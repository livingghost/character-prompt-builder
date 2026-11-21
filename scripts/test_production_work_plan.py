"""Commissioned work reaches its actual result through one recoverable plan."""
from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

import execution_contract as c
import production_case_fixtures as f
import production_operations as operations
import production_store as store
import production_work_plan as plans
import production_work_review as reviews
import production_curation as curation
import test_production_adoption as adoption
import test_production_authored as authored
import work_ledger
from production_fixtures import ACTOR


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
        path = self.plan()
        first = plans.advance(self.root, path)
        self.assertEqual(first['items'][0]['phase'], 'curation', first)
        self.answer(first)
        report = plans.advance(self.root, path)
        self.assertEqual(report['state'], 'complete', report)
        self.assertTrue(report['verification']['ok'])
        self.assertIsNone(work_ledger.read_current(self.root))
        events = store.event_rows(self.root, self.run)
        for event in ('selection', 'slot-acceptance', 'completion', 'adoption-result'):
            self.assertEqual(sum(row['event'] == event for row in events), 1)
        again = plans.advance(self.root, path)
        self.assertEqual(again['state'], 'complete')
        self.assertEqual(events, store.event_rows(self.root, self.run))

    def test_existing_unbound_work_is_exposed_and_not_marked_from_guesswork(self):
        path = self.plan(steps=False)
        self.answer(plans.advance(self.root, path))
        report = plans.advance(self.root, path)
        self.assertEqual(report['state'], 'work-required', report)
        self.assertTrue(report['remaining_work']['steps'])
        self.assertTrue(all(not row['done_at'] for row in work_ledger.read_current(self.root)['steps']))

    def test_prepare_only_finishes_without_selection_or_new_submission(self):
        path = self.plan('prepared-input')
        before = store.event_rows(self.root, self.run)
        report = plans.advance(self.root, path)
        self.assertEqual(report['state'], 'complete', report)
        self.assertEqual(before, store.event_rows(self.root, self.run))

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
        before = store.event_rows(self.root, self.run)
        one = plans.advance(self.root, path)
        two = plans.advance(self.root, path)
        self.assertEqual(one['items'][0]['current']['answer_file'], two['items'][0]['current']['answer_file'])
        self.assertNotEqual(two['state'], 'blocked')
        self.assertEqual(before, store.event_rows(self.root, self.run))

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


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
