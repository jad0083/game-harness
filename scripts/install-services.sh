#!/usr/bin/env bash
# Install the systemd user unit(s) from deploy/ with @REPO@ set to this checkout.
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
# the dashboard draws sign-in QR codes with segno (a dependency in pyproject.toml): say so before a deploy
if [ -x "$ROOT/.venv/bin/python" ] && ! "$ROOT/.venv/bin/python" -c "import segno" 2>/dev/null; then
  echo "segno is missing from $ROOT/.venv: Add a device will show no QR code. Before deploying: $ROOT/.venv/bin/pip install segno"
fi
if [ -z "${SYSTEMD_USER_DIR:-}" ]; then
  systemctl --user daemon-reload
  echo "per-PC settings (GAME_AGENT_URL, GAME_AGENT_TOKEN, GAME_RESOLUTION) go in a drop-in: systemctl --user edit game-pilot-view.service"
fi
