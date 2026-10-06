"""The live pilot's own dashboard (ruling 36): bound to 127.0.0.1, only the service key as a header from
loopback, no cookies, no sign-in routes; it records which device asked (X-Pilot-Device from the
viewer) and reports auth_version. `python -m pilot control` drives it through the viewer and fails
loudly. The new viewer and an old live pilot (and the reverse) keep working during a rolling restart."""

from __future__ import annotations

import asyncio
import hmac
import io
import json
from contextlib import redirect_stdout
from urllib.parse import quote

from aiohttp import ClientSession, web
from aiohttp.test_utils import TestClient, TestServer
from authkit import KEY, NO_KEY, browser_cookie, client, lan_request, origin, through_guard, viewer

from pilot import auth as A
from pilot import cli
from pilot.config import Settings
from pilot.dashboard import make_app, read_events
from pilot.events import EventLog
from pilot.store import open_store


class FakePilot:
    def __init__(self, log):
        self.log = log
        self.paused = False

    def pause(self):
        self.paused = True
        self.log.state.status = "paused"

    def resume(self):
        self.paused = False
        self.log.state.status = "playing"

    def stop(self):
        pass

    def instruct(self, text):
        self.log.emit("instruction", text=text)

    def chat(self, text):
        self.log.emit("chat", role="human", text=text)


def live_app(tmp_path, **kw):
    log = EventLog(tmp_path / "runs", "run1", "m")
    log.emit("run_start", model="m")         # the run's row in the store, as a real run records it
    return make_app(FakePilot(log), key=KEY, **kw), log


def events_of(log, kind):
    return read_events(log.store, log.state.run_id, {kind})


# ---------- config ----------

def test_live_pilot_binds_loopback_by_default(monkeypatch):
    for var in ("PILOT_LIVE_HOST", "PILOT_VIEW_HOST"):
        monkeypatch.delenv(var, raising=False)
    s = Settings.from_env()
    assert s.live_host == "127.0.0.1" and s.dashboard_host == "0.0.0.0" and s.view_host == "0.0.0.0"
    monkeypatch.setenv("PILOT_LIVE_HOST", "0.0.0.0")
    monkeypatch.setenv("PILOT_VIEW_HOST", "192.168.1.76")
    s = Settings.from_env()
    assert s.live_host == "0.0.0.0" and s.view_host == "192.168.1.76" and s.dashboard_host == "192.168.1.76"


def test_run_serves_the_live_dashboard_on_the_live_host():
    import inspect
    src = inspect.getsource(cli.run)
    assert "serve_in_background(pilot, s.live_host, s.dashboard_port)" in src


