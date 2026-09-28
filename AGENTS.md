# AGENTS.md — operating guide for any LLM agent

This is the single source of truth for an AI agent (Gemini, Claude, GPT, or any other) that
plays *Galactic Civilizations IV: Supernova* through this harness or works on its code.
`GEMINI.md` and `CLAUDE.md` only point here. Read this file fully before acting.

Everything below was verified in live play on 2026-09-25 unless marked **unverified**.

---

## 1. What this is

| Piece | Where | What it does |
|---|---|---|
| Windows agent | `crates/game-agent` → `game-agent.exe` (built by `scripts/serve-agent.sh`), running on the gaming PC **192.168.1.77:8765** | HTTP API: screenshots, mouse, keyboard, window focus. Bearer-token auth. |
| Linux controller | `crates/game-controller` → `target/release/game-controller`, on this machine **192.168.1.76** | CLI + MCP server + verified-turn autopilot + game corpus. |
| Game corpus | `corpora/galciv4/` | Everything game-specific: hotkeys, known screens, macros, generated game data, strategy, reference docs. The Rust code is game-agnostic. |
| Play helpers | `scripts/play/` | Shell wrappers for the act → look → decide loop (`act.sh`, `ap.sh`, `hover.sh`, `capture-template.py`). |
| Game journal | `games/terran-2329/journal.md` | What happened in the current game and why. Read it before resuming play. |
| Stellaris | `corpora/stellaris/`, `crates/game-controller/src/stellaris.rs`, `src/pilot/governor.py` | Governor over the native AI: autosave briefing, console directives, speed and pause. See §10. |
| Civilization VI | `corpora/civ6/` (with `lua/harness.lua`), `crates/game-controller/src/civ6.rs`, `src/pilot/civ6_governor.py` | Governor over the native AI: Lua snapshot and structured orders through the tuner, autoplay stretches. See §11. |
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

The Windows agent is installed with `scripts/serve-agent.sh [host]` + the PowerShell one-liner it
prints (see `README.md` → "Quick start" and "Security"). The one-liner holds
a one-time path and SHA-256 pins, so always copy the freshly printed one; stop the server once the
installer reports the agent version. With a `host` name the PC gets its own token in
`.agent_token.<host>`; use it through `GAME_AGENT_TOKEN` for that PC. Agent **1.2.0** adds configurable drag timing and
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
   # add --corpus stellaris for a Stellaris template (default: galciv4)
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
- Agent **1.4** adds `win`, `num0`–`num9`, `add`/`subtract` (numpad +/-), and `plus`/`+`; older agents
  lack them (focus windows by title instead of `win+r`). It runs without a console window and
  logs to `%LOCALAPPDATA%\GameAgent\agent.log`.
- Agent **1.5** refuses to start with a token under 32 characters (see agent.log), returns at most
  16 MiB per `/files/read` (the controller pages larger files), and refuses Windows device names,
  names ending in a dot or space, UNC paths and `:` in file paths; its installer pins the exe by
  SHA-256 and limits the firewall rule to the controller on Private networks.
- Agent **1.6** relays Lua to Civilization VI's FireTuner console (`EnableTuner 1`; the game listens
  on 127.0.0.1:4318 only): `GET /tuner/states`, `POST /tuner/lua`; controller
  `game-controller civ6 states` and `civ6 lua [--state GameCore] "<code>"`. One tuner client at a
  time, so close FireTuner while it runs.
  Verified live (1.6.1): the game lists states as index/name pairs (the game-state VM is
  `GameCore_Tuner`, index 3 in a loaded game); `return` values are not echoed, so write Lua that
  `print()`s its result; the reply's `output` holds the printed lines.
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
`ci-commit.sh` skips the Rust stages when no staged file needs them (`scripts/ci-needs-rust.sh`:
Rust sources, Cargo files, corpora outside `learned/`, the CI scripts); `scripts/ci.sh` alone runs
everything. Conventional commits (`feat` `fix` `docs` `refactor` `test` `chore`). **No AI/assistant
attribution** anywhere (no "Co-Authored-By", no "generated with", no model names in code or
commit messages). One logical change per commit. Never commit `.agent_token`, `play/`,
screenshots, or the game's raw XML (`incoming/`).

