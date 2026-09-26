#!/usr/bin/env bash
# Reads changed file paths on stdin; exits 0 if the Rust CI stages must run, 1 if they can be skipped.
# Rust is needed for Rust sources, Cargo files, the CI scripts themselves, and corpora (the Rust tests
# load manifests, templates and data) except the pilot's learned/ notes. No paths means a full run.
set -uo pipefail
seen=0
while IFS= read -r p; do
  [ -z "$p" ] && continue
  seen=1
  case "$p" in
    corpora/*/learned/*) ;;
    crates/*|Cargo.toml|Cargo.lock|rust-toolchain*|corpora/*|scripts/ci.sh|scripts/ci-needs-rust.sh) exit 0 ;;
  esac
done
[ "$seen" -eq 0 ] && exit 0
exit 1
