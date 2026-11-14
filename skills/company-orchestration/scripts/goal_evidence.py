"""Bounded opt-in goal dependency evidence; structural validation only."""
import json
import os
import stat
from pathlib import Path

MAX_BYTES = 1024 * 1024
MAX_NODES = 4096


def _object(pairs):
    result = {}
    for k, v in pairs:
        if k in result:
            raise ValueError('duplicate JSON field')
        result[k] = v
    return result


def _constant(value):
    raise ValueError('invalid JSON constant')


def _read(base, name):
    if not isinstance(name, str) or not name or '\\' in name or '\x00' in name:
        raise ValueError('invalid sidecar path')
    parts = name.split('/')
    if any(p in ('', '.', '..') for p in parts) or name.startswith('/'):
        raise ValueError('sidecar must be a relative path beneath record directory')
    fd = os.open(base, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        child = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            info = os.fstat(child)
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
                raise ValueError('sidecar must be a bounded regular file')
            data = bytearray()
            while len(data) <= MAX_BYTES:
                chunk = os.read(child, min(65536, MAX_BYTES + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
            if len(data) > MAX_BYTES:
                raise ValueError('sidecar too large')
            return json.loads(data.decode('utf-8'), object_pairs_hook=_object, parse_constant=_constant)
        finally:
            os.close(child)
    finally:
        os.close(fd)


def evaluate(record, base, requested=None):
    declaration = record.get('goal_evidence') if isinstance(record, dict) else None
    if requested is None and declaration is None:
        return {'status': 'not_evaluated'}, []
    errors = []
    def fail(message):
        errors.append({'path': '$.goal_evidence', 'code': 'goal_evidence_invalid', 'message': message})
    try:
        if requested is not None:
            if declaration is not None and declaration != {'mode': 'required', 'path': str(requested)}:
                raise ValueError('requested sidecar differs from record declaration')
            name = str(requested)
        else:
            if not isinstance(declaration, dict) or set(declaration) != {'mode', 'path'} or declaration['mode'] != 'required':
                raise ValueError('expected required sidecar declaration')
            name = declaration['path']
        data = _read(base, name)
        if not isinstance(data, dict) or set(data) != {'format', 'run_id', 'goal', 'tasks'} or data['format'] != 'company-goal-evidence/v1':
            raise ValueError('invalid goal evidence format')
        goal = record.get('goal', {})
        run = record.get('run')
        if not isinstance(run, str) or not run.strip() or data['run_id'] != run or data['goal'] != {k: goal.get(k) for k in ('id', 'revision', 'scope')}:
            raise ValueError('run or goal revision/scope mismatch')
        tasks = record.get('tasks')
        nodes = data['tasks']
        if not isinstance(tasks, list) or not isinstance(nodes, list) or not nodes or len(nodes) > MAX_NODES:
            raise ValueError('invalid task list')
        task_map = {}
        for task in tasks:
            if not isinstance(task, dict) or not isinstance(task.get('id'), str) or task['id'] in task_map:
                raise ValueError('invalid or duplicate record task')
            task_map[task['id']] = task
        node_map = {}
        refs = record.get('evidence')
        if not isinstance(refs, dict):
            raise ValueError('missing record evidence')
        for node in nodes:
            if not isinstance(node, dict) or set(node) != {'task', 'dispatch', 'candidate', 'result_evidence', 'technical_evidence', 'integration_evidence', 'predecessors'}:
                raise ValueError('invalid task evidence shape')
            tid = node['task']
            if not isinstance(tid, str) or tid in node_map or tid not in task_map:
                raise ValueError('unknown or duplicate task')
            task = task_map[tid]
            if node['dispatch'] != task.get('current_dispatch') or node['candidate'] != task.get('candidate') or not node['dispatch'] or not node['candidate']:
                raise ValueError('task dispatch/candidate mismatch')
            for field, source in [('result_evidence', (task.get('execution') or {}).get('result')), ('technical_evidence', task.get('technical')), ('integration_evidence', task.get('parent_integration'))]:
                ref = node[field]
                if not isinstance(ref, str) or not ref or ref not in refs or not isinstance(source, dict) or ref != source.get('evidence'):
                    raise ValueError('task evidence/verification mismatch')
            if not isinstance(node['predecessors'], list) or len(node['predecessors']) > MAX_NODES:
                raise ValueError('invalid predecessors')
            node_map[tid] = node
        if set(node_map) != set(task_map):
            raise ValueError('all current tasks must be represented')
        indegree = {key: 0 for key in node_map}
        outgoing = {key: [] for key in node_map}
        matched_handoffs = []
        for tid, node in node_map.items():
            seen = set()
            for edge in node['predecessors']:
                if not isinstance(edge, dict) or set(edge) != {'task', 'handoff_evidence'}:
                    raise ValueError('missing handoff')
                pred, ref = edge['task'], edge['handoff_evidence']
                if not isinstance(pred, str) or pred not in node_map or pred == tid or pred in seen:
                    raise ValueError('dangling, self or duplicate predecessor')
                handoffs = record.get('handoffs')
                if not isinstance(ref, str) or not ref or ref not in refs or not isinstance(handoffs, list):
                    raise ValueError('missing handoff evidence or record handoffs')
                predecessor = node_map[pred]
                expected = {'evidence': ref, 'from_task': pred,
                            'from_dispatch': predecessor['dispatch'], 'from_candidate': predecessor['candidate'],
                            'to_task': tid, 'to_dispatch': node['dispatch'], 'to_candidate': node['candidate']}
                if handoffs.count(expected) != 1:
                    raise ValueError('handoff is not bound to this task edge')
                if ref in {n[field] for n in nodes for field in ('result_evidence', 'technical_evidence', 'integration_evidence')}:
                    raise ValueError('handoff evidence must be distinct from result, review and integration')
                if any(item['evidence'] == ref for item in matched_handoffs):
                    raise ValueError('handoff evidence reused for another edge')
                matched_handoffs.append(expected)
                seen.add(pred)
                indegree[tid] += 1
                outgoing[pred].append(tid)
        declared_handoffs = record.get('handoffs', [])
        if not isinstance(declared_handoffs, list) or len(declared_handoffs) != len(matched_handoffs):
            raise ValueError('declared handoff missing from dependency graph')
        ready = [key for key, degree in indegree.items() if degree == 0]
        visited = 0
        while ready:
            key = ready.pop()
            visited += 1
            for child in outgoing[key]:
                indegree[child] -= 1
                if indegree[child] == 0:
                    ready.append(child)
        if visited != len(node_map):
            raise ValueError('dependency cycle')
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError) as exc:
        fail(str(exc))
    return {'status': 'invalid' if errors else 'structurally_valid'}, errors
