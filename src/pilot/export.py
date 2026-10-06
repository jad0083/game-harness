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
