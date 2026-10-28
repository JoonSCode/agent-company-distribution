#!/usr/bin/env python3
"""Offline selector behavior and its existing routing-check connection; no model calls."""
import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import record_check
from route_select import STAGES, SelectionError, estimated_cost, load_table, select

PACKAGE = Path(__file__).resolve().parents[1]
CLI = PACKAGE / 'scripts/record_check.py'


def candidate(family='terra', effort='low'):
    model = {'terra': 'gpt-6.1-terra', 'sol': 'gpt-6.1-sol',
             'astra': 'gpt-6-astra', 'luna': 'gpt-6-luna'}[family]
    return dict(route='codex', family=family, model=model, effort=effort,
                supported=True, authenticated=True, tools='supported', billing='subscription',
                runtime_evidence='runtime', quality='adequate', quality_evidence='quality',
                usage_estimate=None)


def unlisted_candidate(refs, route='antigravity', family='flash', model='gemini-3.8-flash-high', effort='high'):
    row = dict(route=route, family=family, model=model, effort=effort,
               supported=True, authenticated=True, tools='supported', billing='subscription',
               runtime_evidence='unlisted-runtime', quality='adequate', quality_evidence='unlisted-quality',
               usage_estimate=None)
    identity = {key: row[key] for key in ('route', 'family', 'model', 'effort')}
    start, end = datetime.now(timezone.utc) - timedelta(hours=1), datetime.now(timezone.utc) + timedelta(hours=1)
    for key in ('unlisted-models', 'unlisted-support', 'unlisted-auth', 'unlisted-tools', 'unlisted-billing'):
        refs[key] = {'ref': 'synthetic://' + key, 'sha256': None, 'kind': 'synthetic'}
    refs['unlisted-runtime'] = {'ref': 'synthetic://runtime', 'sha256': None, 'kind': 'synthetic',
        'unlisted_runtime': {'candidate': identity, 'agent': {'agy': 'antigravity', 'claude': 'claude-code'}.get(route, route), 'host': 'fixture-host', 'supported': True, 'authenticated': True,
            'tools': 'supported', 'billing': 'subscription', 'model_evidence': 'unlisted-models', 'support_evidence': 'unlisted-support',
            'auth_evidence': 'unlisted-auth', 'tools_evidence': 'unlisted-tools',
            'billing_evidence': 'unlisted-billing', 'observed_at': start.isoformat(), 'valid_until': end.isoformat()}}
    refs['unlisted-quality'] = {'ref': 'synthetic://fit', 'sha256': None, 'kind': 'synthetic',
        'task_fit': {'task_evidence': 'semantics', 'candidate': identity,
                     'support': 'quality', 'rationale': 'A bounded task and a checked output fit this setting.'}}
    return row


def request():
    return {'version': 1, 'task': {'actor': 'worker', 'capability': 'coding',
            'complexity': 'bounded', 'coupling': 'local', 'decomposable': False,
            'stage': 'execution', 'uncertainty': 'none', 'evidence': 'semantics'},
            'cost_basis': 'benchmark_prior', 'scope_api_authorized': False,
            'candidates': [candidate(), candidate('sol')]}


def estimate(model, tokens=1000):
    stages = {stage: [] for stage in STAGES}
    stages['execution'] = [{'id': 'execution-1', 'model': model, 'uncached_input': tokens,
        'cached_input': 0, 'cache_write_30m': 0, 'output': 0, 'tools_usd': 0,
        'tier': 'standard', 'region': 'global'}]
    return {'basis': 'estimate', 'evidence': 'estimate', 'stages': stages}


class SelectionFixture:
    def setUp(self):
        self.selection = request()
        self.refs = {key: {'ref': 'synthetic://' + key, 'sha256': None, 'kind': 'synthetic'}
                     for key in ('runtime', 'quality', 'semantics', 'estimate')}
        self.config = {'state': 'configured', 'values': {'services': ['codex', 'cursor'],
                       'excluded_models': [], 'service_order': [], 'api_paid': False}}

    def select(self):
        return select(self.selection, self.refs, self.config, synthetic=True)


