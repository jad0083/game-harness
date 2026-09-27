"""Activity (docs/design/2026-09-27-dashboard-v2-design.md, rulings 18 and 29): every event kind the pilots
emit has a sentence on the page (an unknown kind reads "Unrecognised event", never inline JSON), the
order record's events stay out of the feed, and GET /api/events gives a past campaign's own events
(not the newest run's) with the game date each happened at, then only the new ones."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from aiohttp.test_utils import TestClient, TestServer

from pilot.dashboard import make_app
from pilot.events import EventLog
from pilot.telemetry import Telemetry

ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT / "src" / "pilot" / "static" / "dashboard.html").read_text(encoding="utf-8")
# kinds the design names that another branch emits (the Stellaris watchdog's self-pause)
DESIGN_KINDS = {"stall", "self_paused"}
FEED_QUIET = {"metrics", "status", "trace", "chat", "plan", "order_outcome", "order_followed"}


def emitted_kinds() -> set[str]:
    kinds = set()
    for path in (ROOT / "src" / "pilot").rglob("*.py"):
        kinds |= set(re.findall(r"\bemit\(\s*[\"']([a-z_]+)[\"']", path.read_text(encoding="utf-8")))
    return kinds


def describe_cases() -> set[str]:
    body = re.search(r"function describe\(ev\) \{(.*?)\n\}\n", PAGE, re.DOTALL)
    assert body, "describe(ev) not found in dashboard.html"
    return set(re.findall(r'case "([a-z_]+)":', body.group(1)))


def quiet_kinds() -> set[str]:
    m = re.search(r"const QUIET = new Set\(\[([^\]]*)\]\)", PAGE)
    assert m, "QUIET not found in dashboard.html"
    return set(re.findall(r'"([a-z_]+)"', m.group(1)))


def test_every_emitted_kind_has_a_sentence():
    kinds = emitted_kinds() | DESIGN_KINDS
    assert {"turn", "briefing_error", "model_fallback", "popups_quieted", "last_stand_check"} <= kinds   # the scan works
    missing = sorted(kinds - quiet_kinds() - describe_cases())
    assert missing == [], f"no Activity sentence for {missing}"


def test_quiet_kinds_are_only_the_documented_ones():
    """The order record's events go to the Orders tab, chat to Talk; nothing else is hidden."""
    assert quiet_kinds() == FEED_QUIET


def test_an_unknown_kind_never_prints_json():
    body = re.search(r"function describe\(ev\) \{(.*?)\n\}\n", PAGE, re.DOTALL).group(1)
    assert "JSON.stringify" not in body
    assert "Unrecognised event: " in body


def _campaigns(tmp_path):
    runs = tmp_path / "runs"
    tel = Telemetry(runs / "telemetry.sqlite")
    a = EventLog(runs, "20260926-090000", "m", telemetry=tel)
    a.emit("run_start", game="civ6", model="m")
    a.set_campaign("civ6", "kublai", "Kublai Khan, China")
    a.emit("metrics", date="T50", turn=50, score=1)
    a.emit("briefing_error", error="autoplay at T50: Error: Failed /tuner/lua")
    a.emit("status", status="playing")
    a.emit("turn", turn=52, turns=2, seconds=60.0)
    a.emit("order_outcome", order_kind="research", key="research", id="tech:writing", result="completed", turn=52)
    a.emit("metrics", date="T52", turn=52, score=2)
    a.emit("control", action="pause", by="Pixel phone")
    a.emit("run_end")
    a.close()
    b = EventLog(runs, "20260927-090000", "m", telemetry=tel)          # a newer run of another campaign
    b.emit("run_start", game="stellaris", model="m")
    b.set_campaign("stellaris", "theia", "Theian Union")
    b.emit("metrics", date="2288.01.01", systems=3)
    b.emit("stall", date="2288.01.01", seconds=400, limit=300, frame="")
    b.close()
    return runs, tel


def test_events_api_gives_the_campaigns_own_events_with_their_dates(tmp_path):
    runs, tel = _campaigns(tmp_path)

    async def go():
        async with TestClient(TestServer(make_app(None, runs, tel))) as c:
            evs = await (await c.get("/api/events?campaign=civ6/kublai")).json()
            kinds = [e["kind"] for e in evs]
            assert kinds == ["run_start", "campaign", "briefing_error", "turn", "control", "run_end"]
            assert "stall" not in kinds                                    # the other campaign's
            dates = {e["kind"]: e.get("date") for e in evs}
            assert dates["briefing_error"] == "T50" and dates["turn"] == "T52" and dates["control"] == "T52"
            assert all(e["run_id"] == "20260926-090000" for e in evs)
            later = next(e for e in evs if e["kind"] == "turn")["id"]
            newer = await (await c.get(f"/api/events?campaign=civ6/kublai&after={later}")).json()
            assert [e["kind"] for e in newer] == ["control", "run_end"] and newer[0]["date"] == "T52"
            assert [e["kind"] for e in await (await c.get("/api/events?campaign=civ6/kublai&n=2")).json()] == ["control", "run_end"]
            assert (await c.get("/api/events")).status == 400
            assert (await c.get("/api/events?campaign=civ6/kublai&after=x")).status == 400
    asyncio.run(go())
    tel.close()


def test_events_api_leaves_out_backfill_runs(tmp_path):
    runs, tel = _campaigns(tmp_path)
    bf = EventLog(runs, "20260926-080000-backfill", "backfill", telemetry=tel)
    bf.emit("run_start", game="civ6", model="backfill")
    bf.emit("campaign", game="civ6", name="kublai")
    bf.emit("journal", text="backfilled 40 orders")
    bf.close()

    async def go():
        async with TestClient(TestServer(make_app(None, runs, tel))) as c:
            evs = await (await c.get("/api/events?campaign=civ6/kublai")).json()
            assert not [e for e in evs if e["run_id"].endswith("-backfill")]
    asyncio.run(go())
    tel.close()
