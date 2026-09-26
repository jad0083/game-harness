"""Pillar strategies: the governor's top-down frame (docs/superpowers/specs/2026-09-26-strategy-layer-design.md).

Game-agnostic: the pillars, directive mapping, metrics, aliases and action limits come from the
game's `PillarSpec` (pillars.py; docs/superpowers/specs/2026-09-26-game-pillars-design.md).
Pure data and rules; no model calls, no game input."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, create_model, model_validator

from .pillars import ACTION_KINDS, ActionLimits, PillarSpec

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
        if isinstance(data.get("metric"), str):     # aliases are the game's: apply_aliases(s, spec)
            data["metric"] = data["metric"].strip()
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


def ranking(s: Strategy, spec: PillarSpec) -> list[str]:
    """Directives in pillar-priority order (pillars without a directive, or not in the spec, are skipped)."""
    return [d for p, _ in s.sorted_pillars() if (d := spec.directive_of(p))]


def apply_aliases(s: Strategy, spec: PillarSpec) -> Strategy:
    """`s` with every milestone metric spelled as the spec's recorded measure."""
    pillars = {name: pl.model_copy(update={"milestones": [m.model_copy(update={"metric": spec.alias(m.metric)})
                                                          for m in pl.milestones]})
               for name, pl in s.pillars.items()}
    return s.model_copy(update={"pillars": pillars})


def _months(date: str) -> int:
    y, m, *_ = (int(x) for x in date.split("."))
    return y * 12 + m - 1


def market_briefing_errors(o: MarketOrder, limits: ActionLimits, idle: set[str], income: dict[str, float]) -> list[str]:
    """Why a market order does not fit today's briefing, per the spec's limits: a sell must be of an
    IDLE resource (sell_requires_idle) and at most sell_income_share of its monthly income. Buys
    have no briefing-dependent rule."""
    if o.side != "sell":
        return []
    errs = []
    if limits.sell_requires_idle and o.resource not in idle:
        errs.append(f"selling {o.resource} but it is not idle")
    if limits.sell_income_share is not None:
        if o.resource not in income:
            errs.append(f"no monthly income known for {o.resource}")
        else:
            cap = limits.sell_income_share * max(income[o.resource], 0.0)
            if o.amount > cap:
                errs.append(f"sell {o.resource} {o.amount} is over {cap:.0f} "
                            f"({limits.sell_income_share:.0%} of monthly income)")
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


def _action_errors(name: str, kind: str, items: list, a: ActionLimits, tech_ids: set[str], idle: set[str],
                   income: dict[str, float], briefing: bool) -> list[str]:
    errs: list[str] = []
    if kind == "tech":
        if len(items) > a.max_items:
            errs.append(f"{name}: at most {a.max_items} preferred techs")
        errs.extend(f"{name}: unknown tech {t!r}" for t in items if t not in tech_ids)
        return errs
    if len(items) > a.max_items:
        errs.append(f"{name}: at most {a.max_items} market order{'' if a.max_items == 1 else 's'}")
    for o in items:
        if o.resource not in a.resources:
            errs.append(f"{name}: unknown market resource {o.resource!r}")
        if a.amount_max is not None and not a.amount_min <= o.amount <= a.amount_max:
            errs.append(f"{name}: {o.side} {o.resource} amount must be {a.amount_min}..{a.amount_max}")
        if briefing and o.resource in a.resources:
            errs.extend(f"{name}: {e}" for e in market_briefing_errors(o, a, idle, income))
    return errs


