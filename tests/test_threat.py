"""The military threat tests (docs/design/2026-09-27-postmortem-fixes-design.md, rulings 1 and 18),
replayed on the Kublai campaign's metrics rows (tests/fixtures/civ6_kublai_rows.json, T41-T583)."""

import json

from pilot.config import REPO
from pilot.pillars import load_pillars
from pilot.threat import relative_military, weakness, weakness_line

ROWS = json.loads((REPO / "tests/fixtures/civ6_kublai_rows.json").read_text(encoding="utf-8"))
BUY = load_pillars(REPO / "corpora/civ6").actions["purchase"]


def as_snapshot(row: dict) -> dict:
    """A metrics row as the snapshot fields the test reads. Rows keep no alliance and no enemy kind:
    Mali is an ally from T511 (E1), and every war counts (city-states included)."""
    return {"military": row["military"], "wars": [{"major": True, "civ": "?"}] * (row.get("wars") or 0),
            "majors": [{"civ": n["name"], "military": n["military"],
                        "allied": n["name"] == "CIVILIZATION_MALI" and row["turn"] >= 511} for n in row["neighbours"]]}


def test_e1_the_weakness_test_holds_in_every_pre_war_row_from_t380():
    bands = {(41, 199): (134, 73, 36, 14, 10, 88), (200, 299): (41, 0, 0, 0, 0, 0), (300, 379): (37, 4, 13, 23, 24, 26),
             (380, 459): (42, 9, 0, 13, 42, 42), (460, 540): (31, 0, 25, 31, 31, 31), (541, 583): (40, 39, 40, 40, 40, 40)}
    for (lo, hi), want in bands.items():
        rows = [r for r in ROWS if lo <= r["turn"] <= hi]
        clauses = [{c["clause"] for c in weakness(as_snapshot(r), BUY)} for r in rows]
        got = (len(rows), *(sum(1 for c in clauses if k in c) for k in ("war", "last", "low", "outgunned")),
               sum(1 for c in clauses if c))
        assert got == want, (lo, hi, got)


def test_each_clause_and_an_ally_that_does_not_count():
    s = {"military": 343, "wars": [], "majors": [
        {"civ": "CIVILIZATION_MALI", "military": 2428, "allied": True},
        {"civ": "CIVILIZATION_MAYA", "military": 1491}, {"civ": "CIVILIZATION_GERMANY", "military": 1094},
        {"civ": "CIVILIZATION_NETHERLANDS", "military": 900}, {"civ": "CIVILIZATION_AUSTRALIA", "military": 1106}]}
    assert [c["clause"] for c in weakness(s, BUY)] == ["last", "low", "outgunned"]
    line = weakness_line(s, BUY)
    assert line == ("Military weakness: last of 6; 343 is 0.31 x the median 1,106; CIVILIZATION_MALI 2,428 (7.1x, "
                    "allied), CIVILIZATION_MAYA 1,491 (4.3x), CIVILIZATION_AUSTRALIA 1,106 (3.2x), CIVILIZATION_GERMANY "
                    "1,094 (3.2x), CIVILIZATION_NETHERLANDS 900 (2.6x)")
    ally_only = {"military": 400, "wars": [], "majors": [{"civ": "CIVILIZATION_MALI", "military": 2800, "allied": True},
                                                         {"civ": "CIVILIZATION_MAYA", "military": 390},
                                                         {"civ": "CIVILIZATION_GERMANY", "military": 420}]}
    assert weakness(ally_only, BUY) == [], "an allied major at 7x ours does not count"
    war = {"military": 900, "wars": [{"civ": "CIVILIZATION_AUSTRALIA", "major": True}, {"civ": "CS", "major": False}],
           "majors": [{"civ": "CIVILIZATION_AUSTRALIA", "military": 950}]}
    assert weakness(war, BUY) == [{"clause": "war", "text": "at war with CIVILIZATION_AUSTRALIA"}]
    assert weakness({"military": 900, "wars": [{"civ": "CS", "major": False}], "majors": []}, BUY) == [], \
        "a city-state war is not a war with a major"


def test_military_relative_to_the_median_and_the_strongest_non_ally():
    s = {"military": 318, "majors": [{"civ": "A", "military": 1094}, {"civ": "B", "military": 2428, "allied": True},
                                     {"civ": "C", "military": 1491}]}
    assert relative_military(s) == {"military_vs_median": round(318 / 1491, 3), "military_vs_strongest": round(318 / 1491, 3)}
    assert relative_military({"military": 10, "majors": []}) == {"military_vs_median": None, "military_vs_strongest": None}
