"""The Civilization VI governor loop against FakeCiv6 (ruling 4): decisions apply structured orders
and autoplay, orders are read back, urgent changes stop autoplay, invalid ids never reach the game,
purchases keep the reserve."""

import json
import shutil

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from pilot.civ6 import (
    Checked,
    Civ6Order,
    CorpusIndex,
    FakeCiv6,
    briefing_text,
    check_orders,
    held_outcome,
    metrics,
    order_record,
    order_record_text,
    order_window,
    purchase_cap,
    urgent_changes,
)
from pilot.civ6_governor import Civ6Governor
from pilot.config import REPO, Settings
from pilot.events import EventLog
from pilot.pillars import load_pillars

FIXTURE = json.loads((REPO / "crates/game-controller/tests/fixtures/civ6_snapshot.json").read_text(encoding="utf-8"))
INDEX = CorpusIndex.load(REPO / "corpora/civ6")
SPEC = load_pillars(REPO / "corpora/civ6")


def is_review(info: AgentInfo) -> bool:
    return "change" in info.output_tools[0].parameters_json_schema.get("properties", {})


def orders_model(*answers: list[dict], seen: list | None = None):
    """A model answering each decision with the next list of orders (the last repeats); strategy
    reviews answer 'no change'. `seen` collects every decision prompt."""
    calls = {"n": 0}

    def respond(messages, info: AgentInfo) -> ModelResponse:
        if is_review(info):
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,
                                                     {"change": False, "assessment": "n/a", "rules": []})])
        if seen is not None:
            seen.append("\n".join(str(getattr(p, "content", "")) for m in messages for p in getattr(m, "parts", [])))
        orders = answers[min(calls["n"], len(answers) - 1)]
        calls["n"] += 1
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"orders": orders, "reason": "test"})])

    return FunctionModel(respond)


@pytest.fixture
def setup(tmp_path):
    corpus = tmp_path / "civ6"
    corpus.mkdir()
    for f in ("manifest.toml", "pilot.md", "strategy.md", "pillars.toml"):
        shutil.copy(REPO / "corpora/civ6" / f, corpus / f)
    shutil.copytree(REPO / "corpora/civ6/data", corpus / "data")
    s = Settings(model="google:gemini-3.8-flash", runs_dir=tmp_path / "runs", journal=tmp_path / "journal.md",
                 commit_learnings=False, game="civ6", decide_every_turns=3, poll_s=0, retro_every=0,
                 ask_human_timeout_s=0.05, fallback_model=None, autoplay_chunk=1)
    s.__class__ = type("S", (Settings,), {"corpus_dir": property(lambda self: corpus)})
    return s, EventLog(s.runs_dir, "civ1", s.model)


def governor(setup, game, model) -> Civ6Governor:
    s, log = setup
    g = Civ6Governor(s, game, log, model=model)
    g.status_poll_s = 0
    g.start_grace_s = 0.05
    g.turn_deadline_s = 0.5
    g.recover_every_s = 0
    return g


def run_until_attention(g: Civ6Governor, limit_s: float = 5.0) -> None:
    """Run the governor until it waits for the human, then stop it (as the dashboard would)."""
    import threading
    import time
    t = threading.Thread(target=g.run, kwargs={"max_decisions": 2}, daemon=True)
    t.start()
    end = time.time() + limit_s
    while g.log.state.status != "needs_attention" and t.is_alive() and time.time() < end:
        time.sleep(0.01)
    attention = g.log.state.status == "needs_attention"
    g.stop()
    t.join(5)
    assert attention, "the governor should wait for the human"


def traces(setup) -> list[dict]:
    s, _ = setup
    return [json.loads(p.read_text()) for p in sorted((s.runs_dir / "civ1" / "traces").glob("0*.json"))]


def orders_sent(game: FakeCiv6) -> list[dict]:
    return [a[1] for a in game.actions if a[0] == "order"]


def test_a_decision_applies_orders_then_autoplays(setup):
    game = FakeCiv6(FIXTURE, index=INDEX)
    g = governor(setup, game, orders_model([
        {"kind": "research", "id": "tech:pottery"},
        {"kind": "production", "city": "Beijing", "id": "unit:settler"},
    ], []))
    g.run(max_decisions=2)
    sent = orders_sent(game)
    assert sent[:2] == [{"kind": "research", "id": "tech:pottery"},
                        {"kind": "production", "city": "Beijing", "id": "unit:settler"}]
    kinds = [a[0] for a in game.actions]
    assert kinds.index("autoplay") > kinds.index("order"), "orders first, then autoplay"
    assert [a for a in game.actions if a[0] == "autoplay"] == [("autoplay", 1, False)] * 3, "one turn at a time"
    assert all(not a[2] for a in game.actions if a[0] == "order"), "no order while the AI plays"
    first = traces(setup)[0]
    assert [o["outcome"] for o in first["orders"]] == ["stuck", "stuck"]
    assert game.state["turn"] == FIXTURE["turn"] + 3                 # the AI played the stretch
    assert traces(setup)[1]["trigger"] == "scheduled (3 turns)"
    assert g.log.campaign_id == "civ6/kublai_khan_china_702403662"


def test_an_order_that_did_not_stick_is_reported_and_not_retried_blindly(setup):
    seen: list[str] = []
    game = FakeCiv6(FIXTURE, index=INDEX, sticks=False)
    order = {"kind": "research", "id": "tech:pottery"}
    g = governor(setup, game, orders_model([order], seen=seen))
    g.run(max_decisions=2)
    first, second = traces(setup)[:2]
    assert first["orders"][0]["outcome"] == "research is TECH_MINING"
    assert "did not stick" in seen[1] and "research tech:pottery" in seen[1]
    assert second["orders"][0]["outcome"].startswith("refused: did not stick at the last decision")
    assert orders_sent(game).count(order) == 1


def test_changes_by_the_ai_during_autoplay_are_reported(setup):
    seen: list[str] = []

    def ai(state):   # the AI switches Beijing to a warrior
        state["cities"][0]["producing"] = "UNIT_WARRIOR"

    game = FakeCiv6(FIXTURE, index=INDEX, ai=ai)
    g = governor(setup, game, orders_model([{"kind": "production", "city": "Beijing", "id": "unit:settler"}], [],
                                           seen=seen))
    g.run(max_decisions=2)
    assert "production unit:settler in Beijing: replaced by the AI with unit:warrior by T13" in seen[1]


def test_an_urgent_change_stops_autoplay(setup):
    def war(state):
        state["wars"] = [{"id": 1, "civ": "CIVILIZATION_ROME", "major": True}]

    game = FakeCiv6(FIXTURE, index=INDEX, events={FIXTURE["turn"] + 1: war})
    s, _ = setup
    s.decide_every_turns = 5
    g = governor(setup, game, orders_model([]))
    g.run(max_decisions=2)
    assert [a for a in game.actions if a[0] == "autoplay"] == [("autoplay", 1, False)], "no next turn after it"
    second = traces(setup)[1]
    assert second["trigger"].startswith("urgent: new war: CIVILIZATION_ROME")
    assert game.state["turn"] == FIXTURE["turn"] + 1


def test_invalid_ids_are_rejected_before_the_game(setup):
    game = FakeCiv6(FIXTURE, index=INDEX)
    g = governor(setup, game, orders_model([
        {"kind": "research", "id": "tech:warp_drive"},
        {"kind": "production", "city": "Beijing", "id": "wonder:pyramids"},
        {"kind": "production", "city": "Atlantis", "id": "unit:warrior"},
        {"kind": "civic", "id": "tech:pottery"},
        {"kind": "policies", "ids": ["policy:nope"]},
    ]))
    g.run(max_decisions=1)
    assert orders_sent(game) == []
    outcomes = [o["outcome"] for o in traces(setup)[0]["orders"]]
    assert outcomes[0] == "refused: unknown id 'tech:warp_drive'"
    assert "wonders need a tile" in outcomes[1]
    assert "no city of ours named 'Atlantis'" in outcomes[2]
    assert "tech:pottery is a tech" in outcomes[3]
    assert "unknown policy ids" in outcomes[4]


