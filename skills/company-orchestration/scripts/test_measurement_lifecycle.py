#!/usr/bin/env python3
"""Offline v2 CLI integration. The executable, DB, hooks and traces are SYNTHETIC.
No test-only allow flag or patched production gate; never call the real host.
"""
import copy
from contextlib import closing

import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import unittest

import measurement_lifecycle as lifecycle
from record_check import check_record, make_profile_binding
import test_measurement_gate as measurement_fixture
import test_route_select as selection_fixture
from test_measurement_gate import trace, encode
from storage_test_support import enrolled_run, flags as enrollment_flags, enrollment_path
import tempfile

SCRIPTS = Path(__file__).resolve().parent

def prepared_profile(unit):
    profile = json.loads((SCRIPTS.parent/'assets/worker-profile-example.json').read_text())
    profile['units'][0]['id'] = unit
    table = json.loads((SCRIPTS.parent/'assets/worker-routing-table.json').read_text())
    return make_profile_binding(profile, table, unit)

def canary_trace(actor, executable, check, report):
    """Synthetic Codex functions.exec roundtrips, not live-provider evidence."""
    import shlex
    fixture = lifecycle.decode((SCRIPTS.parent/'assets/measurement-canary.json').read_bytes())
    answer = fixture['expected_outputs'][actor]
    body = fixture['prompts'][actor].split("and body '")[1].split("' Omit")[0]
    argv = [[executable, 'orchestration', 'check', '--terminal', 'term-'+actor, '--json'],
            [executable, 'orchestration', 'send', '--from', 'term-'+actor, '--type', 'worker_done',
             '--subject', answer, '--body', body, '--task-id', 'task-'+actor,
             '--dispatch-id', 'dispatch-'+actor, '--outcome', 'succeeded']]
    base = trace('session-'+actor, 'turn-'+actor, 'response-'+actor)
    rows = base[:2]
    for i in range(3):
        if i < 2:
            rows.append({'type':'response_item','payload':{'type':'custom_tool_call',
                'name':'exec','namespace':'functions','call_id':actor+'-call-'+str(i),
                'input':'text(await tools.exec_command('+json.dumps({'cmd':shlex.join(argv[i]),
                          'login':False,'yield_time_ms':30000})+'));'}})
        else:
            rows.append({'type':'response_item','payload':{'type':'message','role':'assistant',
                'status':'completed','phase':'final_answer',
                'content':[{'type':'output_text','text':answer}]}})
        usage = copy.deepcopy(base[2]); mirror = copy.deepcopy(base[3])
        usage['payload']['response_id'] += '-'+str(i)
        for field in ('turn_token_usage','thread_token_usage'):
            usage['payload'][field] = {k:v*(i+1) for k,v in usage['payload'][field].items()}
        mirror['payload']['info']['total_token_usage'] = usage['payload']['turn_token_usage']
        rows.extend([usage, mirror])
        if i < 2:
            rows.append({'type':'response_item','payload':{'type':'custom_tool_call_output',
                'call_id':actor+'-call-'+str(i),'output':json.dumps({'exit_code':0,
                  'output':json.dumps(check if i == 0 else report)})}})
    end = copy.deepcopy(base[-1]); end['payload']['last_agent_message'] = answer
    rows.append(end)
    return rows, argv


