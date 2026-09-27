"""scripts/extract-civ6.py on hand-written fixtures (tests/fixtures/civ6, the install's layout)."""
import importlib.util
import json
import re
import sys

from pilot.config import REPO

spec = importlib.util.spec_from_file_location("xc6", REPO / "scripts/extract-civ6.py")
xc6 = importlib.util.module_from_spec(spec)
sys.modules["xc6"] = xc6
spec.loader.exec_module(xc6)

FIX = REPO / "tests/fixtures/civ6"


def build(modes=None):
    rdb, mods, crit = xc6.build_db(FIX, modes=modes)
    warnings = list(rdb.warnings)
    loc = xc6.build_loc(FIX, mods, crit, warnings)
    return rdb, xc6.Extractor(rdb, loc), warnings


def strings(v):
    if isinstance(v, str):
        yield v
    elif isinstance(v, list):
        for x in v:
            yield from strings(x)
    elif isinstance(v, dict):
        for x in v.values():
            yield from strings(x)


def cost(rdb, tech):
    row = rdb.db.execute("SELECT Cost FROM Technologies WHERE TechnologyType=?", (tech,)).fetchone()
    return row[0] if row else None


def test_layering_update_delete_replace_and_load_order():
    rdb, _, warnings = build()
    # Writing: base 50 -> Expansion2 Update 55 -> APack (LoadOrder 100, after XP2's -100) 60.
    # The Rise and Fall-only action (777) and the scenario (deletes every tech) are not applied.
    assert cost(rdb, "TECH_WRITING") == 60
    # Deleting the Types row cascades to Technologies and to the prerequisite that named it.
    assert cost(rdb, "TECH_OLD_LORE") is None
    prereqs = rdb.db.execute("SELECT PrereqTech FROM TechnologyPrereqs WHERE Technology='TECH_WRITING'").fetchall()
    assert [p[0] for p in prereqs] == ["TECH_POTTERY"]
    # Priority 2 (RemoveData: Update Cost=999) runs before Priority 1 (Replace the whole row).
    legion = rdb.db.execute("SELECT Cost, StrategicResource FROM Units WHERE UnitType='UNIT_ROMAN_LEGION'").fetchone()
    assert tuple(legion) == (110, "RESOURCE_IRON")
    # Game-mode files load only when asked for.
    assert cost(rdb, "TECH_POTTERY") == 25
    assert cost(build(modes={"heroes"})[0], "TECH_POTTERY") == 1
    # The Types insert trigger ran with the Make_Hash function the schema expects.
    assert rdb.db.execute("SELECT count(*) FROM TypeHashes WHERE Hash != 0").fetchone()[0] == 4
    assert any("UpdateText files not present" in w for w in warnings)


def test_schema_xml_tables_are_created():
    rdb, _, _ = build()
    row = rdb.db.execute("SELECT Leader, Sort, Tooltip FROM LeaderNotes").fetchone()
    assert tuple(row) == ("LEADER_TRAJAN", 0, None)           # an empty default is NULL
    assert not rdb.unknown_tables and not rdb.unknown_columns and not rdb.stats.get("failed_ops")


def test_broken_extract_fails_unless_lenient(tmp_path):
    import shutil
    root = tmp_path / "civ6"
    shutil.copytree(FIX, root)
    (root / "Base/Assets/Gameplay/Data/Renamed.xml").write_text(
        '<GameData><Technologies><Row TechnologyType="TECH_X" CostRenamed="5"/></Technologies>'
        "<NoSuchTable><Row A=\"1\"/></NoSuchTable></GameData>")
    (root / "Base/Assets/Text/en_US/Broken.xml").write_text("<GameData><BaseGameText><Row")
    out = tmp_path / "data"
    assert xc6.main([str(root), "--out", str(out)]) == 1
    assert not out.exists()
    assert xc6.main([str(root), "--out", str(out), "--lenient"]) == 0
    warnings = json.loads((out / "_meta.json").read_text())["warnings"]
    assert any("Technologies.CostRenamed" in w for w in warnings)
    assert any("NoSuchTable" in w for w in warnings)
    assert any("text XML Broken.xml" in w for w in warnings)


def test_criteria_any_and_all():
    crit = xc6.Criteria("RULESET_EXPANSION_2", {"abc"}, set())
    parse = xc6.ET.fromstring
    assert crit(parse('<Criteria any="1"><RuleSetInUse>RULESET_STANDARD</RuleSetInUse>'
                      '<ModInUse>ABC</ModInUse></Criteria>'))
    assert not crit(parse('<Criteria><RuleSetInUse>RULESET_EXPANSION_2</RuleSetInUse>'
                          '<ModInUse>missing</ModInUse></Criteria>'))
    assert crit(parse("<Criteria><LeaderPlayable>Players:Expansion2_Players::LEADER_X</LeaderPlayable></Criteria>"))
    assert not crit(parse("<Criteria><LeaderPlayable>Players:StandardPlayers::LEADER_X</LeaderPlayable></Criteria>"))
    assert not crit(parse("<Criteria><GameCoreInUse>Expansion1</GameCoreInUse></Criteria>"))
    assert crit(None) and crit(parse("<Criteria/>"))