def test_purchases_respect_the_reserve_and_the_treasury_share(setup):
    buy = SPEC.actions["purchase"]
    city = FIXTURE["cities"][0]
    rich = {**FIXTURE, "gold": 400}
    assert purchase_cap(rich, city, "gold", buy) == 200                     # half the treasury
    assert purchase_cap(rich, {**city, "threatened": True}, "gold", buy) == 200, "merely threatened: half"
    assert purchase_cap(rich, {**city, "under_siege": True}, "gold", buy) == 400 - buy.gold_reserve
    assert purchase_cap({**FIXTURE, "gold": buy.gold_reserve}, city, "gold", buy) == 0

    game = FakeCiv6({**FIXTURE, "gold": 400}, index=INDEX, prices={("Beijing", "unit:slinger"): 280})
    g = governor(setup, game, orders_model([{"kind": "purchase", "city": "Beijing", "id": "unit:slinger"}]))
    g.run(max_decisions=1)
    assert orders_sent(game) == [{"kind": "purchase", "city": "Beijing", "id": "unit:slinger", "currency": "gold",
                                  "max_cost": 200}]
    assert game.state["gold"] == 400, "a price over the cap buys nothing"
    assert "over the allowed 200" in traces(setup)[0]["orders"][0]["outcome"]


def test_a_purchase_at_the_reserve_never_reaches_the_game(setup):
    game = FakeCiv6({**FIXTURE, "gold": 30}, index=INDEX)
    g = governor(setup, game, orders_model([{"kind": "purchase", "city": "Beijing", "id": "unit:warrior"}]))
    g.run(max_decisions=1)
    assert orders_sent(game) == []
    assert "at or below the reserve" in traces(setup)[0]["orders"][0]["outcome"]


def test_an_affordable_purchase_is_bought_and_read_back(setup):
    game = FakeCiv6({**FIXTURE, "gold": 400}, index=INDEX, prices={("Beijing", "unit:warrior"): 160})
    g = governor(setup, game, orders_model([{"kind": "purchase", "city": "Beijing", "id": "unit:warrior"}]))
    g.run(max_decisions=1)
    assert game.state["gold"] == 240
    assert traces(setup)[0]["orders"][0]["outcome"] == "stuck"


def test_orders_per_decision_are_capped_by_the_pillars_file(setup):
    game = FakeCiv6(FIXTURE, index=INDEX)
    g = governor(setup, game, orders_model([{"kind": "research", "id": "tech:pottery"},
                                            {"kind": "research", "id": "tech:mining"}]))
    g.run(max_decisions=1)
    assert orders_sent(game) == [{"kind": "research", "id": "tech:pottery"}]
    assert "at most 1 research order" in traces(setup)[0]["orders"][1]["outcome"]


def test_metrics_rows_and_briefing_come_from_the_snapshot():
    m = metrics({**FIXTURE, "date": "T12", "majors": [{"civ": "CIVILIZATION_ROME", "score": 30, "military": 10,
                                                        "techs": 2, "civics": 1, "cities": 2}]})
    assert (m["date"], m["cities"], m["pop"], m["military"]) == ("T12", 1, 2, FIXTURE["military"])
    assert m["peers"]["score"]["rank"] == 2 and m["peers"]["military"]["rank"] == 1
    text = briefing_text(FIXTURE, INDEX, 60)
    assert "tech:mining" in text and "unit:builder" in text and "policy:god_king" in text
    assert "TECH_" not in text and "UNIT_" not in text.replace("ENDTURN_BLOCKING_UNITS", "")


def test_urgent_changes_cover_the_ruled_triggers():
    before = {**FIXTURE, "gold": 100}
    city2 = {**FIXTURE["cities"][0], "name": "Xian", "capital": False}
    two = {**before, "cities": [*FIXTURE["cities"], city2]}
    assert urgent_changes(two, before) == ["city lost: Xian"]
    sieged = {**before, "cities": [{**FIXTURE["cities"][0], "under_siege": True, "threatened": True}]}
    assert urgent_changes(before, sieged)[0].startswith("city threatened: Beijing")
    assert urgent_changes(before, {**before, "era_index": 1, "era": "ERA_CLASSICAL"}) == ["new era: ERA_CLASSICAL"]
    assert urgent_changes(before, {**before, "gold": 40}, gold_reserve=60) == ["gold below the reserve: 40 < 60"]
    wonder = {**before, "cities": [{**FIXTURE["cities"][0], "producing": "BUILDING_PYRAMIDS"}]}
    assert urgent_changes(wonder, before, wonders={"BUILDING_PYRAMIDS"}) == ["wonder race lost: BUILDING_PYRAMIDS in Beijing"]
    gp_before = {**before, "great_people": {"recruited": 0, "past": [], "current": [
        {"class": "GREAT_PERSON_CLASS_SCIENTIST", "cost": 60, "ours": 40}]}}
    gp_now = {**before, "great_people": {"recruited": 1, "current": [], "past": [
        {"class": "GREAT_PERSON_CLASS_SCIENTIST", "claimant": 3}]}}
    assert urgent_changes(gp_before, gp_now) == ["great person race lost: GREAT_PERSON_CLASS_SCIENTIST"]
    assert urgent_changes(before, before) == []


def test_check_orders_uses_the_snapshot_options():
    out = check_orders([Civ6Order(kind="research", id="tech:writing")], FIXTURE, SPEC, INDEX)
    assert "cannot be researched now" in out[0].error
    out = check_orders([Civ6Order(kind="production", city="beijing", id="building:granary")], FIXTURE, SPEC, INDEX)
    assert "Beijing cannot build building:granary now" in out[0].error


def test_the_controller_wrapper_reads_json_and_passes_orders_as_one_argument(tmp_path):
    from pilot.civ6 import ControllerCiv6
    stub = tmp_path / "game-controller"
    log = tmp_path / "args.txt"
    stub.write_text(f"""#!/bin/sh
printf '%s\\n' "$@" >> {log}
case "$4" in
  snapshot) echo '{{"ok":true,"turn":7,"cities":[]}}' ;;
  order) echo '{{"ok":false,"error":"unknown id"}}'; exit 2 ;;
  autoplay) echo '{{"ok":true,"active":false,"turns":5}}' ;;
esac
""")
    stub.chmod(0o755)
    game = ControllerCiv6(stub, tmp_path / "civ6", "http://pc:8765", tmp_path, token="t" * 32)
    assert game.snapshot() == {"ok": True, "turn": 7, "cities": [], "date": "T7"}
    hostile = {"kind": "production", "city": "a'; rm -rf / #", "id": "unit:warrior"}
    assert game.order(hostile) == {"ok": False, "error": "unknown id"}
    assert game.autoplay(5)["turns"] == 5
    args = log.read_text().splitlines()
    assert json.loads(args[args.index("order") + 1]) == hostile, "the order is one argv entry, never shell text"



# ---- review fixes: reserve across purchases, no pillars, autoplay failures, read-back, triggers ------

def test_two_purchases_together_keep_the_reserve():
    rich = {**FIXTURE, "gold": 300}
    out = check_orders([Civ6Order(kind="purchase", city="Beijing", id="unit:warrior"),
                        Civ6Order(kind="purchase", city="Beijing", id="unit:slinger")], rich, SPEC, INDEX)
    caps = [c.wire["max_cost"] for c in out]
    assert caps == [150, 75]
    assert 300 - sum(caps) >= SPEC.actions["purchase"].gold_reserve


def test_without_pillars_purchases_are_refused_and_each_kind_gets_one_order():
    out = check_orders([Civ6Order(kind="purchase", city="Beijing", id="unit:warrior"),
                        Civ6Order(kind="research", id="tech:pottery"),
                        Civ6Order(kind="research", id="tech:mining")], {**FIXTURE, "gold": 900}, None, INDEX)
    assert "purchases need the limits of pillars.toml" in out[0].error
    assert out[1].error == "" and "at most 1 research" in out[2].error


def test_an_invalid_order_does_not_use_the_quota():
    out = check_orders([Civ6Order(kind="research", id="tech:warp"), Civ6Order(kind="research", id="tech:pottery")],
                       FIXTURE, SPEC, INDEX)
    assert out[0].error.startswith("unknown id") and out[1].error == ""


def test_one_production_order_per_city():
    out = check_orders([Civ6Order(kind="production", city="Beijing", id="unit:settler"),
                        Civ6Order(kind="production", city="Beijing", id="unit:warrior")], FIXTURE, SPEC, INDEX)
    assert out[0].error == "" and "one per city" in out[1].error


