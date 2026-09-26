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
_ROW_KEY = {"colonies": "planets"}          # metrics rows store colonies as `planets`


class Milestone(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: str
    op: Literal[">=", "<="]
    target: float
    by: str = Field(description="in-game date YYYY.MM.DD")

    def __init__(self, **data):
        by = data.get("by")
        if by and not re.match(r"^\d{4}\.\d{2}\.\d{2}$", by):
            raise ValueError(f"by {by!r} is not a date YYYY.MM.DD")
        if by and re.match(r"^\d{4}\.\d{2}\.\d{2}$", by):
            _, m, _ = map(int, by.split("."))
            if not 1 <= m <= 12:
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

    def ranking(self) -> list[str]:
        """Directives in pillar-priority order (pillars without a directive are skipped)."""
        ordered = sorted(self.pillars.items(), key=lambda kv: kv[1].priority)
        return [DIRECTIVE_OF[p] for p, _ in ordered if DIRECTIVE_OF.get(p)]


def _months(date: str) -> int:
    y, m, *_ = (int(x) for x in date.split("."))
    return y * 12 + m - 1


def validate(s: Strategy, *, previous: Strategy | None, tech_ids: set[str], idle: set[str],
             income: dict[str, float]) -> list[str]:
    """Reasons the strategy cannot be used (empty = valid)."""
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
        for m in pl.milestones:
            if not re.match(r"^\d{4}\.\d{2}\.\d{2}$", m.by):
                errs.append(f"{name}: milestone by {m.by!r} is not a date YYYY.MM.DD")
            else:
                _, mo, _ = map(int, m.by.split("."))
                if not 1 <= mo <= 12:
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
        if len(pl.market) > 2:
            errs.append(f"{name}: at most 2 market orders")
        for o in pl.market:
            if o.resource == "trade":
                errs.append(f"{name}: trade cannot be sold or bought on the market")
                continue
            cap = 0.2 * max(income.get(o.resource, 0.0), 0.0)
            if o.side == "sell" and o.resource not in idle:
                errs.append(f"{name}: selling {o.resource} but it is not idle")
            if o.side == "sell":
                if o.resource not in income:
                    errs.append(f"{name}: no monthly income known for {o.resource}")
                elif o.amount > cap:
                    errs.append(f"{name}: sell {o.resource} {o.amount} is over {cap:.0f} (20% of monthly income)")
    if previous is not None:
        for name, pl in previous.pillars.items():
            if pl.pinned and name in s.pillars:
                prev_content = pl.model_dump(exclude={"pinned", "edited_by"})
                new_content = s.pillars[name].model_dump(exclude={"pinned", "edited_by"})
                if new_content != prev_content:
                    errs.append(f"{name} is pinned by the human and must not change")
    return errs


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
