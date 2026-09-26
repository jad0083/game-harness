#!/usr/bin/env bash
# Hover the mouse at image coords to read a tooltip (GC4 shows hotkeys and effects in tooltips).
#   scripts/play/hover.sh X Y [X0 Y0 X1 Y1]
# Writes the full frame to s.jpg and a 2x crop of [X0,Y0,X1,Y1] (default: whole frame) to h.png.
set -euo pipefail
source "$(dirname "$0")/common.sh"
ensure_focus
SCREEN="$(ctl health | tr -d ' \n' | sed -n 's/.*"screen":\[\([0-9]*\),\([0-9]*\)\].*/\1 \2/p')"
read -r SW SH <<< "$SCREEN"
SX=$(( $1 * SW / 1568 )); SY=$(( $2 * SH / 882 ))
curl -s -m 5 -H "Authorization: Bearer $GAME_AGENT_TOKEN" -H 'Content-Type: application/json' \
  -X POST "$GAME_AGENT_URL/move" -d "{\"x\":$SX,\"y\":$SY}" >/dev/null
sleep "${WAIT:-1.3}"
ctl screenshot -o "$PLAY_DIR/s.jpg" >/dev/null
"$PY" - "$PLAY_DIR" "${3:-0}" "${4:-0}" "${5:-1568}" "${6:-882}" <<'PYEOF'
import sys
from PIL import Image
d, *box = sys.argv[1:]
im = Image.open(f"{d}/s.jpg").crop(tuple(int(v) for v in box))
im.resize((im.width * 2, im.height * 2)).save(f"{d}/h.png")
print(f"{d}/h.png")
PYEOF
