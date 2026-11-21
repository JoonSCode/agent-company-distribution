#!/usr/bin/env python3
"""Fixed sequential synthetic-TASK canary driver; no provider execution engine.

Requires caller-prepared, honestly sourced record/routing evidence. Never imports
unit-test fixtures or manufactures provider usage. Launch is an explicit action.
The fixed reviewer prompt checks the proposed constant. The driver verifies
actual fixed final answers; final task evidence still needs artifact bindings.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import sqlite3
from contextlib import closing

from measurement_lifecycle import (ADAPTER, decode, digest, encoded, require, write_once,
    prepared, timestamp, events, append, locked, runtime, host, close_attempt,
    SQLITE_HOST, SOURCE_CONTRACT, SOURCE_CONTRACT_268, worker_show, require_fresh_codex_worker, require_268_start)

SCRIPTS = Path(__file__).resolve().parent
FIXTURE = SCRIPTS.parent / 'assets/measurement-canary.json'


def command(args):
    fixture = decode(FIXTURE.read_bytes())
    record = decode(args.record.read_bytes())
    require(record['measurement']['version'] == 2 and record['measurement']['mode'] == 'required', 'explicit v2 record required')
    require(record['measurement']['expected_actors'] == fixture['actors'], 'exact canary actor roster required')
    require(record['measurement']['boundary'] == fixture['boundary'], 'exact new-experiment boundary required')
    require(record['goal']['current_owner'] == 'coordinator', 'model coordinator must be accounted')
    decisions = {}
    for actor in fixture['actors']:
        path = args.decisions / (actor + '.json')
        decision = decode(path.read_bytes())
        require(decision['label'] == 'real' and decision['binding']['planned'] is True
                and decision['binding']['spec_sha256'] == digest(fixture['prompts'][actor].encode()),
                'decision must bind the exact canary prompt and observed live routing evidence')
        decisions[actor] = decision
    from native_operations import pinned
    from native_storage import bound_enrollment
    reference = {'path': str(args.enrollment_request.absolute()), 'sha256': args.expect_enrollment_sha256}
    ep, _ = pinned(reference, Path.cwd())
    enrollment, _, _, _ = bound_enrollment(ep)
    require(args.record.absolute() == Path(enrollment['run']) / enrollment['record'], 'canary canonical record differs')
    storage_flags = ['--enrollment-request', str(ep), '--expect-enrollment-sha256', reference['sha256']]
    base = [sys.executable, '-B']
    if args.action == 'prepare':
        sqlite_host = host(args.orca, 'status')['runtime']['appVersion'] == SQLITE_HOST
        contract_path = SOURCE_CONTRACT_268 if sqlite_host else SOURCE_CONTRACT
        source_name = decode(contract_path.read_bytes())['source_name']
        hooks = args.hooks or args.database.parent / 'agent-hooks' / ('last-status.db' if sqlite_host else 'last-status.json')
        source = args.host_source or Path('/Applications/Orca.app/Contents/Resources/app.asar.unpacked/out/main/chunks') / source_name
        plan = {'adapter': ADAPTER, 'collector': {'database': str(args.database), 'hooks': str(hooks),
                'host_source': str(source), 'sample_session': args.sample_session, 'sample_turn': args.sample_turn},
                'attempts': [{'id': actor, 'actor': actor, 'provider': 'codex', 'ordinal': 1, 'retry_of': None,
                              'decision_sha256': digest((args.decisions / (actor + '.json')).read_bytes()),
                              'spec_sha256': decisions[actor]['binding']['spec_sha256']} for actor in fixture['actors']],
                'limits': fixture['limits']}
        plan_path = args.record.parent / 'canary-plan.json'
        write_once(plan_path, encoded(plan), reference)
        return base + [str(SCRIPTS / 'measurement_lifecycle.py'), 'prepare', '--record', str(args.record),
                       '--plan', str(plan_path), '--ledger', str(args.record.parent / 'measurement-ledger'),
                       '--orca', args.orca, *storage_flags]
    if args.action == 'launch':
        require(args.authorize_live, 'launch requires explicit --authorize-live; no automatic provider calls')
        require(args.actor in fixture['actors'], 'explicit canary actor required')
        binding = decisions[args.actor]['binding']
        require(binding.get('run'), 'exact host run binding required')
        result = base + [str(SCRIPTS / 'routing_launch.py'), '--record', str(args.record),
                        '--decision', str(args.decisions / (args.actor + '.json')), '--orca', args.orca,
                        '--measurement-attempt', args.actor, '--spec', fixture['prompts'][args.actor],
                        '--receipt', str(args.record.parent / ('launch-' + args.actor + '.json')),
                        '--result', str(args.record.parent / ('host-' + args.actor + '.json')),
                        '--from', args.sender, '--worktree', args.worktree, '--run', binding['run'],
                        '--start-timeout', '60', '--declared-billing', 'subscription', '--declared-spend', '0', *storage_flags]
        if binding.get('parent_task'):
            result += ['--parent', binding['parent_task']]
        return result
    result = base + [str(SCRIPTS / 'measurement_lifecycle.py'), args.action, '--record', str(args.record), '--orca', args.orca, *storage_flags]
    if args.actor:
        result += ['--attempt', args.actor]
    return result


def stop_owned(root, prep, attempt, executable, reason):
    """Fence ONLY this saved accepted dispatch. A stop request is not a proven stop."""
    with locked(root) as capability:
        append(root, 'halt', {'attempt': attempt, 'reason': reason,
                             'hard_provider_deadline': False}, capability)
    result = {'attempt': attempt, 'state': 'unknown', 'hard_provider_deadline': False}
    try:
        pending = [e for e in events(root) if e['kind'] == 'pending' and e['value']['attempt'] == attempt]
        require(len(pending) == 1, 'no unique invocation; no dispatch may be guessed')
        saved = decode(Path(pending[0]['value']['result']).read_bytes())
        require(saved['launch_state'] == 'observed' and saved['readback_status'] == 'observed'
                and saved['prelaunch_receipt_sha256'] == pending[0]['value']['receipt_sha256'],
                'unknown acceptance; dispatch-scoped stop unavailable')
        start = decode(saved['stdout'])['result']
        app_version = prep['readiness']['app_version']
        require(runtime(executable, app_version) == prep['runtime'], 'runtime changed; stop refused')
        before = worker_show(executable, start['dispatchId'], app_version)
        d = before['dispatch']
        require(d['id'] == start['dispatchId'] and d['taskId'] == start['taskId']
                and d['runId'] == start['runId'] and d.get('processIncarnation'), 'stop identity mismatch')
        if app_version == SQLITE_HOST:
            require(before['worker']['state'] == 'ready'
                    and before['observation']['exactWorker'] is True
                    and before['observation']['status'] == 'live', 'exact live Codex terminal stop required')
            require_fresh_codex_worker(before, prep['runtime'])
            require_268_start(start, before)
        database = Path(prep['collector']['database']).resolve()
        with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as db:
            db.execute('BEGIN')
            row = db.execute('SELECT task_id, run_id, process_incarnation FROM dispatch_contexts WHERE id=?',
                             (d['id'],)).fetchall()
            if app_version == SQLITE_HOST:
                require(db.execute('SELECT 1 FROM dispatch_contexts WHERE creator_dispatch_id=? LIMIT 1',
                                   (d['id'],)).fetchone() is None, 'scoped canary stop would include helper dispatches')
        require(row == [(d['taskId'], d['runId'], d['processIncarnation'])], 'stop process binding mismatch')
        # Save intent first; never silently reissue an unknown stop mutation.
        with locked(root) as capability:
            append(root, 'stop_pending', {'attempt': attempt, 'dispatch': d['id'],
                                         'process': d['processIncarnation']}, capability)
        flags = ['--full'] if app_version == SQLITE_HOST else []
        stop_proc = subprocess.run([executable, 'orchestration', 'worker-stop', '--dispatch', d['id'], *flags, '--json'],
                                   check=False, capture_output=True, text=True, timeout=30)
        envelope = decode(stop_proc.stdout)
        stopped = envelope.get('result') or {}
        result.update(dispatch=d['id'], stop={k: stopped[k] for k in
                      ('dispatchId', 'state', 'processAction', 'alreadySettled', 'close', 'helpers', 'helperStopError')
                      if k in stopped},
                      stop_exit_code=stop_proc.returncode)
        after = worker_show(executable, d['id'], app_version)
        result.update(readback={'dispatch': after['dispatch'], 'worker': after.get('worker'),
                                'observation': after.get('observation')})
        require(stop_proc.returncode == 0 and envelope.get('ok') is True
                and runtime(executable, app_version) == prep['runtime'] and stopped.get('dispatchId') == d['id']
                and stopped.get('state') == 'stopped' and after['dispatch']['id'] == d['id']
                and after['dispatch']['taskId'] == d['taskId'] and after['dispatch']['runId'] == d['runId']
                and after['dispatch']['assigneePaneKey'] == d['assigneePaneKey']
                and after['dispatch']['processIncarnation'] == d['processIncarnation']
                and after.get('worker', {}).get('state') == 'stopped'
                and after.get('observation', {}).get('status') == 'exited',
                'scoped stop not proven by receipt and exit readback')
        if app_version == SQLITE_HOST:
            require(stopped.get('processAction') == 'closed_agent_terminal'
                    and not stopped.get('helpers') and not stopped.get('helperStopError'),
                    'exclusive canary terminal stop not proven')
        result['state'] = 'stopped'
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error, subprocess.SubprocessError) as exc:
        result['error'] = str(exc)
    # Best-effort final capture uses an existing exact binding only. Unbound sources
    # are never guessed, and partial/cancelled accounting cannot authorize another start.
    try:
        with locked(root) as capability:
            close_attempt(root, prep, attempt, executable, capability)
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error, subprocess.SubprocessError) as exc:
        result['accounting'] = 'partial/unbound: ' + str(exc)
    with locked(root) as capability:
        append(root, 'stop_observed', result, capability)
    return result


def accept_output(root, final, expected):
    """Fixed answer only; shell report/tool outputs are not the task answer."""
    data = (root / final['source']).read_bytes()
    require(digest(data) == final['sha256'], 'canary source hash changed')
    rows = [decode(line) for line in data.splitlines()]
    answers = [r['payload'] for r in rows if r.get('type') == 'response_item'
               and r['payload'].get('type') == 'message'
               and r['payload'].get('role') == 'assistant'
               and r['payload'].get('phase') == 'final_answer']
    require(len(answers) == 1 and answers[0].get('status') == 'completed',
            'one completed canary final answer required')
    content = answers[0].get('content', [])
    require(content and all(c.get('type') == 'output_text' for c in content)
            and ''.join(c['text'] for c in content) == expected, 'canary fixed output mismatch')
    ends = [r['payload'] for r in rows if r.get('type') == 'event_msg'
            and r['payload'].get('type') == 'task_complete']
    require(len(ends) == 1 and ends[0].get('last_agent_message') == expected,
            'canary native final answer mismatch')
    return expected


def drive_attempt(args, fixture):
    """One declared launch and bounded observation; no retries or extra model work."""
    record = decode(args.record.read_bytes())
    root, prep = prepared(record, args.record.parent)
    require(not any(e['kind'] == 'halt' for e in events(root)), 'canary halted')
    remaining = timestamp(prep['created_at']) + prep['limits']['deadline_seconds'] - time.time()
    deadline = time.monotonic() + min(fixture['turn_deadline_seconds'], remaining)
    require(deadline > time.monotonic(), 'run deadline expired before launch')
    args.action = 'launch'
    try:
        proc = subprocess.run(command(args), check=False, capture_output=True, text=True,
                              timeout=max(0.001, deadline - time.monotonic()))
        # A binding may lag acceptance. Observe only; never launch again.
        while time.monotonic() < deadline:
            history = events(root)
            pending = [e for e in history if e['kind'] == 'pending' and e['value']['attempt'] == args.actor]
            require(len(pending) == 1, 'checked launch did not persist an invocation')
            saved = decode(Path(pending[0]['value']['result']).read_bytes())
            require(saved['launch_state'] == 'observed', 'launch outcome unknown; no replay')
            if not any(e['kind'] == 'binding' and e['value']['attempt'] == args.actor for e in history):
                action = 'bind'
            else:
                action = 'close'
            observe = subprocess.run([sys.executable, '-B', str(SCRIPTS/'measurement_lifecycle.py'),
                        action, '--record', str(args.record), '--attempt', args.actor, '--orca', args.orca,
                        '--enrollment-request', str(args.enrollment_request), '--expect-enrollment-sha256', args.expect_enrollment_sha256],
                        check=False, capture_output=True, text=True,
                        timeout=max(0.001, deadline - time.monotonic()))
            if observe.returncode == 0 and action == 'close':
                final = next(e['value'] for e in events(root) if e['kind'] == 'closed' and e['value']['attempt'] == args.actor)
                require(final['outcome'] == 'completed', 'failed/cancelled attempt; stop all further starts')
                answer = accept_output(root, final, fixture['expected_outputs'][args.actor])
                return {'attempt': args.actor, 'state': 'closed', 'answer': answer,
                        'hard_provider_deadline': False}
            if observe.returncode != 0:
                error = decode(observe.stdout).get('error', 'observation failed')
                # A missing exact binding is never relaxed; wait within the same deadline.
                if action == 'close' and error not in ('attempt still running', 'native completion pending'):
                    raise ValueError(error)
            time.sleep(min(0.2, max(0, deadline-time.monotonic())))
        reason = 'turn/run observation deadline reached; requesting scoped stop, not claiming provider hard cap'
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        reason = str(exc)
    stopped = stop_owned(root, prep, args.actor, args.orca, reason)
    raise ValueError('canary halted; ' + json.dumps(stopped))


def run_canary(args):
    fixture = decode(FIXTURE.read_bytes())
    require(args.authorize_live, 'run requires --authorize-live')
    record = decode(args.record.read_bytes())
    root, prep = prepared(record, args.record.parent)
    require(prep['limits'] == fixture['limits'] and not events(root),
            'fixed canary requires exact limits and a fresh prepared ledger; no resume/retry')
    results = []
    for actor in fixture['order']:
        args.actor = actor
        results.append(drive_attempt(args, fixture))
    args.action = 'settle'
    proc = subprocess.run(command(args), check=False, capture_output=True, text=True, timeout=30)
    settlement = decode(proc.stdout)
    require(proc.returncode == 0 or settlement.get('accounting_status') == 'complete',
            'accounting incomplete: ' + proc.stdout)
    return {'ok': proc.returncode == 0, 'attempts': results, 'settlement': settlement,
            'hard_provider_deadline': False,
            'meaning': 'accounting lifecycle and fixed answers checked; final record artifact/acceptance bindings still required'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'run', 'launch', 'bind', 'close', 'settle'))
    parser.add_argument('--record', type=Path, required=True)
    parser.add_argument('--enrollment-request', type=Path, required=True)
    parser.add_argument('--expect-enrollment-sha256', required=True)
    parser.add_argument('--decisions', type=Path, required=True)
    parser.add_argument('--orca', default='orca')
    home = Path.home() / 'Library/Application Support/orca'
    parser.add_argument('--database', type=Path, default=home / 'orchestration.db')
    parser.add_argument('--hooks', type=Path, help='override the version-matched hook store path')
    parser.add_argument('--host-source', type=Path, help='override the version-matched installed source path')
    parser.add_argument('--sample-session', help='explicit historical host-named parser sample, not future identity')
    parser.add_argument('--sample-turn')
    parser.add_argument('--actor')
    parser.add_argument('--from', dest='sender', default='')
    parser.add_argument('--worktree', default='current')
    parser.add_argument('--authorize-live', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.action in ('launch', 'run'):
            require(args.sender, 'explicit host sender required')
            result = run_canary(args) if args.action == 'run' else drive_attempt(args, decode(FIXTURE.read_bytes()))
            print(json.dumps(result))
            return 0 if result.get('ok', True) else 1
        return subprocess.run(command(args), check=False, timeout=60).returncode
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
