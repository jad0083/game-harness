import os
import re
import shutil
import tomllib

import pytest

from pilot.config import REPO
from pilot.pillars import PillarsError, load_pillars

MINI = '''[strategy]
min_milestones_top = 1
metric_aliases = { mil = "military_power" }

[metrics]
names = ["systems", "military_power"]

[pillars.economy]
label = "Economy"
description = "Income."
directive = "consolidate_economy"
actions = ["market"]

[pillars.society]
label = "Society"
description = "Pops."

[actions.market]
max_items = 1
resources_from_manifest = "ui.market.resources"
amount_max = 25
'''


def corpus(tmp_path, text=MINI):
    d = tmp_path / "g"
    d.mkdir(exist_ok=True)
    for f in ("directives.toml", "manifest.toml"):
        shutil.copy(REPO / "corpora/stellaris" / f, d / f)
    (d / "pillars.toml").write_text(text, encoding="utf-8")
    return d


def test_the_stellaris_file_reproduces_todays_pillars():
    spec = load_pillars(REPO / "corpora/stellaris")
    assert spec.game == "stellaris"
    assert spec.ids == ("economy", "expansion", "technology", "diplomacy", "defence", "government", "society")
    assert {p: spec.directive_of(p) for p in spec.ids} == {
        "economy": "consolidate_economy", "expansion": "expand", "technology": "tech_rush",
        "diplomacy": "diplomacy_first", "defence": "defend", "government": None, "society": None}
    rank = ("systems", "pops", "techs", "military_power", "economy_power", "tech_power", "colonies")
    assert spec.metrics == ("systems", "colonies", "pops", "techs_known", "military_power", "economy_power",
                            "tech_power", *(f"rank:{m}" for m in rank))
    for alias, real in (("rank:military", "rank:military_power"), ("rank:economy", "rank:economy_power"),
                        ("rank:tech", "rank:tech_power"), ("military", "military_power"), ("techs", "techs_known"),
                        ("planets", "colonies"), (" pops ", "pops")):
        assert spec.alias(alias) == real
    assert spec.row_keys == {"colonies": "planets"}
    assert (spec.min_milestones_top, spec.min_milestones_each, spec.min_milestones_first) == (0, 1, 2)
    assert (spec.min_goals, spec.min_goals_top, spec.stance_needs_figure) == (2, 3, True)
    assert spec.owners("market") == ["economy"] and spec.owners("tech") == ["technology"]
    m, t = spec.actions["market"], spec.actions["tech"]
    assert (m.field, m.max_items, m.amount_min, m.amount_max, m.sell_income_share, m.sell_requires_idle) == \
        ("market", 1, 1, 25, 0.2, True)
    manifest = tomllib.loads((REPO / "corpora/stellaris/manifest.toml").read_text(encoding="utf-8"))
    assert set(m.resources) == set(manifest["ui"]["market"]["resources"]) and "trade" not in m.resources
    assert (t.field, t.max_items, t.ids_from_corpus) == ("prefer_techs", 6, "tech")
    assert "Market orders cannot use trade" in m.note
    assert "the defence stance must name its exit condition" in spec.instructions


def test_public_view_lists_pillars_in_file_order_with_actions():
    pub = load_pillars(REPO / "corpora/stellaris").public()
    assert [p["id"] for p in pub["pillars"]][:3] == ["economy", "expansion", "technology"]
    assert pub["pillars"][0] == {"id": "economy", "label": "Economy", "description": pub["pillars"][0]["description"],
                                 "directive": "consolidate_economy", "actions": ["market"]}
    assert pub["actions"]["market"]["max_items"] == 1 and pub["actions"]["tech"]["field"] == "prefer_techs"


def test_a_minimal_file_loads(tmp_path):
    spec = load_pillars(corpus(tmp_path))
    assert spec.ids == ("economy", "society") and spec.directive_of("society") is None
    assert spec.alias("mil") == "military_power"


def test_unknown_keys_are_an_error_naming_the_key(tmp_path):
    with pytest.raises(PillarsError, match=r"pillars\.toml: pillars\.society\.colour: unknown key"):
        load_pillars(corpus(tmp_path, MINI.replace('label = "Society"', 'label = "Society"\ncolour = "red"')))
    with pytest.raises(PillarsError, match=r": extras: unknown key"):
        load_pillars(corpus(tmp_path, MINI + '\n[extras]\nx = 1\n'))
    with pytest.raises(PillarsError, match=r": actions\.market\.colour: unknown key"):
        load_pillars(corpus(tmp_path, MINI + 'colour = "red"\n'))


