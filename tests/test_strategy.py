
import re
import tomllib

import pytest

from pilot.config import REPO
from pilot.pillars import load_pillars
from pilot.strategy import (
    MarketOrder,
    Milestone,
    Pillar,
    Strategy,
    apply_aliases,
    keep_pinned,
    metric_value,
    milestone_status,
    ranking,
    validate,
)

SPEC = load_pillars(REPO / "corpora/stellaris")
PRIOS = {"defence": 1, "economy": 2, "technology": 3, "expansion": 4, "diplomacy": 5, "government": 6, "society": 7}
_M = Milestone(metric="systems", op=">=", target=10, by="2250.01.01")


def strat(**over) -> Strategy:
    pillars = {p: Pillar(priority=n, stance=f"{p} stance", goals=[f"{p} goal"], milestones=[_M]) for p, n in PRIOS.items()}
    pillars.update(over)
    return Strategy(pillars=pillars, focus="hold the line")


def test_ranking_follows_priorities_and_skips_pillars_without_a_directive():
    assert ranking(strat(), SPEC) == ["defend", "consolidate_economy", "tech_rush", "expand", "diplomacy_first"]


def test_valid_strategy_has_no_errors():
    assert validate(strat(), SPEC, previous=None, tech_ids={"tech_habitat_1"}, idle=set(), income={}) == []


def test_validation_catches_bad_pillars_metrics_techs_and_orders():
    bad = strat(technology=Pillar(priority=3, stance="s", goals=["g"], prefer_techs=["tech_nope"],
                                  milestones=[Milestone(metric="happiness", op=">=", target=1, by="2250.01.01")]),
                economy=Pillar(priority=3, stance="s", goals=["g"],
                               market=[{"side": "sell", "resource": "energy", "amount": 500}]))
    errs = validate(bad, SPEC, previous=None, tech_ids={"tech_habitat_1"}, idle={"energy"}, income={"energy": 100})
    joined = " | ".join(errs)
    assert "duplicate priority 3" in joined
    assert "unknown metric 'happiness'" in joined
    assert "unknown tech 'tech_nope'" in joined
    assert "energy 500 is over 20" in joined


def test_selling_a_resource_that_is_not_idle_is_rejected():
    s = strat(economy=Pillar(priority=2, stance="s", goals=["g"], market=[{"side": "sell", "resource": "minerals", "amount": 5}]))
    assert any("not idle" in e for e in validate(s, SPEC, previous=None, tech_ids=set(), idle={"energy"}, income={"minerals": 100}))


def test_missing_or_extra_pillars_are_rejected():
    s = strat()
    del s.pillars["society"]
    assert any("missing pillar society" in e for e in validate(s, SPEC, previous=None, tech_ids=set(), idle=set(), income={}))


def test_pinned_pillars_survive_a_model_rewrite():
    human = Pillar(priority=5, stance="stay out of federations", goals=["no federation"], pinned=True, edited_by="human")
    old = strat(diplomacy=human)
    new = strat(diplomacy=Pillar(priority=5, stance="join a federation", goals=["federation"]))
    kept = keep_pinned(new, old)
    assert kept.pillars["diplomacy"].stance == "stay out of federations" and kept.pillars["diplomacy"].pinned


def test_milestone_status_from_metrics_rows():
    rows = [{"date": "2240.01.01", "planets": 4}, {"date": "2241.01.01", "planets": 6}]
    rk = SPEC.row_keys
    m = Milestone(metric="colonies", op=">=", target=10, by="2243.01.01")
    assert milestone_status(m, rows, "2241.01.01", rk) == "on_track"          # +2/yr → 10 by 2243
    assert milestone_status(Milestone(metric="colonies", op=">=", target=12, by="2243.01.01"), rows, "2241.01.01", rk) == "at_risk"
    assert milestone_status(Milestone(metric="colonies", op=">=", target=5, by="2243.01.01"), rows, "2241.01.01", rk) == "met"
    assert milestone_status(Milestone(metric="colonies", op=">=", target=12, by="2240.06.01"), rows, "2241.01.01", rk) == "missed"
    assert milestone_status(m, [], "2241.01.01", rk) == "at_risk", "no data yet is at risk, not an error"


