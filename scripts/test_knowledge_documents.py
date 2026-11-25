"""Exercise authoritative knowledge acquisition and generated presentations."""
from __future__ import annotations

import copy
from dataclasses import FrozenInstanceError
import errno
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import execution_contract as c
import knowledge_documents as documents
from knowledge_documents import DocumentReader, decode_document, markdown_path, record_id, record_path
import rebuild_metadata


DOCUMENT = 'references/current'
RECORD = {'sections': [{'id': 'first', 'body': '# First\nFirst body.\n\n'},
                       {'id': 'second', 'body': '## Second\nSecond body.\n'}]}


class RecordAdmissionTests(unittest.TestCase):
    def setUp(self):
        documents._cached_derivation.cache_clear()
        self.addCleanup(documents._cached_derivation.cache_clear)
        self.encoded = c.encoded(RECORD)

    def acquire(self, value):
        return DocumentReader({record_path(DOCUMENT): c.encoded(value)}.__getitem__).acquire(DOCUMENT)

    def test_records_declare_complete_bodies_without_a_second_source_read(self):
        reads = []
        def read(path):
            reads.append(path)
            self.assertEqual(path, record_path(DOCUMENT))
            return self.encoded
        reader = DocumentReader(read)
        acquired = reader.acquire(DOCUMENT)
        self.assertIs(reader.acquire(DOCUMENT), acquired)
        self.assertEqual(reads, [record_path(DOCUMENT)])
        self.assertEqual(acquired.record, {'path': record_path(DOCUMENT),
                                          'sha256': c.digest(self.encoded), 'size': len(self.encoded)})
        self.assertEqual([section.section_id for section in acquired.sections], ['first', 'second'])
        for row in RECORD['sections']:
            section = acquired.section(row['id'])
            raw = row['body'].encode('utf-8')
            self.assertEqual(section.raw, raw)
            self.assertEqual(section.metadata(), {'section_id': row['id'], 'sha256': c.digest(raw), 'size': len(raw)})

    def test_invalid_record_shapes_and_ambiguous_ids_are_refused(self):
        cases = [None, [], {}, {'sections': []}, {'sections': {}}, {'sections': [None]},
                 {'sections': [RECORD['sections'][0]], 'notes': 'not a record field'},
                 {'sections': [{'id': 'first'}]},
                 {'sections': [{'id': 'first', 'body': 'Body.', 'notes': 'not a section field'}]},
                 {'sections': [RECORD['sections'][0], RECORD['sections'][0]]}]
        cases += [{'sections': [{'id': value, 'body': 'Complete body.'}]}
                  for value in ('', 'MixedCase', '../elsewhere', 'two words', 1, None)]
        cases += [{'sections': [{'id': 'first', 'body': value}]}
                  for value in ('', ' \t\n', None, 1, [], '\ud800')]
        for value in cases:
            with self.subTest(value=value), self.assertRaises(ValueError):
                # JSON permits an escaped surrogate, but a UTF-8 body does not.
                import json
                raw = json.dumps(value, ensure_ascii=True, allow_nan=False).encode('ascii')
                DocumentReader({record_path(DOCUMENT): raw}.__getitem__).acquire(DOCUMENT)

    def test_strict_json_retains_duplicate_key_and_numeric_errors(self):
        for raw, message in (
            (b'{"sections":[],"sections":[]}', 'duplicate JSON key: sections'),
            (b'{"sections":[{"id":"one","body":"first","body":"later"}]}', 'duplicate JSON key: body'),
            (b'{"sections":[{"id":"one","body":NaN}]}', 'non-finite JSON number'),
            (b'\xff', 'utf-8'),
        ):
            with self.subTest(raw=raw), self.assertRaisesRegex(ValueError, message):
                DocumentReader({record_path(DOCUMENT): raw}.__getitem__).acquire(DOCUMENT)

    def test_body_editions_and_order_do_not_reassign_section_identity(self):
        before = self.acquire(RECORD)
        changed = copy.deepcopy(RECORD)
        changed['sections'][0]['body'] = '# Renamed display\nFirst body.\n\n### Another heading\nMore text.\n'
        changed['sections'].reverse()
        after = self.acquire(changed)
        self.assertEqual([section.section_id for section in after.sections], ['second', 'first'])
        self.assertEqual(after.section('second'), before.section('second'))
        self.assertNotEqual(after.section('first').sha256, before.section('first').sha256)
        self.assertEqual(after.section('first').raw, changed['sections'][1]['body'].encode('utf-8'))
        with self.assertRaisesRegex(ValueError, 'not declared'):
            after.section('renamed-display')

    def test_record_and_section_exports_cannot_change_retained_values(self):
        acquired = self.acquire(RECORD)
        exported = acquired.record
        exported['path'] = 'caller-owned export'
        exported['sha256'] = '0' * 64
        section = acquired.section('first')
        metadata = section.metadata()
        metadata['section_id'] = 'caller-owned-export'
        metadata['sha256'] = '0' * 64
        with self.assertRaises(FrozenInstanceError):
            section.raw = b'Changed by caller.'
        with self.assertRaises(FrozenInstanceError):
            acquired.sections = ()
        self.assertEqual(acquired.record['sha256'], c.digest(self.encoded))
        self.assertEqual(acquired.record['path'], record_path(DOCUMENT))
        self.assertEqual(acquired.section('first').metadata()['sha256'], c.digest(RECORD['sections'][0]['body'].encode('utf-8')))
        with self.assertRaises(ValueError):
            acquired.section('../elsewhere')

    def test_new_reader_observes_same_size_same_mtime_edits(self):
        with tempfile.TemporaryDirectory(prefix='knowledge-record-edition-') as temporary:
            root = Path(temporary)
            path = root / record_path(DOCUMENT)
            path.parent.mkdir(parents=True)
            path.write_bytes(self.encoded)
            reader = DocumentReader(lambda relative: (root / relative).read_bytes())
            held = reader.acquire(DOCUMENT)
            before = path.stat()
            revised = self.encoded.replace(b'# First', b'# Later')
            path.write_bytes(revised)
            os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
            self.assertEqual((path.stat().st_size, path.stat().st_mtime_ns),
                             (before.st_size, before.st_mtime_ns))
            self.assertIs(reader.acquire(DOCUMENT), held)
            current = DocumentReader(lambda relative: (root / relative).read_bytes()).acquire(DOCUMENT)
            self.assertEqual(current.section('first').raw, b'# Later\nFirst body.\n\n')
            self.assertNotEqual(current.section('first').sha256, held.section('first').sha256)
            self.assertEqual(current.section('second'), held.section('second'))
            self.assertEqual(current.record['sha256'], c.digest(revised))
            self.assertNotEqual(current.record['sha256'], held.record['sha256'])

    def test_record_formatting_has_its_own_identity_without_changing_body_evidence(self):
        first = decode_document(DOCUMENT, self.encoded)
        changed = self.encoded[:-1] + b'\t'
        later = decode_document(DOCUMENT, changed)
        self.assertEqual(first.sections, later.sections)
        self.assertNotEqual(first.record['sha256'], later.record['sha256'])
        self.assertEqual(later.record['sha256'], c.digest(changed))

    def test_failed_acquisition_does_not_retain_an_incomplete_record(self):
        files = {}
        calls = []
        def read(path):
            calls.append(path)
            return files[path]
        reader = DocumentReader(read)
        with self.assertRaisesRegex(ValueError, 'authoritative record'):
            reader.acquire(DOCUMENT)
        files[record_path(DOCUMENT)] = b'{"sections":[]}'
        with self.assertRaisesRegex(ValueError, 'nonempty ordered sections'):
            reader.acquire(DOCUMENT)
        files[record_path(DOCUMENT)] = self.encoded
        acquired = reader.acquire(DOCUMENT)
        self.assertEqual(acquired.section('first').raw, RECORD['sections'][0]['body'].encode('utf-8'))
        self.assertIs(reader.acquire(DOCUMENT), acquired)
        self.assertEqual(calls, [record_path(DOCUMENT)] * 3)

    def test_independent_readers_share_only_immutable_derivatives_of_exact_bytes(self):
        calls = []
        files = {record_path(DOCUMENT): self.encoded}
        def read(path):
            raw = bytes(bytearray(files[path]))
            calls.append(path)
            return raw
        with patch.object(documents, '_derive', wraps=documents._derive) as derive:
            first = DocumentReader(read).acquire(DOCUMENT)
            second = DocumentReader(read).acquire(DOCUMENT)
            self.assertEqual(derive.call_count, 1)
            self.assertIsNot(first, second)
            self.assertEqual(first.sections, second.sections)
            exported = first.record
            exported['sha256'] = '0' * 64
            self.assertEqual(second.record['sha256'], c.digest(self.encoded))
            files[record_path(DOCUMENT)] = self.encoded.replace(b'# First', b'# Later')
            current = DocumentReader(read).acquire(DOCUMENT)
            self.assertEqual(derive.call_count, 2)
            self.assertNotEqual(current.section('first'), first.section('first'))
            self.assertEqual(calls, [record_path(DOCUMENT)] * 3)
        other_id = 'references/another'
        other = decode_document(other_id, self.encoded)
        self.assertEqual(other.sections, first.sections)
        self.assertNotEqual(other.record['path'], first.record['path'])
        self.assertEqual(other.document_id, other_id)

    def test_oversized_records_are_valid_without_cross_boundary_retention(self):
        with patch.object(documents, '_DERIVATION_CACHE_MAX_BYTES', len(self.encoded) - 1), \
             patch.object(documents, '_derive', wraps=documents._derive) as derive:
            first = self.acquire(RECORD)
            second = self.acquire(RECORD)
            self.assertEqual(first.sections, second.sections)
            self.assertEqual(derive.call_count, 2)
            self.assertEqual(documents._cached_derivation.cache_info().currsize, 0)

    def test_utf8_body_size_and_digest_name_the_original_bytes(self):
        body = '# Detail\n\u5f62\u72b6\n'
        acquired = self.acquire({'sections': [{'id': 'detail', 'body': body}]})
        raw = body.encode('utf-8')
        self.assertEqual(acquired.section('detail').raw, raw)
        self.assertEqual(acquired.section('detail').size, len(raw))
        self.assertNotEqual(len(raw), len(body))
        self.assertEqual(acquired.section('detail').sha256, c.digest(raw))


