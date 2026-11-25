"""Commissioned work reaches its actual result through one recoverable plan."""
from __future__ import annotations

import copy
import errno
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import execution_contract as c
import production_case_fixtures as f
import production_compiler as compiler
import production_operations as operations
import production_store as store
import production_work_plan as plans
import production_work_review as reviews
import production_curation as curation
import test_production_adoption as adoption
import test_production_authored as authored
import work_ledger
from production_fixtures import ACTOR
from production_diagnostics import ProductionError


class WorkPlanTests(unittest.TestCase):
    setUpClass = classmethod(adoption.AdoptionTests.setUpClass.__func__)
    setUp = adoption.AdoptionTests.setUp

    def plan(self, scope='sheet', *, steps=True):
        task = work_ledger.read_current(self.root)
        request = {'source': {'run': self.run}, 'result': {'scope': scope}}
        if scope in {'sheet', 'catalog'}:
            request['result']['influence'] = 'identity'
        if steps:
            request['work_steps'] = {str(step['n']): 'results' for step in task['steps']}
        f.write(self.root / 'work-request.json', request)
        return plans.create(self.root, 'work-request.json')['plan']

    def answer(self, report):
        path = report['items'][0]['current']['answer_file']
        value = c.load(self.root / path)
        value['reason'] = 'The explicit synthetic instruction chooses this reviewed fixture for the selected use.'
        value['approval'].update(actor=ACTOR, mode=value['approval']['mode'] or 'direct',
            evidence={'path': 'adoption-basis.txt', 'locator': 'whole synthetic instruction'})
        for assessment in value['stop_assessments']:
            assessment.update(clear=True, evidence='The explicit synthetic instruction covers this use.')
        if 'continuity_decision' in value:
            value['continuity_decision'].update(character_id='robot', continuity='recurring')
        f.write(self.root / path, value)
        return path

    def test_one_answer_completes_selection_adoption_views_and_bound_work(self):
        with patch.object(compiler, 'acquire_publication', wraps=compiler.acquire_publication) as publication:
            path = self.plan()
            self.assertEqual(publication.call_count, 1)
        with patch.object(compiler, 'acquire_publication', wraps=compiler.acquire_publication) as publication:
            first = plans.advance(self.root, path)
            self.assertEqual(publication.call_count, 1)
        self.assertEqual(first['items'][0]['phase'], 'curation', first)
        self.answer(first)
        with patch.object(compiler, 'acquire_publication', wraps=compiler.acquire_publication) as publication:
            report = plans.advance(self.root, path)
            self.assertEqual(publication.call_count, 1)
        self.assertEqual(report['state'], 'complete', report)
        self.assertTrue(report['verification']['ok'])
        self.assertIsNone(work_ledger.read_current(self.root))
        events = store.event_rows(self.root, self.run)
        for event in ('selection', 'slot-acceptance', 'completion', 'adoption-result'):
            self.assertEqual(sum(row['event'] == event for row in events), 1)
        for operation in (plans.advance, plans.inspect, plans.refresh):
            with self.subTest(operation=operation.__name__), \
                 patch.object(compiler, 'acquire_publication', wraps=compiler.acquire_publication) as publication:
                again = operation(self.root, path)
                self.assertEqual(again['state'], 'complete')
                self.assertEqual(publication.call_count, 1)
        self.assertEqual(events, store.event_rows(self.root, self.run))

    def test_existing_unbound_work_is_exposed_and_not_marked_from_guesswork(self):
        path = self.plan(steps=False)
        self.answer(plans.advance(self.root, path))
        report = plans.advance(self.root, path)
        self.assertEqual(report['state'], 'work-required', report)
        self.assertTrue(report['remaining_work']['steps'])
        self.assertTrue(all(not row['done_at'] for row in work_ledger.read_current(self.root)['steps']))

    def test_formal_adoption_waits_for_open_work_question_before_closing(self):
        path = self.plan()
        question = work_ledger.block(self.root, 'Which synthetic archive note should accompany this result?')['questions'][-1]
        self.answer(plans.advance(self.root, path))
        waiting = plans.advance(self.root, path)
        self.assertEqual(waiting['state'], 'work-required', waiting)
        self.assertEqual(waiting['remaining_work']['questions'][0]['question_id'], question['question_id'])
        self.assertIsNotNone(work_ledger.read_current(self.root))
        events = store.event_rows(self.root, self.run)
        self.assertEqual(sum(row['event'] == 'adoption-result' for row in events), 1)
        work_ledger.respond(self.root, question['question_id'], 'Use the existing synthetic fixture note.', actor=ACTOR)
        completed = plans.advance(self.root, path)
        self.assertEqual(completed['state'], 'complete', completed)
        self.assertEqual(store.event_rows(self.root, self.run), events)

    def test_suspended_plan_finishes_only_its_actual_owner(self):
        path = self.plan()
        owner = work_ledger.read_current(self.root)['task_id']
        self.answer(plans.advance(self.root, path))
        work_ledger.suspend(self.root, reason='Continue independent fixture work while this result remains retained.')
        independent = work_ledger.begin(self.root, 'Unrelated synthetic task.', ['Keep this task open.'])
        completed = plans.advance(self.root, path)
        self.assertEqual(completed['state'], 'complete', completed)
        self.assertEqual(work_ledger.read_current(self.root), independent)
        self.assertEqual(c.load(work_ledger.task_path(self.root, owner))['work_state'], 'completed')

    def test_failed_view_validation_retains_results_without_closing_the_work(self):
        path = self.plan()
        self.answer(plans.advance(self.root, path))
        with patch('validate_studio.validate', return_value=['Synthetic inconsistent derived view']):
            blocked = plans.advance(self.root, path)
        self.assertEqual(blocked['state'], 'verification-required', blocked)
        self.assertFalse(blocked['verification']['ok'])
        self.assertIsNotNone(work_ledger.read_current(self.root))
        events = store.event_rows(self.root, self.run)
        completed = plans.advance(self.root, path)
        self.assertEqual(completed['state'], 'complete', completed)
        self.assertEqual(store.event_rows(self.root, self.run), events)

    def test_failed_projection_blocks_verified_milestone_even_when_studio_validation_passes(self):
        path = self.plan()
        task = work_ledger.read_current(self.root)
        work_ledger.bind_plan(self.root, task['task_id'], path, {str(step['n']): 'verified' for step in task['steps']})
        self.answer(plans.advance(self.root, path))
        failure = {'ok': False, 'diagnostics': [{'projection': 'gallery', 'message': 'Synthetic missing gallery input.'}]}
        with patch('studio_activity.refresh', return_value=failure), patch('validate_studio.validate', return_value=[]):
            blocked = plans.advance(self.root, path)
        self.assertEqual(blocked['state'], 'verification-required', blocked)
        self.assertFalse(blocked['verification']['ok'])
        self.assertIn(path, blocked['verification']['next_action']['argv'])
        self.assertTrue(all(not step['done_at'] for step in work_ledger.read_current(self.root)['steps']))
        events = store.event_rows(self.root, self.run)
        completed = plans.advance(self.root, path)
        self.assertEqual(completed['state'], 'complete', completed)
        self.assertEqual(store.event_rows(self.root, self.run), events)

    def test_prepare_only_finishes_without_selection_or_new_submission(self):
        path = self.plan('prepared-input')
        before = store.event_rows(self.root, self.run)
        report = plans.advance(self.root, path)
        self.assertEqual(report['state'], 'complete', report)
        self.assertEqual(before, store.event_rows(self.root, self.run))

    def test_plan_operations_detect_saved_publication_edits_between_calls(self):
        path = self.plan('prepared-input')
        self.assertEqual(plans.advance(self.root, path)['state'], 'complete')
        consumer = operations.run_dir(self.root, self.run) / 'consumer.json'
        original, before = consumer.read_bytes(), consumer.stat()
        self.assertTrue(original.endswith(b'\n'))
        consumer.write_bytes(original[:-1] + b'\t')
        os.utime(consumer, ns=(before.st_atime_ns, before.st_mtime_ns))
        request = {'source': {'run': self.run}, 'result': {'scope': 'prepared-input'}}
        calls = {'create': lambda: plans.create(self.root, request=request),
                 'inspect': lambda: plans.inspect(self.root, path),
                 'refresh': lambda: plans.refresh(self.root, path),
                 'advance': lambda: plans.advance(self.root, path)}
        for name, operation in calls.items():
            with self.subTest(operation=name), self.assertRaises(ProductionError) as caught:
                operation()
            self.assertEqual(caught.exception.diagnostic.code, 'ARTIFACT_CORRUPT')

    def test_plan_definition_change_does_not_retarget_saved_work(self):
        path = self.plan()
        definition = self.root / path
        definition = definition.parent / 'definition.json'
        value = c.load(definition)
        value['items'][0]['result']['scope'] = 'delivery-only'
        f.write(definition, value)
        with self.assertRaisesRegex(ValueError, 'definition changed'):
            plans.advance(self.root, path)

    def test_unchanged_answer_returns_normal_continuation_without_authorization_error(self):
        path = self.plan()
        owner = work_ledger.read_current(self.root)['task_id']
        owned_paths = (work_ledger.task_path(self.root, owner), self.root / 'work/current.json')
        owned_before = {file: file.read_bytes() for file in owned_paths}
        before = store.event_rows(self.root, self.run)
        one = plans.advance(self.root, path)
        two = plans.advance(self.root, path)
        self.assertEqual(one['items'][0]['current']['answer_file'], two['items'][0]['current']['answer_file'])
        self.assertIsNone(one['continuation_observation']['unchanged_since_previous'])
        self.assertTrue(two['continuation_observation']['unchanged_since_previous'])
        self.assertTrue(two['continuation_observation']['observed_now'])
        inspected = plans.inspect(self.root, path)
        self.assertFalse(inspected['continuation_observation']['observed_now'])
        self.assertNotEqual(two['state'], 'blocked')
        self.assertEqual(before, store.event_rows(self.root, self.run))
        self.assertEqual({file: file.read_bytes() for file in owned_paths}, owned_before)

    def test_interrupted_milestone_replay_restores_the_same_task_and_pointer(self):
        path = self.plan()
        plan = c.load(self.root / path)
        owner = plan['task_id']
        saved = work_ledger.task_path(self.root, owner)
        pointer = self.root / 'work/current.json'
        publish = c.atomic

        def interrupted(file, raw, **kwargs):
            if file == pointer:
                raise OSError('Synthetic interruption before current task publication')
            return publish(file, raw, **kwargs)

        with patch.object(c, 'atomic', side_effect=interrupted), \
                self.assertRaisesRegex(OSError, 'Synthetic interruption'):
            work_ledger.record_plan_stage(self.root, owner, 'results', plan['plan_id'], {'run': self.run})
        retained = c.load(saved)
        self.assertTrue(all(row['done_at'] for row in retained['steps']))
        self.assertTrue(all(row['done_at'] is None for row in c.load(pointer)['steps']))
        ledger = (self.root / 'work/ledger.jsonl').read_bytes()
        committed = saved.read_bytes()

        repeated = work_ledger.record_plan_stage(self.root, owner, 'results', plan['plan_id'], {'run': self.run})
        self.assertEqual(repeated, retained)
        self.assertEqual(saved.read_bytes(), committed)
        self.assertEqual(pointer.read_bytes(), c.encoded(retained))
        self.assertEqual((self.root / 'work/ledger.jsonl').read_bytes(), ledger)
        repaired = pointer.read_bytes()
        work_ledger.record_plan_stage(self.root, owner, 'results', plan['plan_id'], {'run': self.run})
        self.assertEqual(saved.read_bytes(), committed)
        self.assertEqual(pointer.read_bytes(), repaired)
        self.assertEqual((self.root / 'work/ledger.jsonl').read_bytes(), ledger)

    def test_an_unchanged_milestone_preserves_an_absent_current_pointer(self):
        path = self.plan()
        plan = c.load(self.root / path)
        owner = plan['task_id']
        saved = work_ledger.task_path(self.root, owner)
        pointer = self.root / 'work/current.json'
        pointer.unlink()
        before = saved.read_bytes()
        work_ledger.record_plan_stage(self.root, owner, 'prepared', plan['plan_id'], {'run': self.run})
        self.assertFalse(pointer.exists())
        self.assertIsNone(work_ledger.read_current(self.root))
        self.assertEqual(saved.read_bytes(), before)

    def test_typed_plan_selects_a_result_without_creating_or_authorizing_an_answer(self):
        import production_workflow
        parser = production_workflow.build_parser()
        args = parser.parse_args(['plan', '--root', str(self.root), '--run', self.run,
                                  '--scope', 'sheet', '--influence', 'identity'])
        request = plans.request_from_arguments(self.root, args)
        before = store.event_rows(self.root, self.run)
        report = plans.create(self.root, request=request)
        path = self.root / report['plan']
        self.assertEqual(c.load(path.parent / 'request.json'),
            {'source': {'run': self.run}, 'result': {'scope': 'sheet', 'influence': 'identity'}})
        self.assertEqual(before, store.event_rows(self.root, self.run))
        self.assertFalse((self.root / 'work/plan-request.json').exists())
        waiting = plans.advance(self.root, report['plan'])
        self.assertEqual(waiting['items'][0]['phase'], 'curation')
        self.assertEqual(c.load(self.root / waiting['items'][0]['current']['answer_file'])['reason'], '')
        self.assertEqual(before, store.event_rows(self.root, self.run))

    def test_typed_plan_rejects_mixed_declarations_before_work_effects(self):
        import production_workflow
        parser = production_workflow.build_parser()
        before = copy.deepcopy(work_ledger.read_current(self.root))
        for tail in (['--file', 'request.json', '--run', self.run, '--scope', 'sheet'],
                     ['--run', self.run, '--scope', 'sheet'],
                     ['--run', self.run, '--scope', 'sheet', '--influence', 'identity', '--feature', 'vocabulary']):
            args = parser.parse_args(['plan', '--root', str(self.root), *tail])
            with self.assertRaises(ValueError):
                plans.request_from_arguments(self.root, args)
        self.assertEqual(before, work_ledger.read_current(self.root))

    def test_typed_amend_scope_has_one_saved_owner_and_validates_before_work(self):
        import production_workflow
        parser = production_workflow.build_parser()
        f.write(self.root / 'revision.txt', 'Keep the selected subject and change only the numeric controls.')
        before = copy.deepcopy(work_ledger.read_current(self.root))
        args = parser.parse_args(['plan', '--root', str(self.root), '--request-file', 'revision.txt',
            '--from-run', self.run, '--scope', 'prepared-input', '--retain', 'identity',
            '--retain', 'target', '--change', 'controls.parameters'])
        request = plans.request_from_arguments(self.root, args)
        self.assertEqual(request['source']['change_scope'],
                         {'retain': ['identity', 'target'], 'change': ['controls.parameters']})
        self.assertEqual(before, work_ledger.read_current(self.root))
        for replacement in ({'run': self.run, 'change_scope': request['source']['change_scope']},
                            {**request['source'], 'operation': 'compose'},
                            {**request['source'], 'change_scope': {'retain': ['target'], 'change': ['target']}}):
            with self.subTest(source=replacement), self.assertRaises(ValueError):
                plans.create(self.root, request={'source': replacement, 'result': request['result']})
        self.assertEqual(before, work_ledger.read_current(self.root))

    def test_typed_plan_exposes_every_influence_owned_by_the_reference_contract(self):
        import contextlib
        import io
        import production_workflow
        from reference_contract import INTENDED_INFLUENCES
        parser = production_workflow.build_parser()
        for influence in INTENDED_INFLUENCES:
            args = parser.parse_args(['plan', '--root', str(self.root), '--run', self.run,
                                      '--scope', 'sheet', '--influence', influence])
            self.assertEqual(plans.request_from_arguments(self.root, args)['result']['influence'], influence)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parser.parse_args(['plan', '--root', str(self.root), '--run', self.run,
                               '--scope', 'sheet', '--influence', 'scene'])

    def test_wrong_workspace_phase_returns_the_actual_candidate_observation_action(self):
        from production_diagnostics import ProductionError
        from production_workspace import workspace
        with self.assertRaises(ProductionError) as caught:
            workspace(self.root, self.run, phase='decision', candidate=self.candidate)
        diagnostic = caught.exception.diagnostic
        next_action = diagnostic.details['next_action']
        self.assertIn('observe', next_action['argv'])
        self.assertIn(self.candidate, next_action['argv'])
        self.assertIn('next_action', diagnostic.required_action)

    def test_direction_basis_error_names_the_actual_available_source_ids(self):
        import production_plan
        from production_diagnostics import ProductionError
        direction = copy.deepcopy(self.task['direction'])
        direction['basis'] = ['request-is-not-an-applied-source']
        with self.assertRaises(ProductionError) as caught:
            production_plan.validate(direction, self.task['sources'], self.task['criteria'])
        diagnostic = caught.exception.diagnostic
        self.assertEqual(diagnostic.pointer, '$.direction.basis')
        self.assertEqual(diagnostic.details['invalid_sources'], direction['basis'])
        self.assertEqual(diagnostic.details['available_sources'],
                         sorted(row['id'] for row in self.task['sources'] if row['disposition'] == 'applied'))
        self.assertIn('available_sources', diagnostic.required_action)

    def test_direction_criterion_error_names_the_actual_available_criterion_ids(self):
        import production_plan
        from production_diagnostics import ProductionError
        direction = copy.deepcopy(self.task['direction'])
        direction['decisions'][0]['criteria'] = ['A description is not the criterion ID.']
        with self.assertRaises(ProductionError) as caught:
            production_plan.validate(direction, self.task['sources'], self.task['criteria'])
        diagnostic = caught.exception.diagnostic
        self.assertEqual(diagnostic.pointer, '$.direction.decisions[0].criteria')
        self.assertEqual(diagnostic.details['invalid_criteria'], direction['decisions'][0]['criteria'])
        self.assertEqual(diagnostic.details['available_criteria'], sorted(row['id'] for row in self.task['criteria']))
        self.assertIn('available_criteria', diagnostic.required_action)

    def test_dependency_cycle_rejected_before_work_effects(self):
        request = {'items': [
            {'name': 'a', 'source': {'run': self.run}, 'result': {'scope': 'delivery-only'}, 'after': ['b']},
            {'name': 'b', 'source': {'run': self.run}, 'result': {'scope': 'delivery-only'}, 'after': ['a']}]}
        f.write(self.root / 'cycle.json', request)
        before = copy.deepcopy(work_ledger.read_current(self.root))
        with self.assertRaisesRegex(ValueError, 'cycle'):
            plans.create(self.root, 'cycle.json')
        self.assertEqual(before, work_ledger.read_current(self.root))

    def test_named_review_citations_bind_to_actual_criterion_and_candidate(self):
        draft = reviews.draft(self.root, self.run, self.candidate)
        answers = draft['choices']
        answers['reviewer'] = 'Synthetic observer'
        answers['observations'][0].update(observation='A local synthetic image is present.',
            interpretation='This establishes only fixture content.', limitations=['No image quality inference.'])
        for row in answers['checks'].values():
            row.update(verdict='pass', reason='Explicit synthetic test observation.')
        answers['conclusion'] = 'Synthetic local evidence assessed.'
        compiled = reviews.compile_answers(draft['binding'], answers)
        self.assertEqual(compiled['candidate'], self.candidate)
        self.assertTrue(all(row['observation_indices'] == [0] for row in compiled['checks']))
        answers['checks'][next(iter(answers['checks']))]['supports'] = ['missing']
        with self.assertRaisesRegex(ValueError, 'Supports'):
            reviews.compile_answers(draft['binding'], answers)

    def test_first_observer_receives_candidate_without_the_commission_or_criteria(self):
        draft = reviews.observe(self.root, self.run, self.candidate)
        self.assertEqual(set(draft['choices']), {'reviewer', 'observations'})
        self.assertEqual(draft['workspace']['phase'], 'observe')
        for field in ('criteria', 'basis', 'prepared_input', 'sources', 'source_context'):
            self.assertNotIn(field, draft['workspace'])
        self.assertTrue(draft['workspace']['candidate'])

    def test_changed_authority_refresh_keeps_the_previous_answer_and_requires_current_approval(self):
        path = self.plan()
        old = self.answer(plans.advance(self.root, path))
        original = (self.root / old).read_bytes()
        task = operations.read_run(self.root, self.run).prepared['task']['task_id']
        held = store.read_authority(self.root, task)
        current = copy.deepcopy(held.document)
        current['grants'][0]['revoked_at'] = c.now()
        f.write(self.root / 'revoked.json', current)
        store.import_authority(self.root, 'revoked.json', expected=held.event['sha256'])
        before = store.event_rows(self.root, self.run)
        blocked = plans.advance(self.root, path)
        self.assertEqual(blocked['state'], 'blocked', blocked)
        self.assertEqual(before, store.event_rows(self.root, self.run))
        fresh = plans.create(self.root, path)
        new = fresh['items'][0]['current']['answer_file']
        self.assertNotEqual(old, new)
        self.assertEqual((self.root / old).read_bytes(), original)
        self.assertEqual(fresh['items'][0]['current']['previous_answer'], old)
        self.assertFalse(c.load(self.root / new)['reason'])
        self.answer(fresh)
        complete = plans.advance(self.root, path)
        self.assertEqual(complete['state'], 'complete', complete)
        self.assertEqual(store.read_authority(self.root, task).document['grants'][0]['revoked_at'],
                         current['grants'][0]['revoked_at'])

    def test_invalid_source_result_is_rejected_before_binding_a_work_plan(self):
        f.write(self.root / 'invalid-request.json', {'source': {'run': self.run}, 'result': {'scope': 'save'}})
        before = copy.deepcopy(work_ledger.read_current(self.root))
        with self.assertRaisesRegex(ValueError, 'Image execution'):
            plans.create(self.root, 'invalid-request.json')
        self.assertEqual(before, work_ledger.read_current(self.root))

    def test_a_saved_complete_flag_does_not_supply_missing_formal_results(self):
        path = self.plan()
        state = c.load(self.root / path)
        state['items']['item-1']['status'] = 'complete'
        f.write(self.root / path, state)
        before = store.event_rows(self.root, self.run)
        with self.assertRaises(ValueError):
            plans.advance(self.root, path)
        self.assertEqual(before, store.event_rows(self.root, self.run))
        self.assertIsNotNone(work_ledger.read_current(self.root))

    def test_completed_plan_retry_preserves_a_later_withdrawal(self):
        path = self.plan()
        self.answer(plans.advance(self.root, path))
        self.assertEqual(plans.advance(self.root, path)['state'], 'complete')
        draft = curation.draft(self.root, {'kind': 'production', 'run': self.run, 'candidate': self.candidate},
                               {'scope': 'withdraw'})
        value = draft['choices']
        value['reason'] = 'The separate current synthetic instruction withdraws this canonical use.'
        value['approval'].update(actor=ACTOR, mode='direct',
            evidence={'path': 'adoption-basis.txt', 'locator': 'whole synthetic instruction'})
        for condition in value['stop_assessments']:
            condition.update(clear=True, evidence='This explicit synthetic withdrawal is current.')
        curation.apply(self.root, self.root / 'work/withdrawal', value, binding=draft['binding'])
        before = store.event_rows(self.root, self.run)
        result = plans.advance(self.root, path)
        self.assertEqual(result['state'], 'complete', result)
        self.assertEqual(result['items'][0]['current_use'], 'withdrawn')
        self.assertEqual(before, store.event_rows(self.root, self.run))


