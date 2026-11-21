#!/usr/bin/env python3
"""Read-only launch residue explanation; never a launch or reconciliation grant."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

sys.dont_write_bytecode = True
from orca_contract import resolve_orca

LIMIT = 4 * 1024 * 1024
STATES = {'not_started', 'invocation_pending', 'unknown', 'observed'}
ORCA_ID = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', re.IGNORECASE)


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate key')
        result[key] = value
    return result


def _constant(value):
    raise ValueError('nonfinite JSON')


def _safe(path):
    # Do not resolve symlinks: evidence must stay at the supplied exact path.
    for part in (*reversed(path.parents), path):
        if part.is_symlink():
            raise ValueError('symlink path')


def inspect_file(path):
    """Return only metadata and a private parsed value; no artifact writes."""
    info = {'path': str(path)}
    try:
        _safe(path)
        observed = path.lstat()
        if not stat.S_ISREG(observed.st_mode):
            raise ValueError('not a regular file')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size > LIMIT:
                raise ValueError('not a bounded regular file')
            data = stream.read(LIMIT + 1)
            after = os.fstat(stream.fileno())
        if len(data) > LIMIT or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise ValueError('file changed during read')
        info.update(status='present', sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))
        try:
            value = json.loads(data, object_pairs_hook=_unique, parse_constant=_constant)
            info['json_status'] = 'valid'
        except (ValueError, UnicodeError, RecursionError):
            info['json_status'] = 'invalid'
            value = None
        return info, value
    except FileNotFoundError:
        info['status'] = 'absent'
    except (OSError, ValueError):
        info['status'] = 'unreadable_or_unsafe'
    return info, None


def inspect_directory(path):
    info = {'path': str(path), 'entries': []}
    try:
        _safe(path)
        if not stat.S_ISDIR(path.lstat().st_mode):
            raise ValueError('not a directory')
        # Fixed artifact directories only, one level, no recursive traversal.
        with os.scandir(path) as entries:
            names = []
            for entry in entries:
                names.append(entry.name)
                if len(names) > 64:
                    raise ValueError('too many entries')
        info['status'] = 'present'
        info['entries'] = [inspect_file(path / name)[0] for name in sorted(names)]
    except FileNotFoundError:
        info['status'] = 'absent'
    except (OSError, ValueError):
        info['status'] = 'unreadable_or_unsafe'
    return info


def start_request(state, receipt):
    """Read only structured Orca fields from the original, receipt-bound reply."""
    try:
        checked = receipt['receipt']
        argv = checked['launch_argv']
        if (receipt['ok'] is not True or receipt['label'] != 'real' or
                checked['decision_sha256'] != state['decision_sha256'] or
                argv[1:4] != ['orchestration', 'worker-start', '--from'] or
                argv[5] not in ('--spec', '--task')):
            return None
        reply = json.loads(state['stdout'], object_pairs_hook=_unique, parse_constant=_constant)
        runtime = reply.get('_meta', {}).get('runtimeId')
        if not isinstance(runtime, str) or not ORCA_ID.fullmatch(runtime):
            runtime = None
        pinned_runtime = checked.get('agy_runtime_id') or checked.get('host_catalog', {}).get('runtime_id')
        if pinned_runtime is not None and runtime != pinned_runtime:
            return None
        expected = {'runId': checked.get('requested_run'), 'taskId': argv[6] if argv[5] == '--task' else None,
                    'dispatchId': None}
        if reply.get('ok') is True:
            payload = reply['result']
            mutation = payload['mutation']
            if not runtime or type(mutation.get('replayed')) is not bool:
                return None
            request = mutation['requestId']
            for key, prior in expected.items():
                actual = payload.get(key)
                if prior is not None and actual is not None and prior != actual:
                    return None
                expected[key] = prior or actual
            source = 'orca_full_start_response'
        elif reply.get('ok') is False and state['exit_code'] != 0:
            data = reply['error']['data']
            request = data['orchestrationRequestId']
            if (data['originalCommand'][1:] != argv[1:] or data.get('requestSent') is False or
                    'server' in data):
                return None
            recovery = data.get('recovery')
            if recovery is not None and (recovery.get('orchestrationRequestId') != request or
                                         recovery.get('disposition') == 'not_sent'):
                return None
            expected['dispatchId'] = data.get('dispatchId')
            source = 'orca_cli_start_error'
        else:
            return None
        if (not isinstance(request, str) or not ORCA_ID.fullmatch(request) or request == reply.get('id') or
                any(value is not None and (not isinstance(value, str) or not value) for value in expected.values())):
            return None
        return {'request_id': request, 'runtime_id': runtime, 'source': source}, expected
    except (KeyError, IndexError, TypeError, AttributeError, ValueError, RecursionError):
        return None


def query_request(request, expected):
    """Observe the original request in the same runtime through Orca's caller-scoped lookup."""
    if request['runtime_id'] is None:
        return {'status': 'original_runtime_unavailable'}
    try:
        child = subprocess.run([resolve_orca(None), 'orchestration', 'request-show', '--request',
                                request['request_id'], '--environment', 'local', '--full', '--json'],
                               capture_output=True, timeout=30, check=False)
        if child.returncode != 0 or len(child.stdout) > LIMIT:
            return {'status': 'query_unavailable'}
        response = json.loads(child.stdout, object_pairs_hook=_unique, parse_constant=_constant)
        body = response['result']
        if response['ok'] is not True or body['requestId'] != request['request_id']:
            return {'status': 'request_mismatch'}
        if response['_meta']['runtimeId'] != request['runtime_id']:
            return {'status': 'runtime_mismatch'}
        observed = body['state']
        if observed == 'absent' and 'method' not in body and 'receipt' not in body:
            return {'status': 'absent', 'method': None}
        if body.get('method') != 'orchestration.workerStart':
            return {'status': 'method_mismatch'}
        if observed == 'pending':
            return {'status': 'pending', 'method': body['method']}
        if observed != 'completed':
            return {'status': 'query_unavailable'}
        saved = body['receipt']
        if saved['mutation']['requestId'] != request['request_id'] or type(saved['mutation']['replayed']) is not bool:
            return {'status': 'request_mismatch'}
        if any(value is not None and saved.get(key) != value for key, value in expected.items()):
            return {'status': 'start_identity_mismatch'}
        ids = {key: saved.get(key) for key in expected}
        return {'status': 'completed', 'method': body['method'],
                'recorded_start_ids': ids if all(isinstance(value, str) and value for value in ids.values()) else None}
    except (OSError, subprocess.SubprocessError, KeyError, TypeError, AttributeError, ValueError, RecursionError):
        return {'status': 'query_unavailable'}


