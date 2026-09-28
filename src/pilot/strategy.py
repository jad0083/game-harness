"""Pillar strategies: the governor's top-down frame (docs/design/2026-09-26-strategy-layer-design.md).

Game-agnostic: the pillars, directive mapping, metrics, aliases and action limits come from the
game's `PillarSpec` (pillars.py; docs/design/2026-09-26-game-pillars-design.md).
Pure data and rules; no model calls, no game input."""

from __future__ import annotations

import itertools
import json
import re
from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, create_model, model_validator
from pydantic.json_schema import SkipJsonSchema

from .pillars import ACTION_KINDS, ID_LIST_KINDS, ActionLimits, PillarSpec

_DATE_RE = re.compile(r"^\d{4}\.(\d{2})\.\d{2}$")
_TURN_RE = re.compile(r"^T(\d{1,4})$")        # turn-based games (Civ VI): T60 = turn 60


def _valid_date(s: str) -> bool:
    if _TURN_RE.match(s):
        return True
    m = _DATE_RE.match(s)
    return bool(m) and 1 <= int(m.group(1)) <= 12


def _date_fits(s: str, spec: PillarSpec) -> bool:
    """The date is in the game's format (calendar YYYY.MM.DD, or T<turn>)."""
    return bool(_TURN_RE.match(s)) if spec.date_format == "turns" else bool(_DATE_RE.match(s)) and _valid_date(s)


