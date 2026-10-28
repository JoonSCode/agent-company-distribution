#!/usr/bin/env python3
"""Project pinned Orca observations into a new, non-accepted supplementary draft."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import sys

# Select Python's normal cache prefix before importing Company modules.
# Restrict this to the CLI process; callers importing a module are unchanged.
if __name__ == "__main__":
    import os as _os
    import sys as _sys
    _sys.pycache_prefix = _os.path.join(_os.path.abspath(_os.path.expanduser("~")), ".cache", "agent-company", "python")

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from org_audit import InputError, identity, mapping, normalize, sequence, strict_json


def pinned(source, base):
    source = mapping(source)
    if 'file' not in source or set(source) - {'file', 'sha256'}:
        raise InputError('source requires file and optional sha256')
    path = Path(identity(source['file']))
    path = (Path(base) / path).resolve()
    digest = source.get('sha256')
    if digest is not None and (not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest)):
        raise InputError('invalid sha256')
    raw = path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if digest is not None and actual != digest:
        raise InputError('hash mismatch: ' + str(path))
    return strict_json(raw), {'file': str(path), 'sha256': actual}


def project(manifest, base):
    manifest = mapping(manifest)
    if set(manifest) != {'version', 'record', 'launch', 'done', 'binding', 'coverage'}:
        raise InputError('unsupported or missing manifest fields')
    if type(manifest['version']) is not int or manifest['version'] != 1:
        raise InputError('version must be integer 1')
    if manifest['coverage'] not in ('partial', 'declared_complete'):
        raise InputError('invalid coverage')
    binding = mapping(manifest['binding'])
    if set(binding) != {'run', 'task'}:
        raise InputError('selector requires run/task only; other bindings come from the pinned record')
    for value in binding.values():
        identity(value)
    original, record_pin = pinned(manifest['record'], base)
    record = copy.deepcopy(mapping(original))
    if type(record.get('version')) is not int or record.get('version') != 1 or record.get('label') not in ('real', 'synthetic'):
        raise InputError('expected version-1 supplementary record')
    if 'receipt_projection' in record:
        raise InputError('legacy single-task draft requires explicit reconciliation')
    projections = mapping(record.setdefault('receipt_projections', {}))
    if binding['task'] in projections:
        raise InputError('task already has a projection; reconcile explicitly')
    goal = mapping(record.get('goal'))
    if goal.get('status') == 'succeeded':
        raise InputError('cannot project into an accepted-success record')
    tasks = sequence(record.get('tasks'))
    matches = [t for t in tasks if mapping(t).get('id') == binding['task']]
    if len(matches) != 1:
        raise InputError('expected exactly one current task')
    task = matches[0]
    binding = {**binding, 'dispatch': identity(task.get('current_dispatch')),
               'candidate': identity(task.get('candidate')),
               'revision': identity(task.get('goal_revision')),
               'scope': identity(task.get('goal_scope'))}
    if (binding['revision'], binding['scope']) != (goal.get('revision'), goal.get('scope')):
        raise InputError('stale task goal binding')
    mapping(task.get('execution'))  # Declared role actor/lifecycle stay untouched.
    evidence = mapping(record.get('evidence'))
    pins, values = {}, {}
    for name in ('launch', 'done'):
        if name == 'done' and manifest[name] is None:
            values[name] = None
            continue
        values[name], pins[name] = pinned(manifest[name], base)
        eid = 'receipt-projection:' + binding['task'] + ':' + name
        if eid in evidence:
            raise InputError('evidence identity collision: ' + eid)
        evidence[eid] = {'ref': pins[name]['file'], **pins[name],
                         'kind': 'synthetic' if record['label'] == 'synthetic' else 'host'}
    launch = mapping(values['launch'])
    launch_rows = normalize({'id': 'launch', 'format': 'orca_launch'}, launch)
    facts = launch_rows[0]['facts']
    for key, expected in [('run_id', binding['run']), ('task_id', binding['task']),
                          ('dispatch_id', binding['dispatch'])]:
        if facts.get(key) != expected:
            raise InputError('launch binding mismatch: ' + key)
    actor = facts.get('executed_by')
    launch_result = launch['result']
    settings = mapping(launch_result.get('launch', {}))
    model = mapping(task.get('model'))
    if set(model) != {'requested', 'observed', 'effort_requested', 'effort_observed'}:
        raise InputError('invalid model fields')
    observed_model = {}
    for section, fields in [('requested', ('requested', 'effort_requested')),
                            ('effective', ('observed', 'effort_observed'))]:
        observed = mapping(settings.get(section, {}))
        for receipt_key, field in zip(('model', 'effort'), fields):
            value = observed.get(receipt_key)
            if value is not None:
                identity(value)
            if model[field] is not None:
                identity(model[field])
            if model[field] is not None and value is not None and model[field] != value:
                raise InputError('model conflict: ' + field)
            observed_model[field] = value
            if model[field] is None:
                model[field] = value
    observation = {'run': facts['run_id'], 'task': facts['task_id'], 'dispatch': facts['dispatch_id'],
                   'executor_terminal': actor, 'model': observed_model,
                   'launch_state': launch_result.get('state'), 'reported_outcome': None,
                   'message': None, 'basis': 'pinned_receipt_observation',
                   'launch_pointer': '/result', 'done_pointer': None}
    if observation['launch_state'] is not None:
        identity(observation['launch_state'])
    if values['done'] is not None:
        done = mapping(values['done'])
        rows = normalize({'id': 'done', 'format': 'orca_messages'}, done)
        launch_runtime = mapping(launch.get('_meta', {})).get('runtimeId')
        done_runtime = mapping(done.get('_meta', {})).get('runtimeId')
        if launch_runtime is not None and done_runtime is not None and launch_runtime != done_runtime:
            raise InputError('receipt runtime mismatch')
        result = done['result']
        if result.get('runId') != binding['run']:
            raise InputError('done run mismatch')
        page = mapping(result.get('page', {}))
        truncated = any(result.get(k) or page.get(k) for k in ('hasMore', 'nextCursor', 'truncated'))
        total = page.get('total')
        if total is not None and (type(total) is not int or total != len(rows)):
            truncated = True
        if manifest['coverage'] == 'declared_complete' and (truncated or page.get('hasMore') is not False):
            raise InputError('complete coverage requires explicit untruncated pagination')
        candidates = []
        for i, message in enumerate(result['messages']):
            if message.get('type') != 'worker_done':
                continue
            payload = message.get('payload')
            payload = mapping(strict_json(payload) if isinstance(payload, str) else payload)
            message_task = identity(payload.get('taskId'))
            if message_task != binding['task']:
                continue
            if payload.get('dispatchId') != binding['dispatch']:
                raise InputError('stale/mismatched worker_done for selected task')
            if message.get('run_id') != binding['run'] or actor is None or message.get('from_handle') != actor:
                raise InputError('worker_done executor/run mismatch')
            if payload.get('outcome') not in ('succeeded', 'failed'):
                raise InputError('explicit worker_done outcome required')
            candidates.append((i, message, payload))
        if len(candidates) != 1:
            raise InputError('expected exactly one bound worker_done')
        i, message, payload = candidates[0]
        observation.update(reported_outcome=payload['outcome'], message=message['id'],
                           done_pointer='/result/messages/' + str(i))
    elif manifest['coverage'] == 'declared_complete':
        raise InputError('launch-only input cannot claim complete coverage')
    # Keep existing relative evidence valid when the draft moves to another folder.
    record_base = Path(record_pin['file']).parent
    for item in evidence.values():
        item = mapping(item)
        if item.get('file') is not None:
            item['file'] = str((record_base / identity(item['file'])).resolve())
    projections[binding['task']] = {'version': 1, 'status': 'draft', 'input_record': record_pin,
                                    'sources': pins, 'binding': binding, 'coverage': manifest['coverage'],
                                    'observation': observation,
                                    'limits': 'Hashes pin supplied bytes, not authorship. Outcome is a sender report; '
                                              'no acceptance, approval, lifecycle settlement or release inferred.'}
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path, nargs='?', help='optional manifest with explicit SHA-256 pins')
    parser.add_argument('--record', type=Path)
    parser.add_argument('--launch', type=Path)
    parser.add_argument('--done', type=Path)
    parser.add_argument('--run')
    parser.add_argument('--task')
    parser.add_argument('--coverage', choices=('partial', 'declared_complete'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        direct = (args.record, args.launch, args.done, args.run, args.task, args.coverage)
        if args.manifest is not None:
            if any(value is not None for value in direct):
                raise InputError('choose manifest or direct flags, not both')
            manifest = strict_json(args.manifest.read_bytes())
            base = args.manifest.parent
        else:
            if any(value is None for value in (args.record, args.launch, args.run, args.task)):
                raise InputError('direct input requires --record, --launch, --run, --task')
            manifest = {'version': 1, 'coverage': args.coverage or 'partial',
                        'record': {'file': str(args.record)}, 'launch': {'file': str(args.launch)},
                        'done': {'file': str(args.done)} if args.done is not None else None,
                        'binding': {'run': args.run, 'task': args.task}}
            base = Path.cwd()
        record = project(manifest, base)
        # Exclusive creation: existing files, including original inputs, are never replaced.
        with args.output.open('x', encoding='utf-8') as target:
            target.write(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    except (OSError, ValueError, UnicodeError) as exc:
        print(json.dumps({'ok': False, 'status': 'invalid_input', 'error': str(exc)}))
        return 2
    print(json.dumps({'ok': False, 'status': 'draft', 'output': str(args.output),
                      'next': 'Run record_check.py check on this draft; independent judgments remain required.'}))
    return 3


if __name__ == '__main__':
    sys.exit(main())
