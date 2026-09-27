"""The war crisis overlay for the Stellaris governor (docs/design/2026-09-27-stellaris-levers-design.md,
rulings 12-16). Pure: no game access.

Entry needs losses at war, never a ratio (E6: a military ratio would hold 90-97% of the time), a battle
count (allies' battles are in it, E7) or war exhaustion. At least one war on, and any of:
- C1 a colony of ours is occupied;
- C2 systems <= the most in the last 12 months - 2;
- C3 military <= half the most in the last 12 months (0 included);
- C4 a colony was lost since the previous save;
- C5 a ground battle at one of our colonies since the previous save (an invasion index at or past that
  save's `battle_count` of the same war; a retaken colony's old invasion is not new);
- C6 a colony under stability 25 on 2 saves in a row (the planet check).
It enters on the transition, at most once per war per 12 months, and leaves when every war ended, or
after 6 saves in a row with none of C1-C6 once held 6 months. The governor runs the ladder (review,
defend, posture, crisis alloys, cadence 3, the status-quo question) while it is on."""

from __future__ import annotations

from .pillars import ActionLimits
from .stellaris_market import buy_errors, naval_use, unit_price, volume_cap

RECENT_MONTHS = 12
SYSTEMS_LOST = 2
MILITARY_SHARE = 0.5
QUIET_SAVES = 6
MIN_HOLD_MONTHS = 6
WAR_ENTRY_MONTHS = 12          # one entry per war per this many months
POSTURE_GAP_MONTHS = 6         # the war_crisis posture toggles at most once per this many months
CRISIS_PACE = 3                # months between decisions while the crisis lasts
STATUS_QUO_EXHAUSTION = 0.6
ALLOYS_WITHOUT_NAVAL = 1000    # naval use unknown: crisis alloys only under this stock


def _months(date: str) -> int:
    y, m, *_ = (int(x) for x in str(date).split("."))
    return y * 12 + m - 1


def _n(v) -> str:
    return f"{v:.0f}" if isinstance(v, (int, float)) else str(v)


def _recent(rows: list[dict], now: dict) -> list[dict]:
    """Metrics rows dated in the 12 months before save `now`."""
    m = _months(now["date"])
    return [r for r in rows if r.get("date") and 0 < m - _months(r["date"]) <= RECENT_MONTHS]


def _war_key(w: dict) -> str:
    return str(w.get("id") or w.get("name") or "")


def conditions(rows: list[dict], now: dict, prev: dict | None, low_stability=()) -> list[tuple[str, str]]:
    """The entry conditions C1-C6 that hold on save `now` (whatever the war state): (code, text).
    `rows`: metrics rows before it; `prev`: the save before it (None: C4 and C5 cannot be told);
    `low_stability`: colonies under 25 on this save and the one before (stellaris_planets)."""
    out: list[tuple[str, str]] = []
    planets = now.get("planets") or []
    occupied = [p.get("name") or str(p.get("id")) for p in planets if p.get("occupied")]
    if occupied:
        out.append(("C1", f"{', '.join(occupied)} occupied"))
    recent = _recent(rows, now)
    systems = [r["systems"] for r in recent if isinstance(r.get("systems"), (int, float))]
    if systems and isinstance(now.get("systems"), (int, float)) and now["systems"] <= max(systems) - SYSTEMS_LOST:
        out.append(("C2", f"systems {_n(now['systems'])} ({_n(max(systems))} at most in 12 months)"))
    military = [r["military_power"] for r in recent if isinstance(r.get("military_power"), (int, float))]
    top = max(military, default=0)
    mil = now.get("military_power")
    if top > 0 and isinstance(mil, (int, float)) and mil <= MILITARY_SHARE * top:
        out.append(("C3", f"military {_n(mil)} ({_n(top)} at most in 12 months)"))
    if prev is not None and len(planets) < len(prev.get("planets") or []):
        out.append(("C4", f"colony lost ({len(prev.get('planets') or [])} -> {len(planets)})"))
    if prev is not None:
        before = {_war_key(w): int(w.get("battle_count") or 0) for w in prev.get("wars") or []}
        invaded = [w.get("name") or _war_key(w) for w in now.get("wars") or []
                   if any(i >= before.get(_war_key(w), 0) for i in (w.get("own_battles_12m") or {}).get("invasions") or [])]
        if invaded:
            out.append(("C5", f"our colonies invaded ({'; '.join(invaded)})"))
    if low_stability:
        out.append(("C6", f"stability under 25 twice: {', '.join(low_stability)}"))
    return out


def war_crisis(rows: list[dict], now: dict, prev: dict | None, low_stability=()) -> list[tuple[str, str]]:
    """The conditions of a war going badly on save `now`: C1-C6 while at least one war is on, else []."""
    if not now.get("wars"):
        return []
    return conditions(rows, now, prev, low_stability)


