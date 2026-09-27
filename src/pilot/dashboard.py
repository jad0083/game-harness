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
    GET  /api/campaigns                         campaigns: decision and run counts, latest date, empty, state (live/paused/needs_you/stopped)
    GET  /api/decisions?campaign=<id>|run=<id>  decisions (summary + outcome 12 months later)
    GET  /api/decision?run=<id>&episode=<n>     one decision with its full trace
    GET  /api/metrics?campaign=<id>|run=<id>    metric points over in-game time
    GET  /api/plans?campaign=<id>|run=<id>      campaign plan versions, newest first
    GET  /api/strategy?campaign=<id>            current pillar strategy, milestone status, version history, the game's pillars spec
    GET  /api/models                            models to offer, and the saved choice for the next run
    GET  /api/pc                                gaming PC: agent reachable, version, games open, game in front
    GET  /api/view?campaign=<id>|game=<game>    how the page speaks about the game (corpora/<game>/dashboard.toml)
    GET  /api/health?run=<id>                   model health: the last decision calls that fell back or failed
    GET  /api/events?campaign=<id>&after=<id>&n= a campaign's events for Activity, each with the game date it happened at
    GET  /api/orders?campaign=<id>&kind=&fate=&limit=   Civ VI: the order record, every order with its fate, purchases, last stands
    POST /api/capture  {}                       the game screen now, stored as the run's frame (live run)
    POST /api/settings  {"models": [{"model", "thinking"}, ...], "rotate"}   the model list (live too); older {"model", "thinking", "fallback"}
    POST /api/run  {"game", "speed", "months"}   start a pilot run (game-pilot.service); viewer only

Sign-in (auth.py; docs/design/2026-09-27-dashboard-v2-design.md rulings 34-52), viewer:
    GET  /api/auth/me                   who is asking: {via, device, notices, add_device}
    GET  /api/auth/devices              signed-in browsers and script tokens (a browser session only)
    POST /api/auth/devices  {"action": "signout"|"revoke"|"revoke_others"|"rename", "id", "name"}
Every other request needs a principal: a browser's `pilot_session` cookie, a script's `pgt_` token
as a header, or the service key (`dashboard_key`) as `X-Pilot-Key` / `Authorization: Bearer` from
loopback only. Changes must be JSON; a cookie needs a matching Origin. The live pilot's own
dashboard still takes the key (`key_guard`) and is reached through the viewer.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from aiohttp import ClientError, ClientSession, ClientTimeout, web

from .auth import (
    ACTOR_KEY,
    AUTH_KEY,
    AUTH_VERSION,
    KEEPALIVE_S,
    KEY_HEADER,
    RUNNER_KWARGS,
    Auth,
    KeySource,
    ServiceAuth,
    dashboard_key,  # noqa: F401 - re-exported: the key's home before auth.py
    lan_address,
)
from .events import acting
from .view import Names, Views

if TYPE_CHECKING:
    from .pillars import PillarSpec

STATIC = Path(__file__).parent / "static"
log_ = logging.getLogger(__name__)


RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")    # e.g. 20260926-185855; no dots or separators

def link_host(host: str) -> str:
    """A host for links: this machine's LAN address when the dashboard listens on all interfaces."""
    if host not in ("", "0.0.0.0", "::"):
        return f"[{host}]" if ":" in host else host
    return lan_address()


# control actions that already leave their own event (instruction, chat, orders): no extra `control` event
OWN_EVENT = {"instruct", "chat", "answer", "order_add", "order_remove", "decide_now", "override", "review_strategy",
             "set_speed", "set_months", "set_model"}
ACTION_KEY = web.RequestKey("pilot_action", str)
SERVICE = "game-pilot.service"      # deploy/game-pilot.service, started by the dashboard's Start run
LIVE_STATES = {"starting", "playing", "deciding", "paused", "needs_attention"}


class LiveProxy:
    """Finds the live pilot run (newest run whose status.json names a dashboard port that answers)
    and talks to it with the service key over loopback. K is read on every call; after a 401 it is
    re-read once (a rotation) and the call retried."""

    def __init__(self, runs_dir: Path, keys: KeySource | str):
        self.runs_dir = runs_dir
        self.keys = keys if isinstance(keys, KeySource) else KeySource(fixed=keys)
        self._url: str | None = None
        self.run: dict | None = None       # the live run (list_runs row, with its status.json) once found
        self._checked = 0.0
        self._session: ClientSession | None = None

    def session(self) -> ClientSession:
        if self._session is None or self._session.closed:
            self._session = ClientSession()
        return self._session

    @property
    def headers(self) -> dict[str, str]:
        return {KEY_HEADER: self.keys.get()}

    async def request(self, method: str, url: str, extra: dict | None = None, **kw):
        """(status, content type, body) from the live pilot, retried once with a re-read key after a 401."""
        for attempt in (0, 1):
            async with self.session().request(method, url, headers={**(extra or {}), **self.headers}, **kw) as r:
                if r.status == 401 and attempt == 0:
                    self.keys.reload()
                    continue
                return r.status, r.content_type, await r.read()
        raise AssertionError("unreachable")

    def forget(self) -> None:
        self._url, self.run, self._checked = None, None, 0.0

    async def close(self) -> None:
        if self._session:
            await self._session.close()

    async def url(self) -> str | None:
        now = asyncio.get_running_loop().time()
        if now - self._checked < 5:
            return self._url
        self._checked, self._url, self.run = now, None, None
        for run in list_runs(self.runs_dir):
            st = run.get("_status") or {}
            port = (st.get("info") or {}).get("port")
            if not port or st.get("status") not in LIVE_STATES:
                continue
            url = f"http://127.0.0.1:{int(port)}"
            try:
                code, _, body = await self.request("GET", url + "/status", timeout=ClientTimeout(total=2))
                if code == 200 and json.loads(body).get("run_id") == run["id"]:
                    self._url, self.run = url, run
                    break
            except (OSError, TimeoutError, ClientError, ValueError):
                continue
        return self._url


