# Data platform: one SQLite store in a data directory, code read-only

Date: 2026-10-05. Status: design approved in conversation; rulings below are numbered from 1.
Base: `main` at f78aa39.

This is sub-project 1 of the portability programme. The programme makes the harness run anywhere: in
the user's estate (a Komodo stack), on other people's machines, and on one Docker Desktop PC. Its four
sub-projects ship in order:

1. **Data platform** (this design): one SQLite store in a writable data directory; code and base
   corpora read-only; learned knowledge, journals, traces and settings in the store; git as an export.
2. **Appliance image and estate stack**: one multi-stage image (Python app + `game-controller`), the
   dashboard supervising one pilot run as a child process instead of `systemctl`, Litestream wrapping
   the app when configured, configuration by environment, a Komodo stack with OpenBao secrets.
3. **Agent release and pairing**: a versioned Windows installer and a pairing code; PCs registered in the
   store instead of `GAME_AGENT_URL`, `.agent_token*` and `GAME_RESOLUTION`.
4. **Public distribution**: CI-built multi-arch images on a registry, releases, a `compose.yaml` and `.env`
   template, setup docs for a server and for one PC, upgrades through schema migrations.

The user chose the data platform (SQLite with Litestream) after the measurements in "Evidence".

---

## Evidence

- **E1. Size.** After ten days: `runs/telemetry.sqlite` 62 MB (15,537 events, 1,190 decisions, 5,549
  metrics rows); learned files 0.8 MB across games; `runs/` 232 MB, of which about 214 MB is per-run
  frames and 18 MB decision traces.
- **E2. Write rate.** A Civ VI run wrote 623 events in 86 minutes: 7.3 a minute, 339 KiB.
- **E3. Speed on deb-mini2.** SQLite in WAL mode: 0.02 ms per single-row commit (about 60,000 a second);
  a 40 KiB blob commit 0.07 ms. Dashboard queries on the 62 MB file: 3.5-10 ms. A decision spends about
  36 s in model calls.
- **E4. Couplings** (state map, 2026-10-05):
  - Every path derives from the repo location (`config.py:10`).
  - The pilot creates `corpora/<game>/learned/` at start (`learning.py:75`).
  - The Rust controller merges `learned/manifest.toml` and loads its templates and `learned/*.md` from
    the corpus directory (`corpus.rs:232-254`, `autopilot.rs:74`, `corpus.rs:476`).
  - The GalCiv pilot commits learnings through `git` and `scripts/ci-commit.sh` (`controller.py:242-262`).
    Stellaris and Civ VI do not commit.
  - Frames are never pruned.
  - The dashboard finds the live pilot through `runs/<run>/status.json` and lists runs from directories.

## Goals

1. A pilot and dashboard that run with the code and base corpora read-only and every write in one data
   directory.
2. One database file holding all structured state, safe for Litestream (WAL, nothing outside the store
   writing to it).
3. No git, CI or Rust toolchain needed at run time.
4. Today's history and learned knowledge carried over without loss.

## Non-goals

These belong to sub-projects 2-4:
- the container image;
- Litestream configuration;
- process supervision;
- agent pairing and the PC registry;
- publishing.

Also out of scope:
- **Postgres.** The store module keeps it possible later.
- **Moving the hand-written campaign journals.** These are `games/civ6-*/journal.md` and similar; they
  are documentation and stay in git.

---

## Rulings

### Layout

1. **Two locations.** Code: the Python app, the controller binary, and the base corpora (`manifest.toml`,
   `data/`, `docs/`, `templates/`, `lua/`, `res/`, the `.toml` files). Data: one writable directory.
   Settings, with defaults that keep a development checkout working:
   - `PILOT_DATA_DIR` (default `<repo>/runs`);
   - `PILOT_CORPORA_DIR` (default `<repo>/corpora`);
   - `PILOT_CONTROLLER_BIN` (default `<repo>/target/release/game-controller`).
