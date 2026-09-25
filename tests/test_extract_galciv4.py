import importlib.util
import json
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
    assert cp["fields"]["unlocks"] == ["Executive order: Draft Colonists", "Improvement: Manufacturing District"]
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


def test_meta_records_provenance(out):
    m = out["_meta"]
    assert m["tech_tree"] == "HumanTechTree" and m["game_version"] == "t"
    assert m["counts"] == {"tech": 2, "improvement": 7, "order": 1}
    assert m["generator"].startswith("scripts/extract-galciv4.py@")


def test_output_loads_in_the_rust_corpus(out, tmp_path):
    """The generated files must satisfy the controller's loader contract (name present, ids unique)."""
    ctl = ROOT / "target" / "release" / "game-controller"
    if not ctl.exists():
        pytest.skip("release controller not built")
    corpus = tmp_path / "corpus"
    (corpus / "data").mkdir(parents=True)
    (corpus / "manifest.toml").write_text((ROOT / "corpora/galciv4/manifest.toml").read_text())
    for kind in ("tech", "improvement", "order"):
        (corpus / "data" / f"{kind}.json").write_text(json.dumps(out[kind]))
    r = subprocess.run([str(ctl), "--corpus", str(corpus), "corpus", "tech", "colonial policy"],
                       capture_output=True, text=True, check=False)
    assert r.returncode == 0, r.stderr
    assert "**Colonial Policies** (tech)" in r.stdout and "- cost: 27" in r.stdout, r.stdout
