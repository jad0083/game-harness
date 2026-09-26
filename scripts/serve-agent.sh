#!/usr/bin/env bash
# Serve the Windows agent + installer (and the shared token) over HTTP so the
# Windows PC can install or update with a single PowerShell line.
# Usage: scripts/serve-agent.sh [port]   (Ctrl-C to stop once installed)
set -euo pipefail
cd "$(dirname "$0")/.."
PORT="${1:-8000}"

if [[ ! -s .agent_token ]]; then
  openssl rand -base64 24 | tr '+/' '-_' | tr -d '=' > .agent_token
  chmod 600 .agent_token
  echo "generated new token in .agent_token"
fi

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
cp windows_agent/install.ps1 "$STAGE/"
# Build from source (not tracked in git); incremental, so a no-op when nothing changed.
export PATH="$HOME/.cargo/bin:$PATH"
cargo build --target x86_64-pc-windows-gnu --release --bin game-agent
cp target/x86_64-pc-windows-gnu/release/game-agent.exe "$STAGE/"
cp .agent_token "$STAGE/agent_token.txt"

IP="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src") print $(i+1)}')"
echo
echo "On the Windows PC, open PowerShell (not as admin) and run:"
echo
echo "  \$env:GA_SRC='http://${IP}:${PORT}'; irm \"\$env:GA_SRC/install.ps1\" | iex"
echo
cd "$STAGE" && exec python3 -m http.server "$PORT" --bind 0.0.0.0
