"""corpora/civ6/lua/harness.lua run outside the game: LuaJIT (lupa) with the stand-ins of
tests/fixtures/civ6_lua_mock.lua. It proves syntax and control flow of the snapshot's defence,
religion and blocker fields (docs/design/2026-09-27-civ6-levers-design.md, ruling 11) and of the
last stand's calls (rulings 22-27) and of the diplomacy auto-reply; API names and results are checked
live (games/civ6-kublai/journal.md). Skipped when lupa is not installed:
`scripts/civ6-lua-check.sh` runs them with lupa from a cache folder of its own, as a stage of
`scripts/ci.sh`."""

import json

import pytest

from pilot.config import REPO

lupa = pytest.importorskip("lupa")

HARNESS = (REPO / "corpora/civ6/lua/harness.lua").read_text(encoding="utf-8")
MOCK = (REPO / "tests/fixtures/civ6_lua_mock.lua").read_text(encoding="utf-8")
DIPLO_DATA = (REPO / "tests/fixtures/civ6_diplomacy_data.lua").read_text(encoding="utf-8")


def install(rt, version: str = "test", state: str = "InGame") -> None:
    """The chunk the controller sends: the version and the Lua state it installs into, then the file."""
    rt.execute(f'local HARNESS_VERSION = "{version}" local HARNESS_STATE = "{state}"\n' + HARNESS)


def bare_runtime():
    """The mock game with no library installed yet."""
    try:
        from lupa.lua51 import LuaRuntime  # the game's Lua is 5.1
    except ImportError:
        from lupa import LuaRuntime
    rt = LuaRuntime(unpack_returned_tuples=True)
    out: list[str] = []
    rt.globals().print = lambda *a: out.append(" ".join(str(x) for x in a))
    rt.execute(DIPLO_DATA)
    rt.execute(MOCK)
    return rt, out


def runtime(state: str = "InGame"):
    rt, out = bare_runtime()
    install(rt, state=state)
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
        {"unit": "UNIT_ARCHER", "gold": 240, "gold_allowed": True, "faith": 120, "faith_allowed": True},
        {"unit": "UNIT_SPEARMAN", "gold": 260, "gold_allowed": True, "faith": 130, "faith_allowed": True}], \
        "the two cheapest allowed, the best ranged and the best anti-cavalry unit"
    xian = s["cities"][1]
    assert xian["capture_adjacent"] == 0 and xian["enemies"] == []
    assert xian["defence_prices"] == [{"unit": "UNIT_ARCHER", "gold": 240, "gold_allowed": False, "gold_why": "stacking",
                                       "faith": 120, "faith_allowed": False, "faith_why": "stacking"}], \
        "nothing allowed (an Archer on the tile): the best ranged unit, with why"


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


def test_a_unit_in_another_players_district_is_never_a_target():
    """Ruling 23 leaves attacks on cities and districts out: a City Center or an Encampment takes the
    hit for the unit standing in it, so the read-back would show no damage on the unit. A plot with a
    district that is not ours is never a target (a unit standing in our own district still is)."""
    world = ("UNITS = {}; unit { id = 20, owner = 0, utype = 'UNIT_ARCHER', x = 22, y = 22, range = 2 }\n"
             "unit { id = 5, owner = 4, utype = 'UNIT_WARRIOR', x = 23, y = 21 }\n"
             "MOCK.wars[4] = true; MOCK.walls = 100; MOCK.strike = { {23, 21} }\n")
    for district in ("DISTRICT_ENCAMPMENT", "DISTRICT_CITY_CENTER", "DISTRICT_CAMPUS"):
        rt, out = stand_world(world + f"MOCK.districts = {{ ['23,21'] = {{ d = '{district}', owner = 4 }} }}")
        r = call(rt, out, "Harness.last_stand_step, 65536, {}, {}")
        assert r == {"ok": True, "done": True, "reason": "nothing left to do"}, district
        assert requests(rt) == [], district
    rt, out = stand_world(world + "MOCK.districts = { ['23,21'] = { d = 'DISTRICT_CAMPUS', owner = 0 } }")
    assert call(rt, out, "Harness.last_stand_step, 65536, {}, {}")["action"] == "city_strike", "our own district"
    rt, out = stand_world(world)
    assert call(rt, out, "Harness.last_stand_step, 65536, {}, {}")["action"] == "city_strike"


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


# ---- district placement, read-only (ruling 30, stage A) -------------------------------------------

