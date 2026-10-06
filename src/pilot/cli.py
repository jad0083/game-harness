"""`python -m pilot` — run the autonomous LLM pilot, or check the setup.

    python -m pilot check                     # key, model, agent, corpus
    python -m pilot run [--model M] [--port P] [--turns N] [--episodes K]
    python -m pilot run --game stellaris [--speed fast|fastest|...] [--months N]
    python -m pilot run --game civ6 [--decide-turns N]  # the game's AI plays N turns between decisions
    python -m pilot view [--port P] [--host H]   # the dashboard over recorded runs (and the live one)
    python -m pilot prefs --get KEY            # one saved dashboard setting: the bare value, or JSON
    python -m pilot control ACTION [--text T] [--index N] [--port P]   # pause|resume|stop|instruct|… as a script
    python -m pilot dashboard-link [--port P] [--no-qr] [--wait]   # sign a browser in: a one-time link,
                                              # three words and a QR code (never the key)
    python -m pilot dashboard-devices [list | rename ID NAME | revoke ID | revoke-all [--except ID] |
                                       log [-n N] | unlock [--port P]]
    python -m pilot dashboard-key --rotate [--keep all|none|ID,…] [--force]   # a new service key; carried-over
                                              # devices are kept only if named
    python -m pilot dashboard-token create --name N --scope read|control [--expires 90d] | list | revoke ID
    python -m pilot data import --from ROOT [--prune-source]   # copy an install from before the data
                                              # platform into the data directory (PILOT_DATA_DIR)
    python -m pilot data check --from ROOT     # what the data directory lacks of it (exit 1 when anything)
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import threading
import time
from pathlib import Path

from .config import REPO, Settings


def uses_claude_code(s: Settings) -> bool:
    """Whether any configured model (main, pool, fallback or a role) is a claude-code:* model."""
    names = [s.model, s.fallback_model or ""] + [m["model"] for m in s.pool()]
    names += [m["model"] for cfg in (s.roles or {}).values() for m in (cfg or {}).get("models", [])]
    return any(n.startswith("claude-code:") for n in names)


def check_claude_cli(s: Settings) -> bool:
    """Report the claude CLI (the claude-code provider); missing is an error only when a model uses it."""
    from .claude_code import find_claude
    exe, needed = find_claude(), uses_claude_code(s)
    if exe:
        print(f"  ✓ claude CLI {exe} (claude-code:* models use the Claude subscription)")
        return True
    print(f"  {'✗' if needed else '-'} claude CLI not found on PATH or in ~/.local/bin"
          f"{' but a claude-code:* model is configured' if needed else ' (only needed for claude-code:* models)'}")
    return not needed


def check(s: Settings) -> int:
    ok = True
    print(f"model: {s.model}  (coords: {s.coord_space}, thinking: {s.thinking}, images kept: {s.images_in_context})")
    if not s.controller_bin.exists():
        print("  ✗ controller not built: cargo build --release -p game-controller"); ok = False
    if s.provider.startswith("google"):
        key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        if not key:
            print("  ✗ no GEMINI_API_KEY / GOOGLE_API_KEY (put it in .env)"); ok = False
        else:
            try:
                from google import genai
                client = genai.Client(api_key=key)
                names = {m.name.split("/")[-1] for m in client.models.list()}
                name = s.model.split(":", 1)[1]
                print(f"  {'✓' if name in names else '✗'} model {name} {'available' if name in names else 'NOT available for this key'}")
                ok &= name in names
            except Exception as e:  # noqa: BLE001
                print(f"  ✗ API check failed: {e}"); ok = False
    ok &= check_claude_cli(s)
    try:
        import urllib.request
        token = os.environ.get("GAME_AGENT_TOKEN") or (REPO / ".agent_token").read_text().strip()
        req = urllib.request.Request(s.agent_url + "/health", headers={"Authorization": f"Bearer {token}"})
        h = json.load(urllib.request.urlopen(req, timeout=5))
        print(f"  ✓ agent {s.agent_url}: screen {h['screen']}, foreground {h['foreground']!r}")
    except Exception as e:  # noqa: BLE001
        print(f"  ✗ agent {s.agent_url}: {e}"); ok = False
    for f in ("manifest.toml", "pilot.md", "strategy.md"):
        p = s.corpus_dir / f
        print(f"  {'✓' if p.exists() else '✗'} corpus {p.relative_to(REPO)}"); ok &= p.exists()
    print("ready" if ok else "not ready")
    return 0 if ok else 1


def run(s: Settings, episodes: int | None) -> int:
    from .controller import Pilot
    from .dashboard import serve_in_background
    from .events import EventLog
    from .game import McpGame

    run_id = time.strftime("%Y%m%d-%H%M%S")
    from .store import open_store
    log = EventLog(s.runs_dir, run_id, s.model, telemetry=open_store(s.runs_dir), frames_keep=s.frames_keep)
    if s.game == "civ6":
        from .civ6 import ControllerCiv6
        game = ControllerCiv6(s.controller_bin, s.corpus_dir, s.agent_url, REPO, learned=s.learned_dir)
    else:
        game = McpGame(s.controller_bin, s.corpus_dir, s.agent_url, REPO, title=s.window_title,
                      learned=s.learned_dir)
    if s.game == "civ6":
        from .civ6_governor import Civ6Governor
        pilot = Civ6Governor(s, game, log)
    elif s.game == "stellaris":
        from .governor import Governor
        pilot = Governor(s, game, log)
    else:
        pilot = Pilot(s, game, log)
    log.state.info["port"] = s.dashboard_port      # lets the always-on viewer find this run

    def list_models() -> None:
        from .models import available_models
        log.state.info["models"] = available_models(s)

    threading.Thread(target=list_models, daemon=True, name="models").start()
    serve_in_background(pilot, s.live_host, s.dashboard_port)
    from .notify import start_notifier
    start_notifier(log)          # an ntfy notice when a stop lasts (PILOT_NOTIFY_URL; off by default)
    print(f"pilot {run_id}: model {s.model}; live dashboard on {s.live_host}:{s.dashboard_port} (reached through "
          f"the viewer); store {s.db_path}", flush=True)

    done = threading.Event()

    def on_signal(*_):
        if pilot.control.stopping:              # second signal: leave now
            os._exit(1)
        print(f"stopping after the current step (at most {STOP_GRACE_S:.0f} s)...", flush=True)
        pilot.stop()
        arm_stop_grace(done, STOP_GRACE_S, on_force=lambda: log.emit("run_end", forced=True,
                       reason="a step (e.g. a model call) did not finish after the stop request"))

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    try:
        if s.game in ("stellaris", "civ6"):
            pilot.run(max_decisions=episodes)
        else:
            pilot.run(max_episodes=episodes)
    finally:
        done.set()
        game.close()
        _export_at_end(log, s)
        log.close()
    return 0


def _export_at_end(log, s: Settings) -> None:
    """Write the learned files and journals to PILOT_EXPORT_DIR when set; a failure never fails the run."""
    if not s.export_dir:
        return
    from .export import export
    try:
        export(log.store, s.export_dir, game=s.game)
    except Exception as e:  # noqa: BLE001 - a failed export never fails the run
        log.emit("briefing_error", error=f"export failed: {e}"[:300])


STOP_GRACE_S = 20.0


def arm_stop_grace(done: threading.Event, grace_s: float, on_force=None, force_exit=os._exit) -> threading.Thread:
    """After a stop request, give the loop `grace_s` to finish its step, then exit anyway.

    A model call cannot be interrupted, and one that hangs (a slow model, retries) kept the service
    from stopping until systemd killed it. The governor pauses the game before every decision,
    so leaving mid-call is safe; the unfinished decision is dropped."""
    def watch() -> None:
        if not done.wait(grace_s):
            if on_force is not None:
                try:
                    on_force()
                except Exception:  # noqa: BLE001, S110 - the exit matters more than the log line
                    pass
            force_exit(0)

    t = threading.Thread(target=watch, daemon=True, name="stop-grace")
    t.start()
    return t


def game_for_roles(a, prefs: dict) -> str:
    return a.game or prefs.get("game") or "stellaris"


def view(s: Settings, port: int, host: str | None = None) -> int:
    import logging

    from aiohttp import web

    from . import auth
    from .dashboard import link_host, make_app
    from .store import open_store
    app = make_app(None, s.runs_dir, open_store(s.runs_dir))       # the key never reaches this line or the log
    host = host or s.view_host
    print(f"dashboard on http://{link_host(host)}:{port}/ (to sign in a browser: "
          "python -m pilot dashboard-link)", flush=True)
    if not auth.qr_available():             # said loudly: the Add sheet then has no QR code for a phone
        msg = (f"QR codes are off: segno is not installed in {sys.executable} (fix: {Path(sys.executable).parent}/pip "
               "install segno, then restart); Add a device shows the link and the words only")
        print(msg, flush=True)
        logging.getLogger("pilot.view").warning(msg)
    web.run_app(app, host=host, port=port, print=None, **auth.RUNNER_KWARGS)
    return 0


WAIT_POLL_S = 1.0


def auth_store(s: Settings):
    """The sign-in store (the viewer's), opened directly: works with both services down."""
    from .auth import AuthStore
    return AuthStore(Path(os.environ.get("PILOT_AUTH_DB") or s.runs_dir / "auth.sqlite"))


def dashboard_link(s: Settings, port: int, qr: bool = True, wait: bool = False) -> int:
    """A one-time sign-in (10 minutes): a link with the code in its fragment, three words to type and
    a QR code. Safe to print and to run by an agent: whoever uses it shows up in Devices; never K."""
    from .auth import lan_address, qr_text
    store = auth_store(s)
    g = store.create_grant("cli", words=True)
    base = os.environ.get("PILOT_PUBLIC_URL", "").strip().rstrip("/") or f"http://{lan_address()}:{port}"
    url = f"{base}/pair#c={g['link']}"
    print("Sign in a browser (works once, for 10 minutes):")
    print(f"  {url}")
    print(f"or open {base}/ and type: {g['words']}")
    if qr:
        text = qr_text(url)
        print(text if text else "(no QR code: segno is not installed; .venv/bin/pip install segno)")
    sys.stdout.flush()
    if not wait:
        return 0
    while True:
        row = store.grant(g["id"])
        if row["state"] == "used":
            dev = store.device(row["device_id"])
            print(f"Signed in: {dev['name'] if dev else 'a browser'}", flush=True)
            return 0
        if row["state"] != "waiting" or time.time() > row["expires_at"]:
            print("The code was not used in time; make a new one." if row["state"] != "conflict"
                  else "The code was used twice; that sign-in was signed out.", flush=True)
            return 1
        time.sleep(WAIT_POLL_S)


def control(s: Settings, a) -> int:
    """One dashboard control from a script on the controller: JSON over loopback to the viewer with
    the service key (read on each call, so a rotation never breaks a loop); the reply is printed, and
    any refusal exits non-zero with the server's error (the old `curl -s` pattern hid a 401)."""
    import urllib.error
    import urllib.parse
    import urllib.request

    from .auth import DEVICE_NAME_HEADER, dashboard_key
    body: dict = {"action": a.action}
    if a.text is not None:
        body["text"] = a.text
    if a.index is not None:
        body["index"] = a.index
    req = urllib.request.Request(f"http://127.0.0.1:{a.port}/control", data=json.dumps(body).encode(), method="POST",
                                 headers={"X-Pilot-Key": dashboard_key(s.runs_dir), "Content-Type": "application/json",
                                          DEVICE_NAME_HEADER: urllib.parse.quote("the controller")})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print(r.read().decode(errors="replace"))
            return 0
    except urllib.error.HTTPError as e:
        print(f"refused: {e.code} {e.read().decode(errors='replace')[:500]}")
        return 1
    except (urllib.error.URLError, OSError) as e:
        print(f"no dashboard viewer answers on 127.0.0.1:{a.port}: {e}")
        return 1


def _interactive() -> bool:
    return sys.stdin.isatty()


def _when(t: float | None) -> str:
    return time.strftime("%d %b %H:%M", time.localtime(t)) if t else "never"


def live_pilots(s: Settings, key: str) -> list[tuple[str, int | None]]:
    """(run id, info.auth_version or None) of each live pilot that answers on loopback."""
    import urllib.error
    import urllib.request

    from .dashboard import list_runs, live_status
    from .store import open_store
    out = []
    for run in list_runs(open_store(s.runs_dir)):
        st = run.get("_status") or {}
        port = (st.get("info") or {}).get("port")
        if not port or not live_status(st.get("status")):
            continue
        req = urllib.request.Request(f"http://127.0.0.1:{int(port)}/status", headers={"X-Pilot-Key": key})
        try:
            with urllib.request.urlopen(req, timeout=3) as r:
                body = json.load(r)
        except urllib.error.HTTPError:
            out.append((run["id"], None))               # it refuses the key it should share: treat as old
            continue
        except (urllib.error.URLError, OSError, ValueError):
            continue                                    # nothing answers there: not live
        if body.get("run_id") == run["id"]:
            out.append((run["id"], (body.get("info") or {}).get("auth_version")))
    return out


def dashboard_key_cmd(s: Settings, a) -> int:
    """Rotate the service key: a new <data>/secrets/dashboard.key (0600, atomic) that both new-code processes
    read within 2 s; the carried-over devices (the old key cookie) are kept only if named, and the
    carry-over ends. Other browsers and script tokens are untouched. The key is never printed."""
    from .auth import KEY_ENV, KeySource, write_carry_over
    if not a.rotate:
        print("Pass --rotate [--keep all|none|ID,...] to replace the dashboard's service key (it is never printed).")
        return 2
    keys = KeySource(s.runs_dir)
    if keys.from_env:
        print(f"The key comes from {KEY_ENV}: change that variable (in .env or the service files), then restart "
              "both services (game-pilot-view.service and game-pilot.service).")
        return 1
    if not a.force:
        old = [run for run, version in live_pilots(s, keys.get()) if not version or version < 1]
        if old:
            print(f"A live pilot from before the change is running ({', '.join(old)}): it reads the key only at "
                  "startup; rotate after it restarts, or pass --force (its controls then fail until it restarts).")
            return 1
    store = auth_store(s)
    legacy, parent = store.legacy_family()
    if legacy:
        print("Carried over from the old key cookie, and the browsers added from those (kept only if you name "
              "them or the browser that added them):")
        for d in legacy:
            depth, up = 0, parent.get(d["id"])
            while up:
                depth, up = depth + 1, parent.get(up)
            made = f", added from {store.device(parent[d['id']])['name']}" if d["id"] in parent else ""
            print(f"  {'  ' * depth}{d['id']}  {d['name']}{made}, first from {d['created_ip'] or 'unknown'}, last used "
                  f"{_when(d['last_seen_at'])}{' from ' + d['last_ip'] if d['last_ip'] else ''}")
    keep = a.keep
    if keep is None and legacy:
        if not _interactive():
            print("Say which to keep: --keep all, --keep none or --keep ID,ID (nothing changed).")
            return 2
        print("Keep which? (ids separated by commas, all, or none): ", end="", flush=True)
        keep = sys.stdin.readline().strip()
        if not keep:
            print("No answer: nothing changed.")
            return 2
    ids = {d["id"] for d in legacy}
    keep = (keep or "none").strip()
    kept = ids if keep == "all" else set() if keep == "none" else {x.strip() for x in keep.split(",") if x.strip()}
    if kept - ids:
        print(f"Not carried-over devices: {', '.join(sorted(kept - ids))} (nothing changed).")
        return 2
    keys.rotate()
    store.end_carry_over()
    write_carry_over(s.runs_dir, store.meta("legacy_key_fp") or "", 0.0)
    # read again: a browser carried over while the prompt waited is signed out too; what a kept browser
    # added is kept with it
    legacy, parent = store.legacy_family()
    keep_all = set(kept)
    for d in legacy:
        if parent.get(d["id"]) in keep_all:
            keep_all.add(d["id"])
    signed_out = 0
    for d in legacy:
        if d["id"] in keep_all:
            store.audit("legacy_kept", None, d["id"], {"by": "cli"})
        else:
            signed_out += store.revoke(d["id"], "rotate_unkept", by="cli")
    kept = keep_all
    store.audit("key_rotated", None, None, {"by": "cli", "kept": len(kept), "signed_out": signed_out})
    print(f"New service key written to {keys.path} (0600); both services read it within 2 s. The old key no "
          f"longer works anywhere, and old key cookies and ?key= links stop at once. Carried-over devices: kept "
          f"{len(kept)}, signed out {signed_out}. Scripts on the controller read the file again on their next call.")
    return 0


def data_cmd(s: Settings, a) -> int:
    """`data import` copies the install at --from into the data directory and prints what it added and
    skipped; with --prune-source it then checks, and deletes the imported old files only when nothing is
    missing. `data check` prints one difference per line and exits 1 when there is any."""
    from .dataimport import PruneIncomplete, PruneRefused, check, import_install, prune_source
    from .store import open_store
    root = Path(a.source)
    if not root.is_dir():
        print(f"{root} is not a directory")
        return 2
    store = open_store(s.runs_dir)
    if a.action == "check":
        diffs = check(root, store, s.runs_dir)
        print("\n".join(diffs) if diffs else f"nothing missing: {s.runs_dir} holds everything imported from {root}")
        return 1 if diffs else 0
    report = import_install(root, store, s.runs_dir)
    print(f"imported {root} into {s.runs_dir}:")
    for name, n in report.added.items():
        print(f"  {name}: {n} {'copied' if name == 'secrets' else 'added'}")
    print(f"  frames: {report.frames} copied")
    if report.skipped:
        print(f"skipped ({len(report.skipped)}):")
        for item in report.skipped:
            print(f"  {item}")
    if not a.prune_source:
        return 0
    diffs = check(root, store, s.runs_dir)
    if diffs:
        print(f"not pruned: {len(diffs)} item{'s' if len(diffs) != 1 else ''} missing from the data directory:")
        print("\n".join(diffs))
        return 1
    kept: list[str] = []
    failed: list[str] = []
    try:
        deleted = prune_source(root, store, kept)
    except PruneRefused as e:
        print(f"not pruned: {e}")
        return 1
    except PruneIncomplete as e:
        deleted, failed = e.deleted, e.failed
    for p in deleted:
        print(f"deleted {p}")
    if not deleted and not failed:
        print("nothing to delete")
    for item in failed:
        print(f"not deleted {item}")
    for item in kept:
        print(f"kept {item}")
    return 1 if failed else 0


DURATION = {"m": 60, "h": 3600, "d": 86400}


def dashboard_token(s: Settings, a) -> int:
    """Script tokens for other machines: made only here (the browser cannot mint one), shown once,
    read or control scope, sent as a header; listed and revocable in Devices too."""
    import re
    store = auth_store(s)
    if a.action == "create":
        secs = None
        if a.expires and a.expires != "never":
            m = re.fullmatch(r"(\d+)([mhd])", a.expires)
            if not m:
                print("--expires takes a number with m, h or d (e.g. 90d), or never.")
                return 2
            secs = int(m.group(1)) * DURATION[m.group(2)]
        row, tok = store.create_device("script", name=a.name, scope=a.scope, created_via="cli", created_by="cli",
                                       expires_at=time.time() + secs if secs else None)
        print(f"Script token for {row['name']} ({'read only' if row['scope'] == 'read' else 'control'}; "
              f"{'expires ' + _when(row['expires_at']) if row['expires_at'] else 'no expiry'}), shown once:")
        print(f"  {tok}")
        print("Send it as Authorization: Bearer <token> (or X-Pilot-Key) from any address; never as a cookie or in "
              f"a URL. Revoke it in Devices or with: python -m pilot dashboard-token revoke {row['id']}")
        return 0
    if a.action == "revoke":
        row = store.device(a.id)
        ok = bool(row and row["kind"] == "script") and store.revoke(a.id, "revoked", by="cli")
        print("Revoked; its next request is refused." if ok else f"No live script token {a.id}.")
        return 0 if ok else 1
    rows = [d for d in store.list_devices() if d["kind"] == "script"]
    if not rows:
        print("No script tokens. Make one: python -m pilot dashboard-token create --name NAME --scope read")
    for d in rows:
        print(f"{d['id']}  {d['name']:<24} {'read only' if d['scope'] == 'read' else 'control':<9} last used "
              f"{_when(d['last_seen_at'])}{' from ' + d['last_ip'] if d['last_ip'] else ''}; "
              f"{'expires ' + _when(d['expires_at']) if d['expires_at'] else 'no expiry'}")
    return 0


def dashboard_devices(s: Settings, a) -> int:
    """List, rename and sign out devices; read the sign-in log; lift the sign-in pauses."""
    import urllib.error
    import urllib.request

    from .auth import audit_sentences, dashboard_key, name_of
    store = auth_store(s)
    when = lambda t: time.strftime("%d %b %H:%M", time.localtime(t)) if t else "never"
    act = a.action or "list"
    if act == "list":
        rows = store.list_devices()
        if not rows:
            print("No devices signed in. Sign one in: python -m pilot dashboard-link")
        for d in rows:
            badges = ", ".join(b for b in (("carried over from the old link" if d["legacy"] else ""),
                                          ("recovery key" if d["created_via"] == "recovery_key" else "")) if b)
            kind = d["kind"] if d["kind"] == "browser" else f"script ({d['scope']})"
            print(f"{d['id']}  {kind:<16} {d['name']:<30} last used {when(d['last_seen_at'])}"
                  f"{' from ' + d['last_ip'] if d['last_ip'] else ''}; signed in {when(d['created_at'])} by "
                  f"{name_of(store, d['created_by']) or d['created_via'].replace('_', ' ')}{'; ' + badges if badges else ''}")
        return 0
    if act == "rename":
        ok = store.rename(a.id, a.name, by="cli")
        print("Renamed." if ok else f"No signed-in device {a.id}.")
        return 0 if ok else 1
    if act == "revoke":
        ok = store.revoke(a.id, "revoked", by="cli")
        print("Signed out; its next request is refused." if ok else f"No signed-in device {a.id}.")
        return 0 if ok else 1
    if act == "revoke-all":
        n = sum(store.revoke(d["id"], "revoked", by="cli") for d in store.list_devices() if d["id"] != a.keep)
        store.cancel_waiting_grants()          # a leaked code from the command line must not outlive it either
        print(f"Signed out {n} device{'s' if n != 1 else ''} and script token{'s' if n != 1 else ''}"
              f"{', kept ' + a.keep if a.keep else ''}.")
        return 0
    if act == "log":
        for e in reversed(audit_sentences(store, a.n)):
            print(f"{when(e['t'])}  {e['text']}")
        return 0
    if act == "unlock":
        req = urllib.request.Request(f"http://127.0.0.1:{a.port}/api/auth/unlock", data=b"{}", method="POST",
                                     headers={"X-Pilot-Key": dashboard_key(s.runs_dir), "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:     # loopback only: the viewer takes K only from there
                json.load(r)
        except urllib.error.HTTPError as e:
            print(f"The viewer refused: {e.code} {e.read().decode(errors='replace')[:300]}")
            return 1
        except (urllib.error.URLError, OSError):
            print(f"No viewer answers on port {a.port}; its throttles live in memory, so a restart clears them too.")
            return 0
        print("Sign-in pauses lifted: typed words work again from every address.")
        return 0
    return 2


def main(argv: list[str] | None = None) -> int:
    os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
    ap = argparse.ArgumentParser(prog="pilot", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("check", "run"):
        p = sub.add_parser(name)
        p.add_argument("--game", choices=["galciv4", "stellaris", "civ6"])
        p.add_argument("--model", help="pydantic-ai model string, e.g. google:gemini-3.8-flash")
        p.add_argument("--coords", choices=["auto", "norm1000", "pixels"])
        p.add_argument("--thinking", choices=["off", "low", "medium", "high"])
    prefs_p = sub.add_parser("prefs", help="print one saved dashboard setting (for scripts)")
    prefs_p.add_argument("--get", required=True, metavar="KEY", help="e.g. game")
    view_p = sub.add_parser("view", help="read-only dashboard over recorded runs")
    view_p.add_argument("--port", type=int, default=8780)
    view_p.add_argument("--host", help="bind address (default PILOT_VIEW_HOST or 0.0.0.0)")
    ctl_p = sub.add_parser("control", help="send one dashboard control (pause, resume, stop, instruct, ...)")
    ctl_p.add_argument("action")
    ctl_p.add_argument("--text")
    ctl_p.add_argument("--index", type=int)
    ctl_p.add_argument("--port", type=int, default=8780, help="the viewer's port")
    link_p = sub.add_parser("dashboard-link", help="sign a browser in: a one-time link, three words and a QR code")
    link_p.add_argument("--port", type=int, default=8780, help="the viewer's port")
    link_p.add_argument("--no-qr", action="store_true", help="no terminal QR code")
    link_p.add_argument("--wait", action="store_true", help="wait until the code is used and name the browser")
    dev_p = sub.add_parser("dashboard-devices", help="list, rename and sign out devices; the sign-in log; unlock")
    dev_sub = dev_p.add_subparsers(dest="action")
    dev_sub.add_parser("list")
    r = dev_sub.add_parser("rename")
    r.add_argument("id")
    r.add_argument("name")
    r = dev_sub.add_parser("revoke")
    r.add_argument("id")
    r = dev_sub.add_parser("revoke-all", help="sign out every browser and revoke every script token")
    r.add_argument("--except", dest="keep", default="", help="a device id to keep")
    r = dev_sub.add_parser("log")
    r.add_argument("-n", type=int, default=20)
    r = dev_sub.add_parser("unlock", help="lift the throttles on typed sign-in words (asks the viewer over loopback)")
    r.add_argument("--port", type=int, default=8780)
    key_p = sub.add_parser("dashboard-key", help="rotate the dashboard's service key (never printed)")
    key_p.add_argument("--rotate", action="store_true")
    key_p.add_argument("--keep", help="carried-over devices to keep: all, none, or ID,ID")
    key_p.add_argument("--force", action="store_true", help="rotate even while a pre-change live pilot runs")
    tok_p = sub.add_parser("dashboard-token", help="script tokens for other machines")
    tok_sub = tok_p.add_subparsers(dest="action")
    r = tok_sub.add_parser("create")
    r.add_argument("--name", required=True)
    r.add_argument("--scope", required=True, choices=["read", "control"])
    r.add_argument("--expires", default="never", help="e.g. 90d, 12h (default: never)")
    tok_sub.add_parser("list")
    r = tok_sub.add_parser("revoke")
    r.add_argument("id")
    data_p = sub.add_parser("data", help="import an install from before the data platform, or check the import")
    data_sub = data_p.add_subparsers(dest="action", required=True)
    r = data_sub.add_parser("import", help="copy runs/, corpora/*/learned/, the pilot journals and settings")
    r.add_argument("--from", dest="source", required=True, metavar="ROOT", help="the old install (a repo checkout)")
    r.add_argument("--prune-source", action="store_true",
                   help="then delete the imported old runtime files, only when check finds nothing missing")
    r = data_sub.add_parser("check", help="list what the data directory lacks of the old install")
    r.add_argument("--from", dest="source", required=True, metavar="ROOT")
    r = sub.add_parser("export", help="write the store's learned files and journals to a directory")
    r.add_argument("--to", required=True)
    r.add_argument("--game")
    r.add_argument("--campaign")
    run_p = sub.choices["run"]
    run_p.add_argument("--port", type=int)
    run_p.add_argument("--turns", type=int, help="turns per autopilot call")
    run_p.add_argument("--episodes", type=int, help="stop after this many decisions (testing)")
    run_p.add_argument("--speed", choices=["slowest", "slow", "normal", "fast", "faster", "fastest"],
                       help="Stellaris game speed while the AI plays ('faster' = fastest)")
    run_p.add_argument("--months", type=int, help="Stellaris: in-game months between scheduled decisions")
    run_p.add_argument("--decide-turns", type=int, help="Civilization VI: turns the game's AI plays between decisions")
    a = ap.parse_args(argv)
    s = Settings.from_env()
    if a.cmd == "prefs":
        from .models import load_prefs
        v = load_prefs(s.runs_dir).get(a.get, "")
        print(v if isinstance(v, str) else json.dumps(v))
        return 0
    if a.cmd == "data":
        return data_cmd(s, a)
    if a.cmd == "export":
        from .export import export
        from .store import open_store
        n = len(export(open_store(s.runs_dir), Path(a.to), a.game, a.campaign))
        print(f"exported {n} files to {a.to}")
        return 0
    if a.cmd == "view":
        return view(s, a.port, a.host)
    if a.cmd == "control":
        return control(s, a)
    if a.cmd == "dashboard-link":
        return dashboard_link(s, a.port, qr=not a.no_qr, wait=a.wait)
    if a.cmd == "dashboard-devices":
        return dashboard_devices(s, a)
    if a.cmd == "dashboard-key":
        return dashboard_key_cmd(s, a)
    if a.cmd == "dashboard-token":
        return dashboard_token(s, a)
    # the dashboard's model choice beats the environment; command-line options beat both
    from .models import load_prefs
    prefs = load_prefs(s.runs_dir)
    s.model = a.model or prefs.get("model") or s.model
    s.coords = a.coords or s.coords
    s.thinking = a.thinking or prefs.get("thinking") or s.thinking
    s.governor_thinking = a.thinking or prefs.get("thinking") or s.governor_thinking
    if prefs.get("fallback"):
        s.fallback_model = None if prefs["fallback"] == "none" else prefs["fallback"]
    if prefs.get("models") and not a.model:       # the dashboard's model list (each with its thinking)
        s.models = tuple(prefs["models"])
        s.model, s.governor_thinking = prefs["models"][0]["model"], prefs["models"][0]["thinking"]
    s.rotate = bool(prefs.get("rotate", s.rotate))
    s.roles = dict(prefs.get("roles") or {})
    episodes = (s.roles.get("episodes") or {}).get("models")
    if game_for_roles(a, prefs) == "galciv4" and episodes and not a.model:   # GC4 blockers: their own model
        s.model, s.thinking = episodes[0]["model"], episodes[0]["thinking"]
    game = a.game or (prefs.get("game") if a.cmd == "run" else None)
    if game:
        s.game = game
    if a.cmd == "check":
        return check(s)
    s.dashboard_port = a.port or s.dashboard_port
    s.turns_per_autopilot = a.turns or s.turns_per_autopilot
    if a.speed:
        s.speed = "fastest" if a.speed == "faster" else a.speed
    else:
        s.speed = prefs.get("speed", s.speed)
    s.decide_every_months = a.months or prefs.get("months") or s.decide_every_months
    s.decide_every_turns = a.decide_turns or s.decide_every_turns
    return run(s, a.episodes)


if __name__ == "__main__":
    sys.exit(main())
