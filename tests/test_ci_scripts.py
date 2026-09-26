"""scripts/ci-needs-rust.sh decides whether a commit's files need the Rust CI stages."""

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def needs_rust(*paths: str) -> bool:
    r = subprocess.run(["bash", str(REPO / "scripts/ci-needs-rust.sh")], input="\n".join(paths) + "\n",
                       text=True, capture_output=True, timeout=30, check=False)
    assert r.returncode in (0, 1), r.stderr
    return r.returncode == 0


def test_python_docs_and_learned_files_skip_rust():
    assert not needs_rust("src/pilot/governor.py", "tests/test_governor.py", "plan.md", "issues.md",
                          "docs/superpowers/plans/x.md", "games/stellaris-spike/journal.md",
                          "corpora/stellaris/learned/strategy.md", "src/pilot/static/dashboard.html")


def test_rust_sources_corpora_and_ci_itself_need_rust():
    for p in ("crates/game-controller/src/stellaris.rs", "Cargo.toml", "Cargo.lock",
              "corpora/stellaris/manifest.toml", "corpora/galciv4/templates/x.png", "corpora/stellaris/strategy.md",
              "scripts/ci.sh", "scripts/ci-needs-rust.sh"):
        assert needs_rust("src/pilot/governor.py", p), p


def test_no_file_list_means_a_full_run():
    assert needs_rust()
