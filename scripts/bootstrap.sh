#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
uv_bin="${AGENT_COMPANY_UV_BIN:-$(command -v uv || true)}"
if [[ -z "$uv_bin" || ! -x "$uv_bin" ]]; then
  printf '%s\n' 'Preparation required: uv was not found. Install uv separately using its official instructions: https://docs.astral.sh/uv/getting-started/installation/' 'On macOS with Homebrew already installed: brew install uv. This script does not install uv or Homebrew.' >&2
  exit 127
fi

# Preparation is separate from setup. Never fetch Python before consent or a preview.
printf '%s\n' 'Runtime policy: request Python 3.13 through uv, with uv network access and Python downloads disabled.' 'If Python 3.13 is missing, prepare it separately with: uv python install 3.13 (network download), then rerun the same setup/bootstrap command.' 'These flags constrain uv, not every later Git/installer action. uv may write cache metadata; no cache-write-free guarantee. Bootstrap verify may inspect runtime; use setup --dry-run for configuration-only preview.' >&2
if [[ "${1:-}" != "--help" && "${1:-}" != "-h" ]] && ! command -v git >/dev/null 2>&1; then
  printf '%s\n' 'Git is required for bootstrap source verification. Install Git separately, then rerun the same command. No installer has run.' >&2
  exit 127
fi
export PYTHONDONTWRITEBYTECODE=1
exec "$uv_bin" run --offline --no-python-downloads --no-project --python 3.13 --script "$script_dir/agent_company_bootstrap.py" "$@"
