#!/usr/bin/env python3
"""Company-owned Run lifecycle: declared retention, accepted completion, cleanup.

No historical sweep, inferred filenames or recursive deletion. The lead or a
registered Stop callback can complete only an accepted Run. Stdlib Python 3.13+.
"""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import uuid

# Select Python's normal cache prefix before importing Company modules.
# Restrict this to the CLI process; callers importing a module are unchanged.
if __name__ == "__main__":
    import os as _os
    import sys as _sys
    _sys.pycache_prefix = _os.path.join(_os.path.abspath(_os.path.expanduser("~")), ".cache", "agent-company", "python")

sys.dont_write_bytecode = True
from record_check import check_record, unique_object, invalid_constant

FORMAT = 'company-run-retention/v1'
MANIFEST = 'retention-manifest.json'
RECEIPT = 'completion-receipt.json'
LOCK = '.completion.lock'
REJECTION = 'completion-rejection.json'
HOOK_RECEIPT = 'completion-hook-receipt.json'
RESERVED = {MANIFEST, RECEIPT, LOCK, REJECTION, HOOK_RECEIPT}


def default_home():
    if explicit := os.environ.get('SEJONG_HOME'):
        return Path(explicit).expanduser()
    codex = Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex').expanduser()
    # Orca can expose the canonical package through a shared skills link while
    # keeping its own CODEX_HOME. Producer and Stop must use the same Run store.
    package = Path(__file__).resolve().parents[1]
    installed = package.parent.parent
    caller_package = codex / 'skills/company-orchestration'
    standard_orca = Path.home() / 'Library/Application Support/orca/codex-runtime-home/home'
    canonical_callback = (installed == Path.home() / '.codex' and codex == standard_orca and
                          not caller_package.exists())
    if (package.parent.name == 'skills' and
            (installed / 'agent-company/active.json').is_file() and
            (caller_package.resolve() == package or canonical_callback)):
        codex = installed
    return codex / 'sejong'


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def validate_manifest(manifest):
    require(manifest.get('format') == FORMAT, 'unknown manifest format')
    if 'routing_accounting' in manifest:
        require(manifest.get('routing_accounting') == 'required', 'unsupported manifest routing accounting')
    for name in ('run_id', 'owner', 'root'):
        require(isinstance(manifest.get(name), str) and manifest[name], 'missing manifest ' + name)
    consumers = manifest.get('consumers')
    require(isinstance(consumers, list) and all(isinstance(x, str) and x for x in consumers)
            and len(set(consumers)) == len(consumers), 'invalid consumer inventory')
    refs = set()
    for key in ('disposable', 'preserve'):
        require(isinstance(manifest.get(key), list), 'missing declaration: ' + key)
        for binding in manifest[key]:
            require(isinstance(binding, dict), 'invalid file binding')
            parts(binding.get('path'))
            require(binding['path'] not in refs, 'duplicate/conflicting file binding')
            refs.add(binding['path'])
            digest = binding.get('sha256')
            require(isinstance(digest, str) and len(digest) == 64 and all(x in '0123456789abcdef' for x in digest),
                    'invalid file hash')
            identity = binding.get('identity')
            require(isinstance(identity, list) and len(identity) == 5 and
                    all(type(x) is int and x >= 0 for x in identity), 'invalid file identity')
    if 'enrollment' in manifest:
        e = manifest['enrollment']
        require(isinstance(e, dict) and set(e) == {'request', 'sejong_home', 'host', 'session_id', 'cwd', 'cwd_resolved', 'record'}, 'invalid enrollment extension')
        require(e['host'] in ('codex_stop', 'explicit_lead') and all(isinstance(e[k], str) and e[k] for k in ('sejong_home', 'session_id', 'cwd', 'cwd_resolved', 'record')), 'invalid enrollment identity')
        parts(e['record'])
        require(isinstance(e['request'], dict) and set(e['request']) == {'path', 'sha256'} and len(e['request']['sha256']) == 64, 'invalid enrollment source')
    if 'coordination' in manifest:
        coordination = manifest['coordination']
        require(isinstance(coordination, dict) and set(coordination) == {'role', 'root_identity', 'lock_identity'} and
                coordination['role'] == 'run-lifecycle/v1' and coordination['root_identity'] == manifest['root_identity'] and
                isinstance(coordination['lock_identity'], list) and len(coordination['lock_identity']) == 5 and
                all(type(x) is int and x >= 0 for x in coordination['lock_identity']), 'invalid lifecycle coordination binding')
    if 'launch_contract' in manifest:
        require('coordination' in manifest and isinstance(manifest['launch_contract'], dict), 'launch contract requires enrolled coordination')
        for ref, row in manifest['launch_contract'].items():
            parts(ref)
            require(isinstance(row, dict) and set(row) == {'receipt', 'attempt_binding', 'optional'} and isinstance(row['attempt_binding'], dict), 'invalid launch contract')
            parts(row['receipt'])
            require(ref != row['receipt'] and isinstance(row['optional'], list) and len(set(row['optional'])) == len(row['optional']), 'invalid launch output inventory')
            allowed = {ref + '.catalog-refresh/' + name for name in ('status.json', 'response-1.json', 'response-2.json', 'manifest.json', 'failure.json')}
            require(set(row['optional']) <= allowed, 'unsupported optional launch output')
            for output in [ref, row['receipt'], *row['optional']]:
                declaration = manifest.get('creation_contract', {}).get(output, {})
                require(declaration.get('origin') == 'routing_launch.py' and declaration.get('class') == 'preserve', 'launch original not declared retained')
    if 'creation_contract' in manifest:
        require('enrollment' in manifest and isinstance(manifest['creation_contract'], dict), 'creation contract requires enrollment')
        disposable = {x['path'] for x in manifest['disposable']}
        preserved = {x['path'] for x in manifest['preserve']}
        for ref, row in manifest['creation_contract'].items():
            parts(ref)
            require(isinstance(row, dict) and set(row) == {'path', 'class', 'owner', 'consumers', 'reason', 'origin', 'regeneration', 'next_use_or_recheck', 'state'} and row['path'] == ref, 'invalid creation declaration')
            require(row['class'] in ('preserve', 'recreatable', 'unknown') and row['state'] in ('reserved', 'frozen', 'absent') and row['owner'] == manifest['owner'], 'invalid creation class/owner/state')
            require(row['class'] == 'recreatable' or ref not in disposable, 'retained creation artifact declared disposable')
            require(ref != manifest['enrollment']['record'], 'record cannot self-snapshot')
            require(row['state'] != 'frozen' or ref in disposable | preserved, 'frozen binding missing')
            require(ref not in disposable or row['state'] == 'frozen' and row['regeneration'] is not None and row['consumers'] == [], 'live/unproven creation artifact cannot be disposable')
            require(row['state'] != 'absent' or row['class'] == 'preserve' and row['consumers'] == [] and ref not in disposable | preserved,
                    'invalid terminal absence')


