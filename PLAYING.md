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
