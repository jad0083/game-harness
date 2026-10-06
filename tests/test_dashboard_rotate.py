"""Key rotation with a review of the carried-over devices, and scoped script tokens (rulings 45, 47, 48):
`dashboard-key --rotate [--keep all|none|ID,…] [--force]` and `dashboard-token create|list|revoke`."""

from __future__ import annotations

import asyncio
import io
import json
import stat
import threading
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from aiohttp.test_utils import TestClient, TestServer
from authkit import NO_KEY

from pilot import auth as A
from pilot import cli
from pilot.dashboard import make_app
from pilot.events import EventLog

OLD = "o" * 43


def run_cli(*argv: str, stdin: str | None = None, monkeypatch=None) -> tuple[int, str]:
    if stdin is not None:
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
    out = io.StringIO()
    with redirect_stdout(out):
        try:
            code = cli.main(list(argv))
        except SystemExit as e:
            code = e.code
    return code, out.getvalue()


@pytest.fixture
def runs(tmp_path, monkeypatch):
    """runs/ with the old key in its file (no PILOT_DASHBOARD_KEY), and a store that has carried over
    two old-cookie browsers, one signed-in browser and a script token."""
    monkeypatch.delenv("PILOT_DASHBOARD_KEY", raising=False)
    monkeypatch.setenv("PILOT_RUNS_DIR", str(tmp_path / "runs"))
    r = tmp_path / "runs"
    r.mkdir()
    (r / "dashboard.key").write_text(OLD + "\n")
    (r / "dashboard.key").chmod(0o600)
    auth = A.Auth.from_env(r)                       # the viewer's first start: the 72-hour window opens
    store = auth.store
    chrome = store.create_device("browser", name="Chrome on Windows", created_via="legacy_cookie",
                                 created_by="legacy_link", ip="192.168.1.77", legacy=True)[0]
    phone = store.create_device("browser", name="Chrome on Android", created_via="legacy_cookie",
                                created_by="legacy_link", ip="192.168.1.140", legacy=True)[0]
    brave = store.create_device("browser", name="Brave on Windows", created_via="link", created_by=chrome["id"],
                                ip="192.168.1.77")[0]
    token = store.create_device("script", name="laptop watch", scope="read", created_via="cli", created_by="cli")[0]
    return {"dir": r, "auth": auth, "store": store, "chrome": chrome, "phone": phone, "brave": brave, "token": token}


def revoked(store, dev) -> str | None:
    return store.device(dev["id"])["revoke_reason"]


# ---------- rotation ----------

def test_rotate_keeps_the_named_carried_over_devices_and_signs_out_the_rest(runs):
    code, out = run_cli("dashboard-key", "--rotate", "--keep", runs["chrome"]["id"])
    assert code == 0, out
    store = runs["store"]
    assert revoked(store, runs["chrome"]) is None
    assert revoked(store, runs["phone"]) == "rotate_unkept"
    assert revoked(store, runs["brave"]) is None and revoked(store, runs["token"]) is None     # nobody else
    key = (runs["dir"] / "dashboard.key").read_text().strip()
    assert key != OLD and len(key) >= 40 and OLD not in out and key not in out
    assert stat.S_IMODE((runs["dir"] / "dashboard.key").stat().st_mode) == 0o600
    auth = A.Auth.from_env(runs["dir"])
    assert not auth.legacy_open()
    events = {r["event"] for r in store.audit_rows()}
    assert {"key_rotated", "legacy_kept", "legacy_revoked"} <= events
    assert "Chrome on Android" in out and "192.168.1.140" in out


@pytest.mark.parametrize("keep,chrome,phone", [("all", None, None), ("none", "rotate_unkept", "rotate_unkept")])
def test_rotate_keep_all_or_none(runs, keep, chrome, phone):
    code, _ = run_cli("dashboard-key", "--rotate", "--keep", keep)
    assert code == 0
    assert revoked(runs["store"], runs["chrome"]) == chrome and revoked(runs["store"], runs["phone"]) == phone


def test_rotate_asks_which_to_keep_when_run_at_a_terminal(runs, monkeypatch):
    monkeypatch.setattr(cli, "_interactive", lambda: True)
    code, out = run_cli("dashboard-key", "--rotate", stdin=runs["phone"]["id"] + "\n", monkeypatch=monkeypatch)
    assert code == 0 and "Keep which" in out
    assert revoked(runs["store"], runs["phone"]) is None and revoked(runs["store"], runs["chrome"]) == "rotate_unkept"


def test_rotate_refuses_without_an_answer_when_not_at_a_terminal(runs, monkeypatch):
    monkeypatch.setattr(cli, "_interactive", lambda: False)
    code, out = run_cli("dashboard-key", "--rotate")
    assert code != 0 and "--keep" in out
    assert (runs["dir"] / "dashboard.key").read_text().strip() == OLD