def test_a_directive_must_exist_in_directives_toml(tmp_path):
    with pytest.raises(PillarsError, match=r"pillars\.economy\.directive: 'hoard' is not a directive in directives\.toml"):
        load_pillars(corpus(tmp_path, MINI.replace('"consolidate_economy"', '"hoard"')))


def test_two_pillars_cannot_rank_the_same_directive(tmp_path):
    text = MINI.replace('description = "Pops."', 'description = "Pops."\ndirective = "consolidate_economy"')
    with pytest.raises(PillarsError, match="already ranked by pillar economy"):
        load_pillars(corpus(tmp_path, text))


def test_an_action_without_limits_is_an_error(tmp_path):
    with pytest.raises(PillarsError, match=r"pillars\.economy\.actions: action 'market' has no \[actions\.market\] limits"):
        load_pillars(corpus(tmp_path, MINI.split("[actions.market]")[0]))
    with pytest.raises(PillarsError, match=r"actions\.market\.amount_max: required limit is missing"):
        load_pillars(corpus(tmp_path, MINI.replace("amount_max = 25\n", "")))
    with pytest.raises(PillarsError, match=r"actions\.build: unknown action kind"):
        load_pillars(corpus(tmp_path, MINI + "\n[actions.build]\nmax_items = 1\n"))


def test_a_metric_alias_must_name_a_known_metric(tmp_path):
    with pytest.raises(PillarsError, match=r"strategy\.metric_aliases\.mil: alias to unknown metric 'might'"):
        load_pillars(corpus(tmp_path, MINI.replace('mil = "military_power"', 'mil = "might"')))


def test_reserved_and_invalid_pillar_ids_are_rejected(tmp_path):
    for bad in ("focus", "reason", "pillars", "copy", "model_x"):
        with pytest.raises(PillarsError, match=rf"pillars\.{bad}: pillar ids"):
            load_pillars(corpus(tmp_path, MINI.replace("[pillars.society]", f"[pillars.{bad}]")))


def test_min_milestones_top_is_at_most_the_pillar_count(tmp_path):
    with pytest.raises(PillarsError, match=r"strategy\.min_milestones_top: must be 0\.\.2"):
        load_pillars(corpus(tmp_path, MINI.replace("min_milestones_top = 1", "min_milestones_top = 3")))


def test_a_missing_file_is_an_error(tmp_path):
    d = tmp_path / "none"
    d.mkdir()
    with pytest.raises(PillarsError, match=r"pillars\.toml: missing"):
        load_pillars(d)


def test_loads_are_cached_until_the_file_changes(tmp_path):
    d = corpus(tmp_path)
    first = load_pillars(d)
    assert load_pillars(d) is first
    (d / "pillars.toml").write_text(MINI.replace('label = "Society"', 'label = "People"'), encoding="utf-8")
    st = (d / "pillars.toml").stat()
    os.utime(d / "pillars.toml", ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))
    assert load_pillars(d).pillars["society"].label == "People"


def test_cached_spec_is_read_only(tmp_path):
    """The cached spec's dicts are immutable to prevent process-wide cache poisoning."""
    d = corpus(tmp_path)          # written once: rewriting it would change the mtime and miss the cache
    spec = load_pillars(d)
    # Try to modify pillars dict
    with pytest.raises(TypeError):
        spec.pillars["economy"] = None
    # Try to modify metric_aliases dict
    with pytest.raises(TypeError):
        spec.metric_aliases["new"] = "alias"
    # Try to modify row_keys dict
    with pytest.raises(TypeError):
        spec.row_keys["new"] = "key"
    # Try to modify actions dict
    with pytest.raises(TypeError):
        spec.actions["new"] = None
    # Second load returns the same cached object
    second = load_pillars(d)
    assert second is spec
    assert second.pillars["economy"].label == "Economy"  # unchanged


def test_missing_directives_toml_gives_clear_error(tmp_path):
    """When directives.toml is missing, report it clearly instead of saying a directive doesn't exist."""
    d = tmp_path / "g"
    d.mkdir(exist_ok=True)
    shutil.copy(REPO / "corpora/stellaris" / "manifest.toml", d / "manifest.toml")
    (d / "pillars.toml").write_text(MINI, encoding="utf-8")
    # Don't copy directives.toml; let it be missing
    with pytest.raises(PillarsError, match=r"directives\.toml: missing"):
        load_pillars(d)


