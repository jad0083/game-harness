"""corpora/civ6/lua/harness.lua run outside the game: LuaJIT (lupa) with the stand-ins of
tests/fixtures/civ6_lua_mock.lua. It proves syntax and control flow of the snapshot's defence,
religion and blocker fields (docs/design/2026-09-27-civ6-levers-design.md, ruling 11) and of the
last stand's calls (rulings 22-27); API names
and results are checked live (games/civ6-kublai/journal.md). Skipped when lupa is not installed:
`scripts/civ6-lua-check.sh` runs them with lupa from a cache folder of its own."""

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
    """No preview, or a preview of 0 with no walls standing: the formula."""
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


def test_a_zero_preview_stands_while_walls_do():
    """Live T134, Xi'an with walls 100: the preview gives the garrison's share, 0 or 1."""
    s = snapshot(*runtime(), "MOCK.simulate_zero = true; MOCK.walls = 100")
    beijing = s["cities"][0]
    assert beijing["defense"]["walls_hp"] == 100
    assert (beijing["incoming"], beijing["incoming_from"]) == (0, "simulated")


# ---- the last stand (docs/design/2026-09-27-civ6-levers-design.md, rulings 22-27) ----------------

def call(rt, out, lua: str) -> dict:
    out.clear()
    rt.execute(f"Harness.run({lua})")
    assert len(out) == 1, out
    return json.loads(out[0])


def requests(rt) -> list[str]:
    return list(rt.eval("REQUESTS").values())


def stand_world(extra: str = ""):
    """Beijing (22,21): barbarian Spearman (31 HP) and Warrior next to it, a Catapult 2 tiles out, a
    peaceful Scout 3 tiles out; our Archer (range 2) next to the city."""
    rt, out = runtime()
    rt.execute("unit { id = 20, owner = 0, utype = 'UNIT_ARCHER', x = 22, y = 22, range = 2 }\n" + extra)
    return rt, out


def test_turn_ready_names_every_reason_it_is_not():
    rt, out = runtime()
    assert call(rt, out, "Harness.turn_ready") == {"ok": True, "ready": True, "why": [], "turn": 61}
    rt.execute("MOCK.autoplay = true; MOCK.popup = 'TechCivicCompletedPopup'; MOCK.not_our_turn = true")
    r = call(rt, out, "Harness.turn_ready")
    assert r["ready"] is False
    assert r["why"] == ["autoplay active", "not our turn", "on screen: TechCivicCompletedPopup"]
    rt.execute("MOCK.autoplay = false; MOCK.popup = nil; MOCK.not_our_turn = false; UI.HasSentTurnComplete = nil")
    assert call(rt, out, "Harness.turn_ready")["why"] == ["cannot check: turn already sent"], "fails closed"


def test_ls_state_lists_every_unit_near_the_city_with_its_damage():
    rt, out = stand_world()
    r = call(rt, out, "Harness.ls_state, 65536")
    units = {(u["owner"], u["id"]): u for u in r["units"]}
    assert set(units) == {(63, 1), (63, 2), (4, 3), (63, 4), (0, 11), (0, 12), (0, 20)}, "Xi'an's Archer is far"
    assert units[(63, 1)] == {"id": 1, "owner": 63, "x": 23, "y": 21, "damage": 69, "moves": 2, "attacks": 1}
    assert (r["turn"], r["me"]) == (61, 0)
    assert call(rt, out, "Harness.ls_state, 999")["error"] == "no city of ours with ID 999"


def test_a_ranged_unit_takes_the_sure_kill_on_a_capturer_first():
    rt, out = stand_world("MOCK.preview[20] = 40")
    r = call(rt, out, "Harness.last_stand_step, 65536, {}, {}")
    assert (r["action"], r["actor"], r["target"]["id"], r["predicted_kill"]) == ("ranged_attack", "unit:20", 1, True)
    assert requests(rt) == ["unit 20 RANGE_ATTACK 23,21"]
    # authoritative damage: the Spearman has healed to 90 HP, no kill; the adjacent capturers still come first
    rt.execute("REQUESTS = {}")
    r = call(rt, out, 'Harness.last_stand_step, 65536, {["63:1"] = 10}, {}')
    assert (r["target"]["id"], r["target"]["hp"], r["predicted_kill"]) == (1, 90, False)


def test_a_shooter_used_this_turn_is_skipped_and_the_stand_ends():
    rt, out = stand_world()
    r = call(rt, out, 'Harness.last_stand_step, 65536, {}, {["unit:20"] = true}')
    assert r == {"ok": True, "done": True, "reason": "nothing left to do"}
    assert requests(rt) == []


def test_targets_missing_from_the_games_list_are_still_found():
    """GetOperationTargets can miss valid targets (civ6-mcp): hostiles within range count too."""
    rt, out = stand_world("MOCK.op_targets = { [20] = {} }")
    assert call(rt, out, "Harness.last_stand_step, 65536, {}, {}")["action"] == "ranged_attack"


