# Strategy Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the governor's free-text plan and retrospective with versioned per-pillar strategies, set by a Strategist on its own model role, that frame every directive and carry two player actions (preferred tech picks, small market orders).

**Architecture:** A pure-Python `pilot/strategy.py` holds the data model, validation, directive ranking and milestone status. The governor runs the Strategist (role `strategy`) at start, every N decisions, on events and on request, stores versions in telemetry (`strategies` table), puts a frame in every decision prompt and tags off-frame choices. Tech picks and market orders are MCP tools in the Rust controller (`stellaris_pick_tech`, `stellaris_market_sync`), whose selection logic is pure and unit-tested and whose screen positions live in the Stellaris manifest. The dashboard gets a Strategy tab with edit/pin/history.

**Tech Stack:** Python 3.13, pydantic, pydantic-ai, aiohttp, SQLite; Rust (game-controller, jomini); vanilla JS dashboard.

**Spec:** `docs/superpowers/specs/2026-09-26-strategy-layer-design.md`

## Global Constraints

- Pillars are exactly: `economy`, `expansion`, `technology`, `diplomacy`, `defence`, `government`, `society` (each once, priorities unique 1..7).
- Milestone metrics: `systems`, `colonies`, `pops`, `techs_known`, `military_power`, `economy_power`, `tech_power`, and `rank:<measure>` for measure in `systems, pops, techs, military_power, economy_power, tech_power, colonies`; ops `>=`, `<=`.
- Actions: technology `prefer_techs` ≤ 6 corpus tech ids; economy `market` ≤ 2 orders; sell only an idle resource; amount ≤ 20% of that resource's monthly income (≤ 25 for trade).
- Directive mapping: economy→`consolidate_economy`, expansion→`expand`, technology→`tech_rush`, diplomacy→`diplomacy_first`, defence→`defend`; government/society map to none; `prepare_war` never ranked (it keeps its human-approval gate).
- Event reviews: at most one per 12 in-game months; scheduled review every `retro_every` decisions (default 5); a review may return "no change" (no new version).
- Tech pick only when the field's current research has < 10% of its cost; one miss per tech per review.
- Decision request limit 6 (was 4).
- Model role `strategy` replaces `retrospective`; a saved `retrospective` list migrates to `strategy`.
- Commit only through `scripts/ci-commit.sh "<conventional message>" "<body>"`; no AI attribution; tests must not reach a real model provider.
- Never send input unless Stellaris is in the foreground (existing checks); never touch saves other than the test campaign.

## Review Focus

- A Strategist that returns a pinned pillar changed: the pinned pillar must keep the human's text (test in Task 3).
- A human edit arriving while a review runs: the edit wins for that pillar (test in Task 8).
- A milestone on a metric with no data yet (new campaign): status `at_risk`, never an exception (test in Task 1).
- An offered tech list that does not contain any preferred tech, or a field already researching one: no click at all (test in Task 5).
- A monthly trade order in the save that the pillar no longer wants (e.g. the human removed it): it is removed, and an order for a non-idle resource is never added (test in Task 5).

---

### Task 1: Strategy model, validation, ranking and milestone status

**Files:**
- Create: `src/pilot/strategy.py`
- Test: `tests/test_strategy.py`

**Interfaces:**
- Produces:
  - `PILLARS: tuple[str, ...]`, `DIRECTIVE_OF: dict[str, str | None]`, `METRICS: tuple[str, ...]`
  - `class Milestone(BaseModel)`: `metric: str`, `op: Literal[">=", "<="]`, `target: float`, `by: str`
  - `class MarketOrder(BaseModel)`: `side: Literal["sell", "buy"]`, `resource: str`, `amount: int`
  - `class Pillar(BaseModel)`: `priority: int`, `stance: str`, `goals: list[str]`, `milestones: list[Milestone] = []`, `prefer_techs: list[str] = []`, `market: list[MarketOrder] = []`, `pinned: bool = False`, `edited_by: Literal["model","human"] = "model"`
  - `class Strategy(BaseModel)`: `pillars: dict[str, Pillar]`, `focus: str`, `reason: str = ""`; method `ranking() -> list[str]`
  - `validate(s: Strategy, *, previous: Strategy | None, tech_ids: set[str], idle: set[str], income: dict[str, float]) -> list[str]` (empty = valid)
  - `keep_pinned(new: Strategy, previous: Strategy | None) -> Strategy` (pinned pillars of `previous` replace those in `new`)
  - `milestone_status(m: Milestone, rows: list[dict], today: str) -> str` (`met|on_track|at_risk|missed`)
  - `metric_value(row: dict, metric: str) -> float | None`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_strategy.py
import pytest

from pilot.strategy import (Milestone, Pillar, Strategy, keep_pinned, metric_value, milestone_status,
                            validate)

PRIOS = {"defence": 1, "economy": 2, "technology": 3, "expansion": 4, "diplomacy": 5, "government": 6, "society": 7}


def strat(**over) -> Strategy:
    pillars = {p: Pillar(priority=n, stance=f"{p} stance", goals=[f"{p} goal"]) for p, n in PRIOS.items()}
    pillars.update(over)
    return Strategy(pillars=pillars, focus="hold the line")


def test_ranking_follows_priorities_and_skips_pillars_without_a_directive():
    assert strat().ranking() == ["defend", "consolidate_economy", "tech_rush", "expand", "diplomacy_first"]


def test_valid_strategy_has_no_errors():
    assert validate(strat(), previous=None, tech_ids={"tech_habitat_1"}, idle=set(), income={}) == []


def test_validation_catches_bad_pillars_metrics_techs_and_orders():
    bad = strat(technology=Pillar(priority=3, stance="s", goals=["g"], prefer_techs=["tech_nope"],
                                  milestones=[Milestone(metric="happiness", op=">=", target=1, by="2250.01.01")]),
                economy=Pillar(priority=3, stance="s", goals=["g"],
                               market=[{"side": "sell", "resource": "energy", "amount": 500}]))
    errs = validate(bad, previous=None, tech_ids={"tech_habitat_1"}, idle={"energy"}, income={"energy": 100})
    joined = " | ".join(errs)
    assert "duplicate priority 3" in joined
    assert "unknown metric 'happiness'" in joined
    assert "unknown tech 'tech_nope'" in joined
    assert "energy 500 is over 20" in joined


def test_selling_a_resource_that_is_not_idle_is_rejected():
    s = strat(economy=Pillar(priority=2, stance="s", goals=["g"], market=[{"side": "sell", "resource": "minerals", "amount": 5}]))
    assert any("not idle" in e for e in validate(s, previous=None, tech_ids=set(), idle={"energy"}, income={"minerals": 100}))


def test_missing_or_extra_pillars_are_rejected():
    s = strat()
    del s.pillars["society"]
    assert any("missing pillar society" in e for e in validate(s, previous=None, tech_ids=set(), idle=set(), income={}))


def test_pinned_pillars_survive_a_model_rewrite():
    human = Pillar(priority=5, stance="stay out of federations", goals=["no federation"], pinned=True, edited_by="human")
    old = strat(diplomacy=human)
    new = strat(diplomacy=Pillar(priority=5, stance="join a federation", goals=["federation"]))
    kept = keep_pinned(new, old)
    assert kept.pillars["diplomacy"].stance == "stay out of federations" and kept.pillars["diplomacy"].pinned


def test_milestone_status_from_metrics_rows():
    rows = [{"date": "2240.01.01", "planets": 4}, {"date": "2241.01.01", "planets": 6}]
    m = Milestone(metric="colonies", op=">=", target=10, by="2243.01.01")
    assert milestone_status(m, rows, "2241.01.01") == "on_track"          # +2/yr → 10 by 2243
    assert milestone_status(Milestone(metric="colonies", op=">=", target=12, by="2243.01.01"), rows, "2241.01.01") == "at_risk"
    assert milestone_status(Milestone(metric="colonies", op=">=", target=5, by="2243.01.01"), rows, "2241.01.01") == "met"
    assert milestone_status(Milestone(metric="colonies", op=">=", target=12, by="2240.06.01"), rows, "2241.01.01") == "missed"
    assert milestone_status(m, [], "2241.01.01") == "at_risk", "no data yet is at risk, not an error"