def decode(data):
    value = json.loads(data, object_pairs_hook=unique_object, parse_constant=invalid_constant)
    require(isinstance(value, dict), 'metadata must be an object')
    return value


def parts(ref):
    require(isinstance(ref, str) and ref and '\x00' not in ref, 'invalid relative path')
    p = Path(ref)
    require(not p.is_absolute() and all(x not in ('', '.', '..') for x in ref.split('/')),
            'path escape/noncanonical path: ' + ref)
    require(not (set(p.parts) & RESERVED), 'reserved path: ' + ref)
    return p.parts


@contextmanager
def parent_fd(root_fd, ref):
    components = parts(ref)
    fd = os.dup(root_fd)
    try:
        for part in components[:-1]:
            new = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = new
        yield fd, components[-1]
    finally:
        os.close(fd)


def read_file(root_fd, ref, metadata=False, content=True):
    if metadata:
        require(ref in RESERVED, 'unknown metadata path')
        fd = os.open(ref, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=root_fd)
    else:
        with parent_fd(root_fd, ref) as (parent, name):
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1,
                'only singly linked regular files supported: ' + ref)
        digest = hashlib.sha256()
        data = b''
        if content:
            require(before.st_size <= 16 * 1024 * 1024, 'compact metadata exceeds 16 MiB: ' + ref)
            data = stream.read(16 * 1024 * 1024 + 1)
            require(len(data) <= 16 * 1024 * 1024, 'metadata grew beyond limit: ' + ref)
            digest.update(data)
        else:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
        after = os.fstat(stream.fileno())
        require(signature(before) == signature(after), 'changed while reading: ' + ref)
    return data, {'path': ref, 'sha256': digest.hexdigest(), 'identity': signature(after)}


def snapshot_file(fd, ref):
    return read_file(fd, ref, content=False)[1]


def signature(st):
    return [st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns]


def write_metadata(fd, name, value):
    tmp = '.completion-write-' + uuid.uuid4().hex
    handle = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
    try:
        with os.fdopen(handle, 'w') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        # Never follow a metadata link, including on replacement.
        try:
            require(stat.S_ISREG(os.stat(name, dir_fd=fd, follow_symlinks=False).st_mode),
                    'metadata replacement is not a regular file')
        except FileNotFoundError:
            pass
        os.replace(tmp, name, src_dir_fd=fd, dst_dir_fd=fd)
        os.fsync(fd)
    finally:
        try:
            os.unlink(tmp, dir_fd=fd)
        except FileNotFoundError:
            pass


def open_run(home, run):
    # Reject every link in the declared namespace, rather than resolving it away.
    base = Path(os.path.abspath(home)) / 'runs'
    root = Path(os.path.abspath(run))
    relative = root.relative_to(base)
    require(relative.parts, 'runs root is not a Run')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in root.parts[1:]:
            new = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = new
        return root, fd
    except BaseException:
        os.close(fd)
        raise


def verify_run_path(root, fd):
    cursor = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in root.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=cursor)
            os.close(cursor)
            cursor = child
        actual, expected = os.fstat(cursor), os.fstat(fd)
        require((actual.st_dev, actual.st_ino) == (expected.st_dev, expected.st_ino),
                'Run directory moved/replaced')
    finally:
        os.close(cursor)


class RunLock:
    """A held, descriptor-relative capability, never a reentrant lock switch.

    The enrollment pins the stable lock inode. Atomic result/manifest replacement
    cannot replace this coordination resource. Every borrower verifies the exact
    capability, namespace and owning process rather than opening another flock.
    """
    def __init__(self, root, fd, lock):
        self.root, self.fd, self.lock = root, fd, lock
        self.pid, self.held = os.getpid(), False
        self.namespace = self._namespace()
        self.identity = self._identity(os.fstat(lock))

    @staticmethod
    def _identity(st):
        require(stat.S_ISREG(st.st_mode) and st.st_nlink == 1 and
                st.st_uid == os.getuid() and not st.st_mode & 0o077,
                'unsafe lifecycle lock')
        return [st.st_dev, st.st_ino, st.st_uid, st.st_mode, st.st_nlink]

    def _namespace(self):
        cursor = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
        result = []
        try:
            for part in self.root.parts[1:]:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=cursor)
                os.close(cursor); cursor = child
                st = os.fstat(cursor)
                require(st.st_uid in (0, os.getuid()) and not st.st_mode & 0o022,
                        'unsafe lifecycle namespace')
                result.append([st.st_dev, st.st_ino, st.st_uid, st.st_mode])
            return result
        finally:
            os.close(cursor)

    def verify(self, held=True):
        require(self.pid == os.getpid() and (self.held or not held), 'lifecycle capability not held by this process')
        verify_run_path(self.root, self.fd)
        require(self._namespace() == self.namespace, 'lifecycle ancestor changed')
        require(self._identity(os.fstat(self.lock)) == self.identity and
                self._identity(os.stat(LOCK, dir_fd=self.fd, follow_symlinks=False)) == self.identity,
                'lifecycle lock moved/replaced')
        try:
            manifest = decode(read_file(self.fd, MANIFEST, True)[0])
        except FileNotFoundError:
            manifest = {}
        if 'coordination' in manifest:
            require(manifest['coordination'] == self.binding(), 'enrolled lifecycle lock identity changed')
        elif 'enrollment' in manifest:
            raise ValueError('enrolled Run lacks stable coordination binding; owner recovery required')
        return self

    def binding(self):
        st = os.fstat(self.fd)
        return dict(role='run-lifecycle/v1', root_identity=[st.st_dev, st.st_ino], lock_identity=self.identity)


@contextmanager
def lifecycle_lock(home, run, *, create=False):
    root, fd = open_run(home, run)
    lock = None
    cap = None
    try:
        if create and not os.path.lexists(root / LOCK) and os.path.lexists(root / MANIFEST):
            require('enrollment' not in decode(read_file(fd, MANIFEST, True)[0]), 'missing enrolled lifecycle lock; owner recovery required')
        lock = os.open(LOCK, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK |
                       (os.O_CREAT if create else 0), 0o600, dir_fd=fd)
        cap = RunLock(root, fd, lock)
        cap.verify(held=False)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        cap.held = True
        cap.verify()
        yield cap
    finally:
        if cap is not None: cap.held = False
        if lock is not None: os.close(lock)
        os.close(fd)


