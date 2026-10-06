"""The dashboard supervises one pilot run (appliance image design, ruling 5)."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import signal
import sqlite3
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from pilot import supervisor as supervisor_mod
from pilot.store import open_store
from pilot.supervisor import MissingSettings, Supervisor, SupervisorBusy, resume_enabled, run_requirements

pytestmark = pytest.mark.anyio            # the async tests run in one asyncio loop each (anyio's plugin)

SRC = Path(__file__).resolve().parents[1] / "src"

CHILD = textwrap.dedent("""
    import os, signal, sys, time
    mode = os.environ.get("FAKE_MODE", "run")
    print("started", os.getpid(), flush=True)
    if mode == "crash":
        print("bad key", flush=True); sys.exit(3)
    if mode == "end":
        print("campaign over", flush=True); sys.exit(0)
    def bye(*_):
        print("stopping", flush=True); sys.exit(0)
    def count(*_):                       # "stubborn": one line per SIGTERM, and it keeps running
        print("sigterm", flush=True)
    signal.signal(signal.SIGTERM, count if mode == "stubborn" else bye)
    while True:
        time.sleep(0.05)
""")
STARTED: list[Supervisor] = []            # every supervisor a test makes, so its child never outlives the test


@pytest.fixture(autouse=True)
def _reap_children():
    """A fake child runs in its own session: a test that fails before stopping it would leave it running."""
    yield
    while STARTED:
        proc = STARTED.pop()._proc
        if proc is not None and proc.returncode is None:
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(proc.pid, signal.SIGKILL)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def child(tmp_path):
    p = tmp_path / "child.py"
    p.write_text(CHILD)
    return [sys.executable, str(p)]


def sup(tmp_path, child, mode="run", **kw):
    out = []
    s = Supervisor(open_store(tmp_path / "data"), argv=child, env={**os.environ, "FAKE_MODE": mode},
                   out=type("W", (), {"write": lambda self, t: out.append(t), "flush": lambda self: None})(),
                   stop_wait_s=kw.pop("stop_wait_s", 2), **kw)
    STARTED.append(s)
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
    assert not again.running
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


async def test_a_page_stop_is_never_resumed_and_gets_no_second_sigterm(tmp_path, child):
    """Stop on the page goes to the live pilot; the viewer then notes it. A dashboard stop meanwhile sends the
    stopping run no SIGTERM (the pilot takes a second signal as "leave now", without pausing the game): it
    waits, then kills. The row is not live, so nothing resumes."""
    exits = []
    s, out = sup(tmp_path, child, mode="stubborn", stop_wait_s=0.5,
                 emit_exit=lambda code, lines: exits.append(code))
    await s.start("me")
    await wait_for(lambda: any("pilot: started" in t for t in out))
    s.note_stop()
    assert s.running and s.state()["live"] is False
    await s.stop(keep_live=True)                       # a deploy right after the Stop
    assert not s.running and s.state()["live"] is False and s.state()["last_exit"]["code"] == -signal.SIGKILL
    assert not any("sigterm" in t for t in out), out
    assert exits == [-signal.SIGKILL]                   # the run's own exit, for its run_exit event
    again, _ = sup(tmp_path, child)
    assert await again.resume_if_wanted(enabled=True, delay_s=0) is False


async def test_a_page_stop_then_the_runs_own_exit(tmp_path, child):
    s, out = sup(tmp_path, child)
    await s.start("me")
    await wait_for(lambda: any("pilot: started" in t for t in out))
    s.note_stop()
    os.kill(s._proc.pid, signal.SIGTERM)               # stands in for the pilot leaving after the page's Stop
    await wait_for(lambda: not s.running)
    assert s.state()["live"] is False and s.state()["last_exit"]["code"] == 0


async def test_a_child_that_ignores_sigterm_is_killed(tmp_path, child):
    s, out = sup(tmp_path, child, mode="stubborn", stop_wait_s=0.3)
    await s.start("me")
    await wait_for(lambda: any("pilot: started" in t for t in out))
    t0 = time.monotonic()
    await s.stop(keep_live=False)
    assert time.monotonic() - t0 < 5
    assert any("pilot: sigterm" in t for t in out), out
    st = s.state()
    assert not s.running and st["live"] is False and st["last_exit"]["code"] == -signal.SIGKILL


async def test_stop_with_no_child(tmp_path, child):
    s, _ = sup(tmp_path, child)
    s._write(live=True, since=1.0, by="me")            # a run live before this dashboard started
    await s.stop(keep_live=True)
    assert s.state()["live"] is True
    await s.stop(keep_live=False)
    assert s.state()["live"] is False and not s.running


async def test_an_exit_just_before_a_dashboard_stop_stays_the_runs_own(tmp_path, child, monkeypatch):
    """A child that crashed a moment before the dashboard stopped (its watcher not yet round) is a crash:
    not live, its exit recorded on its run, and no resume."""
    monkeypatch.setattr(supervisor_mod, "EXIT_POLL_S", 1.0)       # the watcher looks once a second
    exits = []
    s, _ = sup(tmp_path, child, mode="crash", emit_exit=lambda code, lines: exits.append(code))
    await s.start("me")
    await wait_for(lambda: s._proc.returncode is not None)
    assert s.running                                    # exited, the watcher not yet round
    await s.stop(keep_live=True)
    assert s.state()["live"] is False and s.state()["last_exit"]["code"] == 3 and exits == [3]
    again, _ = sup(tmp_path, child)
    assert await again.resume_if_wanted(enabled=True, delay_s=0) is False


async def test_a_failed_row_write_at_start_stops_the_child(tmp_path, child):
    s, _ = sup(tmp_path, child, stop_wait_s=2)
    write = s._write
    calls = []

    def failing(**changes):
        calls.append(changes)
        if len(calls) == 1:
            raise sqlite3.OperationalError("disk I/O error")
        return write(**changes)
    s._write = failing
    with pytest.raises(sqlite3.OperationalError):
        await s.start("me")
    assert not s.running and s._proc.returncode is not None
    assert s.state()["live"] is False


def test_start_refused_names_missing_settings(tmp_path):
    absent = tmp_path / "absent"                   # never the checkout's own .agent_token
    prefs = {"models": [{"model": "google:gemini-pro-latest", "thinking": "high"}]}
    assert run_requirements({}, prefs, token_file=absent) == ["GAME_AGENT_URL", "GAME_AGENT_TOKEN", "GEMINI_API_KEY"]
    env = {"GAME_AGENT_URL": "http://pc:8765", "GAME_AGENT_TOKEN": "t" * 40, "GOOGLE_API_KEY": "x"}
    assert run_requirements(env, prefs, token_file=absent) == []
    assert run_requirements({**env, "GOOGLE_API_KEY": ""}, {"models": [{"model": "anthropic:claude-x"}]},
                            token_file=absent) == ["ANTHROPIC_API_KEY"]
    token = tmp_path / "token"
    token.write_text("t" * 40)
    assert run_requirements({"GAME_AGENT_URL": "http://pc:8765", "OPENAI_API_KEY": "x"},
                            {"models": [{"model": "openai:gpt-x"}]}, token_file=token) == []
    assert "GAME_AGENT_URL" in str(MissingSettings(["GAME_AGENT_URL"]))
    # prefs saved before the model list name one model; PILOT_MODEL only when the prefs name none
    assert run_requirements({**env, "PILOT_MODEL": "google:x"}, {"model": "anthropic:claude-x"},
                            token_file=absent) == ["ANTHROPIC_API_KEY"]
    assert run_requirements({**env, "PILOT_MODEL": "openai:gpt-x"}, {}, token_file=absent) == ["OPENAI_API_KEY"]


def test_sigterm_to_the_viewer_stops_the_child_and_keeps_live(tmp_path, child):
    """A real dashboard process resumes a live run, and SIGTERM stops the child but keeps the row live."""
    import socket
    import threading
    data = tmp_path / "data"
    open_store(data)._exec("INSERT INTO settings(key, value, changed_by, t) VALUES ('supervisor', ?, NULL, 0)",
                           (json.dumps({"live": True, "since": 0, "by": "test", "last_exit": None}),))
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {**os.environ, "PILOT_DATA_DIR": str(data), "PYTHONPATH": str(SRC), "FAKE_MODE": "run",
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
        reader.join(timeout=5)
        for ln in lines:                 # the fake child runs in its own session: it must not outlive the test
            if ln.startswith("pilot: started "):
                with contextlib.suppress(ProcessLookupError, PermissionError, ValueError):
                    os.killpg(int(ln.split()[-1]), signal.SIGKILL)


# ---- the dashboard's side: Start run, /status and the exit record (ruling P3) ----------------------------

SLEEPER = "import time\nwhile True:\n    time.sleep(0.05)\n"
CRASHER = textwrap.dedent("""
    import os, sqlite3, sys, time
    db = sqlite3.connect(os.environ["FAKE_DB"], timeout=5)
    db.execute("INSERT INTO runs(id, game, started) VALUES ('r9', 'civ6', ?)", (time.time(),))
    db.commit()
    db.close()
    print("model key refused", flush=True)
    sys.exit(3)
