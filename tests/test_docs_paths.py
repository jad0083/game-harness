"""The docs and scripts name the store, not the files it replaced (data platform design, ruling 14)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GONE = ("telemetry.sqlite", "pilot-settings.json", "model-usage.json", "rebuild-telemetry", "PILOT_COMMIT", "PILOT_JOURNAL")


def test_no_doc_or_runtime_script_names_a_replaced_file():
    files = [ROOT / "README.md", ROOT / "ARCHITECTURE.md", ROOT / "AGENTS.md", ROOT / "docs/pilot.md",
             *ROOT.glob("scripts/*.py"), *ROOT.glob("scripts/*.sh")]
    hits = [f"{p.relative_to(ROOT)}: {w}" for p in files for w in GONE if w in p.read_text(encoding="utf-8")]
    assert hits == [], hits


# the one-service layout (appliance image design, ruling 5): the dashboard supervises the run, so the
# pilot's own unit and the deploy scripts that guarded it are gone (an upgrade note may still name the
# old unit an install has, to remove it)
RETIRED = ("deploy-pilot", "pilot-affected", "deploy/game-pilot.service")


def test_no_doc_or_script_names_a_retired_script_or_unit():
    files = [ROOT / "README.md", ROOT / "ARCHITECTURE.md", ROOT / "AGENTS.md", ROOT / "CLAUDE.md", ROOT / "docs/pilot.md",
             *ROOT.glob("scripts/*.py"), *ROOT.glob("scripts/*.sh"), *ROOT.glob("deploy/*"), *ROOT.glob("src/pilot/*.py")]
    hits = [f"{p.relative_to(ROOT)}: {w}" for p in files for w in RETIRED if w in p.read_text(encoding="utf-8")]
    assert hits == [], hits