def test_district_plots_list_where_each_district_may_go_with_the_plot_facts():
    rt, out = runtime()
    rt.execute("MOCK.map = { ['22,20'] = { t = 'TERRAIN_GRASS_HILLS', f = 'FEATURE_FOREST' },"
               " ['23,20'] = { t = 'TERRAIN_GRASS_MOUNTAIN' }, ['21,20'] = { r = 'RESOURCE_IRON', i = 'IMPROVEMENT_MINE' },"
               " ['24,22'] = { river = true } }\n"
               "MOCK.district_plots = { DISTRICT_CAMPUS = { {22, 20}, {24, 22} } }")
    r = call(rt, out, "Harness.district_plots, 65536")
    assert (r["turn"], r["player"], len(r["cities"])) == (61, 0, 1)
    beijing = r["cities"][0]
    assert (beijing["name"], beijing["x"], beijing["y"]) == ("Beijing", 22, 21)
    assert beijing["placed"] == [{"type": "DISTRICT_CITY_CENTER", "x": 22, "y": 21, "complete": True}]
    campus = next(c for c in beijing["candidates"] if c["type"] == "DISTRICT_CAMPUS")
    idx = lambda x, y: str(y * 40 + x)      # the mock's plot index
    assert campus["plots"] == [int(idx(22, 20)), int(idx(24, 22))]
    plots = r["plots"]
    hill = plots[idx(22, 20)]
    assert (hill["t"], hill["f"]) == ("GRASS_HILLS", "FOREST")
    assert len(hill["adj"]) == 6 and int(idx(23, 20)) in hill["adj"] and int(idx(22, 21)) in hill["adj"]
    assert plots[idx(23, 20)]["t"] == "GRASS_MOUNTAIN" and plots[idx(23, 20)]["mountain"] is True
    assert (plots[idx(21, 20)]["r"], plots[idx(21, 20)]["i"]) == ("IRON", "MINE")
    assert plots[idx(22, 21)]["d"] == "CITY_CENTER" and plots[idx(24, 22)]["river"] is True
    assert len(plots) >= 61, "3 tiles around the city and their neighbours"
    assert len(beijing["near"]) == 37 and int(idx(22, 21)) in beijing["near"]
    assert requests(rt) == [], "read-only"
    assert r["built"] == ["PYRAMIDS"], "our built wonders"
    everyone = call(rt, out, "Harness.district_plots")
    assert [c["name"] for c in everyone["cities"]] == ["Beijing", "Xi'an"]


def test_a_retreat_stays_within_reach_of_the_read_back():
    """Review fix: a hurt unit 3 tiles out never retreats to a plot the GameCore read-back cannot see."""
    rt, out = stand_world("UNITS = {}\n"
                          "unit { id = 2, owner = BARB, utype = 'UNIT_WARRIOR', x = 24, y = 21 }\n"
                          "unit { id = 11, owner = 0, utype = 'UNIT_WARRIOR', x = 25, y = 21, dmg = 70 }")
    assert rt.eval("Map.GetPlotDistance(22, 21, 25, 21)") == 3
    far = rt.eval("(function() local n = 0 for _, i in ipairs(UnitManager.GetReachableMovement(UNITS[2])) do "
                  "local p = Map.GetPlotByIndex(i) if Map.GetPlotDistance(22, 21, p:GetX(), p:GetY()) > 3 then n = n + 1 end "
                  "end return n end)()")
    assert far >= 1, "some reachable plots lie 4 tiles out"
    r = call(rt, out, "Harness.last_stand_step, 65536, {}, {}")
    assert r == {"ok": True, "done": True, "reason": "nothing left to do"}, "every free plot within 3 is next to it"
    assert requests(rt) == []


# ---- the diplomacy auto-reply (issues.md T240, T342) ----------------------------------------------
# An AI leader's statement opens DiplomacyActionView, which locks the engine until a human answers.
# popups.toml removes the view's handler; the library's own handler answers while autoplay runs.

AUSTRALIA = 3


def diplo_calls(rt) -> list[str]:
    return list(rt.eval("DIPLO_CALLS").values())


def diplo_log(rt, out) -> list[dict]:
    s = snapshot(rt, out)
    assert s["ok"] is True, s.get("error")
    return s["diplomacy"]["log"]


def game_rows(rt, table: str) -> list[dict]:
    rows = rt.eval(f"(function() local out = {{}} for r in GameInfo.{table}() do out[#out + 1] = r end return out end)()")
    return [dict(r.items()) for r in rows.values()]


