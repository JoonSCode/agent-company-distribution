"""Decode the explicit, local Orca task-list contract at the execution boundary."""
from __future__ import annotations

from graphlib import TopologicalSorter

from org_audit import strict_json

STATES = frozenset(('pending', 'ready', 'dispatched', 'completed', 'failed', 'blocked'))


def dependencies(value):
    """Orca 1.4.268 exposes deps as serialized JSON in a full task row."""
    if isinstance(value, str):
        value = strict_json(value)
    if (not isinstance(value, list) or len(value) > 2000
            or any(not isinstance(item, str) or not item.strip() for item in value)
            or len(set(value)) != len(value)):
        raise ValueError('invalid Orca Task dependencies')
    return sorted(value)


def task_graph(envelope, run):
    result = envelope.get('result') if isinstance(envelope, dict) and envelope.get('ok') is True else None
    if not isinstance(result, dict) or result.get('runId') != run:
        raise ValueError('Orca Task capture does not match Run')
    tasks = result.get('tasks')
    page = result.get('page', {})
    if (not isinstance(tasks, list) or len(tasks) > 2000 or type(result.get('count')) is not int
            or result['count'] != len(tasks) or not isinstance(page, dict)
            or any(source.get(key) for source in (result, page) for key in ('hasMore', 'nextCursor', 'truncated'))
            or (page.get('total') is not None and page['total'] != len(tasks))):
        raise ValueError('incomplete Orca Task capture')
    graph = {}
    for task in tasks:
        if not isinstance(task, dict):
            raise ValueError('invalid Orca Task row')
        tid, state = task.get('id'), task.get('status')
        if (not isinstance(tid, str) or not tid.strip() or tid in graph
                or task.get('run_id') != run or not isinstance(state, str) or state not in STATES):
            raise ValueError('invalid or duplicate Orca Task')
        for key in ('parent_id', 'dispatch_id', 'task_title'):
            value = task.get(key)
            if value is not None and (not isinstance(value, str) or len(value) > 4096):
                raise ValueError('invalid Orca Task field')
        graph[tid] = {key: task.get(key) for key in ('id', 'status', 'parent_id', 'dispatch_id', 'task_title')}
        graph[tid]['needs'] = dependencies(task.get('deps'))
    needs = {tid: task['needs'] for tid, task in graph.items()}
    if any(parent not in graph for deps in needs.values() for parent in deps):
        raise ValueError('Orca Task dependency missing from capture')
    order = TopologicalSorter({tid: needs[tid] for tid in sorted(needs)}).static_order()
    return {tid: graph[tid] for tid in order}
