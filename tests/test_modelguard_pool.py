"""Guarded models and pools (docs/design/2026-10-02-model-guard-design.md, rulings 4-5, 7, 10-11, 16): a
failed request moves to the next model inside the same run, so a tool runs once; each failure kind gets
its retry rule; the order skips open and broken models and puts a failed family last. A pool whose models
are all down waits for one to come back, up to a budget (docs/design/2026-10-06-pool-wait-design.md)."""

from __future__ import annotations

import httpx
import pytest
from pydantic_ai import Agent, Tool
from pydantic_ai.exceptions import ModelHTTPError, UsageLimitExceeded
from pydantic_ai.messages import ModelResponse, TextPart, ThinkingPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import UsageLimits

from pilot import modelguard as G


class Clock:
    def __init__(self, t: float = 1_790_000_000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t


def make_health(clock=None, **kw):
    changes = []
    h = G.ModelHealth(G.GuardConfig(**kw), clock=clock or Clock(), on_change=lambda m, s: changes.append((m, s)))
    return h, changes


class Script:
    """A FunctionModel whose answers are scripted per call: an exception instance is raised, "tool" asks for
    the `bump` tool, any other string is the final answer."""

    def __init__(self, *steps):
        self.steps, self.calls, self.infos = list(steps), 0, []

    def __call__(self, messages, info: AgentInfo):
        self.infos.append(info)
        step = self.steps[min(self.calls, len(self.steps) - 1)]
        self.calls += 1
        if isinstance(step, BaseException):
            raise step
        if step == "tool":
            return ModelResponse(parts=[ToolCallPart("bump", {})])
        return ModelResponse(parts=[TextPart(step)])


def pool_of(health, *pairs, role="decisions"):
    """pairs: (name, Script)."""
    return G.PoolModel(role, [G.GuardedModel(FunctionModel(s, model_name=n.split(":")[-1]), n, health)
                              for n, s in pairs], health)


class Recorder:
    """The pool's reports; `waits` records on_wait too, and `stopping` is the hooks' stop flag."""

    def __init__(self, waits=False, stopping=None):
        self.events, self.waits, self.stopping = [], waits, stopping

    def hooks(self):
        def rec(kind):
            return lambda **kw: self.events.append((kind, kw))
        extra = {"on_wait": rec("wait")} if self.waits else {}
        if self.stopping is not None:
            extra["stopping"] = self.stopping
        return G.Hooks(on_try=rec("try"), on_retry=rec("retry"), on_fallback=rec("fallback"), on_pace=rec("pace"),
                       **extra)

    def kinds(self):
        return [k for k, _ in self.events]

    def of(self, kind):
        return [kw for k, kw in self.events if k == kind]


def run(pool, recorder=None, start=0, limit=10):
    bumps = []

    def bump() -> str:
        """Count a tool call."""
        bumps.append(1)
        return "bumped"
    pool.begin_run(start, recorder.hooks() if recorder else None)
    agent = Agent(pool, output_type=str, tools=[Tool(bump)])
    result = agent.run_sync("go", usage_limits=UsageLimits(request_limit=limit))
    return result, len(bumps)


E503 = ModelHTTPError(503, "gemini-3.8-flash", {"error": {"code": 503, "status": "UNAVAILABLE"}})
PRO, FLASH = "google:gemini-pro-latest", "google:gemini-3.8-flash"


@pytest.fixture
def ticking(monkeypatch):
    """The guard's sleeps advance a fake clock: `clock`, `slept` (each sleep), and `on_sleep(state)`, called
    after each sleep."""
    from types import SimpleNamespace
    state = SimpleNamespace(clock=Clock(), slept=[], on_sleep=None)

    async def sleep(seconds):
        state.slept.append(seconds)
        state.clock.t += seconds
        if state.on_sleep:
            state.on_sleep(state)
    monkeypatch.setattr(G, "_sleep", sleep)
    return state


def test_a_503_on_the_second_request_fails_over_and_the_tool_runs_once():
    h, _ = make_health()
    a, b = Script("tool", E503, E503), Script("done by b")
    rec = Recorder()
    pool = pool_of(h, ("google:gemini-3.8-flash", a), ("google:gemini-3.1-pro-preview", b))
    result, bumps = run(pool, rec)
    assert result.output == "done by b" and bumps == 1, "the run continued on b with its history"
    assert a.calls == 3 and b.calls == 1, "a: the tool call, the 503 and its one retry"
    assert h.status("google:gemini-3.8-flash") == "open"
    retry = [kw for k, kw in rec.events if k == "retry"]
    assert len(retry) == 1 and retry[0]["delay"] == 1.0 and retry[0]["request"] == 2
    fb = [kw for k, kw in rec.events if k == "fallback"]
    assert fb[0]["name"] == "google:gemini-3.8-flash" and fb[0]["next"] == "google:gemini-3.1-pro-preview"
    assert fb[0]["request"] == 2 and fb[0]["failure"].kind == G.OVERLOADED
    assert pool.last_answered == 1 and pool.requests == 2


def test_the_one_retry_can_answer(guard_waits):
    h, _ = make_health()
    a = Script(E503, "second try")
    result, _ = run(pool_of(h, ("google:gemini-3.8-flash", a)))
    assert result.output == "second try" and h.status("google:gemini-3.8-flash") == "closed"
    assert 1.0 in guard_waits


@pytest.mark.parametrize("exc,retried,state", [
    (ModelHTTPError(429, "m", {"error": {"details": [{"@type": "type.googleapis.com/google.rpc.RetryInfo",
                                                     "retryDelay": "2s"}]}}), True, "closed"),
    (ModelHTTPError(429, "m", {"error": {"details": [{"@type": "type.googleapis.com/google.rpc.RetryInfo",
                                                     "retryDelay": "37s"}]}}), False, "open"),
    (ModelHTTPError(429, "m", {"error": {"details": [{"@type": "type.googleapis.com/google.rpc.QuotaFailure",
                                                     "violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel"}]}]}}),
     False, "open"),
    (ModelHTTPError(404, "m"), False, "broken"),
    (ModelHTTPError(403, "m"), False, "broken"),
    (ModelHTTPError(400, "m"), False, "closed"),
    (httpx.ReadTimeout("slow"), False, "open"),
    (ValueError("odd"), False, "open"),
])
def test_each_failure_kind_follows_ruling_7(exc, retried, state, guard_waits):
    h, _ = make_health()
    a = Script(exc, "a answered") if retried else Script(exc)
    b = Script("b answered")
    rec = Recorder()
    result, _ = run(pool_of(h, ("google:gemini-3.8-flash", a), ("anthropic:claude-sonnet-5", b)), rec)
    assert result.output == ("a answered" if retried else "b answered")
    assert ("retry" in rec.kinds()) is retried and a.calls == (2 if retried else 1)
    assert h.status("google:gemini-3.8-flash") == state
    if retried:
        assert 2.0 in guard_waits, "the RetryInfo delay, jitter at its lower bound"


