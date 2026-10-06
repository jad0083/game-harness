"""pilot data import / check / --prune-source (data platform design, rulings 11-12; plan rulings P4, P5):
an install from before the data platform (runs/telemetry.sqlite, runs/<id>/, corpora/<game>/learned/,
games/<game>/journal.md, the settings files and the dashboard key) copied into the store."""

from __future__ import annotations

import json
import os
import sqlite3
import stat
import subprocess
import time
from pathlib import Path

import pytest

from pilot import cli, dataimport
from pilot.events import EventLog
from pilot.learned_files import notes_markdown
from pilot.modelguard import pacific_day
from pilot.store import open_store

RUN = "20261001-100000"
CID = "civ6/kublai"

# runs/telemetry.sqlite as Telemetry(path) created it at bf313b0 (`git show bf313b0:src/pilot/telemetry.py`)
OLD_SCHEMA = """
CREATE TABLE IF NOT EXISTS campaigns (
    id TEXT PRIMARY KEY,            -- '<game>/<save or journal name>'
    game TEXT NOT NULL,
    name TEXT NOT NULL,
    created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    campaign_id TEXT REFERENCES campaigns(id),
    game TEXT, model TEXT,
    settings TEXT,                  -- JSON
    started REAL, ended REAL,
    status TEXT
);
CREATE TABLE IF NOT EXISTS events (
    run_id TEXT NOT NULL, t REAL NOT NULL, kind TEXT NOT NULL, data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_run ON events(run_id, t);
CREATE TABLE IF NOT EXISTS decisions (
    run_id TEXT NOT NULL, episode INTEGER NOT NULL,
    campaign_id TEXT, t REAL,
    date TEXT, month INTEGER,       -- in-game date and months since year 0 (Stellaris)
    trigger TEXT, decision TEXT, reason TEXT, outcome TEXT, current TEXT,
    tokens_in INTEGER, tokens_out INTEGER, seconds REAL,
    trace TEXT,                     -- JSON: prompt, thinking, tool calls, answer
    result TEXT,                    -- JSON: metric deltas N months later (outcome scoring)
    PRIMARY KEY (run_id, episode)
);
CREATE INDEX IF NOT EXISTS decisions_campaign ON decisions(campaign_id, month);
CREATE TABLE IF NOT EXISTS metrics (
    run_id TEXT NOT NULL, campaign_id TEXT, t REAL,
    date TEXT, month INTEGER, data TEXT NOT NULL,
    PRIMARY KEY (run_id, date)
);
CREATE INDEX IF NOT EXISTS metrics_campaign ON metrics(campaign_id, month);
CREATE TABLE IF NOT EXISTS plans (
    campaign_id TEXT, run_id TEXT NOT NULL, t REAL NOT NULL,
    date TEXT, source TEXT,         -- 'decision'
    text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS plans_campaign ON plans(campaign_id, t);
CREATE TABLE IF NOT EXISTS strategies (
    campaign_id TEXT, run_id TEXT NOT NULL, t REAL, date TEXT, trigger TEXT, model TEXT, data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS strategies_campaign ON strategies(campaign_id, t);
"""

EVENTS = [
    {"t": 1000.0, "kind": "run_start", "game": "civ6", "model": "google:gemini-x"},
    {"t": 1000.5, "kind": "campaign", "game": "civ6", "name": "kublai", "title": "China"},
    {"t": 1001.0, "kind": "trace", "episode": 1, "file": "traces/0001.json", "date": "T41", "trigger": "scheduled",
     "decision": "orders", "thinking": 1, "tools": 2},
]
FILE_ONLY = {"t": 1002.0, "kind": "instruction", "text": "build walls in Beijing", "by": "Pixel phone"}
TRACE = {"episode": 1, "date": "T41", "decision": "orders", "model": "google:gemini-x",
         "steps": [{"type": "prompt", "text": "# civ6 — China (country 0)"}, {"type": "thinking", "text": "hm"}]}
STATUS = {"run_id": RUN, "model": "google:gemini-x", "status": "ended", "episodes": 1, "game_date": "T41",
          "info": {"game": "civ6", "port": 8790}}

NOTES_HEAD = "# {}\n\nWritten by the pilot app during play; promote proven items into the main corpus.\n"
STRATEGY = NOTES_HEAD.format("Learned strategy rules") + (
    "\n- When a city is threatened, buy a defender at once.  \n  _why:_ T45 loss _(google:gemini-x, 2026-09-27)_\n"
    "\n- A colony's amenities deficit is no reason to switch to 'consolidate_economy'.  \n"
    "  _why:_ corrected 2026-09-27 (levers design ruling 22, E10): the retrospective of 2226.08.01 said such a "
    "deficit requires consolidate_economy\n"
    "\n- Keep 100 gold for emergencies (a reserve).  \n  _why:_ T60 _(claude-code:opus, 2026-09-30)_\n")
CONTROLS = NOTES_HEAD.format("Learned controls (verified in play)") + (
    "\n- Esc on the bare map opens the pause menu.  \n  _why:_ seen at T12 _(google:gemini-x, 2026-09-28)_\n")
MANIFEST = """# Known screens learned during play (pilot app). Main manifest wins on name clashes.

[screens.news_popup]
description = "GNN news popup"
template = "learned/templates/news_popup.png"
template_roi = [0.1234, 0.05, 0.2, 0.04]
template_threshold = 0.06
auto_dismiss = true
dismiss_click = [0.5, 0.9]
learned_by = "google:gemini-x"
learned_run = "20261001-100000"
"""
PNG = b"\x89PNG\r\n\x1a\n-template-bytes"
EPISODES = [{"t": "2026-10-01T10:00:00", "date": "T41", "situation": "idle city", "decision": "build archer",
             "outcome": "ok", "model": "google:gemini-x", "run": RUN},
            {"t": "2026-10-01T10:05:00", "date": "T42", "situation": "trade offer", "decision": "reject",
             "outcome": "ok", "model": "google:gemini-x", "run": RUN}]
LEDGER = [{"t": "2026-10-01T10:00:01", "kind": "rule", "name": "When a city is threatened", "model": "google:gemini-x",
           "run": RUN, "why": "T45 loss"},
          {"t": "2026-10-01T10:00:02", "kind": "screen", "name": "news_popup", "model": "google:gemini-x", "run": RUN,
           "description": "GNN news popup", "evidence": "seen twice"}]
JOURNAL = ("## Pilot log\nEntries written by the pilot app (google:gemini-x).\n"
           "- **T41**: Strategy review (start of run): accepted — defend first.\n"
           "- no orders — the cities are building archers.\n")
OLD_KEY = "old-dashboard-key-0123456789abcdefghijklmnopqrstuvwxyz"

