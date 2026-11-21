"""Separate current exact-file authority. Never enroll or backfill historical Runs.

All actions use run_completion.unlink_exact with an external durable receipt sink.
Source/owner/pin/open-path denials are not waived by maintenance authority.
"""
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import socket
import stat
import subprocess

import completion_hook as hook
import run_completion as rc
from native_operations import Blocked, request, shape, require, text, valid_hash, pinned, regular, decode, sha

KEYS = ('schema', 'operation_id', 'owner', 'sejong_home', 'root', 'targets', 'preserve', 'historical_metadata', 'classification_evidence', 'consumer_evidence', 'preservation_evidence')


def lexical(value):
    text(value, 'absolute lexical path')
    p = Path(value)
    require(p.is_absolute() and str(p) == value and '..' not in p.parts, 'absolute canonical lexical path required')
    return p


def load(path):
    value, base, source = request(path, 'company-native-storage-maintenance-request/v1', KEYS)
    for key in ('operation_id', 'owner'): text(value[key], key)
    home, root = lexical(value['sejong_home']), lexical(value['root'])
    require(root.is_relative_to(home / 'runs') and root != home / 'runs', 'legacy root outside bounded owned namespace')
    require(not Path(source['path']).is_relative_to(root), 'current request must be outside historical root')
    require(isinstance(value['targets'], list) and bool(value['targets']), 'exact regular-file targets required')
    refs = []
    for item in value['targets']:
        shape(item, ('path', 'sha256', 'identity', 'uid', 'mode', 'origin', 'unnecessary_proof', 'remaining_consumers'), 'maintenance target')
        rc.parts(item['path']); valid_hash(item['sha256']); text(item['origin'], 'origin')
        require(type(item['uid']) is int and type(item['mode']) is int, 'UID/mode required')
        require(item['remaining_consumers'] == [], 'unknown/live remaining consumers', Blocked)
        require(isinstance(item['identity'], list) and len(item['identity']) == 5 and all(type(x) is int and x >= 0 for x in item['identity']), 'invalid exact target identity')
        pinned(item['unnecessary_proof'], base)
        refs.append(item['path'])
    require(len(refs) == len(set(refs)), 'duplicate maintenance target')
    for key in ('preserve', 'historical_metadata'):
        require(isinstance(value[key], list), 'explicit ' + key + ' required')
        for row in value[key]:
            shape(row, ('path', 'sha256', 'identity'), key)
            if row['path'] not in rc.RESERVED: rc.parts(row['path'])
            if row['sha256'] is not None: valid_hash(row['sha256'])
            require((row['sha256'] is None) == (row['identity'] is None), 'invalid absence pin')
        require(len({x['path'] for x in value[key]}) == len(value[key]), 'duplicate preservation/metadata pin')
    protected = {x['path'] for x in value['preserve'] + value['historical_metadata']} | rc.RESERVED
    require(not set(refs) & protected, 'historical metadata/evidence target protected', Blocked)
    for key in ('classification_evidence', 'consumer_evidence', 'preservation_evidence'): pinned(value[key], base)
    return value, source, base


def historical_readback(root, fd, value):
    for item in value['preserve'] + value['historical_metadata']:
        if item['sha256'] is None:
            require(not os.path.lexists(root / item['path']), 'historical absence changed: ' + item['path'], Blocked)
        else:
            binding = rc.read_file(fd, item['path'], True)[1] if item['path'] in rc.RESERVED else rc.snapshot_file(fd, item['path'])
            require(binding == item, 'historical/preserved original changed: ' + item['path'], Blocked)