def test_a_daily_quota_opens_until_midnight_pacific():
    clock = Clock()
    h, changes = make_health(clock)
    quota = ModelHTTPError(429, "m", {"error": {"details": [{"@type": "x.QuotaFailure",
                                                           "violations": [{"quotaId": "RequestsPerDay"}]}]}})
    run(pool_of(h, ("google:gemini-3.8-flash", Script(quota)), ("google:gemini-3.1-pro-preview", Script("ok"))))
    snap = [s for m, s in changes if m == "google:gemini-3.8-flash"][-1]
    assert snap["until"] == round(G.next_pacific_midnight(clock.t), 1)


def test_a_trial_gets_no_retry_and_reopens_with_the_doubled_window():
    clock = Clock()
    h, changes = make_health(clock)
    a, b = Script(E503), Script("b")
    pool = pool_of(h, ("google:gemini-3.8-flash", a), ("anthropic:claude-sonnet-5", b))
    run(pool)
    assert a.calls == 2
    clock.t += 60
    rec = Recorder()
    run(pool, rec)
    assert a.calls == 3, "the trial: one request, no retry"
    assert [s for m, s in changes if m == "google:gemini-3.8-flash"][-1]["until"] == round(clock.t + 120, 1)


def test_order_rotation_caution_and_skips():
    clock = Clock()
    h, _ = make_health(clock)
    names = ["google:gemini-3.8-flash", "google:gemini-3.7-flash", "google:gemini-3.1-pro-preview", "claude-code:opus"]
    pool = pool_of(h, *[(n, Script("x")) for n in names])
    pool.begin_run(1)
    assert pool.ordered() == ([1, 2, 3, 0], [])
    h.failed("google:gemini-3.8-flash", G.Failure(G.OVERLOADED, 503))
    pool.begin_run(0)
    assert pool.ordered() == ([2, 3, 1], ["google:gemini-3.8-flash"]), "3.7 Flash after the other families"
    h.failed("claude-code:opus", G.Failure(G.BROKEN, 404))
    assert pool.ordered() == ([2, 1], ["google:gemini-3.8-flash", "claude-code:opus"])
    clock.t += 60
    assert pool.ordered() == ([0, 1, 2], ["claude-code:opus"]), "a trial keeps its place; the caution ended with the window"


