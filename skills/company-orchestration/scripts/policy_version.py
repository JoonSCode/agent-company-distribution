#!/usr/bin/env python3
"""Read-only common-guidance/Company fingerprints; no synchronization mutations."""
import argparse
import json
import os
from pathlib import Path
import re
import sys

# Select Python's normal cache prefix before importing Company modules.
# Restrict this to the CLI process; callers importing a module are unchanged.
if __name__ == "__main__":
    import os as _os
    import sys as _sys
    _sys.pycache_prefix = _os.path.join(_os.path.abspath(_os.path.expanduser("~")), ".cache", "agent-company", "python")

# Importing a helper must not create bytecode inside managed installed skills.
sys.dont_write_bytecode = True
from orca_contract import decode, digest, load_package, require

SCHEMA = 'company-policy-version/v1'
BEGIN = '<!-- BEGIN Host Local Guidance -->'
END = '<!-- END Host Local Guidance -->'


def common_guidance(data):
    text = data.decode('utf-8')
    starts = list(re.finditer('^' + re.escape(BEGIN) + '$', text, re.MULTILINE))
    ends = list(re.finditer('^' + re.escape(END) + '$', text, re.MULTILINE))
    if not starts and not ends:
        return data
    require(len(starts) == 1 and len(ends) == 1,
            'Host Local Guidance markers must form one complete block')
    start, finish = starts[0].start(), ends[0].end()
    require(start < ends[0].start(), 'Host Local Guidance markers are reversed')
    if text[finish:finish + 1] == '\n':
        finish += 1
    return (text[:start] + text[finish:]).encode('utf-8')


def snapshot(home):
    package = home / 'skills/company-orchestration'
    baseline = load_package(package)
    guidance = (home / 'AGENTS.md').read_bytes()
    active = decode((home / 'agent-company/active.json').read_bytes(), 'active')
    identity = active.get('snapshot_id')
    require(isinstance(identity, str) and re.fullmatch(r'[A-Za-z0-9._-]+', identity),
            'Unsafe/missing snapshot identity')
    manifest_data = (home / 'agent-company/snapshots' / identity / 'manifest.json').read_bytes()
    require(digest(manifest_data) == active.get('manifest_sha256'), 'Active manifest hash mismatch')
    manifest = decode(manifest_data, 'manifest')
    files = manifest.get('files')
    require(isinstance(files, dict) and files, 'Manifest file bindings are missing')
    # The standalone lock is Company-owned content. Only historical generations
    # exclude their former host-specific Core pin from common fingerprints.
    standalone = manifest.get('runtime_contract') == 'orca-company-standalone/v1'
    common_files = {key: value for key, value in files.items()
                    if key.startswith('repo/') and (standalone or key != 'repo/agent-company.lock.json')}
    require(common_files, 'Company source file bindings are missing')
    require(all(isinstance(key, str) and isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value)
                for key, value in common_files.items()), 'Malformed Company source file hash')
    fingerprint = digest(json.dumps(common_files, sort_keys=True).encode())
    policy = digest(json.dumps(baseline['policy_files'], sort_keys=True).encode())
    return {'schema_version': SCHEMA, 'global_common_sha256': digest(common_guidance(guidance)),
            'global_file_sha256': digest(guidance), 'company_content_sha256': fingerprint,
            'company_policy_sha256': policy, 'company_policy_revision': baseline['revision'],
            'company_source_commit': active.get('agent_company_ref'),
            'company_snapshot': identity, 'runtime_contract': manifest.get('runtime_contract'),
            'runtime_certification': 'standalone' if manifest.get('runtime_contract') == 'orca-company-standalone/v1' else 'historical_legacy',
            'scope': 'Actual bound policy integrity and pinned source content; not all runtime health or loaded agent context.'}


def compare(left, right):
    keys = ['global_common_sha256', 'company_content_sha256', 'company_policy_sha256']
    for value in [left, right]:
        require(value.get('schema_version') == SCHEMA, 'Unsupported snapshot schema')
        for key in keys:
            require(isinstance(value.get(key), str) and re.fullmatch(r'[0-9a-f]{64}', value[key]),
                    'Missing/invalid fingerprint: ' + key)
    changed = [key for key in keys if left[key] != right[key]]
    return {'status': 'drift' if changed else 'match', 'changed': changed,
            'runtime_contract_differs': left.get('runtime_contract') != right.get('runtime_contract'),
            'note': 'Host differences are reported separately; match does not authenticate a remote receipt.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('snapshot')
    p.add_argument('--codex-home', type=Path, default=Path(os.environ.get('CODEX_HOME', '~/.codex')).expanduser())
    p = sub.add_parser('compare')
    p.add_argument('local', type=Path)
    p.add_argument('peer', type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'snapshot':
            result, code = snapshot(args.codex_home.expanduser()), 0
        else:
            result = compare(decode(args.local.read_bytes(), 'local'), decode(args.peer.read_bytes(), 'peer'))
            code = 0 if result['status'] == 'match' else 1
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        result, code = {'status': 'unverifiable', 'error': str(exc)}, 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return code


if __name__ == '__main__':
    sys.exit(main())
