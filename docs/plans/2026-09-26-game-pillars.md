# Game Pillars Implementation Plan

**Goal:** Move the strategy layer's Stellaris-specific pillars, directive mapping, metrics, aliases and action limits into `corpora/<game>/pillars.toml`, and drive validation, the Strategist's schema and prompt, decisions, actions, human edits and the dashboard from that file.

**Architecture:** A new pure module `src/pilot/pillars.py` loads and validates `corpora/<game>/pillars.toml` into a frozen `PillarSpec` (cached per corpus). `src/pilot/strategy.py` stays the stored data model but every rule takes the spec, and it generates the Strategist's output model (one named optional field per pillar, action fields only on declaring pillars) and prompt from it. The governor loads the spec per game (strategy layer off with one clear error when the file is missing or invalid), dispatches actions through a kind → game-method hook table, and the dashboard serves the spec with `/api/strategy` so the Strategy tab renders labels, ranking and edit fields from it.

**Tech Stack:** Python 3.13 (`tomllib`, dataclasses), pydantic v2 (`create_model`, `model_validator`), pydantic-ai (`FunctionModel` in tests), aiohttp, SQLite telemetry, vanilla JS dashboard, Playwright (headless check only, not committed).

**Spec:** `docs/design/2026-09-26-game-pillars-design.md`

## Global Constraints

- Stellaris behaviour is unchanged: 7 pillars `economy`, `expansion`, `technology`, `diplomacy`, `defence`, `government`, `society`; directives `consolidate_economy`, `expand`, `tech_rush`, `diplomacy_first`, `defend` (economy, expansion, technology, diplomacy, defence); `government`/`society` rank none.
- Stellaris market: max 1 order, amount 1..25, a sell ≤ 20% of that resource's monthly income, sell only an idle resource, resources = keys of manifest `[ui.market.resources]`, no `trade`; techs ≤ 6 (`prefer_techs`, ids from `data/tech.json`).
- New rule (spec §2): each of the top `min_milestones_top` (Stellaris: 3) pillars needs ≥ 1 milestone in a model review; pinned pillars and human edits are exempt.
- Commits only via `scripts/ci-commit.sh "<conventional msg>" "<body>"` (runs `scripts/ci.sh`; commits only on `CI OK`).
- No AI attribution anywhere (no `Co-Authored-By`, no "generated with", no model names in code or commit text).
- Tests never reach a real model provider (`FunctionModel` only; the `setup` fixture sets `fallback_model=None`).
- Run pytest as `timeout 180 .venv/bin/python -m pytest -q -p no:cacheprovider` (append test paths/`-k` as given in each step).
- Game knowledge lives in corpora (`pillars.toml`, `directives.toml`, `manifest.toml`); Python stays game-agnostic (no pillar ids, directive names, metric names or resource names in `pillars.py`/`strategy.py`).
- Out of scope: Civ VI's own pillars file and hooks; changing directives (`GovernorDecision`'s literal list stays).

## Review Focus

1. **A stored strategy whose pillar ids are not the spec's** (a future rename, or a campaign from before a pillars change): treated as no strategy, logged as a `briefing_error` naming both id lists, and a review runs at start. Test: Task 4 `test_a_stored_strategy_with_other_pillar_ids_is_treated_as_none`.
2. **A pillars file with an unknown key, or a directive not in `directives.toml`**: load fails with a message naming the file and the dotted key; the governor starts without the strategy layer (decisions as before the layer) and logs one `strategy_disabled` event. Tests: Task 1 `test_unknown_keys_are_an_error_naming_the_key`, `test_a_directive_must_exist_in_directives_toml`; Task 4 `test_an_invalid_pillars_file_turns_the_layer_off_naming_the_key`.
3. **A Claude-style answer with named pillar fields** (`{"economy": {...}, "defence": {...}, "focus": ...}`, no `pillars` dict): the generated schema has one named property per pillar, no additionalProperties-only object, and the answer converts to a valid `Strategy` with milestones kept; action fields exist only on declaring pillars. Tests: Task 3 `test_the_review_schema_has_one_named_field_per_pillar`, `test_a_claude_style_answer_converts_to_a_valid_strategy`, `test_action_fields_exist_only_on_declaring_pillars`, `test_a_named_field_review_is_accepted_with_its_milestones`.
4. **A game spec with a pillar that declares an action the game has no hook for**: logged "not supported" once, skipped; other actions still run; play never stops. Test: Task 4 `test_a_declared_action_without_a_game_hook_is_skipped_once`.
5. **The dashboard rendering a spec with 3 pillars and no directives**: labels from the spec, ranking "–", no action fields, no console errors. Tests: Task 5 `test_strategy_api_serves_a_three_pillar_spec_in_the_viewer` + headless check script.

---

### Task 1: Pillars loader and the Stellaris pillars file

**Files:**
- Create: `src/pilot/pillars.py`
- Create: `corpora/stellaris/pillars.toml`
- Test: `tests/test_pillars.py` (new)

**Interfaces:**
- Consumes: `corpora/stellaris/directives.toml` (`[directive.<name>]` tables), `corpora/stellaris/manifest.toml` (`[ui.market.resources]`).
- Produces (module `pilot.pillars`):
  - `ACTION_KINDS: dict[str, str]` = `{"tech": "prefer_techs", "market": "market"}` (action kind → `Pillar` field)
  - `class PillarsError(ValueError)` — message `"<path>: <dotted.key>: <reason>"`
  - `@dataclass(frozen=True) PillarDef(id: str, label: str, description: str, directive: str | None = None, actions: tuple[str, ...] = ())`
  - `@dataclass(frozen=True) ActionLimits(kind: str, field: str, max_items: int, ids_from_corpus: str | None = None, resources: tuple[str, ...] = (), amount_min: int = 1, amount_max: int | None = None, sell_income_share: float | None = None, sell_requires_idle: bool = False, note: str = "")`
  - `@dataclass(frozen=True) PillarSpec(game: str, pillars: dict[str, PillarDef], metrics: tuple[str, ...], metric_aliases: dict[str, str], row_keys: dict[str, str], actions: dict[str, ActionLimits], min_milestones_top: int, instructions: str)` with `ids -> tuple[str, ...]`, `directive_of(pillar: str) -> str | None`, `alias(metric: str) -> str`, `owners(kind: str) -> list[str]`, `public() -> dict`
  - `load_pillars(corpus_dir: Path) -> PillarSpec` (cached per `(resolved path, mtime_ns)`)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_pillars.py
import os
import shutil
import tomllib

import pytest

from pilot.config import REPO
from pilot.pillars import PillarsError, load_pillars

MINI = '''[strategy]
min_milestones_top = 1
metric_aliases = { mil = "military_power" }

[metrics]
names = ["systems", "military_power"]

[pillars.economy]
label = "Economy"
description = "Income."
directive = "consolidate_economy"
actions = ["market"]

[pillars.society]
label = "Society"
description = "Pops."

[actions.market]
max_items = 1
resources_from_manifest = "ui.market.resources"
amount_max = 25
'''


def corpus(tmp_path, text=MINI):
    d = tmp_path / "g"
    d.mkdir(exist_ok=True)
    for f in ("directives.toml", "manifest.toml"):
        shutil.copy(REPO / "corpora/stellaris" / f, d / f)
    (d / "pillars.toml").write_text(text, encoding="utf-8")
    return d


def test_the_stellaris_file_reproduces_todays_pillars():
    spec = load_pillars(REPO / "corpora/stellaris")
    assert spec.game == "stellaris"
    assert spec.ids == ("economy", "expansion", "technology", "diplomacy", "defence", "government", "society")
    assert {p: spec.directive_of(p) for p in spec.ids} == {
        "economy": "consolidate_economy", "expansion": "expand", "technology": "tech_rush",
        "diplomacy": "diplomacy_first", "defence": "defend", "government": None, "society": None}
    rank = ("systems", "pops", "techs", "military_power", "economy_power", "tech_power", "colonies")
    assert spec.metrics == ("systems", "colonies", "pops", "techs_known", "military_power", "economy_power",
                            "tech_power", *(f"rank:{m}" for m in rank))
    for alias, real in (("rank:military", "rank:military_power"), ("rank:economy", "rank:economy_power"),
                        ("rank:tech", "rank:tech_power"), ("military", "military_power"), ("techs", "techs_known"),
                        ("planets", "colonies"), (" pops ", "pops")):
        assert spec.alias(alias) == real
    assert spec.row_keys == {"colonies": "planets"}
    assert spec.min_milestones_top == 3
    assert spec.owners("market") == ["economy"] and spec.owners("tech") == ["technology"]
    m, t = spec.actions["market"], spec.actions["tech"]
    assert (m.field, m.max_items, m.amount_min, m.amount_max, m.sell_income_share, m.sell_requires_idle) == \
        ("market", 1, 1, 25, 0.2, True)
    manifest = tomllib.loads((REPO / "corpora/stellaris/manifest.toml").read_text(encoding="utf-8"))
    assert set(m.resources) == set(manifest["ui"]["market"]["resources"]) and "trade" not in m.resources
    assert (t.field, t.max_items, t.ids_from_corpus) == ("prefer_techs", 6, "tech")
    assert "Market orders cannot use trade" in m.note
    assert "the defence stance must name its exit condition" in spec.instructions


def test_public_view_lists_pillars_in_file_order_with_actions():
    pub = load_pillars(REPO / "corpora/stellaris").public()
    assert [p["id"] for p in pub["pillars"]][:3] == ["economy", "expansion", "technology"]
    assert pub["pillars"][0] == {"id": "economy", "label": "Economy", "description": pub["pillars"][0]["description"],
                                 "directive": "consolidate_economy", "actions": ["market"]}
    assert pub["actions"]["market"]["max_items"] == 1 and pub["actions"]["tech"]["field"] == "prefer_techs"


def test_a_minimal_file_loads(tmp_path):
    spec = load_pillars(corpus(tmp_path))
    assert spec.ids == ("economy", "society") and spec.directive_of("society") is None
    assert spec.alias("mil") == "military_power"


def test_unknown_keys_are_an_error_naming_the_key(tmp_path):
    with pytest.raises(PillarsError, match=r"pillars\.toml: pillars\.society\.colour: unknown key"):
        load_pillars(corpus(tmp_path, MINI.replace('label = "Society"', 'label = "Society"\ncolour = "red"')))
    with pytest.raises(PillarsError, match=r": extras: unknown key"):
        load_pillars(corpus(tmp_path, MINI + '\n[extras]\nx = 1\n'))
    with pytest.raises(PillarsError, match=r": actions\.market\.colour: unknown key"):
        load_pillars(corpus(tmp_path, MINI + 'colour = "red"\n'))


def test_a_directive_must_exist_in_directives_toml(tmp_path):
    with pytest.raises(PillarsError, match=r"pillars\.economy\.directive: 'hoard' is not a directive in directives\.toml"):
        load_pillars(corpus(tmp_path, MINI.replace('"consolidate_economy"', '"hoard"')))


def test_two_pillars_cannot_rank_the_same_directive(tmp_path):
    text = MINI.replace('description = "Pops."', 'description = "Pops."\ndirective = "consolidate_economy"')
    with pytest.raises(PillarsError, match="already ranked by pillar economy"):
        load_pillars(corpus(tmp_path, text))


def test_an_action_without_limits_is_an_error(tmp_path):
    with pytest.raises(PillarsError, match=r"pillars\.economy\.actions: action 'market' has no \[actions\.market\] limits"):
        load_pillars(corpus(tmp_path, MINI.split("[actions.market]")[0]))
    with pytest.raises(PillarsError, match=r"actions\.market\.amount_max: required limit is missing"):
        load_pillars(corpus(tmp_path, MINI.replace("amount_max = 25\n", "")))
    with pytest.raises(PillarsError, match=r"actions\.build: unknown action kind"):
        load_pillars(corpus(tmp_path, MINI + "\n[actions.build]\nmax_items = 1\n"))


def test_a_metric_alias_must_name_a_known_metric(tmp_path):
    with pytest.raises(PillarsError, match=r"strategy\.metric_aliases\.mil: alias to unknown metric 'might'"):
        load_pillars(corpus(tmp_path, MINI.replace('mil = "military_power"', 'mil = "might"')))


def test_reserved_and_invalid_pillar_ids_are_rejected(tmp_path):
    for bad in ("focus", "reason", "pillars", "copy", "model_x"):
        with pytest.raises(PillarsError, match=rf"pillars\.{bad}: pillar ids"):
            load_pillars(corpus(tmp_path, MINI.replace("[pillars.society]", f"[pillars.{bad}]")))


def test_min_milestones_top_is_at_most_the_pillar_count(tmp_path):
    with pytest.raises(PillarsError, match=r"strategy\.min_milestones_top: must be 0\.\.2"):
        load_pillars(corpus(tmp_path, MINI.replace("min_milestones_top = 1", "min_milestones_top = 3")))


def test_a_missing_file_is_an_error(tmp_path):
    d = tmp_path / "none"
    d.mkdir()
    with pytest.raises(PillarsError, match=r"pillars\.toml: missing"):
        load_pillars(d)


def test_loads_are_cached_until_the_file_changes(tmp_path):
    d = corpus(tmp_path)
    first = load_pillars(d)
    assert load_pillars(d) is first
    (d / "pillars.toml").write_text(MINI.replace('label = "Society"', 'label = "People"'), encoding="utf-8")
    st = (d / "pillars.toml").stat()
    os.utime(d / "pillars.toml", ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))
    assert load_pillars(d).pillars["society"].label == "People"
