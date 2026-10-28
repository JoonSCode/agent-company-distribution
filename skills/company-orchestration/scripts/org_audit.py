#!/usr/bin/env python3
"""Read-only receipt replay and organization claim audit; never runtime authority."""
from __future__ import annotations

import argparse
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

FIELDS = {
    'run_id', 'scope', 'revision', 'actor', 'requested_by', 'executed_by',
    'accountable_owner', 'team_id', 'decision_id', 'task_id', 'dispatch_id',
    'request_id', 'message_id', 'recipient', 'created_by', 'parent_task_id',
    'from_team', 'to_team', 'occurred_at', 'error_code',
}
REQUIRED = {'run_id', 'scope', 'revision', 'actor', 'accountable_owner', 'team_id',
            'decision_id', 'task_id', 'dispatch_id', 'request_id', 'occurred_at'}
FORMATS = {'orca_tasks', 'orca_task', 'orca_workers', 'orca_launch', 'orca_error',
           'orca_messages', 'orca_message', 'message_extract', 'claims', 'owner_acceptance'}


class InputError(ValueError):
    pass


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise InputError('duplicate JSON key: ' + key)
            result[key] = value
        return result

    def constant(value):
        raise InputError('non-JSON constant: ' + value)

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def mapping(value):
    if not isinstance(value, dict):
        raise InputError('expected object')
    return value


def sequence(value):
    if not isinstance(value, list):
        raise InputError('expected array')
    return value


def identity(value):
    if not isinstance(value, str) or not value.strip():
        raise InputError('expected nonempty identity/string')
    return value


def normalize(source, document):
    """Known receipt envelopes only. Text bodies are never semantic evidence."""
    fmt = source['format']
    document = mapping(document)
    runtime_id = mapping(document.get('_meta', {})).get('runtimeId')
    if runtime_id is not None:
        runtime_id = identity(runtime_id)
    host_key = runtime_id or source.get('host_id') or ('unknown:' + source['id'])
    rows = []
    basis = 'claimed' if fmt in {'claims', 'owner_acceptance'} else 'host_observed'
    if fmt == 'message_extract':
        basis = 'extracted_observation'

    def emit(pointer, entity, facts):
        clean = {}
        for key, value in facts.items():
            if value is not None:
                clean[key] = identity(value)
        rows.append({'ref': source['id'] + '#' + pointer, 'entity': entity,
                     'basis': basis, 'facts': clean,
                     'source_id': source['id'], 'host_key': host_key,
                     'host_id': source.get('host_id'),
                     'captured_at': source.get('captured_at'),
                     'runtime_id': runtime_id})

    def task(pointer, item, request=None):
        item = mapping(item)
        tid = identity(item.get('id'))
        emit(pointer, ['task', identity(item.get('run_id')), tid], {
            'run_id': item.get('run_id'), 'task_id': tid,
            'parent_task_id': item.get('parent_id'),
            'created_by': item.get('created_by_terminal_handle'),
            'occurred_at': item.get('created_at'), 'request_id': request,
        })

    if fmt in {'orca_tasks', 'orca_task', 'orca_workers', 'orca_launch'}:
        if document.get('ok') is not True:
            raise InputError('successful Orca envelope required')
        result = mapping(document.get('result'))
        request = mapping(result.get('mutation', {})).get('requestId')
        if fmt == 'orca_tasks':
            for index, item in enumerate(sequence(result.get('tasks'))):
                task('/result/tasks/' + str(index), item)
        elif fmt == 'orca_task':
            task('/result/task', result.get('task'), request)
        elif fmt == 'orca_workers':
            for index, item in enumerate(sequence(result.get('workers'))):
                item = mapping(item)
                did = identity(item.get('dispatchId'))
                emit('/result/workers/' + str(index), ['dispatch', did], {
                    'run_id': identity(item.get('runId')),
                    'task_id': identity(item.get('taskId')), 'dispatch_id': did,
                    'executed_by': item.get('agentTerminalHandle'),
                })
        else:
            did = identity(result.get('dispatchId'))
            terminals = {identity(e.get('id')) for e in sequence(result.get('effects', []))
                         if isinstance(e, dict) and e.get('kind') == 'terminal'
                         and e.get('role') == 'agent'}
            if len(terminals) > 1:
                raise InputError('ambiguous launch executor')
            emit('/result', ['dispatch', did], {
                'run_id': identity(result.get('runId')),
                'task_id': identity(result.get('taskId')), 'dispatch_id': did,
                'executed_by': next(iter(terminals), None), 'request_id': request,
            })
    elif fmt == 'orca_error':
        if document.get('ok') is not False:
            raise InputError('failed Orca envelope required')
        error = mapping(document.get('error'))
        data = mapping(error.get('data', {}))
        emit('/error', ['error', source['id']], {
            'request_id': data.get('orchestrationRequestId'),
            'error_code': identity(error.get('code')),
        })
    elif fmt in {'orca_messages', 'orca_message'}:
        if document.get('ok') is not True:
            raise InputError('successful Orca envelope required')
        result = mapping(document.get('result'))
        items = ([(f'/result/messages/{i}', item)
                  for i, item in enumerate(sequence(result.get('messages')))]
                 if fmt == 'orca_messages' else [('/result/message', result.get('message'))])
        for pointer, item in items:
            item = mapping(item)
            mid = identity(item.get('id'))
            emit(pointer, ['message', identity(item.get('run_id')), mid], {
                'run_id': item.get('run_id'), 'message_id': mid,
                'actor': item.get('from_handle'), 'recipient': item.get('to_handle'),
                'occurred_at': item.get('created_at'),
            })
        # Payload and body are sender statements, never host-certified semantics.
    elif fmt == 'message_extract':
        for index, item in enumerate(sequence(document.get('messages'))):
            item = mapping(item)
            message = mapping(item.get('message'))
            mid = identity(message.get('id'))
            emit('/messages/' + str(index) + '/message',
                 ['message', identity(message.get('run_id')), mid], {
                     'run_id': message.get('run_id'), 'message_id': mid,
                     'actor': message.get('from_handle'),
                     'recipient': message.get('to_handle'),
                     'occurred_at': message.get('created_at'),
                 })
    elif fmt == 'owner_acceptance':
        emit('', ['owner_claim', source['id']], {
            'accountable_owner': identity(document.get('accepted_by')),
            'scope': identity(document.get('scope')),
            'revision': identity(document.get('revision')),
            'task_id': document.get('task'), 'dispatch_id': document.get('dispatch'),
            'actor': document.get('terminal'), 'occurred_at': document.get('time'),
        })
    else:
        for index, item in enumerate(sequence(document.get('claims'))):
            item = mapping(item)
            if set(item) - FIELDS - {'id'}:
                raise InputError('unsupported claim field')
            emit('/claims/' + str(index), ['claim', identity(item.get('id'))],
                 {key: item[key] for key in FIELDS if key in item})
    return rows


