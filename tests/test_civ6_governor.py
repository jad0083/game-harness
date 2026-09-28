"""The Civilization VI governor loop against FakeCiv6 (ruling 4): decisions apply structured orders
and autoplay, orders are read back, urgent changes stop autoplay, invalid ids never reach the game,
purchases keep the reserve."""

import json
import shutil
import time

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from pilot.civ6 import (
    Checked,
    Civ6Order,
    CorpusIndex,
    FakeCiv6,
    _stand_apply,
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
    g.end_watch_s = 0
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


def run_briefly(g: Civ6Governor, max_decisions: int = 2, limit_s: float = 10.0) -> bool:
    """Run the governor for `max_decisions`; stop it if it waits for the human (then True)."""
    import threading
    import time
    t = threading.Thread(target=g.run, kwargs={"max_decisions": max_decisions}, daemon=True)
    t.start()
    end = time.time() + limit_s
    while t.is_alive() and g.log.state.status != "needs_attention" and time.time() < end:
        time.sleep(0.01)
    attention = g.log.state.status == "needs_attention"
    g.stop()
    t.join(5)
    return attention


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
        state["cities"] = state["cities"][:1]          # Xian falls (losing every city is the end: ruling 21)

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
    # a garrisoned city one burst from falling is not "in danger" (one capturer, undamaged), but it is
    # about to fall: single turns, so the hand-back checks it again every turn (amendment A1)
    from pilot.civ6 import about_to_fall, in_danger
    burst = {**lone_scout, "garrison": "UNIT_ARCHER", "enemies_near": 3, "capture_adjacent": 1, "incoming": 230}
    assert about_to_fall(burst) and not in_danger(burst)
    city_state_war = [{"civ": "CIVILIZATION_CAGUANA", "major": False}]
    assert autoplay_turns({"wars": city_state_war, "cities": [burst]}, chunk=3, left=10) == 1
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
    # without the unlocked cards (the options read failed) a replaced card may be an obsolete one the
    # game swapped out (invalidated) or the AI's choice (overridden): neither can be told
    assert held_outcome(c, base, snap(30, policy_slots=slots, options=None), 20) == ("unknown", None)
    no_cards = {k: v for k, v in FIXTURE["options"].items() if k != "policies"}
    assert held_outcome(c, base, snap(30, policy_slots=slots, options=no_cards), 20) == ("unknown", None)


def test_an_overridden_policy_names_only_the_cards_the_ai_slotted_since_the_order():
    """Cards already slotted when the order took (Discipline kept beside our God King) are not the
    AI's replacement; only newly slotted ones are."""
    from pilot.civ6 import order_base
    c = Checked(order={"kind": "policies"}, expect={"policies": ["POLICY_GOD_KING"]})
    took = snap(27, policy_slots=[{"policy": "POLICY_GOD_KING", "slot": 0}, {"policy": "POLICY_DISCIPLINE", "slot": 1}])
    base = order_base(c, took)
    assert base == {"turn": 27, "slots": ["POLICY_GOD_KING", "POLICY_DISCIPLINE"]}
    unlocked = {**FIXTURE["options"], "policies": ["POLICY_GOD_KING"]}
    swapped = [{"policy": "POLICY_SURVEY", "slot": 0}, {"policy": "POLICY_DISCIPLINE", "slot": 1}]
    assert held_outcome(c, base, snap(30, policy_slots=swapped, options=unlocked), 20) == ("overridden", "POLICY_SURVEY")
    emptied = [{"policy": None, "slot": 0}, {"policy": "POLICY_DISCIPLINE", "slot": 1}]
    assert held_outcome(c, base, snap(30, policy_slots=emptied, options=unlocked), 20) == ("overridden", None)
    # a row followed from before the order base kept the slots: every other slotted card, as before
    assert held_outcome(c, {"turn": 27}, snap(30, policy_slots=swapped, options=unlocked), 20) \
        == ("overridden", "POLICY_DISCIPLINE, POLICY_SURVEY")
    assert "slots" not in order_base(c, {**took, "policy_slots": None}), "no slots read: nothing to compare with"


def test_a_replacement_of_several_cards_is_named_by_corpus_ids(setup):
    from pilot.civ6_governor import Tracked
    g = governor(setup, FakeCiv6(FIXTURE, index=INDEX), orders_model([]))
    c = Checked(order={"kind": "policies", "ids": ["policy:god_king"]}, expect={"policies": ["POLICY_GOD_KING"]})
    t = Tracked(c, {"key": "policies", "id": "policy:god_king", "ordered": "T27"}, {"turn": 27}, 20)
    g._resolve(t, "overridden", "POLICY_DISCIPLINE, POLICY_SURVEY", snap(30))
    assert g._order_rows[-1]["by"] == "policy:discipline, policy:survey"


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


def test_ordering_what_the_city_already_builds_changes_nothing_and_stays_out_of_the_record(setup):
    """Ruling 14 keeps `production fill` (an empty queue, or the AI's item about to finish) apart from
    `production replace`. Ordering the item the city already builds is neither: it changes nothing,
    so it is not followed, gets no row, and does not end the following of our earlier order there."""
    from pilot.civ6 import order_situation
    archer = {**FIXTURE, "cities": [_city0(producing="UNIT_ARCHER", turns_left=5)]}
    assert order_situation(archer, "UNIT_ARCHER", "Beijing") == "current"
    assert order_situation(archer, "UNIT_SLINGER", "Beijing") == "replace"
    assert order_situation({**FIXTURE, "cities": [_city0(producing=None)]}, "UNIT_ARCHER", "Beijing") == "fill"
    seen: list[str] = []
    s, _ = setup
    s.decide_every_turns = 1
    slinger = {"kind": "production", "city": "Beijing", "id": "unit:slinger"}
    game = FakeCiv6(_replace_fixture(), index=INDEX)
    g = governor(setup, game, orders_model([slinger], [slinger], [], seen=seen))
    g.run(max_decisions=3)
    assert [o for o in orders_sent(game)] == [slinger, slinger]
    assert "production unit:slinger in Beijing: in force at T14 (2 of 7 turns followed)" in seen[2]
    events = _events(setup)
    assert len([e for e in events if e["kind"] == "order_followed"]) == 1
    assert [e for e in events if e["kind"] == "order_outcome"] == [], "no superseded row, no fill row"


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
    assert "Action record" not in prompts[0], "the Stellaris action record stays out of Civ VI reviews"


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


def test_an_idle_civic_and_research_are_filled_when_the_model_gives_no_answer(setup):
    """Ruling 16's fallback needs no model: a decision whose model call fails (an outage, the usage
    limit, every model of the pool) still fills an idle research or civic (E3: T57 needed a human)."""
    def down(messages, info: AgentInfo) -> ModelResponse:
        if is_review(info):
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,
                                                     {"change": False, "assessment": "n/a", "rules": []})])
        raise RuntimeError("model unavailable")

    game = FakeCiv6({**FIXTURE, "civic": None, "research": None}, index=INDEX)
    g = governor(setup, game, FunctionModel(down))
    g.run(max_decisions=1)
    assert orders_sent(game) == [{"kind": "research", "id": "tech:pottery"},
                                 {"kind": "civic", "id": "civic:craftsmanship"}], "the first offered of each"
    first = traces(setup)[0]
    assert first["outcome"] == "error" and "model unavailable" in first["error"]
    assert [o["order"] for o in first["orders"]] == ["research tech:pottery (filled by the governor)",
                                                     "civic civic:craftsmanship (filled by the governor)"]
    assert [o["outcome"] for o in first["orders"]] == ["stuck", "stuck"]
    assert "civic civic:craftsmanship (filled by the governor): carried out and read back" in g._report
    idle_only_civic = FakeCiv6({**FIXTURE, "civic": None}, index=INDEX)
    s, _ = setup
    g2 = governor((s, EventLog(s.runs_dir, "civ2", s.model)), idle_only_civic, FunctionModel(down))
    g2.run(max_decisions=1)
    assert orders_sent(idle_only_civic) == [{"kind": "civic", "id": "civic:craftsmanship"}], "research is running"


def test_a_resolved_order_is_reported_to_the_next_model_that_answers(setup):
    """A decision whose model call fails has shown nobody what became of earlier orders: those
    lines wait for the next decision that gets an answer."""
    prompts: list[str] = []
    calls = {"n": 0}

    def ai(state):
        state["cities"][0]["producing"] = "BUILDING_GRANARY"

    def flaky(messages, info: AgentInfo) -> ModelResponse:
        if is_review(info):
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,
                                                     {"change": False, "assessment": "n/a", "rules": []})])
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("model unavailable")
        prompts.append("\n".join(str(getattr(p, "content", "")) for m in messages for p in getattr(m, "parts", [])))
        orders = [{"kind": "production", "city": "Beijing", "id": "unit:slinger"}] if calls["n"] == 1 else []
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"orders": orders, "reason": "test"})])

    game = FakeCiv6(_replace_fixture(), index=INDEX, ai=ai)
    g = governor(setup, game, FunctionModel(flaky))
    g.run(max_decisions=3)
    assert calls["n"] == 3 and len(prompts) == 2
    assert traces(setup)[1]["outcome"] == "error"
    assert "production unit:slinger in Beijing: replaced by the AI with building:granary by T13" in prompts[1]
    assert g._resolved == [], "reported once it was shown"


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


def test_a_lost_start_is_sent_again_when_turn_ready_shows_only_a_popup_and_some_polls_go_unanswered(setup):
    # live 2026-09-27 T360: the reply was lost, the start never ran, turn-ready showed only an old
    # Civic Completed card and missed some polls; the run waited 20 minutes for a start that never came
    game = FakeCiv6(FIXTURE, index=INDEX, lost_start_not_run=1, popup=True, turn_ready_silent=2)
    g = governor(setup, game, orders_model([]))
    g.status_poll_s, g.start_grace_s, g.turn_deadline_s = 0.01, 0.05, 30.0
    assert not run_briefly(g), "waited for the human"
    events = (setup[0].runs_dir / "civ1" / "events.jsonl").read_text()
    assert "sent again (1 of 2)" in events
    assert game.state["turn"] >= FIXTURE["turn"] + 3


