"""The Stellaris planet check, stage A (docs/design/2026-09-27-stellaris-levers-design.md, ruling 22):
read-only. Pure: no game access.

A colony has a problem on one save when (the pop count is the larger of sapient and working pops, so
robots count):
- `s` stability is below 50 (`c`: below 25, the revolt zone);
- `a` free amenities are below -100 on 300+ pops;
- `h` free housing is below 0 on 1,000+ pops;
- `u` 5% or more of its employable pops are unemployed (not the capital);
- `p` its pops fell 20% or more from their peak in the last 12 months;
- `o` it is occupied.

It is flagged when the problem persists across saves at least 2 months apart with no save between them
without it, and none more than 3 months after the one before (a restart gap: nothing was observed
between them, so the older save is not "the save before"). The governor keeps each save's problems in its metrics row (`colonies`: id -> [pops,
free amenities, stability, codes]), so the check needs no state of its own and survives a restart.
Urgent reasons fire once, at the transition: a colony below stability 25 on 2 saves in a row, and a
planet of 1,000+ pops losing 20% in 12 months. No lever acts on planets in this version."""

from __future__ import annotations

from itertools import pairwise

STABILITY_LOW = 50.0
STABILITY_CRISIS = 25.0
AMENITIES_LOW, AMENITIES_POPS = -100.0, 300
HOUSING_LOW, HOUSING_POPS = 0.0, 1000
UNEMPLOYED_SHARE = 0.05
POPS_DROP, POPS_MONTHS, POPS_URGENT = 0.20, 12, 1000
PERSIST_MONTHS = 2
# saves further apart than this are not "in a row": nothing was observed between them (a restart
# gap of years); 3 leaves room for a poll that missed a monthly save at the fastest speed
NEXT_SAVE_MONTHS = 3
RECORD_GAP_MONTHS = 12            # a pair of rows further apart says nothing about one directive
# the go criterion's estimate for a later planet lever (ruling 22): job output lost to low stability,
# 0.6% per point under 75 (a pre-4.0 coefficient, unverified in 4.5)
STABILITY_FULL, LOSS_PER_POINT = 75.0, 0.006
ORDER = "sahupo"                  # how a flagged planet's problems are listed


def _months(date: str) -> int:
    y, m, *_ = (int(x) for x in str(date).split("."))
    return y * 12 + m - 1


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def pop_count(p: dict) -> int:
    """Sapient pops, or the employable ones when more (robots work but are not sapient)."""
    return max(int(p.get("pops") or 0), int(p.get("employable") or 0))


def colony_codes(p: dict) -> dict[str, str]:
    """The problems a colony shows on one save (all but `p`, which needs the rows): code -> text."""
    out: dict[str, str] = {}
    n, st = pop_count(p), p.get("stability")
    if _num(st) and st < STABILITY_LOW:
        out["s"] = f"stability {st:.0f}"
        if st < STABILITY_CRISIS:
            out["c"] = f"stability {st:.0f}"
    am, ho = p.get("free_amenities"), p.get("free_housing")
    if _num(am) and am < AMENITIES_LOW and n >= AMENITIES_POPS:
        out["a"] = f"amenities {am:.0f}"
    if _num(ho) and ho < HOUSING_LOW and n >= HOUSING_POPS:
        out["h"] = f"housing {ho:.0f}"
    emp, un = p.get("employable"), p.get("unemployed")
    if not p.get("capital") and _num(emp) and emp > 0 and _num(un) and un >= UNEMPLOYED_SHARE * emp:
        out["u"] = f"unemployed {un:.0f} of {emp:.0f}"
    if p.get("occupied"):
        out["o"] = f"occupied by {p.get('occupier') or 'the enemy'}"
    return out


def _before(b: dict, rows: list[dict]) -> list[dict]:
    """`rows` dated before save `b`, newest first."""
    now = _months(b["date"])
    return sorted((r for r in rows if r.get("date") and _months(r["date"]) < now),
                  key=lambda r: _months(r["date"]), reverse=True)


def _entry(r: dict, pid: str) -> list | None:
    e = (r.get("colonies") or {}).get(pid)
    return e if isinstance(e, list) and len(e) >= 4 else None


