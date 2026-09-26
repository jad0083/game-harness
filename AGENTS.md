# AGENTS.md — operating guide for any LLM agent

This is the single source of truth for an AI agent (Gemini, Claude, GPT, or any other) that
plays *Galactic Civilizations IV: Supernova* through this harness or works on its code.
`GEMINI.md` and `CLAUDE.md` only point here. Read this file fully before acting.

Everything below was verified in live play on 2026-09-25 unless marked **unverified**.

---

## 1. What this is

| Piece | Where | What it does |
|---|---|---|
| Windows agent | `crates/game-agent` → `windows_agent/game-agent.exe`, running on the gaming PC **192.168.1.77:8765** | HTTP API: screenshots, mouse, keyboard, window focus. Bearer-token auth. |
| Linux controller | `crates/game-controller` → `target/release/game-controller`, on this machine **192.168.1.76** | CLI + MCP server + verified-turn autopilot + game corpus. |
| Game corpus | `corpora/galciv4/` | Everything game-specific: hotkeys, known screens, macros, generated game data, strategy, reference docs. The Rust code is game-agnostic. |
| Play helpers | `scripts/play/` | Shell wrappers for the act → look → decide loop (`act.sh`, `ap.sh`, `hover.sh`, `capture-template.py`). |
| Game journal | `games/terran-2329/journal.md` | What happened in the current game and why. Read it before resuming play. |
| Stellaris | `corpora/stellaris/`, `crates/game-controller/src/stellaris.rs`, `src/pilot/governor.py` | Governor over the native AI: autosave briefing, console directives, speed and pause. See §10. |
| Pilot app | `src/pilot/` (`python -m pilot`) | Autonomous player with any LLM API key (README → "Pilot app"). |
| Dashboard | `http://192.168.1.76:8780/` (`deploy/game-pilot-view.service`) | Decision traces (thinking, tool calls), campaign charts, and talking to / directing the live model. Telemetry in `runs/telemetry.sqlite`. |

Hard facts:
- Screen 3840×2160 (DPI-aware agent). All screenshots and all coordinates you pass are in
  **1568×882 image space**; the controller scales to the screen.
- The game runs in the foreground of the user's desktop. **Never send input unless the game
  window is in the foreground** — the controller's `turn`/`autopilot` refuse otherwise, and the
  `scripts/play/*.sh` helpers focus the game before every action.
- The agent token is in `.agent_token` (gitignored). Export it as `GAME_AGENT_TOKEN` or let
  `scripts/play/common.sh` read it. Corpus commands work without it.

