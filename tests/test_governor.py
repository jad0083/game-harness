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


def test_governor_decides_on_schedule_and_pauses_while_deciding(setup):
    s, log = setup
    game = FakeStellaris([briefing("2200.01.01"), briefing("2200.06.01"), briefing("2201.01.01")])
    gov = Governor(s, game, log, model=decisions("expand", "keep", consult_first=True))
    gov.run(max_decisions=2)

    acts = [a for a in game.actions if a[0] != "corpus"]
    assert acts[:3] == [("paused", True), ("speed", "fastest"), ("directive", "expand")]
    # resumed after the first decision, paused again at the scheduled date (12 months later)
    assert acts[3] == ("paused", False) and acts[4] == ("paused", True)
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


def test_explicit_journal_survives_game_switch(monkeypatch, tmp_path):
    from pilot import cli
    captured = {}
    monkeypatch.setenv("PILOT_JOURNAL", str(tmp_path / "j.md"))
    monkeypatch.setattr(cli, "check", lambda s: captured.setdefault("s", s) and 0)
    cli.main(["check", "--game", "stellaris"])
    assert captured["s"].game == "stellaris" and captured["s"].journal == tmp_path / "j.md"