def _pops_drop(b: dict, p: dict, rows: list[dict]) -> tuple[float, int] | None:
    """(share lost, peak) when the colony's pops are 20% or more under their peak of the last 12 months."""
    now, pid, n = _months(b["date"]), str(p.get("id")), pop_count(p)
    peaks = [e[0] for r in rows if now - _months(r["date"]) <= POPS_MONTHS
             and (e := _entry(r, pid)) is not None and _num(e[0])]
    peak = max(peaks, default=0)
    if peak > 0 and n <= (1 - POPS_DROP) * peak:
        return 1 - n / peak, int(peak)
    return None


def _codes(b: dict, p: dict, rows: list[dict]) -> dict[str, str]:
    out = colony_codes(p)
    drop = _pops_drop(b, p, _before(b, rows))
    if drop:
        out["p"] = f"pops -{drop[0]:.0%} in 12 months ({drop[1]} to {pop_count(p)})"
    return out


def colony_row(b: dict, rows: list[dict]) -> dict[str, list]:
    """The save's colonies for its metrics row: id -> [pops, free amenities, stability, codes]."""
    out = {}
    for p in b.get("planets") or []:
        am, st = p.get("free_amenities"), p.get("stability")
        out[str(p.get("id"))] = [pop_count(p), round(am, 1) if _num(am) else None,
                                 round(st, 1) if _num(st) else None, "".join(sorted(_codes(b, p, rows)))]
    return out


def _next_to(newer: dict, r: dict | None) -> dict | None:
    """`r` when it is the save before `newer` (at most NEXT_SAVE_MONTHS earlier), else None."""
    return r if r is not None and _months(newer["date"]) - _months(r["date"]) <= NEXT_SAVE_MONTHS else None


def _run(b: dict, pid: str, code: str, older: list[dict]) -> tuple[int, int]:
    """(saves in a row with `code` before `b`, the oldest one's month); older = rows before b, newest first.
    A gap of more than NEXT_SAVE_MONTHS between two saves ends the run."""
    n, since, newer = 0, _months(b["date"]), b
    for r in older:
        e = _entry(r, pid) if _next_to(newer, r) else None
        if e is None or code not in str(e[3]):
            break
        n, since, newer = n + 1, _months(r["date"]), r
    return n, since


def planet_issues(b: dict, rows: list[dict]) -> list[dict]:
    """The colonies of save `b` with a problem that persisted across saves at least 2 months apart (per
    the metrics `rows` before it): {id, name, issues [(code, text)], saves, hints}, in save order."""
    older, now = _before(b, rows), _months(b["date"])
    minerals = (b.get("net") or {}).get("minerals")
    out = []
    for p in b.get("planets") or []:
        pid, codes = str(p.get("id")), _codes(b, p, rows)
        kept, saves = [], 0
        for code in ORDER:
            if code not in codes:
                continue
            n, since = _run(b, pid, code, older)
            if n and now - since >= PERSIST_MONTHS:
                kept.append((code, codes[code]))
                saves = max(saves, n + 1)
        if not kept:
            continue
        hints = []
        if isinstance(p.get("queued"), list) and not p["queued"]:
            hints.append("nothing queued here")
        if _num(minerals) and minerals < 0:
            hints.append("minerals net < 0")
        out.append({"id": p.get("id"), "name": p.get("name") or pid, "issues": kept, "saves": saves, "hints": hints})
    return out


def planet_line(flagged: list[dict]) -> str:
    """One line naming the flagged planets only, e.g. "Planet check: Arnvoss stability 18 (3 saves),
    amenities -253, housing -283; nothing queued here"; "" when none is flagged."""
    parts = []
    for f in flagged:
        texts = [t for _, t in f["issues"]]
        text = f"{f['name']} {texts[0]} ({f['saves']} saves)" + "".join(f", {t}" for t in texts[1:])
        parts.append(text + (f"; {', '.join(f['hints'])}" if f["hints"] else ""))
    return "Planet check: " + " | ".join(parts) if parts else ""


