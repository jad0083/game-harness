"""Dashboard access key, CSRF checks, the PC status it exposes, run-id and key-combo validation."""

from __future__ import annotations

import asyncio
import io
import json
import stat
from contextlib import redirect_stdout

import pytest
from aiohttp.test_utils import TestClient, TestServer

from pilot import dashboard
from pilot.dashboard import make_app
from pilot.events import EventLog

KEY = "k" * 43
NO_KEY: dict = {}          # an explicit empty header set: the conftest default key is not added


class FakePilot:
    def __init__(self, log):
        self.log = log
        self.paused = False

    def pause(self):
        self.paused = True
        self.log.state.status = "paused"


def viewer(tmp_path, key=KEY):
    runs = tmp_path / "runs"
    runs.mkdir(exist_ok=True)
    return make_app(None, runs, key=key)


# ---------- the key itself ----------

def test_key_comes_from_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("PILOT_DASHBOARD_KEY", "from-env")
    assert dashboard.dashboard_key(tmp_path) == "from-env"
    assert not (tmp_path / "dashboard.key").exists()


def test_key_is_generated_once_and_stored_private(tmp_path, monkeypatch):
    monkeypatch.delenv("PILOT_DASHBOARD_KEY", raising=False)
    k1 = dashboard.dashboard_key(tmp_path / "runs")
    path = tmp_path / "runs" / "dashboard.key"
    assert len(k1) >= 40 and path.read_text().strip() == k1
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert dashboard.dashboard_key(tmp_path / "runs") == k1


def test_dashboard_link_cli_prints_the_link(tmp_path, monkeypatch):
    from pilot import cli
    monkeypatch.setenv("PILOT_DASHBOARD_KEY", KEY)
    out = io.StringIO()
    with redirect_stdout(out):
        assert cli.main(["dashboard-link", "--port", "8781"]) == 0
    link = out.getvalue().strip()
    assert link.startswith("http://") and link.endswith(f":8781/?key={KEY}")
    assert "0.0.0.0" not in link


# ---------- access ----------

def test_everything_but_the_page_needs_the_key(tmp_path):
    async def go():
        async with TestClient(TestServer(viewer(tmp_path)), headers=NO_KEY) as c:
            for path in ("/status", "/runs", "/api/campaigns", "/api/pc", "/api/models", "/events.json",
                         "/frame.jpg", "/events", "/runs/run1/events", "/runs/run1/trace/1", "/runs/run1/frame.jpg"):
                r = await c.get(path)
                assert r.status == 401, path
            for path in ("/control", "/api/settings", "/api/run"):
                r = await c.post(path, json={"action": "pause"})
                assert r.status == 401, path
            r = await c.get("/api/campaigns", headers={"X-Pilot-Key": "wrong"})
            assert r.status == 401
            page = await c.get("/")
            assert page.status == 401
            text = await page.text()
            assert "dashboard-link" in text and "<script" not in text
    asyncio.run(go())


def test_key_header_opens_the_api(tmp_path):
    async def go():
        async with TestClient(TestServer(viewer(tmp_path)), headers={"X-Pilot-Key": KEY}) as c:
            assert (await c.get("/runs")).status == 200
            assert (await c.get("/status")).status == 200
            assert (await c.get("/")).status == 200
    asyncio.run(go())


def test_key_link_sets_a_strict_cookie_and_redirects(tmp_path):
    async def go():
        async with TestClient(TestServer(viewer(tmp_path)), headers=NO_KEY) as c:
            r = await c.get(f"/?key={KEY}", allow_redirects=False)
            assert r.status in (302, 303) and r.headers["Location"] == "/"
            cookie = r.headers["Set-Cookie"]
            assert "pilot_key=" in cookie and "HttpOnly" in cookie and "SameSite=Strict" in cookie
            assert (await c.get("/runs")).status == 200           # the cookie jar now carries the key
            page = await c.get("/")
            assert page.status == 200 and "<script" in await page.text()
        async with TestClient(TestServer(viewer(tmp_path)), headers=NO_KEY) as c:
            r = await c.get("/?key=wrong", allow_redirects=False)
            assert r.status == 401 and "Set-Cookie" not in r.headers
    asyncio.run(go())


