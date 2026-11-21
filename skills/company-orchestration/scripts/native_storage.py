"""Read-only explicit Run inventory/plan, existing guarded completion apply only."""
import contextlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess

import run_completion as rc
from native_operations import (Blocked, Invalid, absolute, decode, regular, request,
                               require, sha, shape, text, valid_hash, pinned)

SCHEMA = 'company-native-storage-request/v1'
KEYS = ('schema', 'roots', 'sejong_home', 'record', 'expect_manifest_sha256')
CATEGORIES = ('declared_disposable', 'preserved', 'protected', 'unknown')


def load(path):
    value, base, source = request(path, SCHEMA, KEYS)
    require(isinstance(value['roots'], list) and bool(value['roots']), 'explicit roots required')
    value['sejong_home'] = str(absolute(value['sejong_home'], base))
    rc.parts(value['record'])
    valid_hash(value['expect_manifest_sha256'])
    seen = set()
    for row in value['roots']:
        shape(row, ('path', 'kind', 'run_id', 'owner'), 'root')
        require(row['kind'] == 'company-run', 'unsupported root kind')
        text(row['run_id'], 'run_id'); text(row['owner'], 'owner')
        row['path'] = str(absolute(row['path'], base))
        require(row['path'] not in seen, 'duplicate root')
        seen.add(row['path'])
    return value, source


def inventory(fd, declared, preserved, protected, blockers):
    return rc.storage_inventory(fd, declared, preserved, protected, blockers)


def inspect(value, row):
    result = {**row, 'root_identity': None, 'record': None, 'manifest_sha256': None,
              'disposable': [], 'preserve': [], 'files': [], 'blockers': [], 'activity': None,
              'inventory_complete': False}
    blocked = result['blockers']
    fd = None
    try:
        root, fd = rc.open_run(Path(value['sejong_home']), Path(row['path']))
        rc.verify_run_path(root, fd)
        st = os.fstat(fd)
        require(st.st_uid == os.getuid() and not st.st_mode & 0o022, 'Run root shared/non-owned', Blocked)
        # The explicit Company namespace must not be writable by another actor.
        home = Path(value['sejong_home'])
        for directory in (home, home / 'runs'):
            info = directory.lstat()
            require(info.st_uid == os.getuid() and not info.st_mode & 0o022,
                    'Company namespace shared/non-owned', Blocked)
        result['root_identity'] = [st.st_dev, st.st_ino]
        # A Run inside ANY git worktree is conservatively protected, including
        # clean tracked and untracked source. Never run git or mutate its index.
        for ancestor in (root, *root.parents):
            if os.path.lexists(ancestor / '.git'):
                blocked.append('Run overlaps source/worktree; tracked/uncommitted/untracked files protected')
                break
        declared, preserved, protected = set(), set(), set(rc.RESERVED) | {value['record']}
        try:
            raw, _ = rc.read_file(fd, rc.MANIFEST, metadata=True)
            manifest = rc.decode(raw)
            rc.validate_manifest(manifest)
            result['manifest_sha256'] = rc.sha(raw)
            require(result['manifest_sha256'] == value['expect_manifest_sha256'], 'manifest compare-and-swap mismatch', Blocked)
            require(manifest['root'] == str(root) and manifest.get('root_identity') == result['root_identity'] and
                    manifest['run_id'] == row['run_id'] and manifest['owner'] == row['owner'],
                    'Run/layout/owner binding mismatch', Blocked)
            result['disposable'], result['preserve'] = manifest['disposable'], manifest['preserve']
            declared = {x['path'] for x in manifest['disposable']}
            preserved = {x['path'] for x in manifest['preserve']}
            record_raw, result['record'] = rc.read_file(fd, value['record'])
            record = rc.decode(record_raw)
            # Evidence is protected even if the caller labels it disposable.
            parent = Path(value['record']).parent
            if record.get('goal_evidence'):
                protected.add((parent / record['goal_evidence']['path']).as_posix())
            for evidence in record.get('evidence', {}).values():
                if evidence.get('file'):
                    target = Path(evidence['file'])
                    target = target if target.is_absolute() else root / parent / target
                    try:
                        protected.add(str(target.resolve(strict=True).relative_to(root)))
                    except ValueError:
                        pass
            require(not (declared & protected), 'protected evidence/record declared disposable', Blocked)
            require(bool(preserved), 'compact evidence declaration required', Blocked)
            rc.validate_acceptance(record, root / value['record'], manifest, result['manifest_sha256'],
                                   require_routing=manifest.get('routing_accounting') == 'required')
            rc.pins(fd)
            for binding in [*manifest['disposable'], *manifest['preserve']]:
                rc.pins(fd, binding['path'])
                require(rc.snapshot_file(fd, binding['path']) == binding, 'stale file identity/content: ' + binding['path'], Blocked)
            # Existing receipts require owner recovery, not implicit native retry.
            for name in (rc.RECEIPT, rc.REJECTION):
                require(not os.path.lexists(root / name), 'existing completion attempt requires explicit owner recovery', Blocked)
            rc.storage_preflight(root, fd, declared, Path(value['sejong_home']))
            result['activity'] = rc.probe_activity(root)
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
            blocked.append(str(exc))
        result['files'] = inventory(fd, declared, preserved, protected, blocked)
        rc.verify_run_path(root, fd)
        result['inventory_complete'] = True
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        blocked.append(str(exc))
    finally:
        if fd is not None: os.close(fd)
    result['blockers'] = sorted(set(blocked))
    result['ready'] = not result['blockers']
    result['coverage'] = 'complete' if result['inventory_complete'] else 'unknown'
    result['breakdown'] = {}
    for category in CATEGORIES:
        entries = [x for x in result['files'] if x['category'] == category]
        result['breakdown'][category] = {'files': len(entries) if result['inventory_complete'] else None,
            'bytes': sum(x['bytes'] for x in entries) if result['inventory_complete'] and all(x['bytes'] is not None for x in entries) else None}
    result['files_count'] = len(result['files']) if result['coverage'] == 'complete' else None
    result['bytes'] = (sum(x['bytes'] for x in result['files'])
                       if result['coverage'] == 'complete' and all(x['bytes'] is not None for x in result['files']) else None)
    return result


