#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
uv_bin="${AGENT_COMPANY_UV_BIN:-$(command -v uv || true)}"

if [[ -z "$uv_bin" || ! -x "$uv_bin" ]]; then
  printf '%s\n' 'Agent Company requires uv. Install it with: brew install uv' >&2
  exit 127
fi

export PYTHONDONTWRITEBYTECODE=1
exec "$uv_bin" run --script "$script_dir/agent_company_bootstrap.py" "$@"
