import shutil

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from pilot.config import REPO, Settings
from pilot.events import EventLog
from pilot.game import FakeStellaris
from pilot.governor import Governor, current_directive, months, urgent_changes
from pilot.pillars import load_pillars

STELLARIS = load_pillars(REPO / "corpora/stellaris")


def _pillars_body(prios: dict[str, int], stance: str = "{p} by model") -> dict:
    """Strategist answer pillars; each top-3 pillar carries a milestone (pillars.toml min_milestones_top)."""
    return {p: {"priority": n, "stance": stance.format(p=p), "goals": ["g"],
                "milestones": [{"metric": "systems", "op": ">=", "target": 10, "by": "2230.01.01"}] if n <= 3 else []}
            for p, n in prios.items()}


def briefing(date: str, net: dict | None = None, wars: list | None = None) -> dict:
    return {"date": date, "net": net or {"energy": 5.0, "food": 3.0}, "wars": wars or [], "flags": []}


def _is_strategy_review(info: AgentInfo) -> bool:
    """True when a FunctionModel call is answering the Strategist's StrategyReview schema, not a
    GovernorDecision: lets models written only for `decisions` ignore the strategist's implicit
    start-of-run (and scheduled) review when a test does not script one of its own."""
    return "change" in info.output_tools[0].parameters_json_schema.get("properties", {})


def _quiet_no_change(info: AgentInfo) -> ModelResponse:
    """A harmless StrategyReview answer ('no change'), for models that only script decisions."""
    return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"change": False, "assessment": "n/a", "rules": []})])


def decisions(*choices: str, consult_first: bool = False):
    """A model that returns the given directives in order (one per decision)."""
    calls = {"n": 0}

    def respond(messages, info: AgentInfo) -> ModelResponse:
        if _is_strategy_review(info):
            return _quiet_no_change(info)
        step = sum(isinstance(m, ModelResponse) for m in messages)
        if consult_first and step == 0 and calls["n"] == 0:
            return ModelResponse(parts=[ToolCallPart("consult", {"query": "diplomatic stance"})])
        choice = choices[min(calls["n"], len(choices) - 1)]
        calls["n"] += 1
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,
                                                 {"directive": choice, "reason": f"test chose {choice}"})])

    return FunctionModel(respond)


@pytest.fixture
def setup(tmp_path):
    corpus = tmp_path / "stellaris"
    corpus.mkdir()
    for f in ("manifest.toml", "pilot.md", "strategy.md", "directives.toml", "pillars.toml"):
        shutil.copy(REPO / "corpora/stellaris" / f, corpus / f)
    s = Settings(model="google:gemini-3.8-flash", runs_dir=tmp_path / "runs", journal=tmp_path / "journal.md",
                 commit_learnings=False, game="stellaris", speed="fastest", decide_every_months=12, poll_s=0,
                 ask_human_timeout_s=0.05, fallback_model=None)      # tests never reach a real provider
    s.__class__ = type("S", (Settings,), {"corpus_dir": property(lambda self: corpus)})
    return s, EventLog(s.runs_dir, "run1", s.model)


def test_helpers():
    assert months("2201.01.01") - months("2200.01.01") == 12
    assert current_directive({"flags": ["x", "governor_directive_defend"]}) == "defend"
    assert current_directive({"flags": []}) is None
    before = briefing("2200.01.01", net={"food": 2.0, "energy": 1.0})
    now = briefing("2200.02.01", net={"food": -1.5, "energy": 1.0}, wars=[{"name": "Border War", "attacker": False}])
    reasons = urgent_changes(before, now)
    assert any("new war: Border War (we are defender)" in r for r in reasons)
    assert any("food net turned negative" in r for r in reasons)
    assert urgent_changes(now, now) == []   # an existing deficit or war does not re-trigger
    lag = {**now, "peers": {"behind": ["systems", "military_power"], "stats": {"systems": {"ours": 1, "median": 10},
           "military_power": {"ours": 193.75781, "median": 405.92577500000004}}}}
    assert any("falling behind other empires in systems (1 vs median 10)" in r for r in urgent_changes(now, lag))
    assert any("military_power (194 vs median 406)" in r for r in urgent_changes(now, lag))
    assert not any("falling behind" in r for r in urgent_changes(lag, lag))


def test_governor_decides_on_schedule_and_pauses_while_deciding(setup):
    s, log = setup
    game = FakeStellaris([briefing("2200.01.01"), briefing("2200.06.01"), briefing("2201.01.01")])
    gov = Governor(s, game, log, model=decisions("expand", "keep", consult_first=True))
    gov.run(max_decisions=2)

    acts = [a for a in game.actions if a[0] != "corpus"]
    assert acts[:4] == [("paused", True), ("speed", "fastest"), ("take_control",), ("directive", "expand")]
    # resumed after the first decision, paused again at the scheduled date (12 months later)
    assert acts[4] == ("paused", False) and acts[5] == ("paused", True)
    assert ("directive", "keep") not in acts and acts.count(("directive", "expand")) == 1
    assert game.paused is True, "left paused at the end"
    assert log.state.episodes == 2 and log.state.game_date == "2201.01.01"
    eps = [e for e in log.recent if e["kind"] == "episode"]
    assert eps[0]["situation"] == "start of run" and eps[1]["situation"].startswith("scheduled")
    assert ("corpus", "corpus_search", {"query": "diplomatic stance", "limit": 5}) in game.actions
    assert "expand (applied)" in (s.journal).read_text()


def test_governor_decides_early_on_a_new_war(setup):
    s, log = setup
    war = [{"name": "Invasion of Sol", "attacker": False}]
    game = FakeStellaris([briefing("2200.01.01"), briefing("2200.03.01", wars=war)])
    Governor(s, game, log, model=decisions("expand", "defend")).run(max_decisions=2)
    assert [a for a in game.actions if a[0] == "directive"] == [("directive", "expand"), ("directive", "defend")]
    ep = [e for e in log.recent if e["kind"] == "episode"][1]
    assert ep["situation"].startswith("urgent: new war: Invasion of Sol")


def test_fake_game_records_strategy_actions():
    g = FakeStellaris([briefing("2200.01.01")])
    assert g.pick_tech(["tech_habitat_1"]) == "ok"
    assert g.market_sync([{"side": "sell", "resource": "energy", "amount": 11}]) == "ok"
    assert ("pick_tech", ["tech_habitat_1"]) in g.actions
    assert ("market_sync", [{"side": "sell", "resource": "energy", "amount": 11}]) in g.actions


def test_prepare_war_needs_a_human_yes(setup):
    s, log = setup
    game = FakeStellaris([briefing("2200.01.01")])
    Governor(s, game, log, model=decisions("prepare_war")).run(max_decisions=1)
    assert ("directive", "prepare_war") not in game.actions
    assert any(e["kind"] == "question" for e in log.recent)
    assert "needs a human yes" in log.state.last_decision


def test_traces_capture_tool_calls_and_answer(setup):
    s, log = setup
    game = FakeStellaris([briefing("2200.01.01")])
    Governor(s, game, log, model=decisions("expand", consult_first=True)).run(max_decisions=1)
    import json
    t = json.loads((log.dir / "traces/0001.json").read_text())
    assert t["decision"] == "expand" and t["outcome"] == "applied" and t["date"] == "2200.01.01"
    kinds = [st["type"] for st in t["steps"]]
    assert kinds[0] == "prompt" and "Decision point: start of run" in t["steps"][0]["text"]
    assert {"tool_call", "tool_result", "output", "usage"} <= set(kinds)
    call = next(st for st in t["steps"] if st["type"] == "tool_call")
    assert call["tool"] == "consult" and call["args"] == {"query": "diplomatic stance"}
    assert any(e["kind"] == "trace" and e["file"] == "traces/0001.json" for e in log.recent)
    m = [e for e in log.recent if e["kind"] == "metrics"]
    assert m and m[0]["date"] == "2200.01.01" and "net" in m[0]
    assert log.state.info["directive"] == "expand" and log.state.info["speed"] == "fastest"


def test_trace_serializer_handles_thinking_images_and_retries():
    from pydantic_ai import BinaryContent
    from pydantic_ai.messages import (
        ModelRequest,
        ModelResponse,
        RetryPromptPart,
        TextPart,
        ThinkingPart,
        ToolCallPart,
        ToolReturnPart,
        UserPromptPart,
    )

    from pilot.trace import MAX_TEXT, serialize
    msgs = [ModelRequest(parts=[UserPromptPart(["look", BinaryContent(b"x", media_type="image/jpeg")])]),
            ModelResponse(parts=[ThinkingPart("weighing options"), TextPart("ok"),
                                 ToolCallPart("click", {"x": 1, "y": 2})]),
            ModelRequest(parts=[ToolReturnPart("click", "x" * (MAX_TEXT + 10)), RetryPromptPart("bad args", tool_name="click")]),
            ModelResponse(parts=[ToolCallPart("final_result", {"resolved": True})])]
    steps = serialize(msgs)
    assert steps[0] == {"type": "prompt", "text": "look\n[image]"}
    assert {"type": "thinking", "text": "weighing options"} in steps
    res = next(st for st in steps if st["type"] == "tool_result")
    assert res["text"].endswith("[10 more chars]")
    assert any(st["type"] == "retry" for st in steps)
    assert steps[-2] == {"type": "output", "tool": "final_result", "args": {"resolved": True}}


def test_history_endpoints_serve_runs_traces_and_metrics(setup):
    import asyncio

    from aiohttp.test_utils import TestClient, TestServer

    from pilot.dashboard import make_app
    s, log = setup
    game = FakeStellaris([briefing("2200.01.01"), briefing("2201.01.01")])
    Governor(s, game, log, model=decisions("expand", "keep")).run(max_decisions=2)

    async def go():
        async with TestClient(TestServer(make_app(None, s.runs_dir))) as c:   # read-only viewer
            runs = await (await c.get("/runs")).json()
            assert runs[0]["id"] == "run1" and runs[0]["game"] == "stellaris" and runs[0]["decisions"] == 2
            assert (await (await c.get("/status")).json())["live"] is False
            evs = await (await c.get("/runs/run1/events?kind=metrics,episode")).json()
            assert {e["kind"] for e in evs} == {"metrics", "episode"}
            t = await (await c.get("/runs/run1/trace/2")).json()
            assert t["decision"] == "keep" and t["trigger"].startswith("scheduled")
            assert (await c.get("/runs/run1/trace/9")).status == 404
            assert (await c.get("/runs/..%2Fetc/events")).status == 404
            assert (await c.post("/control", json={"action": "pause"})).status == 503   # no live run
            assert (await c.get("/")).status == 200

    asyncio.run(go())


def test_telemetry_records_campaign_decisions_and_scores_outcomes(setup, tmp_path):
    import json

    from pilot.telemetry import Telemetry
    s, _ = setup
    tel = Telemetry(tmp_path / "t.sqlite")
    log = EventLog(s.runs_dir, "run7", s.model, telemetry=tel)
    src = "save games/unitednationsofearth_-155/autosave_2200.01.01.sav"
    b0 = {**briefing("2200.01.01"), "source": src, "planets": [{}], "pops": 100}
    b1 = {**briefing("2201.01.01"), "source": src, "planets": [{}, {}], "pops": 130}
    b2 = {**briefing("2202.01.01"), "source": src, "planets": [{}, {}, {}], "pops": 150}
    game = FakeStellaris([b0, b1, b2])
    Governor(s, game, log, model=decisions("expand", "keep", "keep")).run(max_decisions=3)

    cid = "stellaris/unitednationsofearth_-155"
    assert log.campaign_id == cid
    runs = tel.query("SELECT * FROM runs")
    assert runs[0]["campaign_id"] == cid and runs[0]["game"] == "stellaris" and runs[0]["status"] == "ended"
    ds = tel.query("SELECT * FROM decisions WHERE campaign_id=? AND decision != 'strategy_review' ORDER BY episode", (cid,))
    assert [d["decision"] for d in ds] == ["expand", "keep", "keep"]
    assert any(d["decision"] == "strategy_review" for d in
              tel.query("SELECT decision FROM decisions WHERE campaign_id=?", (cid,))), "the start-of-run review also traces"
    # the model that actually answered (an alias like gemini-pro-latest resolves to a version) and the
    # thinking level are kept with every decision
    assert ds[0]["model_version"] and ds[0]["model_version"].startswith("function:"), ds[0]["model_version"]
    assert ds[0]["thinking"] == s.governor_thinking
    assert json.loads(ds[0]["trace"])["steps"][0]["type"] == "prompt"
    assert len(tel.query("SELECT * FROM metrics WHERE campaign_id=?", (cid,))) == 3
    # 12 months after 'expand' (2200.01 -> 2201.01): +1 planet, +30 pops
    res = json.loads(ds[0]["result"])
    assert res["planets"] == 1 and res["pops"] == 30 and res["months"] == 12
    text = tel.past_outcomes(cid)
    assert "2200.01.01 | expand (from none) | start of run | " in text and "planets +1" in text

    # the database can be recreated from the JSONL logs alone
    tel2 = Telemetry(tmp_path / "t2.sqlite")
    assert tel2.rebuild(s.runs_dir) >= 1
    ds2 = tel2.query("SELECT decision, result FROM decisions WHERE campaign_id=? AND decision != 'strategy_review' ORDER BY episode", (cid,))
    assert [d["decision"] for d in ds2] == ["expand", "keep", "keep"] and ds2[0]["result"] == ds[0]["result"]


def test_telemetry_failure_never_stops_play(setup):
    s, _ = setup

    class Broken:
        def record(self, *a, **k):
            raise RuntimeError("disk full")

    log = EventLog(s.runs_dir, "run8", s.model, telemetry=Broken())
    Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("expand")).run(max_decisions=1)
    assert log.state.episodes == 1


def test_telemetry_api(setup, tmp_path):
    import asyncio

    from aiohttp.test_utils import TestClient, TestServer

    from pilot.dashboard import make_app
    from pilot.telemetry import Telemetry
    s, _ = setup
    tel = Telemetry(tmp_path / "t.sqlite")
    log = EventLog(s.runs_dir, "run9", s.model, telemetry=tel)
    src = "save games/empire_1/autosave.sav"
    game = FakeStellaris([{**briefing("2200.01.01"), "source": src}, {**briefing("2201.01.01"), "source": src}])
    Governor(s, game, log, model=decisions("expand", "keep", consult_first=True)).run(max_decisions=2)

    async def go():
        async with TestClient(TestServer(make_app(None, s.runs_dir, tel))) as c:
            camps = await (await c.get("/api/campaigns")).json()
            # the start-of-run strategy review also traces a row, but is not a directive decision
            assert camps[0]["id"] == "stellaris/empire_1" and camps[0]["decisions"] == 2 and camps[0]["runs"] == 1
            ds = await (await c.get("/api/decisions", params={"campaign": "stellaris/empire_1"})).json()
            assert [d["decision"] for d in ds] == ["expand", "keep"] and ds[0]["model"] == s.model
            one = await (await c.get("/api/decision", params={"run": "run9", "episode": "1"})).json()
            assert any(st["type"] == "tool_call" and st["tool"] == "consult" for st in one["trace"]["steps"])
            ms = await (await c.get("/api/metrics", params={"run": "run9"})).json()
            assert ms[0]["date"] == "2200.01.01" and "net" in ms[0]
            assert (await c.get("/api/decisions")).status == 400
            assert (await c.get("/api/decision", params={"run": "run9", "episode": "x"})).status == 400

    asyncio.run(go())


def test_api_decisions_reports_off_frame_from_the_trace(setup, tmp_path):
    """Task 9: /api/decisions extracts `off_frame` from each decision's stored trace, so the
    dashboard can tag a decision made without a fresh screen capture."""
    import asyncio

    from aiohttp.test_utils import TestClient, TestServer

    from pilot.dashboard import make_app
    from pilot.telemetry import Telemetry
    s, _ = setup
    tel = Telemetry(tmp_path / "t.sqlite")
    log = EventLog(s.runs_dir, "run-off", s.model, telemetry=tel)
    log.emit("run_start", model=s.model, game="stellaris")
    log.set_campaign("stellaris", "off1", "Off Frame Test")
    log.save_trace(1, {"date": "2200.01.01", "trigger": "start of run", "decision": "expand", "reason": "grow",
                       "outcome": "applied", "current": None, "seconds": 1.0, "tokens_in": 10, "tokens_out": 5,
                       "model": s.model, "off_frame": True, "steps": []})
    log.save_trace(2, {"date": "2200.07.01", "trigger": "scheduled", "decision": "keep", "reason": "steady",
                       "outcome": "kept", "current": "expand", "seconds": 1.0, "tokens_in": 8, "tokens_out": 4,
                       "model": s.model, "off_frame": False, "steps": []})

    async def go():
        async with TestClient(TestServer(make_app(None, s.runs_dir, tel))) as c:
            ds = await (await c.get("/api/decisions", params={"campaign": "stellaris/off1"})).json()
            by_ep = {d["episode"]: d["off_frame"] for d in ds}
            assert by_ep[1] and not by_ep[2]
    asyncio.run(go())


def recording_model(choice: str = "keep"):
    """Decides `choice`, answers chat in text, and records every prompt it was given."""
    seen: list[str] = []

    def respond(messages, info: AgentInfo) -> ModelResponse:
        from pydantic_ai.messages import TextPart, UserPromptPart
        for m in messages:
            for p in getattr(m, "parts", []):
                if isinstance(p, UserPromptPart) and isinstance(p.content, str):
                    seen.append(p.content)
        if not info.output_tools:          # the chat agent answers in plain text
            return ModelResponse(parts=[TextPart("Food is fine: +3/month.")])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"directive": choice, "reason": "r"})])

    return FunctionModel(respond), seen


def test_standing_orders_reach_every_decision_and_persist(setup):
    s, log = setup
    model, seen = recording_model()
    gov = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=model)
    gov.log.set_campaign("stellaris", "c1")
    gov.order_add("Never declare war.")
    gov.order_add("Prioritise research.")
    gov.order_remove(1)
    gov.run(max_decisions=1)
    assert any("STANDING ORDERS" in p and "1. Never declare war." in p and "research" not in p for p in seen)
    assert (s.runs_dir / "orders" / "stellaris_c1.json").exists()
    gov2 = Governor(s, FakeStellaris([briefing("2200.01.01")]), EventLog(s.runs_dir, "run2", s.model), model=model)
    gov2._set_campaign({"source": "save games/c1/x.sav"})
    assert gov2.orders == ["Never declare war."]
    assert any(e["kind"] == "orders" for e in log.recent)


def test_decide_now_and_override_run_between_scheduled_decisions(setup):
    s, log = setup
    model, seen = recording_model("tech_rush")
    game = FakeStellaris([briefing("2200.01.01"), briefing("2200.02.01")])
    gov = Governor(s, game, log, model=model)
    gov.decide_now("We need more alloys")
    gov.override("defend")
    gov.run(max_decisions=3)
    eps = [e for e in log.recent if e["kind"] == "episode"]
    assert eps[1]["situation"] == "human request: We need more alloys"
    assert any("HUMAN INSTRUCTIONS (follow these): We need more alloys" in p for p in seen)
    assert eps[2]["situation"] == "human override" and ("directive", "defend") in game.actions
    import json
    t = json.loads((log.dir / "traces/0003.json").read_text())
    assert t["model"] == "human" and t["decision"] == "defend"
    with pytest.raises(ValueError):
        gov.override("nuke")


def test_chat_answers_without_touching_the_game(setup):
    s, log = setup
    model, _ = recording_model()
    game = FakeStellaris([briefing("2200.01.01")])
    gov = Governor(s, game, log, model=model)
    gov.chat("How is food?")
    for _ in range(50):
        if any(e["kind"] == "chat" and e["role"] == "model" for e in log.recent):
            break
        import time
        time.sleep(0.05)
    answer = next(e for e in log.recent if e["kind"] == "chat" and e["role"] == "model")
    assert answer["text"] == "Food is fine: +3/month."
    assert not [a for a in game.actions if a[0] in ("directive", "paused", "speed")]


def test_pausing_does_not_trigger_a_decision(setup):
    import threading
    import time
    s, log = setup
    model, _ = recording_model()
    gov = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=model)
    t = threading.Thread(target=gov.run, daemon=True)
    t.start()
    time.sleep(0.2)
    gov.pause()
    time.sleep(0.3)
    gov.stop()
    t.join(timeout=5)
    assert log.state.episodes == 1, "only the start-of-run decision"


def test_viewer_ignores_non_run_folders(setup, tmp_path):
    from pilot.dashboard import list_runs
    s, log = setup
    Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep")).run(max_decisions=1)
    (s.runs_dir / "orders").mkdir(exist_ok=True)
    assert [r["id"] for r in list_runs(s.runs_dir)] == ["run1"]


def test_viewer_forwards_live_controls_to_the_running_pilot(setup):
    import asyncio

    from aiohttp.test_utils import TestClient, TestServer

    from pilot.dashboard import make_app
    s, log = setup
    gov = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"))

    async def go():
        live = TestServer(make_app(gov))
        await live.start_server()
        log.state.info["port"] = live.port
        log.state.status = "playing"
        log.emit("status", status="playing")           # writes status.json with the port
        async with TestClient(TestServer(make_app(None, s.runs_dir))) as viewer:
            st = await (await viewer.get("/status")).json()
            assert st["live"] is True and st["run_id"] == "run1"
            r = await viewer.post("/control", json={"action": "order_add", "text": "Keep the peace"})
            assert r.status == 200 and gov.orders == ["Keep the peace"]
            assert (await viewer.post("/control", json={"action": "bogus"})).status == 400
        await live.close()

    asyncio.run(go())


