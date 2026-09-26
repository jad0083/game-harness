"""Telemetry store: every pilot run's events, decisions (with full traces) and game metrics in one
SQLite file (`runs/telemetry.sqlite`), grouped by campaign (one save/playthrough across many runs
and models). The JSONL logs in `runs/<id>/` stay the raw record; `rebuild()` recreates the
database from them at any time.

Outcome scoring joins each decision to the empire's metrics some in-game months later, so the
model (and the human) can see whether a directive actually worked.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

SCHEMA = """
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
    date TEXT, source TEXT,         -- 'decision' | 'retrospective'
    text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS plans_campaign ON plans(campaign_id, t);
CREATE TABLE IF NOT EXISTS strategies (
    campaign_id TEXT, run_id TEXT NOT NULL, t REAL, date TEXT, trigger TEXT, model TEXT, data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS strategies_campaign ON strategies(campaign_id, t);
"""

# Numbers compared N months after a decision (from the governor's metrics events).
SCORED = ("systems", "planets", "pops", "techs_known", "military_power", "economy_power", "tech_power")


def month_index(date: str | None) -> int | None:
    """'2204.09.01' → months since year 0; None for dates in other formats (e.g. GC4 'Jul 2333')."""
    try:
        y, m, *_ = (int(x) for x in (date or "").split("."))
        return y * 12 + m - 1
    except ValueError:
        return None


class Telemetry:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = threading.Lock()
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)
        if "title" not in {r[1] for r in self.db.execute("PRAGMA table_info(campaigns)")}:
            self.db.execute("ALTER TABLE campaigns ADD COLUMN title TEXT")     # the empire's name, for people
        cols = {r[1] for r in self.db.execute("PRAGMA table_info(decisions)")}
        if "model" not in cols:       # added later: the model that made each decision (it can change mid-run)
            self.db.execute("ALTER TABLE decisions ADD COLUMN model TEXT")
        for col in ("model_version", "thinking"):   # the release that answered (aliases resolve), thinking level
            if col not in cols:
                self.db.execute(f"ALTER TABLE decisions ADD COLUMN {col} TEXT")

    def close(self) -> None:
        self.db.close()

    def _exec(self, sql: str, args: tuple = ()) -> None:
        with self._lock:
            self.db.execute(sql, args)

    def query(self, sql: str, args: tuple = ()) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self.db.execute(sql, args).fetchall()]

    # -- writing ----------------------------------------------------------------------------------

    def start_run(self, run_id: str, game: str, model: str, settings: dict, t: float) -> None:
        self._exec("INSERT OR IGNORE INTO runs(id, game, model, settings, started, status) VALUES (?,?,?,?,?,?)",
                   (run_id, game, model, json.dumps(settings, default=str), t, "running"))

    def set_campaign(self, run_id: str, game: str, name: str, t: float, title: str = "") -> str:
        cid = f"{game}/{name}"
        self._exec("INSERT OR IGNORE INTO campaigns(id, game, name, created) VALUES (?,?,?,?)", (cid, game, name, t))
        if title:
            self._exec("UPDATE campaigns SET title=? WHERE id=?", (title, cid))
        self._exec("UPDATE runs SET campaign_id=? WHERE id=?", (cid, run_id))
        self._exec("UPDATE decisions SET campaign_id=? WHERE run_id=? AND campaign_id IS NULL", (cid, run_id))
        self._exec("UPDATE metrics SET campaign_id=? WHERE run_id=? AND campaign_id IS NULL", (cid, run_id))
        self._exec("UPDATE plans SET campaign_id=? WHERE run_id=? AND campaign_id IS NULL", (cid, run_id))
        self._exec("UPDATE strategies SET campaign_id=? WHERE run_id=? AND campaign_id IS NULL", (cid, run_id))
        return cid

    def _title_from_trace(self, run_id: str, tr: dict) -> None:
        """Older runs recorded no empire name; the briefing's first line in the trace has it."""
        cid = self._campaign_of(run_id)
        if not cid or not tr:
            return
        rows = self.query("SELECT title FROM campaigns WHERE id=?", (cid,))
        if not rows or rows[0]["title"]:
            return
        for st in tr.get("steps", []):
            if st.get("type") == "prompt":
                m = re.search(r"^# \S+ — (.+?) \(country \d+", st.get("text", ""), re.MULTILINE)
                if m:
                    self._exec("UPDATE campaigns SET title=? WHERE id=?", (m.group(1), cid))
                return

    def _campaign_of(self, run_id: str) -> str | None:
        rows = self.query("SELECT campaign_id FROM runs WHERE id=?", (run_id,))
        return rows[0]["campaign_id"] if rows else None

    def record(self, run_id: str, ev: dict, trace: dict | None = None) -> None:
        """Store one event; `trace` (the full decision trace) accompanies 'trace' events."""
        kind, t = ev.get("kind", ""), ev.get("t", 0.0)
        data = {k: v for k, v in ev.items() if k not in ("t", "kind")}
        self._exec("INSERT INTO events(run_id, t, kind, data) VALUES (?,?,?,?)",
                   (run_id, t, kind, json.dumps(data, ensure_ascii=False, default=str)))
        if kind == "run_start":
            self.start_run(run_id, data.get("game", ""), data.get("model", ""), data, t)
        elif kind == "campaign":
            self.set_campaign(run_id, data.get("game", ""), data.get("name", ""), t, data.get("title") or "")
        elif kind == "run_end":
            self._exec("UPDATE runs SET ended=?, status='ended' WHERE id=?", (t, run_id))
        elif kind == "metrics":
            self._exec("INSERT OR REPLACE INTO metrics(run_id, campaign_id, t, date, month, data) VALUES (?,?,?,?,?,?)",
                       (run_id, self._campaign_of(run_id), t, data.get("date"), month_index(data.get("date")),
                        json.dumps(data, default=str)))
        elif kind == "plan":
            self._exec("INSERT INTO plans(campaign_id, run_id, t, date, source, text) VALUES (?,?,?,?,?,?)",
                       (self._campaign_of(run_id), run_id, t, data.get("date"), data.get("source"), data.get("text", "")))
        elif kind == "strategy":
            self._exec("INSERT INTO strategies(campaign_id, run_id, t, date, trigger, model, data) VALUES (?,?,?,?,?,?,?)",
                       (self._campaign_of(run_id), run_id, t, data.get("date"), data.get("trigger"), data.get("model"),
                        json.dumps({**(data.get("strategy") or {}), "reason": data.get("reason", "")}, default=str)))
        elif kind == "trace":
            tr = trace or {}
            self._title_from_trace(run_id, tr)
            decision = data.get("decision") or tr.get("decision") or data.get("situation")
            self._exec(
                "INSERT OR REPLACE INTO decisions(run_id, episode, campaign_id, t, date, month, trigger, decision, reason,"
                " outcome, current, tokens_in, tokens_out, seconds, trace, model, model_version, thinking)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (run_id, data.get("episode"), self._campaign_of(run_id), t, data.get("date"), month_index(data.get("date")),
                 data.get("trigger"), decision, data.get("reason") or data.get("situation"), data.get("outcome"),
                 data.get("current"), data.get("tokens_in"), data.get("tokens_out"), data.get("seconds"),
                 json.dumps(tr, ensure_ascii=False, default=str) if tr else None,
                 data.get("model") or tr.get("model"),
                 data.get("model_version") or tr.get("model_version"), data.get("thinking_level") or tr.get("thinking_level")))

    # -- outcome scoring ----------------------------------------------------------------------

    def score(self, campaign_id: str, after_months: int = 12) -> int:
        """Fill `decisions.result` with metric deltas `after_months` later (where that far is known)."""
        mets = self.query("SELECT run_id, month, data FROM metrics WHERE campaign_id=? AND month IS NOT NULL "
                          "ORDER BY month", (campaign_id,))
        if not mets:
            return 0
        scored = 0
        for d in self.query("SELECT run_id, episode, month FROM decisions WHERE campaign_id=? AND month IS NOT NULL",
                            (campaign_id,)):
            # same run only (a reloaded older save repeats months), and an end point close to the mark
            run = [(m["month"], json.loads(m["data"])) for m in mets if m["run_id"] == d["run_id"]]
            start = next((x for mo, x in run if mo >= d["month"]), None)
            end = next((x for mo, x in run if d["month"] + after_months <= mo <= d["month"] + after_months + 3), None)
            if not start or not end:
                continue
            delta = {k: round((end.get(k) or 0) - (start.get(k) or 0), 2) for k in SCORED}
            delta["months"] = after_months
            delta["deficits_after"] = sorted(r for r, v in (end.get("net") or {}).items() if v < 0)
            self._exec("UPDATE decisions SET result=? WHERE run_id=? AND episode=?",
                       (json.dumps(delta), d["run_id"], d["episode"]))
            scored += 1
        return scored

    def latest_plan(self, campaign_id: str) -> str:
        rows = self.query("SELECT text FROM plans WHERE campaign_id=? ORDER BY t DESC LIMIT 1", (campaign_id,))
        return rows[0]["text"] if rows else ""

    def latest_strategy(self, campaign_id: str) -> dict | None:
        rows = self.query("SELECT data FROM strategies WHERE campaign_id=? ORDER BY t DESC LIMIT 1", (campaign_id,))
        return json.loads(rows[0]["data"]) if rows else None

    def strategy_history(self, campaign_id: str, limit: int = 50) -> list[dict]:
        rows = self.query("SELECT date, trigger, model, t, data FROM strategies WHERE campaign_id=? ORDER BY t DESC LIMIT ?",
                          (campaign_id, limit))
        return [{"date": r["date"], "trigger": r["trigger"], "model": r["model"], "t": r["t"],
                 "strategy": json.loads(r["data"])} for r in rows]

    def metrics_rows(self, campaign_id: str) -> list[dict]:
        return [json.loads(r["data"]) for r in
                self.query("SELECT data FROM metrics WHERE campaign_id=? AND month IS NOT NULL ORDER BY month", (campaign_id,))]

    def past_outcomes(self, campaign_id: str, limit: int = 12) -> str:
        """Text table of this campaign's earlier directive changes and what followed, for the model."""
        rows = self.query(
            "SELECT date, decision, current, trigger, result FROM decisions WHERE campaign_id=? AND decision IS NOT NULL"
            " AND decision != 'keep' ORDER BY month DESC LIMIT ?", (campaign_id, limit))
        if not rows:
            return "No earlier directive changes in this campaign."
        out = ["date | directive (from) | trigger | 12 months later"]
        for r in rows:
            res = json.loads(r["result"]) if r["result"] else None
            after = ("not yet known" if not res else
                     ", ".join(f"{k} {v:+g}" for k, v in res.items() if k in SCORED)
                     + (f"; deficits: {', '.join(res['deficits_after'])}" if res.get("deficits_after") else ""))
            out.append(f"{r['date']} | {r['decision']} (from {r['current'] or 'none'}) | {r['trigger']} | {after}")
        return "\n".join(out)

    # -- rebuild ------------------------------------------------------------------------------

    def rebuild(self, runs_dir: Path) -> int:
        """Recreate every table from runs/<id>/events.jsonl and traces/. Returns the runs loaded."""
        n = 0
        with self._lock:
            self.db.execute("BEGIN")
        try:
            with self._lock:
                for table in ("events", "decisions", "metrics", "plans", "strategies", "runs", "campaigns"):
                    self.db.execute(f"DELETE FROM {table}")  # fixed table names
            for d in sorted(p for p in runs_dir.iterdir() if (p / "events.jsonl").exists()):
                with open(d / "events.jsonl", encoding="utf-8") as f:
                    for line in f:
                        try:
                            ev: dict[str, Any] = json.loads(line)
                        except ValueError:
                            continue
                        trace = None
                        if ev.get("kind") == "trace" and ev.get("file") and (d / ev["file"]).exists():
                            try:
                                trace = json.loads((d / ev["file"]).read_text(encoding="utf-8"))
                            except ValueError:
                                trace = None           # a corrupt trace file: keep the decision row
                        self.record(d.name, ev, trace)
                n += 1
            for c in self.query("SELECT id FROM campaigns"):
                self.score(c["id"])
            with self._lock:
                self.db.execute("COMMIT")
        except BaseException:
            with self._lock:
                self.db.execute("ROLLBACK")
            raise
        return n