def check(value):
    root, fd = rc.open_run(Path(value['sejong_home']), Path(value['root']))
    try:
        require(not Path.cwd().is_relative_to(root), 'current workspace protected', Blocked)
        rows = rc.storage_preflight(root, fd, [x['path'] for x in value['targets']], Path(value['sejong_home']))
        rc.pins(fd)
        metadata = {x['path']: x for x in value['historical_metadata']}
        require((rc.RESERVED - {rc.LOCK}) <= set(metadata), 'complete historical metadata/absence pins required', Blocked)
        historical_readback(root, fd, value)
        # Protect every historical native preserve binding and accepted record.
        retained = {'record.json', 'seungjeongwon-run.json', 'run-summary.json'}
        if metadata[rc.MANIFEST]['sha256'] is not None:
            manifest = rc.decode(rc.read_file(fd, rc.MANIFEST, True)[0]); rc.validate_manifest(manifest)
            retained.update(x['path'] for x in manifest['preserve'])
            if 'enrollment' in manifest: retained.add(manifest['enrollment']['record'])
        # No rewriting legacy metadata; supplied inventory must preserve originals.
        require(not retained & {x['path'] for x in value['targets']}, 'historical source/record/evidence protected', Blocked)
        for target in value['targets']:
            rc.pins(fd, target['path'])
            binding = {k: target[k] for k in ('path', 'sha256', 'identity')}
            require(rc.snapshot_file(fd, target['path']) == binding, 'stale maintenance target', Blocked)
            with rc.parent_fd(fd, target['path']) as (parent, name): st = os.stat(name, dir_fd=parent, follow_symlinks=False)
            require(st.st_uid == target['uid'] == os.getuid() and stat.S_IMODE(st.st_mode) == target['mode'] and not st.st_mode & 0o022, 'maintenance target owner/mode mismatch', Blocked)
        coordination = None
        try:
            lock = os.open(rc.LOCK, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        except FileNotFoundError:
            lock = None
        if lock is not None:
            try:
                cap = rc.RunLock(root, fd, lock)
                cap.verify(held=False)
                coordination = cap.binding()
            finally:
                os.close(lock)
        return dict(root_identity=[os.fstat(fd).st_dev, os.fstat(fd).st_ino], root_coordination=coordination, inventory_sha256=sha(json.dumps(rows, sort_keys=True).encode()), activity=rc.probe_activity(root))
    finally:
        os.close(fd)


def plan(request_path):
    value, source, base = load(request_path)
    result: dict = dict(schema='company-native-storage-maintenance-plan/v1', operation_id=value['operation_id'], owner=value['owner'], host=socket.gethostname(), source=source, request=value, root=value['root'], targets=value['targets'], preserve=value['preserve'], historical_metadata=value['historical_metadata'], expected_logical_bytes=None, ready=False, apply_authorized=False, status='blocked', blockers=[])
    try:
        result.update(check(value))
        result.update(ready=True, status='prepared', expected_logical_bytes=sum(x['identity'][2] for x in value['targets']))
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        result['blockers'].append(str(exc))
    return result


def package_fingerprint():
    package = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for path in sorted(package.rglob('*')):
        if '__pycache__' in path.parts or path.name == '.agent-company-skill.json': continue
        require(not path.is_symlink(), 'linked candidate payload', Blocked)
        if path.is_file():
            digest.update(path.relative_to(package).as_posix().encode()); digest.update(sha(regular(path)).encode())
    return digest.hexdigest()


def authority(saved, plan_hash, authorization_path, review_path, base):
    auth = shape(decode(regular(Path(authorization_path))), ('schema', 'operation_id', 'plan_sha256', 'owner', 'host', 'approved_by', 'approved_at', 'valid_until', 'scope', 'authority_evidence'), 'maintenance authorization')
    review = shape(decode(regular(Path(review_path))), ('schema', 'operation_id', 'plan_sha256', 'owner', 'host', 'assessor', 'executor', 'candidate', 'verdict', 'reviewed_at', 'valid_until', 'inventory_evidence', 'preservation_evidence', 'consent_evidence', 'prior_denial_resolution'), 'maintenance review')
    require(auth['schema'] == 'company-native-storage-maintenance-authorization/v1' and review['schema'] == 'company-native-storage-maintenance-review/v1', 'unsupported maintenance authority', Blocked)
    for item, time_key in ((auth, 'approved_at'), (review, 'reviewed_at')):
        require(all(item[k] == saved[k] for k in ('operation_id', 'owner', 'host')) and item['plan_sha256'] == plan_hash, 'stale operation/owner/host/plan approval', Blocked)
        observed, until = [datetime.fromisoformat(item[k].replace('Z', '+00:00')) for k in (time_key, 'valid_until')]
        require(observed.tzinfo is not None and until.tzinfo is not None and observed <= datetime.now(timezone.utc) <= until, 'future/expired/unknown approval validity', Blocked)
    require(auth['approved_by'] == saved['owner'] and auth['scope'] == [x['path'] for x in saved['targets']], 'exact current owner target approval required', Blocked)
    text(review['assessor'], 'assessor')
    require(review['verdict'] == 'approved' and review['executor'] == saved['owner'] and review['assessor'] not in (review['executor'], auth['approved_by']), 'self/missing independent target review', Blocked)
    for doc, key, root in ((auth,'authority_evidence',Path(authorization_path).parent), (review,'inventory_evidence',Path(review_path).parent), (review,'preservation_evidence',Path(review_path).parent), (review,'consent_evidence',Path(review_path).parent)):
        pinned(doc[key],root)
    require(review['consent_evidence'] == auth['authority_evidence'] and review['preservation_evidence'] == saved['request']['preservation_evidence'], 'review does not bind original consent/preservation', Blocked)
    if review['prior_denial_resolution'] is not None:
        shape(review['prior_denial_resolution'], ('denial', 'resolution'), 'prior denial resolution')
        for reference in review['prior_denial_resolution'].values(): pinned(reference,Path(review_path).parent)
    candidate = shape(review['candidate'], ('revision', 'dirty_manifest'), 'candidate')
    _, raw = pinned(candidate['dirty_manifest'], Path(review_path).parent)
    payload = shape(decode(raw), ('revision', 'package_sha256'), 'candidate manifest')
    require(payload['revision'] == candidate['revision'] and payload['package_sha256'] == package_fingerprint(), 'reviewed candidate payload differs', Blocked)
    marker = Path(__file__).resolve().parents[1] / '.agent-company-skill.json'
    if marker.exists():
        require(candidate['revision'] in decode(regular(marker)).values(), 'staged candidate revision mismatch', Blocked)
    else:
        product_root = Path(__file__).resolve().parents[3]
        revision = subprocess.check_output(['git', '--no-optional-locks', '-C', str(product_root), 'rev-parse', 'HEAD'], text=True).strip()
        require(candidate['revision'] == revision, 'source candidate revision mismatch', Blocked)
    _, raw = pinned(saved['request']['consumer_evidence'], base)
    consumers = decode(raw)
    require(consumers.get('quiescent') is True and consumers.get('consumers') == [], 'consumer completeness/quiescence not proved', Blocked)
    _, raw = pinned(saved['request']['preservation_evidence'], base)
    recovery = decode(raw)
    require(isinstance(recovery.get('copies'), list), 'preservation recovery copies required', Blocked)
    copies = {x['original']: x for x in recovery['copies']}
    for item in saved['preserve'] + [x for x in saved['historical_metadata'] if x['sha256'] is not None and x['path'] != rc.LOCK]:
        original = str(Path(saved['root']) / item['path'])
        require(original in copies, 'original recoverability missing', Blocked)
        backup, raw = pinned(copies[original]['copy'], base)
        require(not backup.is_relative_to(Path(saved['root'])) and sha(raw) == item['sha256'], 'recovery original bytes mismatch', Blocked)
    return auth, review


def closeout(request_path):
    """Read one exact current operation; never initialize history or replay apply.

    Supplied actor strings/pins are not authenticated consent. This reader proves
    only the recorded operation's current namespace, action prefix and originals.
    """
    value, base, _ = request(request_path, 'company-native-storage-maintenance-closeout-request/v1', ('schema', 'plan', 'authorization', 'review'))
    plan_path, raw = pinned(value['plan'], base)
    authorization, _ = pinned(value['authorization'], base)
    review, _ = pinned(value['review'], base)
    saved = decode(raw)
    require(saved.get('schema') == 'company-native-storage-maintenance-plan/v1' and saved.get('ready') is True and saved.get('apply_authorized') is False, 'unsupported maintenance result plan')
    source = saved['source']
    require(sha(regular(Path(source['path']))) == source['sha256'], 'maintenance result request changed', Blocked)
    original, _, original_base = load(source['path'])
    require(original == saved['request'], 'maintenance result plan/request mismatch', Blocked)
    result: dict = dict(schema='company-native-storage-maintenance-closeout/v1', operation_id=saved['operation_id'], sejong_home=original['sejong_home'], run=saved['root'], owner=saved['owner'], enrollment='not_applicable_maintenance', status='unknown', reason='operation_result_not_observed', receipt=None, removed_files=None, removed_logical_bytes=None, readback_verified=False, trigger=dict(mode='unknown', observed=False, evidence=None), pending=dict(owner=saved['owner'], recheck='inspect exact current operation originals; never replay apply'))
    bundle = operation_bundle(original, saved['root_identity'])
    legacy_bundle = Path(original['sejong_home']) / 'state/company-storage-maintenance' / sha(str(Path(saved['root'])).encode())
    if not os.path.lexists(bundle) and os.path.lexists(legacy_bundle): bundle = legacy_bundle
    sink = bundle / rc.RECEIPT
    parent = fd = None
    try:
        try:
            parent = hook.state_parent(sink, create=False)
            raw_receipt, receipt_binding = rc.read_file(parent, rc.RECEIPT, True)
        except FileNotFoundError:
            return result
        rc.verify_run_path(bundle, parent)
        require(os.fstat(parent).st_uid == os.getuid() and not os.fstat(parent).st_mode & 0o077, 'maintenance result sink is not private', Blocked)
        authority(saved, value['plan']['sha256'], authorization, review, original_base)
        root, fd = rc.open_run(Path(original['sejong_home']), Path(saved['root']))
        rc.verify_run_path(root, fd)
        require([os.fstat(fd).st_dev, os.fstat(fd).st_ino] == saved['root_identity'], 'maintenance result root identity changed', Blocked)
        rc.storage_preflight(root, fd, [], Path(original['sejong_home']))
        historical_readback(root, fd, original)
        receipt = decode(raw_receipt)
        require(receipt.get('root_identity') == saved['root_identity'], 'receipt root identity differs', Blocked)
        sink_lock = os.open(rc.LOCK, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            sink_cap = rc.RunLock(bundle, parent, sink_lock)
            sink_cap.verify(held=False)
            require(sink_cap.binding() == receipt.get('sink_coordination'), 'receipt sink coordination differs', Blocked)
        finally:
            os.close(sink_lock)
        require(receipt.get('schema') == 'company-native-storage-maintenance-result/v1' and all(receipt.get(k) == saved[k] for k in ('operation_id', 'owner', 'host')) and receipt.get('plan_sha256') == value['plan']['sha256'], 'maintenance receipt provenance mismatch', Blocked)
        bindings = [{k: x[k] for k in ('path', 'sha256', 'identity')} for x in original['targets']]
        removed = receipt.get('removed')
        require(isinstance(removed, list) and removed == bindings[:len(removed)], 'maintenance removed prefix invalid', Blocked)
        require(all(not os.path.lexists(root / x['path']) for x in removed), 'maintenance removed path reappeared', Blocked)
        reference = dict(path=str(sink), sha256=receipt_binding['sha256'])
        result.update(receipt=reference, trigger=dict(mode='explicit_maintenance', observed=True, evidence=reference))
        completed = receipt.get('status') == 'completed' and removed == bindings and not receipt.get('errors') and 'pending' not in receipt
        newer_rejection = False
        try:
            _, rejection = rc.read_file(parent, rc.REJECTION, True)
            newer_rejection = rejection['identity'][3] >= receipt_binding['identity'][3]
        except FileNotFoundError:
            pass
        rc.verify_run_path(bundle, parent)
        require(rc.read_file(parent, rc.RECEIPT, True) == (raw_receipt, receipt_binding), 'maintenance result changed during readback', Blocked)
        result.update(status='completed' if completed and not newer_rejection else 'blocked', reason='verified_completed_operation' if completed and not newer_rejection else 'partial_pending_or_newer_rejection_requires_owner_recovery', removed_files=len(removed), removed_logical_bytes=sum(x['identity'][2] for x in removed), readback_verified=True)
        if result['status'] == 'completed': result['pending'] = None
        return result
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        result.update(status='blocked', reason=str(exc), readback_verified=False, removed_files=None, removed_logical_bytes=None)
        return result
    finally:
        if fd is not None: os.close(fd)
        if parent is not None: os.close(parent)


def operation_bundle(value, root_identity):
    # Stable root identity, not caller spelling or operation_id, owns retry state.
    key = sha(json.dumps(root_identity, separators=(',', ':')).encode())
    return Path(value['sejong_home']) / 'state/company-storage-maintenance' / key


def apply(plan_path, expected_sha256, authorization, review):
    valid_hash(expected_sha256)
    try:
        raw = regular(Path(plan_path)); require(sha(raw) == expected_sha256, 'plan sha256 mismatch', Blocked)
        saved = decode(raw)
        require(saved.get('schema') == 'company-native-storage-maintenance-plan/v1' and saved.get('ready') is True and saved.get('apply_authorized') is False, 'maintenance plan not ready', Blocked)
        source = saved['source']; require(sha(regular(Path(source['path']))) == source['sha256'], 'original maintenance request changed', Blocked)
        value, _, base = load(source['path'])
        require(plan(source['path']) == saved, 'stale maintenance plan/current guard changed', Blocked)
        auth_raw, review_raw = regular(Path(authorization)), regular(Path(review))
        authority(saved, expected_sha256, authorization, review, base)
        # Missing legacy coordination is a blocker, NEVER permission to create or
        # modify old metadata. Normal init/register/complete use this same inode.
        with rc.lifecycle_lock(Path(value['sejong_home']), Path(value['root'])) as root_cap:
            root, fd = root_cap.root, root_cap.fd
            require([os.fstat(fd).st_dev, os.fstat(fd).st_ino] == saved['root_identity'], 'reopened maintenance root differs', Blocked)
            require(root_cap.binding() == saved.get('root_coordination'), 'maintenance root coordination changed', Blocked)
            require(plan(source['path']) == saved, 'maintenance state changed under root lock', Blocked)
            bundle = operation_bundle(value, saved['root_identity'])
            legacy_bundle = Path(value['sejong_home']) / 'state/company-storage-maintenance' / sha(str(Path(value['root'])).encode())
            require(not os.path.lexists(legacy_bundle), 'prior path-keyed operation requires owner recovery', Blocked)
            sink = bundle / rc.RECEIPT
            container = hook.state_parent(bundle, create=True)
            try:
                # Exclusive durable namespace claim: even a crash before intent
                # leaves a non-retryable operation, not an empty new-id escape.
                os.mkdir(bundle.name, 0o700, dir_fd=container)
                os.fsync(container)
            finally:
                os.close(container)
            parent = hook.state_parent(sink, create=False)
            lock = sink_cap = None
            result: dict = dict(schema='company-native-storage-maintenance-result/v1', operation_id=value['operation_id'], owner=value['owner'], host=saved['host'], plan_sha256=expected_sha256, root_identity=saved['root_identity'], status='blocked', removed=[], errors=[])
            try:
                require(os.fstat(parent).st_uid == os.getuid() and not os.fstat(parent).st_mode & 0o077, 'current operation bundle must be private', Blocked)
                lock = os.open(rc.LOCK, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=parent)
                sink_cap = rc.RunLock(bundle, parent, lock)
                sink_cap.verify(held=False)
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                sink_cap.held = True
                sink_cap.verify()
                result['sink_coordination'] = sink_cap.binding()
                require(not any(name != rc.LOCK for name in os.listdir(parent)), 'prior maintenance action requires owner recovery; no new-id retry', Blocked)
                bindings = [{k: x[k] for k in ('path', 'sha256', 'identity')} for x in value['targets']]
                def validate():
                    root_cap.verify(); sink_cap.verify()
                    require([os.fstat(fd).st_dev, os.fstat(fd).st_ino] == saved['root_identity'], 'maintenance root identity changed', Blocked)
                    require(regular(Path(authorization)) == auth_raw and regular(Path(review)) == review_raw and regular(Path(plan_path)) == raw, 'approval/review/plan changed during action', Blocked)
                    require(sha(regular(Path(source['path']))) == source['sha256'], 'request changed during action', Blocked)
                    authority(saved, expected_sha256, authorization, review, base)
                    rc.storage_preflight(root, fd, [x['path'] for x in bindings], Path(value['sejong_home']))
                    historical_readback(root, fd, value)
                def persist(receipt):
                    root_cap.verify(); sink_cap.verify()
                    rc.write_metadata(parent, rc.RECEIPT, receipt)
                    sink_cap.verify()
                    written = rc.read_file(parent, rc.RECEIPT, True)[0]
                    require(rc.decode(written) == receipt and regular(sink) == written, 'external receipt namespace/readback mismatch', Blocked)
                validate(); rc.pins(fd)
                result['activity'] = rc.probe_activity(root)
                persist(result)  # Durable intent before even the first rename.
                rc.unlink_exact(root, fd, bindings, result, validate, persist)
                validate()
                require(all(not os.path.lexists(root / x['path']) for x in bindings), 'removed target reappeared', Blocked)
                result.update(status='completed', readback_verified=True, removed_logical_bytes=sum(x['identity'][2] for x in result['removed']))
                persist(result); validate()
                return {**result, 'receipt': dict(path=str(sink), sha256=sha(regular(sink)))}
            except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
                # A failed final persist/readback is not a completed operation,
                # even when every unlink happened. Preserve the durable prefix
                # and report uncertainty rather than leaking optimistic fields.
                result['status'] = 'blocked'
                result.pop('readback_verified', None)
                result.pop('removed_logical_bytes', None)
                result['errors'].append(str(exc))
                reference = None
                # Never write another actor's/detached/replaced namespace, or
                # overwrite the durable original intent/action-prefix receipt.
                if sink_cap is not None and sink_cap.held:
                    try:
                        root_cap.verify(); sink_cap.verify()
                        rc.write_metadata(parent, rc.REJECTION, result)
                        if os.path.lexists(sink): reference = dict(path=str(sink), sha256=sha(regular(sink)))
                    except (OSError, ValueError) as readback_error:
                        result['errors'].append('receipt namespace unverified: ' + str(readback_error))
                return {**result, 'receipt': reference}
            finally:
                if sink_cap is not None: sink_cap.held = False
                if lock is not None: os.close(lock)
                os.close(parent)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        raise Blocked('maintenance authority/state refused: ' + str(exc)) from exc