```

- [ ] **Step 2: Run to verify they fail**

Run: `timeout 180 .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_pillars.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'pilot.pillars'`.

- [ ] **Step 3: Write `corpora/stellaris/pillars.toml`**

```toml
# Stellaris strategy pillars: what the Strategist may write and how it is checked, which directive
# each pillar ranks, which metrics milestones may use, and the limits of the two player actions.
# Loaded by src/pilot/pillars.py (docs/design/2026-09-26-game-pillars-design.md).
# Unknown keys are an error; directives must exist in directives.toml. Pillar order = display
# fallback; priorities come from the Strategist.

[strategy]
min_milestones_top = 3          # each of the 3 highest-priority pillars needs >= 1 milestone
# spellings models use for the recorded measures (seen live: "rank:military" on 2452.03)
metric_aliases = { military = "military_power", economy = "economy_power", tech = "tech_power", planets = "colonies", techs = "techs_known", "rank:military" = "rank:military_power", "rank:economy" = "rank:economy_power", "rank:tech" = "rank:tech_power", "rank:planets" = "rank:colonies" }
instructions = """Everything must be achievable through directives, tech picks or market orders: the game's AI builds, designs ships and moves fleets. Build on the empire's species, ethics, civics and origin.
While at war, the defence stance must name its exit condition (peace, war exhaustion, or planets retaken). When a hostile neighbour's military is twice ours or more, a defence goal is two shipyards in different systems and alloy production on two or more planets; never reason from a naval-capacity cap the briefing does not show."""

[metrics]
# the briefing's recorded measures; rank:<measure> is our standing among the empires, 1 = best
names = ["systems", "colonies", "pops", "techs_known", "military_power", "economy_power", "tech_power",
         "rank:systems", "rank:pops", "rank:techs", "rank:military_power", "rank:economy_power",
         "rank:tech_power", "rank:colonies"]
row_keys = { colonies = "planets" }   # metrics rows store colonies as `planets`

[pillars.economy]
label = "Economy"
description = "Income, deficits, stockpiles and the market."
directive = "consolidate_economy"
actions = ["market"]

[pillars.expansion]
label = "Expansion"
description = "Outposts, colonies, systems and exploration."
directive = "expand"

[pillars.technology]
label = "Technology"
description = "Research speed and which techs to take."
directive = "tech_rush"
actions = ["tech"]

[pillars.diplomacy]
label = "Diplomacy"
description = "Relations, pacts, federations and the galactic community."
directive = "diplomacy_first"

[pillars.defence]
label = "Defence"
description = "Fleets, starbases, wars and chokepoints."
directive = "defend"

[pillars.government]
label = "Government"
description = "Policies, civics, factions and stability."

[pillars.society]
label = "Society"
description = "Pops, species, amenities and happiness."

# At most one order until ui.market.order_row_pitch is measured live: the controller can only
# find (and so remove) the first order row. Amounts equal mcp.rs MARKET_AMOUNT_MIN/MAX.
[actions.market]
max_items = 1
resources_from_manifest = "ui.market.resources"
amount_min = 1
amount_max = 25
sell_income_share = 0.2        # a sell takes at most 20% of that resource's monthly income
sell_requires_idle = true      # sell only a resource the briefing flags IDLE
note = "Market orders cannot use trade; sell only idle energy, minerals, food, consumer goods or alloys (strategic resources can only be bought)."

# Equals mcp.rs stellaris_pick_tech's limit on `prefer`.
[actions.tech]
field = "prefer_techs"
max_items = 6
ids_from_corpus = "tech"       # data/tech.json
```

- [ ] **Step 4: Write `src/pilot/pillars.py`**

```python
"""Game pillars: each game's strategy guardrails, read from corpora/<game>/pillars.toml
(docs/design/2026-09-26-game-pillars-design.md).

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
```

- [ ] **Step 5: Run to verify they pass**

Run: `timeout 180 .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_pillars.py`
Expected: PASS (13 tests). Then the full suite: `timeout 180 .venv/bin/python -m pytest -q -p no:cacheprovider` — PASS (nothing else uses the module yet).

- [ ] **Step 6: Commit**

```bash
git add src/pilot/pillars.py corpora/stellaris/pillars.toml tests/test_pillars.py
scripts/ci-commit.sh "feat(pilot): game pillars file and loader" "corpora/<game>/pillars.toml defines each game's strategy pillars, directive mapping, metrics, aliases and action limits; src/pilot/pillars.py loads and validates it (unknown keys, unknown directives, actions without limits and aliases to unknown metrics fail naming the key) and caches it per corpus. The Stellaris file reproduces today's seven pillars and limits. Verified by tests/test_pillars.py."
```

---

### Task 2: Game-agnostic strategy rules driven by the spec

**Files:**
- Modify: `src/pilot/strategy.py` (whole file below)
- Modify: `src/pilot/governor.py` (call sites: imports line 30, `frame_text` ~239, `__init__` ~355, `edit_pillar` ~608, `_decide` ~956/~999, `_carry_out_market_actions` ~1111, `_milestones_text` ~1162, `_newly_missed_milestones` ~1173, `_review_strategy` ~1219/~1254)
- Modify: `src/pilot/dashboard.py` (`make_app` signature, new inner `campaign_spec`, `api_strategy` row keys)
- Test: `tests/test_strategy.py`, `tests/test_governor.py`

**Interfaces:**
- Consumes: `pilot.pillars.PillarSpec`, `ActionLimits`, `ACTION_KINDS`, `load_pillars` (Task 1).
- Produces (module `pilot.strategy`; `PILLARS`, `DIRECTIVE_OF`, `METRICS`, `METRIC_ALIASES`, `MARKET_*`, `SELL_INCOME_SHARE`, `MAX_MARKET_ORDERS` and `Strategy.ranking()` are removed):
  - `Milestone`, `MarketOrder`, `Pillar`, `Strategy` (fields unchanged; `Strategy.sorted_pillars()` kept; `Milestone` no longer aliases metrics itself, only strips them)
  - `ranking(s: Strategy, spec: PillarSpec) -> list[str]`
  - `apply_aliases(s: Strategy, spec: PillarSpec) -> Strategy`
  - `market_briefing_errors(o: MarketOrder, limits: ActionLimits, idle: set[str], income: dict[str, float]) -> list[str]`
  - `validate(s: Strategy, spec: PillarSpec, *, previous: Strategy | None, tech_ids: set[str], idle: set[str], income: dict[str, float], briefing_checked: set[str] | None = None, require_milestones: bool = True) -> list[str]`
  - `pinned_misfits(s: Strategy, spec: PillarSpec, *, idle: set[str], income: dict[str, float]) -> list[str]`
  - `keep_pinned(new: Strategy, previous: Strategy | None) -> Strategy` (unchanged)
  - `metric_value(row: dict, metric: str, row_keys: Mapping[str, str] | None = None) -> float | None`
  - `milestone_status(m: Milestone, rows: list[dict], today: str, row_keys: Mapping[str, str] | None = None) -> str`
  - governor: `frame_text(strategy: Strategy | None, spec: PillarSpec, milestones: str) -> str`; `Governor.pillars: PillarSpec` (strict load in this task; Task 4 makes it optional)
  - dashboard: `make_app(pilot, runs_dir: Path | None = None, telemetry=None, corpora: Path | None = None)`; inner `campaign_spec(cid: str) -> PillarSpec | None`
- Validation messages (later tasks match on them): `"missing pillar <id>"`, `"unknown pillar '<id>'"`, `"<id>: priority must be 1..<n>"`, `"<id>: unknown metric '<m>'"`, `"<id>: only the <owners joined ' / '> pillar may set <field>"`, `"<id>: <field> is not an action in this game"`, `"<id>: priority <p> is in the top <N> and needs at least one milestone"`, `"<id>: unknown market resource '<r>'"`, `"<id>: at most <n> preferred techs"`, `"<id>: at most <n> market order(s)"`.

- [ ] **Step 1: Update the tests first**

1a. In `tests/test_strategy.py`, replace the import block and helpers at the top (lines 1–19) with:

```python
import re
import tomllib

from pilot.config import REPO
from pilot.pillars import load_pillars
from pilot.strategy import (
    MarketOrder,
    Milestone,
    Pillar,
    Strategy,
    apply_aliases,
    keep_pinned,
    metric_value,
    milestone_status,
    ranking,
    validate,
)

SPEC = load_pillars(REPO / "corpora/stellaris")
PRIOS = {"defence": 1, "economy": 2, "technology": 3, "expansion": 4, "diplomacy": 5, "government": 6, "society": 7}
_M = Milestone(metric="systems", op=">=", target=10, by="2250.01.01")


def strat(**over) -> Strategy:
    pillars = {p: Pillar(priority=n, stance=f"{p} stance", goals=[f"{p} goal"], milestones=[_M]) for p, n in PRIOS.items()}
    pillars.update(over)
    return Strategy(pillars=pillars, focus="hold the line")


def test_ranking_follows_priorities_and_skips_pillars_without_a_directive():
    assert ranking(strat(), SPEC) == ["defend", "consolidate_economy", "tech_rush", "expand", "diplomacy_first"]
```

1b. Pass the spec to every `validate` / `pinned_misfits` call in that file (mechanical; run once):

```bash
.venv/bin/python - <<'EOF'
import pathlib, re
p = pathlib.Path("tests/test_strategy.py")
t = p.read_text(encoding="utf-8")
t = re.sub(r",(\s*)previous=", r", SPEC,\1previous=", t)
t = re.sub(r"pinned_misfits\((\w+), idle=", r"pinned_misfits(\1, SPEC, idle=", t)
p.write_text(t, encoding="utf-8")
EOF
```

1c. In `_econ` add the default milestone (it is priority 2, a top-3 pillar):

```python
def _econ(*orders, pinned=False):
    return Pillar(priority=2, stance="s", goals=["g"], market=list(orders), pinned=pinned, milestones=[_M],
                  edited_by="human" if pinned else "model")
```

1d. Replace these tests' bodies:

```python
def test_milestone_status_from_metrics_rows():
    rows = [{"date": "2240.01.01", "planets": 4}, {"date": "2241.01.01", "planets": 6}]
    rk = SPEC.row_keys
    m = Milestone(metric="colonies", op=">=", target=10, by="2243.01.01")
    assert milestone_status(m, rows, "2241.01.01", rk) == "on_track"          # +2/yr → 10 by 2243
    assert milestone_status(Milestone(metric="colonies", op=">=", target=12, by="2243.01.01"), rows, "2241.01.01", rk) == "at_risk"
    assert milestone_status(Milestone(metric="colonies", op=">=", target=5, by="2243.01.01"), rows, "2241.01.01", rk) == "met"
    assert milestone_status(Milestone(metric="colonies", op=">=", target=12, by="2240.06.01"), rows, "2241.01.01", rk) == "missed"
    assert milestone_status(m, [], "2241.01.01", rk) == "at_risk", "no data yet is at risk, not an error"


def test_metric_value_reads_counts_and_ranks():
    row = {"planets": 7, "systems": 20, "peers": {"military_power": {"rank": 9, "median": 3000}}}
    assert metric_value(row, "colonies", SPEC.row_keys) == 7 and metric_value(row, "systems") == 20
    assert metric_value(row, "colonies") is None, "without the row keys colonies is not a row field"
    assert metric_value(row, "rank:military_power") == 9
    assert metric_value(row, "rank:techs") is None
```

In `test_milestone_status_requires_at_least_12_months_of_data`, append `, SPEC.row_keys` as the fourth argument of each of its three `milestone_status(...)` calls.

```python
def test_trade_market_orders_are_rejected():
    """Trade is not a market resource (not a key of the manifest's [ui.market.resources])."""
    s = strat(economy=_econ({"side": "sell", "resource": "trade", "amount": 10}))
    errs = validate(s, SPEC, previous=None, tech_ids=set(), idle={"trade"}, income={})
    assert any("unknown market resource 'trade'" in e for e in errs)
    s2 = strat(economy=_econ({"side": "buy", "resource": "trade", "amount": 5}))
    errs2 = validate(s2, SPEC, previous=None, tech_ids=set(), idle=set(), income={})
    assert any("unknown market resource 'trade'" in e for e in errs2)


def test_market_resources_are_the_manifests_market_resources():
    manifest = tomllib.loads((REPO / "corpora/stellaris/manifest.toml").read_text(encoding="utf-8"))
    assert set(SPEC.actions["market"].resources) == set(manifest["ui"]["market"]["resources"])
    assert "trade" not in SPEC.actions["market"].resources


def test_python_market_amount_limits_equal_the_controllers():
    src = (REPO / "crates/game-controller/src/mcp.rs").read_text(encoding="utf-8")
    lo = re.search(r"const MARKET_AMOUNT_MIN: i64 = (\d+);", src)
    hi = re.search(r"const MARKET_AMOUNT_MAX: i64 = (\d+);", src)
    assert lo and hi, "mcp.rs declares its market amount limits as constants"
    m = SPEC.actions["market"]
    assert (m.amount_min, m.amount_max) == (int(lo.group(1)), int(hi.group(1)))
    body = src[src.index("fn validate_market_orders"):]
    body = body[:body.index("\n}\n")]
    assert "MARKET_AMOUNT_MIN..=MARKET_AMOUNT_MAX" in body, "validate_market_orders uses those constants"
```

1e. Append the new tests to `tests/test_strategy.py`:

```python
# ---- game pillars: rules come from the spec ------------------------------------------------------

def test_the_top_pillars_need_a_milestone():
    s = strat(economy=Pillar(priority=2, stance="s", goals=["g"]))
    errs = validate(s, SPEC, previous=None, tech_ids=set(), idle=set(), income={})
    assert "economy: priority 2 is in the top 3 and needs at least one milestone" in errs
    fine = strat(expansion=Pillar(priority=4, stance="s", goals=["g"]))
    assert validate(fine, SPEC, previous=None, tech_ids=set(), idle=set(), income={}) == [], "priority 4 needs none"


def test_a_pinned_top_pillar_without_milestones_is_not_rejected():
    s = strat(economy=Pillar(priority=2, stance="s", goals=["g"], pinned=True, edited_by="human"))
    assert validate(s, SPEC, previous=None, tech_ids=set(), idle=set(), income={}) == []


def test_human_edits_skip_the_milestone_rule():
    s = strat(economy=Pillar(priority=2, stance="s", goals=["g"]))
    assert validate(s, SPEC, previous=None, tech_ids=set(), idle=set(), income={}, require_milestones=False) == []


def test_action_fields_belong_to_the_pillars_that_declare_them():
    s = strat(diplomacy=Pillar(priority=5, stance="s", goals=["g"], prefer_techs=["tech_habitat_1"]))
    errs = validate(s, SPEC, previous=None, tech_ids={"tech_habitat_1"}, idle=set(), income={})
    assert errs == ["diplomacy: only the technology pillar may set prefer_techs"]


def test_aliases_come_from_the_spec():
    s = strat(economy=Pillar(priority=2, stance="s", milestones=[Milestone(metric=" rank:military ", op="<=", target=3, by="2250.01.01")]))
    assert apply_aliases(s, SPEC).pillars["economy"].milestones[0].metric == "rank:military_power"
    assert s.pillars["economy"].milestones[0].metric == "rank:military", "Milestone itself only strips"


def test_validation_uses_the_spec_metrics_and_pillar_count():
    bad = strat(society=Pillar(priority=8, stance="s", milestones=[Milestone(metric="culture", op=">=", target=1, by="2250.01.01")]))
    joined = " | ".join(validate(bad, SPEC, previous=None, tech_ids=set(), idle=set(), income={}))
    assert "society: priority must be 1..7" in joined and "society: unknown metric 'culture'" in joined
```

1f. In `tests/test_governor.py`:

- In the `setup` fixture change the copy tuple to `("manifest.toml", "pilot.md", "strategy.md", "directives.toml", "pillars.toml")`.
- After the imports add:

```python
from pilot.pillars import load_pillars

STELLARIS = load_pillars(REPO / "corpora/stellaris")


def _pillars_body(prios: dict[str, int], stance: str = "{p} by model") -> dict:
    """Strategist answer pillars; each top-3 pillar carries a milestone (pillars.toml min_milestones_top)."""
    return {p: {"priority": n, "stance": stance.format(p=p), "goals": ["g"],
                "milestones": [{"metric": "systems", "op": ">=", "target": 10, "by": "2230.01.01"}] if n <= 3 else []}
            for p, n in prios.items()}
```

- `planner_model` (~line 635): delete `from pilot.strategy import PILLARS`; replace the `strategy = {"pillars": ...}` assignment with:

```python
            strategy = {"pillars": _pillars_body({p: i + 1 for i, p in enumerate(STELLARIS.ids)}, "{p} stance"),
                        "focus": "Survey before expanding", "reason": "bottleneck in surveying"}
```

- `_strategist` (~line 1360): replace the body of `respond` down to `body = ...` with:

```python
    def respond(messages, info):
        calls.append("strategist")
        pillars = _pillars_body(prios)
        if pin_diplomacy_to:
            pillars["diplomacy"]["stance"] = pin_diplomacy_to
        body = {"change": change, "assessment": "ok", "rules": [],
                "strategy": {"pillars": pillars, "focus": "grow", "reason": "start"} if change else None}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, body)])
