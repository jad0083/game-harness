"""The Civilization VI governor loop against FakeCiv6 (ruling 4): decisions apply structured orders
and autoplay, orders are read back, urgent changes stop autoplay, invalid ids never reach the game,
purchases keep the reserve."""

import json
import shutil

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from pilot.civ6 import (
    Civ6Order,
    CorpusIndex,
    FakeCiv6,
    briefing_text,
    check_orders,
    metrics,
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
                 ask_human_timeout_s=0.05, fallback_model=None)
    s.__class__ = type("S", (Settings,), {"corpus_dir": property(lambda self: corpus)})
    return s, EventLog(s.runs_dir, "civ1", s.model)


def governor(setup, game, model) -> Civ6Governor:
    s, log = setup
    g = Civ6Governor(s, game, log, model=model)
    g.min_poll_s = 0
    return g


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
    assert ("autoplay", 3) in game.actions
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
    assert "production unit:settler in Beijing: no longer current" in seen[1]
    assert "Beijing builds UNIT_WARRIOR" in seen[1]


def test_an_urgent_change_stops_autoplay(setup):
    def war(state):
        state["wars"] = [{"id": 1, "civ": "CIVILIZATION_ROME", "major": True}]

    game = FakeCiv6(FIXTURE, index=INDEX, events={FIXTURE["turn"] + 1: war})
    s, _ = setup
    s.decide_every_turns = 5
    g = governor(setup, game, orders_model([]))
    g.run(max_decisions=2)
    assert ("autoplay_stop",) in game.actions[game.actions.index(("autoplay", 5)):]
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
    assert purchase_cap(rich, {**city, "threatened": True}, "gold", buy) == 400 - buy.gold_reserve
    assert purchase_cap({**FIXTURE, "gold": buy.gold_reserve}, city, "gold", buy) == 0

    game = FakeCiv6({**FIXTURE, "gold": 400}, index=INDEX, prices={("Beijing", "unit:slinger"): 280})
    g = governor(setup, game, orders_model([{"kind": "purchase", "city": "Beijing", "id": "unit:slinger"}]))
    g.run(max_decisions=1)
    assert orders_sent(game) == [{"kind": "purchase", "city": "Beijing", "id": "unit:slinger", "currency": "gold",
                                  "max_cost": 200}]
    assert game.state["gold"] == 400, "a price over the cap buys nothing"
    assert "over the allowed 200" in traces(setup)[0]["orders"][0]["outcome"]


def test_a_purchase_at_the_reserve_never_reaches_the_game(setup):
    game = FakeCiv6({**FIXTURE, "gold": 50}, index=INDEX)
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

