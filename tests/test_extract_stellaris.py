import importlib.util
import json
import sys

import pytest

from pilot.config import REPO

spec = importlib.util.spec_from_file_location("xs", REPO / "scripts/extract-stellaris.py")
xs = importlib.util.module_from_spec(spec)
sys.modules["xs"] = xs            # @dataclass needs the module registered
spec.loader.exec_module(xs)


def test_parse_blocks_operators_comments_and_lists():
    b = xs.parse('''
@tier1cost3 = 1500   # a constant
tech_a = {
    area = physics
    category = { field_manipulation }
    cost = @tier1cost3
    prerequisites = { "tech_x" "tech_y" }
    potential = { years_passed > 5 is_ai = no }  # trailing comment
    name = "quoted # not a comment"
}
''')
    assert xs.get(b, "@tier1cost3") == "1500"
    t = xs.get(b, "tech_a")
    assert xs.get(t, "area") == "physics"
    assert xs.values(xs.get(t, "category")) == ["field_manipulation"]
    assert xs.values(xs.get(t, "prerequisites")) == ["tech_x", "tech_y"]
    pot = xs.get(t, "potential")
    assert (pot[0].key, pot[0].op, pot[0].value) == ("years_passed", ">", "5")
    assert xs.get(t, "name") == "quoted # not a comment"


def test_parse_tolerates_stray_braces_and_bom():
    b = xs.parse('﻿a = { b = 1 } } c = 2 d = { e = 3')
    assert xs.get(b, "a")[0].value == "1" and xs.get(b, "c") == "2"
    assert xs.get(xs.get(b, "d"), "e") == "3"


def test_render_is_compact_and_resolves_variables():
    b = xs.parse("x = { add_resource = { energy = @big } modifier = { country_naval_cap_mult = 0.1 } }")
    s = xs.render(xs.get(b, "x"), {"@big": "500"})
    assert s == "add_resource = { energy = 500 } modifier = { country_naval_cap_mult = 0.1 }"
    assert len(xs.render(xs.parse("a = { " + "b = 1 " * 500 + "}"), {}, limit=100)) <= 101


def test_localisation_cleans_codes_icons_and_references():
    loc = xs.Loc()
    loc.load_text('''﻿l_english:
 # comment
 energy:0 "Energy"
 tech_x:1 "§YLaser§! Weapons"
 tech_x_desc:0 "Costs £energy£ 5 and $energy$. [Root.GetName] rules."
 plain: "no version number"
''')
    assert loc("tech_x") == "Laser Weapons"
    assert loc("tech_x_desc") == "Costs energy 5 and Energy. … rules."
    assert loc("plain") == "no version number"
    assert loc("missing_key") is None


