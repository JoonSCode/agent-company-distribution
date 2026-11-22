#!/usr/bin/env python3
"""Offline checks for a generated public checkout, never a private source fallback.

Run from a public checkout: python3.13 -B scripts/check_public_distribution.py
No providers, workers, network requests, dependency installs or user-home writes.
"""
from __future__ import annotations

import ast
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]

# A successful unittest run with skipped cases is not a complete public gate.
UNITTEST_PROGRAM = '''import sys, unittest
suite = unittest.defaultTestLoader.discover('.', pattern='test_*.py')
result = unittest.TextTestRunner(verbosity=2).run(suite)
if result.skipped:
    print('public unit tests must not skip cases', file=sys.stderr)
sys.exit(0 if result.wasSuccessful() and not result.skipped else 1)
'''


class CheckError(Exception):
    pass


def inventory_files(root: Path) -> list[str]:
    inventory = root / 'PUBLIC_INVENTORY.txt'
    if not inventory.is_file():
        raise CheckError('PUBLIC_INVENTORY.txt is required; run against the generated public checkout')
    files = inventory.read_text().splitlines()
    if files != sorted(set(files)):
        raise CheckError('public inventory is not sorted and unique')
    for name in files:
        target = root / name
        if Path(name).is_absolute() or '..' in Path(name).parts or not target.is_file() or target.is_symlink():
            raise CheckError(f'invalid or missing inventory file: {name}')
    result = subprocess.run(['git', '--no-replace-objects', '-c', 'core.fsmonitor=false',
                             'ls-files', '-z'], cwd=root, capture_output=True, check=True)
    tracked = result.stdout.decode().rstrip('\0').split('\0')
    if set(tracked) != set(files):
        raise CheckError('public inventory differs from the tracked checkout')
    return files


def heading_ids(text: str) -> set[str]:
    # GitHub-style Unicode heading slugs, duplicate suffixes and explicit HTML IDs.
    seen: dict[str, int] = {}
    ids = set(re.findall(r'\b(?:id|name)=[\"\']([^\"\']+)', text))
    fenced = False
    for line in text.splitlines():
        if re.match(r'^\s*(```|~~~)', line):
            fenced = not fenced
            continue
        match = re.match(r'^#{1,6}\s+(.+?)\s*#*$', line)
        if fenced or not match:
            continue
        title = re.sub(r'<[^>]*>', '', match.group(1)).lower()
        title = re.sub(r'[^\w\- ]', '', title).replace(' ', '-')
        count = seen.get(title, 0)
        seen[title] = count + 1
        ids.add(title + (f'-{count}' if count else ''))
    return ids


