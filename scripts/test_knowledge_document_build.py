"""Verify knowledge presentation and declaration ownership."""
from __future__ import annotations

from contextlib import redirect_stdout
import errno
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import execution_contract as c
import knowledge_document_build as build
from knowledge_document_build import generated_documents, record_ids, render_document, routed_document_ids
from knowledge_documents import DocumentReader, decode_document, markdown_path, record_path


class RenderDocumentTests(unittest.TestCase):
    def test_rendering_preserves_every_byte_in_declared_section_order(self):
        first = ('Opening.\r\n\r\n'
                 'Caf\u00e9 details\r\n-------------\r\n'
                 '````markdown\r\n<!-- section: example-text -->\r\n'
                 '# A fenced heading\r\n```\r\n<!-- section: INVALID ID -->\r\n````\r\n')
        second = ('## Ordinary nested heading\r\n'
                  '[Relative link](../source.md#topic)\r\n'
                  '| Field | Value |\r\n| --- | --- |\r\n| Complete | Body |\r\n')
        value = {'sections': [{'id': 'opening', 'body': first}, {'id': 'detail', 'body': second}]}
        acquired = decode_document('references/details', c.encoded(value))
        self.assertEqual(render_document(acquired), (first + second).encode('utf-8'))
        self.assertEqual([section.section_id for section in acquired.sections], ['opening', 'detail'])
        self.assertEqual(acquired.section('detail').raw, second.encode('utf-8'))
        value['sections'].reverse()
        reordered = decode_document('references/details', c.encoded(value))
        self.assertEqual(render_document(reordered), (second + first).encode('utf-8'))
        self.assertEqual(reordered.section('detail'), acquired.section('detail'))

    def test_native_front_matter_is_complete_ordinary_section_content(self):
        from narrative_index import parse_front_matter
        for ending in ('\n', '\r\n'):
            body = ending.join(('---', 'kind: design', 'references: []', '---', '',
                                 '# Current form', '', '## Internal topic', 'Complete body.', ''))
            with self.subTest(ending=ending):
                acquired = decode_document('templates/form', c.encoded({
                    'sections': [{'id': 'whole-form', 'body': body}]}))
                rendered = render_document(acquired)
                self.assertEqual(rendered, body.encode('utf-8'))
                self.assertEqual(parse_front_matter(rendered.decode('utf-8')), parse_front_matter(body))
                self.assertEqual(acquired.section('whole-form').raw, rendered)

    def test_records_work_without_a_markdown_presentation_or_heading_parser(self):
        with tempfile.TemporaryDirectory(prefix='knowledge-source-only-') as temporary:
            root = Path(temporary)
            identifier = 'references/current'
            path = root / record_path(identifier)
            path.parent.mkdir(parents=True)
            body = 'Unheaded instructions.\n\n### A display heading\nComplete remainder.\n'
            path.write_bytes(c.encoded({'sections': [{'id': 'actual-unit', 'body': body}]}))
            self.assertFalse((root / markdown_path(identifier)).exists())
            acquired = DocumentReader(lambda relative: (root / relative).read_bytes()).acquire(identifier)
            self.assertEqual(render_document(acquired), body.encode('utf-8'))
            presentation = root / markdown_path(identifier)
            presentation.parent.mkdir(parents=True)
            presentation.write_bytes(b'Different display text.\n')
            later = DocumentReader(lambda relative: (root / relative).read_bytes()).acquire(identifier)
            self.assertEqual(later.sections, acquired.sections)
            self.assertEqual(later.record, acquired.record)