## 9. Working on the code

- `crates/game-controller/src/`: `autopilot.rs` (turn loop, known screens, classification),
  `imaging.rs` (ROI luminance, per-glyph date diff, template diff), `corpus.rs` (records, chunks,
  search), `mcp.rs` (tools), `client.rs` (agent HTTP), `main.rs` (CLI).
- `crates/game-agent/src/`: `main.rs` (HTTP routes, batch/drag validation), `backend.rs` (Win32),
  `keys.rs` (key names), `files.rs` (read roots), `tuner.rs` (Civ VI Lua relay). Cross-build: `cargo build --target x86_64-pc-windows-gnu --release --bin game-agent`,
  or just run `scripts/serve-agent.sh` (it builds, then serves the installer; the exe is not in git).
- Keep game knowledge out of Rust: new screens, keys and thresholds go in the manifest.
- Tests on real pixels live in `crates/game-controller/tests/fixtures/`; extractor tests in
  `tests/test_extract_galciv4.py`. Add a test with every fix.
- `src/harness/` and `windows_agent/agent.py` are the earlier Python implementation, **not
  deployed**; don't extend them.
- Parallel work: use a separate git worktree/branch per task, merge after `scripts/ci.sh` passes.

## 10. Stellaris (governor over the native AI)

Verified live 2026-09-25 (`games/stellaris-spike/journal.md`). The empire is played by the game's
own AI through **`human_ai`** (we stay the player); the model only picks one standing directive.
**Never use observer mode**: there the AI does not explore or expand.

```bash
C="./target/release/game-controller --corpus corpora/stellaris"
$C stellaris brief                   # ~2 KB briefing from the newest autosave (read via the agent)
$C stellaris take-control            # once per session: leave observer mode, human_ai ON (read on screen)
$C stellaris install-mod             # upload the Governor Bridge mod and enable it (agent >= 1.3; restart the game)
$C stellaris bridge-check            # is the mod loaded in the running game, and which version (v1 or v2)?
# The Paradox Launcher opens when mods are enabled: its playset "Governor Bridge" holds only this
# mod (the user's "Initial playset" is theirs); pick it on the launcher's Home, then RESUME.
$C stellaris directive expand        # flags + policies on the empire; confirmed in game.log
$C stellaris posture war_crisis off  # set (on) or clear one Governor Bridge posture; --dry-run prints the line
$C stellaris speed fastest           # slowest | slow | normal | fast | fastest
$C stellaris pause                   # / resume — state read from the screen, safe to repeat
$C stellaris log -l 30               # tail of logs/game.log
$C corpus search "atomic clock"      # 9,152 records from the game files: events with options, techs, policies…
$C corpus get event:distar.311       # every option of an event with its effects
.venv/bin/python -m pilot run --game stellaris --months 12   # the governor loop (speed: normal default)
```
Rules:
- **Never touch other save folders.** "Commonwealth of Man 3" is the user's own game. Test only
  in a throwaway, non-Ironman game; the console disables achievements.
- While observing, console `effect` has no country scope and silently does nothing, and the AI
  does not expand: run `stellaris take-control` (the governor does this at start).
- game.log drops a log line whose text repeats on the same in-game day, and lags a few seconds.
- Space toggles pause, so never press it blind; use `stellaris pause|resume`.
- Esc on the bare map opens the in-game menu ("Paused" still shows beneath it); `stellaris
  pause|resume` recognises it (`[screens.game_menu]`) and closes it first.
- Directives are only those in `corpora/stellaris/directives.toml` (identifiers `[a-z0-9_]`); a
  new directive needs policy options that exist in the game's `common/policies`.
- Directive policies obey the player's rules: each is set only if `can_set_policy` allows it (the
  10-year lock, no stance change at war) and starts that lock (`cooldown = yes`). game.log gets
  `GOVERNOR_POLICY <policy> <option> <nonce>` for each policy set; the reply lists the policies set
  and those locked. A locked policy is not a failure: the flag still changes. An option the newest
  autosave already holds is not sent again (it could restart the lock) and is listed as already in
  force.