def test_metric_value_reads_counts_and_ranks():
    row = {"planets": 7, "systems": 20, "peers": {"military_power": {"rank": 9, "median": 3000}}}
    assert metric_value(row, "colonies", SPEC.row_keys) == 7 and metric_value(row, "systems") == 20
    assert metric_value(row, "colonies") is None, "without the row keys colonies is not a row field"
    assert metric_value(row, "rank:military_power") == 9
    assert metric_value(row, "rank:techs") is None


# Fix round 1 tests

def test_milestone_status_requires_at_least_12_months_of_data():
    """If no data point ≥12 months before now, return at_risk (do not fall back to series[0])."""
    # 11 months apart with favorable trend should still be at_risk
    rows = [{"date": "2240.01.01", "planets": 4}, {"date": "2240.12.01", "planets": 6}]
    m = Milestone(metric="colonies", op=">=", target=10, by="2243.01.01")
    assert milestone_status(m, rows, "2240.12.01", SPEC.row_keys) == "at_risk"  # only 11 months, not 12

    # 1 month apart should be at_risk
    rows = [{"date": "2240.01.01", "planets": 4}, {"date": "2240.02.01", "planets": 6}]
    assert milestone_status(m, rows, "2240.02.01", SPEC.row_keys) == "at_risk"

    # 13 months apart should project from the 12+ month old point (not fall back to series[0])
    rows = [{"date": "2240.01.01", "planets": 4}, {"date": "2241.02.01", "planets": 6}]
    assert milestone_status(m, rows, "2241.02.01", SPEC.row_keys) == "at_risk"  # projects to ~9.5, not on track


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
    errs = validate(new, SPEC, previous=old, tech_ids=set(), idle=set(), income={})
    # Should NOT error because content is the same (ignoring pinned/edited_by)
    assert not any("is pinned" in e for e in errs)

    # Now change the stance, should error
    new2 = strat(diplomacy=Pillar(priority=5, stance="different", goals=["g"], pinned=False, edited_by="model"))
    errs2 = validate(new2, SPEC, previous=old, tech_ids=set(), idle=set(), income={})
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
    """Unknown tech errors should use actual pillar name, not hardcoded 'technology:'."""
    # Put prefer_techs on economy (wrong pillar) with unknown tech
    bad = strat(
        economy=Pillar(priority=2, stance="s", goals=["g"], prefer_techs=["unknown_tech"])
    )
    errs = validate(bad, SPEC, previous=None, tech_ids=set(), idle=set(), income={})
    # Should have error starting with "economy:" (actual pillar name, not "technology:")
    assert any(e.startswith("economy:") and "unknown tech" in e for e in errs)


def test_validation_missing_income_for_sold_resource():
    """When selling a resource with no income entry, error should say 'no monthly income known'."""
    s = strat(economy=Pillar(priority=2, stance="s", goals=["g"],
                             market=[{"side": "sell", "resource": "minerals", "amount": 5}]))
    # minerals not in income dict at all
    errs = validate(s, SPEC, previous=None, tech_ids=set(), idle={"minerals"}, income={})
    assert any("no monthly income known for minerals" in e for e in errs)


def test_trade_market_orders_are_rejected():
    """Trade is not a market resource (not a key of the manifest's [ui.market.resources])."""
    s = strat(economy=_econ({"side": "sell", "resource": "trade", "amount": 10}))
    errs = validate(s, SPEC, previous=None, tech_ids=set(), idle={"trade"}, income={})
    assert any("unknown market resource 'trade'" in e for e in errs)
    s2 = strat(economy=_econ({"side": "buy", "resource": "trade", "amount": 5}))
    errs2 = validate(s2, SPEC, previous=None, tech_ids=set(), idle=set(), income={})
    assert any("unknown market resource 'trade'" in e for e in errs2)


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


