# Appliance Image Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run Game Pilot from one container image whose dashboard supervises the pilot, with a portable
compose for anyone and a pinned Komodo stack on deb-dock1 for the user's estate.

**Architecture:**
- The dashboard (`pilot view`) is the container's main process. A new `Supervisor` starts and stops
  `pilot run` as its child, records in the store whether a run was live, and resumes it after a restart.
- A three-stage Dockerfile builds the Rust controller and the Python app into a slim runtime with `tini` and
  Litestream. An entrypoint checks `/data` and wraps the dashboard in Litestream when a replica is configured.
- GitHub Actions builds, smoke-tests and pushes `ghcr.io/jad0083/game-pilot`. The estate stack pins it by
  digest.

**Tech Stack:** Python 3.13 (aiohttp, asyncio subprocesses), Rust (game-controller), Docker (multi-stage,
buildx), Litestream, GitHub Actions, Docker Compose, Komodo + OpenBao (estate).

**Spec:** docs/design/2026-10-06-appliance-image-design.md (rulings 1-12, Rollout, Errors, Tests).

## Global Constraints

- **Image:** `ghcr.io/jad0083/game-pilot`, amd64 only. It is tagged `:<pyproject version>` (never moved),
  `:sha-<short>` and `:latest`.
- **Base and runtime user:** base images `rust:1-slim-bookworm` and `python:3.13-slim-bookworm`; the runtime
  user is uid and gid `10010`.
- **Paths in the image:**
  - `PILOT_DATA_DIR=/data`, `PILOT_CORPORA_DIR=/app/corpora`, `PILOT_CONTROLLER_BIN=/app/bin/game-controller`;
  - the code at `/app/src` on `PYTHONPATH`, so `config.REPO` is `/app`.
- **Ports:** dashboard `8780` (published); live pilot `8790` (container loopback only).
- **Timings:**
  - compose `stop_grace_period: 40s`;
  - the supervisor's stop wait is `STOP_GRACE_S + 5` (25 s), then SIGKILL;
  - resume runs 10 s after the dashboard starts.
- **Settings:**
  - `PILOT_RESUME` (default on; `0`, `false`, `no` or `off` turns it off);
  - `LITESTREAM_REPLICA_URL` (unset means no Litestream);
  - `LITESTREAM_ACCESS_KEY_ID`, `LITESTREAM_SECRET_ACCESS_KEY`.
- **The supervisor's store row:** `settings` key `supervisor`, a JSON object:
  `{"live": bool, "since": float, "by": str, "last_exit": {"code": int, "t": float, "lines": [str]} | null}`.
- **No `claude` CLI in the image.** No git, Rust toolchain or systemd at run time in the image.
- **Commits** go only through `scripts/ci-commit.sh` (conventional messages). No AI or assistant attribution
  anywhere.
- **Never stage or bake in** `runs/`, `.env`, `.agent_token*` or `play/`: not in a commit, and not in the
  image.
- **Never run `.venv/bin/python -m pilot ...` against the live data** in `runs/`. Use pytest, or
  `PYTHONPATH=src PILOT_DATA_DIR=<temp dir>`.
- **UI-gated files:** a commit that stages `src/pilot/static/*.html` or `src/pilot/auth.py` needs the UI tests
  to have run (`.venv/bin/pytest -m ui tests/ui`).

## Review Focus

1. **A container stop during a run, then a start.** The run resumes by itself in the same campaign. A run the
   human stopped, or one that ended, does not resume. Test: Task 2, `test_container_stop_then_start_resumes`
   and `test_human_stop_does_not_resume`.
2. **A data folder owned by another uid** (a root-created `/mnt/dockervol/...`). The container prints one line
   naming `/data`, uid 10010 and the `chown`, not a traceback loop. Test: Task 3,
   `test_unwritable_data_dir_names_the_fix`.
3. **A fresh install with only a model key.** The dashboard serves sign-in and history. Start refuses and names
   `GAME_AGENT_URL` and `GAME_AGENT_TOKEN`. The PC line says the agent is not configured. Test: Task 1,
   `test_pc_status_not_configured`; Task 2, `test_start_refused_names_missing_settings`.
4. **A run that crashes at start** (a bad key). Its exit code and last lines are recorded and shown, and there
   is no restart loop: resume is tried once per dashboard start. Test: Task 2,
   `test_crash_is_recorded_and_not_restarted`.
5. **Secrets or live data leaking into the image** (`.env`, `.agent_token*`, `runs/`, `play/`, `.git`). The
   build context excludes them, and the image holds none of them. Test: Task 3,
   `test_dockerignore_excludes_secrets_and_data`, plus the smoke script's `ls` check.

## Planning rulings

- **P1 (spec ruling 9).** `auth.allowed_host` already accepts IP literals, loopback, the machine's own names
  and the hosts from `PILOT_PUBLIC_URL`/`PILOT_DASHBOARD_HOSTS`. A container's own hostname (a random id no
  DNS name resolves to) being accepted is harmless, so there is no code change; Task 1 adds a test for the
  NPM case.
  *If wrong:* one function later.
- **P2 (spec ruling 3).** `config.REPO` stays `Path(__file__).parents[2]`. In the image that is `/app`, where
  `corpora/` exists, so `game.py:390` and `notify.py:63` (`REPO / "corpora"`) keep working unchanged.
  *If wrong:* those two read `/app/corpora` while `PILOT_CORPORA_DIR` points elsewhere, which only a
  non-image layout can cause.
- **P3 (spec ruling 5, the exit record).** A child that exits before it wrote its `run_start` has no run to
  attach a `run_exit` event to. The supervisor therefore always records `last_exit` in its settings row. It
  also writes a `run_exit` event to the newest run that started after `since`, when there is one. The
  viewer's `/status` returns `last_exit`, and the page shows it when no run is live.
- **P4 (spec ruling 10, CI preflight).** `scripts/ci.sh` also cross-checks the Windows agent (mingw) and runs
  a LuaJIT check from a local cache; neither belongs in the image's CI. The workflow's preflight runs:
  - the controller's `cargo test -p game-controller`;
  - `ruff`;
  - `pytest -m "not ui"`.

  The local CI gate stays the full `scripts/ci.sh`.
  *If wrong:* the image workflow is a little less strict than the local gate, which still runs before every
  commit.
- **P5 (deploy scripts).** `scripts/deploy-pilot.sh`, `scripts/pilot-affected.py`, `tests/test_deploy_pilot.py`
  and `deploy/game-pilot.service` are deleted. `scripts/install-services.sh` installs the one remaining unit.
  The viewer unit gets `KillMode=mixed` and `TimeoutStopSec=60`, so the supervisor stops the child itself.

---

## File map