class KnowledgePathTests(unittest.TestCase):
    def test_document_paths_have_one_canonical_round_trip(self):
        for identifier in ('references/runtime/production-workflow', 'protocols/semantics',
                           'templates/narrative/personas/persona-template', 'source_2'):
            with self.subTest(identifier=identifier):
                path = record_path(identifier)
                self.assertEqual(path, 'knowledge/' + identifier + '.json')
                self.assertEqual(record_id(path), identifier)
                self.assertEqual(markdown_path(identifier), identifier + '.md')

    def test_invalid_or_private_identities_are_refused_before_reading(self):
        read = Mock(side_effect=AssertionError('Invalid identity reached file acquisition'))
        invalid = ('', '/', '/absolute', '../outside', 'references/../outside', 'references/./source',
                   'references//source', 'references/source/', r'references\source', 'C:/source',
                   '//server/share', 'references/source:stream', 'references/source\0',
                   'references/Upper', 'references/source.md', 'references/source ',
                   'references/con', 'references/aux', 'references/credentials', None, 1)
        for identifier in invalid:
            with self.subTest(identifier=identifier), self.assertRaises(ValueError):
                DocumentReader(read).acquire(identifier)
        read.assert_not_called()
        for path in ('references/source.json', 'knowledge/source', 'knowledge/source.md.json',
                     'knowledge//source.json', 'knowledge/../source.json', 'knowledge/credentials.json', None):
            with self.subTest(path=path), self.assertRaises(ValueError):
                record_id(path)


