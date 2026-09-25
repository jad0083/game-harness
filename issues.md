# Issues

## Open
- [ ] Windows backend (ctypes GDI/SendInput) is untested on real hardware; only covered via fake backend (2026-09-25)

## Resolved
- [ ] install.ps1 Python check crashed on PS 5.1: one-element arg array unrolled to a string (`-c` splatted as `-`,`c`) and native stderr became terminating under `Stop` (2026-09-25; fixed, awaiting re-run on the PC)
