#!/usr/bin/env bash
set -euo pipefail

repository="https://github.com/JoonSCode/agent-company-distribution.git"
release_repository="JoonSCode/agent-company-distribution"
tag="v0.1.0"

if ! command -v gh >/dev/null 2>&1; then
  printf '%s\n' 'Agent Company requires GitHub CLI (gh) to verify the release attestation.' >&2
  exit 127
fi

gh release verify "$tag" --repo "$release_repository"

stage="$(mktemp -d "${TMPDIR:-/tmp}/agent-company-install.XXXXXX")"
trap 'rm -rf -- "$stage"' EXIT

git clone --quiet --depth 1 --branch "$tag" --single-branch "$repository" "$stage/source"
head="$(git -C "$stage/source" rev-parse HEAD)"
tag_commit="$(git -C "$stage/source" rev-parse "refs/tags/$tag^{commit}")"
if [[ "$head" != "$tag_commit" ]]; then
  printf '%s\n' "Agent Company checkout does not match $tag." >&2
  exit 1
fi

bash "$stage/source/scripts/bootstrap.sh" install --user "$@"
