"""The claude-code provider: Claude through the headless Claude Code CLI (the user's subscription).
The real CLI is never called here: subprocess.run is replaced by a recorder with canned results."""

import json
import subprocess
from pathlib import Path

import pytest
from pydantic_ai import Agent, BinaryContent
from pydantic_ai.messages import ModelResponse

from pilot import claude_code
from pilot.config import REPO
from pilot.pillars import load_pillars
from pilot.strategy import review_model

STELLARIS = load_pillars(REPO / "corpora/stellaris")


def _result(structured=None, *, result="", is_error=False, subtype="success", model="claude-opus-4-1") -> str:
    """A `claude -p --output-format json` result, in the shape the CLI printed in a live run."""
    out = {"type": "result", "subtype": subtype, "is_error": is_error, "num_turns": 2, "result": result,
           "session_id": "s-1", "api_error_status": None,
           "usage": {"input_tokens": 1000, "cache_creation_input_tokens": 200, "cache_read_input_tokens": 300,
                     "output_tokens": 111},
           "modelUsage": {model: {"inputTokens": 1000, "outputTokens": 111}}}
    if structured is not None:
        out["structured_output"] = structured
    return json.dumps(out)


class FakeRun:
    """Stands in for subprocess.run: records each call, answers with the queued outcome."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls: list[dict] = []

    def __call__(self, cmd, **kw):
        self.calls.append({"cmd": cmd, **kw})
        o = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
        if isinstance(o, BaseException):
            raise o
        code, stdout, stderr = o if isinstance(o, tuple) else (0, o, "")
        return subprocess.CompletedProcess(cmd, code, stdout, stderr)


@pytest.fixture
def cli(monkeypatch):
    monkeypatch.setattr(claude_code, "find_claude", lambda: "/usr/bin/claude-test")

    def install(*outcomes):
        fake = FakeRun(*outcomes)
        monkeypatch.setattr(claude_code.subprocess, "run", fake)
        return fake
    return install


def _review_answer():
    prios = {"defence": 1, "economy": 2, "technology": 3, "expansion": 4, "diplomacy": 5, "government": 6, "society": 7}
    pillars = {p: {"priority": n, "stance": f"{p} stance", "goals": ["g"],
                   "milestones": [{"metric": "systems", "op": ">=", "target": 10, "by": "2230.01.01"}] if n <= 3 else []}
               for p, n in prios.items()}
    return {"change": True, "assessment": "grew well", "rules": [], "strategy": {**pillars, "focus": "grow", "reason": "start"}}


def test_a_strategy_review_answer_parses_into_the_generated_output_type(cli, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-empty-org")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "tok")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://proxy")
    fake = cli(_result(_review_answer()))
    Review = review_model(STELLARIS)
    agent = Agent(claude_code.model("opus"), output_type=Review, instructions="You are the strategist.",
                  model_settings={"timeout": 77.0, "thinking": "high"})
    result = agent.run_sync("Review the strategy.")
    assert isinstance(result.output, Review)
    assert result.output.change is True and result.output.assessment == "grew well"
    assert result.output.strategy.focus == "grow"
    # usage from the CLI: input includes cache reads/writes (pydantic-ai convention)
    assert result.usage.input_tokens == 1500 and result.usage.output_tokens == 111
    answer = [m for m in result.all_messages() if isinstance(m, ModelResponse)][-1]
    assert answer.model_name == "claude-code:opus"
    assert answer.provider_details["served_model"] == "claude-opus-4-1"

    call = fake.calls[0]
    cmd = call["cmd"]
    assert cmd[0] == "/usr/bin/claude-test" and "-p" in cmd
    assert cmd[cmd.index("--model") + 1] == "opus"
    assert cmd[cmd.index("--output-format") + 1] == "json"
    assert cmd[cmd.index("--tools") + 1] == ""
    assert "--no-session-persistence" in cmd
    assert cmd[cmd.index("--setting-sources") + 1] == ""
    assert cmd[cmd.index("--effort") + 1] == "high"
    schema = json.loads(cmd[cmd.index("--json-schema") + 1])
    assert "change" in schema["properties"] and "assessment" in schema["properties"]
    assert "You are the strategist." in cmd[cmd.index("--system-prompt") + 1]
    assert "Review the strategy." in call["input"]                  # the prompt goes through stdin
    env = call["env"]
    for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL"):
        assert k not in env, f"{k} would bill the API organization instead of the subscription"
    assert env.get("HOME"), "the CLI finds its subscription credentials under HOME"
    assert call["timeout"] == 77.0
    assert Path(call["cwd"]).resolve() != REPO and not Path(call["cwd"]).exists(), "an empty temp dir, removed after"


def test_text_output_needs_no_schema(cli):
    fake = cli(_result(result="Our economy is fine."))
    agent = Agent(claude_code.model("sonnet"), output_type=str, instructions="Chat.")
    assert agent.run_sync("How is the economy?").output == "Our economy is fine."
    assert "--json-schema" not in fake.calls[0]["cmd"]


def test_an_error_result_raises_with_the_cli_message(cli):
    cli(_result(result="Claude AI usage limit reached|1760000000", is_error=True, subtype="error_during_execution"))
    agent = Agent(claude_code.model("opus"), output_type=review_model(STELLARIS))
    with pytest.raises(claude_code.ClaudeCodeError, match="usage limit reached"):
        agent.run_sync("Review.")


def test_a_failed_process_raises_with_stderr(cli):
    cli((1, "", "Error: Invalid API key · Please run /login"))
    agent = Agent(claude_code.model("opus"), output_type=review_model(STELLARIS))
    with pytest.raises(claude_code.ClaudeCodeError, match="exit 1.*Please run /login"):
        agent.run_sync("Review.")


def test_invalid_json_and_timeouts_raise(cli):
    cli("not json at all")
    agent = Agent(claude_code.model("opus"), output_type=review_model(STELLARIS))
    with pytest.raises(claude_code.ClaudeCodeError, match="not JSON"):
        agent.run_sync("Review.")
    cli(subprocess.TimeoutExpired(["claude"], 5))
    with pytest.raises(claude_code.ClaudeCodeError, match="timed out"):
        agent.run_sync("Review.")


def test_a_missing_structured_output_raises(cli):
    cli(_result(None, result="I think we should expand."))
    agent = Agent(claude_code.model("opus"), output_type=review_model(STELLARIS))
    with pytest.raises(claude_code.ClaudeCodeError, match="no structured output"):
        agent.run_sync("Review.")


def test_a_missing_cli_is_a_clear_error(monkeypatch):
    monkeypatch.setattr(claude_code, "find_claude", lambda: None)
    agent = Agent(claude_code.model("opus"), output_type=str)
    with pytest.raises(claude_code.ClaudeCodeError, match="claude CLI not found"):
        agent.run_sync("hi")


def test_find_claude_falls_back_to_the_user_install(monkeypatch, tmp_path):
    monkeypatch.setattr(claude_code.shutil, "which", lambda name: None)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert claude_code.find_claude() is None
    exe = tmp_path / ".local/bin/claude"
    exe.parent.mkdir(parents=True)
    exe.write_text("#!/bin/sh\n")
    exe.chmod(0o755)
    assert claude_code.find_claude() == str(exe)


def test_images_and_tool_results_become_text(cli):
    fake = cli(_result(result="ok"))
    agent = Agent(claude_code.model("haiku"), output_type=str)
    agent.run_sync(["Look at this", BinaryContent(data=b"\xff\xd8", media_type="image/jpeg")])
    assert "Look at this" in fake.calls[0]["input"] and "image omitted" in fake.calls[0]["input"]


def test_resolve_model_only_wraps_claude_code_names():
    m = claude_code.resolve_model("claude-code:opus")
    assert m.model_name == "claude-code:opus"
    assert claude_code.resolve_model("google:gemini-3.8-flash") == "google:gemini-3.8-flash"
    obj = object()
    assert claude_code.resolve_model(obj) is obj
    with pytest.raises(ValueError):
        claude_code.model("--dangerously-skip-permissions")


def test_the_provider_is_listed_and_accepted_without_an_api_key(monkeypatch):
    from pilot.config import Settings
    from pilot.models import check_pool, provider_catalog
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(claude_code, "find_claude", lambda: "/usr/bin/claude-test")
    cat = {p["id"]: p for p in provider_catalog(Settings(), list_models=lambda provider: [])}
    cc = cat["claude-code"]
    assert cc["label"] == "Claude Code (subscription)" and cc["configured"]
    assert {"claude-code:opus", "claude-code:sonnet", "claude-code:haiku", "claude-code:fable"} <= set(cc["models"])
    assert check_pool([{"model": "claude-code:opus", "thinking": "high"}]) == [{"model": "claude-code:opus", "thinking": "high"}]
    monkeypatch.setattr(claude_code, "find_claude", lambda: None)
    cc = {p["id"]: p for p in provider_catalog(Settings(), list_models=lambda provider: [])}["claude-code"]
    assert not cc["configured"] and "claude" in cc["hint"]


def test_pilot_check_reports_the_cli(monkeypatch, capsys):
    from dataclasses import replace

    from pilot.cli import check_claude_cli
    from pilot.config import Settings
    s = Settings(model="google:gemini-3.8-flash", fallback_model=None)
    monkeypatch.setattr(claude_code, "find_claude", lambda: None)
    assert check_claude_cli(s) is True, "not needed: only a note"
    uses = replace(s, roles={"strategy": {"models": [{"model": "claude-code:opus", "thinking": "high"}], "rotate": False}})
    assert check_claude_cli(uses) is False
    assert "claude-code:* model is configured" in capsys.readouterr().out
    monkeypatch.setattr(claude_code, "find_claude", lambda: "/home/u/.local/bin/claude")
    assert check_claude_cli(uses) is True
    assert "/home/u/.local/bin/claude" in capsys.readouterr().out


def test_the_catalog_offers_versioned_claude_models_next_to_the_aliases(monkeypatch):
    from pilot.config import Settings
    from pilot.models import provider_catalog
    monkeypatch.setattr(claude_code, "find_claude", lambda: "/usr/bin/claude-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    listing = {"anthropic": ["anthropic:claude-opus-5-5", "anthropic:claude-opus-4-5-20251101"]}
    cc = {p["id"]: p for p in provider_catalog(Settings(), list_models=lambda provider: listing.get(provider, []))}["claude-code"]
    assert {"claude-code:opus", "claude-code:claude-opus-5-5", "claude-code:claude-opus-4-5-20251101"} <= set(cc["models"])
    assert cc["error"] == ""


def test_a_failed_version_listing_keeps_the_aliases_and_says_why(monkeypatch):
    from pilot.config import Settings
    from pilot.models import provider_catalog
    monkeypatch.setattr(claude_code, "find_claude", lambda: "/usr/bin/claude-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    def listing(provider):
        if provider == "anthropic":
            raise RuntimeError("listing down")
        return []
    cc = {p["id"]: p for p in provider_catalog(Settings(), list_models=listing)}["claude-code"]
    assert "claude-code:opus" in cc["models"] and not any("claude-opus-5" in m for m in cc["models"])
    assert "versions not listed" in cc["error"] and "listing down" in cc["error"]