def test_two_purchases_are_read_back_against_their_total(setup):
    prices = {("Beijing", "unit:warrior"): 100, ("Beijing", "unit:slinger"): 60}
    game = FakeCiv6({**FIXTURE, "gold": 400}, index=INDEX, prices=prices,
                    replies={"purchase": {"ok": True}})
    game.sticks = False                                      # the game said ok but nothing was spent
    g = governor(setup, game, orders_model([{"kind": "purchase", "city": "Beijing", "id": "unit:warrior"},
                                            {"kind": "purchase", "city": "Beijing", "id": "unit:slinger"}]))
    g.run(max_decisions=1)
    assert [o["outcome"] for o in traces(setup)[0]["orders"]] == ["gold went from 400 to 400"] * 2


def test_autoplay_that_fails_to_start_waits_for_the_human(setup):
    game = FakeCiv6(FIXTURE, index=INDEX, start_fails=True)
    g = governor(setup, game, orders_model([]))
    run_until_attention(g)
    events = (setup[0].runs_dir / "civ1" / "events.jsonl").read_text()
    assert "autoplay did not start at T12" in events and '"needs_attention"' in events
    assert [a[0] for a in game.actions].count("autoplay") == 1, "no retry loop burning decisions"
    assert len(traces(setup)) == 1


def test_autoplay_that_never_runs_waits_for_the_human(setup):
    game = FakeCiv6(FIXTURE, index=INDEX, never_starts=True)
    g = governor(setup, game, orders_model([]))
    run_until_attention(g)
    events = (setup[0].runs_dir / "civ1" / "events.jsonl").read_text()
    assert "still inactive" in events and len(traces(setup)) == 1


def test_a_failing_autoplay_stop_does_not_block_the_loop(setup):
    def war(state):
        state["wars"] = [{"id": 1, "civ": "CIVILIZATION_ROME", "major": True}]

    game = FakeCiv6(FIXTURE, index=INDEX, stop_raises=True, events={FIXTURE["turn"] + 1: war})
    g = governor(setup, game, orders_model([{"kind": "research", "id": "tech:pottery"}], []))
    g.run(max_decisions=2)
    assert traces(setup)[1]["trigger"].startswith("urgent: new war")
    assert all(not a[2] for a in game.actions if a[0] == "order")


def test_the_loop_works_when_the_game_is_silent_during_ai_turns(setup):
    """Like the real tuner: every call made while the AI plays times out."""
    game = FakeCiv6(FIXTURE, index=INDEX, busy=True)
    g = governor(setup, game, orders_model([{"kind": "production", "city": "Beijing", "id": "unit:settler"}], []))
    g.run(max_decisions=2)
    assert game.state["turn"] == FIXTURE["turn"] + 3
    assert traces(setup)[1]["trigger"] == "scheduled (3 turns)"
    assert all(not a[2] for a in game.actions if a[0] == "order")
    events = (setup[0].runs_dir / "civ1" / "events.jsonl").read_text()
    assert '"unanswered_polls": 1' in events and '"needs_attention"' not in events


def test_a_turn_that_never_ends_waits_for_the_human(setup):
    game = FakeCiv6(FIXTURE, index=INDEX)
    game.autoplay_status = lambda: {"ok": True, "active": True, "turn": FIXTURE["turn"]}   # stuck mid-turn
    g = governor(setup, game, orders_model([]))
    run_until_attention(g)
    events = (setup[0].runs_dir / "civ1" / "events.jsonl").read_text()
    assert "T12 did not end within" in events


def test_a_failed_read_back_is_unknown_not_a_failure(setup):
    seen: list[str] = []
    order = {"kind": "research", "id": "tech:pottery"}
    game = FakeCiv6(FIXTURE, index=INDEX, readback_fails=True)
    g = governor(setup, game, orders_model([order], seen=seen))
    g.run(max_decisions=2)
    first, second = traces(setup)[:2]
    assert first["orders"][0]["outcome"].startswith("unknown: not read back")
    assert second["orders"][0]["outcome"] == "stuck", "an unknown outcome is not refused as did-not-stick"


def test_a_lost_reply_is_read_back_before_judging(setup):
    game = FakeCiv6(FIXTURE, index=INDEX, transport=True)
    g = governor(setup, game, orders_model([{"kind": "research", "id": "tech:pottery"}]))
    g.run(max_decisions=1)
    assert traces(setup)[0]["orders"][0]["outcome"] == "stuck"


def test_civ6_urgent_events_start_a_strategy_review(setup):
    def lose(state):
        state["cities"] = []

    game = FakeCiv6({**FIXTURE, "cities": [*FIXTURE["cities"], {**FIXTURE["cities"][0], "name": "Xian"}]},
                    index=INDEX, events={FIXTURE["turn"] + 1: lose})
    reviews = {"n": 0}

    def respond(messages, info):
        if is_review(info):
            reviews["n"] += 1
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,
                                                     {"change": False, "assessment": "n/a", "rules": []})])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"orders": [], "reason": "r"})])

    g = governor(setup, game, FunctionModel(respond))
    g.run(max_decisions=2)
    assert traces(setup)[1]["trigger"].startswith("urgent: city lost")
    assert reviews["n"] == 2, "start of run + the city-lost review"


def test_a_human_pause_survives_auto_recovery(setup):
    game = FakeCiv6(FIXTURE, index=INDEX)
    g = governor(setup, game, orders_model([]))
    g.pause()
    g._needs_attention("agent timed out", auto_recover=True)
    assert g._probe_recovered() is True
    assert g.control.paused is True and g.log.state.status == "paused"


def test_a_wonder_the_ai_dropped_is_not_a_lost_race():
    building = {**FIXTURE, "cities": [{**FIXTURE["cities"][0], "producing": "BUILDING_PYRAMIDS"}]}
    assert urgent_changes(building, {**FIXTURE, "wonders_elsewhere": []}, wonders={"BUILDING_PYRAMIDS"}) == []
    assert urgent_changes(building, {**FIXTURE, "wonders_elsewhere": ["BUILDING_PYRAMIDS"]},
                          wonders={"BUILDING_PYRAMIDS"}) == ["wonder race lost: BUILDING_PYRAMIDS in Beijing"]


def test_autoplay_reading_inactive_before_its_last_turn_is_not_its_end(setup):
    s, _ = setup
    s.autoplay_chunk = 3
    game = FakeCiv6(FIXTURE, index=INDEX, blink=True)
    g = governor(setup, game, orders_model([{"kind": "research", "id": "tech:pottery"}], []))
    g.run(max_decisions=2)
    assert game.state["turn"] == FIXTURE["turn"] + 3
    assert traces(setup)[1]["date"] == f"T{FIXTURE['turn'] + 3}"
    assert all(not a[2] for a in game.actions if a[0] == "order"), "no order while the last turn still runs"


def test_a_lost_reply_to_autoplay_is_not_a_failure(setup):
    game = FakeCiv6(FIXTURE, index=INDEX, lost_start_reply=True)
    g = governor(setup, game, orders_model([]))
    g.run(max_decisions=2)
    assert traces(setup)[1]["trigger"] == "scheduled (3 turns)"
    assert [a[0] for a in game.actions].count("autoplay") == 3, "a start that ran is never sent again"


def test_autoplay_chunks_play_several_turns_per_call(setup):
    s, _ = setup
    s.autoplay_chunk = 2
    game = FakeCiv6(FIXTURE, index=INDEX)
    g = governor(setup, game, orders_model([]))
    g.run(max_decisions=2)
    assert [a[1] for a in game.actions if a[0] == "autoplay"] == [2, 1], "the last chunk stops at the decision turn"
    assert game.state["turn"] == FIXTURE["turn"] + 3


def test_autoplay_plays_single_turns_while_in_danger_and_chunks_otherwise():
    """Ruling (live T27-T41): one-turn autoplay stalled the AI's plans (a Settler 7 turns, the
    pantheon), so chunks of `autoplay_chunk` (default 3) run in peace, single turns at war with a
    major or with a city in danger (amendment A1: `in_danger`, not "threatened", which held in 93% of
    the Kublai campaign's city snapshots)."""
    from pilot.civ6_governor import autoplay_turns
    peace = {"wars": [], "cities": [{"threatened": False, "under_siege": False}]}
    assert autoplay_turns(peace, chunk=3, left=10) == 3
    assert autoplay_turns(peace, chunk=3, left=2) == 2
    assert autoplay_turns({**peace, "wars": [{"with": "Rome"}]}, chunk=3, left=10) == 1
    assert autoplay_turns({**peace, "wars": [{"civ": "CIVILIZATION_AUSTRALIA", "major": True}]}, chunk=3, left=10) == 1
    assert autoplay_turns({**peace, "wars": [{"civ": "CIVILIZATION_CAGUANA", "major": False}]}, chunk=3, left=10) == 3
    assert autoplay_turns({"wars": [], "cities": [{"threatened": True, "enemies_near": 1}]}, chunk=3, left=10) == 3
    assert autoplay_turns({"wars": [], "cities": [{"under_siege": True}]}, chunk=3, left=10) == 1
    lone_scout = {"threatened": True, "enemies_near": 1, "garrison": None, "capture_adjacent": 0,
                  "defense": {"garrison_hp": 200, "garrison_max": 200, "walls_hp": 0, "walls_max": 0}}
    assert autoplay_turns({"wars": [], "cities": [lone_scout]}, chunk=3, left=10) == 3
    beijing_t61 = {**lone_scout, "enemies_near": 2, "capture_adjacent": 2}
    assert autoplay_turns({"wars": [], "cities": [beijing_t61]}, chunk=3, left=10) == 1
    from pilot.config import Settings
    assert Settings().autoplay_chunk == 3