def autoplaying(extra: str = ""):
    rt, out = runtime()
    rt.execute("MOCK.autoplay = true; MOCK.civs = { [3] = 'CIVILIZATION_AUSTRALIA' }\n" + extra)
    return rt, out


def test_t240_the_troop_warning_gets_merely_passing_by_then_goodbye():
    """T240: "the mustering of your forces along our borders" offers "My troops are merely passing
    by." (POSITIVE) and "You were right to worry (Declare War)!" (NEGATIVE); "Thank you." follows."""
    rt, out = autoplaying()
    rt.execute("statement(3, 0, 'WARNING_TOO_MANY_TROOPS_NEAR_ME', 'NONE', 7)")
    assert diplo_calls(rt) == ["response 7 0 POSITIVE"]
    rt.execute("statement(3, 0, 'WARNING_TOO_MANY_TROOPS_NEAR_ME', 'POSITIVE', 7)")
    assert diplo_calls(rt) == ["response 7 0 POSITIVE", "close 7"]
    log = diplo_log(rt, out)
    assert [(e["kind"], e["sub"], e["reply"], e["why"]) for e in log] == [
        ("WARNING_TOO_MANY_TROOPS_NEAR_ME", "NONE", "POSITIVE", "table"),
        ("WARNING_TOO_MANY_TROOPS_NEAR_ME", "POSITIVE", "EXIT", "follow-up")]
    assert log[0] | {"n": 0} == {"n": 0, "turn": 61, "at": 61, "from": AUSTRALIA, "civ": "CIVILIZATION_AUSTRALIA",
                                  "session": 7, "kind": "WARNING_TOO_MANY_TROOPS_NEAR_ME", "sub": "NONE",
                                  "reply": "POSITIVE", "why": "table"}
    assert log[1]["n"] == log[0]["n"] + 1


def test_t342_a_statement_with_only_goodbye_is_closed():
    """T342: an agenda warning ("Aspire to be a worthier example ...") offers only Goodbye."""
    rt, out = autoplaying()
    rt.execute("statement(3, 0, 'DIPLOMATIC_HIDDEN_AGENDA_WARNING', 'NONE', 9)")
    assert diplo_calls(rt) == ["close 9"]
    assert [(e["kind"], e["reply"], e["why"]) for e in diplo_log(rt, out)] == [
        ("DIPLOMATIC_HIDDEN_AGENDA_WARNING", "EXIT", "table")]


def test_every_statement_the_ai_starts_has_an_explicit_reply_and_none_declares_war():
    """For every statement the AI can start (the game's data), the reply is one the game offers for it
    (or a deal's refusal, or Goodbye) and never one that carries a diplomatic action: no war, no
    permanent refusal, no statement or session of our own, no deal sent. The only positive answers
    are the five promises; follow-ups (every other subtype) get Goodbye, the only choice they offer."""
    rt, _ = runtime()
    statements = [r for r in game_rows(rt, "DiplomacyStatements") if r.get("Initiator") == "AI"]
    selections = game_rows(rt, "DiplomacySelections")
    offered = {}
    for r in selections:
        offered.setdefault(r["Type"], {})[r["Key"]] = r.get("DiplomaticActionType")
    kinds = sorted({r["Type"] for r in statements if r["SubType"] == "NONE"})
    table = dict(rt.eval("Harness.DIPLOMACY").items())
    assert sorted(table) == kinds, "an explicit reply for every statement the AI can start, and no other"
    assert offered["WARNING_TOO_MANY_TROOPS_NEAR_ME_FROM_AI"]["CHOICE_NEGATIVE"] == "DIPLOACTION_DECLARE_SURPRISE_WAR"
    positive = []
    for n, r in enumerate(statements):
        rt, _ = autoplaying()
        sid = 100 + n
        rt.execute(f"statement(3, 0, '{r['Type']}', '{r['SubType']}', {sid})")
        calls = diplo_calls(rt)
        assert len(calls) == 1, (r, calls)
        verb, *rest = calls[0].split(" ")
        assert verb in ("response", "close"), (r, calls)
        sel = offered.get(r.get("Selections") or "", {})
        if r["SubType"] != "NONE":
            assert list(sel) == ["CHOICE_EXIT"] and calls == [f"close {sid}"], (r, calls)
            continue
        if verb == "close":
            assert rest == [str(sid)]
            continue
        assert rest[:2] == [str(sid), "0"], "our player, explicitly"
        key = "CHOICE_" + rest[2]
        if not sel:                                  # a deal or demand: the deal view's refusal
            assert r["Type"] in ("MAKE_DEAL", "MAKE_DEMAND") and rest[2] == "NEGATIVE", (r, calls)
            continue
        assert key in sel, (r, key)
        assert sel[key] is None, f"{r['Type']}: {key} carries {sel[key]}"
        assert rest[2] == "POSITIVE", (r, calls)
        positive.append(r["Type"])
    assert sorted(positive) == ["WARNING_DONT_SETTLE_NEAR_ME", "WARNING_STOP_CONVERTING_MY_CITIES",
                                "WARNING_STOP_DIGGING_UP_ARTIFACTS", "WARNING_STOP_SPYING_ON_ME",
                                "WARNING_TOO_MANY_TROOPS_NEAR_ME"]