def test_metric_value_reads_counts_and_ranks():
    row = {"planets": 7, "systems": 20, "peers": {"military_power": {"rank": 9, "median": 3000}}}
    assert metric_value(row, "colonies") == 7 and metric_value(row, "systems") == 20
    assert metric_value(row, "rank:military_power") == 9
    assert metric_value(row, "rank:techs") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/test_strategy.py -p no:cacheprovider`
Expected: FAIL (`ModuleNotFoundError: No module named 'pilot.strategy'`)

- [ ] **Step 3: Implement `src/pilot/strategy.py`**

```python
"""Pillar strategies: the governor's top-down frame (docs/superpowers/specs/2026-09-26-strategy-layer-design.md).

Pure data and rules; no model calls, no game input."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

PILLARS = ("economy", "expansion", "technology", "diplomacy", "defence", "government", "society")
DIRECTIVE_OF: dict[str, str | None] = {"economy": "consolidate_economy", "expansion": "expand", "technology": "tech_rush",
                                       "diplomacy": "diplomacy_first", "defence": "defend", "government": None, "society": None}
RANK_MEASURES = ("systems", "pops", "techs", "military_power", "economy_power", "tech_power", "colonies")
METRICS = ("systems", "colonies", "pops", "techs_known", "military_power", "economy_power", "tech_power",
           *(f"rank:{m}" for m in RANK_MEASURES))
_ROW_KEY = {"colonies": "planets"}          # metrics rows store colonies as `planets`


class Milestone(BaseModel):
    metric: str
    op: Literal[">=", "<="]
    target: float
    by: str = Field(description="in-game date YYYY.MM.DD")


class MarketOrder(BaseModel):
    side: Literal["sell", "buy"]
    resource: str
    amount: int = Field(gt=0)


class Pillar(BaseModel):
    priority: int
    stance: str
    goals: list[str] = Field(default_factory=list)
    milestones: list[Milestone] = Field(default_factory=list)
    prefer_techs: list[str] = Field(default_factory=list)
    market: list[MarketOrder] = Field(default_factory=list)
    pinned: bool = False
    edited_by: Literal["model", "human"] = "model"


class Strategy(BaseModel):
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
            if m.metric not in METRICS:
                errs.append(f"{name}: unknown metric {m.metric!r}")
        if pl.prefer_techs and name != "technology":
            errs.append(f"{name}: only the technology pillar prefers techs")
        if len(pl.prefer_techs) > 6:
            errs.append("technology: at most 6 preferred techs")
        for t in pl.prefer_techs:
            if t not in tech_ids:
                errs.append(f"technology: unknown tech {t!r}")
        if pl.market and name != "economy":
            errs.append(f"{name}: only the economy pillar places market orders")
        if len(pl.market) > 2:
            errs.append("economy: at most 2 market orders")
        for o in pl.market:
            cap = 25 if o.resource == "trade" else 0.2 * max(income.get(o.resource, 0.0), 0.0)
            if o.side == "sell" and o.resource not in idle:
                errs.append(f"economy: selling {o.resource} but it is not idle")
            if o.side == "sell" and o.amount > cap:
                errs.append(f"economy: sell {o.resource} {o.amount} is over {cap:.0f} (20% of monthly income)")
    if previous is not None:
        for name, pl in previous.pillars.items():
            if pl.pinned and name in s.pillars and s.pillars[name].model_dump() != pl.model_dump():
                errs.append(f"{name} is pinned by the human and must not change")
    return errs


def keep_pinned(new: Strategy, previous: Strategy | None) -> Strategy:
    """`new` with every pinned pillar of `previous` put back unchanged."""
    if previous is None:
        return new
    pillars = dict(new.pillars)
    for name, pl in previous.pillars.items():
        if pl.pinned:
            pillars[name] = pl
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
    past = next(((mo, v) for mo, v in reversed(series) if now_mo - mo >= 12), series[0])
    span = max(now_mo - past[0], 1)
    projected = now + (now - past[1]) / span * (_months(m.by) - now_mo)
    return "on_track" if ok(projected) else "at_risk"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest -q tests/test_strategy.py -p no:cacheprovider`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add src/pilot/strategy.py tests/test_strategy.py
scripts/ci-commit.sh "feat(pilot): pillar strategy model, validation, ranking and milestone status" "Pure module for the strategy layer spec: seven pillars with priorities, stances, goals, measurable milestones and the two actions; validation (pillars, priorities, metrics, techs, market limits, pinned pillars), directive ranking and milestone status projected from metrics rows."
```

---

### Task 2: Strategy versions in telemetry

**Files:**
- Modify: `src/pilot/telemetry.py` (schema block near line 55; `ingest` near line 157; add methods after `latest_plan` near line 200)
- Test: `tests/test_governor.py` (append)

**Interfaces:**
- Consumes: `Strategy` (Task 1) as `strategy.model_dump()` JSON in events.
- Produces:
  - event kind `strategy` with fields `date, trigger, model, strategy (dict), reason` → row in `strategies`
  - `Telemetry.latest_strategy(campaign_id) -> dict | None` (the stored JSON)
  - `Telemetry.strategy_history(campaign_id, limit=50) -> list[dict]` (newest first: `date, trigger, model, t, strategy`)
  - `Telemetry.metrics_rows(campaign_id) -> list[dict]` (metrics JSON rows, oldest first)

- [ ] **Step 1: Write the failing test**

```python
def test_strategy_versions_are_stored_per_campaign(tmp_path):
    from pilot.events import EventLog
    from pilot.telemetry import Telemetry
    tel = Telemetry(tmp_path / "t.sqlite")
    log = EventLog(tmp_path / "runs", "r1", "m", telemetry=tel)
    log.set_campaign("stellaris", "theian_1", "Theian")
    log.emit("metrics", date="2240.01.01", planets=4)
    log.emit("strategy", date="2240.01.01", trigger="start of run", model="m", reason="first",
             strategy={"pillars": {}, "focus": "grow"})
    log.emit("strategy", date="2245.01.01", trigger="war started", model="m", reason="war",
             strategy={"pillars": {}, "focus": "defend"})
    cid = log.campaign_id
    assert tel.latest_strategy(cid)["focus"] == "defend"
    hist = tel.strategy_history(cid)
    assert [h["trigger"] for h in hist] == ["war started", "start of run"]
    assert tel.metrics_rows(cid)[0]["planets"] == 4
    assert tel.latest_strategy("nope") is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest -q tests/test_governor.py -k strategy_versions -p no:cacheprovider`
Expected: FAIL (`AttributeError: 'Telemetry' object has no attribute 'latest_strategy'`)

- [ ] **Step 3: Implement**

Add to the schema string (after the `plans` index):

```sql
CREATE TABLE IF NOT EXISTS strategies (
    campaign_id TEXT, run_id TEXT NOT NULL, t REAL, date TEXT, trigger TEXT, model TEXT, data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS strategies_campaign ON strategies(campaign_id, t);
```

In `ingest`, next to `elif kind == "plan":`:

```python
        elif kind == "strategy":
            self._exec("INSERT INTO strategies(campaign_id, run_id, t, date, trigger, model, data) VALUES (?,?,?,?,?,?,?)",
                       (self._campaign_of(run_id), run_id, t, data.get("date"), data.get("trigger"), data.get("model"),
                        json.dumps({**(data.get("strategy") or {}), "reason": data.get("reason", "")}, default=str)))
```

Also add `"strategies"` to the table tuple in `rebuild` (the loop near line 229) and to the `UPDATE … SET campaign_id` backfill next to `plans` (near line 119):

```python
        self._exec("UPDATE strategies SET campaign_id=? WHERE run_id=? AND campaign_id IS NULL", (cid, run_id))
```

Methods after `latest_plan`:

```python
    def latest_strategy(self, campaign_id: str) -> dict | None:
        rows = self.query("SELECT data FROM strategies WHERE campaign_id=? ORDER BY t DESC LIMIT 1", (campaign_id,))
        return json.loads(rows[0]["data"]) if rows else None

    def strategy_history(self, campaign_id: str, limit: int = 50) -> list[dict]:
        rows = self.query("SELECT date, trigger, model, t, data FROM strategies WHERE campaign_id=? ORDER BY t DESC LIMIT ?",
                          (campaign_id, limit))
        return [{"date": r["date"], "trigger": r["trigger"], "model": r["model"], "t": r["t"],
                 "strategy": json.loads(r["data"])} for r in rows]

    def metrics_rows(self, campaign_id: str) -> list[dict]:
        return [json.loads(r["data"]) for r in
                self.query("SELECT data FROM metrics WHERE campaign_id=? AND month IS NOT NULL ORDER BY month", (campaign_id,))]
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest -q tests/test_governor.py -k "strategy_versions or telemetry" -p no:cacheprovider`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/pilot/telemetry.py tests/test_governor.py
scripts/ci-commit.sh "feat(telemetry): strategy versions per campaign" "strategies table fed by strategy events (date, trigger, model, JSON), latest and history queries, metrics rows for milestone status; included in rebuild."
```

---

### Task 3: The Strategist (role `strategy`) replaces the retrospective

**Files:**
- Modify: `src/pilot/models.py` (`ROLES`, `ROLE_IDS`, `load_prefs` migration)
- Modify: `src/pilot/governor.py` (new `StrategyReview` output model and `STRATEGY_INSTRUCTIONS` near `class Retrospective` line 55; `_build` role `strategy`; `__init__` loads the strategy; replace `_retrospective` (line 874) with `_review_strategy`; `_since_retro` logic at line 864)
- Test: `tests/test_governor.py` (append)

**Interfaces:**
- Consumes: Task 1 (`Strategy`, `validate`, `keep_pinned`, `milestone_status`), Task 2 (`latest_strategy`, `metrics_rows`).
- Produces:
  - `class StrategyReview(BaseModel)`: `change: bool`, `strategy: Strategy | None`, `assessment: str`, `rules: list[str] = []`
  - `Governor.strategy: Strategy | None`; `Governor._review_strategy(b: dict, trigger: str) -> None`; `Governor.review_requested: str | None` (pending trigger)
  - role id `strategy` in `models.ROLES`; `Governor._pool("strategy")`
  - emits `strategy` events (Task 2) and `strategy_review` events `{date, trigger, change, assessment}`

- [ ] **Step 1: Write the failing tests**

```python
def _strategist(calls, *, change=True, pin_diplomacy_to=None):
    from pilot.strategy import Pillar, Strategy
    prios = {"defence": 1, "economy": 2, "technology": 3, "expansion": 4, "diplomacy": 5, "government": 6, "society": 7}

    def respond(messages, info):
        calls.append("strategist")
        pillars = {p: Pillar(priority=n, stance=f"{p} by model", goals=["g"]).model_dump() for p, n in prios.items()}
        if pin_diplomacy_to:
            pillars["diplomacy"]["stance"] = pin_diplomacy_to
        body = {"change": change, "assessment": "ok", "rules": [],
                "strategy": {"pillars": pillars, "focus": "grow", "reason": "start"} if change else None}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, body)])
    return FunctionModel(respond)


def test_a_strategy_is_set_at_the_start_of_a_run(setup):
    s, log = setup
    calls = []
    Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=_recording("decide", calls),
             role_models={"strategy": _strategist(calls)}).run(max_decisions=1)
    assert calls[0] == "strategist" and calls[1] == "decide"
    assert any(e["kind"] == "strategy" for e in log.recent)


def test_a_no_change_review_writes_no_version(setup):
    from dataclasses import replace
    s, log = setup
    s2 = replace(s, retro_every=1)
    s2.__class__ = s.__class__
    calls = []
    first = _strategist(calls)
    g = Governor(s2, FakeStellaris([briefing(f"22{i:02d}.01.01") for i in range(3)]), log,
                 model=_recording("decide", calls), role_models={"strategy": first})
    g.run(max_decisions=1)
    g._role_objs["strategy"] = _strategist(calls, change=False)
    g.__dict__.pop("_agents", None)
    g._review_strategy(briefing("2202.01.01"), "scheduled")
    assert sum(1 for e in log.recent if e["kind"] == "strategy") == 1
    assert any(e["kind"] == "strategy_review" and not e["change"] for e in log.recent)


def test_the_strategist_cannot_change_a_pinned_pillar(setup):
    from pilot.strategy import Pillar
    s, log = setup
    calls = []
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=_recording("decide", calls),
                 role_models={"strategy": _strategist(calls)})
    g._review_strategy(briefing("2200.01.01"), "start of run")
    g.strategy.pillars["diplomacy"] = Pillar(priority=5, stance="no federations", goals=["g"], pinned=True, edited_by="human")
    g._role_objs["strategy"] = _strategist(calls, pin_diplomacy_to="join a federation")
    g.__dict__.pop("_agents", None)
    g._review_strategy(briefing("2201.01.01"), "scheduled")
    assert g.strategy.pillars["diplomacy"].stance == "no federations"


def test_an_invalid_strategy_is_retried_once_then_dropped(setup):
    s, log = setup
    calls = []

    def bad(messages, info):
        calls.append("bad")
        body = {"change": True, "assessment": "x", "rules": [], "strategy": {"pillars": {}, "focus": "f", "reason": "r"}}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, body)])
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"), role_models={"strategy": FunctionModel(bad)})
    g._review_strategy(briefing("2200.01.01"), "start of run")
    assert calls == ["bad", "bad"] and g.strategy is None
    assert any(e["kind"] == "strategy_rejected" for e in log.recent)


def test_saved_retrospective_models_move_to_the_strategy_role(tmp_path):
    import json as _json

    from pilot.models import ROLE_IDS, load_prefs
    assert "strategy" in ROLE_IDS and "retrospective" not in ROLE_IDS
    (tmp_path / "pilot-settings.json").write_text(_json.dumps({"roles": {"retrospective": {
        "models": [{"model": "google:gemini-3.1-pro-preview", "thinking": "high"}], "rotate": False}}}))
    assert load_prefs(tmp_path)["roles"]["strategy"]["models"][0]["model"] == "google:gemini-3.1-pro-preview"
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/test_governor.py -k "strategy_is_set or no_change_review or pinned_pillar or move_to_the_strategy" -p no:cacheprovider`
Expected: FAIL

- [ ] **Step 3: Implement**

`src/pilot/models.py` — replace the `retrospective` entry in `ROLES` with:

```python
    {"id": "strategy", "label": "Strategy", "help": "Sets and reviews the pillar strategies at the start, every few decisions and on big events: use your best reasoning model."},
```

and in `load_prefs`, before `check_roles`, migrate:

```python
    raw_roles = dict(d.get("roles") or {})
    if "retrospective" in raw_roles and "strategy" not in raw_roles:
        raw_roles["strategy"] = raw_roles.pop("retrospective")
    raw_roles.pop("retrospective", None)
```

(then pass `raw_roles` to `check_roles`). Update the existing test `test_retrospectives_use_their_own_models` to use role `strategy` and the `_strategist` model (the retrospective role no longer exists).

`src/pilot/governor.py` — output model and instructions next to `class Retrospective` (keep `Retrospective` until Task 4 removes its last use):

```python
from .strategy import Strategy, keep_pinned, milestone_status, validate


class StrategyReview(BaseModel):
    change: bool = Field(description="false when the current strategy should stay as it is")
    strategy: Strategy | None = Field(default=None, description="the full new strategy when change is true")
    assessment: str = Field(description="what worked and what did not since the last review, citing numbers")
    rules: list[str] = Field(default_factory=list, description="0-3 general rules learned (situation -> choice)")


STRATEGY_INSTRUCTIONS = """You are the Strategist: you set the empire's top-down strategy, one entry per pillar
(economy, expansion, technology, diplomacy, defence, government, society). Each pillar: a unique priority
(1 = first), a stance of one or two sentences, 1-3 goals, milestones on the briefing's measures
(systems, colonies, pops, techs_known, military_power, economy_power, tech_power, rank:<measure>) with a
target and an in-game date, and only for technology `prefer_techs` (tech ids to pick when offered; at most 6)
and only for economy `market` (at most 2 small monthly orders; sell only a resource the briefing lists as
IDLE, at most 20% of its monthly income). Priorities decide which directives the governor prefers.
Everything must be achievable through directives, tech picks or market orders: the game's AI builds,
designs ships and moves fleets. Never change a pillar marked pinned: the human set it. If nothing
material changed, answer change=false. Build on the empire's species, ethics, civics and origin."""
```

In `_build`, add:

```python
        if role == "strategy":
            return Agent(model, deps_type=GovDeps, output_type=StrategyReview, instructions=STRATEGY_INSTRUCTIONS + "\n\n" + text,
                         tools=[Tool(f) for f in (consult, get_doc)], model_settings=governor_settings(settings), retries=2)
