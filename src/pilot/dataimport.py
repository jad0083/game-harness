"""pilot data import / check / --prune-source (data platform design, rulings 11-12; plan rulings P4, P5):
an install from before the data platform, copied into the store and the data directory.

    runs/telemetry.sqlite            campaigns, runs, events, decisions, metrics, plans, strategies
                                     (opened read-only; never written)
    runs/<id>/events.jsonl           events the telemetry file lacks, by (run_id, t, kind)
    runs/<id>/traces/NNNN.json       decisions.trace where it is empty
    runs/<id>/status.json            run_state
    runs/<id>/latest.jpg, frames/    <data>/frames/<id>/ (never over an existing file)
    corpora/<game>/learned/          learned_notes, learned_screens, episodes, ledger; then the generated
                                     <data>/learned/<game>/
    games/<game>/journal.md          the "## Pilot log" entries, under campaign <game>/imported-journal
    runs/pilot-settings.json, model-usage.json, orders/*.json   settings 'prefs', model_usage, standing_orders
    runs/dashboard.key, dashboard.carryover                     <data>/secrets/ (0600; the directory 0700)

The import is idempotent: what the store already holds is skipped by key, so it can run again after new
runs were recorded. A damaged item (a truncated JSONL line, an unparseable file, a learned screen the store
cannot hold) is named in Report.skipped and the import goes on. `check` reads the source the same way and
lists what the store or the data directory lacks. `prune_source` deletes the imported runtime files and
nothing else. The data directory may be <root>/runs itself (the default install imports in place).
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time
import tomllib
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from .auth import CARRY_FILE, KEY_FILE, SECRETS_DIR, _private_dir
from .learned_files import NOTE_FILES, _screen_block, write_learned_dir

PLATFORM_DIRS = frozenset({"frames", "learned", "secrets"})   # the data directory's own (when it is <root>/runs)
OLD_DIRS = frozenset({"orders"})                               # old runs/ directories that are not runs
RUN_FILES = frozenset({"events.jsonl", "status.json", "traces", "frames", "latest.jpg"})   # all a run dir held
JOURNALS = {"stellaris": "stellaris", "civ6": "civ6", "terran-2329": "galciv4"}   # games/<dir> -> its game
SECRET_FILES = (KEY_FILE, CARRY_FILE)
OLD_FILES = ("telemetry.sqlite", "telemetry.sqlite-wal", "telemetry.sqlite-shm", "pilot-settings.json",
             "model-usage.json")
TABLES = ("campaigns", "runs", "events", "decisions", "metrics", "plans", "strategies", "run_state", "learned_notes",
          "learned_screens", "episodes", "ledger", "journal", "settings", "model_usage", "standing_orders")
# telemetry tables copied from the old file: (key, columns); a column the old file lacks is read as NULL
TELEMETRY = {
    "campaigns": (("id",), ("id", "game", "name", "created", "title")),
    "runs": (("id",), ("id", "campaign_id", "game", "model", "settings", "started", "ended", "status")),
    "decisions": (("run_id", "episode"), ("run_id", "episode", "campaign_id", "t", "date", "month", "trigger",
                                          "decision", "reason", "outcome", "current", "tokens_in", "tokens_out",
                                          "seconds", "trace", "result", "model", "model_version", "thinking")),
    "metrics": (("run_id", "date"), ("run_id", "campaign_id", "t", "date", "month", "data")),
    "plans": (("run_id", "t"), ("campaign_id", "run_id", "t", "date", "source", "text")),
    "strategies": (("run_id", "t"), ("campaign_id", "run_id", "t", "date", "trigger", "model", "data")),
}
LABEL = {"campaigns": "campaign", "runs": "run", "decisions": "decision", "metrics": "metrics", "plans": "plan",
         "strategies": "strategy"}
SCREEN_KEYS = frozenset({"description", "template", "template_roi", "template_threshold", "auto_dismiss",
                         "dismiss_click", "dismiss_key", "learned_by", "learned_run", "disabled_reason"})
# one learned note as learning.py wrote it: "- text  \n  _why:_ why _(model, YYYY-MM-DD)_", the suffix
# missing on rules corrected by hand
NOTE_RE = re.compile(r"(?P<text>.+?)  \n  _why:_ (?P<why>.+?)"
                     r"(?: _\((?P<model>[^()\n]+), (?P<date>\d{4}-\d{2}-\d{2})\)_)?\n*", re.DOTALL)
SECTION_END = re.compile(r"#{1,2} ")       # the next level-1 or level-2 heading ends the pilot log
STAMP = re.compile(r"\*\*(.+?)\*\*: ")
BATCH = 500
FILL_TRACE = "UPDATE decisions SET trace=? WHERE run_id=? AND episode=? AND trace IS NULL"


@dataclass
class Report:
    added: dict[str, int] = field(default_factory=dict)    # rows added per table, traces filled, secrets copied
    skipped: list[str] = field(default_factory=list)       # damaged or unimportable items, with the reason
    frames: int = 0                                        # frame files copied


class PruneRefused(RuntimeError):
    """prune_source would delete a git-tracked path, or cannot tell."""


# ---------------------------------------------------------------- reading the source

def _rel(root: Path, p: Path) -> str:
    try:
        return p.relative_to(root).as_posix()
    except ValueError:
        return str(p)


def _number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _text(v):
    """A JSON value as a TEXT column holds it: strings as they are, other values as JSON."""
    return v if v is None or isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)


def _load_json(path: Path, root: Path, skipped: list[str]):
    """A JSON file's value, or None (with the reason in `skipped`) when it cannot be read."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as e:
        skipped.append(f"{_rel(root, path)}: cannot be read ({e})")
    except ValueError as e:
        skipped.append(f"{_rel(root, path)}: not valid JSON ({e})")
    return None


