#!/usr/bin/env python3
"""Run a checked new Orca worker-start; this is not a server enforcement boundary."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

# Select Python's normal cache prefix before importing Company modules.
# Restrict this to the CLI process; callers importing a module are unchanged.
if __name__ == "__main__":
    import os as _os
    import sys as _sys
    _sys.pycache_prefix = _os.path.join(_os.path.abspath(_os.path.expanduser("~")), ".cache", "agent-company", "python")

from record_check import check_routing, read_json_snapshot


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--decision', required=True, type=Path)
    parser.add_argument('--record', required=True, type=Path)
    parser.add_argument('--receipt', required=True, type=Path)
    parser.add_argument('--result', required=True, type=Path)
    parser.add_argument('--from', dest='sender', required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--spec')
    mode.add_argument('--task')
    parser.add_argument('--retry-of')
    parser.add_argument('--run')
    parser.add_argument('--worktree', required=True)
    parser.add_argument('--name')
    parser.add_argument('--repo')
    parser.add_argument('--base-branch')
    parser.add_argument('--setup', choices=('run', 'skip', 'inherit'))
    parser.add_argument('--display-name')
    parser.add_argument('--task-title')
    parser.add_argument('--parent')
    parser.add_argument('--terminal')
    parser.add_argument('--reuse-dispatch')
    parser.add_argument('--origin-receipt', type=Path)
    args = parser.parse_args(argv)
    if args.retry_of and not args.task:
        parser.error('--retry-of requires --task')
    if args.task and not args.run:
        parser.error('--task requires an explicit --run')
    if args.task and any((args.terminal, args.reuse_dispatch, args.origin_receipt, args.task_title)):
        parser.error('existing Task cannot use new-task title or terminal reuse')
    decision, error, decision_hash = read_json_snapshot(args.decision)
    if error:
        print(json.dumps({'ok': False, 'errors': [error]}))
        return 2
    record, error, record_hash = read_json_snapshot(args.record)
    if error:
        print(json.dumps({'ok': False, 'errors': [error]}))
        return 2
    result = check_routing(decision, args.decision.parent, record, args.record.parent, prelaunch=True)
    result['receipt'].update(decision_sha256=decision_hash, record_sha256=record_hash)
    if result['label'] != 'real':
        result['ok'] = False
        result['errors'].append({'path': '$.label', 'code': 'synthetic_launch',
                                 'message': 'Synthetic routing decisions cannot launch a worker'})
    binding = decision.get('binding', {}) if isinstance(decision, dict) else {}
    spec_hash = hashlib.sha256(args.spec.encode('utf-8')).hexdigest() if args.spec is not None else None
    if args.spec is not None and (not isinstance(binding, dict) or binding.get('spec_sha256') != spec_hash):
        result['ok'] = False
        result['errors'].append({'path': '$.binding.spec_sha256', 'code': 'spec_binding',
                                 'message': 'The exact worker specification must match the decision'})
    if args.spec is not None and (not isinstance(binding, dict) or binding.get('planned') is not True):
        result['ok'] = False
        result['errors'].append({'path': '$.binding.planned', 'code': 'planned_required',
                                 'message': 'worker-start --spec creates a new Task and requires a planned intent'})
    if not isinstance(binding, dict) or binding.get('parent_task') != args.parent:
        result['ok'] = False
        result['errors'].append({'path': '$.binding.parent_task', 'code': 'parent_binding',
                                 'message': 'Parent Task must match the checked decision'})
    result['receipt']['spec_sha256'] = spec_hash
    if (args.run is not None or 'run' in binding or 'run' in record) and (
            not args.run or binding.get('run') != args.run or record.get('run') != args.run):
        result['ok'] = False
        result['errors'].append({'path': '$.binding.run', 'code': 'run_binding', 'message': 'Run must match decision and current record'})
    selected = result['receipt']['selected']
    if selected['route'] != 'codex':
        result['ok'] = False
        result['errors'].append({'path': '$.selected.route', 'code': 'unsupported_launch_route',
                                 'message': 'This launcher supports a new Codex worker only'})
    if not result['ok']:
        print(json.dumps(result))
        return 1
    if args.task:
        current = next((item for item in record['tasks'] if item['id'] == args.task), None)
        if (binding.get('task') != args.task or current is None or
                (args.retry_of and (binding.get('planned') is not False or binding.get('attempt') != args.retry_of or
                 current['current_dispatch'] != args.retry_of or current['execution']['state'] != 'settled' or
                 (current['execution'].get('result') or {}).get('outcome') != 'failed')) or
                (not args.retry_of and (binding.get('planned') is not True or current['current_dispatch'] != 'planned:' + args.task))):
            print(json.dumps({'ok': False, 'error': 'Task or retry binding does not match current record'}))
            return 1
        probe = subprocess.run(['orca', 'orchestration', 'task-list', '--run', args.run, '--from', args.sender, '--json'], check=False, capture_output=True, text=True)
        try:
            envelope = json.loads(probe.stdout)
            listed = envelope['result']
            task = next(item for item in listed['tasks'] if item['id'] == args.task)
            spec_hash = hashlib.sha256(task['spec'].encode('utf-8')).hexdigest()
            valid = (probe.returncode == 0 and envelope.get('ok') is True and listed['runId'] == args.run and
                     task['run_id'] == args.run and task['parent_id'] == args.parent and
                     binding.get('spec_sha256') == spec_hash and task['status'] in (('failed',) if args.retry_of else ('pending', 'ready')))
            if args.retry_of:
                latest_probe = subprocess.run(['orca', 'orchestration', 'dispatch-show', '--task', args.task, '--from', args.sender, '--json'], check=False, capture_output=True, text=True)
                latest = json.loads(latest_probe.stdout)
                failed_probe = subprocess.run(['orca', 'orchestration', 'worker-show', '--dispatch', args.retry_of, '--json'], check=False, capture_output=True, text=True)
                failed = json.loads(failed_probe.stdout)
                dispatch = failed['result']['dispatch']
                valid = valid and latest_probe.returncode == 0 and latest.get('ok') is True and latest['result']['dispatch']['id'] == args.retry_of and failed_probe.returncode == 0 and failed.get('ok') is True and dispatch['id'] == args.retry_of and dispatch['taskId'] == args.task and dispatch['runId'] == args.run and dispatch['status'] == 'failed'
        except (KeyError, TypeError, ValueError, StopIteration, AttributeError):
            valid = False
        if not valid:
            print(json.dumps({'ok': False, 'error': 'Current host Task specification or failed Dispatch mismatch'}))
            return 1
        result['receipt']['spec_sha256'] = spec_hash
        result['receipt']['task_list'] = envelope
        if args.retry_of:
            result['receipt']['failed_dispatch'] = failed
            result['receipt']['latest_dispatch'] = latest
    reuse = any((args.terminal, args.reuse_dispatch, args.origin_receipt))
    if reuse:
        if not all((args.terminal, args.reuse_dispatch, args.origin_receipt)) or args.worktree in ('new-child', 'new-top-level'):
            print(json.dumps({'ok': False, 'error': 'reuse requires terminal, dispatch and original receipt'}))
            return 1
        origin, error, origin_hash = read_json_snapshot(args.origin_receipt)
        evidence = decision.get('reuse_evidence', {})
        source = decision.get('evidence', {}).get(evidence.get('unchanged_evidence'), {}) if isinstance(evidence, dict) else {}
        if error or not isinstance(origin, dict) or not isinstance(evidence, dict) or evidence.get('origin_sha256') != origin_hash:
            print(json.dumps({'ok': False, 'error': 'reuse origin receipt missing or hash mismatch'}))
            return 1
        try:
            envelope = json.loads(origin['stdout']) if isinstance(origin.get('stdout'), str) else origin
            original = envelope['result']
            original_effective = original['launch']['effective']
            original_incarnation = original['prompt']['processIncarnation']
            probe = subprocess.run(['orca', 'orchestration', 'worker-show', '--dispatch', args.reuse_dispatch, '--json'], check=False, capture_output=True, text=True)
            observed = json.loads(probe.stdout)
            live = observed['result']
            terminal = live['terminal']
            dispatch = live['dispatch']
            unchanged = source.get('reuse_binding', {})
            evidence_bytes = (args.decision.parent / source['file']).read_bytes()
            observed_at = datetime.fromisoformat(unchanged['observed_at'].replace('Z', '+00:00'))
            valid_until = datetime.fromisoformat(unchanged['valid_until'].replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            valid = (probe.returncode == 0 and observed.get('ok') is True and envelope.get('ok') is True and original.get('dispatchId') == args.reuse_dispatch
                     and any(effect.get('kind') == 'terminal' and effect.get('id') == args.terminal for effect in original['effects'])
                     and terminal.get('handle') == args.terminal and terminal.get('incarnationId') == original_incarnation
                     and dispatch.get('assigneeHandle') == args.terminal and dispatch.get('processIncarnation', '').endswith(':' + original_incarnation)
                     and live['observation'].get('status') == 'live' and live['observation'].get('exactWorker') is True
                     and live['projection']['liveness'].get('verdict') == 'live'
                     and original_effective.get('agent') == 'codex' and original_effective.get('model') == selected['model']
                     and original_effective.get('effort') == selected['effort'] and isinstance(source, dict)
                     and source.get('kind') == 'host' and isinstance(source.get('file'), str) and isinstance(source.get('sha256'), str)
                     and hashlib.sha256(evidence_bytes).hexdigest() == source['sha256'] and json.loads(evidence_bytes) == unchanged
                     and unchanged.get('dispatch') == args.reuse_dispatch and unchanged.get('terminal') == args.terminal
                     and unchanged.get('incarnation') == original_incarnation and unchanged.get('settings_unchanged') is True
                     and observed_at.tzinfo is not None and valid_until.tzinfo is not None and observed_at <= now <= valid_until)
        except (AttributeError, KeyError, TypeError, ValueError, OSError):
            valid = False
        if not valid:
            print(json.dumps({'ok': False, 'error': 'reuse source, process incarnation, settings or live observation mismatch'}))
            return 1
        result['receipt']['reuse'] = {'origin_sha256': origin_hash, 'worker_show': live,
                                      'limits': 'Original effective launch and current process observation; not current provider model readback.'}
        command = ['orca', 'orchestration', 'worker-start', '--from', args.sender, '--spec', args.spec,
                   '--worktree', args.worktree, '--terminal', args.terminal, '--json']
    else:
        command = ['orca', 'orchestration', 'worker-start', '--from', args.sender, '--task' if args.task else '--spec', args.task or args.spec,
                   '--worktree', args.worktree, '--agent', 'codex', '--model', selected['model'],
                   '--effort', selected['effort'], '--json']
    if args.run:
        command.extend(('--run', args.run))
    if args.retry_of:
        command.extend(('--retry-of', args.retry_of))
    if args.task_title:
        command.extend(('--task-title', args.task_title))
    if args.parent:
        command.extend(('--parent', args.parent))
    for flag, value in (('--name', args.name), ('--repo', args.repo), ('--base-branch', args.base_branch),
                        ('--setup', args.setup), ('--display-name', args.display_name)):
        if value is not None:
            if args.worktree not in ('new-child', 'new-top-level'):
                print(json.dumps({'ok': False, 'error': 'creation options require a new worktree'}))
                return 1
            command.extend((flag, value))
    result['receipt']['launch_argv'] = command
    with args.receipt.open('x', encoding='utf-8') as receipt:
        json.dump(result, receipt, ensure_ascii=False, indent=2)
        receipt.write('\n')
        receipt.flush()
        os.fsync(receipt.fileno())
    with args.result.open('x', encoding='utf-8') as host_receipt:
        host = subprocess.run(command, check=False, capture_output=True, text=True)
        status, reason = ('failed', 'host returned nonzero') if host.returncode else ('unverified', 'host result lacks required readback')
        try:
            envelope = json.loads(host.stdout)
            payload = envelope['result']
            if host.returncode == 0 and envelope.get('ok') is False:
                status, reason = 'failed', 'host returned an unsuccessful result'
            elif host.returncode == 0 and envelope.get('ok') is True and isinstance(payload.get('taskId'), str) and payload['taskId'] and isinstance(payload.get('dispatchId'), str) and payload['dispatchId']:
                if args.task and (payload['taskId'] != args.task or payload['dispatchId'] == args.retry_of):
                    status, reason = 'failed', 'host Task or Dispatch differs from checked identity'
                elif args.run and payload.get('runId') != args.run:
                    status, reason = ('unverified', 'host Run identity missing') if payload.get('runId') is None else ('failed', 'host Run identity differs')
                elif reuse:
                    effects = payload.get('effects')
                    if isinstance(effects, list) and any(isinstance(item, dict) and item.get('kind') == 'terminal' and item.get('id') == args.terminal for item in effects):
                        status, reason = 'observed', 'host IDs and reused terminal observed; model and effort remain prior evidence'
                else:
                    effective = payload.get('launch', {}).get('effective')
                    if isinstance(effective, dict) and all(effective.get(field) is not None for field in ('agent', 'model', 'effort')):
                        if effective.get('agent') == 'codex' and effective.get('model') == selected['model'] and effective.get('effort') == selected['effort']:
                            status, reason = 'observed', 'host IDs and effective launch settings observed'
                        else:
                            status, reason = 'failed', 'host effective launch settings differ from checked selection'
        except (ValueError, KeyError, TypeError, AttributeError):
            pass
        json.dump({'decision_sha256': decision_hash, 'prelaunch_receipt_sha256': hashlib.sha256(args.receipt.read_bytes()).hexdigest(),
                   'exit_code': host.returncode, 'readback_status': status, 'readback_reason': reason,
                   'stdout': host.stdout, 'stderr': host.stderr}, host_receipt, ensure_ascii=False, indent=2)
        host_receipt.write('\n')
        host_receipt.flush()
        os.fsync(host_receipt.fileno())
    sys.stdout.write(host.stdout)
    sys.stderr.write(host.stderr)
    if status != 'observed':
        sys.stderr.write('Routing launch readback ' + status + ': ' + reason + '; inspect the preserved host receipt before any recovery.\n')
    return 0 if status == 'observed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
