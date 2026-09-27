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

from uikit import MODELS, PC_CIV6, UI_KEY, Served, seed_runs

from pilot.auth import Auth


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


@pytest.fixture
def ui_runs(tmp_path, monkeypatch):
    """runs/ with a finished Stellaris campaign and a live Civ VI run (a fake pilot with no frames)."""
    from pilot import dashboard, models
    monkeypatch.setenv("PILOT_DASHBOARD_KEY", UI_KEY)
    monkeypatch.setattr(dashboard, "pc_status", lambda: dict(PC_CIV6))
    monkeypatch.setattr(models, "available_models", lambda s: list(MODELS))
    monkeypatch.setattr(models, "provider_catalog", lambda s: [])
    runs = seed_runs(tmp_path / "runs")
    yield runs
    runs["log"].close()
    runs["tel"].close()


@pytest.fixture
def live_servers(ui_runs):
    """The live pilot's own dashboard and the viewer over the same runs/, both on loopback."""
    from pilot.dashboard import make_app
    log = ui_runs["log"]
    live = Served(make_app(ui_runs["pilot"], key=UI_KEY))
    log.state.info["port"] = live.port
    log.emit("status", status="playing")
    auth = Auth.from_env(ui_runs["runs"], key=UI_KEY, keepalive_s=0.2)
    viewer = Served(make_app(None, ui_runs["runs"], ui_runs["tel"], key=UI_KEY, auth=auth))
    yield {**ui_runs, "live": live, "viewer": viewer, "auth": auth}
    viewer.stop()
    live.stop()


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


