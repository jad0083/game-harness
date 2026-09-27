# Generated game data

Files in this directory are **generated** from the game's own gameplay XML and en_US text by
`scripts/extract-civ6.py` and must never be edited by hand. Regenerate after a game patch or a new
DLC:

```bash
# a copy of the install's data and text, same layout as the install (not committed):
#   incoming/civ6/Base/Assets/Gameplay/Data/**   incoming/civ6/Base/Assets/Text/en_US/**
#   incoming/civ6/DLC/<pack>/<pack>.modinfo       incoming/civ6/DLC/<pack>/Data/*.{xml,sql}
#   incoming/civ6/DLC/<pack>/Text/**              (en_US files are enough)
python3 scripts/extract-civ6.py incoming/civ6 --game-version 1.0.12.68     # ~2 s
```

The PC's agent serves the install read-only (`civ6_install` root), but copy the files once and
slowly: about 1,070 files, 18.7 MB. Parallel bulk reads kept the agent busy long enough to stall
another game's governor (issues.md, 2026-09-26).

Generated for **1.0.12.68** (Gathering Storm ruleset `RULESET_EXPANSION_2`, every owned DLC, no
scenarios, no game modes), 2026-09-26: civ 50, leader 77, agenda 113, city_state 48, unit 144,
building 85, wonder 53, district 36, improvement 59, tech 77, civic 61, policy 140, government 13,
great_person 212, belief 59, governor 8, promotion 145, resource 54, feature 50, terrain 17,
project 38, emergency 15, resolution 19, dedication 12, moment 143 (those worth era score), era 9,
victory 7, random_event 34, alliance 5 — 1,783 records, about 1.1 MB.

## How the rules database is built

The game has no single rules file: it builds an SQLite database at load time. The extractor does
the same, in memory:

1. `Base/Assets/Gameplay/Data/Schema/01_GameplaySchema.sql` and `02_AddTriggers.sql`, the schema
   XML files, then every base data XML file in name order.
