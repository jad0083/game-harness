"""Live dashboard and monitoring API (aiohttp), run in a background thread.

    GET  /            dashboard page
    GET  /status      run state as JSON (for humans and other agents)
    GET  /events      server-sent events (live feed); /events.json?n=100 for the recent list
    GET  /frame.jpg   latest frame
    POST /control     {"action": "pause"|"resume"|"stop"|"instruct", "text": "..."}

Recorded runs (live or finished; also served by `python -m pilot view` without a live pilot):
    GET  /runs                          runs, newest first
    GET  /runs/<id>/events?kind=a,b     recorded events (optionally only some kinds)
    GET  /runs/<id>/trace/<n>           decision n: prompt, thinking, tool calls, answer
    GET  /runs/<id>/frame.jpg           the run's latest frame

Telemetry (runs/telemetry.sqlite, across runs and models):
    GET  /api/campaigns                         campaigns with decision/run counts and latest date
    GET  /api/decisions?campaign=<id>|run=<id>  decisions (summary + outcome 12 months later)
    GET  /api/decision?run=<id>&episode=<n>     one decision with its full trace
    GET  /api/metrics?campaign=<id>|run=<id>    metric points over in-game time
"""

from __future__ import annotations

import asyncio
import json
import re
import threading
from pathlib import Path

from aiohttp import ClientError, ClientSession, ClientTimeout, web

STATIC = Path(__file__).parent / "static"


RUN_ID = re.compile(r"^[A-Za-z0-9_.-]+$")
LIVE_STATES = {"starting", "playing", "deciding", "paused", "needs_attention"}


class LiveProxy:
    """Finds the live pilot run (newest run whose status.json names a dashboard port that answers)."""

    def __init__(self, runs_dir: Path):
        self.runs_dir = runs_dir
        self._url: str | None = None
        self._checked = 0.0
        self._session: ClientSession | None = None

    def session(self) -> ClientSession:
        if self._session is None or self._session.closed:
            self._session = ClientSession()
        return self._session

    def forget(self) -> None:
        self._url, self._checked = None, 0.0

    async def close(self) -> None:
        if self._session:
            await self._session.close()

    async def url(self) -> str | None:
        now = asyncio.get_running_loop().time()
        if now - self._checked < 5:
            return self._url
        self._checked, self._url = now, None
        for run in list_runs(self.runs_dir):
            st = run.get("_status") or {}
            port = (st.get("info") or {}).get("port")
            if not port or st.get("status") not in LIVE_STATES:
                continue
            url = f"http://127.0.0.1:{int(port)}"
            try:
                async with self.session().get(url + "/status", timeout=ClientTimeout(total=2)) as r:
                    if r.status == 200 and (await r.json()).get("run_id") == run["id"]:
                        self._url = url
                        break
            except (OSError, TimeoutError, ClientError, ValueError):
                continue
        return self._url


def list_runs(runs_dir: Path, live_id: str | None = None) -> list[dict]:
    out = []
    dirs = [p for p in runs_dir.iterdir() if (p / "events.jsonl").exists()] if runs_dir.exists() else []
    for d in sorted(dirs, reverse=True):
        st = {}
        if (d / "status.json").exists():
            try:
                st = json.loads((d / "status.json").read_text())
            except ValueError:
                st = {}
        out.append({"id": d.name, "live": d.name == live_id, "model": st.get("model", ""), "_status": st,
                    "game": (st.get("info") or {}).get("game", ""), "decisions": st.get("episodes", 0),
                    "date": st.get("game_date", ""), "status": st.get("status", "")})
    return out


