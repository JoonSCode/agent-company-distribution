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
    args = parser.parse_args(argv)
    try:
        result = prepare(args) if args.command == 'prepare' else check_bundle(args.bundle)
        code = 0 if result['ok'] else 1
    except (ValueError, OSError, KeyError, TypeError, AttributeError, OverflowError, RecursionError) as exc:
        result = status([issue('prepare_input', str(exc))])
        code = 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
