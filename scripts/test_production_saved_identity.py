"""Restore omitted identity owners from an exact synthetic saved input revision."""
from __future__ import annotations

import copy
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import execution_contract as c
import production_identity as identity
import production_identity_boundary as boundary
import production_saved_inputs as saved
from production_diagnostics import ProductionError
from reference_runtime_smoke_test import _fixture_png


class SavedIdentityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='cpb-saved-identity-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.raw = _fixture_png()
        self.native = {'references': [{'id': 'angle', 'file': 'image.png', 'role': 'identity',
            'use_for': ['identity'], 'do_not_transfer': ['lighting'],
            'subject_uses': [{'subject_id': 'A', 'use': 'identity', 'priority': 0}]}]}
        self.task = {'artifact': 'image', 'recording': {'subject_map': {'A': {}}},
            'sources': [{'id': 'pixels', 'path': 'image.png', 'identity': {
                'subject_ids': ['A'], 'selectors': ['']}}], 'criteria': [], 'image_input': 'input.json'}
        self.files = {'image.png': self.raw, 'input.json': c.encoded(self.native)}
        self.loaded = self.publication(self.task, self.files, consumer={'image_input': self.native})
        direct = copy.deepcopy(self.task)
        direct.pop('image_input')
        old = identity.source_snapshot(direct, self.files.__getitem__)
        self.context = {'authoring_work': {'operation': 'amend'},
            'derived_from': {'source_run': {'run': 'saved-run', 'input_sha256': 'a' * 64}},
            'task_content': copy.deepcopy(self.task),
            'identity_coverage': {**old, 'bindings': [], 'reference_choices': copy.deepcopy(self.native['references'])}}

    def publication(self, task, files, *, consumer=None, revision=None):
        objects = {c.digest(raw): raw for raw in files.values()}
        prepared = {'run': 'saved-run', 'input_sha256': 'a' * 64, 'task': copy.deepcopy(task),
            'dependencies': [{'path': path, 'space': 'task-source', 'sha256': c.digest(raw), 'size': len(raw)}
                             for path, raw in files.items()]}
        if revision is not None:
            prepared['authored_revision'] = revision
        return SimpleNamespace(prepared=prepared, consumer=copy.deepcopy(consumer or {}), artifacts={},
            manifest={'files': []}, directory=self.root / 'saved-run',
            evidence=SimpleNamespace(read=objects.__getitem__))

    def restore(self, context=None, loaded=None):
        return saved.identity_context(self.root, context or self.context,
                                      read_run=lambda run: loaded or self.loaded)

    def current(self, choices=None):
        return identity.source_snapshot(self.task, self.files.__getitem__,
            choices=choices or {'external': {'image_input': self.native}})

    def test_saved_original_restores_a_reference_suppressed_by_equal_direct_pixels(self):
        self.assertEqual([row['id'] for row in self.context['identity_coverage']['sources']], ['pixels'])
        restored = self.restore()
        self.assertEqual({row['id'] for row in restored['retained_identity_sources']['sources']},
                         {'pixels', 'reference:angle'})
        comparison = boundary.compare(restored['retained_identity_sources'], self.current())
        self.assertEqual(comparison, {'changes': [], 'unresolved': []})
        boundary.require_unchanged(restored, {'operation': 'amend'}, self.current())

    def test_current_reference_edits_cannot_redefine_the_retained_authority(self):
        before = self.restore()['retained_identity_sources']
        choices = {'external': {'image_input': copy.deepcopy(self.native)}}
        choices['external']['image_input']['references'][0]['do_not_transfer'].append('outfit')
        restored = self.restore()
        self.assertEqual(restored['retained_identity_sources'], before)
        with self.assertRaises(ProductionError) as caught:
            boundary.require_unchanged(restored, {'operation': 'amend'}, self.current(choices))
        self.assertEqual(caught.exception.diagnostic.details['cause'], 'retained-identity-source-changed')
        self.assertTrue(any((row['source'], row['change_kind']) == ('reference:angle', 'authority')
                            for row in caught.exception.diagnostic.details['changes']))

    def test_read_projection_does_not_write_context_or_open_live_originals(self):
        original = copy.deepcopy(self.context)
        with patch.object(c, 'atomic', side_effect=AssertionError('unexpected write')), \
                patch('production_store.stable_bytes', side_effect=AssertionError('unexpected live read')):
            restored = self.restore()
        self.assertEqual(self.context, original)
        self.assertNotIn('retained_identity_sources', self.context)
        self.assertFalse(restored['retained_identity_sources']['unresolved'])

    def test_an_explicit_boundary_does_not_reopen_its_source_run(self):
        context = self.restore()
        def forbidden(run):
            raise AssertionError('the explicit boundary must be sufficient')
        self.assertIs(saved.identity_context(self.root, context, read_run=forbidden), context)

    def test_compose_needs_no_retained_run_reconstruction(self):
        context = copy.deepcopy(self.context)
        context['authoring_work']['operation'] = 'compose'
        self.assertIs(saved.identity_context(self.root, context,
            read_run=lambda _: self.fail('compose loaded a retained run')), context)

    def test_exact_input_revision_mismatch_is_an_unresolved_retained_owner(self):
        context = copy.deepcopy(self.context)
        context['derived_from']['source_run']['input_sha256'] = 'b' * 64
        restored = self.restore(context)
        result = boundary.compare(restored['retained_identity_sources'], self.current())
        self.assertEqual(result['changes'], [])
        self.assertEqual(result['unresolved'][0]['reason'], 'retained-source-run-revision-mismatch')
        self.assertEqual(result['unresolved'][0]['comparison_side'], 'retained_identity_sources')
        self.assertEqual(result['unresolved'][0]['actual_input_sha256'], 'a' * 64)

    def test_missing_run_preserves_known_evidence_and_names_its_owner(self):
        def unavailable(run):
            raise FileNotFoundError('saved publication unavailable')
        restored = saved.identity_context(self.root, self.context, read_run=unavailable)
        self.assertEqual([row['id'] for row in restored['retained_identity_sources']['sources']], ['pixels'])
        row = restored['retained_identity_sources']['unresolved'][0]
        self.assertEqual((row['reason'], row['run']), ('retained-source-run-unavailable', 'saved-run'))

    def test_current_missing_bytes_are_distinguished_from_missing_retained_evidence(self):
        restored = self.restore()
        proposed = identity.source_snapshot(self.task, lambda _: (_ for _ in ()).throw(FileNotFoundError('current')))
        result = boundary.compare(restored['retained_identity_sources'], proposed)
        self.assertTrue(result['unresolved'])
        self.assertEqual({row['comparison_side'] for row in result['unresolved']}, {'current_identity_sources'})

    def test_complete_registered_inventory_remains_meaningful_without_a_source_run(self):
        context = copy.deepcopy(self.context)
        context['derived_from']['source_run'] = None
        context['identity_coverage'] = {**self.current(), 'bindings': []}
        restored = self.restore(context)
        boundary.require_unchanged(restored, {'operation': 'amend'}, self.current())

    def test_omitted_authority_without_saved_evidence_remains_unknown(self):
        context = copy.deepcopy(self.context)
        context['derived_from']['source_run'] = None
        restored = self.restore(context)
        comparison = boundary.compare(restored['retained_identity_sources'], self.current())
        self.assertEqual(comparison['changes'], [])
        self.assertEqual(comparison['unresolved'][0]['source'], 'reference:angle')
        self.assertEqual(comparison['unresolved'][0]['reason'], 'retained-source-owner-unavailable')

    def test_unfinished_saved_choices_restore_graph_identity_without_delivery(self):
        graph = [{'identity_contract': {'character_id': 'A', 'canon_status': 'approved', 'outline': 'Split ring.'}}]
        choices = {'authoring': {'documents': {'state_graphs': {'file': 'graph.json'}}}}
        files = {'choices.json': c.encoded(choices), 'graph.json': c.encoded(graph)}
        task = {'artifact': 'text', 'sources': [], 'criteria': [], 'delivery': {'path': 'unwritten.txt'}}
        revision = {'state': 'draft', 'choices': {'path': 'choices.json', 'sha256': c.digest(files['choices.json'])}}
        loaded = self.publication(task, files, revision=revision)
        context = copy.deepcopy(self.context)
        context.pop('identity_coverage')
        context['task_content'] = copy.deepcopy(task)
        restored = self.restore(context, loaded)
        self.assertFalse(restored['retained_identity_sources']['unresolved'])
        self.assertEqual([row['id'] for row in restored['retained_identity_sources']['sources']],
                         ['state:A:identity_contract'])

    def test_unread_unfinished_owner_is_never_converted_to_empty(self):
        choices = {'authoring': {'documents': {'state_graphs': {'file': 'missing-graph.json'}}}}
        files = {'choices.json': c.encoded(choices)}
        task = {'artifact': 'text', 'sources': [], 'criteria': []}
        revision = {'state': 'draft', 'choices': {'path': 'choices.json', 'sha256': c.digest(files['choices.json'])}}
        context = copy.deepcopy(self.context)
        context.pop('identity_coverage')
        restored = self.restore(context, self.publication(task, files, revision=revision))
        snapshot = restored['retained_identity_sources']
        self.assertEqual(snapshot['sources'], [])
        self.assertTrue(snapshot['unresolved'])
        self.assertEqual(snapshot['unresolved'][0]['reason'], 'retained-source-owner-unavailable')

    def test_saved_archive_resolves_external_original_paths_without_live_media(self):
        proof = {'kind': 'supplied-file', 'reference_id': 'image-owner',
            'resolved_path': '/missing/original.png', 'media_type': 'image/png', 'sha256': c.digest(self.raw)}
        reference_set = {'selected_references': [{'reference_id': 'angle', 'role': 'identity',
            'source': proof, 'authority': {'controls': ['identity'], 'must_not_control': ['lighting']},
            'subject_uses': copy.deepcopy(self.native['references'][0]['subject_uses'])}]}
        retained = {'prepared': reference_set, 'companion': 'references', 'root': self.root / 'saved',
            'files': {'references/sources/' + c.digest(self.raw): self.raw}, 'carrier_paths': {}}
        native = copy.deepcopy(self.native)
        native['references'][0]['file'] = proof['resolved_path']
        task = copy.deepcopy(self.task)
        task['sources'][0]['path'] = proof['resolved_path']
        loaded = self.publication(task, {}, consumer={'image_input': native})
        context = copy.deepcopy(self.context)
        context.pop('identity_coverage')
        with patch.object(saved.CapturedInputs, 'references', return_value=retained), \
                patch('production_store.stable_bytes', side_effect=AssertionError('unexpected original read')):
            restored = self.restore(context, loaded)
        snapshot = restored['retained_identity_sources']
        self.assertEqual(snapshot['unresolved'], [])
        self.assertEqual({row['id'] for row in snapshot['sources']}, {'pixels', 'reference:angle'})
        row = next(row for row in snapshot['sources'] if row['id'] == 'reference:angle')
        self.assertEqual(row['authority']['source'], proof)

    def test_delivered_carrier_bytes_do_not_replace_the_original_reference_identity(self):
        proof = {'kind': 'supplied-file', 'reference_id': 'image-owner',
            'resolved_path': '/missing/original.png', 'media_type': 'image/png', 'sha256': c.digest(self.raw)}
        prepared = {'transport_mode': 'single-board', 'selected_references': [{
            'reference_id': 'angle', 'role': 'identity', 'source': proof,
            'authority': {'controls': ['identity'], 'must_not_control': ['lighting']},
            'subject_uses': copy.deepcopy(self.native['references'][0]['subject_uses'])}]}
        retained = {'prepared': prepared, 'companion': 'references', 'root': self.root / 'saved',
            'files': {'references/sources/' + c.digest(self.raw): self.raw}, 'carrier_paths': {}}
        binding = copy.deepcopy(self.native)
        binding['references'][0].update(file='board.png', sha256=c.digest(b'synthetic board carrier'))
        loaded = self.publication(self.task, {**self.files, 'board.png': b'synthetic board carrier'},
                                  consumer={'image_input': binding})
        context = copy.deepcopy(self.context)
        context.pop('identity_coverage')
        with patch.object(saved.CapturedInputs, 'references', return_value=retained):
            snapshot = self.restore(context, loaded)['retained_identity_sources']
        self.assertEqual(snapshot['unresolved'], [])
        row = next(row for row in snapshot['sources'] if row['id'] == 'reference:angle')
        self.assertEqual(row['sha256'], c.digest(self.raw))
        self.assertEqual(row['authority']['source'], proof)


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