HINT = "fix or remove it by hand, then prune"
TABLES = ("campaigns", "runs", "events", "decisions", "metrics", "plans", "strategies", "run_state", "learned_notes",
          "learned_screens", "episodes", "ledger", "journal", "settings", "model_usage", "standing_orders")


def old_telemetry(path: Path, full: bool = True) -> sqlite3.Connection:
    """The old file; `full` adds the columns the old Telemetry added later (ALTER TABLE)."""
    db = sqlite3.connect(path)
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript(OLD_SCHEMA)
    if full:
        db.execute("ALTER TABLE campaigns ADD COLUMN title TEXT")
        for col in ("model", "model_version", "thinking"):
            db.execute(f"ALTER TABLE decisions ADD COLUMN {col} TEXT")
    return db


def jsonl(rows) -> str:
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)


@pytest.fixture
def old_install(tmp_path):
    """Today's layout under tmp_path/repo (as the code at bf313b0 wrote it)."""
    root = tmp_path / "repo"
    runs = root / "runs"
    run = runs / RUN
    (run / "traces").mkdir(parents=True)
    (run / "frames").mkdir()
    db = old_telemetry(runs / "telemetry.sqlite")
    db.execute("INSERT INTO campaigns(id, game, name, created, title) VALUES (?,?,?,?,?)",
               (CID, "civ6", "kublai", 1000.5, "China"))
    db.execute("INSERT INTO runs VALUES (?,?,?,?,?,?,?,?)", (RUN, CID, "civ6", "google:gemini-x", "{}", 1000.0, None, "ended"))
    for ev in EVENTS:
        db.execute("INSERT INTO events VALUES (?,?,?,?)", (RUN, ev["t"], ev["kind"],
                   json.dumps({k: v for k, v in ev.items() if k not in ("t", "kind")})))
    db.execute("INSERT INTO decisions(run_id, episode, campaign_id, t, date, month, trigger, decision, reason, tokens_in,"
               " tokens_out, seconds, trace, model) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,NULL,?)",
               (RUN, 1, CID, 1001.0, "T41", 41, "scheduled", "orders", "defend", 10, 20, 1.5, "google:gemini-x"))
    db.execute("INSERT INTO metrics VALUES (?,?,?,?,?,?)", (RUN, CID, 1001.0, "T41", 41, json.dumps({"cities": 2})))
    db.execute("INSERT INTO plans VALUES (?,?,?,?,?,?)", (CID, RUN, 1001.0, "T41", "decision", "defend, then expand"))
    db.execute("INSERT INTO strategies VALUES (?,?,?,?,?,?,?)", (CID, RUN, 1000.8, "T41", "start", "google:gemini-x",
                                                                 json.dumps({"pillars": [], "reason": "first"})))
    db.commit()
    db.close()
    (run / "events.jsonl").write_text(jsonl([*EVENTS, FILE_ONLY]), encoding="utf-8")
    (run / "status.json").write_text(json.dumps(STATUS))
    (run / "traces/0001.json").write_text(json.dumps(TRACE, ensure_ascii=False, indent=1), encoding="utf-8")
    (run / "frames/00001.jpg").write_bytes(b"\xff\xd8frame-1")
    (run / "latest.jpg").write_bytes(b"\xff\xd8frame-latest")
    (runs / "archive-throwaway/learned").mkdir(parents=True)          # not a run: no events.jsonl, no status.json
    (runs / "archive-throwaway/learned/strategy.md").write_text("kept\n")
    (runs / "pilot-settings.json").write_text(json.dumps({"model": "google:gemini-x", "thinking": "low", "game": "civ6"}))
    (runs / "model-usage.json").write_text(json.dumps({pacific_day(time.time()): {"google:gemini-x": 5},
                                                       "2026-01-01": {"google:gemini-x": 2}}))
    (runs / "orders").mkdir()
    (runs / "orders/civ6_kublai.json").write_text(json.dumps(["build walls in Beijing", "keep 100 gold"], indent=1))
    (runs / "dashboard.key").write_text(OLD_KEY + "\n")
    (runs / "dashboard.key").chmod(0o600)
    learned = root / "corpora/civ6/learned"
    (learned / "templates").mkdir(parents=True)
    (learned / "strategy.md").write_text(STRATEGY, encoding="utf-8")
    (learned / "controls.md").write_text(CONTROLS, encoding="utf-8")
    (learned / "manifest.toml").write_text(MANIFEST, encoding="utf-8")
    (learned / "templates/news_popup.png").write_bytes(PNG)
    (learned / "episodes.jsonl").write_text(jsonl(EPISODES), encoding="utf-8")
    (learned / "ledger.jsonl").write_text(jsonl(LEDGER), encoding="utf-8")
    (root / "games/civ6").mkdir(parents=True)
    (root / "games/civ6/journal.md").write_text(JOURNAL, encoding="utf-8")
    (root / "games/civ6-kublai").mkdir()                    # a hand-written campaign journal: documentation
    (root / "games/civ6-kublai/journal.md").write_text("# Kublai\n\n## Pilot log\n- **T1**: by hand\n")
    return root


def counts(store) -> dict[str, int]:
    return {t: store.query(f"SELECT COUNT(*) AS n FROM {t}")[0]["n"] for t in TABLES}


def snapshot(root: Path) -> dict[str, bytes]:
    """Every source file's bytes; a read-only SQLite open may leave -wal/-shm files beside telemetry.sqlite."""
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*"))
            if p.is_file() and not p.name.endswith(("-wal", "-shm"))}


def do_import(root: Path, data: Path):
    store = open_store(data)
    return store, dataimport.import_install(root, store, data)


# ---------------------------------------------------------------- import

