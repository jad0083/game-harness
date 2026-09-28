"""The dashboard behind nginx-proxy-manager and Authelia (gamepilot.saczone.com): a request from a
trusted proxy address that carries the shared proxy secret and Authelia's Remote-User is that user,
signed in once through Authelia; anything else is an ordinary request that needs its own sign-in.

The authkit LAN address, 192.168.1.50, is also NPM's address; nothing is trusted unless
PILOT_TRUSTED_PROXIES and PILOT_PROXY_SECRET are set."""

from __future__ import annotations

import asyncio

import pytest
from authkit import LAN, body, lan_request, viewer

from pilot import auth as A

SECRET = "s" * 40
HOST = "gamepilot.saczone.com"


def _env(monkeypatch):
    monkeypatch.setenv("PILOT_TRUSTED_PROXIES", LAN)
    monkeypatch.setenv("PILOT_PROXY_SECRET", SECRET)
    monkeypatch.setenv("PILOT_PUBLIC_URL", f"https://{HOST}")


def _req(app, method="GET", path="/api/auth/me", headers=None, ip=LAN):
    return lan_request(app, method, path, {"X-Forwarded-Proto": "https", "Accept": "application/json",
                                           **(headers or {})}, ip=ip, host=HOST)


async def _who(auth, request):
    async def handler(req):
        p = req[A.PRINCIPAL]
        return A.web.json_response({"kind": p.kind, "name": p.name, "via": p.via})
    try:
        return await auth.middleware(request, handler)
    except A.web.HTTPException as e:
        return e


def test_an_authelia_user_through_the_proxy_is_signed_in(tmp_path, clock, monkeypatch):
    _env(monkeypatch)
    app, auth = viewer(tmp_path, clock)
    r = asyncio.run(_who(auth, _req(app, headers={"X-Pilot-Proxy": SECRET, "Remote-User": "jad"})))
    assert r.status == 200 and body(r) == {"kind": "proxy", "name": "jad", "via": "proxy"}


@pytest.mark.parametrize("headers,ip", [
    ({"Remote-User": "jad"}, LAN),                                    # no proxy secret
    ({"X-Pilot-Proxy": "not-the-secret", "Remote-User": "jad"}, LAN),  # a wrong one
    ({"X-Pilot-Proxy": SECRET, "Remote-User": ""}, LAN),              # Authelia named nobody
    ({"X-Pilot-Proxy": SECRET}, LAN),
    ({"X-Pilot-Proxy": SECRET, "Remote-User": "jad"}, "192.168.1.99"),  # not the proxy's address
])
def test_anything_else_is_an_ordinary_request(tmp_path, clock, monkeypatch, headers, ip):
    _env(monkeypatch)
    app, auth = viewer(tmp_path, clock)
    r = asyncio.run(_who(auth, _req(app, headers=headers, ip=ip)))
    assert r.status == 401 and body(r)["error"] == "sign_in_required"


def test_without_configuration_nothing_is_trusted(tmp_path, clock, monkeypatch):
    monkeypatch.setenv("PILOT_PUBLIC_URL", f"https://{HOST}")
    monkeypatch.setenv("PILOT_PROXY_SECRET", SECRET)        # a secret alone trusts no address
    app, auth = viewer(tmp_path, clock)
    r = asyncio.run(_who(auth, _req(app, headers={"X-Pilot-Proxy": SECRET, "Remote-User": "jad"})))
    assert r.status == 401


def test_changes_through_the_proxy_need_a_matching_origin(tmp_path, clock, monkeypatch):
    _env(monkeypatch)
    app, auth = viewer(tmp_path, clock)
    hdr = {"X-Pilot-Proxy": SECRET, "Remote-User": "jad", "Content-Type": "application/json"}

    async def go():
        r = await _who(auth, _req(app, "POST", "/control", hdr))
        assert r.status == 403 and body(r)["error"] == "origin_required"
        r = await _who(auth, _req(app, "POST", "/control", {**hdr, "Origin": "https://evil.example"}))
        assert r.status == 403
        r = await _who(auth, _req(app, "POST", "/control", {**hdr, "Origin": f"https://{HOST}"}))
        assert r.status == 200 and body(r)["kind"] == "proxy"
    asyncio.run(go())


def test_https_is_read_from_the_trusted_proxy_only(tmp_path, clock, monkeypatch):
    _env(monkeypatch)
    app, auth = viewer(tmp_path, clock)
    assert auth.is_secure(_req(app)) is True
    assert auth.is_secure(_req(app, ip="192.168.1.99")) is False, "a LAN client cannot claim HTTPS"
    assert auth.is_secure(lan_request(app, "GET", "/", {}, ip=LAN, host=HOST)) is False, "no X-Forwarded-Proto"


def test_event_streams_ask_the_proxy_not_to_buffer():
    """nginx buffers a proxied response by default, which would hold the live stream's events back;
    X-Accel-Buffering: no turns that off for this response whatever the proxy host's config."""
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent / "src" / "pilot" / "dashboard.py").read_text()
    streams = src.count('"Content-Type": "text/event-stream"')
    assert streams >= 2 and src.count('"X-Accel-Buffering": "no"') == streams