class GeneratedDocumentCheckTests(unittest.TestCase):
    def test_rebuild_uses_sources_before_public_contract_outputs_exist(self):
        import protocol_contract
        import rebuild_metadata
        from integration_contract import validate_capabilities

        capability = {'artifact_type': 'integration-capability-manifest',
            'interfaces': {'produces': [{'profile': 'synthetic-profile',
                'artifact_types': ['synthetic-artifact'], 'required_features': ['complete-body'],
                'supported_features': ['complete-body'],
                'unknown_optional_feature_policy': 'preserve',
                'unknown_required_feature_policy': 'reject', 'profile_sha256': '0' * 64}],
                'consumes': []}, 'manifest_sha256': '0' * 64}
        with tempfile.TemporaryDirectory(prefix='knowledge-source-build-') as temporary:
            root = Path(temporary)
            capability_path = root / 'config/integration-capabilities.json'
            capability_path.parent.mkdir(parents=True)
            capability_path.write_bytes(c.encoded(capability))
            identifier = 'protocols/semantics'
            canonical = root / record_path(identifier)
            canonical.parent.mkdir(parents=True)
            body = '# Synthetic contract semantics\n\nComplete source body.\n'
            canonical.write_bytes(c.encoded({'sections': [{'id': 'whole', 'body': body}]}))
            with patch.object(rebuild_metadata, 'ROOT', root), \
                 patch.object(rebuild_metadata, '_CAPTURED', None), \
                 patch.object(rebuild_metadata, '_REMOVED', set()), \
                 patch.object(protocol_contract, 'registry', side_effect=AssertionError(
                     'Generation required an already sealed installation')):
                self.assertFalse((root / markdown_path(identifier)).exists())
                rebuilt = rebuild_metadata.rebuild_integration_capabilities()
                rebuild_metadata.rebuild_knowledge_documents()
            self.assertTrue(validate_capabilities(rebuilt)['ok'])
            self.assertEqual(c.load(capability_path), rebuilt)
            self.assertEqual((root / markdown_path(identifier)).read_bytes(), body.encode('utf-8'))
            self.assertEqual(rebuilt['interfaces']['produces'][0]['required_features'],
                             capability['interfaces']['produces'][0]['required_features'])

    def test_check_preserves_canonical_newlines_and_rejects_only_newline_changes(self):
        import catalog_api
        import rebuild_metadata

        metadata = SimpleNamespace(release_pack_dirs=(), default_pack_ids=(),
                                   release_include=('knowledge', 'references'), release_exclude_names=())
        for ending, changed_ending in (('\n', '\r\n'), ('\r\n', '\n')):
            with self.subTest(ending=ending), tempfile.TemporaryDirectory(prefix='knowledge-check-newlines-') as temporary:
                # Keep the patched root equal to resolved paths of generated files.
                root = Path(temporary).resolve()
                identifier = 'references/current'
                canonical = root / record_path(identifier)
                canonical.parent.mkdir(parents=True)
                body = ending.join(('# Complete form', '', 'Caf\u00e9 detail.',
                                    '[Relative reference](detail.md)', ''))
                canonical.write_bytes(c.encoded({'sections': [{'id': 'whole', 'body': body}]}))
                with patch.object(rebuild_metadata, 'ROOT', root), \
                     patch.object(rebuild_metadata, '_CAPTURED', None), \
                     patch.object(rebuild_metadata, '_REMOVED', set()), \
                     patch.object(rebuild_metadata, 'load_package_metadata', return_value=metadata), \
                     patch.object(catalog_api, 'configure_pack_runtime'), \
                     patch.object(catalog_api, 'load_entries', return_value=[]), \
                     patch.object(catalog_api, 'load_pack_catalog', return_value=SimpleNamespace(resources={})), \
                     patch.object(rebuild_metadata, 'build_catalog_document', return_value='# Fixture catalog\n'), \
                     patch.object(rebuild_metadata, 'rebuild_host_manifests'), \
                     patch.object(rebuild_metadata, 'rebuild_repository_guides'), \
                     patch.object(rebuild_metadata, 'rebuild_integration_capabilities'), \
                     patch.object(rebuild_metadata, 'rebuild_implementation_index'):
                    with redirect_stdout(io.StringIO()):
                        self.assertEqual(rebuild_metadata.main([]), 0)
                    rendered = root / markdown_path(identifier)
                    self.assertEqual(rendered.read_bytes(), body.encode('utf-8'))
                    before = {path: path.read_bytes() for path in root.rglob('*') if path.is_file()}
                    output = io.StringIO()
                    with redirect_stdout(output):
                        self.assertEqual(rebuild_metadata.main(['--check']), 0)
                    self.assertEqual(json.loads(output.getvalue())['stale'], [])
                    self.assertEqual({path: path.read_bytes() for path in before}, before)

                    changed = body.replace(ending, changed_ending).encode('utf-8')
                    self.assertNotEqual(changed, before[rendered])
                    rendered.write_bytes(changed)
                    output = io.StringIO()
                    with redirect_stdout(output):
                        self.assertEqual(rebuild_metadata.main(['--check']), 1)
                    self.assertEqual(json.loads(output.getvalue())['stale'], [markdown_path(identifier)])
                    self.assertEqual(rendered.read_bytes(), changed)
                    self.assertEqual({path: path.read_bytes() for path in before if path != rendered},
                                     {path: raw for path, raw in before.items() if path != rendered})


