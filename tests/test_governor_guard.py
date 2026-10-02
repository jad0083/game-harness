"""The governors on the model guard (docs/design/2026-10-02-model-guard-design.md, rulings 11, 17, 19,
21-23): a decision that loses its model mid-run continues on the next one without running a tool twice,
Deciding and the events say what happened, and PILOT_MODEL_GUARD=0 keeps the whole-run retries."""

from __future__ import annotations

from dataclasses import replace

from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from test_governor import FakeStellaris, _is_strategy_review, _quiet_no_change, briefing, decisions, setup  # noqa: F401

from pilot.governor import Governor

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
    first, _ = consult_then_503()
    Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=first, fallback=decisions("expand")).run(max_decisions=1)
    assert sum(e["kind"] == "consult" for e in log.recent) == 2, "the old path replays the run"
    assert not any(e["kind"] == "model_breaker" for e in log.recent)


def test_changing_models_clears_broken_marks(setup):  # noqa: F811
    s, log = setup
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"))
    from pilot.modelguard import BROKEN, Failure
    g.health.failed("google:gemini-3.7-flash", Failure(BROKEN, 404))
    g.set_models([{"model": "google:gemini-3.7-flash", "thinking": "high"}])
    assert g.health.status("google:gemini-3.7-flash") == "closed"
