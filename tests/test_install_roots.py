"""The Windows installer declares the game folders the agent may read, and the few files it may write."""

import re
from pathlib import Path

INSTALL = (Path(__file__).resolve().parents[1] / "windows_agent/install.ps1").read_text(encoding="utf-8")


def test_civ6_read_roots_are_declared():
    for key in ("civ6_docs", "civ6_install", "civ6_appdata"):
        assert re.search(rf"^\s*{key}\s*=", INSTALL, re.MULTILINE), key


def test_civ6_write_root_allows_only_app_options():
    block = INSTALL.split("$writeRoots['civ6_options']", 1)[1].split("}", 1)[0]
    assert re.search(r"allow\s*=\s*@\('AppOptions\.txt'\)", block)
