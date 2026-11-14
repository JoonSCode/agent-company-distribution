#!/usr/bin/env python3
"""Run a checked new Orca worker-start; this is not a server enforcement boundary."""
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import fcntl
import shutil
import stat
import secrets
import sqlite3
import tempfile
import json
import math
import os
from pathlib import Path
import subprocess
import sys

# Select Python's normal cache prefix before importing Company modules.
# Restrict this to the CLI process; callers importing a module are unchanged.
if __name__ == "__main__":
    import os as _os
    import sys as _sys
    _sys.pycache_prefix = _os.path.join(_os.path.abspath(_os.path.expanduser("~")), ".cache", "agent-company", "python")

from record_check import check_routing, read_json_snapshot
from orca_contract import resolve_orca
from company_config import resolve, resource_manifest_check


def atomic_state(path, value):
    """Replace a complete state and sync both its data and directory entry."""
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def timeout_stream_metadata(value):
    """Describe only the complete available buffer, never the whole child stream."""
    kind, data, encoding = 'unsupported', None, None
    if value is None:
        kind = 'none'
    elif isinstance(value, bytes):
        kind, data, encoding = 'bytes', value, 'raw'
    elif isinstance(value, str):
        kind, data, encoding = 'str', value.encode('utf-8', 'surrogatepass'), 'utf-8/surrogatepass'
    return {'type': kind, 'present': value is not None,
            'available_bytes': len(data) if data is not None else None,
            'available_sha256': hashlib.sha256(data).hexdigest() if data is not None else None,
            'hash_scope': 'available_buffer' if data is not None else 'none',
            'encoding': encoding, 'raw_retained': False}


def write_timeout_state(path, value):
    """Publish private metadata via trusted directory descriptors, or keep pending.

    This deliberately applies only to timeout diagnostics, not normal launch IO.
    Never resolve a symlink or chmod an existing directory/target.
    """
    data = (json.dumps(value, ensure_ascii=True, indent=2) + '\n').encode('utf-8')
    if len(data) > 4096:
        raise ValueError('timeout metadata exceeds bound')
    path = path.absolute()
    if '..' in path.parts:
        raise ValueError('unsafe diagnostic path')
    directory = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    temporary = []
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
            info = os.fstat(directory)
            if info.st_uid not in (0, os.getuid()) or info.st_mode & 0o022:
                raise ValueError('unsafe diagnostic directory')
        target = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        try:
            info = os.fstat(target)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or
                    info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 4096):
                raise ValueError('unsafe diagnostic target')
            original = os.read(target, 4097)
            if json.loads(original).get('launch_state') != 'invocation_pending':
                raise ValueError('diagnostic target is not pending')
        finally:
            os.close(target)
        # A private rollback copy keeps pending truthful even if directory sync fails.
        for content in (original, data):
            name = '.timeout-' + secrets.token_hex(16)
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=directory)
            temporary.append(name)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        current = os.stat(path.name, dir_fd=directory, follow_symlinks=False)
        if (current.st_dev, current.st_ino, current.st_nlink, current.st_mode, current.st_uid) != (
                info.st_dev, info.st_ino, info.st_nlink, info.st_mode, info.st_uid):
            raise ValueError('diagnostic target changed')
        os.replace(temporary[1], path.name, src_dir_fd=directory, dst_dir_fd=directory)
        try:
            os.fsync(directory)
            os.unlink(temporary[0], dir_fd=directory)
        except OSError:
            os.replace(temporary[0], path.name, src_dir_fd=directory, dst_dir_fd=directory)
            raise
    finally:
        try:
            for name in temporary:
                try:
                    os.unlink(name, dir_fd=directory)
                except FileNotFoundError:
                    pass
        finally:
            os.close(directory)


def finite_timeout(value):
    try:
        number = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError('timeout must be finite and positive')
    if not math.isfinite(number) or not 0 < number <= 3600:
        raise argparse.ArgumentTypeError('timeout must be finite, positive, and at most 3600 seconds')
    return number


