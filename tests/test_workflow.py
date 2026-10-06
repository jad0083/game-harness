"""The image workflow (appliance image design, ruling 10)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_workflow_builds_smokes_and_pushes_three_tags():
    text = (ROOT / ".github/workflows/image.yml").read_text()
    for must in ("scripts/image-smoke.sh", "ghcr.io/jad0083/game-pilot", ":sha-", ":latest", "paths-ignore",
                 '"**.md"', '"docs/**"', "packages: write", "cargo test -p game-controller", "pytest -q -m \"not ui\""):
        assert must in text, must


def _run_check(tmp_path, exit_code, stderr):
    import os
    import subprocess

    stub = tmp_path / "docker"
    stub.write_text(f"#!/bin/sh\necho '{stderr}' >&2\nexit {exit_code}\n")
    stub.chmod(0o755)
    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"}
    return subprocess.run([str(ROOT / "scripts/image-version-published.sh"), "x:1"], env=env,
                          capture_output=True, text=True, check=False)


def test_version_check_yes_no_and_errors(tmp_path):
    assert _run_check(tmp_path, 0, "").stdout.strip() == "yes"
    for msg in ("manifest unknown", "Error: No such manifest: not found", "NAME_UNKNOWN: name unknown"):
        r = _run_check(tmp_path, 1, msg)
        assert (r.returncode, r.stdout.strip()) == (0, "no"), msg
    r = _run_check(tmp_path, 1, "dial tcp: i/o timeout")
    assert r.returncode != 0 and r.stdout.strip() == "" and "i/o timeout" in r.stderr


def test_workflow_least_privilege_and_main_only_push():
    text = (ROOT / ".github/workflows/image.yml").read_text()
    assert text.index("permissions:\n  contents: read") < text.index("jobs:")
    assert text.count("if: github.ref == 'refs/heads/main'") == 2
    assert "scripts/image-version-published.sh" in text
