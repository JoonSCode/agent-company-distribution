"""Synthetic SQLite WAL + fake checked host, never a real launch."""
import copy
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

import semantic_settings as settings
import company_config
import routing_launch
from catalog_test_support import launch_fixture, semantic_database


class SemanticSettingsTests(unittest.TestCase):
    def setUp(self):
        self.fixture = self.enterContext(launch_fixture(company_config.resolve))
        self.sqlite = self.enterContext(semantic_database(self.fixture.inventory.root))
        self.rows = settings.prepare(self.sqlite.database, self.fixture.catalog.worktree)
        self.fixture.inventory.packet['binding']['host_catalog']['observed_files'] = self.rows
        self.write_packet()

    def write_packet(self):
        self.fixture.write_packet()

    def invoke_catalog(self):
        return self.fixture.invoke(routing_launch.main)

    def update(self, value):
        self.sqlite.db.execute("UPDATE profile_state_documents SET payload=?,revision=revision+1 WHERE domain='settings'", (json.dumps(value),))
        self.sqlite.db.commit()

    def deny(self):
        self.write_packet()
        code, output = self.invoke_catalog()
        self.assertEqual((code, self.fixture.starts), (1, 0), output)

    def test_semantic_context_failure_closes_writer_and_restores_home(self):
        writers = []
        with self.assertRaisesRegex(RuntimeError, 'test body failed'):
            with semantic_database(self.fixture.inventory.root / 'failure') as fixture:
                writers.append(fixture.db)
                self.assertEqual(Path.home(), fixture.home)
                self.assertTrue(Path(str(fixture.database) + '-wal').exists())
                raise RuntimeError('test body failed')
        self.assertEqual(Path.home(), self.sqlite.home)
        with self.assertRaises(sqlite3.ProgrammingError):
            writers[0].execute('SELECT 1')
        # Closing a nested writer must not close this test's independently owned writer.
        self.assertEqual(self.sqlite.db.execute('SELECT 1').fetchone(), (1,))

    def test_semantic_preparation_failure_closes_writer(self):
        connection = sqlite3.connect(':memory:')
        connection.execute('CREATE TABLE profile_state_documents (existing TEXT)')
        with patch('catalog_test_support.sqlite3.connect', return_value=connection):
            with self.assertRaisesRegex(sqlite3.OperationalError, 'already exists'):
                with semantic_database(self.fixture.inventory.root / 'prepare-failure'):
                    self.fail('failed schema preparation must not yield')
        self.assertEqual(Path.home(), self.sqlite.home)
        with self.assertRaises(sqlite3.ProgrammingError):
            connection.execute('SELECT 1')

    def test_unrelated_ui_wal_and_checkpoint_allow(self):
        before = settings.observe(self.sqlite.database, self.fixture.catalog.worktree)
        for checkpoint in (False, True):
            self.sqlite.db.execute("UPDATE profile_state_documents SET payload=?,revision=revision+1 WHERE domain='ui'", (json.dumps({'counter': checkpoint}),))
            self.sqlite.db.commit()
            if checkpoint: self.sqlite.db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
            self.assertEqual(settings.observe(self.sqlite.database, self.fixture.catalog.worktree), before)
        code, output = self.invoke_catalog()
        self.assertEqual((code, self.fixture.starts, self.fixture.refreshes), (0, 1, 1), output)

    def test_relevant_edit_add_delete_uncheckpointed_denies(self):
        for key in self.sqlite.value:
            for action in ('edit', 'delete'):
                with self.subTest(key=key, action=action):
                    value = copy.deepcopy(self.sqlite.value)
                    if action == 'edit': value[key] = {'changed': 'synthetic'}
                    else: del value[key]
                    self.update(value)
                    self.assertNotEqual(settings.observe(self.sqlite.database, self.fixture.catalog.worktree), self.rows[0])
                    self.deny()
                    self.update(self.sqlite.value)
        self.update({**self.sqlite.value, 'newLaunchSetting': 'added'})
        self.deny()

    def test_refresh_relevant_change_denies(self):
        self.fixture.change_at_refresh = lambda _: self.update({**self.sqlite.value, 'provider': 'changed'})
        self.deny()
        self.assertEqual(self.fixture.refreshes, 1)

    def test_external_auth_change_denies(self):
        p = self.sqlite.home / '.codex/auth.json'
        p.parent.mkdir(parents=True)
        p.write_text('synthetic-auth-change')
        self.deny()

    def test_saved_catalog_requires_versioned_semantic_pin_through_refresh(self):
        self.fixture.catalog.use_saved_catalog()
        packet = self.fixture.inventory.packet
        packet['evidence']['inventory']['sha256'] = self.fixture.catalog.digest
        binding = packet['binding']['host_catalog']
        legacy = self.rows
        binding['observed_files'] = legacy[1:]
        self.deny()
        self.assertEqual(self.fixture.refreshes, 0)
        binding['observed_files'] = legacy
        self.deny()
        self.assertEqual(self.fixture.refreshes, 0)
        rows = settings.prepare(self.sqlite.database, self.fixture.catalog.worktree, app_version='1.4.268')
        self.assertNotEqual(rows[0]['sha256'], legacy[0]['sha256'])
        self.assertEqual(rows[1:], legacy[1:])
        binding['observed_files'] = rows
        self.write_packet()
        code, output = self.invoke_catalog()
        self.assertEqual((code, self.fixture.starts, self.fixture.refreshes), (0, 1, 1), output)

    def test_saved_catalog_rejects_settings_change_during_refresh(self):
        self.fixture.catalog.use_saved_catalog()
        packet = self.fixture.inventory.packet
        packet['evidence']['inventory']['sha256'] = self.fixture.catalog.digest
        packet['binding']['host_catalog']['observed_files'] = settings.prepare(
            self.sqlite.database, self.fixture.catalog.worktree, app_version='1.4.268')
        self.fixture.change_at_refresh = lambda _: self.update({**self.sqlite.value, 'permissionMode': 'changed'})
        self.deny()
        self.assertEqual(self.fixture.refreshes, 1)

    def test_explicit_host_observations_require_the_selected_user_data_and_profile(self):
        root = self.fixture.inventory.root
        user_data = root / 'isolated'
        database = self.enterContext(semantic_database(root, user_data=user_data)).database
        worktree = self.fixture.catalog.worktree
        options = {'app_version': '1.4.269', 'user_data': user_data}
        rows = settings.prepare(database, worktree, **options)
        settings.validate_rows(rows, worktree, **options)
        self.assertEqual(rows[0]['path'], str(database))
        paths = {row['path'] for row in rows}
        self.assertIn(str(user_data.joinpath('codex-runtime-home', 'home', 'auth.json')), paths)
        self.assertFalse(any(path.startswith(str(self.sqlite.app)) for path in paths))
        with self.assertRaisesRegex(ValueError, 'local Orca profile database'):
            settings.prepare(self.sqlite.database, worktree, **options)
        with self.assertRaisesRegex(ValueError, 'explicit catalog user-data'):
            settings.prepare(database, worktree, app_version='1.4.269')
        with self.assertRaisesRegex(ValueError, 'changed; reprepare'):
            settings.validate_rows(rows, worktree+'-changed', **options)
        (user_data/'orca-profile-index.json').write_text('{"schemaVersion":1,"activeProfileId":"other"}')
        with self.assertRaisesRegex(ValueError, 'profile selection mismatch'):
            settings.validate_rows(rows, worktree, **options)

    def test_spoof_kind_drop_files_raw_duplicate_wrong_profile_denies(self):
        original = copy.deepcopy(self.rows)
        for case in ('kind', 'role', 'drop', 'raw', 'path', 'profile'):
            with self.subTest(case=case):
                rows = copy.deepcopy(original)
                if case == 'kind': rows[0]['kind'] = 'ignore-database'
                if case == 'role': rows[0]['role'] = 'auth_policy'
                if case == 'drop': rows.pop()
                if case == 'raw': rows.append({'role': 'config', 'path': str(self.sqlite.database)+'-wal', 'sha256': None})
                if case == 'path': rows[0]['path'] = str(self.fixture.inventory.root / 'arbitrary.db')
                if case == 'profile': (self.sqlite.app/'orca-profile-index.json').write_text('{"schemaVersion":1,"activeProfileId":"other"}')
                self.fixture.inventory.packet['binding']['host_catalog']['observed_files'] = rows
                self.deny()

    def test_missing_domain_unknown_version_and_key_presence_denies(self):
        for sql in ("UPDATE profile_state_documents SET domain_version=2 WHERE domain='settings'",
                    "DELETE FROM profile_state_documents WHERE domain='settings'"):
            with self.subTest(sql=sql):
                self.sqlite.db.execute(sql); self.sqlite.db.commit(); self.deny()

    def test_unknown_schema_denies(self):
        self.sqlite.db.execute('ALTER TABLE profile_state_documents ADD COLUMN unknown TEXT')
        self.sqlite.db.commit()
        self.deny()

    def test_exclusive_lock_denies(self):
        self.sqlite.db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        self.sqlite.db.execute('PRAGMA journal_mode=DELETE')
        self.sqlite.db.execute('BEGIN EXCLUSIVE')
        self.deny()
        self.sqlite.db.rollback()

    def test_sqlite_read_failure_denies(self):
        with patch('semantic_settings.sqlite3.connect', side_effect=sqlite3.OperationalError('readonly failure')):
            self.deny()

    def test_missing_database_denies(self):
        self.sqlite.db.close()
        self.sqlite.database.unlink()
        self.deny()
        self.assertFalse(self.sqlite.database.exists())

    def test_corrupt_database_denies(self):
        self.sqlite.db.close()
        self.sqlite.database.write_bytes(b'not sqlite')
        self.deny()

    def test_unknown_start_no_retry(self):
        self.fixture.timeout_start = True
        code, output = self.invoke_catalog()
        self.assertEqual((code, self.fixture.starts), (1, 1), output)
        self.assertEqual(json.loads((self.fixture.inventory.root/'result.json').read_text())['launch_state'], 'unknown')
        code, output = self.invoke_catalog()
        self.assertEqual((code, self.fixture.starts, self.fixture.refreshes), (1, 1, 1), output)
