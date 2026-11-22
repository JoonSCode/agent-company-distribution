#!/usr/bin/env python3
"""Run a checked new Orca worker-start; this is not a server enforcement boundary."""
import argparse
import copy
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import fcntl
import shutil
import stat
import secrets
import sqlite3
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from time import monotonic_ns

# Select Python's normal cache prefix before importing Company modules.
# Restrict this to the CLI process; callers importing a module are unchanged.
if __name__ == "__main__":
    import os as _os
    import sys as _sys
    _sys.pycache_prefix = _os.path.join(_os.path.abspath(_os.path.expanduser("~")), ".cache", "agent-company", "python")

from record_check import (CHECKED_AGENTS, INVENTORY_HASH_CHANGED, check_routing,
                          invalid_constant, read_json_snapshot, unique_object)
from route_select import load_table
from orca_contract import resolve_orca
from company_config import resolve, resource_manifest_check


from atomic_persistence import atomic_state


class LaunchTiming:
    """Opt-in observations from one launcher invocation, stored in its existing result."""

    def __init__(self, args):
        self.origin = monotonic_ns()
        self.marks = {}
        self.mark('entry')
        self.epoch = secrets.token_hex(16)
        self.binding = {
            key + '_sha256': hashlib.sha256(value.encode('utf-8', 'surrogatepass')).hexdigest()
            if value is not None else None
            for key, value in (('run', args.run), ('requested_task', args.task), ('retry_of', args.retry_of))
        }
        self.decision_sha256 = None
        self.receipt_sha256 = None

    def mark(self, name):
        elapsed_ns = monotonic_ns() - self.origin
        self.marks[name] = [datetime.now(timezone.utc).isoformat(), elapsed_ns]

    def add(self, state, reason):
        return {**state, 'timing': {
            'version': 1, 'epoch': self.epoch, **self.binding,
            'decision_sha256': self.decision_sha256, 'receipt_sha256': self.receipt_sha256,
            'reason': reason, 'marks': dict(self.marks),
        }}


def logical_attempt(binding):
    # The enrollment scopes this identity to one Run. The planned token or
    # failed Dispatch distinguishes attempts for the same Task. Fresh evidence,
    # selection, revision and output names cannot mint another attempt.
    return {key: binding.get(key) for key in ('task', 'attempt')} if isinstance(binding, dict) else {}


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


