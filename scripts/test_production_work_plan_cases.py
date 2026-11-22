"""Condition cases for compact recovery and retained request ownership."""
from __future__ import annotations

import copy
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import execution_contract as c
import production_case_fixtures as f
import production_operations as operations
import production_inputs
import production_store as store
import production_work_execution as work_execution
import production_work_plan as plans
import production_direction_smoke_test as external
import production_fixtures as fixtures
import test_production_report_view as report_cases
import sheet_batch_smoke_test as batch_cases
import test_production_adoption as adoption_cases
import test_authored_continuation as authored_cases


class PlanProjectionCases(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def project(self, current):
        definition = {'items': [{'name': 'current', 'result': {'scope': 'delivery-only'}}]}
        state = {'status': 'active', 'task_id': 'synthetic-task', 'items': {'current': {
            'phase': 'execution', 'status': 'needs-input', 'run': 'synthetic-run', 'current': current}}}
        return plans._project(self.root, 'work/plan.json', state, definition)

    def test_nested_owner_reports_stay_compact_and_every_action_reference_resolves(self):
        status = report_cases.long_authoring_status()
        inspection = status['current_task']['authoring']
        body = 'A retained original with all its specific relationships. ' * 18000
        criterion = {'id': 'identity', 'strength': 'hard', 'text': 'Preserve the named whole subject.'}
        workspace = {'phase': 'decision', 'run': 'synthetic-run',
            'basis': {'criteria': [criterion], 'evidence': []},
            'sources': [{'id': 'original', 'saved_path': '/retained/original', 'text': body}],
            'source_context': {'authoring_materials': {'original': body}},
            'prepared_input': {'execution': 'external', 'request': {'prompt': body}, 'outputs': 1},
            'instruction': 'Compare the actual saved input with the selected source and criteria.'}
        compilation = {'ok': False, 'publishable': False,
            'diagnostics': [{'code': 'INPUT_SCHEMA_INVALID', 'phase': 'compilation', 'severity': 'error',
                'file': 'parameters.json', 'pointer': '/width', 'message': 'Choose a supported width.',
                'required_action': 'Correct width in this exact selected parameter file.'}],
            'captured_sources': {'original': body}}
        current = {'choices': 'work/current/choices.json', 'inspection': inspection,
                   'workspace': workspace, 'status': status, 'compilation': compilation}
        original = copy.deepcopy(current)
        report = self.project(current)
        shown = report['items'][0]['current']
        self.assertLess(len(c.encoded(report)), len(c.encoded(current)) // 5)
        self.assertEqual(shown['workspace']['basis']['criteria'], [criterion])
        self.assertEqual(current, original)
        for name in ('inspection', 'workspace', 'status', 'compilation'):
            self.assertEqual(c.load(self.root / shown[name]['full_report']), current[name])
        self.assertEqual(shown['compilation']['diagnostics'][0]['pointer'], '/width')

        def visit(value):
            if isinstance(value, dict):
                if 'action_ref' in value:
                    self.assertIn('argv', report_cases.resolved_action(report, value))
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)
        visit(report)

    def test_material_phases_preserve_the_exact_input_and_observed_candidate(self):
        request = {'prompt': 'Every relation of the exact prepared request.', 'width': 1024, 'height': 768}
        candidate = {'id': 'a' * 64, 'files': [{'path': '/saved/image', 'sha256': 'b' * 64}],
                     'media': {'kind': 'image', 'width': 1024, 'height': 768}}
        for phase, material in (
                ('input', {'prepared_input': {'execution': 'external', 'request': request, 'outputs': 1}}),
                ('observe', {'candidate': candidate})):
            with self.subTest(phase=phase):
                report = self.project({'workspace': {'phase': phase, 'run': 'synthetic-run', **material}})
                for key, value in material.items():
                    self.assertEqual(report['items'][0]['current']['workspace'][key], value)

    def test_blocked_batch_keeps_every_cause_and_one_owner_for_repeated_criteria(self):
        body = 'An exact retained comparison value. ' * 30000
        mismatch = {'code': 'AUTHORIZATION_MISMATCH', 'phase': 'authorization',
            'message': 'The selected operation differs.', 'pointer': '/targets',
            'expected': body, 'actual': body + ' Changed.',
            'required_action': 'Assess the current selected operation.'}
        width = {'code': 'INPUT_SCHEMA_INVALID', 'phase': 'compilation',
            'message': 'Choose a supported width.', 'file': 'parameters.json', 'pointer': '/width',
            'required_action': 'Correct width in the selected file.'}
        batch = {'ok': False, 'outcome': 'blocked', 'batch': 'batch.json', 'panels': {
            'canon.side': {'status': 'blocked', 'run': None, 'source_task': 'side.json',
                'selected_references': [], 'diagnostic': {**mismatch,
                    'report': {'ok': False, 'publishable': False, 'diagnostics': [width],
                               'captured_sources': {'original': body}}}, 'artifact': {'original': body}}}}
        criterion = {'id': 'output', 'strength': 'hard', 'text': 'Assess the whole retained output.'}
        report = self.project({'report': batch, 'diagnostic': mismatch, 'criteria': [criterion],
            'workspace': {'phase': 'review', 'run': 'synthetic-run',
                'basis': {'criteria': [criterion], 'evidence': []}, 'sources': []}})
        current = report['items'][0]['current']
        self.assertLess(len(c.encoded(report)), 15000)
        self.assertEqual(current['workspace']['basis']['criteria'], [criterion])
        self.assertEqual(current['criteria']['owner'], '#/items/0/current/workspace/basis/criteria')
        self.assertEqual(current['diagnostic']['full_report'], 'work/plan.json#/items/current/current/diagnostic')
        self.assertEqual(current['diagnostic']['pointer'], '/targets')
        shown = current['report']
        self.assertEqual(c.load(self.root / shown['full_report']), batch)
        self.assertEqual(shown['panels']['canon.side']['source_task'], 'side.json')
        self.assertEqual(shown['panels']['canon.side']['diagnostic']['report']['diagnostics'][0]['pointer'], '/width')
        self.assertIn('artifact', shown['panels']['canon.side']['omitted_fields'])

    def test_reopened_work_keeps_the_old_plan_in_its_revision_without_resuming_it(self):
        import work_ledger
        task = work_ledger.begin(self.root, 'Revise the retained commission.', ['Prepare', 'Review'])
        task.update(production_plan='work/plans/earlier/plan.json', plan_steps={'1': 'prepared'},
                    production_run='earlier-run')
        task['steps'][0].update(done_at='2000-01-01T00:00:00Z', production={'plan_id': 'earlier-plan'})
        work_ledger.write_current(self.root, task)
        revised = work_ledger.reopen(self.root, 1, reason='The actual instruction changes the intended result.',
                                    actor='Synthetic author')
        self.assertNotIn('production_plan', revised)
        self.assertNotIn('plan_steps', revised)
        self.assertNotIn('production', revised['steps'][0])
        archived = c.load(self.root / revised['revisions'][-1]['snapshot'])
        self.assertEqual(archived['production_plan'], 'work/plans/earlier/plan.json')
        self.assertEqual(archived['plan_steps'], {'1': 'prepared'})
        self.assertIsNone(work_ledger.plan_action(self.root, revised))


class ExternalPlanRecoveryCases(unittest.TestCase):
    setUp = external.LifecycleTests.setUp
    write = external.LifecycleTests.write
    prepare = external.LifecycleTests.prepare
    external_case = external.LifecycleTests.external_case
    external_response = external.LifecycleTests.external_response
    prepared_external_case = external.LifecycleTests.prepared_external_case

    def test_status_returns_the_bound_plan_and_keeps_the_runs_independent_next_operation(self):
        import production_execution
        import production_report_view
        run = self.prepared_external_case()
        self.write('work-request.json', {'source': {'run': run}, 'result': {'scope': 'delivery-only'}})
        plan = plans.create(self.root, 'work-request.json')['plan']
        report = production_execution.status(self.root, run)
        operations.schema_check(report, 'status')
        self.assertEqual(report['current_task']['focus'], 'plan')
        self.assertEqual(report['current_task']['production_plan'], plan)
        self.assertEqual(report['current_task']['next_actions'][0]['command'], 'advance')
        self.assertNotIn('preparation_completion', report['current_task'])
        self.assertNotEqual(report['runs'][0]['next_action']['command'], 'advance')
        shown = production_report_view.present(self.root, report, command='status', run=run)
        self.assertEqual(report_cases.resolved_action(shown, shown['next_action'])['command'],
                         report['runs'][0]['next_action']['command'])
        self.assertEqual(report_cases.resolved_action(shown, shown['current_task']['next_actions'][0])['command'],
                         'advance')

    def test_partial_result_keeps_its_receipt_file_and_never_enters_review_before_settlement(self):
        run, _, _ = self.external_case(count=2)
        self.external_response(amount=None)
        self.write('first.png', external.png())
        request = {'source': {'run': run}, 'result': {'scope': 'delivery-only'}}
        self.write('work-request.json', request)
        plan = plans.create(self.root, 'work-request.json')['plan']
        first = plans.advance(self.root, plan)
        answer_file = first['items'][0]['current']['answer_file']
        answer = c.load(self.root / answer_file)
        answer.update(response='host-response.json', artifacts=['first.png'], final=False,
                      reason='Actual partial synthetic response; the second result is still pending.')
        self.write(answer_file, answer)
        report = plans.advance(self.root, plan)
        self.assertEqual(report['items'][0]['phase'], 'recovery', report)
        self.assertEqual(report['items'][0]['current']['answer_file'], answer_file)
        resumed = plans.inspect(self.root, plan)
        self.assertEqual(resumed['items'][0]['current']['answer_file'], answer_file)
        rows = store.event_rows(self.root, run)
        self.assertEqual(sum(row['event'] == 'external-claim' for row in rows), 1)
        self.assertEqual(sum(row['event'] == 'candidate' for row in rows), 1)
        self.assertFalse(any(row['event'] in {'review', 'selection', 'completion'} for row in rows))

        self.write('second.png', external.png(128))
        answer.update(artifacts=['first.png', 'second.png'], final=True,
                      reason='Both actual synthetic results have now returned.')
        self.write(answer_file, answer)
        received = plans.advance(self.root, plan)
        self.assertEqual(received['items'][0]['phase'], 'observe', received)
        rows = store.event_rows(self.root, run)
        self.assertEqual(sum(row['event'] == 'external-claim' for row in rows), 1)
        self.assertEqual(sum(row['event'] == 'candidate' for row in rows), 2)
        self.assertEqual(sum(row['event'] == 'execution-result' and row['data']['final'] for row in rows), 1)
        import production_execution
        status = production_execution.status(self.root, run)['runs'][0]
        self.assertFalse(status['settlement_open'])
        again = plans.advance(self.root, plan)
        self.assertEqual(again['items'][0]['phase'], 'observe')
        self.assertEqual(store.event_rows(self.root, run), rows)

    def test_one_missing_submit_grant_keeps_the_already_selected_direction_grant(self):
        authority = c.load(self.root / 'fixture-authority.json')
        authority['grants'][0]['operations'].remove('submit')
        authority['grants'][0]['submission_validation_modes'] = []
        self.write('fixture-authority.json', authority)
        run = self.prepared_external_case()
        draft = work_execution.draft(self.root, run)
        answers = copy.deepcopy(draft['choices'])
        answers['reason'] = 'The synthetic instruction authorizes this exact saved external request.'
        answers['approval'].update(actor=fixtures.ACTOR, mode='direct',
            evidence={'path': 'fixture-authority-basis.txt', 'locator': 'whole synthetic declaration'})
        request = answers.get('request_decision')
        if request is not None:
            if 'principal_approval' in request:
                request['principal_approval'] = {'path': 'fixture-authority-basis.txt', 'locator': 'whole'}
            fixtures.assess_rendition(request['rendition_review'])
        result = work_execution.apply(self.root, self.root / 'work/execution-answer', answers,
                                      binding=draft['binding'])
        self.assertEqual(result['state'], 'host-call-required', result)
        current = store.read_authority(self.root, self.task['task_id']).document
        self.assertEqual([grant['id'] for grant in current['grants'] if 'direction' in grant['operations']],
                         ['fixture-grant'])
        records = store.event_rows(self.root, run)
        decisions = [row['data']['request'] for row in records if row['event'] == 'authorization']
        self.assertEqual([row['operation'] for row in decisions], ['direction', 'submit'])
        self.assertEqual(sum(row['event'] == 'external-claim' for row in records), 1)


class RetainedSourcePlanCases(unittest.TestCase):
    setUpClass = classmethod(adoption_cases.AdoptionTests.setUpClass.__func__)
    setUp = adoption_cases.AdoptionTests.setUp

    def test_workspace_model_and_guide_locations_use_the_retained_edition(self):
        import production_workspace
        with patch('generation_references.resolve_model_record',
                   side_effect=AssertionError('Saved interpretation must not select a live model')):
            report = production_workspace.workspace(self.root, self.run, phase='decision')
        knowledge = report['saved_knowledge']
        target = c.load(Path(knowledge['target']['path']))
        self.assertEqual(target['model_id'], knowledge['model']['id'])
        self.assertEqual(c.sha256_file(Path(knowledge['target']['path'])), knowledge['target']['sha256'])
        self.assertTrue(knowledge['resources'])
        for resource in knowledge['resources']:
            self.assertEqual(c.sha256_file(Path(resource['saved_path'])), resource['sha256'])

    def test_from_run_variant_keeps_execution_and_source_bytes_after_original_removal(self):
        source = next(row for row in self.task['sources'] if (self.root / row['path']).is_file())
        original = (self.root / source['path']).read_bytes()
        (self.root / source['path']).unlink()
        f.write(self.root / 'revision-request.txt', 'Preserve the retained character and revise its expression.')
        f.write(self.root / 'work-request.json', {
            'source': {'request': 'revision-request.txt', 'from_run': self.run},
            'result': {'scope': 'prepared-input'}})
        plan = plans.create(self.root, 'work-request.json')['plan']
        report = plans.advance(self.root, plan)
        self.assertEqual(report['items'][0]['state'], 'needs-input', report)
        self.assertEqual(report['items'][0]['phase'], 'authoring')
        choices = c.load(self.root / report['items'][0]['current']['choices'])
        self.assertEqual(choices['authoring']['task']['execution'], 'dispatcher')
        self.assertEqual(choices['authoring']['task']['artifact'], 'image')
        retained = next(row for row in choices['authoring']['task']['sources'] if row['id'] == source['id'])
        self.assertNotEqual(retained['path'], source['path'])
        self.assertEqual((self.root / retained['path']).read_bytes(), original)
        self.assertEqual({key: retained.get(key) for key in ('role', 'disposition', 'locator')},
                         {key: source.get(key) for key in ('role', 'disposition', 'locator')})

    def test_declared_amend_enters_the_affected_stage_and_retains_one_scope_owner(self):
        import production_workflow
        parser = production_workflow.build_parser()
        declaration = {'retain': ['identity', 'target'], 'change': ['controls.parameters']}
        f.write(self.root / 'revision-request.txt', 'Keep the subject and target; revise the numeric controls.')
        args = parser.parse_args(['plan', '--root', str(self.root), '--request-file', 'revision-request.txt',
            '--from-run', self.run, '--scope', 'prepared-input', '--retain', 'identity',
            '--retain', 'target', '--change', 'controls.parameters'])
        plan = plans.create(self.root, request=plans.request_from_arguments(self.root, args))['plan']
        report = plans.advance(self.root, plan)
        self.assertEqual(report['items'][0]['phase'], 'authoring', report)
        current = report['items'][0]['current']
        self.assertEqual(current['stage'], 'rendition')
        self.assertEqual(current['remaining_stages'], ['prepare'])
        choices = c.load(self.root / current['choices'])
        basis_file = self.root / Path(current['choices']).parent / 'work-basis.json'
        basis = c.load(basis_file)
        self.assertEqual(basis['change_scope'], declaration)
        self.assertNotIn('change_scope', choices)
        self.assertNotIn('change_scope', choices['authoring']['task'])
        self.assertEqual(choices['authoring_stage'], 'rendition')
        inspection = production_inputs.authoring_view(self.root, current['choices'])
        self.assertIn('amend-controls', inspection['authoring_scope']['profiles'])
        self.assertEqual(inspection['authoring_stage']['next_stage'], 'prepare')
        self.assertNotEqual(current['inspection']['authoring_stage']['stage'], 'definition')

    def test_recording_amend_drafts_directly_for_preparation(self):
        declaration = {'retain': ['identity', 'target', 'rendition'], 'change': ['recording.slot']}
        draft = production_inputs.draft_inputs(self.root, None, 'work/recording-amend',
            from_run=self.run, operation='amend', change_scope=declaration)
        self.assertEqual(draft['authoring_stage']['stage'], 'prepare')
        self.assertIsNone(draft['authoring_stage']['next_stage'])
        self.assertEqual(draft['authoring_stage']['remaining_stages'], [])
        self.assertEqual(c.load(self.root / 'work/recording-amend/work-basis.json')['change_scope'], declaration)
        self.assertIn('amend-recording', draft['authoring_scope']['profiles'])

    def test_reference_amend_advances_to_prepare_after_its_actual_reading(self):
        import production_reading_scope
        import route_reading
        f.write(self.root / 'reference-request.txt', 'Keep the subject and prompt while revising reference selection.')
        report = plans.create(self.root, request={
            'source': {'request': 'reference-request.txt', 'from_run': self.run,
                'change_scope': {'retain': ['identity', 'target', 'rendition'], 'change': ['references']}},
            'result': {'scope': 'prepared-input'}})
        plan = report['plan']
        waiting = plans.advance(self.root, plan)
        choice_path = waiting['items'][0]['current']['choices']
        choices = c.load(self.root / choice_path)
        choices['reading']['reading_key'] = None
        f.write(self.root / choice_path, choices)
        view = production_inputs.authoring_view(self.root, choice_path)
        self.assertEqual(view['authoring_stage']['stage'], 'depiction')
        self.assertEqual(view['authoring_stage']['next_stage'], 'prepare')
        self.assertFalse(view['authoring_stage']['structural_ready'])
        task, scope = view['task'], view['authoring_scope']
        target = view['choices']['target']
        issued = route_reading.issue(task['route'], task['features'],
            execution=task['execution'], studio=self.root, stream=io.StringIO(),
            operation=production_reading_scope.operation(scope['stage'], task['execution']),
            authoring_scope=scope, model=target['model'], service=target.get('service'))
        choices = c.load(self.root / choice_path)
        choices['reading']['reading_key'] = issued['reading_key']
        f.write(self.root / choice_path, choices)
        ready = production_inputs.authoring_view(self.root, choice_path)
        self.assertTrue(ready['authoring_stage']['structural_ready'], ready['authoring_stage'])
        continued = plans.advance(self.root, plan)
        self.assertEqual(continued['items'][0]['current']['stage'], 'prepare')
        self.assertEqual(c.load(self.root / choice_path)['authoring_stage'], 'prepare')
        self.assertIsNone(continued['items'][0]['run'])


class BatchPlanConditionCases(unittest.TestCase):
    setUp = batch_cases.BatchTests.setUp
    side_reference_prompt = batch_cases.BatchTests.side_reference_prompt

    def test_independent_panels_reach_their_own_answer_without_waiting_for_the_first(self):
        import sheet_batch
        import transport_synthetic
        task = c.load(self.root / 'task.json')
        task['recording']['slot'] = 'canon.side'
        f.write(self.root / 'side-task.json', task)
        self.manifest['requests'].append({'request_id': 'canon.side', 'resolved_slot_id': 'canon.side',
            'result_file': 'side.png', 'target': {'generation_w': 32, 'generation_h': 32},
            'generation_stage': 1, 'required_accepted_reference_results': []})
        self.plan['panels'].append({'request_id': 'canon.side', 'task': 'side-task.json', 'references': []})
        f.write(self.root / 'panel-fill-requests.json', self.manifest)
        f.write(self.root / 'batch-plan.json', self.plan)
        (self.root / 'batch.json').unlink()
        sheet_batch.initialize(self.root, 'batch-plan.json', 'batch.json')
        f.write(self.root / 'work-request.json', {'source': {'batch': 'batch.json'},
            'result': {'scope': 'sheet', 'influence': 'identity'}})
        plan = plans.create(self.root, 'work-request.json')['plan']
        with patch.object(transport_synthetic, 'send', side_effect=AssertionError('Unanswered panels must not send')):
            report = plans.advance(self.root, plan)
        state = c.load(self.root / plan)
        panels = state['items']['item-1']['panels']
        self.assertEqual(set(panels), {'canon.primary', 'canon.side'}, report)
        for panel in panels.values():
            self.assertEqual(panel['phase'], 'execution', panel)
            self.assertTrue((self.root / panel['answers']['execution']['file']).is_file())

    def test_adopted_anchor_unlocks_the_dependent_batch_from_the_same_plan(self):
        import sheet_batch
        import sheet_artifacts
        import transport_synthetic
        import work_ledger
        from PIL import Image
        from sheet_artifacts_smoke_test import make_artifact
        anchor = make_artifact(self.sheet, marker='source', size=(32, 32))
        sheet_artifacts.register_candidates(self.sheet, [('canon.primary', anchor)])
        specification = c.load(self.root / 'spec.json')
        specification['render_intent']['execution_mode'] = 'reference-guided'
        f.write(self.root / 'spec.json', specification)
        task = c.load(self.root / 'task.json')
        task['recording']['slot'] = 'canon.side'
        self.side_reference_prompt(task, anchor)
        f.write(self.root / 'side-task.json', task)
        self.manifest['requests'].append({'request_id': 'canon.side', 'resolved_slot_id': 'canon.side',
            'result_file': 'side.png', 'target': {'generation_w': 32, 'generation_h': 32},
            'generation_stage': 2, 'required_accepted_reference_results': ['canon.primary']})
        self.plan['panels'] = [{'request_id': 'canon.side', 'task': 'side-task.json',
            'references': [{'slot': 'canon.primary', 'artifact_id': None, 'role': 'identity'}]}]
        f.write(self.root / 'panel-fill-requests.json', self.manifest)
        f.write(self.root / 'batch-plan.json', self.plan)
        (self.root / 'batch.json').unlink()
        sheet_batch.initialize(self.root, 'batch-plan.json', 'batch.json')
        blocked = sheet_batch.advance(self.root, 'batch.json')['panels']['canon.side']
        self.assertEqual(blocked['status'], 'blocked')
        self.assertIsNone(blocked['run'])
        f.write(self.root / 'work-request.json', {'items': [
            {'name': 'anchor', 'source': {'kind': 'sheet', 'sheet': self.sheet.relative_to(self.root).as_posix(),
                'slot': 'canon.primary', 'artifact': anchor['artifact_id']},
                'result': {'scope': 'sheet', 'influence': 'identity'}},
            {'name': 'dependent', 'source': {'batch': 'batch.json'},
                'result': {'scope': 'sheet', 'influence': 'identity'}, 'after': ['anchor']}],
            'work_steps': {'1': 'prepared', '2': 'results', '3': 'verified'}})
        plan = plans.create(self.root, 'work-request.json')['plan']
        first = plans.advance(self.root, plan)
        self.assertEqual(first['items'][1]['phase'], 'dependency')
        file = first['items'][0]['current']['answer_file']
        answer = c.load(self.root / file)
        answer['reason'] = 'The synthetic instruction selects this observed anchor for the dependent view.'
        answer['approval'].update(actor=fixtures.ACTOR, mode='direct',
            evidence={'path': 'fixture-authority-basis.txt', 'locator': 'whole synthetic declaration'})
        answer['review'].update(observation='An actual retained synthetic PNG supplies the declared anchor.',
            conclusion='Suitable only for this synthetic source-dependency check.', limitations=['No artwork-quality claim.'])
        f.write(self.root / file, answer)
        with patch.object(transport_synthetic, 'send', side_effect=AssertionError('Dependent execution remains unanswered')):
            report = plans.advance(self.root, plan)
        self.assertEqual(report['items'][0]['state'], 'complete', report)
        side = sheet_batch.load(self.root, 'batch.json')['panels']['canon.side']
        self.assertEqual(side['status'], 'approval-required', report)
        self.assertIsNotNone(side['run'])
        self.assertEqual(side['selected_references'][0]['artifact'], anchor)
        self.assertEqual(c.load(self.sheet)['slots']['canon.primary']['current']['artifact']['artifact_id'],
                         anchor['artifact_id'])
        run = side['run']
        observation = 'Pillow decodes the retained dependent-panel PNG at 32 by 32 pixels.'
        reviewed = None
        with patch.object(transport_synthetic, 'send', wraps=transport_synthetic.send) as send:
            for phase in ('execution', 'observe', 'review', 'curation'):
                self.assertNotEqual(report['state'], 'blocked', report)
                dependent = report['items'][1]
                self.assertEqual(dependent['phase'], 'batch', dependent)
                self.assertEqual(dependent['current']['panel'], 'canon.side')
                saved_panel = c.load(self.root / plan)['items']['dependent']['panels']['canon.side']
                self.assertEqual(saved_panel['phase'], phase, saved_panel)
                self.assertEqual(saved_panel['run'], run)
                file = dependent['current']['answer_file']
                answer = c.load(self.root / file)
                if phase == 'execution':
                    answer['reason'] = 'The synthetic instruction authorizes this dependent view of the adopted anchor.'
                    for stop in answer['stop_assessments']:
                        stop.update(clear=True, evidence='The explicit synthetic instruction covers this exact request.')
                    if 'approval' in answer:
                        answer['approval'].update(actor=fixtures.ACTOR, mode='direct',
                            evidence={'path': 'fixture-authority-basis.txt', 'locator': 'whole'})
                    else:
                        answer['request_decision']['principal_approval'] = {
                            'path': 'fixture-authority-basis.txt', 'locator': 'whole'}
                    fixtures.assess_rendition(answer['request_decision']['rendition_review'])
                elif phase == 'observe':
                    image = dependent['current']['workspace']['candidate']['files'][0]['path']
                    with Image.open(image) as measured:
                        self.assertEqual(measured.size, (32, 32))
                        self.assertEqual(measured.format, 'PNG')
                    answer['reviewer'] = fixtures.ACTOR
                    answer['observations'][0].update(observation=observation,
                        interpretation='This directly measures the declared synthetic output criterion.',
                        limitations=['No artwork quality or identity resemblance is claimed.'])
                elif phase == 'review':
                    self.assertEqual(answer['observations'][0]['observation'], observation)
                    for check in answer['checks'].values():
                        check.update(verdict='pass', reason='The retained observation verifies the declared PNG dimensions.')
                    answer['conclusion'] = 'This dependent panel satisfies its measurable synthetic criterion.'
                else:
                    reviewed = [row for row in store.event_rows(self.root, run) if row['event'] == 'review']
                    self.assertEqual(len(reviewed), 1)
                    answer['reason'] = 'The synthetic instruction adopts this reviewed dependent view into its sheet slot.'
                    answer['approval'].update(actor=fixtures.ACTOR, mode='direct',
                        evidence={'path': 'fixture-authority-basis.txt', 'locator': 'whole'})
                    for stop in answer['stop_assessments']:
                        stop.update(clear=True, evidence='The actual synthetic instruction covers this sheet use.')
                    if 'continuity_decision' in answer:
                        answer['continuity_decision'].update(character_id='robot', continuity='recurring')
                f.write(self.root / file, answer)
                report = plans.advance(self.root, plan)
            self.assertEqual(report['state'], 'complete', report)
            self.assertTrue(report['verification']['ok'], report)
            self.assertEqual(send.call_count, 1)
        self.assertIsNone(work_ledger.read_current(self.root))
        rows = store.event_rows(self.root, run)
        for event in ('dispatch-claim', 'candidate', 'review', 'selection', 'slot-acceptance',
                      'completion', 'adoption-claim', 'adoption-result'):
            self.assertEqual(sum(row['event'] == event for row in rows), 1, event)
        self.assertEqual([row for row in rows if row['event'] == 'review'], reviewed)
        side = sheet_batch.load(self.root, 'batch.json')['panels']['canon.side']
        saved_panel = c.load(self.root / plan)['items']['dependent']['panels']['canon.side']
        self.assertEqual((side['status'], saved_panel['status']), ('received', 'complete'))
        self.assertEqual(side['run'], run)
        self.assertEqual(saved_panel['run'], run)
        self.assertEqual(side['selected_references'][0]['artifact'], anchor)
        sheet = c.load(self.sheet)
        self.assertEqual(sheet['slots']['canon.primary']['current']['artifact']['artifact_id'], anchor['artifact_id'])
        self.assertEqual(sheet['slots']['canon.side']['current']['artifact'], side['artifact'])
        with patch.object(transport_synthetic, 'send', side_effect=AssertionError('A completed batch must not resend')):
            again = plans.advance(self.root, plan)
        self.assertEqual(again['state'], 'complete', again)
        self.assertEqual(rows, store.event_rows(self.root, run))
        self.assertEqual(c.load(self.sheet), sheet)


class AuthoredPlanConditionCases(unittest.TestCase):
    setUp = authored_cases.AuthoredContinuationTests.setUp
    write = authored_cases.AuthoredContinuationTests.write

    def author_review_requirement(self):
        self.choices['authoring']['task']['authored']['requirements'] = ['save', 'delivery', 'review']
        self.write(self.choices_path, self.choices)

    def make_plan(self, source):
        self.write('work-request.json', {'source': source,
            'result': {'scope': 'save', 'path': 'exports/description.txt'}, 'work_steps': {'1': 'results'}})
        return plans.create(self.root, 'work-request.json')['plan']

    def fill_observation(self, report):
        file = report['items'][0]['current']['answer_file']
        answer = c.load(self.root / file)
        answer['reviewer'] = fixtures.ACTOR
        answer['observations'][0].update(observation='The saved text says that a brass key rests on a wooden table.',
            interpretation='The described subject and support surface are explicit.',
            limitations=['This observes authored text only; no generated artwork is claimed.'])
        self.write(file, answer)
        return answer

    def test_new_authored_save_delivers_then_observes_and_reviews_in_one_plan(self):
        import work_ledger
        self.author_review_requirement()
        plan = self.make_plan({'choices': self.choices_path})
        report = plans.advance(self.root, plan)
        self.assertEqual(report['items'][0]['phase'], 'observe', report)
        run = report['items'][0]['run']
        first = report['items'][0]['current']
        self.assertNotIn('criteria', first)
        self.assertNotIn('basis', first['workspace'])
        self.assertEqual((self.root / 'exports/description.txt').read_bytes(),
                         (self.root / 'description.txt').read_bytes())
        observed = self.fill_observation(report)
        reviewed = plans.advance(self.root, plan)
        self.assertEqual(reviewed['items'][0]['phase'], 'review', reviewed)
        file = reviewed['items'][0]['current']['answer_file']
        answer = c.load(self.root / file)
        self.assertEqual(answer['observations'], observed['observations'])
        for criterion in answer['checks'].values():
            criterion.update(verdict='pass', reason='The actual saved sentence identifies the brass key and table.')
        answer['conclusion'] = 'The observed text meets this explicitly synthetic description criterion.'
        self.write(file, answer)
        complete = plans.advance(self.root, plan)
        self.assertEqual(complete['state'], 'complete', complete)
        self.assertIsNone(work_ledger.read_current(self.root))
        rows = store.event_rows(self.root, run)
        for event in ('authored-save', 'authored-delivery', 'authored-review', 'completion'):
            self.assertEqual(sum(row['event'] == event for row in rows), 1)
        self.assertEqual(plans.advance(self.root, plan)['state'], 'complete')
        self.assertEqual(store.event_rows(self.root, run), rows)

    def test_ready_plan_choices_follow_the_plan_once_and_siblings_keep_their_own_action(self):
        import work_ledger
        sibling = authored_cases.authoring_fixtures.authoring_inputs(
            self.root, 'task.json', 'sibling')
        sibling_choices = c.load(self.root / sibling['choices_file'])
        sibling_choices['reading']['reading_key'] = self.choices['reading']['reading_key']
        self.write(sibling['choices_file'], sibling_choices)

        task_id = work_ledger.read_current(self.root)['task_id']
        plan = self.make_plan({'choices': self.choices_path})
        sibling_report = production_inputs.inspect_inputs(self.root, choices_path=sibling['choices_file'])
        sibling_action = sibling_report['next_actions'][0]
        self.assertNotEqual(sibling_action['command'], 'advance', sibling_report)
        if sibling_action['command'] in {'save', 'prepare'}:
            self.assertEqual(sibling_action['args']['choices'], sibling['choices_file'])

        ready = production_inputs.inspect_inputs(self.root, choices_path=self.choices_path)
        action = ready['next_actions'][0]
        self.assertEqual(action['command'], 'advance', ready)
        self.assertIn('--file', action['argv'])
        self.assertIn(plan, action['argv'])

        followed = subprocess.run(action['argv'], cwd=self.root, capture_output=True,
                                  text=True, encoding='utf-8', check=False)
        self.assertEqual(followed.returncode, 0, followed.stdout + followed.stderr)
        completed = json.loads(followed.stdout)
        self.assertEqual(completed['state'], 'complete', completed)
        self.assertIsNone(work_ledger.read_current(self.root))
        runs = store.runs(self.root, task_id=task_id)
        self.assertEqual(len(runs), 1, runs)
        self.assertEqual(completed['items'][0]['run'], runs[0]['run_id'])
        self.assertEqual((self.root / 'exports/description.txt').read_bytes(),
                         (self.root / 'description.txt').read_bytes())

    def test_new_plan_authoring_inspection_returns_without_recursive_plan_inspection(self):
        fixtures.current_request(self.root,
            'Create a synthetic authored paragraph that names the brass key and wooden table.')
        plan = self.make_plan({'request': 'fixture-current-request.txt',
                               'route': 'development', 'execution': 'authored'})
        report = plans.advance(self.root, plan)
        current = report['items'][0]['current']
        self.assertEqual(report['items'][0]['phase'], 'authoring', report)
        self.assertIn('inspection', current)
        self.assertEqual(current['inspection']['authoring_stage']['stage'], 'definition')

    def test_blocked_plan_publication_retries_through_plan_after_input_repair(self):
        import work_ledger
        task_id = work_ledger.read_current(self.root)['task_id']
        prompt_path = self.choices['authoring']['delivery']['file']
        original_prompt = (self.root / prompt_path).read_text(encoding='utf-8')
        self.write(prompt_path, 'SYNTHETIC_REPAIR_MARKER\n')
        plan = self.make_plan({'choices': self.choices_path})

        before = production_inputs.inspect_inputs(self.root, choices_path=self.choices_path)
        self.assertEqual(before['next_actions'][0]['command'], 'advance', before)
        original_prepare = operations.prepare

        def reject_marked_publication(root, task=None, *, choices=None, identity=None):
            if choices == self.choices_path and 'SYNTHETIC_REPAIR_MARKER' in (
                    self.root / prompt_path).read_text(encoding='utf-8'):
                raise ValueError('Synthetic compiler rejection of the marked authored input.')
            return original_prepare(root, task, choices=choices, identity=identity)

        with patch.object(operations, 'prepare', side_effect=reject_marked_publication):
            blocked = plans.advance(self.root, plan)
        self.assertEqual(blocked['state'], 'blocked', blocked)
        self.assertEqual(blocked['items'][0]['state'], 'blocked', blocked)
        self.assertIn(blocked['items'][0]['phase'], {'source', 'authoring'}, blocked)
        self.assertIsNone(blocked['items'][0]['run'])
        self.assertEqual(store.runs(self.root, task_id=task_id), [])

        self.write(prompt_path, original_prompt)
        after = production_inputs.inspect_inputs(self.root, choices_path=self.choices_path)
        action = after['next_actions'][0]
        self.assertEqual(action['command'], 'advance', after)
        followed = subprocess.run(action['argv'], cwd=self.root, capture_output=True,
                                  text=True, encoding='utf-8', check=False)
        self.assertEqual(followed.returncode, 0, followed.stdout + followed.stderr)
        completed = json.loads(followed.stdout)
        self.assertEqual(completed['state'], 'complete', completed)
        self.assertIsNone(work_ledger.read_current(self.root))
        runs = store.runs(self.root, task_id=task_id)
        self.assertEqual(len(runs), 1, runs)
        self.assertEqual(completed['items'][0]['run'], runs[0]['run_id'])
        self.assertEqual((self.root / 'exports/description.txt').read_bytes(),
                         original_prompt.encode('utf-8'))

    def test_existing_unassessed_authored_review_returns_to_current_observation(self):
        self.author_review_requirement()
        run = operations.prepare(self.root, choices=self.choices_path)['run']
        review = operations.draft_review(self.root, run)
        review.update(reviewer=fixtures.ACTOR, observations=[{'evidence': 'candidate',
            'locator': {'kind': 'whole'}, 'observation': 'The saved sentence mentions a key.',
            'interpretation': 'The criterion still needs a complete assessment.', 'limitations': ['Incomplete review.']}],
            conclusion='This actual synthetic review deliberately leaves its criterion unassessed.')
        for criterion in review['checks']:
            criterion.update(verdict='not-assessed', observation_indices=[0], reason='Assessment remains open.')
        self.write('incomplete-review.json', review)
        operations.review_authored(self.root, run, 'incomplete-review.json')
        plan = self.make_plan({'run': run})
        report = plans.advance(self.root, plan)
        self.assertEqual(report['items'][0]['phase'], 'observe', report)
        self.assertEqual(report['items'][0]['state'], 'needs-input')
        self.assertFalse(any(row['event'] == 'completion' for row in store.event_rows(self.root, run)))


class ThreeVariantPlanCase(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name)
        self.enterContext(fixtures.scratch_home(base / 'home'))
        from catalog_retrieval import runtime
        self.addCleanup(runtime.configure_pack_runtime, None)
        self.case = f.create(base / 'studio', base / 'runtime', with_alternate=True)
        self.root = self.case['root']
        task = c.load(self.root / 'task.json')
        task['recording'].update(slot='canon.primary', sheet_panel=True, subject_map={'robot': 'robot'})
        task['generation']['continuity']['robot'] = 'undecided'
        f.write(self.root / 'task.json', task)
        self.run = operations.prepare(self.root, 'task.json')['run']

    def test_prompt_reference_and_model_variants_keep_sources_through_execution_and_adoption(self):
        from generation_references import prepare_references
        from prompt_retrieval import settle_retrieval_record
        import production_variation
        import test_production_variation
        import transport_synthetic
        import work_ledger
        parent = operations.read_run(self.root, self.run)
        original_work = c.decode(production_variation._captured(parent, parent.prepared['task']['work_basis']))
        original_sources = {}
        for source in parent.prepared['task']['sources']:
            if not source.get('applications'):
                continue
            dependency = next(row for row in parent.prepared['dependencies'] if row['path'] == source['path'])
            original_sources[source['id']] = (copy.deepcopy(source), dependency['sha256'])
        prompt = f.PROMPT + ' The same robot remains alone.'
        retrieval = settle_retrieval_record(c.load(self.root / 'retrieval.json'), prompt=prompt,
                                            plot=c.load(self.root / 'plot.json'))
        f.write(self.root / 'variants/prompt-retrieval.json', retrieval)
        f.write(self.root / 'variants/prompt-change.json', {'changes': {'prompt': prompt,
            'retrieval-record': {'path': 'variants/prompt-retrieval.json'}},
            'reason': 'The synthetic author revises only this prompt expression.'})
        prompt_run = production_variation.derive(self.root, self.run,
            changes_file='variants/prompt-change.json', prepare=True)['run']

        c.atomic(self.root / 'variants/palette.png', transport_synthetic._png(32, 32, b'\x50\x78\xa0'))
        references = prepare_references([{'role': 'palette', 'source': {'kind': 'supplied-file',
            'reference_id': 'synthetic-palette', 'resolved_path': str(self.root / 'variants/palette.png')}}],
            model=f.MODEL_ID, output_dir=self.root / 'variants/reference-preparation')
        f.write(self.root / 'variants/references.json', references)
        changes = test_production_variation.VariationTests.reference_changes(
            self, references, 'variants/references.json')
        changes['recording'] = {**copy.deepcopy(parent.prepared['task']['recording']), 'slot': 'canon.side'}
        f.write(self.root / 'variants/reference-change.json', {'changes': changes,
            'reason': 'The synthetic author adds this scoped palette carrier and its explicit delivery instructions.'})
        reference_run = production_variation.derive(self.root, self.run,
            changes_file='variants/reference-change.json', prepare=True)['run']

        alternate_path = f.alternate_task(self.root)
        alternate = c.load(self.root / alternate_path)
        alternate['recording']['slot'] = 'canon.back'
        f.write(self.root / alternate_path, alternate)
        model_run = production_variation.retarget(self.root, self.run, alternate_path,
            reason='The synthetic author chooses the alternate saved model and reevaluates its evidence.', prepare=True)['run']
        variants = {'prompt': prompt_run, 'reference': reference_run, 'model': model_run}
        loaded_variants = {name: operations.read_run(self.root, run) for name, run in variants.items()}
        self.assertEqual(loaded_variants['prompt'].artifacts['request-contract.json']['request']['prompt'], prompt)
        self.assertEqual(len(loaded_variants['reference'].artifacts['request-contract.json']['media']), 1)
        self.assertEqual(loaded_variants['model'].artifacts['package.json']['production_spec']['target_model'],
                         f.ALTERNATE_MODEL_ID)
        for loaded in loaded_variants.values():
            self.assertEqual(loaded.prepared['parent']['run'], self.run)
            retained_work = c.decode(production_variation._captured(loaded, loaded.prepared['task']['work_basis']))
            # The current amendment request changes, while every previously
            # acquired source, including the original request, remains exact.
            for original in original_work['sources'].values():
                self.assertIn(original, retained_work['sources'].values())
            for identifier, (source, digest) in original_sources.items():
                retained = next(row for row in loaded.prepared['task']['sources'] if row['id'] == identifier)
                dependency = next(row for row in loaded.prepared['dependencies'] if row['path'] == retained['path'])
                self.assertEqual(dependency['sha256'], digest)
                for key in ('role', 'disposition', 'locator'):
                    self.assertEqual(retained.get(key), source.get(key))
        before = {name: store.event_rows(self.root, run) for name, run in variants.items()}
        self.assertTrue(all(not rows for rows in before.values()))
        task = work_ledger.read_current(self.root)
        f.write(self.root / 'three-variants.json', {
            'items': [{'name': name, 'source': {'run': run},
                       'result': {'scope': 'sheet', 'influence': 'identity'}} for name, run in variants.items()],
            'work_steps': {str(step['n']): 'results' for step in task['steps']}})
        plan = plans.create(self.root, 'three-variants.json')['plan']
        # Execution and review must use the retained commission even when its
        # original editable location is no longer available.
        (self.root / 'brief.md').unlink()
        observed_phases = {name: [] for name in variants}
        with patch.object(transport_synthetic, 'send', wraps=transport_synthetic.send) as send:
            report = plans.advance(self.root, plan)
            for _ in range(8):
                if report['state'] == 'complete':
                    break
                self.assertNotEqual(report['state'], 'blocked', report)
                for item in report['items']:
                    if item['state'] == 'complete':
                        continue
                    phase = item['phase']
                    observed_phases[item['name']].append(phase)
                    file = item['current']['answer_file']
                    answer = c.load(self.root / file)
                    if phase == 'execution':
                        answer['reason'] = 'The actual synthetic instruction authorizes this exact variant request.'
                        for stop in answer['stop_assessments']:
                            stop.update(clear=True, evidence='The explicit synthetic instruction covers this request.')
                        if 'approval' in answer:
                            answer['approval'].update(actor=fixtures.ACTOR, mode='direct',
                                evidence={'path': 'fixture-authority-basis.txt', 'locator': 'whole'})
                        else:
                            answer['request_decision']['principal_approval'] = {
                                'path': 'fixture-authority-basis.txt', 'locator': 'whole'}
                        fixtures.assess_rendition(answer['request_decision']['rendition_review'])
                    elif phase == 'observe':
                        from PIL import Image
                        image = item['current']['workspace']['candidate']['files'][0]['path']
                        with Image.open(image) as measured:
                            self.assertEqual(measured.size, (32, 32))
                        answer['reviewer'] = fixtures.ACTOR
                        answer['observations'][0].update(observation='Pillow decodes this retained PNG at 32 by 32 pixels.',
                            interpretation='This directly measures the declared synthetic output criterion.',
                            limitations=['No model artwork quality or source resemblance is claimed.'])
                    elif phase == 'review':
                        for check in answer['checks'].values():
                            check.update(verdict='pass', reason='The retained first observation verifies the declared PNG dimensions.')
                        answer['conclusion'] = 'This synthetic variant satisfies its measurable protocol criterion.'
                    elif phase == 'curation':
                        answer['reason'] = 'The synthetic instruction adopts this reviewed variant into its distinct declared sheet slot.'
                        answer['approval'].update(actor=fixtures.ACTOR, mode='direct',
                            evidence={'path': 'fixture-authority-basis.txt', 'locator': 'whole'})
                        for stop in answer['stop_assessments']:
                            stop.update(clear=True, evidence='The actual synthetic instruction covers this sheet use.')
                        if 'continuity_decision' in answer:
                            answer['continuity_decision'].update(character_id='robot', continuity='recurring')
                    else:
                        self.fail('The public continuation exposed an unexpected phase: ' + phase)
                    f.write(self.root / file, answer)
                report = plans.advance(self.root, plan)
            self.assertEqual(report['state'], 'complete', report)
            self.assertEqual(send.call_count, 3)
        self.assertIsNone(work_ledger.read_current(self.root))
        self.assertEqual(store.event_rows(self.root, self.run), [])
        for name, run in variants.items():
            self.assertEqual(observed_phases[name], ['execution', 'observe', 'review', 'curation'])
            rows = store.event_rows(self.root, run)
            for event in ('dispatch-claim', 'candidate', 'review', 'selection', 'completion', 'adoption-result'):
                self.assertEqual(sum(row['event'] == event for row in rows), 1, (name, event))
            loaded = operations.read_run(self.root, run)
            retained_work = c.decode(production_variation._captured(loaded, loaded.prepared['task']['work_basis']))
            for original in original_work['sources'].values():
                self.assertIn(original, retained_work['sources'].values())
            for identifier, (_, digest) in original_sources.items():
                source = next(row for row in loaded.prepared['task']['sources'] if row['id'] == identifier)
                dependency = next(row for row in loaded.prepared['dependencies'] if row['path'] == source['path'])
                self.assertEqual(dependency['sha256'], digest)


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