```

In `__init__` after `self.plan = ""`: `self.strategy: Strategy | None = None` and `self.review_requested: str | None = None`. In `_set_campaign`, after loading the plan:

```python
        if self.log.telemetry is not None:
            try:
                raw = self.log.telemetry.latest_strategy(self.log.campaign_id or "")
                self.strategy = Strategy.model_validate({k: v for k, v in raw.items() if k != "reason"}) if raw else None
            except Exception as e:  # noqa: BLE001
                self.log.emit("briefing_error", error=f"loading the strategy: {e}"[:200])
        self.log.state.info["strategy"] = self.strategy.model_dump() if self.strategy else None
```

Replace `_retrospective` with `_review_strategy` (and change the call at line 865 to `self._review_strategy(b, f"scheduled after {self.s.retro_every} decisions")`):

```python
    def _milestones_text(self) -> str:
        if not self.strategy or self.log.telemetry is None or not self.log.campaign_id:
            return "(none)"
        rows = self.log.telemetry.metrics_rows(self.log.campaign_id)
        today = rows[-1]["date"] if rows else "2200.01.01"
        out = []
        for name, pl in sorted(self.strategy.pillars.items(), key=lambda kv: kv[1].priority):
            for m in pl.milestones:
                out.append(f"- {name}: {m.metric} {m.op} {m.target:g} by {m.by}: {milestone_status(m, rows, today)}")
        return "\n".join(out) or "(none)"

    def _review_strategy(self, b: dict, trigger: str, retried: bool = False, errors: list[str] | None = None) -> None:
        """Strategist review: may keep the strategy or write a new version (pinned pillars stay). An invalid
        answer is retried once with the reasons; still invalid → no change."""
        self._since_retro = 0
        self.review_requested = None
        current = self.strategy.model_dump_json(indent=1) if self.strategy else "(none yet: write the first strategy)"
        prompt = [f"Strategy review, trigger: {trigger}.", "Current strategy:\n" + current,
                  "Milestones (status computed from the recorded numbers):\n" + self._milestones_text(),
                  "Directive changes and what followed:\n" + (self.log.telemetry.past_outcomes(self.log.campaign_id)
                                                              if self.log.telemetry is not None and self.log.campaign_id else "(none)"),
                  "Latest briefing:\n" + (self.last_briefing or self.game.briefing_text())]
        if errors:
            prompt.insert(0, "Your previous answer was rejected: " + "; ".join(errors) + ". Fix exactly these problems.")
        trend = self._trend(b)
        if trend:
            prompt.append(trend)
        deps = GovDeps(self.game, self.store, self.log)
        base: dict = {}
        ask = lambda agent: agent.run_sync("\n\n".join(prompt), deps=deps,  # noqa: E731
                                           usage_limits=UsageLimits(request_limit=self.s.max_requests_per_episode))
        try:
            result, entry = self._call("strategy", ask, on_try=lambda e: base.update(model=e["model"]))
        except Exception as e:  # noqa: BLE001 - a failed review never stops play; retried at the next decision
            self.review_requested = trigger
            self.log.emit("episode_error", error=f"strategy review: {type(e).__name__}: {e}"[:500])
            return
        r: StrategyReview = result.output
        for rule in r.rules[:3]:
            try:
                self.store.add_rule(rule, f"strategy review {b['date']}")
                self.log.emit("learned", category="rules", message="strategy review rule", rule=rule)
            except LearningRejected as e:
                self.log.emit("learn_rejected", category="rules", reason=str(e), rule=rule)
        self.log.emit("strategy_review", date=b["date"], trigger=trigger, change=bool(r.change and r.strategy),
                      assessment=r.assessment[:2000], model=base.get("model"))
        if not (r.change and r.strategy):
            return
        new = keep_pinned(r.strategy, self.strategy)
        errs = validate(new, previous=self.strategy, tech_ids=self._tech_ids(), idle=idle_resources(b),
                        income=b.get("net", {}))
        if errs and not retried:
            # one corrective retry: the model sees exactly what was wrong
            return self._review_strategy(b, trigger, retried=True, errors=errs)
        if errs:
            self.log.emit("strategy_rejected", date=b["date"], errors=errs[:10])
            return
        self._set_strategy(new, b["date"], trigger, base.get("model", ""))

    def _set_strategy(self, s: Strategy, date: str, trigger: str, model: str) -> None:
        self.strategy = s
        self.log.state.info["strategy"] = s.model_dump()
        self.log.emit("strategy", date=date, trigger=trigger, model=model, reason=s.reason, strategy=s.model_dump())

    def _tech_ids(self) -> set[str]:
        """Tech ids from the corpus (for validating preferred techs); cached."""
        if not hasattr(self, "_techs"):
            import json as _json
            path = self.s.corpus_dir / "data" / "tech.json"
            try:
                self._techs = {r["id"].split(":", 1)[1] for r in _json.loads(path.read_text(encoding="utf-8"))}
            except (OSError, ValueError, KeyError):
                self._techs = set()
        return self._techs
