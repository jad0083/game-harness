# Playing Galactic Civilizations IV through the harness

The procedure (loop, decision table, known screens, recording) is in **[AGENTS.md](AGENTS.md)**
§3–§8. This file is the log of **verified controls and UI behaviour** — only things confirmed in
play, with the date. Coordinates are in 1568×882 image space (screen 3840×2160).

## Quick reference

| Want | Do |
|---|---|
| End turn / open next pending item | `tab` |
| Run verified turns | `scripts/play/ap.sh 20` |
| One action + fresh frame | `scripts/play/act.sh click X Y` · `act.sh key K` · `act.sh drag X1 Y1 X2 Y2` |
| Read a tooltip | `scripts/play/hover.sh X Y` → `play/h.png` |
| Look up an event / tech / improvement | `game-controller corpus search "…"` → `corpus get <id>` |
| Ship orders | Explore `o` · Survey `v` · Sentry `n` · Standby `j` · Auto Colonize `c` · Go To = right-click |
| Close a panel | its *Done* button (safer than `esc`, which opens the pause menu on the bare map) |

## Memory across long games
Context gets summarized over a long game. Keep `games/<save-name>/journal.md` (current game:
`games/terran-2329/journal.md`) with the strategy, current goals, key planets/ships, and what
happened each few turns. Re-read it after a context reset or when another model takes over.

## Verified controls
Only list things confirmed in play. Record the game resolution too, since positions depend on it.

Verified 2026-09-25, game resolution 3840x2160 (screenshots downscaled to 1568x882):

- Research: click the research panel (top-left, "Not Researching"/current tech) → Research Center.
- Tutorial popups ("Greetings ...") close with their **Done** button.
- Shipyard: click the "Order the Shipyard..." advisor → select class on the right → **Build Ship**.
- `tab` selects the next idle ship. Colony ship: `c` = Auto Colonize (best known planet),
  or right-click a colonizable planet.
- Mouse wheel down zooms the map out; hovering a ship/button shows a tooltip with its hotkey.
- Advisors panel (top-right) lists pending to-dos; clicking an entry jumps to it.

Verified 2026-09-25 (afternoon, Rust agent, turn 3):

- Key injection from the Rust agent registers in-game (`esc` opened the pause menu).
- `esc` with nothing open opens the **pause menu** (Resume/Save/Load/…); a second `esc` closes it.
  So `esc` is not a free "cancel" — only use it when a panel or dialog is actually open.
- The bottom-right turn button shows the current **blocking item** (⚖ = leader/policy decision,
  green planet = colony/planet action) instead of ending the turn while "action required" items
  are pending, e.g. "A Leader is available to be assigned". (At the time `turn_pump` pressed
  `enter`; it now presses TAB — see the evening entry.) The autopilot reports `NotAdvanced`.
- `turn_indicator_roi` (the date readout, top-right) is stable frame-to-frame when no turn
  passes (diff 0.000), so an unchanged readout is a reliable "did not advance" signal.

Verified 2026-09-25 (evening, autonomous play, Mar → Oct 2329):

- **TAB ends the turn** ("Press Tab to advance to next turn") — not Enter. When something is
  pending, TAB opens it instead. The turn button's icon says what is pending:
  ▷ = ready · ⚖ = leader/policy decision · green planet = idle core world (empty build queue) ·
  green ships = idle fleet · red ! = pending event (TAB opens the event dialog).
- Ship orders (hotkey shown in each action button's tooltip): **Explore = O** (probes),
  **Survey = V** (survey ships: find and visit anomalies), **Sentry = N** (stay until an enemy
  is in sensor range), **Standby = J**, Auto Colonize = C, Go To = right-click.
- Colonial Charter: drag a leader card onto a Minister office; drag a policy from
  *Available Policies* onto an open slot. Both confirmed working through the agent's drag.
- Planet screen ("Choose a region to improve"): click an empty tile → a menu of districts
  with turn costs → click one. Dragging an improvement icon onto a tile did **not** work.
- Event dialogs: click the option button. Outcomes are in the game data — look them up first.
- Galactic News (GNN) bulletins are informational; the autopilot matches the "GNN LIVE" logo
  (`templates/gnn_live.png`) and clicks Close by itself.
- Colonial Charter → Leaders: **double-click** a recruitable card to recruit (costs credits).
  Leader stat icons: 💡 Intelligence · 👥 Social Skills · ⚡ Diligence · ✊ Resolve.
  Minister of Technology = +1 technology slot and research by Intelligence; Minister of
  Exploration = moves/range by Diligence.
- A finished colony ship opens a **boarding** dialog: click a citizen, Board, Done.
- Idle colony ships and the "Colonize Planet? Yes/No" confirmation are handled by the
  autopilot (known screens `idle_colony_ship`, `colonize_confirm`).

Verified 2026-09-25 (night, autonomous play, Feb 2331 → Jul 2333):

- **Research Center**: *Choose New Tech* on the "Research Complete!" panel; the three large
  cards get a 50% insight bonus; techs under *Additional Candidates* are selected by clicking
  them (the top-left label then shows the new tech); *Done* closes.
- **Colony ship boarding** dialog ("Boarding T.A.S. … from Earth"): click a citizen, *Board*,
  *Done* — automated as `colony_ship_boarding`.
- **Colonize confirmation** ("Colonize Planet? <name>") appears after Auto Colonize, sometimes
  only after a camera pan — automated as `colonize_confirm` (Yes).
- **Re-ordering a busy survey ship** raises "Survey in Progress — abandon the in-progress
  survey?" → always *No* (automated as `survey_abandon_confirm`).
- **Shipyard**: TAB opens it when its queue is empty ("Shipyard Idle"); class list on the right,
  *Build Ship*, *Done* — automated as `shipyard_idle` (queues a Colony Ship).
- **AI diplomacy**: an AI can open a trade screen with its own proposal. *Reject* clears the
  table; *Done* returns to a menu (trade / threaten / something else / *Goodbye*) — the menu is
  automated as `diplomacy_menu` (Goodbye). Contact before *Universal Translator* is researched is
  untranslatable; all options just close it.
- **Cutscenes** (e.g. "First Anomaly Survey"): full-screen video ~30 s, then freezes blurred until
  a click.
- **Planet screen district menu** shows an adjacency bonus as a number in a gold circle next to
  the turn cost (e.g. Financial District ②).
- **Governor**: colonies of class ≥ 10 can get a governor (becomes a Core World); the
  "Appoint a Governor" report is informational (one button).
- Relaunching the game: Steam library *PLAY* → **Stardock Launcher** window → its *PLAY* →
  intro video (`esc` skips) → main menu (*Load Game* lists *Auto-Save* and *Previous Auto-Save*).

### Known game bug: turn hangs in "Starting New Month"
GC4 Supernova can hang indefinitely while processing a turn (known bug:
[Steam thread](https://steamcommunity.com/app/1357210/discussions/0/598523169276500298/),
[forum report](https://forums.galciv4.com/515304/bug-stuck-on-ai-turn)). Signs: the pulsing
"Starting New Month" label (known screen `turn_processing`) stays for minutes, the date doesn't
change, and the pause menu has **Save / Load / Main Menu greyed out**. The autopilot waits up
to 180 s while it is visible, then reports "still processing".

Recovery (done autonomously 2026-09-25, ~15 min into a hang): `esc` → **Exit Game** → Yes →
focus the **Steam** window → green **PLAY** (Steam library page) → **Stardock Launcher** opens →
its green **PLAY** → `esc` skips the intro → **Load Game** → newest **Auto-Save** → Load.
The game autosaves each month; expect to replay a few turns.
