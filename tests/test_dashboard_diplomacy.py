"""The activity feed names each diplomacy answer the Civ VI library gave for us (dashboard.html
`describe`, the `diplomacy_reply` event), run under node."""

import json
import re
import shutil
import subprocess

import pytest

from pilot.config import REPO

HTML = (REPO / "src/pilot/static/dashboard.html").read_text(encoding="utf-8")


def describe(ev: dict) -> str:
    fn = re.search(r"^function describe\(ev\) \{.*?^\}", HTML, re.DOTALL | re.MULTILINE)
    assert fn, "dashboard.html defines describe(ev)"
    js = fn.group(0) + f"\nprocess.stdout.write(describe({json.dumps(ev)}));"
    return subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
@pytest.mark.parametrize("ev, text", [
    ({"kind": "diplomacy_reply", "date": "T240", "civ": "civ:australia", "from": 3,
      "statement": "WARNING_TOO_MANY_TROOPS_NEAR_ME", "subtype": "NONE", "text": "the conciliatory reply (a promise)"},
     "T240: civ:australia warning too many troops near me answered: the conciliatory reply (a promise)"),
    ({"kind": "diplomacy_reply", "date": "T240", "civ": None, "from": 3,
      "statement": "WARNING_TOO_MANY_TROOPS_NEAR_ME", "subtype": "POSITIVE", "text": "Goodbye"},
     "T240: player 3 warning too many troops near me (follow-up) answered: Goodbye"),
])
def test_a_diplomacy_reply_reads_as_a_sentence(ev, text):
    assert describe(ev) == text
