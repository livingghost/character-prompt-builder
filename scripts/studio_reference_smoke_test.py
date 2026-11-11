#!/usr/bin/env python3
"""Synthetic current-acceptance references and portable proof verification."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import execution_contract as c
import studio
import studio_reference as sr
import sheet_artifacts as fills
from sheet_artifacts_smoke_test import accepted, make_artifact, decision
from production_fixtures import scratch_home_dir


class StudioSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = studio.init(self.base / 'studio', 'synthetic-source-owner', 'Synthetic source fixture')
        studio.add_character(self.root, 'robot', 'general')
        self.sheet = self.root / 'characters/robot/sheet/sheet-data.json'
        self.artifact = accepted(self.sheet)
        self.source = sr.current_source(self.root, 'robot', 'canon.primary')

    def test_current_source_pins_owner_artifact_and_acceptance(self):
        proof = sr.validate_source(self.source)
        self.assertEqual(self.source['artifact_id'], self.artifact['artifact_id'])
        self.assertEqual(self.source['acceptance_sha256'], c.content_id(c.load(self.sheet)['slots']['canon.primary']['current']))
        self.assertEqual(proof['studio_id'], 'synthetic-source-owner')
        from prepare_generation_references import validate_committed_source
        self.assertEqual(validate_committed_source(self.source), self.source)

    def test_live_reference_reads_do_not_take_writer_locks(self):
        with patch.object(c, 'lock', side_effect=AssertionError('reference reads must not acquire writer locks')):
            current = sr.current_source(self.root, 'robot', 'canon.primary')
            proof = sr.validate_source(current)
        self.assertEqual(current, self.source)
        self.assertEqual(proof['acceptance']['artifact'], self.artifact)

    def test_one_reference_phase_keeps_independent_studio_owners(self):
        import runtime_snapshot
        other = studio.init(self.base / 'other', 'another-source-owner', 'Another synthetic source')
        studio.add_character(other, 'robot', 'general')
        accepted(other / 'characters/robot/sheet/sheet-data.json')
        reads = sr.ReferenceReads()
        with runtime_snapshot.public_call():
            first = sr.current_source(self.root, 'robot', 'canon.primary', read=reads.studio(self.root))
            second = sr.current_source(other, 'robot', 'canon.primary', read=reads.studio(other))
            self.assertEqual(sr.validate_source(first, reads=reads)['studio_id'], 'synthetic-source-owner')
            self.assertEqual(sr.validate_source(second, reads=reads)['studio_id'], 'another-source-owner')
            self.assertIsNot(reads.studio(self.root), reads.studio(other))
        self.assertEqual(first['sha256'], second['sha256'])
        self.assertNotEqual(first['proof_sha256'], second['proof_sha256'])

    def test_status_repairs_a_missing_reference_view_once(self):
        import adoption_workflow
        view = self.sheet.parent / 'active-references.json'
        view.unlink(missing_ok=True)
        with patch.object(adoption_workflow, '_reference_index', wraps=adoption_workflow._reference_index) as index:
            studio.status(self.root)
        self.assertEqual(index.call_count, 1)
        self.assertTrue(view.is_file())

    def test_recorded_paths_keep_the_origin_platform_without_a_live_lookup(self):
        self.assertEqual(str(sr._origin_root('C:\\Studio') / self.source['sheet']),
                         'C:\\Studio\\characters\\robot\\sheet\\sheet-data.json')
        self.assertEqual(str(sr._origin_root('/recorded/studio') / self.source['sheet']),
                         '/recorded/studio/characters/robot/sheet/sheet-data.json')
        with self.assertRaises(ValueError): sr._origin_root('relative/studio')

    def test_candidate_is_not_current(self):
        candidate = make_artifact(self.sheet, marker='pending')
        fills.register_candidates(self.sheet, [('pending', candidate)])
        with self.assertRaisesRegex(ValueError, 'no current accepted'):
            sr.current_source(self.root, 'robot', 'pending')

    def test_uppercase_studio_character_id_is_canonical(self):
        # Studio character IDs follow studio.CHARACTER_ID, which allows
        # uppercase (C01); only slots are restricted to lowercase.
        studio.add_character(self.root, 'C01', 'general')
        sheet = self.root / 'characters/C01/sheet/sheet-data.json'
        artifact = accepted(sheet)
        source = sr.current_source(self.root, 'C01', 'canon.primary')
        self.assertEqual(source['artifact_id'], artifact['artifact_id'])
        self.assertEqual(source['character'], 'C01')
        from prepare_generation_references import validate_committed_source
        self.assertEqual(validate_committed_source(source), source)

    def test_replacement_is_rejected_even_when_old_bytes_remain(self):
        accepted(self.sheet, marker='replacement', color=(140,80,30))
        self.assertTrue(Path(self.source['resolved_path']).is_file())
        with self.assertRaisesRegex(ValueError, 'no longer matches'):
            sr.validate_source(self.source)

    def test_withdrawn_acceptance_is_rejected(self):
        from sheet_artifacts_smoke_test import withdrawal_decision
        fills.withdraw(self.sheet, withdrawal_decision(self.sheet), evidence_root=self.sheet.parent)
        with self.assertRaisesRegex(ValueError, 'no current accepted'):
            sr.validate_source(self.source)

    def test_same_pixels_with_different_provenance_are_distinct(self):
        newer = accepted(self.sheet, marker='new-provenance')
        self.assertEqual(newer['image']['sha256'], self.source['sha256'])
        with self.assertRaisesRegex(ValueError, 'no longer matches'):
            sr.validate_source(self.source)

    def test_same_artifact_readopted_under_new_decision_is_distinct(self):
        accepted(self.sheet, marker='other', color=(70,30,90))
        fills.register_candidates(self.sheet, [('canon.primary', self.artifact)])
        choice = decision(self.sheet, 'canon.primary', self.artifact)
        choice['reason'] = 'Explicit synthetic new decision restores this original.'
        fills.adopt(self.sheet, choice, evidence_root=self.sheet.parent)
        self.assertEqual(sr.current_source(self.root, 'robot', 'canon.primary')['artifact_id'], self.source['artifact_id'])
        with self.assertRaisesRegex(ValueError, 'no longer matches'):
            sr.validate_source(self.source)

    def test_unrelated_candidates_and_slots_do_not_invalidate(self):
        pending = make_artifact(self.sheet, marker='unrelated')
        fills.register_candidates(self.sheet, [('parts.detail', pending)])
        accepted(self.sheet, slot='parts.other', marker='other-accepted')
        self.assertEqual(sr.current_source(self.root, 'robot', 'canon.primary'), self.source)
        sr.validate_source(self.source)

    def test_same_pixels_in_another_slot_cannot_substitute(self):
        fills.register_candidates(self.sheet, [('parts.other', self.artifact)])
        fills.adopt(self.sheet, decision(self.sheet, 'parts.other', self.artifact), evidence_root=self.sheet.parent)
        forged = copy.deepcopy(self.source); forged['slot'] = 'parts.other'
        with self.assertRaisesRegex(ValueError, 'no longer matches'):
            sr.validate_source(forged)

    def test_another_studio_or_character_cannot_substitute(self):
        for changes in ({'studio_id':'another-studio'}, {'character':'another'}, {'sheet':'characters/other/sheet/sheet-data.json'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                sr.validate_source({**self.source, **changes})

    def test_approval_evidence_mutation_is_rejected(self):
        item = c.load(self.sheet)['slots']['canon.primary']['current']['approval']
        (self.sheet.parent / item['evidence_path']).write_bytes(b'changed evidence')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            sr.validate_source(self.source)

    def test_decision_mutation_is_rejected(self):
        item = c.load(self.sheet)['slots']['canon.primary']['current']['approval']
        path = self.sheet.parent / item['decision_path']
        data = c.load(path); data['by'] = 'Someone else'; c.atomic_write_json(path, data)
        with self.assertRaisesRegex(ValueError, 'approval differs'):
            sr.validate_source(self.source)

    def test_image_mutation_is_rejected(self):
        Path(self.source['resolved_path']).write_bytes(b'changed image')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            sr.validate_source(self.source)

    def test_nonidentity_local_approval_is_not_identity_authority(self):
        with self.assertRaisesRegex(ValueError, 'no explicit Studio identity'):
            sr.identity_source(self.source, root=self.root, character_id='robot')

    def test_archive_survives_original_studio_deletion(self):
        companion = self.base / 'package.references'
        sr.archive_source(self.source, companion)
        shutil.rmtree(self.root)
        proof = sr.validate_source(self.source, active=False, source_archive=companion/'sources')
        self.assertEqual(proof['acceptance']['artifact'], self.artifact)

    def test_archive_proof_and_evidence_mutation_are_rejected(self):
        companion = self.base / 'package.references'
        sr.archive_source(self.source, companion)
        folder = companion / 'studio' / self.source['proof_sha256']
        original = (folder/'proof.json').read_bytes()
        (folder/'proof.json').write_bytes(original.replace(b'synthetic-source-owner', b'forged-source-owner'))
        with self.assertRaises(ValueError): sr.validate_source(self.source, active=False, source_archive=companion/'sources')
        (folder/'proof.json').write_bytes(original)
        item = c.load(self.sheet)['slots']['canon.primary']['current']['approval']
        (folder/'sheet'/item['evidence_path']).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            sr.validate_source(self.source, active=False, source_archive=companion/'sources')

    def test_repeated_archive_is_idempotent(self):
        companion = self.base / 'package.references'
        sr.archive_source(self.source, companion)
        before = {p.relative_to(companion):p.read_bytes() for p in companion.rglob('*') if p.is_file()}
        sr.archive_source(self.source, companion)
        self.assertEqual(before, {p.relative_to(companion):p.read_bytes() for p in companion.rglob('*') if p.is_file()})

    def test_symlink_source_cannot_escape(self):
        path = Path(self.source['resolved_path']); outside = self.base/'outside.png'
        outside.write_bytes(path.read_bytes()); path.unlink()
        try: path.symlink_to(outside)
        except (OSError, NotImplementedError): self.skipTest('symbolic links unavailable')
        with self.assertRaises(ValueError): sr.validate_source(self.source)

    def test_cli_resolves_real_ids_and_does_not_overwrite(self):
        import contextlib, io
        target = self.base/'source.json'
        args = ['--studio',str(self.root),'--character','robot','--slot','canon.primary','source','--out',str(target)]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(sr.main(args),0)
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            self.assertEqual(sr.main(args),2)
        diagnostic = json.loads(printed.getvalue())['diagnostics'][0]
        self.assertEqual((diagnostic['code'], diagnostic['required_action']), ('OUTPUT_ALREADY_EXISTS', 'Choose a new --out.'))
        self.assertEqual(c.load(target),self.source)


class AcceptedStudioImageTests(unittest.TestCase):
    """Ordinary slot acceptance is sufficient scene evidence and never invents canon."""

    def setUp(self):
        import production_fixtures
        from transport_synthetic import _png
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.enterContext(production_fixtures.scratch_home(self.base / 'home'))
        self.root = studio.init(self.base / 'studio', 'accepted-scenes', 'Synthetic accepted scenes')
        studio.add_character(self.root, 'robot', 'general')
        self.image = self.base / 'scene.png'; self.image.write_bytes(_png(32, 32, bytes((45, 100, 130))))
        self.row = self.add_image('episode.opening')
        studio.accept(self.root, 'robot', self.row['iteration_id'])
        self.source = sr.current_accepted_source(self.root, 'robot', 'episode.opening')

    def add_image(self, slot):
        return studio.iterate(self.root, 'robot', slot, self.image, package=None, request=None,
                              response=None, note='Synthetic accepted scene fixture.')

    def test_scene_source_keeps_exact_acceptance_without_declaring_a_sheet_panel(self):
        from prepare_generation_references import validate_committed_source
        from visual_continuity import declared_sheet_slots
        proof = sr.validate_source(self.source)
        self.assertEqual(self.source['kind'], 'studio-accepted-image')
        self.assertEqual(self.source['iteration_id'], self.row['iteration_id'])
        self.assertEqual(self.source['sha256'], self.row['result']['sha256'])
        self.assertEqual(self.source['acceptance_sha256'], c.content_id(proof['acceptance']))
        self.assertIsNone(proof['production'])
        self.assertEqual(proof['provenance'], 'external-import')
        self.assertEqual(validate_committed_source(self.source), self.source)
        self.assertNotIn('episode.opening', declared_sheet_slots(self.root, 'robot'))
        self.assertNotIn('episode.opening', studio.StudioRead(self.root).sheet('robot')['slots'])
        with self.assertRaisesRegex(ValueError, 'no canonical identity authority'):
            sr.identity_source(self.source, root=self.root, character_id='robot')

    def test_candidate_or_another_owner_cannot_replace_current_acceptance(self):
        self.add_image('waiting')
        with self.assertRaisesRegex(ValueError, 'currently accepted'):
            sr.current_accepted_source(self.root, 'robot', 'waiting')
        for field, value in [('studio_id', 'other'), ('slot', 'waiting'), ('iteration_id', 'it-9999')]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                sr.validate_source({**self.source, field: value})

    def test_new_acceptance_of_identical_pixels_changes_the_source(self):
        replacement = self.add_image('episode.opening')
        studio.accept(self.root, 'robot', replacement['iteration_id'])
        current = sr.current_accepted_source(self.root, 'robot', 'episode.opening')
        self.assertEqual(current['sha256'], self.source['sha256'])
        self.assertNotEqual(current['proof_sha256'], self.source['proof_sha256'])
        with self.assertRaisesRegex(ValueError, 'no longer matches'):
            sr.validate_source(self.source)

    def test_accepted_copy_and_retained_source_are_both_verified(self):
        proof = sr.validate_source(self.source)
        (self.root / proof['accepted_path']).write_bytes(b'changed accepted copy')
        with self.assertRaisesRegex(ValueError, 'recorded bytes'):
            sr.validate_source(self.source)

    def test_recorded_proof_survives_replacement_and_original_studio_deletion(self):
        companion = self.base / 'request.references'
        sr.archive_source(self.source, companion)
        before = {path.relative_to(companion): path.read_bytes() for path in companion.rglob('*') if path.is_file()}
        sr.archive_source(self.source, companion)
        self.assertEqual(before, {path.relative_to(companion): path.read_bytes() for path in companion.rglob('*') if path.is_file()})
        replacement = self.add_image('episode.opening')
        studio.accept(self.root, 'robot', replacement['iteration_id'])
        shutil.rmtree(self.root)
        proof = sr.validate_source(self.source, active=False, source_archive=companion / 'sources')
        self.assertEqual(proof['iteration_id'], self.row['iteration_id'])
        (companion / 'sources' / self.source['sha256']).write_bytes(b'changed recorded source')
        with self.assertRaisesRegex(ValueError, 'bytes changed'):
            sr.validate_source(self.source, active=False, source_archive=companion / 'sources')

    def test_unrelated_acceptance_does_not_change_selected_scene(self):
        another = self.add_image('episode.other')
        studio.accept(self.root, 'robot', another['iteration_id'])
        self.assertEqual(sr.current_accepted_source(self.root, 'robot', 'episode.opening'), self.source)

    def test_imported_scene_cannot_claim_a_production_selection_without_origin(self):
        proof = copy.deepcopy(sr.validate_source(self.source))
        proof['acceptance']['production_selection'] = '1' * 64
        with self.assertRaisesRegex(ValueError, 'without Production origin'):
            sr._accepted_proof(proof)

    def test_cli_returns_explicit_accepted_scene_source(self):
        import contextlib, io
        target = self.base / 'scene-source.json'
        with contextlib.redirect_stdout(io.StringIO()):
            status = sr.main(['--studio', str(self.root), '--character', 'robot', '--slot', 'episode.opening',
                              'accepted-source', '--out', str(target)])
        self.assertEqual(status, 0)
        self.assertEqual(c.load(target), self.source)


class ProductionStudioSourceTests(unittest.TestCase):
    def setUp(self):
        import adoption_workflow as adoption
        import production_case_fixtures as fixtures
        import production_execution as execution
        import production_fixtures as fixture
        import production_workflow as workflow
        from catalog_retrieval import runtime
        from revision_contract import digest
        from test_production_execution import decisions
        from visual_continuity import file_ref

        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.enterContext(fixture.scratch_home(self.base / 'home'))
        self.addCleanup(runtime.configure_pack_runtime, None)
        case = fixtures.create(self.base / 'studio', self.base / 'runtime')
        self.root, self.settings = case['root'], case['settings']
        authority = c.load(self.root / 'fixture-authority.json')
        authority['grants'][0]['targets'].append('canon:catalog')
        fixtures.write(self.root / 'fixture-authority.json', authority)
        task = case['task']
        task['recording'].update(slot='base.front', sheet_panel=True, subject_map={'robot': 'robot'})
        task['generation']['continuity']['robot'] = 'undecided'
        fixtures.write(self.root / 'task.json', task)
        self.run = workflow.prepare(self.root, 'task.json')['run']
        output = execution.execute(self.root, self.run, decisions_file=decisions(self.root, self.run))
        self.candidate = output['runs'][0]['candidates'][0]
        self.row = studio.read_iterations(studio.character_home(self.root, 'robot'))[0]
        review = workflow.draft_review(self.root, self.run, self.candidate)
        review.update(reviewer='Synthetic test reviewer', observations=[{
            'evidence': 'candidate', 'locator': {'kind': 'whole'},
            'observation': 'A real local synthetic PNG was captured.',
            'interpretation': 'Protocol fixture only.',
            'limitations': ['No generative quality or user approval is asserted.']}],
            conclusion='Synthetic test decision.')
        for check in review['checks']:
            check.update(verdict='pass', observation_indices=[0], reason='Explicit synthetic fixture assessment.')
        fixtures.write(self.root / 'review.json', review)
        workflow.review(self.root, self.run, 'review.json')
        selection = workflow.draft_selection(self.root, self.run, self.candidate)
        selection['reason'] = 'Explicit synthetic selection for later reference adoption.'
        fixture.selection(self.root, self.run, selection)
        fixtures.write(self.root / 'selection.json', selection)
        workflow.select(self.root, self.run, 'selection.json')
        fixtures.write(self.root / 'adoption-basis.txt', 'Explicit synthetic author decision. Not user consent.')
        self.approval = {'scope': 'sheet', 'influence': 'identity', 'character': 'robot',
            'iteration_id': self.row['iteration_id'], 'slot': self.row['slot'],
            'image_sha256': self.row['result']['sha256'], 'by': fixture.ACTOR, 'at': '2000-01-01T00:00:00Z',
            'continuity_decision': {'character_id': 'robot', 'continuity': 'recurring',
                'basis': file_ref(self.root, 'adoption-basis.txt', locator='whole'),
                'by': fixture.ACTOR, 'at': '2000-01-01T00:00:00Z'}}
        fixtures.write(self.root / 'sheet-approval.json', self.approval)
        intent = workflow.adoption_intent(self.root, self.run, self.candidate,
            'robot', self.row['iteration_id'], self.approval)
        token = fixture.grant(self.root, self.run, intent)
        workflow.adopt(self.root, self.run, self.candidate, 'robot', self.row['iteration_id'],
            'sheet-approval.json', token)
        self.sheet = self.root / 'characters/robot/sheet/sheet-data.json'
        self.journal = adoption._journal_path(studio.character_home(self.root, 'robot'), self.row['iteration_id'])
        self.initial_journal = c.load(self.journal)
        self.source = sr.current_source(self.root, 'robot', 'base.front')
        self.record = {'id': 'adopted-test-character', 'label': 'Adopted fixture',
            'curation_status': 'curated', 'category': 'species', 'prompt': 'a fictional test character',
            'domains': ['shared'], 'tags': ['fixture', 'character'],
            'search_terms': [{'phrase': 'adopted test character', 'facet': 'species', 'weight': 1.0, 'source': 'author'}],
            'scaffold': {'family': 'direct-geometry-required', 'confidence': 'fallback'}}
        self.catalog_approval = {**self.approval, 'scope': 'catalog', 'registration_record_sha256': digest(self.record)}
        self.pack = self.base / 'registered-pack'
        fixtures.write(self.root / 'catalog-approval.json', self.catalog_approval)

    def promotion_authorization(self):
        import production_fixtures as fixture
        import production_workflow as workflow
        intent = workflow.adoption_intent(self.root, self.run, self.candidate,
            'robot', self.row['iteration_id'], self.catalog_approval,
            registration_record=self.record, pack_dir=self.pack)
        return fixture.grant(self.root, self.run, intent)

    def promote(self, token=None):
        import production_workflow as workflow
        return workflow.adopt(self.root, self.run, self.candidate, 'robot', self.row['iteration_id'],
            'catalog-approval.json', token or self.promotion_authorization(),
            registration_record=self.record, pack_dir=self.pack, settings=self.settings)

    def test_catalog_promotion_preserves_sheet_acceptance_and_yields_current_reference(self):
        current = c.load(self.sheet)['slots']['base.front']['current']
        companion = self.base / 'before-promotion.references'
        sr.archive_source(self.source, companion)
        self.promote()
        source = sr.current_source(self.root, 'robot', 'base.front')
        proof = sr.identity_source(source, root=self.root, character_id='robot')
        self.assertEqual(c.load(self.sheet)['slots']['base.front']['current'], current)
        self.assertEqual(c.load(self.journal)['sheet_decision'], self.initial_journal['sheet_decision'])
        self.assertEqual(source['artifact_id'], self.source['artifact_id'])
        self.assertEqual(source['acceptance_sha256'], self.source['acceptance_sha256'])
        self.assertNotEqual(source['proof_sha256'], self.source['proof_sha256'])
        self.assertEqual(proof['adoption']['approval'], self.catalog_approval)
        with self.assertRaisesRegex(ValueError, 'no longer matches'):
            sr.validate_source(self.source)
        prior = sr.validate_source(self.source, active=False, source_archive=companion / 'sources')
        self.assertEqual(prior['adoption']['approval'], self.approval)

    def test_promoted_reference_requires_both_original_decision_and_current_claim(self):
        self.promote()
        journal = c.load(self.journal)
        altered_decision = copy.deepcopy(journal['sheet_decision'])
        altered_decision['reason'] = 'Another decision cannot replace the recorded sheet acceptance.'
        changes = [
            {'sheet_decision': altered_decision},
            {'production_claim': self.initial_journal['production_claim']},
            {'approval': {**journal['approval'], 'by': 'Another approver'}},
            {'approval': {**journal['approval'], 'influence': 'outfit'}},
            {'approval': {**journal['approval'], 'iteration_id': 'another-iteration'}},
            {'approval': {**journal['approval'], 'image_sha256': '0' * 64}},
            {'status': 'sheet-bound'},
        ]
        for change in changes:
            with self.subTest(change=change):
                c.atomic_write_json(self.journal, {**journal, **change})
                with self.assertRaises(ValueError):
                    sr.current_source(self.root, 'robot', 'base.front')
        c.atomic_write_json(self.journal, journal)
        sr.validate_source(sr.current_source(self.root, 'robot', 'base.front'))

    def test_cli_reports_a_damaged_adoption_record_with_its_restoring_command(self):
        import contextlib, io
        self.journal.unlink()
        target = self.base / 'source.json'
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            code = sr.main(['--studio', str(self.root), '--character', 'robot', '--slot', 'base.front',
                            'source', '--out', str(target)])
        report = json.loads(printed.getvalue())
        self.assertEqual(code, 2)
        self.assertFalse(report['ok'])
        diagnostic = report['diagnostics'][0]
        self.assertEqual(diagnostic['code'], 'ADOPTION_RECORD_CORRUPT')
        self.assertEqual(diagnostic['file'], 'characters/robot/adoptions/' + self.row['iteration_id'] + '.json')
        self.assertIn('production_workflow.py adopt --run ' + self.run, diagnostic['required_action'])
        self.assertFalse(target.exists())
        import production_edit_inputs
        from production_diagnostics import ProductionError
        with self.assertRaises(ProductionError) as caught:
            production_edit_inputs.select(self.root, 'robot', 'base.front')
        self.assertEqual(caught.exception.diagnostic.code, 'ADOPTION_RECORD_CORRUPT')

    def test_catalog_reference_waits_for_its_completed_result_and_resumes_same_claim(self):
        import production_workflow as workflow
        import adoption_workflow as adoption
        token = self.promotion_authorization()
        append = workflow.append_record
        def interrupted(*args, **kwargs):
            if args[3] == 'adoption-result':
                raise OSError('Synthetic interruption before recording the catalog adoption result.')
            return append(*args, **kwargs)
        with patch.object(workflow, 'append_record', side_effect=interrupted):
            with self.assertRaises(OSError):
                self.promote(token)
        with self.assertRaisesRegex(ValueError, 'ADOPTION_RESULT_MISSING'):
            sr.current_source(self.root, 'robot', 'base.front')
        index = adoption.reference_index(self.root, 'robot')
        self.assertFalse(index['ok'])
        self.assertEqual(index['bindings'][0]['next_action'], 'record-adoption-result')
        self.assertTrue(index['bindings'][0]['adoption']['source_ready'])
        with self.assertRaisesRegex(ValueError, 'reference workflow is incomplete'):
            adoption.supplied_selection(self.root, 'robot')
        claim = c.load(self.journal)['production_claim']
        self.promote(token)
        self.assertEqual(c.load(self.journal)['production_claim'], claim)
        sr.validate_source(sr.current_source(self.root, 'robot', 'base.front'))
        index = adoption.reference_index(self.root, 'robot')
        self.assertTrue(index['ok'])
        self.assertIsNone(index['bindings'][0]['next_action'])
        self.assertEqual(c.load(self.sheet.parent / 'active-references.json'), index)


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    with tempfile.TemporaryDirectory(prefix='cpb-source-test-home-') as home:
        scratch_home_dir(Path(home))
        unittest.main()
