# Shared settings for the play helpers. Source it; do not run it.
# Override with environment variables:
#   GAME_AGENT_URL   agent base URL            (default: GAME_AGENT_URL in <repo>/.env)
#   GAME_AGENT_TOKEN agent bearer token        (default: GAME_AGENT_TOKEN in <repo>/.env, else <repo>/.agent_token)
#   GAME_PLAY_DIR    where frames are written  (default: <repo>/play, gitignored)
#   GAME_TITLE       game window title substring (default "Galactic Civilizations")
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if [ -z "${GAME_AGENT_URL:-}" ] && [ -f "$ROOT/.env" ]; then
  GAME_AGENT_URL="$(sed -n 's/^[[:space:]]*GAME_AGENT_URL[[:space:]]*=[[:space:]]*//p' "$ROOT/.env" | tail -1 | tr -d "\"'")"
fi
[ -n "${GAME_AGENT_URL:-}" ] || { echo "set GAME_AGENT_URL (environment or <repo>/.env), e.g. http://<pc-address>:8765" >&2; exit 2; }
export GAME_AGENT_URL
if [ -z "${GAME_AGENT_TOKEN:-}" ] && [ -f "$ROOT/.env" ]; then
  GAME_AGENT_TOKEN="$(sed -n 's/^[[:space:]]*GAME_AGENT_TOKEN[[:space:]]*=[[:space:]]*//p' "$ROOT/.env" | tail -1 | tr -d "\"'")"
fi
if [ -z "${GAME_AGENT_TOKEN:-}" ]; then
  [ -s "$ROOT/.agent_token" ] || { echo "no agent token: set GAME_AGENT_TOKEN or create $ROOT/.agent_token" >&2; exit 2; }
  export GAME_AGENT_TOKEN="$(tr -d '\n' < "$ROOT/.agent_token")"
fi
PLAY_DIR="${GAME_PLAY_DIR:-$ROOT/play}"
GAME_TITLE="${GAME_TITLE:-Galactic Civilizations}"
CTL="$ROOT/target/release/game-controller"
CORPUS="$ROOT/corpora/galciv4"
PY="$ROOT/.venv/bin/python"; [ -x "$PY" ] || PY=python3
[ -x "$CTL" ] || { echo "build the controller first: cargo build --release -p game-controller" >&2; exit 2; }
mkdir -p "$PLAY_DIR"
ctl() { "$CTL" --corpus "$CORPUS" "$@"; }
foreground() { ctl health | sed -n 's/.*"foreground": "\(.*\)",*$/\1/p'; }
ensure_focus() {
  case "$(foreground)" in *"$GAME_TITLE"*) ;; *) ctl focus "$GAME_TITLE" >/dev/null; sleep 1;; esac
}