class WorkPlanDurabilityTests(unittest.TestCase):
    """A visible replacement does not settle a failed durable publication."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='work-plan-durability-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.task_id = '00000000-0000-4000-8000-000000000001'
        self.plan = 'work/plans/00000000-0000-4000-8000-000000000002/plan.json'
        self.steps = {'1': 'prepared'}
        task = {'task_id': self.task_id, 'work_state': 'active', 'questions': [],
                'steps': [{'n': 1, 'text': 'Prepare the selected work.', 'done_at': None}]}
        work_ledger.write_current(self.root, work_ledger.refreshed(task))
        c.atomic(self.root / self.plan, c.encoded({'status': 'active', 'task_id': self.task_id}))
        self.ledger = self.root / 'work/ledger.jsonl'
        c.atomic(self.ledger, b'')
        self.saved = work_ledger.task_path(self.root, self.task_id)
        self.pointer = self.root / 'work/current.json'
        self.original_pointer = self.pointer.read_bytes()
        self.flush_directory = c.fsync_dir

    def fail_task_flush_after_replacement(self, path):
        if path == self.saved.parent:
            retained = c.load(self.saved)
            self.assertEqual(retained['production_plan'], self.plan)
            self.assertEqual(retained['plan_steps'], self.steps)
            raise OSError(errno.EIO, 'Synthetic task directory flush failure after replacement')
        self.flush_directory(path)

    def test_binding_retry_completes_the_failed_directory_flush_before_updating_current(self):
        with patch.object(c, 'fsync_dir', side_effect=self.fail_task_flush_after_replacement), \
                self.assertRaisesRegex(OSError, 'task directory flush failure'):
            work_ledger.bind_plan(self.root, self.task_id, self.plan, self.steps)
        retained = self.saved.read_bytes()
        self.assertEqual(self.pointer.read_bytes(), self.original_pointer)
        flushed = []

        def flush(path):
            self.flush_directory(path)
            flushed.append(path)

        with patch.object(c, 'fsync_dir', side_effect=flush):
            result = work_ledger.bind_plan(self.root, self.task_id, self.plan, self.steps)
        self.assertIn(self.saved.parent, flushed)
        self.assertIn(self.pointer.parent, flushed)
        self.assertLess(flushed.index(self.saved.parent), flushed.index(self.pointer.parent))
        self.assertEqual(self.saved.read_bytes(), retained)
        self.assertEqual(c.load(self.saved), result)
        self.assertEqual(self.pointer.read_bytes(), c.encoded(result))
        self.assertEqual(self.ledger.read_bytes(), b'')

    def test_binding_retry_keeps_failing_when_its_directory_flush_still_fails(self):
        with patch.object(c, 'fsync_dir', side_effect=self.fail_task_flush_after_replacement):
            with self.assertRaisesRegex(OSError, 'task directory flush failure'):
                work_ledger.bind_plan(self.root, self.task_id, self.plan, self.steps)
            self.assertEqual(self.pointer.read_bytes(), self.original_pointer)
            with self.assertRaisesRegex(OSError, 'task directory flush failure'):
                work_ledger.bind_plan(self.root, self.task_id, self.plan, self.steps)
        self.assertEqual(self.pointer.read_bytes(), self.original_pointer)
        self.assertEqual(self.ledger.read_bytes(), b'')


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