- **Postures** (`[posture.*]` in directives.toml; Governor Bridge v2): flags `governor_posture_<name>`
  that the mod reads to steer the AI's own spending (economic-plan focus, AI budgets; never resources
  or modifiers). `defend`/`prepare_war` switch `naval_cap` and `ship_upgrades`, `tech_rush`
  switches `research_focus`; `war_crisis` belongs to the war crisis only. **Every posture is
  `enabled = false`** until its live probe passes (a fork-and-reload A/B from one autosave on a
  throwaway game, 24 in-game months per arm); a disabled posture is never set, and enabling one is a
  data commit. v2 also exports the naval capacity each month for the empire `take-control` marked
  (`governor_bridge_player`), so the briefing shows "naval capacity used/max (from the mod)" while
  the export agrees with the save's own use (within max(2, 2%)); variables outlive the mod, so an
  export that disagrees is flagged `governor_vars_stale` and the line keeps "the maximum is not in
  the save".
- **Date-stall watchdog**: when the autosave date has not moved for max(300 s, 10 x the run's
  median real month) while the governor wants the game running, it takes a screenshot, logs `stall`
  and flags needs attention. It sends no input and focuses no window: another loaded campaign (no
  autosave yet), the launcher or a browser tab titled Stellaris cannot be told from the governed game
  read-only, so only the human resumes. Pause from the dashboard, not the game's menu, when you want
  it to wait. Time in which the save cannot be read (the PC asleep, the agent away) is left out of
  the held time; reads failing for that limit flag needs attention without pausing the run or
  sending input, and the flag clears by itself once a save of the campaign reads again.
- Settings used: autosave Monthly (`settings.txt` `autosave=2`), tutorial off.
- **Weighted pillars** (`[weights]` in pillars.toml): pillars carry weights (sum 100, 5..50, heaviest
  >= 2x lightest); each decision gets every directive's pressure (weight x milestone need) and a
  suggestion (the top one, or keep within a 1.25 switch margin); decisions name what they `serve`.
  A directive held 2+ years whose pillar metric grew no faster, as ours ÷ the peer median per year,
  than while not held has its pressure halved; the frame says when expand is held back by unsurveyed
  space (none surveyed in reach, influence 950+ for 12 months). A milestone is judged on the latest
  value since it was set (its `set` stamp), never on a past high: met, missed once due, else on track
  or at risk (both games; postmortem-fixes design, ruling 17).
- **Strategy detail** (`[strategy]` in pillars.toml): every pillar needs a milestone, the heaviest two
  on different dates (a checkpoint and an end target), the top 3 two goals, and each stance a figure from
  the briefing; a Strategist answer that misses one is sent back once with its errors. Pinned pillars
  and human edits are exempt.
- **Game pillars**: `corpora/stellaris/pillars.toml` defines the strategy's pillars, metrics, aliases
  and action limits (edit it, not Python, to change them; `tests/test_pillars.py` checks it). A broken
  file turns the strategy layer off with the reason on the Strategy tab.
- **Strategy layer**: the governor keeps a pillar strategy (role `strategy`) that ranks the
  directives; decisions choose within it. Two actions go through the game's screens (positions in
  `[ui.tech]`/`[ui.market]` of the manifest, calibrated on 4.5.1): `stellaris_pick_tech` (clicking a
  field's swap button drops its current research at once, so it only swaps a field under 10% done;
  only the first 4 offered techs are clickable) and `stellaris_market_sync` (a new monthly trade
  starts at 0.1 x the resource's market amount: 10 energy, minerals, food; 5 consumer goods; 1 motes,
  gases, crystals (`new_trade_amount` in `[ui.market]`); alloys and sr_* start at a fraction, so an
  order of them to add is refused on its own until that is measured (removals and other adds still go,
  but an order of the same side and resource already placed stays at its amount); changes are computed from the last autosave, so call it at
  most once per autosave; trade is not a market resource).