def storage_launch_guard(args, reserve=False, capability=None):
    """Exact enrolled producer + retained output contract, before every allocation.

    This is the Company checked entry only, never a raw Orca/slash interceptor.
    Still-live outputs are reserved, never hashed as finished disposable bytes.
    """
    import native_storage as storage
    import run_completion as lifecycle
    from native_operations import require, Blocked, regular, sha, valid_hash, decode
    require(args.enrollment_request is not None, 'explicit storage enrollment request required', Blocked)
    reference = {'path': str(args.enrollment_request.absolute()), 'sha256': valid_hash(args.expect_enrollment_sha256)}
    require(sha(regular(args.enrollment_request)) == reference['sha256'], 'enrollment request pin changed', Blocked)
    enrollment, _, manifest, current = storage.bound_enrollment(args.enrollment_request)
    root = Path(enrollment['run'])
    require(args.record.absolute() == root / enrollment['record'], 'checked record differs from enrollment', Blocked)
    record = decode(regular(args.record))
    require(isinstance(record, dict) and isinstance(record.get('goal'), dict), 'checked record goal object required', Blocked)
    require(record['goal'].get('status') != 'succeeded' and 'artifact_retention' not in record, 'accepted canonical record cannot launch more work', Blocked)
    if args.prepared_bundle is not None:
        import routing_prepare
        checked = routing_prepare.check_bundle(args.prepared_bundle)
        bundle = decode(regular(args.prepared_bundle / 'manifest.json'))
        require(bundle['format'] == routing_prepare.FORMAT and checked['ok'], 'prepared bundle stale/blocked', Blocked)
        require(bundle['enrollment'] == reference and bundle['canonical_record'] == {'path': str(args.record.absolute()), 'sha256': sha(regular(args.record))}, 'prepared canonical enrollment differs', Blocked)
        require(args.decision.absolute() == args.prepared_bundle.absolute() / 'decision.json' and args.spec is not None and args.spec.encode('utf-8') == regular(args.prepared_bundle / 'spec.txt'), 'prepared decision/spec differs', Blocked)
    enrolled_run_id = enrollment['run_id']
    require(record['goal'].get('id') == enrolled_run_id and record['goal'].get('current_owner') == enrollment['owner'], 'checked goal/owner differs from enrollment', Blocked)
    require(record.get('run', enrolled_run_id) == enrolled_run_id, 'record.run differs from enrollment', Blocked)
    require(args.run is None or args.run == enrolled_run_id, '--run differs from enrollment', Blocked)
    if capability is not None:
        capability.verify()
        require(capability.root == root, 'launch capability root differs', Blocked)
    legacy_lock = args.result.absolute().with_name(args.result.name + '.lock')
    require(not os.path.lexists(legacy_lock), 'legacy result lock requires owner recovery', Blocked)
    paths = [args.receipt.absolute(), args.result.absolute()]
    if args.reprepare_inventory:
        directory = args.result.absolute().with_name(args.result.name + '.reprepare')
        paths += [directory / name for name in lifecycle.LAUNCH_OPTIONAL_OUTPUTS['.reprepare']]
    if args.measurement_attempt:
        ledger = root / record.get('measurement', {}).get('ledger', '')
        require(ledger.is_relative_to(root) and ledger != root, 'measurement ledger outside enrolled Run', Blocked)
        require('measurement-v2' in enrollment['consumers'], 'measurement consumer missing from enrollment', Blocked)
        # The measurement producer reserves its exact next sequence before its
        # own writer; speculative launcher reservations would claim its origin.
    try:
        decision = decode(regular(args.decision))
    except FileNotFoundError:
        # Enrollment still precedes all writes. Missing decision is an ordinary
        # downstream prelaunch denial, not authority to probe or start a host.
        decision = {}
    binding = decision.get('binding', {})
    require(binding.get('run', enrolled_run_id) == enrolled_run_id, 'decision.binding.run differs from enrollment', Blocked)
    if binding.get('host_catalog') is not None:
        directory = args.result.absolute().with_name(args.result.name + '.catalog-refresh')
        paths += [directory / name for name in lifecycle.LAUNCH_OPTIONAL_OUTPUTS['.catalog-refresh']]
    # Refuse an ambiguous/observed attempt before reserving renamed outputs.
    # A malformed local packet still gets its pure pre-start diagnostic; this
    # branch never probes a host, refreshes an inventory, or grants another start.
    if reserve:
        require(capability is not None, 'reservation requires held Run capability', Blocked)
        capability.verify()
        result_ref = args.result.absolute().relative_to(root).as_posix()
        if args.reprepare_inventory:
            require(all(path.relative_to(root).as_posix() not in manifest.get('creation_contract', {})
                        for path in paths), 'reprepare requires unused output reservations', Blocked)
        attempt_binding = logical_attempt(binding)
        for prior_ref, prior_contract in manifest.get('launch_contract', {}).items():
            if prior_ref != result_ref and logical_attempt(prior_contract['attempt_binding']) == attempt_binding:
                prior = lifecycle.decode(lifecycle.read_file(capability.fd, prior_ref)[0])
                if prior.get('launch_state') != 'not_started' or os.path.lexists(root / prior_contract['receipt']):
                    checked = check_routing(decision, args.decision.parent, record, args.record.parent, prelaunch=True)
                    require(checked['ok'], 'prelaunch validation denied: ' + json.dumps(checked), Blocked)
                    raise Blocked('attempt has another unresolved or observed result; no renamed-result retry')
    rows = []
    for path in paths:
        storage.lexical(str(path))
        require(path.is_relative_to(root), 'checked output outside enrolled Run', Blocked)
        ref = path.relative_to(root).as_posix()
        lifecycle.parts(ref)
        # Check every currently existing parent without resolving namespace links.
        parent = path.parent
        while parent != root:
            if os.path.lexists(parent):
                info = parent.lstat()
                require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and not info.st_mode & 0o022, 'unsafe output parent', Blocked)
            parent = parent.parent
        declaration = manifest.get('creation_contract', {}).get(ref)
        if declaration is not None:
            require(declaration['class'] == 'preserve' and declaration['owner'] == enrollment['owner'] and declaration['origin'] == 'routing_launch.py' and declaration['state'] == 'reserved', 'launch output declaration is not live retained evidence', Blocked)
        else:
            require(reserve and not os.path.lexists(path), 'output must be reserved before allocation', Blocked)
            rows.append(dict(path=ref, **{'class':'preserve'}, owner=enrollment['owner'], consumers=[], reason='checked_launch_evidence', origin='routing_launch.py', regeneration=None, next_use_or_recheck='freeze only after launch/measurement settlement'))
        if os.path.lexists(path): regular(path)
    if rows:
        storage.classify_value(dict(enrollment=reference, expect_manifest_sha256=current, phase='reserve', artifacts=rows), args.enrollment_request.parent, reference, capability)
    if reserve:
        require(capability is not None, 'reservation requires held Run capability', Blocked)
        capability.verify()
        raw = lifecycle.read_file(capability.fd, lifecycle.MANIFEST, True)[0]
        manifest = lifecycle.decode(raw)
        launches = manifest.setdefault('launch_contract', {})
        result_ref = args.result.absolute().relative_to(root).as_posix()
        declaration = dict(receipt=args.receipt.absolute().relative_to(root).as_posix(),
                           attempt_binding=attempt_binding,
                           optional=[p.relative_to(root).as_posix() for p in paths[2:]])
        if result_ref in launches and launches[result_ref] != declaration:
            prior = lifecycle.decode(lifecycle.read_file(capability.fd, result_ref)[0])
            require(prior.get('launch_state') == 'not_started' and not os.path.lexists(root / launches[result_ref]['receipt']),
                    'launch result/receipt contract changed after possible start', Blocked)
        if launches.get(result_ref) != declaration:
            launches[result_ref] = declaration
            lifecycle.write_metadata(capability.fd, lifecycle.MANIFEST, manifest)
            capability.verify()
    return reference


