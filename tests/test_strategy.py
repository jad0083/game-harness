
from pilot.strategy import (
    MarketOrder,
    Milestone,
    Pillar,
    Strategy,
    keep_pinned,
    metric_value,
    milestone_status,
    validate,
)

PRIOS = {"defence": 1, "economy": 2, "technology": 3, "expansion": 4, "diplomacy": 5, "government": 6, "society": 7}


def strat(**over) -> Strategy:
    pillars = {p: Pillar(priority=n, stance=f"{p} stance", goals=[f"{p} goal"]) for p, n in PRIOS.items()}
    pillars.update(over)
    return Strategy(pillars=pillars, focus="hold the line")


def test_ranking_follows_priorities_and_skips_pillars_without_a_directive():
    assert strat().ranking() == ["defend", "consolidate_economy", "tech_rush", "expand", "diplomacy_first"]


def test_valid_strategy_has_no_errors():
    assert validate(strat(), previous=None, tech_ids={"tech_habitat_1"}, idle=set(), income={}) == []


def test_validation_catches_bad_pillars_metrics_techs_and_orders():
    bad = strat(technology=Pillar(priority=3, stance="s", goals=["g"], prefer_techs=["tech_nope"],
                                  milestones=[Milestone(metric="happiness", op=">=", target=1, by="2250.01.01")]),
                economy=Pillar(priority=3, stance="s", goals=["g"],
                               market=[{"side": "sell", "resource": "energy", "amount": 500}]))
    errs = validate(bad, previous=None, tech_ids={"tech_habitat_1"}, idle={"energy"}, income={"energy": 100})
    joined = " | ".join(errs)
    assert "duplicate priority 3" in joined
    assert "unknown metric 'happiness'" in joined
    assert "unknown tech 'tech_nope'" in joined
    assert "energy 500 is over 20" in joined


def test_selling_a_resource_that_is_not_idle_is_rejected():
    s = strat(economy=Pillar(priority=2, stance="s", goals=["g"], market=[{"side": "sell", "resource": "minerals", "amount": 5}]))
    assert any("not idle" in e for e in validate(s, previous=None, tech_ids=set(), idle={"energy"}, income={"minerals": 100}))


def test_missing_or_extra_pillars_are_rejected():
    s = strat()
    del s.pillars["society"]
    assert any("missing pillar society" in e for e in validate(s, previous=None, tech_ids=set(), idle=set(), income={}))


def test_pinned_pillars_survive_a_model_rewrite():
    human = Pillar(priority=5, stance="stay out of federations", goals=["no federation"], pinned=True, edited_by="human")
    old = strat(diplomacy=human)
    new = strat(diplomacy=Pillar(priority=5, stance="join a federation", goals=["federation"]))
    kept = keep_pinned(new, old)
    assert kept.pillars["diplomacy"].stance == "stay out of federations" and kept.pillars["diplomacy"].pinned


def test_milestone_status_from_metrics_rows():
    rows = [{"date": "2240.01.01", "planets": 4}, {"date": "2241.01.01", "planets": 6}]
    m = Milestone(metric="colonies", op=">=", target=10, by="2243.01.01")
    assert milestone_status(m, rows, "2241.01.01") == "on_track"          # +2/yr → 10 by 2243
    assert milestone_status(Milestone(metric="colonies", op=">=", target=12, by="2243.01.01"), rows, "2241.01.01") == "at_risk"
    assert milestone_status(Milestone(metric="colonies", op=">=", target=5, by="2243.01.01"), rows, "2241.01.01") == "met"
    assert milestone_status(Milestone(metric="colonies", op=">=", target=12, by="2240.06.01"), rows, "2241.01.01") == "missed"
    assert milestone_status(m, [], "2241.01.01") == "at_risk", "no data yet is at risk, not an error"


def test_metric_value_reads_counts_and_ranks():
    row = {"planets": 7, "systems": 20, "peers": {"military_power": {"rank": 9, "median": 3000}}}
    assert metric_value(row, "colonies") == 7 and metric_value(row, "systems") == 20
    assert metric_value(row, "rank:military_power") == 9
    assert metric_value(row, "rank:techs") is None


# Fix round 1 tests

def test_milestone_status_requires_at_least_12_months_of_data():
    """If no data point ≥12 months before now, return at_risk (do not fall back to series[0])."""
    # 11 months apart with favorable trend should still be at_risk
    rows = [{"date": "2240.01.01", "planets": 4}, {"date": "2240.12.01", "planets": 6}]
    m = Milestone(metric="colonies", op=">=", target=10, by="2243.01.01")
    assert milestone_status(m, rows, "2240.12.01") == "at_risk"  # only 11 months, not 12

    # 1 month apart should be at_risk
    rows = [{"date": "2240.01.01", "planets": 4}, {"date": "2240.02.01", "planets": 6}]
    assert milestone_status(m, rows, "2240.02.01") == "at_risk"

    # 13 months apart should project from the 12+ month old point (not fall back to series[0])
    rows = [{"date": "2240.01.01", "planets": 4}, {"date": "2241.02.01", "planets": 6}]
    assert milestone_status(m, rows, "2241.02.01") == "at_risk"  # projects to ~9.5, not on track


