"""The dashboard supervises one pilot run as its child process (appliance image design, ruling 5).
The store row `supervisor` says whether a run was live, so a restarted dashboard can resume it.

The row is {"live": bool, "since": float, "by": str, "last_exit": {"code", "t", "lines"} | null}:
- a start writes live true (who started it, when);
- a stop for a container or service stop (`stop(keep_live=True)`) leaves live true, so the next
  dashboard start resumes the run once, after RESUME_DELAY_S;
- any other exit (a human Stop forwarded to the pilot, the campaign's end, a crash) writes live false,
  so nothing restarts in a loop. Every exit records its code and last lines in `last_exit` (ruling P3:
  a child that dies before its run_start has no run to carry them)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
import time
from collections import deque
from collections.abc import Mapping
from pathlib import Path

from .cli import STOP_GRACE_S

STATE_KEY = "supervisor"
RESUME_DELAY_S = 10.0
TAIL_LINES = 20                 # the child's last lines kept for last_exit
LINE_LIMIT = 1 << 20            # one output line read at most (a longer one is cut into pieces)
EXIT_POLL_S = 0.1               # how often the watcher looks for the child's exit
DRAIN_S = 2.0                   # after the exit, the time its last output gets to arrive
KEYS = {"google": ("GEMINI_API_KEY", "GOOGLE_API_KEY"), "anthropic": ("ANTHROPIC_API_KEY",),
        "openai": ("OPENAI_API_KEY",)}

log_ = logging.getLogger(__name__)


class SupervisorBusy(Exception):
    """A run is already live (this supervisor's child, or one answering on its port elsewhere)."""


class MissingSettings(Exception):
    """Settings a run needs are not set; `names` lists them."""

    def __init__(self, names: list[str]):
        super().__init__("set " + ", ".join(names) + " to start a run")
        self.names = names


def resume_enabled(env: Mapping[str, str]) -> bool:
    """PILOT_RESUME: on by default; 0, false, no or off turns it off."""
    return env.get("PILOT_RESUME", "1").strip().lower() not in ("0", "false", "no", "off")


def run_requirements(env: Mapping[str, str], prefs: dict, token_file: Path | None = None) -> list[str]:
    """Names of the settings a run needs that are missing: GAME_AGENT_URL, GAME_AGENT_TOKEN (unless
    `token_file`, default <repo>/.agent_token, exists), and the model key for the provider of the first
    model in prefs["models"] (else PILOT_MODEL, else Google): google -> GEMINI_API_KEY or GOOGLE_API_KEY,
    anthropic -> ANTHROPIC_API_KEY, openai -> OPENAI_API_KEY, claude-code -> the `claude` CLI."""
    from .config import REPO
    token_file = token_file if token_file is not None else REPO / ".agent_token"
    missing = []
    if not env.get("GAME_AGENT_URL", "").strip():
        missing.append("GAME_AGENT_URL")
    if not env.get("GAME_AGENT_TOKEN", "").strip() and not token_file.exists():
        missing.append("GAME_AGENT_TOKEN")
    models = prefs.get("models") or []
    model = (models[0].get("model") if models else None) or env.get("PILOT_MODEL", "") or "google:"
    provider = model.split(":", 1)[0]
    if provider == "claude-code":
        from .claude_code import find_claude  # where the run looks for it: PATH, then ~/.local/bin
        if not find_claude():
            missing.append("the claude CLI")
    elif provider in KEYS and not any(env.get(k, "").strip() for k in KEYS[provider]):
        missing.append(KEYS[provider][0])
    return missing


class Supervisor:
    """Starts, watches and stops one `pilot run` child; its state lives in the store's settings row."""

    def __init__(self, store, *, argv: list[str] | None = None, env: Mapping[str, str] | None = None,
                 out=None, clock=time.time, stop_wait_s: float = STOP_GRACE_S + 5, emit_exit=None):
        self.store = store
        self.env = env
        hooks = env if env is not None else os.environ
        # test hook: PILOT_SUPERVISOR_ARGV (space-separated) replaces the default child command
        self.argv = list(argv) if argv else (hooks.get("PILOT_SUPERVISOR_ARGV", "").split()
                                             or [sys.executable, "-m", "pilot", "run"])
        self.out = out if out is not None else sys.stdout
        self.clock = clock
        self.stop_wait_s = stop_wait_s
        self.emit_exit = emit_exit
        self._proc: asyncio.subprocess.Process | None = None
        self._watch: asyncio.Task | None = None
        self._tail: deque[str] = deque(maxlen=TAIL_LINES)
        self._stop_requested = False
        self._keep_live = False
        self._resume_tried = False
        self._lock = asyncio.Lock()

    @property
    def running(self) -> bool:
        return self._watch is not None and not self._watch.done()

    # -- the store row ------------------------------------------------------------------------------

    def _read(self) -> dict:
        rows = self.store.query("SELECT value FROM settings WHERE key=?", (STATE_KEY,))
        try:
            row = json.loads(rows[0]["value"]) if rows else {}
        except (TypeError, ValueError):
            return {}
        return row if isinstance(row, dict) else {}

    def state(self) -> dict:
        """The settings row, with defaults for what it lacks (a damaged row reads as no run live)."""
        row = self._read()
        since, last = row.get("since"), row.get("last_exit")
        return {"live": row.get("live") is True, "since": since if isinstance(since, (int, float)) else 0.0,
                "by": str(row.get("by") or ""), "last_exit": last if isinstance(last, dict) else None}

    def _write(self, changed_by: str | None = None, **changes) -> None:
        with self.store.transaction():          # read, change and write as one step
            row = {**self.state(), **changes}
            self.store._exec(
                "INSERT INTO settings(key, value, changed_by, t) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, changed_by=excluded.changed_by, t=excluded.t",
                (STATE_KEY, json.dumps(row), changed_by, self.clock()))

    # -- the child ----------------------------------------------------------------------------------

    async def start(self, by: str, *, live_elsewhere: bool = False) -> None:
        """Spawn the run, pipe its output to `out` as 'pilot: <line>', and write live true. Raises
        SupervisorBusy when a run is live here or `live_elsewhere`."""
        async with self._lock:
            if self.running or live_elsewhere:
                raise SupervisorBusy("a pilot run is already live")
            env = dict(self.env if self.env is not None else os.environ)
            env.setdefault("PYTHONUNBUFFERED", "1")        # its lines arrive as they are printed
            # its own session: a terminal's Ctrl-C reaches the dashboard only, which then stops the run
            # with one SIGTERM (a second signal would make the pilot leave without pausing the game)
            proc = await asyncio.create_subprocess_exec(
                *self.argv, env=env, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT, limit=LINE_LIMIT, start_new_session=True)
            self._proc, self._stop_requested, self._keep_live = proc, False, False
            self._tail.clear()
            self._watch = asyncio.create_task(self._watch_child(proc), name="pilot-run")
            self._write(changed_by=by, live=True, since=self.clock(), by=by)     # last_exit is kept

    async def _read_output(self, stream: asyncio.StreamReader) -> None:
        while True:
            try:
                raw = await stream.readline()
            except ValueError:                      # a line over LINE_LIMIT (dropped): go on in pieces
                raw = await stream.read(LINE_LIMIT)
            if not raw:
                return
            line = raw.decode(errors="replace").rstrip("\r\n")
            self._tail.append(line)
            try:
                self.out.write(f"pilot: {line}\n")
                self.out.flush()
            except (OSError, ValueError):           # the dashboard's own output is gone: keep the tail
                pass

    async def _watch_child(self, proc: asyncio.subprocess.Process) -> None:
        reader = asyncio.create_task(self._read_output(proc.stdout))
        # the exit, not the end of its output: a process it left behind may hold the pipe open
        # (and Process.wait() waits for the pipes too)
        while proc.returncode is None:
            await asyncio.sleep(EXIT_POLL_S)
        try:
            await asyncio.wait_for(reader, DRAIN_S)
        except TimeoutError:
            pass                                    # the last lines that came are kept
        except Exception:
            log_.exception("reading the pilot run's output failed")
        self._exited(proc.returncode)

    def _exited(self, code: int) -> None:
        requested = self._stop_requested
        lines = list(self._tail)
        last = {"code": code, "t": self.clock(), "lines": lines}
        try:
            if requested and self._keep_live:
                self._write(last_exit=last)             # a container stop: the run resumes at the next start
            else:
                self._write(live=False, last_exit=last)
        except Exception:
            log_.exception("recording the pilot run's exit (code %s) failed", code)
        if not requested and self.emit_exit is not None:
            try:
                self.emit_exit(code, lines)
            except Exception:
                log_.exception("recording the pilot run's exit (code %s) on its run failed", code)

    async def stop(self, *, keep_live: bool) -> None:
        """SIGTERM, wait stop_wait_s, then SIGKILL. keep_live=True (a container or service stop) leaves
        live true; False (a human stop) writes live false."""
        async with self._lock:                      # a start in progress spawns first, then is stopped
            proc, watch = self._proc, self._watch
            if proc is None or watch is None or watch.done():
                if not keep_live:
                    self._write(live=False)
                return
            self._stop_requested, self._keep_live = True, keep_live
            try:
                proc.send_signal(signal.SIGTERM)
            except ProcessLookupError:
                pass
        try:
            await asyncio.wait_for(asyncio.shield(watch), self.stop_wait_s)
        except TimeoutError:
            log_.warning("the pilot run did not stop within %.0f s; killing it", self.stop_wait_s)
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            await watch

    async def resume_if_wanted(self, *, enabled: bool, delay_s: float | None = None,
                               live_elsewhere=None) -> bool:
        """Once: if enabled and the row says live, sleep delay_s (None: PILOT_RESUME_DELAY_S if set, else
        RESUME_DELAY_S) and start(by="resume"). Returns True when it started a run. live_elsewhere: an
        async callable that reports a run answering on its port (then nothing starts)."""
        if not enabled or self._resume_tried or not self.state()["live"]:
            return False
        self._resume_tried = True
        if delay_s is None:
            hooks = self.env if self.env is not None else os.environ
            # test hook: PILOT_RESUME_DELAY_S replaces RESUME_DELAY_S
            delay_s = float(hooks.get("PILOT_RESUME_DELAY_S") or RESUME_DELAY_S)
        if delay_s > 0:
            await asyncio.sleep(delay_s)
        if self.running or not self.state()["live"]:     # started or stopped by a human meanwhile
            return False
        if live_elsewhere is not None and await live_elsewhere():
            log_.info("a pilot run already answers on its port: not resuming")
            return False
        try:
            await self.start("resume")
        except SupervisorBusy:
            return False
        except OSError:
            log_.exception("resuming the pilot run failed")
            return False
        return True
