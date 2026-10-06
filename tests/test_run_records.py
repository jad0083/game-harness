"""Run records in the store (data platform design, rulings 2, 6, 9; plan rulings P1-P2): events and run
state in pilot.db, no events.jsonl or status.json, traces in decisions.trace, frames as files with
retention."""

from __future__ import annotations

import json
import sqlite3

import pytest

from pilot import events
from pilot.dashboard import list_runs, read_events
from pilot.events import EventLog
from pilot.store import open_store


def test_events_and_state_go_to_the_store_not_files(tmp_path):
    log = EventLog(tmp_path, "20261005-120000", "google:gemini-pro-latest")
    log.emit("run_start", game="civ6", model="google:gemini-pro-latest")
    log.state.status = "playing"
    log.emit("status", status="playing")
    st = open_store(tmp_path)
    assert [e["kind"] for e in read_events(st, "20261005-120000", set())] == ["run_start", "status"]
    row = st.query("SELECT data FROM run_state WHERE run_id='20261005-120000'")[0]
    assert json.loads(row["data"])["status"] == "playing"
    assert not list(tmp_path.rglob("events.jsonl")) and not list(tmp_path.rglob("status.json"))


def test_a_trace_lives_in_its_decision_row(tmp_path):
    log = EventLog(tmp_path, "20261005-120000", "m")
    log.emit("run_start", game="civ6", model="m")
    ref = log.save_trace(3, {"date": "T10", "decision": "keep", "steps": [{"type": "prompt", "text": "hi"}]})
    assert ref == "decision:20261005-120000:3"
    tr = open_store(tmp_path).query("SELECT trace FROM decisions WHERE run_id=? AND episode=3", ("20261005-120000",))
    assert json.loads(tr[0]["trace"])["steps"][0]["text"] == "hi"
    assert not list(tmp_path.rglob("traces"))


def test_frames_keep_the_newest_n_latest_and_kept_ones(tmp_path):
    log = EventLog(tmp_path, "r1", "m", frames_keep=3)
    kept = log.frame(b"\xff\xd8 attention", keep=True)
    names = [log.frame(b"\xff\xd8 %d" % i) for i in range(6)]
    d = tmp_path / "frames" / "r1"
    on_disk = sorted(p.name for p in d.glob("[0-9]*.jpg"))
    assert on_disk == sorted([kept, *names[-3:]]) and (d / "latest.jpg").read_bytes() == b"\xff\xd8 5"
    log.release(kept)
    log.frame(b"\xff\xd8 next")
    assert kept not in {p.name for p in d.glob("[0-9]*.jpg")}


def test_list_runs_reads_the_store(tmp_path):
    log = EventLog(tmp_path, "20261005-120000", "m")
    log.emit("run_start", game="civ6", model="m")
    log.state.info["game"] = "civ6"
    log.state.episodes = 2
    log.frame(b"\xff\xd8 x")
    log.emit("status", status="playing")
    rows = list_runs(open_store(tmp_path), live_id="20261005-120000")
    assert rows[0]["id"] == "20261005-120000" and rows[0]["live"] and rows[0]["game"] == "civ6"
    assert rows[0]["decisions"] == 2 and rows[0]["frame"] is True


class _FullDisk:
    """A store whose writes fail while `full` is set (a full disk), and succeed after."""

    def __init__(self, store):
        self.store, self.full = store, True

    def record(self, *a):
        if self.full:
            raise sqlite3.OperationalError("database or disk is full")
        return self.store.record(*a)

    def _exec(self, *a):
        if self.full:
            raise sqlite3.OperationalError("database or disk is full")
        return self.store._exec(*a)


def test_a_store_that_keeps_failing_ends_the_run_on_the_tenth_write(tmp_path, capsys):
    """One policy for a full disk: emit swallows a transient store failure, but the 10th failed write in a
    row raises (as the journal and the learned writes always did), so the run stops loudly."""
    assert events.STORE_FAILURES_TO_STOP == 10
    store = _FullDisk(open_store(tmp_path))
    log = EventLog(tmp_path, "r1", "m", telemetry=store)
    for _ in range(9):
        log.emit("status", status="playing")                   # swallowed, printed
    assert capsys.readouterr().out.count("store write failed") == 9
    with pytest.raises(sqlite3.OperationalError, match="disk is full"):
        log.emit("status", status="playing")
    assert "10 store writes failed in a row" in capsys.readouterr().out


def test_a_successful_store_write_resets_the_failure_count(tmp_path):
    store = _FullDisk(open_store(tmp_path))
    log = EventLog(tmp_path, "r1", "m", telemetry=store)
    for _ in range(9):
        log.emit("status", status="playing")
    store.full = False
    log.emit("status", status="playing")                       # a success: the count starts again
    store.full = True
    for _ in range(9):
        log.emit("status", status="playing")
    with pytest.raises(sqlite3.OperationalError):
        log.emit("status", status="playing")