def full_launch_readback(executable, payload, selected, timeout, *, agent='codex', runtime_id=None,
                         reused_process=None):
    """Read the host's exact Dispatch and effective settings or incarnation."""
    from run_completion import start_incarnation_matches

    result = {'status': 'unverified', 'reason': 'full host readback unavailable',
              'exit_code': None, 'stdout': '', 'stderr': ''}
    if not all(isinstance(payload.get(k), str) and payload[k] for k in ('runId', 'taskId', 'dispatchId')):
        return result
    try:
        host = subprocess.run([executable, 'orchestration', 'worker-show', '--dispatch',
                               payload['dispatchId'], '--full', '--json'],
                              check=False, capture_output=True, text=True, timeout=timeout)
        result.update(exit_code=host.returncode, stdout=host.stdout, stderr=host.stderr)
        data = json.loads(host.stdout, object_pairs_hook=unique_object, parse_constant=invalid_constant)
        dispatch = data['result']['dispatch']
        worker = data['result']['worker']
        if (host.returncode != 0 or data.get('ok') is not True or
                (runtime_id is not None and data.get('_meta', {}).get('runtimeId') != runtime_id) or
                dispatch.get('id') != payload['dispatchId'] or
                dispatch.get('taskId') != payload['taskId'] or
                dispatch.get('runId') != payload['runId'] or
                worker.get('dispatchId') != payload['dispatchId'] or
                not start_incarnation_matches(payload, dispatch, data['result'].get('terminal'),
                                              same_runtime=runtime_id is not None) or
                (payload.get('terminal') is not None and
                 (dispatch.get('assigneeHandle') != payload['terminal'] or
                  data['result'].get('terminal', {}).get('handle') != payload['terminal']))):
            return result
        effective = worker['startOptions']['launch']['effective']
        if reused_process is not None:
            handle, pty_id, incarnation = reused_process
            terminal = data['result']['terminal']
            if (dispatch.get('assigneeHandle') != handle or worker.get('agentTerminalHandle') != handle or
                    worker.get('runtimeEpoch') not in (None, runtime_id) or
                    data['result'].get('observation', {}).get('exactWorker') is not True or
                    terminal.get('handle') != handle or terminal.get('ptyId') != pty_id or
                    terminal.get('incarnationId') != incarnation or
                    dispatch.get('processIncarnation') != f'{pty_id}:{incarnation}' or
                    not any(effect.get('kind') == 'terminal' and effect.get('action') == 'reused' and
                            effect.get('id') == handle for effect in worker['effects'])):
                return result
            if effective is not None and not isinstance(effective, dict):
                return result
            effective = effective or {}
            expected = {'agent': agent, 'model': selected['model'], 'effort': selected['effort']}
            if any(effective.get(key) is not None and effective[key] != value for key, value in expected.items()):
                result.update(status='failed', reason='full reuse readback contradicts the checked settings')
            elif any(effective.get(key) is not None for key in ('model', 'effort')):
                result['reason'] = 'full reuse readback contains settings without a current observation contract'
            else:
                result.update(status='observed', reason='same process observed by full reuse readback; current model and effort unknown')
            return result
        if not isinstance(effective, dict) or any(effective.get(k) is None for k in ('agent', 'model', 'effort')):
            return result
        if (effective['agent'], effective['model'], effective['effort']) != (agent, selected['model'], selected['effort']):
            result.update(status='failed', reason='host effective launch settings differ from checked selection')
        else:
            result.update(status='observed', reason='host IDs and effective launch settings observed by full readback')
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError, AttributeError) as exc:
        result['error'] = str(exc)
    return result


def main(argv=None):
    # Parse all arguments before creating the lock or result (including --help).
    args = argument_parser().parse_args(argv)
    timing = args.timing = LaunchTiming(args) if args.record_timing else None
    if args.spec_file is not None:
        from native_operations import regular
        try:
            args.spec = regular(args.spec_file).decode('utf-8')
            if not args.spec or '\0' in args.spec:
                raise ValueError('spec requires nonempty UTF-8 without NUL')
        except (OSError, ValueError) as exc:
            print(json.dumps({'ok': False, 'error': 'spec file blocked', 'detail': str(exc)}))
            return 1
    # Validate the pinned enrollment before opening its existing lifecycle lock.
    try:
        import native_storage as storage
        from native_operations import pinned
        if args.enrollment_request is None: raise ValueError('explicit storage enrollment request required')
        reference = dict(path=str(args.enrollment_request.absolute()), sha256=args.expect_enrollment_sha256)
        ep, _ = pinned(reference, Path.cwd())
        enrollment, _, _, _ = storage.bound_enrollment(ep)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'ok': False, 'error': 'storage enrollment blocked', 'detail': str(exc)}))
        return 1
    # One stable Run capability covers reservation, pending, host and readback.
    path = args.result
    try:
        import run_completion as rc
        if timing is not None:
            timing.mark('lock_enter')
        with rc.lifecycle_lock(Path(enrollment['sejong_home']), Path(enrollment['run'])) as capability:
            if timing is not None:
                timing.mark('lock_acquired')
            args.storage_capability = capability
            if (os.path.lexists(path.with_name(path.name + '.reprepare')) or
                    (args.reprepare_inventory and (os.path.lexists(path) or os.path.lexists(args.receipt)))):
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
            storage_launch_guard(args, reserve=True, capability=capability)
            if path.exists():
                try:
                    prior = json.loads(path.read_text(encoding='utf-8'))
                    if prior.get('launch_state_version') != 1 or prior.get('launch_state') != 'not_started':
                        raise ValueError('unresolved or completed')
                except (OSError, ValueError, AttributeError):
                    print(json.dumps({'ok': False, 'error': 'result already exists; reconciliation required'}))
                    return 1
            initial = {'launch_state_version': 1, 'launch_state': 'not_started'}
            args.initial_launch_state = timing.add(initial, 'preparation_incomplete') if timing else initial
            atomic_state(path, args.initial_launch_state, capability)
            from measurement_lifecycle import launch_guard
            try:
                with launch_guard(args, capability) as lifecycle:
                    args.lifecycle = lifecycle
                    return _main(args)
            except (ValueError, KeyError, TypeError, AttributeError, sqlite3.Error, subprocess.SubprocessError) as exc:
                print(json.dumps({'ok': False, 'error': 'measurement lifecycle blocked', 'detail': str(exc)}))
                return 1
            finally:
                if timing is not None and 'prepared' not in timing.marks:
                    timing.mark('preparation_stopped')
                    try:
                        atomic_state(path, timing.add(args.initial_launch_state, 'preparation_stopped'), capability)
                    except (OSError, ValueError):
                        # The incomplete observation is sufficient if enrichment cannot be persisted.
                        pass
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'ok': False, 'error': 'result persistence failed', 'detail': str(exc)}))
        return 1