def test_a_lost_start_that_turn_ready_cannot_clear_stops_in_bounded_time(setup):
    import time
    game = FakeCiv6(FIXTURE, index=INDEX, lost_start_not_run=3, turn_ready_silent=1)
    g = governor(setup, game, orders_model([]))
    g.status_poll_s, g.start_grace_s, g.turn_deadline_s = 0.01, 0.05, 600.0
    t0 = time.time()
    assert run_briefly(g, limit_s=20.0), "an unclear lost start ends with the human"
    assert time.time() - t0 < 15, "not after the 600 s turn deadline"
    assert "did not start" in g.log.recent[-1].get("reason", "") or any(
        "did not start" in e.get("reason", "") for e in g.log.recent if e["kind"] == "needs_attention")


def test_a_start_that_never_runs_after_two_retries_waits_for_the_human(setup):
    game = FakeCiv6(FIXTURE, index=INDEX, lost_start_not_run=3)
    g = governor(setup, game, orders_model([]))
    run_until_attention(g)
    assert [a[0] for a in game.actions].count("autoplay") == 3, "the first call and two retries"


def test_a_lost_start_reply_read_as_not_started_is_never_sent_again_while_it_runs(setup):
    """The first answered poll after a lost start reply can land where autoplay reads inactive before
    its turn ends (seen live). A start is sent again only once turn-ready shows the game idle at the
    same turn; here it shows the turn handed back, so nothing is sent again."""
    game = FakeCiv6(FIXTURE, index=INDEX, lost_start_reply=True, blink=True)
    g = governor(setup, game, orders_model([]))
    g.status_poll_s, g.start_grace_s = 0.15, 0.05
    g.run(max_decisions=2)
    starts = [a for a in game.actions if a[0] == "autoplay"]
    assert all(not active for _, _, active in starts), f"an autoplay start went out while autoplay ran: {starts}"
    assert len(starts) == 3, "one start per turn: the lost one ran"
    assert game.state["turn"] == FIXTURE["turn"] + 3
    assert traces(setup)[1]["date"] == f"T{FIXTURE['turn'] + 3}"


class _StillPlaying(FakeCiv6):
    """A start whose reply was lost runs for `playing` more calls, during which autoplay-status reads
    inactive at the old turn (as before its last turn ends, seen live) and turn-ready reads `why`;
    then the turn is handed back."""

    def __init__(self, *a, playing: int = 0, why: str = "not our turn", **kw):
        super().__init__(*a, lost_start_reply=True, **kw)
        self.playing, self.why = playing, why

    def _still(self) -> bool:
        if not (self.active and self.playing > 0):
            return False
        self.playing -= 1
        if self.playing == 0:                      # the running start hands back
            self.active, self.remaining = False, 0
            self.state["turn"] += 1
        return True

    def autoplay_status(self) -> dict:
        if self._still():
            return {"ok": True, "active": False, "turns": 0, "turn": self.state["turn"] - (self.playing == 0)}
        return super().autoplay_status()

    def turn_ready(self) -> dict:
        active = self.active
        if self._still():
            self.actions.append(("turn_ready", active))
            return {"ok": True, "ready": False, "why": [self.why], "turn": self.state["turn"] - (self.playing == 0)}
        return super().turn_ready()


@pytest.mark.parametrize("why", ["not our turn", "turn already sent", "autoplay active",
                                 "cannot check: turn already sent"])
def test_a_lost_start_is_waited_for_while_turn_ready_says_the_game_plays(setup, why):
    game = _StillPlaying(FIXTURE, index=INDEX, playing=12, why=why)
    g = governor(setup, game, orders_model([]))
    g.status_poll_s, g.start_grace_s = 0.01, 0.02
    assert not run_briefly(g), "waited for the human"
    starts = [a for a in game.actions if a[0] == "autoplay"]
    assert all(not active for _, _, active in starts), starts
    assert len(starts) == 3, starts
    assert game.state["turn"] == FIXTURE["turn"] + 3


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
                          gold_reserve=at(-1.6)) == ["gold below the reserve: 40 < 46", "gold per turn negative: -1.6"]


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
    # the JSONL logs are the raw record: `pilot rebuild-telemetry` recreates the database from them alone,
    # so the backfilled rows must be in a run log of their own (next to the database by default)
    rebuilt = Telemetry(db)
    rebuilt.rebuild(tmp_path)
    again = rebuilt.campaign_events("civ6/kublai", "order_outcome")
    assert [(r["result"], r["date"]) for r in again] == [(r["result"], r["date"]) for r in rows], "kept by a rebuild"
    rebuilt.close()
    assert mod.main(["--db", str(db), "--campaign", "civ6/kublai", "--write"]) == 1, "still never twice"
    # run folders are named by their start time and the dashboard shows the newest first (its idle
    # feed shows runs[0]): the backfill run sorts at its earliest decision, behind every later real run
    from pilot.dashboard import RUN_ID, list_runs
    real = tmp_path / "20260927-080000"
    real.mkdir()
    (real / "events.jsonl").write_text("", encoding="utf-8")
    listed = [r["id"] for r in list_runs(tmp_path)]
    assert len(listed) == 2 and listed[0] == "20260927-080000", listed
    assert listed[1] == time.strftime("%Y%m%d-%H%M%S", time.localtime(2.0 + 1)) + "-backfill", "its first row: T51"
    assert RUN_ID.match(listed[1])


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


def test_a_city_finishing_its_own_defender_or_whose_defender_was_refused_does_not_block_purchases():
    """Ruling 20's skip rule refuses a defender the city finishes within 2 turns anyway, so defence
    first must not hold other purchases back for it (as `_must_have` already declines); and a
    defender purchase refused for any reason counts as tried for the city."""
    from pilot.civ6 import order_key
    warrior = {"kind": "purchase", "city": "Beijing", "id": "unit:warrior", "currency": "gold"}
    monument = {"kind": "purchase", "city": "Chengdu", "id": "building:monument"}
    chengdu = _city0(name="Chengdu", garrison="UNIT_ARCHER", producing="UNIT_SETTLER", turns_left=6)
    finishing = danger_city(producing="UNIT_WARRIOR", turns_left=1, defence_prices=[WARRIOR])
    s = {**FIXTURE, "gold": 400, "faith": 200, "cities": [finishing, chengdu]}
    both = check_orders([Civ6Order(**warrior), Civ6Order(**monument)], s, SPEC, INDEX)
    assert both[0].error == "Beijing finishes unit:warrior in 1 turn anyway"
    assert both[1].wire and not both[1].error, both[1].error
    alone = check_orders([Civ6Order(**monument)], s, SPEC, INDEX)
    assert alone[0].wire and not alone[0].error, alone[0].error
    two_left = {**s, "cities": [danger_city(producing="UNIT_ARCHER", turns_left=2), chengdu]}
    assert check_orders([Civ6Order(**monument)], two_left, SPEC, INDEX)[0].wire, "an Archer 2 turns out"
    three_left = {**s, "cities": [danger_city(producing="UNIT_ARCHER", turns_left=3), chengdu]}
    assert "buy a defender there first" in check_orders([Civ6Order(**monument)], three_left, SPEC, INDEX)[0].error
    # a defender refused because it did not stick at the last decision was still tried
    s2 = {**s, "cities": [danger_city(), chengdu]}
    refused = check_orders([Civ6Order(**warrior), Civ6Order(**monument)], s2, SPEC, INDEX,
                           {order_key(Civ6Order(**warrior).model_dump())})
    assert refused[0].error.startswith("did not stick at the last decision")
    assert refused[1].wire and not refused[1].error, refused[1].error


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


# ---- the last stand (docs/design/2026-09-27-civ6-levers-design.md, rulings 22-27) ----------------

FALLING = {"threatened": True, "enemies_near": 2, "capture_adjacent": 1, "garrison": None, "incoming": 30,
           "defense": {"garrison_hp": 80, "garrison_max": 200, "walls_hp": 0, "walls_max": 0}}
SAFE = {"threatened": False, "enemies_near": 0, "capture_adjacent": 0, "incoming": 0,
        "defense": {"garrison_hp": 200, "garrison_max": 200, "walls_hp": 0, "walls_max": 0}}
LS_ARCHER = {"id": 5, "owner": 0, "x": 22, "y": 22, "damage": 0, "moves": 2, "attacks": 1}
LS_BARB = {"id": 1, "owner": 63, "x": 23, "y": 21, "damage": 40, "moves": 2, "attacks": 1}
SHOT = {"action": "ranged_attack", "actor": "unit:5", "unit": "UNIT_ARCHER",
        "target": {"id": 1, "owner": 63, "type": "UNIT_WARRIOR", "x": 23, "y": 21, "hp": 60},
        "predicted_damage": 30, "predicted_kill": False}
T0 = FIXTURE["turn"]
STAND_CALLS = ("turn_ready", "ls_state", "stand", "finish_moves")


def falls(state):
    state["cities"][0].update(json.loads(json.dumps(FALLING)))


def recovers(state):
    state["cities"][0].update(json.loads(json.dumps(SAFE)))


def stand_game(events=None, **kw) -> FakeCiv6:
    """Beijing falls at T0+1 (the urgent decision) and recovers at T0+2, unless `events` says else."""
    return FakeCiv6(FIXTURE, index=INDEX, events=events or {T0 + 1: falls, T0 + 2: recovers},
                    ls={"me": 0, "units": [dict(LS_ARCHER), dict(LS_BARB)]}, **kw)


def stand_governor(setup, game, *answers, on=True, every=3) -> Civ6Governor:
    s, _ = setup
    s.last_stand, s.decide_every_turns = on, every
    g = governor(setup, game, orders_model(*(answers or ([],))))
    g.stand_pause_s = g.stand_idle_poll_s = 0
    return g


def after_order(game: FakeCiv6, n: int = 1) -> list:
    """The calls after the n-th order, by kind (and the stand's action)."""
    idx = [i for i, a in enumerate(game.actions) if a[0] == "order"][n - 1]
    return [a[0] if a[0] != "stand" else f"stand {a[2]}" for a in game.actions[idx + 1:]]


