"""Owned synthetic fixtures; import creates no resources or production imports.

Builders return fresh data. Contexts own every directory, environment patch and
SQLite connection, including when preparation or a test raises. Callers inject
production entrypoints explicitly; this module never launches a real host.
"""
import contextlib
import copy
from datetime import datetime, timezone, timedelta
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
from types import SimpleNamespace
from typing import Callable
from unittest.mock import patch

PACKAGE = Path(__file__).resolve().parents[1]


def routing_packet(package=PACKAGE):
    """Build the bounded, two-candidate selector fixture without running policy."""
    candidates = [dict(route='codex', family=family, model=model, effort='low',
        supported=True, authenticated=True, tools='supported', billing='subscription',
        runtime_evidence='runtime', quality='adequate', quality_evidence='quality',
        usage_estimate=None) for family, model in
        [('terra', 'gpt-6.1-terra'), ('sol', 'gpt-6.1-sol')]]
    selection = {'version': 1, 'task': {'actor': 'worker', 'capability': 'coding',
        'complexity': 'bounded', 'coupling': 'local', 'decomposable': False,
        'stage': 'execution', 'uncertainty': 'none', 'evidence': 'semantics'},
        'cost_basis': 'benchmark_prior', 'scope_api_authorized': False,
        'candidates': candidates}
    refs = {key: {'ref': 'synthetic://' + key, 'sha256': None, 'kind': 'synthetic'}
            for key in ('runtime', 'quality', 'semantics', 'estimate')}
    routes = json.loads((package / 'assets/routing-cases.json').read_text())
    packet = copy.deepcopy(next(c['decision'] for c in routes['cases'] if not c['expected_errors']))
    selected = {key: candidates[0][key] for key in ('route', 'family', 'model', 'effort')}
    packet.update(trigger='initial', failure_class=None, prior=None, selected_reason='price_informed')
    packet['selected'] = {**selected, 'supported': True, 'evidence': 'runtime', 'reason_evidence': 'quality'}
    packet['alternatives'] = [{**selected, 'disposition': 'selected', 'reason': 'price_informed', 'evidence': 'runtime'}]
    packet['constraints']['quality'] = 'met'
    packet['evidence'].update(refs)
    packet['price_selection'] = selection
    selection['inventory_evidence'] = 'inventory'
    packet['evidence']['inventory'] = {'ref': 'synthetic://inventory', 'sha256': None, 'kind': 'synthetic',
        'candidate_inventory': [{k: row[k] for k in ('route', 'family', 'model', 'effort')} for row in candidates],
        'host_models': [{'slug': row['model'], 'supported_reasoning_levels': [{'effort': row['effort']}]} for row in candidates]}
    return packet


@contextlib.contextmanager
def inventory_fixture(package=PACKAGE):
    """Own mutable-cache files and launch-policy patches until context exit."""
    with contextlib.ExitStack() as stack:
        from storage_test_support import enrolled_run, flags
        base = Path(stack.enter_context(tempfile.TemporaryDirectory()))
        root = enrolled_run(base, paths=('models_cache.json', 'inventory-before.json', 'decision.json', 'user.md'))
        packet = routing_packet(package)
        packet['binding'].update(task='new', attempt='planned:new', planned=True,
            spec_sha256=hashlib.sha256(b'bounded test').hexdigest())
        from record_check import make_profile_binding
        profile = json.loads((package / 'assets/worker-profile-example.json').read_text())
        profile['units'][0]['id'] = 'new'
        table = json.loads((package / 'assets/worker-routing-table.json').read_text())
        packet['profile_binding'] = make_profile_binding(profile, table, 'new')
        packet['label'] = 'real'
        for item in packet['evidence'].values():
            if item['kind'] == 'synthetic':
                item['kind'] = 'host'
        cache = root / 'models_cache.json'
        contents = {'models': packet['evidence']['inventory']['host_models'],
                    'fetched_at': '2025-01-01T00:00:00Z',
                    'etag': 'same', 'client_version': 'fixture', 'identity': 'fixture'}
        cache.write_text(json.dumps(contents))
        snapshot = root / 'inventory-before.json'
        snapshot.write_bytes(cache.read_bytes())
        packet['evidence']['inventory'].update(file=str(cache),
            sha256=hashlib.sha256(cache.read_bytes()).hexdigest(),
            observed_at='2020-01-01T00:00:00Z', valid_until='2100-01-01T00:00:00Z')
        decision = root / 'decision.json'
        decision.write_text(json.dumps(packet))
        record = json.loads((package / 'assets/record-cases.json').read_text())['cases'][0]['record']
        (root / 'record.json').write_text(json.dumps(record))
        config = root / 'user.md'
        config.write_text('---\nschema_version: 1\npreset: single\nservices: ["codex"]\napi_paid: false\n---\n')
        stack.enter_context(patch.dict(os.environ, {'HOME': str(root), 'CODEX_HOME': str(root),
                                                   'AGENT_COMPANY_CONFIG': str(config)}))
        stack.enter_context(patch('record_check.canonical_home', return_value=root))
        stack.enter_context(patch('routing_launch.shutil.which', return_value='/fake/orca'))
        args = [*flags(root), '--orca', '/fake/orca', '--decision', str(decision),
                '--record', str(root/'record.json'), '--receipt', str(root/'preflight.json'),
                '--result', str(root/'result.json'), '--from', 'fake-sender',
                '--spec', 'bounded test', '--worktree', 'current']
        fake = SimpleNamespace(returncode=0, stderr='', stdout=json.dumps({'ok': True,
            'result': {'taskId': 'fake-task', 'dispatchId': 'fake-dispatch', 'launch': {'effective': {
                'agent': 'codex', 'model': packet['selected']['model'],
                'effort': packet['selected']['effort']}}}}))
        yield SimpleNamespace(root=root, packet=packet, cache=cache, contents=contents,
                              snapshot=snapshot, decision=decision, args=args, fake=fake)