def validate(s: Strategy, spec: PillarSpec, *, previous: Strategy | None, tech_ids: set[str], idle: set[str],
             income: dict[str, float], briefing_checked: set[str] | None = None,
             require_milestones: bool = True) -> list[str]:
    """Reasons the strategy cannot be used under the game's spec (empty = valid).

    Structural checks (pillars, priorities, sizes, metrics, dates, action ownership and limits) apply
    to every pillar. Briefing-dependent checks (sell only an idle resource, at most a share of its
    income) apply only to `briefing_checked` pillars — by default the ones that changed versus
    `previous` and are not pinned there, so a pinned or untouched pillar that no longer fits today's
    briefing never blocks a review (see `pinned_misfits`). With `require_milestones`, each unpinned
    pillar among the top `spec.min_milestones_top` by priority needs a milestone (human edits pass False)."""
    checked = _briefing_checked(s, previous) if briefing_checked is None else briefing_checked
    n = len(spec.pillars)
    errs: list[str] = []
    errs.extend(f"missing pillar {p}" for p in spec.pillars if p not in s.pillars)
    errs.extend(f"unknown pillar {p!r}" for p in s.pillars if p not in spec.pillars)
    seen: dict[int, str] = {}
    for name, pl in s.pillars.items():
        if pl.priority in seen:
            errs.append(f"duplicate priority {pl.priority} ({seen[pl.priority]}, {name})")
        seen[pl.priority] = name
        if not 1 <= pl.priority <= n:
            errs.append(f"{name}: priority must be 1..{n}")
        if len(pl.stance) > 400:
            errs.append(f"{name}: stance is over 400 characters")
        if len(pl.goals) > 3:
            errs.append(f"{name}: at most 3 goals")
        if any(len(g) > 200 for g in pl.goals):
            errs.append(f"{name}: a goal is over 200 characters")
        if len(pl.milestones) > 6:
            errs.append(f"{name}: at most 6 milestones")
        for m in pl.milestones:
            if not _valid_date(m.by):
                errs.append(f"{name}: milestone by {m.by!r} is not a date YYYY.MM.DD")
            if m.metric not in spec.metrics:
                errs.append(f"{name}: unknown metric {m.metric!r}")
        declared = spec.pillars[name].actions if name in spec.pillars else ()
        for kind, fld in ACTION_KINDS.items():
            items = getattr(pl, fld)
            if not items:
                continue
            if kind not in declared:
                owners = spec.owners(kind)
                errs.append(f"{name}: only the {' / '.join(owners)} pillar may set {fld}" if owners
                            else f"{name}: {fld} is not an action in this game")
            if kind in spec.actions:
                errs.extend(_action_errors(name, kind, items, spec.actions[kind], tech_ids, idle, income,
                                           name in checked))
    if require_milestones and spec.min_milestones_top:
        for name, pl in s.sorted_pillars()[:spec.min_milestones_top]:
            if not pl.pinned and not pl.milestones:
                errs.append(f"{name}: priority {pl.priority} is in the top {spec.min_milestones_top} "
                            "and needs at least one milestone")
    if previous is not None:
        for name, pl in previous.pillars.items():
            if pl.pinned and name in s.pillars and _content(s.pillars[name]) != _content(pl):
                errs.append(f"{name} is pinned by the human and must not change")
    return errs


def pinned_misfits(s: Strategy, spec: PillarSpec, *, idle: set[str], income: dict[str, float]) -> list[str]:
    """One line per pinned pillar whose market orders no longer fit today's briefing, for the
    Strategist's prompt (such a pillar is kept, never rejected: only the human can change it)."""
    limits = spec.actions.get("market")
    if limits is None:
        return []
    out = []
    for name, pl in s.sorted_pillars():
        if not pl.pinned:
            continue
        errs = [e for o in pl.market for e in market_briefing_errors(o, limits, idle, income)]
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


def metric_value(row: dict, metric: str, row_keys: Mapping[str, str] | None = None) -> float | None:
    """A metric from a metrics row; `row_keys` maps a metric to the row field that stores it."""
    if metric.startswith("rank:"):
        st = (row.get("peers") or {}).get(metric[5:]) or {}
        return st.get("rank")
    v = row.get((row_keys or {}).get(metric, metric))
    return float(v) if isinstance(v, (int, float)) else None


def milestone_status(m: Milestone, rows: list[dict], today: str, row_keys: Mapping[str, str] | None = None) -> str:
    """met / on_track / at_risk / missed, from metrics rows (oldest first) up to `today`."""
    series = [(_months(r["date"]), metric_value(r, m.metric, row_keys)) for r in rows if r.get("date")]
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


# ---- the Strategist's output: generated from the spec ---------------------------------------------

class PillarOut(BaseModel):
    """One pillar as the Strategist writes it; action fields are added per pillar from the spec."""
    model_config = ConfigDict(extra="forbid")

    priority: int = Field(description="unique; 1 = first")
    stance: str = Field(description="one or two sentences")
    goals: list[str] = Field(default_factory=list, description="1-3 goals")
    milestones: list[Milestone] = Field(default_factory=list, description="measurable targets with a date")

    @model_validator(mode="before")
    @classmethod
    def _drop_human_fields(cls, data):
        """`pinned`/`edited_by` are the human's: a model echoing them never pins anything."""
        if isinstance(data, dict):
            data = {k: v for k, v in data.items() if k not in ("pinned", "edited_by")}
        return data


class _StrategyOutBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    focus: str = Field(description="one line: what this strategy is about")
    reason: str = Field(default="", description="why it was written or changed")

    @model_validator(mode="before")
    @classmethod
    def _lift_pillars(cls, data):
        """An answer in the stored shape ({"pillars": {id: {...}}, "focus"}) is read as named fields."""
        if isinstance(data, dict) and isinstance(data.get("pillars"), dict):
            data = {**data["pillars"], **{k: v for k, v in data.items() if k != "pillars"}}
        return data


