"""Placement corrections preserve retained work, decisions and recoverability."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import copy
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
import execution_contract as c
import production_store as store
import studio
import studio_placement as placement
import validate_studio
from production_diagnostics import ProductionError


class PlacementTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = studio.init(Path(self.temporary.name) / 'studio', 'placement-fixture', 'Synthetic placement decisions')
        self.home = studio.add_character(self.root, 'robot', 'general')
        image = io.BytesIO()
        Image.new('RGB', (8, 8), (40, 100, 170)).save(image, 'PNG')
        self.image = self.root / 'image.png'
        c.atomic(self.image, image.getvalue())

    def iteration(self, slot='candidate'):
        return studio.iterate(self.root, 'robot', slot, self.image, package=None, request=None,
                              response=None, note='Synthetic fixture only.')

    def decision(self, row, destination):
        value = placement.draft(self.root, 'robot', row['iteration_id'], destination)
        value.update(by='Synthetic fixture curator', at='2026-11-11T00:00:00Z',
                     reason='Synthetic placement correction: retain the exact image.')
        return value

    def row(self, identifier):
        return studio._find(studio.read_iterations(self.home), identifier)

    def test_candidate_moves_without_rewriting_origin_or_equal_byte_sibling(self):
        first, second = self.iteration(), self.iteration()
        recorded = (self.home / 'iterations.jsonl').read_bytes()
        result = placement.reassign(self.root, self.decision(first, 'scene.arrival'))
        self.assertEqual((self.home / 'iterations.jsonl').read_bytes(), recorded)
        self.assertEqual(studio.placement_slot(self.row(first['iteration_id'])), 'scene.arrival')
        self.assertEqual(studio.placement_slot(self.row(second['iteration_id'])), 'candidate')
        self.assertEqual(self.row(first['iteration_id'])['slot'], 'candidate')
        self.assertEqual(result['image_sha256'], first['result']['sha256'])
        self.assertEqual(len(studio.read_iteration_records(self.home)), 2)
        self.assertIsNone(studio.acceptance_state(self.root, 'robot', 'scene.arrival'))
        gallery = c.load(self.root / 'gallery.json')['entries']
        self.assertEqual(next(item for item in gallery if item['iteration_id'] == first['iteration_id'])['slot'], 'scene.arrival')

    def test_accepted_move_replaces_destination_and_keeps_both_histories(self):
        first, other = self.iteration('scene.first'), self.iteration('scene.second')
        studio.accept(self.root, 'robot', first['iteration_id'])
        studio.accept(self.root, 'robot', other['iteration_id'])
        first_receipt = copy.deepcopy(self.row(first['iteration_id'])['acceptances'][0])
        result = placement.reassign(self.root, self.decision(first, 'scene.second'))
        self.assertTrue(result['acceptance_current'])
        self.assertIsNone(studio.acceptance_state(self.root, 'robot', 'scene.first'))
        self.assertEqual(studio.acceptance_state(self.root, 'robot', 'scene.second')['iteration_id'], first['iteration_id'])
        moved, replaced = self.row(first['iteration_id']), self.row(other['iteration_id'])
        self.assertEqual(moved['slot'], 'scene.first')
        self.assertEqual(moved['acceptances'][0], first_receipt)
        self.assertEqual(moved['acceptances'][-1]['supersedes'], other['iteration_id'])
        self.assertEqual(replaced['status'], 'superseded')
        studio.verify_accepted_file(self.root, moved)
        self.assertFalse((self.home / 'accepted/scene.first.png').exists())
        self.assertEqual(validate_studio.validate(self.root), [])

    def test_stale_source_and_destination_decisions_make_no_event(self):
        row, other = self.iteration(), self.iteration('scene.destination')
        value = self.decision(row, 'scene.destination')
        studio.accept(self.root, 'robot', other['iteration_id'])
        with self.assertRaises(ProductionError) as caught:
            placement.reassign(self.root, value)
        self.assertEqual(caught.exception.diagnostic.code, 'PLACEMENT_CONFLICT')
        self.assertEqual(store.event_rows(self.root, placement.scope('robot')), [])
        new = self.decision(row, 'scene.destination')
        placement.reassign(self.root, self.decision(row, 'scene.third'))
        with self.assertRaises(ProductionError):
            placement.reassign(self.root, new)
        self.assertEqual(studio.placement_slot(self.row(row['iteration_id'])), 'scene.third')

    def test_two_competing_decisions_have_one_committed_destination(self):
        row = self.iteration()
        choices = [self.decision(row, 'scene.one'), self.decision(row, 'scene.two')]
        def apply(choice):
            try:
                return placement.reassign(self.root, choice)['current_slot']
            except ProductionError as exc:
                return exc.diagnostic.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(apply, choices))
        self.assertEqual(results.count('PLACEMENT_CONFLICT'), 1)
        self.assertEqual(len(store.event_rows(self.root, placement.scope('robot'))), 1)

    def test_interrupted_accepted_copy_replays_and_resumes_exact_receipt(self):
        row = self.iteration('scene.first')
        studio.accept(self.root, 'robot', row['iteration_id'])
        choice = self.decision(row, 'scene.second')
        original = c.atomic
        def fail(target, *args, **kwargs):
            if target == self.home / 'accepted/scene.second.png':
                raise OSError('synthetic copy interruption')
            return original(target, *args, **kwargs)
        with patch.object(c, 'atomic', side_effect=fail), self.assertRaises(ProductionError) as caught:
            placement.reassign(self.root, choice)
        self.assertEqual(caught.exception.diagnostic.code, 'PLACEMENT_PROJECTION_PENDING')
        self.assertEqual(studio.placement_slot(self.row(row['iteration_id'])), 'scene.second')
        result = placement.reassign(self.root, choice)
        self.assertTrue(result['acceptance_current'])
        self.assertEqual(len(self.row(row['iteration_id'])['acceptances']), 2)
        self.assertEqual(len(store.event_rows(self.root, placement.scope('robot'))), 1)
        self.assertEqual(validate_studio.validate(self.root), [])

    def test_later_move_cleans_interrupted_source_without_resurrecting_retry(self):
        row = self.iteration('scene.first')
        studio.accept(self.root, 'robot', row['iteration_id'])
        earlier = self.decision(row, 'scene.second')
        with patch.object(placement, '_publish', side_effect=OSError('synthetic publication interruption')):
            with self.assertRaises(ProductionError):
                placement.reassign(self.root, earlier)
        placement.reassign(self.root, self.decision(row, 'scene.third'))
        self.assertFalse((self.home / 'accepted/scene.first.png').exists())
        self.assertFalse((self.home / 'accepted/scene.second.png').exists())
        before = (self.home / 'iterations.jsonl').read_bytes()
        result = placement.reassign(self.root, earlier)
        self.assertFalse(result['current'])
        self.assertEqual(result['current_slot'], 'scene.third')
        self.assertEqual((self.home / 'iterations.jsonl').read_bytes(), before)
        self.assertEqual(validate_studio.validate(self.root), [])

    def test_later_acceptance_is_not_undone_by_placement_retry(self):
        first, later = self.iteration('scene.first'), self.iteration('scene.second')
        studio.accept(self.root, 'robot', first['iteration_id'])
        decision = self.decision(first, 'scene.second')
        placement.reassign(self.root, decision)
        studio.accept(self.root, 'robot', later['iteration_id'])
        result = placement.reassign(self.root, decision)
        self.assertFalse(result['acceptance_current'])
        self.assertEqual(studio.acceptance_state(self.root, 'robot', 'scene.second')['iteration_id'], later['iteration_id'])
        self.assertEqual(validate_studio.validate(self.root), [])

    def test_retry_cleans_interrupted_source_after_a_later_destination_acceptance(self):
        first, later = self.iteration('scene.first'), self.iteration('scene.second')
        studio.accept(self.root, 'robot', first['iteration_id'])
        choice = self.decision(first, 'scene.second')
        with patch.object(placement, '_publish', side_effect=OSError('synthetic interruption')):
            with self.assertRaises(ProductionError):
                placement.reassign(self.root, choice)
        studio.accept(self.root, 'robot', later['iteration_id'])
        self.assertTrue((self.home / 'accepted/scene.first.png').exists())
        result = placement.reassign(self.root, choice)
        self.assertFalse(result['acceptance_current'])
        self.assertFalse((self.home / 'accepted/scene.first.png').exists())
        self.assertEqual(studio.acceptance_state(self.root, 'robot', 'scene.second')['iteration_id'], later['iteration_id'])

    def test_changed_origin_is_corruption_not_an_implicit_move(self):
        row = self.iteration()
        placement.reassign(self.root, self.decision(row, 'scene.second'))
        records = studio.read_iteration_records(self.home)
        records[0]['slot'] = 'scene.changed'
        studio.write_iterations(self.home, records)
        with self.assertRaises(ProductionError) as caught:
            studio.read_iterations(self.home)
        self.assertEqual(caught.exception.diagnostic.code, 'PLACEMENT_RECORD_CORRUPT')

    def test_new_read_boundary_observes_placement_without_mutating_prior_view(self):
        row = self.iteration()
        read = studio.StudioRead(self.root)
        before = read.placed_iterations('robot')
        placement.reassign(self.root, self.decision(row, 'scene.second'))
        self.assertEqual(studio.placement_slot(before[0]), 'candidate')
        fresh = studio.StudioRead(self.root).placed_iterations('robot')
        self.assertEqual(studio.placement_slot(fresh[0]), 'scene.second')


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
