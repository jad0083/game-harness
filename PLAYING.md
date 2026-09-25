# Playing Galactic Civilizations IV through the harness

Tools come from the `game` MCP server. Every action returns a new screenshot; coordinates are
pixels in the most recent image.

## Turn loop
1. `status` → confirm the agent is up and the game is in the foreground (`focus_game` if not).
2. `screenshot` → read the whole state. Use `zoom` on panels with small text (resources,
   research, event text) before deciding.
3. Handle anything **blocking** first: event/choice popups, "idle ship/colony" notifications,
   empty production or research queues.
4. Give orders: colonies → production; research; ships → move/colonize/survey; diplomacy.
5. End the turn (turn button, bottom-right), then `wait` 5–30s for the AI turns, repeat.

## Precision
- If a click misses, retake the screenshot with `grid=true`, or `zoom` into the area and click
  inside the zoomed image (its coordinates are then active until the next full screenshot).
- `hover` shows tooltips. GC4 explains most numbers there.
- Prefer keyboard shortcuts once verified; record verified ones below.
- After any unexpected screen, press `esc` once and re-screenshot rather than clicking blindly.

## Memory across long games
Context gets summarized over a long game. Keep `games/<save-name>/journal.md` with the strategy,
current goals, key planets/ships, and what happened each few turns. Re-read it after a
context reset.

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
  are pending, e.g. "A Leader is available to be assigned". The `turn_pump` macro's `enter`
  then navigates to that item rather than advancing; the autopilot reports `NotAdvanced`.
- `turn_indicator_roi` (the date readout, top-right) is stable frame-to-frame when no turn
  passes (diff 0.000), so an unchanged readout is a reliable "did not advance" signal.

Verified 2026-09-25 (evening, autonomous play, Mar → Oct 2329):

- **TAB ends the turn** ("Press Tab to advance to next turn") — not Enter. When something is
  pending, TAB opens it instead. The turn button's icon says what is pending:
  ▷ = ready · ⚖ = leader/policy decision · green planet = idle core world (empty build queue) ·
  green ships = idle fleet · red ! = pending event (TAB opens the event dialog).
- Ship orders (hotkey shown in each action button's tooltip): **Explore = O** (probes/survey
  ships auto-explore), **Standby = J**, Auto Colonize = C.
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
