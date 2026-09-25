# Plan

## Harness
- [x] Windows agent: stdlib HTTP API for screenshot + mouse/keyboard + window focus, bearer token
- [x] One-line Windows installer (Python check, subnet-only firewall rule, logon task)
- [x] Linux MCP server with image-space coordinates, zoom, grid overlay, action→screenshot
- [x] CLI for manual smoke tests
- [ ] Install agent on 192.168.1.77 and verify screenshot + click end-to-end
- [ ] Confirm GC4 capture works in borderless mode (not black) and input registers in-game

## Playing
- [ ] Record verified GC4 controls/UI positions in PLAYING.md
- [ ] Play a first full turn cycle autonomously
- [ ] Per-game journal (`games/<save>/journal.md`) for long-game memory
- [ ] Optional: launch GC4 from the harness (Steam/Epic URI) when it isn't running