- **Market buy rules** (`[actions.market.buy]` in pillars.toml): every buy, declared or automatic,
  keeps 2,500 trade after a year of its cost over the trade income, costs at most a quarter of that
  income plus the surplus over two years, is not placed or raised above +50% price (an order in place is kept at its amount up to +100%), stays
  within one base amount a month (six on the galactic market), and is never a resource the AI buys
  itself (under 6 months of cover, or bought since the last save), an IDLE one, or alloys at 95% of
  naval capacity. While trade is IDLE and no declared order passes, the slot is filled with deficit
  cover (6-24 months of stock left, 36 for motes, gases, crystals); else the next decision reads
  "trade idle: nothing qualifies to buy (reason)". A buy in the order list that trades nothing in 2
  saves (`market.trades_net`) is recorded took (not executing).
- **War crisis** (`PILOT_WAR_CRISIS`, default 1): at war, a colony occupied, 2+ systems or half the
  military lost within 12 months, a colony lost, a new invasion, or a colony under stability 25 twice
  enters it (`war going badly: ...`; never on ratios, battle counts or exhaustion; once per war per 12
  months). The ladder: review, defence need missed, `defend` applied, the `war_crisis` posture (skipped:
  not verified until enabled and the v2 export is in the save), alloys on the market slot (only with a
  shipyard we hold, naval room, a measured start amount: not before L2), decisions every 3 months, a
  non-blocking status-quo question. Ends at peace or after 6 quiet saves held 6 months (each save
  counted once, also the one a restarted run re-reads).
- **Planet check** (read-only): a colony under stability 50, amenities under -100 (300+ pops), housing
  under 0 (1,000+ pops), 5% unemployed (not the capital), 20% fewer pops than its 12-month peak, or
  occupied, for 2+ months (saves at most 3 months apart: a restart gap starts the count again), is named in the decision prompt's `Planet check:` line with a hint
  (nothing queued, minerals net < 0). `planet crisis` (under 25 on 2 saves in a row) and `planet
  losing pops` (1,000+ pops) are urgent once and start a review. No directive repairs grown colonies.
- **Action record**: every directive, tech pick, market order and posture is followed in the
  autosaves until it resolves (`order_outcome` events: took, held, researched; overridden, failed,
  did not take, did not stick, removed; not judged: superseded, locked, no-op), with a stick rate per
  key over 10 in-game years (`[orders]` in pillars.toml, in months) in the decision prompt, the
  Strategist's review and the dashboard. Advisory, except that a market order that did not take twice
  in a row is suspended until `[ui.market]` is recalibrated; a review resets only the tech skip.
- **Other screen sizes**: positions and templates are measured at 3840x2160. A host with another size
  sets `GAME_RESOLUTION` (e.g. `2560x1440`); the controller then merges `res/<W>x<H>.toml`. Its
  `[ui.*]` points come from `scripts/res-map.py corpora/stellaris <W>x<H> --write` (one UI scale per
  size in `res/map.toml`, each UI group pinned to top-left or the screen centre; verified within
  1-2 px at 1440p); its screen templates are captured at that size (`capture-template.py`).

## 11. Civilization VI (governor over the native AI)

Verified live 2026-09-26 on mini-rig2 (`games/civ6-kublai/journal.md`; spec
`docs/design/2026-09-26-civ6-governor-design.md`). The game's own AI plays our civilization through
`AutoplayManager` for a few turns at a time; the model gives macro orders between those stretches.
The game must run with `EnableTuner 1` and a game loaded; no input is sent to the window.

```bash
C="./target/release/game-controller --corpus corpora/civ6"
$C civ6 snapshot                      # one JSON document (installs corpora/civ6/lua/harness.lua if missing)
$C civ6 order '{"kind":"research","id":"tech:pottery"}'          # also civic, policies, production, purchase, price
$C civ6 order '{"kind":"production","city":"Beijing","id":"unit:settler"}'
$C civ6 order '{"kind":"purchase","city":"Beijing","id":"unit:warrior","currency":"gold","max_cost":150}'
$C civ6 autoplay 5                    # the AI plays 5 turns, then hands the civ back
$C civ6 autoplay-status               # / autoplay-stop
$C civ6 quiet-popups                  # remove the engine-locking popup handlers (automatic on library install)
$C civ6 lua --state InGame "print(Game.GetCurrentGameTurn())"   # raw Lua, for investigation only
.venv/bin/python -m pilot run --game civ6 --decide-turns 5        # the governor loop (docs/pilot.md)
```
Rules:
- Tuner output comes back only through `print()`; the library prints one JSON line per call.
- Orders name corpus ids and are checked against `corpora/civ6/data` before any Lua is built; the
  model's text reaches Lua only as encoded string literals. Never send model-written Lua.