def report(request_path):
    value, source = load(request_path)
    roots = [inspect(value, row) for row in value['roots']]
    return {'schema': 'company-native-storage/v1', 'status': 'reported', 'read_only': True,
            'sources': [source], 'roots': roots,
            'coverage': 'complete' if all(x['coverage'] == 'complete' for x in roots) else 'unknown',
            'unsupported_roots_bytes': None,
            'limits': ['Only explicitly selected Company Run roots; no whole-disk/app/cache inventory.',
                       'Declared disposable is not deletion authority. Unknown/unregistered files are never selected.',
                       'A successful preview is not a future activity or cleanup guarantee.']}


def build_plan(value, source):
    require(len(value['roots']) == 1, 'plan requires one exact Run root')
    result = inspect(value, value['roots'][0])
    return {'schema': 'company-native-storage-plan/v1', 'operation': 'run_completion.complete',
            'status': 'prepared' if result['ready'] else 'blocked', 'ready': result['ready'],
            'apply_authorized': False, 'sources': [source], 'request': value,
            'root': result['path'], 'run_id': result['run_id'], 'owner': result['owner'],
            'root_identity': result['root_identity'], 'record': result['record'],
            'manifest_sha256': result['manifest_sha256'], 'disposable': result['disposable'],
            'preserve': result['preserve'], 'inventory_sha256': sha(json.dumps(result['files'], sort_keys=True).encode()),
            'expected_bytes': (sum(x['identity'][2] for x in result['disposable']) if result['ready'] else None),
            'blockers': result['blockers'],
            'limits': ['Explicit apply remains subject to user authority and every existing completion guard.']}


def plan(request_path):
    value, source = load(request_path)
    return build_plan(value, source)


def apply(plan_path, expected_sha256):
    valid_hash(expected_sha256)
    raw = regular(Path(plan_path))
    require(sha(raw) == expected_sha256, 'plan sha256 mismatch', Blocked)
    saved = decode(raw)
    require(isinstance(saved, dict) and saved.get('schema') == 'company-native-storage-plan/v1' and
            saved.get('operation') == 'run_completion.complete' and saved.get('ready') is True and
            saved.get('apply_authorized') is False, 'plan not ready or unsupported', Blocked)
    # Re-read the exact original request as well as all accepted retention bytes.
    try:
        source = saved['sources'][0]
        require(sha(regular(Path(source['path']))) == source['sha256'], 'original request changed', Blocked)
        current = plan(source['path'])
        require(current == saved and current['ready'], 'stale plan/current guard changed', Blocked)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise Blocked('plan revalidation refused: ' + str(exc)) from exc
    value = saved['request']
    output = io.StringIO()
    # ONLY the original lock/CAS/quarantine/receipt path may remove files.
    with contextlib.redirect_stdout(output):
        code = rc.main(['complete', '--run', saved['root'], '--sejong-home', value['sejong_home'],
                        '--record', value['record'], '--expect-manifest-sha256', saved['manifest_sha256'], '--trigger', 'explicit_lead'])
    receipt = decode(output.getvalue())
    require(isinstance(receipt, dict), 'completion did not return receipt', Blocked)
    verified = False
    if code == 0 and receipt.get('status') == 'completed':
        root, fd = rc.open_run(Path(value['sejong_home']), Path(saved['root']))
        try:
            readback = rc.decode(rc.read_file(fd, rc.RECEIPT, metadata=True)[0])
            require(readback == receipt and receipt.get('removed') == saved['disposable'], 'completion receipt mismatch', Blocked)
            for item in saved['disposable']:
                with rc.parent_fd(fd, item['path']) as (parent, name):
                    try:
                        os.stat(name, dir_fd=parent, follow_symlinks=False)
                    except FileNotFoundError:
                        continue
                    raise Blocked('removed path still present')
            for item in saved['preserve']:
                require(rc.snapshot_file(fd, item['path']) == item, 'preserved readback mismatch', Blocked)
            verified = True
        finally:
            os.close(fd)
    return {'schema': 'company-native-storage-apply/v1', 'status': 'completed' if verified else 'blocked',
            'plan_sha256': expected_sha256, 'receipt': receipt, 'readback_verified': verified}