def test_import_copies_everything(old_install, tmp_path):
    before = snapshot(old_install)
    data = tmp_path / "data"
    store, report = do_import(old_install, data)
    want = {"campaigns": 1, "runs": 1, "events": 4, "decisions": 1, "metrics": 1, "plans": 1, "strategies": 1,
            "run_state": 1, "learned_notes": 4, "learned_screens": 1, "episodes": 2, "ledger": 2, "journal": 2,
            "settings": 1, "model_usage": 2, "standing_orders": 2}
    assert counts(store) == want
    assert {k: report.added[k] for k in want} == want
    assert report.frames == 2
    row = store.query("SELECT trace, model FROM decisions WHERE run_id=? AND episode=1", (RUN,))[0]
    assert json.loads(row["trace"]) == TRACE and row["model"] == "google:gemini-x"
    assert store.query("SELECT title FROM campaigns")[0]["title"] == "China"
    only = store.query("SELECT data FROM events WHERE run_id=? AND kind='instruction'", (RUN,))
    assert [json.loads(r["data"]) for r in only] == [{"text": "build walls in Beijing", "by": "Pixel phone"}]
    assert all(isinstance(json.loads(r["data"]), dict) for r in store.query("SELECT data FROM events"))
    assert json.loads(store.query("SELECT data FROM run_state WHERE run_id=?", (RUN,))[0]["data"]) == STATUS
    assert (data / f"frames/{RUN}/00001.jpg").read_bytes() == b"\xff\xd8frame-1"
    assert (data / f"frames/{RUN}/latest.jpg").read_bytes() == b"\xff\xd8frame-latest"
    key = data / "secrets/dashboard.key"
    assert key.read_text().strip() == OLD_KEY
    assert stat.S_IMODE(key.stat().st_mode) == 0o600 and stat.S_IMODE(key.parent.stat().st_mode) == 0o700
    gen = data / "learned/civ6"
    assert "[screens.news_popup]" in (gen / "manifest.toml").read_text()
    assert "template_roi = [0.1234, 0.05, 0.2, 0.04]" in (gen / "manifest.toml").read_text()
    assert "dismiss_click = [0.5, 0.9]" in (gen / "manifest.toml").read_text()
    assert (gen / "templates/news_popup.png").read_bytes() == PNG
    assert (gen / "strategy.md").read_text(encoding="utf-8") == STRATEGY       # both bullet shapes, byte for byte
    assert (gen / "controls.md").read_text(encoding="utf-8") == CONTROLS
    rows = store.query("SELECT campaign_id, game, t, date, text FROM journal ORDER BY t")
    assert rows == [{"campaign_id": "civ6/imported-journal", "game": "civ6", "t": 0.0, "date": "T41",
                     "text": "Strategy review (start of run): accepted — defend first."},
                    {"campaign_id": "civ6/imported-journal", "game": "civ6", "t": 1.0, "date": "",
                     "text": "no orders — the cities are building archers."}]
    prefs = json.loads(store.query("SELECT value FROM settings WHERE key='prefs'")[0]["value"])
    assert prefs["model"] == "google:gemini-x" and prefs["game"] == "civ6"
    assert [r["text"] for r in store.query("SELECT text FROM standing_orders WHERE campaign_id=? ORDER BY position",
                                           (CID,))] == ["build walls in Beijing", "keep 100 gold"]
    eps = store.query("SELECT t, situation, run_id FROM episodes ORDER BY t")
    assert [(e["situation"], e["run_id"]) for e in eps] == [("idle city", RUN), ("trade offer", RUN)]
    led = store.query("SELECT game, t, kind, data FROM ledger ORDER BY t")
    assert led[1]["kind"] == "screen" and json.loads(led[1]["data"])["evidence"] == "seen twice"
    assert report.skipped == ["runs/archive-throwaway: not a run directory"]
    assert snapshot(old_install) == before, "the source is never changed"


def test_import_twice_and_after_new_runs(old_install, tmp_path):
    data = tmp_path / "data"
    store, _ = do_import(old_install, data)
    log = EventLog(data, "20261002-090000", "m", telemetry=store)
    log.emit("run_start", game="civ6", model="m")
    log.set_campaign("civ6", "kublai")
    log.emit("instruction", text="a new run's event")
    log.frame(b"\xff\xd8new")
    after_new = counts(store)
    report = dataimport.import_install(old_install, store, data)
    assert counts(store) == after_new
    assert all(n == 0 for n in report.added.values()), report.added
    assert report.frames == 0
    new = store.query("SELECT kind FROM events WHERE run_id='20261002-090000' ORDER BY t, rowid")
    assert [r["kind"] for r in new] == ["run_start", "campaign", "instruction"]
    assert dataimport.check(old_install, store, data) == []


def test_import_skips_damaged_files_and_reports_them(old_install, tmp_path):
    """Review Focus 2: reported and skipped, never aborting. Ruling R11: check names each damaged source
    that prune could delete (the run's files), so prune waits; a learned file is never pruned."""
    run = old_install / "runs" / RUN
    (run / "status.json").write_text('{"run_id": "20261001-1')
    with open(run / "events.jsonl", "a", encoding="utf-8") as f:
        f.write('{"t": 1003.0, "kind": "sta\n{"t": 1004.0, "kind": "chat", "text": "ok"}\n[1, 2]\n')
    (run / "traces/0002.json").write_text("{broken")
    (old_install / "corpora/civ6/learned/manifest.toml").write_text("[screens.x\nbad = ")
    data = tmp_path / "data"
    store, report = do_import(old_install, data)
    text = "\n".join(report.skipped)
    assert f"runs/{RUN}/status.json: not valid JSON" in text
    assert f"runs/{RUN}/events.jsonl line 5: not valid JSON" in text       # the truncated line, now mid-file
    assert f"runs/{RUN}/events.jsonl line 7: not a JSON object" in text
    assert f"runs/{RUN}/traces/0002.json: not valid JSON" in text
    assert "corpora/civ6/learned/manifest.toml: not valid TOML" in text
    assert store.query("SELECT COUNT(*) AS n FROM events WHERE kind='chat'")[0]["n"] == 1, "the import went on"
    assert store.query("SELECT COUNT(*) AS n FROM run_state")[0]["n"] == 0
    assert store.query("SELECT COUNT(*) AS n FROM learned_notes")[0]["n"] == 4, "the other learned files still import"
    diffs = dataimport.check(old_install, store, data)
    for item in (f"runs/{RUN}/status.json: not valid JSON", f"runs/{RUN}/events.jsonl line 5: not valid JSON",
                 f"runs/{RUN}/events.jsonl line 7: not a JSON object", f"runs/{RUN}/traces/0002.json: not valid JSON"):
        assert [d for d in diffs if d.startswith(item) and d.endswith(HINT)], (item, diffs)
    assert not [d for d in diffs if "manifest.toml" in d], "a learned file is never pruned: it does not block"
    assert len(diffs) == 4, diffs


def test_events_and_run_states_that_are_not_json_objects_are_skipped(tmp_path):
    root = tmp_path / "repo"
    run = root / "runs/r1"
    run.mkdir(parents=True)
    (run / "events.jsonl").write_text('"just a string"\n{"kind": "chat"}\n{"t": 5, "kind": "chat", "text": "hi"}\n')
    (run / "status.json").write_text("[1, 2]")
    db = old_telemetry(root / "runs/telemetry.sqlite")
    db.execute("INSERT INTO events VALUES ('r2', 1.0, 'chat', '[\"not an object\"]')")
    db.execute("INSERT INTO events VALUES ('r2', 2.0, 'chat', '{\"text\": \"fine\"}')")
    db.commit()
    db.close()
    store, report = do_import(root, tmp_path / "data")
    text = "\n".join(report.skipped)
    assert "runs/r1/events.jsonl line 1: not a JSON object" in text
    assert "runs/r1/events.jsonl line 2: no t or kind" in text
    assert "runs/r1/status.json: not a JSON object" in text
    assert "telemetry.sqlite event r2" in text and "not a JSON object" in text
    assert [json.loads(r["data"]) for r in store.query("SELECT data FROM events ORDER BY run_id, t")] == \
        [{"text": "hi"}, {"text": "fine"}]
    assert store.query("SELECT COUNT(*) AS n FROM run_state")[0]["n"] == 0


