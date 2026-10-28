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


def pins(fd, ref=None):
    # Path-local pins/activity markers. No historical/home scan.
    def inspect(handle):
        for name in os.listdir(handle):
            if name in {'.pin', '.keep', '.active', 'PIN', 'KEEP'} or (
                name != LOCK and (name.endswith('.lock') or name.endswith('.pid'))
            ):
                raise ValueError('pin/activity marker: ' + name)
    inspect(fd)
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
    scope = [str(exact)] if exact is not None else ['+D', str(root)]
    result = subprocess.run(['/usr/sbin/lsof', '-nP', '-Fpn', *scope],
                            capture_output=True, text=True, timeout=30)
    require(result.returncode in (0, 1) and not result.stderr.strip(),
            'open-file observation failed: ' + result.stderr.strip())
    # This process holds only the Run/ancestor directories and own lock.
    current = None
    for line in result.stdout.splitlines():
        if line.startswith('p'):
            current = line[1:]
        elif line.startswith('n'):
            name = line[1:]
            own_directory = False
            try:
                Path(name).relative_to(root)
                own_directory = stat.S_ISDIR(Path(name).lstat().st_mode)
            except (OSError, ValueError):
                pass
            require(current == str(os.getpid()) and (name == str(root / LOCK) or own_directory),
                    'open activity: ' + line)
    return {'tool': 'lsof exact file' if exact is not None else 'lsof scoped +D',
            'status': 'no external open paths'}


def validate_acceptance(record, record_path, manifest, manifest_hash, require_routing=False):
    checked = check_record(record, record_path.parent, require_routing=require_routing)
    require(checked['ok'], 'record contradictions: ' + json.dumps(checked['errors']))
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
    return checked


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
                              'errors', 'record', 'activity', 'pending'} and
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


