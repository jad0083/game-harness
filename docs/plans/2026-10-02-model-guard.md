# Model Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every model request the pilot makes is paced, classified, retried at most once, and recorded in a circuit breaker per model; a role's models form a pool that moves a failed request to another model with the run's history, so no tool runs twice.

**Architecture:** A new module `src/pilot/modelguard.py` holds `ModelHealth` (breakers, pacing, daily counts; one per pilot process), `GuardedModel` (a pydantic-ai `WrapperModel` per pool entry) and `PoolModel` (a `FallbackModel` subclass with per-request ordering). The governors' `_call` runs each role's single pool agent instead of wrapping whole runs in `run_with_retry`; the GC4 pilot gets the same pool. Events keep their names and gain fields; the dashboard gets sentences for the new kinds and a model-health line.

**Tech Stack:** Python 3.13, pydantic-ai-slim 2.51.0 (`WrapperModel`, `FallbackModel`, `FunctionModel`), google-genai 2.25.0, anthropic SDK, anyio, httpx, stdlib `zoneinfo`; the dashboard is one HTML file with inline JS; tests are pytest, browser tests Playwright (`-m ui`).

**Spec:** `docs/design/2026-10-02-model-guard-design.md` (rulings 1-27; "ruling N" below means that spec's ruling N; "post-mortem ruling 20" means `docs/design/2026-09-27-postmortem-fixes-design.md` ruling 20).

## Global Constraints

- No new dependencies; `zoneinfo`, `anyio`, `httpx`, `anthropic` are already installed.
- Starting values (ruling 15): `overload_retry_s` (1.0, 2.0); `rate_retry_max_s` 10; `breaker_open_s` 60; `breaker_max_s` 600; `pool_max_wait_s` 60; `min_call_interval_s` `{"google": 0.5}`; `model_limits` `{}`; `model_families` `{}`; `model_timeout_s` stays 120.
- Environment (ruling 15): `PILOT_MODEL_GUARD` (default 1; 0 runs the code as at 8c80134), `PILOT_MIN_CALL_INTERVAL`, `PILOT_MODEL_LIMITS`, `PILOT_MODEL_FAMILIES` (JSON objects).
- Daily counts by America/Los_Angeles date in `runs/model-usage.json`, 7 days kept (ruling 14).
- Event names `model_retry` and `model_fallback` keep every existing field (`error`, `delay`, `attempt`, `role`, `model`, `fallback`); new fields `kind`, `family`, `request`; new kinds `model_breaker`, `model_pace`, `pool_exhausted` (rulings 21-22).
- google-genai `retry_options` stays None; Anthropic clients are built with `max_retries=0` (ruling 16).
- Commits only through `scripts/ci-commit.sh "type(scope): subject" "body"`; conventional commits; no AI or assistant attribution anywhere (no Co-Authored-By, no model names in commit messages); never stage `runs/`, `.env`, `.agent_token*`, `play/`, or the live learned files `corpora/*/learned/*` and `games/*/journal.md` that the running pilot changes.
- A commit that stages `src/pilot/static/dashboard.html` needs the Playwright UI tests to have run (`scripts/ci-ui-gate.sh`); run `.venv/bin/pytest -m ui tests/ui` before such a commit.
- Tests run with `.venv/bin/pytest`; the suite's per-test limit is 60 s (`tests/conftest.py`).
- Code comments describe the system, matching the surrounding code's density; no comments about who wrote the code.

## Review Focus

1. **Odd error bodies.** A 429 or 503 whose body is `None`, plain text, bytes or JSON in an unexpected shape must still classify (rate limited without a delay, or overloaded) and never raise from `classify`. Test: Task 1, `test_odd_429_bodies_are_rate_limited_without_a_delay`.
2. **A broken usage file.** `runs/model-usage.json` truncated, not JSON, or unwritable must not stop a run: counts start at 0 for the day, with one note. Test: Task 1, `test_an_unreadable_usage_file_starts_at_zero_with_one_note`.
3. **Pools that repeat a model or one family.** Two entries naming the same model (say 3.1 Pro at high and at low thinking) share one breaker. A pool whose models are all one family still tries every closed model. Test: Task 2, `test_duplicate_entries_share_a_breaker_and_one_family_pools_keep_every_model`.
4. **The request cap is not a model failure.** pydantic-ai's `UsageLimitExceeded` passes through the pool untouched, and no breaker changes. Test: Task 2, `test_the_request_cap_passes_through_and_opens_nothing`.
5. **Threads share one `ModelHealth`.** Chat and decision threads pacing concurrently each get distinct start slots. A trial abandoned by cancellation does not leave a model half-open forever. Tests: Task 1, `test_concurrent_reservations_get_distinct_slots` and `test_an_abandoned_trial_is_due_again`.

## Rulings made while planning

- **P1 (spec ruling 6 wording).** Ruling 6 says `UsageLimitExceeded` "passes through untouched, as today". At the request level that's true. Today, `_call` also catches any failed run (the request cap, an invalid output) and runs it again on the next model. With the guard, `_call` keeps that whole-run fallback for answers that are unusable. A failure to reach a model is handled inside the run, and `PoolExhausted` is raised at once. Task 3 also amends the spec sentence. **Why:** the Stellaris decision path has no retry of its own, so dropping the whole-run fallback would leave its current directive in place whenever a model spends its request cap on tool calls. **If wrong:** those runs replay tools, as they do today.
- **P2 (spec ruling 17, broken marks).** A pool rebuild clears the broken marks of every model in the new pools, a superset of the models it changes. **Why:** re-saving the same models on the dashboard is how a human says "try again" after fixing a key. **If wrong:** a broken model is tried once more, and that fails fast.
- **P3 (agent settings parameter name).** `_build`, `build_governor` and `build_agent` take `agent_settings=None` rather than `model_settings`. **Why:** `agent.py` and `governor.py` import a function named `model_settings`, and a parameter with that name would shadow it.

---

## File Structure

| File | Responsibility |
|---|---|
| `src/pilot/modelguard.py` (new) | Classification, families, Pacific day helpers, `GuardConfig`, `ModelHealth` (Task 1); `ModelUnavailable`, `PoolExhausted`, `Hooks`, `event_hooks`, `emit_breaker`, `build_model`, `GuardedModel`, `PoolModel` (Task 2) |
| `src/pilot/config.py` | The guard's settings and their environment variables (Task 1) |
| `src/pilot/governor.py` | `_call` on the pool, the kill-switch path, pools per role, hooks into Deciding and events, `info.model_health` (Task 3) |
| `src/pilot/civ6_governor.py` | `_build` takes `agent_settings` (Task 3) |
| `src/pilot/agent.py`, `src/pilot/controller.py` | The GC4 episode agent on a pool of `model` and `fallback_model` (Task 4) |
| `src/pilot/static/dashboard.html` | Activity sentences, kind sets, the model-health line, today's counts in the pool editor (Task 5) |
| `tests/conftest.py` | The guard's waits take no real time in tests (Task 1) |
| `tests/test_modelguard_health.py`, `tests/test_modelguard_pool.py`, `tests/test_governor_guard.py`, `tests/test_controller_guard.py`, `tests/ui/test_dashboard_model_health.py` (new) | Tests |
| `docs/pilot.md`, `README.md`, `ARCHITECTURE.md`, the spec | Docs (Tasks 3 and 5) |

---

### Task 1: Health core: classification, families, breakers, pacing, daily counts, settings

**Files:**
- Create: `src/pilot/modelguard.py`
- Modify: `src/pilot/config.py` (the `Settings` dataclass near line 55 and `from_env` near line 139)
- Modify: `tests/conftest.py` (append one autouse fixture)
- Test: `tests/test_modelguard_health.py`

**Interfaces:**
- Consumes: `pydantic_ai.exceptions.ModelHTTPError(status_code, model_name, body=None, *, headers=None)`; `Settings` fields.
- Produces (used by Tasks 2-5):
  - constants: `OVERLOADED`, `TIMEOUT`, `RATE_LIMITED`, `DAILY_QUOTA`, `BROKEN`, `REJECTED`, `OTHER`, `PACIFIC`;
  - `Failure(kind, status=None, retry_after=None, cause="")`;
  - `classify(e) -> Failure`, `describe(f) -> str`, `event_error(model, f) -> str`;
  - `provider(model) -> str`, `family(model, overrides=None) -> str`;
  - `pacific_day(now) -> str`, `next_pacific_midnight(now) -> float`;
  - `GuardConfig` (fields as ruling 15, plus `usage_file`; `GuardConfig.from_settings(s)`);
  - `retry_delay(f, trial, cfg, uniform=random.uniform) -> float | None`;
  - `ModelHealth(config, clock=time.time, on_change=None, on_note=None)` with methods `family(model)`, `status(model)` (returns `"closed" | "open" | "trial" | "half_open" | "broken"`), `begin_trial(model) -> bool`, `abandon_trial(model)`, `succeeded(model, input_tokens=None)`, `failed(model, f, reason=None)`, `cautioned(model) -> bool`, `earliest_reopen(models) -> float | None`, `clear_broken(models)`, `reserve(model) -> float`, `count(model) -> Failure | None`, `today(model) -> int`, `snapshot() -> dict`; attributes `cfg`, `clock`;
  - `on_change(model, snap)` where `snap = {"state", "until", "reason", "openings", "family", "caution"}`;
  - module globals `_sleep` (anyio.sleep) and `_uniform` (random.uniform), replaced in tests.
  - `Settings` gains `model_guard`, `overload_retry_s`, `rate_retry_max_s`, `breaker_open_s`, `breaker_max_s`, `pool_max_wait_s`, `min_call_interval_s`, `model_limits`, `model_families`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_modelguard_health.py`:

```python
"""Model guard health (docs/design/2026-10-02-model-guard-design.md, rulings 2-3, 6-9, 12-15): failures are
classified, breakers open and reopen with a doubling window, a failed family goes behind the others, and
requests are paced and counted per Pacific day."""

from __future__ import annotations

import json
import threading
from datetime import datetime

import httpx
import pytest
from pydantic_ai.exceptions import ModelHTTPError

from pilot import modelguard as G
from pilot.config import Settings


class Clock:
    def __init__(self, t: float = 1_790_000_000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t


def health(tmp_path=None, clock=None, **kw):
    cfg = G.GuardConfig(usage_file=(tmp_path / "model-usage.json") if tmp_path else None, **kw)
    changes, notes = [], []
    h = G.ModelHealth(cfg, clock=clock or Clock(), on_change=lambda m, s: changes.append((m, s)),
                      on_note=notes.append)
    return h, changes, notes


def gemini_429(quota_id="GenerateRequestsPerMinutePerProjectPerModel", delay="37s"):
    details = [{"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [{"quotaId": quota_id}]}]
    if delay:
        details.append({"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": delay})
    return ModelHTTPError(429, "gemini-3.8-flash", {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED",
                                                              "details": details}})


@pytest.mark.parametrize("exc,kind,status", [
    (ModelHTTPError(503, "gemini-3.8-flash", {"error": {"code": 503, "status": "UNAVAILABLE"}}), G.OVERLOADED, 503),
    (ModelHTTPError(529, "claude-sonnet-5", "overloaded"), G.OVERLOADED, 529),
    (ModelHTTPError(500, "m"), G.OVERLOADED, 500),
    (ModelHTTPError(502, "m"), G.OVERLOADED, 502),
    (ModelHTTPError(504, "m"), G.OVERLOADED, 504),
    (httpx.ConnectError("refused"), G.OVERLOADED, None),
    (httpx.RemoteProtocolError("Server disconnected without sending a response."), G.OVERLOADED, None),
    (httpx.ReadTimeout("slow"), G.TIMEOUT, None),
    (TimeoutError(), G.TIMEOUT, None),
    (ModelHTTPError(404, "gemini-3.8-flash-high"), G.BROKEN, 404),
    (ModelHTTPError(403, "m"), G.BROKEN, 403),
    (ModelHTTPError(401, "m"), G.BROKEN, 401),
    (ModelHTTPError(400, "m", "bad thinking config"), G.REJECTED, 400),
    (ModelHTTPError(422, "m"), G.REJECTED, 422),
    (ValueError("odd"), G.OTHER, None),
])
def test_classify(exc, kind, status):
    f = G.classify(exc)
    assert (f.kind, f.status) == (kind, status)


def test_a_429_reads_retry_info_and_the_daily_quota():
    f = G.classify(gemini_429())
    assert f.kind == G.RATE_LIMITED and f.retry_after == 37.0
    assert G.classify(gemini_429(delay="1.5s")).retry_after == 1.5
    assert G.classify(gemini_429(delay=None)).retry_after is None
    assert G.classify(gemini_429("GenerateRequestsPerDayPerProjectPerModel-FreeTier")).kind == G.DAILY_QUOTA


def test_a_429_without_retry_info_reads_the_retry_after_header():
    e = ModelHTTPError(429, "claude-sonnet-5", None, headers={"Retry-After": "12"})
    assert G.classify(e).retry_after == 12.0


@pytest.mark.parametrize("body", [None, "plain text", b"\xff\xfe", '{"error": {"details": "not a list"}}', ["a", "list"],
                                  {"error": "a string"}, {"error": {"details": [1, "x", {"violations": "no"}]}}])
def test_odd_429_bodies_are_rate_limited_without_a_delay(body):
    f = G.classify(ModelHTTPError(429, "m", body))
    assert f.kind == G.RATE_LIMITED and f.retry_after is None
    assert G.classify(ModelHTTPError(503, "m", body)).kind == G.OVERLOADED


def test_describe_and_event_error_read_as_the_dashboard_expects():
    f = G.classify(ModelHTTPError(503, "gemini-3.8-flash"))
    assert G.describe(f) == "overloaded (503)"
    assert G.event_error("google:gemini-3.8-flash", f) == "model gemini-3.8-flash answered 503"
    t = G.classify(httpx.ReadTimeout("slow"))
    assert G.describe(t) == "timed out" and G.event_error("google:gemini-3.1-pro-preview", t) == \
        "model gemini-3.1-pro-preview timed out (ReadTimeout)"
    d = G.classify(gemini_429("GenerateRequestsPerDayPerProjectPerModel"))
    assert G.event_error("google:gemini-3.8-flash", d) == "model gemini-3.8-flash answered 429 (daily quota)"


@pytest.mark.parametrize("model,fam", [
    ("google:gemini-3.8-flash", "gemini-flash"), ("google:gemini-3.7-flash", "gemini-flash"),
    ("google:gemini-flash-latest", "gemini-flash"), ("google:gemini-3.5-flash-lite", "gemini-flash-lite"),
    ("google:gemini-3.1-pro-preview", "gemini-pro"), ("google:gemini-pro-latest", "gemini-pro"),
    ("google-vertex:gemini-3.1-pro-preview", "gemini-pro"), ("google:gemini-4-argon", "gemini"),
    ("anthropic:claude-sonnet-5", "claude"), ("claude-code:opus", "claude"), ("openai:gpt-5", "openai"),
])
def test_families(model, fam):
    assert G.family(model) == fam
    assert G.family(model, {model: "mine"}) == "mine"


def test_pacific_midnight_across_daylight_saving():
    # 2026-11-01 is 25 hours long in Los Angeles; 2027-03-14 is 23 hours long
    for day, hours in (("2026-11-01", 25), ("2027-03-14", 23)):
        start = datetime.fromisoformat(day + "T00:00:00").replace(tzinfo=G.PACIFIC).timestamp()
        end = G.next_pacific_midnight(start + 3600)
        assert round((end - start) / 3600) == hours
        assert G.pacific_day(start + 3600) == day and G.pacific_day(end) != day


def test_retry_delay_follows_ruling_7():
    cfg, lo = G.GuardConfig(), (lambda a, b: a)
    over, rate = G.Failure(G.OVERLOADED, 503), G.Failure(G.RATE_LIMITED, 429, 2.0)
    assert G.retry_delay(over, False, cfg, lo) == 1.0
    assert G.retry_delay(over, True, cfg, lo) is None, "a trial is not retried"
    assert G.retry_delay(rate, False, cfg, lo) == 2.0
    assert G.retry_delay(G.Failure(G.RATE_LIMITED, 429, 37.0), False, cfg, lo) is None
    assert G.retry_delay(G.Failure(G.RATE_LIMITED, 429, None), False, cfg, lo) is None
    for kind in (G.TIMEOUT, G.DAILY_QUOTA, G.BROKEN, G.REJECTED, G.OTHER):
        assert G.retry_delay(G.Failure(kind), False, cfg, lo) is None


def test_breaker_doubles_caps_and_resets():
    clock = Clock()
    h, changes, _ = health(clock=clock)
    m, over = "google:gemini-3.8-flash", G.Failure(G.OVERLOADED, 503)
    for opening, window in ((1, 60), (2, 120), (3, 240), (4, 480), (5, 600), (6, 600)):
        h.failed(m, over)
        assert h.status(m) == "open"
        snap = changes[-1][1]
        assert snap["state"] == "open" and snap["openings"] == opening and snap["until"] == round(clock.t + window, 1)
        assert snap["reason"] == "overloaded (503)" and snap["family"] == "gemini-flash"
        clock.t += window
        assert h.status(m) == "trial"
    h.succeeded(m, 1000)
    assert h.status(m) == "closed" and changes[-1][1]["state"] == "closed"
    h.failed(m, over)
    assert changes[-1][1]["openings"] == 1, "a success resets the doubling"


def test_one_trial_at_a_time_and_a_failed_trial_reopens_with_the_next_window():
    clock = Clock()
    h, changes, _ = health(clock=clock)
    m = "google:gemini-3.8-flash"
    h.failed(m, G.Failure(G.OVERLOADED, 503))
    assert h.begin_trial(m) is False, "not due yet"
    clock.t += 60
    assert h.begin_trial(m) is True and h.status(m) == "half_open"
    assert h.begin_trial(m) is False, "another request skips it while the trial runs"
    h.failed(m, G.Failure(G.OVERLOADED, 503))
    assert h.status(m) == "open" and changes[-1][1]["until"] == round(clock.t + 120, 1)


def test_an_abandoned_trial_is_due_again():
    clock = Clock()
    h, _, _ = health(clock=clock)
    m = "google:gemini-3.8-flash"
    h.failed(m, G.Failure(G.OVERLOADED, 503))
    clock.t += 60
    assert h.begin_trial(m)
    h.abandon_trial(m)
    assert h.status(m) == "trial"


def test_rate_limits_daily_quota_broken_and_rejected():
    clock = Clock()
    h, changes, _ = health(clock=clock)
    h.failed("a:x", G.Failure(G.RATE_LIMITED, 429, 300.0))
    assert changes[-1][1]["until"] == round(clock.t + 300, 1), "the longer of RetryInfo and the window"
    h.failed("a:y", G.Failure(G.RATE_LIMITED, 429, None))
    assert changes[-1][1]["until"] == round(clock.t + 60, 1)
    h.failed("google:gemini-3.8-flash", G.Failure(G.DAILY_QUOTA, 429))
    assert changes[-1][1]["until"] == round(G.next_pacific_midnight(clock.t), 1)
    assert changes[-1][1]["reason"] == "daily quota (429)"
    h.failed("google:gemini-3.8-flash-high", G.Failure(G.BROKEN, 404))
    assert h.status("google:gemini-3.8-flash-high") == "broken" and changes[-1][1]["until"] is None
    clock.t += 10 ** 6
    assert h.status("google:gemini-3.8-flash-high") == "broken", "broken never times out"
    n = len(changes)
    h.failed("a:z", G.Failure(G.REJECTED, 400))
    assert h.status("a:z") == "closed" and len(changes) == n
    h.clear_broken(["google:gemini-3.8-flash-high"])
    assert h.status("google:gemini-3.8-flash-high") == "closed" and changes[-1][1]["state"] == "closed"


def test_a_family_under_caution_and_the_earliest_reopen():
    clock = Clock()
    h, _, _ = health(clock=clock)
    h.failed("google:gemini-3.8-flash", G.Failure(G.OVERLOADED, 503))
    assert h.cautioned("google:gemini-3.7-flash") and not h.cautioned("google:gemini-3.1-pro-preview")
    assert not h.cautioned("google:gemini-3.8-flash"), "the open model itself is skipped, not cautioned"
    h.failed("google:gemini-3.1-pro-preview", G.Failure(G.REJECTED, 400))
    h.failed("anthropic:claude-sonnet-5", G.Failure(G.RATE_LIMITED, 429, None))
    assert not h.cautioned("claude-code:opus"), "only overloads and timeouts caution a family"
    assert h.earliest_reopen(["google:gemini-3.8-flash", "anthropic:claude-sonnet-5", "x:y"]) == clock.t + 60
    assert h.earliest_reopen(["x:y"]) is None
    clock.t += 60
    assert not h.cautioned("google:gemini-3.7-flash"), "caution ends with the window"


def test_pacing_floor_rpm_and_tpm():
    clock = Clock()
    h, _, _ = health(clock=clock, model_limits={"google:gemini-3.1-pro-preview": {"rpm": 30, "tpm": 1_000_000}})
    assert h.reserve("google:gemini-3.8-flash") == 0
    assert h.reserve("google:gemini-3.7-flash") == 0.5, "the provider floor spans models"
    assert h.reserve("anthropic:claude-sonnet-5") == 0, "no floor for other providers"
    clock.t += 10
    assert h.reserve("google:gemini-3.1-pro-preview") == 0
    assert h.reserve("google:gemini-3.1-pro-preview") == 2.0, "60 / 30 rpm"
    h.succeeded("google:gemini-3.1-pro-preview", 40_000)
    clock.t += 100
    h.reserve("google:gemini-3.1-pro-preview")
    assert h.reserve("google:gemini-3.1-pro-preview") == pytest.approx(2.4), "60 x 40,000 / 1,000,000 tpm"


def test_concurrent_reservations_get_distinct_slots():
    h, _, _ = health(clock=Clock())
    waits, start = [], threading.Barrier(8)

    def take():
        start.wait()
        waits.append(h.reserve("google:gemini-3.8-flash"))
    threads = [threading.Thread(target=take) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(waits) == [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5]


def test_daily_counts_persist_roll_over_and_budget(tmp_path):
    clock = Clock(datetime.fromisoformat("2026-10-02T23:59:00").replace(tzinfo=G.PACIFIC).timestamp())
    m = "google:gemini-3.1-pro-preview"
    h, changes, _ = health(tmp_path, clock=clock, model_limits={m: {"daily_requests": 2}})
    assert h.count(m) is None and h.count(m) is None
    over = h.count(m)
    assert over is not None and over.kind == G.DAILY_QUOTA and h.today(m) == 2
    assert h.status(m) == "open" and changes[-1][1]["reason"] == "daily budget"
    assert changes[-1][1]["until"] == round(G.next_pacific_midnight(clock.t), 1)
    again, _, _ = health(tmp_path, clock=clock, model_limits={m: {"daily_requests": 2}})
    assert again.today(m) == 2, "the counts survive a restart"
    clock.t += 120                                   # past midnight Pacific
    assert again.today(m) == 0 and again.count(m) is None
    data = json.loads((tmp_path / "model-usage.json").read_text())
    assert data == {"2026-10-02": {m: 2}, "2026-10-03": {m: 1}}
    clock.t += 9 * 86400
    again.count(m)
    assert list(json.loads((tmp_path / "model-usage.json").read_text())) == ["2026-10-12"], "7 days kept"


def test_an_unreadable_usage_file_starts_at_zero_with_one_note(tmp_path):
    (tmp_path / "model-usage.json").write_text('{"2026-10-02": {"google:gemini-3.8-fla')
    h, _, notes = health(tmp_path)
    assert h.today("google:gemini-3.8-flash") == 0 and len(notes) == 1 and "unreadable" in notes[0]
    assert h.count("google:gemini-3.8-flash") is None, "a new file is written"
    json.loads((tmp_path / "model-usage.json").read_text())


def test_an_unwritable_usage_file_keeps_counting_with_one_note(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("")
    h, _, notes = health()
    h.cfg.usage_file = blocker / "model-usage.json"       # its parent is a file
    for _ in range(3):
        assert h.count("google:gemini-3.8-flash") is None
    assert h.today("google:gemini-3.8-flash") == 3 and len(notes) == 1 and "not written" in notes[0]


def test_snapshot_lists_states_counts_and_caution():
    clock = Clock()
    h, _, _ = health(clock=clock)
    h.count("google:gemini-3.7-flash")
    h.failed("google:gemini-3.8-flash", G.Failure(G.OVERLOADED, 503))
    snap = h.snapshot()
    assert snap["day"] == G.pacific_day(clock.t)
    assert snap["models"]["google:gemini-3.8-flash"]["state"] == "open"
    assert snap["models"]["google:gemini-3.7-flash"] == {"state": "closed", "until": None, "reason": "", "openings": 0,
                                                         "family": "gemini-flash", "caution": True, "today": 1}


def test_settings_and_environment(monkeypatch, tmp_path):
    s = Settings()
    assert s.model_guard is True and s.overload_retry_s == (1.0, 2.0) and s.min_call_interval_s == {"google": 0.5}
    assert (s.rate_retry_max_s, s.breaker_open_s, s.breaker_max_s, s.pool_max_wait_s) == (10.0, 60.0, 600.0, 60.0)
    monkeypatch.setenv("PILOT_MODEL_GUARD", "0")
    monkeypatch.setenv("PILOT_MIN_CALL_INTERVAL", '{"google": 1.5, "anthropic": 0.2}')
    monkeypatch.setenv("PILOT_MODEL_LIMITS", '{"google:gemini-3.1-pro-preview": {"rpm": 25, "daily_requests": 1000}}')
    monkeypatch.setenv("PILOT_MODEL_FAMILIES", '{"google:gemini-4-argon": "gemini-pro"}')
    e = Settings.from_env()
    assert e.model_guard is False and e.min_call_interval_s == {"google": 1.5, "anthropic": 0.2}
    assert e.model_limits["google:gemini-3.1-pro-preview"]["daily_requests"] == 1000
    assert e.model_families == {"google:gemini-4-argon": "gemini-pro"}
    monkeypatch.setenv("PILOT_MODEL_LIMITS", "[1, 2]")
    with pytest.raises(ValueError, match="PILOT_MODEL_LIMITS"):
        Settings.from_env()
    cfg = G.GuardConfig.from_settings(Settings(runs_dir=tmp_path))
    assert cfg.usage_file == tmp_path / "model-usage.json" and cfg.breaker_max_s == 600.0
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `.venv/bin/pytest tests/test_modelguard_health.py -q`
Expected: collection error `ModuleNotFoundError: No module named 'pilot.modelguard'`.

- [ ] **Step 3: Write `src/pilot/modelguard.py` (health part)**

```python
"""Model guard (docs/design/2026-10-02-model-guard-design.md): every model request is paced, a failure is
classified and retried at most once, and each model has a circuit breaker; a role's models form a pool
that moves a failed request to the next model with the run's history, so tools that already ran do not
run again. Nothing game-specific lives here."""

from __future__ import annotations

import json
import math
import os
import random
import re
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import anyio
import httpx

PACIFIC = ZoneInfo("America/Los_Angeles")        # Gemini daily quotas reset at midnight Pacific

OVERLOADED, TIMEOUT, RATE_LIMITED, DAILY_QUOTA = "overloaded", "timeout", "rate_limited", "daily_quota"
BROKEN, REJECTED, OTHER = "broken", "rejected", "other"
CAUTION = frozenset({OVERLOADED, TIMEOUT})       # kinds that put the model's family behind the others (ruling 9)
LABEL = {OVERLOADED: "overloaded", TIMEOUT: "timed out", RATE_LIMITED: "rate limited", DAILY_QUOTA: "daily quota",
         BROKEN: "unusable", REJECTED: "request rejected", OTHER: "failed"}
USAGE_DAYS = 7                                   # days of request counts kept in the usage file (ruling 14)

_sleep = anyio.sleep                             # the guard's waits; tests replace both (tests/conftest.py)
_uniform = random.uniform


@dataclass(frozen=True)
class Failure:
    """One classified model failure (ruling 6)."""
    kind: str
    status: int | None = None
    retry_after: float | None = None             # seconds, from RetryInfo or Retry-After (429 only)
    cause: str = ""                              # one line for logs


def describe(f: Failure) -> str:
    """The failure in a few words, as the dashboard shows it: "overloaded (503)", "timed out"."""
    return LABEL.get(f.kind, f.kind) + (f" ({f.status})" if f.status else "")


def event_error(model: str, f: Failure) -> str:
    """The `error` text of model_retry and model_fallback events, in the form the dashboard already reads
    ("model gemini-3.8-flash answered 503"; ruling 21)."""
    short = model.split(":", 1)[-1]
    if f.status:
        return f"model {short} answered {f.status}" + (" (daily quota)" if f.kind == DAILY_QUOTA else "")
    return f"model {short} {f.cause or LABEL.get(f.kind, f.kind)}"


def _body(body) -> dict:
    if isinstance(body, dict):
        return body
    if isinstance(body, (str, bytes)):
        try:
            d = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            return {}
        return d if isinstance(d, dict) else {}
    return {}


def _details(body) -> list[dict]:
    d = _body(body)
    err = d.get("error", d)
    det = err.get("details") if isinstance(err, dict) else None
    return [x for x in det if isinstance(x, dict)] if isinstance(det, list) else []


def _seconds(text) -> float | None:
    """A protobuf Duration ("37s", "1.5s") or a Retry-After header ("12") in seconds."""
    m = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)s?\s*", str(text or ""))
    return float(m.group(1)) if m else None


def classify(e: BaseException) -> Failure:
    """Ruling 6: what kind of failure an exception from a model request is."""
    from pydantic_ai.exceptions import ModelHTTPError
    if isinstance(e, ModelHTTPError):
        st, cause = e.status_code, f"{e.model_name} answered {e.status_code}"
        if st == 429:
            details = _details(e.body)
            quotas = [str(v.get("quotaId", "")) for x in details
                      for v in (x.get("violations") if isinstance(x.get("violations"), list) else [])
                      if isinstance(v, dict)]
            if any("PerDay" in q for q in quotas):
                return Failure(DAILY_QUOTA, st, None, cause + " (daily quota)")
            after = next((_seconds(x.get("retryDelay")) for x in details if "RetryInfo" in str(x.get("@type", ""))), None)
            if after is None and getattr(e, "headers", None):
                after = _seconds(e.headers.get("retry-after"))
            return Failure(RATE_LIMITED, st, after, cause)
        if st in (500, 502, 503, 504, 529):
            return Failure(OVERLOADED, st, None, cause)
        if st in (401, 403, 404):
            return Failure(BROKEN, st, None, cause)
        if st in (400, 422):
            return Failure(REJECTED, st, None, cause)
        return Failure(OTHER, st, None, cause)
    if isinstance(e, (httpx.TimeoutException, TimeoutError)):
        return Failure(TIMEOUT, None, None, f"timed out ({type(e).__name__})")
    if isinstance(e, (httpx.ConnectError, httpx.RemoteProtocolError, ConnectionError)):
        return Failure(OVERLOADED, None, None, f"connection failed ({type(e).__name__})")
    return Failure(OTHER, None, None, f"{type(e).__name__}: {e}"[:200])


def provider(model: str) -> str:
    return model.split(":", 1)[0] if ":" in model else ""


def family(model: str, overrides: Mapping[str, str] | None = None) -> str:
    """Ruling 3: models that share capacity fail together, so a failover goes to another family."""
    if overrides and model in overrides:
        return overrides[model]
    prov, name = provider(model), model.split(":", 1)[-1].lower()
    if prov in ("anthropic", "claude-code") or name.startswith("claude"):
        return "claude"
    if prov.startswith("google") or name.startswith("gemini"):
        for key, fam in (("flash-lite", "gemini-flash-lite"), ("flash", "gemini-flash"), ("pro", "gemini-pro")):
            if key in name:
                return fam
        return "gemini"
    return prov or name


def pacific_day(now: float) -> str:
    return datetime.fromtimestamp(now, PACIFIC).date().isoformat()


def next_pacific_midnight(now: float) -> float:
    """When Gemini's daily quotas reset after `now` (ruling 7)."""
    d = datetime.fromtimestamp(now, PACIFIC).date() + timedelta(days=1)
    return datetime(d.year, d.month, d.day, tzinfo=PACIFIC).timestamp()


@dataclass
class GuardConfig:
    """Ruling 15's settings, as the guard uses them."""
    overload_retry_s: tuple[float, float] = (1.0, 2.0)
    rate_retry_max_s: float = 10.0
    breaker_open_s: float = 60.0
    breaker_max_s: float = 600.0
    pool_max_wait_s: float = 60.0
    min_call_interval_s: dict = field(default_factory=lambda: {"google": 0.5})
    model_limits: dict = field(default_factory=dict)
    model_families: dict = field(default_factory=dict)
    usage_file: Path | None = None

    @classmethod
    def from_settings(cls, s) -> GuardConfig:
        return cls(overload_retry_s=tuple(s.overload_retry_s), rate_retry_max_s=s.rate_retry_max_s,
                   breaker_open_s=s.breaker_open_s, breaker_max_s=s.breaker_max_s, pool_max_wait_s=s.pool_max_wait_s,
                   min_call_interval_s=dict(s.min_call_interval_s), model_limits=dict(s.model_limits),
                   model_families=dict(s.model_families), usage_file=Path(s.runs_dir) / "model-usage.json")


def retry_delay(f: Failure, trial: bool, cfg: GuardConfig, uniform=random.uniform) -> float | None:
    """Ruling 7: seconds before the one retry on the same model, or None for no retry."""
    if f.kind == OVERLOADED and not trial:
        return uniform(*cfg.overload_retry_s)
    if f.kind == RATE_LIMITED and f.retry_after is not None and f.retry_after <= cfg.rate_retry_max_s:
        return f.retry_after + uniform(0.0, 1.0)
    return None


@dataclass
class Breaker:
    state: str = "closed"            # closed | open | half_open | broken (ruling 2)
    until: float = 0.0
    openings: int = 0                # consecutive openings: the window doubles with each (ruling 8)
    reason: str = ""
    kind: str = ""


class ModelHealth:
    """Ruling 2: the guard's state for every model, one per pilot process, shared by every role and thread.
    `on_change(model, snap)` and `on_note(text)` are called outside the lock; `on_note` must not call back."""

    def __init__(self, config: GuardConfig, clock: Callable[[], float] = time.time,
                 on_change: Callable[[str, dict], None] | None = None, on_note: Callable[[str], None] | None = None):
        self.cfg, self.clock, self.on_change, self.on_note = config, clock, on_change, on_note
        self._lock = threading.Lock()
        self._b: dict[str, Breaker] = {}
        self._last_start: dict[str, float] = {}      # pacing: latest reserved start per model and per "provider:"
        self._tokens: dict[str, int] = {}            # input tokens of each model's last answered request
        self._days: dict[str, dict[str, int]] = {}
        self._day = pacific_day(self.clock())
        self._save_failed = False
        self._load()

    def family(self, model: str) -> str:
        return family(model, self.cfg.model_families)

    # ---- breakers (rulings 7-9) ------------------------------------------------------------------

    def status(self, model: str) -> str:
        """closed, open, trial (its window ended: the next request is its one trial), half_open (the
        trial is running) or broken."""
        with self._lock:
            return self._status(model, self.clock())

    def _status(self, model: str, now: float) -> str:
        b = self._b.get(model)
        if b is None or b.state == "closed":
            return "closed"
        if b.state == "open" and now >= b.until:
            return "trial"
        return b.state

    def begin_trial(self, model: str) -> bool:
        """Take the model's single trial (ruling 8); False when none is due or another is running."""
        with self._lock:
            now = self.clock()
            if self._status(model, now) != "trial":
                return False
            self._b[model].state = "half_open"
            snap = self._snap(model, now)
        self._notify(model, snap)
        return True

    def abandon_trial(self, model: str) -> None:
        """A trial that ended without an answer or a failure (cancelled): due again."""
        with self._lock:
            b = self._b.get(model)
            if b is not None and b.state == "half_open":
                b.state, b.until = "open", self.clock()

    def succeeded(self, model: str, input_tokens: int | None = None) -> None:
        with self._lock:
            if input_tokens:
                self._tokens[model] = int(input_tokens)
            b = self._b.pop(model, None)
            snap = self._snap(model, self.clock()) if b is not None else None
        if snap:
            self._notify(model, snap)

    def failed(self, model: str, f: Failure, reason: str | None = None) -> None:
        """Rulings 7-8: open with the doubling window, open until midnight Pacific, or mark broken; a
        rejected request changes nothing."""
        if f.kind == REJECTED:
            return
        with self._lock:
            now = self.clock()
            b = self._b.setdefault(model, Breaker())
            if f.kind == BROKEN:
                b.state, b.until = "broken", math.inf
            elif f.kind == DAILY_QUOTA:
                b.state, b.until = "open", next_pacific_midnight(now)
            else:
                b.openings += 1
                window = min(self.cfg.breaker_open_s * 2 ** (b.openings - 1), self.cfg.breaker_max_s)
                if f.kind == RATE_LIMITED:
                    window = max(window, f.retry_after or 0.0)
                b.state, b.until = "open", now + window
            b.reason, b.kind = reason or describe(f), f.kind
            snap = self._snap(model, now)
        self._notify(model, snap)

    def cautioned(self, model: str) -> bool:
        """Another model of its family is open after an overload or a timeout (ruling 9)."""
        with self._lock:
            return self._cautioned(model, self.clock())

    def _cautioned(self, model: str, now: float) -> bool:
        fam = self.family(model)
        return any(m != model and b.state == "open" and b.until > now and b.kind in CAUTION and self.family(m) == fam
                   for m, b in self._b.items())

    def earliest_reopen(self, models: Iterable[str]) -> float | None:
        """When the first of these open models is due for its trial (ruling 11)."""
        with self._lock:
            ends = [self._b[m].until for m in models if m in self._b and self._b[m].state == "open"]
        return min(ends) if ends else None

    def clear_broken(self, models: Iterable[str]) -> None:
        changed = []
        with self._lock:
            for m in set(models):
                if m in self._b and self._b[m].state == "broken":
                    del self._b[m]
                    changed.append((m, self._snap(m, self.clock())))
        for m, snap in changed:
            self._notify(m, snap)

    # ---- pacing and counts (rulings 12-14) -----------------------------------------------------

    def reserve(self, model: str) -> float:
        """Take the next start slot for a request to `model`; the seconds to wait before sending it."""
        with self._lock:
            now = self.clock()
            prov = provider(model) + ":"
            floor = float(self.cfg.min_call_interval_s.get(provider(model), 0.0))
            start = max(now, self._last_start.get(prov, -math.inf) + floor,
                        self._last_start.get(model, -math.inf) + self._gap(model))
            self._last_start[prov] = self._last_start[model] = start
            return max(0.0, start - now)

    def _gap(self, model: str) -> float:
        lim = self.cfg.model_limits.get(model) or {}
        gap = 60.0 / float(lim["rpm"]) if lim.get("rpm") else 0.0
        if lim.get("tpm") and self._tokens.get(model):
            gap = max(gap, 60.0 * self._tokens[model] / float(lim["tpm"]))
        return gap

    def count(self, model: str) -> Failure | None:
        """Count a request about to be sent. When the model's daily budget is already spent nothing is
        counted, its breaker opens until midnight Pacific and the failure is returned (ruling 13)."""
        budget = (self.cfg.model_limits.get(model) or {}).get("daily_requests")
        with self._lock:
            self._roll(self.clock())
            today = self._days.setdefault(self._day, {})
            if not budget or today.get(model, 0) < int(budget):
                today[model] = today.get(model, 0) + 1
                notes = self._save()
                over = None
            else:
                notes = []
                over = Failure(DAILY_QUOTA, None, None, f"daily budget of {int(budget)} requests reached")
        for n in notes:
            self._note(n)
        if over is not None:
            self.failed(model, over, reason="daily budget")
        return over

    def today(self, model: str) -> int:
        with self._lock:
            self._roll(self.clock())
            return self._days.get(self._day, {}).get(model, 0)

    def _roll(self, now: float) -> None:
        self._day = pacific_day(now)

    def _load(self) -> None:
        p = self.cfg.usage_file
        if p is None or not p.exists():
            return
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            self._days = {str(d): {str(m): int(n) for m, n in c.items()} for d, c in data.items()}
        except (OSError, ValueError, TypeError, AttributeError) as e:
            self._days = {}
            self._note(f"model usage file {p.name} unreadable ({type(e).__name__}); today's counts start at 0")

    def _save(self) -> list[str]:
        """Write the counts (under the lock); returns a note to give after releasing it."""
        p = self.cfg.usage_file
        if p is None:
            return []
        oldest = (datetime.fromisoformat(self._day) - timedelta(days=USAGE_DAYS - 1)).date().isoformat()
        self._days = {d: c for d, c in self._days.items() if d >= oldest}
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_name(p.name + ".tmp")
            tmp.write_text(json.dumps(self._days, sort_keys=True), encoding="utf-8")
            os.replace(tmp, p)
        except OSError as e:
            if not self._save_failed:
                self._save_failed = True
                return [f"model usage file {p.name} not written ({type(e).__name__}); counts kept in memory"]
        return []

    # ---- what the dashboard reads (ruling 23) --------------------------------------------------

    def snapshot(self) -> dict:
        """Every model the guard has seen: its breaker, its family's caution and today's requests."""
        with self._lock:
            now = self.clock()
            self._roll(now)
            today = self._days.get(self._day, {})
            names = sorted(set(self._b) | set(today))
            return {"day": self._day, "models": {m: {**self._snap(m, now), "today": today.get(m, 0)} for m in names}}

    def _snap(self, model: str, now: float) -> dict:
        b = self._b.get(model) or Breaker()
        state = self._status(model, now)
        return {"state": state, "until": round(b.until, 1) if state == "open" else None, "reason": b.reason,
                "openings": b.openings, "family": self.family(model), "caution": self._cautioned(model, now)}

    def _notify(self, model: str, snap: dict) -> None:
        if self.on_change:
            self.on_change(model, snap)

    def _note(self, text: str) -> None:
        if self.on_note:
            self.on_note(text)
```

Notes for the implementer:
- `test_daily_counts_persist_roll_over_and_budget` expects `{"2026-10-02": {m: 2}, "2026-10-03": {m: 1}}`. The budget-refused request is not counted, so the file keeps 2 for that day.
- In `test_breaker_doubles_caps_and_resets`, the doubling is checked by moving the clock to each window's end and failing again. Every failure increments `openings` until a success resets it.

- [ ] **Step 4: Add the settings to `src/pilot/config.py`**

In the `Settings` dataclass, directly after `retry_delays: tuple[float, ...] = (5, 15, 45)` (line 57), add:

```python
    # the model guard (docs/design/2026-10-02-model-guard-design.md, ruling 15): pacing, one short retry,
    # a breaker per model and failover inside a run; PILOT_MODEL_GUARD=0 runs the whole-run retries above
    model_guard: bool = True
    overload_retry_s: tuple[float, float] = (1.0, 2.0)
    rate_retry_max_s: float = 10.0
    breaker_open_s: float = 60.0
    breaker_max_s: float = 600.0
    pool_max_wait_s: float = 60.0
    min_call_interval_s: dict = field(default_factory=lambda: {"google": 0.5})
    model_limits: dict = field(default_factory=dict)          # model -> {rpm, tpm, daily_requests}
    model_families: dict = field(default_factory=dict)        # model -> family, over the name rule
```

Also correct the comment on the `retry_delays` line, which currently describes the request cap: `# waits between whole-run retries on the first model (PILOT_MODEL_GUARD=0 only)`.

Above `class Settings`, add:

```python
def _json_map(env, name: str, default: dict) -> dict:
    """A JSON object from the environment (the model guard's maps); anything else is an error naming it."""
    raw = env.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = json.loads(raw)
    except ValueError as e:
        raise ValueError(f"{name} is not valid JSON: {e}") from None
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a JSON object, got {type(value).__name__}")
    return value
```

(add `import json` to the imports if it's missing.) In `from_env`, before `if "PILOT_RUNS_DIR" in env:`, add:

```python
        s.model_guard = env.get("PILOT_MODEL_GUARD", "1").strip().lower() not in ("0", "false", "no", "off")
        s.min_call_interval_s = _json_map(env, "PILOT_MIN_CALL_INTERVAL", s.min_call_interval_s)
        s.model_limits = _json_map(env, "PILOT_MODEL_LIMITS", s.model_limits)
        s.model_families = _json_map(env, "PILOT_MODEL_FAMILIES", s.model_families)
```

- [ ] **Step 5: Make the guard's waits instant in tests**

Append to `tests/conftest.py`:

```python
@pytest.fixture(autouse=True)
def guard_waits(monkeypatch):
    """The model guard's retry and pacing waits take no real time in tests; each wait is recorded, and
    retry jitter takes its lower bound."""
    from pilot import modelguard
    waits: list[float] = []

    async def sleep(seconds):
        waits.append(seconds)
    monkeypatch.setattr(modelguard, "_sleep", sleep)
    monkeypatch.setattr(modelguard, "_uniform", lambda lo, hi: lo)
    return waits
```

- [ ] **Step 6: Run the tests**

Run: `.venv/bin/pytest tests/test_modelguard_health.py -q`
Expected: all pass. Then `.venv/bin/pytest -q -x -m "not ui"`, which must also pass (the new settings change nothing else yet).

- [ ] **Step 7: Commit**

```bash
git add src/pilot/modelguard.py src/pilot/config.py tests/conftest.py tests/test_modelguard_health.py
scripts/ci-commit.sh "feat(pilot): model guard health: failure kinds, breakers, pacing and daily counts" "Rulings 2-3, 6-9 and 12-15 of the model guard design: a per-process ModelHealth with doubling breakers, family caution, provider and rpm/tpm pacing, and request counts per Pacific day in runs/model-usage.json; the settings and their environment variables. Verified by tests/test_modelguard_health.py."
```

---

### Task 2: Guarded models and the pool

**Files:**
- Modify: `src/pilot/modelguard.py` (append)
- Test: `tests/test_modelguard_pool.py`

**Interfaces:**
- Consumes (Task 1): everything in Task 1's Produces list.
- Produces (used by Tasks 3-4):
  - `ModelUnavailable(model, failure)` with attributes `.model` and `.failure`;
  - `PoolExhausted(role, tried, skipped)` with attributes `.role`, `.tried` and `.skipped`, and `.causes() -> [{"model", "error"}]`;
  - `Hooks(on_try, on_retry, on_fallback, on_pace)`, each called with keyword arguments:
    - `on_try(name, attempt, of, after, skipped)`, where `after` is `[(name, Failure)]` and `skipped` is `[name]`;
    - `on_retry(name, failure, delay, attempt, request)`;
    - `on_fallback(name, failure, next, request)`;
    - `on_pace(name, waited)`;
  - `event_hooks(emit, role, family, extra=None) -> Hooks`;
  - `emit_breaker(emit, model, snap)`;
  - `build_model(name) -> Model`;
  - `GuardedModel(model, name, health, settings=None)`, where `model` is a Model or a "provider:name" string, with attributes `.name`, `.hooks` and `.request_no`, and the method `.ensure_built()`;
  - `PoolModel(role, models: list[GuardedModel], health)` with `.begin_run(start=0, hooks=None)`, `.ordered(exclude=frozenset()) -> (list[int], list[str])` (worked out again after every failure inside a request), and the attributes `.requests`, `.last_answered: int | None`, `.guarded` and `.hooks`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_modelguard_pool.py`:

```python
"""Guarded models and pools (docs/design/2026-10-02-model-guard-design.md, rulings 4-5, 7, 10-11, 16): a
failed request moves to the next model inside the same run, so a tool runs once; each failure kind gets
its retry rule; the order skips open and broken models and puts a failed family last."""

from __future__ import annotations

import asyncio

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
    from anthropic import AsyncAnthropic
    from pydantic_ai.models.anthropic import AnthropicModel
    from pydantic_ai.providers.anthropic import AnthropicProvider
    sent = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request.read())
        return httpx.Response(200, json={"id": "msg_1", "type": "message", "role": "assistant", "model": "claude-sonnet-5",
                                         "content": [{"type": "text", "text": "claude answered"}],
                                         "stop_reason": "end_turn", "stop_sequence": None,
                                         "usage": {"input_tokens": 10, "output_tokens": 2}})
    client = AsyncAnthropic(api_key="test", max_retries=0, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
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
                                         "role": "chat", "model": "google:gemini-3.8-flash", "kind": "overloaded",
                                         "family": "gemini-flash", "request": 2})
    assert events[1] == ("model_fallback", {"role": "chat", "model": "google:gemini-3.8-flash",
                                            "error": "model gemini-3.8-flash answered 503", "fallback": "claude-code:opus",
                                            "kind": "overloaded", "family": "gemini-flash", "request": 2})
    assert events[2] == ("model_pace", {"model": "google:gemini-3.8-flash", "waited_s": 1.5, "role": "chat"})
    out = []
    G.emit_breaker(lambda kind, **d: out.append((kind, d)), "google:gemini-3.8-flash",
                   {"state": "open", "until": 5.0, "reason": "overloaded (503)", "openings": 1, "family": "gemini-flash",
                    "caution": False})
    assert out == [("model_breaker", {"model": "google:gemini-3.8-flash", "family": "gemini-flash", "state": "open",
                                      "until": 5.0, "reason": "overloaded (503)", "openings": 1})]
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `.venv/bin/pytest tests/test_modelguard_pool.py -q`
Expected: FAIL with `AttributeError: module 'pilot.modelguard' has no attribute 'PoolModel'` (or `'GuardedModel'`).

- [ ] **Step 3: Append the models to `src/pilot/modelguard.py`**

Add these imports at the top of the module, alongside the existing ones:

```python
from contextlib import asynccontextmanager

from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.models import Model
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.wrapper import WrapperModel
from pydantic_ai.settings import merge_model_settings
```

Append:

```python
# ---- models (rulings 4-5, 10-11, 16) ------------------------------------------------------------

class ModelUnavailable(Exception):
    """A model could not answer this request (ruling 4); the pool moves the request on."""

    def __init__(self, model: str, failure: Failure):
        super().__init__(f"{model}: {failure.cause or describe(failure)}")
        self.model, self.failure = model, failure


class PoolExhausted(Exception):
    """No model of a pool could answer a request (ruling 11)."""

    def __init__(self, role: str, tried: list[ModelUnavailable], skipped: list[str]):
        self.role, self.tried, self.skipped = role, list(tried), list(skipped)
        super().__init__(f"no model could answer ({role}): " + "; ".join(
            [f"{u.model} {describe(u.failure)}" for u in self.tried] + [f"{m} skipped" for m in self.skipped]))

    def causes(self) -> list[dict]:
        return ([{"model": u.model, "error": describe(u.failure)} for u in self.tried]
                + [{"model": m, "error": "skipped"} for m in self.skipped])


def _noop(**_kw) -> None:
    return None


@dataclass
class Hooks:
    """What a pool reports to its owner, which writes the events (rulings 17, 21-22). All take keyword
    arguments: on_try(name, attempt, of, after=[(name, Failure)], skipped=[name]); on_retry(name, failure,
    delay, attempt, request); on_fallback(name, failure, next, request); on_pace(name, waited)."""
    on_try: Callable[..., None] = _noop
    on_retry: Callable[..., None] = _noop
    on_fallback: Callable[..., None] = _noop
    on_pace: Callable[..., None] = _noop


def event_hooks(emit, role: str, family: Callable[[str], str], extra: Hooks | None = None) -> Hooks:
    """Hooks that write model_retry, model_fallback and model_pace through `emit(kind, **data)` (rulings
    21-22), after calling `extra`'s."""
    x = extra or Hooks()

    def on_retry(name, failure, delay, attempt, request):
        x.on_retry(name=name, failure=failure, delay=delay, attempt=attempt, request=request)
        emit("model_retry", error=event_error(name, failure), delay=delay, attempt=attempt, role=role, model=name,
             kind=failure.kind, family=family(name), request=request)

    def on_fallback(name, failure, next, request):  # noqa: A002 - the hook's keyword
        x.on_fallback(name=name, failure=failure, next=next, request=request)
        emit("model_fallback", role=role, model=name, error=event_error(name, failure), fallback=next,
             kind=failure.kind, family=family(name), request=request)

    def on_pace(name, waited):
        x.on_pace(name=name, waited=waited)
        emit("model_pace", model=name, waited_s=waited, role=role)
    return Hooks(on_try=x.on_try, on_retry=on_retry, on_fallback=on_fallback, on_pace=on_pace)


def emit_breaker(emit, model: str, snap: dict) -> None:
    """The model_breaker event for one breaker change (ruling 22)."""
    emit("model_breaker", model=model, family=snap["family"], state=snap["state"], until=snap["until"],
         reason=snap["reason"], openings=snap["openings"])


def build_model(name: str) -> Model:
    """A pool entry's provider model with the SDK's own retries off (ruling 16): google-genai never
    retries without retry_options, which pydantic-ai leaves unset; Anthropic's client gets max_retries=0."""
    from pydantic_ai.models import infer_model

    from .claude_code import resolve_model
    m = resolve_model(name)
    if not isinstance(m, str):
        return m
    prov, _, model_name = name.partition(":")
    if prov == "anthropic":
        from anthropic import AsyncAnthropic
        from pydantic_ai.models.anthropic import AnthropicModel
        from pydantic_ai.providers.anthropic import AnthropicProvider
        return AnthropicModel(model_name, provider=AnthropicProvider(
            anthropic_client=AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"), max_retries=0)))
    return infer_model(name)


class GuardedModel(WrapperModel):
    """Ruling 4: one pool entry. It is built on first use, so a model that cannot be built (a missing key,
    an unknown provider) is marked broken instead of breaking its role."""

    def __init__(self, model: Model | str, name: str, health: ModelHealth, settings=None):
        Model.__init__(self)                     # not WrapperModel's, which builds the model at once
        self._source = model
        self._built: Model | None = model if isinstance(model, Model) else None
        self._entered = False
        self.name, self.health, self.entry_settings = name, health, settings
        self.hooks = Hooks()
        self.request_no = 0                      # set by the pool: the request's number in its run

    @property
    def wrapped(self) -> Model:  # type: ignore[override]
        if self._built is None:
            self._built = build_model(self._source)
        return self._built

    def __repr__(self) -> str:
        return f"GuardedModel({self.name!r})"

    @property
    def model_name(self) -> str:
        return self._built.model_name if self._built is not None else self.name.split(":", 1)[-1]

    @property
    def system(self) -> str:
        return self._built.system if self._built is not None else provider(self.name)

    @property
    def model_id(self) -> str:
        return self._built.model_id if self._built is not None else self.name

    def ensure_built(self) -> None:
        try:
            self.wrapped
        except Exception as e:  # noqa: BLE001 - unusable until the models change (ruling 7, broken)
            f = Failure(BROKEN, None, None, f"cannot be built: {type(e).__name__}: {e}"[:200])
            self.health.failed(self.name, f)
            raise ModelUnavailable(self.name, f) from e

    async def __aenter__(self):
        try:
            self.ensure_built()
            await self.wrapped.__aenter__()
            self._entered = True
        except ModelUnavailable:
            pass                                 # marked broken; the pool skips it
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._entered:
            self._entered = False
            return await self.wrapped.__aexit__(exc_type, exc_val, exc_tb)
        return None

    async def request(self, messages, model_settings, model_request_parameters):
        self.ensure_built()
        settings = merge_model_settings(model_settings, self.entry_settings)
        trial = self.health.begin_trial(self.name)
        retried = False
        try:
            while True:
                wait = self.health.reserve(self.name)
                if wait >= 1.0:
                    self.hooks.on_pace(name=self.name, waited=round(wait, 1))
                if wait > 0:
                    await _sleep(wait)
                over = self.health.count(self.name)
                if over is not None:
                    raise ModelUnavailable(self.name, over)
                try:
                    response = await self.wrapped.request(messages, settings, model_request_parameters)
                except UsageLimitExceeded:
                    raise
                except Exception as e:  # noqa: BLE001 - every model failure is classified (ruling 6)
                    f = classify(e)
                    delay = None if retried else retry_delay(f, trial, self.health.cfg, _uniform)
                    if delay is None:
                        self.health.failed(self.name, f)
                        raise ModelUnavailable(self.name, f) from e
                    retried = True
                    self.hooks.on_retry(name=self.name, failure=f, delay=round(delay, 1), attempt=1,
                                        request=self.request_no)
                    await _sleep(delay)
                    continue
                self.health.succeeded(self.name, response.usage.input_tokens)
                return response
        except BaseException as e:
            if trial and not isinstance(e, (Exception,)):
                self.health.abandon_trial(self.name)     # cancelled: the trial is due again
            raise

    @asynccontextmanager
    async def request_stream(self, *args, **kwargs):
        raise NotImplementedError("the pilot does not stream model responses")
        yield  # pragma: no cover


class PoolModel(FallbackModel):
    """Ruling 5: a role's models. Each request goes to the first model that can take it, in ruling 10's
    order; a ModelUnavailable moves the same messages (the run's history so far) to the next model, so
    the run continues and tools that already ran are not run again."""

    def __init__(self, role: str, models: list[GuardedModel], health: ModelHealth):
        super().__init__(models[0], *models[1:], fallback_on=(ModelUnavailable,))
        self.role, self.guarded, self.health = role, list(models), health
        self.hooks = Hooks()
        self._order = list(range(len(models)))
        self.requests = 0
        self.last_answered: int | None = None    # the entry that answered the run's latest request

    def begin_run(self, start: int = 0, hooks: Hooks | None = None) -> None:
        """A new run: the configured order from entry `start` (the rotation), kept for every request of
        the run (ruling 10), and the hooks that report it."""
        n = len(self.guarded)
        self._order = [(start + i) % n for i in range(n)]
        self.requests, self.last_answered = 0, None
        if hooks is not None:
            self.hooks = hooks
            for gm in self.guarded:
                gm.hooks = hooks

    def ordered(self, exclude=frozenset()) -> tuple[list[int], list[str]]:
        """This request's entries (ruling 10): the run's order without open, half-open and broken models,
        and closed models of a family under caution after the others; plus the names skipped."""
        first, later, skipped = [], [], []
        for i in self._order:
            if i in exclude:
                continue
            name = self.guarded[i].name
            state = self.health.status(name)
            if state in ("open", "half_open", "broken"):
                skipped.append(name)
            elif state == "closed" and self.health.cautioned(name):
                later.append(i)
            else:
                first.append(i)
        return first + later, skipped

    async def request(self, messages, model_settings, model_request_parameters):
        self.requests += 1
        tried: list[ModelUnavailable] = []
        done: set[int] = set()
        waited = False
        while True:
            order, skipped = self.ordered(done)     # again after every failure: a failed family moves back (ruling 9)
            if not order:
                rest = [self.guarded[i].name for i in self._order if i not in done]
                reopen = self.health.earliest_reopen(rest + [u.model for u in tried])
                now = self.health.clock()
                if waited or reopen is None or reopen - now > self.health.cfg.pool_max_wait_s:
                    raise PoolExhausted(self.role, tried, rest)
                waited = True                       # ruling 11: wait for the earliest window, once
                await _sleep(max(0.0, reopen - now))
                done = {i for i in done if self.health.status(self.guarded[i].name) != "trial"}
                continue
            i = order[0]
            gm = self.guarded[i]
            done.add(i)
            self.hooks.on_try(name=gm.name, attempt=len(tried) + 1, of=len(self.guarded),
                              after=[(u.model, u.failure) for u in tried], skipped=skipped)
            gm.request_no = self.requests
            try:
                gm.ensure_built()
                prepared = gm.prepare_messages(messages, model_request_parameters)
                response = await gm.request(prepared, model_settings, model_request_parameters)
            except ModelUnavailable as u:
                tried.append(u)
                nxt, _ = self.ordered(done)
                self.hooks.on_fallback(name=gm.name, failure=u.failure,
                                       next=self.guarded[nxt[0]].name if nxt else None, request=self.requests)
                continue
            self.last_answered = i
            return response

    @asynccontextmanager
    async def request_stream(self, *args, **kwargs):
        raise NotImplementedError("the pilot does not stream model responses")
        yield  # pragma: no cover
```

Notes for the implementer:
- `ModelHTTPError(429, "m", {"error": {"details": [{"@type": "x.QuotaFailure", ...}]}})`: `classify` checks only the `violations` quota id, so the `@type` text doesn't matter.
- If pydantic-ai's `Agent` reads `model.profile` on a `FallbackModel` (which raises `NotImplementedError`) in some code path a test hits, override `profile` in `PoolModel` to return the first guarded model's profile, and say so in your report.

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/pytest tests/test_modelguard_pool.py tests/test_modelguard_health.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/pilot/modelguard.py tests/test_modelguard_pool.py
scripts/ci-commit.sh "feat(pilot): guarded models and pools: failover inside a run" "Rulings 4-5, 7, 10-11 and 16 of the model guard design: GuardedModel paces, counts, classifies and retries once; PoolModel orders each request (rotation, family caution, open and broken skipped) and moves a failed request to the next model with the run's history, so a tool runs once; SDK retries off for Gemini and Anthropic. Verified by tests/test_modelguard_pool.py (including a Gemini run continued on Anthropic over a mock transport)."
```

---

### Task 3: The governors on the guard

**Files:**
- Modify: `src/pilot/governor.py`. The places to change:
  - imports (line 35);
  - `build_governor` (line 509);
  - `Governor.__init__` (line 541);
  - `_build` (line 665), `_agent_for` (line 678), `_order` (line 689), `_call` (line 700);
  - `_retry_models` (line 738) and `_retry_decision` (line 748);
  - `set_roles` (line 769), `set_models` (line 780) and `set_fallback` (line 792).
- Modify: `src/pilot/civ6_governor.py` (`_build`, line 303).
- Modify: tests that exercise the whole-run path (listed in Step 5).
- Modify: `docs/design/2026-10-02-model-guard-design.md` (ruling 6's sentence, ruling P1), `docs/pilot.md`, `README.md`, `ARCHITECTURE.md`.
- Test: `tests/test_governor_guard.py`.

**Interfaces:**
- Consumes (Tasks 1-2):
  - `ModelHealth`, `GuardConfig.from_settings`;
  - `GuardedModel`, `PoolModel`, `Hooks`, `event_hooks`, `emit_breaker`, `PoolExhausted`, `describe`.
- Produces:
  - `Governor.health: ModelHealth`;
  - `Governor._call(role, ask, on_try=None) -> (result, entry)` (unchanged signature);
  - `Governor._call_unguarded` (the code as at 8c80134);
  - `Governor._pool_model(role) -> PoolModel`;
  - `log.state.info["model_health"]`, as returned by `ModelHealth.snapshot()`;
  - the `pool_exhausted` event `{role, causes}`;
  - `_build(role, settings, model, agent_settings=None)` and `build_governor(s, briefing, model=None, agent_settings=None)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_governor_guard.py`. Reuse the Stellaris test helpers: `from tests.test_governor import FakeStellaris, briefing, decisions, _is_strategy_review, _quiet_no_change, setup`, the same import form the other governor test files use (check how `tests/test_governor_dashboard.py` imports `setup`, and match it).

```python
"""The governors on the model guard (docs/design/2026-10-02-model-guard-design.md, rulings 11, 17, 19,
21-23): a decision that loses its model mid-run continues on the next one without running a tool twice,
Deciding and the events say what happened, and PILOT_MODEL_GUARD=0 keeps the whole-run retries."""

from __future__ import annotations

from dataclasses import replace

import pytest
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from pilot.governor import Governor
from test_governor import FakeStellaris, _is_strategy_review, _quiet_no_change, briefing, decisions, setup  # noqa: F401

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
    first, calls = consult_then_503()
    game = FakeStellaris([briefing("2200.01.01")])
    Governor(s, game, log, model=first, fallback=decisions("expand")).run(max_decisions=1)
    assert sum(e["kind"] == "consult" for e in log.recent) == 1, "the tool ran once"
    assert "governor_directive_expand" in game.flags
    fb = [e for e in log.recent if e["kind"] == "model_fallback"][-1]
    assert fb["kind"] == "overloaded" and fb["request"] == 2 and fb["family"] == "gemini-flash"
    assert fb["error"] == "model gemini-3.8-flash answered 503"
    retry = [e for e in log.recent if e["kind"] == "model_retry"][-1]
    assert retry["kind"] == "overloaded" and retry["delay"] == 1.0 and retry["role"] == "decisions"
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
    assert fb["kind"] == "answer" and "UsageLimitExceeded" in fb["error"]


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
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/pytest tests/test_governor_guard.py -q`
Expected: FAIL. `test_a_decision_continues_on_the_fallback_and_consults_once` should see 2 consults (the whole-run retry), and `Governor` has no `health` attribute.

- [ ] **Step 3: Implement in `src/pilot/governor.py`**

1. Imports. Add `import threading` if it's missing, and add:

```python
from pydantic_ai import ModelSettings
from .modelguard import (GuardConfig, GuardedModel, Hooks, ModelHealth, PoolExhausted, PoolModel, describe,
                         emit_breaker, event_hooks)
```

2. `build_governor` takes the agent's own settings:

```python
def build_governor(s: Settings, briefing: str, model=None, agent_settings=None) -> Agent[GovDeps, GovernorDecision]:
    return Agent(resolve_model(model or s.model), deps_type=GovDeps, output_type=GovernorDecision,
                 instructions=INSTRUCTIONS + "\n\n" + briefing,
                 tools=[Tool(f) for f in (consult, get_doc, recent_log, remember_rule)],   # outcomes are in the prompt
                 model_settings=agent_settings or governor_settings(s), retries=2)
```

3. In `Governor.__init__`, directly after `self.log = log`:

```python
        # the model guard (docs/design/2026-10-02-model-guard-design.md): one per process, every role
        self.health = ModelHealth(GuardConfig.from_settings(settings), on_change=self._on_breaker,
                                  on_note=lambda text: log.emit("briefing_error", error=f"model guard: {text}"[:300]))
```

4. `_build` gains `agent_settings=None` and passes `model_settings=agent_settings or governor_settings(settings)` in all three branches. It passes `agent_settings=agent_settings` to `build_governor` in the last branch.

5. Replace `_order` and add the rotation:

```python
    def _rotation(self, role: str = "decisions") -> int:
        """Where this call starts in the role's list: 0, or one further each time (take turns)."""
        pool = self._pool(role)
        if not self._rotates(role) or len(pool) < 2:
            return 0
        turns = self.__dict__.setdefault("_turns", {})
        turn = turns.get(role, 0)
        turns[role] = turn + 1
        return turn % len(pool)

    def _order(self, role: str = "decisions") -> list[dict]:
        """This call's models: the role's list as given, or one further on each time (take turns)."""
        pool = self._pool(role)
        i = self._rotation(role)
        return pool[i:] + pool[:i]
```

6. Rename the current `_call` to `_call_unguarded`, keeping its body exactly, and change its docstring's first line to `"""The calls as before the model guard (PILOT_MODEL_GUARD=0, ruling 19): ...`. Then add the guarded path and helpers:

```python
    def _call(self, role: str, ask, on_try=None):
        """Run `ask(agent)` on the role's models; returns (result, entry used).

        With the model guard (docs/design/2026-10-02-model-guard-design.md, ruling 17) the role's one agent
        runs on its pool: a request that cannot reach a model moves to the next model inside the same run,
        so no tool runs twice, and PoolExhausted (no model could be reached) is raised at once. A run that
        ends without a usable answer (the request cap, an invalid output) runs again from the next model,
        as before the guard (plan ruling P1). PILOT_MODEL_GUARD=0: `_call_unguarded`."""
        if not self.s.model_guard:
            return self._call_unguarded(role, ask, on_try)
        configured = self._pool(role)
        start = self._rotation(role)
        pool, agent = self._pool_model(role), self._role_agent(role)
        lock = self.__dict__.setdefault("_pool_locks", {}).setdefault(role, threading.Lock())
        before: list[dict] = []          # whole runs that ended without a usable answer
        track: dict = {}
        with lock:
            try:
                for k in range(len(configured)):
                    first = (start + k) % len(configured)
                    pool.begin_run(first, self._hooks(role, configured, on_try, before, track))
                    try:
                        result = ask(agent)
                    except PoolExhausted as e:
                        self.log.emit("pool_exhausted", role=role, causes=e.causes())
                        raise
                    except Exception as e:  # noqa: BLE001 - an unusable answer: the next model runs it again
                        used = configured[pool.last_answered if pool.last_answered is not None else first]["model"]
                        if k == len(configured) - 1:
                            raise
                        self.log.emit("model_fallback", role=role, model=used, error=f"{type(e).__name__}: {e}"[:300],
                                      fallback=configured[(first + 1) % len(configured)]["model"], kind="answer",
                                      family=self.health.family(used), request=pool.requests)
                        before.append({"model": used, "error": cause(f"{type(e).__name__}: {e}")})
                        continue
                    entry = configured[pool.last_answered]
                    if role == "decisions":
                        self.log.state.info["answered"] = {"model": entry["model"], "after": track.get("after", before),
                                                           "t": round(time.time(), 1),
                                                           "fallback": entry["model"] != configured[start]["model"]}
                    return result, entry
            finally:
                self._publish_health()
        raise RuntimeError(f"no models for {role}")

    def _hooks(self, role: str, entries: list[dict], on_try, before: list[dict], track: dict) -> Hooks:
        """The pool's reports: Deciding's progress and the caller's on_try, then the events (rulings 17,
        21-22). `track["after"]` keeps what failed before the latest try."""
        deciding = self.log.state.info.get("deciding") if role == "decisions" else None
        by_name = {e["model"]: e for e in entries}

        def tried(name, attempt, of, after, skipped):
            track["after"] = before + [{"model": m, "error": describe(f)} for m, f in after]
            if on_try and name in by_name:
                on_try(by_name[name])
            if deciding is not None:
                deciding.update(model=name, attempt=len(before) + attempt, max_attempts=of, retry_at=None,
                                after=track["after"], skipped=skipped)

        def retried(name, failure, delay, attempt, request):
            if deciding is not None:
                deciding.update(retry_at=round(time.time() + delay, 1), retries=attempt, waiting=describe(failure))
        return event_hooks(self.log.emit, role, self.health.family, Hooks(on_try=tried, on_retry=retried))

    def _guarded(self, entry: dict) -> GuardedModel:
        """One pool entry with its own thinking settings (ruling 4)."""
        settings = governor_settings(replace(self.s, governor_thinking=entry["thinking"], model=entry["model"]))
        return GuardedModel(entry.get("obj") or entry["model"], entry["model"], self.health, settings=settings)

    def _pool_model(self, role: str) -> PoolModel:
        cache = self.__dict__.setdefault("_pool_models", {})
        if role not in cache:
            cache[role] = PoolModel(role, [self._guarded(e) for e in self._pool(role)], self.health)
        return cache[role]

    def _agent_settings(self) -> ModelSettings:
        """A pool agent's own settings: the timeout; each model carries its thinking (ruling 4)."""
        return ModelSettings(timeout=self.s.model_timeout_s)

    def _role_agent(self, role: str):
        cache = self.__dict__.setdefault("_pool_agents", {})
        if role not in cache:
            cache[role] = self._build(role, self.s, self._pool_model(role), agent_settings=self._agent_settings())
        return cache[role]

    def _on_breaker(self, model: str, snap: dict) -> None:
        emit_breaker(self.log.emit, model, snap)
        self._publish_health()

    def _publish_health(self) -> None:
        """Now's model-health line and the pool editor's counts read this (ruling 23)."""
        self.log.state.info["model_health"] = self.health.snapshot()

    def _reset_pools(self) -> None:
        """New models: rebuild the pools and their agents; the new pools' models lose broken marks (plan
        ruling P2)."""
        for k in ("_pool_models", "_pool_agents"):
            self.__dict__.pop(k, None)
        self.health.clear_broken({e["model"] for role in ("decisions", "strategy", "chat") for e in self._pool(role)})
        self._publish_health()
```

Check that `cause` (from `.wording`) is imported in governor.py; the old `_call` uses it, so it should be.

7. `_agent_for`, guarded branch. Inside `if key not in cache:`:

```python
            if self.s.model_guard:          # one entry, still guarded (ruling 17)
                cache[key] = self._build(role, self.s, PoolModel(role, [self._guarded(entry)], self.health),
                                         agent_settings=self._agent_settings())
                return cache[key]
```

8. `_retry_models`. Its return line becomes:

```python
        if self.s.model_guard:
            return [e for e in self._pool("strategy") if self.health.status(e["model"]) in ("closed", "trial")]
        failed, now = self.__dict__.setdefault("_failed_at", {}), time.time()
        return [e for e in self._pool("strategy") if now - failed.get(e["model"], 0) >= self.s.model_cooldown_s]
```

9. `_retry_decision`. Before `result = ask(self._agent_for(entry, "decisions"))`, add:

```python
            agent = self._agent_for(entry, "decisions")
            if self.s.model_guard and isinstance(getattr(agent, "model", None), PoolModel):
                agent.model.begin_run(0, event_hooks(self.log.emit, "decisions retry", self.health.family))
```

and use `agent` in the `ask(...)` call.

10. In `set_roles`, `set_models` and `set_fallback` (and anywhere else that does `self.__dict__.pop("_agents", None)`), call `self._reset_pools()` right after that pop.

11. `src/pilot/civ6_governor.py` `_build`: add `agent_settings=None` and use `model_settings=agent_settings or governor_settings(settings)` in both of its own branches. Pass `agent_settings` through to `super()._build(role, settings, model, agent_settings)`.

- [ ] **Step 4: Run the new tests**

Run: `.venv/bin/pytest tests/test_governor_guard.py -q`
Expected: all pass.

- [ ] **Step 5: Run the whole suite and sort the failures**

Run: `.venv/bin/pytest -q -m "not ui" -x --ignore=tests/ui`

Some tests exercise the old whole-run semantics: `test_a_chat_or_review_retry_says_its_role` (its `ask` raises the 503 itself, with no model), `test_a_retry_wait_says_when_the_next_try_is` (it calls `_on_retry` directly; that one should still pass), and any test that sets `retry_delays` and counts whole-run attempts. Give those `s.model_guard = False` (or `replace(s, model_guard=False)` with the `__class__` line the file already uses) and a comment `# the whole-run path (PILOT_MODEL_GUARD=0, model guard ruling 19)`. Any other failure is a defect in the new path: fix the code, not the test. Exception: when a test asserts an exact event list that legitimately gains `model_breaker` and `model_pace` events, filter those kinds out in the test and say so in your report. Expected end state: the full suite passes.

- [ ] **Step 6: Docs**

1. In the spec `docs/design/2026-10-02-model-guard-design.md`, ruling 6's last sentence becomes: "pydantic-ai's own `UsageLimitExceeded` (the per-decision request cap) is not a model failure: it passes through the pool untouched, and the governor's `_call` then runs the decision again from the next model, as before the guard (plan ruling P1)."
2. `docs/pilot.md`: add a section `## Model calls: pacing, retries and failover` with these paragraphs:
   - what a pool is;
   - ruling 7's table, copied from the spec;
   - the breaker windows;
   - family caution;
   - the formula `interval >= W x max(60 / RPM, 60 x tokens per request / TPM)` with W = 1;
   - the settings table: name, default, environment variable;
   - `runs/model-usage.json`;
   - the kill switch;
   - "one place for retries".
   Keep the file's tone; no Jetski material.
3. `README.md`: add the four environment variables to the settings rows, where `PILOT_FALLBACK_MODEL` is listed.
4. `ARCHITECTURE.md`: one entry for `src/pilot/modelguard.py`, next to the other `src/pilot` modules.

- [ ] **Step 7: Commit**

```bash
git add src/pilot/governor.py src/pilot/civ6_governor.py tests/test_governor_guard.py <the adjusted test files> docs/design/2026-10-02-model-guard-design.md docs/pilot.md README.md ARCHITECTURE.md
scripts/ci-commit.sh "feat(pilot): the governors call models through the model guard" "Ruling 17: each role's one agent runs on its pool, so a request that cannot reach a model moves on inside the run and no tool runs twice; Deciding, model_retry/model_fallback (kind, family, request), model_breaker, pool_exhausted and info.model_health report it; an unusable answer still runs again from the next model (plan ruling P1); PILOT_MODEL_GUARD=0 keeps the whole-run retries. Verified by tests/test_governor_guard.py and the full suite."
```

---

### Task 4: The GC4 pilot on the guard

**Files:**
- Modify: `src/pilot/agent.py` (`build_agent` line 311, `run_episode` line 320)
- Modify: `src/pilot/controller.py` (`Pilot.__init__` line 31, `set_model` line 63)
- Test: `tests/test_controller_guard.py`

**Interfaces:**
- Consumes (Tasks 1-2): `ModelHealth`, `GuardConfig`, `GuardedModel`, `PoolModel`, `event_hooks`, `emit_breaker`, `PoolExhausted`.
- Produces:
  - `build_agent(s, game_briefing, model=None, agent_settings=None)`;
  - `Pilot.health`, and `Pilot.pool` (`PoolModel`, or None with the guard off);
  - `run_episode` runs the agent once with the guard on (pool hooks emit the events), and through `run_with_retry` with it off.

- [ ] **Step 1: Write the failing test**

Create `tests/test_controller_guard.py`:

```python
"""GalCiv episodes on the model guard (docs/design/2026-10-02-model-guard-design.md, ruling 18): an episode
whose model is overloaded mid-run continues on the fallback model without repeating its actions."""

from __future__ import annotations

from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from pilot.config import Settings
from pilot.controller import Pilot
from pilot.events import EventLog
from test_pilot import FakeGame, corpus  # noqa: F401

E503 = ModelHTTPError(503, "gemini-3.8-flash", {"error": {"code": 503, "status": "UNAVAILABLE"}})


def note_then_503():
    def respond(messages, info):
        if sum(isinstance(m, ModelResponse) for m in messages) == 0:
            return ModelResponse(parts=[ToolCallPart("note", {"text": "Saw the event", "game_date": "Jul 2333"})])
        raise E503
    return FunctionModel(respond, model_name="gemini-3.8-flash")


def finisher():
    def respond(messages, info):
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
            "situation": "Event", "decision": "Done", "game_date": "", "resolved": True})])
    return FunctionModel(respond, model_name="gemini-3.1-pro-preview")


def make(corpus, tmp_path, **kw):  # noqa: F811
    s = Settings(model="google:gemini-3.8-flash", runs_dir=tmp_path / "runs", journal=tmp_path / "journal.md",
                 commit_learnings=False, game="x", fallback_model=None, **kw)
    s.__class__ = type("S", (Settings,), {"corpus_dir": property(lambda self: corpus)})
    return s, EventLog(s.runs_dir, "run1", s.model)


def test_an_episode_continues_on_the_fallback_and_notes_once(corpus, tmp_path):  # noqa: F811
    s, log = make(corpus, tmp_path)
    pilot = Pilot(s, FakeGame([]), log, model=note_then_503(), fallback=finisher())
    pilot._episode("a dialog is up", None)
    assert (tmp_path / "journal.md").read_text().count("Saw the event") == 1, "the note tool ran once"
    fb = [e for e in log.recent if e["kind"] == "model_fallback"][-1]
    assert fb["role"] == "episodes" and fb["kind"] == "overloaded" and fb["request"] == 2
    assert pilot.health.status("google:gemini-3.8-flash") == "open"
    assert any(e["kind"] == "model_breaker" for e in log.recent)
    assert log.state.info["model_health"]["models"]["google:gemini-3.8-flash"]["state"] == "open"


def test_without_the_guard_the_episode_replays_as_before(corpus, tmp_path):  # noqa: F811
    s, log = make(corpus, tmp_path, model_guard=False, retry_delays=(0,))
    pilot = Pilot(s, FakeGame([]), log, model=note_then_503(), fallback=finisher())
    pilot._episode("a dialog is up", None)
    assert (tmp_path / "journal.md").read_text().count("Saw the event") == 2, "the whole run was retried"
    assert not any(e["kind"] == "model_breaker" for e in log.recent)
```

If `FakeGame([])` or `_episode(stop_text, frame)` need other arguments, adjust the call to match `tests/test_pilot.py`, keeping the assertions.

- [ ] **Step 2: Run it to see it fail**

Run: `.venv/bin/pytest tests/test_controller_guard.py -q`
Expected: FAIL (`Pilot` has no `health`, or two `note` calls).

- [ ] **Step 3: Implement**

`src/pilot/agent.py`:

```python
def build_agent(s: Settings, game_briefing: str, model=None, agent_settings=None) -> Agent[Deps, EpisodeResult]:
    instructions = GENERIC_INSTRUCTIONS.format(coord_rule=coords.describe(s.coord_space)) + "\n\n" + game_briefing
    tools = [Tool(f) for f in (look, click, drag, key, hover, consult, get_record, note,
                               remember_rule, remember_control, learn_screen, ask_human)]
    return Agent(resolve_model(model or s.model), deps_type=Deps, output_type=EpisodeResult, instructions=instructions,
                 tools=tools, model_settings=agent_settings or model_settings(s), retries=2,
                 capabilities=[ProcessHistory(trim_images(s.images_in_context))])
```

In `run_episode`, replace the `run_with_retry(...)` call with:

```python
    limits = UsageLimits(request_limit=deps.settings.max_requests_per_episode)
    pool = getattr(agent, "model", None)
    if deps.settings.model_guard and isinstance(pool, PoolModel):
        # the model guard (docs/design/2026-10-02-model-guard-design.md, ruling 18): failover inside the run
        pool.begin_run(0, event_hooks(deps.log.emit, "episodes", pool.health.family))
        try:
            result = agent.run_sync(content, deps=deps, usage_limits=limits)
        except PoolExhausted as e:
            deps.log.emit("pool_exhausted", role="episodes", causes=e.causes())
            raise
    else:
        result = run_with_retry(lambda: agent.run_sync(content, deps=deps, usage_limits=limits),
                                deps.settings.retry_delays, on_retry)
```

Import `PoolModel`, `PoolExhausted` and `event_hooks` from `.modelguard` at the top of agent.py. Check for a circular import: modelguard imports `.claude_code` only inside `build_model`, so there is none.

`src/pilot/controller.py`, `Pilot.__init__(self, settings, game, log, model=None, fallback=None)`. Replace `self.agent = build_agent(settings, briefing, model=model)` with:

```python
        self.health = ModelHealth(GuardConfig.from_settings(settings),
                                  on_change=lambda m, snap: (emit_breaker(log.emit, m, snap),
                                                             log.state.info.__setitem__("model_health", self.health.snapshot())),
                                  on_note=lambda text: log.emit("briefing_error", error=f"model guard: {text}"[:300]))
        self._model_obj, self._fallback_obj = model, fallback
        self.pool: PoolModel | None = None
        self.agent = self._make_agent()
```

and add:

```python
    def _make_agent(self):
        """The episode agent: with the model guard, on a pool of the model and the fallback model (ruling 18)."""
        if not self.s.model_guard:
            return build_agent(self.s, self._briefing, model=self._model_obj)
        from dataclasses import replace
        entries = [(self._model_obj or self.s.model, self.s.model)]
        if self._fallback_obj is not None:
            entries.append((self._fallback_obj, getattr(self._fallback_obj, "model_name", "fallback")))
        elif self.s.fallback_model and self.s.fallback_model != self.s.model:
            entries.append((self.s.fallback_model, self.s.fallback_model))
        self.pool = PoolModel("episodes", [GuardedModel(obj, name, self.health,
                                                        settings=model_settings(replace(self.s, model=name)))
                                           for obj, name in entries], self.health)
        return build_agent(self.s, self._briefing, model=self.pool,
                           agent_settings=ModelSettings(timeout=self.s.model_timeout_s))
```

In `set_model`, replace `self.agent = build_agent(self.s, self._briefing)` with `self._model_obj = None` followed by `self.agent = self._make_agent()`. Import `ModelSettings` from `pydantic_ai`, and `ModelHealth`, `GuardConfig`, `GuardedModel`, `PoolModel` and `emit_breaker` from `.modelguard`. Import `model_settings` from `.agent` if it's missing.

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/pytest tests/test_controller_guard.py tests/test_pilot.py -q`, then `.venv/bin/pytest -q -m "not ui" --ignore=tests/ui`.
Expected: all pass. `test_model_calls_retry_transient_errors_and_timeouts` still tests `run_with_retry` directly.

- [ ] **Step 5: Commit**

```bash
git add src/pilot/agent.py src/pilot/controller.py tests/test_controller_guard.py
scripts/ci-commit.sh "feat(pilot): GalCiv episodes call models through the model guard" "Ruling 18: the episode agent runs on a pool of the model and the fallback model, so an overloaded model hands the episode to the next one without replaying its screen actions; PILOT_MODEL_GUARD=0 keeps run_with_retry. Verified by tests/test_controller_guard.py and the full suite."
```

---

### Task 5: The dashboard: sentences, the model-health line, today's counts

**Files:**
- Modify: `src/pilot/static/dashboard.html`:
  - the `describe(ev)` switch (near line 2828);
  - `PROBLEM_KINDS` and `MODEL_KINDS` (lines 2904-2908);
  - the figures panel (line 827) and its renderer near `renderGameHealth` (line 2771);
  - `renderPool` (line 3176) and its CSS (lines 486-500).
- Modify: `tests/ui/uikit.py`: `seed_scenario("deciding")` publishes a `model_health`.
- Modify: `docs/pilot.md`: one paragraph on what Now's model-health line says.
- Test: `tests/ui/test_dashboard_model_health.py` and `tests/test_dashboard_activity.py`. The latter already requires a sentence for every emitted kind, and fails until this task adds them.

**Interfaces:**
- Consumes (Task 3):
  - `info.model_health = {"day", "models": {name: {state, until, reason, openings, family, caution, today}}}`;
  - the events `model_breaker` `{model, family, state, until, reason, openings}`, `model_pace` `{model, waited_s, role}` and `pool_exhausted` `{role, causes: [{model, error}]}`.
- Produces: the page elements `#model-health` (a `p.health-line`) and `.pool li .usage`.

- [ ] **Step 1: Write the failing tests**

Run `.venv/bin/pytest tests/test_dashboard_activity.py -q`: it fails now with `no Activity sentence for ['model_breaker', 'model_pace', 'pool_exhausted']`.

In `tests/ui/uikit.py` `seed_scenario`, in the `"deciding"` branch, after `st.info["deciding"] = {...}`, add:

```python
        st.info["model_health"] = {"day": "2026-10-02", "models": {
            "google:gemini-3.8-flash": {"state": "open", "until": now + 300, "reason": "overloaded (503)", "openings": 3,
                                        "family": "gemini-flash", "caution": False, "today": 41},
            "google:gemini-3.7-flash": {"state": "closed", "until": None, "reason": "", "openings": 0,
                                        "family": "gemini-flash", "caution": True, "today": 12},
            "google:gemini-3.1-pro-preview": {"state": "closed", "until": None, "reason": "", "openings": 0,
                                              "family": "gemini-pro", "caution": False, "today": 7}}}
        log.emit("model_breaker", model="google:gemini-3.8-flash", family="gemini-flash", state="open",
                 until=now + 300, reason="overloaded (503)", openings=3)
        log.emit("pool_exhausted", role="chat", causes=[{"model": "google:gemini-3.8-flash", "error": "overloaded (503)"}])
```

Create `tests/ui/test_dashboard_model_health.py`. Follow `tests/ui/test_dashboard_orders_tab.py` for the fixtures (`live_servers`, `browser`, `open_context`, `show`), and check in `tests/ui/conftest.py` how a scenario is selected (look for how `"deciding"` is requested):

```python
"""Model health on Now and in Activity (docs/design/2026-10-02-model-guard-design.md, rulings 22-23)."""

from __future__ import annotations

import pytest
from uikit import CONTEXTS, open_context, show

pytestmark = pytest.mark.ui


@pytest.mark.parametrize("scenario", ["deciding"])
@pytest.mark.parametrize("name", list(CONTEXTS))
def test_the_model_health_line_names_skipped_and_cautioned_models(browser, live_servers, name):
    w = open_context(browser, name, live_servers)
    w.page.goto(w.base + "/", wait_until="domcontentloaded")
    w.page.wait_for_selector("#model-health:not([hidden])", timeout=15000)
    line = w.page.text_content("#model-health")
    assert "Skipped: Gemini 3.8 Flash until" in line and "(overloaded (503), 3rd time)" in line
    assert "Gemini 3.7 Flash after other families" in line
    assert "warn" in w.page.get_attribute("#model-health", "class")
    assert w.page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "no sideways scroll"
    w.context.close()


@pytest.mark.parametrize("scenario", ["deciding"])
def test_activity_says_what_the_guard_did(browser, live_servers):
    w = open_context(browser, "desktop-light", live_servers)
    w.page.goto(w.base + "/", wait_until="domcontentloaded")
    show(w.page, "activity")
    w.page.wait_for_selector("#feed li")
    text = w.page.text_content("#feed")
    assert "Gemini 3.8 Flash skipped until" in text and "3rd time" in text
    assert "No model could answer (chat): Gemini 3.8 Flash overloaded (503)" in text
    w.context.close()
```

The `scenario` fixture (`tests/ui/conftest.py`) picks `seed_scenario`'s state, as in `tests/ui/test_dashboard_governor.py`. The Activity list is `#feed`. Read `shortModel` for the display names ("Gemini 3.8 Flash"), and adjust the expected text if it words them differently.

- [ ] **Step 2: Implement in `dashboard.html`**

1. In `describe(ev)`, next to `case "model_retry":`, add:

```js
    case "model_breaker": return breakerSentence(ev);
    case "model_pace": return `Waited ${dur(ev.waited_s)} before calling ${modelName(ev.model)}, to keep requests apart`;
    case "pool_exhausted": return `No model could answer${ev.role && ev.role !== "decisions" ? ` (${human(ev.role)})` : ""}: ${(ev.causes || []).map((c) => `${modelName(c.model)} ${c.error}`).join("; ")}`;
```

and before `function describe(ev)`, add:

```js
// the model guard's breakers (model guard design, rulings 8 and 22)
const nth = (n) => n === 2 ? "2nd" : n === 3 ? "3rd" : `${n}th`;
function breakerSentence(ev) {
  const m = modelName(ev.model);
  if (ev.state === "open") return `${m} skipped until ${hhmm(ev.until)} (${ev.reason}${ev.openings > 1 ? `, ${nth(ev.openings)} time` : ""})`;
  if (ev.state === "half_open") return `Trying ${m} again`;
  if (ev.state === "broken") return `${m} cannot be used (${ev.reason}); skipped until the models change`;
  return `${m} answers again`;
}
```

2. Add `"model_breaker"`, `"model_pace"` and `"pool_exhausted"` to `MODEL_KINDS`. Add `"pool_exhausted"` to `PROBLEM_KINDS`. Also add `"model_breaker"` to `PROBLEM_KINDS`: `feedCats` puts an event in every set that names its kind, so a closed breaker shows under Problems too, which is acceptable. If `feedCats` lets you filter by state, add only the `open` and `broken` breaker events.

3. After `<p class="health-line" id="game-health" hidden></p>`, add `<p class="health-line" id="model-health" hidden></p>`. After `renderGameHealth`, add:

```js
// Model health (model guard design, ruling 23): one line while a model is skipped or its family waits.
function renderModelHealth() {
  const el = $("model-health"), live = S.live && S.campaign === (S.status.info || {}).campaign;
  const models = live ? ((S.status.info || {}).model_health || {}).models || {} : {};
  const skipped = Object.entries(models).filter(([, h]) => h.state === "open" || h.state === "broken")
    .map(([m, h]) => h.state === "broken" ? `${modelName(m)} (${h.reason}, until the models change)`
      : `${modelName(m)} until ${hhmm(h.until)} (${h.reason}${h.openings > 1 ? `, ${nth(h.openings)} time` : ""})`);
  const later = Object.entries(models).filter(([, h]) => h.state === "closed" && h.caution).map(([m]) => `${modelName(m)} after other families`);
  const parts = [skipped.length ? `Skipped: ${skipped.join(", ")}` : "", ...later].filter(Boolean);
  el.textContent = parts.join("; ") + (parts.length ? "." : "");
  el.className = "health-line" + (skipped.length ? " warn" : "");
  el.hidden = !parts.length;
  if (!el.hidden) $("p-figures").hidden = false;
}
```

Call `renderModelHealth()` everywhere `renderGameHealth()` is called (lines 1501 and 1778).

4. In `renderPool`, compute `const usage = (((S.status || {}).info || {}).model_health || {}).models || {};`. In each `<li>`, before the note, add `${usage[e.model] ? `<span class="usage">${usage[e.model].today} requests today</span>` : ""}`. In the CSS next to `.pool li .note`, add `.pool li .usage { grid-column: 2 / -1; font-size: 12px; color: var(--muted); }`. Also add `.pool li .usage` to the small-text selector list at line 643, where `.pool li .note` is listed.

5. Change the `pool-hint` texts to say that failover happens per request:
   - rotate on: "Each call starts with the next model in the list; a request that fails moves to the next model within the same call."
   - rotate off: "The first model is used; a request that fails (overloaded, bad key, no answer) moves to the next model within the same call."

- [ ] **Step 3: Run the tests**

Run: `.venv/bin/pytest tests/test_dashboard_activity.py -q`, then `.venv/bin/pytest -m ui tests/ui -q`.
Expected: all pass. The UI tests need Playwright's Chromium (`.venv/bin/python -m playwright install chromium` if it's missing).

- [ ] **Step 4: Docs**

In `docs/pilot.md`'s "Model calls" section (added by Task 3), add one paragraph covering:
- Now's model-health line: which models are skipped and until when, and which families wait;
- the pool editor's "N requests today";
- the Activity sentences for breakers, pacing waits and "No model could answer".

- [ ] **Step 5: Commit**

```bash
git add src/pilot/static/dashboard.html tests/ui/uikit.py tests/ui/test_dashboard_model_health.py docs/pilot.md
scripts/ci-commit.sh "feat(dashboard): model health on Now and the guard's events in Activity" "Rulings 22-23 of the model guard design: sentences for model_breaker, model_pace and pool_exhausted, a model-health line naming skipped models and waiting families, and today's requests per model in the pool editor. Verified by tests/test_dashboard_activity.py and tests/ui/test_dashboard_model_health.py at every viewport."
```

---

## After the tasks (the controller, not a subagent)

1. Final whole-branch review, then `superpowers:finishing-a-development-branch`: merge to `main` after `scripts/ci.sh` passes, and push.
2. Deploy with `scripts/deploy-pilot.sh <commit before the merge> <merge commit>`, running `--dry-run` first. No pilot runs, so the viewer restarts for the dashboard (ruling 26).
3. Ruling 20's removal of the kill switch, `run_with_retry`, `retry_delays` and `model_cooldown_s` is a separate later commit, after one full campaign meets the success criteria.
4. `plan.md`: flip the model guard entry to `[x]` with the deploy commit. `issues.md`: flip the replay issue to `[x]` with the deploy commit, since the fix ships with the deploy. Ruling 27's live check comes with the next campaign. Record it in that campaign's journal and in the spec's status line.
