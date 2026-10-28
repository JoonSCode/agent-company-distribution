#!/usr/bin/env python3
"""Pure task-fit selection. No model, provider, host, network or billing calls."""
from decimal import Decimal
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from company_config import ROUTE_ALIASES, route_errors

TABLE = Path(__file__).resolve().parents[1] / 'assets/model-choice-priors.json'
STAGES = ('instructions', 'execution', 'feedback', 'failures', 'retries', 'review', 'integration')
TOKEN_FIELDS = ('uncached_input', 'cached_input', 'cache_write_30m', 'output')
LIMITS = ('Selection advice from supplied classifications and evidence, not execution permission, '
          'authentication, effective-setting readback, actual subscription charges or measured savings.')


class SelectionError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise SelectionError(message)


def obj(value, keys, name):
    require(isinstance(value, dict) and set(value) == set(keys), name + ': incorrect fields')
    return value


def choice(value, values, name):
    require(isinstance(value, str) and value in values, name + ': unknown value')
    return value


def evidence(ref, refs, name, host=False, synthetic=False):
    require(isinstance(ref, str) and ref in refs and isinstance(refs[ref], dict), name + ': missing evidence')
    if host:
        require(refs[ref].get('kind') == ('synthetic' if synthetic else 'host'),
                name + ': requires host evidence, not owner-reported or catalog availability')
    return ref


def amount(value, name):
    require(type(value) in (int, float), name + ': expected nonnegative finite number')
    number = Decimal(str(value))
    require(number.is_finite() and number >= 0, name + ': expected nonnegative finite number')
    return number


def identity(candidate):
    return tuple(candidate[k] for k in ('route', 'family', 'model', 'effort'))


def exact_task_fit(candidate, task, refs):
    """An explicit source-bound exception, not a bare adequate assertion."""
    quality = refs[candidate['quality_evidence']]
    fit = quality.get('task_fit')
    if fit is None:
        return False
    obj(fit, ('task_evidence', 'candidate', 'support', 'rationale'), 'exact task fit')
    require(fit['task_evidence'] == task['evidence'], 'Task-fit evidence is not bound to this classification')
    obj(fit['candidate'], ('route', 'family', 'model', 'effort'), 'task-fit candidate')
    require(identity(fit['candidate']) == identity(candidate), 'Task-fit evidence is for a different model/effort')
    evidence(fit['support'], refs, 'task-fit support')
    require(fit['support'] != candidate['quality_evidence'], 'Task fit needs separate supporting evidence')
    require(isinstance(fit['rationale'], str) and fit['rationale'].strip(),
            'Task fit needs a specific adequacy rationale, not just an adequate flag')
    return True


def load_table():
    data = TABLE.read_bytes()
    return json.loads(data), hashlib.sha256(data).hexdigest()


def estimated_cost(estimate, models, refs):
    """Disjoint billable token categories, full requests, explicit zero/unknown stages."""
    if estimate is None:
        return {'basis': 'unknown', 'total_api_price_proxy_usd': None, 'stage_usd': {s: None for s in STAGES}}
    obj(estimate, ('basis', 'evidence', 'stages'), 'usage_estimate')
    require(estimate['basis'] == 'estimate', 'Selector accepts estimates, not claims of actual usage')
    evidence(estimate['evidence'], refs, 'usage estimate')
    stages = obj(estimate['stages'], STAGES, 'usage stages')
    total, seen, stage_costs, complete = Decimal(0), set(), {}, True
    for stage, units in stages.items():
        if units is None:
            stage_costs[stage] = None
            complete = False
            continue
        require(isinstance(units, list), 'stage must be a list or null')
        subtotal = Decimal(0)
        for unit in units:
            obj(unit, ('id', 'model', *TOKEN_FIELDS, 'tools_usd', 'tier', 'region'), 'usage unit')
            require(isinstance(unit['model'], str) and unit['model'] in models, 'Unknown model in usage estimate')
            rate = models[unit['model']]['usd_per_million_standard']
            key = unit['id']
            require(isinstance(key, str) and key.strip() and key not in seen,
                    'Usage IDs must be unique: do not duplicate instructions, retries or review')
            seen.add(key)
            # Other billing surfaces remain unknown rather than silently applying Standard rates.
            require(unit['tier'] == 'standard' and unit['region'] == 'global',
                    'Unsupported price context: supply a separately verified rate basis')
            for field in TOKEN_FIELDS:
                require(type(unit[field]) is int and unit[field] >= 0, 'Token estimate must be a nonnegative integer')
            long_request = sum(unit[f] for f in TOKEN_FIELDS[:-1]) > 272000
            for field in TOKEN_FIELDS:
                multiplier = Decimal('1.5' if field == 'output' else '2') if long_request else Decimal(1)
                subtotal += Decimal(unit[field]) * Decimal(str(rate[field])) * multiplier / Decimal(1000000)
            subtotal += amount(unit['tools_usd'], 'tools_usd')
        stage_costs[stage] = float(subtotal)
        total += subtotal
    return {'basis': 'whole_work_estimate' if complete else 'incomplete_estimate',
            'total_api_price_proxy_usd': float(total) if complete else None, 'stage_usd': stage_costs}