```

Module-level helper (near `metrics`):

```python
def idle_resources(b: dict) -> set[str]:
    """Resources the briefing would flag IDLE: large stock, positive net, over 10 years of income (trade: > 15,000)."""
    out = set()
    for k, v in (b.get("stockpile") or {}).items():
        n = (b.get("net") or {}).get(k, 0)
        if k == "trade" and v > 15000 and n > 0:
            out.add(k)
        elif v > 5000 and n > 0 and v > n * 120:
            out.add(k)
    return out
```

In `_start`, after `self._set_campaign(b)` and before `self._decide(b, "start of run")`:

```python
                if self.strategy is None:
                    self._review_strategy(b, "start of run")
```

Remove `_retrospective`, `Retrospective`, `RETRO_INSTRUCTIONS` and the `retrospective` branch in `_build`. Keep `self.plan`/`_set_plan` untouched until Task 4 removes the plan text from the decision prompt.

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/python -m pytest -q tests/ -p no:cacheprovider`
Expected: PASS (all; fix any test that still references `retrospective` by switching it to `strategy`)

- [ ] **Step 5: Commit**

```bash
git add src/pilot tests
scripts/ci-commit.sh "feat(governor): Strategist on its own model role replaces the retrospective" "Reviews at run start (no strategy yet) and every retro_every decisions; may keep the strategy (no version) or write a validated new one; pinned pillars are always kept; rules learned as before; saved retrospective model lists move to the strategy role."
```

---

### Task 4: Decisions work inside the frame; event reviews; request limit

**Files:**
- Modify: `src/pilot/governor.py` (`_decide` prompt near line 787 and result handling; `_run_until_next_decision` near line 601; `GovernorDecision`; `urgent_changes`)
- Modify: `src/pilot/config.py` (`governor_max_requests: int = 6`)
- Test: `tests/test_governor.py` (append)

**Interfaces:**
- Consumes: `Governor.strategy`, `Strategy.ranking()`, `_milestones_text()`, `_review_strategy(b, trigger)` (Task 3).
- Produces: `frame_text(strategy, milestones_text) -> str`; decision traces carry `off_frame: bool`; event reviews with a 12-month cap (`Governor._last_event_review_month`); `GovernorDecision` loses `plan`.

- [ ] **Step 1: Write the failing tests**

```python
def test_decisions_get_the_strategy_frame(setup):
    s, log = setup
    seen = []

    def respond(messages, info):
        seen.append(" ".join(str(p.content) for m in messages for p in getattr(m, "parts", []) if hasattr(p, "content")))
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"directive": "keep", "reason": "r"})])
    calls = []
    Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=FunctionModel(respond),
             role_models={"strategy": _strategist(calls)}).run(max_decisions=1)
    assert any("STRATEGY FRAME" in t and "defend > consolidate_economy > tech_rush > expand > diplomacy_first" in t for t in seen)


def test_an_off_frame_choice_is_tagged_and_schedules_a_review(setup):
    s, log = setup
    calls = []
    g = Governor(s, FakeStellaris([briefing("2200.01.01"), briefing("2201.01.01", net={"energy": -5.0})]), log,
                 model=decisions("keep", "diplomacy_first"), role_models={"strategy": _strategist(calls)})
    g.run(max_decisions=2)
    traces = [e for e in log.recent if e["kind"] == "trace" and e.get("decision") == "diplomacy_first"]
    assert traces and traces[-1].get("off_frame") is True
    assert g.review_requested and "off-frame" in g.review_requested


def test_event_reviews_are_capped_at_one_per_year(setup):
    s, log = setup
    calls = []
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"), role_models={"strategy": _strategist(calls)})
    g._review_strategy(briefing("2200.01.01"), "start of run")
    assert g._maybe_event_review(briefing("2201.01.01"), "war started") is True
    assert g._maybe_event_review(briefing("2201.06.01"), "war ended") is False, "within 12 months of the last event review"
    assert g._maybe_event_review(briefing("2202.02.01"), "war ended") is True


def test_the_decision_request_limit_is_six():
    assert Settings().governor_max_requests == 6
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/test_governor.py -k "strategy_frame or off_frame or capped_at_one or request_limit_is_six" -p no:cacheprovider`
Expected: FAIL

- [ ] **Step 3: Implement**

`config.py`: `governor_max_requests: int = 6`.

`governor.py` — module-level:

```python
EVENT_TRIGGERS = ("new war", "war ended", "crisis", "colony lost", "boxed in", "milestone missed", "off-frame")


def frame_text(strategy: Strategy | None, milestones: str) -> str:
    if strategy is None:
        return ""
    lines = ["STRATEGY FRAME (from the Strategist; choose within it):",
             f"Directive ranking: {' > '.join(strategy.ranking())}", f"Focus: {strategy.focus}"]
    for name, pl in sorted(strategy.pillars.items(), key=lambda kv: kv[1].priority):
        lines.append(f"{pl.priority}. {name}{' (pinned by the human)' if pl.pinned else ''}: {pl.stance}")
    at_risk = [m for m in milestones.splitlines() if m.endswith(("at_risk", "missed"))]
    if at_risk:
        lines.append("Milestones at risk or missed:\n" + "\n".join(at_risk))
    lines.append("Pick the highest-ranked directive that fits the briefing, or keep. Choose a directive outside "
                 "this ranking only for an urgent line (new war, deficit, crisis) and say so in the reason.")
    return "\n".join(lines)
```

In `_decide`, replace the `"Campaign plan:\n" + …` prompt element with `frame_text(self.strategy, self._milestones_text()) or "No strategy yet."` (drop the plan text). After the model answers and before applying, compute:

