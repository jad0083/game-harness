"""Dashboard sign-in (docs/design/2026-09-27-dashboard-v2-design.md, rulings 34-52): the service key
works only as a header from loopback, browsers hold their own revocable sessions, the Host is
allow-listed, and the old key cookie carries over for 72 hours.

aiohttp's TestClient always connects from 127.0.0.1, so every "from the LAN" case builds a request
with make_mocked_request and a transport whose peer is 192.168.1.50, and runs the guard on it."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import stat
from urllib.parse import parse_qs, urlsplit

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from authkit import (  # noqa: F401
    DAY,
    KEY,
    LAN,
    NO_KEY,
    Clock,
    body,
    browser_cookie,
    client,
    lan_request,
    origin,
    through_guard,
    viewer,
)

from pilot import auth as A
from pilot.dashboard import LiveProxy, make_app
from pilot.events import EventLog

# ---------- the service key ----------

def test_service_key_from_loopback_is_the_service(tmp_path, clock):
    app, _ = viewer(tmp_path, clock)

    async def go():
        async with client(app) as c:
            r = await c.get("/api/auth/me", headers={"X-Pilot-Key": KEY})
            assert r.status == 200 and (await r.json())["via"] == "service"
            r = await c.get("/api/auth/me", headers={"Authorization": f"Bearer {KEY}"})
            assert r.status == 200 and (await r.json())["via"] == "service"
    asyncio.run(go())


def test_service_key_from_the_lan_is_refused_and_audited(tmp_path, clock):
    app, auth = viewer(tmp_path, clock)

    async def go():
        for hdr in ({"X-Pilot-Key": KEY}, {"Authorization": f"Bearer {KEY}"}):
            r = await through_guard(auth, lan_request(app, "GET", "/status", hdr))
            assert r.status == 401 and body(r)["error"] == "service_key_loopback_only"
            assert r.headers["WWW-Authenticate"].startswith("Bearer")
    asyncio.run(go())
    rows = auth.store.audit_rows()
    assert any(r["event"] == "service_key_refused_lan" and r["ip"] == LAN for r in rows)


def test_service_key_is_never_the_service_behind_a_forwarding_header(tmp_path, clock):
    app, _ = viewer(tmp_path, clock)

    async def go():
        async with client(app) as c:
            for fwd in ({"Forwarded": "for=192.168.1.9"}, {"X-Forwarded-For": "192.168.1.9"}):
                r = await c.get("/status", headers={"X-Pilot-Key": KEY, **fwd})
                assert r.status == 401 and (await r.json())["error"] == "service_key_loopback_only"
    asyncio.run(go())


def test_ipv4_mapped_loopback_is_loopback_and_buckets_unwrap():
    assert A.is_loopback("::ffff:127.0.0.1") and A.is_loopback("::1") and A.is_loopback("127.0.0.1")
    assert not A.is_loopback("192.168.1.50") and not A.is_loopback("") and not A.is_loopback(None)
    assert A.bucket_of("2001:db8:1:2::5") == A.bucket_of("2001:db8:1:2:abcd::9") != A.bucket_of("2001:db8:1:3::5")
    assert A.bucket_of("::ffff:192.168.1.9") == A.bucket_of("192.168.1.9") == "ip:192.168.1.9"


def test_key_rotation_is_picked_up_through_mtime_and_inode(tmp_path, clock, monkeypatch):
    monkeypatch.delenv("PILOT_DASHBOARD_KEY", raising=False)
    runs = tmp_path / "runs"
    runs.mkdir()
    ticks = [0.0]
    keys = A.KeySource(runs, monotonic=lambda: ticks[0])
    old = keys.get()
    assert stat.S_IMODE((runs / "secrets/dashboard.key").stat().st_mode) == 0o600
    auth = A.Auth(keys, A.AuthStore(runs / "auth.sqlite", clock=clock), clock=clock)
    app = make_app(None, runs, auth=auth)

    async def go():
        async with client(app) as c:
            assert (await c.get("/status", headers={"X-Pilot-Key": old})).status == 200
            tmp = runs / "secrets/dashboard.key.new"
            tmp.write_text("n" * 43 + "\n")
            os.chmod(tmp, 0o600)
            os.replace(tmp, runs / "secrets/dashboard.key")          # a new inode, as `dashboard-key --rotate` writes it
            assert (await c.get("/status", headers={"X-Pilot-Key": old})).status == 200   # stat at most every 2 s
            ticks[0] += 2.1
            assert (await c.get("/status", headers={"X-Pilot-Key": old})).status == 401
            assert (await c.get("/status", headers={"X-Pilot-Key": "n" * 43})).status == 200
    asyncio.run(go())


def test_live_proxy_reloads_the_key_once_after_a_401(tmp_path, clock, monkeypatch):
    monkeypatch.delenv("PILOT_DASHBOARD_KEY", raising=False)
    runs = tmp_path / "runs"
    log = EventLog(runs, "run1", "m")
    log.emit("run_start", model="m")         # the run's row in the store, as a real run records it
    seen: list = []

    async def status(request):
        seen.append(request.headers.get("X-Pilot-Key"))
        if request.headers.get("X-Pilot-Key") != "new" * 11:
            return web.json_response({"error": "bad_token"}, status=401)
        return web.json_response({"run_id": "run1", "status": "playing"})

    async def go():
        live = web.Application()
        live.router.add_get("/status", status)
        server = TestServer(live)
        await server.start_server()
        log.state.info["port"] = server.port
        log.state.status = "playing"
        log.emit("status")
        (runs / "secrets").mkdir(mode=0o700)
        (runs / "secrets/dashboard.key").write_text("old" * 11 + "\n")
        keys = A.KeySource(runs, monotonic=lambda: 0.0)
        assert keys.get() == "old" * 11
        (runs / "secrets/dashboard.key").write_text("new" * 11 + "\n")      # rotated; the 2 s stat window has not passed
        proxy = LiveProxy(runs, keys)
        assert await proxy.url() == f"http://127.0.0.1:{server.port}"
        assert seen == ["old" * 11, "new" * 11]
        await proxy.close()
        await server.close()
    asyncio.run(go())
    log.close()


def test_device_header_is_set_by_the_viewer_never_passed_through_from_a_browser(tmp_path, clock):
    runs = tmp_path / "runs"
    log = EventLog(runs, "run1", "m")
    log.emit("run_start", model="m")         # the run's row in the store, as a real run records it
    got: list = []

    async def control(request):
        got.append((request.headers.get(A.DEVICE_HEADER), request.headers.get(A.DEVICE_NAME_HEADER)))
        return web.json_response({"ok": True})

    async def status(_):
        return web.json_response({"run_id": "run1", "status": "playing"})

    async def go():
        live = web.Application()
        live.router.add_get("/status", status)
        live.router.add_post("/control", control)
        server = TestServer(live)
        await server.start_server()
        log.state.info["port"] = server.port
        log.state.status = "playing"
        log.emit("status")
        app, auth = viewer(tmp_path, clock)
        dev, cookie = browser_cookie(auth, name="Pixel phone")
        async with client(app, cookie) as c:
            r = await c.post("/control", json={"action": "pause"},
                             headers={**origin(c), A.DEVICE_HEADER: "spoofed", A.DEVICE_NAME_HEADER: "Mallory"})
            assert r.status == 200
        async with client(app) as c:          # the service key may name the device it acts for
            await c.post("/control", json={"action": "pause"}, headers={"X-Pilot-Key": KEY, A.DEVICE_HEADER: "cli"})
        await server.close()
        assert got[0] == (dev, "Pixel%20phone")
        assert got[1][0] == "cli"
    asyncio.run(go())
    log.close()


# ---------- credential kinds ----------

def test_credential_kinds_stay_apart(tmp_path, clock):
    app, auth = viewer(tmp_path, clock)
    _, cookie = browser_cookie(auth)
    read = auth.store.create_device("script", name="laptop watch", scope="read", created_via="cli", created_by="cli")[1]
    ctl = auth.store.create_device("script", name="watch", scope="control", created_via="cli", created_by="cli")[1]
    assert read.startswith("pgt_") and cookie.startswith("s1.")

    async def go():
        async with client(app) as c:
            r = await c.get("/status", headers={"X-Pilot-Key": cookie})              # a session is no header token
            assert r.status == 401 and (await r.json())["error"] == "bad_token"
            c.session.cookie_jar.update_cookies({A.SESSION_COOKIE: ctl})            # a token is no cookie
            r = await c.get("/status")
            assert r.status == 401
            c.session.cookie_jar.clear()
            for q in (f"/status?key={KEY}", f"/status?key={ctl}", f"/api/campaigns?key={ctl}"):
                assert (await c.get(q)).status == 401, q                             # never from a query string
            assert (await c.get("/status", headers={"Authorization": f"Bearer {read}"})).status == 200
            r = await c.post("/api/settings", json={"rotate": False}, headers={"Authorization": f"Bearer {read}"})
            assert r.status == 403 and (await r.json())["error"] == "read_only"
            r = await c.post("/api/settings", json={"rotate": False}, headers={"X-Pilot-Key": ctl})
            assert r.status == 200
            for tok in (read, ctl):
                assert (await c.get("/api/auth/devices", headers={"X-Pilot-Key": tok})).status == 403
                r = await c.post("/api/auth/devices", json={"action": "revoke_others"}, headers={"X-Pilot-Key": tok})
                assert r.status == 403
                assert (await c.get("/api/auth/me", headers={"X-Pilot-Key": tok})).status == 200
    asyncio.run(go())


def test_a_bad_header_token_from_the_lan_counts_as_a_failure(tmp_path, clock):
    app, auth = viewer(tmp_path, clock)

    async def go():
        r = await through_guard(auth, lan_request(app, "GET", "/status", {"X-Pilot-Key": "pgt_0123456789." + "x" * 43}))
        assert r.status == 401 and body(r)["error"] == "bad_token"
    asyncio.run(go())
    assert auth.throttle.failures(A.bucket_of(LAN)) == 1


# ---------- host allowlist ----------

def test_unknown_host_names_get_421_before_anything_else(tmp_path, clock):
    app, auth = viewer(tmp_path, clock)

    async def go():
        async with client(app) as c:
            r = await c.get("/status", headers={"Host": "evil.example:8780", "X-Pilot-Key": KEY})
            assert r.status == 421 and "PILOT_DASHBOARD_HOSTS" in await r.text()
            r = await c.post("/pair", json={"words": "map orb cra"},
                             headers={"Host": "rebind.evil.example:8780", "Origin": "http://rebind.evil.example:8780"})
            assert r.status == 421
    asyncio.run(go())
    assert any(r["event"] == "host_refused" for r in auth.store.audit_rows())


def test_allowed_host_names(monkeypatch):
    import socket
    monkeypatch.setattr(socket, "gethostname", lambda: "deb-mini2")
    monkeypatch.setattr(socket, "getfqdn", lambda *a: "deb-mini2.corp.example")
    extra = frozenset({"pilot.home"})
    for h in ("192.168.1.76:8780", "127.0.0.1", "[::1]:8780", "[fe80::1]", "localhost:8780", "deb-mini2:8780",
              "deb-mini2.local", "DEB-MINI2.corp.example:8780", "pilot.home:8780"):
        assert A.allowed_host(h, extra), h
    for h in ("evil.example", "deb-mini2.evil.example", "", "192.168.1.76.nip.io"):
        assert not A.allowed_host(h, extra), h


def test_dashboard_hosts_and_public_url_extend_the_list(tmp_path, clock, monkeypatch):
    monkeypatch.setenv("PILOT_DASHBOARD_HOSTS", "pilot.home, other.lan")
    monkeypatch.setenv("PILOT_PUBLIC_URL", "http://gp.example.lan:8780")
    app, _ = viewer(tmp_path, clock)

    async def go():
        async with client(app) as c:
            for h in ("pilot.home:8780", "other.lan", "gp.example.lan:8780"):
                assert (await c.get("/status", headers={"Host": h, "X-Pilot-Key": KEY})).status == 200, h
    asyncio.run(go())


def test_public_url_redirects_page_navigations_to_the_canonical_host(tmp_path, clock, monkeypatch):
    monkeypatch.setenv("PILOT_PUBLIC_URL", "http://192.168.1.76:8780")
    monkeypatch.setenv("PILOT_DASHBOARD_HOSTS", "deb-mini2")   # an allowed name on any machine
    app, auth = viewer(tmp_path, clock)

    async def go():
        r = await through_guard(auth, lan_request(app, "GET", "/?x=1", {"Accept": "text/html"}, host="deb-mini2:8780"))
        assert r.status == 308 and r.headers["Location"] == "http://192.168.1.76:8780/?x=1"
        r = await through_guard(auth, lan_request(app, "GET", "/api/campaigns", {"Accept": "application/json"},
                                                  host="deb-mini2:8780"))
        assert r.status != 308                                  # API calls are never redirected
        async with client(app) as c:                           # loopback: no redirect
            r = await c.get("/", headers={"Accept": "text/html", "X-Pilot-Key": KEY}, allow_redirects=False)
            assert r.status == 200
    asyncio.run(go())


# ---------- the store ----------

def test_store_files_are_private_and_hold_no_secrets(tmp_path, clock):
    store = A.AuthStore(tmp_path / "auth.sqlite", clock=clock)
    _, cookie = store.create_device("browser", name="x", created_via="cli", created_by="cli")
    _, token = store.create_device("script", name="w", scope="read", created_via="cli", created_by="cli")
    grant = store.create_grant("cli", words=True)                  # the words too: only their hash is kept
    assert grant["words"] and len(grant["words"].split()) == 3
    store.db.execute("PRAGMA wal_checkpoint(FULL)")
    for f in ("auth.sqlite", "auth.sqlite-wal", "auth.sqlite-shm"):
        assert stat.S_IMODE((tmp_path / f).stat().st_mode) == 0o600, f
    raw = b"".join((tmp_path / f).read_bytes() for f in ("auth.sqlite", "auth.sqlite-wal"))
    for secret in (cookie.split(".")[2], token.split(".")[1], grant["link"].split(".")[1], grant["words"]):
        assert secret.encode() not in raw, secret


def test_a_corrupt_store_is_moved_aside_and_an_empty_one_starts(tmp_path, clock, caplog):
    path = tmp_path / "auth.sqlite"
    path.write_bytes(b"this is not a database" * 100)
    with caplog.at_level(logging.ERROR):
        store = A.AuthStore(path, clock=clock)
    assert store.list_devices() == []
    assert [p.name for p in tmp_path.glob("auth.sqlite.corrupt-*")]
    assert "corrupt" in caplog.text


def test_a_revoke_by_the_cli_applies_on_the_next_request(tmp_path, clock):
    app, auth = viewer(tmp_path, clock)
    dev, cookie = browser_cookie(auth)

    async def go():
        async with client(app, cookie) as c:
            assert (await c.get("/status")).status == 200
            cli = A.AuthStore(auth.store.path, clock=clock)                       # the CLI's own connection
            cli.revoke(dev, "revoked", by="cli")
            r = await c.get("/status")
            assert r.status == 401 and (await r.json())["error"] == "revoked"
    asyncio.run(go())


# ---------- sessions ----------

def test_revoke_answers_401_revoked_with_who_and_when(tmp_path, clock):
    app, auth = viewer(tmp_path, clock)
    _, admin_cookie = browser_cookie(auth, name="Pixel phone")
    other, other_cookie = browser_cookie(auth, name="Brave on Windows")

    async def go():
        async with client(app, admin_cookie) as a, client(app, other_cookie) as b:
            r = await a.post("/api/auth/devices", json={"action": "revoke", "id": other}, headers=origin(a))
            assert r.status == 200
            r = await b.get("/status")
            j = await r.json()
            assert r.status == 401 and j["error"] == "revoked" and j["by"] == "Pixel phone" and j["at"] == clock.t
            assert j["reason"] and j["fix"] and r.headers["WWW-Authenticate"].startswith("Bearer")
            r = await b.get("/", headers={"Accept": "text/html"}, allow_redirects=False)
            assert r.status == 303 and r.headers["Location"].startswith("/pair?")
            assert parse_qs(urlsplit(r.headers["Location"]).query)["reason"] == ["revoked"]
    asyncio.run(go())


def test_revoke_others_keeps_the_caller_and_sign_out_clears_the_cookie(tmp_path, clock):
    app, auth = viewer(tmp_path, clock)
    _, mine = browser_cookie(auth, name="mine")
    _, theirs = browser_cookie(auth, name="theirs")
    script = auth.store.create_device("script", name="w", scope="read", created_via="cli", created_by="cli")[1]

    async def go():
        async with client(app, mine) as a, client(app, theirs) as b:
            r = await a.post("/api/auth/devices", json={"action": "revoke_others"}, headers=origin(a))
            assert r.status == 200
            assert (await a.get("/status")).status == 200
            assert (await b.get("/status")).status == 401
            assert (await a.get("/status", headers={"X-Pilot-Key": script})).status == 200   # scripts are not browsers
            r = await a.post("/api/auth/devices", json={"action": "signout"}, headers=origin(a))
            assert r.status == 200
            sc = r.headers["Set-Cookie"]
            assert sc.startswith(f"{A.SESSION_COOKIE}=") and ("Max-Age=0" in sc or "expires" in sc.lower())
            c2 = client(app, mine)
            async with c2:
                r = await c2.get("/status")
                assert r.status == 401 and (await r.json())["error"] == "revoked"
    asyncio.run(go())
    assert {r["event"] for r in auth.store.audit_rows()} >= {"revoke_others", "signed_out"}


def test_a_browser_unseen_for_180_days_is_signed_out_idle(tmp_path, clock):
    app, auth = viewer(tmp_path, clock)
    _, cookie = browser_cookie(auth)

    async def go():
        async with client(app, cookie) as c:
            clock.t += 179 * DAY
            assert (await c.get("/status")).status == 200
            clock.t += 181 * DAY
            r = await c.get("/status")
            assert r.status == 401 and (await r.json())["error"] == "idle"
    asyncio.run(go())


def test_cookie_is_resent_weekly_and_last_seen_written_every_5_minutes(tmp_path, clock):
    app, auth = viewer(tmp_path, clock)
    dev, cookie = browser_cookie(auth)

    async def go():
        async with client(app, cookie) as c:
            r = await c.get("/status")
            assert "Set-Cookie" not in r.headers
            seen = auth.store.device(dev)["last_seen_at"]
            clock.t += 120
            await c.get("/status")
            assert auth.store.device(dev)["last_seen_at"] == seen          # within 5 min: no write
            clock.t += 200
            await c.get("/status")
            assert auth.store.device(dev)["last_seen_at"] == clock.t
            clock.t += 7 * DAY + 1
            r = await c.get("/status")
            sc = r.headers.get("Set-Cookie", "")
            assert sc.startswith(f"{A.SESSION_COOKIE}=s1.") and "Max-Age=34560000" in sc
            assert "HttpOnly" in sc and "SameSite=Lax" in sc and "Secure" not in sc
            r = await c.get("/status")
            assert "Set-Cookie" not in r.headers
    asyncio.run(go())


def test_two_addresses_within_10_minutes_get_a_badge_and_a_notice(tmp_path, clock):
    app, auth = viewer(tmp_path, clock)
    dev, cookie = browser_cookie(auth, name="Pixel phone")
    _, other = browser_cookie(auth, name="Chrome on Windows")

    async def go():
        r = await through_guard(auth, lan_request(app, "GET", "/status", {"Cookie": f"{A.SESSION_COOKIE}={cookie}"},
                                                  ip="192.168.1.140"))
        assert r.status == 200
        clock.t += 300
        r = await through_guard(auth, lan_request(app, "GET", "/status", {"Cookie": f"{A.SESSION_COOKIE}={cookie}"},
                                                  ip="192.168.1.203"))
        assert r.status == 200
        async with client(app, other) as c:
            devices = (await (await c.get("/api/auth/devices")).json())["devices"]
            me = await (await c.get("/api/auth/me")).json()
        row = next(d for d in devices if d["id"] == dev)
        assert "used from two addresses" in row["badges"]
        assert any(n["kind"] == "two_addresses" and "Pixel phone" in n["text"] for n in me["notices"])
    asyncio.run(go())


def test_forwarded_stream_closes_within_one_keepalive_after_a_revoke(tmp_path, clock):
    runs = tmp_path / "runs"
    log = EventLog(runs, "run1", "m")
    log.emit("run_start", model="m")         # the run's row in the store, as a real run records it

    async def status(_):
        return web.json_response({"run_id": "run1", "status": "playing"})

    async def events(request):
        resp = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
        await resp.prepare(request)
        try:
            while True:
                await resp.write(b": keepalive\n\n")
                await asyncio.sleep(0.05)
        except (ConnectionResetError, asyncio.CancelledError):
            pass
        return resp

    async def go():
        live = web.Application()
        live.router.add_get("/status", status)
        live.router.add_get("/events", events)
        server = TestServer(live)
        await server.start_server()
        log.state.info["port"] = server.port
        log.state.status = "playing"
        log.emit("status")
        app, auth = viewer(tmp_path, clock)
        dev, cookie = browser_cookie(auth)
        async with client(app, cookie) as c:
            r = await c.get("/events")
            assert r.status == 200
            await r.content.readany()
            auth.store.revoke(dev, "revoked", by="cli")
            loop = asyncio.get_running_loop()
            t0 = loop.time()
            while not r.content.at_eof():
                await asyncio.wait_for(r.content.readany(), 2)
            assert loop.time() - t0 < 1.0
        await server.close()
    asyncio.run(go())
    log.close()


def test_me_names_the_device_and_how_it_signed_in(tmp_path, clock):
    app, auth = viewer(tmp_path, clock)
    dev, cookie = browser_cookie(auth, name="Chrome on Windows")

    async def go():
        async with client(app, cookie) as c:
            me = await (await c.get("/api/auth/me")).json()
        assert me["via"] == "cookie" and me["device"]["id"] == dev and me["device"]["name"] == "Chrome on Windows"
        assert me["device"]["kind"] == "browser" and me["device"]["legacy"] is False
        assert "notices" in me and "add_device" in me
    asyncio.run(go())


def test_rename_is_trimmed_to_60_characters(tmp_path, clock):
    app, auth = viewer(tmp_path, clock)
    dev, cookie = browser_cookie(auth)

    async def go():
        async with client(app, cookie) as c:
            r = await c.post("/api/auth/devices", json={"action": "rename", "id": dev, "name": "  " + "x" * 80},
                             headers=origin(c))
            assert r.status == 200
    asyncio.run(go())
    assert auth.store.device(dev)["name"] == "x" * 60


# ---------- CSRF ----------

def test_mutations_need_json_a_matching_origin_and_same_site(tmp_path, clock):
    app, auth = viewer(tmp_path, clock)
    _, cookie = browser_cookie(auth)

    async def go():
        async with client(app, cookie) as c:
            o = origin(c)
            r = await c.post("/control", data="action=pause", headers={**o, "Content-Type": "application/x-www-form-urlencoded"})
            assert r.status == 403
            r = await c.post("/control", data='{"action":"pause"}', headers={**o, "Content-Type": "text/plain"})
            assert r.status == 403 and (await r.json())["error"] == "json_only"
            assert (await c.post("/api/settings", json={}, headers={"Origin": "http://evil.example"})).status == 403
            assert (await c.post("/api/settings", json={}, headers={"Origin": "null"})).status == 403
            r = await c.post("/api/settings", json={}, headers={**o, "Sec-Fetch-Site": "cross-site"})
            assert r.status == 403
            r = await c.post("/api/settings", json={})                          # a cookie and no Origin
            assert r.status == 403 and (await r.json())["error"] == "origin_required"
            assert (await c.post("/api/settings", json={"rotate": False}, headers=o)).status == 200
            r = await c.post("/api/settings", json={"rotate": False}, headers={**o, "Sec-Fetch-Site": "same-origin"})
            assert r.status == 200
        async with client(app) as c:                                             # a script on the controller
            r = await c.post("/api/settings", json={"rotate": False}, headers={"X-Pilot-Key": KEY})
            assert r.status == 200
            r = await c.options("/api/settings", headers={"X-Pilot-Key": KEY, "Origin": "http://evil.example",
                                                          "Access-Control-Request-Method": "POST"})
            assert not [h for h in r.headers if h.lower().startswith("access-control-")]
    asyncio.run(go())


# ---------- next ----------

@pytest.mark.parametrize("given,want", [
    ("/", "/"), ("/#tab=strategy", "/#tab=strategy"), ("/?campaign=civ6%2Fk#tab=talk", "/?campaign=civ6%2Fk#tab=talk"),
    ("//evil", "/"), ("/\\evil", "/"), ("https://evil", "/"), ("javascript:alert(1)", "/"), ("/%0d%0a", "/"),
    ("/\r\nSet-Cookie:x", "/"), ("/pair?next=/", "/"), ("/pair", "/"), ("/?key=x#t", "/#t"), ("/?a=1&key=x", "/"),
    ("", "/"), (None, "/"), ("status", "/")])
def test_next_stays_on_the_dashboard(given, want):
    assert A.safe_next(given) == want


# ---------- carry-over of the old key cookie ----------

def test_old_cookie_on_the_page_becomes_one_device(tmp_path, clock):
    app, auth = viewer(tmp_path, clock)

    async def go():
        async with client(app, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/140 Safari/537"}) as c:
            c.session.cookie_jar.update_cookies({A.LEGACY_COOKIE: KEY})
            r = await c.get("/", headers={"Accept": "text/html"})
            assert r.status == 200
            cookies = r.headers.getall("Set-Cookie")
            assert any(x.startswith(f"{A.SESSION_COOKIE}=s1.") for x in cookies)
            assert any(x.startswith(f"{A.LEGACY_COOKIE}=") and ("Max-Age=0" in x or "expires" in x.lower()) for x in cookies)
            assert all(KEY not in x for x in cookies)
            me = await (await c.get("/api/auth/me")).json()
            assert me["via"] == "cookie" and me["device"]["legacy"] is True
            assert any(n["kind"] == "carried_over" for n in me["notices"])
    asyncio.run(go())
    devs = auth.store.list_devices()
    assert len(devs) == 1 and devs[0]["created_via"] == "legacy_cookie" and devs[0]["legacy"] == 1
    assert devs[0]["name"] == "Chrome on Windows"


def test_old_cookie_parallel_page_load_makes_exactly_one_device(tmp_path, clock):
    app, auth = viewer(tmp_path, clock)

    async def go():
        async with client(app) as c:
            c.session.cookie_jar.update_cookies({A.LEGACY_COOKIE: KEY})
            rs = await asyncio.gather(c.get("/", headers={"Accept": "text/html"}), c.get("/status"),
                                      c.get("/frame.jpg"), c.get("/events"), c.get("/runs"))
            assert rs[0].status == 200 and rs[1].status == 200
    asyncio.run(go())
    assert len(auth.store.list_devices()) == 1


def test_old_cookie_alone_on_the_api_works_and_makes_no_device(tmp_path, clock):
    app, auth = viewer(tmp_path, clock)

    async def go():
        async with client(app) as c:
            c.session.cookie_jar.update_cookies({A.LEGACY_COOKIE: KEY})
            r = await c.get("/status")
            assert r.status == 200 and "Set-Cookie" not in r.headers
            me = await (await c.get("/api/auth/me")).json()
            assert me["via"] == "legacy_cookie"
            r = await c.post("/control", json={"action": "pause"}, headers=origin(c))
            assert r.status != 401                    # open tabs keep their controls until they reload
    asyncio.run(go())
    assert auth.store.list_devices() == []


def _deletes(r, name) -> bool:
    return any(x.startswith(f"{name}=") and "Max-Age=0" in x for x in r.headers.getall("Set-Cookie", []))


@pytest.mark.parametrize("how", ["revoked", "conflict", "garbage"])
def test_the_old_cookie_never_outlives_a_sign_in(tmp_path, clock, how):
    """A browser that signed in at /pair while it still held the old key cookie loses that cookie on
    its next request; and once its session is signed out, the old cookie does not bring it back in
    (no legacy principal, no new carried-over device) even inside the 72 hours."""
    app, auth = viewer(tmp_path, clock)
    dev, cookie = browser_cookie(auth)
    if how == "garbage":
        cookie = "s1.0123456789." + "x" * 43

    async def go():
        async with client(app) as c:
            c.session.cookie_jar.update_cookies({A.LEGACY_COOKIE: KEY, A.SESSION_COOKIE: cookie})
            if how != "garbage":
                r = await c.get("/status")
                assert r.status == 200 and _deletes(r, A.LEGACY_COOKIE)
                c.session.cookie_jar.update_cookies({A.LEGACY_COOKIE: KEY})       # as if it had kept it
                auth.store.revoke(dev, how, by="cli")
            r = await c.get("/", headers={"Accept": "text/html"}, allow_redirects=False)
            assert r.status == 303 and r.headers["Location"].startswith("/pair?")
            assert "pilot_session=s1." not in r.headers.get("Set-Cookie", "") and _deletes(r, A.LEGACY_COOKIE)
            c.session.cookie_jar.update_cookies({A.LEGACY_COOKIE: KEY})
            r = await c.get("/status")
            assert r.status == 401 and (await r.json())["error"] == ("sign_in_required" if how == "garbage" else how)
    asyncio.run(go())
    assert [d["id"] for d in auth.store.list_devices()] == ([dev] if how == "garbage" else [])


def test_signing_in_deletes_the_old_cookie(tmp_path, clock):
    app, auth = viewer(tmp_path, clock)
    g = auth.store.create_grant("cli", words=True)

    async def go():
        async with client(app) as c:
            c.session.cookie_jar.update_cookies({A.LEGACY_COOKIE: KEY})
            r = await c.post("/pair", json={"words": g["words"]}, headers=origin(c))
            assert r.status == 200 and _deletes(r, A.LEGACY_COOKIE)
    asyncio.run(go())


def test_old_link_inside_the_window_becomes_a_one_tap_sign_in(tmp_path, clock):
    app, auth = viewer(tmp_path, clock)

    async def go():
        async with client(app) as c:
            r = await c.get(f"/?key={KEY}", allow_redirects=False)
            assert r.status == 303 and "Set-Cookie" not in r.headers
            loc = r.headers["Location"]
            assert loc.startswith("/pair#c=") and KEY not in loc
            gid = loc.split("#c=")[1].split(".")[0]
            assert auth.store.grant(gid)["created_by"] == "legacy_link"
            r = await c.get("/?key=wrong", allow_redirects=False)
            assert r.status == 303 and r.headers["Location"] == "/pair?reason=old_link"
        assert auth.throttle.failures(A.bucket_of("127.0.0.1")) == 1
        _, cookie = browser_cookie(auth)
        async with client(app, cookie) as c:            # signed in already: the key just leaves the address bar
            r = await c.get(f"/?key={KEY}", allow_redirects=False)
            assert r.status == 303 and r.headers["Location"] == "/"
    asyncio.run(go())
    assert len([g for g in auth.store.grants() if g["created_by"] == "legacy_link"]) == 1


@pytest.mark.parametrize("end", ["72 hours", "rotation"])
def test_after_the_window_the_old_cookie_is_deleted_and_key_links_are_never_read(tmp_path, clock, end, monkeypatch):
    app, auth = viewer(tmp_path, clock)
    if end == "72 hours":
        clock.t += 72 * 3600 + 1
    else:
        monkeypatch.setattr(auth.keys, "get", lambda: "rotated" * 6)

    compared: list = []
    real = A.hmac.compare_digest
    monkeypatch.setattr(A.hmac, "compare_digest", lambda a, b: compared.append(1) or real(a, b))

    async def go():
        async with client(app) as c:
            c.session.cookie_jar.update_cookies({A.LEGACY_COOKIE: KEY})
            r = await c.get("/", headers={"Accept": "text/html"}, allow_redirects=False)
            assert r.status == 303 and r.headers["Location"].startswith("/pair?")
            assert parse_qs(urlsplit(r.headers["Location"]).query)["reason"] == ["old_link"]
            sc = r.headers.getall("Set-Cookie")
            assert any(x.startswith(f"{A.LEGACY_COOKIE}=") and ("Max-Age=0" in x or "expires" in x.lower()) for x in sc)
            r = await c.get("/status")
            assert r.status == 401
            c.session.cookie_jar.clear()
            compared.clear()
            replies = set()
            for v in (KEY, "wrong", "x"):
                r = await c.get(f"/?key={v}", allow_redirects=False)
                replies.add((r.status, r.headers["Location"]))
            assert replies == {(303, "/pair?reason=old_link")} and not compared
    asyncio.run(go())
    assert auth.store.list_devices() == []


# ---------- headers, 401 shape, logs ----------

def test_every_response_carries_the_security_headers(tmp_path, clock):
    app, _ = viewer(tmp_path, clock)

    async def go():
        async with client(app) as c:
            for path, hdr in (("/", {"X-Pilot-Key": KEY}), ("/status", {}), ("/nope", {"X-Pilot-Key": KEY}),
                              ("/runs", {"X-Pilot-Key": KEY}), ("/status", {"Host": "evil.example"})):
                r = await c.get(path, headers=hdr, allow_redirects=False)
                h = r.headers
                assert h["Cache-Control"] == "no-store", path
                assert h["X-Frame-Options"] == "DENY" and "frame-ancestors 'none'" in h["Content-Security-Policy"]
                assert h["X-Content-Type-Options"] == "nosniff" and h["Referrer-Policy"] == "same-origin", path
    asyncio.run(go())


def test_api_401s_are_json_and_page_navigations_go_to_sign_in(tmp_path, clock):
    app, _ = viewer(tmp_path, clock)

    async def go():
        async with client(app) as c:
            for path in ("/status", "/runs", "/api/campaigns", "/api/pc", "/api/models", "/events.json", "/frame.jpg",
                         "/events", "/runs/run1/events", "/runs/run1/trace/1", "/runs/run1/frame.jpg", "/api/auth/me"):
                r = await c.get(path)
                assert r.status == 401, path
                j = await r.json()
                assert j["error"] == "sign_in_required" and j["reason"] and j["fix"], path
                assert r.headers["WWW-Authenticate"] == 'Bearer realm="Game Pilot"'
            for path in ("/control", "/api/settings", "/api/run", "/api/auth/devices"):
                assert (await c.post(path, json={"action": "pause"})).status == 401, path
            r = await c.get("/?campaign=civ6%2Fk", allow_redirects=False)
            assert r.status == 303
            q = parse_qs(urlsplit(r.headers["Location"]).query)
            assert urlsplit(r.headers["Location"]).path == "/pair" and q["reason"] == ["sign_in_required"]
            assert parse_qs(urlsplit(q["next"][0]).query) == {"campaign": ["civ6/k"]}
    asyncio.run(go())


def test_no_secret_reaches_a_log_a_location_or_a_page(tmp_path, clock, caplog):
    app, auth = viewer(tmp_path, clock)
    seen: list[str] = []

    async def go():
        async with client(app, headers={"User-Agent": "Mozilla/5.0 (Linux; Android 14; Pixel 7) Chrome/140 Mobile"}) as c:
            c.session.cookie_jar.update_cookies({A.LEGACY_COOKIE: KEY})
            for path in (f"/?key={KEY}", "/", "/status", "/api/auth/me", "/api/auth/devices"):
                r = await c.get(path, allow_redirects=False, headers={"Accept": "text/html"})
                seen.extend([*r.headers.getall("Set-Cookie", []), r.headers.get("Location", ""), await r.text()])
            r = await c.post("/api/auth/devices", json={"action": "signout"}, headers=origin(c))
            seen.extend(r.headers.getall("Set-Cookie", []))
            r = await c.get("/status", headers={"X-Pilot-Key": KEY + "x"})
            seen.append(await r.text())
            r = await through_guard(auth, lan_request(app, "GET", "/status", {"X-Pilot-Key": KEY}))
            seen.append(r.text)

    with caplog.at_level(logging.DEBUG):
        asyncio.run(go())
    sessions = [d["id"] for d in auth.store.list_devices(include_revoked=True)]
    assert sessions
    text = caplog.text + "\n".join(str(x) for x in seen)
    assert KEY not in text
    assert "s1." + sessions[0] + "." not in caplog.text


def test_audit_rows_aggregate_per_event_address_and_minute(tmp_path, clock):
    store = A.AuthStore(tmp_path / "auth.sqlite", clock=clock)
    for _ in range(100):
        store.audit("signin_failed", ip=LAN, detail={"how": "words"})
    clock.t += 61
    store.audit("signin_failed", ip=LAN)
    rows = [r for r in store.audit_rows() if r["event"] == "signin_failed"]
    assert sorted(r["count"] for r in rows) == [1, 100]


def test_viewer_startup_line_has_no_key(tmp_path, monkeypatch, capsys):
    from aiohttp import web as aioweb

    from pilot import cli
    monkeypatch.setenv("PILOT_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setattr(aioweb, "run_app", lambda *a, **kw: None)
    assert cli.main(["view", "--port", "8781"]) == 0
    out = capsys.readouterr().out
    assert "key=" not in out and os.environ["PILOT_DASHBOARD_KEY"] not in out
    assert ":8781/" in out and "dashboard-link" in out


def test_legacy_window_is_recorded_once_at_the_first_start(tmp_path, clock):
    runs = tmp_path / "runs"
    runs.mkdir()
    a1 = A.Auth.from_env(runs, key=KEY, clock=clock)
    until = float(a1.store.meta("legacy_until"))
    assert until == clock.t + 72 * 3600
    assert a1.store.meta("legacy_key_fp") == hashlib.sha256(KEY.encode()).hexdigest()
    clock.t += 3600
    a2 = A.Auth.from_env(runs, key=KEY, clock=clock)            # a restart does not extend it
    assert float(a2.store.meta("legacy_until")) == until


def test_the_dashboard_page_runs_only_its_own_inline_script(tmp_path, clock):
    """script-src names the page's one inline script by hash: an injected handler or import() fails."""
    import base64
    import re
    page = (A.STATIC / "dashboard.html").read_text(encoding="utf-8")
    want = {f"'sha256-{base64.b64encode(hashlib.sha256(s.encode()).digest()).decode()}'"
            for s in re.findall(r"<script>(.*?)</script>", page, re.DOTALL)}
    assert len(want) == 1
    app, _ = viewer(tmp_path, clock)
    live_log = EventLog(tmp_path / "live", "run1", "m")
    live = make_app(type("P", (), {"log": live_log})(), key=KEY)

    async def go():
        for a in (app, live):
            async with client(a) as c:
                r = await c.get("/", headers={"X-Pilot-Key": KEY})
                assert r.status == 200
                csp = r.headers["Content-Security-Policy"]
                src = re.search(r"script-src ([^;]*)", csp).group(1).split()
                assert set(src) == want, csp
                assert "frame-ancestors 'none'" in csp and "object-src 'none'" in csp and "base-uri 'none'" in csp
                assert (await r.text()) == page
    asyncio.run(go())
    live_log.close()


