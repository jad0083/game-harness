# Generated game data (planned — nothing generated yet)

Files in this directory will be **generated** from the game's own script files by
`scripts/extract-stellaris.py` (not written yet) and must never be edited by hand. Regenerate
after every game patch:

```bash
python3 scripts/extract-stellaris.py <folder containing common/, events/ and localisation/> --game-version <x.y.z>
```

The folders are `<install>\common`, `<install>\events` and `<install>\localisation\english` on the
Windows PC (Steam: `steamapps\common\Stellaris`). The plan is for the extractor to read the
install through the Windows agent; `scripts/receive-file.py` (a zip over the LAN) is the fallback.
The script files themselves are not committed (Paradox's data). Record the game version with
`--game-version`, and record which DLC are present, because many definitions are gated on
`has_*_dlc` triggers.

Verified on the user's PC (2026-09-25): Stellaris "Cygnus v4.5.1 (358e)", Steam, launched
straight from Steam PLAY (no Paradox Launcher step). 13 DLC folders in the install: plantoid,
leviathans, horizon_signal, utopia, synthetic_dawn, apocalypse, humanoids, megacorp,
ancient_relics, lithoids, federations, necroids, nemesis. The 4.5 welcome screen says 4.5 breaks
save and mod compatibility (Pop Group / Faction changes), so the extractor and save parser must
target 4.5 files, not older examples.

## Source format

Definitions are Clausewitz/PDX script (`key = value`, `key = { ... }`, `#` comments,
`@variable` constants from `common/scripted_variables/` and the top of each file, `yes`/`no`
booleans, comparison operators `<`, `>`, `<=`, `>=`). Display strings come from
`localisation/english/*_l_english.yml` (`key:0 "text"`, with `$other_key$` references,
`£icon£` icons and `§X...§!` colour codes to strip). A definition's name is the localisation of
its key; its description is usually `<key>_desc`.

## Contract

Same as `corpora/galciv4/data/README.md`:

- `<kind>.json` — a JSON array of records for one entity kind. The file stem is the kind.
- `_meta.json` — `{ "game_version": "...", "generated_at": "...", "generator": "<commit>",
  "counts": {"<kind>": n, ...}, "dlc": [...] }`. Files starting with `_` are not loaded as records.

Record shape (extra keys go under `fields`; the extractor decides which fields each kind has):

```json
{
  "id": "technology:tech_space_construction",   // optional; defaults to "<kind>:<slug of name>"
  "name": "Space Construction",                 // required (localised)
  "aliases": ["tech_space_construction"],       // optional; the script key is a useful alias
  "summary": "Unlocks Outposts ...",            // optional one-liner shown in search results
  "fields": {                                   // optional, rendered in order by corpus_get
    "area": "engineering",
    "tier": 0,
    "cost": "...",
    "prerequisites": ["..."],
    "unlocks": ["..."]
  }
}
```

The loader rejects a record without a `name` and any duplicate `id`, so a bad extract fails at
startup rather than during play. Keep the script key as an alias: the companion mod and the
save file refer to things by key, the UI and the model by localised name.

## Planned kinds and their source folders

| Kind | Source (under the install folder) | Fields worth keeping |
|---|---|---|
| `technology` | `common/technology/*.txt` | area, category, tier, cost, weight modifiers, prerequisites, is_rare/is_dangerous, what it unlocks (reverse lookup over the kinds below) |
| `building` | `common/buildings/*.txt` | category, cost, upkeep, build time, jobs/modifiers, upgrade chain, prerequisites, potential/allow conditions (summarised) |
| `district` | `common/districts/*.txt` | cost, upkeep, housing, jobs, planet-class restrictions |
| `tradition` | `common/traditions/*.txt`, `common/tradition_categories/*.txt` | tree, adoption/finisher, effects, requirements |
| `ascension_perk` | `common/ascension_perks/*.txt` | effects, prerequisites (traditions/techs), exclusions |
| `policy` | `common/policies/*.txt` | options, per-option effects, faction reactions, requirements |
| `edict` | `common/edicts/*.txt` | cost (resources/upkeep), duration, effects, requirements |
| `civic` | `common/governments/civics/*.txt` (civics without `is_origin`) | ethics/authority requirements, effects |
| `origin` | `common/governments/civics/*.txt` (`is_origin = yes`) | description, effects, starting conditions |
| `trait` | `common/traits/*.txt` | cost, opposites, species class, effects (species and leader traits) |
| `ship_component` | `common/component_templates/*.txt` | size, slot type, power, cost, stats, prerequisites |
| `ship_section` | `common/section_templates/*.txt` (+ `common/ship_sizes/*.txt`) | ship size, slots, cost |
| `event` | `events/*.txt` | id, type, title/desc localised, options with their localised names and summarised effects, trigger summary |

Version note: the 4.x line (4.0 "Phoenix" onwards) reworked pops, jobs and districts; the
wiki pages in `../docs/` state which version they were last verified for. Generated records win
over the wiki prose.
