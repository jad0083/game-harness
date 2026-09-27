"""Pillar strategies: the governor's top-down frame (docs/superpowers/specs/2026-09-26-strategy-layer-design.md).

Game-agnostic: the pillars, directive mapping, metrics, aliases and action limits come from the
game's `PillarSpec` (pillars.py; docs/superpowers/specs/2026-09-26-game-pillars-design.md).
Pure data and rules; no model calls, no game input."""

from __future__ import annotations

import json
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

    weight: int = 0         # share of the empire's effort; all pillars sum to 100
    priority: int = 0       # derived: rank by weight, 1 = heaviest (set by Strategy)
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

    @model_validator(mode="after")
    def _weights_and_ranks(self):
        """A strategy stored with ranks only (before weights) gets weights from its ranks; then every
        pillar's `priority` is set to its rank by weight. Works on copies: the pillars passed in may be
        shared with other strategies."""
        self.pillars = {n: pl.model_copy() for n, pl in self.pillars.items()}
        if self.pillars and not any(pl.weight for pl in self.pillars.values()):
            by_rank = sorted(self.pillars.items(), key=lambda kv: (kv[1].priority, kv[0]))
            for (_, pl), w in zip(by_rank, default_weights(len(by_rank), LEGACY_MIN_WEIGHT), strict=True):
                pl.weight = w
        for rank, (_, pl) in enumerate(self.sorted_pillars(), 1):
            pl.priority = rank
        return self

    def sorted_pillars(self) -> list[tuple[str, Pillar]]:
        """(name, pillar) pairs, heaviest first (equal weights by name)."""
        return sorted(self.pillars.items(), key=lambda kv: (-kv[1].weight, kv[0]))


LEGACY_MIN_WEIGHT = 5