def never_while_autoplay_runs(game: FakeCiv6) -> bool:
    """(g) the invariant for every call the stand adds, as for orders: nothing while the AI plays."""
    return all(not a[-1] for a in game.actions if a[0] in (*STAND_CALLS, "order"))


def stand_rows(setup) -> list[tuple]:
    return [(e["key"], e["result"]) for e in _events(setup) if e["kind"] == "order_outcome" and e["key"].startswith("stand")]


def test_a_city_is_about_to_fall_only_when_it_can_be_taken_now():
    from pilot.civ6 import about_to_fall
    city = lambda **over: {**_city0(), **FALLING, **over}
    assert about_to_fall(city()), "worn down to 80/200, a capturer adjacent, no walls"
    assert not about_to_fall(city(capture_adjacent=0)), "nothing next to it that can take it"
    assert not about_to_fall(city(defense={**FALLING["defense"], "walls_hp": 50, "walls_max": 100})), "walls stand"
    assert about_to_fall(city(defense={**FALLING["defense"], "walls_hp": 0, "walls_max": 100})), "walls down"
    assert not about_to_fall(city(defense={**FALLING["defense"], "garrison_hp": 150}, incoming=100))
    assert about_to_fall(city(defense={**FALLING["defense"], "garrison_hp": 150}, incoming=150)), "burst"
    assert about_to_fall(city(defense={**FALLING["defense"], "garrison_hp": 100})), "exactly half"
    beijing_t61 = city(capture_adjacent=2, incoming=40, defense=SAFE["defense"])
    assert not about_to_fall(beijing_t61), "Beijing at T61: 200/200 with two capturers adjacent"
    scout = city(capture_adjacent=0, enemies_near=1, defense=SAFE["defense"])
    assert not about_to_fall(scout), "a lone scout"
    assert not about_to_fall(_city0(threatened=True, enemies_near=3, damaged=True)), "an old snapshot never falls"


def test_a_city_starting_to_fall_is_urgent_once():
    now = {**FIXTURE, "cities": [{**_city0(), **FALLING}]}
    assert any(u.startswith("city falling: Beijing (garrison 80/200, no walls, 1 unit(s) next to it")
               for u in urgent_changes(FIXTURE, now))
    assert not any(u.startswith("city falling") for u in urgent_changes(now, now)), "only on the transition"
    text = briefing_text(now, INDEX)
    assert "ABOUT TO FALL" in text


def test_a_stand_action_took_only_when_the_read_back_shows_it():
    from pilot.civ6 import stand_verdict
    before = {"me": 0, "units": [dict(LS_ARCHER), dict(LS_BARB)]}
    hit = {"me": 0, "units": [{**LS_ARCHER, "attacks": 0}, {**LS_BARB, "damage": 70}]}
    assert stand_verdict(SHOT, before, hit) == ("took", "target: 30 damage (predicted 30)")
    assert stand_verdict(SHOT, before, {"me": 0, "units": [{**LS_ARCHER, "attacks": 0}]})[0] == "took", "killed"
    assert stand_verdict(SHOT, before, before)[0] == "did_not_take"
    kept = {"me": 0, "units": [dict(LS_ARCHER), {**LS_BARB, "damage": 70}]}
    assert stand_verdict(SHOT, before, kept) == (
        "did_not_take", "the attacker kept its attack; target: 30 damage (predicted 30)")
    strike = {"action": "city_strike", "actor": "city:65536", "target": SHOT["target"], "predicted_damage": 20}
    assert stand_verdict(strike, before, hit)[0] == "took"
    back = {"action": "retreat", "actor": "unit:5", "to": {"x": 21, "y": 23}}
    assert stand_verdict(back, before, {"me": 0, "units": [{**LS_ARCHER, "x": 21, "y": 23}]}) == ("took", "on 21,23")
    assert stand_verdict(back, before, before)[0] == "did_not_take"
    assert stand_verdict(SHOT, before, None) == ("unknown", "no read-back")
    assert stand_verdict(None, before, hit)[0] == "took", "a lost reply is judged by any change"
    assert stand_verdict(None, before, before)[0] == "did_not_take"


def test_stand_actions_join_the_order_record():
    rows = _rows("stand ranged", ["took", "did_not_take", "took"]) + _rows("stand retreat", ["unknown"])
    rec = order_record(rows, 30, ORDERS)
    assert (rec["stand ranged"]["judged"], rec["stand ranged"]["rate"]) == (3, 0.67)
    assert rec["stand retreat"]["judged"] == 0 and rec["stand retreat"]["excluded"]["unknown"] == 1
    text = order_record_text(rec)
    assert "- stand ranged: 3 judged; 2 took, 1 did not take; held 67%" in text


def test_the_last_stand_is_off_by_default_and_capped_at_three(monkeypatch):
    assert (Settings().last_stand, Settings().last_stand_max) == (False, 3)
    monkeypatch.setenv("PILOT_LAST_STAND", "1")
    monkeypatch.setenv("PILOT_LAST_STAND_MAX", "2")
    s = Settings.from_env()
    assert (s.last_stand, s.last_stand_max) == (True, 2)
    monkeypatch.setenv("PILOT_LAST_STAND", "0")
    assert Settings.from_env().last_stand is False


def test_a_falling_city_gets_its_stand_between_the_urgent_decision_and_a_one_turn_hand_back(setup):
    """(a) urgent decision → orders read back → steps → pins → autoplay 1; (g) nothing is sent while
    autoplay runs."""
    game = stand_game(stand=[SHOT])
    g = stand_governor(setup, game, [], [{"kind": "research", "id": "tech:pottery"}], [])
    g.run(max_decisions=3)
    urgent = traces(setup)[1]
    assert "city falling: Beijing" in urgent["trigger"]
    assert [o["outcome"] for o in urgent["orders"]] == ["stuck"], "the model's orders are read back first"
    assert after_order(game)[:9] == ["turn_ready", "ls_state", "stand ranged_attack", "ls_state", "turn_ready",
                                     "stand done", "finish_moves", "turn_ready", "autoplay"]
    hand_back = [a for a in game.actions if a[0] == "autoplay"][1]
    assert hand_back == ("autoplay", 1, False), "one turn: the AI plays the rest of the turn"
    turns = [e for e in _events(setup) if e["kind"] == "turn"]
    assert (turns[1]["turn"], turns[1]["turns"]) == (T0 + 2, 1), "the turn advanced by exactly one"
    assert never_while_autoplay_runs(game), "(g)"
    assert stand_rows(setup) == [("stand ranged", "took"), ("stand pin", "took")]
    stand = next(e for e in _events(setup) if e["kind"] == "last_stand")
    assert stand["stopped"] == "done: nothing left to do" and stand["pins"] == [{"id": 5, "x": 22, "y": 22}]
    assert [a["action"] for a in stand["actions"]] == ["ranged_attack", "pin"]
    assert sum(1 for a in game.actions if a[0] == "stand") == 2, "one stand: the city recovered at T0+2"
    s, _ = setup
    assert "Last stand for Beijing (stand 1 in a row): ranged_attack took" in s.journal.read_text()


def test_without_the_setting_a_falling_city_only_autoplays(setup):
    """(b) off by default: no new call at all."""
    game = stand_game(stand=[SHOT])
    g = stand_governor(setup, game, [], [{"kind": "research", "id": "tech:pottery"}], [], on=False)
    g.run(max_decisions=3)
    assert "city falling: Beijing" in traces(setup)[1]["trigger"], "the urgent decision still runs"
    assert {a[0] for a in game.actions} <= {"order", "autoplay", "autoplay_stop", "ai_strategies"}
    assert [a for a in game.actions if a[0] == "autoplay"] == [("autoplay", 1, False)] * 4


def test_an_ignored_first_action_stops_the_stand_and_still_hands_back(setup):
    """(c)"""
    game = stand_game(stand=[SHOT, SHOT], stand_ignored=True)
    g = stand_governor(setup, game)
    g.run(max_decisions=3)
    assert never_while_autoplay_runs(game)
    calls = [a[0] if a[0] != "stand" else f"stand {a[2]}" for a in game.actions]
    i = calls.index("stand ranged_attack")
    assert calls[i:i + 4] == ["stand ranged_attack", "ls_state", "turn_ready", "autoplay"], "stopped at once"
    assert stand_rows(setup) == [("stand ranged", "did_not_take")]
    stand = next(e for e in _events(setup) if e["kind"] == "last_stand")
    assert stand["stopped"].startswith("ranged_attack did not take: the attacker kept its attack")
    assert not any(e["kind"] == "last_stand_off" for e in _events(setup)), "one failure is not enough"


def test_two_ignored_first_actions_turn_the_stand_off_for_the_run(setup):
    """(d) the circuit breaker: the next falling turn only autoplays."""
    game = stand_game(events={T0 + 1: falls}, stand=[SHOT] * 5, stand_ignored=True)
    g = stand_governor(setup, game, every=4)
    g.run(max_decisions=3)
    assert never_while_autoplay_runs(game)
    assert [a[2] for a in game.actions if a[0] == "stand"] == ["ranged_attack", "ranged_attack"]
    off = [e for e in _events(setup) if e["kind"] == "last_stand_off"]
    assert len(off) == 1 and off[0]["reason"].startswith("the first action of 2 stands did not take")
    s, _ = setup
    assert "Last stand turned off for this run" in s.journal.read_text()
    autoplays = [a for a in game.actions if a[0] == "autoplay"]
    assert len(autoplays) == 5 and all(a == ("autoplay", 1, False) for a in autoplays)


def test_a_lost_reply_is_never_sent_again(setup):
    """(e) the action ran but its reply was lost: read back, recorded, and the stand ends."""
    game = stand_game(stand=[SHOT, SHOT], stand_lost_reply=True)
    g = stand_governor(setup, game)
    g.run(max_decisions=3)
    assert never_while_autoplay_runs(game)
    assert [a[2] for a in game.actions if a[0] == "stand"] == ["ranged_attack"]
    assert stand_rows(setup) == [("stand lost reply", "took")]
    stand = next(e for e in _events(setup) if e["kind"] == "last_stand")
    assert "not sent again" in stand["stopped"] and stand["pins"] == []


