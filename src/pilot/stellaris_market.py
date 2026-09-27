"""Market buy rules for the Stellaris governor (docs/design/2026-09-27-stellaris-levers-design.md, rulings
9-10). Pure: no game access; the numbers come from `[actions.market.buy]` in pillars.toml (BuyRules).

- Price per unit = 100 / market_amount x (1 + fluctuation) x (1 + fee); the fluctuation comes from the
  briefing's `market.fluct` (percent), taken as 0 without a market block ("price unknown").
- Reserve: trade - 12 x max(0, cost - trade income) >= trade_reserve (2,500, where the AI's own market
  spending starts). Spend cap: cost <= income_share x max(trade income, 0) + (trade - reserve) /
  surplus_months (income_share 0.5 for alloys in a war crisis).
- Price guard: no new order above skip_above_pct; an order already in the save is dropped above
  never_above_pct, and buying more of it than its amount there is a new order (above skip_above_pct
  the order in place stays at its amount: `keep_placed`). Volume: at most `volume[kind]` base amounts a month (1 internal, 6 galactic).
- Never what the AI buys anyway: a deficit with under ai_cover_months of stock, a resource the AI
  bought since the last save, an IDLE one, alloys at naval_full of naval capacity outside a crisis.
- Idle-trade fill: while trade is IDLE and no declared order passed, the first deficit with
  ai_cover_months..cover_months of stock (strategic_cover_months for motes, gases and crystals),
  1.2 x its deficit, that passes every rule and whose start amount is measured."""

from __future__ import annotations

import math
from collections.abc import Callable

from .pillars import ActionLimits, BuyRules


def _market(b: dict) -> dict | None:
    m = b.get("market")
    return m if isinstance(m, dict) else None


def fluct(res: str, b: dict) -> float:
    """The resource's price fluctuation in percent (0 when the save shows none)."""
    return float(((_market(b) or {}).get("fluct") or {}).get(res) or 0.0)


def unit_price(res: str, b: dict, rules: BuyRules) -> tuple[float | None, bool]:
    """(trade per unit, whether the fluctuation is known); None for a resource without a base price."""
    amount = rules.base_amount.get(res)
    if not amount:
        return None, False
    return 100.0 / amount * (1 + fluct(res, b) / 100.0) * (1 + rules.fee), _market(b) is not None


def market_kind(b: dict) -> str:
    """"galactic" or "internal"; unknown counts as internal (the smaller volume)."""
    return (_market(b) or {}).get("kind") or "internal"


def volume_cap(res: str, b: dict, rules: BuyRules) -> int:
    """Units a month: `volume[kind]` base amounts (alloys 25 internal, 150 galactic)."""
    per = rules.volume.get(market_kind(b), min(rules.volume.values()))
    return int(rules.base_amount.get(res, 0) * per)


def naval_use(b: dict) -> float | None:
    """Used / maximum naval capacity from the Governor Bridge export (levers ruling 19), or None when
    the save has no current export (no mod, or a stale one)."""
    gv = b.get("governor_vars") or {}
    cap = gv.get("governor_naval_cap")
    if b.get("governor_vars_stale") or not isinstance(cap, (int, float)) or cap <= 0:
        return None
    used = gv.get("governor_naval_used", b.get("used_naval_capacity"))
    return float(used) / cap if isinstance(used, (int, float)) else None


def _n(v: float) -> str:
    return f"{v:.0f}" if abs(v) >= 100 or float(v).is_integer() else f"{v:.1f}"


def ai_bought(res: str, b: dict, prev: dict | None) -> float:
    """What the AI itself bought of `res` since the previous save: the rise of our cumulative `bought`
    less what our own monthly trade delivered (`trades_net`, last month) in the months between."""
    now, before = ((_market(b) or {}).get("bought") or {}), ((_market(prev or {}) or {}).get("bought") or {})
    if not prev or res not in now:
        return 0.0
    ours = max(0.0, float(((_market(b) or {}).get("trades_net") or {}).get(res) or 0.0))
    months = 1
    try:
        y1, m1, *_ = (int(x) for x in str(prev.get("date")).split("."))
        y2, m2, *_ = (int(x) for x in str(b.get("date")).split("."))
        months = max(1, (y2 - y1) * 12 + m2 - m1)
    except ValueError:
        pass
    return float(now.get(res) or 0.0) - float(before.get(res) or 0.0) - ours * months


