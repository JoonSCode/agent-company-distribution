#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Read explicitly selected Codex JSONL; stdout only, no provider calls."""
import argparse
import hashlib
import json
from pathlib import Path

# Select Python's normal cache prefix before importing Company modules.
# Restrict this to the CLI process; callers importing a module are unchanged.
if __name__ == "__main__":
    import os as _os
    import sys as _sys
    _sys.pycache_prefix = _os.path.join(_os.path.abspath(_os.path.expanduser("~")), ".cache", "agent-company", "python")

FIELDS = ('input_tokens', 'cached_input_tokens', 'cache_write_input_tokens',
          'output_tokens', 'reasoning_output_tokens', 'total_tokens')


class Invalid(ValueError):
    pass


def unique_object(pairs):
    """Reject ambiguous keys at the JSON decoding boundary, including nested objects."""
    value = {}
    for key, item in pairs:
        if key in value:
            raise Invalid('duplicate JSON key')
        value[key] = item
    return value


def counts(value):
    if not isinstance(value, dict) or set(value) != set(FIELDS):
        raise Invalid('unsupported usage fields')
    if any(type(value[k]) is not int or value[k] < 0 for k in FIELDS):
        raise Invalid('counts must be nonnegative integers')
    if value['total_tokens'] != value['input_tokens'] + value['output_tokens']:
        raise Invalid('total differs from input plus output')
    if (value['cached_input_tokens'] > value['input_tokens'] or
            value['cache_write_input_tokens'] > value['input_tokens'] or
            value['reasoning_output_tokens'] > value['output_tokens']):
        raise Invalid('subset exceeds containing count')
    return value