def maintenance_plan(request_path):
    import native_maintenance
    return native_maintenance.plan(request_path)


def maintenance_apply(plan_path, expected_sha256, authorization, review):
    import native_maintenance
    return native_maintenance.apply(plan_path, expected_sha256, authorization, review)


# These adapters narrow the existing lifecycle; they do not intercept arbitrary IO.
ENROLL_KEYS = ('schema', 'sejong_home', 'run', 'run_id', 'owner', 'record', 'host', 'session_id', 'cwd', 'consumers', 'expect_session_binding_sha256', 'identity_evidence')
ARTIFACT_KEYS = ('path', 'class', 'owner', 'consumers', 'reason', 'origin', 'regeneration', 'next_use_or_recheck')


def lexical(value):
    text(value, 'absolute lexical path')
    path = Path(value)
    require(path.is_absolute() and str(path) == value and '..' not in path.parts, 'absolute canonical lexical path required')
    return path


def strings(value, label):
    require(isinstance(value, list) and all(isinstance(x, str) and x.strip() for x in value) and len(set(value)) == len(value), 'invalid ' + label)
    return value


def load_enrollment(path):
    value, base, source = request(path, 'company-native-storage-enrollment/v1', ENROLL_KEYS)
    for key in ('run_id', 'owner', 'session_id'): text(value[key], key)
    require(value['host'] in ('codex_stop', 'explicit_lead'), 'unsupported enrollment host')
    home = rc.default_home() if value['sejong_home'] is None else lexical(value['sejong_home'])
    home = lexical(str(home))
    run, cwd = lexical(value['run']), lexical(value['cwd'])
    require(cwd.is_dir(), 'actual cwd missing')
    require(not Path(source['path']).is_relative_to(run), 'enrollment request must be outside Run')
    require(run.is_relative_to(home / 'runs') and run != home / 'runs', 'Run outside resolved home')
    rc.parts(value['record']); strings(value['consumers'], 'consumers')
    if value['expect_session_binding_sha256'] is not None: valid_hash(value['expect_session_binding_sha256'])
    _, raw = pinned(value['identity_evidence'], base)
    observation = shape(decode(raw), ('host', 'session_id', 'cwd'), 'host identity observation')
    require(observation == {k: value[k] for k in observation}, 'host/session/cwd observation mismatch')
    if value['host'] == 'codex_stop':
        require(home == lexical(str(rc.default_home())), 'producer/callback home disagreement', Blocked)
    value['home_resolution'] = ('explicit_request' if value['sejong_home'] is not None else 'SEJONG_HOME' if os.environ.get('SEJONG_HOME') else 'shared_installed' if home == Path(rc.__file__).resolve().parents[3] / 'sejong' else 'standalone_codex_home')
    value['sejong_home'] = str(home)
    value['cwd_resolved'] = str(cwd.resolve(strict=True))
    return value, source


def enrollment_metadata(value, source):
    return dict(request=source, sejong_home=value['sejong_home'], host=value['host'], session_id=value['session_id'], cwd=value['cwd'], cwd_resolved=value['cwd_resolved'], record=value['record'])


def bound_enrollment(path):
    import completion_hook as hook
    value, source = load_enrollment(path)
    binding = decode(regular(hook.binding_path(value['sejong_home'], value['session_id'])))
    expected = dict(format='company-completion-session/v1', session_id=value['session_id'], run=value['run'], run_id=value['run_id'], owner=value['owner'], repo_root=value['cwd_resolved'], record=value['record'])
    require(binding == expected, 'exact session binding mismatch', Blocked)
    root, fd = rc.open_run(Path(value['sejong_home']), Path(value['run']))
    try:
        raw = rc.read_file(fd, rc.MANIFEST, True)[0]; manifest = rc.decode(raw); rc.validate_manifest(manifest)
        require(manifest.get('enrollment') == enrollment_metadata(value, source) and manifest['root'] == str(root) and manifest['root_identity'] == [os.fstat(fd).st_dev, os.fstat(fd).st_ino] and manifest['run_id'] == value['run_id'] and manifest['owner'] == value['owner'] and manifest['consumers'] == value['consumers'], 'enrollment manifest binding mismatch', Blocked)
        rc.verify_run_path(root, fd)
        return value, source, manifest, sha(raw)
    finally:
        os.close(fd)