def main(argv=None):
    # Parse all arguments before creating the lock or result (including --help).
    args = argument_parser().parse_args(argv)
    # The lock is stable across atomic replacement and covers all local prechecks.
    path = args.result
    try:
        with path.with_name(path.name + '.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                print(json.dumps({'ok': False, 'error': 'result locked; reconciliation required'}))
                return 1
            if args.reprepare_inventory and (path.exists() or args.receipt.exists() or
                    path.with_name(path.name + '.reprepare').exists()):
                print(json.dumps({'ok': False, 'error': 'reprepare requires unused result and receipt paths; preserve prior attempts'}))
                return 1
            if args.reprepare_inventory:
                # This narrow opt-in cannot follow a host probe, reuse or lifecycle start.
                current, error, _ = read_json_snapshot(args.record)
                if (error or not isinstance(current, dict) or current.get('measurement') is not None or
                        args.task or args.retry_of or args.terminal or args.reuse_dispatch or
                        args.origin_receipt or args.measurement_attempt):
                    print(json.dumps({'ok': False, 'error': 'inventory reprepare supports only a fresh non-measurement spec launch'}))
                    return 1
            if path.exists():
                try:
                    prior = json.loads(path.read_text(encoding='utf-8'))
                    if prior.get('launch_state_version') != 1 or prior.get('launch_state') != 'not_started':
                        raise ValueError('unresolved or completed')
                except (OSError, ValueError, AttributeError):
                    print(json.dumps({'ok': False, 'error': 'result already exists; reconciliation required'}))
                    return 1
            atomic_state(path, {'launch_state_version': 1, 'launch_state': 'not_started'})
            from measurement_lifecycle import launch_guard
            try:
                with launch_guard(args) as lifecycle:
                    args.lifecycle = lifecycle
                    return _main(args)
            except (ValueError, KeyError, TypeError, AttributeError, sqlite3.Error, subprocess.SubprocessError) as exc:
                print(json.dumps({'ok': False, 'error': 'measurement lifecycle blocked', 'detail': str(exc)}))
                return 1
    except OSError as exc:
        print(json.dumps({'ok': False, 'error': 'result persistence failed', 'detail': str(exc)}))
        return 1


def argument_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--orca', help='single Orca executable (not a shell command)')
    parser.add_argument('--measurement-attempt', help='v2 prepared attempt ID; no fresh retry on unknown start')
    parser.add_argument('--decision', required=True, type=Path)
    parser.add_argument('--reprepare-inventory', type=Path,
                        help='explicit one-time pre-host reprepare using a full hash-matching preparation snapshot')
    parser.add_argument('--record', required=True, type=Path)
    parser.add_argument('--receipt', required=True, type=Path)
    parser.add_argument('--result', required=True, type=Path)
    parser.add_argument('--from', dest='sender', required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--spec')
    mode.add_argument('--task')
    parser.add_argument('--retry-of')
    parser.add_argument('--run')
    parser.add_argument('--worktree', required=True)
    parser.add_argument('--name')
    parser.add_argument('--repo')
    parser.add_argument('--base-branch')
    parser.add_argument('--setup', choices=('run', 'skip', 'inherit'))
    parser.add_argument('--display-name')
    parser.add_argument('--task-title')
    parser.add_argument('--parent')
    parser.add_argument('--terminal')
    parser.add_argument('--reuse-dispatch')
    parser.add_argument('--origin-receipt', type=Path)
    parser.add_argument('--resource-manifest', type=Path, help='nonsecret declaration file')
    parser.add_argument('--require-resource-manifest', action='store_true')
    parser.add_argument('--declared-host')
    parser.add_argument('--declared-tool', action='append', default=[])
    parser.add_argument('--declared-billing', choices=('subscription', 'paid_api'))
    parser.add_argument('--declared-spend', type=float)
    parser.add_argument('--require-trusted-capacity', action='store_true', help='deny: trusted issuer/reservation is not supported')
    parser.add_argument('--probe-timeout', type=finite_timeout, default=30.0)
    parser.add_argument('--start-timeout', type=finite_timeout, default=300.0)
    return parser


def reprepare_inventory(args, decision, record, rejected, original_hash):
    """Explicit fresh evidence binding, not a relaxed inventory hash check.

    Only fetched_at may advance within the already approved freshness window.
    All other JSON fields (including unknown fields) must be identical. Keep both
    complete byte streams: a model/effort projection is not an inventory snapshot.
    """
    from record_check import canonical_home, make_profile_binding

    def require(condition, message):
        if not condition:
            raise ValueError(message)

    def unique_object(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value, 'duplicate inventory JSON key')
            value[key] = item
        return value

    def invalid_constant(value):
        raise ValueError('nonfinite inventory JSON value: ' + value)

    ref = decision['price_selection']['inventory_evidence']
    inventory = decision['evidence'][ref]
    expected_errors = {('$.evidence.' + ref, 'hash_mismatch'),
                       ('$.price_selection', 'price_selection_invalid')}
    require(not rejected['ok'] and decision['label'] == 'real' and
            {(e['path'], e['code']) for e in rejected['errors']} == expected_errors and
            any(e['message'] == 'Candidate inventory hash changed before comparison' for e in rejected['errors']),
            'reprepare is limited to an inventory-only hash denial')
    require(json.loads(args.result.read_bytes()) == {'launch_state_version': 1, 'launch_state': 'not_started'},
            'reprepare requires authoritative local not_started before any host invocation')
    path = (args.decision.parent / inventory['file']).resolve()
    require(path == (canonical_home() / 'models_cache.json').resolve(), 'inventory is not canonical')
    before = args.reprepare_inventory.read_bytes()
    require(hashlib.sha256(before).hexdigest() == inventory['sha256'], 'missing hash-matching full inventory snapshot')
    current = path.read_bytes()
    old = json.loads(before, object_pairs_hook=unique_object, parse_constant=invalid_constant)
    new = json.loads(current, object_pairs_hook=unique_object, parse_constant=invalid_constant)
    require(isinstance(old, dict) and isinstance(new, dict), 'inventory must be an object')
    require(isinstance(new.get('models'), list) and bool(new['models']), 'missing or partial models inventory')
    # No model/capability/price/availability field is projected out. Unknown
    # envelope fields, client identity/version and etag changes need review too.
    require(json.dumps({k: v for k, v in old.items() if k != 'fetched_at'}, sort_keys=True) ==
            json.dumps({k: v for k, v in new.items() if k != 'fetched_at'}, sort_keys=True),
            'inventory content changed; material selection review required')
    old_time, new_time, observed, until = [datetime.fromisoformat(value.replace('Z', '+00:00'))
        for value in (old['fetched_at'], new['fetched_at'], inventory['observed_at'], inventory['valid_until'])]
    now = datetime.now(timezone.utc)
    require(all(t.tzinfo is not None for t in (old_time, new_time, observed, until)) and
            old_time <= new_time <= now <= until and observed <= new_time,
            'refresh timestamp is unknown, regressed, future or outside existing freshness bounds')
    refreshed = copy.deepcopy(decision)
    refreshed['evidence'][ref]['sha256'] = hashlib.sha256(current).hexdigest()
    if 'profile_binding' in refreshed:
        profile = refreshed['profile_binding']
        recomputed = make_profile_binding(profile['profile'], profile['table'], profile['unit_id'], profile['pins'])
        require(recomputed == profile, 'profile selection changed; review required')
        refreshed['profile_binding'] = recomputed
    # Recompute the full candidate comparison and binding using current bytes;
    # never extend freshness, alter a user pin, or use a cached successful check.
    checked = check_routing(refreshed, args.decision.parent, record, args.record.parent, prelaunch=True)
    require(checked['ok'] and refreshed['selected'] == decision['selected'],
            'current-evidence selection or binding failed; review required: ' + json.dumps(checked['errors']))
    archive = args.result.with_name(args.result.name + '.reprepare')
    archive.mkdir(mode=0o700)  # Exclusive, durable one-refresh marker even on later failure.
    for name, data in (('inventory-before.json', before), ('inventory-current.json', current)):
        with (archive / name).open('xb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    atomic_state(archive / 'decision-before.json', decision)
    atomic_state(archive / 'decision.json', refreshed)
    digest = hashlib.sha256((archive / 'decision.json').read_bytes()).hexdigest()
    provenance = {'original_decision_sha256': original_hash, 'decision_sha256': digest,
                  'original_inventory_sha256': inventory['sha256'],
                  'current_inventory_sha256': refreshed['evidence'][ref]['sha256'],
                  'inventory_path': str(path), 'snapshot_path': str(args.reprepare_inventory.resolve()),
                  'archive': str(archive.resolve()), 'refresh_count': 1,
                  'not_started': True, 'host_invocations_before_refresh': 0,
                  'rejected_check': rejected, 'current_check': copy.deepcopy(checked)}
    atomic_state(archive / 'provenance.json', provenance)
    return refreshed, checked, digest, provenance


def _main(args):
    parser = argument_parser()
    executable = resolve_orca(args.orca)
    if not shutil.which(executable):
        print(json.dumps({'ok': False, 'error': 'Orca executable unavailable'}))
        return 1
    if args.retry_of and not args.task:
        parser.error('--retry-of requires --task')
    if args.task and not args.run:
        parser.error('--task requires an explicit --run')
    if args.task and any((args.terminal, args.reuse_dispatch, args.origin_receipt, args.task_title)):
        parser.error('existing Task cannot use new-task title or terminal reuse')
    decision, error, decision_hash = read_json_snapshot(args.decision)
    if error:
        print(json.dumps({'ok': False, 'errors': [error]}))
        return 2
    record, error, record_hash = read_json_snapshot(args.record)
    if error:
        print(json.dumps({'ok': False, 'errors': [error]}))
        return 2
    result = check_routing(decision, args.decision.parent, record, args.record.parent, prelaunch=True)
    original_decision_hash = decision_hash
    refresh = None
    if args.reprepare_inventory and not result['ok']:
        try:
            decision, result, decision_hash, refresh = reprepare_inventory(
                args, decision, record, result, decision_hash)
        except (ValueError, KeyError, TypeError, AttributeError, OSError) as exc:
            print(json.dumps({'ok': False, 'error': 'inventory reprepare denied', 'detail': str(exc)}))
            return 1
    result['receipt'].update(decision_sha256=decision_hash, record_sha256=record_hash)
    if refresh is not None:
        result['receipt']['inventory_reprepare'] = refresh
    if result['label'] != 'real':
        result['ok'] = False
        result['errors'].append({'path': '$.label', 'code': 'synthetic_launch',
                                 'message': 'Synthetic routing decisions cannot launch a worker'})
    binding = decision.get('binding', {}) if isinstance(decision, dict) else {}
    spec_hash = hashlib.sha256(args.spec.encode('utf-8')).hexdigest() if args.spec is not None else None
    if args.spec is not None and (not isinstance(binding, dict) or binding.get('spec_sha256') != spec_hash):
        result['ok'] = False
        result['errors'].append({'path': '$.binding.spec_sha256', 'code': 'spec_binding',
                                 'message': 'The exact worker specification must match the decision'})
    if args.spec is not None and (not isinstance(binding, dict) or binding.get('planned') is not True):
        result['ok'] = False
        result['errors'].append({'path': '$.binding.planned', 'code': 'planned_required',
                                 'message': 'worker-start --spec creates a new Task and requires a planned intent'})
    if not isinstance(binding, dict) or binding.get('parent_task') != args.parent:
        result['ok'] = False
        result['errors'].append({'path': '$.binding.parent_task', 'code': 'parent_binding',
                                 'message': 'Parent Task must match the checked decision'})
    result['receipt']['spec_sha256'] = spec_hash
    if (args.run is not None or 'run' in binding or 'run' in record) and (
            not args.run or binding.get('run') != args.run or record.get('run') != args.run):
        result['ok'] = False
        result['errors'].append({'path': '$.binding.run', 'code': 'run_binding', 'message': 'Run must match decision and current record'})
    selected = result['receipt']['selected']
    catalog_context = binding.get('host_catalog')
    if catalog_context is not None:
        # Existing-workspace opt-in only; legacy/reprepare/reuse behavior is untouched.
        try:
            from host_model_catalog import bound_catalog, require
            require(args.worktree == catalog_context['worktree'], 'launch worktree differs from catalog')
            require(not any((args.reprepare_inventory, args.task, args.retry_of, args.terminal,
                             args.reuse_dispatch, args.measurement_attempt, args.origin_receipt))
                    and record.get('measurement') is None, 'catalog mode requires fresh spec launch')
            require(not any(os.environ.get(k) for k in
                            ('ORCA_PAIRING_CODE', 'ORCA_REMOTE_PAIRING', 'ORCA_ENVIRONMENT', 'ORCA_DEV_REPO_ROOT')),
                    'catalog mode requires the same local installed host')
            require(Path(shutil.which(executable)).resolve().is_relative_to(
                    Path('/Applications/Orca.app/Contents/Resources')), 'catalog mode requires installed Orca CLI')
            catalog_before = bound_catalog(decision, args.decision.parent, resolve())
        except (ValueError, OSError, KeyError, TypeError) as exc:
            print(json.dumps({'ok': False, 'error': 'catalog binding denied', 'detail': str(exc)}))
            return 1
    if selected['route'] != 'codex':
        result['ok'] = False
        result['errors'].append({'path': '$.selected.route', 'code': 'unsupported_launch_route',
                                 'message': 'This launcher supports a new Codex worker only'})
    if not result['ok']:
        print(json.dumps(result))
        return 1
    # These checks run before every possible host subprocess. The host, tools and
    # billing are explicit caller declarations, not host-authenticated facts.
    if args.require_trusted_capacity:
        print(json.dumps({'ok': False, 'error': 'trusted capacity issuer and reservation unsupported'}))
        return 1
    manifest_path = args.resource_manifest
    try:
        manifest = resource_manifest_check(
            resolve(), root=manifest_path.absolute().parent if manifest_path else Path('.'),
            name=manifest_path.name if manifest_path else None,
            required=args.require_resource_manifest, service=selected['route'],
            host=args.declared_host, model=selected['model'], effort=selected['effort'],
            tools=args.declared_tool, billing=args.declared_billing, spend=args.declared_spend)
    except (ValueError, OSError, KeyError) as exc:
        print(json.dumps({'ok': False, 'error': 'resource declaration configuration invalid', 'detail': str(exc)}))
        return 1
    result['receipt']['resource_manifest'] = manifest
    if manifest['status'] == 'denied':
        print(json.dumps({'ok': False, 'resource_manifest': manifest}))
        return 1
    if args.task:
        current = next((item for item in record['tasks'] if item['id'] == args.task), None)
        if (binding.get('task') != args.task or current is None or
                (args.retry_of and (binding.get('planned') is not False or binding.get('attempt') != args.retry_of or
                 current['current_dispatch'] != args.retry_of or current['execution']['state'] != 'settled' or
                 (current['execution'].get('result') or {}).get('outcome') != 'failed')) or
                (not args.retry_of and (binding.get('planned') is not True or current['current_dispatch'] != 'planned:' + args.task))):
            print(json.dumps({'ok': False, 'error': 'Task or retry binding does not match current record'}))
            return 1
        try:
            probe = subprocess.run([executable, 'orchestration', 'task-list', '--run', args.run, '--from', args.sender, '--json'], check=False, capture_output=True, text=True, timeout=args.probe_timeout)
            envelope = json.loads(probe.stdout)
            listed = envelope['result']
            task = next(item for item in listed['tasks'] if item['id'] == args.task)
            spec_hash = hashlib.sha256(task['spec'].encode('utf-8')).hexdigest()
            valid = (probe.returncode == 0 and envelope.get('ok') is True and listed['runId'] == args.run and
                     task['run_id'] == args.run and task['parent_id'] == args.parent and
                     binding.get('spec_sha256') == spec_hash and task['status'] in (('failed',) if args.retry_of else ('pending', 'ready')))
            if args.retry_of:
                latest_probe = subprocess.run([executable, 'orchestration', 'dispatch-show', '--task', args.task, '--from', args.sender, '--json'], check=False, capture_output=True, text=True, timeout=args.probe_timeout)
                latest = json.loads(latest_probe.stdout)
                failed_probe = subprocess.run([executable, 'orchestration', 'worker-show', '--dispatch', args.retry_of, '--json'], check=False, capture_output=True, text=True, timeout=args.probe_timeout)
                failed = json.loads(failed_probe.stdout)
                dispatch = failed['result']['dispatch']
                valid = valid and latest_probe.returncode == 0 and latest.get('ok') is True and latest['result']['dispatch']['id'] == args.retry_of and failed_probe.returncode == 0 and failed.get('ok') is True and dispatch['id'] == args.retry_of and dispatch['taskId'] == args.task and dispatch['runId'] == args.run and dispatch['status'] == 'failed'
        except (KeyError, TypeError, ValueError, StopIteration, AttributeError, OSError, subprocess.SubprocessError):
            valid = False
        if not valid:
            print(json.dumps({'ok': False, 'error': 'Current host Task specification or failed Dispatch mismatch'}))
            return 1
        result['receipt']['spec_sha256'] = spec_hash
        result['receipt']['task_list'] = envelope
        if args.retry_of:
            result['receipt']['failed_dispatch'] = failed
            result['receipt']['latest_dispatch'] = latest
    reuse = any((args.terminal, args.reuse_dispatch, args.origin_receipt))
    if reuse:
        if not all((args.terminal, args.reuse_dispatch, args.origin_receipt)) or args.worktree in ('new-child', 'new-top-level'):
            print(json.dumps({'ok': False, 'error': 'reuse requires terminal, dispatch and original receipt'}))
            return 1
        origin, error, origin_hash = read_json_snapshot(args.origin_receipt)
        evidence = decision.get('reuse_evidence', {})
        source = decision.get('evidence', {}).get(evidence.get('unchanged_evidence'), {}) if isinstance(evidence, dict) else {}
        if error or not isinstance(origin, dict) or not isinstance(evidence, dict) or evidence.get('origin_sha256') != origin_hash:
            print(json.dumps({'ok': False, 'error': 'reuse origin receipt missing or hash mismatch'}))
            return 1
        try:
            envelope = json.loads(origin['stdout']) if isinstance(origin.get('stdout'), str) else origin
            original = envelope['result']
            original_effective = original['launch']['effective']
            original_incarnation = original['prompt']['processIncarnation']
            probe = subprocess.run([executable, 'orchestration', 'worker-show', '--dispatch', args.reuse_dispatch, '--json'], check=False, capture_output=True, text=True, timeout=args.probe_timeout)
            observed = json.loads(probe.stdout)
            live = observed['result']
            terminal = live['terminal']
            dispatch = live['dispatch']
            unchanged = source.get('reuse_binding', {})
            evidence_bytes = (args.decision.parent / source['file']).read_bytes()
            observed_at = datetime.fromisoformat(unchanged['observed_at'].replace('Z', '+00:00'))
            valid_until = datetime.fromisoformat(unchanged['valid_until'].replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            valid = (probe.returncode == 0 and observed.get('ok') is True and envelope.get('ok') is True and original.get('dispatchId') == args.reuse_dispatch
                     and any(effect.get('kind') == 'terminal' and effect.get('id') == args.terminal for effect in original['effects'])
                     and terminal.get('handle') == args.terminal and terminal.get('incarnationId') == original_incarnation
                     and dispatch.get('assigneeHandle') == args.terminal and dispatch.get('processIncarnation', '').endswith(':' + original_incarnation)
                     and live['observation'].get('status') == 'live' and live['observation'].get('exactWorker') is True
                     and live['projection']['liveness'].get('verdict') == 'live'
                     and original_effective.get('agent') == 'codex' and original_effective.get('model') == selected['model']
                     and original_effective.get('effort') == selected['effort'] and isinstance(source, dict)
                     and source.get('kind') == 'host' and isinstance(source.get('file'), str) and isinstance(source.get('sha256'), str)
                     and hashlib.sha256(evidence_bytes).hexdigest() == source['sha256'] and json.loads(evidence_bytes) == unchanged
                     and unchanged.get('dispatch') == args.reuse_dispatch and unchanged.get('terminal') == args.terminal
                     and unchanged.get('incarnation') == original_incarnation and unchanged.get('settings_unchanged') is True
                     and observed_at.tzinfo is not None and valid_until.tzinfo is not None and observed_at <= now <= valid_until)
        except (AttributeError, KeyError, TypeError, ValueError, OSError, subprocess.SubprocessError):
            valid = False
        if not valid:
            print(json.dumps({'ok': False, 'error': 'reuse source, process incarnation, settings or live observation mismatch'}))
            return 1
        result['receipt']['reuse'] = {'origin_sha256': origin_hash, 'worker_show': live,
                                      'limits': 'Original effective launch and current process observation; not current provider model readback.'}
        command = [executable, 'orchestration', 'worker-start', '--from', args.sender, '--spec', args.spec,
                   '--worktree', args.worktree, '--terminal', args.terminal, '--json']
    else:
        command = [executable, 'orchestration', 'worker-start', '--from', args.sender, '--task' if args.task else '--spec', args.task or args.spec,
                   '--worktree', args.worktree, '--agent', 'codex', '--model', selected['model'],
                   '--effort', selected['effort'], '--json']
    if args.run:
        command.extend(('--run', args.run))
    if args.retry_of:
        command.extend(('--retry-of', args.retry_of))
    if args.task_title:
        command.extend(('--task-title', args.task_title))
    if args.parent:
        command.extend(('--parent', args.parent))
    for flag, value in (('--name', args.name), ('--repo', args.repo), ('--base-branch', args.base_branch),
                        ('--setup', args.setup), ('--display-name', args.display_name)):
        if value is not None:
            if args.worktree not in ('new-child', 'new-top-level'):
                print(json.dumps({'ok': False, 'error': 'creation options require a new worktree'}))
                return 1
            command.extend((flag, value))
    if args.lifecycle is not None:
        args.lifecycle.check()
    if args.reprepare_inventory:
        # One final current-evidence validation, never another refresh. This mode
        # has made no host calls. Subsequent pending/unknown state never falls back.
        final = check_routing(decision, args.decision.parent, record, args.record.parent, prelaunch=True)
        _, decision_error, final_original_hash = read_json_snapshot(args.decision)
        _, record_error, final_record_hash = read_json_snapshot(args.record)
        if (not final['ok'] or final['receipt']['selected'] != selected or
                final['receipt'].get('price_selection') != result['receipt'].get('price_selection') or
                final['receipt']['configuration_sha256'] != result['receipt']['configuration_sha256'] or
                decision_error or record_error or final_original_hash != original_decision_hash or
                final_record_hash != record_hash):
            print(json.dumps({'ok': False, 'error': 'pre-host evidence changed after preparation; no second refresh',
                              'check': final}))
            return 1
    if catalog_context is not None:
        try:
            from host_model_catalog import load as load_catalog, compare, require
            refreshed_path = args.result.with_name(args.result.name + '.catalog-refresh')
            probe = subprocess.run(['node', str(Path(__file__).with_name('host_model_catalog.cjs')),
                                    str(refreshed_path), args.worktree],
                                   check=False, capture_output=True, text=True, timeout=200)
            require(probe.returncode == 0, 'host catalog refresh failed')
            manifest_hash = hashlib.sha256((refreshed_path / 'manifest.json').read_bytes()).hexdigest()
            fresh = load_catalog(refreshed_path, manifest_hash, worktree=args.worktree,
                                 model=selected['model'], effort=selected['effort'])
            compare(catalog_before, fresh)
            # Refresh is metadata-only. Never replace a decision, broaden candidates,
            # revise auth/billing declarations, or silently refresh a changed context.
            final = check_routing(decision, args.decision.parent, record, args.record.parent, prelaunch=True)
            require(final['ok'] and final['receipt']['configuration_sha256'] ==
                    result['receipt']['configuration_sha256'] and
                    final['receipt']['selected'] == selected and
                    final['receipt'].get('price_selection') == result['receipt'].get('price_selection'),
                    'prelaunch context or selection changed')
            require(read_json_snapshot(args.decision)[2] == original_decision_hash and
                    read_json_snapshot(args.record)[2] == record_hash, 'decision/record changed')
            bound_catalog(decision, args.decision.parent, resolve())
            result['receipt']['host_catalog'] = {
                'prepared_manifest_sha256': decision['evidence'][decision['price_selection']['inventory_evidence']]['sha256'],
                'refreshed_manifest_sha256': manifest_hash, 'refreshed_directory': str(refreshed_path),
                'runtime_id': fresh['runtime_id'], 'worktree': fresh['worktree']}
        except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as exc:
            print(json.dumps({'ok': False, 'error': 'catalog prelaunch denied', 'detail': str(exc)}))
            return 1
    result['receipt']['launch_argv'] = command
    with args.receipt.open('x', encoding='utf-8') as receipt:
        json.dump(result, receipt, ensure_ascii=False, indent=2)
        receipt.write('\n')
        receipt.flush()
        os.fsync(receipt.fileno())
    if args.lifecycle is not None:
        args.lifecycle.pending(command, args.receipt)
    atomic_state(args.result, {'launch_state_version': 1, 'launch_state': 'invocation_pending',
                               'decision_sha256': decision_hash})
    try:
        host = subprocess.run(command, check=False, capture_output=True, text=True, timeout=args.start_timeout)
    except subprocess.TimeoutExpired as exc:
        partial = {'format': 'company-launch-timeout/v1',
                   'stdout': timeout_stream_metadata(exc.output),
                   'stderr': timeout_stream_metadata(exc.stderr)}
        state = {'launch_state_version': 1, 'launch_state': 'unknown',
                 'decision_sha256': decision_hash, 'error_code': 'host_start_timeout',
                 'error': 'host start timed out; outcome unknown', 'partial_output': partial,
                 'diagnostic_reference': 'self'}
        diagnostic = 'available'
        try:
            write_timeout_state(args.result, state)
        except (OSError, ValueError):
            # No raw fallback and no repeated invocation. Durable pending is unknown,
            # never evidence of no start or permission to refresh/retry.
            diagnostic = 'unavailable'
        print(json.dumps({'ok': False, 'error': 'host outcome unknown; reconciliation required',
                          'launch_state': 'unknown', 'error_code': 'host_start_timeout',
                          'diagnostic': diagnostic}))
        return 1
    except (OSError, subprocess.SubprocessError) as exc:
        atomic_state(args.result, {'launch_state_version': 1, 'launch_state': 'unknown',
                                   'decision_sha256': decision_hash, 'error': str(exc)})
        print(json.dumps({'ok': False, 'error': 'host outcome unknown; reconciliation required'}))
        return 1
    status, reason = ('failed', 'host returned nonzero') if host.returncode else ('unverified', 'host result lacks required readback')
    try:
        envelope = json.loads(host.stdout)
        payload = envelope['result']
        if host.returncode == 0 and envelope.get('ok') is False:
            status, reason = 'failed', 'host returned an unsuccessful result'
        elif host.returncode == 0 and envelope.get('ok') is True and isinstance(payload.get('taskId'), str) and payload['taskId'] and isinstance(payload.get('dispatchId'), str) and payload['dispatchId']:
            if args.task and (payload['taskId'] != args.task or payload['dispatchId'] == args.retry_of):
                status, reason = 'failed', 'host Task or Dispatch differs from checked identity'
            elif args.run and payload.get('runId') != args.run:
                status, reason = ('unverified', 'host Run identity missing') if payload.get('runId') is None else ('failed', 'host Run identity differs')
            elif reuse:
                effects = payload.get('effects')
                if isinstance(effects, list) and any(isinstance(item, dict) and item.get('kind') == 'terminal' and item.get('id') == args.terminal for item in effects):
                    status, reason = 'observed', 'host IDs and reused terminal observed; model and effort remain prior evidence'
            else:
                effective = payload.get('launch', {}).get('effective')
                if isinstance(effective, dict) and all(effective.get(field) is not None for field in ('agent', 'model', 'effort')):
                    if effective.get('agent') == 'codex' and effective.get('model') == selected['model'] and effective.get('effort') == selected['effort']:
                        status, reason = 'observed', 'host IDs and effective launch settings observed'
                    else:
                        status, reason = 'failed', 'host effective launch settings differ from checked selection'
    except (ValueError, KeyError, TypeError, AttributeError):
        pass
    atomic_state(args.result, {'launch_state_version': 1, 'launch_state': 'observed' if status == 'observed' else 'unknown',
               'decision_sha256': decision_hash, 'prelaunch_receipt_sha256': hashlib.sha256(args.receipt.read_bytes()).hexdigest(),
               'exit_code': host.returncode, 'readback_status': status, 'readback_reason': reason,
               'stdout': host.stdout, 'stderr': host.stderr})
    if status == 'observed' and args.lifecycle is not None:
        args.lifecycle.bind()
    sys.stdout.write(host.stdout)
    sys.stderr.write(host.stderr)
    if status != 'observed':
        sys.stderr.write('Routing launch readback ' + status + ': ' + reason + '; inspect the preserved host receipt before any recovery.\n')
    return 0 if status == 'observed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