def pins(fd, ref=None):
    # Path-local pins/activity markers. No historical/home scan.
    def inspect(handle, root=False):
        for name in os.listdir(handle):
            if name in {'.pin', '.keep', '.active', 'PIN', 'KEEP'} or (
                (name != LOCK or not root) and (name.endswith('.lock') or name.endswith('.pid'))
            ):
                raise ValueError('pin/activity marker: ' + name)
    inspect(fd, root=True)
    if ref:
        cursor = os.dup(fd)
        try:
            for part in parts(ref)[:-1]:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=cursor)
                os.close(cursor)
                cursor = child
                inspect(cursor)
        finally:
            os.close(cursor)


def probe_activity(root, exact=None):
    # Fixed OS-owned paths only: never discover a replacement through PATH.
    executable = {'darwin': '/usr/sbin/lsof', 'linux': '/usr/bin/lsof'}.get(sys.platform)
    if executable is None:
        raise ValueError('open-file observation unsupported platform: ' + sys.platform)
    scope = [str(exact)] if exact is not None else ['+D', str(root)]
    result = subprocess.run([executable, '-nP', '-Fpn', *scope],
                            capture_output=True, text=True, timeout=30)
    require(result.returncode in (0, 1) and not result.stderr.strip(),
            'open-file observation failed: ' + result.stderr.strip())
    # lsof may return 1 even with own directory fields; parse both valid exits.
    # Empty success or malformed output must never become quiescence.
    require((result.returncode == 1 and result.stdout == '') or
            (bool(result.stdout) and result.stdout.endswith('\n')),
            'malformed open-file observation')
    # This process holds only the Run/ancestor directories and own lock.
    current = None
    observed_name = False
    pending_file = False
    for line in result.stdout.split('\n')[:-1]:
        require(bool(line) and '\x00' not in line, 'malformed open-file observation field')
        if line.startswith('p'):
            require((current is None or observed_name) and line[1:].isascii() and
                    line[1:].isdecimal() and int(line[1:]) > 0,
                    'malformed open-file observation process')
            current = line[1:]
            observed_name = False
        elif line.startswith('f'):
            # lsof emits file-set delimiters even when only -Fpn is requested.
            require(current is not None and bool(line[1:]) and not pending_file,
                    'malformed open-file observation file')
            pending_file = True
            observed_name = False
        elif line.startswith('n'):
            name = line[1:]
            require(current is not None and bool(name), 'malformed open-file observation name')
            observed_name = True
            pending_file = False
            own_directory = False
            try:
                Path(name).relative_to(root)
                own_directory = stat.S_ISDIR(Path(name).lstat().st_mode)
            except (OSError, ValueError):
                pass
            require(current == str(os.getpid()) and (name == str(root / LOCK) or own_directory),
                    'open activity: ' + line)
        else:
            raise ValueError('malformed open-file observation field')
    require(not result.stdout or observed_name, 'malformed open-file observation missing name')
    return {'tool': 'lsof exact file' if exact is not None else 'lsof scoped +D',
            'status': 'no external open paths'}


def validate_acceptance(record, record_path, manifest, manifest_hash, require_routing=False):
    # A manifest CAS cannot promote live reservations to final evidence. This
    # check is independent of incidental activity markers or current lsof output.
    for ref, row in manifest.get('creation_contract', {}).items():
        require(row.get('state') in ('frozen', 'absent') and row.get('consumers') == [],
                'creation contract unfinished: ' + ref)
        if row['state'] == 'absent':
            require(not os.path.lexists(record_path.parent / ref), 'terminal absence reappeared: ' + ref)
    validate_launch_terminals(record_path.parent, manifest)
    checked = check_record(record, record_path.parent, require_routing=require_routing)
    require(checked['ok'], 'record contradictions: ' + json.dumps(checked['errors']))
    policy = checked.get('measurement', {}).get('policy')
    require(policy is None or policy['success_eligible'],
            'accounting complete but success-only completion refused: ' +
            (policy['verdict'] if policy else 'unknown'))
    require(record.get('label') == 'real' and record.get('resource_accounting') == 'required',
            'real resource-accounted record required')
    goal = record['goal']
    require(goal['status'] == 'succeeded' and goal['id'] == manifest['run_id']
            and goal['current_owner'] == manifest['owner'], 'exact completed Run/owner required')
    assessment = goal.get('assessment') or {}
    require(assessment.get('verdict') == 'succeeded' and assessment.get('basis') in ('human', 'independent'),
            'overall accepted success required')
    evidence = record['evidence'].get(assessment.get('evidence'), {})
    require(evidence.get('file') and evidence.get('sha256'), 'actual acceptance evidence bytes required')
    study_tasks = accepted_study_tasks(record, record_path.parent, manifest['preserve'])
    for task in record['tasks']:
        if task['id'] in study_tasks:
            continue
        require(task['execution']['state'] == 'settled' and
                task['execution']['result']['outcome'] == 'succeeded' and
                (task.get('technical') or {}).get('verdict') == 'passed' and
                (task.get('parent_integration') or {}).get('verdict') == 'passed',
                'all current tasks must be accepted and integrated')
    contract = record.get('artifact_retention', {})
    require(contract.get('run_id') == manifest['run_id'] and
            contract.get('manifest_sha256') == manifest_hash and contract.get('quiescent') is True,
            'stale/missing retention acceptance binding')
    require(contract.get('consumers') == [{'id': c, 'state': 'settled'} for c in manifest['consumers']],
            'consumer settlement mismatch')
    if record.get('measurement', {}).get('version') == 2:
        from measurement_lifecycle import retained_files
        require('measurement-v2' in manifest['consumers'], 'measurement retention consumer required')
        preserved = {item['path']: item['sha256'] for item in manifest['preserve']}
        for path, sha256 in retained_files(record, record_path.parent):
            try:
                relative = path.relative_to(record_path.parent.resolve()).as_posix()
            except ValueError:
                raise ValueError('measurement ledger must be inside retained Run')
            require(preserved.get(relative) == sha256, 'measurement evidence not preserved: ' + relative)
    return checked


def validate_launch_terminals(root, manifest):
    """Start return is not exit. Unknown/pending cannot be frozen or accepted."""
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        return _validate_launch_terminals(root, descriptor, manifest)
    finally:
        os.close(descriptor)


