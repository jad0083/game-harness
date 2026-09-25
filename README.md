# Game Harness: Ultra-Low-Latency Autonomous AI Controller

An ultra-low-latency, 100% Rust-powered autonomous AI game harness that plays turn-based Windows strategy games (*Galactic Civilizations IV: Supernova*) running on a remote PC over a local network.

```
 Linux AI Controller (192.168.1.76)                  Windows 11 Gaming PC (192.168.1.77)
 ┌─────────────────────────────────────────┐         ┌─────────────────────────────────────────┐
 │ LLM Agent (Claude / Gemini / AGY)       │         │ Galactic Civilizations IV: Supernova    │
 │   └─ game-controller (Native Rust)      │         │   (Running borderless / windowed)       │
 │      • 3-tier corpus (game.toml + wiki) │         └─────────────────────────────────────────┘
 │      • autopilot (1.12s/turn baseline)  │                              ▲
 │      • stdio MCP server (13 tools)      │  HTTP/TCP 8765               │ GDI / Win32 SendInput
 │      • AVX2 SIMD diff + 80µs classifier │ ──────────────► ┌─────────────────────────────────────────┐
 │                                         │ ◄────────────── │ game-agent.exe (Native Rust)            │
 │                                         │  (JPEG / JSON)  │   • Axum 0.8 HTTP API (:8765)           │
 │                                         │  (~50ms net)    │   • GDI StretchBlt downscaling          │
 │                                         │                 │   • SIMD BGRA->RGB + JPEG encoding      │
 │                                         │                 │   • Per-Monitor V2 HiDPI Awareness      │
 └─────────────────────────────────────────┘                 └─────────────────────────────────────────┘
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for full technical documentation on system topology, SIMD luminance classification, coordinate scaling, and corpus architecture.

---

## Core Components

| Component | Path / Binary | Architecture | Performance / Capabilities |
|---|---|---|---|
| **Windows Remote Agent** | [`crates/game-agent`](crates/game-agent) & [`windows_agent/game-agent.exe`](windows_agent/game-agent.exe) | Compiled native Rust (`x86_64-pc-windows-gnu`) | ~8ms screen capture & JPEG encode; native Win32 `SendInput`, `SetCursorPos`, and `mouse_event`; Per-Monitor V2 HiDPI aware. |
| **Linux Native Controller** | [`crates/game-controller`](crates/game-controller) & [`target/release/game-controller`](target/release/game-controller) | Compiled native Rust (`x86_64-unknown-linux-gnu`) | 0.36ms RPC overhead, **1.12s per complete turn** autopilot advancement, in-memory corpus search (<500µs), stdio MCP server. |
| **3-Tier Game Corpus** | [`corpora/galciv4/`](corpora/galciv4/) | Structured TOML + Markdown + Text | 33 verified hotkeys, 8 screen signatures, 3 atomic macros, 150 Techs, 273 Planetary Improvements, 40 Executive Orders, 13 Wiki guides. |
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

# 7. Send Keyboard Combos
./target/release/game-controller key "esc"
./target/release/game-controller key "enter"

# 8. Single Turn Advancement (Tab -> Space -> Tab -> F -> Enter)
./target/release/game-controller turn

# 9. Autonomous Autopilot Loop (Halts on Event Dialogs / Modals)
./target/release/game-controller autopilot --turns 25

# 10. Query 3-Tier In-Memory Game Corpus
./target/release/game-controller corpus
./target/release/game-controller corpus search "Sublight Drives"
./target/release/game-controller corpus tech "Colonial Policies"
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
| `drag` | `x1, y1, x2, y2, button, wait` | Drag from `(x1, y1)` to `(x2, y2)` with multi-step interpolation. |
| `key` | `combo, repeat` | Press key/combo (resolves aliases like `end_turn` $\to$ `enter` via `game.toml`). |
| `type_text` | `text` | Type literal string into focused UI element. |
| `batch` | `actions: [...]` | Execute atomic multi-action sequence in a single network round-trip. |
| `wait_settle` | `timeout, threshold` | Wait for on-screen animations or AI turns to stabilize. |
| `diff` | `{}` | Compare current frame against previous capture and highlight changes. |
| `autopilot_turns`| `turns` | Run high-speed autonomous turn loop until event dialog occurs. |
| `run_macro` | `name` | Execute pre-registered macro from `game.toml` (`turn_pump`, `auto_scout_cycle`). |
| `corpus_search` | `query, limit` | Sub-millisecond in-memory search across techs, improvements, and wiki. |
| `corpus_tech` | `name` | Look up detailed tech prerequisites, unlocks, and costs. |
| `corpus_improvement` | `name` | Look up planetary district stats, costs, and adjacency rules. |
| `corpus_order` | `name` | Look up Executive Order control costs, cooldowns, and effects. |
| `corpus_strategy` | `{}` | Retrieve the complete strategic playbook (`strategy.md`). |
| `game_state` | `{}` | Query live agent status, foreground window, and screen dimensions. |
| `focus` | `title` | Bring target window to foreground by title substring. |

---

## Testing & CI

```bash
# Run native Rust unit tests (8/8 tests pass in ~0.04s)
cargo test --workspace

# Run legacy regression test suite (40/40 tests pass in ~10.8s)
.venv/bin/pytest -q
```