def complete(root, fd, manifest, manifest_hash, record_ref, probe=probe_activity):
    result = {'format': 'company-run-completion/v1', 'run_id': manifest['run_id'],
              'manifest_sha256': manifest_hash, 'status': 'blocked', 'removed': [], 'errors': []}
    try:
        validate_manifest(manifest)
        verify_run_path(root, fd)
        require(manifest.get('format') == FORMAT and manifest.get('root') == str(root) and
                manifest.get('root_identity') == [os.fstat(fd).st_dev, os.fstat(fd).st_ino],
                'Run/layout identity mismatch')
        record_data, record_binding = read_file(fd, record_ref)
        record = decode(record_data)
        validate_acceptance(record, root / record_ref, manifest, manifest_hash,
                            require_routing=manifest.get('routing_accounting') == 'required')
        result['record'] = record_binding
        require(manifest['preserve'], 'compact evidence declaration required')
        protected = {x['path'] for x in manifest['preserve']} | {record_ref}
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
        for binding in manifest['disposable']:
            if binding['path'] in done:
                continue
            pins(fd, binding['path'])
            result['activity'] = probe_activity(root, root / binding['path']) if probe is probe_activity else probe(root)
            for preserved in manifest['preserve']:
                require(snapshot_file(fd, preserved['path']) == preserved, 'preserved evidence changed during completion')
            require(sha(read_file(fd, MANIFEST, True)[0]) == manifest_hash,
                    'manifest changed during completion')
            require(read_file(fd, record_ref)[1] == record_binding, 'acceptance changed during completion')
            verify_run_path(root, fd)
            with parent_fd(fd, binding['path']) as (parent, name):
                require(snapshot_file(fd, binding['path']) == binding, 'target changed before deletion')
                quarantine = '.completion-quarantine-' + uuid.uuid4().hex
                os.rename(name, quarantine, src_dir_fd=parent, dst_dir_fd=parent)
                try:
                    # Rename changes ctime. All other identity fields must match.
                    st = os.stat(quarantine, dir_fd=parent, follow_symlinks=False)
                    require(signature(st)[:4] == binding['identity'][:4] and stat.S_ISREG(st.st_mode)
                            and st.st_nlink == 1, 'target swapped during rename')
                    verify_run_path(root, fd)
                    with parent_fd(fd, binding['path']) as (fresh, _):
                        require(os.fstat(fresh).st_ino == os.fstat(parent).st_ino, 'parent moved during rename')
                    # Write-ahead receipt: crash between unlink and receipt is fail-closed.
                    result['pending'] = {'path': binding['path'], 'quarantine': quarantine}
                    write_metadata(fd, RECEIPT, result)
                    result['activity'] = probe_activity(root, root / Path(binding['path']).parent / quarantine) if probe is probe_activity else probe(root)
                    require(read_file(fd, record_ref)[1] == record_binding and
                            sha(read_file(fd, MANIFEST, True)[0]) == manifest_hash,
                            'acceptance/manifest changed during quarantine')
                    for preserved in manifest['preserve']:
                        require(snapshot_file(fd, preserved['path']) == preserved,
                                'preserved evidence changed during quarantine')
                    pins(fd, binding['path'])
                    final = snapshot_file(parent, quarantine)
                    require(final['sha256'] == binding['sha256'] and
                            final['identity'] == signature(st), 'quarantine changed before unlink')
                    last = os.stat(quarantine, dir_fd=parent, follow_symlinks=False)
                    require(signature(last) == final['identity'] and stat.S_ISREG(last.st_mode) and
                            last.st_nlink == 1, 'quarantine replaced before unlink')
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
                write_metadata(fd, RECEIPT, result)
        result['status'] = 'completed'
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        result['errors'].append(str(exc))
    write_metadata(fd, RECEIPT if result['status'] == 'completed' else REJECTION, result)
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
    parser.add_argument('--session-id', help='Bind this exact host session to a future Stop callback')
    parser.add_argument('--repo-root', type=Path, help='Exact hook cwd; no ancestor fallback')
    parser.add_argument('--expect-session-binding-sha256', help='CAS rebind after prior accepted completion')
    args = parser.parse_args(argv)
    fd = lock = None
    try:
        root, fd = open_run(args.sejong_home, args.run)
        lock = os.open(LOCK, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        require(stat.S_ISREG(os.fstat(lock).st_mode) and os.fstat(lock).st_nlink == 1, 'unsafe lock')
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.command == 'init':
            require(args.run_id and args.owner and len(set(args.consumer)) == len(args.consumer), 'Run/owner/unique consumers required')
            manifest = {'format': FORMAT, 'run_id': args.run_id, 'owner': args.owner,
                        'root': str(root), 'root_identity': [os.fstat(fd).st_dev, os.fstat(fd).st_ino],
                        'consumers': args.consumer, 'disposable': [], 'preserve': [],
                        'routing_accounting': 'required'}
            try:
                prior = decode(read_file(fd, MANIFEST, True)[0])
            except FileNotFoundError:
                write_metadata(fd, MANIFEST, manifest)
            else:
                require(prior == manifest, 'already registered; never overwrite a changed Run')
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
                try:
                    read_file(fd, RECEIPT, True)
                except FileNotFoundError:
                    pass
                else:
                    raise ValueError('completion already attempted; declaration frozen')
                refs = {x['path'] for key in ('disposable', 'preserve') for x in manifest[key]}
                for key in ('disposable', 'preserve'):
                    for ref in getattr(args, key):
                        require(ref not in refs, 'duplicate retention declaration')
                        pins(fd, ref)
                        manifest[key].append(snapshot_file(fd, ref))
                        refs.add(ref)
                write_metadata(fd, MANIFEST, manifest)
                result = {'status': 'declared', 'run_id': manifest['run_id']}
            else:
                require(args.record, 'exact accepted completion record required')
                result = complete(root, fd, manifest, sha(data), args.record)
        result['manifest_sha256'] = sha(read_file(fd, MANIFEST, True)[0])
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result['status'] != 'blocked' else 1
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result = {'status': 'blocked', 'errors': [str(exc)], 'removed': []}
        if fd is not None and lock is not None:
            # Contended locks must not overwrite another completion's receipt.
            if not isinstance(exc, BlockingIOError):
                try:
                    write_metadata(fd, REJECTION, result)
                except (OSError, ValueError):
                    pass
        print(json.dumps(result, ensure_ascii=False))
        return 1
    finally:
        if lock is not None:
            os.close(lock)
        if fd is not None:
            os.close(fd)


if __name__ == '__main__':
    sys.exit(main())
