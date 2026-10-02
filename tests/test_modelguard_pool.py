"""Guarded models and pools (docs/design/2026-10-02-model-guard-design.md, rulings 4-5, 7, 10-11, 16): a
failed request moves to the next model inside the same run, so a tool runs once; each failure kind gets
its retry rule; the order skips open and broken models and puts a failed family last."""

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
    def __init__(self):
        self.events = []

    def hooks(self):
        def rec(kind):
            return lambda **kw: self.events.append((kind, kw))
        return G.Hooks(on_try=rec("try"), on_retry=rec("retry"), on_fallback=rec("fallback"), on_pace=rec("pace"))

    def kinds(self):
        return [k for k, _ in self.events]


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


def test_everything_open_waits_up_to_the_limit_then_gives_up(monkeypatch):
    clock, waits = Clock(), []

    async def sleep(seconds):
        waits.append(seconds)
        clock.t += seconds
    monkeypatch.setattr(G, "_sleep", sleep)
    h, _ = make_health(clock)
    a = Script(E503)
    with pytest.raises(G.PoolExhausted) as e:
        run(pool_of(h, ("google:gemini-3.8-flash", a)))
    # the 503 and its retry open the breaker for 60 s; the pool waits once; the trial fails (no retry)
    assert waits == [1.0, 60.0] and a.calls == 3
    assert e.value.causes() == [{"model": "google:gemini-3.8-flash", "error": "overloaded (503)"}] * 2
    waits.clear()
    h2, _ = make_health(clock, pool_max_wait_s=30)
    b = Script(E503)
    with pytest.raises(G.PoolExhausted):
        run(pool_of(h2, ("google:gemini-3.8-flash", b)))
    assert waits == [1.0] and b.calls == 2, "a 60 s window is over the 30 s limit: no wait"


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
    hooks = G.event_hooks(lambda kind, /, **d: events.append((kind, d)), "chat", G.family)
    f = G.Failure(G.OVERLOADED, 503)
    hooks.on_retry(name="google:gemini-3.8-flash", failure=f, delay=1.0, attempt=1, request=2)
    hooks.on_fallback(name="google:gemini-3.8-flash", failure=f, next="claude-code:opus", request=2)
    hooks.on_pace(name="google:gemini-3.8-flash", waited=1.5)
    assert events[0] == ("model_retry", {"error": "model gemini-3.8-flash answered 503", "delay": 1.0, "attempt": 1,
                                         "role": "chat", "model": "google:gemini-3.8-flash", "kind": "overloaded",
                                         "family": "gemini-flash", "request": 2})
    assert events[1] == ("model_fallback", {"role": "chat", "model": "google:gemini-3.8-flash",
                                            "error": "model gemini-3.8-flash answered 503", "fallback": "claude-code:opus",
                                            "kind": "overloaded", "family": "gemini-flash", "request": 2})
    assert events[2] == ("model_pace", {"model": "google:gemini-3.8-flash", "waited_s": 1.5, "role": "chat"})
    out = []
    G.emit_breaker(lambda kind, /, **d: out.append((kind, d)), "google:gemini-3.8-flash",
                   {"state": "open", "until": 5.0, "reason": "overloaded (503)", "openings": 1, "family": "gemini-flash",
                    "caution": False})
    assert out == [("model_breaker", {"model": "google:gemini-3.8-flash", "family": "gemini-flash", "state": "open",
                                      "until": 5.0, "reason": "overloaded (503)", "openings": 1})]