""")


MARKER = "import os, pathlib, time\npathlib.Path(os.environ['FAKE_MARKER']).write_text('started')\n" \
         "while True:\n    time.sleep(0.05)\n"


def run_settings(monkeypatch, script: Path) -> None:
    """What a run needs (run_requirements) and the child the supervisor starts instead of `pilot run`."""
    monkeypatch.setenv("PILOT_SUPERVISOR_ARGV", f"{sys.executable} {script}")
    monkeypatch.setenv("GAME_AGENT_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("GAME_AGENT_TOKEN", "t" * 40)
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.delenv("PILOT_MODEL", raising=False)


def test_the_dashboard_starts_the_run_through_the_supervisor(tmp_path, monkeypatch):
    from aiohttp.test_utils import TestClient, TestServer

    from pilot import dashboard
    script = tmp_path / "sleeper.py"
    script.write_text(SLEEPER)
    run_settings(monkeypatch, script)
    app = dashboard.make_app(None, tmp_path / "data")
    sup = app[dashboard.SUPERVISOR]
    STARTED.append(sup)

    async def go():
        async with TestClient(TestServer(app)) as c:
            monkeypatch.delenv("GAME_AGENT_URL")
            r = await c.post("/api/run", json={"game": "civ6"})
            assert r.status == 400 and "GAME_AGENT_URL" in await r.text() and not sup.running
            monkeypatch.setenv("GAME_AGENT_URL", "http://127.0.0.1:9")
            r = await c.post("/api/run", json={"game": "civ6"})
            assert r.status == 200, await r.text()
            assert (await r.json())["started"] == "pilot run"
            assert sup.running and sup.state()["live"] is True
            r = await c.post("/api/run", json={"game": "civ6"})
            assert r.status == 409 and "already live" in await r.text()
            st = await (await c.get("/status")).json()
            assert st["live"] is False and st["supervisor"]["live"] is True
    asyncio.run(go())
    # the dashboard's shutdown stopped the child and kept the row live, as a container stop does
    assert not sup.running and sup.state()["live"] is True


def test_a_crash_is_on_status_and_on_the_run_it_started(tmp_path, monkeypatch):
    from aiohttp.test_utils import TestClient, TestServer

    from pilot import dashboard
    from pilot.dashboard import read_events
    script = tmp_path / "crasher.py"
    script.write_text(CRASHER)
    run_settings(monkeypatch, script)
    data = tmp_path / "data"
    tel = open_store(data)
    tel.record("r1", {"t": 1.0, "kind": "run_start", "game": "civ6", "model": "m"})     # an older run
    monkeypatch.setenv("FAKE_DB", str(tel.path))
    app = dashboard.make_app(None, data, tel)
    sup = app[dashboard.SUPERVISOR]
    STARTED.append(sup)

    async def go():
        async with TestClient(TestServer(app)) as c:
            assert (await c.post("/api/run", json={"game": "civ6"})).status == 200
            await wait_for(lambda: not sup.running)
            st = await (await c.get("/status")).json()
            assert st["supervisor"]["live"] is False
            assert st["supervisor"]["last_exit"]["code"] == 3
            assert "model key refused" in st["supervisor"]["last_exit"]["lines"]
    asyncio.run(go())
    exits = read_events(tel, "r9", {"run_exit"})
    assert [(e["code"], "model key refused" in e["lines"]) for e in exits] == [(3, True)]
    assert read_events(tel, "r1", {"run_exit"}) == []


def viewer_with_a_live_row(tmp_path, monkeypatch, **env):
    """A viewer app over a data directory whose supervisor row says a run was live; its child would leave
    a marker file."""
    from pilot import dashboard
    script = tmp_path / "marker.py"
    script.write_text(MARKER)
    run_settings(monkeypatch, script)
    monkeypatch.setenv("FAKE_MARKER", str(tmp_path / "started"))
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    data = tmp_path / "data"
    open_store(data)._exec("INSERT INTO settings(key, value, changed_by, t) VALUES ('supervisor', ?, NULL, 0)",
                           (json.dumps({"live": True, "since": 0, "by": "test", "last_exit": None}),))
    app = dashboard.make_app(None, data)
    STARTED.append(app[dashboard.SUPERVISOR])
    return app, app[dashboard.SUPERVISOR]


def test_resume_off_at_startup_marks_the_run_not_live(tmp_path, monkeypatch, capsys):
    from aiohttp.test_utils import TestClient, TestServer
    app, sup = viewer_with_a_live_row(tmp_path, monkeypatch, PILOT_RESUME="0", PILOT_RESUME_DELAY_S="0")

    async def go():
        async with TestClient(TestServer(app)) as c:
            await asyncio.sleep(0.3)
            assert (await c.get("/status")).status == 200
    asyncio.run(go())
    assert sup.state()["live"] is False and not (tmp_path / "started").exists()
    assert "not resumed: PILOT_RESUME is off" in capsys.readouterr().out


def test_a_dashboard_stop_cancels_a_pending_resume(tmp_path, monkeypatch):
    """Stopped within the resume delay, the dashboard starts nothing (and the run stays live for the next start)."""
    from aiohttp.test_utils import TestClient, TestServer
    app, sup = viewer_with_a_live_row(tmp_path, monkeypatch, PILOT_RESUME_DELAY_S="1")

    async def go():
        async with TestClient(TestServer(app)) as c:
            assert (await c.get("/status")).status == 200
        await asyncio.sleep(1.5)                       # past the delay, in the same loop
    asyncio.run(go())
    assert not (tmp_path / "started").exists() and not sup.running and sup.state()["live"] is True


def test_a_failed_resume_is_said(tmp_path, monkeypatch, capsys):
    from aiohttp.test_utils import TestClient, TestServer
    app, sup = viewer_with_a_live_row(tmp_path, monkeypatch, PILOT_RESUME_DELAY_S="soon")

    async def go():
        async with TestClient(TestServer(app)):
            end = time.monotonic() + 3
            seen = ""
            while "not resumed" not in seen and time.monotonic() < end:
                await asyncio.sleep(0.05)
                seen += capsys.readouterr().out
            return seen
    seen = asyncio.run(go())
    assert "the pilot run was not resumed" in seen and "soon" in seen, seen
    assert not sup.running


def test_a_store_error_declining_the_resume_does_not_stop_the_viewer(tmp_path, monkeypatch, capsys):
    """PILOT_RESUME off and the store raising on the decline write: one line, the viewer still serves."""
    from aiohttp.test_utils import TestClient, TestServer

    from pilot.supervisor import Supervisor

    app, _sup = viewer_with_a_live_row(tmp_path, monkeypatch, PILOT_RESUME="0")

    def boom(self):
        raise OSError("database is locked")
    monkeypatch.setattr(Supervisor, "decline_resume", boom)

    async def go():
        async with TestClient(TestServer(app)) as c:
            await asyncio.sleep(0.3)
            r = await c.get("/healthz")
            assert r.status == 200 and await r.text() == "ok"
    asyncio.run(go())
    out = capsys.readouterr().out
    assert "could not mark the pilot run not live" in out and "database is locked" in out