def test_milestone_by_must_be_valid_date_format():
    """Milestone.by must be YYYY.MM.DD with valid month 1-12."""
    # Invalid format
    try:
        Milestone(metric="colonies", op=">=", target=10, by="not-a-date")
        assert False, "should reject invalid date format"
    except ValueError:
        pass

    # Invalid month format with dash instead of dot
    try:
        Milestone(metric="colonies", op=">=", target=10, by="2250-01-01")
        assert False, "should reject invalid date format"
    except ValueError:
        pass


def test_validation_rejects_invalid_milestone_dates():
    """Milestone constructor rejects invalid by dates."""
    # Milestone constructor should reject non-date format
    try:
        Milestone(metric="colonies", op=">=", target=10, by="not-a-date")
        assert False, "should reject invalid date format"
    except ValueError as e:
        assert "is not a date" in str(e)

    # Milestone constructor should reject dash format
    try:
        Milestone(metric="colonies", op=">=", target=10, by="2250-01-01")
        assert False, "should reject dash format"
    except ValueError as e:
        assert "is not a date" in str(e)


def test_pinned_pillar_comparison_ignores_pinned_and_edited_by():
    """Pinned pillars should only error if content differs, not editing metadata."""
    human = Pillar(priority=5, stance="s", goals=["g"], pinned=True, edited_by="human")
    old = strat(diplomacy=human)
    # New pillar has same content but different edited_by and not pinned
    new = strat(diplomacy=Pillar(priority=5, stance="s", goals=["g"], pinned=False, edited_by="model"))
    errs = validate(new, previous=old, tech_ids=set(), idle=set(), income={})
    # Should NOT error because content is the same (ignoring pinned/edited_by)
    assert not any("is pinned" in e for e in errs)

    # Now change the stance, should error
    new2 = strat(diplomacy=Pillar(priority=5, stance="different", goals=["g"], pinned=False, edited_by="model"))
    errs2 = validate(new2, previous=old, tech_ids=set(), idle=set(), income={})
    assert any("is pinned" in e for e in errs2)


def test_keep_pinned_deep_copies_pillars():
    """Mutating the previous pillar after keep_pinned should not affect the result."""
    human = Pillar(priority=5, stance="s", goals=["g"], pinned=True, edited_by="human")
    old = strat(diplomacy=human)
    new = strat(diplomacy=Pillar(priority=5, stance="different", goals=["different"]))
    kept = keep_pinned(new, old)

    # Mutate old.pillars["diplomacy"] (should not affect kept)
    old.pillars["diplomacy"].stance = "mutated"
    old.pillars["diplomacy"].goals = ["mutated"]

    # kept should still have the original stance and goals
    assert kept.pillars["diplomacy"].stance == "s"
    assert kept.pillars["diplomacy"].goals == ["g"]


def test_validation_errors_have_correct_pillar_scope():
    """Unknown tech and market errors should use actual pillar names, not hardcoded names."""
    bad = strat(
        technology=Pillar(priority=3, stance="s", goals=["g"], prefer_techs=["unknown_tech"]),
        expansion=Pillar(priority=4, stance="s", goals=["g"],
                         market=[{"side": "sell", "resource": "minerals", "amount": 5}])
    )
    errs = validate(bad, previous=None, tech_ids=set(), idle=set(), income={})
    # Should have error mentioning "technology: unknown tech"
    assert any("technology:" in e and "unknown tech" in e for e in errs)


def test_validation_missing_income_for_sold_resource():
    """When selling a resource with no income entry, error should say 'no monthly income known'."""
    s = strat(economy=Pillar(priority=2, stance="s", goals=["g"],
                             market=[{"side": "sell", "resource": "minerals", "amount": 5}]))
    # minerals not in income dict at all
    errs = validate(s, previous=None, tech_ids=set(), idle={"minerals"}, income={})
    assert any("no monthly income known for minerals" in e for e in errs)


def test_forbid_extra_fields_in_models():
    """Models should reject unknown fields (ConfigDict(extra='forbid'))."""
    # Try to create Milestone with unknown field
    try:
        Milestone(metric="colonies", op=">=", target=10, by="2250.01.01", unknown_field="value")
        assert False, "should reject unknown field"
    except ValueError:
        pass

    # Try to create MarketOrder with unknown field
    try:
        MarketOrder(side="sell", resource="energy", amount=5, unknown_field="value")
        assert False, "should reject unknown field"
    except ValueError:
        pass

    # Try to create Pillar with unknown field
    try:
        Pillar(priority=1, stance="s", unknown_field="value")
        assert False, "should reject unknown field"
    except ValueError:
        pass

    # Try to create Strategy with unknown field
    try:
        Strategy(pillars={}, focus="test", unknown_field="value")
        assert False, "should reject unknown field"
    except ValueError:
        pass