def _jsonl(path: Path, root: Path, skipped: list[str]) -> Iterator[tuple[int, dict]]:
    """(line number, object) for each line that is a JSON object; blank lines are passed over."""
    if not path.is_file():
        return
    try:
        lines = path.read_text(encoding="utf-8").split("\n")
    except (OSError, UnicodeDecodeError) as e:
        skipped.append(f"{_rel(root, path)}: cannot be read ({e})")
        return
    for n, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except ValueError as e:
            skipped.append(f"{_rel(root, path)} line {n}: not valid JSON ({e})")
            continue
        if not isinstance(obj, dict):
            skipped.append(f"{_rel(root, path)} line {n}: not a JSON object")
            continue
        yield n, obj


@contextlib.contextmanager
def _old_db(root: Path, skipped: list[str]):
    """runs/telemetry.sqlite opened read-only (never written; SQLite may leave empty -wal/-shm files
    beside a WAL file), or None when there is none or it cannot be read."""
    path = root / "runs" / "telemetry.sqlite"
    if not path.is_file():
        yield None
        return
    db = None
    try:
        db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        db.execute("SELECT name FROM sqlite_master LIMIT 1").fetchall()
    except sqlite3.Error as e:
        if db is not None:
            db.close()
        skipped.append(f"{_rel(root, path)}: cannot be read ({e})")
        yield None
        return
    try:
        yield db
    finally:
        db.close()


def _quoted(cols: tuple[str, ...]) -> str:
    return ", ".join(f'"{c}"' for c in cols)          # fixed column names only ("trigger" is a keyword)


def _columns(db: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in db.execute(f"PRAGMA table_info({table})")}     # fixed table names only


def _old_rows(db: sqlite3.Connection, table: str, cols: tuple[str, ...]):
    """The old table's rows in `cols` order (NULL for a column the file lacks); none when the table is missing."""
    have = _columns(db, table)
    if not have:
        return iter(())
    sel = ", ".join(f'"{c}"' if c in have else "NULL" for c in cols)
    return db.execute(f"SELECT {sel} FROM {table} ORDER BY rowid")


def _old_events(db: sqlite3.Connection, root: Path, skipped: list[str]) -> dict[str, list[tuple]]:
    """The old file's events per run, (run_id, t, kind, data) with data a JSON object, in recorded order."""
    out: dict[str, list[tuple]] = {}
    for rid, t, kind, data in _old_rows(db, "events", ("run_id", "t", "kind", "data")):
        try:
            ok = isinstance(json.loads(data), dict)
        except (TypeError, ValueError):
            ok = False
        why = "" if ok else "data is not a JSON object"
        why = why or ("" if _number(t) and isinstance(kind, str) else "no t or kind")
        if why:
            skipped.append(f"runs/telemetry.sqlite event {rid} t={t} {kind}: {why}")
            continue
        out.setdefault(rid, []).append((rid, t, kind, data))
    return out


def _is_run(d: Path) -> bool:
    return (d / "events.jsonl").is_file() or (d / "status.json").is_file()


def _run_dirs(root: Path, data_dir: Path, skipped: list[str]) -> list[Path]:
    """The run directories under root/runs; other directories are named in `skipped`, except the data
    directory's own (frames/, learned/, secrets/ when it is root/runs) and the old orders/."""
    runs = root / "runs"
    if not runs.is_dir():
        return []
    out = []
    for d in sorted(runs.iterdir()):
        if not d.is_dir() or d.name in OLD_DIRS or d.resolve() == data_dir.resolve():
            continue
        if d.name in PLATFORM_DIRS and runs.resolve() == data_dir.resolve():
            continue
        if _is_run(d):
            out.append(d)
        else:
            skipped.append(f"{_rel(root, d)}: not a run directory")
    return out


def _run_events(d: Path, root: Path, skipped: list[str]) -> list[tuple[int, dict]]:
    """(line number, event) of the run log's events that can be recorded."""
    out = []
    for n, ev in _jsonl(d / "events.jsonl", root, skipped):
        if not _number(ev.get("t")) or not isinstance(ev.get("kind"), str):
            skipped.append(f"{_rel(root, d / 'events.jsonl')} line {n}: no t or kind")
        elif ev["kind"] == "trace" and not (isinstance(ev.get("episode"), int) and not isinstance(ev["episode"], bool)):
            skipped.append(f"{_rel(root, d / 'events.jsonl')} line {n}: a trace event without an episode")
        else:
            out.append((n, ev))
    return out


