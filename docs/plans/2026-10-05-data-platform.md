# Data Platform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every write the pilot and dashboard make goes to one data directory, holding the SQLite store `pilot.db`, frames, a generated `learned/` view, and secrets. The code and base corpora become read-only, and git leaves the runtime.

**Architecture:**
- **Store:** a new `src/pilot/store.py` owns `pilot.db`: the schema with its versioned migrations, and the tables for learned knowledge, journals, settings, usage, standing orders and run state. `Telemetry` becomes a subclass of `Store`, so its callers keep working.
- **Same interfaces, new storage:** `EventLog`, `LearnedStore`, `Journal`, `load_prefs`/`save_prefs`, `ModelHealth` usage and the governors' standing orders keep their interfaces and switch storage.
- **Controller:** the Rust `game-controller` gains `--learned <dir>`.
- **Git and migration:** a `pilot export` command replaces the runtime git commits. `pilot data import`/`check` migrates an old install.

**Tech Stack:** Python 3.13 stdlib `sqlite3` (WAL), aiohttp dashboard, pydantic-ai; Rust (clap, toml, image) for the controller; pytest and Playwright; `cargo test`.

**Spec:** `docs/design/2026-10-05-data-platform-design.md` (rulings 1-14).

## Global Constraints

- `PILOT_DATA_DIR`, default `<repo>/runs`. `PILOT_RUNS_DIR` stays as an alias, and `PILOT_DATA_DIR` wins when both are set.
- `PILOT_CORPORA_DIR`, default `<repo>/corpora`.
- `PILOT_CONTROLLER_BIN`, default `<repo>/target/release/game-controller`.
- `PILOT_FRAMES_KEEP`, default 200.
- `PILOT_EXPORT_DIR`, default unset.
- Data directory layout (ruling 2):
  - `pilot.db`;
  - `auth.sqlite` (unchanged);
  - `frames/<run_id>/NNNNN.jpg` and `frames/<run_id>/latest.jpg`;
  - `learned/<game>/`;
  - `secrets/dashboard.key`, `secrets/dashboard.carryover` (0600).
- `pilot.db` settings: WAL, `synchronous=NORMAL`, `busy_timeout` 5000 ms. Forward migrations keyed by `meta.schema_version` run at open. No code outside `store.py` and its `Store` subclasses opens `pilot.db`.
- Nothing writes into the corpora directory at run time (ruling 3).
- No `git`, `scripts/ci-commit.sh` or `PILOT_COMMIT` at run time (ruling 10).
- `events.jsonl` and `status.json` are no longer written (ruling 6); events live in the `events` table.
- Hand-written campaign journals (`games/<game>-<leader>/journal.md`) stay in git and are never touched by import or prune.
- Commits only through `scripts/ci-commit.sh` with conventional commit messages. No AI or assistant attribution anywhere.
- A commit that stages `src/pilot/static/*.html` or `src/pilot/auth.py` needs the Playwright UI tests to have run (`.venv/bin/pytest -m ui tests/ui`).
- Never stage `runs/`, `.env`, `.agent_token*`, `play/`, or the live learned files and journals the running pilot changes in the main checkout.

## Rulings made while planning

- **P1 (spec ruling 4, traces).** Traces are stored in the existing `decisions.trace` column, keyed `(run_id, episode)`, which already holds the same JSON, instead of a new `traces` table. *If wrong:* none; the data and key are the same.
- **P2 (spec ruling 4, live run).** The spec's `live(run_id, port, pid, started, updated)` becomes `run_state(run_id PRIMARY KEY, data TEXT, updated REAL)`, holding what `status.json` held: the whole `RunState.as_dict()`. The dashboard's run list needs the whole state (model, game, decisions, date, status), not just the port, and the live pilot's port is `data.info.port`. *If wrong:* one table wider than the spec's.
- **P3 (naming).** `Settings.runs_dir` remains the attribute that holds the data directory, to avoid touching ~40 references. `PILOT_DATA_DIR` sets it. *If wrong:* a cosmetic rename later.
- **P4 (imported journal lines).** Pilot-log lines in `games/<game>/journal.md` carry no run or campaign id, so the import files them under campaign `<game>/imported-journal`. New lines carry the real campaign. *If wrong:* older lines are not tied to a campaign, as they never were.
- **P5 (prune).** `pilot data import --prune-source` deletes only untracked runtime files under the old data directory:
  - `telemetry.sqlite*`;
  - `<run_id>/` directories;
  - `pilot-settings.json`, `model-usage.json`, `orders/`;
  - the old `dashboard.key`/`dashboard.carryover`.

  It never deletes git-tracked files, so `corpora/*/learned/` and `games/*/journal.md` stay. *If wrong:* stale learned files remain in the repo as the last committed export.

## Review Focus

1. **Two processes write `pilot.db` at once:** the viewer saving prefs while the pilot writes events. Neither may fail with "database is locked". *Test:* Task 1, `test_two_stores_write_concurrently`.
2. **Old installs with damaged files.** A truncated `events.jsonl` line, an unparseable `status.json` or an invalid learned `manifest.toml` are reported by import and skipped, never aborting it. *Test:* Task 7, `test_import_skips_damaged_files_and_reports_them`.
3. **A fresh install with no learned data.** It still generates `learned/<game>/` (an empty overlay), and the controller loads the corpus with it. *Test:* Task 3, `test_fresh_store_generates_an_empty_overlay`.
4. **Import repeated after new runs were recorded in `pilot.db`.** It adds nothing twice and loses nothing new. *Test:* Task 7, `test_import_twice_and_after_new_runs`.
5. **An unwritable data directory.** The pilot stops at start with a message naming the directory. *Test:* Task 1, `test_unwritable_data_dir_fails_at_start_with_its_name`.

---

### Task 1: The store and the paths

**Files:**
- Create: `src/pilot/store.py`
- Modify: `src/pilot/telemetry.py` (the `Telemetry` class becomes a `Store` subclass; `SCHEMA` and migrations move to `store.py`)
- Modify: `src/pilot/config.py` (paths and settings)
- Test: `tests/test_store.py`

**Interfaces:**
- Produces:
  - `store.SCHEMA_VERSION: int`, `store.DB_NAME = "pilot.db"`;
  - `class Store` with `__init__(self, path: Path)`, `path`, `db` (`sqlite3.Connection`), `query(sql, args=()) -> list[dict]`, `_exec(sql, args=())`, `executemany(sql, rows)`, `transaction()` (a context manager), `close()`;
  - `open_store(data_dir: Path) -> Telemetry`, cached per resolved path per process;
  - `Telemetry(Store)`, with every existing method kept;
  - the `Settings` fields `frames_keep: int = 200` and `export_dir: Path | None = None`;
  - the properties `corpus_dir` (from `corpora_dir`), `corpora_dir: Path`, `controller_bin: Path` (from env), `db_path: Path` (`runs_dir / "pilot.db"`), `frames_dir: Path` (`runs_dir / "frames"`), `learned_dir: Path` (`runs_dir / "learned" / game`), `secrets_dir: Path` (`runs_dir / "secrets"`);
  - `Settings.telemetry_db` is removed. Every user of it (`cli.py:95,175,190`, `dashboard.py`, tests) switches to `open_store(s.runs_dir)`.

- [ ] **Step 1: Write the failing tests** — `tests/test_store.py`:

```python
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
    with pytest.raises(RuntimeError):
        with st.transaction():
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
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/pytest tests/test_store.py -q`
Expected: `ModuleNotFoundError: No module named 'pilot.store'`.

- [ ] **Step 3: Write `src/pilot/store.py`**

```python
"""The pilot's store (docs/design/2026-10-05-data-platform-design.md): one SQLite file, pilot.db, in the
data directory, holding telemetry, learned knowledge, journals, traces (decisions.trace), settings,
model usage, standing orders and run state. WAL mode lets the dashboard read while the pilot writes;
a busy timeout covers the rare moments both write. No other module opens pilot.db."""

from __future__ import annotations

import contextlib
import sqlite3
import threading
from pathlib import Path

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


def open_store(data_dir: Path):
    """The store of one data directory, opened once per process (a Telemetry, which is a Store)."""
    from .telemetry import Telemetry
    key = Path(data_dir).resolve()
    with _OPEN_LOCK:
        if key not in _OPEN:
            _OPEN[key] = Telemetry(key / DB_NAME)
        return _OPEN[key]
```

