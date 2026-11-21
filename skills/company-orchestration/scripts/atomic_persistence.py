"""Shared offline atomic JSON persistence for launch and consumer settlement."""
import json
import os
import secrets
import tempfile


def atomic_state(path, value, capability=None):
    """Replace a complete state and sync both its data and directory entry."""
    if capability is not None:
        import run_completion as rc
        capability.verify()
        ref = path.absolute().relative_to(capability.root).as_posix()
        with rc.parent_fd(capability.fd, ref) as (parent, name):
            temporary = '.launch-write-' + secrets.token_hex(16)
            handle = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
            try:
                with os.fdopen(handle, 'w', encoding='utf-8') as stream:
                    json.dump(value, stream, ensure_ascii=False, indent=2); stream.write('\n')
                    stream.flush(); os.fsync(stream.fileno())
                capability.verify()
                with rc.parent_fd(capability.fd, ref) as (fresh, _):
                    rc.require((os.fstat(fresh).st_dev, os.fstat(fresh).st_ino) == (os.fstat(parent).st_dev, os.fstat(parent).st_ino), 'launch parent moved')
                os.replace(temporary, name, src_dir_fd=parent, dst_dir_fd=parent)
                os.fsync(parent)
                capability.verify()
                rc.require(rc.decode(rc.read_file(capability.fd, ref)[0]) == value, 'launch state readback differs')
            finally:
                try: os.unlink(temporary, dir_fd=parent)
                except FileNotFoundError: pass
        return
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)
