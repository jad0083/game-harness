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