```python
        ranked = self.strategy.ranking() if self.strategy else []
        off_frame = bool(ranked) and chosen not in ("keep", current) and chosen not in ranked[:2]
        if off_frame:
            self.review_requested = f"off-frame decision: {chosen} ({reason})"
```

and add `"off_frame": off_frame` to the trace dict passed to `save_trace` (`base` update) so the `trace` event summary carries it (add `"off_frame"` to the summary keys in `events.py` `save_trace`). Delete the `d.plan` handling and the `plan` field from `GovernorDecision`.

Event reviews:

```python
    def _maybe_event_review(self, b: dict, trigger: str) -> bool:
        """Run a strategy review for a big event, at most once per 12 in-game months."""
        last = getattr(self, "_last_event_review_month", None)
        now = months(b["date"])
        if last is not None and now - last < 12:
            return False
        self._last_event_review_month = now
        self._review_strategy(b, trigger)
        return True
```

In the main loop after each `_decide(b, reason)`: if `reason` starts with `urgent:` and contains any of `EVENT_TRIGGERS`, or `self.review_requested` is set, call `self._maybe_event_review(b, self.review_requested or reason)`; if the review fails, `_review_strategy` leaves `review_requested` set so the next decision retries it. Add `urgent_changes` entries `colony lost: <n> -> <m>` (when `len(planets)` drops) and `boxed in` (when `expansion.reach_unclaimed` becomes 0 from > 0).

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/python -m pytest -q tests/ -p no:cacheprovider`
Expected: PASS (update older tests that asserted plan text in the prompt to assert the frame instead)

- [ ] **Step 5: Commit**

```bash
git add src/pilot tests
scripts/ci-commit.sh "feat(governor): decisions choose within the strategy frame; event reviews" "Decision prompts carry the pillar ranking, focus and at-risk milestones instead of the free-text plan; a choice outside the top of the ranking is tagged off_frame and schedules a review; big events (war, crisis, colony lost, boxed in, missed milestone) trigger a review at most once per 12 in-game months; decision request limit 6."
```

---

### Task 5: Tech-pick and market-order selection (Rust, pure)

**Files:**
- Modify: `crates/game-controller/src/stellaris.rs` (new section "strategy actions"; `Briefing` gets `market_orders`)
- Test: same file `#[cfg(test)] mod tests`

**Interfaces:**
- Produces:
  - `pub struct TechPick { pub field: String, pub tech: String, pub option_index: usize }`
  - `pub fn choose_tech_pick(research: &BTreeMap<String, Research>, prefer: &[String], cost: &dyn Fn(&str) -> Option<f64>) -> Option<TechPick>`
  - `pub struct MarketOrderSpec { pub side: String, pub resource: String, pub amount: i64 }` (serde)
  - `pub fn market_diff(current: &[MarketOrderSpec], desired: &[MarketOrderSpec]) -> (Vec<MarketOrderSpec>, Vec<MarketOrderSpec>)` (to add, to remove)
  - `Briefing.market_orders: Vec<MarketOrderSpec>` read from the save's `market.monthly_trades` for our country

- [ ] **Step 1: Write the failing tests** (append to `mod tests`)

```rust
    #[test]
    fn tech_pick_prefers_offered_techs_and_leaves_started_research_alone() {
        let mut research = BTreeMap::new();
        research.insert("engineering".to_string(), Research { current: Some(("tech_mining_2".into(), 50.0)),
            alternatives: vec!["tech_mining_2".into(), "tech_habitat_1".into(), "tech_lasers_2".into()] });
        research.insert("society".to_string(), Research { current: Some(("tech_gene_crops".into(), 900.0)),
            alternatives: vec!["tech_gene_crops".into(), "tech_doctrine_navy_size_2".into()] });
        let cost = |t: &str| Some(if t == "tech_mining_2" { 1000.0 } else { 2000.0 });
        let prefer = vec!["tech_doctrine_navy_size_2".to_string(), "tech_habitat_1".to_string()];
        let pick = choose_tech_pick(&research, &prefer, &cost).unwrap();
        // society is 45% done (900/2000): not swapped; engineering is 5% done: swapped to habitats (option 2)
        assert_eq!((pick.field.as_str(), pick.tech.as_str(), pick.option_index), ("engineering", "tech_habitat_1", 1));
        // already researching a preferred tech: nothing to do
        let mut r2 = research.clone();
        r2.get_mut("engineering").unwrap().current = Some(("tech_habitat_1".into(), 0.0));
        assert!(choose_tech_pick(&r2, &["tech_habitat_1".to_string()], &cost).is_none());
        // no preferred tech offered: nothing
        assert!(choose_tech_pick(&research, &["tech_zro_1".to_string()], &cost).is_none());
    }

    #[test]
    fn market_diff_adds_missing_and_removes_unwanted_orders() {
        let o = |s: &str, r: &str, a: i64| MarketOrderSpec { side: s.into(), resource: r.into(), amount: a };
        let (add, remove) = market_diff(&[o("sell", "energy", 11), o("buy", "food", 5)], &[o("sell", "energy", 11), o("sell", "trade", 20)]);
        assert_eq!(add, vec![o("sell", "trade", 20)]);
        assert_eq!(remove, vec![o("buy", "food", 5)]);
    }

    #[test]
    fn briefing_reads_our_monthly_trades() {
        let gs = br#"date="2201.10.01"
player={ { name="x" country=0 } }
country={ 0={ name={ key="NAME_Us" } type="default" } }
market={ monthly_trades={ { trade_data={ trade_type=market_sell resource="energy" country=0 } amount=11 price=0 id=0 }
                          { trade_data={ trade_type=market_buy resource="minerals" country=7 } amount=5 price=0 id=1 } } }
"#;
        let b = brief_gamestate(gs).unwrap();
        assert_eq!(b.market_orders, vec![MarketOrderSpec { side: "sell".into(), resource: "energy".into(), amount: 11 }]);
    }
```

(`Research` needs `#[derive(Clone)]` if not present.)

- [ ] **Step 2: Run to verify they fail**

Run: `PATH=$HOME/.cargo/bin:$PATH cargo test -p game-controller --release tech_pick market_diff monthly_trades`
Expected: compile errors (missing items)

- [ ] **Step 3: Implement**

```rust
// ---- strategy actions (tech picks, market orders) ----------------------------------------------

#[derive(Debug, Clone, PartialEq, Serialize, serde::Deserialize)]
pub struct MarketOrderSpec {
    pub side: String,
    pub resource: String,
    pub amount: i64,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct TechPick {
    pub field: String,
    pub tech: String,
    /// 0-based position of `tech` in the field's offered alternatives (the screen lists them in this order)
    pub option_index: usize,
}

/// The first preferred tech that is offered in a field whose current research is below 10% of its
/// cost (fields already researching a preferred tech are left alone).
pub fn choose_tech_pick(research: &BTreeMap<String, Research>, prefer: &[String], cost: &dyn Fn(&str) -> Option<f64>) -> Option<TechPick> {
    for want in prefer {
        for (field, r) in research {
            if let Some((cur, _)) = &r.current {
                if prefer.contains(cur) {
                    continue;
                }
            }
            let Some(idx) = r.alternatives.iter().position(|t| t == want) else { continue };
            let started = r.current.as_ref().map(|(t, p)| cost(t).map(|c| *p >= 0.1 * c).unwrap_or(*p > 0.0)).unwrap_or(false);
            if !started {
                return Some(TechPick { field: field.clone(), tech: want.clone(), option_index: idx });
            }
        }
    }
    None
}

/// Orders to add and to remove so the save's monthly trades equal `desired`.
pub fn market_diff(current: &[MarketOrderSpec], desired: &[MarketOrderSpec]) -> (Vec<MarketOrderSpec>, Vec<MarketOrderSpec>) {
    let add = desired.iter().filter(|d| !current.contains(d)).cloned().collect();
    let remove = current.iter().filter(|c| !desired.contains(c)).cloned().collect();
    (add, remove)
}
```

In `Briefing` add `pub market_orders: Vec<MarketOrderSpec>,` and in `brief_gamestate` before `Ok(b)`:

```rust
    if let Some(trades) = obj(&root, "market").and_then(|m| get(&m, "monthly_trades")).and_then(|v| v.read_array().ok()) {
        for t in trades.values().filter_map(|x| x.read_object().ok()) {
            let Some(td) = obj(&t, "trade_data") else { continue };
            if i64_(&td, "country").map(|c| c as u64) != Some(b.country) {
                continue;
            }
            let side = match string(&td, "trade_type").as_deref() { Some("market_sell") => "sell", Some("market_buy") => "buy", _ => continue };
            b.market_orders.push(MarketOrderSpec { side: side.into(), resource: string(&td, "resource").unwrap_or_default(),
                                                   amount: i64_(&t, "amount").unwrap_or(0) });
        }
    }
```

- [ ] **Step 4: Run to verify they pass**

