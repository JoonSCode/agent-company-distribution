#!/usr/bin/env python3
"""Read-only timeline of explicitly pinned Company receipts."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

if __name__ == '__main__':
    sys.dont_write_bytecode = True

from org_audit import InputError, identity, mapping, normalize, sequence, strict_json
from routing_explain import STATES, inspect_file

SOURCE_KEYS = ('precheck', 'launch', 'worker_done', 'settlement', 'usage')
ROUTING_REASON_CODES = ('hash_mismatch', 'parent_binding', 'planned_required',
                        'run_binding', 'selected_runtime_invalid', 'spec_binding',
                        'synthetic_launch', 'type', 'value')
INSTALL_PHASES = ('created', 'preflight_all', 'stage_all', 'backup_managed',
                  'apply_snapshot', 'apply_skills', 'apply_agents', 'write_indexes',
                  'commit_active_hashes', 'cleanup')
OFFSET_TIME = re.compile(
    r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}'
    r'(?:\.[0-9]{1,6})?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])'
)


class TimelineError(ValueError):
    """An invalid or conflicting input with a fixed, safe error code."""


def require(condition, code):
    if not condition:
        raise TimelineError(code)


def digest_id(value):
    return hashlib.sha256(identity(value).encode('utf-8')).hexdigest()


def pinned(source, base):
    source = mapping(source)
    require(set(source) == {'file', 'sha256'}, 'invalid_source_ref')
    expected = source['sha256']
    require(isinstance(expected, str) and re.fullmatch('[0-9a-f]{64}', expected),
            'invalid_source_pin')
    info, document = inspect_file(base / identity(source['file']))
    require(info['status'] == 'present', 'source_unavailable')
    require(info['sha256'] == expected, 'source_hash_mismatch')
    require(info['json_status'] == 'valid', 'invalid_source_json')
    return mapping(document), expected


def evidence(sha256, pointer, embedded_pointer=None):
    result = {'sha256': sha256, 'pointer': pointer}
    if embedded_pointer is not None:
        result['embedded_pointer'] = embedded_pointer
    return result


def stage(name, status, reason, *refs):
    return {'stage': name, 'status': status, 'reason': reason, 'occurred_at': None,
            'observed_at': None, 'duration_ms': None, 'evidence': list(refs)}


def utc_time(value):
    if not isinstance(value, str) or not OFFSET_TIME.fullmatch(value) or value.endswith('-00:00'):
        return None
    try:
        return datetime.fromisoformat(value).astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return None


def envelope(document):
    require(document.get('ok') is True, 'unsuccessful_orca_receipt')
    runtime_id = mapping(document.get('_meta', {})).get('runtimeId')
    return mapping(document.get('result')), identity(runtime_id) if runtime_id is not None else None


def precheck(source, selector):
    if source is None:
        return stage('routing_precheck', 'unknown', 'source_missing'), {}, None
    document, sha256 = source
    report = mapping(document.get('receipt'))
    binding = mapping(report.get('binding'))
    require(type(document.get('ok')) is bool
            and document.get('label') in ('real', 'synthetic')
            and report.get('format') == 'company-routing-decision/v1'
            and type(binding.get('planned')) is bool, 'invalid_precheck')
    require(binding.get('revision') == selector['revision'], 'revision_mismatch')
    for run in (binding.get('run'), report.get('requested_run')):
        require(run is None or run == selector['run'], 'run_mismatch')
    # Planned spec launches may use a local task alias before Orca allocates its ID.
    if binding['planned'] is False or report.get('task_list') is not None:
        require(binding.get('task') == selector['task'], 'task_mismatch')
    result = stage('routing_precheck', 'passed' if document['ok'] else 'rejected',
                   'routing_report', evidence(sha256, '/ok'), evidence(sha256, '/receipt/binding'))
    if not document['ok']:
        error_codes = [mapping(error).get('code') for error in sequence(document.get('errors', []))]
        result['reason_codes'] = [code for code in ROUTING_REASON_CODES if code in error_codes]
        if 'errors' in document:
            result['evidence'].append(evidence(sha256, '/errors'))
    return result, report, sha256


def checked_launch(source, selector, check_stage, report, precheck_sha):
    if source is None:
        return stage('launch', 'unknown', 'source_missing'), None
    document, sha256 = source
    state = identity(document.get('launch_state'))
    require(type(document.get('launch_state_version')) is int
            and document['launch_state_version'] == 1 and state in STATES,
            'invalid_launch_state')
    for field in ('decision_sha256', 'prelaunch_receipt_sha256'):
        if field in document:
            require(isinstance(document[field], str) and re.fullmatch('[0-9a-f]{64}', document[field]),
                    'invalid_launch_pin')
    if state != 'not_started':
        require('decision_sha256' in document, 'decision_pin_missing')
    if precheck_sha is not None:
        if 'prelaunch_receipt_sha256' in document:
            require(document['prelaunch_receipt_sha256'] == precheck_sha, 'precheck_pin_mismatch')
        if 'decision_sha256' in document:
            require(document['decision_sha256'] == report.get('decision_sha256'), 'decision_pin_mismatch')
    ref = evidence(sha256, '/launch_state')
    readback = document.get('readback_status')
    if state == 'not_started':
        require(readback is None, 'conflicting_readback')
        return stage('launch', 'not_started', 'local_state_only', ref), None

    if precheck_sha is not None:
        require(check_stage['status'] == 'passed', 'rejected_precheck_with_invocation')
    if state != 'observed':
        require(readback in (None, 'failed', 'unverified'), 'conflicting_readback')
        if document.get('error_code') == 'host_start_timeout':
            return stage('launch', 'unknown', 'host_start_timeout', ref,
                         evidence(sha256, '/error_code')), None
        if readback is not None:
            return stage('launch', 'unknown', 'host_readback_' + readback, ref,
                         evidence(sha256, '/readback_status')), None
        return stage('launch', 'unknown', state, ref), None
    require(readback == 'observed' and type(document.get('exit_code')) is int
            and document['exit_code'] == 0, 'conflicting_readback')
    require('prelaunch_receipt_sha256' in document, 'precheck_pin_missing')

    host = strict_json(identity(document.get('stdout')))
    payload, runtime = envelope(mapping(host))
    facts = normalize({'id': 'launch', 'format': 'orca_launch'}, host)[0]['facts']
    require(facts['run_id'] == selector['run'] and facts['task_id'] == selector['task'],
            'launch_binding_mismatch')
    dispatch = facts['dispatch_id']
    actor = facts.get('executed_by')
    concise_actor = payload.get('terminal')
    if concise_actor is not None:
        concise_actor = identity(concise_actor)
        require(actor is None or actor == concise_actor, 'launch_executor_mismatch')
        actor = concise_actor
    binding = report.get('binding', {})
    predecessor = binding.get('attempt') if binding.get('planned') is False else None
    require(dispatch != predecessor, 'reused_dispatch')
    refs = [ref, evidence(sha256, '/readback_status'), evidence(sha256, '/stdout', '/result')]
    return stage('launch', 'observed', 'checked_readback', *refs), {
        'dispatch': dispatch, 'actor': actor, 'runtime': runtime, 'predecessor': predecessor,
    }


def worker_report(source, selector, launch, known_dispatches):
    if source is None:
        return stage('worker_report', 'unknown', 'source_missing')
    document, sha256 = source
    result, runtime = envelope(document)
    require(result.get('runId') in (None, selector['run']), 'report_run_mismatch')
    messages = sequence(result.get('messages'))
    if launch is None:
        return stage('worker_report', 'unknown', 'launch_binding_missing',
                     evidence(sha256, '/result/messages'))
    require(runtime is None or launch['runtime'] is None or runtime == launch['runtime'],
            'report_runtime_mismatch')
    matches, message_ids = [], set()
    for index, message in enumerate(messages):
        message = mapping(message)
        if message.get('type') != 'worker_done':
            continue
        payload = message.get('payload')
        payload = mapping(strict_json(payload) if isinstance(payload, str) else payload)
        task, dispatch = identity(payload.get('taskId')), identity(payload.get('dispatchId'))
        if task != selector['task']:
            require(dispatch != launch['dispatch'], 'report_task_mismatch')
            continue
        message_id = identity(message.get('id'))
        require(message_id not in message_ids, 'duplicate_worker_report')
        message_ids.add(message_id)
        if dispatch != launch['dispatch']:
            require(known_dispatches.get(dispatch) == (selector['run'], task), 'report_dispatch_mismatch')
            continue
        require(message.get('run_id') in (None, selector['run']), 'report_run_mismatch')
        actors = [actor for actor in (message.get('from_handle'), message.get('from')) if actor is not None]
        require(launch['actor'] is not None and actors
                and all(actor == launch['actor'] for actor in actors), 'report_executor_mismatch')
        outcome = payload.get('outcome')
        require(outcome in ('succeeded', 'failed'), 'invalid_report_outcome')
        pointer = f'/result/messages/{index}'
        report = stage('worker_report', outcome, 'sender_report', evidence(sha256, pointer))
        stamp = utc_time(message.get('created_at'))
        if stamp is not None:
            report['occurred_at'] = stamp.isoformat().replace('+00:00', 'Z')
        matches.append(report)
    require(len(matches) <= 1, 'duplicate_worker_report')
    return matches[0] if matches else stage('worker_report', 'unknown', 'no_matching_report',
                                         evidence(sha256, '/result/messages'))


def worker_settlement(source, selector, launch, launch_stage, report_stage):
    if source is None:
        return stage('worker_settlement', 'unknown', 'source_missing'), None
    document, sha256 = source
    result, runtime = envelope(document)
    dispatch = mapping(result.get('dispatch'))
    ref = evidence(sha256, '/result/dispatch')
    if launch is None:
        return stage('worker_settlement', 'unknown', 'launch_binding_missing', ref), None
    require((dispatch.get('runId'), dispatch.get('taskId'), dispatch.get('id'))
            == (selector['run'], selector['task'], launch['dispatch']), 'settlement_binding_mismatch')
    require(runtime is None or launch['runtime'] is None or runtime == launch['runtime'],
            'settlement_runtime_mismatch')
    require(launch['actor'] is None or dispatch.get('assigneeHandle') in (None, launch['actor']),
            'settlement_executor_mismatch')
    retry_of = dispatch.get('retryOfDispatchId')
    if retry_of is not None:
        identity(retry_of)
        require(retry_of != launch['dispatch'], 'reused_dispatch')
    if launch['predecessor'] is not None and 'retryOfDispatchId' in dispatch:
        require(retry_of == launch['predecessor'], 'predecessor_mismatch')
    retry_of = retry_of or launch['predecessor']
    status = identity(dispatch.get('status'))
    if status not in ('completed', 'failed', 'cancelled'):
        return stage('worker_settlement', 'unknown', 'terminal_state_missing', ref), retry_of
    reported = report_stage['status']
    require(reported == 'unknown' or (reported, status) in
            (('succeeded', 'completed'), ('failed', 'failed')), 'settlement_report_conflict')

    settled = stage('worker_settlement', status, 'dispatch_status', ref)
    start, finish = (utc_time(dispatch.get(field)) for field in ('dispatchedAt', 'completedAt'))
    if start is not None and finish is not None and finish < start:
        settled['reason'] = 'dispatch_clock_reversed'
        settled['evidence'].append(evidence(sha256, '/result/dispatch/dispatchedAt'))
    else:
        if start is not None:
            launch_stage['occurred_at'] = start.isoformat().replace('+00:00', 'Z')
            launch_stage['evidence'].append(evidence(sha256, '/result/dispatch/dispatchedAt'))
        if finish is not None:
            settled['occurred_at'] = finish.isoformat().replace('+00:00', 'Z')
        else:
            settled['reason'] = 'dispatch_time_unavailable'
    return settled, retry_of


def usage_projection(source, selector, launch):
    result = {'coverage': 'unknown', 'observed_raw_total': None, 'total_raw_tokens': None,
              'evidence': []}
    if source is None:
        return result
    document, sha256 = source
    require(document.get('schema') == 'company-native-usage/v1'
            and document.get('status') == 'reported', 'invalid_usage_report')
    rows = sequence(mapping(document.get('breakdown')).get('task'))
    result['evidence'] = [evidence(sha256, '/breakdown/task')]
    if launch is None:
        return result
    target = [selector['run'], selector['task'], launch['dispatch']]
    matches = []
    for index, row in enumerate(rows):
        row = mapping(row)
        group_id = identity(row.get('id'))
        if group_id.startswith('[') and strict_json(group_id) == target:
            matches.append((index, row))
    require(len(matches) <= 1, 'duplicate_usage_group')
    if not matches:
        return result
    index, row = matches[0]
    result['evidence'] = [evidence(sha256, f'/breakdown/task/{index}')]
    if row.get('attribution') != 'bound':
        return result
    coverage = row.get('coverage')
    observed, total = row.get('observed_raw_total'), row.get('total_raw_tokens')
    require(coverage in ('complete', 'partial', 'unknown'), 'invalid_usage_coverage')
    for count in (observed, total):
        require(count is None or (type(count) is int and count >= 0), 'invalid_usage_count')
    require((coverage == 'complete' and observed is not None and total == observed)
            or (coverage == 'partial' and observed is not None and total is None)
            or (coverage == 'unknown' and observed is None and total is None), 'invalid_usage_coverage')
    return {**result, 'coverage': coverage, 'observed_raw_total': observed, 'total_raw_tokens': total}


def installer_projection(source):
    if source is None:
        return None
    document, sha256 = source
    require(document.get('schema_version') == 'agent-company.install-transaction/v0.2'
            and document.get('status') == 'recovery_required'
            and document.get('phase') in INSTALL_PHASES
            and document.get('action') in ('install', 'update', 'rollback', 'uninstall'),
            'invalid_installer_journal')
    return {'binding': 'unlinked', 'action': document['action'], 'phase': document['phase'],
            **stage('installer_journal', 'recovery_required', 'journal_snapshot',
                    evidence(sha256, '/phase'), evidence(sha256, '/status'),
                    evidence(sha256, '/action'))}


def project(manifest, base):
    """Project pinned receipts without mutating input or consulting host state."""
    try:
        return _project(mapping(manifest), Path(base))
    except (InputError, OSError, UnicodeError, RecursionError, json.JSONDecodeError):
        # The strict reader may include raw keys in its exception message.
        raise TimelineError('invalid_receipt_shape') from None


def _project(manifest, base):
    require(base.is_absolute(), 'base_must_be_absolute')
    require({'version', 'current', 'attempts'} <= manifest.keys()
            and manifest.keys() <= {'version', 'current', 'attempts', 'installer'}
            and type(manifest['version']) is int and manifest['version'] == 1,
            'invalid_manifest')
    current = identity(manifest['current'])
    selectors, prepared, known_dispatches = set(), [], {}
    for selector in sequence(manifest['attempts']):
        selector = mapping(selector)
        keys = {'id', 'run', 'task', 'revision'}
        require(keys <= selector.keys() and selector.keys() <= keys | set(SOURCE_KEYS),
                'invalid_attempt')
        for key in keys:
            identity(selector[key])
        require(re.fullmatch('[0-9a-f]{40}', selector['revision']), 'invalid_revision')
        require(selector['id'] not in selectors, 'duplicate_attempt')
        selectors.add(selector['id'])
        sources = {key: pinned(selector[key], base) if selector.get(key) is not None else None
                   for key in SOURCE_KEYS}
        require(any(sources.values()), 'attempt_evidence_missing')
        check_stage, check, check_pin = precheck(sources['precheck'], selector)
        launch_stage, launch = checked_launch(sources['launch'], selector, check_stage, check, check_pin)
        precheck_link = 'unknown'
        if check_pin is not None and sources['launch'] is not None:
            launch_document, _ = sources['launch']
            if 'prelaunch_receipt_sha256' in launch_document:
                precheck_link = 'receipt_sha256'
            elif 'decision_sha256' in launch_document:
                precheck_link = 'decision_sha256'
        if launch is not None:
            dispatch = launch['dispatch']
            require(dispatch not in known_dispatches, 'duplicate_dispatch')
            known_dispatches[dispatch] = (selector['run'], selector['task'])
        prepared.append((selector, sources, check_stage, launch_stage, launch, precheck_link))
    require(current in selectors, 'current_attempt_missing')
    attempts = []
    for selector, sources, check_stage, launch_stage, launch, precheck_link in prepared:
        report = worker_report(sources['worker_done'], selector, launch, known_dispatches)
        settlement, retry_of = worker_settlement(sources['settlement'], selector, launch,
                                                 launch_stage, report)
        if retry_of in known_dispatches:
            require(known_dispatches[retry_of] == (selector['run'], selector['task']),
                    'predecessor_binding_mismatch')
        attempts.append({
            'id_sha256': digest_id(selector['id']), 'current': selector['id'] == current,
            'binding': {'run_sha256': digest_id(selector['run']),
                        'task_sha256': digest_id(selector['task']),
                        'dispatch_sha256': digest_id(launch['dispatch']) if launch else None,
                        'retry_of_dispatch_sha256': digest_id(retry_of) if retry_of else None,
                        'revision': selector['revision'],
                        'revision_source': 'precheck' if sources['precheck'] else 'manifest',
                        'precheck_link': precheck_link},
            'stages': [check_stage, launch_stage, report, settlement,
                       stage('independent_review', 'unknown', 'source_not_supported'),
                       stage('tool_execution', 'unknown', 'source_not_supported')],
            'usage': usage_projection(sources['usage'], selector, launch),
        })
    installer = manifest.get('installer')
    return {'format': 'company-stage-timeline/v1', 'ok': True, 'coverage': 'supplied_receipts',
            'attempts': attempts,
            'installer': installer_projection(pinned(installer, base) if installer is not None else None),
            'technical_acceptance': None, 'overall_acceptance': None, 'whole_run_total_raw_tokens': None}


def main(argv=None):
    # Avoid argparse's default error echo of untrusted options or path strings.
    argv = sys.argv[1:] if argv is None else argv
    if argv in (['-h'], ['--help']):
        print('usage: stage_timeline.py MANIFEST\nProject a pinned receipt manifest to JSON on stdout.')
        return 0
    try:
        require(len(argv) == 1 and not argv[0].startswith('-'), 'manifest_argument_required')
        path = Path(argv[0]).absolute()
        info, manifest = inspect_file(path)
        require(info['status'] == 'present', 'manifest_unavailable')
        require(info['json_status'] == 'valid', 'invalid_manifest_json')
        result = project(manifest, path.parent)
    except (TimelineError, OSError, ValueError) as exc:
        code = str(exc) if isinstance(exc, TimelineError) else 'manifest_unavailable'
        print(json.dumps({'ok': False, 'error': code}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