```
and delete its now-unused `from pilot.strategy import Pillar`.

- `test_strategy_review_updates_bookkeeping_and_saves_a_trace` (~1480) and `test_a_failed_reviews_retry_bypasses_the_event_cap_and_a_success_clears_it` (~1745): replace the `pillars = {p: Pillar(...).model_dump() for ...}` line with `pillars = _pillars_body(prios)`.
- `test_retro_every_counts_the_start_decision_when_no_review_ran` (~1605): delete `from pilot.strategy import PILLARS`; `enumerate(PILLARS)` → `enumerate(STELLARIS.ids)`.
- `_milestone_strategist` (~2689): replace its `pillars = ...` line with `pillars = _pillars_body(PRIOS)` (keep the following `pillars["economy"]["milestones"] = [...]` line).
- `g.strategy.ranking()` at ~1770 and ~1875 → `ranking(g.strategy, STELLARIS)` with `from pilot.strategy import ranking` inside each test.
- `test_edit_pillar_rejects_an_invalid_edit_and_leaves_strategy_unchanged` (~2242): `match="only the technology pillar prefers techs"` → `match="only the technology pillar may set prefer_techs"`.
- `test_frame_text_lists_only_at_risk_and_missed_milestones` (~2801): `frame_text(_strategy_with(), lines)` → `frame_text(_strategy_with(), STELLARIS, lines)`.
- Replace `test_rank_and_measure_aliases_map_to_the_recorded_metrics` and `test_strategy_instructions_list_every_metric_name` with:

```python
def test_rank_and_measure_aliases_map_to_the_recorded_metrics():
    from pilot.strategy import Pillar, Strategy, apply_aliases
    for alias, real in (("rank:military", "rank:military_power"), ("rank:economy", "rank:economy_power"),
                        ("rank:tech", "rank:tech_power"), ("military", "military_power"), ("techs", "techs_known"),
                        ("planets", "colonies")):
        s = Strategy(pillars={"economy": Pillar(priority=1, stance="s", milestones=[
            Milestone(metric=alias, op=">=", target=1, by="2200.01.01")])}, focus="f")
        m = apply_aliases(s, STELLARIS).pillars["economy"].milestones[0]
        assert m.metric == real and real in STELLARIS.metrics


def test_strategy_instructions_list_every_metric_name():
    from pilot.governor import STRATEGY_INSTRUCTIONS
    for m in STELLARIS.metrics:
        assert m in STRATEGY_INSTRUCTIONS, m
```
(`Milestone` is imported at the top of the first test: add `Milestone` to its `from pilot.strategy import …` line.)

- [ ] **Step 2: Run to verify they fail**

Run: `timeout 180 .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_strategy.py tests/test_governor.py -x`
Expected: FAIL — `ImportError: cannot import name 'apply_aliases' from 'pilot.strategy'`.

- [ ] **Step 3: Rewrite `src/pilot/strategy.py`**

```python
"""Pillar strategies: the governor's top-down frame (docs/design/2026-09-26-strategy-layer-design.md).

Game-agnostic: the pillars, directive mapping, metrics, aliases and action limits come from the
game's `PillarSpec` (pillars.py; docs/design/2026-09-26-game-pillars-design.md).
Pure data and rules; no model calls, no game input."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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
```

- [ ] **Step 4: Update the governor call sites** (`src/pilot/governor.py`)

Imports (replace line 30):

```python
from .pillars import PillarSpec, load_pillars
from .strategy import (
    Strategy,
    apply_aliases,
    keep_pinned,
    market_briefing_errors,
    milestone_status,
    pinned_misfits,
    ranking,
    validate,
)
```

`frame_text` (replace the function):

```python
def frame_text(strategy: Strategy | None, spec: PillarSpec, milestones: str) -> str:
    """The strategy frame shown to a decision: the pillar ranking (from the game's spec), focus,
    stances and any at-risk/missed milestones, replacing the old free-text campaign plan."""
    if strategy is None:
        return ""
    lines = ["STRATEGY FRAME (from the Strategist; choose within it):",
             f"Directive ranking: {' > '.join(ranking(strategy, spec))}", f"Focus: {strategy.focus}"]
    for name, pl in strategy.sorted_pillars():
        lines.append(f"{pl.priority}. {name}{' (pinned by the human)' if pl.pinned else ''}: {pl.stance}")
    at_risk = [m for m in milestones.splitlines() if m.endswith(("at_risk", "missed"))]
    if at_risk:
        lines.append("Milestones at risk or missed:\n" + "\n".join(at_risk))
    lines.append("Pick the highest-ranked directive that fits the briefing, or keep. Choose a directive outside "
                 "this ranking only for an urgent line (new war, deficit, crisis) and say so in the reason.")
    return "\n".join(lines)
```

`__init__`, directly after `self.journal = Journal(...)`:

```python
        self.pillars: PillarSpec = load_pillars(settings.corpus_dir)   # the game's strategy guardrails
```

`_decide`: `frame_text(self.strategy, self._milestones_text())` → `frame_text(self.strategy, self.pillars, self._milestones_text())`; `ranked = self.strategy.ranking() if self.strategy else []` → `ranked = ranking(self.strategy, self.pillars) if self.strategy else []`.

`edit_pillar`: replace the first lines and the build/validate lines:

```python
        from .strategy import Pillar
        if name not in self.pillars.pillars:
            raise ValueError(f"unknown pillar {name!r}")
```
and inside the lock:

```python
            s = apply_aliases(self.strategy.model_copy(update={"pillars": {**self.strategy.pillars, name: new},
                                                              "reason": trigger}), self.pillars)
            b = self._last_b
            if s.pillars[name].market and b is None:
                raise ValueError("no briefing yet: market orders can be edited after the first save is read")
            # briefing checks (idle, income share) for the edited pillar only: another pinned
            # pillar that no longer fits today's briefing must not block this edit; the milestone
            # rule is for model reviews, never for a human edit
            errs = validate(s, self.pillars, previous=None, tech_ids=self._tech_ids(), idle=idle_resources(b or {}),
                            income=(b or {}).get("net", {}), briefing_checked={name}, require_milestones=False)
```

`_carry_out_market_actions`: `errs = market_briefing_errors(o, idle, income)` → `errs = market_briefing_errors(o, self.pillars.actions["market"], idle, income)`.

`_milestones_text`: `milestone_status(m, rows, today)` → `milestone_status(m, rows, today, self.pillars.row_keys)`.
`_newly_missed_milestones`: both calls get `, self.pillars.row_keys` as the fourth argument.

`_review_strategy`: `pinned_misfits(self.strategy, idle=..., income=...)` → `pinned_misfits(self.strategy, self.pillars, idle=idle_resources(b), income=b.get("net") or {})`; and

```python
                new = keep_pinned(apply_aliases(r.strategy, self.pillars), self.strategy)
                errs = validate(new, self.pillars, previous=self.strategy, tech_ids=self._tech_ids(),
                                idle=idle_resources(b), income=b.get("net", {}))
```

- [ ] **Step 5: Dashboard milestone status uses the campaign's row keys** (`src/pilot/dashboard.py`)

Change the signature and add the helper right after `tel = …`:

```python
def make_app(pilot, runs_dir: Path | None = None, telemetry=None, corpora: Path | None = None) -> web.Application:
    """Dashboard for a live `pilot` (Pilot or Governor), or read-only over `runs_dir` when pilot is None.
    `corpora` is where each game's pillars file is read (default: the repo's corpora/)."""
    from .config import REPO
    log = pilot.log if pilot else None
    runs_dir = runs_dir or (log.dir.parent if log else Path("runs"))
    tel = telemetry or (log.telemetry if log else None)
    corpora = corpora or (REPO / "corpora")
    live_url = None                  # set for the viewer: finds a live run to refuse a second start

    def campaign_spec(cid: str):
        """The pillars spec of a campaign's game (id '<game>/<name>'), or None when the game has no
        valid pillars file. The live governor's own spec wins for its game."""
        from .pillars import PillarsError, load_pillars
        game = cid.split("/", 1)[0]
        live = getattr(pilot, "pillars", None)
        if live is not None and getattr(getattr(pilot, "s", None), "game", None) == game:
            return live
        if not re.fullmatch(r"[a-z0-9_]+", game):
            return None
        try:
            return load_pillars(corpora / game)
        except PillarsError:
            return None
