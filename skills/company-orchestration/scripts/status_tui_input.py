#!/usr/bin/env python3
"""Observe one explicit current Company record; no discovery, writes or approval pins."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
import copy
from graphlib import CycleError, TopologicalSorter
import os
from pathlib import Path
import re
import subprocess
import sys
import time

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import status_tui_data as data
from orca_contract import resolve_orca
from orca_task_graph import task_graph

IDENTITY_FIELDS = ('device', 'inode', 'mode', 'size', 'mtime_ns', 'ctime_ns')


def _run_metadata(executable, runtime, *args):
    try:
        result = subprocess.run(
            [executable, 'orchestration', args[0], '--environment', 'local', *args[1:], '--full', '--json'],
            capture_output=True, timeout=1, check=False,
        )
        if result.returncode or len(result.stdout) > data.MAX_BYTES:
            return {}
        reply = data.obj(data.strict_json(result.stdout))
        if reply.get('ok') is True and data.obj(reply.get('_meta')).get('runtimeId') == runtime:
            return data.obj(reply.get('result'))
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return {}
    return {}


def _launch_settings(executable, runtime, run_id, task):
    task_id, status = task['id'], task['host_status']
    dispatch_id = task['current_dispatch']
    if dispatch_id is None:
        current = _run_metadata(executable, runtime, 'dispatch-show', '--task', task_id).get('dispatch')
        if (not isinstance(current, dict) or
                (current.get('run_id'), current.get('task_id'), current.get('status')) != (run_id, task_id, status)):
            return {}
        dispatch_id = current.get('id')
    if not isinstance(dispatch_id, str) or not dispatch_id.startswith('ctx_'):
        return {}
    worker_reply = _run_metadata(executable, runtime, 'worker-show', '--dispatch', dispatch_id)
    try:
        dispatch = data.obj(worker_reply.get('dispatch'))
        worker = data.obj(worker_reply.get('worker'))
        if (dispatch.get('runId'), dispatch.get('taskId'), dispatch.get('id'), dispatch.get('status'),
                worker.get('dispatchId')) != (run_id, task_id, dispatch_id, status, dispatch_id):
            return {}
        launch = data.obj(data.obj(worker.get('startOptions')).get('launch'))
        settings = {}
        for key in ('requested', 'effective'):
            entry = launch.get(key)
            if entry is not None:
                details = data.obj(entry)
                settings[key] = {field: data.text(details.get(field), True)
                                 for field in ('model', 'effort')}
        return {'current_dispatch': dispatch_id, 'launch_settings': settings}
    except ValueError:
        return {}


def _attach_run_settings(executable, runtime, run_id, tasks, cache):
    if not tasks or not runtime:
        cache.clear()
        return
    reply = _run_metadata(executable, runtime, 'worker-list', '--run', run_id)
    try:
        if data.obj(reply.get('scope')).get('run') != run_id:
            raise data.InputError('wrong worker-list scope')
        workers = {}
        for item in data.rows(reply.get('workers'), 100):
            row = data.obj(item)
            task_id = row.get('taskId')
            if row.get('runId') != run_id:
                raise data.InputError('foreign worker in Orca Run')
            details = (data.text(row.get('dispatchId')), data.text(row.get('dispatchStatus')),
                       data.text(row.get('workerState'), True))
            workers.setdefault(data.text(task_id), []).append(details)
    except ValueError:
        cache.clear()
        return

    now = time.monotonic()
    current = {}
    pending = []
    for task_id, task in tasks.items():
        dispatches = tuple(workers.get(task_id, ()))
        if task['host_status'] in ('pending', 'ready'):
            continue
        key = (runtime, run_id, task_id, task['host_status'], task['current_dispatch'], dispatches)
        if key in cache and cache[key][0] > now:
            current[key] = cache[key]
            task.update(cache[key][1])
        else:
            if key in cache:
                current[key] = cache[key]
            pending.append((key, task))
    if pending:
        # Discover untouched tasks before revisiting expired metadata.
        pending.sort(key=lambda item: item[0] in cache)
        pending = pending[:12]
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = [pool.submit(_launch_settings, executable, runtime, run_id, task) for _, task in pending]
            for (key, task), future in zip(pending, futures):
                details = future.result()
                archived = (details.get('launch_settings') and task['current_dispatch']
                            and task['host_status'] in ('completed', 'failed'))
                current[key] = (float('inf') if archived else now + 10, details)
                task.update(details)
    cache.clear()
    cache.update(current)


def load_run_snapshot(run_id, settings_cache=None):
    """Read one explicit local Orca Run for display, with no record writes."""
    if not re.fullmatch(r'run_[A-Za-z0-9_-]{1,128}', run_id):
        raise data.InputError('invalid Orca Run ID')
    executable = resolve_orca(None)
    try:
        result = subprocess.run(
            [executable, 'orchestration', 'task-list', '--environment', 'local',
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

    meta = reply.get('_meta')
    runtime = meta.get('runtimeId') if isinstance(meta, dict) else None
    _attach_run_settings(executable, runtime if isinstance(runtime, str) else None, run_id, tasks,
                         {} if settings_cache is None else settings_cache)
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


def _attach_orca_tasks(snapshot, run):
    start = time.monotonic_ns()
    try:
        result = subprocess.run(
            [resolve_orca(None), 'orchestration', 'task-list', '--environment', 'local',
             '--run', run, '--json', '--full'],
            capture_output=True, timeout=3, check=True,
        )
        received = time.monotonic_ns()
        if len(result.stdout) > data.MAX_BYTES:
            raise data.InputError('Orca Task capture too large')
        envelope = data.strict_json(result.stdout)
        tasks = task_graph(envelope, run)
        runtime = data.text(data.obj(envelope.get('_meta')).get('runtimeId'))
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise data.InputError('local Orca Task observation unavailable') from exc
    for dep in snapshot['dependencies']:
        if dep['task'] not in tasks or sorted(dep['needs']) != tasks[dep['task']]['needs']:
            raise data.InputError('Orca dependencies differ from attached plan')
    recorded = {task['id']: task for task in snapshot['tasks']}
    rows = []
    for tid, host in tasks.items():
        prior = recorded.get(tid, {})
        dispatch = host['dispatch_id']
        dispatch_unconfirmed = dispatch is None and (
            bool(prior.get('current_dispatch')) and not prior['current_dispatch'].startswith('planned:')
            or host['status'] in ('dispatched', 'completed', 'failed')
        )
        if dispatch is None or prior.get('current_dispatch') != dispatch:
            prior = {key: prior[key] for key in ('classification', 'team_id') if key in prior}
        rows.append({
            **prior, 'id': tid, 'title': host['task_title'] or tid, 'current_dispatch': dispatch,
            'needs': host['needs'], 'state': '?' if prior.get('state') == 'WAIT' else prior.get('state', '?'),
            'host_status': host['status'], 'dispatch_unconfirmed': dispatch_unconfirmed,
            'host_parent_id': host['parent_id'], 'static_eligibility': 'unknown',
        })
    snapshot.update(
        tasks=rows, dependencies=[{'task': tid, 'needs': row['needs'], 'basis': 'orca_task_list'}
                                  for tid, row in tasks.items()],
        dependency_coverage='host', live_host_state='orca_task_list',
        orca_observation={'run': run, 'runtime_id': runtime, 'surface': 'local_task_list'},
        view_timing={'orca_task_list_ns': received - start,
                     'orca_worker_list_ns': None, 'join_ns': time.monotonic_ns() - received},
    )
    snapshot['warnings'] = [warning for warning in snapshot['warnings']
                            if warning not in ('live_host_state:unknown', 'dependency_coverage:unknown')]
    snapshot['warnings'].append('Orca status is a Task observation; worker process and acceptance are separate')


def load_record_snapshot(record_path, metadata_path=None, *, context_path=None, orca_run=None):
    """Pure read-only current-record attachment through the original projection.

    `metadata_path` is an optional *unchanged* manifest-v1 attachment. Its record
    path, declared bytes and revision must match this selected record exactly.
    This never refreshes declared metadata pins or merges with an old snapshot.
    """
    if context_path is not None:
        if metadata_path is not None or orca_run is not None:
            raise data.InputError('planning context is exclusive with metadata and live Orca')
        from status_tui_context import load_context_snapshot
        return load_context_snapshot(record_path, context_path)
    try:
        path = Path(os.path.abspath(record_path))
        observed = data.Sources(path)
        record = data.obj(observed.manifest)
        if type(record.get('version')) is not int or record['version'] != 1:
            raise data.InputError('unsupported Company record version')
        if orca_run is not None and (data.text(orca_run) != record.get('run') or record.get('label') != 'real'):
            raise data.InputError('a real record for the selected Run is required')
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
        if orca_run is not None:
            _attach_orca_tasks(snapshot, orca_run)
        source.unchanged()
        snapshot.update(input_mode='orca' if orca_run is not None else 'record', metadata_attached=metadata_path is not None,
            record_observation=_observation(path, source.tracked[path]),
            input_observations=[_observation(p, value) for p, value in source.tracked.items()])
        snapshot['warnings'].append('current record bytes observed per read; not approval/authentication/process liveness')
        return snapshot
    except data.InputError: raise
    except (ValueError, OSError, TypeError, KeyError, IndexError, RecursionError) as exc:
        raise data.InputError('invalid current record input') from exc
