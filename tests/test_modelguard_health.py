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
