"""Stellaris market buy rules (docs/design/2026-09-27-stellaris-levers-design.md, rulings 9-10): the price
model, the 2,500 trade reserve, the spend cap, the price guard, the volume cap, never buying what the
AI buys anyway, and the idle-trade fill."""

import pytest

from pilot.config import REPO
from pilot.pillars import load_pillars
from pilot.stellaris_market import PRICE_UNKNOWN, buy_errors, idle_fill, naval_use, price_note, unit_price, volume_cap

LIMITS = load_pillars(REPO / "corpora/stellaris").actions["market"]
RULES = LIMITS.buy
MEASURED = {"energy", "minerals", "food", "consumer_goods", "volatile_motes", "exotic_gases", "rare_crystals"}


def empire(trade=20000.0, trade_net=100.0, stock=None, net=None, fluct=None, kind="galactic", bought=None,
           trades=None, **extra) -> dict:
    """A briefing with a market block: trade 20,000 (+100 a month) unless told otherwise."""
    return {"date": "2250.01.01", "stockpile": {"trade": trade, **(stock or {})},
            "net": {"trade": trade_net, **(net or {})},
            "market": {"kind": kind, "fluct": dict(fluct or {}), "bought": dict(bought or {}), "sold": {},
                       "trades_net": dict(trades or {})}, **extra}


def buy(res: str, amount: int) -> dict:
    return {"side": "buy", "resource": res, "amount": amount}


def test_the_price_is_base_times_the_fluctuation_times_the_fee():
    price, known = unit_price("alloys", empire(fluct={"alloys": 50}), RULES)
    assert price == pytest.approx(4 * 1.5 * 1.3) and known
    assert unit_price("sr_zro", empire(), RULES)[0] == pytest.approx(20 * 1.3)
    assert unit_price("energy", {"date": "2250.01.01"}, RULES) == (pytest.approx(1.3), False), \
        "no market block: the fluctuation is taken as 0 and the price is unknown"


def test_a_save_without_a_market_block_says_price_unknown():
    assert price_note(empire()) == "" and price_note({"date": "2250.01.01"}) == PRICE_UNKNOWN
    assert PRICE_UNKNOWN.startswith("price unknown")
    bare = {"date": "2250.01.01", "stockpile": {"trade": 20000.0, "minerals": 300}, "net": {"trade": 100.0, "minerals": -20.0}}
    assert buy_errors(buy("minerals", 10), bare, None, RULES, set()) == [], "not refused: checked at the base price"


def test_the_reserve_keeps_2500_trade():
    # trade 3,000 and a cost 60 over the monthly trade income: 3,000 - 12 x 60 = 2,280 < 2,500
    poor = empire(trade=3000, trade_net=5)
    errs = buy_errors(buy("consumer_goods", 25), poor, None, RULES, set())      # 25 x 2.6 = 65 trade a month
    assert any("reserve" in e and "2500" in e for e in errs), errs
    assert buy_errors(buy("consumer_goods", 25), empire(), None, RULES, set()) == []


def test_the_spend_cap_and_its_crisis_share_for_alloys():
    at_reserve = empire(trade=2500, trade_net=100)          # cap = 0.25 x 100 + 0 surplus = 25 trade a month
    alloys = buy("alloys", 8)                                # 8 x 5.2 = 41.6
    assert any("spend cap" in e for e in buy_errors(alloys, at_reserve, None, RULES, set()))
    assert buy_errors(alloys, at_reserve, None, RULES, set(), crisis=True) == [], "0.5 of the income in a crisis"
    goods = buy("consumer_goods", 16)                        # 16 x 2.6 = 41.6: the crisis share is for alloys only
    assert any("spend cap" in e for e in buy_errors(goods, at_reserve, None, RULES, set(), crisis=True))
    surplus = empire(trade=2500 + 24 * 20, trade_net=100)   # a surplus spent over 24 months adds 20
    assert buy_errors(buy("alloys", 8), surplus, None, RULES, set()) == []


def test_the_price_guard_skips_above_50_and_never_buys_above_100():
    at = lambda pct: empire(fluct={"minerals": pct})
    assert buy_errors(buy("minerals", 10), at(49), None, RULES, set()) == []
    assert any("+51%" in e and "50%" in e for e in buy_errors(buy("minerals", 10), at(51), None, RULES, set()))
    assert buy_errors(buy("minerals", 10), at(80), None, RULES, set(), placed=10) == [], \
        "an order already placed is kept while the price stays at +100% or less"
    assert any("100%" in e for e in buy_errors(buy("minerals", 10), at(101), None, RULES, set(), placed=10))


def test_the_price_guard_counts_a_raise_as_a_new_order():
    """The +100% allowance covers the amount already in the save; buying more above +50% is a new order."""
    at80 = empire(fluct={"minerals": 80})
    errs = buy_errors(buy("minerals", 25), at80, None, RULES, set(), placed=5)
    assert any("no raise above +50%" in e and "5 in place" in e for e in errs), errs
    assert buy_errors(buy("minerals", 25), at80, None, RULES, set(), placed=25) == []
    assert buy_errors(buy("minerals", 5), at80, None, RULES, set(), placed=25) == [], "a smaller order is no new buy"
    b = empire(stock={"minerals": 300}, net={"minerals": -20.0}, fluct={"minerals": 80})
    assert idle_fill(b, None, LIMITS, {"trade"}, MEASURED, placed=lambda o: 10)[0] == buy("minerals", 10), \
        "the fill in place stays at its amount rather than growing to 24 at +80%"
    assert idle_fill(b, None, LIMITS, {"trade"}, MEASURED, placed=lambda o: 0)[0] is None


