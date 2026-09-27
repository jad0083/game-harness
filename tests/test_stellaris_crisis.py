"""The war crisis overlay (docs/design/2026-09-27-stellaris-levers-design.md, rulings 12-16): entry on
losses at war (C1-C6), never on ratios, battle counts or exhaustion; exit on peace or after 6 quiet
saves held 6 months; at most one entry per war per 12 months; the status-quo question."""

import json

from pilot.config import REPO
from pilot.pillars import load_pillars
from pilot.stellaris_crisis import crisis_alloys, crisis_step, status_quo, war_crisis

WAR = {"id": "50331650", "name": "Khell Zen vs Theia", "our_exhaustion": 0.2, "their_exhaustion": 0.3,
       "battle_count": 10, "battles_won": 0, "battles_lost": 10,
       "own_battles_12m": {"won": 0, "lost": 3, "ships_lost": 12, "ground_at_our_colonies": 0, "invasions": []}}


def empire(date, systems=30, military=1000.0, planets=9, wars=(WAR,), occupied=(), **extra) -> dict:
    colonies = [{"id": i, "name": f"P{i}", "occupied": f"P{i}" in occupied, "occupier": "Khell Zen"} for i in range(planets)]
    return {"date": date, "systems": systems, "military_power": military, "planets": colonies,
            "wars": [dict(w) for w in wars], **extra}


def row(date, systems=30, military=1000.0, planets=9, wars=1) -> dict:
    return {"date": date, "systems": systems, "military_power": military, "planets": planets, "wars": wars}


YEAR = [row(f"2255.{m:02d}.01") for m in range(1, 13)]


def codes(conds):
    return [c for c, _ in conds]


def test_each_entry_condition():
    prev = empire("2255.12.01")
    assert codes(war_crisis(YEAR, empire("2256.01.01", occupied=("P3",)), prev)) == ["C1"]
    assert codes(war_crisis(YEAR, empire("2256.01.01", systems=28), prev)) == ["C2"]
    assert codes(war_crisis(YEAR, empire("2256.01.01", systems=29), prev)) == [], "one system is not two"
    assert codes(war_crisis(YEAR, empire("2256.01.01", military=500), prev)) == ["C3"]
    assert codes(war_crisis(YEAR, empire("2256.01.01", military=0), prev)) == ["C3"], "0 is a fall to half"
    assert codes(war_crisis(YEAR, empire("2256.01.01", planets=8), prev)) == ["C4"]
    invaded = {**WAR, "battle_count": 12, "own_battles_12m": {**WAR["own_battles_12m"], "ground_at_our_colonies": 1,
                                                               "invasions": [11]}}
    assert codes(war_crisis(YEAR, empire("2256.01.01", wars=(invaded,)), prev)) == ["C5"]
    assert codes(war_crisis(YEAR, empire("2256.01.01", occupied=("P3",)), prev, ["Arnvoss"])) == ["C1", "C6"]
    texts = dict(war_crisis(YEAR, empire("2256.01.01", systems=27, military=300), prev))
    assert texts["C2"] == "systems 27 (30 at most in 12 months)" and texts["C3"] == "military 300 (1000 at most in 12 months)"


def test_an_old_invasion_counted_again_after_a_retake_is_not_new():
    before = {**WAR, "battle_count": 130, "own_battles_12m": {**WAR["own_battles_12m"], "ground_at_our_colonies": 1,
                                                               "invasions": [125]}}
    again = {**before, "battle_count": 131, "own_battles_12m": {**before["own_battles_12m"], "ground_at_our_colonies": 2,
                                                                 "invasions": [125, 125]}}
    assert war_crisis(YEAR, empire("2256.01.01", wars=(again,)), empire("2255.12.01", wars=(before,))) == []
    assert war_crisis(YEAR, empire("2256.01.01", wars=(again,)), None) == [], "no earlier save: nothing to tell"


def test_no_entry_on_ratios_battles_or_exhaustion_alone():
    beaten = {**WAR, "our_exhaustion": 0.95, "their_exhaustion": 0.1, "battles_lost": 233}
    weak = empire("2256.01.01", wars=(beaten,), military=1000, neighbours=[{"name": "Khell Zen", "military": 90000}])
    assert war_crisis(YEAR, weak, empire("2255.12.01")) == []


def test_only_at_war():
    assert war_crisis(YEAR, empire("2256.01.01", systems=20, wars=()), empire("2255.12.01")) == []