def test_control_failure_flags_needs_attention_instead_of_crashing(setup):
    import threading
    import time
    s, log = setup

    class Stuck(FakeStellaris):
        def set_paused(self, paused):
            if paused is False:
                raise RuntimeError("could not resume the game: the Paused label did not disappear")
            return super().set_paused(paused)

    gov = Governor(s, Stuck([briefing("2200.01.01")]), log, model=decisions("keep"))
    t = threading.Thread(target=gov.run, daemon=True)
    t.start()
    for _ in range(40):
        if log.state.status == "needs_attention":
            break
        time.sleep(0.05)
    assert log.state.status == "needs_attention" and gov.control.paused
    assert any(e["kind"] == "needs_attention" and "Paused label" in e["reason"] for e in log.recent)
    gov.stop()
    t.join(timeout=5)
    assert not t.is_alive()


def test_default_speed_is_normal():
    assert Settings().speed == "normal"


def test_default_model_is_gemini_flash_with_medium_thinking():
    s = Settings()
    assert s.model == "google:gemini-3.8-flash" and s.thinking == "medium" and s.governor_thinking == "medium"


def test_explicit_journal_survives_game_switch(monkeypatch, tmp_path):
    from pilot import cli
    captured = {}
    monkeypatch.setenv("PILOT_JOURNAL", str(tmp_path / "j.md"))
    monkeypatch.setattr(cli, "check", lambda s: captured.setdefault("s", s) and 0)
    cli.main(["check", "--game", "stellaris"])
    assert captured["s"].game == "stellaris" and captured["s"].journal == tmp_path / "j.md"


def test_governor_thinks_more_than_episodes():
    from pilot.governor import governor_settings
    s = Settings(model="google:gemini-3.8-flash", thinking="low")
    assert governor_settings(s)["google_thinking_config"]["thinking_level"] == "medium"
    assert governor_settings(Settings(model="google:x", governor_thinking="high"))["google_thinking_config"]["thinking_level"] == "high"


def _run_bg(gov):
    import threading
    t = threading.Thread(target=gov.run, daemon=True)
    t.start()
    return t


def _wait(pred, secs=3.0):
    import time
    end = time.time() + secs
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.05)
    return False


def test_network_errors_flag_needs_attention_instead_of_crashing(setup):
    from urllib.error import URLError
    s, log = setup

    class Flaky(FakeStellaris):
        def set_paused(self, paused):
            if paused is False:
                raise URLError("agent unreachable")
            return super().set_paused(paused)

    gov = Governor(s, Flaky([briefing("2200.01.01")]), log, model=decisions("keep"))
    t = _run_bg(gov)
    assert _wait(lambda: log.state.status == "needs_attention"), log.state.status
    assert t.is_alive(), "the run survives"
    gov.stop()
    t.join(timeout=5)


def test_startup_failure_waits_for_resume_then_retries(setup):
    s, log = setup
    calls = {"n": 0}

    class Stubborn(FakeStellaris):
        def take_control(self):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("could not read the console's reply to human_ai")
            return super().take_control()

    gov = Governor(s, Stubborn([briefing("2200.01.01")]), log, model=decisions("keep"))
    t = _run_bg(gov)
    assert _wait(lambda: log.state.status == "needs_attention")
    assert log.state.episodes == 0
    gov.resume()
    assert _wait(lambda: log.state.episodes >= 1), "startup retried after Resume"
    gov.stop()
    t.join(timeout=5)
    assert calls["n"] == 2


def test_failing_request_is_dropped_not_retried_in_a_tight_loop(setup):
    import time
    s, log = setup

    class Dead(FakeStellaris):
        def briefing(self):
            if self.dead:
                raise ConnectionError("agent down")
            return super().briefing()

    game = Dead([briefing("2200.01.01")])
    game.dead = False
    gov = Governor(s, game, log, model=decisions("keep"))
    t = _run_bg(gov)
    assert _wait(lambda: log.state.episodes >= 1)
    gov.pause()
    game.dead = True
    gov.decide_now("now please")
    time.sleep(1.5)
    n = sum(1 for e in log.recent if e["kind"] == "needs_attention")
    assert 1 <= n <= 2, f"{n} needs_attention events: tight loop"
    assert gov.requests.empty(), "the failed request was consumed"
    gov.stop()
    t.join(timeout=5)


def test_notes_never_answer_a_question_only_answers_do():
    from pilot.agent import HumanChannel
    h = HumanChannel()
    h.push("prioritise defence")               # a note: must not count as an answer
    assert h.ask("Apply prepare_war?", timeout=0.1) is None
    assert h.take_all() == ["prioritise defence"], "the note is still there for the next decision"
    import threading
    threading.Timer(0.05, lambda: h.answer("yes")).start()
    assert h.ask("Apply prepare_war?", timeout=2) == "yes"


def test_prepare_war_applies_only_after_an_explicit_yes(setup):
    import threading
    s, log = setup
    s.ask_human_timeout_s = 3
    game = FakeStellaris([briefing("2200.01.01")])
    gov = Governor(s, game, log, model=decisions("prepare_war"))
    def human():
        _wait(lambda: bool(log.state.pending_question))
        gov.instruct("you should prioritise defence")     # a note during the question
        gov.answer("yes")
    threading.Thread(target=human, daemon=True).start()
    gov.run(max_decisions=1)
    assert ("directive", "prepare_war") in game.actions
    assert any(e["kind"] == "answer" and e["answer"] == "yes" for e in log.recent)


def test_chat_history_keeps_whole_exchanges(setup):
    s, log = setup
    model, _ = recording_model()
    gov = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=model)
    for i in range(12):
        gov._chat(f"question {i}")
    hist = gov._chat_history()
    from pydantic_ai.messages import ModelRequest, UserPromptPart
    assert isinstance(hist[0], ModelRequest) and any(isinstance(p, UserPromptPart) for p in hist[0].parts), \
        "history starts at the beginning of an exchange"
    assert len(gov.chat_exchanges) <= 6


def test_scoring_uses_the_same_run_and_a_nearby_end_point(tmp_path):
    import json

    from pilot.telemetry import Telemetry
    tel = Telemetry(tmp_path / "t.sqlite")
    for run in ("a", "b"):
        tel.record(run, {"t": 1, "kind": "run_start", "game": "stellaris", "model": "m"})
        tel.record(run, {"t": 1, "kind": "campaign", "game": "stellaris", "name": "c"})
    tel.record("a", {"t": 2, "kind": "trace", "episode": 1, "date": "2200.01.01", "decision": "expand"})
    tel.record("a", {"t": 2, "kind": "metrics", "date": "2200.01.01", "planets": 1})
    tel.record("b", {"t": 3, "kind": "metrics", "date": "2201.01.01", "planets": 9})   # other run: ignored
    assert tel.score("stellaris/c") == 0
    tel.record("a", {"t": 4, "kind": "metrics", "date": "2205.01.01", "planets": 5})   # 5 years later: too far
    assert tel.score("stellaris/c") == 0
    tel.record("a", {"t": 5, "kind": "metrics", "date": "2201.02.01", "planets": 2})
    assert tel.score("stellaris/c") == 1
    res = json.loads(tel.query("SELECT result FROM decisions")[0]["result"])
    assert res["planets"] == 1


def test_rebuild_survives_a_corrupt_trace_file(setup, tmp_path):
    from pilot.telemetry import Telemetry
    s, log = setup
    Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("expand")).run(max_decisions=1)
    (log.dir / "traces/0001.json").write_text("{ not json")
    tel = Telemetry(tmp_path / "r.sqlite")
    assert tel.rebuild(s.runs_dir) == 1
    assert tel.query("SELECT decision, trace FROM decisions WHERE decision='expand'")[0] == {"decision": "expand", "trace": None}


def planner_model(retro_rules=("Survey before expanding: expand stalls when few reachable systems are surveyed.",)):
    """Decides `expand` on the first decision, `keep` afterwards; the strategist writes a new
    version (with rules learned) whenever it is reviewed. `expansion` is priority 2 (STELLARIS.ids
    order), so the first `expand` choice stays within the frame's top 2 and is never off-frame."""
    seen = []
    calls = {"n": 0}

    def respond(messages, info: AgentInfo) -> ModelResponse:
        from pydantic_ai.messages import UserPromptPart
        for m in messages:
            for p in getattr(m, "parts", []):
                if isinstance(p, UserPromptPart) and isinstance(p.content, str):
                    seen.append(p.content)
        if _is_strategy_review(info):
            strategy = {"pillars": _pillars_body({p: i + 1 for i, p in enumerate(STELLARIS.ids)}, "{p} stance"),
                        "focus": "Survey before expanding", "reason": "bottleneck in surveying"}
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
                "change": True, "assessment": "Expansion lagged the median; surveying was the bottleneck.",
                "rules": list(retro_rules), "strategy": strategy})])
        choice = "expand" if calls["n"] == 0 else "keep"
        calls["n"] += 1
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"directive": choice, "reason": "r"})])

    return FunctionModel(respond), seen


def test_the_strategy_frame_persists_and_the_strategist_reviews_on_schedule(setup, tmp_path):
    """Successor to the old free-text campaign plan test (Task 4 drops `plan` from decisions): the
    strategist's frame, not a plan, is what now reaches later decisions."""
    from pilot.telemetry import Telemetry
    s, _ = setup
    s.retro_every = 3
    tel = Telemetry(tmp_path / "t.sqlite")
    log = EventLog(s.runs_dir, "run5", s.model, telemetry=tel)
    src = "save games/emp_1/x.sav"
    game = FakeStellaris([{**briefing(f"22{i:02d}.01.01"), "source": src} for i in range(8)])
    model, seen = planner_model()
    gov = Governor(s, game, log, model=model)
    gov.run(max_decisions=4)          # 4 decisions; the strategist also reviews at start and after 3
    assert any("STRATEGY FRAME" in p and "Survey before expanding" in p for p in seen), \
        "the frame is shown to later decisions"
    hist = tel.strategy_history("stellaris/emp_1")
    assert [h["trigger"] for h in hist] == ["scheduled after 3 decisions", "start of run"]
    assert hist[0]["strategy"]["focus"] == "Survey before expanding"
    rules = (s.corpus_dir / "learned" / "strategy.md")
    assert rules.exists() and "Survey before expanding" in rules.read_text()


def test_a_plan_can_still_be_set_directly_and_persists_across_governors(setup, tmp_path):
    """The campaign plan machinery (superseded by the strategy frame in decision prompts) is kept
    for whatever else sets it directly; `_set_plan`/telemetry round-trip still works."""
    from pilot.telemetry import Telemetry
    s, _ = setup
    tel = Telemetry(tmp_path / "t.sqlite")
    log = EventLog(s.runs_dir, "run5b", s.model, telemetry=tel)
    src = "save games/emp_2/x.sav"
    gov = Governor(s, FakeStellaris([{**briefing("2200.01.01"), "source": src}]), log, model=decisions("keep"))
    gov.run(max_decisions=1)
    gov._set_plan("Goals &amp; milestones", "2203.01.01", "decision")
    assert gov.plan == "Goals & milestones"
    # a new Governor for the same campaign picks the plan up again
    gov2 = Governor(s, FakeStellaris([briefing("2210.01.01")]),
                    EventLog(s.runs_dir, "run6b", s.model, telemetry=tel), model=decisions("keep"))
    gov2._set_campaign({"source": src})
    assert gov2.plan == "Goals & milestones"


def test_remember_rule_tool_records_a_rule(setup):
    """Regression: 'learned' events passed kind= as data and raised TypeError."""
    s, log = setup

    def respond(messages, info: AgentInfo) -> ModelResponse:
        if _is_strategy_review(info):
            return _quiet_no_change(info)
        step = sum(isinstance(m, ModelResponse) for m in messages)
        if step == 0:
            return ModelResponse(parts=[ToolCallPart("remember_rule", {
                "rule": "When influence is capped and systems lag, keep expand and check surveying.",
                "why": "influence 800 unused while systems 4 vs median 15"})])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"directive": "keep", "reason": "r"})])

    Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=FunctionModel(respond)).run(max_decisions=1)
    ev = [e for e in log.recent if e["kind"] == "learned"]
    assert ev and ev[0]["category"] == "rules"
    assert "keep expand and check surveying" in (s.corpus_dir / "learned/strategy.md").read_text()
    assert not any(e["kind"] == "episode_error" for e in log.recent)


def test_plans_api(setup, tmp_path):
    import asyncio

    from aiohttp.test_utils import TestClient, TestServer

    from pilot.dashboard import make_app
    from pilot.telemetry import Telemetry
    s, _ = setup
    s.retro_every = 2
    tel = Telemetry(tmp_path / "t.sqlite")
    log = EventLog(s.runs_dir, "run7", s.model, telemetry=tel)
    game = FakeStellaris([{**briefing(f"22{i:02d}.01.01"), "source": "save games/e1/x.sav"} for i in range(6)])
    model, _ = planner_model()
    gov = Governor(s, game, log, model=model)
    gov.run(max_decisions=3)
    gov._set_plan("Reach 6 systems by 2205.", "2202.01.01", "decision")   # the plan endpoint still serves direct writes

    async def go():
        async with TestClient(TestServer(make_app(None, s.runs_dir, tel))) as c:
            plans = await (await c.get("/api/plans", params={"campaign": "stellaris/e1"})).json()
            assert plans and "Reach 6 systems" in plans[0]["text"]
            ds = await (await c.get("/api/decisions", params={"campaign": "stellaris/e1"})).json()
            # strategy reviews also trace (start of run, and after 2 decisions per retro_every) but are
            # not directive decisions, so they are excluded here
            assert [d["decision"] for d in ds] == ["expand", "keep", "keep"]

    asyncio.run(go())


def test_instructions_carry_only_the_directive_section_of_the_strategy():
    from pilot.governor import strategy_core
    full = (REPO / "corpora/stellaris/strategy.md").read_text()
    core = strategy_core(full)
    assert "## 9. Governor directives" in core and "| Directive |" in core
    assert "## 1. Opening" not in core and "Opening (first ~10 years)" in core, "other sections only as contents"
    assert len(core) < len(full) * 0.6, "the core stays well under the whole playbook (it is sent with every call)"


def test_decision_prompt_includes_past_outcomes(setup, tmp_path):
    from pilot.telemetry import Telemetry
    s, _ = setup
    tel = Telemetry(tmp_path / "t.sqlite")
    log = EventLog(s.runs_dir, "r8", s.model, telemetry=tel)
    model, seen = recording_model("expand")
    game = FakeStellaris([{**briefing(f"22{i:02d}.01.01"), "source": "save games/e/x.sav"} for i in range(3)])
    Governor(s, game, log, model=model).run(max_decisions=2)
    assert any("Earlier directive changes in this campaign" in p and "expand (from none)" in p for p in seen)


def test_model_can_be_switched_live_from_the_dashboard(setup, monkeypatch, tmp_path):
    import asyncio

    from aiohttp.test_utils import TestClient, TestServer

    from pilot.dashboard import make_app
    from pilot.telemetry import Telemetry
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")      # constructing Gemini clients needs a key, not the network
    s, _ = setup
    tel = Telemetry(tmp_path / "t.sqlite")
    log = EventLog(s.runs_dir, "r9", s.model, telemetry=tel)
    gov = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"))
    gov.run(max_decisions=1)
    assert "set_model" in log.state.info["controls"]

    async def go():
        async with TestClient(TestServer(make_app(gov))) as c:
            r = await c.post("/control", json={"action": "set_model", "model": "google:gemini-3.8-pro", "thinking": "high"})
            assert r.status == 200, await r.text()
            st = await (await c.get("/status")).json()
            assert st["model"] == "google:gemini-3.8-pro" and st["info"]["thinking"] == "high"
            assert (await c.post("/control", json={"action": "set_model", "model": "rm -rf /"})).status == 400
            assert (await c.post("/control", json={"action": "set_model", "model": "google:x", "thinking": "max"})).status == 400

    asyncio.run(go())
    assert gov.s.model == "google:gemini-3.8-pro" and gov.s.governor_thinking == "high"
    assert "gemini-3.8-pro" in str(gov.agent.model.model_name) and "gemini-3.8-pro" in str(gov.chat_agent.model.model_name)
    assert any(e["kind"] == "model" and e["model"] == "google:gemini-3.8-pro" for e in log.recent)
    # decisions keep the model that made them
    assert tel.query("SELECT model FROM decisions WHERE run_id='r9'")[0]["model"] == "google:gemini-3.8-flash"


def test_model_list_includes_current_and_configured(monkeypatch):
    from pilot import models
    monkeypatch.setattr(models, "google_models", lambda: ["google:gemini-3.8-flash", "google:gemini-3.8-pro"])
    monkeypatch.setenv("PILOT_MODELS", "openai:gpt-5, bad model ,anthropic:claude-sonnet-5")
    got = models.available_models(Settings(model="google:gemini-3.8-flash"))
    assert got == sorted(["google:gemini-3.8-flash", "google:gemini-3.8-pro", "openai:gpt-5", "anthropic:claude-sonnet-5"])


def test_a_decision_that_keeps_calling_tools_is_cut_off_and_keeps_the_directive(setup):
    s, log = setup

    def respond(messages, info: AgentInfo) -> ModelResponse:
        if _is_strategy_review(info):
            return _quiet_no_change(info)
        return ModelResponse(parts=[ToolCallPart("consult", {"query": "more"})])   # never answers

    game = FakeStellaris([briefing("2200.01.01")])
    Governor(s, game, log, model=FunctionModel(respond)).run(max_decisions=1)
    err = [e for e in log.recent if e["kind"] == "episode_error"]
    assert err and "no answer within 6 model calls" in err[0]["error"]
    assert not [a for a in game.actions if a[0] == "directive"]
    assert sum(1 for a in game.actions if a[0] == "corpus") <= 6


def test_models_that_cannot_play_are_filtered(monkeypatch):
    from pilot import models

    class M:
        def __init__(self, name):
            self.name, self.supported_actions = f"models/{name}", ["generateContent"]

    class Client:
        def __init__(self, api_key):
            self.models = self
        def list(self):
            return [M(n) for n in ("gemini-3.8-flash", "gemini-3.8-flash-tts", "gemini-3-pro-image", "gemini-3.1-pro-preview",
                                   "gemini-robotics-er-2-preview", "gemini-3.5-transcribe", "gemini-2.5-computer-use-preview")]
    import google.genai
    monkeypatch.setattr(google.genai, "Client", Client)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    assert models.google_models() == ["google:gemini-3.8-flash", "google:gemini-3.1-pro-preview"]


def test_loading_another_game_stops_the_governor_acting(setup):
    s, log = setup
    a = {**briefing("2200.01.01"), "source": "save games/empire_a/x.sav"}
    other = {**briefing("2203.06.01"), "source": "save games/empire_b/x.sav"}
    game = FakeStellaris([a, a, other])
    gov = Governor(s, game, log, model=decisions("expand", "tech_rush"))
    t = _run_bg(gov)
    assert _wait(lambda: log.state.status == "needs_attention")
    assert any("the game changed" in e.get("reason", "") and "empire_b" in e["reason"] for e in log.recent)
    assert [a_ for a_ in game.actions if a_[0] == "directive"] == [("directive", "expand")], "nothing applied to game B"
    assert game.paused
    gov.stop()
    t.join(timeout=5)


def test_model_choice_is_saved_for_the_next_run_without_a_live_pilot(setup, monkeypatch):
    import asyncio

    from aiohttp.test_utils import TestClient, TestServer

    from pilot import cli, models
    from pilot.dashboard import make_app
    s, _ = setup
    monkeypatch.setattr(models, "available_models", lambda st: ["google:gemini-3.8-flash", "google:gemini-3.1-pro-preview"])

    async def go():
        async with TestClient(TestServer(make_app(None, s.runs_dir))) as c:
            cat = await (await c.get("/api/models")).json()
            assert "google:gemini-3.1-pro-preview" in cat["models"]
            r = await c.post("/api/settings", json={"model": "google:gemini-3.1-pro-preview", "thinking": "high"})
            assert r.status == 200 and (await r.json())["applied_live"] is False
            assert (await c.post("/api/settings", json={"model": "bad", "thinking": "high"})).status == 400
            cat = await (await c.get("/api/models")).json()
            assert cat["model"] == "google:gemini-3.1-pro-preview" and cat["thinking"] == "high"

    asyncio.run(go())
    assert models.load_prefs(s.runs_dir) == {"model": "google:gemini-3.1-pro-preview", "thinking": "high",
                                             "models": [{"model": "google:gemini-3.1-pro-preview", "thinking": "high"}]}
    # the next `pilot run` picks it up; a command-line option still wins
    seen = {}
    monkeypatch.setenv("PILOT_RUNS_DIR", str(s.runs_dir))
    monkeypatch.setattr(cli, "run", lambda st, ep: seen.setdefault("s", st) and 0)
    cli.main(["run", "--game", "stellaris"])
    assert seen["s"].model == "google:gemini-3.1-pro-preview" and seen["s"].governor_thinking == "high"
    seen.clear()
    cli.main(["run", "--game", "stellaris", "--model", "google:gemini-3.8-flash"])
    assert seen["s"].model == "google:gemini-3.8-flash"


def test_start_run_from_the_dashboard_saves_settings_and_starts_the_service(setup, monkeypatch):
    import asyncio

    from aiohttp.test_utils import TestClient, TestServer

    from pilot import cli, dashboard, models
    s, _ = setup
    calls = []

    class Proc:
        returncode = 0
        async def communicate(self):
            return b"", b""

    async def fake_exec(*args, **kw):
        calls.append(args)
        return Proc()

    monkeypatch.setattr(dashboard.asyncio, "create_subprocess_exec", fake_exec)

    async def go():
        async with TestClient(TestServer(dashboard.make_app(None, s.runs_dir))) as c:
            r = await c.post("/api/run", json={"game": "stellaris", "speed": "fast", "months": 6})
            assert r.status == 200, await r.text()
            assert (await c.post("/api/run", json={"game": "chess"})).status == 400
            assert (await c.post("/api/run", json={"months": 500})).status == 400

    asyncio.run(go())
    assert calls == [("systemctl", "--user", "start", "game-pilot.service")]
    assert models.load_prefs(s.runs_dir) == {"game": "stellaris", "speed": "fast", "months": 6}
    seen = {}
    monkeypatch.setenv("PILOT_RUNS_DIR", str(s.runs_dir))
    monkeypatch.setattr(cli, "run", lambda st, ep: seen.setdefault("s", st) and 0)
    cli.main(["run"])                                   # what the service runs
    assert (seen["s"].game, seen["s"].speed, seen["s"].decide_every_months) == ("stellaris", "fast", 6)


