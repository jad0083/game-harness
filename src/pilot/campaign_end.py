"""The end of a campaign (docs/design/2026-09-27-postmortem-fixes-design.md, rulings 21-23): once our
civilization (Civ VI) or empire (Stellaris) is gone, the run ends with a deterministic report and no
model call. The Kublai campaign's last city fell in AI turn T579, the loss was seen at T583, and 16
decisions and 4 reviews still ran until a human stopped the run at T763.

Pure: the governors read the game and telemetry and call these."""

from __future__ import annotations

import re

RESULT_LOST = "lost"

# the urgent reasons that name a loss ("city lost: Beijing", "colony lost: 5 -> 4")
_LOST_RE = re.compile(r"\b(city|colony) lost: ([^;]+)")


def settlers(snapshot: dict) -> int:
    """Our settlers (any unit type named *SETTLER*) in a Civ VI snapshot."""
    by_type = (snapshot.get("units") or {}).get("by_type") or {}
    return sum(int(v or 0) for k, v in by_type.items() if "SETTLER" in str(k))


def civ6_read(snapshot: dict) -> str | None:
    """What one Civ VI snapshot says about the end (ruling 21): "not alive" (the game's IsAlive is
    false: the run ends at once), "no cities" (0 cities and 0 settlers: it ends on the second such read
    in a row), or None. The local player id is never used: China was alive again at T913 while the
    local player read -1 at T916."""
    if snapshot.get("alive") is False:
        return "not alive"
    if not snapshot.get("cities") and settlers(snapshot) == 0:
        return "no cities"
    return None


def civ6_signal(read: str) -> str:
    return ("the game reports our civilization is not alive" if read == "not alive"
            else "0 cities and 0 settlers on 2 reads in a row")


def stellaris_zero(b: dict) -> bool:
    """A Stellaris save in which we own no planet (ruling 22). A lost capital is not the end, nor a
    briefing that cannot find our country (another game's save reads the same way)."""
    return isinstance(b.get("planets"), list) and not b["planets"]


def stellaris_zero_row(row: dict) -> bool:
    """The same test on a metrics row (`planets` is the count there)."""
    return row.get("planets") == 0


def losses(episodes: list[dict]) -> list[dict]:
    """The cities (or colonies) lost in the campaign, oldest first, from the decisions' urgent
    reasons: [{"what": "Beijing", "date": "T546"}]; each city once (its first loss)."""
    out, seen = [], set()
    for e in episodes:
        for kind, what in _LOST_RE.findall(str(e.get("situation") or "")):
            what = what.strip()
            key = (kind, what) if kind == "city" else (kind, what, e.get("date"))
            if key in seen:
                continue
            seen.add(key)
            out.append({"what": what if kind == "city" else f"colonies {what}", "date": e.get("date")})
    return out


def _at_war(n: dict) -> bool:
    return bool(n.get("at_war")) or "AT WAR" in (n.get("status") or [])


def enemy_ratio(rows: list[dict], ours_key: str) -> dict | None:
    """Our military against the strongest enemy at war with us, from the last metrics row (oldest
    first) that shows one: {"date", "ours", "enemy", "theirs", "ratio"}; None without any."""
    for r in reversed(rows):
        enemies = [n for n in r.get("neighbours") or [] if _at_war(n) and isinstance(n.get("military"), (int, float))]
        ours = r.get(ours_key)
        if enemies and isinstance(ours, (int, float)):
            top = max(enemies, key=lambda n: n["military"])
            return {"date": r.get("date"), "ours": ours, "enemy": top.get("name"), "theirs": top["military"],
                    "ratio": round(ours / top["military"], 2) if top["military"] else None}
    return None


def last_held(rows: list[dict], count_key: str) -> str | None:
    """The date of the last metrics row in which we still held a city or planet."""
    return next((r.get("date") for r in reversed(rows) if (r.get(count_key) or 0) > 0), None)


def first_zero_after(rows: list[dict], count_key: str, last: str | None, months) -> str | None:
    """The date of the first metrics row after `last` with none held (the loss first seen)."""
    after = [r for r in rows if r.get("date") and (last is None or months(r["date"]) > months(last))]
    return next((r["date"] for r in after if (r.get(count_key) or 0) == 0), None)


def _num(v) -> str:
    return f"{v:,.0f}" if isinstance(v, (int, float)) else str(v)


def report_text(name: str, rep: dict) -> str:
    """The journal's end line, e.g. "Campaign lost: China (Kublai Khan) was eliminated in T579, seen at
    T583 (0 cities and 0 settlers on 2 reads in a row). Cities lost: ... The run ended."."""
    what = "cities" if rep.get("game") == "civ6" else "colonies"
    parts = [(f"Campaign lost: {name} was eliminated in {rep.get('turn') or 'an unknown turn'}, seen at "
              f"{rep.get('seen')} ({rep.get('signal')}).")]
    lost = rep.get("lost") or []
    if lost:
        parts.append(f"{what.capitalize()} lost: " + ", ".join(f"{x['what']} {x['date']}" for x in lost) + ".")
    r = rep.get("ratio")
    if r:
        parts.append(f"Last military against the strongest enemy ({r['date']}): {_num(r['ours'])} vs {r['enemy']} "
                     f"{_num(r['theirs'])}" + (f" ({r['ratio']:g}x)." if r.get("ratio") is not None else "."))
    stranded = rep.get("stranded") or {}
    if stranded:
        parts.append("Stranded: " + ", ".join(f"{_num(v)} {k}" for k, v in stranded.items()) + ".")
    after = rep.get("after") or {}
    parts.append(f"Decisions after the loss was first seen: {after.get('decisions', 0)} "
                 f"(strategy reviews {after.get('reviews', 0)}).")
    if rep.get("note"):
        parts.append(rep["note"])
    parts.append("The run ended; nothing more is decided for this campaign while the signal holds.")
    return " ".join(parts)
