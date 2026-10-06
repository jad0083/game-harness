#!/bin/sh
# Container entrypoint (appliance image design, ruling 4): check the data directory, then run the
# dashboard, under Litestream when a replica is configured.
set -eu
DATA="${PILOT_DATA_DIR:-/data}"
CONFIG="${LITESTREAM_CONFIG:-/app/docker/litestream.yml}"
if [ ! -d "$DATA" ] || ! ( : > "$DATA/.write-test" ) 2>/dev/null; then
  echo "game-pilot: cannot write the data directory $DATA as uid $(id -u); fix: chown $(id -u):$(id -g) the host folder mounted there" >&2
  exit 1
fi
rm -f "$DATA/.write-test"
if [ -n "${LITESTREAM_REPLICA_URL:-}" ]; then
  # only into an empty directory, and only when the replica holds a backup (0.5: -if-replica-exists
  # exits 0 when none is found)
  if [ ! -e "$DATA/pilot.db" ]; then
    litestream restore -config "$CONFIG" -if-replica-exists "$DATA/pilot.db"
  fi
  exec litestream replicate -config "$CONFIG" -exec "pilot view --port 8780"
fi
exec pilot view --port 8780