def test_proposals_get_goodbye_and_deals_are_refused():
    """Friendship, delegations, embassies, open borders, alliances and peace are left with Goodbye (no
    safe accept rule is proven); a deal or a demand is refused as the deal view refuses one."""
    rt, out = autoplaying()
    for sid, kind in enumerate(("DECLARE_FRIEND", "DIPLOMATIC_DELEGATION", "RESIDENT_EMBASSY", "OPEN_BORDERS",
                                "MAKE_ALLIANCE", "RENEW_ALLIANCE", "MAKE_PEACE", "FIRST_MEET_NO_MANS_INFO_EXCHANGE"), 1):
        rt.execute(f"statement(3, 0, '{kind}', 'NONE', {sid})")
        assert diplo_calls(rt)[-1] == f"close {sid}", kind
    rt.execute("DIPLO_CALLS = {} statement(3, 0, 'MAKE_DEAL', 'NONE', 20) statement(3, 0, 'MAKE_DEMAND', 'NONE', 21)")
    assert diplo_calls(rt) == ["response 20 0 NEGATIVE", "response 21 0 NEGATIVE"]
    assert [e["reply"] for e in diplo_log(rt, out)][-2:] == ["REFUSE", "REFUSE"]


def test_a_second_statement_in_an_answered_session_gets_goodbye():
    """An AI answering our refusal with another offer (or any follow-up whose subtype reads NONE)."""
    rt, out = autoplaying()
    rt.execute("statement(3, 0, 'MAKE_DEAL', 'NONE', 5) statement(3, 0, 'MAKE_DEAL', 'NONE', 5)")
    assert diplo_calls(rt) == ["response 5 0 NEGATIVE", "close 5"]
    assert diplo_log(rt, out)[-1]["why"] == "follow-up"


def test_an_unknown_statement_kind_gets_goodbye_never_a_positive_answer():
    rt, out = autoplaying()
    rt.execute("statement(3, 0, 'PROPOSE_SOMETHING_NEW', 'NONE', 4)")
    assert diplo_calls(rt) == ["close 4"]
    assert [(e["kind"], e["reply"], e["why"]) for e in diplo_log(rt, out)] == [("PROPOSE_SOMETHING_NEW", "EXIT", "unknown")]


def test_a_reply_the_game_does_not_offer_safely_falls_back_to_goodbye():
    """The live data decides: a promise whose choice carries a diplomatic action (a patch or a mod), or
    data that cannot be read, gets Goodbye instead."""
    rt, out = autoplaying("for r in GameInfo.DiplomacySelections() do if r.Type == 'WARNING_STOP_SPYING_ON_ME_FROM_AI' "
                          "and r.Key == 'CHOICE_POSITIVE' then r.DiplomaticActionType = 'DIPLOACTION_DECLARE_SURPRISE_WAR' end end")
    rt.execute("statement(3, 0, 'WARNING_STOP_SPYING_ON_ME', 'NONE', 3)")
    assert diplo_calls(rt) == ["close 3"]
    assert diplo_log(rt, out)[-1]["why"] == "guard"
    rt.execute("GameInfo.DiplomacySelections = nil statement(3, 0, 'WARNING_TOO_MANY_TROOPS_NEAR_ME', 'NONE', 8)")
    assert diplo_calls(rt) == ["close 3", "close 8"], "fails closed"


