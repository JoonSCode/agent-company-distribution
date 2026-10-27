#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Transactional ownership of the opt-in routing PreToolUse command."""
import hashlib
from pathlib import Path
import shlex
import sys

from agent_company_completion_hook_install import _atomic, _decode, _encode, _read, HOOKS
from agent_company_install_types import InstallError

REGISTRY = 'agent-company/routing-hook.json'
SCRIPT = 'skills/company-orchestration/scripts/routing_hook.py'
PREFIX = ': agent-company-routing-hook=v1; exec '
SCHEMA = 'agent-company.routing-hook-install/v1'


def desired_entry(paths):
    command = PREFIX + shlex.join([str(Path(sys.executable).resolve()), '-B', str(paths.codex_home / SCRIPT)])
    return {'hooks': [{'type': 'command', 'command': command, 'timeout': 30}]}


def registry_entry(paths, raw):
    if raw is None:
        return None
    value = _decode(raw)
    if set(value) != {'schema_version', 'entry', 'script_sha256'} or value['schema_version'] != SCHEMA:
        raise InstallError('routing_hook_conflict', 'invalid owned registry')
    entry, digest = value['entry'], value['script_sha256']
    if entry is None and digest is None:
        return None
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
        raise InstallError('routing_hook_conflict', 'invalid script hash')
    if not isinstance(entry, dict) or set(entry) != {'hooks'} or not isinstance(entry['hooks'], list) or len(entry['hooks']) != 1:
        raise InstallError('routing_hook_conflict', 'invalid entry')
    item = entry['hooks'][0]
    if not isinstance(item, dict) or set(item) != {'type', 'command', 'timeout'} or item.get('type') != 'command' or item.get('timeout') != 30:
        raise InstallError('routing_hook_conflict', 'invalid command')
    command = item.get('command')
    try:
        args = shlex.split(command[len(PREFIX):]) if isinstance(command, str) and command.startswith(PREFIX) else []
    except ValueError as exc:
        raise InstallError('routing_hook_conflict', 'invalid quoting') from exc
    if len(args) != 3 or not Path(args[0]).is_absolute() or not Path(args[0]).name.startswith('python') or args[1:] != ['-B', str(paths.codex_home / SCRIPT)] or command != PREFIX + shlex.join(args):
        raise InstallError('routing_hook_conflict', 'command escaped owned target')
    return entry


def plan(paths, expected, desired, recovering=False):
    raw = _read(paths, HOOKS)
    document = _decode(raw)
    hooks = document.get('hooks', {})
    if not isinstance(hooks, dict):
        raise InstallError('routing_hook_conflict', 'invalid hooks')
    found = []
    for event, entries in hooks.items():
        if not isinstance(entries, list):
            raise InstallError('routing_hook_conflict', 'invalid event')
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get('hooks'), list):
                raise InstallError('routing_hook_conflict', 'invalid group')
            if any(isinstance(item, dict) and isinstance(item.get('command'), str) and item['command'].startswith(PREFIX) for item in entry['hooks']):
                if event != 'PreToolUse' or len(entry['hooks']) != 1:
                    raise InstallError('routing_hook_conflict', 'owned command moved or mixed')
                found.append(entry)
    if len(found) > 1:
        raise InstallError('routing_hook_conflict', 'duplicate owned command')
    actual = found[0] if found else None
    if actual != expected and not (recovering and actual == desired):
        raise InstallError('routing_hook_conflict', 'owned command changed')
    if actual == desired:
        return raw, raw
    entries = [entry for entry in hooks.get('PreToolUse', []) if entry not in found]
    if desired is not None:
        entries.append(desired)
    hooks['PreToolUse'] = entries
    document['hooks'] = hooks
    return raw, _encode(document)


def preflight_hook(paths, enabled=True):
    current = registry_entry(paths, _read(paths, REGISTRY))
    plan(paths, current, (current or desired_entry(paths)) if enabled else None)


def apply_hook(paths, enabled=True):
    before = _read(paths, REGISTRY)
    current = registry_entry(paths, before)
    desired = (current or desired_entry(paths)) if enabled else None
    raw, updated = plan(paths, current, desired)
    script = _read(paths, SCRIPT) if enabled else None
    if enabled and not script:
        raise InstallError('routing_hook_conflict', 'routing hook script missing')
    _atomic(paths, REGISTRY, _encode({'schema_version': SCHEMA, 'entry': desired,
            'script_sha256': hashlib.sha256(script).hexdigest() if script is not None else None}), before)
    if updated != raw:
        _atomic(paths, HOOKS, updated, raw)


def restore_hook(paths, desired_registry):
    current_registry = _read(paths, REGISTRY)
    if current_registry is None and desired_registry is None:
        return
    current, desired = registry_entry(paths, current_registry), registry_entry(paths, desired_registry)
    raw, updated = plan(paths, current, desired, recovering=True)
    if updated != raw:
        _atomic(paths, HOOKS, updated, raw)


def verify_hook(paths, expected_hash=None):
    raw = _read(paths, REGISTRY)
    if raw is None or (expected_hash is not None and hashlib.sha256(raw).hexdigest() != expected_hash):
        raise InstallError('routing_hook_conflict', 'registry missing or changed')
    entry = registry_entry(paths, raw)
    if entry is None:
        raise InstallError('routing_hook_conflict', 'routing hook not registered')
    plan(paths, entry, entry)
    script = _read(paths, SCRIPT)
    if not script or hashlib.sha256(script).hexdigest() != _decode(raw)['script_sha256']:
        raise InstallError('routing_hook_conflict', 'script missing or changed')
    return {'status': 'ok', 'event': 'PreToolUse', 'registry_sha256': hashlib.sha256(raw).hexdigest(), 'script_sha256': hashlib.sha256(script).hexdigest()}