class SourceOnlyBuildTests(unittest.TestCase):
    def command(self, arguments):
        output = io.StringIO()
        with redirect_stdout(output):
            status = build.main(arguments)
        return status, json.loads(output.getvalue())

    def test_source_only_build_and_check_preserve_complete_bytes_without_an_installed_contract(self):
        for ending, changed_ending in (('\n', '\r\n'), ('\r\n', '\n')):
            with self.subTest(ending=ending), tempfile.TemporaryDirectory(prefix='knowledge-source-build-') as temporary:
                root = Path(temporary)
                body = ending.join(('# Current source', '', 'Caf\u00e9 detail.',
                                    '[Relative reference](detail.md)', ''))
                forms = {
                    'references/current': {'sections': [
                        {'id': 'opening', 'body': body},
                        {'id': 'following', 'body': 'Complete following body.' + ending}]},
                    'templates/form': {'sections': [
                        {'id': 'whole', 'body': ending.join(('---', 'kind: design', '---', '# Full form', ''))}]},
                }
                for identifier, value in forms.items():
                    source = root / record_path(identifier)
                    source.parent.mkdir(parents=True, exist_ok=True)
                    source.write_bytes(c.encoded(value))
                originals = {path: path.read_bytes() for path in root.rglob('*') if path.is_file()}
                expected = {markdown_path(identifier): ''.join(row['body'] for row in value['sections']).encode('utf-8')
                            for identifier, value in forms.items()}
                with patch.object(build, 'ROOT', root):
                    status, report = self.command(['--check'])
                    self.assertEqual((status, report['stale']), (1, sorted(expected)))
                    self.assertEqual({path: path.read_bytes() for path in root.rglob('*') if path.is_file()}, originals)
                    self.assertEqual(self.command([])[0], 0)
                    self.assertEqual({relative: (root / relative).read_bytes() for relative in expected}, expected)
                    self.assertEqual(self.command(['--check'])[0], 0)
                    target = root / markdown_path('references/current')
                    changed = expected['references/current.md'].decode('utf-8').replace(ending, changed_ending).encode('utf-8')
                    target.write_bytes(changed)
                    status, report = self.command(['--check'])
                    self.assertEqual((status, report['stale']), (1, ['references/current.md']))
                    self.assertEqual(target.read_bytes(), changed)
                    self.assertEqual(self.command([])[0], 0)
                    self.assertEqual(target.read_bytes(), expected['references/current.md'])
                    self.assertEqual({path: path.read_bytes() for path in originals}, originals)
                    self.assertFalse((root / 'protocols/contract-manifest.json').exists())
                    self.assertFalse((root / 'config').exists())

    def test_candidate_only_removes_presentations_owned_by_the_previous_manifest(self):
        with tempfile.TemporaryDirectory(prefix='knowledge-owned-removal-') as temporary:
            root = Path(temporary)
            source = root / record_path('references/current')
            source.parent.mkdir(parents=True)
            source.write_bytes(c.encoded({'sections': [{'id': 'complete', 'body': 'Current body.\n'}]}))
            for name in ('current', 'removed', 'authored', 'unowned'):
                target = root / f'references/{name}.md'
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((name + ' original.\n').encode('utf-8'))
            inventory = root / 'MANIFEST.json'
            inventory.write_bytes(c.encoded({'files': [
                {'path': record_path('references/current')},
                {'path': record_path('references/removed')},
                {'path': record_path('references/already-absent')},
                {'path': 'references/authored.md'}]}))
            before = {path: path.read_bytes() for path in root.rglob('*') if path.is_file()}
            outputs, obsolete = generated_documents(root)
            self.assertEqual(outputs, {'references/current.md': b'Current body.\n'})
            self.assertEqual(obsolete, ('references/removed.md',))
            self.assertEqual({path: path.read_bytes() for path in before}, before)
            with patch.object(build, 'ROOT', root):
                status, report = self.command(['--check'])
                self.assertEqual((status, report['stale']), (1, ['references/current.md', 'references/removed.md']))
                self.assertEqual({path: path.read_bytes() for path in before}, before)
                status, report = self.command([])
                self.assertEqual((status, report['removed']), (0, ['references/removed.md']))
            self.assertFalse((root / 'references/removed.md').exists())
            for path in (source, inventory, root / 'references/authored.md', root / 'references/unowned.md'):
                self.assertEqual(path.read_bytes(), before[path])

    def test_all_canonical_records_are_acquired_before_any_output_is_changed(self):
        with tempfile.TemporaryDirectory(prefix='knowledge-build-acquisition-') as temporary:
            root = Path(temporary)
            source = root / record_path('references/a-current')
            source.parent.mkdir(parents=True)
            source.write_bytes(c.encoded({'sections': [{'id': 'whole', 'body': 'New body.\n'}]}))
            invalid = root / record_path('references/z-invalid')
            invalid.write_bytes(b'{"sections":[{"id":"whole","body":"First","body":"Duplicate"}]}')
            target = root / 'references/a-current.md'
            target.parent.mkdir(parents=True)
            target.write_bytes(b'Previous generated body.\n')
            before = {path: path.read_bytes() for path in root.rglob('*') if path.is_file()}
            with patch.object(build, 'ROOT', root), self.assertRaises(ValueError):
                self.command([])
            self.assertEqual({path: path.read_bytes() for path in root.rglob('*') if path.is_file()}, before)

    def test_same_byte_render_requires_the_directory_durability_barrier_on_every_retry(self):
        with tempfile.TemporaryDirectory(prefix='knowledge-build-durability-') as temporary:
            root = Path(temporary)
            body = b'Complete body.\n'
            source = root / record_path('references/current')
            source.parent.mkdir(parents=True)
            source.write_bytes(c.encoded({'sections': [{'id': 'whole', 'body': body.decode('utf-8')}]}))
            target = root / 'references/current.md'
            target.parent.mkdir(parents=True)
            target.write_bytes(body)
            failure = OSError(errno.EIO, 'Injected source-render directory fsync failure')
            with patch.object(build, 'ROOT', root):
                with patch.object(c, 'fsync_dir', side_effect=failure) as barrier:
                    for _ in range(2):
                        with self.assertRaisesRegex(OSError, 'source-render directory fsync failure'):
                            self.command([])
                        self.assertEqual(target.read_bytes(), body)
                    self.assertEqual(barrier.call_count, 2)
                with patch.object(c, 'fsync_dir', wraps=c.fsync_dir) as barrier:
                    self.assertEqual(self.command([])[0], 0)
                barrier.assert_called_once_with(target.parent)