def _run_traces(d: Path, root: Path, skipped: list[str]) -> dict[int, dict]:
    """traces/NNNN.json by episode (a strategy review's is negative: -001.json)."""
    out = {}
    for p in sorted((d / "traces").glob("*.json")):
        try:
            episode = int(p.stem)
        except ValueError:
            skipped.append(f"{_rel(root, p)}: not a trace file name")
            continue
        tr = _load_json(p, root, skipped)
        if tr is None:
            continue
        if not isinstance(tr, dict):
            skipped.append(f"{_rel(root, p)}: not a JSON object")
            continue
        out[episode] = tr
    return out


def _run_status(d: Path, root: Path, skipped: list[str]) -> dict | None:
    path = d / "status.json"
    if not path.is_file():
        return None
    st = _load_json(path, root, skipped)
    if st is not None and not isinstance(st, dict):
        skipped.append(f"{_rel(root, path)}: not a JSON object")
        return None
    return st


def _run_frames(d: Path) -> list[tuple[str, Path]]:
    """(name, file) of the run's frames: latest.jpg beside the log (as the old EventLog wrote it), then
    frames/*.jpg (a frames/latest.jpg only when there is no other)."""
    found: dict[str, Path] = {}
    if (d / "latest.jpg").is_file():
        found["latest.jpg"] = d / "latest.jpg"
    for p in sorted((d / "frames").glob("*.jpg")):
        if p.is_file():
            found.setdefault(p.name, p)
    return sorted(found.items())


def _notes(path: Path, root: Path, skipped: list[str]) -> list[dict]:
    """The learned notes of strategy.md or controls.md, in file order."""
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        skipped.append(f"{_rel(root, path)}: cannot be read ({e})")
        return []
    if text.startswith("- "):
        text = "\n\n" + text
    out, first = [], {}
    for i, chunk in enumerate(text.split("\n\n- ")[1:], 1):
        m = NOTE_RE.fullmatch(chunk)
        if not m:
            skipped.append(f"{_rel(root, path)} item {i}: not a learned note ({chunk.strip()[:60]!r})")
            continue
        note = m["text"].strip()
        if note in first:                   # the store holds one note per text (the first)
            skipped.append(f"{_rel(root, path)} item {i}: the same text as item {first[note]}, kept once")
            continue
        first[note] = i
        out.append({"text": note, "why": m["why"].strip(), "model": m["model"], "t": m["date"]})
    return out


def _screen(name: str, sc, corpus_dir: Path) -> tuple[dict | None, str]:
    """One [screens.<name>] table of an old learned manifest as a learned_screens row, or why it cannot be."""
    if not isinstance(sc, dict):
        return None, "not a table"
    extra = sorted(set(sc) - SCREEN_KEYS)
    if extra:
        return None, f"has {', '.join(extra)}, which the store does not hold"
    roi = sc.get("template_roi")
    if not (isinstance(roi, list) and len(roi) == 4 and all(_number(v) for v in roi)):
        return None, "no valid template_roi (four numbers)"
    if not _number(sc.get("template_threshold")):
        return None, "no valid template_threshold"
    click, key = sc.get("dismiss_click"), sc.get("dismiss_key")
    if click is not None:
        if not (isinstance(click, list) and len(click) == 2 and all(_number(v) for v in click)):
            return None, "dismiss_click is not two numbers"
        action = {"click": click}
    elif isinstance(key, str):
        action = {"key": key}
    else:
        return None, "no dismiss_click or dismiss_key"
    template = sc.get("template")
    if not isinstance(template, str):
        return None, "no template"
    png = None
    for p in (corpus_dir / template, corpus_dir / "learned" / template, corpus_dir / "learned/templates" / f"{name}.png"):
        if p.resolve().is_relative_to(corpus_dir.resolve()) and p.is_file():
            png = p.read_bytes()
            break
    if png is None:
        return None, f"template file {template} missing"
    row = {"name": name, "description": _text(sc.get("description")) or "",
           "roi": "[" + ", ".join(repr(v) for v in roi) + "]", "threshold": float(sc["template_threshold"]),
           "auto_dismiss": 1 if sc.get("auto_dismiss") is True else 0, "action": json.dumps(action), "png": png,
           "learned_by": _text(sc.get("learned_by")), "run_id": _text(sc.get("learned_run")),
           "disabled_reason": _text(sc.get("disabled_reason"))}
    try:
        tomllib.loads(_screen_block(row))
    except (ValueError, TypeError, KeyError, IndexError):
        return None, "cannot be written as TOML"
    return row, ""


def _screens(ld: Path, root: Path, skipped: list[str]) -> list[dict]:
    path = ld / "manifest.toml"
    if not path.is_file():
        return []
    rel = _rel(root, path)
    try:
        doc = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as e:
        skipped.append(f"{rel}: cannot be read ({e})")
        return []
    except tomllib.TOMLDecodeError as e:
        skipped.append(f"{rel}: not valid TOML ({e})")
        return []
    for extra in sorted(set(doc) - {"screens"}):
        skipped.append(f"{rel}: [{extra}] not imported (the store holds learned screens only)")
    screens = doc.get("screens", {})
    if not isinstance(screens, dict):
        skipped.append(f"{rel}: screens is not a table")
        return []
    out = []
    for name, sc in screens.items():
        row, why = _screen(name, sc, ld.parent)
        if row is None:
            skipped.append(f"{rel}: screen {name}: {why}")
        else:
            out.append(row)
    return out


