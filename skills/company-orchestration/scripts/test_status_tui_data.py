#!/usr/bin/env python3
"""Portable source/staged read-model contract tests; all staffing is synthetic."""
from __future__ import annotations
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import status_tui_data as data

ASSETS = Path(__file__).resolve().parent.parent / 'assets'


def dump(path, value):
    raw = (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()
    Path(path).write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def fixture(root, count=3):
    """Use the existing checker corpus, not a parallel invented checker schema."""
    root = Path(root)
    record = copy.deepcopy(json.loads((ASSETS / 'record-cases.json').read_text())['cases'][0]['record'])
    record['goal'].update(status='active', known_failure=False, assessment=None)
    template = record['tasks'][0]
    record['tasks'] = []
    for i in range(count):
        task = copy.deepcopy(template)
        task.update(id=f't{i+1}', current_dispatch=f'd{i+1}')
        for key in ('technical', 'parent_integration'):
            task[key].update(task=task['id'], dispatch=task['current_dispatch'])
        task['execution']['result'].update(task=task['id'], dispatch=task['current_dispatch'])
        task['model'].update(requested='fixture-model', observed=None)
        record['tasks'].append(task)
    claims = {'synthetic': True, 'scope': 'approved-scope', 'revision': 'r1', 'head': 'B',
              'teams': [{'id': 'build', 'label': '구현', 'lead': 'B', 'members': ['worker']},
                        {'id': 'review', 'label': '검증', 'lead': 'qa-lead', 'members': ['reviewer']}]}
    refs = lambda pointer, source='claims': [{'source': source, 'pointer': pointer}]
    org = {'head': {'actor': 'B', 'evidence': refs('/head')}, 'teams': []}
    for i, team in enumerate(claims['teams']):
        org['teams'].append({'id': team['id'], 'label': team['label'],
                            'lead': {'actor': team['lead'], 'evidence': refs(f'/teams/{i}/lead')},
                            'members': [{'actor': team['members'][0], 'evidence': refs(f'/teams/{i}/members/0')}],
                            'evidence': refs(f'/teams/{i}')})
    tasks = [{'id': t['id'], 'title': f'작업 {i+1}', 'classification': 'code',
              'team_id': 'build' if i != 1 else 'review', 'actor': 'worker' if i != 1 else 'reviewer',
              'assigned_model': 'fixture-model', 'specialist': {'status': 'unknown', 'id': None, 'evidence': []},
              'evidence': refs(f'/tasks/{i}', 'record')} for i, t in enumerate(record['tasks'])]
    dependencies = [{'task': t['id'], 'needs': [record['tasks'][i-1]['id']],
                     'evidence': refs(f'/dependencies/{i-1}', 'plan')} for i, t in enumerate(record['tasks']) if i]
    plan = {'synthetic': True, 'scope': 'approved-scope', 'revision': 'r1',
            'dependencies': [{k: v for k, v in dep.items() if k != 'evidence'} for dep in dependencies]}
    sources = []
    for sid, obj in [('record', record), ('claims', claims), ('plan', plan)]:
        digest = dump(root / (sid + '.json'), obj)
        sources.append({'id': sid, 'path': sid + '.json', 'sha256': digest, 'kind': sid})
    manifest = {'schema': 'company-status-tui-input/v1', 'version': 1,
                'binding': {'goal_id': record['goal']['id'], 'scope': 'approved-scope', 'revision': 'r1',
                            'record_sha256': sources[0]['sha256']}, 'sources': sources,
                'record': 'record', 'organization': org, 'tasks': tasks, 'dependencies': dependencies}
    dump(root / 'view.json', manifest)
    return manifest, record, claims, plan


class DataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.manifest, self.record, self.claims, self.plan = fixture(self.root)

    def load(self):
        dump(self.root / 'view.json', self.manifest)
        return data.load_snapshot(self.root / 'view.json')

    def repin(self, sid, obj):
        digest = dump(self.root / (sid + '.json'), obj)
        next(s for s in self.manifest['sources'] if s['id'] == sid)['sha256'] = digest
        if sid == 'record': self.manifest['binding']['record_sha256'] = digest

    def reject(self):
        with self.assertRaises(data.InputError): self.load()

    def test_p01_org_and_task_parent_are_different_relations(self):
        snap = self.load()
        self.assertEqual([t['id'] for t in snap['organization']['teams']], ['build', 'review'])
        self.assertEqual(snap['tasks'][0]['team_id'], 'build')
        self.assertNotIn('parent', snap['tasks'][0])
        self.assertEqual(snap['dependencies'][0]['needs'], ['t1'])
        self.assertEqual(snap['organization']['basis'], 'claimed')
        self.assertEqual(snap['live_host_state'], 'unknown')

    def test_p02_no_org_no_fake_registry_teams(self):
        self.manifest['organization'] = None
        for task in self.manifest['tasks']: task['team_id'] = None
        snap = self.load()
        self.assertIsNone(snap['organization'])
        self.assertTrue(all(t['team_id'] is None for t in snap['tasks']))

    def test_p03_bad_revision_hash_and_unknown_fields(self):
        for mutate in (lambda: self.manifest['binding'].update(revision='r2'),
                       lambda: self.manifest['sources'][0].update(sha256='0'*64),
                       lambda: self.manifest.update(unexpected=True),
                       lambda: self.manifest['tasks'][0].update(parent='B')):
            original = copy.deepcopy(self.manifest)
            mutate(); self.reject(); self.manifest = original

    def test_p03_duplicate_orphan_and_ambiguous_ids(self):
        for mutate in (lambda: self.manifest['tasks'].append(copy.deepcopy(self.manifest['tasks'][0])),
                       lambda: self.manifest['tasks'][0].update(id='absent'),
                       lambda: self.manifest['tasks'][0].update(team_id='absent'),
                       lambda: self.manifest['organization']['teams'].append(copy.deepcopy(self.manifest['organization']['teams'][0])),
                       lambda: self.manifest['sources'].append(copy.deepcopy(self.manifest['sources'][0]))):
            original = copy.deepcopy(self.manifest)
            mutate(); self.reject(); self.manifest = original

    def test_p03_task_revision_and_duplicate_record_id(self):
        self.record['tasks'][0]['goal_revision'] = 'old'
        self.repin('record', self.record); self.reject()
        self.record['tasks'][0]['goal_revision'] = 'r1'
        self.record['tasks'].append(copy.deepcopy(self.record['tasks'][0]))
        self.repin('record', self.record); self.reject()

    def test_p03_cycles_self_orphan_duplicate_edges(self):
        for needs in (['t2'], ['t1'], ['missing'], ['t2', 't2']):
            original = copy.deepcopy(self.manifest)
            self.manifest['dependencies'].append({'task': 't1', 'needs': list(needs),
                                                 'evidence': [{'source': 'plan', 'pointer': '/dependencies/2'}]})
            self.plan['dependencies'].append({'task': 't1', 'needs': list(needs)})
            self.repin('plan', self.plan); self.reject()
            self.plan['dependencies'].pop(); self.manifest = original; self.repin('plan', self.plan)

    def test_p03_evidence_must_exist_and_bind_semantics(self):
        self.manifest['organization']['head']['evidence'][0]['pointer'] = '/teams/0/label'
        self.reject()
        self.manifest['organization']['head']['evidence'][0]['pointer'] = '/missing'
        self.reject()

    def test_p03_claim_revision_binding(self):
        self.claims['revision'] = 'old'
        self.repin('claims', self.claims); self.reject()

    def test_p03_plan_mismatch(self):
        self.manifest['dependencies'][0]['needs'] = []
        self.reject()

    def test_p03_strict_json_duplicate_nan_wrong_type(self):
        for raw in ('{"schema":1,"schema":2}', '{"x":NaN}', '[]'):
            (self.root / 'view.json').write_text(raw)
            with self.assertRaises(data.InputError): data.load_snapshot(self.root / 'view.json')
        self.manifest['version'] = True; self.reject()

    def test_p03_symlinks_nonregular_and_drift(self):
        (self.root / 'link.json').symlink_to(self.root / 'record.json')
        self.manifest['sources'][0]['path'] = 'link.json'; self.reject()
        self.manifest['sources'][0]['path'] = '.'; self.reject()
        self.manifest['sources'][0]['path'] = 'record.json'
        (self.root / 'record.json').write_text('{}'); self.reject()

    def test_p03_changed_during_checker_rejected(self):
        original = data.status_view.build_view
        def change(*args, **kwargs):
            result = original(*args, **kwargs)
            (self.root / 'claims.json').write_text('{}')
            return result
        with patch.object(data.status_view, 'build_view', side_effect=change): self.reject()

    def test_p04_assigned_requires_registry_and_exact_assignment(self):
        native_id = 'agent-company-development'
        registry = {'id': 'development', 'native_agent': {'name': native_id}}
        sha = dump(self.root / 'registry.json', registry)
        self.manifest['sources'].append({'id': 'reg', 'path': 'registry.json', 'sha256': sha, 'kind': 'registry'})
        assignment = {'scope': 'approved-scope', 'revision': 'r1', 'task': 't1',
                      'dispatch': 'd1', 'actor': 'worker', 'specialist': native_id}
        sha = dump(self.root / 'assignment.json', assignment)
        self.manifest['sources'].append({'id': 'assignment', 'path': 'assignment.json', 'sha256': sha, 'kind': 'assignment'})
        self.manifest['tasks'][0]['specialist'] = {'status': 'assigned', 'id': native_id,
                                                  'evidence': [{'source': 'assignment', 'pointer': ''}]}
        self.assertEqual(self.load()['tasks'][0]['specialist']['id'], native_id)
        self.manifest['tasks'][0]['specialist']['id'] = 'role-code'; self.reject()
        self.manifest['tasks'][0]['specialist'] = {'status': 'none', 'id': None,
                                                  'evidence': [{'source': 'assignment', 'pointer': ''}]}
        self.reject()  # assignment still says assigned

    def test_p04_unknown_vs_explicit_none(self):
        self.assertEqual(self.load()['tasks'][0]['specialist']['status'], 'unknown')
        self.claims['assignment'] = {'task': 't1', 'dispatch': 'd1', 'actor': 'worker', 'specialist': None}
        self.repin('claims', self.claims)
        self.manifest['tasks'][0]['specialist'] = {'status': 'none', 'id': None,
                                                  'evidence': [{'source': 'claims', 'pointer': '/assignment'}]}
        self.assertEqual(self.load()['tasks'][0]['specialist']['status'], 'none')

    def test_p04_model_conflict_and_plan_only(self):
        self.manifest['tasks'][0]['assigned_model'] = 'invention'; self.reject()
        self.record['tasks'][0]['model']['requested'] = None
        self.repin('record', self.record)
        self.claims['assignment'] = {'task': 't1', 'assigned_model': 'invention'}
        self.repin('claims', self.claims)
        self.manifest['tasks'][0]['evidence'].append({'source': 'claims', 'pointer': '/assignment'})
        self.assertEqual(self.load()['tasks'][0]['model_basis'], 'planned')

    def test_p05_sub_not_acc_without_both_reviews(self):
        self.assertEqual(self.load()['tasks'][0]['state'], 'ACC')
        self.record['tasks'][0]['parent_integration'] = None
        self.repin('record', self.record)
        snap = self.load()
        self.assertEqual(snap['tasks'][0]['state'], 'SUB')
        self.assertFalse(snap['overall_goal_acceptance']['earned_success'])
        self.assertFalse(snap['tasks'][0]['stages']['parent_integration']['earned_success'])

    def test_p05_stale_review_checker_errors_preserved(self):
        self.record['tasks'][0]['technical']['candidate'] = 'old'
        self.repin('record', self.record)
        snap = self.load()
        self.assertNotEqual(snap['tasks'][0]['state'], 'ACC')
        self.assertFalse(snap['check']['ok'])
        self.assertTrue(snap['check']['errors'])

    def test_p06_recorded_live_not_run_and_overlap_unknown(self):
        self.record['tasks'][0]['execution'].update(state='live', result=None)
        self.record['tasks'][0].update(technical=None, parent_integration=None)
        self.repin('record', self.record)
        snap = self.load()
        self.assertEqual(snap['tasks'][0]['state'], '?')
        self.assertEqual(snap['observed_overlap'], 'unknown')
        self.assertEqual(snap['live_host_state'], 'unknown')
        self.assertIn('실행 관측 없음', snap['tasks'][0]['state_note'])

    def test_p06_missing_attachment_includes_unassigned_record_task(self):
        self.manifest['tasks'].pop()
        snap = self.load()
        self.assertEqual(len(snap['tasks']), 3)
        self.assertIsNone(snap['tasks'][-1]['team_id'])

    def test_org_audit_reuse_preserves_unknowns(self):
        audit = {'version': 1, 'coverage': 'partial', 'sources': [], 'events': [], 'expected_events': []}
        sha = dump(self.root / 'audit.json', audit)
        self.manifest['sources'].append({'id': 'audit', 'path': 'audit.json', 'sha256': sha, 'kind': 'org_manifest'})
        snap = self.load()
        self.assertEqual(snap['org_audits'][0]['report']['status'], 'incomplete')
        self.assertIn('partial_coverage', [i['code'] for i in snap['org_audits'][0]['report']['issues']])

    def test_org_handoff_reuse(self):
        audit = {'schema': 'company-org-handoff', 'version': 1, 'coverage': 'partial', 'sources': [], 'declarations': []}
        sha = dump(self.root / 'audit.json', audit)
        self.manifest['sources'].append({'id': 'audit', 'path': 'audit.json', 'sha256': sha, 'kind': 'org_handoff'})
        self.assertEqual(self.load()['org_audits'][0]['report']['schema'], 'company-org-import')

    def test_org_audit_field_status_and_event_edges_not_task_edges(self):
        import org_audit
        fact = {'id': 'claim', 'actor': 'B', 'scope': 'approved-scope', 'revision': 'r1', 'team_id': 'build'}
        pin = dump(self.root / 'audit-facts.json', {'claims': [fact]})
        event = dict.fromkeys(org_audit.REQUIRED)
        event.update(id='lead-acceptance',kind='acceptance',actor='B',scope='approved-scope',revision='r1',
                     team_id='build',evidence=['facts#/claims/0'],depends_on=[])
        audit = {'version':1,'coverage':'partial','sources':[{'id':'facts','path':'audit-facts.json',
                 'sha256':pin,'format':'claims','provenance':'synthetic claim'}],
                 'events':[event], 'expected_events':[]}
        sha = dump(self.root / 'audit.json',audit)
        self.manifest['sources'].append({'id':'audit','path':'audit.json','sha256':sha,'kind':'org_manifest'})
        snap = self.load()
        field_status = snap['org_audits'][0]['report']['events'][0]['field_status']
        self.assertEqual(field_status['actor'],'claimed')
        self.assertEqual(field_status['task_id'],'unknown')
        self.assertEqual(len(snap['dependencies']),2)
        self.assertTrue(any(p['path'].endswith('audit-facts.json') for p in snap['input_pins']))

    def test_relation_scalar_exact_head_lead_member_and_cross_team(self):
        snap = self.load()
        self.assertEqual(snap['organization']['head']['actor'], 'B')
        self.assertEqual(snap['organization']['teams'][0]['lead']['actor'], 'B')
        self.assertEqual(snap['organization']['teams'][0]['members'][0]['actor'], 'worker')
        for actor, pointer in [('reviewer', '/teams/1/members/0'), ('B', '/teams/0/lead'),
                               ('B', '/head'), ('qa-lead', '/teams/1/lead')]:
            with self.subTest(pointer=pointer):
                self.manifest['organization']['teams'][0]['members'] = [
                    {'actor': actor, 'evidence': [{'source': 'claims', 'pointer': pointer}]}]
                self.reject()

    def test_relation_head_and_lead_cannot_borrow_member_or_other_team(self):
        for target, actor, pointer in [
                ('head', 'worker', '/teams/0/members/0'),
                ('head', 'B', '/teams/0/lead'),
                ('lead', 'B', '/head'),
                ('lead', 'qa-lead', '/teams/1/lead'),
                ('lead', 'worker', '/teams/0/members/0')]:
            original = copy.deepcopy(self.manifest)
            value = {'actor': actor, 'evidence': [{'source': 'claims', 'pointer': pointer}]}
            if target == 'head': self.manifest['organization']['head'] = value
            else: self.manifest['organization']['teams'][0]['lead'] = value
            with self.subTest(target=target, pointer=pointer): self.reject()
            self.manifest = original

    def test_relation_structured_explicit_and_parent_context(self):
        member = self.manifest['organization']['teams'][0]['members'][0]
        member['evidence'] = [{'source': 'claims', 'pointer': '/fact'}]
        for relation in ('member', 'lead', 'head'):
            self.claims['fact'] = {'actor': 'worker', 'relation': relation, 'team_id': 'build'}
            self.repin('claims', self.claims)
            if relation == 'member':
                self.assertEqual(self.load()['organization']['teams'][0]['members'][0]['basis'], 'claimed')
            else: self.reject()
        self.claims['fact'] = {'actor': 'worker', 'role': 'member', 'team_id': 'review'}
        self.repin('claims', self.claims); self.reject()
        self.claims['teams'][0]['members'][0] = {'actor': 'worker'}
        member['evidence'][0]['pointer'] = '/teams/0/members/0'
        self.repin('claims', self.claims)
        self.assertEqual(self.load()['organization']['teams'][0]['members'][0]['basis'], 'claimed')
        member['evidence'][0]['pointer'] += '/actor'
        self.assertEqual(self.load()['organization']['teams'][0]['members'][0]['basis'], 'claimed')
        self.claims['teams'][0]['members'][0]['team_id'] = 'review'
        self.repin('claims', self.claims); self.reject()

    def test_relation_missing_role_or_team_is_unknown_not_defaulted(self):
        member = self.manifest['organization']['teams'][0]['members'][0]
        member['evidence'] = [{'source': 'claims', 'pointer': '/fact'}]
        for fact in ('worker', {'actor': 'worker'}, {'actor': 'worker', 'team_id': 'build'},
                     {'actor': 'worker', 'relation': 'member'}):
            self.claims['fact'] = fact; self.repin('claims', self.claims)
            value = self.load()['organization']['teams'][0]['members'][0]
            self.assertIsNone(value['actor']); self.assertEqual(value['basis'], 'unknown')
            self.assertEqual(value['acceptance'], 'unknown')

    def test_relation_structured_head_lead_and_conflicting_evidence(self):
        for target, fact in [('head', {'actor': 'B', 'relation': 'head'}),
                             ('lead', {'actor': 'B', 'role': 'lead', 'team_id': 'build'})]:
            self.claims['fact'] = fact; self.repin('claims', self.claims)
            value = self.manifest['organization']['head'] if target == 'head' else self.manifest['organization']['teams'][0]['lead']
            original = copy.deepcopy(value['evidence'])
            value['evidence'] = [{'source': 'claims', 'pointer': '/fact'}]
            snap = self.load()['organization']
            projected = snap['head'] if target == 'head' else snap['teams'][0]['lead']
            self.assertEqual(projected['actor'], 'B')
            value['evidence'] = original
        self.claims['teams'][0]['lead'] = {'actor': 'B', 'relation': 'member', 'team_id': 'build'}
        self.repin('claims', self.claims)
        self.manifest['organization']['teams'][0]['lead']['evidence'].append({'source': 'claims', 'pointer': '/teams/0/lead'})
        self.reject()

    def test_dependency_coverage_and_read_only(self):
        self.manifest['dependencies'] = []
        dump(self.root / 'view.json', self.manifest)
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.iterdir() if p.is_file()}
        snap = data.load_snapshot(self.root / 'view.json')
        after = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.iterdir() if p.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(snap['dependency_coverage'], 'unknown')
        self.assertIsNone(snap['captured_at'])


if __name__ == '__main__': unittest.main()