2. Every non-scenario pack's `<InGameActions><UpdateDatabase>` whose `criteria` pass for the
   ruleset: `GameCoreInUse` (Expansion2 for Gathering Storm), `RuleSetInUse`, `LeaderPlayable`
   (the ruleset's player list), `ModInUse` (installed packs), `ConfigurationValueMatches` (game
   modes; only with `--modes`); `any="1"` means OR. Actions run in `LoadOrder` order (Gathering
   Storm's core is -100, most packs 0, some 100), then by pack folder name; inside an action,
   files with a higher `Priority` load first (schema, then removals, then data).
3. XML operations: `<Row>` insert, `<Replace>` insert-or-replace, `<InsertOrIgnore>`, `<Update>`
   with `<Where>`/`<Set>`, `<Delete>` with column filters (an empty `<Delete/>` clears the table).
   An empty attribute or element is NULL and element text is trimmed, as in the game. Foreign keys
   are deferred inside one transaction, so deleting a `Types` row cascades (Gathering Storm deletes
   and re-adds whole kinds this way).
4. Text follows the same `<UpdateText>` actions; only en_US rows are kept.

The run stops without writing anything when an operation fails, a row names an unknown table or
column, or a data or text file does not parse (after a patch renames a column, say); `--lenient`
writes anyway and lists the problems first in `_meta.json` `warnings`.

Checked against the game: with `--no-dlc --ruleset RULESET_STANDARD --check-against
DebugGameplay.sqlite` (the base-ruleset database the game wrote on the PC), all 318 tables match
row for row except the 741 effect types the engine registers itself (`GameEffects`,
`GameEffectArguments`, `Types`) and two number-formatting differences (`.25` vs `0.25`, `05` vs
`5`). The Gathering Storm build matches
the published totals (50 civilizations, 77 leaders after the Leader Pass) but has **not** been
compared with a Gathering Storm `DebugGameplay.sqlite` yet (the game writes one only after a GS
game is loaded with `CopyDatabasesToDisk 1`). `_meta.json` lists the files a modinfo names that do
not exist in the install (the game skips them too) and the foreign-key rows left dangling.

## Contract

- `<kind>.json` — a JSON array of records for one kind. The file stem is the kind.
- `_adjacency.json` — the district adjacency rules as data for the placement scorer
  (`src/pilot/civ6_placement.py`, levers design ruling 30): `Adjacency_YieldChanges` and
  `District_Adjacencies` rows with the game's column names (NULL, 0 and false columns left out),
  `DistrictReplaces` (unique district -> the district it replaces), `Districts` (placement flags of
  the districts that need a tile), `District_ValidTerrains`, `ResourceClasses` and `NaturalWonders`.
- `_meta.json` — `{ "game_version", "ruleset", "generated_at", "generator": "<script @ commit>",
  "source": "xml-layered", "counts": {kind: n}, "dlc": [pack folders], "dlc_names", "modes",
  "localisation_keys", "operations", "check_against", "warnings" }`. Files starting with `_` are not
  loaded as records.

Record shape (the loader rejects a record without a `name` and any duplicate `id`):

```json
{
  "id": "unit:roman_legion",            // <kind>:<type key without its prefix, lower case>
  "name": "Legion",                     // en_US name
  "aliases": ["UNIT_ROMAN_LEGION"],     // the game's type key, always
  "summary": "Unique to Rome, replaces Swordsman; 40 strength, 2 moves, cost 110; requires Iron Working.",
  "fields": {"unique_to": "Rome", "replaces": "Swordsman", "combat": 40, "resource_cost": "10 Iron", "...": "..."}
}
```

Conventions:
- Values name things by their English name, not their key. Icons are turned into words
  (`[ICON_Science]` -> "Science", dropped when the next word already says it); placeholders the UI
  fills at run time become `[CivName]` or `N`, never raw braces.
- **Unique items** carry `unique_to` ("Rome", "Teddy Roosevelt (Rough Rider) (America)" for a
  leader's unique, "Nan Madol (city-state suzerain)") and `replaces`; unlock lists mark them too
  ("Legion (unit, unique: Rome)"), so a generic unlock is never mistaken for your own.
- **Effects** use the game's own text first (`LOC_*_DESCRIPTION`, government bonus text, policy
  text); then `ModifierStrings` templates with their `ModifierArguments` filled in (great people:
  "Instantly builds a Library in this district. Libraries provide +1 Science."); a few argument-only
  effects get a plain phrase ("+1 Governor Title", "+2 Envoy(s)"); only then a compact line
  `effect(args) on collection [if requirements]`, capped at 200 characters. Great writers, artists
  and musicians list their Great Works instead; prophets and others with no action text show their
  unit's description.
- Adjacency is rendered from `Adjacency_YieldChanges` columns ("+1 Science per 2 adjacent
  districts", "+2 Gold per adjacent River or Harbor"), not from the text templates.
- `purchase` is `gold`, `faith` or `none`; districts and wonders cannot be bought. Costs are
  standard-speed production; read live purchase prices from the game.

Fields per kind (only non-empty ones are written):

| Kind | Fields |
|---|---|
| civ | ability, uniques, leaders, start_bias, dlc |
| leader | civ, ability, uniques, agenda, ai_traits, ai_favours (AI favoured techs, civics, wonders, yields), dlc |
| agenda | historical_for, random, description |
| city_state | type, suzerain_bonus, unique_improvement, dlc |
| unit | unique_to, replaces, class, domain, combat, ranged, range, bombard, anti_air, moves, sight, cost, purchase, must_purchase, maintenance, resource_cost, resource_upkeep, requires, upgrades_to, obsolete_with, can_train, charges, description |
| building | unique_to, replaces, district, cost, maintenance, yields, housing, amenities, citizen_slots, great_person_points, great_work_slots, power_required, requires, requires_buildings, exclusive_with, purchase, must_purchase, internal_only, effect |
| wonder | era, cost, requires, placement, district, yields, great_person_points, great_work_slots, housing, amenities, effect |
| district | unique_to, replaces, cost, cost_progression, requires, requires_population, adjacency, buildings, housing, amenities, appeal, great_person_points, trade_route_yields, citizen_yields, one_per_city, one_per_river, no_adjacent_city_center, coast, effect |
| improvement | unique_to, yields, adjacency, valid_on, requires, built_by, bonus_yields, tourism, housing, appeal, one_per_city, buildable, effect |
| tech / civic | era, cost, prerequisites, leads_to, eureka / inspiration (trigger text and %), unlocks, effects, obsoletes_units, description, repeatable |
| policy | slot, requires, obsoleted_by, age (Dark/Golden Age only), effect |
| government | tier, requires, slots, inherent_bonus, legacy_bonus |
| great_person | class, era, charges, action, action_modifiers (compact fallback), passive, action_requires, great_works |
| belief | class, effect |
| governor | title, base_ability, promotions ("Tier N Name: text (after X)"), assign_to_city_state, description |
| promotion | class, tier, requires, effect |
| resource | class, yields, improvement, revealed_by, amenities, accumulation, power, harvest |
| feature / terrain | yields, adjacent_yields, movement_cost, defense, appeal, natural_wonder, impassable, removable, fresh_water, description |
| project | district, cost, requires, requires_building, space_race, yield_conversion, great_person_points, max_per_player, effect |
| emergency | trigger, description, goal, duration, hostile, buffs_while_active, rewards |
| resolution | target, earliest_era, latest_era, option_a, option_b |
| dedication | golden_age, normal_age, dark_age, eras |
| moment | era_score, eras, obsolete_era, description |
| era | order, min_turns, max_turns, great_person_base_cost, warmonger_points, description |
| victory | how_to_win, blurb, enabled_by_default |
| random_event | severity, effect, yields_after, climate_change_points, description, long_description |
| alliance | effects (per level), description |

Game modes (Heroes & Legends, Secret Societies, Monopolies and Corporations, Apocalypse, Dramatic
Ages, Barbarian Clans, Zombie Defense, Tech and Civic Shuffle) change units and rules: a campaign
should turn them off, or regenerate with `--modes <names>` (matched against each criterion's
`ConfigurationValueMatches` text) and record that in `_meta.json`.
