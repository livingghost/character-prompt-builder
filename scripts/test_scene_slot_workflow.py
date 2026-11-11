"""Retained-result curation across Production, Studio, adoption and edit sources.

All images and author decisions are synthetic local fixtures. These tests judge
workflow integrity, not image quality or actual user consent.
"""
from __future__ import annotations

import copy
from unittest.mock import patch

import adoption_workflow
import execution_contract as c
import production_acceptance as acceptance
import production_case_fixtures as fixtures
import production_edit_inputs
import production_fixtures as fixture
import production_store as store
import production_workflow as workflow
import sheet_artifacts as fills
import studio
import studio_gallery
import studio_placement
import studio_reference
import transport_synthetic
import validate_studio
from test_production_review import ReviewCase


class SceneSlotWorkflowTests(ReviewCase):
    def move(self, destination: str) -> dict:
        decision = studio_placement.draft(self.root, 'robot', self.iteration, destination)
        decision.update(by=fixture.ACTOR, at='2000-01-02T00:00:00Z',
                        reason='Synthetic author places the retained result in its intended scene.')
        result = studio_placement.reassign(self.root, decision)
        self.assertTrue(result['ok'])
        self.assertEqual(result['current_slot'], destination)
        return decision

    def adopt_scene(self, label: str) -> tuple[dict, str]:
        approval = adoption_workflow.draft_approval(
            self.root, 'robot', self.iteration, scope='sheet', influence='pose-camera')
        approval.update(by=fixture.ACTOR, at='2000-01-03T00:00:00Z',
                        note='Synthetic author adopts this exact scene: ' + label)
        path = 'approval-' + label + '.json'
        fixtures.write(self.root / path, approval)
        token = fixture.grant(self.root, self.run, workflow.adoption_intent(
            self.root, self.run, self.candidate, 'robot', self.iteration, approval))
        workflow.adopt(self.root, self.run, self.candidate, 'robot', self.iteration, path, token)
        return approval, token

    def withdraw(self, slot: str) -> dict:
        sidecar = self.home / 'sheet/sheet-data.json'
        decision = fills.draft_withdrawal(sidecar, slot)
        evidence = self.root / 'withdrawal-authority.txt'
        fixtures.write(evidence, 'Synthetic author ends this exact canonical scene adoption. Not user consent.')
        decision.update(by=fixture.ACTOR, at='2000-01-04T00:00:00Z',
                        reason='Synthetic author corrects the scene placement.',
                        evidence={'path': evidence.name, 'sha256': c.sha256_file(evidence), 'locator': 'whole'})
        fills.withdraw(sidecar, decision, evidence_root=self.root)
        return decision

    def test_selected_candidate_is_placed_and_adopted_without_recreating_production(self):
        review = self.record_review([('output', 'pass'), ('palette', 'pass')])
        selection = self.select()
        original = self.row(self.candidate)
        prepared = workflow.read_run(self.root, self.run).prepared
        initial_events = store.event_rows(self.root, self.run)
        with patch.object(transport_synthetic, 'send', side_effect=AssertionError('Curation must not send')):
            self.move('scene.result')
            self.adopt_scene('result')
            workflow.complete(self.root, self.run)
        row = self.row(self.candidate)
        self.assertEqual((row['slot'], studio.placement_slot(row)), ('candidate', 'scene.result'))
        self.assertEqual(row['result'], original['result'])
        self.assertEqual(row['production'], original['production'])
        self.assertEqual(workflow.read_run(self.root, self.run).prepared, prepared)
        self.assertEqual(workflow.latest_review(store.event_rows(self.root, self.run), self.candidate), review)
        after = store.event_rows(self.root, self.run)
        self.assertEqual(after[:len(initial_events)], initial_events)
        self.assertEqual([event['sha256'] for event in after if event['event'] == 'selection'], [selection['sha256']])
        source = studio_reference.current_source(self.root, 'robot', 'scene.result')
        self.assertEqual(source['sha256'], row['result']['sha256'])
        entry = next(item for item in studio_gallery.build_index(self.root)['entries']
                     if item['entry_id'] == 'robot/' + self.iteration)
        self.assertEqual((entry['slot'], entry['recorded_slot']), ('scene.result', 'candidate'))
        self.assertEqual(validate_studio.validate(self.root), [])

    def test_completed_acceptance_survives_withdraw_move_and_fresh_adoption(self):
        self.record_review([('output', 'pass'), ('palette', 'pass')])
        decision = acceptance.draft(self.root, self.run, self.candidate, 'fixture-grant', scope='studio-slot')
        decision['reason'] = 'Synthetic author accepts this retained result.'
        fixtures.write(self.root / 'acceptance.json', decision)
        done = acceptance.accept(self.root, self.run, decision_file='acceptance.json')
        original = self.row(self.candidate)
        initial_source = studio_reference.current_accepted_source(self.root, 'robot', 'candidate')
        accepted_archive = self.root / 'accepted-source-proof'
        studio_reference.archive_source(initial_source, accepted_archive)
        edit = production_edit_inputs.select(self.root, 'robot', 'candidate')
        self.assertEqual(edit['source']['kind'], 'studio-accepted-image')
        self.assertIsNone(edit['identity'])
        with patch.object(transport_synthetic, 'send', side_effect=AssertionError('Curation must not send')):
            first_move = self.move('scene.first')
            self.adopt_scene('first')
            old_canon = studio_reference.current_source(self.root, 'robot', 'scene.first')
            canon_archive = self.root / 'canonical-source-proof'
            studio_reference.archive_source(old_canon, canon_archive)
            self.withdraw('scene.first')
            self.assertEqual(studio.acceptance_state(self.root, 'robot', 'scene.first')['iteration_id'], self.iteration)
            self.move('scene.final')
            self.adopt_scene('final')
            replay = studio_placement.reassign(self.root, first_move)
            self.assertFalse(replay['current'])
        self.assertEqual(studio.placement_slot(self.row(self.candidate)), 'scene.final')
        self.assertEqual(self.row(self.candidate)['result'], original['result'])
        self.assertEqual(workflow.verify_completion(self.root, self.run, done['task_id'])['sha256'], done['completion'])
        self.assertIsNone(studio.acceptance_state(self.root, 'robot', 'candidate'))
        self.assertIsNone(studio.acceptance_state(self.root, 'robot', 'scene.first'))
        with self.assertRaises(ValueError):
            studio_reference.validate_source(initial_source)
        with self.assertRaises(ValueError):
            studio_reference.validate_source(old_canon)
        studio_reference.validate_source(initial_source, active=False, source_archive=accepted_archive / 'sources')
        studio_reference.validate_source(old_canon, active=False, source_archive=canon_archive / 'sources')
        current = studio_reference.current_source(self.root, 'robot', 'scene.final')
        self.assertEqual(current['sha256'], original['result']['sha256'])
        self.assertNotEqual(current['proof_sha256'], old_canon['proof_sha256'])
        self.assertEqual(validate_studio.validate(self.root), [])

    def test_completed_canonical_scope_keeps_its_recorded_placement_chain(self):
        self.record_review([('output', 'pass'), ('palette', 'pass')])
        self.select()
        self.move('scene.original')
        self.adopt_scene('original')
        choice = workflow.draft_selection(self.root, self.run, self.candidate)
        choice.update(reason='Synthetic author completes the adopted scene delivery.', scope='studio-adoption',
                      adoption={'character': 'robot', 'iteration_id': self.iteration, 'scope': 'sheet'})
        fixture.selection(self.root, self.run, choice)
        fixtures.write(self.root / 'canonical-selection.json', choice)
        selected = workflow.select(self.root, self.run, 'canonical-selection.json')
        done = workflow.complete(self.root, self.run)
        retained = c.encoded(selected)
        self.assertEqual(len(selected['data']['studio_placement']), 1)
        with patch.object(transport_synthetic, 'send', side_effect=AssertionError('Curation must not send')):
            self.withdraw('scene.original')
            self.move('scene.later')
            self.adopt_scene('later')
        self.assertEqual(len(store.event_rows(self.root, studio_placement.scope('robot'))), 2)
        self.assertEqual(workflow.verify_completion(self.root, self.run, self.case['task']['task_id']), done)
        actual = workflow.find(store.event_rows(self.root, self.run), 'selection', selected['sha256'])
        self.assertEqual(c.encoded(actual), retained)
        self.assertEqual(studio.placement_slot(self.row(self.candidate)), 'scene.later')
        self.assertEqual(validate_studio.validate(self.root), [])

    def test_accepted_proof_binds_the_selection_named_by_its_receipt(self):
        self.record_review([('output', 'pass'), ('palette', 'pass')])
        decision = acceptance.draft(self.root, self.run, self.candidate, 'fixture-grant', scope='studio-slot')
        decision['reason'] = 'Synthetic author accepts this exact selection.'
        fixtures.write(self.root / 'acceptance.json', decision)
        acceptance.accept(self.root, self.run, decision_file='acceptance.json')
        source = studio_reference.current_accepted_source(self.root, 'robot', 'candidate')
        companion = self.root / 'accepted-source-proof'
        studio_reference.archive_source(source, companion)
        folder = companion / 'studio' / source['proof_sha256']
        proof = c.load(folder / 'proof.json')
        replacement = copy.deepcopy(proof['production']['selection'])
        replacement['data']['selection']['reason'] = 'A different selection, not the acceptance receipt.'
        replacement['sha256'] = c.content_id({key: value for key, value in replacement.items() if key != 'sha256'})
        proof['production']['selection'] = replacement
        fixtures.write(folder / 'proof.json', proof)
        altered = {**source, 'proof_sha256': c.content_id(proof)}
        folder.rename(companion / 'studio' / altered['proof_sha256'])
        with self.assertRaisesRegex(ValueError, 'selection differs from its acceptance receipt'):
            studio_reference.validate_source(altered, active=False, source_archive=companion / 'sources')


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    import unittest
    unittest.main()
