# Plan

## Harness (Python, 2026-09-25 morning — now legacy)
- [x] Windows agent: stdlib HTTP API for screenshot + mouse/keyboard + window focus, bearer token
- [x] One-line Windows installer (Python check, subnet-only firewall rule, logon task)
- [x] Linux MCP server with image-space coordinates, zoom, grid overlay, action→screenshot
- [x] CLI for manual smoke tests
- [x] Install agent on 192.168.1.77 and verify screenshot + click end-to-end
- [x] Confirm GC4 capture works (not black) and mouse/keyboard input registers in-game

## Rust rewrite (2026-09-25 afternoon)
- [x] Rust Windows agent (axum, GDI StretchBlt, SendInput) cross-compiled and installed on the PC
- [x] Rust Linux controller: CLI, HTTP client, imaging, stdio MCP server (18 tools)
- [x] GC4 corpus: `game.toml` hotkeys/screens/macros, `strategy.md`, 13 wiki articles
- [x] Redeploy the DPI-aware agent build (installer fixed in 3e425bf; PC now reports 3840x2160)
- [ ] Restore `zoom`/`hover`/`scroll`/grid in the Rust MCP, or document why they're gone
- [x] Tests for the Rust MCP coordinate mapping and for the agent's batch validation (`cargo test --workspace`: 18)
- [ ] Decide the Python harness's fate: delete, or keep as the reference implementation with its tests pointed at what runs
- [ ] Stop tracking `game-agent.exe`; publish it as a release asset
- [x] Deploy agent 1.2.0 (configurable drag + read-only game-folder access; 4 roots verified on the PC 2026-09-25)
- [ ] Retry placing Earth's Capital City with the slow drag

## Game corpus (design: see ARCHITECTURE.md §5)
- [x] Restructure `corpora/galciv4/`: `manifest.toml`, `docs/*.md` with Source/License headers, `data/` contract
- [x] Corpus engine: generic records from `data/*.json`, paragraph-chunked docs, id-based `get`, alias + fuzzy lookup, deterministic search with match snippets (7 tests)
- [x] CLI `corpus search|get|tech|improvement|order|strategy` and MCP `corpus_get`; lookups report missing data instead of guessing
- [x] Get `Data/Gameplay/*.xml` + `Data/English/Text/*.xml` from the PC (`scripts/receive-file.py`)
- [x] `scripts/extract-galciv4.py` with fixture tests → `data/tech.json` (130), `improvement.json` (528), `order.json` (66), `_meta.json`
- [x] Extend the extractor to ship components, policies and starbase modules as their own record kinds → `policy.json` (203), `ship_component.json` (355), `starbase_module.json` (167)
- [x] Extract event dialogs with every choice's exact outcome → `event.json` (994)
- [x] Reconcile `strategy.md` numbers with the generated data (checked Capital City, Draft Colonists, Colonial Policies; the 27-vs-24 discrepancy is only in the wiki docs)
- [x] Wire the autopilot to the `manifest.toml` screen signatures (`luminance_roi`/threshold, new `turn_indicator_roi`)
- [x] Autopilot verifies a turn advanced (date readout diff), reports `NotAdvanced`, and refuses to send keys unless the game is foreground
- [x] Live-validate `turn_indicator_roi` and the `NotAdvanced` path against the running game (blocked by a pending leader prompt, correctly reported)
- [x] End-turn via TAB with verified advance (date readout, per-glyph strip diff); live: Mar → Oct 2329
- [x] Known informational screens auto-dismissed by template (first: GNN bulletin), verified live
- [x] Per-game journal (`games/terran-2329/journal.md`)
- [ ] Recognise the turn button's pending-item icons (policy / idle planet / idle fleet / event) so the autopilot reports *what* blocks it
- [x] Auto-handle idle survey ships (Survey, `v`) and never abandon a survey in progress
- [ ] Auto-handle idle probes (Explore, `o`) — needs a template of the probe's action icon

## Autonomy (known screens and recovery)
- [x] Known-screen system: template match → click / key / click sequence; `only_when_blocked`; `busy`; up to 3 attempts per turn; late dialogs after camera pans
- [x] Known screens: GNN bulletin, diplomacy menu, colonize confirmation, colony ship boarding, idle colony ship, idle survey ship, survey-abandon guard, idle shipyard, turn processing
- [x] `scripts/play/` helpers and `scripts/play/capture-template.py` for adding screens
- [ ] Planet build queue (idle core world): choose a district automatically from a rule (adjacency first)
- [ ] Research selection and "Research Complete" panel: pick from a priority list in the manifest
- [ ] Probe / warship idle handling (Explore / Sentry)
- [ ] Deploy agent 1.1.0 and retry Capital City placement with a slow drag

## LLM portability
- [x] `AGENTS.md` as the single model-neutral operating guide; `GEMINI.md` and `CLAUDE.md` point to it
- [x] `.gemini/settings.json` (Gemini CLI MCP + context files) alongside `.mcp.json` (Claude Code)
- [ ] Try a full session with Gemini CLI end-to-end and record any client-specific differences

