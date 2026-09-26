"""Decision traces: a model run's messages as plain JSON steps for the dashboard
(prompt, thinking, text, tool calls with arguments, tool results, retries, final answer).
Images are replaced by a placeholder; long texts are cut."""

from __future__ import annotations

import json
from typing import Any

from pydantic_ai import BinaryContent
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

MAX_TEXT = 6000
OUTPUT_TOOL_PREFIX = "final_result"


def _text(content: Any) -> str:
    if isinstance(content, str):
        s = content
    elif isinstance(content, BinaryContent):
        s = "[image]" if content.is_image else f"[{content.media_type}]"
    elif isinstance(content, (list, tuple)):
        s = "\n".join(_text(c) for c in content)
    else:
        try:
            s = json.dumps(content, ensure_ascii=False, default=str, indent=1)
        except (TypeError, ValueError):
            s = str(content)
    return s if len(s) <= MAX_TEXT else s[:MAX_TEXT] + f"… [{len(s) - MAX_TEXT} more chars]"


def serialize(messages: list[ModelMessage]) -> list[dict]:
    steps: list[dict] = []
    for m in messages:
        if isinstance(m, ModelRequest):
            for p in m.parts:
                if isinstance(p, UserPromptPart):
                    steps.append({"type": "prompt", "text": _text(p.content)})
                elif isinstance(p, ToolReturnPart):
                    steps.append({"type": "tool_result", "tool": p.tool_name, "text": _text(p.content)})
                elif isinstance(p, RetryPromptPart):
                    steps.append({"type": "retry", "tool": p.tool_name or "", "text": _text(p.content)})
        elif isinstance(m, ModelResponse):
            usage = {"in": m.usage.input_tokens or 0, "out": m.usage.output_tokens or 0}
            for p in m.parts:
                if isinstance(p, ThinkingPart):
                    if p.content:
                        steps.append({"type": "thinking", "text": _text(p.content)})
                elif isinstance(p, TextPart):
                    if p.content.strip():
                        steps.append({"type": "text", "text": _text(p.content)})
                elif isinstance(p, ToolCallPart):
                    kind = "output" if p.tool_name.startswith(OUTPUT_TOOL_PREFIX) else "tool_call"
                    steps.append({"type": kind, "tool": p.tool_name, "args": p.args_as_dict()})
            steps.append({"type": "usage", **usage})
    return steps