@pytest.mark.parametrize("how", ["corrupt", "deleted", "new_path"])
def test_the_carry_over_window_survives_a_new_store(tmp_path, clock, monkeypatch, how):
    """The 72 hours are counted from the first start of this code, not of this store: a store moved
    aside as corrupt, deleted or pointed elsewhere (PILOT_AUTH_DB) neither reopens a closed window
    nor extends an open one (runs/secrets/dashboard.carryover keeps the deadline)."""
    monkeypatch.delenv("PILOT_AUTH_DB", raising=False)
    runs = tmp_path / "runs"
    runs.mkdir()
    a1 = A.Auth.from_env(runs, key=KEY, clock=clock)
    until = float(a1.store.meta("legacy_until"))
    assert stat.S_IMODE((runs / "secrets/dashboard.carryover").stat().st_mode) == 0o600

    def new_store():
        a1.store.db.close()
        db = runs / "auth.sqlite"
        if how == "new_path":
            monkeypatch.setenv("PILOT_AUTH_DB", str(tmp_path / f"elsewhere-{clock.t}" / "auth.sqlite"))
            return
        for p in runs.glob("auth.sqlite*"):
            p.unlink()
        if how == "corrupt":
            db.write_bytes(b"this is not a database" * 100)

    clock.t += 3600
    new_store()
    a2 = A.Auth.from_env(runs, key=KEY, clock=clock)
    assert a2.legacy_open() and float(a2.store.meta("legacy_until")) == until      # not extended
    clock.t += 72 * 3600
    a1 = a2
    new_store()
    a3 = A.Auth.from_env(runs, key=KEY, clock=clock)
    assert not a3.legacy_open()                                                     # not reopened


