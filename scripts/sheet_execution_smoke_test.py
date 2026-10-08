#!/usr/bin/env python3
"""Accepted-source freshness and model derivation through synthetic Production."""
from __future__ import annotations
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import execution_contract as c
import production_case_fixtures as fixture
import production_workflow as workflow
import production_execution as execution
import sheet_artifacts as fills
from sheet_artifacts_smoke_test import accepted, make_artifact, decision


class SheetExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.case = fixture.create(base / 'studio', base / 'runtime', with_upscale=True)
        self.root = self.case['root']; self.sheet = self.root / 'characters/robot/sheet/sheet-data.json'

    def test_candidate_changes_do_not_stale_the_accepted_source(self):
        accepted(self.sheet)
        task = c.load(self.root / 'task.json')
        task['sources'][0]['path'] = self.sheet.relative_to(self.root).as_posix()
        fixture.write(self.root / 'task.json', task)
        run = workflow.prepare(self.root, 'task.json')['run']
        other = make_artifact(self.sheet, marker='redo')
        fills.register_candidates(self.sheet, [('canon.primary', other)])
        workflow.assert_current(self.root, run)
        directory, prepared, _, _ = workflow.load_run(self.root, run)
        dependency = next(row for row in prepared['dependencies'] if row['path'] == task['sources'][0]['path'])
        self.assertNotEqual(dependency['sha256'], c.sha256_file(self.sheet))
        self.assertEqual(c.digest(c.object_read(directory, dependency['sha256'])), dependency['sha256'])
        fills.adopt(self.sheet, decision(self.sheet, 'canon.primary', other), evidence_root=self.sheet.parent)
        with self.assertRaises(ValueError): workflow.assert_current(self.root, run)

    def test_cropped_source_model_upscale_retains_full_lineage(self):
        original = accepted(self.sheet, size=(32, 32))
        crop = fills.crop(self.sheet, 'canon.primary', 'parts.detail', [0, 0, 16, 16])
        source = (self.sheet.parent / crop['image']['path']).relative_to(self.root).as_posix()
        path = fixture.upscale_task(self.root, source=source, scale=4)
        task = c.load(self.root / path)
        task['upscale']['derivation'] = {'sheet': self.sheet.relative_to(self.root).as_posix(),
                                        'slot': 'parts.detail', 'artifact_id': crop['artifact_id']}
        task['recording'].update(slot='parts.detail', sheet_panel=True, subject_map={'robot':'robot'})
        fixture.write(self.root / path, task)
        run = workflow.prepare(self.root, path)['run']
        approved = fixture.fill_decisions(self.root, run, 'upscale-approved.json')
        result = execution.execute(self.root, run, decisions_file=approved)
        self.assertTrue(result['execution_completed'], result)
        candidates = c.load(self.sheet)['slots']['parts.detail']['candidates']
        final = next(row for row in candidates if row['provenance']['kind'] == 'upscale')
        provenance = fills.verify_artifact(final, self.sheet.parent)
        self.assertEqual(provenance['sources'], [crop])
        self.assertEqual(provenance['recipe']['scale_factor'], 4)
        self.assertEqual(fills.verify_artifact(crop, self.sheet.parent)['sources'], [original])
        self.assertEqual((final['image']['width'], final['image']['height']), (64, 64))
        import transport_synthetic
        with patch.object(transport_synthetic, 'send', side_effect=AssertionError('no repeat')):
            execution.resume(self.root, run)
        self.assertIsNone(c.load(self.sheet)['slots']['parts.detail']['current'])


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