def test_an_old_telemetry_file_without_the_later_columns_imports(tmp_path):
    root = tmp_path / "repo"
    (root / "runs").mkdir(parents=True)
    db = old_telemetry(root / "runs/telemetry.sqlite", full=False)
    db.execute("INSERT INTO campaigns VALUES ('civ6/a', 'civ6', 'a', 1.0)")
    db.execute("INSERT INTO decisions(run_id, episode, campaign_id, decision) VALUES ('r1', 1, 'civ6/a', 'keep')")
    db.execute("DROP TABLE strategies")                     # an older file still: the table came later
    db.commit()
    db.close()
    store, report = do_import(root, tmp_path / "data")
    assert store.query("SELECT id, title FROM campaigns") == [{"id": "civ6/a", "title": None}]
    assert store.query("SELECT decision, model, thinking FROM decisions") == \
        [{"decision": "keep", "model": None, "thinking": None}]
    assert report.added["campaigns"] == 1 and report.added["decisions"] == 1


def test_the_source_telemetry_file_is_opened_read_only(old_install, tmp_path):
    """A WAL-mode source whose WAL was never checkpointed (a pilot that died): a read-write connection
    would checkpoint the WAL into the main file and delete it on close; mode=ro reads both, writes none."""
    path = old_install / "runs/telemetry.sqlite"
    live = tmp_path / "live.sqlite"
    path.rename(live)
    w = sqlite3.connect(live)
    w.execute("PRAGMA wal_autocheckpoint=0")
    w.execute("INSERT INTO events VALUES (?, 1001.5, 'chat', '{\"text\": \"only in the WAL\"}')", (RUN,))
    w.commit()
    path.write_bytes(live.read_bytes())
    Path(f"{path}-wal").write_bytes(Path(f"{live}-wal").read_bytes())
    w.close()
    main, wal = path.read_bytes(), Path(f"{path}-wal").read_bytes()
    store, _ = do_import(old_install, tmp_path / "data")
    assert store.query("SELECT COUNT(*) AS n FROM events WHERE t=1001.5")[0]["n"] == 1, "the WAL was read"
    assert path.read_bytes() == main and Path(f"{path}-wal").read_bytes() == wal


def test_notes_with_and_without_attribution_round_trip(tmp_path):
    """18 hand-corrected Stellaris rules carry no `_(model, date)_` suffix (ruling R7a)."""
    root = tmp_path / "repo"
    learned = root / "corpora/stellaris/learned"
    learned.mkdir(parents=True)
    (learned / "strategy.md").write_text(STRATEGY, encoding="utf-8")
    store, _ = do_import(root, tmp_path / "data")
    rows = store.query("SELECT text, why, model, t FROM learned_notes ORDER BY rowid")
    assert len(rows) == 3
    assert rows[1]["model"] is None and rows[1]["t"] is None and rows[1]["why"].startswith("corrected 2026-09-27")
    assert (rows[0]["model"], rows[0]["t"]) == ("google:gemini-x", "2026-09-27")
    assert notes_markdown(store, "stellaris", "rule") == STRATEGY
    assert (tmp_path / "data/learned/stellaris/strategy.md").read_text(encoding="utf-8") == STRATEGY


def test_notes_and_episodes_the_store_cannot_hold_are_reported(tmp_path):
    """A bullet with no why, a rule written twice (the store keeps one note per text) and an episode
    repeated with the same t and situation are named, not dropped silently."""
    root = tmp_path / "repo"
    learned = root / "corpora/civ6/learned"
    learned.mkdir(parents=True)
    again = "\n- When a city is threatened, buy a defender at once.  \n  _why:_ T50 _(google:gemini-x, 2026-09-29)_\n"
    (learned / "strategy.md").write_text(STRATEGY + "\n- a hand-written line with no why\n" + again, encoding="utf-8")
    (learned / "episodes.jsonl").write_text(jsonl([EPISODES[0], EPISODES[1], EPISODES[0]]), encoding="utf-8")
    store, report = do_import(root, tmp_path / "data")
    assert store.query("SELECT COUNT(*) AS n FROM learned_notes")[0]["n"] == 3
    assert store.query("SELECT why FROM learned_notes ORDER BY rowid")[0]["why"] == "T45 loss", "the first is kept"
    assert store.query("SELECT COUNT(*) AS n FROM episodes")[0]["n"] == 2
    text = "\n".join(report.skipped)
    assert "corpora/civ6/learned/strategy.md item 4: not a learned note" in text
    assert "corpora/civ6/learned/strategy.md item 5: the same text as item 1, kept once" in text
    assert "corpora/civ6/learned/episodes.jsonl line 3: the same t and situation as line 1, kept once" in text
    assert dataimport.check(root, store, tmp_path / "data") == []


def test_multi_line_journal_entries_import_whole(tmp_path):
    """Journal.note wrote `- {stamp}{text.strip()}` with the text's own newlines (ruling R7b)."""
    root = tmp_path / "repo"
    (root / "games/civ6").mkdir(parents=True)
    (root / "games/civ6/journal.md").write_text(
        "## Pilot log\nEntries written by the pilot app (m).\n"
        "- **T55**: Strategy review: accepted — Defence worked.\n\nThe economy is behind.\n\nKeep security first.\n"
        "- **T61**: no orders — fine.\n"
        "- **T73**: civic: unknown: no reply (Error: Failed\n\nCaused by:\n    0: timed out); civic is None\n\n\n",
        encoding="utf-8")
    (root / "games/terran-2329").mkdir(parents=True)
    (root / "games/terran-2329/journal.md").write_text(
        "# Journal\n\n## 2329\n- **Open threads**: not a pilot line\n\n## Pilot log\nEntries written by the pilot app (m).\n"
        "- **Oct 4, 2333**: Idle core world: Earth\n", encoding="utf-8")
    store, _ = do_import(root, tmp_path / "data")
    rows = store.query("SELECT campaign_id, game, t, date, text FROM journal ORDER BY campaign_id, t")
    assert [(r["campaign_id"], r["t"], r["date"]) for r in rows] == [
        ("civ6/imported-journal", 0.0, "T55"), ("civ6/imported-journal", 1.0, "T61"),
        ("civ6/imported-journal", 2.0, "T73"), ("galciv4/imported-journal", 0.0, "Oct 4, 2333")]
    assert rows[0]["text"] == "Strategy review: accepted — Defence worked.\n\nThe economy is behind.\n\nKeep security first."
    assert rows[2]["text"] == "civic: unknown: no reply (Error: Failed\n\nCaused by:\n    0: timed out); civic is None"
    assert rows[3]["game"] == "galciv4"
    again = dataimport.import_install(root, store, tmp_path / "data")
    assert again.added["journal"] == 0


