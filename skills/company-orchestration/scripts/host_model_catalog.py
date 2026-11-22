#!/usr/bin/env python3
"""Validate pinned Orca catalog metadata; NEVER grants checked-launch authority."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

FORMAT = 'company-host-catalog-metadata/v1'
MAX_AGE_SECONDS = 300
EXPLICIT_HOST_VERSION = '1.4.269'
SAVED_ONLY_VERSIONS = ('1.4.268', EXPLICIT_HOST_VERSION)
REVIEWED_VERSIONS = ('1.4.245', '1.4.261', '1.4.263', *SAVED_ONLY_VERSIONS)
COHERENT_CATALOG = 'agent-session.coherent-model-catalog.v1'
SAVED_ONLY_CAPABILITIES = (
    'agent-session.model-catalog.model-efforts.v1',
    'agent-session.model-catalog.saved-only.v1',
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def strict_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    def constant(value):
        raise ValueError('nonfinite JSON constant: ' + value)
    return json.loads(raw, object_pairs_hook=unique, parse_constant=constant)


def timestamp(value):
    require(isinstance(value, str), 'missing timestamp')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(result.tzinfo is not None, 'timestamp must have timezone')
    return result


def verify_local_host(metadata):
    """Check the live profile locator and packaged app against the pinned observation."""
    host = metadata['host']
    app, user_data = Path(host['app']), Path(host['user_data'])
    for path in (app, user_data):
        require(path.resolve(strict=True) == path and path.is_dir(), 'catalog host path changed')
    for name, key, expected in (
            ('orca-runtime.json', 'runtimeId', metadata['runtime_id']),
            ('host-installation.json', 'installationId', host['installation_id'])):
        path = user_data / name
        require(path.resolve(strict=True) == path and path.is_file(), 'catalog host identity path changed')
        value = strict_json(path.read_bytes())
        require(isinstance(value, dict) and value.get(key) == expected, 'catalog live host identity changed')
    seal = app / 'Contents/_CodeSignature/CodeResources'
    require(seal.resolve(strict=True) == seal and seal.is_file() and
            hashlib.sha256(seal.read_bytes()).hexdigest() == host['code_resources_sha256'],
            'catalog packaged app seal changed')


def load(directory, digest, *, worktree, model=None, effort=None, now=None,
         prepared_observation=None):
    """No global cache reads, fallback models, account inference, or source writes.

    A caller must pin manifest bytes, not merely name an editable directory.
    Unknown response fields are retained in result and compared on explicit recheck.
    This validates *observed rows*, not completeness, auth, tools or billing.
    Only pass (prepared_at, original_fetched_at) from a validated Run
    preparation, when comparing a new local read to that Run's pinned catalog.
    """
    directory = Path(directory)
    now = now or datetime.now(timezone.utc)
    raw = (directory / 'manifest.json').read_bytes()
    require(hashlib.sha256(raw).hexdigest() == digest, 'manifest hash mismatch')
    manifest = strict_json(raw)
    require(isinstance(manifest, dict) and manifest.get('format') == FORMAT, 'unknown manifest format')
    app_version = manifest.get('app_version')
    require(app_version in REVIEWED_VERSIONS, 'unreviewed host version')
    saved_only = app_version in SAVED_ONLY_VERSIONS
    explicit = app_version == EXPLICIT_HOST_VERSION
    if prepared_observation is not None:
        require(explicit, 'prepared catalog reuse requires an explicit saved-only host')
        prepared_at, original_fetched_at = prepared_observation
    host = manifest.get('host')
    if explicit:
        require(isinstance(host, dict) and set(host) == {'app', 'user_data', 'code_resources_sha256'},
                'explicit local catalog host required')
        for value in (host['app'], host['user_data']):
            require(isinstance(value, str) and value.startswith('/') and str(Path(value)) == value and
                    '..' not in Path(value).parts and '\0' not in value, 'invalid explicit host path')
        require(Path(host['app']).suffix == '.app' and isinstance(host['code_resources_sha256'], str) and
                re.fullmatch(r'[0-9a-f]{64}', host['code_resources_sha256']), 'invalid packaged app binding')
    else:
        require('host' not in manifest, 'explicit catalog host requires a reviewed version')
    require(isinstance(worktree, str) and re.fullmatch(r'id:[^:]+::/.+', worktree), 'exact worktree id required')
    require(manifest.get('worktree') == worktree, 'worktree context changed; reprepare')
    runtime = manifest.get('runtime_id')
    require(isinstance(runtime, str) and bool(runtime), 'missing runtime identity')
    receipts = manifest.get('receipts')
    if not isinstance(receipts, list) or len(receipts) not in ((2,) if saved_only else (2, 3)):
        raise ValueError('bounded status + catalog receipt sequence required')
    responses, seen_ids, previous_time = [], set(), None
    for index, receipt in enumerate(receipts):
        require(isinstance(receipt, dict), 'malformed receipt')
        name = 'status.json' if index == 0 else 'response-%d.json' % index
        require(receipt.get('file') == name, 'unexpected response path')
        raw = (directory / name).read_bytes()
        require(hashlib.sha256(raw).hexdigest() == receipt.get('sha256'), 'response hash mismatch')
        response = strict_json(raw)
        require(isinstance(response, dict) and response.get('ok') is True, 'unsuccessful envelope')
        request_id = response.get('id')
        require(isinstance(request_id, str) and request_id and request_id not in seen_ids, 'missing or duplicate request id')
        seen_ids.add(request_id)
        require(response.get('_meta', {}).get('runtimeId') == runtime, 'runtime identity changed')
        started, received = timestamp(receipt.get('started_at')), timestamp(receipt.get('received_at'))
        require(started <= received <= now and (now - received).total_seconds() <= MAX_AGE_SECONDS,
                'stale or future catalog receipt')
        require(prepared_observation is None or prepared_at <= started, 'catalog receipt predates preparation')
        require(previous_time is None or previous_time <= started, 'out-of-order receipts')
        previous_time = received
        params = {} if index == 0 else {'agent': 'codex', 'worktree': worktree}
        if saved_only and index == 1:
            params['savedOnly'] = True
            require(isinstance(receipt.get('params'), dict) and receipt['params'].get('savedOnly') is True,
                    'saved-only request required')
        if index == 2:
            params['waitForListing'] = True
            require(isinstance(receipt.get('params'), dict) and receipt['params'].get('waitForListing') is True,
                    'literal waitForListing required')
            require(responses[-1].get('listingInProgress') is True, 'unsolicited catalog retry')
        require(receipt.get('method') == ('status.get' if index == 0 else 'agentSession.modelCatalog')
                and receipt.get('params') == params, 'method or launch context mismatch')
        result = response.get('result')
        require(isinstance(result, dict), 'malformed result')
        responses.append(result)
    status, result = responses[0], responses[-1]
    capabilities = status.get('capabilities')
    require(status.get('runtimeId') == runtime and status.get('appVersion') == app_version
            and isinstance(capabilities, list) and COHERENT_CATALOG in capabilities
            and (not saved_only or all(capability in capabilities for capability in SAVED_ONLY_CAPABILITIES)),
            'unverified host provenance')
    if explicit:
        descriptor = status.get('hostDescriptor')
        installation_id = descriptor.get('installationId') if isinstance(descriptor, dict) else None
        require(status.get('graphStatus') == 'ready' and isinstance(installation_id, str) and
                bool(installation_id), 'unverified explicit host installation or readiness')
        host = {**host, 'installation_id': installation_id}
    require(result.get('origin') == 'probe', 'unknown or fallback catalog origin')
    require(result.get('listingInProgress', False) is False and result.get('waitExpired', False) is False,
            'partial listing')
    require(result.get('unavailable') is None, 'catalog unavailable')
    require(result.get('nextCursor') is None and result.get('hasMore', False) is False
            and result.get('complete', True) is True, 'pagination or incomplete result')
    if saved_only:
        # The reviewed Codex resolvers can project a base catalog for an
        # unresolved workspace, but that projection cannot name its configured model.
        require(result.get('modelsDifferByWorkspace') is True
                and result.get('listingNamesConfiguredModel') is True,
                'missing verified workspace catalog; refresh in Orca and reprepare')
    # Absence of complete is NOT converted to a completeness claim.
    fetched = result.get('fetchedAt')
    require(type(fetched) in (int, float) and fetched > 0, 'missing host fetchedAt')
    if prepared_observation is not None:
        require(fetched >= original_fetched_at, 'host catalog fetchedAt regressed since preparation')
    fetched = datetime.fromtimestamp(fetched / 1000, timezone.utc)
    require(previous_time is not None and fetched <= previous_time and
            (prepared_observation is not None or (now - fetched).total_seconds() <= MAX_AGE_SECONDS),
            'stale or future host catalog; fresh receipt is not fresh provider metadata')
    models = result.get('models')
    if not isinstance(models, list) or not models:
        raise ValueError('missing models')
    normalized, ids = [], set()
    for row in models:
        require(isinstance(row, dict) and isinstance(row.get('id'), str) and row['id'], 'malformed model')
        require(not saved_only or row.get('effortsKnown', True) is True, 'unverified model efforts')
        require(row['id'] not in ids, 'duplicate model id')
        ids.add(row['id'])
        levels = row.get('efforts')
        if not isinstance(levels, list) or not levels:
            raise ValueError('missing model efforts')
        values = []
        for level in levels:
            require(isinstance(level, dict) and isinstance(level.get('value'), str) and level['value'], 'malformed effort')
            require(level['value'] not in values, 'duplicate effort')
            values.append(level['value'])
        normalized.append({'slug': row['id'], 'supported_reasoning_levels': [{'effort': value} for value in values]})
    if model is not None or effort is not None:
        require(any(row['slug'] == model and {'effort': effort} in row['supported_reasoning_levels']
                    for row in normalized), 'selected model/effort absent; reprepare')
    return {'format': FORMAT, 'app_version': app_version, 'runtime_id': runtime, 'worktree': worktree,
            **({'host': host} if explicit else {}),
            'selected': {'model': model, 'effort': effort}, 'models': normalized,
            'host_result': result, 'metadata_verified': True, 'launch_authorized': False,
            'unknown': ['effective_provider_config', 'provider_list_completeness',
                        'required_capabilities', 'provider_tools', 'authentication', 'billing']}


def compare(before, after):
    """Explicit metadata recheck. Equality is never launch approval."""
    def stable(value):
        result = dict(value)
        result['host_result'] = {k: v for k, v in value['host_result'].items() if k != 'fetchedAt'}
        return result
    require(stable(before) == stable(after), 'catalog selection or context changed; explicit reprepare required')


def require_launch_authority(metadata):
    # Catalog availability is one input, not standalone launch authority.
    raise ValueError('catalog_requires_checked_launcher: use routing_launch.py with bound host_catalog evidence')


def inventory_reference(decision):
    """Resolve the common inventory ID while retaining historical comparison inputs."""
    binding = decision.get('binding', {})
    selection = decision.get('price_selection', {})
    require(isinstance(binding, dict) and isinstance(selection, dict), 'invalid inventory binding')
    common = binding.get('inventory_evidence')
    legacy = selection.get('inventory_evidence')
    require(common is None or isinstance(common, str) and bool(common), 'invalid common inventory reference')
    require(legacy is None or isinstance(legacy, str) and bool(legacy), 'invalid legacy inventory reference')
    require(common is None or legacy is None or common == legacy, 'inventory references disagree')
    ref = common if common is not None else legacy
    require(isinstance(ref, str) and bool(ref), 'inventory reference required')
    return ref


def bound_catalog(decision, base, configuration, *, now=None):
    """Opt-in inventory consumer. Existing auth/billing/quality gates remain upstream."""
    ref = inventory_reference(decision)
    source = decision['evidence'][ref]
    require(source.get('source') == 'orca_model_catalog', 'not a host catalog source')
    selected = decision['selected']
    require(all(isinstance(selected[key], str) and selected[key] for key in ('model', 'effort')),
            'selected model/effort absent; reprepare')
    return observed_catalog(source, decision['binding']['host_catalog'], base, configuration,
                            selected, now=now)


def observed_catalog(source, context, base, configuration, selected=None, *, now=None):
    require(context['configuration_sha256'] == configuration['configuration_sha256'],
            'observed Company configuration changed; reprepare')
    path = (Path(base) / source['file']).resolve()
    require(path.name == 'manifest.json', 'catalog evidence must pin manifest.json')
    selected = {} if selected is None else selected
    value = load(path.parent, source['sha256'], worktree=context['worktree'],
                 model=selected.get('model'), effort=selected.get('effort'), now=now)
    require(value['runtime_id'] == context['runtime_id'], 'catalog runtime binding changed')
    host = value.get('host')
    if host is not None:
        verify_local_host(value)
    observations = context['observed_files']
    require(isinstance(observations, list) and observations, 'observed config/auth policy files required')
    require({'config', 'auth_policy'} <= {row['role'] for row in observations},
            'explicit config and auth policy observations required')
    from semantic_settings import KIND, LEGACY_VERSION, validate_rows
    require(all(row.get('kind') in (None, 'file', KIND) for row in observations),
            'unknown observation kind')
    saved_only = value['app_version'] in SAVED_ONLY_VERSIONS
    if saved_only or any(row.get('kind') == KIND for row in observations):
        validate_rows(observations, context['worktree'],
                      app_version=value['app_version'] if saved_only else LEGACY_VERSION,
                      user_data=host['user_data'] if host is not None else None)
    for row in observations:
        if row.get('kind') == KIND:
            continue
        path = Path(row['path'])
        require(path.is_absolute(), 'observed file path must be absolute')
        # Legacy byte/absence observations remain unchanged outside the DB.
        digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
        require(digest == row['sha256'], 'observed config/auth policy changed; reprepare')
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--worktree', required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--effort', required=True)
    parser.add_argument('--for-launch', action='store_true', help='metadata alone is not a checked-launch permission')
    args = parser.parse_args()
    try:
        value = load(args.directory, args.sha256, worktree=args.worktree, model=args.model, effort=args.effort)
        if args.for_launch:
            require_launch_authority(value)
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError, AttributeError, OverflowError) as error:
        print(json.dumps({'ok': False, 'error': str(error), 'launch_authorized': False}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