## Playing
- [x] Record verified GC4 controls/UI positions in PLAYING.md
- [x] Bring PLAYING.md in line with the Rust MCP tool set (quick reference; procedure moved to AGENTS.md)
- [x] Play a first full turn cycle autonomously (2026-09-25)
- [ ] Automate launching/reloading GC4 (Steam → Stardock Launcher → Load Game) — done by hand once, documented in AGENTS.md §7

## Alternatives evaluated (2026-09-25)
- [ ] Perception layer: OCR + UI-element detection on the gaming PC's GPU, so the model clicks element IDs instead of guessed pixels
- [ ] Spike: is a GC4 save file parseable per turn? If so, read state from files and use vision only to confirm actions
- Rejected for now: controller in Docker / GPU host (controller does no GPU work; Linux box has only an Intel iGPU); moving the game to Linux (Proton/VFIO) until the above are exhausted

## Stellaris (LLM governor over the native AI)
- [x] Corpus seeded from the web: `corpora/stellaris/`, with 46 docs from 34 official-wiki pages (1,405 chunks), a manifest (33 hotkeys, 0 screens), a strategy with governor directives, a draft pilot briefing and a data contract
- [x] Spike in a throwaway non-Ironman game: autosave via agent, console injection, pause/date, `log` → game.log, `set_policy` held by the AI (`games/stellaris-spike/journal.md`)
- [x] Design: monthly autosave → briefing → LLM → pause, whitelisted effects, unpause; the game's AI plays the empire under `human_ai` (observer mode dropped: no expansion)
- [x] Save reader: `stellaris.rs` (jomini) → ~2 KB empire briefing; `game-controller stellaris brief`, MCP `stellaris_briefing`; tests on a real autosave
- [x] Extractor: `scripts/fetch-stellaris-files.py` (install via the agent) + `scripts/extract-stellaris.py` → 9,152 records (tech, policy, edict, building, district, tradition, ascension perk, civic, event) for 4.5.1
- [x] Directive bridge: `directives.toml` + `stellaris directive <name>` / MCP `stellaris_directive` (play → flag + policies → observe, confirmed in game.log), `stellaris log` / `stellaris_log`; verified live 2026-09-25 (flag and stance held 20 months)
- [x] Game speed control: `stellaris speed` / MCP `stellaris_speed` (slowest … fastest), verified live
- [x] Pause state from the screen: `stellaris pause|resume` / MCP `stellaris_pause`, safe to repeat; directives pause while applying. Verified at Fastest (30/30 save reads, directive confirmed)
- [x] Governor loop in the pilot app (`src/pilot/governor.py`, `pilot run --game stellaris --speed … --months …`): pauses to decide, urgent triggers (new war, new deficit), `prepare_war` needs a human yes; verified live with Gemini at Fastest (3 decisions)
- [x] Pilot: Stellaris game adapter (`McpGame` Stellaris methods, `FakeStellaris`); `pilot.md` finalised
- [ ] Long unattended Stellaris run in a real game (user's choice of empire), with learned rules committed
- [x] `stellaris take-control` / MCP `stellaris_take_control`: human_ai ON (console reply read on screen), leaves observer mode; briefing reports systems owned
- [x] Which directive levers the AI keeps: policies yes (20 months); console-added edicts no (cancelled within a month); briefing shows active edicts
- [ ] Companion mod: `ai_weight` modifiers keyed to `governor_directive_*` so the AI itself favours the directive's edicts, buildings and expansion (needs write access to the game's `mod/` folder, or a user install)
- [ ] Screen templates: pause/date and event popups

## Pilot app: observability and control
- [x] Decision traces: prompt, Gemini thought summaries, tool calls and results, answer, tokens, time (`runs/<id>/traces/`)
- [x] Telemetry per campaign in SQLite (`runs/telemetry.sqlite`), rebuildable from the JSONL logs; outcome scoring 12 months later; governor tool `past_outcomes`
- [x] Dashboard: campaign charts with directive lane and decision marks, decision list with outcomes, reasoning reader, activity feed; dark/light, phone layout
- [x] Talk to and direct the live model: ask (read-only chat), note for next decision, decide now, standing orders, override, Yes/No
- [x] Always-on LAN dashboard `http://192.168.1.76:8780/` (systemd user service, forwards live controls); `deploy/game-pilot.service` for the pilot itself
- [x] Dashboard updates itself: live/history switching, event stream with de-duplication, periodic refresh, freshness indicator, reader follows the newest decision
- [x] Default model Gemini 3.8 Flash with `medium` thinking for GC4 episodes and Stellaris decisions (thought summaries in traces)
- [x] Peer benchmarks in the Stellaris briefing (ours vs median/best of the other regular empires, rank, FALLING BEHIND line), urgent trigger when newly behind, standing line on the dashboard
- [x] Briefing: expansion room (unclaimed systems 1–2 jumps out, surveyed by us, held by others), construction/science/colony ships, BOXED IN / NO CONSTRUCTION SHIP lines