2. **The data directory:**

   | Path | Holds |
   |---|---|
   | `pilot.db` | everything structured (ruling 4), SQLite in WAL mode |
   | `auth.sqlite` | sign-in devices and sessions, as today (separate file, 0600) |
   | `frames/<run_id>/NNNNN.jpg`, `frames/<run_id>/latest.jpg` | screenshots as files (ruling 9) |
   | `learned/<game>/` | generated from the store for the controller (ruling 7) |
   | `secrets/dashboard.key`, `secrets/dashboard.carryover` | secrets as files (0600), never in a database |

3. **Nothing writes into the corpora directory at run time.** `LearnedStore` no longer creates
   `learned/`; the base corpora may be read-only.

### The store

4. **`pilot.db` tables.** The telemetry tables move unchanged: `campaigns`, `runs`, `events`, `decisions`,
   `metrics`, `plans`, `strategies`. New tables:
   - `meta(key, value)`: `schema_version`.
   - `traces(run_id, episode, data)`: the JSON that `traces/NNNN.json` held. Primary key
     `(run_id, episode)`.
   - `learned_notes(game, kind, text, why, model, run_id, t)`: kind `rule` or `control`, in the order
     added.
   - `learned_screens(game, name, description, roi, threshold, auto_dismiss, action, png, learned_by,
     run_id, t, disabled_reason)`: `png` is a blob, `action` is JSON (`dismiss_click`/`dismiss_key`).
     Primary key `(game, name)`.
   - `episodes(game, t, date, situation, decision, outcome, model, run_id)`.
   - `ledger(game, t, kind, data)`: the provenance ledger, `data` JSON.
   - `journal(campaign_id, game, t, date, text)`: the pilot's journal lines.
   - `settings(key, value, changed_by, t)`: `key` `prefs` holds today's `pilot-settings.json`.
   - `model_usage(day, model, count)`: today's `model-usage.json`, 7 days kept.
   - `standing_orders(campaign_id, position, text)`.
   - `live(run_id, port, pid, started, updated)`: replaces `status.json`.
5. **One module, the same interfaces.** `src/pilot/store.py` owns `pilot.db`:
   - one connection per thread;
   - WAL mode, `synchronous=NORMAL`, a 5 s busy timeout;
   - forward migrations keyed by `schema_version`, run at open.

   The following keep their public interfaces and change only their storage, so their callers do not
   change:
   - `Telemetry`, `LearnedStore`, `Journal`;
   - `EventLog.save_trace` and `EventLog.frame`;
   - `models.load_prefs`/`save_prefs`;
   - `ModelHealth`'s usage counts;
   - the governors' standing orders.

   No other code opens `pilot.db`.
6. **`events.jsonl` stops.** The `events` table holds every event. `telemetry.rebuild` and the `rebuild`
   CLI command go; the import (ruling 11) reads old JSONL once.

### The controller and the learned files

7. **A generated learned directory.** After the store opens, and after every change to a game's learned
   screens or notes, the pilot writes `<data>/learned/<game>/` from the store:
   - `manifest.toml` (the same `[screens.*]` keys as today; template paths relative to this directory,
     `templates/<name>.png`);
   - `templates/<name>.png`;
   - `strategy.md`, `controls.md` (the same markdown as today).

   It writes a temporary directory and renames it into place, so a controller never reads a half-written
   one. The store stays the only source of truth.
8. **`game-controller --learned <dir>`.** The controller reads the learned overlay, its templates and its
   `*.md` notes from `<dir>`, resolving overlay template paths against `<dir>`. Without the option it
   reads `<corpus>/learned` and resolves paths against the corpus directory, as today (CLI and
   development use). The pilot always passes `<data>/learned/<game>`.

### Frames, git and export

9. **Frame retention.** After each frame is saved, frames of that run beyond the newest
   `PILOT_FRAMES_KEEP` (default 200) are deleted. A frame named by an open needs-attention card is kept
   until the card closes. `latest.jpg` is always kept.
