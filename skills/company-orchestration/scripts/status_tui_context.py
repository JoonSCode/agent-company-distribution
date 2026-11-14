#!/usr/bin/env python3
"""Explicit immutable planning-context capture; never an execution ledger."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import status_tui_data as data

SCHEMA = 'company-status-tui-context/v1'


def _absolute(path):
    return Path(os.path.abspath(path))


def _binding(record):
    goal = data.obj(record.get('goal'))
    return {key: data.text(goal.get(field)) for key, field in (
        ('goal_id', 'id'), ('scope', 'scope'), ('revision', 'revision'))}


def _assignments(record, binding, metadata):
    # Deliberately exclude result/candidate/review/usage/observed serving state.
    from status_tui_input import _models
    models = _models(record, binding)
    attached = {row['id']: row for row in data.rows(metadata.get('tasks'))}
    result, seen = [], set()
    for task in data.rows(record.get('tasks')):
        tid = data.text(data.obj(task).get('id'))
        if tid in seen: raise data.InputError('duplicate context Task')
        seen.add(tid)
        if (task.get('goal_scope'), task.get('goal_revision')) != (binding['scope'], binding['revision']):
            raise data.InputError('context task revision mismatch')
        actor = data.text(data.obj(task.get('execution')).get('actor'), True)
        meta = attached.get(tid)
        if meta is not None:
            if actor is not None and meta['actor'] != actor:
                raise data.InputError('context actor conflicts with record assignment')
            if models[tid] is not None and meta['assigned_model'] not in (None, models[tid]):
                raise data.InputError('context model conflicts with record assignment')
        result.append({'id': tid, 'dispatch': data.text(task.get('current_dispatch')),
                       'actor': actor, 'requested_model': data.obj(task.get('model', {})).get('requested'),
                       'routing_decision': copy.deepcopy(task.get('routing_decision'))})
    return result


def _record_facts(manifest, record):
    """Capture only task identity/explicit plan model facts, never historic stages.

    Mutable record may be task identity evidence, not organization, specialist or
    dependency authority. Other evidence stays in its immutable original source.
    """
    rid = manifest['record']
    def refuse_refs(value):
        if isinstance(value, dict):
            if value.get('source') == rid and set(value) == {'source', 'pointer'}:
                raise data.InputError('record cannot supply persistent organization/assignment evidence')
            for child in value.values(): refuse_refs(child)
        elif isinstance(value, list):
            for child in value: refuse_refs(child)
    refuse_refs(manifest['organization']); refuse_refs(manifest['dependencies'])
    facts = {}
    for task in data.rows(manifest['tasks']):
        refuse_refs(task['specialist'])
        for ref in data.rows(task['evidence']):
            if ref['source'] != rid: continue
            pointer = ref['pointer']
            raw = data.obj(data.pointer(record, pointer))
            # Only the declared current Task object is supported, not arbitrary
            # annotations or old result/acceptance events that happen to name it.
            parts = pointer.split('/')
            if len(parts) != 3 or parts[1] != 'tasks' or raw.get('id') != task['id']:
                raise data.InputError('unsupported mutable-record planning evidence')
            fact = {'id': raw['id']}
            if 'assigned_model' in raw: fact['assigned_model'] = data.text(raw['assigned_model'], True)
            facts[pointer] = fact
    return facts


def _metadata(source, record_path):
    manifest = data.obj(source.manifest)
    selected = [row for row in data.rows(manifest.get('sources'), 256)
                if isinstance(row, dict) and row.get('id') == manifest.get('record')]
    if len(selected) != 1 or selected[0].get('kind') != 'record':
        raise data.InputError('context metadata record missing')
    if _absolute(source.path.parent / data.text(selected[0].get('path'))) != record_path:
        raise data.InputError('context selects a different record path')
    if any(row.get('kind') == 'record' and row is not selected[0] for row in manifest['sources']):
        raise data.InputError('multiple mutable record sources unsupported')
    return manifest, selected[0]


def prepare_context(record_path, metadata_path):
    """Validate the original immutable attachment and prepare a planning capsule."""
    from status_tui_input import load_record_snapshot
    path = _absolute(record_path)
    snapshot = load_record_snapshot(path, metadata_path)
    source = data.Sources(metadata_path)
    manifest, selected = _metadata(source, path)
    for entry in manifest['sources']: source.load(entry)
    source.replay()
    record = data.obj(source.documents[manifest['record']])
    binding = _binding(record)
    assignments = _assignments(record, binding, manifest)
    facts = _record_facts(manifest, record)
    # Static metadata and audited transitive sources stay frozen. Record execution
    # evidence remains the fresh record checker's own explicitly pinned input.
    static = [{'path': str(p), 'sha256': digest} for p, (_, digest) in source.tracked.items() if p != path]

    source.unchanged()
    for observation in snapshot['input_observations']:
        raw, identity = data.read_regular(observation['path'])
        if (hashlib.sha256(raw).hexdigest() != observation['sha256'] or
                identity != tuple(observation['identity'].values())):
            raise data.InputError('capture input changed')
    return {'schema': SCHEMA, 'version': 1, 'binding': binding,
            'record': {'path': str(path), 'captured_sha256': selected['sha256']},
            'metadata': {'path': str(source.path), 'sha256': source.tracked[source.path][1]},
            'assignments': assignments, 'record_facts': facts, 'static_pins': static}


def _new_private_file(path, raw):
    """Exclusive dirfd write in an existing private caller-owned directory.

    No mkdir, overwrite, symlink traversal, or replacement of a pre-existing path.
    The final readback checks name, bytes, inode and parent path before success.
    A failed/raced write is not reported as a valid capture.
    """
    path = _absolute(path)
    directory = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    fd = None
    try:
        for part in path.parts[1:-1]:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory); directory = next_fd
        parent = os.fstat(directory)
        if parent.st_uid != os.getuid() or stat.S_IMODE(parent.st_mode) & 0o077:
            raise data.InputError('context output requires a private caller-owned directory')
        fd = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=directory)
        initial = os.fstat(fd)
        if not stat.S_ISREG(initial.st_mode) or initial.st_uid != os.getuid():
            raise data.InputError('unsafe context output')
        with os.fdopen(fd, 'wb', closefd=False) as stream:
            stream.write(raw); stream.flush(); os.fsync(fd)
        final = os.fstat(fd)
        actual, identity = data.read_regular(path)
        if actual != raw or identity != data._identity(final):
            raise data.InputError('context output changed during capture')
        if (os.stat(path.parent, follow_symlinks=False).st_dev,
            os.stat(path.parent, follow_symlinks=False).st_ino) != (parent.st_dev, parent.st_ino):
            raise data.InputError('context output parent changed')
    except OSError as exc:
        raise data.InputError('context output unavailable, existing or unsafe') from exc
    finally:
        if fd is not None: os.close(fd)
        os.close(directory)


def capture_context(record_path, metadata_path, output_path):
    context = prepare_context(record_path, metadata_path)
    raw = (json.dumps(context, ensure_ascii=False, indent=2) + '\n').encode()
    if len(raw) > data.MAX_BYTES: raise data.InputError('context too large')
    # Recheck all captured inputs immediately before the sole authorized write.
    for pin in [context['metadata'], *context['static_pins'],
                {'path': context['record']['path'], 'sha256': context['record']['captured_sha256']}]:
        content, _ = data.read_regular(pin['path'])
        if hashlib.sha256(content).hexdigest() != data.sha(pin['sha256']):
            raise data.InputError('capture input changed before write')
    _new_private_file(output_path, raw)
    # A source racing the sole write must not receive a success receipt either.
    for pin in [context['metadata'], *context['static_pins'],
                {'path': context['record']['path'], 'sha256': context['record']['captured_sha256']}]:
        content, _ = data.read_regular(pin['path'])
        if hashlib.sha256(content).hexdigest() != data.sha(pin['sha256']):
            raise data.InputError('capture input changed during write')
    return {'schema': SCHEMA, 'sha256': hashlib.sha256(raw).hexdigest(), 'status': 'captured',
            'launch_authorized': False}


class ContextSources(data.Sources):
    facts: dict

    def evidence(self, refs, binding, required=False, kinds=None):
        values = super().evidence(refs, binding, required, kinds)
        # The only frozen record facts are validated task IDs/plan model fields.
        # Fresh record stages are still read by _project_snapshot/build_view.
        return [(sid, self.facts[ref['pointer']] if sid == self.manifest['record'] and ref['pointer'] in self.facts else value)
                for ref, (sid, value) in zip(refs, values)]


def load_context_snapshot(record_path, context_path):
    from status_tui_input import _evidence_inputs, _observation
    try:
        path = _absolute(record_path)
        capsule = data.Sources(context_path)
        context = data.obj(capsule.manifest, {'schema', 'version', 'binding', 'record', 'metadata',
                                             'assignments', 'record_facts', 'static_pins'})
        if context['schema'] != SCHEMA or type(context['version']) is not int or context['version'] != 1:
            raise data.InputError('unsupported planning context')
        provenance = data.obj(context['record'], {'path', 'captured_sha256'})
        data.sha(provenance['captured_sha256'])
        if provenance['path'] != str(path): raise data.InputError('context record path mismatch')
        record_raw = capsule.read(path)
        record = data.obj(data.strict_json(record_raw))
        if type(record.get('version')) is not int or record['version'] != 1:
            raise data.InputError('unsupported Company record version')
        binding = _binding(record)
        if context['binding'] != binding: raise data.InputError('context goal/scope/revision mismatch')
        metadata = data.obj(context['metadata'], {'path', 'sha256'})
        capsule.read(data.text(metadata['path']), metadata['sha256'])
        for pin in data.rows(context['static_pins'], 1024):
            data.obj(pin, {'path', 'sha256'}); capsule.read(data.text(pin['path']), pin['sha256'])
        source = ContextSources(metadata['path'])
        source.tracked.update(capsule.tracked)
        manifest, selected = _metadata(source, path)
        if {k: manifest['binding'][k] for k in binding} != binding:
            raise data.InputError('context metadata binding mismatch')
        if selected['sha256'] != provenance['captured_sha256'] or manifest['binding']['record_sha256'] != selected['sha256']:
            raise data.InputError('context captured record provenance mismatch')
        if _assignments(record, binding, manifest) != context['assignments']:
            raise data.InputError('context Task/Dispatch/actor/model assignment changed')
        if _record_facts(manifest, record) != context['record_facts']:
            raise data.InputError('context task planning source changed')
        source.facts = data.obj(context['record_facts'])
        # Context's explicit mutable-record contract, not --metadata/v1 repinning.
        selected['sha256'] = capsule.tracked[path][1]
        manifest['binding']['record_sha256'] = selected['sha256']
        _evidence_inputs(source, record, path.parent)
        snapshot = data._project_snapshot(source)
        attached_ids = {row['id'] for row in manifest['tasks']}
        from status_tui_input import _models
        models = _models(record, binding)
        for task in snapshot['tasks']:
            if task['id'] not in attached_ids:
                task['title'] = '?'; task['assigned_model'] = models[task['id']]
                task['model_basis'] = 'assigned' if models[task['id']] is not None else 'unknown'
        if snapshot['organization']:
            org = snapshot['organization']
            actors = [org['head']]
            for team in org['teams']: actors.extend([team['lead'], *team['members']])
            for actor in actors:
                if actor is not None: actor['acceptance'] = 'unknown'
        source.unchanged()
        snapshot.update(input_mode='record', context_attached=True, metadata_attached=False,
                        context_provenance=copy.deepcopy(context),
                        record_observation=_observation(path, source.tracked[path]),
                        input_observations=[_observation(p, value) for p, value in source.tracked.items()])
        snapshot['warnings'].append('immutable planning context is not current staffing consent, acceptance or liveness')
        return snapshot
    except data.InputError: raise
    except (ValueError, OSError, TypeError, KeyError, IndexError, RecursionError) as exc:
        raise data.InputError('invalid planning context input') from exc