def test_the_city_strikes_first_once_walls_stand():
    rt, out = stand_world("MOCK.walls = 100; MOCK.strike = { {23, 21}, {23, 22}, {24, 21} }; MOCK.preview.city = 25")
    r = call(rt, out, "Harness.last_stand_step, 65536, {}, {}")
    assert (r["action"], r["actor"], r["target"]["id"], r["predicted_damage"]) == ("city_strike", "city:65536", 1, 25)
    assert requests(rt) == ["city 23,21"]
    rt.execute("MOCK.walls = 0; REQUESTS = {}")
    assert call(rt, out, "Harness.last_stand_step, 65536, {}, {}")["action"] == "ranged_attack", "no walls: no strike"


def test_only_hostile_units_are_targets_two_ways():
    """A barbarian or a player at war with us, and IsAttackChangeWarState empty; never a civilian."""
    # at war with player 4, but attacking would still change a war state: not a target
    rt, out = stand_world("UNITS = {}; unit { id = 20, owner = 0, utype = 'UNIT_ARCHER', x = 22, y = 22, range = 2 }\n"
                          "unit { id = 3, owner = 4, utype = 'UNIT_WARRIOR', x = 23, y = 21 }\n"
                          "MOCK.wars[4] = true; MOCK.war_state = { 4 }")
    assert call(rt, out, "Harness.last_stand_step, 65536, {}, {}")["reason"] == "nothing left to do"
    # not at war: never an enemy, whatever the war-state check says
    rt.execute("MOCK.wars[4] = false; MOCK.war_state = {}")
    assert call(rt, out, "Harness.last_stand_step, 65536, {}, {}")["reason"] == "no hostile unit within 3 tiles"
    # at war and no war-state change: a target; its Settler next to it never is
    rt.execute("MOCK.wars[4] = true; UNITS[2].utype = 'UNIT_SETTLER'")
    assert call(rt, out, "Harness.last_stand_step, 65536, {}, {}")["reason"] == "no hostile unit within 3 tiles"
    rt.execute("UNITS[2].utype = 'UNIT_WARRIOR'")
    r = call(rt, out, "Harness.last_stand_step, 65536, {}, {}")
    assert (r["action"], r["target"]["owner"]) == ("ranged_attack", 4)
    assert requests(rt) == ["unit 20 RANGE_ATTACK 23,21"]


def test_hidden_plots_are_out_of_reach():
    rt, out = stand_world("MOCK.hidden = { ['23,21'] = true, ['23,22'] = true, ['24,21'] = true }")
    assert call(rt, out, "Harness.last_stand_step, 65536, {}, {}")["done"] is True


def test_a_hurt_unit_next_to_a_capturer_retreats_but_never_the_garrison():
    rt, out = stand_world("UNITS = {}\n"
                          "unit { id = 2, owner = BARB, utype = 'UNIT_WARRIOR', x = 23, y = 22 }\n"
                          "unit { id = 11, owner = 0, utype = 'UNIT_WARRIOR', x = 22, y = 22, dmg = 70 }\n"
                          "unit { id = 13, owner = 0, utype = 'UNIT_WARRIOR', x = 22, y = 21, dmg = 80 }")
    r = call(rt, out, "Harness.last_stand_step, 65536, {}, {}")
    assert (r["action"], r["actor"], r["hp"]) == ("retreat", "unit:11", 30)
    assert r["to"] != {"x": 22, "y": 21}, "the city tile holds the garrison"
    d = rt.eval(f"Map.GetPlotDistance(23, 22, {r['to']['x']}, {r['to']['y']})")
    assert d >= 2, "never next to a hostile"
    assert requests(rt) == [f"unit 11 MOVE_TO {r['to']['x']},{r['to']['y']} mod=0"]
    r = call(rt, out, 'Harness.last_stand_step, 65536, {}, {["unit:11"] = true}')
    assert r["reason"] == "nothing left to do", "the hurt garrison (unit 13) stays"


def test_a_step_is_refused_when_the_game_is_not_ready():
    rt, out = stand_world("MOCK.popup = 'DiplomacyActionView'")
    r = call(rt, out, "Harness.last_stand_step, 65536, {}, {}")
    assert r == {"ok": False, "error": "not ready: on screen: DiplomacyActionView"}
    assert requests(rt) == []


def test_finish_moves_pins_our_unit():
    rt, out = stand_world()
    assert call(rt, out, "Harness.finish_moves, 20") == {"ok": True, "unit": 20, "moves_before": 2, "moves": 0}
    assert call(rt, out, "Harness.finish_moves, 1")["error"] == "no unit of ours with ID 1"


# ---- the AI's intent (ruling 29) --------------------------------------------------------------------

def test_each_city_lists_the_ais_top_three_builds():
    s = snapshot(*runtime())
    beijing, xian = s["cities"]
    assert beijing["recommend"] == [{"type": "DISTRICT_HOLY_SITE", "score": 729}, {"type": "BUILDING_GRANARY", "score": 669},
                                    {"type": "UNIT_ARCHER", "score": 632}]
    assert xian["recommend"] == []
    s = snapshot(*runtime(), "MOCK.no_city_ai = true")
    assert s["ok"] is True and "recommend" not in s["cities"][0]