def test_after_three_stands_in_a_row_the_ai_defends_alone(setup):
    """(f)"""
    game = stand_game(events={T0 + 1: falls})
    g = stand_governor(setup, game, every=5)
    g.run(max_decisions=3)
    assert never_while_autoplay_runs(game)
    assert [a[2] for a in game.actions if a[0] == "stand"] == ["done"] * 3
    s, _ = setup
    journal = s.journal.read_text()
    assert journal.count("has had 3 stands in a row (the limit)") == 1
    assert game.state["turn"] == T0 + 6, "T0+1..T0+3 with a stand, T0+4 and T0+5 without"


def test_stands_that_never_reached_the_game_do_not_use_up_the_limit(setup):
    """Ruling 22's cap bounds scripted stands: a stand stopped before its first step (a popup at the
    hand-back, seen live at T207, or no GameCore read) ran nothing and does not count."""
    game = stand_game(events={T0 + 1: falls}, popup=True)
    game.events[T0 + 4] = lambda state: setattr(game, "popup", False)       # the popups are gone at T0+4
    g = stand_governor(setup, game, every=5)
    g.run(max_decisions=3)
    assert never_while_autoplay_runs(game)
    steps = [(a[1], a[2]) for a in game.actions if a[0] == "stand"]
    assert steps == [(FIXTURE["cities"][0]["id"], "done")] * 2, "T0+4 and T0+5 still get their stands"
    s, _ = setup
    journal = s.journal.read_text()
    assert "stands in a row (the limit)" not in journal
    assert journal.count("(not counted toward the limit: nothing ran)") == 3
    assert "Last stand for Beijing (stand 2 in a row)" in journal


def test_the_action_cap_and_the_time_budget_stop_a_stand(setup):
    """(h) at most 8 actions per stand, and 90 s."""
    archers = [{**LS_ARCHER, "id": i} for i in range(5, 15)]
    shots = [{**SHOT, "actor": f"unit:{i}", "predicted_damage": 5} for i in range(5, 15)]
    game = FakeCiv6(FIXTURE, index=INDEX, events={T0 + 1: falls, T0 + 2: recovers},
                    ls={"me": 0, "units": [*archers, dict(LS_BARB)]}, stand=shots)
    g = stand_governor(setup, game)
    g.run(max_decisions=3)
    assert never_while_autoplay_runs(game)
    assert sum(1 for a in game.actions if a[0] == "stand") == 8
    assert sum(1 for a in game.actions if a[0] == "finish_moves") == 8
    stand = next(e for e in _events(setup) if e["kind"] == "last_stand")
    assert stand["stopped"] == "8 actions (the limit)"


def test_the_time_budget_stops_a_stand(setup):
    game = stand_game(stand=[SHOT, {**SHOT, "actor": "unit:6"}])
    g = stand_governor(setup, game)
    clock = iter(range(0, 10_000, 50))
    g._now = lambda: next(clock)
    g.run(max_decisions=3)
    assert [a[2] for a in game.actions if a[0] == "stand"] == ["ranged_attack"]
    stand = next(e for e in _events(setup) if e["kind"] == "last_stand")
    assert stand["stopped"] == "the 90 s budget ran out"
    assert not any(a[0] == "finish_moves" for a in game.actions), "no pins after the budget"


def test_a_popup_means_no_action_and_a_hand_back(setup):
    """(i) turn-ready fails: nothing is sent; autoplay takes the turn after a few polls."""
    game = stand_game(stand=[SHOT], popup=True)
    g = stand_governor(setup, game)
    g.run(max_decisions=3)
    assert never_while_autoplay_runs(game)
    calls = [a[0] for a in game.actions]
    assert "stand" not in calls and "ls_state" not in calls
    i = calls.index("turn_ready")
    assert calls[i:i + 6] == ["turn_ready"] * 6 and calls[i + 6] == "autoplay", "1 check, 5 polls, then autoplay"
    stand = next(e for e in _events(setup) if e["kind"] == "last_stand")
    assert stand["stopped"].startswith("not ready: on screen: TechCivicCompletedPopup; nothing sent")


def test_no_game_core_read_means_no_action(setup):
    game = stand_game(stand=[SHOT], ls_fails=1)
    g = stand_governor(setup, game)
    g.run(max_decisions=3)
    assert never_while_autoplay_runs(game)
    assert not any(a[0] == "stand" for a in game.actions)
    stand = next(e for e in _events(setup) if e["kind"] == "last_stand")
    assert stand["stopped"] == "no GameCore read before the first action: nothing sent"
    assert [a for a in game.actions if a[0] == "autoplay"][1] == ("autoplay", 1, False)


def recorded_snapshots(game: FakeCiv6) -> FakeCiv6:
    """Record every snapshot in `game.actions` as ("snapshot", turn, active)."""
    take = game.snapshot

    def snapshot():
        game.actions.append(("snapshot", game.state["turn"], game.active))
        return take()
    game.snapshot = snapshot
    return game


def test_a_turn_that_moved_on_during_the_stand_is_not_handed_back_again(setup):
    """The stand stops on 'the turn changed': turn T is over, so there is nothing to hand back. An
    autoplay start for T would play T+1 while the wait accepted its first reading: the loop takes a
    fresh snapshot instead."""
    def moved_on(ls, reply):
        _stand_apply(ls, reply)
        game.state["turn"] += 1                         # the turn ended during the stand (not by us)
    game = recorded_snapshots(stand_game(stand=[SHOT], stand_effect=moved_on))
    g = stand_governor(setup, game)
    g.run(max_decisions=3)
    assert never_while_autoplay_runs(game)
    stand = next(e for e in _events(setup) if e["kind"] == "last_stand")
    assert stand["stopped"] == "the turn changed"
    calls = [a[0] if a[0] != "stand" else f"stand {a[2]}" for a in game.actions]
    i = calls.index("stand ranged_attack")
    assert calls[i:i + 4] == ["stand ranged_attack", "ls_state", "turn_ready", "snapshot"], calls[i:i + 6]
    assert game.actions[i + 3][1] == T0 + 2, "the snapshot at the turn the game is on"


class _Lingering(FakeCiv6):
    """Turn-ready reads `why` for `lingering` more calls (autoplay still running from before the
    stand, or the turn already sent); records whether autoplay was started meanwhile."""

    def __init__(self, *a, why: str = "autoplay active", **kw):
        super().__init__(*a, **kw)
        self.lingering, self.why, self.started_while_lingering = 0, why, False

    def turn_ready(self) -> dict:
        if self.lingering > 0:
            self.lingering -= 1
            self.actions.append(("turn_ready", self.active))
            return {"ok": True, "ready": False, "why": [self.why], "turn": self.state["turn"]}
        return super().turn_ready()

    def autoplay(self, turns: int) -> dict:
        self.started_while_lingering |= self.lingering > 0
        return super().autoplay(turns)


@pytest.mark.parametrize("why", ["autoplay active", "turn already sent"])
def test_the_hand_back_never_starts_autoplay_while_turn_ready_says_a_turn_is_playing(setup, why):
    game = _Lingering(FIXTURE, index=INDEX, why=why, ls={"me": 0, "units": [dict(LS_ARCHER), dict(LS_BARB)]})

    def falls_while_playing(state):
        falls(state)
        game.lingering = 9                              # 1 for the stand's check, 8 for the hand-back
    game.events = {T0 + 1: falls_while_playing, T0 + 2: recovers}
    g = stand_governor(setup, game)
    g.run(max_decisions=3)
    stand = next(e for e in _events(setup) if e["kind"] == "last_stand")
    assert stand["stopped"] == f"not ready: {why}; nothing sent"
    assert not game.started_while_lingering, "autoplay started while turn-ready said a turn is playing"
    assert game.lingering == 0 and game.state["turn"] == T0 + 4, "decisions at T0, T0+1 (falling) and T0+4"
    assert [a for a in game.actions if a[0] == "autoplay"][1] == ("autoplay", 1, False), "then the hand-back"


def test_a_pinned_unit_the_hand_back_moved_is_noted(setup):
    def moved(state):
        recovers(state)
        state["cities"][0]["defenders"] = [{"id": 5, "x": 20, "y": 22}]
    game = stand_game(events={T0 + 1: falls, T0 + 2: moved}, stand=[SHOT])
    g = stand_governor(setup, game)
    g.run(max_decisions=3)
    assert never_while_autoplay_runs(game)
    check = next(e for e in _events(setup) if e["kind"] == "last_stand_check")
    assert check["pins"][0]["result"] == "moved" and check["pins"][0]["now"] == {"x": 20, "y": 22}
    s, _ = setup
    assert "the hand-back moved pinned unit(s) 5 (22,22 → 20,22): pins do not hold" in s.journal.read_text()


def test_the_controller_wrapper_runs_the_last_stand_subcommands(tmp_path):
    from pilot.civ6 import ControllerCiv6, GameRefused
    stub = tmp_path / "game-controller"
    log = tmp_path / "args.txt"
    stub.write_text(f"""#!/bin/sh
printf '%s\\n' "$@" >> {log}
case "$4" in
  turn-ready) echo '{{"ok":true,"ready":false,"why":["engine busy"],"turn":7}}' ;;
  ls-state) echo '{{"ok":true,"turn":7,"me":0,"units":[]}}' ;;
  last-stand-step) echo '{{"ok":false,"error":"not ready: engine busy"}}'; exit 2 ;;
  finish-moves) echo '{{"ok":false,"error":"no unit of ours with ID 9"}}'; exit 2 ;;
esac
""")
    stub.chmod(0o755)
    game = ControllerCiv6(stub, tmp_path / "civ6", "http://pc:8765", tmp_path, token="t" * 32)
    assert game.turn_ready()["why"] == ["engine busy"]
    assert game.ls_state(65536)["units"] == []
    assert game.last_stand_step(65536, {"63:1": 40}, ["city:65536", "unit:5"]) == {"ok": False,
                                                                                   "error": "not ready: engine busy"}
    with pytest.raises(GameRefused):
        game.finish_moves(9)
    args = log.read_text().splitlines()
    i = args.index("last-stand-step")
    assert args[i:i + 6] == ["last-stand-step", "65536", "--damage", '{"63:1": 40}', "--skip", "city:65536,unit:5"]
    assert args[args.index("ls-state") + 1] == "65536" and args[args.index("finish-moves") + 1] == "9"