def test_statements_to_other_players_or_from_us_are_left_alone():
    rt, out = autoplaying()
    rt.execute("statement(3, 4, 'WARNING_TOO_MANY_TROOPS_NEAR_ME', 'NONE', 2) statement(0, 3, 'DENOUNCE', 'NONE', 6)")
    assert diplo_calls(rt) == []
    assert diplo_log(rt, out) == []


def test_outside_autoplay_a_statement_waits_and_is_answered_when_autoplay_starts():
    """The view no longer shows it, so it waits (listed in the snapshot) until our next autoplay."""
    rt, out = runtime()
    rt.execute("statement(3, 0, 'WARNING_TOO_MANY_TROOPS_NEAR_ME', 'NONE', 7) statement(3, 0, 'DENOUNCE', 'NONE', 8)")
    assert diplo_calls(rt) == []
    log = diplo_log(rt, out)
    assert [(e["why"], "reply" in e) for e in log] == [("waiting", False), ("waiting", False)]
    rt.execute("MOCK.open[8] = nil")                  # closed by the game meanwhile
    r = call(rt, out, "Harness.autoplay, 1")
    assert r["active"] is True
    assert diplo_calls(rt) == ["response 7 0 POSITIVE"]
    log = diplo_log(rt, out)
    assert [(e.get("reply"), e["why"], e.get("late")) for e in log] == [
        ("POSITIVE", "table", True), (None, "gone", None)]
    rt.execute("statement(3, 0, 'WARNING_TOO_MANY_TROOPS_NEAR_ME', 'POSITIVE', 7)")
    assert diplo_calls(rt)[-1] == "close 7"


def test_an_answered_session_left_open_is_closed_when_autoplay_next_starts():
    """No follow-up came (the session would stay open with no view to close it). That Goodbye is an
    answer too: it is logged (why 'sweep') for the governor and the briefing."""
    rt, out = autoplaying()
    rt.execute("statement(3, 0, 'MAKE_DEAL', 'NONE', 5)")
    call(rt, out, "Harness.autoplay, 1")
    assert diplo_calls(rt) == ["response 5 0 NEGATIVE", "close 5"]
    call(rt, out, "Harness.autoplay, 1")
    assert diplo_calls(rt) == ["response 5 0 NEGATIVE", "close 5"], "closed once"
    log = diplo_log(rt, out)
    assert [(e["kind"], e["reply"], e["why"], e["session"]) for e in log] == [
        ("MAKE_DEAL", "REFUSE", "table", 5), ("MAKE_DEAL", "EXIT", "sweep", 5)]
    assert log[1] | {"n": 0} == {"n": 0, "turn": 61, "at": 61, "from": AUSTRALIA, "civ": "CIVILIZATION_AUSTRALIA",
                                  "session": 5, "kind": "MAKE_DEAL", "sub": "NONE", "reply": "EXIT", "why": "sweep"}
    assert log[1]["n"] == log[0]["n"] + 1


def test_a_follow_up_that_comes_after_the_hand_back_is_answered_when_autoplay_starts():
    """T240's "Thank you." arriving once autoplay has handed back: it waits, and the next start answers
    it as a follow-up (Goodbye), not as a session closed before an answer."""
    rt, out = autoplaying()
    rt.execute("statement(3, 0, 'WARNING_TOO_MANY_TROOPS_NEAR_ME', 'NONE', 7)")
    rt.execute("MOCK.autoplay = false statement(3, 0, 'WARNING_TOO_MANY_TROOPS_NEAR_ME', 'POSITIVE', 7)")
    assert diplo_calls(rt) == ["response 7 0 POSITIVE"]
    call(rt, out, "Harness.autoplay, 1")
    assert diplo_calls(rt) == ["response 7 0 POSITIVE", "close 7"]
    log = diplo_log(rt, out)
    assert [(e["sub"], e.get("reply"), e["why"], e.get("late")) for e in log] == [
        ("NONE", "POSITIVE", "table", None), ("POSITIVE", "EXIT", "follow-up", True)]


def test_a_sweep_goodbye_that_fails_is_logged_once_and_retried():
    rt, out = autoplaying()
    rt.execute("statement(3, 0, 'MAKE_DEAL', 'NONE', 5) MOCK.dipl_fails = 'close'")
    call(rt, out, "Harness.autoplay, 1")
    call(rt, out, "Harness.autoplay, 1")
    sweeps = [e for e in diplo_log(rt, out) if e["why"] == "sweep"]
    assert len(sweeps) == 1 and "the session is gone" in sweeps[0]["err"]
    rt.execute("MOCK.dipl_fails = false")
    call(rt, out, "Harness.autoplay, 1")
    assert diplo_calls(rt) == ["response 5 0 NEGATIVE", "close 5"]
    sweeps = [e for e in diplo_log(rt, out) if e["why"] == "sweep"]
    assert len(sweeps) == 1 and "err" not in sweeps[0], "the same entry, now without the error"