def make_app(pilot, runs_dir: Path | None = None, telemetry=None) -> web.Application:
    """Dashboard for a live `pilot` (Pilot or Governor), or read-only over `runs_dir` when pilot is None."""
    log = pilot.log if pilot else None
    runs_dir = runs_dir or (log.dir.parent if log else Path("runs"))
    tel = telemetry or (log.telemetry if log else None)

    def need_tel():
        if tel is None:
            raise web.HTTPServiceUnavailable(text="no telemetry database for this dashboard")
        return tel

    async def q(sql: str, args: tuple = ()) -> list[dict]:
        return await asyncio.to_thread(need_tel().query, sql, args)

    def scope(request) -> tuple[str, tuple]:
        if "campaign" in request.query:
            return "campaign_id=?", (request.query["campaign"],)
        if "run" in request.query:
            return "run_id=?", (request.query["run"],)
        raise web.HTTPBadRequest(text="campaign or run is required")

    async def api_campaigns(_):
        rows = await q(
            "SELECT c.id, c.game, c.name, c.created,"
            " (SELECT COUNT(*) FROM runs r WHERE r.campaign_id=c.id) AS runs,"
            " (SELECT COUNT(*) FROM decisions d WHERE d.campaign_id=c.id) AS decisions,"
            " (SELECT MAX(date) FROM metrics m WHERE m.campaign_id=c.id) AS latest,"
            " (SELECT GROUP_CONCAT(DISTINCT r.model) FROM runs r WHERE r.campaign_id=c.id) AS models"
            " FROM campaigns c ORDER BY c.created DESC")
        return web.json_response(rows)

    async def api_decisions(request):
        where, args = scope(request)
        rows = await q(f"SELECT run_id, episode, campaign_id, t, date, month, trigger, decision, reason, outcome, current,"
                       f" tokens_in, tokens_out, seconds, result,"
                       f" (SELECT model FROM runs WHERE runs.id=decisions.run_id) AS model"
                       f" FROM decisions WHERE {where} ORDER BY t", args)
        for r in rows:
            r["result"] = json.loads(r["result"]) if r["result"] else None
        return web.json_response(rows)

    async def api_decision(request):
        run, ep = request.query.get("run", ""), request.query.get("episode", "")
        if not ep.isdigit():
            raise web.HTTPBadRequest(text="episode must be a number")
        rows = await q("SELECT *, (SELECT model FROM runs WHERE runs.id=decisions.run_id) AS model"
                       " FROM decisions WHERE run_id=? AND episode=?", (run, int(ep)))
        if not rows:
            raise web.HTTPNotFound()
        r = rows[0]
        r["trace"] = json.loads(r["trace"]) if r["trace"] else None
        r["result"] = json.loads(r["result"]) if r["result"] else None
        return web.json_response(r)

    async def api_metrics(request):
        where, args = scope(request)
        rows = await q(f"SELECT date, month, data FROM metrics WHERE {where} ORDER BY month, t", args)
        return web.json_response([{"date": r["date"], "month": r["month"], **json.loads(r["data"])} for r in rows])

    api = [web.get("/api/campaigns", api_campaigns), web.get("/api/decisions", api_decisions),
           web.get("/api/decision", api_decision), web.get("/api/metrics", api_metrics)]

    def run_dir(request) -> Path:
        rid = request.match_info["run"]
        if not RUN_ID.match(rid) or not (runs_dir / rid / "events.jsonl").exists():
            raise web.HTTPNotFound()
        return runs_dir / rid

    async def runs(_):
        rows = list_runs(runs_dir, log.state.run_id if log else None)
        return web.json_response([{k: v for k, v in r.items() if k != "_status"} for r in rows])

    def read_events(path: Path, kinds: set[str]) -> list[dict]:
        out = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                if not kinds or ev.get("kind") in kinds:
                    out.append(ev)
        return out[-5000:]

    async def run_events(request):
        d = run_dir(request)
        kinds = set(filter(None, request.query.get("kind", "").split(",")))
        out = await asyncio.to_thread(read_events, d / "events.jsonl", kinds)
        return web.json_response(out)

    async def run_trace(request):
        d = run_dir(request)
        n = request.match_info["n"]
        if not n.isdigit():
            raise web.HTTPNotFound()
        p = d / "traces" / f"{int(n):04d}.json"
        if not p.exists():
            raise web.HTTPNotFound()
        return web.FileResponse(p, headers={"Content-Type": "application/json"})

    async def run_frame(request):
        p = run_dir(request) / "latest.jpg"
        if not p.exists():
            raise web.HTTPNotFound()
        return web.FileResponse(p, headers={"Cache-Control": "no-store"})

    history = [web.get("/runs", runs), web.get("/runs/{run}/events", run_events),
               web.get("/runs/{run}/trace/{n}", run_trace), web.get("/runs/{run}/frame.jpg", run_frame)]

    async def index(_):
        return web.FileResponse(STATIC / "dashboard.html")

    async def status(_):
        if not log:
            return web.json_response({"status": "viewer", "live": False})
        return web.json_response({**log.state.as_dict(), "live": True}, dumps=lambda o: json.dumps(o, default=str))

    if not log:
        # Always-on viewer: forward live endpoints to a running pilot's own dashboard, if any.
        proxy = LiveProxy(runs_dir)

        async def v_status(request):
            url = await proxy.url()
            if url:
                try:
                    async with proxy.session().get(url + "/status", timeout=ClientTimeout(total=3)) as r:
                        return web.json_response(await r.json())
                except (OSError, TimeoutError, ClientError):
                    proxy.forget()
            return await status(request)

        async def v_forward(request):
            url = await proxy.url()
            if not url:
                raise web.HTTPServiceUnavailable(text="no live pilot run")
            body = await request.read() if request.method == "POST" else None
            try:
                async with proxy.session().request(request.method, url + request.path_qs, data=body,
                                                   headers={"Content-Type": request.content_type},
                                                   timeout=ClientTimeout(total=30)) as r:
                    return web.Response(body=await r.read(), status=r.status,
                                        content_type=r.content_type, headers={"Cache-Control": "no-store"})
            except (OSError, TimeoutError, ClientError) as e:
                proxy.forget()
                raise web.HTTPBadGateway(text=f"live pilot unreachable: {e}") from e

        async def v_events(request):
            url = await proxy.url()
            if not url:
                raise web.HTTPServiceUnavailable(text="no live pilot run")
            resp = web.StreamResponse(headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"})
            await resp.prepare(request)
            try:
                async with proxy.session().get(url + "/events", timeout=ClientTimeout(total=None, sock_read=60)) as r:
                    async for chunk in r.content.iter_any():
                        await resp.write(chunk)
            except (OSError, TimeoutError, ClientError, ConnectionResetError, asyncio.CancelledError):
                pass
            return resp

        app = web.Application()
        app.on_cleanup.append(lambda _: proxy.close())
        app.add_routes([web.get("/", index), web.get("/status", v_status), web.get("/events", v_events),
                        web.get("/events.json", v_forward), web.get("/frame.jpg", v_forward),
                        web.post("/control", v_forward), *history, *api])
        return app

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
        elif action in ("chat", "order_add") and body.get("text", "").strip() and hasattr(pilot, action):
            getattr(pilot, action)(body["text"].strip())
        elif action == "order_remove" and hasattr(pilot, "order_remove") and str(body.get("index", "")).isdigit():
            pilot.order_remove(int(body["index"]))
        elif action == "decide_now" and hasattr(pilot, "decide_now"):
            pilot.decide_now(body.get("text", "") or "")
        elif action == "override" and hasattr(pilot, "override"):
            try:
                pilot.override(str(body.get("directive", "")))
            except ValueError as e:
                raise web.HTTPBadRequest(text=str(e)) from e
        else:
            raise web.HTTPBadRequest(text="action must be pause|resume|stop|instruct|chat|order_add|order_remove|"
                                          "decide_now|override, with its text/index/directive")
        return web.json_response({"ok": True, "status": log.state.status})

    app = web.Application()
    app.add_routes([web.get("/", index), web.get("/status", status), web.get("/frame.jpg", frame),
                    web.get("/events", events), web.get("/events.json", events_json), web.post("/control", control),
                    *history, *api])
    return app


def serve_in_background(pilot, host: str, port: int, runs_dir: Path | None = None,
                        telemetry=None) -> threading.Thread:
    def run() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        runner = web.AppRunner(make_app(pilot, runs_dir, telemetry))
        loop.run_until_complete(runner.setup())
        loop.run_until_complete(web.TCPSite(runner, host, port).start())
        loop.run_forever()

    t = threading.Thread(target=run, daemon=True, name="dashboard")
    t.start()
    return t
