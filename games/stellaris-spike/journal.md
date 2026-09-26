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
- **First governor run** (`pilot run --game stellaris --speed fastest --months 6 --episodes 3`,
  Gemini 3.8 Flash): 2207.02 → expand (tech_rush replaced; "515 influence, only 1/3 starbases");
  2207.09 keep; 2208.04 keep. ~6.2k input / 0.1–0.4k output tokens and ~2 s per decision; the
  scheduled stop overshot by one month at Fastest (2 s polling). The game was left paused with
  `governor_directive_expand`. The run's journal and learned episodes were discarded (test game).

## Correction: observer mode does not play the empire fully (2212–2216)
- Counting **owned systems** (distinct systems of `controlled_planets`) instead of starbase
  capacity showed the earlier conclusion was wrong: from 2200 to 2212 our empire stayed at **1
  system** while every AI empire grew to 9–18. In observer mode the AI researched and built
  warships (fleet 20 → 30) but never surveyed (`first_system_survey_finished` missing) or expanded.
- **`human_ai`** ("Toggles AI for Human countries") fixes it: we stay the player and the game's AI
  plays the empire fully. After switching it on in 2212.03: 2 systems by 2214.02, 4 by 2215.11,
  empire size 56 → 79, starbase capacity used 1/3 → 3/3, a new colony (Al-Jissa).
- Console effects then apply directly (the player's empire is the scope): directives no longer
  need `play`/`observe`. `play 0` does not change the `human_ai` state.
- `human_ai` is a toggle and its state is not saved; `is_ai` is `no` in both states and
  `last_date_was_human` only records the last `play`. The console's reply "Human AI is now ON/OFF"
  is read on screen: `help` first fills the console so the reply lands on the bottom line, then
  the ON and OFF templates are compared (the closer one wins; the console is semi-transparent, so
  absolute distances drift with the map behind it).
- A scoped log (`if = { limit = { exists = capital_scope } log = … }`) is written while playing and
  not while observing, which detects observer mode.
- **game.log** drops a log line whose text repeats on the same in-game day, and writes with a few
  seconds' delay. Every marker now carries a unique suffix and is polled for up to 8 s.
- Live validation run (Gemini, Normal speed, 12-month cadence): 3 decisions, all `keep`, reasons
  citing stockpiles; the run was stopped to fix the control mode above.
- **Edicts are not steerable from the console under `human_ai`**: `effect add_edict = map_the_stars`
  took effect (`has_edict` true, logged at 2217.2.7 and again at 2217.7.1) but the edict was gone by
  the next monthly save both times; the AI manages edicts itself. Policies, in contrast, stayed
  20 months. Directives therefore stay flags + policies. Steering the AI's edict and build
  choices needs the companion mod (`ai_weight` modifiers reading `governor_directive_*`), which
  needs a file written into the game's `mod/` folder (the agent is read-only).
- End-to-end governor run on the `human_ai` path (Gemini, Normal, 6-month cadence): take-control
  at start ("human_ai is ON"), then 3 × `keep` (2216.02 – 2217.02) citing "influence maxed at 800
  and only 4 systems owned" and positive nets; game left paused.
- **Peer benchmarks** (2217–2218): the briefing now shows "FALLING BEHIND: systems 4 vs median 15.5".
  Gemini cites it in both decisions but keeps `expand` ("not resource-constrained": 860 influence,
  +14 alloys/month) while systems stay at 4 (median 16.5). The briefing lacks why expansion stalls
  (reachable unclaimed systems, construction ships, closed borders), so the model cannot name the
  constraint yet.
- **Expansion diagnostics**: 2218.02 has room (4 unclaimed systems 1 jump out, 9 within 2 jumps)
  and 2 construction + 3 science ships, but only 2 of those 9 were surveyed by us first: the stall
  is exploration after 12 years without it, not a lack of space. (An unclaimed system lists the
  null starbase id 4294967295; the first version of the check counted those as claimed.)

## Evaluation: Governor Bridge in United Nations of Earth 2 (2203.10 – 2215.02, telemetry)
- Mod loaded for the whole campaign, directive `expand` throughout. Systems 3 → 12 (≈0.8 a year);
  peer median 2 → 14, so the rank slid from 3rd to 9th of 14. The first campaign (no mod, mostly
  observer mode) had 4–5 systems at 2216–2219, so `human_ai` + mod expands, but slower than peers.
- The gate is **influence**: net +3.6 to +4.6 a month, stockpile repeatedly spent down to 7–70,
  while alloys sat at 85–370 and energy piled up to 14,400 unused. Vanilla funds outpost alloys
  only while influence > 75 (`alloys_expenditure_starbases_expand`).
- **Bug found**: the mod's extra influence went to category `starbases`, which in vanilla only
  nomadic empires spend influence from; outposts draw influence from `stations`
  (`influence_expenditure_stations`, "min is 1 jump away"). So the expand directive reserved
  influence in a pool nothing spends. Fixed (entry now `stations`, desired_min 75); a test checks
  every mod entry against the categories a non-nomadic empire spends from. The energy-for-planets
  entry of `consolidate_economy` was dropped for the same reason (only the Gaia seeder uses it).
- Next check: systems a year and influence stockpile after the fixed mod has run ~5 years; if
  still ≈0.8 a year the remaining lever is influence income itself (traditions, envoys), not budget.

## Postmortem: Theian test campaign (2200–2282, telemetry, saves and dashboard frames)
- Lost 32 → 13 systems. Root cause of the war losses: the capital Theia held the only shipyard
  (Titawin A Station) and nearly all alloy production (+35 of +40); occupied from 2257.03, alloy
  income fell to +2 to +5, the AI built nothing for ~6 years and military was 0 from 2261.03 to
  2265.06. Income recovered to +34.5 within four months of the 2270.01.10 peace, which ceded
  Ribharm, Rhynstane, Stape and Kilnstane to a new UNE vassal. Grimvoss and Undulonn were emptied
  in the Lyrite absorption war.
- Root cause of the lost decade 2245–2254: a false naval-cap premise from our own `trends()` hint
  (frames show 124/117 in 2244.07, 76/117 in 2245.06, 51/115 in 2246.06); the models ran
  `tech_rush` for naval techs and wrote five "capped" rules into learned/strategy.md. Peacetime
  military collapses (2224, 2226, 2244–45, 2248, 2251) were ship losses, cause unknown (monsters
  likely).
- Harness gaps: no naval max, occupation, shipyards, fleets or own-battle split in the briefing;
  directives not read back (`tech_rush` left the economy on balanced for seven years); traces cut
  at 6,000 characters; three skipped decisions (503s, request limit).
- Done now: hint reworded and a `MILITARY FELL` flag added, false rules purged, lessons in
  strategy.md §12. Planned (plan.md): war-readiness briefing, directive read-back, two shipyards
  before war, fleet snapshots, full traces; the strategy layer carries war exit criteria and
  market orders.
