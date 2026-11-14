"""Bounded historical catalog integrity versus current catalog-input readiness.

Diagnostics only: neither result is Run acceptance or checked-launch authority.
The legacy record checker remains the completion/status consistency gate.
"""
import hashlib
from pathlib import Path

from host_model_catalog import bound_catalog, load, require, strict_json, timestamp

SCOPE = 'recorded_host_catalog_inputs'
LIMITS = [
    'Supplied pinned bytes/bindings only; not authenticated historical provenance.',
    'Historical effective configuration, authentication, tools and billing are not reconstructed.',
    'No task/Run success, completion acceptance, retry or launch permission.',
]
INPUT_ERRORS = (ValueError, TypeError, KeyError, AttributeError, OSError, OverflowError, RecursionError)


class MissingHistory(ValueError):
    pass


def pinned_json(evidence, base):
    """A reference or bare hash is not available historical evidence."""
    if not isinstance(evidence, dict) or not evidence.get('file') or not evidence.get('sha256'):
        raise MissingHistory('pinned historical file bytes are unavailable')
    digest = evidence['sha256']
    require(isinstance(digest, str) and len(digest) == 64 and
            all(c in '0123456789abcdef' for c in digest), 'invalid historical SHA-256')
    path = Path(base) / evidence['file']
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == digest, 'historical file hash mismatch')
    value = strict_json(raw)
    require(isinstance(value, dict), 'historical JSON object required')
    return path, value


def catalog_capture_time(manifest):
    """Read capture time only from a bounded, object-shaped receipt sequence.

    Callers must verify pinned manifest bytes first; load/bound_catalog still
    validate every receipt, response hash, timestamp and context afterwards.
    Present malformed nested data is invalid, not missing historical evidence.
    """
    receipts = manifest.get('receipts')
    require(isinstance(receipts, list) and len(receipts) in (2, 3),
            'bounded status + catalog receipt sequence required')
    require(all(isinstance(receipt, dict) for receipt in receipts), 'malformed receipt')
    return timestamp(receipts[-1].get('received_at'))


def historical_catalog(decision, evidence, base):
    """Reuse immutable catalog validation at capture time, never bound_catalog.

    This intentionally does not resolve Company settings, read observed_files,
    inspect the live semantic DB, or rerun selection under today's policy.
    """
    binding = decision['binding']
    context = binding['host_catalog']
    inventory = evidence[decision['price_selection']['inventory_evidence']]
    require(inventory.get('source') == 'orca_model_catalog', 'not a host catalog source')
    path, manifest = pinned_json(inventory, base)
    require(path.name == 'manifest.json', 'catalog evidence must pin manifest.json')
    captured = catalog_capture_time(manifest)
    selected = decision['selected']
    metadata = load(path.parent, inventory['sha256'], worktree=context['worktree'],
                    model=selected['model'], effort=selected['effort'], now=captured)
    require(metadata['runtime_id'] == context['runtime_id'], 'historical runtime binding mismatch')
    _, preflight = pinned_json(evidence.get(decision.get('receipt_evidence')), base)
    require(preflight.get('ok') is True and preflight.get('label') == 'real',
            'successful real-shaped recorded prelaunch receipt required')
    receipt = preflight['receipt']
    require(all(receipt['selected'].get(k) == selected[k] for k in ('route', 'family', 'model', 'effort')),
            'historical selection binding mismatch')
    # Planned Task/Dispatch IDs can legitimately differ after host start. Do not
    # manufacture an exact-launch binding from this prelaunch metadata receipt.
    require(all(receipt['binding'].get(k) == binding[k] for k in ('scope', 'revision')),
            'historical scope/revision binding mismatch')
    require(isinstance(binding.get('spec_sha256'), str) and len(binding['spec_sha256']) == 64 and
            receipt.get('spec_sha256') == binding['spec_sha256'], 'historical specification binding mismatch')
    require(receipt.get('configuration_sha256') == context['configuration_sha256'] and
            isinstance(context['configuration_sha256'], str) and len(context['configuration_sha256']) == 64,
            'historical configuration hash binding mismatch')
    refresh = receipt.get('host_catalog')
    if not isinstance(refresh, dict):
        raise MissingHistory('checked-launch catalog receipt is unavailable')
    require(refresh.get('prepared_manifest_sha256') == inventory['sha256'] and
            refresh.get('runtime_id') == context['runtime_id'] and refresh.get('worktree') == context['worktree'],
            'historical checked-launch catalog binding mismatch')
    # The refreshed metadata must also be retained; its existence in a preflight
    # claim alone does not prove those historical bytes are still available.
    refreshed_path, refreshed = pinned_json({'file': str(Path(refresh['refreshed_directory']) / 'manifest.json'),
                                            'sha256': refresh['refreshed_manifest_sha256']}, base)
    refreshed_metadata = load(refreshed_path.parent, refresh['refreshed_manifest_sha256'],
        worktree=context['worktree'], model=selected['model'], effort=selected['effort'],
        now=catalog_capture_time(refreshed))
    from host_model_catalog import compare
    compare(metadata, refreshed_metadata)
    return captured.isoformat()


def evaluate(record, base, configuration, *, legacy_ok):
    """Additive results; never reinterpret legacy errors, totals or acceptance."""
    history, current = [], []
    tasks = record.get('tasks', []) if isinstance(record, dict) else []
    evidence = record.get('evidence', {}) if isinstance(record, dict) else {}
    if not isinstance(tasks, list):
        tasks = []
    for index, task in enumerate(tasks):
        key = {'task_index': index, 'task': task.get('id') if isinstance(task, dict) else None}
        decision = task.get('routing_decision') if isinstance(task, dict) else None
        h = {**key, 'status': 'unknown', 'reason': 'recorded host catalog history unavailable'}
        c = {**key, 'status': 'unknown', 'reason': 'recorded host catalog inputs unavailable'}
        try:
            if not isinstance(decision, dict) or 'host_catalog' not in decision.get('binding', {}):
                history.append(h)
                current.append(c)
                continue
            h['captured_at'] = historical_catalog(decision, evidence, base)
            h.update(status='valid', reason='pinned catalog and prelaunch receipt bindings match')
        except (MissingHistory, OSError, KeyError) as exc:
            h.update(status='unknown', reason=str(exc))
        except INPUT_ERRORS as exc:
            h.update(status='invalid', reason=str(exc))
        try:
            if not isinstance(decision, dict):
                raise ValueError('recorded decision unavailable')
            require(configuration is not None, 'current Company configuration unavailable')
            # Record-level evidence is the actual Checker evidence namespace;
            # embedded/cached decision evidence cannot replace it here.
            bound_catalog({**decision, 'evidence': evidence}, base, configuration)
            c.update(status='ready', reason='current bounded catalog inputs match; checked launch still required')
        except INPUT_ERRORS as exc:
            c.update(status='blocked', reason=str(exc))
        history.append(h)
        current.append(c)
    historical_status = ('invalid' if any(x['status'] == 'invalid' for x in history) else
                         'valid' if history and all(x['status'] == 'valid' for x in history) else 'unknown')
    current_status = ('blocked' if not legacy_ok or any(x['status'] == 'blocked' for x in current) else
                      'ready' if current and all(x['status'] == 'ready' for x in current) else 'unknown')
    common = {'scope': SCOPE, 'launch_authorized': False, 'limits': LIMITS}
    return {
        'historical_integrity': {**common, 'status': historical_status, 'tasks': history},
        'current_readiness': {**common, 'status': current_status, 'legacy_record_ok': bool(legacy_ok),
                              'live_host_state': 'unknown', 'tasks': current},
    }
