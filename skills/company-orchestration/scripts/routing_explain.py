#!/usr/bin/env python3
"""Read-only launch residue explanation; never a launch or reconciliation grant."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat

LIMIT = 4 * 1024 * 1024
STATES = {'not_started', 'invocation_pending', 'unknown', 'observed'}


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


def explain(result_path, receipt_path):
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
    return {'format': 'company-routing-explain/v1', 'ok': not invalid,
            'read_only': True, 'launch_authorized': False, 'local_state': local_state,
            'artifacts': artifacts, 'receipt_binding': receipt_binding,
            'last_observed_stage': stage, 'host_no_start': 'unknown',
            'new_attempt_allowed': False, 'same_attempt_retry_allowed': False,
            'reconcile_plan': {'status': 'blocked', 'reasons': reasons, 'steps': [
                'Preserve exact result, receipt, refresh and archive artifacts; do not delete, overwrite or reset.',
                'Have the responsible host owner reconcile the exact prior Task/Dispatch and establish authoritative settlement or no-start evidence.',
                'Only after authoritative reconciliation and separate approval, prepare fresh inputs at entirely unused paths and run the existing live gates.']},
            'limits': ['Local artifact observations are not authenticated host evidence.',
                       'Directory presence proves neither refresh completion nor the exact denial stage.',
                       'Lock presence does not report lock ownership; concurrent snapshots are not atomic.',
                       'No host evidence importer or retry authorization is implemented here.']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('explain', 'reconcile-plan'))
    parser.add_argument('--result', required=True, type=Path)
    parser.add_argument('--receipt', required=True, type=Path)
    args = parser.parse_args(argv)
    report = explain(args.result, args.receipt)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