def run(saves, rows=(), low=None):
    state, events, prev, rows = None, [], None, list(rows)
    for b in saves:
        state, ev = crisis_step(state, rows, b, prev, (low or {}).get(b["date"], []))
        events.append((b["date"], ev))
        rows.append(row(b["date"], b["systems"], b["military_power"], len(b["planets"]), len(b["wars"])))
        prev = b
    return state, [e for e in events if e[1]]


def test_the_crisis_enters_on_the_transition_and_leaves_after_6_quiet_saves_held_6_months():
    saves = [empire("2256.01.01", systems=27)] + [empire(f"2256.{m:02d}.01", systems=27) for m in range(2, 4)] \
        + [empire(f"2256.{m:02d}.01", systems=30) for m in range(4, 13)]
    state, events = run(saves, YEAR)
    assert events[0] == ("2256.01.01", "enter"), "transition only: the next saves do not enter again"
    assert events[1][0] == "2256.09.01" and events[1][1].startswith("exit"), events
    assert not state["active"] and "6 quiet saves" in events[1][1]


def test_a_save_already_counted_changes_nothing():
    """Each save counts once (ruling 14's 6 quiet saves): a restart re-reads the save the last run saw,
    without the save before it (prev None), and an older save may be loaded; neither changes the state."""
    saves = [empire("2256.01.01", systems=27)] + [empire(f"2256.{m:02d}.01") for m in range(2, 5)]
    state, _ = run(saves, YEAR)
    assert state["active"] and state["quiet"] == 3 and state["seen"] == "2256.04.01"
    assert crisis_step(state, YEAR, saves[-1], None) == (state, None), "the same save again"
    assert crisis_step(state, YEAR, saves[1], None) == (state, None), "an older save"
    lost = empire("2256.05.01", planets=8)                       # C4 against the save before
    after, ev = crisis_step(state, YEAR, lost, saves[-1])
    assert ev is None and after["quiet"] == 0 and codes(after["conditions"]) == ["C4"]
    assert crisis_step(after, YEAR, lost, None) == (after, None), "without the save before, C4 is not quiet"
    newer, _ = crisis_step(after, YEAR, empire("2256.06.01", planets=8), lost)
    assert newer["quiet"] == 1 and newer["seen"] == "2256.06.01"


def test_peace_ends_the_crisis_at_once():
    _, events = run([empire("2256.01.01", systems=27), empire("2256.02.01", systems=27, wars=())], YEAR)
    assert events == [("2256.01.01", "enter"), ("2256.02.01", "exit: every war ended")]


def test_at_most_one_entry_per_war_per_12_months():
    saves = [empire("2256.01.01", systems=27)] + [empire(f"2256.{m:02d}.01", systems=27, wars=()) for m in (2,)] \
        + [empire("2256.03.01", systems=27)]
    _, events = run(saves, YEAR)
    assert [e for _, e in events] == ["enter", "exit: every war ended"], "the same war within 12 months"
    other = {**WAR, "id": "99", "name": "Another war"}
    _, events = run(saves[:2] + [empire("2256.03.01", systems=27, wars=(other,))], YEAR)
    assert [e for _, e in events] == ["enter", "exit: every war ended", "enter"], "a new war may enter"


def test_the_theia_collapse_enters_at_2256_08():
    """E8: replayed on Theia's metrics rows, the first collapse enters at 2256.08, 7 months before the
    capital fell (2257.03)."""
    rows = json.loads((REPO / "tests/fixtures/stellaris_theia_2254_2263.json").read_text(encoding="utf-8"))["rows"]
    saves = [empire(r["date"], r["systems"], r["military_power"], r["planets"], wars=(WAR,) * r["wars"]) for r in rows]
    _, events = run(saves)
    assert events[0] == ("2256.08.01", "enter"), events[:3]


def test_the_status_quo_question_names_losses_exhaustion_and_occupation():
    b = empire("2256.03.01", systems=27, occupied=("P2",))
    [(war, q)] = status_quo(b, YEAR, war_crisis(YEAR, b, empire("2256.02.01")))
    assert war == WAR["id"]
    assert "Systems 30 -> 27" in q and "ours 20%, theirs 30%" in q and "P2" in q and "never proposes peace" in q
    tired = empire("2256.03.01", wars=({**WAR, "our_exhaustion": 0.7, "their_exhaustion": 0.5},))
    assert status_quo(tired, YEAR, []) != [], "exhaustion 0.6 or more and at least theirs"
    forced = empire("2256.03.01", wars=({**WAR, "force_peace": {"ours": True, "theirs": False, "date": "2256.02.11"}},))
    assert status_quo(forced, YEAR, []) != []
    assert status_quo(empire("2256.03.01", military=400), YEAR, [("C3", "military 400")]) == [], \
        "a military fall alone asks nothing"