def explain(result_path, receipt_path, *, query=False):
    result_path = Path(os.path.abspath(result_path))
    receipt_path = Path(os.path.abspath(receipt_path))
    state_file, state = inspect_file(result_path)
    receipt_file, receipt = inspect_file(receipt_path)
    refresh = inspect_directory(result_path.with_name(result_path.name + '.catalog-refresh'))
    archive = inspect_directory(result_path.with_name(result_path.name + '.reprepare'))
    lock, _ = inspect_file(result_path.with_name(result_path.name + '.lock'))
    valid_state = (isinstance(state, dict) and type(state.get('launch_state_version')) is int
                   and state['launch_state_version'] == 1 and isinstance(state.get('launch_state'), str)
                   and state['launch_state'] in STATES)
    local_state = state['launch_state'] if valid_state else 'unavailable_or_invalid'
    receipt_valid = isinstance(receipt, dict) and isinstance(receipt.get('receipt'), dict)
    receipt_binding = 'unknown'
    if valid_state and 'prelaunch_receipt_sha256' in state:
        receipt_binding = ('matches' if state['prelaunch_receipt_sha256'] == receipt_file.get('sha256')
                           else 'mismatch')
    # These are lower bounds from local artifacts, never inferred host no-start.
    if local_state == 'observed':
        stage = 'local_observed_state_recorded'
    elif local_state == 'unknown':
        stage = 'local_unknown_outcome_recorded'
    elif local_state == 'invocation_pending':
        stage = 'local_invocation_pending_recorded'
    elif receipt_valid:
        stage = 'prelaunch_receipt_present'
    elif refresh['status'] == 'present':
        stage = 'catalog_refresh_directory_present'
    elif archive['status'] == 'present':
        stage = 'inventory_reprepare_archive_present'
    elif local_state == 'not_started':
        stage = 'local_not_started_recorded'
    else:
        stage = 'unknown'
    reasons = ['trustworthy_host_no_start_evidence_missing', 'separate_approval_and_fresh_preparation_required']
    if local_state in {'invocation_pending', 'unknown', 'observed'}:
        reasons.append('prior_host_attempt_requires_authoritative_settlement')
    if refresh['status'] != 'absent' or archive['status'] != 'absent' or receipt_file['status'] != 'absent':
        reasons.append('exclusive_artifacts_must_be_preserved_not_reused')
    if local_state == 'not_started':
        reasons.append('local_not_started_does_not_prove_host_no_start_or_path_reusability')
    artifacts = {'state': state_file, 'receipt': receipt_file, 'catalog_refresh': refresh,
                 'inventory_archive': archive, 'lock': lock}
    invalid = any(item['status'] == 'unreadable_or_unsafe' for item in artifacts.values())
    invalid = invalid or any(entry['status'] == 'unreadable_or_unsafe'
                             for directory in (refresh, archive) for entry in directory['entries'])
    invalid = invalid or (state_file['status'] == 'present' and not valid_state)
    invalid = invalid or (receipt_file['status'] == 'present' and not receipt_valid) or receipt_binding == 'mismatch'
    bound_request = (start_request(state, receipt) if not invalid and receipt_binding == 'matches' and
                     local_state in ('unknown', 'observed') else None)
    request, expected = bound_request or (None, None)
    lookup = (query_request(request, expected) if request is not None else {'status': 'request_unavailable'}) if query else None
    return {'format': 'company-routing-explain/v1', 'ok': not invalid,
            'read_only': True, 'launch_authorized': False, 'local_state': local_state,
            'artifacts': artifacts, 'receipt_binding': receipt_binding,
            'last_observed_stage': stage, 'host_no_start': 'unknown',
            'new_attempt_allowed': False, 'same_attempt_retry_allowed': False,
            'reconcile_plan': {'status': 'blocked', 'reasons': reasons, 'orca_request': request,
                               'request_lookup': lookup, 'steps': [
                'Preserve exact result, receipt, refresh and archive artifacts; do not delete, overwrite or reset.',
                'Use --query-request in the original local Orca caller context when the original request and runtime were retained.',
                'Have the responsible host owner reconcile the exact prior Task/Dispatch and establish authoritative settlement or no-start evidence.',
                'Only after authoritative reconciliation and separate approval, prepare fresh inputs at entirely unused paths and run the existing live gates.']},
            'limits': ['Local artifact observations are not authenticated host evidence.',
                       'Directory presence proves neither refresh completion nor the exact denial stage.',
                       'Lock presence does not report lock ownership; concurrent snapshots are not atomic.',
                       'Request lookup observes an Orca receipt under its current caller identity. Absence does not prove no start.',
                       'Request completion does not prove worker liveness, consumer exit, or settlement.']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('explain', 'reconcile-plan'))
    parser.add_argument('--result', required=True, type=Path)
    parser.add_argument('--receipt', required=True, type=Path)
    parser.add_argument('--query-request', action='store_true', help='reconcile-plan only: read the retained exact request from local Orca')
    args = parser.parse_args(argv)
    if args.query_request and args.command != 'reconcile-plan':
        parser.error('--query-request requires reconcile-plan')
    report = explain(args.result, args.receipt, query=args.query_request)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
