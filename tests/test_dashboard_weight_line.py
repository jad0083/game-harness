"""The Strategy tab's "not working here" tooltip names what the directive record measured
(dashboard.html `weightLine`), run under node: ours ÷ the peer median when the record is relative
(stellaris levers design, ruling 7), as the frame and the Strategist print it."""

import json
import re
import shutil
import subprocess

import pytest

from pilot.config import REPO

HTML = (REPO / "src/pilot/static/dashboard.html").read_text(encoding="utf-8")


def weight_line(pl: dict, p: dict, total: float) -> str:
    consts = [re.search(rf"^const {name} = .*?;$", HTML, re.DOTALL | re.MULTILINE) for name in ("esc", "fmt", "human", "MS_STATUS")]
    fn = re.search(r"^function weightLine\(pl, p, total\) \{.*?^\}", HTML, re.DOTALL | re.MULTILINE)
    assert all(consts) and fn, "dashboard.html defines esc, fmt, human, MS_STATUS and weightLine"
    js = "\n".join(c.group(0) for c in consts) + "\n" + fn.group(0) + \
        f"\nprocess.stdout.write(weightLine({json.dumps(pl)}, {json.dumps(p)}, {json.dumps(total)}));"
    return subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout


def _title(html: str) -> str:
    return re.search(r'class="p-need bad" title="([^"]*)"', html).group(1)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_not_working_tooltip_says_divided_by_the_median_for_a_relative_record():
    record = {"directive": "defend", "metric": "military_power", "held_rate": 0.008, "other_rate": -0.009,
              "held_years": 3.5, "relative": True}
    p = {"status": "on_track", "need": 1.0, "efficacy": 0.5, "pressure": 10.0, "record": record}
    assert _title(weight_line({"weight": 20}, p, 40.0)) == \
        "military power ÷ median +0.008/yr over 3.5 years with defend vs -0.009/yr otherwise"
    absolute = {**record, "relative": False, "metric": "influence", "held_rate": 1.5, "other_rate": 2.0}
    assert _title(weight_line({"weight": 20}, {**p, "record": absolute}, 40.0)) == \
        "influence +1.5/yr over 3.5 years with defend vs +2/yr otherwise", "Civ VI and metrics without a median"
