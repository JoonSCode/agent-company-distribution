#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Source/installed CLI for the single canonical Markdown resolver."""
import argparse
import json
from pathlib import Path
import sys

# Select Python's normal cache prefix before importing Company modules.
# Restrict this to the CLI process; callers importing a module are unchanged.
if __name__ == "__main__":
    import os as _os
    import sys as _sys
    _sys.pycache_prefix = _os.path.join(_os.path.abspath(_os.path.expanduser("~")), ".cache", "agent-company", "python")

# Read-only configuration is also called from managed skills and updater children.
sys.dont_write_bytecode = True

# The installed snapshot and source checkout have the same layout.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills/company-orchestration/scripts'))
from company_config import ConfigError, resolve, readiness, user_path, read_document, save_document, restore_document, encode


def main():
    parser = argparse.ArgumentParser(description='Show/explain resolved Company Markdown configuration')
    parser.add_argument('action', choices=['show', 'explain'])
    parser.add_argument('--home', type=Path)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--task-config', type=Path)
    parser.add_argument('--preset', choices=['single', 'multiple', 'custom'])
    args = parser.parse_args()
    try:
        result = resolve(home=args.home, user=args.config, task=args.task_config, preset=args.preset)
        result['routes'] = readiness(result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ConfigError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
