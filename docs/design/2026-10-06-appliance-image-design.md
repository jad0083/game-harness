# Appliance image and estate stack: one container, the dashboard supervising the pilot

Date: 2026-10-06. Status: design approved in conversation (sections 1-5); rulings below are numbered from 1.
Base: `main` at 822a7f2.

This is sub-project 2 of the portability programme (docs/design/2026-10-05-data-platform-design.md, which
lists all four). Sub-project 1, the data platform, is deployed: every write goes to one data directory
(`pilot.db`, `auth.sqlite`, `frames/`, `learned/`, `secrets/`), and code and corpora are read-only. This
design puts the app in one image and runs it in two ways:

- **Portable**: a plain `compose.yaml` and `.env.example` in this repo. Every secret and setting is an
  environment variable, and nothing is specific to Komodo or OpenBao. A server, someone else's machine or one
  Docker Desktop PC runs it with `docker compose up -d`.
- **The user's estate**: a stack in `jad0083/stacks` (`apps/games/game-pilot/`) deployed by Komodo through
  GitOps, with secrets rendered from OpenBao by Periphery, on deb-dock1.

---

## Evidence

- **E1. Today's install** (deb-mini2, 2026-10-06): two systemd user units run from the checkout:
  `game-pilot-view.service` (`pilot view --port 8780`) and `game-pilot.service` (`pilot run`). The dashboard
  starts a run with `systemctl --user start game-pilot.service` (`dashboard.py` `api_run`). Drop-ins hold
  `GAME_AGENT_URL`, `GAME_AGENT_TOKEN` and `GAME_RESOLUTION` (both units) and `PILOT_TRUSTED_PROXIES`,
  `PILOT_PROXY_SECRET` and `PILOT_PUBLIC_URL` (the viewer). `.env` holds the model keys.
- **E2. Deploying** goes through `scripts/deploy-pilot.sh` and `scripts/pilot-affected.py`, which restart only
  what a change affects, so an unrelated merge does not stop a live run (postmortem-fixes design, ruling 28).
- **E3. Estate conventions** (`jad0083/stacks`, `jad0083/komodo`, read 2026-10-06):
  - A stack is `compose.yaml` + `komodo.toml` + `README.md`, grouped by function.
  - Images are pinned `tag@sha256:digest`, and Renovate opens digest PRs at night with automerge off.
    Stateful stacks stay on this pinned lane.
  - Secrets live at `secret/apps/<stack>/<KEY>`. A `[[NAME]]` in `komodo.toml` is resolved by Periphery from a
    host-rendered `[secrets]` table, and every `[[X]]` must appear as `${X}` in the compose (a test).
  - Data is bind-mounted under `/mnt/dockervol/<stack>/` and owned by the container's uid.
  - Every service declares `restart`. A port published on the LAN gets a DOCKER-USER guard so that only NPM
    (192.168.1.50) reaches it.
  - Own images are built by GitHub Actions in the app's repo and pushed to `ghcr.io/jad0083/*`. The precedent
    is `subtitler/.github/workflows/docker.yml`: preflight tests, then build, smoke, push; version tags are
    immutable, plus `:sha-<short>` and `:latest`. Stacks pull without registry credentials.
  - No stack has a backup of its own data, and nothing uses Litestream.
- **E4. deb-dock1** is 192.168.1.53 (Proxmox LXC 304, Debian 13, Docker 29). Its Periphery is enrolled and it
  runs `plex-main` through Komodo.
- **E5. The game-harness repository is public**, so a package published from it can be pulled anonymously
  like the other own images.
- **E6. The first live run on the data platform** (Alexander T174-T221, 2026-10-06) worked end to end from the
  checkout.

## Goals

1. One image that runs the dashboard and, under it, the pilot, with no git, Rust toolchain, systemd or checkout
   on the host.
2. A portable compose that needs three values (a model key, the agent URL, the agent token) and a data folder.
3. The user's Game Pilot running as a pinned Komodo stack on deb-dock1, at the same URL, with the live history,
   devices and keys carried over.
4. A redeploy or reboot during a run costs one clean stop and an automatic resume, not an idle campaign.
5. Continuous replication of `pilot.db` when a Litestream replica is configured; nothing when it is not.

## Non-goals

- Multi-arch images, GitHub releases and public setup docs beyond the README (sub-project 4).
- Agent pairing and a PC registry in the store; `GAME_AGENT_URL`, `GAME_AGENT_TOKEN` and `GAME_RESOLUTION`
  stay environment variables (sub-project 3).
