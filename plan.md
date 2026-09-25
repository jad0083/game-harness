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
- [ ] Autopilot: verify a turn actually advanced before counting it; use the `game.toml` screen signatures it parses
- [ ] Restore `zoom`/`hover`/`scroll`/grid in the Rust MCP, or document why they're gone
- [x] Tests for the Rust MCP coordinate mapping and for the agent's batch validation (`cargo test --workspace`: 18)
- [ ] Decide the Python harness's fate: delete, or keep as the reference implementation with its tests pointed at what runs
- [ ] Stop tracking `game-agent.exe`; publish it as a release asset

## Game corpus (design: see ARCHITECTURE.md §5)
- [x] Restructure `corpora/galciv4/`: `manifest.toml`, `docs/*.md` with Source/License headers, `data/` contract
- [x] Corpus engine: generic records from `data/*.json`, paragraph-chunked docs, id-based `get`, alias + fuzzy lookup, deterministic search with match snippets (7 tests)
- [x] CLI `corpus search|get|tech|improvement|order|strategy` and MCP `corpus_get`; lookups report missing data instead of guessing
- [x] Get `Data/Gameplay/*.xml` + `Data/English/Text/*.xml` from the PC (`scripts/receive-file.py`)
- [x] `scripts/extract-galciv4.py` with fixture tests → `data/tech.json` (130), `improvement.json` (528), `order.json` (66), `_meta.json`
- [ ] Extend the extractor to ship components, policies and starbase modules as their own record kinds
- [ ] Reconcile `strategy.md` numbers with the generated data (e.g. Colonial Policies costs 24, not 27)
- [ ] Wire the autopilot to the `manifest.toml` screen signatures it already parses

## Playing
- [x] Record verified GC4 controls/UI positions in PLAYING.md
- [ ] Bring PLAYING.md in line with the Rust MCP tool set
- [ ] Play a first full turn cycle autonomously
- [ ] Per-game journal (`games/<save>/journal.md`) for long-game memory
- [ ] Optional: launch GC4 from the harness (Steam/Epic URI) when it isn't running

## Alternatives evaluated (2026-09-25)
- [ ] Perception layer: OCR + UI-element detection on the gaming PC's GPU, so Claude clicks element IDs instead of guessed pixels
- [ ] Spike: is a GC4 save file parseable per turn? If so, read state from files and use vision only to confirm actions
- Rejected for now: controller in Docker / GPU host (controller does no GPU work; Linux box has only an Intel iGPU); moving the game to Linux (Proton/VFIO) until the above are exhausted
