"""Each game's dashboard view (corpora/<game>/dashboard.toml, GET /api/view) and readable names for
game ids (docs/design/2026-09-27-dashboard-v2-design.md, rulings 2, 3, 29 and 30)."""

from __future__ import annotations

import asyncio
import re
import tomllib
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

from pilot import civ6, governor, telemetry
from pilot.dashboard import make_app
from pilot.events import EventLog
from pilot.telemetry import Telemetry
from pilot.view import CATEGORIES, Names, fallback_name, load_view

CORPORA = Path(__file__).resolve().parents[1] / "corpora"
GAMES = sorted(p.parent.name for p in CORPORA.glob("*/dashboard.toml"))
RESERVE_KEYS = {"gold_keep", "faith_keep"}        # info.reserves fields a figure may name as `keep`


def sample_row(game: str) -> dict:
    """A metrics row as the game's governor writes it, with one rival."""
    if game == "civ6":
        return civ6.metrics({"turn": 50, "cities": [{"name": "Beijing", "pop": 3}],
                             "majors": [{"civ": "CIVILIZATION_GERMANY", "score": 40, "military": 90, "cities": 2,
                                         "at_war": False}]})
    if game == "stellaris":
        return governor.metrics({"date": "2288.01.01", "neighbours": [{"name": "Theian Union"}]})
    return {}


def known_keys(game: str) -> tuple[set[str], dict]:
    """Metric keys a view may name: the pillars file's [metrics] names (mapped to row keys) and the
    fields of the game's metrics rows."""
    row = sample_row(game)
    keys = set(row)
    pillars = CORPORA / game / "pillars.toml"
    if pillars.exists():
        m = tomllib.loads(pillars.read_text(encoding="utf-8"))["metrics"]
        keys |= {m.get("row_keys", {}).get(n, n) for n in m["names"]}
    return keys, row


def is_known(key: str, keys: set[str], row: dict) -> bool:
    if "." in key:                                   # net.energy: a nested per-resource figure
        head, tail = key.split(".", 1)
        return isinstance(row.get(head), dict) and re.fullmatch(r"[a-z_]+", tail) is not None
    return key in keys


def test_every_game_view_is_valid():
    assert {"civ6", "stellaris", "galciv4"} <= set(GAMES)
    for game in GAMES:
        view = load_view(CORPORA, game)
        assert view["known"] and view["error"] == "", (game, view["error"])


@pytest.mark.parametrize("game", GAMES)
def test_view_metric_keys_are_known_metrics(game):
    view = load_view(CORPORA, game)
    keys, row = known_keys(game)
    rival = (row.get("neighbours") or [{}])[0]
    named = [f["key"] for f in view["figures"] if f["kind"] in ("value", "rank")]
    named += [f["rank"] for f in view["figures"] if f["rank"]]
    named += [s for c in view["chart"] for s in c["series"]]
    named += (view["outcomes"] or {}).get("keys", []) + list((view["outcomes"] or {}).get("watch", {}))
    named += [c["ours"] for c in (view["rivals"] or {}).get("columns", []) if c["ours"]]
    assert [k for k in named if not is_known(k, keys, row)] == []
    for f in view["figures"]:
        assert set(re.findall(r"\{(\w+)\}", f["sub"])) <= set(row), f
        assert not f["keep"] or f["keep"] in RESERVE_KEYS, f
    assert [c["key"] for c in (view["rivals"] or {}).get("columns", []) if c["key"] not in rival] == []
    assert set((view["outcomes"] or {}).get("keys", [])) <= set(telemetry.SCORED)
    assert set(view["recovery"]) <= set(CATEGORIES)
    assert all(label for label in view["labels"].values())


def test_a_missing_or_broken_view_falls_back_and_says_why(tmp_path):
    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "dashboard.toml").write_text('[game]\nname = "X"\ntime_unit = "year"\n')
    view = load_view(tmp_path, "broken")
    assert not view["known"] and "time_unit" in view["error"]
    assert view["figures"] == [] and view["chart"] == [] and view["rivals"] is None
    assert load_view(tmp_path, "nothing")["error"] == ""
    assert load_view(tmp_path, "../etc")["id"] == "../etc" and not load_view(tmp_path, "../etc")["known"]


