#!/usr/bin/env python3
"""Observe one explicit current Company record; no discovery, writes or approval pins."""
from __future__ import annotations
import copy
from graphlib import CycleError, TopologicalSorter
import os
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import status_tui_data as data
from orca_contract import resolve_orca

IDENTITY_FIELDS = ('device', 'inode', 'mode', 'size', 'mtime_ns', 'ctime_ns')


def load_run_snapshot(run_id):
    """Read one explicit local Orca Run for display, with no record writes."""
    if not re.fullmatch(r'run_[A-Za-z0-9_-]{1,128}', run_id):
        raise data.InputError('invalid Orca Run ID')
    try:
        result = subprocess.run(
            [resolve_orca(None), 'orchestration', 'task-list', '--environment', 'local',
             '--run', run_id, '--full', '--brief', '--json'],
            capture_output=True, timeout=2, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise data.InputError('Orca task list unavailable') from exc
    if result.returncode != 0 or len(result.stdout) > data.MAX_BYTES:
        raise data.InputError('Orca refused the selected Run or returned too much data')
    reply = data.obj(data.strict_json(result.stdout))
    if reply.get('ok') is not True:
        raise data.InputError('Orca task list rejected')
    observed = data.obj(reply.get('result'))
    raw_tasks = data.rows(observed.get('tasks'))
    if (observed.get('runId') != run_id or type(observed.get('count')) is not int
            or observed['count'] != len(raw_tasks)):
        raise data.InputError('Orca Run or task count mismatch')

    tasks = {}
    declared_needs = {}
    for raw in raw_tasks:
        row = data.obj(raw)
        task_id = data.text(row.get('id'))
        if row.get('run_id') != run_id or task_id in tasks:
            raise data.InputError('foreign or duplicate task in Orca Run')
        status = data.text(row.get('status'))
        needs = row.get('deps')
        if needs is not None:
            if isinstance(needs, str):
                needs = data.strict_json(needs.encode('utf-8'))
            needs = [data.text(need) for need in data.rows(needs)]
            if len(set(needs)) != len(needs):
                raise data.InputError('duplicate task dependency')
            declared_needs[task_id] = needs
        tasks[task_id] = {
            'id': task_id, 'title': data.text(row.get('task_title') or row.get('display_name') or task_id),
            'state': '?', 'host_status': status, 'needs': declared_needs.get(task_id, []),
            'parent_task': data.text(row.get('parent_id'), True),
            'current_dispatch': data.text(row.get('dispatch_id'), True),
        }
    if any(need not in tasks for needs in declared_needs.values() for need in needs):
        raise data.InputError('task dependency is outside the selected Run')
    try:
        TopologicalSorter(declared_needs).prepare()
    except CycleError as exc:
        raise data.InputError('task dependency cycle') from exc

    return {
        'schema': 'company-status-tui/v1', 'input_mode': 'orca_run',
        'binding': {'run_id': run_id}, 'organization': None, 'tasks': list(tasks.values()),
        'dependencies': [{'task': task_id, 'needs': needs} for task_id, needs in declared_needs.items()],
        'dependency_coverage': ('reported' if tasks and len(declared_needs) == len(tasks)
                                else 'partial' if declared_needs else 'unknown'),
        'sources': [{'kind': 'orca_task_list', 'run_id': run_id}],
        'overall_goal_acceptance': {'earned_success': False, 'badge_kind': 'unknown'},
        'check': {'ok': True, 'scope': 'task_list_response'}, 'live_host_state': 'task_list_observed',
        'observed_overlap': 'unknown',
    }


def _observation(path, tracked):
    identity, digest = tracked
    return {'path': str(path), 'sha256': digest,
            'identity': dict(zip(IDENTITY_FIELDS, identity))}


def _evidence_inputs(source, record, base):
    """Follow only typed, explicit checker inputs, not arbitrary paths in JSON.

    Record evidence.file pins are never re-pinned. Catalog receipt/raw-response
    and refreshed catalog references are transitive inputs of the unchanged
    checker. A declared goal sidecar has observed current bytes, not a new pin.
    Current policy/config/semantic settings remain the checker's own environment,
    not an atomic host snapshot or new discovery/authority mechanism.
    """
    visited = set()

    def pinned(path, digest, depth=0):
        if depth > 4 or len(visited) >= 256:
            raise data.InputError('too many transitive evidence inputs')
        path = Path(os.path.abspath(path))
        raw = source.read(path, data.sha(digest))
        if path in visited: return
        visited.add(path)
        try: document = data.strict_json(raw)
        except data.InputError: return  # Receipts may legitimately be non-JSON text.
        if not isinstance(document, dict): return
        if document.get('format') == 'company-host-catalog-metadata/v1':
            for row in data.rows(document.get('receipts'), 3):
                data.obj(row)
                pinned(path.parent / data.text(row.get('file')), row.get('sha256'), depth+1)
        receipt = document.get('receipt')
        catalog = receipt.get('host_catalog') if isinstance(receipt, dict) else None
        if isinstance(catalog, dict) and 'refreshed_directory' in catalog:
            pinned(base / data.text(catalog['refreshed_directory']) / 'manifest.json',
                   catalog.get('refreshed_manifest_sha256'), depth+1)

    for evidence in data.obj(record.get('evidence')).values():
        if isinstance(evidence, dict) and 'file' in evidence:
            pinned(base / data.text(evidence['file']), evidence.get('sha256'))
    declaration = record.get('goal_evidence')
    if isinstance(declaration, dict) and 'path' in declaration:
        source.read(base / data.text(declaration['path']))


def _models(record, binding):
    """Exact recorded requested/selected assignment only; never observed serving."""
    models = {}
    for task in data.rows(record.get('tasks')):
        data.obj(task)
        tid = data.text(task.get('id'))
        requested = data.text(data.obj(task.get('model', {})).get('requested'), True)
        selected = None
        decision = task.get('routing_decision')
        if decision is not None:
            bound = data.obj(data.obj(decision).get('binding'))
            if (bound.get('task'), bound.get('scope'), bound.get('revision'), bound.get('attempt')) != (
                    tid, binding['scope'], binding['revision'], task.get('current_dispatch')):
                raise data.InputError('stale routing assignment')
            selected = data.text(data.obj(decision.get('selected')).get('model'), True)
        if requested is not None and selected is not None and requested != selected:
            raise data.InputError('requested and selected model contradiction')
        models[tid] = selected or requested
    return models


def load_record_snapshot(record_path, metadata_path=None, *, context_path=None):
    """Pure read-only current-record attachment through the original projection.

    `metadata_path` is an optional *unchanged* manifest-v1 attachment. Its record
    path, declared bytes and revision must match this selected record exactly.
    This never refreshes declared metadata pins or merges with an old snapshot.
    """
    if context_path is not None:
        if metadata_path is not None: raise data.InputError('metadata and context are mutually exclusive')
        from status_tui_context import load_context_snapshot
        return load_context_snapshot(record_path, context_path)
    try:
        path = Path(os.path.abspath(record_path))
        observed = data.Sources(path)
        record = data.obj(observed.manifest)
        if type(record.get('version')) is not int or record['version'] != 1:
            raise data.InputError('unsupported Company record version')
        goal = data.obj(record.get('goal'))
        binding = {key: data.text(goal.get(field)) for key, field in (
            ('goal_id', 'id'), ('scope', 'scope'), ('revision', 'revision'))}
        binding['record_sha256'] = observed.tracked[path][1]
        models = _models(record, binding)
        source = observed
        if metadata_path is None:
            source.manifest = {'schema': 'company-status-tui-input/v1', 'version': 1,
                'binding': binding, 'record': 'record', 'sources': [
                    {'id': 'record', 'path': str(path), 'sha256': binding['record_sha256'], 'kind': 'record'}],
                'organization': None, 'tasks': [], 'dependencies': []}
        else:
            source = data.Sources(metadata_path)
            attachment = data.obj(source.manifest)
            entries = data.rows(attachment.get('sources'), 256)
            selected = [data.obj(row) for row in entries if isinstance(row, dict) and row.get('id') == attachment.get('record')]
            if len(selected) != 1 or selected[0].get('kind') != 'record':
                raise data.InputError('metadata record source missing')
            selected_path = Path(os.path.abspath(source.path.parent / data.text(selected[0].get('path'))))
            if selected_path != path:
                raise data.InputError('metadata selects a different record path')
            # Share the initially observed selected-file identity with the pinned
            # loader, so replacement between these reads rejects even same bytes.
            prior = source.tracked.get(path)
            if prior is not None and prior != observed.tracked[path]:
                raise data.InputError('record changed during attachment')
            source.tracked[path] = observed.tracked[path]
        _evidence_inputs(source, record, path.parent)
        snapshot = data._project_snapshot(source)
        attached_ids = {row['id'] for row in source.manifest['tasks']}
        for task in snapshot['tasks']:
            if task['id'] not in attached_ids:
                task['title'] = '?'
                task['assigned_model'] = models[task['id']]
                task['model_basis'] = 'assigned' if task['assigned_model'] is not None else 'unknown'
        source.unchanged()
        snapshot.update(input_mode='record', metadata_attached=metadata_path is not None,
            record_observation=_observation(path, source.tracked[path]),
            input_observations=[_observation(p, value) for p, value in source.tracked.items()])
        snapshot['warnings'].append('current record bytes observed per read; not approval/authentication/process liveness')
        return snapshot
    except data.InputError: raise
    except (ValueError, OSError, TypeError, KeyError, IndexError, RecursionError) as exc:
        raise data.InputError('invalid current record input') from exc
