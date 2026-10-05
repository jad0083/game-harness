"""The pilot's store (docs/design/2026-10-05-data-platform-design.md): one SQLite file, pilot.db, in the
data directory, holding telemetry, learned knowledge, journals, traces (decisions.trace), settings,
model usage, standing orders and run state. WAL mode lets the dashboard read while the pilot writes;
a busy timeout covers the rare moments both write. No other module opens pilot.db."""

from __future__ import annotations

import contextlib
import sqlite3
import threading
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .telemetry import Telemetry

DB_NAME = "pilot.db"
SCHEMA_VERSION = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS campaigns (
    id TEXT PRIMARY KEY, game TEXT NOT NULL, name TEXT NOT NULL, created REAL NOT NULL, title TEXT);
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY, campaign_id TEXT REFERENCES campaigns(id), game TEXT, model TEXT,
    settings TEXT, started REAL, ended REAL, status TEXT);
CREATE TABLE IF NOT EXISTS events (run_id TEXT NOT NULL, t REAL NOT NULL, kind TEXT NOT NULL, data TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS events_run ON events(run_id, t);
CREATE INDEX IF NOT EXISTS events_kind ON events(kind, t);
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


class DataDirError(RuntimeError):
    """The data directory cannot be written; the message names it."""


def _columns(db: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in db.execute(f"PRAGMA table_info({table})")}   # fixed table names only


def _migrate(db: sqlite3.Connection) -> None:
    """Bring any older pilot.db (or a copied telemetry.sqlite, version 0) to SCHEMA_VERSION."""
    db.executescript(SCHEMA)
    if "title" not in _columns(db, "campaigns"):
        db.execute("ALTER TABLE campaigns ADD COLUMN title TEXT")
    cols = _columns(db, "decisions")
    for col in ("model", "model_version", "thinking"):
        if col not in cols:
            db.execute(f"ALTER TABLE decisions ADD COLUMN {col} TEXT")
    db.execute("INSERT INTO meta(key, value) VALUES ('schema_version', ?) "
               "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(SCHEMA_VERSION),))


class Store:
    """One connection per instance, shared by its threads under a lock (as Telemetry always did)."""

    def __init__(self, path: Path):
        path = Path(path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None, timeout=5.0)
            self.db.row_factory = sqlite3.Row
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA synchronous=NORMAL")
            self.db.execute("PRAGMA busy_timeout=5000")
            _migrate(self.db)
        except (OSError, sqlite3.OperationalError) as e:
            raise DataDirError(f"cannot write the data directory {path.parent}: {e}") from e
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