class HTMLLinks(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if value and name in {'href', 'src', 'srcset'}:
                if name == 'srcset':
                    self.links.extend(item.strip().split()[0] for item in value.split(',') if item.strip())
                else:
                    self.links.append(value)


def local_links(root: Path, files: list[str]) -> list[dict[str, str]]:
    checked = []
    for name in files:
        if Path(name).suffix.lower() != '.md':
            continue
        text = (root / name).read_text()
        html = HTMLLinks()
        html.feed(text)
        links = re.findall(r'\]\(<?([^\s)>]+)>?(?:\s+[\"\'][^)]*)?\)', text)
        # Reference-style definitions are also targets, even if unused.
        links += re.findall(r'^\s{0,3}\[[^\]]+\]:\s*<?([^\s>]+)>?', text, re.M)
        for link in links + html.links:
            parsed = urlsplit(link)
            if parsed.scheme or parsed.netloc:
                continue
            path = (root / name).parent / unquote(parsed.path) if parsed.path else root / name
            path = path.resolve()
            if not path.is_relative_to(root.resolve()) or not path.exists():
                raise CheckError(f'broken local link: {name} -> {link}')
            if parsed.fragment and path.suffix.lower() == '.md':
                if unquote(parsed.fragment) not in heading_ids(path.read_text()):
                    raise CheckError(f'broken Markdown anchor: {name} -> {link}')
            checked.append({'from': name, 'target': link})
    return checked


def import_closure(root: Path, files: list[str]) -> None:
    # Package tools use flat sibling imports and root tools add the bundled package.
    # jsonschema is explicitly optional/dependency-declared by its runtime consumers;
    # the offline tests/demo below need only the stdlib.
    local = {Path(name).stem for name in files if name.endswith('.py')}
    for name in files:
        if not name.endswith('.py'):
            continue
        for node in ast.walk(ast.parse((root / name).read_text(), filename=name)):
            imports = ([alias.name for alias in node.names] if isinstance(node, ast.Import)
                       else [node.module] if isinstance(node, ast.ImportFrom) and node.module else [])
            for module in imports:
                top = module.split('.')[0]
                if top not in sys.stdlib_module_names and top not in local and top != 'jsonschema':
                    raise CheckError(f'unshipped Python import: {name} -> {top}')


def run_checks(root: Path = ROOT) -> dict[str, object]:
    if not Path('/bin/zsh').is_file():
        raise CheckError('zsh is required for the controlled PTY test; install zsh before running the public checks')
    files = inventory_files(root)
    links = local_links(root, files)
    import_closure(root, files)
    results = []
    # Never inherit credentials, private PYTHONPATH or provider configuration.
    with tempfile.TemporaryDirectory(prefix='company-public-check-') as raw:
        home = Path(raw).resolve(strict=True)
        env = {'PATH': os.defpath, 'HOME': str(home), 'TMPDIR': str(home),
               'CODEX_HOME': str(home / 'codex'), 'CLAUDE_CONFIG_DIR': str(home / 'claude'),
               'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONNOUSERSITE': '1',
               'UV_OFFLINE': '1', 'UV_PYTHON_DOWNLOADS': 'never', 'PIP_NO_INDEX': '1',
               'LANG': 'C.UTF-8', 'TERM': 'xterm-256color'}
        script_dir = root / 'skills/company-orchestration/scripts'
        # The full runtime suite can take more than ten minutes on a busy host.
        commands = [
            ([sys.executable, '-E', '-s', '-B', '-c', UNITTEST_PROGRAM], script_dir, 900),
            ([sys.executable, '-E', '-s', '-B', str(script_dir / 'policy_manifest.py'), 'check'], root, 300),
        ]
        for command, cwd, timeout in commands:
            result = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True, timeout=timeout)
            sys.stdout.write(result.stdout)
            sys.stderr.write(result.stderr)
            results.append({'command': command, 'exit': result.returncode})
            if result.returncode:
                raise CheckError(f'public command failed ({result.returncode}): {command}')
        capture = json.loads((root / 'assets/readme/capture.json').read_text())
        for frame in capture['frames']:
            command = [sys.executable, '-E', '-s', '-B', str(root / 'scripts/agent_company_demo.py'),
                       '--once', '--width', str(frame['columns']), '--height', str(frame['rows']),
                       '--layout', frame['layout']]
            result = subprocess.run(command, cwd=home, env=env, capture_output=True, timeout=30)
            expected = root / 'assets/readme' / (frame['name'] + '.txt')
            if result.returncode or result.stdout != expected.read_bytes() or hashlib.sha256(result.stdout).hexdigest() != frame['stdout_sha256']:
                raise CheckError(f'demo output/capture differs: {frame["name"]}')
            image = root / 'assets/readme' / (frame['name'] + '.png')
            if hashlib.sha256(image.read_bytes()).hexdigest() != frame['png_sha256']:
                raise CheckError(f'demo image hash differs: {frame["name"]}')
            results.append({'command': command, 'exit': result.returncode})
        if list(home.iterdir()):
            raise CheckError('offline checks wrote into their isolated HOME')
    return {'status': 'passed', 'files': len(files), 'local_links': len(links),
            'commands': results, 'capture_frames': len(capture['frames'])}


def main() -> int:
    try:
        print(json.dumps(run_checks(), indent=2))
    except (CheckError, OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f'public check failed: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