def _episodes(ld: Path, root: Path, skipped: list[str]) -> list[tuple]:
    """episodes.jsonl rows as (t, date, situation, decision, outcome, model, run_id); the store holds one
    episode per (t, situation), so a repeat is named and left out."""
    out, first = [], {}
    for n, e in _jsonl(ld / "episodes.jsonl", root, skipped):
        row = tuple(_text(e.get(k)) for k in ("t", "date", "situation", "decision", "outcome", "model", "run"))
        if (row[0], row[2]) in first:
            skipped.append(f"{_rel(root, ld / 'episodes.jsonl')} line {n}: the same t and situation as line "
                           f"{first[row[0], row[2]]}, kept once")
            continue
        first[row[0], row[2]] = n
        out.append(row)
    return out


def _ledger(ld: Path, root: Path, skipped: list[str]) -> list[tuple]:
    """ledger.jsonl rows as (t, kind, data): data is the rest of the record, as LearnedStore stores it."""
    out = []
    for _, rec in _jsonl(ld / "ledger.jsonl", root, skipped):
        rest = {k: v for k, v in rec.items() if k not in ("t", "kind")}
        out.append((_text(rec.get("t")), _text(rec.get("kind")), json.dumps(rest, ensure_ascii=False, default=str)))
    return out


def _journal(path: Path, root: Path, skipped: list[str]) -> list[tuple[str, str]]:
    """The "## Pilot log" entries of a journal as (date, text). Journal.note wrote `- {stamp}{text}` where the
    text keeps its own newlines, so an entry runs to the next `- ` line or the end of the section."""
    try:
        lines = path.read_text(encoding="utf-8").split("\n")
    except (OSError, UnicodeDecodeError) as e:
        skipped.append(f"{_rel(root, path)}: cannot be read ({e})")
        return []
    start = next((i for i, ln in enumerate(lines) if ln.strip() == "## Pilot log"), None)
    if start is None:
        return []
    entries: list[list[str]] = []
    end = len(lines)
    for i in range(start + 1, len(lines)):
        line = lines[i]
        if SECTION_END.match(line):
            end = i
            break
        if line.startswith("- "):
            entries.append([line[2:]])
        elif entries:                   # before the first entry: the "Entries written by the pilot app" line
            entries[-1].append(line)
    after = sum(1 for ln in lines[end + 1:] if ln.startswith("- "))
    if after:
        skipped.append(f"{_rel(root, path)}: the pilot log ends at line {end + 1} (a heading); "
                       f"{after} list items after it are not imported")
    out = []
    for e in entries:
        body = "\n".join(e).rstrip()
        m = STAMP.match(body)
        out.append((m[1], body[m.end():]) if m else ("", body))
    return out


def _journals(root: Path, skipped: list[str]) -> list[tuple]:
    """Journal rows (campaign_id, game, t, date, text) of the pilot's default journals (plan ruling P4);
    games/<game>-<leader>/ journals are hand-written documentation and stay out."""
    rows = []
    for dirname, game in JOURNALS.items():
        path = root / "games" / dirname / "journal.md"
        if path.is_file():
            rows += [(f"{game}/imported-journal", game, float(i), d, t)
                     for i, (d, t) in enumerate(_journal(path, root, skipped))]
    return rows


def _prefs(root: Path, skipped: list[str]) -> dict | None:
    path = root / "runs/pilot-settings.json"
    if not path.is_file():
        return None
    d = _load_json(path, root, skipped)
    if d is not None and not isinstance(d, dict):
        skipped.append(f"{_rel(root, path)}: not a JSON object")
        return None
    return d


def _usage(root: Path, skipped: list[str]) -> list[tuple[str, str, int]]:
    path = root / "runs/model-usage.json"
    if not path.is_file():
        return []
    d = _load_json(path, root, skipped)
    if d is None:
        return []
    if not isinstance(d, dict):
        skipped.append(f"{_rel(root, path)}: not a JSON object")
        return []
    rows = []
    for day, counts in d.items():
        if not isinstance(counts, dict):
            skipped.append(f"{_rel(root, path)}: {day}: not an object of counts")
            continue
        for model, n in counts.items():
            if isinstance(n, int) and not isinstance(n, bool) and n >= 0:
                rows.append((day, model, n))
            else:
                skipped.append(f"{_rel(root, path)}: {day} {model}: not a count")
    return rows


