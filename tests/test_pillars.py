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