def test_duplicate_entries_share_a_breaker_and_one_family_pools_keep_every_model():
    h, _ = make_health()
    pool = pool_of(h, ("google:gemini-3.1-pro-preview", Script(E503)), ("google:gemini-3.1-pro-preview", Script("low")),
                   ("google:gemini-3.8-flash", Script("flash")))
    result, _ = run(pool)
    assert result.output == "flash", "the second 3.1 Pro entry shares the open breaker"
    flash = pool_of(h, ("google:gemini-3.8-flash", Script("a")), ("google:gemini-3.7-flash", Script("b")))
    h.failed("google:gemini-3.6-flash", G.Failure(G.OVERLOADED, 503))
    flash.begin_run(0)
    assert flash.ordered() == ([0, 1], []), "caution reorders, never drops"


def test_everything_open_waits_up_to_the_limit_then_gives_up(ticking):
    h, _ = make_health(ticking.clock)
    a = Script(E503)
    with pytest.raises(G.PoolExhausted) as e:
        run(pool_of(h, ("google:gemini-3.8-flash", a)))
    # the 503 and its 1 s retry open the breaker for 60 s; the pool waits 60 s; the trial fails (no retry) and
    # opens it for 120 s, past the 60 s left of the 120 s budget: the pool gives up at once
    assert ticking.slept[0] == 1.0 and sum(ticking.slept) == 61.0 and a.calls == 3
    assert e.value.causes() == [{"model": "google:gemini-3.8-flash", "error": "overloaded (503)"}] * 2
    ticking.slept.clear()
    h2, _ = make_health(ticking.clock, pool_max_wait_s=30)
    b = Script(E503)
    with pytest.raises(G.PoolExhausted):
        run(pool_of(h2, ("google:gemini-3.8-flash", b)))
    assert ticking.slept == [1.0] and b.calls == 2, "a 60 s window is past the 30 s budget: no wait, only the retry"


def test_the_pool_waits_for_the_earliest_window_and_answers(ticking):
    """Pool-wait ruling 1: both models open, their windows ending in 40 s and 70 s; the pool sleeps until the
    first ends (in steps of at most POOL_STOP_STEP_S), then sends that model its trial, which answers."""
    clock = ticking.clock
    h, _ = make_health(clock, pool_max_wait_s=120)
    clock.t -= 20
    h.failed(PRO, G.Failure(G.OVERLOADED, 503))        # a 60 s window: 40 s left
    clock.t += 30
    h.failed(FLASH, G.Failure(G.OVERLOADED, 503))      # 70 s left
    clock.t -= 10
    a, b = Script("pro answered"), Script("flash answered")
    rec = Recorder(waits=True)
    result, _ = run(pool_of(h, (PRO, a), (FLASH, b)), rec)
    assert result.output == "pro answered" and (a.calls, b.calls) == (1, 0)
    assert sum(ticking.slept) == pytest.approx(40.0) and max(ticking.slept) <= G.POOL_STOP_STEP_S
    assert rec.of("wait") == [{"models": [PRO, FLASH], "seconds": 40.0, "waited": 0.0, "budget": 120.0,
                               "reason": "every model is overloaded"}]
    assert h.status(PRO) == "closed" and h.status(FLASH) == "open"