@pytest.mark.parametrize("line, where", [
    ("min_milestones_each = 7", "strategy.min_milestones_each: must be 0..6"),
    ("min_goals = 4", "strategy.min_goals: must be 0..3"),
    ("min_goals_top = 3", r"strategy.min_goals_top: must be 0..2"),
    ('stance_needs_figure = "yes"', "strategy.stance_needs_figure: must be true or false"),
])
def test_detail_rules_are_checked(tmp_path, line, where):
    with pytest.raises(PillarsError, match=re.escape(where)):
        load_pillars(corpus(tmp_path, MINI.replace("min_milestones_top = 1", f"min_milestones_top = 1\n{line}")))


# ---- [weights]: weight bounds, milestone need and how pressure acts (weighted pillars spec) ---------

def test_the_stellaris_weights_table():
    w = load_pillars(REPO / "corpora/stellaris").weights
    assert (w.mode, w.min, w.max, w.spread, w.switch_margin) == ("exclusive", 5, 50, 2.0, 1.25)
    assert w.need == {"met": 0.3, "on_track": 1.0, "at_risk": 1.5, "missed": 2.0}


def test_weights_default_when_the_table_is_absent(tmp_path):
    w = load_pillars(corpus(tmp_path)).weights
    assert (w.mode, w.min, w.max, w.spread, w.switch_margin) == ("exclusive", 0, 100, 1.0, 1.0)
    assert w.need == {"met": 1.0, "on_track": 1.0, "at_risk": 1.0, "missed": 1.0}


@pytest.mark.parametrize("table, where", [
    ('mode = "both"', 'weights.mode: must be "exclusive" or "share"'),
    ("min = 60", "weights.min: must be 0..50 (at most 100 / 2 pillars)"),
    ("max = 30", "weights.max: must be min..100 and leave room for 100 across 2 pillars"),
    ("spread = 0.5", "weights.spread: must be a number >= 1"),
    ("switch_margin = 0.9", "weights.switch_margin: must be a number >= 1"),
    ("colour = 1", "weights.colour: unknown key"),
    ("need = { met = -1 }", "weights.need.met: must be a number >= 0"),
    ("need = { soon = 1 }", "weights.need.soon: unknown key"),
])
def test_bad_weights_are_rejected(tmp_path, table, where):
    with pytest.raises(PillarsError, match=re.escape(where)):
        load_pillars(corpus(tmp_path, MINI + f"\n[weights]\n{table}\n"))


def test_the_stellaris_stall_rule():
    w = load_pillars(REPO / "corpora/stellaris").weights
    assert (w.stall_years, w.stall_factor) == (2.0, 0.5)


@pytest.mark.parametrize("table, where", [
    ("stall_years = -1", "weights.stall_years: must be a number >= 0"),
    ("stall_factor = 1.5", "weights.stall_factor: must be a number in (0, 1]"),
])
def test_bad_stall_rules_are_rejected(tmp_path, table, where):
    with pytest.raises(PillarsError, match=re.escape(where)):
        load_pillars(corpus(tmp_path, MINI + f"\n[weights]\n{table}\n"))


# ---- Civilization VI: share mode, no directives, id-list actions, turn dates -----------------------

def test_the_civ6_file_is_share_mode_with_order_actions():
    spec = load_pillars(REPO / "corpora/civ6")
    assert spec.game == "civ6"
    assert spec.ids == ("science", "culture", "faith", "economy", "military", "expansion", "diplomacy")
    assert all(spec.directive_of(p) is None for p in spec.ids)
    assert spec.weights.mode == "share" and spec.weights.stall_years == 0
    assert spec.date_format == "turns"
    assert {"science", "culture", "gold", "faith", "cities", "pop", "military", "score", "era_score",
            "techs_known", "civics_known", "rank:score", "rank:military"} <= set(spec.metrics)
    assert spec.owners("tech") == ["science"] and spec.owners("civic") == ["culture"]
    assert "military" in spec.owners("production") and "expansion" in spec.owners("production")
    assert set(spec.owners("purchase")) >= {"economy", "military"}
    fields = {k: a.field for k, a in spec.actions.items()}
    assert fields == {"tech": "prefer_techs", "civic": "prefer_civics", "policy": "prefer_policies",
                      "production": "prefer_production", "purchase": "prefer_purchases"}
    assert spec.actions["production"].ids_from_corpus == ("unit", "building", "district", "project")
    assert all(a.full_ids for a in spec.actions.values())
    buy = spec.actions["purchase"]
    assert buy.gold_reserve > 0 and buy.faith_reserve >= 0 and 0 < buy.treasury_share <= 0.5
    assert buy.threatened_share > buy.treasury_share
    assert all(a.max_orders >= 1 for a in spec.actions.values())
    assert "T60" in spec.instructions


