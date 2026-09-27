"""The `claude-code` provider: Claude through the headless Claude Code CLI (`claude -p`), billed to
the user's Claude subscription instead of an Anthropic API key.

A model string `claude-code:<alias>` (opus, sonnet, haiku, fable, or a full model id) becomes a
pydantic-ai FunctionModel, so the governor's pools, fallback, cool-down, timeouts and traces treat it
like any other model. Each request is one single-shot CLI run:

- the prompt is the conversation rendered as text (stdin); the agent's instructions are the system
  prompt; screenshots are not sent (text only);
- structured output uses the output tool's JSON schema (`--json-schema`); plain-text agents (Talk)
  get the CLI's text result;
- no tools (`--tools ""`), no MCP servers, no settings files, no saved session, an empty temporary
  working directory; the agent's function tools (consult, get_doc...) are not offered;
- the thinking level maps to `--effort` (off and low -> low);
- ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN / ANTHROPIC_BASE_URL are removed from the CLI's
  environment, otherwise it would bill the API organization instead of the subscription.

Any failure (missing CLI, non-zero exit, an error result such as a usage limit, invalid JSON, a
timeout) raises ClaudeCodeError and is never retried here: the caller moves on to its next model.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from pydantic_ai.messages import (
    BinaryContent,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.profiles import ModelProfile
from pydantic_ai.usage import RequestUsage

PREFIX = "claude-code"
MODELS = ("opus", "sonnet", "haiku", "fable")          # CLI aliases offered on the dashboard
ALIAS_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
DROP_ENV = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "CLAUDECODE")
EFFORT = {"off": "low", "low": "low", "medium": "medium", "high": "high"}
DEFAULT_TIMEOUT_S = 120.0
MAX_SYSTEM_ARG = 100_000        # one argv string is limited to 128 KiB on Linux; longer goes to stdin
ERR_CHARS = 400
IMAGE_NOTE = "[image omitted: this model receives text only]"


class ClaudeCodeError(RuntimeError):
    """The CLI gave no usable answer; the message carries its error text (truncated)."""


def find_claude() -> str | None:
    """The `claude` executable: on PATH, else the per-user install (~/.local/bin/claude), which a
    systemd service's PATH often lacks."""
    found = shutil.which("claude")
    if found:
        return found
    local = Path(os.path.expanduser("~")) / ".local/bin/claude"
    return str(local) if local.is_file() and os.access(local, os.X_OK) else None


def cli_env() -> dict[str, str]:
    """os.environ without the API-key variables (the subscription must pay, not the API org)."""
    return {k: v for k, v in os.environ.items() if k not in DROP_ENV}


