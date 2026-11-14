#!/usr/bin/env python3
"""Source-bound, read-only Company organization/task projection. No discovery or scheduler."""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import org_audit
import status_view

KINDS = {'record', 'org_manifest', 'org_handoff', 'claims', 'plan', 'registry', 'assignment', 'observation'}
FAMILIES = {'general', 'language', 'structured_data', 'reasoning', 'code', 'research',
            'visual', 'design', 'media_generation', 'tool_use'}
MAX_BYTES = 16 * 1024 * 1024
MAX_ROWS = 2000


class InputError(ValueError):
    """Invalid attachment/binding. The CLI emits a bounded diagnostic, not raw input."""


def obj(value, keys=None):
    if not isinstance(value, dict): raise InputError('expected object')
    if keys is not None and set(value) != set(keys): raise InputError('missing or unsupported fields')
    return value


def rows(value, limit=MAX_ROWS):
    if not isinstance(value, list) or len(value) > limit: raise InputError('expected bounded array')
    return value


def text(value, nullable=False):
    if value is None and nullable: return None
    if not isinstance(value, str) or not value.strip() or len(value) > 4096:
        raise InputError('expected bounded nonempty string')
    return value


def sha(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-fA-F]{64}', value):
        raise InputError('invalid SHA256')
    return value.lower()


def strict_json(raw):
    try: return org_audit.strict_json(raw)
    except (ValueError, UnicodeError, RecursionError) as exc: raise InputError('invalid strict JSON') from exc


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def read_regular(path):
    """Walk using dirfds/O_NOFOLLOW; no symlink component, FIFO/device, or race read."""
    path = Path(os.path.abspath(path))
    directory = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:-1]:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory); directory = next_fd
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_BYTES:
                raise InputError('source is not a bounded regular file')
            chunks, length = [], 0
            while True:
                block = os.read(fd, min(65536, MAX_BYTES + 1 - length))
                if not block: break
                chunks.append(block); length += len(block)
                if length > MAX_BYTES: raise InputError('source too large')
            if _identity(before) != _identity(os.fstat(fd)):
                raise InputError('source changed while reading')
            raw = b''.join(chunks)
        finally: os.close(fd)
        if _identity(before) != _identity(os.stat(path.name, dir_fd=directory, follow_symlinks=False)):
            raise InputError('source replaced while reading')
        return raw, _identity(before)
    except OSError as exc:
        raise InputError('source unavailable or unsafe') from exc
    finally: os.close(directory)


def pointer(document, path):
    if not isinstance(path, str) or (path and not path.startswith('/')):
        raise InputError('invalid RFC6901 pointer')
    if not path: return document
    value = document
    for raw in path[1:].split('/'):
        if re.search(r'~(?![01])', raw): raise InputError('invalid RFC6901 escape')
        key = raw.replace('~1', '/').replace('~0', '~')
        if isinstance(value, dict) and key in value: value = value[key]
        elif isinstance(value, list) and re.fullmatch('0|[1-9][0-9]*', key) and int(key) < len(value): value = value[int(key)]
        else: raise InputError('evidence pointer missing')
    return value


