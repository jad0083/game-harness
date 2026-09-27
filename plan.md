# Plan

## Harness (Python, 2026-09-25 morning — now legacy)
- [x] Windows agent: stdlib HTTP API for screenshot + mouse/keyboard + window focus, bearer token
- [x] One-line Windows installer (Python check, subnet-only firewall rule, logon task)
- [x] Linux MCP server with image-space coordinates, zoom, grid overlay, action→screenshot
- [x] CLI for manual smoke tests
- [x] Install agent on the gaming PC and verify screenshot + click end-to-end
- [x] Confirm GC4 capture works (not black) and mouse/keyboard input registers in-game

## Rust rewrite (2026-09-25 afternoon)
- [x] Rust Windows agent (axum, GDI StretchBlt, SendInput) cross-compiled and installed on the PC
- [x] Rust Linux controller: CLI, HTTP client, imaging, stdio MCP server (18 tools)
- [x] GC4 corpus: `game.toml` hotkeys/screens/macros, `strategy.md`, 13 wiki articles
- [x] Redeploy the DPI-aware agent build (installer fixed in 20e43e9; PC now reports 3840x2160)
- [ ] Restore `zoom`/`hover`/`scroll`/grid in the Rust MCP, or document why they're gone
- [x] Tests for the Rust MCP coordinate mapping and for the agent's batch validation (`cargo test --workspace`: 18)
- [ ] Decide the Python harness's fate: delete, or keep as the reference implementation with its tests pointed at what runs
- [x] Stop tracking `game-agent.exe` (scripts/serve-agent.sh builds it from source before serving)
- [ ] Deploy agent 1.5.0 (security fixes: token length, file paths, read cap, pinned install, firewall) on both PCs — mini-rig2 done 2026-09-26 (`GA_FW_PROFILE='Domain,Private'` there); main PC pending
- [ ] Per-host agent tokens: `serve-agent.sh <host>` serves `.agent_token.<host>`; switch each PC to its own token at the next reinstall — mini-rig2 switched (token in `.env` and the services' drop-ins); main PC pending
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
- [x] Strategy detail rules (pillars.toml `[strategy]`): a milestone on every pillar, checkpoint + end target on priority 1, two goals on the top 3, a briefing figure in each stance, so every model writes at the same detail (deployed d91768b)
- [x] Weighted pillars: weights (sum 100) instead of priorities; each decision sees directive pressure = weight × milestone need with a suggestion and switch margin (share mode defined for many-lever games); decisions name what they serve; dashboard shows weight × need = pressure (spec 2026-09-26-weighted-pillars-design.md; deployed e8da86c, live: Opus wrote weights, decision followed the suggestion)
- [ ] Directive efficacy: a directive that does not move its pillar's metric (held 2+ years, no faster than otherwise) loses half its pressure; its record goes to the frame and the Strategist (spec ruling 13)
- [ ] Event boosts to milestone need (war → defence) and share-mode consumers for GalCiv IV / Civ VI
- [ ] Stellaris levers from the Civ VI lessons (2026-09-27): a record per action kind, buy-out rules (market), crisis response when a war goes badly, deeper mod-steered AI (Governor Bridge), and a planet-development check; research → design with rulings → build → review → deploy (live checks when Stellaris is the running game)
- [ ] Stellaris market: a new monthly trade starts from the resource's own amount (0.1 x its market amount; levers ruling 8); alloys and sr_* refused unsent until the live market check measures their fractional start (an order of the same side and resource already placed is kept at its amount)
- [ ] Stellaris briefing fields for the levers (ruling 1): policy dates, market block (kind, prices, bought/sold, last month's trades), occupied colonies, force peace, own battles apart from allies', invasions, shipyards, colony jobs/unemployment/districts/queue, `governor_*` variables
- [ ] Stellaris directives obey the player's policy rules (`can_set_policy`, `cooldown = yes`) and report each policy set through a `GOVERNOR_POLICY` marker; the reply lists set and locked policies (levers rulings 3, 20)
- [ ] Governor Bridge v2 (levers rulings 18-19): posture flags beside the directive (`naval_cap`, `ship_upgrades` under defend/prepare_war, `research_focus` under tech_rush, `war_crisis` for the crisis) steering economic-plan subplans and AI budgets, `stellaris posture` / MCP `stellaris_posture`, all disabled until each passes its live probe; the monthly naval-capacity export for the empire `take-control` marks; `bridge-check` reports v1 or v2
- [ ] Stellaris date-stall watchdog (levers ruling 23): the autosave date unchanged for max(300 s, 10 x the run's median real month) while running → screenshot, `stall` event and needs attention, with no input to the game (a resume could reach another loaded campaign or a window merely titled Stellaris); time without a readable save is no stall (an agent outage flags needs attention and clears by itself); live check L6 (an event popup that autopauses)
- [ ] GalCiv IV levers from the Civ VI and Stellaris lessons (2026-09-27): whether the game's own AI can play our faction (governor model instead of screen play), a record per action kind, rush-buys with credits, crisis response, AI steering through data mods, planet tile placement, and stall/hang recovery; research → design with rulings → build → review → deploy (live checks when GalCiv IV is the running game)

## Pilot app: observability and control
- [ ] Dashboard v2 design pass with the learnings from three games (2026-09-27): information architecture per game, status and recovery when the governor stops, Civ VI and Stellaris lever views, phone and dark mode; research → design with rulings → build → review → deploy (after the Civ VI branch merges)
- [ ] Dashboard sign-in without the clunky key cookie (2026-09-27): per-device sessions, adding a phone or another browser without a terminal, sign-out and revocation, no master key in URLs or cookies, automation keeps a header token
- [ ] Dashboard sign-in A1 (branch feat/dashboard-v2): per-device sessions in `runs/auth.sqlite`, the service key only as a header from loopback, host allowlist (421) and optional canonical host, 72-hour carry-over of the old key cookie, `/api/auth/me` and devices (sign out, revoke, rename), stream closed on sign-out, signed-out banner, `X-Pilot-Device` on forwarded controls, no key in the startup line or access log
- [ ] Dashboard sign-in A2 (branch feat/dashboard-v2): the sign-in page (`/pair`, ported from the proof of concept's shell), three-word codes and one-time links (QR code with segno), ⋯ > Add a device, Settings > Devices, throttles on typed words only (atomic), a replayed code signs out the device it made, the no-script form, the recovery-key form (off), `dashboard-link` (link, words, QR, `--wait`) and `dashboard-devices` (list, rename, revoke, revoke-all, log, unlock)
- [ ] Dashboard sign-in A3 (branch feat/dashboard-v2): the live pilot binds 127.0.0.1 (`PILOT_LIVE_HOST`) and takes only the key header from loopback (no cookies, no sign-in routes), records the device behind each control and chat (`by`), reports `info.auth_version`; `python -m pilot control` for scripts (loud on refusals); `PILOT_VIEW_HOST` / `view --host`
- [ ] Dashboard sign-in A4 (branch feat/dashboard-v2): `dashboard-key --rotate [--keep] [--force]` (both services read the new key within 2 s; carried-over devices kept only if named; refused with the env key or a pre-change live pilot) and `dashboard-token create|list|revoke` (read or control scope, optional expiry, CLI only). Runbook: after the deploy, rotate with `--keep <the user's devices>` so the leaked copies of the key stop working
- [ ] Dashboard v2 U7 (branch feat/dashboard-v2): the phone is its own layout (a 52 px bar with the campaign, its date and a state dot; ⋯ holds Pause, Stop, Settings and the devices; a bottom nav Now · Decisions · levers · Strategy · Talk; Now leads with the last decision and ends with the recent problems and all activity; Reasoning, the campaign list, Settings and Add a device as full-screen sheets; no sideways scroll, no text under 13 px); the campaign control is a list with each campaign's game, state (live, paused, needs you, stopped), last date, decisions and runs, empty ones folded away (`/api/campaigns` `empty`, `state`)
- [ ] Dashboard v2 U6 (branch feat/dashboard-v2): Activity speaks in sentences for every event kind (an unknown kind reads "Unrecognised event", never JSON), repeats in a row group ("…, 3 times, T55–T57"), filters Problems, Orders, Model, You and All (Problems while a stop is open), each row with its game date, wall time and the raw event behind a disclosure; a campaign shows its own events (`GET /api/events?campaign=&after=`), not the newest run's
- [ ] Dashboard v2 U5 (branch feat/dashboard-v2): Civ VI Orders tab (`/api/orders`: the order record per kind with rates above the sample floor, every order with its fate, filters, open orders followed, backfilled tags, purchases, last stands; buy-outs from `info.reserves`), game health on Now (`info.game_health`, `popups_quieted`), the last stand armed/off in the facts line (`info.last_stand`), reader tabs Reasoning · levers · Strategy · Talk · Activity with arrow keys, the game screen in the levers tab
- [ ] Dashboard v2 U4 (branch feat/dashboard-v2): decision rows lead with the model's reason (trigger in words, model and time, fate chips or counts per fate, outcome line in the game's unit and keys with a watch flag, "No decision:" with the cause, Problems only); Reasoning leads with the decision, then labelled pairs (trigger, answered by with the models tried, took), orders with fates and badges, the full reason and the folded trace; the page scrolls, not the reader
- [ ] Dashboard v2 U3 (branch feat/dashboard-v2): the governor line (one sentence per state, the facts, who answered, deciding with its model, attempt and retry countdown, a question with its deadline), the needs-you card (`info.attention` with a category per call site, age, cost, recovery steps, Resume, Capture the game screen, What happened), title and favicon, model health (`/api/health`), the PC chip's states, Stop in ⋯ with the game's words
- [ ] Dashboard v2 U2 (branch feat/dashboard-v2): each game describes itself in `corpora/<game>/dashboard.toml` (`/api/view`): figures with rank or reserve sublines, chart views and series, rivals columns, outcome keys, recovery steps, Talk and Settings words; ids read as names from the corpus; Strategy speaks share or exclusive mode, folds the summary, shows the last review's result
- [ ] Dashboard v2 U1 (branch feat/dashboard-v2): light-mode text tokens darkened to pass WCAG AA (browser check on computed colours in four contexts), serif only for the model's words, toasts and inline "Saved" instead of `alert()`, tool-call arguments in the system's voice
- [ ] Dashboard v2 U0 (branch feat/dashboard-v2): truthful basics for Civ VI (PC chip knows Civ VI, readout hides what a game lacks, pace in turns, failed decisions show their cause, no NaN chart, frame fetched only when recorded, Reasoning cleared on a campaign switch, campaign dates in game order, real plurals); browser tests in CI (`pytest -m ui`)
- [x] Decision traces: prompt, Gemini thought summaries, tool calls and results, answer, tokens, time (`runs/<id>/traces/`)
- [x] Telemetry per campaign in SQLite (`runs/telemetry.sqlite`), rebuildable from the JSONL logs; outcome scoring 12 months later; governor tool `past_outcomes`
- [x] Dashboard: campaign charts with directive lane and decision marks, decision list with outcomes, reasoning reader, activity feed; dark/light, phone layout
- [x] Briefing: our species (traits, climate preference), other species in the empire, identity (AI personality, traditions, perks), colonisable planets in our borders with their fit, growth and naval-capacity techs, naval capacity used, idle stockpiles, colonies against peers (2026-09-26)
- [x] Neighbours' identity in the briefing: ethics, government, civics, AI personality, species traits, colonies, traditions, perks
- [x] Corpus: 363 species traits and 24 colonisable planet classes from the game files; advanced strategy doc (4.5.1 files + wiki); playbook §10 lessons from play and §11 species and identity, both sent with every decision
- [x] Directives set policies only under each option's `valid` trigger; `expand`/`diplomacy_first` also set proactive first contact — live check that the policies change in game — verified 2026-09-26 in a new Theian game: the save holds `first_contact_protocol = first_contact_proactive`
- [x] Versioned Claude Code models in the catalog (aliases plus every id from the Anthropic listing; deployed d91768b)
- [x] Model provider `claude-code:*` (Claude Code CLI, Claude subscription instead of an API key) for any role, Strategy first; falls back to the next model on a usage limit or CLI error
- [ ] Economic-plan subplans gated on directive flags (naval capacity under `defend`/`prepare_war`, research under `tech_rush`, pops under `expand`, small strategic-resource targets when one runs out) — test against the game files, then measure over ~10 in-game years. Naval capacity and research are Governor Bridge v2 postures on feat/stellaris-levers (disabled until their live probe)
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
- [x] Always-on LAN dashboard (port 8780) (systemd user service, forwards live controls); `deploy/game-pilot.service` for the pilot itself
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
- [x] Strategy layer: seven pillar strategies set by a Strategist model role at reviews and events, framing each directive; tech picks and market orders; Strategy tab with edit and pin (spec docs/design/2026-09-26-strategy-layer-design.md; deployed 1e2854c + 32d4b6d, 30-year live evaluation running)
- [ ] War-readiness briefing (Theian postmortem): naval-capacity maximum, occupied planets, shipyards, fleets, production per planet, own vs. allies' battles; urgent triggers for military −50%, occupation, system lost
- [ ] Directive read-back: check each directive's policies in the next save and report the ones that did not change; every directive sets all its policies
- [ ] Two shipyards in different systems and alloys on two or more planets before any war (strategy rule and mod budget nudge)
- [ ] Monthly fleet snapshot in telemetry to find what destroys ships in peacetime
- [ ] Full decision prompts in traces (no 6,000-character cut)
- [x] CI skips the Rust stages for commits with no Rust, Cargo or corpus files (`scripts/ci-needs-rust.sh`)
- [x] Game pillars: each game defines its strategy pillars, metrics and actions in `corpora/<game>/pillars.toml`; the strategy layer, decisions, actions and dashboard use them as guardrails (spec docs/design/2026-09-26-game-pillars-design.md; deployed 31e3481 on mini-rig2, two live reviews accepted with milestones and trait-based identity)
- [x] Civilization VI integration (after game pillars) — governor live on mini-rig2 since 2026-09-26 (China, Kublai Khan, from T41)
- [x] Civ VI tuner relay (agent 1.6.0 /tuner/*, controller civ6 states|lua) — agent 1.6.1 live on mini-rig2
- [x] Civ VI corpus: `scripts/extract-civ6.py` rebuilds the Gathering Storm + DLC rules database from the game's XML (modinfo criteria, load order, cascading deletes) → 1,783 records in 29 kinds; 16 docs (13 wiki pages, civ6-mcp playbook, CivBench appendix, links); first `strategy.md`; manifest with the window title; loads in the controller and CI
- [ ] Civ VI corpus: compare the Gathering Storm build with a GS `DebugGameplay.sqlite` (`CopyDatabasesToDisk 1`, load a GS game; `--check-against`) and the DLC load order in `Logs/Modding.log`
- [x] Civ VI pillars.toml, hotkeys and screens once the game can be read (tuner relay or saves) and played — pillars.toml in share mode live; hotkeys/screens not needed while the governor plays through the tuner
- [x] Civ VI governor (spec docs/design/2026-09-26-civ6-governor-design.md): `corpora/civ6/lua/harness.lua` (snapshot, orders, autoplay; checked live), controller `civ6 snapshot|order|autoplay|autoplay-stop|autoplay-status`, `corpora/civ6/pillars.toml` in share mode, `python -m pilot run --game civ6` (first live runs; not yet a service) — deployed 4f6a969, one-turn/3-turn autoplay, review fixes
- [x] Civ VI governor as a service on mini-rig2 (drop-in `PILOT_GAME=civ6`) with the dashboard following the campaign — running via runs/pilot-settings.json game=civ6 (dashboard Start run offers Civ VI)
- [x] Civ VI: engine-locking popups (wonder movies, natural wonders, projects, disasters, rock bands) quieted on every library install (`corpora/civ6/popups.toml`, `civ6 quiet-popups`)
- [ ] Civ VI district and wonder placement (a tile planner, design option 2), so production orders can name them (stage B: stage A's verdict at T202 is go; the first placement goes to a throwaway save)
- [ ] Civ VI MCP tools for snapshot, orders and autoplay
- [x] Civ VI order record: every order followed until it completes, holds or the AI replaces it; `order_outcome` events reloaded per campaign; stick rate per kind in the decision prompt and the Strategist (`[orders]` in pillars.toml); idle research/civic asked again, then filled by the governor; a timed-out autoplay start sent again twice (levers design, rulings 12-16)
- [x] Civ VI buy-out rules: `in_danger` instead of threatened (purchase share and autoplay chunks), gold reserve 30 + 10 per gold of deficit, pantheon faith reserve, balances excluded from milestones, defenders first and with faith, stacking, cooldown, known-price cap, skip what finishes anyway, defenders ordered into production bought in danger; walls text fixed (levers design, rulings 17-21 and A1)
- [x] Civ VI snapshot: city position, buildings, garrison, garrison and walls HP, and for a threatened city its enemies, defenders, capture threats, incoming damage, strike and defender prices; religion and every end-turn blocker (levers design docs/design/2026-09-27-civ6-levers-design.md, ruling 11; checked live read-only at T124-T129)
- [ ] Civ VI last stand for a city about to fall (levers design, rulings 22-27): `about_to_fall` and the "city falling" urgent trigger; one scripted action per call (city strike, ranged attacks, retreat of hurt units), each read back in GameCore, then pins and a one-turn autoplay hand-back; hostile-only targets, 8 actions / 90 s, no resends, a circuit breaker; controller `civ6 turn-ready|ls-state|last-stand-step|finish-moves`; off by default (`PILOT_LAST_STAND`) until the L6 checklist passes on a throwaway save or in a maintenance window — deployed 469cd14 but off (`PILOT_LAST_STAND=0`) until live check L6 passes
- [x] Civ VI AI-intent briefing (levers design, ruling 29): each city's top 3 builds from the game's AI in the snapshot, our strategies from `Logs/AI_Victories.csv` (`civ6 ai-strategies`, one agent read per decision), "The AI's own plan" in the briefing, and `top3_hit` on each override in the order record
- [x] Civ VI option 2 stage A, read-only (levers design, ruling 30): the extractor writes the adjacency rules as data (`data/_adjacency.json`), `civ6 district-plots` reads the plots each district may use, `scripts/civ6-placement.py` scores them and the AI's placements and prints stage B's go / no-go (L3 at T202: go, +1.00 over the 5 rateable districts, a thin margin; districts with fewer than 3 other plots to compare with are left out)
- [ ] Civ VI option 4 probe (levers design, ruling 28): a mod strategy for player 0 steered by a player property, gates G1-G4 in a maintenance window with fork and reload; pillar postures only if it passes
- [x] Dashboard access key: `PILOT_DASHBOARD_KEY` or `runs/dashboard.key`, one link per browser (`python -m pilot dashboard-link`), JSON-only same-origin changes

## Hosts
- [x] Second game host mini-rig2 (2560x1440): agent 1.4.0 installed and reachable with the shared token (2026-09-26)
- [ ] Host registry (`hosts.toml`: name, agent URL, screen) and one governor service per host (own dashboard port, `GAME_AGENT_URL`); dashboard lists live runs of every host
- [ ] Installer detects Civilization VI folders (documents, saves, logs, install) for the agent's read roots; update both hosts
- [x] Screen positions per resolution: `res/<W>x<H>.toml` overlays selected by `GAME_RESOLUTION`; Stellaris 2560x1440 screens measured live on mini-rig2 (8068268, 7d43af8)
- [x] Stellaris tech and market positions at 2560x1440: mapped from 4K by `scripts/res-map.py` (scale 1.2, anchors in `res/map.toml`), verified live with a tech pick and a market order added and removed (e49d2bc)
- [x] Stellaris on mini-rig2: borderless, monthly autosave, tutorial off, Governor Bridge playset; governor service points at mini-rig2 (systemd drop-in) and plays the new Blooms of Gaea campaign (2026-09-26)
- [ ] Buy-outs per game (economy pillar action): Stellaris converts idle stock into the bottleneck resource on the market (no rush-buy exists); GalCiv4 rushes builds with credits (verify in play first); Civilization VI buys units, buildings, tiles and great people with gold or faith. Rule: spend when turns saved times the item's value beats the resource's other uses, keep a reserve, buy at once for a threatened city or planet
