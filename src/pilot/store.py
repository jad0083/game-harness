"""The pilot's store (docs/design/2026-10-05-data-platform-design.md): one SQLite file, pilot.db, in the
data directory, holding telemetry, learned knowledge, journals, traces (decisions.trace), settings,
model usage, standing orders and run state. WAL mode lets the dashboard read while the pilot writes;
a busy timeout covers the rare moments both write. No other module opens pilot.db."""

from __future__ import annotations

import contextlib
import sqlite3
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .telemetry import Telemetry

DB_NAME = "pilot.db"

BUSY_TIMEOUT_S = 5.0

# The schema, in the migration steps below. Every statement is idempotent (IF NOT EXISTS), so a step that
# meets tables an older telemetry file already has leaves them and their rows alone.
TELEMETRY_TABLES = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS campaigns (
    id TEXT PRIMARY KEY, game TEXT NOT NULL, name TEXT NOT NULL, created REAL NOT NULL, title TEXT);
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY, campaign_id TEXT REFERENCES campaigns(id), game TEXT, model TEXT,
    settings TEXT, started REAL, ended REAL, status TEXT);
CREATE TABLE IF NOT EXISTS events (run_id TEXT NOT NULL, t REAL NOT NULL, kind TEXT NOT NULL, data TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS events_run ON events(run_id, t);
CREATE TABLE IF NOT EXISTS decisions (
    run_id TEXT NOT NULL, episode INTEGER NOT NULL, campaign_id TEXT, t REAL, date TEXT, month INTEGER,
    trigger TEXT, decision TEXT, reason TEXT, outcome TEXT, current TEXT,
    tokens_in INTEGER, tokens_out INTEGER, seconds REAL, trace TEXT, result TEXT,
    model TEXT, model_version TEXT, thinking TEXT,
    PRIMARY KEY (run_id, episode));
CREATE INDEX IF NOT EXISTS decisions_campaign ON decisions(campaign_id, month);
CREATE TABLE IF NOT EXISTS metrics (
    run_id TEXT NOT NULL, campaign_id TEXT, t REAL, date TEXT, month INTEGER, data TEXT NOT NULL,
    PRIMARY KEY (run_id, date));
CREATE INDEX IF NOT EXISTS metrics_campaign ON metrics(campaign_id, month);
CREATE TABLE IF NOT EXISTS plans (campaign_id TEXT, run_id TEXT NOT NULL, t REAL NOT NULL, date TEXT, source TEXT,
    text TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS plans_campaign ON plans(campaign_id, t);
CREATE TABLE IF NOT EXISTS strategies (campaign_id TEXT, run_id TEXT NOT NULL, t REAL, date TEXT, trigger TEXT,
    model TEXT, data TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS strategies_campaign ON strategies(campaign_id, t);
"""

# the data platform's tables (docs/design/2026-10-05-data-platform-design.md, ruling 4) and an index for
# reads by event kind
PLATFORM_TABLES = """
CREATE INDEX IF NOT EXISTS events_kind ON events(kind, t);
CREATE TABLE IF NOT EXISTS learned_notes (
    game TEXT NOT NULL, kind TEXT NOT NULL, text TEXT NOT NULL, why TEXT NOT NULL, model TEXT, run_id TEXT, t TEXT,
    UNIQUE (game, kind, text));
CREATE TABLE IF NOT EXISTS learned_screens (
    game TEXT NOT NULL, name TEXT NOT NULL, description TEXT, roi TEXT, threshold REAL, auto_dismiss INTEGER,
    action TEXT, png BLOB, learned_by TEXT, run_id TEXT, t TEXT, disabled_reason TEXT,
    PRIMARY KEY (game, name));
CREATE TABLE IF NOT EXISTS episodes (
    game TEXT NOT NULL, t TEXT, date TEXT, situation TEXT, decision TEXT, outcome TEXT, model TEXT, run_id TEXT,
    UNIQUE (game, t, situation));
CREATE TABLE IF NOT EXISTS ledger (game TEXT NOT NULL, t TEXT, kind TEXT, data TEXT);
CREATE TABLE IF NOT EXISTS journal (campaign_id TEXT, game TEXT, t REAL, date TEXT, text TEXT NOT NULL,
    UNIQUE (campaign_id, t, text));
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL, changed_by TEXT, t REAL);
CREATE TABLE IF NOT EXISTS model_usage (day TEXT NOT NULL, model TEXT NOT NULL, count INTEGER NOT NULL,
    PRIMARY KEY (day, model));
CREATE TABLE IF NOT EXISTS standing_orders (campaign_id TEXT NOT NULL, position INTEGER NOT NULL, text TEXT NOT NULL,
    PRIMARY KEY (campaign_id, position));
CREATE TABLE IF NOT EXISTS run_state (run_id TEXT PRIMARY KEY, data TEXT NOT NULL, updated REAL);
"""

# sqlite3.OperationalError messages meaning the file or its directory cannot be opened or written
_CANNOT_WRITE = ("unable to open database file", "readonly database", "disk i/o error")


class DataDirError(RuntimeError):
    """The data directory cannot be written; the message names it."""


def _run(db: sqlite3.Connection, script: str) -> None:
    """A schema script inside the open transaction (executescript would commit it first)."""
    for statement in script.split(";"):
        if statement.strip():
            db.execute(statement)


def _columns(db: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in db.execute(f"PRAGMA table_info({table})")}   # fixed table names only


def _step_1(db: sqlite3.Connection) -> None:
    """The telemetry tables; a copied telemetry.sqlite (version 0) gains the columns older files lack."""
    _run(db, TELEMETRY_TABLES)
    if "title" not in _columns(db, "campaigns"):
        db.execute("ALTER TABLE campaigns ADD COLUMN title TEXT")
    cols = _columns(db, "decisions")
    for col in ("model", "model_version", "thinking"):
        if col not in cols:
            db.execute(f"ALTER TABLE decisions ADD COLUMN {col} TEXT")


def _step_2(db: sqlite3.Connection) -> None:
    _run(db, PLATFORM_TABLES)


# STEPS[n - 1] brings a database from version n - 1 to n; version 0 is a file without meta.schema_version
# (a new file or a copied runs/telemetry.sqlite).
STEPS = (_step_1, _step_2)
SCHEMA_VERSION = len(STEPS)


def _stored_version(db: sqlite3.Connection) -> int:
    """meta.schema_version; 0 when the meta table or its row is missing (a new file, a copied telemetry.sqlite)."""
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='meta'").fetchone():
        return 0
    row = db.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    try:
        return int(row[0]) if row else 0
    except (TypeError, ValueError):
        return 0


def _migrate(db: sqlite3.Connection) -> None:
    """Apply the steps above the stored version in one write transaction. A second process opening the
    file meanwhile waits for it (busy timeout), then reads the new version and has nothing to do. A file
    at or above SCHEMA_VERSION is not touched: a stored version is never lowered."""
    if _stored_version(db) >= SCHEMA_VERSION:
        return
    db.execute("BEGIN IMMEDIATE")
    try:
        version = _stored_version(db)            # again under the lock: another process may have migrated
        if version < SCHEMA_VERSION:
            for step in STEPS[version:]:
                step(db)
            db.execute("INSERT INTO meta(key, value) VALUES ('schema_version', ?) "
                       "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(SCHEMA_VERSION),))
    except BaseException:
        if db.in_transaction:                    # SQLite may have rolled it back already (e.g. a full disk)
            db.execute("ROLLBACK")
        raise
    db.execute("COMMIT")


def _wal(db: sqlite3.Connection) -> None:
    """Switch to WAL. The switch needs an exclusive lock, and while another connection opens the same new
    file SQLite answers 'database is locked' at once instead of waiting through the busy handler, so wait
    here, up to the busy timeout."""
    deadline = time.monotonic() + BUSY_TIMEOUT_S
    while True:
        try:
            db.execute("PRAGMA journal_mode=WAL")
            return
        except sqlite3.OperationalError as e:
            if "database is locked" not in str(e) or time.monotonic() > deadline:
                raise
            time.sleep(0.01)


class Store:
    """One connection per instance, shared by its threads under a lock (as Telemetry always did)."""

    def __init__(self, path: Path):
        path = Path(path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise DataDirError(f"cannot write the data directory {path.parent}: {e}") from e
        db = None
        try:
            db = sqlite3.connect(path, check_same_thread=False, isolation_level=None, timeout=BUSY_TIMEOUT_S)
            db.row_factory = sqlite3.Row
            db.execute(f"PRAGMA busy_timeout={int(BUSY_TIMEOUT_S * 1000)}")
            _wal(db)
            db.execute("PRAGMA synchronous=NORMAL")
            _migrate(db)
        except BaseException as e:
            if db is not None:
                db.close()
            if isinstance(e, sqlite3.OperationalError) and any(m in str(e).lower() for m in _CANNOT_WRITE):
                raise DataDirError(f"cannot write {path.name} in the data directory {path.parent}: {e}") from e
            raise
        self.db = db
        self.path = path
        self._lock = threading.RLock()

    def close(self) -> None:
        self.db.close()

    def _exec(self, sql: str, args: tuple = ()) -> None:
        with self._lock:
            self.db.execute(sql, args)

    def executemany(self, sql: str, rows) -> None:
        with self._lock:
            self.db.executemany(sql, rows)

    def query(self, sql: str, args: tuple = ()) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self.db.execute(sql, args).fetchall()]

    @contextlib.contextmanager
    def transaction(self):
        with self._lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                yield self
            except BaseException:
                self.db.execute("ROLLBACK")
                raise
            self.db.execute("COMMIT")


_OPEN: dict[Path, Store] = {}
_OPEN_LOCK = threading.Lock()


def open_store(data_dir: Path) -> Telemetry:
    """The store of one data directory, opened once per process (a Telemetry, which is a Store)."""
    from .telemetry import Telemetry
    key = Path(data_dir).resolve()
    with _OPEN_LOCK:
        if key not in _OPEN:
            _OPEN[key] = Telemetry(key / DB_NAME)
        return _OPEN[key]
