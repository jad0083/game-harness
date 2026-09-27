"""The Stellaris action record (docs/design/2026-09-27-stellaris-levers-design.md, rulings 2-6): every
directive, tech pick, market order and posture is followed in the saves until it resolves."""

from pilot.config import REPO
from pilot.pillars import load_pillars
from pilot.stellaris_record import (
    action_record,
    action_record_text,
    directive_action,
    judge,
    market_action,
    market_suspended,
    outcome_row,
    parse_directive_reply,
    posture_action,
    review_outcome,
    supersede,
    tech_action,
)

SPEC = load_pillars(REPO / "corpora/stellaris").orders
CAP, GRACE = SPEC.open_cap_turns, SPEC.open_grace_turns

# the controller's reply (mcp.rs stellaris_directive, stellaris.rs Applied::summary)
LOCKED = ("Policies locked (not set: the 10-year policy lock, a rule such as no stance change at war, or the "
          "option is not valid now)")
CIVILIAN = (f"Directive tech_rush applied and confirmed in game.log. Policies set: "
            f"economic_policy=economic_policy_civilian. {LOCKED}: none.\nConsole lines:\n"
            "effect remove_country_flag = governor_directive_expand\n"
            "effect set_country_flag = governor_posture_research_focus remove_country_flag = governor_posture_naval_cap\n"
            "The next monthly autosave will list governor_directive_tech_rush under Governor flags.")


def save(date: str, flags=("governor_directive_tech_rush",), policies=None, dates=None, **kw) -> dict:
    return {"date": date, "flags": list(flags), "policies": policies or {"economic_policy": "economic_policy_civilian"},
            "policy_dates": dates or {"economic_policy": "2271.12.01"}, **kw}


def test_the_reply_names_what_the_game_set_what_was_locked_and_the_postures_set():
    info = parse_directive_reply(CIVILIAN)
    assert info == {"set": {"economic_policy": "economic_policy_civilian"}, "in_force": {}, "locked": {},
                    "reported": True, "postures": ["research_focus"]}
    both = parse_directive_reply(
        "Directive defend applied and confirmed in game.log. Policies set: none. Already in force (not set again, so "
        f"its 10-year lock is not restarted): economic_policy=economic_policy_military. {LOCKED}: "
        "diplomatic_stance=diplo_stance_belligerent, first_contact_protocol=first_contact_proactive.\nConsole lines:\n")
    assert both["set"] == {} and both["in_force"] == {"economic_policy": "economic_policy_military"}
    assert both["locked"] == {"diplomatic_stance": "diplo_stance_belligerent",
                              "first_contact_protocol": "first_contact_proactive"}
    assert parse_directive_reply("Directive expand applied")["reported"] is False, "an older controller: nothing known"


def test_a_directive_whose_policy_the_ai_reverts_is_overridden_with_the_option_and_date():
    a = directive_action("tech_rush", "2271.12.01", parse_directive_reply(CIVILIAN))
    assert a["key"] == "directive tech_rush" and a["id"] == "tech_rush"
    assert judge(a, save("2271.12.01"), CAP, GRACE)[0] == "open", "never judged on the save it was applied on"
    assert judge(a, save("2272.01.01"), CAP, GRACE)[0] == "open" and a["state"] == "took"
    reverted = save("2272.05.01", policies={"economic_policy": "economic_policy_balanced"},
                    dates={"economic_policy": "2272.01.01"})
    assert judge(a, reverted, CAP, GRACE) == ("overridden", "economic_policy_balanced",
                                               "economic_policy → economic_policy_balanced on 2272.01.01")


def test_a_directive_without_its_flag_failed_and_one_whose_policies_were_all_locked_is_locked():
    a = directive_action("tech_rush", "2271.12.01", parse_directive_reply(CIVILIAN))
    result, _, detail = judge(a, save("2272.01.01", flags=[]), CAP, GRACE)
    assert result == "failed" and "governor_directive_tech_rush" in detail
    locked = parse_directive_reply(f"Directive tech_rush applied. Policies set: none. {LOCKED}: "
                                   "economic_policy=economic_policy_civilian.")
    b = directive_action("tech_rush", "2271.12.01", locked)
    result, _, detail = judge(b, save("2272.01.01", policies={"economic_policy": "economic_policy_balanced"}), CAP, GRACE)
    assert result == "locked" and "economic_policy" in detail, "no marker: locked, not a failure"
    flag_only = directive_action("expand", "2271.12.01", parse_directive_reply("Directive expand applied"))
    assert judge(flag_only, save("2272.01.01", flags=["governor_directive_expand"]), CAP, GRACE)[0] == "took"