def _content(c) -> str:
    if isinstance(c, str):
        return c
    if isinstance(c, BinaryContent):
        return IMAGE_NOTE if c.is_image else f"[{c.media_type} attachment omitted]"
    if isinstance(c, (list, tuple)):
        return "\n".join(_content(x) for x in c)
    try:
        return json.dumps(c, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(c)


def render(messages: list[ModelMessage]) -> tuple[str, str]:
    """(system text, prompt text) from pydantic-ai messages. A single request is sent as is; a
    conversation with earlier answers is labelled turn by turn."""
    system: list[str] = []
    turns: list[tuple[str, str]] = []
    for m in messages:
        if isinstance(m, ModelRequest):
            for p in m.parts:
                if isinstance(p, SystemPromptPart):
                    system.append(p.content)
                elif isinstance(p, UserPromptPart):
                    turns.append(("User", _content(p.content)))
                elif isinstance(p, ToolReturnPart):
                    turns.append(("Tool result", f"{p.tool_name}: {_content(p.content)}"))
                elif isinstance(p, RetryPromptPart):
                    turns.append(("User", p.model_response()))
        elif isinstance(m, ModelResponse):
            for p in m.parts:
                if isinstance(p, TextPart):
                    turns.append(("Assistant", p.content))
                elif isinstance(p, ToolCallPart):
                    turns.append(("Assistant", f"(called {p.tool_name} with {p.args_as_json_str()})"))
    if len(turns) == 1:
        return "\n\n".join(system), turns[0][1]
    return "\n\n".join(system), "\n\n".join(f"## {who}\n{text}" for who, text in turns)


def _usage(d: dict) -> RequestUsage:
    u = d.get("usage") or {}
    read, write = int(u.get("cache_read_input_tokens") or 0), int(u.get("cache_creation_input_tokens") or 0)
    return RequestUsage(input_tokens=int(u.get("input_tokens") or 0) + read + write,
                        output_tokens=int(u.get("output_tokens") or 0),
                        cache_read_tokens=read, cache_write_tokens=write)


def _short(text: str) -> str:
    text = (text or "").strip()
    return text if len(text) <= ERR_CHARS else text[:ERR_CHARS] + "..."


def model(alias: str) -> FunctionModel:
    """A pydantic-ai model that answers through `claude -p --model <alias>`."""
    if not ALIAS_RE.match(alias):
        raise ValueError(f"not a Claude model alias: {alias!r}")

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        exe = find_claude()
        if not exe:
            raise ClaudeCodeError("claude CLI not found on PATH or in ~/.local/bin; install Claude Code "
                                  "and log in with the subscription (claude /login)")
        system, prompt = render(messages)
        if info.instructions:
            system = (info.instructions + "\n\n" + system).strip()
        if len(system) > MAX_SYSTEM_ARG:
            prompt, system = f"# Instructions\n{system}\n\n# Request\n{prompt}", "Follow the instructions in the request."
        settings = info.model_settings or {}
        timeout = float(settings.get("timeout") or DEFAULT_TIMEOUT_S)
        cmd = [exe, "-p", "--model", alias, "--output-format", "json", "--tools", "",
               "--no-session-persistence", "--setting-sources", "", "--strict-mcp-config",
               "--disable-slash-commands", "--max-turns", "3", "--system-prompt", system or "You are a helpful assistant."]
        thinking = getattr(info.model_request_parameters, "thinking", None)
        effort = EFFORT.get("off" if thinking is False else str(thinking)) if thinking is not None else None
        if effort:
            cmd += ["--effort", effort]
        out_tool = info.output_tools[0] if info.output_tools else None
        if out_tool is not None:
            cmd += ["--json-schema", json.dumps(out_tool.parameters_json_schema)]
        with tempfile.TemporaryDirectory(prefix="pilot-claude-") as cwd:
            try:
                proc = subprocess.run(cmd, input=prompt, cwd=cwd, env=cli_env(), capture_output=True,
                                      text=True, timeout=timeout, check=False)
            except subprocess.TimeoutExpired as e:
                raise ClaudeCodeError(f"claude-code:{alias} timed out after {timeout:.0f} s") from e
            except OSError as e:
                raise ClaudeCodeError(f"claude-code:{alias} could not start {exe}: {e}") from e
        try:
            d = json.loads(proc.stdout)
        except ValueError:
            d = None
        if not isinstance(d, dict):
            if proc.returncode:
                raise ClaudeCodeError(f"claude-code:{alias} exit {proc.returncode}: {_short(proc.stderr or proc.stdout)}")
            raise ClaudeCodeError(f"claude-code:{alias} answer is not JSON: {_short(proc.stdout)}")
        if d.get("is_error") or proc.returncode:
            detail = d.get("result") or d.get("subtype") or proc.stderr
            status = f" (API {d['api_error_status']})" if d.get("api_error_status") else ""
            raise ClaudeCodeError(f"claude-code:{alias} error{status}, exit {proc.returncode}: {_short(str(detail))}")
        details = {"served_model": ", ".join((d.get("modelUsage") or {}).keys()), "session_id": d.get("session_id")}
        if out_tool is not None:
            data = d.get("structured_output")
            if not isinstance(data, dict):
                raise ClaudeCodeError(f"claude-code:{alias} gave no structured output: {_short(str(d.get('result')))}")
            part = ToolCallPart(out_tool.name, data)
        else:
            part = TextPart(str(d.get("result") or ""))
        return ModelResponse(parts=[part], usage=_usage(d), provider_details=details)

    # supports_thinking: pydantic-ai passes the thinking level on (as request parameters) for --effort
    profile = ModelProfile(supports_json_schema_output=True, supports_json_object_output=True, supports_thinking=True)
    return FunctionModel(respond, model_name=f"{PREFIX}:{alias}", profile=profile)


def resolve_model(m):
    """A `claude-code:<alias>` string becomes its model object; anything else is returned as is
    (pydantic-ai resolves other provider strings itself)."""
    if isinstance(m, str) and m.startswith(PREFIX + ":"):
        return model(m.split(":", 1)[1])
    return m
