"""Military threat tests shared by the governors (docs/design/2026-09-27-postmortem-fixes-design.md):
the weakness test (ruling 1). Pure: snapshots and metrics rows in, clauses and text out.

The Kublai campaign's gap built for 150+ turns with nothing that changed the buying rules (post-mortem
RC1, RC2): replayed on its metrics rows, the weakness test holds in every row from T380 to T540 (E1),
so it covers the whole pre-war window, where a test that switches on only in a crisis stayed off."""

from __future__ import annotations

from statistics import median

WEAK_MEDIAN_SHARE = 0.6       # defaults of [actions.purchase] weak_median_share...
STRONG_NEIGHBOUR_RATIO = 2.0  # ...and strong_neighbour_ratio


def _num(v) -> str:
    return f"{v:,.0f}" if isinstance(v, (int, float)) else str(v)


def thresholds(limits) -> tuple[float, float]:
    """(weak_median_share, strong_neighbour_ratio) from the purchase limits, else the defaults."""
    share = getattr(limits, "weak_median_share", 0) or WEAK_MEDIAN_SHARE
    ratio = getattr(limits, "strong_neighbour_ratio", 0) or STRONG_NEIGHBOUR_RATIO
    return float(share), float(ratio)


def majors_military(snapshot: dict) -> list[dict]:
    """The met majors with a known military strength."""
    return [m for m in snapshot.get("majors") or [] if isinstance(m.get("military"), (int, float))]


def weakness(snapshot: dict, limits=None) -> list[dict]:
    """The clauses of ruling 1 that hold, each {"clause", "text"}; [] when none does:
    - war: at war with a major (`wars[].major`);
    - last: our military ranks last among the met majors, with at least 2 met;
    - low: our military is under `weak_median_share` x the median of the met majors;
    - outgunned: a met major that is not our ally has `strong_neighbour_ratio` x our military or more
      (a major without the snapshot's `allied` field counts as not allied, which errs toward defending).
    Without our military strength only the war clause can hold."""
    share, ratio = thresholds(limits)
    out = []
    wars = [w for w in snapshot.get("wars") or [] if w.get("major", True)]
    if wars:
        out.append({"clause": "war", "text": "at war with " + ", ".join(str(w.get("civ")) for w in wars)})
    ours = snapshot.get("military")
    majors = majors_military(snapshot)
    if not isinstance(ours, (int, float)) or not majors:
        return out
    mils = [m["military"] for m in majors]
    if len(majors) >= 2 and all(v > ours for v in mils):
        out.append({"clause": "last", "text": f"last of {len(majors) + 1}"})
    med = median(mils)
    if ours < share * med:
        out.append({"clause": "low", "text": f"{_num(ours)} is {ours / med:.2f} x the median {_num(med)}"})
    strong = [m for m in majors if m["military"] >= ratio * max(ours, 1e-9) and not m.get("allied")]
    if strong:
        out.append({"clause": "outgunned", "text": ", ".join(
            f"{m.get('civ')} {_num(m['military'])} ({m['military'] / ours:.1f}x)" if ours else f"{m.get('civ')} {_num(m['military'])}"
            for m in strong)})
    return out


def weakness_line(snapshot: dict, limits=None) -> str:
    """The briefing's line, e.g. "Military weakness: last of 6; 343 is 0.31 x the median 1,094;
    CIVILIZATION_MALI 2,428 (7.1x, allied), CIVILIZATION_MAYA 1,491 (4.3x)" (an ally at the ratio is
    named but does not count); "" when no clause holds."""
    clauses = weakness(snapshot, limits)
    if not clauses:
        return ""
    _share, ratio = thresholds(limits)
    ours = snapshot.get("military")
    parts = [c["text"] for c in clauses if c["clause"] in ("war", "last", "low")]
    if isinstance(ours, (int, float)) and ours > 0:
        big = [m for m in majors_military(snapshot) if m["military"] >= ratio * ours]
        if big:
            parts.append(", ".join(f"{m.get('civ')} {_num(m['military'])} ({m['military'] / ours:.1f}x"
                                   + (", allied)" if m.get("allied") else ")")
                                   for m in sorted(big, key=lambda m: -m["military"])))
    return "Military weakness: " + "; ".join(parts)


def relative_military(snapshot: dict) -> dict:
    """Our military against the met majors (ruling 18): `military_vs_median` (ours / their median) and
    `military_vs_strongest` (ours / the strongest that is not our ally), rounded to 3 places; a value
    is None when it cannot be computed."""
    ours = snapshot.get("military")
    majors = majors_military(snapshot)
    if not isinstance(ours, (int, float)) or not majors:
        return {"military_vs_median": None, "military_vs_strongest": None}
    med = median(m["military"] for m in majors)
    others = [m["military"] for m in majors if not m.get("allied")]
    top = max(others) if others else None
    return {"military_vs_median": round(ours / med, 3) if med else None,
            "military_vs_strongest": round(ours / top, 3) if top else None}


# ---- falling behind, neighbour buildup, loyalty (rulings 10, 11, 13) -----------------------------