FAKE_HOST = r'''
import json, os, sqlite3, sys, time, hashlib
from pathlib import Path
sys.path.insert(0, SCRIPTS)
from test_measurement_gate import trace, encode
root = Path(__file__).parent
args = sys.argv[1:]
state_path = root / 'fake-state.json'
state = json.loads(state_path.read_text())
sqlite_host = (root/'use-268').exists()
def save(): state_path.write_text(json.dumps(state))
def arg(k): return args[args.index(k)+1]
def source(actor, complete=False):
    global state
    data = encode(trace('session-'+actor, 'turn-'+actor, 'response-'+actor)[:None if complete else 2])
    fixture = json.loads((Path(SCRIPTS).parent/'assets/measurement-canary.json').read_text())
    if complete and actor in fixture['prompts'] and state.get('specs', {}).get('task-'+actor) == fixture['prompts'][actor]:
        import subprocess
        from test_measurement_lifecycle import canary_trace
        receipts = root / ('report-'+actor+'.json')
        if not receipts.exists():
            _, commands = canary_trace(actor, str(root/'fake-orca'), {}, {})
            outputs = [json.loads(subprocess.run(cmd, check=True, capture_output=True, text=True).stdout)
                       for cmd in commands]
            receipts.write_text(json.dumps(outputs))
            state = json.loads(state_path.read_text())
        rows, _ = canary_trace(actor, str(root/'fake-orca'), *json.loads(receipts.read_text()))
        # Model has reported, but its final response/usage/native end can lag.
        lag = root/('lag-'+actor)
        if lag.exists() and int(lag.read_text()) > 0:
            lag.write_text(str(int(lag.read_text())-1))
            rows = rows[:-4]
        data = encode(rows)
    if sqlite_host and (root/'seed-hook').exists():
        from datetime import datetime, timezone
        rows = [json.loads(line) for line in data.splitlines()]
        marker = root / ('complete-'+actor)
        at = (datetime.fromtimestamp(marker.stat().st_mtime, timezone.utc) if marker.exists()
              else datetime.now(timezone.utc))
        for row in rows:
            row['timestamp'] = '2000-01-01T00:00:00Z' if (root/'stale-source').exists() else at.isoformat()
        data = encode(rows)
    custom = root / ('custom-source-'+actor)
    if complete and custom.exists(): data = custom.read_bytes()
    (root / ('trace-'+actor)).write_bytes(data)
def register(actor):
    dispatch = 'dispatch-'+actor
    row = {'id': dispatch, 'runId':'goal-1', 'taskId':arg('--task') if '--task' in args else 'task-'+actor,
           'assigneePaneKey':'pane-'+actor, 'processIncarnation':'process-'+actor, 'status':'running'}
    if sqlite_host:
        row['processIncarnation'] = 'pty-'+actor+':process-'+actor
    state['dispatches'][dispatch] = row
    state.setdefault('specs', {})[row['taskId']] = arg('--spec') if '--spec' in args else state['specs'][row['taskId']]
    with sqlite3.connect(root/('orchestration.db' if sqlite_host else 'host.db')) as db:
        db.execute('INSERT INTO dispatch_contexts (id,run_id,task_id,assignee_pane_key,process_incarnation,'
                   'launch_token_hash) VALUES (?,?,?,?,?,?)',
                   (dispatch, row['runId'], row['taskId'], row['assigneePaneKey'], row['processIncarnation'], hashlib.sha256(('launch-'+actor).encode()).hexdigest()))
    hooks = json.loads((root/'hooks.json').read_text())
    hooks['entries'].append({'paneKey':row['assigneePaneKey'], 'launchTokenHash':hashlib.sha256(('launch-'+actor).encode()).hexdigest(),
          'receivedAt': int(time.time()*1000),
          'providerSession':{'key':'session_id','id':'session-'+actor,'transcriptPath':str(root/('trace-'+actor))},
          'hostTurn':{'owner':'codex:session-'+actor, 'currentTurnKey':'turn:turn-'+actor}})
    (root/'hooks.json').write_text(json.dumps(hooks))
    if (root/'missing-hook').exists():
        hooks['entries'][-1].pop('launchTokenHash')
        (root/'hooks.json').write_text(json.dumps(hooks))
    if sqlite_host:
        entry = {**hooks['entries'][-1], 'source':'codex'}
        if (root/'seed-hook').exists():
            entry['hookEventName'] = 'SessionStart'
            entry['hostTurn']['currentTurnKey'] = 'seed'
        if (root/'wrong-hook-turn').exists(): entry['hostTurn']['currentTurnKey']='turn:wrong'
        if (root/'wrong-hook-provider').exists(): entry['source']='hermes'
        with sqlite3.connect(root/'agent-hooks/last-status.db') as db:
            db.execute('INSERT INTO rows VALUES (?, ?, ?)',
                       ('entry\0'+row['assigneePaneKey'], 2, json.dumps(entry)))
    source(actor)
    save()
    return dispatch
if args[0] == 'status':
    result = {'target':{'kind':'local'}, 'runtime':{'state':'ready','runtimeId':'runtime-fixture',
        'appVersion':'1.4.268' if sqlite_host else '1.4.245',
        'capabilities':['orchestration.contract.v1','orchestration.worker-stop-verdict.v1']}}
    if (root/'use-269').exists(): result['runtime']['appVersion']='1.4.269'
    if (root/'unknown-version').exists(): result['runtime']['appVersion']='1.4.270'
elif args[:3] == ['agent','hooks','status']:
    result = {'enabled':True,'settingsPath':str(root/('profiles/local-default/profile-state.db' if sqlite_host else 'host-settings.json')),
              'statuses':[{'agent':'codex','state':'installed','managedHooksPresent':True}]}
elif args[:2] == ['worktree', 'show'] and sqlite_host:
    result = {'worktree':{'hostId': 'ssh' if (root/'remote-worktree').exists() else 'local',
                          'isArchived':False, 'isBare':False}}
elif args[1] == 'worker-start':
    if '--task' in args:
        actor = arg('--task')[5:] + ('-retry' if '--retry-of' in args else '')
    else:
        spec = arg('--spec')
        fixture = json.loads((Path(SCRIPTS).parent/'assets/measurement-canary.json').read_text())
        actor = next((a for a,p in fixture['prompts'].items() if p == spec), spec.split(':',1)[0])
    ledger = root/'ledger'
    events = [json.loads(p.read_text()) for p in sorted(ledger.glob('event-*.json'))]
    assert any(e['kind']=='pending' and e['value']['attempt']==actor for e in events), 'NOT DURABLE BEFORE START'
    with (root/'starts').open('a') as stream: stream.write(actor+'\n')
    if (root/'crash-start').exists(): sys.exit(3)
    if (root/'slow-start').exists(): time.sleep(1)
    dispatch = register(actor)
    result = {'taskId':state['dispatches'][dispatch]['taskId'],'dispatchId':dispatch,'runId':'goal-1',
              'launch':{'effective':{'agent':'codex','model':arg('--model'),'effort':arg('--effort')}}}
    if sqlite_host:
        state.setdefault('effective', {})[dispatch] = result['launch']['effective']
        save()
        result['mode'] = {'mode':'terminal', 'preferred':'terminal'}
        result['prompt'] = {'provider':'codex', 'processIncarnation':'process-'+actor}
        handle = 'term_wrong' if (root/'wrong-handle').exists() else 'term_'+actor
        result['effects'] = [{'kind':'terminal', 'role':'agent', 'action':'created', 'id':handle}]
        if (root/'structured-start').exists(): result['mode']['mode']='structured'
        if (root/'duplicate-effect').exists(): result['effects'] *= 2
    if (root/'wrong-start').exists(): result['runId']='wrong-run'
    if (root/'fast-complete').exists(): source(actor, True)
    if (root/'auto-complete').exists(): (root/('complete-'+actor)).write_text('completed')
elif args[1] == 'worker-show':
    dispatch = arg('--dispatch')
    row = state['dispatches'][dispatch]
    actor = dispatch[len('dispatch-'):]
    if (root/('complete-'+actor)).exists():
        source(actor, True)
        row = state['dispatches'][dispatch]
        row['status'] = (root/('complete-'+actor)).read_text() or 'completed'
        save()
    result = {'dispatch':row,'worker':{'state':'stopped' if row['status']=='cancelled' else 'ready'},
              'observation':{'status':'exited' if row['status']=='cancelled' else 'live','exactWorker':True}}
    if sqlite_host:
        if '--full' not in args:
            result = {'dispatchId':dispatch, 'state':result['worker']['state'], 'liveness':result['observation']['status']}
        else:
            handle = 'term_'+actor
            row.update(assigneeHandle=handle, hostScope={'kind':'local','hostId':'local'})
            result['worker'].update(dispatchId=dispatch,runtimeEpoch='runtime-fixture',agentTerminalHandle=handle,
                startOptions={'agent':'codex','terminal':None,'mode':{'mode':'terminal','preferred':'terminal'}})
            result['worker']['startOptions']['launch'] = {'effective':state['effective'][dispatch]}
            result['terminal'] = {'handle':handle,'executionHostId':'local','agentIdentity':'codex',
                                  'ptyId':'pty-'+actor,'incarnationId':'process-'+actor}
            result['terminalResource'] = {'ownerDispatchId':dispatch,'originDispatchId':dispatch,
                                          'terminalHandle':handle,'ownershipState':'owned'}
            if (root/'wrong-worker-mode').exists():
                result['worker']['startOptions']['mode']['preferred']='structured'
            if (root/'wrong-process').exists(): row['processIncarnation']='unrelated'
elif args[1] == 'check':
    actor = arg('--terminal')[len('term-'):]
    assert args == ['orchestration','check','--terminal','term-'+actor,'--json']
    assert state['dispatches']['dispatch-'+actor]['status'] == 'running'
    state.setdefault('checked', []).append(actor); save()
    result = {'count':0,'messages':[]}
elif args[1] == 'send':
    actor = arg('--from')[len('term-'):]
    assert actor in state.get('checked', [])
    assert arg('--type') == 'worker_done' and arg('--outcome') == 'succeeded'
    assert arg('--task-id') == 'task-'+actor and arg('--dispatch-id') == 'dispatch-'+actor
    assert len(arg('--body').split('. ')) == 3
    assert set(args[2::2]) == {'--from','--type','--subject','--body','--task-id','--dispatch-id','--outcome'}
    row = state['dispatches']['dispatch-'+actor]
    assert row['status'] == 'running', 'duplicate or non-owned worker report'
    row['status'] = 'completed'
    state.setdefault('reports', []).append(actor); save()
    result = {'message':{'type':'worker_done','from_handle':'term-'+actor,
              'payload':json.dumps({'taskId':'task-'+actor,'dispatchId':'dispatch-'+actor,'outcome':'succeeded'})},
              'lifecycle':{'action':'completed','taskId':'task-'+actor,'dispatchId':'dispatch-'+actor}}
elif args[1] == 'task-list':
    result = {'runId':'goal-1','tasks':[{'id':tid,'run_id':'goal-1','parent_id':'parent-task',
               'spec':spec,'deps':'[]','status':'ready' if state.get('planned_task') == tid else 'failed'}
               for tid,spec in state['specs'].items()]}
    result['count'] = len(result['tasks'])
elif args[1] == 'dispatch-show':
    result = {'dispatch':next(d for d in state['dispatches'].values() if d['taskId']==arg('--task'))}
elif args[1] == 'worker-stop':
    dispatch=arg('--dispatch')
    if sqlite_host: assert '--full' in args
    with (root/'stops').open('a') as stream: stream.write(dispatch+'\n')
    if (root/'unknown-stop').exists():
        print(json.dumps({'ok':False,'result':{'dispatchId':dispatch,'state':'stop_unknown'}})); sys.exit(1)
    state['dispatches'][dispatch]['status']='cancelled'; save()
    result={'dispatchId':dispatch,'state':'stopped','processAction':'closed_agent_terminal'}
    if (root/'wrong-stop').exists(): result['dispatchId']='dispatch-unrelated'
    if (root/'helper-stop').exists(): result['helpers']=[{'outcome':'unconfirmed'}]
else:
    raise RuntimeError('unsupported fake host command '+str(args))
print(json.dumps({'ok':True,'result':result}))
'''


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.build_fixture()

    def build_fixture(self, owner='B'):
        self.scripts = SCRIPTS
        fixture = measurement_fixture.MeasurementGateTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = enrolled_run(Path(temporary.name), owner=owner, consumers=('measurement-v2',), paths=('plan', 'objective', 'criteria'))
        for name in ('plan', 'objective', 'criteria'):
            (self.base / name).write_bytes((fixture.base / name).read_bytes())
        self.record = fixture.record
        self.record['run'] = 'goal-1'
        self.record['measurement'].pop('participants')
        self.record['measurement']['version'] = 2
        self.record_path = self.base / 'record.json'
        self.root = self.base / 'ledger'
        self.exe = self.base / 'fake-orca'
        self.exe.write_text('#!' + sys.executable + '\nSCRIPTS = ' + repr(str(SCRIPTS)) + '\n' + FAKE_HOST)
        self.exe.chmod(0o700)
        self.env = dict(os.environ)
        self.env.update(CODEX_HOME=str(self.base), HOME=str(self.base/'home'), PYTHONDONTWRITEBYTECODE='1')
        config = self.base/'config.md'
        config.write_text('---\nschema_version: 1\npreset: single\nservices: ["codex"]\napi_paid: false\n---\n')
        self.env['AGENT_COMPANY_CONFIG'] = str(config)
        self.env.pop('AGENT_COMPANY_TASK_CONFIG', None)
        (self.base/'host-settings.json').write_text(json.dumps({'settings': {
            'experimentalNativeChat':False,'experimentalStructuredNativeChat':False,
            'openAgentTabsInChatByDefault':False,'agentStatusHooksEnabled':True,'tabAutoGenerateTitle':False}}))
        with closing(sqlite3.connect(self.base/'host.db')) as db:
            db.execute('CREATE TABLE dispatch_contexts (id, run_id, task_id, assignee_pane_key, process_incarnation, launch_token_hash)')
            db.execute('CREATE TABLE worker_dispatches (dispatch_id, runtime_epoch, agent_terminal_handle, state)')
            db.commit()
        self.probe_source = self.base/'trace-probe'
        self.probe_source.write_bytes(encode(trace('session-probe','turn-probe','response-probe')))
        import time
        self.hooks = {'version':2, 'entries':[{'paneKey':'pane-probe','launchTokenHash':'hash-probe','receivedAt':int(time.time()*1000),
                     'providerSession':{'key':'session_id','id':'session-probe','transcriptPath':str(self.probe_source)},
                     'hostTurn':{'owner':'codex:session-probe','currentTurnKey':'turn:turn-probe'}}]}
        (self.base/'hooks.json').write_text(json.dumps(self.hooks))
        state = {'dispatches':{}}  # Zero active/historical dispatch rows; sample is compatibility only.
        contract = lifecycle.decode(lifecycle.SOURCE_CONTRACT.read_bytes())
        (self.base/'host-source.js').write_text('\n'.join(s['text']+s['end'] for s in contract['sections']))
        (self.base/'fake-state.json').write_text(json.dumps(state))
        selection = selection_fixture.SelectionCLITests()
        selection.setUp()
        self.addCleanup(selection.doCleanups)
        self.actors = ['B','worker','reviewer','independent-reviewer']
        attempts = []
        self.packets = {}
        for actor in self.actors:
            packet = copy.deepcopy(selection.packet())
            packet['binding'].update(task='task-'+actor, attempt='planned:task-'+actor, planned=True,
                spec_sha256=lifecycle.digest(self.spec(actor).encode()), parent_task='parent-task', run='goal-1')
            packet['profile_binding'] = prepared_profile('task-'+actor)
            packet['label'] = 'real'  # Required by production launch gate; all data here remain test fixtures.
            for item in packet['evidence'].values():
                if item['kind'] == 'synthetic': item['kind'] = 'host'
            inventory = self.base/'models_cache.json'
            inventory.write_text(json.dumps({'models':packet['evidence']['inventory']['host_models']}))
            packet['evidence']['inventory'].update(file=inventory.name, sha256=lifecycle.digest(inventory.read_bytes()),
                observed_at='2020-01-01T00:00:00Z',valid_until='2100-01-01T00:00:00Z')
            path = self.base/('decision-'+actor+'.json')
            path.write_text(json.dumps(packet))
            self.packets[actor] = packet
            attempts.append({'id':actor,'actor':actor,'provider':'codex','decision_sha256':lifecycle.digest(path.read_bytes()),
                             'spec_sha256':packet['binding']['spec_sha256'],'ordinal':1,'retry_of':None})
        self.plan = {'adapter':lifecycle.ADAPTER, 'collector':{'database':str(self.base/'host.db'),'hooks':str(self.base/'hooks.json'),
            'host_source':str(self.base/'host-source.js'), 'sample_session':'session-probe','sample_turn':'turn-probe'},
            'attempts':attempts, 'limits':{'max_attempts':6,'concurrency':1,'paid_fallback':False,
                                         'max_raw_tokens':1000,'deadline_seconds':600}}
        (self.base/'plan.json').write_text(json.dumps(self.plan))
        self.save()

    def spec(self, actor):
        return actor + ': synthetic bounded sum 2+3; no tools, nested agents, network or private data'

    def save(self):
        self.record_path.write_text(json.dumps(self.record))

    def cli(self, script, args, expected=0):
        if script in ('measurement_lifecycle.py', 'measurement_canary.py'):
            args = [*args, *enrollment_flags(self.base)]
        proc = subprocess.run([sys.executable, '-B', str(self.scripts/script), *args],
                              env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, expected, proc.stdout+proc.stderr)
        self.assertNotIn('Traceback', proc.stderr)
        return json.loads(proc.stdout) if proc.stdout.strip() else {}

    def lifecycle(self, action, extra=(), expected=0):
        return self.cli('measurement_lifecycle.py', [action,'--record',str(self.record_path),'--orca',str(self.exe),*extra],expected)

    def prepare(self):
        result = self.lifecycle('prepare', ['--plan',str(self.base/'plan.json'),'--ledger',str(self.root)])
        self.record['measurement'].update(ledger='ledger',prepare_sha256=result['prepare_sha256'])
        self.save()
        return result

    def launch_args(self, actor, suffix=''):
        return [*enrollment_flags(self.base), '--orca',str(self.exe),'--record',str(self.record_path),
                '--decision',str(self.base/('decision-'+actor+'.json')), '--measurement-attempt',actor,
                '--receipt',str(self.base/('receipt-'+actor+suffix)), '--result',str(self.base/('result-'+actor+suffix)),
                '--from','synthetic-sender','--spec',self.spec(actor),'--worktree','current',
                '--parent','parent-task','--run','goal-1']

    def launch(self, actor, expected=0, suffix=''):
        return self.cli('routing_launch.py',self.launch_args(actor,suffix),expected)

    def close(self, actor, outcome='completed'):
        (self.base/('complete-'+actor)).write_text(outcome)
        return self.lifecycle('close',['--attempt',actor])

    def finish(self, settle_expected=0):
        self.prepare()
        for actor in self.actors:
            self.launch(actor)
            self.close(actor)
        result = self.lifecycle('settle', expected=settle_expected)
        self.record['measurement']['settlement_sha256'] = result['sha256']
        self.record['goal'].update(status='succeeded',assessment={'revision':'r1','scope':'approved-scope',
            'verdict':'succeeded','basis':'independent','actor':'independent-reviewer','evidence':'assessment'})
        task = self.record['tasks'][0]
        task.update(id='task-worker',current_dispatch='dispatch-worker')
        for item in (task['execution']['result'],task['technical'],task['parent_integration']):
            item.update(task='task-worker',dispatch='dispatch-worker')
        entries = []
        for key, value in result['receipt']['value']['responses'].items():
            entries.append({'provider':'codex','kind':'request','id':key.split('/')[-1], 'session':value['session'],
                'tokenizer':'unknown','input':10,'output':5,'cached_input':2,'reasoning':3,
                'cached_in_input':True,'reasoning_in_output':True,'evidence':'usage'})
        self.record['usage'] = {'coverage':'complete','expected':list(result['receipt']['value']['responses']),'entries':entries}
        self.save()
        return result

    def test_cli_prepare_checked_launch_settle_and_record(self):
        self.finish()
        checked = self.cli('record_check.py',['check',str(self.record_path),'--json'])
        self.assertTrue(checked['ok'])
        self.assertEqual(checked['usage']['total_raw_tokens'],60)
        self.assertEqual((self.base/'starts').read_text().splitlines(),self.actors)
        self.assertEqual(lifecycle.decode((self.root/'prepare.json').read_bytes())['future_provider_ids'],'unobserved')
        self.assertEqual([e['value']['status'] for e in lifecycle.events(self.root) if e['kind']=='binding'],['identity_observed']*4)

    def test_measured_existing_task_allows_only_timestamp_reprepare(self):
        actor = 'worker'
        task = self.record['tasks'][0]
        task.update(id='task-worker', current_dispatch='planned:task-worker',
                    execution={'actor': 'worker', 'state': 'unknown', 'result': None},
                    technical=None, parent_integration=None)
        self.save()
        state = self.base/'fake-state.json'
        state.write_text(json.dumps(dict(lifecycle.decode(state.read_bytes()),
            specs={'task-worker': self.spec(actor)}, planned_task='task-worker')))
        inventory = self.base/'models_cache.json'
        before = dict(lifecycle.decode(inventory.read_bytes()),
                      fetched_at='2021-01-01T00:00:00Z', client_version='same', identity='same')
        inventory.write_text(json.dumps(before))
        snapshot = self.base/'inventory-original.json'
        snapshot.write_bytes(inventory.read_bytes())
        decision = self.base/'decision-worker.json'
        packet = self.packets[actor]
        packet['evidence']['inventory']['sha256'] = lifecycle.digest(snapshot.read_bytes())
        decision.write_text(json.dumps(packet))
        pin = next(item for item in self.plan['attempts'] if item['id'] == actor)
        pin['decision_sha256'] = lifecycle.digest(decision.read_bytes())
        (self.base/'plan.json').write_text(json.dumps(self.plan))
        self.prepare()
        for changed in ('identity', 'client_version', None):
            after = dict(before, fetched_at='2022-01-01T00:00:00Z')
            if changed:
                after[changed] = 'changed'
            inventory.write_text(json.dumps(after))
            args = self.launch_args(actor, '-'+str(changed))
            args[args.index('--spec'):args.index('--spec')+2] = ['--task', 'task-worker']
            args.extend(('--reprepare-inventory', str(snapshot)))
            result = self.cli('routing_launch.py', args, expected=int(changed is not None))
            if changed:
                self.assertIn('material selection review required', result['detail'])
                self.assertEqual(lifecycle.events(self.root), [])
                self.assertFalse((self.base/'starts').exists())
        self.close(actor)
        events = lifecycle.events(self.root)
        pending, binding = (event['value'] for event in events[:2])
        self.assertEqual(pending['planned_decision_sha256'], pin['decision_sha256'])
        self.assertNotEqual(pending['effective_decision_sha256'], pin['decision_sha256'])
        self.assertEqual(pending['effective_decision_sha256'], binding['host_receipt']['decision_sha256'])
        self.assertEqual((self.base/'starts').read_text().splitlines(), [actor])

    def test_budget_exceeded_complete_accounting_non_success_and_idempotent(self):
        self.plan['limits']['max_raw_tokens'] = 50
        (self.base/'plan.json').write_text(json.dumps(self.plan))
        result = self.finish(settle_expected=1)
        self.assertEqual(result['accounting_status'], 'complete')
        self.assertEqual(result['policy'], {'verdict':'budget_exceeded', 'reasons':['budget_exceeded'],
                         'max_raw_tokens':50, 'success_eligible':False})
        # Successful record claims are refused even though all usage is present.
        self.assertFalse(check_record(self.record, self.base)['ok'])
        self.record = lifecycle.accounting_record(self.record, self.base, result['receipt'])
        self.save()
        checked = self.cli('record_check.py', ['check', str(self.record_path), '--json'])
        self.assertEqual(checked['usage']['total_raw_tokens'], 60)
        self.assertEqual(checked['measurement']['policy']['verdict'], 'budget_exceeded')
        self.assertEqual(self.record['goal']['status'], 'failed')
        before = {p.name:p.read_bytes() for p in self.root.glob('*') if p.is_file()}
        output = self.base/'final-record.json'
        for _ in range(2):
            self.assertEqual(self.lifecycle('finalize', ['--output-record', str(output)])['sha256'], result['sha256'])
            self.assertEqual(self.lifecycle('settle', expected=1)['sha256'], result['sha256'])
        self.assertEqual(before, {p.name:p.read_bytes() for p in self.root.glob('*') if p.is_file()})
        self.assertEqual(lifecycle.decode(output.read_bytes()), self.record)
        import run_completion
        with self.assertRaisesRegex(ValueError, 'success-only completion refused: budget_exceeded'):
            run_completion.validate_acceptance(self.record, self.record_path, {}, '')
        self.lifecycle('finalize', ['--output-record', str(self.record_path)], expected=1)

    def test_halted_complete_accounting_is_not_success(self):
        self.prepare()
        for actor in self.actors:
            self.launch(actor); self.close(actor)
        lifecycle.append(self.root, 'halt', {'reason':'synthetic final acceptance failure'})
        result = self.lifecycle('finalize')
        self.assertEqual(result['policy']['verdict'], 'halted')
        self.lifecycle('settle', expected=1)

    def test_finalization_receipt_and_source_tampering_rejected(self):
        result = self.finish()
        path = self.root/('event-%06d.json' % result['receipt']['sequence'])
        original = path.read_bytes()
        for change in ('policy', 'version', 'raw', 'responses'):
            event = lifecycle.decode(original)
            if change == 'policy': event['value']['policy']['success_eligible'] = False
            if change == 'version': event['value']['receipt_version'] = 99
            if change == 'raw': event['value']['raw_total'] = 0
            if change == 'responses': event['value']['responses'].pop(next(iter(event['value']['responses'])))
            path.write_bytes(lifecycle.encoded(event))
            self.lifecycle('finalize', expected=1)
        path.write_bytes(original)
        source = next(e['value']['source'] for e in lifecycle.events(self.root) if e['kind']=='closed')
        (self.root/source).write_bytes(b'forged\n')
        self.lifecycle('finalize', expected=1)

    def test_duplicate_terminal_and_missing_evidence_rejected(self):
        result = self.finish()
        with self.assertRaisesRegex(ValueError, 'accepted record freezes classification'):
            lifecycle.append(self.root, 'settlement', result['receipt']['value'])
        # The supported producer now refuses this earlier. Still feed exactly
        # the old duplicate-terminal negative bytes to the read-only judge.
        previous = result['receipt']
        forged = dict(version=lifecycle.VERSION, sequence=previous['sequence'] + 1,
            previous=lifecycle.digest(lifecycle.encoded(previous)), at=lifecycle.now(),
            kind='settlement', value=previous['value'])
        (self.root / ('event-%06d.json' % forged['sequence'])).write_bytes(lifecycle.encoded(forged))
        self.lifecycle('finalize', expected=1)
        self.assertFalse(check_record(self.record, self.base)['ok'])
        (self.root/('event-%06d.json' % (result['receipt']['sequence']+1))).unlink()
        source = next(e['value']['source'] for e in lifecycle.events(self.root) if e['kind']=='closed')
        (self.root/source).unlink()
        self.lifecycle('finalize', expected=1)

    def test_legacy_v2_receipt_remains_readable_without_rewrite(self):
        result = self.finish()
        event = result['receipt']
        event['value'] = {k:event['value'][k] for k in ('prepare_sha256','responses','raw_total')}
        path = self.root/('event-%06d.json' % event['sequence'])
        path.write_bytes(lifecycle.encoded(event))
        self.record['measurement']['settlement_sha256'] = lifecycle.digest(path.read_bytes())
        self.save()
        self.assertTrue(check_record(self.record, self.base)['ok'])
        self.assertEqual(self.lifecycle('finalize')['receipt'], event)
        self.assertEqual(path.read_bytes(), lifecycle.encoded(event))

    def test_unsupported_or_unproven_collector_denies_without_start(self):
        (self.base/'host-source.js').write_text('unsupported source contract')
        self.lifecycle('prepare',['--plan',str(self.base/'plan.json'),'--ledger',str(self.root)],1)
        self.assertFalse((self.base/'starts').exists())
        self.assertFalse(self.root.exists())

    def test_replay_with_different_result_path_is_rejected(self):
        self.prepare(); self.launch('B')
        self.launch('B',1,'-replay')
        self.assertEqual((self.base/'starts').read_text().splitlines(),['B'])

    def test_unknown_start_blocks_all_new_work(self):
        self.prepare(); (self.base/'crash-start').touch()
        self.launch('B',1)
        self.launch('B',1,'-again')
        self.launch('worker',1)
        self.lifecycle('bind',['--attempt','B'],1)
        self.assertEqual((self.base/'starts').read_text().splitlines(),['B'])

    def test_wrong_launch_run_never_binds(self):
        self.prepare(); (self.base/'wrong-start').touch()
        self.launch('B',1)
        self.assertFalse(any(e['kind']=='binding' for e in lifecycle.events(self.root)))

    def test_pending_coordinator_cannot_settle(self):
        self.prepare(); self.launch('B')
        self.lifecycle('settle',expected=1)
        self.record['goal']['status']='succeeded'
        checked = check_record(self.record,self.base)
        self.assertFalse(checked['ok']); self.assertIsNone(checked['usage']['total_raw_tokens'])

    def test_raw_missing_null_forgery_and_duplicate_rejected(self):
        self.finish()
        original = copy.deepcopy(self.record)
        for change in ('missing','null','forge','duplicate','expected_duplicate','wrong_session','wrong_task'):
            with self.subTest(change=change):
                self.record = copy.deepcopy(original)
                entries = self.record['usage']['entries']
                if change=='missing': entries.pop()
                if change=='null': entries[0]['input']=None
                if change=='forge': entries[0]['output']=999
                if change=='duplicate': entries.append(copy.deepcopy(entries[0]))
                if change=='expected_duplicate': self.record['usage']['expected'].append(self.record['usage']['expected'][0])
                if change=='wrong_session': entries[0]['session']='forged'
                if change=='wrong_task': self.record['tasks'][0]['current_dispatch']='other'
                checked = check_record(self.record,self.base)
                self.assertFalse(checked['ok']); self.assertIsNone(checked['usage']['total_raw_tokens'])

    def test_source_tamper_and_late_append(self):
        self.prepare(); self.launch('B')
        self.close('B')
        source = self.base/'trace-B'
        source.write_bytes(source.read_bytes()+encode([{'type':'event_msg','payload':{'type':'agent_message'}}]))
        self.assertIn('late source',self.lifecycle('settle',expected=1)['error'])
        first = next(e for e in lifecycle.events(self.root) if e['kind']=='binding')
        (self.root/first['value']['prefix']).write_bytes(b'forged\n')
        self.lifecycle('settle',expected=1)

    def test_fast_completed_source_binds_without_backdating(self):
        self.prepare(); (self.base/'fast-complete').touch()
        self.launch('B')
        binding = next(e for e in lifecycle.events(self.root) if e['kind']=='binding')
        self.assertEqual(binding['value']['status'],'usage_observed')
        self.close('B')

    def test_failed_and_cancelled_costs_retained(self):
        self.prepare()
        for i, actor in enumerate(self.actors):
            self.launch(actor)
            self.close(actor, ['failed','cancelled','completed','completed'][i])
        result = self.lifecycle('settle', expected=1)
        self.assertFalse(result['policy']['success_eligible'])
        self.assertEqual(result['policy']['verdict'], 'attempt_failed')
        self.assertEqual(self.lifecycle('finalize')['sha256'], result['sha256'])
        self.assertEqual(result['receipt']['value']['raw_total'],60)
        self.assertEqual(len(result['receipt']['value']['responses']),4)

    def test_missing_actor_and_mutated_goal_fail(self):
        self.prepare()
        for field in ('scope','revision'):
            record=copy.deepcopy(self.record); record['goal'][field]='changed'
            self.assertFalse(check_record(record,self.base)['ok'])
        record=copy.deepcopy(self.record); record['measurement']['expected_actors'].remove('reviewer')
        self.assertFalse(check_record(record,self.base)['ok'])

    def test_append_only_amendment_and_omission(self):
        self.prepare()
        attempt=copy.deepcopy(self.plan['attempts'][0]); attempt.update(id='extra',actor='new-reviewer')
        path=self.base/'amend.json'; path.write_text(json.dumps([attempt]))
        before=(self.root/'prepare.json').read_bytes()
        self.lifecycle('amend',['--plan',str(path)])
        self.assertEqual((self.root/'prepare.json').read_bytes(),before)
        self.assertEqual(len(lifecycle.prepared(self.record,self.base)[1]['attempts']),5)
        self.lifecycle('settle',expected=1)
        self.lifecycle('amend',['--plan',str(path)],1)

    def test_two_processes_cannot_reserve_same_attempt(self):
        self.prepare(); (self.base/'slow-start').touch()
        command=[sys.executable,'-B',str(SCRIPTS/'routing_launch.py')]
        first=subprocess.Popen(command+self.launch_args('B','-one'),env=self.env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        second=subprocess.Popen(command+self.launch_args('B','-two'),env=self.env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        first_out=first.communicate(timeout=30); second_out=second.communicate(timeout=30)
        self.assertEqual(sorted([first.returncode,second.returncode]),[0,1],str((first_out,second_out)))
        self.assertEqual((self.base/'starts').read_text().splitlines(),['B'])


    def test_saved_launch_reconciles_missing_hook_without_relaunch(self):
        self.prepare(); (self.base/'missing-hook').touch()
        self.launch('B',1)
        self.assertEqual(lifecycle.decode((self.base/'result-B').read_bytes())['launch_state'],'observed')
        hooks=json.loads((self.base/'hooks.json').read_text())
        hooks['entries'][-1]['launchTokenHash']=lifecycle.digest(b'launch-B')
        hooks['entries'][-1]['hostTurn']['currentTurnKey']='turn:wrong'
        (self.base/'hooks.json').write_text(json.dumps(hooks))
        self.lifecycle('bind',['--attempt','B'],1)
        hooks['entries'][-1]['hostTurn']['currentTurnKey']='turn:turn-B'
        (self.base/'hooks.json').write_text(json.dumps(hooks))
        self.lifecycle('bind',['--attempt','B'])
        self.lifecycle('bind',['--attempt','B'],1)
        self.assertEqual((self.base/'starts').read_text().splitlines(),['B'])

    def test_cumulative_append_counts_responses_not_mirrors(self):
        rows=trace('session-worker','turn-worker','response-worker')
        extra=copy.deepcopy(rows[2]); extra['payload']['response_id']='response-worker-2'
        for field in ('turn_token_usage','thread_token_usage'):
            extra['payload'][field]={k:v*2 for k,v in extra['payload'][field].items()}
        mirror=copy.deepcopy(rows[3])
        mirror['payload']['info']['total_token_usage']={k:v*2 for k,v in mirror['payload']['info']['total_token_usage'].items()}
        rows=rows[:4]+[extra,mirror,rows[4]]
        (self.base/'custom-source-worker').write_bytes(encode(rows))
        result=self.finish()
        self.assertEqual(result['receipt']['value']['raw_total'],75)
        self.assertEqual(len(result['receipt']['value']['responses']),5)
        self.assertTrue(check_record(self.record,self.base)['ok'])

    def test_partial_failed_source_preserved_not_closed(self):
        self.prepare(); self.launch('B')
        (self.base/'custom-source-B').write_bytes(encode(trace('session-B','turn-B','response-B')[:-1]))
        (self.base/'complete-B').write_text('failed')
        self.lifecycle('close',['--attempt','B'],1)
        history=lifecycle.events(self.root)
        self.assertEqual(history[-1]['kind'],'partial')
        self.assertTrue((self.root/history[-1]['value']['source']).exists())
        self.lifecycle('settle',expected=1)
        self.assertIsNone(check_record(self.record,self.base)['usage']['total_raw_tokens'])

    def test_completion_requires_all_measurement_files_and_consumer(self):
        import run_completion
        self.finish()
        self.record.update(label='real',resource_accounting='required')
        for evidence in self.record['evidence'].values(): evidence['kind']='host'
        acceptance=self.base/'acceptance.json'; acceptance.write_text('{"accepted":true}')
        self.record['evidence']['assessment'].update(kind='independent',file='acceptance.json',
                                                  sha256=lifecycle.digest(acceptance.read_bytes()))
        for task in self.record['tasks']:
            task['resource_preflight']={'host':'fixture','cpu':'1','ram':'1GB','disk':'fixture','evidence':'result'}
            task['resources']=[]
        preserve=[{'path':str(path.relative_to(self.base.resolve())),'sha256':sha} for path,sha in lifecycle.retained_files(self.record,self.base)]
        manifest={'run_id':'goal-1','owner':'B','consumers':['measurement-v2'],'preserve':preserve}
        mh=lifecycle.digest(lifecycle.encoded(manifest))
        self.record['artifact_retention']={'run_id':'goal-1','manifest_sha256':mh,'quiescent':True,
                                         'consumers':[{'id':'measurement-v2','state':'settled'}]}
        self.assertTrue(run_completion.validate_acceptance(self.record,self.record_path,manifest,mh)['ok'])
        manifest['preserve'].pop()
        with self.assertRaisesRegex(ValueError,'measurement evidence not preserved'):
            run_completion.validate_acceptance(self.record,self.record_path,manifest,mh)


    def test_final_snapshot_hash_tamper_rejected(self):
        self.finish()
        final=next(e['value'] for e in lifecycle.events(self.root) if e['kind']=='closed')
        path=self.root/final['source']
        path.write_bytes(path.read_bytes().replace(b'"input_tokens": 10',b'"input_tokens": 11',1))
        checked=check_record(self.record,self.base)
        self.assertFalse(checked['ok'])
        self.assertIsNone(checked['usage']['total_raw_tokens'])

    def test_unplanned_native_turn_nested_usage_and_truncation_rejected(self):
        rows=trace('session-B','turn-B','response-B')
        for change in ('turn','root','newline'):
            candidate=copy.deepcopy(rows)
            if change=='turn': candidate[2]['payload']['turn_id']='unplanned'
            if change=='root': candidate[2]['payload']['root_turn_id']='nested'
            data=encode(candidate)
            if change=='newline': data=data[:-1]
            with self.assertRaises(ValueError): lifecycle.single_turn(data,'turn-B')

    def test_zero_active_prepare_and_prelaunch_need_no_probe_worker(self):
        self.hooks['entries'][0].pop('launchTokenHash')
        self.hooks['entries'][0]['receivedAt'] = 1
        (self.base/'hooks.json').write_text(json.dumps(self.hooks))
        with closing(sqlite3.connect(self.base/'host.db')) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM dispatch_contexts').fetchone()[0], 0)
        self.prepare()
        prep = lifecycle.decode((self.root/'prepare.json').read_bytes())
        self.assertNotIn('dispatch', prep['readiness'])
        self.assertFalse(prep['readiness']['hard_provider_deadline'])
        self.assertEqual(lifecycle.digest((self.root/'capture-probe').read_bytes()), prep['capture_probe_sha256'])
        self.launch('B')
        self.assertEqual((self.base/'starts').read_text().splitlines(), ['B'])

    def test_unsupported_capture_settings_deny_before_start(self):
        path = self.base/'host-settings.json'
        settings = json.loads(path.read_text())
        settings['settings']['experimentalNativeChat'] = True
        path.write_text(json.dumps(settings))
        result = self.lifecycle('prepare',['--plan',str(self.base/'plan.json'),'--ledger',str(self.root)],1)
        self.assertIn('unsupported launch configuration',result['error'])
        self.assertFalse((self.base/'starts').exists()); self.assertFalse(self.root.exists())

    def test_unsupported_sample_denies_without_start(self):
        self.probe_source.write_bytes(encode(trace('session-probe','turn-probe','response-probe')[:-1]))
        result = self.lifecycle('prepare', ['--plan',str(self.base/'plan.json'),'--ledger',str(self.root)], 1)
        self.assertIn('source shape', result['error'])
        self.assertFalse(self.root.exists())
        self.assertFalse((self.base/'starts').exists())

    def test_v2_intentional_retry_retains_failed_usage(self):
        self.prepare(); self.launch('worker'); self.close('worker', 'failed')
        task = self.record['tasks'][0]
        task.update(id='task-worker', current_dispatch='dispatch-worker')
        task['execution']['state'] = 'settled'
        task['execution']['result'].update(outcome='failed', task='task-worker', dispatch='dispatch-worker')
        for key in ('technical', 'parent_integration'):
            task[key].update(task='task-worker',dispatch='dispatch-worker')
        self.save()
        packet = copy.deepcopy(self.packets['worker'])
        packet['binding'].update(planned=False, attempt='dispatch-worker')
        path = self.base/'decision-worker-retry.json'; path.write_text(json.dumps(packet))
        retry = copy.deepcopy(next(a for a in self.plan['attempts'] if a['id']=='worker'))
        retry.update(id='worker-retry',ordinal=2,retry_of='worker',decision_sha256=lifecycle.digest(path.read_bytes()))
        amendment = self.base/'retry-amend.json'; amendment.write_text(json.dumps([retry]))
        self.lifecycle('amend',['--plan',str(amendment)])
        argv = self.launch_args('worker-retry')
        pos = argv.index('--spec'); argv[pos:pos+2] = ['--task','task-worker','--retry-of','dispatch-worker']
        self.cli('routing_launch.py', argv)
        self.close('worker-retry')
        for actor in self.actors:
            if actor != 'worker': self.launch(actor); self.close(actor)
        settled = self.lifecycle('settle')['receipt']['value']
        self.assertEqual(settled['raw_total'], 75)
        self.assertEqual({r['attempt'] for r in settled['responses'].values()}, set(self.actors+['worker-retry']))
        failed = next(e['value'] for e in lifecycle.events(self.root) if e['kind']=='closed' and e['value']['attempt']=='worker')
        self.assertEqual(failed['outcome'],'failed')
        self.assertTrue((self.root/failed['source']).exists())
        self.assertEqual((self.base/'starts').read_text().splitlines().count('worker-retry'),1)

    def canary_setup(self):
        # Different goal owner uses a fresh empty namespace, never rebinds or
        # rewrites the already-created B fixture's historical enrollment.
        self.build_fixture(owner='coordinator')
        import measurement_canary as canary
        fixture = lifecycle.decode(canary.FIXTURE.read_bytes())
        self.actors = fixture['actors']
        from typing import Any
        def renamed(value: Any) -> Any:
            if isinstance(value, dict): return {k: renamed(v) for k,v in value.items()}
            if isinstance(value, list): return [renamed(v) for v in value]
            return 'coordinator' if value == 'B' else value
        self.record = renamed(self.record)
        task = self.record['tasks'][0]
        task['technical']['actor'] = 'independent-reviewer'
        task['parent_integration']['actor'] = 'coordinator'
        self.record['measurement'].update(expected_actors=self.actors, boundary=fixture['boundary'])
        self.plan['limits'] = fixture['limits']
        self.plan['attempts'] = []
        for actor in self.actors:
            packet = copy.deepcopy(self.packets['worker'])
            packet['binding'].update(task='task-'+actor, attempt='planned:task-'+actor,
                                    spec_sha256=lifecycle.digest(fixture['prompts'][actor].encode()))
            packet['profile_binding'] = prepared_profile('task-'+actor)
            path=self.base/(actor+'.json'); path.write_text(json.dumps(packet))
            self.plan['attempts'].append({'id':actor,'actor':actor,'provider':'codex','ordinal':1,'retry_of':None,
                'decision_sha256':lifecycle.digest(path.read_bytes()),'spec_sha256':packet['binding']['spec_sha256']})
        (self.base/'plan.json').write_text(json.dumps(self.plan)); self.save(); self.prepare()
        return fixture

    def test_deterministic_canary_driver_real_clis_offline(self):
        self.canary_setup(); (self.base/'auto-complete').touch()
        result = self.cli('measurement_canary.py',['run','--record',str(self.record_path),
            '--decisions',str(self.base),'--orca',str(self.exe),'--from','synthetic-sender','--authorize-live'])
        self.assertTrue(result['ok']); self.assertFalse(result['hard_provider_deadline'])
        self.assertEqual(result['settlement']['receipt']['value']['raw_total'],135)
        self.assertEqual(len(result['settlement']['receipt']['value']['responses']),9)
        self.assertEqual([r['answer'] for r in result['attempts']],
                         ['CANARY_SUM=5','CANARY_REVIEW=PASS','CANARY_ACCEPT=PASS'])
        state = json.loads((self.base/'fake-state.json').read_text())
        self.assertEqual(state['reports'], self.actors)
        self.assertEqual(state['checked'], self.actors)
        self.assertEqual((self.base/'starts').read_text().splitlines(),self.actors)

    def use_sqlite_host(self, app_version='1.4.268'):
        # Stage a synthetic reviewed host artifact. Production code still
        # checks the selected contract and exact bytes through each CLI.
        pkg = self.base/'fixture-package'
        shutil.copytree(SCRIPTS.parent, pkg, ignore=shutil.ignore_patterns('__pycache__'))
        self.scripts = pkg/'scripts'
        path = self.scripts.parent/'assets'/lifecycle.SQLITE_HOSTS[app_version].name
        contract = lifecycle.decode(path.read_bytes())
        bundle = self.base/'host-bundle'
        out = bundle/'app.asar.unpacked/out'
        host_source = out/'main/chunks'/contract['source_name']
        host_source.parent.mkdir(parents=True)
        host_source.write_bytes(b'explicit offline host source fixture\n')
        contract['observed_full_sha256'] = lifecycle.digest(host_source.read_bytes())
        if 'title_renderer' in contract:
            self.title_renderer = out/contract['title_renderer']['path']
            self.title_renderer.parent.mkdir(parents=True)
            self.title_renderer.write_bytes(b'explicit offline display-only title fixture\n')
            contract['title_renderer']['sha256'] = lifecycle.digest(self.title_renderer.read_bytes())
            self.title_asar = bundle/'app.asar'
            self.title_asar.write_bytes(b'explicit offline title layout handler fixture\n')
            contract['title_app_asar_sha256'] = lifecycle.digest(self.title_asar.read_bytes())
        path.write_bytes(lifecycle.encoded(contract))
        db = self.base/'orchestration.db'
        (self.base/'host.db').rename(db)
        with closing(sqlite3.connect(db)) as conn:
            conn.execute('ALTER TABLE dispatch_contexts ADD COLUMN creator_dispatch_id')
        self.profile_db = self.base/'profiles/local-default/profile-state.db'
        self.profile_db.parent.mkdir(parents=True)
        self.profile_db.with_suffix('.db.authority').write_text('sqlite\n')
        with closing(sqlite3.connect(self.profile_db)) as conn:
            conn.execute('CREATE TABLE profile_state_documents (domain TEXT PRIMARY KEY, domain_version INTEGER, payload TEXT)')
        self.set_sqlite_settings()
        self.hook_db = self.base/'agent-hooks/last-status.db'
        self.hook_db.parent.mkdir()
        with closing(sqlite3.connect(self.hook_db)) as conn, conn:
            conn.execute('CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            conn.execute('CREATE TABLE rows (key TEXT PRIMARY KEY, seq INTEGER NOT NULL, value TEXT NOT NULL)')
            conn.execute("INSERT INTO meta VALUES ('schema_version','202')")
            sample = {**self.hooks['entries'][0], 'source':'codex'}
            conn.executemany('INSERT INTO rows VALUES (?,?,?)',
                             [('entry\0pane-probe',1,json.dumps(sample)), ('commitment\0pane-probe',2,'{}')])
        (self.base/'use-268').touch()
        if app_version == '1.4.269':
            (self.base/'use-269').touch()
        self.plan['collector'].update(database=str(db), hooks=str(self.hook_db), host_source=str(host_source))
        (self.base/'plan.json').write_bytes(lifecycle.encoded(self.plan))

    def set_sqlite_settings(self, **overrides):
        payload = {'agentDefaultSurface':'terminal','agentStatusHooksEnabled':True,
                   'tabAutoGenerateTitle':False, **overrides}
        with closing(sqlite3.connect(self.profile_db)) as conn, conn:
            conn.execute("INSERT OR REPLACE INTO profile_state_documents VALUES ('settings',1,?)",
                         (json.dumps(payload),))

    def test_268_sqlite_prepare_checked_launch_and_settlement(self):
        self.use_sqlite_host()
        self.set_sqlite_settings(tabAutoGenerateTitle=True, agentDefaultSurface='chat',
                                 nativeChatProviders={'codex':False})
        result = self.finish()
        prep = lifecycle.decode((self.root/'prepare.json').read_bytes())
        self.assertEqual(prep['readiness']['app_version'], '1.4.268')
        self.assertEqual(prep['readiness']['hook_schema'], 202)
        self.assertTrue(prep['readiness']['capture_settings']['tabAutoGenerateTitle'])
        self.assertEqual(prep['readiness']['title_renderer_sha256'],
                         lifecycle.digest(self.title_renderer.read_bytes()))
        self.assertEqual(prep['readiness']['title_app_asar_sha256'],
                         lifecycle.digest(self.title_asar.read_bytes()))
        self.assertEqual(prep['future_provider_ids'], 'unobserved')
        self.assertEqual(result['receipt']['value']['raw_total'],60)
        bindings = [e['value']['bridge'] for e in lifecycle.events(self.root) if e['kind']=='binding']
        self.assertEqual([(b['dispatch'],b['session'],b['turn']) for b in bindings],
                         [('dispatch-'+a,'session-'+a,'turn-'+a) for a in self.actors])
        paths = [self.root/name for name in ('prepare.json','capture-probe')] + list(self.root.glob('event-*.json'))
        hashes = [lifecycle.digest(path.read_bytes()) for path in paths]
        self.assertTrue(self.cli('record_check.py',['check',str(self.record_path),'--json'])['ok'])
        self.assertEqual([lifecycle.digest(path.read_bytes()) for path in paths], hashes)

    def test_269_pinned_sqlite_settlement_without_automatic_titles(self):
        self.use_sqlite_host('1.4.269')
        self.set_sqlite_settings(tabAutoGenerateTitle=True)
        args = ['--plan', str(self.base/'plan.json'), '--ledger', str(self.root)]
        self.assertIn('unsupported automatic title implementation',
                      self.lifecycle('prepare', args, expected=1)['error'])
        self.set_sqlite_settings()
        result = self.finish()
        prep = lifecycle.decode((self.root/'prepare.json').read_bytes())
        self.assertEqual(prep['readiness']['app_version'], '1.4.269')
        self.assertEqual(result['receipt']['value']['raw_total'], 60)

    def test_268_seed_hook_requires_closed_fresh_native_turn(self):
        self.use_sqlite_host()
        (self.base/'seed-hook').touch()
        self.prepare()
        self.assertIn('native turn identity unavailable', self.launch('B', 1)['detail'])
        self.assertEqual([e['kind'] for e in lifecycle.events(self.root)], ['pending'])
        (self.base/'stale-source').touch()
        (self.base/'complete-B').write_text('completed')
        self.assertIn('fresh completed native turn required',
                      self.lifecycle('bind', ['--attempt', 'B'], expected=1)['error'])
        (self.base/'stale-source').unlink()
        self.lifecycle('bind', ['--attempt', 'B'])
        closed = self.lifecycle('close', ['--attempt', 'B'])
        self.assertTrue(closed['ok'])
        self.assertEqual([e['kind'] for e in lifecycle.events(self.root)], ['pending', 'binding', 'closed'])

    def test_268_prelaunch_rejects_title_chat_remote_and_unknown_store(self):
        self.use_sqlite_host()
        self.set_sqlite_settings(tabAutoGenerateTitle=True)
        self.prepare()
        for i, (override, expected) in enumerate([
            ({'tabAutoGenerateTitle':False},'collector contract/source changed'),
            ({'tabAutoGenerateTitle':'unknown'},'unsupported launch configuration'),
            ({'nativeChatProviders':{'codex':True}},'unsupported launch configuration'),
            ({'agentDefaultSurface':'chat'},'unsupported launch configuration'),
            ({'nativeChatProviders':{'codex':'false'}},'unknown Codex launch preference'),
        ]):
            with self.subTest(override=override):
                self.set_sqlite_settings(**override)
                self.assertIn(expected,self.launch('B',1,suffix=str(i))['detail'])
        self.set_sqlite_settings(tabAutoGenerateTitle=True)
        with closing(sqlite3.connect(self.hook_db)) as conn:
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA wal_autocheckpoint=0')
            conn.execute("UPDATE meta SET value='203' WHERE key='schema_version'")
            conn.commit()
            self.assertTrue(self.hook_db.with_suffix('.db-wal').stat().st_size)
            self.assertIn('unsupported SQLite hook store schema',self.launch('B',1,suffix='schema')['detail'])
            conn.execute("UPDATE meta SET value='202' WHERE key='schema_version'")
            conn.commit()
        self.hook_db.with_suffix('.json').write_text('{}')
        self.assertIn('hook-store authority',self.launch('B',1,suffix='legacy')['detail'])
        self.hook_db.with_suffix('.json').unlink()
        source = Path(self.plan['collector']['host_source'])
        original = source.read_bytes()
        source.write_bytes(original + b'changed')
        self.assertIn('unsupported host source contract',self.launch('B',1,suffix='source')['detail'])
        source.write_bytes(original)
        for path in (self.title_renderer, self.title_asar):
            original = path.read_bytes()
            path.write_bytes(original + b'changed')
            self.assertIn('unsupported automatic title implementation',
                          self.launch('B',1,suffix=path.name)['detail'])
            path.write_bytes(original)
        (self.base/'unknown-version').touch()
        self.assertIn('unsupported host version',self.launch('B',1,suffix='version')['detail'])
        (self.base/'unknown-version').unlink()
        (self.base/'remote-worktree').touch()
        self.assertIn('existing local worktree',self.launch('B',1,suffix='remote')['detail'])
        self.assertFalse((self.base/'starts').exists())
        self.assertEqual(lifecycle.events(self.root), [])

    def test_268_exact_source_rejects_unproven_worker_and_hook(self):
        for flag, expected in [('structured-start','actual launch'),
                               ('wrong-handle','launch terminal handle mismatch'),
                               ('duplicate-effect','launch terminal handle mismatch'),
                               ('wrong-worker-mode','fresh owned local Codex terminal'),
                               ('missing-hook','unique launch-token hook binding'),
                               ('wrong-hook-provider','local Codex terminal hook'),
                               ('wrong-hook-turn','fresh exact single-turn source'),
                               ('wrong-process','launch process incarnation mismatch')]:
            with self.subTest(flag=flag):
                self.build_fixture()
                self.use_sqlite_host()
                self.prepare()
                (self.base/flag).touch()
                self.assertIn(expected,self.launch('B',1)['detail'])
                self.assertEqual([e['kind'] for e in lifecycle.events(self.root)], ['pending'])
                (self.base/flag).unlink()
                self.assertIn('no renamed-result retry',self.launch('B',1,suffix='repeat')['detail'])
                self.assertEqual((self.base/'starts').read_text().splitlines(),['B'])
                self.lifecycle('settle',expected=1)

    def test_268_scoped_stop_refuses_helpers_and_bad_verdict(self):
        import measurement_canary as canary
        for flag, expected in [('plain','stopped'),('existing-child','unknown'),
                               ('wrong-stop','unknown'),('helper-stop','unknown')]:
            with self.subTest(flag=flag):
                self.build_fixture()
                self.use_sqlite_host()
                self.prepare(); self.launch('B')
                if flag == 'existing-child':
                    with closing(sqlite3.connect(self.plan['collector']['database'])) as conn, conn:
                        conn.execute("INSERT INTO dispatch_contexts (id,creator_dispatch_id) VALUES ('child','dispatch-B')")
                if flag != 'plain':
                    (self.base/flag).touch()
                root, prep = lifecycle.prepared(self.record,self.base)
                result = canary.stop_owned(root,prep,'B',str(self.exe),'deadline')
                self.assertEqual(result['state'],expected)
                self.assertFalse(result['hard_provider_deadline'])
                if flag == 'existing-child':
                    self.assertFalse((self.base/'stops').exists())
                else:
                    self.assertEqual((self.base/'stops').read_text().splitlines(),['dispatch-B'])
                self.launch('worker',1)
                self.lifecycle('settle',expected=1)

    def test_canary_host_completed_before_final_waits_without_reexecution(self):
        self.canary_setup(); (self.base/'auto-complete').touch()
        (self.base/'lag-worker').write_text('10')
        result = self.cli('measurement_canary.py',['run','--record',str(self.record_path),
            '--decisions',str(self.base),'--orca',str(self.exe),'--from','synthetic-sender','--authorize-live'])
        history = lifecycle.events(self.root)
        partials = [e for e in history if e['kind']=='partial']
        self.assertTrue(partials)
        self.assertTrue(all(e['value']['outcome']=='completed' for e in partials))
        self.assertFalse(any(e['kind']=='halt' for e in history))
        self.assertEqual(result['settlement']['receipt']['value']['raw_total'],135)
        self.assertEqual((self.base/'starts').read_text().splitlines(),self.actors)
        self.assertEqual(json.loads((self.base/'fake-state.json').read_text())['reports'],self.actors)

    def test_canary_budget_failure_returns_full_receipt_and_nonzero(self):
        self.canary_setup(); (self.base/'auto-complete').touch()
        rows, _ = canary_trace('coordinator', str(self.exe), {}, {})
        for row in rows:
            payload = row['payload']
            if row['type'] == 'token_usage_record':
                for field in ('usage', 'turn_token_usage', 'thread_token_usage'):
                    payload[field] = {k:v*10000 for k,v in payload[field].items()}
            if row['type'] == 'event_msg' and payload.get('type') == 'token_count':
                for field in ('total_token_usage', 'last_token_usage'):
                    payload['info'][field] = {k:v*10000 for k,v in payload['info'][field].items()}
        (self.base/'custom-source-coordinator').write_bytes(encode(rows))
        result = self.cli('measurement_canary.py', ['run', '--record', str(self.record_path),
            '--decisions', str(self.base), '--orca', str(self.exe), '--from', 'synthetic-sender',
            '--authorize-live'], expected=1)
        self.assertFalse(result['ok'])
        self.assertEqual(result['settlement']['accounting_status'], 'complete')
        self.assertEqual(result['settlement']['policy']['verdict'], 'budget_exceeded')
        self.assertEqual(result['settlement']['receipt']['value']['raw_total'], 450090)
        self.assertEqual(len(result['settlement']['receipt']['value']['responses']), 9)
        self.assertEqual((self.base/'starts').read_text().splitlines(), self.actors)

    def test_host_completion_and_usage_without_native_end_cannot_close(self):
        self.prepare(); self.launch('B')
        rows = trace('session-B','turn-B','response-B')
        source = self.base/'custom-source-B'
        source.write_bytes(encode(rows[:-1]))
        (self.base/'complete-B').write_text('completed')
        for _ in range(2):
            self.assertEqual(self.lifecycle('close',['--attempt','B'],1)['error'],'native completion pending')
        self.assertFalse(any(e['kind']=='closed' for e in lifecycle.events(self.root)))
        source.write_bytes(encode(rows))
        self.lifecycle('close',['--attempt','B'])
        self.assertEqual((self.base/'starts').read_text().splitlines(),['B'])

    def test_native_tail_and_conflicting_duplicate_fail_closed(self):
        rows, _ = canary_trace('worker',str(self.exe),{}, {})
        for change in ('post_end','duplicate_conflict','missing_response','unmetered_final'):
            candidate = copy.deepcopy(rows)
            if change == 'post_end': candidate += [candidate[-4]]
            if change == 'duplicate_conflict':
                duplicate = copy.deepcopy(candidate[3]); duplicate['payload']['root_turn_id']='other'
                candidate.insert(5,duplicate)
            if change == 'missing_response': candidate = candidate[:3]+candidate[5:]
            if change == 'unmetered_final': candidate = candidate[:-3]+[candidate[-1]]
            path=self.base/'negative.jsonl'; path.write_bytes(encode(candidate))
            with self.subTest(change=change):
                try:
                    lifecycle.single_turn(path.read_bytes(),'turn-worker')
                    result=lifecycle.read_usage(path,lifecycle.digest(path.read_bytes()),'worker','turn-worker')
                    self.assertNotEqual(result['usage']['coverage'],'complete')
                except ValueError:
                    pass  # Explicitly expected strict rejection, never reported as complete.

    def test_lifecycle_roundtrip_duplicates_count_once(self):
        rows, _ = canary_trace('worker',str(self.exe),{}, {})
        rows.insert(5,copy.deepcopy(rows[3]))
        path=self.base/'duplicates.jsonl'; path.write_bytes(encode(rows))
        result=lifecycle.read_usage(path,lifecycle.digest(path.read_bytes()),'worker','turn-worker')
        self.assertEqual(result['usage']['coverage'],'complete')
        self.assertEqual(result['usage']['raw_total'],45)
        self.assertEqual(len(result['provenance']['responses']),3)

    def test_duplicate_response_across_actors_cannot_settle(self):
        rows=trace('session-worker','turn-worker','response-B')
        (self.base/'custom-source-worker').write_bytes(encode(rows))
        self.prepare()
        for actor in self.actors:
            self.launch(actor); self.close(actor)
        result=self.lifecycle('settle',expected=1)
        self.assertIn('duplicate response across participants',result['error'])

    def test_source_advancing_during_completed_readback_stays_open(self):
        from unittest.mock import patch
        self.prepare(); self.launch('B')
        (self.base/'complete-B').write_text('completed')
        root,prep=lifecycle.prepared(self.record,self.base)
        original=lifecycle.host
        calls=[]
        def readback(*args):
            value=original(*args)
            if 'worker-show' in args:
                calls.append(value)
                if len(calls)==2:
                    path=self.base/'trace-B'
                    path.write_bytes(path.read_bytes()+encode([{'type':'event_msg','payload':{'type':'bookkeeping'}}]))
            return value
        with patch.object(lifecycle,'host',readback):
            with self.assertRaisesRegex(ValueError,'native completion pending'):
                lifecycle.close_attempt(root,prep,'B',str(self.exe))
        self.assertFalse(any(e['kind']=='closed' for e in lifecycle.events(root)))
        self.lifecycle('close',['--attempt','B'])
        self.assertEqual((self.base/'starts').read_text().splitlines(),['B'])

    def test_fixed_answer_acceptance_excludes_report_tool_output(self):
        import measurement_canary as canary
        rows, _ = canary_trace('worker',str(self.exe),{}, {})
        for change in ('valid','wrong','whitespace','missing','duplicate','wrong_end'):
            candidate=copy.deepcopy(rows)
            if change == 'wrong': candidate[-4]['payload']['content'][0]['text']='CANARY_SUM=6'
            if change == 'whitespace': candidate[-4]['payload']['content'][0]['text']+='\n'
            if change == 'missing': del candidate[-4]
            if change == 'duplicate': candidate.insert(-4,copy.deepcopy(candidate[-4]))
            if change == 'wrong_end': candidate[-1]['payload']['last_agent_message']='report only'
            path=self.base/'answer.jsonl'; path.write_bytes(encode(candidate))
            final={'source':path.name,'sha256':lifecycle.digest(path.read_bytes())}
            if change == 'valid': self.assertEqual(canary.accept_output(self.base,final,'CANARY_SUM=5'),'CANARY_SUM=5')
            else:
                with self.assertRaises(ValueError): canary.accept_output(self.base,final,'CANARY_SUM=5')

    def test_wrong_answer_halts_before_next_actor_without_losing_usage(self):
        self.canary_setup(); (self.base/'auto-complete').touch()
        rows,_=canary_trace('worker',str(self.exe),{}, {})
        rows[-4]['payload']['content'][0]['text']='CANARY_SUM=6'
        (self.base/'custom-source-worker').write_bytes(encode(rows))
        result=self.cli('measurement_canary.py',['run','--record',str(self.record_path),
            '--decisions',str(self.base),'--orca',str(self.exe),'--from','synthetic-sender','--authorize-live'],1)
        self.assertIn('canary halted',result['error'])
        self.assertEqual((self.base/'starts').read_text().splitlines(),['worker'])
        final=next(e['value'] for e in lifecycle.events(self.root) if e['kind']=='closed')
        usage=lifecycle.read_usage(self.root/final['source'],final['sha256'],'worker','turn-worker')
        self.assertEqual(usage['usage']['raw_total'],45)
        self.lifecycle('settle',expected=1)

    def test_scoped_stop_readback_and_halt_blocks_new_starts(self):
        import measurement_canary as canary
        self.prepare(); self.launch('B')
        root, prep=lifecycle.prepared(self.record,self.base)
        result=canary.stop_owned(root,prep,'B',str(self.exe),'deadline')
        self.assertEqual(result['state'],'stopped')
        self.assertEqual((self.base/'stops').read_text().splitlines(),['dispatch-B'])
        self.launch('worker',1)
        self.lifecycle('settle',expected=1)
        self.assertEqual((self.base/'starts').read_text().splitlines(),['B'])
        self.assertTrue(any(e['kind']=='partial' for e in lifecycle.events(root)))

    def test_deadline_driver_requests_only_its_dispatch_stop(self):
        import measurement_canary as canary
        from unittest.mock import patch
        from types import SimpleNamespace
        import time
        fixture = self.canary_setup()
        args = SimpleNamespace(enrollment_request=enrollment_path(self.base), expect_enrollment_sha256=lifecycle.digest(enrollment_path(self.base).read_bytes()), record=self.record_path, decisions=self.base, orca=str(self.exe),
                               action='launch', actor='worker', authorize_live=True,
                               sender='synthetic-sender', worktree='current')
        # Advance only the driver's clock, not subprocess/host clocks. No gate is mocked.
        ticks = iter([0, 0, 0, 121])
        clock = SimpleNamespace(time=time.time, monotonic=lambda: next(ticks), sleep=time.sleep)
        with patch.dict(os.environ, self.env), patch.object(canary, 'time', clock):
            with self.assertRaisesRegex(ValueError, 'canary halted'):
                canary.drive_attempt(args, fixture)
        self.assertEqual((self.base/'starts').read_text().splitlines(),['worker'])
        self.assertEqual((self.base/'stops').read_text().splitlines(),['dispatch-worker'])
        self.assertTrue(any(e['kind']=='halt' for e in lifecycle.events(self.root)))

    def test_unknown_stop_never_claims_cap_and_blocks_starts(self):
        import measurement_canary as canary
        self.prepare(); self.launch('B'); (self.base/'unknown-stop').touch()
        root, prep=lifecycle.prepared(self.record,self.base)
        result=canary.stop_owned(root,prep,'B',str(self.exe),'deadline')
        self.assertEqual(result['state'],'unknown'); self.assertFalse(result['hard_provider_deadline'])
        self.launch('worker',1)
        self.assertEqual((self.base/'starts').read_text().splitlines(),['B'])

    def test_unknown_acceptance_does_not_guess_stop_dispatch(self):
        import measurement_canary as canary
        self.prepare(); (self.base/'crash-start').touch(); self.launch('B',1)
        root, prep=lifecycle.prepared(self.record,self.base)
        result=canary.stop_owned(root,prep,'B',str(self.exe),'unknown start')
        self.assertEqual(result['state'],'unknown')
        self.assertFalse((self.base/'stops').exists())
        self.launch('worker',1)

    def test_canary_runner_rejects_unapproved_roster_without_launch(self):
        self.cli('measurement_canary.py',['prepare','--record',str(self.record_path),
                 '--decisions',str(self.base),'--orca',str(self.exe)],1)
        self.assertFalse((self.base/'starts').exists())


# Frozen terminal calculation from base 47a6cac28ddec822c0ce30ba42388761db3f8f6c.
# Deliberately independent of usage_policy; no Git or baseline checkout at runtime.
FROZEN_TERMINAL_VALUE = '''def terminal_value(root, p, history):
    """Accounting completeness is not policy acceptance. No host/model calls.

    Receipt schema is independent of the immutable v2 prepare/event envelope.
    Legacy v2 settlements have only prepare_sha256/responses/raw_total.
    """
    require(p['limits'] == decode((root / 'prepare.json').read_bytes())['limits'],
            'immutable limits changed')
    union = observed_union(root, p, history)
    total = sum(item['counts']['total_tokens'] for item in union.values())
    reasons = []
    if total > p['limits']['max_raw_tokens']:
        reasons.append('budget_exceeded')
    if any(e['kind'] == 'halt' for e in history):
        reasons.append('halted')
    latest = {a['actor']: a['id'] for a in p['attempts']}
    if any(e['kind'] == 'closed' and e['value']['attempt'] in latest.values()
           and e['value']['outcome'] != 'completed' for e in history):
        reasons.append('attempt_failed')
    return {'receipt_version': 1, 'accounting_status': 'complete',
            'prepare_sha256': digest((root / 'prepare.json').read_bytes()),
            'responses': union, 'raw_total': total,
            'policy': {'verdict': reasons[0] if reasons else 'within_budget',
                       'reasons': reasons, 'max_raw_tokens': p['limits']['max_raw_tokens'],
                       'success_eligible': not reasons}}
'''


class UsagePolicyTests(unittest.TestCase):
    """Synthetic policy inputs, not provider receipts or completeness evidence."""

    def setUp(self):
        from tempfile import TemporaryDirectory
        self.root = Path(self.enterContext(TemporaryDirectory(prefix='usage-policy-')))
        self.prep = {'attempts': [{'id': 'first', 'actor': 'worker'}],
                     'limits': {'max_raw_tokens': 15}}
        (self.root / 'prepare.json').write_bytes(lifecycle.encoded(self.prep))
        self.responses = {'codex/request/fixture': {'counts': {'total_tokens': 15}}}
        self.history = [{'kind': 'closed', 'value': {'attempt': 'first', 'outcome': 'completed'}}]

    def oracle(self, prep, history, responses):
        namespace = dict(vars(lifecycle))
        namespace['observed_union'] = lambda *_: responses
        exec(FROZEN_TERMINAL_VALUE, namespace)
        return namespace['terminal_value'](self.root, prep, history)

    def test_fixed_same_input_table_and_actual_terminal_consumer(self):
        from unittest.mock import patch
        cases = [
            ('below', 16, None, None, []),
            ('exact', 15, None, None, []),
            ('over', 14, None, None, ['budget_exceeded']),
            ('halt', 15, 'halt', None, ['halted']),
            ('failed', 15, None, 'failed', ['attempt_failed']),
            ('cancelled', 15, None, 'cancelled', ['attempt_failed']),
            ('all-reasons', 14, 'halt', 'failed', ['budget_exceeded', 'halted', 'attempt_failed']),
            ('partial-retained', 15, 'partial', None, []),
            ('terminal-replay', 15, 'settlement', None, []),
            ('retry-completed', 20, 'retry', 'failed', []),
            ('retry-failed', 20, 'retry', 'completed', ['attempt_failed']),
            ('two-actors', 20, 'actor', 'failed', ['attempt_failed']),
        ]
        for name, limit, extra, outcome, reasons in cases:
            with self.subTest(case=name):
                prep, history, responses = copy.deepcopy((self.prep, self.history, self.responses))
                prep['limits']['max_raw_tokens'] = limit
                if outcome:
                    history[0]['value']['outcome'] = outcome
                if extra in ('halt', 'partial', 'settlement'):
                    history.append({'kind': extra, 'value': {}})
                if extra in ('retry', 'actor'):
                    prep['attempts'].append({'id': 'next', 'actor': 'worker' if extra == 'retry' else 'reviewer'})
                    history.append({'kind': 'closed', 'value': {'attempt': 'next',
                                    'outcome': 'completed' if outcome == 'failed' else 'failed'}})
                    responses['codex/request/fixture-next'] = {'counts': {'total_tokens': 5}}
                (self.root / 'prepare.json').write_bytes(lifecycle.encoded(prep))
                frozen = copy.deepcopy((prep, history, responses))
                expected = self.oracle(prep, history, responses)
                total, policy = lifecycle.usage_policy(prep['attempts'], limit, history, responses)
                self.assertEqual((total, policy), (expected['raw_total'], expected['policy']))
                self.assertEqual(policy['reasons'], reasons)
                with patch.object(lifecycle, 'observed_union', return_value=responses) as union, \
                     patch.object(lifecycle, 'usage_policy', wraps=lifecycle.usage_policy) as helper:
                    actual = lifecycle.terminal_value(self.root, prep, history)
                    union.assert_called_once_with(self.root, prep, history)
                    helper.assert_called_once_with(prep['attempts'], limit, history, responses)
                self.assertEqual(lifecycle.encoded(actual), lifecycle.encoded(expected))
                self.assertEqual(actual['accounting_status'], 'complete')
                self.assertEqual(actual['policy']['success_eligible'], not reasons)
                self.assertEqual((prep, history, responses), frozen)
                policy['reasons'].append('caller-mutation')
                self.assertEqual(lifecycle.usage_policy(prep['attempts'], limit, history, responses)[1], expected['policy'])

    def test_pure_helper_has_no_io_or_host_calls(self):
        from unittest.mock import patch
        with patch('builtins.open', side_effect=AssertionError('unexpected open')), \
             patch.object(Path, 'read_bytes', side_effect=AssertionError('unexpected read')), \
             patch.object(lifecycle, 'host', side_effect=AssertionError('unexpected host')), \
             patch.object(lifecycle, 'now', side_effect=AssertionError('unexpected clock')), \
             patch.object(lifecycle, 'append', side_effect=AssertionError('unexpected append')):
            self.assertEqual(lifecycle.usage_policy(self.prep['attempts'], 15,
                             self.history, self.responses)[0], 15)

    def test_immutable_limits_and_upstream_partial_fail_before_policy(self):
        from unittest.mock import patch
        changed = copy.deepcopy(self.prep)
        changed['limits']['max_raw_tokens'] = 99
        with patch.object(lifecycle, 'usage_policy') as helper:
            with self.assertRaisesRegex(ValueError, 'immutable limits changed'):
                lifecycle.terminal_value(self.root, changed, self.history)
            helper.assert_not_called()
        for reason in ('retained partial evidence changed', 'source identity/coverage changed',
                       'every planned actor/attempt must be reserved, bound and closed exactly once'):
            with self.subTest(reason=reason), \
                 patch.object(lifecycle, 'observed_union', side_effect=ValueError(reason)), \
                 patch.object(lifecycle, 'usage_policy') as helper:
                with self.assertRaisesRegex(ValueError, reason):
                    lifecycle.terminal_value(self.root, self.prep, self.history)
                helper.assert_not_called()

    def test_terminal_receipt_exact_replay_legacy_and_negatives(self):
        from unittest.mock import patch
        with patch.object(lifecycle, 'observed_union', return_value=self.responses):
            expected = self.oracle(self.prep, self.history, self.responses)
            terminal = {'kind': 'settlement', 'value': copy.deepcopy(expected)}
            history = self.history + [terminal]
            before = copy.deepcopy(history)
            self.assertEqual(lifecycle.terminal_receipt(self.root, self.prep, history), (terminal, expected))
            self.assertEqual(lifecycle.terminal_receipt(self.root, self.prep, history), (terminal, expected))
            self.assertEqual(history, before)
            for field, value in [('raw_total', 0), ('receipt_version', 99),
                                 ('policy', {'success_eligible': True}), ('responses', {})]:
                forged = copy.deepcopy(history)
                forged[-1]['value'][field] = value
                with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'receipt forged'):
                    lifecycle.terminal_receipt(self.root, self.prep, forged)
            for invalid in (self.history, history + [terminal], history + [{'kind': 'halt', 'value': {}}]):
                with self.assertRaisesRegex(ValueError, 'exact terminal accounting receipt required'):
                    lifecycle.terminal_receipt(self.root, self.prep, invalid)
            legacy = copy.deepcopy(terminal)
            legacy['value'] = {k: expected[k] for k in ('prepare_sha256', 'responses', 'raw_total')}
            self.assertEqual(lifecycle.terminal_receipt(self.root, self.prep, self.history + [legacy]),
                             (legacy, expected))
            legacy['value']['raw_total'] = 0
            with self.assertRaisesRegex(ValueError, 'legacy settlement forged'):
                lifecycle.terminal_receipt(self.root, self.prep, self.history + [legacy])


if __name__=='__main__':
    unittest.main()
