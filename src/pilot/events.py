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
    game_date: str = ""                # latest in-game date reported by a decision
    learned: dict[str, int] = field(default_factory=lambda: {"screens": 0, "rules": 0, "controls": 0})
    tokens_in: int = 0
    tokens_out: int = 0
    requests: int = 0
    pending_question: str = ""
    started_at: float = field(default_factory=time.time)
    frame_path: str = ""
    info: dict[str, Any] = field(default_factory=dict)   # game-specific: game, speed, directive…

    def as_dict(self) -> dict[str, Any]:
        d = dict(self.__dict__)
        d["uptime_s"] = round(time.time() - self.started_at)
        return d


class EventLog:
    def __init__(self, runs_dir: Path, run_id: str, model: str, telemetry=None):
        self.dir = runs_dir / run_id
        (self.dir / "frames").mkdir(parents=True, exist_ok=True)
        self.state = RunState(run_id=run_id, model=model)
        self.recent: deque[dict] = deque(maxlen=300)
        self._lock = threading.Lock()
        self._subscribers: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = []
        self._frame_n = 0
        self._file = open(self.dir / "events.jsonl", "a", encoding="utf-8")  # noqa: SIM115 - lives for the run
        self.telemetry = telemetry          # optional Telemetry: every event is also written there
        self.campaign_id: str | None = None

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

    def emit(self, kind: str, _trace: dict | None = None, **data: Any) -> dict:
        ev = {"t": round(time.time(), 3), "kind": kind, **data}
        with self._lock:
            self._file.write(json.dumps(ev, ensure_ascii=False, default=str) + "\n")
            self._file.flush()
            self.recent.append(ev)
            subs = list(self._subscribers)
        if self.telemetry is not None:
            try:
                self.telemetry.record(self.state.run_id, ev, _trace)
            except Exception as e:  # noqa: BLE001 - telemetry must never stop play; JSONL is the record
                print(f"telemetry write failed: {e}", flush=True)
        (self.dir / "status.json").write_text(json.dumps(self.state.as_dict(), default=str))
        for loop, q in subs:
            loop.call_soon_threadsafe(q.put_nowait, ev)
        return ev

    def save_trace(self, episode: int, trace: dict) -> str:
        """Write one decision's full trace (prompt, thinking, tool calls, answer) to traces/NNNN.json."""
        (self.dir / "traces").mkdir(exist_ok=True)
        rel = f"traces/{episode:04d}.json"
        (self.dir / rel).write_text(json.dumps(trace, ensure_ascii=False, default=str, indent=1), encoding="utf-8")
        summary = {k: trace.get(k) for k in ("date", "trigger", "decision", "reason", "situation", "outcome",
                                              "current", "seconds", "tokens_in", "tokens_out", "model",
                                              "model_version", "thinking_level", "off_frame")}
        thinking = sum(1 for st in trace.get("steps", []) if st.get("type") == "thinking")
        tools = sum(1 for st in trace.get("steps", []) if st.get("type") == "tool_call")
        self.emit("trace", _trace=trace, episode=episode, file=rel, thinking=thinking, tools=tools, **summary)
        return rel

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
        self._file.close()