def default_weights(n: int, lo: int) -> list[int]:
    """Weights for ranks 1..n: `lo` each plus the rest in proportion to n+1-rank, rounded by largest
    remainder so they sum to 100 (7 pillars, lo 5: 21/19/17/14/12/10/7)."""
    if n <= 0:
        return []
    lo = min(lo, 100 // n)
    total = n * (n + 1) / 2
    raw = [lo + (100 - n * lo) * (n + 1 - r) / total for r in range(1, n + 1)]
    out = [int(x) for x in raw]
    for i in sorted(range(n), key=lambda i: raw[i] - out[i], reverse=True)[:100 - sum(out)]:
        out[i] += 1
    return out


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


def _weight_errors(s: Strategy, spec: PillarSpec) -> list[str]:
    """pillars.toml [weights]: the weights sum to 100, each within min..max, the heaviest at least
    `spread` x the lightest."""
    w = spec.weights
    errs = []
    total = sum(pl.weight for pl in s.pillars.values())
    if total != 100:
        errs.append(f"weights must sum to 100 (got {total})")
    errs.extend(f"{name}: weight must be {w.min}..{w.max}" for name, pl in s.pillars.items()
                if not w.min <= pl.weight <= w.max)
    ws = [pl.weight for pl in s.pillars.values()]
    if ws and w.spread > 1 and max(ws) < w.spread * min(ws):
        errs.append(f"the heaviest pillar ({max(ws)}) must weigh at least {w.spread:g} x the lightest ({min(ws)})")
    return errs


def _detail_errors(s: Strategy, spec: PillarSpec) -> list[str]:
    """The spec's detail rules for a Strategist's answer: milestones on every pillar and a checkpoint
    plus an end target on the first, concrete goals on the top pillars, figures in each stance.
    Pinned pillars are the human's and exempt."""
    errs: list[str] = []
    for rank, (name, pl) in enumerate(s.sorted_pillars(), 1):
        if pl.pinned:
            continue
        if spec.min_milestones_each and len(pl.milestones) < spec.min_milestones_each:
            errs.append(f"{name}: needs at least {spec.min_milestones_each} milestone"
                        f"{'' if spec.min_milestones_each == 1 else 's'}")
        if rank == 1 and spec.min_milestones_first and len({m.by for m in pl.milestones}) < spec.min_milestones_first:
            errs.append(f"{name}: the heaviest pillar needs at least {spec.min_milestones_first} milestones on different dates")
        if rank <= spec.min_goals_top and len(pl.goals) < spec.min_goals:
            errs.append(f"{name}: weight rank {rank} is in the top {spec.min_goals_top} and needs at least "
                        f"{spec.min_goals} goals")
        if spec.stance_needs_figure and not re.search(r"\d", pl.stance):
            errs.append(f"{name}: the stance must cite at least one figure from the briefing")
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
    errs: list[str] = []
    errs.extend(f"missing pillar {p}" for p in spec.pillars if p not in s.pillars)
    errs.extend(f"unknown pillar {p!r}" for p in s.pillars if p not in spec.pillars)
    errs.extend(_weight_errors(s, spec))
    for name, pl in s.pillars.items():
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
    if require_milestones:
        errs.extend(_detail_errors(s, spec))
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

    weight: int = Field(description="share of the empire's effort; all pillars together sum to 100")
    stance: str = Field(description="one or two sentences")
    goals: list[str] = Field(default_factory=list, description="1-3 goals")
    milestones: list[Milestone] = Field(default_factory=list, description="measurable targets with a date")

    @model_validator(mode="before")
    @classmethod
    def _drop_human_fields(cls, data):
        """`pinned`/`edited_by` are the human's: a model echoing them never pins anything. An empty
        action list is dropped too (the stored shape carries every action field on every pillar); a
        non-empty one on a pillar that does not declare it still fails."""
        if isinstance(data, dict):
            data = {k: v for k, v in data.items() if k not in ("pinned", "edited_by", "priority")
                    and not (k in ACTION_KINDS.values() and k not in cls.model_fields and v == [])}
        return data


class _StrategyOutBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    focus: str = Field(description="one line: what this strategy is about")
    reason: str = Field(default="", description="why it was written or changed")

    @model_validator(mode="before")
    @classmethod
    def _lift_pillars(cls, data):
        """An answer in the stored shape ({"pillars": {id: {...}}, "focus", "identity"}) is read as named
        fields; its top-level `identity` is dropped (the review's own `identity` field carries it)."""
        if isinstance(data, dict) and isinstance(data.get("pillars"), dict):
            data = {**data["pillars"], **{k: v for k, v in data.items() if k not in ("pillars", "identity")}}
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


def strategy_for_prompt(s: Strategy, spec: PillarSpec) -> str:
    """`s` as JSON in the Strategist's output shape (one field per pillar in priority order, only the
    action fields the pillar declares, then focus and reason; no pinned/edited_by, no identity), so
    an answer that echoes it validates against `review_model(spec)`."""
    out: dict = {}
    for name, pl in s.sorted_pillars():
        declared = spec.pillars[name].actions if name in spec.pillars else ()
        keep = {"weight", "stance", "goals", "milestones"} | {ACTION_KINDS[k] for k in declared if k in ACTION_KINDS}
        out[name] = pl.model_dump(include=keep)
    out.update(focus=s.focus, reason=s.reason)
    return json.dumps(out, indent=1, ensure_ascii=False)


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
    w = spec.weights
    lines.append(f"Each pillar: a weight (a whole number, the share of the empire's effort; all pillars sum to "
                 f"100, each {w.min}..{w.max}"
                 + (f", the heaviest at least {w.spread:g} x the lightest" if w.spread > 1 else "")
                 + "; the governor steers by weight x how far behind the pillar's milestones are), a stance of one or two "
                 "sentences, 1-3 goals, and milestones on the briefing's measures (exactly these names: "
                 + ", ".join(spec.metrics) + "; a rank is 1 = best, so use op <= for it) with a target and an "
                 "in-game date YYYY.MM.DD.")
    if spec.min_milestones_top:
        lines.append(f"Each of the {spec.min_milestones_top} highest-priority pillars needs at least one milestone.")
    if spec.min_milestones_each:
        lines.append(f"Every pillar needs at least {spec.min_milestones_each} milestone"
                     f"{'' if spec.min_milestones_each == 1 else 's'}, so each one can be measured.")
    if spec.min_milestones_first:
        lines.append(f"The heaviest pillar needs at least {spec.min_milestones_first} milestones: a checkpoint "
                     "and a later end target.")
    if spec.min_goals:
        lines.append(f"Each of the {spec.min_goals_top} heaviest pillars needs at least {spec.min_goals} "
                     "concrete goals (what to reach and where, not 'wait' or 'maintain').")
    if spec.stance_needs_figure:
        lines.append("Each stance cites at least one figure from the briefing (a stock, a monthly net, a ratio "
                     "or a count), so it is checkable.")
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


# ---- pressure: weight x milestone need (weighted pillars spec) -------------------------------------

def pressures(s: Strategy, spec: PillarSpec, status_of) -> dict[str, dict]:
    """Per pillar: weight, need (the largest `[weights.need]` multiplier among its milestones' statuses,
    1.0 without milestones), the status that set it and pressure = weight x need. `status_of(name,
    milestone)` gives a milestone's status (met / on_track / at_risk / missed)."""
    table = spec.weights.need
    out = {}
    for name, pl in s.sorted_pillars():
        statuses = [status_of(name, m) for m in pl.milestones]
        worst = max(statuses, key=lambda st: table.get(st, 1.0), default="")
        need = table.get(worst, 1.0) if worst else 1.0
        out[name] = {"weight": pl.weight, "need": need, "status": worst, "pressure": round(pl.weight * need, 1)}
    return out


def directive_pressure(press: dict[str, dict], spec: PillarSpec) -> list[tuple[str, float, str]]:
    """(directive, pressure, pillar) for every pillar that ranks a directive, highest pressure first."""
    rows = [(d, p["pressure"], name) for name, p in press.items() if (d := spec.directive_of(name))]
    return sorted(rows, key=lambda r: (-r[1], r[2]))


def suggestion(ranked: list[tuple[str, float, str]], current: str | None, margin: float) -> str:
    """The top-pressure directive, or "keep" while the current directive's pressure is at least the
    top's divided by `margin` (switching costs the game's AI time to re-plan)."""
    if not ranked:
        return "keep"
    top = ranked[0]
    cur = next((r for r in ranked if r[0] == current), None)
    if cur is not None and (cur is top or cur[1] >= top[1] / margin):
        return "keep"
    return top[0]


def shares(press: dict[str, dict]) -> dict[str, int]:
    """Each pillar's share of the total pressure, in whole percent (share mode)."""
    total = sum(p["pressure"] for p in press.values())
    return {name: round(100 * p["pressure"] / total) if total else 0 for name, p in press.items()}


def rebalance(pillars: dict[str, Pillar], edited: str) -> dict[str, Pillar]:
    """`pillars` after a human set `edited`'s weight: the other unpinned pillars are rescaled in
    proportion (largest remainder) so all weights sum to 100 again; pinned ones keep theirs. Bounds
    are left to `validate`."""
    fixed = sum(pl.weight for n, pl in pillars.items() if n == edited or pl.pinned)
    free = [n for n, pl in pillars.items() if n != edited and not pl.pinned]
    target, have = 100 - fixed, sum(pillars[n].weight for n in free)
    if not free or have <= 0 or target < 0:
        return pillars
    raw = {n: pillars[n].weight * target / have for n in free}
    new = {n: int(v) for n, v in raw.items()}
    for n in sorted(free, key=lambda n: raw[n] - new[n], reverse=True)[:target - sum(new.values())]:
        new[n] += 1
    return {n: pl.model_copy(update={"weight": new[n]}) if n in new else pl for n, pl in pillars.items()}
