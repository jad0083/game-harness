#!/usr/bin/env bash
# Run the verified autopilot for up to N turns (default 10).
#   scripts/play/ap.sh 20
# Prints one line per turn: "advanced", "dialog detected", or "did NOT advance: <reason>".
# The frame it stopped on is written to $GAME_PLAY_DIR/current_screen.jpg - look at it,
# resolve the blocker (see AGENTS.md "Decision procedure"), then run ap.sh again.
set -euo pipefail
source "$(dirname "$0")/common.sh"
ensure_focus
cd "$PLAY_DIR"   # the controller writes current_screen.jpg / modal_event.jpg to the cwd
ctl autopilot --turns "${1:-10}" 2>&1 | grep -v '^==='
echo "stop frame: $PLAY_DIR/current_screen.jpg"