# ---- the order record (docs/design/2026-09-27-civ6-levers-design.md, rulings 12-16) ---------------

ORDERS = SPEC.orders


def _city0(**over) -> dict:
    return {**FIXTURE["cities"][0], **over}


def snap(turn: int, **over) -> dict:
    return {**FIXTURE, "turn": turn, "date": f"T{turn}", **over}


def test_research_and_civics_complete_when_they_leave_the_options_and_are_overridden_while_offered():
    c = Checked(order={"kind": "research"}, expect={"research": "TECH_POTTERY"})
    base = {"turn": 12, "turns_left": 5}
    opts = FIXTURE["options"]
    assert held_outcome(c, base, snap(13, research={"tech": "TECH_POTTERY"}), 8) == ("open", None)
    done = snap(14, research={"tech": "TECH_MINING"}, options={**opts, "techs": ["TECH_MINING"]})
    assert held_outcome(c, base, done, 8) == ("completed", None)
    assert held_outcome(c, base, snap(14, research={"tech": "TECH_MINING"}), 8) == ("overridden", "TECH_MINING")
    assert held_outcome(c, base, snap(14, research={"tech": "TECH_MINING"}, options=None), 8) == ("unknown", "TECH_MINING")
    civic = Checked(order={"kind": "civic"}, expect={"civic": "CIVIC_FOREIGN_TRADE"})
    assert held_outcome(civic, base, snap(14, civic=None, options={**opts, "civics": ["CIVIC_CRAFTSMANSHIP"]}), 8) \
        == ("completed", None)
    assert held_outcome(civic, base, snap(14, civic={"civic": "CIVIC_CRAFTSMANSHIP"}), 8) \
        == ("overridden", "CIVIC_CRAFTSMANSHIP")


def test_units_complete_when_their_count_rises_and_are_overridden_when_the_ai_switches_early():
    c = Checked(order={"kind": "production"}, expect={"city": "Beijing", "producing": "UNIT_SLINGER"})
    base = {"turn": 27, "turns_left": 4, "count": 0}
    building = snap(28, cities=[_city0(producing="UNIT_SLINGER", turns_left=3)])
    assert held_outcome(c, base, building, 7) == ("open", None)
    built = snap(31, cities=[_city0(producing="BUILDING_GRANARY")], units={"by_type": {"UNIT_SLINGER": 1}})
    assert held_outcome(c, base, built, 7) == ("completed", None)
    switched = snap(29, cities=[_city0(producing="BUILDING_GRANARY")])
    assert held_outcome(c, base, switched, 7) == ("overridden", "BUILDING_GRANARY"), "live T27-31: Slinger → Granary"
    late = snap(32, cities=[_city0(producing="BUILDING_GRANARY")])
    assert held_outcome(c, base, late, 7) == ("unknown", "BUILDING_GRANARY"), "after its turns: built and lost?"
    obsolete = snap(29, cities=[_city0(producing="UNIT_ARCHER", can_build=["UNIT_ARCHER", "UNIT_WARRIOR"])])
    assert held_outcome(c, base, obsolete, 7) == ("invalidated", "UNIT_ARCHER"), "Slinger after Archery"
    assert held_outcome(c, base, snap(29, cities=[]), 7) == ("unknown", None), "the city is gone"


def test_buildings_complete_when_they_appear_and_orders_that_stay_current_are_held():
    c = Checked(order={"kind": "production"}, expect={"city": "Beijing", "producing": "BUILDING_MONUMENT"})
    base = {"turn": 12, "turns_left": 6, "count": 0}
    assert held_outcome(c, base, snap(18, cities=[_city0(producing="UNIT_SETTLER", buildings=["BUILDING_MONUMENT"])]),
                        9) == ("completed", None)
    older = snap(18, cities=[_city0(producing="UNIT_SETTLER", can_build=["UNIT_SETTLER"])])      # no buildings field
    assert held_outcome(c, base, older, 9) == ("completed", None)
    current = snap(21, cities=[_city0(producing="BUILDING_MONUMENT", buildings=[])])
    assert held_outcome(c, base, current, 9) == ("held", None), "still current when its window ends"
    assert held_outcome(c, base, snap(20, cities=[_city0(producing="BUILDING_MONUMENT")]), 9) == ("open", None)
    assert order_window("production", 6) == 9 and order_window("production", 40) == 20
    assert order_window("research", None) == 3 and order_window("policies", 1) == 20


def test_policies_changed_by_the_ai_are_overridden():
    c = Checked(order={"kind": "policies"}, expect={"policies": ["POLICY_GOD_KING", "POLICY_DISCIPLINE"]})
    base = {"turn": 27}
    assert held_outcome(c, base, snap(30), 20) == ("open", None)
    slots = [{"policy": "POLICY_SURVEY", "slot": 0}, {"policy": "POLICY_DISCIPLINE", "slot": 1}]
    unslotted = {**FIXTURE["options"], "policies": ["POLICY_GOD_KING"]}      # unlocked again, not active
    assert held_outcome(c, base, snap(30, policy_slots=slots, options=unslotted), 20) == ("overridden", "POLICY_SURVEY")
    assert held_outcome(c, base, snap(47), 20) == ("held", None)
    gone = snap(30, policy_slots=slots, options={**FIXTURE["options"], "policies": []})
    assert held_outcome(c, base, gone, 20) == ("invalidated", None)


def _rows(key: str, results: list[str], start: int = 10, step: int = 4) -> list[dict]:
    return [{"key": key, "result": r, "turn": start + step * i, "id": "unit:slinger", "by": "building:granary",
             "city": "Beijing", "date": f"T{start + step * i}"} for i, r in enumerate(results)]


def test_the_stick_rate_needs_enough_judged_orders_and_flags_weak_kinds():
    rows = _rows("production replace", ["completed", "overridden", "overridden", "completed", "overridden"]) \
        + _rows("civic", ["completed", "completed"]) + _rows("research", ["refused"])
    rec = order_record(rows, 30, ORDERS)
    r = rec["production replace"]
    assert (r["judged"], r["completed"], r["overridden"], r["rate"], r["weak"]) == (5, 2, 3, 0.4, True)
    assert r["last_override"] == {"id": "unit:slinger", "by": "building:granary", "city": "Beijing", "date": "T26"}
    assert rec["civic"]["rate"] is None and rec["civic"]["judged"] == 2, "below 3 samples: counts only"
    assert rec["research"]["judged"] == 0 and rec["research"]["excluded"]["refused"] == 1
    assert list(rec) == ["research", "civic", "production replace"], "a fixed order of keys"
    text = order_record_text(rec, {"research": (0, 10), "civic": (3, 10)})
    assert ("- production replace: 5 judged; 2 completed, 3 replaced by the AI (last: unit:slinger → building:granary "
            "in Beijing, T26); held 40% — does not stick here") in text
    assert "- civic: 2 judged; 2 completed (a rate needs 3)" in text
    assert "- research: 0 judged (not judged: 1 refused)" in text
    assert "- civic idle at 3 of 10 snapshots in the last 30 turns" in text and "research idle" not in text
    assert not order_record(_rows("production fill", ["completed"] * 3 + ["overridden"]), 30, ORDERS)["production fill"]["weak"]


def test_the_window_widens_back_until_it_holds_enough_orders():
    old = _rows("production replace", ["overridden"] * 6, start=10, step=2)       # T10-T20
    new = _rows("production replace", ["completed"] * 3, start=60, step=2)        # T60-T64
    r = order_record(old + new, 70, ORDERS)["production replace"]
    assert (r["judged"], r["completed"], r["overridden"]) == (8, 3, 5), "the last 8 judged, back to T14"
    many = _rows("production replace", ["completed"] * 12, start=50, step=1)
    assert order_record(old + many, 70, ORDERS)["production replace"]["judged"] == 12, "30 turns hold 12"