class Milestone(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: str
    op: Literal[">=", "<="]
    target: float
    by: str = Field(description="in-game date YYYY.MM.DD, or T<turn> in a turn-based game")
    # when the milestone was set (postmortem-fixes design, ruling 17): stamped by the governor when it
    # publishes a strategy, never written by the model (left out of the Strategist's schema); only
    # rows from then on are judged. None (stored before the stamp): no row filter.
    set: SkipJsonSchema[str | None] = None

    def __init__(self, **data):
        if isinstance(data.get("metric"), str):     # aliases are the game's: apply_aliases(s, spec)
            data["metric"] = data["metric"].strip()
        for key in ("by", "set"):
            v = data.get(key)
            if v and not _valid_date(v):
                raise ValueError(f"{key} {v!r} is not a date YYYY.MM.DD or a turn T<turn>")
        super().__init__(**data)

    def key(self) -> tuple:
        """What makes two milestones the same one (its `set` is not part of it)."""
        return (self.metric, self.op, self.target, self.by)


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
    prefer_civics: list[str] = Field(default_factory=list)
    prefer_policies: list[str] = Field(default_factory=list)
    prefer_production: list[str] = Field(default_factory=list)
    prefer_purchases: list[str] = Field(default_factory=list)
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
        ranked_only = all("weight" not in pl.model_fields_set for pl in self.pillars.values()) and \
            any("priority" in pl.model_fields_set for pl in self.pillars.values())
        if self.pillars and ranked_only:     # stored before weights; an answer with weights 0 is not converted
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


def _apportion(raw: dict, total: int) -> dict:
    """Round `raw` shares to integers summing to `total` (largest remainder)."""
    out = {k: int(v) for k, v in raw.items()}
    for k in sorted(raw, key=lambda k: raw[k] - out[k], reverse=True)[:total - sum(out.values())]:
        out[k] += 1
    return out


def default_weights(n: int, lo: int) -> list[int]:
    """Weights for ranks 1..n: `lo` each plus the rest in proportion to n+1-rank, rounded by largest
    remainder so they sum to 100 (7 pillars, lo 5: 21/19/17/14/12/10/7)."""
    if n <= 0:
        return []
    lo = min(lo, 100 // n)
    total = n * (n + 1) / 2
    shares = _apportion({r: lo + (100 - n * lo) * (n + 1 - r) / total for r in range(1, n + 1)}, 100)
    return [shares[r] for r in range(1, n + 1)]


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
    """Months since year 0, or the turn for a T<turn> date (one step of the game's clock)."""
    t = _TURN_RE.match(date)
    if t:
        return int(t.group(1))
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


def _content(pl: Pillar, *, ignore_weight: bool = False) -> dict:
    """What a pillar says (the derived rank and the milestones' `set` stamps never count; the weight
    optionally)."""
    exclude: dict = {"pinned": True, "edited_by": True, "priority": True, "milestones": {"__all__": {"set"}}}
    if ignore_weight:
        exclude["weight"] = True
    return pl.model_dump(exclude=exclude)


def _briefing_checked(s: Strategy, previous: Strategy | None) -> set[str]:
    """Pillars that changed versus `previous` and are not pinned there (all of them without one)."""
    if previous is None:
        return set(s.pillars)
    out = set()
    for name, pl in s.pillars.items():
        old = previous.pillars.get(name)
        if old is None or (not old.pinned and _content(pl, ignore_weight=True) != _content(old, ignore_weight=True)):
            out.add(name)
    return out


def _action_errors(name: str, kind: str, items: list, a: ActionLimits, tech_ids: set[str], idle: set[str],
                   income: dict[str, float], briefing: bool, ids: Mapping[str, set[str]] | None = None) -> list[str]:
    errs: list[str] = []
    if kind == "tech":
        known = (ids or {}).get("tech", tech_ids)
        if len(items) > a.max_items:
            errs.append(f"{name}: at most {a.max_items} preferred techs")
        errs.extend(f"{name}: unknown tech {t!r}" for t in items if t not in known)
        return errs
    if kind in ID_LIST_KINDS:
        if len(items) > a.max_items:
            errs.append(f"{name}: at most {a.max_items} in {a.field}")
        known = (ids or {}).get(kind)
        if known is not None:
            errs.extend(f"{name}: unknown {kind} {t!r}" for t in items if t not in known)
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


def _relative_errors(s: Strategy, spec: PillarSpec, standing: Mapping) -> list[str]:
    """`[strategy] relative_military` (postmortem-fixes design, ruling 18) against today's standing
    ({"military", "median", "peers": majors met, "weak": ruling 1's low or last}). Pinned pillars are
    exempt, as for every rule of the Strategist's answer."""
    rel = spec.relative
    if rel is None:
        return []
    errs: list[str] = []
    peers, med = standing.get("peers"), standing.get("median")
    for name, pl in s.sorted_pillars():
        if pl.pinned:
            continue
        for m in pl.milestones:
            if m.metric.startswith("rank:") and isinstance(peers, int) and peers < rel.rank_min_peers:
                errs.append(f"{name}: {m.metric} ranks us among only {peers} majors met; a rank milestone needs "
                            f"{rel.rank_min_peers} or more (use {' or '.join(rel.relative)})")
            if (m.metric == rel.metric and m.op == ">=" and isinstance(med, (int, float)) and med > 0
                    and m.target < rel.absolute_share * med):
                errs.append(f"{name}: {m.metric} >= {m.target:g} by {m.by} is under {rel.absolute_share:g} x the median "
                            f"of the majors we have met ({med:,.0f}); set it relative: {' or '.join(rel.relative)}")
    owner = s.pillars.get(rel.pillar)
    if standing.get("weak") and owner is not None and not owner.pinned and not any(
            m.metric in rel.relative and m.op == ">=" and m.target >= rel.min_target for m in owner.milestones):
        errs.append(f"{rel.pillar}: our military is weak against the majors we have met (under the median share, or "
                    f"last): hold a milestone on {' or '.join(rel.relative)} >= {rel.min_target:g}")
    return errs


_UNIT_ID_RE = re.compile(r"\bunit:[a-z0-9_]+")


def _unavailable_errors(s: Strategy, unavailable) -> list[str]:
    """Ids a model's answer plans on that the game cannot use now (ruling 8): each preferred purchase
    or production id and each `unit:` id quoted in a goal that `unavailable(id)` names; pinned pillars
    are exempt."""
    errs: list[str] = []
    for name, pl in s.sorted_pillars():
        if pl.pinned:
            continue
        ids = [*pl.prefer_purchases, *pl.prefer_production, *(m for g in pl.goals for m in _UNIT_ID_RE.findall(g))]
        errs.extend(f"{name}: {why}" for i in dict.fromkeys(ids) if (why := unavailable(i)))
    return errs


def _unpursuable_errors(s: Strategy, spec: PillarSpec) -> list[str]:
    """Goals that name a word of `[strategy] unpursuable` (ruling 25): no order kind can pursue them
    ("Get peace with Australia" at T563, T565 and T575; the game's AI handles diplomacy during
    autoplay). Whole words, plurals included; pinned pillars are exempt."""
    errs: list[str] = []
    for name, pl in s.sorted_pillars():
        if pl.pinned:
            continue
        for g in pl.goals:
            hit = next((w for w in spec.unpursuable
                        if re.search(rf"\b{re.escape(w)}(?:s|es|d|ed)?\b", g, re.IGNORECASE)), None)
            if hit:
                errs.append(f"{name}: goal {g!r} names {hit!r}: no order can pursue it: the game's AI handles "
                            "diplomacy during autoplay")
    return errs


def validate(s: Strategy, spec: PillarSpec, *, previous: Strategy | None, tech_ids: set[str], idle: set[str],
             income: dict[str, float], briefing_checked: set[str] | None = None,
             require_milestones: bool = True, ids: Mapping[str, set[str]] | None = None,
             standing: Mapping | None = None, unavailable=None) -> list[str]:
    """Reasons the strategy cannot be used under the game's spec (empty = valid).

    Structural checks (pillars, priorities, sizes, metrics, dates, action ownership and limits) apply
    to every pillar. Briefing-dependent checks (sell only an idle resource, at most a share of its
    income) apply only to `briefing_checked` pillars — by default the ones that changed versus
    `previous` and are not pinned there, so a pinned or untouched pillar that no longer fits today's
    briefing never blocks a review (see `pinned_misfits`). With `require_milestones`, each unpinned
    pillar among the top `spec.min_milestones_top` by priority needs a milestone (human edits pass False).
    `ids` holds the known ids per id-list action kind (tech, civic, policy, production, purchase); a
    kind missing from it is checked for size only (tech falls back to `tech_ids`). `standing` (our
    military against the majors met; a game with `[strategy] relative_military`) turns on ruling 18's
    rules for a model's answer; `unavailable(id)` (a reason, or None) sends back ids the game cannot use
    now, e.g. a unit whose strategic resource we lack (ruling 8)."""
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
            if not _date_fits(m.by, spec):
                errs.append(f"{name}: milestone by {m.by!r} is not a turn T<turn>" if spec.date_format == "turns"
                            else f"{name}: milestone by {m.by!r} is not a date YYYY.MM.DD")
            if m.metric not in spec.metrics:
                errs.append(f"{name}: unknown metric {m.metric!r}")
            elif m.metric in spec.milestone_exclude and require_milestones and not pl.pinned:
                errs.append(f"{name}: {m.metric} is a balance, not a milestone metric here (pillars.toml [metrics] "
                            "milestone_exclude: a stock rewards hoarding); use a per-turn measure")
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
                                           name in checked, ids))
    if require_milestones and spec.min_milestones_top:
        for rank, (name, pl) in enumerate(s.sorted_pillars()[:spec.min_milestones_top], 1):
            if not pl.pinned and not pl.milestones:
                errs.append(f"{name}: priority {rank} is in the top {spec.min_milestones_top} "
                            "and needs at least one milestone")
    if require_milestones:
        errs.extend(_detail_errors(s, spec))
        if standing is not None:
            errs.extend(_relative_errors(s, spec, standing))
        if unavailable is not None:
            errs.extend(_unavailable_errors(s, unavailable))
        if spec.unpursuable:
            errs.extend(_unpursuable_errors(s, spec))
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
    restored = False
    for name, pl in previous.pillars.items():
        if pl.pinned:
            pillars[name] = pl.model_copy(deep=True)
            restored = True
    if not restored:
        return new
    # the pins keep their weights: the unpinned pillars share the rest; rebuilt so ranks follow
    return Strategy(**{**new.model_dump(exclude={"pillars"}), "pillars": rebalance(pillars, None)})


