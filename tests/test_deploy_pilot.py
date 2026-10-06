"""A deploy restarts only the affected game's pilot (docs/design/2026-09-27-postmortem-fixes-design.md,
ruling 28): scripts/pilot-affected.py classifies the changed paths, scripts/deploy-pilot.sh acts on it.
A Stellaris-only merge restarted the live Civ VI run at T462."""

import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

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
    assert not p["restart_pilot"] and not p["build"]
    assert p["restart_view"], "the viewer imports game modules too (stellaris_record, civ6) and keeps them"
    assert p["message"] == ("not restarted: the running civ6 pilot is unaffected; the change applies at its next start")
    assert pa.plan(["src/pilot/stellaris_market.py"], "stellaris")["restart_pilot"]
    assert pa.plan(["src/pilot/controller.py"], "civ6")["restart_view"]
    corpus = pa.plan(["corpora/stellaris/pillars.toml", "docs/pilot.md"], "civ6")
    assert not corpus["restart_view"] and not corpus["restart_pilot"], "the viewer reads a corpus per request"


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


def test_a_rust_change_restarts_a_stellaris_or_galciv4_pilot_but_not_a_civ6_one():
    """Stellaris and GalCiv IV keep one `game-controller mcp` child for the whole run (McpGame), so a
    rebuilt binary reaches them only through a restart; Civ VI runs the binary afresh for each call."""
    for game, path in (("stellaris", "crates/game-controller/src/stellaris.rs"),
                       ("galciv4", "crates/game-controller/src/autopilot.rs"), ("unknown", "Cargo.lock")):
        p = pa.plan([path], game)
        assert p["build"] and p["restart_pilot"], game
        assert "rust changed" in p["message"], p["message"]
    civ6 = pa.plan(["crates/game-controller/src/civ6.rs"], "civ6")
    assert civ6["build"] and not civ6["restart_pilot"], "paused, built and resumed: no restart"


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


def deploy(tmp_path: Path, changed: str, status: dict | None, dry: bool = True,
           key_files: dict[str, str] | None = None, dotenv: str | None = None,
           extra_env: dict[str, str] | None = None) -> tuple[str, list[str]]:
    """Run the script in a new repository whose last commit changes `changed`; the pilot runs when
    `status` is given (its /status JSON). With `key_files` (path in the repo -> key) the dashboard key
    comes from those files instead of PILOT_DASHBOARD_KEY."""
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    for f in ("deploy-pilot.sh", "pilot-affected.py"):
        shutil.copy(REPO / "scripts" / f, repo / "scripts" / f)
    (repo / ".venv").symlink_to(REPO / ".venv")
    (repo / ".gitignore").write_text(".venv\nruns/\nstore/\nelsewhere/\n.env\n")
    if dotenv is not None:
        (repo / ".env").write_text(dotenv)
    for rel, key in (key_files or {}).items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(key + "\n")

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
    base = {k: v for k, v in os.environ.items() if k not in ("PILOT_DATA_DIR", "PILOT_RUNS_DIR")}
    if key_files is not None:
        del env["PILOT_DASHBOARD_KEY"]
        base.pop("PILOT_DASHBOARD_KEY", None)
    r = subprocess.run(["bash", str(repo / "scripts/deploy-pilot.sh"), "HEAD~1", "HEAD", *(["--dry-run"] if dry else [])],
                       capture_output=True, text=True, env={**base, **env, **(extra_env or {})}, timeout=60, check=False)
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


def test_a_rust_change_with_a_running_stellaris_pilot_pauses_builds_and_restarts_it(tmp_path):
    out, _ = deploy(tmp_path, "crates/game-controller/src/stellaris.rs", {"status": "playing", "info": {"game": "stellaris"}})
    lines = out.splitlines()
    pause = lines.index("would pause the stellaris pilot through its dashboard")
    build = lines.index("would run: cargo build --release -p game-controller")
    restart = lines.index("would run: systemctl --user restart game-pilot.service")
    assert pause < build < restart
    assert "would resume" not in out, "the restart starts it on the new binary"
    assert "not restarted" not in out


def test_a_real_run_pauses_through_the_dashboard_and_restarts_nothing_else(tmp_path):
    _out, calls = deploy(tmp_path, "crates/game-controller/src/civ6.rs", CIV6, dry=False)
    assert any(c.startswith("curl") and c.endswith("/control") and '"pause"' in c for c in calls), calls
    assert "cargo build --release -p game-controller" in calls
    assert any(c.startswith("curl") and '"resume"' in c for c in calls)
    assert not any(c.startswith("systemctl --user restart") for c in calls)


