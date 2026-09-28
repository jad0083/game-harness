"""Decisions as the page shows them (docs/design/2026-09-27-dashboard-v2-design.md, rulings 14, 27, 28,
30): the trigger in words, an error cut to its cause, orders by name with their fates, whether a
fallback model answered and the calls before it; outcomes labelled in the game's unit."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from aiohttp.test_utils import TestClient, TestServer

from pilot.dashboard import make_app
from pilot.events import EventLog
from pilot.telemetry import Telemetry

CORPORA = Path(__file__).resolve().parents[1] / "corpora"


def civ6_run(tmp_path):
    runs = tmp_path / "runs"
    tel = Telemetry(runs / "telemetry.sqlite")
    log = EventLog(runs, "20260927-100000", "m", telemetry=tel)
    log.emit("run_start", game="civ6", model="google:gemini-3.8-flash")
    log.set_campaign("civ6", "kublai", "Kublai Khan, China")
    log.save_trace(1, {"episode": 1, "date": "T41", "trigger": "scheduled (5 turns)", "decision": "orders",
                       "reason": "Build a slinger.", "outcome": "production unit:slinger in Chengdu: stuck",
                       "model": "google:gemini-3.8-flash", "steps": [],
                       "orders": [{"order": "production unit:slinger in Chengdu", "outcome": "stuck", "kind": "production",
                                   "id": "unit:slinger", "city": "Chengdu"},
                                  {"order": "research tech:writing", "outcome": "stuck", "kind": "research",
                                   "id": "tech:writing", "city": ""},
                                  {"order": "purchase building:gurdwara in Beijing with faith",
                                   "outcome": "refused: 380 faith, over the 283 allowed", "kind": "purchase",
                                   "id": "building:gurdwara", "city": "Beijing"},
                                  {"order": "civic civic:foreign_trade (filled by the governor)",
                                   "outcome": "unknown: no reply (TimeoutError: timed out); civic civic:foreign_trade",
                                   "kind": "civic", "id": "civic:foreign_trade", "city": "", "by": "governor"}]})
    log.emit("order_outcome", order_kind="production", key="production replace", id="unit:slinger", city="Chengdu",
             ordered="T41", result="overridden", by="unit:trader", turns=2, date="T43", turn=43)
    log.emit("order_followed", ref="w1", row={"order_kind": "research", "key": "research", "id": "tech:writing", "city": "",
                                              "ordered": "T41", "ref": "w1"},
             order={"kind": "research", "id": "tech:writing"}, wire=None, expect={}, base={"turn": 41}, window=8)
    time.sleep(0.01)          # events are stamped to the millisecond: a model call comes after the last decision
    log.emit("model_retry", error="model gemini-3.8-flash answered 503", delay=5, attempt=1)
    log.emit("model_retry", error="model gemini-3.8-flash answered 503", delay=15, attempt=2)
    log.emit("model_fallback", role="decisions", model="google:gemini-3.8-flash",
             error="ModelHTTPError: status_code: 503, high demand", fallback="google:gemini-3.1-pro-preview")
    time.sleep(0.01)
    log.save_trace(2, {"episode": 2, "date": "T46", "decision": "orders", "reason": "Hold.", "outcome": "no orders",
                       "trigger": "urgent: great person race lost: GREAT_PERSON_CLASS_SCIENTIST; gold below the reserve: 12 < 30",
                       "model": "google:gemini-3.1-pro-preview", "steps": []})
    log.save_trace(3, {"episode": 3, "date": "T51", "trigger": "urgent: city threatened: Chengdu (2 enemy units near)",
                       "outcome": "error", "steps": [],
                       "error": "Error: Failed /tuner/lua\n\nCaused by:\n    0: operation timed out"})
    return runs, tel, log


def test_decisions_read_as_the_page_shows_them(tmp_path):
    runs, tel, log = civ6_run(tmp_path)

    async def go():
        async with TestClient(TestServer(make_app(None, runs, tel, corpora=CORPORA))) as c:
            rows = await (await c.get("/api/decisions?campaign=civ6/kublai")).json()
        first, second, third = rows
        assert first["trigger_label"]["text"] == "Scheduled" and not first["trigger_label"]["urgent"]
        fates = [(o["name"], o["city"], o["fate"]["key"], o["fate"]["word"], o["fate"]["why"]) for o in first["orders"]]
        assert fates == [("Slinger", "Chengdu", "replaced", "replaced by the AI", "the AI chose Trader"),
                         ("Writing", "", "open", "in force", ""),
                         ("Gurdwara", "Beijing", "refused", "refused", "380 faith, over the 283 allowed"),
                         ("Foreign Trade", "", "noreply", "no reply", "no answer in time (timed out)")]
        assert first["orders"][2]["currency"] == "faith" and first["orders"][3]["filled"] is True
        assert first["fallback"] is False
        assert second["trigger_label"]["text"] == "Great Scientist race lost, and 1 more"
        assert second["fallback"] is True
        assert second["attempts"] == [{"model": "google:gemini-3.8-flash", "cause": "overloaded (503)", "times": 3}]
        assert third["cause"] == "the game's tuner did not answer (timed out)"
        assert third["trigger_label"]["category"] == "city threatened"
    asyncio.run(go())
    log.close()


def test_one_decision_has_its_attempts_and_fates(tmp_path):
    runs, tel, log = civ6_run(tmp_path)

    async def go():
        async with TestClient(TestServer(make_app(None, runs, tel, corpora=CORPORA))) as c:
            d = await (await c.get("/api/decision?run=20260927-100000&episode=2")).json()
            assert d["fallback"] is True and d["attempts"][0]["times"] == 3
            d1 = await (await c.get("/api/decision?run=20260927-100000&episode=1")).json()
            assert d1["attempts"] == [] and d1["orders"][0]["fate"]["key"] == "replaced"
            assert d1["trace"]["orders"][0]["id"] == "unit:slinger"
    asyncio.run(go())
    log.close()


def test_outcome_scoring_labels_its_window_in_the_games_unit(tmp_path):
    runs = tmp_path / "runs"
    tel = Telemetry(runs / "telemetry.sqlite")
    tel.record("r", {"t": 1.0, "kind": "run_start", "game": "civ6", "model": "m"})
    tel.record("r", {"t": 2.0, "kind": "campaign", "game": "civ6", "name": "k"})
    for i, turn in enumerate(range(40, 56)):
        tel.record("r", {"t": 3.0 + i, "kind": "metrics", "date": f"T{turn}", "score": turn, "military": 500 - 10 * i})
    tel.record("r", {"t": 3.5, "kind": "trace", "episode": 1, "date": "T40", "decision": "orders"})
    assert tel.score("civ6/k") == 1
    res = tel.query("SELECT result FROM decisions")[0]["result"]
    assert '"unit": "turns"' in res and '"months": 12' in res and '"military": -120' in res


def test_a_directives_policy_report_reaches_the_page(tmp_path):
    """Stellaris levers ruling 3 / dashboard ruling 23: the policies a directive's reply reported set,
    locked and already in force ride along with its decision, taken from the action the governor
    follows for it (its `order_followed` event, as main's governor writes it); a decision with no
    directive applied has none."""
    from pilot.stellaris_record import directive_action, parse_directive_reply
    runs = tmp_path / "runs"
    tel = Telemetry(runs / "telemetry.sqlite")
    log = EventLog(runs, "20260927-120000", "m", telemetry=tel)
    log.emit("run_start", game="stellaris", model="m")
    log.set_campaign("stellaris", "gaea", "Blooms of Gaea")
    reply = ("Policies set: economic_policy=economic_policy_militarist. Policies locked (not set: the 10-year policy lock, a "
             "rule such as no stance change at war, or the option is not valid now): diplomatic_stance=diplo_stance_belligerent.")
    a = directive_action("defend", "2291.03.01", parse_directive_reply(reply))
    log.save_trace(1, {"episode": 1, "date": "2291.03.01", "decision": "defend", "outcome": "applied", "reason": "Hold.",
                       "steps": []})
    log.emit("order_followed", ref=a["ref"], action=a)
    log.save_trace(2, {"episode": 2, "date": "2292.03.01", "decision": "keep", "outcome": "kept", "reason": "Hold.", "steps": []})
    want = {"set": {"economic_policy": "economic_policy_militarist"},
            "locked": {"diplomatic_stance": "diplo_stance_belligerent"}, "in_force": {}}

    async def go():
        async with TestClient(TestServer(make_app(None, runs, tel, corpora=CORPORA))) as c:
            rows = await (await c.get("/api/decisions?campaign=stellaris/gaea")).json()
            assert rows[0]["applied"] == want and rows[1]["applied"] is None
            d = await (await c.get("/api/decision?run=20260927-120000&episode=1")).json()
            assert d["applied"] == want                                   # Reasoning has it too
    asyncio.run(go())
    log.close()


def test_an_order_is_in_force_only_while_the_record_follows_it(tmp_path):
    """Traces from before the order record have no follow-up rows: their stuck orders took but were not
    followed, and must not read "in force" for ever (about 100 of them on the live campaign); an order
    the record still follows is in force, and one it resolved has its result."""
    runs, tel, log = civ6_run(tmp_path)
    log.save_trace(4, {"episode": 4, "date": "T56", "decision": "orders", "reason": "Pottery.", "outcome": "stuck",
                       "steps": [], "orders": [{"order": "research tech:pottery", "outcome": "stuck"},
                                               {"order": "civic civic:code_of_laws", "outcome": "stuck", "kind": "civic",
                                                "id": "civic:code_of_laws", "city": ""}]})

    async def go():
        async with TestClient(TestServer(make_app(None, runs, tel, corpora=CORPORA))) as c:
            return await (await c.get("/api/decisions?campaign=civ6/kublai")).json()
    rows = asyncio.run(go())
    old = [(o["name"], o["fate"]["key"], o["fate"]["word"]) for o in rows[-1]["orders"]]
    assert old == [("Pottery", "held", "took, not followed"), ("Code of Laws", "held", "took, not followed")]
    assert ("Writing", "open", "in force") in [(o["name"], o["fate"]["key"], o["fate"]["word"]) for o in rows[0]["orders"]]
    log.emit("order_outcome", order_kind="research", key="research", id="tech:writing", city="", ordered="T41",
             result="completed", turns=3, date="T44", turn=44, ref="w1")
    rows = asyncio.run(go())
    assert ("Writing", "held", "completed") in [(o["name"], o["fate"]["key"], o["fate"]["word"]) for o in rows[0]["orders"]]
    log.close()