- A Litestream replica in the estate (the user chose to leave it off for now).
- The `claude-code` provider in the image (the user's pools are Gemini only).
- Deferring a Komodo redeploy until the run reaches a pause point.

---

## Rulings

1. **Two layers.** This repo holds the portable `compose.yaml` and `.env.example`. The estate stack in
   `jad0083/stacks` is the same service pinned by digest, with OpenBao secrets mapped onto the same variable
   names. Nothing in this repo refers to Komodo or OpenBao.

2. **One container; the dashboard supervises the pilot** (approach A). The container's main process is
   `pilot view` under `tini`. A run is its child process. There is no process supervisor and no Docker
   socket.

3. **The image** (`Dockerfile`, three stages):
   - `rust` (rust:1-slim-bookworm) builds `game-controller` in release mode (the controller crate only).
   - `py` (python:3.13-slim-bookworm) installs the app and its runtime dependencies from `pyproject.toml` into
     `/opt/venv`, without dev extras.
   - `runtime` (python:3.13-slim-bookworm) holds:
     - `/opt/venv`, `/app/bin/game-controller`, `/app/corpora` (read-only) and `/app/src`;
     - `tini` and the Litestream binary (a pinned version, checked by SHA-256);
     - `/app/entrypoint.sh`.
   - The package runs from `/app/src` (`PYTHONPATH`, not installed into the venv), so the code's own root
     (`config.REPO`) is `/app`. Any default still derived from it points inside the image, and the plan checks
     that nothing at run time needs a checkout there (no `.git`, no `scripts/`).
   - It runs as uid and gid 10010 and sets `PILOT_DATA_DIR=/data`, `PILOT_CORPORA_DIR=/app/corpora` and
     `PILOT_CONTROLLER_BIN=/app/bin/game-controller`.
   - It exposes 8780; the live pilot's 8790 stays on the container's loopback.
   - A `HEALTHCHECK` calls an unauthenticated `GET /healthz` (added to the dashboard: 200 and `ok`, no data).

4. **The entrypoint** (`entrypoint.sh`):
   - It checks that `/data` exists and is writable by the running uid. If not, it prints one line naming the
     directory, the uid and the fix (`chown 10010:10010`) and exits 1.
   - If `LITESTREAM_REPLICA_URL` is set:
     - It restores `pilot.db` from the replica only when `/data/pilot.db` does not exist (`-if-replica-exists`),
       never over existing data.
     - It then `exec`s `litestream replicate -exec "pilot view --port 8780"` with a config generated from the
       environment (one database, `/data/pilot.db`, one replica).
   - Otherwise it `exec`s `pilot view --port 8780`.
   - `auth.sqlite` is not replicated: losing it means signing devices in again, which the sign-in link covers.

5. **The supervisor** (`src/pilot/supervisor.py`, owned by the dashboard; it replaces `systemctl` in
   `api_run`).
   - **Start** (`start(by)`):
     - It refuses when a run is live: a child it owns, or a run answering on the live port.
     - It spawns `python -m pilot run` with the dashboard's environment.
     - It copies the child's output, line by line with a `pilot: ` prefix, to its own stdout (the container
       log).
     - It writes the `settings` row `supervisor` = `{"live": true, "since": t, "by": who}`.
   - **Stop** (a human stop):
     - The dashboard's existing stop control goes to the live pilot first; the supervisor then sends SIGTERM,
       and after the existing 20 s stop grace, SIGKILL.
     - It writes `live: false`.
   - **The child exits by itself** (a run that ended, a crash, the end of a campaign):
     - It records the exit code and the last 20 log lines and writes `live: false`.
     - It emits `run_exit` into the store's events, which the Now page shows.
     - It never restarts a failed run by itself.
   - **The container stops** (SIGTERM to the dashboard): the supervisor stops the child the same way but leaves
     `live: true`. The compose sets `stop_grace_period: 40s`.
   - **Resume**: when the dashboard starts and finds `live: true`, it starts a run with the saved prefs after
     10 s. Resume is tried once per dashboard start. `PILOT_RESUME=0` turns it off. The resumed run has a new
     run id and the same campaign (the governor reads the campaign from the game).

6. **One code path in both installs.** A checkout runs one unit, `game-pilot-view.service`, whose dashboard
   supervises the pilot. `deploy/game-pilot.service` is removed.
   - `scripts/deploy-pilot.sh` and `scripts/pilot-affected.py` are retired, with their tests and AGENTS.md
     text: a redeploy now costs one clean stop and a resume, and an image replaces everything at once.
   - Deploying becomes: merge the Renovate PR (or bump the pin), Komodo redeploys, the run resumes.