- Research and civics are set in the `GameCore` state (the UI's request sent from the tuner is
  ignored); everything else runs in `InGame` (GameCore lacks the government, policy slots, era score,
  military strength and purchase prices). The library installs itself into each state on first use.
- Policy cards change for free only in the turn a civic completes (`policies_unlock_cost` is 0);
  wonders and new districts need a tile, which is not supported yet.
- The tuner does not answer while the AI plays its turn (calls time out): the governor autoplays one
  turn at a time and only reads or orders between turns; never repeat an order blindly after a timeout.
- Tutorial advisor popups hold an autoplay turn forever (seen at T17, cleared by clicking OK):
  `Harness.autoplay` sets `UserConfiguration` `TutorialLevel` to -1 for the session.
- Wonder movies and four other popups hold the game's engine event until closed
  (`ExclusivePopupManager:Lock`), so an autoplay turn never ends (T134: 600 s on the Pyramids). Each
  popup is its own tuner state; `corpora/civ6/popups.toml` lists state, event and handler, and the
  controller removes those handlers before the first `InGame` call of each load runs (the library's
  `Harness.popups_quiet` flag; unsettled entries are retried on the next call, and the reply lists
  the outcomes in `popups_quieted`). A stall that still happens needs the screen: hover + click the
  popup's X.
- An AI leader's statement (T240 "the mustering of your forces along our borders", T342 an agenda
  warning) opens the leader screen, which holds the engine until a human answers. `popups.toml`
  removes that screen's statement handler, but only while the library's own handler (registered in
  `InGame` only) is in place (`requires = "dipl_handler"`; otherwise the controller puts the screen's
  handler back and a statement waits for a human on screen, as before). That handler answers while
  autoplay runs, from its explicit table: the conciliatory promise to a warning, Goodbye to
  proposals, first meetings and everything else, a refusal to deals and demands; never a choice that
  declares war or accepts a deal. A statement outside autoplay waits until autoplay next starts.
  The snapshot's `diplomacy` lists the last 20 answers; the governor emits `diplomacy_reply` and adds
  a briefing line and the order record's diplomacy section. Until the next load a human sees no AI
  statement on screen. A controller built before `requires` refuses that popups.toml (unknown
  field), so build the binary with the corpus change (pause the governor across the merge and the
  build).
- One-turn autoplay costs the AI its multi-turn plans (a Settler idle for 7 turns, no pantheon; a
  4-turn stretch settled and chose one at once): `PILOT_AUTOPLAY_CHUNK` sets turns per call.
- Menus, when the screen must be used: the UI ignores a click without a preceding hover (move the
  mouse onto the button, then click), and the "Continue" screen after loading needs a key press.
- Throwaway games only: the tuner turns achievements off.
- The scripted last stand for a city about to fall (`PILOT_LAST_STAND=1`; off by default) sends
  unit and city actions: `civ6 last-stand-step`, `ls-state`, `finish-moves`, `turn-ready` (numeric
  IDs, never model orders). Its first live use follows the L6 checklist of
  `docs/design/2026-09-27-civ6-levers-design.md` on a throwaway save or in a maintenance window.
- District placement is read-only for now (stage A): `civ6 district-plots` and
  `scripts/civ6-placement.py` rate plots and the AI's placements; no placement order exists.
- The AI's own plan is read-only: each city's top 3 builds in the snapshot (`recommend`) and our
  strategies from `Logs/AI_Victories.csv` (`civ6 ai-strategies --offset N`: one agent read per
  decision, never a bulk read).

