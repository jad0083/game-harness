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


def ui_gate(log_text: str, *paths: str, tmp_path) -> bool:
    log = tmp_path / "ci.log"
    log.write_text(log_text)
    r = subprocess.run(["bash", str(REPO / "scripts/ci-ui-gate.sh"), str(log)], input="\n".join(paths) + "\n",
                       text=True, capture_output=True, timeout=30, check=False)
    assert r.returncode in (0, 1), r.stderr
    return r.returncode == 0


def test_ci_runs_the_browser_tests_when_chromium_is_there():
    ci = (REPO / "scripts/ci.sh").read_text(encoding="utf-8")
    assert "pytest -q -m ui" in ci and "UI tests skipped" in ci


def test_a_page_change_is_not_committed_when_the_browser_tests_were_skipped(tmp_path):
    skipped = "== python ==\nUI tests skipped: Playwright's Chromium is not installed\nCI OK\n"
    ran = "== python ==\n7 passed in 12.1s\nCI OK\n"
    for page in ("src/pilot/static/dashboard.html", "src/pilot/static/pair.html", "src/pilot/static/signin.js",
                 "src/pilot/auth.py"):
        assert not ui_gate(skipped, "README.md", page, tmp_path=tmp_path), page
        assert ui_gate(ran, "README.md", page, tmp_path=tmp_path), page
    assert ui_gate(skipped, "src/pilot/governor.py", "plan.md", tmp_path=tmp_path)


def test_ci_commit_applies_the_ui_gate():
    assert "scripts/ci-ui-gate.sh" in (REPO / "scripts/ci-commit.sh").read_text(encoding="utf-8")