# ---- the AI's intent (docs/design/2026-09-27-civ6-levers-design.md, ruling 29) -------------------

AI_LOG = [(1, 0, "STRATEGY_EARLY_EXPLORATION", "Following"), (1, 1, "STRATEGY_EARLY_EXPLORATION", "Following"),
          (6, 0, "VICTORY_STRATEGY_RELIGIOUS_VICTORY", "Following"), (11, 0, "VICTORY_STRATEGY_SCIENCE_VICTORY", "Following"),
          (33, 0, "STRATEGY_EARLY_EXPLORATION", "Stopped"), (36, 0, "VICTORY_STRATEGY_SCIENCE_VICTORY", "Stopped"),
          (56, 0, "VICTORY_STRATEGY_SCIENCE_VICTORY", "Following"), (76, 0, "VICTORY_STRATEGY_SCIENCE_VICTORY", "Stopped")]
RECOMMEND = [{"type": "DISTRICT_HOLY_SITE", "score": 729}, {"type": "DISTRICT_CAMPUS", "score": 669},
             {"type": "BUILDING_ORACLE", "score": 632}]


def test_the_ais_strategies_are_read_from_its_log():
    from pilot.civ6 import ai_strategy_states
    rows = [[turn, name, status] for turn, who, name, status in AI_LOG if who == 0]
    st = ai_strategy_states(rows)
    assert st["VICTORY_STRATEGY_SCIENCE_VICTORY"] == {"status": "Stopped", "since": 56, "stopped": 76}
    assert st["VICTORY_STRATEGY_RELIGIOUS_VICTORY"] == {"status": "Following", "since": 6, "stopped": None}
    assert st["STRATEGY_EARLY_EXPLORATION"] == {"status": "Stopped", "since": 1, "stopped": 33}


def test_the_briefing_shows_the_ais_own_plan():
    from pilot.civ6 import ai_plan_text, ai_strategy_states
    rows = [[turn, name, status] for turn, who, name, status in AI_LOG if who == 0]
    s = {**FIXTURE, "turn": 80, "cities": [_city0(recommend=RECOMMEND), {**_city0(), "name": "Xi'an", "recommend": []}]}
    text = ai_plan_text(s, INDEX, ai_strategy_states(rows))
    assert text == ("The AI's own plan: Beijing → district:holy_site, district:campus, wonder:oracle; strategies: "
                    "religious victory (since T6), science victory (since T56, stopped T76).")
    assert "early exploration" not in text, "stopped more than 30 turns ago"
    eras = rows + [[1, "STRATEGY_ANCIENT_CHANGES", "Following"], [81, "STRATEGY_CLASSICAL_CHANGES", "Following"]]
    shown = ai_plan_text(s, INDEX, ai_strategy_states(eras))
    assert "classical changes (since T81)" in shown and "ancient changes" not in shown, "only the latest era's"
    assert text in briefing_text(s, INDEX, strategies=ai_strategy_states(rows))
    assert ai_plan_text(FIXTURE, INDEX, {}) == "", "an old snapshot and no log: no line"


def test_each_decision_reads_the_ai_log_once_from_where_it_stopped(setup):
    seen: list[str] = []
    base = {**FIXTURE, "cities": [_city0(recommend=RECOMMEND)]}
    game = FakeCiv6(base, index=INDEX, ai_log=AI_LOG[:4])
    g = governor(setup, game, orders_model([], seen=seen))

    def more(state):
        game.ai_log += AI_LOG[4:]
    game.events[T0 + 2] = more
    g.run(max_decisions=2)
    reads = [a for a in game.actions if a[0] == "ai_strategies"]
    assert reads == [("ai_strategies", 0, False), ("ai_strategies", 4, False)], "one read per decision, from the last end"
    assert "The AI's own plan: Beijing → district:holy_site, district:campus, wonder:oracle; strategies: religious " \
           "victory (since T6), science victory (since T11), early exploration (since T1)." in seen[0]
    assert "science victory (since T56, stopped T76)" in seen[1]


def test_a_failed_log_read_leaves_the_decision_alone(setup):
    game = FakeCiv6({**FIXTURE, "cities": [_city0(recommend=RECOMMEND)]}, index=INDEX)
    game.ai_strategies = lambda offset, player: (_ for _ in ()).throw(RuntimeError("HTTP 404"))
    seen: list[str] = []
    g = governor(setup, game, orders_model([], seen=seen))
    g.run(max_decisions=1)
    assert "The AI's own plan: Beijing → district:holy_site" in seen[0]
    assert any(e["kind"] == "briefing_error" and "AI strategy log" in e["error"] for e in _events(setup))


def test_an_override_records_whether_the_ai_took_its_own_top_three(setup):
    """top3_hit: was the AI's replacement in the city's top 3 when we ordered?"""
    recs = [{"type": "BUILDING_GRANARY", "score": 700}, {"type": "UNIT_SETTLER", "score": 650},
            {"type": "UNIT_ARCHER", "score": 500}]
    base = {**_replace_fixture(), "cities": [_city0(producing="UNIT_WARRIOR", turns_left=5, recommend=recs)]}

    def ai(state):
        state["cities"][0]["producing"] = "BUILDING_GRANARY"
    seen: list[str] = []
    game = FakeCiv6(base, index=INDEX, ai=ai)
    g = governor(setup, game, orders_model([{"kind": "production", "city": "Beijing", "id": "unit:slinger"}], [],
                                           seen=seen))
    g.run(max_decisions=2)
    rows = [e for e in _events(setup) if e["kind"] == "order_outcome"]
    assert [(r["result"], r["by"], r["top3_hit"], r["top3"]) for r in rows] == [
        ("overridden", "building:granary", True, ["building:granary", "unit:settler", "unit:archer"])]
    assert "the AI's replacement was in the city's own top 3 builds (at order time) 1 of 1 times" in seen[1]
    no_recs = order_row_top3(setup, [])
    assert no_recs is None, "an empty recommendation list is unknown, not a miss"
    from pilot.civ6 import top3_hits
    assert top3_hits([*rows, {"result": "overridden", "top3_hit": False}, {"result": "completed", "top3_hit": None}]) \
        == (1, 2)



def order_row_top3(setup, recs):
    """The top 3 a production order's row keeps when the city's recommendations are `recs`."""
    from pilot.civ6 import Checked
    g = governor(setup, FakeCiv6(FIXTURE, index=INDEX), orders_model([]))
    b = {**FIXTURE, "cities": [_city0(recommend=recs)]}
    c = Checked(order={"kind": "production", "city": "Beijing", "id": "unit:slinger"},
                wire={"kind": "production", "city": "Beijing", "id": "unit:slinger"})
    return g._order_row(c, b, "replace")["top3"]


def test_a_start_that_times_out_recovers_without_a_human(setup, monkeypatch):
    # live 2026-09-27: the service restarted while the AI still played the last stretch; the first
    # snapshot timed out and the run waited for a human although the tuner answered seconds later
    game = FakeCiv6(FIXTURE, index=INDEX)
    real, n = game.snapshot, {"calls": 0}

    def flaky():
        n["calls"] += 1
        if n["calls"] == 1:
            raise RuntimeError("game-controller civ6 snapshot failed (exit 1): operation timed out")
        return real()

    monkeypatch.setattr(game, "snapshot", flaky)
    g = governor(setup, game, orders_model([]))
    g.recover_every_s = 0
    g.run(max_decisions=1)
    kinds = [e["kind"] for e in g.log.recent]
    assert "needs_attention" in kinds and "recovered" in kinds, kinds
    assert traces(setup)[0]["trigger"] == "start of run", "the start was tried again by itself"


def test_a_start_that_fails_for_another_reason_still_waits_for_the_human(setup, monkeypatch):
    import threading
    game = FakeCiv6(FIXTURE, index=INDEX)
    monkeypatch.setattr(game, "snapshot", lambda: (_ for _ in ()).throw(RuntimeError("no game loaded")))
    g = governor(setup, game, orders_model([]))
    g.recover_every_s = 0
    t = threading.Thread(target=g.run, kwargs={"max_decisions": 1}, daemon=True)
    t.start()
    t.join(2)
    assert g.log.state.status == "needs_attention" and not any(e["kind"] == "recovered" for e in g.log.recent)
    g.control.stopping = True
    t.join(5)


# ---- the diplomacy auto-reply (issues.md T240, T342) ----------------------------------------------
# The library answers an AI leader's statement during autoplay and logs it in the snapshot's
# `diplomacy` (the last 20); the governor turns each new answer into one `diplomacy_reply` event and
# the briefing says what was answered for us.

def _dipl(*entries, handler: bool = True) -> dict:
    return {"handler": handler, "log": [dict(e) for e in entries]}


_T240 = ({"n": 1, "turn": 13, "at": 13, "from": 3, "civ": "CIVILIZATION_AUSTRALIA", "session": 7,
          "kind": "WARNING_TOO_MANY_TROOPS_NEAR_ME", "sub": "NONE", "reply": "POSITIVE", "why": "table"},
         {"n": 2, "turn": 13, "at": 13, "from": 3, "civ": "CIVILIZATION_AUSTRALIA", "session": 7,
          "kind": "WARNING_TOO_MANY_TROOPS_NEAR_ME", "sub": "POSITIVE", "reply": "EXIT", "why": "follow-up"})
_WAITING = {"n": 3, "turn": 13, "from": 3, "civ": "CIVILIZATION_AUSTRALIA", "session": 9, "kind": "MAKE_PEACE",
            "sub": "NONE", "why": "waiting"}


def _diplomacy_line(s: dict) -> str | None:
    return next((line for line in briefing_text(s, INDEX).splitlines() if line.startswith("Diplomacy")), None)