def _action_field(a: ActionLimits):
    if a.kind == "tech":
        return (list[str], Field(default_factory=list,
                                 description=f"tech ids to pick when offered; at most {a.max_items}"))
    if a.kind == "market":
        return (list[MarketOrder], Field(default_factory=list,
                                         description=f"at most {a.max_items} monthly order(s), amount "
                                                     f"{a.amount_min}-{a.amount_max}; resources: {', '.join(a.resources)}"))
    raise ValueError(f"unknown action kind {a.kind!r}")


def review_model(spec: PillarSpec) -> type[BaseModel]:
    """The Strategist's output model for this game: `strategy` has one named optional field per
    pillar (every provider sees named properties), each carrying only the actions it declares."""
    fields = {}
    for pid, p in spec.pillars.items():
        extra = {spec.actions[k].field: _action_field(spec.actions[k]) for k in p.actions if k in spec.actions}
        model = create_model(f"Pillar_{pid}", __base__=PillarOut, **extra) if extra else PillarOut
        fields[pid] = (model | None, Field(default=None, description=f"{p.label}: {p.description}"))
    out = create_model("StrategyOut", __base__=_StrategyOutBase, **fields)
    return create_model(
        "StrategyReview",
        change=(bool, Field(description="false when the current strategy should stay as it is")),
        strategy=(out | None, Field(default=None, description="the full new strategy when change is true")),
        assessment=(str, Field(description="what worked and what did not since the last review, citing numbers")),
        rules=(list[str], Field(default_factory=list, description="0-3 general rules learned (situation -> choice)")),
        identity=(str, Field(default="", description="how our species (its traits by name), ethics, civics and origin "
                                                      "shape this strategy, and which pillars each trait affects")),
    )


def to_strategy(out: BaseModel, spec: PillarSpec) -> Strategy:
    """The stored `Strategy` from a generated `StrategyOut` (pillars the model left out stay out, so
    `validate` names them missing); metric aliases applied."""
    pillars = {}
    for pid in spec.pillars:
        p = getattr(out, pid, None)
        if p is not None:
            pillars[pid] = Pillar.model_validate(p.model_dump())
    return apply_aliases(Strategy(pillars=pillars, focus=out.focus, reason=out.reason), spec)


def strategist_instructions(spec: PillarSpec) -> str:
    """The Strategist's instructions: pillars, metrics and action limits from the spec, then the
    game's own rules (`[strategy] instructions`)."""
    lines = [("You are the Strategist: you set the top-down strategy. Write one entry per pillar, each under "
              "its own field named by the pillar id:")]
    for p in spec.pillars.values():
        ranks = f"ranks the directive {p.directive}" if p.directive else "ranks no directive"
        lines.append(f"- {p.id} ({p.label}): {p.description} [{ranks}]")
    lines.append(f"Each pillar: a unique priority (1..{len(spec.pillars)}, 1 = first), a stance of one or two "
                 "sentences, 1-3 goals, and milestones on the briefing's measures (exactly these names: "
                 + ", ".join(spec.metrics) + "; a rank is 1 = best, so use op <= for it) with a target and an "
                 "in-game date YYYY.MM.DD.")
    if spec.min_milestones_top:
        lines.append(f"Each of the {spec.min_milestones_top} highest-priority pillars needs at least one milestone.")
    for kind, a in spec.actions.items():
        owners = spec.owners(kind)
        if not owners:
            continue
        on = " and ".join(owners)
        if kind == "tech":
            lines.append(f"Only {on}: `{a.field}` (tech ids to pick when offered; at most {a.max_items}).")
        else:
            rule = (f"at most {a.max_items} small monthly order{'' if a.max_items == 1 else 's'}, amount "
                    f"{a.amount_min}-{a.amount_max}; resources: {', '.join(a.resources)}")
            if a.sell_requires_idle:
                rule += "; sell only a resource the briefing lists as IDLE"
            if a.sell_income_share is not None:
                rule += f", at most {a.sell_income_share:.0%} of its monthly income"
            lines.append(f"Only {on}: `{a.field}` ({rule}).")
        if a.note:
            lines.append(a.note)
    lines.append("Priorities decide which directives the governor prefers. Never change a pillar marked pinned: "
                 "the human set it. If nothing material changed, answer change=false.")
    lines.append("Build on our species (race) and its traits, ethics, civics and origin: fill `identity` with how "
                 "they shape this strategy, naming the traits you rely on and the pillars they affect (e.g. "
                 "industrious → economy on minerals; enduring → long wars are affordable), and weigh a "
                 "neighbour's traits when dealing with or fighting it.")
    if spec.instructions:
        lines.append(spec.instructions)
    return "\n".join(lines)
