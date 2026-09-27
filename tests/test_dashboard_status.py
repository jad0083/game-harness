"""What the dashboard serves for the governor line and its card (docs/design/2026-09-27-dashboard-v2-design.md,
rulings 7, 9 and 10): the game-screen capture, model health, the PC chip's states, no duplicate models."""

from __future__ import annotations

import asyncio
import io
import json
import urllib.error

import pytest
from aiohttp.test_utils import TestClient, TestServer
from authkit import KEY, NO_KEY, ProdServer, browser_cookie, viewer

from pilot import dashboard
from pilot.dashboard import make_app
from pilot.events import EventLog
from pilot.models import check_pool


class Shot:
    def __init__(self, image):
        self.image = image


class LivePilot:
    def __init__(self, log, image=b"\xff\xd8jpeg"):
        self.log = log
        self.game = type("G", (), {"screenshot": lambda _self: Shot(image)})()


def test_capture_stores_the_game_screen_as_the_runs_frame_and_says_who(tmp_path):
    runs = tmp_path / "runs"
    log = EventLog(runs, "20260927-100000", "m")
    log.state.info["attention"] = {"reason": "autoplay did not start", "category": "transient", "frame": ""}
    app = make_app(LivePilot(log), runs, key=KEY)

    async def go():
        async with TestClient(TestServer(app), headers={"X-Pilot-Key": KEY, "X-Pilot-Device": "d1",
                                                        "X-Pilot-Device-Name": "Pixel%20phone"}) as c:
            r = await c.post("/api/capture", json={})
            assert r.status == 200, await r.text()
            frame = (await r.json())["frame"]
        assert frame and (log.dir / frame).read_bytes() == b"\xff\xd8jpeg"
        assert log.state.frame_path == frame and log.state.info["attention"]["frame"] == frame
        ev = next(e for e in log.recent if e["kind"] == "capture")
        assert ev["by"] == "Pixel phone" and ev["frame"] == frame
    asyncio.run(go())
    log.close()


def test_a_capture_that_gets_no_image_says_so(tmp_path):
    runs = tmp_path / "runs"
    log = EventLog(runs, "20260927-100000", "m")

    async def go():
        async with TestClient(TestServer(make_app(LivePilot(log, image=None), runs, key=KEY)),
                              headers={"X-Pilot-Key": KEY}) as c:
            r = await c.post("/api/capture", json={})
            assert r.status == 502 and (await r.json())["error"] == "capture_failed"
    asyncio.run(go())
    log.close()


def test_capture_is_refused_without_a_session(tmp_path, clock):
    app, _ = viewer(tmp_path, clock)

    async def go():
        async with TestClient(ProdServer(app), headers=NO_KEY) as c:
            r = await c.post("/api/capture", json={}, headers={"Origin": f"http://{c.server.host}:{c.server.port}"})
            assert r.status == 401
    asyncio.run(go())


def test_the_viewer_without_a_live_run_cannot_capture(tmp_path, clock):
    app, auth = viewer(tmp_path, clock)
    _, cookie = browser_cookie(auth)

    async def go():
        async with TestClient(ProdServer(app), headers=NO_KEY) as c:
            c.session.cookie_jar.update_cookies({"pilot_session": cookie})
            r = await c.post("/api/capture", json={}, headers={"Origin": f"http://{c.server.host}:{c.server.port}"})
            assert r.status == 503
    asyncio.run(go())


def _events(log, kinds_and_fields):
    for kind, fields in kinds_and_fields:
        log.emit(kind, **fields)


def test_health_counts_calls_that_fell_back_or_failed(tmp_path):
    runs = tmp_path / "runs"
    log = EventLog(runs, "20260927-100000", "m")
    for n in range(1, 6):
        if n in (2, 3, 5):
            log.emit("model_fallback", role="decisions", model="google:gemini-3.8-flash",
                     error="ModelHTTPError: status_code: 503, high demand", fallback="google:gemini-3.1-pro-preview")
        log.save_trace(n, {"episode": n, "model": "google:gemini-3.1-pro-preview" if n in (2, 3, 5) else "google:gemini-3.8-flash",
                           "date": f"T{50 + n}", "outcome": "stuck", "steps": []})
    log.emit("model_fallback", role="strategy", model="anthropic:claude-x", error="status_code: 400, credit balance too low",
             fallback="google:gemini-3.1-pro-preview")

    async def go():
        async with TestClient(TestServer(make_app(None, runs))) as c:
            h = await (await c.get("/api/health?run=20260927-100000")).json()
        assert h["calls"] == 5 and h["bad"] == 3 and h["last_fell_back"] is True
        assert h["from_model"] == "google:gemini-3.8-flash" and h["to_model"] == "google:gemini-3.1-pro-preview"
        assert h["cause"] == "overloaded (503)"
        assert h["billing"] == [{"model": "anthropic:claude-x", "cause": "billing: credit balance too low"}]
    asyncio.run(go())
    log.close()


def test_health_of_a_quiet_run_is_calm(tmp_path):
    runs = tmp_path / "runs"
    log = EventLog(runs, "20260927-100000", "m")
    log.save_trace(1, {"episode": 1, "model": "google:gemini-3.8-flash", "date": "T50", "outcome": "stuck", "steps": []})

    async def go():
        async with TestClient(TestServer(make_app(None, runs))) as c:
            h = await (await c.get("/api/health?run=20260927-100000")).json()
            assert h["bad"] == 0 and h["billing"] == [] and h["last_fell_back"] is False
            assert (await c.get("/api/health?run=../x")).status == 404
    asyncio.run(go())
    log.close()


class FakeResp(io.BytesIO):
    def __init__(self, body: dict):
        super().__init__(json.dumps(body).encode())

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.mark.parametrize(("error", "state"), [
    (urllib.error.URLError(ConnectionRefusedError(111, "Connection refused")), "offline"),
    (urllib.error.URLError(TimeoutError("timed out")), "timeout"),
    (TimeoutError("timed out"), "timeout"),
    (urllib.error.HTTPError("http://pc:8765/health", 401, "Unauthorized", {}, None), "refused"),
])
def test_the_pc_chip_tells_offline_from_not_answering(monkeypatch, error, state):
    monkeypatch.setenv("GAME_AGENT_TOKEN", "t")
    monkeypatch.setenv("GAME_AGENT_URL", "http://mini-rig2:8765")

    def urlopen(req, timeout=None):
        raise error
    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    st = dashboard.pc_status()
    assert st["online"] is False and st["state"] == state and st["host"] == "mini-rig2"


def test_the_pc_chip_names_the_host(monkeypatch):
    monkeypatch.setenv("GAME_AGENT_TOKEN", "t")
    monkeypatch.setenv("GAME_AGENT_URL", "http://mini-rig2:8765")

    def urlopen(req, timeout=None):
        if req.full_url.endswith("/health"):
            return FakeResp({"version": "1.6.1", "foreground": "Sid Meier's Civilization VI (DX12)"})
        return FakeResp({"windows": [{"title": "Sid Meier's Civilization VI (DX12)"}]})
    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    st = dashboard.pc_status()
    assert st["state"] == "on" and st["host"] == "mini-rig2" and st["front_game"] == "civ6"


def test_the_model_list_refuses_the_same_model_twice():
    with pytest.raises(ValueError, match="twice"):
        check_pool([{"model": "google:gemini-3.8-flash", "thinking": "high"},
                    {"model": "google:gemini-3.8-flash", "thinking": "low"}])
    assert len(check_pool([{"model": "google:gemini-3.8-flash"}, {"model": "google:gemini-3.1-pro-preview"}])) == 2