def test_a_recreated_store_without_a_record_of_the_window_keeps_it_shut(tmp_path, clock, monkeypatch):
    monkeypatch.delenv("PILOT_AUTH_DB", raising=False)
    runs = tmp_path / "runs"
    runs.mkdir()
    a1 = A.Auth.from_env(runs, key=KEY, clock=clock)
    a1.store.db.close()
    (runs / "secrets/dashboard.carryover").unlink()
    (runs / "auth.sqlite").write_bytes(b"this is not a database" * 100)
    for p in runs.glob("auth.sqlite-*"):
        p.unlink()
    a2 = A.Auth.from_env(runs, key=KEY, clock=clock)
    assert a2.store.recreated and not a2.legacy_open()


def test_the_conflict_notice_lasts_24_hours_whatever_the_network_logs(tmp_path, clock):
    """Anyone on the LAN adds audit rows without signing in (bad Host names, wrong words); 100 minutes
    of that must not push ruling 42's warning out of /api/auth/me before its 24 hours are up."""
    app, auth = viewer(tmp_path, clock)
    _, cookie = browser_cookie(auth)
    auth.store.audit("grant_conflict", "192.168.1.203", None, {"grant": "g1", "device": "Brave on Windows"})
    for _ in range(100):
        clock.t += 60
        auth.store.audit("host_refused", "192.168.1.9", detail={"host": "evil.example"})
        auth.store.audit("signin_failed", "192.168.1.9", detail={"how": "words"})

    async def go():
        async with client(app, cookie) as c:
            first = (await (await c.get("/api/auth/me")).json())["notices"]
            clock.t += A.NOTICE_S
            return first, (await (await c.get("/api/auth/me")).json())["notices"]
    first, later = asyncio.run(go())
    assert any(n["kind"] == "conflict" and "192.168.1.203" in n["text"] for n in first)
    assert not any(n["kind"] == "conflict" for n in later)