def test_the_briefing_says_what_was_answered_for_us():
    line = _diplomacy_line({**FIXTURE, "diplomacy": _dipl(*_T240, _WAITING)})
    assert line is not None
    assert "never war" in line and "no deal accepted" in line
    assert "T13 civ:australia warning too many troops near me: the conciliatory reply (a promise)" in line
    assert "T13 civ:australia warning too many troops near me (positive follow-up): Goodbye" in line
    assert "T13 civ:australia make peace: waiting for the next autoplay" in line


def test_the_briefing_names_refusals_failures_and_sessions_closed_before_an_answer():
    line = _diplomacy_line({**FIXTURE, "diplomacy": _dipl(
        {"n": 1, "turn": 13, "at": 13, "from": 4, "civ": "CIVILIZATION_ROME", "session": 1, "kind": "MAKE_DEAL",
         "sub": "NONE", "reply": "REFUSE", "why": "table"},
        {"n": 2, "turn": 13, "at": 14, "from": 4, "civ": "CIVILIZATION_ROME", "session": 2, "kind": "DENOUNCE",
         "sub": "NONE", "reply": "EXIT", "why": "table", "late": True, "err": "the session is gone"},
        {"n": 3, "turn": 13, "from": 4, "civ": "CIVILIZATION_ROME", "session": 3, "kind": "OPEN_BORDERS", "sub": "NONE",
         "why": "gone"},
        {"n": 4, "turn": 14, "at": 14, "from": 4, "civ": "CIVILIZATION_ROME", "session": 4, "kind": "NEW_THING",
         "sub": "NONE", "reply": "EXIT", "why": "unknown"},
        {"n": 5, "turn": 14, "from": 4, "civ": "CIVILIZATION_ROME", "kind": "DENOUNCE", "sub": "NONE",
         "why": "no session"})})
    assert "civ:rome make deal: refused" in line
    assert "civ:rome denounce: Goodbye (at T14, when autoplay started; failed: the session is gone)" in line
    assert "civ:rome open borders: closed before an answer" in line
    assert "civ:rome new thing: Goodbye (an unknown statement)" in line
    assert "T14 civ:rome denounce: not answered (its session could not be read)" in line


def test_the_briefing_says_goodbye_was_sent_after_a_failed_reply():
    line = _diplomacy_line({**FIXTURE, "diplomacy": _dipl(
        {**_T240[0], "err": "the session is gone", "closed": True})})
    assert "the conciliatory reply (a promise) (failed: the session is gone; Goodbye sent instead)" in line


def test_the_briefing_names_the_goodbye_sent_when_autoplay_started():
    """The library closes a session our answer left open (no follow-up came) when autoplay next starts."""
    line = _diplomacy_line({**FIXTURE, "diplomacy": _dipl(
        {"n": 5, "turn": 13, "at": 14, "from": 4, "civ": "CIVILIZATION_ROME", "session": 1, "kind": "MAKE_DEAL",
         "sub": "NONE", "reply": "EXIT", "why": "sweep"})})
    assert "T13 civ:rome make deal: Goodbye (the session our answer left open, closed at T14 when autoplay started)" \
        in line


def test_the_briefing_leaves_out_answers_older_than_ten_turns_but_never_a_waiting_one():
    old = {**_T240[0], "turn": 1, "at": 1}
    waiting = {**_WAITING, "turn": 1}
    assert _diplomacy_line({**FIXTURE, "diplomacy": _dipl(old)}) is None, "T1 at T12: over ten turns ago"
    assert "T2 civ:australia" in _diplomacy_line({**FIXTURE, "diplomacy": _dipl({**old, "turn": 2, "at": 2})})
    line = _diplomacy_line({**FIXTURE, "diplomacy": _dipl(old, waiting)})
    assert "T1 civ:australia make peace: waiting" in line and "troops" not in line


def test_the_briefing_warns_when_the_auto_reply_is_not_installed():
    """The controller then leaves the leader screen's handler in place (popups.toml `requires`)."""
    line = _diplomacy_line({**FIXTURE, "diplomacy": _dipl(handler=False)})
    assert line is not None and "not installed" in line
    assert "the leader screen is kept" in line and "until a human answers it on screen" in line


def test_no_diplomacy_line_without_a_statement_or_from_an_older_library():
    assert _diplomacy_line({**FIXTURE, "diplomacy": _dipl()}) is None
    assert _diplomacy_line(FIXTURE) is None


def _replies(setup) -> list[dict]:
    return [e for e in _events(setup) if e["kind"] == "diplomacy_reply"]


def test_each_answer_is_one_diplomacy_reply_event_and_in_the_next_prompt(setup):
    seen: list[str] = []

    def statements(state):
        state["diplomacy"] = _dipl(*_T240, _WAITING)

    def answered_late(state):          # autoplay started: the waiting peace offer got Goodbye
        state["diplomacy"]["log"][2].update(reply="EXIT", why="table", at=14, late=True)

    game = FakeCiv6(FIXTURE, index=INDEX, events={FIXTURE["turn"] + 1: statements, FIXTURE["turn"] + 2: answered_late})
    g = governor(setup, game, orders_model([], seen=seen))
    g.run(max_decisions=2)
    replies = _replies(setup)
    assert [(e["statement"], e["subtype"], e["reply"], e["why"]) for e in replies] == [
        ("WARNING_TOO_MANY_TROOPS_NEAR_ME", "NONE", "POSITIVE", "table"),
        ("WARNING_TOO_MANY_TROOPS_NEAR_ME", "POSITIVE", "EXIT", "follow-up"),
        ("MAKE_PEACE", "NONE", "EXIT", "table")], "once each, and the waiting one once answered"
    first = replies[0]
    assert (first["civ"], first["from"], first["turn"], first["at"], first["date"], first["session"]) == (
        "civ:australia", 3, 13, 13, "T13", 7)
    assert first["text"] == "the conciliatory reply (a promise)"
    assert replies[2]["late"] is True and replies[2]["date"] == "T14"
    assert "T13 civ:australia warning too many troops near me: the conciliatory reply" in seen[1]


def test_a_restarted_run_does_not_report_the_same_answers_again(setup, tmp_path):
    from pilot.telemetry import Telemetry
    s, _ = setup
    tel = Telemetry(tmp_path / "t.sqlite")
    base = {**FIXTURE, "diplomacy": _dipl(*_T240)}
    first = Civ6Governor(s, FakeCiv6(base, index=INDEX), EventLog(s.runs_dir, "r1", s.model, telemetry=tel),
                         model=orders_model([]))
    first.status_poll_s, first.start_grace_s = 0, 0.05
    first.run(max_decisions=1)
    second = Civ6Governor(s, FakeCiv6(base, index=INDEX), EventLog(s.runs_dir, "r2", s.model, telemetry=tel),
                          model=orders_model([]))
    second.status_poll_s, second.start_grace_s = 0, 0.05
    second.run(max_decisions=1)
    rows = tel.campaign_events(first.log.campaign_id, "diplomacy_reply")
    assert [(r["session"], r["subtype"]) for r in rows] == [(7, "NONE"), (7, "POSITIVE")]


_T240_RECORD = ("Diplomacy answered for us in this campaign (the harness's auto-reply during autoplay; the last 8):\n"
                "- T13 civ:australia warning too many troops near me: the conciliatory reply (a promise)\n"
                "- T13 civ:australia warning too many troops near me (positive follow-up): Goodbye")


def test_the_order_record_carries_the_diplomacy_answered_for_us(setup):
    """A promise made for us (T240: "my troops are merely passing by") is a commitment a strategy review
    must see: the Strategist's order record and the published record list the campaign's answers."""
    prompts: list[str] = []

    def respond(messages, info):
        text = "\n".join(str(getattr(p, "content", "")) for m in messages for p in getattr(m, "parts", []))
        if is_review(info):
            prompts.append(text)
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,
                                                     {"change": False, "assessment": "n/a", "rules": []})])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"orders": [], "reason": "r"})])

    g = governor(setup, FakeCiv6({**FIXTURE, "diplomacy": _dipl(*_T240)}, index=INDEX), FunctionModel(respond))
    g.run(max_decisions=1)
    assert "Order record in this campaign (held until done / replaced by the AI):\n(no orders judged yet)\n" \
        + _T240_RECORD in prompts[0]
    assert [(r["turn"], r["civ"], r["statement"], r["subtype"], r["reply"], r["text"])
            for r in g.log.state.info["diplomacy_record"]] == [
        (13, "civ:australia", "WARNING_TOO_MANY_TROOPS_NEAR_ME", "NONE", "POSITIVE", "the conciliatory reply (a promise)"),
        (13, "civ:australia", "WARNING_TOO_MANY_TROOPS_NEAR_ME", "POSITIVE", "EXIT", "Goodbye")]
    quiet = governor(setup, FakeCiv6(FIXTURE, index=INDEX), orders_model([]))
    assert "Diplomacy answered" not in quiet._records_section(), "no section without an answer"


def test_a_restarted_run_keeps_the_diplomacy_in_its_order_record(setup, tmp_path):
    """After a reload the library's log is empty; the record comes from telemetry, like order outcomes."""
    from pilot.telemetry import Telemetry
    s, _ = setup
    tel = Telemetry(tmp_path / "t.sqlite")
    first = Civ6Governor(s, FakeCiv6({**FIXTURE, "diplomacy": _dipl(*_T240)}, index=INDEX),
                         EventLog(s.runs_dir, "r1", s.model, telemetry=tel), model=orders_model([]))
    first.status_poll_s, first.start_grace_s = 0, 0.05
    first.run(max_decisions=1)
    second = Civ6Governor(s, FakeCiv6({**FIXTURE, "diplomacy": _dipl()}, index=INDEX),
                          EventLog(s.runs_dir, "r2", s.model, telemetry=tel), model=orders_model([]))
    second.status_poll_s, second.start_grace_s = 0, 0.05
    second.run(max_decisions=1)
    assert _T240_RECORD in second._records_section()
    assert [r["subtype"] for r in second.log.state.info["diplomacy_record"]] == ["NONE", "POSITIVE"]