def test_learned_screens_without_a_region_or_threshold_are_skipped(tmp_path):
    root = tmp_path / "repo"
    learned = root / "corpora/galciv4/learned"
    (learned / "templates").mkdir(parents=True)
    for n in ("good", "no_roi", "bad_roi", "no_threshold", "clicks"):
        (learned / f"templates/{n}.png").write_bytes(PNG)
    (learned / "manifest.toml").write_text(
        '[screens.good]\ntemplate = "learned/templates/good.png"\ntemplate_roi = [0.1, 0.1, 0.2, 0.05]\n'
        'template_threshold = 0.06\nauto_dismiss = true\ndismiss_key = "c"\n'
        '[screens.no_roi]\ntemplate = "learned/templates/no_roi.png"\ntemplate_threshold = 0.06\ndismiss_key = "c"\n'
        '[screens.bad_roi]\ntemplate = "learned/templates/bad_roi.png"\ntemplate_roi = [0.1, "x", 0.2, 0.05]\n'
        'template_threshold = 0.06\ndismiss_key = "c"\n'
        '[screens.no_threshold]\ntemplate = "learned/templates/no_threshold.png"\ntemplate_roi = [0.1, 0.1, 0.2, 0.05]\n'
        'dismiss_key = "c"\n'
        '[screens.clicks]\ntemplate = "learned/templates/clicks.png"\ntemplate_roi = [0.1, 0.1, 0.2, 0.05]\n'
        'template_threshold = 0.06\ndismiss_clicks = [[0.1, 0.2], [0.3, 0.4]]\n'
        '[screens.no_template]\ntemplate = "learned/templates/gone.png"\ntemplate_roi = [0.1, 0.1, 0.2, 0.05]\n'
        'template_threshold = 0.06\ndismiss_key = "c"\n')
    store, report = do_import(root, tmp_path / "data")
    assert [r["name"] for r in store.query("SELECT name FROM learned_screens")] == ["good"]
    assert json.loads(store.query("SELECT action FROM learned_screens")[0]["action"]) == {"key": "c"}
    text = "\n".join(report.skipped)
    for name, why in (("no_roi", "template_roi"), ("bad_roi", "template_roi"), ("no_threshold", "template_threshold"),
                      ("clicks", "dismiss_clicks"), ("no_template", "template file")):
        assert f"screen {name}" in text and why in text, (name, text)
    assert dataimport.check(root, store, tmp_path / "data") == []


# ---------------------------------------------------------------- check

def test_check_reports_missing_items(old_install, tmp_path):
    data = tmp_path / "data"
    store, _ = do_import(old_install, data)
    assert dataimport.check(old_install, store, data) == []
    store._exec("UPDATE decisions SET trace=NULL WHERE run_id=? AND episode=1", (RUN,))
    (data / f"frames/{RUN}/00001.jpg").unlink()
    store._exec("DELETE FROM learned_screens WHERE game='civ6' AND name='news_popup'")
    diffs = dataimport.check(old_install, store, data)
    assert f"trace {RUN}#1 missing" in diffs
    assert f"frame {RUN}/00001.jpg missing" in diffs
    assert "learned screen civ6/news_popup missing" in diffs
    assert len(diffs) == 3, diffs


def test_check_reports_missing_rows_of_every_source(old_install, tmp_path):
    data = tmp_path / "data"
    store, _ = do_import(old_install, data)
    for sql in ("DELETE FROM events WHERE kind='instruction'", "DELETE FROM journal WHERE t=1",
                "DELETE FROM standing_orders", "DELETE FROM settings", "DELETE FROM learned_notes WHERE kind='control'",
                "DELETE FROM episodes WHERE situation='idle city'", "DELETE FROM run_state", "DELETE FROM metrics"):
        store._exec(sql)
    (data / "secrets/dashboard.key").unlink()
    diffs = "\n".join(dataimport.check(old_install, store, data))
    for want in (f"events {RUN}: 1 missing", "journal civ6/imported-journal #1 missing", f"standing orders {CID} missing",
                 "prefs missing", "learned control civ6", "episode civ6", f"run state {RUN} missing",
                 f"metrics {RUN} T41 missing", "secret dashboard.key missing"):
        assert want in diffs, (want, diffs)


def test_check_ignores_model_usage_days_the_guard_no_longer_keeps(old_install, tmp_path):
    data = tmp_path / "data"
    store, _ = do_import(old_install, data)
    store._exec("DELETE FROM model_usage WHERE day='2026-01-01'")      # the guard drops days older than a week
    assert dataimport.check(old_install, store, data) == []
    store._exec("DELETE FROM model_usage")
    assert dataimport.check(old_install, store, data) == [f"model usage {pacific_day(time.time())} google:gemini-x missing"]


# ---------------------------------------------------------------- prune

def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *args], cwd=root, check=True,
                   capture_output=True)


def test_prune_removes_only_untracked_runtime_files(old_install, tmp_path):
    git(old_install, "init", "-q")
    git(old_install, "add", "corpora", "games")
    git(old_install, "commit", "-q", "-m", "base")
    data = tmp_path / "data"
    store, _ = do_import(old_install, data)
    assert dataimport.check(old_install, store, data) == []
    runs = old_install / "runs"
    deleted = dataimport.prune_source(old_install, store)
    for gone in ("telemetry.sqlite", RUN, "pilot-settings.json", "model-usage.json", "orders", "dashboard.key"):
        assert not (runs / gone).exists(), gone
        assert runs / gone in deleted
    assert not (runs / "telemetry.sqlite-wal").exists() and not (runs / "telemetry.sqlite-shm").exists()
    assert (runs / "archive-throwaway/learned/strategy.md").read_text() == "kept\n", "not a run directory: left alone"
    for kept in ("strategy.md", "controls.md", "manifest.toml", "templates/news_popup.png", "episodes.jsonl",
                 "ledger.jsonl"):
        assert (old_install / "corpora/civ6/learned" / kept).exists(), kept
    assert (old_install / "games/civ6/journal.md").exists()
    assert counts(store)["events"] == 4 and (data / "secrets/dashboard.key").exists()


