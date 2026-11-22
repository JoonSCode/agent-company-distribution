#!/usr/bin/env python3
"""Validate untrusted worker-unit proposals. No host access or execution authority.

validate_profile_document(document) returns the original document or raises
ProfileError(code, detail). CLI: worker_profile.py validate PROFILE.json.
"""
import argparse
import json
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / 'assets'

class ProfileError(ValueError):
    def __init__(self, code, detail):
        self.code, self.detail = code, detail
        super().__init__(f'{code}: {detail}')

def load_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ProfileError('INVALID_JSON', f'duplicate key: {key}')
            result[key] = value
        return result
    with open(path, encoding='utf-8') as stream:
        return json.load(stream, object_pairs_hook=pairs)

def validate_schema(value, schema, path='$'):
    """Validate the self-contained subset used by the bundled strict schemas."""
    def fail(message):
        raise ProfileError('INVALID_DOCUMENT', f'{path}: {message}')
    if 'oneOf' in schema:
        matches = 0
        for branch in schema['oneOf']:
            try:
                validate_schema(value, branch, path)
                matches += 1
            except ProfileError:
                pass
        if matches != 1: fail('must match exactly one allowed shape')
        return
    if 'const' in schema and (type(value) is not type(schema['const']) or value != schema['const']): fail('invalid version or constant')
    if 'enum' in schema and value not in schema['enum']: fail('unsupported value')
    typ = schema.get('type')
    types = {'object': dict, 'array': list, 'string': str, 'integer': int, 'boolean': bool}
    if typ and type(value) is not types[typ]: fail(f'expected {typ}')
    if typ == 'string' and len(value.strip()) < schema.get('minLength', 0): fail('empty string')
    if typ == 'integer' and value < schema.get('minimum', value): fail('below minimum')
    if typ == 'object':
        missing = set(schema.get('required', [])) - value.keys()
        if missing: fail('missing ' + ', '.join(sorted(missing)))
        props = schema.get('properties', {})
        if schema.get('additionalProperties') is False and set(value) - props.keys(): fail('unexpected fields: ' + ', '.join(sorted(set(value)-props.keys())))
        for key in value.keys() & props.keys(): validate_schema(value[key], props[key], path + '.' + key)
    if typ == 'array':
        if len(value) < schema.get('minItems', 0): fail('too few items')
        if 'maxItems' in schema and len(value) > schema['maxItems']: fail('too many items')
        if schema.get('uniqueItems') and len({json.dumps(x, sort_keys=True) for x in value}) != len(value): fail('duplicate items')
        for i, item in enumerate(value): validate_schema(item, schema['items'], f'{path}[{i}]')

def validate_profile_document(document):
    # Provide actionable distinctions before structural validation.
    if isinstance(document, dict) and isinstance(document.get('units'), list):
        for unit in document['units']:
            if not isinstance(unit, dict) or not isinstance(unit.get('profile'), dict):
                raise ProfileError('PROFILE_INCOMPLETE', 'unit profile missing')
            p = unit['profile']
            for key in ('difficulty','family','input_modalities','output_modalities','required_capabilities','required_tools','context_requirement','hard_constraints','uncertainties'):
                if key not in p or p[key] is None or (key in ('difficulty','family','input_modalities','output_modalities') and not p[key]):
                    raise ProfileError('PROFILE_INCOMPLETE', f'missing {key}')
            if p['difficulty'] not in ('easy','medium','hard'):
                raise ProfileError('PROFILE_INCOMPLETE', 'unknown difficulty')
            if p['context_requirement'] != 'not_applicable' and (type(p['context_requirement']) is not int or p['context_requirement'] < 1):
                raise ProfileError('PROFILE_INCOMPLETE', 'unknown context requirement')
            if p.get('uncertainties'): raise ProfileError('PROFILE_INCOMPLETE', 'unresolved uncertainties: ' + str(p['uncertainties']))
            schema = load_json(ASSETS / 'worker-profile.schema.json')['properties']['units']['items']['properties']['profile']['properties']
            for key in ('family','input_modalities','output_modalities','required_capabilities'):
                allowed = schema[key].get('enum', schema[key].get('items', {}).get('enum', []))
                values = p[key] if isinstance(p[key], list) else [p[key]]
                if any(v not in allowed for v in values): raise ProfileError('UNSUPPORTED_PROFILE', f'unsupported {key}')
    validate_schema(document, load_json(ASSETS / 'worker-profile.schema.json'))
    units = document['units']; ids = [u['id'] for u in units]
    if len(set(ids)) != len(ids): raise ProfileError('INVALID_DAG', 'duplicate unit id')
    graph = {u['id']: u['depends_on'] for u in units}
    visiting, done = set(), set()
    def visit(node):
        if node in visiting: raise ProfileError('INVALID_DAG', 'dependency cycle')
        if node in done: return
        visiting.add(node)
        for dep in graph[node]:
            if dep not in graph: raise ProfileError('INVALID_DAG', f'unknown dependency {dep}')
            visit(dep)
        visiting.remove(node); done.add(node)
    for node in ids: visit(node)
    return document

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['validate', 'compare']); parser.add_argument('profile')
    parser.add_argument('reviewed', nargs='?', help='accepted profile to compare with the candidate')
    args = parser.parse_args()
    if (args.command == 'compare') != (args.reviewed is not None):
        parser.error('compare requires a candidate profile and a reviewed profile')
    try:
        candidate = validate_profile_document(load_json(args.profile))
        if args.reviewed is not None:
            reviewed = validate_profile_document(load_json(args.reviewed))
            actual, expected = (
                {row['id']: {**row, 'depends_on': sorted(row['depends_on'])} for row in doc['units']}
                for doc in (candidate, reviewed)
            )
            added, removed = sorted(actual.keys() - expected.keys()), sorted(expected.keys() - actual.keys())
            changed = {uid: sorted(key for key in expected[uid] if actual[uid][key] != expected[uid][key])
                       for uid in sorted(actual.keys() & expected.keys()) if actual[uid] != expected[uid]}
            match = not (added or removed or changed)
            print(json.dumps(dict(status='match' if match else 'mismatch', added=added, removed=removed,
                                  changed=changed, launch_authorized=False)))
            return 0 if match else 1
        print(json.dumps({'status':'valid'}))
    except (ProfileError, OSError, ValueError) as exc:
        print(json.dumps({'status':'error','code':getattr(exc,'code','INVALID_JSON'),'detail':str(exc)})); return 1
    return 0
if __name__ == '__main__': raise SystemExit(main())