| File | Task | Responsibility |
|---|---|---|
| `src/pilot/dashboard.py` | 1, 2 | `/healthz`; `pc_status` not-configured; `api_run` through the supervisor; `last_exit` in viewer `/status`; startup/shutdown hooks |
| `src/pilot/auth.py` | 1 | `/healthz` in `PUBLIC_PATHS` |
| `src/pilot/supervisor.py` (new) | 2 | `Supervisor`, `run_requirements`, `resume_enabled` |
| `src/pilot/static/dashboard.html` | 1, 2 | the not-configured PC label; the last-exit line |
| `deploy/game-pilot-view.service`, `scripts/install-services.sh` | 2 | one unit; KillMode=mixed |
| `deploy/game-pilot.service`, `scripts/deploy-pilot.sh`, `scripts/pilot-affected.py`, `tests/test_deploy_pilot.py` | 2 | deleted |
| `Dockerfile`, `.dockerignore`, `docker/entrypoint.sh`, `docker/litestream.yml`, `scripts/image-smoke.sh` (new) | 3 | the image and its local smoke test |
| `compose.yaml`, `.env.example` (new) | 4 | the portable install |
| `.github/workflows/image.yml` (new) | 5 | build, smoke, push |
| README, docs/pilot.md, ARCHITECTURE.md, AGENTS.md | 2, 4, 5 | docs |

---

### Task 1: Container readiness in the dashboard

**Files:**
- Modify: `src/pilot/dashboard.py`:
  - `pc_status` (around 213-240): not configured when `GAME_AGENT_URL` is unset;
  - routes (around 798-849): `GET /healthz`.
- Modify: `src/pilot/auth.py:80`: `("GET", "/healthz")` in `PUBLIC_PATHS`.
- Modify: `src/pilot/static/dashboard.html`: the PC status label for `state == "not_configured"`.
- Test: `tests/test_container_ready.py` (new); a UI assertion in the existing PC-status UI test, if there is
  one (grep `tests/ui` for `api/pc`).

**Interfaces:**
- Produces:
  - `GET /healthz` returns 200 with `ok` and no other content. It is public and needs no sign-in.
  - `pc_status()` returns `{"online": False, "state": "not_configured", "host": "", "error": "set GAME_AGENT_URL"}`
    when `os.environ.get("GAME_AGENT_URL")` is empty.

- [ ] **Step 1: Write the failing tests** (`tests/test_container_ready.py`)

```python
"""What a container needs from the dashboard (appliance image design, rulings 3, 7 and 9)."""

from __future__ import annotations

from aiohttp.test_utils import TestClient, TestServer

from pilot.auth import Auth, allowed_host
from pilot.dashboard import make_app, pc_status
from pilot.store import open_store

KEY = "k" * 48


async def test_healthz_is_public_and_says_nothing(tmp_path):
    auth = Auth.from_env(tmp_path, key=KEY)
    app = make_app(None, tmp_path, open_store(tmp_path), key=KEY, auth=auth)
    async with TestClient(TestServer(app)) as c:
        r = await c.get("/healthz")
        assert r.status == 200 and (await r.text()) == "ok"
        r = await c.get("/runs", allow_redirects=False)
        assert r.status in (302, 303, 401)              # everything else still needs a sign-in


def test_pc_status_not_configured(monkeypatch):
    monkeypatch.delenv("GAME_AGENT_URL", raising=False)
    assert pc_status() == {"online": False, "state": "not_configured", "host": "", "error": "set GAME_AGENT_URL"}


def test_the_public_hostname_and_loopback_are_allowed(monkeypatch):
    # NPM forwards Host: gamepilot.saczone.com; the healthcheck calls 127.0.0.1:8780 (planning ruling P1)
    assert allowed_host("gamepilot.saczone.com", frozenset({"gamepilot.saczone.com"}))
    assert allowed_host("127.0.0.1:8780")
    assert not allowed_host("evil.example")
```

  The repo's pytest config must run async tests. Check how the existing aiohttp tests do it (grep
  `TestClient` in tests/) and copy their marker or fixture style exactly.

- [ ] **Step 2: Run them to see them fail.** Run `.venv/bin/pytest tests/test_container_ready.py -q`. Expected:
  `/healthz` gives 404 or a redirect, and `pc_status` has no `not_configured`.

- [ ] **Step 3: Implement**
  - `auth.py`: add `("GET", "/healthz")` to `PUBLIC_PATHS`.
  - `dashboard.py`:
    - add `async def healthz(_): return web.Response(text="ok")` to the routes that both the viewer and the
      live app serve;
    - at the top of `pc_status`, add:

      ```python
      if not os.environ.get("GAME_AGENT_URL", "").strip():
          return {"online": False, "state": "not_configured", "host": "", "error": "set GAME_AGENT_URL"}
      ```

  - `dashboard.html`: wherever the PC state is turned into words, `not_configured` reads
    "Agent not configured (set GAME_AGENT_URL)".

- [ ] **Step 4: Run the tests.** Run `.venv/bin/pytest tests/test_container_ready.py -q`, then the full
  non-UI suite. Run `.venv/bin/pytest -q -m ui tests/ui`, because `auth.py` and `dashboard.html` are staged.

- [ ] **Step 5: Commit.**
  `git add src/pilot/auth.py src/pilot/dashboard.py src/pilot/static/dashboard.html tests/test_container_ready.py`
  then `scripts/ci-commit.sh "feat(dashboard): /healthz and an agent that is not configured" "<body>"`.

---

### Task 2: The supervisor, resume, and one service

**Files:**
- Create: `src/pilot/supervisor.py`.
- Modify: `src/pilot/dashboard.py`:
  - `api_run` (around 764-785): through the supervisor;
  - `SERVICE` (127): removed;
  - viewer `/status` (`status`, around 856): `last_exit` and `supervisor`;
  - `make_app` viewer branch: startup and shutdown hooks.
- Modify: `src/pilot/static/dashboard.html`: when no run is live and `last_exit.code != 0`, one line "The last
  run stopped with exit code N" and the last 3 lines in a details element.
- Modify: `deploy/game-pilot-view.service` (`KillMode=mixed`, `TimeoutStopSec=60`) and
  `scripts/install-services.sh` (its last hint names `game-pilot-view.service`).
- Delete: `deploy/game-pilot.service`, `scripts/deploy-pilot.sh`, `scripts/pilot-affected.py`,
  `tests/test_deploy_pilot.py`.
- Modify docs, replacing deploy-pilot text with: merge the image pin or restart the viewer; the run resumes.
  - `AGENTS.md` §8 "Deploying to the running services";
  - `docs/pilot.md`: every `deploy-pilot.sh`/`pilot-affected.py` mention, plus a "Supervisor and resume"
    paragraph;
  - `CLAUDE.md`, if it names them.
- Test: `tests/test_supervisor.py` (new). Update any test that asserted `systemctl` in `api_run` (grep
  `systemctl` in tests/).

**Interfaces:**
- Consumes (Task 1): nothing beyond `make_app`.
- Produces (`src/pilot/supervisor.py`):