def test_the_volume_cap_is_one_base_amount_internal_and_six_galactic():
    assert [volume_cap(r, empire(kind="internal"), RULES) for r in ("alloys", "consumer_goods", "rare_crystals")] == [25, 50, 10]
    assert [volume_cap(r, empire(kind="galactic"), RULES) for r in ("alloys", "consumer_goods", "rare_crystals")] == [150, 300, 60]
    assert volume_cap("rare_crystals", {"date": "2250.01.01"}, RULES) == 10, "unknown market: the internal cap"
    errs = buy_errors(buy("rare_crystals", 12), empire(kind="internal"), None, RULES, set())
    assert any("volume" in e and "10" in e for e in errs), errs
    assert buy_errors(buy("rare_crystals", 12), empire(kind="galactic"), None, RULES, set()) == []


def test_what_the_ai_buys_anyway_is_never_bought():
    short = empire(stock={"minerals": 50}, net={"minerals": -10})           # 5 months of cover: the AI buys
    assert any("the AI buys" in e for e in buy_errors(buy("minerals", 10), short, None, RULES, set()))
    before = empire(bought={"minerals": 100})
    after = empire(bought={"minerals": 1100})
    assert any("bought" in e for e in buy_errors(buy("minerals", 10), after, before, RULES, set()))
    ours = empire(bought={"minerals": 110}, trades={"minerals": 10, "trade": -13})
    assert buy_errors(buy("minerals", 10), ours, before, RULES, set()) == [], "our own monthly trade is not the AI's"
    assert any("IDLE" in e for e in buy_errors(buy("minerals", 10), empire(), None, RULES, {"minerals"}))
    full = empire(governor_vars={"governor_naval_cap": 100, "governor_naval_used": 96}, used_naval_capacity=96)
    assert naval_use(full) == pytest.approx(0.96)
    assert any("naval capacity" in e for e in buy_errors(buy("alloys", 5), full, None, RULES, set()))
    assert not any("naval capacity" in e for e in buy_errors(buy("alloys", 5), full, None, RULES, set(), crisis=True))
    stale = {**full, "governor_vars_stale": True}
    assert naval_use(stale) is None and buy_errors(buy("alloys", 5), stale, None, RULES, set()) == []


def test_the_idle_trade_fill_buys_deficit_cover():
    b = empire(stock={"minerals": 300, "consumer_goods": 30, "food": 1000},
               net={"minerals": -20.0, "consumer_goods": -10.0, "food": -1.0})
    order, why = idle_fill(b, None, LIMITS, {"trade"}, MEASURED)
    assert order == buy("minerals", 24) and why == "", "1.2 x the deficit; goods (3 months) and food (1000) are not due"
    deep = empire(stock={"minerals": 600}, net={"minerals": -30.0})
    assert idle_fill(deep, None, LIMITS, {"trade"}, MEASURED)[0] == buy("minerals", 25), "at most amount_max"
    crystals = empire(kind="internal", stock={"rare_crystals": 300}, net={"rare_crystals": -10.0})   # 30 months
    assert idle_fill(crystals, None, LIMITS, {"trade"}, MEASURED)[0] == buy("rare_crystals", 10), \
        "36 months for strategic resources, at most one base amount on the internal market"


def test_the_idle_trade_fill_buys_nothing_and_says_why():
    order, why = idle_fill(empire(), None, LIMITS, {"trade"}, MEASURED)
    assert order is None and "no resource in deficit" in why
    pricey = empire(stock={"minerals": 300}, net={"minerals": -20.0}, fluct={"minerals": 60})
    order, why = idle_fill(pricey, None, LIMITS, {"trade"}, MEASURED)
    assert order is None and "minerals" in why and "+60%" in why


def test_alloys_and_sr_are_not_filled_until_their_start_amount_is_measured():
    b = empire(stock={"alloys": 300, "sr_zro": 30}, net={"alloys": -30.0, "sr_zro": -2.0})
    order, why = idle_fill(b, None, LIMITS, {"trade"}, MEASURED)
    assert order is None and "alloys" in why and "not measured" in why
    assert idle_fill(b, None, LIMITS, {"trade"}, MEASURED | {"alloys"})[0] == buy("alloys", 25)


def test_the_idle_trade_fill_in_a_war_crisis_gets_the_crisis_rules():
    full = {"governor_vars": {"governor_naval_cap": 100, "governor_naval_used": 96}, "used_naval_capacity": 96}
    b = empire(stock={"alloys": 300}, net={"alloys": -30.0}, **full)
    assert idle_fill(b, None, LIMITS, {"trade"}, MEASURED | {"alloys"})[0] is None, "alloys wait for naval room"
    assert idle_fill(b, None, LIMITS, {"trade"}, MEASURED | {"alloys"}, crisis=True)[0] == buy("alloys", 25)


def test_a_suspended_resource_is_not_filled():
    b = empire(stock={"minerals": 300, "food": 300}, net={"minerals": -20.0, "food": -20.0})
    blocked = lambda side, res: "suspended" if res == "minerals" else None
    assert idle_fill(b, None, LIMITS, {"trade"}, MEASURED, blocked)[0] == buy("food", 24)