def test_the_wait_ends_at_the_budget_however_windows_move(ticking):
    """Each failed trial doubles the window (60 s, then 120 s, then 240 s); the pool waits only for a window that
    ends within the budget left, so its waiting never passes the budget (ruling W3)."""
    h, _ = make_health(ticking.clock, pool_max_wait_s=120)
    a = Script(E503)
    rec = Recorder(waits=True)
    with pytest.raises(G.PoolExhausted) as e:
        run(pool_of(h, (FLASH, a)), rec)
    waits = rec.of("wait")
    assert a.calls == 3, "the 503, its retry, then the trial after the first window"
    assert [(w["seconds"], w["waited"]) for w in waits] == [(60.0, 0.0)], "the 120 s window ends past the 60 s left"
    assert waits[0]["reason"] == "every model is overloaded" and waits[0]["budget"] == 120.0
    assert sum(ticking.slept) == 61.0, "the guard's 1 s retry, then the one window"
    assert [c["error"] for c in e.value.causes()] == ["overloaded (503)"] * 2 and not e.value.stopped
    ticking.slept.clear()
    h2, _ = make_health(ticking.clock, pool_max_wait_s=180)        # 180 s or more: the second trial too
    b = Script(E503)
    rec2 = Recorder(waits=True)
    with pytest.raises(G.PoolExhausted):
        run(pool_of(h2, (FLASH, b)), rec2)
    assert [(w["seconds"], w["waited"]) for w in rec2.of("wait")] == [(60.0, 0.0), (120.0, 60.0)]
    assert b.calls == 4 and sum(ticking.slept) == 181.0, "the 120 s window ends exactly at the budget; then it is spent"


def test_a_daily_quota_is_not_waited_for(ticking):
    """Ruling W3: every model on its daily quota (open until midnight Pacific) cannot come back within the
    budget, so the pool gives up at once instead of sleeping the budget out."""
    h, _ = make_health(ticking.clock)
    for name in (PRO, FLASH):
        h.failed(name, G.Failure(G.DAILY_QUOTA, 429))
    rec = Recorder(waits=True)
    with pytest.raises(G.PoolExhausted) as e:
        run(pool_of(h, (PRO, Script("x")), (FLASH, Script("y"))), rec)
    assert ticking.slept == [] and rec.of("wait") == []
    assert [c["error"] for c in e.value.causes()] == ["skipped", "skipped"]


def test_a_second_request_waits_for_a_running_trial(ticking):
    """Ruling 5: chat finds the decision holding the model's trial (half-open); it looks again every POOL_POLL_S
    and is answered once that trial succeeds, instead of failing at once."""
    clock = ticking.clock
    h, _ = make_health(clock)
    h.failed(PRO, G.Failure(G.OVERLOADED, 503))
    clock.t += 60
    assert h.begin_trial(PRO)                           # the decision's request holds the trial

    def trial_answers(state):                           # after two poll steps
        if sum(state.slept) >= 2 * G.POOL_POLL_S and h.status(PRO) == "half_open":
            h.succeeded(PRO)
    ticking.on_sleep = trial_answers
    a = Script("chat answered")
    rec = Recorder(waits=True)
    result, _ = run(pool_of(h, (PRO, a), role="chat"), rec)
    assert result.output == "chat answered" and a.calls == 1
    assert [(w["seconds"], w["reason"]) for w in rec.of("wait")] == [(G.POOL_POLL_S, f"a trial is running on {PRO}")] * 2
    assert sum(ticking.slept) == pytest.approx(2 * G.POOL_POLL_S)


def test_an_abandoned_trial_is_picked_up_by_the_waiting_request(ticking):
    """Another request holds the model's trial, then abandons it (cancelled, no verdict): the model is due for
    its trial again, and the waiting request takes it and is answered."""
    clock = ticking.clock
    h, _ = make_health(clock)
    h.failed(PRO, G.Failure(G.OVERLOADED, 503))
    clock.t += 60
    assert h.begin_trial(PRO)                           # the other request's trial

    def abandoned(state):                               # during the first poll step
        if h.status(PRO) == "half_open":
            h.abandon_trial(PRO)
    ticking.on_sleep = abandoned
    a = Script("answered on the abandoned trial")
    rec = Recorder(waits=True)
    result, _ = run(pool_of(h, (PRO, a), role="chat"), rec)
    assert result.output == "answered on the abandoned trial" and a.calls == 1
    assert [w["reason"] for w in rec.of("wait")] == [f"a trial is running on {PRO}"]
    assert sum(ticking.slept) == pytest.approx(G.POOL_POLL_S) and h.status(PRO) == "closed"


