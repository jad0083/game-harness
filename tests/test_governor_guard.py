"""The governors on the model guard (docs/design/2026-10-02-model-guard-design.md, rulings 11, 17, 19,
21-23): a decision that loses its model mid-run continues on the next one without running a tool twice,
Deciding and the events say what happened, and PILOT_MODEL_GUARD=0 keeps the whole-run retries."""

from __future__ import annotations

from dataclasses import replace

import pytest
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from test_governor import FakeStellaris, _is_strategy_review, _quiet_no_change, briefing, decisions, setup  # noqa: F401

from pilot.governor import Governor
from pilot.store import open_store

E503 = ModelHTTPError(503, "gemini-3.8-flash", {"error": {"code": 503, "status": "UNAVAILABLE"}})


def consult_then_503():
    """Answers the Strategist; for a decision: consult first, then 503 on every later request."""
    calls = {"n": 0}

    def respond(messages, info):
        if _is_strategy_review(info):
            return _quiet_no_change(info)
        calls["n"] += 1
        if sum(isinstance(m, ModelResponse) for m in messages) == 0:
            return ModelResponse(parts=[ToolCallPart("consult", {"query": "stance"})])
        raise E503
    return FunctionModel(respond, model_name="gemini-3.8-flash"), calls


def test_a_decision_continues_on_the_fallback_and_consults_once(setup):  # noqa: F811
    s, log = setup
    first, _ = consult_then_503()
    game = FakeStellaris([briefing("2200.01.01")])
    Governor(s, game, log, model=first, fallback=decisions("expand")).run(max_decisions=1)
    assert sum(e["kind"] == "consult" for e in log.recent) == 1, "the tool ran once"
    assert "governor_directive_expand" in game.flags
    fb = [e for e in log.recent if e["kind"] == "model_fallback"][-1]
    assert fb["failure"] == "overloaded" and fb["request"] == 2 and fb["family"] == "gemini-flash"
    assert fb["error"] == "model gemini-3.8-flash answered 503"
    retry = [e for e in log.recent if e["kind"] == "model_retry"][-1]
    assert retry["failure"] == "overloaded" and retry["delay"] == 1.0 and retry["role"] == "decisions"
    breaker = [e for e in log.recent if e["kind"] == "model_breaker"][-1]
    assert breaker["state"] == "open" and breaker["model"] == "google:gemini-3.8-flash"
    health = log.state.info["model_health"]["models"]["google:gemini-3.8-flash"]
    assert health["state"] == "open" and health["today"] >= 3, "the 503, its retry and the consult (and any review)"
    ans = log.state.info["answered"]
    assert ans["fallback"] is True and ans["after"] == [{"model": "google:gemini-3.8-flash", "error": "overloaded (503)"}]


def test_the_decision_record_names_the_model_that_answered_after_a_failover(setup):  # noqa: F811
    """Ruling 25: the saved trace (and its `trace` event) names the fallback entry and its thinking level."""
    import json
    s, log = setup
    first, _ = consult_then_503()
    game = FakeStellaris([briefing("2200.01.01")])
    g = Governor(s, game, log, model=first, fallback=decisions("expand"))
    configured = g._pool

    def pool(role="decisions"):          # the two entries think differently, so the record shows whose it is
        return [{**e, "thinking": t} for e, t in zip(configured(role), ("low", "high"))]
    g._pool = pool
    g.run(max_decisions=1)
    fallback = pool()[1]
    assert fallback["model"] != "google:gemini-3.8-flash"
    ev = [e for e in log.recent if e["kind"] == "trace" and e.get("decision") == "expand"][-1]
    assert (ev["model"], ev["thinking_level"]) == (fallback["model"], "high")
    row = log.store.query("SELECT trace FROM decisions WHERE run_id=? AND episode=?", (log.state.run_id, ev["episode"]))
    saved = json.loads(row[0]["trace"])
    assert (saved["model"], saved["thinking_level"], saved["decision"]) == (fallback["model"], "high", "expand")


def test_an_open_model_is_skipped_by_the_next_call(setup):  # noqa: F811
    s, log = setup
    first, calls = consult_then_503()
    g = Governor(s, FakeStellaris([briefing("2200.01.01"), briefing("2201.01.01")]), log, model=first,
                 fallback=decisions("expand", "keep"))
    g.run(max_decisions=2)
    assert calls["n"] == 3, "the second decision skips the open model"


def test_no_model_answers_then_pool_exhausted_and_the_directive_stays(setup):  # noqa: F811
    s, log = setup
    s = replace(s, pool_max_wait_s=0)
    s.__class__ = setup[0].__class__

    def down(messages, info):
        if _is_strategy_review(info):
            return _quiet_no_change(info)
        raise E503
    Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=FunctionModel(down)).run(max_decisions=1)
    ex = [e for e in log.recent if e["kind"] == "pool_exhausted"][-1]
    assert ex["role"] == "decisions" and ex["causes"][0]["error"] == "overloaded (503)"
    assert any(e["kind"] == "episode_error" for e in log.recent)