class CatalogFixture:
    """Mutable synthetic receipt data with explicit writes, no validator import."""
    def __init__(self, root, now):
        self.root = root
        self.now = now
        self.worktree = 'id:fixture-repo::/fixture/workspace'
        self.status = {'id': 'fixture-status', 'ok': True, '_meta': {'runtimeId': 'fixture-runtime'},
                       'result': {'runtimeId': 'fixture-runtime', 'appVersion': '1.4.245',
                                  'capabilities': ['agent-session.coherent-model-catalog.v1']}}
        self.response = {'id': 'fixture-catalog', 'ok': True, '_meta': {'runtimeId': 'fixture-runtime'},
                         'result': {'origin': 'probe', 'fetchedAt': now.timestamp() * 1000,
                                    'modelsDifferByWorkspace': True,
                                    'models': [{'id': 'fixture-model', 'efforts': [{'value': 'low'}]}]}}
        self.manifest = {'format': 'company-host-catalog-metadata/v1', 'runtime_id': 'fixture-runtime',
                         'app_version': '1.4.245', 'worktree': self.worktree, 'receipts': []}
        for name, method, params in (
            ('status.json', 'status.get', {}),
            ('response-1.json', 'agentSession.modelCatalog', {'agent': 'codex', 'worktree': self.worktree})):
            self.manifest['receipts'].append({'file': name, 'method': method, 'params': params,
                'started_at': now.isoformat(), 'received_at': now.isoformat()})

    def use_saved_catalog(self):
        self.manifest['app_version'] = self.status['result']['appVersion'] = '1.4.268'
        self.status['result']['capabilities'] += [
            'agent-session.model-catalog.model-efforts.v1',
            'agent-session.model-catalog.saved-only.v1',
        ]
        self.manifest['receipts'][1]['params']['savedOnly'] = True
        self.response['result']['listingNamesConfiguredModel'] = True
        self.save()

    def bind_explicit_host(self, app, user_data):
        self.use_saved_catalog()
        self.manifest['app_version'] = self.status['result']['appVersion'] = '1.4.269'
        installation_id = 'fixture-installation'
        self.status['result'].update(graphStatus='ready', hostDescriptor={'installationId': installation_id})
        seal = app / 'Contents/_CodeSignature/CodeResources'
        seal.parent.mkdir(parents=True)
        seal.write_bytes(b'synthetic resource seal')
        user_data.mkdir(parents=True, exist_ok=True)
        (user_data/'host-installation.json').write_text(json.dumps({'installationId': installation_id}))
        (user_data/'orca-runtime.json').write_text(json.dumps({'runtimeId': self.manifest['runtime_id']}))
        self.manifest['host'] = {'app': str(app), 'user_data': str(user_data),
                                 'code_resources_sha256': hashlib.sha256(seal.read_bytes()).hexdigest()}
        self.save()

    def save(self):
        for receipt, response in zip(self.manifest['receipts'], [self.status, self.response]):
            raw = json.dumps(response).encode()
            (self.root / receipt['file']).write_bytes(raw)
            receipt['sha256'] = hashlib.sha256(raw).hexdigest()
        raw = json.dumps(self.manifest).encode()
        (self.root / 'manifest.json').write_bytes(raw)
        self.digest = hashlib.sha256(raw).hexdigest()


@contextlib.contextmanager
def catalog_fixture(now=None):
    with tempfile.TemporaryDirectory() as temp:
        fixture = CatalogFixture(Path(temp), now if now is not None else datetime(2026, 1, 1, tzinfo=timezone.utc))
        fixture.save()
        yield fixture