def test_a_failing_game_call_is_recorded_and_never_raised():
    rt, out = autoplaying("MOCK.dipl_fails = true")
    rt.execute("statement(3, 0, 'DENOUNCE', 'NONE', 4)")
    e = diplo_log(rt, out)[-1]
    assert e["reply"] == "EXIT" and "the session is gone" in e["err"]


def test_the_log_keeps_the_last_twenty():
    rt, out = autoplaying()
    rt.execute("for i = 1, 25 do statement(3, 0, 'DENOUNCE', 'NONE', i) end")
    log = diplo_log(rt, out)
    assert len(log) == 20 and log[-1]["session"] == 25 and log[0]["session"] == 6
    assert log[-1]["n"] - log[0]["n"] == 19


def test_a_reinstall_replaces_the_handler_and_keeps_the_log():
    rt, out = autoplaying()
    rt.execute("statement(3, 0, 'DENOUNCE', 'NONE', 1)")
    install(rt, version="next")
    assert rt.eval("#Events.DiplomacyStatement.fns") == 1, "the old handler is removed first"
    rt.execute("statement(3, 0, 'DENOUNCE', 'NONE', 2)")
    assert diplo_calls(rt) == ["close 1", "close 2"], "answered once"
    assert [e["session"] for e in diplo_log(rt, out)] == [1, 2]
    install(rt, version="next")
    assert rt.eval("#Events.DiplomacyStatement.fns") == 1, "the same version is a no-op"


def test_a_stale_handler_left_registered_does_nothing():
    """Belt and braces: a handler of a replaced library that could not be removed stays silent."""
    rt, _ = autoplaying()
    rt.execute("OLD_FN = Events.DiplomacyStatement.fns[1]")
    install(rt, version="next")
    rt.execute("Events.DiplomacyStatement.Add(OLD_FN) statement(3, 0, 'DENOUNCE', 'NONE', 2)")
    assert diplo_calls(rt) == ["close 2"]


def test_the_handler_is_installed_in_ingame_only():
    """GameCore gets the library too (research and civics): no second handler there."""
    rt, out = runtime(state="GameCore")
    assert rt.eval("#Events.DiplomacyStatement.fns") == 0
    rt, out = runtime()
    assert rt.eval("#Events.DiplomacyStatement.fns") == 1
    assert snapshot(rt, out)["diplomacy"] == {"handler": True, "log": []}


def test_a_failed_answer_falls_back_to_goodbye():
    """AddResponse raising (a binding that rejects the session): Goodbye is sent at once instead, so
    no session is left open behind the quieted leader screen."""
    rt, out = autoplaying("MOCK.dipl_fails = 'response'")
    rt.execute("statement(3, 0, 'WARNING_TOO_MANY_TROOPS_NEAR_ME', 'NONE', 7)")
    assert diplo_calls(rt) == ["close 7"]
    assert rt.eval("MOCK.open[7]") is None
    e = diplo_log(rt, out)[-1]
    assert (e["reply"], e["closed"]) == ("POSITIVE", True) and "the session is gone" in e["err"]
    call(rt, out, "Harness.autoplay, 1")
    assert diplo_calls(rt) == ["close 7"], "closed once"


@pytest.mark.parametrize("kind", ["WARNING_TOO_MANY_TROOPS_NEAR_ME", "DENOUNCE"])
def test_a_session_whose_answer_failed_is_closed_when_autoplay_next_starts(kind):
    """Every call of the answer raised (the promise, its Goodbye fallback, or a plain Goodbye): the
    session stays listed as open, and the next autoplay start closes it."""
    rt, out = autoplaying("MOCK.dipl_fails = true")
    rt.execute(f"statement(3, 0, '{kind}', 'NONE', 7)")
    assert diplo_calls(rt) == [] and "the session is gone" in diplo_log(rt, out)[-1]["err"]
    rt.execute("MOCK.dipl_fails = false")
    call(rt, out, "Harness.autoplay, 1")
    assert diplo_calls(rt) == ["close 7"]
    assert rt.eval("MOCK.open[7]") is None


