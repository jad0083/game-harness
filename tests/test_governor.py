import shutil

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from pilot.config import REPO, Settings
from pilot.events import EventLog
from pilot.game import FakeStellaris
from pilot.governor import Governor, current_directive, months, urgent_changes


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
    for f in ("manifest.toml", "pilot.md", "strategy.md", "directives.toml"):
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
    version (with rules learned) whenever it is reviewed. `expansion` is priority 2 (PILLARS
    order), so the first `expand` choice stays within the frame's top 2 and is never off-frame."""
    from pilot.strategy import PILLARS
    seen = []
    calls = {"n": 0}

    def respond(messages, info: AgentInfo) -> ModelResponse:
        from pydantic_ai.messages import UserPromptPart
        for m in messages:
            for p in getattr(m, "parts", []):
                if isinstance(p, UserPromptPart) and isinstance(p.content, str):
                    seen.append(p.content)
        if _is_strategy_review(info):
            strategy = {"pillars": {p: {"priority": i + 1, "stance": f"{p} stance", "goals": ["g"]}
                                    for i, p in enumerate(PILLARS)},
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
    s.poll_s = 0.3                                      # the change must land before the next poll
    bs = [briefing(f"22{y:02d}.{m:02d}.01") for y in range(3) for m in (1, 7)]
    game = FakeStellaris(bs)
    gov = Governor(s, game, log, model=decisions("keep"))
    t = threading.Thread(target=gov.run, daemon=True)
    t.start()
    assert _wait(lambda: log.state.episodes >= 1)
    gov.set_speed("fastest")
    gov.set_months(6)                                   # was 24: the next decision now comes at +6 months
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
    from pilot.strategy import Pillar

    prios = {"defence": 1, "economy": 2, "technology": 3, "expansion": 4, "diplomacy": 5, "government": 6, "society": 7}

    def respond(messages, info):
        calls.append("strategist")
        pillars = {p: Pillar(priority=n, stance=f"{p} by model", goals=["g"]).model_dump() for p, n in prios.items()}
        if pin_diplomacy_to:
            pillars["diplomacy"]["stance"] = pin_diplomacy_to
        body = {"change": change, "assessment": "ok", "rules": [],
                "strategy": {"pillars": pillars, "focus": "grow", "reason": "start"} if change else None}
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
    from pilot.governor import STRATEGY_INSTRUCTIONS
    assert ("While at war, the defence stance must name its exit condition (peace, war exhaustion, "
            "or planets retaken).") in STRATEGY_INSTRUCTIONS
    assert ("When a hostile neighbour's military is twice ours or more, a defence goal is two "
            "shipyards in different systems and alloy production on two or more planets; never "
            "reason from a naval-capacity cap the briefing does not show.") in STRATEGY_INSTRUCTIONS


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
    from pilot.strategy import Pillar
    s, log = setup
    prios = {"defence": 1, "economy": 2, "technology": 3, "expansion": 4, "diplomacy": 5, "government": 6, "society": 7}

    def respond(messages, info):
        pillars = {p: Pillar(priority=n, stance=f"{p} by model", goals=["g"]).model_dump() for p, n in prios.items()}
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

    from pilot.strategy import PILLARS
    from pilot.telemetry import Telemetry
    s, _ = setup
    s2 = replace(s, retro_every=1)
    s2.__class__ = s.__class__
    tel = Telemetry(tmp_path / "t.sqlite")
    src = "save games/emp_x/x.sav"
    seed = EventLog(s2.runs_dir, "seed", s2.model, telemetry=tel)
    seed.emit("run_start", game="stellaris", model=s2.model)
    seed.set_campaign("stellaris", "emp_x", "Empire X")
    strategy = {"pillars": {p: {"priority": i + 1, "stance": f"{p} s", "goals": ["g"]} for i, p in enumerate(PILLARS)},
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

    from pilot.strategy import Pillar
    s, log = setup
    s2 = replace(s, decide_every_months=1)
    s2.__class__ = s.__class__
    prios = {"defence": 1, "economy": 2, "technology": 3, "expansion": 4, "diplomacy": 5, "government": 6, "society": 7}
    n = {"count": 0}

    def respond(messages, info):
        n["count"] += 1
        if n["count"] == 1:
            raise RuntimeError("boom")
        pillars = {p: Pillar(priority=i, stance=f"{p} by model", goals=["g"]).model_dump() for p, i in prios.items()}
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
    s, log = setup
    calls = []
    game = FakeStellaris([briefing("2200.01.01"), briefing("2201.01.01")])
    g = Governor(s, game, log, model=decisions("defend", "keep"), role_models={"strategy": _strategist(calls)})
    g.run(max_decisions=2)
    assert g.strategy.ranking()[0] == "defend", "defend is top-ranked and is the current directive"
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
    s, log = setup
    s2 = replace(s, decide_every_months=1)
    s2.__class__ = s.__class__
    calls = []
    game = FakeStellaris([briefing("2200.01.01"), briefing("2200.02.01")])
    g = Governor(s2, game, log, model=decisions("consolidate_economy", "tech_rush"),
                 role_models={"strategy": _strategist(calls)})
    g.run(max_decisions=2)
    assert g.strategy.ranking()[:3] == ["defend", "consolidate_economy", "tech_rush"]
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