def test_rotate_refuses_unknown_ids(runs):
    code, out = run_cli("dashboard-key", "--rotate", "--keep", "0000000000")
    assert code != 0 and "0000000000" in out
    assert (runs["dir"] / "dashboard.key").read_text().strip() == OLD


def _pair(app, *bodies: dict) -> list[int]:
    """POST /pair with each body in turn, in fresh browsers (no cookie): their statuses."""
    async def go():
        out = []
        for body in bodies:
            async with TestClient(TestServer(app), headers=NO_KEY) as c:
                r = await c.post("/pair", json=body, headers={"Origin": f"http://{c.server.host}:{c.server.port}"})
                out.append(r.status)
        return out
    return asyncio.run(go())


def test_a_device_added_from_a_carried_over_one_is_carried_over_too(runs):
    """The leaked key's carried-over device L adds D through Add a device: D is flagged legacy, listed
    under L at rotation and signed out with it (--keep none), so L cannot launder itself into D."""
    store, auth = runs["store"], runs["auth"]
    thief = store.create_device("browser", name="Chrome on Linux", created_via="legacy_cookie",
                                created_by="legacy_link", ip="192.168.1.203", legacy=True)[0]
    g = store.create_grant(thief["id"], words=True)
    assert _pair(make_app(None, runs["dir"], auth=auth), {"words": g["words"], "name": "Innocent Chrome"}) == [200]
    d = next(x for x in store.list_devices() if x["name"] == "Innocent Chrome")
    assert d["legacy"] == 1 and d["created_by"] == thief["id"]
    code, out = run_cli("dashboard-key", "--rotate", "--keep", "none")
    assert code == 0 and "Innocent Chrome" in out
    assert revoked(store, thief) == "rotate_unkept" and revoked(store, d) == "rotate_unkept"
    assert [x["name"] for x in store.list_devices() if x["kind"] == "browser"] == []


def test_keeping_a_carried_over_device_keeps_what_it_added(runs):
    code, out = run_cli("dashboard-key", "--rotate", "--keep", runs["chrome"]["id"])
    assert code == 0 and "Brave on Windows" in out                           # listed under Chrome
    assert revoked(runs["store"], runs["brave"]) is None and revoked(runs["store"], runs["phone"]) == "rotate_unkept"


def test_an_old_key_link_made_before_rotation_signs_nobody_in_after_it(runs):
    store, auth = runs["store"], runs["auth"]
    g = store.create_grant("legacy_link")
    mine = store.create_grant(runs["phone"]["id"], words=True)            # a code the unkept phone left open
    assert run_cli("dashboard-key", "--rotate", "--keep", runs["chrome"]["id"])[0] == 0
    assert store.grant(g["id"])["state"] == "cancelled" and store.grant(mine["id"])["state"] == "cancelled"
    assert _pair(make_app(None, runs["dir"], auth=auth), {"link": g["link"]}, {"words": mine["words"]}) == [410, 410]


def test_an_old_key_link_expires_with_the_window(tmp_path):
    from authkit import Clock, viewer
    clock = Clock()
    app, auth = viewer(tmp_path, clock)
    g = auth.store.create_grant("legacy_link")
    clock.t += A.LEGACY_WINDOW_S - 60                 # made in the window's last minutes
    auth.store._x("UPDATE grants SET created_at=?, expires_at=? WHERE id=?", (clock.t, clock.t + 600, g["id"]))
    clock.t += 120                                     # the window has closed; the grant has 8 minutes left
    assert not auth.legacy_open()
    assert _pair(app, {"link": g["link"]}) == [410]
    assert [d for d in auth.store.list_devices() if d["kind"] == "browser"] == []


def test_a_device_carried_over_while_the_prompt_waits_is_signed_out_too(runs, monkeypatch):
    """The legacy list is read before the prompt; a carried-over device minted while it waits (one per
    page load with another user agent) is not in it, and is signed out all the same."""
    monkeypatch.setattr(cli, "_interactive", lambda: True)
    store, late = runs["store"], {}

    class Slow(io.StringIO):
        def readline(self, *a):
            late["dev"] = store.create_device("browser", name="Firefox on Linux", created_via="legacy_cookie",
                                              created_by="legacy_link", ip="192.168.1.203", legacy=True)[0]
            return "none\n"

    monkeypatch.setattr("sys.stdin", Slow())
    code, out = run_cli("dashboard-key", "--rotate")
    assert code == 0, out
    assert revoked(store, late["dev"]) == "rotate_unkept"
    assert [x["name"] for x in store.list_devices() if x["kind"] == "browser"] == []


def test_rotate_refuses_while_the_key_comes_from_the_environment(runs, monkeypatch):
    monkeypatch.setenv("PILOT_DASHBOARD_KEY", OLD)
    code, out = run_cli("dashboard-key", "--rotate", "--keep", "all")
    assert code != 0 and "PILOT_DASHBOARD_KEY" in out and "restart both services" in out
    assert (runs["dir"] / "dashboard.key").read_text().strip() == OLD