class GeneratedDocumentTests(unittest.TestCase):
    def test_dry_run_and_real_render_share_content_and_only_remove_previously_owned_outputs(self):
        with tempfile.TemporaryDirectory(prefix='knowledge-presentations-') as temporary:
            root = Path(temporary)
            kept_id, removed_id = DOCUMENT, 'references/removed'
            for identifier in (kept_id, removed_id):
                source = root / record_path(identifier)
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_bytes(c.encoded(RECORD))
            authored = root / 'references/independent.md'
            authored.parent.mkdir(parents=True)
            authored.write_bytes(b'Independent authored document.\n')
            with patch.object(rebuild_metadata, 'ROOT', root), \
                 patch.object(rebuild_metadata, '_CAPTURED', None), \
                 patch.object(rebuild_metadata, '_REMOVED', set()):
                expected = sorted([markdown_path(kept_id), markdown_path(removed_id)])
                self.assertEqual(rebuild_metadata.rebuild_knowledge_documents(), expected)
                initial = {relative: (root / relative).read_bytes() for relative in expected}
                operation = Mock()
                with patch.object(rebuild_metadata._operation_context, 'current', return_value=operation):
                    self.assertEqual(rebuild_metadata.rebuild_knowledge_documents(), expected)
                self.assertEqual(operation.artifact.call_count, len(expected))
                for relative, raw in initial.items():
                    operation.artifact.assert_any_call((root / relative).absolute(),
                                                       content_sha256=c.digest(raw), size=len(raw))
                (root / 'MANIFEST.json').write_bytes(c.encoded({'files': [
                    {'path': record_path(kept_id)}, {'path': record_path(removed_id)},
                    {'path': 'references/independent.md'}]}))
                current_record = c.encoded(RECORD).replace(b'# First', b'# Later')
                (root / record_path(kept_id)).write_bytes(current_record)
                (root / record_path(removed_id)).unlink()
                captured, removed = {}, set()
                with patch.object(rebuild_metadata, '_CAPTURED', captured), \
                     patch.object(rebuild_metadata, '_REMOVED', removed):
                    self.assertEqual(rebuild_metadata.rebuild_knowledge_documents(), [markdown_path(kept_id)])
                self.assertEqual(set(captured), {root / markdown_path(kept_id)})
                self.assertEqual(removed, {root / markdown_path(removed_id)})
                self.assertEqual({relative: (root / relative).read_bytes() for relative in expected}, initial)
                generated = captured[root / markdown_path(kept_id)].encode('utf-8')
                self.assertEqual(generated, initial[markdown_path(kept_id)].replace(b'# First', b'# Later'))
                self.assertEqual(rebuild_metadata.rebuild_knowledge_documents(), [markdown_path(kept_id)])
                self.assertEqual((root / markdown_path(kept_id)).read_bytes(), generated)
                self.assertFalse((root / markdown_path(removed_id)).exists())
                self.assertEqual((root / record_path(kept_id)).read_bytes(), current_record)
                self.assertEqual(authored.read_bytes(), b'Independent authored document.\n')

    def test_capture_renders_the_record_even_when_the_markdown_is_missing_or_stale(self):
        for present in (True, False):
            with self.subTest(present=present), tempfile.TemporaryDirectory(prefix='knowledge-capture-') as temporary:
                root = Path(temporary)
                source = root / record_path(DOCUMENT)
                source.parent.mkdir(parents=True)
                source.write_bytes(c.encoded(RECORD))
                target = root / markdown_path(DOCUMENT)
                target.parent.mkdir(parents=True)
                if present:
                    target.write_bytes(b'Stale presentation.\n')
                captured = {}
                with patch.object(rebuild_metadata, 'ROOT', root), \
                     patch.object(rebuild_metadata, '_CAPTURED', captured), \
                     patch.object(rebuild_metadata, '_REMOVED', set()):
                    self.assertEqual(rebuild_metadata.rebuild_knowledge_documents(), [markdown_path(DOCUMENT)])
                self.assertEqual(captured[target], ''.join(row['body'] for row in RECORD['sections']))
                self.assertEqual(source.read_bytes(), c.encoded(RECORD))
                self.assertEqual(target.exists(), present)
                if present:
                    self.assertEqual(target.read_bytes(), b'Stale presentation.\n')

    def test_capture_manifest_describes_the_same_tree_as_actual_generation(self):
        with tempfile.TemporaryDirectory(prefix='knowledge-capture-manifest-') as temporary:
            root = Path(temporary)
            source, generated, obsolete = (root / name for name in ('source.bin', 'generated.md', 'obsolete.md'))
            source.write_bytes(b'\0\1\2')
            generated.write_bytes(b'Previous generated body.\n')
            obsolete.write_bytes(b'Old owned document.\n')
            manifest = root / 'MANIFEST.json'
            manifest.write_bytes(b'{}\n')
            created = root / 'new.md'
            captured = {generated: 'Current generated body.\n', created: '', manifest: 'Its own inventory excludes this.'}
            before = {path: path.read_bytes() for path in (source, generated, obsolete, manifest)}
            with patch.object(rebuild_metadata, 'ROOT', root), \
                 patch.object(rebuild_metadata, '_CAPTURED', captured), \
                 patch.object(rebuild_metadata, '_REMOVED', {obsolete}):
                predicted = rebuild_metadata.manifest_file_records(iter(before))
            self.assertEqual({path: path.read_bytes() for path in before}, before)
            self.assertFalse(created.exists())
            self.assertEqual([row['path'] for row in predicted], ['generated.md', 'new.md', 'source.bin'])
            for path, text in captured.items():
                path.write_bytes(text.encode('utf-8'))
            obsolete.unlink()
            with patch.object(rebuild_metadata, 'ROOT', root), \
                 patch.object(rebuild_metadata, '_CAPTURED', None), \
                 patch.object(rebuild_metadata, '_REMOVED', set()):
                actual = rebuild_metadata.manifest_file_records(root.iterdir())
            self.assertEqual(actual, predicted)
            for row in actual:
                raw = (root / row['path']).read_bytes()
                self.assertEqual((row['bytes'], row['sha256']), (len(raw), c.digest(raw)))

    def test_a_new_invocation_selects_its_own_capture_mode_after_a_failed_check(self):
        observed = []
        def stop(_root):
            observed.append(isinstance(rebuild_metadata._CAPTURED, dict))
            raise RuntimeError('Stop before acquiring the catalog.')
        with patch.object(rebuild_metadata, '_CAPTURED', None), \
             patch.object(rebuild_metadata, '_REMOVED', set()), \
             patch.object(rebuild_metadata, 'load_package_metadata', side_effect=stop):
            for arguments in (['--check'], []):
                with self.assertRaisesRegex(RuntimeError, 'Stop before acquiring the catalog'):
                    rebuild_metadata.main(arguments)
        self.assertEqual(observed, [True, False])

    def test_generated_writes_retain_private_and_symbolic_link_boundaries(self):
        with tempfile.TemporaryDirectory(prefix='knowledge-write-boundaries-') as temporary:
            root = Path(temporary)
            raw = b'Generated body.\n'
            target = root / 'target.md'
            target.write_bytes(raw)
            private = root / 'credentials.json'
            private.write_bytes(raw)
            with patch.object(rebuild_metadata, '_CAPTURED', None):
                with self.assertRaisesRegex(ValueError, 'Private Studio credentials'):
                    rebuild_metadata.write_text_atomic(private, raw.decode('utf-8'))
                self.assertEqual(private.read_bytes(), raw)
                alias = root / 'alias.md'
                try:
                    alias.symlink_to(target)
                except (OSError, NotImplementedError) as exc:
                    self.skipTest(str(exc))
                with self.assertRaisesRegex(ValueError, 'symbolic link'):
                    rebuild_metadata.write_text_atomic(alias, raw.decode('utf-8'))
                self.assertTrue(alias.is_symlink())
                self.assertEqual(target.read_bytes(), raw)

    def test_metadata_retry_after_parent_sync_failure_requires_the_barrier_before_success(self):
        with tempfile.TemporaryDirectory(prefix='knowledge-metadata-durability-') as temporary:
            root = Path(temporary)
            target = root / 'metadata.json'
            target.write_bytes(b'{"edition":"previous"}\n')
            text = '{"edition":"current"}\n'
            raw = text.encode('utf-8')
            operation = Mock()

            def failed_parent_barrier(path):
                self.assertEqual(path, root)
                self.assertEqual(target.read_bytes(), raw)
                raise OSError(errno.EIO, 'Injected parent directory fsync failure')

            with patch.object(rebuild_metadata, '_CAPTURED', None), \
                 patch.object(rebuild_metadata._operation_context, 'current', return_value=operation):
                with patch.object(c, 'fsync_dir', side_effect=failed_parent_barrier) as barrier:
                    with self.assertRaisesRegex(OSError, 'parent directory fsync failure'):
                        rebuild_metadata.write_text_atomic(target, text)
                    self.assertEqual(target.read_bytes(), raw)
                    operation.artifact.assert_not_called()
                    with self.assertRaisesRegex(OSError, 'parent directory fsync failure'):
                        rebuild_metadata.write_text_atomic(target, text)
                    self.assertEqual(barrier.call_count, 2)
                    operation.artifact.assert_not_called()
                with patch.object(c, 'fsync_dir', wraps=c.fsync_dir) as barrier:
                    rebuild_metadata.write_text_atomic(target, text)
                    barrier.assert_called_once_with(root)
                self.assertEqual(target.read_bytes(), raw)
                operation.artifact.assert_called_once_with(target.absolute(),
                    content_sha256=c.digest(raw), size=len(raw))


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