GAME_WINDOWS = {"Stellaris": "stellaris", "Galactic Civilizations": "galciv4",
                "Civilization VI": "civ6"}      # "Sid Meier's Civilization VI" (DX11) and "(DX12)"


def game_of(title: str) -> str | None:
    """The known game a window title belongs to, if any."""
    for k, g in GAME_WINDOWS.items():
        if (title == k if k == "Stellaris" else k in title):
            return g
    return None


def pc_status() -> dict:
    """Agent health and open game windows on the gaming PC (read-only calls). Window titles stay
    here: the answer only says which known games are open and whether one is in front. `state`
    tells the chip's cases apart (ruling 10): on, offline (the connection was refused), timeout (no
    answer in 3 s: the page shows "busy" when the live run just finished a turn, else "not
    answering"), refused (the agent refused our token), error."""
    import socket
    import urllib.error
    import urllib.request
    from urllib.parse import urlparse

    from .config import REPO, Settings
    url = Settings().agent_url.rstrip("/")
    host = urlparse(url).hostname or url
    try:
        token = os.environ.get("GAME_AGENT_TOKEN") or (REPO / ".agent_token").read_text().strip()
        hdr = {"Authorization": f"Bearer {token}"}
        with urllib.request.urlopen(urllib.request.Request(url + "/health", headers=hdr), timeout=3) as r:  # LAN agent
            h = json.load(r)
        with urllib.request.urlopen(urllib.request.Request(url + "/windows", headers=hdr), timeout=3) as r:
            titles = [w.get("title", "") for w in json.load(r).get("windows", [])]
    except Exception as e:  # noqa: BLE001 - offline is a normal answer here
        reason = getattr(e, "reason", e)
        state = ("refused" if isinstance(e, urllib.error.HTTPError) and e.code in (401, 403)
                 else "offline" if isinstance(reason, ConnectionRefusedError)
                 else "timeout" if isinstance(reason, (TimeoutError, socket.timeout)) or "timed out" in str(e).lower()
                 else "error")
        return {"online": False, "state": state, "host": host, "error": str(e)[:120]}
    games = sorted({g for g in map(game_of, titles) if g})
    front = game_of(h.get("foreground") or "")
    return {"online": True, "state": "on", "host": host, "version": h.get("version"), "games": games,
            "game_in_front": front is not None, "front_game": front}


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
                    "date": st.get("game_date", ""), "status": st.get("status", ""),
                    "frame": (d / "latest.jpg").exists(),
                    "backfill": d.name.endswith("-backfill")})      # scripts/civ6-backfill-orders.py; no run to show
    return out


HEALTH_WINDOW_S = 3600       # model health looks at the decisions of the last hour...
HEALTH_CALLS = 5             # ...and at most this many of them


def model_health(events: list[dict], now: float | None = None) -> dict:
    """Ruling 9: of the last `HEALTH_CALLS` decisions in the hour before `now` (the run's newest
    event, so it also works for history), how many fell back to another model or got no answer;
    the model they fell back from (the commonest), to, and why; models whose errors are billing or
    a refused key (Settings marks those)."""
    from collections import Counter

    from .wording import cause
    now = now if now is not None else max((e.get("t", 0) for e in events), default=0)
    calls, pending = [], []
    billing: dict[str, str] = {}
    for e in events:
        kind = e.get("kind")
        if kind in ("model_fallback", "model_retry", "episode_error") and e.get("error"):
            why = cause(e["error"])
            if e.get("model") and why.startswith(("billing", "the provider refused")):
                billing.setdefault(e["model"], why)
        if kind == "model_fallback" and e.get("role", "decisions") == "decisions":
            pending.append(e)
        elif kind == "trace" and (e.get("episode") or 0) > 0 and e.get("decision") != "strategy_review":
            calls.append({"t": e.get("t", 0), "model": e.get("model"), "fell_back": bool(pending),
                          "failed": e.get("outcome") == "error", "from": [p.get("model") for p in pending],
                          "why": [cause(p.get("error")) for p in pending]})
            pending = []
    recent = [c for c in calls if c["t"] >= now - HEALTH_WINDOW_S][-HEALTH_CALLS:]
    bad = [c for c in recent if c["fell_back"] or c["failed"]]
    frm = Counter(m for c in bad for m in c["from"]).most_common(1)
    to = Counter(c["model"] for c in bad if c["fell_back"] and not c["failed"]).most_common(1)
    why = Counter(w for c in bad for w in c["why"]).most_common(1)
    return {"calls": len(recent), "bad": len(bad), "failed": sum(1 for c in bad if c["failed"]),
            "from_model": frm[0][0] if frm else None, "to_model": to[0][0] if to else None,
            "cause": why[0][0] if why else None, "last_fell_back": bool(calls and calls[-1]["fell_back"]),
            "billing": [{"model": m, "cause": w} for m, w in billing.items()], "window_s": HEALTH_WINDOW_S}


