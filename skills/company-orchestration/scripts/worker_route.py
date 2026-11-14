#!/usr/bin/env python3
"""Pure, deterministic worker assignment proposal; not authorization to launch.

prepare(document, table, pins=None) returns per-unit proposals and canonical SHA256
hashes. pins maps unit IDs to exact route/model/effort identity objects. Capabilities
and evidence in a table are untrusted assertions, not host or quality verification.
CLI: worker_route.py prepare PROFILE.json [--table TABLE.json] [--pins PINS.json].
"""
import argparse
import hashlib
import json
from worker_profile import ASSETS, ProfileError, load_json, validate_profile_document, validate_schema

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()

def validate_table(table, priors=None):
    validate_schema(table, load_json(ASSETS / 'worker-routing-table.schema.json'))
    priors = priors if priors is not None else load_json(ASSETS / 'model-choice-priors.json')
    keys = set()
    for row in table['entries']:
        key = (row['family'], row['difficulty'])
        if key in keys: raise ProfileError('INVALID_TABLE', f'duplicate row {key}')
        keys.add(key); identities = set(); models = set()
        for c in row['candidates']:
            ident = c['identity']; ident_key = tuple(ident[k] for k in ('route','model','effort'))
            if ident_key in identities: raise ProfileError('INVALID_TABLE', f'duplicate identity {ident_key}')
            identities.add(ident_key)
            if ident['model'] in models: raise ProfileError('INVALID_TABLE', f'duplicate model {ident["model"]}')
            models.add(ident['model'])
            if ident['route'] != 'codex' or ident['model'] not in priors['models'] or ident['effort'] not in priors['models'][ident['model']]['efforts']:
                raise ProfileError('INVALID_TABLE', f'unknown policy identity {ident_key}')
    ident = table['common_default']['identity']
    if (ident['route'] != 'codex' or ident['model'] != 'gpt-6.1-terra' or
            ident['effort'] not in priors['models'][ident['model']]['efforts']):
        raise ProfileError('INVALID_TABLE', 'common default must be a supported codex/gpt-6.1-terra identity')
    required = {('general', difficulty) for difficulty in ('easy', 'medium', 'hard')}
    if not required.issubset(keys):
        raise ProfileError('INVALID_TABLE', 'general easy/medium/hard rows required')
    return table

def prepare(document, table, pins=None):
    validate_profile_document(document); priors = load_json(ASSETS / 'model-choice-priors.json'); validate_table(table, priors)
    if pins is None: pins = {}
    if not isinstance(pins, dict): raise ProfileError('INVALID_PIN', 'pins must be an object')
    ids = {u['id'] for u in document['units']}
    if set(pins) - ids: raise ProfileError('INVALID_PIN', 'pin references unknown unit')
    identity_schema = load_json(ASSETS / 'worker-routing-table.schema.json')['properties']['entries']['items']['properties']['candidates']['items']['properties']['identity']
    for pin in pins.values(): validate_schema(pin, identity_schema)
    rows = {(r['family'],r['difficulty']):r for r in table['entries']}; results = []
    for unit in document['units']:
        p = unit['profile']; row = rows.get((p['family'],p['difficulty'])); rejected = []; eligible = []
        chain = sorted(row['candidates'] if row else [], key=lambda c: (c['priority'], *(c['identity'][k] for k in ('route', 'model', 'effort'))))
        def rejection_reasons(c):
            reasons = []
            if not c['enabled']: reasons.append('disabled')
            if unit['id'] in pins and c['identity'] != pins[unit['id']]: reasons.append('pin mismatch')
            for required, available in [('input_modalities','input_modalities'),('output_modalities','output_modalities'),('required_capabilities','capabilities'),('required_tools','tools'),('hard_constraints','constraints')]:
                missing = sorted(set(p[required]) - set(c[available]))
                if missing: reasons.append(f'{required}: missing {missing}')
            if p['context_requirement'] != 'not_applicable' and c['context_limit'] < p['context_requirement']: reasons.append('insufficient context')
            return reasons
        for index, c in enumerate(chain):
            reasons = rejection_reasons(c)
            if reasons: rejected.append({'identity':c['identity'],'fallback_index':index,'reasons':reasons})
            else: eligible.append({'identity':c['identity'],'fallback_index':index,'evidence':c['evidence']})
        selected = eligible[0] if eligible else None
        source = 'local' if selected else None
        default = table['common_default']
        provenance = {'consulted': False, 'selected': False, 'identity': default['identity'],
                      'evidence': default['evidence'], 'reasons': []}
        if selected:
            provenance['reasons'] = ['local candidate eligible']
        elif row is None:
            provenance['reasons'] = ['no table row']
        else:
            provenance['consulted'] = True
            # A changed effort must not revive the same failed/ineligible model.
            duplicate = any((c['identity']['route'], c['identity']['model']) ==
                            (default['identity']['route'], default['identity']['model']) for c in chain)
            reasons = ['duplicate local route/model'] if duplicate else rejection_reasons(default)
            provenance['reasons'] = reasons
            if not reasons:
                selected = {'identity': default['identity'], 'fallback_index': None, 'evidence': default['evidence']}
                source = 'common_default'
                provenance['selected'] = True
        selection_reasons = ([r for r in rejected if source == 'common_default' or
                              r['fallback_index'] < selected['fallback_index']] if selected else [])
        results.append({'unit_id':unit['id'],'status':'MATCH' if selected else 'NO_MATCH','selected':selected['identity'] if selected else None,'evidence':selected['evidence'] if selected else [],'reason':None if selected else ('no table row' if row is None else 'no eligible candidate'),'rejected':rejected,
                        'eligible_chain':eligible,'fallback_index':selected['fallback_index'] if selected else None,'selection_reasons':selection_reasons,
                        'selected_source':source,'default_provenance':provenance})
    return {'version':2,'profile_sha256':digest(document),'table_sha256':digest(table),'source_sha256':digest(priors),'pins_sha256':digest(pins),'hash_format':'sha256 of UTF-8 canonical JSON (sorted keys, compact separators, unescaped Unicode)','results':results,'authority':'proposal only; table evidence is unverified; existing host and policy checks remain required'}

def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('command',choices=['prepare','validate']); parser.add_argument('profile'); parser.add_argument('--table',default=str(ASSETS / 'worker-routing-table.json')); parser.add_argument('--pins')
    args = parser.parse_args()
    try:
        result = prepare(load_json(args.profile),load_json(args.table),load_json(args.pins) if args.pins else None)
        print(json.dumps(result,sort_keys=True,indent=2)); return 0 if all(r['status']=='MATCH' for r in result['results']) else 2
    except (ProfileError, OSError, ValueError) as exc:
        print(json.dumps({'status':'error','code':getattr(exc,'code','INVALID_JSON'),'detail':str(exc)})); return 1
if __name__ == '__main__': raise SystemExit(main())