def test_names_come_from_the_corpus_with_a_readable_fallback():
    names = Names(CORPORA)
    assert names.name("civ6", "CIVILIZATION_GERMANY") == "Germany"
    assert names.name("civ6", "BUILDING_GURDWARA") == "Gurdwara"
    assert names.name("civ6", "unit:trader") == "Trader"
    assert names.name("civ6", "UNIT_SLINGER") == "Slinger"
    assert names.name("civ6", "GREAT_PERSON_CLASS_SCIENTIST") == "Great Scientist"
    assert names.name("civ6", "Chengdu") == "Chengdu" and names.name("stellaris", "Theian Union") == "Theian Union"
    assert names.name("civ6", 12) == 12
    assert fallback_name("DISTRICT_COMMERCIAL_HUB") == "Commercial Hub"
    assert fallback_name("unit:war_cart") == "War Cart"
    assert names.names("civ6", ["unit:trader", "Chengdu", "CIVILIZATION_GERMANY"]) == {
        "unit:trader": "Trader", "CIVILIZATION_GERMANY": "Germany"}


def _civ6_campaign(tmp_path):
    runs = tmp_path / "runs"
    tel = Telemetry(runs / "telemetry.sqlite")
    log = EventLog(runs, "20260927-100000", "m", telemetry=tel)
    log.emit("run_start", game="civ6", model="m")
    log.set_campaign("civ6", "kublai", "Kublai Khan, China")
    log.emit("metrics", date="T50", score=90, neighbours=[{"name": "CIVILIZATION_GERMANY", "military": 90, "score": 40,
                                                            "cities": 2, "at_war": True}])
    log.emit("strategy", date="T50", trigger="start of run", model="m", reason="r",
             strategy={"focus": "science", "pillars": {"economy": {"weight": 30, "prefer_production": ["unit:trader"]}}})
    return runs, tel, log


def test_api_view_speaks_for_the_campaigns_game(tmp_path):
    runs, tel, log = _civ6_campaign(tmp_path)

    async def go():
        async with TestClient(TestServer(make_app(None, runs, tel, corpora=CORPORA))) as c:
            civ = await (await c.get("/api/view?campaign=civ6/kublai")).json()
            assert civ["id"] == "civ6" and civ["game"]["time_unit"] == "turn" and civ["game"]["levers_label"] == "Orders"
            assert [f["key"] for f in civ["figures"]][:2] == ["rank:score", "rank:military"]
            st = await (await c.get("/api/view?game=stellaris")).json()
            assert st["game"]["cadence"] == "every_months" and st["rivals"]["label"] == "Neighbours"
            unknown = await (await c.get("/api/view?game=nothing_here")).json()
            assert unknown["known"] is False and unknown["figures"] == []
            bad = await c.get("/api/view?game=../x")
            assert bad.status == 200 and (await bad.json())["known"] is False
    asyncio.run(go())
    log.close()


def test_api_view_of_the_live_run_without_a_campaign(tmp_path):
    runs, tel, log = _civ6_campaign(tmp_path)

    class P:
        pass
    pilot = P()
    pilot.log = log

    async def go():
        async with TestClient(TestServer(make_app(pilot, runs, tel, corpora=CORPORA))) as c:
            assert (await (await c.get("/api/view")).json())["id"] == "civ6"
    asyncio.run(go())
    log.close()


def test_apis_return_names_next_to_ids(tmp_path):
    runs, tel, log = _civ6_campaign(tmp_path)

    async def go():
        async with TestClient(TestServer(make_app(None, runs, tel, corpora=CORPORA))) as c:
            rows = await (await c.get("/api/metrics?campaign=civ6/kublai")).json()
            nb = rows[0]["neighbours"][0]
            assert nb["name"] == "Germany" and nb["id"] == "CIVILIZATION_GERMANY"
            strat = await (await c.get("/api/strategy?campaign=civ6/kublai")).json()
            assert strat["names"]["unit:trader"] == "Trader"
    asyncio.run(go())
    log.close()


def test_api_strategy_lists_the_latest_review_results(tmp_path):
    runs, tel, log = _civ6_campaign(tmp_path)
    log.emit("strategy_review", date="T52", trigger="war", change="science up", accepted=True, assessment="a")
    log.emit("strategy_review_skipped", trigger="city lost", reason="within 12 months of the last event review",
             date="T55", next_after=64)

    async def go():
        async with TestClient(TestServer(make_app(None, runs, tel, corpora=CORPORA))) as c:
            strat = await (await c.get("/api/strategy?campaign=civ6/kublai")).json()
            assert [(r["kind"], r.get("next_after")) for r in strat["reviews"]] == [
                ("strategy_review_skipped", 64), ("strategy_review", None)]
    asyncio.run(go())
    log.close()
