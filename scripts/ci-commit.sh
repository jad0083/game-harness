#!/usr/bin/env bash
# Run CI; only if it passes, commit the staged changes with the given message and push.
# Usage: git add <paths> && scripts/ci-commit.sh "type: message" ["body"]
set -uo pipefail
cd "$(dirname "$0")/.."
log="$(mktemp)"
if ! scripts/ci.sh >"$log" 2>&1; then
  echo "CI FAILED — nothing committed. Last lines:"; tail -25 "$log"; exit 1
fi
tail -2 "$log"
if git diff --cached --quiet; then echo "nothing staged"; exit 1; fi
if [ "$#" -ge 2 ]; then git commit -q -m "$1" -m "$2"; else git commit -q -m "$1"; fi
git push -q && git log --oneline -1
