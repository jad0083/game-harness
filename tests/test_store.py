"""The store (docs/design/2026-10-05-data-platform-design.md, rulings 1-5): one pilot.db per data
directory, WAL, a busy timeout, forward migrations, one cached store per process and path."""

from __future__ import annotations

import os
import sqlite3
import threading

import pytest

from pilot import store as S
from pilot.config import Settings


def test_a_new_store_has_every_table_wal_and_the_current_version(tmp_path):
    st = S.open_store(tmp_path)
    tables = {r["name"] for r in st.query("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"campaigns", "runs", "events", "decisions", "metrics", "plans", "strategies", "meta", "learned_notes",
            "learned_screens", "episodes", "ledger", "journal", "settings", "model_usage", "standing_orders",
            "run_state"} <= tables
    assert st.query("PRAGMA journal_mode")[0]["journal_mode"] == "wal"
    assert st.query("PRAGMA busy_timeout")[0]["timeout"] == 5000
    assert int(st.query("SELECT value FROM meta WHERE key='schema_version'")[0]["value"]) == S.SCHEMA_VERSION
    assert (tmp_path / "pilot.db").exists()


def test_open_store_is_cached_per_path(tmp_path):
    assert S.open_store(tmp_path) is S.open_store(tmp_path)
    assert S.open_store(tmp_path / "other") is not S.open_store(tmp_path)


def test_a_version_1_database_is_migrated_forward(tmp_path):
    db = sqlite3.connect(tmp_path / "pilot.db")
    db.executescript("CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);"
                     "INSERT INTO meta VALUES ('schema_version', '1');"
                     "CREATE TABLE campaigns(id TEXT PRIMARY KEY, game TEXT NOT NULL, name TEXT NOT NULL, created REAL NOT NULL);")
    db.commit()
    db.close()
    st = S.Store(tmp_path / "pilot.db")
    assert int(st.query("SELECT value FROM meta WHERE key='schema_version'")[0]["value"]) == S.SCHEMA_VERSION
    assert "title" in {r["name"] for r in st.query("PRAGMA table_info(campaigns)")}


def test_two_stores_write_concurrently(tmp_path):
    a, b = S.Store(tmp_path / "pilot.db"), S.Store(tmp_path / "pilot.db")   # the pilot and the viewer
    errors = []

    def write(st, kind):
        try:
            for i in range(300):
                st._exec("INSERT INTO events(run_id, t, kind, data) VALUES (?,?,?,?)", ("r", float(i), kind, "{}"))
        except sqlite3.OperationalError as e:
            errors.append(e)
    ts = [threading.Thread(target=write, args=(a, "a")), threading.Thread(target=write, args=(b, "b"))]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert errors == [] and a.query("SELECT count(*) AS n FROM events")[0]["n"] == 600


def test_transaction_rolls_back_on_error(tmp_path):
    st = S.open_store(tmp_path)
    with pytest.raises(RuntimeError), st.transaction():
        st._exec("INSERT INTO settings(key, value, changed_by, t) VALUES ('x', '1', '', 0)")
        raise RuntimeError("boom")
    assert st.query("SELECT * FROM settings WHERE key='x'") == []


def test_paths_come_from_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("PILOT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PILOT_RUNS_DIR", str(tmp_path / "old"))
    monkeypatch.setenv("PILOT_CORPORA_DIR", str(tmp_path / "corpora"))
    monkeypatch.setenv("PILOT_CONTROLLER_BIN", str(tmp_path / "bin/game-controller"))
    monkeypatch.setenv("PILOT_FRAMES_KEEP", "50")
    monkeypatch.setenv("PILOT_EXPORT_DIR", str(tmp_path / "export"))
    monkeypatch.setenv("PILOT_GAME", "civ6")
    s = Settings.from_env()
    assert s.runs_dir == tmp_path / "data", "PILOT_DATA_DIR wins over the PILOT_RUNS_DIR alias"
    assert s.corpus_dir == tmp_path / "corpora/civ6" and s.controller_bin == tmp_path / "bin/game-controller"
    assert s.db_path == tmp_path / "data/pilot.db" and s.frames_dir == tmp_path / "data/frames"
    assert s.learned_dir == tmp_path / "data/learned/civ6" and s.secrets_dir == tmp_path / "data/secrets"
    assert s.frames_keep == 50 and s.export_dir == tmp_path / "export"


def test_unwritable_data_dir_fails_at_start_with_its_name(tmp_path):
    ro = tmp_path / "ro"
    ro.mkdir()
    os.chmod(ro, 0o500)
    try:
        with pytest.raises(S.DataDirError, match=str(ro)):
            S.open_store(ro)
    finally:
        os.chmod(ro, 0o700)
