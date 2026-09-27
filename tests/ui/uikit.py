"""Helpers for the dashboard's browser tests: a fixture server in its own thread, a fake live pilot,
and browser contexts with their errors collected."""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path

from aiohttp import web

from pilot.events import EventLog
from pilot.telemetry import Telemetry

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


PC_CIV6 = {"online": True, "state": "on", "host": "mini-rig2", "version": "1.6.1", "games": ["civ6"], "game_in_front": True,
           "front_game": "civ6"}
MODELS = ["google:gemini-3.8-flash", "google:gemini-3.1-pro-preview"]
CIV6_METRICS = [{"date": f"T{t}", "turn": t, "score": 40 + t, "military": 300 + 5 * t, "science": 20.5 + t / 10,
                 "culture": 12.0 + t / 20, "faith_yield": 4.0, "gold_yield": 9.5 + t / 10, "production": 30 + t / 5,
                 "gold": 200 + t, "faith": 60 + t, "cities": 5 + t // 20, "techs_known": 20 + t // 3,
                 "civics_known": 18 + t // 4, "pop": 30 + t // 2, "wars": 1 if t >= 55 else 0,
                 "peers": {"score": {"rank": 1, "median": 80, "ours": 40 + t}, "military": {"rank": 2, "median": 560, "ours": 300 + 5 * t},
                           "techs": {"rank": 4, "median": 42, "ours": 20 + t // 3}, "civics": {"rank": 2, "median": 30, "ours": 18 + t // 4},
                           "cities": {"rank": 2, "median": 6, "ours": 5 + t // 20}},
                 "peer_count": 3,
                 "neighbours": [{"name": "CIVILIZATION_GERMANY", "military": 700, "score": 88, "cities": 6, "at_war": t >= 55},
                                {"name": "CIVILIZATION_NETHERLANDS", "military": 420, "score": 75, "cities": 4, "at_war": False},
                                {"name": "CIVILIZATION_AUSTRALIA", "military": 510, "score": 80, "cities": 5, "at_war": False}]}
                for t in range(50, 58)]
CIV6_STRATEGY = {"focus": "Hold Chengdu, then out-tech Germany", "identity": "Kublai Khan's trading posts:\n- a free "
                 "economic policy slot\n- Eureka and Inspiration from each new trading post\nso traders pay twice.",
                 "reason": "war with Germany",
                 "pillars": {"military": {"weight": 30, "priority": 1, "stance": "Two slingers per threatened city (military 560 median).",
                                          "goals": ["Hold Chengdu"], "prefer_production": ["unit:slinger"], "milestones": []},
                             "science": {"weight": 25, "priority": 2, "stance": "Campus in every city (science 25.6).",
                                         "goals": ["Writing then Currency"], "prefer_techs": ["tech:writing"], "milestones": []},
                             "economy": {"weight": 20, "priority": 3, "stance": "Traders to Beijing (gold 9.5 a turn).",
                                         "goals": ["Two traders"], "prefer_production": ["unit:trader"], "milestones": []},
                             "culture": {"weight": 10, "priority": 4, "stance": "Monuments (culture 14.6).", "goals": [],
                                         "milestones": []},
                             "faith": {"weight": 5, "priority": 5, "stance": "Keep 25 faith for a pantheon (faith 117).",
                                       "goals": [], "milestones": []},
                             "expansion": {"weight": 5, "priority": 6, "stance": "A settler once Chengdu holds (7 cities).",
                                           "goals": [], "milestones": []},
                             "diplomacy": {"weight": 5, "priority": 7, "stance": "Peace with Australia (score 80).",
                                           "goals": [], "milestones": []}}}


def _trace(log: EventLog, n: int, **fields) -> None:
    log.state.episodes = n
    log.save_trace(n, {"episode": n, "model": "google:gemini-3.1-pro-preview", "thinking_level": "medium",
                       "game": fields.get("game", "civ6"), "current": None, "seconds": 63.0,
                       "tokens_in": 41000, "tokens_out": 1200,
                       "steps": [{"type": "prompt", "text": "briefing"}], **fields})


def seed_runs(runs: Path) -> dict:
    """runs/ with a finished Stellaris campaign and a live Civ VI run (its EventLog, playing at T57).
    Used by the browser tests' fixtures and by scratch scripts that serve the same data."""
    tel = Telemetry(runs / "telemetry.sqlite")
    old = EventLog(runs, "20260926-090000", "google:gemini-3.8-flash", telemetry=tel)
    old.emit("run_start", game="stellaris", model="google:gemini-3.8-flash", speed="fast")
    old.set_campaign("stellaris", "theia", "Theian Union")
    for i, mo in enumerate(range(1, 7)):
        old.emit("metrics", date=f"2288.{mo:02d}.01", systems=20 + i, planets=8, pops=90 + i, techs_known=140 + i,
                 net={"energy": 40 + i, "minerals": 30, "food": 10, "alloys": 12, "influence": 2, "unity": 8},
                 stockpile={"energy": 900, "minerals": 800, "food": 500, "alloys": 300, "influence": 100, "unity": 400},
                 military_power=5000 + 100 * i, economy_power=3000, tech_power=2000, directive="expand",
                 room=3, room_surveyed=2, construction_ships=1, behind=["pops"] if i > 3 else [],
                 peers={"systems": {"rank": 3, "median": 18}, "pops": {"rank": 6, "median": 200},
                        "techs": {"rank": 4, "median": 150}, "military_power": {"rank": 2, "median": 4000}},
                 peer_count=8,
                 neighbours=[{"name": "Tzynn Empire", "military": 9000, "economy": 2500, "tech": 2100, "systems": 30,
                              "opinion": -40, "status": ["rival", "on our border"]},
                             {"name": "Glebsig Foundation", "military": 3000, "economy": 5000, "tech": 1900,
                              "systems": 15, "opinion": 60, "status": ["commercial pact"]}])
    _trace(old, 1, game="stellaris", date="2288.03.01", trigger="scheduled", decision="expand",
           reason="Room to grow toward the core.", outcome="applied", current="diplomacy_first")
    old.state.status = "stopped"
    old.emit("run_end")
    old.close()

    log = EventLog(runs, "20260927-100000", "google:gemini-3.8-flash", telemetry=tel)
    log.emit("run_start", game="civ6", model="google:gemini-3.8-flash")
    log.set_campaign("civ6", "kublai", "Kublai Khan, China")
    for m in CIV6_METRICS:
        log.emit("metrics", **m)
    log.emit("strategy", date="T50", trigger="start of run", model="google:gemini-3.1-pro-preview",
             reason=CIV6_STRATEGY["reason"], strategy={k: v for k, v in CIV6_STRATEGY.items() if k != "reason"})
    _trace(log, 1, date="T52", trigger="scheduled (5 turns)", decision="orders", outcome="research tech:writing: stuck",
           reason="Chengdu is under siege; buy a slinger with faith and keep science on Writing while the walls hold. "
                  "Germany's army is twice ours near the border, so the second city needs a defender before any builder.",
           orders=[{"order": "research tech:writing", "outcome": "stuck", "kind": "research", "id": "tech:writing", "city": ""},
                   {"order": "production unit:slinger in Chengdu", "outcome": "stuck", "kind": "production",
                    "id": "unit:slinger", "city": "Chengdu"},
                   {"order": "purchase building:gurdwara in Beijing with faith", "outcome": "refused: 380 faith, over "
                    "the 283 allowed", "kind": "purchase", "id": "building:gurdwara", "city": "Beijing"},
                   {"order": "civic civic:foreign_trade", "outcome": "unknown: no reply (TimeoutError: timed out)",
                    "kind": "civic", "id": "civic:foreign_trade", "city": ""},
                   {"order": "purchase unit:warrior in Xian", "outcome": "stuck", "kind": "purchase", "id": "unit:warrior",
                    "city": "Xian"}])
    log.emit("order_outcome", order_kind="production", key="production replace", id="unit:slinger", city="Chengdu",
             ordered="T52", result="overridden", by="unit:trader", turns=2, date="T54", turn=54)
    tel._exec("UPDATE decisions SET result=? WHERE run_id=? AND episode=1",
              ('{"score": 17, "science": 8.1, "military": -226, "pop": 2, "months": 12, "unit": "turns"}', log.state.run_id))
    _trace(log, 2, date="T55", trigger="urgent: city threatened: Chengdu (2 enemy units near)", outcome="error",
           error="ModelHTTPError: status_code: 503, model_name: gemini-3.8-flash, body: {'error': {'code': 503, "
                 "'message': 'This model is currently experiencing high demand.'}}")
    log.emit("order_outcome", order_kind="research", key="research", id="tech:writing", city="", ordered="T52",
             result="completed", by=None, turns=3, date="T55", turn=55)
    log.emit("order_outcome", order_kind="purchase", key="purchase faith", id="building:gurdwara", city="Beijing",
             currency="faith", ordered="T52", result="refused", by=None, turns=0, date="T52", turn=52,
             detail="refused: 380 faith, over the 283 allowed")
    log.emit("order_followed", ref="f1", row={"order_kind": "civic", "key": "civic", "id": "civic:foreign_trade", "city": "",
                                              "ordered": "T52", "ref": "f1"},
             order={"kind": "civic", "id": "civic:foreign_trade"}, wire=None, expect={}, base={"turn": 52}, window=8)
    log.emit("last_stand", city="Chengdu", turn=54, date="T54", in_a_row=1, ran=True, stopped="done: nothing left to do",
             actions=[{"action": "city_strike", "result": "took", "detail": "the target lost 28", "predicted": 28}], pins=[])
    info = log.state.info
    info.update(game="civ6", decide_turns=5, directives=[], controls=["instruct", "chat", "order_add", "order_remove",
                                                                        "decide_now", "set_models", "set_months"],
                reserves={"gold": 257, "gold_keep": 46, "gold_rule": "30 + 10 for each gold of deficit a turn (1.6 now)",
                          "faith": 117, "faith_keep": 25, "faith_for": "for the pantheon", "in_danger": ["Chengdu"],
                          "date": "T57"},
                last_stand={"on": True, "max": 3, "in_a_row": 1, "off_reason": "", "active": None},
                game_health={"popups": {"quieted": 5, "total": 6, "turn": 50, "failed": ["ProjectBuiltPopup.OnProjectComplete"]},
                             "timeouts": 3, "calls": 40, "last_turn_s": 42.0, "held": False})
    log.state.game_date = "T57"
    log.state.status = "playing"
    return {"runs": runs, "tel": tel, "log": log, "pilot": FakePilot(log)}


# The Stellaris levers' data as docs/design/2026-09-27-stellaris-levers-design.md shapes it (rulings 2-6,
# 13, 18; dashboard rulings 23-26): the pilot does not publish it yet, so the page renders it only when
# it is there. Order-record rows are the Civ VI shape with Stellaris keys and fates.
STELLARIS_RECORD = {
    "directive defend": {"judged": 3, "took": 2, "held": 0, "overridden": 1, "failed": 0, "min_samples": 3, "rate": 0.67,
                         "weak": False, "excluded": {"superseded": 1, "locked": 1},
                         "last_override": {"id": "economic_policy", "by": "civilian_economy", "date": "2291.01.01"}},
    "market buy alloys": {"judged": 2, "took": 0, "did_not_take": 2, "min_samples": 3, "rate": None, "weak": False,
                          "excluded": {}, "suspended": True},
    "tech": {"judged": 5, "researched": 3, "held": 1, "did_not_stick": 1, "min_samples": 3, "rate": 0.8, "weak": False,
             "excluded": {"no_op": 53}},
    "posture naval_cap": {"judged": 1, "took": 1, "min_samples": 3, "rate": None, "weak": False, "excluded": {}},
}
STELLARIS_CRISIS = {"since": "2291.03.01", "reasons": ["a colony occupied (Arnvoss)", "lost 2 systems"],
                    "step": {"n": 2, "of": 4, "text": "defensive stance"}, "boost": {"pillar": "defence", "need": 2.0}}
STELLARIS_POSTURES = [{"name": "naval_cap", "label": "naval capacity", "on": True, "enabled": True},
                      {"name": "ship_upgrades", "label": "ship upgrades", "on": False, "enabled": False}]
STELLARIS_MARKET = {"kind": "galactic", "fluct": {"alloys": 14.0, "energy": -8.0}, "bought": {"alloys": 20}, "sold": {"energy": 100},
                    "trades_net": {"alloys": 5, "energy": -10}}
STELLARIS_STRATEGY = {"focus": "Hold the core until the war ends", "identity": "A fortress empire.", "reason": "war crisis",
                      "pillars": {name: {"weight": w, "priority": i + 1, "stance": f"{name} stance (military 5,200).", "goals": [],
                                         "milestones": [], **({"market": [{"side": "buy", "resource": "alloys", "amount": 5}]}
                                                              if name == "economy" else {})}
                                  for i, (name, w) in enumerate((("defence", 30), ("economy", 20), ("technology", 15),
                                                                 ("expansion", 10), ("diplomacy", 10), ("government", 10),
                                                                 ("society", 5)))}}


def _seed_stellaris(runs: Path, out: dict) -> dict:
    """The live run is a Stellaris campaign in a war crisis, with the levers' data (the Civ VI run ended)."""
    old, tel = out["log"], out["tel"]
    old.state.status = "stopped"
    old.emit("run_end")
    old.close()
    log = EventLog(runs, "20260927-120000", "google:gemini-3.8-flash", telemetry=tel)
    log.emit("run_start", game="stellaris", model="google:gemini-3.8-flash", speed="fast")
    log.set_campaign("stellaris", "gaea", "Blooms of Gaea")
    for i, mo in enumerate(range(1, 8)):
        log.emit("metrics", date=f"2291.{mo:02d}.01", systems=30 - (2 if mo >= 3 else 0), planets=9, pops=120, techs_known=200 + i,
                 net={"energy": 40, "minerals": 30, "food": 10, "alloys": 12, "influence": 2, "unity": 8},
                 stockpile={"energy": 900, "minerals": 800, "food": 500, "alloys": 300, "influence": 100, "unity": 400},
                 military_power=5200 - 300 * i, economy_power=3000, tech_power=2000, directive="defend", wars=1,
                 crisis=mo >= 3, market=STELLARIS_MARKET, postures=STELLARIS_POSTURES,
                 peers={"systems": {"rank": 3, "median": 28}}, peer_count=8)
    log.emit("strategy", date="2291.03.01", trigger="war going badly: C1, C2", model="google:gemini-3.1-pro-preview",
             reason=STELLARIS_STRATEGY["reason"], strategy={k: v for k, v in STELLARIS_STRATEGY.items() if k != "reason"})
    _trace(log, 1, game="stellaris", date="2291.03.01", trigger="urgent: war going badly: a colony occupied (Arnvoss)",
           decision="defend", reason="Arnvoss is occupied; hold the chokepoints.", outcome="applied", current="expand",
           applied={"set": ["economic_policy"], "locked": [{"policy": "diplomatic_stance", "why": "at war"}], "in_force": []})
    log.state.info.update(game="stellaris", every_months=12, speed="fast", directive="defend", directives=["expand", "defend"],
                          controls=["instruct", "chat", "decide_now", "override", "order_add", "order_remove"],
                          order_record=STELLARIS_RECORD, crisis=STELLARIS_CRISIS, postures=STELLARIS_POSTURES)
    log.state.game_date = "2291.07.01"
    log.state.status = "playing"
    return {**out, "log": log, "pilot": FakePilot(log)}


def _jpeg() -> bytes:
    """A small game-screen stand-in (Pillow is a dev dependency; without it no frame)."""
    try:
        import io

        from PIL import Image
    except ImportError:                  # pragma: no cover
        return b""
    buf = io.BytesIO()
    Image.new("RGB", (160, 90), (40, 60, 90)).save(buf, "JPEG")
    return buf.getvalue()


def seed_scenario(runs: Path, scenario: str = "playing") -> dict:
    """seed_runs, then the live Civ VI run in one of the governor line's states: playing, needs (autoplay
    did not start at T57, 6 h 52 min ago), deciding (the fallback model's second call), paused, question;
    or a live Stellaris run with the levers' data (stellaris)."""
    import time
    out = seed_runs(runs)
    log, st = out["log"], out["log"].state
    now = time.time()
    if scenario == "needs":
        log.emit("briefing_error", error="autoplay at T57: Error: Failed /tuner/lua\n\nCaused by:\n    0: operation timed out")
        st.status = "needs_attention"
        st.info["attention"] = {"reason": "autoplay did not start at T57 (still inactive after 21 s). Check the game "
                                          "(a dialog, a crash, the main menu), then press Resume.",
                                "category": "transient", "since": now - 24720, "date": "T57", "date_now": "T57",
                                "auto_recover": False, "next_probe_at": None, "probes": 0,
                                "errors": ["the game's tuner did not answer (timed out)"],
                                "raw": ["autoplay at T57: Error: Failed /tuner/lua\n\nCaused by:\n    0: operation timed out"],
                                "frame": ""}
        log.emit("needs_attention", reason=st.info["attention"]["reason"], category="transient")
    elif scenario == "needs_old":          # a pilot from before info.attention: only the event
        st.status = "needs_attention"
        log.emit("needs_attention", reason="game control failed: RuntimeError: the tuner is off. Fix the game, then Resume.")
    elif scenario == "deciding":
        st.status = "deciding"
        st.info["deciding"] = {"since": now - 72, "trigger": "urgent: city threatened: Chengdu (2 enemy units near)",
                               "model": "google:gemini-3.1-pro-preview", "attempt": 2, "max_attempts": 2, "retry_at": None,
                               "retries": 0, "after": [{"model": "google:gemini-3.8-flash", "error": "overloaded (503)"}]}
    elif scenario == "paused":
        st.status = "paused"
        from pilot.events import acting
        with acting("Pixel phone", "d1"):
            log.emit("control", action="pause")
    elif scenario == "stellaris":
        return _seed_stellaris(runs, out)
    elif scenario == "question":
        st.pending_question = "Apply 'prepare_war'? The Tzynn border fleets outnumber ours."
        st.question_deadline, st.default_if_silent = now + 45, "no"
    return out


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
        self.log.state.info.pop("attention", None)

    def stop(self):
        self.calls.append("stop")

    def instruct(self, text):
        self.calls.append(("instruct", text))
        self.log.emit("instruction", text=text)

    def answer(self, text):
        self.calls.append(("answer", text))
        self.log.state.pending_question, self.log.state.question_deadline = "", 0.0

    @property
    def game(self):
        """The game's screen, for "Capture the game screen"."""
        class Game:
            def screenshot(self):
                return type("Shot", (), {"image": _jpeg()})()
        return Game()


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


def open_context(browser, name: str, servers: dict, *, signed_in: bool = True, device: str = "Chrome on Windows",
                 **extra) -> Watched:
    """A fresh browser context (one of CONTEXTS) on the fixture viewer, with fonts stubbed (no
    request leaves the box) and, when signed_in, its own device session from the viewer's store."""
    ctx = browser.new_context(**{**CONTEXTS[name], **extra})
    ctx.route("https://fonts.googleapis.com/**", lambda r: r.fulfill(status=200, content_type="text/css", body=""))
    ctx.route("https://fonts.gstatic.com/**", lambda r: r.fulfill(status=200, body=b""))
    w = Watched(ctx, ctx.new_page())
    w.base = servers["viewer"].url
    w.device = sign_in(ctx, w.base, servers["auth"], device) if signed_in else None
    return w


def show(page, where: str) -> None:
    """Bring a destination on screen: a reader tab on a desktop; on a phone its bottom-nav view (ruling
    1: Activity is at the end of Now, under "All activity")."""
    if page.is_visible("#bottom-nav"):
        if where == "activity":
            page.click('#bottom-nav a[data-view="now"]')
            if page.get_attribute("#all-activity", "aria-expanded") != "true":
                page.click("#all-activity")
        else:
            page.click(f'#bottom-nav a[data-view="{where}"]')
    else:
        page.click(f'.tabs button[data-tab="{where}"]')
    page.wait_for_timeout(200)


def pick_campaign(page, cid: str) -> None:
    """Switch the page to another campaign through the campaign list (ruling 4)."""
    page.click("#campaign")
    page.wait_for_selector("#camp-dialog[open]")
    page.click(f'#camp-dialog button[data-cid="{cid}"]')
    page.wait_for_function(f"document.getElementById('campaign').dataset.cid === {cid!r}")
    page.wait_for_timeout(300)


def sign_in(ctx, base: str, auth, name: str = "Chrome on Windows") -> str:
    """Give the context a session cookie as a sign-in would; returns the device id."""
    row, cred = auth.store.create_device("browser", name=name, created_via="cli", created_by="cli", ip="127.0.0.1")
    ctx.add_cookies([{"name": "pilot_session", "value": cred, "url": base, "httpOnly": True, "sameSite": "Lax"}])
    return row["id"]


# Contrast of every visible piece of text against what is behind it (WCAG 2 formula): colours are
# read from computed styles, backgrounds composited up the ancestors. Disabled controls are exempt.
CONTRAST_JS = r"""
(root) => {
  const parse = (c) => {
    let m = /^rgba?\(([^)]*)\)$/.exec(c);
    if (m) { const p = m[1].split(/[\s,\/]+/).filter(Boolean).map(Number); return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; }
    m = /^color\(srgb ([^)]*)\)$/.exec(c);
    if (m) { const p = m[1].split(/[\s\/]+/).filter(Boolean).map(Number); return [p[0] * 255, p[1] * 255, p[2] * 255, p.length > 3 ? p[3] : 1]; }
    return null;
  };
  const over = (top, under) => { const a = top[3]; return [0, 1, 2].map((i) => top[i] * a + under[i] * (1 - a)).concat(1); };
  const lum = (c) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
                       return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); };
  const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  const bgOf = (el) => {
    const chain = [];
    for (let e = el; e && e.nodeType === 1; e = e.parentElement) chain.push(getComputedStyle(e).backgroundColor);
    let bg = [255, 255, 255, 1];
    for (const c of chain.reverse()) { const p = parse(c); if (p && p[3] > 0) bg = over(p, bg); }
    return bg;
  };
  const out = [], seen = new Set();
  const all = (root || document).querySelectorAll("body *");
  for (const el of all) {
    if (el.closest("[disabled], [aria-disabled='true'], .sr, script, style, option, title")) continue;
    const svgText = el instanceof SVGTextElement;
    const own = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
    if (!own) continue;
    if (!el.getClientRects().length) continue;
    const cs = getComputedStyle(el);
    if (cs.visibility === "hidden" || +cs.opacity === 0) continue;
    const fg = parse(svgText ? cs.fill : cs.color);
    if (!fg) { out.push(`unparsed colour ${svgText ? cs.fill : cs.color} on ${el.tagName}`); continue; }
    if (fg[3] === 0) continue;
    const bg = bgOf(el);
    const r = ratio(over(fg, bg), bg);
    const size = parseFloat(cs.fontSize), bold = parseInt(cs.fontWeight, 10) >= 700;
    const need = size >= 24 || (size >= 18.66 && bold) ? 3 : 4.5;
    if (r + 1e-6 < need) {
      const text = el.textContent.trim().replace(/\s+/g, " ").slice(0, 40);
      const key = `${el.className && el.className.baseVal !== undefined ? el.className.baseVal : el.className}|${cs.color}|${text}`;
      if (!seen.has(key)) { seen.add(key); out.push(`${r.toFixed(2)} < ${need}: <${el.tagName.toLowerCase()} class="${el.getAttribute("class") || ""}"> "${text}" (${svgText ? cs.fill : cs.color} on rgb(${bg.slice(0, 3).map(Math.round)}), ${size}px)`); }
    }
  }
  return out;
}
"""


def contrast_failures(page, root: str | None = None) -> list[str]:
    """Text on the page (or inside the element matching `root`) below WCAG AA contrast."""
    handle = page.query_selector(root) if root else None
    return page.evaluate(CONTRAST_JS, handle)
