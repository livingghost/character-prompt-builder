#!/usr/bin/env python3
"""Offline gallery projection tests using synthetic, source-owned recorded artwork."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urljoin, urlparse
from urllib.request import url2pathname

import execution_contract as c
import studio_gallery as gallery


def projected(entries: list[dict], at: str = '2026-01-01T12:00:00Z') -> dict:
    payload = {'studio_id': 'synthetic-gallery', 'title': 'Synthetic artwork',
               'order': 'recorded_at_desc', 'entries': copy.deepcopy(entries), 'diagnostics': []}
    return {**payload, 'revision': c.content_id(payload), 'generated_at': at}


def cards_from(path: Path) -> dict:
    text = path.read_text(encoding='utf-8')
    return json.loads(text.removeprefix('CPBGallery.start(').removesuffix(');\n'))


def search_document(path: Path) -> list:
    text = path.read_text(encoding='utf-8')
    return json.loads('[' + text.removeprefix('CPBGallery.searchDocument(').removesuffix(');\n') + ']')


def snapshot(paths) -> dict:
    return {str(path): (path.read_bytes(), path.stat().st_mtime_ns) for path in paths if path.is_file()}


class GalleryProjectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'studio'
        self.root.mkdir()
        self.html = self.root / 'gallery.html'
        self.assets = gallery.asset_dir(self.html)
        for relative, raw in {
            'images/example result.svg': b'<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"></svg>',
            'records/request.json': b'{"text":"Exact synthetic request"}',
            'records/response.json': b'{"result":"images/example result.svg"}',
            'records/package.json': b'{"kind":"synthetic-package"}',
            'records/provenance.json': b'{"kind":"synthetic-provenance"}',
        }.items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)

    def entry(self, number: int, **changes) -> dict:
        return {
            'entry_id': f'subject/it-{number:04}', 'character': 'subject', 'iteration_id': f'it-{number:04}',
            'kind': 'generation', 'slot': 'canon.primary', 'status': 'candidate',
            'at': '2026-01-01T12:00:00Z', 'availability': 'present',
            'evaluation': 'not_reviewed', 'disposition': 'candidate', 'seed': number,
            'model_record': 'synthetic-model', 'service': {'model_identifier': 'local-synthetic-model'},
            'request_recorded': True, 'prompt_fields_known': True,
            'prompt': 'A recorded synthetic image.', 'negative_prompt': 'Synthetic excluded texture.',
            'settings': {'width': 100, 'height': 100}, 'media': {},
            'result': 'images/example result.svg', 'result_sha256': 'a' * 64,
            'request': 'records/request.json', 'response': 'records/response.json',
            'package': 'records/package.json', 'provenance': 'records/provenance.json',
            'diagnostics': [], 'selection_diagnostics': [], 'acceptances': [],
            **changes,
        }

    def all_projection_files(self):
        return [self.html, self.html.with_suffix('.json'), *self.assets.rglob('*')]

    def test_landing_html_and_eager_index_do_not_embed_complete_details(self):
        gallery.publish(self.root, projected([self.entry(1)]))
        small_html_size = self.html.stat().st_size
        large_value = 'saved-media-value-' * 8192
        entries = [self.entry(number, prompt='Complete synthetic detail ' * 500)
                   for number in range(205, 0, -1)]
        entries[-1]['settings']['payload'] = large_value
        entries[-1]['note'] = 'A searchable note on the oldest recorded entry.'
        gallery.publish(self.root, projected(entries))
        page = self.html.read_text(encoding='utf-8')
        self.assertEqual(self.html.stat().st_size, small_html_size)
        self.assertNotIn('<section', page)
        self.assertNotIn('Complete synthetic detail', page)
        self.assertNotIn(large_value, (self.assets / 'index.js').read_text(encoding='utf-8'))
        self.assertNotIn('A searchable note', (self.assets / 'index.js').read_text(encoding='utf-8'))
        compact = cards_from(self.assets / 'index.js')['cards']
        self.assertEqual([card['entry_id'] for card in compact], [entry['entry_id'] for entry in entries])
        held = c.load(self.html.with_suffix('.json'))
        self.assertEqual(held['entries'], entries)
        for entry, card in zip(entries, compact):
            detail = gallery.detail_file(self.html, entry['entry_id'])
            key, revision, text = search_document(detail.with_suffix('.search.js'))
            self.assertEqual((key, revision), (card['key'], card['revision']))
            self.assertIn(entry['prompt'], text)
            self.assertTrue(detail.is_file())
        self.assertIn(large_value, search_document(gallery.detail_file(self.html, entries[-1]['entry_id']).with_suffix('.search.js'))[2])

    def test_detail_preserves_actual_text_settings_history_and_raw_evidence_links(self):
        entry = self.entry(1, prompt='A heron beside a sign marked <keep & record>.',
                           note='A synthetic observation: caf\u00e9 sign.',
                           settings={'steps': 20, 'extra': {'strength': 0.5}},
                           media={'reference': ['media-reference-1']},
                           acceptances=[{'at': '2026-01-02T12:00:00Z', 'supersedes': 'it-0000'}],
                           reason='The selected image meets the authored intention.', decision_kind='selection')
        gallery.publish(self.root, projected([entry]))
        detail = gallery.detail_file(self.html, entry['entry_id'])
        page = detail.read_text(encoding='utf-8')
        self.assertEqual(page.count('A heron beside a sign marked &lt;keep &amp; record&gt;.'), 1)
        self.assertIn('in place of it-0000', page)
        self.assertIn('selection reason: The selected image', page)
        self.assertIn('media-reference-1', page)
        self.assertIn('loading="lazy"', page)
        for relative in ('request.json', 'response.json', 'package.json', 'provenance.json'):
            self.assertIn('href="./records/' + relative + '"', page)
        self.assertIn('href="gallery.json"', page)
        self.assertIn('src="./images/example%20result.svg"', page)
        searchable = search_document(detail.with_suffix('.search.js'))[2]
        for text in (entry['prompt'], entry['negative_prompt'], entry['note'], 'strength', 'media-reference-1', 'in place of it-0000'):
            self.assertIn(text, searchable)
        self.assertEqual(c.load(self.html.with_suffix('.json'))['entries'][0], entry)

    def test_unchanged_refresh_reuses_bytes_timestamps_and_entry_rendering(self):
        index = projected([self.entry(1), self.entry(2)])
        gallery.publish(self.root, index)
        before = snapshot(self.all_projection_files())
        with patch.object(gallery, 'render_entry', side_effect=AssertionError('unchanged detail was rendered')), \
                patch.object(c, 'atomic', side_effect=AssertionError('unchanged projection was rewritten')):
            gallery.publish(self.root, {**index, 'generated_at': '2026-02-01T12:00:00Z'})
        self.assertEqual(snapshot(self.all_projection_files()), before)
        self.assertEqual(c.load(self.html.with_suffix('.json'))['generated_at'], index['generated_at'])

    def test_status_updates_replace_only_the_changed_entry_and_do_not_accumulate_versions(self):
        entries = [self.entry(1), self.entry(2), self.entry(3)]
        gallery.publish(self.root, projected(entries))
        unchanged = [gallery.detail_file(self.html, entry['entry_id']) for entry in entries[1:]]
        unchanged += [path.with_suffix('.search.js') for path in unchanged]
        before = snapshot(unchanged)
        original_files = {path.relative_to(self.assets).as_posix() for path in self.assets.rglob('*') if path.is_file()}
        evidence = snapshot([*self.root.joinpath('records').iterdir(), *self.root.joinpath('images').iterdir()])
        for number in range(6):
            entries[0].update(status='accepted', disposition='selected',
                              reason=f'Synthetic selection decision {number}', decision_kind='selection')
            gallery.publish(self.root, projected(entries))
        self.assertEqual(snapshot(unchanged), before)
        self.assertEqual({path.relative_to(self.assets).as_posix() for path in self.assets.rglob('*') if path.is_file()}, original_files)
        changed = gallery.detail_file(self.html, entries[0]['entry_id']).read_text(encoding='utf-8')
        self.assertIn('Synthetic selection decision 5', changed)
        self.assertNotIn('Synthetic selection decision 0', changed)
        cards = cards_from(self.assets / 'index.js')['cards']
        self.assertEqual((cards[0]['status'], cards[0]['disposition']), ('accepted', 'selected'))
        self.assertEqual(snapshot(Path(path) for path in evidence), evidence)

    def test_explicit_snapshot_has_rebased_links_and_independent_entry_assets(self):
        index = projected([self.entry(1)])
        gallery.publish(self.root, index)
        exported = self.root / 'views' / 'browser' / 'saved.html'
        gallery.publish(self.root, index, exported)
        before = snapshot([exported, exported.with_suffix('.json'), *gallery.asset_dir(exported).rglob('*')])
        page = exported.read_text(encoding='utf-8')
        self.assertIn('<base href="../../">', page)
        card = cards_from(gallery.asset_dir(exported) / 'index.js')['cards'][0]
        base = urljoin(exported.as_uri(), '../../')
        resolved = Path(url2pathname(urlparse(urljoin(base, card['detail'])).path))
        self.assertEqual(resolved, gallery.detail_file(exported, 'subject/it-0001'))
        detail = resolved.read_text(encoding='utf-8')
        self.assertIn('<base href="../../../../">', detail)
        changed = projected([self.entry(1, status='accepted')])
        gallery.publish(self.root, changed)
        self.assertEqual(snapshot(Path(path) for path in before), before)
        self.assertEqual(c.load(exported.with_suffix('.json'))['entries'][0]['status'], 'candidate')

    def test_missing_search_asset_is_detected_and_repaired_from_recorded_content(self):
        index = projected([self.entry(1), self.entry(2)])
        gallery.publish(self.root, index)
        with patch.object(gallery, 'build_index', return_value=index):
            self.assertIsNone(gallery.stale(self.root))
            missing = gallery.detail_file(self.html, 'subject/it-0002').with_suffix('.search.js')
            missing.unlink()
            self.assertIn('missing or changed', gallery.stale(self.root))
            gallery.publish(self.root, index)
            self.assertIsNone(gallery.stale(self.root))
            self.assertIn('A recorded synthetic image.', search_document(missing)[2])

    def test_malformed_generated_manifest_is_reported_and_repaired(self):
        index = projected([self.entry(1)])
        gallery.publish(self.root, index)
        with patch.object(gallery, 'build_index', return_value=index):
            (self.assets / 'manifest.json').write_text('[]', encoding='utf-8')
            self.assertIn('manifest is not an object', gallery.stale(self.root))
            gallery.publish(self.root, index)
            self.assertIsNone(gallery.stale(self.root))

    def test_projection_ownership_preserves_unrelated_files(self):
        self.assets.mkdir()
        unrelated = self.assets / 'authored.txt'
        unrelated.write_text('Authored outside the gallery.', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'no generated ownership record'):
            gallery.publish(self.root, projected([self.entry(1)]))
        self.assertEqual(unrelated.read_text(encoding='utf-8'), 'Authored outside the gallery.')
        other = self.root / 'view.html'
        gallery.publish(self.root, projected([self.entry(1)]), other)
        extra = gallery.asset_dir(other) / 'authored.txt'
        extra.write_text('Keep this independent note.', encoding='utf-8')
        gallery.publish(self.root, projected([self.entry(1, status='accepted')]), other)
        self.assertEqual(extra.read_text(encoding='utf-8'), 'Keep this independent note.')


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
