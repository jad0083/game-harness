"""The decisions list names the model of each decision (dashboard.html `shortModel`), run under node."""

import json
import re
import shutil
import subprocess

import pytest

from pilot.config import REPO

HTML = (REPO / "src/pilot/static/dashboard.html").read_text(encoding="utf-8")


def short_model(d: dict) -> str:
    fn = re.search(r"^function shortModel\(d\) \{.*?^\}", HTML, re.DOTALL | re.MULTILINE)
    assert fn, "dashboard.html defines shortModel(d)"
    js = fn.group(0) + f"\nprocess.stdout.write(shortModel({json.dumps(d)}));"
    return subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
@pytest.mark.parametrize("d, label", [
    ({"model": "google:gemini-3.1-pro-preview", "thinking": "medium"}, "Gemini 3.1 Pro · medium"),
    ({"model": "google:gemini-3.8-flash", "thinking": "high"}, "Gemini 3.8 Flash · high"),
    ({"model": "anthropic:claude-sonnet-5", "thinking": "medium"}, "Sonnet 5 (API) · medium"),
    ({"model": "claude-code:sonnet", "model_version": "claude-sonnet-5", "thinking": "high"}, "Sonnet 5 (Claude Code) · high"),
    ({"model": "claude-code:opus", "thinking": ""}, "Opus (Claude Code)"),
    ({"model": "claude-code:sonnet", "model_version": "claude-code:sonnet", "thinking": "medium"},
     "Sonnet (Claude Code) · medium"),
    ({"model": "claude-code:claude-opus-4-5-20251101"}, "Opus 4.5 (Claude Code)"),
    ({"model": "openai:gpt-5.2", "thinking": "low"}, "gpt-5.2 · low"),
    ({"model": "human"}, ""),
])
def test_short_model_label(d, label):
    assert short_model(d) == label


def test_the_decision_row_shows_the_model():
    row = HTML[HTML.index("function renderDecisions"):HTML.index("async function selectDecision")]
    assert "shortModel(d)" in row