```python
STATE_KEY = "supervisor"
RESUME_DELAY_S = 10.0

class SupervisorBusy(Exception): ...           # a run is already live
class MissingSettings(Exception):              # .names: list[str]
    def __init__(self, names: list[str]): ...

def run_requirements(env: Mapping[str, str], prefs: dict) -> list[str]:
    """Names of the settings a run needs that are missing: GAME_AGENT_URL, GAME_AGENT_TOKEN
    (unless <repo>/.agent_token exists), and the model key for the provider of the first model in
    prefs["models"] (else PILOT_MODEL): google -> GEMINI_API_KEY or GOOGLE_API_KEY, anthropic ->
    ANTHROPIC_API_KEY, openai -> OPENAI_API_KEY, claude-code -> the `claude` CLI on PATH."""

def resume_enabled(env: Mapping[str, str]) -> bool:      # PILOT_RESUME, default on

class Supervisor:
    def __init__(self, store, *, argv: list[str] | None = None, env: Mapping[str, str] | None = None,
                 out=None, clock=time.time, stop_wait_s: float = STOP_GRACE_S + 5, emit_exit=None): ...
    # argv default: [sys.executable, "-m", "pilot", "run"]; out default: sys.stdout
    # emit_exit(code, lines): called after an unrequested exit (the dashboard writes run_exit, P3)
    @property
    def running(self) -> bool: ...
    def state(self) -> dict: ...                 # the settings row (Global Constraints), {} defaults filled
    async def start(self, by: str, *, live_elsewhere: bool = False) -> None:
        """Raises SupervisorBusy if running or live_elsewhere; else spawns, pipes output with a
        'pilot: ' prefix to `out`, writes {"live": True, "since": now, "by": by, "last_exit": <kept>}."""
    async def stop(self, *, keep_live: bool) -> None:
        """SIGTERM, wait stop_wait_s, then SIGKILL. keep_live=True (container stop) leaves live true;
        False (human stop) writes live false."""
    async def resume_if_wanted(self, *, enabled: bool, delay_s: float = RESUME_DELAY_S,
                               live_elsewhere=None) -> bool:
        """Once: if enabled and the row says live, sleep delay_s and start(by="resume"). Returns True
        when it started a run. live_elsewhere: an async callable that reports a run answering on its port."""
```

  The child's own exit, without `stop()`, writes `live: false` and
  `last_exit={"code", "t", "lines": last 20 lines}`, then calls `emit_exit`. An exit during
  `stop(keep_live=True)` records `last_exit` but leaves `live: true`.

- [ ] **Step 1: Write the failing tests** (`tests/test_supervisor.py`). The fake child is a small Python script
  whose behaviour the test sets through an environment variable.

```python
"""The dashboard supervises one pilot run (appliance image design, ruling 5)."""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
import textwrap
import time

import pytest

from pilot.store import open_store
from pilot.supervisor import (MissingSettings, Supervisor, SupervisorBusy, resume_enabled, run_requirements)

CHILD = textwrap.dedent("""
    import os, signal, sys, time
    mode = os.environ.get("FAKE_MODE", "run")
    print("started", flush=True)
    if mode == "crash":
        print("bad key", flush=True); sys.exit(3)
    if mode == "end":
        print("campaign over", flush=True); sys.exit(0)
    def bye(*_):
        print("stopping", flush=True); sys.exit(0)
    signal.signal(signal.SIGTERM, bye)
    while True:
        time.sleep(0.05)
""")


@pytest.fixture
def child(tmp_path):
    p = tmp_path / "child.py"
    p.write_text(CHILD)
    return [sys.executable, str(p)]


def sup(tmp_path, child, mode="run", **kw):
    out = []
    s = Supervisor(open_store(tmp_path / "data"), argv=child, env={**os.environ, "FAKE_MODE": mode},
                   out=type("W", (), {"write": lambda self, t: out.append(t), "flush": lambda self: None})(),
                   stop_wait_s=2, **kw)
    return s, out


async def wait_for(cond, timeout=5.0):
    end = time.monotonic() + timeout
    while not cond():
        assert time.monotonic() < end, "timed out"
        await asyncio.sleep(0.02)


async def test_start_records_live_and_refuses_a_second(tmp_path, child):
    s, out = sup(tmp_path, child)
    await s.start("Pixel phone")
    assert s.running and s.state()["live"] is True and s.state()["by"] == "Pixel phone"
    with pytest.raises(SupervisorBusy):
        await s.start("again")
    await wait_for(lambda: any("pilot: started" in t for t in out))
    await s.stop(keep_live=False)


async def test_human_stop_does_not_resume(tmp_path, child):
    s, _ = sup(tmp_path, child)
    await s.start("me")
    await s.stop(keep_live=False)
    assert not s.running and s.state()["live"] is False
    again, _ = sup(tmp_path, child)
    assert await again.resume_if_wanted(enabled=True, delay_s=0) is False


async def test_container_stop_then_start_resumes(tmp_path, child):
    s, _ = sup(tmp_path, child)
    await s.start("me")
    await s.stop(keep_live=True)                       # SIGTERM to the dashboard: the run was live
    assert s.state()["live"] is True
    again, _ = sup(tmp_path, child)
    assert await again.resume_if_wanted(enabled=True, delay_s=0) is True
    assert again.running and again.state()["by"] == "resume"
    await again.stop(keep_live=False)


async def test_resume_off_and_a_run_live_elsewhere(tmp_path, child):
    s, _ = sup(tmp_path, child)
    await s.start("me")
    await s.stop(keep_live=True)
    again, _ = sup(tmp_path, child)
    assert await again.resume_if_wanted(enabled=False, delay_s=0) is False

    async def elsewhere():
        return True
    assert await again.resume_if_wanted(enabled=True, delay_s=0, live_elsewhere=elsewhere) is False
    assert resume_enabled({}) and not resume_enabled({"PILOT_RESUME": "0"})
    assert not resume_enabled({"PILOT_RESUME": "off"}) and resume_enabled({"PILOT_RESUME": "1"})


async def test_crash_is_recorded_and_not_restarted(tmp_path, child):
    exits = []
    s, _ = sup(tmp_path, child, mode="crash", emit_exit=lambda code, lines: exits.append((code, lines)))
    await s.start("me")
    await wait_for(lambda: not s.running)
    st = s.state()
    assert st["live"] is False and st["last_exit"]["code"] == 3 and "bad key" in st["last_exit"]["lines"]
    assert exits and exits[0][0] == 3
    again, _ = sup(tmp_path, child, mode="crash")
    assert await again.resume_if_wanted(enabled=True, delay_s=0) is False      # not a loop


async def test_a_run_that_ends_by_itself_does_not_resume(tmp_path, child):
    s, _ = sup(tmp_path, child, mode="end")
    await s.start("me")
    await wait_for(lambda: not s.running)
    assert s.state()["live"] is False and s.state()["last_exit"]["code"] == 0


def test_start_refused_names_missing_settings(tmp_path):
    prefs = {"models": [{"model": "google:gemini-pro-latest", "thinking": "high"}]}
    assert run_requirements({}, prefs) == ["GAME_AGENT_URL", "GAME_AGENT_TOKEN", "GEMINI_API_KEY"]
    env = {"GAME_AGENT_URL": "http://pc:8765", "GAME_AGENT_TOKEN": "t" * 40, "GOOGLE_API_KEY": "x"}
    assert run_requirements(env, prefs) == []
    assert run_requirements({**env, "GOOGLE_API_KEY": ""}, {"models": [{"model": "anthropic:claude-x"}]}) \
        == ["ANTHROPIC_API_KEY"]


def test_sigterm_to_the_viewer_stops_the_child_and_keeps_live(tmp_path, child):
    """A real dashboard process resumes a live run, and SIGTERM stops the child but keeps the row live."""
    import json
    import socket
    import threading
    data = tmp_path / "data"
    open_store(data)._exec("INSERT INTO settings(key, value, changed_by, t) VALUES ('supervisor', ?, NULL, 0)",
                           (json.dumps({"live": True, "since": 0, "by": "test", "last_exit": None}),))
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {**os.environ, "PILOT_DATA_DIR": str(data), "PYTHONPATH": "src", "FAKE_MODE": "run",
           "PILOT_SUPERVISOR_ARGV": " ".join(child), "PILOT_DASHBOARD_KEY": "k" * 48,
           "PILOT_RESUME": "1", "PILOT_RESUME_DELAY_S": "0", "GAME_AGENT_URL": "http://127.0.0.1:9",
           "GAME_AGENT_TOKEN": "t" * 40, "GEMINI_API_KEY": "x"}
    p = subprocess.Popen([sys.executable, "-m", "pilot", "view", "--port", str(port), "--host", "127.0.0.1"],
                         env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    lines: list[str] = []
    reader = threading.Thread(target=lambda: lines.extend(iter(p.stdout.readline, "")), daemon=True)
    reader.start()
    try:
        end = time.monotonic() + 20
        while not any("pilot: started" in ln for ln in lines):
            assert p.poll() is None and time.monotonic() < end, "".join(lines)
            time.sleep(0.05)
        p.send_signal(signal.SIGTERM)
        assert p.wait(timeout=10) is not None
        reader.join(timeout=5)
        assert any("pilot: stopping" in ln for ln in lines), "".join(lines)
        row = open_store(data).query("SELECT value FROM settings WHERE key='supervisor'")
        assert json.loads(row[0]["value"])["live"] is True
    finally:
        if p.poll() is None:
            p.kill()
```

  **Note on the last test.** It needs two environment hooks, both internal and used only by tests:
  - `PILOT_SUPERVISOR_ARGV`: a space-separated argv overriding the child command;
  - `PILOT_RESUME_DELAY_S`: overriding `RESUME_DELAY_S`.

  If `view` has no `--host` option, drop it; the viewer's bind default is fine for loopback.