LIMITS = load_pillars(REPO / "corpora/stellaris").actions["market"]
MEASURED = {"energy", "minerals", "food", "consumer_goods", "alloys"}


def at_war(**extra) -> dict:
    b = {"date": "2256.01.01", "stockpile": {"trade": 20000.0, "alloys": 300.0}, "net": {"trade": 100.0, "alloys": 20.0},
         "market": {"kind": "galactic", "fluct": {}, "bought": {}, "sold": {}, "trades_net": {}},
         "shipyards": [{"system": "Titawin", "occupied": False}], "wars": [WAR]}
    b.update(extra)
    return b


def test_crisis_alloys_are_bought_only_through_every_gate():
    order, why = crisis_alloys(at_war(), None, LIMITS, set(), MEASURED)
    assert order == {"side": "buy", "resource": "alloys", "amount": 25} and why == ""
    assert "start amount not measured" in crisis_alloys(at_war(), None, LIMITS, set(), MEASURED - {"alloys"})[1]
    assert "no shipyard" in crisis_alloys(at_war(shipyards=[{"system": "Theia", "occupied": True}]), None, LIMITS,
                                          set(), MEASURED)[1], "Theia 2257-2265: the only shipyard occupied"
    full = at_war(governor_vars={"governor_naval_cap": 100, "governor_naval_used": 96}, used_naval_capacity=96)
    assert "naval capacity" in crisis_alloys(full, None, LIMITS, set(), MEASURED)[1]
    rich = at_war(stockpile={"trade": 20000.0, "alloys": 1500.0})
    assert "naval use unknown" in crisis_alloys(rich, None, LIMITS, set(), MEASURED)[1]
    assert "IDLE" in crisis_alloys(at_war(), None, LIMITS, {"alloys"}, MEASURED)[1]
    poor = at_war(stockpile={"trade": 2600.0, "alloys": 300.0}, net={"trade": 20.0, "alloys": 20.0})
    order, _ = crisis_alloys(poor, None, LIMITS, set(), MEASURED)
    assert order["amount"] == 2, "sized to the crisis cap: 0.5 x 20 + 100 / 24 = 14.2 trade, 5.2 a unit"
    assert crisis_alloys(at_war(stockpile={"trade": 2400.0, "alloys": 300.0}), None, LIMITS, set(), MEASURED)[0] is None
    pricey = at_war(market={"kind": "galactic", "fluct": {"alloys": 120}, "bought": {}, "sold": {}, "trades_net": {}})
    assert "100%" in crisis_alloys(pricey, None, LIMITS, set(), MEASURED)[1]


def test_crisis_alloys_already_placed_are_kept_up_to_plus_100():
    """Like any buy in place (ruling 9's price guard): a crisis order is dropped only above +100%."""
    dear = at_war(market={"kind": "galactic", "fluct": {"alloys": 70}, "bought": {}, "sold": {}, "trades_net": {}})
    assert crisis_alloys(dear, None, LIMITS, set(), MEASURED)[0] is None, "no new order above +50%"
    assert crisis_alloys(dear, None, LIMITS, set(), MEASURED, placed=25)[0] == {"side": "buy", "resource": "alloys", "amount": 25}


def test_crisis_alloys_in_place_are_not_raised_above_plus_50():
    """A larger order is a new buy: above +50% the order in place stays at its amount (ruling 9)."""
    dear = at_war(market={"kind": "galactic", "fluct": {"alloys": 80}, "bought": {}, "sold": {}, "trades_net": {}})
    assert crisis_alloys(dear, None, LIMITS, set(), MEASURED, placed=1)[0] == {"side": "buy", "resource": "alloys", "amount": 1}
    cheap = at_war(market={"kind": "galactic", "fluct": {"alloys": 30}, "bought": {}, "sold": {}, "trades_net": {}})
    assert crisis_alloys(cheap, None, LIMITS, set(), MEASURED, placed=1)[0]["amount"] == 25, "at +30% it may grow"
