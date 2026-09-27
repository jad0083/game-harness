"""District placement, stage A (docs/design/2026-09-27-civ6-levers-design.md, ruling 30): the pure scorer
against the committed rules (corpora/civ6/data/_adjacency.json) on a small hex map, and the read-only
script on a saved reply."""

import json
import sqlite3
import subprocess
import sys

from pilot.civ6_placement import (
    Rules,
    adjacency,
    go_verdict,
    lost_value,
    rate_candidates,
    rate_placed,
    relative_shares,
    report,
    report_text,
)
from pilot.config import REPO

RULES = Rules.load(REPO / "corpora/civ6")
W, H = 12, 12


def neighbours(x: int, y: int) -> list[tuple[int, int]]:
    """Odd rows shifted right (the mock's layout); the scorer itself only follows `adj` lists."""
    odd = y & 1
    steps = [(-1, 0), (1, 0), (-1 + odd, -1), (odd, -1), (-1 + odd, 1), (odd, 1)]
    return [(x + dx, y + dy) for dx, dy in steps if 0 <= x + dx < W and 0 <= y + dy < H]


def idx(x: int, y: int) -> str:
    return str(y * W + x)


def world(**over) -> dict[str, dict]:
    """Grassland owned by player 0; `over["x,y"]` sets a plot's facts (short keys, as district-plots)."""
    plots = {}
    for y in range(H):
        for x in range(W):
            plots[idx(x, y)] = {"x": x, "y": y, "t": "GRASS", "o": 0,
                                "adj": [int(idx(*n)) for n in neighbours(x, y)], **over.get(f"{x},{y}", {})}
    return plots


def ring(x: int, y: int, r: int = 3) -> list[int]:
    seen, frontier = {(x, y)}, [(x, y)]
    for _ in range(r):
        frontier = [n for f in frontier for n in neighbours(*f) if n not in seen]
        seen |= set(frontier)
    return [int(idx(*p)) for p in seen]


def test_adjacency_follows_the_games_rules():
    around = neighbours(5, 5)
    plots = world(**{f"{around[0][0]},{around[0][1]}": {"t": "GRASS_MOUNTAIN", "mountain": True},
                     f"{around[1][0]},{around[1][1]}": {"t": "PLAINS_MOUNTAIN", "mountain": True},
                     f"{around[2][0]},{around[2][1]}": {"d": "CITY_CENTER"},
                     f"{around[3][0]},{around[3][1]}": {"d": "HOLY_SITE"},
                     f"{around[4][0]},{around[4][1]}": {"f": "JUNGLE"}})
    assert adjacency(RULES, "DISTRICT_CAMPUS", idx(5, 5), plots) == {"YIELD_SCIENCE": 3}, "2 mountains, 2 districts"
    assert adjacency(RULES, "DISTRICT_HOLY_SITE", idx(5, 5), plots) == {"YIELD_FAITH": 3}
    assert adjacency(RULES, "DISTRICT_THEATER", idx(5, 5), plots) == {"YIELD_CULTURE": 1}
    river = world(**{"5,5": {"river": True}, f"{around[0][0]},{around[0][1]}": {"d": "HARBOR"}})
    assert adjacency(RULES, "DISTRICT_COMMERCIAL_HUB", idx(5, 5), river) == {"YIELD_GOLD": 4}, "river 2, harbour 2"
    assert adjacency(RULES, "DISTRICT_SEOWON", idx(5, 5), world())["YIELD_SCIENCE"] == 4, "a `Self` rule"
    reef = world(**{f"{around[0][0]},{around[0][1]}": {"f": "REEF", "water": True}})
    assert adjacency(RULES, "DISTRICT_CAMPUS", idx(5, 5), reef) == {"YIELD_SCIENCE": 2}
    iron = world(**{f"{around[0][0]},{around[0][1]}": {"r": "IRON"}})
    assert adjacency(RULES, "DISTRICT_INDUSTRIAL_ZONE", idx(5, 5), iron) == {"YIELD_PRODUCTION": 1}, "strategic class"
    assert adjacency(RULES, "DISTRICT_LAVRA", idx(5, 5), plots) == {"YIELD_FAITH": 3}, "a unique district's own rules"
    assert lost_value({"r": "WHEAT", "i": "FARM", "f": "FOREST"}) == 6 and lost_value({}) == 0
    # a wonder stands on a DISTRICT_WONDER plot (seen live at T202): a wonder for the Theater once built,
    # never a district
    wonder = world(**{f"{around[0][0]},{around[0][1]}": {"d": "WONDER", "w": "PYRAMIDS", "built": True},
                      f"{around[2][0]},{around[2][1]}": {"d": "WONDER", "w": "GREAT_BATH", "built": False},
                      f"{around[1][0]},{around[1][1]}": {"d": "CITY_CENTER"}})
    assert adjacency(RULES, "DISTRICT_THEATER", idx(5, 5), wonder) == {"YIELD_CULTURE": 2}, "the Great Bath is unfinished"
    assert adjacency(RULES, "DISTRICT_CAMPUS", idx(5, 5), wonder) == {}


def test_relative_shares_are_one_for_an_even_split():
    assert relative_shares({"science": 30, "faith": 10}) == {"science": 1.5, "faith": 0.5}
    assert set(relative_shares({}).values()) == {1.0}


