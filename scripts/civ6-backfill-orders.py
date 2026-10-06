#!/usr/bin/env python3
"""Recover a Civ VI campaign's order record from decision traces written before the record existed
(docs/design/2026-09-27-civ6-levers-design.md, ruling 13; check L4).

Only apply-time outcomes come back: purchases (completed at once), refused, lost and unknown orders.
Whether an accepted order later held or was replaced by the AI exists only as prose, so it is not
backfilled.

    scripts/civ6-backfill-orders.py                       # read-only: rows and counts per key
    scripts/civ6-backfill-orders.py --write               # add them as order_outcome events of a new run

--write adds the rows as a new run named <time>-backfill, in the campaign, where <time> is the
earliest backfilled decision's (so the run sorts among the real runs by time), to the store in the
data directory (--data-dir; default PILOT_DATA_DIR, else runs/). It refuses when the campaign already
has backfilled rows. Run it once, with the governor stopped or paused, when deploying the order record."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from pilot.civ6 import backfill_rows
from pilot.config import Settings
from pilot.store import open_store

CAMPAIGN = "civ6/kublai_khan_china_702403662"


def decisions(data_dir: Path, campaign: str) -> list[dict]:
    store = open_store(data_dir)
    rows = store.query("SELECT date, t, trace FROM decisions WHERE campaign_id=? AND decision IS NOT NULL"
                       " AND decision != 'strategy_review' ORDER BY t", (campaign,))
    done = store.query("SELECT COUNT(*) AS n FROM events e JOIN runs r ON r.id = e.run_id WHERE r.campaign_id=?"
                       " AND e.kind='order_outcome' AND e.data LIKE '%\"backfilled\": true%'", (campaign,))[0]["n"]
    out = []
    for r in rows:
        trace = json.loads(r["trace"]) if r["trace"] else {}
        out.append({"date": r["date"], "t": r["t"], "orders": trace.get("orders") or []})
    return out if not done else [{"already": done}]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--data-dir", type=Path, default=None, help="the pilot's data directory (default: PILOT_DATA_DIR, else runs/)")
    ap.add_argument("--campaign", default=CAMPAIGN)
    ap.add_argument("--write", action="store_true", help="add the rows as order_outcome events of a new run")
    args = ap.parse_args(argv)
    data_dir = args.data_dir or Settings.from_env().runs_dir
    if not (data_dir / "pilot.db").is_file():
        print(f"no store at {data_dir / 'pilot.db'}: pass --data-dir (or set PILOT_DATA_DIR) to the data directory",
              file=sys.stderr)
        return 2
    found = decisions(data_dir, args.campaign)
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
    store = open_store(data_dir)
    for ev in events:
        store.record(run, ev)
    print(f"written as run {run} ({store.path})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