def _replace_fixture() -> dict:
    """Beijing builds a Warrior with 5 turns left: a production order there replaces the AI's choice."""
    return {**FIXTURE, "cities": [_city0(producing="UNIT_WARRIOR", turns_left=5)]}


def _events(setup) -> list[dict]:
    s, _ = setup
    return [json.loads(line) for line in (s.runs_dir / "civ1" / "events.jsonl").read_text().splitlines()]


def test_an_order_the_ai_replaces_is_in_the_record_and_the_next_prompt(setup):
    seen: list[str] = []

    def ai(state):
        state["cities"][0]["producing"] = "BUILDING_GRANARY"

    game = FakeCiv6(_replace_fixture(), index=INDEX, ai=ai)
    g = governor(setup, game, orders_model([{"kind": "production", "city": "Beijing", "id": "unit:slinger"}], [],
                                           seen=seen))
    g.run(max_decisions=2)
    assert "production unit:slinger in Beijing: replaced by the AI with building:granary by T13" in seen[1]
    assert "Order record in this campaign (held until done / replaced by the AI):" in seen[1]
    assert "- production replace: 1 judged; 1 replaced by the AI (last: unit:slinger → building:granary in Beijing, T13)" \
        in seen[1]
    rows = [e for e in _events(setup) if e["kind"] == "order_outcome"]
    assert [(r["key"], r["result"], r["by"], r["turns"], r["situation"]) for r in rows] == \
        [("production replace", "overridden", "building:granary", 1, "replace")]
    assert g.log.state.info["order_record"]["production replace"]["overridden"] == 1


def test_a_tech_that_completes_is_reported_completed(setup):
    seen: list[str] = []

    def learn(state):
        state["research"] = {"tech": "TECH_MINING", "turns_left": 3}
        state["options"] = {**state["options"], "techs": [t for t in state["options"]["techs"] if t != "TECH_POTTERY"]}

    game = FakeCiv6(FIXTURE, index=INDEX, events={FIXTURE["turn"] + 2: learn})
    g = governor(setup, game, orders_model([{"kind": "research", "id": "tech:pottery"}], [], seen=seen))
    g.run(max_decisions=2)
    assert "research tech:pottery: completed by T14" in seen[1]
    assert "- research: 1 judged; 1 completed (a rate needs 3)" in seen[1]


def test_a_decision_without_orders_keeps_following_earlier_ones(setup):
    seen: list[str] = []
    s, _ = setup
    s.decide_every_turns = 1

    def switch(state):
        state["cities"][0]["producing"] = "BUILDING_MONUMENT"

    game = FakeCiv6(_replace_fixture(), index=INDEX, events={FIXTURE["turn"] + 2: switch})
    g = governor(setup, game, orders_model([{"kind": "production", "city": "Beijing", "id": "unit:slinger"}], [], [],
                                           seen=seen))
    g.run(max_decisions=3)
    assert "production unit:slinger in Beijing: in force at T13 (1 of 7 turns followed)" in seen[1]
    assert "production unit:slinger in Beijing: replaced by the AI with building:monument by T14" in seen[2]


def test_a_later_run_of_the_campaign_starts_with_its_record(setup, tmp_path):
    from pilot.telemetry import Telemetry
    s, _ = setup
    tel = Telemetry(tmp_path / "t.sqlite")

    def ai(state):
        state["cities"][0]["producing"] = "BUILDING_GRANARY"

    first = Civ6Governor(s, FakeCiv6(_replace_fixture(), index=INDEX, ai=ai), EventLog(s.runs_dir, "r1", s.model, telemetry=tel),
                         model=orders_model([{"kind": "production", "city": "Beijing", "id": "unit:slinger"}], []))
    first.status_poll_s, first.start_grace_s = 0, 0.05
    first.run(max_decisions=2)
    seen: list[str] = []
    second = Civ6Governor(s, FakeCiv6(_replace_fixture(), index=INDEX), EventLog(s.runs_dir, "r2", s.model, telemetry=tel),
                          model=orders_model([], seen=seen))
    second.status_poll_s, second.start_grace_s = 0, 0.05
    second.run(max_decisions=1)
    assert "- production replace: 1 judged; 1 replaced by the AI" in seen[0], "the record survives a restart"
    assert second.log.state.info["order_record"]["production replace"]["judged"] == 1


def test_the_civ6_strategist_sees_the_order_record(setup):
    prompts: list[str] = []

    def respond(messages, info):
        text = "\n".join(str(getattr(p, "content", "")) for m in messages for p in getattr(m, "parts", []))
        if is_review(info):
            prompts.append(text)
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,
                                                     {"change": False, "assessment": "n/a", "rules": []})])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"orders": [], "reason": "r"})])

    g = governor(setup, FakeCiv6(FIXTURE, index=INDEX), FunctionModel(respond))
    g.run(max_decisions=1)
    assert "Order record in this campaign (held until done / replaced by the AI):\n(no orders judged yet)" in prompts[0]
    assert "Directive record" not in prompts[0]


def test_trace_orders_carry_kind_id_and_city(setup):
    game = FakeCiv6(FIXTURE, index=INDEX)
    g = governor(setup, game, orders_model([{"kind": "production", "city": "beijing", "id": "unit:settler"},
                                            {"kind": "research", "id": "tech:pottery"}]))
    g.run(max_decisions=1)
    orders = traces(setup)[0]["orders"]
    assert [(o["kind"], o["id"], o["city"]) for o in orders] == [("production", "unit:settler", "Beijing"),
                                                                 ("research", "tech:pottery", "")]


def test_an_idle_civic_is_asked_again_then_filled_by_the_governor(setup):
    from pilot.strategy import Pillar, Strategy
    seen: list[str] = []
    idle = {**FIXTURE, "civic": None}
    game = FakeCiv6(idle, index=INDEX)
    g = governor(setup, game, orders_model([], seen=seen))
    weights = {"science": 25, "expansion": 20, "economy": 15, "culture": 12, "military": 12, "faith": 8, "diplomacy": 8}
    g.strategy = Strategy(pillars={n: Pillar(weight=w, stance="s") for n, w in weights.items()}, focus="f")
    g.strategy.pillars["culture"] = g.strategy.pillars["culture"].model_copy(
        update={"prefer_civics": ["civic:code_of_laws", "civic:foreign_trade"]})
    g.run(max_decisions=1)
    assert len(seen) == 2 and "Your answer was incomplete: nothing is being progressed" in seen[1], "one retry"
    assert orders_sent(game) == [{"kind": "civic", "id": "civic:foreign_trade"}], "the first preferred civic offered"
    first = traces(setup)[0]
    assert first["orders"][0]["order"] == "civic civic:foreign_trade (filled by the governor)"
    assert first["orders"][0]["by"] == "governor" and first["retried_for"] == ["civic"]


def test_an_idle_research_answered_on_the_retry_is_not_filled(setup):
    seen: list[str] = []
    game = FakeCiv6({**FIXTURE, "research": None}, index=INDEX)
    g = governor(setup, game, orders_model([], [{"kind": "research", "id": "tech:sailing"}], seen=seen))
    g.run(max_decisions=1)
    assert orders_sent(game) == [{"kind": "research", "id": "tech:sailing"}]
    assert "filled by the governor" not in traces(setup)[0]["orders"][0]["order"]


def test_without_a_strategy_the_first_offered_item_fills_an_idle_research(setup):
    game = FakeCiv6({**FIXTURE, "research": None}, index=INDEX)
    g = governor(setup, game, orders_model([{"kind": "research", "id": "tech:warp_drive"}]))
    g.run(max_decisions=1)
    assert orders_sent(game) == [{"kind": "research", "id": "tech:pottery"}], "an invalid order does not count"


def test_a_purchase_is_completed_at_once_and_refused_orders_get_a_row(setup):
    game = FakeCiv6({**FIXTURE, "gold": 400}, index=INDEX, prices={("Beijing", "unit:warrior"): 160})
    g = governor(setup, game, orders_model([{"kind": "purchase", "city": "Beijing", "id": "unit:warrior"},
                                            {"kind": "research", "id": "tech:warp"}]))
    g.run(max_decisions=1)
    rows = [(e["key"], e["result"]) for e in _events(setup) if e["kind"] == "order_outcome"]
    assert rows == [("purchase gold", "completed"), ("research", "refused")]
    assert game.state["units"]["by_type"]["UNIT_WARRIOR"] == 2


