#!/usr/bin/env python3
"""Check a prepared shell before agent-command delivery; never send input or launch.

Operator workflow only: source snapshots do not authenticate a live process.
Stdlib Python 3.13+. No provider, shell-settings or managed-install writes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import secrets
import sys
import time

sys.dont_write_bytecode = True
from record_check import unique_object, invalid_constant

FORMAT = 'company-shell-readiness/v1'
PREFIX = 'COMPANY_R2_READY_'
UPDATE_QUESTION = '[oh-my-zsh] Would you like to update? [Y/n]'
MAX_AGE_MS = 60000


def require(condition, message):
    if not condition:
        raise ValueError(message)


def observation(show, screen, handle, worktree, prompt, source='screen'):
    require(show.get('ok') is True and screen.get('ok') is True, 'host observation failed')
    terminal = show['result']['terminal']
    frame = screen['result']['terminal']
    identity = {key: terminal[key] for key in
                ('handle', 'ptyId', 'incarnationId', 'worktreeId', 'executionHostId')}
    require(all(isinstance(x, str) and x for x in identity.values()), 'unknown terminal identity')
    runtime = show['_meta']['runtimeId']
    require(isinstance(runtime, str) and runtime and runtime == screen['_meta']['runtimeId'],
            'runtime observation mismatch')
    require(identity['handle'] == handle == frame['handle'] and terminal['worktreePath'] == worktree,
            'terminal/worktree mismatch')
    require(terminal['connected'] is True and terminal['writable'] is True and
            terminal['orphaned'] is False and not terminal.get('agentIdentity'),
            'owned blank shell required; existing agent/disconnected terminal rejected')
    require(frame.get('source') == source and frame['status'] == 'running' and not frame.get('draft'),
            'current shell ' + source + ' required')
    require(all(isinstance(frame.get(key), str) and frame[key].isdecimal()
                for key in ('oldestCursor', 'nextCursor')), 'unknown stream cursor')
    lines = frame['tail']
    require(isinstance(lines, list) and lines and all(isinstance(x, str) for x in lines),
            'missing shell screen')
    require(not any(UPDATE_QUESTION in line for line in lines), 'known shell update question; no command may be sent')
    require(not any(re.search(r'\?(?!\d)', line) for line in lines),
            'unresolved/unknown startup question; no input permitted')
    require(isinstance(prompt, str) and prompt.strip() and '\n' not in prompt and '\r' not in prompt,
            'exact observed shell prompt required')
    # Incremental stream output need not include the final painted prompt.
    prompt_lines = lines if source == 'screen' else terminal['preview'].splitlines()
    visible = [line.strip() for line in prompt_lines if line.strip()]
    require(visible and visible[-1] == prompt.strip(), 'shell prompt absent/ambiguous')
    require(type(terminal['lastOutputAt']) is int, 'unknown shell observation time')
    return {'runtime': runtime, **identity}, lines, terminal['lastOutputAt']


def prepare(show, screen, handle, worktree, prompt, now=None):
    identity, _, last_output = observation(show, screen, handle, worktree, prompt)
    now = int(time.time() * 1000) if now is None else now
    require(0 <= now - last_output <= MAX_AGE_MS, 'stale initial shell observation')
    nonce = secrets.token_hex(16)
    # The complete output marker never occurs in the command echo.
    command = "printf '\\n%s%s\\n' '" + PREFIX + "' '" + nonce + "'"
    return {'format': FORMAT, 'status': 'challenge_prepared', 'identity': identity,
            'worktree': worktree, 'prompt': prompt, 'issued_at_ms': now,
            'before_last_output_ms': last_output,
            'before_cursor': int(screen['result']['terminal']['nextCursor']),
            'nonce': nonce, 'command': command}


def verify(challenge, show, screen, now=None):
    require(challenge.get('format') == FORMAT and challenge.get('status') == 'challenge_prepared',
            'invalid shell challenge')
    nonce = challenge['nonce']
    require(isinstance(nonce, str) and re.fullmatch('[0-9a-f]{32}', nonce), 'invalid challenge nonce')
    identity, lines, last_output = observation(show, screen, challenge['identity']['handle'],
                                               challenge['worktree'], challenge['prompt'], source='stream')
    require(identity == challenge['identity'], 'stale terminal incarnation/runtime')
    now = int(time.time() * 1000) if now is None else now
    issued = challenge['issued_at_ms']
    require(type(issued) is int and 0 <= now - issued <= MAX_AGE_MS and
            issued <= last_output <= now and last_output > challenge['before_last_output_ms'],
            'stale/unknown shell proof')
    marker = PREFIX + nonce
    frame = screen['result']['terminal']
    require(not frame.get('truncated') and not frame.get('limited') and
            int(frame['oldestCursor']) <= challenge['before_cursor'] < int(frame['nextCursor']),
            'stale/gapped stream cursor')
    require(sum(line.strip() == marker for line in lines) == 1,
            'fresh executed nonce output required; echo-only/unknown proof rejected')
    return {'format': FORMAT, 'status': 'saved_shell_proof_validated', 'identity': identity,
            'nonce': nonce, 'observed_at_ms': now,
            'scope': 'Saved shell round trip only; no current injection authorization. '
                     'Operator must recheck the same owned live terminal immediately before one agent command, '
                     'then confirm actual agent readiness before supervised adoption. '
                     'No launch, Dispatch or live-process authentication is certified.'}


def read(path):
    data = path.read_bytes()
    require(len(data) <= 1024 * 1024, 'oversized readiness evidence')
    value = json.loads(data, object_pairs_hook=unique_object, parse_constant=invalid_constant)
    require(isinstance(value, dict), 'readiness evidence must be an object')
    return value, hashlib.sha256(data).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'verify'))
    parser.add_argument('--show', required=True, type=Path)
    parser.add_argument('--read', required=True, type=Path, help='screen read for prepare; incremental stream read for verify')
    parser.add_argument('--challenge', type=Path)
    parser.add_argument('--terminal')
    parser.add_argument('--worktree')
    parser.add_argument('--prompt')
    args = parser.parse_args(argv)
    try:
        show, show_hash = read(args.show)
        screen, screen_hash = read(args.read)
        if args.command == 'prepare':
            require(args.terminal and args.worktree and args.prompt and not args.challenge,
                    'prepare needs exact terminal/worktree/prompt, no challenge')
            result = prepare(show, screen, args.terminal, args.worktree, args.prompt)
        else:
            require(args.challenge and not (args.terminal or args.worktree or args.prompt),
                    'verify needs only the saved challenge and current observations')
            challenge, challenge_hash = read(args.challenge)
            result = verify(challenge, show, screen)
            result['challenge_sha256'] = challenge_hash
        result['source_sha256'] = {'show': show_hash, 'read': screen_hash}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({'format': FORMAT, 'status': 'blocked', 'error': str(exc)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