def _orders(root: Path, store, skipped: list[str]) -> dict[str, list[str]]:
    """runs/orders/<campaign>.json by campaign id: the file name is the id with [^A-Za-z0-9_.-] made '_',
    mapped back through the campaigns the store knows (the file stem when none matches)."""
    files = sorted((root / "runs/orders").glob("*.json"))
    if not files:
        return {}
    ids = [r["id"] for r in store.query("SELECT id FROM campaigns ORDER BY id")] + ["no-campaign"]
    by_name: dict[str, str] = {}
    for cid in ids:
        by_name.setdefault(re.sub(r"[^A-Za-z0-9_.-]", "_", cid), cid)
    out = {}
    for p in files:
        orders = _load_json(p, root, skipped)
        if orders is None:
            continue
        if not (isinstance(orders, list) and all(isinstance(o, str) for o in orders)):
            skipped.append(f"{_rel(root, p)}: not a list of orders")
            continue
        out[by_name.get(p.stem, p.stem)] = orders
    return out


# ---------------------------------------------------------------- import

def _keys(store, table: str, key: tuple[str, ...], where: str = "", args: tuple = ()) -> set[tuple]:
    """The key tuples the store holds (loaded once, compared in memory: NULL parts compare equal too)."""
    return {tuple(r[c] for c in key) for r in store.query(f"SELECT {_quoted(key)} FROM {table} {where}", args)}


def _counts(store) -> dict[str, int]:
    out = {t: store.query(f"SELECT COUNT(*) AS n FROM {t}")[0]["n"] for t in TABLES}
    out["traces"] = store.query("SELECT COUNT(*) AS n FROM decisions WHERE trace IS NOT NULL")[0]["n"]
    return out


def _telemetry(root: Path, store, report: Report) -> None:
    """The old telemetry tables, row by row: what the store has by key is left as it is, except that a
    decision stored without a trace takes the old file's."""
    with _old_db(root, report.skipped) as db:
        if db is None:
            return
        with store.transaction():
            for table, (key, cols) in TELEMETRY.items():
                have = _keys(store, table, key)
                at = [cols.index(k) for k in key]
                sql = f"INSERT OR IGNORE INTO {table}({_quoted(cols)}) VALUES ({', '.join('?' * len(cols))})"
                batch, traces = [], []
                for row in _old_rows(db, table, cols):
                    k = tuple(row[i] for i in at)
                    if k not in have:
                        batch.append(tuple(row))
                    elif table == "decisions" and row[cols.index("trace")] is not None:
                        traces.append((row[cols.index("trace")], *k))
                    if len(batch) >= BATCH:
                        store.executemany(sql, batch)
                        batch = []
                    if len(traces) >= BATCH:
                        store.executemany(FILL_TRACE, traces)
                        traces = []
                store.executemany(sql, batch)
                store.executemany(FILL_TRACE, traces)
            for rid, rows in _old_events(db, root, report.skipped).items():
                have = _keys(store, "events", ("t", "kind"), "WHERE run_id=?", (rid,))
                store.executemany("INSERT INTO events(run_id, t, kind, data) VALUES (?,?,?,?)",
                                  [r for r in rows if (r[1], r[2]) not in have])


# rows an event derives in Telemetry.record that may exist already (from the telemetry file): then only the
# event is added, so a decision keeps its outcome score and a plan is not doubled
_DERIVED = {"plan": ("plans", "run_id=? AND t=?"), "strategy": ("strategies", "run_id=? AND t=?"),
            "trace": ("decisions", "run_id=? AND episode=?"), "metrics": ("metrics", "run_id=? AND date IS ?")}


def _record(store, rid: str, ev: dict, trace: dict | None) -> None:
    kind, t = ev["kind"], ev["t"]
    if kind in _DERIVED:
        table, where = _DERIVED[kind]
        second = {"plan": t, "strategy": t, "trace": ev.get("episode"), "metrics": ev.get("date")}[kind]
        if store.query(f"SELECT 1 FROM {table} WHERE {where} LIMIT 1", (rid, second)):
            data = {k: v for k, v in ev.items() if k not in ("t", "kind")}
            store._exec("INSERT INTO events(run_id, t, kind, data) VALUES (?,?,?,?)",
                        (rid, t, kind, json.dumps(data, ensure_ascii=False, default=str)))
            return
    store.record(rid, ev, trace)


def _place(tmp: str, dst: Path) -> bool:
    """Give a finished temp file the name `dst` unless that exists: a hard link fails when `dst` appeared
    meanwhile; on a filesystem without hard links, a replace after one more look."""
    try:
        os.link(tmp, dst)
        return True
    except FileExistsError:
        return False
    except OSError:
        if dst.exists():
            return False
        os.replace(tmp, dst)
        return True


def _copy(src: Path, dst: Path) -> bool:
    """Copy a file unless `dst` exists; a reader never sees half a file."""
    if dst.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{dst.name}-", suffix=".tmp", dir=dst.parent)
    os.close(fd)
    try:
        shutil.copy2(src, tmp)
        return _place(tmp, dst)
    finally:
        Path(tmp).unlink(missing_ok=True)


