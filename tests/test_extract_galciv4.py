import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "extract-galciv4.py"
FIXTURE = ROOT / "tests" / "fixtures" / "galciv4"

spec = importlib.util.spec_from_file_location("extract_galciv4", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    out = tmp_path_factory.mktemp("data")
    r = subprocess.run([sys.executable, str(SCRIPT), str(FIXTURE), "--out", str(out), "--game-version", "t"],
                       capture_output=True, text=True, cwd=ROOT, check=False)
    assert r.returncode == 0, r.stderr
    return {p.stem: json.loads(p.read_text()) for p in out.glob("*.json")}


def by_id(records, id_):
    return next(r for r in records if r["id"] == id_)


def test_clean_strips_markup():
    assert mod.clean("[ICON=Stat_Manufacturing_Icon] Manufacturing") == "Manufacturing"
    assert mod.clean("Expand [COLOR=Gold]policies[/COLOR].") == "Expand policies ."
    assert mod.clean("grows <i>fast</i>") == "grows fast"
    assert mod.clean(None) == ""


def test_only_the_requested_tree_is_exported_and_root_is_skipped(out):
    ids = [r["id"] for r in out["tech"]]
    assert ids == ["tech:colonial_policies", "tech:planetary_improvements"], ids
    cp = by_id(out["tech"], "tech:colonial_policies")
    assert cp["fields"]["cost"] == 27, "Human tree cost, not the Master tree's 99"
    assert cp["fields"]["tree"] == "HumanTechTree"


def test_tech_prerequisites_effects_unlocks_and_text(out):
    cp = by_id(out["tech"], "tech:colonial_policies")
    assert cp["summary"] == "Expand our capacity for policies ."
    assert cp["fields"]["description"] == "Colonial bureaucracy grows with us."
    assert cp["fields"]["prerequisites"] == ["Planetary Improvements"], "resolved via GenericName"
    assert cp["fields"]["age"] == "Age Of Expansion"
    assert cp["fields"]["effects"] == ["+1 Policy Slots"]
    assert cp["fields"]["unlocks"] == [
        "Executive order: Draft Colonists",
        "Improvement: Manufacturing District",
        "Policy: Research Grants",
        "Ship component: Hull Plating",
        "Starbase module: Interstellar Exchange",
    ]
    assert set(cp["aliases"]) == {"HumanTech_ColonialPolicies", "Tech_ColonialPolicies"}


def test_improvement_costs_are_split_from_effects(out):
    md = by_id(out["improvement"], "improvement:manufacturing_district")
    f = md["fields"]
    assert f["cost"] == "60" and f["maintenance"] == "1"
    assert f["resources"] == ["5 Durantium"]
    assert f["effects"] == ["+20% Manufacturing (Colony)", "-5% Approval (Colony)"], f["effects"]
    assert f["per_level"] == ["+2.5% Manufacturing (Colony)"]
    assert f["adjacency"] == ["+3 to adjacent Manufacturing"]
    assert f["requires_tech"] == ["Colonial Policies"]
    assert f["type"] == "Manufacturing" and f["placement"] == "Manufacturing Hub"
    assert f["source"] == "ImprovementDefs.xml"
    wonder = by_id(out["improvement"], "improvement:synth_foundry")
    assert wonder["fields"]["unique"] == "one per civilization"
    assert wonder["fields"]["requires_trait"] == ["Synthetic Life"]


def test_order_resolves_name_and_effects_through_artifact_power(out):
    eo = by_id(out["order"], "order:draft_colonists")
    assert eo["name"] == "Draft Colonists"
    f = eo["fields"]
    assert f["control_cost"] == "33" and f["cooldown_turns"] == "12" and "credits_cost" not in f
    assert f["effects"] == ["-2% Approval (Unit) for 10 turns", "Award Colony Ship With Passenger (1, Unit_Colonist)"]
    assert f["requires_tech"] == ["Colonial Policies"]
    assert f["blocked_by_trait"] == ["Slavers Ability"]
    assert eo["summary"].startswith("Sometimes we can't afford")


def test_collisions_prefer_real_and_human_variants_and_keep_tiers(out):
    eo = by_id(out["order"], "order:draft_colonists")
    assert eo["fields"]["control_cost"] == "33", "tutorial (15) and synth (99) variants must lose"
    assert set(eo["aliases"]) == {"EO_DraftColonists", "EO_DraftColonists_TutorialVariant", "EO_Synth_DraftColonists"}
    md = by_id(out["improvement"], "improvement:manufacturing_district")
    assert "requires_trait" not in md["fields"], "the Synthetic variant must not replace the base district"
    tiers = sorted(r["id"] for r in out["improvement"] if r["name"] == "Upgrade Wealth")
    assert tiers == ["improvement:upgrade_wealth_1", "improvement:upgrade_wealth_2"]
    t1 = by_id(out["improvement"], "improvement:upgrade_wealth_1")
    assert t1["fields"]["variant"] == "Project_UpgradeWealth1_Human"
    assert "description" not in t1["fields"], "an unresolved label must not leak as text"
    nanites = sorted(r["id"] for r in out["improvement"] if r["name"] == "Precursor Nanites")
    assert nanites == ["improvement:precursor_nanites_0", "improvement:precursor_nanites_1", "improvement:precursor_nanites_2"]
    assert len({r["id"] for r in out["improvement"]}) == len(out["improvement"]), "ids must be unique"


def test_policy_costs_prereqs_and_terran_variant(out):
    rg = by_id(out["policy"], "policy:research_grants")
    assert rg["fields"]["effects"] == ["+20% Research (Colony)"], "Terran variant (20%) beats the base (50%)"
    assert rg["fields"]["source"] == "PolicyDefs_Terrans.xml"
    assert set(rg["aliases"]) == {"Policy_ResearchGrants", "Policy_Terran_ResearchGrants"}
    assert rg["fields"]["requires_tech"] == ["Colonial Policies"]
    assert rg["summary"] == "Fund the sciences ."
    act = by_id(out["policy"], "policy:draft_act")["fields"]
    assert act["type"] == "Accord" and act["cost"] == "40 Consensus"
    assert act["authority_cost"] == "10" and act["maturity_turns"] == "12"
    assert act["grants_order"] == "Draft Colonists", "resolved through the executive order's artifact power"
    assert act["requires_government"] == ["Federation"] and act["requires_policy"] == ["Research Grants"]
    ge = by_id(out["policy"], "policy:the_great_expansion")["fields"]
    assert ge["upkeep"] == "2"
    assert ge["effects"] == ["+200% Growth (Colony, capital world only)"], "no repeal trigger, no flag bookkeeping"
    assert ge["requires_trait"] == ["Wealthy Ability"] and ge["blocked_by_trait"] == ["Slavers Ability"]


def test_ship_component_cost_mass_and_effects(out):
    hp = by_id(out["ship_component"], "ship_component:hull_plating")["fields"]
    assert hp["cost"] == "10" and hp["mass"] == "2 + 5% of hull" and hp["resources"] == ["2 Elerium"]
    assert hp["effects"] == ["+2 Armor Rating (Ship)"], "AI Threat stat is not an effect"
    assert hp["category"] == "Defenses" and hp["type"] == "Armor" and hp["slot"] == "Defense"
    assert hp["limit"] == "one per ship" and hp["requires_tech"] == ["Colonial Policies"]
    md = by_id(out["ship_component"], "ship_component:mass_driver")["fields"]
    assert md["cost"] == "13" and md["mass"] == "5" and md["effects"] == ["+4 Kinetic Attack (Ship)"]
    assert md["source"] == "ShipComponents_Weapons.xml"
    sm = by_id(out["ship_component"], "ship_component:supply_module")["fields"]
    assert sm["effects"] == ["+100 Manufacturing Overflow (Colony) on supply reached colony"]
    names = {r["name"] for r in out["ship_component"]}
    assert "Frigate Module" not in names, "Hidden-category components are not offered to players"
    fg = sorted(r["id"] for r in out["ship_component"] if r["name"] == "Field Generator")
    assert fg == ["ship_component:field_generator_0", "ship_component:field_generator_tech"]


def test_starbase_module_costs_upgrades_and_variants(out):
    ex = by_id(out["starbase_module"], "starbase_module:interstellar_exchange")
    f = ex["fields"]
    assert ex["summary"] == "Boosts influence nearby." and f["description"] == "A cultural hub."
    assert f["module_cost"] == "1" and f["maintenance"] == "1" and f["resources"] == ["1 Durantium"]
    assert f["effects"] == ["+10% Influence Per Turn (Colony)"] and f["specialization"] == "Culture"
    assert f["requires_tech"] == ["Colonial Policies"]
    assert "SynthInterstellarExchangeModule" in ex["aliases"], "lower-case synth file is read, its variant loses"
    emb = by_id(out["starbase_module"], "starbase_module:interstellar_embassy")
    assert emb["fields"]["upgrades_from"] == ["Interstellar Exchange"]
    red = by_id(out["starbase_module"], "starbase_module:dyson_sphere_red")["fields"]
    assert red["resources"] == ["10 Energy"] and red["effects"] == ["+20 Energy Generation"]
    assert red["star_type"] == ["Red Star"] and red["limit"] == "one per nexus type"
    assert red["dlc"] == "Mega Structures" and red["turns_to_build"] == "8"
    assert any(r["id"] == "starbase_module:dyson_sphere_blue" for r in out["starbase_module"])


def test_event_choices_spell_out_outcomes(out):
    ev = by_id(out["event"], "event:precursor_probe_0")
    assert ev["name"] == "Precursor Probe" and ev["summary"].endswith("orbiting {PLANETNAME}.")
    assert ev["fields"]["type"] == "Crisis Event" and ev["fields"]["once_per_player"] == "yes"
    assert ev["fields"]["choices"] == [
        "1. Let's study this and see what we can learn. -> +200 Credits (one-time); +1 Sensor Power (Ship) (permanent)",
        (
            "2. Repair the Probe and see what it does. [Unlock the Stargazer ship] -> "
            "+10% Approval (Colony) for 10 turns; Award Improvement (Manufacturing District)"
        ),
    ]


def test_event_variants_are_kept_and_exact_copies_merged(out):
    ids = sorted(r["id"] for r in out["event"])
    assert ids == ["event:precursor_probe_0", "event:precursor_probe_echo"], "Test*.xml events are skipped"
    echo = by_id(out["event"], "event:precursor_probe_echo")
    assert echo["aliases"] == ["Event_PrecursorProbe_Echo", "Event_PrecursorProbe_EchoCopy"]
    assert echo["fields"]["choices"] == ["1. Listen to the echo."]


def test_all_ids_unique_and_names_resolved(out):
    for kind in ("tech", "improvement", "order", "policy", "ship_component", "starbase_module", "event"):
        ids = [r["id"] for r in out[kind]]
        assert len(ids) == len(set(ids)), kind
        assert all(r["id"].startswith(f"{kind}:") for r in out[kind]), kind
        bad = [r["name"] for r in out[kind] if "_" in r["name"] or r["name"].endswith("Name")]
        assert not bad, (kind, bad)


def test_meta_records_provenance(out):
    m = out["_meta"]
    assert m["tech_tree"] == "HumanTechTree" and m["game_version"] == "t"
    assert m["counts"] == {
        "tech": 2,
        "improvement": 7,
        "order": 1,
        "policy": 3,
        "ship_component": 5,
        "starbase_module": 5,
        "event": 2,
    }
    assert m["generator"].startswith("scripts/extract-galciv4.py@")


def test_output_loads_in_the_rust_corpus(out, tmp_path):
    """The generated files must satisfy the controller's loader contract (name present, ids unique)."""
    ctl = ROOT / "target" / "release" / "game-controller"
    if not ctl.exists():
        pytest.skip("release controller not built")
    corpus = tmp_path / "corpus"
    (corpus / "data").mkdir(parents=True)
    (corpus / "manifest.toml").write_text((ROOT / "corpora/galciv4/manifest.toml").read_text())
    for kind in ("tech", "improvement", "order", "policy", "ship_component", "starbase_module", "event"):
        (corpus / "data" / f"{kind}.json").write_text(json.dumps(out[kind]))
    # The CLI insists on an agent token even for offline corpus commands; none is used here.
    env = {**os.environ, "GAME_AGENT_TOKEN": os.environ.get("GAME_AGENT_TOKEN", "unused")}
    r = subprocess.run([str(ctl), "--corpus", str(corpus), "corpus", "tech", "colonial policy"],
                       capture_output=True, text=True, check=False, env=env)
    assert r.returncode == 0, r.stderr
    assert "**Colonial Policies** (tech)" in r.stdout and "- cost: 27" in r.stdout, r.stdout
    r = subprocess.run([str(ctl), "--corpus", str(corpus), "corpus", "get", "event:precursor_probe_0"],
                       capture_output=True, text=True, check=False, env=env)
    assert r.returncode == 0, r.stderr
    assert "**Precursor Probe** (event)" in r.stdout and "Sensor Power" in r.stdout, r.stdout


def test_corpus_cli_works_without_an_agent_token(tmp_path):
    """`game-controller corpus ...` reads local files only and must not require GAME_AGENT_TOKEN."""
    ctl = ROOT / "target" / "release" / "game-controller"
    if not ctl.exists():
        pytest.skip("release controller not built")
    env = {k: v for k, v in __import__("os").environ.items() if k != "GAME_AGENT_TOKEN"}
    r = subprocess.run([str(ctl), "--corpus", str(ROOT / "corpora/galciv4"), "corpus", "search", "draft colonists"],
                       capture_output=True, text=True, cwd=tmp_path, env=env, check=False)
    assert r.returncode == 0, r.stderr
    assert "order:draft_colonists" in r.stdout
