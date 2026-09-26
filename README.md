# Game Harness: Ultra-Low-Latency Autonomous AI Controller

An ultra-low-latency, 100% Rust-powered autonomous AI game harness that plays turn-based Windows strategy games (*Galactic Civilizations IV: Supernova*) running on a remote PC over a local network.

```
 Linux AI Controller (192.168.1.76)                  Windows 11 Gaming PC (192.168.1.77)
 ┌─────────────────────────────────────────┐         ┌─────────────────────────────────────────┐
 │ LLM Agent (Claude / Gemini / AGY)       │         │ Galactic Civilizations IV: Supernova    │
 │   └─ game-controller (Native Rust)      │         │   (Running borderless / windowed)       │
 │      • game corpus (manifest+data+docs)│         └─────────────────────────────────────────┘
 │      • autopilot (verified turn loop)   │                              ▲
 │      • stdio MCP server (19 tools, +5 Stellaris)      │  HTTP/TCP 8765               │ GDI / Win32 SendInput
 │      • frame diff + luminance check     │ ──────────────► ┌─────────────────────────────────────────┐
 │                                         │ ◄────────────── │ game-agent.exe (Native Rust)            │
 │                                         │  (JPEG / JSON)  │   • Axum 0.8 HTTP API (:8765)           │
 │                                         │  (~50ms net)    │   • GDI StretchBlt downscaling          │
 │                                         │                 │   • BGRA->RGB + JPEG encoding           │
 │                                         │                 │   • Per-Monitor V2 HiDPI Awareness      │
 └─────────────────────────────────────────┘                 └─────────────────────────────────────────┘
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for system topology, the turn verification and known-screen system, coordinate scaling, and the corpus layout.

## For AI agents (Gemini, Claude, others)

Start with **[AGENTS.md](AGENTS.md)** — the model-neutral operating guide: setup, the play loop,
the decision procedure for every kind of blocker, known screens and how to add them, corpus
lookups, recoveries, and how to record and commit what you learn.

| Client | Context file | MCP config |
|---|---|---|
| Gemini CLI | `GEMINI.md` (+ `AGENTS.md` via `.gemini/settings.json`) | `.gemini/settings.json` |
| Claude Code | `CLAUDE.md` (imports `AGENTS.md`) | `.mcp.json` |
| Any other | `AGENTS.md` | run `./target/release/game-controller mcp` (stdio) |

Without MCP, everything works from the shell: `scripts/play/act.sh`, `ap.sh`, `hover.sh`,
`capture-template.py` and the `game-controller` CLI. Frames are written to `play/` (gitignored).

## Status (2026-09-25)

- Plays GC4 Supernova 4.1.1 as the Terran Alliance, Jan 2329 → Jul 2333 so far; five worlds
  (Earth, Mars, Artemis, Agena II, Macrinus III). Game log: [`games/terran-2329/journal.md`](games/terran-2329/journal.md).
- Every turn is verified by the HUD date changing; the autopilot clears 9 kinds of known screens
  by itself and stops only for real decisions (events, research, builds, policies, trades).
- **Stellaris** (4.5.1): the pilot app governs an empire over the native AI (observer mode +
  console directives, decisions from the monthly autosave). Verified live at Fastest speed on a
  throwaway game; see [`games/stellaris-spike/journal.md`](games/stellaris-spike/journal.md).
- Agent 1.2.0 (configurable drag, read-only game folders) is deployed on the PC.
- Open problems and history: [`issues.md`](issues.md); roadmap: [`plan.md`](plan.md).

---

## Core Components

| Component | Path / Binary | Architecture | Performance / Capabilities |
|---|---|---|---|
| **Windows Remote Agent** | [`crates/game-agent`](crates/game-agent) & [`windows_agent/game-agent.exe`](windows_agent/game-agent.exe) | Compiled native Rust (`x86_64-pc-windows-gnu`) | ~8ms screen capture & JPEG encode; native Win32 `SendInput`, `SetCursorPos`, and `mouse_event`; Per-Monitor V2 HiDPI aware. |
| **Linux Native Controller** | [`crates/game-controller`](crates/game-controller) → `target/release/game-controller` (build with `cargo build --release`; `.mcp.json` points here) | Compiled native Rust (`x86_64-unknown-linux-gnu`) | ~1 ms agent round-trip; autopilot that verifies each turn by the HUD date changing and stops on dialogs or blockers; in-memory corpus (search <1 ms); stdio MCP server. |
| **Game Corpus** | [`corpora/galciv4/`](corpora/galciv4/) | `manifest.toml` + `templates/*.png` + generated `data/*.json` + `docs/*.md` + `strategy.md` | 34 hotkeys, 17 screens (9 recognised by template), 3 macros; 130 techs, 528 improvements, 66 executive orders, 203 policies, 355 ship components, 167 starbase modules and 994 events generated from the game's own XML by `scripts/extract-galciv4.py`; 13 reference docs chunked into 168 searchable pieces. |
| **Stellaris corpus** | [`corpora/stellaris/`](corpora/stellaris/) | `manifest.toml`, `directives.toml`, `templates/`, `docs/*.md`, `strategy.md`, `pilot.md` | 9,152 records generated from the game's own files by `scripts/extract-stellaris.py` (679 techs, 56 policies, 171 edicts, 498 buildings, 147 districts, 234 traditions, 49 ascension perks, 358 civics, 6,960 events with every option); 46 wiki reference docs; 6 governor directives; pause-state screen; verified console/speed keys. Save reader in `crates/game-controller/src/stellaris.rs`. |
| **Pilot app** | [`src/pilot/`](src/pilot/) (`python -m pilot`) | Python 3.13, pydantic-ai (any provider: Gemini, OpenAI, Anthropic, Ollama) | Plays autonomously with an API key: GC4 blockers as vision episodes; Stellaris as a text-only governor. Live dashboard on :8790; run logs in `runs/`. |
| **Play helpers** | [`scripts/play/`](scripts/play/) | Bash + Python | `act.sh` (one action + frame), `ap.sh` (autopilot), `hover.sh` (tooltips), `capture-template.py` (new known screens). |
| **Legacy Python harness** | [`src/harness/`](src/harness/), `windows_agent/agent.py` | Python 3.12 | The first implementation; **not deployed**. Its tests still run in CI. |

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

# 11. Stellaris: briefing of the player's empire from an autosave
./target/release/game-controller stellaris brief                      # newest autosave on the PC (agent >= 1.2)
./target/release/game-controller stellaris brief path/to/autosave.sav # local file, offline
./target/release/game-controller stellaris brief --json
./target/release/game-controller stellaris directive expand --dry-run  # console lines only
./target/release/game-controller stellaris directive expand            # apply (Stellaris must be foreground)
./target/release/game-controller stellaris log -l 30                   # tail of logs/game.log
./target/release/game-controller stellaris speed fastest               # slowest|slow|normal|fast|fastest
./target/release/game-controller stellaris pause                       # / resume; state read from the screen, safe to repeat

# 12. Launch Stdio MCP Server (Claude Code / Gemini / Antigravity)
./target/release/game-controller mcp
```

---

## Model Context Protocol (MCP) Server

The controller is a stdio MCP server. Run it from the repo root so it finds `.agent_token` and
`corpora/galciv4` (or set `GAME_AGENT_TOKEN` / pass `--corpus`).

Claude Code — `.mcp.json` (in this repo):
```json
{ "mcpServers": { "game": { "command": "./target/release/game-controller", "args": ["mcp"],
  "env": { "GAME_AGENT_URL": "http://192.168.1.77:8765" } } } }
```

Gemini CLI — `.gemini/settings.json` (in this repo):
```json
{ "contextFileName": ["GEMINI.md", "AGENTS.md"],
  "mcpServers": { "game": { "command": "./target/release/game-controller", "args": ["mcp"], "cwd": ".",
    "env": { "GAME_AGENT_URL": "http://192.168.1.77:8765" }, "timeout": 600000 } } }
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
| `stellaris_briefing` | `json` | *Stellaris corpus only.* Briefing from the newest monthly autosave (fetched via the agent's `/files`): date, government, stockpile and net per resource with deficits flagged, power, research and options, policies, planets, wars. About 2 KB of text. |
| `stellaris_directive` | `name` | *Stellaris only.* Apply a governor directive from `corpora/stellaris/directives.toml`: `play <country>` → clear other directive flags, set `governor_directive_<name>` and its policies → `observe`; confirmed by `GOVERNOR_APPLIED <name>` in game.log. Checks the game is foreground before every keystroke. |
| `stellaris_speed` | `speed` | *Stellaris only.* Set the game speed: slowest, slow, normal, fast, fastest (`-` ×4 then `=` ×n; fastest ≈ 2.5 in-game months per second). |
| `stellaris_pause` | `paused` | *Stellaris only.* Pause or resume; reads the state from the screen first (the yellow "Paused" label), so it is safe to repeat. |
| `stellaris_log` | `lines` | *Stellaris only.* Tail of `logs/game.log`. |

---

## Testing & CI

```bash
scripts/ci.sh                                  # release build, cargo test, clippy -D warnings,
                                               # Windows agent check, corpus load, ruff, pytest -> "CI OK"
git add <paths> && scripts/ci-commit.sh "type(scope): message" "body"   # commits + pushes only if CI passes
```
Rust: 41 tests (controller: coordinate mapping, imaging incl. real-frame fixtures, corpus,
autopilot classifier, known-screen loading, MCP schema; agent: batch and drag validation).
Python: 55 tests (extractor fixtures, offline corpus CLI, legacy harness).

## Pilot app (autonomous player with any LLM)

```bash
echo 'GEMINI_API_KEY=…' >> .env                 # or OPENAI_API_KEY / ANTHROPIC_API_KEY
.venv/bin/python -m pilot check --game stellaris
.venv/bin/python -m pilot run --game galciv4                                   # vision episodes per blocker
.venv/bin/python -m pilot run --game stellaris --months 12   # governor; --speed normal (default) … fastest
.venv/bin/python -m pilot run --model openai:gpt-5 --game stellaris --episodes 3 --no-commit
```
Environment overrides: `PILOT_MODEL`, `PILOT_GAME`, `PILOT_SPEED`, `PILOT_DECIDE_MONTHS`,
`PILOT_POLL_S`, `PILOT_PORT`, `PILOT_COMMIT`, `PILOT_JOURNAL`, `PILOT_THINKING`, `PILOT_CAMPAIGN`,
`PILOT_RUNS_DIR`.

### Dashboard (LAN): `http://192.168.1.76:8780/`
Always on (`deploy/game-pilot-view.service`, a systemd user service; linger is enabled). It shows
every recorded campaign and, while a pilot runs, forwards its live controls (the pilot's own
dashboard is on :8790).
- **Empire over time**: net income, stockpile, power (or a table) over in-game months, the directive
  in force above the chart, and a mark for every decision (click to read it).
- **Decisions**: date, directive, trigger, the model's reason, and what changed 12 months later.
- **Reasoning**: the full trace of a decision: what the model was shown, its thinking (Gemini
  thought summaries), every tool call with arguments and result, the answer, tokens and time.
- **Talk** (live runs): *Ask* the model about its reasoning (never changes the game); *Note for next
  decision*; *Decide now* (pauses and decides immediately); *Standing orders* (in every decision
  until removed, saved per campaign); *Override* (apply a directive yourself, recorded as yours);
  Yes/No when the model asks for confirmation (e.g. `prepare_war`).
- **Activity**: the event feed; plus pause / resume / stop in the top bar.

### Telemetry (`runs/telemetry.sqlite`)
Every event, decision (with its full trace) and monthly metric point, grouped by **campaign** (the
Stellaris save folder, or the GC4 journal directory; `PILOT_CAMPAIGN` overrides). Each decision is
scored against the empire 12 in-game months later, and the governor's `past_outcomes` tool shows
those results before it decides. The JSONL logs in `runs/<id>/` stay the raw record:
`python -m pilot rebuild-telemetry` recreates the database; `python -m pilot view` serves it.
The database is local (gitignored); curated knowledge (`learned/`, strategy, journal) is committed.

**Stellaris governor** (`src/pilot/governor.py`): pause → briefing from the newest autosave →
the model returns one directive or `keep` → apply (`play` → flag + policies → `observe`) →
resume at `--speed` (default `normal`) → poll autosaves until `--months` have passed, a new war starts, or a
resource turns negative → pause → decide again. The game is paused whenever the model thinks,
so any speed is safe. `prepare_war` is applied only after a human "yes" on the dashboard. If the
game stops responding to pause/resume (e.g. a text box has keyboard focus; the controller tries
one Esc first), the governor stops acting and flags *needs attention* until you press Resume.
Measured with Gemini 3.8 Flash: ~6.2k input / ~0.4k output tokens and ~2 s per decision.

## Game corpus

`corpora/<game>/` is the only place game knowledge lives; the controller is game-agnostic.

```
corpora/galciv4/
  manifest.toml   hotkeys, known screens (template, ROI, action), macros — hand-verified
  templates/      reference crops that identify known screens
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