def fake_live_pilot(runs_dir, status: dict):
    """A live run whose dashboard answers /status as `status` (a pre-change pilot has no auth_version)."""
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps(status).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    log = EventLog(runs_dir, "20260927-100000", "m")        # its run and run state in the store
    log.emit("run_start", model="m")
    log.state.status = "playing"
    log.state.info["port"] = srv.server_address[1]
    log.emit("status", status="playing")
    status["run_id"] = log.state.run_id
    return srv


def test_rotate_refuses_while_a_pre_change_live_pilot_runs(runs):
    srv = fake_live_pilot(runs["dir"], {"status": "playing", "info": {"game": "civ6"}})
    try:
        code, out = run_cli("dashboard-key", "--rotate", "--keep", "all")
        assert code != 0 and "reads the key only at startup" in out
        assert (runs["dir"] / "dashboard.key").read_text().strip() == OLD
        code, _ = run_cli("dashboard-key", "--rotate", "--keep", "all", "--force")
        assert code == 0 and (runs["dir"] / "dashboard.key").read_text().strip() != OLD
    finally:
        srv.shutdown()


def test_rotate_goes_ahead_with_a_new_live_pilot(runs):
    srv = fake_live_pilot(runs["dir"], {"status": "playing", "info": {"auth_version": 1}})
    try:
        assert run_cli("dashboard-key", "--rotate", "--keep", "all")[0] == 0
    finally:
        srv.shutdown()


def test_dashboard_key_without_rotate_explains_itself(runs):
    code, out = run_cli("dashboard-key")
    assert code != 0 and "--rotate" in out and OLD not in out


def test_a_running_viewer_and_live_pilot_take_the_new_key(runs):
    """After a rotation both new-code processes use the new key (the file is re-read), and the old
    one stops working."""
    log = EventLog(runs["dir"], "run1", "m")

    class P:
        def __init__(self):
            self.log = log

    live = make_app(P())
    keys = live[A.AUTH_KEY].keys

    async def go():
        async with TestClient(TestServer(live), headers=NO_KEY) as c:
            assert (await c.get("/status", headers={"X-Pilot-Key": OLD})).status == 200
            assert run_cli("dashboard-key", "--rotate", "--keep", "all")[0] == 0
            keys.reload()                          # (the 2-second stat window, collapsed for the test)
            new = (runs["dir"] / "dashboard.key").read_text().strip()
            assert (await c.get("/status", headers={"X-Pilot-Key": OLD})).status == 401
            assert (await c.get("/status", headers={"X-Pilot-Key": new})).status == 200
    asyncio.run(go())
    log.close()


# ---------- script tokens ----------

def test_token_create_prints_it_once_with_its_scope(runs):
    code, out = run_cli("dashboard-token", "create", "--name", "laptop watch", "--scope", "read")
    assert code == 0
    tok = next(w for w in out.split() if w.startswith("pgt_"))
    assert "read" in out and "Authorization: Bearer" in out
    row, why = runs["store"].check("script", tok)
    assert not why and row["scope"] == "read" and row["name"] == "laptop watch" and row["expires_at"] is None
    code, out = run_cli("dashboard-token", "list")
    assert code == 0 and "laptop watch" in out and "pgt_" not in out
    code, _ = run_cli("dashboard-token", "revoke", row["id"])
    assert code == 0 and runs["store"].check("script", tok)[1] == "revoked"
    assert any(r["event"] == "token_revoked" for r in runs["store"].audit_rows())


def test_token_scopes_and_expiry(runs):
    code, out = run_cli("dashboard-token", "create", "--name", "ctl", "--scope", "control", "--expires", "90d")
    assert code == 0
    tok = next(w for w in out.split() if w.startswith("pgt_"))
    row, _ = runs["store"].check("script", tok)
    assert abs(row["expires_at"] - (row["created_at"] + 90 * 86400)) < 5
    for bad in (["--scope", "admin"], ["--expires", "soon"]):
        code, _ = run_cli("dashboard-token", "create", "--name", "x", *(["--scope", "read"] if bad[0] != "--scope" else []), *bad)
        assert code != 0
    assert run_cli("dashboard-token", "revoke", "0000000000")[0] != 0


def test_a_cli_token_works_on_the_viewer_by_its_scope(runs, tmp_path):
    _, out = run_cli("dashboard-token", "create", "--name", "watch", "--scope", "read")
    read = next(w for w in out.split() if w.startswith("pgt_"))
    app = make_app(None, runs["dir"], auth=runs["auth"])

    async def go():
        async with TestClient(TestServer(app), headers=NO_KEY) as c:
            assert (await c.get("/status", headers={"Authorization": f"Bearer {read}"})).status == 200
            r = await c.post("/api/settings", json={"rotate": False}, headers={"Authorization": f"Bearer {read}"})
            assert r.status == 403 and (await r.json())["error"] == "read_only"
            c.session.cookie_jar.update_cookies({"pilot_session": read})
            assert (await c.get("/status")).status == 401
    asyncio.run(go())
