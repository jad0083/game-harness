# Issues

## Open

- [ ] Telemetry: one decision made on United Nations of Earth 2 (2203.10) during the model-switch test is recorded under the old throwaway campaign, stretching its chart to 2201 (history kept as recorded; the campaign guard prevents new cases)

### Pilot / Stellaris (code review 2026-09-25, 7dc677a..616b501)
- [ ] (medium/low) `set_paused` Esc fallback: if the pause detector misreads the screen, Esc on the bare map opens the game menu

### Deployment

### Rust controller (`crates/game-controller`)
- [ ] `manifest.toml` screen fields `choice_keys`, `buttons`, `dismiss_key`, `title_ocr`, `is_blocking` are parsed but still unused (the autopilot now uses `luminance_roi`, `luminance_threshold`, `turn_indicator_roi`)
- [ ] Earth's **Capital City** (0 cost, +6 pop cap, +100 influence; `CapitalOnly`, `PlacementType: Special`) could not be placed: drag onto plains and onto the grassland "home" tile did nothing, double-click only selects it, and the tile menu lists only districts. Likely the agent's drag (button down → 12 moves at 20 ms → up) is too fast for the planet screen, or it needs a specific tile. Earth has a housing crisis (5/5 pop) until solved (found 2026-09-25, Feb 2330)
- [ ] GC4 turn hang in "Starting New Month" (game bug) occurred once after first contact with Baratak Grove, Jun 2331; recovered by quit + relaunch + autosave (2026-09-25). Recovery is manual; could become a macro (needs the launcher steps and a way to pick the save)
- [ ] Rust agent's key table lacks `win`/`lwin` (the Python agent had them), so `win+r` fails; Steam window focus was used instead (2026-09-25)
- [ ] `manifest.toml` macro `dismiss_tutorial` still presses `enter` then `esc`; `esc` on the bare map opens the pause menu — unverified and risky, don't run it
- [ ] Autopilot can't place buildings or choose research; those blockers always go to the model (plan.md "Autonomy")
- [ ] `.mcp.json` / `.gemini/settings.json` assume `./target/release/game-controller` is built; a fresh clone needs `cargo build --release -p game-controller` first (documented in AGENTS.md §2)
- [ ] Event option number keys (`1`/`2`/`3`) claimed in strategy.md are unverified; clicking works
- [ ] `autopilot.rs:105-107` `click_norm` emits image-space coords without scaling (latent: no macro uses it yet)
- [ ] `client.rs:254-256` `focus` returns Ok on a 404 body; `settle`/`windows`/`focus` never check HTTP status (a 401 surfaces as a JSON parse error)
- [ ] Rust MCP has no `zoom`, `hover`, `scroll`, `list_windows`, or grid overlay; `GAME_SCREENSHOT_DIR` frame archive dropped from `.mcp.json` (shell workaround: `scripts/play/hover.sh`)
- [ ] `clippy --all-targets`: 2 warnings (`corpus.rs:466`, `imaging.rs:28`); "0 warnings" achieved via `#![allow(dead_code, ...)]` in every file

### Rust agent (`crates/game-agent`)
- [ ] Installer picks the first *existing* docs folder: on the PC `stellaris_docs` resolved to a stale 2022 copy under `OneDrive\Documents` while Stellaris 4.5 likely writes to `MyDocuments` (`D:\OneDrive - Sacramento`); confirmed at launch: its logs stayed at 2022 while the game ran. Installer now picks the candidate with the newest files (2026-09-25)
- [ ] `main.rs:192-199` fallback token is a nanosecond timestamp in hex; `main.rs:214` non-constant-time compare; Python `--allow` client-IP list dropped
- [ ] `main.rs:256` `x + w` can wrap in release, bypassing the bounds check (GDI then fails; no crash)
- [ ] Console-subsystem exe launched as an interactive logon task → console window on the game desktop at every logon
- [ ] Zero tests for the shipped agent binary