def low_stability(b: dict, rows: list[dict]) -> list[str]:
    """Colonies below stability 25 on save `b` and on the save before it (war crisis C6); a save more
    than NEXT_SAVE_MONTHS older is not the save before."""
    older = _before(b, rows)
    prev = _next_to(b, older[0] if older else None)
    out = []
    for p in b.get("planets") or []:
        e = _entry(prev, str(p.get("id"))) if prev else None
        if "c" in colony_codes(p) and e is not None and "c" in str(e[3]):
            out.append(p.get("name") or str(p.get("id")))
    return out


def planet_urgent(b: dict, rows: list[dict]) -> list[str]:
    """Urgent reasons, each once at its transition: "planet crisis: <name> stability <n>" when a colony
    is below 25 for the second save in a row, and "planet losing pops: <name> -<p>% in 12 months" when a
    planet of 1,000+ pops first shows a 20% loss. A save more than NEXT_SAVE_MONTHS before the next one
    is not the save before it (after a restart gap the transition fires again)."""
    older = _before(b, rows)
    prev, prev2 = (older + [None, None])[:2]
    prev = _next_to(b, prev)
    prev2 = _next_to(prev, prev2) if prev else None
    out = []
    for p in b.get("planets") or []:
        pid, name, codes = str(p.get("id")), p.get("name") or str(p.get("id")), _codes(b, p, rows)
        e1 = _entry(prev, pid) if prev else None
        e2 = _entry(prev2, pid) if prev2 else None
        if "c" in codes and e1 is not None and "c" in str(e1[3]) and not (e2 is not None and "c" in str(e2[3])):
            out.append(f"planet crisis: {name} {codes['c']}")
        drop = _pops_drop(b, p, older)
        if drop and drop[1] >= POPS_URGENT and not (e1 is not None and "p" in str(e1[3])):
            out.append(f"planet losing pops: {name} -{drop[0]:.0%} in 12 months")
    return out


def planet_record(rows: list[dict]) -> dict[str, dict]:
    """Per directive held, the change of free amenities per planet-year on colonies with an amenity
    deficit (`a`) at the start of each interval between two metrics rows (at most 12 months apart), and
    the number of distinct planets: {directive: {per_planet_year, planet_years, planets}}. Advisory
    (weighted-pillars ruling 13's kind of record)."""
    dated = sorted((r for r in rows if r.get("date") and isinstance(r.get("colonies"), dict)),
                   key=lambda r: _months(r["date"]))
    acc: dict[str, list] = {}
    for r0, r1 in pairwise(dated):
        d, gap = r0.get("directive"), _months(r1["date"]) - _months(r0["date"])
        if not d or not 0 < gap <= RECORD_GAP_MONTHS:
            continue
        for pid, e0 in r0["colonies"].items():
            e1 = _entry(r1, pid)
            if e1 is None or not isinstance(e0, list) or len(e0) < 4 or "a" not in str(e0[3]) \
                    or not _num(e0[1]) or not _num(e1[1]):
                continue
            a = acc.setdefault(d, [0.0, 0.0, set()])
            a[0] += e1[1] - e0[1]
            a[1] += gap / 12
            a[2].add(pid)
    return {d: {"per_planet_year": round(ch / yrs, 1), "planet_years": round(yrs, 2), "planets": len(ps)}
            for d, (ch, yrs, ps) in sorted(acc.items()) if yrs > 0}


def planet_record_text(rec: dict[str, dict]) -> str:
    """One line per directive, e.g. "- consolidate_economy: amenities +9 per planet-year over 12.5
    planet-years on 3 planets"."""
    out = []
    for d, r in rec.items():
        yrs, n = r["planet_years"], r["planets"]
        out.append(f"- {d}: amenities {r['per_planet_year']:+.0f} per planet-year over {yrs:g} "
                   f"planet-year{'' if yrs == 1 else 's'} on {n} planet{'' if n == 1 else 's'}")
    return "\n".join(out)


def stability_loss(b: dict) -> float | None:
    """The go criterion's estimate (ruling 22), in percent: job output lost to stability under 75,
    sum of pops x (75 - stability) x 0.6% over all pops; None without pops."""
    total = loss = 0.0
    for p in b.get("planets") or []:
        n, st = pop_count(p), p.get("stability")
        if n <= 0 or not _num(st):
            continue
        total += n
        loss += n * max(0.0, STABILITY_FULL - st) * LOSS_PER_POINT
    return round(100 * loss / total, 2) if total else None