def _runs(root: Path, store, data_dir: Path, report: Report) -> None:
    for d in _run_dirs(root, data_dir, report.skipped):
        rid = d.name
        events = _run_events(d, root, report.skipped)
        traces = _run_traces(d, root, report.skipped)
        status = _run_status(d, root, report.skipped)
        with store.transaction():
            have = _keys(store, "events", ("t", "kind"), "WHERE run_id=?", (rid,))     # once per run
            for n, ev in events:
                if (ev["t"], ev["kind"]) in have:
                    continue
                try:
                    _record(store, rid, ev, traces.get(ev["episode"]) if ev["kind"] == "trace" else None)
                except sqlite3.Error as e:       # one statement failed; the run's transaction goes on
                    report.skipped.append(f"{_rel(root, d / 'events.jsonl')} line {n}: not recorded ({e})")
            decided = _keys(store, "decisions", ("episode",), "WHERE run_id=?", (rid,))
            for episode, tr in traces.items():
                if (episode,) not in decided:
                    report.skipped.append(f"{_rel(root, d)}/traces/{episode:04d}.json: no decision {episode} in the run")
                    continue
                store._exec(FILL_TRACE, (json.dumps(tr, ensure_ascii=False, default=str), rid, episode))
            if status is not None:
                store._exec("INSERT OR IGNORE INTO run_state(run_id, data, updated) VALUES (?,?,?)",
                            (rid, json.dumps(status, default=str), (d / "status.json").stat().st_mtime))
        for name, src in _run_frames(d):
            try:
                report.frames += _copy(src, data_dir / "frames" / rid / name)
            except OSError as e:
                report.skipped.append(f"{_rel(root, src)}: cannot be copied ({e})")


def _learned(root: Path, store, data_dir: Path, report: Report) -> None:
    for ld in sorted((root / "corpora").glob("*/learned")):
        if not ld.is_dir():
            continue
        game = ld.parent.name
        notes = [(kind, n) for kind, (fname, _) in NOTE_FILES.items() for n in _notes(ld / fname, root, report.skipped)]
        screens = _screens(ld, root, report.skipped)
        episodes = _episodes(ld, root, report.skipped)
        ledger = _ledger(ld, root, report.skipped)
        with store.transaction():
            store.executemany("INSERT OR IGNORE INTO learned_notes(game, kind, text, why, model, run_id, t)"
                              " VALUES (?,?,?,?,?,NULL,?)",
                              [(game, kind, n["text"], n["why"], n["model"], n["t"]) for kind, n in notes])
            store.executemany("INSERT OR IGNORE INTO learned_screens(game, name, description, roi, threshold, auto_dismiss,"
                              " action, png, learned_by, run_id, t, disabled_reason) VALUES (?,?,?,?,?,?,?,?,?,?,NULL,?)",
                              [(game, s["name"], s["description"], s["roi"], s["threshold"], s["auto_dismiss"],
                                s["action"], s["png"], s["learned_by"], s["run_id"], s["disabled_reason"])
                               for s in screens])
            have = _keys(store, "episodes", ("t", "situation"), "WHERE game=?", (game,))
            store.executemany("INSERT OR IGNORE INTO episodes(game, t, date, situation, decision, outcome, model,"
                              " run_id) VALUES (?,?,?,?,?,?,?,?)",
                              [(game, *e) for e in episodes if (e[0], e[2]) not in have])
            have = _keys(store, "ledger", ("t", "kind", "data"), "WHERE game=?", (game,))
            store.executemany("INSERT INTO ledger(game, t, kind, data) VALUES (?,?,?,?)",
                              [(game, *r) for r in ledger if r not in have])
        write_learned_dir(store, game, data_dir / "learned" / game)


def _settings(root: Path, store, report: Report) -> None:
    prefs = _prefs(root, report.skipped)
    usage = _usage(root, report.skipped)
    orders = _orders(root, store, report.skipped)
    with store.transaction():
        if prefs is not None and not store.query("SELECT 1 FROM settings WHERE key='prefs'"):
            by = prefs.get("changed_by")
            store._exec("INSERT INTO settings(key, value, changed_by, t) VALUES ('prefs', ?, ?, ?)",
                        (json.dumps(prefs), by if isinstance(by, str) else None,
                         (root / "runs/pilot-settings.json").stat().st_mtime))
        store.executemany("INSERT OR IGNORE INTO model_usage(day, model, count) VALUES (?,?,?)", usage)
        for cid, texts in orders.items():
            if not store.query("SELECT 1 FROM standing_orders WHERE campaign_id=? LIMIT 1", (cid,)):
                store.executemany("INSERT INTO standing_orders(campaign_id, position, text) VALUES (?,?,?)",
                                  [(cid, i, t) for i, t in enumerate(texts)])


def _secrets(root: Path, data_dir: Path, report: Report) -> int:
    """runs/dashboard.key and runs/dashboard.carryover into <data>/secrets/ (0600, the directory 0700); a
    file already there is kept (said in the report when it differs). Returns the files copied."""
    copied = 0
    for name in SECRET_FILES:
        src, dst = root / "runs" / name, data_dir / SECRETS_DIR / name
        if not src.is_file():
            continue
        if dst.exists():
            if dst.read_bytes() != src.read_bytes():
                report.skipped.append(f"runs/{name}: {SECRETS_DIR}/{name} exists and differs; the one in "
                                      f"{SECRETS_DIR}/ is kept and the old file stays")
            continue
        _private_dir(dst.parent)
        fd, tmp = tempfile.mkstemp(prefix=f".{name}-", suffix=".tmp", dir=dst.parent)   # mode 0600
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(src.read_bytes())
            copied += _place(tmp, dst)
        finally:
            Path(tmp).unlink(missing_ok=True)
    return copied


