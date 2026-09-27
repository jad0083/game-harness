# Game pillars: the strategy layer's guardrails come from each game's corpus

Date: 2026-09-26 · Status: approved design (option 1), user asked to proceed to deployment

## Why

The strategy layer (spec `2026-09-26-strategy-layer-design.md`) hard-codes Stellaris: seven pillar ids,
their directive mapping, the milestone metrics, and the two actions with their limits live in
`src/pilot/strategy.py`, and the dashboard copies the directive map. Other games have other pillars
(Civilization VI: science, culture, faith, military, expansion, economy, diplomacy), so adding a game
would mean editing the strategy code. The first live reviews also showed two problems the fixed shape
causes: Claude models could not fill `pillars: dict[str, Pillar]` (the tool schema has no named
fields, so Opus returned `{}` twice), and the accepted strategy had no milestones at all.

## Intent (agreed)

Each game defines its pillars in its corpus. Everything downstream uses them as guardrails: what the
Strategist may write, how it is validated, what a decision may choose and what counts as off-frame,
which actions the harness carries out, which metrics milestones may use, and what the dashboard shows.
Adding a game's strategy layer = a corpus file plus that game's action tools; no strategy-code change.
Stellaris behaves exactly as today after the move.

## 1. The pillars file: `corpora/<game>/pillars.toml`

```toml
[strategy]
min_milestones_top = 3          # each of the top-N priority pillars needs >= 1 milestone
metric_aliases = { "rank:military" = "rank:military_power", military = "military_power" }

[metrics]                        # names milestones may use; rank metrics are 1 = best
names = ["systems", "colonies", "pops", "techs_known", "military_power", "economy_power",
         "tech_power", "rank:systems", ...]

[pillars.economy]
label = "Economy"
description = "Income, deficits, stockpiles and trade."
directive = "consolidate_economy"   # optional: the directive this pillar ranks
actions = ["market"]                # optional: action kinds this pillar may carry

[actions.market]                    # per-action limits; the harness hook for the kind carries it out
max_items = 1
resources_from_manifest = "ui.market.resources"
amount_max = 25
sell_income_share = 0.2
sell_requires_idle = true

[actions.tech]
field = "prefer_techs"
max_items = 6
ids_from_corpus = "tech"
```

Pillar order in the file is the display fallback; priorities come from the Strategist. A pillar may
have no directive (government, society in Stellaris) and no actions. Unknown keys in the file are an
error at load time (fail fast, clear message naming the key).

## 2. Code

- `src/pilot/pillars.py` (new): `PillarSpec` (pillars with label, description, directive, actions;
  metrics and aliases; action limits; `min_milestones_top`) loaded and validated from the corpus by
  `load_pillars(corpus_dir)`; cached per corpus. `Settings`/`Governor` load it for the game.
- `strategy.py` becomes game-agnostic: `Strategy.pillars` stays `dict[str, Pillar]` as stored data, but
  every function takes the spec — `validate(s, spec, ...)`, `ranking(s, spec)`, metric checks and aliases
  from the spec, action checks per `spec.actions`. The Stellaris constants move to the pillars file.
  Market and tech rules become generic action checks driven by the limits (resources list, amount max,
  income share, idle requirement, id source).
- Strategist output schema is generated from the spec: a pydantic model with one named optional field
  per pillar id (`economy: PillarOut | None`, ...) so every provider sees named properties; it is
  converted to `Strategy` after the call. Pillar fields that carry an action exist only on pillars that
  declare it. The prompt lists pillar ids with labels and descriptions, metric names, and per-pillar
  actions with their limits, all from the spec.
- Validation adds: each of the top `min_milestones_top` pillars has at least one milestone.
- Decisions: the frame and off-frame check use `ranking(s, spec)`; a decision may pick a directive only
  from the ranking or `keep` (anything else is off-frame and must cite an urgent line — unchanged rule,
  now spec-driven).
- Actions: `_carry_out_actions` runs an action only when the spec declares it for that pillar, through a
  per-game hook table (`{"tech": game.pick_tech, "market": game.market_sync}` for Stellaris); a game
  without a hook for a declared action logs "not supported" once and skips it.
- Human edits: editable fields are the pillar's generic fields plus its declared action fields.
- Dashboard: `/api/strategy` includes the spec (ids, labels, descriptions, directives, actions); the
  Strategy tab renders labels and the ranking from it (the copied `DIRECTIVE_OF` is removed) and shows
  edit fields per declared action.
- Rust keeps its own tool validation (market resources from the manifest, amount 1..25); a test keeps
  the Stellaris pillars file's limits equal to Rust's.

## 3. Migration

`corpora/stellaris/pillars.toml` carries exactly today's seven pillars, directives, metrics, aliases and
limits (1 market order, 25, 20%, idle-only, techs <= 6). Stored strategies stay valid (same pillar ids).
A campaign's stored strategy whose pillar ids don't match the spec (a future rename) is treated as no
strategy (review at start) and logged.

## 4. Failures

- Missing or invalid pillars file for a game with the strategy layer: the governor starts without the
  strategy layer (decisions as before the layer) and logs one clear error naming the file and key.
- Everything else as the strategy-layer spec §4.

## 5. Testing

- Loader: valid file; unknown key; directive naming a non-existent directive (checked against
  `directives.toml`); action without limits; metric alias to an unknown metric.
- Schema: generated model has one named field per pillar; a Claude-style answer with named fields
  converts to a valid Strategy; the JSON schema has no `additionalProperties`-only object for pillars.
- A second, synthetic game spec (3 pillars, no actions) runs a governor review + decision end to end
  with FakeStellaris-style fakes: ranking, frame, off-frame, validation all follow the synthetic spec.
- Stellaris: every existing strategy test passes unchanged in behaviour (the file reproduces today).
- Min milestones: a strategy without milestones on the top 3 is rejected with a clear reason.
- Dashboard: Strategy tab renders the synthetic spec's labels headless, no console errors.
- Live: redeploy on the Theian campaign; a review succeeds with Claude and with Gemini; milestones present.

## Out of scope

Civ VI's own pillars file and hooks (next project); changing directives themselves.
