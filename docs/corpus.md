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
  learned/        rules and episodes the pilot learned (committed)
```

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
reference docs; the governor directives and the Governor Bridge mod (`corpora/stellaris/mod/`).
Autosaves are read by `crates/game-controller/src/stellaris.rs`.

## Other screen sizes

Positions and templates are measured at 3840x2160. A PC with another size sets `GAME_RESOLUTION`
(e.g. `2560x1440`); the controller then merges `res/<W>x<H>.toml` over the manifest. Its UI points
come from `scripts/res-map.py corpora/<game> <W>x<H> --write`: one UI scale per size in
`res/map.toml`, each UI group pinned to the top-left corner or the screen centre (verified within
1–2 px at 1440p). Screen templates are captured again at that size with
`scripts/play/capture-template.py`.