def _stop_in_the_wait(monkeypatch, health, model: str, stop) -> list[float]:
    """The guard's sleeps: once `model` is open (the pool's wait), the run is stopped. Returns those sleeps."""
    from pilot import modelguard as G
    waited: list[float] = []

    async def sleep(seconds):
        if health().status(model) == "open":
            waited.append(seconds)
            stop()
    monkeypatch.setattr(G, "_sleep", sleep)
    return waited


def _stop_lines(log) -> list[str]:
    return [e["text"] for e in log.recent if e["kind"] == "journal" and e["text"].startswith("Stopped while waiting")]


def test_a_stop_ends_the_wait_for_the_decisions_models(setup, monkeypatch):  # noqa: F811
    """Pool-wait ruling 3: a page Stop while the decision's pool waits for its model ends the wait within a
    step, and the decision ends quietly: one plain line, no error, no error trace, no crisis ladder by rule."""
    from pilot import modelguard as G
    s, log = setup

    def down(messages, info):
        if _is_strategy_review(info):
            return _quiet_no_change(info)
        raise E503
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=FunctionModel(down))
    crisis = []
    g._crisis_without_answer = lambda *a: crisis.append(a)
    waited = _stop_in_the_wait(monkeypatch, lambda: g.health, s.model, g.stop)
    g.run(max_decisions=1)
    kinds = [e["kind"] for e in log.recent]
    assert sum(waited) <= G.POOL_STOP_STEP_S
    assert "episode_error" not in kinds and "pool_exhausted" not in kinds and crisis == []
    assert _stop_lines(log) == ["Stopped while waiting for the models: no decision this time; the directive stays"]
    assert not log.store.query("SELECT 1 FROM decisions WHERE run_id=? AND episode > 0", (log.state.run_id,))
    wait = next(e for e in log.recent if e["kind"] == "model_wait")
    assert (wait["role"], wait["models"], wait["budget_s"], wait["reason"]) == (
        "decisions", [s.model], 120.0, "every model is overloaded")


def test_a_stop_during_a_strategy_review_wait_ends_quietly(setup, monkeypatch):  # noqa: F811
    s, log = setup

    def down(messages, info):
        raise E503
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=FunctionModel(down))
    _stop_in_the_wait(monkeypatch, lambda: g.health, s.model, g.stop)
    g.run(max_decisions=1)
    kinds = [e["kind"] for e in log.recent]
    assert "episode_error" not in kinds and "pool_exhausted" not in kinds
    assert _stop_lines(log) == ["Stopped while waiting for the models: no strategy review this time"], \
        "one line per stop: the decision after the review is not called"


def _decider(asked: list):
    """A decisions model that records each call and answers "expand"."""
    def respond(messages, info):
        asked.append("decide")
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"directive": "expand", "reason": "test"})])
    return FunctionModel(respond)


def test_a_stop_during_the_review_wait_starts_no_decision_call(setup, monkeypatch):  # noqa: F811
    """Final review, finding 1: the start-of-run review's pool is down and the decisions pool answers; a Stop
    during the review's wait starts no decision call afterwards, and the stop gets its one plain line."""
    s, log = setup
    asked: list = []

    def strategist(messages, info):
        raise E503
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=_decider(asked),
                 role_models={"strategy": FunctionModel(strategist, model_name="gemini-pro-latest")})
    _stop_in_the_wait(monkeypatch, lambda: g.health, "gemini-pro-latest", g.stop)
    g.run(max_decisions=1)
    assert asked == [], "no decision call after the stop"
    assert _stop_lines(log) == ["Stopped while waiting for the models: no strategy review this time"]
    assert not any(e["kind"] in ("episode_error", "pool_exhausted") for e in log.recent)


def test_a_stop_during_the_review_call_starts_no_decision_call(setup):  # noqa: F811
    """The Stop comes while the review's model answers (no wait): the decision is not called, and its gate
    gives the stop's one line."""
    s, log = setup
    asked: list = []
    holder: dict = {}

    def strategist(messages, info):
        holder["g"].stop()
        return _quiet_no_change(info)
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=_decider(asked),
                 role_models={"strategy": FunctionModel(strategist, model_name="gemini-pro-latest")})
    holder["g"] = g
    g.run(max_decisions=1)
    assert asked == []
    assert _stop_lines(log) == [] and [e["text"] for e in log.recent if e["kind"] == "journal"
                                       and e["text"].startswith("Stopped")] == [
        "Stopped: no decision this time; the directive stays"]


