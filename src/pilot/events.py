"""Run log and live state: every event goes to the store's events table (pilot.db) and to live
subscribers (the dashboard's server-sent events); the run's state is kept in run_state; frames are
JPEG files under <data>/frames/<run_id>/."""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import json
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .store import open_store

# A store write that fails is printed and play goes on, but this many failures in a row (a full disk, an
# unwritable data directory) raise from emit, so the run stops loudly as a failed journal or learned write
# does; a successful write starts the count again.
STORE_FAILURES_TO_STOP = 10

# Who asked for what is running now (a device named by the viewer, or "the controller"): events
# emitted while a dashboard control runs carry it as `by` (and `by_id`).
ACTOR: contextvars.ContextVar[tuple[str, str | None] | None] = contextvars.ContextVar("pilot_actor", default=None)


@contextlib.contextmanager
def acting(by: str, by_id: str | None = None):
    token = ACTOR.set((by, by_id))
    try:
        yield
    finally:
        ACTOR.reset(token)


@dataclass
class RunState:
    run_id: str
    model: str
    status: str = "starting"           # starting | playing | deciding | paused | stopped | needs_attention | ended
    turns_advanced: int = 0
    episodes: int = 0
    last_stop: str = ""
    last_decision: str = ""
    game_date: str = ""                # latest in-game date reported by a decision
    learned: dict[str, int] = field(default_factory=lambda: {"screens": 0, "rules": 0, "controls": 0})
    tokens_in: int = 0
    tokens_out: int = 0
    requests: int = 0
    pending_question: str = ""
    question_deadline: float = 0.0     # when an open question times out (wall clock), 0 when none
    default_if_silent: str = ""        # what the governor does when nobody answers ("no")
    started_at: float = field(default_factory=time.time)
    frame_path: str = ""
    info: dict[str, Any] = field(default_factory=dict)   # game-specific: game, speed, directive…
    # info also carries what the dashboard shows while it lasts: `attention` (why the run needs the
    # human, docs/design/2026-09-27-dashboard-v2-design.md ruling 7), `deciding` (the decision being
    # made, ruling 11) and `answered` (the model that gave the last decision, ruling 6)

    def as_dict(self) -> dict[str, Any]:
        d = dict(self.__dict__)
        d["uptime_s"] = round(time.time() - self.started_at)
        return d


class EventLog:
    def __init__(self, runs_dir: Path, run_id: str, model: str, telemetry=None, frames_keep: int = 200):
        """`runs_dir` is the data directory; `telemetry` is its store (default: `open_store(runs_dir)`)."""
        self.store = telemetry if telemetry is not None else open_store(runs_dir)
        self.telemetry = self.store         # the name the governors read
        self.dir = runs_dir / "frames" / run_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.frames_keep = frames_keep
        self._kept: set[str] = set()        # frames exempt from retention until released (a needs-you card's)
        self.state = RunState(run_id=run_id, model=model)
        self.recent: deque[dict] = deque(maxlen=300)
        self._lock = threading.Lock()
        self._subscribers: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = []
        self._frame_n = 0
        self._store_failures = 0            # failed store writes in a row (STORE_FAILURES_TO_STOP)
        self.campaign_id: str | None = None

    def frame(self, jpeg: bytes | None, keep: bool = False) -> str:
        """Save a frame as NNNNN.jpg and latest.jpg in the run's frames directory; returns its name ('' if
        none). The newest `frames_keep` numbered frames stay, and those saved with `keep` until released."""
        if not jpeg:
            return ""
        with self._lock:
            self._frame_n += 1
            name = f"{self._frame_n:05d}.jpg"
            if keep:
                self._kept.add(name)
        (self.dir / name).write_bytes(jpeg)
        (self.dir / "latest.jpg").write_bytes(jpeg)
        self._prune()
        self.state.frame_path = name
        return name

    def release(self, name: str) -> None:
        """A frame saved with `keep` falls under retention again (deleted by a later frame's pruning)."""
        with self._lock:
            self._kept.discard(name)

    def _prune(self) -> None:
        """Delete the oldest numbered frames beyond `frames_keep`, kept ones aside."""
        with self._lock:
            kept = set(self._kept)
        frames = [p for p in sorted(self.dir.glob("[0-9]*.jpg")) if p.name not in kept]
        for p in frames[:max(0, len(frames) - self.frames_keep)]:
            p.unlink(missing_ok=True)       # another thread's pruning may have taken it first

    def emit(self, kind: str, _trace: dict | None = None, **data: Any) -> dict:
        actor = ACTOR.get()
        if actor and "by" not in data and not (kind == "chat" and data.get("role") == "model"):
            data["by"] = actor[0]
            if actor[1]:
                data["by_id"] = actor[1]
        ev = {"t": round(time.time(), 3), "kind": kind, **data}
        with self._lock:
            self.recent.append(ev)
            subs = list(self._subscribers)
        try:
            self.store.record(self.state.run_id, ev, _trace)
            self.store._exec("INSERT INTO run_state(run_id, data, updated) VALUES (?,?,?) ON CONFLICT(run_id)"
                             " DO UPDATE SET data=excluded.data, updated=excluded.updated",
                             (self.state.run_id, json.dumps(self.state.as_dict(), default=str), time.time()))
        except Exception as e:      # a transient store failure never stops play; a lasting one does (re-raised)
            with self._lock:
                self._store_failures += 1
                failures = self._store_failures
            print(f"store write failed: {e}", flush=True)
            if failures >= STORE_FAILURES_TO_STOP:
                print(f"{failures} store writes failed in a row; the run stops", flush=True)
                raise
        else:
            with self._lock:
                self._store_failures = 0
        for loop, q in subs:
            loop.call_soon_threadsafe(q.put_nowait, ev)
        return ev

    def save_trace(self, episode: int, trace: dict) -> str:
        """Record one decision's full trace (prompt, thinking, tool calls, answer): its `trace` event
        carries it into decisions.trace. Returns its reference, 'decision:<run_id>:<episode>'."""
        ref = f"decision:{self.state.run_id}:{episode}"
        summary = {k: trace.get(k) for k in ("date", "trigger", "decision", "reason", "situation", "outcome",
                                              "current", "seconds", "tokens_in", "tokens_out", "model",
                                              "model_version", "thinking_level", "off_frame", "serves")}
        thinking = sum(1 for st in trace.get("steps", []) if st.get("type") == "thinking")
        tools = sum(1 for st in trace.get("steps", []) if st.get("type") == "tool_call")
        self.emit("trace", _trace=trace, episode=episode, file=ref, thinking=thinking, tools=tools, **summary)
        return ref

    def set_campaign(self, game: str, name: str, title: str = "") -> None:
        """Name the campaign (save/playthrough) this run belongs to; `title` is for people (empire name)."""
        self.campaign_id = f"{game}/{name}"
        self.state.info["campaign"] = self.campaign_id
        self.emit("campaign", game=game, name=name, title=title)

    def subscribe(self, loop: asyncio.AbstractEventLoop) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        with self._lock:
            self._subscribers.append((loop, q))
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self._lock:
            self._subscribers = [(lp, s) for lp, s in self._subscribers if s is not q]

    def close(self) -> None:
        """Nothing to close: the store outlives the run (kept for callers)."""
