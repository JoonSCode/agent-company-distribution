"""Strict preregistration declarations only; never execute evaluator or oracle."""
import re
from collections import Counter
from offline_sidecar import read_json


def validate(root, name):
    d = read_json(root, name)
    def need(ok, message):
        if not ok: raise ValueError(message)
    def obj(v, keys, label):
        need(isinstance(v, dict) and set(v) == set(keys), 'invalid ' + label)
    def ident(v):
        return isinstance(v, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', v) is not None
    def ids(v):
        return isinstance(v, list) and bool(v) and all(ident(x) for x in v) and len(v) == len(set(v))
    obj(d, {'format', 'population', 'holdout', 'assignment', 'evaluator', 'stopping', 'measurement', 'metrics', 'approval_gates'}, 'spec fields')
    need(d['format'] == 'company-experiment-spec/v1', 'unsupported spec version')
    obj(d['population'], {'description', 'development_tasks'}, 'population')
    need(isinstance(d['population']['description'], str) and bool(d['population']['description'].strip()) and ids(d['population']['development_tasks']), 'task population required')
    obj(d['holdout'], {'tasks', 'independent', 'selection_ref'}, 'holdout')
    h = d['holdout']
    need(ids(h['tasks']) and h['independent'] is True and ident(h['selection_ref']) and not set(h['tasks']) & set(d['population']['development_tasks']), 'independent disjoint holdout required')
    obj(d['assignment'], {'frozen_ref', 'orders'}, 'assignment')
    a = d['assignment']
    need(ident(a['frozen_ref']) and isinstance(a['orders'], list) and bool(a['orders']), 'frozen assignment required')
    counts = Counter()
    for row in a['orders']:
        obj(row, {'task', 'repeat', 'order'}, 'assignment row')
        need(row['task'] in h['tasks'] and type(row['repeat']) is int and 1 <= row['repeat'] <= 10000 and row['order'] in (['baseline', 'candidate'], ['candidate', 'baseline']), 'invalid assignment row')
        key = (row['task'], row['repeat'])
        need(key not in counts, 'duplicate assignment')
        counts[key] = 1
    for task in h['tasks']:
        orders = Counter(tuple(x['order']) for x in a['orders'] if x['task'] == task)
        need(orders[('baseline','candidate')] > 0 and orders[('baseline','candidate')] == orders[('candidate','baseline')], 'balanced per-task order required')
    obj(d['evaluator'], {'executor', 'assessor', 'oracle_ref', 'separation'}, 'evaluator')
    e = d['evaluator']
    need(all(ident(e[k]) for k in ('executor', 'assessor', 'oracle_ref')) and e['executor'] != e['assessor'] and e['separation'] is True, 'separate evaluator and oracle reference required')
    obj(d['stopping'], {'rule_ref', 'denominator'}, 'stopping')
    need(ident(d['stopping']['rule_ref']) and d['stopping']['denominator'] == 'all_planned_including_failures_aborted_missing_unknown', 'stopping rule and full failure denominator required')
    obj(d['measurement'], {'coverage', 'provenance', 'missing'}, 'measurement')
    m = d['measurement']
    need(ids(m['coverage']) and set(m['coverage']) == {'lead', 'worker', 'review', 'integration', 'retry'} and m['provenance'] == 'attributable_receipts' and m['missing'] == 'unknown', 'full-stage measurement provenance and unknown required')
    need(ids(d['metrics']) and {'wall_time', 'quality', 'user_burden'} <= set(d['metrics']), 'wall time, quality and user burden metrics required')
    need(ids(d['approval_gates']) and {'execution_authority', 'resource_authority', 'measurement_authority'} <= set(d['approval_gates']), 'approval gates required')
    return {'format': d['format'], 'status': 'valid_declaration', 'holdout_tasks': len(h['tasks']), 'planned_pairs': len(a['orders']), 'execution_performed': False, 'limits': 'Declarations do not authenticate independence, approvals, receipts or real outcomes.'}
