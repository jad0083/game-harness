# Controller reference: CLI and MCP tools

`target/release/game-controller` (build: `cargo build --release -p game-controller`) talks to the
Windows agent named by `GAME_AGENT_URL` (e.g. `http://<pc-address>:8765`) with the token from
`GAME_AGENT_TOKEN` or `.agent_token`. Coordinates are in the space of the last screenshot
(1568×882); the controller scales them to the PC's screen. Corpus commands work offline.

## CLI

The compiled controller binary provides full programmatic access to all agent functions:

```bash
# 1. Health & Latency Check
./target/release/game-controller health

# 2. Live State, Window Rects, and Foreground Window
./target/release/game-controller state

# 3. Bring Game Window to Foreground
./target/release/game-controller focus "Galactic Civilizations"

# 4. Capture Downscaled Screenshot
./target/release/game-controller screenshot -o current_screen.jpg

# 5. Click in Last-Image Coordinate Space (Automatically Scaled to Screen)
./target/release/game-controller click 580 490 --button left --count 1

# 6. Drag in Last-Image Coordinate Space
./target/release/game-controller drag 1510 140 640 310 --button left
# Slower drag for UIs with a drag-threshold timer or hover-sensitive drop targets
./target/release/game-controller drag 1510 140 640 310 --hold-ms 250 --steps 40 --step-ms 25 --dwell-ms 300 --wiggle

# 7. Send Keyboard Combos
./target/release/game-controller key "esc"
./target/release/game-controller key "enter"

# 8. One turn: runs the manifest's turn_pump macro, waits for the screen to settle, then
#    reports advanced (date readout changed) / dialog (HUD dimmed) / did NOT advance.
#    Refuses unless the game window is in the foreground (see `focus`).
./target/release/game-controller turn

# 9. Turn loop: stops at the first dialog or blocked turn and saves current_screen.jpg
./target/release/game-controller autopilot --turns 25

# 10. Query the game corpus (ids from `search`, bodies from `get`)
./target/release/game-controller corpus                       # what is loaded
./target/release/game-controller corpus search "draft colonists" --limit 5
./target/release/game-controller corpus get "doc:executive_orders#1"
./target/release/game-controller corpus tech "Colonial Policies"   # exact, alias, or closest name
./target/release/game-controller corpus improvement "Manufacturing District"
./target/release/game-controller corpus order "Draft Colonists"
./target/release/game-controller corpus strategy

# 11. Stellaris: briefing of the player's empire from an autosave
./target/release/game-controller stellaris brief                      # newest autosave on the PC (agent >= 1.2)
./target/release/game-controller stellaris brief path/to/autosave.sav # local file, offline
./target/release/game-controller stellaris brief --json
./target/release/game-controller stellaris take-control               # once per session: AI plays the empire (human_ai)
./target/release/game-controller stellaris install-mod                # companion mod into the game's mod folder (agent >= 1.3)
./target/release/game-controller stellaris bridge-check               # is it loaded?
./target/release/game-controller stellaris directive expand --dry-run  # console lines only
./target/release/game-controller stellaris directive expand            # apply (Stellaris must be foreground)
./target/release/game-controller stellaris log -l 30                   # tail of logs/game.log
./target/release/game-controller stellaris speed fastest               # slowest|slow|normal|fast|fastest
./target/release/game-controller stellaris pause                       # / resume; state read from the screen, safe to repeat

# 12. Civilization VI: Lua through the agent's FireTuner relay (agent >= 1.6; game started with
#     EnableTuner 1; one tuner client at a time, so close FireTuner)
./target/release/game-controller civ6 states                           # game identity, then "index<TAB>state" lines
./target/release/game-controller civ6 lua "return Game.GetCurrentGameTurn()"   # --state GameCore (default)
./target/release/game-controller civ6 lua --state InGame --timeout-ms 10000 "print('hi')"
#     prints the result (the game's first reply), then each printed line; errors (game not
#     listening: HTTP 502, no reply in time: 504, unknown state: 400) exit non-zero
# The governor surface (library corpora/civ6/lua/harness.lua, installed into the game's Lua state on
# first use and whenever the file changes; each prints one JSON line):
./target/release/game-controller --corpus corpora/civ6 civ6 snapshot   # the game as one JSON document
./target/release/game-controller --corpus corpora/civ6 civ6 order '{"kind":"research","id":"tech:pottery"}'
#     kinds: research {id}, civic {id}, policies {ids}, production {city, id},
#     purchase {city, id, currency gold|faith, max_cost?}, price {city, id, currency} (read-only);
#     ids are corpus ids, checked against data/ first; exit 2 when the game or the check refuses
./target/release/game-controller --corpus corpora/civ6 civ6 autoplay 5         # 1..50 turns by the game's AI
./target/release/game-controller --corpus corpora/civ6 civ6 autoplay-status    # / autoplay-stop
./target/release/game-controller --corpus corpora/civ6 civ6 quiet-popups      # popups.toml handlers removed (also on library install)

# 13. Launch Stdio MCP Server (Claude Code / Gemini / Antigravity)
./target/release/game-controller mcp
```

## MCP server

The controller is a stdio MCP server. Run it from the repo root so it finds `.agent_token` and
`corpora/galciv4` (or set `GAME_AGENT_TOKEN` / pass `--corpus`).