The `test_open_store_is_cached_per_path` cache can leak between tests that use the same `tmp_path`. Add an autouse fixture to `tests/conftest.py` that clears the cache after each test:

```python
@pytest.fixture(autouse=True)
def _fresh_stores():
    """Each test opens its own pilot.db stores (open_store caches one per path per process)."""
    yield
    from pilot import store
    with store._OPEN_LOCK:
        for st in store._OPEN.values():
            st.close()
        store._OPEN.clear()
```

- [ ] **Step 4: Make `Telemetry` a `Store`.** In `src/pilot/telemetry.py`:
  - delete `SCHEMA` and the connection/migration code in `__init__`, `close`, `_exec` and `query`, which now come from `Store`;
  - declare `class Telemetry(Store)` with no `__init__` of its own;
  - delete `rebuild` (ruling 6);
  - update the module docstring: "Telemetry tables in the pilot's store (pilot.db). Outcome scoring joins ...".

  Every other method (`start_run`, `set_campaign`, `record`, `score`, `latest_plan`, `latest_strategy`, `strategy_history`, `campaign_events`, `metrics_rows`, `past_outcomes`) stays unchanged.

  In `src/pilot/cli.py`:
  - remove the `rebuild-telemetry` subcommand (its parser line, the `rebuild` function, the usage line in the module docstring);
  - replace `Telemetry(s.telemetry_db)` with `open_store(s.runs_dir)`. That's `cli.py:95` (`EventLog(..., telemetry=open_store(s.runs_dir))`) and `:190` (`make_app(None, s.runs_dir, open_store(s.runs_dir))`).

- [ ] **Step 5: Paths in `src/pilot/config.py`**
  - **`Settings` fields:**
    - `corpora_dir: Path = REPO / "corpora"` and `controller_path: Path = REPO / "target/release/game-controller"`;
    - `frames_keep: int = 200` and `export_dir: Path | None = None`;
    - remove `commit_learnings` (Task 6 removes its users; for now leave the field and remove it in Task 6).
  - **Properties:**
    - `corpus_dir` returns `self.corpora_dir / self.game`;
    - `controller_bin` returns `self.controller_path`;
    - `db_path` returns `self.runs_dir / "pilot.db"`;
    - `frames_dir` returns `self.runs_dir / "frames"`;
    - `learned_dir` returns `self.runs_dir / "learned" / self.game`;
    - `secrets_dir` returns `self.runs_dir / "secrets"`;
    - delete the `telemetry_db` property.
  - **`from_env`:** replace the `PILOT_RUNS_DIR` block with:

```python
        data_dir = env.get("PILOT_DATA_DIR") or env.get("PILOT_RUNS_DIR")
        if data_dir:
            s.runs_dir = Path(data_dir)
        if env.get("PILOT_CORPORA_DIR"):
            s.corpora_dir = Path(env["PILOT_CORPORA_DIR"])
        if env.get("PILOT_CONTROLLER_BIN"):
            s.controller_path = Path(env["PILOT_CONTROLLER_BIN"])
        s.frames_keep = max(1, int(env.get("PILOT_FRAMES_KEEP", s.frames_keep)))
        if env.get("PILOT_EXPORT_DIR"):
            s.export_dir = Path(env["PILOT_EXPORT_DIR"])
```

  Change the "telemetry" lines in `docs/pilot.md` and README (`runs/telemetry.sqlite`) to `pilot.db` in Task 8, not here.

- [ ] **Step 6: Run the tests.**
  1. `.venv/bin/pytest tests/test_store.py -q`: all pass.
  2. `.venv/bin/pytest -q -m "not ui"`. Tests that build `Telemetry(tmp/"telemetry.sqlite")` keep working, because `Telemetry(path)` still opens any path. Tests that use `Settings.telemetry_db` or `rebuild` must switch to `open_store(...)` or be deleted (the rebuild tests). Change each and list them in the report.
- [ ] **Step 7: Commit**: `git add src/pilot/store.py src/pilot/telemetry.py src/pilot/config.py src/pilot/cli.py tests/` then `scripts/ci-commit.sh "feat(pilot): one store, pilot.db, in a data directory" "<body>"`.

---

### Task 2: Run records in the store (events, run state, traces, frames, the dashboard's reads)

**Files:**
- Modify: `src/pilot/events.py` (`EventLog`)
- Modify: `src/pilot/dashboard.py`:
  - `list_runs` (`:241`), `LiveProxy._find` (`:179`), `run_dir`, `run_events`, `run_trace`, `run_frame` (`:785-825`);
  - `api_health` (`:827`);
  - the live `frame.jpg` (`:954`) and the capture handler (`:1005`).
- Modify: `src/pilot/cli.py` (`:93-120` run creation; `:286` run listing)
- Test: `tests/test_run_records.py`, plus updates in `tests/test_dashboard_*.py`

**Interfaces:**
- Consumes (Task 1): `open_store`, `Store.query/_exec`, `Settings.frames_dir`, `Settings.frames_keep`.
- Produces:
  - `EventLog(runs_dir: Path, run_id: str, model: str, telemetry=None, frames_keep: int = 200)`. `runs_dir` is the data directory. When `telemetry` is None, `EventLog` uses `open_store(runs_dir)`, so a store is always present.
  - `EventLog.dir` is `<data>/frames/<run_id>`.
  - `EventLog.frame(jpeg, keep: bool = False) -> str` returns `"NNNNN.jpg"`. A frame saved with `keep=True` is exempt from retention until `EventLog.release(name)` is called.
  - `EventLog.save_trace(episode, trace) -> str` returns `"decision:<run_id>:<episode>"`; the trace lives in `decisions.trace`.
  - `dashboard.list_runs(store: Telemetry, live_id: str | None = None) -> list[dict]` (same row keys as today).
  - `dashboard.read_events(store, run_id, kinds: set[str]) -> list[dict]` (the newest 5000, oldest first, each `{"t", "kind", **data}`).

- [ ] **Step 1: Write the failing tests** — `tests/test_run_records.py`:

```python
"""Run records in the store (data platform design, rulings 2, 6, 9; plan rulings P1-P2): events and run
state in pilot.db, no events.jsonl or status.json, traces in decisions.trace, frames as files with
retention."""

from __future__ import annotations

import json

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
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/pytest tests/test_run_records.py -q`
Expected: failures. `read_events` doesn't take a store, and `events.jsonl` is still written.

- [ ] **Step 3: Implement `EventLog`** (`src/pilot/events.py`)
  - **Module docstring:** "Run log and live state: every event goes to the store's events table (pilot.db) and to live subscribers; the run's state is kept in run_state; frames are JPEG files under <data>/frames/<run_id>/."
  - **`__init__`:**
    - `self.store = telemetry if telemetry is not None else open_store(runs_dir)`, and `self.telemetry = self.store`; the old `telemetry` attribute name stays, because the governors read `log.telemetry`.
    - `self.dir = runs_dir / "frames" / run_id`, then `self.dir.mkdir(parents=True, exist_ok=True)`.
    - `self.frames_keep = frames_keep`, `self._kept: set[str] = set()`.
    - Remove the `events.jsonl` file handle and `close()`'s file close (`close()` becomes a no-op kept for callers).
  - **`frame(jpeg, keep=False)`:**
    - Write `NNNNN.jpg` and `latest.jpg` into `self.dir`. If `keep`, add the name to `self._kept`.
    - Then prune: list `[0-9]*.jpg` sorted by name, and delete the oldest beyond `self.frames_keep`, skipping names in `self._kept`.
    - Set `state.frame_path = name` and return `name`.
  - **`release(name)`:** remove the name from `self._kept`.
  - **`emit`:**
    - Drop the file write. Keep `recent` and subscribers.
    - Call `self.store.record(self.state.run_id, ev, _trace)`. On an exception, print as today but say "store write failed".
    - Replace the `status.json` write with `self.store._exec("INSERT INTO run_state(run_id, data, updated) VALUES (?,?,?) ON CONFLICT(run_id) DO UPDATE SET data=excluded.data, updated=excluded.updated", (run_id, json.dumps(self.state.as_dict(), default=str), time.time()))`.
  - **`save_trace(episode, trace)`:** don't write a file. Emit the `trace` event exactly as today, with the `_trace=trace` that `Telemetry.record` stores in `decisions.trace`, and `file=f"decision:{run_id}:{episode}"`. Return that string.
  - **Callers of `frame` that pass a needs-attention frame:** `governor.py:1196` (the attention card) passes `keep=True`. The `_needs_attention` close path that clears `info["attention"]` calls `self.log.release(name)`. Find it by searching `info.pop("attention"` and `"attention"` in `governor.py` and `civ6_governor.py`.