# ---- Task 8 fix round 1, item 4: pillar content caps -------------------------------------------

def test_a_too_long_stance_is_rejected():
    s = strat(economy=Pillar(priority=2, stance="s" * 401, goals=["g"]))
    assert any("stance is over 400 characters" in e for e in
              validate(s, SPEC, previous=None, tech_ids=set(), idle=set(), income={}))


def test_a_stance_at_exactly_the_cap_is_accepted():
    s = strat(economy=Pillar(priority=2, stance="s" * 400, goals=["g"]))
    assert not any("stance is over" in e for e in
                  validate(s, SPEC, previous=None, tech_ids=set(), idle=set(), income={}))


def test_too_many_goals_are_rejected():
    s = strat(economy=Pillar(priority=2, stance="s", goals=["a", "b", "c", "d"]))
    assert any("at most 3 goals" in e for e in
              validate(s, SPEC, previous=None, tech_ids=set(), idle=set(), income={}))


def test_a_too_long_goal_is_rejected():
    s = strat(economy=Pillar(priority=2, stance="s", goals=["g" * 201]))
    assert any("a goal is over 200 characters" in e for e in
              validate(s, SPEC, previous=None, tech_ids=set(), idle=set(), income={}))


def test_too_many_milestones_are_rejected():
    ms = [Milestone(metric="systems", op=">=", target=n, by="2250.01.01") for n in range(7)]
    s = strat(economy=Pillar(priority=2, stance="s", goals=["g"], milestones=ms))
    assert any("at most 6 milestones" in e for e in
              validate(s, SPEC, previous=None, tech_ids=set(), idle=set(), income={}))


# ---- final review fixes: split validation, one set of market rules, one order ----------------

def _econ(*orders, pinned=False):
    return Pillar(priority=2, stance="s", goals=["g"], market=list(orders), pinned=pinned, milestones=[_M],
                  edited_by="human" if pinned else "model")


def test_an_unchanged_pinned_pillar_that_no_longer_fits_the_briefing_does_not_block_a_review():
    """Ruling (final review 1): briefing-dependent checks (idle, 20% of income) apply only to
    pillars that changed versus the previous strategy and are not pinned."""
    sell = {"side": "sell", "resource": "energy", "amount": 10}
    old = strat(economy=_econ(sell, pinned=True))
    new = strat(economy=_econ(sell, pinned=True), expansion=Pillar(priority=4, stance="new", goals=["g"]))
    # energy is no longer idle and income collapsed: the pinned order no longer fits today
    assert validate(new, SPEC, previous=old, tech_ids=set(), idle=set(), income={"energy": 1.0}) == []


def test_an_unchanged_unpinned_pillar_is_not_rechecked_against_the_briefing():
    sell = {"side": "sell", "resource": "energy", "amount": 10}
    old = strat(economy=_econ(sell))
    assert validate(strat(economy=_econ(sell)), SPEC, previous=old, tech_ids=set(), idle=set(), income={"energy": 1.0}) == []


def test_a_changed_pillar_is_checked_against_the_briefing():
    old = strat(economy=_econ({"side": "sell", "resource": "energy", "amount": 10}))
    new = strat(economy=_econ({"side": "sell", "resource": "energy", "amount": 11}))
    errs = validate(new, SPEC, previous=old, tech_ids=set(), idle=set(), income={"energy": 100.0})
    assert any("not idle" in e for e in errs)


def test_structural_market_checks_apply_to_unchanged_pinned_pillars_too():
    bad = {"side": "sell", "resource": "unobtainium", "amount": 30}
    old = strat(economy=_econ(bad, pinned=True))
    errs = validate(strat(economy=_econ(bad, pinned=True)), SPEC, previous=old, tech_ids=set(), idle=set(), income={})
    joined = " | ".join(errs)
    assert "unknown market resource 'unobtainium'" in joined and "1..25" in joined


