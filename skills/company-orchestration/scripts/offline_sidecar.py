"""Bounded, no-follow JSON reads for explicitly rooted offline sidecars."""
import json
import os
from pathlib import Path
import stat

LIMIT = 65536


def read_json(root, name):
    root = Path(root).absolute()
    parts = str(name).split('/')
    if not parts or any(p in ('', '.', '..') for p in parts) or '\\' in str(name) or Path(name).is_absolute():
        raise ValueError('sidecar path must be relative to root')
    # Open each component without following symlinks, including the root ancestry.
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in root.parts[1:] + tuple(parts[:-1]):
            nxt = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = nxt
        file_fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            if not stat.S_ISREG(os.fstat(file_fd).st_mode):
                raise ValueError('sidecar must be a regular file')
            with os.fdopen(file_fd, 'rb') as stream:
                file_fd = None
                raw = stream.read(LIMIT + 1)
            if len(raw) > LIMIT:
                raise ValueError('sidecar exceeds 64 KiB')
        finally:
            if file_fd is not None:
                os.close(file_fd)
    finally:
        os.close(fd)
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = value
        return result
    return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