def test_campaign_title_comes_from_the_briefing_or_the_trace(setup, tmp_path):
    from pilot.telemetry import Telemetry
    s, _ = setup
    tel = Telemetry(tmp_path / "t.sqlite")
    log = EventLog(s.runs_dir, "r10", s.model, telemetry=tel)
    game = FakeStellaris([{**briefing("2200.01.01"), "source": "save games/e/x.sav", "name": "United Nations of Earth 2"}])
    Governor(s, game, log, model=decisions("keep")).run(max_decisions=1)
    assert tel.query("SELECT title FROM campaigns")[0]["title"] == "United Nations of Earth 2"
    # a campaign recorded before titles existed: filled from the trace's briefing line
    tel.record("old", {"t": 1, "kind": "run_start", "game": "stellaris", "model": "m"})
    tel.record("old", {"t": 1, "kind": "campaign", "game": "stellaris", "name": "folder_1"})
    tel.record("old", {"t": 2, "kind": "trace", "episode": 1, "date": "2201.01.01", "decision": "keep"},
               {"steps": [{"type": "prompt", "text": "Decision point.\nBriefing:\n# 2201.01.01 — Kilik Cooperative (country 3, v4.5.1)\n"}]})
    assert tel.query("SELECT title FROM campaigns WHERE id='stellaris/folder_1'")[0]["title"] == "Kilik Cooperative"


def test_a_transient_model_error_is_retried_and_the_decision_still_made(setup):
    from pydantic_ai.exceptions import ModelHTTPError
    s, log = setup
    s.retry_delays = (0, 0)
    calls = {"n": 0}

    def respond(messages, info: AgentInfo) -> ModelResponse:
        if _is_strategy_review(info):
            return _quiet_no_change(info)
        calls["n"] += 1
        if calls["n"] == 1:
            raise ModelHTTPError(status_code=503, model_name="gemini-3.8-flash", body={"error": "high demand"})
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"directive": "expand", "reason": "r"})])

    game = FakeStellaris([briefing("2200.01.01")])
    Governor(s, game, log, model=FunctionModel(respond)).run(max_decisions=1)
    assert ("directive", "expand") in game.actions
    retries = [e for e in log.recent if e["kind"] == "model_retry"]
    assert len(retries) == 1 and retries[0]["error"] == "model gemini-3.8-flash answered 503"
    assert not any(e["kind"] == "episode_error" for e in log.recent)


def test_a_permanent_model_error_is_not_retried(setup):
    from pydantic_ai.exceptions import ModelHTTPError
    s, log = setup
    s.retry_delays = (0, 0)
    calls = {"n": 0}

    def respond(messages, info: AgentInfo) -> ModelResponse:
        if _is_strategy_review(info):
            return _quiet_no_change(info)
        calls["n"] += 1
        raise ModelHTTPError(status_code=400, model_name="m", body={"error": "bad request"})

    Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=FunctionModel(respond)).run(max_decisions=1)
    assert calls["n"] == 1
    assert any(e["kind"] == "episode_error" for e in log.recent)


def test_responses_are_never_cached(setup):
    import asyncio

    from aiohttp.test_utils import TestClient, TestServer

    from pilot.dashboard import make_app
    s, _ = setup

    async def go():
        async with TestClient(TestServer(make_app(None, s.runs_dir))) as c:
            for path in ("/", "/status", "/api/campaigns", "/api/decision?run=x&episode=9"):
                assert (await c.get(path)).headers.get("Cache-Control") == "no-store", path

    asyncio.run(go())


def test_speed_and_months_can_be_changed_during_a_run(setup):
    import threading
    s, log = setup
    s.decide_every_months = 24
    s.poll_s = 0.05
    bs = [briefing(f"22{y:02d}.{m:02d}.01") for y in range(3) for m in (1, 7)]
    game = FakeStellaris(bs, advance_only_when_running=True)   # the speed request's extra read must not skip a save
    changed = {"done": False}
    inner = decisions("keep")

    def respond(messages, info: AgentInfo) -> ModelResponse:
        # change the pace while the first decision is being made (game paused), so the next poll is
        # guaranteed to see it; changing it from the test thread after the decision raced the poll
        if not changed["done"] and not _is_strategy_review(info):
            changed["done"] = True
            gov.set_speed("fastest")
            gov.set_months(6)                           # was 24: the next decision now comes at +6 months
        return inner.function(messages, info)

    gov = Governor(s, game, log, model=FunctionModel(respond))
    t = threading.Thread(target=gov.run, daemon=True)
    t.start()
    assert _wait(lambda: log.state.episodes >= 2, secs=5), log.state.episodes
    gov.stop(); t.join(timeout=5)
    assert ("speed", "fastest") in game.actions
    assert log.state.info["speed"] == "fastest" and log.state.info["every_months"] == 6
    eps = [e for e in log.recent if e["kind"] == "episode"]
    assert eps[1]["date"] == "2200.07.01", "decided 6 months after the first decision, not 24"
    with pytest.raises(ValueError):
        gov.set_speed("warp")
    with pytest.raises(ValueError):
        gov.set_months(0)


def test_pace_controls_over_the_dashboard(setup):
    import asyncio

    from aiohttp.test_utils import TestClient, TestServer

    from pilot import models
    from pilot.dashboard import make_app
    s, log = setup
    gov = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"))

    async def go():
        async with TestClient(TestServer(make_app(gov))) as c:
            assert (await c.post("/control", json={"action": "set_months", "months": 3})).status == 200
            assert (await c.post("/control", json={"action": "set_speed", "speed": "fast"})).status == 200
            assert (await c.post("/control", json={"action": "set_speed", "speed": "ludicrous"})).status == 400
            assert (await c.post("/control", json={"action": "set_months", "months": "many"})).status == 400
        async with TestClient(TestServer(make_app(None, s.runs_dir))) as v:     # no run: saved for later
            assert (await v.post("/api/settings", json={"speed": "slow", "months": 9})).status == 200

    asyncio.run(go())
    assert gov.s.decide_every_months == 3 and gov.requests.get_nowait() == ("speed", "fast")
    assert models.load_prefs(s.runs_dir) == {"speed": "slow", "months": 9}


def test_trends_compare_with_twelve_months_ago_and_flag_idle_alloys():
    from pilot.governor import trends
    old = {"date": "2230.01.01", "systems": 21, "pops": 6700, "military_power": 1000.0, "tech_power": 500.0,
           "stockpile": {"alloys": 1200.0}, "peers": {"military_power": {"median": 2000.0, "rank": 14}}}
    now = {"date": "2231.01.01", "systems": 21, "pops": 6900, "military_power": 1030.0, "tech_power": 540.0,
           "stockpile": {"alloys": 2240.0}, "peers": {"military_power": {"median": 2300.0, "rank": 14}}}
    t = trends(old, now)
    assert t.startswith("Change since 2230.01.01 (12 months):")
    assert "systems +0" in t and "pops +200" in t and "military +30 (the others' median +300)" in t
    assert "ALLOYS PILING UP" in t, t
    assert "ALLOYS" not in trends(old, {**now, "stockpile": {"alloys": 1300.0}})
    assert trends(None, now) == ""


def test_trends_never_claim_a_naval_cap_the_save_cannot_show():
    # Theian 2245-2254: the hint said "likely at naval capacity" while the fleet was at 51/115; the
    # models then chased naval-capacity techs for nine years.
    from pilot.governor import trends
    old = {"date": "2230.01.01", "military_power": 1000.0, "stockpile": {"alloys": 1200.0}}
    now = {"date": "2231.01.01", "military_power": 1030.0, "stockpile": {"alloys": 2240.0}}
    assert "naval capacity" not in trends(old, now)


def test_trends_flag_a_military_collapse_as_losses():
    from pilot.governor import trends
    old = {"date": "2244.07.01", "military_power": 3000.0, "stockpile": {"alloys": 300.0}}
    now = {"date": "2245.06.01", "military_power": 900.0, "stockpile": {"alloys": 400.0}}
    t = trends(old, now)
    assert "MILITARY FELL 70%" in t, t
    assert "MILITARY FELL" not in trends(old, {**now, "military_power": 2000.0})


def test_war_ending_is_urgent():
    from pilot.governor import urgent_changes
    war = {"name": "A vs B", "attacker": False}
    assert urgent_changes({"wars": [war]}, {"wars": []}) == ["war ended: A vs B"]


def test_metrics_keep_neighbours_for_comparison():
    from pilot.governor import metrics
    b = {"date": "2236.06.01", "neighbours": [{"id": 1, "name": "Ess Jaggon Authority", "military": 2475.0, "economy": 1282.0,
         "tech": 978.0, "systems": 27, "techs": 77, "borders": True, "border_range": 0, "opinion_ours": 681,
         "opinion_theirs": 681, "threat": 0, "status": ["alliance"], "kind": "default"}]}
    n = metrics(b)["neighbours"][0]
    assert n == {"name": "Ess Jaggon Authority", "military": 2475.0, "economy": 1282.0, "tech": 978.0, "systems": 27,
                 "opinion": 681, "status": ["alliance"]}


def test_a_crisis_appearing_is_urgent():
    from pilot.governor import urgent_changes
    before = {"galaxy": {"crises": []}}
    now = {"galaxy": {"crises": [["swarm", "Prethoryn Scourge", 90000.0]]}}
    assert urgent_changes(before, now) == ["crisis: Prethoryn Scourge (swarm) appeared"]
    assert urgent_changes(now, now) == []


def test_strategy_core_keeps_directives_lessons_and_identity():
    from pilot.config import REPO
    from pilot.governor import strategy_core
    core = strategy_core((REPO / "corpora/stellaris/strategy.md").read_text(encoding="utf-8"))
    assert "## 9. Governor directives" in core
    assert "## 10. Lessons from play" in core and "## 11. Species and empire identity" in core
    assert "## 8. Crisis preparation" not in core and "Crisis preparation" in core, "other sections stay in the index"


def test_a_stale_autosave_at_start_waits_for_a_fresh_one(setup):
    """A new or just-loaded game has no autosave of its own yet: the newest one belongs to another
    campaign. The governor plays one month for a fresh save before its first decision."""
    import time as _t
    s, log = setup
    old = {**briefing("2318.02.01"), "source": "save games/unitednationsofearth2_-6/autosave_2318.02.01.sav",
           "source_modified": _t.time() - 3600}
    new = {**briefing("2200.02.01"), "source": "save games/federatedtheian_-19/autosave_2200.02.01.sav",
           "source_modified": _t.time()}
    game = FakeStellaris([old, old, new, new])
    Governor(s, game, log, model=decisions("expand")).run(max_decisions=1)
    assert log.campaign_id == "stellaris/federatedtheian_-19"
    assert ("paused", False) in game.actions, "the game ran to write a fresh autosave"
    assert any(e["kind"] == "journal" and "fresh autosave" in e.get("text", "") for e in log.recent)


def test_an_overloaded_model_falls_back_to_the_other_one(setup):
    from pydantic_ai.exceptions import ModelHTTPError
    s, log = setup
    from dataclasses import replace
    s = replace(s, retry_delays=(0,))
    s.__class__ = setup[0].__class__

    def overloaded(messages, info):
        raise ModelHTTPError(503, "gemini-3.6-flash", "high demand")
    game = FakeStellaris([briefing("2200.01.01")])
    Governor(s, game, log, model=FunctionModel(overloaded), fallback=decisions("expand")).run(max_decisions=1)
    kinds = [e["kind"] for e in log.recent]
    assert "model_fallback" in kinds
    assert "governor_directive_expand" in game.flags, "the fallback model's decision was applied"


def test_fallback_model_is_saved_and_switchable_live(setup, tmp_path):
    from pilot.models import load_prefs, save_prefs
    assert save_prefs(tmp_path, fallback="google:gemini-3.1-pro-preview")["fallback"] == "google:gemini-3.1-pro-preview"
    assert load_prefs(tmp_path)["fallback"] == "google:gemini-3.1-pro-preview"
    assert save_prefs(tmp_path, fallback="none")["fallback"] == "none", "the fallback can be switched off"
    with pytest.raises(ValueError):
        save_prefs(tmp_path, fallback="not a model")
    s, log = setup
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"))
    first = g.s.pool()[0]
    g.set_fallback("google:gemini-3.7-flash")      # older control: the pool becomes first + this one
    assert log.state.info["pool"] == [first, {"model": "google:gemini-3.7-flash", "thinking": first["thinking"]}]
    g.set_fallback("none")
    assert log.state.info["pool"] == [first]
    assert "set_fallback" in log.state.info["controls"]


# ---- model pool: providers, per-model thinking, taking turns ----------------------------------

def test_model_pool_prefs_roundtrip_and_old_settings(tmp_path):
    import json as _json

    from pilot.models import load_prefs, save_prefs
    pool = [{"model": "google:gemini-3.1-pro-preview", "thinking": "medium"},
            {"model": "anthropic:claude-sonnet-5", "thinking": "high"}]
    p = save_prefs(tmp_path, models=pool, rotate=True)
    assert p["models"] == pool and p["rotate"] is True
    assert p["model"] == "google:gemini-3.1-pro-preview" and p["thinking"] == "medium", "first model mirrored for older readers"
    assert load_prefs(tmp_path)["models"] == pool
    for bad in ([], [{"model": "nope", "thinking": "low"}], [{"model": "google:x", "thinking": "extreme"}],
                [{"model": f"google:m{i}", "thinking": "low"} for i in range(7)]):
        with pytest.raises(ValueError):
            save_prefs(tmp_path, models=bad)
    # settings saved before the pool existed: model + thinking + fallback
    (tmp_path / "pilot-settings.json").write_text(_json.dumps(
        {"model": "google:gemini-3.6-flash", "thinking": "high", "fallback": "google:gemini-3.1-pro-preview"}))
    assert load_prefs(tmp_path)["models"] == [{"model": "google:gemini-3.6-flash", "thinking": "high"},
                                              {"model": "google:gemini-3.1-pro-preview", "thinking": "high"}]


def test_thinking_settings_per_provider():
    from dataclasses import replace

    from pilot.agent import model_settings
    s = Settings()
    g = model_settings(replace(s, model="google:gemini-3.1-pro-preview", thinking="high"))
    assert g["google_thinking_config"]["thinking_level"] == "high"
    a = model_settings(replace(s, model="anthropic:claude-sonnet-5", thinking="medium"))
    assert a["thinking"] == "medium" and "google_thinking_config" not in a
    assert model_settings(replace(s, model="anthropic:claude-sonnet-5", thinking="off"))["thinking"] is False
    o = model_settings(replace(s, model="openai:gpt-5", thinking="low"))
    assert o["openai_reasoning_effort"] == "low"


def _recording(name, calls):
    def respond(messages, info):
        if _is_strategy_review(info):
            return _quiet_no_change(info)
        calls.append(name)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"directive": "keep", "reason": name})])
    return FunctionModel(respond)


def test_models_take_turns_when_rotation_is_on(setup):
    from dataclasses import replace
    s, log = setup
    calls = []
    s2 = replace(s, rotate=True)
    s2.__class__ = s.__class__
    game = FakeStellaris([briefing("2200.01.01"), briefing("2201.01.01"), briefing("2202.01.01")])
    Governor(s2, game, log, model=_recording("a", calls), fallback=_recording("b", calls)).run(max_decisions=3)
    assert calls == ["a", "b", "a"]


def test_first_model_decides_when_rotation_is_off(setup):
    s, log = setup
    calls = []
    game = FakeStellaris([briefing("2200.01.01"), briefing("2201.01.01")])
    Governor(s, game, log, model=_recording("a", calls), fallback=_recording("b", calls)).run(max_decisions=2)
    assert calls == ["a", "a"]


def test_model_pool_can_be_changed_live(setup):
    s, log = setup
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"))
    g.set_models([{"model": "google:gemini-3.1-pro-preview", "thinking": "low"},
                  {"model": "anthropic:claude-sonnet-5", "thinking": "high"}], rotate=True)
    assert log.state.info["pool"] == [{"model": "google:gemini-3.1-pro-preview", "thinking": "low"},
                                        {"model": "anthropic:claude-sonnet-5", "thinking": "high"}]
    assert log.state.info["rotate"] is True and log.state.model == "google:gemini-3.1-pro-preview"
    with pytest.raises(ValueError):
        g.set_models([], rotate=False)
    assert "set_models" in log.state.info["controls"]


def test_provider_catalog_shows_which_providers_have_keys(monkeypatch):
    from pilot.models import provider_catalog
    monkeypatch.setenv("GOOGLE_API_KEY", "x")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    cat = {p["id"]: p for p in provider_catalog(Settings(), list_models=lambda provider: [f"{provider}:m1"])}
    assert set(cat) >= {"google", "anthropic", "openai"}
    assert cat["google"]["configured"] and cat["google"]["models"] == ["google:m1"]
    assert not cat["anthropic"]["configured"] and cat["anthropic"]["models"] == []
    assert cat["anthropic"]["key_env"] == "ANTHROPIC_API_KEY"


# ---- model roles: decisions, strategy and talk can each have their own models ------------------

def test_the_strategist_uses_its_own_model(setup):
    from dataclasses import replace
    s, log = setup
    s2 = replace(s, retro_every=1)
    s2.__class__ = s.__class__
    calls = []
    game = FakeStellaris([briefing(f"22{i:02d}.01.01") for i in range(4)])
    Governor(s2, game, log, model=_recording("decide", calls),
             role_models={"strategy": _strategist(calls)}).run(max_decisions=2)
    # the strategist reviews at the start of the run, then again after the next decision (retro_every=1)
    assert calls == ["strategist", "decide", "decide", "strategist"], calls


def test_roles_without_their_own_models_use_the_decision_models(setup):
    s, log = setup
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"))
    assert [e["model"] for e in g._pool("strategy")] == [e["model"] for e in g._pool("decisions")]
    g.set_roles({"chat": {"models": [{"model": "anthropic:claude-haiku-4-5", "thinking": "off"}], "rotate": False}})
    assert [e["model"] for e in g._pool("chat")] == ["anthropic:claude-haiku-4-5"]
    assert g._pool("strategy")[0]["model"] == g._pool("decisions")[0]["model"], "unset roles follow decisions"
    assert log.state.info["roles"] == {"chat": {"models": [{"model": "anthropic:claude-haiku-4-5", "thinking": "off"}], "rotate": False}}
    g.set_roles({"chat": None})
    assert log.state.info["roles"] == {}
    with pytest.raises(ValueError):
        g.set_roles({"nonsense": {"models": [{"model": "google:x", "thinking": "low"}]}})


def test_role_settings_are_saved(tmp_path):
    from pilot.models import load_prefs, save_prefs
    roles = {"strategy": {"models": [{"model": "google:gemini-3.1-pro-preview", "thinking": "high"}], "rotate": False}}
    assert save_prefs(tmp_path, roles=roles)["roles"] == roles
    assert load_prefs(tmp_path)["roles"] == roles
    assert "strategy" not in save_prefs(tmp_path, roles={"strategy": None}).get("roles", {}), "None = same as decisions"


def test_any_model_failure_moves_on_to_the_next_model(setup):
    """Not only overload: a bad key, a missing model or an unusable answer also hands over."""
    from pydantic_ai.exceptions import ModelHTTPError
    s, log = setup
    calls = []

    def broken(messages, info):
        if _is_strategy_review(info):
            return _quiet_no_change(info)
        calls.append("a")
        raise ModelHTTPError(401, "anthropic:claude-x", "invalid x-api-key")
    game = FakeStellaris([briefing("2200.01.01")])
    Governor(s, game, log, model=FunctionModel(broken), fallback=_recording("b", calls)).run(max_decisions=1)
    assert calls == ["a", "b"], "a non-transient error is not retried; the next model decides"
    assert any(e["kind"] == "model_fallback" for e in log.recent)


def test_a_failing_model_cools_down_behind_the_others(setup):
    from dataclasses import replace

    from pydantic_ai.exceptions import ModelHTTPError
    s, log = setup
    s2 = replace(s, retry_delays=(0,))
    s2.__class__ = s.__class__
    calls = []

    def overloaded(messages, info):
        if _is_strategy_review(info):
            return _quiet_no_change(info)
        calls.append("a")
        raise ModelHTTPError(503, "gemini", "high demand")
    game = FakeStellaris([briefing("2200.01.01"), briefing("2201.01.01"), briefing("2202.01.01")])
    Governor(s2, game, log, model=FunctionModel(overloaded), fallback=_recording("b", calls)).run(max_decisions=2)
    # decision 1: a (+1 retry) fails, b answers; decision 2: a is cooling down, so b goes first
    assert calls == ["a", "a", "b", "b"], calls