- [ ] **Step 4: Implement the dashboard reads** (`src/pilot/dashboard.py`)
  - **`list_runs(store, live_id=None)`:**
    - Rows come from `SELECT r.id, r.model, r.game, r.status, s.data FROM runs r LEFT JOIN run_state s ON s.run_id = r.id ORDER BY r.id DESC`.
    - `st = json.loads(data or "{}")`. Build the same keys as today: `id`, `live`, `model` (`st.get("model") or r.model`), `_status`, `game`, `decisions`, `date`, `status`, `frame`, `backfill`.
    - `frame` is `(store.path.parent / "frames" / id / "latest.jpg").exists()`.
  - **`read_events(store, run_id, kinds)`:** `SELECT t, kind, data FROM events WHERE run_id=?` (plus `AND kind IN (...)` when `kinds`) `ORDER BY t DESC LIMIT 5000`. Reverse the rows and return `{"t", "kind", **json.loads(data)}`.
  - **`run_dir(request)`** becomes `run_id(request)`: it validates `RUN_ID` and that `SELECT 1 FROM runs WHERE id=?` returns a row, or raises 404.
  - **Routes:**
    - `run_events` uses `read_events(tel, rid, kinds)`.
    - `run_trace` returns `decisions.trace` for `(rid, int(n))` as `application/json`, or 404 when it's missing or null.
    - `run_frame` serves `<data>/frames/<rid>/latest.jpg`.
    - `api_health` uses `read_events`.
    - The live `/frame.jpg` serves `log.dir / "latest.jpg"`, unchanged.
  - **`LiveProxy`:** keep its constructor arguments `(runs_dir, keys)`. In `_find`, call `list_runs(open_store(self.runs_dir))` instead of reading directories; the rest of its logic is unchanged.
  - **`make_app`:** wherever it uses `runs_dir / rid / ...` for events or traces, switch to the store. The viewer's `tel` argument is the store; the live pilot uses `log.store`.
  - **`cli.py:95`:** the run's `EventLog(..., telemetry=open_store(s.runs_dir), frames_keep=s.frames_keep)`.
  - **`cli.py:286`:** `list_runs(open_store(s.runs_dir))`. **`cli.py:120`:** the startup line says `store {s.db_path}` instead of the `events.jsonl` path.

- [ ] **Step 5: Run the tests**
  - Run `.venv/bin/pytest tests/test_run_records.py -q`, then the full `.venv/bin/pytest -q -m "not ui"`.
  - Update the tests that read `events.jsonl`, `status.json`, `traces/` or `latest.jpg` under `runs/<id>/` (5+2+1+1 files, found by grep). Have each read the store or `frames/<id>/` instead, keeping its assertions about behaviour.
  - Run `.venv/bin/pytest -q -m ui tests/ui`. The UI fixtures (`tests/ui/uikit.py seed_runs`) build `EventLog`s, so they follow automatically; fix any path they assume.
- [ ] **Step 6: Commit**: `scripts/ci-commit.sh "feat(pilot): run records, traces and run state in the store; frames with retention" "<body>"`. Stage `dashboard.py` (no HTML) and the tests.

---

### Task 3: Learned knowledge and journals in the store; the generated learned directory