- [ ] **Step 2: Run them to see them fail.** Run `.venv/bin/pytest tests/test_supervisor.py -q`. Expected:
  `ModuleNotFoundError: pilot.supervisor`.

- [ ] **Step 3: Implement `src/pilot/supervisor.py`.** Core shape:

```python
"""The dashboard supervises one pilot run as its child process (appliance image design, ruling 5).
The store row `supervisor` says whether a run was live, so a restarted dashboard can resume it."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import signal
import sys
import time
from collections import deque
from pathlib import Path
from typing import Mapping

from .cli import STOP_GRACE_S          # if this import is circular, move STOP_GRACE_S to config.py and import it in both

STATE_KEY = "supervisor"
RESUME_DELAY_S = 10.0
KEYS = {"google": ("GEMINI_API_KEY", "GOOGLE_API_KEY"), "anthropic": ("ANTHROPIC_API_KEY",),
        "openai": ("OPENAI_API_KEY",)}


class SupervisorBusy(Exception):
    pass


class MissingSettings(Exception):
    def __init__(self, names: list[str]):
        super().__init__("set " + ", ".join(names) + " to start a run")
        self.names = names


def resume_enabled(env: Mapping[str, str]) -> bool:
    return env.get("PILOT_RESUME", "1").strip().lower() not in ("0", "false", "no", "off")


def run_requirements(env: Mapping[str, str], prefs: dict) -> list[str]:
    from .config import REPO
    missing = []
    if not env.get("GAME_AGENT_URL", "").strip():
        missing.append("GAME_AGENT_URL")
    if not env.get("GAME_AGENT_TOKEN", "").strip() and not (REPO / ".agent_token").exists():
        missing.append("GAME_AGENT_TOKEN")
    models = prefs.get("models") or []
    model = (models[0].get("model") if models else None) or env.get("PILOT_MODEL", "") or "google:"
    provider = model.split(":", 1)[0]
    if provider == "claude-code":
        if not shutil.which("claude"):
            missing.append("the claude CLI")
    elif provider in KEYS and not any(env.get(k, "").strip() for k in KEYS[provider]):
        missing.append(KEYS[provider][0])
    return missing
```

  **The `Supervisor` class:**
  - It holds `self._proc: asyncio.subprocess.Process | None`, a reader task and `self._tail = deque(maxlen=20)`.
  - **`start`** runs `asyncio.create_subprocess_exec(*argv, env=env, stdout=PIPE, stderr=STDOUT)` and
    writes the row. A reader task reads lines, writes `f"pilot: {line}"` to `out`, appends to `_tail`, and
    on EOF awaits `proc.wait()`, then calls `_exited(code)`.
  - **`_exited`** writes `live: False` unless `self._stopping_keep_live`, and always writes `last_exit`. It
    calls `emit_exit(code, list(tail))` only when the exit was not requested by `stop()`.
  - **`stop`** sets the flag and calls `proc.send_signal(SIGTERM)`. It runs `asyncio.wait_for(proc.wait(),
    stop_wait_s)`; on a timeout it calls `proc.kill()` and awaits `proc.wait()`. It then awaits the reader
    task.
  - **The row:** read and write it through `store.query("SELECT value FROM settings WHERE key=?")` and an
    upsert like `models.save_prefs`'s, inside `store.transaction()`.
  - **The test hooks:** `PILOT_SUPERVISOR_ARGV`, used if set, splits on whitespace and overrides the default
    argv; `PILOT_RESUME_DELAY_S` overrides the delay in `resume_if_wanted` when the caller passes none.
    Comment both as test hooks.

  **`dashboard.py`, the viewer branch of `make_app`:**
  - `sup = Supervisor(tel, emit_exit=...)`. `emit_exit` writes `run_exit` with `{"code", "lines"}` to the
    newest run whose `started` is at or after `sup.state()["since"]`. It uses `tel.record(run_id, {"t":
    time.time(), "kind": "run_exit", ...})`; check the `runs` columns for the start time.
  - `api_run`:
    - It keeps its prefs save.
    - It then checks `run_requirements(os.environ, load_prefs(runs_dir))`. On any missing name it raises
      `web.HTTPBadRequest(text=str(MissingSettings(names)))`.
    - It replaces the `systemctl` call with `await sup.start(actor_name(request), live_elsewhere=bool(await
      live_url()))`, mapping `SupervisorBusy` to `HTTPConflict("a pilot run is already live")`.
    - It answers `{"ok": True, "started": "pilot run", **prefs}`.
  - `app.on_startup`: `asyncio.create_task(sup.resume_if_wanted(enabled=resume_enabled(os.environ),
    live_elsewhere=<async lambda returning bool(await live_url())>))`.
  - `app.on_shutdown`: `await sup.stop(keep_live=True)` when `sup.running`.
  - The viewer `status()` adds `"supervisor": sup.state()`. Its `last_exit` is used by the page.
  - Remove `SERVICE`, and any text naming `game-pilot.service` in error strings (for example `refused_key`'s
    fix: "Restart the dashboard after a key rotation.").

  **`dashboard.html`:** when `/status` says `live: false` and `supervisor.last_exit.code` is non-zero, show
  "The last run stopped with exit code N" with the last 3 lines in a `<details>`. Use the page's existing
  status-line styles.

