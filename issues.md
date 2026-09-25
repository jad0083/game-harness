# Issues

## Open

### Deployment
- [ ] Agent on 192.168.1.77 is the 12:04 build (7c4a284) without DPI awareness: reports 3072x1728 on a 3840x2160 display, screenshots captured at virtualized resolution, default `/screenshot` returns full-size JPEG (x-target-width 3072) (2026-09-25)
- [ ] `install.ps1:28` downloads `game-agent.exe` over the running exe before `Stop-ScheduledTask` (line 66) → update fails on the locked file under `$ErrorActionPreference='Stop'`; line 74 points at `agent.log`, which the Rust agent never writes; header still describes the Python agent (2026-09-25)
- [ ] `scripts/serve-agent.sh:18-20` silently skips a missing `game-agent.exe` → remote install fails with HTTP 404 instead of failing fast

### Rust controller (`crates/game-controller`)
- [ ] `mcp.rs:82-88` `to_screen_coords` passes raw image coords through as screen pixels when no screenshot has been taken or the point is out of range; `mcp.rs:377-378` defaults missing `x`/`y` to 0 → wrong-place clicks instead of an error
- [ ] `corpus.rs:472-558` tech parser keys most entries by an effects line: `corpus tech "Colonial Policies"` → not found; `corpus tech drive` → name "Unlocks Singularity Driver Ship Component", cost -102
- [ ] `autopilot.rs:79` counts turns locally with no check that a turn advanced; `game.toml` screen fields (`luminance_roi`, `choice_keys`, `buttons`, `dismiss_key`, `title_ocr`, `is_blocking`) are parsed (`corpus.rs:38-55`) but never read; modal ROI hard-coded in `imaging.rs:132`
- [ ] `autopilot.rs:105-107` `click_norm` emits image-space coords without scaling (latent: no macro uses it yet)
- [ ] `client.rs:254-256` `focus` returns Ok on a 404 body; `settle`/`windows`/`focus` never check HTTP status (a 401 surfaces as a JSON parse error)
- [ ] `corpus.rs:455` byte-slices `[..180]` → abort (`panic="abort"`) if a wiki paragraph has a multibyte char at that boundary
- [ ] Rust MCP has no `zoom`, `hover`, `scroll`, `list_windows`, or grid overlay; `GAME_SCREENSHOT_DIR` frame archive dropped from `.mcp.json`; `PLAYING.md` documents tools that no longer exist
- [ ] `clippy --all-targets`: 2 warnings (`corpus.rs:466`, `imaging.rs:28`); "0 warnings" achieved via `#![allow(dead_code, ...)]` in every file

### Rust agent (`crates/game-agent`)
- [ ] `main.rs:192-199` fallback token is a nanosecond timestamp in hex; `main.rs:214` non-constant-time compare; Python `--allow` client-IP list dropped
- [ ] `/batch` (`main.rs:436-471`): `count`/`repeat` unclamped, `parse_combo` errors swallowed and reported `ok:true`, `std::thread::sleep` blocks tokio workers
- [ ] `main.rs:256` `x + w` can wrap in release, bypassing the bounds check (GDI then fails; no crash)
- [ ] Console-subsystem exe launched as an interactive logon task → console window on the game desktop at every logon
- [ ] Zero tests for the shipped agent binary

### Repo hygiene / docs
- [ ] `windows_agent/game-agent.exe` (1.4 MB) is tracked and re-committed on every rebuild
- [ ] Stale `crates/game-agent/Cargo.lock`, `.gitignore`, and 413 MB `crates/game-agent/target/` from the pre-workspace build
- [ ] `.mcp.json` points at gitignored `./target/release/game-controller`; fresh clone has no MCP until `cargo build --release`, undocumented
- [ ] 12 stray `*.jpg` crops in the repo root and 16 MB `screenshots/` (ignored, should be deleted)
- [ ] `corpora/galciv4/wiki/` is ~12k lines scraped from wiki.galciv.com with no licence/attribution note
- [ ] Docs overstate the code: ARCHITECTURE.md "13 MCP tools" (code: 18), "AVX2 SIMD" (none), "in-memory token index" (linear scan), "<100 µs search" (measured 375–661 µs); README lists 17 tools
- [ ] Python harness (`src/harness`, `windows_agent/agent.py`, 40 tests) is no longer deployed; its green suite covers nothing that runs (`agent.py` `settle` stub always returns `settled: True`)

## Resolved
- [x] Windows backend (GDI capture, SendInput, focus) verified on real hardware against GC4 at 3840x2160 (2026-09-25)
- [x] install.ps1 Python check crashed on PS 5.1: one-element arg array unrolled to a string (`-c` splatted as `-`,`c`) and native stderr became terminating under `Stop` (2026-09-25; fixed in ef2987a, installed OK)
