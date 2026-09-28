"""The military threat tests (docs/design/2026-09-27-postmortem-fixes-design.md, rulings 1 and 18),
replayed on the Kublai campaign's metrics rows (tests/fixtures/civ6_kublai_rows.json, T41-T583)."""

import itertools
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


# ---- rulings 10-13: falling behind, neighbour buildup, gold per turn, loyalty --------------------

SPEC = load_pillars(REPO / "corpora/civ6")


def test_e4_falling_behind_counts_reproduce_with_per_measure_factors():
    from pilot.threat import behind
    factors = dict(SPEC.peers.behind)
    counts = dict.fromkeys(factors, 0)
    was: set = set()
    for r in ROWS:
        now = set(behind(r, factors, SPEC.peers.last_min_peers))
        for m in now - was:
            counts[m] += 1
        was = now
    assert counts == {"military": 10, "techs": 9, "civics": 0, "score": 2, "cities": 2}
    t457 = next(r for r in ROWS if r["turn"] == 457)
    from pilot.threat import behind_text
    assert behind_text(t457, "military").startswith("falling behind in military: ")


def test_e3_neighbour_buildup_fires_18_times_australia_first_at_t478():
    from pilot.threat import buildup, buildup_text
    fired: dict = {}
    fires = []
    for i, r in enumerate(ROWS):
        rows = [{**x, "neighbours": [{**n, "allied": n["name"] == "CIVILIZATION_MALI" and x["turn"] >= 511}
                                     for n in x["neighbours"]]} for x in ROWS[max(0, i - 40):i + 1]]
        fires += [(r["turn"], f) for f in buildup(rows, 20, lambda d: int(d[1:]), fired=fired)]
    assert len(fires) == 18 and (fires[0][0], fires[-1][0]) == (344, 561)
    aus = [(t, f) for t, f in fires if f["name"] == "CIVILIZATION_AUSTRALIA"]
    assert aus[0][0] == 478 and (aus[0][1]["base"], aus[0][1]["military"], aus[0][1]["ours"]) == (345, 598, 295)
    assert 512 not in [t for t, _ in aus], "718 -> 955 over T496-T512 is +33%"
    assert (510, "CIVILIZATION_MAYA") in [(t, f["name"]) for t, f in fires]
    assert buildup_text(aus[0][1], "turns").startswith("neighbour buildup: CIVILIZATION_AUSTRALIA 598 military (+73% in ")
    assert buildup_text(aus[0][1], "turns").endswith("), 2.0x ours (295)")
    names = [(t, f["name"]) for t, f in fires]
    for t, name in names:
        assert not any(name == n and t < t2 < t + 20 for t2, n in names), "at most once per neighbour per window"


def test_an_ally_never_fires():
    from pilot.threat import buildup
    rows = [{"date": "T10", "military": 100, "neighbours": [{"name": "MALI", "military": 200, "allied": True}]},
            {"date": "T20", "military": 100, "neighbours": [{"name": "MALI", "military": 400, "allied": True}]}]
    assert buildup(rows, 20, lambda d: int(d[1:])) == []
    rows[1]["neighbours"][0]["allied"] = False
    assert [f["name"] for f in buildup(rows, 20, lambda d: int(d[1:]))] == ["MALI"]


def test_e5_gold_per_turn_turns_negative_five_times():
    from pilot.civ6 import urgent_changes
    fires = []
    for a, b in itertools.pairwise(ROWS):
        reasons = urgent_changes({"yields": {"gold": a["gold_yield"]}}, {"yields": {"gold": b["gold_yield"]}})
        fires += [(b["turn"], x) for x in reasons if x.startswith("gold per turn negative")]
    assert [t for t, _ in fires] == [77, 84, 123, 291, 583]
    assert next(x for t, x in fires if t == 291) == "gold per turn negative: " + format(
        next(r["gold_yield"] for r in ROWS if r["turn"] == 291), ".1f")


def _loyal(turn: int, **cities) -> dict:
    return {"turn": turn, "cities": [{"name": n, "loyalty": v} for n, v in cities.items()]}


def test_loyalty_falling_fires_for_haarlem_at_t547_and_rockhampton_once():
    from pilot.threat import loyalty_falls, loyalty_rose
    assert loyalty_falls(_loyal(546, Haarlem=95), _loyal(547, Haarlem=77)) == [{"name": "Haarlem", "loyalty": 77, "drop": 18.0}]
    assert loyalty_falls(_loyal(546, Haarlem=95), _loyal(547, Haarlem=90)) == [], "90 > 5 x 5 and over 50"
    fired: set = set()
    series = {552 + i: round(93 - 90 * i / 16) for i in range(17)}         # 93 at T552 to 3 at T568
    snaps = [_loyal(t, Rockhampton=v) for t, v in series.items()]
    count = 0
    for a, b in itertools.pairwise(snaps):
        fired -= loyalty_rose(a, b)
        for f in loyalty_falls(a, b):
            if f["name"] not in fired:
                fired.add(f["name"])
                count += 1
    assert count == 1
    assert loyalty_rose(_loyal(1, A=40), _loyal(2, A=45)) == {"A"}, "a rise re-arms it"
