# Stellaris corpus

Game knowledge for playing **Stellaris** (Paradox, real-time with pause) through the harness,
in the same layout as `corpora/galciv4/` (see ARCHITECTURE.md §5). The model here is an **LLM
governor over the native AI**: state comes from the monthly autosave, and the player empire is
steered through a small companion mod's events fired from the console (stance flags, policies,
edicts, native-AI weights — never free resources or stat bonuses).

```
corpora/stellaris/
├── manifest.toml   # metadata, hotkeys (from the wiki), screens to capture (commented placeholders)
├── strategy.md     # playbook distilled from docs/, each rule cites its doc; governor directives
├── pilot.md        # DRAFT briefing for the governor model (finalised after the bridge spike)
├── data/README.md  # generated-data contract; no data generated yet
└── docs/*.md       # 46 reference files from 34 wiki pages (Source:/License: headers)
```

## Verified on the user's PC (2026-09-25)

- Stellaris "Cygnus v4.5.1 (358e)", Steam; launched straight from Steam PLAY (no Paradox
  Launcher step); runs borderless. The 4.5 welcome screen warns that 4.5 breaks save and mod
  compatibility (Pop Group / Faction changes).
- 13 DLC folders: plantoid, leviathans, horizon_signal, utopia, synthetic_dawn, apocalypse,
  humanoids, megacorp, ancient_relics, lithoids, federations, necroids, nemesis.
- Documents folder: `D:\OneDrive - Sacramento\Paradox Interactive\Stellaris` with
  `logs/game.log`, `save games/`, `mod/`, `settings.txt`, `dlc_load.json`.
- `settings.txt`: `autosave=2` is Monthly, `4` is Semiannually (UI order Monthly, Quarterly,
  Semiannually, …); `tutorial=0` is None.
- `logs/game.log` records script `log` effects with the in-game date, e.g.
  `[18:08:59][effect_impl.cpp:22191]: [2200.1.1] Log effect, file: … line: 966. LOST COLONY PARENT CREATED`
  — usable as the companion mod's output channel.

## Provenance and licence

All `docs/` files come from the official wiki, https://stellaris.paradoxwikis.com/. Its footer
states "Content is available under Attribution-ShareAlike 3.0 unless otherwise noted" (CC BY-SA
3.0), recorded in each file's `License:` line; redistribution must keep attribution and the
same licence. The live wiki serves a JavaScript challenge to non-browser clients, so every page
was taken from an Internet Archive (Wayback Machine) capture of the wiki URL; the capture
timestamp and the page's own version banner ("verified for 4.4", "last verified for 3.14", …)
are on the first body line of each file. Text was converted from HTML to markdown (navigation,
images, edit links and references stripped; tables kept as markdown, split into row groups so
search chunks stay small). Long pages are split into topical files:

- Beginner's guide → `beginners_guide`, `_concepts`, `_early_game`, `_late_game`
- Jobs → `jobs`, `jobs_worker_and_special`
- Effects and Conditions (the engine dumps) → `effects_*` / `triggers_*` grouped by the first
  scope each entry lists (general, country, planet, space, other)
- Scopes → the explanatory part only; its flat list duplicates `triggers_*` / `effects_*`

## What is unverified

- Every hotkey except the ones marked `verified` in `manifest.toml` (the wiki's Hotkeys page is
  a 2024 capture; F1–F10 depend on the navigation menu order). The console key on the user's
  keyboard layout.
- `process_title` (window title) and all screen positions — no screens are captured yet.
- Wiki numbers: pages were verified for 4.2–4.4 (some sections 3.x), not 4.5.
- Everything in `pilot.md` about the bridge and the briefing format.

## Next steps

1. Spike: read the window title, capture pause indicator / date readout / event popup /
   console templates, and confirm the console key.
2. Extractor `scripts/extract-stellaris.py` over `common/`, `events/` and
   `localisation/english/` (read through the agent) → `data/*.json` per `data/README.md`.
3. Companion bridge mod: directive events that set flags / edicts / policies, `log` effects to
   `game.log`; fired from the console.
4. Save parser: unzip the `.sav` (`gamestate` + `meta`, see `docs/save_game_editing.md`) and
   build the monthly briefing.
5. Finalise `pilot.md` and the directive list in `strategy.md` from the spike.