@pytest.mark.parametrize(("files", "used"), [
    ({"runs/secrets/dashboard.key": "new-key", "runs/dashboard.key": "old-key"}, "new-key"),
    ({"runs/dashboard.key": "old-key"}, "old-key"),
])
def test_the_script_reads_the_key_from_secrets_then_the_old_place(tmp_path, files, used):
    """The data platform keeps the key in runs/secrets/; an install not yet imported has runs/dashboard.key."""
    _out, calls = deploy(tmp_path, "crates/game-controller/src/civ6.rs", CIV6, dry=False, key_files=files)
    status = [c for c in calls if c.startswith("curl") and c.endswith("/status")]
    assert status and all(f"X-Pilot-Key: {used}" in c for c in status), calls


def test_the_script_reads_the_data_directory_from_dotenv_as_config_does(tmp_path):
    """PILOT_DATA_DIR set only in .env (config.py loads it from there): the key is read under it. Only that
    key is read from .env, which holds secrets; the environment wins over it."""
    secret = "AIza-never-printed-0123456789"
    dotenv = f'GEMINI_API_KEY={secret}\n PILOT_DATA_DIR = "store"\nPILOT_DATA_DIR=ignored-second\n'
    files = {"store/secrets/dashboard.key": "from-dotenv-dir", "runs/secrets/dashboard.key": "default-dir",
             "elsewhere/secrets/dashboard.key": "from-environment"}
    out, calls = deploy(tmp_path / "a", "crates/game-controller/src/civ6.rs", CIV6, dry=False, key_files=files,
                        dotenv=dotenv)
    status = [c for c in calls if c.startswith("curl") and c.endswith("/status")]
    assert status and all("X-Pilot-Key: from-dotenv-dir" in c for c in status), calls
    assert secret not in out and not [c for c in calls if secret in c]
    _, calls = deploy(tmp_path / "b", "crates/game-controller/src/civ6.rs", CIV6, dry=False, key_files=files,
                      dotenv=dotenv, extra_env={"PILOT_DATA_DIR": "elsewhere"})
    assert all("X-Pilot-Key: from-environment" in c for c in calls if c.startswith("curl") and c.endswith("/status"))


@pytest.mark.parametrize(("dotenv", "environment", "used"), [
    ("PILOT_RUNS_DIR=store\n", {}, "store"),                                       # .env's alias, nothing else
    ("PILOT_RUNS_DIR=elsewhere\nPILOT_DATA_DIR=store\n", {}, "store"),             # PILOT_DATA_DIR wins
    ("PILOT_DATA_DIR=store\n", {"PILOT_RUNS_DIR": "elsewhere"}, "store"),          # even over the env's alias
    ("PILOT_RUNS_DIR=store\n", {"PILOT_RUNS_DIR": "elsewhere"}, "elsewhere"),      # the environment wins its key
])
def test_the_script_finds_the_data_directory_in_the_order_config_does(tmp_path, dotenv, environment, used):
    """config.py: load_dotenv fills keys the environment lacks, then PILOT_DATA_DIR beats PILOT_RUNS_DIR."""
    files = {"store/secrets/dashboard.key": "store", "elsewhere/secrets/dashboard.key": "elsewhere",
             "runs/secrets/dashboard.key": "runs"}
    _, calls = deploy(tmp_path, "crates/game-controller/src/civ6.rs", CIV6, dry=False, key_files=files,
                      dotenv=dotenv, extra_env=environment)
    status = [c for c in calls if c.startswith("curl") and c.endswith("/status")]
    assert status and all(f"X-Pilot-Key: {used} " in c for c in status), calls


def test_the_script_finds_cargo_in_the_users_toolchain():
    """First live deploy (2026-09-27): a service shell has no ~/.cargo/bin on PATH, so a Rust change
    failed with "cargo: command not found"; ci.sh adds it, and so must the deploy script."""
    text = (Path(__file__).resolve().parent.parent / "scripts" / "deploy-pilot.sh").read_text()
    assert 'export PATH="$HOME/.cargo/bin:$PATH"' in text
    assert text.index('export PATH="$HOME/.cargo/bin:$PATH"') < text.index("cargo build")