- [ ] **Step 4: Retire the systemd pilot unit and the deploy scripts.**
  - Run `git rm deploy/game-pilot.service scripts/deploy-pilot.sh scripts/pilot-affected.py tests/test_deploy_pilot.py`.
  - Edit `deploy/game-pilot-view.service`: add `KillMode=mixed` and `TimeoutStopSec=60` under `[Service]`.
  - Edit `scripts/install-services.sh`: its final hint says
    `systemctl --user edit game-pilot-view.service`.
  - Grep for the scripts' names across `*.md`, `scripts/` and `src/`, and update every live doc. Leave
    `docs/design/` and `docs/plans/` history alone. `tests/test_docs_paths.py` may need the names added to its
    banned list; add them.

- [ ] **Step 5: Run the tests.**
  - `.venv/bin/pytest tests/test_supervisor.py -q`;
  - the full non-UI suite;
  - `.venv/bin/pytest -q -m ui tests/ui`, because `dashboard.html` is staged.

- [ ] **Step 6: Commit** through `scripts/ci-commit.sh`:
  `feat(dashboard): the dashboard supervises the pilot run and resumes it after a restart`. A second commit
  for the deletions and docs is fine: `refactor: one service; deploy-pilot and pilot-affected retired`.

---

### Task 3: The image

**Files:**
- Create: `Dockerfile`, `.dockerignore`, `docker/entrypoint.sh`, `docker/litestream.yml`,
  `scripts/image-smoke.sh`.
- Test: `tests/test_image_files.py` (new), covering the entrypoint with stubs and `.dockerignore`.

**Interfaces:**
- Consumes (Task 1): `GET /healthz`.
- Produces: `docker build -t game-pilot:dev .` builds the image. `scripts/image-smoke.sh <image>` exits 0 when
  the image passes the smoke checks. Task 5's workflow calls it.

- [ ] **Step 1: Write the failing tests** (`tests/test_image_files.py`)

```python
"""The image's entrypoint and build context (appliance image design, rulings 3, 4 and 12)."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "docker" / "entrypoint.sh"


def stub(dir: Path, name: str, body: str) -> None:
    p = dir / name
    p.write_text("#!/bin/sh\n" + body)
    p.chmod(p.stat().st_mode | stat.S_IEXEC)


def run(tmp_path, env_extra=None, data=None):
    bin_ = tmp_path / "bin"
    bin_.mkdir(exist_ok=True)
    log = tmp_path / "calls"
    stub(bin_, "litestream", f'echo "litestream $*" >> {log}\n')
    stub(bin_, "pilot", f'echo "pilot $*" >> {log}\n')
    data = data or (tmp_path / "data")
    env = {"PATH": f"{bin_}:/usr/bin:/bin", "PILOT_DATA_DIR": str(data), "LITESTREAM_CONFIG": str(ROOT / "docker/litestream.yml"),
           **(env_extra or {})}
    r = subprocess.run(["sh", str(ENTRY)], env=env, capture_output=True, text=True, timeout=30)
    return r, (log.read_text().splitlines() if log.exists() else [])


def test_no_replica_runs_the_dashboard(tmp_path):
    (tmp_path / "data").mkdir()
    r, calls = run(tmp_path)
    assert r.returncode == 0, r.stderr
    assert calls == ["pilot view --port 8780"]


def test_a_replica_restores_into_an_empty_dir_then_replicates(tmp_path):
    (tmp_path / "data").mkdir()
    r, calls = run(tmp_path, {"LITESTREAM_REPLICA_URL": "s3://bucket/pilot"})
    assert r.returncode == 0, r.stderr
    assert calls[0].startswith("litestream restore") and "-if-replica-exists" in calls[0]
    assert calls[1].startswith("litestream replicate") and '-exec' in calls[1] and "pilot view --port 8780" in calls[1]


def test_a_replica_never_restores_over_existing_data(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "pilot.db").write_bytes(b"x")
    r, calls = run(tmp_path, {"LITESTREAM_REPLICA_URL": "s3://bucket/pilot"})
    assert r.returncode == 0 and not any(c.startswith("litestream restore") for c in calls)


def test_unwritable_data_dir_names_the_fix(tmp_path):
    if os.geteuid() == 0:
        return                                   # root writes whatever the mode
    d = tmp_path / "data"
    d.mkdir()
    d.chmod(0o500)
    try:
        r, calls = run(tmp_path, data=d)
    finally:
        d.chmod(0o700)
    assert r.returncode == 1 and calls == []
    msg = r.stdout + r.stderr
    assert str(d) in msg and "chown" in msg and msg.count("\n") <= 2


def test_dockerignore_excludes_secrets_and_data():
    lines = {line.strip() for line in (ROOT / ".dockerignore").read_text().splitlines() if line.strip()}
    for must in (".env", ".agent_token*", "runs/", "play/", ".git", ".venv", "target/", "incoming/", ".claude/"):
        assert must in lines, must
```

- [ ] **Step 2: Run them to see them fail.** Run `.venv/bin/pytest tests/test_image_files.py -q`. Expected:
  the files are missing.

- [ ] **Step 3: Write `docker/entrypoint.sh`** (POSIX sh, `set -eu`)