Run: `PATH=$HOME/.cargo/bin:$PATH cargo test -p game-controller --release`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add crates/game-controller/src/stellaris.rs
scripts/ci-commit.sh "feat(stellaris): tech-pick and market-order selection; monthly trades in the briefing" "Pure selection for the strategy actions: the first preferred tech offered in a field under 10% done (never swaps a preferred or started tech), and the add/remove diff between the save's monthly trades and the economy pillar's orders; the briefing lists our monthly trades from market.monthly_trades."
```

---

### Task 6: Screen steps for tech picks and market orders (Rust MCP tools + live calibration)

**Files:**
- Modify: `corpora/stellaris/manifest.toml` (new `[ui.tech]` and `[ui.market]` tables)
- Modify: `crates/game-controller/src/corpus.rs` (parse `ui` table into `GameManifest.ui: toml::Table` if not already generic)
- Modify: `crates/game-controller/src/stellaris.rs` (`pick_tech`, `sync_market` async fns)
- Modify: `crates/game-controller/src/mcp.rs` (tools `stellaris_pick_tech {prefer: [..]}`, `stellaris_market_sync {orders: [..]}`)
- Modify: `src/pilot/game.py` (`McpGame.pick_tech(prefer)`, `McpGame.market_sync(orders)`; `FakeStellaris` records them)
- Test: `tests/test_governor.py` (FakeStellaris contract), manual live check

**Interfaces:**
- Consumes: `choose_tech_pick`, `market_diff`, `MarketOrderSpec` (Task 5); `PauseDetector` (existing) for foreground/pause.
- Produces: `McpGame.pick_tech(prefer: list[str]) -> str` (text: "picked <tech> in <field>" | "nothing to pick: …"); `McpGame.market_sync(orders: list[dict]) -> str` ("added …; removed …" | "orders already match"); `FakeStellaris.pick_tech/market_sync` append `("pick_tech", prefer)` / `("market_sync", orders)` to `actions` and return `"ok"`.

- [ ] **Step 1: Live calibration (manual, game on the Theian test save, governor paused)**

With the game paused and in front: press `f4`; screenshot; record the swap-button centre of each field and the first option card centre and card pitch after pressing each swap button (as on 2026-09-26: engineering swap at image (229,331); options listed at x≈390, first card y≈125, next ≈190, ≈257). Close with `esc`. Open the market by clicking the energy icon at (48,10); click "Add new monthly trade" (382,156); record the dialog's Buy (≈816,311) / Sell (873,311) buttons, each resource icon (energy ≈820,335; the others by hovering), the amount `+` (855,388) and Add/Edit (863,452); click an existing order row and record its Cancel/Remove button. Write them to the manifest:

```toml
[ui.tech]   # verified 2026-09-26 on 4.5.1, 1568x882 image space
open_key = "f4"
swap = { physics = [229, 168], society = [229, 249], engineering = [229, 331] }
first_option = [390, 125]
option_pitch = 66
close_key = "esc"

[ui.market]
open_click = [48, 10]
add = [382, 156]
buy = [816, 311]
sell = [873, 311]
resources = { energy = [820, 335], minerals = [837, 335], food = [855, 335], alloys = [872, 335], consumer_goods = [820, 353], trade = [0, 0] }
plus = [855, 388]
confirm = [863, 452]
order_row_first = [370, 161]
order_row_pitch = 14
remove = [0, 0]
close_key = "esc"
```

Replace every calibrated value with what the screenshots show (the `[0, 0]` entries have to be measured; do not guess). Amount clicks: one `+` per unit (the dialog adds 10 with ctrl; use plain clicks up to 25, ctrl-click for 10s).

- [ ] **Step 2: Write the failing Python contract test**

```python
def test_fake_game_records_strategy_actions():
    g = FakeStellaris([briefing("2200.01.01")])
    assert g.pick_tech(["tech_habitat_1"]) == "ok"
    assert g.market_sync([{"side": "sell", "resource": "energy", "amount": 11}]) == "ok"
    assert ("pick_tech", ["tech_habitat_1"]) in g.actions and ("market_sync", [{"side": "sell", "resource": "energy", "amount": 11}]) in g.actions
```

Run: `.venv/bin/python -m pytest -q tests/test_governor.py -k strategy_actions -p no:cacheprovider` → FAIL.

- [ ] **Step 3: Implement the Python adapters**

```python
    # McpGame
    def pick_tech(self, prefer: list[str]) -> str:
        self.ensure_foreground()
        return self._checked(self.call("stellaris_pick_tech", prefer=prefer))

    def market_sync(self, orders: list[dict]) -> str:
        self.ensure_foreground()
        return self._checked(self.call("stellaris_market_sync", orders=orders))

    # FakeStellaris
    def pick_tech(self, prefer: list[str]) -> str:
        self.actions.append(("pick_tech", list(prefer)))
        return "ok"

    def market_sync(self, orders: list[dict]) -> str:
        self.actions.append(("market_sync", list(orders)))
        return "ok"
```

Add both to the `StellarisGame` protocol in `governor.py`.

- [ ] **Step 4: Implement the Rust tools**

In `stellaris.rs`:

```rust
fn ui_point(ui: &toml::Table, section: &str, key: &str) -> Result<(i32, i32)> {
    let v = ui.get(section).and_then(|s| s.get(key)).and_then(|p| p.as_array()).context(format!("manifest has no ui.{section}.{key}"))?;
    let x = v.first().and_then(|n| n.as_integer()).context("bad point")? as i32;
    let y = v.get(1).and_then(|n| n.as_integer()).context("bad point")? as i32;
    if (x, y) == (0, 0) { bail!("ui.{section}.{key} is not calibrated"); }
    Ok((x, y))
}

/// Pick the first preferred tech offered in a field under 10% done (screen: F4, swap, option card).
pub async fn pick_tech(client: &crate::client::AgentClient, pause: &PauseDetector, ui: &toml::Table,
                       research: &BTreeMap<String, Research>, prefer: &[String], cost: &dyn Fn(&str) -> Option<f64>) -> Result<String> {
    let Some(pick) = choose_tech_pick(research, prefer, cost) else { return Ok("nothing to pick: no preferred tech offered in a field that is free to change".into()) };
    pause.set_paused(client, true).await?;
    pause.close_menu(client).await?;
    let key = |k: &str| ui.get("tech").and_then(|s| s.get(k)).and_then(|v| v.as_str()).unwrap_or("").to_string();
    require_foreground(client).await?;
    client.key(&key("open_key"), 1).await?;
    tokio::time::sleep(std::time::Duration::from_millis(800)).await;
    let swap = ui.get("tech").and_then(|s| s.get("swap")).and_then(|s| s.get(&pick.field)).and_then(|p| p.as_array())
        .context("manifest ui.tech.swap is missing this field")?;
    let (sx, sy) = (swap[0].as_integer().unwrap_or(0) as i32, swap[1].as_integer().unwrap_or(0) as i32);
    require_foreground(client).await?;
    client.click(sx, sy, "left", 1).await?;
    tokio::time::sleep(std::time::Duration::from_millis(600)).await;
    let (fx, fy) = ui_point(ui, "tech", "first_option")?;
    let pitch = ui.get("tech").and_then(|s| s.get("option_pitch")).and_then(|v| v.as_integer()).unwrap_or(66) as i32;
    require_foreground(client).await?;
    client.click(fx, fy + pitch * pick.option_index as i32, "left", 1).await?;
    tokio::time::sleep(std::time::Duration::from_millis(500)).await;
    require_foreground(client).await?;
    client.key(&key("close_key"), 1).await?;
    Ok(format!("picked {} in {} (option {}); the next autosave confirms it", pick.tech, pick.field, pick.option_index + 1))
}
```

`sync_market` follows the same pattern: open the market (`open_click`), for each order to remove click `order_row_first + pitch*i` then `remove`; for each order to add click `add`, `sell`/`buy`, the resource point, `plus` `amount` times (with `ctrl` held via `client.key("ctrl+…")` is not supported for clicks: use plain clicks, capped at 25 by validation), then `confirm`; finally `close_key`. It returns `"added …; removed …"`. In `mcp.rs` add two tools next to `stellaris_directive`, loading `ui` from the corpus manifest, the briefing from `fetch_latest_save` + `brief_save`, and tech costs from the corpus tech records (`fields.cost`).

- [ ] **Step 5: Live check, then commit**

With the governor paused: run `./target/release/game-controller --corpus corpora/stellaris mcp` via the pilot's `McpGame` in a Python shell, call `pick_tech([...])` with a tech from the current offers, play one month, confirm the briefing's research shows it; call `market_sync([{"side":"sell","resource":"energy","amount":5}])`, play one month, confirm `market_orders` in the briefing; then `market_sync([])` removes it. Run `PATH=$HOME/.cargo/bin:$PATH cargo test -p game-controller --release` and the Python tests.

```bash
git add corpora/stellaris/manifest.toml crates/game-controller/src src/pilot/game.py src/pilot/governor.py tests
scripts/ci-commit.sh "feat(stellaris): tech picks and market orders as MCP tools" "stellaris_pick_tech and stellaris_market_sync carry out the strategy actions through the Technology and Market screens (positions calibrated in the manifest, 4.5.1), paused and in the foreground; verified live: a picked tech and a monthly sell order appeared in the next autosave and removal worked."
```

---

### Task 7: The governor carries out the actions and verifies them

**Files:**
- Modify: `src/pilot/governor.py` (`_carry_out_actions(b)` called at the end of `_decide`; misses per review)
- Test: `tests/test_governor.py` (append)

**Interfaces:**
- Consumes: `Governor.strategy` (Task 3), `game.pick_tech`, `game.market_sync` (Task 6), briefing `research` and `market_orders` (Task 5).
- Produces: events `strategy_action` `{kind: tech|market, result}`; `Governor._tech_misses: dict[str, int]` reset at each review.

- [ ] **Step 1: Write the failing tests**

```python
def test_decisions_carry_out_the_strategy_actions(setup):
    from pilot.strategy import Pillar
    s, log = setup
    calls = []
    game = FakeStellaris([briefing("2200.01.01"), briefing("2201.01.01")])
    g = Governor(s, game, log, model=decisions("keep"), role_models={"strategy": _strategist(calls)})
    g._review_strategy(briefing("2200.01.01"), "start of run")
    g.strategy.pillars["technology"] = Pillar(priority=3, stance="s", goals=["g"], prefer_techs=["tech_habitat_1"])
    g.strategy.pillars["economy"] = Pillar(priority=2, stance="s", goals=["g"], market=[{"side": "sell", "resource": "energy", "amount": 5}])
    g._carry_out_actions(briefing("2200.01.01"))
    assert ("pick_tech", ["tech_habitat_1"]) in game.actions
    assert ("market_sync", [{"side": "sell", "resource": "energy", "amount": 5}]) in game.actions