def test_briefing_checked_names_override_the_changed_pillar_rule():
    """edit_pillar: the edited pillar (pinned by the edit itself) is the only one checked."""
    sell = {"side": "sell", "resource": "energy", "amount": 10}
    s = strat(economy=_econ(sell, pinned=True))
    assert validate(s, SPEC, previous=None, tech_ids=set(), idle=set(), income={"energy": 100.0}, briefing_checked=set()) == []
    errs = validate(s, SPEC, previous=None, tech_ids=set(), idle=set(), income={"energy": 100.0}, briefing_checked={"economy"})
    assert any("not idle" in e for e in errs)


def test_pinned_misfits_name_each_pinned_pillar_that_no_longer_fits():
    from pilot.strategy import pinned_misfits
    s = strat(economy=_econ({"side": "sell", "resource": "energy", "amount": 10}, pinned=True))
    lines = pinned_misfits(s, SPEC, idle=set(), income={"energy": 100.0})
    assert len(lines) == 1 and lines[0].startswith("pinned economy no longer fits: ") and "not idle" in lines[0]
    assert pinned_misfits(s, SPEC, idle={"energy"}, income={"energy": 100.0}) == []
    unpinned = strat(economy=_econ({"side": "sell", "resource": "energy", "amount": 10}))
    assert pinned_misfits(unpinned, SPEC, idle=set(), income={"energy": 100.0}) == []


def test_sell_cap_is_the_smaller_of_25_and_20_percent_of_income():
    ok = strat(economy=_econ({"side": "sell", "resource": "energy", "amount": 25}))
    assert validate(ok, SPEC, previous=None, tech_ids=set(), idle={"energy"}, income={"energy": 1000.0}) == []
    over = strat(economy=_econ({"side": "sell", "resource": "energy", "amount": 26}))
    assert any("1..25" in e for e in validate(over, SPEC, previous=None, tech_ids=set(), idle={"energy"}, income={"energy": 1000.0}))
    small = strat(economy=_econ({"side": "sell", "resource": "energy", "amount": 21}))
    assert any("over 20" in e for e in validate(small, SPEC, previous=None, tech_ids=set(), idle={"energy"}, income={"energy": 100.0}))


def test_buys_are_capped_at_25_and_need_no_idle_or_income():
    assert validate(strat(economy=_econ({"side": "buy", "resource": "alloys", "amount": 25})), SPEC,
                    previous=None, tech_ids=set(), idle=set(), income={}) == []
    errs = validate(strat(economy=_econ({"side": "buy", "resource": "alloys", "amount": 26})), SPEC,
                    previous=None, tech_ids=set(), idle=set(), income={})
    assert any("1..25" in e for e in errs)


def test_at_most_one_market_order_until_the_row_pitch_is_measured():
    two = strat(economy=_econ({"side": "buy", "resource": "alloys", "amount": 5},
                              {"side": "buy", "resource": "food", "amount": 5}))
    assert any("at most 1 market order" in e for e in validate(two, SPEC, previous=None, tech_ids=set(), idle=set(), income={}))


def test_market_resources_are_the_manifests_market_resources():
    manifest = tomllib.loads((REPO / "corpora/stellaris/manifest.toml").read_text(encoding="utf-8"))
    assert set(SPEC.actions["market"].resources) == set(manifest["ui"]["market"]["resources"])
    assert "trade" not in SPEC.actions["market"].resources


