"""Pure, offline assessment of a supplied timeline projection and outcome evidence.

No receipt authenticity, independent approval or release authority is conferred.
"""
import json
from pathlib import Path
import re
import sys

if __name__ == '__main__':
    sys.dont_write_bytecode = True

from outcome_eval import trial_status
from stage_timeline import inspect_file, project


def assess(projection, candidate, outcome, review, consent, release):
    """Return a deterministic assessment; callers supply all evidence explicitly."""
    if projection.get('format') != 'company-stage-timeline/v1' or projection.get('ok') is not True:
        return {'status': 'refused', 'reason': 'invalid projection'}
    current = [a for a in projection.get('attempts', []) if a.get('current') is True]
    if len(current) != 1:
        return {'status': 'refused', 'reason': 'ambiguous current attempt'}
    attempt = current[0]
    if (not isinstance(candidate, dict) or not re.fullmatch(r'[0-9a-f]{40}', candidate.get('revision', '')) or not re.fullmatch(r'[0-9a-f]{64}', candidate.get('sha256', ''))
            or attempt.get('binding', {}).get('revision') != candidate['revision']
            or outcome.get('candidate_sha256') != candidate['sha256']):
        return {'status': 'refused', 'reason': 'candidate mismatch'}
    if not review or review.get('candidate') != candidate or not review.get('assessor') or not review.get('executor') or review.get('assessor') == review.get('executor') or review.get('critical_failure') not in (True, False, None):
        return {'status': 'refused', 'reason': 'independent candidate review missing'}
    stages = {s['stage']: s['status'] for s in attempt['stages']}
    if len(stages) != len(attempt['stages']):
        return {'status': 'refused', 'reason': 'duplicate stage'}
    if stages.get('routing_precheck') == 'rejected':
        return {'status': 'refused', 'reason': 'precheck rejected'}
    status, critical = trial_status(outcome['reported'], outcome['execution'], outcome['checks'],
                                    review.get('critical_failure'), outcome['trace_present'])
    if any(stages.get(name) != expected for name, expected in (('launch', 'observed'), ('worker_report', 'succeeded'), ('worker_settlement', 'completed'))):
        status = 'unknown' if status == 'success' else status
    usage = attempt.get('usage') or {}
    return {'status': status, 'critical_failure': critical,
            'candidate': candidate, 'binding': attempt['binding'],
            'stage_evidence': {s['stage']: s.get('evidence', []) for s in attempt['stages']}, 'usage': {'coverage': usage.get('coverage'),
            'observed_raw_total': usage.get('observed_raw_total'),
            'task_total_raw_tokens': usage.get('total_raw_tokens') if usage.get('coverage') == 'complete' else None,
            'whole_run_total': None}, 'consent_declared': consent is True, 'release_authorization_declared': release is True,
            'overall_acceptance': None, 'measured_savings': None}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv in (['-h'], ['--help']):
        print('usage: offline_replay.py TIMELINE_MANIFEST ASSESSMENT_INPUT')
        return 0
    try:
        if len(argv) != 2 or any(arg.startswith('-') for arg in argv):
            raise ValueError('expected two input files')
        manifest_path, assessment_path = (Path(arg).absolute() for arg in argv)
        manifest_info, manifest = inspect_file(manifest_path)
        assessment_info, assessment = inspect_file(assessment_path)
        if any(info['status'] != 'present' or info['json_status'] != 'valid'
               for info in (manifest_info, assessment_info)):
            raise ValueError('missing or invalid input')
        if not isinstance(assessment, dict) or set(assessment) != {
                'candidate', 'outcome', 'review', 'consent', 'release'}:
            raise ValueError('invalid assessment input')
        result = assess(project(manifest, manifest_path.parent), **assessment)
    except (OSError, ValueError, AttributeError, TypeError, KeyError):
        print(json.dumps({'status': 'refused', 'reason': 'invalid replay input'}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 2 if result['status'] == 'refused' else 0


if __name__ == '__main__':
    raise SystemExit(main())