```

In `api_strategy`, before the `for name, pl in s.pillars.items():` loop add `spec = campaign_spec(cid)` and `row_keys = spec.row_keys if spec else {}`, and call `milestone_status(m, rows, today, row_keys)`.

- [ ] **Step 6: Run the tests**

Run: `timeout 180 .venv/bin/python -m pytest -q -p no:cacheprovider`
Expected: PASS (all of `tests/test_strategy.py`, `tests/test_governor.py`, `tests/test_pillars.py`). Also `grep -nE "PILLARS|DIRECTIVE_OF|METRIC_ALIASES|MARKET_RESOURCES|\.ranking\(\)" src/pilot/*.py` prints nothing.

- [ ] **Step 7: Commit**

```bash
git add src/pilot/strategy.py src/pilot/governor.py src/pilot/dashboard.py tests/test_strategy.py tests/test_governor.py
scripts/ci-commit.sh "refactor(pilot): strategy rules driven by the game's pillars file" "validate, ranking, aliases, market checks, pinned misfits and milestone status take the PillarSpec; the Stellaris constants now live in corpora/stellaris/pillars.toml. Adds the min-milestones rule for the top pillars of a model review (pinned pillars and human edits exempt). Stellaris strategy tests pass with the same behaviour; fixtures carry milestones on the top three pillars."
```

---

### Task 3: Strategist output schema and prompt generated from the spec

**Files:**
- Modify: `src/pilot/strategy.py` (append `PillarOut`, `review_model`, `to_strategy`, `strategist_instructions`)
- Modify: `src/pilot/governor.py` (remove `StrategyReview` class and `STRATEGY_INSTRUCTIONS`; `_build`, `__init__`, `_review_strategy`)
- Test: `tests/test_strategy.py`, `tests/test_governor.py`

**Interfaces:**
- Consumes: `PillarSpec`, `ActionLimits` (Task 1); `Pillar`, `Strategy`, `MarketOrder`, `Milestone`, `apply_aliases` (Task 2).
- Produces (module `pilot.strategy`):
  - `class PillarOut(BaseModel)`: `priority: int`, `stance: str`, `goals: list[str] = []`, `milestones: list[Milestone] = []`; drops `pinned`/`edited_by` on input; `extra="forbid"`
  - `review_model(spec: PillarSpec) -> type[BaseModel]` — fields `change: bool`, `strategy: <StrategyOut> | None`, `assessment: str`, `rules: list[str]`; `StrategyOut` has one optional field per pillar id (type `PillarOut` subclass with `prefer_techs` / `market` only when that pillar declares `tech` / `market`), plus `focus: str`, `reason: str = ""`; accepts the stored shape `{"pillars": {...}}` too (lifted to named fields before validation)
  - `to_strategy(out: BaseModel, spec: PillarSpec) -> Strategy` (aliases applied)
  - `strategist_instructions(spec: PillarSpec) -> str`
  - governor: `Governor._review_type: type[BaseModel]`; the `strategy` role agent uses `output_type=self._review_type` and `instructions=strategist_instructions(self.pillars) + "\n\n" + text`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_strategy.py`:

```python
# ---- the Strategist's schema is generated from the spec -------------------------------------------

def _objects(node):
    if isinstance(node, dict):
        if node.get("type") == "object":
            yield node
        for v in node.values():
            yield from _objects(v)
    elif isinstance(node, list):
        for v in node:
            yield from _objects(v)


def _strategy_out_schema(schema: dict) -> dict:
    return next(d for d in schema["$defs"].values() if "focus" in d.get("properties", {}))


def test_the_review_schema_has_one_named_field_per_pillar():
    from pilot.strategy import review_model
    schema = review_model(SPEC).model_json_schema()
    out = _strategy_out_schema(schema)
    assert set(out["properties"]) == {*SPEC.ids, "focus", "reason"}
    assert "pillars" not in out["properties"]
    loose = [o for o in _objects(schema) if not o.get("properties") and o.get("additionalProperties") not in (None, False)]
    assert loose == [], "no object whose only shape is additionalProperties (Claude cannot fill those)"


def test_a_claude_style_answer_converts_to_a_valid_strategy():
    from pilot.strategy import review_model, to_strategy
    ms = [{"metric": "rank:military", "op": "<=", "target": 3, "by": "2250.01.01"}]
    answer = {"change": True, "assessment": "a", "rules": [], "strategy": {
        "defence": {"priority": 1, "stance": "hold", "goals": ["g"], "milestones": ms},
        "economy": {"priority": 2, "stance": "grow", "goals": ["g"], "milestones": ms,
                    "market": [{"side": "buy", "resource": "alloys", "amount": 5}]},
        "technology": {"priority": 3, "stance": "research", "goals": ["g"], "milestones": ms,
                       "prefer_techs": ["tech_habitat_1"]},
        "expansion": {"priority": 4, "stance": "s"}, "diplomacy": {"priority": 5, "stance": "s"},
        "government": {"priority": 6, "stance": "s"}, "society": {"priority": 7, "stance": "s"},
        "focus": "hold the line"}}
    r = review_model(SPEC).model_validate(answer)
    s = to_strategy(r.strategy, SPEC)
    assert s.pillars["defence"].milestones[0].metric == "rank:military_power", "aliases applied"
    assert s.pillars["economy"].market[0].resource == "alloys"
    assert validate(s, SPEC, previous=None, tech_ids={"tech_habitat_1"}, idle=set(), income={}) == []


def test_action_fields_exist_only_on_declaring_pillars():
    import pydantic

    from pilot.strategy import review_model
    schema = review_model(SPEC).model_json_schema()
    defs = schema["$defs"]
    out = _strategy_out_schema(schema)

    def pillar_props(pid):
        ref = next(x["$ref"] for x in out["properties"][pid]["anyOf"] if "$ref" in x)
        return set(defs[ref.rsplit("/", 1)[1]]["properties"])
    assert "market" in pillar_props("economy") and "prefer_techs" not in pillar_props("economy")
    assert "prefer_techs" in pillar_props("technology") and "market" not in pillar_props("technology")
    assert not {"market", "prefer_techs"} & pillar_props("diplomacy")
    with pytest.raises(pydantic.ValidationError):
        review_model(SPEC).model_validate({"change": True, "assessment": "a", "strategy": {
            "focus": "f", "diplomacy": {"priority": 1, "stance": "s", "prefer_techs": ["x"]}}})


def test_the_stored_shape_and_human_fields_are_accepted_as_input():
    from pilot.strategy import review_model, to_strategy
    legacy = {"change": True, "assessment": "a", "strategy": {"focus": "f", "reason": "r", "pillars": {
        "economy": {"priority": 1, "stance": "s", "pinned": True, "edited_by": "human"}}}}
    s = to_strategy(review_model(SPEC).model_validate(legacy).strategy, SPEC)
    assert set(s.pillars) == {"economy"} and s.pillars["economy"].pinned is False, "a model can never pin"


def test_the_prompt_comes_from_the_spec():
    from pilot.strategy import strategist_instructions
    text = strategist_instructions(SPEC)
    for pid, p in SPEC.pillars.items():
        assert f"- {pid} ({p.label}): {p.description}" in text
    for m in SPEC.metrics:
        assert m in text
    assert "Each of the 3 highest-priority pillars needs at least one milestone." in text
    assert "at most 1 small monthly order, amount 1-25" in text and "at most 20% of its monthly income" in text
    assert "Only technology: `prefer_techs` (tech ids to pick when offered; at most 6)." in text
    assert SPEC.actions["market"].note in text and SPEC.instructions in text
```
Add `import pytest` to the top imports of `tests/test_strategy.py`.

In `tests/test_governor.py`:

- `_strategist` returns named fields: replace its `body = …` line with

```python
        body = {"change": change, "assessment": "ok", "rules": [],
                "strategy": {**pillars, "focus": "grow", "reason": "start"} if change else None}
```

- Replace the three `STRATEGY_INSTRUCTIONS` tests (`test_strategy_instructions_cover_the_defence_naval_cap_ruling`, `test_strategy_instructions_forbid_trade_market_orders`, `test_strategy_instructions_allow_at_most_one_small_monthly_order`) and `test_strategy_instructions_list_every_metric_name` with:

```python
def test_strategy_instructions_cover_the_defence_naval_cap_ruling():
    from pilot.strategy import strategist_instructions
    text = strategist_instructions(STELLARIS)
    assert ("While at war, the defence stance must name its exit condition (peace, war exhaustion, "
            "or planets retaken).") in text
    assert ("When a hostile neighbour's military is twice ours or more, a defence goal is two "
            "shipyards in different systems and alloy production on two or more planets; never "
            "reason from a naval-capacity cap the briefing does not show.") in text


def test_strategy_instructions_forbid_trade_market_orders():
    from pilot.strategy import strategist_instructions
    assert ("Market orders cannot use trade; sell only idle energy, minerals, food, consumer goods "
            "or alloys (strategic resources can only be bought).") in strategist_instructions(STELLARIS)


def test_strategy_instructions_allow_at_most_one_small_monthly_order():
    from pilot.strategy import strategist_instructions
    text = strategist_instructions(STELLARIS)
    assert "at most 1 small monthly order" in text and "at most 2 small" not in text


def test_strategy_instructions_list_every_metric_name():
    from pilot.strategy import strategist_instructions
    for m in STELLARIS.metrics:
        assert m in strategist_instructions(STELLARIS), m
```

- Append:

```python
def test_a_named_field_review_is_accepted_with_its_milestones(setup):
    """Live 2026-09-26: Claude returned `pillars: {}` twice for a dict-typed schema. With one named
    field per pillar the answer is accepted and its milestones are kept."""
    s, log = setup
    calls, schemas = [], []
    inner = _strategist(calls)

    def respond(messages, info):
        schemas.append(info.output_tools[0].parameters_json_schema)
        return inner.function(messages, info)

    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"),
                 role_models={"strategy": FunctionModel(respond)})
    g._review_strategy(briefing("2200.01.01"), "start of run")
    out = next(d for d in schemas[0]["$defs"].values() if "focus" in d.get("properties", {}))
    assert set(STELLARIS.ids) <= set(out["properties"])
    assert g.strategy is not None and set(g.strategy.pillars) == set(STELLARIS.ids)
    assert g.strategy.pillars["defence"].milestones and g.strategy.pillars["technology"].milestones
    assert not any(e["kind"] == "strategy_rejected" for e in log.recent)
```

- [ ] **Step 2: Run to verify they fail**

Run: `timeout 180 .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_strategy.py tests/test_governor.py -k "schema or claude or action_fields or stored_shape or prompt_comes or instructions or named_field"`
Expected: FAIL — `ImportError: cannot import name 'review_model'` / `strategist_instructions`.

- [ ] **Step 3: Append the generator to `src/pilot/strategy.py`**

Add `create_model, model_validator` to the pydantic import (`from pydantic import BaseModel, ConfigDict, Field, create_model, model_validator`) and append:

```python
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
    return (list[MarketOrder], Field(default_factory=list,
                                     description=f"at most {a.max_items} monthly order(s), amount "
                                                 f"{a.amount_min}-{a.amount_max}; resources: {', '.join(a.resources)}"))


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
    lines = ["You are the Strategist: you set the top-down strategy. Write one entry per pillar, each under "
             "its own field named by the pillar id:"]
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
    if spec.instructions:
        lines.append(spec.instructions)
    return "\n".join(lines)
```

- [ ] **Step 4: Wire it into the governor** (`src/pilot/governor.py`)

- Delete the `StrategyReview` class and the `STRATEGY_INSTRUCTIONS` string.
- Add `review_model, strategist_instructions, to_strategy` to the `from .strategy import (...)` list.
- In `__init__`, right after `self.pillars = load_pillars(...)`: `self._review_type = review_model(self.pillars)`.
- In `_build`, the strategy branch:

```python
        if role == "strategy":
            return Agent(model, deps_type=GovDeps, output_type=self._review_type,
                         instructions=strategist_instructions(self.pillars) + "\n\n" + text,
                         tools=[Tool(f) for f in (consult, get_doc)], model_settings=governor_settings(settings), retries=2)
```

- In `_review_strategy`: `r: StrategyReview = result.output` → `r = result.output`; and

```python
            elif r.change and r.strategy is not None:
                new = keep_pinned(to_strategy(r.strategy, self.pillars), self.strategy)
```
(`apply_aliases` is no longer used in `_review_strategy`; it stays imported for `edit_pillar`.)

- [ ] **Step 5: Run to verify they pass**

Run: `timeout 180 .venv/bin/python -m pytest -q -p no:cacheprovider`
Expected: PASS. `grep -n "STRATEGY_INSTRUCTIONS\|class StrategyReview" src/pilot/*.py tests/*.py` prints nothing.

- [ ] **Step 6: Commit**

```bash
git add src/pilot/strategy.py src/pilot/governor.py tests/test_strategy.py tests/test_governor.py
scripts/ci-commit.sh "feat(pilot): Strategist schema and prompt generated from the game's pillars" "The Strategist's output has one named optional field per pillar (action fields only on pillars that declare them) instead of a dict, so Claude models see named properties; answers are converted to the stored Strategy with aliases applied, and the stored shape is still accepted. The prompt lists pillars, metrics and action limits from pillars.toml plus the game's own rules. Verified with schema, conversion and governor review tests."
```

---

### Task 4: Governor wiring — optional spec, stored-strategy check, action hooks, per-spec edits

**Files:**
- Modify: `src/pilot/governor.py` (`__init__`, `_start`, `_set_campaign`, `edit_pillar`, `request_review`, `_carry_out_actions`, `_carry_out_tech_actions`, `_carry_out_market_actions`, `_review_strategy`, `_tech_ids`; new `ACTION_METHODS`, `action_hooks`)
- Modify: `src/pilot/config.py` (`Settings.pillars_file`)
- Test: `tests/test_governor.py`

**Interfaces:**
- Consumes: `load_pillars`, `PillarsError`, `PillarSpec`, `ACTION_KINDS` (Task 1); `validate(..., require_milestones=False)`, `apply_aliases`, `ranking`, `market_briefing_errors(o, limits, idle, income)` (Task 2); `review_model`, `strategist_instructions`, `to_strategy` (Task 3).
- Produces:
  - `ACTION_METHODS: dict[str, str]` = `{"tech": "pick_tech", "market": "market_sync"}`; `action_hooks(game) -> dict[str, Callable]` (kinds whose method exists and is callable on `game`)
  - `Governor.pillars: PillarSpec | None`, `Governor.pillars_error: str` (empty when loaded)
  - event `strategy_disabled {error}` (once, at construction, when the file is missing or invalid)
  - event `strategy_action {action: <kind>, result: "not supported by this game; skipped"}` once per kind per governor
  - `log.state.info["pillars"]`: `PillarSpec.public()` or `None`
  - `Governor._GENERIC_FIELDS: ClassVar[set[str]]` = `{"stance", "goals", "milestones", "priority"}`; editable = generic − priority ∪ the pillar's declared action fields
  - `Settings.pillars_file -> Path` (`corpus_dir / "pillars.toml"`)

- [ ] **Step 1: Write the failing tests** (append to `tests/test_governor.py`)

```python
# ---- game pillars: governor wiring ----------------------------------------------------------------

def test_a_missing_pillars_file_turns_the_strategy_layer_off(setup):
    s, log = setup
    (s.corpus_dir / "pillars.toml").unlink()
    calls, seen = [], []

    def respond(messages, info):
        seen.append(" ".join(str(p.content) for m in messages for p in getattr(m, "parts", []) if hasattr(p, "content")))
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"directive": "expand", "reason": "r"})])

    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=FunctionModel(respond),
                 role_models={"strategy": _strategist(calls)})
    g.run(max_decisions=1)
    assert calls == [], "no Strategist call without a pillars file"
    assert g.pillars is None and "pillars.toml" in g.pillars_error
    off = [e for e in log.recent if e["kind"] == "strategy_disabled"]
    assert len(off) == 1 and "pillars.toml: missing" in off[0]["error"]
    assert any("No strategy yet." in t for t in seen)
    assert ("directive", "expand") in g.game.actions, "decisions run as before the layer"
    assert log.state.info["pillars"] is None
    with pytest.raises(ValueError, match="strategy layer is off"):
        g.edit_pillar("economy", {"stance": "x"})
    with pytest.raises(ValueError, match="strategy layer is off"):
        g.request_review()


def test_an_invalid_pillars_file_turns_the_layer_off_naming_the_key(setup):
    s, log = setup
    f = s.corpus_dir / "pillars.toml"
    f.write_text(f.read_text(encoding="utf-8").replace('label = "Society"', 'label = "Society"\ncolour = "red"'),
                 encoding="utf-8")
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"))
    off = [e for e in log.recent if e["kind"] == "strategy_disabled"]
    assert g.pillars is None and len(off) == 1 and "pillars.society.colour: unknown key" in off[0]["error"]


def test_a_stored_strategy_with_other_pillar_ids_is_treated_as_none(setup, tmp_path):
    from pilot.telemetry import Telemetry
    s, _ = setup
    tel = Telemetry(tmp_path / "t.sqlite")
    seed = EventLog(s.runs_dir, "seed", s.model, telemetry=tel)
    seed.emit("run_start", game="stellaris", model=s.model)
    seed.set_campaign("stellaris", "emp_z", "Empire Z")
    seed.emit("strategy", date="2199.01.01", trigger="start of run", model="seed", reason="seed",
              strategy={"pillars": {"navy": {"priority": 1, "stance": "s", "goals": []}}, "focus": "f"})
    calls = []
    log = EventLog(s.runs_dir, "run2", s.model, telemetry=tel)
    g = Governor(s, FakeStellaris([{**briefing("2200.01.01"), "source": "save games/emp_z/x.sav"}]), log,
                 model=decisions("keep"), role_models={"strategy": _strategist(calls)})
    g.run(max_decisions=1)
    assert calls and calls[0] == "strategist", "reviewed at start as if there were no strategy"
    assert set(g.strategy.pillars) == set(STELLARIS.ids)
    errs = [e for e in log.recent if e["kind"] == "briefing_error" and "do not match" in e.get("error", "")]
    assert errs and "navy" in errs[0]["error"] and "economy" in errs[0]["error"]


def test_a_declared_action_without_a_game_hook_is_skipped_once(setup):
    from pilot.strategy import Pillar
    s, log = setup

    class NoMarket(FakeStellaris):
        market_sync = None

    game = NoMarket([briefing("2200.01.01")])
    g = Governor(s, game, log, model=decisions("keep"))
    g.strategy = _strategy_with(
        technology=Pillar(priority=3, stance="s", goals=["g"], prefer_techs=["tech_habitat_1"]),
        economy=Pillar(priority=2, stance="s", goals=["g"], market=[{"side": "buy", "resource": "alloys", "amount": 5}]))
    g._carry_out_actions(_idle_energy("2200.01.01"))
    g._carry_out_actions(_idle_energy("2200.02.01"))
    unsupported = [e for e in log.recent if e["kind"] == "strategy_action" and "not supported" in e.get("result", "")]
    assert len(unsupported) == 1 and unsupported[0]["action"] == "market"
    assert ("pick_tech", ["tech_habitat_1"]) in game.actions, "the supported action still runs"
    assert log.state.status != "needs_attention"


def test_edit_pillar_fields_follow_the_pillars_file(setup):
    s, log = setup
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"))
    g.strategy = _strategy_with()
    g._last_b = _idle_energy("2200.01.01")
    with pytest.raises(ValueError, match="technology: only the economy pillar may set market"):
        g.edit_pillar("technology", {"market": [{"side": "buy", "resource": "alloys", "amount": 5}]})
    assert not g.strategy.pillars["technology"].pinned
    g.edit_pillar("economy", {"market": [{"side": "buy", "resource": "alloys", "amount": 5}]})
    assert g.strategy.pillars["economy"].market[0].resource == "alloys"
    g.edit_pillar("society", {"milestones": [{"metric": "planets", "op": ">=", "target": 5, "by": "2230.01.01"}]})
    assert g.strategy.pillars["society"].milestones[0].metric == "colonies", "aliases apply to human edits too"


def test_the_pillars_spec_is_published_for_the_dashboard(setup):
    s, log = setup
    Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"))
    assert [p["id"] for p in log.state.info["pillars"]["pillars"]] == list(STELLARIS.ids)
```

- [ ] **Step 2: Run to verify they fail**

Run: `timeout 180 .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_governor.py -k "pillars_file or stored_strategy_with_other or without_a_game_hook or follow_the_pillars or published_for_the_dashboard"`
Expected: FAIL — `PillarsError` raised from `Governor.__init__`; `KeyError: 'pillars'`; no "not supported" event.

- [ ] **Step 3: Implement**

`src/pilot/config.py`, after `corpus_dir`:

```python
    @property
    def pillars_file(self) -> Path:
        """The game's strategy pillars (docs/design/2026-09-26-game-pillars-design.md)."""
        return self.corpus_dir / "pillars.toml"
```

`src/pilot/governor.py`:

Imports: `from .pillars import ACTION_KINDS, PillarsError, PillarSpec, load_pillars`; add `from collections.abc import Callable`.

Module level, after `TECH_PICK_RE`:

```python
# Action kind -> the game method that carries it out. A game whose object lacks the method has no
# hook for that kind: a pillar declaring it is logged "not supported" once and skipped.
ACTION_METHODS = {"tech": "pick_tech", "market": "market_sync"}


def action_hooks(game) -> dict[str, Callable]:
    out = {}
    for kind, method in ACTION_METHODS.items():
        fn = getattr(game, method, None)
        if callable(fn):
            out[kind] = fn
    return out
```

`__init__`: replace `self.pillars: PillarSpec = load_pillars(...)` and `self._review_type = ...` with:

```python
        # the game's strategy guardrails; a missing or invalid file turns the strategy layer off
        # (decisions as before the layer) with one clear error naming the file and key
        self.pillars: PillarSpec | None = None
        self.pillars_error = ""
        try:
            self.pillars = load_pillars(settings.corpus_dir)
            self._review_type = review_model(self.pillars)
        except PillarsError as e:
            self.pillars_error = str(e)
            log.emit("strategy_disabled", error=self.pillars_error[:500])
        log.state.info["pillars"] = self.pillars.public() if self.pillars else None
        self._unsupported: set[str] = set()       # action kinds already logged as "not supported"
```

Add a helper method:

```python
    def _spec(self) -> PillarSpec:
        """The pillars spec, or ValueError (a 400 on the dashboard) while the strategy layer is off."""
        if self.pillars is None:
            raise ValueError(f"the strategy layer is off: {self.pillars_error}")
        return self.pillars
```

`_start`: `reviewed = self.strategy is None` → `reviewed = self.strategy is None and self.pillars is not None`.

`_set_campaign`, replace the strategy `try` body:

```python
            try:
                raw = self.log.telemetry.latest_strategy(self.log.campaign_id or "")
                stored = Strategy.model_validate(raw) if raw else None
                if stored is not None and (self.pillars is None or set(stored.pillars) != set(self.pillars.ids)):
                    if self.pillars is not None:
                        self.log.emit("briefing_error", error=(
                            f"stored strategy pillars {sorted(stored.pillars)} do not match "
                            f"{self.s.pillars_file.name} {list(self.pillars.ids)}; a review at start writes a new one")[:300])
                    stored = None
                self.strategy = stored
            except Exception as e:  # noqa: BLE001
                self.log.emit("briefing_error", error=f"loading the strategy: {e}"[:200])
```

`edit_pillar` (whole method):

```python
    _GENERIC_FIELDS: ClassVar[set[str]] = {"stance", "goals", "milestones", "priority"}

    def edit_pillar(self, name: str, fields: dict) -> None:
        """The human's edit: validated like a model strategy under the game's spec (against the last
        briefing this governor read: tech ids, idle resources and real monthly income), then pinned
        and recorded as a new version. Editable: stance, goals, milestones and the action fields the
        pillar declares in pillars.toml; `priority` is never editable (priorities stay unique). The
        milestone rule is for model reviews only. The read-modify-write is atomic (locked)."""
        from .strategy import Pillar
        spec = self._spec()
        if name not in spec.pillars:
            raise ValueError(f"unknown pillar {name!r}")
        if not isinstance(fields, dict):
            # ValueError, not TypeError: the dashboard's control() turns ValueError into a 400
            raise ValueError(f"fields must be an object, got {type(fields).__name__}")  # noqa: TRY004
        unknown = sorted(set(fields) - self._GENERIC_FIELDS - set(ACTION_KINDS.values()))
        if unknown:
            raise ValueError(f"unknown field(s): {', '.join(unknown)}")
        own = {spec.actions[k].field for k in spec.pillars[name].actions if k in spec.actions}
        for kind, fld in ACTION_KINDS.items():
            if fld in fields and fld not in own:
                owners = spec.owners(kind)
                raise ValueError(f"{name}: only the {' / '.join(owners)} pillar may set {fld}" if owners
                                 else f"{name}: {fld} is not an action in this game")
        editable = (self._GENERIC_FIELDS - {"priority"}) | own
        with self._strategy_lock:
            if self.strategy is None:
                raise ValueError("no strategy yet")
            cur = self.strategy.pillars[name].model_dump()
            new = Pillar.model_validate({**cur, **{k: v for k, v in fields.items() if k in editable},
                                         "pinned": True, "edited_by": "human"})
            trigger = f"edited by human: {name}"
            s = apply_aliases(self.strategy.model_copy(update={"pillars": {**self.strategy.pillars, name: new},
                                                              "reason": trigger}), spec)
            b = self._last_b
            if s.pillars[name].market and b is None:
                raise ValueError("no briefing yet: market orders can be edited after the first save is read")
            errs = validate(s, spec, previous=None, tech_ids=self._tech_ids(), idle=idle_resources(b or {}),
                            income=(b or {}).get("net", {}), briefing_checked={name}, require_milestones=False)
            if errs:
                raise ValueError("; ".join(errs))
            self.strategy = s
        self._publish_strategy(s, self.log.state.game_date or "", trigger, "human")
```
(Remove the old `_PILLAR_FIELDS` class attribute.)

`request_review`: first line `self._spec()` (raises while the layer is off).

`_review_strategy`: first statement of the method:

```python
        if self.pillars is None:
            self.log.emit("strategy_review_skipped", trigger=trigger, reason=f"strategy layer off: {self.pillars_error}"[:300])
            return
```

`_carry_out_actions`, `_carry_out_tech_actions`, `_carry_out_market_actions` (replace all three):

```python
    def _carry_out_actions(self, b: dict) -> None:
        """The strategy's player actions, per the game's spec: each action kind a pillar declares runs
        through the game's hook for it (ACTION_METHODS); a kind without a hook is logged "not
        supported" once and skipped. Each tool acts at most once per briefing date (the result stays
        stale until the next autosave). Nothing here ever raises out of this call, pauses the game,
        or undoes the decision already applied — any failure is logged as a strategy_action event."""
        if not self.strategy or self.pillars is None:
            return
        hooks = action_hooks(self.game)
        runners = {"tech": self._carry_out_tech_actions, "market": self._carry_out_market_actions}
        for kind in self.pillars.actions:
            if not self.pillars.owners(kind):
                continue
            hook = hooks.get(kind)
            if hook is None:
                if kind not in self._unsupported:
                    self._unsupported.add(kind)
                    self._log_action(kind, "not supported by this game; skipped")
                continue
            try:
                runners[kind](b, hook)
            except Exception as e:  # noqa: BLE001 - nothing here may stop play
                self._log_action("error", f"failed: {e}"[:300])

    def _declared(self, kind: str) -> list:
        """The items of action `kind` across the pillars that declare it, in priority order."""
        owners = set(self.pillars.owners(kind))
        fld = self.pillars.actions[kind].field
        return [x for name, pl in self.strategy.sorted_pillars() if name in owners for x in getattr(pl, fld)]

    def _carry_out_tech_actions(self, b: dict, pick_tech: Callable[[list[str]], str]) -> None:
        date = b.get("date")
        limit = self.pillars.actions["tech"].max_items
        prefer = [t for t in dict.fromkeys(self._declared("tech")) if self._tech_misses.get(t, 0) < 1][:limit]
        fields = (b.get("research") or {}).values()
        researching = {((r or {}).get("current") or [None])[0] for r in fields}
        offered = {t for r in fields for t in (r or {}).get("alternatives", [])}
        pending = None
        if self._pending_pick and date != self._tech_sync_date:   # judge a pick only on a later save
            pending, self._pending_pick = self._pending_pick, None
        if pending:
            if pending in researching:
                pass    # still being researched: stuck, nothing to verify yet
            elif pending in offered:
                # still offered but not picked up as current: the pick did not stick
                self._tech_misses[pending] = self._tech_misses.get(pending, 0) + 1
                self._log_action("tech", f"{pending} did not stick; skipped until the next review")
                prefer = [t for t in prefer if t != pending]
            else:
                # neither current nor offered any more: researched to completion
                self._log_action("tech", f"researched {pending}")
        if prefer and not researching & set(prefer) and date != self._tech_sync_date:
            self._tech_sync_date = date
            try:
                res = pick_tech(prefer)
                self._log_action("tech", res)
                m = TECH_PICK_RE.match(res)
                if m:
                    self._pending_pick = m.group(1)
            except Exception as e:  # noqa: BLE001 - actions never stop play
                self._log_action("tech", f"failed: {e}"[:300])

    def _carry_out_market_actions(self, b: dict, market_sync: Callable[[list[dict]], str]) -> None:
        date = b.get("date")
        current = b.get("market_orders") or []
        pending_market, later = self._pending_market, date != self._market_sync_date
        if pending_market is not None and later:
            self._pending_market = None
            if not self._same_orders(current, pending_market):
                self._log_action("market", f"market orders did not stick: wanted {pending_market}, save has {current}")
                self._market_stuck = True
        limits = self.pillars.actions["market"]
        idle, income = idle_resources(b), b.get("net") or {}
        desired = []
        for o in self._declared("market"):
            errs = market_briefing_errors(o, limits, idle, income)
            if errs:     # a sell that no longer fits today's briefing (e.g. a pinned or older order)
                if later:
                    self._log_action("market", f"skipped sell {o.resource}: {'; '.join(errs)}"[:300])
                continue
            desired.append(o.model_dump())
        if not self._market_stuck and not self._same_orders(desired, current) and later:
            self._market_sync_date = date
            try:
                res = market_sync(desired)
                self._log_action("market", res)
                self._pending_market = desired
            except Exception as e:  # noqa: BLE001 - actions never stop play
                self._log_action("market", f"failed: {e}"[:300])
```

`_tech_ids` — read the ids from the spec's source:

```python
    def _tech_ids(self) -> set[str]:
        """Ids for preferred techs, from `data/<ids_from_corpus>.json` of the corpus (the spec's tech
        action); cached once a read succeeds (a failed read is logged and retried, never cached)."""
        if getattr(self, "_techs", None) is not None:
            return self._techs
        tech = (self.pillars.actions.get("tech") if self.pillars else None)
        if tech is None or not tech.ids_from_corpus:
            return set()
        path = self.s.corpus_dir / "data" / f"{tech.ids_from_corpus}.json"
        try:
            techs = {r["id"].split(":", 1)[1] for r in json.loads(path.read_text(encoding="utf-8"))}
        except (OSError, ValueError, KeyError) as e:
            self.log.emit("briefing_error", error=f"tech ids: {e}"[:200])
            return set()
        self._techs = techs
        return techs
```

Guard the remaining `self.pillars` readers against `None`: in `_decide`, `frame_text(...)` only when `self.pillars` is set:

```python
                  (frame_text(self.strategy, self.pillars, self._milestones_text()) if self.pillars else "")
                  or "No strategy yet.",
```
and `ranked = ranking(self.strategy, self.pillars) if self.strategy and self.pillars else []`. In `_milestones_text` and `_newly_missed_milestones` the `self.strategy is None` early returns already cover it (strategy is always None while the layer is off).

- [ ] **Step 4: Run to verify they pass**

Run: `timeout 180 .venv/bin/python -m pytest -q -p no:cacheprovider`
Expected: PASS (new tests and every existing tech/market/edit test, e.g. `test_decisions_carry_out_the_strategy_actions`, `test_a_tech_that_did_not_stick_is_not_retried_until_the_next_review`, `test_market_orders_that_do_not_stick_wait_for_the_next_review`, `test_edit_pillar_rejects_an_invalid_edit_and_leaves_strategy_unchanged`).

- [ ] **Step 5: Commit**

```bash
git add src/pilot/governor.py src/pilot/config.py tests/test_governor.py
scripts/ci-commit.sh "feat(pilot): governor loads each game's pillars; actions through a hook table" "The governor loads corpora/<game>/pillars.toml; a missing or invalid file turns the strategy layer off with one strategy_disabled error naming the file and key, and decisions run as before the layer. A stored strategy whose pillar ids differ from the file is treated as none and reviewed at start. Actions run only for pillars that declare them, through the game's pick_tech/market_sync hooks; a kind without a hook is logged once as not supported. Human edits accept the pillar's declared action fields. Verified by governor tests."
```

---

### Task 5: Dashboard renders the Strategy tab from the spec

**Files:**
- Modify: `src/pilot/dashboard.py` (`api_strategy` returns `spec`; docstring line for `/api/strategy`)
- Modify: `src/pilot/static/dashboard.html` (strategy section ~576–722: remove `DIRECTIVE_OF`; `pillarCard`, `marketFieldsHtml`, `openEditForm`, `submitEdit`, `renderStrategy`)
- Test: `tests/test_governor.py` (API tests), headless check script in the scratchpad (not committed)

**Interfaces:**
- Consumes: `make_app(..., corpora=...)` and `campaign_spec(cid)` (Task 2); `PillarSpec.public()` (Task 1); `Governor.pillars` (Task 4).
- Produces: `GET /api/strategy?campaign=<id>` → `{"current", "milestones", "history", "spec"}` where `spec` is `PillarSpec.public()` for the campaign's game or `null`.
- JS: `specIndex(spec) -> {id: pillar}`, `pillarLabel(byId, id)`, `pillarCard(name, pl, ms, byId)`, `marketFieldsHtml(orders, limits)`, `openEditForm(name, pillar, byId, spec)`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_governor.py`)

```python
THREE_PILLARS = '''[strategy]
min_milestones_top = 1

[metrics]
names = ["systems", "pops"]

[pillars.faith]
label = "Faith"
description = "Religion and its spread."

[pillars.science]
label = "Science"
description = "Research output."

[pillars.culture]
label = "Culture"
description = "Great works and tourism."
'''


def test_strategy_api_serves_the_games_pillars(setup, tmp_path):
    import asyncio

    from aiohttp.test_utils import TestClient, TestServer

    from pilot.dashboard import make_app
    from pilot.telemetry import Telemetry
    s, _ = setup
    tel = Telemetry(tmp_path / "t.sqlite")
    log = EventLog(s.runs_dir, "rsp", s.model, telemetry=tel)
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"), role_models={"strategy": _strategist([])})
    log.emit("run_start", model=s.model, game=s.game)
    log.set_campaign("stellaris", "c9", "Test")
    g._review_strategy(briefing("2200.01.01"), "start of run")

    async def go():
        async with TestClient(TestServer(make_app(g, s.runs_dir, tel))) as c:
            body = await (await c.get(f"/api/strategy?campaign={log.campaign_id}")).json()
            assert [p["id"] for p in body["spec"]["pillars"]] == list(STELLARIS.ids)
            assert body["spec"]["actions"]["market"]["max_items"] == 1
    asyncio.run(go())


def test_strategy_api_serves_a_three_pillar_spec_in_the_viewer(tmp_path):
    import asyncio

    from aiohttp.test_utils import TestClient, TestServer

    from pilot.dashboard import make_app
    from pilot.telemetry import Telemetry
    corpora = tmp_path / "corpora"
    (corpora / "civtest").mkdir(parents=True)
    (corpora / "civtest" / "pillars.toml").write_text(THREE_PILLARS, encoding="utf-8")
    tel = Telemetry(tmp_path / "t.sqlite")
    log = EventLog(tmp_path / "runs", "r1", "test:model", telemetry=tel)
    log.emit("run_start", model="test:model", game="civtest")
    log.set_campaign("civtest", "c1", "Test civ")
    strategy = {"pillars": {p: {"priority": i + 1, "stance": f"{p} stance", "goals": ["g"]}
                            for i, p in enumerate(["science", "faith", "culture"])}, "focus": "pray"}
    log.emit("strategy", date="2200.01.01", trigger="start of run", model="seed", reason="seed", strategy=strategy)

    async def go():
        async with TestClient(TestServer(make_app(None, tmp_path / "runs", tel, corpora=corpora))) as c:
            body = await (await c.get("/api/strategy?campaign=civtest/c1")).json()
            assert [(p["id"], p["label"], p["directive"], p["actions"]) for p in body["spec"]["pillars"]] == [
                ("faith", "Faith", None, []), ("science", "Science", None, []), ("culture", "Culture", None, [])]
            assert body["current"]["focus"] == "pray"
            missing = await (await c.get("/api/strategy?campaign=nogame/c1")).json()
            assert missing["spec"] is None
    asyncio.run(go())


def test_dashboard_strategy_tab_reads_the_spec_not_a_copied_map():
    html = (REPO / "src/pilot/static/dashboard.html").read_text(encoding="utf-8")
    assert "DIRECTIVE_OF" not in html
    assert "data.spec" in html and "function specIndex(" in html
    assert 'name === "technology"' not in html and 'name === "economy"' not in html
```

- [ ] **Step 2: Run to verify they fail**

Run: `timeout 180 .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_governor.py -k "strategy_api_serves or reads_the_spec"`
Expected: FAIL — `KeyError: 'spec'`; `DIRECTIVE_OF` still in the page.

- [ ] **Step 3: API** (`src/pilot/dashboard.py`)

Docstring line: `GET  /api/strategy?campaign=<id>            current pillar strategy, milestone status, version history, the game's pillars spec`. `api_strategy`:

```python
    async def api_strategy(request):
        """The current pillar strategy, its milestones' status, version history and the game's
        pillars spec (labels, directives, actions) for a campaign."""
        from .strategy import Strategy, milestone_status
        cid = request.query.get("campaign") or (log.campaign_id if log else "")
        spec = campaign_spec(cid) if cid else None
        public = spec.public() if spec else None
        if tel is None or not cid:
            return web.json_response({"current": None, "milestones": [], "history": [], "spec": public})
        cur = await asyncio.to_thread(tel.latest_strategy, cid)
        rows = await asyncio.to_thread(tel.metrics_rows, cid)
        hist = await asyncio.to_thread(tel.strategy_history, cid)
        row_keys = spec.row_keys if spec else {}
        ms = []
        if cur:
            try:
                s = Strategy.model_validate({k: v for k, v in cur.items() if k != "reason"})
            except ValueError:
                s = None    # an older/foreign strategy shape: serve the raw record, no milestone status
            if s is not None:
                today = rows[-1]["date"] if rows else "2200.01.01"
                for name, pl in s.pillars.items():
                    for m in pl.milestones:
                        ms.append({"pillar": name, **m.model_dump(), "status": milestone_status(m, rows, today, row_keys)})
        return web.json_response({"current": cur, "milestones": ms, "history": hist, "spec": public})
```

- [ ] **Step 4: Strategy tab** (`src/pilot/static/dashboard.html`)

Replace the `DIRECTIVE_OF` comment and constant (lines ~577–580) with:

```js
// Pillar labels, directives and actions come from the game's pillars file (/api/strategy `spec`).
// Without a spec (an older campaign, or a game without one) pillars show their ids and no ranking.
function specIndex(spec) {
  const byId = {};
  ((spec && spec.pillars) || []).forEach((p) => { byId[p.id] = p; });
  return byId;
}
function pillarLabel(byId, id) { return (byId[id] && byId[id].label) || human(id); }
function pillarActions(byId, id) { return (byId[id] && byId[id].actions) || []; }
```

Replace `pillarCard`, `marketFieldsHtml`, `openEditForm` and `submitEdit`:

```js
function pillarCard(name, pl, ms, byId) {
  const def = byId[name] || {};
  const acts = pillarActions(byId, name);
  const goals = (pl.goals || []).map((g) => `<li>${esc(g)}</li>`).join("");
  const msRows = ms.map(milestoneRow).join("");
  const actions = [];
  if (acts.includes("tech") && (pl.prefer_techs || []).length) actions.push(`Prefers: ${esc(pl.prefer_techs.join(", "))}`);
  if (acts.includes("market")) (pl.market || []).forEach((o) => actions.push(`Market: ${esc(o.side)} ${esc(o.resource)} ${fmt(o.amount)}/month`));
  return `<article class="pillar" data-pillar="${esc(name)}">
    <div class="p-head"><h3 title="${esc(def.description || "")}">${esc(pillarLabel(byId, name))}</h3><span class="p-num">priority ${esc(pl.priority)}</span>
      ${pl.pinned ? `<span class="tag" title="Pinned by a human edit: a review will never change it">pinned</span>` : ""}</div>
    <p class="stance">${esc(pl.stance || "")}</p>
    ${goals ? `<ul class="goals">${goals}</ul>` : ""}
    ${msRows ? `<ul class="ms-list">${msRows}</ul>` : ""}
    ${actions.length ? `<div class="actions">${actions.map((a) => `<div>${a}</div>`).join("")}</div>` : ""}
    <div class="p-buttons"><button type="button" class="btn" data-edit="${esc(name)}">Edit</button>${pl.pinned ? `<button type="button" class="btn" data-unpin="${esc(name)}">Unpin</button>` : ""}</div>
    <div class="p-form-slot"></div>
  </article>`;
}

function marketFieldsHtml(orders, limits) {
  const n = Math.max(1, (limits && limits.max_items) || 1);
  const res = limits && (limits.resources || []).length ? `; resources: ${limits.resources.join(", ")}` : "";
  const range = limits && limits.amount_max ? `; amount ${limits.amount_min}–${limits.amount_max}` : "";
  const rows = Array.from({ length: n }, (_, i) => {
    const o = orders[i] || { side: "sell", resource: "", amount: "" };
    return `<div class="market-row">
      <select name="m${i}-side"><option value="sell"${o.side === "sell" ? " selected" : ""}>sell</option><option value="buy"${o.side === "buy" ? " selected" : ""}>buy</option></select>
      <input name="m${i}-resource" placeholder="resource" value="${esc(o.resource || "")}">
      <input name="m${i}-amount" type="number" min="1" placeholder="amount / month" value="${esc(o.amount ?? "")}"></div>`;
  }).join("");
  return `<div class="market-fields"><span>Market orders (up to ${n}${esc(range)}${esc(res)})</span>${rows}</div>`;
}

function openEditForm(name, pillar, byId, spec) {
  const art = $("strategy").querySelector(`article[data-pillar="${CSS.escape(name)}"]`);
  if (!art) return;
  const acts = pillarActions(byId, name);
  const limits = (spec && spec.actions) || {};
  const slot = art.querySelector(".p-form-slot");
  slot.innerHTML = `<form class="p-form">
    <label>Stance<textarea name="stance">${esc(pillar.stance || "")}</textarea></label>
    <label>Goals (one per line, up to 3)<textarea name="goals">${esc((pillar.goals || []).join("\n"))}</textarea></label>
    ${acts.includes("tech") ? `<label>Prefer techs (comma list, up to ${esc((limits.tech || {}).max_items || "")})<input name="prefer_techs" value="${esc((pillar.prefer_techs || []).join(", "))}"></label>` : ""}
    ${acts.includes("market") ? marketFieldsHtml(pillar.market || [], limits.market) : ""}
    <p class="p-error" hidden></p>
    <div class="row"><button type="submit" class="btn primary">Save</button><button type="button" class="btn" data-cancel>Cancel</button></div>
  </form>`;
  const editBtn = art.querySelector(`[data-edit]`), unpinBtn = art.querySelector(`[data-unpin]`);
  editBtn.hidden = true; if (unpinBtn) unpinBtn.hidden = true;
  const close = () => { slot.innerHTML = ""; editBtn.hidden = false; if (unpinBtn) unpinBtn.hidden = false; };
  slot.querySelector("[data-cancel]").addEventListener("click", close);
  slot.querySelector("form").addEventListener("submit", (e) => { e.preventDefault(); submitEdit(name, slot, close); });
}

async function submitEdit(name, slot, onSaved) {
  const form = slot.querySelector("form");
  const fields = { stance: form["stance"].value, goals: form["goals"].value.split("\n").map((s) => s.trim()).filter(Boolean).slice(0, 3) };
  if (form["prefer_techs"]) fields.prefer_techs = form["prefer_techs"].value.split(",").map((s) => s.trim()).filter(Boolean);
  const rows = form.querySelectorAll(".market-row").length;
  if (rows) {
    const market = [];
    for (let i = 0; i < rows; i++) {
      const res = form[`m${i}-resource`].value.trim();
      if (res) market.push({ side: form[`m${i}-side`].value, resource: res, amount: +form[`m${i}-amount`].value || 0 });
    }
    fields.market = market;
  }
  const btn = form.querySelector('button[type="submit"]');
  btn.disabled = true;
  let r;
  try {
    r = await fetch("/control", { method: "POST", headers: { "Content-Type": "application/json" },
                                  body: JSON.stringify({ action: "edit_pillar", pillar: name, fields }) });
  } catch (e) {
    const err = slot.querySelector(".p-error"); err.textContent = "Could not reach the server: " + e.message; err.hidden = false; btn.disabled = false;
    return;
  }
  if (!r.ok) {
    const err = slot.querySelector(".p-error");
    err.textContent = (await r.text()) || "The edit was rejected.";
    err.hidden = false;
    btn.disabled = false;
    return;         // Ruling: show the server's reason inline, keep the form open
  }
  toast(`${human(name)}: edit saved and pinned.`);
  onSaved();
  loadStatus();
}
```

In `renderStrategy`, replace the `ranking` line, the card line and the two wiring lines:

```js
  const spec = data.spec || null, byId = specIndex(spec);
  const pillars = Object.entries(cur.pillars || {}).sort((a, b) => (a[1].priority || 0) - (b[1].priority || 0));
  const ranking = pillars.map(([name]) => byId[name] && byId[name].directive).filter(Boolean).map(human).join(", ");
```
```js
  h += pillars.map(([name, pl]) => pillarCard(name, pl, msByPillar[name] || [], byId)).join("");
```
```js
  box.querySelectorAll("[data-edit]").forEach((b) => b.addEventListener("click", () => openEditForm(b.dataset.edit, cur.pillars[b.dataset.edit], byId, spec)));
  box.querySelectorAll("[data-unpin]").forEach((b) => b.addEventListener("click", () => {
    if (confirm(`Unpin ${pillarLabel(byId, b.dataset.unpin)}? A future review may change it again.`)) control({ action: "unpin_pillar", pillar: b.dataset.unpin });
  }));
```

- [ ] **Step 5: Run the tests**

Run: `timeout 180 .venv/bin/python -m pytest -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 6: Headless check (3 pillars, no directives; not committed)**

Write `$SCRATCH/pillars_headless.py` (`$SCRATCH` = this session's scratchpad directory) and run it with `.venv/bin/python $SCRATCH/pillars_headless.py $SCRATCH`:

```python
import asyncio
import json
import sys
import tempfile
from pathlib import Path

from aiohttp import web
from playwright.async_api import async_playwright

from pilot.dashboard import make_app
from pilot.events import EventLog
from pilot.telemetry import Telemetry

THREE = """[strategy]
min_milestones_top = 1

[metrics]
names = ["systems", "pops"]

[pillars.faith]
label = "Faith"
description = "Religion and its spread."

[pillars.science]
label = "Science"
description = "Research output."

[pillars.culture]
label = "Culture"
description = "Great works and tourism."
"""
MODELS = {"models": [], "model": "test:model", "thinking": "medium", "game": "civtest", "fallback": "none",
          "providers": [], "pool": [], "rotate": False, "roles": {}, "role_meta": [], "speed": "normal", "months": 12}


async def main(out: Path) -> None:
    tmp = Path(tempfile.mkdtemp())
    corpora = tmp / "corpora"
    (corpora / "civtest").mkdir(parents=True)
    (corpora / "civtest" / "pillars.toml").write_text(THREE, encoding="utf-8")
    tel = Telemetry(tmp / "t.sqlite")
    log = EventLog(tmp / "runs", "r1", "test:model", telemetry=tel)
    log.emit("run_start", model="test:model", game="civtest")
    log.set_campaign("civtest", "c1", "Test civ")
    ms = [{"metric": "systems", "op": ">=", "target": 5, "by": "2250.01.01"}]
    strategy = {"pillars": {p: {"priority": i + 1, "stance": f"{p} stance", "goals": ["g"], "milestones": ms}
                            for i, p in enumerate(["faith", "science", "culture"])}, "focus": "pray", "reason": "seed"}
    log.emit("strategy", date="2200.01.01", trigger="start of run", model="seed", reason="seed", strategy=strategy)
    runner = web.AppRunner(make_app(None, tmp / "runs", tel, corpora=corpora))
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", 8799).start()
    errors: list[str] = []
    async with async_playwright() as p:
        b = await p.chromium.launch()
        page = await b.new_page()
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        await page.route("**/api/pc", lambda r: r.fulfill(status=200, content_type="application/json", body='{"online": false}'))
        await page.route("**/api/models", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(MODELS)))
        await page.goto("http://127.0.0.1:8799/")
        await page.click('.tabs [data-tab="strategy"]')
        await page.wait_for_selector("#strategy article.pillar")
        labels = await page.locator("#strategy article.pillar h3").all_inner_texts()
        head = await page.locator("#strategy .strategy-head").inner_text()
        await page.click('#strategy [data-edit="science"]')
        form_inputs = await page.locator("#strategy .p-form input").count()
        await page.screenshot(path=str(out / "pillars-3.png"), full_page=True)
        await b.close()
    await runner.cleanup()
    print("labels:", labels, "| head:", head.replace("\n", " "), "| inputs:", form_inputs, "| errors:", errors)
    assert labels == ["Faith", "Science", "Culture"], labels
    assert "Ranking: –" in head, head
    assert form_inputs == 0, "no action fields on pillars without actions"
    assert not errors, errors
    print("HEADLESS OK")