**Files:**
- Modify: `src/pilot/learning.py` (`LearnedStore`, `Journal`)
- Create: `src/pilot/learned_files.py` (`render_overlay(store, game) -> dict[str, bytes]`, `write_learned_dir(store, game, out_dir)`, `rules_markdown(store, game) -> str`)
- Modify: the call sites:
  - `src/pilot/controller.py:36-48` (`LearnedStore`, `Journal`, the briefing's learned rules);
  - `src/pilot/governor.py:567,583-587` and `src/pilot/civ6_governor.py:246-250` (stores, journals, prompts);
  - `src/pilot/config.py` (`default_journal` goes away).
- Test: `tests/test_learned_store.py`

**Interfaces:**
- Consumes (Tasks 1-2): `open_store(data_dir)`, `Settings.learned_dir`, `Settings.corpus_dir`, `Store.query/_exec/transaction`.
- Produces:
  - `LearnedStore(store, game: str, corpus_dir: Path, learned_dir: Path, model: str, run_id: str)`. Same methods: `remember_frame`, `screens() -> dict`, `main_screen_names`, `add_screen`, `record_dismissals`, `add_rule`, `add_control`, `add_episode`, `recall`, `repeated`, and the `refuse` attribute.
  - `LearnedStore.rules_markdown() -> str` (what `learned/strategy.md` contained).
  - `Journal(store, game: str, model: str, campaign: Callable[[], str | None])`, with `note(text, game_date="")`.
  - `learned_files.write_learned_dir(store, game, out_dir)`: writes `manifest.toml`, `templates/<name>.png`, `strategy.md`, `controls.md` atomically (into a temp dir, then rename).

- [ ] **Step 1: Write the failing tests** — `tests/test_learned_store.py`:

```python
"""Learned knowledge and journals in the store (data platform design, rulings 4, 7): the same
LearnedStore behaviour, the files the controller reads generated from the store, journals as rows."""

from __future__ import annotations

import io
import tomllib

from PIL import Image

from pilot.learned_files import write_learned_dir
from pilot.learning import Journal, LearnedStore, LearningRejected, ScreenAction
from pilot.store import open_store


def jpeg(color=(10, 20, 30), title: str | None = None) -> bytes:
    img = Image.new("RGB", (1568, 882), color)
    if title:
        for x in range(600, 980):
            for y in range(300, 330):
                img.putpixel((x, y), (250, 250, 250) if (x // 7 + y // 5) % 2 else (5, 5, 5))
    b = io.BytesIO()
    img.save(b, "JPEG", quality=95)
    return b.getvalue()


def make(tmp_path, corpus=None):
    corpus = corpus or tmp_path / "corpora/galciv4"
    corpus.mkdir(parents=True, exist_ok=True)
    (corpus / "manifest.toml").write_text("[screens.gnn_news]\ndescription = 'x'\n")
    st = open_store(tmp_path / "data")
    return st, LearnedStore(st, "galciv4", corpus, tmp_path / "data/learned/galciv4", "google:m", "run1")


def test_rules_and_controls_are_rows_and_render_as_before(tmp_path):
    st, ls = make(tmp_path)
    ls.add_rule("When offered an artifact or 200 credits, take the artifact while rich.", "recurring")
    ls.add_control("Key n puts a warship on Sentry.", "tooltip")
    md = ls.rules_markdown()
    assert md.startswith("# Learned strategy rules") and "take the artifact" in md and "_why:_ recurring" in md
    out = tmp_path / "data/learned/galciv4"
    assert "take the artifact" in (out / "strategy.md").read_text() and "Sentry" in (out / "controls.md").read_text()
    with __import__("pytest").raises(LearningRejected):
        ls.add_rule("short", "x")


def test_a_learned_screen_is_a_row_with_its_png_and_the_overlay_follows(tmp_path):
    st, ls = make(tmp_path)
    ls.remember_frame(jpeg((10, 20, 30)))
    ls.add_screen("colony_prompt", jpeg(title="x"), (576, 290, 992, 330), ScreenAction(key="c"), "d", "e")
    row = st.query("SELECT name, auto_dismiss, length(png) AS n FROM learned_screens WHERE game='galciv4'")[0]
    assert row["name"] == "colony_prompt" and row["auto_dismiss"] == 1 and row["n"] > 100
    out = tmp_path / "data/learned/galciv4"
    man = tomllib.loads((out / "manifest.toml").read_text())
    assert man["screens"]["colony_prompt"]["template"] == "templates/colony_prompt.png"
    assert man["screens"]["colony_prompt"]["dismiss_key"] == "c" and (out / "templates/colony_prompt.png").exists()
    for _ in range(3):
        ls.record_dismissals(["colony_prompt"], advanced=False)
    man = tomllib.loads((out / "manifest.toml").read_text())
    assert man["screens"]["colony_prompt"]["auto_dismiss"] is False and "disabled_reason" in man["screens"]["colony_prompt"]


def test_episodes_recall_and_the_corpora_stay_untouched(tmp_path):
    corpus = tmp_path / "corpora/galciv4"
    st, ls = make(tmp_path, corpus)
    ls.add_episode("Event: Space Creature Migration", "Protected the creatures", "resolved", "Jul 2333")
    ls.add_episode("Event: Space Creature Migration", "Protected the creatures", "resolved", "Jul 2334")
    assert ls.recall("space creature")[0]["decision"] == "Protected the creatures"
    assert ls.repeated("Event: Space Creature Migration") == 2
    assert not (corpus / "learned").exists(), "nothing is written into the corpora (ruling 3)"


def test_fresh_store_generates_an_empty_overlay(tmp_path):
    st = open_store(tmp_path / "data")
    write_learned_dir(st, "civ6", tmp_path / "data/learned/civ6")
    man = tomllib.loads((tmp_path / "data/learned/civ6/manifest.toml").read_text())
    assert man.get("screens", {}) == {}


def test_the_journal_is_rows_per_campaign(tmp_path):
    st = open_store(tmp_path / "data")
    j = Journal(st, "civ6", "google:m", campaign=lambda: "civ6/alexander_1")
    j.note("Settled Pella", "T5")
    rows = st.query("SELECT campaign_id, game, date, text FROM journal")
    assert rows == [{"campaign_id": "civ6/alexander_1", "game": "civ6", "date": "T5", "text": "Settled Pella"}]
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/pytest tests/test_learned_store.py -q`
Expected: `ImportError` for `pilot.learned_files` / a `TypeError` from the new `LearnedStore` signature.

- [ ] **Step 3: Implement `src/pilot/learned_files.py`.** It turns the store's rows into today's file formats, so the controller and `pilot export` read the same files:

```python
"""The learned files generated from the store (data platform design, ruling 7): the overlay manifest,
its templates and the notes, in the formats the Rust controller and the old learned/ folder used."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

NOTE_FILES = {"rule": ("strategy.md", "Learned strategy rules"),
              "control": ("controls.md", "Learned controls (verified in play)")}


def _toml_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def notes_markdown(store, game: str, kind: str) -> str:
    file, title = NOTE_FILES[kind]
    out = [f"# {title}\n\nWritten by the pilot app during play; promote proven items into the main corpus.\n"]
    for r in store.query("SELECT text, why, model, t FROM learned_notes WHERE game=? AND kind=? ORDER BY rowid",
                         (game, kind)):
        out.append(f"\n- {r['text'].strip()}  \n  _why:_ {r['why'].strip()} _({r['model']}, {(r['t'] or '')[:10]})_\n")
    return "".join(out)


def manifest_toml(store, game: str) -> str:
    out = ["# Known screens learned during play (pilot app). Main manifest wins on name clashes.\n"]
    for r in store.query("SELECT * FROM learned_screens WHERE game=? ORDER BY rowid", (game,)):
        action = json.loads(r["action"] or "{}")
        lines = [f"\n[screens.{r['name']}]", f"description = {_toml_str(r['description'] or '')}",
                 f"template = {_toml_str('templates/' + r['name'] + '.png')}",
                 f"template_roi = {r['roi']}", f"template_threshold = {r['threshold']}",
                 f"auto_dismiss = {'true' if r['auto_dismiss'] else 'false'}"]
        if r["disabled_reason"]:
            lines.append(f"disabled_reason = {_toml_str(r['disabled_reason'])}")
        if action.get("click"):
            lines.append(f"dismiss_click = [{action['click'][0]}, {action['click'][1]}]")
        else:
            lines.append(f"dismiss_key = {_toml_str(action.get('key') or '')}")
        lines += [f"learned_by = {_toml_str(r['learned_by'] or '')}", f"learned_run = {_toml_str(r['run_id'] or '')}"]
        out.append("\n".join(lines) + "\n")
    return "".join(out)


def render(store, game: str) -> dict[str, bytes]:
    """Every generated file of one game, by path relative to its learned directory."""
    files = {"manifest.toml": manifest_toml(store, game).encode(),
             "strategy.md": notes_markdown(store, game, "rule").encode(),
             "controls.md": notes_markdown(store, game, "control").encode()}
    for r in store.query("SELECT name, png FROM learned_screens WHERE game=? AND png IS NOT NULL", (game,)):
        files[f"templates/{r['name']}.png"] = bytes(r["png"])
    return files


def write_learned_dir(store, game: str, out_dir: Path) -> None:
    """Write the generated files into `out_dir`, replacing it whole: a reader never sees a half-written one."""
    out_dir = Path(out_dir)
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=f".{out_dir.name}-", dir=out_dir.parent))
    for rel, data in render(store, game).items():
        (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp / rel).write_bytes(data)
    old = out_dir.with_name(f".{out_dir.name}-old")
    if out_dir.exists():
        if old.exists():
            shutil.rmtree(old)
        os.rename(out_dir, old)
    os.rename(tmp, out_dir)
    if old.exists():
        shutil.rmtree(old, ignore_errors=True)
```

- [ ] **Step 4: Implement `LearnedStore` and `Journal` on the store** (`src/pilot/learning.py`)
  - **Module docstring:** describe the store tables (`learned_notes`, `learned_screens`, `episodes`, `ledger`) and the generated `<data>/learned/<game>/`. Keep the paragraph on activation and disabling.
  - **`__init__(store, game, corpus_dir, learned_dir, model, run_id)`:** don't create any directory. Store the arguments, then call `write_learned_dir(store, game, learned_dir)` so the controller always has the current overlay (Review Focus 3).
  - **`_ledger(kind, name, **data)`:** `INSERT INTO ledger(game, t, kind, data)` with the JSON of `{name, model, run, **data}`.
  - **`screens()`:** `{name: {...}}` from `learned_screens`, with the same keys the TOML had, so `record_dismissals` and `add_screen`'s name check keep working.
  - **`main_screen_names()`:** unchanged; it reads the corpus manifest.
  - **`add_screen`:** the same validation and distinctness check. Encode `tpl` to PNG bytes, then `INSERT INTO learned_screens(game, name, description, roi, threshold, auto_dismiss, action, png, learned_by, run_id, t, disabled_reason)`:
    - `roi` is the text `"[nx, ny, nw, nh]"`, as the TOML wrote it;
    - `action` is `json.dumps({"click": [nx, ny]})` or `{"key": key}`;
    - `auto_dismiss` is 1;
    - `disabled_reason` is NULL.

    Then `write_learned_dir(...)`, then the ledger row. The return message is unchanged.
  - **`_disable(name, reason)`:** `UPDATE learned_screens SET auto_dismiss=0, disabled_reason=? WHERE game=? AND name=?`, then `write_learned_dir`, then the ledger.
  - **`add_rule`/`add_control`:** same validation. `INSERT OR IGNORE INTO learned_notes(game, kind, text, why, model, run_id, t)` with `t = time.strftime("%Y-%m-%dT%H:%M:%S")`, then `write_learned_dir`. The return text is "rule recorded" / "control recorded".
  - **`add_episode`:** `INSERT OR IGNORE INTO episodes(...)`.
  - **`recall(query, limit)`:** the same scoring over `SELECT situation, decision, outcome, date, model, run_id AS run, t FROM episodes WHERE game=? ORDER BY rowid`.
  - **`rules_markdown()`:** `learned_files.notes_markdown(self.store, self.game, "rule")`.
  - **`Journal(store, game, model, campaign)`:**
    - `note(text, game_date="")` does `INSERT OR IGNORE INTO journal(campaign_id, game, t, date, text) VALUES (campaign() or f"{game}/no-campaign", game, time.time(), game_date, text.strip())`.
    - `config.default_journal` and `Settings.journal` are removed, along with `PILOT_JOURNAL` (`cli.py:565-568`, `config.py:25-27,91,192`). Their users are the `Journal(...)` constructions below.
- [ ] **Step 5: Call sites**
  - **`controller.py:42-48`:**
    - `self.store = LearnedStore(log.store, settings.game, settings.corpus_dir, settings.learned_dir, settings.model, log.state.run_id)`;
    - `self.journal = Journal(log.store, settings.game, settings.model, campaign=lambda: self.log.campaign_id)`;
    - the briefing appends `"\n\n## Rules learned in play\n" + self.store.rules_markdown()` when the store has any rule.
  - **`governor.py:567` and `:583-587`, `civ6_governor.py:246-250`:** the same three changes. Search each file for `Journal(` and `LearnedStore(`.
  - **`learning.py`:** `game.reload()` calls are unchanged. `write_learned_dir` already ran inside `add_screen`, so the controller's reload sees the new overlay.
- [ ] **Step 6: Run the tests**
  - Run `.venv/bin/pytest tests/test_learned_store.py -q`, then the full non-UI suite.
  - Update the 6 test files that read `learned/strategy.md` and the 9 that use `journal.md` to read the store (`rules_markdown()`, the `journal` table) instead. `tests/test_pilot.py`'s learn-screen tests (`:87-130`) construct `LearnedStore(corpus, "m", "r")`; change them to the new signature with an `open_store(tmp_path/"data")`.
- [ ] **Step 7: Commit**: `scripts/ci-commit.sh "feat(pilot): learned knowledge and journals in the store" "<body>"`.

---

### Task 4: The controller reads a learned directory (`--learned`)

**Files:**
- Modify: `crates/game-controller/src/corpus.rs` (`load_base` `:226-235`, `merge_learned` `:240-254`, learned notes `:475-479`)
- Modify: `crates/game-controller/src/main.rs` (`:20-30`, the global `Cli` struct; `:300` setup)
- Modify: `src/pilot/game.py:68` and `src/pilot/civ6.py:64` (pass `--learned`)
- Test: Rust unit tests in `corpus.rs`; `tests/test_controller_args.py`

**Interfaces:**
- Consumes (Task 3): `Settings.learned_dir` (`<data>/learned/<game>`), whose `manifest.toml` lists templates as `templates/<name>.png` relative to that directory.
- Produces:
  - **Rust:** `pub fn set_learned_dir(dir: PathBuf)` and `fn learned_dir(corpus_dir: &Path) -> PathBuf`. The second returns the set directory, or `corpus_dir.join("learned")`.
  - **Rust CLI:** the global option `--learned <DIR>`.
  - **Python:** `McpGame`/`ControllerCiv6` receive `learned: Path` and put `--learned <dir>` before the subcommand.

- [ ] **Step 1: Write the failing Rust tests** (in `corpus.rs`'s `#[cfg(test)] mod tests`):

```rust
    #[test]
    fn an_explicit_learned_dir_supplies_screens_and_absolute_templates() {
        let tmp = tempfile::tempdir().unwrap();
        let corpus = tmp.path().join("corpus");
        let learned = tmp.path().join("data/learned/galciv4");
        std::fs::create_dir_all(corpus.join("learned")).unwrap();
        std::fs::create_dir_all(learned.join("templates")).unwrap();
        std::fs::write(corpus.join("manifest.toml"), "[screens.main_one]\ndescription = \"m\"\n").unwrap();
        std::fs::write(corpus.join("learned/manifest.toml"),
            "[screens.stale]\ndescription = \"old\"\ntemplate = \"learned/templates/stale.png\"\n").unwrap();
        std::fs::write(learned.join("manifest.toml"),
            "[screens.fresh]\ndescription = \"new\"\ntemplate = \"templates/fresh.png\"\n").unwrap();
        std::fs::write(learned.join("strategy.md"), "# Learned strategy rules\n\n- take the artifact\n").unwrap();
        let m = GameManifest::load_with_learned(&corpus.join("manifest.toml"), None, Some(&learned)).unwrap();
        assert!(m.screens.contains_key("main_one") && m.screens.contains_key("fresh"));
        assert!(!m.screens.contains_key("stale"), "the corpus learned folder is ignored when a learned dir is given");
        let tpl = m.screens["fresh"].template.clone().unwrap();
        assert_eq!(PathBuf::from(&tpl), learned.join("templates/fresh.png"));
        let c = GameCorpus::load_from_dir_with_learned(&corpus, Some(&learned)).unwrap();
        assert!(c.search("artifact", 5).iter().any(|h| h.id.starts_with("learned:")));
    }

    #[test]
    fn without_a_learned_dir_the_corpus_folder_is_used_as_before() {
        let tmp = tempfile::tempdir().unwrap();
        let corpus = tmp.path().join("corpus");
        std::fs::create_dir_all(corpus.join("learned")).unwrap();
        std::fs::write(corpus.join("manifest.toml"), "").unwrap();
        std::fs::write(corpus.join("learned/manifest.toml"),
            "[screens.stale]\ndescription = \"old\"\ntemplate = \"learned/templates/stale.png\"\n").unwrap();
        let m = GameManifest::load_with_learned(&corpus.join("manifest.toml"), None, None).unwrap();
        assert_eq!(m.screens["stale"].template.as_deref(), Some("learned/templates/stale.png"));
    }
```

Adjust these to the crate's real types. If `ScreenDef.template` is an `Option<String>`, compare strings. If `GameCorpus::search` has a different name or signature, use the one `corpus.rs`'s existing search tests use. Check whether `tempfile` is a dev-dependency in `crates/game-controller/Cargo.toml`, and add it if it's missing.

- [ ] **Step 2: Run them to see them fail**

Run: `cargo test -p game-controller learned_dir -- --nocapture`
Expected: a compile error (`load_with_learned` not found).

- [ ] **Step 3: Implement in `corpus.rs`**
  - Add `static LEARNED: OnceLock<PathBuf>` with `pub fn set_learned_dir(dir: PathBuf) { let _ = LEARNED.set(dir); }`.
  - Add `fn learned_dir(corpus_dir: &Path) -> (PathBuf, bool)`. It returns `(dir, explicit)`: the set directory with `true`, or `corpus_dir.join(LEARNED_DIR)` with `false`.
  - Add `pub fn load_with_learned(path, resolution, learned: Option<&Path>)`, which `load_for_resolution` and `load_base` route through. `load_from_file` keeps its signature and passes `LEARNED.get().map(PathBuf::as_path)`.
  - `merge_learned(&mut self, dir: &Path, explicit: bool)` reads `dir.join("manifest.toml")`. When `explicit`, each merged screen's `template` becomes `dir.join(rel).to_string_lossy()`, an absolute path; `base.join(abs)` in `autopilot.rs:74` then yields the absolute path unchanged.
  - The learned notes loop (`:475`) iterates `sorted_files(&learned_dir(dir).0, "md")`.
  - Add `GameCorpus::load_from_dir_with_learned(dir, learned: Option<&Path>)`; `load_from_dir` calls it with `LEARNED.get()`.

  **In `main.rs`:**
  - Add `#[arg(long, global = true)] learned: Option<PathBuf>` to the `Cli` struct beside `corpus`.
  - At the top of `main`, after parsing, add `if let Some(d) = &cli.learned { corpus::set_learned_dir(d.clone()); }`.

- [ ] **Step 4: Python passes `--learned`**
  - `game.py:68`: `self.cmd = [str(controller), "--corpus", str(corpus), "--learned", str(learned), "mcp"]`, with `learned` a new constructor parameter after `corpus`.
  - `civ6.py:64`: `self.base = [str(controller), "--corpus", str(corpus), "--learned", str(learned)]`.
  - `cli.py:98,100`: pass `s.learned_dir`.
  - `tests/test_controller_args.py`: assert both command lists contain `--learned <dir>` before `mcp` / the `civ6` subcommand. Build them with a fake path and don't start a process.
- [ ] **Step 5: Run the tests.** Run `cargo test -p game-controller` (all pass) and `.venv/bin/pytest -q -m "not ui"`.
- [ ] **Step 6: Commit**: `git add crates/game-controller src/pilot/game.py src/pilot/civ6.py src/pilot/cli.py tests/test_controller_args.py`, then `scripts/ci-commit.sh "feat(controller): --learned reads the learned overlay from a data directory" "<body>"`. CI runs the Rust stages.

---

### Task 5: Settings, model usage and standing orders in the store

**Files:**
- Modify: `src/pilot/models.py` (`load_prefs`/`save_prefs` `:120-257`)
- Modify: `src/pilot/modelguard.py` (`GuardConfig.usage_file`, then `usage_store`; `ModelHealth._load/_save` `:401-425`)
- Modify: `src/pilot/governor.py` (`_orders_file`, `_save_orders`, `_load_campaign_state` `:1004-1011,1403-1409`)
- Modify: `scripts/deploy-pilot.sh:48` (reads the game from the store)
- Test: `tests/test_store_settings.py`; update `tests/test_modelguard_health.py` (the usage-file tests)

**Interfaces:**
- Consumes (Task 1): `open_store`, `Store.query/_exec/transaction`.
- Produces:
  - `load_prefs(runs_dir) -> dict` and `save_prefs(runs_dir, ...) -> dict` keep their signatures and read or write the `settings` row `key='prefs'`.
  - `GuardConfig.usage_store` (a `Store` or None) replaces `usage_file`. `GuardConfig.from_settings(s)` sets `usage_store=open_store(s.runs_dir)`. The governors' and pilot's kill-switch code uses `replace(guard, usage_store=None)` where it used `usage_file=None`.
  - `python -m pilot prefs --get <key>` prints one prefs value, for the scripts.

- [ ] **Step 1: Write the failing tests** — `tests/test_store_settings.py`:

```python
"""Settings, model usage and standing orders in the store (data platform design, ruling 4)."""

from __future__ import annotations

import time

from pilot import modelguard as G
from pilot.models import load_prefs, save_prefs
from pilot.store import open_store


def test_prefs_round_trip_through_the_settings_row(tmp_path):
    save_prefs(tmp_path, models=[{"model": "google:gemini-pro-latest", "thinking": "high"}], rotate=False, game="civ6")
    assert load_prefs(tmp_path)["game"] == "civ6" and load_prefs(tmp_path)["models"][0]["model"] == "google:gemini-pro-latest"
    assert not (tmp_path / "pilot-settings.json").exists()
    row = open_store(tmp_path).query("SELECT key FROM settings")
    assert row == [{"key": "prefs"}]


def test_model_usage_counts_live_in_the_store(tmp_path):
    st = open_store(tmp_path)
    h = G.ModelHealth(G.GuardConfig(usage_store=st))
    for _ in range(3):
        h.count("google:gemini-pro-latest")
    again = G.ModelHealth(G.GuardConfig(usage_store=st))
    assert again.today("google:gemini-pro-latest") == 3
    rows = st.query("SELECT model, count FROM model_usage")
    assert rows == [{"model": "google:gemini-pro-latest", "count": 3}]
    assert not (tmp_path / "model-usage.json").exists()


def test_usage_older_than_seven_days_is_dropped(tmp_path):
    st = open_store(tmp_path)
    st._exec("INSERT INTO model_usage(day, model, count) VALUES ('2020-01-01', 'm', 5)")
    G.ModelHealth(G.GuardConfig(usage_store=st), clock=time.time).count("m")
    assert st.query("SELECT count(*) AS n FROM model_usage WHERE day='2020-01-01'")[0]["n"] == 0
```

Add a governor test to `tests/test_governor.py` next to the standing-orders tests (search `order_add`). `order_add("hold the line")` stores a `standing_orders` row for the run's campaign, and a new governor for the same campaign loads it. Assert that no `orders/` folder appears.

- [ ] **Step 2: Run them to see them fail.** Run: `.venv/bin/pytest tests/test_store_settings.py -q`.
- [ ] **Step 3: Implement**
  - **`models.py`:**
    - `load_prefs(runs_dir)` reads `json.loads(open_store(runs_dir).query("SELECT value FROM settings WHERE key='prefs'")[0]["value"])`, or `{}` when there is no row. The validation that follows is unchanged.
    - `save_prefs` ends with an upsert: `INSERT INTO settings(key, value, changed_by, t) VALUES ('prefs', ?, ?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, changed_by=excluded.changed_by, t=excluded.t`. It writes no file.
  - **`modelguard.py`:**
    - Rename the `GuardConfig.usage_file` field to `usage_store`.
    - `from_settings` passes `open_store(s.runs_dir)` (import inside the method).
    - `_load` does `SELECT day, model, count FROM model_usage` into `self._days`.
    - `_save` replaces today's rows in one transaction (delete the day's rows, insert the counts) and deletes days older than `USAGE_DAYS`. It keeps the existing one-time note on failure, now saying "model usage not saved (...)".
    - Update the docstrings and the comment at `:220`.
  - **`governor.py`:**
    - Remove `_orders_file`.
    - `_save_orders` does `DELETE FROM standing_orders WHERE campaign_id=?`, then inserts `(cid, i, text)`, both inside `self.log.store.transaction()`, then publishes the event as today.
    - `_load_campaign_state` uses `SELECT text FROM standing_orders WHERE campaign_id=? ORDER BY position`.
  - **`cli.py`:** add a `prefs` subcommand with `--get KEY` that prints `load_prefs(s.runs_dir).get(KEY, "")`.
  - **`scripts/deploy-pilot.sh:48`:** replace the JSON read of `runs/pilot-settings.json` with `game=$(.venv/bin/python -m pilot prefs --get game)`.
  - **`tests/test_modelguard_health.py`:** the usage-file tests (`test_daily_counts_persist_roll_over_and_budget`, `test_an_unreadable_usage_file_starts_at_zero_with_one_note`, `test_an_unwritable_usage_file_keeps_counting_with_one_note`) use `usage_store=open_store(tmp_path)`.
    - The "unreadable file" case becomes "a store whose `model_usage` table is missing": drop the table, then expect one note and counting from 0.
    - The "unwritable" case closes the store's connection; expect one note, with counting continuing in memory.
- [ ] **Step 4: Run the tests.** Run `.venv/bin/pytest tests/test_store_settings.py tests/test_modelguard_health.py tests/test_governor.py -q`, then the full non-UI suite.
- [ ] **Step 5: Commit**: `scripts/ci-commit.sh "feat(pilot): settings, model usage and standing orders in the store" "<body>"`.

---

### Task 6: No git at run time; `pilot export`; read-only corpora

**Files:**
- Modify: `src/pilot/controller.py` (remove `_commit`, `_learned_since_commit`, `_commit_lock` and their calls `:178,219,242-262`)
- Modify: `src/pilot/config.py` (remove `commit_learnings`, `PILOT_COMMIT`)
- Modify: `src/pilot/cli.py` (remove `--no-commit`; add `export`; export at run end when `export_dir` is set)
- Create: `src/pilot/export.py`
- Test: `tests/test_export.py`, `tests/test_readonly_corpora.py`

**Interfaces:**
- Consumes (Tasks 1-3): `open_store`, `learned_files.render`, the `journal` table.
- Produces:
  - `export.export(store, out_dir: Path, game: str | None = None, campaign: str | None = None) -> list[Path]`, returning the paths written;
  - the CLI `python -m pilot export --to DIR [--game G] [--campaign ID]`;
  - at run end, `if s.export_dir: export(store, s.export_dir, game=s.game)`.

- [ ] **Step 1: Write the failing tests**

`tests/test_export.py`:

```python
"""pilot export (data platform design, ruling 10): learned files and journals written to a directory."""

from __future__ import annotations

from pilot.export import export
from pilot.learning import Journal, LearnedStore
from pilot.store import open_store


def test_export_writes_learned_files_and_journals(tmp_path):
    corpus = tmp_path / "corpora/civ6"
    corpus.mkdir(parents=True)
    (corpus / "manifest.toml").write_text("")
    st = open_store(tmp_path / "data")
    LearnedStore(st, "civ6", corpus, tmp_path / "data/learned/civ6", "m", "r").add_rule(
        "When a city is threatened, buy a defender at once.", "T45 loss")
    Journal(st, "civ6", "m", campaign=lambda: "civ6/alexander_1").note("Settled Pella", "T5")
    written = export(st, tmp_path / "out")
    assert (tmp_path / "out/civ6/learned/strategy.md").read_text().count("buy a defender") == 1
    assert (tmp_path / "out/civ6/learned/manifest.toml").exists()
    j = (tmp_path / "out/journals/civ6__alexander_1.md").read_text()
    assert "**T5**: Settled Pella" in j and j.startswith("# Journal: civ6/alexander_1")
    assert all(p.is_file() for p in written)
```

`tests/test_readonly_corpora.py`. Copy `corpora/civ6` (the files Civ VI's governor reads: `pilot.md`, `strategy.md`, `pillars.toml`, `manifest.toml`, `dashboard.toml`, `data/`, `popups.toml`, `lua/`) into `tmp_path/corpora/civ6`, then `chmod -R a-w` it. Run one `Civ6Governor` decision with the fakes `tests/test_civ6_governor.py` uses (reuse its `setup` fixture pattern, with `Settings(corpora_dir=tmp_path/"corpora", runs_dir=tmp_path/"data", ...)`). Assert:
- the run completes;
- no file under `tmp_path/corpora` changed (compare an `os.walk` listing with mtimes before and after);
- `tmp_path/data/learned/civ6/manifest.toml` exists.

Restore the write bits in a `finally`.

- [ ] **Step 2: Run them to see them fail.** Run: `.venv/bin/pytest tests/test_export.py tests/test_readonly_corpora.py -q`.
- [ ] **Step 3: Implement `src/pilot/export.py`**:

```python
"""pilot export (data platform design, ruling 10): the store's learned files and pilot journals as files,
for a repo or a person. Committing them is outside the pilot."""

from __future__ import annotations

import re
from pathlib import Path

from .learned_files import render


def _safe(campaign: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", campaign.replace("/", "__"))


def export(store, out_dir: Path, game: str | None = None, campaign: str | None = None) -> list[Path]:
    out_dir = Path(out_dir)
    written: list[Path] = []
    games = [game] if game else sorted({r["game"] for r in store.query(
        "SELECT game FROM learned_notes UNION SELECT game FROM learned_screens UNION SELECT game FROM journal")})
    for g in games:
        for rel, data in render(store, g).items():
            p = out_dir / g / "learned" / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
            written.append(p)
    where, args = ("WHERE campaign_id=?", (campaign,)) if campaign else (
        ("WHERE game=?", (game,)) if game else ("", ()))
    by: dict[str, list[dict]] = {}
    for r in store.query(f"SELECT campaign_id, date, text FROM journal {where} ORDER BY t", args):
        by.setdefault(r["campaign_id"], []).append(r)
    for cid, rows in by.items():
        p = out_dir / "journals" / f"{_safe(cid)}.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        lines = [f"# Journal: {cid}\n\nEntries written by the pilot app.\n"]
        lines += [f"- {'**' + r['date'] + '**: ' if r['date'] else ''}{r['text']}" for r in rows]
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        written.append(p)
    return written
```

  - **`cli.py`:** add `sub.add_parser("export")` with `--to` (required), `--game` and `--campaign`. It calls `export(open_store(s.runs_dir), Path(a.to), a.game, a.campaign)` and prints the count.
  - **At the end of a run:** in the run function, where `run_end` is emitted for each game path, call `export(log.store, s.export_dir, game=s.game)` when `s.export_dir`. Wrap it in try/except, and on an exception emit `briefing_error` with `f"export failed: {e}"`, so a failed export never fails the run.
  - **`controller.py`:** remove `_commit` and everything listed in Files, plus the `subprocess` import if it's unused.
  - **`config.py`/`cli.py`:** remove `commit_learnings`, `PILOT_COMMIT` and `--no-commit`.
- [ ] **Step 4: Run the tests.** Run `.venv/bin/pytest tests/test_export.py tests/test_readonly_corpora.py -q`, then the full non-UI suite. Update the tests that set `commit_learnings=False` by deleting that argument.
- [ ] **Step 5: Commit**: `scripts/ci-commit.sh "feat(pilot): export replaces runtime git; the corpora can be read-only" "<body>"`.

---

### Task 7: `pilot data import` and `pilot data check`; secrets in `secrets/`

**Files:**
- Create: `src/pilot/dataimport.py`
- Modify: `src/pilot/cli.py` (the `data` subcommand: `import --from ROOT [--prune-source]`, `check --from ROOT`)
- Modify: `src/pilot/auth.py` (`dashboard_key` `:355`, `carry_over_record`/`write_carry_over` `:375-390`, `KeySource` `:393`): the key and carry-over files live in `<data>/secrets/`. Reading falls back to the old `<data>/dashboard.key` when `secrets/` has none.
- Test: `tests/test_dataimport.py`; update the `dashboard.key` tests (8 files) for the `secrets/` location

**Interfaces:**
- Consumes (Tasks 1-5): every table; `learned_files.write_learned_dir`.
- Produces:
  - `dataimport.import_install(root: Path, store, data_dir: Path) -> Report` and `dataimport.check(root: Path, store, data_dir: Path) -> list[str]`, whose return value lists the differences (empty when the copy is complete);
  - `Report` is a dataclass with `added: dict[str, int]`, `skipped: list[str]` (damaged files and lines, with the reason) and `frames: int`;
  - `dataimport.prune_source(root: Path) -> list[Path]` (plan ruling P5).

- [ ] **Step 1: Write the failing tests** — `tests/test_dataimport.py`:
  - **A fixture `old_install(tmp_path)`.** It writes today's layout under `tmp_path/repo`:
    - `runs/telemetry.sqlite`, created with the old schema by `Telemetry(path)` before Task 1; build it with plain `sqlite3` and the old `CREATE TABLE` statements copied from `telemetry.py` at commit `bf313b0` (`git show bf313b0:src/pilot/telemetry.py`). Insert one campaign, one run, 3 events and one decision with `trace` NULL.
    - `runs/20261001-100000/events.jsonl` (the same 3 events plus one only in the file, plus one truncated line).
    - `runs/20261001-100000/status.json` (a valid one).
    - `runs/20261001-100000/traces/0001.json`.
    - `runs/20261001-100000/frames/00001.jpg` and `latest.jpg`.
    - `runs/pilot-settings.json`, `runs/model-usage.json`, `runs/orders/civ6_x.json`, `runs/dashboard.key`.
    - `corpora/civ6/learned/{strategy.md,controls.md,manifest.toml,templates/a.png,episodes.jsonl,ledger.jsonl}`, using today's formats as `learning.py` at `bf313b0` wrote them.
    - `games/civ6/journal.md` with a `## Pilot log` section of 2 lines.
  - **The tests:**
    - `test_import_copies_everything`: after `import_install`, every count matches. The decision's trace is filled from `traces/0001.json`, the file-only event is present, `secrets/dashboard.key` exists with mode 0600, `learned/civ6/manifest.toml` is regenerated, and the 2 journal lines are under `civ6/imported-journal` (plan ruling P4). The source files are unchanged (compare their bytes).
    - `test_import_twice_and_after_new_runs`: import, add a new run through `EventLog(data_dir, ...)`, import again. Table counts don't change from the second import, and the new run's events are still there.
    - `test_import_skips_damaged_files_and_reports_them`: corrupt `status.json`, add a truncated JSONL line and an invalid learned `manifest.toml`. The import completes, and `report.skipped` names each one with its reason.
    - `test_check_reports_missing_items`: after the import, delete one decision's trace, one frame and one learned screen row. `check` lists all three.
    - `test_prune_removes_only_untracked_runtime_files`: `git init` the fixture repo and commit `corpora/` and `games/`. After `prune_source`, `runs/telemetry.sqlite`, `runs/20261001-100000/`, `pilot-settings.json`, `model-usage.json`, `orders/` and the old key are gone; `corpora/civ6/learned/*` and `games/civ6/journal.md` remain.
- [ ] **Step 2: Run them to see them fail.** Run: `.venv/bin/pytest tests/test_dataimport.py -q`.
- [ ] **Step 3: Implement `src/pilot/dataimport.py`.** Each source is handled by its own small function, which adds counts to the report. A damaged item is recorded in `skipped` and the import continues (Review Focus 2).
  - **`_telemetry(root, store)`:** if `root/runs/telemetry.sqlite` exists:
    1. `ATTACH DATABASE ? AS old`;
    2. `INSERT OR IGNORE` into `campaigns`, `runs`, `decisions` and `metrics` from `old.*`, naming the columns explicitly. Old databases may lack `title`/`model`/`model_version`/`thinking`, so read `PRAGMA old.table_info` first and select NULL for any missing column;
    3. `plans` and `strategies` inserted where no row has the same `(run_id, t)`;
    4. events inserted where no row has the same `(run_id, t, kind)`;
    5. `DETACH`.
  - **`_runs(root, store, data_dir)`:** for each `root/runs/<id>/`:
    - each `events.jsonl` line not already in `events` by `(run_id, t, kind)` goes through `Telemetry.record(id, ev, trace)`, with the trace file contents when it's a `trace` event;
    - each `traces/NNNN.json` fills `decisions.trace` where it is NULL;
    - `status.json` goes into `run_state` (`INSERT OR IGNORE`);
    - `frames/*.jpg` and `latest.jpg` are copied to `data_dir/frames/<id>/` when that file doesn't exist there.
  - **`_learned(root, store, data_dir)`:** for each `root/corpora/<game>/learned/`:
    - `strategy.md`/`controls.md` bullets are parsed with `re.findall(r"^- (.+?)  \n  _why:_ (.+?) _\((.+?), (\d{4}-\d{2}-\d{2})\)_$", text, re.M)` into `learned_notes` (`INSERT OR IGNORE`);
    - `manifest.toml` screens (via `tomllib`) and their PNG go into `learned_screens`, with `roi` as the TOML's list text and `action` from `dismiss_click`/`dismiss_key`;
    - `episodes.jsonl` and `ledger.jsonl` rows are inserted;
    - then `write_learned_dir(store, game, data_dir/"learned"/game)`.
  - **`_journals(root, store)`:** each `root/games/<g>/journal.md`, where `<g>` is one of `stellaris`, `civ6` or `terran-2329` (the pilot's default journals; the hand-written `games/<game>-<leader>/` journals are documentation and not imported). Its `## Pilot log` section lines `- **<date>**: <text>` or `- <text>` go into `journal`, with `campaign_id=f"{game}/imported-journal"` (plan ruling P4) and `t` = the line's index, to keep the order.
  - **`_settings(root, store)`:** `pilot-settings.json` goes into `settings` when there is no `prefs` row; `model-usage.json` into `model_usage` (`INSERT OR IGNORE`); `orders/*.json` into `standing_orders`, mapping the sanitized file name back to a campaign id through `SELECT id FROM campaigns`, falling back to the file stem.
  - **`_secrets(root, data_dir)`:** copy `runs/dashboard.key` and `runs/dashboard.carryover` to `data_dir/secrets/` (mode 0600, `secrets/` 0700) when absent.
  - **`check(root, store, data_dir)`:** recount every source item the same way and compare it with the store and files. Return lines like `"trace 20261001-100000#1 missing"`.
  - **`prune_source(root)`:** delete only the paths listed in plan ruling P5. Refuse (raise) when `git -C root ls-files --error-unmatch <path>` says a path is tracked.
  - **`cli.py data import --from ROOT [--prune-source]`:** prints the report. With `--prune-source`, it runs `check` first and prunes only when `check` returns `[]`. **`cli.py data check --from ROOT`** prints the differences and returns 1 when there are any.
  - **`auth.py`:** the key path is `runs_dir / "secrets" / "dashboard.key"`, falling back to `runs_dir / "dashboard.key"` for reading; `CARRY_FILE` likewise. `_write_private` creates `secrets/` with 0700.
- [ ] **Step 4: Run the tests.**
  1. `.venv/bin/pytest tests/test_dataimport.py -q`.
  2. The full non-UI suite; update the `dashboard.key` tests for `secrets/`.
  3. `.venv/bin/pytest -q -m ui tests/ui`, because `auth.py` is staged.
- [ ] **Step 5: Commit**: `scripts/ci-commit.sh "feat(pilot): pilot data import and check; the dashboard key in secrets/" "<body>"`.

---

### Task 8: Scripts and docs

**Files:**
- Modify: `scripts/civ6-placement.py:75` and `scripts/civ6-backfill-orders.py:28-90`:
  - both use `open_store(<data dir>)` instead of `runs/telemetry.sqlite`;
  - the backfill writes its events through `Telemetry.record` instead of a JSONL file (drop the `--runs-dir`/JSONL code and its docstring paragraph).
- Modify: `docs/pilot.md` (a new "Data directory" section; replace every `runs/telemetry.sqlite`, `pilot-settings.json` and `model-usage.json` mention), `README.md` (settings rows: `PILOT_DATA_DIR`, `PILOT_CORPORA_DIR`, `PILOT_CONTROLLER_BIN`, `PILOT_FRAMES_KEEP`, `PILOT_EXPORT_DIR`; remove `PILOT_COMMIT` and `PILOT_JOURNAL`), `ARCHITECTURE.md` (`store.py`, `learned_files.py`, `export.py`, `dataimport.py`), `AGENTS.md` (§1 table telemetry path; §8 "Recording what you learn": the pilot's learned knowledge lives in the store and reaches the repo through `pilot export --to corpora/..`)
- Test: `tests/test_docs_paths.py`

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Write the failing test** — `tests/test_docs_paths.py`:

```python
"""The docs and scripts name the store, not the files it replaced (data platform design, ruling 14)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GONE = ("telemetry.sqlite", "pilot-settings.json", "model-usage.json", "rebuild-telemetry", "PILOT_COMMIT", "PILOT_JOURNAL")


def test_no_doc_or_runtime_script_names_a_replaced_file():
    files = [ROOT / "README.md", ROOT / "ARCHITECTURE.md", ROOT / "AGENTS.md", ROOT / "docs/pilot.md",
             *ROOT.glob("scripts/*.py"), *ROOT.glob("scripts/*.sh")]
    hits = [f"{p.relative_to(ROOT)}: {w}" for p in files for w in GONE if w in p.read_text(encoding="utf-8")]
    assert hits == [], hits
```

- [ ] **Step 2: Run it to see it fail.** Run: `.venv/bin/pytest tests/test_docs_paths.py -q`.
- [ ] **Step 3: Make the script and doc changes listed under Files.**
  - **Section shape:** the `docs/pilot.md` "Data directory" section gives the layout table from spec ruling 2, then `pilot export`, `pilot data import`/`check`/`--prune-source`, and frame retention.
  - **History is left alone:** design docs and journals under `docs/design/` and `games/` are history and aren't edited.
- [ ] **Step 4: Run the tests.** Run `.venv/bin/pytest tests/test_docs_paths.py -q`, then `scripts/ci.sh`. It must print `CI OK`.
- [ ] **Step 5: Commit**: `scripts/ci-commit.sh "docs: the data directory, export and import; scripts on the store" "<body>"`.

---

## After the tasks (the controller, not a subagent)

1. **Review and merge.** Run the final whole-branch review, then `superpowers:finishing-a-development-branch`, merging to `main`.
2. **Roll out on deb-mini2** (spec ruling 13):
   1. Stop `game-pilot.service` (it's already stopped) and `game-pilot-view.service`.
   2. `git pull`.
   3. `cargo build --release -p game-controller`.
   4. `.venv/bin/python -m pilot data import --from /mnt/codeman-cases/game-harness`.
   5. `.venv/bin/python -m pilot data check --from /mnt/codeman-cases/game-harness`. It must print no differences.
   6. `scripts/deploy-pilot.sh <old> <new>`, then start the viewer.
   7. Confirm on the dashboard that every past campaign is listed and a past decision's trace opens.
3. **Live check (the success criteria).** The next Civ VI run on mini-rig2 should leave `git status` with no learned or journal changes. Learned rules should survive a pilot restart.
4. **Records.** Flip the `plan.md` "Portability 1" entry to `[x]`. Leave `--prune-source` for the user to run once satisfied, and say so.