7. **Configuration by environment.**
   - `.env.example` lists every variable the app reads, grouped and with one line each:
     - **required**: one model key (`GEMINI_API_KEY`, or another provider's), `GAME_AGENT_URL`,
       `GAME_AGENT_TOKEN`;
     - **common**:
       - `GAME_RESOLUTION`, `PILOT_PUBLIC_URL`, `PILOT_TRUSTED_PROXIES`, `PILOT_PROXY_SECRET`;
       - `PILOT_DASHBOARD_KEY` (otherwise generated into `/data/secrets/`);
       - `PILOT_RESUME`, `PILOT_NOTIFY_URL`;
     - **optional**: `LITESTREAM_REPLICA_URL`, `LITESTREAM_ACCESS_KEY_ID`, `LITESTREAM_SECRET_ACCESS_KEY`,
       `PILOT_EXPORT_DIR`, and the model and governor tunables.
   - The path variables are set by the image and documented as such.
   - The dashboard starts without the required variables, so history and sign-in work on a fresh install. A
     run is refused while one is missing, with its name on the dashboard ("set GAME_AGENT_URL to start a
     run"), and the PC status line says the agent is not configured.

8. **The portable compose** (this repo):

   ```yaml
   services:
     game-pilot:
       image: ghcr.io/jad0083/game-pilot:${GAME_PILOT_VERSION:-latest}
       ports: ["${GAME_PILOT_PORT:-8780}:8780"]
       env_file: .env
       volumes: ["${GAME_PILOT_DATA:-./data}:/data"]
       stop_grace_period: 40s
       restart: unless-stopped
   ```

   The first sign-in is `docker compose exec game-pilot pilot dashboard-link`.

9. **Behind a proxy in a container.**
   - Docker's bridge network keeps the client address for published ports, so `PILOT_TRUSTED_PROXIES` works
     unchanged.
   - The dashboard's allowed Host names come from `PILOT_PUBLIC_URL` and `PILOT_DASHBOARD_HOSTS`, plus
     loopback. The container's own hostname is not trusted.

10. **CI builds the image** (`.github/workflows/image.yml`, after the subtitler precedent).
    - It runs on a push to `main` that changes code; docs-only pushes are ignored.
    - **Preflight**: `scripts/ci.sh` (Rust and Python; the browser tests when Playwright's Chromium installs).
    - **Build and smoke**:
      - start the image on an empty `/data` and wait for healthy;
      - check that `/` redirects to sign-in and that `/healthz` answers;
      - check that a forwarded request is accepted only from the trusted proxy;
      - run `pilot data check` on a fixture.
    - **Push** to `ghcr.io/jad0083/game-pilot` as:
      - `:<pyproject version>` (never moved once published);
      - `:sha-<short>`;
      - `:latest`.
    - amd64 only. After the first push, the package's visibility is checked to be public.

11. **The estate stack** (`jad0083/stacks/apps/games/game-pilot/`):
    - `compose.yaml`: the same service, with these differences:
      - the image pinned `:<version>@sha256:<digest>`;
      - `user: "10010:10010"` and `container_name: game-pilot`;
      - `/mnt/dockervol/game-pilot/data:/data`;
      - each secret as `KEY=${X:?rendered by Periphery from OpenBao}` instead of `env_file`.
    - `komodo.toml`:
      - `server = "deb-dock1"`, the pinned lane, `deploy = true`;
      - secrets `GAME_PILOT_GEMINI_API_KEY`, `GAME_PILOT_AGENT_TOKEN` and `GAME_PILOT_PROXY_SECRET` from
        `secret/apps/game-pilot/{GEMINI_API_KEY,AGENT_TOKEN,PROXY_SECRET}`;
      - plain lines for `GAME_AGENT_URL`, `GAME_RESOLUTION`, `PILOT_PUBLIC_URL` and `PILOT_TRUSTED_PROXIES=192.168.1.50`.
    - deb-dock1's Periphery template gets the three secret lines.
    - A DOCKER-USER guard on deb-dock1 lets only NPM and the host reach 8780 (with a test in the komodo repo,
      as for voicestudio).

12. **Litestream when configured.** Replication is configured only by environment; with no replica URL nothing
    runs. The estate leaves it off (non-goal). The docs say how to switch it on, and how to restore: start
    the container on an empty `/data`.

---

## Rollout (the live install to deb-dock1)

1. **Release.** CI builds and smoke-tests the image; the digest of `ghcr.io/jad0083/game-pilot:<version>` is
   recorded. The package is public.
2. **Prepare deb-dock1.**
   - `install -d -o 10010 -g 10010 -m 0700 /mnt/dockervol/game-pilot/data`.
   - OpenBao (needs an admin token from `mint-admin-token.sh`, which the user runs):
     - write `GEMINI_API_KEY` and `AGENT_TOKEN` at `secret/apps/game-pilot/` (`PROXY_SECRET` exists);
     - grant deb-dock1's AppRole;
     - add the three template lines;
     - restart `openbao-agent` and Periphery.
   - Add the guard.
   - Push the stack with `deploy = false`.
3. **Freeze and copy.**
   - Stop `game-pilot-view.service` on deb-mini2 (the pilot is stopped with it).
   - Copy `pilot.db` and `auth.sqlite` with SQLite's backup API (consistent copies), then `frames/`, `learned/`
     and `secrets/`, keeping their modes, to deb-dock1's data directory, owned by 10010.
   - Compare: the table row counts of both copies are equal, and `PRAGMA integrity_check` is `ok`.
4. **Start on deb-dock1.** Set `deploy = true` and add the stack's path to the `Stacks` sync (through the
   Komodo API if it allows; otherwise the user's one UI step). Then check:
   - the container is healthy and `/` redirects to sign-in;
   - the user's devices still sign in;
   - the history lists all runs;
   - `/api/pc` reaches mini-rig2.
5. **Switch the route.** Repoint NPM host 54 to `192.168.1.53:8780` (the user's NPM credentials, used
   transiently). Check `gamepilot.saczone.com` through Authelia and that the proxy secret is enforced.
6. **Live check.** Start a short run from the dashboard. Redeploy the stack once mid-run: the run stops cleanly
   and resumes by itself.
7. **Retire deb-mini2's install.**
   - Disable `game-pilot-view.service` and remove `game-pilot.service`.
   - Drop 8780 from `npm-only-guard.sh` (with its test).
   - Keep deb-mini2's `runs/` unchanged as the rollback copy until the user approves pruning it.
8. **Mark it done.** `plan.md` Portability 2 is ticked after step 6 passes.

**Rollback** (before step 7): repoint NPM host 54 to deb-mini2 and start its viewer. Data written on deb-dock1
after the move is copied back the same way if it matters.

---

## Errors

- **`/data` is not writable**: one line from the entrypoint with the directory, the uid and the fix.
- **A Litestream replica that cannot be reached at start**: Litestream's own error, and the container exits.
  Restore never writes over existing data.
- **A run that fails to start** (a bad key, the agent unreachable): the Now page shows the child's last lines
  and exit code. Resume is tried once per dashboard start.
- **A missing required variable**: in the estate, compose's `:?` stops the deploy first. Elsewhere the
  dashboard runs, and Start names the missing variable instead of starting a run.

## Tests

- **`tests/test_supervisor.py`** (a fake child script):
  - start, and a second start refused;
  - a human stop (`live: false`, no resume);
  - a crash (`run_exit` with the code and lines);
  - a container stop (`live: true`), then resume on the next start;
  - `PILOT_RESUME=0`;
  - SIGTERM to a real dashboard subprocess.
- **`tests/test_entrypoint.py`** (the script with `litestream` and `pilot` stubbed on PATH):
  - no replica;
  - a replica with an empty `/data` (restore, then replicate);
  - a replica with an existing database (no restore);
  - an unwritable `/data`.
- **`tests/test_env_example.py`**: every variable the code reads (scanned from `src/pilot`) is in
  `.env.example` or listed as internal or image-set, and the portable `compose.yaml` parses and uses only
  documented variables.
- **`tests/test_dashboard_*`**:
  - `/healthz` is public and says nothing;
  - Start with a required variable missing is refused and names it;
  - the allowed Host names come from the environment, not the hostname;
  - `api_run` goes through the supervisor.
- **The CI smoke test** (ruling 10).
- **The estate repos' own suites**, run before pushing: the stack rules in `jad0083/stacks` and the guard tests
  in `jad0083/komodo`.
- **Retired with their scripts**: `tests/test_deploy_pilot.py` and the `pilot-affected.py` tests.

## Docs

- **README**:
  - Run it with Docker: the portable compose, `.env`, the sign-in link.
  - Run it from a checkout: one `pilot view` unit, for development.
- **docs/pilot.md**: the supervisor and resume; container settings; Litestream on and off, and restore;
  upgrading (pull the image; the run resumes).
- **AGENTS.md**: §1's Dashboard row (deb-dock1, the container, `docker exec game-pilot pilot dashboard-link`)
  and §8's deploy text replace `deploy-pilot.sh`.
- **ARCHITECTURE.md**: the image and the supervisor.

## Risks

- **A redeploy interrupts a decision.** The stop grace (20 s) ends a model call. The run resumes and decides
  again from the game's state, as after any stop today.
- **Port 8780 stays guarded on two hosts** during the move. The deb-mini2 rule is removed only in step 7.
- **A public package carries the corpora and the game knowledge.** These are in the public repository
  already; the image adds no secret.
- **No backup in the estate** until a Litestream replica is configured (the user's choice). deb-mini2's
  `runs/` copy covers the move itself.