def test_our_own_later_order_supersedes_the_earlier_one(setup):
    game = FakeCiv6(_replace_fixture(), index=INDEX)
    g = governor(setup, game, orders_model([{"kind": "production", "city": "Beijing", "id": "unit:slinger"}],
                                           [{"kind": "production", "city": "Beijing", "id": "unit:scout"}]))
    g.run(max_decisions=2)
    rows = [(e["id"], e["result"]) for e in _events(setup) if e["kind"] == "order_outcome"]
    assert rows == [("unit:slinger", "superseded")]
    assert [t.row["id"] for t in g._tracking] == ["unit:scout"]


def test_a_timed_out_autoplay_start_is_sent_again(setup):
    game = FakeCiv6(FIXTURE, index=INDEX, lost_start_not_run=2)
    g = governor(setup, game, orders_model([]))
    g.run(max_decisions=2)
    assert [a[0] for a in game.actions].count("autoplay") >= 3
    assert traces(setup)[1]["trigger"] == "scheduled (3 turns)"
    events = (setup[0].runs_dir / "civ1" / "events.jsonl").read_text()
    assert "sent again (1 of 2)" in events and "sent again (2 of 2)" in events and '"needs_attention"' not in events


def test_a_start_that_never_runs_after_two_retries_waits_for_the_human(setup):
    game = FakeCiv6(FIXTURE, index=INDEX, lost_start_not_run=3)
    g = governor(setup, game, orders_model([]))
    run_until_attention(g)
    assert [a[0] for a in game.actions].count("autoplay") == 3, "the first call and two retries"


# ---- buy-out rules (docs/design/2026-09-27-civ6-levers-design.md, rulings 17-21) -----------------

BUY = SPEC.actions["purchase"]
WARRIOR = {"unit": "UNIT_WARRIOR", "gold": 160, "gold_allowed": True, "faith": 80, "faith_allowed": True}
ARCHER = {"unit": "UNIT_ARCHER", "gold": 240, "gold_allowed": True, "faith": 120, "faith_allowed": True}


def danger_city(**over) -> dict:
    """Beijing at T61: two barbarians next to it that can take it, no unit on its tile, no walls."""
    return _city0(**{"garrison": None, "capture_adjacent": 2, "enemies_near": 2, "threatened": True,
                     "defense": {"garrison_hp": 200, "garrison_max": 200, "walls_hp": 0, "walls_max": 0},
                     "defence_prices": [WARRIOR, ARCHER], **over})


def buy(*orders: dict, city: dict | None = None, **snap_over) -> list:
    s = {**FIXTURE, "gold": 400, "faith": 200, "cities": [city or danger_city()], **snap_over}
    return check_orders([Civ6Order(**o) for o in orders], s, SPEC, INDEX)


def test_danger_needs_more_than_an_enemy_nearby():
    from pilot.civ6 import in_danger
    lone = danger_city(capture_adjacent=0, enemies_near=1)
    assert not in_danger(lone), "a lone scout 3 tiles away"
    assert in_danger(danger_city()), "Beijing T61: 2 hostile melee next to it, no garrison"
    assert not in_danger(danger_city(capture_adjacent=1, garrison="UNIT_ARCHER")), "garrisoned, one attacker"
    assert in_danger(danger_city(capture_adjacent=0, enemies_near=3)), "Haarlem T51: 3 enemies, empty tile"
    assert in_danger(danger_city(capture_adjacent=0, enemies_near=0, defense={"garrison_hp": 150, "garrison_max": 200,
                                                                              "walls_hp": 0, "walls_max": 0}))
    assert not in_danger(_city0(threatened=True, enemies_near=1)), "old snapshot: today's test"
    assert in_danger(_city0(threatened=True, enemies_near=2)), "old snapshot: two enemies near"
    rich = {**FIXTURE, "gold": 400}
    assert purchase_cap(rich, lone, "gold", BUY) == 200
    assert purchase_cap(rich, danger_city(), "gold", BUY) == 400 - 30


def test_the_gold_reserve_grows_with_a_deficit():
    from pilot.civ6 import gold_reserve_now
    at = lambda g: gold_reserve_now({**FIXTURE, "yields": {**FIXTURE["yields"], "gold": g}}, BUY)
    assert (at(1.4), at(-1.6), at(0), at(-0.6)) == (30, 46, 30, 36)
    assert urgent_changes({**FIXTURE, "gold": 50}, {**FIXTURE, "gold": 40, "yields": {**FIXTURE["yields"], "gold": -1.6}},
                          gold_reserve=at(-1.6)) == ["gold below the reserve: 40 < 46"]


def test_what_the_city_finishes_anyway_is_not_bought():
    for left, refused in ((1, True), (2, True), (3, False)):
        out = buy({"kind": "purchase", "city": "Beijing", "id": "unit:archer"},
                  city=danger_city(producing="UNIT_ARCHER", turns_left=left))
        assert bool(out[0].error) == refused, left
    out = buy({"kind": "purchase", "city": "Beijing", "id": "unit:archer"},
              city=danger_city(producing="UNIT_SLINGER", turns_left=1))
    assert out[0].error == "Beijing finishes unit:slinger in 1 turn anyway", "a defender of the same class"
    out = buy({"kind": "purchase", "city": "Beijing", "id": "building:granary"})
    assert out[0].error == "Beijing cannot build building:granary now"
    out = buy({"kind": "purchase", "city": "Beijing", "id": "building:walls"})
    assert out[0].error == "building:walls cannot be bought: walls come from production"


def test_faith_keeps_the_pantheon_price_until_one_is_founded():
    rel = {"pantheon": None, "can_create_pantheon": True, "pantheon_cost": 25, "religion": None}
    out = buy({"kind": "purchase", "city": "Beijing", "id": "unit:warrior", "currency": "faith"},
              faith=83, religion=rel)
    assert out[0].wire is None, "refused before sending"
    assert out[0].error == "unit:warrior costs 80 faith in Beijing, over the 58 allowed: keeps 25 faith for the pantheon"
    ok = buy({"kind": "purchase", "city": "Beijing", "id": "unit:warrior", "currency": "faith"},
             faith=83, religion={**rel, "pantheon": "BELIEF_INITIATION_RITES", "can_create_pantheon": False})
    assert ok[0].wire["max_cost"] == 83
    old = buy({"kind": "purchase", "city": "Beijing", "id": "unit:warrior", "currency": "faith"}, faith=83)
    assert old[0].wire["max_cost"] == 83, "no religion block: the static reserve only"
    text = briefing_text({**FIXTURE, "faith": 83, "religion": rel}, INDEX, limits=BUY)
    assert "Pantheon: none (founding one costs 25 faith; purchases keeps 25 faith for the pantheon)" in text
    assert "83 faith (reserve 25)" in text
    assert "not in this snapshot (the pantheon reserve is off)" in briefing_text(FIXTURE, INDEX, limits=BUY)


def test_a_defender_for_a_city_in_danger_comes_first():
    out = buy({"kind": "purchase", "city": "Beijing", "id": "building:monument"},
              {"kind": "purchase", "city": "Beijing", "id": "unit:archer"},
              city=danger_city(defence_prices=[]))                         # prices unknown
    monument, archer = out
    assert archer.wire["max_cost"] == 400 - 30, "the Archer gets the cap of a city in danger"
    assert monument.error.startswith("gold 400 (less 370 for earlier purchases, the defender for Beijing first)")
    alone = buy({"kind": "purchase", "city": "Beijing", "id": "building:monument"})
    assert alone[0].error == "Beijing is in danger with no defender on its tile: buy a defender there first"


def test_a_gold_defender_is_bought_with_faith_when_the_game_allows_it():
    out = buy({"kind": "purchase", "city": "Beijing", "id": "unit:warrior"})
    assert out[0].wire["currency"] == "faith" and out[0].note == "bought with faith instead of gold: 80 faith rather than 160 gold"
    no_faith = danger_city(defence_prices=[{**WARRIOR, "faith_allowed": False}])
    out = buy({"kind": "purchase", "city": "Beijing", "id": "unit:warrior"}, city=no_faith)
    assert out[0].wire["currency"] == "gold" and not out[0].note
    poor = buy({"kind": "purchase", "city": "Beijing", "id": "unit:warrior"}, faith=50)
    assert poor[0].wire["currency"] == "gold", "the faith does not cover it"
    monument = buy({"kind": "purchase", "city": "Beijing", "id": "building:monument"},
                   city=danger_city(garrison="UNIT_WARRIOR"))
    assert monument[0].wire["currency"] == "gold", "other items keep the model's currency"


