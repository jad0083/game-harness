#!/usr/bin/env bash
# Run corpora/civ6/lua/harness.lua outside the game: LuaJIT (lupa) with the stand-ins of
# tests/fixtures/civ6_lua_mock.lua (tests/test_harness_lua.py). It proves syntax and control flow
# only; API names and results are checked live. lupa is not in the shared .venv (the live services
# run from it), so plain pytest skips these tests; this script keeps lupa in a cache folder of its
# own and runs them with .venv's pytest. scripts/ci.sh runs it on every CI run.
set -euo pipefail
cd "$(dirname "$0")/.."
cache="${XDG_CACHE_HOME:-$HOME/.cache}/game-harness/lupa"
if [ ! -d "$cache/lupa" ]; then
  .venv/bin/python -m pip install --quiet --target "$cache" 'lupa>=2.0'
fi
PYTHONPATH="$cache" exec .venv/bin/pytest -q tests/test_harness_lua.py "$@"
