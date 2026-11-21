#!/usr/bin/env python3
"""Nonlaunching, local catalog preparation from existing authority and evidence.

No subprocess, host discovery, approval creation or automatic reprepare. Bundles
retain live evidence paths: they are private review artifacts, not portable grants.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

sys.dont_write_bytecode = True
from company_config import resolve
from record_check import check_routing, unique_object, invalid_constant

PACKAGE = Path(__file__).resolve().parents[1]
LEGACY_FORMAT = 'company-routing-prepare/v1'
FORMAT = 'company-routing-prepare/v2'
FILES = ('original-record.json', 'original-decision.json', 'spec.txt', 'record.json',
         'decision.json', 'patch.json', 'routing-check.json', 'missing-fields.json')
LIMITS = ('Supplied-evidence preparation only; not authenticated host readiness or launch permission. '
          'Manual/profile/measurement/completion responsibilities and checked launch remain mandatory.')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def decode(raw):
    return json.loads(raw.decode('utf-8'), object_pairs_hook=unique_object, parse_constant=invalid_constant)


def encoded(value):
    return (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')


def issue(code, message, path='$'):
    return {'path': path, 'code': code, 'message': message}


def regular(path):
    path = Path(path).absolute()
    if path.resolve() != path or not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError('expected nonsymlink regular file: ' + str(path))
    return path.read_bytes()


def source_state():
    baseline = PACKAGE / 'references/upstream/baseline.json'
    raw = regular(baseline)
    rows = decode(raw)['policy_files']
    state = {'references/upstream/baseline.json': digest(raw)}
    for row in rows:
        name = row['path']
        if not isinstance(name, str) or Path(name).is_absolute() or '..' in Path(name).parts or name in state:
            raise ValueError('invalid or duplicate source binding')
        actual = digest(regular(PACKAGE / name))
        if actual != row['sha256']:
            raise ValueError('source policy drift: ' + name)
        state[name] = actual
    return state


def rebase(document, base, target):
    """Only relocate file references. Never fill authority or semantic fields."""
    value = copy.deepcopy(document)
    patch = []
    if isinstance(value, dict) and isinstance(value.get('evidence'), dict):
        for key, row in value['evidence'].items():
            if isinstance(row, dict) and isinstance(row.get('file'), str):
                old = row['file']
                new = str((base / old).absolute())
                if old != new:
                    pointer = key.replace('~', '~0').replace('/', '~1')
                    patch.append({'target': target, 'op': 'replace',
                                  'path': '/evidence/' + pointer + '/file', 'value': new})
                    row['file'] = new
    return value, patch


def evidence_inputs(documents):
    """Pin supplied files and catalog receipt bytes; never copy credentials/DBs."""
    paths = set()
    for document in documents:
        refs = document.get('evidence', {}) if isinstance(document, dict) else {}
        if not isinstance(refs, dict):
            continue
        for row in refs.values():
            if not isinstance(row, dict) or not isinstance(row.get('file'), str):
                continue
            path = Path(row['file'])
            paths.add(str(path))
            if row.get('source') == 'orca_model_catalog':
                manifest = decode(regular(path))
                for receipt in manifest['receipts']:
                    name = receipt['file']
                    if not isinstance(name, str) or Path(name).name != name or name in ('.', '..'):
                        raise ValueError('unsafe catalog receipt path')
                    paths.add(str(path.parent / name))
    return sorted(paths)


def checked(record, decision, root, spec, worktree):
    errors = []
    try:
        result = check_routing(decision, root, record, root, prelaunch=True)
    except (ValueError, OSError, KeyError, TypeError, AttributeError, OverflowError) as exc:
        result = {'ok': False, 'errors': [issue('routing_input', str(exc))]}
    errors.extend(result['errors'])
    if not isinstance(record, dict) or record.get('label') != 'real':
        errors.append(issue('real_record_required', 'Supply the existing real record', '$.record.label'))
    if not isinstance(decision, dict) or decision.get('label') != 'real':
        errors.append(issue('real_decision_required', 'Supply the existing real decision', '$.label'))
    binding = decision.get('binding') if isinstance(decision, dict) else None
    binding = binding if isinstance(binding, dict) else {}
    if binding.get('spec_sha256') != digest(spec):
        errors.append(issue('spec_binding', 'Exact UTF-8 spec does not match existing binding', '$.binding.spec_sha256'))
    if binding.get('planned') is not True:
        errors.append(issue('planned_required', 'Convenience preparation supports only fresh planned spec tasks', '$.binding.planned'))
    context = binding.get('host_catalog')
    if not isinstance(context, dict) or context.get('worktree') != worktree:
        errors.append(issue('worktree_binding', 'Supply existing exact local host catalog/worktree binding', '$.binding.host_catalog'))
    observations = context.get('observed_files') if isinstance(context, dict) else None
    if not isinstance(observations, list) or not any(
            isinstance(row, dict) and row.get('kind') == 'orca-profile-settings/v1' for row in observations):
        errors.append(issue('semantic_observation_required',
                            'Supply existing semantic helper observations; legacy byte-only preparation remains manual',
                            '$.binding.host_catalog.observed_files'))
    if not isinstance(worktree, str) or not worktree.startswith('id:') or '::/' not in worktree:
        errors.append(issue('exact_worktree_required', 'An existing exact host worktree selector is required'))
    if isinstance(record, dict) and record.get('measurement') is not None:
        errors.append(issue('measurement_lifecycle_required',
                            'Use existing measurement lifecycle preparation; this tool never certifies capture readiness', '$.record.measurement'))
    if any(os.environ.get(k) for k in ('ORCA_PAIRING_CODE', 'ORCA_REMOTE_PAIRING', 'ORCA_ENVIRONMENT', 'ORCA_DEV_REPO_ROOT')):
        errors.append(issue('local_host_required', 'Remote/development host selectors are unsupported'))
    return result, errors


def status(errors):
    return {'format': FORMAT, 'ok': not errors, 'status': 'blocked' if errors else 'prepared',
            'launch_authorized': False, 'missing_fields': errors, 'limits': LIMITS}


def write_private(root, name, raw):
    fd = os.open(root / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def prepare(args):
    root = args.output.absolute()
    if root.parent.resolve() != root.parent:
        raise ValueError('output parent must not contain symlinks')
    from native_storage import reserve_producer
    reference = {'path': str(args.enrollment_request.absolute()), 'sha256': args.expect_enrollment_sha256}
    enrollment = reserve_producer(reference, [root / name for name in (*FILES, 'manifest.json')], 'routing_prepare.py')
    canonical = Path(enrollment['run']) / enrollment['record']
    # Reviewed snapshots are not a competing authoritative lifecycle record.
    if regular(canonical) != regular(args.record):
        raise ValueError('prepared snapshot differs from enrolled canonical record')
    root.mkdir(mode=0o700)  # atomic reservation; exists/dangling symlink/parallel caller denies
    os.chmod(root, 0o700)
    raw_record, raw_decision, spec = [regular(path) for path in (args.record, args.decision, args.spec_file)]
    spec.decode('utf-8')  # exact bytes, no newline trimming or normalization
    record, rp = rebase(decode(raw_record), args.record.absolute().parent, 'record.json')
    decision, dp = rebase(decode(raw_decision), args.decision.absolute().parent, 'decision.json')
    source = source_state()
    configuration = resolve()['configuration_sha256']
    inputs = {str(path.absolute()): digest(raw) for path, raw in
              ((args.record, raw_record), (args.decision, raw_decision), (args.spec_file, spec))}
    errors = []
    try:
        for name in evidence_inputs((record, decision)):
            inputs[name] = digest(regular(Path(name)))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        errors.append(issue('evidence_input', str(exc)))
    result, missing = checked(record, decision, root, spec, args.worktree)
    errors.extend(missing)
    # Check again after reading the evidence. No successful cached check is reused.
    for name, expected in inputs.items():
        if digest(regular(Path(name))) != expected:
            errors.append(issue('input_drift', 'Input changed during preparation: ' + name))
    if resolve()['configuration_sha256'] != configuration or source_state() != source:
        errors.append(issue('preparation_drift', 'Configuration/source changed during preparation'))
    payloads = dict(zip(FILES, (raw_record, raw_decision, spec, encoded(record), encoded(decision),
                               encoded(rp + dp), encoded(result), encoded(errors))))
    for name, raw in payloads.items():
        write_private(root, name, raw)
    manifest = {**status(errors), 'worktree': args.worktree, 'configuration_sha256': configuration,
                'source': source, 'inputs': inputs,
                'enrollment': reference, 'canonical_record': {'path': str(canonical), 'sha256': digest(raw_record)},
                'artifacts': {name: digest(raw) for name, raw in payloads.items()}}
    write_private(root, 'manifest.json', encoded(manifest))  # complete marker written last
    directory = os.open(root, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return {**status(errors), 'bundle': str(root)}


def check_bundle(root):
    root = root.absolute()
    manifest = decode(regular(root / 'manifest.json'))
    errors = []
    if manifest['format'] not in (LEGACY_FORMAT, FORMAT) or set(manifest['artifacts']) != set(FILES):
        raise ValueError('unknown or incomplete bundle format')
    if stat.S_IMODE(root.stat().st_mode) != 0o700:
        errors.append(issue('bundle_permissions', 'Bundle directory must be 0700'))
    for name in (*FILES, 'manifest.json'):
        if stat.S_IMODE((root / name).stat().st_mode) != 0o600:
            errors.append(issue('bundle_permissions', 'Bundle files must be 0600: ' + name))
    payloads = {name: regular(root / name) for name in FILES}
    for name, raw in payloads.items():
        if digest(raw) != manifest['artifacts'][name]:
            errors.append(issue('artifact_drift', 'Bundle artifact changed: ' + name))
    for name, expected in manifest['inputs'].items():
        if digest(regular(Path(name))) != expected:
            errors.append(issue('input_drift', 'Original input changed: ' + name))
    if source_state() != manifest['source']:
        errors.append(issue('source_drift', 'Package source changed; review a new preparation'))
    if resolve()['configuration_sha256'] != manifest['configuration_sha256']:
        errors.append(issue('configuration_drift', 'Company configuration changed'))
    _, missing = checked(decode(payloads['record.json']), decode(payloads['decision.json']), root,
                         payloads['spec.txt'], manifest['worktree'])
    errors.extend(missing)
    if manifest['format'] == FORMAT:
        from native_storage import bound_enrollment
        from native_operations import pinned
        ep, _ = pinned(manifest['enrollment'], root)
        enrollment, _, _, _ = bound_enrollment(ep)
        canonical = Path(enrollment['run']) / enrollment['record']
        if manifest['canonical_record'] != {'path': str(canonical), 'sha256': digest(regular(canonical))} or regular(canonical) != payloads['original-record.json']:
            errors.append(issue('canonical_record_drift', 'Enrolled canonical record changed; old preparation cannot launch'))
    # A denied bundle remains denied; checking it never repairs missing authority.
    errors.extend(decode(payloads['missing-fields.json']))
    return {**status(errors), 'bundle': str(root)}


def preview(request_path, expected_sha256):
    """Read a reviewed DAG and current supplied observations; never reserve/start.

    The existing checker owns authority and profile selection. Context is pinned
    review evidence, not authenticated host state or a resource reservation.
    """
    from datetime import datetime, timezone
    from native_operations import pinned, require, shape, text
    from native_storage import bound_enrollment, strings
    from record_check import Checker
    from worker_profile import validate_profile_document

    request_path = request_path.absolute()
    inputs = {}

    def read(reference, base):
        path, raw = pinned(reference, base)
        require(str(path) not in inputs or inputs[str(path)] == digest(raw), 'input changed between reads')
        inputs[str(path)] = digest(raw)
        return path, raw

    _, raw = read({'path': str(request_path), 'sha256': expected_sha256}, request_path.parent)
    value = shape(decode(raw), ('schema', 'record', 'profile', 'enrollment', 'context',
                               'worktree', 'units'), 'preview request')
    require(value['schema'] == 'company-routing-preview-request/v1', 'unknown preview request')
    text(value['worktree'], 'worktree')
    record_path, record_raw = read(value['record'], request_path.parent)
    _, profile_raw = read(value['profile'], request_path.parent)
    context_path, context_raw = read(value['context'], request_path.parent)
    ep, _ = read(value['enrollment'], request_path.parent)
    enrollment, _, _, enrollment_hash = bound_enrollment(ep)
    canonical = Path(enrollment['run']) / enrollment['record']
    require(record_path == canonical, 'preview requires the enrolled canonical record path')
    record, rp = rebase(decode(record_raw), record_path.parent, 'record.json')
    profile = validate_profile_document(decode(profile_raw))
    context = shape(decode(context_raw), ('schema', 'binding', 'observed_at', 'valid_until',
                    'units', 'writers', 'capacity', 'evidence'), 'preview context')
    require(context['schema'] == 'company-routing-preview-context/v1', 'unknown preview context')
    goal = record['goal']
    require(context['binding'] == dict(run=enrollment['run_id'], scope=goal['scope'],
            revision=goal['revision'], owner=goal['current_owner'], worktree=value['worktree'],
            record_sha256=digest(record_raw), profile_sha256=digest(profile_raw)), 'stale preview context binding')
    require('artifact_retention' not in record and goal['id'] == enrollment['run_id'] and goal['current_owner'] == enrollment['owner']
            and goal['owner_acceptance'] == 'accepted' and goal['status'] == 'active', 'active accepted enrolled goal required')
    observed, until = [datetime.fromisoformat(context[k].replace('Z', '+00:00'))
                       for k in ('observed_at', 'valid_until')]
    require(observed.tzinfo is not None and until.tzinfo is not None
            and observed <= datetime.now(timezone.utc) <= until, 'preview context expired or future')
    checker = Checker(context_path.parent)
    checker.evidence_map(context['evidence'], '$.context.evidence', 'real')
    require(not checker.errors, 'invalid preview context evidence: ' + str(checker.errors))
    # Pin actual files as well as declarations; opaque URLs alone cannot make a
    # unit, shared writer or capacity ready. No credential/profile DB copying.
    for ref in context['evidence'].values():
        require(ref.get('kind') == 'host' and isinstance(ref.get('file'), str), 'pinned host context provenance required')
        read({'path': ref['file'], 'sha256': ref['sha256']}, context_path.parent)

    def observation(row, fields):
        shape(row, fields, 'context observation')
        require(isinstance(row['evidence'], str) and row['evidence'] in context['evidence'],
                'missing context observation provenance')
        if 'task' in fields:
            text(row['task'], 'observed Task', nullable=True)

    require(isinstance(context['units'], dict) and isinstance(context['writers'], dict), 'context maps required')
    ids = {u['id'] for u in profile['units']}
    require(set(context['units']) == ids, 'context must observe every exact profile unit')
    for row in context['units'].values():
        observation(row, ('task', 'evidence'))
    for resource, row in context['writers'].items():
        text(resource, 'writer resource')
        observation(row, ('task', 'evidence'))
    observation(context['capacity'], ('available', 'evidence'))
    require(type(context['capacity']['available']) is int and context['capacity']['available'] >= 0,
            'nonnegative observed available capacity required')
    require(isinstance(value['units'], list), 'unit inputs must be an array')
    supplied = {}
    for row in value['units']:
        shape(row, ('id', 'decision', 'spec_file', 'writers'), 'unit inputs')
        text(row['id'], 'unit id')
        require(row['id'] not in supplied, 'duplicate unit inputs')
        strings(row['writers'], 'writer resources')
        supplied[row['id']] = row
    require(set(supplied) == ids, 'input units must match the exact profile DAG')
    source, configuration = source_state(), resolve()['configuration_sha256']
    tasks = {t['id']: t for t in record['tasks']}
    errors, rows = [], []
    for unit in sorted(profile['units'], key=lambda u: u['id']):
        name, blocks = unit['id'], []
        item = supplied[name]
        decision_path, decision_raw = read(item['decision'], request_path.parent)
        spec_path, spec = read(item['spec_file'], request_path.parent)
        spec_text = spec.decode('utf-8')  # retain every space, CR and terminal LF
        require(bool(spec_text.strip()) and '\x00' not in spec_text, 'nonempty NUL-free UTF-8 spec required')
        decision, dp = rebase(decode(decision_raw), decision_path.parent, 'decision.json')
        for path in evidence_inputs((record, decision)):
            raw = regular(Path(path))
            require(path not in inputs or inputs[path] == digest(raw), 'evidence changed between reads')
            inputs[path] = digest(raw)
        result, missing = checked(record, decision, request_path.parent, spec, value['worktree'])
        blocks.extend(missing)
        binding = decision.get('binding', {})
        if (binding.get('task') != name or binding.get('run') != enrollment['run_id']
                or name in tasks or context['units'][name]['task'] is not None):
            blocks.append(issue('fresh_unit_required', 'Unit is already observed, unknown or not bound to this planned Run/unit'))
        if decision.get('selected', {}).get('route') != 'codex':
            blocks.append(issue('local_codex_required', 'Preview initially supports only fresh local Codex specs'))
        if decision.get('constraints', {}).get('billing') != 'subscription':
            blocks.append(issue('subscription_required', 'Preview initially supports only the existing Codex subscription path'))
        if decision.get('profile_binding', {}).get('profile') != profile:
            blocks.append(issue('profile_dag_mismatch', 'Decision must bind the exact complete reviewed profile DAG'))
        dependencies = []
        for dep in sorted(unit['depends_on']):
            task_id = context['units'][dep]['task']
            task = tasks.get(task_id)
            mapped = (task_id == dep or task is not None and
                      task.get('routing_decision', {}).get('profile_binding', {}).get('unit_id') == dep)
            accepted = (mapped and task is not None and task['execution']['state'] == 'settled'
                        and task['execution']['result'] is not None
                        and task['execution']['result']['outcome'] == 'succeeded'
                        and all(task.get(k) is not None and task[k]['verdict'] == 'passed'
                                for k in ('technical', 'parent_integration')))
            dependencies.append({'unit': dep, 'task': task_id, 'accepted': accepted})
            if not accepted:
                blocks.append(issue('dependency_unaccepted', 'Current settled, independently accepted dependency required: ' + dep))
        for resource in item['writers']:
            state = context['writers'].get(resource)
            if state is None or state['task'] is not None:
                blocks.append(issue('writer_unavailable', 'Current evidenced free writer required: ' + resource))
        rows.append({'unit_id': name, 'status': 'blocked' if blocks else 'ready',
                     'missing_fields': blocks, 'dependencies': dependencies, 'writers': sorted(item['writers']),
                     'spec': {'path': str(spec_path), 'sha256': digest(spec), 'bytes': len(spec), 'text': spec_text},
                     'decision': decision, 'patch': rp + dp, 'routing_check': result,
                     'checked_inputs': {'record': {'path': str(canonical), 'sha256': digest(record_raw)},
                         'decision': {'path': str(decision_path), 'sha256': digest(decision_raw)},
                         'spec_file': {'path': str(spec_path), 'sha256': digest(spec)},
                         'worktree': value['worktree'], 'enrollment': {'path': str(ep), 'sha256': inputs[str(ep)]},
                         'run': enrollment['run_id'], 'parent': binding.get('parent_task'),
                         'deps': [d['task'] for d in dependencies if d['accepted']]}})
    # No arbitrary scheduling priority: ambiguous simultaneous claims all block.
    ready = [row for row in rows if row['status'] == 'ready']
    for row in ready:
        conflicts = [other['unit_id'] for other in ready if other is not row
                     and set(row['writers']) & set(other['writers'])]
        if conflicts:
            row['missing_fields'].append(issue('shared_writer', 'Conflicting ready units: ' + ', '.join(conflicts)))
        if len(ready) > context['capacity']['available']:
            row['missing_fields'].append(issue('capacity_unavailable', 'Observed capacity cannot cover this ready wave; narrow the reviewed DAG'))
        if row['missing_fields']:
            row['status'] = 'blocked'
    # Revalidate the same inputs/current source at the end, never reuse a cached
    # successful check. Preview performs no lock/reservation and is not a lease.
    for path, expected in sorted(inputs.items()):
        if digest(regular(Path(path))) != expected:
            errors.append(issue('input_drift', 'Input changed during preview: ' + path))
    if source_state() != source or resolve()['configuration_sha256'] != configuration:
        errors.append(issue('preparation_drift', 'Configuration/source changed during preview'))
    if bound_enrollment(ep)[3] != enrollment_hash or datetime.now(timezone.utc) > until:
        errors.append(issue('context_drift', 'Enrollment or context validity changed during preview'))
    for row in rows:
        row['missing_fields'].extend(errors)
        row['status'] = 'blocked' if row['missing_fields'] else 'ready'
    missing = [dict(error, path='$.units.' + row['unit_id'] + error['path'][1:])
               for row in rows for error in row['missing_fields']]
    return {**status(missing), 'format': 'company-routing-preview/v1', 'read_only': True,
            'units': rows, 'ready': [row['unit_id'] for row in rows if row['status'] == 'ready'],
            'inputs': dict(sorted(inputs.items())), 'source': source, 'configuration_sha256': configuration,
            'limits': LIMITS + ' Supplied context is not authenticated host state or a reservation; '
            'planned unit IDs are never host Task IDs. Recheck each checked launch; no automatic retry. '
            'Launcher --spec-file transport is a separate integration seam; this preview sends nothing.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    item = sub.add_parser('prepare', help='write an exclusive private review bundle, never launch')
    for name in ('record', 'decision', 'spec-file', 'output'):
        item.add_argument('--' + name, type=Path, required=True)
    item.add_argument('--worktree', required=True)
    item.add_argument('--enrollment-request', type=Path, required=True)
    item.add_argument('--expect-enrollment-sha256', required=True)
    item = sub.add_parser('check', help='read-only current revalidation, never launch')
    item.add_argument('bundle', type=Path)
    item = sub.add_parser('preview', help='read-only reviewed DAG projection; no bundle write or launch')
    item.add_argument('--request', type=Path, required=True)
    item.add_argument('--expect-request-sha256', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'preview':
            result = preview(args.request, args.expect_request_sha256)
        else:
            result = prepare(args) if args.command == 'prepare' else check_bundle(args.bundle)
        code = 0 if result['ok'] else 1
    except (ValueError, OSError, KeyError, TypeError, AttributeError, OverflowError, RecursionError) as exc:
        result = status([issue('prepare_input', str(exc))])
        if args.command == 'preview':
            result.update(format='company-routing-preview/v1', read_only=True)
        code = 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