def test_one_address_cannot_flood_the_audit(tmp_path, clock, monkeypatch):
    """Failures from one address add at most a few rows an hour (later ones only raise a count), and
    when the table is over its limit the network's noise goes before real events."""
    store = A.AuthStore(tmp_path / "auth.sqlite", clock=clock)
    store.audit("signin", "192.168.1.77", "abcdef0123", {"how": "link"})
    for _ in range(120):                                     # two hours, two noise rows a minute
        clock.t += 60
        store.audit("host_refused", "192.168.1.9")
        store.audit("signin_failed", "192.168.1.9")
    rows = [r for r in store.audit_rows(10_000) if r["ip"] == "192.168.1.9"]
    assert len(rows) <= 2 * A.AUDIT_PER_IP_HOUR + 2
    assert sum(r["count"] for r in rows) == 240                # nothing lost from the counts
    monkeypatch.setattr(A, "AUDIT_MAX_ROWS", 10)
    for i in range(40):                                      # many addresses, one row each
        store.audit("host_refused", f"192.168.2.{i}")
    store.audit("grant_conflict", "192.168.1.203", None, {"grant": "g1"})
    store.housekeeping()
    left = store.audit_rows(10_000)
    assert len(left) <= 10
    assert {"signin", "grant_conflict"} <= {r["event"] for r in left}