def launch_incarnation(start, result):
    """Retain the start value, or use an identity-bound saved full readback."""
    original = start.get('processIncarnation') or start.get('prompt', {}).get('processIncarnation')
    full = result.get('full_readback')
    if full is None:
        return original
    if not isinstance(full, dict) or full.get('status') != 'observed' or full.get('exit_code') != 0:
        return None
    try:
        envelope = decode(full['stdout'])
        dispatch = envelope['result']['dispatch']
        worker = envelope['result']['worker']
        if (envelope.get('ok') is not True or
                not all(isinstance(start.get(k), str) and start[k] for k in ('runId', 'taskId', 'dispatchId')) or
                dispatch.get('id') != start['dispatchId'] or dispatch.get('taskId') != start['taskId'] or
                dispatch.get('runId') != start['runId'] or worker.get('dispatchId') != start['dispatchId'] or
                (start.get('terminal') is not None and
                 (dispatch.get('assigneeHandle') != start['terminal'] or
                  envelope['result'].get('terminal', {}).get('handle') != start['terminal']))):
            return None
        value = dispatch.get('processIncarnation')
        if not isinstance(value, str) or not value or (original and original != value):
            return None
        return value
    except (ValueError, KeyError, TypeError, AttributeError):
        return None


def _validate_launch_terminals(root, descriptor, manifest):
    verify_run_path(root, descriptor)
    for result_ref, contract in manifest.get('launch_contract', {}).items():
        parts(result_ref); parts(contract['receipt'])
        value = decode(read_file(descriptor, result_ref)[0])
        if value.get('launch_state') == 'not_started':
            require(not os.path.lexists(root / contract['receipt']), 'pre-host receipt needs owner reconciliation')
            continue
        require(value.get('launch_state') == 'observed' and value.get('readback_status') == 'observed',
                'launch outcome unknown/pending: ' + result_ref)
        require(sha(read_file(descriptor, contract['receipt'])[0]) == value.get('prelaunch_receipt_sha256'), 'launch receipt changed')
        start = decode(value['stdout'])['result']
        settlement = value.get('consumer_settlement', {})
        terminal = settlement.get('observation', {})
        dispatch = settlement.get('dispatch', {})
        incarnation = launch_incarnation(start, value)
        require(incarnation and dispatch.get('processIncarnation') == incarnation and
                terminal.get('exactWorker') is True and terminal.get('status') == 'exited' and
                dispatch.get('id') == start['dispatchId'] and dispatch.get('taskId') == start['taskId'] and
                ('runId' not in start or dispatch.get('runId') == start['runId']) and
                (not value.get('full_readback') or start.get('terminal') is None or
                 dispatch.get('assigneeHandle') == start['terminal']) and
                dispatch.get('status') in ('completed', 'failed', 'cancelled'),
                'exact exited launch consumer not settled: ' + result_ref)