```sh
#!/bin/sh
# Container entrypoint (appliance image design, ruling 4): check the data directory, then run the
# dashboard, under Litestream when a replica is configured.
set -eu
DATA="${PILOT_DATA_DIR:-/data}"
CONFIG="${LITESTREAM_CONFIG:-/app/docker/litestream.yml}"
if [ ! -d "$DATA" ] || ! ( : > "$DATA/.write-test" ) 2>/dev/null; then
  echo "game-pilot: cannot write the data directory $DATA as uid $(id -u); fix: chown $(id -u):$(id -g) the host folder mounted there" >&2
  exit 1
fi
rm -f "$DATA/.write-test"
if [ -n "${LITESTREAM_REPLICA_URL:-}" ]; then
  if [ ! -e "$DATA/pilot.db" ]; then
    litestream restore -config "$CONFIG" -if-replica-exists "$DATA/pilot.db"
  fi
  exec litestream replicate -config "$CONFIG" -exec "pilot view --port 8780"
fi
exec pilot view --port 8780
```

  Litestream 0.5 may name the restore and replicate flags differently from 0.3. Check `litestream restore -h`
  and `litestream replicate -h` in the built image, and adapt both the entrypoint and its stub assertions
  to the real flags. Never restore over an existing database.

  `pilot` must be on the image's PATH: a two-line wrapper `/usr/local/bin/pilot` running
  `exec /opt/venv/bin/python -m pilot "$@"`.

- [ ] **Step 4: Write `docker/litestream.yml`.** Litestream expands `$VAR` in its config:

```yaml
dbs:
  - path: ${PILOT_DATA_DIR}/pilot.db
    replicas:
      - url: ${LITESTREAM_REPLICA_URL}
```

  The S3 credentials come from Litestream's own environment variables (`LITESTREAM_ACCESS_KEY_ID`,
  `LITESTREAM_SECRET_ACCESS_KEY`), so the file names none.

- [ ] **Step 5: Write `.dockerignore`.** List each excluded path on its own line, exactly as the test lists
  them:
  - `.env`, `.env.*`, `.agent_token*`;
  - `runs/`, `play/`, `incoming/`;
  - `.git`, `.venv`, `target/`, `.claude/`;
  - `**/__pycache__`, `tests/`, `docs/`, `games/`, `windows_agent/`, `src/harness/`.

- [ ] **Step 6: Write the `Dockerfile`**

```dockerfile
# syntax=docker/dockerfile:1
# Game Pilot appliance (appliance image design, ruling 3): the dashboard supervises the pilot.
FROM rust:1-slim-bookworm AS rust
WORKDIR /src
COPY Cargo.toml Cargo.lock ./
COPY crates ./crates
RUN cargo build --release -p game-controller && strip target/release/game-controller

FROM python:3.13-slim-bookworm AS py
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
COPY pyproject.toml /tmp/pyproject.toml
# runtime dependencies only, from pyproject (the package itself runs from /app/src)
RUN /opt/venv/bin/python - <<'EOF'
import subprocess, tomllib
deps = tomllib.load(open("/tmp/pyproject.toml", "rb"))["project"]["dependencies"]
subprocess.check_call(["/opt/venv/bin/pip", "install", *deps])
EOF

FROM python:3.13-slim-bookworm AS runtime
ARG LITESTREAM_VERSION=0.5.17
ARG LITESTREAM_SHA256=cfb371176d164437ae869f8351cfde49bd1804ae71c61923f75c9cba9c9c006d
RUN apt-get update && apt-get install -y --no-install-recommends tini ca-certificates curl \
 && curl -fsSL -o /tmp/ls.tar.gz "https://github.com/benbjohnson/litestream/releases/download/v${LITESTREAM_VERSION}/litestream-${LITESTREAM_VERSION}-linux-x86_64.tar.gz" \
 && echo "${LITESTREAM_SHA256}  /tmp/ls.tar.gz" | sha256sum -c - \
 && tar -xzf /tmp/ls.tar.gz -C /usr/local/bin litestream && rm /tmp/ls.tar.gz \
 && apt-get purge -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/* \
 && groupadd -g 10010 pilot && useradd -u 10010 -g 10010 -M -d /data -s /usr/sbin/nologin pilot
COPY --from=py /opt/venv /opt/venv
COPY --from=rust /src/target/release/game-controller /app/bin/game-controller
COPY corpora /app/corpora
COPY src /app/src
COPY docker /app/docker
RUN printf '#!/bin/sh\nexec /opt/venv/bin/python -m pilot "$@"\n' > /usr/local/bin/pilot \
 && chmod 0755 /usr/local/bin/pilot /app/docker/entrypoint.sh \
 && install -d -o 10010 -g 10010 -m 0700 /data
ENV PYTHONPATH=/app/src PYTHONUNBUFFERED=1 PYDANTIC_AI_NO_BANNER=1 \
    PILOT_DATA_DIR=/data PILOT_CORPORA_DIR=/app/corpora PILOT_CONTROLLER_BIN=/app/bin/game-controller
USER 10010:10010
WORKDIR /app
EXPOSE 8780
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD /opt/venv/bin/python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8780/healthz', timeout=3).read() == b'ok' else 1)"
ENTRYPOINT ["/usr/bin/tini", "--", "/app/docker/entrypoint.sh"]
```

  **Litestream** is pinned to v0.5.17 (released 2026-08-31). Its asset is
  `litestream-0.5.17-linux-x86_64.tar.gz`, sha256
  `cfb371176d164437ae869f8351cfde49bd1804ae71c61923f75c9cba9c9c006d`, taken from the GitHub release API on
  2026-10-06. Check that `litestream version` runs in the built image. If the tarball holds the binary
  under a subdirectory, adjust the `tar` member path; do not change the pin.

  **Cargo workspace.** If the controller cannot build with only `crates/` present (it may read
  `corpora/` at compile time), copy whatever it needs into the `rust` stage and note why. The Windows agent
  crate must not be built.

