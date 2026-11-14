#!/usr/bin/env python3
"""Exercise the opt-in measurement boundary with synthetic provider sources."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

PACKAGE = Path(__file__).resolve().parents[1]
SCRIPTS = PACKAGE / 'scripts'
sys.path.insert(0, str(SCRIPTS))
from record_check import check_record


def counts():
    return {'input_tokens': 10, 'cached_input_tokens': 2, 'cache_write_input_tokens': 0,
            'output_tokens': 5, 'reasoning_output_tokens': 3, 'total_tokens': 15}


def trace(session, turn, response):
    c = counts()
    return [
        {'type': 'session_meta', 'payload': {'id': session}},
        {'type': 'event_msg', 'payload': {'type': 'task_started', 'turn_id': turn}},
        {'type': 'token_usage_record', 'payload': {'thread_id': session, 'session_id': session,
            'turn_id': turn, 'root_turn_id': turn, 'response_id': response,
            'usage': c, 'turn_token_usage': c, 'thread_token_usage': c}},
        {'type': 'event_msg', 'payload': {'type': 'token_count', 'info': {
            'total_token_usage': c, 'last_token_usage': c}}},
        {'type': 'event_msg', 'payload': {'type': 'task_complete', 'turn_id': turn}},
    ]


def encode(rows):
    return b''.join(json.dumps(row).encode() + b'\n' for row in rows)


class MeasurementGateTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.record = copy.deepcopy(json.loads((PACKAGE / 'assets/record-cases.json').read_text())['cases'][0]['record'])
        self.record['goal'].update(status='active', known_failure=False, assessment=None)
        goal = self.record['goal']
        plan = b'approved plan for the original goal'
        (self.base / 'plan').write_bytes(plan)
        self.record['evidence']['plan'].update(file='plan', sha256=hashlib.sha256(plan).hexdigest())
        for name in ('objective', 'criteria'):
            data = (name + ' frozen for goal-1').encode()
            (self.base / name).write_bytes(data)
            self.record['evidence'][name] = {'ref': 'fixture:' + name, 'kind': 'synthetic',
                                              'file': name, 'sha256': hashlib.sha256(data).hexdigest()}
        participants = []
        self.rows = {}
        for actor, session, turn, response in [('B', 'lead-session', 'lead-turn', 'lead-response'),
                ('worker', 'worker-session', 'worker-turn', 'worker-response'),
                ('reviewer', 'reviewer-session', 'reviewer-turn', 'reviewer-response'),
                ('independent-reviewer', 'independent-session', 'independent-turn', 'independent-response')]:
            rows = trace(session, turn, response)
            source = self.base / '2026/10/28' / (session + '.jsonl')
            source.parent.mkdir(parents=True, exist_ok=True)
            prefix = encode(rows[:-1])
            source.write_bytes(prefix)
            self.rows[actor] = (source, rows)
            participants.append({'actor': actor, 'provider': 'codex', 'session': session,
                'source': str(source), 'turns': [turn], 'prefix_bytes': len(prefix),
                'prefix_sha256': hashlib.sha256(prefix).hexdigest()})
        self.record['measurement'] = {'mode': 'required',
            'goal_binding': {field: goal[field] for field in ('id', 'revision', 'scope', 'plan')},
            'objective': 'objective', 'criteria': 'criteria',
            'boundary': {'start': 'lead request', 'end': 'integrated report',
                         'shared_costs': 'lead, worker, retries, verification and integration'},
            'expected_actors': ['B', 'worker', 'reviewer', 'independent-reviewer'],
            'participants': participants}

    def preflight(self, record=None):
        return check_record(self.record if record is None else record, self.base, measurement_preflight=True)

    def complete(self):
        for source, rows in self.rows.values():
            source.write_bytes(encode(rows[:-1]))
        preflight = self.preflight()
        self.assertTrue(preflight['ok'], preflight)
        data = json.dumps(preflight).encode()
        (self.base / 'preflight.json').write_bytes(data)
        record = copy.deepcopy(self.record)
        record['evidence']['preflight'] = {'ref': 'fixture:preflight', 'kind': 'synthetic',
            'file': 'preflight.json', 'sha256': hashlib.sha256(data).hexdigest()}
        record['measurement']['preflight'] = 'preflight'
        record['goal'].update(status='succeeded', assessment={'revision': 'r1', 'scope': 'approved-scope',
            'verdict': 'succeeded', 'basis': 'independent', 'actor': 'independent-reviewer', 'evidence': 'assessment'})
        entries = []
        for participant in record['measurement']['participants']:
            source, rows = self.rows[participant['actor']]
            final = encode(rows)
            source.write_bytes(final)
            participant.update(final_bytes=len(final), final_sha256=hashlib.sha256(final).hexdigest())
            entries.append({'provider': 'codex', 'tokenizer': 'unknown', 'kind': 'request',
                'id': rows[2]['payload']['response_id'], 'session': participant['session'],
                'input': 10, 'output': 5, 'cached_input': 2, 'reasoning': 3,
                'cached_in_input': True, 'reasoning_in_output': True, 'evidence': 'usage'})
        record['usage'] = {'coverage': 'complete',
            'expected': ['codex/request/' + entry['id'] for entry in entries], 'entries': entries}
        return record

    def codes(self, record):
        return {error['code'] for error in self.preflight(record)['errors']}

    def test_preflight_real_cli_and_older_session_path(self):
        path = self.base / 'record.json'
        path.write_text(json.dumps(self.record))
        proc = subprocess.run([sys.executable, str(SCRIPTS / 'record_check.py'), 'check', str(path),
                               '--measurement-preflight', '--json'], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue(json.loads(proc.stdout)['ok'])
        self.assertEqual(check_record(self.complete(), self.base)['usage']['total_raw_tokens'], 60)

    def test_missing_lead_or_unobserved_participant_fails(self):
        record = copy.deepcopy(self.record)
        record['measurement']['participants'].pop(0)
        self.assertIn('measurement_participants', self.codes(record))
        record = copy.deepcopy(self.record)
        record['measurement']['participants'][1]['turns'] = ['future-turn']
        self.assertIn('measurement_source', self.codes(record))
        record = copy.deepcopy(self.record)
        record['measurement']['participants'].pop(2)
        record['measurement']['expected_actors'].remove('reviewer')
        self.assertIn('measurement_participants', self.codes(record))

    def test_source_missing_wrong_session_or_bad_prefix_fails(self):
        for field, value in [('source', '/nonexistent/source'), ('session', 'other'),
                             ('prefix_bytes', None), ('prefix_sha256', '0' * 64)]:
            with self.subTest(field=field):
                record = copy.deepcopy(self.record)
                record['measurement']['participants'][0][field] = value
                self.assertIn('measurement_source', self.codes(record))

    def test_completed_source_cannot_be_backdated_with_a_precompletion_prefix(self):
        source, rows = self.rows['B']
        source.write_bytes(encode(rows))
        self.assertIn('measurement_not_live', self.codes(self.record))

    def test_no_usage_and_partial_values_fail(self):
        for rows in ([self.rows['B'][1][0], self.rows['B'][1][1]], copy.deepcopy(self.rows['B'][1][:-1])):
            if len(rows) > 2:
                rows[2]['payload']['usage']['input_tokens'] = None
            source, _ = self.rows['B']
            data = encode(rows)
            source.write_bytes(data)
            record = copy.deepcopy(self.record)
            record['measurement']['participants'][0].update(prefix_bytes=len(data), prefix_sha256=hashlib.sha256(data).hexdigest())
            self.assertIn('measurement_source', self.codes(record))

    def test_duplicates_and_goal_binding_are_rejected(self):
        record = copy.deepcopy(self.record)
        record['measurement']['participants'].append(copy.deepcopy(record['measurement']['participants'][0]))
        self.assertIn('measurement_overlap', self.codes(record))
        record = copy.deepcopy(self.record)
        record['measurement']['goal_binding']['scope'] = 'narrowed-secondary-qa'
        self.assertIn('measurement_goal', self.codes(record))
        record = copy.deepcopy(self.record)
        record['measurement']['criteria'] = 'usage'
        self.assertIn('measurement_freeze', self.codes(record))

    def test_append_allowed_but_prefix_change_or_truncation_fails(self):
        self.assertTrue(self.preflight()['ok'])
        source, rows = self.rows['B']
        with source.open('ab') as stream:
            stream.write(encode([{'type': 'event_msg', 'payload': {'type': 'unrelated'}}]))
        self.assertTrue(self.preflight()['ok'])
        data = source.read_bytes()
        source.write_bytes(data[:self.record['measurement']['participants'][0]['prefix_bytes'] - 1])
        self.assertIn('measurement_source', self.codes(self.record))
        source.write_bytes(encode(rows).replace(b'lead-session', b'evil-session', 1))
        self.assertIn('measurement_source', self.codes(self.record))

    def test_success_requires_full_and_matched_usage(self):
        for change in ('partial', 'null', 'omitted', 'mismatch', 'duplicate', 'unfinished', 'no_preflight', 'changed_boundary'):
            with self.subTest(change=change):
                record = self.complete()
                if change == 'partial': record['usage']['coverage'] = 'partial'
                if change == 'null': record['usage']['entries'][0]['input'] = None
                if change == 'omitted': record['usage']['entries'].pop()
                if change == 'mismatch': record['usage']['entries'][0]['input'] = 9
                if change == 'duplicate': record['usage']['entries'].append(copy.deepcopy(record['usage']['entries'][0]))
                if change == 'unfinished':
                    source, rows = self.rows['B']
                    data = encode(rows[:-1])
                    record['measurement']['participants'][0].update(final_bytes=len(data), final_sha256=hashlib.sha256(data).hexdigest())
                if change == 'no_preflight': del record['measurement']['preflight']
                if change == 'changed_boundary': record['measurement']['boundary']['shared_costs'] = 'worker only'
                result = check_record(record, self.base)
                self.assertFalse(result['ok'])
                self.assertIsNone(result['usage']['total_raw_tokens'])

    def test_failed_and_ordinary_records_remain_readable(self):
        record = copy.deepcopy(self.record)
        record['goal'].update(status='failed', known_failure=True)
        record['measurement']['participants'] = []
        self.assertTrue(check_record(record, self.base)['ok'])
        record.pop('measurement')
        self.assertTrue(check_record(record, self.base)['ok'])
        self.assertIn('measurement_required', self.codes(record))


if __name__ == '__main__':
    unittest.main()