asyncio.run(main(Path(sys.argv[1])))
```
Expected output ends with `HEADLESS OK`; open `$SCRATCH/pillars-3.png` and confirm three cards in priority order (Faith, Science, Culture) with milestone rows. Then run it once more against the Stellaris campaign on the running viewer (`http://127.0.0.1:8780/` after Task 7's deploy) by eye: seven labelled cards, the ranking line, and one market row in the Economy edit form.

- [ ] **Step 7: Commit**

```bash
git add src/pilot/dashboard.py src/pilot/static/dashboard.html tests/test_governor.py
scripts/ci-commit.sh "feat(dashboard): Strategy tab renders from the game's pillars spec" "/api/strategy returns the campaign's pillars spec; the Strategy tab takes pillar labels, the directive ranking and the edit fields per declared action from it (the copied directive map is gone, and the market form shows the file's order limit). Verified by API tests and a headless render of a three-pillar spec without directives, no console errors."
```

---

### Task 6: Second-game end-to-end test and Rust/Python limit equality

**Files:**
- Create: `tests/test_game_pillars.py`
- Modify: `tests/test_strategy.py` (`test_python_market_amount_limits_equal_the_controllers` → the full equality test)

**Interfaces:**
- Consumes: everything above — `load_pillars`, `Governor` (`pillars`, `strategy`, `review_requested`, `run`), `ranking`, `validate`, `review_model`, `FakeStellaris`, the `strategy_action` / `trace` events.
- Produces: tests only.

