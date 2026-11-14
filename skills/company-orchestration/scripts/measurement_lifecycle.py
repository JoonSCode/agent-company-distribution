#!/usr/bin/env python3
"""Version 2 local accounting ledger. No provider execution; no background collector.

Trust boundary: the same local OS account owns Orca metadata and these receipts.
Hashes detect changed evidence; they are not signatures against that OS account.
Only exact, fresh terminal hook bindings are supported. Structured/Hermes and
resumed sessions fail closed rather than being represented as Codex turns.
"""
import argparse
import copy
from contextlib import closing, contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess


from provider_usage import read_usage, unique_object

VERSION = 2
ADAPTER = 'orca-local-terminal/v2'
SOURCE_CONTRACT = Path(__file__).resolve().parent.parent / 'assets/orca-terminal-source-contract.json'


def collector_probe(config, executable):
    """Capability/access probe, NOT a future dispatch binding or billing receipt.

    The explicitly selected historical hook is only a parser-compatibility sample.
    No active worker, fresh hook, launch hash join or future provider ID is needed.
    Source slices are pinned to the reviewed installed host contract; unknown
    versions/serializers fail closed. Only allowlisted metadata leaves this probe.
    """
    contract = decode(SOURCE_CONTRACT.read_bytes())
    status = host(executable, 'status')
    require(status.get('target', {}).get('kind') == 'local'
            and status.get('runtime', {}).get('state') == 'ready', 'ready local runtime required')
    rt = status['runtime']
    require(rt.get('appVersion') == contract['app_version'],
            'unsupported host version: review exact resolver, hook serializer and worker-stop contract')
    require({'orchestration.contract.v1', 'orchestration.worker-stop-verdict.v1'}
            <= set(rt.get('capabilities', [])), 'unsupported host accounting/stop surfaces')
    hook_status = host(executable, 'agent', 'hooks', 'status')
    codex = [s for s in hook_status.get('statuses', []) if s.get('agent') == 'codex']
    require(hook_status.get('enabled') is True and len(codex) == 1
            and codex[0].get('state') == 'installed' and codex[0].get('managedHooksPresent') is True,
            'Codex managed hook capture is unavailable; enable/repair host hooks before launch')
    settings = decode(Path(hook_status['settingsPath']).read_bytes())['settings']
    # Read only these booleans; never export settings, prompts, accounts or env.
    flags = {k: settings.get(k) for k in ('experimentalNativeChat', 'experimentalStructuredNativeChat',
              'openAgentTabsInChatByDefault', 'agentStatusHooksEnabled', 'tabAutoGenerateTitle')}
    require(flags['agentStatusHooksEnabled'] is True
            and all(flags[k] is False for k in flags if k != 'agentStatusHooksEnabled'),
            'unsupported launch configuration: terminal-only/no-title-model capture required; do not change host settings implicitly')
    source_path = Path(config['host_source']).resolve()
    code = source_path.read_text()
    for section in contract['sections']:
        start = code.find(section['start'])
        end = code.find(section['end'], start + len(section['start']))
        require(start >= 0 and end > start
                and digest(code[start:end].encode()) == section['sha256'],
                'unsupported host source contract: exact resolver/serializer/scoped stop requires review')
    database = Path(config['database']).resolve()
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as db:
        db.execute('SELECT id, run_id, task_id, assignee_pane_key, process_incarnation, '
                   'launch_token_hash FROM dispatch_contexts LIMIT 0')
        db.execute('SELECT dispatch_id, runtime_epoch, agent_terminal_handle, state FROM worker_dispatches LIMIT 0')
    hooks = decode(Path(config['hooks']).read_bytes())
    require(hooks.get('version') == 2 and isinstance(hooks.get('entries'), (dict, list)),
            'unsupported hook snapshot schema; version 2 required')
    entries = hooks['entries']
    entries = list(entries.values()) if isinstance(entries, dict) else entries
    samples = [e for e in entries if e.get('providerSession', {}).get('key') == 'session_id'
               and e['providerSession'].get('id') == config['sample_session']]
    require(len(samples) == 1, 'explicit host-named historical sample required (not a LIVE dispatch)')
    sample_source = Path(samples[0]['providerSession']['transcriptPath']).resolve()
    sha = digest(sample_source.read_bytes())
    sample = read_usage(sample_source, sha, 'capability-sample-only', config['sample_turn'])
    require(sample['provenance']['session_id'] == config['sample_session']
            and sample['usage']['coverage'] == 'complete' and sample['provenance']['responses'],
            'unsupported provider source shape: complete response-level export required')
    require(isinstance(rt.get('runtimeId'), str) and rt['runtimeId'], 'host runtime identity unavailable')
    return {'runtime': rt['runtimeId'], 'app_version': rt['appVersion'],
            'source_contract_sha256': digest(SOURCE_CONTRACT.read_bytes()),
            'host_source_sha256': digest(code.encode()), 'hook_schema': 2,
            'capture_settings': flags, 'codex_hooks': 'installed',
            'sample': {'session': config['sample_session'], 'turn': config['sample_turn'],
                       'source': str(sample_source), 'sha256': sha},
            'meaning': 'capability/access only; future dispatch identity unobserved',
            'stop_command': ['orchestration', 'worker-stop', '--dispatch'],
            'hard_provider_deadline': False}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def decode(data):
    return json.loads(data, object_pairs_hook=unique_object,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False) + '\n').encode()


