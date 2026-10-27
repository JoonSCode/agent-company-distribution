#!/usr/bin/env python3
"""Portable, non-authoritative Company record and routing-decision checks (stdlib only)."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from company_config import ConfigError, canonical_home, resolve, route_errors
from route_select import SelectionError, select as select_by_price

ROUTES = ('agy', 'antigravity', 'claude-code', 'claude', 'grok', 'codex', 'cursor', 'other')
FAMILIES = ('flash', 'claude', 'grok', 'luna', 'terra', 'sol', 'astra', 'other', 'excluded_pro')
FAILURES = ('capacity', 'auth', 'tools', 'quality')
TRIGGERS = ('initial', 'reassignment')
DISPOSITIONS = ('selected', 'compared', 'incompatible', 'not_required', 'excluded')
REASONS = ('ordinary_assignment', 'bounded_codex_fallback', 'user_pin', 'tool_incompatibility',
           'quality_incompatibility', 'complex_scope', 'not_required', 'excluded_model', 'price_informed')
TASK_CLASSES = ('bounded_simple', 'complex_diagnosis', 'head_orchestration', 'other')
QUALITIES = ('met', 'unmet', 'unknown')
TOOLS = ('supported', 'unsupported', 'unknown')
BILLINGS = ('subscription', 'paid_api', 'unknown')
CONTEXTS = ('reusable', 'contaminated', 'fresh', 'unknown')
REVIEWS = ('independent', 'parent', 'deterministic', 'pending')
RECONSIDERS = ('failure_class_change', 'quality_evidence', 'tool_change', 'user_pin_change',
               'scope_boundary', 'none')
ROUTING_LIMITS = (
    'Structured validation and supplied-evidence price selection only. Does not intercept Orca, '
    'authenticate supplied semantic/price evidence, require every candidate, mandate a model, equate models, or convert quota to tokens.'
)
NO_RECORD = object()


def identity(candidate):
    if not isinstance(candidate, dict):
        return None
    return tuple(candidate.get(field) for field in ('route', 'family', 'model', 'effort'))




class Checker:
    def __init__(self, base):
        self.base = Path(base)
        self.errors = []
        self.refs = {}
        self.price_result = None
        try:
            self.configuration = resolve()
        except (ConfigError, OSError) as exc:
            self.configuration = None
            self.error('$.configuration', 'configuration_invalid', str(exc))

    def error(self, path, code, message):
        self.errors.append({'path': path, 'code': code, 'message': message})

    def obj(self, value, path, required):
        if not isinstance(value, dict):
            self.error(path, 'type', 'Expected object')
            return {}
        for key in required:
            if key not in value:
                self.error(path + '.' + key, 'required', 'Missing field')
        return value

    def seq(self, value, path):
        if not isinstance(value, list):
            self.error(path, 'type', 'Expected array')
            return []
        return value

    def string(self, value, path, nullable=False):
        if nullable and value is None:
            return True
        if not isinstance(value, str) or not value.strip():
            self.error(path, 'type', 'Expected nonempty string' + (' or null' if nullable else ''))
            return False
        return True

    def enum(self, value, path, choices):
        if value not in choices:
            self.error(path, 'value', 'Expected one of ' + ', '.join(choices))

    def evidence(self, value, path, required=False):
        if value is None:
            if required:
                self.error(path, 'evidence_required', 'Evidence reference required')
            return
        if self.string(value, path) and value not in self.refs:
            self.error(path, 'unknown_evidence', 'Reference is absent from evidence map')

    def binding(self, value, path, task, candidate):
        b = self.obj(value, path, ['task', 'dispatch', 'candidate', 'evidence'])
        for field, expected in [('task', task.get('id')), ('dispatch', task.get('current_dispatch')), ('candidate', candidate)]:
            if b.get(field) != expected or expected is None:
                self.error(path + '.' + field, 'stale_binding', 'Must match current Task/Dispatch/candidate')
        self.evidence(b.get('evidence'), path + '.evidence', True)
        return b

    def resources(self, task, path, final):
        execution = task.get('execution')
        execution = execution if isinstance(execution, dict) else {}
        pre = self.obj(task.get('resource_preflight'), path + '.resource_preflight',
                       ['host', 'cpu', 'ram', 'disk', 'evidence'])
        for field in ['host', 'cpu', 'ram', 'disk']:
            self.string(pre.get(field), path + '.resource_preflight.' + field)
        self.evidence(pre.get('evidence'), path + '.resource_preflight.evidence', True)
        seen = set()
        for i, value in enumerate(self.seq(task.get('resources'), path + '.resources')):
            p = path + '.resources[%d]' % i
            v = self.obj(value, p, ['host', 'key', 'kind', 'owner', 'allocation',
                                   'reason', 'retention', 'closeout'])
            for field in ['host', 'key', 'kind', 'owner']:
                self.string(v.get(field), p + '.' + field)
            key = (v.get('host'), v.get('key'))
            if all(isinstance(x, str) for x in key):
                if key in seen:
                    self.error(p, 'duplicate_resource', 'Resource host/key must be unique within Task')
                seen.add(key)
            self.enum(v.get('allocation'), p + '.allocation', ['reuse', 'new'])
            self.string(v.get('reason'), p + '.reason', True)
            if v.get('allocation') == 'new' and not v.get('reason'):
                self.error(p + '.reason', 'allocation_reason', 'New allocation needs a task-specific reason')
            self.enum(v.get('retention'), p + '.retention', ['durable', 'evidence', 'reusable', 'temporary'])
            close = v.get('closeout')
            if close is None:
                if final or execution.get('state') in ['exited', 'settled']:
                    self.error(p + '.closeout', 'resource_closeout', 'Finished work needs resource settlement')
                continue
            c = self.obj(close, p + '.closeout', ['disposition', 'evidence', 'next_use'])
            self.enum(c.get('disposition'), p + '.closeout.disposition',
                      ['released', 'preserved', 'deferred', 'removed'])
            self.evidence(c.get('evidence'), p + '.closeout.evidence', True)
            self.string(c.get('next_use'), p + '.closeout.next_use', True)
            if c.get('disposition') in ['preserved', 'deferred'] and not c.get('next_use'):
                self.error(p + '.closeout', 'retention_reason', 'Kept resources need next consumer or recheck condition')
            if v.get('retention') in ['durable', 'evidence'] and c.get('disposition') == 'removed':
                self.error(p + '.closeout', 'durable_removal', 'Required source/evidence must be promoted before scoped cleanup')
            if c.get('disposition') in ['released', 'removed'] and execution.get('state') in ['live', 'unknown']:
                self.error(p + '.closeout', 'unknown_exit', 'Live/unknown execution cannot prove resource release')

    def evidence_map(self, value, path, label):
        self.refs = self.obj(value, path, [])
        for name, item in self.refs.items():
            p = path + '.' + name
            evidence = self.obj(item, p, ['ref', 'sha256', 'kind'])
            self.string(evidence.get('ref'), p + '.ref')
            self.enum(evidence.get('kind'), p + '.kind', ['synthetic', 'human', 'independent', 'host', 'source', 'provider'])
            if label == 'synthetic' and evidence.get('kind') != 'synthetic':
                self.error(p, 'synthetic_label', 'Synthetic examples must label every evidence item synthetic')
            digest = evidence.get('sha256')
            if digest is not None and (not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest)):
                self.error(p + '.sha256', 'hash_format', 'Expected lowercase SHA-256 or null')
            if 'file' in evidence:
                if self.string(evidence['file'], p + '.file'):
                    try:
                        data = (self.base / evidence['file']).read_bytes()
                        if digest is None:
                            self.error(p, 'hash_required', 'Supplied files require a SHA-256')
                        elif hashlib.sha256(data).hexdigest() != digest:
                            self.error(p, 'hash_mismatch', 'Supplied file content differs from pinned SHA-256')
                    except (OSError, ValueError) as exc:
                        self.error(p, 'file_read', str(exc))

    def route_fields(self, value, path, extra, evidence_required, allow_excluded=False):
        candidate = self.obj(value, path, ['route', 'family', 'model', 'effort', 'evidence'] + extra)
        self.enum(candidate.get('route'), path + '.route', ROUTES)
        self.enum(candidate.get('family'), path + '.family', FAMILIES)
        self.string(candidate.get('model'), path + '.model')
        effort = candidate.get('effort')
        if effort is not None and not (isinstance(effort, str) and effort.strip()):
            self.error(path + '.effort', 'type', 'Expected nonempty provider effort label or null')
        if candidate.get('evidence') is None:
            if evidence_required:
                self.evidence(None, path + '.evidence', True)
        else:
            self.evidence(candidate.get('evidence'), path + '.evidence', True)
        model = candidate.get('model')
        excluded = self.configuration['values']['excluded_models'] if self.configuration else []
        if not allow_excluded and model in excluded:
            self.error(path, 'excluded_model', 'Model is excluded by resolved configuration')
        return candidate

    def pin_bound(self, candidate):
        if not isinstance(candidate, dict):
            return False
        ref = candidate.get('reason_evidence')
        evidence = self.refs.get(ref) if isinstance(ref, str) else None
        binds = evidence.get('binds') if isinstance(evidence, dict) else None
        return isinstance(binds, dict) and identity(binds) == identity(candidate)

    def routing_receipt(self, decision):
        decision = decision if isinstance(decision, dict) else {}
        selected = decision.get('selected') if isinstance(decision.get('selected'), dict) else {}
        binding = decision.get('binding') if isinstance(decision.get('binding'), dict) else {}
        receipt = {'format': 'company-routing-decision/v1',
                'binding': {field: binding.get(field) for field in ('task', 'scope', 'revision', 'attempt', 'planned')},
                'selected': {field: selected.get(field) for field in ('route', 'family', 'model', 'effort')},
                'configuration_sha256': self.configuration['configuration_sha256'] if self.configuration else None,
                'limits': ROUTING_LIMITS}
        if self.price_result is not None:
            receipt['price_selection'] = self.price_result
        return receipt

    def price_selection(self, decision, path, require_selected=True, prelaunch=False, pinned=False, recorded_prelaunch=False):
        if self.configuration is None:
            self.error(path, 'price_selection_invalid', 'Resolved configuration is unavailable')
            return None
        config = self.configuration
        label = decision.get('label', getattr(self, 'label', None))
        if label == 'synthetic' and config['state'] != 'configured':
            config = {**config, 'values': {**config['values'], 'services': ['codex', 'claude-code', 'antigravity', 'grok', 'cursor']}}
        try:
            selection = decision.get('price_selection')
            host_models = None
            if prelaunch and label != 'synthetic' and isinstance(selection, dict):
                inventory_ref = selection.get('inventory_evidence')
                inventory = self.refs.get(inventory_ref, {}) if isinstance(inventory_ref, str) else {}
                if isinstance(inventory, dict) and isinstance(inventory.get('file'), str):
                    inventory_path = (self.base / inventory['file']).resolve()
                    if inventory_path != (canonical_home() / 'models_cache.json').resolve():
                        raise SelectionError('Codex inventory must reference this host canonical models_cache.json')
                    inventory_bytes = inventory_path.read_bytes()
                    if hashlib.sha256(inventory_bytes).hexdigest() != inventory.get('sha256'):
                        raise SelectionError('Candidate inventory hash changed before comparison')
                    contents = json.loads(inventory_bytes)
                    if not isinstance(contents, dict) or not isinstance(contents.get('models'), list):
                        raise SelectionError('Pinned Codex inventory must contain the host models array')
                    observed = datetime.fromisoformat(inventory['observed_at'].replace('Z', '+00:00'))
                    valid_until = datetime.fromisoformat(inventory['valid_until'].replace('Z', '+00:00'))
                    if observed.tzinfo is None or valid_until.tzinfo is None or not observed <= datetime.now(timezone.utc) <= valid_until:
                        raise SelectionError('Host model inventory freshness is expired or unknown')
                    host_models = contents['models']
            elif recorded_prelaunch and label != 'synthetic' and isinstance(selection, dict):
                inventory = self.refs.get(selection.get('inventory_evidence'), {})
                inventory_path = (self.base / inventory['file']).resolve()
                contents = json.loads(inventory_path.read_bytes())
                host_models = contents['models']
                receipt_ref = self.refs[decision['receipt_evidence']]
                receipt = json.loads((self.base / receipt_ref['file']).read_bytes())
                checked = receipt['receipt']
                if (receipt.get('ok') is not True or receipt.get('label') != 'real' or
                        identity(checked['selected']) != identity(decision['selected']) or
                        any(checked['binding'].get(k) != decision['binding'].get(k) for k in ('scope', 'revision')) or
                        checked.get('spec_sha256') != decision['binding'].get('spec_sha256') or
                        checked.get('spec_sha256') is None or
                        checked['price_selection'].get('status') != 'selected' or
                        (not pinned and identity(checked['price_selection'].get('selected')) != identity(decision['selected']))):
                    raise SelectionError('Recorded prelaunch receipt does not bind this selection and specification')
            elif (prelaunch or recorded_prelaunch) and label == 'synthetic' and isinstance(selection, dict):
                inventory = self.refs.get(selection.get('inventory_evidence'), {})
                host_models = inventory.get('host_models') if isinstance(inventory, dict) else None
            result = select_by_price(decision.get('price_selection'), self.refs, config, synthetic=label == 'synthetic', prelaunch=prelaunch or recorded_prelaunch,
                                     requested=decision.get('selected') if (prelaunch or recorded_prelaunch) and not pinned else None, host_models=host_models)
            if recorded_prelaunch and label != 'synthetic':
                previous = checked['price_selection']
                if (previous['candidate_table_sha256'] != result['candidate_table_sha256'] or
                        any(previous[group] != result[group] for group in ('compared', 'rejected')) or
                        previous['comparison_basis'] != result['comparison_basis']):
                    raise SelectionError('Recorded candidate table or comparison differs from prelaunch receipt')
        except (SelectionError, ValueError, TypeError, KeyError, AttributeError, OSError) as exc:
            self.error(path, 'price_selection_invalid', str(exc))
            return None
        self.price_result = result
        if require_selected and result['status'] != 'selected':
            self.error(path, 'price_selection_incomplete', 'Decompose the complex outcome before an executable selection')
        return result

    def routing(self, decision, path, expected, require_receipt, prelaunch=False):
        required = ['version', 'binding', 'trigger', 'failure_class', 'prior', 'selected', 'alternatives',
                    'selected_reason', 'constraints', 'boundary']
        if require_receipt:
            required.append('receipt_evidence')
        decision = self.obj(decision, path, required)
        if type(decision.get('version')) is not int or decision.get('version') != 1:
            self.error(path + '.version', 'version', 'Only integer routing decision version 1 is supported')
        if 'label' in decision:
            self.enum(decision.get('label'), path + '.label', ['synthetic', 'real'])
        elif expected is None:
            self.error(path + '.label', 'required', 'Missing field')
        binding = self.obj(decision.get('binding'), path + '.binding',
                           ['task', 'scope', 'revision', 'attempt', 'planned'])
        for field in ('task', 'scope', 'revision', 'attempt'):
            self.string(binding.get(field), path + '.binding.' + field)
        if type(binding.get('planned')) is not bool:
            self.error(path + '.binding.planned', 'type', 'Expected boolean')
        elif binding.get('planned') is True:
            if binding.get('attempt') != 'planned:' + str(binding.get('task')):
                self.error(path + '.binding.attempt', 'planned_binding', 'Planned attempt must be planned:<task>')
        elif isinstance(binding.get('attempt'), str) and binding.get('attempt').startswith('planned:'):
            self.error(path + '.binding.attempt', 'planned_binding', 'Recorded attempt cannot keep a planned token')
        if expected is not None:
            for field in ('task', 'scope', 'revision', 'attempt'):
                if field in expected and binding.get(field) != expected[field]:
                    self.error(path + '.binding.' + field, 'stale_binding',
                               'Decision binding must match current task, scope, revision and attempt')
        self.enum(decision.get('trigger'), path + '.trigger', TRIGGERS)
        if decision.get('failure_class') is not None:
            self.enum(decision.get('failure_class'), path + '.failure_class', FAILURES)
        raw_selected = decision.get('selected') if isinstance(decision.get('selected'), dict) else {}
        pinned = identity(raw_selected) if decision.get('selected_reason') == 'user_pin' and self.pin_bound(raw_selected) else None
        if decision.get('selected_reason') == 'user_pin' and pinned is None:
            self.error(path + '.selected.reason_evidence', 'unbound_pin', 'Explicit task pin requires exact route/model/effort evidence binding')
        if prelaunch and pinned is not None and decision.get('label') != 'synthetic':
            pin_evidence = self.refs.get(raw_selected.get('reason_evidence'), {})
            if not isinstance(pin_evidence, dict) or pin_evidence.get('kind') != 'human':
                self.error(path + '.selected.reason_evidence', 'unbound_pin', 'A real user pin requires human evidence')
        if prelaunch and pinned is not None:
            pin_evidence = self.refs.get(raw_selected.get('reason_evidence'), {})
            pin_binding = pin_evidence.get('task_binding') if isinstance(pin_evidence, dict) else None
            if not isinstance(pin_binding, dict) or any(pin_binding.get(field) != binding.get(field) for field in ('task', 'scope', 'revision', 'attempt')):
                self.error(path + '.selected.reason_evidence', 'unbound_pin', 'User pin must bind this task, scope, revision and attempt')
        prior = decision.get('prior')
        if prior is not None:
            prior = self.route_fields(prior, path + '.prior', [], True)
        selected = self.route_fields(decision.get('selected'), path + '.selected',
                                     ['supported', 'reason_evidence'], True, allow_excluded=pinned is not None)
        if type(selected.get('supported')) is not bool:
            self.error(path + '.selected.supported', 'type', 'Expected boolean')
        elif selected.get('supported') is not True:
            self.error(path + '.selected.supported', 'unsupported_effort',
                       'Selected effort must be recorded as supported by that route')
        if prelaunch and pinned is not None and decision.get('label') != 'synthetic':
            selected_evidence = self.refs.get(selected.get('evidence'), {})
            if not isinstance(selected_evidence, dict) or selected_evidence.get('kind') != 'host':
                self.error(path + '.selected.evidence', 'host_evidence_required', 'A pinned launch requires host support evidence')
        self.evidence(selected.get('reason_evidence'), path + '.selected.reason_evidence', True)
        self.enum(decision.get('selected_reason'), path + '.selected_reason', REASONS)
        selected_rows = []
        alternatives = []
        for index, value in enumerate(self.seq(decision.get('alternatives'), path + '.alternatives')):
            item_path = path + '.alternatives[%d]' % index
            alternative = self.obj(value, item_path, ['route', 'family', 'model', 'effort', 'disposition', 'reason', 'evidence'])
            self.enum(alternative.get('disposition'), item_path + '.disposition', DISPOSITIONS)
            self.enum(alternative.get('reason'), item_path + '.reason', REASONS)
            lift = pinned is not None and identity(alternative) == pinned and alternative.get('reason') == 'user_pin'
            alternative = self.route_fields(alternative, item_path, ['disposition', 'reason'],
                                            alternative.get('disposition') != 'not_required', allow_excluded=lift)
            alternatives.append(alternative)
            if alternative.get('disposition') == 'selected':
                selected_rows.append(alternative)
        matched = (len(selected_rows) == 1 and identity(selected_rows[0]) == identity(selected) and
                   selected_rows[0].get('evidence') == selected.get('evidence') and
                   selected_rows[0].get('reason') == decision.get('selected_reason'))
        if not matched:
            self.error(path + '.selected', 'selected_mismatch',
                       'Exactly one alternative must match the selected route, model, effort, evidence and reason')
        if expected is not None and isinstance(expected.get('model'), dict):
            requested, effort = expected['model'].get('requested'), expected['model'].get('effort_requested')
            if isinstance(requested, str) and requested != selected.get('model'):
                self.error(path + '.selected.model', 'selected_mismatch', 'Selected model must match the task request when that request is known')
            if isinstance(effort, str) and effort != selected.get('effort'):
                self.error(path + '.selected.effort', 'selected_mismatch', 'Selected effort must match the task request when that request is known')
        constraints = self.obj(decision.get('constraints'), path + '.constraints',
                               ['task', 'quality', 'tool', 'billing', 'context'])
        self.enum(constraints.get('task'), path + '.constraints.task', TASK_CLASSES)
        self.enum(constraints.get('quality'), path + '.constraints.quality', QUALITIES)
        self.enum(constraints.get('tool'), path + '.constraints.tool', TOOLS)
        self.enum(constraints.get('billing'), path + '.constraints.billing', BILLINGS)
        self.enum(constraints.get('context'), path + '.constraints.context', CONTEXTS)
        if self.configuration is not None:
            # Synthetic fixtures establish structure, not real account intent/readiness.
            # Paid permission and private pins remain checked on every surface.
            route_config = self.configuration
            if decision.get('label', getattr(self, 'label', None)) == 'synthetic' and route_config['state'] != 'configured':
                route_config = {**route_config, 'values': {**route_config['values'], 'services': ['codex', 'claude-code', 'antigravity', 'grok', 'cursor']}}
            problems = route_errors(route_config, route=selected.get('route'), model=selected.get('model'),
                                    effort=selected.get('effort'), billing=constraints.get('billing'),
                                    head=constraints.get('task') == 'head_orchestration', explicit_pin=pinned is not None)
            for problem in problems:
                self.error(path + '.selected', 'configuration_gate', problem)
        boundary = self.obj(decision.get('boundary'), path + '.boundary',
                            ['review', 'reconsider', 'scope', 'next', 'inherits'])
        self.enum(boundary.get('review'), path + '.boundary.review', REVIEWS)
        self.enum(boundary.get('reconsider'), path + '.boundary.reconsider', RECONSIDERS)
        self.string(boundary.get('scope'), path + '.boundary.scope')
        self.string(boundary.get('next'), path + '.boundary.next')
        if type(boundary.get('inherits')) is not bool:
            self.error(path + '.boundary.inherits', 'type', 'Expected boolean')
        if decision.get('trigger') == 'initial' and (prior is not None or decision.get('failure_class') is not None):
            self.error(path + '.trigger', 'reason_binding', 'Initial assignment has no prior failure')
        if decision.get('trigger') == 'reassignment' and (not isinstance(prior, dict) or decision.get('failure_class') is None):
            self.error(path + '.trigger', 'reason_binding', 'Reassignment must bind the prior candidate and one failure class')
        reason_evidence = selected.get('reason_evidence')
        stale = isinstance(prior, dict) and reason_evidence == prior.get('evidence') and identity(selected) != identity(prior)
        evidence = self.refs.get(reason_evidence) if isinstance(reason_evidence, str) else None
        if isinstance(evidence, dict) and 'binds' in evidence:
            binds = evidence.get('binds')
            if not isinstance(binds, dict):
                self.error(path + '.selected.reason_evidence', 'type', 'Reason binding must be an object, not prose')
                stale = True
            else:
                for field in ('route', 'family', 'model', 'effort'):
                    if field not in binds:
                        self.error(path + '.selected.reason_evidence', 'required', 'Reason binding is missing ' + field)
                if identity(binds) != identity(selected):
                    stale = True
        if stale:
            self.error(path + '.selected.reason_evidence', 'stale_rationale',
                       'Selected reason evidence still binds to another candidate')
        if require_receipt:
            self.evidence(decision.get('receipt_evidence'), path + '.receipt_evidence', True)
        if 'tokens' in decision:
            tokens = self.obj(decision.get('tokens'), path + '.tokens', ['input', 'output', 'basis'])
            if tokens.get('basis') == 'quota':
                self.error(path + '.tokens.basis', 'quota_token_conversion',
                           'Quota, credit or price cannot be converted into token counts')
            else:
                self.enum(tokens.get('basis'), path + '.tokens.basis', ['observed', 'unknown'])
            for field in ('input', 'output'):
                count = tokens.get(field)
                if count is not None and (type(count) is not int or count < 0):
                    self.error(path + '.tokens.' + field, 'count', 'Expected nonnegative integer or null')
            if tokens.get('basis') == 'unknown' and (tokens.get('input') is not None or tokens.get('output') is not None):
                self.error(path + '.tokens', 'token_basis', 'Unknown token basis cannot carry counts')
            if tokens.get('basis') == 'observed' and tokens.get('input') is None and tokens.get('output') is None:
                self.error(path + '.tokens', 'token_basis', 'Observed token basis needs a count')
        if prelaunch and pinned is None and 'price_selection' not in decision:
            self.error(path + '.price_selection', 'price_selection_required', 'Fresh unpinned assignment requires a candidate comparison')
        if 'price_selection' in decision or decision.get('selected_reason') == 'price_informed':
            recorded_prelaunch = (not prelaunch and require_receipt and isinstance(decision.get('price_selection'), dict)
                                  and 'inventory_evidence' in decision['price_selection'])
            result = self.price_selection(decision, path + '.price_selection', prelaunch=prelaunch, pinned=pinned is not None, recorded_prelaunch=recorded_prelaunch)
            if result and result['status'] == 'selected':
                if identity(result['selected']) != identity(selected) and not ((prelaunch or recorded_prelaunch) and pinned is not None):
                    self.error(path + '.selected', 'price_selection_mismatch',
                               'Selected model/effort must match the deterministic price-selection result')
                rows = decision['price_selection']['candidates']
                chosen = next((row for row in rows if identity(row) == identity(selected if pinned is not None and (prelaunch or recorded_prelaunch) else result['selected'])), None)
                if (chosen is None or constraints.get('billing') != chosen['billing'] or constraints.get('quality') != 'met'
                        or constraints.get('tool') != 'supported' or (prelaunch and (
                            not chosen['supported'] or not chosen['authenticated'] or chosen['tools'] != 'supported'
                            or chosen['quality'] != 'adequate'))):
                    self.error(path + '.constraints', 'price_selection_mismatch',
                               'Decision constraints must preserve selected billing, adequate quality and supported tools')
        self.routing_rules(decision, path, binding, prior if isinstance(prior, dict) else None, selected,
                           alternatives, constraints, boundary)

    def routing_rules(self, decision, path, binding, prior, selected, alternatives, constraints, boundary):
        failure, reason = decision.get('failure_class'), decision.get('selected_reason')

        if failure == 'capacity' and reason == 'quality_incompatibility':
            self.error(path + '.failure_class', 'capacity_not_quality',
                       'Capacity failure is not a quality failure and does not justify a stronger setting')
        if reason == 'complex_scope':
            if constraints.get('task') != 'complex_diagnosis':
                self.error(path + '.constraints.task', 'reason_binding', 'Complex scope requires the complex_diagnosis task class')
            if boundary.get('inherits') is not False:
                self.error(path + '.boundary.inherits', 'blanket_inheritance',
                           'Stronger complex work cannot inherit onto the remaining simple work')
            if boundary.get('scope') == binding.get('scope'):
                self.error(path + '.boundary.scope', 'narrow_scope',
                           'Complex diagnosis must name a scope id narrower than the bound task scope')
            nxt = boundary.get('next')
            if nxt in (None, 'none', boundary.get('scope'), binding.get('scope')):
                self.error(path + '.boundary.next', 'next_boundary',
                           'Complex diagnosis must name the next boundary id for remaining simple work')
        if reason == 'tool_incompatibility' and (constraints.get('tool') != 'unsupported' or failure not in ('tools', 'capacity')):
            self.error(path + '.selected_reason', 'reason_binding',
                       'Tool incompatibility requires an unsupported tool constraint and failure class tools or capacity')
        if reason == 'quality_incompatibility' and failure != 'capacity' and (
                failure != 'quality' or constraints.get('quality') != 'unmet'):
            self.error(path + '.selected_reason', 'reason_binding',
                       'Quality incompatibility requires failure class quality and unmet quality constraint')
        if reason == 'bounded_codex_fallback':
            if not (isinstance(prior, dict) and selected.get('route') == 'codex' and
                    failure in ('capacity', 'auth')):
                self.error(path + '.selected_reason', 'reason_binding',
                           'Bounded fallback requires a recorded prior route and capacity/auth failure')
            if not any(isinstance(item, dict) and item.get('evidence') and
                       item.get('disposition') == 'compared' for item in alternatives):
                self.error(path + '.alternatives', 'missing_comparison',
                           'Fallback requires an evidence-backed task-fit comparison; no fixed model mapping')

    def check(self, record, require_routing=False):
        r = self.obj(record, '$', ['version', 'label', 'evidence', 'goal', 'ownership', 'tasks', 'usage'])
        if type(r.get('version')) is not int or r.get('version') != 1:
            self.error('$.version', 'version', 'Only integer version 1 is supported')
        self.enum(r.get('label'), '$.label', ['synthetic', 'real'])
        self.label = r.get('label')
        if 'resource_accounting' in r:
            self.enum(r['resource_accounting'], '$.resource_accounting', ['required'])
        if 'routing_accounting' in r:
            self.enum(r['routing_accounting'], '$.routing_accounting', ['required'])
        self.evidence_map(r.get('evidence'), '$.evidence', r.get('label'))
        routing_required = require_routing or r.get('routing_accounting') == 'required'
        g = self.obj(r.get('goal'), '$.goal', ['id', 'revision', 'scope', 'plan', 'status', 'known_failure', 'assessment', 'current_owner', 'owner_acceptance'])
        for key in ['id', 'revision', 'scope']:
            self.string(g.get(key), '$.goal.' + key)
        self.string(g.get('current_owner'), '$.goal.current_owner', True)
        self.enum(g.get('owner_acceptance'), '$.goal.owner_acceptance', ['pending', 'accepted'])
        self.evidence(g.get('plan'), '$.goal.plan', True)
        self.enum(g.get('status'), '$.goal.status', ['pending', 'active', 'failed', 'succeeded'])
        if type(g.get('known_failure')) is not bool:
            self.error('$.goal.known_failure', 'type', 'Expected boolean')
        if g.get('known_failure') is True and g.get('status') == 'succeeded':
            self.error('$.goal.status', 'overall_failure', 'Team passes cannot override known overall failure')
        if g.get('assessment') is not None:
            a = self.obj(g['assessment'], '$.goal.assessment', ['revision', 'scope', 'verdict', 'basis', 'actor', 'evidence'])
            for field in ['revision', 'scope']:
                self.string(a.get(field), '$.goal.assessment.' + field)
                if a.get(field) != g.get(field):
                    self.error('$.goal.assessment.' + field, 'goal_binding', 'Overall assessment must match current revision/scope')
            self.string(a.get('actor'), '$.goal.assessment.actor')
            if a.get('basis') == 'independent' and a.get('actor') == g.get('current_owner'):
                self.error('$.goal.assessment.actor', 'self_acceptance', 'Independent overall assessment cannot be by the goal owner')
            self.enum(a.get('verdict'), '$.goal.assessment.verdict', ['pending', 'failed', 'succeeded'])
            self.enum(a.get('basis'), '$.goal.assessment.basis', ['human', 'independent', 'team_checks'])
            self.evidence(a.get('evidence'), '$.goal.assessment.evidence', True)
            if g.get('status') == 'succeeded' and (a.get('verdict') != 'succeeded' or a.get('basis') not in ['human', 'independent']):
                self.error('$.goal.assessment', 'overall_acceptance', 'Overall success requires recorded human/independent success')
            if a.get('verdict') == 'failed' and g.get('status') == 'succeeded':
                self.error('$.goal.status', 'overall_failure', 'Overall assessment records failure')
        elif g.get('status') == 'succeeded':
            self.error('$.goal.assessment', 'overall_acceptance', 'Overall success needs an assessment')
        owner, accepted_key = None, None
        for i, value in enumerate(self.seq(r.get('ownership'), '$.ownership')):
            p = '$.ownership[%d]' % i
            event_errors = len(self.errors)
            o = self.obj(value, p, ['revision', 'scope', 'from', 'to', 'status', 'accepted_by', 'evidence'])
            for field in ['revision', 'scope', 'to']:
                self.string(o.get(field), p + '.' + field)
            self.string(o.get('from'), p + '.from', True)
            self.enum(o.get('status'), p + '.status', ['proposed', 'accepted'])
            self.evidence(o.get('evidence'), p + '.evidence', o.get('status') == 'accepted')
            self.string(o.get('accepted_by'), p + '.accepted_by', True)
            if o.get('status') == 'accepted' and o.get('accepted_by') != o.get('to'):
                self.error(p + '.accepted_by', 'owner_acceptance', 'Accepted owner must explicitly be the accepting actor')
            key = (o.get('revision'), o.get('scope'))
            if all(isinstance(x, str) for x in key) and o.get('status') == 'accepted':
                if o.get('from') != owner:
                    self.error(p + '.from', 'owner_chain', 'Accepted transfer must start from the last accepted owner, including across revisions')
                elif len(self.errors) == event_errors:
                    owner, accepted_key = o.get('to'), key
        key = (g.get('revision'), g.get('scope'))
        if g.get('current_owner') != owner:
            self.error('$.goal.current_owner', 'unaccepted_owner', 'Continuity responsibility stays with the last accepted owner until a valid successor transfer')
        acceptance = 'accepted' if owner is not None and accepted_key == key else 'pending'
        if g.get('owner_acceptance') != acceptance:
            self.error('$.goal.owner_acceptance', 'scope_acceptance', 'Acceptance must match the latest accepted revision/scope; continuity does not authorize new scope')
        if g.get('status') in ['active', 'succeeded'] and acceptance != 'accepted':
            self.error('$.goal.owner_acceptance', 'owner_pending', 'Active/succeeded revision requires explicit acceptance for that revision/scope')
        task_ids = set()
        for i, value in enumerate(self.seq(r.get('tasks'), '$.tasks')):
            p = '$.tasks[%d]' % i
            t = self.obj(value, p, ['id', 'goal_revision', 'goal_scope', 'parent', 'current_dispatch', 'candidate', 'execution', 'technical', 'parent_integration', 'model', 'retry_claimed', 'another_writer_claimed'])
            for field in ['id', 'parent', 'current_dispatch', 'candidate']:
                if self.string(t.get(field), p + '.' + field) and field == 'id':
                    if t[field] in task_ids:
                        self.error(p + '.id', 'duplicate_task', 'Duplicate Task ID')
                    task_ids.add(t[field])
            for field, expected in [('goal_revision', g.get('revision')), ('goal_scope', g.get('scope'))]:
                self.string(t.get(field), p + '.' + field)
                if t.get(field) != expected:
                    self.error(p + '.' + field, 'goal_binding', 'Task must belong to current goal revision/scope')
            m = self.obj(t.get('model'), p + '.model', ['requested', 'observed', 'effort_requested', 'effort_observed'])
            for field in ['requested', 'observed', 'effort_requested', 'effort_observed']:
                self.string(m.get(field), p + '.model.' + field, True)
            ex = self.obj(t.get('execution'), p + '.execution', ['state', 'actor', 'result'])
            self.enum(ex.get('state'), p + '.execution.state', ['live', 'unknown', 'exited', 'settled'])
            self.string(ex.get('actor'), p + '.execution.actor')
            if ex.get('result') is not None:
                b = self.binding(ex['result'], p + '.execution.result', t, t.get('candidate'))
                self.enum(b.get('outcome'), p + '.execution.result.outcome', ['succeeded', 'failed'])
                if ex.get('state') != 'settled':
                    self.error(p + '.execution', 'unsettled_result', 'Result claim requires recorded execution settlement')
            elif ex.get('state') == 'settled':
                self.error(p + '.execution.result', 'settlement_result', 'Settled execution requires bound outcome receipt')
            for field in ['retry_claimed', 'another_writer_claimed']:
                if type(t.get(field)) is not bool:
                    self.error(p + '.' + field, 'type', 'Expected boolean')
                elif t[field] and ex.get('state') not in ['exited', 'settled']:
                    self.error(p + '.' + field, 'unknown_exit', 'Unknown/live exit cannot justify retry or another writer')
            for field in ['technical', 'parent_integration']:
                if t.get(field) is None:
                    continue
                a = self.binding(t[field], p + '.' + field, t, t.get('candidate'))
                self.enum(a.get('verdict'), p + '.' + field + '.verdict', ['pending', 'passed', 'failed'])
                self.string(a.get('actor'), p + '.' + field + '.actor')
                if field == 'parent_integration' and a.get('actor') != t.get('parent'):
                    self.error(p + '.' + field, 'parent_binding', 'Integration actor must be recorded parent')
                if a.get('verdict') == 'passed' and field == 'technical' and a.get('actor') == ex.get('actor'):
                    self.error(p + '.' + field, 'self_acceptance', 'Technical acceptance must be independent of executor')
            if r.get('resource_accounting') == 'required':
                self.resources(t, p, g.get('status') in ['failed', 'succeeded'])
            if routing_required or 'routing_decision' in t:
                if 'routing_decision' not in t:
                    self.error(p + '.routing_decision', 'routing_required',
                               'This Run requires a routing decision for every current task')
                else:
                    self.routing(t.get('routing_decision'), p + '.routing_decision', {
                        'task': t.get('id'), 'scope': g.get('scope'), 'revision': g.get('revision'),
                        'attempt': t.get('current_dispatch'),
                        'model': t.get('model') if isinstance(t.get('model'), dict) else {}}, True)
        usage = self.obj(r.get('usage'), '$.usage', ['coverage', 'expected', 'entries'])
        self.enum(usage.get('coverage'), '$.usage.coverage', ['unknown', 'partial', 'complete'])
        expected = []
        for i, value in enumerate(self.seq(usage.get('expected'), '$.usage.expected')):
            if self.string(value, '$.usage.expected[%d]' % i):
                expected.append(value)
        if len(expected) != len(set(expected)):
            self.error('$.usage.expected', 'duplicate_usage', 'Expected provenance keys must be unique')
        seen, sessions, subtotals = set(), {}, {}
        complete = True
        for i, value in enumerate(self.seq(usage.get('entries'), '$.usage.entries')):
            p = '$.usage.entries[%d]' % i
            fields = ['provider', 'tokenizer', 'kind', 'id', 'session', 'input', 'output', 'cached_input', 'reasoning', 'cached_in_input', 'reasoning_in_output', 'evidence']
            u = self.obj(value, p, fields)
            # An explicit null count means unknown; an absent required field is
            # malformed and must not enter aggregation after obj reports it.
            valid = all(field in u for field in fields)
            for field in ['provider', 'tokenizer', 'id', 'session']:
                valid = self.string(u.get(field), p + '.' + field) and valid
            if isinstance(u.get('provider'), str) and '/' in u['provider']:
                self.error(p + '.provider', 'provenance_format', 'Provider namespace cannot contain a slash')
                valid = False
            self.enum(u.get('kind'), p + '.kind', ['request', 'session'])
            self.evidence(u.get('evidence'), p + '.evidence', True)
            for field in ['input', 'output', 'cached_input', 'reasoning']:
                n = u.get(field)
                if n is not None and (type(n) is not int or n < 0):
                    self.error(p + '.' + field, 'count', 'Expected nonnegative integer or null')
                    valid = False
            for field in ['cached_in_input', 'reasoning_in_output']:
                if type(u.get(field)) is not bool:
                    self.error(p + '.' + field, 'type', 'Expected explicit boolean inclusion')
            for extra, main, flag in [('cached_input', 'input', 'cached_in_input'), ('reasoning', 'output', 'reasoning_in_output')]:
                if type(u.get(extra)) is int and u[extra] > 0 and u.get(flag) is not True:
                    self.error(p + '.' + flag, 'usage_inclusion', 'Normalize reported inclusive input/output before summing; never add subcounts')
                if type(u.get(extra)) is int and type(u.get(main)) is int and u[extra] > u[main]:
                    self.error(p + '.' + extra, 'usage_inclusion', 'Included subcount cannot exceed its total')
            if not valid or u.get('kind') not in ['request', 'session']:
                complete = False
                continue
            key = u['provider'] + '/' + u['kind'] + '/' + u['id']
            session = (u['provider'], u['session'])
            prior = sessions.setdefault(session, [])
            duplicate = key in seen or (prior and ('session' in prior or u['kind'] == 'session'))
            if u['kind'] == 'session' and u['id'] != u['session']:
                self.error(p + '.id', 'session_identity', 'Session unit ID must equal session provenance')
            if duplicate:
                self.error(p, 'duplicate_usage', 'Repeated provenance or overlapping session/request accounting')
                complete = False
                continue
            seen.add(key)
            prior.append(u['kind'])
            group = u['provider'] + '/' + u['tokenizer']
            subtotal = subtotals.setdefault(group, {'input': None, 'output': None, 'observed_entries': 0})
            subtotal['observed_entries'] += 1
            for field in ['input', 'output']:
                if u[field] is None:
                    complete = False
                else:
                    subtotal[field] = (subtotal[field] or 0) + u[field]
        if not expected or set(expected) != seen:
            complete = False
        if usage.get('coverage') != 'complete':
            complete = False
        elif not complete:
            self.error('$.usage.coverage', 'incomplete_coverage', 'Complete claim requires every expected unit exactly once and all input/output counts')
        return {'ok': not self.errors, 'label': r.get('label'), 'errors': self.errors, 'usage': {'coverage': usage.get('coverage'), 'observed_subtotals': subtotals, 'total_raw_tokens': sum(s['input'] + s['output'] for s in subtotals.values()) if complete and not self.errors else None, 'tokenizer_note': 'Provider/tokenizer groups retain distinct counting conventions; subtotal fields contain observed counts only.'}}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON field: ' + key)
        result[key] = value
    return result


def invalid_constant(value):
    raise ValueError('Non-JSON constant: ' + value)


def read_json(path):
    return read_json_snapshot(path)[:2]


def read_json_snapshot(path):
    try:
        data = Path(path).read_bytes()
        value = json.loads(data.decode('utf-8'), object_pairs_hook=unique_object, parse_constant=invalid_constant)
        return value, None, hashlib.sha256(data).hexdigest()
    except (OSError, ValueError, RecursionError) as exc:
        return None, {'path': str(path), 'code': 'input_read', 'message': str(exc)}, None


def check_record(record, base, require_routing=False):
    return Checker(base).check(record, require_routing=require_routing)


def check_routing(decision, base, record=NO_RECORD, record_base=None, *, prelaunch=False):
    checker = Checker(base)
    expected = None
    if record is not NO_RECORD:
        current = check_record(record, base if record_base is None else record_base)
        checker.errors.extend({**error, 'path': '$.record' + error['path'][1:]}
                              for error in current['errors'])
        if current['ok']:
            goal = record['goal']
            expected = {'scope': goal['scope'], 'revision': goal['revision']}
            binding = decision.get('binding') if isinstance(decision, dict) else None
            binding = binding if isinstance(binding, dict) else {}
            task = next((task for task in record['tasks'] if task['id'] == binding.get('task')), None)
            if task is not None:
                expected.update(task=task['id'], attempt=task['current_dispatch'], model=task['model'])
            elif binding.get('planned') is not True:
                checker.error('$.binding.task', 'unknown_task',
                              'An unrecorded task must use a planned binding')
    if not isinstance(decision, dict):
        checker.error('$', 'type', 'Expected object')
        label = None
    else:
        label = decision.get('label')
        checker.evidence_map(decision.get('evidence'), '$.evidence', label)
        if expected is not None and 'label' not in decision:
            checker.error('$.label', 'required', 'Missing field')
        checker.routing(decision, '$', expected, False, prelaunch=prelaunch)
    return {'ok': not checker.errors, 'label': label, 'errors': checker.errors,
            'receipt': checker.routing_receipt(decision)}



def selection_advice(decision, base):
    checker = Checker(base)
    if not isinstance(decision, dict):
        checker.error('$', 'type', 'Expected decision object')
    else:
        checker.enum(decision.get('label'), '$.label', ['synthetic', 'real'])
        checker.evidence_map(decision.get('evidence'), '$.evidence', decision.get('label'))
        checker.price_selection(decision, '$.price_selection', require_selected=False)
    return {'ok': not checker.errors, 'errors': checker.errors, 'advice': checker.price_result,
            'limits': 'Advice only: complete the existing routing decision and run routing-check before an authorized launch.'}


def case_suite(value, base, mode):
    checker = Checker(base)
    suite = checker.obj(value, '$', ['version', 'label', 'cases'])
    if suite.get('version') != 1 or type(suite.get('version')) is not int:
        checker.error('$.version', 'version', 'Expected integer version 1')
    if suite.get('label') != 'synthetic':
        checker.error('$.label', 'synthetic_label', 'Case suites must be synthetic')
    results = []
    record_key = 'record' if mode == 'record' else 'decision'
    for index, item in enumerate(checker.seq(suite.get('cases'), '$.cases')):
        path = '$.cases[%d]' % index
        case = checker.obj(item, path, ['name', record_key, 'expected_errors'])
        checker.string(case.get('name'), path + '.name')
        expected = checker.seq(case.get('expected_errors'), path + '.expected_errors')
        for offset, code in enumerate(expected):
            checker.string(code, path + '.expected_errors[%d]' % offset)
        if mode == 'record':
            actual = check_record(case.get('record'), base)
            if actual.get('label') != 'synthetic':
                checker.error(path + '.record.label', 'synthetic_label', 'Every case record must be synthetic')
        else:
            actual = check_routing(case.get('decision'), base)
            if actual.get('label') != 'synthetic':
                checker.error(path + '.decision.label', 'synthetic_label', 'Every routing case must be synthetic')
        found = sorted(set(error['code'] for error in actual['errors']))
        passed = found == sorted(set(code for code in expected if isinstance(code, str)))
        results.append({'name': case.get('name'), 'passed': passed, 'expected_errors': expected, 'result': actual})
    if not results:
        checker.error('$.cases', 'empty_cases', 'At least one case is required')
    return {'ok': not checker.errors and all(item['passed'] for item in results), 'label': 'synthetic',
            'errors': checker.errors, 'cases': results}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', action='store_true', dest='global_json')
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ['check', 'cases', 'routing-check', 'routing-cases', 'routing-select']:
        item = sub.add_parser(command)
        item.add_argument('path', type=Path)
        item.add_argument('--json', action='store_true')
        if command == 'check':
            item.add_argument('--require-resources', action='store_true', help='Reject records without resource accounting')
            item.add_argument('--require-routing', action='store_true',
                              help='Require a routing decision on every task even if the record omits routing_accounting')
        elif command == 'routing-check':
            item.add_argument('--record', type=Path,
                              help='Validate against the current supplementary record and goal/task binding')
    args = parser.parse_args(argv)
    value, error, decision_sha256 = read_json_snapshot(args.path)
    if error:
        result, code = {'ok': False, 'errors': [error]}, 2
    elif args.command == 'check':
        result = check_record(value, args.path.parent, require_routing=args.require_routing)
        if args.require_resources and (not isinstance(value, dict) or value.get('resource_accounting') != 'required'):
            result['errors'].append({'path': '$.resource_accounting', 'code': 'resource_accounting', 'message': 'Resource accounting is required for this invocation'})
            result['ok'] = False
            result['usage']['total_raw_tokens'] = None
        code = 0 if result['ok'] else 1
    elif args.command == 'routing-select':
        result = selection_advice(value, args.path.parent)
        result['request_sha256'] = decision_sha256
        code = 0 if result['ok'] else 1
    elif args.command == 'routing-check':
        record, error, record_sha256 = read_json_snapshot(args.record) if args.record is not None else (NO_RECORD, None, None)
        if error:
            result, code = {'ok': False, 'errors': [error]}, 2
        else:
            result = check_routing(value, args.path.parent, record,
                                   args.record.parent if args.record is not None else None, prelaunch=True)
            result['receipt']['decision_sha256'] = decision_sha256
            if args.record is not None:
                result['receipt']['record_sha256'] = record_sha256
            code = 0 if result['ok'] else 1
    else:
        result = case_suite(value, args.path.parent, 'record' if args.command == 'cases' else 'routing')
        code = 0 if result['ok'] else 1
    if args.global_json or args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(('PASS' if result['ok'] else 'FAIL') + ' — recorded consistency only')
        for e in result.get('errors', []):
            print(e['path'] + ': ' + e['code'] + ': ' + e['message'])
        for case in result.get('cases', []):
            print(('PASS ' if case['passed'] else 'FAIL ') + str(case['name']))
    return code


if __name__ == '__main__':
    sys.exit(main())
