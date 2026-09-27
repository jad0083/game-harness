"""The Civ VI Orders tab's data (docs/design/2026-09-27-dashboard-v2-design.md, rulings 19-22): GET /api/orders
gives the order record per key with its rate only above the sample floor, the log of every order with
its fate and the decision it came from (backfilled rows tagged), purchases, open orders with how far
they were followed, and the last stands; the live record and the campaign record agree."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from aiohttp.test_utils import TestClient, TestServer
from test_civ6_governor import INDEX, _replace_fixture, governor, orders_model, setup  # noqa: F401

from pilot.civ6 import FakeCiv6
from pilot.dashboard import make_app
from pilot.events import EventLog
from pilot.telemetry import Telemetry

CORPORA = Path(__file__).resolve().parents[1] / "corpora"


def row(key, result, turn, **kw):
    kind = key.split()[0]
    return {"order_kind": kind, "key": key, "item_kind": None, "id": kw.pop("id", "unit:slinger"), "city": kw.pop("city", "Chengdu"),
            "currency": kw.pop("currency", None), "situation": None, "ordered": kw.pop("ordered", f"T{turn - 2}"),
            "top3_hit": None, "result": result, "by": kw.pop("by", None), "turns": 2, "date": f"T{turn}", "turn": turn,
            "detail": kw.pop("detail", ""), **kw}


def campaign(tmp_path):
    """A Civ VI campaign with a backfill run (as scripts/civ6-backfill-orders.py writes it) and a real run."""
    runs = tmp_path / "runs"
    tel = Telemetry(runs / "telemetry.sqlite")
    bf = EventLog(runs, "20260926-080000-backfill", "backfill", telemetry=tel)
    bf.emit("run_start", game="civ6", model="backfill")
    bf.emit("campaign", game="civ6", name="kublai")
    for r in (row("purchase gold", "completed", 20, id="unit:warrior", currency="gold", backfilled=True, ordered="T20"),
              row("purchase faith", "refused", 22, id="building:gurdwara", city="Beijing", currency="faith", backfilled=True,
                  ordered="T22", detail="refused: 380 faith, over the 283 allowed")):
        bf.emit("order_outcome", **r)
    bf.emit("run_end")
    bf.close()
    log = EventLog(runs, "20260927-100000", "m", telemetry=tel)
    log.emit("run_start", game="civ6", model="m")
    log.set_campaign("civ6", "kublai", "Kublai Khan, China")
    log.save_trace(1, {"episode": 1, "date": "T39", "decision": "orders", "reason": "r", "outcome": "o", "steps": []})
    for turn in (41, 43, 44, 46):
        log.emit("order_outcome", **row("production replace", "overridden", turn, by="unit:trader", ordered="T39"))
    for turn, res in ((42, "completed"), (45, "held"), (47, "completed")):
        log.emit("order_outcome", **row("research", res, turn, id="tech:writing", city="", ordered="T39"))
    log.emit("order_followed", ref="r1", row={**row("civic", None, 0, id="civic:foreign_trade", city="", ordered="T46"),
                                              "ref": "r1"},
             order={"kind": "civic", "id": "civic:foreign_trade"}, wire=None, expect={"civic": "CIVIC_FOREIGN_TRADE"},
             base={"turn": 46}, window=8)
    log.emit("metrics", date="T49", turn=49, score=100)
    log.emit("last_stand", city="Chengdu", turn=44, date="T44", in_a_row=1, ran=True, stopped="done",
             actions=[{"action": "city_strike", "result": "took", "detail": "predicted 28", "predicted": 28}], pins=[])
    return runs, tel, log


def test_orders_api_gives_the_record_log_purchases_and_open_orders(tmp_path):
    runs, tel, log = campaign(tmp_path)

    async def go():
        async with TestClient(TestServer(make_app(None, runs, tel, corpora=CORPORA))) as c:
            o = await (await c.get("/api/orders?campaign=civ6/kublai")).json()
            rec = o["record"]
            assert rec["production replace"]["label"] == "Production, replace the AI's choice"
            assert (rec["production replace"]["judged"], rec["production replace"]["rate"], rec["production replace"]["weak"]) == (4, 0.0, True)
            assert rec["research"]["judged"] == 3 and rec["research"]["rate"] == 1.0
            assert rec["purchase faith"]["excluded"]["refused"] == 1 and rec["purchase faith"]["rate"] is None
            assert rec["production replace"]["last_override"]["by_name"] == "Trader"
            assert o["spec"] == {"window_turns": 30, "weak_rate": 0.5, "min_samples": {"production": 4, "purchase": 4, "other": 3}}
            assert o["now_turn"] == 49
            log_rows = o["log"]
            assert [r["date"] for r in log_rows][:3] == ["T47", "T46", "T46"]      # newest first, open orders among them
            opened = next(r for r in log_rows if r["fate"]["key"] == "open")
            assert opened["name"] == "Foreign Trade" and opened["followed"] == {"turns": 3, "window": 8}
            back = [r for r in log_rows if r.get("backfilled")]
            assert len(back) == 2 and back[0]["fate"]["key"] == "refused" and back[0]["fate"]["why"] == "380 faith, over the 283 allowed"
            slinger = next(r for r in log_rows if r["id"] == "unit:slinger")
            assert slinger["name"] == "Slinger" and slinger["fate"]["by"] == "Trader"
            assert slinger["decision"] == {"run_id": "20260927-100000", "episode": 1}
            assert [p["currency"] for p in o["purchases"]] == ["faith", "gold"]
            assert o["stands"][0]["city"] == "Chengdu"
            only = await (await c.get("/api/orders?campaign=civ6/kublai&kind=purchase&fate=refused")).json()
            assert [r["id"] for r in only["log"]] == ["building:gurdwara"]
            assert len((await (await c.get("/api/orders?campaign=civ6/kublai&limit=2")).json())["log"]) == 2
            assert (await c.get("/api/orders")).status == 400
            runs_list = await (await c.get("/runs")).json()
            assert next(r for r in runs_list if r["id"].endswith("-backfill"))["backfill"] is True
    asyncio.run(go())
    log.close()


def test_the_live_record_and_the_campaign_record_agree(setup):  # noqa: F811
    s, log = setup
    tel = Telemetry(s.runs_dir / "telemetry.sqlite")
    log.telemetry = tel
    log.emit("run_start", game="civ6", model="m")

    def ai(state):
        state["cities"][0]["producing"] = "BUILDING_GRANARY"
    game = FakeCiv6(_replace_fixture(), index=INDEX, ai=ai)
    g = governor(setup, game, orders_model([{"kind": "production", "city": "Beijing", "id": "unit:slinger"}], []))
    g.run(max_decisions=2)
    live = g.log.state.info["order_record"]

    async def go():
        async with TestClient(TestServer(make_app(None, s.runs_dir, tel, corpora=CORPORA))) as c:
            o = await (await c.get(f"/api/orders?campaign={log.campaign_id}")).json()
        strip = lambda rec: {k: {f: v for f, v in r.items() if f not in ("label",)} for k, r in rec.items()}
        got = strip(o["record"])
        for r in got.values():
            if r.get("last_override"):
                r["last_override"].pop("by_name", None)
                r["last_override"].pop("name", None)
        assert got == json.loads(json.dumps(live)) and live
    asyncio.run(go())
    tel.close()
