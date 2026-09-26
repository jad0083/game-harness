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


def decisions(*choices: str, consult_first: bool = False):
    """A model that returns the given directives in order (one per decision)."""
    calls = {"n": 0}

    def respond(messages, info: AgentInfo) -> ModelResponse:
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
                 ask_human_timeout_s=0.05)
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
    ds = tel.query("SELECT * FROM decisions WHERE campaign_id=? ORDER BY episode", (cid,))
    assert [d["decision"] for d in ds] == ["expand", "keep", "keep"]
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
    ds2 = tel2.query("SELECT decision, result FROM decisions WHERE campaign_id=? ORDER BY episode", (cid,))
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
    assert tel.query("SELECT decision, trace FROM decisions")[0] == {"decision": "expand", "trace": None}


def planner_model(retro_rules=("Survey before expanding: expand stalls when few reachable systems are surveyed.",)):
    """Decides with a plan on the first decision, keeps afterwards; answers retrospectives."""
    seen = []

    def respond(messages, info: AgentInfo) -> ModelResponse:
        from pydantic_ai.messages import UserPromptPart
        for m in messages:
            for p in getattr(m, "parts", []):
                if isinstance(p, UserPromptPart) and isinstance(p.content, str):
                    seen.append(p.content)
        props = info.output_tools[0].parameters_json_schema.get("properties", {})
        if "assessment" in props:
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
                "assessment": "Expansion lagged the median; surveying was the bottleneck.",
                "rules": list(retro_rules), "plan": "1. Survey all systems within 2 jumps by 2203.\\n2. Reach 8 systems by 2205."})])
        first = not any("Campaign plan:" in p and "Reach 6 systems" in p for p in seen)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
            "directive": "expand" if first else "keep", "reason": "r",
            "plan": "1. Reach 6 systems by 2205.\\n2. Keep all nets positive." if first else ""})])

    return FunctionModel(respond), seen


def test_campaign_plan_persists_and_retrospective_runs(setup, tmp_path):

    from pilot.telemetry import Telemetry
    s, _ = setup
    s.retro_every = 3
    tel = Telemetry(tmp_path / "t.sqlite")
    log = EventLog(s.runs_dir, "run5", s.model, telemetry=tel)
    src = "save games/emp_1/x.sav"
    game = FakeStellaris([{**briefing(f"22{i:02d}.01.01"), "source": src} for i in range(8)])
    model, seen = planner_model()
    gov = Governor(s, game, log, model=model)
    gov.run(max_decisions=4)          # 3 decisions, then the retrospective counts as the 4th
    plans = tel.query("SELECT date, text, source FROM plans WHERE campaign_id='stellaris/emp_1' ORDER BY t")
    assert [p["source"] for p in plans] == ["decision", "retrospective"], plans
    assert "Reach 6 systems" in plans[0]["text"] and "Survey all systems" in plans[1]["text"]
    assert any("Campaign plan:" in p and "Reach 6 systems" in p for p in seen), "the plan is shown to later decisions"
    retro = [e for e in log.recent if e["kind"] == "trace" and e.get("decision") == "retrospective"]
    assert retro and "bottleneck" in retro[0]["reason"]
    rules = (s.corpus_dir / "learned" / "strategy.md")
    assert rules.exists() and "Survey before expanding" in rules.read_text()
    assert gov.plan.startswith("1. Survey all systems")
    gov._set_plan("Goals &amp; milestones", "2203.01.01", "decision")
    assert gov.plan == "Goals & milestones"
    # a new Governor for the same campaign picks the plan up again
    gov2 = Governor(s, FakeStellaris([briefing("2210.01.01")]), EventLog(s.runs_dir, "run6", s.model, telemetry=tel), model=model)
    gov2._set_campaign({"source": src})
    assert gov2.plan == "Goals & milestones"


def test_remember_rule_tool_records_a_rule(setup):
    """Regression: 'learned' events passed kind= as data and raised TypeError."""
    s, log = setup

    def respond(messages, info: AgentInfo) -> ModelResponse:
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
    Governor(s, game, log, model=model).run(max_decisions=3)

    async def go():
        async with TestClient(TestServer(make_app(None, s.runs_dir, tel))) as c:
            plans = await (await c.get("/api/plans", params={"campaign": "stellaris/e1"})).json()
            assert [p["source"] for p in plans] == ["retrospective", "decision"], plans
            ds = await (await c.get("/api/decisions", params={"campaign": "stellaris/e1"})).json()
            assert ds[-1]["decision"] == "retrospective" and "bottleneck" in ds[-1]["reason"]

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
        return ModelResponse(parts=[ToolCallPart("consult", {"query": "more"})])   # never answers

    game = FakeStellaris([briefing("2200.01.01")])
    Governor(s, game, log, model=FunctionModel(respond)).run(max_decisions=1)
    err = [e for e in log.recent if e["kind"] == "episode_error"]
    assert err and "no answer within 4 model calls" in err[0]["error"]
    assert not [a for a in game.actions if a[0] == "directive"]
    assert sum(1 for a in game.actions if a[0] == "corpus") <= 4


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
    assert models.load_prefs(s.runs_dir) == {"model": "google:gemini-3.1-pro-preview", "thinking": "high"}
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