class Sources:
    def __init__(self, path):
        self.path = Path(os.path.abspath(path))
        self.tracked = {}
        self.documents, self.entries, self.audits = {}, {}, []
        self.manifest = strict_json(self.read(self.path))

    def read(self, path, expected=None):
        path = Path(os.path.abspath(path))
        raw, identity = read_regular(path)
        digest = hashlib.sha256(raw).hexdigest()
        if expected is not None and digest != sha(expected): raise InputError('source hash mismatch')
        prior = self.tracked.get(path)
        if prior and prior != (identity, digest): raise InputError('source changed during snapshot')
        self.tracked[path] = (identity, digest)
        return raw

    def unchanged(self):
        # Check every input again after checker/audit replay; never merge torn snapshots.
        for path, (identity, digest) in list(self.tracked.items()):
            raw, current = read_regular(path)
            if identity != current or hashlib.sha256(raw).hexdigest() != digest:
                raise InputError('source changed during projection')

    def load(self, source):
        obj(source, {'id', 'path', 'sha256', 'kind'})
        sid = text(source['id'])
        if sid in self.entries: raise InputError('duplicate source ID')
        if source['kind'] not in KINDS: raise InputError('unknown source kind')
        path = self.path.parent / text(source['path'])
        raw = self.read(path, source['sha256'])
        self.documents[sid] = strict_json(raw)
        self.entries[sid] = {**source, 'resolved_path': str(Path(os.path.abspath(path))),
                             'sha256': hashlib.sha256(raw).hexdigest()}

    def replay(self):
        # Original audit/import functions remain authoritative. Verify explicit nested
        # file references before/after they reopen them; hashes are not authentication.
        for sid, source in self.entries.items():
            if source['kind'] not in {'org_manifest', 'org_handoff'}: continue
            document = obj(self.documents[sid])
            base = Path(source['resolved_path']).parent
            for nested in rows(document.get('sources')):
                obj(nested)
                if 'sha256' not in nested: raise InputError('audit source pin required')
                self.read(base / text(nested.get('path')), nested['sha256'])
            operation = org_audit.import_handoff if source['kind'] == 'org_handoff' else org_audit.audit
            try: report = operation(document, base)
            except (ValueError, OSError, TypeError, KeyError) as exc: raise InputError('invalid org audit input') from exc
            if report['status'] == 'inconsistent': raise InputError('organization audit contradiction')
            self.audits.append({'source': sid, 'report': report})

    def evidence(self, refs, binding, required=False, kinds=None):
        values = []
        for ref in rows(refs, 256):
            obj(ref, {'source', 'pointer'})
            sid = text(ref['source'])
            if sid not in self.entries: raise InputError('evidence source missing')
            if kinds and self.entries[sid]['kind'] not in kinds: raise InputError('wrong evidence kind')
            document = self.documents[sid]
            value = pointer(document, ref['pointer'])
            if binding:
                candidates = [value, document]
                if isinstance(document, dict): candidates += [document.get('goal'), document.get('binding')]
                bound = False
                for candidate in candidates:
                    if not isinstance(candidate, dict): continue
                    if 'scope' in candidate or 'revision' in candidate:
                        if (candidate.get('scope'), candidate.get('revision')) != (binding['scope'], binding['revision']):
                            raise InputError('evidence scope/revision mismatch')
                        bound = True
                        break
                if not bound: raise InputError('evidence scope/revision missing')
            values.append((sid, value))
        if required and not values: raise InputError('explicit evidence required')
        return values


def _actor_context(document, path):
    """Recognize organization slots, not arbitrary equal actor strings.

    RFC6901 ancestry is evidence: teams[i].lead/members[j] carries that exact
    enclosing team's ID. A scalar /actor child retains its structured parent.
    An arbitrary event needs explicit relation/role and team_id instead.
    """
    parts = path.split('/')[1:] if path else []
    if parts and parts[-1] == 'actor': parts = parts[:-1]
    node_path = '/' + '/'.join(parts) if parts else ''
    node = pointer(document, node_path)
    roles, teams = [], []
    if isinstance(node, dict):
        for key in ('relation', 'role'):
            if key in node: roles.append(text(node[key]))
        if 'team_id' in node: teams.append(text(node['team_id'], True))
    if parts and parts[-1] == 'head':
        parent = pointer(document, '/' + '/'.join(parts[:-1]) if parts[:-1] else '')
        if isinstance(parent, dict) and isinstance(parent.get('teams'), list):
            roles.append('head'); teams.append(None)
    offset = 1 if parts and parts[-1] == 'lead' else 2 if len(parts) >= 2 and parts[-2] == 'members' and re.fullmatch('0|[1-9][0-9]*', parts[-1]) else 0
    if offset:
        prefix = parts[:-offset]
        if len(prefix) >= 2 and prefix[-2] == 'teams' and re.fullmatch('0|[1-9][0-9]*', prefix[-1]):
            team = obj(pointer(document, '/' + '/'.join(prefix)))
            roles.append('lead' if offset == 1 else 'member')
            identifiers = [text(team[k]) for k in ('id', 'team_id') if k in team]
            teams.extend(identifiers)
    return node, roles, teams