def metric_value(row: dict, metric: str, row_keys: Mapping[str, str] | None = None) -> float | None:
    """A metric from a metrics row; `row_keys` maps a metric to the row field that stores it."""
    if metric.startswith("rank:"):
        st = (row.get("peers") or {}).get(metric[5:]) or {}
        return st.get("rank")
    v = row.get((row_keys or {}).get(metric, metric))
    return float(v) if isinstance(v, (int, float)) else None


def milestone_status(m: Milestone, rows: list[dict], today: str, row_keys: Mapping[str, str] | None = None,
                     lookback: int = 12) -> str:
    """met / on_track / at_risk / missed, from metrics rows (oldest first) up to `today`, judged on one
    value (postmortem-fixes design, ruling 17): the latest row at or before `today` and not before the
    milestone's `set`; once `today` is past `by`, the latest such row at or before `by` (its check date:
    a target met on its date stays met after a later dip, and does not fire "milestone missed"). met: it
    meets the target; missed: otherwise, once `today` is past `by`; else on_track or at_risk from the
    projection (that value against a row at least `lookback` steps older, months or turns: any row of
    the campaign, since a trend needs history). A milestone with no reading since it was set is at_risk
    (missed once `by` has passed: nothing shows it met). A value met before the latest row no longer
    counts ("military >= 170 by T350" read met at T350 with 124)."""
    series = [(_months(r["date"]), metric_value(r, m.metric, row_keys)) for r in rows if r.get("date")]
    series = [(mo, v) for mo, v in series if v is not None and mo <= _months(today)]
    since = _months(m.set) if m.set else None
    past_due = _months(today) > _months(m.by)
    upto = _months(m.by) if past_due else _months(today)
    judged = [(mo, v) for mo, v in series if (since is None or mo >= since) and mo <= upto]
    ok = (lambda v: v >= m.target) if m.op == ">=" else (lambda v: v <= m.target)
    if not judged:
        return "missed" if past_due else "at_risk"
    now_mo, now = judged[-1]
    if ok(now):
        return "met"
    if past_due:
        return "missed"
    past = next(((mo, v) for mo, v in reversed(series) if now_mo - mo >= lookback), None)
    if past is None:
        return "at_risk"
    span = max(now_mo - past[0], 1)
    projected = now + (now - past[1]) / span * (_months(m.by) - now_mo)
    return "on_track" if ok(projected) else "at_risk"


