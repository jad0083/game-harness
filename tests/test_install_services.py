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
    out = (tmp_path / "game-pilot.service").read_text(encoding="utf-8")
    assert "@REPO@" not in out and f"ExecStart={REPO}/.venv/bin/python -m pilot run" in out
