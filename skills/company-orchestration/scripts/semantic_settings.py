#!/usr/bin/env python3
"""Bounded, read-only Orca profile settings observation; prints hashes only."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
from host_model_catalog import EXPLICIT_HOST_VERSION, SAVED_ONLY_VERSIONS, strict_json

KIND = 'orca-profile-settings/v1'
LEGACY_VERSION = '1.4.245'
SETTINGS_VERSIONS = (LEGACY_VERSION, *SAVED_ONLY_VERSIONS)
MAX_BYTES = 1024 * 1024
COLUMNS = [('domain', 'TEXT', 1, 1), ('payload', 'TEXT', 1, 0),
           ('domain_version', 'INTEGER', 1, 0), ('revision', 'INTEGER', 1, 0),
           ('updated_at', 'INTEGER', 1, 0), ('content_hash', 'TEXT', 1, 0)]


def require(ok, message):
    if not ok:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()


def authority(database, *, app_version=LEGACY_VERSION, user_data=None):
    require(app_version in SETTINGS_VERSIONS, 'unreviewed settings observation version')
    require((app_version == EXPLICIT_HOST_VERSION) == (user_data is not None),
            'explicit catalog user-data directory required only for its reviewed version')
    path = Path(database)
    app = Path(user_data) if user_data is not None else Path.home() / 'Library/Application Support/Orca'
    if user_data is not None:
        require(app.is_absolute() and app.resolve(strict=True) == app and app.is_dir(),
                'exact canonical local Orca user-data directory required')
    require(path.is_absolute() and path == path.resolve() and path.name == 'profile-state.db'
            and path.parent.parent == app / 'profiles', 'exact canonical local Orca profile database required')
    return path, app


def external_files(app):
    return [('config', app / 'orca-profile-index.json'),
            ('config', Path.home() / '.codex/config.toml'),
            ('config', app / 'codex-runtime-home' / 'home' / 'config.toml'),
            ('auth_policy', Path.home() / '.codex/auth.json'),
            ('auth_policy', app / 'codex-runtime-home' / 'home' / 'auth.json'),
            ('auth_policy', app / 'codex-hook-trust.json')]


def observe(database, worktree, *, app_version=LEGACY_VERSION, user_data=None):
    path, app = authority(database, app_version=app_version, user_data=user_data)
    require(isinstance(worktree, str) and worktree.startswith('id:') and '::/' in worktree,
            'exact worktree required')
    # Index remains a separate byte pin; ensure the DB is the selected profile.
    index_path = app / 'orca-profile-index.json'
    if user_data is not None:
        require(index_path.resolve(strict=True) == index_path, 'explicit profile index path changed')
    index = strict_json(index_path.read_bytes())
    require(index.get('schemaVersion') == 1 and index.get('activeProfileId') == path.parent.name,
            'profile selection mismatch')
    try:
        connection = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=0.2)
        try:
            connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, MAX_BYTES * 2)
            connection.execute('PRAGMA query_only=ON')
            connection.execute('BEGIN')
            # All reads use this snapshot, including committed, uncheckpointed WAL.
            schema = connection.execute("SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type,name").fetchmany(257)
            require(len(schema) <= 256 and len(canonical(schema)) <= MAX_BYTES, 'schema bound exceeded')
            columns = connection.execute('PRAGMA table_info(profile_state_documents)').fetchall()
            require([(r[1], r[2], r[3], r[5]) for r in columns] == COLUMNS
                    and all(r[4] is None for r in columns), 'unknown settings table schema')
            rows = connection.execute("SELECT domain_version,length(CAST(payload AS BLOB)) FROM profile_state_documents WHERE domain='settings'").fetchall()
            require(len(rows) == 1 and rows[0][0] == 1 and type(rows[0][1]) is int
                    and 0 < rows[0][1] <= MAX_BYTES, 'missing, oversized or unknown settings domain')
            raw = connection.execute("SELECT payload FROM profile_state_documents WHERE domain='settings'").fetchone()[0]
            settings = strict_json(raw)
            require(isinstance(settings, dict), 'settings must be an object')
            value = {'kind': KIND, 'app_version': app_version, 'path': str(path),
                     'profile': path.parent.name, 'worktree': worktree,
                     'namespace': 'profile_state_documents/settings', 'domain_version': 1,
                     'schema': schema, 'settings': settings}
            digest = hashlib.sha256(canonical(value)).hexdigest()
        finally:
            connection.close()
    except (sqlite3.Error, RecursionError, OverflowError) as error:
        # Do not surface SQL payloads, credentials or raw database contents.
        raise ValueError('settings SQLite read failed: ' + type(error).__name__) from None
    return {'kind': KIND, 'role': 'config', 'path': str(path), 'sha256': digest}


def prepare(database, worktree, *, app_version=LEGACY_VERSION, user_data=None):
    rows = [observe(database, worktree, app_version=app_version, user_data=user_data)]
    for role, path in external_files(Path(rows[0]['path']).parents[2]):
        rows.append({'role': role, 'path': str(path),
                     'sha256': hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None})
    return rows


def validate_rows(rows, worktree, *, app_version=LEGACY_VERSION, user_data=None):
    semantic = [row for row in rows if row.get('kind') == KIND]
    require(len(semantic) == 1, 'exactly one semantic settings observation required')
    row = semantic[0]
    require(set(row) == {'kind', 'role', 'path', 'sha256'} and row['role'] == 'config',
            'invalid semantic settings observation')
    path, app = authority(row['path'], app_version=app_version, user_data=user_data)
    required = {(role, str(p)) for role, p in external_files(app)}
    actual = set((r.get('role'), r.get('path')) for r in rows if r.get('kind') in (None, 'file'))
    require(required <= actual, 'required external config/auth observations missing')
    require(not any(r is not row and r.get('path') in (str(path), str(path)+'-wal', str(path)+'-shm') for r in rows),
            'do not byte-pin mutable database/WAL alongside semantic settings')
    require(observe(path, worktree, app_version=app_version, user_data=user_data) == row,
            'observed semantic settings changed; reprepare')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True)
    parser.add_argument('--worktree', required=True)
    parser.add_argument('--app-version', choices=SETTINGS_VERSIONS, default=LEGACY_VERSION)
    parser.add_argument('--user-data', help='exact local user-data directory for 1.4.269')
    args = parser.parse_args()
    try:
        print(json.dumps(prepare(args.database, args.worktree, app_version=args.app_version,
                                 user_data=args.user_data), indent=2))
        return 0
    except (ValueError, OSError, TypeError, KeyError, RecursionError):
        print(json.dumps({'ok': False, 'error': 'semantic settings observation denied'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
