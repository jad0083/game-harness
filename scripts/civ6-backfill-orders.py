#!/usr/bin/env python3
"""Recover a Civ VI campaign's order record from decision traces written before the record existed
(docs/design/2026-09-27-civ6-levers-design.md, ruling 13; check L4).

Only apply-time outcomes come back: purchases (completed at once), refused, lost and unknown orders.
Whether an accepted order later held or was replaced by the AI exists only as prose, so it is not
backfilled.

    scripts/civ6-backfill-orders.py                       # read-only: rows and counts per key
    scripts/civ6-backfill-orders.py --write               # add them as order_outcome events of a new run

--write adds the rows as a new run named <time>-backfill, in the campaign, where <time> is the
earliest backfilled decision's (so the run sorts among the real runs by time): its log
runs/<time>-backfill/events.jsonl (the raw record, so `python -m pilot rebuild-telemetry` recreates
them) and the telemetry database. It refuses when the campaign already has backfilled rows. Run it
once, with the governor stopped or paused, when deploying the order record."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from pilot.civ6 import backfill_rows
from pilot.telemetry import Telemetry

CAMPAIGN = "civ6/kublai_khan_china_702403662"


def decisions(db: Path, campaign: str) -> list[dict]:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute("SELECT date, t, trace FROM decisions WHERE campaign_id=? AND decision IS NOT NULL"
                           " AND decision != 'strategy_review' ORDER BY t", (campaign,)).fetchall()
        done = con.execute("SELECT COUNT(*) FROM events e JOIN runs r ON r.id = e.run_id WHERE r.campaign_id=?"
                           " AND e.kind='order_outcome' AND e.data LIKE '%\"backfilled\": true%'", (campaign,)).fetchone()[0]
    finally:
        con.close()
    out = []
    for r in rows:
        trace = json.loads(r["trace"]) if r["trace"] else {}
        out.append({"date": r["date"], "t": r["t"], "orders": trace.get("orders") or []})
    return out if not done else [{"already": done}]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", type=Path, default=ROOT / "runs" / "telemetry.sqlite")
    ap.add_argument("--campaign", default=CAMPAIGN)
    ap.add_argument("--write", action="store_true", help="add the rows as order_outcome events of a new run")
    ap.add_argument("--runs-dir", type=Path, default=None,
                    help="where the new run's events.jsonl goes (default: the database's folder, runs/)")
    args = ap.parse_args(argv)
    found = decisions(args.db, args.campaign)
    if found and "already" in found[0]:
        print(f"{args.campaign} already has {found[0]['already']} backfilled rows; nothing to do")
        return 1 if args.write else 0
    rows = backfill_rows(found)
    times = {d["date"]: d["t"] for d in found}
    for r in rows:
        print(json.dumps(r, ensure_ascii=False))
    counts = Counter((r["key"], r["result"]) for r in rows)
    print(f"{len(rows)} rows from {len(found)} decisions:", ", ".join(f"{k} {res} {n}" for (k, res), n in sorted(counts.items())))
    if not args.write or not rows:
        return 0
    game, name = args.campaign.split("/", 1)
    now = time.time()
    # named like a real run (its start time, %Y%m%d-%H%M%S) at the earliest backfilled decision, so it
    # sorts among the runs by time and never ahead of a later real run (the dashboard lists newest first)
    first = min(times.get(r["date"]) or now for r in rows)
    run = f"{time.strftime('%Y%m%d-%H%M%S', time.localtime(first))}-backfill"
    events = [{"t": now, "kind": "run_start", "game": game, "model": "backfill"},
              {"t": now, "kind": "campaign", "game": game, "name": name},
              *({"t": times.get(r["date"]) or now, "kind": "order_outcome", **r} for r in rows),
              {"t": now, "kind": "run_end", "decisions": 0}]
    # the run log first: it is the raw record the database is rebuilt from (telemetry.py)
    log = (args.runs_dir or args.db.parent) / run / "events.jsonl"
    log.parent.mkdir(parents=True, exist_ok=False)
    log.write_text("".join(json.dumps(ev, ensure_ascii=False, default=str) + "\n" for ev in events), encoding="utf-8")
    tel = Telemetry(args.db)
    for ev in events:
        tel.record(run, ev)
    tel.close()
    print(f"written as run {run} ({log})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