class SelectionTests(SelectionFixture, unittest.TestCase):
    def test_benchmark_prior_without_local_ab_does_not_claim_actual_usage(self):
        with patch('socket.create_connection', side_effect=AssertionError('network forbidden')), \
             patch('subprocess.run', side_effect=AssertionError('execution forbidden')):
            result = self.select()
        self.assertEqual(result['selected']['family'], 'terra')
        self.assertEqual(result['comparison_basis'], 'benchmark_prior')
        for field in ('actual_usage', 'actual_subscription_charge_or_credits', 'effective_model', 'effective_effort'):
            self.assertIsNone(result[field])
        self.assertEqual(result['fallback'], 'unknown_until_host_readback')
        self.assertIsNone(result['compared'][0]['cost']['total_api_price_proxy_usd'])
        self.assertEqual(result['candidate_table_sha256'], load_table()[1])

    def test_same_task_not_title_and_no_forced_tiers(self):
        for actor in ('company_head', 'team_lead', 'worker'):
            self.selection['task']['actor'] = actor
            self.selection['candidates'] = [candidate()]
            self.assertEqual(self.select()['selected']['family'], 'terra')
        self.selection['task'].update(stage='consultation', uncertainty='none')
        with self.assertRaisesRegex(SelectionError, 'genuine'):
            self.select()

    def test_coupled_complex_executor_and_genuine_consultation(self):
        self.selection['task'].update(complexity='complex', coupling='coupled')
        self.assertEqual(self.select()['selected']['family'], 'sol')
        self.selection['task'].update(complexity='bounded', coupling='local',
                                      stage='consultation', uncertainty='conflict')
        self.assertEqual(self.select()['selected']['family'], 'sol')

    def task_fit_override(self):
        row = self.selection['candidates'][0]
        self.refs['support'] = {'ref': 'synthetic://task-specific-result', 'sha256': None, 'kind': 'synthetic'}
        fit = {'task_evidence': self.selection['task']['evidence'],
               'candidate': {key: row[key] for key in ('route', 'family', 'model', 'effort')},
               'support': 'support',
               'rationale': 'The supplied task-specific result covers this coupled change and acceptance checks.'}
        self.refs['quality']['task_fit'] = fit
        return fit

    def test_exact_task_evidence_can_supersede_family_prior(self):
        self.selection['task'].update(complexity='complex', coupling='coupled')
        self.selection['candidates'] = [candidate('terra', 'max'), candidate('sol', 'max')]
        self.assertEqual(self.select()['selected']['family'], 'sol')  # bare adequate is insufficient
        self.task_fit_override()
        result = self.select()
        self.assertEqual(result['selected']['family'], 'terra')
        self.assertEqual(result['compared'][0]['comparison_value'], 1.01)
        self.assertTrue(result['compared'][0]['task_fit_overrides_general_prior'])
        self.selection['task'].update(stage='consultation', uncertainty='ambiguity')
        self.assertEqual(self.select()['selected']['family'], 'terra')
        self.selection['candidates'][0]['quality'] = 'unknown'
        self.assertEqual(self.select()['selected']['family'], 'sol')

    def test_empty_stale_or_self_supporting_override_cannot_bypass_prior(self):
        self.selection['task'].update(complexity='complex', coupling='coupled')
        for field, value in [('rationale', ''), ('task_evidence', 'different-task'),
                             ('support', 'quality'), ('support', 'missing'),
                             ('candidate', {'route': 'codex', 'family': 'terra',
                                            'model': 'gpt-6.1-terra', 'effort': 'max'})]:
            with self.subTest(field=field, value=value):
                fit = self.task_fit_override()
                fit[field] = value
                with self.assertRaises(SelectionError):
                    self.select()

    def test_complete_estimates_take_precedence_over_requested_benchmark(self):
        terra, sol = self.selection['candidates']
        terra['usage_estimate'] = estimate(terra['model'], 100000)
        sol['usage_estimate'] = estimate(sol['model'], 1000)
        result = self.select()
        self.assertEqual(result['selected']['family'], 'sol')
        self.assertEqual(result['requested_comparison_basis'], 'benchmark_prior')
        self.assertEqual(result['comparison_basis'], 'whole_work_estimate')
        self.assertEqual([row['comparison_value'] for row in result['compared']], [.002, .1])
        terra['usage_estimate']['stages']['review'] = None
        result = self.select()
        self.assertEqual(result['comparison_basis'], 'benchmark_prior')
        self.assertIsNone(next(row for row in result['compared'] if row['candidate']['family'] == 'terra')
                          ['cost']['total_api_price_proxy_usd'])

    def test_separable_outcome_requires_work_units_not_all_terra(self):
        self.selection['task'].update(complexity='complex', decomposable=True, stage='outcome')
        result = self.select()
        self.assertEqual(result['status'], 'decompose')
        self.assertIsNone(result['selected'])
        self.selection['task'].update(complexity='bounded', stage='execution')
        self.assertEqual(self.select()['selected']['family'], 'terra')

    def test_unknown_or_malformed_semantics_cannot_fallback(self):
        for field, value in [('capability', 'anything'), ('complexity', None),
                             ('coupling', []), ('decomposable', 'true'), ('actor', 'CEO')]:
            with self.subTest(field=field):
                self.selection = request()
                self.selection['task'][field] = value
                with self.assertRaises(SelectionError):
                    self.select()

    def test_unknown_runtime_and_owner_report_cannot_fallback(self):
        for field, value in [('supported', None), ('authenticated', 'true'),
                             ('tools', 'unknown'), ('billing', 'unknown'), ('effort', 'ultra')]:
            with self.subTest(field=field):
                self.selection = request()
                self.selection['candidates'][0][field] = value
                with self.assertRaises(SelectionError):
                    self.select()
        self.selection = request()
        self.refs['runtime']['kind'] = 'human'
        with self.assertRaisesRegex(SelectionError, 'host evidence'):
            select(self.selection, self.refs, self.config)

    def test_unknown_quality_excluded_not_assumed_adequate(self):
        self.selection['candidates'][0]['quality'] = 'unknown'
        self.assertEqual(self.select()['selected']['family'], 'sol')
        self.selection['candidates'][1]['quality'] = 'insufficient'
        with self.assertRaisesRegex(SelectionError, 'No eligible'):
            self.select()

    def test_max_and_xhigh_remain_distinct_and_missing_prior_not_interpolated(self):
        self.selection['candidates'] = [candidate(effort='max'), candidate(effort='xhigh')]
        self.assertEqual(self.select()['selected']['effort'], 'xhigh')
        self.selection['candidates'] = [candidate('luna', 'low')]
        with self.assertRaisesRegex(SelectionError, 'exact-effort'):
            self.select()

    def test_api_requires_both_opt_in_and_current_scope_no_paid_fallback(self):
        self.selection['candidates'] = [candidate()]
        self.selection['candidates'][0]['billing'] = 'paid_api'
        for config_allowed, scope_allowed in ((False, False), (True, False), (False, True)):
            self.config['values']['api_paid'] = config_allowed
            self.selection['scope_api_authorized'] = scope_allowed
            with self.assertRaisesRegex(SelectionError, 'No eligible'):
                self.select()
        self.config['values']['api_paid'] = True
        self.selection['scope_api_authorized'] = True
        self.assertEqual(self.select()['status'], 'selected')  # advice, not a launch

    def test_resolved_services_exclusions_head_choices_and_order_preserved(self):
        self.config['values']['excluded_models'] = ['gpt-6.1-terra']
        self.assertEqual(self.select()['selected']['family'], 'sol')
        self.config['values']['excluded_models'] = []
        self.selection['task']['actor'] = 'company_head'
        self.config['values']['head_model'] = 'gpt-6.1-sol'
        self.assertEqual(self.select()['selected']['family'], 'sol')
        del self.config['values']['head_model']
        self.selection['candidates'][1] = unlisted_candidate(self.refs, route='cursor', family='other',
                                                              model='cursor-fixture', effort='high')
        self.config['values']['service_order'] = ['cursor', 'codex']
        self.assertEqual(self.select()['selected']['route'], 'cursor')
        self.config['values']['services'] = []
        with self.assertRaisesRegex(SelectionError, 'No eligible'):
            self.select()

    def test_whole_work_overhead_can_reverse_low_unit_price_and_mixed_models(self):
        self.selection['cost_basis'] = 'whole_work_estimate'
        for row in self.selection['candidates']:
            row['usage_estimate'] = estimate(row['model'])
        terra, sol = self.selection['candidates']
        self.assertEqual(self.select()['selected']['family'], 'terra')
        # Failed implementation and a strong-model review belong to the same workflow cost.
        retry = copy.deepcopy(terra['usage_estimate']['stages']['execution'][0])
        retry.update(id='retry-1', uncached_input=5000)
        terra['usage_estimate']['stages']['retries'] = [retry]
        review = copy.deepcopy(retry)
        review.update(id='review-1', model='gpt-6-astra', uncached_input=1000)
        terra['usage_estimate']['stages']['review'] = [review]
        result = self.select()
        self.assertEqual(result['selected']['family'], 'sol')
        self.assertAlmostEqual(result['compared'][1]['cost']['total_api_price_proxy_usd'], .016)
        self.assertAlmostEqual(result['compared'][0]['cost']['total_api_price_proxy_usd'], .002)

    def test_incomplete_usage_is_unknown_not_zero(self):
        self.selection['cost_basis'] = 'whole_work_estimate'
        for row in self.selection['candidates']:
            row['usage_estimate'] = estimate(row['model'])
        self.selection['candidates'][0]['usage_estimate']['stages']['review'] = None
        with self.assertRaisesRegex(SelectionError, 'Incomplete'):
            self.select()
        models = load_table()[0]['models']
        result = estimated_cost(self.selection['candidates'][0]['usage_estimate'], models, self.refs)
        self.assertIsNone(result['total_api_price_proxy_usd'])

    def test_duplicate_invalid_and_unsupported_price_units_rejected(self):
        models = load_table()[0]['models']
        for field, value in [('uncached_input', -1), ('cached_input', True), ('tools_usd', float('nan')),
                             ('tier', 'batch'), ('region', 'regional'), ('model', 'unknown')]:
            with self.subTest(field=field):
                usage = estimate('gpt-6.1-terra')
                usage['stages']['execution'][0][field] = value
                with self.assertRaises(SelectionError):
                    estimated_cost(usage, models, self.refs)
        usage = estimate('gpt-6.1-terra')
        usage['stages']['review'] = copy.deepcopy(usage['stages']['execution'])
        with self.assertRaisesRegex(SelectionError, 'unique'):
            estimated_cost(usage, models, self.refs)

    def test_long_context_rates_and_disjoint_cache_billing(self):
        models = load_table()[0]['models']
        usage = estimate('gpt-6.1-terra', 272000)
        unit = usage['stages']['execution'][0]
        unit.update(cached_input=1000, cache_write_30m=1000, output=1000)
        result = estimated_cost(usage, models, self.refs)
        self.assertAlmostEqual(result['total_api_price_proxy_usd'], .5541)


