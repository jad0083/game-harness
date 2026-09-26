#!/usr/bin/env bash
# One action, then a fresh frame.
#   scripts/play/act.sh                      # just focus the game and screenshot
#   scripts/play/act.sh click 480 638        # any game-controller subcommand (image coords 1568x882)
#   scripts/play/act.sh key tab
#   WAIT=2 scripts/play/act.sh drag 188 310 422 310
# Always focuses the game first (never sends input to another window).
# Writes $GAME_PLAY_DIR/s.jpg (default play/s.jpg) and prints its path.
set -euo pipefail
source "$(dirname "$0")/common.sh"
ensure_focus
if [ "$#" -gt 0 ]; then ctl "$@" | tail -1; sleep "${WAIT:-1.2}"; fi
ctl screenshot -o "$PLAY_DIR/s.jpg" >/dev/null
echo "$PLAY_DIR/s.jpg"
