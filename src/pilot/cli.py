"""`python -m pilot` — run the autonomous LLM pilot, or check the setup.

    python -m pilot check                     # key, model, agent, corpus
    python -m pilot run [--model M] [--port P] [--turns N] [--no-commit] [--episodes K]
    python -m pilot run --game stellaris [--speed fast|fastest|...] [--months N]
    python -m pilot view [--port P]           # read-only dashboard over recorded runs
    python -m pilot rebuild-telemetry         # recreate runs/telemetry.sqlite from the run logs
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time

from .config import REPO, Settings


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
    game = McpGame(s.controller_bin, s.corpus_dir, s.agent_url, REPO, title=s.window_title)
    if s.game == "stellaris":
        from .governor import Governor
        pilot = Governor(s, game, log)
    else:
        pilot = Pilot(s, game, log)
    log.state.info["port"] = s.dashboard_port      # lets the always-on viewer find this run
    serve_in_background(pilot, s.dashboard_host, s.dashboard_port)
    print(f"pilot {run_id}: model {s.model}; dashboard http://{s.dashboard_host}:{s.dashboard_port}/ ; "
          f"log {log.dir / 'events.jsonl'}", flush=True)

    def on_signal(*_):
        print("stopping after the current step...", flush=True)
        pilot.stop()

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    try:
        if s.game == "stellaris":
            pilot.run(max_decisions=episodes)
        else:
            pilot.run(max_episodes=episodes)
    finally:
        game.close()
        log.close()
    return 0


def rebuild(s: Settings) -> int:
    from .telemetry import Telemetry
    tel = Telemetry(s.telemetry_db)
    n = tel.rebuild(s.runs_dir)
    counts = {t: tel.query(f"SELECT COUNT(*) AS n FROM {t}")[0]["n"] for t in ("campaigns", "runs", "decisions", "metrics")}
    print(f"rebuilt {s.telemetry_db} from {n} runs: {counts}")
    return 0


def view(s: Settings, port: int) -> int:
    from aiohttp import web

    from .dashboard import make_app
    print(f"viewer: http://{s.dashboard_host}:{port}/ over {s.runs_dir}", flush=True)
    from .telemetry import Telemetry
    web.run_app(make_app(None, s.runs_dir, Telemetry(s.telemetry_db)), host=s.dashboard_host, port=port, print=None)
    return 0


def main(argv: list[str] | None = None) -> int:
    os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
    ap = argparse.ArgumentParser(prog="pilot", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("check", "run"):
        p = sub.add_parser(name)
        p.add_argument("--game", choices=["galciv4", "stellaris"])
        p.add_argument("--model", help="pydantic-ai model string, e.g. google:gemini-3.8-flash")
        p.add_argument("--coords", choices=["auto", "norm1000", "pixels"])
        p.add_argument("--thinking", choices=["off", "low", "medium", "high"])
    sub.add_parser("rebuild-telemetry", help="recreate runs/telemetry.sqlite from the run logs")
    view_p = sub.add_parser("view", help="read-only dashboard over recorded runs")
    view_p.add_argument("--port", type=int, default=8780)
    run_p = sub.choices["run"]
    run_p.add_argument("--port", type=int)
    run_p.add_argument("--turns", type=int, help="turns per autopilot call")
    run_p.add_argument("--episodes", type=int, help="stop after this many decisions (testing)")
    run_p.add_argument("--no-commit", action="store_true", help="don't commit learnings")
    run_p.add_argument("--speed", choices=["slowest", "slow", "normal", "fast", "faster", "fastest"],
                       help="Stellaris game speed while the AI plays ('faster' = fastest)")
    run_p.add_argument("--months", type=int, help="Stellaris: in-game months between scheduled decisions")
    a = ap.parse_args(argv)
    s = Settings.from_env()
    if a.cmd == "view":
        return view(s, a.port)
    if a.cmd == "rebuild-telemetry":
        return rebuild(s)
    s.model = a.model or s.model
    s.coords = a.coords or s.coords
    s.thinking = a.thinking or s.thinking
    if a.game and a.game != s.game:
        from .config import default_journal
        s.game, s.journal = a.game, default_journal(a.game)
    if a.cmd == "check":
        return check(s)
    s.dashboard_port = a.port or s.dashboard_port
    s.turns_per_autopilot = a.turns or s.turns_per_autopilot
    s.commit_learnings = s.commit_learnings and not a.no_commit
    if a.speed:
        s.speed = "fastest" if a.speed == "faster" else a.speed
    s.decide_every_months = a.months or s.decide_every_months
    return run(s, a.episodes)


if __name__ == "__main__":
    sys.exit(main())
