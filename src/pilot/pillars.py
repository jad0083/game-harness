"""Game pillars: each game's strategy guardrails, read from corpora/<game>/pillars.toml
(docs/superpowers/specs/2026-09-26-game-pillars-design.md).

Pure data; no model calls, no game input. Unknown keys are an error (fail fast, naming the key)."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel

# The action kinds the harness can validate and carry out, and the Pillar field each one fills.
ACTION_KINDS: dict[str, str] = {"tech": "prefer_techs", "market": "market"}
_ACTION_KEYS = {
    "tech": {"field", "max_items", "ids_from_corpus", "note"},
    "market": {"field", "max_items", "resources_from_manifest", "amount_min", "amount_max",
               "sell_income_share", "sell_requires_idle", "note"},
}
_ACTION_REQUIRED = {"tech": ("max_items", "ids_from_corpus"),
                    "market": ("max_items", "resources_from_manifest", "amount_max")}
_TOP_KEYS = {"strategy", "metrics", "pillars", "actions"}
_STRATEGY_KEYS = {"min_milestones_top", "metric_aliases", "instructions"}
_METRICS_KEYS = {"names", "row_keys"}
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
    ids_from_corpus: str | None = None
    resources: tuple[str, ...] = ()
    amount_min: int = 1
    amount_max: int | None = None
    sell_income_share: float | None = None
    sell_requires_idle: bool = False
    note: str = ""


@dataclass(frozen=True)
class PillarSpec:
    game: str
    pillars: dict[str, PillarDef]
    metrics: tuple[str, ...]
    metric_aliases: dict[str, str] = field(default_factory=dict)
    row_keys: dict[str, str] = field(default_factory=dict)
    actions: dict[str, ActionLimits] = field(default_factory=dict)
    min_milestones_top: int = 0
    instructions: str = ""

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
        return {"game": self.game, "metrics": list(self.metrics), "min_milestones_top": self.min_milestones_top,
                "pillars": [{"id": p.id, "label": p.label, "description": p.description, "directive": p.directive,
                             "actions": list(p.actions)} for p in self.pillars.values()],
                "actions": {k: {"field": a.field, "max_items": a.max_items, "resources": list(a.resources),
                                "amount_min": a.amount_min, "amount_max": a.amount_max}
                            for k, a in self.actions.items()}}


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
    if not f.exists():
        return set()
    try:
        return set(tomllib.loads(f.read_text(encoding="utf-8")).get("directive", {}))
    except tomllib.TOMLDecodeError as e:
        raise PillarsError(f"{f}: not valid TOML: {e}") from None


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
    if ids is not None and (not isinstance(ids, str) or not _ID.match(ids)):
        raise _err(path, f"{where}.ids_from_corpus", "must name a data/<name>.json file")
    note = t.get("note", "")
    if not isinstance(note, str):
        raise _err(path, f"{where}.note", "must be text")
    return ActionLimits(kind=kind, field=fld, max_items=t["max_items"], ids_from_corpus=ids, resources=resources,
                        amount_min=lo, amount_max=hi, sell_income_share=None if share is None else float(share),
                        sell_requires_idle=idle, note=note.strip())


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
    actions = {kind: _action(path, corpus, kind, t) for kind, t in _table(path, raw, "actions").items()}
    directives = _directives(corpus)
    pillars_raw = _table(path, raw, "pillars")
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
    instructions = strat.get("instructions", "")
    if not isinstance(instructions, str):
        raise _err(path, "strategy.instructions", "must be text")
    return PillarSpec(game=corpus.name, pillars=pillars, metrics=tuple(names), metric_aliases=aliases,
                      row_keys=row_keys, actions=actions, min_milestones_top=top, instructions=instructions.strip())