def test_view_takes_a_host(monkeypatch, tmp_path):
    from aiohttp import web as aioweb
    seen: dict = {}
    monkeypatch.setenv("PILOT_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setattr(aioweb, "run_app", lambda app, **kw: seen.update(kw))
    out = io.StringIO()
    with redirect_stdout(out):
        assert cli.main(["view", "--port", "8781", "--host", "127.0.0.1"]) == 0
    assert seen["host"] == "127.0.0.1" and seen["port"] == 8781 and seen["access_log"] is None


# ---------- the live guard ----------

def test_live_guard_takes_only_the_key_header_from_loopback(tmp_path):
    app, log = live_app(tmp_path)

    async def go():
        async with TestClient(TestServer(app), headers=NO_KEY) as c:
            assert (await c.get("/status", headers={"X-Pilot-Key": KEY})).status == 200
            assert (await c.get("/status", headers={"Authorization": f"Bearer {KEY}"})).status == 200
            c.session.cookie_jar.update_cookies({"pilot_key": KEY})                 # the old cookie: refused
            r = await c.get("/status")
            assert r.status == 401 and (await r.json())["error"] == "sign_in_required"
            c.session.cookie_jar.clear()
            assert (await c.get(f"/status?key={KEY}")).status == 401
            r = await c.get("/", allow_redirects=False)
            assert r.status == 401 and "Set-Cookie" not in r.headers
            for path in ("/pair", "/api/auth/me", "/api/auth/devices"):
                r = await c.get(path, headers={"X-Pilot-Key": KEY})
                assert r.status == 404, path                                         # no sign-in routes here
            r = await c.get("/status", headers={"X-Pilot-Key": KEY, "X-Forwarded-For": "192.168.1.9"})
            assert r.status == 401
            r = await c.post("/control", data='{"action": "pause"}', headers={"X-Pilot-Key": KEY, "Content-Type": "text/plain"})
            assert r.status == 403
            r = await c.get("/status", headers={"X-Pilot-Key": KEY})
            h = r.headers
            assert h["Cache-Control"] == "no-store" and h["X-Frame-Options"] == "DENY" and h["X-Content-Type-Options"] == "nosniff"
    asyncio.run(go())
    log.close()


def test_live_guard_refuses_the_key_from_the_lan(tmp_path):
    app, log = live_app(tmp_path)
    guard = next(m for m in app.middlewares)

    async def go():
        async def handler(_):
            return web.json_response({"ok": True})
        r = await guard(lan_request(app, "GET", "/status", {"X-Pilot-Key": KEY}), handler)
        assert r.status == 401 and json.loads(r.body)["error"] == "service_key_loopback_only"
    asyncio.run(go())
    log.close()


def test_live_status_reports_auth_version(tmp_path):
    app, log = live_app(tmp_path)

    async def go():
        async with TestClient(TestServer(app), headers={"X-Pilot-Key": KEY}) as c:
            st = await (await c.get("/status")).json()
        assert st["info"]["auth_version"] == 1
    asyncio.run(go())
    log.close()


def test_live_pilot_records_which_device_asked(tmp_path):
    app, log = live_app(tmp_path)

    async def go():
        async with TestClient(TestServer(app), headers={"X-Pilot-Key": KEY}) as c:
            dev = {A.DEVICE_HEADER: "a1b2c3d4e5", A.DEVICE_NAME_HEADER: quote("Pixel phone")}
            assert (await c.post("/control", json={"action": "pause"}, headers=dev)).status == 200
            assert (await c.post("/control", json={"action": "chat", "text": "why?"}, headers=dev)).status == 200
            assert (await c.post("/control", json={"action": "instruct", "text": "hold"}, headers=dev)).status == 200
            assert (await c.post("/control", json={"action": "resume"})).status == 200     # a script on the controller
    asyncio.run(go())
    controls = events_of(log, "control")
    assert controls[0]["action"] == "pause" and controls[0]["by"] == "Pixel phone" and controls[0]["by_id"] == "a1b2c3d4e5"
    assert controls[-1]["action"] == "resume" and controls[-1]["by"] == "the controller"
    assert [e["by"] for e in events_of(log, "chat")] == ["Pixel phone"]
    assert events_of(log, "instruction")[0]["by"] == "Pixel phone"
    status_after = [e for e in events_of(log, "status")]
    assert all("by" not in e or e["by"] in ("Pixel phone", "the controller") for e in status_after)
    log.close()


def test_the_live_stream_closes_when_the_key_changes(tmp_path, monkeypatch):
    monkeypatch.delenv("PILOT_DASHBOARD_KEY", raising=False)
    runs = tmp_path / "runs"
    (runs / "secrets").mkdir(parents=True, mode=0o700)
    (runs / "secrets/dashboard.key").write_text(KEY + "\n")
    log = EventLog(runs, "run1", "m")
    app = make_app(FakePilot(log), keepalive_s=0.1)

    async def go():
        async with TestClient(TestServer(app), headers={"X-Pilot-Key": KEY}) as c:
            r = await c.get("/events")
            assert r.status == 200
            await r.content.readany()
            app[A.AUTH_KEY].keys.reload()
            (runs / "secrets/dashboard.key").write_text("n" * 43 + "\n")
            app[A.AUTH_KEY].keys.reload()
            loop = asyncio.get_running_loop()
            t0 = loop.time()
            while not r.content.at_eof():
                await asyncio.wait_for(r.content.readany(), 2)
            assert loop.time() - t0 < 1.0
    asyncio.run(go())
    log.close()


# ---------- rolling restart: new viewer with an old pilot, old viewer with a new pilot ----------

OLD_PILOT = web.AppKey("old_pilot", object)


def old_live_app(log) -> web.Application:
    """The live pilot as deployed before this change: the key as a cookie or header, from anywhere."""
    want = KEY.encode()

    @web.middleware
    async def old_guard(request, handler):
        given = request.headers.get("X-Pilot-Key") or request.cookies.get("pilot_key")
        if not (given and hmac.compare_digest(given.encode(), want)):
            return web.Response(status=401, text="dashboard key required")
        return await handler(request)

    pilot = FakePilot(log)

    async def status(_):
        return web.json_response({**log.state.as_dict(), "live": True})

    async def control(request):
        body = await request.json()
        getattr(pilot, body["action"])()
        return web.json_response({"ok": True, "status": log.state.status})

    app = web.Application(middlewares=[old_guard])
    app.add_routes([web.get("/status", status), web.post("/control", control)])
    app[OLD_PILOT] = pilot
    return app


def test_new_viewer_drives_an_old_live_pilot(tmp_path, clock):
    runs = tmp_path / "runs"
    log = EventLog(runs, "run1", "m")
    log.emit("run_start", model="m")         # the run's row in the store, as a real run records it
    old = old_live_app(log)

    async def go():
        server = TestServer(old)
        await server.start_server()
        log.state.info["port"] = server.port
        log.state.status = "playing"
        log.emit("status")
        app, auth = viewer(tmp_path, clock)
        _, cookie = browser_cookie(auth)
        async with client(app, cookie) as c:
            st = await (await c.get("/status")).json()
            assert st["live"] is True and st["run_id"] == "run1"
            r = await c.post("/control", json={"action": "pause"}, headers=origin(c))
            assert r.status == 200 and old[OLD_PILOT].paused
        await server.close()
    asyncio.run(go())
    log.close()


def test_old_viewer_drives_a_new_live_pilot(tmp_path):
    """The deployed viewer's forwarding: the key as X-Pilot-Key to 127.0.0.1, the browser's
    Content-Type passed through, no device header."""
    app, log = live_app(tmp_path)

    async def go():
        server = TestServer(app)
        await server.start_server()
        base = f"http://127.0.0.1:{server.port}"
        async with ClientSession() as s:
            async with s.get(base + "/status", headers={"X-Pilot-Key": KEY}) as r:
                assert r.status == 200 and (await r.json())["run_id"] == "run1"
            async with s.post(base + "/control", data=b'{"action": "pause"}',
                              headers={"Content-Type": "application/json", "X-Pilot-Key": KEY}) as r:
                assert r.status == 200
            async with s.get(base + "/events.json", headers={"X-Pilot-Key": KEY}) as r:
                assert r.status == 200
        await server.close()
    asyncio.run(go())
    assert events_of(log, "control")[0]["by"] == "the controller"
    log.close()


# ---------- python -m pilot control ----------

def run_control(monkeypatch, tmp_path, status: int, reply: dict, *argv: str) -> tuple[int, str, list]:
    calls: list = []
    monkeypatch.setenv("PILOT_RUNS_DIR", str(tmp_path / "runs"))

    class Resp(io.BytesIO):
        def __init__(self, body):
            super().__init__(body)
            self.status = status

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def urlopen(req, timeout=None):
        import urllib.error
        calls.append((req.full_url, json.loads(req.data), dict(req.header_items())))
        body = json.dumps(reply).encode()
        if status >= 400:
            raise urllib.error.HTTPError(req.full_url, status, "err", {}, io.BytesIO(body))
        return Resp(body)

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    out = io.StringIO()
    with redirect_stdout(out):
        code = cli.main(["control", *argv])
    return code, out.getvalue(), calls


def test_control_posts_json_over_loopback_with_the_key(monkeypatch, tmp_path):
    code, out, calls = run_control(monkeypatch, tmp_path, 200, {"ok": True, "status": "paused"}, "pause")
    assert code == 0 and "paused" in out
    url, body, headers = calls[0]
    assert url == "http://127.0.0.1:8780/control" and body == {"action": "pause"}
    assert headers["X-pilot-key"] == "test-dashboard-key" and headers["Content-type"] == "application/json"
    assert headers["X-pilot-device-name"] == quote("the controller")
    code, _, calls = run_control(monkeypatch, tmp_path, 200, {"ok": True}, "instruct", "--text", "hold the line",
                                 "--port", "8781")
    assert calls[0][0] == "http://127.0.0.1:8781/control" and calls[0][1] == {"action": "instruct", "text": "hold the line"}
    _, _, calls = run_control(monkeypatch, tmp_path, 200, {"ok": True}, "order_remove", "--index", "2")
    assert calls[0][1] == {"action": "order_remove", "index": 2}


def test_control_exits_non_zero_with_the_servers_error(monkeypatch, tmp_path, capsys):
    code, out, _ = run_control(monkeypatch, tmp_path, 401, {"error": "bad_token", "reason": "The token is unknown.",
                                                            "fix": "Create one."}, "pause")
    assert code != 0 and "401" in out and "The token is unknown." in out
    code, out, _ = run_control(monkeypatch, tmp_path, 503, {"error": "x"}, "resume")
    assert code != 0


def test_control_through_the_viewer_reaches_the_live_pilot(tmp_path, clock):
    """End to end on loopback: the CLI's request (the key header) to a viewer that forwards to the pilot."""
    runs = tmp_path / "runs"
    live, log = live_app(tmp_path)

    async def go():
        server = TestServer(live)
        await server.start_server()
        log.state.info["port"] = server.port
        log.state.status = "playing"
        log.emit("status")
        app, _ = viewer(tmp_path, clock)
        async with client(app) as c:
            r = await c.post("/control", json={"action": "pause"},
                             headers={"X-Pilot-Key": KEY, A.DEVICE_NAME_HEADER: quote("the controller")})
            assert r.status == 200
        await server.close()
    asyncio.run(go())
    assert events_of(log, "control")[0]["by"] == "the controller"
    assert runs.exists()
    log.close()


def test_a_browser_behind_the_viewer_is_named_on_the_live_pilot(tmp_path, clock):
    live, log = live_app(tmp_path)

    async def go():
        server = TestServer(live)
        await server.start_server()
        log.state.info["port"] = server.port
        log.state.status = "playing"
        log.emit("status")
        app, auth = viewer(tmp_path, clock)
        _, cookie = browser_cookie(auth, name="Pixel phone")
        async with client(app, cookie) as c:
            assert (await c.post("/control", json={"action": "pause"}, headers=origin(c))).status == 200
            r = await through_guard(auth, lan_request(app, "GET", "/status", {"X-Pilot-Key": KEY}))
            assert r.status == 401
        await server.close()
    asyncio.run(go())
    assert events_of(log, "control")[0]["by"] == "Pixel phone"
    log.close()


def test_a_stop_the_live_pilot_accepts_is_noted_by_the_supervisor(tmp_path, clock, monkeypatch):
    """The page's Stop goes to the live pilot through the viewer. Once the pilot accepts it, the viewer's
    supervisor marks the run not live (a stopped run never resumes, and a dashboard stop meanwhile sends it
    no second SIGTERM); a refused stop or another action does not."""
    from pilot import dashboard
    live, log = live_app(tmp_path)
    stops = []

    def stop(self):
        stops.append(1)
        if len(stops) == 1:
            raise RuntimeError("the pilot refused")
    monkeypatch.setattr(FakePilot, "stop", stop)

    async def go():
        server = TestServer(live)
        await server.start_server()
        log.state.info["port"] = server.port
        log.state.status = "playing"
        log.emit("status")
        app, auth = viewer(tmp_path, clock)
        noted = []
        monkeypatch.setattr(app[dashboard.SUPERVISOR], "note_stop", lambda: noted.append(1))
        _, cookie = browser_cookie(auth, name="Pixel phone")
        async with client(app, cookie) as c:
            assert (await c.post("/control", json={"action": "pause"}, headers=origin(c))).status == 200
            assert (await c.post("/control", json={"action": "stop"}, headers=origin(c))).status == 500
            assert noted == []
            assert (await c.post("/control", json={"action": "stop"}, headers=origin(c))).status == 200
            assert noted == [1]
        await server.close()
    asyncio.run(go())
    log.close()


def test_what_a_device_changes_is_in_the_sign_in_log(tmp_path, clock, monkeypatch):
    """Rulings 49.6 and 50: /control, /api/settings, /api/run and /api/capture through the viewer each
    leave a `control` audit row naming the action and the device, so a revoked session's doings show
    in dashboard-devices log and Recent sign-in activity; saved settings name who saved them."""
    import sys
    live, log = live_app(tmp_path)
    runs = tmp_path / "runs"
    child = tmp_path / "child.py"                       # stands in for `pilot run`, the supervisor's child
    child.write_text("import time\nwhile True:\n    time.sleep(0.05)\n")
    monkeypatch.setenv("PILOT_SUPERVISOR_ARGV", f"{sys.executable} {child}")
    for var, value in (("GAME_AGENT_URL", "http://127.0.0.1:9"), ("GAME_AGENT_TOKEN", "t" * 40), ("GEMINI_API_KEY", "x")):
        monkeypatch.setenv(var, value)
    monkeypatch.delenv("PILOT_MODEL", raising=False)

    async def go():
        server = TestServer(live)
        await server.start_server()
        log.state.info["port"] = server.port
        log.state.status = "playing"
        log.emit("status")
        app, auth = viewer(tmp_path, clock)
        dev, cookie = browser_cookie(auth, name="Pixel phone")
        async with client(app, cookie) as c:
            assert (await c.post("/control", json={"action": "pause"}, headers=origin(c))).status == 200
            assert (await c.post("/control", json={"action": "resume"}, headers=origin(c))).status == 200
            assert (await c.post("/api/settings", json={"rotate": True}, headers=origin(c))).status == 200
            await c.post("/api/capture", json={}, headers=origin(c))
        await server.close()
        log.state.status = "stopped"
        log.emit("status")
        app, auth = viewer(tmp_path, clock)                 # a fresh viewer: no live run cached
        async with client(app, cookie) as c:
            assert (await c.post("/api/run", json={"game": "civ6"}, headers=origin(c))).status == 200
        return auth, dev
    auth, dev = asyncio.run(go())
    rows = [r for r in auth.store.audit_rows() if r["event"] == "control"]
    actions = sorted(json.loads(r["detail"])["action"] for r in rows)
    assert actions == ["capture", "pause", "resume", "run", "settings"]
    assert all(r["device_id"] == dev and r["ip"] == "127.0.0.1" for r in rows)
    text = " | ".join(e["text"] for e in A.audit_sentences(auth.store))
    assert "Pixel phone" in text and "paused the run" in text.lower() and "started a run" in text.lower()
    assert open_store(runs).query("SELECT changed_by FROM settings WHERE key='prefs'") == [{"changed_by": "Pixel phone"}]
    log.close()


def test_a_last_stand_is_a_live_run_to_the_viewer_and_the_cli(tmp_path, clock, monkeypatch):
    """Civ6Governor's `last stand` status (ruling 22) is live: the viewer keeps forwarding /status and
    the stream (the red alarm shows) and the CLI's live_pilots finds the run; only stopped is not live."""
    from pilot.dashboard import live_status
    live, log = live_app(tmp_path)
    assert all(live_status(s) for s in ("starting", "playing", "deciding", "paused", "needs_attention", "last stand"))
    assert not any(live_status(s) for s in ("stopped", "", None))

    async def go():
        server = TestServer(live)
        await server.start_server()
        log.state.info["port"] = server.port
        log.state.status = "last stand"
        log.emit("status")
        app, _ = viewer(tmp_path, clock)
        async with client(app, headers={"X-Pilot-Key": KEY}) as c:
            st = await (await c.get("/status")).json()
            assert (await c.get("/events.json")).status == 200
        found = await asyncio.to_thread(cli.live_pilots, Settings.from_env(), KEY)
        await server.close()
        return st, found
    monkeypatch.setenv("PILOT_RUNS_DIR", str(tmp_path / "runs"))
    st, found = asyncio.run(go())
    assert st["live"] is True and st["status"] == "last stand"
    assert [r for r, _v in found] == ["run1"]
    log.close()


def test_a_settings_change_is_one_activity_row(tmp_path):
    """set_models, set_roles, set_fallback, edit_pillar and unpin_pillar each leave their own event
    (models, roles, strategy) carrying `by`: no second `control` row for the same save."""
    class Pilot(FakePilot):
        def set_models(self, models, rotate=None):
            self.log.emit("models", models=models, rotate=bool(rotate))

        def set_roles(self, roles):
            self.log.emit("roles", roles=roles)

    log = EventLog(tmp_path / "runs", "run1", "m")
    app = make_app(Pilot(log), key=KEY)

    async def go():
        async with TestClient(TestServer(app), headers={"X-Pilot-Key": KEY}) as c:
            dev = {A.DEVICE_HEADER: "a1b2c3d4e5", A.DEVICE_NAME_HEADER: quote("Pixel phone")}
            pool = [{"model": "google:gemini-3.8-flash", "thinking": "medium"}]
            assert (await c.post("/control", json={"action": "set_models", "models": pool}, headers=dev)).status == 200
            assert (await c.post("/control", json={"action": "set_roles", "roles": {}}, headers=dev)).status == 200
    asyncio.run(go())
    assert events_of(log, "control") == []
    assert [e["by"] for e in events_of(log, "models") + events_of(log, "roles")] == ["Pixel phone", "Pixel phone"]
    from pilot.dashboard import OWN_EVENT
    assert {"set_models", "set_roles", "set_fallback", "edit_pillar", "unpin_pillar"} <= OWN_EVENT
    log.close()
