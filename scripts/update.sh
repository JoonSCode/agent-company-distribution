#!/usr/bin/env bash
set -euo pipefail

# Keep the pinned source and managed skills unchanged in launchd and child Python.
export PYTHONDONTWRITEBYTECODE=1

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
uv_bin="${AGENT_COMPANY_UV_BIN:-$(command -v uv || true)}"

# launchd's PATH omits the default uv installer location. Keep an explicit
# override and PATH resolution first, then reuse the user's installed uv.
if [[ -z "$uv_bin" && -n "${HOME:-}" && -x "$HOME/.local/bin/uv" ]]; then
  uv_bin="$HOME/.local/bin/uv"
fi

if [[ -z "$uv_bin" || ! -x "$uv_bin" ]]; then
  printf '%s\n' 'Agent Company requires uv. Install it with: brew install uv' >&2
  exit 127
fi

exec "$uv_bin" run --script "$script_dir/agent_company_update_status.py" "$@"