def test_a_tech_that_did_not_stick_is_not_retried_until_the_next_review(setup):
    from pilot.strategy import Pillar
    s, log = setup
    calls = []
    game = FakeStellaris([briefing("2200.01.01")])
    g = Governor(s, game, log, model=decisions("keep"), role_models={"strategy": _strategist(calls)})
    g._review_strategy(briefing("2200.01.01"), "start of run")
    g.strategy.pillars["technology"] = Pillar(priority=3, stance="s", goals=["g"], prefer_techs=["tech_habitat_1"])
    offered = {**briefing("2200.02.01"), "research": {"engineering": {"current": ["tech_mining_2", 5.0],
                                                                       "alternatives": ["tech_mining_2", "tech_habitat_1"]}}}
    g._carry_out_actions(offered)                  # picks
    g._carry_out_actions(offered)                  # still not researching it: a miss, no second click
    assert sum(1 for a in game.actions if a[0] == "pick_tech") == 1
```

- [ ] **Step 2: Run to verify they fail** — `.venv/bin/python -m pytest -q tests/test_governor.py -k "carry_out or did_not_stick" -p no:cacheprovider` → FAIL.

- [ ] **Step 3: Implement**

```python
    def _carry_out_actions(self, b: dict) -> None:
        """The strategy's player actions: preferred tech picks and monthly market orders (game paused)."""
        if not self.strategy:
            return
        tech = self.strategy.pillars.get("technology")
        prefer = [t for t in (tech.prefer_techs if tech else []) if self._tech_misses.get(t, 0) < 1]
        researching = {((r or {}).get("current") or [None])[0] for r in (b.get("research") or {}).values()}
        pending = getattr(self, "_pending_pick", None)
        if pending and pending not in researching:
            self._tech_misses[pending] = self._tech_misses.get(pending, 0) + 1
            self.log.emit("strategy_action", kind="tech", result=f"{pending} did not stick; skipped until the next review")
            prefer = [t for t in prefer if t != pending]
        self._pending_pick = None
        if prefer and not researching & set(prefer):
            try:
                res = self.game.pick_tech(prefer)
                self.log.emit("strategy_action", kind="tech", result=res)
                if res.startswith("picked") or res == "ok":
                    offered = [t for r in (b.get("research") or {}).values() for t in (r or {}).get("alternatives", [])]
                    self._pending_pick = next((t for t in prefer if t in offered), prefer[0])
            except Exception as e:  # noqa: BLE001 - actions never stop play
                self.log.emit("strategy_action", kind="tech", result=f"failed: {e}"[:300])
        econ = self.strategy.pillars.get("economy")
        desired = [o.model_dump() for o in (econ.market if econ else [])]
        if desired != (b.get("market_orders") or []):
            try:
                self.log.emit("strategy_action", kind="market", result=self.game.market_sync(desired))
            except Exception as e:  # noqa: BLE001
                self.log.emit("strategy_action", kind="market", result=f"failed: {e}"[:300])
```

Initialise `self._tech_misses: dict[str, int] = {}` in `__init__` and reset it in `_review_strategy`. Call `self._carry_out_actions(b)` at the end of `_decide` (after the directive is applied, game still paused).

- [ ] **Step 4: Run to verify they pass** — full suite, PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pilot/governor.py tests/test_governor.py
scripts/ci-commit.sh "feat(governor): carry out the strategy's tech picks and market orders" "After each decision the governor asks the controller to pick a preferred tech (when offered and the field is free) and to match the monthly market orders to the economy pillar; a pick that is not being researched at the next decision counts as a miss and is not retried until the next review."
```

---

### Task 8: Dashboard API: strategy, edit/pin, history, review now

**Files:**
- Modify: `src/pilot/dashboard.py` (routes near line 270; control actions near line 419)
- Modify: `src/pilot/governor.py` (`edit_pillar`, `unpin_pillar`, `request_review`)
- Test: `tests/test_governor.py` (append; use the existing aiohttp `TestClient` pattern from `test_responses_are_never_cached`)

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces:
  - `GET /api/strategy?campaign=<id>` → `{"current": {...}|null, "milestones": [{"pillar","metric","op","target","by","status"}], "history": [...]}`
  - control actions: `edit_pillar {pillar, fields}` (validated; sets `pinned=True, edited_by="human"`), `unpin_pillar {pillar}`, `review_strategy {}`
  - `Governor.edit_pillar(name: str, fields: dict) -> None`, `Governor.unpin_pillar(name) -> None`, `Governor.request_review() -> None`

- [ ] **Step 1: Write the failing tests**

```python
def test_human_pillar_edits_pin_and_win_over_a_running_review(setup):
    s, log = setup
    calls = []
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"), role_models={"strategy": _strategist(calls)})
    g._review_strategy(briefing("2200.01.01"), "start of run")
    g.edit_pillar("diplomacy", {"stance": "no federations", "goals": ["stay independent"]})
    assert g.strategy.pillars["diplomacy"].pinned and g.strategy.pillars["diplomacy"].edited_by == "human"
    g._role_objs["strategy"] = _strategist(calls, pin_diplomacy_to="join a federation")
    g.__dict__.pop("_agents", None)
    g._review_strategy(briefing("2201.01.01"), "scheduled")
    assert g.strategy.pillars["diplomacy"].stance == "no federations"
    g.unpin_pillar("diplomacy")
    assert not g.strategy.pillars["diplomacy"].pinned
    with pytest.raises(ValueError):
        g.edit_pillar("happiness", {"stance": "x"})


def test_strategy_api_returns_current_milestones_and_history(setup, tmp_path):
    import asyncio

    from aiohttp.test_utils import TestClient, TestServer

    from pilot.dashboard import make_app
    from pilot.telemetry import Telemetry
    s, _ = setup
    tel = Telemetry(tmp_path / "t.sqlite")
    log = EventLog(s.runs_dir, "rs", s.model, telemetry=tel)
    calls = []
    g = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"), role_models={"strategy": _strategist(calls)})
    log.set_campaign("stellaris", "c1", "Test")
    g._review_strategy(briefing("2200.01.01"), "start of run")

    async def go():
        async with TestClient(TestServer(make_app(g, s.runs_dir, tel))) as c:
            r = await c.get(f"/api/strategy?campaign={log.campaign_id}")
            body = await r.json()
            assert body["current"]["focus"] == "grow" and len(body["history"]) == 1
            r = await c.post("/control", json={"action": "edit_pillar", "pillar": "economy", "fields": {"stance": "save energy"}})
            assert r.status == 200 and g.strategy.pillars["economy"].pinned
            r = await c.post("/control", json={"action": "review_strategy"})
            assert r.status == 200 and g.review_requested == "requested from the dashboard"
    asyncio.run(go())
```

- [ ] **Step 2: Run to verify they fail** → FAIL.

- [ ] **Step 3: Implement**

Governor:

```python
    def edit_pillar(self, name: str, fields: dict) -> None:
        """The human's edit: validated, pinned, recorded as a new version."""
        from .strategy import PILLARS, Pillar
        if name not in PILLARS:
            raise ValueError(f"unknown pillar {name!r}")
        if self.strategy is None:
            raise ValueError("no strategy yet")
        cur = self.strategy.pillars[name].model_dump()
        allowed = {"stance", "goals", "milestones", "prefer_techs", "market", "priority"}
        new = Pillar.model_validate({**cur, **{k: v for k, v in fields.items() if k in allowed}, "pinned": True, "edited_by": "human"})
        s = self.strategy.model_copy(update={"pillars": {**self.strategy.pillars, name: new}, "reason": f"human edit: {name}"})
        errs = validate(s, previous=None, tech_ids=self._tech_ids(), idle=idle_resources({}) | {o.resource for o in new.market},
                        income={o.resource: o.amount * 5 for o in new.market})
        if errs:
            raise ValueError("; ".join(errs))
        self._set_strategy(s, self.log.state.game_date or "", f"human edit: {name}", "human")

    def unpin_pillar(self, name: str) -> None:
        if self.strategy is None or name not in self.strategy.pillars:
            raise ValueError(f"unknown pillar {name!r}")
        p = self.strategy.pillars[name].model_copy(update={"pinned": False})
        s = self.strategy.model_copy(update={"pillars": {**self.strategy.pillars, name: p}, "reason": f"unpinned: {name}"})
        self._set_strategy(s, self.log.state.game_date or "", f"unpinned: {name}", "human")

    def request_review(self) -> None:
        self.review_requested = "requested from the dashboard"
        self.log.emit("instruction", text="Strategy review requested")
```

A running review already reloads `self.strategy` before validating (`keep_pinned(r.strategy, self.strategy)` reads the latest version, which includes a pin made while the model was thinking), so the human edit wins.

Dashboard (`make_app`): add `web.get("/api/strategy", api_strategy)`:

```python
    async def api_strategy(request):
        from .strategy import Strategy, milestone_status
        cid = request.query.get("campaign") or (log.campaign_id if log else "")
        if tel is None or not cid:
            return web.json_response({"current": None, "milestones": [], "history": []})
        cur = await asyncio.to_thread(tel.latest_strategy, cid)
        rows = await asyncio.to_thread(tel.metrics_rows, cid)
        hist = await asyncio.to_thread(tel.strategy_history, cid)
        ms = []
        if cur:
            s = Strategy.model_validate({k: v for k, v in cur.items() if k != "reason"})
            today = rows[-1]["date"] if rows else "2200.01.01"
            for name, pl in s.pillars.items():
                for m in pl.milestones:
                    ms.append({"pillar": name, **m.model_dump(), "status": milestone_status(m, rows, today)})
        return web.json_response({"current": cur, "milestones": ms, "history": hist})
```

(`tel` is the telemetry instance already passed to `make_app`.) Control actions next to `set_roles`:

```python
        elif action == "edit_pillar" and hasattr(pilot, "edit_pillar"):
            try:
                pilot.edit_pillar(str(body.get("pillar", "")), dict(body.get("fields") or {}))
            except ValueError as e:
                raise web.HTTPBadRequest(text=str(e)) from e
        elif action == "unpin_pillar" and hasattr(pilot, "unpin_pillar"):
            try:
                pilot.unpin_pillar(str(body.get("pillar", "")))
            except ValueError as e:
                raise web.HTTPBadRequest(text=str(e)) from e
        elif action == "review_strategy" and hasattr(pilot, "request_review"):
            pilot.request_review()
```

and add `edit_pillar|unpin_pillar|review_strategy` to the error message list and `"edit_pillar", "unpin_pillar", "review_strategy"` to `log.state.info["controls"]`.

- [ ] **Step 4: Run to verify they pass** — full suite PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pilot tests
scripts/ci-commit.sh "feat(dashboard): strategy API with pillar edit, pin and review now" "GET /api/strategy returns the current strategy, milestone status and version history; control actions edit_pillar (validated, pins it), unpin_pillar and review_strategy; a human edit made during a review is kept."
```

---

### Task 9: Dashboard UI: Strategy tab, Settings role, chart marks, off-frame tag

**Files:**
- Modify: `src/pilot/static/dashboard.html` (tab bar near line 351: rename Plan → Strategy; `renderPlan` → `renderStrategy`; decisions list tag; chart review marks)
- Test: headless render (Playwright script in the scratchpad), no committed test

**Interfaces:**
- Consumes: `/api/strategy` (Task 8), control actions `edit_pillar`, `unpin_pillar`, `review_strategy`; decision traces with `off_frame`.

- [ ] **Step 1: Implement the tab**

Replace the Plan tab button with `Strategy` (`data-tab="strategy"`, panel `tab-strategy`). `renderStrategy(data)` renders: a header line `Focus: … · Ranking: defend > …` (use a comma list, not a middle dot) and `Last review: <date>, <trigger>, <model>`; then one `<article class="pillar">` per pillar in priority order with the pillar name and priority, a `pinned` tag, the stance, goals as a list, milestones as rows `metric op target by <date>` with a status mark (`met` good, `on_track` ink, `at_risk` warn, `missed` bad — colour plus the word, never colour alone), actions (`Prefers: …`, `Market: sell energy 5/month`), and buttons `Edit` / `Unpin`. `Edit` swaps the card for a small form (stance textarea, goals textarea one per line, priority number) that posts `{"action":"edit_pillar","pillar":…, "fields":{…}}` to `/control` and re-renders. Below: `<details><summary>History (N versions)</summary>` with `date, trigger, model, reason` rows. A `Review strategy now` button posts `review_strategy` and disables itself until the next `strategy` or `strategy_review` event arrives over SSE. Load `/api/strategy?campaign=…` in `loadCampaignData` and on SSE events `strategy` / `strategy_review`.

- [ ] **Step 2: Decisions and chart**

In `renderDecisions`, when `d.off_frame` (from the decisions API; add `json_extract(trace,'$.off_frame') AS off_frame` to the `/api/decisions` query), add `<span class="tag bad">off-frame</span>` after the trigger. In `renderChart`, draw a small diamond on the directive lane at each history entry's month (history from the strategy data), with `<title>Strategy review: <trigger></title>`.

- [ ] **Step 3: Settings**

The role list comes from `/api/models` `role_meta`, so the `strategy` role appears automatically; check its help text shows under the role buttons.

- [ ] **Step 4: Headless check**

Run a Playwright script (scratchpad) against `http://127.0.0.1:8780/` with `/control` routed to a stub: open the Strategy tab, screenshot, click `Edit` on a pillar, submit, confirm the stub received `edit_pillar`, open History, open Settings → Models → Strategy. Expected: no console errors; screenshots show the pillars in priority order with milestone marks.

- [ ] **Step 5: Commit**

```bash
git add src/pilot/static/dashboard.html src/pilot/dashboard.py
scripts/ci-commit.sh "feat(dashboard): Strategy tab with pillars, milestones, edit and pin, history, review now" "The Plan tab becomes Strategy: pillars in priority order with stance, goals, milestones and their status, actions, pinned tags, inline edit (pins) and unpin, version history and a review-now button; off-frame decisions are tagged and strategy reviews are marked on the chart. Rendered headless without console errors."
```

---

### Task 10: Docs, deploy and live evaluation

**Files:**
- Modify: `README.md`, `AGENTS.md` (§10), `ARCHITECTURE.md`, `corpora/stellaris/pilot.md` (decision rules: the frame), `corpora/stellaris/strategy.md` (§9 note: directives follow the strategy frame), `plan.md`, `issues.md`

- [ ] **Step 1: Update the docs** — describe the strategy layer (pillars, Strategist role, triggers, frame, actions, dashboard tab) where the retrospective and plan were described; `pilot.md` tells the decision model to choose within the frame and to cite an urgent line when it does not; add plan.md items (checked only after the live run below) and record any live issues in issues.md.

- [ ] **Step 2: Full verification** — `scripts/ci.sh` (must print `CI OK`).

- [ ] **Step 3: Deploy** — `systemctl --user restart game-pilot-view.service game-pilot.service` with the Theian test save running; confirm in the activity feed: a `strategy` event at start (the first run on a campaign without a strategy), decisions showing `STRATEGY FRAME` in their prompt, `strategy_action` events.

- [ ] **Step 4: Live evaluation (~30 in-game years)** — from telemetry: count strategy versions (expect well under the 16 in 37 years seen with the free-text plan), list milestone statuses, confirm directives stay within the top of the ranking except tagged off-frame decisions, and confirm at least one preferred tech was researched after a pick. Write the results to `games/stellaris-spike/journal.md`.

- [ ] **Step 5: Commit**

```bash
git add README.md AGENTS.md ARCHITECTURE.md corpora/stellaris/pilot.md corpora/stellaris/strategy.md plan.md issues.md games/stellaris-spike/journal.md
scripts/ci-commit.sh "docs: strategy layer; live evaluation" "Docs describe the pillar strategies, the Strategist role, review triggers, the decision frame, the tech-pick and market actions and the Strategy tab; journal records the 30-year live evaluation."
```
