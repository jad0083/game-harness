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