def stamp_milestones(new: Strategy, previous: Strategy | None, date: str | None) -> Strategy:
    """`new` with each milestone's `set` stamped (ruling 17): a milestone with the same metric, op,
    target and `by` as one of the same pillar in `previous` keeps that one's `set` (None stays None:
    a strategy stored before the stamp); any other gets `date` (None when the date is unknown). A
    `set` the model or a request wrote is never kept."""
    stamp = date if date and _valid_date(date) else None
    pillars = {}
    changed = False
    for name, pl in new.pillars.items():
        old = {m.key(): m.set for m in (previous.pillars[name].milestones
                                         if previous is not None and name in previous.pillars else [])}
        ms = [m.model_copy(update={"set": old.get(m.key(), stamp)}) for m in pl.milestones]
        changed = changed or any(a.set != b.set for a, b in zip(ms, pl.milestones, strict=True))
        pillars[name] = pl.model_copy(update={"milestones": ms})
    return new.model_copy(update={"pillars": pillars}) if changed else new


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


ID_LIST_TEXT = {"tech": "tech ids to pick when offered", "civic": "civic ids to progress when offered",
                "policy": "policy ids to slot", "production": "unit, building, district or project ids to build",
                "purchase": "unit or building ids to buy with gold or faith"}


def _action_field(a: ActionLimits):
    if a.kind in ID_LIST_KINDS:
        return (list[str], Field(default_factory=list,
                                 description=f"{ID_LIST_TEXT[a.kind]}; at most {a.max_items}"))
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
        out[name] = pl.model_dump(include=keep, exclude={"milestones": {"__all__": {"set"}}})   # `set` is the governor's
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
                 + ", ".join(m for m in spec.metrics if m not in spec.milestone_exclude)
                 + "; a rank is 1 = best, so use op <= for it"
                 + (f"; never {' or '.join(spec.milestone_exclude)}: a balance rewards hoarding"
                    if spec.milestone_exclude else "") + ") with a target and "
                 + ("a turn written T<turn> (e.g. T60)." if spec.date_format == "turns" else "an in-game date YYYY.MM.DD."))
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
    rel = spec.relative
    if rel is not None:
        lines.append(f"Military targets are relative to the majors we have met: while our military is under the "
                     f"median share or last among them, the {rel.pillar} pillar holds a milestone on "
                     f"{' or '.join(rel.relative)} with a target of at least {rel.min_target:g}; an absolute "
                     f"{rel.metric} target under {rel.absolute_share:g} x their median is sent back; a rank milestone "
                     f"needs at least {rel.rank_min_peers} majors met.")
    for kind, a in spec.actions.items():
        owners = spec.owners(kind)
        if not owners:
            continue
        on = " and ".join(owners)
        if kind in ID_LIST_KINDS:
            lines.append(f"Only {on}: `{a.field}` ({ID_LIST_TEXT[kind]}; at most {a.max_items}"
                         + ("; corpus ids with their kind, e.g. tech:pottery" if a.full_ids else "") + ").")
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
    lines.append(("Weights decide each pillar's share of the decisions' effort." if spec.weights.mode == "share"
                  else "Priorities decide which directives the governor prefers.")
                 + " Never change a pillar marked pinned: the human set it. If nothing material changed, answer change=false.")
    lines.append(spec.identity or (
        "Build on our species (race) and its traits, ethics, civics and origin: fill `identity` with how "
        "they shape this strategy, naming the traits you rely on and the pillars they affect (e.g. "
        "industrious → economy on minerals; enduring → long wars are affordable), and weigh a "
        "neighbour's traits when dealing with or fighting it."))
    if spec.instructions:
        lines.append(spec.instructions)
    return "\n".join(lines)


# ---- pressure: weight x milestone need (weighted pillars spec) -------------------------------------

