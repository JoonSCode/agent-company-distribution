#!/usr/bin/env python3
"""Unlisted routes and Codex gates, using synthetic or local fake host evidence."""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import record_check
import test_route_select


class UnlistedRoutingTests(unittest.TestCase):
    def setUp(self):
        fixture = test_route_select.SelectionCLITests()
        fixture.setUp()
        self.config = fixture.config
        self.config['configuration_sha256'] = 'a' * 64
        self.config['values']['services'] = ['codex', 'antigravity', 'grok', 'cursor']
        self.packet = fixture.packet()
        row = test_route_select.unlisted_candidate(self.packet['evidence'])
        self.packet['price_selection']['candidates'].append(row)
        self.packet['evidence']['inventory']['candidate_inventory'].append(self.identity(row))
        self.choose(row)

    @staticmethod
    def identity(row):
        return {key: row[key] for key in ('route', 'family', 'model', 'effort')}

    def choose(self, row):
        selected = self.identity(row)
        self.packet['selected'] = {**selected, 'supported': True, 'evidence': row['runtime_evidence'],
                                   'reason_evidence': row['quality_evidence']}
        self.packet['alternatives'] = [{**selected, 'disposition': 'selected',
                                        'reason': 'ordinary_assignment', 'evidence': row['runtime_evidence']}]
        self.packet['selected_reason'] = 'ordinary_assignment'

    def check(self, packet=None, base=None):
        with patch('record_check.resolve', return_value=self.config):
            return record_check.check_routing(packet or self.packet, base or Path('.'), prelaunch=True)

    def test_flash_and_grok_are_bound_without_inventing_prices(self):
        for route, family, model, effort in (('antigravity', 'flash', 'gemini-3.8-flash-high', 'high'),
                                             ('grok', 'grok', 'grok-4.7', None)):
            with self.subTest(route=route):
                packet = copy.deepcopy(self.packet)
                row = test_route_select.unlisted_candidate(packet['evidence'], route, family, model, effort)
                packet['price_selection']['candidates'][-1] = row
                packet['evidence']['inventory']['candidate_inventory'][-1] = self.identity(row)
                self.packet = packet
                self.choose(row)
                result = self.check()
                self.assertTrue(result['ok'], result['errors'])
                comparison = result['receipt']['price_selection']
                selected = next(r for r in comparison['compared'] if r['candidate'] == self.identity(row))
                self.assertIsNone(selected['comparison_value'])
                self.assertIsNone(selected['cost']['total_api_price_proxy_usd'])
                self.assertIsNone(comparison['actual_usage'])
                self.assertIsNone(comparison['effective_model'])

    def test_unlisted_missing_stale_or_wrong_evidence_fails(self):
        for mutation in ('missing_model_ref', 'missing_support_ref', 'missing_auth_ref', 'missing_tools_ref', 'missing_billing_ref',
                         'wrong_agent', 'wrong_model', 'wrong_effort', 'expired', 'unsupported',
                         'unauthenticated', 'tools_unknown', 'billing_unknown', 'missing_task_fit',
                         'wrong_task_fit', 'invented_estimate', 'price_informed', 'invented_tokens'):
            with self.subTest(mutation=mutation):
                packet = copy.deepcopy(self.packet)
                row = packet['price_selection']['candidates'][-1]
                runtime = packet['evidence']['unlisted-runtime']['unlisted_runtime']
                if mutation.startswith('missing_') and mutation.endswith('_ref'):
                    key = {'missing_model_ref': 'model_evidence', 'missing_support_ref': 'support_evidence', 'missing_auth_ref': 'auth_evidence',
                           'missing_tools_ref': 'tools_evidence', 'missing_billing_ref': 'billing_evidence'}[mutation]
                    runtime[key] = 'missing'
                elif mutation == 'wrong_agent':
                    runtime['agent'] = 'codex'
                elif mutation == 'wrong_model':
                    runtime['candidate']['model'] = 'different'
                elif mutation == 'wrong_effort':
                    runtime['candidate']['effort'] = 'medium'
                elif mutation == 'expired':
                    runtime['observed_at'] = '2000-01-01T00:00:00+00:00'
                    runtime['valid_until'] = '2000-01-01T01:00:00+00:00'
                elif mutation == 'unsupported':
                    row['supported'] = False
                elif mutation == 'unauthenticated':
                    row['authenticated'] = False
                elif mutation == 'tools_unknown':
                    row['tools'] = 'unknown'
                elif mutation == 'billing_unknown':
                    row['billing'] = 'unknown'
                elif mutation == 'missing_task_fit':
                    del packet['evidence']['unlisted-quality']['task_fit']
                elif mutation == 'wrong_task_fit':
                    packet['evidence']['unlisted-quality']['task_fit']['candidate']['effort'] = 'medium'
                elif mutation == 'invented_estimate':
                    row['usage_estimate'] = test_route_select.estimate('gpt-6.1-terra')
                elif mutation == 'price_informed':
                    packet['selected_reason'] = packet['alternatives'][0]['reason'] = 'price_informed'
                elif mutation == 'invented_tokens':
                    packet['tokens'] = {'input': 100, 'output': 0, 'basis': 'unknown'}
                result = self.check(packet)
                self.assertFalse(result['ok'], (mutation, result))
                print(mutation, sorted({e['code'] for e in result['errors']}))

    def test_codex_alias_and_table_omission_do_not_bypass_comparison(self):
        for model, route, family in (('gpt-6.1-terra', 'antigravity', 'flash'),
                                      ('provider/gpt-6.1-terra-alias', 'antigravity', 'flash'),
                                      ('gemini-3.8-flash-high', 'codex', 'flash')):
            with self.subTest(model=model, route=route):
                packet = copy.deepcopy(self.packet)
                row = packet['price_selection']['candidates'][-1]
                row.update(model=model, route=route, family=family)
                packet['evidence']['inventory']['candidate_inventory'][-1] = self.identity(row)
                packet['selected'].update(self.identity(row))
                packet['alternatives'][0].update(self.identity(row))
                self.assertFalse(self.check(packet)['ok'])
        packet = copy.deepcopy(self.packet)
        packet['price_selection']['candidates'].pop(0)
        packet['evidence']['inventory']['candidate_inventory'].pop(0)
        result = self.check(packet)
        self.assertTrue(any('host and table' in e['message'] for e in result['errors']), result['errors'])

    def test_same_model_on_other_route_needs_own_evidence_and_has_no_codex_price(self):
        packet = copy.deepcopy(self.packet)
        row = test_route_select.unlisted_candidate(packet['evidence'], 'cursor', 'terra', 'gpt-6.1-terra', 'low')
        packet['price_selection']['candidates'][-1] = row
        packet['evidence']['inventory']['candidate_inventory'][-1] = self.identity(row)
        self.packet = packet
        self.choose(row)
        result = self.check()
        self.assertTrue(result['ok'], result['errors'])
        selected = next(item for item in result['receipt']['price_selection']['compared']
                        if item['candidate'] == self.identity(row))
        self.assertIsNone(selected['comparison_value'])
        self.assertIsNone(selected['cost']['total_api_price_proxy_usd'])
        del packet['evidence']['unlisted-runtime']['unlisted_runtime']['model_evidence']
        self.assertFalse(self.check()['ok'])

    def test_unlisted_user_pin_still_requires_bound_current_runtime(self):
        packet = copy.deepcopy(self.packet)
        packet['selected_reason'] = packet['alternatives'][0]['reason'] = 'user_pin'
        evidence = packet['evidence']['unlisted-quality']
        evidence['binds'] = self.identity(packet['selected'])
        evidence['task_binding'] = {k: packet['binding'][k] for k in ('task', 'scope', 'revision', 'attempt')}
        self.assertTrue(self.check(packet)['ok'], self.check(packet)['errors'])
        self.config['values']['excluded_models'] = [packet['selected']['model']]
        self.assertTrue(self.check(packet)['ok'], self.check(packet)['errors'])
        self.config['values']['excluded_models'] = []
        evidence['task_binding']['task'] = 'wrong'
        self.assertFalse(self.check(packet)['ok'])
        evidence['task_binding']['task'] = packet['binding']['task']
        del packet['price_selection']
        self.assertFalse(self.check(packet)['ok'])

    def test_mixed_inventory_still_rejects_dominated_codex(self):
        fixture = test_route_select.SelectionCLITests()
        fixture.setUp()
        fixture.selection['candidates'] = [test_route_select.candidate('terra', 'medium'),
                                           test_route_select.candidate('sol', 'medium')]
        packet = fixture.packet()
        unlisted = test_route_select.unlisted_candidate(packet['evidence'])
        packet['price_selection']['candidates'].append(unlisted)
        packet['evidence']['inventory']['candidate_inventory'].append(self.identity(unlisted))
        packet['selected'].update(model='gpt-6.1-sol', family='sol', effort='medium')
        packet['alternatives'][0].update(model='gpt-6.1-sol', family='sol', effort='medium')
        result = self.check(packet)
        self.assertTrue(any('dominated' in error['message'] for error in result['errors']), result['errors'])
        packet['selected'].update(model='gpt-6.1-terra', family='terra')
        packet['alternatives'][0].update(model='gpt-6.1-terra', family='terra')
        self.assertTrue(self.check(packet)['ok'], self.check(packet)['errors'])

    def test_legacy_record_remains_readable_without_authorizing_new_alias(self):
        fixture = test_route_select.SelectionCLITests()
        fixture.setUp()
        packet = fixture.packet()
        packet['price_selection']['candidates'][1]['route'] = 'cursor'
        packet['selected'].update(route='cursor', model='gpt-6.1-sol', family='sol')
        packet['alternatives'][0].update(route='cursor', model='gpt-6.1-sol', family='sol')
        del packet['price_selection']['inventory_evidence']
        packet['receipt_evidence'] = 'runtime'
        self.config['values']['service_order'] = ['cursor', 'codex']
        with patch('record_check.resolve', return_value=self.config):
            checker = record_check.Checker('.')
            checker.evidence_map(packet['evidence'], '$.evidence', 'synthetic')
            checker.routing(packet, '$', None, require_receipt=True)
            self.assertFalse(checker.errors, checker.errors)
        self.assertFalse(self.check(packet)['ok'])

    def test_real_labeled_files_are_pinned_current_and_contain_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            packet = copy.deepcopy(self.packet)
            packet['label'] = 'real'
            now = datetime.now(timezone.utc)
            start, end = (now - timedelta(minutes=1)).isoformat(), (now + timedelta(minutes=10)).isoformat()
            for evidence in packet['evidence'].values():
                evidence['kind'] = 'host'
            for key in ('unlisted-quality', 'quality'):
                source = root / (key + '-fit.txt')
                source.write_text('fixture task-fit evidence\n')
                packet['evidence'][key].update(file=str(source), sha256=hashlib.sha256(source.read_bytes()).hexdigest())
            cache = root / 'models_cache.json'
            cache.write_text(json.dumps({'models': packet['evidence']['inventory']['host_models']}))
            inv = packet['evidence']['inventory']
            inv.update(file=str(cache), sha256=hashlib.sha256(cache.read_bytes()).hexdigest(), host='fixture-host', observed_at=start, valid_until=end)
            raw = root / 'raw-source.txt'
            raw.write_text('fixture host source\n')
            packet['evidence']['raw-source'] = {'ref': 'raw-source', 'kind': 'host', 'host': 'fixture-host', 'file': str(raw),
                'sha256': hashlib.sha256(raw.read_bytes()).hexdigest(), 'observed_at': start, 'valid_until': end}
            for key in ('unlisted-models', 'unlisted-support', 'unlisted-auth', 'unlisted-tools', 'unlisted-billing'):
                source = root / (key + '.txt')
                if key == 'unlisted-models':
                    source.write_text('gemini-3.8-flash-high\tFixture (High)\n')
                else:
                    claim, value = {'unlisted-support': ('supported', True), 'unlisted-auth': ('authenticated', True), 'unlisted-tools': ('tools', 'supported'),
                                    'unlisted-billing': ('billing', 'subscription')}[key]
                    source.write_text(json.dumps({'format': 'company-runtime-observation/v1',
                        'candidate': self.identity(packet['selected']), 'agent': 'antigravity', 'host': 'fixture-host',
                        'claim': claim, 'value': value, 'source_evidence': 'raw-source'}))
                packet['evidence'][key].update(file=str(source), host='fixture-host', sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                                               observed_at=start, valid_until=end)
            with patch('record_check.canonical_home', return_value=root):
                packet['binding']['spec_sha256'] = 'b' * 64
                preflight = self.check(packet, root)
                self.assertTrue(preflight['ok'], preflight['errors'])
                foreign = copy.deepcopy(packet)
                foreign['evidence']['inventory']['host'] = 'fixture-other'
                self.assertFalse(self.check(foreign, root)['ok'])
                del foreign['evidence']['inventory']['host']
                self.assertFalse(self.check(foreign, root)['ok'])
                alternate = copy.deepcopy(packet)
                alternate_row = alternate['price_selection']['candidates'][-1]
                alternate_row.update(route='cursor', family='terra', model='gpt-6.1-terra', effort='low')
                alternate_id = self.identity(alternate_row)
                alternate['selected'].update(alternate_id)
                alternate['alternatives'][0].update(alternate_id)
                alternate['evidence']['inventory']['candidate_inventory'][-1] = alternate_id
                runtime = alternate['evidence']['unlisted-runtime']['unlisted_runtime']
                runtime.update(candidate=alternate_id, agent='cursor')
                alternate['evidence']['unlisted-quality']['task_fit']['candidate'] = alternate_id
                alternate_model = root / 'alternate-models.txt'
                alternate_model.write_text(json.dumps({'models': [{'id': 'gpt-6.1-terra',
                    'supported_reasoning_levels': [{'effort': 'low'}]}]}))
                alternate['evidence']['unlisted-models'].update(file=str(alternate_model),
                    sha256=hashlib.sha256(alternate_model.read_bytes()).hexdigest())
                for key, claim, value in (('unlisted-support', 'supported', True),
                                          ('unlisted-auth', 'authenticated', True),
                                          ('unlisted-tools', 'tools', 'supported'),
                                          ('unlisted-billing', 'billing', 'subscription')):
                    source = root / ('alternate-' + key + '.json')
                    source.write_text(json.dumps({'format': 'company-runtime-observation/v1',
                        'candidate': alternate_id, 'agent': 'cursor', 'host': 'fixture-host',
                        'claim': claim, 'value': value, 'source_evidence': 'raw-source'}))
                    alternate['evidence'][key].update(file=str(source), sha256=hashlib.sha256(source.read_bytes()).hexdigest())
                checked_alternate = self.check(alternate, root)
                self.assertTrue(checked_alternate['ok'], checked_alternate['errors'])
                alt_compared = next(item for item in checked_alternate['receipt']['price_selection']['compared']
                                    if item['candidate'] == alternate_id)
                self.assertIsNone(alt_compared['comparison_value'])
                alternate_model.write_text('gpt-6.1-terra-other\n')
                alternate['evidence']['unlisted-models']['sha256'] = hashlib.sha256(alternate_model.read_bytes()).hexdigest()
                self.assertFalse(self.check(alternate, root)['ok'])
                packet['evidence']['quality']['kind'] = 'synthetic'
                self.assertFalse(self.check(packet, root)['ok'])
                packet['evidence']['quality']['kind'] = 'host'
                del packet['evidence']['unlisted-quality']['file']
                self.assertFalse(self.check(packet, root)['ok'])
                packet['evidence']['unlisted-quality']['file'] = str(root / 'unlisted-quality-fit.txt')
                receipt = {'ok': True, 'label': 'real', 'receipt': {
                    'binding': copy.deepcopy(packet['binding']), 'selected': copy.deepcopy(packet['selected']),
                    'spec_sha256': 'b' * 64, 'price_selection': preflight['receipt']['price_selection']}}
                receipt_path = root / 'preflight.json'
                receipt_path.write_text(json.dumps(receipt))
                packet['evidence']['receipt'] = {'ref': 'receipt', 'kind': 'host', 'file': str(receipt_path),
                    'sha256': hashlib.sha256(receipt_path.read_bytes()).hexdigest()}
                packet['receipt_evidence'] = 'receipt'
                with patch('record_check.resolve', return_value=self.config):
                    checker = record_check.Checker(root)
                    checker.evidence_map(packet['evidence'], '$.evidence', 'real')
                    replay = checker.price_selection(packet, '$.price_selection', recorded_prelaunch=True)
                    self.assertFalse(checker.errors, checker.errors)
                    self.assertEqual(replay['selected'], self.identity(packet['selected']))
                model_file = root / 'unlisted-models.txt'
                model_file.write_text('different-model\n')
                packet['evidence']['unlisted-models']['sha256'] = hashlib.sha256(model_file.read_bytes()).hexdigest()
                self.assertFalse(self.check(packet, root)['ok'])
                model_file.write_text('gemini-3.8-flash-high\tFixture (High)\n')
                self.assertFalse(self.check(packet, root)['ok'])  # stale hash
                packet['evidence']['unlisted-models']['sha256'] = hashlib.sha256(model_file.read_bytes()).hexdigest()
                packet['evidence']['unlisted-auth']['valid_until'] = '2000-01-01T00:00:00+00:00'
                self.assertFalse(self.check(packet, root)['ok'])
                packet['evidence']['unlisted-auth']['valid_until'] = end
                billing = root / 'unlisted-billing.txt'
                billing.write_text('unrelated text')
                packet['evidence']['unlisted-billing']['sha256'] = hashlib.sha256(billing.read_bytes()).hexdigest()
                self.assertFalse(self.check(packet, root)['ok'])

    def test_only_supported_catalog_shapes_bind_exact_model_and_effort(self):
        row = {'route': 'cursor', 'model': 'gpt-6.1-terra', 'effort': 'low'}
        def catalog(model='gpt-6.1-terra', effort='low', **extra):
            return json.dumps({'models': [{'id': model, 'supported_reasoning_levels': [{'effort': effort}]}], **extra})
        self.assertTrue(record_check.catalog_supports_candidate(catalog(), row))
        self.assertFalse(record_check.catalog_supports_candidate(catalog(effort='high'), row))
        self.assertFalse(record_check.catalog_supports_candidate(catalog(model='other', error='gpt-6.1-terra unavailable'), row))
        self.assertFalse(record_check.catalog_supports_candidate(catalog(error='unavailable'), row))
        self.assertFalse(record_check.catalog_supports_candidate(json.dumps({'models': [{'id': row['model']}]}), row))
        self.assertFalse(record_check.catalog_supports_candidate('gpt-6.1-terra\n', row))

        agy = {'route': 'antigravity', 'model': 'fixture-model-high', 'effort': 'high'}
        agy_list = 'fixture-model-low\tFixture (Low)\nfixture-model-high\tFixture (High)\n'
        self.assertTrue(record_check.catalog_supports_candidate(agy_list, agy))
        self.assertFalse(record_check.catalog_supports_candidate(agy_list, {**agy, 'effort': 'low'}))
        self.assertFalse(record_check.catalog_supports_candidate('error: fixture-model-high unavailable\n', agy))
        self.assertFalse(record_check.catalog_supports_candidate(agy_list + 'error: unavailable\n', agy))

        grok = {'route': 'grok', 'model': 'fixture-grok', 'effort': None}
        grok_list = 'You are logged in with grok.com.\n\nDefault model: fixture-grok\n\nAvailable models:\n  * fixture-grok (default)\n  - fixture-grok-other\n'
        self.assertTrue(record_check.catalog_supports_candidate(grok_list, grok))
        self.assertFalse(record_check.catalog_supports_candidate(grok_list, {**grok, 'effort': 'high'}))
        self.assertFalse(record_check.catalog_supports_candidate(grok_list + 'error: unavailable\n', grok))


if __name__ == '__main__':
    unittest.main(verbosity=2)