def test_a_statement_that_cannot_be_read_is_still_logged_and_closed():
    """A failure while reading the statement (GetKeyName raising) must not swallow it: it is logged
    with the error and gets Goodbye like an unknown kind."""
    rt, out = autoplaying("MOCK.keyname_fails = true")
    rt.execute("statement(3, 0, 'WARNING_TOO_MANY_TROOPS_NEAR_ME', 'NONE', 7)")
    assert diplo_calls(rt) == ["close 7"]
    e = diplo_log(rt, out)[-1]
    assert (e.get("kind"), e["session"], e["civ"], e["reply"], e["why"]) == (
        None, 7, "CIVILIZATION_AUSTRALIA", "EXIT", "unknown")
    assert "no such key" in e["err"]


def test_an_install_without_the_state_header_is_replaced_by_the_next_version():
    """A controller built before HARNESS_STATE sends the chunk without it: no handler. The rebuilt
    controller's version covers the header (civ6.rs INSTALL_HEADER), so it installs again, and that
    install registers the handler, which answers."""
    rt, out = bare_runtime()
    rt.execute('local HARNESS_VERSION = "text-only"\n' + HARNESS)
    assert rt.eval("#Events.DiplomacyStatement.fns") == 0
    assert snapshot(rt, out)["diplomacy"]["handler"] is False
    install(rt, version="with-header")
    assert rt.eval("#Events.DiplomacyStatement.fns") == 1
    rt.execute("MOCK.autoplay = true statement(3, 0, 'WARNING_TOO_MANY_TROOPS_NEAR_ME', 'NONE', 7)")
    assert diplo_calls(rt) == ["response 7 0 POSITIVE"]
    assert snapshot(rt, out)["diplomacy"]["handler"] is True


def test_a_statement_without_a_readable_session_is_not_left_waiting():
    """No SessionID in the event and FindOpenSessionID gives nothing, outside autoplay: there is no
    session to answer later, so it is logged as such instead of waiting forever."""
    rt, out = runtime()
    rt.execute("MOCK.autoplay = false; MOCK.civs = { [3] = 'CIVILIZATION_AUSTRALIA' }; MOCK.find_session = nil")
    rt.execute("statement(3, 0, 'DENOUNCE', 'NONE', nil)")
    assert diplo_log(rt, out)[-1]["why"] == "no session"
    rt.execute("MOCK.autoplay = true")
    call(rt, out, "Harness.autoplay, 1")
    assert [e["why"] for e in diplo_log(rt, out)] == ["no session"]


def test_a_sweep_retried_after_a_reinstall_is_still_one_entry():
    rt, out = autoplaying()
    rt.execute("statement(3, 0, 'MAKE_DEAL', 'NONE', 5) MOCK.dipl_fails = 'close'")
    call(rt, out, "Harness.autoplay, 1")
    install(rt, version="next")
    rt.execute("MOCK.dipl_fails = false")
    call(rt, out, "Harness.autoplay, 1")
    sweeps = [e for e in diplo_log(rt, out) if e["why"] == "sweep"]
    assert len(sweeps) == 1 and "err" not in sweeps[0], sweeps


# ---- postmortem-fixes design, rulings 1, 7 and 21: the snapshot fields ---------------------------

GUANGZHOU = """CITIES[#CITIES + 1] = new_city { id = 393216, name = 'Guangzhou', x = 10, y = 10,
  can_build = { 'UNIT_WARRIOR', 'UNIT_INFANTRY', 'UNIT_MACHINE_GUN', 'UNIT_MODERN_AT' }, buildings = {} }
MOCK.gold = 1630 MOCK.faith = 1961"""


def test_a_guangzhou_like_city_lists_what_it_can_buy_even_when_nothing_threatens_it():
    """Post-mortem H5: the list showed Infantry and Tank "not allowed now" for lack of Oil, never the
    buyable Modern AT (1,160) or Machine Gun (1,080). Every city now gets it, threatened or not."""
    s = snapshot(*runtime(), GUANGZHOU)
    gz = s["cities"][2]
    assert gz["threatened"] is False
    units = {p["unit"]: p for p in gz["defence_prices"]}
    assert units["UNIT_MODERN_AT"] | {} == {"unit": "UNIT_MODERN_AT", "gold": 1160, "gold_allowed": True,
                                             "faith": 580, "faith_allowed": True}
    assert units["UNIT_MACHINE_GUN"]["gold_allowed"] is True
    assert "UNIT_INFANTRY" not in units or units["UNIT_INFANTRY"].get("gold_why") == "game", \
        "Infantry (no Oil) is not what the city can buy"
    assert [p["unit"] for p in gz["defence_prices"]] == ["UNIT_WARRIOR", "UNIT_MACHINE_GUN", "UNIT_MODERN_AT"]