def accepted_study_tasks(record, base, preserved):
    """Only a complete, accepted saved feasibility deliverable may retain failed trials.

    This checks captured bytes, never executes an oracle or changes trial outcomes.
    Every other Task still uses the ordinary production completion gate.
    """
    if 'study_completion' not in record:
        return set()
    import outcome_eval as outcome
    contract = record['study_completion']
    outcome.shape(contract, {'mode', 'plan', 'report', 'trials'}, 'study completion')
    require(contract['mode'] == 'accepted_study', 'unsupported study completion mode')
    evidence = record['evidence']
    # Keep all frozen inputs/results in the ordinary protected evidence inventory.
    files = {item['file']: item['sha256'] for item in evidence.values() if item.get('file')}
    frozen = {item['path']: item['sha256'] for item in preserved}

    def read(reference):
        outcome.shape(reference, {'path', 'sha256'}, 'study evidence')
        require(files.get(reference['path']) == reference['sha256'], 'study evidence must be retained in record')
        require(frozen.get(reference['path']) == reference['sha256'], 'study evidence must be frozen for retention')
        fd = os.open(base, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            data, binding = read_file(fd, reference['path'])
        finally:
            os.close(fd)
        require(binding['sha256'] == reference['sha256'], 'study evidence changed')
        return data

    refs = []
    for key in ('plan', 'report'):
        item = evidence.get(contract[key], {})
        require(item.get('file') and item.get('sha256'), 'study ' + key + ' evidence bytes required')
        refs.append({'path': item['file'], 'sha256': item['sha256']})
    plan_ref, report_ref = refs
    plan_path = base / plan_ref['path']
    read(plan_ref)
    bundle, plan = outcome.load_plan(plan_path, plan_ref['sha256'])
    require(plan['evidence_class'] == 'real', 'real study required')
    prefix = Path(plan_ref['path']).parent

    def bound(reference):
        return read({'path': (prefix / reference['path']).as_posix(), 'sha256': reference['sha256']})

    for reference in [plan['common']['context'], *plan['arms'].values()]:
        bound(reference)
    report = decode(read(report_ref))
    outcome.shape(report, {'format', 'evidence_class', 'plan_sha256', 'study', 'planned_attempts',
                          'observed_attempts', 'missing_trials', 'critical_failure_trials', 'trials',
                          'arms', 'gate', 'quality', 'user_burden', 'tokens', 'comparison', 'limits'},
                  'saved study report')
    expected = {trial['id']: trial for trial in plan['expected_trials']}
    mapping = contract['trials']
    require(isinstance(mapping, dict) and set(mapping) == set(expected) and
            all(isinstance(x, str) and x for x in mapping.values()) and
            len(set(mapping.values())) == len(mapping), 'missing/duplicate study trial mapping')
    require(report.get('format') == outcome.VERSION and report.get('study') == 'feasibility' and
            report.get('evidence_class') == 'real' and report.get('plan_sha256') == plan_ref['sha256'] and
            report.get('planned_attempts') == len(expected) and report.get('observed_attempts') == len(expected) and
            report.get('missing_trials') == [] and isinstance(report.get('trials'), dict) and
            set(report['trials']) == set(expected), 'incomplete/stale study report')
    tasks = {task['id']: task for task in record['tasks']}
    seen = set()
    assessor = record['goal']['assessment']['actor']
    require(assessor != record['goal']['current_owner'] and
            all(assessor != task['execution']['actor'] for task in tasks.values()),
            'study report cannot be self-approved')
    for tid, trial in expected.items():
        saved = report['trials'][tid]
        outcome.shape(saved, {'status', 'execution', 'oracle', 'reported_status', 'critical_failure',
                              'usage', 'record_sha256', 'review_sha256'}, 'saved trial')
        require(saved.get('status') in ('success', 'failure', 'environment_failure', 'aborted'),
                'unknown trial cannot complete study')
        raw_ref = {'path': 'trials/' + tid + '/record.json', 'sha256': saved.get('record_sha256')}
        raw = decode(bound(raw_ref))
        outcome.shape(raw, {'format', 'binding', 'reported_status', 'workspace', 'artifacts',
                            'launch', 'worker_done', 'brief', 'trace', 'usage'}, 'saved trial record')
        binding = outcome.trial_binding(plan, plan_ref['sha256'], trial)
        require(raw.get('binding') == binding, 'stale study candidate/conditions')
        require(raw['format'] == outcome.VERSION and raw['reported_status'] in outcome.STATUSES,
                'invalid raw trial record')
        require(raw['reported_status'] == saved['reported_status'], 'study reported status mismatch')
        for key in ('brief', 'launch', 'worker_done', 'trace', 'usage'):
            if raw.get(key) is not None:
                bound(raw[key])
        require(isinstance(raw['artifacts'], dict), 'trial artifact inventory required')
        artifacts = {name: bound(reference) for name, reference in raw['artifacts'].items()}
        require(outcome.file_tree(bundle / 'trials' / tid / 'artifacts') == artifacts,
                'trial artifact inventory mismatch')
        require(bound(raw['brief']) == outcome.brief(bundle, plan, plan_ref['sha256'], trial,
                                                    Path(raw['workspace'])).encode(), 'trial brief mismatch')
        actual = outcome.execution(bundle, raw, plan, seen, bound)
        initial = plan['tasks'][trial['task']]['initial']
        changed = sorted(name for name, data in artifacts.items()
                         if name not in initial or data != initial[name].encode())
        changed += sorted(set(initial) - set(artifacts))
        require(actual['modified_artifacts'] is None or actual['modified_artifacts'] == sorted(changed),
                'trial modified-artifact claim mismatch')
        require(saved.get('execution') == actual and actual['run_id'] == record['goal']['id'],
                'stale study execution identity')
        task = tasks.get(mapping[tid])
        require(task is not None and task['id'] == actual['task_id'] and
                task['current_dispatch'] == actual['dispatch_id'] and
                task['candidate'] == binding['candidate_sha256'] and
                task['execution']['actor'] == actual['executor'] and
                task['execution']['state'] == 'settled', 'study Task/Dispatch/candidate must be settled and exact')
        result = task['execution']['result']
        receipt = raw['worker_done']
        if receipt is None:
            launch = outcome.envelope(bound(raw['launch']))
            require(saved['status'] == 'environment_failure' and launch.get('state') == 'failed' and
                    launch.get('failedStage') == 'agent_readiness' and result['outcome'] == 'failed',
                    'absent done requires actual failed readiness attempt')
            receipt = raw['launch']
        else:
            require(result['outcome'] == actual['outcome'], 'trial result cannot relabel actual outcome')
            require(actual['outcome'] != 'failed' or saved['status'] == 'failure',
                    'failed trial cannot be reported as success')
        result_evidence = evidence[result['evidence']]
        require(result_evidence.get('file') == (prefix / receipt['path']).as_posix() and
                result_evidence.get('sha256') == receipt['sha256'], 'trial result must bind actual receipt bytes')
        require((bundle / 'trials' / tid / 'review.json').exists() == (saved['review_sha256'] is not None),
                'raw review omitted from report')
        reviewed_critical = None
        if saved['review_sha256'] is not None:
            review = decode(bound({'path': 'trials/' + tid + '/review.json', 'sha256': saved['review_sha256']}))
            template = outcome.review_binding(raw, actual, 'real')
            outcome.shape(review, template, 'study review')
            require(all(review[k] == template[k] for k in template
                        if k not in ('assessor', 'critical_failure', 'basis', 'note')) and
                    review['assessor'] != actual['executor'] and review['basis'] == 'independent',
                    'stale/self-approved study review')
            require(isinstance(review['assessor'], str) and review['assessor'].strip() and
                    isinstance(review['note'], str) and review['note'].strip() and
                    (review['critical_failure'] is None or type(review['critical_failure']) is bool),
                    'invalid raw review verdict')
            reviewed_critical = review['critical_failure']
        validate_saved_oracle(outcome, plan['tasks'][trial['task']], artifacts, saved['oracle'])
        status, critical = outcome.trial_status(raw['reported_status'], actual, saved['oracle'],
                                                reviewed_critical, raw['trace'] is not None)
        require(saved['status'] == status and saved['critical_failure'] is critical,
                'saved status/critical finding contradicts original evidence')
        usage = decode(bound(raw['usage'])) if raw['usage'] is not None else None
        if usage is not None:
            outcome.shape(usage, {'coverage', 'raw_total', 'tokenizer', 'scope', 'source'}, 'saved usage')
            require(usage['coverage'] in ('unknown', 'partial', 'complete') and
                    (usage['raw_total'] is None or type(usage['raw_total']) is int and usage['raw_total'] >= 0) and
                    all(usage[key] is None or isinstance(usage[key], str) for key in ('tokenizer', 'scope', 'source')),
                    'invalid saved usage')
        require(outcome.canonical(saved['usage']) == outcome.canonical(usage), 'saved usage contradicts raw evidence')
    require(outcome.canonical(report) == outcome.canonical(outcome.summarize(plan, plan_ref['sha256'], report['trials'])),
            'saved full report/denominator/aggregate mismatch')
    return set(mapping.values())


def validate_saved_oracle(outcome, task, artifacts, saved):
    """Check saved oracle data without ever executing Python task artifacts."""
    require(isinstance(saved, dict), 'saved oracle result required for every trial')
    safe = outcome.oracle(task, artifacts, allow_task_code=False)
    if task['oracle']['kind'] == 'json_equal' or safe['reason'] == 'missing oracle artifact':
        require(outcome.canonical(saved) == outcome.canonical(safe), 'saved pure oracle result mismatch')
        return
    keys = {'critical_failure', 'protected_changed_or_missing', 'unexpected_files', 'passed', 'exit_code', 'reason'}
    executed = saved.get('reason') == 'isolated Python function cases; no provider or device execution'
    outcome.shape(saved, keys | ({'stdout', 'stderr'} if executed else set()), 'saved Python oracle')
    for field in ('critical_failure', 'protected_changed_or_missing', 'unexpected_files'):
        require(outcome.canonical(saved[field]) == outcome.canonical(safe[field]), 'saved oracle artifact facts mismatch')
    require(type(saved['passed']) is bool, 'saved oracle verdict must be boolean')
    if not executed:
        require(saved['reason'] in ('oracle timeout', 'task code execution not enabled') and
                saved['exit_code'] is None and saved['passed'] is False,
                'unknown/absent Python oracle result')
        return
    require(type(saved['exit_code']) is int and
            all(isinstance(saved[field], str) and len(saved[field]) <= 4000 for field in ('stdout', 'stderr')),
            'saved Python oracle execution fields required')
    try:
        cases = outcome.decode(saved['stdout'])
    except ValueError:
        cases = None
    passed = (saved['exit_code'] == 0 and not safe['critical_failure'] and
              outcome.canonical(cases) == outcome.canonical([True] * len(task['oracle']['cases'])))
    require(saved['passed'] is passed, 'saved Python oracle verdict contradicts exit/output')


def validate_receipt(previous, manifest, manifest_hash, record_binding):
    require(set(previous) <= {'format', 'run_id', 'manifest_sha256', 'status', 'removed',
                              'errors', 'record', 'activity', 'pending', 'record_validation', 'trigger'} and
            previous.get('format') == 'company-run-completion/v1' and
            previous.get('run_id') == manifest['run_id'] and
            previous.get('status') in ('blocked', 'completed') and
            previous.get('errors') == [] and isinstance(previous.get('activity'), dict),
            'invalid previous completion receipt')
    require(previous.get('manifest_sha256') == manifest_hash and previous.get('record') == record_binding,
            'previous completion binding mismatch')
    removed = previous.get('removed')
    require(isinstance(removed, list) and len(removed) <= len(manifest['disposable']) and
            removed == manifest['disposable'][:len(removed)], 'invalid previous removed bindings')
    require('pending' not in previous, 'interrupted unlink; preserve quarantine for owner recovery')
    require(previous['status'] != 'completed' or removed == manifest['disposable'],
            'incomplete successful receipt')
    return removed


def storage_inventory(fd, declared, preserved, protected, blockers):
    """One bounded nofollow source/ownership inventory shared by every entry."""
    rows, visited = [], 0
    root_device = os.fstat(fd).st_dev
    def visit(handle, prefix='', depth=0):
        nonlocal visited
        require(depth <= 64, 'inventory limit reached')
        before = os.fstat(handle)
        for name in sorted(os.listdir(handle)):
            visited += 1
            require(visited <= 100000, 'inventory limit reached')
            ref = prefix + name
            st = os.stat(name, dir_fd=handle, follow_symlinks=False)
            if name == '.git':
                blockers.append('source/worktree metadata present')
                rows.append({'path': ref, 'category': 'protected', 'bytes': None, 'identity': signature(st)})
                continue
            if stat.S_ISDIR(st.st_mode):
                if st.st_uid != os.getuid() or st.st_mode & 0o022 or st.st_dev != root_device:
                    blockers.append('shared/non-owned/cross-device directory protected: ' + ref)
                    rows.append({'path': ref, 'category': 'protected', 'bytes': None, 'identity': signature(st)})
                    continue
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=handle)
                try:
                    require((os.fstat(child).st_dev, os.fstat(child).st_ino) == (st.st_dev, st.st_ino), 'directory replaced during inventory')
                    visit(child, ref + '/', depth + 1)
                finally:
                    os.close(child)
                continue
            safe = stat.S_ISREG(st.st_mode) and st.st_nlink == 1 and st.st_uid == os.getuid() and not st.st_mode & 0o022 and st.st_dev == root_device
            category = ('protected' if not safe or ref in protected else 'preserved' if ref in preserved else 'declared_disposable' if ref in declared else 'unknown')
            if not safe and ref in declared:
                blockers.append('unsafe/shared/non-owned disposable file: ' + ref)
            rows.append({'path': ref, 'category': category, 'bytes': st.st_size if safe else None, 'identity': signature(st)})
        require(signature(before) == signature(os.fstat(handle)), 'directory changed during inventory')
    visit(fd)
    return rows


