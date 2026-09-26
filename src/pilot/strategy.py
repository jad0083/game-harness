"""Pillar strategies: the governor's top-down frame (docs/superpowers/specs/2026-09-26-strategy-layer-design.md).

Pure data and rules; no model calls, no game input."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PILLARS = ("economy", "expansion", "technology", "diplomacy", "defence", "government", "society")
DIRECTIVE_OF: dict[str, str | None] = {"economy": "consolidate_economy", "expansion": "expand", "technology": "tech_rush",
                                       "diplomacy": "diplomacy_first", "defence": "defend", "government": None, "society": None}
RANK_MEASURES = ("systems", "pops", "techs", "military_power", "economy_power", "tech_power", "colonies")
METRICS = ("systems", "colonies", "pops", "techs_known", "military_power", "economy_power", "tech_power",
           *(f"rank:{m}" for m in RANK_MEASURES))
# Spellings models use for the recorded measures (seen live: "rank:military" on 2452.03).
_SHORT = {"military": "military_power", "economy": "economy_power", "tech": "tech_power", "planets": "colonies"}
METRIC_ALIASES = {**_SHORT, "techs": "techs_known", **{f"rank:{k}": f"rank:{v}" for k, v in _SHORT.items()}}
_ROW_KEY = {"colonies": "planets"}          # metrics rows store colonies as `planets`
_DATE_RE = re.compile(r"^\d{4}\.(\d{2})\.\d{2}$")


def _valid_date(s: str) -> bool:
    m = _DATE_RE.match(s)
    return bool(m) and 1 <= int(m.group(1)) <= 12


class Milestone(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: str
    op: Literal[">=", "<="]
    target: float
    by: str = Field(description="in-game date YYYY.MM.DD")

    def __init__(self, **data):
        if isinstance(data.get("metric"), str):     # common model spellings of the recorded measures
            data["metric"] = METRIC_ALIASES.get(data["metric"].strip(), data["metric"].strip())
        by = data.get("by")
        if by and not _valid_date(by):
            raise ValueError(f"by {by!r} is not a date YYYY.MM.DD")
        super().__init__(**data)


class MarketOrder(BaseModel):
    model_config = ConfigDict(extra="forbid")

    side: Literal["sell", "buy"]
    resource: str
    amount: int = Field(gt=0)


class Pillar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    priority: int
    stance: str
    goals: list[str] = Field(default_factory=list)
    milestones: list[Milestone] = Field(default_factory=list)
    prefer_techs: list[str] = Field(default_factory=list)
    market: list[MarketOrder] = Field(default_factory=list)
    pinned: bool = False
    edited_by: Literal["model", "human"] = "model"


class Strategy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pillars: dict[str, Pillar]
    focus: str
    reason: str = ""
    identity: str = ""      # how our species, traits, ethics, civics and origin shape this strategy

    def sorted_pillars(self) -> list[tuple[str, Pillar]]:
        """(name, pillar) pairs in priority order."""
        return sorted(self.pillars.items(), key=lambda kv: kv[1].priority)

    def ranking(self) -> list[str]:
        """Directives in pillar-priority order (pillars without a directive are skipped)."""
        return [DIRECTIVE_OF[p] for p, _ in self.sorted_pillars() if DIRECTIVE_OF.get(p)]


def _months(date: str) -> int:
    y, m, *_ = (int(x) for x in date.split("."))
    return y * 12 + m - 1


# One set of market rules, shared with the controller's market_sync tool (mcp.rs
# validate_market_orders; tests keep the two equal). MARKET_RESOURCES are the keys of
# corpora/stellaris/manifest.toml [ui.market.resources]; trade is not a market resource.
MARKET_RESOURCES = ("energy", "minerals", "food", "consumer_goods", "alloys", "volatile_motes", "exotic_gases",
                    "rare_crystals", "sr_living_metal", "sr_zro", "sr_dark_matter")
MARKET_MIN_AMOUNT = 1
MARKET_MAX_AMOUNT = 25
SELL_INCOME_SHARE = 0.2      # a sell order takes at most 20% of that resource's monthly income
# At most one order until ui.market.order_row_pitch is measured live: the controller can only
# find (and so remove) the first order row.
MAX_MARKET_ORDERS = 1


def market_briefing_errors(o: MarketOrder, idle: set[str], income: dict[str, float]) -> list[str]:
    """Why a market order does not fit today's briefing: a sell must be of an IDLE resource and at
    most 20% of its monthly income. Buys have no briefing-dependent rule."""
    if o.side != "sell":
        return []
    errs = []
    if o.resource not in idle:
        errs.append(f"selling {o.resource} but it is not idle")
    if o.resource not in income:
        errs.append(f"no monthly income known for {o.resource}")
    else:
        cap = SELL_INCOME_SHARE * max(income[o.resource], 0.0)
        if o.amount > cap:
            errs.append(f"sell {o.resource} {o.amount} is over {cap:.0f} (20% of monthly income)")
    return errs


def _content(pl: Pillar) -> dict:
    return pl.model_dump(exclude={"pinned", "edited_by"})


def _briefing_checked(s: Strategy, previous: Strategy | None) -> set[str]:
    """Pillars that changed versus `previous` and are not pinned there (all of them without one)."""
    if previous is None:
        return set(s.pillars)
    out = set()
    for name, pl in s.pillars.items():
        old = previous.pillars.get(name)
        if old is None or (not old.pinned and _content(pl) != _content(old)):
            out.add(name)
    return out


def validate(s: Strategy, *, previous: Strategy | None, tech_ids: set[str], idle: set[str],
             income: dict[str, float], briefing_checked: set[str] | None = None) -> list[str]:
    """Reasons the strategy cannot be used (empty = valid).

    Structural checks (pillars, priorities, sizes, metrics, dates, techs, market resource, side,
    amount and count) apply to every pillar. Briefing-dependent checks (sell only an idle resource,
    at most 20% of its income) apply only to `briefing_checked` pillars — by default the ones that
    changed versus `previous` and are not pinned there, so a pinned or untouched pillar that no
    longer fits today's briefing never blocks a review (see `pinned_misfits`)."""
    checked = _briefing_checked(s, previous) if briefing_checked is None else briefing_checked
    errs: list[str] = []
    for p in PILLARS:
        if p not in s.pillars:
            errs.append(f"missing pillar {p}")
    for p in s.pillars:
        if p not in PILLARS:
            errs.append(f"unknown pillar {p!r}")
    seen: dict[int, str] = {}
    for name, pl in s.pillars.items():
        if pl.priority in seen:
            errs.append(f"duplicate priority {pl.priority} ({seen[pl.priority]}, {name})")
        seen[pl.priority] = name
        if not 1 <= pl.priority <= len(PILLARS):
            errs.append(f"{name}: priority must be 1..{len(PILLARS)}")
        if len(pl.stance) > 400:
            errs.append(f"{name}: stance is over 400 characters")
        if len(pl.goals) > 3:
            errs.append(f"{name}: at most 3 goals")
        for g in pl.goals:
            if len(g) > 200:
                errs.append(f"{name}: a goal is over 200 characters")
        if len(pl.milestones) > 6:
            errs.append(f"{name}: at most 6 milestones")
        for m in pl.milestones:
            if not _valid_date(m.by):
                errs.append(f"{name}: milestone by {m.by!r} is not a date YYYY.MM.DD")
            if m.metric not in METRICS:
                errs.append(f"{name}: unknown metric {m.metric!r}")
        if pl.prefer_techs and name != "technology":
            errs.append(f"{name}: only the technology pillar prefers techs")
        if len(pl.prefer_techs) > 6:
            errs.append(f"{name}: at most 6 preferred techs")
        for t in pl.prefer_techs:
            if t not in tech_ids:
                errs.append(f"{name}: unknown tech {t!r}")
        if pl.market and name != "economy":
            errs.append(f"{name}: only the economy pillar places market orders")
        if len(pl.market) > MAX_MARKET_ORDERS:
            errs.append(f"{name}: at most {MAX_MARKET_ORDERS} market order")
        for o in pl.market:
            if o.resource == "trade":
                errs.append(f"{name}: trade cannot be sold or bought on the market")
                continue
            if o.resource not in MARKET_RESOURCES:
                errs.append(f"{name}: unknown market resource {o.resource!r}")
            if not MARKET_MIN_AMOUNT <= o.amount <= MARKET_MAX_AMOUNT:
                errs.append(f"{name}: {o.side} {o.resource} amount must be {MARKET_MIN_AMOUNT}..{MARKET_MAX_AMOUNT}")
            if name in checked:
                errs.extend(f"{name}: {e}" for e in market_briefing_errors(o, idle, income))
    if previous is not None:
        for name, pl in previous.pillars.items():
            if pl.pinned and name in s.pillars and _content(s.pillars[name]) != _content(pl):
                errs.append(f"{name} is pinned by the human and must not change")
    return errs