def import_install(root: Path, store, data_dir: Path) -> Report:
    """Copy the install at `root` (a repo checkout from before the data platform) into `store` and
    `data_dir`; the source is only read. Safe to run again: nothing is added twice."""
    root, data_dir = Path(root), Path(data_dir)
    report = Report()
    before = _counts(store)
    _telemetry(root, store, report)
    _runs(root, store, data_dir, report)
    _learned(root, store, data_dir, report)
    rows = _journals(root, report.skipped)
    with store.transaction():
        store.executemany("INSERT OR IGNORE INTO journal(campaign_id, game, t, date, text) VALUES (?,?,?,?,?)", rows)
    _settings(root, store, report)
    secrets_copied = _secrets(root, data_dir, report)
    after = _counts(store)
    report.added = {**{k: after[k] - before[k] for k in after}, "secrets": secrets_copied}
    return report


# ---------------------------------------------------------------- check

def _usage_kept_from() -> str:
    """The oldest day the model guard keeps in model_usage (older days are dropped by design)."""
    from .modelguard import USAGE_DAYS, pacific_day
    return (date.fromisoformat(pacific_day(time.time())) - timedelta(days=USAGE_DAYS - 1)).isoformat()


def _fmt(key: tuple) -> str:
    return " ".join(str(k) for k in key)


def check(root: Path, store, data_dir: Path) -> list[str]:
    """What the store and the data directory lack of the install at `root`, one line per item; [] when the
    copy is complete. Items the import skips as damaged are not differences (the import names them)."""
    root, data_dir = Path(root), Path(data_dir)
    diffs: list[str] = []
    ignored: list[str] = []
    want_decisions: set[tuple] = set()
    want_traces: set[tuple] = set()
    want_events: dict[str, set] = {}
    with _old_db(root, ignored) as db:
        if db is not None:
            for table, (key, _) in TELEMETRY.items():
                want = {tuple(r) for r in _old_rows(db, table, key)}
                if table == "decisions":            # with the decisions of the run logs, below
                    want_decisions |= want
                    continue
                diffs += [f"{LABEL[table]} {_fmt(k)} missing" for k in sorted(want - _keys(store, table, key), key=str)]
            if "trace" in _columns(db, "decisions"):
                want_traces |= {tuple(r) for r in db.execute("SELECT run_id, episode FROM decisions WHERE trace IS NOT NULL")}
            for rid, rows in _old_events(db, root, ignored).items():
                want_events.setdefault(rid, set()).update((t, kind) for _, t, kind, _ in rows)
    want_states, frames = set(), []
    for d in _run_dirs(root, data_dir, ignored):
        rid = d.name
        events = [ev for _, ev in _run_events(d, root, ignored)]
        want_events.setdefault(rid, set()).update((ev["t"], ev["kind"]) for ev in events)
        want_decisions |= {(rid, ev["episode"]) for ev in events if ev["kind"] == "trace"}
        for episode in _run_traces(d, root, ignored):
            if (rid, episode) in want_decisions:
                want_traces.add((rid, episode))
        if _run_status(d, root, ignored) is not None:
            want_states.add(rid)
        frames += [(rid, name, src) for name, src in _run_frames(d)]
    for rid in sorted(want_events):
        missing = len(want_events[rid] - _keys(store, "events", ("t", "kind"), "WHERE run_id=?", (rid,)))
        if missing:
            diffs.append(f"events {rid}: {missing} missing")
    have = _keys(store, "decisions", ("run_id", "episode"))
    diffs += [f"decision {rid}#{ep} missing" for rid, ep in sorted(want_decisions - have, key=str)]
    traced = _keys(store, "decisions", ("run_id", "episode"), "WHERE trace IS NOT NULL")
    diffs += [f"trace {rid}#{ep} missing" for rid, ep in sorted((want_traces & have) - traced, key=str)]
    states = {r for (r,) in _keys(store, "run_state", ("run_id",))}
    diffs += [f"run state {rid} missing" for rid in sorted(want_states - states)]
    for rid, name, src in frames:
        dst = data_dir / "frames" / rid / name
        if not dst.is_file():
            diffs.append(f"frame {rid}/{name} missing")
        elif src.is_file() and os.access(src, os.R_OK) and dst.stat().st_size != src.stat().st_size:
            diffs.append(f"frame {rid}/{name} differs")
    for ld in sorted((root / "corpora").glob("*/learned")):
        if not ld.is_dir():
            continue
        game = ld.parent.name
        have_notes = _keys(store, "learned_notes", ("kind", "text"), "WHERE game=?", (game,))
        for kind, (fname, _) in NOTE_FILES.items():
            for n in _notes(ld / fname, root, ignored):
                if (kind, n["text"]) not in have_notes:
                    diffs.append(f"learned {kind} {game}: {n['text'][:60]!r} missing")
        names = {n for (n,) in _keys(store, "learned_screens", ("name",), "WHERE game=?", (game,))}
        diffs += [f"learned screen {game}/{s['name']} missing" for s in _screens(ld, root, ignored)
                  if s["name"] not in names]
        have_eps = _keys(store, "episodes", ("t", "situation"), "WHERE game=?", (game,))
        diffs += [f"episode {game} {e[0]} missing" for e in _episodes(ld, root, ignored) if (e[0], e[2]) not in have_eps]
        have_led = _keys(store, "ledger", ("t", "kind", "data"), "WHERE game=?", (game,))
        diffs += [f"ledger {game} {r[0]} {r[1]} missing" for r in _ledger(ld, root, ignored) if r not in have_led]
        if not (data_dir / "learned" / game / "manifest.toml").is_file():
            diffs.append(f"learned/{game} not generated")
    have_j = _keys(store, "journal", ("campaign_id", "t", "text"))
    diffs += [f"journal {cid} #{int(t)} missing" for cid, _, t, _, text in _journals(root, ignored)
              if (cid, t, text) not in have_j]
    if _prefs(root, ignored) is not None and not store.query("SELECT 1 FROM settings WHERE key='prefs'"):
        diffs.append("prefs missing")
    kept_from, have_u = _usage_kept_from(), _keys(store, "model_usage", ("day", "model"))
    diffs += [f"model usage {day} {model} missing" for day, model, _ in _usage(root, ignored)
              if day >= kept_from and (day, model) not in have_u]
    have_o = {c for (c,) in _keys(store, "standing_orders", ("campaign_id",))}
    diffs += [f"standing orders {cid} missing" for cid, texts in _orders(root, store, ignored).items()
              if texts and cid not in have_o]
    diffs += [f"secret {name} missing" for name in SECRET_FILES
              if (root / "runs" / name).is_file() and not (data_dir / SECRETS_DIR / name).exists()]
    return diffs