def test_strategy_versions_are_stored_per_campaign(tmp_path):
    from pilot.events import EventLog
    from pilot.telemetry import Telemetry
    tel = Telemetry(tmp_path / "t.sqlite")
    log = EventLog(tmp_path / "runs", "r1", "m", telemetry=tel)
    log.emit("run_start", game="stellaris", model="m")
    log.set_campaign("stellaris", "theian_1", "Theian")
    log.emit("metrics", date="2240.01.01", planets=4)
    log.emit("strategy", date="2240.01.01", trigger="start of run", model="m", reason="first",
             strategy={"pillars": {}, "focus": "grow"})
    log.emit("strategy", date="2245.01.01", trigger="war started", model="m", reason="war",
             strategy={"pillars": {}, "focus": "defend"})
    cid = log.campaign_id
    assert tel.latest_strategy(cid)["focus"] == "defend"
    hist = tel.strategy_history(cid)
    assert [h["trigger"] for h in hist] == ["war started", "start of run"]
    assert tel.metrics_rows(cid)[0]["planets"] == 4
    assert tel.latest_strategy("nope") is None


# ---- Task 3: the Strategist (role `strategy`) replaces the retrospective -----------------------

def _strategist(calls, *, change=True, pin_diplomacy_to=None):
    prios = {"defence": 1, "economy": 2, "technology": 3, "expansion": 4, "diplomacy": 5, "government": 6, "society": 7}

    def respond(messages, info):
        calls.append("strategist")
        pillars = _pillars_body(prios)
        if pin_diplomacy_to:
            pillars["diplomacy"]["stance"] = pin_diplomacy_to
        body = {"change": change, "assessment": "ok", "rules": [],
                "strategy": {**pillars, "focus": "grow", "reason": "start"} if change else None}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, body)])
    return FunctionModel(respond)


def test_a_strategy_is_set_at_the_start_of_a_run(setup):
    s, log = setup
    calls = []
    Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=_recording("decide", calls),
             role_models={"strategy": _strategist(calls)}).run(max_decisions=1)
    assert calls[0] == "strategist" and calls[1] == "decide"
    assert any(e["kind"] == "strategy" for e in log.recent)


def test_a_no_change_review_writes_no_version(setup):
    from dataclasses import replace
    s, log = setup
    s2 = replace(s, retro_every=1)
    s2.__class__ = s.__class__
    calls = []
    first = _strategist(calls)
    g = Governor(s2, FakeStellaris([briefing(f"22{i:02d}.01.01") for i in range(3)]), log,
                 model=_recording("decide", calls), role_models={"strategy": first})
    g.run(max_decisions=1)
    g._role_objs["strategy"] = _strategist(calls, change=False)
    g.__dict__.pop("_agents", None)
    g._review_strategy(briefing("2202.01.01"), "scheduled")
    assert sum(1 for e in log.recent if e["kind"] == "strategy") == 1
    assert any(e["kind"] == "strategy_review" and not e["change"] for e in log.recent)


def test_the_strategist_cannot_change_a_pinned_pillar(setup):
    from pilot.strategy import Pillar
    s, log = setup
    calls = []
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=_recording("decide", calls),
                 role_models={"strategy": _strategist(calls)})
    g._review_strategy(briefing("2200.01.01"), "start of run")
    g.strategy.pillars["diplomacy"] = Pillar(priority=5, stance="no federations", goals=["g"], pinned=True, edited_by="human")
    g._role_objs["strategy"] = _strategist(calls, pin_diplomacy_to="join a federation")
    g.__dict__.pop("_agents", None)
    g._review_strategy(briefing("2201.01.01"), "scheduled")
    assert g.strategy.pillars["diplomacy"].stance == "no federations"


def test_an_invalid_strategy_is_retried_once_then_dropped(setup):
    s, log = setup
    calls = []

    def bad(messages, info):
        calls.append("bad")
        body = {"change": True, "assessment": "x", "rules": [], "strategy": {"pillars": {}, "focus": "f", "reason": "r"}}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, body)])
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"), role_models={"strategy": FunctionModel(bad)})
    g._review_strategy(briefing("2200.01.01"), "start of run")
    assert calls == ["bad", "bad"] and g.strategy is None
    assert any(e["kind"] == "strategy_rejected" for e in log.recent)


def test_saved_retrospective_models_move_to_the_strategy_role(tmp_path):
    import json as _json

    from pilot.models import ROLE_IDS, load_prefs
    assert "strategy" in ROLE_IDS and "retrospective" not in ROLE_IDS
    (tmp_path / "pilot-settings.json").write_text(_json.dumps({"roles": {"retrospective": {
        "models": [{"model": "google:gemini-3.1-pro-preview", "thinking": "high"}], "rotate": False}}}))
    assert load_prefs(tmp_path)["roles"]["strategy"]["models"][0]["model"] == "google:gemini-3.1-pro-preview"


def test_strategy_instructions_cover_the_defence_naval_cap_ruling():
    from pilot.strategy import strategist_instructions
    text = strategist_instructions(STELLARIS)
    assert ("While at war, the defence stance must name its exit condition (peace, war exhaustion, "
            "or planets retaken).") in text
    assert ("When a hostile neighbour's military is twice ours or more, a defence goal is two "
            "shipyards in different systems and alloy production on two or more planets; never "
            "reason from a naval-capacity cap the briefing does not show.") in text


def test_strategy_instructions_forbid_trade_market_orders():
    from pilot.strategy import strategist_instructions
    assert ("Market orders cannot use trade; sell only idle energy, minerals, food, consumer goods "
            "or alloys (strategic resources can only be bought).") in strategist_instructions(STELLARIS)


def test_strategy_instructions_allow_at_most_one_small_monthly_order():
    from pilot.strategy import strategist_instructions
    text = strategist_instructions(STELLARIS)
    assert "at most 1 small monthly order" in text and "at most 2 small" not in text


def test_strategy_instructions_list_every_metric_name():
    from pilot.strategy import strategist_instructions
    for m in STELLARIS.metrics:
        assert m in strategist_instructions(STELLARIS), m


def test_the_strategist_receives_the_naval_cap_ruling_in_its_prompt(setup):
    s, log = setup
    seen = []

    def respond(messages, info):
        seen.append(info.instructions or "")
        body = {"change": False, "assessment": "ok", "rules": [], "strategy": None}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, body)])

    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"),
                 role_models={"strategy": FunctionModel(respond)})
    g._review_strategy(briefing("2200.01.01"), "start of run")
    combined = " ".join(seen)
    assert "the defence stance must name its exit condition" in combined
    assert "never reason from a naval-capacity cap the briefing does not show" in combined


# ---- Task 3 fix round 1 -------------------------------------------------------------------------

def test_strategy_review_updates_bookkeeping_and_saves_a_trace(setup):
    """Item 1: tokens/requests grow, rules learned are counted, and a trace file is saved, like decisions."""
    s, log = setup
    prios = {"defence": 1, "economy": 2, "technology": 3, "expansion": 4, "diplomacy": 5, "government": 6, "society": 7}

    def respond(messages, info):
        pillars = _pillars_body(prios)
        body = {"change": True, "assessment": "ok", "rules": ["Always expand early."],
                "strategy": {"pillars": pillars, "focus": "grow", "reason": "start"}}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, body)])

    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"),
                 role_models={"strategy": FunctionModel(respond)})
    before = (log.state.tokens_in, log.state.requests, log.state.learned["rules"])
    g._review_strategy(briefing("2200.01.01"), "start of run")
    assert log.state.tokens_in > before[0]
    assert log.state.requests > before[1]
    assert log.state.learned["rules"] == before[2] + 1
    trace_files = sorted((log.dir / "traces").glob("*.json"))
    assert trace_files, "a trace file was saved for the review"
    import json as _json
    tr = _json.loads(trace_files[0].read_text())
    assert tr["decision"] == "strategy_review" and tr["trigger"] == "start of run"
    assert any(e["kind"] == "journal" or e["kind"] == "trace" for e in log.recent)


def test_a_crash_after_the_model_call_never_pauses_the_game(setup, monkeypatch):
    """Item 2: any exception past the model call (keep_pinned, validate, _set_strategy, event emits) is
    caught, logged as an episode_error (not mislabeled as a game-control failure), review_requested is
    set, the current strategy is kept, and the game is never paused; the decision still happens."""
    import pilot.governor as governor_mod
    s, log = setup
    calls = []

    def boom(*a, **k):
        raise KeyError("boom")

    monkeypatch.setattr(governor_mod, "validate", boom)
    game = FakeStellaris([briefing("2200.01.01")])
    g = Governor(s, game, log, model=decisions("expand"), role_models={"strategy": _strategist(calls)})
    g.run(max_decisions=1)
    assert g.strategy is None
    assert g.review_requested == "start of run"
    errs = [e for e in log.recent if e["kind"] == "episode_error"]
    assert errs and "strategy review" in errs[0]["error"] and "game control" not in errs[0]["error"]
    assert ("directive", "expand") in game.actions, "the decision still happened"
    assert log.state.status != "needs_attention"
    assert g.control.paused is False


def test_change_true_without_a_strategy_is_retried_as_invalid_output(setup):
    """Item 3: change=true with strategy=None is an invalid answer, retried once (not silently kept)."""
    s, log = setup
    calls = []

    def respond(messages, info):
        calls.append(1)
        body = {"change": True, "assessment": "x", "rules": [], "strategy": None}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, body)])

    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"),
                 role_models={"strategy": FunctionModel(respond)})
    g._review_strategy(briefing("2200.01.01"), "start of run")
    assert len(calls) == 2, "retried once with the reasons"
    assert g.strategy is None
    rejected = [e for e in log.recent if e["kind"] == "strategy_rejected"]
    assert rejected and "change=true but no strategy given" in rejected[0]["errors"][0]


def test_a_rejected_then_retried_review_emits_one_strategy_review_per_answer(setup):
    """Item 5: strategy_review is emitted after validation, once per model answer, each with `change`
    (as the model answered) and `accepted` (whether a version was actually written) set correctly."""
    s, log = setup
    calls = []

    def bad(messages, info):
        calls.append("bad")
        body = {"change": True, "assessment": "x", "rules": [], "strategy": {"pillars": {}, "focus": "f", "reason": "r"}}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, body)])

    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"), role_models={"strategy": FunctionModel(bad)})
    g._review_strategy(briefing("2200.01.01"), "start of run")
    assert calls == ["bad", "bad"]
    reviews = [e for e in log.recent if e["kind"] == "strategy_review"]
    assert len(reviews) == 2, reviews
    assert [r["change"] for r in reviews] == [True, True]
    assert [r["accepted"] for r in reviews] == [False, False]


def test_load_prefs_ignores_a_malformed_roles_value(tmp_path):
    """Item 6: a non-dict `roles` in a saved settings file is ignored, not a crash."""
    import json as _json

    from pilot.models import load_prefs
    (tmp_path / "pilot-settings.json").write_text(_json.dumps({"roles": 5}))
    assert load_prefs(tmp_path).get("roles", {}) == {}


def test_tech_ids_read_failure_is_not_cached_and_logs_an_event(setup):
    """Item 4: a failed tech.json read logs an event and is retried on the next call (never cached empty)."""
    s, log = setup
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"))
    assert g._tech_ids() == set()               # the test corpus fixture has no data/tech.json
    assert any(e["kind"] == "briefing_error" and "tech ids" in e["error"] for e in log.recent)
    n_errors = sum(1 for e in log.recent if e["kind"] == "briefing_error" and "tech ids" in e["error"])
    assert g._tech_ids() == set()
    assert sum(1 for e in log.recent if e["kind"] == "briefing_error" and "tech ids" in e["error"]) == n_errors + 1, \
        "retried (and logged again), not cached as an empty set"


def test_retro_every_skips_the_start_decision_when_a_review_just_ran(setup):
    """Item 7 (half 1): the start-of-run decision does not also count toward the schedule when the
    strategist already reviewed for it."""
    from dataclasses import replace
    s, log = setup
    s2 = replace(s, retro_every=1)
    s2.__class__ = s.__class__
    calls = []
    g = Governor(s2, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("expand"),
                 role_models={"strategy": _strategist(calls)})
    g.run(max_decisions=1)
    assert calls == ["strategist"], calls
    assert g._since_retro == 0


def test_retro_every_counts_the_start_decision_when_no_review_ran(setup, tmp_path):
    """Item 7 (half 2): when the campaign already has a strategy (no start-of-run review runs), the
    start-of-run decision counts toward the schedule like any other."""
    from dataclasses import replace

    from pilot.telemetry import Telemetry
    s, _ = setup
    s2 = replace(s, retro_every=1)
    s2.__class__ = s.__class__
    tel = Telemetry(tmp_path / "t.sqlite")
    src = "save games/emp_x/x.sav"
    seed = EventLog(s2.runs_dir, "seed", s2.model, telemetry=tel)
    seed.emit("run_start", game="stellaris", model=s2.model)
    seed.set_campaign("stellaris", "emp_x", "Empire X")
    strategy = {"pillars": {p: {"priority": i + 1, "stance": f"{p} s", "goals": ["g"]} for i, p in enumerate(STELLARIS.ids)},
                "focus": "grow", "reason": "seed"}
    seed.emit("strategy", date="2199.01.01", trigger="start of run", model="seed", reason="seed", strategy=strategy)

    calls = []
    log2 = EventLog(s2.runs_dir, "run2", s2.model, telemetry=tel)
    g = Governor(s2, FakeStellaris([{**briefing("2200.01.01"), "source": src}]), log2, model=decisions("expand"),
                 role_models={"strategy": _strategist(calls)})
    g._set_campaign({**briefing("2200.01.01"), "source": src})
    assert g.strategy is not None and g.strategy.reason == "seed", "item 9: reason survives the reload"
    g.run(max_decisions=1)
    assert calls == ["strategist"], calls           # only the scheduled review fires, not a start-of-run one
    reviews = [e for e in log2.recent if e["kind"] == "strategy_review"]
    assert reviews and reviews[0]["trigger"] == "scheduled after 1 decisions"


def test_when_every_strategy_model_fails_play_continues_with_the_current_strategy(setup):
    """Item 8: every model in the strategy role failing never blocks a decision."""
    s, log = setup

    def always_fails(messages, info):
        raise RuntimeError("boom")

    game = FakeStellaris([briefing("2200.01.01")])
    g = Governor(s, game, log, model=decisions("expand"), role_models={"strategy": FunctionModel(always_fails)})
    g.run(max_decisions=1)
    assert g.strategy is None
    assert g.review_requested == "start of run"
    assert any(e["kind"] == "episode_error" and "strategy review" in e["error"] for e in log.recent)
    assert ("directive", "expand") in game.actions, "play continued: the real decision still happened"


# ---- Task 3 fix round 2: strategy review rows are not directive decisions ------------------------

def test_strategy_review_rows_are_excluded_from_directive_decision_readers(setup, tmp_path):
    """A strategy review's own trace row (decision='strategy_review') must never be read as a directive
    decision: not in past_outcomes() text, never scored by score(), and not listed by the dashboard's
    campaign/decisions APIs (Task 9 adds its own, deliberate review marks)."""
    import asyncio

    from aiohttp.test_utils import TestClient, TestServer

    from pilot.dashboard import make_app
    from pilot.telemetry import Telemetry
    s, _ = setup
    tel = Telemetry(tmp_path / "t.sqlite")
    log = EventLog(s.runs_dir, "run10", s.model, telemetry=tel)
    src = "save games/rev_1/x.sav"
    game = FakeStellaris([{**briefing("2200.01.01"), "source": src}, {**briefing("2201.01.01"), "source": src}])
    Governor(s, game, log, model=decisions("expand", "keep")).run(max_decisions=2)
    cid = "stellaris/rev_1"

    # past_outcomes(): the review is absent, not just outnumbered by real decisions
    text = tel.past_outcomes(cid)
    assert "strategy_review" not in text
    assert "2200.01.01 | expand (from none)" in text

    # score(): review rows are never scored, even though they carry a date/month like a decision
    rows = tel.query("SELECT decision, result FROM decisions WHERE campaign_id=?", (cid,))
    review_rows = [r for r in rows if r["decision"] == "strategy_review"]
    assert review_rows, "the start-of-run review did trace its own row"
    assert all(r["result"] is None for r in review_rows)

    async def go():
        async with TestClient(TestServer(make_app(None, s.runs_dir, tel))) as c:
            camps = await (await c.get("/api/campaigns")).json()
            assert camps[0]["decisions"] == 2, "only the 2 real decisions, not the review"
            ds = await (await c.get("/api/decisions", params={"campaign": cid})).json()
            assert [d["decision"] for d in ds] == ["expand", "keep"]

    asyncio.run(go())


# ---- Task 4: decisions work inside the frame; event reviews; request limit ---------------------

def test_decisions_get_the_strategy_frame(setup):
    s, log = setup
    seen = []

    def respond(messages, info):
        seen.append(" ".join(str(p.content) for m in messages for p in getattr(m, "parts", []) if hasattr(p, "content")))
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"directive": "keep", "reason": "r"})])
    calls = []
    Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=FunctionModel(respond),
             role_models={"strategy": _strategist(calls)}).run(max_decisions=1)
    assert any("STRATEGY FRAME" in t and "defend > consolidate_economy > tech_rush > expand > diplomacy_first" in t for t in seen)


def test_an_off_frame_choice_is_tagged_and_schedules_a_review(setup):
    s, log = setup
    calls = []
    g = Governor(s, FakeStellaris([briefing("2200.01.01"), briefing("2201.01.01", net={"energy": -5.0})]), log,
                 model=decisions("keep", "diplomacy_first"), role_models={"strategy": _strategist(calls)})
    g.run(max_decisions=2)
    traces = [e for e in log.recent if e["kind"] == "trace" and e.get("decision") == "diplomacy_first"]
    assert traces and traces[-1].get("off_frame") is True
    assert g.review_requested and "off-frame" in g.review_requested


def test_event_reviews_are_capped_at_one_per_year(setup):
    s, log = setup
    calls = []
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"), role_models={"strategy": _strategist(calls)})
    g._review_strategy(briefing("2200.01.01"), "start of run")
    assert g._maybe_event_review(briefing("2201.01.01"), "war started") is True
    assert g._maybe_event_review(briefing("2201.06.01"), "war ended") is False, "within 12 months of the last event review"
    assert g._maybe_event_review(briefing("2202.02.01"), "war ended") is True


def test_the_decision_request_limit_is_six():
    assert Settings().governor_max_requests == 6


# ---- Task 4 rulings -------------------------------------------------------------------------

def test_a_failed_reviews_retry_bypasses_the_event_cap_and_a_success_clears_it(setup):
    """Ruling: a retry of a failed review (review_requested set by a failure) bypasses the 12-month
    event cap and does not move the cap's last-review month; a successful retry clears
    review_requested. The failed start review is retried at the next (scheduled) decision."""
    from dataclasses import replace

    s, log = setup
    s2 = replace(s, decide_every_months=1)
    s2.__class__ = s.__class__
    prios = {"defence": 1, "economy": 2, "technology": 3, "expansion": 4, "diplomacy": 5, "government": 6, "society": 7}
    n = {"count": 0}

    def respond(messages, info):
        n["count"] += 1
        if n["count"] == 1:
            raise RuntimeError("boom")
        pillars = _pillars_body(prios)
        body = {"change": True, "assessment": "ok", "rules": [],
                "strategy": {"pillars": pillars, "focus": "grow", "reason": "retry"}}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, body)])

    game = FakeStellaris([briefing("2200.01.01"), briefing("2200.02.01")])
    g = Governor(s2, game, log, model=decisions("keep", "keep"), role_models={"strategy": FunctionModel(respond)})
    g.run(max_decisions=2)
    assert n["count"] == 2, "the failed start review was retried exactly once, at the next decision"
    assert g.strategy is not None and g.strategy.reason == "retry"
    assert g.review_requested is None, "a successful retry clears review_requested"
    assert getattr(g, "_last_event_review_month", None) is None, \
        "a retry of a failed review does not update the cap's last-review month"


def test_off_frame_does_not_fire_for_keep_even_when_current_is_top_ranked(setup):
    """Ruling: the off-frame tag (and the review it schedules) must not fire for 'keep' of the
    current directive when the current directive is itself top-ranked."""
    from pilot.strategy import ranking
    s, log = setup
    calls = []
    game = FakeStellaris([briefing("2200.01.01"), briefing("2201.01.01")])
    g = Governor(s, game, log, model=decisions("defend", "keep"), role_models={"strategy": _strategist(calls)})
    g.run(max_decisions=2)
    assert ranking(g.strategy, STELLARIS)[0] == "defend", "defend is top-ranked and is the current directive"
    traces = [e for e in log.recent if e["kind"] == "trace" and e.get("decision") == "keep"]
    assert traces and traces[-1].get("off_frame") is False
    assert g.review_requested is None


def test_off_frame_does_not_fire_when_no_strategy_exists_yet(setup):
    """Ruling: the off-frame tag (and the review it schedules) must not fire when no strategy
    exists yet, however far the choice would otherwise be from a (non-existent) ranking."""
    s, log = setup

    def always_fails(messages, info):
        raise RuntimeError("boom")

    game = FakeStellaris([briefing("2200.01.01")])
    g = Governor(s, game, log, model=decisions("diplomacy_first"), role_models={"strategy": FunctionModel(always_fails)})
    g.run(max_decisions=1)
    assert g.strategy is None
    traces = [e for e in log.recent if e["kind"] == "trace" and e.get("decision") == "diplomacy_first"]
    assert traces and traces[-1].get("off_frame") is False


def test_urgent_changes_flags_colony_loss_being_boxed_in_and_a_military_collapse():
    before = {**briefing("2200.01.01"), "planets": [{}, {}, {}], "expansion": {"reach_unclaimed": 4},
              "military_power": 1000}
    now = {**briefing("2200.02.01"), "planets": [{}, {}], "expansion": {"reach_unclaimed": 0},
           "military_power": 400}
    reasons = urgent_changes(before, now)
    assert any("colony lost: 3 -> 2" in r for r in reasons)
    assert any(r == "boxed in" for r in reasons)
    assert any("military fell: 1000 -> 400" in r for r in reasons)
    assert urgent_changes(now, now) == [], "no further loss, and already boxed in, does not re-trigger"


