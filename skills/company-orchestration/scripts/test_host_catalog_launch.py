"""Synthetic end-to-end checked-launch fixtures; NEVER a mocked live-host claim."""
import copy
from contextlib import closing, redirect_stdout
from datetime import datetime, timedelta, timezone
import hashlib
from io import StringIO
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import company_config
import record_check
import routing_launch
from catalog_test_support import CatalogFixture, launch_fixture, bind_history_run


class HostCatalogLaunchTests(unittest.TestCase):
    def setUp(self):
        self.fixture = self.enterContext(launch_fixture(company_config.resolve))

    def write_packet(self):
        self.fixture.write_packet()

    def invoke_catalog(self):
        return self.fixture.invoke(routing_launch.main)

    def test_catalog_churn_reaches_fake_checked_host(self):
        self.fixture.inventory.cache.write_text('{unrelated malformed global cache churn')
        code, output = self.invoke_catalog()
        self.assertEqual((code, self.fixture.refreshes, self.fixture.starts), (0, 1, 1), output)
        receipt = json.loads((self.fixture.inventory.root/'preflight.json').read_text())['receipt']
        self.assertEqual(receipt['host_catalog']['prepared_manifest_sha256'], self.fixture.catalog.digest)
        self.assertEqual(receipt['selected']['model'], self.fixture.inventory.packet['selected']['model'])
        self.assertEqual(json.loads((self.fixture.inventory.root/'result.json').read_text())['launch_state'], 'observed')

    def test_default_catalog_without_comparison_reaches_fake_checked_host(self):
        bind_history_run(self.fixture)
        packet = self.fixture.inventory.packet
        record = json.loads((self.fixture.inventory.root / 'record.json').read_text())
        comparison = packet.pop('price_selection')
        packet['binding']['inventory_evidence'] = comparison['inventory_evidence']
        selected = packet['selected']
        candidate = next(row for row in comparison['candidates']
                         if all(row[k] == selected[k] for k in ('route', 'family', 'model', 'effort')))
        packet['selected_runtime'] = {k: candidate[k] for k in
                                      ('route', 'family', 'model', 'effort', 'supported',
                                       'authenticated', 'tools', 'billing', 'runtime_evidence')}
        packet['selected_reason'] = 'ordinary_assignment'
        binding = packet['profile_binding']
        availability = {row['id']: [level['value'] for level in row['efforts']]
                        for row in self.fixture.catalog.response['result']['models']}
        packet['profile_binding'] = record_check.make_profile_binding(
            binding['profile'], binding['table'], binding['unit_id'], codex_availability=availability)
        packet['alternatives'] = [{**{k: selected[k] for k in ('route', 'family', 'model', 'effort')},
                                   'disposition': 'selected', 'reason': 'ordinary_assignment',
                                   'evidence': selected['evidence']}]
        self.write_packet()
        code, output = self.invoke_catalog()
        self.assertEqual((code, self.fixture.refreshes, self.fixture.starts), (0, 1, 1), output)
        receipt = json.loads((self.fixture.inventory.root/'preflight.json').read_text())['receipt']
        self.assertNotIn('price_selection', receipt)
        self.assertEqual(receipt['host_catalog']['prepared_manifest_sha256'], self.fixture.catalog.digest)
        task = record['tasks'][0]
        history = copy.deepcopy(packet)
        history['binding'].update(task=task['id'], scope=record['goal']['scope'],
                                  revision=record['goal']['revision'], attempt=task['current_dispatch'], planned=False)
        history['receipt_evidence'] = 'preflight'
        history['launch_evidence'] = 'launch'
        record['label'] = 'real'
        for value in record['evidence'].values():
            value['kind'] = 'host'
        record['evidence'].update(history['evidence'])
        original = self.fixture.inventory.root / 'preflight.json'
        record['evidence']['preflight'] = {'ref': 'fixture://preflight', 'kind': 'host',
                                            'file': str(original), 'sha256': hashlib.sha256(original.read_bytes()).hexdigest()}
        launch = self.fixture.inventory.root / 'result.json'
        record['evidence']['launch'] = {'ref': 'fixture://launch', 'kind': 'host',
                                        'file': str(launch), 'sha256': hashlib.sha256(launch.read_bytes()).hexdigest()}
        task['routing_decision'] = history
        task['model'].update(requested=selected['model'], effort_requested=selected['effort'])
        checked = record_check.check_record(record, self.fixture.inventory.root)
        self.assertTrue(checked['ok'], checked)
        self.assertEqual(checked['historical_integrity']['status'], 'valid')
        observed = self.fixture.observed
        original_observation = observed.read_bytes()
        observed.write_bytes(original_observation + b'\nchanged later\n')
        after = record_check.check_record(record, self.fixture.inventory.root)
        self.assertEqual(after['historical_integrity']['status'], 'valid')
        self.assertEqual(after['current_readiness']['status'], 'blocked')
        observed.write_bytes(original_observation)
        history['binding']['spec_sha256'] = 'f' * 64
        checked = record_check.check_record(record, self.fixture.inventory.root)
        self.assertIn('selected_runtime_receipt_invalid', [e['code'] for e in checked['errors']])

    def test_catalog_prelaunch_negatives(self):
        original = copy.deepcopy(self.fixture.inventory.packet)
        original_args = list(self.fixture.inventory.args)
        for kind in ('model', 'effort', 'worktree', 'runtime', 'config', 'authpolicy', 'stale', 'tamper', 'paid', 'auth', 'profile'):
            with self.subTest(kind=kind):
                self.fixture.inventory.packet = copy.deepcopy(original)
                self.fixture.inventory.args = list(original_args)
                self.fixture.inventory.args[self.fixture.inventory.args.index('--result')+1] = str(self.fixture.inventory.root/(kind+'.result'))
                context = self.fixture.inventory.packet['binding']['host_catalog']
                if kind in ('model', 'effort'): self.fixture.inventory.packet['selected'][kind] = 'changed'
                if kind == 'worktree': self.fixture.inventory.args[self.fixture.inventory.args.index('--worktree')+1] = 'current'
                if kind == 'runtime': context['runtime_id'] = 'changed'
                if kind == 'config': context['configuration_sha256'] = '0'*64
                if kind == 'authpolicy': context['observed_files'][0]['sha256'] = '0'*64
                if kind == 'stale':
                    self.fixture.catalog.response['result']['fetchedAt'] = 1
                    self.fixture.catalog.save()
                    self.fixture.inventory.packet['evidence']['inventory']['sha256'] = self.fixture.catalog.digest
                if kind == 'tamper': (self.fixture.catalog.root/'response-1.json').write_text('{}')
                if kind == 'paid': self.fixture.inventory.packet['constraints']['billing'] = 'paid_api'
                if kind == 'auth': self.fixture.inventory.packet['price_selection']['candidates'][0]['authenticated'] = False
                if kind == 'profile': self.fixture.inventory.packet['profile_binding'] = {'version': 0}
                self.write_packet()
                code, output = self.invoke_catalog()
                self.assertEqual((code, self.fixture.starts), (1, 0), output)
                self.fixture.catalog.response['result']['fetchedAt'] = self.fixture.catalog.now.timestamp()*1000
                self.fixture.catalog.save()
                original['evidence']['inventory']['sha256'] = self.fixture.catalog.digest

    def test_config_change_during_refresh_denies_before_start(self):
        self.fixture.change_at_refresh = lambda _: self.fixture.observed.write_text('changed auth policy')
        code, output = self.invoke_catalog()
        self.assertEqual((code, self.fixture.refreshes, self.fixture.starts), (1, 1, 0), output)

    def test_configured_table_change_during_refresh_denies_before_start(self):
        inventory = self.fixture.inventory
        table = inventory.root / 'configured-table.json'
        table.write_text(json.dumps(inventory.packet['profile_binding']['table']))
        pin = hashlib.sha256(table.read_bytes()).hexdigest()
        config = inventory.root / 'user.md'
        config.write_text('---\nschema_version: 1\npreset: single\nservices: ["codex"]\napi_paid: false\nworker_table: "' + str(table) + '#sha256=' + pin + '"\n---\n')
        inventory.packet['binding']['host_catalog']['configuration_sha256'] = company_config.resolve()['configuration_sha256']
        self.fixture.write_packet()
        self.fixture.change_at_refresh = lambda _: table.write_text(table.read_text() + ' ')
        code, output = self.invoke_catalog()
        self.assertEqual((code, self.fixture.refreshes, self.fixture.starts), (1, 1, 0), output)

    def test_self_consistent_unconfigured_table_denied_before_host(self):
        packet = self.fixture.inventory.packet
        binding = packet['profile_binding']
        changed = copy.deepcopy(binding['table'])
        changed['source'] += ' unconfigured'
        packet['profile_binding'] = record_check.make_profile_binding(binding['profile'], changed, binding['unit_id'])
        self.fixture.write_packet()
        code, output = self.invoke_catalog()
        self.assertEqual((code, self.fixture.refreshes, self.fixture.starts), (1, 0, 0), output)
        self.assertIn('profile_table_authority', output)

    def test_refreshed_runtime_change_denies_before_start(self):
        def change(target):
            manifest = json.loads((target/'manifest.json').read_text())
            manifest['runtime_id'] = 'other-runtime'
            (target/'manifest.json').write_text(json.dumps(manifest))
        self.fixture.change_at_refresh = change
        code, output = self.invoke_catalog()
        self.assertEqual((code, self.fixture.refreshes, self.fixture.starts), (1, 1, 0), output)

    def test_catalog_unknown_start_never_retries(self):
        self.fixture.timeout_start = True
        code, output = self.invoke_catalog()
        self.assertEqual((code, self.fixture.starts), (1, 1), output)
        self.assertEqual(json.loads((self.fixture.inventory.root/'result.json').read_text())['launch_state'], 'unknown')
        code, output = self.invoke_catalog()
        self.assertEqual((code, self.fixture.starts, self.fixture.refreshes), (1, 1, 1), output)

    def test_explicit_269_catalog_keeps_existing_task_and_measurement_checks(self):
        self.exercise_explicit_catalog(reuse=False)

    def test_explicit_269_prepared_catalog_reuses_later_observation_after_300_seconds(self):
        self.exercise_explicit_catalog(reuse=True)

    def exercise_explicit_catalog(self, *, reuse):
        import measurement_lifecycle as lifecycle
        import semantic_settings
        from test_measurement_lifecycle import LifecycleTests

        fixture = LifecycleTests()
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        fixture.use_sqlite_host('1.4.269')
        actor = 'worker'
        task_id = 'task-worker'
        prior_actor = 'reviewer'
        prior_task = 'task-reviewer'
        task = fixture.record['tasks'][0]
        task.update(id=task_id, current_dispatch='planned:'+task_id,
                    execution={'actor': actor, 'state': 'unknown', 'result': None},
                    technical=None, parent_integration=None)
        specs = {task_id: fixture.spec(actor)}
        if reuse:
            fixture.record['tasks'].append({**copy.deepcopy(task), 'id': prior_task,
                'current_dispatch': 'planned:'+prior_task,
                'execution': {**task['execution'], 'actor': prior_actor}})
            specs[prior_task] = fixture.spec(prior_actor)
        fixture.save()
        state = fixture.base/'fake-state.json'
        state.write_text(json.dumps({**json.loads(state.read_bytes()),
            'specs': specs, 'planned_task': task_id}))

        # The measurement fixture only needs a minimal schema. Give the same
        # synthetic DB the full semantic settings schema for both consumers.
        with closing(sqlite3.connect(fixture.profile_db)) as conn, conn:
            settings = conn.execute("SELECT payload FROM profile_state_documents WHERE domain='settings'").fetchone()[0]
            conn.execute('DROP TABLE profile_state_documents')
            conn.execute('CREATE TABLE profile_state_documents (domain TEXT PRIMARY KEY NOT NULL, '
                         'payload TEXT NOT NULL, domain_version INTEGER NOT NULL, revision INTEGER NOT NULL, '
                         'updated_at INTEGER NOT NULL, content_hash TEXT NOT NULL)')
            conn.execute("INSERT INTO profile_state_documents VALUES ('settings', ?, 1, 1, 1, 'fixture')", (settings,))
        (fixture.base/'orca-profile-index.json').write_text('{"schemaVersion":1,"activeProfileId":"local-default"}')
        app = fixture.base/'Orca.app'
        cli = app/'Contents/Resources/bin/orca'
        cli.parent.mkdir(parents=True)
        cli.touch(mode=0o700)
        initial = fixture.base/'catalog-original'
        initial.mkdir()
        catalog = CatalogFixture(initial, datetime.now(timezone.utc))
        for response in (catalog.status, catalog.response):
            response['_meta']['runtimeId'] = 'runtime-fixture'
        catalog.manifest['runtime_id'] = catalog.status['result']['runtimeId'] = 'runtime-fixture'
        packet = fixture.packets[actor]
        inventory = packet['evidence']['inventory']
        artifact = fixture.base/'prior-report.md'
        artifact.write_text('synthetic prerequisite output\n')
        profile = packet['profile_binding']['profile']
        profile['units'].insert(0, {**copy.deepcopy(profile['units'][0]), 'id': prior_task})
        profile['units'][1]['depends_on'] = [prior_task]
        packet['profile_binding'] = record_check.make_profile_binding(profile, packet['profile_binding']['table'], task_id)
        packet['binding'].update(task_deps=[prior_task], task_artifacts={prior_task: str(artifact)})
        catalog.response['result']['models'] = [
            {'id': row['slug'], 'efforts': [{'value': level['effort']} for level in row['supported_reasoning_levels']]}
            for row in inventory['host_models']]
        availability = {row['id']: [level['value'] for level in row['efforts']]
                        for row in catalog.response['result']['models']}
        if reuse:
            packet['profile_binding'] = record_check.make_profile_binding(
                profile, packet['profile_binding']['table'], task_id, codex_availability=availability)
        # The provider fetch predates the still-fresh collector receipt.
        provider_age = 50 if reuse else 250
        catalog.response['result']['fetchedAt'] = (catalog.now - timedelta(seconds=provider_age)).timestamp() * 1000
        catalog.bind_explicit_host(app, fixture.base)

        fixture.env['ORCA_USER_DATA_PATH'] = str(fixture.base)
        fixture.env['ORCA_CLI_COMMAND'] = str(cli)
        with patch.dict(os.environ, fixture.env, clear=True):
            rows = semantic_settings.prepare(fixture.profile_db, catalog.worktree, app_version='1.4.269',
                                             user_data=fixture.base)
            config_hash = company_config.resolve()['configuration_sha256']
        inventory.update(source='orca_model_catalog', file=str(initial/'manifest.json'), sha256=catalog.digest)
        packet['binding']['host_catalog'] = {'worktree': catalog.worktree, 'runtime_id': 'runtime-fixture',
                                             'configuration_sha256': config_hash, 'observed_files': rows}
        decision = fixture.base/'decision-worker.json'
        decision.write_text(json.dumps(packet))
        next(row for row in fixture.plan['attempts'] if row['id'] == actor)['decision_sha256'] = (
            hashlib.sha256(decision.read_bytes()).hexdigest())
        plan_path = fixture.base/'plan.json'
        original_paths = [decision, fixture.record_path, fixture.root/'prepare.json',
                          initial/'manifest.json', initial/'response-1.json', initial/'status.json']
        if reuse:
            prior_packet = fixture.packets[prior_actor]
            prior_packet['evidence']['inventory'] = copy.deepcopy(inventory)
            prior_packet['binding']['host_catalog'] = packet['binding']['host_catalog']
            prior_binding = prior_packet['profile_binding']
            prior_packet['profile_binding'] = record_check.make_profile_binding(
                prior_binding['profile'], prior_binding['table'], prior_task, codex_availability=availability)
            prior_decision = fixture.base/('decision-'+prior_actor+'.json')
            prior_decision.write_text(json.dumps(prior_packet))
            next(row for row in fixture.plan['attempts'] if row['id'] == prior_actor)['decision_sha256'] = (
                hashlib.sha256(prior_decision.read_bytes()).hexdigest())
            original_paths.append(prior_decision)
            provider_observed = catalog.response['result']['fetchedAt']
            catalog.response['result']['fetchedAt'] = (catalog.now - timedelta(seconds=301)).timestamp() * 1000
            catalog.save()
            fixture.plan['host_catalog'] = {'manifest': inventory['file'], 'sha256': catalog.digest,
                                            'context': packet['binding']['host_catalog']}
            plan_path.write_text(json.dumps(fixture.plan))
            denied = fixture.lifecycle('prepare', ['--plan', str(plan_path), '--ledger', str(fixture.root)], expected=1)
            self.assertIn('stale or future host catalog', denied['error'])
            self.assertFalse(fixture.root.exists())
            catalog.response['result']['fetchedAt'] = provider_observed
            catalog.save()
            fixture.plan['host_catalog']['sha256'] = catalog.digest
        plan_path.write_text(json.dumps(fixture.plan))
        fixture.prepare()
        prepared_at = datetime.fromisoformat(json.loads((fixture.root/'prepare.json').read_bytes())['created_at'])
        original_inputs = {path: path.read_bytes() for path in original_paths}
        (fixture.base/'models_cache.json').write_text('{unrelated malformed global cache churn')

        run = subprocess.run
        commands = []
        wrong_task_runtime = False
        prior_status = 'completed'
        prior_dispatch_id, prior_handle = 'dispatch-'+prior_actor, 'term_'+prior_actor
        report = {'provenance': 'worker_report', 'outcome': 'succeeded', 'reportPath': str(artifact),
                  'messageId': 'msg-prior', 'reportedBy': prior_handle}
        mail = {'type': 'worker_done', 'id': 'msg-prior', 'from_handle': prior_handle,
                'to_handle': 'run:goal-1', 'run_id': 'goal-1', 'payload': json.dumps({
                    'taskId': prior_task, 'dispatchId': prior_dispatch_id, 'outcome': 'succeeded',
                    'reportPath': str(artifact)})}
        prior_dispatch = {'id': prior_dispatch_id, 'task_id': prior_task, 'run_id': 'goal-1',
                          'status': 'completed', 'assignee_handle': prior_handle}
        hook_trust = fixture.base/'codex-hook-trust.json'

        def host(argv, **kwargs):
            commands.append(argv)
            if argv[0] == '/usr/bin/codesign':
                self.assertEqual(argv[-1], str(app))
                return SimpleNamespace(returncode=0)
            if argv[0] == 'node':
                self.assertEqual(argv[3:], [catalog.worktree, str(app), str(fixture.base)])
                if not reuse and case != 'stale-current-provider':
                    shutil.copytree(initial, argv[2])
                    return SimpleNamespace(returncode=0)
                target = Path(argv[2])
                target.mkdir()
                observed = copy.deepcopy(catalog)
                observed.root = target
                for item in observed.manifest['receipts']:
                    item.update(started_at=checked_at.isoformat(), received_at=checked_at.isoformat())
                observed.status['id'] += '-recheck'
                observed.response['id'] += '-recheck'
                if reuse:
                    observed.response['result']['fetchedAt'] = provider_observed + 35_068
                if case == 'changed-listing':
                    observed.response['result']['models'].append({'id': 'other', 'efforts': [{'value': 'low'}]})
                if case == 'changed-catalog-host':
                    observed.status['result']['hostDescriptor']['installationId'] += '-other'
                if case == 'regressed-provider':
                    observed.response['result']['fetchedAt'] = provider_observed - 1000
                if case == 'future-provider':
                    observed.response['result']['fetchedAt'] = (checked_at + timedelta(seconds=1)).timestamp() * 1000
                if case == 'malformed-provider':
                    observed.response['result']['fetchedAt'] = 'malformed'
                if case == 'stale-current-provider':
                    observed.response['result']['fetchedAt'] -= 51_000
                if case in ('stale-recheck', 'preparation-predated'):
                    for item in observed.manifest['receipts']:
                        item.update(started_at=catalog.now.isoformat(), received_at=catalog.now.isoformat())
                observed.save()
                return SimpleNamespace(returncode=0)
            self.assertEqual(argv[0], str(cli))
            if argv[2:3] in (['inbox'], ['dispatch-show']):
                if argv[2] == 'inbox' and case == 'expired-catalog':
                    catalog_clock.now.return_value = catalog.now + timedelta(seconds=51)
                if argv[2] == 'inbox' and case == 'expired-recheck-after-prerequisite':
                    launch_clock.now.return_value = checked_at + timedelta(seconds=301)
                if argv[2] == 'inbox' and case == 'changed-hook-trust':
                    hook_trust.write_text('{"synthetic":true}\n')
                result = {'messages': [mail]} if argv[2] == 'inbox' else {'dispatch': prior_dispatch}
                return SimpleNamespace(returncode=0, stderr='', stdout=json.dumps({
                    'ok': True, '_meta': {'runtimeId': 'runtime-fixture'}, 'result': result}))
            result = run([str(fixture.exe), *argv[1:]], **kwargs)
            output = json.loads(result.stdout)
            if argv[2:3] == ['task-list']:
                tasks = output['result']['tasks']
                tasks[0]['deps'] = json.dumps([prior_task])
                predecessor = {'id': prior_task, 'run_id': 'goal-1',
                               'status': prior_status, 'deps': '[]', 'result': json.dumps(report)}
                if reuse:
                    tasks[1].update(predecessor)
                else:
                    tasks.append(predecessor)
                    output['result']['count'] += 1
            runtime_id = 'other' if argv[2:3] == ['task-list'] and wrong_task_runtime else 'runtime-fixture'
            output['_meta'] = {'runtimeId': runtime_id}
            result.stdout = json.dumps(output)
            return result

        staged = fixture.scripts.parent/'assets'/lifecycle.SQLITE_HOSTS['1.4.269'].name
        cases = ['wrong-profile', 'wrong-cli', 'wrong-task-runtime', 'unsettled-prerequisite',
                 'changed-hook-trust']
        cases += (['wrong-run', 'wrong-worktree', 'changed-scope', 'changed-decision', 'changed-listing', 'changed-catalog-host',
                   'regressed-provider', 'future-provider', 'malformed-provider', 'preparation-predated',
                   'stale-recheck', 'expired-recheck-after-prerequisite', 'exact']
                  if reuse else ['stale-current-provider', 'expired-catalog', 'exact'])
        if reuse:
            cases.insert(0, 'predecessor')
        for case in cases:
            with self.subTest(case=case), patch.dict(os.environ, fixture.env, clear=True), \
                    patch.dict(lifecycle.SQLITE_HOSTS, {'1.4.269': staged}), \
                    patch('host_model_catalog.datetime', wraps=datetime) as catalog_clock, \
                    patch('routing_launch.datetime', wraps=datetime) as launch_clock, \
                    patch('routing_launch.subprocess.run', side_effect=host), redirect_stdout(StringIO()) as output:
                early = case in ('predecessor', 'preparation-predated')
                checked_at = prepared_at + timedelta(seconds=1 if early else 301) if reuse else catalog.now
                catalog_clock.now.return_value = launch_clock.now.return_value = checked_at
                hook_trust.unlink(missing_ok=True)
                launch_actor = prior_actor if case == 'predecessor' else actor
                args = fixture.launch_args(launch_actor, '-'+case)
                spec = args.index('--spec')
                args[spec:spec+2] = ['--task', 'task-'+launch_actor]
                args[args.index('--orca')+1] = str(cli)
                args[args.index('--worktree')+1] = catalog.worktree
                wrong_task_runtime = case == 'wrong-task-runtime'
                prior_status = 'ready' if case in ('predecessor', 'unsettled-prerequisite') else 'completed'
                commands.clear()
                if case == 'wrong-profile':
                    os.environ['ORCA_USER_DATA_PATH'] = str(fixture.base/'other')
                if case == 'wrong-cli':
                    os.environ['ORCA_CLI_COMMAND'] = str(fixture.exe)
                if case == 'wrong-run':
                    args[args.index('--run')+1] = 'other-run'
                if case == 'wrong-worktree':
                    args[args.index('--worktree')+1] = catalog.worktree + '-other'
                if case == 'changed-decision':
                    decision.write_bytes(original_inputs[decision] + b' ')
                if case == 'changed-scope':
                    decision.write_text(json.dumps({**packet, 'binding': {**packet['binding'], 'scope': 'other'}}))
                allowed = case in ('predecessor', 'exact')
                code = routing_launch.main(args)
                if case in ('changed-decision', 'changed-scope'):
                    decision.write_bytes(original_inputs[decision])
                self.assertEqual(code, 0 if allowed else 1, output.getvalue())
                start_count = sum(argv[2:3] == ['worker-start'] for argv in commands)
                self.assertEqual(start_count, int(allowed))
                if case in ('wrong-profile', 'wrong-cli'):
                    self.assertEqual(commands, [])
                if not allowed:
                    history = [e['kind'] for e in lifecycle.events(fixture.root)]
                    self.assertEqual(history, ['pending', 'binding', 'closed'] if reuse else [])
                    self.assertFalse(Path(args[args.index('--receipt')+1]).exists())
                if case in ('expired-catalog', 'changed-hook-trust', 'expired-recheck-after-prerequisite'):
                    self.assertEqual([argv[2] for argv in commands if argv[1:2] == ['orchestration']],
                                     ['task-list', 'inbox', 'dispatch-show'])
                    denial = json.loads(output.getvalue())
                    self.assertEqual(denial['error'], 'explicit catalog binding changed before start')
                    reason = {'expired-catalog': 'stale or future host catalog',
                              'changed-hook-trust': 'config/auth policy changed',
                              'expired-recheck-after-prerequisite': 'stale or future catalog receipt'}
                    self.assertIn(reason[case], denial['detail'])
                reasons = {'changed-decision': 'catalog_preparation_invalid',
                           'changed-scope': 'catalog Run/scope differs',
                           'wrong-worktree': 'launch worktree differs from catalog',
                           'changed-listing': 'catalog selection or context changed',
                           'changed-catalog-host': 'catalog selection or context changed',
                           'regressed-provider': 'host catalog fetchedAt regressed since preparation',
                           'future-provider': 'stale or future host catalog',
                           'malformed-provider': 'missing host fetchedAt',
                           'preparation-predated': 'catalog receipt predates preparation',
                           'stale-current-provider': 'stale or future host catalog',
                           'stale-recheck': 'stale or future catalog receipt',
                           'wrong-run': '--run differs from enrollment'}
                if case in reasons:
                    self.assertIn(reasons[case], output.getvalue())
            if case == 'predecessor':
                fixture.close(prior_actor)
        self.assertEqual((fixture.base/'starts').read_text().splitlines(), [prior_actor, actor] if reuse else [actor])
        start_events = ['pending', 'binding']
        self.assertEqual([event['kind'] for event in lifecycle.events(fixture.root)],
                         start_events + ['closed'] + start_events if reuse else start_events)
        receipt = json.loads((fixture.base/'receipt-worker-exact').read_bytes())['receipt']
        self.assertEqual(receipt['task_deps'], [prior_task])
        self.assertEqual(receipt['task_artifacts'][prior_task]['sha256'],
                         hashlib.sha256(artifact.read_bytes()).hexdigest())
        self.assertEqual(receipt['host_catalog']['prepared_manifest_sha256'], catalog.digest)
        refresh = receipt['host_catalog']
        self.assertEqual({path: path.read_bytes() for path in original_inputs}, original_inputs)
        if reuse:
            anchor = receipt['host_catalog_preparation']
            self.assertEqual(anchor['run'], 'goal-1')
            self.assertEqual(anchor['prepare_sha256'], fixture.record['measurement']['prepare_sha256'])
            self.assertEqual(datetime.fromisoformat(anchor['prepared_at']), prepared_at)
            observed_at = datetime.fromisoformat(refresh['observed_at'])
            self.assertGreater((observed_at - prepared_at).total_seconds(), 300)
            self.assertNotEqual(refresh['refreshed_manifest_sha256'], catalog.digest)
            refresh_dir = Path(refresh['refreshed_directory'])
            prior_refresh_dir = fixture.base/('result-'+prior_actor+'-predecessor.catalog-refresh')
            first_seen, later_seen = [json.loads((path/'response-1.json').read_bytes())['result']
                                      for path in (prior_refresh_dir, refresh_dir)]
            self.assertEqual(first_seen, later_seen)
            self.assertGreater(later_seen['fetchedAt'], provider_observed)
            self.assertGreater(observed_at.timestamp() - later_seen['fetchedAt'] / 1000, 300)
            self.assertEqual(later_seen, {**catalog.response['result'], 'fetchedAt': provider_observed + 35_068})
            self.assertEqual(receipt['price_selection']['status'], 'selected')
            import record_integrity
            for planned, name in ((prior_packet, 'receipt-'+prior_actor+'-predecessor'),
                                  (packet, 'receipt-worker-exact')):
                recorded = {**planned, 'receipt_evidence': 'preflight'}
                raw_receipt = fixture.base/name
                evidence = {**planned['evidence'], 'preflight': {
                    'file': str(raw_receipt), 'sha256': hashlib.sha256(raw_receipt.read_bytes()).hexdigest()}}
                self.assertEqual(record_integrity.historical_catalog(recorded, evidence, fixture.base, fixture.record),
                                 catalog.now.isoformat())
            with patch.dict(os.environ, fixture.env, clear=True), \
                    patch('host_model_catalog.datetime', wraps=datetime) as clock, redirect_stdout(StringIO()) as output:
                clock.now.return_value = checked_at
                self.assertEqual(record_check.main(['routing-check', str(decision), '--record',
                                                    str(fixture.record_path), '--json']), 0, output.getvalue())
                self.assertEqual(record_check.main(['routing-check', str(decision), '--json']), 1, output.getvalue())
                self.assertIn('stale or future catalog receipt', output.getvalue())
        else:
            self.assertEqual(refresh['refreshed_manifest_sha256'], catalog.digest)
