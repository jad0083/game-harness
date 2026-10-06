#!/usr/bin/env bash
# Deploy a change to this checkout's services, restarting only what it affects
# (docs/design/2026-09-27-postmortem-fixes-design.md, ruling 28: a Stellaris-only merge restarted the live
# Civ VI run at T462). Run it on the controller after the merge (and after `git pull`), from any directory:
#   scripts/deploy-pilot.sh <from> <to>             e.g. the commit deployed before and HEAD
#   scripts/deploy-pilot.sh <from> <to> --dry-run   print what it would do; change nothing
# scripts/pilot-affected.py classifies the changed paths. The running pilot's game comes from its own
# dashboard's /status (info.game; PILOT_PORT, the key from PILOT_DASHBOARD_KEY, else the data directory's
# secrets/dashboard.key, else its dashboard.key from before the data platform), or
# from the store's prefs when no pilot runs. A Rust change pauses the pilot through its dashboard,
# builds the controller and resumes a Civ VI pilot (each call runs the binary afresh; a pilot the human had
# paused stays paused); a Stellaris or GalCiv IV pilot keeps one `game-controller mcp` child for the run,
# so it is restarted instead. game-pilot.service restarts when its game's files or shared code changed;
# game-pilot-view.service restarts for the dashboard's static files and any src/pilot/*.py.
set -euo pipefail
export PATH="$HOME/.cargo/bin:$PATH"                 # cargo, as in scripts/ci.sh
cd "$(dirname "$0")/.."
[ $# -ge 2 ] || { echo "usage: $0 <from> <to> [--dry-run]" >&2; exit 2; }
from="$1" to="$2" dry=0
[ "${3:-}" = "--dry-run" ] && dry=1
py=.venv/bin/python
run() { if [ "$dry" -eq 1 ]; then echo "would run: $*"; else echo "+ $*"; "$@"; fi; }

port="${PILOT_PORT:-8790}"
# one key's first value in .env, trimmed of spaces and quotes as config.py's load_dotenv does; sed reads only
# that key (.env holds secrets: never cat or source it)
dotenv_value() {
  sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*//p" .env 2>/dev/null | head -n 1 \
    | sed -e 's/[[:space:]]*$//' -e 's/^["'\'']*//' -e 's/["'\'']*$//' || true
}
# the data directory as config.py finds it: each key from the environment, else from .env; PILOT_DATA_DIR
# before its alias PILOT_RUNS_DIR; else runs/
data_dir="${PILOT_DATA_DIR:-$(dotenv_value PILOT_DATA_DIR)}"
runs_dir="${PILOT_RUNS_DIR:-$(dotenv_value PILOT_RUNS_DIR)}"
data="${data_dir:-${runs_dir:-runs}}"
key="${PILOT_DASHBOARD_KEY:-$(cat "$data/secrets/dashboard.key" 2>/dev/null || cat "$data/dashboard.key" 2>/dev/null || true)}"
status() { curl -fsS -m 3 -H "X-Pilot-Key: $key" "http://127.0.0.1:$port/status" 2>/dev/null || true; }
control() {
  curl -fsS -m 10 -H "X-Pilot-Key: $key" -H "Content-Type: application/json" \
    -d "{\"action\": \"$1\"}" "http://127.0.0.1:$port/control" >/dev/null
}
# "<run status> <game>" from /status on stdin ("" when unreadable)
state_game() { "$py" -c 'import json, sys
try:
    d = json.load(sys.stdin)
except ValueError:
    d = {}
print(d.get("status") or "-", (d.get("info") or {}).get("game") or "")' 2>/dev/null || true; }

running=0 held=""
systemctl --user is-active --quiet game-pilot.service && running=1
if [ "$running" -eq 1 ]; then
  read -r run_status game <<<"$(status | state_game)" || true
  # a pilot paused by the human or waiting for one is left as it is: never paused or resumed here
  case "${run_status:-}" in paused|needs_attention) held=yes ;; esac
else
  game="$("$py" -m pilot prefs --get game 2>/dev/null || true)"
fi
game="${game:-unknown}"

eval "$("$py" scripts/pilot-affected.py "$from" "$to" --game "$game" --running "$running" --format env)"
echo "changed: ${CLASSES:-nothing}"

if [ "$BUILD" = "1" ]; then
  if [ "$running" -eq 1 ] && [ -z "$held" ]; then
    if [ "$dry" -eq 1 ]; then echo "would pause the $game pilot through its dashboard"
    elif ! control pause; then
      echo "could not pause the pilot through its dashboard (port $port): pause it, then build and resume by hand" >&2
      exit 1
    fi
  fi
  run cargo build --release -p game-controller
  if [ "$running" -eq 1 ] && [ -z "$held" ] && [ "$RESTART_PILOT" != "1" ]; then
    if [ "$dry" -eq 1 ]; then echo "would resume the $game pilot through its dashboard"; else control resume; fi
  fi
fi

if [ "$RESTART_PILOT" = "1" ]; then
  echo "$MESSAGE"
  run systemctl --user restart game-pilot.service
else
  echo "$MESSAGE"
fi

if [ "$RESTART_VIEW" = "1" ]; then
  if systemctl --user is-active --quiet game-pilot-view.service; then
    run systemctl --user restart game-pilot-view.service
  else
    echo "the viewer (game-pilot-view.service) is not running: nothing to restart"
  fi
fi
