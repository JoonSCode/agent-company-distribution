#!/usr/bin/env python3
"""Company-native storage, bound usage and next-launch reasoning preparation.

Stdlib only. No provider, Claude, implicit home discovery or automatic launch.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

sys.dont_write_bytecode = True
# Keep helpers one module when this file is executed, not only imported.
if __name__ == '__main__':
    # Select the same managed-bytecode read boundary as other Company CLIs.
    sys.pycache_prefix = os.path.join(os.path.abspath(os.path.expanduser('~')), '.cache', 'agent-company', 'python')
    sys.modules.setdefault('native_operations', sys.modules[__name__])


class Invalid(ValueError):
    """Malformed or contradictory caller input (exit 2)."""


class Blocked(ValueError):
    """Current state/authority guard refused an operation (exit 1)."""


def require(condition, message, error: type[ValueError] = Invalid):
    if not condition:
        raise error(message)


def shape(value, keys, label):
    require(isinstance(value, dict) and set(value) == set(keys), 'invalid ' + label + ' fields')
    return value


def text(value, label, nullable=False):
    require((nullable and value is None) or
            (isinstance(value, str) and bool(value.strip()) and '\x00' not in value), 'invalid ' + label)
    return value


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def valid_hash(value):
    require(isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None, 'invalid sha256')
    return value


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON key')
        result[key] = value
    return result


def invalid_constant(_value):
    raise Invalid('nonfinite JSON constant')


def decode(raw):
    return json.loads(raw, object_pairs_hook=unique, parse_constant=invalid_constant)


def absolute(value, base):
    text(value, 'path')
    path = Path(value)
    require('..' not in path.parts, 'parent traversal forbidden')
    return Path(os.path.abspath(path if path.is_absolute() else base / path))


def regular(path, limit=128 * 1024 * 1024):
    """No link in any path component, single inode, bounded stable read."""
    path = Path(path).absolute()
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = child
        handle = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        with os.fdopen(handle, 'rb') as stream:
            before = os.fstat(stream.fileno())
            require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1, 'unsafe input file')
            require(before.st_size <= limit, 'input exceeds read limit')
            raw = stream.read(limit + 1)
            after = os.fstat(stream.fileno())
            require(len(raw) <= limit and signature(before) == signature(after), 'input changed while reading')
            actual = os.stat(path.name, dir_fd=fd, follow_symlinks=False)
            require(signature(actual) == signature(after), 'input path replaced while reading')
            return raw
    finally:
        os.close(fd)


def signature(st):
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def request(path, schema, keys):
    path = Path(path).absolute()
    raw = regular(path, 16 * 1024 * 1024)
    value = shape(decode(raw), keys, 'request')
    require(value['schema'] == schema, 'unknown request schema')
    return value, path.parent, {'path': str(path), 'sha256': sha(raw)}


def pinned(reference, base):
    shape(reference, ('path', 'sha256'), 'file reference')
    path = absolute(reference['path'], base)
    raw = regular(path)
    require(sha(raw) == valid_hash(reference['sha256']), 'source pin mismatch')
    return path, raw


def pointer(value, reference):
    require(isinstance(reference, str) and (not reference or reference.startswith('/')), 'invalid JSON pointer')
    if not reference:
        return value
    for token in reference[1:].split('/'):
        require(re.search('~(?![01])', token) is None, 'invalid JSON pointer escape')
        token = token.replace('~1', '/').replace('~0', '~')
        if isinstance(value, list):
            require(re.fullmatch('0|[1-9][0-9]*', token) is not None, 'invalid array pointer')
            index = int(token)
            require(index < len(value), 'pointer missing')
            value = value[index]
        else:
            require(isinstance(value, dict) and token in value, 'pointer missing')
            value = value[token]
    return value


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Invalid(message)


def main(argv=None):
    try:
        parser = Parser(description=__doc__)
        families = parser.add_subparsers(dest='family', required=True)
        for family, commands in (('storage', ('report', 'plan', 'apply')),
                                 ('usage', ('report',)), ('reasoning', ('prepare', 'check'))):
            sub = families.add_parser(family).add_subparsers(dest='command', required=True)
            for command in commands:
                item = sub.add_parser(command)
                if command in ('report', 'plan', 'prepare'):
                    item.add_argument('--request', required=True, type=Path)
                if command == 'prepare': item.add_argument('--output', required=True, type=Path)
                if command == 'check': item.add_argument('--bundle', required=True, type=Path)
                if command == 'apply':
                    item.add_argument('--plan', required=True, type=Path)
                    item.add_argument('--expect-plan-sha256', required=True)
        args = parser.parse_args(argv)
        if args.family == 'storage':
            import native_storage as module
            result = (module.apply(args.plan, args.expect_plan_sha256) if args.command == 'apply'
                      else getattr(module, args.command)(args.request))
        elif args.family == 'usage':
            import native_usage
            result = native_usage.report(args.request)
        else:
            import native_reasoning
            result = (native_reasoning.prepare(args.request, args.output) if args.command == 'prepare'
                      else native_reasoning.check(args.bundle))
        code = 1 if result.get('status') == 'blocked' else 0
    except Blocked as exc:
        result, code = {'status': 'blocked', 'errors': [str(exc)[:2000]]}, 1
    except (Invalid, ValueError, OSError, KeyError, TypeError, AttributeError, OverflowError, RecursionError) as exc:
        result, code = {'status': 'invalid', 'errors': [str(exc)[:2000]]}, 2
    print(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
