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
            page = await c.get("/", allow_redirects=False)                 # the page sends a browser to sign in
            assert page.status == 303 and page.headers["Location"].startswith("/pair?")
    asyncio.run(go())


def test_key_header_opens_the_api(tmp_path):
    async def go():
        async with TestClient(TestServer(viewer(tmp_path)), headers={"X-Pilot-Key": KEY}) as c:
            assert (await c.get("/runs")).status == 200
            assert (await c.get("/status")).status == 200
            assert (await c.get("/")).status == 200
    asyncio.run(go())


def test_a_valid_key_link_in_the_window_redirects_to_sign_in_without_a_cookie(tmp_path):
    """The old link no longer sets a cookie holding the key: inside the 72-hour carry-over it becomes
    a one-time sign-in link (the key never reaches the address bar or a cookie again)."""
    async def go():
        async with TestClient(TestServer(viewer(tmp_path)), headers=NO_KEY) as c:
            r = await c.get(f"/?key={KEY}", allow_redirects=False)
            assert r.status == 303 and r.headers["Location"].startswith("/pair#c=")
            assert "Set-Cookie" not in r.headers and KEY not in r.headers["Location"]
            assert (await c.get("/runs")).status == 401
            r = await c.get("/?key=wrong", allow_redirects=False)
            assert r.status == 303 and "Set-Cookie" not in r.headers
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


def test_pc_status_does_not_expose_the_window_title(monkeypatch):
    calls: list = []
    monkeypatch.setenv("GAME_AGENT_TOKEN", "t")
    monkeypatch.setattr("urllib.request.urlopen", fake_agent("Inbox - private mail", ["Stellaris", "Inbox - private mail"], calls))
    st = dashboard.pc_status()
    assert "Inbox" not in json.dumps(st)
    assert st == {"online": True, "version": "1.4.0", "games": ["stellaris"], "game_in_front": False, "front_game": None}
    monkeypatch.setattr("urllib.request.urlopen", fake_agent("Stellaris", ["Stellaris"], calls))
    st = dashboard.pc_status()
    assert st["game_in_front"] is True and st["front_game"] == "stellaris"


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


# ---------- run ids ----------

@pytest.mark.parametrize("rid", ["20260926-185855", "run1", "archive_2"])
def test_run_id_accepts_real_ids(rid):
    assert dashboard.RUN_ID.match(rid)


@pytest.mark.parametrize("rid", ["..", ".", ".hidden", "a/b", "a\\b", "a..b", ""])
def test_run_id_rejects_traversal(rid):
    assert not dashboard.RUN_ID.match(rid)


def test_the_access_page_offers_a_box_for_the_key():
    from pilot.dashboard import LOCKED_PAGE
    assert '<form method="get" action="/"' in LOCKED_PAGE and 'name="key"' in LOCKED_PAGE