def _peer_median(row: dict, key: str | None) -> float | None:
    m = (((row.get("peers") or {}).get(key) or {}).get("median")) if key else None
    return float(m) if isinstance(m, (int, float)) and m > 0 else None


def directive_record(rows: list[dict], directive: str, metric: str,
                     row_keys: Mapping[str, str] | None = None,
                     peer_keys: Mapping[str, str] | None = None) -> dict | None:
    """How `metric` grew per in-game year while `directive` was in force in this campaign versus the
    rest of the time, from consecutive metrics rows (each step counts for the directive in force at its
    start). Ranks count going down as growth. None without at least 6 months of each.

    When rows carry the metric's peer median (`peers[<peer_keys.get(metric, metric)>].median`), the
    growth is that of ours / median, from the steps whose both rows have one, rounded to 3 decimals,
    with `relative` True (stellaris levers design, ruling 7): an absolute rate rewards whatever was held
    late, when every empire grows faster. Ranks and metrics without a median stay absolute."""
    peer = None if metric.startswith("rank:") else (peer_keys or {}).get(metric, metric)
    steps = []
    for a, b in itertools.pairwise(rows):
        va, vb = metric_value(a, metric, row_keys), metric_value(b, metric, row_keys)
        if va is None or vb is None or not a.get("date") or not b.get("date"):
            continue
        months = _months(b["date"]) - _months(a["date"])
        if months > 0:
            steps.append((a, b, va, vb, months))
    relative = any(_peer_median(a, peer) and _peer_median(b, peer) for a, b, *_ in steps)
    held = [0.0, 0]
    other = [0.0, 0]
    for a, b, va, vb, months in steps:
        if relative:
            ma, mb = _peer_median(a, peer), _peer_median(b, peer)
            if not (ma and mb):
                continue
            va, vb = va / ma, vb / mb
        delta = (va - vb) if metric.startswith("rank:") else (vb - va)
        bucket = held if a.get("directive") == directive else other
        bucket[0] += delta
        bucket[1] += months
    if held[1] < 6 or other[1] < 6:
        return None
    places = 3 if relative else 1
    out = {"held_years": round(held[1] / 12, 1), "held_rate": round(held[0] * 12 / held[1], places),
           "other_rate": round(other[0] * 12 / other[1], places)}
    return {**out, "relative": True} if relative else out


def pressures(s: Strategy, spec: PillarSpec, status_of, record_of=None) -> dict[str, dict]:
    """Per pillar: weight, need (the largest `[weights.need]` multiplier among its milestones' statuses,
    1.0 without milestones), the status that set it and pressure = weight x need. `status_of(name,
    milestone)` gives a milestone's status (met / on_track / at_risk / missed). With `record_of(name,
    metric)` (a `directive_record` of the pillar's directive on its first milestone's metric), a
    directive held `stall_years` or more that grew its metric no faster than the rest of the time
    "does not work here": pressure x `stall_factor`, and the record is kept for the frame."""
    table, w = spec.weights.need, spec.weights
    out = {}
    for name, pl in s.sorted_pillars():
        statuses = [status_of(name, m) for m in pl.milestones]
        worst = max(statuses, key=lambda st: table.get(st, 1.0), default="")
        need = table.get(worst, 1.0) if worst else 1.0
        row = {"weight": pl.weight, "need": need, "status": worst, "pressure": round(pl.weight * need, 1)}
        if record_of is not None and w.stall_years > 0 and pl.milestones:
            metric = pl.milestones[0].metric
            rec = record_of(name, metric)
            if rec and rec["held_years"] >= w.stall_years and rec["held_rate"] <= rec["other_rate"]:
                row.update(efficacy=w.stall_factor, record={**rec, "metric": metric, "directive": spec.directive_of(name)},
                           pressure=round(pl.weight * need * w.stall_factor, 1))
        out[name] = row
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


def rebalance(pillars: dict[str, Pillar], edited: str | None) -> dict[str, Pillar]:
    """`pillars` with the unpinned ones (other than `edited`, a weight the human just set) rescaled in
    proportion (largest remainder) so all weights sum to 100 again; pinned ones keep theirs. Bounds
    are left to `validate`."""
    fixed = sum(pl.weight for n, pl in pillars.items() if n == edited or pl.pinned)
    free = [n for n, pl in pillars.items() if n != edited and not pl.pinned]
    target, have = 100 - fixed, sum(pillars[n].weight for n in free)
    if not free or have <= 0 or target < 0:
        return pillars
    new = _apportion({n: pillars[n].weight * target / have for n in free}, target)
    return {n: pl.model_copy(update={"weight": new[n]}) if n in new else pl for n, pl in pillars.items()}