# ---- postmortem-fixes design, rulings 15 and 19 --------------------------------------------------

def test_civ6_event_reviews_are_capped_at_5_turns_and_a_new_war_always_reviews(setup):
    """War-7 and H7: the T541 new war came 3 turns after the T538 review and was skipped (12 steps =
    12 turns). Now a new war and a lost city always review; other events wait 5 turns."""
    from pilot.strategy import Pillar, Strategy
    game = FakeCiv6(FIXTURE, index=INDEX)
    g = governor(setup, game, orders_model([]))
    g.strategy = Strategy(pillars={p: Pillar(weight=w, stance="s 1") for p, w in
                                   zip(SPEC.ids, (20, 15, 10, 15, 20, 10, 10), strict=True)}, focus="hold")
    assert g._maybe_event_review({**FIXTURE, "date": "T538"}, "urgent: city threatened: Beijing") is True
    assert g._maybe_event_review({**FIXTURE, "date": "T541"},
                                 "urgent: new war: CIVILIZATION_AUSTRALIA is at war with us") is True
    assert g._maybe_event_review({**FIXTURE, "date": "T542"}, "urgent: city threatened: Taiyuan") is False
    skip = [e for e in g.log.recent if e["kind"] == "strategy_review_skipped"][-1]
    assert skip["reason"] == "within 5 turns of the last event review"
    assert g._maybe_event_review({**FIXTURE, "date": "T543"}, "urgent: city lost: Beijing") is True
    assert g._maybe_event_review({**FIXTURE, "date": "T548"}, "urgent: city threatened: Taiyuan") is True, \
        "5 turns after the last review, city lost included"


def test_the_civ6_outcome_scoring_and_past_outcomes_speak_turns(setup, tmp_path):
    from pilot.telemetry import Telemetry
    s, _ = setup
    tel = Telemetry(tmp_path / "t.sqlite")
    log = EventLog(s.runs_dir, "civt", s.model, telemetry=tel)
    g = Civ6Governor(s, FakeCiv6(FIXTURE, index=INDEX), log, model=orders_model([]))
    log.emit("run_start", game="civ6", model=s.model)
    log.set_campaign("civ6", "kublai", "China")
    assert g._past_outcomes_text().startswith("No earlier")
    log.save_trace(1, {"date": "T12", "decision": "orders", "trigger": "x", "reason": "r", "steps": []})
    assert "| 12 turns later" in g._past_outcomes_text()


# ---- postmortem-fixes design, ruling 7: what the game will sell, and why not ---------------------

MODERN_AT = {"unit": "UNIT_MODERN_AT", "gold": 1160, "gold_allowed": True, "faith": 1160, "faith_allowed": True}
MACHINE_GUN = {"unit": "UNIT_MACHINE_GUN", "gold": 1080, "gold_allowed": True, "faith": 1080, "faith_allowed": True}
INFANTRY = {"unit": "UNIT_INFANTRY", "gold": 860, "gold_allowed": False, "gold_why": "game", "faith": 860,
            "faith_allowed": False, "faith_why": "game"}


def test_the_corpus_gives_each_units_resource_cost_upkeep_and_strength():
    assert INDEX.resource_cost["unit:infantry"] == (1, "Oil") and "unit:modern_at" not in INDEX.resource_cost
    assert INDEX.maintenance["unit:modern_at"] == 8 and INDEX.strength["unit:machine_gun"] == 85


def test_each_refusal_is_named_from_the_corpus_and_the_library():
    from pilot.civ6 import refusal
    stock = {**FIXTURE, "gold": 1630, "faith": 1961, "resources": {"RESOURCE_OIL": 0, "RESOURCE_ALUMINUM": 3}}
    assert refusal(MODERN_AT, "gold", stock, INDEX) is None
    assert refusal(INFANTRY, "gold", stock, INDEX) == ("resource", "needs 1 Oil, have 0")
    assert refusal(INFANTRY, "gold", {**stock, "resources": None}, INDEX) == ("resource", "needs 1 Oil, stock unknown")
    taken = {**MODERN_AT, "gold_allowed": False, "gold_why": "stacking"}
    assert refusal(taken, "gold", stock, INDEX) == ("stacking", "a unit is on the tile")
    poor = {**MODERN_AT, "gold_allowed": False, "gold_why": "balance"}
    assert refusal(poor, "gold", {**stock, "gold": 900}, INDEX) == ("balance", "costs 1160 gold, over the balance of 900")
    assert refusal({**MODERN_AT, "faith_allowed": False}, "faith", stock, INDEX) == ("game", "the game refuses it")


def test_a_city_with_nothing_to_buy_says_so_with_each_reason():
    """Post-mortem H5: "No gold or faith purchases are available" (T548) while Modern AT and Machine
    Gun were buyable elsewhere; each city now says what it can buy and why not."""
    taken = {**MODERN_AT, "gold_allowed": False, "gold_why": "stacking", "faith_allowed": False, "faith_why": "stacking"}
    city = danger_city(name="Guangzhou", defence_prices=[INFANTRY, taken])
    text = briefing_text({**FIXTURE, "gold": 1630, "faith": 1961, "resources": {"RESOURCE_OIL": 0},
                          "cities": [city]}, INDEX, limits=BUY)
    assert ("no defender can be bought now (unit:infantry: needs 1 Oil, have 0; unit:modern_at: a unit is on the "
            "tile)") in text
    ok = briefing_text({**FIXTURE, "gold": 1630, "faith": 1961, "resources": {"RESOURCE_OIL": 0},
                        "cities": [danger_city(defence_prices=[INFANTRY, MACHINE_GUN])]}, INDEX, limits=BUY)
    assert ("defenders to buy: unit:infantry 860 gold (refused: needs 1 Oil, have 0) / 860 faith (refused: needs 1 "
            "Oil, have 0), unit:machine_gun 1080 gold / 1080 faith") in ok


# ---- postmortem-fixes design, rulings 21-23: the run ends when our civilization is gone ----------

def _telemetry_log(setup, tmp_path, run="civ1"):
    from pilot.telemetry import Telemetry
    s, _ = setup
    tel = Telemetry(tmp_path / "t.sqlite")
    return tel, EventLog(s.runs_dir, run, s.model, telemetry=tel)


def _lost(state):
    """Our last city falls; no settler left (T583: 0 cities, 0 units)."""
    state["cities"] = []
    state["units"] = {"total": 0, "by_class": {}, "by_type": {}}


def _counting_model(calls: list):
    def respond(messages, info):
        calls.append("review" if is_review(info) else "decide")
        if is_review(info):
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,
                                                     {"change": False, "assessment": "n/a", "rules": []})])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"orders": [], "reason": "r"})])
    return FunctionModel(respond)


def test_zero_cities_and_settlers_read_twice_ends_the_run_with_no_model_call(setup, tmp_path):
    tel, log = _telemetry_log(setup, tmp_path)
    s, _ = setup
    calls: list = []
    game = FakeCiv6(FIXTURE, index=INDEX, events={FIXTURE["turn"] + 1: _lost})
    g = Civ6Governor(s, game, log, model=_counting_model(calls))
    g.status_poll_s, g.start_grace_s, g.turn_deadline_s, g.end_watch_s = 0, 0.05, 0.5, 0
    g.run(max_decisions=5)
    assert calls == ["review", "decide"], "the start only: no decision and no review after the end"
    end = [e for e in log.recent if e["kind"] == "campaign_end"]
    assert len(end) == 1 and end[0]["result"] == "lost" and end[0]["signal"] == "0 cities and 0 settlers on 2 reads in a row"
    assert (end[0]["last_city_turn"], end[0]["seen"]) == ("T12", "T13")
    assert end[0]["report"]["stranded"] == {"gold": FIXTURE["gold"], "faith": FIXTURE["faith"]}
    assert end[0]["report"]["after"] == {"decisions": 0, "reviews": 0}
    assert log.state.status == "ended" and log.state.info["end"]["result"] == "lost"
    assert tel.query("SELECT status FROM runs WHERE id='civ1'")[0]["status"] == "lost", "run_end keeps it"
    assert "Campaign lost: China (Kublai Khan (China)) was eliminated in T12, seen at T13" in s.journal.read_text()
    assert ("autoplay_stop",) in game.actions


def test_one_zero_city_read_does_not_end_the_run(setup):
    class Glitch(FakeCiv6):
        blank = 1

        def snapshot(self):
            s = super().snapshot()
            if s["turn"] > FIXTURE["turn"] and self.blank:
                self.blank -= 1
                s = {**s, "cities": [], "units": {"by_type": {}}}
            return s
    game = Glitch(FIXTURE, index=INDEX)
    g = governor(setup, game, orders_model([]))
    game.state["turn"] += 1
    first = game.snapshot()
    assert first["cities"] == []
    assert g._end_check(first)["cities"], "the second read shows the city again: the run goes on"
    assert not g._ended


def test_alive_false_ends_it_at_once_and_a_settler_or_player_minus_one_does_not(setup, tmp_path):
    from pilot.campaign_end import civ6_read
    assert civ6_read({**FIXTURE, "alive": False}) == "not alive"
    settler = {**FIXTURE, "cities": [], "units": {"by_type": {"UNIT_SETTLER": 1}}}
    assert civ6_read(settler) is None, "a settler can found a city again"
    assert civ6_read({**FIXTURE, "local_player": -1, "alive": None}) is None, "the local player id is never used"
    _tel, log = _telemetry_log(setup, tmp_path, "civ2")
    s, _ = setup
    game = FakeCiv6(FIXTURE, index=INDEX, events={FIXTURE["turn"] + 1: lambda st: st.update(alive=False)})
    g = Civ6Governor(s, game, log, model=_counting_model([]))
    g.status_poll_s, g.start_grace_s, g.turn_deadline_s, g.end_watch_s = 0, 0.05, 0.5, 0
    g.run(max_decisions=5)
    end = next(e for e in log.recent if e["kind"] == "campaign_end")
    assert end["signal"] == "the game reports our civilization is not alive"
    assert sum(1 for a in game.actions if a[0] == "autoplay") == 1


