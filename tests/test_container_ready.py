"""What a container needs from the dashboard (appliance image design, rulings 3, 7 and 9)."""

from __future__ import annotations

import asyncio

from aiohttp.test_utils import TestClient, TestServer

from pilot.auth import Auth, allowed_host
from pilot.dashboard import make_app, pc_status
from pilot.store import open_store

KEY = "k" * 48


def test_healthz_is_public_and_says_nothing(tmp_path):
    async def go():
        auth = Auth.from_env(tmp_path, key=KEY)
        app = make_app(None, tmp_path, open_store(tmp_path), key=KEY, auth=auth)
        async with TestClient(TestServer(app)) as c:
            r = await c.get("/healthz")
            assert r.status == 200 and (await r.text()) == "ok"
            r = await c.get("/runs", allow_redirects=False)
            assert r.status in (302, 303, 401)              # everything else still needs a sign-in
    asyncio.run(go())


def test_pc_status_not_configured(monkeypatch):
    monkeypatch.delenv("GAME_AGENT_URL", raising=False)
    assert pc_status() == {"online": False, "state": "not_configured", "host": "", "error": "set GAME_AGENT_URL"}


def test_the_public_hostname_and_loopback_are_allowed():
    # NPM forwards Host: gamepilot.saczone.com; the healthcheck calls 127.0.0.1:8780 (planning ruling P1)
    assert allowed_host("gamepilot.saczone.com", frozenset({"gamepilot.saczone.com"}))
    assert allowed_host("127.0.0.1:8780")
    assert not allowed_host("evil.example")
