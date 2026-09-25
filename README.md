# Game Harness: Ultra-Low-Latency Autonomous AI Controller

An ultra-low-latency, 100% Rust-powered autonomous AI game harness that plays turn-based Windows strategy games (*Galactic Civilizations IV: Supernova*) running on a remote PC over a local network.

```
 Linux AI Controller (192.168.1.76)                  Windows 11 Gaming PC (192.168.1.77)
 ┌─────────────────────────────────────────┐         ┌─────────────────────────────────────────┐
 │ LLM Agent (Claude / Gemini / AGY)       │         │ Galactic Civilizations IV: Supernova    │
 │   └─ game-controller (Native Rust)      │         │   (Running borderless / windowed)       │
 │      • game corpus (manifest+data+docs)│         └─────────────────────────────────────────┘
 │      • autopilot (verified turn loop)   │                              ▲
 │      • stdio MCP server (19 tools)      │  HTTP/TCP 8765               │ GDI / Win32 SendInput
 │      • frame diff + luminance check     │ ──────────────► ┌─────────────────────────────────────────┐
 │                                         │ ◄────────────── │ game-agent.exe (Native Rust)            │
 │                                         │  (JPEG / JSON)  │   • Axum 0.8 HTTP API (:8765)           │
 │                                         │  (~50ms net)    │   • GDI StretchBlt downscaling          │
 │                                         │                 │   • BGRA->RGB + JPEG encoding           │
 │                                         │                 │   • Per-Monitor V2 HiDPI Awareness      │
 └─────────────────────────────────────────┘                 └─────────────────────────────────────────┘
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for system topology, the modal-detection heuristic, coordinate scaling, and the corpus layout.

---

## Core Components

| Component | Path / Binary | Architecture | Performance / Capabilities |
|---|---|---|---|
| **Windows Remote Agent** | [`crates/game-agent`](crates/game-agent) & [`windows_agent/game-agent.exe`](windows_agent/game-agent.exe) | Compiled native Rust (`x86_64-pc-windows-gnu`) | ~8ms screen capture & JPEG encode; native Win32 `SendInput`, `SetCursorPos`, and `mouse_event`; Per-Monitor V2 HiDPI aware. |
| **Linux Native Controller** | [`crates/game-controller`](crates/game-controller) → `target/release/game-controller` (build with `cargo build --release`; `.mcp.json` points here) | Compiled native Rust (`x86_64-unknown-linux-gnu`) | ~1 ms agent round-trip; autopilot that verifies each turn by the HUD date changing and stops on dialogs or blockers; in-memory corpus (search <1 ms); stdio MCP server. |
| **Game Corpus** | [`corpora/galciv4/`](corpora/galciv4/) | `manifest.toml` + generated `data/*.json` + `docs/*.md` + `strategy.md` | 33 hotkeys, 8 screen signatures, 3 macros; 130 techs, 528 improvements, 66 executive orders, 203 policies, 355 ship components, 167 starbase modules and 994 events generated from the game's own XML by `scripts/extract-galciv4.py`; 13 reference docs chunked into 168 searchable pieces. |
| **Legacy Pytest Suite** | [`src/harness/`](src/harness/) & [`tests/`](tests/) | Python 3.12 (FakeBackend fixtures) | 40/40 legacy tests passing in 10.86s. |

---

## Remote Windows Agent Setup & Deployment

The remote Windows agent is a single, self-contained native Rust executable (`game-agent.exe`, ~1.4 MB) with **zero external dependencies** (no Python, no Visual C++ runtimes required).

### Option A: Automated Network Install (from Linux Controller)
1. On the Linux controller, serve the agent installer and shared token:
   ```bash
   ./scripts/serve-agent.sh
   ```
2. On the Windows gaming PC, open PowerShell (standard user) and run the one-liner printed by the script:
   ```powershell
   $env:GA_SRC='http://192.168.1.76:8000'; irm "$env:GA_SRC/install.ps1" | iex
   ```
   *This automatically registers a non-elevated Logon Task in `%LOCALAPPDATA%\GameAgent` and configures the local Windows Defender firewall rule for port 8765.*

### Option B: Cross-Compiling on Linux
You can recompile the Windows agent binary directly on the Linux controller:
```bash
cargo build --target x86_64-pc-windows-gnu --release --bin game-agent
cp target/x86_64-pc-windows-gnu/release/game-agent.exe windows_agent/game-agent.exe
```

---

## Command-Line Interface (CLI)

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

# 11. Launch Stdio MCP Server (Claude Code / Gemini / Antigravity)
./target/release/game-controller mcp
```

---

## Model Context Protocol (MCP) Server

To connect Claude Desktop, Claude Code, or Antigravity IDE directly to the game harness, add the following to your MCP configuration (`.mcp.json` or `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "galciv4": {
      "command": "/mnt/codeman-cases/game-harness/target/release/game-controller",
      "args": ["mcp"],
      "env": {
        "GAME_AGENT_URL": "http://192.168.1.77:8765",
        "GAME_AGENT_TOKEN": "<your-token>"
      }
    }
  }
}
```

### Available MCP Tools

| Tool | Parameters | Description |
|---|---|---|
| `screenshot` | `{}` | Capture full frame from Windows agent with dynamic scaling metadata. |
| `click` | `x, y, button, count, wait` | Click at `(x, y)` in last-image space (automatically scaled to physical screen). |
| `drag` | `x1, y1, x2, y2, button, wait, hold_ms, steps, step_ms, dwell_ms, wiggle` | Drag from `(x1, y1)` to `(x2, y2)` with multi-step interpolation. Optional timing: `hold_ms` after press (default 30), `steps` (12, 2..120), `step_ms` (15, 5..200), `dwell_ms` at target before release (30, 0..3000), `wiggle` ±3 px at target (false). |
| `key` | `combo, repeat` | Press key/combo (resolves aliases like `end_turn` $\to$ `enter` via `game.toml`). |
| `type_text` | `text` | Type literal string into focused UI element. |
| `batch` | `actions: [...]` | Execute atomic multi-action sequence in a single network round-trip. |
| `wait_settle` | `timeout, threshold` | Wait for on-screen animations or AI turns to stabilize. |
| `diff` | `{}` | Compare current frame against previous capture and highlight changes. |
| `autopilot_turns`| `turns` | Run the turn loop; each turn is verified by the date readout changing. Stops with a screenshot at the first dialog (HUD dimmed) or blocked turn (indicator unchanged). Refuses if the game is not the foreground window. |
| `run_macro` | `name` | Execute pre-registered macro from `game.toml` (`turn_pump`, `auto_scout_cycle`). |
| `corpus_search` | `query, limit` | Keyword search over records, playbook and reference docs; returns ids + one-line match snippets. |
| `corpus_get` | `id` | One compact record (`tech:colonial_policies`) or one prose chunk (`doc:anomalies#0`, `strategy#2`). |
| `corpus_tech` / `corpus_improvement` / `corpus_order` | `name` | Name lookup (exact, alias, or closest match) in the generated `data/*.json` records: cost, prerequisites, effects, unlocks, adjacency, requirements. |
| `corpus_info` | `{}` | Loaded counts, hotkeys, macros, and screen names. |
| `corpus_strategy` | `{}` | The complete strategic playbook (`strategy.md`). |
| `game_state` | `{}` | Query live agent status, foreground window, and screen dimensions. |
| `focus` | `title` | Bring target window to foreground by title substring. |

---

## Testing & CI

```bash
cargo test --workspace          # controller: imaging, MCP coordinate mapping, corpus; agent: batch validation
cargo clippy --workspace --all-targets
.venv/bin/pytest -q             # legacy Python harness (no longer deployed)
```

## Game corpus

`corpora/<game>/` is the only place game knowledge lives; the controller is game-agnostic.

```
corpora/galciv4/
  manifest.toml   hotkeys, screen signatures, macros — hand-verified
  strategy.md     playbook for the model, also chunked for search
  data/           GENERATED records, one <kind>.json each (tech, improvement, order, policy,
                  ship_component, starbase_module, event) — see data/README.md
  docs/*.md       reference prose with Source:/License: headers, chunked at ~1500 chars
```

Search returns ids and match snippets; `get` returns one record or chunk. Entity records are
generated from the game's own definition files, not scraped from the wiki, so costs and
prerequisites match the installed version. To regenerate after a game patch, copy
`<install>\Data\Gameplay` and `<install>\Data\English\Text` from the PC (`scripts/receive-file.py`
accepts a zip over the LAN) and run:

```bash
python3 scripts/extract-galciv4.py <folder-with-Gameplay-and-Text> --game-version 4.1.1
```

Current counts (4.1.1): 130 techs, 528 improvements, 66 executive orders, 203 policies, 355 ship
components, 167 starbase modules, 994 events. Only tech/improvement/order have name-lookup
commands; reach the other kinds with `corpus search` + `corpus get` (e.g. `event:precursor_probe`,
whose `choices` field lists each button's exact outcome).

`data/_meta.json` records the game version, generator commit and counts. The wiki `docs/` can lag
the game (the wiki lists Colonial Policies at 27 research; the game data says 24): when they
disagree, the generated records win.
