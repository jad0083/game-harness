"""Exit 0 when Playwright and its Chromium are installed (scripts/ci.sh then runs the browser tests)."""

import sys
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sys.exit(1)
try:
    with sync_playwright() as p:
        sys.exit(0 if Path(p.chromium.executable_path).exists() else 1)
except Exception:  # noqa: BLE001 - any failure means: no browser tests here
    sys.exit(1)
