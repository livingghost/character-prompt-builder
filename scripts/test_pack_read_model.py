"""Pack acquisition, pure construction, and persistence use one input owner."""
from __future__ import annotations

from collections import Counter
from contextlib import closing
from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from builder_inputs import BuilderInputs, FileInput
import pack_cache as cache
import pack_manager as packs
import runtime_snapshot
from state_protocol import schema_read_scope


class PackReadModelTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / 'pack'
        self.manifest = packs.initialize_pack(self.root, name='Synthetic acquired catalog', release='2026.11.07.1')
        self.manifest['content']['resource_globs'] = ['resources/**/*']
        self.manifest['content']['resource_bindings'] = {'synthetic-policy': 'resources/policy.json'}
        self.settings = packs.PackSettings((self.root,), self.base / 'state.json', self.base / 'cache',
                                          self.base / 'managed', self.base / 'quarantine')
        packs.save_state(self.settings.state_file, {'enabled_packs': [self.manifest['pack_id']]})
        self.variant('A')

    def variant(self, value):
        packs.atomic_write_json(self.root / 'pack.json', self.manifest)
        packs.atomic_write_json(self.root / 'records/lighting.json', {
            'kind': 'module', 'category': 'lighting', 'records': [{
                'id': 'synthetic-acquired-light', 'label': 'Synthetic ' + value,
                'curation_status': 'vocabulary', 'category': 'lighting',
                'prompt': 'Controlled synthetic light ' + value + '.',
                'domains': ['shared'], 'tags': ['synthetic'],
                'search_terms': [{'phrase': 'synthetic light ' + value, 'facet': 'lighting',
                                  'weight': 1, 'source': 'author'}],
            }],
        })
        packs.atomic_write_json(self.root / 'resources/policy.json', {'synthetic': value})
        packs.write_lock(self.root)

    def files(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes()
                for p in self.root.rglob('*') if p.is_file()}

    def restore(self, values):
        for relative, raw in values.items():
            packs.atomic(self.root / relative, raw, replace=True)

    def label(self, catalog):
        return next(e.record['label'] for e in catalog.entries if e.record['id'] == 'synthetic-acquired-light')

    def test_changed_source_cannot_be_published_under_another_input_fingerprint(self):
        original = self.files()
        before = packs.active_snapshot(self.settings)
        fingerprint = cache._expected_fingerprint(before, builder=cache.capture_builder_inputs(cache.ROOT).fingerprint)
        derive = cache._derive_catalog
        injections = []

        def change_after_acquisition(inputs, named_fingerprint, builder):
            self.assertEqual(inputs.snapshot, before)
            self.assertEqual(named_fingerprint, fingerprint)
            self.variant('B')
            injections.append(True)
            return derive(inputs, named_fingerprint, builder)

        with patch.object(cache, '_derive_catalog', side_effect=change_after_acquisition):
            report, catalog = cache.refresh_runtime_catalog(self.settings, quiet=True)
        self.assertEqual(injections, [True])
        self.assertEqual(self.label(catalog), 'Synthetic A')
        self.assertEqual(report['fingerprint'], fingerprint)
        with closing(sqlite3.connect(report['cache_path'])) as connection:
            stored = dict(connection.execute('SELECT key, value FROM meta'))
            row = json.loads(connection.execute('SELECT record_json FROM records').fetchone()[0])
        self.assertEqual(json.loads(stored['snapshot_json']), before)
        self.assertEqual(row['label'], 'Synthetic A')
        self.assertFalse(cache.cache_status(self.settings)['fresh'])
        changed = self.files()
        self.restore(original)
        warm, restored = cache.refresh_runtime_catalog(self.settings, quiet=True)
        self.assertFalse(warm['rebuilt'])
        self.assertEqual(self.label(restored), 'Synthetic A')
        self.restore(changed)
        following, current = cache.refresh_runtime_catalog(self.settings, quiet=True)
        self.assertTrue(following['rebuilt'])
        self.assertNotEqual(following['fingerprint'], fingerprint)
        self.assertEqual(self.label(current), 'Synthetic B')

    def test_each_selected_file_is_acquired_once_for_cold_construction(self):
        opened = Counter()
        original_open = Path.open

        def record_open(path, *args, **kwargs):
            if self.root in path.parents:
                opened[path.relative_to(self.root).as_posix()] += 1
            return original_open(path, *args, **kwargs)

        expected = set(self.files())
        with patch.object(Path, 'open', record_open):
            report, catalog = cache.refresh_runtime_catalog(self.settings, quiet=True)
        self.assertTrue(report['rebuilt'])
        self.assertEqual(self.label(catalog), 'Synthetic A')
        self.assertEqual(opened, Counter({name: 1 for name in expected}))

    def test_validation_and_derivation_need_no_live_pack_files(self):
        with schema_read_scope():
            inputs = packs.acquire_runtime_inputs(self.settings)
            builder = cache.capture_builder_inputs(cache.ROOT).fingerprint
            fingerprint = cache._expected_fingerprint(inputs.snapshot, builder=builder)
            shutil.rmtree(self.root)
            built = cache._derive_catalog(inputs, fingerprint, builder)
        self.assertEqual(built.records[0][1].record['label'], 'Synthetic A')
        self.assertEqual(built.resources[0].relative_path, 'resources/policy.json')
        database = self.base / 'independent.sqlite3'
        with patch.object(packs, 'acquire_runtime_inputs', side_effect=AssertionError('writer acquired source')):
            cache._create_database(database, built)
        with closing(sqlite3.connect(database)) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM records').fetchone()[0], 1)

    def test_new_read_detects_same_size_and_mtime_content_drift(self):
        first, _ = cache.refresh_runtime_catalog(self.settings, quiet=True)
        path = self.root / 'records/lighting.json'
        info = path.stat()
        raw = path.read_bytes()
        changed = raw.replace(b'Synthetic A', b'Synthetic B')
        self.assertEqual(len(raw), len(changed))
        path.write_bytes(changed)
        os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns))
        second, catalog = cache.refresh_runtime_catalog(self.settings, quiet=True)
        self.assertNotEqual(first['fingerprint'], second['fingerprint'])
        self.assertEqual(catalog.entries, ())
        self.assertTrue(any(row['code'] == 'invalid-enabled-pack' for row in catalog.diagnostics))

    def test_acquired_values_and_runtime_catalog_are_isolated(self):
        inputs = packs.acquire_runtime_inputs(self.settings)
        pack = inputs.packs[self.manifest['pack_id']]
        self.assertIs(pack.parameter_document('./resources/policy.json'), pack.json('resources/policy.json'))
        with self.assertRaises(ValueError):
            pack.parameter_document('../policy.json')
        with self.assertRaises(TypeError):
            inputs.state['enabled_packs'].clear()
        with self.assertRaises(TypeError):
            pack.json('records/lighting.json')['records'][0]['label'] = 'Mutated'
        with self.assertRaises(TypeError):
            inputs.discovered[self.manifest['pack_id']].manifest['content']['record_globs'].append('other/*')
        _, catalog = cache.refresh_runtime_catalog(self.settings, quiet=True)
        with self.assertRaises(TypeError):
            catalog.entries[0].record['label'] = 'Mutated'
        other_root = self.base / 'other-pack'
        shutil.copytree(self.root, other_root)
        other = replace(self.settings, roots=(other_root,), cache_dir=self.base / 'other-cache')
        other_catalog = cache.load_runtime_catalog(other, quiet=True)
        self.assertNotEqual(catalog.fingerprint, other_catalog.fingerprint)
        self.assertEqual(self.label(other_catalog), 'Synthetic A')

    def test_disabled_pack_only_contributes_its_manifest(self):
        other = self.base / 'disabled-pack'
        disabled = packs.initialize_pack(other, name='Synthetic disabled source', release='2026.11.07.1')
        (other / 'records/unreadable.json').write_text('{', encoding='utf-8')
        settings = replace(self.settings, roots=(self.root, other))
        packs.save_state(settings.state_file, {'enabled_packs': [self.manifest['pack_id']],
                                              'disabled_packs': [disabled['pack_id']]})
        original_open = Path.open
        opened = []

        def reject_disabled_content(path, *args, **kwargs):
            if other in path.parents:
                opened.append(path.relative_to(other).as_posix())
                self.assertEqual(path, other / 'pack.json')
            return original_open(path, *args, **kwargs)

        with patch.object(Path, 'open', reject_disabled_content):
            catalog = cache.load_runtime_catalog(settings, quiet=True)
        self.assertEqual(opened, ['pack.json'])
        self.assertEqual(self.label(catalog), 'Synthetic A')

    def test_snapshot_uses_catalog_inputs_after_live_source_changes(self):
        catalog = cache.load_runtime_catalog(self.settings, quiet=True)
        original = self.files()
        self.variant('B')
        output = self.base / 'captured-runtime'
        runtime_snapshot.capture(catalog, self.settings, output)
        payload = json.loads((output / 'snapshot.json').read_text(encoding='utf-8'))
        self.assertEqual(payload['entries'][0]['record']['label'], 'Synthetic A')
        for relative, raw in original.items():
            self.assertEqual((output / 'packs' / self.manifest['pack_id'] / relative).read_bytes(), raw)
        self.assertEqual(self.label(cache.load_runtime_catalog(self.settings, quiet=True)), 'Synthetic B')

    def test_pack_globs_have_portable_segment_semantics(self):
        (self.root / 'resources/empty').mkdir()
        (self.root / 'resources/nested').mkdir()
        (self.root / 'resources/nested/fixture.json').write_text('{}', encoding='utf-8')
        inputs = packs.PackInput.read(self.root)
        lighting = ['records/lighting.json']
        resources = ['resources/nested/fixture.json', 'resources/policy.json']
        examples = {
            'records/*.json': lighting, 'records/**/*.json': lighting,
            '**/*.json': ['pack.json', 'pack.lock.json', *lighting, *resources],
            'resources/**/*': resources, 'resources/**': [], '**': [], 'resources/': [],
            'records/[al]*.json': lighting, 'missing/*': [], 'RECORDS/*.json': [],
        }
        for pattern, expected in examples.items():
            with self.subTest(pattern=pattern):
                actual, issues = inputs.expand([pattern])
                self.assertEqual([path.relative_to(self.root).as_posix() for path in actual], expected)
                self.assertEqual([issue.code for issue in issues],
                                 ['empty-glob'] if pattern in {'missing/*', 'RECORDS/*.json'} else [])
                self.assertEqual(packs._expand_globs(self.root, [pattern]), (actual, issues))
        for pattern in ('records/**name.json', '../*', '/records/*'):
            with self.subTest(pattern=pattern):
                actual, issues = inputs.expand([pattern])
                self.assertEqual(actual, [])
                self.assertEqual([issue.code for issue in issues], ['unsafe-glob'])

    def test_empty_directory_changes_invalidate_derived_glob_diagnostics(self):
        self.manifest['content']['resource_globs'].append('resources/empty/')
        packs.atomic_write_json(self.root / 'pack.json', self.manifest)
        packs.write_lock(self.root)
        first, before = cache.refresh_runtime_catalog(self.settings, quiet=True)

        def empty_globs(catalog):
            return [row for row in catalog.pack_reports[self.manifest['pack_id']]['warnings']
                    if row['code'] == 'empty-glob']

        self.assertEqual(len(empty_globs(before)), 1)
        (self.root / 'resources/empty').mkdir()
        second, after = cache.refresh_runtime_catalog(self.settings, quiet=True)
        self.assertTrue(second['rebuilt'])
        self.assertNotEqual(first['fingerprint'], second['fingerprint'])
        self.assertEqual(empty_globs(after), [])
        forced, checked = cache.refresh_runtime_catalog(self.settings, quiet=True, force=True)
        self.assertEqual(second['fingerprint'], forced['fingerprint'])
        self.assertEqual(after.pack_reports, checked.pack_reports)

    def binary_catalog(self):
        self.manifest['content']['resource_bindings']['synthetic-binary'] = 'resources/blob.bin'
        packs.atomic_write_json(self.root / 'pack.json', self.manifest)
        raw = b'\xff\x00synthetic acquired binary'
        (self.root / 'resources/blob.bin').write_bytes(raw)
        packs.write_lock(self.root)
        return cache.load_runtime_catalog(self.settings, quiet=True), raw

    def test_binary_capture_verifies_content_at_its_explicit_read_boundary(self):
        catalog, original = self.binary_catalog()
        output = self.base / 'captured-binary'
        runtime_snapshot.capture(catalog, self.settings, output)
        self.assertEqual((output / 'packs' / self.manifest['pack_id'] / 'resources/blob.bin').read_bytes(), original)
        (self.root / 'resources/blob.bin').write_bytes(b'\xffchanged')
        with self.assertRaises(runtime_snapshot.ProductionError) as caught:
            runtime_snapshot.capture(catalog, self.settings, self.base / 'changed-binary')
        self.assertEqual(caught.exception.diagnostic.code, 'PACK_CONTENT_MISMATCH')

    def test_binary_capture_rejects_file_and_directory_links_introduced_after_acquisition(self):
        catalog, original = self.binary_catalog()
        blob = self.root / 'resources/blob.bin'
        outside = self.base / 'outside.bin'
        outside.write_bytes(original)
        blob.unlink()
        try:
            blob.symlink_to(outside)
        except (OSError, NotImplementedError) as exc:
            self.skipTest('symbolic links are unavailable: ' + str(exc))
        with self.assertRaises(runtime_snapshot.ProductionError):
            runtime_snapshot.capture(catalog, self.settings, self.base / 'file-link')
        blob.unlink()
        blob.write_bytes(original)
        resources = self.root / 'resources'
        moved = self.base / 'moved-resources'
        resources.rename(moved)
        resources.symlink_to(moved, target_is_directory=True)
        with self.assertRaises(runtime_snapshot.ProductionError):
            runtime_snapshot.capture(catalog, self.settings, self.base / 'directory-link')

    def test_inventory_refuses_a_missing_pack_root(self):
        with self.assertRaises(packs.PackError):
            packs.inventory_rows(self.base / 'missing-pack')

    def test_explicit_state_created_at_read_is_not_replaced_by_first_use_selection(self):
        settings = replace(self.settings, initialize_all_discovered=True)
        settings.state_file.unlink()
        read = Path.read_text
        reads = []

        def create_before_read(path, *args, **kwargs):
            if path == settings.state_file:
                reads.append(path)
                packs.atomic_write_json(path, {'pack_roots': [], 'enabled_packs': [],
                                              'disabled_packs': [self.manifest['pack_id']]})
            return read(path, *args, **kwargs)

        with patch.object(Path, 'read_text', create_before_read):
            inputs = packs.acquire_runtime_inputs(settings)
        self.assertEqual(reads, [settings.state_file])
        self.assertEqual(inputs.state['enabled_packs'], [])
        self.assertEqual(inputs.selected, ())

    def test_schema_evaluation_consumes_the_bytes_named_by_the_builder_fingerprint(self):
        source = cache.capture_builder_inputs(cache.ROOT)
        relative = 'schemas/pack-record-file.schema.json'
        changed = json.loads(source.read_bytes(relative))
        changed['not'] = {}
        strict = BuilderInputs(source.root, tuple(
            FileInput(item.path, json.dumps(changed).encode('utf-8')) if item.path == relative else item
            for item in source.files))
        with patch.object(cache, 'capture_builder_inputs', return_value=strict):
            rejected, catalog = cache.refresh_runtime_catalog(self.settings, quiet=True)
        self.assertEqual(catalog.entries, ())
        self.assertTrue(any(row['code'] == 'invalid-enabled-pack' for row in catalog.diagnostics))
        accepted, catalog = cache.refresh_runtime_catalog(self.settings, quiet=True)
        self.assertNotEqual(rejected['fingerprint'], accepted['fingerprint'])
        self.assertEqual(self.label(catalog), 'Synthetic A')


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