- [ ] **Step 1: Write the tests**

```python
# tests/test_game_pillars.py
"""A second, synthetic game (3 pillars, no actions) runs the strategy layer end to end: the
Strategist's schema, validation, the ranking, the frame and the off-frame check all follow its
pillars file, with no strategy-code change (spec 2026-09-26-game-pillars-design.md §5)."""

import shutil

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from pilot.config import REPO, Settings
from pilot.events import EventLog
from pilot.game import FakeStellaris
from pilot.governor import Governor
from pilot.pillars import load_pillars
from pilot.strategy import Milestone, Pillar, Strategy, ranking, review_model, validate

SYNTH = """[strategy]
min_milestones_top = 1
metric_aliases = { planets = "colonies" }
instructions = "Grow tall: few cities, each great."

[metrics]
names = ["colonies", "pops", "techs_known"]
row_keys = { colonies = "planets" }

[pillars.science]
label = "Science"
description = "Research output and great scientists."
directive = "tech_rush"

[pillars.growth]
label = "Growth"
description = "New cities and population."
directive = "expand"

[pillars.culture]
label = "Culture"
description = "Great works and tourism."
"""


def briefing(date: str) -> dict:
    return {"date": date, "net": {"energy": 5.0}, "wars": [], "flags": []}


@pytest.fixture
def synth(tmp_path):
    corpus = tmp_path / "synth"
    corpus.mkdir()
    for f in ("pilot.md", "strategy.md", "directives.toml"):
        shutil.copy(REPO / "corpora/stellaris" / f, corpus / f)
    (corpus / "pillars.toml").write_text(SYNTH, encoding="utf-8")
    s = Settings(model="google:gemini-3.8-flash", runs_dir=tmp_path / "runs", journal=tmp_path / "journal.md",
                 commit_learnings=False, game="synth", speed="fastest", decide_every_months=12, poll_s=0,
                 ask_human_timeout_s=0.05, fallback_model=None)      # tests never reach a real provider
    s.__class__ = type("S", (Settings,), {"corpus_dir": property(lambda self: corpus)})
    return s, EventLog(s.runs_dir, "synth1", s.model), load_pillars(corpus)


def _strategist(schemas: list):
    def respond(messages, info: AgentInfo) -> ModelResponse:
        schemas.append(info.output_tools[0].parameters_json_schema)
        body = {"change": True, "assessment": "ok", "rules": [], "strategy": {
            "science": {"priority": 1, "stance": "research first", "goals": ["g"],
                        "milestones": [{"metric": "planets", "op": ">=", "target": 6, "by": "2230.01.01"}]},
            "growth": {"priority": 2, "stance": "settle", "goals": ["g"]},
            "culture": {"priority": 3, "stance": "later"},
            "focus": "tall", "reason": "start"}}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, body)])
    return FunctionModel(respond)


def _decider(prompts: list, choices: list[str]):
    n = {"i": 0}

    def respond(messages, info: AgentInfo) -> ModelResponse:
        prompts.append(" ".join(str(p.content) for m in messages for p in getattr(m, "parts", []) if hasattr(p, "content")))
        c = choices[min(n["i"], len(choices) - 1)]
        n["i"] += 1
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"directive": c, "reason": f"test chose {c}"})])
    return FunctionModel(respond)


def test_a_synthetic_game_runs_review_and_decisions_on_its_own_pillars(synth):
    s, log, spec = synth
    schemas, prompts = [], []
    game = FakeStellaris([briefing("2200.01.01"), briefing("2201.01.01")])
    g = Governor(s, game, log, model=_decider(prompts, ["keep", "defend"]), role_models={"strategy": _strategist(schemas)})
    g.run(max_decisions=2)

    out = next(d for d in schemas[0]["$defs"].values() if "focus" in d.get("properties", {}))
    assert set(out["properties"]) == {"science", "growth", "culture", "focus", "reason"}
    assert set(g.strategy.pillars) == {"science", "growth", "culture"}
    assert g.strategy.pillars["science"].milestones[0].metric == "colonies", "the synthetic game's alias"
    assert ranking(g.strategy, spec) == ["tech_rush", "expand"]
    assert "Directive ranking: tech_rush > expand" in prompts[0]
    traces = [e for e in log.recent if e["kind"] == "trace" and e.get("decision") == "defend"]
    assert traces and traces[-1].get("off_frame") is True, "defend is outside this game's ranking"
    assert g.review_requested and "off-frame" in g.review_requested
    assert not any(a[0] in ("pick_tech", "market_sync") for a in game.actions), "no actions declared"
    assert not any(e["kind"] == "strategy_action" for e in log.recent)


def test_the_synthetic_strategist_prompt_and_schema_carry_no_stellaris_pillars(synth):
    s, log, spec = synth
    from pilot.strategy import strategist_instructions
    text = strategist_instructions(spec)
    assert "- science (Science): Research output and great scientists. [ranks the directive tech_rush]" in text
    assert "economy" not in text and "prefer_techs" not in text and "market" not in text
    assert "Grow tall: few cities, each great." in text
    schema = review_model(spec).model_json_schema()
    assert "prefer_techs" not in str(schema) and "market" not in str(schema)


def test_validation_follows_the_synthetic_spec(synth):
    _, _, spec = synth
    ms = [Milestone(metric="pops", op=">=", target=5, by="2230.01.01")]
    ok = Strategy(pillars={"science": Pillar(priority=1, stance="s", goals=["g"], milestones=ms),
                           "growth": Pillar(priority=2, stance="s"), "culture": Pillar(priority=3, stance="s")}, focus="f")
    assert validate(ok, spec, previous=None, tech_ids=set(), idle=set(), income={}) == []
    stellaris_shaped = Strategy(pillars={"economy": Pillar(priority=1, stance="s", milestones=ms)}, focus="f")
    errs = " | ".join(validate(stellaris_shaped, spec, previous=None, tech_ids=set(), idle=set(), income={}))
    assert "unknown pillar 'economy'" in errs and "missing pillar science" in errs
    bad = ok.model_copy(update={"pillars": {**ok.pillars, "culture": Pillar(
        priority=4, stance="s", milestones=[Milestone(metric="systems", op=">=", target=1, by="2230.01.01")],
        prefer_techs=["x"])}})
    errs = " | ".join(validate(bad, spec, previous=None, tech_ids=set(), idle=set(), income={}))
    assert "culture: priority must be 1..3" in errs
    assert "culture: unknown metric 'systems'" in errs
    assert "culture: prefer_techs is not an action in this game" in errs
    no_ms = ok.model_copy(update={"pillars": {**ok.pillars, "science": Pillar(priority=1, stance="s")}})
    assert "science: priority 1 is in the top 1 and needs at least one milestone" in \
        validate(no_ms, spec, previous=None, tech_ids=set(), idle=set(), income={})
```

