"""pilot export (data platform design, ruling 10): the store's learned files and pilot journals as files,
for a repo or a person. Committing them is outside the pilot."""

from __future__ import annotations

import hashlib
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
        files = render(store, g)
        for rel, data in files.items():
            p = out_dir / g / "learned" / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
            written.append(p)
        templates = out_dir / g / "learned" / "templates"
        if templates.is_dir():
            for stale in templates.glob("*.png"):         # as write_learned_dir: only templates this render dropped
                if stale.is_file() and f"templates/{stale.name}" not in files:
                    stale.unlink()
    where, args = ("WHERE campaign_id=?", (campaign,)) if campaign else (
        ("WHERE game=?", (game,)) if game else ("", ()))
    by: dict[str, list[dict]] = {}
    for r in store.query(f"SELECT campaign_id, date, text FROM journal {where} ORDER BY t", args):
        by.setdefault(r["campaign_id"], []).append(r)
    taken: set[str] = set()
    for cid in sorted(by):
        name = _safe(cid)
        if name in taken:                                 # two ids sanitise alike: keep both files
            name += "-" + hashlib.sha1(cid.encode()).hexdigest()[:8]
        taken.add(name)
        p = out_dir / "journals" / f"{name}.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        lines = [f"# Journal: {cid}\n\nEntries written by the pilot app.\n"]
        for r in by[cid]:
            text = "\n".join(ln.rstrip() for ln in r["text"].rstrip().split("\n")).replace("\n", "\n  ")
            lines.append(f"- {'**' + r['date'] + '**: ' if r['date'] else ''}{text}")
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        written.append(p)
    return written