def test_prune_refuses_a_tracked_path_and_deletes_nothing(old_install, tmp_path):
    git(old_install, "init", "-q")
    git(old_install, "add", "-f", f"runs/{RUN}/status.json", "games")
    git(old_install, "commit", "-q", "-m", "base")
    data = tmp_path / "data"
    store, _ = do_import(old_install, data)
    with pytest.raises(dataimport.PruneRefused, match=f"runs/{RUN}"):
        dataimport.prune_source(old_install, store)
    assert (old_install / "runs/telemetry.sqlite").exists() and (old_install / "runs/pilot-settings.json").exists()


def test_prune_keeps_a_run_directory_with_no_run_in_the_store(old_install, tmp_path):
    (old_install / "runs/20261003-120000").mkdir()             # a run log the store has no run for
    (old_install / "runs/20261003-120000/status.json").write_text(json.dumps({"status": "ended"}))
    data = tmp_path / "data"
    store, _ = do_import(old_install, data)
    kept: list[str] = []
    deleted = dataimport.prune_source(old_install, store, kept)
    assert (old_install / "runs/20261003-120000/status.json").exists()
    assert old_install / "runs/telemetry.sqlite" in deleted
    assert kept == ["runs/20261003-120000: no run of that id in the store"]


def test_prune_keeps_an_old_key_that_differs_from_the_one_in_secrets(old_install, tmp_path):
    data = tmp_path / "data"
    (data / "secrets").mkdir(parents=True)
    (data / "secrets/dashboard.key").write_text("a-newer-key\n")
    store, report = do_import(old_install, data)
    assert (data / "secrets/dashboard.key").read_text() == "a-newer-key\n", "never overwritten"
    assert any("dashboard.key" in s and "differs" in s for s in report.skipped), report.skipped
    dataimport.prune_source(old_install, store)
    assert (old_install / "runs/dashboard.key").read_text().strip() == OLD_KEY


def test_import_check_and_prune_in_place(old_install):
    """The default install: the data directory IS <root>/runs (PILOT_DATA_DIR unset), ruling R8."""
    runs = old_install / "runs"
    (runs / "auth.sqlite").write_bytes(b"sign-in store")
    store, report = do_import(old_install, runs)
    assert (runs / "pilot.db").exists() and (runs / f"frames/{RUN}/latest.jpg").exists()
    assert (runs / "secrets/dashboard.key").read_text().strip() == OLD_KEY
    assert not any(s.startswith(("runs/frames", "runs/learned", "runs/secrets")) for s in report.skipped), report.skipped
    assert dataimport.check(old_install, store, runs) == []
    again = dataimport.import_install(old_install, store, runs)
    assert all(n == 0 for n in again.added.values()) and again.frames == 0
    assert [s for s in again.skipped if "not a run directory" in s] == ["runs/archive-throwaway: not a run directory"]
    before = counts(store)
    deleted = dataimport.prune_source(old_install, store)
    assert runs / RUN in deleted and not (runs / RUN).exists() and not (runs / "telemetry.sqlite").exists()
    assert not (runs / "dashboard.key").exists()
    for kept in ("pilot.db", f"frames/{RUN}/00001.jpg", f"frames/{RUN}/latest.jpg", "learned/civ6/manifest.toml",
                 "secrets/dashboard.key", "auth.sqlite", "archive-throwaway/learned/strategy.md"):
        assert (runs / kept).exists(), kept
    assert counts(store) == before
    assert dataimport.check(old_install, store, runs) == []


# ---------------------------------------------------------------- the command

def test_data_import_check_and_prune_commands(old_install, tmp_path, monkeypatch, capsys):
    data = tmp_path / "data"
    monkeypatch.setenv("PILOT_DATA_DIR", str(data))
    monkeypatch.delenv("PILOT_RUNS_DIR", raising=False)
    assert cli.main(["data", "import", "--from", str(old_install)]) == 0
    out = capsys.readouterr().out
    assert "events: 4 added" in out and "frames: 2 copied" in out
    assert "skipped (1):\n  runs/archive-throwaway: not a run directory" in out
    assert cli.main(["data", "check", "--from", str(old_install)]) == 0
    assert "nothing missing" in capsys.readouterr().out
    (data / f"frames/{RUN}/latest.jpg").unlink()
    assert cli.main(["data", "check", "--from", str(old_install)]) == 1
    assert f"frame {RUN}/latest.jpg missing" in capsys.readouterr().out.splitlines()
    open_store(data)._exec("DELETE FROM journal")
    assert cli.main(["data", "import", "--from", str(old_install), "--prune-source"]) == 0
    out = capsys.readouterr().out
    assert "journal: 2 added" in out and "frames: 1 copied" in out
    assert f"deleted {old_install / 'runs' / RUN}" in out
    assert not (old_install / "runs/telemetry.sqlite").exists()


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads a file whatever its mode")
def test_prune_source_is_refused_while_check_finds_differences(old_install, tmp_path, monkeypatch, capsys):
    data = tmp_path / "data"
    monkeypatch.setenv("PILOT_DATA_DIR", str(data))
    (old_install / "runs" / RUN / "latest.jpg").chmod(0o000)      # cannot be copied: check finds it missing
    try:
        assert cli.main(["data", "import", "--from", str(old_install), "--prune-source"]) == 1
    finally:
        (old_install / "runs" / RUN / "latest.jpg").chmod(0o644)
    out = capsys.readouterr().out
    assert "not pruned" in out and (old_install / "runs/telemetry.sqlite").exists()


def test_a_trace_event_without_an_episode_is_skipped_and_the_run_goes_on(old_install, tmp_path):
    with open(old_install / "runs" / RUN / "events.jsonl", "a", encoding="utf-8") as f:
        f.write('\n{"t": 1005.0, "kind": "trace", "decision": "keep"}\n{"t": 1006.0, "kind": "chat", "text": "after"}\n')
    store, report = do_import(old_install, tmp_path / "data")
    assert f"runs/{RUN}/events.jsonl line 6: a trace event without an episode" in report.skipped
    assert store.query("SELECT COUNT(*) AS n FROM events WHERE kind='chat'")[0]["n"] == 1


def test_files_are_copied_where_the_filesystem_has_no_hard_links(old_install, tmp_path, monkeypatch):
    def no_link(*_):
        raise PermissionError("hard links are not supported here")
    monkeypatch.setattr(dataimport.os, "link", no_link)
    data = tmp_path / "data"
    store, report = do_import(old_install, data)
    assert report.frames == 2 and report.added["secrets"] == 1
    assert (data / "secrets/dashboard.key").read_text().strip() == OLD_KEY
    assert stat.S_IMODE((data / "secrets/dashboard.key").stat().st_mode) == 0o600
    assert dataimport.check(old_install, store, data) == []
    assert not [p for p in data.rglob("*.tmp")], "no temp files left"


