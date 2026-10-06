"""What the dashboard's APIs say about a game: Civ VI windows, campaign dates in game order, frames."""

from __future__ import annotations

import asyncio
import io
import json

from aiohttp.test_utils import TestClient, TestServer

from pilot import dashboard
from pilot.dashboard import make_app
from pilot.events import EventLog
from pilot.telemetry import Telemetry


class FakeResp(io.BytesIO):
    def __init__(self, body: dict):
        super().__init__(json.dumps(body).encode())

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_civ6_window_is_a_known_game():
    assert dashboard.game_of("Sid Meier's Civilization VI (DX12)") == "civ6"
    assert dashboard.game_of("Sid Meier's Civilization VI") == "civ6"
    assert dashboard.game_of("Stellaris") == "stellaris"
    assert dashboard.game_of("Civilization VI wiki - Chrome") == "civ6"   # a title match is a hint, not proof
    assert dashboard.game_of("Inbox") is None


def test_pc_status_names_civ6_in_front(monkeypatch):
    monkeypatch.setenv("GAME_AGENT_TOKEN", "t")
    monkeypatch.setenv("GAME_AGENT_URL", "http://127.0.0.1:8765")

    def urlopen(req, timeout=None):
        if req.full_url.endswith("/health"):
            return FakeResp({"version": "1.6.1", "foreground": "Sid Meier's Civilization VI (DX12)"})
        return FakeResp({"windows": [{"title": "Sid Meier's Civilization VI (DX12)"}]})

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    st = dashboard.pc_status()
    assert st["games"] == ["civ6"] and st["front_game"] == "civ6" and st["game_in_front"] is True


def _campaign(tmp_path, run: str, game: str, name: str, dates: list[str]) -> Telemetry:
    tel = Telemetry(tmp_path / "runs" / "telemetry.sqlite")
    tel.record(run, {"t": 1.0, "kind": "run_start", "game": game, "model": "m"})
    tel.record(run, {"t": 2.0, "kind": "campaign", "game": game, "name": name})
    for i, d in enumerate(dates):
        tel.record(run, {"t": 3.0 + i, "kind": "metrics", "date": d, "score": i})
    return tel


def test_campaign_latest_date_is_the_latest_in_game_order(tmp_path):
    """MAX(date) compares text, so "T99" beat "T310"; the latest date follows the game's own order."""
    tel = _campaign(tmp_path, "r1", "civ6", "kublai", ["T99", "T100", "T310", "T57"])
    tel.record("r2", {"t": 20.0, "kind": "run_start", "game": "stellaris", "model": "m"})
    tel.record("r2", {"t": 21.0, "kind": "campaign", "game": "stellaris", "name": "theia"})
    for i, d in enumerate(["2288.12.01", "2289.01.01", "2288.08.01"]):
        tel.record("r2", {"t": 22.0 + i, "kind": "metrics", "date": d})

    async def go():
        app = make_app(None, tmp_path / "runs", tel)
        async with TestClient(TestServer(app)) as c:
            rows = {r["id"]: r for r in await (await c.get("/api/campaigns")).json()}
        assert rows["civ6/kublai"]["latest"] == "T310"
        assert rows["stellaris/theia"]["latest"] == "2289.01.01"
    asyncio.run(go())


