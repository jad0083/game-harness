"""The docs and scripts name the store, not the files it replaced (data platform design, ruling 14)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GONE = ("telemetry.sqlite", "pilot-settings.json", "model-usage.json", "rebuild-telemetry", "PILOT_COMMIT", "PILOT_JOURNAL")


def test_no_doc_or_runtime_script_names_a_replaced_file():
    files = [ROOT / "README.md", ROOT / "ARCHITECTURE.md", ROOT / "AGENTS.md", ROOT / "docs/pilot.md",
             *ROOT.glob("scripts/*.py"), *ROOT.glob("scripts/*.sh")]
    hits = [f"{p.relative_to(ROOT)}: {w}" for p in files for w in GONE if w in p.read_text(encoding="utf-8")]
    assert hits == [], hits