def test_a_decision_stored_without_a_trace_takes_the_old_files(old_install, tmp_path):
    db = sqlite3.connect(old_install / "runs/telemetry.sqlite")
    db.execute("UPDATE decisions SET trace=? WHERE episode=1", (json.dumps({"steps": [], "from": "telemetry"}),))
    db.commit()
    db.close()
    (old_install / "runs" / RUN / "traces/0001.json").unlink()
    data = tmp_path / "data"
    store = open_store(data)
    store._exec("INSERT INTO decisions(run_id, episode, decision) VALUES (?, 1, 'orders')", (RUN,))
    dataimport.import_install(old_install, store, data)
    row = store.query("SELECT trace, decision FROM decisions WHERE run_id=? AND episode=1", (RUN,))[0]
    assert json.loads(row["trace"])["from"] == "telemetry" and row["decision"] == "orders"
    assert dataimport.check(old_install, store, data) == []


# ---------------------------------------------------------------- fix round 1: prune fails closed (R11)

def _bad_telemetry(root: Path) -> None:
    p = root / "runs/telemetry.sqlite"
    p.write_bytes(b"not a database, " * 8 + p.read_bytes()[128:])


def _non_utf8_line(root: Path) -> None:
    with open(root / "runs" / RUN / "events.jsonl", "ab") as f:
        f.write(b'{"t": 1009.0, "kind": "chat", "text": "caf\xe9"}\n{"t": 1010.0, "kind": "chat", "text": "next"}\n')


DAMAGE = {
    "unreadable telemetry": (_bad_telemetry, "runs/telemetry.sqlite: cannot be read", "runs/telemetry.sqlite"),
    "non-UTF-8 events line": (_non_utf8_line, f"runs/{RUN}/events.jsonl line 5: not UTF-8", f"runs/{RUN}/events.jsonl"),
    "orphan trace": (lambda r: (r / "runs" / RUN / "traces/0009.json").write_text('{"steps": []}'),
                     f"runs/{RUN}/traces/0009.json: no decision 9", f"runs/{RUN}/traces/0009.json"),
    "undecodable trace": (lambda r: (r / "runs" / RUN / "traces/0002.json").write_bytes(b'{"steps": "\xff"}'),
                          f"runs/{RUN}/traces/0002.json: cannot be read", f"runs/{RUN}/traces/0002.json"),
    "unparseable status": (lambda r: (r / "runs" / RUN / "status.json").write_text("{broken"),
                           f"runs/{RUN}/status.json: not valid JSON", f"runs/{RUN}/status.json"),
    "undecodable settings": (lambda r: (r / "runs/pilot-settings.json").write_bytes(b'{"model": "\xff"}'),
                             "runs/pilot-settings.json: cannot be read", "runs/pilot-settings.json"),
    "unparseable usage": (lambda r: (r / "runs/model-usage.json").write_text("{"),
                          "runs/model-usage.json: not valid JSON", "runs/model-usage.json"),
    "bad orders": (lambda r: (r / "runs/orders/civ6_kublai.json").write_text("[1, 2]"),
                   "runs/orders/civ6_kublai.json: not a list of orders", "runs/orders/civ6_kublai.json"),
    "unknown file in a run": (lambda r: (r / "runs" / RUN / "notes.md").write_text("by hand\n"),
                              f"runs/{RUN}/notes.md: a file the old pilot did not write", f"runs/{RUN}/notes.md"),
    "unknown file in frames": (lambda r: (r / "runs" / RUN / "frames/clip.png").write_bytes(b"png"),
                               f"runs/{RUN}/frames/clip.png: a file the old pilot did not write",
                               f"runs/{RUN}/frames/clip.png"),
    "bad trace name": (lambda r: (r / "runs" / RUN / "traces/notes.json").write_text("{}"),
                       f"runs/{RUN}/traces/notes.json: not a trace file name", f"runs/{RUN}/traces/notes.json"),
}


@pytest.mark.parametrize("case", DAMAGE)
def test_a_source_not_imported_in_full_blocks_prune(old_install, tmp_path, monkeypatch, capsys, case):
    """Ruling R11: check names every prunable source not imported in full, with a hint, and prune refuses
    (from the command and from prune_source itself) while it does; the source survives."""
    damage, item, survivor = DAMAGE[case]
    damage(old_install)
    data = tmp_path / "data"
    monkeypatch.setenv("PILOT_DATA_DIR", str(data))
    assert cli.main(["data", "import", "--from", str(old_install), "--prune-source"]) == 1
    out = capsys.readouterr().out
    assert "not pruned" in out and item in out, out
    assert (old_install / survivor).exists() and (old_install / "runs/telemetry.sqlite").exists()
    store = open_store(data)
    diffs = dataimport.check(old_install, store, data)
    assert [d for d in diffs if d.startswith(item) and d.endswith(HINT)], diffs
    with pytest.raises(dataimport.PruneRefused):
        dataimport.prune_source(old_install, store)
    assert (old_install / survivor).exists()


def test_a_non_utf8_byte_costs_one_line(old_install, tmp_path):
    _non_utf8_line(old_install)
    store, report = do_import(old_install, tmp_path / "data")
    assert f"runs/{RUN}/events.jsonl line 5: not UTF-8" in report.skipped
    assert [json.loads(r["data"])["text"] for r in store.query("SELECT data FROM events WHERE kind='chat'")] == ["next"]
    assert store.query("SELECT COUNT(*) AS n FROM events")[0]["n"] == 5, "the other lines are imported"


def test_events_that_fail_to_record_are_reported_and_block_prune(tmp_path):
    """P4: a metrics event whose date is a number (month_index raises TypeError); P5: a trace whose steps
    are strings (AttributeError in the title lookup). Each line is reported and leaves nothing behind;
    the import goes on, and check names the lines until they are fixed."""
    root = tmp_path / "repo"
    run = root / "runs/r1"
    (run / "traces").mkdir(parents=True)
    (run / "traces/0001.json").write_text(json.dumps({"episode": 1, "steps": ["not", "objects"]}))
    (run / "events.jsonl").write_text(jsonl([
        {"t": 1.0, "kind": "run_start", "game": "civ6", "model": "m"},
        {"t": 2.0, "kind": "campaign", "game": "civ6", "name": "a"},
        {"t": 3.0, "kind": "metrics", "date": 41, "cities": 2},
        {"t": 4.0, "kind": "trace", "episode": 1, "file": "traces/0001.json"},
        {"t": 5.0, "kind": "chat", "text": "after"}]))
    data = tmp_path / "data"
    store, report = do_import(root, data)
    text = "\n".join(report.skipped)
    assert "runs/r1/events.jsonl line 3: not recorded (TypeError" in text
    assert "runs/r1/events.jsonl line 4: not recorded (AttributeError" in text
    assert [r["kind"] for r in store.query("SELECT kind FROM events ORDER BY t")] == ["run_start", "campaign", "chat"]
    assert store.query("SELECT COUNT(*) AS n FROM metrics")[0]["n"] == 0, "no half-recorded event"
    diffs = dataimport.check(root, store, data)
    assert "events r1: 2 missing (events.jsonl lines 3, 4)" in diffs, diffs
    with pytest.raises(dataimport.PruneRefused):
        dataimport.prune_source(root, store)


