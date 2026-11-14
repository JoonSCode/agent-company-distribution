"""Declared task depth to the unchanged approved router/checked-launch bundle.

Preparation never changes this turn, grants authority or launches any host/model.
"""
import argparse
from pathlib import Path

import routing_prepare
from native_operations import (Blocked, decode, pinned, regular, request, require,
                               sha, shape, text)

SCHEMA = 'company-native-reasoning-request/v1'
KEYS = ('schema', 'depth', 'effort', 'record', 'decision', 'spec_file', 'worktree')
SIDECAR = 'native-reasoning.json'


def load(request_path):
    value, base, source = request(request_path, SCHEMA, KEYS)
    require(value['depth'] in ('standard', 'deep', 'ultrathink'), 'unsupported task depth')
    text(value['effort'], 'explicit effort'); text(value['worktree'], 'worktree')
    files, raw = {}, {}
    for key in ('record', 'decision', 'spec_file'):
        files[key], raw[key] = pinned(value[key], base)
    raw['spec_file'].decode('utf-8')
    record, decision = decode(raw['record']), decode(raw['decision'])
    require(isinstance(record, dict) and isinstance(decision, dict), 'record/decision objects required')
    selected = decision.get('selected')
    require(isinstance(selected, dict), 'existing selected pair required')
    for key in ('route', 'model', 'effort'): text(selected.get(key), 'selected ' + key)
    depth = 'deep' if value['depth'] == 'ultrathink' else value['depth']
    return value, source, files, decision, {
        'schema': 'company-native-reasoning/v1', 'status': 'blocked', 'launch_authorized': False,
        'sources': [source, *({'path': str(files[k]), 'sha256': sha(raw[k])} for k in files)],
        'requested': {'depth': depth, 'alias': 'ultrathink' if value['depth'] == 'ultrathink' else None,
                      'model': selected['model'], 'effort': value['effort']},
        'approved': {k: selected.get(k) for k in ('route', 'family', 'model', 'effort')},
        'binding': decision.get('binding'),
        'effective': {'model': None, 'effort': None, 'status': 'not_launched'},
        'next_checked_launch': None, 'blockers': [],
        'checks': {'configuration_services_model_and_paid_optin': 'existing_router_required',
                   'native_supported_effort': 'existing_router_and_catalog_required',
                   'resource_caps_and_budget': 'not_supplied; unchanged launcher gate remains required when scope requires a manifest',
                   'trusted_capacity_or_live_quota': 'unknown'},
        'limits': ['Task depth is a declaration, not a universal effort mapping or magic prompt keyword.',
                   'No current-turn change; only an exact next checked Codex launch request.',
                   'Requested/approved are not serving/effective observations; no paid fallback or default write.']}


def guards(value, decision):
    selected = decision['selected']
    errors = []
    if selected['effort'] != value['effort']:
        errors.append({'code': 'effort_approval_mismatch', 'message': 'Request differs from the existing approved effort; no automatic remap.'})
    if selected['route'] != 'codex':
        errors.append({'code': 'checked_launch_bridge_unavailable', 'message': 'Existing checked-launch bridge is Codex-only; preserve provider selection, no fallback.'})
    return errors


def launch_input(root, worktree, binding):
    return {'entrypoint': 'routing_launch.py', 'record': str(root / 'record.json'),
            'decision': str(root / 'decision.json'), 'spec_file': str(root / 'spec.txt'),
            'worktree': worktree, 'run': binding.get('run'), 'parent': binding.get('parent_task'),
            'binding_flags': {flag: binding[key] for flag, key in (('--run', 'run'), ('--parent', 'parent_task'))
                              if binding.get(key) is not None},
            'required_caller_flags': ['--from', '--receipt', '--result'],
            'resource_limit_flags_if_required_by_scope': ['--require-resource-manifest', '--resource-manifest',
                '--declared-host', '--declared-tool', '--declared-billing', '--declared-spend'],
            'spec_transport': 'Read spec_file as exact UTF-8 and pass its CONTENT as --spec; never --spec-file.',
            'result_rule': 'Use an unused exact result and prelaunch receipt path; existing/unknown result blocks, never auto-retry.',
            'check_before_launch': 'Recheck this bundle, then the unchanged launcher repeats current policy/catalog/authority checks.'}


