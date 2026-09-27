"""Game pillars: each game's strategy guardrails, read from corpora/<game>/pillars.toml
(docs/design/2026-09-26-game-pillars-design.md).

Pure data; no model calls, no game input. Unknown keys are an error (fail fast, naming the key)."""

from __future__ import annotations

import re
import tomllib
import types
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel

# The action kinds the harness can validate and carry out, and the Pillar field each one fills.
# tech/civic/policy/production/purchase are "id lists": corpus ids the Strategist prefers (and, in
# games with orders such as Civ VI, the kinds of order a decision may give, `max_orders` per decision).
ACTION_KINDS: types.MappingProxyType[str, str] = types.MappingProxyType({
    "tech": "prefer_techs", "market": "market", "civic": "prefer_civics", "policy": "prefer_policies",
    "production": "prefer_production", "purchase": "prefer_purchases"})
ID_LIST_KINDS = ("tech", "civic", "policy", "production", "purchase")
_ID_LIST_KEYS = {"field", "max_items", "max_orders", "ids_from_corpus", "full_ids", "note"}
_ACTION_KEYS = {
    **dict.fromkeys(ID_LIST_KINDS, _ID_LIST_KEYS),
    "purchase": _ID_LIST_KEYS | {"gold_reserve", "faith_reserve", "treasury_share", "threatened_share",
                                 "gold_reserve_per_deficit", "pantheon_reserve", "prophet_faith_reserve",
                                 "skip_turns_left", "defence_first", "defender_classes", "defence_cooldown_turns"},
    "market": {"field", "max_items", "resources_from_manifest", "amount_min", "amount_max",
               "sell_income_share", "sell_requires_idle", "note"},
}
_ACTION_REQUIRED = {**dict.fromkeys(ID_LIST_KINDS, ("max_items", "ids_from_corpus")),
                    "purchase": ("max_items", "ids_from_corpus", "gold_reserve", "treasury_share"),
                    "market": ("max_items", "resources_from_manifest", "amount_max")}
_TOP_KEYS = {"strategy", "metrics", "pillars", "actions", "weights", "orders"}
_ORDERS_KEYS = {"window_turns", "min_resolved", "min_samples", "weak_rate", "open_cap_turns", "open_grace_turns"}
ORDER_SAMPLE_GROUPS = ("production", "purchase", "other")
_WEIGHTS_KEYS = {"mode", "min", "max", "spread", "switch_margin", "need", "stall_years", "stall_factor"}
NEED_STATUSES = ("met", "on_track", "at_risk", "missed")
_STRATEGY_KEYS = {"min_milestones_top", "min_milestones_each", "min_milestones_first", "min_goals", "min_goals_top",
                  "stance_needs_figure", "metric_aliases", "instructions", "date_format", "identity"}
DATE_FORMATS = ("calendar", "turns")     # milestone dates: YYYY.MM.DD, or T<turn> (turn-based games)
_METRICS_KEYS = {"names", "row_keys", "milestone_exclude"}
_PILLAR_KEYS = {"label", "description", "directive", "actions"}
_RESERVED_IDS = {"focus", "reason", "pillars"}      # fields of the Strategist's output model
_ID = re.compile(r"^[a-z][a-z0-9_]*$")


class PillarsError(ValueError):
    """A missing or invalid pillars file; the message names the file and the key."""


@dataclass(frozen=True)
class PillarDef:
    id: str
    label: str
    description: str
    directive: str | None = None
    actions: tuple[str, ...] = ()


