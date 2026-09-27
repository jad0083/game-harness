"""Opt-in notices outside the page (docs/design/2026-09-27-dashboard-v2-design.md, ruling 8).

When the run needs the human for 5 minutes, again at 30 minutes and at 2 hours, and once when it no
longer does, the live pilot posts one line to an ntfy topic: `PILOT_NOTIFY_URL`, the topic's full URL
(e.g. a self-hosted server, or a long random topic on a public one). Unset, or not an http(s) URL, and
nothing is sent: it is off by default. The message names the game, what stopped (the view's recovery
title for the stop's category) and for how long, "Game Pilot needs you: Civ VI, autoplay did not
start at T57 (5 min)", with the dashboard's plain address as its click action (`PILOT_PUBLIC_URL`, else
this machine's LAN address on 8780). It never carries a key, a cookie or a token. Web Notifications and
Web Push need a secure context, which plain HTTP on the LAN is not.

A daemon thread reads the run's state every 15 s; posting happens there, so a slow or failing server
never holds the game loop, and a failure is logged and forgotten.
"""

from __future__ import annotations

import logging
import os
import threading
import time
import urllib.request
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

MARKS = (300, 1800, 7200)          # seconds a stop has lasted when a notice goes out
VIEWER_PORT = 8780                 # the always-on dashboard (deploy/game-pilot-view.service)
TIMEOUT_S = 10


def duration(seconds: float) -> str:
    """'5 min', '2 h', '2 h 1 min'; whole minutes, rounded down."""
    m = int(seconds // 60)
    if m < 1:
        return "less than a minute"
    h, m = divmod(m, 60)
    return f"{h} h {m} min" if h and m else f"{h} h" if h else f"{m} min"


def _gdate(d: str) -> str:
    """'2288.08.01' reads '2288.08' (the day is always the 1st); 'T57' stays."""
    parts = str(d or "").split(".")
    return ".".join(parts[:2]) if len(parts) == 3 and all(p.isdigit() for p in parts) else str(d or "")


def http_post(url: str, body: str, headers: dict[str, str]) -> None:
    req = urllib.request.Request(url, data=body.encode("utf-8"), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:     # an http(s) URL, checked in notifier_from_env
        r.read(256)


class Notifier:
    """Watches one run's state; `check` posts at most one notice per call and returns what it sent."""

    def __init__(self, url: str, dashboard_url: str, post: Callable[[str, str, dict], None] = http_post,
                 corpora: Path | None = None):
        from .view import Views
        if corpora is None:
            from .config import REPO
            corpora = REPO / "corpora"
        self.url, self.dashboard_url, self.post = url, dashboard_url.rstrip("/"), post
        self.views = Views(corpora)
        self._stop_key: float | None = None        # the stop being watched (its `since`)
        self._sent: set[int] = set()               # marks already sent for it
        self._seen: float | None = None            # first seen, for a pilot that sends no `attention`

    def _words(self, game: str) -> tuple[str, dict]:
        view = self.views.get(game or "")
        return view["game"].get("short") or game or "the game", view.get("recovery") or {}

    def _send(self, text: str, tags: str, priority: str) -> str:
        headers = {"Title": "Game Pilot", "Click": self.dashboard_url, "Tags": tags, "Priority": priority}
        try:
            self.post(self.url, text, headers)
        except Exception as e:  # noqa: BLE001 - a notice must never stop the run
            log.warning("notice not sent: %s", e)
        return text

    def check(self, state: Any, now: float | None = None) -> str | None:
        now = time.time() if now is None else now
        info = getattr(state, "info", None) or {}
        status = getattr(state, "status", "")
        game, recovery = self._words(info.get("game", ""))
        if status == "needs_attention":
            att = info.get("attention") or {}
            if self._seen is None:
                self._seen = now
            since = float(att.get("since") or self._seen)
            if since != self._stop_key:
                self._stop_key, self._sent = since, set()
            due = [m for m in MARKS if now - since >= m and m not in self._sent]
            if not due:
                return None
            self._sent.update(due)
            title = (recovery.get(att.get("category") or "") or {}).get("title") or "The run stopped"
            date = _gdate(att.get("date") or getattr(state, "game_date", ""))
            what = title[:1].lower() + title[1:] + (f" at {date}" if date else "")
            return self._send(f"Game Pilot needs you: {game}, {what} ({duration(now - since)})", "warning", "high")
        self._seen = None
        if self._stop_key is None:
            return None
        since, sent = self._stop_key, bool(self._sent)
        self._stop_key, self._sent = None, set()
        if not sent:                                # over before the first notice: nothing to take back
            return None
        date = _gdate(getattr(state, "game_date", ""))
        at = f" at {date}" if date else ""
        how = {"paused": f"paused{at}", "stopped": f"the run stopped{at}"}.get(status, f"{game} is playing again{at}")
        lead = f"{game}, " if status in ("paused", "stopped") else ""
        return self._send(f"Game Pilot no longer needs you: {lead}{how} (after {duration(now - since)})",
                          "white_check_mark", "default")

    def start(self, log_: Any, stop: threading.Event | None = None, every: float = 15.0) -> threading.Thread:
        """Check `log_.state` every `every` seconds in a daemon thread until `stop` is set."""
        stop = stop or threading.Event()

        def watch() -> None:
            while not stop.wait(every):
                try:
                    self.check(log_.state)
                except Exception as e:  # noqa: BLE001 - keep watching
                    log.warning("notice check failed: %s", e)

        t = threading.Thread(target=watch, daemon=True, name="notify")
        t.start()
        return t


def notifier_from_env(env: Mapping[str, str] | None = None) -> Notifier | None:
    """A Notifier when PILOT_NOTIFY_URL is an http(s) URL; None (off) otherwise."""
    env = os.environ if env is None else env
    url = (env.get("PILOT_NOTIFY_URL") or "").strip()
    if not url:
        return None
    if not url.startswith(("https://", "http://")):
        log.warning("PILOT_NOTIFY_URL is not an http(s) URL; notices are off")
        return None
    public = (env.get("PILOT_PUBLIC_URL") or "").strip().rstrip("/")
    if not public:
        from .auth import lan_address
        public = f"http://{lan_address()}:{VIEWER_PORT}"
    return Notifier(url, public)


def start_notifier(log_: Any, env: Mapping[str, str] | None = None) -> threading.Thread | None:
    """The live pilot's notice thread, or None when notices are off (the default)."""
    n = notifier_from_env(env)
    return n.start(log_) if n else None
