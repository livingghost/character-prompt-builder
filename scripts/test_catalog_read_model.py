"""The browser projection consumes the catalog's acquired pack inputs."""
from __future__ import annotations

from collections import Counter
from contextlib import redirect_stderr
from dataclasses import replace
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import browser_catalog
import catalog_html as html
from catalog_html_smoke_test import PACK_ID, REPLACEMENT_PACK_ID, fixture, replacement_fixture
import pack_cache
import pack_cli
import pack_manager as packs


class CatalogReadModelTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='cpb-catalog-read-')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.root = self.base / 'pack'
        fixture(self.root)
        manifest = packs.load_json(self.root / 'pack.json')
        manifest['content']['resource_bindings']['catalog-thumbnails'] = 'resources/catalog-thumbnails.json'
        packs.atomic_write_json(self.root / 'pack.json', manifest)
        self.thumbnail('resources/thumbnail.png')
        self.settings = packs.PackSettings((self.root,), self.base / 'state.json', self.base / 'cache',
                                          self.base / 'managed', self.base / 'quarantine')
        packs.save_state(self.settings.state_file, {'enabled_packs': [PACK_ID]})

    def thumbnail(self, relative):
        path = self.root / relative
        packs.atomic_write_json(self.root / 'resources/catalog-thumbnails.json', {
            'format': 'character-prompt-builder-catalog-thumbnails',
            'assets': {'fixture-visual-evidence': {
                'path': relative, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            }},
        })

    def catalog(self):
        return pack_cache.load_runtime_catalog(self.settings, quiet=True)

    def test_ready_acquires_selected_text_once_for_runtime_and_browser(self):
        texts = {path.relative_to(self.root).as_posix() for path in self.root.rglob('*')
                 if path.is_file() and path.suffix in {'.json', '.svg'}}
        opened = Counter()
        original_open = Path.open

        def record_open(path, *args, **kwargs):
            if self.root in path.parents:
                opened[path.relative_to(self.root).as_posix()] += 1
            return original_open(path, *args, **kwargs)

        with patch.object(Path, 'open', record_open), redirect_stderr(io.StringIO()), \
                patch.object(html, 'validate_pack_input', side_effect=AssertionError('display revalidated pack')):
            ok, lines = pack_cli.ready(self.settings, set())
        self.assertTrue(ok, lines)
        self.assertTrue(any(line.startswith('catalog: ') for line in lines), lines)
        self.assertEqual({name: opened[name] for name in texts}, {name: 1 for name in texts})
        # One input acquisition and one live media check for the output phase.
        self.assertEqual(opened['resources/thumbnail.png'], 2)
        output = browser_catalog.output_directory(self.settings)
        self.assertIn('Fixture canonical scene', (output / 'data/catalog-index.js').read_text(encoding='utf-8'))

    def test_warm_browser_view_uses_owned_records_warnings_and_thumbnail_metadata(self):
        self.catalog()
        report, runtime = pack_cache.refresh_runtime_catalog(self.settings, quiet=True)
        self.assertFalse(report['rebuilt'])
        for relative in ('pack.json', 'records/scene.json', 'records/assets.json',
                         'resources/catalog-thumbnails.json'):
            (self.root / relative).unlink()
        original_open = Path.open

        def refuse_source_text(path, *args, **kwargs):
            if self.root in path.parents and path.suffix == '.json':
                raise AssertionError('display reopened acquired source text: ' + str(path))
            return original_open(path, *args, **kwargs)

        with patch.object(Path, 'open', refuse_source_text), \
                patch.object(html, 'validate_pack_input', side_effect=AssertionError('display revalidated pack')):
            views = html.load_runtime_views(runtime)
            result = html.write_catalog_directory(views, self.base / 'owned-browser')
        self.assertEqual(result['record_count'], len(runtime.entries))
        self.assertEqual([row.to_dict() for row in views[0].validation.issues],
                         runtime.pack_reports[PACK_ID]['warnings'])
        self.assertTrue(any(row.code == 'development-pack' for row in views[0].validation.issues))
        page = self.base / 'owned-browser/packs' / (PACK_ID + '.html')
        self.assertIn('development-pack', page.read_text(encoding='utf-8'))

    def test_runtime_views_keep_resolved_replacements_and_declared_resources(self):
        other = self.base / 'replacement'
        replacement_fixture(other)
        self.settings = replace(self.settings, roots=(self.root, other))
        packs.save_state(self.settings.state_file, {'enabled_packs': [PACK_ID, REPLACEMENT_PACK_ID]})
        runtime = self.catalog()
        with patch.object(html, 'validate_pack_input', side_effect=AssertionError('display revalidated pack')):
            views = html.load_runtime_views(runtime)
        actual = [(view.pack_id, record.record['id']) for view in views for record in view.validation.records]
        expected = [(entry.source_pack, entry.record['id']) for entry in runtime.entries]
        self.assertCountEqual(actual, expected)
        self.assertNotIn((PACK_ID, 'fixture-canonical-scene'), actual)
        self.assertIn((REPLACEMENT_PACK_ID, 'fixture-canonical-scene'), actual)
        base = next(view for view in views if view.pack_id == PACK_ID)
        self.assertIn('resources/fixture.svg', base.validation.resource_files)
        self.assertIs(base.inputs, runtime.inputs.packs[PACK_ID])
        result = html.write_catalog_directory(views, self.base / 'resolved-browser')
        self.assertEqual(result['canonical_asset_link_count'], 3)

    def test_new_owner_uses_changed_thumbnail_metadata_at_the_same_root(self):
        before = html.load_runtime_views(self.catalog())[0]
        first = html._catalog_thumbnail_resources(before)['fixture-visual-evidence']
        self.thumbnail('resources/fixture thumb \ud14c\uc2a4\ud2b8.svg')
        after = html.load_runtime_views(self.catalog())[0]
        second = html._catalog_thumbnail_resources(after)['fixture-visual-evidence']
        self.assertEqual(first.relative_path, 'resources/thumbnail.png')
        self.assertEqual(second.relative_path, 'resources/fixture thumb \ud14c\uc2a4\ud2b8.svg')
        self.assertEqual(html._catalog_thumbnail_resources(before)['fixture-visual-evidence'], first)

    def test_later_output_rechecks_binary_thumbnail_bytes(self):
        views = html.load_runtime_views(self.catalog())
        html.write_catalog_directory(views, self.base / 'first-output')
        (self.root / 'resources/thumbnail.png').write_bytes(b'changed synthetic image')
        with self.assertRaises(packs.PackError):
            html.write_catalog_directory(views, self.base / 'later-output')
        self.assertFalse((self.base / 'later-output').exists())

    def test_standalone_portable_copy_uses_owned_text(self):
        views = html.load_pack_directories([self.root])
        path = self.root / 'resources/authority.json'
        before = path.read_bytes()
        packs.atomic_write_json(path, {'authority': 'changed after inspection'})
        original_open = Path.open

        def refuse_source_text(selected, *args, **kwargs):
            if selected == path:
                raise AssertionError('portable copy reopened acquired text')
            return original_open(selected, *args, **kwargs)

        with patch.object(Path, 'open', refuse_source_text):
            html.write_catalog_directory(views, self.base / 'portable', copy_assets=True)
        copied = self.base / 'portable/media' / PACK_ID / 'resources/authority.json'
        self.assertEqual(copied.read_bytes(), before)

    def test_fixed_catalog_without_acquired_inputs_does_not_reopen_live_sources(self):
        fixed = replace(self.catalog(), inputs=None)
        with patch.object(packs.PackInput, 'read', side_effect=AssertionError('hidden source fallback')):
            with self.assertRaisesRegex(packs.PackError, 'acquired live pack inputs'):
                html.load_runtime_views(fixed)


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