def _actor(source, binding, value, team_id=None, relation=None):
    if value is None: return None
    obj(value, {'actor', 'evidence'})
    actor = text(value['actor'])
    evidence = source.evidence(value['evidence'], binding)
    matches = []
    for ref, (sid, raw) in zip(value['evidence'], evidence):
        node, roles, teams = _actor_context(source.documents[sid], ref['pointer'])
        identity = node.get('actor', node.get('accepted_by')) if isinstance(node, dict) else raw
        if identity != actor: raise InputError('actor evidence contradiction')
        if any(role != relation for role in roles) or any(team != team_id for team in teams):
            raise InputError('actor relation/team evidence contradiction')
        # Missing team is not the requested team. Missing role is not membership.
        if roles and (teams or relation == 'head'): matches.append(node)
    # Even a valid claim is not consent/authenticated staffing. An explicit accepted
    # interpretation can be retained as claimed, never upgraded to host_observed.
    accepted = any(isinstance(v, dict) and (v.get('accepted_by') == actor or v.get('status') == 'accepted') for v in matches)
    return {**value, 'actor': actor if matches else None, 'declared_actor': actor,
            'basis': 'claimed' if matches else 'unknown', 'acceptance': 'claimed' if accepted else 'unknown',
            'relation': relation}


def organization(source, binding, raw):
    if raw is None: return None
    obj(raw, {'head', 'teams'})
    head = _actor(source, binding, raw['head'], relation='head')
    teams, seen = [], set()
    for team in rows(raw['teams']):
        obj(team, {'id', 'label', 'lead', 'members', 'evidence'})
        tid, label = text(team['id']), text(team['label'])
        if tid in seen: raise InputError('duplicate team ID')
        seen.add(tid)
        values = source.evidence(team['evidence'], binding)
        if values and not any(isinstance(v, dict) and (v.get('id') == tid or v.get('team_id') == tid) for _, v in values):
            raise InputError('team evidence contradiction')
        lead = _actor(source, binding, team['lead'], tid, 'lead')
        members, member_ids = [], set()
        for member in rows(team['members']):
            projected = _actor(source, binding, member, tid, 'member')
            if projected is None: raise InputError('null member')
            aid = projected['declared_actor']
            if aid in member_ids: raise InputError('duplicate member ID')
            member_ids.add(aid); members.append(projected)
        teams.append({**team, 'lead': lead, 'members': members,
                      'basis': 'claimed' if values else 'unknown'})
    return {'head': head, 'teams': teams, 'basis': 'claimed', 'staffing_observed': False}


def _native_ids(source):
    ids = set()
    for sid, entry in source.entries.items():
        if entry['kind'] != 'registry': continue
        document = obj(source.documents[sid])
        # Registry is the pinned agents/*.json profile shape, not a fuzzy role/skill.
        name = text(obj(document.get('native_agent')).get('name'))
        text(document.get('id'))
        if name in ids: raise InputError('ambiguous registry native ID')
        ids.add(name)
    return ids


def _specialist(source, binding, raw, task, registry):
    obj(raw, {'status', 'id', 'evidence'})
    status = raw['status']
    if status not in {'assigned', 'none', 'unknown'}: raise InputError('invalid specialist status')
    evidence = source.evidence(raw['evidence'], binding, required=status != 'unknown')
    if status == 'assigned':
        specialist = text(raw['id'])
        if specialist not in registry: raise InputError('unregistered native specialist')
    else:
        specialist = None
        if raw['id'] is not None: raise InputError('non-assigned specialist ID')
    if status != 'unknown':
        matched = False
        for sid, item in evidence:
            if source.entries[sid]['kind'] not in {'assignment', 'claims'} or not isinstance(item, dict): continue
            if (item.get('task', item.get('task_id')) == task['id'] and
                item.get('dispatch', item.get('dispatch_id')) == task.get('current_dispatch') and
                item.get('actor') == task.get('assigned_actor') and 'specialist' in item and
                item['specialist'] == specialist): matched = True
        if not matched: raise InputError('specialist assignment not current-bound')
    return copy.deepcopy(raw)


def _state(task):
    stages = task['stages']
    execution = stages['execution']
    if any(s['badge_kind'] == 'error' for s in stages.values()): return 'FAIL', 'checker stage error'
    if task['errors']: return 'ERR', 'checker task errors'
    if all(s['earned_success'] for s in stages.values()): return 'ACC', '기록상 제출·독립 기술·상위 통합 통과'
    if execution['earned_success']: return 'SUB', '제출됨; 독립 기술/상위 통합 대기'
    if execution['state'] == 'live': return '?', '기록 live; 실행 관측 없음'
    return '?', '실행 관측 없음'


def load_snapshot(manifest_path):
    """Validate a single explicit attachment and replay existing checkers, without writes.

    InputError rejects torn/contradictory attachments. Record checker errors are
    retained in `check` and stages instead of turning them into false success.
    """
    try: return _load_snapshot(manifest_path)
    except InputError: raise
    except (ValueError, OSError, TypeError, KeyError, IndexError, RecursionError) as exc:
        raise InputError('invalid projection input') from exc