def test_a_land_unit_on_the_city_tile_blocks_another():
    out = buy({"kind": "purchase", "city": "Beijing", "id": "unit:archer"}, city=danger_city(garrison="UNIT_ARCHER"))
    assert out[0].error == "Beijing already has unit:archer on its tile: the game refuses a second land unit there"
    two = buy({"kind": "purchase", "city": "Beijing", "id": "unit:warrior"},
              {"kind": "purchase", "city": "Beijing", "id": "unit:archer"})
    assert two[0].wire and "second land unit" in two[1].error
    settler = buy({"kind": "purchase", "city": "Beijing", "id": "unit:settler"}, city=_city0(garrison="UNIT_ARCHER"))
    assert settler[0].wire, "a civilian shares the tile"


def test_one_defender_purchase_per_city_per_five_turns():
    s = {**FIXTURE, "gold": 400, "faith": 200, "cities": [danger_city()]}
    order = [Civ6Order(kind="purchase", city="Beijing", id="unit:warrior")]
    for last, refused in ((8, True), (7, False)):
        out = check_orders(order, s, SPEC, INDEX, defender_buys={"beijing": last})
        assert bool(out[0].error) == refused, last
    assert "got a defender at T8: the next defender purchase there waits until T13" in \
        check_orders(order, s, SPEC, INDEX, defender_buys={"beijing": 8})[0].error


def test_a_defender_ordered_into_production_is_bought_in_a_city_in_danger():
    out = buy({"kind": "production", "city": "Beijing", "id": "unit:warrior"})
    assert out[0].wire == {"kind": "purchase", "city": "Beijing", "id": "unit:warrior", "currency": "faith",
                           "max_cost": 200}
    assert out[0].note == "bought instead of queued (in danger): 80 faith"
    for city in (danger_city(garrison="UNIT_ARCHER"), danger_city(capture_adjacent=0, enemies_near=1),
                 danger_city(producing="UNIT_SLINGER", turns_left=2), danger_city(defence_prices=[])):
        kept = buy({"kind": "production", "city": "Beijing", "id": "unit:warrior"}, city=city)
        assert kept[0].wire == {"kind": "production", "city": "Beijing", "id": "unit:warrior"}, city
    settler = buy({"kind": "production", "city": "Beijing", "id": "unit:settler"})
    assert settler[0].wire["kind"] == "production", "only defenders"


def test_t83_replay_a_gold_warrior_is_bought_with_faith(setup):
    """Live T83: after Australia declared war and Xi'an was damaged, the model bought a Warrior for 160
    gold while holding 388 faith."""
    xian = {**danger_city(), "name": "Xi'an", "capital": False, "capture_adjacent": 0, "enemies_near": 1,
            "defense": {"garrison_hp": 150, "garrison_max": 200, "walls_hp": 0, "walls_max": 0}}
    base = {**FIXTURE, "turn": 83, "gold": 280, "faith": 388, "cities": [FIXTURE["cities"][0], xian],
            "religion": {"pantheon": "BELIEF_INITIATION_RITES", "can_create_pantheon": False, "pantheon_cost": 25}}
    prices = {("Xi'an", "unit:warrior", "gold"): 160, ("Xi'an", "unit:warrior", "faith"): 80}
    game = FakeCiv6(base, index=INDEX, prices=prices)
    g = governor(setup, game, orders_model([{"kind": "purchase", "city": "Xi'an", "id": "unit:warrior"}]))
    g.run(max_decisions=1)
    assert orders_sent(game) == [{"kind": "purchase", "city": "Xi'an", "id": "unit:warrior", "currency": "faith",
                                  "max_cost": 388}]
    assert (game.state["gold"], game.state["faith"]) == (280, 308)
    first = traces(setup)[0]["orders"][0]
    assert first["outcome"] == "stuck" and "bought with faith instead of gold: 80 faith rather than 160 gold" in first["order"]
    rows = [(e["key"], e["result"], e["id"]) for e in _events(setup) if e["kind"] == "order_outcome"]
    assert rows == [("purchase faith", "completed", "unit:warrior")]


def test_a_price_read_in_the_decision_refuses_a_purchase_over_the_cap(setup):
    calls = {"n": 0}

    def respond(messages, info):
        if is_review(info):
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,
                                                     {"change": False, "assessment": "n/a", "rules": []})])
        calls["n"] += 1
        if calls["n"] == 1:
            return ModelResponse(parts=[ToolCallPart("price", {"city": "Beijing", "item": "unit:slinger"})])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"orders": [
            {"kind": "purchase", "city": "Beijing", "id": "unit:slinger"}], "reason": "r"})])

    game = FakeCiv6({**FIXTURE, "gold": 400}, index=INDEX, prices={("Beijing", "unit:slinger", "gold"): 280,
                                                                   ("Beijing", "unit:slinger", "faith"): 140})
    g = governor(setup, game, FunctionModel(respond))
    g.run(max_decisions=1)
    assert [a[1]["currency"] for a in game.actions if a[0] == "order"] == ["gold", "faith"], "price shows both"
    assert all(a[1]["kind"] == "price" for a in game.actions if a[0] == "order"), "the purchase is never sent"
    assert traces(setup)[0]["orders"][0]["outcome"] == ("refused: unit:slinger costs 280 gold in Beijing, over the "
                                                        "200 allowed: one purchase takes at most 50% of the gold "
                                                        "balance (100% for a city in danger)")


def test_the_briefing_shows_a_city_in_danger_with_its_defence_and_prices():
    text = briefing_text({**FIXTURE, "cities": [danger_city(incoming=33)]}, INDEX, limits=BUY)
    assert ("IN DANGER: 2 enemy units within 3 tiles, 2 next to it that can take it; garrison 200/200, walls 0/0 "
            "(no walls: this city cannot strike; walls come from production); one attack from each enemy in range: "
            "about 33 damage; on its tile: no unit; defenders to buy: unit:warrior 160 gold / 80 faith, "
            "unit:archer 240 gold / 120 faith") in text
    assert "THREATENED: 1 enemy units" in briefing_text({**FIXTURE, "cities": [danger_city(capture_adjacent=0,
                                                                                          enemies_near=1)]}, INDEX)


def test_the_limits_text_names_the_purchase_rules(setup):
    g = governor(setup, FakeCiv6(FIXTURE, index=INDEX), orders_model([]))
    text = g._limits_text({**FIXTURE, "yields": {**FIXTURE["yields"], "gold": -1.6}})
    assert "Purchases keep 46 gold (30 + 10 per gold of deficit per turn) and 0 faith in reserve" in text
    assert "never what the city finishes within 2 turns anyway" in text and "walls cannot be bought" in text


def test_a_weak_production_replace_record_adds_the_buy_guidance(setup):
    seen: list[str] = []
    game = FakeCiv6(FIXTURE, index=INDEX)
    g = governor(setup, game, orders_model([], seen=seen))
    g._order_rows = [{"key": "production replace", "result": r, "turn": 5 + i, "id": "unit:slinger",
                      "by": "building:granary", "city": "Beijing", "date": f"T{5 + i}"}
                     for i, r in enumerate(["overridden", "overridden", "overridden", "completed"])]
    g.run(max_decisions=1)
    assert "does not stick here" in seen[0]
    assert "The AI replaced most production orders that replaced its own choice: buy what must exist now" in seen[0]


def test_with_known_prices_a_defender_and_another_purchase_both_fit():
    out = buy({"kind": "purchase", "city": "Beijing", "id": "building:monument"},
              {"kind": "purchase", "city": "Beijing", "id": "unit:archer", "currency": "gold"},
              city=danger_city(defence_prices=[{**ARCHER, "faith_allowed": False}]))
    monument, archer = out
    assert archer.wire["currency"] == "gold" and archer.wire["max_cost"] == 370
    assert monument.wire["max_cost"] == 130, "400 less the Archer's known 240, above the reserve of 30"


# ---- backfill of apply-time outcomes (ruling 13, check L4) -----------------------------------------

