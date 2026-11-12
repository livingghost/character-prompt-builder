"""Retarget exact external requests while retaining applicable authored evidence."""
from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import execution_contract as c
from catalog_retrieval.runtime import configure_pack_runtime
import production_fixtures as fixtures
import production_inputs as inputs
import production_store as store
import production_variation as variation
import production_workflow as workflow
from production_diagnostics import ProductionError
from semantic_edit_plan_smoke_test import PROMPT, TARGET, setup_plan, write
import transport_synthetic
import work_ledger


class ExternalRetargetTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='external-retarget-')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.root = self.base / 'studio'
        self.enterContext(fixtures.scratch_home(self.base / 'home'))
        configure_pack_runtime(None)
        self.addCleanup(configure_pack_runtime, None)
        self.enterContext(patch.object(transport_synthetic, 'send',
            side_effect=AssertionError('External retarget preparation must not send a request.')))
        self.plan = setup_plan(self.root)
        work = work_ledger.begin(self.root, 'Synthetic external retarget comparison', ['prepare', 'review'])
        write(self.root, 'brief.md', b'Preserve the vase geometry and camera framing; change only the wall color.\n')
        write(self.root, 'author-notes.json', {'author_note': 'Keep this original artistic choice.',
            'mentioned_model': TARGET['model_identifier']})
        task = {'task_id': work['task_id'], 'route': 'generation',
            'features': ['semantic-instruction-edit', 'instruction-edit'],
            'sources': [
                {'id': 'brief', 'path': 'brief.md', 'role': 'design', 'disposition': 'applied',
                    'locator': 'whole', 'reason': 'The synthetic authored commission supplies the preservation scope.'},
                {'id': 'model-card', 'path': 'author-notes.json', 'role': 'design', 'disposition': 'applied',
                    'locator': 'whole', 'reason': 'The source identifier does not make author notes generated target guidance.'},
                {'id': 'scene', 'path': 'scene.png', 'role': 'accepted-source', 'disposition': 'applied',
                    'locator': 'whole', 'reason': 'The synthetic scene supplies the camera framing.'},
                {'id': 'design', 'path': 'design.png', 'role': 'reference-images', 'disposition': 'applied',
                    'locator': 'whole', 'reason': 'The synthetic construction image supplies the vase geometry.'}],
            'delivery': {'path': 'prompt.txt', 'translation_notes': 'Retain the exact authored external instruction.'},
            'criteria': [{'id': 'wall', 'strength': 'hard', 'text': 'Inspect the requested wall color change.'},
                         {'id': 'geometry', 'strength': 'hard', 'text': 'Inspect the preserved vase geometry.'}],
            'world_views': [], 'semantic_edit': 'edit-plan.json', 'image_input': 'image-input.json'}
        fixtures.task(self.root, task, artifact='image', execution='external')
        for criterion in task['criteria']:
            criterion['evidence'] = 'image'
        task['direction'].update(purpose='Retain the authored edit and preservation scope across the interface choice.',
            basis=['brief'], decisions=[{
                'id': 'expression', 'question': 'Which depiction should be carried forward?', 'importance': 'material',
                'basis': ['brief'], 'options': [
                    {'id': 'preserve-scene', 'expression': 'Preserve the existing scene and object geometry.',
                        'realization': {'method': 'authored instruction', 'instructions': PROMPT,
                            'capability_source': None, 'limitations': ['Synthetic fixture only.']},
                        'tradeoffs': ['Requires the accepted scene and construction reference.']},
                    {'id': 'recompose', 'expression': 'Recompose the room around the same vase.',
                        'realization': {'method': 'authored instruction', 'instructions': 'Recompose the room.',
                            'capability_source': None, 'limitations': ['Outside the selected preservation scope.']},
                        'tradeoffs': ['Would change the camera framing.']}],
                'selected': 'preserve-scene', 'reason': 'The synthetic commission fixes the framing.',
                'criteria': ['wall', 'geometry'], 'depends_on': [], 'deviations': []}])
        write(self.root, 'task.json', task)
        self.task = task
        self.parent = workflow.prepare(self.root, 'task.json')
        self.run = self.parent['run']
        self.loaded = workflow.read_run(self.root, self.run)

    def draft(self):
        result = inputs.draft_inputs(self.root, None, 'edit', from_run=self.run)
        self.assertEqual(result['unresolved'], [], result)
        return result['choices_file'], c.load(self.root / result['choices_file'])

    def choose(self, choices, *, model=None, operation=None):
        selected = choices['target']['model']
        selected['requested'] = 'Explicit alternate synthetic external interface'
        if model is not None:
            selected['target']['model_identifier'] = model
        if operation is not None:
            selected['target']['operation'] = operation
        write(self.root, 'alternate-model-evidence.json', {'synthetic': True,
            'offered_target': selected['target'],
            'statement': 'This fixture explicitly declares the same native fields and references for the selected target.'})
        selected['evidence'] = {'path': 'alternate-model-evidence.json', 'locator': 'whole synthetic interface declaration'}

    def test_saved_external_target_switch_preserves_authored_sources_criteria_and_upload_evidence(self):
        parent_files = {path.relative_to(self.loaded.directory).as_posix(): path.read_bytes()
            for path in self.loaded.directory.rglob('*') if path.is_file()}
        choices_path, choices = self.draft()
        inherited = copy.deepcopy(choices)
        self.choose(choices, model='vendor:example-editor@2')
        write(self.root, choices_path, choices)
        result = variation.retarget(self.root, self.run, choices=choices_path,
            reason='Synthetic explicit comparison of external model editions.', prepare=True)
        child = workflow.read_run(self.root, result['run'])
        request = child.artifacts['execution-plan.json']['request']
        self.assertEqual(request['model'], 'vendor:example-editor@2')
        self.assertEqual(request['operation'], TARGET['operation'])
        self.assertEqual(request['prompt'], PROMPT)
        self.assertEqual(request['images'], ['synthetic-scene', 'synthetic-design'])
        self.assertEqual(child.prepared['task']['criteria'], self.task['criteria'])
        self.assertEqual(child.prepared['task']['direction'], self.task['direction'])
        self.assertEqual(child.prepared['authority']['grants'], self.loaded.prepared['authority']['grants'])
        old_references = self.loaded.consumer['image_input']['references']
        references = child.consumer['image_input']['references']
        self.assertEqual(len(references), len(old_references))
        for reference, original in zip(references, old_references, strict=True):
            self.assertEqual({key: value for key, value in reference.items() if key != 'file'},
                             {key: value for key, value in original.items() if key != 'file'})
            self.assertNotEqual(reference['file'], original['file'])
            source = self.loaded.evidence.read(original['sha256'])
            self.assertEqual((self.root / reference['file']).read_bytes(), source)
            self.assertEqual(child.evidence.read(reference['sha256']), source)
        old_fields = self.loaded.consumer['image_input']['external_request']['reference_fields']
        fields = child.consumer['image_input']['external_request']['reference_fields']
        self.assertEqual(len(fields), len(old_fields))
        for field, original in zip(fields, old_fields, strict=True):
            self.assertEqual({key: value for key, value in field.items() if key != 'evidence'},
                             {key: value for key, value in original.items() if key != 'evidence'})
            evidence, old_evidence = field['evidence'], original['evidence']
            self.assertEqual({key: value for key, value in evidence.items() if key != 'path'},
                             {key: value for key, value in old_evidence.items() if key != 'path'})
            self.assertNotEqual(evidence['path'], old_evidence['path'])
            upload = self.loaded.evidence.read(old_evidence['sha256'])
            self.assertEqual((self.root / evidence['path']).read_bytes(), upload)
            self.assertEqual(child.evidence.read(evidence['sha256']), upload)
        self.assertEqual(child.consumer['semantic_edit']['edit'], self.loaded.consumer['semantic_edit']['edit'])
        self.assertEqual(inherited['authoring']['sources']['model-card'], choices['authoring']['sources']['model-card'])
        sources = {row['id']: row for row in child.prepared['task']['sources']}
        notes = c.load(self.root / sources['model-card']['path'])
        self.assertEqual(notes, {'author_note': 'Keep this original artistic choice.',
            'mentioned_model': TARGET['model_identifier']})
        lineage = child.prepared['parent']
        self.assertEqual((lineage['kind'], lineage['run']), ('retarget', self.run))
        self.assertEqual(lineage['input_sha256'], self.loaded.prepared['input_sha256'])
        self.assertEqual(lineage['request_sha256'], self.loaded.artifacts['execution-plan.json']['request_sha256'])
        self.assertFalse(result['authorization_inherited'])
        self.assertFalse(result['external_effect'])
        self.assertEqual(store.event_rows(self.root, self.run), [])
        self.assertEqual(store.event_rows(self.root, result['run']), [])
        self.assertEqual(parent_files, {path.relative_to(self.loaded.directory).as_posix(): path.read_bytes()
            for path in self.loaded.directory.rglob('*') if path.is_file()})
        self.assertEqual(c.load(self.root / 'request.json')['model'], TARGET['model_identifier'])
        self.assertEqual(c.load(self.root / 'image-input.json')['model'], self.plan['model'])

    def test_external_operation_is_part_of_the_target(self):
        choices_path, choices = self.draft()
        self.choose(choices, operation='instruction-edit')
        write(self.root, choices_path, choices)
        result = variation.retarget(self.root, self.run, choices=choices_path,
            reason='Synthetic explicit operation change on the same external model.', prepare=True)
        child = workflow.read_run(self.root, result['run'])
        self.assertEqual(child.artifacts['execution-plan.json']['request']['operation'], 'instruction-edit')
        self.assertEqual(child.prepared['parent']['changes'][0]['field'], 'target')
        self.assertEqual(child.prepared['parent']['changes'][0]['after']['operation'], 'instruction-edit')
        self.assertEqual(store.event_rows(self.root, result['run']), [])

    def test_same_external_target_has_no_retarget_transition(self):
        choices_path, _ = self.draft()
        with self.assertRaises(ProductionError) as caught:
            variation.retarget(self.root, self.run, choices=choices_path,
                reason='Synthetic unchanged target check.', prepare=True)
        self.assertEqual(caught.exception.diagnostic.code, 'RETARGET_NO_OP')
        self.assertEqual(len(store.runs(self.root)), 1)
        self.assertEqual(store.event_rows(self.root, self.run), [])


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main(verbosity=2)
