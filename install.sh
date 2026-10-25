#!/usr/bin/env bash
set -euo pipefail

# This source entry does not download the historical Core-bound v0.1.0 release.
if [[ -z "${BASH_SOURCE[0]:-}" || ! -f "${BASH_SOURCE[0]}" ]]; then
  printf '%s\n' 'Pipe installation of the historical v0.1.0 artifact is unsupported for standalone Orca Company.' 'Use a reviewed, pinned source checkout, then run: bash scripts/setup.sh install' >&2
  exit 1
fi
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ ! -f "$script_dir/scripts/bootstrap.sh" || ! -d "$script_dir/.git" && ! -f "$script_dir/.git" ]]; then
  printf '%s\n' 'Use a reviewed, pinned Company Git source checkout, then run: bash scripts/setup.sh install' >&2
  exit 1
fi
exec bash "$script_dir/scripts/setup.sh" "$@"
