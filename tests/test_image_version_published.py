"""scripts/image-version-published.sh against a stub `docker` on PATH."""
import os
import stat
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "image-version-published.sh"


def run(tmp_path, stderr, code):
    stub = tmp_path / "docker"
    stub.write_text(f"#!/bin/sh\nprintf '%s\\n' \"$STUB_ERR\" >&2\nexit {code}\n")
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}", "STUB_ERR": stderr}
    return subprocess.run(["bash", str(SCRIPT), "ghcr.io/x:1"], env=env, capture_output=True, text=True, check=False)


@pytest.mark.parametrize("err", [
    "no such manifest: ghcr.io/x:1",
    "manifest unknown",
    "denied",
    "NAME UNKNOWN: repository name not known to registry",
])
def test_a_missing_tag_is_no(tmp_path, err):
    r = run(tmp_path, err, 1)
    assert (r.returncode, r.stdout.strip()) == (0, "no"), r.stderr


def test_an_existing_tag_is_yes(tmp_path):
    r = run(tmp_path, "", 0)
    assert (r.returncode, r.stdout.strip()) == (0, "yes")


@pytest.mark.parametrize("err", [
    'Get "https://ghcr.io/v2/": dial tcp: lookup ghcr.io: no such host',
    "unauthorized: authentication required",
])
def test_any_other_error_exits_2(tmp_path, err):
    r = run(tmp_path, err, 1)
    assert r.returncode == 2 and r.stdout.strip() == "" and err in r.stderr