def _load_snapshot(manifest_path):
    return _project_snapshot(Sources(manifest_path))


def _project_snapshot(source):
    # Shared pure projection; record mode supplies an in-memory attachment while
    # manifest mode keeps the original declared pins and strict schema unchanged.
    document = obj(source.manifest, {'schema', 'version', 'binding', 'sources', 'record', 'organization', 'tasks', 'dependencies'})
    if document['schema'] != 'company-status-tui-input/v1' or type(document['version']) is not int or document['version'] != 1:
        raise InputError('unsupported input schema/version')
    binding = obj(document['binding'], {'goal_id', 'scope', 'revision', 'record_sha256'})
    for key in ('goal_id', 'scope', 'revision'): text(binding[key])
    sha(binding['record_sha256'])
    for entry in rows(document['sources'], 256): source.load(entry)
    rid = text(document['record'])
    if rid not in source.entries or source.entries[rid]['kind'] != 'record': raise InputError('record source missing')
    entry = source.entries[rid]
    if entry['sha256'] != sha(binding['record_sha256']): raise InputError('record binding hash mismatch')
    record = obj(source.documents[rid])
    goal = obj(record.get('goal'))
    if (goal.get('id'), goal.get('scope'), goal.get('revision')) != (binding['goal_id'], binding['scope'], binding['revision']):
        raise InputError('record goal binding mismatch')
    record_base = Path(entry['resolved_path']).parent
    # Evidence files are explicitly referenced/pinned by the original record (no
    # directory/session discovery). Keep these transitive pins in sources as well.
    for evidence in obj(record.get('evidence')).values():
        if isinstance(evidence, dict) and 'file' in evidence:
            source.read(record_base / text(evidence['file']), sha(evidence.get('sha256')))
    raw_tasks, task_map = rows(record.get('tasks')), {}
    for task in raw_tasks:
        obj(task); tid = text(task.get('id'))
        if tid in task_map: raise InputError('duplicate record task ID')
        if (task.get('goal_scope'), task.get('goal_revision')) != (binding['scope'], binding['revision']):
            raise InputError('task current revision mismatch')
        task_map[tid] = task
    source.replay()
    org = organization(source, binding, document['organization'])
    team_ids = {team['id'] for team in org['teams']} if org else set()
    registry = _native_ids(source)
    metadata = {}
    for attached in rows(document['tasks']):
        obj(attached, {'id', 'title', 'classification', 'team_id', 'actor', 'assigned_model', 'specialist', 'evidence'})
        tid = text(attached['id'])
        if tid in metadata or tid not in task_map: raise InputError('duplicate/orphan task attachment')
        text(attached['title']); text(attached['team_id'], True); text(attached['actor'], True)
        model = text(attached['assigned_model'], True)
        if attached['classification'] is not None and attached['classification'] not in FAMILIES: raise InputError('unsupported task classification')
        if attached['team_id'] is not None and attached['team_id'] not in team_ids: raise InputError('orphan task team')
        evidence = source.evidence(attached['evidence'], binding, required=True)
        if not any(isinstance(v, dict) and (v.get('id') == tid or v.get('task', v.get('task_id')) == tid) for _, v in evidence):
            raise InputError('task evidence ID mismatch')
        task = task_map[tid]
        requested = obj(task.get('model', {})).get('requested')
        decision = task.get('routing_decision')
        selected = None
        if isinstance(decision, dict):
            db = obj(decision.get('binding'))
            if (db.get('task'), db.get('scope'), db.get('revision'), db.get('attempt')) != (tid,binding['scope'],binding['revision'],task.get('current_dispatch')):
                raise InputError('stale routing assignment')
            selected = obj(decision.get('selected')).get('model')
        known = [m for m in (requested, selected) if m is not None]
        if model is not None and any(m != model for m in known): raise InputError('assigned model conflicts with record/router')
        model_basis = 'assigned' if model is not None and known else 'unknown'
        if model is not None and not known:
            if not any(isinstance(v, dict) and v.get('assigned_model') == model for _, v in evidence):
                raise InputError('plan-only model evidence missing')
            model_basis = 'planned'
        meta = {**attached, 'assigned_actor': attached['actor'], 'model_basis': model_basis,
                'assignment_basis': 'claimed'}
        meta['specialist'] = _specialist(source, binding, attached['specialist'],
                                       {**task, 'assigned_actor': attached['actor']}, registry)
        metadata[tid] = meta
    dependencies, needs_map = [], {}
    for dep in rows(document['dependencies']):
        obj(dep, {'task', 'needs', 'evidence'})
        tid = text(dep['task']); needs = rows(dep['needs'])
        if tid not in task_map or tid in needs_map: raise InputError('orphan/duplicate dependency consumer')
        for need in needs: text(need)
        if len(set(needs)) != len(needs) or tid in needs or any(n not in task_map for n in needs):
            raise InputError('duplicate/self/orphan dependency')
        evidence = source.evidence(dep['evidence'], binding, required=True, kinds={'plan'})
        if not any(isinstance(v, dict) and v.get('task') == tid and v.get('needs') == needs for _, v in evidence):
            raise InputError('dependency differs from pinned plan')
        needs_map[tid] = list(needs); dependencies.append(copy.deepcopy(dep))
    # Kahn rather than recursive DFS, so a bounded long DAG is not stack-dependent.
    pending = {tid: set(needs_map.get(tid, [])) for tid in task_map}
    ready = [tid for tid, needs in pending.items() if not needs]
    reverse = {tid: [] for tid in task_map}
    for tid, needs in pending.items():
        for need in needs: reverse[need].append(tid)
    visited = 0
    while ready:
        tid = ready.pop(); visited += 1
        for child in reverse[tid]:
            pending[child].remove(tid)
            if not pending[child]: ready.append(child)
    if visited != len(task_map): raise InputError('task dependency cycle')
    view = status_view.build_view(record, record_path=entry['resolved_path'], record_sha256=entry['sha256'], base=record_base)
    projected = []
    for task in view['tasks']:
        tid = task['id']
        meta = metadata.get(tid, {'id': tid, 'title': tid, 'classification': None, 'team_id': None,
                                 'actor': None, 'assigned_actor': None, 'assigned_model': None,
                                 'model_basis': 'unknown', 'assignment_basis': 'unknown', 'evidence': [],
                                 'specialist': {'status': 'unknown', 'id': None, 'evidence': []}})
        state, note = _state(task)
        projected.append({**meta, 'current_dispatch': task['current_dispatch'], 'candidate': task['candidate'],
                          'stages': task['stages'], 'errors': task['errors'], 'state': state, 'state_note': note,
                          'needs': needs_map.get(tid, []), 'static_eligibility': 'unknown'})
    by_id = {task['id']: task for task in projected}
    for task in projected:
        if task['id'] in needs_map:
            satisfied = all(by_id[n]['state'] == 'ACC' for n in task['needs'])
            task['static_eligibility'] = 'recorded_prerequisites_met' if satisfied else 'recorded_prerequisites_unmet'
            if not satisfied and task['state'] == '?': task.update(state='WAIT', state_note='선언 needs 미충족; 실행 생존 별도 unknown')
    warnings = ['hashes verify bytes, not consent or host origin', 'live_host_state:unknown', 'observed_overlap:unknown']
    if org is None: warnings.append('organization:unknown')
    if not dependencies: warnings.append('dependency_coverage:unknown')
    warnings.extend('org_audit:' + audit['report']['status'] for audit in source.audits if audit['report']['status'] != 'consistent_with_evidence')
    source.unchanged()
    return {'schema': 'company-status-tui/v1', 'binding': copy.deepcopy(binding), 'organization': org,
            'tasks': projected, 'dependencies': dependencies, 'dependency_coverage': 'partial' if dependencies else 'unknown',
            'warnings': warnings, 'sources': [dict(entry) for entry in source.entries.values()],
            'input_pins': [{'path': str(path), 'sha256': digest} for path, (_, digest) in source.tracked.items()],
            'org_audits': source.audits, 'goal': view['goal'], 'check': view['snapshot']['consistency_check'],
            'summary': view['summary'], 'overall_goal_acceptance': view['overall_goal_acceptance'],
            'historical_integrity': view['snapshot']['historical_integrity'],
            'current_readiness': view['snapshot']['current_readiness'],
            'input_label': 'synthetic' if any(isinstance(doc, dict) and doc.get('synthetic') is True for doc in source.documents.values()) or view['snapshot']['label'] == 'synthetic' else 'claimed',
            'record_label': view['snapshot']['label'], 'generated_at': view['snapshot']['generated_at'],
            'captured_at': view['snapshot']['captured_at'], 'live_host_state': 'unknown', 'observed_overlap': 'unknown'}