Replace `test_python_market_amount_limits_equal_the_controllers` in `tests/test_strategy.py` with:

```python
def test_the_stellaris_pillars_file_limits_equal_the_controllers():
    """Rust keeps its own tool validation (mcp.rs); the pillars file must never plan what the tools refuse."""
    src = (REPO / "crates/game-controller/src/mcp.rs").read_text(encoding="utf-8")
    lo = re.search(r"const MARKET_AMOUNT_MIN: i64 = (\d+);", src)
    hi = re.search(r"const MARKET_AMOUNT_MAX: i64 = (\d+);", src)
    assert lo and hi, "mcp.rs declares its market amount limits as constants"
    market, tech = SPEC.actions["market"], SPEC.actions["tech"]
    assert (market.amount_min, market.amount_max) == (int(lo.group(1)), int(hi.group(1)))
    body = src[src.index("fn validate_market_orders"):]
    body = body[:body.index("\n}\n")]
    assert "MARKET_AMOUNT_MIN..=MARKET_AMOUNT_MAX" in body, "validate_market_orders uses those constants"
    orders = re.search(r"orders\.len\(\) > (\d+)", body)
    assert orders and market.max_items <= int(orders.group(1)), "never more orders than stellaris_market_sync takes"
    techs = re.search(r"prefer\.len\(\) > (\d+)", src)
    assert techs and tech.max_items == int(techs.group(1)), "prefer_techs limit equals stellaris_pick_tech's"
    manifest = tomllib.loads((REPO / "corpora/stellaris/manifest.toml").read_text(encoding="utf-8"))
    assert set(market.resources) == set(manifest["ui"]["market"]["resources"]) and "trade" not in market.resources
```