def read_usage(path, expected_sha256, scope, turn_id=None):
    data = Path(path).read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected_sha256:
        raise Invalid('source hash mismatch')
    if not scope or not scope.strip():
        raise Invalid('explicit scope required')
    # Reject malformed/truncated JSON rather than publishing partial data as complete.
    rows = [json.loads(line, object_pairs_hook=unique_object)
            for line in data.decode('utf-8').splitlines()]
    if any(not isinstance(r, dict) or not isinstance(r.get('payload'), dict) for r in rows):
        raise Invalid('unsupported JSONL row')
    sessions = [r['payload'].get('id') for r in rows if r.get('type') == 'session_meta']
    if len(sessions) != 1 or not isinstance(sessions[0], str) or not sessions[0]:
        raise Invalid('exactly one session_meta required')
    session = sessions[0]
    turns = set()
    records, starts, ends, mirrors = {}, {}, {}, {}
    contexts, model_items = [], []
    previous = None
    thread_prefix = dict.fromkeys(FIELDS, 0)
    last_thread = dict.fromkeys(FIELDS, 0)
    for line, row in enumerate(rows, 1):
        p = row['payload']
        if row.get('type') == 'turn_context':
            t = p.get('turn_id')
            if not isinstance(t, str) or not t:
                raise Invalid('turn context missing identity')
            contexts.append((line, t))
        if row.get('type') == 'response_item':
            model_items.append(line)
        if row.get('type') == 'event_msg':
            if p.get('type') == 'agent_message':
                model_items.append(line)
            if p.get('type') == 'item_completed':
                item = p.get('item')
                if not isinstance(item, dict):
                    raise Invalid('unsupported completed item')
                if item.get('type') == 'AgentMessage':
                    model_items.append(line)
        if row.get('type') == 'event_msg' and p.get('type') in ('task_started', 'task_complete'):
            t = p.get('turn_id')
            if not isinstance(t, str) or not t:
                raise Invalid('turn boundary missing identity')
            turns.add(t)
            target = starts if p['type'] == 'task_started' else ends
            if t in target:
                raise Invalid('duplicate turn boundary')
            target[t] = line
        if row.get('type') == 'token_usage_record':
            for key in ('thread_id', 'session_id', 'turn_id', 'root_turn_id', 'response_id'):
                if not isinstance(p.get(key), str) or not p[key]:
                    raise Invalid('usage identity missing')
            if p['thread_id'] != session or p['session_id'] != session:
                raise Invalid('usage session mismatch')
            turns.add(p['turn_id'])
            for key in ('usage', 'turn_token_usage', 'thread_token_usage'):
                counts(p.get(key))
            if any(p['usage'][k] > p['turn_token_usage'][k] or
                   p['turn_token_usage'][k] > p['thread_token_usage'][k] for k in FIELDS):
                raise Invalid('impossible cumulative usage')
            identity = {k: p[k] for k in ('thread_id', 'session_id', 'turn_id', 'root_turn_id',
                                         'response_id', 'usage', 'turn_token_usage', 'thread_token_usage')}
            rid = p['response_id']
            if rid in records and records[rid]['value'] != identity:
                raise Invalid('conflicting duplicate response')
            if rid not in records:
                for k in FIELDS:
                    thread_prefix[k] += p['usage'][k]
                if any(thread_prefix[k] > p['thread_token_usage'][k] or
                       last_thread[k] + p['usage'][k] > p['thread_token_usage'][k]
                       for k in FIELDS):
                    raise Invalid('thread cumulative usage contradicts responses')
                last_thread = p['thread_token_usage']
                records[rid] = {'line': line, 'value': identity}
            previous = identity
        if row.get('type') == 'event_msg' and p.get('type') == 'token_count' and p.get('info') is not None:
            info = p['info']
            total = counts(info.get('total_token_usage'))
            last = counts(info.get('last_token_usage'))
            if previous is None or total != previous['thread_token_usage'] or last != previous['usage']:
                raise Invalid('cumulative mirror does not match response record')
            mirrors[previous['response_id']] = line
    if turn_id is None:
        if len(turns) != 1:
            raise Invalid('explicit --turn-id required for reused or ambiguous session')
        turn_id = next(iter(turns))
    if turn_id not in turns:
        raise Invalid('selected turn not found')
    start, end = starts.get(turn_id, 0), ends.get(turn_id, len(rows) + 1)
    if any(start < line < end and context_turn != turn_id for line, context_turn in contexts):
        raise Invalid('context identity contradicts selected turn boundaries')
    selected = [v for v in records.values() if v['value']['turn_id'] == turn_id]
    totals = {k: sum(r['value']['usage'][k] for r in selected) for k in FIELDS}
    reasons = []
    if not data.endswith(b'\n'):
        reasons.append('missing final newline; capture may be truncated')
    if turn_id not in starts or turn_id not in ends:
        reasons.append('missing selected turn start or completion')
    if not selected:
        reasons.append('no selected response usage')
    else:
        last = selected[-1]
        cumulative = last['value']['turn_token_usage']
        if any(totals[k] > cumulative[k] for k in FIELDS):
            raise Invalid('response sum exceeds turn cumulative usage')
        if totals != cumulative:
            reasons.append('response sum does not cover entire turn cumulative usage')
        # Validate each prefix, so a matching final sum cannot hide corrupt intermediate totals.
        prefix = dict.fromkeys(FIELDS, 0)
        for r in selected:
            for k in FIELDS:
                prefix[k] += r['value']['usage'][k]
            if any(prefix[k] > r['value']['turn_token_usage'][k] for k in FIELDS):
                raise Invalid('response prefix exceeds cumulative usage')
            if prefix != r['value']['turn_token_usage']:
                reasons.append('incomplete intermediate cumulative coverage')
            if r['value']['response_id'] not in mirrors:
                reasons.append('missing cumulative mirror')
        if any(not start < r['line'] < end for r in selected):
            reasons.append('usage outside selected turn boundaries')
        # A trailing model item without subsequent usage could be an uncounted final response.
        if any(last['line'] < line < end for line in model_items):
            reasons.append('response item after final usage')
    coverage = 'complete' if not reasons else ('partial' if selected else 'unknown')
    usage = {'coverage': coverage, 'raw_total': totals['total_tokens'] if selected else None,
             'tokenizer': 'Codex provider-reported; exact tokenizer unknown',
             'scope': scope, 'source': f'sha256:{digest};session:{session};turn:{turn_id}'}
    return {'format': 'company-codex-usage/v1', 'usage': usage,
            'provenance': {'trace_sha256': digest, 'session_id': session, 'turn_id': turn_id,
                           'scope': scope, 'coverage_reasons': sorted(set(reasons)),
                           'coverage_boundary': 'captured selected turn only; not whole Company run',
                           'totals': totals if selected else None,
                           'responses': [{'line': r['line'], **r['value']} for r in selected]}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trace', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--scope', required=True)
    parser.add_argument('--turn-id')
    parser.add_argument('--format', choices=('provenance', 'usage'), default='provenance')
    args = parser.parse_args(argv)
    try:
        result = read_usage(args.trace, args.sha256, args.scope, args.turn_id)
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        # Never echo malformed source content or paths containing private prompt material.
        print(json.dumps({'status': 'invalid', 'error': 'Invalid trace, hash, identity or usage; no complete result emitted.'}))
        return 2
    print(json.dumps(result['usage'] if args.format == 'usage' else result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
