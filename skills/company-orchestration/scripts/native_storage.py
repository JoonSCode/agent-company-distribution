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
                               require, sha, shape, text, valid_hash)

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
    """Descriptor-relative walk: no linked directories, devices or broad discovery."""
    rows = []
    def visit(handle, prefix='', depth=0):
        require(depth <= 64 and len(rows) <= 100000, 'inventory limit reached', Blocked)
        before = os.fstat(handle)
        for name in sorted(os.listdir(handle)):
            ref = prefix + name
            st = os.stat(name, dir_fd=handle, follow_symlinks=False)
            if name == '.git':
                blockers.append('source/worktree metadata present')
                rows.append({'path': ref, 'category': 'protected', 'bytes': None, 'identity': rc.signature(st)})
                continue
            if stat.S_ISDIR(st.st_mode):
                if st.st_uid != os.getuid() or st.st_mode & 0o022:
                    blockers.append('shared/non-owned directory protected: ' + ref)
                    rows.append({'path': ref, 'category': 'protected', 'bytes': None, 'identity': rc.signature(st)})
                    continue
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=handle)
                try:
                    require((os.fstat(child).st_dev, os.fstat(child).st_ino) == (st.st_dev, st.st_ino),
                            'directory replaced during inventory', Blocked)
                    visit(child, ref + '/', depth + 1)
                finally:
                    os.close(child)
                continue
            safe = stat.S_ISREG(st.st_mode) and st.st_nlink == 1 and st.st_uid == os.getuid() and not st.st_mode & 0o022
            category = ('protected' if not safe or ref in protected else
                        'preserved' if ref in preserved else
                        'declared_disposable' if ref in declared else 'unknown')
            if not safe and ref in declared:
                blockers.append('unsafe/shared/non-owned disposable file: ' + ref)
            rows.append({'path': ref, 'category': category, 'bytes': st.st_size if safe else None,
                         'identity': rc.signature(st)})
        after = os.fstat(handle)
        require(rc.signature(before) == rc.signature(after), 'directory changed during inventory', Blocked)
    visit(fd)
    return rows


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
                        '--record', value['record'], '--expect-manifest-sha256', saved['manifest_sha256']])
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