def now():
    return datetime.now(timezone.utc).isoformat()


def timestamp(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(result.tzinfo is not None, 'timezone required')
    return result.timestamp()


def write_once(path, data):
    """Exclusive durable receipts. A partial write blocks recovery, never retries work."""
    with path.open('xb') as stream:
        os.chmod(path, 0o600)
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextmanager
def locked(root):
    with (root / '.lock').open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def host(executable, *args):
    proc = subprocess.run([executable, *args, '--json'], capture_output=True,
                          text=True, timeout=30, check=False)
    envelope = decode(proc.stdout)
    require(proc.returncode == 0 and envelope.get('ok') is True, 'host read failed')
    return envelope['result']


def runtime(executable):
    value = host(executable, 'status')
    # Accept only the observed host identity, never a caller's claimed runtime.
    require(value.get('target', {}).get('kind') == 'local'
            and value.get('runtime', {}).get('state') == 'ready', 'ready local runtime required')
    ident = value['runtime'].get('runtimeId')
    require(isinstance(ident, str) and ident, 'host runtime identity unavailable')
    return ident


def exact_source(config, executable, dispatch_id, after=None):
    """Allowlisted join; never enumerate transcript filenames or copy hook payloads."""
    first = host(executable, 'orchestration', 'worker-show', '--dispatch', dispatch_id)
    dispatch = first['dispatch']
    require(dispatch['id'] == dispatch_id and first['observation']['exactWorker'] is True
            and first['observation']['status'] == 'live', 'exact live worker required')
    database = Path(config['database']).resolve()
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute('SELECT id, run_id, task_id, assignee_pane_key, process_incarnation, '
                          'launch_token_hash FROM dispatch_contexts WHERE id=?', (dispatch_id,)).fetchall()
    require(len(rows) == 1, 'exact dispatch row required')
    row = dict(rows[0])
    require(row['task_id'] == dispatch['taskId'] and row['run_id'] == dispatch['runId']
            and row['assignee_pane_key'] == dispatch['assigneePaneKey']
            and row['process_incarnation'] == dispatch['processIncarnation']
            and isinstance(row['launch_token_hash'], str) and len(row['launch_token_hash']) == 64
            and all(c in '0123456789abcdef' for c in row['launch_token_hash'])
            and row['process_incarnation'],
            'dispatch identity or launch hash unavailable')
    status = decode(Path(config['hooks']).read_bytes())
    entries = status['entries']
    entries = list(entries.values()) if isinstance(entries, dict) else entries
    matches = [entry for entry in entries if entry.get('paneKey') == row['assignee_pane_key']
               and entry.get('launchTokenHash') == row['launch_token_hash']]
    require(len(matches) == 1, 'unique launch-token hook binding required')
    entry = matches[0]
    require(entry.get('connectionId') is None and not entry.get('providerSessionOnly')
            and not entry.get('structuredHost'), 'local terminal hook required')
    require(type(entry['receivedAt']) is int, 'host hook timestamp must be milliseconds')
    observed = entry['receivedAt'] / 1000
    require(0 <= datetime.now(timezone.utc).timestamp() - observed <= 120,
            'stale or future hook binding')
    require(after is None or observed >= timestamp(after), 'hook predates launch intent')
    provider = entry['providerSession']
    require(provider['key'] == 'session_id' and provider['id']
            and entry['hostTurn']['owner'] == 'codex:' + provider['id'], 'Codex terminal session required')
    turn_key = entry['hostTurn']['currentTurnKey']
    require(isinstance(turn_key, str) and turn_key.startswith('turn:') and len(turn_key) > 5,
            'native turn identity unavailable')
    turn = turn_key[5:]  # Explicit Orca hostTurn encoding, not a guessed provider ID.
    source = Path(provider['transcriptPath']).resolve()
    data = source.read_bytes()
    require(data and data.endswith(b'\n'), 'partial source write; reconcile later')
    rows = [decode(line) for line in data.splitlines()]
    sessions = [r['payload'].get('id') for r in rows if r.get('type') == 'session_meta']
    starts = [r['payload'].get('turn_id') for r in rows if r.get('type') == 'event_msg'
              and r['payload'].get('type') == 'task_started']
    require(sessions == [provider['id']] and starts == [turn],
            'fresh exact single-turn source required; resumed/nested sessions unsupported')
    single_turn(data, turn)
    second = host(executable, 'orchestration', 'worker-show', '--dispatch', dispatch_id)
    require(second['dispatch'] == dispatch and second['observation']['exactWorker'] is True
            and second['observation']['status'] == 'live', 'worker changed during capture')
    return {'dispatch': dispatch_id, 'task': row['task_id'], 'run': row['run_id'],
            'pane': row['assignee_pane_key'], 'process': row['process_incarnation'],
            'launch_token_sha256': row['launch_token_hash'], 'session': provider['id'],
            'turn': turn, 'source': str(source), 'observed_at': entry['receivedAt'],
            'prefix_bytes': len(data), 'prefix_sha256': digest(data)}, data


def single_turn(data, turn):
    require(data and data.endswith(b'\n'), 'complete JSONL record boundary required')
    ended = False
    for line in data.splitlines():
        row = decode(line)
        payload = row['payload']
        require(not ended or (row.get('type') not in ('response_item', 'token_usage_record', 'turn_context')
                and not (row.get('type') == 'event_msg' and payload.get('type') in
                         ('task_started', 'task_complete', 'agent_message', 'item_completed', 'token_count'))),
                'native activity after completion; cannot finalize snapshot')
        if row.get('type') == 'event_msg' and payload.get('type') == 'task_complete':
            ended = True
        if row.get('type') in ('token_usage_record', 'turn_context'):
            require(payload.get('turn_id') == turn, 'unplanned native turn')
        if row.get('type') == 'token_usage_record':
            require(payload.get('root_turn_id') == turn, 'nested model usage unsupported')
        if row.get('type') == 'event_msg' and payload.get('type') in ('task_started', 'task_complete'):
            require(payload.get('turn_id') == turn, 'unplanned native boundary')


def freeze(record, base):
    m, goal = record['measurement'], record['goal']
    require(m.get('version') == VERSION and m.get('mode') == 'required', 'measurement v2 required')
    binding = {k: goal[k] for k in ('id', 'revision', 'scope', 'plan')}
    require(m['goal_binding'] == binding, 'goal binding differs')
    files = {}
    for name, ref in [('plan', goal['plan']), ('objective', m['objective']), ('criteria', m['criteria'])]:
        evidence = record['evidence'][ref]
        data = (base / evidence['file']).read_bytes()
        require(digest(data) == evidence['sha256'], 'frozen input hash mismatch')
        files[name] = {'ref': ref, 'sha256': digest(data)}
    require(set(m['boundary']) == {'start', 'end', 'shared_costs'}
            and all(isinstance(v, str) and v for v in m['boundary'].values()), 'explicit boundary required')
    actors = m['expected_actors']
    require(isinstance(actors, list) and actors and all(isinstance(a, str) and a for a in actors)
            and len(set(actors)) == len(actors), 'unique expected actors required')

    return {'goal_binding': binding, 'files': files, 'boundary': m['boundary'], 'expected_actors': actors}


def required_actors(record):
    result = {record['goal']['current_owner']}
    for task in record['tasks']:
        for key in ('execution', 'technical', 'parent_integration'):
            if task.get(key):
                result.add(task[key]['actor'])
    assessment = record['goal'].get('assessment') or {}
    if assessment.get('basis') == 'independent':
        result.add(assessment['actor'])
    return result


def validate_attempts(attempts, actors):
    require(isinstance(attempts, list) and attempts, 'attempt roster required')
    ids, ordinals = set(), {}
    for item in attempts:
        require(set(item) == {'id', 'actor', 'provider', 'decision_sha256', 'spec_sha256', 'ordinal', 'retry_of'},
                'exact planned attempt fields required; future IDs must remain unobserved')
        require(isinstance(item['id'], str) and item['id'] and item['id'] not in ids, 'duplicate attempt')
        ids.add(item['id'])
        require(item['actor'] in actors and item['provider'] == 'codex', 'unsupported or omitted participant')
        require(type(item['ordinal']) is int and item['ordinal'] > 0, 'attempt ordinal required')
        require(item['ordinal'] == ordinals.get(item['actor'], 0) + 1, 'actor attempt ordinal must be sequential')
        ordinals[item['actor']] = item['ordinal']
        for key in ('decision_sha256', 'spec_sha256'):
            require(isinstance(item[key], str) and len(item[key]) == 64
                    and all(c in '0123456789abcdef' for c in item[key]), 'planned hash required')
        require(item['retry_of'] is None or item['retry_of'] in ids - {item['id']}, 'retry predecessor missing')
    require({item['actor'] for item in attempts} == set(actors), 'all actors need attempts')


def events(root):
    result, previous = [], None
    for path in sorted(root.glob('event-*.json')):
        data = path.read_bytes()
        item = decode(data)
        require(path.name == 'event-%06d.json' % len(result) and item['sequence'] == len(result)
                and item['previous'] == previous and item['version'] == VERSION, 'ledger chain changed')
        result.append(item)
        previous = digest(data)
    return result


def append(root, kind, value):
    prior = events(root)
    sequence = len(prior)
    previous = digest((root / ('event-%06d.json' % (sequence - 1))).read_bytes()) if prior else None
    item = {'version': VERSION, 'sequence': sequence, 'previous': previous,
            'at': now(), 'kind': kind, 'value': value}
    write_once(root / ('event-%06d.json' % sequence), encoded(item))
    return item


def prepared(record, base):
    root = (base / record['measurement']['ledger']).resolve()
    data = (root / 'prepare.json').read_bytes()
    require(digest(data) == record['measurement']['prepare_sha256'], 'prepare hash mismatch')
    p = decode(data)
    require(p['version'] == VERSION and p['adapter'] == ADAPTER and p['frozen'] == freeze(record, base),
            'immutable prepared contract changed')
    validate_attempts(p['attempts'], p['frozen']['expected_actors'])
    require(p['limits']['paid_fallback'] is False and p['limits']['concurrency'] == 1,
            'unsupported spend/concurrency policy')
    require(digest((root / 'capture-probe').read_bytes()) == p['capture_probe_sha256'], 'capture probe changed')
    for event in events(root):
        if event['kind'] == 'amendment':
            extra = event['value']['attempts']
            require(isinstance(extra, list) and extra, 'empty amendment')
            p['attempts'] += extra
    actors = {a['actor'] for a in p['attempts']}
    validate_attempts(p['attempts'], actors)
    require(required_actors(record) <= actors and len(p['attempts']) <= p['limits']['max_attempts'],
            'required actor omitted or attempt budget exceeded')
    return root, p


def prepare(record_path, plan_path, root, executable, probe_dispatch=None):
    record = decode(record_path.read_bytes())
    plan = decode(plan_path.read_bytes())
    frozen = freeze(record, record_path.parent)
    validate_attempts(plan['attempts'], frozen['expected_actors'])
    require(required_actors(record) <= set(frozen['expected_actors']), 'required participant omitted')
    limits = plan['limits']
    require(set(limits) == {'max_attempts', 'concurrency', 'paid_fallback', 'max_raw_tokens', 'deadline_seconds'}
            and limits['paid_fallback'] is False and limits['concurrency'] == 1
            and all(type(limits[k]) is int and limits[k] > 0 for k in ('max_attempts', 'max_raw_tokens', 'deadline_seconds'))
            and len(plan['attempts']) <= limits['max_attempts'], 'numeric bounded no-paid-fallback limits required')
    require(plan['adapter'] == ADAPTER, 'unsupported collector adapter')
    require(probe_dispatch is None, '--probe-dispatch is obsolete: readiness must not depend on active work')
    bridge = collector_probe(plan['collector'], executable)
    runtime_id = bridge['runtime']
    root.mkdir(mode=0o700, parents=False, exist_ok=False)
    probe = os.urandom(32)
    write_once(root / 'capture-probe', probe)
    require((root / 'capture-probe').read_bytes() == probe, 'capture readback failed')
    value = {'version': VERSION, 'adapter': ADAPTER, 'created_at': now(), 'runtime': runtime_id,
             'collector': plan['collector'], 'readiness': bridge, 'frozen': frozen,
             'attempts': plan['attempts'], 'limits': limits, 'future_provider_ids': 'unobserved',
             'capture_probe_sha256': digest(probe)}
    write_once(root / 'prepare.json', encoded(value))
    return {'ok': True, 'ledger': str(root), 'prepare_sha256': digest(encoded(value)),
            'future_provider_ids': 'unobserved'}


class Launch:
    def __init__(self, args, record, base):
        self.root, self.prep = prepared(record, base)
        self.args = args
        self.attempt = next((a for a in self.prep['attempts'] if a['id'] == args.measurement_attempt), None)
        if self.attempt is None:
            raise ValueError('explicit prepared attempt required')

    def check(self):
        args, p = self.args, self.prep
        decision = decode(args.decision.read_bytes())
        require(decision.get('constraints', {}).get('billing') == 'subscription'
                and args.declared_billing != 'paid_api', 'v2 forbids paid billing/fallback')
        require(not any((args.terminal, args.reuse_dispatch, args.origin_receipt)), 'v2 terminal reuse unsupported')
        require(digest(args.decision.read_bytes()) == self.attempt['decision_sha256'], 'prepared decision changed')
        require(args.spec is None or digest(args.spec.encode()) == self.attempt['spec_sha256'], 'prepared spec changed')
        require(runtime(args.orca) == p['runtime'], 'runtime changed since preparation')
        require(datetime.now(timezone.utc).timestamp() <= timestamp(p['created_at']) + p['limits']['deadline_seconds'],
                'prepared deadline expired')
        history = events(self.root)
        require(not any(e['kind'] == 'halt' for e in history), 'canary halted; no further starts')
        require(not any(e['kind'] == 'settlement' for e in history), 'already settled')
        require(not any(e['value'].get('attempt') == self.attempt['id'] for e in history),
                'attempt already reserved; reconcile, never launch again')
        pending = {e['value']['attempt'] for e in history if e['kind'] == 'pending'}
        closed = {e['value']['attempt'] for e in history if e['kind'] == 'closed'}
        require(pending <= closed, 'previous attempt still open or outcome unknown')
        total = 0
        for event in history:
            if event['kind'] == 'closed':
                final = event['value']
                binding = next(e['value'] for e in history if e['kind'] == 'binding'
                               and e['value']['attempt'] == final['attempt'])
                total += read_usage(self.root / final['source'], final['sha256'], final['attempt'],
                                    binding['bridge']['turn'])['usage']['raw_total']
        require(total < p['limits']['max_raw_tokens'], 'observed soft token stop reached')
        predecessor = self.attempt['retry_of']
        if predecessor:
            prior = [e for e in history if e['kind'] == 'closed' and e['value']['attempt'] == predecessor]
            require(len(prior) == 1 and prior[0]['value']['outcome'] == 'failed', 'retry needs retained failed settlement')
            bindings = [e['value'] for e in history if e['kind'] == 'binding' and e['value']['attempt'] == predecessor]
            require(len(bindings) == 1 and args.retry_of == bindings[0]['bridge']['dispatch'], 'retry dispatch mismatch')
        else:
            require(args.retry_of is None, 'unplanned retry')
        # Access/capability only, never require an unrelated live dispatch.
        probe = collector_probe(p['collector'], args.orca)
        require(probe == p['readiness'], 'collector contract/source changed since preparation')

    def pending(self, command, receipt):
        require(digest(self.args.decision.read_bytes()) == self.attempt['decision_sha256'], 'decision changed before invocation')
        return append(self.root, 'pending', {'attempt': self.attempt['id'], 'argv': command,
                      'result': str(self.args.result.resolve()), 'receipt_sha256': digest(receipt.read_bytes()),
                      'prepare_sha256': digest((self.root / 'prepare.json').read_bytes())})

    def bind(self):
        return bind(self.root, self.prep, self.attempt['id'], self.args.orca)


@contextmanager
def launch_guard(args):
    record = decode(args.record.read_bytes())
    m = record.get('measurement', {})
    if m.get('version') != VERSION:
        yield None
        return
    require(m.get('mode') == 'required', 'v2 must require measurement')
    args.orca = args.orca or 'orca'
    launch = Launch(args, record, args.record.parent)
    with locked(launch.root):
        yield launch


def bind(root, p, attempt, executable):
    history = events(root)
    require(not any(e['kind'] in ('binding', 'settlement') and
                    (e['kind'] == 'settlement' or e['value'].get('attempt') == attempt) for e in history),
            'already bound or settled')
    pending = [e for e in history if e['kind'] == 'pending' and e['value']['attempt'] == attempt]
    require(len(pending) == 1, 'exact persisted invocation required')
    pending = pending[0]
    saved = decode(Path(pending['value']['result']).read_bytes())
    require(saved['launch_state'] == 'observed' and saved['readback_status'] == 'observed'
            and saved['prelaunch_receipt_sha256'] == pending['value']['receipt_sha256'],
            'accepted host receipt unavailable; unknown start cannot be retried')
    start = decode(saved['stdout'])['result']
    require(runtime(executable) == p['runtime'], 'runtime changed')
    bridge, data = exact_source(p['collector'], executable, start['dispatchId'], after=pending['at'])
    require(bridge['task'] == start['taskId'] and bridge['run'] == start['runId'], 'launch/source ID mismatch')
    require(not any(e['kind'] == 'binding' and (e['value']['bridge']['dispatch'] == bridge['dispatch']
                or e['value']['bridge']['session'] == bridge['session']) for e in history), 'duplicate dispatch/session')
    name = 'source-%06d-prefix.jsonl' % len(history)
    write_once(root / name, data)
    return append(root, 'binding', {'attempt': attempt, 'bridge': bridge, 'prefix': name,
                  'host_receipt_sha256': digest(encoded(saved)), 'host_receipt': saved,
                  'status': 'usage_observed' if any(decode(line).get('type') == 'token_usage_record'
                                                   for line in data.splitlines()) else 'identity_observed'})


def close_attempt(root, p, attempt, executable):
    history = events(root)
    require(not any(e['kind'] == 'settlement' or (e['kind'] == 'closed' and e['value']['attempt'] == attempt)
                    for e in history), 'already closed or settled')
    bindings = [e['value'] for e in history if e['kind'] == 'binding' and e['value']['attempt'] == attempt]
    require(len(bindings) == 1, 'attempt has no exact binding')
    binding = bindings[0]
    bridge = binding['bridge']
    observed = host(executable, 'orchestration', 'worker-show', '--dispatch', bridge['dispatch'])['dispatch']
    require(runtime(executable) == p['runtime'] and observed['id'] == bridge['dispatch']
            and observed['taskId'] == bridge['task'] and observed['runId'] == bridge['run']
            and observed['processIncarnation'] == bridge['process'], 'final host identity changed')
    outcome = observed['status']
    require(outcome in ('completed', 'failed', 'cancelled'), 'attempt still running')
    data = Path(bridge['source']).read_bytes()
    prefix = (root / binding['prefix']).read_bytes()
    require(digest(prefix) == bridge['prefix_sha256'] and data.startswith(prefix), 'source prefix changed')
    name = 'source-%06d-final.jsonl' % len(history)
    # Preserve even incomplete failed/cancelled accounting; it never becomes zero.
    write_once(root / name, data)
    # A worker_done can settle the host while its tool result/final response is
    # still streaming. Preserve that observation, but never close on host status
    # alone or turn a partial capture into a terminal accounting failure.
    pending = False
    try:
        if not data or not data.endswith(b'\n'):
            pending = True
            raise ValueError('source write in progress')
        single_turn(data, bridge['turn'])
        sample = read_usage(root / name, digest(data), attempt, bridge['turn'])
        require(sample['provenance']['session_id'] == bridge['session'], 'final source identity changed')
        if sample['usage']['coverage'] != 'complete':
            pending = True
            raise ValueError('final source incomplete')
        second = host(executable, 'orchestration', 'worker-show', '--dispatch', bridge['dispatch'])['dispatch']
        require(second == observed and runtime(executable) == p['runtime'], 'final host identity changed during capture')
        if Path(bridge['source']).read_bytes() != data:
            pending = True
            raise ValueError('source advanced during capture')
    except ValueError as exc:
        append(root, 'partial', {'attempt': attempt, 'outcome': outcome, 'source': name,
               'sha256': digest(data), 'bytes': len(data), 'reason': str(exc)})
        if outcome == 'completed' and pending:
            raise ValueError('native completion pending') from exc
        raise ValueError('partial accounting preserved; attempt remains open') from exc
    starts = [decode(line)['payload'].get('turn_id') for line in data.splitlines()
              if decode(line).get('type') == 'event_msg' and decode(line)['payload'].get('type') == 'task_started']
    require(starts == [bridge['turn']], 'unplanned additional turn')
    return append(root, 'closed', {'attempt': attempt, 'outcome': outcome, 'source': name,
                  'sha256': digest(data), 'bytes': len(data), 'host_dispatch': observed})


def observed_union(root, p, history):
    for event in history:
        require(event['kind'] in ('pending', 'binding', 'partial', 'closed', 'amendment',
                                  'halt', 'stop_pending', 'stop_observed', 'settlement'),
                'unsupported ledger event')
        if event['kind'] == 'partial':
            item = event['value']
            data = (root / item['source']).read_bytes()
            require(digest(data) == item['sha256'] and len(data) == item['bytes'],
                    'retained partial evidence changed')
    roster = {a['id']: a for a in p['attempts']}
    closed = [e['value'] for e in history if e['kind'] == 'closed']
    bindings = [e['value'] for e in history if e['kind'] == 'binding']
    pending = [e['value'] for e in history if e['kind'] == 'pending']
    for items in (closed, bindings, pending):
        require(len(items) == len(roster) and {i['attempt'] for i in items} == set(roster),
                'every planned actor/attempt must be reserved, bound and closed exactly once')
    require(len({b['bridge']['dispatch'] for b in bindings}) == len(bindings),
            'duplicate dispatch binding')
    result, scopes = {}, set()
    for final in closed:
        binding = next(b for b in bindings if b['attempt'] == final['attempt'])
        bridge = binding['bridge']
        invocation = next(i for i in pending if i['attempt'] == final['attempt'])
        saved = binding['host_receipt']
        start = decode(saved['stdout'])['result']
        dispatch = final['host_dispatch']
        require(invocation['prepare_sha256'] == digest((root / 'prepare.json').read_bytes())
                and saved['prelaunch_receipt_sha256'] == invocation['receipt_sha256']
                and digest(encoded(saved)) == binding['host_receipt_sha256']
                and saved['launch_state'] == 'observed' and saved['readback_status'] == 'observed',
                'invocation/host receipt binding changed')
        require(start['dispatchId'] == bridge['dispatch'] == dispatch['id']
                and start['taskId'] == bridge['task'] == dispatch['taskId']
                and start['runId'] == bridge['run'] == dispatch['runId']
                and bridge['process'] == dispatch['processIncarnation']
                and final['outcome'] == dispatch['status']
                and final['outcome'] in ('completed', 'failed', 'cancelled'),
                'terminal host identity/outcome changed')
        positions = [next(e['sequence'] for e in history if e['kind'] == kind
                          and e['value'].get('attempt') == final['attempt'])
                     for kind in ('pending', 'binding', 'closed')]
        require(positions == sorted(set(positions)), 'attempt event order changed')
        prefix = (root / binding['prefix']).read_bytes()
        data = (root / final['source']).read_bytes()
        require(digest(prefix) == bridge['prefix_sha256'] and len(prefix) == bridge['prefix_bytes']
                and data.startswith(prefix) and digest(data) == final['sha256'] and len(data) == final['bytes'],
                'captured source changed')
        key = (bridge['session'], bridge['turn'])
        require(key not in scopes, 'duplicate turn binding')
        scopes.add(key)
        single_turn(data, bridge['turn'])
        sample = read_usage(root / final['source'], final['sha256'], final['attempt'], bridge['turn'])
        require(sample['provenance']['session_id'] == bridge['session'] and sample['usage']['coverage'] == 'complete',
                'source identity/coverage changed')
        for response in sample['provenance']['responses']:
            key = 'codex/request/' + response['response_id']
            require(key not in result, 'duplicate response across participants')
            result[key] = {'session': bridge['session'], 'counts': response['usage'],
                           'attempt': final['attempt'], 'actor': roster[final['attempt']]['actor']}
    require(result, 'empty response union')
    return result


def usage_policy(attempts, max_raw_tokens, history, responses):
    """Pure policy over decoded history and an already validated response union.

    This does not establish accounting completeness or authorize launch. The
    caller owns evidence validation; prelaunch soft-stop checks remain separate.
    """
    total = sum(item['counts']['total_tokens'] for item in responses.values())
    reasons = []
    if total > max_raw_tokens:
        reasons.append('budget_exceeded')
    if any(e['kind'] == 'halt' for e in history):
        reasons.append('halted')
    latest = {a['actor']: a['id'] for a in attempts}
    if any(e['kind'] == 'closed' and e['value']['attempt'] in latest.values()
           and e['value']['outcome'] != 'completed' for e in history):
        reasons.append('attempt_failed')
    return total, {'verdict': reasons[0] if reasons else 'within_budget',
                   'reasons': reasons, 'max_raw_tokens': max_raw_tokens,
                   'success_eligible': not reasons}


def terminal_value(root, p, history):
    """Accounting completeness is not policy acceptance. No host/model calls.

    Receipt schema is independent of the immutable v2 prepare/event envelope.
    Legacy v2 settlements have only prepare_sha256/responses/raw_total.
    """
    require(p['limits'] == decode((root / 'prepare.json').read_bytes())['limits'],
            'immutable limits changed')
    union = observed_union(root, p, history)
    total, policy = usage_policy(p['attempts'], p['limits']['max_raw_tokens'], history, union)
    return {'receipt_version': 1, 'accounting_status': 'complete',
            'prepare_sha256': digest((root / 'prepare.json').read_bytes()),
            'responses': union, 'raw_total': total, 'policy': policy}


def terminal_receipt(root, p, history):
    receipts = [e for e in history if e['kind'] == 'settlement']
    require(len(receipts) == 1 and receipts[0] == history[-1],
            'exact terminal accounting receipt required; missing, duplicated or nonterminal')
    expected = terminal_value(root, p, history)
    actual = receipts[0]['value']
    if 'receipt_version' not in actual:
        require(encoded(actual) == encoded({k: expected[k] for k in ('prepare_sha256', 'responses', 'raw_total')}),
                'legacy settlement forged')
        # Old receipts never certified failed/halted/budget-exceeded success.
    else:
        require(encoded(actual) == encoded(expected), 'terminal accounting/policy receipt forged')
    return receipts[0], expected


def settle(root, p):
    history = events(root)
    for event in history:
        if event['kind'] == 'closed':
            final = event['value']
            binding = next(e['value'] for e in history if e['kind'] == 'binding'
                           and e['value']['attempt'] == final['attempt'])
            require(digest(Path(binding['bridge']['source']).read_bytes()) == final['sha256'],
                    'late source append/change after close; cannot settle')
    if any(e['kind'] == 'settlement' for e in history):
        return terminal_receipt(root, p, history)[0]  # Verify, never append duplicates.
    return append(root, 'settlement', terminal_value(root, p, history))


def accounting_record(record, base, event):
    """Derive usage/failure only. Never manufacture success or independent review."""
    result = copy.deepcopy(record)
    root, p = prepared(result, base)
    actual, value = terminal_receipt(root, p, events(root))
    require(actual == event, 'wrong terminal receipt')
    ref = 'measurement-terminal'
    path = root / ('event-%06d.json' % event['sequence'])
    evidence = {'ref': str(path), 'file': str(path), 'sha256': digest(encoded(event)),
                'kind': 'host' if record['label'] == 'real' else 'synthetic'}
    require(ref not in result['evidence'] or result['evidence'][ref] == evidence,
            'terminal evidence reference collision')
    result['evidence'][ref] = evidence
    result['measurement']['settlement_sha256'] = evidence['sha256']
    entries = []
    for key, item in value['responses'].items():
        counts = item['counts']
        entries.append({'provider': 'codex', 'kind': 'request', 'id': key.split('/')[-1],
                        'session': item['session'], 'tokenizer': 'unknown',
                        'input': counts['input_tokens'], 'output': counts['output_tokens'],
                        'cached_input': counts['cached_input_tokens'],
                        'reasoning': counts['reasoning_output_tokens'],
                        'cached_in_input': True, 'reasoning_in_output': True, 'evidence': ref})
    result['usage'] = {'coverage': 'complete', 'expected': list(value['responses']), 'entries': entries}
    if not value['policy']['success_eligible']:
        goal = result['goal']
        goal.update(status='failed', known_failure=True,
                    assessment={'revision': goal['revision'], 'scope': goal['scope'],
                                'verdict': 'failed', 'basis': 'team_checks',
                                'actor': goal['current_owner'], 'evidence': ref})
    return result


def validate(record, base, final=False):
    root, p = prepared(record, base)
    history = events(root)
    terminal = any(e['kind'] == 'settlement' for e in history)
    require(not terminal or final, 'terminal accounting receipt exists but record binding is missing')
    if final:
        event, receipt = terminal_receipt(root, p, history)
        require(record['measurement']['settlement_sha256'] == digest(encoded(event)), 'settlement hash mismatch')
        if not receipt['policy']['success_eligible']:
            require(record['goal']['status'] == 'failed' and record['goal']['known_failure'] is True,
                    'complete accounting is non-success: ' + ', '.join(receipt['policy']['reasons']))
            require((record['goal'].get('assessment') or {}).get('verdict') != 'succeeded',
                    'policy failure cannot claim successful overall acceptance')
        union = observed_union(root, p, history)
        for task in record['tasks']:
            require(any(e['kind'] == 'binding' and e['value']['bridge']['task'] == task['id']
                        and e['value']['bridge']['dispatch'] == task['current_dispatch']
                        and next(a['actor'] for a in p['attempts'] if a['id'] == e['value']['attempt'])
                            == task['execution']['actor'] for e in history), 'record Task/Dispatch not bound')
        require(receipt['responses'] == union and receipt['prepare_sha256'] == digest((root / 'prepare.json').read_bytes())
                and receipt['raw_total'] == sum(x['counts']['total_tokens'] for x in union.values()), 'settlement forged')
        usage = record['usage']
        require(usage['coverage'] == 'complete' and len(usage['expected']) == len(union)
                and set(usage['expected']) == set(union) and len(usage['entries']) == len(union), 'usage union incomplete/duplicated')
        seen = set()
        for entry in usage['entries']:
            key = '/'.join(entry[k] for k in ('provider', 'kind', 'id'))
            require(key in union and key not in seen, 'unexpected/duplicate response')
            seen.add(key)
            expected = union[key]
            require(entry['session'] == expected['session'], 'wrong usage session')
            for name, source in [('input', 'input_tokens'), ('output', 'output_tokens'),
                                 ('cached_input', 'cached_input_tokens'), ('reasoning', 'reasoning_output_tokens')]:
                require(type(entry[name]) is int and entry[name] == expected['counts'][source], 'raw usage missing or forged')
    result = {'version': VERSION, 'prepare_sha256': digest((root / 'prepare.json').read_bytes())}
    if final:
        result.update(accounting_status='complete', policy=receipt['policy'])
    return result


def retained_files(record, base):
    root, _ = prepared(record, base)
    names = ['prepare.json', 'capture-probe']
    history = events(root)
    names += ['event-%06d.json' % i for i in range(len(history))]
    for event in history:
        if event['kind'] == 'binding':
            names.append(event['value']['prefix'])
        if event['kind'] in ('closed', 'partial'):
            names.append(event['value']['source'])
    return [(root / name, digest((root / name).read_bytes())) for name in names]


def amend(root, p, path):
    history = events(root)
    require(not any(e['kind'] == 'settlement' for e in history), 'already settled')
    pending = {e['value']['attempt'] for e in history if e['kind'] == 'pending'}
    closed = {e['value']['attempt'] for e in history if e['kind'] == 'closed'}
    require(pending <= closed, 'cannot authorize extra work while prior work remains open')
    extra = decode(path.read_bytes())
    require(isinstance(extra, list) and extra, 'new attempts required')
    combined = p['attempts'] + extra
    validate_attempts(combined, {a['actor'] for a in combined})
    require(len(combined) <= p['limits']['max_attempts'], 'attempt budget exceeded')
    return append(root, 'amendment', {'attempts': extra})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'bind', 'close', 'settle', 'finalize', 'amend'))
    parser.add_argument('--record', type=Path, required=True)
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--ledger', type=Path)
    parser.add_argument('--orca', default='orca')
    parser.add_argument('--probe-dispatch')
    parser.add_argument('--attempt')
    parser.add_argument('--output-record', type=Path,
                        help='finalize only: new sibling record; never overwrite source/history')
    args = parser.parse_args(argv)
    try:
        require(args.output_record is None or (args.action == 'finalize'
                and args.output_record.resolve() != args.record.resolve()
                and args.output_record.resolve().parent == args.record.resolve().parent),
                'finalize output must be a distinct sibling record')
        if args.action == 'prepare':
            result = prepare(args.record, args.plan, args.ledger, args.orca, args.probe_dispatch)
        else:
            record = decode(args.record.read_bytes())
            root = (args.record.parent / record['measurement']['ledger']).resolve()
            with locked(root):
                root, p = prepared(record, args.record.parent)
                if args.action == 'amend':
                    result = amend(root, p, args.plan)
                elif args.action == 'bind':
                    result = bind(root, p, args.attempt, args.orca)
                elif args.action == 'close':
                    result = close_attempt(root, p, args.attempt, args.orca)
                else:
                    result = settle(root, p)
                if args.output_record is not None:
                    from record_check import check_record
                    derived = accounting_record(record, args.record.parent, result)
                    checked = check_record(derived, args.record.parent)
                    require(checked['ok'], 'final record rejected: ' + json.dumps(checked['errors']))
                    data = encoded(derived)
                    if args.output_record.exists():
                        require(args.output_record.read_bytes() == data, 'derived record already exists with different bytes')
                    else:
                        write_once(args.output_record, data)
            result = {'ok': True, 'receipt': result, 'sha256': digest(encoded(result))}
            if args.action in ('settle', 'finalize'):
                _, value = terminal_receipt(root, p, events(root))
                result.update(accounting_status='complete', policy=value['policy'])
                result['ok'] = value['policy']['success_eligible'] if args.action == 'settle' else True
        print(json.dumps(result))
        return 0 if result['ok'] else 1
    except (ValueError, OSError, KeyError, TypeError, AttributeError, StopIteration, sqlite3.Error, subprocess.SubprocessError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