def storage_preflight(root, fd, targets, home=None):
    """Full native Git/UID/shared union, also inside completion's action lock.

    No git subprocess/index writes. Missing inventory is refusal, never clean.
    Repeated by the sole unlink engine including after same-parent quarantine.
    """
    verify_run_path(root, fd)
    if home is None:
        # complete's public signature is retained; locate its explicit runs ancestor.
        home = next((p.parent for p in reversed(root.parents) if p.name == 'runs'), None)
    if home is None:
        raise ValueError('Company namespace unknown')
    require(root.is_relative_to(Path(home) / 'runs'), 'Company namespace unknown')
    cursor = root
    while True:
        st = cursor.lstat()
        require(stat.S_ISDIR(st.st_mode) and st.st_uid == os.getuid() and not st.st_mode & 0o022,
                'Company namespace shared/non-owned')
        if cursor == Path(home):
            break
        cursor = cursor.parent
    for ancestor in (root, *root.parents):
        require(not os.path.lexists(ancestor / '.git'), 'Run overlaps source/worktree; tracked/uncommitted/untracked files protected')
    blockers = []
    rows = storage_inventory(fd, set(targets), set(), RESERVED, blockers)
    require(not blockers, '; '.join(sorted(set(blockers))))
    verify_run_path(root, fd)
    return rows