def test_directives_toml_is_needed_only_when_a_pillar_ranks_a_directive(tmp_path):
    d = tmp_path / "g"
    d.mkdir()
    shutil.copy(REPO / "corpora/stellaris/manifest.toml", d / "manifest.toml")
    (d / "pillars.toml").write_text('[metrics]\nnames = ["cities"]\n[pillars.science]\nlabel = "Science"\n'
                                    'description = "Research."\n', encoding="utf-8")
    assert load_pillars(d).directive_of("science") is None


CIV_MINI = '''[strategy]
date_format = "turns"
[metrics]
names = ["cities", "gold"]
[weights]
mode = "share"
[pillars.economy]
label = "Economy"
description = "Gold."
actions = ["purchase", "production"]
[actions.purchase]
max_items = 3
max_orders = 1
ids_from_corpus = ["unit", "building"]
full_ids = true
gold_reserve = 100
faith_reserve = 0
treasury_share = 0.5
threatened_share = 0.9
[actions.production]
max_items = 4
ids_from_corpus = ["unit", "building", "district", "project"]
full_ids = true
'''


def civ_corpus(tmp_path, text=CIV_MINI):
    d = tmp_path / "c"
    d.mkdir(exist_ok=True)
    shutil.copy(REPO / "corpora/civ6/manifest.toml", d / "manifest.toml")
    (d / "pillars.toml").write_text(text, encoding="utf-8")
    return d


def test_a_minimal_civ6_style_file_loads(tmp_path):
    spec = load_pillars(civ_corpus(tmp_path))
    buy = spec.actions["purchase"]
    assert (buy.field, buy.max_orders, buy.gold_reserve, buy.treasury_share, buy.threatened_share) == \
        ("prefer_purchases", 1, 100, 0.5, 0.9)
    assert spec.actions["production"].max_orders == 1        # default: one order per decision


@pytest.mark.parametrize("old, new, where", [
    ('date_format = "turns"', 'date_format = "moons"', "strategy.date_format"),
    ("treasury_share = 0.5", "treasury_share = 1.5", "actions.purchase.treasury_share"),
    ("threatened_share = 0.9", "threatened_share = 0.2", "actions.purchase.threatened_share"),
    ("gold_reserve = 100", "gold_reserve = -1", "actions.purchase.gold_reserve"),
    ("max_orders = 1", "max_orders = 0", "actions.purchase.max_orders"),
    ('ids_from_corpus = ["unit", "building"]', 'ids_from_corpus = ["unit", "Bad!"]', "actions.purchase.ids_from_corpus"),
    ("full_ids = true\ngold", 'full_ids = "yes"\ngold', "actions.purchase.full_ids"),
    ("[actions.production]\nmax_items = 4", "[actions.production]\nmax_items = 4\ngold_reserve = 5",
     "actions.production.gold_reserve"),
])
def test_bad_civ6_limits_are_rejected(tmp_path, old, new, where):
    assert old in CIV_MINI
    with pytest.raises(PillarsError, match=re.escape(where)):
        load_pillars(civ_corpus(tmp_path, CIV_MINI.replace(old, new)))


def test_the_civ6_order_record_settings_load():
    orders = load_pillars(REPO / "corpora/civ6").orders
    assert (orders.window_turns, orders.min_resolved, orders.weak_rate, orders.open_cap_turns,
            orders.open_grace_turns) == (30, 8, 0.5, 20, 3)
    assert dict(orders.min_samples) == {"production": 4, "purchase": 4, "other": 3}
    assert (orders.min_samples_of("production replace"), orders.min_samples_of("purchase faith"),
            orders.min_samples_of("civic")) == (4, 4, 3)


def test_the_stellaris_action_record_counts_in_months():
    """Levers design ruling 5: 10 in-game years, widened to 6 judged, followed 24 months at most."""
    orders = load_pillars(REPO / "corpora/stellaris").orders
    assert (orders.window_turns, orders.min_resolved, orders.weak_rate, orders.open_cap_turns,
            orders.open_grace_turns) == (120, 6, 0.5, 24, 1)
    assert all(orders.min_samples_of(k) == 3 for k in ("directive tech_rush", "tech", "market buy food", "posture x"))