@contextlib.contextmanager
def locked_run(value, capability=None, *, create=False):
    if capability is not None:
        require(isinstance(capability, rc.RunLock) and capability.root == Path(value['run']), 'wrong Run capability', Blocked)
        capability.verify()
        yield capability.root, capability.fd
        capability.verify()
    else:
        with rc.lifecycle_lock(Path(value['sejong_home']), Path(value['run']), create=create) as cap:
            yield cap.root, cap.fd


def enroll(request_path):
    import completion_hook as hook
    value, source = load_enrollment(request_path)
    try:
        # Creation of Run itself is explicit, not a recursive allocator/adopter.
        root, before = rc.open_run(Path(value['sejong_home']), Path(value['run']))
        try:
            require(set(os.listdir(before)) <= {rc.MANIFEST, rc.LOCK}, 'existing legacy contents cannot enroll', Blocked)
            rc.verify_run_path(root, before)
        finally:
            os.close(before)
        with rc.lifecycle_lock(Path(value['sejong_home']), Path(value['run']), create=True) as cap:
            root, fd = cap.root, cap.fd
            rc.storage_preflight(root, fd, [], Path(value['sejong_home']))
            names = set(os.listdir(fd))
            require(names <= {rc.MANIFEST, rc.LOCK}, 'existing legacy contents cannot enroll', Blocked)
            try:
                manifest = rc.decode(rc.read_file(fd, rc.MANIFEST, True)[0])
            except FileNotFoundError:
                manifest = None
            require(manifest is None or manifest.get('enrollment') == enrollment_metadata(value, source), 'old/changed bootstrap manifest cannot enroll', Blocked)
            manifest = rc.initialize_run(root, fd, value['run_id'], value['owner'], value['consumers'], enrollment_metadata(value, source), cap.binding())
            hook.register_session(Path(value['sejong_home']), value['session_id'], root, value['run_id'], value['owner'], Path(value['cwd']), value['record'], value['expect_session_binding_sha256'])
            _, _, _, current_hash = bound_enrollment(request_path)
        return dict(schema='company-native-storage-enrollment-result/v1', status='enrolled', sejong_home=value['sejong_home'], home_resolution=value['home_resolution'], run=value['run'], run_id=value['run_id'], owner=value['owner'], host=value['host'], session_id=value['session_id'], cwd=value['cwd'], cwd_resolved=value['cwd_resolved'], request=source, manifest_sha256=current_hash, readback_verified=True, identity_authentication='supplied observation; actual host provenance needs independent review')
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise Blocked('enrollment refused: ' + str(exc)) from exc


def artifact(value, enrollment, base):
    shape(value, ARTIFACT_KEYS, 'artifact')
    try:
        rc.parts(value['path'])
    except ValueError as exc:
        raise Invalid(str(exc)) from exc
    require(value['path'] != enrollment['record'], 'accepted record cannot self-snapshot')
    require(value['class'] in ('preserve', 'recreatable', 'unknown'), 'invalid artifact class')
    for key in ('owner', 'reason', 'origin'): text(value[key], key)
    require(value['owner'] == enrollment['owner'], 'artifact owner mismatch')
    require(set(strings(value['consumers'], 'artifact consumers')) <= set(enrollment['consumers']), 'undeclared consumer')
    text(value['next_use_or_recheck'], 'recheck', nullable=value['class'] != 'unknown')
    if value['class'] == 'recreatable':
        require(value['regeneration'] is not None, 'recreatable artifact needs regeneration proof')
    if value['regeneration'] is not None: pinned(value['regeneration'], base)
    return value


def classify(request_path):
    value, base, source = request(request_path, 'company-native-storage-classification/v1', ('schema', 'enrollment', 'expect_manifest_sha256', 'phase', 'artifacts'))
    return classify_value(value, base, source)