def test_military_falling_by_half_triggers_an_early_decision_and_a_capped_review(setup):
    """Ruling: 'military fell' is an EVENT_TRIGGERS member (it schedules a review), still capped at
    one per 12 in-game months like any other event trigger."""
    from pilot.governor import EVENT_TRIGGERS
    assert "military fell" in EVENT_TRIGGERS
    s, log = setup
    calls = []
    b0 = {**briefing("2200.01.01"), "military_power": 1000}
    b1 = {**briefing("2200.03.01"), "military_power": 400}
    game = FakeStellaris([b0, b1])
    g = Governor(s, game, log, model=decisions("keep", "keep"), role_models={"strategy": _strategist(calls)})
    g.run(max_decisions=2)
    ep = [e for e in log.recent if e["kind"] == "episode"][1]
    assert ep["situation"].startswith("urgent: military fell: 1000 -> 400")
    assert any(e["kind"] == "strategy_review" and "military fell" in e["trigger"] for e in log.recent)


# ---- Task 4 fix round 1 ----------------------------------------------------------------------

def test_off_frame_reviews_are_capped_and_a_refused_one_is_dropped(setup):
    """Item 1 (critical): off-frame requests go through the *normal* capped review path (unlike a
    failed review's own retry, which bypasses it) — 8 off-frame decisions within 12 in-game months
    produce at most one strategist review, and a refused (capped) request is dropped rather than
    re-firing on every later decision."""
    from dataclasses import replace
    s, log = setup
    s2 = replace(s, decide_every_months=1, retro_every=0)   # isolate the off-frame path from the periodic retrospective
    s2.__class__ = s.__class__
    calls = []
    # ranking (from _strategist): defend > consolidate_economy > tech_rush > expand > diplomacy_first;
    # the top 2 (defend, consolidate_economy) are never picked, so every one of these 8 is off-frame,
    # and consecutive picks always differ from `current` so off_frame fires every single time
    choices = ("tech_rush", "expand", "diplomacy_first", "tech_rush", "expand", "diplomacy_first", "tech_rush", "expand")
    game = FakeStellaris([briefing(f"2200.{i:02d}.01") for i in range(1, 9)])
    g = Governor(s2, game, log, model=decisions(*choices), role_models={"strategy": _strategist(calls)})
    g.run(max_decisions=8)
    reviews = [e for e in log.recent if e["kind"] == "strategy_review"]
    off_frame_reviews = [r for r in reviews if r["trigger"].startswith("off-frame")]
    assert len(off_frame_reviews) == 1, reviews   # the mandatory start-of-run review is separate
    skips = [e for e in log.recent if e["kind"] == "strategy_review_skipped"]
    assert skips and all(s["reason"] == "within 12 months of the last event review" for s in skips)
    assert g.review_requested is None, "the last refused request was dropped, not left to re-fire forever"


def test_military_fell_compares_against_the_last_decisions_briefing_not_the_previous_poll(setup):
    """Item 2 (important): a slow decline that never drops >=50% between two consecutive polls, but
    has dropped >=50% since the briefing of the last decision, still fires 'military fell'."""
    s, log = setup
    calls = []
    b0 = {**briefing("2200.01.01"), "military_power": 1000}
    polls = [{**briefing(f"2200.0{i}.01"), "military_power": m} for i, m in zip(range(2, 6), (850, 700, 550, 400))]
    game = FakeStellaris([b0, *polls])
    g = Governor(s, game, log, model=decisions("keep", "keep"), role_models={"strategy": _strategist(calls)})
    g.run(max_decisions=2)
    ep = [e for e in log.recent if e["kind"] == "episode"][1]
    assert ep["situation"].startswith("urgent: military fell: 1000 -> 400"), ep["situation"]
    assert ep["date"] == "2200.05.01", "fires only once the cumulative drop from the last decision reaches half"


def test_the_off_frame_cutoff_is_the_top_two_of_the_ranking(setup):
    """Item 3: pin the boundary exactly — the 2nd-ranked directive is in the frame, the 3rd-ranked
    is off it."""
    from dataclasses import replace

    from pilot.strategy import ranking
    s, log = setup
    s2 = replace(s, decide_every_months=1)
    s2.__class__ = s.__class__
    calls = []
    game = FakeStellaris([briefing("2200.01.01"), briefing("2200.02.01")])
    g = Governor(s2, game, log, model=decisions("consolidate_economy", "tech_rush"),
                 role_models={"strategy": _strategist(calls)})
    g.run(max_decisions=2)
    assert ranking(g.strategy, STELLARIS)[:3] == ["defend", "consolidate_economy", "tech_rush"]
    traces = {e["decision"]: e for e in log.recent if e["kind"] == "trace"}
    assert traces["consolidate_economy"]["off_frame"] is False, "2nd-ranked is within the frame"
    assert traces["tech_rush"]["off_frame"] is True, "3rd-ranked is off it"


def test_decision_prompt_says_no_strategy_yet_when_there_is_none(setup):
    """Item 4: the decision prompt falls back to 'No strategy yet.' when there is no strategy."""
    s, log = setup
    seen = []

    def always_fails(messages, info):
        raise RuntimeError("boom")

    def respond(messages, info):
        seen.append(" ".join(str(p.content) for m in messages for p in getattr(m, "parts", []) if hasattr(p, "content")))
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"directive": "keep", "reason": "r"})])

    Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=FunctionModel(respond),
             role_models={"strategy": FunctionModel(always_fails)}).run(max_decisions=1)
    assert any("No strategy yet." in t for t in seen)


# ---- Task 7: the governor carries out the actions and verifies them ---------------------------

class _TechTool(FakeStellaris):
    """A FakeStellaris whose pick_tech replies with the tool's own wording — either the classic
    "picked <id> in <field>" or the newer "clicked <id> in <field> (option n); unverified until
    the next autosave …" — naming whichever prefer[index] it clicks (plain FakeStellaris always
    replies "ok", which names nothing)."""

    def __init__(self, briefings, index=0, field="engineering", clicked=False):
        super().__init__(briefings)
        self.index = index
        self.field = field
        self.clicked = clicked

    def pick_tech(self, prefer):
        self.actions.append(("pick_tech", list(prefer)))
        tech = prefer[self.index]
        if self.clicked:
            return f"clicked {tech} in {self.field} (option {self.index + 1}); unverified until the next autosave"
        return f"picked {tech} in {self.field}"


def test_decisions_carry_out_the_strategy_actions(setup):
    from pilot.strategy import Pillar
    s, log = setup
    calls = []
    game = FakeStellaris([briefing("2200.01.01"), briefing("2201.01.01")])
    g = Governor(s, game, log, model=decisions("keep"), role_models={"strategy": _strategist(calls)})
    g._review_strategy(briefing("2200.01.01"), "start of run")
    g.strategy.pillars["technology"] = Pillar(priority=3, stance="s", goals=["g"], prefer_techs=["tech_habitat_1"])
    g.strategy.pillars["economy"] = Pillar(priority=2, stance="s", goals=["g"], market=[{"side": "sell", "resource": "energy", "amount": 5}])
    g._carry_out_actions(_idle_energy("2200.01.01"))
    assert ("pick_tech", ["tech_habitat_1"]) in game.actions
    assert ("market_sync", [{"side": "sell", "resource": "energy", "amount": 5}]) in game.actions


def test_a_tech_that_did_not_stick_is_not_retried_until_the_next_review(setup):
    from pilot.strategy import Pillar
    s, log = setup
    calls = []
    game = FakeStellaris([briefing("2200.01.01")])
    g = Governor(s, game, log, model=decisions("keep"), role_models={"strategy": _strategist(calls)})
    g._review_strategy(briefing("2200.01.01"), "start of run")
    g.strategy.pillars["technology"] = Pillar(priority=3, stance="s", goals=["g"], prefer_techs=["tech_habitat_1"])
    offered = {**briefing("2200.02.01"), "research": {"engineering": {"current": ["tech_mining_2", 5.0],
                                                                       "alternatives": ["tech_mining_2", "tech_habitat_1"]}}}
    g._carry_out_actions(offered)                  # picks
    g._carry_out_actions(offered)                  # still not researching it: a miss, no second click
    assert sum(1 for a in game.actions if a[0] == "pick_tech") == 1


def test_actions_run_at_most_once_per_briefing_date_even_on_failure(setup):
    """Verified fact 1: the market and research tools read the last autosave, which stays stale
    until the next monthly autosave, so both act at most once per briefing date — even a failed
    attempt is not retried on the same date."""
    from pilot.strategy import Pillar
    s, log = setup

    class Failing(FakeStellaris):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.tech_calls = 0
            self.market_calls = 0

        def pick_tech(self, prefer):
            self.tech_calls += 1
            raise RuntimeError("tech pick failed")

        def market_sync(self, orders):
            self.market_calls += 1
            raise RuntimeError("market sync failed")

    game = Failing([briefing("2200.01.01")])
    g = Governor(s, game, log, model=decisions("keep"), role_models={"strategy": _strategist([])})
    g._review_strategy(briefing("2200.01.01"), "start of run")
    g.strategy.pillars["technology"] = Pillar(priority=3, stance="s", goals=["g"], prefer_techs=["tech_habitat_1"])
    g.strategy.pillars["economy"] = Pillar(priority=2, stance="s", goals=["g"], market=[{"side": "sell", "resource": "energy", "amount": 5}])
    b = _idle_energy("2200.01.01")
    g._carry_out_actions(b)
    g._carry_out_actions(b)   # same briefing date: neither tool is retried even though both failed
    assert game.tech_calls == 1 and game.market_calls == 1


def test_market_sync_is_skipped_when_orders_already_match_regardless_of_order(setup):
    """Verified fact 2: order-insensitive compare against the save's market_orders; when they
    already match the economy pillar's orders, the tool is not called at all."""
    from pilot.strategy import Pillar
    s, log = setup
    game = FakeStellaris([briefing("2200.01.01")])
    g = Governor(s, game, log, model=decisions("keep"), role_models={"strategy": _strategist([])})
    g._review_strategy(briefing("2200.01.01"), "start of run")
    g.strategy.pillars["economy"] = Pillar(priority=2, stance="s", goals=["g"], market=[
        {"side": "buy", "resource": "energy", "amount": 5},
        {"side": "buy", "resource": "minerals", "amount": 3},
    ])
    b = {**briefing("2200.01.01"), "market_orders": [
        {"side": "buy", "resource": "minerals", "amount": 3},
        {"side": "buy", "resource": "energy", "amount": 5},
    ]}
    g._carry_out_actions(b)
    assert not any(a[0] == "market_sync" for a in game.actions)


def test_a_failed_action_is_logged_and_never_raises_or_pauses(setup):
    """Verified fact 3: a failure of either tool is logged as a strategy_action event with the
    error, never raises out of _carry_out_actions, and never pauses the game."""
    from pilot.strategy import Pillar
    s, log = setup

    class Failing(FakeStellaris):
        def pick_tech(self, prefer):
            raise RuntimeError("agent unreachable")

        def market_sync(self, orders):
            raise RuntimeError("save is stale")

    game = Failing([briefing("2200.01.01")])
    g = Governor(s, game, log, model=decisions("keep"), role_models={"strategy": _strategist([])})
    g._review_strategy(briefing("2200.01.01"), "start of run")
    g.strategy.pillars["technology"] = Pillar(priority=3, stance="s", goals=["g"], prefer_techs=["tech_habitat_1"])
    g.strategy.pillars["economy"] = Pillar(priority=2, stance="s", goals=["g"], market=[{"side": "sell", "resource": "energy", "amount": 5}])
    g._carry_out_actions(_idle_energy("2200.01.01"))   # must not raise
    actions = [e for e in log.recent if e["kind"] == "strategy_action"]
    assert any(a["action"] == "tech" and "agent unreachable" in a["result"] for a in actions)
    assert any(a["action"] == "market" and "save is stale" in a["result"] for a in actions)
    assert not any(a[0] == "paused" for a in game.actions)


def test_tech_misses_reset_at_each_review(setup):
    """Verified fact 4: a miss is reset at each strategy review, so a preferred tech that missed
    once is tried again after the next review."""
    from pilot.strategy import Pillar
    s, log = setup
    calls = []
    game = _TechTool([briefing("2200.01.01")])
    g = Governor(s, game, log, model=decisions("keep"), role_models={"strategy": _strategist(calls)})
    g._review_strategy(briefing("2200.01.01"), "start of run")
    g.strategy.pillars["technology"] = Pillar(priority=3, stance="s", goals=["g"], prefer_techs=["tech_habitat_1"])
    offered = {**briefing("2200.02.01"), "research": {"engineering": {"current": ["tech_mining_2", 5.0],
                                                                       "alternatives": ["tech_mining_2", "tech_habitat_1"]}}}
    g._carry_out_actions(offered)                  # picks (game replies "picked tech_habitat_1 in engineering")
    g._carry_out_actions({**offered, "date": "2200.03.01"})   # a later save: still offered, not current → a miss
    assert g._tech_misses.get("tech_habitat_1") == 1

    g._review_strategy(briefing("2200.03.01"), "scheduled")   # resets the miss counter
    g.strategy.pillars["technology"] = Pillar(priority=3, stance="s", goals=["g"], prefer_techs=["tech_habitat_1"])
    assert g._tech_misses == {}

    later = {**briefing("2200.04.01"), "research": {"engineering": {"current": ["tech_mining_2", 5.0],
                                                                      "alternatives": ["tech_mining_2", "tech_habitat_1"]}}}
    g._carry_out_actions(later)
    assert sum(1 for a in game.actions if a[0] == "pick_tech") == 2, "retried after the review reset the miss count"


def test_the_tech_actually_picked_is_parsed_from_the_tools_reply(setup):
    """Fix round 1, item 1: the pending pick comes from the tool's own reply (both the classic
    "picked …" and the newer "clicked … (option n); unverified …" forms), not a guess — proven
    with a two-tech prefer list where the tool clicks the second one."""
    from pilot.strategy import Pillar
    s, log = setup
    game = _TechTool([briefing("2200.01.01")], index=1, clicked=True)
    g = Governor(s, game, log, model=decisions("keep"), role_models={"strategy": _strategist([])})
    g._review_strategy(briefing("2200.01.01"), "start of run")
    g.strategy.pillars["technology"] = Pillar(priority=3, stance="s", goals=["g"],
                                              prefer_techs=["tech_habitat_1", "tech_mining_2"])
    g._carry_out_actions(briefing("2200.01.01"))
    assert ("pick_tech", ["tech_habitat_1", "tech_mining_2"]) in game.actions
    assert g._pending_pick == "tech_mining_2", "parsed from the reply, not guessed from the offers"


def test_an_unmatched_reply_leaves_no_pending_pick(setup):
    """Fix round 1, item 1: a reply that matches neither form (e.g. "nothing to pick: …") is not
    turned into a pending pick."""
    from pilot.strategy import Pillar
    s, log = setup

    class NothingToPick(FakeStellaris):
        def pick_tech(self, prefer):
            self.actions.append(("pick_tech", list(prefer)))
            return "nothing to pick: no research screen is open"

    game = NothingToPick([briefing("2200.01.01")])
    g = Governor(s, game, log, model=decisions("keep"), role_models={"strategy": _strategist([])})
    g._review_strategy(briefing("2200.01.01"), "start of run")
    g.strategy.pillars["technology"] = Pillar(priority=3, stance="s", goals=["g"], prefer_techs=["tech_habitat_1"])
    g._carry_out_actions(briefing("2200.01.01"))
    assert g._pending_pick is None


def test_a_tech_still_offered_but_not_current_counts_as_a_miss(setup):
    """Fix round 1, item 2 (miss case): the picked tech is neither current research nor gone from
    the offers, so it is still listed among some field's alternatives — a miss."""
    from pilot.strategy import Pillar
    s, log = setup
    game = _TechTool([briefing("2200.01.01")])
    g = Governor(s, game, log, model=decisions("keep"), role_models={"strategy": _strategist([])})
    g._review_strategy(briefing("2200.01.01"), "start of run")
    g.strategy.pillars["technology"] = Pillar(priority=3, stance="s", goals=["g"], prefer_techs=["tech_habitat_1"])
    g._carry_out_actions(briefing("2200.01.01"))              # picks tech_habitat_1
    still_offered = {**briefing("2200.02.01"), "research": {"engineering": {
        "current": ["tech_mining_2", 5.0], "alternatives": ["tech_mining_2", "tech_habitat_1"]}}}
    g._carry_out_actions(still_offered)
    assert g._tech_misses.get("tech_habitat_1") == 1
    misses = [e for e in log.recent if e["kind"] == "strategy_action" and e.get("action") == "tech"
              and "did not stick" in e["result"]]
    assert misses


def test_a_tech_gone_from_the_offers_is_treated_as_researched_not_a_miss(setup):
    """Fix round 1, item 2 (completed case): the picked tech is neither current research nor
    offered any more anywhere — it finished, not a miss."""
    from pilot.strategy import Pillar
    s, log = setup
    game = _TechTool([briefing("2200.01.01")])
    g = Governor(s, game, log, model=decisions("keep"), role_models={"strategy": _strategist([])})
    g._review_strategy(briefing("2200.01.01"), "start of run")
    g.strategy.pillars["technology"] = Pillar(priority=3, stance="s", goals=["g"], prefer_techs=["tech_habitat_1"])
    g._carry_out_actions(briefing("2200.01.01"))              # picks tech_habitat_1
    completed = {**briefing("2200.02.01"), "research": {"engineering": {
        "current": ["tech_mining_2", 5.0], "alternatives": ["tech_mining_2", "tech_shipyard_1"]}}}
    g._carry_out_actions(completed)
    assert "tech_habitat_1" not in g._tech_misses
    researched = [e for e in log.recent if e["kind"] == "strategy_action" and e.get("action") == "tech"
                  and e["result"] == "researched tech_habitat_1"]
    assert researched


def test_market_orders_that_do_not_stick_wait_for_the_next_review(setup):
    """Fix round 1, item 3: after a sync, the next later save is checked against what was asked
    for; a mismatch is logged and not retried until the following review resets the flag."""
    from pilot.strategy import Pillar
    s, log = setup
    calls = []
    game = FakeStellaris([briefing("2200.01.01")])
    g = Governor(s, game, log, model=decisions("keep"), role_models={"strategy": _strategist(calls)})
    g._review_strategy(briefing("2200.01.01"), "start of run")
    g.strategy.pillars["economy"] = Pillar(priority=2, stance="s", goals=["g"],
                                           market=[{"side": "sell", "resource": "energy", "amount": 5}])
    g._carry_out_actions(_idle_energy("2200.01.01"))       # syncs
    assert sum(1 for a in game.actions if a[0] == "market_sync") == 1

    g._carry_out_actions(_idle_energy("2200.02.01"))       # later save still shows no orders: did not stick
    assert sum(1 for a in game.actions if a[0] == "market_sync") == 1, "not retried right after the mismatch"
    stuck = [e for e in log.recent if e["kind"] == "strategy_action" and e.get("action") == "market"
             and "did not stick" in e["result"]]
    assert stuck

    g._carry_out_actions(_idle_energy("2200.03.01"))       # still stuck: no further attempts before a review
    assert sum(1 for a in game.actions if a[0] == "market_sync") == 1

    g._review_strategy(briefing("2200.04.01"), "scheduled")     # resets the give-up flag
    g.strategy.pillars["economy"] = Pillar(priority=2, stance="s", goals=["g"],
                                           market=[{"side": "sell", "resource": "energy", "amount": 5}])
    g._carry_out_actions(_idle_energy("2200.05.01"))
    assert sum(1 for a in game.actions if a[0] == "market_sync") == 2, "retried after the review reset the flag"


def test_malformed_briefing_data_does_not_raise_out_of_carry_out_actions(setup):
    """Fix round 1, item 4: the whole body is wrapped so even malformed briefing data cannot raise
    out of _carry_out_actions; the failure is logged as a strategy_action event instead."""
    from pilot.strategy import Pillar
    s, log = setup
    game = FakeStellaris([briefing("2200.01.01")])
    g = Governor(s, game, log, model=decisions("keep"), role_models={"strategy": _strategist([])})
    g._review_strategy(briefing("2200.01.01"), "start of run")
    g.strategy.pillars["technology"] = Pillar(priority=3, stance="s", goals=["g"], prefer_techs=["tech_habitat_1"])
    bad = {**briefing("2200.01.01"), "research": "not a dict"}   # .values() will fail
    g._carry_out_actions(bad)   # must not raise
    assert any(e["kind"] == "strategy_action" and e.get("action") == "error" for e in log.recent)


def test_a_pick_is_not_judged_on_the_save_it_was_made_on(setup):
    """The save stays stale until the next autosave: a second decision on the same save must not
    count the fresh pick as a miss."""
    from pilot.strategy import Pillar
    s, log = setup
    game = FakeStellaris([briefing("2200.01.01")])
    game.pick_tech = lambda prefer: (game.actions.append(("pick_tech", list(prefer))), "clicked tech_habitat_1 in engineering (option 2)")[1]
    g = Governor(s, game, log, model=decisions("keep"), role_models={"strategy": _strategist([])})
    g._review_strategy(briefing("2200.01.01"), "start of run")
    g.strategy.pillars["technology"] = Pillar(priority=3, stance="s", goals=["g"], prefer_techs=["tech_habitat_1"])
    same = {**briefing("2200.01.01"), "research": {"engineering": {"current": ["tech_mining_2", 5.0],
                                                                   "alternatives": ["tech_habitat_1", "tech_mining_2"]}}}
    g._carry_out_actions(same)
    g._carry_out_actions(same)                       # e.g. "decide now" on the same save
    assert not [e for e in log.recent if e["kind"] == "strategy_action" and "did not stick" in e.get("result", "")]
    assert g._pending_pick == "tech_habitat_1", "still waiting for a later save"


