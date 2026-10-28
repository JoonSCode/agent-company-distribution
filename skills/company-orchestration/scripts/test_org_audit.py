#!/usr/bin/env python3
"""Synthetic behavior tests only; private receipt replay is kept outside this repo."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import org_audit as audit


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='company-org-audit-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.doc = {'version': 1, 'coverage': 'declared_complete', 'sources': [],
                    'events': [], 'expected_events': []}
        self.task = {'id': 'task-a', 'run_id': 'run-a', 'parent_id': 'technical-parent',
                     'created_by_terminal_handle': 'proxy', 'created_at': 't1'}
        self.worker = {'dispatchId': 'dispatch-a', 'taskId': 'task-a',
                       'runId': 'run-a', 'agentTerminalHandle': 'member'}
        self.source('tasks', 'orca_tasks', {'ok': True, 'result': {'tasks': [self.task]}})
        self.source('workers', 'orca_workers', {'ok': True, 'result': {'workers': [self.worker]}})
        self.source('claims', 'claims', {'claims': [{
            'id': 'acceptance', 'scope': 'scope-a', 'revision': 'r1',
            'accountable_owner': 'lead', 'team_id': 'design', 'decision_id': 'decision-a',
            'request_id': 'request-a', 'actor': 'lead', 'requested_by': 'lead',
        }]})
        self.event = {key: None for key in audit.REQUIRED}
        self.event.update(id='assignment-a', kind='assignment', run_id='run-a',
                          scope='scope-a', revision='r1', accountable_owner='lead',
                          team_id='design', decision_id='decision-a', request_id='request-a',
                          actor='lead', requested_by='lead', executed_by='member',
                          task_id='task-a', dispatch_id='dispatch-a', occurred_at='t1',
                          created_by='proxy', parent_task_id='technical-parent',
                          evidence=['tasks#/result/tasks/0', 'workers#/result/workers/0',
                                    'claims#/claims/0'])
        self.doc['events'] = [self.event]
        self.doc['expected_events'] = ['assignment-a']

    def source(self, sid, fmt, value):
        if fmt in {'orca_tasks', 'orca_workers'}:
            value['result'].setdefault('page', {'hasMore': False, 'nextCursor': None})
        path = self.base / (sid + '.json')
        path.write_text(json.dumps(value))
        source = {'id': sid, 'path': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                  'format': fmt, 'provenance': 'synthetic fixture, not observed live',
                  'host_id': 'fixture-host', 'captured_at': 'capture-time'}
        self.doc['sources'].append(source)
        return source

    def run_audit(self):
        return audit.audit(self.doc, self.base)

    def codes(self):
        return {i['code'] for i in self.run_audit()['issues']}

    def test_proxy_creator_executor_owner_are_distinct(self):
        result = self.run_audit()
        self.assertEqual(result['status'], 'consistent_with_evidence')  # Ownership remains a claim.
        self.assertEqual(self.codes(), {'claim_only'})
        checks = result['events'][0]['field_status']
        self.assertEqual(checks['created_by'], 'host_observed')
        self.assertEqual(checks['executed_by'], 'host_observed')
        self.assertEqual(checks['accountable_owner'], 'claimed')
        self.assertEqual(result['events'][0]['event']['requested_by'], 'lead')

    def test_out_of_order_events_and_sources_do_not_change_result(self):
        later = copy.deepcopy(self.event)
        later.update(id='later', depends_on=['assignment-a'])
        self.doc['events'].insert(0, later)
        forward = self.run_audit()
        self.doc['events'].reverse()
        self.doc['sources'].reverse()
        backward = self.run_audit()
        self.assertEqual(forward['status'], backward['status'])
        self.assertNotIn('missing_dependency', self.codes())
        self.assertNotIn('dependency_cycle', self.codes())

    def test_expected_event_and_evidence_absence_are_unknown_not_contradiction(self):
        self.doc['expected_events'].append('unrecorded-consultation')
        self.event['evidence'].append('absent#/result')
        result = self.run_audit()
        self.assertEqual(result['status'], 'incomplete')
        self.assertTrue({'missing_event', 'missing_evidence'} <= self.codes())
        self.assertFalse(any(i['severity'] == 'contradiction' for i in result['issues']))

    def test_null_missing_and_unsupported_fields_differ(self):
        self.event['decision_id'] = None
        del self.event['scope']
        self.event['from_team'] = 'unproven-team'
        self.assertTrue({'unknown_field', 'missing_field', 'unsupported_claim'} <= self.codes())

    def test_wrong_dispatch_executor_is_contradiction(self):
        self.event['executed_by'] = 'proxy'
        result = self.run_audit()
        self.assertEqual(result['status'], 'inconsistent')
        self.assertEqual(result['events'][0]['field_status']['executed_by'], 'contradiction')

    def test_parent_and_creator_cannot_prove_owner(self):
        self.event['accountable_owner'] = 'proxy'
        self.event['evidence'].remove('claims#/claims/0')
        result = self.run_audit()
        self.assertEqual(result['events'][0]['field_status']['accountable_owner'], 'unsupported')

    def test_duplicate_event_source_and_receipt_identities(self):
        self.doc['events'].append(copy.deepcopy(self.event))
        self.doc['sources'].append(copy.deepcopy(self.doc['sources'][0]))
        self.source('duplicate-tasks', 'orca_tasks', {'ok': True, 'result': {'tasks': [self.task, self.task]}})
        duplicates = [i for i in self.run_audit()['issues'] if i['code'] == 'duplicate_identity']
        self.assertEqual(len(duplicates), 3)

    def test_same_identity_repeated_in_snapshots_is_allowed_but_conflict_is_not(self):
        self.source('workers-again', 'orca_workers', {'ok': True, 'result': {'workers': [self.worker]}})
        self.assertNotIn('duplicate_identity', self.codes())
        bad = {**self.worker, 'taskId': 'other-task'}
        self.source('wrong-worker', 'orca_workers', {'ok': True, 'result': {'workers': [bad]}})
        self.assertIn('identity_contradiction', self.codes())

    def test_hash_changed_or_missing_file_cannot_supply_observed_facts(self):
        (self.base / 'tasks.json').write_text('{}')
        (self.base / 'workers.json').unlink()
        result = self.run_audit()
        self.assertEqual(result['status'], 'inconsistent')
        self.assertTrue({'hash_mismatch', 'unreadable_source', 'missing_evidence'} <= self.codes())
        self.assertFalse(any(r['basis'] == 'host_observed' for r in result['observations']))

    def test_transcript_extraction_is_not_raw_host_and_body_never_proves_decision(self):
        self.source('messages', 'message_extract', {'messages': [{'source': 'transcript', 'source_line': 42,
                    'message': {'id': 'message-a', 'run_id': 'run-a', 'from_handle': 'lead',
                                'to_handle': 'other-lead', 'created_at': 't1',
                                'body': 'decision-a accepted all owners and real meeting happened'}}]})
        self.event['evidence'] = ['messages#/messages/0/message']
        checks = self.run_audit()['events'][0]['field_status']
        self.assertEqual(checks['actor'], 'extracted_observation')
        self.assertEqual(checks['decision_id'], 'unsupported')
        self.assertEqual(checks['accountable_owner'], 'unsupported')
        self.assertNotIn('body', json.dumps(self.run_audit()['observations']))

    def test_launch_and_denial_normalize_request_and_dispatch(self):
        self.source('launch', 'orca_launch', {'ok': True, 'result': {
            'runId': 'run-a', 'taskId': 'task-a', 'dispatchId': 'dispatch-a',
            'mutation': {'requestId': 'request-launch'}, 'effects': [
                {'kind': 'terminal', 'role': 'agent', 'id': 'member'}]}})
        self.source('denial', 'orca_error', {'ok': False, 'error': {
            'code': 'consumer_fenced', 'data': {'orchestrationRequestId': 'denied-request'}}})
        rows = {r['ref']: r for r in self.run_audit()['observations']}
        self.assertEqual(rows['launch#/result']['facts']['executed_by'], 'member')
        self.assertEqual(rows['launch#/result']['facts']['request_id'], 'request-launch')
        self.assertEqual(rows['denial#/error']['facts']['error_code'], 'consumer_fenced')
        self.assertNotIn('accountable_owner', rows['launch#/result']['facts'])

    def test_cycles_and_missing_dependencies(self):
        self.event['depends_on'] = ['assignment-a', 'missing']
        self.assertTrue({'dependency_cycle', 'missing_dependency'} <= self.codes())

    def test_distinct_hosts_are_not_conflated_and_capture_time_is_not_occurrence(self):
        other = self.source('other-host', 'orca_workers', {'ok': True, 'result': {
            'workers': [{**self.worker, 'taskId': 'other-task'}]}})
        other['host_id'] = 'other-host'
        result = self.run_audit()
        self.assertNotIn('identity_contradiction', self.codes())
        observation = next(r for r in result['observations'] if r['source_id'] == 'workers')
        self.assertNotIn('occurred_at', observation['facts'])
        self.assertEqual(result['events'][0]['event']['occurred_at'], 't1')

    def test_pagination_truncation_and_absent_metadata_override_complete_claim(self):
        for page, extra, expected in [
            ({'hasMore': True, 'nextCursor': 'next'}, {}, 'incomplete_capture'),
            ({'hasMore': False, 'nextCursor': 'next'}, {}, 'incomplete_capture'),
            ({'hasMore': False, 'nextCursor': None, 'total': 2}, {}, 'incomplete_capture'),
            ({'hasMore': False, 'nextCursor': None}, {'truncated': True}, 'incomplete_capture'),
            (None, {}, 'capture_coverage_unknown'),
        ]:
            with self.subTest(page=page, extra=extra):
                raw = {'ok': True, 'result': {'workers': [self.worker], 'page': page, **extra}}
                source = self.source('paged', 'orca_workers', raw)
                self.assertIn(expected, self.codes())
                self.assertEqual(self.run_audit()['status'], 'incomplete')
                self.doc['sources'].remove(source)

    def test_malformed_envelope_does_not_silently_become_empty_evidence(self):
        self.source('bad', 'orca_workers', {'ok': True, 'result': {'workers': [{}]}})
        self.assertIn('unreadable_source', self.codes())

    def test_runtime_identity_uses_string_or_optional_host_fallback(self):
        for meta in [{}, {'runtimeId': None}, {'runtimeId': 'runtime-a'}]:
            for host in [None, 'host-a']:
                with self.subTest(meta=meta, host=host):
                    source = self.source('runtime', 'orca_workers', {
                        'ok': True, '_meta': meta, 'result': {'workers': [self.worker]}})
                    source['host_id'] = host
                    result = self.run_audit()
                    row = next(r for r in result['observations'] if r['source_id'] == 'runtime')
                    self.assertEqual(row['runtime_id'], meta.get('runtimeId'))
                    self.assertEqual(row['host_key'], meta.get('runtimeId') or host or 'unknown:runtime')
                    self.assertEqual(result['status'], 'consistent_with_evidence')
                    self.assertNotIn('accountable_owner', row['facts'])
                    self.assertNotIn('team_id', row['facts'])
                    self.doc['sources'].remove(source)

    def test_malformed_runtime_identity_produces_structured_source_error(self):
        for value in [['runtime-a'], [], {'id': 'runtime-a'}, {}, True, False, 1, 0, '', '  ']:
            with self.subTest(value=value):
                source = self.source('bad-runtime', 'orca_workers', {
                    'ok': True, '_meta': {'runtimeId': value},
                    'result': {'workers': [self.worker]}})
                path = self.base / 'manifest.json'
                path.write_text(json.dumps(self.doc))
                result = subprocess.run([sys.executable, str(Path(audit.__file__)), str(path)],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertEqual(result.stderr, '')
                report = json.loads(result.stdout)
                self.assertEqual(report['status'], 'inconsistent')
                self.assertTrue(any(i['code'] == 'unreadable_source' and i['severity'] == 'invalid'
                                    for i in report['issues']))
                self.assertFalse(any(r['source_id'] == 'bad-runtime' for r in report['observations']))
                self.doc['sources'].remove(source)

    def test_malformed_host_identity_remains_structured_manifest_error(self):
        source = self.doc['sources'][0]
        for value in [['host-a'], [], {'id': 'host-a'}, {}, True, False, 1, 0, '', '  ']:
            with self.subTest(value=value):
                source['host_id'] = value
                path = self.base / 'manifest.json'
                path.write_text(json.dumps(self.doc))
                result = subprocess.run([sys.executable, str(Path(audit.__file__)), str(path)],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(result.stderr, '')
                self.assertEqual(json.loads(result.stdout)['status'], 'invalid_input')

    def test_duplicate_json_keys_and_nan_rejected(self):
        for raw in ['{"a":1,"a":2}', '{"a":NaN}']:
            with self.assertRaises(ValueError):
                audit.strict_json(raw)

    def test_cli_separates_unknown_from_failure_and_does_not_mutate_inputs(self):
        path = self.base / 'manifest.json'
        path.write_text(json.dumps(self.doc))
        before = {p.name: p.read_bytes() for p in self.base.iterdir()}
        result = subprocess.run([sys.executable, str(Path(audit.__file__)), str(path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'], 'consistent_with_evidence')
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.base.iterdir()})
        self.event['scope'] = None
        path.write_text(json.dumps(self.doc))
        result = subprocess.run([sys.executable, str(Path(audit.__file__)), str(path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 3)
        self.assertEqual(json.loads(result.stdout)['status'], 'incomplete')
        self.event['executed_by'] = 'wrong'
        path.write_text(json.dumps(self.doc))
        result = subprocess.run([sys.executable, str(Path(audit.__file__)), str(path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        path.write_text('[]')
        result = subprocess.run([sys.executable, str(Path(audit.__file__)), str(path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)['status'], 'invalid_input')


class ImportTests(unittest.TestCase):
    setUp = AuditTests.setUp
    source = AuditTests.source

    def handoff(self):
        return {'schema': 'company-org-handoff', 'version': 1,
                'coverage': 'declared_complete', 'sources': copy.deepcopy(self.doc['sources']),
                'declarations': [copy.deepcopy(self.event)]}

    def imported(self, handoff=None):
        return audit.import_handoff(handoff or self.handoff(), self.base)

    def test_import_pins_unpinned_bytes_and_retains_claim_basis(self):
        handoff = self.handoff()
        for source in handoff['sources']:
            source.pop('sha256')
        result = self.imported(handoff)
        self.assertEqual(result['schema'], 'company-org-import')
        self.assertEqual(result['status'], 'consistent_with_evidence')
        self.assertEqual(result['declarations'][0]['field_status']['accountable_owner'], 'claimed')
        self.assertEqual(len(result['draft_events']), 2)  # Claims are not host events.
        self.assertNotIn('events', result)
        for source in result['sources']:
            self.assertEqual(source['sha256'], source['verified_sha256'])
        self.assertIsNone(result['draft_events'][0]['accountable_owner'])
        self.assertIsNone(result['draft_events'][0]['scope'])
        self.assertNotIn('sha256', handoff['sources'][0])

    def test_import_rejects_schema_version_and_extra_fields(self):
        for field, value in [('schema', 'other'), ('version', True), ('version', '1'),
                             ('version', 2), ('unexpected', 'value'),
                             ('sources', {}), ('declarations', {})]:
            with self.subTest(field=field, value=value):
                handoff = self.handoff()
                handoff[field] = value
                with self.assertRaises(audit.InputError):
                    self.imported(handoff)

    def test_import_rejects_malformed_source_and_declaration_types(self):
        for target, field, value in [('source', 'sha256', None), ('source', 'path', []),
                                     ('source', 'host_id', False), ('source', 'extra', 'x'),
                                     ('declaration', 'accountable_owner', {}),
                                     ('declaration', 'evidence', 'tasks#/result/tasks/0'),
                                     ('declaration', 'depends_on', [False]),
                                     ('declaration', 'authority', 'approved')]:
            with self.subTest(target=target, field=field):
                handoff = self.handoff()
                item = handoff['sources'][0] if target == 'source' else handoff['declarations'][0]
                item[field] = value
                with self.assertRaises(audit.InputError):
                    self.imported(handoff)

    def test_import_hash_failure_and_error_keep_failure_visible(self):
        handoff = self.handoff()
        handoff['sources'][0]['sha256'] = '0' * 64
        self.source('denied', 'orca_error', {'ok': False, 'error': {
            'code': 'runtime_access_denied', 'data': {'orchestrationRequestId': 'failed-request'}}})
        handoff['sources'].append(self.doc['sources'][-1])
        result = self.imported(handoff)
        self.assertEqual(result['status'], 'inconsistent')
        self.assertIn('hash_mismatch', {i['code'] for i in result['issues']})
        denied = next(d for d in result['draft_events'] if d['kind'] == 'orca_error')
        self.assertEqual(denied['error_code'], 'runtime_access_denied')
        self.assertEqual(denied['request_id'], 'failed-request')

    def test_import_message_shapes_have_exact_pointers_without_body_or_payload(self):
        message = {'id': 'msg-a', 'run_id': 'run-a', 'from_handle': 'proxy',
                   'to_handle': 'dispatch:other', 'created_at': 't2',
                   'body': 'owner accepted decision-a', 'payload': '{invalid JSON'}
        for fmt, result, pointer in [
            ('orca_messages', {'messages': [message], 'count': 1}, '/result/messages/0'),
            ('orca_message', {'message': message}, '/result/message'),
        ]:
            with self.subTest(fmt=fmt):
                source = self.source(fmt, fmt, {'ok': True, '_meta': {'runtimeId': 'runtime-a'}, 'result': result})
                report = self.imported()
                row = next(r for r in report['observations'] if r['source_id'] == fmt)
                self.assertEqual(row['ref'], fmt + '#' + pointer)
                self.assertEqual(row['facts']['actor'], 'proxy')
                self.assertEqual(row['host_id'], 'fixture-host')
                self.assertEqual(row['runtime_id'], 'runtime-a')
                self.assertEqual(row['captured_at'], 'capture-time')
                self.assertNotIn('body', json.dumps(row))
                self.assertNotIn('payload', json.dumps(row))
                self.assertNotIn('accountable_owner', row['facts'])
                self.assertEqual(row['facts']['occurred_at'], 't2')
                if fmt == 'orca_messages':
                    self.assertIn('capture_coverage_unknown', {i['code'] for i in report['issues']})
                self.doc['sources'].remove(source)

    def test_import_bad_or_failed_message_shape_cannot_supply_facts(self):
        for value in [{'ok': False, 'result': {'messages': []}},
                      {'ok': True, 'result': {'messages': [{}]}},
                      {'ok': True, 'result': {'messages': 'x'}},
                      {'ok': True, 'result': {'answer': {'id': 'msg-a'}}}]:
            source = self.source('bad-message', 'orca_messages', value)
            report = self.imported()
            self.assertEqual(report['status'], 'inconsistent')
            self.assertFalse(any(r['source_id'] == 'bad-message' for r in report['observations']))
            self.doc['sources'].remove(source)

    def test_import_scope_revision_and_creator_only_owner_negative_controls(self):
        for field in ('scope', 'revision'):
            handoff = self.handoff()
            handoff['declarations'][0][field] = 'wrong'
            result = self.imported(handoff)
            self.assertEqual(result['status'], 'inconsistent')
            self.assertEqual(result['declarations'][0]['field_status'][field], 'claim_contradiction')
        handoff = self.handoff()
        declaration = handoff['declarations'][0]
        declaration['accountable_owner'] = 'proxy'
        declaration['evidence'].remove('claims#/claims/0')
        result = self.imported(handoff)
        self.assertEqual(result['status'], 'incomplete')
        self.assertEqual(result['declarations'][0]['field_status']['accountable_owner'], 'unsupported')

    def test_import_source_pointer_is_exact_not_convenient_text_search(self):
        handoff = self.handoff()
        handoff['declarations'][0]['evidence'] = ['tasks#/result/tasks/1', 'claims#/claims/0']
        report = self.imported(handoff)
        self.assertIn('missing_evidence', {i['code'] for i in report['issues']})
        self.assertEqual(report['declarations'][0]['field_status']['created_by'], 'unsupported')

    def test_import_duplicates_and_partial_message_pages_remain_visible(self):
        handoff = self.handoff()
        handoff['sources'].append(copy.deepcopy(handoff['sources'][0]))
        handoff['declarations'].append(copy.deepcopy(handoff['declarations'][0]))
        self.assertIn('duplicate_identity', {i['code'] for i in self.imported(handoff)['issues']})
        source = self.source('paged-messages', 'orca_messages', {'ok': True, 'result': {
            'messages': [], 'count': 0, 'page': {'hasMore': True, 'nextCursor': 'next'}}})
        report = self.imported()
        self.assertIn('incomplete_capture', {i['code'] for i in report['issues']})
        self.assertEqual(report['status'], 'incomplete')
        self.doc['sources'].remove(source)

    def test_import_distinct_runtime_namespaces_do_not_merge_identity(self):
        for sid, host, task in [('host-a', 'a', 'task-a'), ('host-b', 'b', 'task-b')]:
            source = self.source(sid, 'orca_workers', {'ok': True,
                '_meta': {'runtimeId': 'runtime-' + host},
                'result': {'workers': [{**self.worker, 'taskId': task}]}})
            source['host_id'] = host
        self.assertNotIn('identity_contradiction', {i['code'] for i in self.imported()['issues']})

    def test_import_declared_host_cannot_hide_same_runtime_identity_conflict(self):
        for host in (None, 'host-a', 'host-b'):
            with self.subTest(host=host):
                source = self.source('same-runtime', 'orca_tasks', {'ok': True,
                    '_meta': {'runtimeId': 'runtime-a'}, 'result': {'tasks': [self.task]}})
                source['host_id'] = None
                other = self.source('other-declared-host', 'orca_tasks', {'ok': True,
                    '_meta': {'runtimeId': 'runtime-a'},
                    'result': {'tasks': [{**self.task, 'created_by_terminal_handle': 'other'}]}})
                other['host_id'] = host
                self.assertIn('identity_contradiction', {i['code'] for i in self.imported()['issues']})
                self.doc['sources'].remove(source)
                self.doc['sources'].remove(other)

    def test_import_cli_structured_errors_and_read_only_output(self):
        path = self.base / 'handoff.json'
        path.write_text(json.dumps(self.handoff()))
        before = {p.name: p.read_bytes() for p in self.base.iterdir()}
        command = [sys.executable, str(Path(audit.__file__)), 'import', str(path)]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['schema'], 'company-org-import')
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.base.iterdir()})
        path.write_text('{"schema":"company-org-handoff","schema":"wrong"}')
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr, '')
        self.assertEqual(json.loads(result.stdout)['status'], 'invalid_input')


if __name__ == '__main__':
    unittest.main()