def test_a_model_whose_trial_succeeded_elsewhere_is_tried_again(ticking):
    """The request lost the model's trial to another request (its first try failed over); once that trial
    succeeds the model is closed, and the waiting request sends it the request."""
    clock = ticking.clock
    h, _ = make_health(clock)
    h.failed(PRO, G.Failure(G.OVERLOADED, 503))
    clock.t += 60
    a = Script("answered after the other trial")
    pool = pool_of(h, (PRO, a))
    real_ordered, taken = pool.ordered, []

    def ordered(exclude=frozenset()):
        out = real_ordered(exclude)
        if not taken:                       # another role takes the trial between this order and the send
            taken.append(h.begin_trial(PRO))
        return out
    pool.ordered = ordered
    ticking.on_sleep = lambda state: h.succeeded(PRO) if h.status(PRO) == "half_open" else None
    rec = Recorder(waits=True)
    result, _ = run(pool, rec)
    assert taken == [True] and result.output == "answered after the other trial" and a.calls == 1
    assert rec.of("fallback")[0]["failure"].cause == "its trial is running" and len(rec.of("wait")) == 1


def test_a_rejected_model_is_not_sent_the_request_again_after_a_wait(ticking):
    """A rejected request (400) leaves the breaker closed; the wait for another model does not send the same
    request to the model that rejected it again."""
    clock = ticking.clock
    h, _ = make_health(clock, min_call_interval_s={})       # no pacing wait: every sleep is the pool's
    clock.t -= 20
    h.failed(PRO, G.Failure(G.OVERLOADED, 503))        # 40 s left
    clock.t += 20
    a, b = Script(ModelHTTPError(400, "gemini-3.8-flash")), Script("pro answered")
    result, _ = run(pool_of(h, (FLASH, a), (PRO, b)))
    assert result.output == "pro answered" and (a.calls, b.calls) == (1, 1)
    assert sum(ticking.slept) == pytest.approx(40.0)
    ticking.slept.clear()
    c = Script(ModelHTTPError(400, "gemini-3.8-flash"))
    with pytest.raises(G.PoolExhausted):
        run(pool_of(h, (FLASH, c)))
    assert ticking.slept == [] and c.calls == 1, "nothing else to wait for: at once"


def test_all_broken_fails_at_once(ticking):
    h, _ = make_health(ticking.clock, min_call_interval_s={})       # no pacing wait: every sleep is the pool's
    e404 = ModelHTTPError(404, "m")
    rec = Recorder(waits=True)
    with pytest.raises(G.PoolExhausted) as e:
        run(pool_of(h, (PRO, Script(e404)), (FLASH, Script(e404))), rec)
    assert ticking.slept == [] and rec.of("wait") == []
    assert [c["error"] for c in e.value.causes()] == ["unusable (404)"] * 2


def test_a_stop_ends_the_wait(ticking):
    """Ruling 3: `stopping()` turns true after the first 1 s step of a 60 s wait; the pool gives up at once."""
    h, _ = make_health(ticking.clock)
    h.failed(PRO, G.Failure(G.OVERLOADED, 503))
    a = Script("never sent")
    rec = Recorder(waits=True, stopping=lambda: len(ticking.slept) >= 1)
    with pytest.raises(G.PoolExhausted) as e:
        run(pool_of(h, (PRO, a)), rec)
    assert sum(ticking.slept) <= 2 * G.POOL_STOP_STEP_S and a.calls == 0
    assert e.value.stopped and e.value.causes()[-1] == {"model": "-", "error": "stopped while waiting"}
    assert str(e.value).endswith("stopped while waiting")
    assert rec.of("wait")[0]["seconds"] == 60.0
    ticking.slept.clear()
    already = Recorder(waits=True, stopping=lambda: True)  # a run already stopping: no wait, and no model_wait
    with pytest.raises(G.PoolExhausted) as e2:
        run(pool_of(h, (PRO, Script("never sent"))), already)
    assert e2.value.stopped and ticking.slept == [] and already.of("wait") == []


def test_no_budget_fails_at_once(ticking):
    """PILOT_POOL_WAIT_S=0: an open pool raises at once, as before ruling 11, and so does a running trial."""
    clock = ticking.clock
    h, _ = make_health(clock, pool_max_wait_s=0)
    h.failed(PRO, G.Failure(G.OVERLOADED, 503))
    rec = Recorder(waits=True)
    with pytest.raises(G.PoolExhausted):
        run(pool_of(h, (PRO, Script("x"))), rec)
    clock.t += 60
    assert h.begin_trial(PRO)
    with pytest.raises(G.PoolExhausted):
        run(pool_of(h, (PRO, Script("x"))), rec)
    assert ticking.slept == [] and rec.of("wait") == []