def pinned_misfits(s: Strategy, *, idle: set[str], income: dict[str, float]) -> list[str]:
    """One line per pinned pillar whose market orders no longer fit today's briefing, for the
    Strategist's prompt (such a pillar is kept, never rejected: only the human can change it)."""
    out = []
    for name, pl in s.sorted_pillars():
        if not pl.pinned:
            continue
        errs = [e for o in pl.market for e in market_briefing_errors(o, idle, income)]
        if errs:
            out.append(f"pinned {name} no longer fits: {'; '.join(errs)}")
    return out


def keep_pinned(new: Strategy, previous: Strategy | None) -> Strategy:
    """`new` with every pinned pillar of `previous` put back unchanged."""
    if previous is None:
        return new
    pillars = dict(new.pillars)
    for name, pl in previous.pillars.items():
        if pl.pinned:
            pillars[name] = pl.model_copy(deep=True)
    return new.model_copy(update={"pillars": pillars})


def metric_value(row: dict, metric: str) -> float | None:
    if metric.startswith("rank:"):
        st = (row.get("peers") or {}).get(metric[5:]) or {}
        return st.get("rank")
    v = row.get(_ROW_KEY.get(metric, metric))
    return float(v) if isinstance(v, (int, float)) else None


def milestone_status(m: Milestone, rows: list[dict], today: str) -> str:
    """met / on_track / at_risk / missed, from metrics rows (oldest first) up to `today`."""
    series = [(_months(r["date"]), metric_value(r, m.metric)) for r in rows if r.get("date")]
    series = [(mo, v) for mo, v in series if v is not None and mo <= _months(today)]
    ok = (lambda v: v >= m.target) if m.op == ">=" else (lambda v: v <= m.target)
    if any(ok(v) for _, v in series):
        return "met"
    if _months(today) > _months(m.by):
        return "missed"
    if len(series) < 2:
        return "at_risk"
    now_mo, now = series[-1]
    past = next(((mo, v) for mo, v in reversed(series) if now_mo - mo >= 12), None)
    if past is None:
        return "at_risk"
    span = max(now_mo - past[0], 1)
    projected = now + (now - past[1]) / span * (_months(m.by) - now_mo)
    return "on_track" if ok(projected) else "at_risk"
