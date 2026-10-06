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


# an old runs/telemetry.sqlite: no meta table, campaigns without title, decisions without the model columns
OLD_TELEMETRY = """
CREATE TABLE campaigns (id TEXT PRIMARY KEY, game TEXT NOT NULL, name TEXT NOT NULL, created REAL NOT NULL);
CREATE TABLE events (run_id TEXT NOT NULL, t REAL NOT NULL, kind TEXT NOT NULL, data TEXT NOT NULL);
CREATE TABLE decisions (run_id TEXT NOT NULL, episode INTEGER NOT NULL, campaign_id TEXT, t REAL, date TEXT,
    month INTEGER, trigger TEXT, decision TEXT, reason TEXT, outcome TEXT, current TEXT, tokens_in INTEGER,
    tokens_out INTEGER, seconds REAL, trace TEXT, result TEXT, PRIMARY KEY (run_id, episode));
INSERT INTO campaigns VALUES ('stellaris/c', 'stellaris', 'c', 1.0);
INSERT INTO decisions(run_id, episode, campaign_id, decision) VALUES ('r', 1, 'stellaris/c', 'expand');
"""


def _old_telemetry(path):
    db = sqlite3.connect(path)
    db.executescript(OLD_TELEMETRY)
    db.close()


def _version(st) -> str:
    return st.query("SELECT value FROM meta WHERE key='schema_version'")[0]["value"]


def test_a_version_1_database_is_migrated_forward(tmp_path):
    db = sqlite3.connect(tmp_path / "pilot.db")
    db.executescript(S.TELEMETRY_TABLES + "INSERT INTO meta VALUES ('schema_version', '1');"
                     "INSERT INTO campaigns(id, game, name, created) VALUES ('civ6/k', 'civ6', 'k', 1.0);")
    db.close()
    st = S.Store(tmp_path / "pilot.db")
    assert int(_version(st)) == S.SCHEMA_VERSION
    assert "title" in {r["name"] for r in st.query("PRAGMA table_info(campaigns)")}
    assert st.query("SELECT name FROM sqlite_master WHERE name IN ('settings', 'events_kind') ORDER BY name") == [
        {"name": "events_kind"}, {"name": "settings"}], "step 2"
    assert st.query("SELECT id FROM campaigns") == [{"id": "civ6/k"}]


def test_an_old_telemetry_database_without_meta_is_migrated_with_its_rows(tmp_path):
    _old_telemetry(tmp_path / "pilot.db")
    st = S.Store(tmp_path / "pilot.db")
    assert _version(st) == str(S.SCHEMA_VERSION)
    assert "title" in {r["name"] for r in st.query("PRAGMA table_info(campaigns)")}
    assert {"model", "model_version", "thinking"} <= {r["name"] for r in st.query("PRAGMA table_info(decisions)")}
    assert st.query("SELECT name FROM sqlite_master WHERE name='settings'"), "step 2's tables"
    assert st.query("SELECT decision FROM decisions") == [{"decision": "expand"}]


def test_a_database_at_the_current_version_is_not_migrated_again(tmp_path):
    S.Store(tmp_path / "pilot.db").close()
    db = sqlite3.connect(tmp_path / "pilot.db")
    db.executescript("DROP TABLE run_state; CREATE TABLE sentinel(x); INSERT INTO sentinel VALUES (1);")
    db.close()
    st = S.Store(tmp_path / "pilot.db")
    assert _version(st) == str(S.SCHEMA_VERSION)
    assert not st.query("SELECT name FROM sqlite_master WHERE name='run_state'"), "no schema script ran"
    assert st.query("SELECT x FROM sentinel") == [{"x": 1}]


def test_a_newer_database_keeps_its_version(tmp_path):
    S.Store(tmp_path / "pilot.db").close()
    db = sqlite3.connect(tmp_path / "pilot.db")
    db.executescript(f"UPDATE meta SET value='{S.SCHEMA_VERSION + 1}' WHERE key='schema_version'; DROP TABLE run_state;")
    db.close()
    st = S.Store(tmp_path / "pilot.db")              # opens without migrating, and without an error
    assert _version(st) == str(S.SCHEMA_VERSION + 1), "a stored version is never lowered"
    assert not st.query("SELECT name FROM sqlite_master WHERE name='run_state'")


def _open_at_once(path, barrier, opened, errors):
    barrier.wait()
    try:
        opened.append(S.Store(path))
    except Exception as e:  # noqa: BLE001 - collected for the assertion
        errors.append(e)


