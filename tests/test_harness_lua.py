"""corpora/civ6/lua/harness.lua run outside the game: LuaJIT (lupa) with the stand-ins of
tests/fixtures/civ6_lua_mock.lua. It proves syntax and control flow of the snapshot's defence,
religion and blocker fields (docs/design/2026-09-27-civ6-levers-design.md, ruling 11); API names
and results are checked live (games/civ6-kublai/journal.md). Skipped when lupa is not installed."""

import json

import pytest

from pilot.config import REPO

lupa = pytest.importorskip("lupa")

HARNESS = (REPO / "corpora/civ6/lua/harness.lua").read_text(encoding="utf-8")
MOCK = (REPO / "tests/fixtures/civ6_lua_mock.lua").read_text(encoding="utf-8")


def runtime():
    from lupa import LuaRuntime
    rt = LuaRuntime(unpack_returned_tuples=True)
    out: list[str] = []
    rt.globals().print = lambda *a: out.append(" ".join(str(x) for x in a))
    rt.execute(MOCK)
    rt.execute('local HARNESS_VERSION = "test"\n' + HARNESS)
    return rt, out


def snapshot(rt, out, setup: str = "") -> dict:
    if setup:
        rt.execute(setup)
    out.clear()
    rt.execute("Harness.run(Harness.snapshot)")
    assert len(out) == 1, out
    return json.loads(out[0])


def test_the_snapshot_has_the_defence_facts_of_each_city():
    s = snapshot(*runtime())
    assert s["ok"] is True, s.get("error")
    beijing, xian = s["cities"]
    assert (beijing["name"], beijing["x"], beijing["y"]) == ("Beijing", 22, 21)
    assert beijing["garrison"] is None, "a settler on the tile is no garrison (null, not missing)"
    assert beijing["defense"] == {"garrison_hp": 200, "garrison_max": 200, "walls_hp": 0, "walls_max": 0}
    assert beijing["buildings"] == ["BUILDING_MONUMENT", "BUILDING_PYRAMIDS"]
    assert beijing["wonders"] == ["BUILDING_PYRAMIDS"]
    assert beijing["enemies_near"] == 3 and beijing["threatened"] is True
    assert xian["garrison"] == "UNIT_ARCHER"
    assert xian["defense"]["garrison_hp"] == 160 and xian["damaged"] is True


def test_a_threatened_city_lists_enemies_defenders_incoming_and_prices():
    s = snapshot(*runtime())
    beijing = s["cities"][0]
    kinds = [(e["type"], e["kind"], e["dist"], e["hp"]) for e in beijing["enemies"]]
    assert kinds == [("UNIT_SPEARMAN", "melee", 1, 31), ("UNIT_WARRIOR", "melee", 1, 100),
                     ("UNIT_CATAPULT", "siege", 2, 100)], "the peaceful scout is no enemy"
    assert beijing["capture_adjacent"] == 2
    assert beijing["incoming"] == 18 + 15 + 40 and beijing["incoming_from"] == "simulated"
    assert beijing["can_strike"] is False
    assert [d["type"] for d in beijing["defenders"]] == ["UNIT_WARRIOR"]
    assert beijing["defenders"][0] | {"id": 0} == {"id": 0, "type": "UNIT_WARRIOR", "kind": "melee", "x": 21, "y": 22,
                                                   "dist": 2, "hp": 50, "moves": 1, "attacks": 1, "range": 0}
    assert beijing["defence_prices"] == [
        {"unit": "UNIT_WARRIOR", "gold": 160, "gold_allowed": True, "faith": 80, "faith_allowed": True},
        {"unit": "UNIT_ARCHER", "gold": 240, "gold_allowed": True, "faith": 120, "faith_allowed": True}]
    xian = s["cities"][1]
    assert xian["capture_adjacent"] == 0 and xian["enemies"] == []
    assert all(not p["gold_allowed"] and not p["faith_allowed"] for p in xian["defence_prices"]), "stacking"


@pytest.mark.parametrize("setup", ["MOCK.simulate_fails = true", "MOCK.simulate_zero = true"])
def test_without_a_combat_preview_incoming_uses_the_damage_formula(setup):
    """No preview, or a preview of 0 (seen live at T129 for a Catapult 4 tiles away): the formula."""
    s = snapshot(*runtime(), setup)
    beijing = s["cities"][0]
    assert beijing["incoming_from"] == "formula"
    import math
    want = sum(24 * math.exp(0.04 * (strength - 28)) for strength in (25, 20, 35))
    assert beijing["incoming"] == round(want)


def test_religion_and_every_blocker_are_read():
    s = snapshot(*runtime())
    assert s["religion"] == {"pantheon": None, "can_create_pantheon": True, "pantheon_cost": 25, "religion": None,
                             "religions_founded": 1, "religions_max": 4, "prophet_points": 31, "prophet_cost": 60}
    assert s["blockers_all"] == ["ENDTURN_BLOCKING_COMMEMORATION_AVAILABLE", "ENDTURN_BLOCKING_UNITS"]
    assert s["blocker"] == "ENDTURN_BLOCKING_COMMEMORATION_AVAILABLE"


def test_a_failing_new_field_is_left_out_and_the_snapshot_still_answers():
    s = snapshot(*runtime(), "MOCK.religion_fails = true; CityManager.GetCommandTargets = nil")
    assert s["ok"] is True and "religion" not in s
    assert "can_strike" not in s["cities"][0] and "enemies" in s["cities"][0]