def test_a_file_without_an_orders_table_has_no_record(tmp_path):
    assert load_pillars(civ_corpus(tmp_path)).orders is None


@pytest.mark.parametrize("table, where", [
    ("[orders]\nwindow_turns = 0", "orders.window_turns"),
    ("[orders]\nmin_resolved = 1.5", "orders.min_resolved"),
    ("[orders]\nweak_rate = 1", "orders.weak_rate"),
    ("[orders]\nopen_grace_turns = 30", "orders.open_grace_turns"),
    ("[orders]\nmin_samples = { production = 0 }", "orders.min_samples.production"),
    ("[orders]\nmin_samples = { tactics = 2 }", "orders.min_samples.tactics"),
    ("[orders]\nhorizon = 3", "orders.horizon"),
])
def test_bad_order_record_settings_are_rejected(tmp_path, table, where):
    with pytest.raises(PillarsError, match=re.escape(where)):
        load_pillars(civ_corpus(tmp_path, CIV_MINI + table + "\n"))


def test_the_civ6_buy_out_rules_load():
    spec = load_pillars(REPO / "corpora/civ6")
    buy = spec.actions["purchase"]
    assert (buy.gold_reserve, buy.gold_reserve_per_deficit, buy.faith_reserve) == (30, 10.0, 0)
    assert (buy.pantheon_reserve, buy.prophet_faith_reserve, buy.skip_turns_left) == (True, 0, 2)
    assert buy.defence_first and buy.defence_cooldown_turns == 5
    assert buy.defender_classes == ("Melee", "Ranged", "Anti Cavalry", "Light Cavalry", "Heavy Cavalry")
    assert spec.milestone_exclude == ("gold", "faith")
    assert "walls" in buy.note.lower() and "cannot be bought" in buy.note
    stellaris = load_pillars(REPO / "corpora/stellaris")
    assert stellaris.milestone_exclude == () and "purchase" not in stellaris.actions


@pytest.mark.parametrize("line, where", [
    ("gold_reserve_per_deficit = -1", "actions.purchase.gold_reserve_per_deficit"),
    ('pantheon_reserve = "yes"', "actions.purchase.pantheon_reserve"),
    ("prophet_faith_reserve = 1.5", "actions.purchase.prophet_faith_reserve"),
    ("skip_turns_left = -2", "actions.purchase.skip_turns_left"),
    ("defence_first = 1", "actions.purchase.defence_first"),
    ('defender_classes = "Melee"', "actions.purchase.defender_classes"),
    ("defence_first = true", "actions.purchase.defender_classes"),       # needs the classes
    ("defence_cooldown_turns = -5", "actions.purchase.defence_cooldown_turns"),
    ("defence_now = true", "actions.purchase.defence_now"),
])
def test_bad_buy_out_rules_are_rejected(tmp_path, line, where):
    text = CIV_MINI.replace("threatened_share = 0.9\n", f"threatened_share = 0.9\n{line}\n")
    with pytest.raises(PillarsError, match=re.escape(where)):
        load_pillars(civ_corpus(tmp_path, text))


def test_milestone_exclude_names_known_metrics(tmp_path):
    ok = CIV_MINI.replace('names = ["cities", "gold"]', 'names = ["cities", "gold"]\nmilestone_exclude = ["gold"]')
    assert load_pillars(civ_corpus(tmp_path, ok)).milestone_exclude == ("gold",)
    bad = CIV_MINI.replace('names = ["cities", "gold"]', 'names = ["cities", "gold"]\nmilestone_exclude = ["faith"]')
    other = tmp_path / "other"          # a fresh file: loads are cached by path and modification time
    other.mkdir()
    with pytest.raises(PillarsError, match=re.escape("metrics.milestone_exclude")):
        load_pillars(civ_corpus(other, bad))


def test_the_public_view_shows_every_buy_out_rule_and_the_record_settings():
    pub = load_pillars(REPO / "corpora/civ6").public()
    buy = pub["actions"]["purchase"]
    assert buy["defender_classes"][0] == "Melee" and buy["prophet_faith_reserve"] == 0 and buy["pantheon_reserve"]
    assert pub["orders"]["window_turns"] == 30 and pub["milestone_exclude"] == ["gold", "faith"]
    assert load_pillars(REPO / "corpora/stellaris").public()["orders"]["open_cap_turns"] == 24