def test_a_second_run_on_a_lost_campaign_ends_at_its_start(setup, tmp_path):
    _tel, log = _telemetry_log(setup, tmp_path, "civ3")
    s, _ = setup
    calls: list = []
    dead = {**FIXTURE, "turn": 763, "cities": [], "units": {"total": 0, "by_class": {}, "by_type": {}}}
    game = FakeCiv6(dead, index=INDEX)
    g = Civ6Governor(s, game, log, model=_counting_model(calls))
    g.end_watch_s = 0
    g.run(max_decisions=5)
    assert calls == [] and [e["kind"] for e in log.recent].count("campaign_end") == 1
    assert log.state.status == "ended" and not any(a[0] == "autoplay" for a in game.actions)


def test_the_end_report_lists_the_cities_lost_the_enemy_ratio_and_the_stranded_treasury():
    from pilot.campaign_end import enemy_ratio, losses, report_text
    episodes = [{"date": "T475", "situation": "urgent: city lost: Shanghai"},
                {"date": "T546", "situation": "urgent: city lost: Beijing; city threatened: Longxi (3 enemy units near)"},
                {"date": "T583", "situation": "urgent: city lost: Longxi"}]
    rows = [r for r in json.loads((REPO / "tests/fixtures/civ6_kublai_rows.json").read_text()) if r["turn"] <= 583]
    ratio = enemy_ratio(rows, "military")
    assert (ratio["date"], ratio["ours"], ratio["enemy"], ratio["theirs"], ratio["ratio"]) == \
        ("T579", 139, "CIVILIZATION_AUSTRALIA", 1561, 0.09)
    rep = {"game": "civ6", "turn": "T579", "seen": "T583", "signal": "0 cities and 0 settlers on 2 reads in a row",
           "lost": losses(episodes), "ratio": ratio, "stranded": {"gold": 1675.77, "faith": 994.97},
           "after": {"decisions": 0, "reviews": 0}}
    text = report_text("China (Kublai Khan)", rep)
    assert text.startswith("Campaign lost: China (Kublai Khan) was eliminated in T579, seen at T583 (0 cities and 0 "
                           "settlers on 2 reads in a row). Cities lost: Shanghai T475, Beijing T546, Longxi T583.")
    assert "139 vs CIVILIZATION_AUSTRALIA 1,561 (0.09x)" in text and "Stranded: 1,676 gold, 995 faith." in text
    assert "Decisions after the loss was first seen: 0 (strategy reviews 0)." in text


def test_the_report_notes_a_game_that_keeps_playing_by_itself(setup, tmp_path):
    class PlaysOn(FakeCiv6):
        def autoplay_status(self):
            reply = super().autoplay_status()
            if not self.state.get("cities"):
                self.state["turn"] += 1              # all-AI turns after the elimination (T763 -> T1290)
            return reply
    _tel, log = _telemetry_log(setup, tmp_path, "civ4")
    s, _ = setup
    game = PlaysOn(FIXTURE, index=INDEX, events={FIXTURE["turn"] + 1: _lost})
    g = Civ6Governor(s, game, log, model=_counting_model([]))
    g.status_poll_s, g.start_grace_s, g.turn_deadline_s, g.end_watch_s = 0, 0.05, 0.5, 0
    g.run(max_decisions=5)
    end = next(e for e in log.recent if e["kind"] == "campaign_end")
    assert "keeps playing all-AI turns by itself" in end["report"]["note"]
    assert "exit to the main menu to stop it" in end["text"]


def test_a_snapshot_for_another_player_waits_for_the_human(setup):
    game = FakeCiv6(FIXTURE, index=INDEX, events={FIXTURE["turn"] + 1: lambda st: st.update(player=3)})
    g = governor(setup, game, orders_model([]))
    run_until_attention(g)
    assert any(e["kind"] == "needs_attention" and "player 3, this run governs player 0" in e["reason"]
               for e in g.log.recent)


# ---- postmortem-fixes design, ruling 18 -----------------------------------------------------------

LATE_MAJORS = [{"id": 1, "civ": "CIVILIZATION_MALI", "military": 2428, "allied": True, "score": 1, "cities": 4, "techs": 70},
               {"id": 2, "civ": "CIVILIZATION_MAYA", "military": 1491, "score": 1, "cities": 9, "techs": 70},
               {"id": 3, "civ": "CIVILIZATION_AUSTRALIA", "military": 1106, "score": 1, "cities": 9, "techs": 70}]


def test_rows_and_the_briefing_carry_military_relative_to_the_majors_met():
    s = {**FIXTURE, "military": 471, "majors": LATE_MAJORS}
    row = metrics(s)
    assert (row["military_vs_median"], row["military_vs_strongest"]) == (round(471 / 1491, 3), round(471 / 1491, 3))
    assert row["neighbours"][0]["allied"] is True and "allied" not in row["neighbours"][1]
    text = briefing_text(s, INDEX, limits=BUY)
    assert ("Military standing (peers are the 3 majors we have met): ours 471 is 0.316 x their median 1491 and 0.316 x "
            "the strongest that is not our ally; rank 4 of 4.") in text
    assert "civ:mali score 1, military 2428, cities 4, techs 70, ALLIED" in text


def test_the_governor_gives_the_strategist_its_military_standing(setup):
    g = governor(setup, FakeCiv6(FIXTURE, index=INDEX), orders_model([]))
    st = g._standing({**FIXTURE, "military": 471, "majors": LATE_MAJORS})
    assert st == {"military": 471, "median": 1491.0, "peers": 3, "weak": True}
    assert g._standing({**FIXTURE, "majors": []}) is None


# ---- postmortem-fixes design, rulings 10-14: the triggers -------------------------------------------

def _longxi(prices, turn=570) -> dict:
    """T570: at war with Australia; Longxi in danger with no unit on its tile."""
    city = danger_city(name="Longxi", defense={"garrison_hp": 80, "garrison_max": 200, "walls_hp": 0, "walls_max": 400},
                       defence_prices=prices)
    return {**FIXTURE, "turn": turn, "gold": 1407.6, "faith": 755.8, "cities": [city], "military": 329,
            "wars": [{"id": 3, "civ": "CIVILIZATION_AUSTRALIA", "major": True}], "majors": LATE_MAJORS}


def test_a_city_that_stays_in_danger_at_war_decides_at_every_hand_back(setup):
    """War-8, H6: T571-T574 had no decision while Longxi stayed in danger with a Modern AT allowed."""
    game = FakeCiv6(_longxi([MODERN_AT]), index=INDEX)
    g = governor(setup, game, orders_model([]))
    g.run(max_decisions=4)
    triggers = [t["trigger"] for t in traces(setup)]
    assert triggers[0] == "start of run"
    assert all(t.startswith("urgent: city still in danger: Longxi (walls 0/400, garrison 80/200; unit:modern_at 1160 "
                            "gold allowed)") for t in triggers[1:4]), triggers
    assert [a[1] for a in game.actions if a[0] == "autoplay"] == [1, 1, 1], "one turn at a time, a decision each"


def test_nothing_to_buy_gives_no_standing_danger_decision(setup):
    """T576-T582: nothing could be bought, so no decision each turn."""
    refused = {**MODERN_AT, "gold_allowed": False, "gold_why": "stacking", "faith_allowed": False, "faith_why": "stacking"}
    game = FakeCiv6(_longxi([refused]), index=INDEX)
    g = governor(setup, game, orders_model([]))
    g.run(max_decisions=2)
    assert traces(setup)[1]["trigger"] == "scheduled (3 turns)"
    from pilot.civ6 import standing_danger
    peace = {**_longxi([MODERN_AT]), "wars": []}
    assert standing_danger(peace, INDEX, BUY) == "", "only while at war with a major"
    assert standing_danger(_longxi([MODERN_AT]), INDEX, BUY, {"longxi": 568}) == "", "the defender cooldown runs"


def test_falling_behind_buildup_and_income_review_and_loyalty_only_decides(setup):
    from pilot.civ6_governor import EVENT_TRIGGERS_CIV6
    reviews = ("falling behind in military: 318 against a median of 1,094, last of 6",
               "neighbour buildup: CIVILIZATION_AUSTRALIA 598 military (+73% in 20 turns), 2.0x ours (295)",
               "gold per turn negative: -6.8")
    assert all(any(t in r for t in EVENT_TRIGGERS_CIV6) for r in reviews)
    assert not any(t in "loyalty falling: Haarlem 77 (-18 a turn)" for t in EVENT_TRIGGERS_CIV6)
    assert not any(t in "falling behind in techs: 57 against a median of 69" for t in EVENT_TRIGGERS_CIV6)
    assert not any(t in "city still in danger: Longxi (...)" for t in EVENT_TRIGGERS_CIV6)
    g = governor(setup, FakeCiv6(FIXTURE, index=INDEX), orders_model([]))
    last = {**FIXTURE, "turn": 546, "cities": [{**FIXTURE["cities"][0], "name": "Haarlem", "loyalty": 95}]}
    now = {**FIXTURE, "turn": 547, "cities": [{**FIXTURE["cities"][0], "name": "Haarlem", "loyalty": 77}]}
    assert g._threat_reasons(last, now) == ["loyalty falling: Haarlem 77 (-18 a turn)"]
    later = {**now, "turn": 548, "cities": [{**now["cities"][0], "loyalty": 59}]}
    assert g._threat_reasons(now, later) == [], "once until it rises"
    assert g._row(later)["low_loyalty"] == 0 and g._row({**later, "cities": [{**later["cities"][0], "loyalty": 41}]})["low_loyalty"] == 1


def test_a_hand_back_that_falls_behind_in_military_is_urgent(setup):
    g = governor(setup, FakeCiv6(FIXTURE, index=INDEX), orders_model([]))
    ahead = {**FIXTURE, "military": 1500, "majors": LATE_MAJORS}
    lagging = {**FIXTURE, "military": 300, "majors": LATE_MAJORS}
    assert g._threat_reasons(ahead, lagging) == ["falling behind in military: 300 against a median of 1,491, last of 4"]
    assert "military" in g._row(lagging)["behind"] and "military" not in g._row(ahead)["behind"]
