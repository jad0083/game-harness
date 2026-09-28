"""The strategy layer on Civilization VI's pillars: share mode, id-list actions and turn dates."""

import pytest

from pilot.config import REPO
from pilot.pillars import load_pillars
from pilot.strategy import (
    Milestone,
    Pillar,
    Strategy,
    milestone_status,
    review_model,
    strategist_instructions,
    to_strategy,
    validate,
)
from pilot.telemetry import month_index

SPEC = load_pillars(REPO / "corpora/civ6")
IDS = {"tech": {"tech:pottery", "tech:writing"}, "civic": {"civic:code_of_laws"},
       "policy": {"policy:god_king"}, "production": {"unit:settler", "building:monument"},
       "purchase": {"unit:settler", "unit:warrior"}}
WEIGHTS = {"science": 25, "expansion": 20, "economy": 15, "culture": 12, "military": 12, "faith": 8, "diplomacy": 8}


def civ_strategy(**over) -> Strategy:
    pillars = {}
    for name, w in WEIGHTS.items():
        pillars[name] = Pillar(weight=w, stance=f"{name} at 3 per turn", goals=["reach 5", "hold 2"],
                               milestones=[Milestone(metric="cities", op=">=", target=2, by="T40"),
                                           Milestone(metric="science", op=">=", target=10, by="T80")])
    pillars["science"] = pillars["science"].model_copy(update={"prefer_techs": ["tech:writing"]})
    pillars["culture"] = pillars["culture"].model_copy(update={"prefer_civics": ["civic:code_of_laws"],
                                                                "prefer_policies": ["policy:god_king"]})
    pillars["expansion"] = pillars["expansion"].model_copy(update={"prefer_production": ["unit:settler"]})
    pillars["military"] = pillars["military"].model_copy(update={"prefer_purchases": ["unit:warrior"]})
    for name, fields in over.items():
        pillars[name] = pillars[name].model_copy(update=fields)
    return Strategy(pillars=pillars, focus="expand to 4 cities")


def errors(s: Strategy) -> list[str]:
    return validate(s, SPEC, previous=None, tech_ids=set(), idle=set(), income={}, ids=IDS)


def test_a_civ6_strategy_with_turn_dates_and_corpus_ids_is_valid():
    assert errors(civ_strategy()) == []


def test_unknown_ids_and_foreign_action_fields_are_rejected():
    errs = errors(civ_strategy(culture={"prefer_civics": ["civic:space_race"]},
                               science={"prefer_production": ["unit:settler"]}))
    assert "culture: unknown civic 'civic:space_race'" in errs
    assert any("science: only the" in e and "prefer_production" in e for e in errs)


def test_too_many_preferred_ids_are_rejected():
    errs = errors(civ_strategy(science={"prefer_techs": ["tech:pottery", "tech:writing"] * 3}))
    assert any("science: at most 4" in e for e in errs)


def test_calendar_dates_are_rejected_in_a_turn_based_game():
    s = civ_strategy(science={"milestones": [Milestone(metric="science", op=">=", target=10, by="2250.01.01"),
                                             Milestone(metric="science", op=">=", target=20, by="T90")]})
    assert any("T<turn>" in e for e in errors(s))


def test_a_turn_milestone_is_judged_on_turn_rows():
    m = Milestone(metric="cities", op=">=", target=3, by="T60")
    rows = [{"date": "T10", "cities": 1}, {"date": "T25", "cities": 2}]
    assert milestone_status(m, rows, "T25") == "on_track"          # +1 per 15 turns reaches 4 by T60
    assert milestone_status(m, rows, "T61") == "missed"
    assert milestone_status(m, [*rows, {"date": "T30", "cities": 3}], "T30") == "met"
    with pytest.raises(ValueError):
        Milestone(metric="cities", op=">=", target=3, by="turn 60")


def test_turn_dates_have_a_month_index_for_telemetry():
    assert month_index("T12") == 12 and month_index("T0") == 0
    assert month_index("2204.09.01") == 2204 * 12 + 8
    assert month_index("T") is None and month_index("Jul 2333") is None


def test_the_strategist_is_told_turns_and_the_id_lists():
    text = strategist_instructions(SPEC)
    assert "T<turn>" in text and "YYYY.MM.DD" not in text
    assert "prefer_civics" in text and "prefer_purchases" in text
    model = review_model(SPEC)
    answer = model.model_validate({"change": True, "assessment": "first", "strategy": {
        "focus": "f", **{n: {"weight": w, "stance": "s 1", "goals": [], "milestones": []} for n, w in WEIGHTS.items()},
        "culture": {"weight": 12, "stance": "s 1", "prefer_civics": ["civic:code_of_laws"]}}})
    s = to_strategy(answer.strategy, SPEC)
    assert s.pillars["culture"].prefer_civics == ["civic:code_of_laws"]
    with pytest.raises(ValueError):
        model.model_validate({"change": True, "assessment": "x", "strategy": {
            "focus": "f", "science": {"weight": 10, "stance": "s", "prefer_civics": ["civic:code_of_laws"]}}})


def test_stellaris_strategies_keep_calendar_dates():
    stellaris = load_pillars(REPO / "corpora/stellaris")
    text = strategist_instructions(stellaris)
    assert "YYYY.MM.DD" in text and "T<turn>" not in text