def test_a_stopping_run_starts_no_strategy_review(setup):  # noqa: F811
    """The event review after a decision and a scheduled one are gated too; the stop's line is given once."""
    s, log = setup
    asked: list = []

    def strategist(messages, info):
        asked.append("review")
        return _quiet_no_change(info)
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"),
                 role_models={"strategy": FunctionModel(strategist, model_name="gemini-pro-latest")})
    g.stop()
    assert g._maybe_event_review({"date": "2200.01.01"}, "new war", retry=True) is False
    g._review_strategy({"date": "2200.01.01"}, "scheduled after 5 decisions")
    assert asked == []
    assert [e["text"] for e in log.recent if e["kind"] == "journal"] == ["Stopped: no strategy review this time"]


def test_a_stop_during_the_retry_starts_no_further_model(setup):  # noqa: F811
    """Ruling 20's retry: a stop that ended one entry's pool wait starts no call on the next entry."""
    from pilot.modelguard import PoolExhausted
    s, log = setup
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"))
    entries = [{"model": "google:gemini-pro-latest", "thinking": "low"},
               {"model": "google:gemini-3.8-flash", "thinking": "low"}]
    g._retry_models = lambda: entries
    g._agent_for = lambda entry, role: entry
    asked = []

    def ask(agent):
        asked.append(agent["model"])
        g.stop()                                       # the Stop arrives during this entry's pool wait
        raise PoolExhausted("decisions retry", [], [agent["model"]], stopped=True)
    assert g._retry_decision(ask) is None
    assert asked == ["google:gemini-pro-latest"]
    assert not any(e["kind"] == "pool_exhausted" for e in log.recent), "a stop is not a pool failure"


def test_the_pool_hooks_read_the_stop_flag(setup):  # noqa: F811
    s, log = setup
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"))
    hooks = [g._hooks("chat", g._pool("chat"), None, [], {}), g._guard_hooks("decisions retry")]
    assert [h.stopping() for h in hooks] == [False, False]
    g.control.stopping = True
    assert [h.stopping() for h in hooks] == [True, True]


def test_an_unusable_answer_runs_again_on_the_next_model(setup):  # noqa: F811
    """Plan ruling P1: the request cap is not a model failure, but the run is tried from the next model."""
    s, log = setup

    def chatty(messages, info):
        if _is_strategy_review(info):
            return _quiet_no_change(info)
        return ModelResponse(parts=[ToolCallPart("consult", {"query": "more"})])
    game = FakeStellaris([briefing("2200.01.01")])
    Governor(s, game, log, model=FunctionModel(chatty, model_name="gemini-3.8-flash"),
             fallback=decisions("expand")).run(max_decisions=1)
    assert "governor_directive_expand" in game.flags
    fb = [e for e in log.recent if e["kind"] == "model_fallback"][-1]
    assert fb["failure"] == "answer" and "UsageLimitExceeded" in fb["error"]


def test_the_kill_switch_keeps_whole_run_retries(setup):  # noqa: F811
    s, log = setup
    s = replace(s, model_guard=False, retry_delays=(0,))
    s.__class__ = setup[0].__class__
    open_store(s.runs_dir)._exec("DROP TABLE model_usage")     # a guard that read it would note the failure
    first, _ = consult_then_503()
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=first, fallback=decisions("expand"))
    g.run(max_decisions=1)
    g.set_models([{"model": "google:gemini-3.7-flash", "thinking": "high"}])
    assert sum(e["kind"] == "consult" for e in log.recent) == 2, "the old path replays the run"
    assert not any(e["kind"] == "model_breaker" for e in log.recent)
    assert "model_health" not in log.state.info, "nothing of the guard is published"
    assert not any("model guard" in str(e.get("error", "")) for e in log.recent)


@pytest.mark.parametrize("guard", [True, False])
def test_a_retry_model_whose_agent_cannot_be_built_is_passed_over(setup, guard):  # noqa: F811
    """Ruling 20's retry goes on to the next Strategy model when one's agent cannot be built, on both
    paths (the agent is built inside the retry's own error handling, as before the guard)."""
    s, log = setup
    entries = [{"model": "google:gemini-a", "thinking": "high"}, {"model": "google:gemini-b", "thinking": "high"}]
    s = replace(s, model_guard=guard, roles={"strategy": {"models": entries, "rotate": False}})
    s.__class__ = setup[0].__class__
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"))

    def agent_for(entry, role="decisions"):
        if entry["model"] == "google:gemini-a":
            raise RuntimeError("cannot build")
        return "agent b"
    g._agent_for = agent_for
    assert g._retry_decision(lambda agent: agent) == ("agent b", entries[1])


def test_changing_models_clears_broken_marks(setup):  # noqa: F811
    s, log = setup
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"))
    from pilot.modelguard import BROKEN, Failure
    g.health.failed("google:gemini-3.7-flash", Failure(BROKEN, 404))
    g.set_models([{"model": "google:gemini-3.7-flash", "thinking": "high"}])
    assert g.health.status("google:gemini-3.7-flash") == "closed"