def test_event_hooks_emit_model_wait():
    events, seen = [], []
    extra = G.Hooks(on_wait=lambda **kw: seen.append(kw), stopping=lambda: True)
    hooks = G.event_hooks(lambda kind, **d: events.append((kind, d)), "chat", G.family, extra)
    hooks.on_wait(models=[PRO, FLASH], seconds=40.0, waited=45.0, budget=120.0, reason="every model is overloaded")
    assert events == [("model_wait", {"role": "chat", "models": [PRO, FLASH], "seconds": 40.0, "waited_s": 45.0,
                                      "budget_s": 120.0, "reason": "every model is overloaded"})]
    assert len(seen) == 1 and hooks.stopping() is True, "the extra hooks' own, when no stop flag is given"
    flag = {"stop": False}
    own = G.event_hooks(lambda kind, **d: None, "chat", G.family, extra, stopping=lambda: flag["stop"])
    assert own.stopping() is False
    flag["stop"] = True
    assert own.stopping() is True
    assert G.event_hooks(lambda kind, **d: None, "chat", G.family).stopping() is False
    assert G.Hooks().stopping() is False


def test_after_an_overload_the_request_goes_to_another_family_first():
    h, _ = make_health()
    a, b, c = Script(E503), Script("3.7 answered"), Script("pro answered")
    rec = Recorder()
    result, _ = run(pool_of(h, ("google:gemini-3.8-flash", a), ("google:gemini-3.7-flash", b),
                            ("google:gemini-3.1-pro-preview", c)), rec)
    assert result.output == "pro answered" and b.calls == 0
    assert [kw["next"] for k, kw in rec.events if k == "fallback"] == ["google:gemini-3.1-pro-preview"]


def test_the_request_cap_passes_through_and_opens_nothing():
    h, changes = make_health()
    pool = pool_of(h, ("google:gemini-3.8-flash", Script("tool")), ("google:gemini-3.1-pro-preview", Script("x")))
    with pytest.raises(UsageLimitExceeded):
        run(pool, limit=2)
    assert changes == [] and h.status("google:gemini-3.8-flash") == "closed"


def test_entry_settings_reach_their_model():
    h, _ = make_health()
    a = Script("ok")
    gm = G.GuardedModel(FunctionModel(a), "google:gemini-3.8-flash", h,
                        settings={"google_thinking_config": {"thinking_level": "high"}, "timeout": 120})
    pool = G.PoolModel("decisions", [gm], h)
    pool.begin_run(0)
    Agent(pool, output_type=str, model_settings={"timeout": 120}).run_sync("go")
    assert a.infos[0].model_settings["google_thinking_config"] == {"thinking_level": "high"}


def test_a_model_that_cannot_be_built_is_broken_and_skipped():
    h, _ = make_health()
    b = Script("b answered")
    pool = G.PoolModel("decisions", [G.GuardedModel("nosuchprovider:model", "nosuchprovider:model", h),
                                     G.GuardedModel(FunctionModel(b), "anthropic:claude-sonnet-5", h)], h)
    result, _ = run(pool)
    assert result.output == "b answered" and h.status("nosuchprovider:model") == "broken"


def test_pacing_waits_are_reported(guard_waits):
    h, _ = make_health(min_call_interval_s={"google": 1.5})
    rec = Recorder()
    run(pool_of(h, ("google:gemini-3.8-flash", Script("tool", "done"))), rec)
    assert 1.5 in guard_waits and [kw["waited"] for k, kw in rec.events if k == "pace"] == [1.5]


def test_counts_include_failed_requests():
    h, _ = make_health()
    run(pool_of(h, ("google:gemini-3.8-flash", Script(E503, E503)), ("google:gemini-3.1-pro-preview", Script("ok"))))
    assert h.today("google:gemini-3.8-flash") == 2 and h.today("google:gemini-3.1-pro-preview") == 1