@dataclass(frozen=True)
class ActionLimits:
    kind: str
    field: str
    max_items: int
    ids_from_corpus: str | tuple[str, ...] | None = None   # data/<name>.json file(s) the ids come from
    resources: tuple[str, ...] = ()
    amount_min: int = 1
    amount_max: int | None = None
    sell_income_share: float | None = None
    sell_requires_idle: bool = False
    note: str = ""
    max_orders: int = 1                  # orders of this kind per decision (games with orders)
    full_ids: bool = False               # ids keep their "<kind>:" prefix ("tech:pottery"), as orders name them
    gold_reserve: int = 0                # purchase: gold kept back
    faith_reserve: int = 0               # purchase: faith kept back
    treasury_share: float | None = None  # purchase: at most this share of the balance per purchase
    threatened_share: float | None = None  # ... or this share for a city in danger ("buy at once")
    # Civ VI buy-out rules (docs/design/2026-09-27-civ6-levers-design.md, rulings 18-20); the defaults
    # turn each rule off.
    gold_reserve_per_deficit: float = 0.0  # the gold reserve grows by this per gold per turn of deficit
    pantheon_reserve: bool = False       # keep the pantheon's live price in faith until one is founded
    prophet_faith_reserve: int = 0       # faith kept while a Great Prophet (our religion) is within reach
    skip_turns_left: int = 0             # never buy what the city finishes within this many turns anyway
    defence_first: bool = False          # a city in danger with no defender on its tile gets one first
    defender_classes: tuple[str, ...] = ()   # unit classes (data/unit.json fields.class) that defend a city
    defence_cooldown_turns: int = 0      # at most one defender purchase per city per this many turns

    @property
    def corpus_files(self) -> tuple[str, ...]:
        f = self.ids_from_corpus
        return () if f is None else (f,) if isinstance(f, str) else tuple(f)


@dataclass(frozen=True)
class WeightsSpec:
    """How pillar weights are bounded and how milestone status turns weight into pressure
    (docs/design/2026-09-26-weighted-pillars-design.md). The defaults leave weights free
    and pressure equal to weight."""
    mode: str = "exclusive"          # exclusive: one standing directive; share: effort split across levers
    min: int = 0
    max: int = 100
    spread: float = 1.0              # heaviest >= spread x lightest
    switch_margin: float = 1.0       # keep the current directive while its pressure >= top / margin
    need: dict[str, float] = field(default_factory=lambda: dict.fromkeys(NEED_STATUSES, 1.0))
    stall_years: float = 0.0         # a directive held this long without beating its metric's other growth...
    stall_factor: float = 1.0        # ...has its pressure multiplied by this (0 years: rule off)


@dataclass(frozen=True)
class OrdersSpec:
    """How the order record judges whether a kind of order sticks (games with orders, e.g. Civ VI;
    docs/design/2026-09-27-civ6-levers-design.md, rulings 12 and 14). Absent: the record is off."""
    window_turns: int = 30           # the stick rate looks at orders resolved in the last N turns...
    min_resolved: int = 8            # ...widened back until it holds this many judged orders of the key
    min_samples: dict[str, int] = field(default_factory=lambda: {"production": 4, "purchase": 4, "other": 3})
    weak_rate: float = 0.5           # a rate at or below this (with enough samples): "does not stick here"
    open_cap_turns: int = 20         # an order is followed at most this long (policies: exactly this long)
    open_grace_turns: int = 3        # ...and at least its turns left plus this

    def min_samples_of(self, key: str) -> int:
        group = key.split(" ", 1)[0]
        return self.min_samples.get(group if group in ("production", "purchase") else "other", 1)


