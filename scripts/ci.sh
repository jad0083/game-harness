#!/usr/bin/env bash
# Local CI: everything that must pass before a commit.
#   scripts/ci.sh          full run
#   CI_CHANGED_FILES=...   newline-separated paths (set by ci-commit.sh from the staged files): the
#                          Rust stages are skipped when none of them needs Rust (scripts/ci-needs-rust.sh)
#                          and a controller binary already exists
# Exits non-zero on the first failing stage.
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/.cargo/bin:$PATH"

stage() { printf '\n== %s ==\n' "$1"; }

rust=1
if [ -n "${CI_CHANGED_FILES:-}" ] && [ -x target/release/game-controller ] \
   && ! printf '%s\n' "$CI_CHANGED_FILES" | scripts/ci-needs-rust.sh; then
  rust=0
fi

if [ "$rust" -eq 1 ]; then
stage "cargo build (release, controller)"
cargo build --release -p game-controller 2>&1 | tail -1

stage "cargo test"
cargo test --workspace 2>&1 | grep -E "^test result|FAILED|panicked" || true
cargo test --workspace --quiet >/dev/null 2>&1

stage "cargo clippy (windows agent + controller)"
cargo clippy --workspace --all-targets -- -D warnings -A clippy::wrong_self_convention 2>&1 | tail -1
cargo check -p game-agent --target x86_64-pc-windows-gnu --quiet 2>&1 | tail -1

stage "corpus loads"
./target/release/game-controller --corpus corpora/galciv4 corpus | sed -n '2,10p'

else
stage "rust stages skipped: no Rust, Cargo or corpus files in this commit"
fi

stage "python: ruff + pytest"
.venv/bin/ruff check .
.venv/bin/pytest -q 2>&1 | tail -1

printf '\nCI OK\n'