class LaunchFixture:
    def __init__(self, inventory, catalog):
        self.inventory = inventory
        self.catalog = catalog
        self.observed = inventory.root / 'observed-config'
        self.starts = 0
        self.refreshes = 0
        self.change_at_refresh: Callable[[Path], object] | None = None
        self.timeout_start = False

    def write_packet(self):
        self.inventory.decision.write_text(json.dumps(self.inventory.packet))

    def invoke(self, main):
        """Execute an injected checked-launch consumer behind counted fake I/O."""
        output = io.StringIO()
        def host(command, **kwargs):
            if command[0] == 'node':
                self.refreshes += 1
                target = Path(command[2])
                shutil.copytree(self.catalog.root, target)
                if self.change_at_refresh:
                    self.change_at_refresh(target)
                return SimpleNamespace(returncode=0, stdout='', stderr='')
            self.starts += 1
            if self.timeout_start:
                raise subprocess.TimeoutExpired('FAKE host', 1)
            return self.inventory.fake
        with patch('routing_launch.shutil.which', return_value='/Applications/Orca.app/Contents/Resources/fake-orca'), \
             patch('routing_launch.subprocess.run', side_effect=host), contextlib.redirect_stdout(output):
            code = main(self.inventory.args)
        return code, output.getvalue()


def bind_history_run(fixture):
    """Bind a planned profile to a distinct fake host-issued Task and Dispatch."""
    inventory = fixture.inventory
    record_path = inventory.root / 'record.json'
    record = json.loads(record_path.read_text())
    run_id = record['goal']['id']
    record['run'] = run_id
    record_path.write_text(json.dumps(record))
    inventory.packet['binding']['run'] = run_id
    inventory.args += ['--run', run_id]
    response = json.loads(inventory.fake.stdout)
    response['result'].update(runId=run_id, taskId='task-1', dispatchId='dispatch-current')
    inventory.fake.stdout = json.dumps(response)
    fixture.write_packet()


@contextlib.contextmanager
def launch_fixture(configuration, package=PACKAGE):
    """Compose independently owned resources; resolve config only inside patches."""
    with inventory_fixture(package) as inventory, \
         catalog_fixture(datetime.now(timezone.utc) - timedelta(seconds=1)) as catalog:
        catalog.response['result']['models'] = [
            {'id': row['slug'], 'efforts': [{'value': x['effort']} for x in row['supported_reasoning_levels']]}
            for row in inventory.contents['models']]
        catalog.save()
        fixture = LaunchFixture(inventory, catalog)
        inventory.packet['evidence']['inventory'].update(source='orca_model_catalog',
            file=str(catalog.root/'manifest.json'), sha256=catalog.digest)
        fixture.observed.write_text('synthetic provider and auth policy')
        inventory.packet['binding']['host_catalog'] = {
            'runtime_id': 'fixture-runtime', 'worktree': catalog.worktree,
            'configuration_sha256': configuration()['configuration_sha256'],
            'observed_files': [{'role': role, 'path': str(fixture.observed),
                'sha256': hashlib.sha256(fixture.observed.read_bytes()).hexdigest()}
                for role in ('config', 'auth_policy')]}
        inventory.args[inventory.args.index('--worktree')+1] = catalog.worktree
        fixture.write_packet()
        yield fixture


@contextlib.contextmanager
def semantic_database(root, *, user_data=None):
    """Keep the WAL writer open through observation, then close before deletion."""
    home = root / 'home'
    with patch('semantic_settings.Path.home', return_value=home), contextlib.ExitStack() as stack:
        app = user_data if user_data is not None else home / 'Library/Application Support/Orca'
        database = app / 'profiles/local-default/profile-state.db'
        database.parent.mkdir(parents=True)
        (app / 'orca-profile-index.json').write_text(json.dumps({'schemaVersion': 1, 'activeProfileId': 'local-default'}))
        db = sqlite3.connect(database)
        stack.callback(db.close)
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA wal_autocheckpoint=0')
        db.execute('CREATE TABLE profile_state_documents (domain TEXT PRIMARY KEY NOT NULL, payload TEXT NOT NULL, domain_version INTEGER NOT NULL, revision INTEGER NOT NULL, updated_at INTEGER NOT NULL, content_hash TEXT NOT NULL)')
        value = {'agentCmdOverrides': {'codex': ''}, 'agentDefaultArgs': {'codex': ''},
                 'agentDefaultEnv': {'codex': {}}, 'activeCodexManagedAccountId': None,
                 'provider': 'subscription', 'agentPermissionDefault': 'restricted'}
        db.execute('INSERT INTO profile_state_documents VALUES (?,?,1,1,1,?)', ('settings', json.dumps(value), 'unused'))
        db.execute('INSERT INTO profile_state_documents VALUES (?,?,1,1,1,?)', ('ui', '{}', 'unused'))
        db.commit()
        yield SimpleNamespace(home=home, app=app, database=database, db=db, value=value)