def audit(document, base):
    document = mapping(document)
    if type(document.get('version')) is not int or document['version'] != 1:
        raise InputError('version must be integer 1')
    if document.get('coverage') not in ('partial', 'declared_complete'):
        raise InputError('coverage must be partial or declared_complete')
    issues, observations, sources = [], [], []

    def issue(code, path, detail, severity='unknown'):
        issues.append({'code': code, 'path': path, 'detail': detail, 'severity': severity})

    source_ids = set()
    for index, source in enumerate(sequence(document.get('sources'))):
        path = 'sources/' + str(index)
        source = mapping(source)
        sid = identity(source.get('id'))
        if sid in source_ids:
            issue('duplicate_identity', path, sid, 'invalid')
            continue
        source_ids.add(sid)
        if not isinstance(source.get('format'), str) or source['format'] not in FORMATS:
            issue('unsupported_format', path, sid, 'invalid')
            continue
        identity(source.get('provenance'))
        for metadata in ('captured_at', 'host_id'):
            if source.get(metadata) is not None:
                identity(source[metadata])
        filename = Path(identity(source.get('path')))
        filename = filename if filename.is_absolute() else Path(base) / filename
        expected = identity(source.get('sha256'))
        try:
            raw = filename.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            if digest != expected:
                issue('hash_mismatch', path, sid, 'invalid')
                continue
            content = strict_json(raw)
            rows = normalize(source, content)
        except (OSError, ValueError, UnicodeError) as exc:
            issue('unreadable_source', path, type(exc).__name__ + ': ' + str(exc), 'invalid')
            continue
        sources.append({**source, 'resolved_path': str(filename.resolve()), 'verified_sha256': digest})
        local_ids = set()
        for row in rows:
            key = tuple(row['entity'])
            if key in local_ids:
                issue('duplicate_identity', row['ref'], repr(key), 'invalid')
            local_ids.add(key)
        observations.extend(rows)
        if source['format'] in {'orca_tasks', 'orca_workers', 'orca_messages'}:
            result = content['result']
            page = result.get('page')
            truncated = any(result.get(key) for key in ('hasMore', 'nextCursor', 'truncated'))
            if isinstance(page, dict):
                truncated = truncated or any(page.get(key) for key in ('hasMore', 'nextCursor', 'truncated'))
                total = page.get('total')
                if type(total) is int and total > len(rows):
                    truncated = True
            if truncated:
                issue('incomplete_capture', path, 'more pages or truncation reported')
            elif not isinstance(page, dict) or page.get('hasMore') is not False or page.get('nextCursor') is not None:
                issue('capture_coverage_unknown', path, 'no explicit terminal page metadata')
        if not rows:
            issue('empty_source', path, sid)

    # Immutable identities may repeat in different snapshots; status/time may change.
    stable = {}
    for row in observations:
        if row['basis'] == 'claimed':
            continue
        for field in {'run_id', 'task_id', 'dispatch_id', 'executed_by', 'created_by', 'parent_task_id', 'actor', 'recipient'}:
            if field not in row['facts']:
                continue
            key = (row['host_key'], *row['entity'], field)
            value = row['facts'][field]
            if key in stable and stable[key] != value:
                issue('identity_contradiction', row['ref'], field, 'contradiction')
            stable[key] = value
    by_ref = {row['ref']: row for row in observations}
    events, by_id = [], {}
    for index, event in enumerate(sequence(document.get('events'))):
        event = mapping(event)
        path = 'events/' + str(index)
        eid = identity(event.get('id'))
        identity(event.get('kind'))  # Kind is a claimed interpretation, never a proven meeting.
        if set(event) - FIELDS - {'id', 'kind', 'evidence', 'depends_on'}:
            issue('unsupported_field', path, eid, 'invalid')
        if eid in by_id:
            issue('duplicate_identity', path, eid, 'invalid')
            continue
        by_id[eid] = event
        linked = []
        for ref in sequence(event.get('evidence')):
            identity(ref)
            if ref not in by_ref:
                issue('missing_evidence', path, ref)
            else:
                linked.append(by_ref[ref])
        if not linked:
            issue('missing_evidence', path, eid)
        checks = {}
        for field in sorted(REQUIRED | (set(event) & FIELDS)):
            value = event.get(field)
            if value is None:
                checks[field] = 'unknown'
                issue('missing_field' if field not in event else 'unknown_field', path + '/' + field, eid)
                continue
            identity(value)
            observed = [r for r in linked if r['basis'] != 'claimed' and field in r['facts']]
            claimed = [r for r in linked if r['basis'] == 'claimed' and field in r['facts']]
            if any(r['facts'][field] != value for r in observed):
                checks[field] = 'contradiction'
                issue('contradiction', path + '/' + field, eid, 'contradiction')
            elif observed:
                checks[field] = ('host_observed' if any(r['basis'] == 'host_observed' for r in observed)
                                 else 'extracted_observation')
            elif any(r['facts'][field] != value for r in claimed):
                checks[field] = 'claim_contradiction'
                issue('claim_contradiction', path + '/' + field, eid, 'contradiction')
            elif claimed:
                checks[field] = 'claimed'
                issue('claim_only', path + '/' + field, eid, 'claim')
            else:
                checks[field] = 'unsupported'
                issue('unsupported_claim', path + '/' + field, eid)
        events.append({'event': event, 'field_status': checks, 'kind_status': 'claimed'})

    expected = sequence(document.get('expected_events'))
    if len({identity(e) for e in expected}) != len(expected):
        issue('duplicate_identity', 'expected_events', 'event IDs', 'invalid')
    for eid in expected:
        if eid not in by_id:
            issue('missing_event', 'expected_events', eid)
    for eid, event in by_id.items():
        for dep in sequence(event.get('depends_on', [])):
            if identity(dep) not in by_id:
                issue('missing_dependency', eid, dep)
    # Arrival order is immaterial; only explicit logical dependencies are checked.
    visiting, visited = set(), set()
    def visit(eid):
        if eid in visiting:
            issue('dependency_cycle', eid, eid, 'invalid')
            return
        if eid in visited or eid not in by_id:
            return
        visiting.add(eid)
        for dep in by_id[eid].get('depends_on', []):
            visit(dep)
        visiting.remove(eid)
        visited.add(eid)
    for eid in by_id:
        visit(eid)
    if not events:
        issue('missing_events', 'events', 'no event claims supplied')
    if document['coverage'] == 'partial':
        issue('partial_coverage', 'coverage', 'absence cannot prove non-occurrence')
    inconsistent = any(i['severity'] in {'invalid', 'contradiction'} for i in issues)
    unknown = any(i['severity'] == 'unknown' for i in issues)
    return {'version': 1, 'status': 'inconsistent' if inconsistent else ('incomplete' if unknown else 'consistent_with_evidence'),
            'coverage': document['coverage'], 'issues': issues, 'sources': sources,
            'observations': observations, 'events': events,
            'limits': ['Caller-declared provenance and hashes do not authenticate host origin.',
                       'Event kinds, decisions, owner acceptance and team semantics require source review.',
                       'No hierarchy enforcement, launch interception, or proof of overall workflow completion.']}


