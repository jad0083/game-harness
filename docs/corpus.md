# Game corpora

`corpora/<game>/` is the only place game knowledge lives; the Rust controller is game-agnostic.

```
corpora/<game>/
  manifest.toml   hotkeys, known screens (template, region, action), macros, UI points — hand-verified
  templates/      reference crops that identify known screens
  res/            overlays for other screen sizes (res/<W>x<H>.toml, res/map.toml)
  strategy.md     playbook for the model, also chunked for search
  pillars.toml    the strategy layer's pillars, weights, metrics and action limits (Stellaris)
  directives.toml governor directives (Stellaris)
  data/           GENERATED records, one <kind>.json each — never edit by hand
  docs/*.md       reference prose with Source:/License: headers, chunked for search
  learned/        the last exported copy of what the pilot learned (`pilot export`; not written at run time)
```

The live learned overlay is `<data>/learned/<game>/`, generated from the pilot's store; the controller
reads it in place of `learned/` (`--learned`).

`corpus search` returns ids and snippets; `corpus get <id>` returns one record or chunk (see
[cli.md](cli.md)). Records are generated from the game's own definition files, not the wiki, so
costs and prerequisites match the installed version; when the wiki disagrees, the records win.

## Galactic Civilizations IV

130 techs, 528 improvements, 66 executive orders, 203 policies, 355 ship components, 167 starbase
modules and 994 events (game 4.1.1), from `scripts/extract-galciv4.py`. To regenerate after a patch,
copy `<install>\Data\Gameplay` and `<install>\Data\English\Text` from the PC (the agent's read-only
`/files` access or `scripts/receive-file.py`) and run:

```bash
python3 scripts/extract-galciv4.py <folder-with-Gameplay-and-Text> --game-version 4.1.1
```

Only techs, improvements and orders have name lookups; reach the rest with `search` + `get` (e.g.
`event:precursor_probe`, whose `choices` list each button's exact outcome). `data/_meta.json`
records the game version, generator commit and counts.

## Stellaris

9,152 records from the game's files (`scripts/extract-stellaris.py`): techs, policies, edicts,
buildings, districts, traditions, ascension perks, civics and events with every option; 46 wiki
reference docs; the governor directives and postures (`directives.toml`) and the Governor Bridge mod (`corpora/stellaris/mod/`, v2: AI budgets and economic-plan subplans gated on directive and posture flags, and the monthly naval-capacity export).
Autosaves are read by `crates/game-controller/src/stellaris.rs`.

## Civilization VI

1,783 records for game 1.0.12.68 with the Gathering Storm rules and every owned DLC (no scenarios,
no game modes), from `scripts/extract-civ6.py`: 29 kinds — civ 50, leader 77, agenda 113,
city_state 48, unit 144, building 85, wonder 53, district 36, improvement 59, tech 77, civic 61,
policy 140, government 13, great_person 212, belief 59, governor 8, promotion 145, resource 54,
feature 50, terrain 17, project 38, emergency 15, resolution 19, dedication 12, moment 143, era 9,
victory 7, random_event 34, alliance 5 (about 1.1 MB). Civ VI has no single rules file: the
extractor rebuilds the game's rules database from the base XML plus each DLC's modinfo
`UpdateDatabase` actions (criteria, `LoadOrder`, file priority, Row/Replace/Update/Delete with
cascading deletes), then renders records with the game's own en_US text. Ids are `<kind>:<key
without prefix>` (`tech:writing`, `unit:roman_legion`, `great_person:hypatia`) and the game key is
always an alias (`corpus get` by id; `search "TECH_WRITING"` finds it). Unique units, buildings,
districts and improvements name their civilization or leader in `unique_to`. The record contract,
the layering rules and the check against the game's own debug database are in
`corpora/civ6/data/README.md`. `data/_adjacency.json` (not a record file) keeps the district
adjacency rules as data (`Adjacency_YieldChanges`, `District_Adjacencies`, `DistrictReplaces`,
placement flags, resource classes, natural wonders) for the placement scorer
(`src/pilot/civ6_placement.py`).

```bash
# copy Base/Assets/Gameplay/Data, Base/Assets/Text/en_US and DLC/*/{*.modinfo,Data,Text} once,
# slowly (not a bulk parallel read of the PC's agent), into incoming/civ6/, then:
python3 scripts/extract-civ6.py incoming/civ6 --game-version 1.0.12.68
python3 scripts/fetch-civ6-wiki.py                   # the 13 Civilization Wiki docs (MediaWiki API)
./target/release/game-controller --corpus corpora/civ6 corpus get district:campus
```

`strategy.md` is a first playbook (opening, district adjacency, victory paths, buying with gold
and faith, diplomacy), grounded in the records and cited sources; nothing in it has been verified
in play yet. `docs/` holds 13 Civilization Wiki pages (CC BY-SA 3.0, Firaxis "Civilopedia entry"
sections removed), the civ6-mcp agent playbook (MIT, adjacency table corrected for Gathering
Storm), CivBench's playbook appendix (CC BY 4.0) and `links.md` for sources that may only be
linked (official Civilopedia, CivFanatics, Zigzagzigal, the modding wiki). The manifest has only
the window title so far (`Sid Meier's Civilization VI`, matching both the DX11 and DX12 builds):
no hotkeys or screens until they are verified in play, and no pillars or live metrics until the
game can be read (tuner or saves).

## Other screen sizes

Positions and templates are measured at 3840x2160. A PC with another size sets `GAME_RESOLUTION`
(e.g. `2560x1440`); the controller then merges `res/<W>x<H>.toml` over the manifest. Its UI points
come from `scripts/res-map.py corpora/<game> <W>x<H> --write`: one UI scale per size in
`res/map.toml`, each UI group pinned to the top-left corner or the screen centre (verified within
1–2 px at 1440p). Screen templates are captured again at that size with
`scripts/play/capture-template.py`.