def test_the_stellaris_pillars_file_limits_equal_the_controllers():
    """Rust keeps its own tool validation (mcp.rs); the pillars file must never plan what the tools refuse."""
    src = (REPO / "crates/game-controller/src/mcp.rs").read_text(encoding="utf-8")
    lo = re.search(r"const MARKET_AMOUNT_MIN: i64 = (\d+);", src)
    hi = re.search(r"const MARKET_AMOUNT_MAX: i64 = (\d+);", src)
    assert lo and hi, "mcp.rs declares its market amount limits as constants"
    market, tech = SPEC.actions["market"], SPEC.actions["tech"]
    assert (market.amount_min, market.amount_max) == (int(lo.group(1)), int(hi.group(1)))
    body = src[src.index("fn validate_market_orders"):]
    body = body[:body.index("\n}\n")]
    assert "MARKET_AMOUNT_MIN..=MARKET_AMOUNT_MAX" in body, "validate_market_orders uses those constants"
    orders = re.search(r"orders\.len\(\) > (\d+)", body)
    assert orders and market.max_items <= int(orders.group(1)), "never more orders than stellaris_market_sync takes"
    techs = re.search(r"prefer\.len\(\) > (\d+)", src)
    assert techs and tech.max_items == int(techs.group(1)), "prefer_techs limit equals stellaris_pick_tech's"
    manifest = tomllib.loads((REPO / "corpora/stellaris/manifest.toml").read_text(encoding="utf-8"))
    assert set(market.resources) == set(manifest["ui"]["market"]["resources"]) and "trade" not in market.resources


# ---- game pillars: rules come from the spec ------------------------------------------------------

def test_the_top_pillars_need_a_milestone():
    s = strat(economy=Pillar(priority=2, stance="s", goals=["g"]))
    errs = validate(s, SPEC, previous=None, tech_ids=set(), idle=set(), income={})
    assert "economy: priority 2 is in the top 3 and needs at least one milestone" in errs
    fine = strat(expansion=Pillar(priority=4, stance="s", goals=["g"]))
    assert validate(fine, SPEC, previous=None, tech_ids=set(), idle=set(), income={}) == [], "priority 4 needs none"


def test_a_pinned_top_pillar_without_milestones_is_not_rejected():
    s = strat(economy=Pillar(priority=2, stance="s", goals=["g"], pinned=True, edited_by="human"))
    assert validate(s, SPEC, previous=None, tech_ids=set(), idle=set(), income={}) == []


def test_human_edits_skip_the_milestone_rule():
    s = strat(economy=Pillar(priority=2, stance="s", goals=["g"]))
    assert validate(s, SPEC, previous=None, tech_ids=set(), idle=set(), income={}, require_milestones=False) == []


def test_action_fields_belong_to_the_pillars_that_declare_them():
    s = strat(diplomacy=Pillar(priority=5, stance="s", goals=["g"], prefer_techs=["tech_habitat_1"]))
    errs = validate(s, SPEC, previous=None, tech_ids={"tech_habitat_1"}, idle=set(), income={})
    assert errs == ["diplomacy: only the technology pillar may set prefer_techs"]


def test_aliases_come_from_the_spec():
    s = strat(economy=Pillar(priority=2, stance="s", milestones=[Milestone(metric=" rank:military ", op="<=", target=3, by="2250.01.01")]))
    assert apply_aliases(s, SPEC).pillars["economy"].milestones[0].metric == "rank:military_power"
    assert s.pillars["economy"].milestones[0].metric == "rank:military", "Milestone itself only strips"


def test_validation_uses_the_spec_metrics_and_pillar_count():
    bad = strat(society=Pillar(priority=8, stance="s", milestones=[Milestone(metric="culture", op=">=", target=1, by="2250.01.01")]))
    joined = " | ".join(validate(bad, SPEC, previous=None, tech_ids=set(), idle=set(), income={}))
    assert "society: priority must be 1..7" in joined and "society: unknown metric 'culture'" in joined


# ---- the Strategist's schema is generated from the spec -------------------------------------------

def _objects(node):
    if isinstance(node, dict):
        if node.get("type") == "object":
            yield node
        for v in node.values():
            yield from _objects(v)
    elif isinstance(node, list):
        for v in node:
            yield from _objects(v)


def _strategy_out_schema(schema: dict) -> dict:
    return next(d for d in schema["$defs"].values() if "focus" in d.get("properties", {}))