def test_a_milestone_on_a_balance_is_rejected():
    """E7 of docs/design/2026-09-27-civ6-levers-design.md: faith >= 200 by T70 paid for hoarding."""
    hoard = civ_strategy(faith={"milestones": [Milestone(metric="faith", op=">=", target=200, by="T70")]})
    assert any("faith: faith is a balance, not a milestone metric here" in e and "milestone_exclude" in e
               for e in errors(hoard))
    treasury = civ_strategy(economy={"milestones": [Milestone(metric="treasury", op=">=", target=300, by="T90")]})
    from pilot.strategy import apply_aliases
    assert any("economy: gold is a balance" in e for e in errors(apply_aliases(treasury, SPEC)))
    assert errors(civ_strategy(faith={"milestones": [Milestone(metric="faith_yield", op=">=", target=10, by="T70")]})) == []
    text = strategist_instructions(SPEC)
    assert "never gold or faith: a balance rewards hoarding" in text
    names = text.split("exactly these names: ")[1].split(";")[0].split(", ")
    assert "faith_yield" in names and "faith" not in names and "gold" not in names


def test_balance_milestones_bind_the_strategist_not_pins_or_human_edits():
    pinned = civ_strategy(economy={"milestones": [Milestone(metric="gold", op=">=", target=60, by="T130")],
                                   "pinned": True})
    assert errors(pinned) == [], "a pinned pillar comes back unchanged in every answer"
    human = civ_strategy(economy={"milestones": [Milestone(metric="gold", op=">=", target=60, by="T130")]})
    assert validate(human, SPEC, previous=None, tech_ids=set(), idle=set(), income={}, ids=IDS,
                    briefing_checked={"science"}, require_milestones=False) == [], "a human edit elsewhere"


def test_the_t350_military_milestone_is_at_risk_then_missed_not_met():
    """Post-mortem strategy-1 (postmortem-fixes design, ruling 17): "military >= 170 by T350", set at
    T342 with 123, read met at T350 with 124 because T326 and T329 were above 170. Judged on the
    current value it reads at_risk T342-T350 and missed from T351."""
    import json

    from pilot.config import REPO
    rows = [r for r in json.loads((REPO / "tests/fixtures/civ6_kublai_rows.json").read_text(encoding="utf-8"))
            if 326 <= r["turn"] <= 352]
    m = Milestone(metric="military", op=">=", target=170, by="T350", set="T342")
    for t in (342, 344, 345, 347, 350):
        assert milestone_status(m, rows, f"T{t}") == "at_risk", t
    assert milestone_status(m, rows, "T351") == "missed"
    assert milestone_status(m.model_copy(update={"set": None}), rows, "T350") == "at_risk", \
        "without the stamp the old rows above 170 no longer read met either"


# ---- postmortem-fixes design, ruling 18: military targets relative to the majors met -------------

def _military(*milestones, pinned=False):
    return civ_strategy(military={"milestones": list(milestones), "pinned": pinned})


def _check(s, standing):
    return validate(s, SPEC, previous=None, tech_ids=set(), idle=set(), income={}, ids=IDS, standing=standing)


def test_the_t525_absolute_military_targets_are_sent_back():
    """Strategy-7: the T525 targets 520 and 580 against a median of 1,106 (0.47 and 0.52 x)."""
    s = _military(Milestone(metric="military", op=">=", target=520, by="T540"),
                  Milestone(metric="military", op=">=", target=580, by="T560"))
    errs = _check(s, {"military": 471, "median": 1106.0, "peers": 5, "weak": True})
    assert any("military >= 520 by T540 is under 0.5 x the median of the majors we have met (1,106)" in e for e in errs)
    assert not any("580" in e for e in errs), "580 is 0.52 x the median"
    assert any("military: our military is weak" in e and "military_vs_median or military_vs_strongest >= 0.5" in e
               for e in errs)


def test_a_relative_milestone_satisfies_the_rule_and_ranks_need_three_majors():
    ok = _military(Milestone(metric="military_vs_median", op=">=", target=0.6, by="T560"))
    assert _check(ok, {"military": 471, "median": 1106.0, "peers": 5, "weak": True}) == []
    low = _military(Milestone(metric="military_vs_strongest", op=">=", target=0.3, by="T560"))
    assert any("weak" in e for e in _check(low, {"military": 471, "median": 1106.0, "peers": 5, "weak": True}))
    rank = _military(Milestone(metric="rank:military", op="<=", target=1, by="T350"))
    errs = _check(rank, {"military": 200, "median": 180.0, "peers": 2, "weak": False})
    assert any("rank:military ranks us among only 2 majors met; a rank milestone needs 3 or more" in e for e in errs)
    assert _check(rank, {"military": 200, "median": 180.0, "peers": 3, "weak": False}) == []


def test_pinned_pillars_and_human_edits_are_exempt_and_the_strategist_is_told():
    pinned = _military(Milestone(metric="military", op=">=", target=100, by="T540"), pinned=True)
    assert _check(pinned, {"military": 471, "median": 1106.0, "peers": 5, "weak": True}) == []
    human = _military(Milestone(metric="military", op=">=", target=100, by="T540"))
    assert validate(human, SPEC, previous=None, tech_ids=set(), idle=set(), income={}, ids=IDS, require_milestones=False,
                    briefing_checked={"military"}, standing={"military": 471, "median": 1106.0, "peers": 5, "weak": True}) == []
    text = strategist_instructions(SPEC)
    assert "military_vs_median or military_vs_strongest with a target of at least 0.5" in text
    assert "military_vs_median" in text.split("exactly these names: ")[1]