def argument_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--orca', help='single Orca executable (not a shell command)')
    parser.add_argument('--enrollment-request', type=Path, help='exact storage enrollment request; required before supported writes')
    parser.add_argument('--expect-enrollment-sha256')
    parser.add_argument('--prepared-bundle', type=Path, help='exact retained v2 review bundle; canonical record remains live')
    parser.add_argument('--measurement-attempt', help='v2 prepared attempt ID; no fresh retry on unknown start')
    parser.add_argument('--decision', required=True, type=Path)
    parser.add_argument('--reprepare-inventory', type=Path,
                        help='explicit one-time pre-host reprepare using a full hash-matching preparation snapshot')
    parser.add_argument('--record', required=True, type=Path)
    parser.add_argument('--receipt', required=True, type=Path)
    parser.add_argument('--result', required=True, type=Path)
    parser.add_argument('--record-timing', action='store_true',
                        help='include private launcher timing in the retained result')
    parser.add_argument('--from', dest='sender', required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--spec')
    mode.add_argument('--spec-file', type=Path, help='read exact UTF-8 spec bytes before launch checks')
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

    def same_json(a, b):
        if type(a) is not type(b):
            return False
        if isinstance(a, dict):
            return a.keys() == b.keys() and all(same_json(a[key], b[key]) for key in a)
        if isinstance(a, list):
            return len(a) == len(b) and all(same_json(x, y) for x, y in zip(a, b))
        return a == b

    from host_model_catalog import inventory_reference
    ref = inventory_reference(decision)
    inventory = decision['evidence'][ref]
    pin_error = ('$.evidence.' + ref, 'hash_mismatch')
    drift_errors = {(path, INVENTORY_HASH_CHANGED) for path in ('$.selected_runtime', '$.price_selection')}
    errors = {(e['path'], e['code']) for e in rejected['errors']}
    require(not rejected['ok'] and decision['label'] == 'real' and
            decision['selected']['route'] == 'codex' and inventory.get('source') != 'orca_model_catalog' and
            pin_error in errors and bool(errors & drift_errors) and errors <= {pin_error, *drift_errors},
            'reprepare is limited to an inventory-only hash denial')
    require(json.loads(args.result.read_bytes()) == args.initial_launch_state,
            'reprepare requires authoritative local not_started before any host invocation')
    path = (args.decision.parent / inventory['file']).resolve()
    require(path == (canonical_home() / 'models_cache.json').resolve(), 'inventory is not canonical')
    before = args.reprepare_inventory.read_bytes()
    require(hashlib.sha256(before).hexdigest() == inventory['sha256'], 'missing hash-matching full inventory snapshot')
    current = path.read_bytes()
    old = json.loads(before, object_pairs_hook=unique_object, parse_constant=invalid_constant, parse_float=Decimal)
    new = json.loads(current, object_pairs_hook=unique_object, parse_constant=invalid_constant, parse_float=Decimal)
    require(isinstance(old, dict) and isinstance(new, dict), 'inventory must be an object')
    require(isinstance(new.get('models'), list) and bool(new['models']), 'missing or partial models inventory')
    # No model/capability/price/availability field is projected out. Unknown
    # envelope fields, client identity/version and etag changes need review too.
    require(same_json({k: v for k, v in old.items() if k != 'fetched_at'},
                      {k: v for k, v in new.items() if k != 'fetched_at'}),
            'inventory content changed; material selection review required')
    old_time, new_time, observed, until = [datetime.fromisoformat(value.replace('Z', '+00:00'))
        for value in (old['fetched_at'], new['fetched_at'], inventory['observed_at'], inventory['valid_until'])]
    now = datetime.now(timezone.utc)
    require(all(t.tzinfo is not None for t in (old_time, new_time, observed, until)) and
            old_time < new_time <= now <= until and observed <= new_time,
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
    decision_before = args.decision.read_bytes()
    require(hashlib.sha256(decision_before).hexdigest() == original_hash, 'original decision changed during reprepare')
    archive = args.result.with_name(args.result.name + '.reprepare')
    archive.mkdir(mode=0o700)  # Exclusive, durable one-refresh marker even on later failure.
    for name, data in (('inventory-before.json', before), ('inventory-current.json', current),
                       ('decision-before.json', decision_before)):
        handle = os.open(archive / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(handle, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
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
    timing = args.timing
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
    if timing is not None:
        timing.decision_sha256 = decision_hash
    record, error, record_hash = read_json_snapshot(args.record)
    if error:
        print(json.dumps({'ok': False, 'errors': [error]}))
        return 2
    result = check_routing(decision, args.decision.parent, record, args.record.parent, prelaunch=True)
    original_decision_hash = decision_hash
    refresh = None
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
    if (args.run is not None or 'run' in binding or 'run' in record) and (
            not args.run or binding.get('run') != args.run or record.get('run') != args.run):
        result['ok'] = False
        result['errors'].append({'path': '$.binding.run', 'code': 'run_binding', 'message': 'Run must match decision and current record'})
    if args.reprepare_inventory and not result['ok']:
        try:
            decision, result, decision_hash, refresh = reprepare_inventory(
                args, decision, record, result, decision_hash)
        except (ValueError, KeyError, TypeError, AttributeError, OSError, ArithmeticError, RecursionError) as exc:
            print(json.dumps({'ok': False, 'error': 'inventory reprepare denied', 'detail': str(exc),
                              'rejected_check': result}))
            return 1
    result['receipt'].update(decision_sha256=decision_hash, record_sha256=record_hash, spec_sha256=spec_hash,
                             requested_run=args.run)
    if timing is not None:
        timing.decision_sha256 = decision_hash
    profile_binding = decision.get('profile_binding')
    result['receipt']['profile_unit'] = profile_binding.get('unit_id') if isinstance(profile_binding, dict) else None
    if refresh is not None:
        result['receipt']['inventory_reprepare'] = refresh
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
    agent = CHECKED_AGENTS.get(selected['route'])
    if agent is None:
        result['ok'] = False
        result['errors'].append({'path': '$.selected.route', 'code': 'unsupported_launch_route',
                                 'message': 'Checked launch supports Codex and subscription Antigravity workers'})
    runtime_id = None
    if result['ok'] and agent == 'antigravity':
        runtime = decision.get('selected_runtime') or {}
        efforts = load_table()[0]['worker_route_efforts']['agy'].get(selected['model'], [])
        if (runtime.get('billing') != 'subscription' or args.declared_billing not in (None, 'subscription')
                or selected['effort'] not in efforts
                or args.terminal or args.origin_receipt or args.reuse_dispatch or args.reprepare_inventory
                or catalog_context is not None or args.measurement_attempt or record.get('measurement') is not None):
            result['ok'] = False
            result['errors'].append({'path': '$.selected_runtime', 'code': 'unsupported_agy_launch',
                                     'message': 'Require an exact supported AGY model/effort and subscription runtime '
                                                'evidence for a new worker; Codex-only bridges cannot be used.'})
        else:
            runtime_id = decision['evidence'][runtime['runtime_evidence']]['unlisted_runtime']['host']
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
            required=args.require_resource_manifest, service=agent,
            host=args.declared_host, model=selected['model'], effort=selected['effort'],
            tools=args.declared_tool, billing=args.declared_billing, spend=args.declared_spend)
    except (ValueError, OSError, KeyError) as exc:
        print(json.dumps({'ok': False, 'error': 'resource declaration configuration invalid', 'detail': str(exc)}))
        return 1
    result['receipt']['resource_manifest'] = manifest
    if manifest['status'] == 'denied':
        print(json.dumps({'ok': False, 'resource_manifest': manifest}))
        return 1
    if runtime_id is not None:
        if ((args.declared_host is not None and args.declared_host != runtime_id) or
                os.environ.get('ORCA_ENVIRONMENT') not in (None, '', 'local') or
                any(os.environ.get(k) for k in ('ORCA_PAIRING_CODE', 'ORCA_REMOTE_PAIRING', 'ORCA_DEV_REPO_ROOT'))):
            print(json.dumps({'ok': False, 'error': 'AGY evidence requires the same local Orca runtime'}))
            return 1
        try:
            probe = subprocess.run([executable, 'status', '--json'], check=False, capture_output=True,
                                   text=True, timeout=args.probe_timeout)
            status = json.loads(probe.stdout)
            live = status['result']['runtime']
            if (probe.returncode or status.get('ok') is not True or status['result']['target']['kind'] != 'local'
                    or live.get('state') != 'ready' or live.get('reachable') is not True or live['runtimeId'] != runtime_id
                    or status['_meta']['runtimeId'] != runtime_id):
                raise ValueError('local runtime differs from the pinned AGY evidence')
        except (OSError, subprocess.SubprocessError, ValueError, KeyError, AttributeError, TypeError) as exc:
            print(json.dumps({'ok': False, 'error': 'AGY host identity unavailable', 'detail': str(exc)}))
            return 1
        result['receipt']['agy_runtime_id'] = runtime_id
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
            probe = subprocess.run([executable, 'orchestration', 'task-list', '--run', args.run, '--from', args.sender, '--full', '--json'], check=False, capture_output=True, text=True, timeout=args.probe_timeout)
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
                failed_probe = subprocess.run([executable, 'orchestration', 'worker-show', '--dispatch', args.retry_of, '--full', '--json'], check=False, capture_output=True, text=True, timeout=args.probe_timeout)
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
        reuse_probe = {'exit_code': None, 'stdout': '', 'stderr': ''}
        try:
            if isinstance(origin.get('stdout'), str) and origin.get('launch_state') != 'observed':
                raise ValueError('original checked result has no observed launch')
            envelope = (json.loads(origin['stdout'], object_pairs_hook=unique_object, parse_constant=invalid_constant)
                        if isinstance(origin.get('stdout'), str) else origin)
            original = envelope['result']
            original_task_id = original['taskId']
            original_run = original['runId']
            reuse_runtime = envelope['_meta']['runtimeId']
            original_effective = original['launch']['effective']
            original_incarnation = original['prompt']['processIncarnation']
            if (not all(isinstance(value, str) and value.strip() for value in
                        (original_task_id, original_run, reuse_runtime, original_incarnation)) or
                    original_run != record['goal']['id']):
                raise ValueError('missing original reuse identity or different requested Run')
            probe = subprocess.run([executable, 'orchestration', 'worker-show', '--dispatch', args.reuse_dispatch, '--full', '--json'], check=False, capture_output=True, text=True, timeout=args.probe_timeout)
            reuse_probe.update(exit_code=probe.returncode, stdout=probe.stdout, stderr=probe.stderr)
            observed = json.loads(probe.stdout, object_pairs_hook=unique_object, parse_constant=invalid_constant)
            live = observed['result']
            terminal = live['terminal']
            dispatch = live['dispatch']
            prior_worker = live['worker']
            reuse_pty = terminal['ptyId']
            prior_effective = (prior_worker.get('startOptions', {}).get('launch') or {}).get('effective')
            unchanged = source.get('reuse_binding', {})
            evidence_bytes = (args.decision.parent / source['file']).read_bytes()
            observed_at = datetime.fromisoformat(unchanged['observed_at'].replace('Z', '+00:00'))
            valid_until = datetime.fromisoformat(unchanged['valid_until'].replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            valid = (probe.returncode == 0 and observed.get('ok') is True and envelope.get('ok') is True and original.get('dispatchId') == args.reuse_dispatch
                     and observed.get('_meta', {}).get('runtimeId') == reuse_runtime
                     and any(effect.get('kind') == 'terminal' and effect.get('id') == args.terminal for effect in original['effects'])
                     and terminal.get('handle') == args.terminal and terminal.get('incarnationId') == original_incarnation
                     and isinstance(reuse_pty, str) and bool(reuse_pty)
                     and dispatch.get('id') == args.reuse_dispatch
                     and prior_worker.get('dispatchId') == args.reuse_dispatch and prior_worker.get('agentTerminalHandle') == args.terminal
                     and prior_worker.get('runtimeEpoch') in (None, reuse_runtime)
                     and dispatch.get('runId') == original_run and dispatch.get('taskId') == original_task_id
                     and dispatch.get('assigneeHandle') == args.terminal
                     and dispatch.get('processIncarnation') == f'{reuse_pty}:{original_incarnation}'
                     and live['observation'].get('status') == 'live' and live['observation'].get('exactWorker') is True
                     and live['projection']['liveness'].get('verdict') == 'live'
                     and original_effective.get('agent') == 'codex' and original_effective.get('model') == selected['model']
                     and original_effective.get('effort') == selected['effort']
                     and (prior_effective is None or (isinstance(prior_effective, dict) and
                          all(prior_effective.get(key) in (None, original_effective[key]) for key in ('agent', 'model', 'effort'))))
                     and isinstance(source, dict)
                     and source.get('kind') == 'host' and isinstance(source.get('file'), str) and isinstance(source.get('sha256'), str)
                     and hashlib.sha256(evidence_bytes).hexdigest() == source['sha256'] and json.loads(evidence_bytes) == unchanged
                     and unchanged.get('dispatch') == args.reuse_dispatch and unchanged.get('terminal') == args.terminal
                     and unchanged.get('incarnation') == original_incarnation and unchanged.get('settings_unchanged') is True
                     and observed_at.tzinfo is not None and valid_until.tzinfo is not None and observed_at <= now <= valid_until)
        except (AttributeError, KeyError, TypeError, ValueError, OSError, subprocess.SubprocessError) as exc:
            reuse_probe['error'] = str(exc)
            valid = False
        if not valid:
            args.initial_launch_state['reuse_probe'] = reuse_probe
            atomic_state(args.result, args.initial_launch_state, args.storage_capability)
            print(json.dumps({'ok': False, 'error': 'reuse source, process incarnation, settings or live observation mismatch'}))
            return 1
        result['receipt']['reuse'] = {'origin_sha256': origin_hash, 'worker_show': live,
                                      'prior_launch_effective': {key: original_effective[key] for key in ('agent', 'model', 'effort')},
                                      'limits': 'Original effective launch and current process observation; current model and effort unknown.'}
        result['receipt']['requested_run'] = original_run
        command = [executable, 'orchestration', 'worker-start', '--from', args.sender, '--spec', args.spec,
                   '--worktree', args.worktree, '--terminal', args.terminal, '--json']
    else:
        command = [executable, 'orchestration', 'worker-start', '--from', args.sender, '--task' if args.task else '--spec', args.task or args.spec,
                   '--worktree', args.worktree, '--agent', agent, '--model', selected['model'],
                   '--effort', selected['effort'], '--json', '--full']
    checked_run = original_run if reuse else args.run
    if checked_run:
        command.extend(('--run', checked_run))
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
            from host_model_catalog import load as load_catalog, compare, require, inventory_reference
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
                'prepared_manifest_sha256': decision['evidence'][inventory_reference(decision)]['sha256'],
                'refreshed_manifest_sha256': manifest_hash, 'refreshed_directory': str(refreshed_path),
                'runtime_id': fresh['runtime_id'], 'worktree': fresh['worktree']}
        except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as exc:
            print(json.dumps({'ok': False, 'error': 'catalog prelaunch denied', 'detail': str(exc)}))
            return 1
    try:
        storage_launch_guard(args, reserve=False, capability=args.storage_capability)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'ok': False, 'error': 'storage enrollment changed before start', 'detail': str(exc)}))
        return 1
    final_authority = check_routing(decision, args.decision.parent, record, args.record.parent, prelaunch=True)
    if runtime_id is not None and (read_json_snapshot(args.decision)[2] != original_decision_hash or
                                   read_json_snapshot(args.record)[2] != record_hash):
        print(json.dumps({'ok': False, 'error': 'AGY decision or record changed before start'}))
        return 1
    if (not final_authority['ok'] or
            final_authority['receipt'].get('worker_table_authority') != result['receipt'].get('worker_table_authority') or
            final_authority['receipt'].get('configuration_sha256') != result['receipt'].get('configuration_sha256')):
        print(json.dumps({'ok': False, 'error': 'configured worker table or configuration changed before start',
                          'check': final_authority}))
        return 1
    result['receipt']['launch_argv'] = command
    import run_completion as rc
    args.storage_capability.verify()
    receipt_ref = args.receipt.absolute().relative_to(args.storage_capability.root).as_posix()
    with rc.parent_fd(args.storage_capability.fd, receipt_ref) as (parent, name):
        receipt_handle = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
    with os.fdopen(receipt_handle, 'w', encoding='utf-8') as receipt:
        if timing is None:
            json.dump(result, receipt, ensure_ascii=False, indent=2)
            receipt.write('\n')
        else:
            payload = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
            receipt.write(payload)
            timing.receipt_sha256 = hashlib.sha256(payload.encode('utf-8')).hexdigest()
        receipt.flush()
        os.fsync(receipt.fileno())
    if args.lifecycle is not None:
        args.lifecycle.pending(command, args.receipt)
    args.storage_capability.verify()
    pending = {'launch_state_version': 1, 'launch_state': 'invocation_pending',
               'decision_sha256': decision_hash}
    if timing is not None:
        timing.mark('prepared')
        pending = timing.add(pending, 'invocation_pending')
    atomic_state(args.result, pending, args.storage_capability)
    try:
        args.storage_capability.verify()
        if timing is not None:
            timing.mark('start_enter')
        host = subprocess.run(command, check=False, capture_output=True, text=True, timeout=args.start_timeout)
    except subprocess.TimeoutExpired as exc:
        if timing is not None:
            timing.mark('start_exit')
        partial = {'format': 'company-launch-timeout/v1',
                   'stdout': timeout_stream_metadata(exc.output),
                   'stderr': timeout_stream_metadata(exc.stderr)}
        state = {'launch_state_version': 1, 'launch_state': 'unknown',
                 'decision_sha256': decision_hash, 'error_code': 'host_start_timeout',
                 'error': 'host start timed out; outcome unknown', 'partial_output': partial,
                 'diagnostic_reference': 'self'}
        if timing is not None:
            state = timing.add(state, 'host_start_timeout')
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
        state = {'launch_state_version': 1, 'launch_state': 'unknown',
                 'decision_sha256': decision_hash, 'error': str(exc)}
        if timing is not None:
            if 'start_enter' in timing.marks:
                timing.mark('start_exit')
            state = timing.add(state, 'host_start_error')
        atomic_state(args.result, state, args.storage_capability)
        print(json.dumps({'ok': False, 'error': 'host outcome unknown; reconciliation required'}))
        return 1
    if timing is not None:
        timing.mark('start_exit')
    status, reason = ('failed', 'host returned nonzero') if host.returncode else ('unverified', 'host result lacks required readback')
    full_readback = None
    try:
        envelope = json.loads(host.stdout, object_pairs_hook=unique_object, parse_constant=invalid_constant)
        payload = envelope['result']
        response_runtime = envelope.get('_meta', {}).get('runtimeId')
        if host.returncode == 0 and envelope.get('ok') is False:
            status, reason = 'failed', 'host returned an unsuccessful result'
        elif runtime_id is not None and response_runtime != runtime_id:
            status, reason = 'unverified', 'host runtime does not match AGY evidence'
        elif host.returncode == 0 and envelope.get('ok') is True and isinstance(payload.get('taskId'), str) and payload['taskId'] and isinstance(payload.get('dispatchId'), str) and payload['dispatchId']:
            if args.task and (payload['taskId'] != args.task or payload['dispatchId'] == args.retry_of):
                status, reason = 'failed', 'host Task or Dispatch differs from checked identity'
            elif args.run and payload.get('runId') != args.run:
                status, reason = ('unverified', 'host Run identity missing') if payload.get('runId') is None else ('failed', 'host Run identity differs')
            elif reuse:
                incarnation = (payload.get('prompt') or {}).get('processIncarnation')
                effective = (payload.get('launch') or {}).get('effective')
                reported_terminal = payload.get('terminal')
                if payload['taskId'] == original_task_id or payload['dispatchId'] == args.reuse_dispatch:
                    status, reason = 'failed', 'reuse did not return a new Task and Dispatch'
                elif reported_terminal is not None and reported_terminal != args.terminal:
                    status, reason = 'failed', 'reuse returned a different terminal'
                elif incarnation is not None and incarnation != original_incarnation:
                    status, reason = 'failed', 'reuse returned a different terminal incarnation'
                elif payload.get('runId') != original_run or response_runtime not in (None, reuse_runtime):
                    status, reason = 'unverified', 'reuse host response does not identify the original Run and runtime'
                elif any(effect.get('kind') == 'terminal' and
                         (effect.get('id') != args.terminal or effect.get('action') not in (None, 'reused'))
                         for effect in (payload.get('effects') or ())):
                    status, reason = 'failed', 'reuse returned a contradictory terminal effect'
                elif effective is not None and not isinstance(effective, dict):
                    status, reason = 'unverified', 'reuse response contains malformed effective settings'
                elif any((effective or {}).get(field) not in (None, expected)
                         for field, expected in (('agent', agent), ('model', selected['model']), ('effort', selected['effort']))):
                    status, reason = 'failed', 'reuse returned effective settings that contradict the checked selection'
                elif any((effective or {}).get(key) is not None for key in ('model', 'effort')):
                    status, reason = 'unverified', 'reuse response contains settings without a current observation contract'
                else:
                    full_readback = full_launch_readback(
                        executable, payload, selected, args.probe_timeout, agent=agent,
                        runtime_id=reuse_runtime, reused_process=(args.terminal, reuse_pty, original_incarnation))
                    status, reason = full_readback['status'], full_readback['reason']
            else:
                effective = payload.get('launch', {}).get('effective')
                if isinstance(effective, dict) and all(effective.get(field) is not None for field in ('agent', 'model', 'effort')):
                    if effective.get('agent') == agent and effective.get('model') == selected['model'] and effective.get('effort') == selected['effort']:
                        if response_runtime and payload.get('runId') and not payload.get('processIncarnation'):
                            full_readback = full_launch_readback(executable, payload, selected, args.probe_timeout,
                                                                agent=agent, runtime_id=response_runtime)
                            status, reason = full_readback['status'], full_readback['reason']
                        else:
                            status, reason = 'observed', 'host IDs and effective launch settings observed'
                    else:
                        status, reason = 'failed', 'host effective launch settings differ from checked selection'
                elif runtime_id is not None and isinstance(effective, dict) and any(
                        effective.get(k) is not None and effective[k] != v for k, v in
                        (('agent', agent), ('model', selected['model']), ('effort', selected['effort']))):
                    status, reason = 'failed', 'partial host settings contradict checked AGY selection'
                elif args.run:
                    full_readback = full_launch_readback(executable, payload, selected, args.probe_timeout,
                                                        agent=agent, runtime_id=runtime_id or response_runtime)
                    status, reason = full_readback['status'], full_readback['reason']
    except (ValueError, KeyError, TypeError, AttributeError):
        pass
    if timing is not None:
        timing.mark('readback_done')
    args.storage_capability.verify()
    final = {'launch_state_version': 1, 'launch_state': 'observed' if status == 'observed' else 'unknown',
               'decision_sha256': decision_hash, 'prelaunch_receipt_sha256': hashlib.sha256(args.receipt.read_bytes()).hexdigest(),
               'exit_code': host.returncode, 'readback_status': status, 'readback_reason': reason,
               'stdout': host.stdout, 'stderr': host.stderr,
               'full_readback': full_readback}
    if reuse:
        final['reuse_settings'] = {'status': 'unknown', 'model': None, 'effort': None}
    atomic_state(args.result, timing.add(final, 'readback_finished') if timing else final,
                 args.storage_capability)
    if status == 'observed' and args.lifecycle is not None:
        args.lifecycle.bind()
    sys.stdout.write(host.stdout)
    sys.stderr.write(host.stderr)
    if status != 'observed':
        sys.stderr.write('Routing launch readback ' + status + ': ' + reason + '; inspect the preserved host receipt before any recovery.\n')
    return 0 if status == 'observed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