class SelectionCLITests(SelectionFixture, unittest.TestCase):
    def test_prelaunch_requires_selection_for_ordinary_assignment(self):
        packet = self.packet()
        del packet['price_selection']
        packet['selected_reason'] = 'ordinary_assignment'
        packet['alternatives'][0]['reason'] = 'ordinary_assignment'
        self.assertTrue(record_check.check_routing(packet, PACKAGE, prelaunch=False)['ok'])
        result = record_check.check_routing(packet, PACKAGE, prelaunch=True)
        self.assertIn('price_selection_required', [e['code'] for e in result['errors']])

    def test_prelaunch_complexity_does_not_exclude_adequate_terra(self):
        self.selection['task'].update(complexity='complex', coupling='coupled')
        self.selection['inventory_evidence'] = 'inventory'
        self.refs['inventory'] = {'ref': 'synthetic://inventory', 'sha256': None, 'kind': 'synthetic',
                                  'candidate_inventory': [{k: row[k] for k in ('route', 'family', 'model', 'effort')} for row in self.selection['candidates']]}
        result = select(self.selection, self.refs, self.config, synthetic=True, prelaunch=True)
        self.assertEqual(result['selected']['family'], 'terra')

    def test_prelaunch_rejects_omission_and_unbound_quality_exclusion(self):
        packet = self.packet()
        packet['price_selection']['candidates'].pop()
        result = record_check.check_routing(packet, PACKAGE, prelaunch=True)
        self.assertIn('price_selection_invalid', [e['code'] for e in result['errors']])
        packet = self.packet()
        terra, sol = packet['price_selection']['candidates']
        packet['price_selection']['candidates'] = [sol]
        packet['evidence']['inventory']['candidate_inventory'] = [{k: sol[k] for k in ('route', 'family', 'model', 'effort')}]
        for row in (packet['selected'], packet['alternatives'][0]):
            row.update({k: sol[k] for k in ('route', 'family', 'model', 'effort')})
        result = record_check.check_routing(packet, PACKAGE, prelaunch=True)
        self.assertTrue(any('host and table' in e['message'] for e in result['errors']))
        packet = self.packet()
        packet['price_selection']['candidates'][1]['quality'] = 'unknown'
        result = record_check.check_routing(packet, PACKAGE, prelaunch=True)
        self.assertIn('price_selection_invalid', [e['code'] for e in result['errors']])

    def test_prelaunch_rejects_dominated_pair(self):
        self.selection['candidates'] = [candidate('terra', 'medium'), candidate('sol', 'medium')]
        packet = self.packet()
        packet['selected'].update(model='gpt-6.1-sol', family='sol', effort='medium')
        packet['alternatives'][0].update(model='gpt-6.1-sol', family='sol', effort='medium')
        result = record_check.check_routing(packet, PACKAGE, prelaunch=True)
        self.assertIn('price_selection_invalid', [e['code'] for e in result['errors']])

    def test_three_known_medium_candidates_select_terra(self):
        self.selection['candidates'] = [candidate('terra', 'medium'), candidate('sol', 'medium'), candidate('astra', 'medium')]
        packet = self.packet()
        result = record_check.check_routing(packet, PACKAGE, prelaunch=True)
        self.assertTrue(result['ok'], result['errors'])
        self.assertEqual(result['receipt']['selected']['model'], 'gpt-6.1-terra')
        for row in (packet['selected'], packet['alternatives'][0]):
            row.update(model='gpt-6-astra', family='astra')
        self.assertIn('price_selection_invalid', [e['code'] for e in record_check.check_routing(packet, PACKAGE, prelaunch=True)['errors']])

    def test_prelaunch_rejects_equal_cost_lower_score(self):
        self.selection['candidates'] = [candidate('sol', 'high'), candidate('sol', 'xhigh')]
        packet = self.packet()
        packet['selected']['effort'] = 'high'
        packet['alternatives'][0]['effort'] = 'high'
        result = record_check.check_routing(packet, PACKAGE, prelaunch=True)
        self.assertIn('price_selection_invalid', [e['code'] for e in result['errors']])

    def test_prelaunch_rejects_omitted_dominating_other_effort(self):
        self.selection['candidates'] = [candidate('terra', 'high')]
        packet = self.packet()
        packet['evidence']['inventory']['host_models'][0]['supported_reasoning_levels'].append({'effort': 'medium'})
        result = record_check.check_routing(packet, PACKAGE, prelaunch=True)
        self.assertTrue(any('host and table' in e['message'] for e in result['errors']))

    def test_prelaunch_preserves_explicit_bound_user_pin(self):
        packet = self.packet()
        del packet['price_selection']
        packet['selected_reason'] = 'user_pin'
        packet['alternatives'][0]['reason'] = 'user_pin'
        packet['evidence']['quality']['binds'] = {k: packet['selected'][k] for k in ('route', 'family', 'model', 'effort')}
        packet['evidence']['quality']['task_binding'] = {k: packet['binding'][k] for k in ('task', 'scope', 'revision', 'attempt')}
        self.assertTrue(record_check.check_routing(packet, PACKAGE, prelaunch=True)['ok'])
        packet['evidence']['quality']['task_binding']['task'] = 'other-task'
        self.assertIn('unbound_pin', [e['code'] for e in record_check.check_routing(packet, PACKAGE, prelaunch=True)['errors']])

    def test_prelaunch_accepts_bound_task_failure(self):
        packet = self.packet()
        row = packet['price_selection']['candidates'][1]
        row['quality'] = 'insufficient'
        row['quality_evidence'] = 'failure'
        packet['evidence']['failure'] = {'ref': 'synthetic://failure', 'kind': 'synthetic', 'sha256': None,
            'task_failure': {'task_evidence': packet['price_selection']['task']['evidence'],
                'candidate': {k: row[k] for k in ('route', 'family', 'model', 'effort')}, 'support': 'quality'}}
        self.assertTrue(record_check.check_routing(packet, PACKAGE, prelaunch=True)['ok'])

    def test_prelaunch_accepts_bound_tool_unavailability(self):
        packet = self.packet()
        row = packet['price_selection']['candidates'][1]
        row['tools'] = 'unsupported'
        row['runtime_evidence'] = 'unavailable'
        packet['evidence']['unavailable'] = {'ref': 'synthetic://unavailable', 'kind': 'synthetic', 'sha256': None,
            'unavailable_candidates': [{k: row[k] for k in ('route', 'family', 'model', 'effort')}]}
        self.assertTrue(record_check.check_routing(packet, PACKAGE, prelaunch=True)['ok'])

    def packet(self):
        routes = json.loads((PACKAGE / 'assets/routing-cases.json').read_text())
        packet = copy.deepcopy(next(c['decision'] for c in routes['cases'] if not c['expected_errors']))
        selected = self.select()['selected']
        packet.update(trigger='initial', failure_class=None, prior=None, selected_reason='price_informed',
                      price_selection=self.selection)
        packet['selected'] = {**selected, 'supported': True, 'evidence': 'runtime', 'reason_evidence': 'quality'}
        packet['alternatives'] = [{**selected, 'disposition': 'selected', 'reason': 'price_informed', 'evidence': 'runtime'}]
        packet['constraints']['quality'] = 'met'
        packet['evidence'].update(self.refs)
        packet['price_selection'] = copy.deepcopy(self.selection)
        packet['price_selection']['inventory_evidence'] = 'inventory'
        packet['evidence']['inventory'] = {'ref': 'synthetic://inventory', 'sha256': None, 'kind': 'synthetic',
            'candidate_inventory': [{k: row[k] for k in ('route', 'family', 'model', 'effort')} for row in self.selection['candidates']],
            'host_models': [{'slug': row['model'], 'supported_reasoning_levels': [{'effort': row['effort']}]} for row in self.selection['candidates']]}
        return packet

    def invoke(self, command, packet, expected=0, record=None):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'route.json'
            path.write_text(json.dumps(packet))
            before = path.read_bytes()
            args = [sys.executable, '-I', str(CLI), command, str(path), '--json']
            if record is not None:
                rpath = Path(tmp) / 'record.json'
                rpath.write_text(json.dumps(record))
                args += ['--record', str(rpath)]
            process = subprocess.run(args, capture_output=True, text=True, cwd=tmp)
            self.assertEqual(process.returncode, expected, process.stdout + process.stderr)
            self.assertNotIn('Traceback', process.stderr)
            self.assertEqual(before, path.read_bytes())
            return json.loads(process.stdout)

    def test_cli_advice_and_routing_check_use_same_selection(self):
        packet = self.packet()
        advice = self.invoke('routing-select', packet)
        checked = self.invoke('routing-check', packet)
        self.assertEqual(advice['advice'], checked['receipt']['price_selection'])
        self.assertEqual(advice['request_sha256'], checked['receipt']['decision_sha256'])
        self.assertEqual(checked['receipt']['selected']['family'], 'terra')

    def test_cli_tampering_and_malformed_input_fail_closed(self):
        packet = self.packet()
        packet['selected'].update(model='gpt-6.1-sol', family='sol')
        packet['alternatives'][0].update(model='gpt-6.1-sol', family='sol')
        result = self.invoke('routing-check', packet, 1)
        self.assertIn('price_selection_invalid', [e['code'] for e in result['errors']])
        for value in (None, [], {}, {'version': '1'}):
            packet = self.packet()
            packet['price_selection'] = value
            result = self.invoke('routing-check', packet, 1)
            self.assertIn('price_selection_invalid', [e['code'] for e in result['errors']])

    def test_cli_decomposition_advice_is_not_launch_receipt(self):
        packet = self.packet()
        packet['price_selection']['task'].update(complexity='complex', decomposable=True, stage='outcome')
        self.assertEqual(self.invoke('routing-select', packet)['advice']['status'], 'decompose')
        result = self.invoke('routing-check', packet, 1)
        self.assertIn('price_selection_incomplete', [e['code'] for e in result['errors']])

    def test_cli_cannot_ignore_complete_estimates_using_prior_selection(self):
        terra, sol = self.selection['candidates']
        terra['usage_estimate'] = estimate(terra['model'], 100000)
        sol['usage_estimate'] = estimate(sol['model'], 1000)
        packet = self.packet()
        checked = self.invoke('routing-check', packet)
        self.assertEqual(checked['receipt']['selected']['family'], 'sol')
        self.assertEqual(checked['receipt']['price_selection']['comparison_basis'], 'whole_work_estimate')
        packet['selected'].update(model=terra['model'], family='terra')
        packet['alternatives'][0].update(model=terra['model'], family='terra')
        result = self.invoke('routing-check', packet)
        self.assertEqual(result['receipt']['selected']['family'], 'terra')

    def test_cli_current_record_binding_still_applies(self):
        packet = self.packet()
        packet['binding'].update(task='new', attempt='planned:new', planned=True)
        records = json.loads((PACKAGE / 'assets/record-cases.json').read_text())
        record = copy.deepcopy(records['cases'][0]['record'])
        self.assertTrue(self.invoke('routing-check', packet, record=record)['ok'])
        packet['binding']['revision'] = 'stale'
        result = self.invoke('routing-check', packet, 1, record=record)
        self.assertIn('stale_binding', [e['code'] for e in result['errors']])


if __name__ == '__main__':
    unittest.main()