def test_localisation_layering_and_cleaning():
    _, x, _ = build()
    loc = x.loc
    assert loc("LOC_UNIT_ROMAN_LEGION_DESCRIPTION").startswith("Roman unique melee unit")   # DLC Replace
    assert loc("LOC_BOOST_TRIGGER_WRITING") == "Meet another civilization."                  # DLC Update
    assert loc("LOC_DELETED_LATER") is None                                                  # DLC Delete
    assert loc("LOC_TECH_WRITING_NAME") == "Writing"                                         # fr_FR row ignored
    # icons that repeat the next word disappear, [NEWLINE] becomes a space
    assert loc("LOC_TRAIT_ALL_ROADS_DESCRIPTION") == \
        "Your Trade Routes earn +1 Gold. Cities start with a Trading Post."
    assert loc.clean("+4 [ICON_Strength]") == "+4 Combat Strength"
    assert loc.clean("Found {1_CivName} in {1_Num} turns.") == "Found [CivName] in N turns."
    assert loc.clean("{Amount : plural 1?tile; other?tiles;}", {"Amount": "1"}) == "tile"
    assert loc.clean("{Amount : number #} Gold", {"Amount": "200"}) == "200 Gold"


def test_unique_unit_is_tagged_with_its_civ():
    _, x, _ = build()
    legion = next(r for r in x.unit() if r["id"] == "unit:roman_legion")
    assert legion["name"] == "Legion"
    assert "UNIT_ROMAN_LEGION" in legion["aliases"]
    assert legion["fields"]["unique_to"] == "Rome"
    assert legion["fields"]["replaces"] == "Swordsman"
    assert legion["summary"].startswith("Unique to Rome, replaces Swordsman")
    rome = next(r for r in x.civ() if r["id"] == "civ:rome")
    assert rome["fields"]["uniques"] == ["Legion (unit, replaces Swordsman)"]
    assert rome["fields"]["ability"] == [
        "All Roads Lead to Rome: Your Trade Routes earn +1 Gold. Cities start with a Trading Post."]
    scientist = next(r for r in x.unit() if r["id"] == "unit:great_scientist")
    assert scientist["fields"]["can_train"] == "no"


def test_modifier_strings_render_great_person_actions():
    _, x, _ = build()
    hyp = next(r for r in x.great_person() if r["id"] == "great_person:hypatia")
    assert hyp["fields"]["action"] == ("Library buildings provide +1 Science. "
                                       "Triggers the Eureka for 2 random technologies.")
    assert hyp["fields"]["action_requires"] == ["owned tile", "completed district type: Campus"]
    assert hyp["summary"].startswith("Great Scientist, Classical Era.")


def test_tech_eureka_unlocks_and_effect_phrases():
    _, x, _ = build()
    writing = next(r for r in x.tech() if r["id"] == "tech:writing")
    f = writing["fields"]
    assert f["cost"] == 60 and f["era"] == "Ancient Era"
    assert f["prerequisites"] == ["Pottery"]
    assert f["eureka"] == "Meet another civilization. (40%)"
    assert f["unlocks"] == ["Campus (district)"]
    iron = next(r for r in x.tech() if r["id"] == "tech:iron_working")
    assert "Legion (unit, unique: Rome)" in iron["fields"]["unlocks"]
    assert f["effects"] == ["+1 Governor Title"]


def test_district_adjacency_is_grouped_and_readable():
    _, x, _ = build()
    campus = next(r for r in x.district() if r["id"] == "district:campus")
    assert campus["fields"]["adjacency"] == ["+1 Science per adjacent Mountain", "+1 Science per 2 adjacent districts"]
    assert "cheaper while you have fewer" in campus["fields"]["cost_progression"]


def test_main_writes_records_and_meta(tmp_path):
    out = tmp_path / "data"
    assert xc6.main([str(FIX), "--out", str(out), "--game-version", "9.9"]) == 0
    meta = json.loads((out / "_meta.json").read_text())
    assert meta["game_version"] == "9.9" and meta["ruleset"] == "RULESET_EXPANSION_2"
    assert meta["counts"]["tech"] == 3 and meta["counts"]["emergency"] == 0
    assert meta["dlc"] == ["APack", "Expansion2"]
    assert any("emergency: no EmergencyAlliances" in w for w in meta["warnings"])
    for kind in xc6.KINDS:
        recs = json.loads((out / f"{kind}.json").read_text())
        ids = [r["id"] for r in recs]
        assert len(ids) == len(set(ids))
        for r in recs:
            assert r["name"] and r["id"].startswith(kind + ":")
            assert not any("{" in t or "[ICON" in t for t in strings(r)), r


def test_committed_corpus_ids_cited_by_strategy_and_docs_exist():
    """Every `kind:id` the hand-written civ6 texts cite must be a generated record or a doc."""
    corpus = REPO / "corpora/civ6"
    ids = set()
    for f in (corpus / "data").glob("[a-z]*.json"):
        ids |= {r["id"] for r in json.loads(f.read_text())}
    docs = {p.stem for p in (corpus / "docs").glob("*.md")}
    for text in [corpus / "strategy.md", *sorted((corpus / "docs").glob("*.md"))]:
        for ref in re.findall(r"`([a-z_]+:[a-z0-9_]+)`", text.read_text()):
            if ref.startswith("doc:"):
                assert ref[4:] in docs, (text.name, ref)
            elif ref.split(":")[0] in xc6.KINDS:
                assert ref in ids, (text.name, ref)


def test_committed_corpus_has_no_raw_markup():
    for f in (REPO / "corpora/civ6/data").glob("[a-z]*.json"):
        for r in json.loads(f.read_text()):
            assert not any("{" in t or "[ICON" in t or "LOC_" in t for t in strings(r)), r