def select(selection, refs, configuration, *, synthetic=False, table=None, table_sha256=None, prelaunch=False, requested=None, host_models=None, current_runtime=True, explicit_pin=False, legacy_record=False):
    """LLM supplies semantics/quality fit; deterministic code applies gates and prices."""
    fields = ('version', 'task', 'cost_basis', 'scope_api_authorized', 'candidates')
    obj(selection, (*fields, 'inventory_evidence') if prelaunch or 'inventory_evidence' in selection else fields, 'price_selection')
    require(type(selection['version']) is int and selection['version'] == 1, 'Unknown selection version')
    require(type(selection['scope_api_authorized']) is bool, 'scope_api_authorized must be boolean')
    task = obj(selection['task'], ('actor', 'capability', 'complexity', 'coupling', 'decomposable',
                                  'stage', 'uncertainty', 'evidence'), 'semantic task')
    choice(task['actor'], ('company_head', 'team_lead', 'worker'), 'actor')
    choice(task['capability'], ('focused', 'visual_writing', 'coding', 'judgment'), 'capability')
    choice(task['complexity'], ('bounded', 'complex'), 'complexity')
    choice(task['coupling'], ('local', 'coupled'), 'coupling')
    choice(task['stage'], ('outcome', 'execution', 'consultation'), 'stage')
    choice(task['uncertainty'], ('none', 'ambiguity', 'conflict', 'repeated_failure'), 'uncertainty')
    require(type(task['decomposable']) is bool, 'decomposable must be boolean')
    evidence(task['evidence'], refs, 'semantic classification')
    if task['stage'] == 'consultation':
        require(task['uncertainty'] != 'none', 'Consultation requires genuine ambiguity, conflict or repeated failure')
    if task['complexity'] == 'complex' and task['decomposable'] and task['stage'] == 'outcome':
        return {'status': 'decompose', 'selected': None,
                'next': 'Separate the hard design/contract/judgment from bounded execution; classify each real work unit.',
                'limits': LIMITS}
    basis = choice(selection['cost_basis'], ('benchmark_prior', 'whole_work_estimate'), 'cost basis')
    require(isinstance(selection['candidates'], list) and selection['candidates'], 'No candidates supplied')
    if prelaunch:
        ref = evidence(selection['inventory_evidence'], refs, 'candidate inventory', host=True, synthetic=synthetic)
        if not synthetic:
            require(isinstance(refs[ref].get('file'), str) and isinstance(refs[ref].get('sha256'), str),
                    'Candidate inventory requires a pinned host evidence file')
        inventory = refs[ref].get('candidate_inventory')
        require(isinstance(inventory, list) and inventory, 'Candidate inventory must enumerate the considered model and effort pairs')
        for item in inventory:
            obj(item, ('route', 'family', 'model', 'effort'), 'inventory candidate')
        require(len({identity(item) for item in inventory}) == len(inventory), 'Duplicate inventory candidate')
        require({identity(item) for item in inventory} == {identity(item) for item in selection['candidates']},
                'Candidate list differs from supplied host inventory')
    if table is None:
        table, table_sha256 = load_table()
    require(table.get('version') == 1, 'Unknown candidate table version')
    models = table['models']
    if prelaunch and requested:
        require(isinstance(host_models, list), 'Pinned Codex model inventory is required')
        effort = requested.get('effort')
        requested_model = models.get(requested.get('model'), {})
        requested_prior = requested_model.get('ale_v1_user_transcription', {}).get(effort)
        known = set()
        for host in host_models:
            require(isinstance(host, dict) and isinstance(host.get('slug'), str) and isinstance(host.get('supported_reasoning_levels'), list),
                    'Malformed host model inventory')
            model = models.get(host['slug'])
            levels = {item.get('effort') for item in host['supported_reasoning_levels'] if isinstance(item, dict)}
            if model and host['slug'] not in configuration['values'].get('excluded_models', []):
                for level in levels.intersection(model['efforts']):
                    prior = model['ale_v1_user_transcription'].get(level)
                    if prior is None:
                        continue
                    dominates = (requested_prior is not None and prior['score_percent'] >= requested_prior['score_percent']
                                 and prior['usd_per_task'] <= requested_prior['usd_per_task']
                                 and (prior['score_percent'] > requested_prior['score_percent']
                                      or prior['usd_per_task'] < requested_prior['usd_per_task']))
                    if requested.get('route') != 'codex' or level == effort or dominates:
                        known.add(('codex', model['family'], host['slug'], level))
        supplied = {identity(row) for row in selection['candidates']}
        require(known <= supplied, 'Known Codex host and table model/effort omitted from candidates')
    eligible, rejected, seen = [], [], set()
    for candidate in selection['candidates']:
        obj(candidate, ('route', 'family', 'model', 'effort', 'supported', 'authenticated', 'tools',
                        'billing', 'runtime_evidence', 'quality', 'quality_evidence', 'usage_estimate'), 'candidate')
        for field in ('route', 'family', 'model'):
            require(isinstance(candidate[field], str) and candidate[field], 'Incomplete model/effort identity')
        require(candidate['effort'] is None or (isinstance(candidate['effort'], str) and candidate['effort'].strip()),
                'Incomplete model/effort identity')
        key = identity(candidate)
        require(key not in seen, 'Duplicate candidate')
        seen.add(key)
        # The table is scoped to the Codex path. A different service offering
        # the same model ID is a separate, independently evidenced candidate.
        model = models.get(candidate['model']) if candidate['route'] == 'codex' or legacy_record else None
        if model is not None:
            require(candidate['effort'] in model['efforts'] and candidate['family'] == model['family'],
                    'Unsupported table model/effort/family combination')
        else:
            require(candidate['route'] != 'codex',
                    'Unknown Codex model: refresh source table, never infer an alias')
        require(type(candidate['supported']) is bool and type(candidate['authenticated']) is bool,
                'Unknown or malformed runtime support/authentication; no automatic fallback')
        choice(candidate['tools'], ('supported', 'unsupported', 'unknown'), 'tools')
        choice(candidate['billing'], ('subscription', 'paid_api', 'unknown'), 'billing')
        choice(candidate['quality'], ('adequate', 'insufficient', 'unknown'), 'quality')
        evidence(candidate['runtime_evidence'], refs, 'candidate runtime', host=True, synthetic=synthetic)
        evidence(candidate['quality_evidence'], refs, 'task-specific quality fit')
        require(candidate['tools'] != 'unknown' and candidate['billing'] != 'unknown',
                'Unknown tools or billing; no automatic fallback')
        if model is None:
            runtime = refs[candidate['runtime_evidence']].get('unlisted_runtime')
            obj(runtime, ('candidate', 'agent', 'host', 'supported', 'authenticated', 'tools', 'billing',
                          'model_evidence', 'support_evidence', 'auth_evidence', 'tools_evidence',
                          'billing_evidence', 'observed_at', 'valid_until'), 'unlisted runtime')
            require(runtime['candidate'] == dict(zip(('route', 'family', 'model', 'effort'), key)),
                    'Unlisted runtime must bind the exact candidate and effort')
            require(runtime['agent'] == ROUTE_ALIASES.get(candidate['route'], candidate['route']),
                    'Unlisted runtime must bind the actual agent route')
            require(isinstance(runtime['host'], str) and runtime['host'].strip(),
                    'Unlisted runtime requires the observed host')
            require(all(runtime[field] == candidate[field] for field in ('supported', 'authenticated', 'tools', 'billing')),
                    'Unlisted runtime observations do not match candidate support, authentication, tools or billing')
            for field in ('model_evidence', 'support_evidence', 'auth_evidence', 'tools_evidence', 'billing_evidence'):
                ref = evidence(runtime[field], refs, 'unlisted ' + field, host=True, synthetic=synthetic)
                if not synthetic:
                    require(isinstance(refs[ref].get('file'), str) and isinstance(refs[ref].get('sha256'), str),
                            'Unlisted runtime evidence needs a pinned host file')
                    require(refs[ref].get('host') == runtime['host'], 'Unlisted evidence is for a different host')
                    try:
                        source_at = datetime.fromisoformat(refs[ref]['observed_at'].replace('Z', '+00:00'))
                        source_until = datetime.fromisoformat(refs[ref]['valid_until'].replace('Z', '+00:00'))
                    except (KeyError, ValueError, AttributeError, TypeError):
                        raise SelectionError('Unlisted host evidence freshness is malformed')
                    require(source_at.tzinfo is not None and source_until.tzinfo is not None and source_at <= source_until,
                            'Unlisted host evidence freshness is malformed')
                    if prelaunch and current_runtime:
                        require(source_at <= datetime.now(timezone.utc) <= source_until,
                                'Unlisted host evidence freshness is expired or unknown')
            try:
                observed = datetime.fromisoformat(runtime['observed_at'].replace('Z', '+00:00'))
                until = datetime.fromisoformat(runtime['valid_until'].replace('Z', '+00:00'))
            except (ValueError, AttributeError, TypeError):
                raise SelectionError('Unlisted runtime freshness is malformed')
            require(observed.tzinfo is not None and until.tzinfo is not None and observed <= until,
                    'Unlisted runtime freshness is malformed')
            if prelaunch and current_runtime:
                require(observed <= datetime.now(timezone.utc) <= until,
                        'Unlisted runtime freshness is expired or unknown')
            require(candidate['usage_estimate'] is None,
                    'Unlisted model has no verified rate in the table; do not fabricate an estimate')
            if candidate['quality'] == 'adequate':
                require(exact_task_fit(candidate, task, refs), 'Unlisted candidate needs exact task-fit evidence')
                if not synthetic:
                    fit = refs[candidate['quality_evidence']]['task_fit']
                    for ref in (candidate['quality_evidence'], fit['support']):
                        item = refs[ref]
                        require(item.get('kind') in ('human', 'independent', 'host', 'source', 'provider')
                                and isinstance(item.get('file'), str) and isinstance(item.get('sha256'), str),
                                'Unlisted task-fit and support need separate pinned real evidence files')
        if prelaunch:
            require(candidate['quality'] != 'unknown', 'Unknown quality cannot establish a task-specific exclusion')
            if candidate['quality'] == 'insufficient':
                failure = refs[candidate['quality_evidence']].get('task_failure')
                require(isinstance(failure, dict) and failure.get('task_evidence') == task['evidence']
                        and failure.get('candidate') == dict(zip(('route', 'family', 'model', 'effort'), key))
                        and isinstance(failure.get('support'), str) and failure['support'] in refs
                        and failure['support'] != candidate['quality_evidence'],
                        'Quality exclusion requires task and candidate bound failure evidence')
            if not candidate['supported'] or not candidate['authenticated'] or candidate['tools'] == 'unsupported':
                unavailable = refs[candidate['runtime_evidence']].get('unavailable_candidates')
                require(isinstance(unavailable, list) and dict(zip(('route', 'family', 'model', 'effort'), key)) in unavailable,
                        'Runtime exclusion requires candidate bound host evidence')
        cost = estimated_cost(candidate['usage_estimate'], models, refs)
        reasons = route_errors(configuration, route=candidate['route'], model=candidate['model'],
                               effort=candidate['effort'], billing=candidate['billing'],
                               head=task['actor'] == 'company_head',
                               explicit_pin=explicit_pin and requested is not None and identity(requested) == key)
        if not candidate['supported'] or not candidate['authenticated'] or candidate['tools'] != 'supported':
            reasons.append('Runtime, authentication or tools unavailable')
        if candidate['billing'] == 'paid_api' and not selection['scope_api_authorized']:
            reasons.append('No explicit current-scope API permission; never a subscription fallback')
        if candidate['quality'] != 'adequate':
            reasons.append('Task-specific model and effort quality is not adequately supported')
        demanding = (task['complexity'] == 'complex' and
                     (task['coupling'] == 'coupled' or task['capability'] in ('coding', 'judgment')))
        prior_conflict = (model is not None and (task['capability'] not in model['capability_priors'] or
                          ((demanding or task['stage'] == 'consultation') and not model['demanding_work_prior'])))
        task_override = False
        if prior_conflict and candidate['quality'] == 'adequate' and not prelaunch:
            task_override = exact_task_fit(candidate, task, refs)
            if not task_override:
                reasons.append('General capability prior needs source-bound exact-task adequacy evidence to supersede it')
        if reasons:
            rejected.append({'candidate': dict(zip(('route', 'family', 'model', 'effort'), key)), 'reasons': reasons})
            continue
        eligible.append({'candidate': dict(zip(('route', 'family', 'model', 'effort'), key)),
                         'cost': cost, 'task_fit_overrides_general_prior': task_override})
    require(eligible, 'No eligible supported task-fit candidate; no authorized fallback')
    # Complete supplied estimates describe these eligible workflows, unlike benchmark tasks.
    # A caller cannot select the cheaper-looking prior while ignoring a known all-in reversal.
    complete = all(row['cost']['total_api_price_proxy_usd'] is not None for row in eligible)
    requested_basis = basis
    if complete:
        basis = 'whole_work_estimate'
    require(basis != 'whole_work_estimate' or complete,
            'Incomplete whole-work estimate cannot establish a price comparison; use an explicit prior or obtain missing evidence')
    for row in eligible:
        if basis == 'whole_work_estimate':
            row['comparison_value'] = row['cost']['total_api_price_proxy_usd']
        elif row['candidate']['model'] in models and (row['candidate']['route'] == 'codex' or legacy_record):
            key = row['candidate']
            prior = models[key['model']]['ale_v1_user_transcription'].get(key['effort'])
            require(prior is not None, 'No exact-effort benchmark prior; do not interpolate effort or invent usage')
            row['comparison_value'] = prior['usd_per_task']
        else:
            row['comparison_value'] = None
    order = configuration['values'].get('service_order', [])
    def rank(row):
        service = ROUTE_ALIASES.get(row['candidate']['route'], row['candidate']['route'])
        preference = order.index(service) if service in order else len(order)
        value = row['comparison_value']
        return preference, value is None, Decimal(str(value)) if value is not None else Decimal(0), str(identity(row['candidate']))
    eligible.sort(key=rank)
    selected = eligible[0]
    if prelaunch and requested is not None:
        selected = next((row for row in eligible if identity(row['candidate']) == identity(requested)), None)
        require(selected is not None, 'Requested candidate was not eligible in the comparison')
        chosen_key = selected['candidate']
        chosen_model = models.get(chosen_key['model']) if chosen_key['route'] == 'codex' or legacy_record else None
        chosen_prior = chosen_model['ale_v1_user_transcription'].get(chosen_key['effort']) if chosen_model else None
        if chosen_prior is not None and not explicit_pin:
            for row in eligible:
                key = row['candidate']
                comparison_model = models.get(key['model']) if key['route'] == 'codex' or legacy_record else None
                prior = comparison_model['ale_v1_user_transcription'].get(key['effort']) if comparison_model else None
                if (prior is not None and prior['score_percent'] >= chosen_prior['score_percent']
                        and row['comparison_value'] <= selected['comparison_value']
                        and (prior['score_percent'] > chosen_prior['score_percent'] or row['comparison_value'] < selected['comparison_value'])):
                    raise SelectionError('Requested candidate is dominated on benchmark score and comparison cost by an eligible candidate')
    return {'status': 'selected', 'selected': selected['candidate'], 'comparison_basis': basis,
            'requested_comparison_basis': requested_basis,
            'comparison_scope': ('ALE v1 directional starting prior; unlisted values are unknown and unranked, not this task estimate or confidence interval'
                                 if basis == 'benchmark_prior' else 'Estimated whole-work API price proxy, not a bill'),
            'candidate_table_sha256': table_sha256, 'compared': eligible, 'rejected': rejected,
            'actual_usage': None, 'actual_subscription_charge_or_credits': None,
            'effective_model': None, 'effective_effort': None, 'fallback': 'unknown_until_host_readback',
            'limits': LIMITS}