- [ ] **Step 7: Write `scripts/image-smoke.sh`** (bash; argument `IMAGE`). It:
  - runs the image with `-p 127.0.0.1:18780:8780` and a fresh temp dir owned by 10010 as `/data`;
  - waits up to 60 s for `docker inspect` to report healthy;
  - checks that `curl -s 127.0.0.1:18780/healthz` is `ok`, and that `/` answers 302 or 303 to `/pair`, or
    whatever sign-in path the app uses;
  - checks that a request with `X-Forwarded-For` and no proxy secret from a non-trusted source is not treated
    as proxied (use the app's existing proxy test expectations to pick the assertion);
  - runs `docker exec <c> pilot data check --from /app`, expecting exit 0 with "nothing missing" or "no old
    install". Adapt the assertion to what `data check` prints for a root with no `runs/`;
  - runs `docker exec <c> sh -c 'ls -a /app; test ! -e /app/.env && test ! -e /app/runs && test ! -e /app/.git'`;
  - checks `docker exec <c> id -u` is `10010`;
  - stops the container with `docker stop` and asserts it exits within 45 s;
  - removes the container.

  It prints each check, and exits non-zero on the first failure.

- [ ] **Step 8: Build and smoke locally.** Run `docker build -t game-pilot:dev .`, then
  `scripts/image-smoke.sh game-pilot:dev`. Note the image size (`docker image ls game-pilot:dev`) in the
  report; the expected size is about 250-300 MB.

- [ ] **Step 9: Run the tests.** Run `.venv/bin/pytest tests/test_image_files.py -q`, then the full non-UI
  suite.

- [ ] **Step 10: Commit.** Run `git add Dockerfile .dockerignore docker scripts/image-smoke.sh tests/test_image_files.py`
  then `scripts/ci-commit.sh "feat(image): the Game Pilot appliance image" "<body>"`.

---

### Task 4: The portable install (compose and .env.example)

**Files:**
- Create: `compose.yaml`, `.env.example`.
- Modify: `README.md` (a "Run it with Docker" section first, then "Run it from a checkout"), `docs/pilot.md`
  (a "Container" section: settings, data folder, Litestream on/off and restore, upgrading).
- Test: `tests/test_env_example.py` (new).

**Interfaces:**
- Consumes (Task 3): the image's variables and paths.
- Produces: `compose.yaml` exactly as spec ruling 8. `.env.example` has the groups `# Required`, `# Common`,
  `# Optional` and `# Set by the image (do not set)`.

- [ ] **Step 1: Write the failing test** (`tests/test_env_example.py`)

```python
"""Every setting the app reads is documented for a container install (appliance image design, ruling 7)."""

from __future__ import annotations

import re
from pathlib import Path

import yaml   # if PyYAML is not installed, parse compose.yaml with a minimal check instead (see Step 3)

ROOT = Path(__file__).resolve().parents[1]
# read in tests only, or internal hooks; never set by a user
INTERNAL = {"PILOT_SUPERVISOR_ARGV", "PILOT_RESUME_DELAY_S", "PILOT_RUNS_DIR"}


def read_by_code() -> set[str]:
    names = set()
    for p in (ROOT / "src/pilot").glob("*.py"):
        names |= set(re.findall(r"\b((?:PILOT|GAME|LITESTREAM)_[A-Z0-9_]+|(?:GEMINI|GOOGLE|ANTHROPIC|OPENAI)_API_KEY)\b",
                                p.read_text(encoding="utf-8")))
    return names


def documented() -> set[str]:
    return set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]+)=", (ROOT / ".env.example").read_text(), re.M))


def test_every_setting_the_code_reads_is_in_env_example():
    missing = read_by_code() - documented() - INTERNAL
    assert not missing, sorted(missing)


def test_env_example_holds_no_values_for_secrets():
    text = (ROOT / ".env.example").read_text()
    for key in ("GEMINI_API_KEY", "GAME_AGENT_TOKEN", "PILOT_PROXY_SECRET", "PILOT_DASHBOARD_KEY"):
        assert re.search(rf"^#?\s*{key}=\s*$", text, re.M), key


def test_compose_is_the_portable_service():
    c = yaml.safe_load((ROOT / "compose.yaml").read_text())
    s = c["services"]["game-pilot"]
    assert s["image"].startswith("ghcr.io/jad0083/game-pilot:")
    assert s["restart"] == "unless-stopped" and s["stop_grace_period"] == "40s"
    assert s["env_file"] == ".env" and any(v.endswith(":/data") for v in s["volumes"])
```

- [ ] **Step 2: Run it to see it fail.** Run `.venv/bin/pytest tests/test_env_example.py -q`. Expected: the
  files are missing.

- [ ] **Step 3: Write `compose.yaml`** (spec ruling 8, verbatim) and `.env.example`.
  - In `.env.example`, each variable is a line `NAME=` (secrets empty) or `NAME=<default>`, after a `# one
    line` comment.
  - Group the lines:
    - **Required:** `GEMINI_API_KEY`, `GAME_AGENT_URL`, `GAME_AGENT_TOKEN`.
    - **Common:** `GAME_RESOLUTION`, `PILOT_PUBLIC_URL`, `PILOT_TRUSTED_PROXIES`, `PILOT_PROXY_SECRET`,
      `PILOT_DASHBOARD_KEY`, `PILOT_RESUME`, `PILOT_NOTIFY_URL`.
    - **Optional:** everything else the code reads, including `GOOGLE_API_KEY`, `ANTHROPIC_API_KEY`,
      `OPENAI_API_KEY`, the `LITESTREAM_*` variables and every other `PILOT_*`/`GAME_*` variable.
    - **Set by the image:** `PILOT_DATA_DIR`, `PILOT_CORPORA_DIR`, `PILOT_CONTROLLER_BIN`, commented out.
  - Give each a one-line description. Take its meaning and default from `config.py` and `docs/pilot.md`'s
    settings table; do not guess.
  - **PyYAML.** If PyYAML is not in the venv, do not add it to runtime dependencies. Either add it to the dev
    extra, or replace `yaml.safe_load` with checks over the text: the image line, `restart: unless-stopped`,
    `stop_grace_period: 40s`, `env_file: .env`, `:/data`.

- [ ] **Step 4: Write the docs.**
  - **README, "Run it with Docker":**
    1. `curl -O` the `compose.yaml` and `.env.example` from the repository (or clone it);
    2. `cp .env.example .env` and fill in the three required values;
    3. `mkdir data && sudo chown 10010:10010 data`;
    4. `docker compose up -d`;
    5. `docker compose exec game-pilot pilot dashboard-link` to sign in.
  - **README, "Run it from a checkout":** the existing setup, plus one unit (`scripts/install-services.sh`).
  - **docs/pilot.md, "Container":**
    - the settings table points at `.env.example`;
    - the data folder and its uid;
    - Litestream: the replica URL and keys, and restoring by starting on an empty folder;
    - upgrading: pull a new image and `docker compose up -d`; a live run resumes.

- [ ] **Step 5: Run the tests.** Run `.venv/bin/pytest tests/test_env_example.py tests/test_docs_paths.py -q`,
  then the full non-UI suite. Also run `docker compose -f compose.yaml config` with a temp `.env` copied from
  `.env.example`; it must parse.

- [ ] **Step 6: Commit.** Run `git add compose.yaml .env.example README.md docs/pilot.md tests/test_env_example.py`
  then `scripts/ci-commit.sh "feat: a portable compose install" "<body>"`. If you add PyYAML to the dev
  extra, include `pyproject.toml`.

---

### Task 5: CI builds and pushes the image

**Files:**
- Create: `.github/workflows/image.yml`.
- Modify: `ARCHITECTURE.md` (an "Image and supervisor" section), `AGENTS.md` §1's table (a row: "Image:
  `ghcr.io/jad0083/game-pilot`, built by `.github/workflows/image.yml`").
- Test: `tests/test_workflow.py` (new): the workflow parses, uses `scripts/image-smoke.sh`, pushes the three
  tags, and has `paths-ignore` for `**.md` and `docs/**`.

**Interfaces:**
- Consumes (Tasks 3 and 4): the `Dockerfile` and `scripts/image-smoke.sh`.
- Produces: images at `ghcr.io/jad0083/game-pilot:<version>`, `:sha-<short>` and `:latest`.

- [ ] **Step 1: Write the failing test** (`tests/test_workflow.py`)

```python
"""The image workflow (appliance image design, ruling 10)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_workflow_builds_smokes_and_pushes_three_tags():
    text = (ROOT / ".github/workflows/image.yml").read_text()
    for must in ("scripts/image-smoke.sh", "ghcr.io/jad0083/game-pilot", ":sha-", ":latest", "paths-ignore",
                 '"**.md"', '"docs/**"', "packages: write", "cargo test -p game-controller", "pytest -q -m \"not ui\""):
        assert must in text, must
```

- [ ] **Step 2: Run it to see it fail.** Run `.venv/bin/pytest tests/test_workflow.py -q`.

- [ ] **Step 3: Write `.github/workflows/image.yml`**, modelled on the subtitler precedent (planning ruling P4).
  - It runs `on: push: branches: [main]` with `paths-ignore: ["**.md", "docs/**", "games/**"]`, and on
    `workflow_dispatch`.
  - It sets `concurrency: {group: image-${{ github.ref }}, cancel-in-progress: false}`.
  - **Job `preflight`** (ubuntu-latest):
    - check out the repo;
    - `dtolnay/rust-toolchain@stable`;
    - `cargo test -p game-controller`;
    - `actions/setup-python@v5` with 3.13;
    - `python -m venv .venv && .venv/bin/pip install -e '.[dev]'`;
    - `.venv/bin/ruff check .`;
    - `.venv/bin/pytest -q -m "not ui"`;
    - read the version from `pyproject.toml` into an output.
  - **Job `image`**, which needs `preflight`, with `permissions: {contents: read, packages: write}`:
    - check out the repo;
    - `docker/setup-buildx-action@v3`;
    - build with `--load` as `game-pilot:ci`;
    - run `scripts/image-smoke.sh game-pilot:ci`;
    - `docker/login-action@v3` to ghcr with `GITHUB_TOKEN`;
    - tag and push:
      - `:sha-${GITHUB_SHA::7}` always;
      - `:latest` always;
      - `:<version>` only if `docker manifest inspect ghcr.io/jad0083/game-pilot:<version>` fails, i.e. it
        is not yet published;
    - print the pushed digest (`docker buildx imagetools inspect ... --format '{{json .Manifest.Digest}}'`)
      in the job summary.
  - Add the label `org.opencontainers.image.source=https://github.com/jad0083/game-harness` at build time
    (`--label`), so the package links to the public repository.

- [ ] **Step 4: Write the docs.**
  - ARCHITECTURE.md, "Image and supervisor": the three stages, the entrypoint, the supervisor and its store
    row, resume, and the two installs.
  - AGENTS.md §1: the image row.

- [ ] **Step 5: Run the tests.** Run `.venv/bin/pytest tests/test_workflow.py -q`, then the full non-UI suite.
  If `actionlint` is installed, run it on the workflow; if not, note that in the report.

- [ ] **Step 6: Commit.** Run `git add .github/workflows/image.yml ARCHITECTURE.md AGENTS.md tests/test_workflow.py`
  then `scripts/ci-commit.sh "ci: build, smoke-test and push the appliance image" "<body>"`.
  - The push may be refused if the git credential lacks the `workflow` scope. Report that as BLOCKED with the
    exact error; the controller decides.

---

## Rollout (controller steps, after the branch is merged; spec "Rollout")

These steps touch other repositories, OpenBao, NPM and two hosts, so the controller runs them; they are not
implementer tasks. The user supplies the OpenBao admin token (`mint-admin-token.sh`) and the NPM credentials.
Possibly the user also does the `Stacks` sync UI step.

- **R1. Release.**
  - Push `main`, and watch the workflow run (GitHub's web UI or API, through `curl` with no token, since the
    repository is public).
  - Record the digest.
  - Check that the package `ghcr.io/jad0083/game-pilot` is public: an anonymous
    `docker pull ghcr.io/jad0083/game-pilot:<version>` from deb-dock1 works.
  - If the workflow cannot be pushed (token scope) or run, build and push from deb-mini2 instead. Use
    `docker buildx build --push` after `docker login ghcr.io` with a token the user provides; ask.
- **R2. The estate stack** (`/home/jad/stacks/apps/games/game-pilot/`):
  - `compose.yaml`: per spec ruling 11, with the image pinned `:<version>@sha256:<digest>`.
  - `komodo.toml`: `server = "deb-dock1"`, `deploy = false` at first, with the `[[GAME_PILOT_*]]` mappings
    and `secret_refs`.
  - `README.md`: the runbook.
  - Run that repo's `python3 -m pytest tests -q`, then commit and push (`push-repos.py --push` or `git push`).
- **R3. Secrets and the guard** (komodo repo and OpenBao):
  - Write `secret/apps/game-pilot/GEMINI_API_KEY` and `AGENT_TOKEN`; read the values from `.env` and the
    drop-in by single key, and never print them.
  - Grant deb-dock1's AppRole read (the shared `secret/data/apps/*` policy may already cover it; check).
  - Add the three template lines to `stacks/deb-dock1/agent/templates/periphery.config.toml.ctmpl`.
  - Restart `openbao-agent` and Periphery on deb-dock1.
  - Add the DOCKER-USER guard for 8780 on deb-dock1, like voicestudio's, and run the komodo repo's tests.
- **R4. Freeze and copy.**
  - Stop `game-pilot-view.service` on deb-mini2.
  - Make `install -d -o 10010 -g 10010 -m 0700 /mnt/dockervol/game-pilot/data` on deb-dock1.
  - Copy `pilot.db` and `auth.sqlite` with `sqlite3`'s `.backup`, then `frames/`, `learned/` and `secrets/`
    (`rsync -a`), and `chown -R 10010:10010`.
  - Compare row counts per table and `PRAGMA integrity_check` on both sides.
- **R5. Deploy.**
  - Set `deploy = true` and push.
  - Add the stack's path to the `Stacks` sync (through the API if the controller can, else ask the user).
  - Check:
    - the container is healthy;
    - `/` redirects;
    - the history lists 54 runs or more;
    - `/api/pc` (signed in, as in the data-platform check) reaches mini-rig2.
- **R6. Route.**
  - Repoint NPM host 54 to `192.168.1.53:8780`.
  - Check `https://gamepilot.saczone.com` gives the Authelia redirect.
  - Check that a request to 192.168.1.53:8780 from a host other than NPM is dropped.
- **R7. Live check.**
  - Start the game on mini-rig2 (as on 2026-10-06), then start a run from the dashboard.
  - Once it has played a turn, redeploy the stack from Komodo. Confirm the run stops and a resumed run starts
    within a minute, in the same campaign.
  - Stop the run and exit the game.
- **R8. Retire and record.**
  - Disable and remove deb-mini2's viewer unit.
  - Remove 8780 from `npm-only-guard.sh` (with its test), and keep `runs/` there.
  - Update AGENTS.md §1's Dashboard row (deb-dock1, the container, `docker exec game-pilot pilot dashboard-link`).
  - Tick `plan.md` Portability 2, and add `issues.md` entries for anything left open.