def import_handoff(document, base):
    """Explicit typed boundary: import facts, retain AI declarations as claims."""
    document = mapping(document)
    if set(document) != {'schema', 'version', 'coverage', 'sources', 'declarations'}:
        raise InputError('handoff requires only schema/version/coverage/sources/declarations')
    if document['schema'] != 'company-org-handoff':
        raise InputError('unsupported handoff schema')
    if type(document['version']) is not int or document['version'] != 1:
        raise InputError('handoff version must be integer 1')
    sources = []
    for source in sequence(document['sources']):
        source = mapping(source)
        required = {'id', 'path', 'format', 'provenance'}
        if not required <= set(source) or set(source) - required - {'sha256', 'captured_at', 'host_id'}:
            raise InputError('unsupported or missing source field')
        for key in required:
            identity(source[key])
        if '#' in source['id']:
            raise InputError('source id cannot contain #')
        for key in ('captured_at', 'host_id'):
            if source.get(key) is not None:
                identity(source[key])
        source = dict(source)
        if 'sha256' in source:
            if not isinstance(source['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', source['sha256']):
                raise InputError('sha256 must be 64 lowercase hexadecimal characters')
        else:
            filename = Path(source['path'])
            filename = filename if filename.is_absolute() else Path(base) / filename
            source['sha256'] = hashlib.sha256(filename.read_bytes()).hexdigest()
        sources.append(source)
    declarations = sequence(document['declarations'])
    for declaration in declarations:
        declaration = mapping(declaration)
        if not {'id', 'kind', 'evidence'} <= set(declaration) or set(declaration) - FIELDS - {'id', 'kind', 'evidence', 'depends_on'}:
            raise InputError('unsupported or missing declaration field')
        identity(declaration['id'])
        identity(declaration['kind'])
        for key in FIELDS & set(declaration):
            if declaration[key] is not None:
                identity(declaration[key])
        for key in ('evidence', 'depends_on'):
            for value in sequence(declaration.get(key, [])):
                identity(value)
    report = audit({'version': 1, 'coverage': document['coverage'], 'sources': sources,
                    'events': declarations, 'expected_events': []}, base)
    drafts = []
    for row in report['observations']:
        if row['basis'] != 'host_observed':
            continue
        draft = dict.fromkeys(sorted(REQUIRED))
        draft.update(row['facts'])
        draft.update(id=row['ref'], kind=next(s['format'] for s in sources if s['id'] == row['source_id']),
                     evidence=[row['ref']], depends_on=[])
        drafts.append(draft)
    report['declarations'] = report.pop('events')
    return {'schema': 'company-org-import', **report, 'draft_events': drafts}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    importing = bool(argv and argv[0] == 'import')
    if importing:
        argv.pop(0)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    args = parser.parse_args(argv)
    try:
        operation = import_handoff if importing else audit
        result = operation(strict_json(args.manifest.read_bytes()), args.manifest.parent)
    except (OSError, ValueError, UnicodeError) as exc:
        print(json.dumps({'status': 'invalid_input', 'error': str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return {'consistent_with_evidence': 0, 'inconsistent': 1, 'incomplete': 3}[result['status']]


if __name__ == '__main__':
    sys.exit(main())
