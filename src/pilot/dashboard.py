"""Live dashboard and monitoring API (aiohttp), run in a background thread.

    GET  /            dashboard page
    GET  /status      run state as JSON (for humans and other agents)
    GET  /events      server-sent events (live feed); /events.json?n=100 for the recent list
    GET  /frame.jpg   latest frame
    POST /control     {"action": "pause"|"resume"|"stop"|"instruct", "text": "..."}
"""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path

from aiohttp import web

STATIC = Path(__file__).parent / "static"


def make_app(pilot) -> web.Application:
    log = pilot.log

    async def index(_):
        return web.FileResponse(STATIC / "dashboard.html")

    async def status(_):
        return web.json_response(log.state.as_dict(), dumps=lambda o: json.dumps(o, default=str))

    async def frame(_):
        p = log.dir / "latest.jpg"
        if not p.exists():
            raise web.HTTPNotFound()
        return web.FileResponse(p, headers={"Cache-Control": "no-store"})

    async def events_json(request):
        n = int(request.query.get("n", 100))
        return web.json_response(list(log.recent)[-n:], dumps=lambda o: json.dumps(o, default=str))

    async def events(request):
        resp = web.StreamResponse(headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"})
        await resp.prepare(request)
        q = log.subscribe(asyncio.get_running_loop())
        try:
            for ev in list(log.recent)[-50:]:
                await resp.write(f"data: {json.dumps(ev, default=str)}\n\n".encode())
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15)
                    await resp.write(f"data: {json.dumps(ev, default=str)}\n\n".encode())
                except TimeoutError:
                    await resp.write(b": keepalive\n\n")
        except (ConnectionResetError, asyncio.CancelledError):
            pass
        finally:
            log.unsubscribe(q)
        return resp

    async def control(request):
        body = await request.json()
        action = body.get("action")
        if action == "pause":
            pilot.pause()
        elif action == "resume":
            pilot.resume()
        elif action == "stop":
            pilot.stop()
        elif action == "instruct" and body.get("text", "").strip():
            pilot.instruct(body["text"].strip())
        else:
            raise web.HTTPBadRequest(text="action must be pause|resume|stop|instruct (with text)")
        return web.json_response({"ok": True, "status": log.state.status})

    app = web.Application()
    app.add_routes([web.get("/", index), web.get("/status", status), web.get("/frame.jpg", frame),
                    web.get("/events", events), web.get("/events.json", events_json), web.post("/control", control)])
    return app


def serve_in_background(pilot, host: str, port: int) -> threading.Thread:
    def run() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        runner = web.AppRunner(make_app(pilot))
        loop.run_until_complete(runner.setup())
        loop.run_until_complete(web.TCPSite(runner, host, port).start())
        loop.run_forever()

    t = threading.Thread(target=run, daemon=True, name="dashboard")
    t.start()
    return t