def test_a_directive_is_superseded_before_its_first_save_and_held_after_it():
    a = directive_action("tech_rush", "2271.12.01", parse_directive_reply(CIVILIAN))
    assert supersede(a)[0] == "superseded"
    judge(a, save("2272.01.01"), CAP, GRACE)
    assert supersede(a)[0] == "held"
    b = directive_action("tech_rush", "2271.12.01", parse_directive_reply(CIVILIAN))
    judge(b, save("2272.01.01"), CAP, GRACE)
    assert judge(b, save("2273.12.01"), CAP, GRACE)[0] == "held", "followed 24 months at most"


def research(current=None, alternatives=()):
    return {"physics": {"current": current, "alternatives": list(alternatives)}}


def test_a_tech_pick_is_researched_held_or_did_not_stick():
    a = tech_action("tech_lasers_2", "physics", "2250.01.01")
    assert (a["key"], a["id"]) == ("tech", "tech_lasers_2")
    assert judge(a, {"date": "2250.02.01", "research": research(["tech_lasers_2", 3.0])}, CAP, GRACE)[0] == "open"
    assert review_outcome(a) == ("held", "still researched in physics at the review")
    done = {"date": "2250.09.01", "research": research(["tech_x", 1.0], ["tech_y"])}
    assert judge(tech_action("tech_lasers_2", "physics", "2250.01.01"), done, CAP, GRACE)[0] == "researched"
    missed = {"date": "2250.02.01", "research": research(["tech_x", 1.0], ["tech_lasers_2"])}
    result, by, _ = judge(tech_action("tech_lasers_2", "physics", "2250.01.01"), missed, CAP, GRACE)
    assert (result, by) == ("did_not_stick", "tech_x")
    unread = tech_action("tech_lasers_2", "physics", "2250.01.01")
    assert judge(unread, {"date": "2250.02.01"}, CAP, GRACE)[0] == "open", "no research block: cannot tell"
    assert review_outcome(tech_action("t", "physics", "2250.01.01")) is None, "not yet seen: no verdict"


def test_a_market_order_took_did_not_take_or_was_removed():
    buy = {"side": "buy", "resource": "consumer_goods", "amount": 15}
    a = market_action(buy, "2250.01.01", "cal1")
    assert a["key"] == "market buy consumer_goods" and a["calibration"] == "cal1"
    six = [{**buy, "amount": 6}]
    result, _, detail = judge(a, {"date": "2250.02.01", "market_orders": six}, CAP, GRACE)
    assert result == "did_not_take" and "15" in detail and "6" in detail
    b = market_action(buy, "2250.01.01", "cal1")
    assert judge(b, {"date": "2250.02.01", "market_orders": [buy]}, CAP, GRACE)[0] == "open"
    assert judge(b, {"date": "2250.05.01", "market_orders": []}, CAP, GRACE)[0] == "removed"
    c = market_action(buy, "2250.01.01", "cal1")
    judge(c, {"date": "2250.02.01", "market_orders": [buy]}, CAP, GRACE)
    assert supersede(c)[0] == "held"
    assert judge(c, {"date": "2252.01.01", "market_orders": [buy]}, CAP, GRACE)[0] == "held", "24 months"
    gone = market_action({**buy, "amount": 0}, "2250.01.01", "cal1")
    assert judge(gone, {"date": "2250.02.01", "market_orders": []}, CAP, GRACE)[0] == "took", "a removal took"


def test_a_posture_took_when_its_flag_is_in_the_next_save():
    a = posture_action("naval_cap", True, "2250.01.01")
    assert a["key"] == "posture naval_cap"
    assert judge(a, {"date": "2250.02.01", "flags": ["governor_posture_naval_cap"]}, CAP, GRACE)[0] == "took"
    b = posture_action("naval_cap", True, "2250.01.01")
    assert judge(b, {"date": "2250.02.01", "flags": []}, CAP, GRACE)[0] == "did_not_take"
    assert supersede(posture_action("naval_cap", True, "2250.01.01"))[0] == "superseded"


def rows(key: str, results: list[str], start: str = "2250.01.01") -> list[dict]:
    a = {"key": key, "id": key.split(" ", 1)[-1], "ordered": start, "kind": "directive"}
    y = int(start[:4])
    return [outcome_row({**a, "ref": f"r{i}"}, r, None, f"detail {i}", f"{y + i}.01.01") for i, r in enumerate(results)]


def test_the_record_counts_took_held_and_researched_against_every_failure():
    rec = action_record(rows("directive tech_rush", ["held", "overridden", "held", "overridden", "locked"])
                        + rows("tech", ["researched", "did_not_stick", "no_op", "no_op"])
                        + rows("market buy food", ["took", "did_not_take", "removed"]), 2260 * 12, SPEC)
    d = rec["directive tech_rush"]
    assert (d["judged"], d["held"], d["overridden"], d["rate"], d["weak"]) == (4, 2, 2, 0.5, True)
    assert d["excluded"]["locked"] == 1
    assert (rec["tech"]["judged"], rec["tech"]["excluded"]["no_op"]) == (2, 2)
    assert rec["market buy food"]["rate"] == 0.33, "removed counts as a failure"
    assert list(rec) == ["directive tech_rush", "tech", "market buy food"], "directives, tech, market, postures"
    text = action_record_text(rec)
    assert ("- directive tech_rush: 4 judged; 2 held, 2 overridden by the AI (last: detail 3) (not judged: 1 locked); "
            "stick rate 50% — does not stick here") in text
    assert "- tech: 2 judged; 1 researched, 1 did not stick (last: detail 1) (not judged: 2 no-op) (a rate needs 3)" in text