def test_the_review_schema_has_one_named_field_per_pillar():
    from pilot.strategy import review_model
    schema = review_model(SPEC).model_json_schema()
    out = _strategy_out_schema(schema)
    assert set(out["properties"]) == {*SPEC.ids, "focus", "reason"}
    assert "pillars" not in out["properties"]
    loose = [o for o in _objects(schema) if not o.get("properties") and o.get("additionalProperties") not in (None, False)]
    assert loose == [], "no object whose only shape is additionalProperties (Claude cannot fill those)"


def test_a_claude_style_answer_converts_to_a_valid_strategy():
    from pilot.strategy import review_model, to_strategy
    ms = [{"metric": "rank:military", "op": "<=", "target": 3, "by": "2250.01.01"}]
    answer = {"change": True, "assessment": "a", "rules": [], "strategy": {
        "defence": {"priority": 1, "stance": "hold", "goals": ["g"], "milestones": ms},
        "economy": {"priority": 2, "stance": "grow", "goals": ["g"], "milestones": ms,
                    "market": [{"side": "buy", "resource": "alloys", "amount": 5}]},
        "technology": {"priority": 3, "stance": "research", "goals": ["g"], "milestones": ms,
                       "prefer_techs": ["tech_habitat_1"]},
        "expansion": {"priority": 4, "stance": "s"}, "diplomacy": {"priority": 5, "stance": "s"},
        "government": {"priority": 6, "stance": "s"}, "society": {"priority": 7, "stance": "s"},
        "focus": "hold the line"}}
    r = review_model(SPEC).model_validate(answer)
    s = to_strategy(r.strategy, SPEC)
    assert s.pillars["defence"].milestones[0].metric == "rank:military_power", "aliases applied"
    assert s.pillars["economy"].market[0].resource == "alloys"
    assert validate(s, SPEC, previous=None, tech_ids={"tech_habitat_1"}, idle=set(), income={}) == []


def test_action_fields_exist_only_on_declaring_pillars():
    import pydantic

    from pilot.strategy import review_model
    schema = review_model(SPEC).model_json_schema()
    defs = schema["$defs"]
    out = _strategy_out_schema(schema)

    def pillar_props(pid):
        ref = next(x["$ref"] for x in out["properties"][pid]["anyOf"] if "$ref" in x)
        return set(defs[ref.rsplit("/", 1)[1]]["properties"])
    assert "market" in pillar_props("economy") and "prefer_techs" not in pillar_props("economy")
    assert "prefer_techs" in pillar_props("technology") and "market" not in pillar_props("technology")
    assert not {"market", "prefer_techs"} & pillar_props("diplomacy")
    with pytest.raises(pydantic.ValidationError):
        review_model(SPEC).model_validate({"change": True, "assessment": "a", "strategy": {
            "focus": "f", "diplomacy": {"priority": 1, "stance": "s", "prefer_techs": ["x"]}}})


def test_the_stored_shape_and_human_fields_are_accepted_as_input():
    from pilot.strategy import review_model, to_strategy
    legacy = {"change": True, "assessment": "a", "strategy": {"focus": "f", "reason": "r", "pillars": {
        "economy": {"priority": 1, "stance": "s", "pinned": True, "edited_by": "human"}}}}
    s = to_strategy(review_model(SPEC).model_validate(legacy).strategy, SPEC)
    assert set(s.pillars) == {"economy"} and s.pillars["economy"].pinned is False, "a model can never pin"


def test_the_prompt_comes_from_the_spec():
    from pilot.strategy import strategist_instructions
    text = strategist_instructions(SPEC)
    for pid, p in SPEC.pillars.items():
        assert f"- {pid} ({p.label}): {p.description}" in text
    for m in SPEC.metrics:
        assert m in text
    assert "Each of the 3 highest-priority pillars needs at least one milestone." in text
    assert "at most 1 small monthly order, amount 1-25" in text and "at most 20% of its monthly income" in text
    assert "Only technology: `prefer_techs` (tech ids to pick when offered; at most 6)." in text
    assert SPEC.actions["market"].note in text and SPEC.instructions in text