def classify_value(value, base, source, capability=None):
    ep, _ = pinned(value['enrollment'], base)
    enrollment, _, _, _ = bound_enrollment(ep)
    if capability is None:
        try:
            with rc.lifecycle_lock(Path(enrollment['sejong_home']), Path(enrollment['run'])) as cap:
                return classify_value(value, base, source, cap)
        except Invalid:
            # Strict caller errors keep public exit 2, even through acquisition.
            raise
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
            raise Blocked('classification refused: ' + str(exc)) from exc
    capability.verify()
    valid_hash(value['expect_manifest_sha256']); require(value['phase'] in ('reserve', 'freeze', 'absent'), 'invalid classification phase')
    require(isinstance(value['artifacts'], list) and bool(value['artifacts']), 'exact artifacts required')
    artifacts = [artifact(x, enrollment, base) for x in value['artifacts']]
    require(len({x['path'] for x in artifacts}) == len(artifacts), 'duplicate artifact')
    try:
        with locked_run(enrollment, capability) as (root, fd):
            _, _, manifest, current = bound_enrollment(ep)
            require(current == value['expect_manifest_sha256'], 'manifest compare-and-swap mismatch', Blocked)
            require(not any(os.path.lexists(root / x) for x in (rc.RECEIPT, rc.REJECTION)), 'completion freezes classification', Blocked)
            if os.path.lexists(root / enrollment['record']):
                active_record = rc.decode(rc.read_file(fd, enrollment['record'])[0])
                require(active_record.get('goal', {}).get('status') != 'succeeded' and 'artifact_retention' not in active_record, 'accepted record freezes classification', Blocked)
            rc.storage_preflight(root, fd, [row['path'] for row in artifacts] if value['phase'] == 'freeze' else [], Path(enrollment['sejong_home']))
            declarations = manifest.setdefault('creation_contract', {})
            if value['phase'] in ('freeze', 'absent'):
                rc.validate_launch_terminals(root, manifest)
            disposable, preserve = [], []
            for row in artifacts:
                ref = row['path']; prior = declarations.get(ref)
                if prior is not None:
                    require(prior['class'] == row['class'] or prior['class'] == 'recreatable' and row['class'] == 'preserve', 'preserve/unknown cannot downgrade', Blocked)
                    require(prior['owner'] == row['owner'] and prior['origin'] == row['origin'], 'creation provenance cannot change', Blocked)
                else:
                    require(value['phase'] == 'reserve', 'freeze requires prior reservation', Blocked)
                    require(not os.path.lexists(root / ref), 'creation reservation must precede file allocation', Blocked)
                    cursor = os.dup(fd)
                    try:
                        for part in rc.parts(ref)[:-1]:
                            try:
                                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=cursor)
                            except FileNotFoundError:
                                break
                            os.close(cursor); cursor = child
                            info = os.fstat(cursor)
                            require(info.st_uid == os.getuid() and not info.st_mode & 0o022, 'unsafe reservation parent', Blocked)
                    finally:
                        os.close(cursor)
                    require(not any(x['path'] == ref for x in [*manifest['disposable'], *manifest['preserve']]), 'existing binding cannot be adopted', Blocked)
                state = prior.get('state') if prior else 'reserved'
                if value['phase'] == 'absent':
                    optional = {p for c in manifest.get('launch_contract', {}).values() for p in c['optional']}
                    optional |= {c['receipt'] for result_ref, c in manifest.get('launch_contract', {}).items()
                                 if rc.decode(rc.read_file(fd, result_ref)[0]).get('launch_state') == 'not_started'}
                    require(prior is not None and state in ('reserved', 'absent') and ref in optional and
                            row['class'] == 'preserve' and row['origin'] == 'routing_launch.py' and
                            row['consumers'] == [] and not os.path.lexists(root / ref),
                            'terminal absence requires a supported unused optional output', Blocked)
                    declarations[ref] = {**row, 'state': 'absent'}
                    continue
                if prior and prior['class'] == 'recreatable' and row['class'] == 'preserve':
                    promoted = [x for x in manifest['disposable'] if x['path'] == ref]
                    if promoted:
                        require(rc.snapshot_file(fd, ref) == promoted[0], 'promotion original changed', Blocked)
                        manifest['disposable'] = [x for x in manifest['disposable'] if x['path'] != ref]
                        manifest['preserve'].extend(promoted)
                if value['phase'] == 'freeze':
                    require(not row['consumers'], 'freeze requires explicit no remaining consumers', Blocked)
                    if state != 'frozen':
                        (disposable if row['class'] == 'recreatable' else preserve).append(ref)
                    else:
                        binding = next(x for x in [*manifest['disposable'], *manifest['preserve']] if x['path'] == ref)
                        require(rc.snapshot_file(fd, ref) == binding, 'frozen original changed', Blocked)
                    state = 'frozen'
                declarations[ref] = {**row, 'state': state}
            if value['phase'] in ('freeze', 'absent'):
                rc.probe_activity(root)  # Closed immutable bytes, never a still-live writer snapshot.
            rc.register_declarations(fd, manifest, disposable, preserve)
            rc.validate_manifest(manifest)
            require(sha(rc.read_file(fd, rc.MANIFEST, True)[0]) == current, 'manifest changed during classification', Blocked)
            capability.verify()
            rc.write_metadata(fd, rc.MANIFEST, manifest)
            capability.verify()
            require(rc.decode(rc.read_file(fd, rc.MANIFEST, True)[0]) == manifest, 'classification readback failed', Blocked)
            return dict(schema='company-native-storage-classification-result/v1', status='reserved' if value['phase'] == 'reserve' else 'frozen', manifest_sha256=sha(rc.read_file(fd, rc.MANIFEST, True)[0]), artifacts=artifacts, readback_verified=True, source=source)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        raise Blocked('classification refused: ' + str(exc)) from exc


