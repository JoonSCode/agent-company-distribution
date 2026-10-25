#!/usr/bin/env python3
"""Supported Codex Stop command callback, scoped to an explicitly bound Company Run.

Stop is merely a wakeup. Success comes only from the exact accepted record.
The installer owns registering this separate command; Core hooks stay unchanged.
"""
import argparse
import contextlib
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import sys

sys.dont_write_bytecode = True
import run_completion as lifecycle


def binding_path(home, session_id):
    lifecycle.require(isinstance(session_id, str) and session_id and len(session_id) <= 4096,
                      'missing/invalid host session_id')
    return Path(home) / 'state/company-completion' / (hashlib.sha256(session_id.encode()).hexdigest() + '.json')


def state_parent(target, create=False):
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in target.parent.absolute().parts[1:]:
            if create:
                try:
                    os.mkdir(part, 0o700, dir_fd=fd)
                except FileExistsError:
                    pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def register_session(home, session_id, root, run_id, owner, repo, record, expected=None):
    lifecycle.parts(record)
    target = binding_path(home, session_id)
    fd = state_parent(target, create=True)
    lock = None
    try:
        lock = os.open('.registration.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        lifecycle.require(stat.S_ISREG(os.fstat(lock).st_mode) and os.fstat(lock).st_nlink == 1,
                          'unsafe registration lock')
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        payload = {'format': 'company-completion-session/v1', 'session_id': session_id,
                   'run': str(root), 'run_id': run_id, 'owner': owner,
                   'repo_root': str(repo.resolve()), 'record': record}
        try:
            existing = os.open(target.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
        except FileNotFoundError:
            existing = None
        if existing is not None:
            with os.fdopen(existing, 'rb') as stream:
                lifecycle.require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), 'unsafe session binding')
                prior_data = stream.read()
                prior = lifecycle.decode(prior_data)
            if prior == payload:
                return
            lifecycle.require(lifecycle.sha(prior_data) == expected and prior.get('session_id') == session_id,
                              'session already bound; exact prior binding hash required')
            prior_root, prior_fd = lifecycle.open_run(home, Path(prior['run']))
            prior_lock = None
            try:
                prior_lock = os.open(lifecycle.LOCK, os.O_RDWR | os.O_NOFOLLOW, dir_fd=prior_fd)
                fcntl.flock(prior_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                manifest_data = lifecycle.read_file(prior_fd, lifecycle.MANIFEST, True)[0]
                manifest = lifecycle.decode(manifest_data)
                receipt = lifecycle.decode(lifecycle.read_file(prior_fd, lifecycle.RECEIPT, True)[0])
                record_data, record_binding = lifecycle.read_file(prior_fd, prior['record'])
                lifecycle.validate_manifest(manifest)
                lifecycle.validate_receipt(receipt, manifest, lifecycle.sha(manifest_data), record_binding)
                lifecycle.require(receipt['status'] == 'completed', 'prior Run not safely completed')
                lifecycle.validate_acceptance(lifecycle.decode(record_data), prior_root / prior['record'],
                                              manifest, lifecycle.sha(manifest_data))
                temp = '.binding-' + os.urandom(16).hex()
                out = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
                with os.fdopen(out, 'w') as stream:
                    json.dump(payload, stream)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temp, target.name, src_dir_fd=fd, dst_dir_fd=fd)
                os.fsync(fd)
            finally:
                if prior_lock is not None:
                    os.close(prior_lock)
                os.close(prior_fd)
            return
        # Atomic exclusive create; never replace another owner.
        out = os.open(target.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                      0o600, dir_fd=fd)
        with os.fdopen(out, 'w') as stream:
            json.dump(payload, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(fd)
    finally:
        if lock is not None:
            os.close(lock)
        os.close(fd)


def dispatch(payload, home):
    if payload.get('hook_event_name') != 'Stop':
        return {'status': 'skipped', 'reason': 'not Stop'}
    session_id = payload.get('session_id')
    target = binding_path(home, session_id)
    try:
        parent = state_parent(target)
    except FileNotFoundError:
        return {'status': 'skipped', 'reason': 'unregistered session'}
    try:
        try:
            fd = os.open(target.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        except FileNotFoundError:
            return {'status': 'skipped', 'reason': 'unregistered session'}
    finally:
        os.close(parent)
    with os.fdopen(fd, 'rb') as stream:
        lifecycle.require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode) and os.fstat(stream.fileno()).st_nlink == 1,
                          'unsafe session binding')
        binding = lifecycle.decode(stream.read())
    lifecycle.require(binding.get('format') == 'company-completion-session/v1'
                      and binding.get('session_id') == session_id, 'session identity mismatch')
    cwd = payload.get('cwd')
    lifecycle.require(isinstance(cwd, str) and cwd and Path(cwd).is_absolute(), 'explicit host cwd required')
    lifecycle.require(str(Path(cwd).resolve()) == binding.get('repo_root'),
                      'exact registered cwd mismatch')
    root, run_fd = lifecycle.open_run(home, Path(binding['run']))
    try:
        data, _ = lifecycle.read_file(run_fd, lifecycle.MANIFEST, True)
        manifest = lifecycle.decode(data)
        lifecycle.validate_manifest(manifest)
        lifecycle.require(manifest.get('run_id') == binding['run_id'] and
                          manifest.get('owner') == binding['owner'], 'registered Run/owner mismatch')
        try:
            record = lifecycle.decode(lifecycle.read_file(run_fd, binding['record'])[0])
        except FileNotFoundError:
            record = {}
        lifecycle.require(isinstance(record.get('goal', {}), dict), 'invalid goal metadata')
        if record.get('goal', {}).get('status') != 'succeeded':
            result = {'status': 'skipped', 'reason': 'Run unfinished, failed or no accepted record',
                      'run_id': binding['run_id'], 'session_id': session_id}
            lifecycle.write_metadata(run_fd, lifecycle.HOOK_RECEIPT, result)
            return result
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result = {'status':'blocked', 'run_id':binding['run_id'], 'errors':[str(exc)], 'removed':[]}
        lifecycle.write_metadata(run_fd, lifecycle.HOOK_RECEIPT, result)
        return result
    finally:
        os.close(run_fd)
    # This is the executable completion connection, not a policy suggestion.
    # Main obtains the same exclusive Run lock and validates every guard again.
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = lifecycle.main(['complete', '--run', str(root), '--sejong-home', str(home),
                               '--record', binding['record'], '--expect-manifest-sha256', lifecycle.sha(data)])
    result = lifecycle.decode(output.getvalue())
    result['hook'] = {'event': 'Stop', 'session_id': session_id, 'exit_code': code}
    root, run_fd = lifecycle.open_run(home, root)
    try:
        lifecycle.write_metadata(run_fd, lifecycle.HOOK_RECEIPT, result)
    finally:
        os.close(run_fd)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('event', nargs='?', default='Stop', choices=['Stop'])
    parser.add_argument('--sejong-home', type=Path, default=lifecycle.default_home())
    args = parser.parse_args(argv)
    try:
        data = sys.stdin.read(16 * 1024 * 1024 + 1)
        lifecycle.require(len(data) <= 16 * 1024 * 1024, 'hook payload exceeds compact limit')
        payload = lifecycle.decode(data)
        lifecycle.require(payload.get('hook_event_name') == args.event, 'hook event mismatch')
        result = dispatch(payload, args.sejong_home)
        if result['status'] == 'blocked':
            print('Company completion cleanup deferred: ' + '; '.join(result['errors']), file=sys.stderr)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print('Company completion hook preserved all unverified paths: ' + str(exc), file=sys.stderr)
    # Never infer completion, block ordinary user replies, or interfere with Core's gates.
    print('{}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