@dataclass(frozen=True)
class PillarSpec:
    game: str
    pillars: dict[str, PillarDef]
    metrics: tuple[str, ...]
    metric_aliases: dict[str, str] = field(default_factory=dict)
    row_keys: dict[str, str] = field(default_factory=dict)
    actions: dict[str, ActionLimits] = field(default_factory=dict)
    min_milestones_top: int = 0
    min_milestones_each: int = 0      # every unpinned pillar
    min_milestones_first: int = 0     # the priority-1 pillar, on distinct dates (checkpoint + end target)
    min_goals: int = 0                # for each of the top `min_goals_top` pillars
    min_goals_top: int = 0
    stance_needs_figure: bool = False  # a stance cites a number from the briefing
    weights: WeightsSpec = field(default_factory=WeightsSpec)
    instructions: str = ""
    date_format: str = "calendar"      # milestone `by`: "calendar" YYYY.MM.DD or "turns" T<turn>
    identity: str = ""                 # the Strategist's `identity` instruction (default: our species)
    orders: OrdersSpec | None = None   # the order record's settings ([orders]); None: no record
    milestone_exclude: tuple[str, ...] = ()   # metrics never used as milestones ([metrics] milestone_exclude)

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(self.pillars)

    def directive_of(self, pillar: str) -> str | None:
        p = self.pillars.get(pillar)
        return p.directive if p else None

    def alias(self, metric: str) -> str:
        m = metric.strip()
        return self.metric_aliases.get(m, m)

    def owners(self, kind: str) -> list[str]:
        """Pillar ids (file order) that declare action `kind`."""
        return [pid for pid, p in self.pillars.items() if kind in p.actions]

    def public(self) -> dict:
        """JSON view for the dashboard."""
        w = self.weights
        return {"game": self.game, "metrics": list(self.metrics), "min_milestones_top": self.min_milestones_top,
                "weights": {"mode": w.mode, "min": w.min, "max": w.max, "spread": w.spread,
                            "switch_margin": w.switch_margin, "need": dict(w.need),
                            "stall_years": w.stall_years, "stall_factor": w.stall_factor},
                "pillars": [{"id": p.id, "label": p.label, "description": p.description, "directive": p.directive,
                             "actions": list(p.actions)} for p in self.pillars.values()],
                "date_format": self.date_format, "milestone_exclude": list(self.milestone_exclude),
                "actions": {k: {"field": a.field, "max_items": a.max_items, "resources": list(a.resources),
                                "amount_min": a.amount_min, "amount_max": a.amount_max, "max_orders": a.max_orders,
                                "gold_reserve": a.gold_reserve, "faith_reserve": a.faith_reserve,
                                "treasury_share": a.treasury_share, "threatened_share": a.threatened_share,
                                "gold_reserve_per_deficit": a.gold_reserve_per_deficit,
                                "pantheon_reserve": a.pantheon_reserve, "prophet_faith_reserve": a.prophet_faith_reserve,
                                "skip_turns_left": a.skip_turns_left, "defence_first": a.defence_first,
                                "defender_classes": list(a.defender_classes),
                                "defence_cooldown_turns": a.defence_cooldown_turns}
                            for k, a in self.actions.items()},
                "orders": None if self.orders is None else {
                    "window_turns": self.orders.window_turns, "min_resolved": self.orders.min_resolved,
                    "min_samples": dict(self.orders.min_samples), "weak_rate": self.orders.weak_rate,
                    "open_cap_turns": self.orders.open_cap_turns, "open_grace_turns": self.orders.open_grace_turns}}


_CACHE: dict[tuple[str, int], PillarSpec] = {}


def load_pillars(corpus_dir: Path) -> PillarSpec:
    """The game's pillars from `<corpus_dir>/pillars.toml`, validated; cached until the file changes."""
    corpus = Path(corpus_dir)
    path = corpus / "pillars.toml"
    try:
        stamp = path.stat().st_mtime_ns
    except FileNotFoundError:
        raise PillarsError(f"{path}: missing (the strategy layer needs it)") from None
    key = (str(path.resolve()), stamp)
    if key not in _CACHE:
        _CACHE[key] = _parse(path, corpus)
    return _CACHE[key]


def _err(path: Path, key: str, msg: str) -> PillarsError:
    return PillarsError(f"{path}: {key}: {msg}")


def _unknown(path: Path, where: str, table: dict, allowed: set[str]) -> None:
    extra = sorted(set(table) - allowed)
    if extra:
        raise _err(path, f"{where}.{extra[0]}" if where else extra[0], "unknown key")


def _table(path: Path, raw: dict, key: str) -> dict:
    t = raw.get(key, {})
    if not isinstance(t, dict):
        raise _err(path, key, "must be a table")
    return t