# ---- Task 8: dashboard API, human edit/pin/unpin, review now -----------------------------------

def test_human_pillar_edits_pin_and_win_over_a_running_review(setup):
    s, log = setup
    calls = []
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"), role_models={"strategy": _strategist(calls)})
    g._review_strategy(briefing("2200.01.01"), "start of run")
    g.edit_pillar("diplomacy", {"stance": "no federations", "goals": ["stay independent"]})
    assert g.strategy.pillars["diplomacy"].pinned and g.strategy.pillars["diplomacy"].edited_by == "human"
    g._role_objs["strategy"] = _strategist(calls, pin_diplomacy_to="join a federation")
    g.__dict__.pop("_agents", None)
    g._review_strategy(briefing("2201.01.01"), "scheduled")
    assert g.strategy.pillars["diplomacy"].stance == "no federations"
    g.unpin_pillar("diplomacy")
    assert not g.strategy.pillars["diplomacy"].pinned
    with pytest.raises(ValueError):
        g.edit_pillar("happiness", {"stance": "x"})


def test_strategy_api_returns_current_milestones_and_history(setup, tmp_path):
    import asyncio

    from aiohttp.test_utils import TestClient, TestServer

    from pilot.dashboard import make_app
    from pilot.telemetry import Telemetry
    s, _ = setup
    tel = Telemetry(tmp_path / "t.sqlite")
    log = EventLog(s.runs_dir, "rs", s.model, telemetry=tel)
    calls = []
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"), role_models={"strategy": _strategist(calls)})
    log.emit("run_start", model=s.model, game=s.game)   # a runs row is needed before telemetry can attribute a campaign
    log.set_campaign("stellaris", "c1", "Test")
    g._review_strategy(briefing("2200.01.01"), "start of run")

    async def go():
        async with TestClient(TestServer(make_app(g, s.runs_dir, tel))) as c:
            r = await c.get(f"/api/strategy?campaign={log.campaign_id}")
            body = await r.json()
            assert body["current"]["focus"] == "grow" and len(body["history"]) == 1
            assert body["error"] == "", "a valid pillars file reports no error"
            r = await c.post("/control", json={"action": "edit_pillar", "pillar": "economy", "fields": {"stance": "save energy"}})
            assert r.status == 200 and g.strategy.pillars["economy"].pinned
            r = await c.post("/control", json={"action": "review_strategy"})
            assert r.status == 200 and g.requests.get_nowait() == ("review", "requested from the dashboard")
    asyncio.run(go())


def test_strategy_api_reports_a_missing_pillars_file_without_computing_milestones(setup, tmp_path):
    """Fix round 1, item 1: a campaign whose game has no (or an invalid) pillars.toml must not
    silently compute milestone status with an empty row_keys mapping (every remapped metric, e.g.
    Stellaris's colonies -> planets, would then read wrong); it must report the error instead, and
    never 500."""
    import asyncio

    from aiohttp.test_utils import TestClient, TestServer

    from pilot.dashboard import make_app
    from pilot.telemetry import Telemetry
    s, _ = setup
    tel = Telemetry(tmp_path / "t.sqlite")
    log = EventLog(s.runs_dir, "rb", s.model, telemetry=tel)
    log.emit("run_start", model=s.model, game="brokengame")
    log.set_campaign("brokengame", "c1", "Test")     # a game the live pilot (None) does not own
    pillars = _pillars_body(PRIOS)
    log.emit("strategy", date="2200.01.01", trigger="start of run", model=s.model, reason="seed",
             strategy={"pillars": pillars, "focus": "grow", "reason": "seed"})
    corpora_dir = tmp_path / "corpora"          # no "brokengame" subdirectory: load_pillars fails
    corpora_dir.mkdir()

    async def go():
        async with TestClient(TestServer(make_app(None, s.runs_dir, tel, corpora=corpora_dir))) as c:
            r = await c.get(f"/api/strategy?campaign={log.campaign_id}")
            assert r.status == 200, "a broken pillars file must not 500 the endpoint"
            body = await r.json()
            assert body["milestones"] == [], "no milestone status without a valid spec's row_keys"
            assert body["error"].startswith("pillars: "), body["error"]
            assert body["current"]["focus"] == "grow", "the strategy itself is still served"
    asyncio.run(go())


def test_edit_pillar_rejects_an_invalid_edit_and_leaves_strategy_unchanged(setup):
    """Ruling 1: a human edit is validated exactly like a model strategy; an invalid edit raises
    ValueError with the reasons and never touches the strategy."""
    s, log = setup
    calls = []
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"), role_models={"strategy": _strategist(calls)})
    g._review_strategy(briefing("2200.01.01"), "start of run")
    before = g.strategy.model_dump()
    with pytest.raises(ValueError, match="only the technology pillar may set prefer_techs"):
        g.edit_pillar("diplomacy", {"prefer_techs": ["some_tech"]})
    assert g.strategy.model_dump() == before, "a rejected edit must not change the strategy"


def test_edit_pillar_ignores_priority_edits(setup):
    """Ruling 1: priority is not an editable field (priorities stay unique)."""
    s, log = setup
    calls = []
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"), role_models={"strategy": _strategist(calls)})
    g._review_strategy(briefing("2200.01.01"), "start of run")
    before = g.strategy.pillars["diplomacy"].priority
    g.edit_pillar("diplomacy", {"stance": "no federations", "priority": 1})
    assert g.strategy.pillars["diplomacy"].priority == before


def test_edit_pillar_records_a_new_strategy_version_with_trigger_text(setup, tmp_path):
    """Ruling 2: an applied edit is stored as a new strategy version (trigger 'edited by human:
    <pillar>') so it survives a restart and appears in history."""
    from pilot.telemetry import Telemetry
    s, _ = setup
    tel = Telemetry(tmp_path / "t2.sqlite")
    log = EventLog(s.runs_dir, "run-edit", s.model, telemetry=tel)
    calls = []
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"), role_models={"strategy": _strategist(calls)})
    log.emit("run_start", model=s.model, game=s.game)   # a runs row is needed before telemetry can attribute a campaign
    log.set_campaign("stellaris", "edit-hist", "Test")
    g._review_strategy(briefing("2200.01.01"), "start of run")
    g.edit_pillar("economy", {"stance": "save energy"})
    hist = tel.strategy_history(log.campaign_id)
    assert hist[0]["trigger"] == "edited by human: economy"
    assert hist[0]["strategy"]["pillars"]["economy"]["pinned"] is True
    # survives a restart: a new Governor for the same campaign loads the edited version
    g2 = Governor(s, FakeStellaris([briefing("2200.02.01")]),
                 EventLog(s.runs_dir, "run-edit2", s.model, telemetry=tel), model=decisions("keep"))
    g2._set_campaign({"source": "save games/edit-hist/x.sav"})
    assert g2.strategy.pillars["economy"].stance == "save energy"
    assert g2.strategy.pillars["economy"].pinned


def test_request_review_queues_a_review_request(setup):
    """Final review 5: review_strategy from the dashboard goes through the request queue (it runs
    at once, between scheduled decisions) instead of waiting for the next decision."""
    s, log = setup
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"))
    g.request_review()
    assert g.requests.get_nowait() == ("review", "requested from the dashboard")
    assert g.review_requested is None


def test_a_review_request_bypasses_the_event_cap(setup):
    s, log = setup
    calls = []
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"), role_models={"strategy": _strategist(calls)})
    g._review_strategy(briefing("2200.01.01"), "start of run")
    g._last_event_review_month = months("2200.01.01")   # a review just counted against the cap
    g._handle_request(("review", "requested from the dashboard"), briefing("2200.06.01"))
    assert calls == ["strategist", "strategist"]
    assert g._last_event_review_month == months("2200.01.01"), "a requested review does not move the cap"


def test_control_edit_pillar_returns_400_for_an_invalid_edit(setup, tmp_path):
    import asyncio

    from aiohttp.test_utils import TestClient, TestServer

    from pilot.dashboard import make_app
    from pilot.telemetry import Telemetry
    s, _ = setup
    tel = Telemetry(tmp_path / "t3.sqlite")
    log = EventLog(s.runs_dir, "rs2", s.model, telemetry=tel)
    calls = []
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"), role_models={"strategy": _strategist(calls)})
    log.set_campaign("stellaris", "c2", "Test")
    g._review_strategy(briefing("2200.01.01"), "start of run")

    async def go():
        async with TestClient(TestServer(make_app(g, s.runs_dir, tel))) as c:
            r = await c.post("/control", json={"action": "edit_pillar", "pillar": "diplomacy",
                                               "fields": {"prefer_techs": ["some_tech"]}})
            assert r.status == 400
            assert not g.strategy.pillars["diplomacy"].pinned

            r = await c.post("/control", json={"action": "unpin_pillar", "pillar": "nope"})
            assert r.status == 400
    asyncio.run(go())


# ---- Task 8 fix round 1 --------------------------------------------------------------------

def test_edit_pillar_allows_a_stance_only_edit_before_any_briefing(setup):
    """Item 1: a human edit with no market orders is fine even before the governor has ever
    read a briefing (self._last_b is None)."""
    from pilot.strategy import Pillar, Strategy
    s, log = setup
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"))
    assert g._last_b is None
    prios = {"defence": 1, "economy": 2, "technology": 3, "expansion": 4, "diplomacy": 5, "government": 6, "society": 7}
    g.strategy = Strategy(pillars={p: Pillar(priority=n, stance=f"{p} stance", goals=["g"]) for p, n in prios.items()},
                          focus="hold")
    g.edit_pillar("economy", {"stance": "save for a war"})
    assert g.strategy.pillars["economy"].stance == "save for a war" and g.strategy.pillars["economy"].pinned


def test_edit_pillar_rejects_a_market_order_with_no_briefing_yet(setup):
    """Item 1: a market-order edit before any briefing is rejected, not silently allowed."""
    from pilot.strategy import Pillar, Strategy
    s, log = setup
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"))
    prios = {"defence": 1, "economy": 2, "technology": 3, "expansion": 4, "diplomacy": 5, "government": 6, "society": 7}
    g.strategy = Strategy(pillars={p: Pillar(priority=n, stance=f"{p} stance", goals=["g"]) for p, n in prios.items()},
                          focus="hold")
    with pytest.raises(ValueError, match="no briefing yet"):
        g.edit_pillar("economy", {"market": [{"side": "sell", "resource": "energy", "amount": 5}]})


def test_edit_pillar_market_order_is_checked_against_the_real_briefing_idle_state(setup):
    """Item 1: idle/income for a human market edit come from the governor's own last briefing,
    not from the edit itself (a real, non-idle resource must still be rejected)."""
    s, log = setup
    calls = []
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"), role_models={"strategy": _strategist(calls)})
    g._review_strategy(briefing("2200.01.01", net={"energy": 50}), "start of run")   # no stockpile: energy is not idle
    assert g._last_b is not None
    with pytest.raises(ValueError, match="not idle"):
        g.edit_pillar("economy", {"market": [{"side": "sell", "resource": "energy", "amount": 5}]})


def test_edit_pillar_market_order_over_20pct_of_real_income_is_rejected(setup):
    """Item 1: the 20%-of-income cap is computed from the real briefing's net income."""
    s, log = setup
    calls = []
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"), role_models={"strategy": _strategist(calls)})
    b = {**briefing("2200.01.01", net={"energy": 50}), "stockpile": {"energy": 10000}}   # idle, income 50/month
    g._review_strategy(b, "start of run")
    with pytest.raises(ValueError, match="over"):
        g.edit_pillar("economy", {"market": [{"side": "sell", "resource": "energy", "amount": 20}]})   # cap is 10


def test_edit_pillar_market_order_within_cap_is_accepted(setup):
    s, log = setup
    calls = []
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"), role_models={"strategy": _strategist(calls)})
    b = {**briefing("2200.01.01", net={"energy": 50}), "stockpile": {"energy": 10000}}
    g._review_strategy(b, "start of run")
    g.edit_pillar("economy", {"market": [{"side": "sell", "resource": "energy", "amount": 5}]})   # within the cap of 10
    assert g.strategy.pillars["economy"].market[0].amount == 5


def test_a_human_edit_landing_during_a_review_survives_the_commit(setup):
    """Item 2: a human edit/pin that lands after the model has answered but before the review
    commits its new strategy must not be lost. Simulated by hooking `journal.note`, which the
    review calls right before it assigns the new strategy."""
    s, log = setup
    calls = []
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"), role_models={"strategy": _strategist(calls)})
    g._review_strategy(briefing("2200.01.01"), "start of run")

    real_note = g.journal.note

    def hooked_note(*a, **kw):
        g.edit_pillar("diplomacy", {"stance": "no federations, landed mid-commit"})
        return real_note(*a, **kw)
    g.journal.note = hooked_note

    g._role_objs["strategy"] = _strategist(calls, pin_diplomacy_to="join a federation")
    g.__dict__.pop("_agents", None)
    g._review_strategy(briefing("2201.01.01"), "scheduled")
    assert g.strategy.pillars["diplomacy"].stance == "no federations, landed mid-commit"
    assert g.strategy.pillars["diplomacy"].edited_by == "human"


def test_control_edit_pillar_rejects_a_non_dict_fields_body(setup, tmp_path):
    """Item 3: a malformed `fields` body (not an object) is a 400, never a 500."""
    import asyncio

    from aiohttp.test_utils import TestClient, TestServer

    from pilot.dashboard import make_app
    from pilot.telemetry import Telemetry
    s, _ = setup
    tel = Telemetry(tmp_path / "t4.sqlite")
    log = EventLog(s.runs_dir, "rs3", s.model, telemetry=tel)
    calls = []
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"), role_models={"strategy": _strategist(calls)})
    log.set_campaign("stellaris", "c3", "Test")
    g._review_strategy(briefing("2200.01.01"), "start of run")

    async def go():
        async with TestClient(TestServer(make_app(g, s.runs_dir, tel))) as c:
            for bad in (5, True, [1]):
                r = await c.post("/control", json={"action": "edit_pillar", "pillar": "economy", "fields": bad})
                assert r.status == 400, (bad, r.status)
    asyncio.run(go())


def test_control_edit_pillar_rejects_unknown_field_names(setup, tmp_path):
    """Item 3: an unknown field name is a 400 naming it, not silently dropped."""
    import asyncio

    from aiohttp.test_utils import TestClient, TestServer

    from pilot.dashboard import make_app
    from pilot.telemetry import Telemetry
    s, _ = setup
    tel = Telemetry(tmp_path / "t5.sqlite")
    log = EventLog(s.runs_dir, "rs4", s.model, telemetry=tel)
    calls = []
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"), role_models={"strategy": _strategist(calls)})
    log.set_campaign("stellaris", "c4", "Test")
    g._review_strategy(briefing("2200.01.01"), "start of run")

    async def go():
        async with TestClient(TestServer(make_app(g, s.runs_dir, tel))) as c:
            r = await c.post("/control", json={"action": "edit_pillar", "pillar": "economy",
                                               "fields": {"nonsense": 1, "focus": "x"}})
            assert r.status == 400
            text = await r.text()
            assert "nonsense" in text and "focus" in text
            assert not g.strategy.pillars["economy"].pinned
    asyncio.run(go())


def test_edit_pillar_rejects_non_dict_fields_and_unknown_field_names(setup):
    """Item 3, governor-level: same checks are enforced by Governor.edit_pillar itself."""
    s, log = setup
    calls = []
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"), role_models={"strategy": _strategist(calls)})
    g._review_strategy(briefing("2200.01.01"), "start of run")
    with pytest.raises(ValueError):
        g.edit_pillar("economy", 5)
    with pytest.raises(ValueError, match="nonsense"):
        g.edit_pillar("economy", {"nonsense": 1})


def test_api_strategy_degrades_instead_of_500_on_an_unparseable_historical_strategy(setup, tmp_path):
    """Item 5: a stored strategy row that no longer matches the current Strategy schema (e.g. an
    older format) must not crash the API; the raw dict and empty milestones are served instead."""
    import asyncio

    from aiohttp.test_utils import TestClient, TestServer

    from pilot.dashboard import make_app
    from pilot.telemetry import Telemetry
    s, _ = setup
    tel = Telemetry(tmp_path / "t6.sqlite")
    log = EventLog(s.runs_dir, "rs5", s.model, telemetry=tel)
    log.emit("run_start", model=s.model, game=s.game)
    log.set_campaign("stellaris", "c5", "Test")
    log.emit("strategy", date="2200.01.01", trigger="start of run", model="m",
             reason="", strategy={"pillars": {"economy": {"not": "a valid pillar shape"}}, "focus": "grow"})

    async def go():
        async with TestClient(TestServer(make_app(None, s.runs_dir, tel))) as c:
            r = await c.get(f"/api/strategy?campaign={log.campaign_id}")
            assert r.status == 200
            body = await r.json()
            assert body["current"]["focus"] == "grow" and body["milestones"] == []
    asyncio.run(go())


# ---- final review fixes -------------------------------------------------------------------------

PRIOS = {"defence": 1, "economy": 2, "technology": 3, "expansion": 4, "diplomacy": 5, "government": 6, "society": 7}


def _strategy_with(**over):
    from pilot.strategy import Pillar, Strategy
    pillars = {p: Pillar(priority=n, stance=f"{p} stance", goals=["g"]) for p, n in PRIOS.items()}
    pillars.update(over)
    return Strategy(pillars=pillars, focus="hold")


def _pinned_energy_sell(amount=10):
    from pilot.strategy import Pillar
    return Pillar(priority=2, stance="sell spare energy", goals=["g"], pinned=True, edited_by="human",
                  market=[{"side": "sell", "resource": "energy", "amount": amount}])


def test_edit_pillar_is_not_blocked_by_a_pinned_pillar_that_no_longer_fits(setup):
    """Final review 1: the briefing checks apply to the edited pillar only."""
    s, log = setup
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"))
    g.strategy = _strategy_with(economy=_pinned_energy_sell())
    g._last_b = briefing("2200.01.01", net={"energy": 1.0})        # energy no longer idle, income tiny
    g.edit_pillar("diplomacy", {"stance": "stay friendly"})
    assert g.strategy.pillars["diplomacy"].stance == "stay friendly"
    assert g.strategy.pillars["economy"].market[0].amount == 10, "the pinned order is kept"


def test_a_review_is_not_blocked_by_a_pinned_pillar_that_no_longer_fits_and_is_warned(setup):
    """Final review 1: a pinned pillar failing today's briefing checks is kept (never rejected)
    and the Strategist's prompt says so."""
    s, log = setup
    prompts, calls = [], []
    inner = _strategist(calls)

    def respond(messages, info):
        prompts.append(" ".join(str(p.content) for m in messages for p in getattr(m, "parts", []) if hasattr(p, "content")))
        return inner.function(messages, info)

    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"),
                 role_models={"strategy": FunctionModel(respond)})
    g.strategy = _strategy_with(economy=_pinned_energy_sell())
    g._review_strategy(briefing("2201.01.01", net={"energy": 1.0}), "scheduled")
    assert g.strategy.focus == "grow", "the new strategy was accepted"
    assert g.strategy.pillars["economy"].pinned and g.strategy.pillars["economy"].market[0].amount == 10
    assert not any(e["kind"] == "strategy_rejected" for e in log.recent)
    assert "pinned economy no longer fits: selling energy but it is not idle" in prompts[0]


def _idle_energy(date: str) -> dict:
    """A briefing where energy is idle (big stock, positive net) with a 20% cap of 20."""
    return {**briefing(date, net={"energy": 100.0, "food": 3.0}), "stockpile": {"energy": 20000}}


def test_sells_that_no_longer_fit_are_dropped_before_market_sync(setup):
    """Final review 2: a sell failing today's idle / 20% check is skipped (and logged); the rest
    is synced."""
    from pilot.strategy import Pillar
    s, log = setup
    game = FakeStellaris([briefing("2200.01.01")])
    g = Governor(s, game, log, model=decisions("keep"))
    g.strategy = _strategy_with(economy=Pillar(priority=2, stance="s", goals=["g"],
                                               market=[{"side": "sell", "resource": "energy", "amount": 10}]))
    g._carry_out_actions({**briefing("2200.01.01", net={"energy": 100.0}), "market_orders": [
        {"side": "sell", "resource": "energy", "amount": 10}]})     # energy not idle any more
    assert ("market_sync", []) in game.actions, "the stale sell is removed, not kept"
    skipped = [e for e in log.recent if e["kind"] == "strategy_action" and "skipped sell energy" in e.get("result", "")]
    assert skipped and "not idle" in skipped[0]["result"]


def test_sells_that_still_fit_are_synced(setup):
    from pilot.strategy import Pillar
    s, log = setup
    game = FakeStellaris([briefing("2200.01.01")])
    g = Governor(s, game, log, model=decisions("keep"))
    g.strategy = _strategy_with(economy=Pillar(priority=2, stance="s", goals=["g"],
                                               market=[{"side": "sell", "resource": "energy", "amount": 10}]))
    g._carry_out_actions(_idle_energy("2200.01.01"))
    assert ("market_sync", [{"side": "sell", "resource": "energy", "amount": 10}]) in game.actions
    assert not any("skipped sell" in e.get("result", "") for e in log.recent if e["kind"] == "strategy_action")


def test_a_sell_over_20_percent_of_todays_income_is_skipped(setup):
    from pilot.strategy import Pillar
    s, log = setup
    game = FakeStellaris([briefing("2200.01.01")])
    g = Governor(s, game, log, model=decisions("keep"))
    g.strategy = _strategy_with(economy=Pillar(priority=2, stance="s", goals=["g"],
                                               market=[{"side": "sell", "resource": "energy", "amount": 25}]))
    g._carry_out_actions(_idle_energy("2200.01.01"))            # cap today is 20
    assert not any(a[0] == "market_sync" for a in game.actions), "nothing to sync: no orders wanted, none placed"
    assert any("skipped sell energy" in e.get("result", "") and "20% of monthly income" in e["result"]
               for e in log.recent if e["kind"] == "strategy_action")


