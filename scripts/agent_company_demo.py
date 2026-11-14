#!/usr/bin/env python3
"""Explore the real Company TUI with bundled synthetic records, no model or install."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
# Both paths are part of the public runtime; no development checkout is needed.
sys.path.insert(0, str(ROOT / 'skills' / 'company-orchestration' / 'scripts'))
import status_tui


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, epilog=(
        'No credentials, Orca connection, installation or live workers. '
        'Interactive: j/k select, x focus, w wide, o/f/c views, q exit. '
        'Use --once in CI or a non-interactive shell.'))
    parser.add_argument('--once', action='store_true', help='print a checked frame and exit; writes no state')
    parser.add_argument('--json', action='store_true', help='print the validated read model; requires --once')
    parser.add_argument('--width', type=int, help='frame columns; requires --once (default 80)')
    parser.add_argument('--height', type=int, help='frame rows; requires --once (default 24)')
    parser.add_argument('--layout', choices=('wide', 'focus'), default='wide')
    parser.add_argument('--unicode', action='store_true', help='original Unicode/Korean labels instead of English ASCII')
    parser.add_argument('--palette', choices=('light', 'dark'), default='light', help='Unicode colors only; no host theme changes')
    args = parser.parse_args(argv)
    if not args.once and (args.json or args.width is not None or args.height is not None):
        parser.error('--json/--width/--height require --once')
    if any(value is not None and value < 1 for value in (args.width, args.height)):
        parser.error('positive dimensions required')
    if not args.once and not (sys.stdin.isatty() and sys.stdout.isatty()):
        print('Company demo: interactive mode needs a terminal. Try: python3 scripts/agent_company_demo.py --once', file=sys.stderr)
        return 2
    forwarded = ['--manifest', str(ROOT / 'skills' / 'company-orchestration' / 'assets' / 'demo' / 'view.json'),
                 '--layout', args.layout, '--palette', args.palette]
    if not args.unicode:
        forwarded.append('--ascii')
    if args.once:
        forwarded += ['--once', '--width', str(args.width or 80), '--height', str(args.height or 24)]
    if args.json:
        forwarded.append('--json')
    return status_tui.main(forwarded)


if __name__ == '__main__':
    sys.exit(main())