@pytest.mark.parametrize("start", ["empty", "old telemetry"])
def test_two_processes_migrating_at_once_both_succeed(tmp_path, start):
    """The pilot and the viewer open the same file at the same moment; the second waits for the first's
    migration instead of repeating it (a repeated ALTER TABLE fails with 'duplicate column name')."""
    for i in range(10):
        path = tmp_path / str(i) / "pilot.db"
        path.parent.mkdir()
        if start == "old telemetry":
            _old_telemetry(path)
        barrier, opened, errors = threading.Barrier(2), [], []
        ts = [threading.Thread(target=_open_at_once, args=(path, barrier, opened, errors)) for _ in range(2)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        assert errors == [] and len(opened) == 2
        assert {_version(st) for st in opened} == {str(S.SCHEMA_VERSION)}
        assert [r["name"] for r in opened[0].query("PRAGMA table_info(campaigns)")].count("title") == 1
        for st in opened:
            st.close()


def test_a_corrupt_database_is_not_called_an_unwritable_directory(tmp_path):
    (tmp_path / "pilot.db").write_bytes(bytes(range(256)) * 16)
    with pytest.raises(sqlite3.DatabaseError) as e:
        S.Store(tmp_path / "pilot.db")
    assert not isinstance(e.value, S.DataDirError)


def test_a_locked_database_at_open_is_not_called_an_unwritable_directory(tmp_path, monkeypatch):
    def locked(db):
        raise sqlite3.OperationalError("database is locked")
    monkeypatch.setattr(S, "_migrate", locked)
    with pytest.raises(sqlite3.OperationalError, match="database is locked") as e:
        S.Store(tmp_path / "pilot.db")
    assert not isinstance(e.value, S.DataDirError)


def test_campaign_events_of_the_same_millisecond_come_back_in_the_order_written(tmp_path):
    st = S.open_store(tmp_path)
    st.record("b", {"t": 1.0, "kind": "run_start", "game": "civ6", "model": "m"})
    st.record("a", {"t": 1.0, "kind": "run_start", "game": "civ6", "model": "m"})
    st.record("b", {"t": 1.0, "kind": "campaign", "game": "civ6", "name": "k"})
    st.record("a", {"t": 1.0, "kind": "campaign", "game": "civ6", "name": "k"})
    for run, n in (("b", 1), ("a", 2), ("b", 3), ("a", 4)):
        st.record(run, {"t": 5.0, "kind": "order_outcome", "n": n})
    assert [e["n"] for e in st.campaign_events("civ6/k", "order_outcome")] == [1, 2, 3, 4]


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


@pytest.mark.skipif(os.geteuid() == 0, reason="root writes whatever the mode")
@pytest.mark.parametrize("argv", [["prefs", "--get", "game"], ["run", "--game", "civ6"], ["export", "--to", "out"]])
def test_an_unwritable_data_dir_ends_the_cli_with_its_name_not_a_traceback(monkeypatch, tmp_path, capsys, argv):
    from pilot import cli
    ro = tmp_path / "ro"
    ro.mkdir()
    os.chmod(ro, 0o500)
    monkeypatch.setenv("PILOT_DATA_DIR", str(ro / "data"))
    monkeypatch.chdir(tmp_path)
    try:
        assert cli.main(argv) == 1
    finally:
        os.chmod(ro, 0o700)
    out = capsys.readouterr()
    assert f"cannot write the data directory {ro / 'data'}" in out.err and out.err.count("\n") == 1, out.err
    assert "Traceback" not in out.err + out.out


def test_a_relative_data_dir_becomes_absolute(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PILOT_DATA_DIR", "runs")
    s = Settings.from_env()
    assert s.runs_dir.is_absolute() and s.runs_dir == (tmp_path / "runs").resolve()
    assert s.learned_dir.is_absolute()


class _FailingCommit:
    """The store's connection, except that COMMIT fails (a full disk, an I/O error)."""

    def __init__(self, db):
        self._db = db

    def execute(self, sql, *a):
        if sql == "COMMIT":
            raise sqlite3.OperationalError("database or disk is full")
        return self._db.execute(sql, *a)

    def __getattr__(self, name):
        return getattr(self._db, name)


def test_an_error_after_sqlite_rolled_back_by_itself_surfaces_as_the_original(tmp_path):
    st = S.open_store(tmp_path)
    with pytest.raises(ValueError, match="boom"), st.transaction():
        st._exec("INSERT INTO settings(key, value, changed_by, t) VALUES ('k', 'v', NULL, 0)")
        st.db.execute("ROLLBACK")          # what SQLite does itself on SQLITE_FULL or an I/O error
        raise ValueError("boom")
    assert not st.db.in_transaction and st.query("SELECT * FROM settings") == []


def test_a_failed_commit_rolls_back_and_releases_the_write_lock(tmp_path):
    st = S.open_store(tmp_path)
    real = st.db
    st.db = _FailingCommit(real)
    try:
        with pytest.raises(sqlite3.OperationalError, match="disk is full"), st.transaction():
            st._exec("INSERT INTO settings(key, value, changed_by, t) VALUES ('k', 'v', NULL, 0)")
        assert not real.in_transaction
    finally:
        st.db = real
    assert st.query("SELECT * FROM settings") == []
