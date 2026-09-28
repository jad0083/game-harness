"""A deploy restarts only the affected game's pilot (docs/design/2026-09-27-postmortem-fixes-design.md,
ruling 28): scripts/pilot-affected.py classifies the changed paths, scripts/deploy-pilot.sh acts on it.
A Stellaris-only merge restarted the live Civ VI run at T462."""

import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("pilot_affected", REPO / "scripts/pilot-affected.py")
pa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pa)


def test_each_path_gets_its_class():
    assert pa.classify("src/pilot/civ6_governor.py") == "civ6"
    assert pa.classify("corpora/civ6/lua/harness.lua") == "civ6"
    assert pa.classify("corpora/civ6/pilot.md") == "civ6", "the governor reads its corpus's .md files at start"
    assert pa.classify("src/pilot/stellaris_market.py") == "stellaris"
    assert pa.classify("src/pilot/controller.py") == "galciv4"
    assert pa.classify("corpora/civ6/learned/strategy.md") == "none"
    assert pa.classify("src/pilot/static/dashboard.html") == "view"
    assert pa.classify("crates/game-controller/src/civ6.rs") == "rust" and pa.classify("Cargo.lock") == "rust"
    for p in ("docs/pilot.md", "games/civ6-kublai/journal.md", "tests/test_governor.py", "plan.md", "scripts/ci.sh"):
        assert pa.classify(p) == "none", p
    for p in ("src/pilot/governor.py", "src/pilot/dashboard.py", "pyproject.toml", "weird/new-file.bin"):
        assert pa.classify(p) == "shared", p


def test_a_stellaris_only_change_leaves_a_running_civ6_pilot_alone():
    p = pa.plan(["src/pilot/stellaris_market.py", "corpora/stellaris/pillars.toml", "docs/pilot.md",
                 "tests/test_stellaris_market.py", "corpora/civ6/learned/strategy.md"], "civ6")
    assert not p["restart_pilot"] and not p["restart_view"] and not p["build"]
    assert p["message"] == ("not restarted: the running civ6 pilot is unaffected; the change applies at its next start")
    assert pa.plan(["src/pilot/stellaris_market.py"], "stellaris")["restart_pilot"]


def test_shared_code_restarts_any_pilot_and_the_viewer_and_unknown_is_shared():
    for game in ("civ6", "stellaris", "galciv4"):
        p = pa.plan(["src/pilot/governor.py"], game)
        assert p["restart_pilot"] and p["restart_view"], game
    assert pa.plan(["weird/new-file.bin"], "civ6")["restart_pilot"], "an unknown path is the safe side"
    assert pa.plan(["corpora/civ6/pillars.toml"], "unknown")["restart_pilot"], "a game that cannot be read: any game's class"
    view = pa.plan(["src/pilot/static/dashboard.html"], "civ6")
    assert view["restart_view"] and not view["restart_pilot"]
    assert pa.plan(["src/pilot/governor.py"], "civ6", running=False)["message"] == \
        "no pilot runs: the change applies at its next start"


# ---- scripts/deploy-pilot.sh in a throwaway repository, with systemctl, curl and cargo stubbed -------------

STUB = """#!/usr/bin/env bash
echo "$(basename "$0") $*" >> "$STUB_LOG"
case "$(basename "$0") $*" in
  "systemctl --user is-active --quiet game-pilot.service") exit "${PILOT_ACTIVE:-0}" ;;
  "systemctl --user is-active --quiet game-pilot-view.service") exit 0 ;;
  curl*/status) printf '%s' "$STATUS_JSON" ;;
esac
exit 0
"""


def deploy(tmp_path: Path, changed: str, status: dict | None, dry: bool = True) -> tuple[str, list[str]]:
    """Run the script in a new repository whose last commit changes `changed`; the pilot runs when
    `status` is given (its /status JSON)."""
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    for f in ("deploy-pilot.sh", "pilot-affected.py"):
        shutil.copy(REPO / "scripts" / f, repo / "scripts" / f)
    (repo / ".venv").symlink_to(REPO / ".venv")
    (repo / ".gitignore").write_text(".venv\n")

    def commit(message: str) -> None:
        for args in (["add", "-A", "."], ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", message]):
            subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True)
    commit("base")
    target = repo / changed
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("x\n")
    commit("change")
    stubs = tmp_path / "bin"
    stubs.mkdir()
    for name in ("systemctl", "curl", "cargo"):
        (stubs / name).write_text(STUB)
        (stubs / name).chmod(0o755)
    log = tmp_path / "calls.log"
    env = {"PATH": f"{stubs}:/usr/bin:/bin", "STUB_LOG": str(log), "HOME": str(tmp_path),
           "PILOT_ACTIVE": "0" if status is not None else "3", "STATUS_JSON": json.dumps(status or {}),
           "PILOT_DASHBOARD_KEY": "k"}
    r = subprocess.run(["bash", str(repo / "scripts/deploy-pilot.sh"), "HEAD~1", "HEAD", *(["--dry-run"] if dry else [])],
                       capture_output=True, text=True, env={**os.environ, **env}, timeout=60, check=False)
    assert r.returncode == 0, r.stderr
    return r.stdout, log.read_text().splitlines() if log.exists() else []


CIV6 = {"status": "playing", "info": {"game": "civ6"}}


def test_the_script_leaves_a_running_civ6_pilot_on_a_stellaris_change(tmp_path):
    out, calls = deploy(tmp_path, "src/pilot/stellaris_market.py", CIV6)
    assert "not restarted: the running civ6 pilot is unaffected; the change applies at its next start" in out
    assert "restart" not in " ".join(c for c in calls if c.startswith("systemctl --user restart"))
    assert "would run: systemctl --user restart game-pilot.service" not in out


def test_the_script_restarts_the_pilot_and_viewer_on_shared_code(tmp_path):
    out, _ = deploy(tmp_path, "src/pilot/governor.py", CIV6)
    assert "would run: systemctl --user restart game-pilot.service" in out
    assert "would run: systemctl --user restart game-pilot-view.service" in out


def test_a_rust_change_pauses_builds_and_resumes_without_a_restart(tmp_path):
    out, _ = deploy(tmp_path, "crates/game-controller/src/civ6.rs", CIV6)
    lines = out.splitlines()
    pause = lines.index("would pause the civ6 pilot through its dashboard")
    build = lines.index("would run: cargo build --release -p game-controller")
    resume = lines.index("would resume the civ6 pilot through its dashboard")
    assert pause < build < resume
    assert "would run: systemctl --user restart game-pilot.service" not in out
    held, _ = deploy(tmp_path / "held", "crates/game-controller/src/civ6.rs", {**CIV6, "status": "needs_attention"})
    assert "would pause" not in held and "would resume" not in held, "a pilot waiting for the human is left alone"


def test_a_real_run_pauses_through_the_dashboard_and_restarts_nothing_else(tmp_path):
    _out, calls = deploy(tmp_path, "crates/game-controller/src/civ6.rs", CIV6, dry=False)
    assert any(c.startswith("curl") and c.endswith("/control") and '"pause"' in c for c in calls), calls
    assert "cargo build --release -p game-controller" in calls
    assert any(c.startswith("curl") and '"resume"' in c for c in calls)
    assert not any(c.startswith("systemctl --user restart") for c in calls)
