#!/usr/bin/env python3
"""Recover a Civ VI campaign's order record from decision traces written before the record existed
(docs/design/2026-09-27-civ6-levers-design.md, ruling 13; check L4).

Only apply-time outcomes come back: purchases (completed at once), refused, lost and unknown orders.
Whether an accepted order later held or was replaced by the AI exists only as prose, so it is not
backfilled.

    scripts/civ6-backfill-orders.py                       # read-only: rows and counts per key
    scripts/civ6-backfill-orders.py --write               # add them as order_outcome events of a new run

--write adds rows to the telemetry database (a new run named backfill-<time>, in the campaign); it
refuses when the campaign already has backfilled rows. Run it once, with the governor stopped or
paused, when deploying the order record."""

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
    tel = Telemetry(args.db)
    run = f"backfill-{time.strftime('%Y%m%d-%H%M%S')}"
    game, name = args.campaign.split("/", 1)
    now = time.time()
    tel.record(run, {"t": now, "kind": "run_start", "game": game, "model": "backfill"})
    tel.record(run, {"t": now, "kind": "campaign", "game": game, "name": name})
    for r in rows:
        tel.record(run, {"t": times.get(r["date"]) or now, "kind": "order_outcome", **r})
    tel.record(run, {"t": now, "kind": "run_end", "decisions": 0})
    tel.close()
    print(f"written as run {run}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