def behind(row: dict, factors: dict[str, float], last_min_peers: int = 3) -> list[str]:
    """The measures of a Civ VI metrics row where ours is under factor x the median of the met majors
    (`[peers] behind`; ruling 10); military also while it ranks last with `last_min_peers` or more
    majors met. Replayed on the Kublai rows (E4), Stellaris's 0.5 never fires for techs, whose gap RC1
    names, so each measure has its own factor."""
    out = []
    peers = row.get("peers") or {}
    n = row.get("peer_count") or 0
    for m, f in factors.items():
        st = peers.get(m) or {}
        ours, med = st.get("ours"), st.get("median")
        if not isinstance(ours, (int, float)) or not isinstance(med, (int, float)):
            continue
        last = m == "military" and n >= last_min_peers and st.get("rank") == n + 1
        if ours < f * med or last:
            out.append(m)
    return out


def behind_text(row: dict, measure: str) -> str:
    """"falling behind in military: 318 against a median of 1,094, last of 6"."""
    st = (row.get("peers") or {}).get(measure) or {}
    n = row.get("peer_count") or 0
    last = f", last of {n + 1}" if n and st.get("rank") == n + 1 else ""
    return f"falling behind in {measure}: {_num(st.get('ours'))} against a median of {_num(st.get('median'))}{last}"


def _allied(n: dict) -> bool:
    """A neighbour we are allied with: Civ VI's `allied`, Stellaris's alliance or federation status."""
    return bool(n.get("allied")) or any("alliance" in s or "federation" in s for s in n.get("status") or [])


def buildup(rows: list[dict], window: int, step, *, ours_key: str = "military", ratio: float = 2.0,
            growth: float = 0.5, fired: dict[str, int] | None = None) -> list[dict]:
    """Neighbour buildup on the newest of `rows` (oldest first; ruling 11): a met neighbour, not our
    ally, with at least `ratio` x our military that grew by `growth` or more since the oldest row of the
    last `window` steps (`step(date)`: turns or months). At most once per neighbour per window:
    `fired` (name -> step of its last fire) is updated. Replayed on the Kublai rows with 20 turns it
    fires 18 times in T344-T561, Australia first at T478 (345 -> 598 against our 295), not at T512
    (+33% over T496-T512); Maya at T510."""
    if not rows or not rows[-1].get("date"):
        return []
    fired = {} if fired is None else fired
    now = rows[-1]
    t = step(now["date"])
    ours = now.get(ours_key)
    if not isinstance(ours, (int, float)) or ours <= 0:
        return []
    earlier = [r for r in rows[:-1] if r.get("date") and t - window <= step(r["date"]) < t]
    out = []
    for n in now.get("neighbours") or []:
        name, mil = n.get("name"), n.get("military")
        if not isinstance(mil, (int, float)) or mil < ratio * ours or _allied(n):
            continue
        if name in fired and t - fired[name] < window:
            continue
        past = [(r, next((x.get("military") for x in r.get("neighbours") or [] if x.get("name") == name), None))
                for r in earlier]
        past = [(r, v) for r, v in past if isinstance(v, (int, float)) and v > 0]
        if not past:
            continue
        base_row, base = past[0]
        if mil >= (1 + growth) * base:
            fired[name] = t
            out.append({"name": name, "military": mil, "base": base, "since": base_row["date"],
                        "span": t - step(base_row["date"]), "ours": ours, "ratio": mil / ours})
    return out


def buildup_text(fire: dict, unit: str) -> str:
    """"neighbour buildup: CIVILIZATION_AUSTRALIA 598 military (+73% in 20 turns), 2.0x ours (295)"."""
    return (f"neighbour buildup: {fire['name']} {_num(fire['military'])} military "
            f"(+{fire['military'] / fire['base'] - 1:.0%} in {fire['span']} {unit}), {fire['ratio']:.1f}x ours "
            f"({_num(fire['ours'])})")


def loyalty_falls(before: dict, now: dict, flip_turns: int = 5) -> list[dict]:
    """Cities whose loyalty fell since `before` (ruling 13) and is under 50, or at most `flip_turns` x
    its drop per turn (a flip within about 5 turns): Haarlem 95 -> 77 at T547 (18 a turn) fires there,
    where "under 50" alone waits until T549. [{"name", "loyalty", "drop"}] (drop per turn)."""
    turns = max(1, (now.get("turn") or 0) - (before.get("turn") or 0))
    was = {c.get("name"): c.get("loyalty") for c in before.get("cities") or []}
    out = []
    for c in now.get("cities") or []:
        prev, cur = was.get(c.get("name")), c.get("loyalty")
        if not isinstance(prev, (int, float)) or not isinstance(cur, (int, float)) or cur >= prev:
            continue
        drop = (prev - cur) / turns
        if cur < 50 or cur <= flip_turns * drop:
            out.append({"name": c.get("name"), "loyalty": cur, "drop": drop})
    return out


def loyalty_rose(before: dict, now: dict) -> set[str]:
    """Cities whose loyalty rose since `before` (their loyalty trigger may fire again)."""
    was = {c.get("name"): c.get("loyalty") for c in before.get("cities") or []}
    return {c.get("name") for c in now.get("cities") or []
            if isinstance(was.get(c.get("name")), (int, float)) and isinstance(c.get("loyalty"), (int, float))
            and c["loyalty"] > was[c.get("name")]}
