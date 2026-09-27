#!/usr/bin/env bash
# Install the systemd user units from deploy/ with @REPO@ set to this checkout.
#   scripts/install-services.sh            # into ~/.config/systemd/user, then daemon-reload
#   SYSTEMD_USER_DIR=/tmp/x scripts/install-services.sh   # elsewhere (no reload)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${SYSTEMD_USER_DIR:-$HOME/.config/systemd/user}"
mkdir -p "$DEST"
for unit in "$ROOT"/deploy/*.service; do
  sed "s#@REPO@#$ROOT#g" "$unit" > "$DEST/$(basename "$unit")"
  echo "installed $DEST/$(basename "$unit")"
done
if [ -z "${SYSTEMD_USER_DIR:-}" ]; then
  systemctl --user daemon-reload
  echo "per-PC settings (GAME_AGENT_URL, GAME_RESOLUTION) go in a drop-in: systemctl --user edit game-pilot.service"
fi