LIVE_TRACE_ORDERS = [      # shapes from the Kublai campaign's traces (T43-T129), before the record
    {"date": "T43", "orders": [{"order": "research tech:writing", "outcome": "stuck"}]},
    {"date": "T51", "orders": [{"order": "research tech:writing", "outcome": "refused: tech:writing cannot be researched now"}]},
    {"date": "T73", "orders": [{"order": "civic civic:drama_poetry", "outcome": "unknown: no reply (Error: Failed /tuner/lua)"}]},
    {"date": "T83", "orders": [{"order": "purchase unit:warrior in Xi’an with gold", "outcome": "stuck"},
                               {"order": "policies policy:agoge, policy:urban_planning", "outcome": "stuck"}]},
    {"date": "T85", "orders": [{"order": "production district:holy_site in Beijing", "outcome": "unknown: not read back (no snapshot)"}]},
    {"date": "T90", "orders": [{"order": "civic ", "outcome": "refused: unknown id ''"}]},
    {"date": "T104", "orders": [{"order": "production unit:trader in Chengdu", "outcome": "Chengdu builds BUILDING_PYRAMIDS"},
                                {"order": "purchase building:shrine in Beijing with faith", "outcome": "stuck"}]},
    {"date": "T140", "orders": [{"order": "research tech:x", "outcome": "stuck", "kind": "research"}]},   # the record's own
]


def test_the_backfill_recovers_apply_time_outcomes_only():
    from pilot.civ6 import backfill_rows
    rows = backfill_rows(LIVE_TRACE_ORDERS)
    got = [(r["date"], r["key"], r["id"], r["city"], r["result"]) for r in rows]
    assert got == [("T51", "research", "tech:writing", "", "refused"),
                   ("T73", "civic", "civic:drama_poetry", "", "lost"),
                   ("T83", "purchase gold", "unit:warrior", "Xi’an", "completed"),
                   ("T85", "production unknown", "district:holy_site", "Beijing", "unknown"),
                   ("T90", "civic", "", "", "refused"),
                   ("T104", "production unknown", "unit:trader", "Chengdu", "refused"),
                   ("T104", "purchase faith", "building:shrine", "Beijing", "completed")]
    assert all(r["backfilled"] and r["turn"] == int(r["date"][1:]) for r in rows)
    rec = order_record(rows, 110, ORDERS)
    assert rec["purchase gold"]["completed"] == 1 and rec["civic"]["excluded"]["refused"] == 1
    assert "production unknown" in rec, "shown while its rows are in the window"
    assert "research" not in rec, "refused at T51, outside the last 30 turns: nothing left to say"
    assert order_record(rows, 60, ORDERS)["research"]["excluded"]["refused"] == 1


def test_the_backfill_script_reads_only_until_asked_and_writes_once(tmp_path, capsys):
    import importlib.util

    from pilot.telemetry import Telemetry
    db = tmp_path / "t.sqlite"
    tel = Telemetry(db)
    tel.record("r1", {"t": 1.0, "kind": "run_start", "game": "civ6", "model": "m"})
    tel.record("r1", {"t": 1.0, "kind": "campaign", "game": "civ6", "name": "kublai"})
    for i, d in enumerate(LIVE_TRACE_ORDERS):
        tel.record("r1", {"t": 2.0 + i, "kind": "trace", "episode": i + 1, "date": d["date"], "decision": "orders"},
                   {"orders": d["orders"], "decision": "orders"})
    tel.close()
    spec = importlib.util.spec_from_file_location("backfill", REPO / "scripts/civ6-backfill-orders.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.main(["--db", str(db), "--campaign", "civ6/kublai"]) == 0
    assert "7 rows from 8 decisions" in capsys.readouterr().out
    assert Telemetry(db).campaign_events("civ6/kublai", "order_outcome") == [], "read-only by default"
    assert mod.main(["--db", str(db), "--campaign", "civ6/kublai", "--write"]) == 0
    rows = Telemetry(db).campaign_events("civ6/kublai", "order_outcome")
    assert [r["result"] for r in rows] == ["refused", "lost", "completed", "unknown", "refused", "refused", "completed"]
    assert mod.main(["--db", str(db), "--campaign", "civ6/kublai", "--write"]) == 1, "never twice"


# ---- review fixes ------------------------------------------------------------------------------

def test_a_city_that_cannot_get_a_defender_now_does_not_block_other_purchases():
    monument = {"kind": "purchase", "city": "Beijing", "id": "building:monument"}
    s = {**FIXTURE, "gold": 400, "faith": 200, "turn": 12, "cities": [danger_city()]}
    cooling = check_orders([Civ6Order(**monument)], s, SPEC, INDEX, defender_buys={"beijing": 10})
    assert cooling[0].wire, "its defender cooldown runs: nothing to buy there first"
    closed = buy(monument, city=danger_city(defence_prices=[{**WARRIOR, "gold_allowed": False, "faith_allowed": False}]))
    assert closed[0].wire, "no listed defender is allowed now"
    tried = buy({"kind": "purchase", "city": "Beijing", "id": "unit:warrior", "currency": "gold"}, monument,
                gold=100, faith=0)
    assert "over the 70 allowed" in tried[0].error and tried[1].wire, "the defender was tried and did not fit"
    assert "buy a defender there first" in buy(monument)[0].error


def test_a_unit_another_city_also_builds_is_not_read_as_completed():
    c = Checked(order={"kind": "production"}, expect={"city": "Beijing", "producing": "UNIT_TRADER"})
    base = {"turn": 100, "turns_left": 6, "count": 0, "others": 1}
    both = [_city0(producing="BUILDING_GRANARY"), {**_city0(), "name": "Chengdu", "producing": "UNIT_BUILDER"}]
    one_more = snap(102, cities=both, units={"by_type": {"UNIT_TRADER": 1}})
    assert held_outcome(c, base, one_more, 9) == ("unknown", "BUILDING_GRANARY"), "Chengdu's Trader, or ours?"
    two_more = snap(107, cities=both, units={"by_type": {"UNIT_TRADER": 2}})
    assert held_outcome(c, base, two_more, 9) == ("completed", None)
    from pilot.civ6 import order_base
    after = snap(100, cities=[_city0(producing="UNIT_TRADER", turns_left=6),
                              {**_city0(), "name": "Chengdu", "producing": "UNIT_TRADER"}])
    assert order_base(c, after)["others"] == 1


def test_the_pantheon_reserve_holds_below_its_price_and_stops_when_none_is_left():
    from pilot.civ6 import faith_reserve_now
    rel = {"pantheon": None, "pantheon_cost": 25}
    assert faith_reserve_now({"faith": 20, "religion": {**rel, "can_create_pantheon": False}}, BUY)[0] == 25
    assert faith_reserve_now({"faith": 90, "religion": {**rel, "can_create_pantheon": True}}, BUY)[0] == 25
    assert faith_reserve_now({"faith": 90, "religion": {**rel, "can_create_pantheon": False}}, BUY)[0] == 0, \
        "the game refuses a pantheon we could pay for: none is left"


def test_orders_still_followed_survive_a_restart(setup, tmp_path):
    from pilot.telemetry import Telemetry
    s, _ = setup
    tel = Telemetry(tmp_path / "t.sqlite")
    first = Civ6Governor(s, FakeCiv6(_replace_fixture(), index=INDEX), EventLog(s.runs_dir, "r1", s.model, telemetry=tel),
                         model=orders_model([{"kind": "production", "city": "Beijing", "id": "unit:slinger"}]))
    first.status_poll_s, first.start_grace_s = 0, 0.05
    first.run(max_decisions=1)
    assert len(first._tracking) == 1, "open when the run ends"
    ref = first._tracking[0].row["ref"]

    def ai(state):
        state["cities"][0]["producing"] = "BUILDING_GRANARY"

    after = {**_replace_fixture(), "cities": [_city0(producing="UNIT_SLINGER", turns_left=4)]}
    seen: list[str] = []
    second = Civ6Governor(s, FakeCiv6(after, index=INDEX, ai=ai), EventLog(s.runs_dir, "r2", s.model, telemetry=tel),
                          model=orders_model([], seen=seen))
    second.status_poll_s, second.start_grace_s = 0, 0.05
    second.run(max_decisions=2)
    assert "production unit:slinger in Beijing: replaced by the AI with building:granary by T13" in seen[1]
    rows = tel.campaign_events("civ6/kublai_khan_china_702403662", "order_outcome")
    assert [(r["ref"], r["result"]) for r in rows] == [(ref, "overridden")]
    third = Civ6Governor(s, FakeCiv6(after, index=INDEX), EventLog(s.runs_dir, "r3", s.model, telemetry=tel),
                         model=orders_model([]))
    third.status_poll_s, third.start_grace_s = 0, 0.05
    third.run(max_decisions=1)
    assert third._tracking == [], "a resolved order is not followed again"
