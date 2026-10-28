#!/usr/bin/env python3
"""Opt-in Codex PreToolUse guard; not an Orca server enforcement boundary."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import sys

# A direct bind or hook invocation must not create caches in the managed skill.
sys.dont_write_bytecode = True
from completion_hook import state_parent
from record_check import check_record, check_routing, read_json_snapshot


def deny(reason):
    return {'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny',
                                   'permissionDecisionReason': reason}}


def raw_launch(tool, data):
    command = data.get('command', data.get('cmd', data.get('code')))
    if tool not in ('Bash', 'exec_command', 'functions.exec', 'exec') or not isinstance(command, str):
        return False
    if tool in ('functions.exec', 'exec'):
        # Only a literal JSON-style cmd string can be safely inspected here.
        matches = re.findall(r'(?:\bcmd\b|"cmd")\s*:\s*("(?:\\.|[^"\\])*")', command)
        commands = []
        for match in matches:
            try:
                commands.append(json.loads(match))
            except ValueError:
                continue
    else:
        commands = [command]
    for command in commands:
        segments, start, quote, escaped = [], 0, None, False
        for index, char in enumerate(command):
            if escaped:
                escaped = False
            elif char == '\\' and quote != "'":
                escaped = True
            elif quote and char == quote:
                quote = None
            elif not quote and char in ("'", '"'):
                quote = char
            elif not quote and char in ';&|\n':
                segments.append(command[start:index])
                start = index + 1
        segments.append(command[start:])
        for segment in segments:
            try:
                part = shlex.split(segment, comments=True)
            except ValueError:
                continue
            if not part or Path(part[0]).name != 'orca':
                continue
            if part[1:3] in (['orchestration', 'worker-start'], ['orchestration', 'dispatch'], ['agent', 'launch']):
                return True
            if part[1:3] == ['worktree', 'create'] and any(arg == '--agent' or arg.startswith('--agent=') for arg in part[3:]):
                return True
    return False


def binding_path(home, session):
    if not isinstance(session, str) or not session or len(session) > 4096:
        raise ValueError('invalid Codex session ID')
    return Path(home) / 'state/company-routing' / (hashlib.sha256(session.encode()).hexdigest() + '.json')


def bind(home, session, decision, record, receipt_dir, expected=None):
    target = binding_path(home, session)
    parent = state_parent(target, create=True)
    lock = None
    try:
        lock = os.open('.routing-bind.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        old = None
        try:
            fd = os.open(target.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
            with os.fdopen(fd, 'rb') as existing:
                old = existing.read()
        except FileNotFoundError:
            pass
        if old is not None and (expected is None or hashlib.sha256(old).hexdigest() != expected):
            raise FileExistsError('session binding exists; exact prior hash required')
        if old is None and expected is not None:
            raise FileNotFoundError('expected prior session binding is absent')
        if old is not None:
            archive = target.name + '.' + hashlib.sha256(old).hexdigest()
            try:
                fd = os.open(archive, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
            except FileExistsError:
                fd = os.open(archive, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
                with os.fdopen(fd, 'rb') as saved:
                    if saved.read() != old:
                        raise ValueError('existing binding archive differs')
            else:
                with os.fdopen(fd, 'wb') as saved:
                    saved.write(old)
                    saved.flush()
                    os.fsync(saved.fileno())
        name = target.name if old is None else '.routing-' + os.urandom(16).hex()
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        with os.fdopen(fd, 'w', encoding='utf-8') as out:
            json.dump({'session_id': session, 'decision': str(Path(decision).resolve()),
                       'record': str(Path(record).resolve()), 'receipt_dir': str(Path(receipt_dir).resolve())}, out)
            out.flush()
            os.fsync(out.fileno())
        if old is not None:
            os.replace(name, target.name, src_dir_fd=parent, dst_dir_fd=parent)
        os.fsync(parent)
    finally:
        if lock is not None:
            os.close(lock)
        os.close(parent)


def guard(event, scope_path):
    if not scope_path or event.get('hook_event_name') != 'PreToolUse':
        return {}
    tool, data = event.get('tool_name'), event.get('tool_input')
    data = data if isinstance(data, dict) else {}
    raw_orca = raw_launch(tool, data)
    native = tool in ('spawn_agent', 'Agent')
    if not raw_orca and not native:
        return {}
    scope, error, _ = read_json_snapshot(Path(scope_path))
    if error or not isinstance(scope, dict):
        return deny('Company routing scope cannot be read.')
    if scope.get('session_id') != event.get('session_id'):
        return {}
    decision_path, record_path = scope.get('decision'), scope.get('record')
    if not isinstance(decision_path, str) or not isinstance(record_path, str):
        return deny('Company routing scope lacks decision or current record.')
    decision_path, record_path = Path(decision_path), Path(record_path)
    decision, error, decision_hash = read_json_snapshot(decision_path)
    if error:
        return deny('Company routing decision cannot be read.')
    record, error, record_hash = read_json_snapshot(record_path)
    if error:
        return deny('Company routing record cannot be read.')
    if native:
        record_check = check_record(record, record_path.parent)
        result = check_routing(decision, decision_path.parent, prelaunch=True)
        binding = decision.get('binding', {}) if isinstance(decision, dict) else {}
        goal = record.get('goal', {}) if isinstance(record, dict) else {}
        tasks = record.get('tasks', []) if isinstance(record, dict) else []
        task = next((item for item in tasks if isinstance(item, dict) and item.get('id') == binding.get('task')), None) if isinstance(tasks, list) and isinstance(binding, dict) else None
        if (not record_check['ok'] or not isinstance(goal, dict) or task is None or binding.get('planned') is not False
                or binding.get('scope') != goal.get('scope') or binding.get('revision') != goal.get('revision')
                or binding.get('attempt') != task.get('current_dispatch')):
            return deny('Native helper decision must bind an existing current parent Task and Dispatch.')
    else:
        result = check_routing(decision, decision_path.parent, record, record_path.parent, prelaunch=True)
    if not result['ok'] or result['label'] != 'real':
        return deny('Company routing prelaunch check failed.')
    if raw_orca:
        return deny('Use the checked Company launcher for Orca worker-start.')
    selected = result['receipt']['selected']
    if selected['route'] != 'codex' or data.get('model') != selected['model'] or data.get('reasoning_effort') != selected['effort']:
        return deny('Native helper model and effort must match the checked decision.')
    message = data.get('message')
    binding = decision.get('binding', {}) if isinstance(decision, dict) else {}
    if not isinstance(message, str) or not isinstance(binding, dict) or binding.get('spec_sha256') != hashlib.sha256(message.encode('utf-8')).hexdigest():
        return deny('Native helper message must match the checked decision.')
    # A native helper is not an Orca Task. No Task or Dispatch identity is synthesized here.
    tool_id, receipt_dir = event.get('tool_use_id'), scope.get('receipt_dir')
    if not isinstance(tool_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', tool_id) or not isinstance(receipt_dir, str):
        return deny('Native helper receipt path is unavailable.')
    result['receipt'].update(decision_sha256=decision_hash, record_sha256=record_hash, native_tool_use_id=tool_id)
    try:
        with (Path(receipt_dir) / (tool_id + '.json')).open('x', encoding='utf-8') as out:
            json.dump(result, out, ensure_ascii=False, indent=2)
            out.write('\n')
    except OSError:
        return deny('Native helper prelaunch receipt could not be retained.')
    return {}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command')
    register = sub.add_parser('bind')
    register.add_argument('--session', required=True)
    register.add_argument('--decision', required=True)
    register.add_argument('--record', required=True)
    register.add_argument('--receipt-dir', required=True)
    register.add_argument('--expected-sha256')
    args = parser.parse_args()
    home = Path(os.environ.get('SEJONG_HOME', str(Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))) / 'sejong'))).expanduser()
    if args.command == 'bind':
        bind(home, args.session, args.decision, args.record, args.receipt_dir, args.expected_sha256)
        return
    event = json.load(sys.stdin)
    override = os.environ.get('COMPANY_ROUTING_SCOPE')
    if override:
        scope = override
    else:
        try:
            target = binding_path(home, event.get('session_id'))
            parent = state_parent(target)
            try:
                fd = os.open(target.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
                os.close(fd)
            finally:
                os.close(parent)
            scope = str(target)
        except FileNotFoundError:
            scope = None
    print(json.dumps(guard(event, scope)))


if __name__ == '__main__':
    main()