def test_a_refusal_names_the_balance_or_the_game():
    s = snapshot(*runtime(), GUANGZHOU + " MOCK.gold = 1100")
    at = {p["unit"]: p for p in s["cities"][2]["defence_prices"]}["UNIT_MODERN_AT"]
    assert (at["gold_allowed"], at["gold_why"], at["faith_allowed"]) == (False, "balance", True), \
        "still listed: the best anti-cavalry unit, allowed or not"


def test_the_snapshot_reads_alive_the_strategic_stock_and_alliances():
    s = snapshot(*runtime(), "MOCK.stock = { RESOURCE_IRON = 3 } MOCK.allies = { [2] = true }")
    assert s["alive"] is True
    assert s["resources"] == {"RESOURCE_IRON": 3, "RESOURCE_OIL": 0}, "strategic resources only"
    allied = {m["id"]: m.get("allied") for m in s["majors"]}
    assert allied[2] is True and allied[1] is False
    assert snapshot(*runtime(), "MOCK.dead = true")["alive"] is False, "false stays false"


def test_unreadable_new_fields_are_left_out_or_null():
    s = snapshot(*runtime(), "MOCK.alive_fails = true MOCK.stock_fails = true MOCK.alliance_fails = true")
    assert s["ok"] is True and s["alive"] is None and "resources" not in s
    assert all("allied" not in m for m in s["majors"]), "no field: the governor counts every major as not allied"


def test_the_library_as_sent_with_comment_lines_blanked_still_runs():
    """The controller blanks every full-line comment but the license notice (civ6.rs
    blank_comment_lines): the agent takes at most 64 KiB of code and the file is over that."""
    body = "".join("\n" if ln.lstrip().startswith("--") and "License" not in ln and "Copyright" not in ln else ln
                   for ln in HARNESS.splitlines(True))
    assert len(body) < 64 * 1024
    rt, out = bare_runtime()
    rt.execute('local HARNESS_VERSION = "sent" local HARNESS_STATE = "InGame"\n' + body)
    assert snapshot(rt, out)["ok"] is True


# ---- postmortem-fixes design, ruling 26: every class that can take a city ---------------------------

def test_a_giant_death_robot_next_to_the_city_counts_as_a_capturer_and_a_ranged_unit_does_not():
    """War-12: Guangzhou (T565) fell to a GDR next to it (Combat 130, RangedCombat 120) without the
    capture count seeing it: it read as ranged. A unit the game lets capture with a melee strength and a
    class other than ranged or siege counts; a Crossbowman (ranged, CanCapture too) does not."""
    setup = """UNITS = {}
unit { id = 30, owner = BARB, utype = 'UNIT_GIANT_DEATH_ROBOT', x = 23, y = 21 }
unit { id = 31, owner = BARB, utype = 'UNIT_CROSSBOWMAN', x = 23, y = 22, range = 2 }"""
    beijing = snapshot(*runtime(), setup)["cities"][0]
    assert beijing["capture_adjacent"] == 1, "the robot, not the crossbowman"
    kinds = {e["type"]: (e["kind"], e["capture"]) for e in beijing["enemies"]}
    assert kinds == {"UNIT_GIANT_DEATH_ROBOT": ("ranged", True), "UNIT_CROSSBOWMAN": ("ranged", False)}


def test_the_last_stand_shoots_a_giant_death_robot_next_to_the_city_before_a_weaker_crossbowman():
    """The stand's priority and retreat use the same test: a capturer next to the city comes first."""
    rt, out = stand_world("""UNITS = { UNITS[#UNITS] }
unit { id = 30, owner = BARB, utype = 'UNIT_GIANT_DEATH_ROBOT', x = 23, y = 21 }
unit { id = 31, owner = BARB, utype = 'UNIT_CROSSBOWMAN', x = 23, y = 22, dmg = 50, range = 2 }""")
    r = call(rt, out, "Harness.last_stand_step, 65536, {}, {}")
    assert (r["action"], r["actor"], r["target"]["id"]) == ("ranged_attack", "unit:20", 30)