def unlink_exact(root, fd, bindings, result, validate, persist, probe=probe_activity):
    """Sole exact-file quarantine/unlink engine; caller supplies validated authority.

    Completion uses accepted Run CAS and its existing receipt sink. Separately
    reviewed current maintenance uses external write-ahead receipts, never a
    forged accepted Run or a write into historical metadata.
    """
    done = {x['path'] for x in result['removed']}
    for binding in bindings:
        if binding['path'] in done:
            continue
        validate()
        pins(fd, binding['path'])
        result['activity'] = probe_activity(root, root / binding['path']) if probe is probe_activity else probe(root)
        with parent_fd(fd, binding['path']) as (parent, name):
            require(snapshot_file(fd, binding['path']) == binding, 'target changed before deletion')
            quarantine = '.completion-quarantine-' + uuid.uuid4().hex
            os.rename(name, quarantine, src_dir_fd=parent, dst_dir_fd=parent)
            try:
                st = os.stat(quarantine, dir_fd=parent, follow_symlinks=False)
                require(signature(st)[:4] == binding['identity'][:4] and stat.S_ISREG(st.st_mode) and st.st_nlink == 1,
                        'target swapped during rename')
                verify_run_path(root, fd)
                with parent_fd(fd, binding['path']) as (fresh, _):
                    require((os.fstat(fresh).st_dev, os.fstat(fresh).st_ino) == (os.fstat(parent).st_dev, os.fstat(parent).st_ino), 'parent moved during rename')
                result['pending'] = {'path': binding['path'], 'quarantine': quarantine}
                persist(result)
                result['activity'] = probe_activity(root, root / Path(binding['path']).parent / quarantine) if probe is probe_activity else probe(root)
                validate()
                storage_preflight(root, fd, [* [x['path'] for x in bindings], (Path(binding['path']).parent / quarantine).as_posix()])
                pins(fd, binding['path'])
                final = snapshot_file(parent, quarantine)
                require(final['sha256'] == binding['sha256'] and final['identity'] == signature(st), 'quarantine changed before unlink')
                last = os.stat(quarantine, dir_fd=parent, follow_symlinks=False)
                require(signature(last) == final['identity'] and stat.S_ISREG(last.st_mode) and last.st_nlink == 1 and
                        last.st_uid == os.getuid() and not last.st_mode & 0o022, 'quarantine replaced before unlink')
                # The final authority callback can yield too. Revalidate BOTH
                # its exact target and live namespace after it returns; moving
                # only the namespace check leaves a replacement-file hole.
                validate()
                storage_preflight(root, fd, [*[x['path'] for x in bindings], (Path(binding['path']).parent / quarantine).as_posix()])
                pins(fd, binding['path'])
                final = snapshot_file(parent, quarantine)
                require(final['sha256'] == binding['sha256'] and final['identity'] == signature(st), 'quarantine changed after final validation')
                last = os.stat(quarantine, dir_fd=parent, follow_symlinks=False)
                require(signature(last) == final['identity'] and stat.S_ISREG(last.st_mode) and last.st_nlink == 1 and
                        last.st_uid == os.getuid() and not last.st_mode & 0o022, 'quarantine replaced after final validation')
                verify_run_path(root, fd)
                with parent_fd(fd, binding['path']) as (fresh, _):
                    require((os.fstat(fresh).st_dev, os.fstat(fresh).st_ino) ==
                            (os.fstat(parent).st_dev, os.fstat(parent).st_ino),
                            'parent moved before unlink')
                os.unlink(quarantine, dir_fd=parent)
                os.fsync(parent)
            except BaseException:
                try:
                    os.stat(name, dir_fd=parent, follow_symlinks=False)
                except FileNotFoundError:
                    os.rename(quarantine, name, src_dir_fd=parent, dst_dir_fd=parent)
                raise
            result.pop('pending', None)
            result['removed'].append(binding)
            persist(result)


def complete(root, fd, manifest, manifest_hash, record_ref, probe=probe_activity, trigger='direct_complete', capability=None):
    result = {'format': 'company-run-completion/v1', 'run_id': manifest['run_id'],
              'manifest_sha256': manifest_hash, 'status': 'blocked', 'removed': [], 'errors': [], 'trigger': {'mode': trigger}}
    if capability is None:
        home = (Path(manifest['enrollment']['sejong_home']) if 'enrollment' in manifest else
                next((p.parent for p in reversed(root.parents) if p.name == 'runs'), None))
        require(home is not None, 'Company namespace unknown')
        context = lifecycle_lock(home, root)
        try:
            cap = context.__enter__()
        except (OSError, ValueError) as exc:
            # Lock/read failure is a blocked result, never authority to publish
            # a diagnostic through an unheld descriptor.
            result['errors'].append(str(exc))
            return result
        try:
            require((os.fstat(fd).st_dev, os.fstat(fd).st_ino) ==
                    (os.fstat(cap.fd).st_dev, os.fstat(cap.fd).st_ino), 'completion descriptor root differs')
            return complete(root, cap.fd, manifest, manifest_hash, record_ref, probe, trigger, cap)
        finally:
            context.__exit__(None, None, None)
    try:
        if capability is not None: capability.verify()
        validate_manifest(manifest)
        verify_run_path(root, fd)
        require(manifest.get('format') == FORMAT and manifest.get('root') == str(root) and
                manifest.get('root_identity') == [os.fstat(fd).st_dev, os.fstat(fd).st_ino],
                'Run/layout identity mismatch')
        record_data, record_binding = read_file(fd, record_ref)
        record = decode(record_data)
        checked = validate_acceptance(record, root / record_ref, manifest, manifest_hash,
                            require_routing=manifest.get('routing_accounting') == 'required')
        # An annotation on an already accepted record, not an acceptance shortcut.
        # Older receipts without this optional field remain readable.
        result['record_validation'] = {key: checked[key] for key in
                                       ('historical_integrity', 'current_readiness')}
        result['record'] = record_binding
        require(manifest['preserve'], 'compact evidence declaration required')
        protected = {x['path'] for x in manifest['preserve']} | {record_ref}
        declaration = record.get('goal_evidence')
        if declaration is not None:
            sidecar = (Path(record_ref).parent / declaration['path']).as_posix()
            protected.add(sidecar)
        # Every local evidence file is protected, whether or not explicitly registered.
        for item in record['evidence'].values():
            if item.get('file'):
                path = Path(item['file'])
                path = path if path.is_absolute() else root / Path(record_ref).parent / path
                try:
                    protected.add(str(path.resolve(strict=True).relative_to(root)))
                except ValueError:
                    pass
        targets = [x['path'] for x in manifest['disposable']]
        require(len(set(targets)) == len(targets) and not (set(targets) & protected), 'protected/duplicate deletion path')
        storage_preflight(root, fd, targets)
        pins(fd)
        for binding in manifest['preserve']:
            require(snapshot_file(fd, binding['path']) == binding, 'preserved evidence changed')
        previous = None
        try:
            previous = decode(read_file(fd, RECEIPT, True)[0])
        except FileNotFoundError:
            pass
        if previous is not None:
            result['removed'] = validate_receipt(previous, manifest, manifest_hash, record_binding)
            require(previous['status'] == 'completed', 'partial completion requires explicit owner recovery; refusing retry')
        done = {x['path'] for x in result['removed']}
        for binding in manifest['disposable']:
            pins(fd, binding['path'])
            for preserved in manifest['preserve']:
                require(snapshot_file(fd, preserved['path']) == preserved, 'preserved evidence changed during completion')
            if binding['path'] in done:
                with parent_fd(fd, binding['path']) as (parent, name):
                    try:
                        os.stat(name, dir_fd=parent, follow_symlinks=False)
                    except FileNotFoundError:
                        continue
                raise ValueError('deleted path reappeared; refusing retry')
            require(snapshot_file(fd, binding['path']) == binding, 'stale disposable identity/content')
        result['activity'] = probe(root)
        def validate_action():
            if capability is not None: capability.verify()
            storage_preflight(root, fd, targets)
            verify_run_path(root, fd)
            require(sha(read_file(fd, MANIFEST, True)[0]) == manifest_hash, 'manifest changed during completion')
            require(read_file(fd, record_ref)[1] == record_binding, 'acceptance changed during completion')
            for preserved in manifest['preserve']:
                require(snapshot_file(fd, preserved['path']) == preserved, 'preserved evidence changed during completion')
        def persist(value):
            capability.verify()
            write_metadata(fd, RECEIPT, value)
        unlink_exact(root, fd, manifest['disposable'], result, validate_action, persist, probe)
        result['status'] = 'completed'
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        result['errors'].append(str(exc))
    # A diagnostic is a mutation, not an exception to the capability boundary.
    # In particular succeeded Stop borrows this path before its outer verify.
    try:
        capability.verify()
    except (OSError, ValueError) as exc:
        result['status'] = 'blocked'
        if str(exc) not in result['errors']: result['errors'].append(str(exc))
        return result
    write_metadata(fd, RECEIPT if result['status'] == 'completed' else REJECTION, result)
    return result


