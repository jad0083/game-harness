#!/usr/bin/env bash
# scripts/image-version-published.sh <image:tag>: prints "yes" when the registry holds the tag and "no"
# when it answers that the manifest does not exist. Any other failure (network, auth, registry error)
# prints the error to stderr and exits non-zero, so a version tag is never moved on a guess.
set -uo pipefail
ref="${1:?usage: image-version-published.sh <image:tag>}"
if err="$(docker manifest inspect "$ref" 2>&1 >/dev/null)"; then
  echo yes
# "no such manifest" is the docker CLI's own wording (29.x); "manifest unknown" and "name unknown" are the
# registry's; ghcr answers "denied" for a package that does not exist yet. A token that can push but cannot
# read a tag means the tag does not exist for it, because ghcr's write access implies read access.
elif grep -qiE 'no such manifest|manifest unknown|not found|name unknown|denied' <<<"$err"; then
  echo no
else
  echo "image-version-published: cannot tell whether $ref exists: $err" >&2
  exit 2
fi
