"""The activity feed names each diplomacy answer the Civ VI library gave for us (dashboard.html
`describe`, the `diplomacy_reply` event), run under node with the page's own helpers. The row carries
its game date, so the sentence does not repeat it."""

import json
import re
import shutil
import subprocess

import pytest

from pilot.config import REPO

HTML = (REPO / "src/pilot/static/dashboard.html").read_text(encoding="utf-8")
HELPERS = ("esc", "fmt", "human", "tidy", "sentence", "gdate", "clip", "dur", "plural")


def describe(ev: dict) -> str:
    fn = re.search(r"^function describe\(ev\) \{.*?^\}", HTML, re.DOTALL | re.MULTILINE)
    assert fn, "dashboard.html defines describe(ev)"
    consts = [re.search(rf"^const {name} = .*?;$", HTML, re.MULTILINE) for name in HELPERS]
    assert all(consts), f"dashboard.html defines {HELPERS}"
    js = "\n".join(c.group(0) for c in consts) + "\n" + fn.group(0) + \
        f"\nprocess.stdout.write(describe({json.dumps(ev)}));"
    return subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
@pytest.mark.parametrize("ev, text", [
    ({"kind": "diplomacy_reply", "date": "T240", "civ": "civ:australia", "from": 3,
      "statement": "WARNING_TOO_MANY_TROOPS_NEAR_ME", "subtype": "NONE", "text": "the conciliatory reply (a promise)"},
     "Australia: warning too many troops near me; answered: the conciliatory reply (a promise)"),
    ({"kind": "diplomacy_reply", "date": "T240", "civ": None, "from": 3,
      "statement": "WARNING_TOO_MANY_TROOPS_NEAR_ME", "subtype": "POSITIVE", "text": "Goodbye"},
     "Player 3: warning too many troops near me (follow-up); answered: Goodbye"),
    ({"kind": "crisis", "event": "enter", "date": "2291.03.01", "conditions": ["colony Theia occupied"]},
     "War crisis at 2291.03: colony Theia occupied"),
    ({"kind": "crisis", "event": "exit", "date": "2293.01.01", "why": "every war ended"},
     "War crisis over: every war ended"),
])
def test_a_diplomacy_reply_and_a_crisis_read_as_sentences(ev, text):
    assert describe(ev) == text
