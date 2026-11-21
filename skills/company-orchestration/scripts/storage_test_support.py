"""Explicit synthetic enrollment builders; never used by product entrypoints.

Call before writing fixture inputs. Real storage enrollment/classification runs;
there is no patched guard, invented live host or adoption of populated roots.
"""
import hashlib
import json
from pathlib import Path

import native_storage
import run_completion as rc


def save(path, value):
    path.write_text(json.dumps(value) + '\n')
    return path


def pin(path):
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def enrolled_run(base, *, record='record.json', paths=(), run_id='goal-1', owner='B', consumers=()):
    base = Path(base)
    home = base / 'sejong'
    root = home / 'runs/fixture'
    root.mkdir(parents=True)
    cwd = base / 'workspace'
    cwd.mkdir()
    identity = save(base / 'fixture-identity.json', dict(host='explicit_lead', session_id='synthetic-fixture', cwd=str(cwd)))
    request = save(base / 'fixture-enrollment.json', dict(schema='company-native-storage-enrollment/v1', sejong_home=str(home), run=str(root), run_id=run_id, owner=owner, record=record, host='explicit_lead', session_id='synthetic-fixture', cwd=str(cwd), consumers=list(consumers), expect_session_binding_sha256=None, identity_evidence=pin(identity)))
    result = native_storage.enroll(request)
    assert result['status'] == 'enrolled' and result['readback_verified']
    reserve(root, paths)
    return root


def enrollment_path(root):
    return root.parents[2] / 'fixture-enrollment.json'


def flags(root):
    request = enrollment_path(root)
    return ['--enrollment-request', str(request), '--expect-enrollment-sha256', pin(request)['sha256']]


def reserve(root, paths):
    paths = list(paths)
    if not paths:
        return
    request = enrollment_path(root)
    intake, _, _, _ = native_storage.bound_enrollment(request)
    result = native_storage.classify_value(dict(enrollment=pin(request), expect_manifest_sha256=pin(root / rc.MANIFEST)['sha256'], phase='reserve', artifacts=[dict(path=p, **{'class': 'preserve'}, owner=intake['owner'], consumers=[], reason='retained synthetic fixture original', origin='storage_test_support', regeneration=None, next_use_or_recheck='fixture teardown after all original assertions') for p in paths]), request.parent, pin(request))
    assert result['status'] == 'reserved' and result['readback_verified']


def fixture_goal():
    return {'id': 'goal-1', 'current_owner': 'B'}
