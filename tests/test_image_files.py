"""The image's entrypoint and build context (appliance image design, rulings 3, 4 and 12)."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "docker" / "entrypoint.sh"


def stub(dir: Path, name: str, body: str) -> None:
    p = dir / name
    p.write_text("#!/bin/sh\n" + body)
    p.chmod(p.stat().st_mode | stat.S_IEXEC)


def run(tmp_path, env_extra=None, data=None):
    bin_ = tmp_path / "bin"
    bin_.mkdir(exist_ok=True)
    log = tmp_path / "calls"
    stub(bin_, "litestream", f'echo "litestream $*" >> {log}\n')
    stub(bin_, "pilot", f'echo "pilot $*" >> {log}\n')
    data = data or (tmp_path / "data")
    env = {"PATH": f"{bin_}:/usr/bin:/bin", "PILOT_DATA_DIR": str(data), "LITESTREAM_CONFIG": str(ROOT / "docker/litestream.yml"),
           **(env_extra or {})}
    r = subprocess.run(["sh", str(ENTRY)], env=env, capture_output=True, text=True, timeout=30, check=False)
    return r, (log.read_text().splitlines() if log.exists() else [])


def test_no_replica_runs_the_dashboard(tmp_path):
    (tmp_path / "data").mkdir()
    r, calls = run(tmp_path)
    assert r.returncode == 0, r.stderr
    assert calls == ["pilot view --port 8780"]


def test_a_replica_restores_into_an_empty_dir_then_replicates(tmp_path):
    (tmp_path / "data").mkdir()
    r, calls = run(tmp_path, {"LITESTREAM_REPLICA_URL": "s3://bucket/pilot"})
    assert r.returncode == 0, r.stderr
    assert calls[0].startswith("litestream restore") and "-if-replica-exists" in calls[0]
    assert calls[1].startswith("litestream replicate") and '-exec' in calls[1] and "pilot view --port 8780" in calls[1]


def test_a_replica_never_restores_over_existing_data(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "pilot.db").write_bytes(b"x")
    r, calls = run(tmp_path, {"LITESTREAM_REPLICA_URL": "s3://bucket/pilot"})
    assert r.returncode == 0 and not any(c.startswith("litestream restore") for c in calls)


def test_unwritable_data_dir_names_the_fix(tmp_path):
    if os.geteuid() == 0:
        return                                   # root writes whatever the mode
    d = tmp_path / "data"
    d.mkdir()
    d.chmod(0o500)
    try:
        r, calls = run(tmp_path, data=d)
    finally:
        d.chmod(0o700)
    assert r.returncode == 1 and calls == []
    msg = r.stdout + r.stderr
    assert str(d) in msg and "chown" in msg and msg.count("\n") <= 2


def test_dockerignore_excludes_secrets_and_data():
    lines = {line.strip() for line in (ROOT / ".dockerignore").read_text().splitlines() if line.strip()}
    for must in (".env", ".agent_token*", "runs/", "play/", ".git", ".venv", "target/", "incoming/", ".claude/"):
        assert must in lines, must
