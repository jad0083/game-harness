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
                          "docs/plans/x.md", "games/stellaris-spike/journal.md",
                          "corpora/stellaris/learned/strategy.md", "src/pilot/static/dashboard.html")


def test_rust_sources_corpora_and_ci_itself_need_rust():
    for p in ("crates/game-controller/src/stellaris.rs", "Cargo.toml", "Cargo.lock",
              "corpora/stellaris/manifest.toml", "corpora/galciv4/templates/x.png", "corpora/stellaris/strategy.md",
              "scripts/ci.sh", "scripts/ci-needs-rust.sh"):
        assert needs_rust("src/pilot/governor.py", p), p


def test_no_file_list_means_a_full_run():
    assert needs_rust()


def test_ci_runs_the_civ6_lua_library_in_luajit_on_every_run():
    """pytest skips tests/test_harness_lua.py (lupa is not in the shared .venv), so without this stage
    a syntax or runtime error in corpora/civ6/lua/harness.lua would pass CI and break every live
    Civ VI call. The stage must run whatever the commit touches (not only with the Rust stages)."""
    lines = (REPO / "scripts/ci.sh").read_text(encoding="utf-8").splitlines()
    runs = [i for i, line in enumerate(lines) if line.strip().startswith("scripts/civ6-lua-check.sh")]
    assert runs, "scripts/ci.sh does not run scripts/civ6-lua-check.sh"
    rust_block_end = max(i for i, line in enumerate(lines) if line.strip() == "fi")
    assert all(i > rust_block_end for i in runs), "the Lua check sits inside a conditional block"
