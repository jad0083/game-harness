"""Helpers for the dashboard's browser tests: a fixture server in its own thread, a fake live pilot,
and browser contexts with their errors collected."""

from __future__ import annotations

import asyncio
import threading

from aiohttp import web

from pilot.events import EventLog

UI_KEY = "ui-test-dashboard-key-0123456789abcdef"
PHONE_UA = ("Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/140.0.0.0 Mobile Safari/537.36")
CONTEXTS = {
    "desktop-light": {"viewport": {"width": 1440, "height": 900}, "color_scheme": "light"},
    "desktop-dark": {"viewport": {"width": 1440, "height": 900}, "color_scheme": "dark"},
    "phone-light": {"viewport": {"width": 390, "height": 844}, "device_scale_factor": 2, "is_mobile": True,
                        "has_touch": True, "color_scheme": "light", "user_agent": PHONE_UA},
    "phone-dark": {"viewport": {"width": 390, "height": 844}, "device_scale_factor": 2, "is_mobile": True,
                       "has_touch": True, "color_scheme": "dark", "user_agent": PHONE_UA},
}


class Served:
    """An aiohttp app on 127.0.0.1:<free port>, in its own thread and event loop."""

    def __init__(self, app: web.Application):
        self.app = app
        self.loop = asyncio.new_event_loop()
        self.port = 0
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name="ui-server")
        self._thread.start()
        if not self._ready.wait(10):
            raise RuntimeError("fixture server did not start")

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.runner = web.AppRunner(self.app, shutdown_timeout=0.2)
        self.loop.run_until_complete(self.runner.setup())
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        self.loop.run_until_complete(site.start())
        self.port = site._server.sockets[0].getsockname()[1]
        self._ready.set()
        self.loop.run_forever()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def call(self, fn, *a, **kw):
        """Run fn in the server's loop (e.g. an EventLog.emit whose subscribers live there)."""
        fut = asyncio.run_coroutine_threadsafe(self._call(fn, *a, **kw), self.loop)
        return fut.result(10)

    async def _call(self, fn, *a, **kw):
        return fn(*a, **kw)

    def stop(self) -> None:
        try:
            asyncio.run_coroutine_threadsafe(self.runner.cleanup(), self.loop).result(10)
        finally:
            self.loop.call_soon_threadsafe(self.loop.stop)
            self._thread.join(10)


class FakePilot:
    """The live pilot's control surface, without a game."""

    def __init__(self, log: EventLog):
        self.log = log
        self.calls: list = []

    def pause(self):
        self.calls.append("pause")
        self.log.state.status = "paused"

    def resume(self):
        self.calls.append("resume")
        self.log.state.status = "playing"

    def stop(self):
        self.calls.append("stop")

    def instruct(self, text):
        self.calls.append(("instruct", text))
        self.log.emit("instruction", text=text)


class Watched:
    """A page with its console errors, page errors and failed requests collected."""

    def __init__(self, context, page):
        self.context, self.page = context, page
        self.errors: list[str] = []
        self.failed: list[str] = []
        self.requests: list[str] = []
        page.on("console", lambda m: self.errors.append(f"console: {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: self.errors.append(f"pageerror: {e}"))
        page.on("request", lambda r: self.requests.append(r.url))
        page.on("response", lambda r: self.failed.append(f"{r.status} {r.url}") if r.status >= 400 else None)
        page.on("requestfailed", lambda r: self.failed.append(f"failed {r.url}: {r.failure}")
                if "/events" not in r.url else None)     # the stream is cut when the page closes


def open_context(browser, name: str, base: str, *, signed_in: bool = True, **extra):
    """A fresh browser context (one of CONTEXTS) with fonts stubbed (no request leaves the box) and,
    when signed_in, the credential a signed-in browser holds."""
    ctx = browser.new_context(**{**CONTEXTS[name], **extra})
    ctx.route("https://fonts.googleapis.com/**", lambda r: r.fulfill(status=200, content_type="text/css", body=""))
    ctx.route("https://fonts.gstatic.com/**", lambda r: r.fulfill(status=200, body=b""))
    if signed_in:
        sign_in(ctx, base)
    page = ctx.new_page()
    return Watched(ctx, page)


def sign_in(ctx, base: str) -> None:
    ctx.add_cookies([{"name": "pilot_key", "value": UI_KEY, "url": base}])
