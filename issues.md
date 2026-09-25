# Issues

## Open

### Deployment

### Rust controller (`crates/game-controller`)
- [ ] `autopilot.rs:79` counts turns locally with no check that a turn advanced; `game.toml` screen fields (`luminance_roi`, `choice_keys`, `buttons`, `dismiss_key`, `title_ocr`, `is_blocking`) are parsed (`corpus.rs:38-55`) but never read; modal ROI hard-coded in `imaging.rs:132`
- [ ] `autopilot.rs:105-107` `click_norm` emits image-space coords without scaling (latent: no macro uses it yet)
- [ ] `client.rs:254-256` `focus` returns Ok on a 404 body; `settle`/`windows`/`focus` never check HTTP status (a 401 surfaces as a JSON parse error)
- [ ] Rust MCP has no `zoom`, `hover`, `scroll`, `list_windows`, or grid overlay; `GAME_SCREENSHOT_DIR` frame archive dropped from `.mcp.json`; `PLAYING.md` documents tools that no longer exist
- [ ] `clippy --all-targets`: 2 warnings (`corpus.rs:466`, `imaging.rs:28`); "0 warnings" achieved via `#![allow(dead_code, ...)]` in every file

### Rust agent (`crates/game-agent`)
- [ ] `main.rs:192-199` fallback token is a nanosecond timestamp in hex; `main.rs:214` non-constant-time compare; Python `--allow` client-IP list dropped
- [ ] `main.rs:256` `x + w` can wrap in release, bypassing the bounds check (GDI then fails; no crash)
- [ ] Console-subsystem exe launched as an interactive logon task → console window on the game desktop at every logon
- [ ] Zero tests for the shipped agent binary

### Repo hygiene / docs
- [ ] `windows_agent/game-agent.exe` (1.4 MB) is tracked and re-committed on every rebuild
- [ ] Stale `crates/game-agent/Cargo.lock`, `.gitignore`, and 413 MB `crates/game-agent/target/` from the pre-workspace build
- [ ] `.mcp.json` points at gitignored `./target/release/game-controller`; fresh clone has no MCP until `cargo build --release`, undocumented
- [ ] 12 stray `*.jpg` crops in the repo root and 16 MB `screenshots/` (ignored, should be deleted)
- [ ] Docs still overstate the autopilot: "1.12 s/turn" measures key-send time, not verified game turns (README/ARCHITECTURE §2, §7); `#![allow(dead_code, …)]` remains in `game-agent/main.rs` and controller files
- [ ] Corpus keyword search can rank a page that mentions a term above the page defining it (e.g. `draft colonists` → civ_abilities before executive_orders) until generated `order` records exist
- [ ] Python harness (`src/harness`, `windows_agent/agent.py`, 40 tests) is no longer deployed; its green suite covers nothing that runs (`agent.py` `settle` stub always returns `settled: True`)

## Resolved
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