def bundle_binding(root, value, files, decision, result):
    """Cross-check identities and bytes, not just two independently valid routes.

    These local pins are review bindings, never authenticated launch authority.
    A different bundle or request requires an explicit fresh preparation.
    """
    manifest_raw = regular(root / 'manifest.json')
    manifest = decode(manifest_raw)
    require(manifest['worktree'] == value['worktree'], 'native bundle worktree mismatch', Blocked)
    for key, original, prepared in (('record', 'original-record.json', 'record.json'),
                                    ('decision', 'original-decision.json', 'decision.json'),
                                    ('spec_file', 'spec.txt', 'spec.txt')):
        pin = next(row for row in result['sources'][1:] if row['path'] == str(files[key]))
        require(manifest['inputs'].get(str(files[key])) == pin['sha256'],
                'native bundle original input identity mismatch: ' + key, Blocked)
        raw = regular(root / original)
        require(sha(raw) == pin['sha256'], 'native bundle original bytes mismatch: ' + key, Blocked)
        if key != 'spec_file':
            rebased, _patch = routing_prepare.rebase(decode(raw), files[key].parent, prepared)
            require(decode(regular(root / prepared)) == rebased,
                    'native bundle prepared input mismatch: ' + key, Blocked)
    actual = decode(regular(root / 'decision.json'))
    require(actual['selected'] == decision['selected'] and actual['binding'] == result['binding'],
            'native bundle approved pair/binding mismatch', Blocked)
    return {'path': str(root), 'manifest_sha256': sha(manifest_raw),
            'sources': result['sources'], 'worktree': value['worktree'], 'binding': result['binding']}


def prepare(request_path, output=None):
    value, source, files, decision, result = load(request_path)
    require(output is not None, 'explicit exclusive output required')
    result['blockers'] = guards(value, decision)
    if result['blockers']:
        return result
    root = Path(output).absolute()
    result['bundle'] = str(root)
    try:
        routing_prepare.prepare(argparse.Namespace(record=files['record'], decision=files['decision'],
            spec_file=files['spec_file'], output=root, worktree=value['worktree']))
        # Exact depth/effort input is retained without rewriting routing authority.
        require(sha(regular(Path(source['path']))) == source['sha256'], 'native request changed during preparation', Blocked)
        routing_prepare.write_private(root, SIDECAR, routing_prepare.encoded({
            'schema': 'company-native-reasoning-binding/v1', 'request': source,
            'requested': result['requested'], 'approved': result['approved'],
            'bundle': bundle_binding(root, value, files, decision, result)}))
        # Use the same full cross-binding gate for prepare and later checks.
        return check(root)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError, RecursionError) as exc:
        result['blockers'] = [{'code': 'router_prepare_guard', 'message': str(exc)}]
    return result


def check(bundle):
    root = Path(bundle).absolute()
    try:
        sidecar_raw = regular(root / SIDECAR)
        sidecar = decode(sidecar_raw)
        shape(sidecar, ('schema', 'request', 'requested', 'approved', 'bundle'), 'native reasoning binding')
        require(sidecar['schema'] == 'company-native-reasoning-binding/v1', 'unknown native binding')
        source = sidecar['request']
        require(sha(regular(Path(source['path']))) == source['sha256'], 'native request source changed', Blocked)
        value, pin, files, decision, result = load(source['path'])
        require(pin == source and sidecar['requested'] == result['requested'] and sidecar['approved'] == result['approved'],
                'native requested/approved binding changed', Blocked)
        require(sidecar['bundle'] == bundle_binding(root, value, files, decision, result),
                'native request/bundle binding changed; prepare a new bundle explicitly', Blocked)
        checked = routing_prepare.check_bundle(root)
        require(regular(root / SIDECAR) == sidecar_raw and
                sha(regular(root / 'manifest.json')) == sidecar['bundle']['manifest_sha256'],
                'native sidecar/bundle changed during check', Blocked)
        result['bundle'], result['router'] = str(root), checked
        result['blockers'] = [*guards(value, decision), *checked['missing_fields']]
        if not result['blockers']:
            result['status'] = 'prepared'
            result['next_checked_launch'] = launch_input(root, value['worktree'], decision['binding'])
        return result
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError, RecursionError) as exc:
        return {'schema': 'company-native-reasoning/v1', 'status': 'blocked', 'launch_authorized': False,
                'bundle': str(root), 'effective': {'model': None, 'effort': None, 'status': 'not_launched'},
                'next_checked_launch': None, 'blockers': [{'code': 'bundle_guard', 'message': str(exc)}]}
