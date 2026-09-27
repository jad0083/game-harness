"""scripts/serve-agent.sh serves the installer on a one-time path and prints a one-liner that pins
install.ps1 and game-agent.exe by SHA-256. Runs the script in a scratch copy of the repo layout
(GA_DRY_RUN: print and exit before serving; GA_EXE: a prebuilt exe instead of the build)."""

import hashlib
import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
INSTALL = (REPO / "windows_agent/install.ps1").read_text(encoding="utf-8")


def serve(tmp_path: Path, *args: str, token: str | None = None) -> subprocess.CompletedProcess:
    (tmp_path / "scripts").mkdir(exist_ok=True)
    (tmp_path / "windows_agent").mkdir(exist_ok=True)
    shutil.copy(REPO / "scripts/serve-agent.sh", tmp_path / "scripts/serve-agent.sh")
    shutil.copy(REPO / "windows_agent/install.ps1", tmp_path / "windows_agent/install.ps1")
    exe = tmp_path / "game-agent.exe"
    exe.write_bytes(b"MZ fake agent")
    if token is not None:
        (tmp_path / ".agent_token").write_text(token + "\n")
    env = {**os.environ, "GA_DRY_RUN": "1", "GA_EXE": str(exe), "GA_BIND": "10.0.0.5"}
    return subprocess.run(["bash", str(tmp_path / "scripts/serve-agent.sh"), *args], env=env, text=True,
                          capture_output=True, timeout=60, check=False)


def one_liner(out: str) -> str:
    lines = [ln.strip() for ln in out.splitlines() if "$env:GA_SRC=" in ln]
    assert len(lines) == 1, out
    return lines[0]


def test_one_liner_pins_the_installer_and_the_exe(tmp_path):
    r = serve(tmp_path, "8123")
    assert r.returncode == 0, r.stderr
    line = one_liner(r.stdout)
    m = re.search(r"\$env:GA_SRC='http://10\.0\.0\.5:8123/([0-9a-f]{32})';", line)
    assert m, line
    exe_sha = hashlib.sha256(b"MZ fake agent").hexdigest()
    ps1_sha = hashlib.sha256((tmp_path / "windows_agent/install.ps1").read_bytes()).hexdigest()
    assert f"$env:GA_SHA256='{exe_sha}'" in line
    assert f"-ne '{ps1_sha}'" in line, "install.ps1 is checked before it runs"
    assert line.index("Get-FileHash") < line.index("iex"), "hash check before running the script"
    assert "irm" not in line, "no unverified irm | iex"
    assert exe_sha in r.stdout.replace(line, ""), "the exe hash is printed on its own too"


def test_every_run_gets_a_new_path(tmp_path):
    a = one_liner(serve(tmp_path, "8123").stdout)
    b = one_liner(serve(tmp_path, "8123").stdout)
    rid = re.compile(r":8123/([0-9a-f]{32})'")
    assert rid.search(a).group(1) != rid.search(b).group(1)


def test_prints_a_reminder_to_stop_and_binds_only_the_controller_address(tmp_path):
    out = serve(tmp_path).stdout
    assert re.search(r"(?i)stop .*as soon as", out)
    assert "10.0.0.5" in out and "0.0.0.0" not in out
    assert re.search(r"stops by itself after \d+ minutes", out)


def test_generates_a_long_private_token(tmp_path):
    r = serve(tmp_path)
    assert r.returncode == 0, r.stderr
    tok = tmp_path / ".agent_token"
    assert len(tok.read_text().strip()) >= 32
    assert stat.S_IMODE(tok.stat().st_mode) == 0o600


def test_refuses_to_serve_a_short_token(tmp_path):
    r = serve(tmp_path, token="short")
    assert r.returncode != 0
    assert "32" in r.stderr


@pytest.mark.parametrize("bad", ["../x", "a b", "-p"])
def test_rejects_bad_arguments(tmp_path, bad):
    assert serve(tmp_path, bad).returncode != 0


def test_installer_verifies_the_exe_before_stopping_the_running_agent():
    assert "GA_SHA256" in INSTALL
    verify = INSTALL.index("Get-FileHash")
    stop = INSTALL.index("Stop-Process")
    assert verify < stop, "a bad download must leave the running agent alone"
    assert re.search(r"throw .*hash", INSTALL[verify:verify + 600], re.IGNORECASE)


def test_installer_is_ascii():
    # Windows PowerShell 5.1 reads a BOM-less file as ANSI.
    assert INSTALL.isascii()