def test_a_run_from_gemini_with_thoughts_continues_on_anthropic():
    """Ruling 25: the history holds Gemini thought parts; the Anthropic model prepares and sends it."""
    import httpx2  # the Anthropic SDK's own HTTP layer
    from anthropic import AsyncAnthropic
    from pydantic_ai.models.anthropic import AnthropicModel
    from pydantic_ai.providers.anthropic import AnthropicProvider
    sent = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        sent.append(request.read())
        return httpx2.Response(200, json={"id": "msg_1", "type": "message", "role": "assistant", "model": "claude-sonnet-5",
                                         "content": [{"type": "text", "text": "claude answered"}],
                                         "stop_reason": "end_turn", "stop_sequence": None,
                                         "usage": {"input_tokens": 10, "output_tokens": 2}})
    client = AsyncAnthropic(api_key="test", max_retries=0, http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)))
    claude = AnthropicModel("claude-sonnet-5", provider=AnthropicProvider(anthropic_client=client))

    def gemini(messages, info):
        if len(messages) == 1:
            return ModelResponse(parts=[ThinkingPart("weighing it", signature="c2ln", provider_name="google-gla"),
                                        ToolCallPart("bump", {})], model_name="gemini-3.8-flash")
        raise E503
    h, _ = make_health()
    pool = G.PoolModel("decisions", [G.GuardedModel(FunctionModel(gemini), "google:gemini-3.8-flash", h),
                                     G.GuardedModel(claude, "anthropic:claude-sonnet-5", h)], h)
    result, bumps = run(pool)
    assert result.output == "claude answered" and bumps == 1 and len(sent) == 1


