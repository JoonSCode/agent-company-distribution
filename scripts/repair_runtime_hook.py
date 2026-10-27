#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Explicit transactional Company hook installation for a shared Orca home.

Default is dry-run. Copies only the already trusted canonical Company command;
never changes skills, plugin settings, disabled hooks or other owners' entries.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import tomllib
import uuid

import agent_company_completion_hook_install as hook
import agent_company_routing_hook_install as routing_hook
from agent_company_hook_probe import list_hooks
from agent_company_execution_health import installation_home
from agent_company_install_engine import verify_prior
from agent_company_install_io import install_paths, read_json
from agent_company_install_lock import acquire_lock, release_lock
from agent_company_install_state import load_index
from agent_company_install_types import InstallError


def sha(data):
    return hashlib.sha256(data).hexdigest() if data is not None else None


def install_runtime_hook(home: Path, runtime: Path, *, apply: bool = False) -> dict:
    home, runtime = home.expanduser().absolute(), runtime.expanduser().absolute()
    paths, target = install_paths(home), install_paths(runtime)
    if runtime == home or installation_home(runtime) != home:
        raise InstallError('runtime_hook_conflict', 'target must resolve to this installation through shared skills or the standard Orca home')
    lock = acquire_lock(paths)
    try:
        if paths.journal.exists():
            raise InstallError('recovery_required', 'finish the canonical install transaction first')
        verify_prior(paths, load_index(paths))
        active = read_json(paths.root / 'active.json')
        hook.verify_hook(paths, active.get('completion_hook_sha256'))
        entry = hook._registry_entry(paths, hook._read(paths, hook.REGISTRY))
        canonical_hooks = list_hooks(home)
        canonical = [row for row in canonical_hooks if row.get('command') == entry['hooks'][0]['command']]
        if len(canonical) != 1 or canonical[0].get('enabled') is not True or canonical[0].get('trustStatus') != 'trusted':
            raise InstallError('runtime_hook_conflict', 'canonical Company command must already be enabled and trusted')
        trust = canonical[0].get('currentHash')
        if not isinstance(trust, str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', trust):
            raise InstallError('runtime_hook_conflict', 'canonical trust digest unavailable')
        routing_entry, routing_trust = None, None
        if active.get('routing_hook_sha256'):
            routing_hook.verify_hook(paths, active['routing_hook_sha256'])
            routing_entry = routing_hook.registry_entry(paths, hook._read(paths, routing_hook.REGISTRY))
            rows = [row for row in canonical_hooks if row.get('command') == routing_entry['hooks'][0]['command']]
            if len(rows) != 1 or rows[0].get('enabled') is not True or rows[0].get('trustStatus') != 'trusted':
                raise InstallError('runtime_hook_conflict', 'canonical routing command must already be enabled and trusted')
            routing_trust = rows[0].get('currentHash')
            if not isinstance(routing_trust, str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', routing_trust):
                raise InstallError('runtime_hook_conflict', 'canonical routing trust digest unavailable')
        old_hooks = hook._read(target, hook.HOOKS)
        old_config = hook._read(target, 'config.toml')
        if old_hooks is None or old_config is None:
            raise InstallError('runtime_hook_conflict', 'target must have its existing Orca hooks.json and config.toml')
        _, _, owned = hook._owned(hook._decode(old_hooks))
        prior_entry = owned[0] if owned else None
        if prior_entry is not None and prior_entry != entry:
            raise InstallError('runtime_hook_conflict', 'existing Company command differs; preserve it for review')
        _, new_hooks = hook._plan(target, prior_entry, entry)
        prior_routing = None
        if routing_entry is not None:
            document = hook._decode(old_hooks)
            routing_groups = document.get('hooks', {}).get('PreToolUse', [])
            if not isinstance(routing_groups, list):
                raise InstallError('runtime_hook_conflict', 'invalid target PreToolUse groups')
            owned_routing = [group for group in routing_groups if isinstance(group, dict) and any(
                isinstance(item, dict) and isinstance(item.get('command'), str) and item['command'].startswith(routing_hook.PREFIX)
                for item in group.get('hooks', []))]
            if len(owned_routing) > 1:
                raise InstallError('runtime_hook_conflict', 'duplicate target routing command')
            prior_routing = owned_routing[0] if owned_routing else None
            if prior_routing is not None and prior_routing != routing_entry:
                raise InstallError('runtime_hook_conflict', 'existing routing command differs; preserve it for review')
            routing_hook.plan(target, prior_routing, prior_routing)
            document = hook._decode(new_hooks)
            groups = document.setdefault('hooks', {}).setdefault('PreToolUse', [])
            if prior_routing is None:
                groups.append(routing_entry)
            new_hooks = hook._encode(document)
        stop = hook._decode(new_hooks)['hooks']['Stop']
        key = f'{runtime / hook.HOOKS}:stop:{stop.index(entry)}:0'
        cfg = tomllib.loads(old_config.decode())
        state = cfg.get('hooks', {}).get('state', {}).get(key)
        if cfg.get('features', {}).get('hooks') is False or (state is not None and state.get('enabled') is False):
            raise InstallError('runtime_hook_conflict', 'target hooks were explicitly disabled; do not enable them')
        if state is not None and state.get('trusted_hash') != trust:
            raise InstallError('runtime_hook_conflict', 'existing target trust differs; preserve it for review')
        new_config = old_config
        if state is None:
            new_config += ('\n[hooks.state.' + json.dumps(key, ensure_ascii=False) + ']\ntrusted_hash = ' + json.dumps(trust) + '\n').encode()
        routing_key = None
        if routing_entry is not None:
            groups = hook._decode(new_hooks)['hooks']['PreToolUse']
            routing_key = f'{runtime / hook.HOOKS}:pre_tool_use:{groups.index(routing_entry)}:0'
            routing_state = cfg.get('hooks', {}).get('state', {}).get(routing_key)
            if routing_state is not None and (routing_state.get('enabled') is False or routing_state.get('trusted_hash') != routing_trust):
                raise InstallError('runtime_hook_conflict', 'target routing hook is disabled or trust differs')
            if routing_state is None:
                new_config += ('\n[hooks.state.' + json.dumps(routing_key, ensure_ascii=False) + ']\ntrusted_hash = ' + json.dumps(routing_trust) + '\n').encode()
        if len(new_config) > hook.MAX_BYTES:
            raise InstallError('runtime_hook_conflict', 'proposed configuration exceeds the bounded size limit')
        # Parse the exact proposed bytes before writing any file.
        tomllib.loads(new_config.decode())
        result = {'status': 'dry_run', 'runtime_home': str(runtime), 'hook_key': key,
                  'trusted_hash': trust, 'before': {'hooks': sha(old_hooks), 'config': sha(old_config)},
                  'after': {'hooks': sha(new_hooks), 'config': sha(new_config)}}
        if routing_entry is not None:
            result['routing_hook_key'] = routing_key
            result['routing_trusted_hash'] = routing_trust
        if not apply:
            return result
        transaction = f'agent-company/state/runtime-hook-transactions/{uuid.uuid4().hex}'
        hook._atomic(paths, transaction + '/before-hooks.json', old_hooks, None)
        hook._atomic(paths, transaction + '/before-config.toml', old_config, None)
        receipt = transaction + '/receipt.json'
        result.update(status='pending', receipt=str(home / receipt))
        hook._atomic(paths, receipt, hook._encode(result), None)
        wrote_hooks = wrote_config = False
        try:
            if new_hooks != old_hooks:
                hook._atomic(target, hook.HOOKS, new_hooks, old_hooks)
                wrote_hooks = True
            if new_config != old_config:
                hook._atomic(target, 'config.toml', new_config, old_config)
                wrote_config = True
            observed = [row for row in list_hooks(runtime) if row.get('command') == entry['hooks'][0]['command']]
            if len(observed) != 1 or observed[0].get('enabled') is not True or observed[0].get('trustStatus') != 'trusted':
                raise InstallError('runtime_hook_conflict', 'fresh target hooks/list did not confirm enabled trusted registration')
            if routing_entry is not None:
                observed_routing = [row for row in list_hooks(runtime) if row.get('command') == routing_entry['hooks'][0]['command']]
                if len(observed_routing) != 1 or observed_routing[0].get('enabled') is not True or observed_routing[0].get('trustStatus') != 'trusted':
                    raise InstallError('runtime_hook_conflict', 'fresh target hooks/list did not confirm routing registration')
            result['status'] = 'installed'
        except (InstallError, OSError, ValueError) as error:
            result.update(status='rolled_back', error=str(error))
            try:
                if wrote_config:
                    hook._atomic(target, 'config.toml', old_config, new_config)
                if wrote_hooks:
                    if routing_entry is not None:
                        current, restored = routing_hook.plan(target, routing_entry, prior_routing)
                        if restored != current:
                            hook._atomic(target, hook.HOOKS, restored, current)
                    # Merge only our prior entry back into the latest document,
                    # retaining unrelated edits made after the attempted install.
                    current, restored = hook._plan(target, entry, prior_entry)
                    if restored != current:
                        hook._atomic(target, hook.HOOKS, restored, current)
            except (InstallError, OSError, ValueError) as rollback_error:
                result.update(status='recovery_required', rollback_error=str(rollback_error))
            previous = hook._read(paths, receipt)
            hook._atomic(paths, receipt, hook._encode(result), previous)
            raise InstallError('runtime_hook_conflict', f'{result["status"]}; inspect {home / receipt}') from error
        previous = hook._read(paths, receipt)
        hook._atomic(paths, receipt, hook._encode(result), previous)
        return result
    finally:
        release_lock(paths, lock)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--codex-home', type=Path, default=install_paths().codex_home)
    parser.add_argument('--runtime-home', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    try:
        result = install_runtime_hook(args.codex_home, args.runtime_home, apply=args.apply)
    except (InstallError, OSError, ValueError, TypeError, AttributeError) as error:
        print(json.dumps({'status': 'error', 'reason': str(error)}))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