def reserve_producer(reference, paths, origin, capability=None):
    """Reserve a fixed producer inventory using actual enrollment and manifest CAS.

    Repeated reservation verifies existing live declarations; it never adopts
    allocated bytes or makes enrollment optional. Callers keep originals live
    until their own consumer settlement and final classification.
    """
    ep, _ = pinned(reference, Path.cwd())
    enrollment, _, manifest, current = bound_enrollment(ep)
    if capability is None:
        with rc.lifecycle_lock(Path(enrollment['sejong_home']), Path(enrollment['run'])) as cap:
            return reserve_producer(reference, paths, origin, cap)
    capability.verify()
    root = Path(enrollment['run'])
    if os.path.lexists(root / enrollment['record']):
        active = decode(regular(root / enrollment['record']))
        require(isinstance(active, dict) and isinstance(active.get('goal'), dict), 'producer canonical goal object required', Blocked)
        require(active['goal'].get('status') != 'succeeded' and 'artifact_retention' not in active, 'accepted record freezes classification', Blocked)
    rows = []
    for path in paths:
        path = lexical(str(Path(path).absolute()))
        require(path.is_relative_to(root), 'producer output outside enrolled Run', Blocked)
        ref = path.relative_to(root).as_posix()
        rc.parts(ref)
        try:
            rc.pins(capability.fd, ref)
        except FileNotFoundError:
            # pins inspected every existing ancestor before the first absent
            # directory; reservation does not allocate that future namespace.
            rc.pins(capability.fd)
        prior = manifest.get('creation_contract', {}).get(ref)
        if prior is not None:
            require(prior['origin'] == origin and prior['class'] == 'preserve' and prior['state'] == 'reserved' and prior['owner'] == enrollment['owner'], 'producer output is not its live retained declaration', Blocked)
        else:
            require(not os.path.lexists(path), 'producer reservation must precede allocation', Blocked)
            rows.append(dict(path=ref, **{'class': 'preserve'}, owner=enrollment['owner'], consumers=[], reason='retained producer original', origin=origin, regeneration=None, next_use_or_recheck='freeze after explicit producer and consumer settlement'))
    if rows:
        classify_value(dict(enrollment=reference, expect_manifest_sha256=current, phase='reserve', artifacts=rows), ep.parent, reference, capability)
    return enrollment


def settle_launch(request_path):
    """Observe exact consumer exit; synchronous worker-start return is not exit."""
    value, base, source = request(request_path, 'company-native-storage-launch-settlement/v1',
                                  ('schema', 'enrollment', 'result', 'expect_result_sha256', 'orca'))
    ep, _ = pinned(value['enrollment'], base)
    enrollment, _, _, _ = bound_enrollment(ep)
    rc.parts(value['result']); valid_hash(value['expect_result_sha256'])
    executable = lexical(value['orca'])
    with rc.lifecycle_lock(Path(enrollment['sejong_home']), Path(enrollment['run'])) as cap:
        _, _, manifest, _ = bound_enrollment(ep)
        require(value['result'] in manifest.get('launch_contract', {}), 'undeclared launch result', Blocked)
        raw = rc.read_file(cap.fd, value['result'])[0]
        require(sha(raw) == value['expect_result_sha256'], 'launch result CAS mismatch', Blocked)
        result = decode(raw)
        require(result.get('launch_state') == 'observed' and result.get('readback_status') == 'observed' and
                'consumer_settlement' not in result, 'unknown/already settled launch cannot be rewritten', Blocked)
        active = decode(rc.read_file(cap.fd, enrollment['record'])[0])
        require(active.get('goal', {}).get('status') != 'succeeded' and 'artifact_retention' not in active,
                'accepted record freezes launch settlement', Blocked)
        contract = manifest['launch_contract'][value['result']]
        require(manifest['creation_contract'][value['result']]['state'] == 'reserved', 'launch result already frozen', Blocked)
        start = decode(result['stdout'])['result']
        observed = subprocess.run([str(executable), 'orchestration', 'worker-show', '--dispatch', start['dispatchId'], '--full', '--json'],
                                  capture_output=True, text=True, timeout=30)
        envelope = decode(observed.stdout)
        require(observed.returncode == 0 and envelope.get('ok') is True, 'terminal host read failed', Blocked)
        result['consumer_settlement'] = envelope['result']
        dispatch = result['consumer_settlement'].get('dispatch', {})
        observation = result['consumer_settlement'].get('observation', {})
        incarnation = rc.launch_incarnation(start, result)
        require(incarnation and dispatch.get('processIncarnation') == incarnation and
                dispatch.get('id') == start['dispatchId'] and dispatch.get('taskId') == start['taskId'] and
                ('runId' not in start or dispatch.get('runId') == start['runId']) and
                (not result.get('full_readback') or start.get('terminal') is None or
                 dispatch.get('assigneeHandle') == start['terminal']) and
                dispatch.get('status') in ('completed', 'failed', 'cancelled') and
                observation.get('exactWorker') is True and observation.get('status') == 'exited',
                'exact consumer exit not proven', Blocked)
        require(sha(rc.read_file(cap.fd, contract['receipt'])[0]) == result['prelaunch_receipt_sha256'], 'launch receipt changed', Blocked)
        cap.verify()
        require(rc.read_file(cap.fd, value['result'])[0] == raw, 'result changed during exit observation', Blocked)
        from atomic_persistence import atomic_state
        atomic_state(cap.root / value['result'], result, cap)
        cap.verify()
        require(decode(rc.read_file(cap.fd, value['result'])[0]) == result, 'settlement readback mismatch', Blocked)
        return dict(schema='company-native-storage-launch-settlement-result/v1', status='settled', source=source,
                    result=value['result'], result_sha256=sha(rc.read_file(cap.fd, value['result'])[0]), readback_verified=True)