# ---------------------------------------------------------------- prune

def _tracked(root: Path, paths: list[Path]) -> list[str]:
    """The git-tracked files under `paths` (none when root is not in a git work tree)."""
    if not paths:
        return []
    try:
        inside = subprocess.run(["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
                                capture_output=True, text=True, check=False)
    except OSError as e:
        if (root / ".git").exists():
            raise PruneRefused(f"cannot ask git which files are tracked in {root}: {e}") from e
        return []
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        if (root / ".git").exists():
            raise PruneRefused(f"cannot ask git which files are tracked in {root}: {inside.stderr.strip()}")
        return []
    r = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--", *(_rel(root, p) for p in paths)],
                       capture_output=True, text=True, check=False)
    if r.returncode != 0:
        raise PruneRefused(f"git ls-files failed in {root}: {r.stderr.strip()}")
    return [f for f in r.stdout.split("\0") if f]


def prune_source(root: Path, store, kept: list[str] | None = None) -> list[Path]:
    """Delete the imported runtime files of the install at `root` (plan ruling P5) and return them:
    runs/telemetry.sqlite (and -wal, -shm), runs/<id>/ of each run the store holds, pilot-settings.json,
    model-usage.json, orders/, and the old dashboard.key/dashboard.carryover once <data>/secrets/ holds the
    same bytes. Never anything else (frames/, learned/, secrets/, pilot.db, auth.sqlite, unknown files, a
    run directory holding a file the old pilot did not write), and nothing at all when a path is tracked
    by git. What stays for another reason is named in `kept`. Run it only after check() returned []."""
    root = Path(root)
    runs = root / "runs"
    data_dir = Path(store.path).parent
    kept = [] if kept is None else kept
    if not runs.is_dir():
        return []
    known = {r["id"] for r in store.query("SELECT id FROM runs")}
    targets = [runs / n for n in OLD_FILES if (runs / n).is_file()]
    if (runs / "orders").is_dir():
        targets.append(runs / "orders")
    for d in _run_dirs(root, data_dir, []):
        extra = sorted(p.name for p in d.iterdir() if p.name not in RUN_FILES)
        if d.name not in known:
            kept.append(f"{_rel(root, d)}: no run of that id in the store")
        elif extra:
            kept.append(f"{_rel(root, d)}: holds {', '.join(extra[:5])}, which the import does not copy")
        else:
            targets.append(d)
    for name in SECRET_FILES:
        old, new = runs / name, data_dir / SECRETS_DIR / name
        if not old.is_file() or old.resolve() == new.resolve():
            continue
        if new.is_file() and old.read_bytes() == new.read_bytes():
            targets.append(old)
        else:
            kept.append(f"{_rel(root, old)}: {SECRETS_DIR}/{name} does not hold the same bytes")
    data = data_dir.resolve()
    targets = [p for p in targets if not data.is_relative_to(p.resolve())]     # never the data directory itself
    tracked = _tracked(root, targets)
    if tracked:
        raise PruneRefused(f"refused: git tracks {', '.join(tracked[:5])}{' ...' if len(tracked) > 5 else ''} "
                           f"in {root}; nothing was deleted")
    for p in targets:
        if p.is_dir() and not p.is_symlink():
            shutil.rmtree(p)
        else:
            p.unlink(missing_ok=True)
    return targets
