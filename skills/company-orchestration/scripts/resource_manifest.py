"""Validate user-declared resource limits; never inspect accounts or contact hosts."""
from datetime import datetime, timezone
import re
from offline_sidecar import read_json

FIELDS = {'service', 'approval_ref', 'auth', 'hosts', 'models', 'efforts', 'tools', 'billing', 'quota', 'spending_ceiling', 'observed_at', 'valid_until'}
TOKEN = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:/+-]{0,127}\Z')
SECRET = re.compile(r'(?:sk-|api[_-]?key|secret|password|bearer|token|credential)', re.I)


def token(value):
    return isinstance(value, str) and value.lower() not in ('unknown', 'none', 'null') and TOKEN.fullmatch(value) and not SECRET.search(value)


def time_value(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ', value):
        raise ValueError('canonical UTC timestamp required')
    return datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)


def check(root, name, *, required=False, service=None, host=None, model=None, effort=None, tools=None, billing=None, spend=None, now=None):
    """Return status/errors; valid declarations are not authenticated observations."""
    if name is None:
        return {'status': 'denied' if required else 'unknown', 'errors': ['manifest required'] if required else [], 'basis': 'not supplied'}
    try:
        doc = read_json(root, name)
        if not isinstance(doc, dict) or set(doc) != {'format', 'resources'} or doc['format'] != 'company-resource-manifest/v1' or not isinstance(doc['resources'], list) or not doc['resources']:
            raise ValueError('invalid manifest envelope')
        seen = set()
        for r in doc['resources']:
            if not isinstance(r, dict) or set(r) != FIELDS:
                raise ValueError('invalid resource fields; secrets forbidden')
            if not token(r['service']) or r['service'] in seen or not token(r['approval_ref']):
                raise ValueError('invalid service or nonsecret approval reference')
            seen.add(r['service'])
            for k in ('hosts', 'models', 'efforts', 'tools'):
                if not isinstance(r[k], list) or not r[k] or any(not token(x) for x in r[k]) or len(set(r[k])) != len(r[k]):
                    raise ValueError('invalid allowed ' + k)
            if r['auth'] not in ('authenticated', 'unauthenticated', 'unknown') or r['billing'] not in ('subscription', 'paid_api', 'unknown') or r['quota'] not in ('available', 'exhausted', 'unknown'):
                raise ValueError('invalid auth/billing/quota')
            ceiling = r['spending_ceiling']
            if ceiling is not None and (type(ceiling) not in (int, float) or not 0 <= ceiling <= 1000000):
                raise ValueError('invalid spending ceiling')
            if time_value(r['observed_at']) >= time_value(r['valid_until']):
                raise ValueError('invalid observation interval')
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise ValueError('timezone-aware current time required')
        r = next((x for x in doc['resources'] if x['service'] == service), None)
        if r is None:
            raise ValueError('service missing or unknown')
        errors = []
        if not time_value(r['observed_at']) <= current < time_value(r['valid_until']): errors.append('stale or future observation')
        if r['auth'] != 'authenticated': errors.append('authentication not declared authenticated')
        if r['quota'] != 'available': errors.append('quota not declared available')
        if billing not in ('subscription', 'paid_api') or r['billing'] != billing: errors.append('billing unknown or mismatch')
        for k, v in (('hosts', host), ('models', model), ('efforts', effort)):
            if v is None or v not in r[k]: errors.append(k + ' mismatch or unknown')
        if not isinstance(tools, (list, tuple)) or not tools or any(x not in r['tools'] for x in tools): errors.append('tools mismatch or unknown')
        if billing == 'paid_api' and (r['spending_ceiling'] is None or type(spend) not in (int, float) or not 0 <= spend <= r['spending_ceiling']): errors.append('paid spending authorization missing or exceeded')
        return {'status': 'denied' if errors else 'declared_ready', 'errors': errors, 'basis': 'user declaration; authenticity and live state unknown'}
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, RecursionError) as exc:
        return {'status': 'denied', 'errors': [str(exc)], 'basis': 'invalid declaration'}