def test_sdk_retries_are_off(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    g = G.build_model("google:gemini-3.8-flash")
    assert g.client._api_client._http_options.retry_options is None
    a = G.build_model("anthropic:claude-sonnet-5")
    assert a.client.max_retries == 0
    assert G.build_model("claude-code:opus").model_name == "claude-code:opus"


def test_event_hooks_write_the_events():
    events = []
    hooks = G.event_hooks(lambda kind, **d: events.append((kind, d)), "chat", G.family)
    f = G.Failure(G.OVERLOADED, 503)
    hooks.on_retry(name="google:gemini-3.8-flash", failure=f, delay=1.0, attempt=1, request=2)
    hooks.on_fallback(name="google:gemini-3.8-flash", failure=f, next="claude-code:opus", request=2)
    hooks.on_pace(name="google:gemini-3.8-flash", waited=1.5)
    assert events[0] == ("model_retry", {"error": "model gemini-3.8-flash answered 503", "delay": 1.0, "attempt": 1,
                                         "role": "chat", "model": "google:gemini-3.8-flash", "failure": "overloaded",
                                         "family": "gemini-flash", "request": 2})
    assert events[1] == ("model_fallback", {"role": "chat", "model": "google:gemini-3.8-flash",
                                            "error": "model gemini-3.8-flash answered 503", "fallback": "claude-code:opus",
                                            "failure": "overloaded", "family": "gemini-flash", "request": 2})
    assert events[2] == ("model_pace", {"model": "google:gemini-3.8-flash", "waited_s": 1.5, "role": "chat"})
    out = []
    G.emit_breaker(lambda kind, **d: out.append((kind, d)), "google:gemini-3.8-flash",
                   {"state": "open", "until": 5.0, "reason": "overloaded (503)", "openings": 1, "family": "gemini-flash",
                    "caution": False})
    assert out == [("model_breaker", {"model": "google:gemini-3.8-flash", "family": "gemini-flash", "state": "open",
                                      "until": 5.0, "reason": "overloaded (503)", "openings": 1})]


def test_a_trial_that_is_rejected_is_due_again():
    clock = Clock()
    h, _ = make_health(clock)
    a = Script(E503, E503, ModelHTTPError(400, "m"), "a answers")
    b = Script("b")
    pool = pool_of(h, ("google:gemini-3.8-flash", a), ("anthropic:claude-sonnet-5", b))
    run(pool)
    assert h.status("google:gemini-3.8-flash") == "open"
    clock.t += 60
    run(pool)
    assert h.status("google:gemini-3.8-flash") == "trial", "a rejected trial gives no verdict: not left half-open"
    result, _ = run(pool)
    assert result.output == "a answers" and h.status("google:gemini-3.8-flash") == "closed"


@pytest.mark.parametrize("method", ["reserve", "count"])
def test_a_guard_error_before_sending_fails_over_inside_the_run(method):
    """Limits that slipped past check_guard_settings make reserve() or count() raise: that model fails
    over within the run like any failure (its breaker opens), never the whole decision."""
    h, _ = make_health()
    real, seen = getattr(h, method), []

    def broken(model):
        seen.append(model)
        if model == "google:gemini-3.8-flash" and seen.count(model) == 2:
            raise ValueError("could not convert string to float: 'fast'")
        return real(model)
    setattr(h, method, broken)
    a, b = Script("tool", "a never answers this"), Script("done by b")
    rec = Recorder()
    result, bumps = run(pool_of(h, ("google:gemini-3.8-flash", a), ("anthropic:claude-sonnet-5", b)), rec)
    assert result.output == "done by b" and bumps == 1, "the tool ran once"
    assert a.calls == 1 and b.calls == 1
    fb = next(kw for k, kw in rec.events if k == "fallback")
    assert fb["failure"].kind == G.OTHER and "ValueError" in fb["failure"].cause
    assert fb["next"] == "anthropic:claude-sonnet-5"
    assert h.status("google:gemini-3.8-flash") == "open", "an `other` failure opens the breaker"


def test_malformed_limits_in_a_config_built_in_code_fail_over():
    h, _ = make_health(model_limits={"google:gemini-3.8-flash": {"rpm": "fast"}})
    a, b = Script("a"), Script("b answered")
    result, _ = run(pool_of(h, ("google:gemini-3.8-flash", a), ("anthropic:claude-sonnet-5", b)))
    assert result.output == "b answered" and a.calls == 0


def test_a_trial_taken_by_another_request_is_skipped():
    """Two requests saw the same trial due (another role's pool shares the health): the one that lost
    begin_trial moves on, without counting a request or changing the breaker."""
    clock = Clock()
    h, changes = make_health(clock)
    name = "google:gemini-3.8-flash"
    h.failed(name, G.Failure(G.OVERLOADED, 503))
    clock.t += 60
    a, b = Script("a"), Script("b answered")
    pool = pool_of(h, (name, a), ("anthropic:claude-sonnet-5", b))
    other = G.GuardedModel(FunctionModel(Script("other")), name, h)      # another role's entry for the model
    real_ordered, taken = pool.ordered, []

    def ordered(exclude=frozenset()):
        out = real_ordered(exclude)
        if not taken:                       # between this request's order and its send, the other takes it
            taken.append(other.health.begin_trial(name))
        return out
    pool.ordered = ordered
    rec = Recorder()
    result, _ = run(pool, rec)
    assert taken == [True] and result.output == "b answered" and a.calls == 0
    assert h.status(name) == "half_open", "the other request's trial is untouched"
    assert h.today(name) == 0 and changes[-1][1]["state"] == "half_open"
    fb = next(kw for k, kw in rec.events if k == "fallback")
    assert fb["failure"].kind == G.OTHER and fb["failure"].cause == "its trial is running"


@pytest.mark.parametrize("raised,kind,calls", [("connect", G.OVERLOADED, 2), ("timeout", G.TIMEOUT, 1)])
def test_anthropic_transport_errors_reach_the_guard_classified(raised, kind, calls):
    """The Anthropic SDK raises APIConnectionError / APITimeoutError from its httpx2 transport and
    pydantic-ai wraps them in ModelAPIError: the guard still sees an overload or a timeout."""
    import httpx2
    from anthropic import AsyncAnthropic
    from pydantic_ai.models.anthropic import AnthropicModel
    from pydantic_ai.providers.anthropic import AnthropicProvider
    sent = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        sent.append(1)
        if raised == "connect":
            raise httpx2.ConnectError("refused", request=request)
        raise httpx2.ReadTimeout("slow", request=request)
    client = AsyncAnthropic(api_key="test", max_retries=0,
                            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)))
    claude = AnthropicModel("claude-sonnet-5", provider=AnthropicProvider(anthropic_client=client))
    h, _ = make_health()
    b = Script("gemini answered")
    rec = Recorder()
    pool = G.PoolModel("decisions", [G.GuardedModel(claude, "anthropic:claude-sonnet-5", h),
                                     G.GuardedModel(FunctionModel(b), "google:gemini-3.1-pro-preview", h)], h)
    result, _ = run(pool, rec)
    assert result.output == "gemini answered" and len(sent) == calls, "an overload gets its one retry"
    assert [kw["failure"].kind for k, kw in rec.events if k == "fallback"] == [kind]
