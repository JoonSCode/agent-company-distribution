"""Pinned Codex response union with explicit scope and attribution coverage."""
import json
from pathlib import Path

import provider_usage
from native_operations import (absolute, decode, pinned, pointer, regular, request,
                               require, sha, shape, text, valid_hash)

ATTR = ('run_id', 'task_id', 'dispatch_id', 'actor', 'model')
SOURCE_KEYS = ('id', 'provider', 'trace', 'sha256', 'turn_id', 'scope', *ATTR, 'binding')
DIMENSIONS = {'run': 'run_id', 'task': 'task_id', 'actor': 'actor', 'model': 'model', 'capture': 'id'}


def report(request_path):
    value, base, source_pin = request(request_path, 'company-native-usage-request/v1',
                                      ('schema', 'required_scopes', 'sources'))
    required = value['required_scopes']
    require(isinstance(required, list) and all(isinstance(x, str) and x.strip() for x in required)
            and len(set(required)) == len(required), 'invalid required scopes')
    require(isinstance(value['sources'], list), 'sources must be array')
    captures, identities, memberships, seen = [], {}, {}, set()
    duplicates = 0
    for row in value['sources']:
        shape(row, SOURCE_KEYS, 'usage source')
        for key in ('id', 'provider', 'trace', 'scope'):
            text(row[key], key)
        text(row['turn_id'], 'turn_id', nullable=True)
        for key in ATTR: text(row[key], key, nullable=True)
        valid_hash(row['sha256'])
        require(row['id'] not in seen, 'duplicate source id')
        seen.add(row['id'])
        capture = {k: row[k] for k in ('id', 'provider', 'scope', *ATTR)}
        capture.update(coverage='unknown', attribution='unknown', responses=[],
                       source={'path': str(absolute(row['trace'], base)), 'sha256': row['sha256']},
                       binding=None, reasons=[])
        if row['provider'] != 'codex':
            capture['reasons'] = ['unsupported provider adapter; no token total inferred']
            captures.append(capture)
            continue
        trace = absolute(row['trace'], base)
        trace_raw = regular(trace)
        require(sha(trace_raw) == row['sha256'], 'trace source pin mismatch')
        parsed = provider_usage.read_usage(trace, row['sha256'], row['scope'], row['turn_id'])
        require(regular(trace) == trace_raw, 'trace changed during parsing')
        provenance = parsed['provenance']
        bound = False
        if row['binding'] is not None:
            shape(row['binding'], ('path', 'sha256', 'pointer'), 'usage binding')
            binding_path, binding_raw = pinned({k: row['binding'][k] for k in ('path', 'sha256')}, base)
            binding = pointer(decode(binding_raw), row['binding']['pointer'])
            require(isinstance(binding, dict), 'usage binding must select an object')
            expected = {**{k: row[k] for k in ATTR}, 'provider': row['provider'],
                        'session_id': provenance['session_id'], 'turn_id': provenance['turn_id']}
            require(all(k in binding and binding[k] == expected[k] for k in expected), 'capture/attribution binding conflict')
            capture['binding'] = {**row['binding'], 'path': str(binding_path)}
            capture['evidence_class'] = 'synthetic' if binding.get('synthetic') is True else 'supplied-bound-source'
            bound = True
        capture.update(coverage=parsed['usage']['coverage'], attribution='bound' if bound else 'claimed',
                       reasons=provenance['coverage_reasons'], session_id=provenance['session_id'],
                       turn_id=provenance['turn_id'])
        for response in provenance['responses']:
            identity = (row['provider'], response['response_id'])
            signature = {k: v for k, v in response.items() if k != 'line'}
            if identity in identities:
                require(identities[identity] == signature, 'conflicting provider/response identity')
                duplicates += 1
            else:
                identities[identity] = signature
                memberships[identity] = []
            memberships[identity].append(capture)
            capture['responses'].append(identity)
        captures.append(capture)
    scopes = []
    missing = []
    for scope in sorted(set(required) | {x['scope'] for x in captures}):
        rows = [x for x in captures if x['scope'] == scope]
        if scope in required and not rows: missing.append(scope)
        complete = bool(rows) and all(x['coverage'] == 'complete' and x['attribution'] == 'bound' for x in rows)
        response_keys = {k for row in rows for k in row['responses']}
        observed = sum(identities[k]['usage']['total_tokens'] for k in response_keys) if response_keys else None
        scopes.append({'id': scope, 'coverage': 'complete' if complete else 'partial' if response_keys else 'unknown',
                       'attribution': 'bound' if rows and all(x['attribution'] == 'bound' for x in rows) else 'unknown',
                       'observed_raw_total': observed, 'total_raw_tokens': observed if complete else None})
    full = bool(required) and not missing and bool(captures) and all(
        x['coverage'] == 'complete' and x['attribution'] == 'bound' for x in captures)
    observed = sum(x['usage']['total_tokens'] for x in identities.values()) if identities else None
    breakdown = {}
    for dimension, field in DIMENSIONS.items():
        def group_value(capture):
            if dimension == 'task':
                parts = [capture[k] for k in ('run_id', 'task_id', 'dispatch_id')]
                return json.dumps(parts, ensure_ascii=False, separators=(',', ':')) if all(parts) else None
            return capture[field]
        groups = {}
        for identity, associations in memberships.items():
            values = {group_value(x) for x in associations}
            shared = len(values) > 1
            key = 'shared/unallocated' if shared else next(iter(values)) or 'unknown'
            group = groups.setdefault(key, {'id': key, 'response_ids': [], 'observed_raw_total': 0,
                                             'coverage': 'complete', 'attribution': 'bound'})
            group['response_ids'].append({'provider': identity[0], 'response_id': identity[1]})
            group['observed_raw_total'] += identities[identity]['usage']['total_tokens']
            if any(x['coverage'] != 'complete' for x in associations): group['coverage'] = 'partial'
            if shared: group['attribution'] = 'shared/unallocated'
            elif key == 'unknown': group['attribution'] = 'unknown'
            elif any(x['attribution'] != 'bound' for x in associations): group['attribution'] = 'claimed'
        # Captures without parseable responses still appear, never as a zero total.
        for capture in captures:
            if capture['responses']: continue
            key = group_value(capture) or 'unknown'
            group = groups.setdefault(key, {'id': key, 'response_ids': [], 'observed_raw_total': None,
                                             'coverage': 'unknown', 'attribution': 'unknown'})
            group['coverage'] = 'partial' if group['response_ids'] else 'unknown'
            group['attribution'] = 'unknown'
        for group in groups.values():
            # Unknown required capture is visible on every grouping, not laundered
            # into an apparently complete model/task subtotal.
            if not full and group['coverage'] == 'complete': group['coverage'] = 'partial'
            group['total_raw_tokens'] = (group['observed_raw_total'] if group['coverage'] == 'complete' and
                                         group['attribution'] == 'bound' else None)
        breakdown[dimension] = [groups[key] for key in sorted(groups)]
    return {'schema': 'company-native-usage/v1', 'status': 'reported',
            'sources': [source_pin], 'coverage': 'complete' if full else 'partial' if identities else 'unknown',
            'required_scopes': required, 'missing_required_scopes': missing, 'scopes': scopes,
            'observed_raw_total': observed, 'total_raw_tokens': observed if full else None,
            'deduped_response_count': len(identities), 'duplicate_response_count': duplicates,
            'conflicts': [], 'unsupported_source_count': sum(x['provider'] != 'codex' for x in captures),
            'captures': captures, 'breakdown': breakdown,
            'unknown_attribution': {k: sum(x[field] is None or x['attribution'] != 'bound' for x in captures)
                                    for k, field in DIMENSIONS.items()},
            'limits': ['Captured required scopes only, not whole-account/24h/7d/fleet usage.',
                       'Binding is supplied provenance, not authenticated execution or billing evidence.',
                       'Cached/reasoning counts are subsets, never additional tokens.',
                       'No currency, savings, skill attribution or unsupported provider estimates.']}
