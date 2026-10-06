#!/usr/bin/env bash
# Smoke checks for the Game Pilot image: scripts/image-smoke.sh <image>
# Starts it with an empty /data and no settings of its own, then checks health, sign-in, the proxy
# header rule, the data check, what the image holds, the user and a clean stop. Exits on the first failure.
set -euo pipefail
IMAGE="${1:?usage: image-smoke.sh <image>}"
PORT="${SMOKE_PORT:-18780}"
NAME="game-pilot-smoke-$$"
DATA="$(mktemp -d)"
chmod 0700 "$DATA"
cleanup() {
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  # empty it as the container's user, then hand the folder back so the host-side rm can remove it
  docker run --rm -u 0 -v "$DATA:/d" --entrypoint sh "$IMAGE" \
    -c "rm -rf /d/* /d/.[!.]*; chown $(id -u):$(id -g) /d" >/dev/null 2>&1 || true
  rm -rf "$DATA" 2>/dev/null || true
}
trap cleanup EXIT
fail() { echo "FAIL: $*" >&2; docker logs --tail 30 "$NAME" >&2 2>&1 || true; exit 1; }
ok() { echo "ok   $*"; }
BASE="http://127.0.0.1:$PORT"

# the data folder belongs to uid 10010 (the image's user), as a host folder would be set up
docker run --rm -u 0 -v "$DATA:/d" --entrypoint chown "$IMAGE" 10010:10010 /d || fail "could not own the data dir"
# requests from the host arrive from the bridge gateway: trust it as the proxy, with a test secret
GATEWAY="$(docker network inspect bridge -f '{{(index .IPAM.Config 0).Gateway}}')" || fail "no bridge gateway"
SECRET="smoke-proxy-secret-$$-$RANDOM"
docker run -d --name "$NAME" -p "127.0.0.1:$PORT:8780" -v "$DATA:/data" \
  -e "PILOT_TRUSTED_PROXIES=$GATEWAY" -e "PILOT_PROXY_SECRET=$SECRET" "$IMAGE" >/dev/null || fail "container did not start"

for _ in $(seq 60); do
  [ "$(docker inspect -f '{{.State.Health.Status}}' "$NAME")" = healthy ] && break
  [ "$(docker inspect -f '{{.State.Running}}' "$NAME")" = true ] || fail "container exited"
  sleep 1
done
[ "$(docker inspect -f '{{.State.Health.Status}}' "$NAME")" = healthy ] || fail "not healthy within 60 s"
ok "healthy with an empty /data and no settings"

[ "$(curl -s "$BASE/healthz")" = ok ] || fail "/healthz is not 'ok'"
ok "GET /healthz -> ok"

read -r code loc < <(curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' "$BASE/")
[[ "$code" =~ ^30[23]$ && "$loc" == "$BASE/pair"* ]] || fail "GET / -> $code $loc (want 302/303 to /pair)"
ok "GET / -> $code to /pair"

# Remote-User with a made-up proxy secret, even from the trusted proxy address, is an ordinary unsigned request
code="$(curl -s -o /dev/null -w '%{http_code}' -H 'Accept: application/json' -H 'X-Forwarded-For: 10.0.0.9' \
  -H 'X-Forwarded-Proto: https' -H 'X-Pilot-Proxy: not-a-secret' -H 'Remote-User: intruder' "$BASE/api/auth/me")"
[ "$code" = 401 ] || fail "forged proxy headers -> $code (want 401)"
ok "forged proxy headers are not trusted (401)"

# the right secret and Remote-User from the trusted address is the proxy's signed-in user
me="$(curl -s -H 'Accept: application/json' -H 'X-Forwarded-Proto: https' -H "X-Pilot-Proxy: $SECRET" \
  -H 'Remote-User: smoke-user' "$BASE/api/auth/me")"
[[ "$me" == *\"via\":\ \"proxy\"* ]] || fail "proxy secret + Remote-User not accepted: $me"
ok "proxy secret + Remote-User accepted (via proxy)"

# a root with no old install (an empty folder; /app itself holds the shipped learned rules, which
# `data check` would count as old-install files the store lacks)
out="$(docker exec "$NAME" sh -c 'd=$(mktemp -d) && pilot data check --from "$d"')" || fail "data check exited non-zero: $out"
[[ "$out" == nothing\ missing:* ]] || fail "data check said: $out"
ok "pilot data check: $out"

listing="$(docker exec "$NAME" sh -c 'ls -a /app; test ! -e /app/.env && test ! -e /app/runs && test ! -e /app/.git && ! ls /app/.agent_token* /app/play 2>/dev/null')" \
  || fail "the image holds .env, runs, .git, .agent_token* or play: $listing"
ok "no .env, runs, .git, .agent_token* or play in /app"

[ "$(docker exec "$NAME" id -u)" = 10010 ] || fail "not running as uid 10010"
ok "runs as uid 10010"

start=$SECONDS
docker stop "$NAME" >/dev/null
took=$((SECONDS - start))
[ "$took" -le 45 ] || fail "stop took ${took}s (limit 45)"
[ "$(docker inspect -f '{{.State.ExitCode}}' "$NAME")" != 137 ] || fail "killed by SIGKILL, not a clean stop"
ok "docker stop in ${took}s"
echo "image smoke OK: $IMAGE"