def test_the_review_schema_keeps_the_identity_field_for_the_species_guardrail():
    """Ruling 1: the generated review model keeps `identity` with the same description the governor
    used to check (the species guardrail lives in governor.py, unchanged)."""
    from pilot.strategy import review_model
    schema = review_model(SPEC).model_json_schema()
    identity = schema["properties"]["identity"]
    assert identity.get("default") == ""
    assert "how our species" in identity["description"] and "traits by name" in identity["description"]
    assert "which pillars each trait affects" in identity["description"]


# ---- Task 3 fix round 1 -------------------------------------------------------------------------

def test_the_species_guidance_is_part_of_every_games_prompt():
    """Fix round 1, item 1: the migration dropped the species/identity guidance from the old
    STRATEGY_INSTRUCTIONS; it belongs in the generated prompt (every game, not only Stellaris)."""
    from pilot.pillars import PillarDef, PillarSpec
    from pilot.strategy import strategist_instructions
    text = strategist_instructions(SPEC)
    assert "naming the traits you rely on" in text and "weigh a neighbour's traits" in text
    synthetic = PillarSpec(game="synthetic", pillars={"eco": PillarDef("eco", "Economy", "money and stuff")},
                           metrics=("m",))
    text2 = strategist_instructions(synthetic)
    assert "naming the traits you rely on" in text2 and "weigh a neighbour's traits" in text2


def test_action_field_rejects_an_unknown_action_kind():
    """Fix round 1, item 2: _action_field only knows tech/market; anything else is a clear error,
    not a silent fallthrough to the market shape."""
    from pilot.pillars import ActionLimits
    from pilot.strategy import _action_field
    with pytest.raises(ValueError, match="unknown action kind"):
        _action_field(ActionLimits(kind="something_else", field="x", max_items=1))


# ---- final review, item 1: an answer that echoes the prompt's strategy must validate -------------

def _main_shape() -> dict:
    """A strategy as main stores it: every pillar with empty action lists, pinned/edited_by and identity."""
    s = strat(economy=Pillar(priority=2, stance="s", goals=["g"], milestones=[_M], pinned=True, edited_by="human",
                             market=[MarketOrder(side="buy", resource="alloys", amount=5)]))
    return s.model_copy(update={"identity": "industrious lithoids", "reason": "r"}).model_dump()


def test_the_stored_main_shape_validates_as_a_review_strategy():
    from pilot.strategy import review_model, to_strategy
    dumped = _main_shape()
    assert dumped["pillars"]["diplomacy"]["market"] == [] and dumped["identity"]
    r = review_model(SPEC).model_validate({"change": True, "assessment": "a", "strategy": dumped})
    s = to_strategy(r.strategy, SPEC)
    assert set(s.pillars) == set(SPEC.ids) and s.pillars["economy"].market[0].resource == "alloys"
    assert not s.pillars["economy"].pinned, "a model can never pin"


def test_a_non_empty_undeclared_action_still_fails():
    import pydantic

    from pilot.strategy import review_model
    dumped = _main_shape()
    dumped["pillars"]["diplomacy"]["market"] = [{"side": "buy", "resource": "alloys", "amount": 5}]
    with pytest.raises(pydantic.ValidationError, match="market"):
        review_model(SPEC).model_validate({"change": True, "assessment": "a", "strategy": dumped})


def test_the_prompt_shows_the_strategy_in_the_output_shape():
    import json

    from pilot.strategy import review_model, strategy_for_prompt
    s = Strategy.model_validate(_main_shape())
    text = strategy_for_prompt(s, SPEC)
    shown = json.loads(text)
    assert "pillars" not in shown and "identity" not in shown and shown["focus"] == "hold the line"
    assert set(SPEC.ids) <= set(shown)
    assert "market" in shown["economy"] and "prefer_techs" in shown["technology"]
    assert not {"market", "prefer_techs"} & set(shown["diplomacy"])
    assert "pinned" not in text and "edited_by" not in text
    review_model(SPEC).model_validate({"change": True, "assessment": "a", "strategy": shown})
