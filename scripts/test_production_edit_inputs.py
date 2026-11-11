"""An instruction edit of an adopted Studio image starts from one editable draft.

`draft-inputs --edit-character --edit-slot` selects the accepted image with its
adoption evidence and the applicable choices of the run that produced it. The
draft names every edit requirement at once; once the synthetic fixture author
answers them, `prepare --choices` prepares the dispatcher or external request
without hand-written derived records. No provider is contacted, and no image
quality or user approval is asserted.
"""
from __future__ import annotations

import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import execution_contract as c
import production_case_fixtures as cases
import production_fixtures as fixture
import production_inputs
import production_workflow as workflow
import work_ledger
from production_diagnostics import DEFAULT_ACTION, ProductionError
from test_production_choice_reports import ChoiceReports

GOAL = 'Replace the plain background of the adopted robot image with a pale green wall.'
PROMPT = ('Edit the supplied image: replace the plain background behind the robot with a pale green wall. '
          'Keep the robot, its pose, its framing and its flat graphic finish unchanged.')
EDIT_FIELDS = ['task_changes.semantic_edit.' + part for part in
               ('edit.target', 'edit.change', 'edit.preserve', 'review_criteria')]


class AdoptedImageEditTests(ChoiceReports, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='cpb-edit-inputs-')
        cls.addClassCleanup(cls.temp.cleanup)
        base = Path(cls.temp.name)
        cls.enterClassContext(fixture.scratch_home(base / 'home'))
        cls.enterClassContext(patch.dict(os.environ, {'CPB_READS_LEDGER': str(base / 'studio/work/reads.jsonl')}))
        from catalog_retrieval import runtime
        cls.addClassCleanup(runtime.configure_pack_runtime, None)
        cls.case = cases.adopted_case(base / 'studio', base / 'runtime')
        cls.root = cls.case['root']

    def setUp(self):
        from catalog_retrieval import runtime
        runtime.configure_pack_runtime(self.case['settings'])
        self.addCleanup(self.close_work)

    def close_work(self):
        if work_ledger.read_current(self.root) is not None:
            work_ledger.abandon(self.root, 'Synthetic edit test ends its work task.', actor=fixture.ACTOR)

    def draft(self, execution: str, directory: str, **options) -> dict:
        return production_inputs.draft_inputs(self.root, None, directory, route='generation', execution=execution,
            edit_character='robot', edit_slot='base.front', new_task=GOAL, **options)

    def answer(self, result: dict) -> dict:
        """The synthetic fixture author's answers to every entry the draft reported."""
        from reading_fixtures import fixture_reading
        path = self.root / result['choices_file']
        choices = c.load(path)
        task = choices['authoring']['task']
        target = choices['target']
        reading = fixture_reading(route='generation', features=task['features'], studio=self.root,
            ledger=self.root / 'work/reads.jsonl', execution=task['execution'], model=target['model'],
            service=target['service'])
        choices['reading']['reading_key'] = reading['reading_key']
        (self.root / choices['authoring']['delivery']['file']).write_bytes(PROMPT.encode('utf-8'))
        task['direction'].update(purpose='Change only the background of the adopted robot front image.',
            intended_effect='The same adopted robot reads clearly against a pale green wall.')
        task['criteria'] = [
            {'id': 'requested-background', 'strength': 'hard', 'evidence': 'image',
             'text': 'The plain background behind the robot is a pale green wall across the visible backdrop.'},
            {'id': 'robot-preserved', 'strength': 'hard', 'evidence': 'image',
             'text': 'Compare the whole robot with the complete adopted base.front image: identity, shape, colors, '
                     'pose and framing match within the visible scene.',
             'identity_review': ['robot'],
             'identity_bindings': [{'source': 'reference:edit-source', 'subject_ids': ['robot'], 'selectors': [''],
                 'treatment': 'preserve', 'reason': 'The edit keeps the adopted robot; only the background changes.',
                 'carriers': [{'kind': 'reference', 'reference': 'edit-source', 'use': 'identity'}],
                 'variation': None}]}]
        if task['execution'] == 'dispatcher':
            task['recording'].update(slot='edit.background', sheet_panel=False, role='background-edit')
        else:
            target['operation'] = 'generate'
            external = choices['external']
            external['image_input']['external_request'] = {'model_field': ['model'], 'prompt_field': ['prompt'],
                'operation_field': ['operation'], 'count_field': ['count'], 'count': 1,
                'prompt_syntax': {'default': 'literal', 'control': None}}
            external['request'] = {'width': 32, 'height': 32, 'inputs': {'references': [None]}}
            external['media_slots'] = [['inputs', 'references', 0]]
        choices['authoring']['documents']['production_spec']['render_intent']['prompt_expression'] = \
            'its flat graphic finish'
        plan_path = self.root / choices['task_changes']['semantic_edit']
        plan = c.load(plan_path)
        plan['edit'].update(target='background behind the robot',
            change='replace the plain background with a pale green wall',
            preserve=['robot identity', 'robot pose', 'camera framing', 'flat graphic finish'])
        plan['review_criteria'] = ['requested-background', 'robot-preserved']
        plan_path.write_bytes(c.encoded(plan))
        path.write_bytes(c.encoded(choices))
        return choices

    def assert_draft_prefill(self, result: dict) -> dict:
        choices = result['choices']
        authored = choices['authoring']
        source = self.case['source']
        self.assertEqual(authored['task']['features'],
                         ['semantic-instruction-edit', 'instruction-edit', 'recurring-identity'])
        self.assertEqual(authored['task']['artifact'], 'image')
        path = Path(source['resolved_path']).relative_to(self.root).as_posix()
        self.assertEqual([(row['id'], row['path'], row['role'], row['disposition']) for row in authored['task']['sources']],
                         [('edit-source', path, 'accepted-source', 'applied')])
        self.assertEqual(result['edit_source']['source'], source)
        self.assertEqual(result['edit_source']['origin'], {'run': self.case['run'], 'candidate': self.case['candidate']})
        specification = authored['documents']['production_spec']
        self.assertEqual(specification['render_intent']['execution_mode'], 'instruction-edit')
        self.assertIsNone(specification['render_intent']['prompt_expression'])
        self.assertEqual([row['id'] for row in specification['subjects']], ['robot'])
        plan = c.load(self.root / choices['task_changes']['semantic_edit'])
        self.assertEqual((plan['source'], plan['edit']['required_reference_roles']), ('edit-source', ['scene']))
        self.assertEqual((plan['edit']['target'], plan['edit']['change'], plan['edit']['preserve'],
                          plan['review_criteria']), (None, None, None, None))
        self.assertEqual(choices['target'], {'kind': 'catalog', 'model': cases.MODEL_ID, 'service': 'synthetic'})
        self.assertEqual(authored['task']['criteria'], [])
        self.assertIsNone(authored['task']['direction']['purpose'])
        self.assertEqual((self.root / authored['delivery']['file']).read_bytes(), b'')
        return choices

    def assert_reports_together(self, result: dict, expected: set[str]) -> None:
        fields = [row['field'] for row in result['unresolved']]
        self.assertEqual(set(fields), expected, result['unresolved'])
        for row in result['unresolved']:
            self.assertNotEqual(row['required_action'], DEFAULT_ACTION, row)
            self.assert_guidance(row['guidance'])
        identity = {next(iter(row['gaps'])): row['gaps'] for row in result['unresolved']
                    if row['code'] == 'IDENTITY_COVERAGE_INCOMPLETE'}
        self.assertEqual(identity['uncovered']['uncovered'],
                         [{'source': 'reference:edit-source', 'pointer': '', 'subject_ids': ['robot']}])
        self.assertEqual(identity['missing_whole_reviews']['missing_whole_reviews'], ['robot'])

    def test_dispatcher_edit_draft_names_every_requirement_and_prepares_after_they_are_answered(self):
        result = self.draft('dispatcher', 'work/edit-dispatcher')
        choices = self.assert_draft_prefill(result)
        authored = choices['authoring']
        references = authored['references']
        self.assertEqual(references['image_input'], {})
        self.assertEqual([(row['id'], row['role'], row['source'], row['subject_uses'])
                          for row in references['additional_references']],
                         [('edit-source', 'scene', self.case['source'],
                           [{'subject_id': 'robot', 'use': 'identity', 'priority': 0}])])
        self.assertEqual(authored['generation']['continuity'], {'robot': 'recurring'})
        self.assertEqual(authored['task']['recording'], {'character': 'robot', 'slot': None,
            'subject_map': {'robot': 'robot'}, 'sheet_panel': None, 'role': None})
        self.assertEqual(authored['documents']['parameters'], {'width': 32, 'height': 32, 'steps': 20})
        self.assertEqual(choices['validation']['mode'], 'target-schema')
        self.assert_reports_together(result, {
            'reading.reading_key', 'authoring.task.direction.purpose', 'authoring.task.direction.intended_effect',
            'authoring.task.criteria', 'authoring.delivery.content',
            'authoring.documents.production_spec.render_intent.prompt_expression',
            'authoring.task.recording.slot', 'authoring.task.recording.sheet_panel', 'authoring.task.recording.role',
            *EDIT_FIELDS})
        edit_rows = [row for row in result['unresolved'] if row['field'] in EDIT_FIELDS]
        for row in edit_rows:
            self.assertEqual(row['file'], choices['task_changes']['semantic_edit'])
        authored = {row['field'] for row in result['unresolved'] if row['code'] == 'AUTHORED_CHOICE_REQUIRED'}
        inspected = {row['field'] for row in self.inspected(result['choices_file'])}
        self.assertEqual(inspected, authored)
        report = self.refused(result['choices_file'])
        workflow.schema_check(report, 'compilation-report')
        self.assertEqual({row['pointer'] for row in report['diagnostics']}, authored)
        plan = next(row for row in report['diagnostics'] if row['pointer'] == EDIT_FIELDS[0])
        self.assertEqual(plan['file'], choices['task_changes']['semantic_edit'])

        self.answer(result)
        prepared = workflow.prepare(self.root, choices=result['choices_file'])
        self.assertTrue(prepared['ok'], prepared)
        _, snapshot, consumer, _ = workflow.load_run(self.root, prepared['run'])
        binding = consumer['semantic_edit']
        self.assertEqual((binding['source'], binding['status']), ('edit-source', 'prepared-not-generated'))
        scene = consumer['image_input']['references'][0]
        self.assertEqual((scene['id'], scene['role'], scene['sha256']), ('edit-source', 'scene', self.case['source']['sha256']))
        self.assertNotEqual(scene['file'], snapshot['task']['sources'][0]['path'])
        selected = consumer['image_input']['prepared_reference_set']['selected_references'][0]
        self.assertEqual(selected['source'], self.case['source'])
        package = c.load(Path(prepared['package']))
        robot = package['visual_continuity']['subjects']['robot']
        self.assertEqual((robot['continuity'], robot['studio_character']), ('recurring', 'robot'))
        self.assertEqual([ref['artifact_id'] for ref in robot['identity_refs']], [self.case['source']['artifact_id']])

        # Reopening the edit run restores the same editable plan and mirrored Studio reference.
        again = production_inputs.draft_inputs(self.root, None, 'work/edit-dispatcher-again', from_run=prepared['run'])
        self.assertEqual(again['unresolved'], [])
        reopened = again['choices']
        self.assertEqual(reopened['authoring']['references']['image_input'], {})
        self.assertEqual(reopened['authoring']['references']['additional_references'][0]['source'], self.case['source'])
        self.assertEqual(reopened['task_changes']['semantic_edit'], 'work/edit-dispatcher-again/edit-plan.json')
        self.assertEqual(c.load(self.root / reopened['task_changes']['semantic_edit']),
                         c.load(self.root / choices['task_changes']['semantic_edit']))
        repeated = workflow.prepare(self.root, choices=again['choices_file'])
        self.assertTrue(repeated['ok'], repeated)
        self.assertEqual(workflow.load_run(self.root, repeated['run'])[2]['semantic_edit']['edit'], binding['edit'])

    def test_external_edit_draft_names_every_requirement_and_prepares_after_the_upload(self):
        result = self.draft('external', 'work/edit-external')
        choices = self.assert_draft_prefill(result)
        external = choices['external']
        self.assertEqual(external['image_input'], {'artifact_type': 'image-input-plan',
            'references': [{'id': 'edit-source'}], 'external_request': None})
        delivery = external['reference_delivery']['choices']
        self.assertEqual([(row['id'], row['role'], row['source']) for row in delivery['additional_references']],
                         [('edit-source', 'scene', self.case['source'])])
        self.assertNotIn('recording', choices['authoring']['task'])
        self.assert_reports_together(result, {
            'reading.reading_key', 'target.operation', 'authoring.task.direction.purpose',
            'authoring.task.direction.intended_effect', 'authoring.task.criteria', 'authoring.delivery.content',
            'authoring.documents.production_spec.render_intent.prompt_expression',
            'external.request', 'external.image_input.external_request', *EDIT_FIELDS})

        choices = self.answer(result)
        built = production_inputs.build_inputs(self.root, None, result['choices_file'], 'work/edit-external-carriers')
        self.assertEqual(built['request_state'], 'reference-upload-required', built)
        self.assertEqual([row['reason'] for row in built['unresolved']], ['provider-upload-required'], built)
        carrier = built['unresolved'][0]['carrier']
        self.assertEqual(carrier['sha256'], self.case['source']['sha256'])
        c.atomic(self.root / 'work/upload-receipt.json', c.encoded({'synthetic': True, 'media': 'synthetic-robot-front',
                                                                    'carrier_sha256': carrier['sha256']}))
        choices['external']['image_input']['references'][0]['transport'] = {'value': 'synthetic-robot-front',
            'evidence': {'path': 'work/upload-receipt.json', 'locator': 'whole synthetic receipt'},
            'uploaded_file': carrier['path']}
        (self.root / result['choices_file']).write_bytes(c.encoded(choices))
        prepared = workflow.prepare(self.root, choices=result['choices_file'])
        self.assertTrue(prepared['ok'], prepared)
        consumer = workflow.load_run(self.root, prepared['run'])[2]
        self.assertEqual(consumer['semantic_edit']['source'], 'edit-source')
        bound = consumer['image_input']
        self.assertEqual(bound['prepared_reference_set']['selected_references'][0]['source'], self.case['source'])
        self.assertEqual(bound['external_request']['request']['inputs']['references'], ['synthetic-robot-front'])
        self.assertEqual(bound['external_request']['request']['prompt'], PROMPT)

    def test_an_accepted_image_without_an_origin_or_identity_invents_no_subject(self):
        from sheet_artifacts_smoke_test import accepted
        accepted(self.root / 'characters/robot/sheet/sheet-data.json', slot='canon.primary')
        result = production_inputs.draft_inputs(self.root, None, 'work/edit-external-import',
            route='generation', execution='dispatcher', model=cases.MODEL_ID, service='synthetic',
            edit_character='robot', edit_slot='canon.primary', new_task=GOAL)
        self.assertIsNone(result['edit_source']['origin'])
        self.assertIsNone(result['edit_source']['identity'])
        choices = result['choices']
        authored = choices['authoring']
        self.assertNotIn('production_spec', authored['documents'])
        self.assertEqual(authored['generation']['continuity'], {})
        self.assertEqual(authored['task']['recording']['subject_map'], {})
        task = authored['task']
        from reading_fixtures import fixture_reading
        reading = fixture_reading(route='generation', features=task['features'], studio=self.root,
            ledger=self.root / 'work/reads.jsonl', execution=task['execution'],
            model=cases.MODEL_ID, service='synthetic')
        choices['reading']['reading_key'] = reading['reading_key']
        (self.root / authored['delivery']['file']).write_bytes(PROMPT.encode('utf-8'))
        task['direction'].update(purpose='Change only the background of the accepted image.',
            intended_effect='The same robot reads clearly against a pale green wall.')
        task['criteria'] = [{'id': 'requested-background', 'strength': 'hard', 'evidence': 'image',
                             'text': 'The visible backdrop is pale green.'}]
        task['recording'].update(slot='candidate', sheet_panel=False, role='background-edit')
        authored['documents']['parameters'] = {'width': 32, 'height': 32, 'steps': 20}
        import request_validation
        import runtime_evidence
        from request_validation_fixtures import fixture_validation
        record = fixture_validation(self.root, cases.MODEL_ID, service='synthetic',
                                    reference_mode='authored-rendition')
        choices['validation'] = request_validation.draft_choices(record, runtime_evidence.reader(self.root))
        plan_path = self.root / choices['task_changes']['semantic_edit']
        plan = c.load(plan_path)
        plan['edit'].update(target='background behind the robot',
            change='replace the plain background with a pale green wall', preserve=['robot'])
        plan['review_criteria'] = ['requested-background']
        plan_path.write_bytes(c.encoded(plan))
        (self.root / result['choices_file']).write_bytes(c.encoded(choices))
        prepared = workflow.prepare(self.root, choices=result['choices_file'])
        self.assertTrue(prepared['ok'], prepared)
        consumer = workflow.load_run(self.root, prepared['run'])[2]
        self.assertEqual(consumer['semantic_edit']['source'], 'edit-source')
        package = c.load(Path(prepared['package']))
        self.assertEqual(package['visual_continuity']['subjects'], {})

    def test_refused_selections_name_their_repair_and_open_no_work(self):
        cases_ = {
            'slot-missing': dict(edit_slot=None),
            'route': dict(route='upscale'),
            'execution': dict(execution='authored'),
            'upscale-option': dict(scale=2.0),
            'not-accepted': dict(edit_slot='base.back'),
            'no-open-task': dict(new_task=None),
        }
        for name, change in cases_.items():
            options = {'route': 'generation', 'execution': 'dispatcher', 'edit_character': 'robot',
                       'edit_slot': 'base.front', 'new_task': GOAL, **change}
            with self.subTest(name=name), self.assertRaises(ProductionError) as caught:
                production_inputs.draft_inputs(self.root, None, 'work/refused-' + name, **options)
            diagnostic = caught.exception.diagnostic
            self.assertEqual(diagnostic.phase, 'authoring')
            self.assertNotEqual(diagnostic.required_action, DEFAULT_ACTION)
            self.assert_guidance(diagnostic.as_dict()['guidance'])
            self.assertIsNone(work_ledger.read_current(self.root))
            self.assertFalse((self.root / ('work/refused-' + name)).exists())
        with self.assertRaises(ProductionError) as caught:
            production_inputs.draft_inputs(self.root, 'task.json', 'work/refused-task', edit_character='robot',
                                           edit_slot='base.front', route='generation', execution='dispatcher')
        self.assertIn('--from-run', caught.exception.diagnostic.required_action)


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
