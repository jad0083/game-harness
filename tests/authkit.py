"""Shared helpers for the dashboard sign-in tests (a viewer with an injected clock, clients with the
production runner settings, requests from a LAN peer through make_mocked_request)."""

from __future__ import annotations

import json
from unittest import mock

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer, make_mocked_request

from pilot import auth as A
from pilot.dashboard import make_app

KEY = "K" * 43
NO_KEY: dict = {}
LAN = "192.168.1.50"
DAY = 86400


class Clock:
    def __init__(self):
        self.t = 1_800_000_000.0

    def __call__(self):
        return self.t


def viewer(tmp_path, clock, key=KEY, **kw):
    runs = tmp_path / "runs"
    runs.mkdir(exist_ok=True)
    auth = A.Auth.from_env(runs, key=key, clock=clock, keepalive_s=0.1, **kw)
    return make_app(None, runs, key=key, auth=auth), auth


def browser_cookie(auth, name="Chrome on Windows", ip="127.0.0.1") -> tuple[str, str]:
    row, cred = auth.store.create_device("browser", name=name, created_via="cli", created_by="cli", ip=ip)
    return row["id"], cred


class ProdServer(TestServer):
    """A test server with the production runner settings (no access log: request lines can carry an
    old ?key=)."""

    async def start_server(self, loop=None, **kw):
        await super().start_server(loop, **{**A.RUNNER_KWARGS, **kw})


def client(app, cookie: str | None = None, **kw) -> TestClient:
    c = TestClient(ProdServer(app), headers=kw.pop("headers", NO_KEY), **kw)
    if cookie:
        c.session.cookie_jar.update_cookies({A.SESSION_COOKIE: cookie})
    return c


def origin(c) -> dict:
    return {"Origin": f"http://{c.server.host}:{c.server.port}"}


def lan_request(app, method: str, path: str, headers: dict | None = None, ip: str = LAN, host: str = "192.168.1.76:8780"):
    transport = mock.Mock()
    transport.get_extra_info.side_effect = lambda k, d=None: (ip, 50000) if k == "peername" else d
    return make_mocked_request(method, path, headers={"Host": host, **(headers or {})}, transport=transport, app=app)


async def through_guard(auth, request) -> web.StreamResponse:
    async def handler(req):
        return web.json_response({"principal": req[A.PRINCIPAL].kind})
    try:
        return await auth.middleware(request, handler)
    except web.HTTPException as e:
        return e


def body(resp) -> dict:
    return json.loads(resp.body)


