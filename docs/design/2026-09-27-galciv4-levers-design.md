# GalCiv IV governor, levers: the game's AI plays our faction (soak with event hold), action record, rush rules, crisis, placement check, state reader, watchdog and relaunch, mini-rig2

Date: 2026-09-27. Status: approved in a hands-off run for the offline phases. The live phases wait for the
user's go on two setup changes on mini-rig2: Steam Cloud off for GalCiv IV (ruling 2) and the cheat console on
(ruling 8).
It carries the Civ VI levers design (`docs/design/2026-09-27-civ6-levers-design.md`, "the Civ VI design")
and the Stellaris levers design (`2026-09-27-stellaris-levers-design.md`, "the Stellaris design") over to
Galactic Civilizations IV where they fit. Rulings are numbered from 1. Rulings from other documents are
cited with that document's name.

Base: `main` at 6350d4a. The code map took its line numbers at 469cd14. No GalCiv IV file has changed
since then (`git diff 469cd14..6350d4a` on `src/pilot/{controller,agent,game,learning}.py`,
`autopilot.rs` and `corpora/galciv4` is empty; checked here). The Stellaris watchdog and the planned
`record.py` exist only on branch `feat/stellaris-levers` (09077d9), not on `main`.

Game: GalCiv IV Supernova. The saves are 4.1.1. The game is installed on mini-rig2
(`GalCiv4.exe`, 47,708,840 B, mtime 2026-09-26 22:28Z); its build number was not read. The Civ VI
governor is running on mini-rig2 now. Anything marked **unverified** has not been seen in live play. The
section "Unverified, in one place" at the end lists every such item.

Sources:
- Five research passes (working notes, not in the repo): the code map, play history, AI takeover, state
  reading, and economy/crisis/placement.
- Seven adversarial votes on them: 3 on the takeover, 2 on state reading, 2 on the economy.
- Static analysis notes on the console handlers in the game executable (working notes, not in the repo).
- Local copies of mini-rig2 files, read earlier through the agent: `Prefs.ini` and `debug.err`
  (Nov 2024), `HotKeys.ini`, the exe, and the terran-2329 Auto-Save (turn 56, from Steam Cloud).
- `incoming/gc4data.zip` (544 XML files), `games/terran-2329/journal.md`, `issues.md`, `plan.md`,
  `PLAYING.md`, `AGENTS.md` §7, and the four GalCiv IV runs in `runs/`.

Writing this design read no files from either PC and sent no input to any game. Checks made while
writing are marked "(checked here)".

---

## Evidence

**E1. Screen play costs one model intervention per 1.3 turns.** Play history, 2026-09-25, traced play
only:
- About 56 turns. The autopilot confirmed 43 of them; median **1.99 s** per autopilot turn, max 13.35 s.
- **41** model interventions in the hand-driven sessions plus 3 by the pilot, and about 11 handled by known screens. That
  is 0.75 interventions per turn.
- 43 advances against 43 stops. The longest unattended run was **6 turns**.
- Wall time was about 72 s per turn over the session, 56 s without the hang.
- The coding session made 293 API calls with 178.9M cache-read tokens, about 610k context per call.
- The pilot app used about 23k tokens per episode. It lost 2 of 5 episodes (Gemini SDK
  `ValidationError`, run 173553) and counted **0** turns while the date moved 2 months (run 173641).
- For comparison, the Civ VI governor made 95 decisions over T41-T302, one per 2.7 turns, about 22.5k
  tokens each.

**E2. What stopped the turns.**

| Blocker | Model | Known screen | Note |
|---|---|---|---|
| Event with a choice | 16 | 0 | Every choice matched a `strategy.md` §5 rule. 11 were looked up with `corpus get` |
| Research complete | 4 | 0 | |
| Informational report (Appoint a Governor) | 1 | 0 | |
| Idle core world (build) | 7 | 0 | Built through the tile menu, 4-6 calls each. Planet-screen drags failed 3 of 3 |
| Colonial Charter | 2 (4 actions) | 0 | Drags work there (4 of 4) |
| Idle units, boarding, shipyard | 9 | 5 screens built live, 11 handlings | |
| First contact, AI trade | 3 | 1 (`diplomacy_menu`) | |
| Cutscene | 1 | 0 | Wait about 30 s, then one click |
| Turn hang | 1 | 0 | |

**E3. The turn hang cost 28% of the session.** "Starting New Month" never ended after first contact
(Jun 2331), and Save/Load were greyed out.
- It took 6 minutes to judge it a hang and 6 minutes to recover by hand: Exit → Steam → Stardock
  Launcher → skip intro → Load newest Auto-Save. Then 4 months were replayed.
- Total: **18.6 min**, 57 API calls, 39M cache-read tokens.
- Recovery is still manual (`issues.md:59`, `plan.md:63`, AGENTS.md §7).

**E4. The game's own AI can play our faction. Console commands in the current exe** (line numbers in a strings
dump of the exe, a working note):
- `ai <hold>` (6469-6473) "toggle[s] the local play to be AI and back". With `hold`, the user presses
  the turn button instead of the AI.
- `soak <numTurns>` (6539-6543) "Calls several commands that are useful for soak testing". After N
  turns "the player will be converted back to a human player". Without N it runs indefinitely.
- `resumesoak` (6527-6529) checks the current state before it toggles. `disablesoak` (6534-6536).
- `turn` (6396-6398) toggles the forced handling of idle ships and colonies.
- `savelog <file>` (6402-6406) writes the console log to a file. `clearlog` (6561).
- Read-only: `liststat` (6241-6244), `listplayers` (7197-7199), `showdifficulties` (7081-7083).
- Replies:
  - "Success: AI active for player." (32046), with "  Will not auto-pass turns." (31979) under `hold`;
  - "Success: AI turned off for player." (42494);
  - "Starting Soak Test" / "Stopping Soak Test" (42507-42508) and "Running for %lu Turn(s)" (31998);
  - "Holding new turn when an event is triggered" (42506).
- Static analysis of the handlers:
  - The `soak` handler toggles a soak flag. It sets an event-hold flag **only** for the argument `event`
    or `events`. It then calls the `ai` handler (without hold) and the `turn` handler. Both are toggles.
  - Each turn the count goes down. At 0, soak toggles `ai` and `turn` back and switches itself off.
  - The event dispatcher sends an event owned by an AI-controlled player to the AI resolver unless the
    event-hold flag is set. `ai hold` clears that flag.
  - With the flag set, an event puts our player on hold and goes to the normal UI. Auto-pass resumes
    once the popup closes.
- Access:
  - The console is enabled by `EnableCheats` in `Prefs.ini` (UI label "Enable Cheat Console"; 0 on
    mini-rig2, line 102) or by the `-cheat` launch option.
  - It opens with the backtick key (`HotKeys.ini` `[UnhideDebugConsole]` KeyboardCode=192; the agent maps the backtick to 0xC0
    at `keys.rs:73`).
- Web sources:
  - A moderator (Illauna, Apr 2025): "soak - have the AI play for the player". The developer (Frogboy,
    Oct 2023): "watch the AI play out the game".
  - Whether the soaked player gets difficulty buffs: "Pretty sure… normal difficulty" (Draver) and "it
    doesn't receive the same buffs" (Illauna). `AIDefs.xml` 104-115 gives Normal +1 Fertility on
    colonies, yet Illauna also wrote "Normal has no bonuses or penalties".

**E5. The votes on the takeover: 0 of 3 refuted it** (high, medium, medium). Their corrections:
- Plain soak does not hold on events. The hold needs `soak N events` (vote 2, from static analysis).
  Vote 1 found that the hold message is not in soak's help text.
- Under `ai` and `ai hold` the AI very likely answers our events itself (vote 2, an inference from the
  dispatcher).
- `ai`, `soak` and `turn` are blind toggles (votes 2 and 3). Vote 3 said the exe has no "on" reply. The
  exe does have one: "Success: AI active for player." (checked here).
- "Fleet-wide automate" is wrong. Those commands are redirect rules (vote 1).
- The multiplayer "Convert" button works only in a restored multiplayer game, and taking control back
  means rejoining the lobby (vote 2).
- Directives on autonomous worlds belong to Federations and Empires. The Auto-Save's `DLCstatus.txt` has
  FederationsAndEmpires=0 (vote 1).
