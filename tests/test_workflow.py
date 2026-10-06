"""The image workflow (appliance image design, ruling 10)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_workflow_builds_smokes_and_pushes_three_tags():
    text = (ROOT / ".github/workflows/image.yml").read_text()
    for must in ("scripts/image-smoke.sh", "ghcr.io/jad0083/game-pilot", ":sha-", ":latest", "paths-ignore",
                 '"**.md"', '"docs/**"', "packages: write", "cargo test -p game-controller", "pytest -q -m \"not ui\""):
        assert must in text, must