def test_market_actions_are_skipped_when_the_game_has_no_market_action(tmp_path):
    """Fix round 1, item 3: a spec with no [actions.market] must not KeyError, and the pillar that
    owns market orders is found from the spec (`spec.owners('market')`), never hard-coded to
    'economy'."""
    import re

    from pilot.strategy import Pillar
    corpus = tmp_path / "stellaris"
    corpus.mkdir()
    for f in ("manifest.toml", "pilot.md", "strategy.md", "directives.toml"):
        shutil.copy(REPO / "corpora/stellaris" / f, corpus / f)
    text = (REPO / "corpora/stellaris/pillars.toml").read_text(encoding="utf-8")
    text = text.replace('actions = ["market"]\n', "")               # economy no longer declares it
    text = re.sub(r"\[actions\.market\][\s\S]*?(?=\n#|\n\[)", "", text)  # and the limits table is gone
    (corpus / "pillars.toml").write_text(text, encoding="utf-8")

    s = Settings(model="google:gemini-3.8-flash", runs_dir=tmp_path / "runs", journal=tmp_path / "journal.md",
                 commit_learnings=False, game="stellaris", speed="fastest", decide_every_months=12, poll_s=0,
                 ask_human_timeout_s=0.05, fallback_model=None)
    s.__class__ = type("S", (Settings,), {"corpus_dir": property(lambda self: corpus)})
    log = EventLog(s.runs_dir, "run_nomarket", s.model)
    game = FakeStellaris([briefing("2200.01.01")])
    g = Governor(s, game, log, model=decisions("keep"))
    assert g.pillars.actions.get("market") is None, "the test corpus must actually lack a market action"
    g.strategy = _strategy_with(economy=Pillar(priority=2, stance="s", goals=["g"],
                                               market=[{"side": "sell", "resource": "energy", "amount": 5}]))
    g._carry_out_actions(_idle_energy("2200.01.01"))               # must not raise (no KeyError on actions["market"])
    assert not any(a[0] == "market_sync" for a in game.actions), "no market action in the spec: nothing to sync"


def test_review_now_runs_at_once_without_waiting_for_a_scheduled_decision(setup):
    """Final review 5: the save date never advances (no scheduled decision can come), yet the
    requested review runs; no extra directive decision is made for it."""
    s, log = setup
    calls = []
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"),
                 role_models={"strategy": _strategist(calls)})
    t = _run_bg(g)
    try:
        assert _wait(lambda: log.state.episodes == 1 and calls == ["strategist"])
        g.request_review()
        assert _wait(lambda: any(e["kind"] == "strategy_review" and e["trigger"] == "requested from the dashboard"
                                 for e in log.recent)), "the requested review ran"
        assert len(calls) == 2
        assert log.state.episodes == 1, "no directive decision was made for it"
    finally:
        g.stop()
        t.join(3)


def test_one_review_per_decision_point(setup):
    """Final review 6: a scheduled review that ran inside _decide is the review for this decision
    point; an urgent event trigger at the same point does not start a second one."""
    from dataclasses import replace
    s, log = setup
    s2 = replace(s, retro_every=1)
    s2.__class__ = s.__class__
    calls = []
    b0 = briefing("2200.01.01")
    b1 = briefing("2200.03.01", wars=[{"name": "Border War", "attacker": False}])
    g = Governor(s2, FakeStellaris([b0, b1]), log, model=decisions("keep", "keep"),
                 role_models={"strategy": _strategist(calls)})
    g.run(max_decisions=2)
    eps = [e for e in log.recent if e["kind"] == "episode"]
    assert eps[1]["situation"].startswith("urgent: new war")
    reviews = [e for e in log.recent if e["kind"] == "strategy_review"]
    assert [r["trigger"] for r in reviews] == ["start of run", "scheduled after 1 decisions"], reviews


def test_an_event_review_still_runs_when_no_review_ran_in_the_decision(setup):
    s, log = setup
    calls = []
    b0 = briefing("2200.01.01")
    b1 = briefing("2200.03.01", wars=[{"name": "Border War", "attacker": False}])
    g = Governor(s, FakeStellaris([b0, b1]), log, model=decisions("keep", "keep"),
                 role_models={"strategy": _strategist(calls)})
    g.run(max_decisions=2)
    reviews = [e for e in log.recent if e["kind"] == "strategy_review"]
    assert len(reviews) == 2 and reviews[1]["trigger"].startswith("urgent: new war")


def test_errored_decision_rows_with_a_null_decision_stay_visible(tmp_path):
    """Final review 7: `decision != 'strategy_review'` is NULL-unsafe in SQL (NULL != x is NULL),
    so errored decisions (decision NULL) vanished from the dashboard's lists and counts and from
    scoring. Only strategy_review rows are excluded."""
    import asyncio
    import json

    from aiohttp.test_utils import TestClient, TestServer

    from pilot.dashboard import make_app
    from pilot.telemetry import Telemetry
    tel = Telemetry(tmp_path / "t.sqlite")
    tel.start_run("r1", "stellaris", "m", {}, 1.0)
    cid = tel.set_campaign("r1", "stellaris", "nulls", 1.0)
    row = "INSERT INTO decisions(run_id, episode, campaign_id, t, date, month, decision) VALUES (?,?,?,?,?,?,?)"
    tel._exec(row, ("r1", 1, cid, 1.0, "2200.01.01", 2200 * 12, "expand"))
    tel._exec(row, ("r1", 2, cid, 2.0, "2200.01.01", 2200 * 12, None))            # an errored decision
    tel._exec(row, ("r1", -1, cid, 3.0, "2200.01.01", 2200 * 12, "strategy_review"))
    for date, month, pops in (("2200.01.01", 2200 * 12, 10), ("2201.01.01", 2201 * 12, 20)):
        tel._exec("INSERT INTO metrics(run_id, campaign_id, t, date, month, data) VALUES (?,?,?,?,?,?)",
                  ("r1", cid, 1.0, date, month, json.dumps({"pops": pops})))
    assert tel.score(cid) == 2, "the errored row is scored like any decision; the review is not"

    async def go():
        async with TestClient(TestServer(make_app(None, tmp_path, tel))) as c:
            camps = await (await c.get("/api/campaigns")).json()
            assert camps[0]["decisions"] == 2
            ds = await (await c.get("/api/decisions", params={"campaign": cid})).json()
            assert [d["decision"] for d in ds] == ["expand", None]
    asyncio.run(go())


def _milestone_strategist(calls, by="2200.02.01"):
    from pilot.strategy import Milestone

    def respond(messages, info):
        calls.append("strategist")
        pillars = _pillars_body(PRIOS)
        pillars["economy"]["milestones"] = [Milestone(metric="pops", op=">=", target=1000, by=by).model_dump()]
        body = {"change": True, "assessment": "ok", "rules": [],
                "strategy": {"pillars": pillars, "focus": "grow", "reason": "start"}}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, body)])
    return FunctionModel(respond)


def test_a_milestone_turning_missed_is_urgent_and_triggers_a_review(setup, tmp_path):
    """Final review 8: a milestone newly turning `missed` (not missed at the previous check) is
    an urgent reason, "milestone missed: <pillar> <metric>", which starts a (capped) review."""
    from pilot.governor import EVENT_TRIGGERS
    from pilot.telemetry import Telemetry
    assert "milestone missed" in EVENT_TRIGGERS
    s, _ = setup
    tel = Telemetry(tmp_path / "t.sqlite")
    log = EventLog(s.runs_dir, "runm", s.model, telemetry=tel)
    src = "save games/mile_1/x.sav"
    game = FakeStellaris([{**briefing(d), "source": src, "pops": 50} for d in ("2200.01.01", "2200.02.01", "2200.03.01")])
    calls = []
    g = Governor(s, game, log, model=decisions("keep", "keep"), role_models={"strategy": _milestone_strategist(calls)})
    g.run(max_decisions=2)
    eps = [e for e in log.recent if e["kind"] == "episode"]
    assert eps[1]["situation"] == "urgent: milestone missed: economy pops" and eps[1]["date"] == "2200.03.01"
    assert any(e["kind"] == "strategy_review" and "milestone missed" in e["trigger"] for e in log.recent)


def test_a_milestone_already_missed_does_not_fire_again(setup, tmp_path):
    from pilot.governor import metrics
    from pilot.telemetry import Telemetry
    s, _ = setup
    tel = Telemetry(tmp_path / "t.sqlite")
    log = EventLog(s.runs_dir, "runm2", s.model, telemetry=tel)
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"),
                 role_models={"strategy": _milestone_strategist([], by="2199.06.01")})
    log.set_campaign("stellaris", "mile_2", "Test")
    g._review_strategy(briefing("2200.01.01"), "start of run")
    for d in ("2200.01.01", "2200.02.01"):
        log.emit("metrics", **{**metrics(briefing(d)), "pops": 50})
    assert g._newly_missed_milestones("2200.01.01", "2200.02.01") == []
    g2 = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"),
                  role_models={"strategy": _milestone_strategist([], by="2200.01.01")})
    g2.strategy = g.strategy.model_copy(deep=True)
    g2.strategy.pillars["economy"].milestones[0].by = "2200.01.01"
    assert g2._newly_missed_milestones("2200.01.01", "2200.02.01") == ["milestone missed: economy pops"]


def test_decision_instructions_refer_to_the_strategy_frame_not_the_campaign_plan():
    from pilot.governor import INSTRUCTIONS
    assert "campaign plan" not in INSTRUCTIONS
    assert "the strategy frame" in INSTRUCTIONS


def test_a_failing_briefing_text_read_never_raises_out_of_a_review(setup):
    """Final review 9: building the review prompt (which may read the briefing text from the game)
    is inside the review's own error handling: logged, retried at the next decision."""
    s, log = setup

    class NoText(FakeStellaris):
        def briefing_text(self):
            raise RuntimeError("agent unreachable")

    g = Governor(s, NoText([briefing("2200.01.01")]), log, model=decisions("keep"), role_models={"strategy": _strategist([])})
    assert g.last_briefing is None or g.last_briefing == ""
    g._review_strategy(briefing("2200.01.01"), "start of run")          # must not raise
    assert g.review_requested == "start of run" and g._review_retry
    assert any(e["kind"] == "episode_error" and "agent unreachable" in e["error"] for e in log.recent)


def test_dashboard_clears_review_pending_only_on_a_review_result():
    """Final review 9: a human edit's `strategy` event must not re-enable "Review strategy now"
    while a review is running; only the review's own result (strategy_review, or episode_error)
    does."""
    import re

    from pilot.config import REPO
    html = (REPO / "src/pilot/static/dashboard.html").read_text(encoding="utf-8")
    clears = [ln for ln in html.splitlines() if "reviewPending = false" in ln and "ev.kind" in ln]
    assert clears, "onEvent clears the pending state"
    for ln in clears:
        assert '"strategy_review"' in ln and '"episode_error"' in ln
        assert not re.search(r'ev\.kind === "strategy"\s*\|\|', ln), ln


# ---- final review 10: coverage ------------------------------------------------------------------

def test_idle_resources_boundaries():
    from pilot.governor import idle_resources

    def idle(res, stock, net):
        return res in idle_resources({"stockpile": {res: stock}, "net": {res: net}})
    assert not idle("energy", 1_000_000, 0), "a huge stockpile with no net income is not idle"
    assert not idle("energy", 1_000_000, -5), "nor with a deficit"
    assert not idle("energy", 6000, 50), "exactly 120 months of income (50*120) is not over the threshold"
    assert idle("energy", 6001, 50)
    assert not idle("energy", 5000, 1), "the stockpile must be over 5000"
    assert idle("energy", 5001, 1)
    assert not idle("trade", 15000, 10), "trade: exactly 15000 is not over the threshold"
    assert idle("trade", 15001, 10)
    assert not idle("trade", 20000, 0)
    assert not idle("trade", 10000, 1), "trade uses only its own threshold, like the briefing"
    assert not idle("volatile_motes", 1_000_000, 1), "the briefing never flags strategic resources idle"


def test_frame_text_lists_only_at_risk_and_missed_milestones():
    from pilot.governor import frame_text
    lines = ("- economy: pops >= 100 by 2210.01.01: met\n- expansion: systems >= 20 by 2210.01.01: on_track\n"
             "- technology: techs_known >= 80 by 2210.01.01: at_risk\n- defence: military_power >= 5000 by 2205.01.01: missed")
    text = frame_text(_strategy_with(), STELLARIS, lines)
    assert "techs_known >= 80 by 2210.01.01: at_risk" in text and "military_power >= 5000 by 2205.01.01: missed" in text
    assert ": met" not in text and "on_track" not in text


def test_unpin_pillar_on_an_unknown_pillar_raises_and_leaves_the_strategy_unchanged(setup):
    s, log = setup
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"))
    g.strategy = _strategy_with(economy=_pinned_energy_sell())
    before = g.strategy
    with pytest.raises(ValueError, match="unknown pillar 'navy'"):
        g.unpin_pillar("navy")
    assert g.strategy is before and g.strategy.pillars["economy"].pinned
    assert not any(e["kind"] == "strategy" for e in log.recent)


def test_a_broken_milestone_check_never_pauses_the_governor(setup, monkeypatch):
    """The milestone check runs in the poll loop: an unexpected error there is logged, not raised
    (raising would reach run() and flag needs_attention)."""
    s, log = setup
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"), role_models={"strategy": _strategist([])})
    g._review_strategy(briefing("2200.01.01"), "start of run")
    from pilot.strategy import Milestone
    g.strategy.pillars["expansion"].milestones = [Milestone(metric="systems", op=">=", target=10, by="2200.02.01")]
    import pilot.governor as gm
    monkeypatch.setattr(gm, "milestone_status", lambda *a, **k: (_ for _ in ()).throw(ValueError("bad row date")))
    monkeypatch.setattr(g, "_metrics_rows", lambda: [{"date": "x"}])
    assert g._newly_missed_milestones("2200.01.01", "2200.02.01") == []
    assert any(e["kind"] == "briefing_error" and "milestone" in e.get("error", "") for e in log.recent)


def test_the_corrective_retry_shows_the_rejected_answer(setup):
    """Live 2452.03: the retry prompt named only the error, so the retry model (another model in the
    rotation) started over and returned empty pillars. The retry must see the answer to fix."""
    s, log = setup
    prompts = []

    def bad(messages, info):
        prompts.append("\n".join(str(getattr(p, "content", "")) for m in messages for p in getattr(m, "parts", [])))
        body = {"change": True, "assessment": "x", "rules": [], "strategy": {"pillars": {}, "focus": "hold the line", "reason": "r"}}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, body)])
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"), role_models={"strategy": FunctionModel(bad)})
    g._review_strategy(briefing("2200.01.01"), "start of run")
    assert len(prompts) == 2
    assert "Your rejected answer" in prompts[1] and "hold the line" in prompts[1]


def test_rank_and_measure_aliases_map_to_the_recorded_metrics():
    from pilot.strategy import Milestone, Pillar, Strategy, apply_aliases
    for alias, real in (("rank:military", "rank:military_power"), ("rank:economy", "rank:economy_power"),
                        ("rank:tech", "rank:tech_power"), ("military", "military_power"), ("techs", "techs_known"),
                        ("planets", "colonies")):
        s = Strategy(pillars={"economy": Pillar(priority=1, stance="s", milestones=[
            Milestone(metric=alias, op=">=", target=1, by="2200.01.01")])}, focus="f")
        m = apply_aliases(s, STELLARIS).pillars["economy"].milestones[0]
        assert m.metric == real and real in STELLARIS.metrics


# ---- Fix round 1, item 2: aliases are pinned at the governor (both write paths) -----------------

def test_a_strategist_reviews_milestone_metric_is_stored_aliased(setup):
    """A Strategist answer written in a common model spelling ("rank:military") is stored under
    the recorded measure's real name ("rank:military_power"), not the raw spelling."""
    s, log = setup

    def respond(messages, info):
        pillars = _pillars_body(PRIOS)
        pillars["economy"]["milestones"] = [{"metric": "rank:military", "op": "<=", "target": 3, "by": "2210.01.01"}]
        body = {"change": True, "assessment": "ok", "rules": [],
                "strategy": {"pillars": pillars, "focus": "grow", "reason": "start"}}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, body)])

    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"),
                 role_models={"strategy": FunctionModel(respond)})
    g._review_strategy(briefing("2200.01.01"), "start of run")
    assert g.strategy is not None, "the answer must have validated"
    assert g.strategy.pillars["economy"].milestones[0].metric == "rank:military_power"


def test_edit_pillar_stores_the_milestone_metric_aliased(setup):
    """A human edit's milestone metric ("planets") is stored under the recorded measure's real
    name ("colonies") too: edit_pillar aliases exactly like a model review."""
    s, log = setup
    calls = []
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"),
                 role_models={"strategy": _strategist(calls)})
    g._review_strategy(briefing("2200.01.01"), "start of run")
    g.edit_pillar("economy", {"milestones": [{"metric": "planets", "op": ">=", "target": 5, "by": "2210.01.01"}]})
    assert g.strategy.pillars["economy"].milestones[0].metric == "colonies"


def _species_briefing(date: str) -> dict:
    return {**briefing(date), "identity": {"species": {"name": "Lithoid humans", "class": "LITHOID",
            "traits": ["trait_lithoid", "trait_industrious", "trait_enduring", "trait_wasteful"]}}}


def _identity_strategist(identities: list[str], seen_prompts: list[str]):
    """Answers with a valid strategy whose `identity` is taken from `identities` in turn."""
    prios = {"defence": 1, "economy": 2, "technology": 3, "expansion": 4, "diplomacy": 5, "government": 6, "society": 7}

    def respond(messages, info):
        seen_prompts.append("\n".join(str(getattr(p, "content", "")) for m in messages for p in getattr(m, "parts", [])))
        pillars = _pillars_body(prios)
        ident = identities[min(len(seen_prompts) - 1, len(identities) - 1)]
        body = {"change": True, "assessment": "ok", "rules": [], "identity": ident,
                "strategy": {"pillars": pillars, "focus": "grow", "reason": "start"}}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, body)])
    return FunctionModel(respond)


def test_a_start_review_must_build_on_our_species_traits(setup):
    s, log = setup
    prompts = []
    g = Governor(s, FakeStellaris([_species_briefing("2200.01.01")]), log, model=decisions("keep"),
                 role_models={"strategy": _identity_strategist(["We will grow fast.", ("Industrious and enduring lithoids: "
                                                                "mining-heavy economy, long wars are affordable.")], prompts)})
    g._review_strategy(_species_briefing("2200.01.01"), "start of run")
    assert len(prompts) == 2, "the first answer ignored our traits and was sent back once"
    assert "industrious" in prompts[1] and "enduring" in prompts[1]
    assert g.strategy is not None and "Industrious" in g.strategy.identity


def test_a_dashboard_review_also_checks_the_species_traits(setup):
    s, log = setup
    prompts = []
    g = Governor(s, FakeStellaris([_species_briefing("2200.01.01")]), log, model=decisions("keep"),
                 role_models={"strategy": _identity_strategist(["nothing about us", "still nothing"], prompts)})
    g._review_strategy(_species_briefing("2200.01.01"), "requested from the dashboard")
    assert g.strategy is None and any(e["kind"] == "strategy_rejected" for e in log.recent)


def test_the_strategist_prompt_names_our_species_and_traits(setup):
    s, log = setup
    prompts = []
    g = Governor(s, FakeStellaris([_species_briefing("2200.01.01")]), log, model=decisions("keep"),
                 role_models={"strategy": _identity_strategist(["industrious enduring lithoids"], prompts)})
    g._review_strategy(_species_briefing("2200.01.01"), "start of run")
    assert "Our species: Lithoid humans" in prompts[0] and "industrious" in prompts[0]


def test_a_named_field_review_is_accepted_with_its_milestones(setup):
    """Live 2026-09-26: Claude returned `pillars: {}` twice for a dict-typed schema. With one named
    field per pillar the answer is accepted and its milestones are kept."""
    s, log = setup
    calls, schemas = [], []
    inner = _strategist(calls)

    def respond(messages, info):
        schemas.append(info.output_tools[0].parameters_json_schema)
        return inner.function(messages, info)

    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"),
                 role_models={"strategy": FunctionModel(respond)})
    g._review_strategy(briefing("2200.01.01"), "start of run")
    out = next(d for d in schemas[0]["$defs"].values() if "focus" in d.get("properties", {}))
    assert set(STELLARIS.ids) <= set(out["properties"])
    assert g.strategy is not None and set(g.strategy.pillars) == set(STELLARIS.ids)
    assert g.strategy.pillars["defence"].milestones and g.strategy.pillars["technology"].milestones
    assert not any(e["kind"] == "strategy_rejected" for e in log.recent)


def test_the_corrective_retry_sends_back_the_named_field_shape(setup):
    """Ruling 2: the corrective retry still includes the rejected answer, dumped as JSON of the
    generated named-field shape (never the old {"pillars": {...}} shape)."""
    s, log = setup
    prompts = []
    prios = {"defence": 1, "economy": 2, "technology": 3, "expansion": 4, "diplomacy": 5, "government": 6, "society": 7}

    def bad_then_ok(messages, info):
        prompts.append("\n".join(str(getattr(p, "content", "")) for m in messages for p in getattr(m, "parts", [])))
        if len(prompts) == 1:
            body = {"change": True, "assessment": "x", "rules": [], "strategy": {"focus": "f", "reason": "r"}}
        else:
            pillars = _pillars_body(prios)
            body = {"change": True, "assessment": "ok", "rules": [], "strategy": {**pillars, "focus": "grow", "reason": "start"}}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, body)])

    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"),
                 role_models={"strategy": FunctionModel(bad_then_ok)})
    g._review_strategy(briefing("2200.01.01"), "start of run")
    assert len(prompts) == 2, "the first answer was rejected and retried once"
    rejected = prompts[1].split("Your rejected answer:\n", 1)[1].split("\n\n", 1)[0]
    assert '"pillars"' not in prompts[1] and '"focus": "f"' in rejected
    assert "missing pillar defence" in prompts[1], "the reasons name the pillars the answer left out"
    assert g.strategy is not None and set(g.strategy.pillars) == set(STELLARIS.ids)