10. **No git at run time; export instead.** `Pilot._commit`, its `git`/`ci-commit.sh` calls and
    `PILOT_COMMIT` are removed.
    - `pilot export --to <dir> [--game <g>] [--campaign <id>]` writes `<game>/learned/` (ruling 7's
      files) and `journals/<campaign>.md` (the pilot's journal lines as markdown).
    - With `PILOT_EXPORT_DIR` set, every run exports there when it ends.
    - Committing an export is outside the pilot.

### Migration

11. **`pilot data import --from <root>`** copies an old install into the data directory. It is
    idempotent: rows already present are skipped by key. The keys are a table's primary key where it has one, `(run_id, t, kind)` for events, `(game, kind, text)` for learned notes, `(game, t, situation)` for episodes, and `(campaign_id, t, text)` for journal lines.
    - The telemetry tables (through `ATTACH`).
    - `runs/*/traces/*.json`.
    - `runs/*/events.jsonl` events missing from the table.
    - `corpora/<game>/learned/{strategy.md,controls.md,manifest.toml,templates/*,episodes.jsonl,ledger.jsonl}`
      for every game.
    - The `## Pilot log` lines of `games/*/journal.md`, under the campaign the run recorded.
    - `runs/pilot-settings.json`, `runs/model-usage.json`, `runs/orders/*.json`.
    - `runs/dashboard.key` and `runs/dashboard.carryover`, into `secrets/`.
    - `runs/*/frames` and `latest.jpg`, copied.

    The source is not changed. `--prune-source` deletes the imported old files, and only after a passing
    check.
12. **`pilot data check --from <root>`** compares the source and the store: counts per table, traces,
    learned items, journal lines and frames. Any difference is listed and returns non-zero.

### Rollout

13. **deb-mini2.** In order:
    1. stop the pilot and the viewer;
    2. `pilot data import --from <repo>`;
    3. `pilot data check`;
    4. merge and `scripts/deploy-pilot.sh`;
    5. start the viewer.

    The old `runs/` and `corpora/*/learned` stay until `--prune-source`. The systemd units keep working:
    with `PILOT_DATA_DIR` unset, the data directory is `<repo>/runs`, which now holds `pilot.db`.
14. **Docs.** Update `docs/pilot.md` (the data directory, export, import, retention), `README.md`
    (settings), `ARCHITECTURE.md` (`store.py`), `AGENTS.md` (§8: learned knowledge lives in the store and
    reaches the repo through `pilot export`), and `plan.md`/`issues.md`.

## Tests

- **Interface parity:** the existing tests of `LearnedStore`, `Journal`, `Telemetry`, prefs, guard usage
  and standing orders pass unchanged against the store.
- **Store:**
  - schema creation;
  - a migration from an older `schema_version`;
  - two threads writing while a third reads;
  - WAL mode and busy timeout in force.
- **Generated learned directory:**
  - for the same rules and screens it matches today's files;
  - it is replaced atomically;
  - a Rust test loads learned screens and templates through `--learned`;
  - without the option, today's behaviour holds.
- **Import:**
  - a fixture of today's layout imports completely;
  - a second import changes nothing;
  - `check` reports a missing trace, a missing frame and a missing learned screen.
- **Read-only code:** a pilot run against a read-only copy of `corpora/` writes nothing there.
- **Frames:** retention keeps the newest N and the frame of an open attention card.
- **Export:** writes the expected files.
- **Dashboard:** the existing UI tests pass on the store.

## Success criteria

- Every past campaign shows on the dashboard from `pilot.db`.
- After a live Civ VI run, `git status` shows no learned or journal changes in the repo.
- Learned rules and screens survive a restart.
- The full test suite and the UI suite pass.

## Risks

- **Two writers on one file.** The dashboard viewer and the pilot are separate processes on the same
  `pilot.db`. WAL allows one writer at a time with readers in parallel. The viewer writes only settings
  and standing orders, rarely, so the 5 s busy timeout covers contention.
- **Copying frames doubles their disk use** until `--prune-source` (214 MB today).
- **The generated learned directory can lag the store** by one write if the pilot dies between the
  commit and the rename. The next start rebuilds it from the store.