- `turn` can leave research unassigned: "Remember to open the tech screen…" (exe_w 42409).
- No player-facing research queue exists. The engine has an internal one ("FAILED: Research queue is
  empty.", 42411).
- **Steam Cloud couples mini-rig2 to the user's PC.** The terran-2329 Auto-Save reached mini-rig2 that
  way. Any save written on mini-rig2 goes back up to the cloud. The same Saves folder holds the user's
  own saves (New Save Name*, 2023-2025). (vote 3)
- mini-rig2 has not run GalCiv IV since Nov 2024. Its `Prefs.ini` has every popup switch on.
  `ShowBattlesDuringSoak` is a [Hidden] key that the UI cannot change. mini-rig2 has only the Supernova
  DLC folder, while the save uses MegaStructures and Warlords as well. The exe reports `x-usedcheats` in
  its match telemetry. (vote 3)

**E6. Other automation in the game (partial).**
- Per-world "Automate" ("Allow the AI to manage your world") excludes the capital and needs a governor
  (`UIText_PlanetScreens.xml` 6-18). In terran-2329 the only core world is Earth, the capital, so it
  covers nothing.
- Also: auto colonize, survey, explore and mine; starbase auto-build and auto-upgrade; improvement
  auto-upgrade; repeating shipyard queues.

**E7. Saves can be read without vision, in part** (state-read finding; both votes: not refuted, high).
- A `.GC4Sav` is a zip. `Save.tmp` is 17.0 MB deflated and 337 MB unpacked at turn 56. Four small
  **deflated** entries sit at the end: TurnNum.txt, Guid.txt, Description.txt and DLCstatus.txt. The
  2023 save (version 2.0) has no TurnNum.txt or Guid.txt.
- `Save.tmp` is positional binary. A game-definition reference is FNV-1a 32 over the UTF-16LE internal
  name.
- Decoded on the turn-56 Auto-Save:
  - 22 **stat blocks**, each with 10 series per turn. Block 0 matches our numbers: Credits 1110.2,
    Research 5.8, Manufacturing 8.0, Approval 0.72. Block keys are not player indices, and blocks 14-21
    look like minor factions.
  - **Tech state.** Colonial Policies, Universal Translator, Armed Shuttles and Research Districts are
    researched, plus Starbases, which was free. Hyperwave Radio is at 51.6 points.
  - An **event history** of (hash, value) pairs for all players. All 111 ids match corpus aliases.
  - Planet names.
- Owner, population, buildings, queues, policies, diplomacy and fleets are **not** decoded.
- The probe's anchors are fragile (a hard-coded offset, first plausible header, blocks mapped by order).
  "3-5 days" is realistic only for porting stats, tech and sidecars (vote 2).
- Cost:
  - A full save read takes at least 2 agent requests (16 MiB cap per read).
  - Parsing took 0.9 s in Python.
  - Autosave runs every 5 turns (`AutoSaveFrequency=5`), in 2 slots (Auto-Save and Previous Auto-Save).

**E8. `debug.err` is a readable event stream, from an old build.** The copy read is from build 2.91
(Nov 2024).
- It logs:
  - `EndTurn N`, `StartTurn N`, `Start/End AI planning turn N` and `Turn Complete. Duration=… ms`;
  - `Popup Manager Update: Unhiding <Wnd>` (ResearchCompletePopupWnd, InteractionWnd,
    CrisesUpPopupWnd, CutsceneWnd, PolicyWnd, GNNWnd, …);
  - `CGameEventSystem::TriggerEvent <id> Player <name>` (79 of 81 ids map to corpus aliases);
  - colonisation, trades and autosaves.
- "Turn Complete" is missing on 5-7 of 25 turns; the two votes counted differently. EndTurn, StartTurn
  and "End AI planning turn N" appear on every turn.
- Popups are only ever logged as "Unhiding", never as closed.
- The file is recreated at each launch. Whether 4.1.1 still writes these lines and flushes them during
  play is **unverified**.

**E9. Rush-buy, from the game data** (economy finding; both votes: not refuted, high).
- `RushCostMultiplier` 7.5 (`GlobalDefs.xml:40`). 1 Control per rush for a core world or a shipyard
  (`:2143-2144`).
- Once per month per core world and per shipyard (`HotSpotText.xml:384-385`). A shipyard rushes only
  ship designs. A rush may also need strategic resources.
- The game's own refusals:
  - "Already used rush this Month.";
  - "Your government doesn't allow rushing.";
  - "You do not have enough Control.";
  - "Worker's Rights: No Rushing";
  - "Item already ready to complete."
- No price formula is published. The price is shown only in the Rush tooltip.
- **Control is not the binding cost** (vote 2 correction). Every faction gets a flat +100 Control
  (`GlobalDefs.xml:651-657`). The top bar shows "100 +0".
- The rival AIs' own spending:
  - early strategies use `SpendUntilBroke` with buffers of 50-1000;
  - the at-war strategies (Diplomatic, Trader, Scientific) apply from turn 75, with `BreakEven`, a
    200-credit buffer and PlanetDefenderFillCap 1;
  - `Wartime` has TurnStart 1000, a sentinel that probably keeps it off.
- terran-2329 held **1,100-1,289 idle credits** from 2331 on, with income 0 to +2. It never rushed.

**E10. War, from the game data.**
- Only destroying the attacking fleet ends a siege (`UIText.xml:24353`). A siege lasts 2-10 turns
  (`GlobalDefs.xml:879-884`). Only transports can besiege a core world.
- Alerts: BesiegedPlanet (with the months left), ConqueredPlanetLoss, LostShipsInFleetBattle
  (`AlertDefs.xml` 424, 448, 380).
- **War-ending events the defender can use** (vote corrections):
  - `WarAimsEvents_v30.xml`: Event_WarAims_Completed_L0 (we pay −10 credits a month for 100 turns),
    Overtime_L2, CeaseFire_HFY01 (+500 credits to us).
  - In `Events_23.xml`, 13 "LosingAIWantsCeaseFire…" offers pay us. Only the 4 "AIWantsCeaseFire"
    offers (0x45A3, 0x55A3, 0x65B4, 0x75C5) cost us.
  - All 65 war-weariness events need `PlayerIsAggressor`. `pilot.md` forbids declaring war.
- Executive orders cost Control: Draft Civilian Ships 100 (Terran techs), Forced Overtime 100, Print
  Money 45. Defense Matrix is a colony upgrade (250 credits). Mercenaries (750-2,700) need the Age of
  Expansion.

**E11. Tile placement, from the game data.**
- A tile feature gives Level to one improvement type. Neighbour bonuses give Level to adjacent types.
- Most district Levels are **percentage multipliers**: Manufacturing +2%, Research +1%, Wealth +3%,
  Food +10%, Influence +3% per level. Only Population and Approval are flat.
- District upgrade projects add +1 Level to every district of a type. Planet terrain matters too.
- One saved frame confirms the rule: a Research District on Lakes next to a Research District showed
  "2" (`runs/20260925-173641/frames/00004.jpg`).
- The corpus has adjacency only as prose. The **Capital City was never placed**: 3 of 3 planet-screen
  drags failed (`issues.md:58`).

**E12. The environment.**
- mini-rig2 is 2560x1440 (`DisplayResolution=-1 x -1`, Fullscreen=1). It runs Civ VI now.
- One Steam account, so one game at a time.
- The agent has read roots `galciv4_docs` and `galciv4_install`. Its only write roots are
  `stellaris_mods` and `civ6_options` (`windows_agent/install.ps1:171-189`, checked here).
- `HotKeys.ini` on mini-rig2 (2024) binds Explore to X, while O was verified on the main PC. It binds
  R to rush and to fleet Repair, Ctrl+R to CompleteTechResearch, and F1-F4 to
  Teleport/Clone/Restore/Destroy.
- The known screens and click positions were measured at 3840x2160 on the main PC.
- The Stellaris resolution overlay exists (`corpus.rs:192-223`, `res/map.toml`, `scripts/res-map.py`).
  It maps only `[ui.*]` points; overlay screens replace whole screens.

**E13. The code** (code map).
- GalCiv IV runs `controller.Pilot` (`cli.py:88-100`). It never imports the governor, strategy or
  pillars modules.
- The turn count resets on every autopilot call (`mcp.rs:635`). `telemetry.month_index` returns None
  for GalCiv IV dates (`telemetry.py:73-84`).
- **Bug:** a timed-out GalCiv IV model call is never retried. `run_episode`'s `on_retry`
  (`agent.py:328-329`) reads `e.model_name`, and an `httpx` timeout has no such field, so the retry
  raises `AttributeError`. This was reproduced with a stub agent.
- `FORBIDDEN_COMBOS` (`learning.py:33-36`) lacks ctrl+r, F1-F4 and the backtick.
- `shipyard_idle` always queues a Colony Ship (`manifest.toml:221-228`).
- Nothing on the Python side bounds a hung controller: `_rpc` blocks on `readline` (`game.py:96-99`).

---

## What transfers from Civ VI and Stellaris, and what does not

| Lesson | GalCiv IV | Ruling |
|---|---|---|
| The game's AI plays, the model steers (Civ VI `AutoplayManager`, Stellaris `human_ai`) | **Transfers**, through `soak N events`: a bounded stretch that hands back by itself, like Civ VI `autoplay N`. Events stay with the model. | 1, 5, 6 |
| One-turn stretches cost the AI its plans (Civ VI issues.md:19; amendment A1) | **Transfers as a default**: N = 5; 2 only when a world is in danger. The AI here plans each turn ("Start AI Planning turn N"), so the loss may be smaller (**unverified**). | 5, 16 |
| Blind toggles, read back on screen (Stellaris `human_ai`, `toggle_until`) | **Transfers**: `ai`/`soak` are toggles; replies are read from `savelog` text, with templates as the fallback. | 4 |
| Never send model-written code (Civ VI Lua) | **Transfers**: a Rust whitelist of console commands; the model never types into the console. | 4 |
| A record per action kind with stick rates (Civ VI 12-15) | **Transfers**. Keys are event, research, policy, rush, stretch and crisis. The clock is `TurnNum`. | 12, 13 |
| No pressure factor for a failing channel (Civ VI 15) | **Transfers** unchanged. | 13 |
| Research or civic blocker always filled (Civ VI 16) | **Transfers**: after a stretch hands back, an empty research slot is filled. | 7 |
| Buy-outs with reserves, in danger first (Civ VI 17-20) | **Transfers, narrowed.** Under soak the AI spends our credits itself (E9), so the model rushes only in danger or when credits sit idle. | 14, 15 |
| Never buy what the AI finishes anyway (Civ VI 20) | **Transfers**: skip at ≤ 2 turns left. The game also refuses "ready to complete". | 14 |
| Scripted last stand (Civ VI 22-27) | **Does not transfer.** Combat resolves itself, there is no tactical API, and the AI moves the fleets under soak. The Stellaris war-crisis overlay transfers instead. | 16, 17 |
| Entry on losses, never ratios (Stellaris 12) | **Transfers.** | 16 |
| Status quo or peace is the human's call, asked, never blocking (Stellaris 15) | **Transfers**, and the harness answers the AI's own ceasefire offers by rule. | 17 |
| Mod-steered AI priorities (Civ VI 28, Stellaris 17-21) | **Does not transfer to terran-2329**: game data is baked into saves. For a new campaign it transfers as the custom-faction editor, which binds only our faction and gives no bonus. | 19 |
| Placement planner, read-only first (Civ VI 30) | **Transfers as stage A only.** Under soak the AI places. The first question is whether it places Earth's Capital City. | 18 |
| Popups hold the engine (Civ VI T134 movie, tutorial) | **Transfers**: `Prefs.ini` switches off, plus known screens and a cutscene rule. | 8, 22 |
| Date-stall watchdog (Stellaris 23) | **Transfers**, keyed on `TurnNum` and `debug.err`, plus the relaunch that AGENTS.md §7 does by hand. | 20, 21 |
| Resolution overlay (Stellaris `res/`) | **Transfers, extended** to `[screens.*]` points, because GalCiv IV keeps its positions there. | 23 |
| Fork and reload for state-changing probes (Civ VI 28) | **Transfers**: the probe plays a copy save, and the campaign resumes from its own save. | 3 |

---

## Rulings

### Architecture

1. **Move GalCiv IV to the governor model. The game's AI plays our faction in bounded `soak N events`
   stretches. The model steers between stretches and answers the events that hold a turn. Screen play
   stays as the blocker handler and the fallback.**
   - **Decision.**
     - The target architecture is the governor model, the pattern proven in Civ VI and Stellaris. A
       new `Gc4Governor(Governor)` drives the loop:
       1. Take a briefing (rulings 9-11).
       2. Make a decision (ruling 7).
       3. Carry out the orders by scripted screen flows with read-back.
       4. Run `soak N events` (ruling 5).
       5. Answer held events (ruling 6).
       6. Repeat.
     - `run_episode` (`agent.py:317`) stays inside the governor, for screens that neither a known screen
       nor a scripted flow recognises.
     - The hybrid ("game automation for subsystems plus the model on macro decisions") is the
       **fallback**. It runs if the probe's gates G2-G4 fail (ruling 3):
       - screen play on mini-rig2;
       - known screens and new templates;
       - automatic event answers from the corpus;
       - the watchdog and relaunch;
       - rush and placement tools.
     - Pure screen play as it runs today is retired as a target. It survives as the fallback's core and
       as the blocker handler.
   - **Votes.** No path was refuted by a majority: all three takeover votes returned "not refuted"
     (high, medium, medium). These sub-paths are out, each on evidence the design accepts:
     - **`ai hold` as the play mode.** It very likely gives our events to the AI (E4, vote 2's reading of
       the dispatcher). It becomes the primary mode only if G4b shows that events still hold under it.
     - **An indefinite `soak`.** It never hands back, and it could run past the known hang without a
       watchdog.
     - **The multiplayer lobby's Convert button.** It needs a restored multiplayer game (vote 2).
     - **Data mods for terran-2329.** Game data is baked into saves (E5).
     - **Planet Automate as the main lever.** It covers no world in terran-2329 (E6).
     - **"Fleet-wide automate".** It does not exist (vote 1).
   - **Why.**
     - E1-E3: screen play needs the model about every 1.3 turns and never ran more than 6 turns alone.
     - The Civ VI governor decided once per 2.7 turns at a similar token cost per call, and it ran
       T41-T302 unattended.
     - Of E2's 41 interventions, the AI would take over the 7 builds, 2 charter blockers, 9 idle units
       and boardings, 4 research picks (unless we pick), the capital (including the unplaced Capital
       City, **unverified**) and the credits (E9). The 16 events stay with the model by choice. They
       are the one channel where a choice cannot be overridden, and all 16 matched a written rule.
   - **Cost if wrong.**
     - The AI plays our faction badly. Steam reports mention a loan taken while deep in debt and fleets
       sent on "kamikaze missions".
     - The AI could also answer diplomacy against `strategy.md`, for example by trading technology away.
     - The record (rulings 12-13) and the briefing trends show this within about 20 turns. The fallback
       is already built, because its parts are the governor's own blocker handler, watchdog and tools.

2. **GalCiv IV moves to mini-rig2. The user's desktop is never used. terran-2329 continues from its
   Steam Cloud copy, identified by GUID, with Steam Cloud switched off for GalCiv IV on mini-rig2.**
   - **Decision.**
     - All GalCiv IV play, reads and probes happen on mini-rig2 (192.168.1.159). The harness sends
       nothing to 192.168.1.77 for GalCiv IV: no reads, no input, no installs.
     - The campaign is terran-2329, from the turn-56 Auto-Save already on mini-rig2 (GUID
       `B44F8E54DDB146FEAA39A0AC6923F10F`).
     - It is renamed on first load to `harness-terran-2329` (Save As), and all harness saves use the
       `harness-` prefix.
     - **Steam Cloud for GalCiv IV is switched off on mini-rig2** before the first save there. This is a
       one-time step in Steam's game properties, done in maintenance window 1. It is read back from
       the Steam properties page.
     - **Campaign identity is the save GUID** (ruling 9). The governor never loads, briefs from or acts
       on a save whose GUID differs from the campaign's.
     - GalCiv IV runs only while no other Steam game runs on the account. Switching mini-rig2 from
       Civ VI takes a window (Rollout, phase 1).
   - **Why.**
     - The rules for this work forbid the main PC.
     - mini-rig2 already holds the campaign, the exe, and read roots for both GalCiv IV folders.
     - Vote 3: with cloud sync on, harness autosaves under the shared names "Auto-Save" and "Previous
       Auto-Save" would reach the user's PC. The user's own later autosave could also come down and be
       loaded by the hang recovery. The GUID check stops the second case; switching the cloud off stops
       both.
   - **Cost if wrong.**
     - If the Steam toggle is per account rather than per machine (**unverified**), the user's PC also
       stops syncing GalCiv IV saves. The step is then undone, and the harness relies on the GUID check
       and its `harness-` names alone.
     - If mini-rig2 lacks the MegaStructures or Warlords content the save uses (E5), G0 fails, and the
       DLC install waits for the user.

3. **The takeover probe: gates before the governor path is switched on. The probe plays a copy save,
   and the campaign resumes from its own save.**
   - **Decision.** The probe runs in maintenance window 1 (Rollout) on `harness-probe`, a copy of the
     campaign save. Afterwards `harness-terran-2329` is loaded again, as in Civ VI ruling 28's fork and
     reload. Gates, in order:

     | Gate | Pass | If it fails |
     |---|---|---|
     | **G0 load** | The copy loads on mini-rig2 at 2560x1440 and the sidecar GUID matches | Ask the user (DLC, install). Stop. |
     | **G1 console** | With `EnableCheats=1` (ruling 8), the backtick key opens the console. `help ai` matches E4. `clearlog` + `savelog harness_reply.txt` produces a file that the agent can list and read (record its path) | Console replies fall back to 1440p text templates (ruling 4). If the console cannot open: the hybrid |
     | **G2 soak** | `soak 3 events` replies "Starting Soak Test", "Running for 3 Turn(s)", "Holding new turn…" and "Success: AI active for player.". After TAB, exactly 3 turns pass and control returns ("Stopping Soak Test", or the turn button waits for us) | The hybrid |
     | **G3 the AI acts for us** | Within the 3 turns the AI changes something we did not: Earth's build queue, research, ship orders, credits spent | The hybrid |
     | **G4a events held** | A triggered event holds the turn with its dialog on screen, and after our click the stretch continues | Events go to the AI (plain `soak N`). The model reviews them afterwards from the save's event history, and the record keeps `event` as AI-made |
     | **G4b `ai hold` comparison** (only if G4a passes) | Under `ai hold`, one event is either answered by the AI (expected) or held | If held, `ai hold` becomes the primary mode, with the model acting every turn and TAB ending it |
     | **G5 hand-back** | After the stretch: "Success: Turn actions required." or the normal blockers; research empty or set | Stop, with the reply saved for the design |
     | **G6 fairness** | `liststat Fertility breakdown` and `liststat Research breakdown` on a colony and on Earth, before and during soak, plus `showdifficulties`. No difficulty modifier beyond Normal's +1 Fertility | +1 Fertility: accepted and disclosed in the journal. Anything more (credits, research, free techs): no-go |
     | **G7 state after reload** | Save during a stretch, reload, and read the state: human or AI, soak on or off | Its answer sets ruling 21's resume step |

     Also measured, without a gate:
     - how the AI answers diplomacy and trade offers (`debug.err` OnPerformTrade, InteractionWnd);
     - seconds per turn under soak;
     - whether `debug.err` grows during play (ruling 10).
   - **Why.**
     - Every takeover claim is static: strings, static analysis and forum posts. None has been observed in
       this build.
     - The votes flagged exactly these unknowns: event handling, diplomacy, fairness, reload state and
       console input.
     - Forking protects the campaign from a failed probe.
   - **Cost if wrong.** One window, about 45-60 minutes (**estimate**). If the reload fails, the
     campaign keeps up to 3 probe turns the AI played.

### Engine hand-over

4. **The console is a narrow channel: a Rust whitelist, typed key by key, replies read from `savelog`.
   The model never touches the console.**
   - **Decision.**
     - A new `game-controller galciv4` command group sends console lines through the agent. The CLI and
       MCP take only these shapes, checked in Rust against a fixed grammar:
       - `ai`;
       - `soak <1-20> events` and `soak <1-20>`;
       - `disablesoak`, `resumesoak`;
       - `clearlog`;
       - `savelog harness_reply.txt`;
       - `listplayers`;
       - `liststat <Stat> [breakdown]`, where Stat is one of the 10 stat series names plus Fertility;
       - `showdifficulties`;
       - `help <cmd>`, only for the commands above.

       Anything else is refused before sending. Cheats (`completeresearch`, `modcredits`, `fow`, `god`,
       `localplayer`, `aioffertrade`, …), `run` and `turn` alone are never sent.
     - **Flow of one call**, every step under `require_foreground`:
       1. Open the console with the backtick key and check it is open (a 1440p template, as `[screens.console_open]`
          in Stellaris).
       2. Send `clearlog`, then the command, then `savelog harness_reply.txt`. Characters go one by one
          with `key` for `[a-z0-9 _.]`. `type_text` (KEYEVENTF_UNICODE) is used only once G1 shows that
          the console accepts it.
       3. Read the reply file through the agent (`galciv4_docs`, at the path recorded in G1).
       4. Close the console, even when reading failed, as Stellaris does.
     - **Keys the model may never press** go into `FORBIDDEN_COMBOS` before `EnableCheats=1` is written:
       the backtick, ctrl+r (CompleteTechResearch), f1-f4 (Teleport, Clone, Restore, Destroy), and a bare `r` on
       the galaxy map. The pilot's `key` tool refuses them. The manifest's unverified
       `rush_buy = "r"` is removed.
   - **Why.**
     - Enabling cheats turns on debug keys that the pilot's key filter does not block today (E12, E13).
     - The Civ VI rule "never send model-written Lua" applies to the console as well.
     - `savelog` gives text, and the controller has no OCR.
     - Key-by-key input avoids the unverified Unicode injection.
   - **Cost if wrong.**
     - If `savelog` writes outside the read roots, replies fall back to templates of the last console
       line, read with `text_mask_diff_search` as Stellaris reads `human_ai`. That means 5-6 more
       templates.
     - Key-by-key typing costs about 1 s per command.

5. **Stretches: `soak N events` from a known human state, N = 5 (2 in danger), never indefinite, stopped
   only by N or by `disablesoak`.**
   - **Decision.**
     - The controller keeps a soak state: `human`, `soaking(until_turn)` or `unknown`. It is persisted
       in the campaign state (`_load_campaign_state`).
     - **Start** (`galciv4 stretch N`):
       - Only from `human`.
       - It sends `soak N events` and requires all four replies from G2.
       - It then presses TAB once through the autopilot's turn verification. Soak starts after the turn
         it was typed in (Illauna).
       - A partial reply, such as "Stopping Soak Test", means we were already soaking. The state
         becomes `unknown`, and resolution runs.
     - **Resolution from `unknown`:**
       1. `disablesoak` ("Disabled soak for local player").
       2. `ai` until the reply is "AI turned off for player", at most 2 toggles, as in
          `HumanAiReader.toggle_until`.
       3. Then `human`. A failure calls `_needs_attention`.
     - **End.** The stretch ends when `TurnNum` (ruling 9) reaches `until_turn`, and the hand-back
       signature from G5 is seen. The stretch then counts as `stretch ok`.
     - **Stretch length.** Settings `[governor] stretch_turns = 5` and `danger_stretch_turns = 2`, in
       the GalCiv IV `pillars.toml`. Stretches drop to 2 while any world is in danger (ruling 16). They
       never drop to 1, since one-turn stretches cost Civ VI the AI's plans.
     - `soak` without N, a bare `ai`, and `turn` alone are never sent. `resumesoak` is used only if G7
       shows that a reload keeps soak half-on.
   - **Why.**
     - Toggles cannot be repeated safely (E5).
     - A bounded soak hands back by itself, as Civ VI `autoplay N` does, so a lost reply cannot leave
       the AI playing forever.
     - Five turns: research completed about every 14 turns (4 in about 56), so a decision every 5 turns
       sees each completion within one stretch. Events hold the turn anyway.
     - Civ VI's 4-turn stretch kept the AI's plans where 1-turn stretches lost them (issues.md:19).
   - **Cost if wrong.**
     - If toggling to human every 5 turns resets the AI's plans, the record shows it: stretch outcomes,
       idle queues at hand-back. The fix is `ai hold` if G4b allows it, or longer stretches.
     - A 2-turn danger stretch delays an urgent check by at most 1 turn.

6. **Held turns go to the model with the event's corpus record attached. What the AI answers is
   recorded, not blocked.**
   - **Decision.**
     - During a stretch, a held turn looks like this: the HUD is dimmed (the existing `turn_check`), and
       `debug.err` shows `TriggerEvent <id> Player <our name>`, or `Unhiding` of the event window, with
       no later `EndTurn`.
     - The governor then:
       1. maps `<id>` to the corpus through the alias (`event:<id>`), or, when the log is silent, sends
          the title crop to `corpus search`, as today;
       2. makes one model call with the full record (every choice with its effects) and the
          `strategy.md` §5 rules, choosing an option index;
       3. clicks the option by the button column. The positions for 2, 3 and 4 options are measured at
          1440p. At 4K they sat at x≈380-480, y 526-686;
       4. reads back: the dialog closes, and the next turn arrives or the hold ends.
     - An event the model cannot place goes to `run_episode` (vision).
     - **What the AI answers for us is recorded:**
       - trades and treaties, from `debug.err` OnPerformTrade;
       - first contacts;
       - diplomacy, from InteractionWnd without a hold.

       These are `ai_made` rows in the record (ruling 12), and "AI trades since the last decision" goes
       into the briefing. The harness does not block them: under soak it has no hook.
   - **Why.**
     - E2: all 16 events matched written rules. One call with the record costs about 2 calls fewer than
       today's lookup (E1: events took 2-3 calls).
     - The strategy's "never trade away technology" cannot be enforced under soak. It can be measured.
   - **Cost if wrong.**
     - A wrong option is a one-shot choice, as it is today.
     - If the AI trades technology away, the record shows it within a stretch. The response is the
       Strategist's; a tighter hook is out of scope.

7. **Between stretches, `Gc4Governor` decides. Its orders are scripted screen flows with read-back. An
   empty research slot is always filled.**
   - **Decision.**
     - `src/pilot/galciv4_governor.py`: `Gc4Governor(Governor)`, overriding the same set that
       `Civ6Governor` overrides (`civ6_governor.py:213-918`): `_build`/`_build_agents`,
       `override`/`set_speed`/`set_months`, `_set_campaign`, `_trend`, `_start`, `_handle_request`,
       `_run_until_next_decision`, `_decide`/`_apply`, `_records_section`.
     - `src/pilot/galciv4.py`: `ControllerGalCiv4`, `FakeGalCiv4`, and the pure checks (rulings 12-17).
     - `cli.py:88-100` dispatches `--game galciv4` to it when `PILOT_GC4_GOVERNOR=1`. Otherwise
       `Pilot` runs as today.
     - **Order kinds**, each a controller flow with a template read-back:
       - `research <tech id>`: the research screen; click the tech; read back through the save's
         current research, or the screen;
       - `policy <slot> <policy id>`: the Colonial Charter Government tab; drag (drags work here, E2);
         read back by a pixel diff of the slot region;
       - `rush <world|shipyard>` (ruling 15);
       - `stretch <n>` (ruling 5, in-band);
       - `ask <text>`: a non-blocking question to the human, as in Stellaris ruling 15.

       Leaders and ministers stay with `run_episode` until the record shows that the AI leaves them
       alone.
     - **Research blocker** (the Civ VI ruling 16 analogue). At hand-back, when research is empty
       (G5) and the answer names none, the governor asks once more. Then it orders the first researchable
       tech in the strategy's preferred list, marked "filled by the governor".
     - **Pillars.** A new `corpora/galciv4/pillars.toml` (game-pillars design) holds:
       - pillars research, expansion, economy, military and influence;
       - metrics from the stat series (Research, Population, Credits, MilitaryPower, Influence);
       - `stall_turns`, `[orders]` as in Civ VI, and the stretch settings.
     - Dates are `T<n>` from `TurnNum`, so `months()` and `month_index` work unchanged. The calendar date
       (Jan 2329 + (T−1) months) is shown in brackets for the journal.
   - **Why.**
     - The base class already provides the run loop, pause, requests, `needs_attention`, auto-recovery,
       the model pool, chat, the Strategist and event review. The Civ VI subclass shows the seam.
     - Research is the one model lever that E1 shows holding everywhere (Civ VI 5 of 5).
     - `T<n>` gives GalCiv IV outcome scoring for the first time (E13).
   - **Cost if wrong.**
     - A scripted flow that misreads its screen changes nothing: each flow refuses to click when its
       template does not match.
     - A research order the AI overrides under soak is counted, and the lever is flagged
       (ruling 13).

### Game settings

8. **`Prefs.ini` through a narrow write root, edited only with the game closed.**
   - **Decision.**
     - `install.ps1` gains a write root `galciv4_prefs` (the `galciv4_docs` path, allow `Prefs.ini`
       only). It is added **only** with a new installer switch `-GalCiv4Prefs`, used on mini-rig2, so
       the user's PC never gets it.
     - `game-controller galciv4 prefs` edits `key=value` lines in place, keeping every other line and
       the encoding. It refuses while the GalCiv IV window exists (agent `/health`), because the game
       rewrites the file on exit.
     - Values:

       | Key | Now (mini-rig2) | Set | Why |
       |---|---|---|---|
       | `EnableCheats` | 0 | 1 | The console (ruling 4). Written only after the forbidden keys (ruling 4) are deployed |
       | `AutoSaveFrequency` | 5 | 1 | A `TurnNum` every turn for the clock and the watchdog, and at most 1 turn lost in a hang (rulings 9, 20, 21) |
       | `EnableTutorial`, `EnableScreenExplanationDialogs` | 1 | 0 | Popups that hold turns |
       | `ShowPreBattleScreen`, `AutoStartBattleViewer`, `MoveCameraToViewBattles` | 1 | 0 | Battle screens that would hold a soak |
       | `ShowBattlesDuringSoak` ([Hidden]) | 1 | 0 | Not settable in the UI |
       | `SkipIntro` | 0 | 1 | One step less in the relaunch |

     - The prior file is kept as `Prefs.ini.harness-bak` through the same write root (added to `allow`).
       The values are read back after the next launch.
   - **Why.**
     - Civ VI's `civ6_options` root for `AppOptions.txt` is the precedent.
     - A file edit is deterministic and can be read back. The options screen at 1440p is not calibrated,
       and one key cannot be set in the UI at all.
   - **Cost if wrong.**
     - An agent reinstall on mini-rig2, which restarts the Civ VI tuner relay, is done only in window 1.
     - If a per-turn autosave slows turns too much (G-measure: the 2024 baseline was 1.1-1.4 s against
       0.7-1.1 s), set `AutoSaveFrequency=2`. That doubles the worst-case replay.

### State reading

9. **Sidecar reader: turn, GUID and freshness from the last few KB of a save.**
   - **Decision.**
     - `galciv4.rs` reads the size (`/files/list`), then the last 4 KB of the newest `.GC4Sav` in
       `Saves/`.
     - It parses the end-of-central-directory record and raw-inflates TurnNum.txt, Guid.txt and
       Description.txt (they are deflated, E7).
     - It refuses saves without these entries (versions before 4.x).
     - It retries while the central directory or a CRC is incomplete. It judges freshness by
       `TurnNum`, never by mtime or zip dates (E7: zip dates are a month off).
     - Uses:
       - the governor's turn clock;
       - campaign identity: GUID equals the campaign's (ruling 2);
       - "an autosave landed";
       - the pilot's turn count (ruling 24).
   - **Why.** It is the cheapest reliable turn signal. The HUD date is only a pixel difference.
   - **Cost if wrong.** A few KB per read. If the save is caught mid-rotation, the reader retries.

10. **`debug.err` tailer: live signals, if 4.1.1 still writes them.**
    - **Decision.**
      - Offset reads of `galciv4_docs/debug.err`, handling truncation: the file is recreated at launch,
        so a smaller size means offset 0.
      - Parsed lines:
        - `EndTurn N`, `StartTurn N`, `Start/End AI planning turn N`, used for turn progress. "Turn
          Complete" is not used; it is missing on some turns (E8).
        - `Unhiding <Wnd>`: popup opened. There are no close events, so the screen confirms.
        - `TriggerEvent <id> Player <name>`: the event and its owner.
        - OnPerformTrade: AI trades (ruling 6).
        - Battles, autosave steps, and "was colonized by Player".
      - Paths and EOS ids in the file never go into briefings, telemetry or git.
    - **Why.** Turn progress without screenshots, event ids for the corpus, and popup kinds before any
      vision call. Those are the Stellaris `game.log` roles.
    - **Cost if wrong.** If 4.1.1 does not flush during play (G-measure), the tailer is off. The
      watchdog then uses `TurnNum` plus the HUD date, and events use the title crop.

11. **Save reader stage 1 (stats, tech, event history) and the briefing. Stage 2 comes from diffs.**
    - **Decision.**
      - **Stage 1**, in `galciv4.rs` (flate2, streamed; version gate on the 4.1.1 header, refusing
        others loudly):
        - the string pool and hash → name;
        - the 10 stat series per block;
        - the tech records;
        - the event-history pairs;
        - planet names.
      - Anchors validate themselves (sizes, plausibility, known names). There are no hard-coded offsets.
      - Our block is identified by matching the stat series against `liststat` values of the local
        player (ruling 4), not by order.
      - It reads the save once per decision, never per turn: 17+ MB over 2 agent requests, about 1 s of
        parsing.
      - **Briefing** (~2 KB, the Stellaris shape):
        - `T<n>` and the derived date;
        - credits and net per turn, research, manufacturing, population, approval and influence, with
          5- and 10-turn trends;
        - researched techs, current research and progress;
        - our events in the last stretch, with corpus ids;
        - AI trades;
        - soak state and the last stretch's outcome;
        - rivals **only as the median of the major-faction blocks and our rank**, never per rival.
      - **Stage 2** (planet owner, population, queues, policies, fleets, diplomacy) comes from diffing
        consecutive per-turn saves after single known actions. It is scheduled only after stage 1
        briefs 20 turns without a failure.
    - **Why.**
      - E7: stats and tech decode today, and nothing else does.
      - The median-and-rank rule limits the save's beyond-fog knowledge to one steering figure, the same
        use Stellaris makes of "military ÷ median".
    - **Cost if wrong.**
      - A patch moves layouts: the gate refuses, the briefing falls back to `liststat` numbers, and
        `needs_attention` names the version.
      - Stage 2 may take weeks (vote 2). Until then policies and queues are read on screen.

### The action record

12. **Every model action is followed until it resolves.**
    - **Decision.** A pure `held_outcome` for GalCiv IV, in the shape of `civ6.py:947`, over briefings
      and screen read-backs:

      | Key | Completed or held | Overridden or failed | Neutral | Source |
      |---|---|---|---|---|
      | `event` | The dialog closed and the stretch went on | The dialog stayed open after the click | – | Screen, `debug.err` |
      | `research` | The tech became researched, or is still current at the window end | Current research changed while ours was still researchable | Our own later order | Save tech records |
      | `policy` | The slot region is unchanged at the next decision | The slot changed (the AI re-slotted) | Our own later order | Pixel diff of the charter crop taken after our change |
      | `rush world`, `rush shipyard` | The item completed next turn | Refused (the game's message), or not completed | – | Screen, stat jump |
      | `stretch` | N turns, handed back | Ended early: stall, or reply missing | Held by an event (not a failure) | `TurnNum`, replies |
      | `crisis <step>` | Per step (ruling 17) | – | – | – |
      | `ai_made trade` | Informational only, not rated | – | – | `debug.err` |

      Windows: research resolves when the tech completes or after 20 turns; policies after 20 turns.
    - **Why.** It is the Civ VI lesson (E1 of the Civ VI design): acceptance is not the outcome.
      Under soak, the open question is exactly whether the AI keeps the model's research and policies.
    - **Cost if wrong.** A misread slot diff, for example the charter scrolled. The flow opens the same
      tab at the same scroll, and an unmatched template resolves `unknown`.

13. **Stick rates and where they go: the Civ VI record, shared code, no pressure factor.**
    - **Decision.**
      - After the Stellaris branch's planned move of the record helpers to `src/pilot/record.py`, GalCiv
        IV reuses `order_record`, `order_record_text`, `order_outcome` rows, `telemetry.campaign_events`
        and `log.state.info["order_record"]`.
      - Settings go in `pillars.toml` `[orders]`: window 30 turns, widened to 8 resolved; minimum 3
        samples; weak rate 0.5.
      - A flagged key reads "does not stick under soak". The frame adds: "the AI replaces your
        <kind> during stretches: use it only at hand-back, when the AI has nothing current".
      - There is no pressure factor (Civ VI ruling 15: a failing channel is not a failing pillar).
    - **Why.** Two games already share this shape, so a third copy would drift.
    - **Cost if wrong.** An advisory line the model ignores. The record itself shows it.

### Rush-buys

14. **Rush rules under soak: the AI spends our credits; the model rushes only in danger or when credits
    sit idle.**
    - **Decision.** A pure `rush_check(briefing, target, price)` in `galciv4.py`, in the shape of
      Civ VI `check_orders`. It refuses when:
      - **not in danger and not idle.** "Idle" means credits ≥ 3 × reserve for ≥ 10 turns under soak,
        with income ≥ 0. E9: the AI spends by its own strategy, so peacetime rushes by the model would
        double-spend.
      - **reserve.** The reserve is max(300, 20 × |net income| when income is negative). In danger
        (ruling 16) the reserve is 200 for defensive rushes only: the AI's own at-war buffer (E9).
      - **price over the cap.** The cap is 50% of the credits above the reserve per rush, and 100% for
        an in-danger defensive rush.
      - **the item finishes anyway**, at ≤ 2 turns left.
      - **the game would refuse**: already rushed this month, a government that forbids it, or a
        shipyard item that is not a ship design.
      - **a non-defensive rush while any world is in danger** ("in danger first").

      The priority order comes from `strategy.md`: a defender at the shipyard nearest the besieged world
      first, then colony ships early, then manufacturing districts. Control is checked only against the
      game's own refusal (E9: 100 stock, 1 per rush). `strategy.md:79`'s "200 credits is about a turn of
      rush-buying" is replaced by measured prices after L4.
    - **Why.** E9: the idle 1,100 credits were a screen-play symptom. Under soak the AI's own
      `SpendUntilBroke` or `BreakEven` should spend them, and the record will show whether it does.
    - **Cost if wrong.** Credits sit idle under a passive AI. The idle rule opens the lever after 10
      turns.

15. **The rush flow: a model tool with the price read from the tooltip, clicked only after the check,
    read back next turn.**
    - **Decision.** `galciv4 rush <world|shipyard>` is a scripted flow at 1440p:
      1. Open the world or shipyard.
      2. Left-click the first queue item.
      3. Hover Rush and return the tooltip crop.
      4. The governor's model call reads credits, Control and resources from the crop. The controller
         has no OCR, so the model is the reader.
      5. `rush_check` runs on that price.
      6. Click Rush only if the check passes.
      7. Next turn: `rush` completed or not.

      A bare `r` is never pressed (ruling 4). The flow exists only after L4 has captured its positions.
    - **Why.** There is no price formula (E9), and the price appears only in the tooltip. Clicking only
      after the check keeps credits from being spent by mistake.
    - **Cost if wrong.** A misread price: the check uses the model's number. The read-back shows the
      real credit drop, and a mismatch over 10% turns the tool off for the run, with a journal line.

### Crisis

16. **Entry on losses, never on ratios. Danger drives the stretch length.**
    - **Decision.** A pure `in_crisis(briefing, prev)` is true when we are at war with a major and any
      of these holds:
      - a BesiegedPlanet or ConqueredPlanetLoss alert, from 1440p templates captured live (L7);
      - MilitaryPower down ≥ 30% within 3 turns;
      - Population down while a siege alert was seen in the last 3 turns.

      At-war status comes from the model's frame or the Relations screen until `debug.err` or the save
      is shown to carry it (**unverified**).

      `in_danger(world)` is true for a besieged world, or a core world with an enemy transport in its
      system. It sets `danger_stretch_turns` (ruling 5). An enemy nearby is not "danger": Civ VI E6
      found that "threatened" held 93% of the time.
    - **Why.** It is the Stellaris ruling-12 lesson: ratios alone flag the whole game.
    - **Cost if wrong.** A crisis entered a turn late. Under soak the AI defends meanwhile.

17. **The crisis ladder, the exits, and what the crisis never does.**
    - **Decision.** While in crisis, one step per decision, each recorded as `crisis <step>`:
      1. An urgent decision with a crisis frame: the world, the months left, the siege source.
      2. A defensive rush at the nearest shipyard (rulings 14-15, reserve 200).
      3. Draft Civilian Ships, when the tech is known and Control ≥ 100, for a **core-world** siege only.
         It uses our whole Control stock.
      4. Event answers by rule:
         - accept every ceasefire that pays us (the 13 "LosingAIWantsCeaseFire…", CeaseFire_HFY01);
         - accept a costly "AIWantsCeaseFire" only after a world was lost, or when a siege falls in ≤ 2
           months with no relief within reach;
         - accept WarAims_Completed_L0 (−10 credits a month for 100 turns) on the same terms.
      5. `ask`: "propose peace to X?" is a non-blocking question to the human.

      **Exit:** the war ends, or 6 turns pass with no alert and no loss.

      **Never:**
      - declare war;
      - propose peace or offer terms without the human;
      - move fleets (no tactical API; the AI moves them);
      - buy mercenaries (Age of Expansion only, and uncalibrated).
    - **Why.**
      - E10: only fleets stop sieges, and the AI moves the fleets under soak. The model's levers are
        money, one executive order, and answers.
      - Most AI ceasefire offers pay us (vote corrections), so a blanket "reject" would be wrong.
    - **Cost if wrong.** An accepted ceasefire we could have won: the rule accepts costly offers only
      after a loss.

### Placement

18. **Stage A only, read-only. The first question is whether the AI places Earth's Capital City.**
    - **Decision.**
      - **L5 check:** after the first stretch on the campaign, open Earth's planet screen once. Is the
        Capital City placed? The record's journal line says yes or no.
      - **Extractor:** `scripts/extract-galciv4.py` emits `data/_adjacency.json`, with the vote
        corrections included:
        - per improvement: type, placement, neighbour bonuses, level effects **as multipliers or flat**,
          blocked and required features, and capital-only, unique and district flags;
        - per feature: bonus type and value;
        - the upgrade projects;
        - planet terrain.
      - **Scorer:** `src/pilot/gc4_placement.py`, a pure rater like `civ6_placement.rate_candidates`.
        Level comes from the features plus the neighbours. Gain = level × the district's multiplier × the
        planet's base output of that yield, so planet outputs are an input.
      - **Stage A:** rate the tiles the AI actually used on Earth and one other core world, with inputs
        from hover tooltips (E11: no tile data in the save yet). It is compared with the scorer's best.
      - **Go criterion for stage B:** over ≥ 4 AI placements, the scorer beats the AI by ≥ +1 Level on
        average. Stage B is the fallback path's autopilot resolving idle core worlds, and it runs only
        on the fallback path: under soak the AI builds.
    - **Why.**
      - E11: the Capital City has been unplaced since Feb 2330. That is a permanent economic loss, and
        the engine can place it (the AI's homeworld list, `AIDefs.xml:1678-1681`).
      - Civ VI ruling 30's gate applies: measure first.
    - **Cost if wrong.** If the AI does not place the Capital City, the slow drag in agent 1.2.0
      (`issues.md:58`) is retried in window 1 on the probe copy. The extractor work is reused by the
      fallback.

### Steering by data

19. **Only for a new campaign, and only through the custom-faction editor, never a data mod. A new
    campaign needs the user's approval.**
    - **Decision.**
      - terran-2329 keeps its data (baked into the save).
      - For a new campaign the Strategist proposes Character Traits and a Priorities order: the faction's
        `PersonalityTraits` and `AICategoryWeight` (Terran defaults: Expansion 22, Tech 20, Military 18,
        …).
      - These are set in the game's custom-faction editor ("how this Civilization behaves when being
        controlled by the AI"). It gives no stat bonus and binds only our faction.
      - A `Mods/` override of `FACTION_TERRAN` is not used: it would change every Terran AI.
      - `AITechGovernorDefs.xml` is not used: it looks stale, with 10 of 133 names matching.
    - **Why.** It is the fair, faction-scoped form of the Stellaris and Civ VI mod lesson. Civ VI
      showed strategies commit for 20+ turns, and here the choice lasts the whole campaign, hence the
      approval.
    - **Cost if wrong.** A campaign with worse priorities than the defaults. It is judged against the
      same pillars as terran-2329.

### Stalls and hangs

20. **A turn-stall watchdog in `Gc4Governor._run_until_next_decision`.**
    - **Decision.**
      - It tracks the wall-clock time of the last turn change: `TurnNum`, `debug.err` `StartTurn`, or
        the HUD date diff, whichever is seen first.
      - A stretch is stalled when no turn change is seen for `stall_s` and no event is held (a held
        event is a decision, ruling 6).
      - `stall_s = max(180, 10 × median seconds per turn over the last 20 turns)`, with an injected
        clock for tests (the Stellaris design's ruling 23).
      - Steps:
        1. Take a screenshot and log `stall`. Clear known screens: a pause menu, or a cutscene after
           30 s (ruling 22).
        2. Unknown screen: `run_episode`.
        3. If the `turn_processing` busy label has been up for `stall_s` and the pause menu shows
           Save/Load greyed out (a 1440p template, the hang signature): the relaunch (ruling 21).
        4. Otherwise, after another `stall_s`: `_needs_attention` with the frame.
      - `game.py`'s `_rpc` gets a read timeout (`stall_s` + 60), so a hung controller cannot hang the
        governor (E13).
    - **Why.**
      - E3: the hang took 12 minutes to recognise and recover by hand, 28% of a session.
      - 180 s matches `BUSY_MAX_WAIT_SECS` and is 13× the slowest observed turn.
    - **Cost if wrong.** A slow late-game turn is judged a stall. Step 1 is harmless, and the hang
      needs the greyed Save/Load signature.

21. **The relaunch, AGENTS.md §7 automated, and never when the game has vanished.**
    - **Decision.** `game-controller galciv4 relaunch` is a Rust sequence. Each step is gated by a 1440p
      template and gets one attempt and a timeout:
      1. In the pause menu: Exit Game → Yes. Wait up to 60 s for the GalCiv IV window to disappear
         (`/health` title). The controller never kills a process, so a game that does not exit means
         `needs_attention`.
      2. `focus "Steam"`, then the GalCiv IV library page, then PLAY.
      3. The Stardock Launcher (focus by title), then PLAY.
      4. The main menu (intro skipped, ruling 8), then Load Game.
      5. Pick the save: the newest `harness-` or Auto-Save file whose sidecar GUID matches the campaign.
         It is chosen by file list and sidecar before any click, then selected by its row. The row order
         is measured in L8.
      6. Load. Read `TurnNum` back and compare it with the expected turn: at most `AutoSaveFrequency`
         turns lost.
      7. The console state is `unknown`: ruling 5's resolution runs, then the stretch resumes.

      Limits:
      - One relaunch per 30 minutes. A second failure in a run means `needs_attention`, and stretches
        stop.
      - **The relaunch runs only after the hang signature.** If the game window is gone, or Steam shows
        the account in use elsewhere, it is never relaunched automatically, and the harness never
        presses "Play anyway". The likeliest cause is the account being used on the user's PC.
    - **Why.**
      - E3 and AGENTS.md §7 give the steps. `AutoSaveFrequency=1` bounds the replay to one turn.
      - One Steam account means a relaunch could take the account from the user.
    - **Cost if wrong.** A hang waits for a human, which is today's state. The circuit breaker stops
      loops.

22. **Popups that hold the engine: switch them off, template the rest, and guard the shipyard at war.**
    - **Decision.**
      - `Prefs.ini` (ruling 8) removes the tutorial, the screen explanations, the battle screens and
        the soak battle views.
      - The existing known screens are re-captured at 1440p (ruling 23).
      - New known screens:
        - the probe's Explore (`o`/`x` as verified on mini-rig2) and the warship's Sentry (`n`);
        - a cutscene rule: `Unhiding CutsceneWnd` or `FullScreenBink`, then wait 30 s, then one click
          when the frame stops changing;
        - untranslated first contact.
      - **War guard:** `shipyard_idle` gains a `skip_when` condition that the controller evaluates:
        at war, the screen goes to the model instead of queueing a Colony Ship.
      - Most of these screens do not appear under soak. They matter for the fallback and for
        hand-back turns.
    - **Why.** E2: popups and idle units were 11 or more interventions. Under soak, a battle viewer or
      tutorial would hold every stretch (the Civ VI T17 lesson).
    - **Cost if wrong.** A template that also matches another dialog. `capture-template.py --against`
      checks ≥ 0.10 against other frames.

### mini-rig2 at 1440p

23. **A GalCiv IV resolution overlay, with `res-map.py` extended to screen points. Templates are
    re-captured, and new screens exist only at 1440p.**
    - **Decision.**
      - `corpora/galciv4/res/2560x1440.toml` replaces every `[screens.*]` at 1440p. That includes
        `main_galaxy_map`'s `turn_indicator_roi` and `event_modal`'s `luminance_roi`, which is in
        pixels.
      - `corpora/galciv4/res/map.toml` gives GalCiv IV's scale and anchors: date top-right, turn
        button bottom-right, dialogs and the console at the centre or top-left, as measured.
      - `scripts/res-map.py` gains mapping of `[screens.*]` `dismiss_click(s)` and `*_roi` (normalized
        or pixel) by the same anchors. Templates are still captured with `capture-template.py`.
      - New screens exist only in the overlay:
        - the console;
        - the relaunch chain: Steam PLAY, Launcher PLAY, Load Game, the save row, the pause menu hang
          signature, Exit and Yes;
        - event option columns;
        - the research and charter flows;
        - rush;
        - the siege alerts.

        With `GAME_RESOLUTION` unset (4K) they are absent, and each flow fails loudly with "manifest has
        no [screens.x]".
      - Both services' host drop-ins already set `GAME_AGENT_URL` and `GAME_RESOLUTION` for mini-rig2
        (issues.md:29).
    - **Why.**
      - E12: the known screens were measured at 4K on a PC that is no longer used.
      - Stellaris's 4K templates did not match at 1440p (best 0.19), so GalCiv IV's will not be assumed
        to either.
      - GalCiv IV keeps its positions in `[screens.*]`, which `res-map.py` does not map today.
    - **Cost if wrong.** If the UI scales proportionally, the anchors are identity and only the
      templates change: some work saved, none lost.

### Carry-over fixes

24. **Screen-pilot fixes needed by both paths.**
    - **Decision.**
      - `run_episode`'s `on_retry` uses the `Governor._on_retry` pattern for exceptions without
        `model_name` (E13). A test raises `httpx.ReadTimeout` through a real `run_with_retry`.
      - `EpisodeResult` gains `kind` and a corpus `id`, so episodes feed `order_outcome` rows.
      - The pilot counts turns from `TurnNum` (ruling 9), not from autopilot reports, and its dates are
        `T<n>`.
      - The forbidden keys from ruling 4.
    - **Why.** E1: the pilot lost 2 of 5 episodes and counted 0 turns. The retry bug turns every model
      timeout into an unresolved episode.
    - **Cost if wrong.** None beyond the tests.

---

## Rollout

Live checks need GalCiv IV to be the running game on mini-rig2. Steam allows one running game per
account, so GalCiv IV runs only while the Civ VI governor and game are stopped. The user's desktop is
never used, not even for reads.

- **Phase 0, offline (no PC, CI only).** Commits in order, each through `scripts/ci-commit.sh`:
  1. ruling 24 (pilot fixes, forbidden keys);
  2. rulings 9-10 (sidecar and `debug.err` parsers, with fixtures from the local copies: a 1 KB zip
     tail and a `debug.err` excerpt);
  3. ruling 11 stage 1 (Rust reader on synthetic fixtures built from real layouts);
  4. ruling 4 (console grammar, key-by-key encoding, reply parser);
  5. ruling 5 (soak state machine);
  6. rulings 7, 12-17 (`Gc4Governor`, `FakeGalCiv4`, record, rush and crisis checks, `pillars.toml`),
     off unless `PILOT_GC4_GOVERNOR=1`;
  7. ruling 18's extractor and scorer;
  8. ruling 23's `res-map.py` extension;
  9. ruling 8's installer switch and prefs editor.
- **Phase 1, maintenance window 1 on mini-rig2.** The Civ VI governor is paused from the dashboard and
  then stopped at a turn boundary, and the Civ VI game is exited.
  1. Reinstall the agent with `-GalCiv4Prefs`. This restarts the tuner relay, which is harmless with
     Civ VI closed.
  2. Switch Steam Cloud off for GalCiv IV (ruling 2) and read it back.
  3. Write `Prefs.ini` (ruling 8) with the game closed.
  4. Launch GalCiv IV and capture the 1440p templates and screen points (L2).
  5. Run the probe G0-G7 (ruling 3) on `harness-probe`.
  6. Run the read-only checks L3 and L4.
  7. Load `harness-terran-2329` again.
  8. Write the journal, `issues.md` and `plan.md`.
  9. Restore Civ VI if the user wants it running.
- **Phase 2, governor path live** (if G2-G4a pass). 20 turns of terran-2329 under `Gc4Governor`:
  - the record rebuilt at start;
  - the watchdog armed;
  - the relaunch tested once on purpose (Exit, then relaunch; safe, because the path only reloads our
    own save);
  - the Capital City check (L5).
- **Phase 3.** The rush tool after L4 prices. The crisis templates when an AI war happens (no war is
  staged). Placement stage A.
- **Phase 4.** A new campaign with a custom faction (ruling 19), only with the user's approval.
- **Fallback branch** (if G2, G3 or G4a fails). The same phases with the hybrid: screen play on
  mini-rig2 with the overlay, automatic event answers from the corpus, the watchdog and relaunch, and
  the rush and placement tools.
- **`plan.md` gains `[ ]` lines:** the GalCiv IV governor (soak), state reader stage 1, the record,
  rush rules, crisis ladder, placement stage A, relaunch automation, and the 1440p overlay. The spike
  line (`plan.md:67`) is ticked with its answer when stage 1 lands.
- **`issues.md` gains `[ ]` lines:**
  - the `on_retry` AttributeError;
  - the missing forbidden debug keys;
  - `shipyard_idle` queueing colony ships at war;
  - `PLAYING.md:110` "autosaves each month" (it is every `AutoSaveFrequency` turns);
  - Steam Cloud coupling between mini-rig2 and the user's PC.
- **Seams with the other games:**
  - `record.py` (after the Stellaris branch merges);
  - `Governor` hooks: `_records_section`, `event_triggers`;
  - `telemetry.campaign_events`;
  - `install.ps1` write roots;
  - `res-map.py`.

  No other game's behaviour changes. The Stellaris and Civ VI tests stay green.

---

## Testing

**Unit tests** (pytest; `scripts/ci.sh` stays green):

- **Sidecar and `debug.err`:**
  - TurnNum, GUID and Description from a real 1 KB tail, with the entries raw-inflated;
  - a 2023-format save is refused;
  - a truncated tail is retried;
  - `debug.err` turn lines, `Unhiding`, `TriggerEvent` → corpus id, OnPerformTrade;
  - truncation (a smaller file means offset 0);
  - a turn without "Turn Complete" still counts.
- **Console:**
  - the grammar accepts exactly the whitelist and rejects `completeresearch`, `ai hold`, `soak`
    without N, `turn`, `run x` and upper-case variants;
  - key-by-key encoding of `soak 5 events`;
  - reply parsing for each E4 string;
  - partial replies set the state to `unknown`.
- **Soak state machine** (`FakeGalCiv4` with scripted replies):
  - start only from `human`;
  - "Stopping Soak Test" on start → resolution (`disablesoak`, then `ai` until "turned off", at most 2
    toggles) → `human`;
  - no command is sent while `soaking`, except `disablesoak`;
  - `until_turn` from `TurnNum`;
  - a held event pauses the count without ending the stretch.
- **Governor** (the `test_civ6_governor.py` patterns):
  - a decision then a stretch of 5;
  - a held event gets one model call with the record attached, and the click is recorded;
  - research empty at hand-back → one corrective retry → filled from the preferred list;
  - in danger → stretch 2;
  - the record rebuilt from `order_outcome` rows on a second run;
  - `T<n>` dates give `month_index`.
- **Record:** `held_outcome` per key (E-table of ruling 12): research completed against overridden;
  policy slot diff unchanged against changed; rush completed against refused; stretch early end.
- **Rush:** `rush_check`:
  - the reserve at +2 and at −3 income;
  - idle after 10 turns;
  - refused at ≤ 2 turns left;
  - a non-defensive rush refused in danger;
  - the in-danger cap at 100% above the 200 reserve;
  - "already rushed this month".
- **Crisis:**
  - `in_crisis` with a siege alert, with a 30% military drop in 3 turns, and not with a nearby enemy
    alone;
  - ceasefire answers per event id (the pay-us ones accepted; a costly one accepted only after a loss).
- **Watchdog and relaunch** (injected clock, `FakeGalCiv4` screens):
  - a stall → known screen → episode → `needs_attention`;
  - the hang signature → relaunch;
  - a vanished window → `needs_attention`, never a relaunch;
  - a "Play anyway" screen → `needs_attention`;
  - the second failure trips the breaker;
  - a GUID mismatch refuses the load;
  - `_rpc` times out.
- **Pilot:**
  - `on_retry` with `httpx.ReadTimeout` retries;
  - `EpisodeResult.kind`;
  - the forbidden keys (backtick, ctrl+r, f1-f4, bare `r`).
- **Placement:** `_adjacency.json` extractor fixtures (multipliers against flat; blocked features);
  the scorer reproduces the frame-00004 "2" on Lakes next to a Research District.

**Rust:**
- the save reader stage 1 on a synthetic `Save.tmp` fragment (a stats block and 20 tech records built
  from real byte layouts) and on the 1 KB tail;
- the version gate;
- anchors fail loudly on a shifted layout;
- the console grammar;
- the `prefs` editor keeps other lines and refuses while the window exists;
- the overlay loads, and every declared 1440p template loads (the existing test).

The 17 MB save stays out of git.

**Live checks** (mini-rig2 with GalCiv IV running; never the main PC):
- **L1** (window 1, read-only): Steam Cloud off, read back; `Prefs.ini` values read back after launch.
- **L2**: 1440p captures for every screen in ruling 23; each template ≥ 0.10 from the other frames.
- **L3** (read-only): `debug.err` grows during play, is readable while the game runs, and contains 4.1.1
  turn lines.
- **L4** (read-only): hover the Rush tooltip on Earth's queue at 2 progress points and on one shipyard
  item; record the prices.
- **G0-G7** (ruling 3), on `harness-probe`.
- **L5**: after the first campaign stretch, is Earth's Capital City placed?
- **L6**: 20 turns on the governor path. Stretches, held events, AI trades, credits trend, and seconds
  per turn.
- **L7**: the first AI war. Capture the siege and conquest alerts and the ceasefire dialogs, and run the
  crisis ladder.
- **L8**: one deliberate relaunch (Exit, then relaunch), with the save-row order checked.

---

## Out of scope

- **A scripted tactical last stand, fleet moves, and mercenaries** (rulings 17, E10).
- **Proposing peace or treaties by the harness, and declaring war** (ruling 17).
- **Data mods, hot-loading data, and `AITechGovernorDefs` edits** (ruling 19).
- **Planet directives.** They need Federations and Empires, which is inactive in this save (E5).
- **Automating leaders and ministers** until the record shows the AI leaves them alone (ruling 7).
- **Save stage 2** (queues, policies, fleets, diplomacy) before stage 1 briefs 20 turns (ruling 11).
- **Placement stage B on the governor path** (ruling 18).
- **Per-rival figures in briefings** (ruling 11).
- **The main PC for anything GalCiv IV**, including reads (ruling 2).
- **HUD OCR and the perception layer** (`plan.md:66`). The sidecar, the log and the save replace it
  here.
- **Multiplayer lobby conversion and Automate as primary levers** (ruling 1).

---

## Unverified, in one place

- **Takeover:**
  - that `soak N events` holds our events for the UI and resumes after the click (static only);
  - that `ai hold` gives events to the AI (an inference from the dispatcher);
  - that the AI acts for our faction in this build (G2-G3);
  - how the AI answers diplomacy and trades for us;
  - whether toggling to human every 5 turns costs the AI its plans;
  - the soak and AI state after save and load (G7);
  - the difficulty modifiers on our player: Normal +1 Fertility against "Normal has no bonuses" (G6);
  - whether the console accepts KEYEVENTF_UNICODE input;
  - where `savelog` writes;
  - whether the console marks the campaign or affects achievements (`x-usedcheats`).
- **Environment:**
  - loading the save on mini-rig2 (MegaStructures and Warlords content);
  - whether the Steam Cloud toggle is per machine;
  - GalCiv IV's UI scale at 1440p;
  - the save-row order in Load Game;
  - the launcher's foreground behaviour.
- **State:**
  - that 4.1.1 writes and flushes `debug.err` lines during play;
  - identifying our stat block through `liststat`;
  - the turn-time cost of `AutoSaveFrequency=1` (the 2024 baseline was 1.1-1.4 s against 0.7-1.1 s);
  - at-war status in the log or the save;
  - that the event-history second value is a turn (it is not always, vote 2).
- **Economy:**
  - the rush price (no formula);
  - the approval cost of rushing (web only);
  - whether a shipyard rush needs resources in practice;
  - whether the AI spends idle credits under soak.
- **Crisis:** alert templates (no war seen yet); whether the ceasefire conversations arrive as held
  events under `soak N events`.
- **Placement:**
  - whether the AI places the Capital City;
  - that the level formula is right, beyond one frame;
  - whether Automate replaces player improvements below level 3 (`AIDefs.xml:1676`).
- **Wall-clock:** the window 1 length (45-60 minutes, an estimate).