## 2. Setup (fresh clone on the Linux controller)

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]' pillow   # CI tools + image helpers
cargo build --release -p game-controller                             # binary used by MCP and scripts
scripts/ci.sh                                                        # must print "CI OK"
./target/release/game-controller health                             # agent reachable?
```

The Windows agent is installed with `scripts/serve-agent.sh` + a PowerShell one-liner (see
`README.md` → "Remote Windows Agent Setup"). Agent **1.2.0** adds configurable drag timing and
read-only file access to game folders listed in `roots.json` (Stellaris and GalCiv4 documents
and install dirs, detected by the installer): `GET /files/roots|list|read`.

### Connecting your model's tools (MCP)
The controller is a stdio MCP server: `./target/release/game-controller mcp` (19 tools, listed in
`README.md`). Pre-made configs:
- **Gemini CLI**: `.gemini/settings.json` (this repo). Start `gemini` in the repo root.
- **Claude Code**: `.mcp.json` (this repo).
- Anything else: run the command above with `GAME_AGENT_URL` and `GAME_AGENT_TOKEN` in the env.

If your client cannot use MCP, use the shell: `scripts/play/*.sh` and the `game-controller` CLI
do everything the MCP tools do. Screenshots land in `play/` (gitignored); open the JPEG/PNG
files with your image/file-reading tool to see them.

## 3. The play loop

```bash
scripts/play/ap.sh 20          # run up to 20 verified turns; prints one line per turn
```
Each turn the autopilot: checks the game is foreground → clears known screens (§5) → presses
**TAB** (end turn) → waits until the HUD date changes, a dialog appears, or the game stops
processing → classifies the result. It prints one of:

| Output | Meaning | What you do |
|---|---|---|
| `advanced` (maybe `(dismissed …)`) | Turn verified by the date readout changing | Nothing; the loop continues. |
| `dialog detected (HUD dimmed)` | An unknown dialog needs a decision | Look at `play/current_screen.jpg`, decide (§4), click the option. |
| `did NOT advance: … blocking end-turn` | Something pending that isn't automated | Look, then `scripts/play/act.sh key tab` to open the pending item, resolve it (§4). |
| `still processing ('Starting New Month' …)` | The game is busy after 180 s | Wait; if it lasts > 5 min it is the known hang → §7. |

Then run `scripts/play/ap.sh` again. Single actions:
```bash
scripts/play/act.sh click 480 638      # click (image coords), then fresh frame at play/s.jpg
scripts/play/act.sh key tab            # key or combo; keys: tab esc enter space a-z 0-9 f1-f12 arrows …
WAIT=1.5 scripts/play/act.sh drag 188 310 422 310
scripts/play/hover.sh 1535 857 1150 680 1568 882   # tooltip → play/h.png (2x crop)
```

## 4. Decision procedure (what blocks a turn and how to resolve it)

The bottom-right turn button shows what is pending: ▷ ready · ⚖ leader/policy · green planet =
idle core world (empty build queue) · green ships = idle fleet · red **!** = pending event.
**TAB** opens the next pending item. Decide with the corpus and `corpora/galciv4/strategy.md`.

| Blocker | How it looks | Resolve |
|---|---|---|
| **Event / situation report** | Dimmed HUD, titled dialog with 2–3 buttons | `game-controller corpus search "<event title>"` → `corpus get event:<id>` lists every choice's exact effects. Apply the rules in `strategy.md` §5 (permanent > one-time; artifact over +200 credits while treasury > ~500; avoid Nihilism/cruel options). Click the button. |
| **Research complete** | Left panel "Research Complete!" | *Choose New Tech* → pick per strategy (research/expansion techs, Hyperwave Radio for policy slots) → *Done*. Clicking a tech in *Additional Candidates* selects it. |
| **Idle core world** | "Choose a region to improve" planet screen | Click an empty tile → district menu with turn costs and adjacency bonus (a number in a gold circle) → click one → *Done*. Prefer adjacency bonuses; balance research vs. production vs. income. Dragging improvements onto tiles does **not** work yet (issues.md). |
| **Policy slot / leader** | Colonial Charter opens | Government tab: drag a policy from *Available Policies* onto an open slot. Leaders tab: double-click a card to recruit. Ministers tab: drag a leader onto an office. Then *Done*. |
| **Idle warship** | Ship selected, green-ships icon | `key n` (Sentry) to guard, or right-click a destination. |
| **Idle probe** | Probe selected | `key o` (Explore). |
| **AI trade proposal** | Trade screen with "You Give / You Get" | Never give technology or most of the treasury for treaties/trinkets. *Reject* → table clears → *Done*. The following diplomacy menu closes itself (known screen). |
| **Cutscene** | Full-screen video (e.g. "First Anomaly Survey") | Wait ~30 s; when it freezes on a blurred frame, click once. |
| **Tutorial popup** | "Greetings …" | *Done*. |

`esc` only closes an open panel; on the bare map it **opens the pause menu** — close it with a
second `esc` or *Resume*.

## 5. Known screens (handled by the autopilot)

Defined in `corpora/galciv4/manifest.toml` under `[screens.*]`; matched by comparing a template
image (`corpora/galciv4/templates/*.png`) with a region of the frame.

| Screen | Recognised by | Action |
|---|---|---|
| `gnn_news` | "GNN LIVE" logo | click Close |
| `diplomacy_menu` | "Goodbye." button | click Goodbye |
| `colonize_confirm` | "Colonize Planet" dialog title | click Yes |
| `colony_ship_boarding` | "Boarding T.A.S." title | click first citizen → Board → Done |
| `idle_colony_ship` * | colonize icon in unit action slot | key `c` (Auto Colonize) |
| `idle_survey_ship` * | survey icon in unit action slot | key `v` (Survey) |
| `survey_abandon_confirm` | "Survey in Progress" title | click No (never abandon a survey) |
| `shipyard_idle` * | "Shipyard Idle" label | Colony Ship → Build Ship → Done |
| `turn_processing` (busy) | "Starting New Month" label | keep waiting (up to 180 s) |

\* `only_when_blocked`: acted on only after TAB failed to end the turn (TAB has just selected a
genuinely idle unit). A unit that stays selected may already be busy; re-ordering it can cancel
work in progress.

### Adding a known screen (the main way this harness learns)
When the same blocker needs the same answer twice, automate it:
1. Get a frame showing it (`play/current_screen.jpg` or `scripts/play/act.sh`).
2. Choose a static, unique box: a dialog title, a fixed button label, or an icon — not the map,
   names, or numbers. Capture it and check it does **not** match other frames:
   ```bash
   .venv/bin/python scripts/play/capture-template.py play/current_screen.jpg X0 Y0 X1 Y1 my_screen \
       --against play/s.jpg other_frames.jpg        # other frames should be >= 0.10
   ```
3. Add to `manifest.toml` (normalized coords = image px / 1568 or / 882):
   ```toml
   [screens.my_screen]
   description = "what it is and why this action is always right"
   template = "templates/my_screen.png"
   template_roi = [x, y, w, h]          # printed by capture-template.py
   template_threshold = 0.06            # 0.05–0.06 for text, default 0.08
   auto_dismiss = true
   dismiss_click = [nx, ny]             # or dismiss_key = "c", or dismiss_clicks = [[..],[..]]
   # only_when_blocked = true           # for idle-unit style screens
   # busy = true                        # "still processing" indicators: wait, never click
   ```
4. Run it live (`scripts/play/ap.sh`) and confirm the output says `(dismissed my_screen)`.
5. `scripts/ci.sh` (a test requires every declared template to load), then commit (§8).

Only automate answers that are *always* right. Real decisions (events, trades, builds, tech,
policies) stay with the model.

## 6. The corpus (look things up, don't guess)

```bash
C="./target/release/game-controller --corpus corpora/galciv4"
$C corpus                                   # counts: 130 techs, 528 improvements, 66 orders,
                                            # 203 policies, 355 ship components, 167 starbase modules, 994 events
$C corpus search "precursor probe" --limit 5   # ids + one-line snippets
$C corpus get event:precursor_probe           # one record: every choice with exact effects
$C corpus tech "Hyperwave Radio"               # also: improvement, order (exact/alias/fuzzy)
$C corpus strategy                             # the playbook
```
Records are generated from the game's own XML (`scripts/extract-galciv4.py`) and win over the
wiki prose in `docs/`. Never hand-edit `corpora/galciv4/data/`.

## 7. Known problems and recoveries

- **Turn hang** (GC4 bug): "Starting New Month" for many minutes, date unchanged, pause menu has
  Save/Load greyed. Recovery: `esc` → *Exit Game* → *Yes* → `game-controller focus "Steam"` →
  green *PLAY* on the library page → **Stardock Launcher** → its green *PLAY* → `esc` skips the
  intro → *Load Game* → newest *Auto-Save* → *Load*. Replay the lost turns the same way.
- **Capital City can't be placed on Earth** (drag doesn't register). Retry after deploying agent
  1.1.0 with a slow drag (`--hold-ms 250 --steps 40 --step-ms 25 --dwell-ms 300 --wiggle`).
- **No Windows key** in the Rust agent's key table (`win+r` fails); focus windows by title instead.
- Full list: `issues.md`.

## 8. Recording what you learn (required)

The user is hands-off. Every solved problem goes into the repo, CI-checked, committed, pushed:

| You learned… | Write it to |
|---|---|
| A hotkey / UI behaviour, verified in play | `PLAYING.md` "Verified controls" and `manifest.toml` `[hotkeys]` with a `# verified:` comment |
| A recurring screen with a fixed answer | `manifest.toml` `[screens.*]` + template (§5) |
| A decision rule | `corpora/galciv4/strategy.md` |
| What happened in the game | `games/terran-2329/journal.md` (dated by in-game month) |
| A bug or limitation | `issues.md` (`- [ ]` open; `- [x]` only when fixed **and** deployed) |
| A feature planned / done | `plan.md` (same checkbox rules) |
| Code behaviour changes | `README.md`, `ARCHITECTURE.md` |

Commit through the CI gate — it runs `scripts/ci.sh` and commits only if everything passes:
```bash
git add <paths> && scripts/ci-commit.sh "type(scope): what changed" "why, and how it was verified"
```
Conventional commits (`feat` `fix` `docs` `refactor` `test` `chore`). **No AI/assistant
attribution** anywhere (no "Co-Authored-By", no "generated with", no model names in code or
commit messages). One logical change per commit. Never commit `.agent_token`, `play/`,
screenshots, or the game's raw XML (`incoming/`).

## 9. Working on the code

- `crates/game-controller/src/`: `autopilot.rs` (turn loop, known screens, classification),
  `imaging.rs` (ROI luminance, per-glyph date diff, template diff), `corpus.rs` (records, chunks,
  search), `mcp.rs` (tools), `client.rs` (agent HTTP), `main.rs` (CLI).
- `crates/game-agent/src/`: `main.rs` (HTTP routes, batch/drag validation), `backend.rs` (Win32),
  `keys.rs` (key names). Cross-build: `cargo build --target x86_64-pc-windows-gnu --release --bin game-agent`,
  copy to `windows_agent/game-agent.exe`, deploy with `scripts/serve-agent.sh`.
- Keep game knowledge out of Rust: new screens, keys and thresholds go in the manifest.
- Tests on real pixels live in `crates/game-controller/tests/fixtures/`; extractor tests in
  `tests/test_extract_galciv4.py`. Add a test with every fix.
- `src/harness/` and `windows_agent/agent.py` are the earlier Python implementation, **not
  deployed**; don't extend them.
- Parallel work: use a separate git worktree/branch per task, merge after `scripts/ci.sh` passes.

## 10. Stellaris (governor over the native AI)

Verified live 2026-09-25 (`games/stellaris-spike/journal.md`). The empire is played by the game's
own AI in **observer mode**; the model only picks one standing directive.

```bash
C="./target/release/game-controller --corpus corpora/stellaris"
$C stellaris brief                   # ~2 KB briefing from the newest autosave (read via the agent)
$C stellaris directive expand        # play 0 → flags + policies → observe; confirmed in game.log
$C stellaris speed fastest           # slowest | slow | normal | fast | fastest
$C stellaris pause                   # / resume — state read from the screen, safe to repeat
$C stellaris log -l 30               # tail of logs/game.log
.venv/bin/python -m pilot run --game stellaris --months 12   # the governor loop (speed: normal default)
```
Rules:
- **Never touch other save folders.** "Commonwealth of Man 3" is the user's own game. Test only
  in a throwaway, non-Ironman game; the console disables achievements.
- While observing, console `effect` has no country scope and silently does nothing: always
  `play <id>` first (the `directive` command does this).
- Space toggles pause, so never press it blind; use `stellaris pause|resume`.
- Directives are only those in `corpora/stellaris/directives.toml` (identifiers `[a-z0-9_]`); a
  new directive needs policy options that exist in the game's `common/policies`.
- Settings used: autosave Monthly (`settings.txt` `autosave=2`), tutorial off.