# ---- game pillars: governor wiring ----------------------------------------------------------------

def test_a_missing_pillars_file_turns_the_strategy_layer_off(setup):
    s, log = setup
    (s.corpus_dir / "pillars.toml").unlink()
    calls, seen = [], []

    def respond(messages, info):
        seen.append(" ".join(str(p.content) for m in messages for p in getattr(m, "parts", []) if hasattr(p, "content")))
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"directive": "expand", "reason": "r"})])

    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=FunctionModel(respond),
                 role_models={"strategy": _strategist(calls)})
    g.run(max_decisions=1)
    assert calls == [], "no Strategist call without a pillars file"
    assert g.pillars is None and "pillars.toml" in g.pillars_error
    off = [e for e in log.recent if e["kind"] == "strategy_disabled"]
    assert len(off) == 1 and "pillars.toml: missing" in off[0]["error"]
    assert any("No strategy yet." in t for t in seen)
    assert ("directive", "expand") in g.game.actions, "decisions run as before the layer"
    assert log.state.info["pillars"] is None
    with pytest.raises(ValueError, match="strategy layer is off"):
        g.edit_pillar("economy", {"stance": "x"})
    with pytest.raises(ValueError, match="strategy layer is off"):
        g.request_review()


def test_an_invalid_pillars_file_turns_the_layer_off_naming_the_key(setup):
    s, log = setup
    f = s.corpus_dir / "pillars.toml"
    f.write_text(f.read_text(encoding="utf-8").replace('label = "Society"', 'label = "Society"\ncolour = "red"'),
                 encoding="utf-8")
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"))
    off = [e for e in log.recent if e["kind"] == "strategy_disabled"]
    assert g.pillars is None and len(off) == 1 and "pillars.society.colour: unknown key" in off[0]["error"]


def test_a_stored_strategy_with_other_pillar_ids_is_treated_as_none(setup, tmp_path):
    from pilot.telemetry import Telemetry
    s, _ = setup
    tel = Telemetry(tmp_path / "t.sqlite")
    seed = EventLog(s.runs_dir, "seed", s.model, telemetry=tel)
    seed.emit("run_start", game="stellaris", model=s.model)
    seed.set_campaign("stellaris", "emp_z", "Empire Z")
    seed.emit("strategy", date="2199.01.01", trigger="start of run", model="seed", reason="seed",
              strategy={"pillars": {"navy": {"priority": 1, "stance": "s", "goals": []}}, "focus": "f"})
    calls = []
    log = EventLog(s.runs_dir, "run2", s.model, telemetry=tel)
    g = Governor(s, FakeStellaris([{**briefing("2200.01.01"), "source": "save games/emp_z/x.sav"}]), log,
                 model=decisions("keep"), role_models={"strategy": _strategist(calls)})
    g.run(max_decisions=1)
    assert calls and calls[0] == "strategist", "reviewed at start as if there were no strategy"
    assert set(g.strategy.pillars) == set(STELLARIS.ids)
    mismatches = [e for e in log.recent if e["kind"] == "strategy_mismatch"]
    assert len(mismatches) == 1
    assert mismatches[0]["stored"] == ["navy"] and set(mismatches[0]["spec"]) == set(STELLARIS.ids)


def test_a_declared_action_without_a_game_hook_is_skipped_once(setup):
    from pilot.strategy import Pillar
    s, log = setup

    class NoMarket(FakeStellaris):
        market_sync = None

    game = NoMarket([briefing("2200.01.01")])
    g = Governor(s, game, log, model=decisions("keep"))
    g.strategy = _strategy_with(
        technology=Pillar(priority=3, stance="s", goals=["g"], prefer_techs=["tech_habitat_1"]),
        economy=Pillar(priority=2, stance="s", goals=["g"], market=[{"side": "buy", "resource": "alloys", "amount": 5}]))
    g._carry_out_actions(_idle_energy("2200.01.01"))
    g._carry_out_actions(_idle_energy("2200.02.01"))
    unsupported = [e for e in log.recent if e["kind"] == "strategy_action" and "not supported" in e.get("result", "")]
    assert len(unsupported) == 1 and unsupported[0]["action"] == "market"
    assert ("pick_tech", ["tech_habitat_1"]) in game.actions, "the supported action still runs"
    assert log.state.status != "needs_attention"


def test_edit_pillar_fields_follow_the_pillars_file(setup):
    s, log = setup
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"))
    g.strategy = _strategy_with()
    g._last_b = _idle_energy("2200.01.01")
    with pytest.raises(ValueError, match="technology: only the economy pillar may set market"):
        g.edit_pillar("technology", {"market": [{"side": "buy", "resource": "alloys", "amount": 5}]})
    assert not g.strategy.pillars["technology"].pinned
    g.edit_pillar("economy", {"market": [{"side": "buy", "resource": "alloys", "amount": 5}]})
    assert g.strategy.pillars["economy"].market[0].resource == "alloys"
    g.edit_pillar("society", {"milestones": [{"metric": "planets", "op": ">=", "target": 5, "by": "2230.01.01"}]})
    assert g.strategy.pillars["society"].milestones[0].metric == "colonies", "aliases apply to human edits too"


def test_the_pillars_spec_is_published_for_the_dashboard(setup):
    s, log = setup
    Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"))
    assert [p["id"] for p in log.state.info["pillars"]["pillars"]] == list(STELLARIS.ids)


def test_no_review_is_attempted_while_the_strategy_layer_is_off(setup):
    """Fix round 1, item 1: with the layer off, neither the scheduled retro-review check nor the
    event-review call site (run loop) may reach _review_strategy — zero strategy_review_skipped
    events even after more than retro_every decisions plus an urgent event, and decisions still
    run normally."""
    from dataclasses import replace
    s, log = setup
    (s.corpus_dir / "pillars.toml").unlink()
    s2 = replace(s, retro_every=2, decide_every_months=1)
    s2.__class__ = s.__class__
    war = [{"name": "Test War", "attacker": False}]
    briefings = [briefing("2200.01.01"), briefing("2200.02.01"), briefing("2200.03.01", wars=war),
                 briefing("2200.04.01", wars=war)]
    game = FakeStellaris(briefings)
    g = Governor(s2, game, log, model=decisions("keep", "keep", "keep", "keep"))
    g.run(max_decisions=4)
    assert log.state.episodes == 4, "decisions still run with the layer off"
    assert not any(e["kind"] == "strategy_review_skipped" for e in log.recent)
    assert sum(1 for e in log.recent if e["kind"] == "strategy_disabled") == 1


def test_control_review_strategy_returns_400_when_the_layer_is_off(setup, tmp_path):
    """Fix round 1, item 2: the dashboard's review_strategy control must not 500 when the strategy
    layer is off; request_review's ValueError is turned into a 400, like unpin_pillar."""
    import asyncio

    from aiohttp.test_utils import TestClient, TestServer

    from pilot.dashboard import make_app
    from pilot.telemetry import Telemetry
    s, _ = setup
    (s.corpus_dir / "pillars.toml").unlink()
    tel = Telemetry(tmp_path / "t7.sqlite")
    log = EventLog(s.runs_dir, "rs7", s.model, telemetry=tel)
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"))
    log.set_campaign("stellaris", "c7", "Test")

    async def go():
        async with TestClient(TestServer(make_app(g, s.runs_dir, tel))) as c:
            r = await c.post("/control", json={"action": "review_strategy"})
            assert r.status == 400
    asyncio.run(go())


# ---- Task 5: dashboard renders the Strategy tab from the spec -----------------------------------

THREE_PILLARS = '''[strategy]
min_milestones_top = 1

[metrics]
names = ["systems", "pops"]

[pillars.faith]
label = "Faith"
description = "Religion and its spread."

[pillars.science]
label = "Science"
description = "Research output."

[pillars.culture]
label = "Culture"
description = "Great works and tourism."
'''


def test_strategy_api_serves_the_games_pillars(setup, tmp_path):
    import asyncio

    from aiohttp.test_utils import TestClient, TestServer

    from pilot.dashboard import make_app
    from pilot.telemetry import Telemetry
    s, _ = setup
    tel = Telemetry(tmp_path / "t.sqlite")
    log = EventLog(s.runs_dir, "rsp", s.model, telemetry=tel)
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"), role_models={"strategy": _strategist([])})
    log.emit("run_start", model=s.model, game=s.game)
    log.set_campaign("stellaris", "c9", "Test")
    g._review_strategy(briefing("2200.01.01"), "start of run")

    async def go():
        async with TestClient(TestServer(make_app(g, s.runs_dir, tel))) as c:
            body = await (await c.get(f"/api/strategy?campaign={log.campaign_id}")).json()
            assert [p["id"] for p in body["spec"]["pillars"]] == list(STELLARIS.ids)
            assert body["spec"]["actions"]["market"]["max_items"] == 1
    asyncio.run(go())


def test_strategy_api_serves_a_three_pillar_spec_in_the_viewer(tmp_path):
    import asyncio

    from aiohttp.test_utils import TestClient, TestServer

    from pilot.dashboard import make_app
    from pilot.telemetry import Telemetry
    corpora = tmp_path / "corpora"
    (corpora / "civtest").mkdir(parents=True)
    (corpora / "civtest" / "pillars.toml").write_text(THREE_PILLARS, encoding="utf-8")
    (corpora / "civtest" / "directives.toml").write_text("", encoding="utf-8")   # no directive is ranked
    tel = Telemetry(tmp_path / "t.sqlite")
    log = EventLog(tmp_path / "runs", "r1", "test:model", telemetry=tel)
    log.emit("run_start", model="test:model", game="civtest")
    log.set_campaign("civtest", "c1", "Test civ")
    strategy = {"pillars": {p: {"priority": i + 1, "stance": f"{p} stance", "goals": ["g"]}
                            for i, p in enumerate(["science", "faith", "culture"])}, "focus": "pray"}
    log.emit("strategy", date="2200.01.01", trigger="start of run", model="seed", reason="seed", strategy=strategy)

    async def go():
        async with TestClient(TestServer(make_app(None, tmp_path / "runs", tel, corpora=corpora))) as c:
            body = await (await c.get("/api/strategy?campaign=civtest/c1")).json()
            assert [(p["id"], p["label"], p["directive"], p["actions"]) for p in body["spec"]["pillars"]] == [
                ("faith", "Faith", None, []), ("science", "Science", None, []), ("culture", "Culture", None, [])]
            assert body["current"]["focus"] == "pray"
            missing = await (await c.get("/api/strategy?campaign=nogame/c1")).json()
            assert missing["spec"] is None
    asyncio.run(go())


def test_dashboard_strategy_tab_reads_the_spec_not_a_copied_map():
    html = (REPO / "src/pilot/static/dashboard.html").read_text(encoding="utf-8")
    assert "DIRECTIVE_OF" not in html
    assert "data.spec" in html and "function specIndex(" in html
    assert 'name === "technology"' not in html and 'name === "economy"' not in html


# ---- final review fixes -------------------------------------------------------------------------

def _main_shape_strategy(**over):
    """A strategy as main stores it (every action field on every pillar, identity), top 3 with milestones."""
    from pilot.strategy import Strategy
    body = _pillars_body(PRIOS)
    for p in body.values():
        p.update(prefer_techs=[], market=[], pinned=False, edited_by="model")
    body["economy"].update(pinned=True, edited_by="human", market=[{"side": "buy", "resource": "alloys", "amount": 5}])
    for k, v in over.items():
        body[k].update(v)
    return Strategy.model_validate({"pillars": body, "focus": "hold", "reason": "seed", "identity": "industrious"})


def _echo_strategist(prompts: list[str], *, spoil_first: bool = False):
    """Answers change=true with the strategy JSON its own prompt shows (a verbatim echo)."""
    import json

    def respond(messages, info):
        text = "\n".join(str(getattr(p, "content", "")) for m in messages for p in getattr(m, "parts", []))
        prompts.append(text)
        shown = json.loads(text.split("Current strategy:\n", 1)[1].split("\n\n", 1)[0])
        if spoil_first and len(prompts) == 1:
            shown["defence"]["milestones"] = []          # rejected: a top-3 pillar without a milestone
        elif spoil_first:
            shown = json.loads(text.split("Your rejected answer:\n", 1)[1].split("\n\n", 1)[0])
            shown["defence"]["milestones"] = [{"metric": "systems", "op": ">=", "target": 12, "by": "2231.01.01"}]
        body = {"change": True, "assessment": "echo", "rules": [], "strategy": shown}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, body)])
    return FunctionModel(respond)


def test_a_strategist_echoing_the_prompts_strategy_is_accepted(setup):
    s, log = setup
    prompts = []
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"),
                 role_models={"strategy": _echo_strategist(prompts)})
    g.strategy = _main_shape_strategy()
    g._review_strategy(briefing("2200.01.01"), "scheduled")
    assert len(prompts) == 1 and not any(e["kind"] == "strategy_rejected" for e in log.recent)
    shown = prompts[0].split("Current strategy:\n", 1)[1].split("\n\n", 1)[0]
    assert '"pillars"' not in shown and '"pinned"' not in shown and '"identity"' not in shown
    assert "Pinned by the human" in prompts[0] and "economy" in prompts[0].split("Pinned by the human", 1)[1][:80]
    assert any(e["kind"] == "strategy_review" and e["accepted"] for e in log.recent)
    assert g.strategy.pillars["economy"].pinned, "the human's pin is kept"


def test_the_corrective_retry_shows_the_rejected_answer_in_the_output_shape(setup):
    s, log = setup
    prompts = []
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"),
                 role_models={"strategy": _echo_strategist(prompts, spoil_first=True)})
    g.strategy = _main_shape_strategy()
    g._review_strategy(briefing("2200.01.01"), "scheduled")
    assert len(prompts) == 2
    rejected = prompts[1].split("Your rejected answer:\n", 1)[1].split("\n\n", 1)[0]
    assert '"pinned"' not in rejected and "null" not in rejected and '"prefer_techs"' not in rejected.split('"technology"')[0]
    assert not any(e["kind"] == "strategy_rejected" for e in log.recent), "the fixed echo is accepted"
    assert g.strategy.pillars["defence"].milestones[0].target == 12


def _viewer_campaign(tmp_path, game: str, strategy: dict | None, pillars: str | None):
    """A telemetry db with one campaign '<game>/c1' (and a stored strategy), and a corpora dir."""
    from pilot.telemetry import Telemetry
    corpora = tmp_path / "corpora"
    (corpora / game).mkdir(parents=True)
    if pillars is not None:
        (corpora / game / "pillars.toml").write_text(pillars, encoding="utf-8")
        (corpora / game / "directives.toml").write_text("", encoding="utf-8")
    tel = Telemetry(tmp_path / "t.sqlite")
    log = EventLog(tmp_path / "runs", "r1", "test:model", telemetry=tel)
    log.emit("run_start", model="test:model", game=game)
    log.set_campaign(game, "c1", "Test")
    log.emit("metrics", date="2200.01.01", systems=3)
    if strategy is not None:
        log.emit("strategy", date="2200.01.01", trigger="start of run", model="seed", reason="seed", strategy=strategy)
    return tel, corpora


def _get_strategy(app, cid: str) -> dict:
    import asyncio

    from aiohttp.test_utils import TestClient, TestServer

    async def go():
        async with TestClient(TestServer(app)) as c:
            r = await c.get(f"/api/strategy?campaign={cid}")
            assert r.status == 200
            return await r.json()
    return asyncio.run(go())


def test_strategy_api_reports_a_stored_strategy_with_other_pillars(tmp_path):
    from pilot.dashboard import make_app
    ms = [{"metric": "systems", "op": ">=", "target": 10, "by": "2230.01.01"}]
    stored = {"pillars": {"navy": {"priority": 1, "stance": "s", "goals": [], "milestones": ms}}, "focus": "f"}
    tel, corpora = _viewer_campaign(tmp_path, "civtest", stored, THREE_PILLARS)
    body = _get_strategy(make_app(None, tmp_path / "runs", tel, corpora=corpora), "civtest/c1")
    assert body["error"] == "stored strategy does not match the game's pillars; the next review writes a new one"
    assert body["milestones"] == [] and body["current"]["focus"] == "f"


def test_strategy_api_is_quiet_for_a_game_without_pillars_or_strategy(tmp_path):
    from pilot.dashboard import make_app
    tel, corpora = _viewer_campaign(tmp_path, "galciv4", None, None)
    body = _get_strategy(make_app(None, tmp_path / "runs", tel, corpora=corpora), "galciv4/c1")
    assert body["error"] == "" and body["spec"] is None and body["current"] is None


def test_strategy_api_reports_the_live_pilots_pillars_error(setup, tmp_path):
    from pilot.dashboard import make_app
    from pilot.telemetry import Telemetry
    s, _ = setup
    (s.corpus_dir / "pillars.toml").unlink()
    tel = Telemetry(tmp_path / "t.sqlite")
    log = EventLog(s.runs_dir, "rl", s.model, telemetry=tel)
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"))
    log.emit("run_start", model=s.model, game=s.game)
    log.set_campaign("stellaris", "live", "Test")
    body = _get_strategy(make_app(g, s.runs_dir, tel), log.campaign_id)
    assert "pillars.toml: missing" in body["error"] and "strategy layer is off" in body["error"]
    assert body["spec"] is None, "no spec is served while the live layer is off (edits would fail)"


def test_dashboard_prefixes_only_a_pillars_file_error_as_layer_off():
    html = (REPO / "src/pilot/static/dashboard.html").read_text(encoding="utf-8")
    assert '>Strategy layer off: ${esc(data.error)}<' not in html, "mismatch/live errors are complete messages"
    assert 'data.error.startsWith("pillars: ")' in html


def test_a_failing_review_model_turns_the_layer_off(setup, monkeypatch):
    import pilot.governor as gm
    s, log = setup

    def boom(spec):
        raise TypeError("schema build failed")
    monkeypatch.setattr(gm, "review_model", boom)
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("expand"))
    assert g.pillars is None and "TypeError: schema build failed" in g.pillars_error
    off = [e for e in log.recent if e["kind"] == "strategy_disabled"]
    assert len(off) == 1 and "schema build failed" in off[0]["error"]
    assert log.state.info["pillars"] is None
    g.run(max_decisions=1)
    assert ("directive", "expand") in g.game.actions, "decisions still run"


def test_a_main_shape_strategy_without_milestones_upgrades_cleanly(setup, tmp_path):
    """Upgrade path: main stored strategies with every action field on every pillar, identity, and
    no milestones. It loads; change=false keeps it; change=true needs milestones on the new
    version's top pillars only."""
    from pilot.strategy import Strategy
    from pilot.telemetry import Telemetry
    s, _ = setup
    tel = Telemetry(tmp_path / "t.sqlite")
    seed = EventLog(s.runs_dir, "seed", s.model, telemetry=tel)
    seed.emit("run_start", game="stellaris", model=s.model)
    seed.set_campaign("stellaris", "emp_u", "Empire U")
    old = {p: {"priority": n, "stance": f"{p} old", "goals": ["g"], "milestones": [], "prefer_techs": [], "market": [],
               "pinned": False, "edited_by": "model"} for p, n in PRIOS.items()}
    seed.emit("strategy", date="2199.01.01", trigger="start of run", model="main", reason="seed",
              strategy={"pillars": old, "focus": "old focus", "reason": "seed", "identity": "industrious"})

    new_prios = {"economy": 1, "expansion": 2, "society": 3, "defence": 4, "technology": 5, "diplomacy": 6, "government": 7}
    answers = []

    def respond(messages, info):
        change, body = answers.pop(0)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
            "change": change, "assessment": "a", "rules": [], "strategy": body})])

    log = EventLog(s.runs_dir, "up", s.model, telemetry=tel)
    log.emit("run_start", game="stellaris", model=s.model)
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"),
                 role_models={"strategy": FunctionModel(respond)})
    g._set_campaign({**briefing("2200.01.01"), "source": "save games/emp_u/x.sav"})
    assert g.strategy is not None and g.strategy.focus == "old focus", "the main-shape strategy loads"
    assert g.review_requested is None and not any(e["kind"] == "strategy_mismatch" for e in log.recent)
    loaded = g.strategy

    answers.append((False, None))
    g._review_strategy(briefing("2200.01.01"), "scheduled")
    assert g.strategy is loaded, "change=false keeps it although its top pillars have no milestones"

    missing = _pillars_body(new_prios)
    missing["society"]["milestones"] = []                # a new top-3 pillar without a milestone
    answers.extend([(True, {**missing, "focus": "new"}), (True, {**missing, "focus": "new"})])
    g._review_strategy(briefing("2200.02.01"), "scheduled")
    assert g.strategy is loaded
    rejected = [e for e in log.recent if e["kind"] == "strategy_rejected"]
    assert rejected and rejected[-1]["errors"] == ["society: priority 3 is in the top 3 and needs at least one milestone"]

    answers.append((True, {**_pillars_body(new_prios), "focus": "new"}))   # milestones on the new top 3 only
    g._review_strategy(briefing("2200.03.01"), "scheduled")
    assert isinstance(g.strategy, Strategy) and g.strategy.focus == "new"
    assert [n for n, pl in g.strategy.sorted_pillars() if pl.milestones] == ["economy", "expansion", "society"]
