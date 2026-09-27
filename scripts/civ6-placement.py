#!/usr/bin/env python3
"""District placement, stage A (docs/design/2026-09-27-civ6-levers-design.md, ruling 30): read-only.

    .venv/bin/python scripts/civ6-placement.py                      # one tuner query: civ6 district-plots
    .venv/bin/python scripts/civ6-placement.py --json plots.json    # a saved reply, no game needed
    .venv/bin/python scripts/civ6-placement.py --campaign civ6/kublai_khan_china_702403662 --save plots.json

Rates where each district the cities could place may go (adjacency from the game's rules x the share
of effort of its pillar - the tile given up - plots a heavier pillar's district wants) and rates the
districts the AI placed the same way; prints the go / no-go of stage B (our best plot beats the AI's
by at least +1 adjacency on average over at least 4 districts that have at least 3 other plots to
compare with). Shares come from --shares, else the
campaign's latest strategy weights (runs/telemetry.sqlite, opened read-only), else an even split.
Nothing is sent to the game but the one read-only query; nothing is placed."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from pilot.civ6 import CorpusIndex
from pilot.civ6_placement import Rules, report, report_text


def shares_from(text: str) -> dict[str, float]:
    out = {}
    for part in filter(None, (p.strip() for p in text.split(","))):
        name, _, value = part.partition("=")
        out[name.strip()] = float(value)
    return out


def campaign_weights(db: Path, campaign: str) -> dict[str, float]:
    """The pillar weights of the campaign's latest strategy (read-only)."""
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        row = con.execute("SELECT data FROM strategies WHERE campaign_id=? ORDER BY t DESC LIMIT 1", (campaign,)).fetchone()
    finally:
        con.close()
    if not row:
        return {}
    return {name: float(p.get("weight") or 0) for name, p in (json.loads(row[0]).get("pillars") or {}).items()}


def read_live(city: str | None) -> dict:
    """One read-only tuner query through the controller (GAME_AGENT_URL / GAME_AGENT_TOKEN from the env)."""
    args = [str(REPO / "target/release/game-controller"), "--corpus", str(REPO / "corpora/civ6"), "civ6", "district-plots"]
    if city:
        args += ["--city", city]
    r = subprocess.run(args, cwd=REPO, capture_output=True, text=True, timeout=120, check=False, env=os.environ.copy())
    try:
        reply = json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        raise SystemExit(f"district-plots failed (exit {r.returncode}): {(r.stderr or r.stdout)[:400]}") from None
    if reply.get("ok") is False:
        raise SystemExit(f"district-plots refused: {reply.get('error')}")
    return reply


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", type=Path, help="a saved `civ6 district-plots` reply (no game needed)")
    ap.add_argument("--city", help="one city (numeric ID) for the live read")
    ap.add_argument("--save", type=Path, help="also write the live reply here")
    ap.add_argument("--shares", default="", help="pillar=weight,... (e.g. science=30,faith=10); overrides --campaign")
    ap.add_argument("--campaign", default="", help="take the shares from this campaign's latest strategy")
    ap.add_argument("--telemetry", type=Path, default=REPO / "runs/telemetry.sqlite")
    ap.add_argument("--corpus", type=Path, default=REPO / "corpora/civ6")
    ap.add_argument("--out-json", action="store_true", help="print the report as JSON")
    a = ap.parse_args(argv)
    data = json.loads(a.json.read_text(encoding="utf-8")) if a.json else read_live(a.city)
    if a.save and not a.json:
        a.save.write_text(json.dumps(data), encoding="utf-8")
    shares = shares_from(a.shares) if a.shares else (campaign_weights(a.telemetry, a.campaign) if a.campaign else {})
    r = report(data, Rules.load(a.corpus), shares, CorpusIndex.load(a.corpus).cid)
    r["shares"] = shares or "even"
    print(json.dumps(r, indent=1) if a.out_json else report_text(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
