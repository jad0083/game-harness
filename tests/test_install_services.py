"""deploy/*.service carry no machine paths; scripts/install-services.sh fills in the checkout."""

import subprocess

from pilot.config import REPO


def test_units_use_the_repo_placeholder():
    for unit in (REPO / "deploy").glob("*.service"):
        text = unit.read_text(encoding="utf-8")
        assert "@REPO@" in text and "/mnt/" not in text and "/home/" not in text, unit.name


def test_install_services_fills_in_the_checkout(tmp_path):
    subprocess.run([str(REPO / "scripts/install-services.sh")], check=True, capture_output=True,
                   env={"SYSTEMD_USER_DIR": str(tmp_path), "PATH": "/usr/bin:/bin"})
    out = (tmp_path / "game-pilot-view.service").read_text(encoding="utf-8")
    assert "@REPO@" not in out and f"ExecStart={REPO}/.venv/bin/python -m pilot view --port 8780" in out
    assert "KillMode=mixed" in out and "TimeoutStopSec=60" in out      # the dashboard stops its run itself
    assert sorted(p.name for p in tmp_path.iterdir()) == ["game-pilot-view.service"]   # one service