def initialize_run(root, fd, run_id, owner, consumers, enrollment=None, coordination=None):
    require(run_id and owner and len(set(consumers)) == len(consumers), 'Run/owner/unique consumers required')
    manifest = {'format': FORMAT, 'run_id': run_id, 'owner': owner, 'root': str(root),
                'root_identity': [os.fstat(fd).st_dev, os.fstat(fd).st_ino],
                'consumers': consumers, 'disposable': [], 'preserve': [], 'routing_accounting': 'required'}
    if enrollment is not None:
        manifest['enrollment'] = enrollment
        require(coordination is not None, 'enrollment requires stable coordination')
        manifest['coordination'] = coordination
    try:
        prior = decode(read_file(fd, MANIFEST, True)[0])
    except FileNotFoundError:
        write_metadata(fd, MANIFEST, manifest)
    else:
        require(prior == manifest, 'already registered; never overwrite a changed Run')
    return manifest


def register_declarations(fd, manifest, disposable, preserve):
    for name in (RECEIPT, REJECTION):
        try:
            read_file(fd, name, True)
        except FileNotFoundError:
            continue
        raise ValueError('completion already attempted; declaration frozen')
    refs = {x['path'] for key in ('disposable', 'preserve') for x in manifest[key]}
    for key, values in (('disposable', disposable), ('preserve', preserve)):
        for ref in values:
            require(ref not in refs, 'duplicate retention declaration')
            pins(fd, ref)
            manifest[key].append(snapshot_file(fd, ref))
            refs.add(ref)
    return manifest


def blocked_observation(observed, exc):
    """Output only: retain earlier facts, never re-read an invalid capability."""
    result: dict = dict(observed) if observed is not None else {'removed': []}
    result['status'] = 'blocked'
    if 'hook' in result:
        result['hook'] = {**result['hook'], 'exit_code': 1}
    result['errors'] = list(result.get('errors', []))
    if str(exc) not in result['errors']:
        result['errors'].append(str(exc))
    if observed is not None:
        result['observation'] = dict(scope='earlier_in_memory', current_namespace='unknown',
                                     receipt_readback='unknown', remaining_targets='unknown',
                                     recovery='owner recheck required; no automatic retry')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['init', 'register', 'complete'])
    parser.add_argument('--run', required=True, type=Path)
    parser.add_argument('--sejong-home', type=Path, default=default_home())
    parser.add_argument('--run-id')
    parser.add_argument('--owner')
    parser.add_argument('--consumer', action='append', default=[])
    parser.add_argument('--disposable', action='append', default=[])
    parser.add_argument('--preserve', action='append', default=[])
    parser.add_argument('--record')
    parser.add_argument('--expect-manifest-sha256')
    parser.add_argument('--trigger', choices=('direct_complete', 'explicit_lead', 'codex_stop'), default='direct_complete')
    parser.add_argument('--session-id', help='Bind this exact host session to a future Stop callback')
    parser.add_argument('--repo-root', type=Path, help='Exact hook cwd; no ancestor fallback')
    parser.add_argument('--expect-session-binding-sha256', help='CAS rebind after prior accepted completion')
    args = parser.parse_args(argv)
    fd = lock = None
    context = cap = None
    result = None
    try:
        context = lifecycle_lock(args.sejong_home, args.run, create=args.command == 'init')
        cap = context.__enter__()
        root, fd, lock = cap.root, cap.fd, cap.lock
        if args.command == 'init':
            initialize_run(root, fd, args.run_id, args.owner, args.consumer)
            if args.session_id:
                require(args.repo_root, 'session registration requires exact repo-root')
                from completion_hook import register_session
                register_session(args.sejong_home, args.session_id, root, args.run_id,
                                 args.owner, args.repo_root, args.record or 'record.json',
                                 args.expect_session_binding_sha256)
            result = {'status': 'registered', 'run_id': args.run_id}
        else:
            data, _ = read_file(fd, MANIFEST, True)
            manifest = decode(data)
            validate_manifest(manifest)
            require(manifest.get('format') == FORMAT and manifest.get('root') == str(root) and
                    manifest.get('root_identity') == [os.fstat(fd).st_dev, os.fstat(fd).st_ino], 'Run/layout identity mismatch')
            require(sha(data) == args.expect_manifest_sha256, 'manifest compare-and-swap mismatch')
            if args.command == 'register':
                register_declarations(fd, manifest, args.disposable, args.preserve)
                cap.verify()
                write_metadata(fd, MANIFEST, manifest)
                result = {'status': 'declared', 'run_id': manifest['run_id']}
            else:
                require(args.record, 'exact accepted completion record required')
                result = complete(root, fd, manifest, sha(data), args.record, trigger=args.trigger, capability=cap)
        cap.verify()
        result['manifest_sha256'] = sha(read_file(fd, MANIFEST, True)[0])
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result['status'] != 'blocked' else 1
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result = blocked_observation(result, exc)
        if cap is not None:
            # Contended locks must not overwrite another completion's receipt.
            if not isinstance(exc, BlockingIOError):
                try:
                    cap.verify()
                    write_metadata(fd, REJECTION, result)
                except (OSError, ValueError):
                    pass
        print(json.dumps(result, ensure_ascii=False))
        return 1
    finally:
        if cap is not None:
            context.__exit__(None, None, None)


if __name__ == '__main__':
    sys.exit(main())