def _closeout(request_path):
    value, base, _ = request(request_path, 'company-native-storage-closeout-request/v1', ('schema', 'enrollment', 'sejong_home', 'session_id', 'cwd', 'run', 'run_id', 'owner', 'record', 'trigger'))
    for key in ('sejong_home', 'cwd', 'run'): lexical(value[key])
    for key in ('session_id', 'run_id', 'owner'): text(value[key], key)
    rc.parts(value['record'])
    result: dict = dict(schema='company-native-storage-closeout/v1', sejong_home=value['sejong_home'], run=value['run'], run_id=value['run_id'], owner=value['owner'], session_id=value['session_id'], cwd=value['cwd'], enrollment='not_enrolled', trigger=dict(mode='unknown', observed=False, evidence=None), status='not_enrolled', reason='exact_enrollment_not_supplied', receipt=None, removed_files=None, removed_logical_bytes=None, readback_verified=False, retained_files=None, unknown_files=None, pending=dict(owner=value['owner'], recheck='supply exact enrollment and observe result'))
    if value['enrollment'] is None:
        return result
    ep, _ = pinned(value['enrollment'], base)
    try:
        import completion_hook as hook
        intake, _ = load_enrollment(ep)
        for key in ('sejong_home', 'run', 'run_id', 'owner', 'record', 'session_id', 'cwd'):
            require(value[key] == intake[key], 'closeout identity mismatch: ' + key, Blocked)
        try:
            regular(hook.binding_path(intake['sejong_home'], intake['session_id']))
        except FileNotFoundError:
            result['reason'] = 'exact_session_binding_absent'
            return result
        enrollment, source, manifest, manifest_hash = bound_enrollment(ep)
        for key in ('sejong_home', 'run', 'run_id', 'owner', 'record', 'session_id', 'cwd'):
            require(value[key] == enrollment[key], 'closeout identity mismatch: ' + key, Blocked)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result.update(status='blocked', reason=str(exc)); return result
    result.update(enrollment='enrolled', status='unknown', reason='result_not_observed')
    if value['trigger'] is not None:
        _, raw = pinned(value['trigger'], base); trigger = shape(decode(raw), ('mode', 'host', 'event', 'session_id', 'cwd'), 'trigger observation')
        require(trigger['session_id'] == value['session_id'] and trigger['cwd'] == value['cwd'], 'trigger identity mismatch')
        require(trigger['mode'] in ('automatic', 'explicit'), 'invalid trigger mode')
        result['trigger'] = dict(mode=trigger['mode'], observed=True, evidence=value['trigger'])
        if trigger['mode'] == 'automatic' and (trigger['host'] != 'codex_stop' or enrollment['host'] != 'codex_stop'):
            result.update(status='skipped', reason='unsupported_automatic_trigger', removed_files=0, removed_logical_bytes=0); return result
        if trigger['mode'] == 'automatic' and trigger['event'] != 'Stop':
            result.update(status='skipped', reason='not_Stop', removed_files=0, removed_logical_bytes=0); return result
    root, fd = rc.open_run(Path(value['sejong_home']), Path(value['run']))
    try:
        receipts = {}
        # A separately validated hook observation survives a corrupt action
        # receipt. Never let an unvalidated receipt overwrite that provenance.
        for name in (rc.HOOK_RECEIPT, rc.REJECTION, rc.RECEIPT):
            try:
                raw, binding = rc.read_file(fd, name, True)
            except FileNotFoundError:
                continue
            receipts[name] = (rc.decode(raw), binding)
            if name == rc.HOOK_RECEIPT:
                h = receipts[name][0]
                same_run = h.get('run_id') == value['run_id']
                skipped_hook = (same_run and h.get('session_id') == value['session_id'] and
                                h.get('status') == 'skipped' and h.get('reason') in
                                ('unsupported_automatic_trigger', 'Run unfinished, failed or no accepted record'))
                bound_hook = (same_run and h.get('format') == 'company-run-completion/v1' and
                              h.get('manifest_sha256') == manifest_hash and
                              h.get('record') == rc.read_file(fd, value['record'])[1] and
                              h.get('hook', {}).get('event') == 'Stop' and
                              h.get('hook', {}).get('session_id') == value['session_id'] and
                              h.get('trigger', {}).get('mode') == 'codex_stop' and
                              h.get('status') in ('blocked', 'completed'))
                if skipped_hook or bound_hook:
                    result['trigger'] = dict(mode='codex_stop', observed=True, evidence=dict(path=str(root / name), sha256=binding['sha256']))
        if not receipts: return result

        if rc.RECEIPT not in receipts:
            name = rc.REJECTION if rc.REJECTION in receipts else rc.HOOK_RECEIPT
            r, b = receipts[name]
            require(r.get('run_id') == value['run_id'], 'receipt Run provenance mismatch', Blocked)
            result['receipt'] = dict(path=str(root / name), sha256=b['sha256'])
            if (r.get('format') == 'company-run-completion/v1' and r.get('manifest_sha256') == manifest_hash and
                    r.get('trigger', {}).get('mode') in ('explicit_lead', 'codex_stop', 'direct_complete')):
                result['trigger'] = dict(mode=r['trigger']['mode'], observed=True, evidence=result['receipt'])
            if r.get('status') == 'skipped' and r.get('session_id') == value['session_id']:
                result.update(status='skipped', reason=r.get('reason'), removed_files=0, removed_logical_bytes=0, readback_verified=True)
            elif r.get('status') == 'blocked':
                result.update(status='blocked', reason='; '.join(r.get('errors', ['completion blocked'])))
            return result
        r, b = receipts[rc.RECEIPT]
        result['receipt'] = dict(path=str(root / rc.RECEIPT), sha256=b['sha256'])
        record_raw, record_binding = rc.read_file(fd, value['record'])
        require(r.get('format') == 'company-run-completion/v1' and r.get('run_id') == value['run_id'] and r.get('manifest_sha256') == manifest_hash and r.get('record') == record_binding and r.get('status') in ('blocked', 'completed'), 'completion receipt provenance mismatch', Blocked)
        removed = r.get('removed')
        require(isinstance(removed, list) and removed == manifest['disposable'][:len(removed)], 'invalid removed prefix', Blocked)
        if r['status'] == 'completed':
            rc.validate_receipt(r, manifest, manifest_hash, record_binding)
        rc.validate_acceptance(rc.decode(record_raw), root / value['record'], manifest, manifest_hash, require_routing=manifest.get('routing_accounting') == 'required')
        rc.storage_preflight(root, fd, [])
        for item in manifest['preserve']:
            require(rc.snapshot_file(fd, item['path']) == item, 'preserved readback mismatch', Blocked)
        for item in removed:
            require(not os.path.lexists(root / item['path']), 'deleted path reappeared; refusing retry', Blocked)
        rc.verify_run_path(root, fd)
        if r.get('trigger', {}).get('mode') in ('explicit_lead', 'codex_stop', 'direct_complete'):
            result['trigger'] = dict(mode=r['trigger']['mode'], observed=True, evidence=result['receipt'])
        result.update(removed_files=len(removed), removed_logical_bytes=sum(x['identity'][2] for x in removed), readback_verified=True, retained_files=len(manifest['preserve']))
        newer = [v for k, v in receipts.items() if k != rc.RECEIPT and v[1]['identity'][3] >= b['identity'][3] and v[0].get('status') == 'blocked']
        if newer:
            result.update(status='blocked', reason='; '.join(newer[-1][0].get('errors', ['newer completion rejection'])))
        elif r['status'] == 'completed':
            result.update(status='removed' if removed else 'skipped', reason='verified_completed_receipt' if removed else 'no_disposable', pending=None)
        else:
            result.update(status='blocked', reason='partial_completion_requires_owner_recovery')
        return result
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result.update(status='blocked', reason=str(exc), readback_verified=False)
        return result
    finally:
        os.close(fd)


