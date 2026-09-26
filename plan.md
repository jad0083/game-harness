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
- [x] Stop tracking `game-agent.exe` (scripts/serve-agent.sh builds it from source before serving)
- [x] Deploy agent 1.4.0 (no console window, agent.log, numpad/win/plus keys, OS-random token) — deployed 2026-09-26 by typing the installer one-liner into the PC's PowerShell through the agent itself
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
- [x] Companion mod "Governor Bridge" (`corpora/stellaris/mod/`): additive AI budget entries gated on `governor_directive_*`, `stellaris install-mod` / `bridge-check`; deployed 2026-09-25 into United Nations of Earth 2 via a launcher playset "Governor Bridge" (bridge-check: loaded, no errors)
- [ ] Surveying speed is not budget-driven (science ship count comes from engine defines): find another lever if the mod doesn't lift expansion
- [x] Evaluate the mod on 11 in-game years of telemetry: expansion is influence-gated; the expand directive's influence went to a nomad-only budget pool (journal, 2026-09-26)
- [ ] Re-measure expansion ~5 in-game years after the fixed mod (influence → `stations`) is loaded
- [ ] Screen templates: pause/date and event popups

## Pilot app: observability and control
- [x] Decision traces: prompt, Gemini thought summaries, tool calls and results, answer, tokens, time (`runs/<id>/traces/`)
- [x] Telemetry per campaign in SQLite (`runs/telemetry.sqlite`), rebuildable from the JSONL logs; outcome scoring 12 months later; governor tool `past_outcomes`
- [x] Dashboard: campaign charts with directive lane and decision marks, decision list with outcomes, reasoning reader, activity feed; dark/light, phone layout
- [x] Briefing: our species (traits, climate preference), other species in the empire, identity (AI personality, traditions, perks), colonisable planets in our borders with their fit, growth and naval-capacity techs, naval capacity used, idle stockpiles, colonies against peers (2026-09-26)
- [x] Neighbours' identity in the briefing: ethics, government, civics, AI personality, species traits, colonies, traditions, perks
- [x] Corpus: 363 species traits and 24 colonisable planet classes from the game files; advanced strategy doc (4.5.1 files + wiki); playbook §10 lessons from play and §11 species and identity, both sent with every decision
- [x] Directives set policies only under each option's `valid` trigger; `expand`/`diplomacy_first` also set proactive first contact — live check that the policies change in game — verified 2026-09-26 in a new Theian game: the save holds `first_contact_protocol = first_contact_proactive`
- [ ] Economic-plan subplans gated on directive flags (naval capacity under `defend`/`prepare_war`, research under `tech_rush`, pops under `expand`, small strategic-resource targets when one runs out) — test against the game files, then measure over ~10 in-game years
- [ ] Evaluate carrier doctrine under `prepare_war` (`fleet_doctrine = strike_wing_fleet_doctrine`, cruisers and hangars known): live test that the AI's refreshed designs raise fleet power
- [ ] Evaluate isolationist stance for a boxed-in research phase (+10% unity, but −25% diplomatic weight; conflicts with federation play)
- [x] Live test: player actions under `human_ai` persist — a research pick (swap button in the Technology screen, F4) and a monthly market order (Market → Add new monthly trade) both held 13 in-game months (2026-09-26)
- [x] Model list in Settings: provider (Google, Anthropic, OpenAI) + model + thinking per entry, add/remove, and "take turns" to spread load; with turns off the first decides and the rest are fallbacks in order (2026-09-26)
- [x] Model roles: Decisions, Retrospectives, Talk and GC4 blockers each use their own model list or the decision models (Settings → Models); any model failure moves on to the next model, and a failed model cools down behind the others for 10 minutes (2026-09-26)
- [ ] Governor market action: (keep each order small so prices do not drift; buy the resource in deficit, pay with the idle one) a small monthly sell order for idle energy/trade into alloys or minerals (player action through the market screen; needs a live check that the AI keeps the order)
- [ ] Governor Bridge: `expand` funds orbital habitats once `tech_habitat_1` is known; `prepare_war`/`defend` set the belligerent stance — files uploaded, live at the next game start
- [x] Briefing: federation (type, level, cohesion, leader, members), Galactic Community vote and recent resolutions, crises and awakened empires, our situations; a crisis appearing is an urgent trigger
- [x] Neighbours panel (strength ratios against ours, opinion, relation tags, military trend) and war spans shaded on the chart (2026-09-26)
- [x] Each decision records the model release that answered (aliases resolve) and the thinking level; shown with the decision
- [x] Talk to and direct the live model: ask (read-only chat), note for next decision, decide now, standing orders, override, Yes/No
- [x] Always-on LAN dashboard `http://192.168.1.76:8780/` (systemd user service, forwards live controls); `deploy/game-pilot.service` for the pilot itself
- [x] Dashboard updates itself: live/history switching, event stream with de-duplication, periodic refresh, freshness indicator, reader follows the newest decision
- [x] Default model Gemini 3.8 Flash with `medium` thinking for GC4 episodes and Stellaris decisions (thought summaries in traces)
- [x] Peer benchmarks in the Stellaris briefing (ours vs median/best of the other regular empires, rank, FALLING BEHIND line), urgent trigger when newly behind, standing line on the dashboard
- [x] Briefing: expansion room (unclaimed systems 1–2 jumps out, surveyed by us, held by others), construction/science/colony ships, BOXED IN / NO CONSTRUCTION SHIP lines
- [x] Campaign plan (written and revised by the governor, per campaign, versioned) and retrospectives every N decisions (assessment, up to 3 rules into the learned overlay, revised plan); dashboard Plan tab
- [x] Code review follow-ups: answers channel, chat history, scoped scoring, transactional rebuild, escaping, console always closed, exact window title
- [x] Fewer tokens per governor decision: strategy trimmed to the directives section (+ contents), outcomes in the prompt, 4-call limit, short policy line (live: ~4.5k input tokens and 1 call for a routine decision, was ~15k and 2)
- [x] Live model selector on the dashboard: model and thinking pickers (Gemini models for this key + PILOT_MODELS), switch from the next model call, each decision records its model
- [x] Dashboard design pass: standing as chips with expansion room, single pause/resume toggle, decision-mark tooltips, no-wrap meta, compact empty screen panel, Talk auto-scroll, confirmation toasts
- [x] Agent 1.3.0 deployed on the PC (remotely, 2026-09-25): write root limited to mod/governor_bridge/, mod/governor_bridge.mod and dlc_load.json; other writes refused (403) on the PC
- [x] Model and thinking pickers always visible: with no run they save the choice for the next run (runs/pilot-settings.json; command-line options still win), during a run they also switch it live
- [x] Start a pilot run from the dashboard (game, speed, decision interval; runs game-pilot.service)
- [x] Dashboard redesign: readout strip, warm ivory on deep space, amber accent, Bricolage Grotesque + Fraunces, hairline sections instead of cards; PC status chip, campaign titles, markdown in the model's text, show-all decisions
- [x] Game speed and decision interval shown and changeable on the dashboard (live and for the next run)
- [x] Dashboard follows the live campaign; no-store responses; transient model errors retried