def _str_map(path: Path, key: str, m) -> dict[str, str]:
    if not isinstance(m, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in m.items()):
        raise _err(path, key, "must be a table of text values")
    return dict(m)


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _directives(corpus: Path) -> set[str]:
    f = corpus / "directives.toml"
    try:
        text = f.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise PillarsError(f"{f}: missing") from None
    try:
        return set(tomllib.loads(text).get("directive", {}))
    except tomllib.TOMLDecodeError as e:
        raise PillarsError(f"{f}: not valid TOML: {e}") from None


def load_directive_policies(corpus: Path) -> dict[str, dict[str, str]]:
    """Each directive's policies (policy -> option) from `<corpus>/directives.toml`: what the console
    tries to set (levers design ruling 3; the game reports which it did)."""
    f = Path(corpus) / "directives.toml"
    try:
        raw = tomllib.loads(f.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise PillarsError(f"{f}: missing") from None
    except tomllib.TOMLDecodeError as e:
        raise PillarsError(f"{f}: not valid TOML: {e}") from None
    return {name: dict(d.get("policies") or {}) for name, d in (raw.get("directive") or {}).items()}


def _manifest_keys(path: Path, corpus: Path, dotted, key: str) -> tuple[str, ...]:
    f = corpus / "manifest.toml"
    if not isinstance(dotted, str):
        raise _err(path, key, "must be a dotted table name in manifest.toml")
    try:
        node = tomllib.loads(f.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise _err(path, key, f"cannot read {f}: {e}") from None
    for part in dotted.split("."):
        node = node.get(part) if isinstance(node, dict) else None
    if not isinstance(node, dict) or not node:
        raise _err(path, key, f"manifest.toml has no table [{dotted}]")
    return tuple(node)


def _action(path: Path, corpus: Path, kind: str, t) -> ActionLimits:
    where = f"actions.{kind}"
    if kind not in ACTION_KINDS:
        raise _err(path, where, f"unknown action kind (known: {', '.join(ACTION_KINDS)})")
    if not isinstance(t, dict):
        raise _err(path, where, "must be a table")
    _unknown(path, where, t, _ACTION_KEYS[kind])
    for req in _ACTION_REQUIRED[kind]:
        if req not in t:
            raise _err(path, f"{where}.{req}", "required limit is missing")
    fld = t.get("field", ACTION_KINDS[kind])
    if fld != ACTION_KINDS[kind]:
        raise _err(path, f"{where}.field", f"must be {ACTION_KINDS[kind]!r}")
    if not _int(t["max_items"]) or t["max_items"] < 1:
        raise _err(path, f"{where}.max_items", "must be an integer >= 1")
    resources: tuple[str, ...] = ()
    if "resources_from_manifest" in t:
        resources = _manifest_keys(path, corpus, t["resources_from_manifest"], f"{where}.resources_from_manifest")
    lo, hi = t.get("amount_min", 1), t.get("amount_max")
    if hi is not None and not (_int(lo) and _int(hi) and 1 <= lo <= hi):
        raise _err(path, f"{where}.amount_max", "amounts must be integers with 1 <= amount_min <= amount_max")
    share = t.get("sell_income_share")
    if share is not None and not (isinstance(share, (int, float)) and not isinstance(share, bool) and 0 < share <= 1):
        raise _err(path, f"{where}.sell_income_share", "must be a number in (0, 1]")
    idle = t.get("sell_requires_idle", False)
    if not isinstance(idle, bool):
        raise _err(path, f"{where}.sell_requires_idle", "must be true or false")
    ids = t.get("ids_from_corpus")
    if isinstance(ids, list):
        if not ids or not all(isinstance(i, str) and _ID.match(i) for i in ids):
            raise _err(path, f"{where}.ids_from_corpus", "must name data/<name>.json files")
        ids = tuple(ids)
    elif ids is not None and (not isinstance(ids, str) or not _ID.match(ids)):
        raise _err(path, f"{where}.ids_from_corpus", "must name a data/<name>.json file")
    note = t.get("note", "")
    if not isinstance(note, str):
        raise _err(path, f"{where}.note", "must be text")
    orders = t.get("max_orders", 1)
    if not _int(orders) or orders < 1:
        raise _err(path, f"{where}.max_orders", "must be an integer >= 1")
    full = t.get("full_ids", False)
    if not isinstance(full, bool):
        raise _err(path, f"{where}.full_ids", "must be true or false")
    reserves = {}
    for key in ("gold_reserve", "faith_reserve"):
        v = t.get(key, 0)
        if not _int(v) or v < 0:
            raise _err(path, f"{where}.{key}", "must be an integer >= 0")
        reserves[key] = v
    shares = {}
    for key in ("treasury_share", "threatened_share"):
        v = t.get(key)
        if v is not None and not (_num(v) and 0 < v <= 1):
            raise _err(path, f"{where}.{key}", "must be a number in (0, 1]")
        shares[key] = None if v is None else float(v)
    if shares["threatened_share"] is not None and shares["threatened_share"] < (shares["treasury_share"] or 0):
        raise _err(path, f"{where}.threatened_share", "must be at least treasury_share")
    buyout: dict = {}
    per = t.get("gold_reserve_per_deficit", 0)
    if not _num(per) or per < 0:
        raise _err(path, f"{where}.gold_reserve_per_deficit", "must be a number >= 0")
    buyout["gold_reserve_per_deficit"] = float(per)
    for key in ("pantheon_reserve", "defence_first"):
        v = t.get(key, False)
        if not isinstance(v, bool):
            raise _err(path, f"{where}.{key}", "must be true or false")
        buyout[key] = v
    for key in ("prophet_faith_reserve", "skip_turns_left", "defence_cooldown_turns"):
        v = t.get(key, 0)
        if not _int(v) or v < 0:
            raise _err(path, f"{where}.{key}", "must be an integer >= 0")
        buyout[key] = v
    classes = t.get("defender_classes", [])
    if not isinstance(classes, list) or not all(isinstance(c, str) and c.strip() for c in classes):
        raise _err(path, f"{where}.defender_classes", "must be a list of unit classes (data/unit.json fields.class)")
    if buyout["defence_first"] and not classes:
        raise _err(path, f"{where}.defender_classes", "defence_first needs the unit classes that defend a city")
    buyout["defender_classes"] = tuple(c.strip() for c in classes)
    return ActionLimits(kind=kind, field=fld, max_items=t["max_items"], ids_from_corpus=ids, resources=resources,
                        amount_min=lo, amount_max=hi, sell_income_share=None if share is None else float(share),
                        sell_requires_idle=idle, note=note.strip(), max_orders=orders, full_ids=full,
                        **reserves, **shares, **buyout)


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _weights(path: Path, t, n: int) -> WeightsSpec:
    if not isinstance(t, dict):
        raise _err(path, "weights", "must be a table")
    _unknown(path, "weights", t, _WEIGHTS_KEYS)
    d = WeightsSpec()
    mode = t.get("mode", d.mode)
    if mode not in ("exclusive", "share"):
        raise _err(path, "weights.mode", 'must be "exclusive" or "share"')
    lo = t.get("min", d.min)
    if not _int(lo) or not 0 <= lo <= 100 // n:
        raise _err(path, "weights.min", f"must be 0..{100 // n} (at most 100 / {n} pillars)")
    hi = t.get("max", d.max)
    if not _int(hi) or not lo <= hi <= 100 or hi * n < 100:
        raise _err(path, "weights.max", f"must be min..100 and leave room for 100 across {n} pillars")
    for key in ("spread", "switch_margin"):
        v = t.get(key, getattr(d, key))
        if not _num(v) or v < 1:
            raise _err(path, f"weights.{key}", "must be a number >= 1")
    stall_years = t.get("stall_years", d.stall_years)
    if not _num(stall_years) or stall_years < 0:
        raise _err(path, "weights.stall_years", "must be a number >= 0")
    stall_factor = t.get("stall_factor", d.stall_factor)
    if not _num(stall_factor) or not 0 < stall_factor <= 1:
        raise _err(path, "weights.stall_factor", "must be a number in (0, 1]")
    need_raw = t.get("need", {})
    if not isinstance(need_raw, dict):
        raise _err(path, "weights.need", "must be a table")
    _unknown(path, "weights.need", need_raw, set(NEED_STATUSES))
    need = dict(d.need)
    for k, v in need_raw.items():
        if not _num(v) or v < 0:
            raise _err(path, f"weights.need.{k}", "must be a number >= 0")
        need[k] = float(v)
    return WeightsSpec(mode=mode, min=lo, max=hi, spread=float(t.get("spread", d.spread)),
                       switch_margin=float(t.get("switch_margin", d.switch_margin)), need=need,
                       stall_years=float(stall_years), stall_factor=float(stall_factor))


def _orders(path: Path, t) -> OrdersSpec:
    if not isinstance(t, dict):
        raise _err(path, "orders", "must be a table")
    _unknown(path, "orders", t, _ORDERS_KEYS)
    d = OrdersSpec()
    ints = {}
    for key, lo in (("window_turns", 1), ("min_resolved", 1), ("open_cap_turns", 1), ("open_grace_turns", 0)):
        v = t.get(key, getattr(d, key))
        if not _int(v) or v < lo:
            raise _err(path, f"orders.{key}", f"must be an integer >= {lo}")
        ints[key] = v
    if ints["open_grace_turns"] > ints["open_cap_turns"]:
        raise _err(path, "orders.open_grace_turns", "must be at most open_cap_turns")
    rate = t.get("weak_rate", d.weak_rate)
    if not _num(rate) or not 0 < rate < 1:
        raise _err(path, "orders.weak_rate", "must be a number in (0, 1)")
    raw = t.get("min_samples", {})
    if not isinstance(raw, dict):
        raise _err(path, "orders.min_samples", "must be a table")
    _unknown(path, "orders.min_samples", raw, set(ORDER_SAMPLE_GROUPS))
    samples = dict(d.min_samples)
    for k, v in raw.items():
        if not _int(v) or v < 1:
            raise _err(path, f"orders.min_samples.{k}", "must be an integer >= 1")
        samples[k] = v
    return OrdersSpec(min_samples=types.MappingProxyType(samples), weak_rate=float(rate), **ints)


def _parse(path: Path, corpus: Path) -> PillarSpec:
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise PillarsError(f"{path}: not valid TOML: {e}") from None
    _unknown(path, "", raw, _TOP_KEYS)
    strat = _table(path, raw, "strategy")
    _unknown(path, "strategy", strat, _STRATEGY_KEYS)
    mt = _table(path, raw, "metrics")
    _unknown(path, "metrics", mt, _METRICS_KEYS)
    names = mt.get("names")
    if not isinstance(names, list) or not names or not all(isinstance(n, str) and n for n in names):
        raise _err(path, "metrics.names", "must be a non-empty list of metric names")
    aliases = _str_map(path, "strategy.metric_aliases", strat.get("metric_aliases", {}))
    for a, target in aliases.items():
        if target not in names:
            raise _err(path, f"strategy.metric_aliases.{a}", f"alias to unknown metric {target!r}")
    row_keys = _str_map(path, "metrics.row_keys", mt.get("row_keys", {}))
    for k in row_keys:
        if k not in names:
            raise _err(path, f"metrics.row_keys.{k}", "not a metric in metrics.names")
    exclude = mt.get("milestone_exclude", [])
    if not isinstance(exclude, list) or not all(isinstance(m, str) and m in names for m in exclude):
        raise _err(path, "metrics.milestone_exclude", "must be a list of metrics from metrics.names")
    actions = {kind: _action(path, corpus, kind, t) for kind, t in _table(path, raw, "actions").items()}
    pillars_raw = _table(path, raw, "pillars")
    # a game whose pillars rank no directive (share mode, e.g. Civ VI) needs no directives.toml
    ranks = isinstance(pillars_raw, dict) and any(isinstance(t, dict) and "directive" in t for t in pillars_raw.values())
    directives = _directives(corpus) if ranks else set()
    if not pillars_raw:
        raise _err(path, "pillars", "at least one pillar is required")
    pillars: dict[str, PillarDef] = {}
    ranked_by: dict[str, str] = {}
    for pid, t in pillars_raw.items():
        where = f"pillars.{pid}"
        if not _ID.match(pid) or pid in _RESERVED_IDS or pid.startswith("model_") or hasattr(BaseModel, pid):
            raise _err(path, where, "pillar ids are [a-z][a-z0-9_]*, not focus/reason/pillars or a pydantic name")
        if not isinstance(t, dict):
            raise _err(path, where, "must be a table")
        _unknown(path, where, t, _PILLAR_KEYS)
        for k in ("label", "description"):
            if not isinstance(t.get(k), str) or not t[k].strip():
                raise _err(path, f"{where}.{k}", "required text")
        d = t.get("directive")
        if d is not None:
            if not isinstance(d, str) or d not in directives:
                raise _err(path, f"{where}.directive", f"{d!r} is not a directive in directives.toml")
            if d in ranked_by:
                raise _err(path, f"{where}.directive", f"{d!r} is already ranked by pillar {ranked_by[d]}")
            ranked_by[d] = pid
        acts = t.get("actions", [])
        if not isinstance(acts, list) or not all(isinstance(a, str) for a in acts):
            raise _err(path, f"{where}.actions", "must be a list of action kinds")
        for a in acts:
            if a not in actions:
                raise _err(path, f"{where}.actions", f"action {a!r} has no [actions.{a}] limits")
        pillars[pid] = PillarDef(pid, t["label"].strip(), t["description"].strip(), d, tuple(acts))
    top = strat.get("min_milestones_top", 0)
    if not _int(top) or not 0 <= top <= len(pillars):
        raise _err(path, "strategy.min_milestones_top", f"must be 0..{len(pillars)}")
    detail = {}
    for key, hi in (("min_milestones_each", 6), ("min_milestones_first", 6), ("min_goals", 3),
                    ("min_goals_top", len(pillars))):
        v = strat.get(key, 0)
        if not _int(v) or not 0 <= v <= hi:
            raise _err(path, f"strategy.{key}", f"must be 0..{hi}")
        detail[key] = v
    figure = strat.get("stance_needs_figure", False)
    if not isinstance(figure, bool):
        raise _err(path, "strategy.stance_needs_figure", "must be true or false")
    instructions = strat.get("instructions", "")
    if not isinstance(instructions, str):
        raise _err(path, "strategy.instructions", "must be text")
    identity = strat.get("identity", "")
    if not isinstance(identity, str):
        raise _err(path, "strategy.identity", "must be text")
    date_format = strat.get("date_format", "calendar")
    if date_format not in DATE_FORMATS:
        raise _err(path, "strategy.date_format", f"must be one of {', '.join(DATE_FORMATS)}")
    weights = _weights(path, raw.get("weights", {}), len(pillars))
    orders = _orders(path, raw["orders"]) if "orders" in raw else None
    return PillarSpec(game=corpus.name, weights=weights, orders=orders, milestone_exclude=tuple(exclude), pillars=types.MappingProxyType(pillars), metrics=tuple(names),
                      metric_aliases=types.MappingProxyType(aliases), row_keys=types.MappingProxyType(row_keys),
                      actions=types.MappingProxyType(actions), min_milestones_top=top, stance_needs_figure=figure,
                      instructions=instructions.strip(), date_format=date_format,
                      identity=identity.strip(), **detail)