def test_extract_end_to_end_on_a_tiny_install(tmp_path):
    root = tmp_path / "stl"
    (root / "common/technology").mkdir(parents=True)
    (root / "common/scripted_variables").mkdir(parents=True)
    (root / "common/policies").mkdir(parents=True)
    (root / "events").mkdir(parents=True)
    (root / "localisation/english").mkdir(parents=True)
    (root / "common/scripted_variables/00.txt").write_text("@tier1cost3 = 1500\n")
    (root / "common/technology/00_phys.txt").write_text('''
tech_basic = { area = physics tier = 0 cost = 0 start_tech = yes }
tech_physics_1 = { area = physics category = { field_manipulation } tier = 1 cost = @tier1cost3
                   prerequisites = { "tech_basic" } }
''')
    (root / "common/policies/00.txt").write_text('''
diplomatic_stance = { category = diplomacy allow = { is_at_war = no }
  option = { name = "diplo_stance_cooperative" modifier = { country_trust_growth = 0.5 } }
  option = { name = "diplo_stance_isolationist" } }
''')
    (root / "events/test.txt").write_text('''
namespace = test
country_event = { id = test.1 title = test.1.name desc = test.1.desc
  option = { name = test.1.a add_resource = { energy = 100 } }
  option = { name = test.1.b custom_tooltip = test.1.b.tt hidden_effect = { set_country_flag = x } } }
country_event = { id = test.2 hide_window = yes is_triggered_only = yes immediate = { } }
''')
    (root / "localisation/english/t_l_english.yml").write_text('''l_english:
 tech_physics_1:0 "Administrative AI"
 tech_physics_1_desc:0 "Better paperwork."
 tech_basic:0 "Basic Science"
 field_manipulation:0 "Field Manipulation"
 diplomatic_stance:0 "Diplomatic Stance"
 diplo_stance_cooperative:0 "Cooperative"
 diplo_stance_cooperative_desc:0 "We want friends."
 test.1.name:0 "A Strange Signal"
 test.1.desc:0 "Scientists detect a signal."
 test.1.a:0 "Study it"
 test.1.b:0 "Ignore it"
 test.1.b.tt:0 "Nothing happens."
''')
    (root / "launcher-settings.json").write_text(json.dumps({"rawVersion": "v4.5.1"}))
    (root / "dlc.json").write_text('["dlc014_utopia"]')
    out = tmp_path / "data"
    assert xs.main([str(root), "--out", str(out)]) == 0

    tech = {r["id"]: r for r in json.loads((out / "tech.json").read_text())}
    t = tech["tech:tech_physics_1"]
    assert t["name"] == "Administrative AI" and t["summary"] == "Better paperwork."
    assert t["fields"]["cost"] == 1500 and t["fields"]["prerequisites"] == ["Basic Science"]
    assert t["fields"]["category"] == ["Field Manipulation"] and "tech_physics_1" in t["aliases"]
    assert tech["tech:tech_basic"]["fields"]["leads_to"] == ["Administrative AI"]

    pol = json.loads((out / "policy.json").read_text())[0]
    assert pol["name"] == "Diplomatic Stance" and "diplo_stance_cooperative" in pol["aliases"]
    assert pol["fields"]["options"][0].startswith("Cooperative (diplo_stance_cooperative): We want friends.")
    assert "country_trust_growth = 0.5" in pol["fields"]["options"][0]

    ev = json.loads((out / "event.json").read_text())
    assert [e["id"] for e in ev] == ["event:test.1"], "hidden events are skipped"
    ch = ev[0]["fields"]["choices"]
    assert ch[0] == "1. Study it -> add_resource = { energy = 100 }"
    assert ch[1].startswith("2. Ignore it -> Nothing happens.")
    meta = json.loads((out / "_meta.json").read_text())
    assert meta["game_version"] == "v4.5.1" and meta["counts"]["tech"] == 2 and meta["dlc"] == ["dlc014_utopia"]


@pytest.mark.skipif(not (REPO / "incoming/stellaris/common").exists(), reason="game files not fetched")
def test_real_files_parse_without_errors():
    loc = xs.Loc()
    loc.load_dir(REPO / "incoming/stellaris/localisation/english")
    assert loc("tech_physics_1")


def test_species_traits_and_planet_classes(tmp_path):
    root = tmp_path / "stl"
    (root / "common/traits").mkdir(parents=True)
    (root / "common/planet_classes").mkdir(parents=True)
    (root / "localisation/english").mkdir(parents=True)
    (root / "common/traits/04_species_traits.txt").write_text('''
trait_adaptive = { cost = 2 opposites = { "trait_nonadaptive" } allowed_archetypes = { BIOLOGICAL }
  tags = { organic positive habitability } modifier = { pop_environment_tolerance = 0.10 } }
''')
    (root / "common/traits/00_scientist_traits.txt").write_text('''
leader_trait_curator = { leader_class = { scientist } cost = 1 modifier = { x = 1 } }
''')
    (root / "common/planet_classes/00.txt").write_text('''
pc_continental = { climate = "wet" colonizable = yes }
pc_toxic = { colonizable = no }
pc_habitat = { climate = "artificial" colonizable = yes }
''')
    (root / "localisation/english/t_l_english.yml").write_text('''l_english:
 trait_adaptive:0 "Adaptive"
 trait_adaptive_desc:0 "Handles many climates."
 pc_continental:0 "Continental"
''')
    out = tmp_path / "data"
    assert xs.main([str(root), "--out", str(out)]) == 0
    traits = json.loads((out / "trait.json").read_text())
    assert [t["id"] for t in traits] == ["trait:trait_adaptive"], "leader traits are skipped"
    t = traits[0]
    assert t["name"] == "Adaptive" and t["fields"]["cost"] == 2
    assert "pop_environment_tolerance = 0.10" in t["fields"]["modifier"]
    assert t["fields"]["opposites"] == ["trait_nonadaptive"] and t["fields"]["archetypes"] == ["BIOLOGICAL"]
    pcs = {p["id"]: p for p in json.loads((out / "planet_class.json").read_text())}
    assert set(pcs) == {"planet_class:pc_continental", "planet_class:pc_habitat"}, "only colonizable classes"
    assert pcs["planet_class:pc_continental"]["fields"]["climate"] == "wet"