def test_two_did_not_take_in_a_row_suspend_a_market_order_until_the_calibration_changes():
    def row(result, cal="cal1", when="2250.02.01"):
        a = market_action({"side": "buy", "resource": "consumer_goods", "amount": 15}, "2250.01.01", cal)
        return outcome_row(a, result, None, "", when)
    two = [row("did_not_take"), row("did_not_take", when="2250.03.01")]
    assert market_suspended(two, "buy", "consumer_goods", "cal1")
    assert not market_suspended(two, "buy", "consumer_goods", "cal2"), "recalibrated: lifted"
    assert not market_suspended(two, "sell", "consumer_goods", "cal1")
    assert not market_suspended(two[:1], "buy", "consumer_goods", "cal1")
    broken = [two[0], row("failed", when="2250.02.15"), two[1]]
    assert not market_suspended(broken, "buy", "consumer_goods", "cal1"), "a timeout (failed) breaks the run"
    assert not market_suspended([*two, row("took", when="2250.04.01")], "buy", "consumer_goods", "cal1")


def test_a_buy_in_the_order_list_that_never_executes_is_recorded_took_not_executing():
    """Ruling 10: `net` leaves market trades out, so a buy that sits in the order list without trading
    shows only in `trades_net` (last month's monthly trades): none in 2 saves after it was seen."""
    order = {"side": "buy", "resource": "minerals", "amount": 10}
    a = market_action(order, "2250.01.01", "cal1")
    s = lambda d, trades: {"date": d, "market_orders": [order], "market": {"kind": "galactic", "trades_net": trades}}
    assert judge(a, s("2250.02.01", {}), CAP, GRACE)[0] == "open" and a["state"] == "took", \
        "the save that first shows it may predate its first trade"
    assert judge(a, s("2250.03.01", {}), CAP, GRACE)[0] == "open"
    result, by, detail = judge(a, s("2250.04.01", {"energy": -5.0, "trade": 4.0}), CAP, GRACE)
    assert (result, by) == ("took", "not executing") and "no minerals bought" in detail


def test_a_buy_that_trades_is_followed_and_named_with_its_last_trade_when_held():
    order = {"side": "buy", "resource": "minerals", "amount": 10}
    a = market_action(order, "2250.01.01", "cal1")
    trading = {"minerals": 10.0, "trade": -13.0}
    for d in ("2250.02.01", "2250.03.01", "2250.04.01", "2250.05.01"):
        save_ = {"date": d, "market_orders": [order], "market": {"kind": "galactic", "trades_net": trading}}
        assert judge(a, save_, CAP, GRACE)[0] == "open"
    result, detail = supersede(a)
    assert result == "held" and "+10 minerals for 13 trade" in detail
    blind = market_action(order, "2250.01.01", "cal1")
    for d in ("2250.02.01", "2250.03.01", "2250.04.01", "2250.05.01"):
        assert judge(blind, {"date": d, "market_orders": [order]}, CAP, GRACE)[0] == "open", \
            "without a market block the check is the order list alone"


def test_market_actions_can_carry_the_crisis_key_and_count_toward_the_suspension():
    order = {"side": "buy", "resource": "alloys", "amount": 25}
    a = market_action(order, "2250.01.01", "cal1", key="crisis market buy alloys")
    assert a["key"] == "crisis market buy alloys" and a["kind"] == "market"
    rows = [outcome_row(market_action(order, d, "cal1", key="crisis market buy alloys"), "did_not_take", None, "",
                        d2) for d, d2 in (("2250.01.01", "2250.02.01"), ("2250.03.01", "2250.04.01"))]
    assert market_suspended(rows, "buy", "alloys", "cal1"), "the click arithmetic is the same for crisis orders"


def test_the_same_save_judged_again_after_a_restart_is_not_a_second_dry_save():
    order = {"side": "buy", "resource": "minerals", "amount": 10}
    a = market_action(order, "2250.01.01", "cal1")
    s = lambda d: {"date": d, "market_orders": [order], "market": {"kind": "galactic", "trades_net": {}}}
    judge(a, s("2250.02.01"), CAP, GRACE)
    assert judge(a, s("2250.03.01"), CAP, GRACE)[0] == "open"
    assert judge(a, s("2250.03.01"), CAP, GRACE)[0] == "open", "a restart reads the save it was judged on again"
    assert judge(a, s("2250.04.01"), CAP, GRACE)[:2] == ("took", "not executing")