- [ ] **Step 2: Run them**

Run: `timeout 180 .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_game_pillars.py tests/test_strategy.py`
Expected: PASS (these pin behaviour built in Tasks 1–5). To see each guard bite once, temporarily set `max_items = 7` under `[actions.tech]` in `corpora/stellaris/pillars.toml` → `test_the_stellaris_pillars_file_limits_equal_the_controllers` FAILS; restore it (`git checkout corpora/stellaris/pillars.toml`) → PASS. Likewise temporarily put `directive = "defend"` on `culture` in `SYNTH` → the off-frame assertion FAILS; restore.

- [ ] **Step 3: Full suite**

Run: `timeout 180 .venv/bin/python -m pytest -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_game_pillars.py tests/test_strategy.py
scripts/ci-commit.sh "test(pilot): a synthetic second game runs the strategy layer on its own pillars" "A three-pillar game with no actions reviews, ranks, frames and flags off-frame decisions from its own pillars file with no strategy-code change; validation rejects Stellaris pillars and metrics there. The Stellaris pillars file's market amounts, order count and tech limit are pinned to the controller's mcp.rs checks."
```

---

### Task 7: Docs, deploy and live check

**Files:**
- Modify: `README.md` (Strategy layer paragraph, ~line 298), `ARCHITECTURE.md` (Strategy layer bullet, ~line 293), `AGENTS.md` (§10 Strategy layer bullet, ~line 253), `corpora/stellaris/pilot.md` (Decision rules, first bullet ~line 54), `plan.md` (line 131), `issues.md` (Open list)

**Interfaces:**
- Consumes: the deployed behaviour of Tasks 1–6.
- Produces: docs; the running `game-pilot-view.service` and `game-pilot.service` on the new code.

- [ ] **Step 1: Update the docs**

`README.md` — at the start of the **Strategy layer** paragraph, after "keeps one strategy per campaign:", replace "seven pillars with a" with "the game's pillars from `corpora/<game>/pillars.toml` (Stellaris: seven) with a", and append this sentence at the end of the paragraph:

```markdown
Each game defines its pillars in `corpora/<game>/pillars.toml`: labels and descriptions, the directive a
pillar ranks, the metrics milestones may use (and model spellings of them), which pillar carries which
action, the action limits, and how many top pillars need a milestone (Stellaris: 3). The Strategist's
answer has one named field per pillar; a missing or invalid file turns the strategy layer off with one
`strategy_disabled` error naming the file and key. Adding a game's strategy layer = that file plus the
game's action tools.
```

`ARCHITECTURE.md` — replace the first two lines of the Strategy layer bullet ("`strategy.py` is pure (Pillar, Milestone, MarketOrder, Strategy with `ranking()`; `validate` —") with:

```markdown
- Strategy layer: `pillars.py` loads `corpora/<game>/pillars.toml` into a `PillarSpec` (pillars,
  directives checked against `directives.toml`, metrics and aliases, action limits; unknown keys fail
  naming the key; cached per corpus). `strategy.py` is pure and game-agnostic (Pillar, Milestone,
  MarketOrder, Strategy; `ranking(s, spec)`; `review_model(spec)` generates the Strategist's output with
  one named field per pillar and `to_strategy` converts it; `strategist_instructions(spec)`; `validate(s, spec, …)` —
```
and in the same bullet replace "`_carry_out_actions` (once per save date, verified in a later save)" with "`_carry_out_actions` (per declared action kind through `action_hooks(game)` — `pick_tech`, `market_sync`; a kind without a hook is logged once as not supported; once per save date, verified in a later save)", and "dashboard `/api/strategy`" with "dashboard `/api/strategy` (with the campaign's `spec`, from which the Strategy tab renders labels, ranking and edit fields)".

`AGENTS.md` §10 — replace the first sentence of the **Strategy layer** bullet with:

```markdown
- **Strategy layer**: the governor keeps a pillar strategy (role `strategy`) that ranks the
  directives; decisions choose within it. The pillars, their directives, milestone metrics and action
  limits are in `corpora/stellaris/pillars.toml` (edit that file, not Python, to change them; a test
  keeps its market and tech limits equal to `mcp.rs`).
```
(keep the rest of the bullet — the two actions' screen notes — unchanged).

`corpora/stellaris/pilot.md` — in the first Decision-rules bullet, after "set by the Strategist." insert: "The pillars and the directive each one ranks are defined in `pillars.toml`."

`issues.md` — add under `## Open`:

```markdown
- [ ] Claude models returned `pillars: {}` for the Strategist (a dict-typed schema has no named fields) and the accepted strategy had no milestones (2026-09-26; fixed by game pillars: named field per pillar, top-3 milestone rule; flip after the live check)
```

- [ ] **Step 2: Full verification**

Run: `scripts/ci.sh`
Expected: last line `CI OK`.

- [ ] **Step 3: Commit the docs**

```bash
git add README.md ARCHITECTURE.md AGENTS.md corpora/stellaris/pilot.md issues.md
scripts/ci-commit.sh "docs: game pillars file drives the strategy layer" "README, ARCHITECTURE, AGENTS §10 and the Stellaris pilot briefing describe corpora/<game>/pillars.toml, the generated Strategist schema, the action hook table and the dashboard's spec; issues.md records the empty-pillars and missing-milestones problems this fixes."
git push
```

- [ ] **Step 4: Deploy**

Check first (the PC is the user's desktop): the dashboard at `http://192.168.1.76:8780/` shows the Theian campaign as the live one and Stellaris in the foreground (`./target/release/game-controller health`). Then:

```bash
systemctl --user restart game-pilot-view.service
systemctl --user restart game-pilot.service
sleep 60; systemctl --user --no-pager status game-pilot.service game-pilot-view.service | head -20
curl -s "http://127.0.0.1:8780/api/strategy?campaign=$(curl -s http://127.0.0.1:8780/status | .venv/bin/python -c 'import json,sys; print(json.load(sys.stdin)["info"]["campaign"])')" \
  | .venv/bin/python -c 'import json,sys; b=json.load(sys.stdin); print([p["id"] for p in b["spec"]["pillars"]])'
```
Expected: both services `active (running)`; the last line prints the seven Stellaris pillar ids; no `strategy_disabled` event in the activity feed.

- [ ] **Step 5: Live check — a review with Claude and one with Gemini**

```bash
M=$(curl -s http://127.0.0.1:8780/api/models)
CLAUDE=$(printf '%s' "$M" | .venv/bin/python -c 'import json,sys; print(next(m for m in json.load(sys.stdin)["models"] if m.startswith("anthropic:")))')
GEMINI=$(printf '%s' "$M" | .venv/bin/python -c 'import json,sys; print(next(m for m in json.load(sys.stdin)["models"] if m.startswith("google:")))')
review() {
  curl -s -X POST http://127.0.0.1:8780/control -H 'Content-Type: application/json' \
    -d "{\"action\":\"set_roles\",\"roles\":{\"strategy\":{\"models\":[{\"model\":\"$1\",\"thinking\":\"medium\"}],\"rotate\":false}}}"
  curl -s -X POST http://127.0.0.1:8780/control -H 'Content-Type: application/json' -d '{"action":"review_strategy"}'
}
check() {
  .venv/bin/python - <<'EOF'
import json, sqlite3
db = sqlite3.connect("runs/telemetry.sqlite")
ev = json.loads(db.execute("SELECT data FROM events WHERE kind='strategy_review' ORDER BY t DESC LIMIT 1").fetchone()[0])
st = json.loads(db.execute("SELECT data FROM strategies ORDER BY t DESC LIMIT 1").fetchone()[0])
top = sorted(st["pillars"].items(), key=lambda kv: kv[1]["priority"])[:3]
print("model:", ev.get("model"), "| accepted:", ev.get("accepted"), "| change:", ev.get("change"))
print("top-3 milestones:", {k: len(v.get("milestones", [])) for k, v in top})
EOF
}
review "$CLAUDE"   # wait until the activity feed shows the strategy_review (the game pauses for it), then:
check
review "$GEMINI"
check
```
Expected, for each: `accepted: True` (or `change: False` with the current strategy already carrying milestones on its top three), and every top-3 pillar with ≥ 1 milestone. If Claude's review is rejected, read its trace (`/api/decision?run=<run>&episode=<negative n>`) and fix before continuing. Afterwards restore the strategy role the user had (`/api/models` → `roles` before the change; post it back with `set_roles`).

- [ ] **Step 6: Record and flip**

In `plan.md` line 131 change `- [ ] Game pillars:` to `- [x] Game pillars:` and append `; deployed <short sha>, reviews accepted live with Claude and Gemini`. In `issues.md` flip the new entry to `- [x]` with `(deployed <short sha>; live reviews with <CLAUDE> and <GEMINI> accepted with milestones)`. Add a dated line to `games/stellaris/journal.md` with the two review results.

```bash
git add plan.md issues.md games/stellaris/journal.md
scripts/ci-commit.sh "docs: game pillars deployed and checked live" "Services restarted on the game-pillars code; strategy reviews with Claude and Gemini were accepted on the Theian campaign with milestones on the top three pillars."
git push
```

---

## Self-review notes

- Spec coverage: §1 file format and fail-fast → Task 1; §2 loader/Settings → Tasks 1, 4 (`Settings.pillars_file`); game-agnostic `strategy.py` → Task 2; generated schema + prompt → Task 3; min milestones → Task 2; decisions frame/off-frame from `ranking(s, spec)` → Task 2 (wiring), Task 6 (synthetic proof); action hook table + "not supported once" → Task 4; human edits per declared fields → Task 4; dashboard spec + no `DIRECTIVE_OF` + edit fields per action → Task 5; Rust equality → Tasks 2 and 6; §3 migration (same ids, mismatch = no strategy) → Tasks 1, 4; §4 missing/invalid file → Task 4; §5 tests → Tasks 1, 3, 4, 5, 6; live → Task 7.
- Deliberate behaviour choices the spec leaves open: the milestone rule exempts pinned pillars and human edits (a pinned or human-owned pillar is never rejected, consistent with the existing pinned-misfit rule); the Strategist's output also accepts the stored `{"pillars": {...}}` shape and drops `pinned`/`edited_by` (a model can never pin); two pillars may not rank the same directive (the ranking would repeat it).
- `idle_resources` (which resources the briefing flags IDLE) and the `GovernorDecision` directive list stay in `governor.py`: they mirror the Stellaris briefing and directive set, which the spec leaves out of scope.
