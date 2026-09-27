"""`python -m pilot` — run the autonomous LLM pilot, or check the setup.

    python -m pilot check                     # key, model, agent, corpus
    python -m pilot run [--model M] [--port P] [--turns N] [--no-commit] [--episodes K]
    python -m pilot run --game stellaris [--speed fast|fastest|...] [--months N]
    python -m pilot run --game civ6 [--decide-turns N]  # the game's AI plays N turns between decisions
    python -m pilot view [--port P]           # read-only dashboard over recorded runs
    python -m pilot dashboard-link [--port P] [--no-qr] [--wait]   # sign a browser in: a one-time link,
                                              # three words and a QR code (never the key)
    python -m pilot dashboard-devices [list | rename ID NAME | revoke ID | revoke-all [--except ID] |
                                       log [-n N] | unlock [--port P]]
    python -m pilot rebuild-telemetry         # recreate runs/telemetry.sqlite from the run logs
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
    from .telemetry import Telemetry
    log = EventLog(s.runs_dir, run_id, s.model, telemetry=Telemetry(s.telemetry_db))
    if s.game == "civ6":
        from .civ6 import ControllerCiv6
        game = ControllerCiv6(s.controller_bin, s.corpus_dir, s.agent_url, REPO)
    else:
        game = McpGame(s.controller_bin, s.corpus_dir, s.agent_url, REPO, title=s.window_title)
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
    serve_in_background(pilot, s.dashboard_host, s.dashboard_port)
    print(f"pilot {run_id}: model {s.model}; dashboard http://{s.dashboard_host}:{s.dashboard_port}/ ; "
          f"log {log.dir / 'events.jsonl'}", flush=True)

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
        log.close()
    return 0


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


def rebuild(s: Settings) -> int:
    from .telemetry import Telemetry
    tel = Telemetry(s.telemetry_db)
    n = tel.rebuild(s.runs_dir)
    counts = {t: tel.query(f"SELECT COUNT(*) AS n FROM {t}")[0]["n"] for t in ("campaigns", "runs", "decisions", "metrics")}
    print(f"rebuilt {s.telemetry_db} from {n} runs: {counts}")
    return 0


def view(s: Settings, port: int) -> int:
    from aiohttp import web

    from .auth import RUNNER_KWARGS
    from .dashboard import link_host, make_app
    from .telemetry import Telemetry
    app = make_app(None, s.runs_dir, Telemetry(s.telemetry_db))       # the key never reaches this line or the log
    print(f"dashboard on http://{link_host(s.dashboard_host)}:{port}/ (to sign in a browser: "
          "python -m pilot dashboard-link)", flush=True)
    web.run_app(app, host=s.dashboard_host, port=port, print=None, **RUNNER_KWARGS)
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
        ok = store.rename(a.id, a.name)
        print("Renamed." if ok else f"No signed-in device {a.id}.")
        return 0 if ok else 1
    if act == "revoke":
        ok = store.revoke(a.id, "revoked", by="cli")
        print("Signed out; its next request is refused." if ok else f"No signed-in device {a.id}.")
        return 0 if ok else 1
    if act == "revoke-all":
        n = sum(store.revoke(d["id"], "revoked", by="cli") for d in store.list_devices() if d["id"] != a.keep)
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
    sub.add_parser("rebuild-telemetry", help="recreate runs/telemetry.sqlite from the run logs")
    view_p = sub.add_parser("view", help="read-only dashboard over recorded runs")
    view_p.add_argument("--port", type=int, default=8780)
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
    run_p = sub.choices["run"]
    run_p.add_argument("--port", type=int)
    run_p.add_argument("--turns", type=int, help="turns per autopilot call")
    run_p.add_argument("--episodes", type=int, help="stop after this many decisions (testing)")
    run_p.add_argument("--no-commit", action="store_true", help="don't commit learnings")
    run_p.add_argument("--speed", choices=["slowest", "slow", "normal", "fast", "faster", "fastest"],
                       help="Stellaris game speed while the AI plays ('faster' = fastest)")
    run_p.add_argument("--months", type=int, help="Stellaris: in-game months between scheduled decisions")
    run_p.add_argument("--decide-turns", type=int, help="Civilization VI: turns the game's AI plays between decisions")
    a = ap.parse_args(argv)
    s = Settings.from_env()
    if a.cmd == "view":
        return view(s, a.port)
    if a.cmd == "dashboard-link":
        return dashboard_link(s, a.port, qr=not a.no_qr, wait=a.wait)
    if a.cmd == "dashboard-devices":
        return dashboard_devices(s, a)
    if a.cmd == "rebuild-telemetry":
        return rebuild(s)
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
    if game and game != s.game:
        from .config import default_journal
        s.game = game
        if "PILOT_JOURNAL" not in os.environ:      # an explicit journal path wins over the game default
            s.journal = default_journal(game)
    if a.cmd == "check":
        return check(s)
    s.dashboard_port = a.port or s.dashboard_port
    s.turns_per_autopilot = a.turns or s.turns_per_autopilot
    s.commit_learnings = s.commit_learnings and not a.no_commit
    if a.speed:
        s.speed = "fastest" if a.speed == "faster" else a.speed
    else:
        s.speed = prefs.get("speed", s.speed)
    s.decide_every_months = a.months or prefs.get("months") or s.decide_every_months
    s.decide_every_turns = a.decide_turns or s.decide_every_turns
    return run(s, a.episodes)


if __name__ == "__main__":
    sys.exit(main())