def test_directive_policies_come_from_the_directives_file():
    from pilot.pillars import load_directive_policies
    got = load_directive_policies(REPO / "corpora/stellaris")
    assert got["tech_rush"] == {"economic_policy": "economic_policy_civilian"}
    assert got["defend"] == {"diplomatic_stance": "diplo_stance_belligerent"}
    assert set(got) == {"expand", "consolidate_economy", "tech_rush", "prepare_war", "defend", "diplomacy_first"}


def test_stellaris_metrics_name_their_peer_median_keys():
    spec = load_pillars(REPO / "corpora/stellaris")
    assert dict(spec.peer_keys) == {"techs_known": "techs"}
    assert load_pillars(REPO / "corpora/civ6").peer_keys == {}


def test_a_peer_key_for_an_unknown_metric_is_rejected(tmp_path):
    with pytest.raises(PillarsError, match=re.escape("metrics.peer_keys.bogus")):
        load_pillars(civ_corpus(tmp_path, CIV_MINI.replace("[metrics]\n", '[metrics]\npeer_keys = { bogus = "x" }\n')))


# ---- Stellaris market buy rules (docs/design/2026-09-27-stellaris-levers-design.md, ruling 9) --------

def test_the_stellaris_market_buy_rules():
    spec = load_pillars(REPO / "corpora/stellaris")
    market = spec.actions["market"]
    buy = market.buy
    assert (market.amount_max, market.max_items) == (25, 1), "amounts and slots change only after live check L2"
    assert (buy.base_amount["energy"], buy.base_amount["consumer_goods"], buy.base_amount["alloys"],
            buy.base_amount["rare_crystals"], buy.base_amount["sr_zro"]) == (100, 50, 25, 10, 5)
    assert set(buy.base_amount) == set(market.resources), "every market resource has a base price"
    assert (buy.fee, buy.trade_reserve, buy.income_share, buy.crisis_income_share, buy.surplus_months) == (
        0.3, 2500, 0.25, 0.5, 24)
    assert (buy.skip_above_pct, buy.never_above_pct) == (50, 100)
    assert dict(buy.volume) == {"internal": 1, "galactic": 6}
    assert (buy.ai_cover_months, buy.cover_months, buy.strategic_cover_months) == (6, 24, 36)
    assert buy.strategic == ("volatile_motes", "exotic_gases", "rare_crystals")
    assert (buy.naval_full, buy.cover_factor, buy.idle_fill) == (0.95, 1.2, True)
    assert spec.public()["actions"]["market"]["buy"]["trade_reserve"] == 2500


def test_a_market_table_without_buy_rules_has_none(tmp_path):
    assert load_pillars(corpus(tmp_path)).actions["market"].buy is None


_BUY = "\n[actions.market.buy]\nbase_amount = { energy = 100, alloys = 25 }\n"


@pytest.mark.parametrize("table, where", [
    ("\n[actions.market.buy]\nfee = 0.3\n", "actions.market.buy.base_amount: required"),
    ("\n[actions.market.buy]\nbase_amount = { energy = 0 }\n", "actions.market.buy.base_amount.energy"),
    ("\n[actions.market.buy]\nbase_amount = { gold = 10 }\n", "actions.market.buy.base_amount.gold"),
    (_BUY + "fee = 1.5\n", "actions.market.buy.fee"),
    (_BUY + "trade_reserve = -1\n", "actions.market.buy.trade_reserve"),
    (_BUY + "income_share = 0\n", "actions.market.buy.income_share"),
    (_BUY + "crisis_income_share = 0.1\n", "actions.market.buy.crisis_income_share"),
    (_BUY + "never_above_pct = 40\n", "actions.market.buy.never_above_pct"),
    (_BUY + "volume = { internal = 0 }\n", "actions.market.buy.volume.internal"),
    (_BUY + "volume = { lunar = 1 }\n", "actions.market.buy.volume.lunar"),
    (_BUY + "cover_months = 3\n", "actions.market.buy.cover_months"),
    (_BUY + 'strategic = ["gold"]\n', "actions.market.buy.strategic"),
    (_BUY + "naval_full = 1.5\n", "actions.market.buy.naval_full"),
    (_BUY + "idle_fill = 1\n", "actions.market.buy.idle_fill"),
    (_BUY + "colour = 1\n", "actions.market.buy.colour: unknown key"),
])
def test_bad_buy_rules_are_rejected(tmp_path, table, where):
    with pytest.raises(PillarsError, match=re.escape(where)):
        load_pillars(corpus(tmp_path, MINI + table))