def test_campaigns_say_their_runs_whether_they_are_empty_and_which_is_live(tmp_path):
    """The campaign list (ruling 4): runs and decisions per campaign, `empty` for one with neither a
    decision nor a metrics row (a failed start), and `state` live, paused, needs_you or stopped from the
    live pilot's own run."""
    runs = tmp_path / "runs"
    tel = Telemetry(runs / "telemetry.sqlite")
    empty = EventLog(runs, "20260925-080000", "m", telemetry=tel)
    empty.emit("run_start", game="galciv4", model="m")
    empty.set_campaign("galciv4", "untitled", "")
    empty.emit("run_end")
    empty.close()
    old = EventLog(runs, "20260926-080000", "m", telemetry=tel)
    old.emit("run_start", game="civ6", model="m")
    old.set_campaign("civ6", "kublai", "Kublai Khan, China")
    old.emit("metrics", date="T50", turn=50, score=1)
    old.emit("run_end")
    old.close()
    backfill = EventLog(runs, "20260926-223910-backfill", "m", telemetry=tel)    # ruling 20: hidden in run lists
    backfill.emit("run_start", game="civ6", model="m")
    backfill.set_campaign("civ6", "kublai", "Kublai Khan, China")
    backfill.close()
    live = EventLog(runs, "20260927-080000", "m", telemetry=tel)
    live.emit("run_start", game="civ6", model="m")
    live.set_campaign("civ6", "kublai", "Kublai Khan, China")
    live.state.status = "needs_attention"

    async def go():
        async with TestClient(TestServer(make_app(FakeLive(live), runs, tel))) as c:
            rows = {r["id"]: r for r in await (await c.get("/api/campaigns")).json()}
        assert rows["galciv4/untitled"]["empty"] is True and rows["galciv4/untitled"]["runs"] == 1
        assert rows["galciv4/untitled"]["state"] == "stopped"
        assert rows["civ6/kublai"]["empty"] is False and rows["civ6/kublai"]["runs"] == 2
        assert rows["civ6/kublai"]["state"] == "needs_you"
        # when each was last played (its newest run's end, else start): the page's "No run is playing. Last: ..."
        assert rows["civ6/kublai"]["last_t"] >= rows["galciv4/untitled"]["last_t"] > 0
        async with TestClient(TestServer(make_app(None, runs, tel))) as c:       # a viewer with no live pilot
            rows = {r["id"]: r for r in await (await c.get("/api/campaigns")).json()}
        assert rows["civ6/kublai"]["state"] == "stopped"
    asyncio.run(go())
    live.close()


class FakeLive:
    def __init__(self, log):
        self.log = log


def test_runs_say_whether_they_have_a_frame(tmp_path):
    """The page asks for a run's frame only when one exists (a 404 every 10 s for governor games)."""
    runs = tmp_path / "runs"
    with_frame, without = EventLog(runs, "20260927-100000", "m"), EventLog(runs, "20260927-110000", "m")
    with_frame.frame(b"\xff\xd8jpeg")
    with_frame.emit("run_start", model="m"), without.emit("run_start", model="m")   # their rows in the store

    async def go():
        async with TestClient(TestServer(make_app(None, runs))) as c:
            rows = {r["id"]: r for r in await (await c.get("/runs")).json()}
        assert rows["20260927-100000"]["frame"] is True
        assert rows["20260927-110000"]["frame"] is False
    asyncio.run(go())
    with_frame.close(), without.close()


def test_decisions_carry_the_error_of_a_failed_decision(tmp_path):
    """A decision whose every model call failed shows its error in the list, not an empty row."""
    runs = tmp_path / "runs"
    tel = Telemetry(runs / "telemetry.sqlite")
    log = EventLog(runs, "20260927-100000", "m", telemetry=tel)
    log.emit("run_start", game="civ6", model="m")
    log.set_campaign("civ6", "kublai")
    log.save_trace(1, {"episode": 1, "date": "T55", "trigger": "scheduled", "outcome": "error",
                       "error": "ModelHTTPError: status_code: 503, high demand", "steps": []})
    log.save_trace(2, {"episode": 2, "date": "T56", "decision": "keep", "outcome": "no orders", "steps": []})

    async def go():
        async with TestClient(TestServer(make_app(None, runs, tel))) as c:
            rows = await (await c.get("/api/decisions?campaign=civ6/kublai")).json()
        assert [r["error"] for r in rows] == ["ModelHTTPError: status_code: 503, high demand", None]
    asyncio.run(go())
    log.close()
