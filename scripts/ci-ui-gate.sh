#!/usr/bin/env bash
# Reads staged file paths on stdin; $1 is the CI log. Exits 1 when a dashboard page or the sign-in
# code is staged but CI skipped the browser tests (Playwright's Chromium missing), so such a change
# is never committed untested in a browser. Exits 0 otherwise.
set -uo pipefail
log="${1:?usage: ci-ui-gate.sh <ci log>}"
grep -q "UI tests skipped" "$log" || exit 0
while IFS= read -r p; do
  case "$p" in
    src/pilot/static/dashboard.html|src/pilot/static/pair.html|src/pilot/static/signin.js|src/pilot/auth.py)
      echo "UI tests were skipped, but $p is staged: install Chromium (.venv/bin/python -m playwright install chromium)"
      exit 1 ;;
  esac
done
exit 0