# ---------- CSRF ----------

def test_mutations_need_json_and_a_matching_origin(tmp_path):
    async def go():
        async with TestClient(TestServer(viewer(tmp_path)), headers={"X-Pilot-Key": KEY}) as c:
            body = json.dumps({"rotate": False})
            r = await c.post("/api/settings", data=body, headers={"Content-Type": "text/plain"})
            assert r.status == 403
            r = await c.post("/api/settings", data=body)            # no content type at all
            assert r.status == 403
            r = await c.post("/api/settings", json={"rotate": False}, headers={"Origin": "http://evil.example"})
            assert r.status == 403
            host = f"{c.server.host}:{c.server.port}"
            r = await c.post("/api/settings", json={"rotate": False}, headers={"Origin": f"http://{host}"})
            assert r.status == 200
            r = await c.post("/api/settings", json={"rotate": False})  # no Origin (curl, the viewer's proxy)
            assert r.status == 200
    asyncio.run(go())


def test_live_pilot_needs_the_key_and_json(tmp_path):
    log = EventLog(tmp_path / "runs", "run1", "m")
    pilot = FakePilot(log)

    async def go():
        async with TestClient(TestServer(make_app(pilot, key=KEY)), headers=NO_KEY) as c:
            assert (await c.post("/control", json={"action": "pause"})).status == 401
            assert (await c.get("/frame.jpg")).status == 401
            r = await c.post("/control", data='{"action": "pause"}',
                             headers={"X-Pilot-Key": KEY, "Content-Type": "text/plain"})
            assert r.status == 403 and not pilot.paused
            r = await c.post("/control", json={"action": "pause"}, headers={"X-Pilot-Key": KEY})
            assert r.status == 200 and pilot.paused
    asyncio.run(go())
    log.close()


def test_viewer_passes_the_key_to_the_live_pilot(tmp_path):
    runs = tmp_path / "runs"
    log = EventLog(runs, "run1", "m")
    pilot = FakePilot(log)

    async def go():
        live = TestServer(make_app(pilot, key=KEY))
        await live.start_server()
        log.state.info["port"] = live.port
        log.state.status = "playing"
        log.emit("status", status="playing")
        async with TestClient(TestServer(make_app(None, runs, key=KEY)), headers={"X-Pilot-Key": KEY}) as v:
            st = await (await v.get("/status")).json()
            assert st["live"] is True and st["run_id"] == "run1"
            r = await v.post("/control", json={"action": "pause"})
            assert r.status == 200 and pilot.paused
        await live.close()
    asyncio.run(go())
    log.close()


# ---------- run ids ----------

@pytest.mark.parametrize("rid", ["20260926-185855", "run1", "archive_2"])
def test_run_id_accepts_real_ids(rid):
    assert dashboard.RUN_ID.match(rid)


@pytest.mark.parametrize("rid", ["..", ".", ".hidden", "a/b", "a\\b", "a..b", ""])
def test_run_id_rejects_traversal(rid):
    assert not dashboard.RUN_ID.match(rid)


# ---------- /api/pc ----------

class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake_agent(foreground: str, titles: list[str], calls: list):
    def urlopen(req, timeout=None):
        calls.append(req.full_url)
        if req.full_url.endswith("/health"):
            return FakeResp(json.dumps({"version": "1.4.0", "foreground": foreground}).encode())
        return FakeResp(json.dumps({"windows": [{"title": t} for t in titles]}).encode())
    return urlopen


def test_pc_status_uses_the_configured_agent_url(monkeypatch):
    from pilot.config import Settings
    calls: list = []
    monkeypatch.setenv("GAME_AGENT_TOKEN", "t")
    monkeypatch.setattr("urllib.request.urlopen", fake_agent("", [], calls))
    monkeypatch.setenv("GAME_AGENT_URL", "http://10.9.9.9:1234/")
    dashboard.pc_status()
    assert calls[0] == "http://10.9.9.9:1234/health"
    monkeypatch.delenv("GAME_AGENT_URL")
    calls.clear()
    dashboard.pc_status()
    assert calls[0] == Settings().agent_url.rstrip("/") + "/health"
