"""An instruction edit of an accepted Studio image starts from one editable draft.

`draft-inputs --edit-character --edit-slot` selects the accepted image with its
acceptance evidence and the applicable choices of the run that produced it. An
independently adopted identity retains its canonical proof. The
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
from test_production_review import ReviewCase

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
        import studio_reference
        cls.case['accepted_source'] = studio_reference.current_accepted_source(cls.root, 'robot', 'base.front')

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
             'identity_bindings': [{'source': 'reference:edit-identity', 'subject_ids': ['robot'], 'selectors': [''],
                 'treatment': 'preserve', 'reason': 'The edit keeps the adopted robot; only the background changes.',
                 'carriers': [{'kind': 'reference', 'reference': 'edit-identity', 'use': 'identity'}],
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
        source = self.case['accepted_source']
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
                         [{'source': 'reference:edit-identity', 'pointer': '', 'subject_ids': ['robot']}])
        self.assertEqual(identity['missing_whole_reviews']['missing_whole_reviews'], ['robot'])

    def test_dispatcher_edit_draft_names_every_requirement_and_prepares_after_they_are_answered(self):
        result = self.draft('dispatcher', 'work/edit-dispatcher')
        choices = self.assert_draft_prefill(result)
        authored = choices['authoring']
        references = authored['references']
        self.assertEqual(references['image_input'], {})
        self.assertEqual([(row['id'], row['role'], row['source'], row.get('subject_uses', []))
                          for row in references['additional_references']],
                         [('edit-source', 'scene', self.case['accepted_source'], []),
                          ('edit-identity', 'identity', self.case['source'],
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
        self.assertEqual(selected['source'], self.case['accepted_source'])
        package = c.load(Path(prepared['package']))
        robot = package['visual_continuity']['subjects']['robot']
        self.assertEqual((robot['continuity'], robot['studio_character']), ('recurring', 'robot'))
        self.assertEqual([ref['artifact_id'] for ref in robot['identity_refs']], [self.case['source']['artifact_id']])

        # Reopening the edit run restores the same editable plan and mirrored Studio reference.
        again = production_inputs.draft_inputs(self.root, None, 'work/edit-dispatcher-again', from_run=prepared['run'])
        self.assertEqual(again['unresolved'], [])
        reopened = again['choices']
        self.assertEqual(reopened['authoring']['references']['image_input'], {})
        self.assertEqual(reopened['authoring']['references']['additional_references'][0]['source'], self.case['accepted_source'])
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
            'references': [{'id': 'edit-source'}, {'id': 'edit-identity'}], 'external_request': None})
        delivery = external['reference_delivery']['choices']
        self.assertEqual([(row['id'], row['role'], row['source']) for row in delivery['additional_references']],
                         [('edit-source', 'scene', self.case['accepted_source']),
                          ('edit-identity', 'identity', self.case['source'])])
        self.assertNotIn('recording', choices['authoring']['task'])
        self.assert_reports_together(result, {
            'reading.reading_key', 'target.operation', 'authoring.task.direction.purpose',
            'authoring.task.direction.intended_effect', 'authoring.task.criteria', 'authoring.delivery.content',
            'authoring.documents.production_spec.render_intent.prompt_expression',
            'external.request', 'external.image_input.external_request', *EDIT_FIELDS})

        choices = self.answer(result)
        built = production_inputs.build_inputs(self.root, None, result['choices_file'], 'work/edit-external-carriers')
        self.assertEqual(built['request_state'], 'reference-upload-required', built)
        self.assertEqual([row['reason'] for row in built['unresolved']], ['provider-upload-required'] * 2, built)
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
        self.assertEqual(bound['prepared_reference_set']['selected_references'][0]['source'], self.case['accepted_source'])
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


class AcceptedSceneEditTests(ReviewCase):
    """A two-subject scene remains editable before and after separate scene adoption."""

    def configure_task(self, task):
        import studio
        studio.add_character(self.root, 'partner', 'general')
        specification = c.load(self.root / 'spec.json')
        partner = copy.deepcopy(specification['subjects'][0]); partner['id'] = 'partner'
        specification['subjects'].append(partner)
        cases.write(self.root / 'spec.json', specification)
        task['generation']['continuity'] = {'robot': 'one-off', 'partner': 'one-off'}
        task['recording'].update(slot='episode.opening', sheet_panel=False,
                                 subject_map={'robot': 'robot', 'partner': 'partner'})

    def setUp(self):
        from catalog_retrieval import runtime
        home = tempfile.TemporaryDirectory(); self.addCleanup(home.cleanup)
        self.enterContext(fixture.scratch_home(Path(home.name)))
        self.addCleanup(runtime.configure_pack_runtime, None)
        super().setUp()
        self.record_review([('output', 'pass'), ('palette', 'pass')])
        self.select()
        import studio
        studio.accept(self.root, 'robot', self.iteration)

    def answered_draft(self, destination, directory):
        from reading_fixtures import fixture_reading
        result = production_inputs.draft_inputs(self.root, None, directory, route='generation',
            execution='dispatcher', edit_character='robot', edit_slot='episode.opening')
        choices = result['choices']; authored = choices['authoring']; task = authored['task']
        self.assertEqual(result['edit_source']['source']['kind'], 'studio-accepted-image')
        self.assertIsNone(result['edit_source']['identity'])
        self.assertEqual(task['recording']['subject_map'], {'robot': 'robot', 'partner': 'partner'})
        self.assertEqual(authored['generation']['continuity'], {'robot': 'one-off', 'partner': 'one-off'})
        self.assertEqual([row['id'] for row in authored['documents']['production_spec']['subjects']], ['robot', 'partner'])
        reading = fixture_reading(route='generation', features=task['features'], studio=self.root,
            ledger=self.root / 'work/reads.jsonl', execution='dispatcher', model=cases.MODEL_ID, service='synthetic')
        choices['reading']['reading_key'] = reading['reading_key']
        prompt = ('Edit the supplied scene: make the backdrop pale green. Preserve both robots, their positions, '
                  'the camera framing and the flat graphic finish.')
        cases.write(self.root / authored['delivery']['file'], prompt)
        task['direction'].update(purpose='Change the two-subject scene backdrop.',
                                 intended_effect='Both existing participants remain in the edited scene.')
        task['criteria'] = [
            {'id': 'backdrop', 'strength': 'hard', 'evidence': 'image', 'text': 'The backdrop is pale green.'},
            {'id': 'participants', 'strength': 'hard', 'evidence': 'image',
             'text': 'Both source robots, their positions, camera framing and flat graphic finish remain unchanged.'}]
        task['recording'].update(slot=destination, sheet_panel=False, role='scene-edit')
        authored['documents']['production_spec']['render_intent']['prompt_expression'] = 'flat graphic finish'
        plan = c.load(self.root / choices['task_changes']['semantic_edit'])
        plan['edit'].update(target='scene backdrop', change='make the backdrop pale green',
                            preserve=['both source robots', 'subject positions', 'camera framing', 'flat graphic finish'])
        plan['review_criteria'] = ['backdrop', 'participants']
        cases.write(self.root / choices['task_changes']['semantic_edit'], plan)
        cases.write(self.root / result['choices_file'], choices)
        return result

    def test_same_slot_and_deliberate_new_slot_preserve_both_subjects_without_sheet_adoption(self):
        import studio
        self.assertNotIn('episode.opening', studio.StudioRead(self.root).sheet('robot')['slots'])
        for destination in ('episode.opening', 'episode.alternate'):
            with self.subTest(destination=destination):
                draft = self.answered_draft(destination, 'work/' + destination)
                result = workflow.prepare(self.root, choices=draft['choices_file'])
                self.assertTrue(result['ok'], result)
                loaded = workflow.load_run(self.root, result['run'])
                self.assertEqual(loaded[1]['task']['recording']['slot'], destination)
                self.assertEqual(loaded[2]['semantic_edit']['source'], 'edit-source')
                package = c.load(Path(result['package']))
                self.assertEqual(set(package['visual_continuity']['subjects']), {'robot', 'partner'})
                self.assertEqual(package['visual_continuity']['purpose'], 'image')
                self.assertEqual(studio.acceptance_state(self.root, 'robot', 'episode.opening')['iteration_id'], self.iteration)

    def test_an_adopted_scene_does_not_become_a_single_subject_panel(self):
        import adoption_workflow
        approval = adoption_workflow.draft_approval(self.root, 'robot', self.iteration, scope='sheet', influence='environment')
        approval.update(by=fixture.ACTOR, at='2000-01-01T00:00:00Z', note='Synthetic adoption of the whole two-subject scene.')
        cases.write(self.root / 'scene-approval.json', approval)
        token = fixture.grant(self.root, self.run, workflow.adoption_intent(
            self.root, self.run, self.candidate, 'robot', self.iteration, approval))
        workflow.adopt(self.root, self.run, self.candidate, 'robot', self.iteration, 'scene-approval.json', token)
        draft = self.answered_draft('episode.opening', 'work/adopted-scene-edit')
        result = workflow.prepare(self.root, choices=draft['choices_file'])
        self.assertTrue(result['ok'], result)
        package = c.load(Path(result['package']))
        self.assertEqual(set(package['visual_continuity']['subjects']), {'robot', 'partner'})

    def test_acceptance_change_during_upload_stops_before_a_new_send(self):
        import production_execution as execution
        import production_store as store
        import studio
        import studio_reference
        import transport_synthetic as transport
        from test_production_execution import decisions

        draft = self.answered_draft('episode.alternate', 'work/send-boundary')
        prepared = workflow.prepare(self.root, choices=draft['choices_file'])
        run = prepared['run']
        approved = decisions(self.root, run)
        source = draft['edit_source']['source']
        original_upload = transport.upload_media

        def replace_acceptance(*args, **kwargs):
            uploaded = original_upload(*args, **kwargs)
            replacement = studio.iterate(self.root, 'robot', 'episode.opening', Path(source['resolved_path']),
                package=None, request=None, response=None, note='Synthetic replacement with identical source bytes.')
            studio.accept(self.root, 'robot', replacement['iteration_id'])
            return uploaded

        with patch.object(transport, 'upload_media', side_effect=replace_acceptance), \
             patch.object(transport, 'send', side_effect=AssertionError('A stale accepted scene must not be sent')) as send:
            with self.assertRaisesRegex(ValueError, 'STUDIO_REFERENCE_CHANGED'):
                execution.execute(self.root, run, decisions_file=approved)
        self.assertEqual(send.call_count, 0)
        operations = [row['data']['operation'] for row in store.event_rows(self.root, run)
                      if row['event'] == 'external-step']
        self.assertEqual(operations, ['upload'])
        directory, saved, _, _ = workflow.load_run(self.root, run)
        self.assertIn(source, saved['studio_reference_sources'])
        proof = next(directory.glob('package.*.references/studio/' + source['proof_sha256'] + '/proof.json'))
        studio_reference.validate_source(source, active=False, source_archive=proof.parent.parent.parent / 'sources')

    def test_accepted_scene_reference_preparation_is_independent_of_prompt_form(self):
        import pack_manager
        import studio_reference
        from model_prompt_input_fixtures import prompt_input
        from prepare_generation_references import prepare_references
        from catalog_retrieval import runtime
        models = c.load(self.case['pack'] / 'records/models.json')
        tagged = copy.deepcopy(models['records'][0]); tagged['id'] = 'cpb-synthetic-tags'
        tagged['label'] = 'Synthetic tagged reference fixture'; tagged['aliases'] = ['synthetic tagged fixture']
        tagged['prompt_input'] = prompt_input('tag-based', vocabularies=('danbooru',))
        tagged['prompt_dialect'] = 'fixture-family'
        models['records'].append(tagged)
        cases.write(self.case['pack'] / 'records/models.json', models)
        pack_manager.write_lock(self.case['pack']); runtime.configure_pack_runtime(self.case['settings'])
        source = studio_reference.current_accepted_source(self.root, 'robot', 'episode.opening')
        for model in (cases.MODEL_ID, tagged['id']):
            with self.subTest(model=model):
                references = prepare_references([{'role': 'scene', 'source': source}], model=model,
                    output_dir=self.root / 'work' / model)
                self.assertEqual(references['selected_references'][0]['source'], source)


class InheritedIdentityEditTests(unittest.TestCase):
    def test_scene_edit_carries_exact_identity_reference_scope_and_guidance(self):
        import production_execution as execution
        import studio
        import studio_reference_fixtures as reference_fixtures
        from prepare_generation_references import prepare_references
        from test_production_execution import decisions

        case = reference_fixtures.adopted_case(self)
        root = case.root
        task, canonical = reference_fixtures.reference_task(case)
        run = workflow.prepare(root, task)['run']
        output = execution.execute(root, run, decisions_file=decisions(root, run))
        candidate = output['runs'][0]['candidates'][0]
        review = workflow.draft_review(root, run, candidate)
        review.update(reviewer=fixture.ACTOR, observations=[{
            'evidence': 'candidate', 'locator': {'kind': 'whole'},
            'observation': 'The local synthetic PNG is captured.',
            'interpretation': 'Protocol fixture only.', 'limitations': ['No visual quality or user approval.']}],
            conclusion='Synthetic reference scene is selected.')
        for check in review['checks']:
            check.update(verdict='pass', observation_indices=[0], reason='Explicit synthetic fixture assessment.')
        cases.write(root / 'inherited-review.json', review)
        workflow.review(root, run, 'inherited-review.json')
        selection = workflow.draft_selection(root, run, candidate)
        selection['reason'] = 'Synthetic acceptance of a scene that uses an independently adopted identity.'
        fixture.selection(root, run, selection)
        cases.write(root / 'inherited-selection.json', selection)
        workflow.select(root, run, 'inherited-selection.json')
        iteration = next(row for row in studio.StudioRead(root).iterations('robot')
                         if (row.get('production') or {}).get('candidate') == candidate)
        studio.accept(root, 'robot', iteration['iteration_id'])

        result = production_inputs.draft_inputs(root, None, 'work/inherited-edit', route='generation',
            execution='dispatcher', edit_character='robot', edit_slot='scene.result')
        authored = result['choices']['authoring']
        self.assertIsNone(result['edit_source']['identity'])
        self.assertEqual(result['edit_source']['source']['kind'], 'studio-accepted-image')
        self.assertIn('recurring-identity', authored['task']['features'])
        self.assertEqual(authored['task']['recording']['subject_map'], {'C01': 'robot'})
        self.assertEqual(authored['generation']['continuity'], {'C01': 'recurring'})
        selected = authored['references']['additional_references']
        self.assertEqual(selected[1]['source'], canonical)
        self.assertEqual(selected[1]['subject_uses'], [{'subject_id': 'C01', 'use': 'identity', 'priority': 0}])
        rebuilt = prepare_references([{key: value for key, value in row.items() if key != 'id'} for row in selected],
            model=cases.MODEL_ID, output_dir=root / 'work/inherited-reference-check')
        original = c.load(root / 'studio-references.json')['selected_references'][0]
        self.assertEqual(rebuilt['selected_references'][1]['authority'], original['authority'])


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
