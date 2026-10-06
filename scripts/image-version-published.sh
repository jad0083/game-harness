#!/usr/bin/env bash
# scripts/image-version-published.sh <image:tag>: prints "yes" when the registry holds the tag and "no"
# when it answers that the manifest does not exist. Any other failure (network, auth, registry error)
# prints the error to stderr and exits non-zero, so a version tag is never moved on a guess.
set -uo pipefail
ref="${1:?usage: image-version-published.sh <image:tag>}"
if err="$(docker manifest inspect "$ref" 2>&1 >/dev/null)"; then
  echo yes
elif grep -qiE 'manifest unknown|not found|name unknown' <<<"$err"; then
  echo no
else
  echo "image-version-published: cannot tell whether $ref exists: $err" >&2
  exit 2
fi
