#!/usr/bin/env bash
# Serve the Windows agent + installer (and the agent token) over HTTP so the Windows PC can install
# or update with a single PowerShell line.
#
# Usage: scripts/serve-agent.sh [port]        (default port 8000)
#
# Plain HTTP on the LAN, so the exposure is kept short and the payload is pinned:
#   - files are served under a random one-time path (/<32 hex>/...) printed only in the one-liner;
#   - the server binds the controller's address only and stops by itself after GA_SERVE_SECS
#     (default 900 s); stop it (Ctrl-C) as soon as the installer has finished;
#   - the one-liner carries the SHA-256 of install.ps1 (checked before it runs) and of
#     game-agent.exe (checked by install.ps1 before the running agent is replaced).
# Env: GA_BIND (address to bind and to put in the one-liner; default: this host's LAN address),
#      GA_SERVE_SECS, GA_EXE (a prebuilt game-agent.exe instead of the build), GA_DRY_RUN=1 (print
#      the one-liner and exit without serving).
set -euo pipefail
cd "$(dirname "$0")/.."

PORT=8000
for a in "$@"; do
  if [[ $a =~ ^[0-9]{1,5}$ ]]; then
    PORT=$a
  else
    echo "usage: scripts/serve-agent.sh [port]" >&2
    exit 2
  fi
done
SECS="${GA_SERVE_SECS:-900}"
MIN_TOKEN=32
TOKEN_FILE=.agent_token

if [[ ! -s $TOKEN_FILE ]]; then
  (umask 077 && openssl rand -base64 24 | tr '+/' '-_' | tr -d '=' > "$TOKEN_FILE")
  echo "generated a new token in $TOKEN_FILE"
fi
chmod 600 "$TOKEN_FILE"
TOKEN="$(tr -d '\r\n' < "$TOKEN_FILE")"
if (( ${#TOKEN} < MIN_TOKEN )); then
  echo "$TOKEN_FILE holds ${#TOKEN} characters; the agent (>= 1.5.0) needs at least $MIN_TOKEN." >&2
  echo "Delete it to generate a new one (then update GAME_AGENT_TOKEN users)." >&2
  exit 1
fi

if [[ -n ${GA_EXE:-} ]]; then
  EXE="$GA_EXE"
else
  # Build from source (not tracked in git); incremental, so a no-op when nothing changed.
  export PATH="$HOME/.cargo/bin:$PATH"
  cargo build --target x86_64-pc-windows-gnu --release --bin game-agent
  EXE=target/x86_64-pc-windows-gnu/release/game-agent.exe
fi

IP="${GA_BIND:-$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src") print $(i+1)}')}"
if [[ -z $IP ]]; then
  echo "could not find this host's LAN address; set GA_BIND" >&2
  exit 1
fi

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
chmod 700 "$STAGE"
RID="$(openssl rand -hex 16)"
mkdir "$STAGE/$RID"
: > "$STAGE/index.html"   # "/" shows an empty page, not a listing that would reveal the path
cp windows_agent/install.ps1 "$STAGE/$RID/"
cp "$EXE" "$STAGE/$RID/game-agent.exe"
cp "$TOKEN_FILE" "$STAGE/$RID/agent_token.txt"
EXE_SHA="$(sha256sum "$STAGE/$RID/game-agent.exe" | cut -d' ' -f1)"
PS1_SHA="$(sha256sum "$STAGE/$RID/install.ps1" | cut -d' ' -f1)"

echo
echo "game-agent.exe SHA-256: $EXE_SHA"
echo "install.ps1    SHA-256: $PS1_SHA"
echo
echo "On the Windows PC, open PowerShell (not as admin) and run this one line:"
echo
# shellcheck disable=SC2016  # PowerShell variables, printed literally
printf '  $env:GA_SRC='"'"'http://%s:%s/%s'"'"'; $env:GA_SHA256='"'"'%s'"'"'; $f="$env:TEMP\\ga-install.ps1"; iwr "$env:GA_SRC/install.ps1" -UseBasicParsing -OutFile $f; if ((Get-FileHash $f).Hash -ne '"'"'%s'"'"') { throw '"'"'install.ps1 hash mismatch'"'"' }; iex (Get-Content -Raw -Encoding UTF8 $f)\n' \
  "$IP" "$PORT" "$RID" "$EXE_SHA" "$PS1_SHA"
echo
echo "Serving on http://$IP:$PORT/ (this address only). Stop it (Ctrl-C) as soon as the installer"
echo "has finished: it serves the agent token. It stops by itself after $((SECS / 60)) minutes."
[[ -n ${GA_DRY_RUN:-} ]] && exit 0
timeout "$SECS" python3 -m http.server "$PORT" --bind "$IP" --directory "$STAGE" || true
echo "server stopped"
