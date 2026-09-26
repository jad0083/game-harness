"""Run log and live state: every event goes to runs/<id>/events.jsonl and to live subscribers
(the dashboard's server-sent events). Frames are saved as JPEG files next to the log."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class RunState:
    run_id: str
    model: str
    status: str = "starting"           # starting | playing | deciding | paused | stopped | needs_attention
    turns_advanced: int = 0
    episodes: int = 0
    last_stop: str = ""
    last_decision: str = ""
    learned: dict[str, int] = field(default_factory=lambda: {"screens": 0, "rules": 0, "controls": 0})
    tokens_in: int = 0
    tokens_out: int = 0
    requests: int = 0
    pending_question: str = ""
    started_at: float = field(default_factory=time.time)
    frame_path: str = ""

    def as_dict(self) -> dict[str, Any]:
        d = dict(self.__dict__)
        d["uptime_s"] = round(time.time() - self.started_at)
        return d


class EventLog:
    def __init__(self, runs_dir: Path, run_id: str, model: str):
        self.dir = runs_dir / run_id
        (self.dir / "frames").mkdir(parents=True, exist_ok=True)
        self.state = RunState(run_id=run_id, model=model)
        self.recent: deque[dict] = deque(maxlen=300)
        self._lock = threading.Lock()
        self._subscribers: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = []
        self._frame_n = 0
        self._file = open(self.dir / "events.jsonl", "a", encoding="utf-8")  # noqa: SIM115 - lives for the run

    def frame(self, jpeg: bytes | None) -> str:
        """Save a frame; returns its path relative to the run dir ('' if none)."""
        if not jpeg:
            return ""
        with self._lock:
            self._frame_n += 1
            rel = f"frames/{self._frame_n:05d}.jpg"
        (self.dir / rel).write_bytes(jpeg)
        (self.dir / "latest.jpg").write_bytes(jpeg)
        self.state.frame_path = rel
        return rel

    def emit(self, kind: str, **data: Any) -> dict:
        ev = {"t": round(time.time(), 3), "kind": kind, **data}
        with self._lock:
            self._file.write(json.dumps(ev, ensure_ascii=False, default=str) + "\n")
            self._file.flush()
            self.recent.append(ev)
            subs = list(self._subscribers)
        (self.dir / "status.json").write_text(json.dumps(self.state.as_dict(), default=str))
        for loop, q in subs:
            loop.call_soon_threadsafe(q.put_nowait, ev)
        return ev

    def subscribe(self, loop: asyncio.AbstractEventLoop) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        with self._lock:
            self._subscribers.append((loop, q))
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self._lock:
            self._subscribers = [(lp, s) for lp, s in self._subscribers if s is not q]

    def close(self) -> None:
        self._file.close()