def make_app(pilot, runs_dir: Path | None = None, telemetry=None, corpora: Path | None = None,
             key: str | None = None, auth: Auth | None = None, keepalive_s: float = KEEPALIVE_S) -> web.Application:
    """Dashboard for a live `pilot` (Pilot or Governor), or read-only over `runs_dir` when pilot is None.
    `corpora` is where each game's pillars file is read (default: the repo's corpora/). `key` fixes
    the service key (default: `PILOT_DASHBOARD_KEY` or runs/dashboard.key, re-read when it changes);
    `auth` is the viewer's sign-in state (default: `Auth.from_env`)."""
    from .config import REPO
    log = pilot.log if pilot else None
    runs_dir = runs_dir or (log.dir.parent if log else Path("runs"))
    tel = telemetry or (log.telemetry if log else None)
    corpora = corpora or (REPO / "corpora")
    live_url = None                  # set for the viewer: finds a live run to refuse a second start
    live_run = None                  # set for the viewer: (campaign, status) of the live run, if any
    views, names = Views(corpora), Names(corpora)

    def game_of_campaign(cid: str) -> str:
        return cid.split("/", 1)[0] if cid else ""

    def campaign_spec(cid: str, stored: bool = True) -> tuple[PillarSpec | None, str]:
        """The pillars spec of a campaign's game (id '<game>/<name>'), and "" for no error; or
        (None, "pillars: <message>") when the game's pillars file is missing or invalid (logged
        too) — the caller must not silently compute milestone status without it (an empty
        `row_keys` mis-maps every metric that needs row remapping, e.g. Stellaris's `colonies`).
        The live governor's own spec wins for its game; for its own campaign with the layer off,
        its error is returned (edits would fail). A game with no pillars file and no `stored`
        strategy (e.g. galciv4) has no strategy layer at all: (None, "")."""
        from .pillars import PillarsError, load_pillars
        game = cid.split("/", 1)[0]
        live_game = getattr(getattr(pilot, "s", None), "game", None) == game
        live = getattr(pilot, "pillars", None)
        if live is not None and live_game:
            return live, ""
        live_error = getattr(pilot, "pillars_error", "") if log is not None and cid == log.campaign_id else ""
        if live_error and isinstance(live_error, str):
            return None, f"the strategy layer is off: {live_error}"
        if not re.fullmatch(r"[a-z0-9_]+", game):
            return None, ""
        if not stored and not (corpora / game / "pillars.toml").exists():
            return None, ""
        try:
            return load_pillars(corpora / game), ""
        except PillarsError as e:
            log_.warning("campaign %s: pillars: %s", cid, e)
            return None, f"pillars: {e}"

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
            "SELECT c.id, c.game, c.name, c.title, c.created,"
            " (SELECT COUNT(*) FROM runs r WHERE r.campaign_id=c.id) AS runs,"
            " (SELECT COUNT(*) FROM decisions d WHERE d.campaign_id=c.id AND (d.decision IS NULL OR d.decision != 'strategy_review')) AS decisions,"
            " (SELECT m.date FROM metrics m WHERE m.campaign_id=c.id AND m.month IS NOT NULL"
            "  ORDER BY m.month DESC, m.t DESC LIMIT 1) AS latest,"      # in game order: MAX(date) put "T99" after "T310"
            " (SELECT GROUP_CONCAT(DISTINCT r.model) FROM runs r WHERE r.campaign_id=c.id) AS models,"
            " (SELECT COUNT(*) FROM metrics m WHERE m.campaign_id=c.id) AS metrics"
            " FROM campaigns c ORDER BY c.created DESC")
        # the campaign list (ruling 4): empty campaigns fold away; the live one says its state
        if log is not None:
            live_cid, live_status = log.campaign_id, log.state.status
        else:
            live_cid, live_status = await live_run() if live_run else (None, None)
        for r in rows:
            r["empty"] = not r["decisions"] and not r["metrics"]
            r["state"] = ({"paused": "paused", "needs_attention": "needs_you"}.get(live_status or "", "live")
                          if live_cid and r["id"] == live_cid and live_status in LIVE_STATES else "stopped")
        return web.json_response(rows)

    def decorate(rows: list[dict], order_rows: list[dict], calls: list[dict]) -> list[dict]:
        """What the page shows for each decision (rulings 27, 28, 30): the trigger as a category in
        words, an error cut to its cause, each order by name with its fate (the order record's later
        outcome where there is one), and whether a fallback model answered (`calls`: the runs'
        model_retry / model_fallback events, oldest first)."""
        from .wording import attempts, cause, fate, order_parts, trigger
        by_run: dict[str, list[dict]] = {}
        for e in calls:
            by_run.setdefault(e["run_id"], []).append(e)
        prev_t: dict[str, float] = {}
        for r in rows:
            game = game_of_campaign(r.get("campaign_id") or "")
            name = lambda i, game=game: names.name(game, i)
            r["trigger_label"] = trigger(r.get("trigger"), name)
            if r.get("error"):
                r["cause"] = cause(r["error"])
            before = [e for e in by_run.get(r["run_id"], []) if prev_t.get(r["run_id"], 0) < e["t"] <= (r["t"] or 0)]
            prev_t[r["run_id"]] = r["t"] or 0
            r["attempts"] = attempts(before)
            r["fallback"] = any(e["kind"] == "model_fallback" and e.get("role", "decisions") == "decisions" for e in before)
            orders = json.loads(r.pop("orders_json", None) or "null")
            if not orders:
                continue
            out = []
            for o in orders:
                p = order_parts(o)
                later = [x for x in order_rows if x.get("ordered") == r["date"] and x.get("id") == p["id"]
                         and (x.get("city") or "").lower() == p["city"].lower()
                         and x.get("order_kind") in (p["kind"], "purchase" if p["kind"] == "production" else p["kind"])]
                row = later[-1] if later else None
                ids = [i.strip() for i in p["id"].split(",")] if p["kind"] == "policies" else [p["id"]]
                out.append({**p, "name": ", ".join(str(names.name(game, i)) for i in ids if i),
                            "text": o.get("order"), "outcome": o.get("outcome"),
                            "fate": fate(o.get("outcome"), row.get("result") if row else None, kind=p["kind"],
                                         by=", ".join(str(names.name(game, b.strip())) for b in (row.get("by") or "").split(",")
                                                      if b.strip()) if row else "",
                                         detail=(row or {}).get("detail") or "")})
            r["orders"] = out
        return rows

    async def decision_context(rows: list[dict]) -> tuple[list[dict], list[dict]]:
        """The order record rows of the decisions' campaigns and the model-call events of their runs."""
        cids = sorted({r["campaign_id"] for r in rows if r.get("campaign_id")})
        order_rows = [x for c in cids for x in await asyncio.to_thread(need_tel().campaign_events, c, "order_outcome")]
        run_ids = sorted({r["run_id"] for r in rows})
        calls = []
        if run_ids:
            marks = ",".join("?" * len(run_ids))
            calls = [{"run_id": e["run_id"], "t": e["t"], "kind": e["kind"], **json.loads(e["data"])} for e in await q(
                f"SELECT run_id, t, kind, data FROM events WHERE kind IN ('model_retry', 'model_fallback')"
                f" AND run_id IN ({marks}) ORDER BY t", tuple(run_ids))]
        return order_rows, calls

    async def api_decisions(request):
        # excludes strategy_review rows: this lists directive decisions, not strategy reviews (Task 9
        # adds its own review marks)
        where, args = scope(request)
        rows = await q(f"SELECT run_id, episode, campaign_id, t, date, month, trigger, decision, reason, outcome, current,"
                       f" tokens_in, tokens_out, seconds, result, model_version, thinking,"
                       f" json_extract(trace,'$.off_frame') AS off_frame, json_extract(trace,'$.error') AS error,"
                       f" json_extract(trace,'$.orders') AS orders_json, json_extract(trace,'$.retried_for') AS retried_for,"
                       f" COALESCE(model, (SELECT model FROM runs WHERE runs.id=decisions.run_id)) AS model"
                       f" FROM decisions WHERE {where} AND (decision IS NULL OR decision != 'strategy_review') ORDER BY t", args)
        for r in rows:
            r["result"] = json.loads(r["result"]) if r["result"] else None
            r["retried_for"] = json.loads(r["retried_for"]) if r["retried_for"] else None
        order_rows, calls = await decision_context(rows)
        return web.json_response(await asyncio.to_thread(decorate, rows, order_rows, calls))

    async def api_decision(request):
        run, ep = request.query.get("run", ""), request.query.get("episode", "")
        if not ep.isdigit():
            raise web.HTTPBadRequest(text="episode must be a number")
        rows = await q("SELECT *, COALESCE(model, (SELECT model FROM runs WHERE runs.id=decisions.run_id)) AS model"
                       " FROM decisions WHERE run_id=? AND episode=?", (run, int(ep)))
        if not rows:
            raise web.HTTPNotFound()
        r = rows[0]
        r["trace"] = json.loads(r["trace"]) if r["trace"] else None
        r["result"] = json.loads(r["result"]) if r["result"] else None
        r["orders_json"] = json.dumps((r["trace"] or {}).get("orders")) if (r["trace"] or {}).get("orders") else None
        r["error"] = (r["trace"] or {}).get("error")
        prev = await q("SELECT MAX(t) AS t FROM decisions WHERE run_id=? AND t < ?", (run, r["t"] or 0))
        order_rows, calls = await decision_context([r])
        calls = [e for e in calls if e["t"] > ((prev[0]["t"] if prev else None) or 0)]
        return web.json_response((await asyncio.to_thread(decorate, [r], order_rows, calls))[0])

    def readable_rows(rows: list[dict], game: str) -> list[dict]:
        """Rivals keep their id and get a readable name (CIVILIZATION_GERMANY -> Germany)."""
        for r in rows:
            for n in r.get("neighbours") or []:
                if isinstance(n, dict) and n.get("name") != (name := names.name(game, n.get("name"))):
                    n["id"], n["name"] = n["name"], name
        return rows

    async def api_metrics(request):
        where, args = scope(request)
        rows = await q(f"SELECT date, month, campaign_id, data FROM metrics WHERE {where} ORDER BY month, t", args)
        game = game_of_campaign(rows[0]["campaign_id"] or "") if rows else ""
        out = [{"date": r["date"], "month": r["month"], **json.loads(r["data"])} for r in rows]
        return web.json_response(await asyncio.to_thread(readable_rows, out, game))

    async def api_view(request):
        """How the page speaks about a game: the campaign's (or the live run's) dashboard.toml."""
        game = request.query.get("game") or game_of_campaign(request.query.get("campaign", "")) \
            or (getattr(getattr(pilot, "s", None), "game", None) if pilot else None) \
            or game_of_campaign(log.campaign_id or "" if log else "") or ((log.state.info or {}).get("game", "") if log else "")
        return web.json_response(await asyncio.to_thread(views.get, game))

    async def api_orders(request):
        """The Civ VI Orders tab (rulings 19-22): the order record per key (the governor's
        `order_record` over the campaign's order_outcome rows, so it agrees with the live
        `info.order_record`), every order newest first with its fate, name and the decision it came
        from (backfilled rows tagged; open orders with how far they were followed), purchases, and
        the last stands. Filters: kind (research, civic, policies, production, purchase, stand), fate
        (held, replaced, refused, noreply, open), limit."""
        from .civ6 import order_record
        from .wording import fate, record_label
        cid = request.query.get("campaign", "")
        if not cid:
            raise web.HTTPBadRequest(text="campaign is required")
        tel_ = need_tel()
        game = game_of_campaign(cid)
        rows = await asyncio.to_thread(tel_.campaign_events, cid, "order_outcome")
        followed = await asyncio.to_thread(tel_.campaign_events, cid, "order_followed")
        stands = await asyncio.to_thread(tel_.campaign_events, cid, "last_stand")
        checks = await asyncio.to_thread(tel_.campaign_events, cid, "last_stand_check")
        mets = await asyncio.to_thread(tel_.metrics_rows, cid)
        decs = await q("SELECT run_id, episode, date FROM decisions WHERE campaign_id=? AND"
                       " (decision IS NULL OR decision != 'strategy_review') ORDER BY t", (cid,))
        spec, _ = campaign_spec(cid)
        orders_spec = getattr(spec, "orders", None)
        now_turn = max([m.get("turn") for m in mets if isinstance(m.get("turn"), int)]
                       + [r.get("turn") for r in rows if isinstance(r.get("turn"), int)] + [0])

        def build() -> dict:
            nm = lambda i: names.name(game, i)
            rec = order_record(rows, now_turn, orders_spec) if orders_spec else {}
            for k, r in rec.items():
                r["label"] = record_label(k)
                if r.get("last_override"):
                    r["last_override"].update(name=nm(r["last_override"].get("id")), by_name=nm(r["last_override"].get("by")))
            by_date = {d["date"]: {"run_id": d["run_id"], "episode": d["episode"]} for d in decs}
            done = {r.get("ref") for r in rows if r.get("ref")}
            items = []
            for r in rows:
                by = ", ".join(str(nm(b.strip())) for b in str(r.get("by") or "").split(",") if b.strip())
                items.append({**r, "name": ", ".join(str(nm(i.strip())) for i in str(r.get("id") or "").split(",") if i.strip()),
                              "fate": fate("stuck", r.get("result"), kind=r.get("order_kind") or "", by=by,
                                           detail=r.get("detail") or "")})
            for f in followed:
                if not f.get("ref") or f["ref"] in done:
                    continue
                done.add(f["ref"])
                row = dict(f.get("row") or {})
                start = (f.get("base") or {}).get("turn") or 0
                items.append({**row, "result": None, "date": row.get("ordered"), "turn": start,
                              "name": str(nm(row.get("id"))), "fate": fate("stuck", None, kind=row.get("order_kind") or ""),
                              "followed": {"turns": max(0, now_turn - start), "window": f.get("window")}})
            for it in items:
                it["decision"] = by_date.get(it.get("ordered"))
            items = [it for _, it in sorted(enumerate(items), key=lambda p: ((p[1].get("turn") or 0), p[0]), reverse=True)]
            kind, want = request.query.get("kind", ""), request.query.get("fate", "")
            shown = [it for it in items if (not kind or it.get("order_kind") == kind or str(it.get("key", "")).startswith(kind))
                     and (not want or it["fate"]["key"] == want)]
            limit = int(request.query["limit"]) if request.query.get("limit", "").isdigit() else 200
            return {"record": rec, "now_turn": now_turn,
                    "spec": ({"window_turns": orders_spec.window_turns, "weak_rate": orders_spec.weak_rate,
                              "min_samples": dict(orders_spec.min_samples)} if orders_spec else None),
                    "log": shown[:limit], "purchases": [it for it in items if it.get("order_kind") == "purchase"][:20],
                    "stands": list(reversed(stands))[:3], "stand_checks": list(reversed(checks))[:3]}
        return web.json_response(await asyncio.to_thread(build))

    async def api_events(request):
        """Activity for one campaign (rulings 4, 18): its own events across its runs (backfill runs
        left out), oldest first, the newest `n` (default 600) after the event `after` (each row's `id`;
        times are rounded to the millisecond, so they cannot tell events apart), each with the game date
        it happened at (its own date, a turn event's turn, else the newest metrics date before it). The
        feed's quiet kinds (metrics, status, traces, chat, plans, the order record's rows) are left out;
        they have their own views."""
        cid = request.query.get("campaign", "")
        if not cid:
            raise web.HTTPBadRequest(text="campaign is required")
        try:
            after = int(request.query.get("after") or 0)
            n = min(int(request.query.get("n") or 600), 2000)
        except ValueError as e:
            raise web.HTTPBadRequest(text="after and n must be numbers") from e
        before = await q("SELECT json_extract(e.data, '$.date') AS date FROM events e JOIN runs r ON r.id = e.run_id"
                         " WHERE r.campaign_id=? AND e.kind='metrics' AND e.rowid<=? AND e.run_id NOT LIKE '%-backfill'"
                         " ORDER BY e.rowid DESC LIMIT 1", (cid, after)) if after else []
        rows = await q("SELECT e.rowid AS id, e.run_id, e.t, e.kind, CASE WHEN e.kind='metrics' THEN json_object('date',"
                       " json_extract(e.data, '$.date')) ELSE e.data END AS data FROM events e JOIN runs r ON r.id = e.run_id"
                       " WHERE r.campaign_id=? AND e.rowid>? AND e.run_id NOT LIKE '%-backfill'"
                       " AND e.kind NOT IN ('status', 'trace', 'chat', 'plan', 'order_outcome', 'order_followed')"
                       " ORDER BY e.rowid", (cid, after))

        def build() -> list[dict]:
            date = before[0]["date"] if before else None
            out = []
            for r in rows:
                try:
                    data = json.loads(r["data"])
                except ValueError:
                    continue
                if r["kind"] == "metrics":
                    date = data.get("date") or date
                    continue
                own = data.get("date") or (f"T{data['turn']}" if r["kind"] == "turn" and isinstance(data.get("turn"), int) else None)
                out.append({**data, "id": r["id"], "run_id": r["run_id"], "t": r["t"], "kind": r["kind"], "date": own or date})
            return out[-n:]
        return web.json_response(await asyncio.to_thread(build))

    async def api_plans(request):
        where, args = scope(request)
        rows = await q(f"SELECT run_id, t, date, source, text FROM plans WHERE {where} ORDER BY t DESC", args)
        return web.json_response(rows)

    async def api_strategy(request):
        """The current pillar strategy, its milestones' status, version history and the game's
        pillars spec (labels, directives, actions) for a campaign."""
        from .strategy import Strategy, directive_record, milestone_status, pressures
        cid = request.query.get("campaign") or (log.campaign_id if log else "")
        cur = await asyncio.to_thread(tel.latest_strategy, cid) if tel is not None and cid else None
        spec, error = campaign_spec(cid, stored=cur is not None) if cid else (None, "")
        public = spec.public() if spec else None
        if tel is None or not cid:
            return web.json_response({"current": None, "milestones": [], "history": [], "spec": public, "error": error})
        rows = await asyncio.to_thread(tel.metrics_rows, cid)
        hist = await asyncio.to_thread(tel.strategy_history, cid)
        ms: list = []
        press: dict = {}
        if cur:
            try:
                s = Strategy.model_validate({k: v for k, v in cur.items() if k != "reason"})
            except ValueError:
                s = None    # an older/foreign strategy shape: serve the raw record, no milestone status
            if s is not None and spec is not None and set(s.pillars) != set(spec.ids):
                error = "stored strategy does not match the game's pillars; the next review writes a new one"
            elif s is not None and spec is not None:  # no spec (missing/invalid pillars file): no milestone status,
                today = rows[-1]["date"] if rows else "2200.01.01"   # never guess with empty row_keys
                for name, pl in s.pillars.items():
                    for m in pl.milestones:
                        ms.append({"pillar": name, **m.model_dump(),
                                  "status": milestone_status(m, rows, today, spec.row_keys)})
                press = pressures(s, spec, lambda _n, m: milestone_status(m, rows, today, spec.row_keys) if rows else "",
                                  record_of=lambda name, metric: (directive_record(rows, d, metric, spec.row_keys)
                                                                  if (d := spec.directive_of(name)) and rows else None))
            if s is not None:   # weights as the governor sees them (a ranked strategy converts on load)
                cur = {**s.model_dump(), "reason": cur.get("reason", "")}
        ids = {i for pl in ((cur or {}).get("pillars") or {}).values() if isinstance(pl, dict)
               for v in pl.values() if isinstance(v, list) for i in v if isinstance(i, str)}
        # the latest review results (accepted, rejected, skipped), newest first, for the Review button
        reviews = await q("SELECT e.t, e.kind, e.data FROM events e JOIN runs r ON r.id = e.run_id WHERE r.campaign_id=?"
                          " AND e.kind IN ('strategy_review', 'strategy_rejected', 'strategy_review_skipped')"
                          " ORDER BY e.t DESC LIMIT 8", (cid,))
        return web.json_response({"current": cur, "milestones": ms, "history": hist, "spec": public, "error": error,
                                  "pressure": press,
                                  "names": await asyncio.to_thread(names.names, game_of_campaign(cid), sorted(ids)),
                                  "reviews": [{"t": r["t"], "kind": r["kind"], **json.loads(r["data"])} for r in reviews]})

    models_cache: dict = {}

    async def api_models(_):
        """Models to offer (cached 10 min) and the saved choice for the next run."""
        from .config import Settings
        from .models import ROLES, available_models, load_prefs, provider_catalog
        now = asyncio.get_running_loop().time()
        if not models_cache or now - models_cache["t"] > 600:
            s = Settings.from_env()
            models_cache.update(t=now, models=await asyncio.to_thread(available_models, s), default=s.model,
                                providers=await asyncio.to_thread(provider_catalog, s))
        prefs = load_prefs(runs_dir)
        return web.json_response({"models": models_cache["models"], "model": prefs.get("model", models_cache["default"]),
                                  "thinking": prefs.get("thinking", "medium"), "game": prefs.get("game", "stellaris"),
                                  "fallback": prefs.get("fallback", Settings.fallback_model or "none"),
                                  "providers": models_cache.get("providers", []),
                                  "pool": prefs.get("models") or Settings(model=prefs.get("model", models_cache["default"]),
                                                                          governor_thinking=prefs.get("thinking", "medium")).pool(),
                                  "rotate": prefs.get("rotate", False),
                                  "roles": prefs.get("roles", {}), "role_meta": ROLES,
                                  "speed": prefs.get("speed", "normal"), "months": prefs.get("months", 12)})

    async def api_settings(request):
        """Save the model and thinking level for the next run (and the live run, if any)."""
        from .models import save_prefs
        body = await request.json()
        try:
            months = body.get("months")
            prefs = save_prefs(runs_dir, model=body.get("model") or None, thinking=body.get("thinking") or None,
                               speed=body.get("speed") or None, months=int(months) if months not in (None, "") else None,
                               fallback=body.get("fallback") or None, models=body.get("models"),
                               rotate=body.get("rotate"), roles=body.get("roles"))
        except (ValueError, TypeError) as e:
            raise web.HTTPBadRequest(text=str(e)) from e
        if pilot is not None and hasattr(pilot, "set_model") and body.get("model"):
            pilot.set_model(prefs["model"], prefs.get("thinking"))
        if pilot is not None and hasattr(pilot, "set_fallback") and body.get("fallback"):
            pilot.set_fallback(prefs["fallback"])
        if pilot is not None and hasattr(pilot, "set_models") and (body.get("models") or body.get("rotate") is not None):
            pilot.set_models(prefs["models"], prefs.get("rotate", False))
        if pilot is not None and hasattr(pilot, "set_roles") and body.get("roles") is not None:
            pilot.set_roles(body["roles"])
        return web.json_response({"ok": True, **prefs, "applied_live": pilot is not None})

    async def api_run(request):
        """Start a pilot run as the game-pilot user service (settings saved for it first)."""
        from .models import load_prefs, save_prefs
        if log is not None:
            raise web.HTTPConflict(text="this dashboard belongs to a running pilot")
        body = await request.json()
        try:
            months = body.get("months")
            save_prefs(runs_dir, game=body.get("game"), speed=body.get("speed"),
                       months=int(months) if months not in (None, "") else None)
        except (ValueError, TypeError) as e:
            raise web.HTTPBadRequest(text=str(e)) from e
        proxy_url = await live_url() if live_url else None
        if proxy_url:
            raise web.HTTPConflict(text="a pilot run is already live")
        proc = await asyncio.create_subprocess_exec(
            "systemctl", "--user", "start", SERVICE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        out, _ = await proc.communicate()
        if proc.returncode != 0:
            raise web.HTTPInternalServerError(text=f"could not start {SERVICE}: {out.decode(errors='replace')[:300]}")
        return web.json_response({"ok": True, "started": SERVICE, **load_prefs(runs_dir)})

    pc_cache: dict = {}

    async def api_pc(_):
        """Is the gaming PC reachable, which agent version, which game is open or in front (cached 4 s)."""
        now = asyncio.get_running_loop().time()
        if pc_cache and now - pc_cache["t"] < 4:
            return web.json_response(pc_cache["data"])
        data = await asyncio.to_thread(pc_status)
        pc_cache.update(t=now, data=data)
        return web.json_response(data)

    api = [web.get("/api/campaigns", api_campaigns), web.get("/api/decisions", api_decisions),
           web.get("/api/pc", api_pc), web.get("/api/view", api_view), web.get("/api/orders", api_orders),
           web.get("/api/events", api_events),
           web.post("/api/run", api_run),
           web.get("/api/models", api_models), web.post("/api/settings", api_settings),
           web.get("/api/plans", api_plans), web.get("/api/strategy", api_strategy),
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

    async def api_health(request):
        """Model health of a run (live or recorded), from its events (ruling 9)."""
        rid = request.query.get("run", "") or (log.state.run_id if log else "")
        if not RUN_ID.match(rid) or not (runs_dir / rid / "events.jsonl").exists():
            raise web.HTTPNotFound()
        evs = await asyncio.to_thread(read_events, runs_dir / rid / "events.jsonl",
                                      {"trace", "model_fallback", "model_retry", "episode_error"})
        live = log is not None and log.state.run_id == rid
        return web.json_response(model_health(evs, now=time.time() if live else None))

    history = [web.get("/runs", runs), web.get("/runs/{run}/events", run_events), web.get("/api/health", api_health),
               web.get("/runs/{run}/trace/{n}", run_trace), web.get("/runs/{run}/frame.jpg", run_frame)]

    async def index(_):
        return web.FileResponse(STATIC / "dashboard.html")

    async def status(_):
        if not log:
            return web.json_response({"status": "viewer", "live": False})
        return web.json_response({**log.state.as_dict(), "live": True}, dumps=lambda o: json.dumps(o, default=str))

    if not log:
        # Always-on viewer: forward live endpoints to a running pilot's own dashboard, if any.
        auth = auth or Auth.from_env(runs_dir, key=key)
        proxy = LiveProxy(runs_dir, auth.keys)
        live_url = proxy.url

        async def live_run() -> tuple[str | None, str | None]:
            if not await proxy.url() or not proxy.run:
                return None, None
            st = proxy.run.get("_status") or {}
            return (st.get("info") or {}).get("campaign"), st.get("status")

        def refused_key() -> web.Response:
            # the live pilot's 401 is about the service key, never this browser's sign-in
            return web.json_response({"error": "live_pilot_refused_key", "reason": "The live pilot refused the "
                                      "dashboard's service key.", "fix": "Restart game-pilot.service after a key "
                                      "rotation."}, status=502)

        async def v_status(request):
            url = await proxy.url()
            if url:
                try:
                    code, _, body = await proxy.request("GET", url + "/status", auth.device_headers(request),
                                                        timeout=ClientTimeout(total=3))
                    if code == 200:
                        return web.json_response(json.loads(body))
                except (OSError, TimeoutError, ClientError, ValueError):
                    pass
                proxy.forget()
            return await status(request)

        async def v_forward(request):
            url = await proxy.url()
            if not url:
                raise web.HTTPServiceUnavailable(text="no live pilot run")
            body = await request.read() if request.method == "POST" else None
            try:
                code, ctype, data = await proxy.request(
                    request.method, url + request.path_qs, {"Content-Type": request.content_type,
                                                            **auth.device_headers(request)},
                    data=body, timeout=ClientTimeout(total=30))
            except (OSError, TimeoutError, ClientError) as e:
                proxy.forget()
                raise web.HTTPBadGateway(text=f"live pilot unreachable: {e}") from e
            if code == 401:
                return refused_key()
            return web.Response(body=data, status=code, content_type=ctype)

        async def v_events(request):
            """The live pilot's event stream, closed within one keepalive once this request's
            principal is no longer valid (signed out, revoked, the old cookie's window closed)."""
            url = await proxy.url()
            if not url:
                raise web.HTTPServiceUnavailable(text="no live pilot run")
            resp = web.StreamResponse(headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"})
            await resp.prepare(request)
            loop = asyncio.get_running_loop()
            pending: asyncio.Future | None = None
            try:
                async with proxy.session().get(url + "/events", headers={**auth.device_headers(request), **proxy.headers},
                                              timeout=ClientTimeout(total=None, sock_read=60)) as r:
                    if r.status != 200:
                        return resp
                    chunks = r.content.iter_any().__aiter__()
                    check_at = loop.time() + auth.keepalive_s
                    while True:
                        pending = pending or asyncio.ensure_future(chunks.__anext__())
                        done, _ = await asyncio.wait({pending}, timeout=max(0.0, check_at - loop.time()))
                        if done:
                            chunk, pending = pending.result(), None
                            await resp.write(chunk)
                        if loop.time() >= check_at:
                            if not auth.still_valid(request):
                                break                         # signed out or revoked: the stream ends
                            check_at = loop.time() + auth.keepalive_s
            except (OSError, TimeoutError, ClientError, ConnectionResetError, StopAsyncIteration, asyncio.CancelledError):
                pass
            finally:
                if pending is not None:
                    pending.cancel()
            return resp

        app = web.Application(middlewares=[auth.middleware])
        auth.install(app)
        app.on_cleanup.append(lambda _: proxy.close())
        app.add_routes([web.get("/", index), web.get("/status", v_status), web.get("/events", v_events),
                        web.get("/events.json", v_forward), web.get("/frame.jpg", v_forward),
                        web.post("/control", v_forward), web.post("/api/capture", v_forward), *history, *api])
        return app

    # the live pilot: the service key as a header from loopback only (the viewer, scripts on this machine)
    service = ServiceAuth(KeySource(runs_dir, fixed=key), keepalive_s)
    log.state.info["auth_version"] = AUTH_VERSION

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
                    ev = await asyncio.wait_for(q.get(), timeout=service.keepalive_s)
                    await resp.write(f"data: {json.dumps(ev, default=str)}\n\n".encode())
                except TimeoutError:
                    if not service.still_valid(request):
                        break                          # the key changed: the stream ends
                    await resp.write(b": keepalive\n\n")
        except (ConnectionResetError, asyncio.CancelledError):
            pass
        finally:
            log.unsubscribe(q)
        return resp

    async def capture(request):
        """The game screen now (the agent's screenshot: read-only for the game), stored as the run's
        frame and on the needs-you card, with who asked (ruling 7)."""
        by, by_id = request.get(ACTOR_KEY) or ("the controller", None)
        shoot = getattr(getattr(pilot, "game", None), "screenshot", None)
        if shoot is None:
            return web.json_response({"error": "no_capture", "reason": "This run cannot capture the game screen."},
                                     status=409)
        try:
            shot = await asyncio.to_thread(shoot)
        except Exception as e:  # noqa: BLE001 - said to the page, never raised
            shot, why = None, str(e)
        else:
            why = ""
        image = getattr(shot, "image", None)
        if not image:
            from .wording import cause
            return web.json_response({"error": "capture_failed", "reason": "The game screen could not be captured"
                                      + (f": {cause(why)}." if why else "."), "fix": "Check the PC and its agent."},
                                     status=502)
        frame = log.frame(image)
        if isinstance(log.state.info.get("attention"), dict):
            log.state.info["attention"]["frame"] = frame
        with acting(by, by_id):
            log.emit("capture", frame=frame)
        return web.json_response({"ok": True, "frame": frame})

    async def control(request):
        by, by_id = request.get(ACTOR_KEY) or ("the controller", None)
        with acting(by, by_id):
            reply = await control_as(request)
            action = request.get(ACTION_KEY)
            if action and action not in OWN_EVENT:
                log.emit("control", action=action)     # pause, resume, stop, settings: "Paused, from Pixel phone"
        return reply

    async def control_as(request):
        from .models import save_prefs
        body = await request.json()
        action = body.get("action")
        request[ACTION_KEY] = action
        if action == "pause":
            pilot.pause()
        elif action == "resume":
            pilot.resume()
        elif action == "stop":
            pilot.stop()
        elif action == "instruct" and body.get("text", "").strip():
            pilot.instruct(body["text"].strip())
        elif action == "set_models" and hasattr(pilot, "set_models"):
            try:
                pilot.set_models(body.get("models") or [], body.get("rotate"))
            except ValueError as e:
                raise web.HTTPBadRequest(text=str(e)) from e
        elif action == "set_roles" and hasattr(pilot, "set_roles"):
            try:
                pilot.set_roles(body.get("roles") or {})
            except ValueError as e:
                raise web.HTTPBadRequest(text=str(e)) from e
        elif action == "edit_pillar" and hasattr(pilot, "edit_pillar"):
            fields = body.get("fields")
            try:
                pilot.edit_pillar(str(body.get("pillar", "")), {} if fields is None else fields)
            except (ValueError, TypeError) as e:
                raise web.HTTPBadRequest(text=str(e)) from e
        elif action == "unpin_pillar" and hasattr(pilot, "unpin_pillar"):
            try:
                pilot.unpin_pillar(str(body.get("pillar", "")))
            except ValueError as e:
                raise web.HTTPBadRequest(text=str(e)) from e
        elif action == "review_strategy" and hasattr(pilot, "request_review"):
            try:
                pilot.request_review()
            except ValueError as e:
                raise web.HTTPBadRequest(text=str(e)) from e
        elif action == "set_fallback" and hasattr(pilot, "set_fallback"):
            try:
                pilot.set_fallback(str(body.get("model", "")) or None)
            except ValueError as e:
                raise web.HTTPBadRequest(text=str(e)) from e
        elif action == "set_model" and hasattr(pilot, "set_model"):
            try:
                pilot.set_model(str(body.get("model", "")), body.get("thinking") or None)
            except ValueError as e:
                raise web.HTTPBadRequest(text=str(e)) from e
        elif action == "set_speed" and hasattr(pilot, "set_speed"):
            try:
                pilot.set_speed(str(body.get("speed", "")))
                save_prefs(runs_dir, speed=str(body.get("speed", "")))
            except ValueError as e:
                raise web.HTTPBadRequest(text=str(e)) from e
        elif action == "set_months" and hasattr(pilot, "set_months"):
            try:
                months = int(body.get("months"))
                pilot.set_months(months)
                save_prefs(runs_dir, months=months)
            except (ValueError, TypeError) as e:
                raise web.HTTPBadRequest(text=str(e)) from e
        elif action == "answer" and body.get("text", "").strip() and hasattr(pilot, "answer"):
            pilot.answer(body["text"].strip())
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
            raise web.HTTPBadRequest(text="action must be pause|resume|stop|instruct|answer|set_model|set_models|set_roles|set_fallback|set_speed|set_months|chat|order_add|order_remove|"
                                          "decide_now|override|edit_pillar|unpin_pillar|review_strategy, with its text/index/directive/pillar/fields")
        return web.json_response({"ok": True, "status": log.state.status})

    app = web.Application(middlewares=[service.middleware])
    app[AUTH_KEY] = service
    app.on_response_prepare.append(service.on_prepare)
    app.add_routes([web.get("/", index), web.get("/status", status), web.get("/frame.jpg", frame),
                    web.get("/events", events), web.get("/events.json", events_json), web.post("/control", control),
                    web.post("/api/capture", capture), *history, *api])
    return app


def serve_in_background(pilot, host: str, port: int, runs_dir: Path | None = None,
                        telemetry=None) -> threading.Thread:
    def run() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        runner = web.AppRunner(make_app(pilot, runs_dir, telemetry), **RUNNER_KWARGS)
        loop.run_until_complete(runner.setup())
        loop.run_until_complete(web.TCPSite(runner, host, port).start())
        loop.run_forever()

    t = threading.Thread(target=run, daemon=True, name="dashboard")
    t.start()
    return t
