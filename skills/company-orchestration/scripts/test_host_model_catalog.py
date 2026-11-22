"""Synthetic metadata fixtures, never real host/provider execution evidence."""
import copy
import os
import json
import unittest
from unittest.mock import patch

import host_model_catalog as catalog
import record_check
import routing_launch
from catalog_test_support import CatalogFixture, catalog_fixture, launch_fixture, routing_packet


class CatalogTests(unittest.TestCase):
    def test_inventory_reference_supports_common_and_legacy_and_rejects_conflicts(self):
        from host_model_catalog import inventory_reference
        self.assertEqual(inventory_reference({'binding': {'inventory_evidence': 'i'}}), 'i')
        self.assertEqual(inventory_reference({'price_selection': {'inventory_evidence': 'i'}}), 'i')
        self.assertEqual(inventory_reference({'binding': {'inventory_evidence': 'i'},
                                               'price_selection': {'inventory_evidence': 'i'}}), 'i')
        for document in ({}, {'binding': {'inventory_evidence': ''}},
                         {'binding': {'inventory_evidence': 'a'},
                          'price_selection': {'inventory_evidence': 'b'}}):
            with self.subTest(document=document), self.assertRaises(ValueError):
                inventory_reference(document)
    def setUp(self):
        self.fixture = self.enterContext(catalog_fixture())

    def save(self):
        self.fixture.save()

    def load(self, **kwargs):
        return catalog.load(self.fixture.root, self.fixture.digest, worktree=self.fixture.worktree,
                            model='fixture-model', effort='low', now=self.fixture.now, **kwargs)

    def test_fixture_builders_do_not_share_mutable_data(self):
        first = routing_packet()
        second = routing_packet()
        self.assertEqual(first, second)
        first['price_selection']['candidates'][0]['model'] = 'changed'
        first['evidence']['inventory']['host_models'].clear()
        self.assertEqual(second, routing_packet())
        with catalog_fixture() as other:
            other.response['result']['models'].clear()
            self.assertTrue(self.fixture.response['result']['models'])
        self.assertFalse(other.root.exists())

    def test_fixture_preparation_failure_releases_resources_and_patches(self):
        environment = dict(os.environ)
        home = record_check.canonical_home
        which = routing_launch.shutil.which
        roots = []
        save = CatalogFixture.save
        def fail_after_save(fixture):
            roots.append(fixture.root)
            roots.append(record_check.canonical_home())
            save(fixture)
            raise RuntimeError('fixture preparation failed')
        with patch.object(CatalogFixture, 'save', fail_after_save):
            with self.assertRaisesRegex(RuntimeError, 'fixture preparation failed'):
                with launch_fixture(lambda: self.fail('configuration must not run')):
                    self.fail('failed preparation must not yield')
        self.assertEqual(dict(os.environ), environment)
        self.assertIs(record_check.canonical_home, home)
        self.assertIs(routing_launch.shutil.which, which)
        self.assertTrue(roots)
        self.assertTrue(all(not root.exists() for root in roots))

    def test_shared_cache_mutation_does_not_change_pinned_metadata(self):
        before = self.load()
        cache = self.fixture.root / 'models_cache.json'
        for value in ('{}', '{malformed unrelated writer', '{"fetched_at":"changed","models":[]}'):
            cache.write_text(value)
            after = self.load()
            self.assertEqual(before, after)
            catalog.compare(before, after)
        self.assertFalse(after['launch_authorized'])

    def test_manifest_and_raw_tampering(self):
        for name in ('manifest.json', 'response-1.json'):
            with self.subTest(name=name):
                self.save()
                with (self.fixture.root / name).open('ab') as stream:
                    stream.write(b' ')
                with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                    self.load()

    def test_selected_model_and_effort_absent(self):
        original = copy.deepcopy(self.fixture.response)
        for field in ('id', 'efforts'):
            self.fixture.response = copy.deepcopy(original)
            self.fixture.response['result']['models'][0][field] = 'other' if field == 'id' else [{'value': 'high'}]
            self.save()
            with self.assertRaisesRegex(ValueError, 'selected model/effort absent'):
                self.load()

    def test_stale_receipt_cannot_be_refreshed_by_fetched_at(self):
        self.fixture.manifest['receipts'][-1]['received_at'] = '2025-01-01T00:00:00Z'
        self.save()
        with self.assertRaises(ValueError):
            self.load()

    def test_fresh_receipt_cannot_hide_stale_or_future_provider_metadata(self):
        for seconds in (-301, 1):
            self.fixture.response['result']['fetchedAt'] = (self.fixture.now.timestamp() + seconds) * 1000
            self.save()
            with self.assertRaisesRegex(ValueError, 'host catalog'):
                self.load()

    def test_partial_pagination_unavailable_and_fallback_rejected(self):
        original = copy.deepcopy(self.fixture.response)
        for field, value in [('listingInProgress', True), ('waitExpired', True), ('nextCursor', 'next'), ('hasMore', True),
                             ('complete', False), ('unavailable', {'reason': 'auth'}), ('origin', 'unknown')]:
            with self.subTest(field=field):
                self.fixture.response = copy.deepcopy(original)
                self.fixture.response['result'][field] = value
                self.save()
                with self.assertRaises(ValueError):
                    self.load()

    def test_unknown_completeness_not_promoted_to_true(self):
        metadata = self.load()
        self.assertIn('provider_list_completeness', metadata['unknown'])
        self.assertNotIn('complete', metadata['host_result'])

    def test_same_runtime_cannot_mask_app_version_change(self):
        before = self.load()
        for version in ('1.4.261', '1.4.263'):
            with self.subTest(version=version):
                self.fixture.manifest['app_version'] = self.fixture.status['result']['appVersion'] = version
                self.save()
                after = self.load()
                self.assertEqual(after['app_version'], version)
                with self.assertRaisesRegex(ValueError, 'explicit reprepare'):
                    catalog.compare(before, after)

    def test_saved_catalog_requires_literal_parameter_and_workspace_observation(self):
        self.fixture.use_saved_catalog()
        self.assertFalse(self.load()['launch_authorized'])
        params = self.fixture.manifest['receipts'][1]['params']
        for value in (1, False, None):
            params['savedOnly'] = value
            self.save()
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'saved-only'):
                self.load()
        params['savedOnly'] = True
        self.fixture.response['result'].pop('modelsDifferByWorkspace')
        self.save()
        with self.assertRaisesRegex(ValueError, 'verified workspace catalog'):
            self.load()

    def test_saved_catalog_does_not_accept_older_status_capabilities(self):
        self.fixture.use_saved_catalog()
        current = self.fixture.status['result']['capabilities']
        for missing in current:
            self.fixture.status['result']['capabilities'] = [value for value in current if value != missing]
            self.save()
            with self.subTest(missing=missing), self.assertRaisesRegex(ValueError, 'unverified host provenance'):
                self.load()
        self.fixture.status['result']['capabilities'] = ' '.join(current)
        self.save()
        with self.assertRaisesRegex(ValueError, 'unverified host provenance'):
            self.load()

    def test_explicit_host_receipt_and_runtime_binding(self):
        app = self.fixture.root / 'Orca.app'
        data = self.fixture.root / 'profile'
        self.fixture.bind_explicit_host(app, data)
        metadata = self.load()
        self.assertEqual(metadata['host']['user_data'], str(data))
        catalog.verify_local_host(metadata)
        for file, value in (
                (data/'orca-runtime.json', {'runtimeId': 'other'}),
                (data/'host-installation.json', {'installationId': 'other'}),
                (app/'Contents/_CodeSignature/CodeResources', 'replaced seal')):
            with self.subTest(file=file.name):
                before = file.read_bytes()
                file.write_text(json.dumps(value))
                with self.assertRaisesRegex(ValueError, 'catalog .* changed'):
                    catalog.verify_local_host(metadata)
                file.write_bytes(before)
        self.fixture.manifest['host']['user_data'] = str(data.parent/'other-profile')
        self.save()
        with self.assertRaisesRegex(ValueError, 'explicit reprepare'):
            catalog.compare(metadata, self.load())
        self.fixture.manifest.pop('host')
        self.save()
        with self.assertRaisesRegex(ValueError, 'explicit local catalog host required'):
            self.load()

    def test_269_saved_result_rejects_partial_unknown_stale_and_tampered_evidence(self):
        self.fixture.bind_explicit_host(self.fixture.root/'Orca.app', self.fixture.root/'isolated')
        self.assertFalse(self.load()['launch_authorized'])
        baseline = copy.deepcopy(self.fixture.response['result'])
        for changes, message in (
                ({'listingInProgress': True}, 'partial listing'),
                ({'listingNamesConfiguredModel': False}, 'verified workspace catalog'),
                ({'unavailable': {'reason': 'auth'}}, 'catalog unavailable'),
                ({'fetchedAt': 1}, 'stale or future host catalog'),
                ({'models': [{**baseline['models'][0], 'effortsKnown': False}]}, 'unverified model efforts'),
                ({'models': [{'id': 'fixture-model', 'efforts': [{'value': 'other'}]}]}, 'model/effort absent')):
            with self.subTest(changes=changes):
                self.fixture.response['result'] = {**baseline, **changes}
                self.save()
                with self.assertRaisesRegex(ValueError, message):
                    self.load()
        (self.fixture.root/'response-1.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'response hash mismatch'):
            self.load()

    def test_malformed_duplicate_nonfinite_models(self):
        original = copy.deepcopy(self.fixture.response)
        for models in ([], None, [{}], [{'id': 'x', 'efforts': []}],
                       original['result']['models'] * 2):
            self.fixture.response['result']['models'] = models
            self.save()
            with self.assertRaises(ValueError):
                self.load()
        for raw in ('{"x":1,"x":2}', '{"x":NaN}', '{malformed'):
            with self.assertRaises(ValueError):
                catalog.strict_json(raw)

    def test_provider_context_capability_change_requires_reprepare(self):
        before = self.load()
        for field, value in [('provider', 'different-provider'), ('contextWindow', 1),
                             ('tools', ['changed']), ('unknownCriticalField', False)]:
            after = copy.deepcopy(before)
            after['host_result'][field] = value
            with self.assertRaisesRegex(ValueError, 'explicit reprepare'):
                catalog.compare(before, after)
        after = copy.deepcopy(before)
        after['worktree'] = 'id:fixture-repo::/another'
        with self.assertRaises(ValueError):
            catalog.compare(before, after)

    def test_runtime_request_worktree_mismatch_rejected(self):
        self.fixture.response['_meta']['runtimeId'] = 'other-runtime'
        self.save()
        with self.assertRaisesRegex(ValueError, 'runtime identity'):
            self.load()
        self.fixture.response['_meta']['runtimeId'] = 'fixture-runtime'
        self.fixture.manifest['receipts'][-1]['params']['worktree'] = 'current'
        self.save()
        with self.assertRaisesRegex(ValueError, 'context mismatch'):
            self.load()

    def test_equal_catalog_cannot_prove_unchanged_unreported_provider(self):
        metadata = self.load()
        catalog.compare(metadata, metadata)
        with self.assertRaisesRegex(ValueError, 'catalog_requires_checked_launcher'):
            catalog.require_launch_authority(metadata)

    def test_forged_capability_provider_fields_do_not_grant_launch(self):
        metadata = self.load()
        metadata.update(launch_authorized=True, authenticated=True, billing='subscription', tools=['exec'])
        metadata['host_result'].update(provider='invented', complete=True)
        with self.assertRaisesRegex(ValueError, 'catalog_requires_checked_launcher'):
            catalog.require_launch_authority(metadata)


if __name__ == '__main__':
    unittest.main()