def final_summary(result):
    """A projection of validated observations, never action/acceptance authority."""
    count, size = result.get('removed_files'), result.get('removed_logical_bytes')
    removed = 'unknown' if count is None or size is None else f'{count} files/{size} logical bytes'
    receipt = result.get('receipt')
    reference = 'unknown' if receipt is None else receipt['path'] + '#sha256=' + receipt['sha256']
    trigger = result.get('trigger', {})
    mode = trigger.get('mode', 'unknown')
    provenance = 'prior receipt; not a new invocation' if receipt is not None else 'no action receipt observed'
    pending = result.get('pending')
    followup = '' if pending is None else '; pending_owner=' + str(pending.get('owner')) + '; recheck=' + str(pending.get('recheck'))
    return ('Storage: home=' + str(result.get('sejong_home', 'unknown')) +
        '; enrollment=' + str(result.get('enrollment', 'not_applicable_maintenance')) +
        '; trigger=' + str(mode) + ' (' + provenance + ')' +
        '; status=' + str(result.get('status', 'unknown')) + '; removed=' + removed +
        '; receipt=' + reference + '; reason=' + str(result.get('reason', 'unknown')) + followup)


def closeout(request_path):
    result = _closeout(request_path)
    result['final_summary'] = final_summary(result)
    return result


def maintenance_closeout(request_path):
    import native_maintenance
    result = native_maintenance.closeout(request_path)
    result['final_summary'] = final_summary(result)
    return result