class RecordEnumerationTests(unittest.TestCase):
    def test_records_have_sorted_unique_ids_independent_of_presentations(self):
        with tempfile.TemporaryDirectory(prefix='knowledge-enumeration-') as temporary:
            root = Path(temporary)
            self.assertEqual(record_ids(root), [])
            expected = ['protocols/meaning', 'references/runtime/first', 'templates/form']
            for identifier in reversed(expected):
                path = root / record_path(identifier)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(c.encoded({'sections': [{'id': 'whole', 'body': 'Complete body.\n'}]}))
            (root / 'unrelated.json').write_bytes(b'{}')
            self.assertEqual(record_ids(root), expected)
            original = Path.cwd()
            try:
                os.chdir(root)
                self.assertEqual(record_ids(Path('.')), expected)
            finally:
                os.chdir(original)

    def test_malformed_and_private_record_locations_are_refused(self):
        for name in ('source.md.json', 'Upper.json', 'credentials.json'):
            with self.subTest(name=name), tempfile.TemporaryDirectory(prefix='knowledge-invalid-location-') as temporary:
                root = Path(temporary)
                directory = root / 'knowledge'
                directory.mkdir()
                (directory / name).write_bytes(b'{}')
                with self.assertRaises(ValueError):
                    record_ids(root)

    def test_enumeration_refuses_symbolic_links_instead_of_following_them(self):
        with tempfile.TemporaryDirectory(prefix='knowledge-linked-record-') as temporary:
            root = Path(temporary)
            directory = root / 'knowledge'
            directory.mkdir()
            outside = root / 'outside.json'
            outside.write_bytes(b'{}')
            alias = directory / 'aliased.json'
            try:
                alias.symlink_to(outside)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(str(exc))
            with self.assertRaisesRegex(ValueError, 'symbolic link'):
                record_ids(root)


class RoutedDocumentTests(unittest.TestCase):
    def test_only_declared_read_owners_contribute_sorted_document_ids(self):
        manifest = {
            'routes': {'generation': {'reads': ['references/shared', 'references/route'],
                                      'example': {'reads': ['references/ignored-example']}}},
            'features': {'model': {'reads': ['references/shared', 'references/model']}},
            'operation_contexts': {'prepare': {'reads': ['references/operation'],
                                               'executions': {'external': ['references/external']}}},
            'reading_scopes': {'authoring': {'documents': {'references/scoped': [
                {'sections': ['fixed'], 'reason': 'references/ignored-reason'}]},
                'deferred_documents': {'references/deferred': {'until': 'rendition'}}}},
            'regression': ['references/ignored-regression'],
            'operations': {'example': {'reads': ['references/ignored-operation']}},
        }
        self.assertEqual(routed_document_ids(manifest), [
            'references/deferred', 'references/external', 'references/model',
            'references/operation', 'references/route', 'references/scoped', 'references/shared'])

    def test_malformed_declarations_fail_at_their_owner(self):
        for manifest in (
            {'routes': {'generation': {'reads': 'references/source'}}},
            {'operation_contexts': {'prepare': {'executions': {'external': ['../outside']}}}},
            {'reading_scopes': {'authoring': {'documents': ['references/source']}}},
            {'features': {'private': {'reads': ['credentials']}}},
            {'routes': []},
        ):
            with self.subTest(manifest=manifest), self.assertRaises(ValueError):
                routed_document_ids(manifest)


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