### Repo hygiene / docs
- [ ] `windows_agent/game-agent.exe` (1.4 MB) is tracked and re-committed on every rebuild
- [ ] Stale `crates/game-agent/Cargo.lock`, `.gitignore`, and 413 MB `crates/game-agent/target/` from the pre-workspace build
- [ ] `.mcp.json` points at gitignored `./target/release/game-controller`; fresh clone has no MCP until `cargo build --release`, undocumented
- [ ] `#![allow(dead_code, …)]` remains in `game-agent/main.rs`, `imaging.rs`, `mcp.rs` (removed from `corpus.rs`, `autopilot.rs`)
- [ ] Python harness (`src/harness`, `windows_agent/agent.py`, 40 tests) is no longer deployed; its green suite covers nothing that runs (`agent.py` `settle` stub always returns `settled: True`)
- [ ] Agent key table has no numpad keys or `+`; Stellaris speed-up must use `=` (VK_OEM_PLUS) until added

## Resolved
- [x] Dashboard kept showing the previously selected campaign when a run started on a different one, so a reload was needed to see the live game (2026-09-25; the page now follows the live campaign unless another was picked deliberately; all responses no-store; browser test)
- [x] A transient Gemini 503 ("high demand") skipped a governor decision (2026-09-25; transient 429/5xx are retried after 5, 15 and 45 s with a feed entry; tests)
- [x] The governor fixed its campaign at start; when the user loaded another game mid-run (United Nations of Earth 2), the next decision applied `expand` there and was recorded under the old campaign (2026-09-25; every briefing's save folder is now checked, a different game pauses the run with needs-attention; test)
- [x] `take-control` failed to read the console's reply to human_ai when a bright nebula was behind the semi-transparent console (template distances 0.103 / 0.130); the governor correctly waited for the human instead of crashing (2026-09-25; replies are now read from white-text masks: right word ≤ 0.023, wrong ≥ 0.057 on 4 real frames; fixture added)
- [x] Model picker listed Gemini models that cannot play (TTS, image, transcription, robotics, computer-use) (2026-09-25; filtered; test)
- [x] Every "learned" / "learn_rejected" event raised TypeError: `emit(kind, …)` was also given `kind=` as data, so the governor's `remember_rule` and GC4's learning tools failed whenever a model used them (found 2026-09-25 while adding retrospectives; data key renamed to `category`; regression test)
- [x] (medium) Chat history slice `[-20:]` can start with an orphan tool result; providers reject it and chat stays broken for the run (`governor._chat`) (2026-09-25; whole exchanges kept (last 6); test)
- [x] (medium) `prepare_war` approval takes any pending note as the answer and treats text starting with "y" as yes; answers need their own channel (`HumanChannel.ask`) (2026-09-25; answers have their own channel (dashboard Yes/No/answer box); notes never answer; exact yes; tests)
- [x] (low-medium) `HumanAiReader::set` leaves the console open when a screenshot or decode fails mid-read (2026-09-25; console closed even when reading fails)
- [x] (low-medium) `take_control` types `play <id>` with the id from the newest autosave of any campaign and doesn't re-check the scope probe afterwards; campaign detection uses the same newest-save rule (2026-09-25; scope probe re-checked after `play`, loud failure otherwise (campaign detection by newest save remains; documented))
- [x] (low) Outcome scoring can mix metrics from different runs of a campaign (reloaded older save) and labels any later point "12 months later" (2026-09-25; same run only, end point within +3 months of the mark; test)
- [x] (low) `rebuild-telemetry` is not transactional; a corrupt trace file aborts it half-way (2026-09-25; one transaction, corrupt trace files tolerated; test)
- [x] (low) Dashboard: some server numbers are not escaped; FAILED outcomes are double-escaped (`&amp;quot;`) (2026-09-25; all server values escaped once)
- [x] (low) Stellaris foreground check matches the substring "Stellaris" (a browser tab titled "Stellaris Wiki" would pass) (2026-09-25; exact title "Stellaris" in Rust and the pilot)
- [x] Governor crashed on non-RuntimeError failures (agent unreachable: URLError; MCP pipe; JSON), crashed on startup failures, and could spin on a failing queued request (2026-09-25, code review #1–3; any failure → needs-attention, startup retries after Resume, failed requests are consumed and followed by a back-off; 3 tests)
- [x] Stellaris: in observer mode the AI never explored or expanded our empire (1 system 2200–2212 while AI empires reached 9–18); the spike had judged by starbase capacity (2026-09-25; switched to `human_ai`, 1 → 4 systems in 3.5 years; briefing now reports systems owned)
- [x] Stellaris game.log drops repeated log text on the same in-game day, so repeated directives looked unconfirmed (2026-09-25; unique nonce per marker, 8 s polling)
- [x] Corpus summary pointed every game at corpora/galciv4/data/README.md (2026-09-25; now names the loaded corpus directory)
- [x] Live governor run died after 3 decisions: "could not resume the game: the Paused label did not disappear". Stellaris's system search (hotkey F) was open with keyboard focus, so Space went into the text box; stray keys typed while the pilot had focused the game are the likely cause (2026-09-25; set_paused now tries one Esc before giving up, and the governor flags needs-attention instead of crashing; reproduced and verified live)
- [x] Governor: pausing from the dashboard triggered a model decision ("paused by the human" was treated as a decision point) (2026-09-25; fixed, regression test)
- [x] Pilot auto-commit body named the model, against the no-model-names rule (2026-09-25; fixed)
- [x] Stellaris pause was toggled blind with Space; runs at Fastest ended in the wrong state, and the first "Paused" template misread the pulsing label (distance 0.108) as running (2026-09-25; colour signature + checked `set_paused`, verified live 3× pause/resume cycles)
- [x] Image test fixtures `crates/game-controller/tests/fixtures/*.jpg` were gitignored (`*.jpg`), so 3 imaging tests failed in any fresh clone (2026-09-25; ignore exception added, fixtures tracked, fresh clone tested)
- [x] Agent reported no file roots: PS 5.1 wrote `roots.json` with a BOM and the loader ignored the parse error; re-registering an elevated scheduled task failed with Access denied (2026-09-25; 8d81a44, redeployed, 4 roots verified)
- [x] 12 stray `*.jpg` crops in the repo root and `screenshots/` (2026-09-25; moved to gitignored `play/archive/`)
- [x] `PLAYING.md` documented Python-era MCP tools (`status`, `zoom`, `focus_game`) (2026-09-25; rewritten with a quick reference, procedure in AGENTS.md)
- [x] Docs were Claude-specific (`CLAUDE.md` only) and the play loop lived in untracked scratch scripts (2026-09-25; `AGENTS.md`, `GEMINI.md`, `.gemini/settings.json`, `scripts/play/`)
- [x] "Colonize Planet?" confirmation dims the HUD, so the loop stopped before checking known screens; and when it appeared after a camera pan the pre-turn check returned Modal (2026-09-25; retry on any non-advanced verdict, settle after each dismissal; 0dca505, 0f95cf0)
- [x] Re-pressing Survey on a ship that was already surveying asked to abandon the survey (2026-09-25; `only_when_blocked` + `survey_abandon_confirm` → No; 0f4e557)
- [x] Turns stuck in AI processing were reported as blocked after the 8 s settle (2026-09-25; `busy` screens extend the wait to 180 s; 68cc89f)
- [x] Colony ship boarding dialog blocked every new colony ship (2026-09-25; `colony_ship_boarding` click sequence; bc34180)
- [x] Manifest `end_turn` was `enter`; the game ends turns with TAB, and `space`/`f`/`e` hotkeys were wrong (2026-09-25; corrected from live tooltips: explore = O, standby = J; b0059ae, e19ddbc)
- [x] Autopilot judged a turn 0.9 s after the key, before the game finished processing, and reported a real advance as NotAdvanced (2026-09-25; now waits for the date to change; b0059ae)
- [x] Date change "Jul → Aug" read as unchanged: whole-box mean diff 0.028 < 0.03 (2026-09-25; per-glyph strip metric, real-frame fixtures; e19ddbc)
- [x] GNN news bulletin blocked the loop (2026-09-25; template match + auto Close; c67c8b5)
- [x] `game-controller corpus …` required an agent token although it works offline (2026-09-25; test added)
- [x] Root `ruff check .` linted other agents' worktrees under `.claude/`, and a CI failure was committed because `| tail` hid the exit code (2026-09-25; excluded worktrees; `scripts/ci-commit.sh` gates commits on CI)
- [x] `turn_indicator_roi` and `NotAdvanced` detection validated live: with a pending leader prompt the date readout stayed identical (diff 0.000) and the autopilot reported the blocked turn instead of counting it (2026-09-25)
- [x] Rust agent key injection was unproven on real hardware (only the Python agent had been); verified live 2026-09-25 (`esc` opened the game's pause menu)
- [x] Autopilot counted turns locally with no check that a turn advanced, and hard-coded its modal ROI (2026-09-25; now diffs the manifest's `turn_indicator_roi` before/after the macro, returns `NotAdvanced` when unchanged, reads `luminance_roi`/threshold from the manifest, and refuses to send keys unless the game is foreground; 4 classifier tests)
- [x] Docs claimed "1.12 s/turn" for the autopilot, which measured key-send time rather than game turns (2026-09-25; replaced by a description of the verification)
- [x] Corpus keyword search ranked wiki mentions above the defining page for `draft colonists` (2026-09-25; generated `order` records now match by name and rank first)
- [x] Heuristic wiki tech/improvement/order parsers produced mangled records (`corpus tech drive` → cost −102; `Colonial Policies` not found) (2026-09-25; removed, replaced by generated `data/*.json` records with a loader that rejects bad data; lookups now say when data is missing)
- [x] `corpus.rs` byte-sliced excerpts at 180 could abort on a multibyte boundary (2026-09-25; removed with the rewrite, all truncation is char-based)
- [x] Docs overstated the corpus/MCP: "13 tools" (now 19, documented), "AVX2 SIMD" (removed), "token index / <100 µs" (now described as a linear scan, measured 50–100 µs) (2026-09-25)
- [x] `corpora/galciv4/wiki/` had no licence/attribution (2026-09-25; moved to `docs/*.md`, each with `Source:` and `License:` headers)
- [x] Agent `/batch` had unclamped `count`/`repeat`, swallowed `parse_combo` errors as `ok:true`, and `/type` accepted unbounded text (2026-09-25; fixed in 13a7352 with tests, redeployed, verified live: bad combo and 1001-char text both return 400)
- [x] Rust MCP `to_screen_coords` passed raw image coords through as screen pixels when no screenshot had been taken or the point was out of range; missing `x`/`y` defaulted to 0 (2026-09-25; fixed with tests, controller rebuilt, verified over stdio: all such calls now return tool errors before reaching the agent)
- [x] Agent on 192.168.1.77 was the 12:04 build (7c4a284) without DPI awareness: reported 3072x1728 on a 3840x2160 display and captured at virtualized resolution (2026-09-25; redeployed the `79fb15a` build via the fixed installer, `/health` now reports 3840x2160 and `max_side=1568` yields 1568x882)
- [x] `install.ps1` downloaded `game-agent.exe` over the running exe before stopping the task → update failed on the locked file; also pointed at an `agent.log` the Rust agent never writes (2026-09-25; fixed in 3e425bf, verified by a successful update on the PC)
- [x] `scripts/serve-agent.sh` silently skipped a missing `game-agent.exe` → HTTP 404 on install instead of failing fast (2026-09-25; fixed in 3e425bf)
- [x] Windows backend (GDI capture, SendInput, focus) verified on real hardware against GC4 at 3840x2160 (2026-09-25)
- [x] install.ps1 Python check crashed on PS 5.1: one-element arg array unrolled to a string (`-c` splatted as `-`,`c`) and native stderr became terminating under `Stop` (2026-09-25; fixed in ef2987a, installed OK)