def _campus_and_holy_site_city(shares_first: dict) -> tuple[dict, dict]:
    """One plot is best for both a Campus and a Holy Site (two mountains); a second has one mountain."""
    near_best, near_next = neighbours(5, 5), neighbours(8, 5)
    plots = world(**{f"{near_best[0][0]},{near_best[0][1]}": {"t": "GRASS_MOUNTAIN", "mountain": True},
                     f"{near_best[1][0]},{near_best[1][1]}": {"t": "GRASS_MOUNTAIN", "mountain": True},
                     f"{near_next[0][0]},{near_next[0][1]}": {"t": "GRASS_MOUNTAIN", "mountain": True},
                     "8,5": {"f": "FOREST"}})
    city = {"name": "Beijing", "x": 6, "y": 7, "near": ring(6, 7),
            "candidates": [{"type": "DISTRICT_CAMPUS", "plots": [int(idx(5, 5)), int(idx(8, 5))]},
                           {"type": "DISTRICT_HOLY_SITE", "plots": [int(idx(5, 5)), int(idx(8, 5))]},
                           {"type": "DISTRICT_ENCAMPMENT", "plots": [int(idx(4, 7))]}],
            "placed": [{"type": "DISTRICT_CITY_CENTER", "x": 6, "y": 7, "complete": True}]}
    return city, plots


def test_the_heavier_pillar_keeps_its_best_plot():
    city, plots = _campus_and_holy_site_city({})
    rated = rate_candidates(city, plots, RULES, {"science": 30, "faith": 10})
    assert set(rated) == {"DISTRICT_CAMPUS", "DISTRICT_HOLY_SITE"}, "no adjacency rules: not rated"
    campus, holy = rated["DISTRICT_CAMPUS"], rated["DISTRICT_HOLY_SITE"]
    assert (campus[0].x, campus[0].y, campus[0].total, campus[0].penalty) == (5, 5, 2, 0.0)
    assert (holy[0].x, holy[0].y) == (8, 5), "the Holy Site gives the Campus's best plot up"
    reserved = next(r for r in holy if (r.x, r.y) == (5, 5))
    assert reserved.penalty > 0 and holy[0].lost == 1, "the forest is given up"
    flipped = rate_candidates(city, plots, RULES, {"science": 10, "faith": 30})
    assert (flipped["DISTRICT_HOLY_SITE"][0].x, flipped["DISTRICT_CAMPUS"][0].x) == (5, 8)


def _placed_city(gains: list[int]) -> tuple[dict, dict]:
    """Campuses the AI placed on plain plots while a plot with two mountains was free next to each."""
    over, placed = {}, []
    for k, gain in enumerate(gains):
        x, y = 1 + 2 * k, 2 + 4 * (k % 2)
        placed.append({"type": "DISTRICT_CAMPUS", "x": x, "y": y, "complete": True})
        over[f"{x},{y}"] = {"d": "CAMPUS"}
        spot = neighbours(x, y + 3)[0]
        for m in neighbours(*spot)[:gain]:
            over[f"{m[0]},{m[1]}"] = {"t": "GRASS_MOUNTAIN", "mountain": True}
    plots = world(**over)
    free = [int(i) for i, p in plots.items() if not p.get("d")]
    return {"name": "Beijing", "x": 6, "y": 6, "near": free, "placed": placed,
            "candidates": [{"type": "DISTRICT_THEATER", "plots": free}]}, plots


def test_the_ais_placements_are_the_baseline_for_the_go_criterion():
    city, plots = _placed_city([2, 2, 1, 2])
    rated = rate_placed(city, plots, RULES)
    assert len(rated) == 4 and all(r["gain"] >= 1 for r in rated)
    boxed_in = rate_placed({**city, "candidates": []}, plots, RULES)
    assert all(r["gain"] == 0 for r in boxed_in), "a city with no free plot offers no better one"
    assert go_verdict(rated)[0] == "go"
    assert go_verdict(rated[:3])[0] == "wait", "fewer than 4 districts"
    flat = [{**r, "gain": 0} for r in rated]
    verdict, why = go_verdict(flat)
    assert verdict == "no-go" and "the AI already places well" in why


def test_the_report_names_items_by_corpus_id_and_prints_the_verdict():
    city, plots = _campus_and_holy_site_city({})
    data = {"turn": 171, "player": 0, "cities": [city], "plots": plots}
    from pilot.civ6 import CorpusIndex
    r = report(data, RULES, {"science": 30, "faith": 10}, CorpusIndex.load(REPO / "corpora/civ6").cid)
    assert list(r["cities"][0]["candidates"]) == ["district:campus", "district:holy_site"]
    assert r["verdict"] == "wait"
    text = report_text(r)
    assert "- Beijing: district:campus at 5,5 (+2 science; score 3)" in text
    assert text.endswith("the criterion needs 4.")


def test_the_script_reads_a_saved_reply_and_the_campaigns_weights_read_only(tmp_path):
    city, plots = _campus_and_holy_site_city({})
    saved = tmp_path / "plots.json"
    saved.write_text(json.dumps({"turn": 171, "player": 0, "cities": [city], "plots": plots}))
    db = tmp_path / "t.sqlite"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE strategies (campaign_id TEXT, run_id TEXT, t REAL, date TEXT, trigger TEXT, model TEXT, "
                "data TEXT)")
    con.execute("INSERT INTO strategies VALUES ('civ6/x', 'r', 1, 'T170', 'x', 'm', ?)",
                (json.dumps({"pillars": {"science": {"weight": 10}, "faith": {"weight": 30}}}),))
    con.commit()
    con.close()
    before = db.read_bytes()
    out = subprocess.run([sys.executable, str(REPO / "scripts/civ6-placement.py"), "--json", str(saved), "--campaign",
                          "civ6/x", "--telemetry", str(db)], capture_output=True, text=True, check=True).stdout
    assert "- Beijing: district:campus at 8,5" in out and "district:holy_site at 5,5" in out, "faith is heavier"
    assert "Verdict: wait" in out
    assert db.read_bytes() == before
