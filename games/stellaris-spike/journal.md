# Journal — Stellaris integration spike (throwaway game, United Nations of Earth)

Goal: check that an LLM can govern a Stellaris empire through the existing agent without a mod
("LLM governor over the native AI"). Non-Ironman game, medium galaxy, Ensign, seed 447162947.
All findings verified live on 2026-09-25 on the user's PC.

## Environment
- **Stellaris Cygnus v4.5.1 (358e)**, Steam. Steam *PLAY* starts the game directly (no Paradox
  Launcher step). The 4.5 welcome screen says 4.5 breaks save and mod compatibility.
- DLC folders: plantoid, leviathans, horizon_signal, utopia, synthetic_dawn, apocalypse,
  humanoids, megacorp, ancient_relics, lithoids, federations, necroids, nemesis.
- Live documents folder: `D:\OneDrive - Sacramento\Paradox Interactive\Stellaris` (agent root
  `stellaris_docs`). A stale 2022 copy sits under `OneDrive\Documents`; the installer now
  picks the most recently written candidate.
- `settings.txt`: `autosave=2` = Monthly (4 = Semiannually), `tutorial=0` = None. Both set from
  the in-game Settings → Gameplay; monthly autosave works without the restart the game asks for.

## Reading the game
- **Autosaves**: `save games/<empire>_<id>/autosave_YYYY.MM.DD.sav`, one per in-game month. A
  `.sav` is a ZIP with `meta` (578 B: version, date, DLC) and `gamestate` (plain Clausewitz text).
  Year 2200 of a medium galaxy is 20.3 MB unzipped / 1.27 MB zipped; fetched through
  `/files/read` in ~15 ms on the LAN.
- Largest sections: `ship_design` 5.6 MB, `planets` 4.0, `ships` 3.4, `country` 2.9, `fleet` 1.2.
  The player country block is ~76 KB. It has `budget` (income/expense by source),
  `tech_status` (known techs, per-field queues, `alternatives` on offer, `stored_techpoints`),
  `active_policies`, `ethos`, `government`, `owned_planets`, `fleets_manager`, `flags`, and an
  `ai=` block (strategies) even while a human plays it.
- `player={ {name=… country=0} }` stays `country=0` in observer mode.
- A prototype regex summariser extracts country 0, research, policies and planets in 0.04 s.
  A real implementation should use a proper Clausewitz parser (e.g. the `jomini` crate).
- **`logs/game.log`** records script `log` effects with the in-game date:
  `[18:09:49][effect_impl.cpp:22191]: [2200.1.1] Log effect, file:  line: 1. HARNESS_PING`.
  Vanilla scripts write here too (e.g. `LOST COLONY PARENT CREATED`, `first_contact.1` choices).
  Localisation like `[This.GetName]` is not expanded in log lines.
- **HUD**: date and speed at the top right (`2200.01.08` / `Normal speed` / `Paused`); a large
  "Paused" banner sits above the bottom-centre system label.

## Acting on the game
- **Console**: `` ` `` opens and closes it; the agent's `/type` (Unicode input) enters text, and `enter`
  runs it. It warns that debug commands disable achievements; saves then carry
  `cheated_on_save=yes`.
- **Pause**: `space` toggles it. About 7 days pass in 4 s at Normal speed (~17 s per month).
- `effect set_policy = { policy = diplomatic_stance option = diplo_stance_cooperative cooldown = no }`
  applies at once ("Policy on Diplomatic Stance is set to Cooperative") and shows in the next
  autosave.
- **`observe`** hands the player's empire to the native AI. Research had been idle (points piling
  up in `stored_techpoints`); the AI filled all three queues on the day `observe` ran and the
  stored points were spent (known techs stay at 31 until the first ones finish).
- **Pitfall**: in observer mode, console `effect` has no country scope. The console still printed
  "set to Expansionist", but nothing changed in any country and a `set_country_flag` landed nowhere.
- **Works**: `play 0` → `effect …` → `observe`. The flag `harness_probe2` landed on country 0; the
  AI kept `diplo_stance_isolationist` for the two months checked (Oct and Nov 2200).

## Conclusion
The governor design works with vanilla commands:
**monthly autosave → briefing → LLM decision → pause, `play 0`, whitelisted effects, `observe`,
unpause**, with `game.log` as the urgent-event channel. The native AI runs day-to-day play.
Open questions for the build:
- Which directives the AI keeps over longer periods (policies held for 2 months; edicts,
  economy plans and war decisions are untested).
- Whether a companion mod is still needed: for AI-weight flags and for richer `log` event
  hooks (e.g. war declared). Installing one needs write access or a user step; the agent is
  read-only.
- Save size and parse time late in the game.
- Achievements are off for any game driven this way.

## Build checks (same game, loaded from the 2200.11.01 autosave)
- `game-controller stellaris directive expand` sent `play 0` → clear flags → set
  `governor_directive_expand` + `diplo_stance_expansionist` → `observe`; `GOVERNOR_APPLIED expand`
  appeared in game.log at once. The 2202.07.01 autosave (20 months later, run at Fastest) still
  has the flag and the stance, so the AI kept the directive.
- Over those 20 months the empire stayed at 1 planet, 1/3 starbases and 31 techs, while the
  stockpiles grew. Every AI empire looks the same (flat tech counts, 0–2 new starbases). This is
  4.5's early pace at Ensign, not an observer-mode problem: `tech_physics_1` costs 1,500
  (`@tier1cost3`) against +12.8 physics per month.
- **Speeds** (HUD label while running): Slowest, Slow, Normal, Fast, Fastest; `-`/`=` step
  through them, and pressing them while paused also works. Fastest ≈ 2.5 in-game months per real second.
  Only the 5 most recent autosaves are kept (2200.12 had rotated out by 2202.07).
- Load Game lists save folders; "Load Latest Save" on United Nations of Earth loads the newest
  autosave. Another folder ("Commonwealth of Man 3", 2219) is the user's own game: never touch it.
- **Fastest-speed reliability** (2204–2207): 30/30 autosave fetch+parse cycles succeeded while
  running at Fastest (saves rotate about every 0.4 s). Directives applied while running are
  confirmed (`GOVERNOR_APPLIED tech_rush` at 2207.1.15; the 2207.02.01 save has the policy and
  flag). Space toggles pause, so blind presses ended in the wrong state; the "Paused" label
  pulses (template distance 0.011–0.108), and a yellow-pixel share (23–47% paused, 0% running)
  reads it reliably. `-`/`=` do not change the pause state.