def test_a_corrupt_table_in_the_old_file_is_reported_and_blocks_prune(tmp_path):
    """Q3: a damaged page partway through a table: the rows before it are imported, the table is named,
    the import goes on to the other tables and sources, and check names it (prune waits)."""
    root = tmp_path / "repo"
    (root / "runs").mkdir(parents=True)
    path = root / "runs/telemetry.sqlite"
    db = sqlite3.connect(path)
    db.executescript(OLD_SCHEMA)
    db.execute("INSERT INTO campaigns VALUES ('civ6/a', 'civ6', 'a', 1.0)")
    db.execute("DROP INDEX events_run")                     # every page past the schema holds events rows
    for i in range(400):
        db.execute("INSERT INTO events VALUES ('r1', ?, 'chat', ?)", (float(i), json.dumps({"text": "x" * 400})))
    db.commit()
    page, pages = db.execute("PRAGMA page_size").fetchone()[0], db.execute("PRAGMA page_count").fetchone()[0]
    db.close()
    raw = bytearray(path.read_bytes())
    raw[(pages // 2) * page:(pages // 2 + 1) * page] = b"\xa5" * page
    path.write_bytes(bytes(raw))
    data = tmp_path / "data"
    store, report = do_import(root, data)
    assert any(s.startswith("runs/telemetry.sqlite table events: cannot be read") for s in report.skipped), report.skipped
    assert store.query("SELECT COUNT(*) AS n FROM campaigns")[0]["n"] == 1
    diffs = dataimport.check(root, store, data)
    assert [d for d in diffs if d.startswith("runs/telemetry.sqlite table events: cannot be read") and d.endswith(HINT)]
    with pytest.raises(dataimport.PruneRefused):
        dataimport.prune_source(root, store)
    assert path.exists()


def test_events_sharing_t_and_kind_are_counted(old_install, tmp_path):
    """Two events of one run with the same t and kind are two events: a store holding one gets the other."""
    with open(old_install / "runs" / RUN / "events.jsonl", "a", encoding="utf-8") as f:
        f.write(jsonl([{"t": 1007.0, "kind": "dismissed", "name": "a"}, {"t": 1007.0, "kind": "dismissed", "name": "b"}]))
    data = tmp_path / "data"
    store, _ = do_import(old_install, data)
    assert store.query("SELECT COUNT(*) AS n FROM events WHERE kind='dismissed'")[0]["n"] == 2
    store._exec("DELETE FROM events WHERE rowid = (SELECT MAX(rowid) FROM events WHERE kind='dismissed')")
    assert f"events {RUN}: 1 missing (events.jsonl line 6)" in dataimport.check(old_install, store, data)
    report = dataimport.import_install(old_install, store, data)
    assert report.added["events"] == 1
    assert dataimport.check(old_install, store, data) == []
    assert dataimport.import_install(old_install, store, data).added["events"] == 0


def test_check_names_only_run_log_lines_the_store_lacks(old_install, tmp_path):
    """The telemetry file holds three copies of one (t, kind), the run log one: a store holding two lacks one,
    and the log's line is not named (the store holds as many as the log has)."""
    db = sqlite3.connect(old_install / "runs/telemetry.sqlite")
    for _ in range(2):
        db.execute("INSERT INTO events VALUES (?, 1001.0, 'trace', '{}')", (RUN,))
    db.commit()
    db.close()
    data = tmp_path / "data"
    store, _ = do_import(old_install, data)
    store._exec("DELETE FROM events WHERE rowid = (SELECT MAX(rowid) FROM events WHERE kind='trace')")
    assert f"events {RUN}: 1 missing" in dataimport.check(old_install, store, data)


@pytest.mark.parametrize("git_fails", ["missing", "dubious ownership"])
def test_prune_refuses_when_git_cannot_answer_inside_a_repo(old_install, tmp_path, monkeypatch, git_fails):
    """The install sits below the repository's top (P7): .git is found in a parent, and when git cannot
    say what is tracked, nothing is deleted."""
    git(tmp_path, "init", "-q")
    data = tmp_path / "data"
    store, _ = do_import(old_install, data)

    def run(cmd, *a, **kw):
        if git_fails == "missing":
            raise FileNotFoundError(2, "No such file or directory", "git")
        return subprocess.CompletedProcess(cmd, 128, "", "fatal: detected dubious ownership in repository")
    monkeypatch.setattr(dataimport.subprocess, "run", run)
    with pytest.raises(dataimport.PruneRefused, match="git"):
        dataimport.prune_source(old_install, store)
    assert (old_install / "runs/telemetry.sqlite").exists() and (old_install / "runs" / RUN).exists()


def test_a_tracked_file_below_the_repo_top_is_found(old_install, tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "add", "-f", f"repo/runs/{RUN}/status.json")
    git(tmp_path, "commit", "-q", "-m", "base")
    store, _ = do_import(old_install, tmp_path / "data")
    with pytest.raises(dataimport.PruneRefused, match=f"runs/{RUN}/status.json"):
        dataimport.prune_source(old_install, store)
    assert (old_install / "runs/telemetry.sqlite").exists()


@pytest.mark.skipif(os.geteuid() == 0, reason="root deletes whatever the directory mode")
def test_a_deletion_error_is_reported_with_what_was_deleted(old_install, tmp_path, monkeypatch, capsys):
    data = tmp_path / "data"
    monkeypatch.setenv("PILOT_DATA_DIR", str(data))
    run = old_install / "runs" / RUN
    run.chmod(0o555)                                       # nothing directly in it can be removed
    try:
        assert cli.main(["data", "import", "--from", str(old_install), "--prune-source"]) == 1
        out = capsys.readouterr().out
        assert f"deleted {old_install / 'runs/telemetry.sqlite'}" in out
        assert f"deleted {old_install / 'runs/pilot-settings.json'}" in out
        assert f"not deleted {run}:" in out
        assert not (old_install / "runs/telemetry.sqlite").exists() and (run / "events.jsonl").exists()
        with pytest.raises(dataimport.PruneIncomplete) as e:     # again: only the run directory is left
            dataimport.prune_source(old_install, open_store(data))
        assert e.value.deleted == [] and [f for f in e.value.failed if f.startswith(f"{run}:")], e.value.failed
    finally:
        run.chmod(0o755)