def crisis_step(state: dict | None, rows: list[dict], now: dict, prev: dict | None,
                low_stability=()) -> tuple[dict, str | None]:
    """The crisis state after save `now`: (state, "enter" | "exit: <why>" | None). `state` holds
    active, since, conditions, quiet (saves in a row without any condition) and entries (war -> the
    month of its last entry)."""
    s = {"active": False, "since": None, "conditions": [], "quiet": 0, "entries": {}, **(state or {})}
    s["entries"] = dict(s["entries"])
    now_m, wars = _months(now["date"]), [_war_key(w) for w in now.get("wars") or []]
    conds = war_crisis(rows, now, prev, low_stability)
    if not s["active"]:
        fresh = [w for w in wars if now_m - s["entries"].get(w, -10 ** 9) >= WAR_ENTRY_MONTHS]
        if not conds or not fresh:
            return s, None
        s.update(active=True, since=now["date"], conditions=[list(c) for c in conds], quiet=0,
                 wars=wars, entries={**s["entries"], **{w: now_m for w in wars}})
        return s, "enter"
    if not wars:
        s.update(active=False, quiet=0)
        return s, "exit: every war ended"
    if conds:
        s.update(quiet=0, conditions=[list(c) for c in conds], wars=wars)
        return s, None
    s["quiet"] += 1
    if s["quiet"] >= QUIET_SAVES and now_m - _months(s["since"]) >= MIN_HOLD_MONTHS:
        s.update(active=False)
        return s, f"exit: {QUIET_SAVES} quiet saves"
    return s, None


def status_quo(now: dict, rows: list[dict], conds: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """The wars to ask the human about (ruling 15), with the question: when a colony is occupied (C1) or
    systems fell (C2), or our war exhaustion is 0.6 or more and at least theirs, or their side can
    force a status quo on us. The harness never proposes peace itself."""
    have = {c for c, _ in conds}
    recent = _recent(rows, now)
    top = max([r["systems"] for r in recent if isinstance(r.get("systems"), (int, float))], default=now.get("systems"))
    occupied = [p.get("name") for p in now.get("planets") or [] if p.get("occupied")]
    out = []
    for w in now.get("wars") or []:
        ours, theirs = float(w.get("our_exhaustion") or 0), float(w.get("their_exhaustion") or 0)
        forced = bool((w.get("force_peace") or {}).get("ours"))
        if not (have & {"C1", "C2"} or (ours >= STATUS_QUO_EXHAUSTION and ours >= theirs) or forced):
            continue
        q = (f"Accept a status-quo peace in '{w.get('name') or _war_key(w)}'? Systems {_n(top)} -> "
             f"{_n(now.get('systems'))} in 12 months; war exhaustion ours {ours:.0%}, theirs {theirs:.0%}"
             + (f"; occupied: {', '.join(occupied)}" if occupied else "")
             + ("; their side can force a status quo on us now" if forced else "")
             + ". Only you can offer it (War screen); the harness never proposes peace, and the crisis steps go on.")
        out.append((_war_key(w), q))
    return out


def crisis_alloys(b: dict, prev: dict | None, limits: ActionLimits, idle: set[str], measured: set[str],
                  blocked=None) -> tuple[dict | None, str]:
    """The war crisis market step (ruling 13, step 5): buy alloys when a shipyard sits in a system we
    control, naval use is known under 95% (or unknown with under 1,000 alloys in stock), alloys are not
    IDLE, their start amount is measured and every buy rule passes at the crisis cap. The amount is the
    most the crisis cap and the reserve allow, at most the volume cap and amount_max. (order, "") or
    (None, why not)."""
    rules = limits.buy
    if rules is None or "alloys" not in limits.resources:
        return None, "no alloys buy rules"
    if "alloys" not in measured:
        return None, "alloys start amount not measured (live check L2)"
    held = blocked("buy", "alloys") if blocked else None
    if held:
        return None, f"alloys {held}"
    if not any(not y.get("occupied") for y in b.get("shipyards") or []):
        return None, "no shipyard in a system we control"
    use = naval_use(b)
    stock = float((b.get("stockpile") or {}).get("alloys") or 0.0)
    if use is not None and use >= rules.naval_full:
        return None, f"the fleet is at {use:.0%} of naval capacity"
    if use is None and stock >= ALLOYS_WITHOUT_NAVAL:
        return None, f"naval use unknown and {stock:.0f} alloys in stock"
    if "alloys" in idle:
        return None, "alloys are IDLE"
    price, _known = unit_price("alloys", b, rules)
    trade, income = float((b.get("stockpile") or {}).get("trade") or 0.0), float((b.get("net") or {}).get("trade") or 0.0)
    budget = min(rules.crisis_income_share * max(income, 0.0) + (trade - rules.trade_reserve) / rules.surplus_months,
                 income + (trade - rules.trade_reserve) / 12)
    amount = min(int(budget // price) if price and budget > 0 else 0, volume_cap("alloys", b, rules),
                 limits.amount_max or 10 ** 6)
    order = {"side": "buy", "resource": "alloys", "amount": max(amount, limits.amount_min)}
    errs = buy_errors(order, b, prev, rules, idle, crisis=True)
    if amount < limits.amount_min or errs:
        return None, "; ".join(errs) or "the reserve leaves nothing to spend"
    return order, ""