def test_a_carried_over_browser_is_no_new_device_to_the_others(tmp_path, clock):
    """Flow 1: on deploy day Chrome and the phone carry over, and each is told once about its own sign-in;
    neither is announced to the other as "New device signed in" (only devices signed in with a code are).
    Notices name their device, so the page can fold several into one line."""
    app, auth = viewer(tmp_path, clock)
    store = auth.store
    chrome, _ = store.create_device("browser", name="Chrome on Windows", created_via="legacy_cookie",
                                    created_by="legacy_link", ip="192.168.1.77", legacy=True)
    _, phone_cookie = store.create_device("browser", name="Chrome on Android", created_via="legacy_cookie",
                                         created_by="legacy_link", ip="127.0.0.1", legacy=True)
    g = store.create_grant(chrome["id"], words=True)
    store.redeem("words", g["words"], ip="192.168.1.77", name="Brave on Windows")

    async def go():
        async with client(app, phone_cookie) as c:
            return (await (await c.get("/api/auth/me")).json())["notices"]
    notices = asyncio.run(go())
    assert [n["kind"] for n in notices] == ["carried_over", "new_device"], notices
    assert notices[1]["device"] == "Brave on Windows" and notices[0]["device"] == "Chrome on Android"


@pytest.mark.parametrize("has_qr", [True, False])
def test_viewer_startup_says_when_qr_codes_are_off(tmp_path, monkeypatch, capsys, caplog, has_qr):
    """segno missing from the deployed Python means no QR code in Add a device: `view` says so loudly at
    start (stdout for the journal, and a warning in the log), with the fix."""
    from aiohttp import web as aioweb

    from pilot import cli
    monkeypatch.setenv("PILOT_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setattr(aioweb, "run_app", lambda *a, **kw: None)
    monkeypatch.setattr(A, "qr_available", lambda: has_qr)
    with caplog.at_level(logging.WARNING):
        assert cli.main(["view", "--port", "8781"]) == 0
    out = capsys.readouterr().out
    assert ("segno" in out and "pip install segno" in out and "QR" in caplog.text) is (not has_qr)