Claude Code — `.mcp.json` (in this repo):
```json
{ "mcpServers": { "game": { "command": "./target/release/game-controller", "args": ["mcp"],
  "env": { "GAME_AGENT_URL": "http://<pc-address>:8765" } } } }
```

Gemini CLI — `.gemini/settings.json` (in this repo):
```json
{ "contextFileName": ["GEMINI.md", "AGENTS.md"],
  "mcpServers": { "game": { "command": "./target/release/game-controller", "args": ["mcp"], "cwd": ".",
    "env": { "GAME_AGENT_URL": "http://<pc-address>:8765" }, "timeout": 600000 } } }
```

### Available MCP Tools

| Tool | Parameters | Description |
|---|---|---|
| `screenshot` | `{}` | Capture full frame from Windows agent with dynamic scaling metadata. |
| `click` | `x, y, button, count, wait` | Click at `(x, y)` in last-image space (automatically scaled to physical screen). |
| `drag` | `x1, y1, x2, y2, button, wait, hold_ms, steps, step_ms, dwell_ms, wiggle` | Drag from `(x1, y1)` to `(x2, y2)` with multi-step interpolation. Optional timing: `hold_ms` after press (default 30), `steps` (12, 2..120), `step_ms` (15, 5..200), `dwell_ms` at target before release (30, 0..3000), `wiggle` ±3 px at target (false). |
| `key` | `combo, repeat` | Press key/combo; manifest aliases resolve (e.g. `end_turn` → `tab`, `explore` → `o`). |
| `type_text` | `text` | Type literal string into focused UI element. |
| `batch` | `actions: [...]` | Execute atomic multi-action sequence in a single network round-trip. |
| `wait_settle` | `timeout, threshold` | Wait for on-screen animations or AI turns to stabilize. |
| `diff` | `{}` | Compare current frame against previous capture and highlight changes. |
| `autopilot_turns`| `turns` | Run the turn loop; each turn is verified by the date readout changing and known screens are cleared automatically. Stops with a screenshot at the first unknown dialog (HUD dimmed) or blocked turn (indicator unchanged). Refuses if the game is not the foreground window. |
| `run_macro` | `name` | Execute a macro from `manifest.toml` (`turn_pump` = TAB, `auto_scout_cycle` = TAB then O). |
| `corpus_search` | `query, limit` | Keyword search over records, playbook and reference docs; returns ids + one-line match snippets. |
| `corpus_get` | `id` | One compact record (`tech:colonial_policies`) or one prose chunk (`doc:anomalies#0`, `strategy#2`). |
| `corpus_tech` / `corpus_improvement` / `corpus_order` | `name` | Name lookup (exact, alias, or closest match) in the generated `data/*.json` records: cost, prerequisites, effects, unlocks, adjacency, requirements. |
| `corpus_info` | `{}` | Loaded counts, hotkeys, macros, and screen names. |
| `corpus_strategy` | `{}` | The complete strategic playbook (`strategy.md`). |
| `game_state` | `{}` | Query live agent status, foreground window, and screen dimensions. |
| `focus` | `title` | Bring target window to foreground by title substring. |
| `stellaris_briefing` | `json` | *Stellaris corpus only.* Briefing from the newest monthly autosave (fetched via the agent's `/files`): date, government, stockpile and net per resource with deficits flagged, power, research and options, policies, planets (occupied ones flagged), wars (our side's and our own battles, invasions, force peace), shipyards at war, market prices. About 2 KB of text; `json` adds policy dates, per-colony jobs, unemployment, districts and queue, the market block and `governor_*` variables. |
| `stellaris_take_control` | `{}` | *Stellaris only.* Hand the empire to the game's AI: leave observer mode if needed, switch `human_ai` on (the console's reply is read on screen). Once per session. |
| `stellaris_directive` | `name` | *Stellaris only.* Apply a governor directive from `corpora/stellaris/directives.toml`: clear other directive flags, set `governor_directive_<name>` and its policies; confirmed by a scoped `GOVERNOR_APPLIED <name> <nonce>` in game.log. Checks the game is foreground before every keystroke. |
| `stellaris_speed` | `speed` | *Stellaris only.* Set the game speed: slowest, slow, normal, fast, fastest (`-` ×4 then `=` ×n; fastest ≈ 2.5 in-game months per second). |
| `stellaris_pause` | `paused` | *Stellaris only.* Pause or resume; reads the state from the screen first (the yellow "Paused" label), so it is safe to repeat. |
| `stellaris_log` | `lines` | *Stellaris only.* Tail of `logs/game.log`. |
| `stellaris_pick_tech` | `prefer` | *Stellaris only.* Pick the first preferred tech (≤ 6 ids) offered in a field under 10% done: Technology → swap → option card (only the first 4 offered are clickable); unverified until the next autosave. |
| `stellaris_market_sync` | `orders` | *Stellaris only.* Make the monthly market trades equal `orders` (≤ 2 of `{side, resource, amount 1..25}`, resources from the manifest); a new trade starts at the resource's own amount (`[ui.market]` `new_trade_amount`: 10 energy/minerals/food, 5 consumer goods, 1 motes/gases/crystals), and adding alloys or sr_* is refused before anything is sent until their fractional start is measured; computed from the last autosave, so call at most once per autosave. |

