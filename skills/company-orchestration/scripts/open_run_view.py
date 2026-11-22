#!/usr/bin/env python3
"""Open the current local Orca coordinator's Run view once per tab and Run."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import sys

if __name__ == '__main__':
    sys.pycache_prefix = os.path.join(os.path.abspath(os.path.expanduser('~')), '.cache', 'agent-company', 'python')
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from company_config import canonical_home
from orca_contract import resolve_orca


def orca_result(orca, *args, timeout=3):
    reply = subprocess.run([orca, *args, '--environment', 'local', '--json'],
                           capture_output=True, timeout=timeout, check=False)
    if reply.returncode:
        raise ValueError('Orca command failed')
    payload = json.loads(reply.stdout)
    if not isinstance(payload, dict) or payload.get('ok') is not True or not isinstance(payload.get('result'), dict):
        raise ValueError('invalid Orca reply')
    return payload['result']


def owned_run(orca, handle):
    run = orca_result(orca, 'orchestration', 'run-current', '--full').get('run')
    if run is None:
        return None
    if not isinstance(run, dict):
        raise ValueError('invalid Run binding')
    if run.get('coordinator_handle') != handle or run.get('legacy') != 0:
        return None
    run_id = run.get('id')
    if not isinstance(run_id, str) or not re.fullmatch(r'run_[A-Za-z0-9_-]{1,128}', run_id):
        raise ValueError('invalid Run ID')
    return run_id


def claim_split(tab, run_id):
    root = canonical_home() / 'agent-company/state/run-view'
    if root.resolve() != root:
        raise ValueError('unsafe Run view state path')
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(directory)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise ValueError('Run view state must be private')
        marker = hashlib.sha256(f'{tab}\n{run_id}'.encode()).hexdigest() + '.attempt'
        try:
            fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        except FileExistsError:
            return False
        os.close(fd)
        # Keep the claim even if the process dies after Orca accepted the split.
        os.fsync(directory)
        return True
    finally:
        os.close(directory)


def open_current():
    handle = os.environ.get('ORCA_TERMINAL_HANDLE')
    if not handle:
        return {'status': 'skipped', 'reason': 'no_orca_terminal'}
    orca = resolve_orca(None)
    run_id = owned_run(orca, handle)
    if run_id is None:
        return {'status': 'skipped', 'reason': 'no_owned_local_run'}
    terminal = orca_result(orca, 'terminal', 'show', '--terminal', handle).get('terminal')
    if not isinstance(terminal, dict) or terminal.get('handle') != handle:
        raise ValueError('terminal identity mismatch')
    tab, leaf = terminal.get('tabId'), terminal.get('leafId')
    if (not isinstance(tab, str) or not tab or not isinstance(leaf, str) or not leaf
            or terminal.get('connected') is not True or terminal.get('orphaned') is not False
            or terminal.get('writable') is not True or terminal.get('executionHostId') != 'local'):
        return {'status': 'skipped', 'reason': 'no_owned_local_pane'}
    if owned_run(orca, handle) != run_id:
        return {'status': 'skipped', 'reason': 'run_binding_changed'}
    if not claim_split(tab, run_id):
        return {'status': 'already_requested', 'run_id': run_id}
    command = 'exec ' + shlex.join([sys.executable, '-B', str(Path(__file__).with_name('status_tui.py')),
                                   '--run', run_id])
    try:
        split = orca_result(orca, 'terminal', 'split', '--terminal', handle, '--direction',
                            'horizontal', '--command', command, timeout=12).get('split')
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {'status': 'split_unconfirmed', 'run_id': run_id}
    if (not isinstance(split, dict) or split.get('tabId') != tab or not split.get('leafId')
            or split['leafId'] == leaf or not split.get('handle') or split['handle'] == handle):
        return {'status': 'split_unconfirmed', 'run_id': run_id}
    return {'status': 'pane_accepted', 'run_id': run_id, 'terminal': split['handle'], 'tab_id': tab}


if __name__ == '__main__':
    try:
        result = open_current()
    except (OSError, ValueError, subprocess.TimeoutExpired):
        result = {'status': 'skipped', 'reason': 'local_read_or_state_unavailable'}
    print(json.dumps(result))
