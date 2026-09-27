"""Browser tests of the dashboard pages (Playwright's own Chromium), against fixture servers on
127.0.0.1 with a throwaway runs/ folder: never the live 8780/8790 services.

Run with `pytest -m ui` (scripts/ci.sh does when Chromium is installed); the plain `pytest` run
leaves them out. Screenshots go to each test's tmp dir."""

from __future__ import annotations

from pathlib import Path

import pytest

try:
    from playwright.sync_api import sync_playwright
except ImportError:          # pragma: no cover - the shared .venv has it; a fresh one may not
    sync_playwright = None

from uikit import UI_KEY, FakePilot, Served

from pilot.events import EventLog
from pilot.telemetry import Telemetry


def _chromium_ok() -> bool:
    if sync_playwright is None:
        return False
    try:
        with sync_playwright() as p:
            return Path(p.chromium.executable_path).exists()
    except Exception:  # noqa: BLE001
        return False


CHROMIUM = _chromium_ok()


def pytest_collection_modifyitems(config, items):
    if CHROMIUM:
        return
    skip = pytest.mark.skip(reason="Playwright's Chromium is not installed (python -m playwright install chromium)")
    for item in items:
        if "tests/ui/" in str(item.fspath).replace("\\", "/"):
            item.add_marker(skip)


CIV6_METRICS = [{"date": f"T{t}", "score": 40 + t, "military": 300 + 5 * t, "science": 20.5 + t / 10, "culture": 12.0 + t / 20,
                     "gold": 200 + t, "faith": 60 + t, "cities": 5 + t // 20, "techs_known": 20 + t // 3, "civics_known": 18 + t // 4,
                     "pop": 30 + t // 2} for t in range(50, 58)]


def _trace(log: EventLog, n: int, **fields) -> None:
    log.state.episodes = n
    log.save_trace(n, {"episode": n, "model": "google:gemini-3.1-pro-preview", "thinking_level": "medium",
                       "game": fields.get("game", "civ6"), "current": None, "seconds": 63.0,
                       "tokens_in": 41000, "tokens_out": 1200,
                       "steps": [{"type": "prompt", "text": "briefing"}], **fields})


@pytest.fixture
def ui_runs(tmp_path, monkeypatch):
    """runs/ with a finished Stellaris campaign and a live Civ VI run (a fake pilot with no frames)."""
    from pilot import dashboard, models
    monkeypatch.setenv("PILOT_DASHBOARD_KEY", UI_KEY)
    monkeypatch.setattr(dashboard, "pc_status", lambda: {"online": True, "version": "1.6.1", "games": ["civ6"],
                                                         "game_in_front": True, "front_game": "civ6"})
    monkeypatch.setattr(models, "available_models", lambda s: ["google:gemini-3.8-flash", "google:gemini-3.1-pro-preview"])
    monkeypatch.setattr(models, "provider_catalog", lambda s: [])
    runs = tmp_path / "runs"
    tel = Telemetry(runs / "telemetry.sqlite")

    old = EventLog(runs, "20260926-090000", "google:gemini-3.8-flash", telemetry=tel)
    old.emit("run_start", game="stellaris", model="google:gemini-3.8-flash", speed="fast")
    old.set_campaign("stellaris", "theia", "Theian Union")
    for i, mo in enumerate(range(1, 7)):
        old.emit("metrics", date=f"2288.{mo:02d}.01", systems=20 + i, planets=8, pops=90 + i,
                 net={"energy": 40 + i, "minerals": 30, "food": 10, "alloys": 12, "influence": 2, "unity": 8},
                 stockpile={"energy": 900, "minerals": 800, "food": 500, "alloys": 300, "influence": 100, "unity": 400},
                 military_power=5000 + 100 * i, economy_power=3000, tech_power=2000)
    _trace(old, 1, game="stellaris", date="2288.03.01", trigger="scheduled", decision="expand",
           reason="Room to grow toward the core.", outcome="applied", current="diplomacy_first")
    old.state.status = "stopped"
    old.emit("run_end")
    old.close()

    log = EventLog(runs, "20260927-100000", "google:gemini-3.8-flash", telemetry=tel)
    log.emit("run_start", game="civ6", model="google:gemini-3.8-flash")
    log.set_campaign("civ6", "kublai", "Kublai Khan, China")
    for m in CIV6_METRICS:
        log.emit("metrics", **m)
    _trace(log, 1, date="T52", trigger="scheduled", decision="orders", outcome="research tech:writing: stuck",
           reason="Chengdu is under siege; buy a slinger with faith and keep science on Writing.")
    _trace(log, 2, date="T55", trigger="city threatened (Chengdu)", outcome="error",
           error="ModelHTTPError: status_code: 503, model_name: gemini-3.8-flash, body: {'error': {'code': 503, "
                 "'message': 'This model is currently experiencing high demand.'}}")
    info = log.state.info
    info.update(game="civ6", decide_turns=5, directives=[], controls=["instruct", "chat", "order_add", "order_remove",
                                                                        "decide_now", "set_models", "set_months"])
    log.state.game_date = "T57"
    log.state.status = "playing"
    yield {"runs": runs, "tel": tel, "log": log, "pilot": FakePilot(log)}
    log.close()
    tel.close()


@pytest.fixture
def live_servers(ui_runs):
    """The live pilot's own dashboard and the viewer over the same runs/, both on loopback."""
    from pilot.dashboard import make_app
    log = ui_runs["log"]
    live = Served(make_app(ui_runs["pilot"], key=UI_KEY))
    log.state.info["port"] = live.port
    log.emit("status", status="playing")
    viewer = Served(make_app(None, ui_runs["runs"], ui_runs["tel"], key=UI_KEY))
    yield {**ui_runs, "live": live, "viewer": viewer}
    viewer.stop()
    live.stop()


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