def buy_errors(order: dict, b: dict, prev: dict | None, rules: BuyRules, idle: set[str], *,
               placed: float = 0, crisis: bool = False) -> list[str]:
    """Why buy `order` breaks the rules on save `b` (`prev`: the save before it; `idle`: resources the
    briefing flags IDLE; `placed`: the amount of this side and resource the save already holds, 0 for
    none; `crisis`: a war crisis is on). Empty: allowed. Sells are not checked here."""
    if order.get("side") != "buy":
        return []
    res, amount = order.get("resource"), int(order.get("amount") or 0)
    price, _known = unit_price(res, b, rules)
    if price is None:
        return [f"no base price for {res}"]
    errs: list[str] = []
    pct = fluct(res, b)
    if pct > rules.never_above_pct:
        errs.append(f"price {pct:+.0f}% over base: never bought above +{rules.never_above_pct:.0f}%")
    elif pct > rules.skip_above_pct and amount > placed:      # up to the amount in place it is no new buy
        errs.append(f"price {pct:+.0f}% over base: no new order above +{rules.skip_above_pct:.0f}%" if not placed
                    else f"price {pct:+.0f}% over base: no raise above +{rules.skip_above_pct:.0f}% ({_n(placed)} in place)")
    cap = volume_cap(res, b, rules)
    if amount > cap:
        errs.append(f"{amount} is over the volume cap of {cap} a month on the {market_kind(b)} market")
    stock, net = (b.get("stockpile") or {}), (b.get("net") or {})
    n = net.get(res)
    if isinstance(n, (int, float)) and n < 0 and float(stock.get(res) or 0) < rules.ai_cover_months * -n:
        errs.append(f"the AI buys {res} itself ({float(stock.get(res) or 0) / -n:.1f} months of cover, under "
                    f"{rules.ai_cover_months:g})")
    got = ai_bought(res, b, prev)
    if got > 0.5:
        errs.append(f"the AI bought {_n(got)} {res} since the last save")
    if res in idle:
        errs.append(f"{res} is IDLE")
    use = naval_use(b)
    if res == "alloys" and not crisis and use is not None and use >= rules.naval_full:
        errs.append(f"the fleet is at {use:.0%} of naval capacity (alloys wait for room)")
    trade, income = float(stock.get("trade") or 0.0), float(net.get("trade") or 0.0)
    cost = amount * price
    left = trade - 12 * max(0.0, cost - income)
    if left < rules.trade_reserve:
        errs.append(f"reserve: {_n(trade)} trade - 12 x {_n(max(0.0, cost - income))} over income leaves "
                    f"{_n(left)}, under the {rules.trade_reserve:.0f} kept")
    share = rules.crisis_income_share if crisis and res == "alloys" else rules.income_share
    limit = share * max(income, 0.0) + (trade - rules.trade_reserve) / rules.surplus_months
    if cost > limit:
        errs.append(f"costs {_n(cost)} trade a month, over the spend cap of {_n(max(limit, 0.0))}")
    return errs


def keep_placed(order: dict, placed: float, errors: Callable[[dict], list[str]]) -> tuple[dict | None, list[str]]:
    """(`order`, []) when `errors` finds nothing wrong with it. When it raises an order the save holds
    (`placed`, a smaller amount) and breaks a rule that the amount in place does not, (that order at
    its amount, the raise's errors): the raise is refused and the order in place is not removed. Else
    (None, its errors)."""
    errs = errors(order)
    if not errs:
        return order, []
    if 0 < placed < int(order.get("amount") or 0):
        kept = {**order, "amount": int(placed)}
        if not errors(kept):
            return kept, errs
    return None, errs


def cover_candidates(b: dict, limits: ActionLimits) -> list[tuple[float, dict]]:
    """Deficits with ai_cover_months..cover_months of stock left (strategic_cover_months for the
    strategic resources), most urgent first: (months of cover, buy 1.2 x the deficit, capped by the
    volume and amount_max)."""
    rules = limits.buy
    stock, net = (b.get("stockpile") or {}), (b.get("net") or {})
    out = []
    for i, res in enumerate(limits.resources):
        n = net.get(res)
        if res not in rules.base_amount or not isinstance(n, (int, float)) or n >= 0:
            continue
        cover = float(stock.get(res) or 0.0) / -n
        top = rules.strategic_cover_months if res in rules.strategic else rules.cover_months
        if not rules.ai_cover_months <= cover <= top:
            continue
        amount = min(math.ceil(rules.cover_factor * -n - 1e-9), volume_cap(res, b, rules),
                     limits.amount_max or math.inf)
        out.append((cover, i, {"side": "buy", "resource": res, "amount": max(int(amount), limits.amount_min)}))
    return [(c, o) for c, _i, o in sorted(out, key=lambda x: (x[0], x[1]))]


def idle_fill(b: dict, prev: dict | None, limits: ActionLimits, idle: set[str], measured: set[str],
              blocked: Callable[[str, str], str | None] | None = None, *,
              placed: Callable[[dict], float] = lambda _o: 0) -> tuple[dict | None, str]:
    """The order that fills an empty slot while trade is IDLE: the first deficit-cover candidate that
    passes every buy rule, whose start amount is `measured`, and that `blocked(side, resource)` does
    not hold back (a suspension); a candidate raising the order in place (`placed(order)`: its amount)
    past a rule keeps that order at its amount. (order, "" or why it was kept) or (None, why nothing
    qualifies)."""
    rules = limits.buy
    if rules is None:
        return None, "no buy rules"
    candidates = cover_candidates(b, limits)
    if not candidates:
        return None, (f"no resource in deficit with {rules.ai_cover_months:g}-{rules.cover_months:g} months of "
                      f"cover ({rules.strategic_cover_months:g} for {', '.join(rules.strategic) or 'none'})")
    why = []
    for _cover, o in candidates:
        res = o["resource"]
        if res not in measured:
            why.append(f"{res}: start amount not measured")
            continue
        held = blocked(o["side"], res) if blocked else None
        if held:
            why.append(f"{res}: {held}")
            continue
        have = placed(o)
        got, errs = keep_placed(o, have, lambda x, have=have: buy_errors(x, b, prev, rules, idle, placed=have))
        if got is None:
            why.append(f"{res}: {'; '.join(errs)}")
            continue
        return got, (f"kept at the {got['amount']} in place, not {o['amount']}: {'; '.join(errs)}" if errs else "")
    return None, " | ".join(why)
