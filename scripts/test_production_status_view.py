"""Public navigation retains rework paths without repeating full decision material."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import execution_contract as c
import production_case_fixtures as fixtures
import production_acceptance
import production_execution as execution
import production_fixtures
import production_inputs
import production_status_view
import production_workflow as workflow
import transport_synthetic
from test_production_execution import decisions


class StatusViewTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name)
        self.enterContext(production_fixtures.scratch_home(base / 'home'))
        from catalog_retrieval import runtime
        self.addCleanup(runtime.configure_pack_runtime, None)
        self.base = base
        self.case = fixtures.create(base / 'studio', base / 'runtime')
        self.root = self.case['root']

    def cli(self, *arguments):
        result = subprocess.run([sys.executable, str(Path(workflow.__file__)), *arguments],
            capture_output=True, text=True, encoding='utf-8', env=dict(os.environ), check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def captured(self):
        run = workflow.prepare(self.root, 'task.json')['run']
        result = execution.execute(self.root, run, decisions_file=decisions(self.root, run))
        return run, result['runs'][0]['candidates'][0]

    def review(self, run, candidate, *, assessed=True, conclusion='The observed fixture is retained.'):
        value = workflow.draft_review(self.root, run, candidate)
        value.update(reviewer='Synthetic technical reviewer',
            observations=[{'evidence': 'candidate', 'locator': {'kind': 'whole'},
                'observation': 'The retained protocol fixture is a readable PNG.',
                'interpretation': 'Technical fixture observation only.',
                'limitations': ['No artistic inference.']}],
            conclusion=conclusion)
        if assessed:
            for check in value['checks']:
                check.update(verdict='pass', observation_indices=[0], reason='Observed synthetic output.')
        fixtures.write(self.root / 'review.json', value)
        return workflow.review(self.root, run, 'review.json')

    def test_custom_review_survives_partial_edit_and_log_cleanup_with_explicit_alternatives(self):
        run, candidate = self.captured()
        custom = 'work/review-in-progress.json'
        self.cli('draft-review', '--root', str(self.root), '--run', run,
                 '--candidate', candidate, '--out', custom)
        self.cli('logs-cleanup', '--root', str(self.root), '--before', '9999-01-01', '--apply')
        (self.root / custom).write_text('{"candidate":', encoding='utf-8')
        report = self.cli('status', '--root', str(self.root), '--run', run)
        state = report['runs'][0]
        self.assertEqual(state['integrity'], 'intact')
        self.assertEqual(state['candidates'], [candidate])
        self.assertEqual(state['next_action']['command'], 'status')
        self.assertEqual(state['next_action']['draft'], custom)
        self.assertIn('incomplete or unreadable', state['next_action']['reason'])
        for context in state['next_action']['read_context']:
            self.assertEqual(context['argv'][-2:], ['--candidate', candidate])
        self.assertEqual((self.root / custom).read_text(encoding='utf-8'), '{"candidate":')
        second = 'work/another-review.json'
        self.cli('draft-review', '--root', str(self.root), '--run', run,
                 '--candidate', candidate, '--out', second)
        action = self.cli('status', '--root', str(self.root), '--run', run)['runs'][0]['next_action']
        self.assertEqual(action['command'], 'status')
        self.assertNotIn('draft', action)
        self.assertEqual({item['draft'] for item in action['alternatives']}, {custom, second})
        self.assertFalse(any(row['event'] == 'review' for row in workflow.read_run(self.root, run).rows))

    def test_recorded_review_changes_basis_without_erasing_old_draft(self):
        run, candidate = self.captured()
        custom = 'work/first-review.json'
        self.cli('draft-review', '--root', str(self.root), '--run', run,
                 '--candidate', candidate, '--out', custom)
        before = (self.root / custom).read_bytes()
        self.review(run, candidate, assessed=False)
        report = self.cli('status', '--root', str(self.root), '--run', run)
        action = report['runs'][0]['next_action']
        self.assertEqual(action['command'], 'draft-review')
        self.assertNotEqual(action['draft'], custom)
        self.assertEqual((self.root / custom).read_bytes(), before)
        self.assertIn(custom, [item['path'] for item in report['current_task']['authoring']['decision_drafts']])

    def test_unregistered_canonical_review_remains_available(self):
        run, candidate = self.captured()
        identity = c.content_id({'run': run, 'candidate': candidate, 'basis': None,
                                'grant': None, 'scope': None})[:24]
        path = f'production/decisions/{run}/review/{identity}.json'
        fixtures.write(self.root / path, workflow.draft_review(self.root, run, candidate))
        before = (self.root / path).read_bytes()
        action = self.cli('status', '--root', str(self.root), '--run', run)['runs'][0]['next_action']
        self.assertEqual((action['command'], action['draft']), ('review', path))
        self.assertEqual((self.root / path).read_bytes(), before)

    def test_reused_path_and_competing_publisher_never_offer_another_candidate_draft(self):
        task = c.load(self.root / 'task.json')
        task['generation']['count'] = 2
        task['recording'] = None
        fixtures.write(self.root / 'task.json', task)
        run = workflow.prepare(self.root, 'task.json')['run']
        first, second = execution.execute(self.root, run,
            decisions_file=decisions(self.root, run))['runs'][0]['candidates']
        reused = 'work/reused-review.json'
        self.cli('draft-review', '--root', str(self.root), '--run', run,
                 '--candidate', first, '--out', reused)
        (self.root / reused).unlink()
        self.cli('draft-review', '--root', str(self.root), '--run', run,
                 '--candidate', second, '--out', reused)
        raced = 'work/competing-review.json'
        write = workflow._write_new
        def competing_writer(root, out, value):
            if value['candidate'] == first:
                workflow._write_decision_draft(root, run, 'review', out,
                    workflow.draft_review(root, run, second), candidate=second)
            write(root, out, value)
        with patch.object(workflow, '_write_new', side_effect=competing_writer):
            with self.assertRaises(ValueError):
                workflow._write_decision_draft(self.root, run, 'review', raced,
                    workflow.draft_review(self.root, run, first), candidate=first)
        report = self.cli('status', '--root', str(self.root), '--run', run)
        action = report['runs'][0]['next_action']
        options = {item['read_context'][0]['argv'][-1]: item for item in action['alternatives']}
        self.assertEqual(options[first]['command'], 'draft-review')
        self.assertNotIn(options[first]['draft'], {reused, raced})
        self.assertEqual(options[second]['command'], 'status')
        self.assertEqual({item['draft'] for item in options[second]['alternatives']}, {reused, raced})
        for path in (reused, raced):
            self.assertEqual(c.load(self.root / path)['candidate'], second)
        self.assertFalse(any(row['event'] == 'review' for row in workflow.read_run(self.root, run).rows))

    def test_custom_acceptance_and_selection_remain_separate_explicit_choices(self):
        run, candidate = self.captured()
        self.review(run, candidate)
        acceptance, selection = 'work/acceptance.json', 'work/selection.json'
        self.cli('draft-acceptance', '--root', str(self.root), '--run', run,
                 '--candidate', candidate, '--out', acceptance)
        action = self.cli('status', '--root', str(self.root), '--run', run)['runs'][0]['next_action']
        self.assertEqual((action['command'], action['draft']), ('accept', acceptance))
        authority = execution.status(self.root, run)['runs'][0]['authority']
        document = copy.deepcopy(authority['document'])
        another = copy.deepcopy(document['grants'][0])
        another['id'] = 'another-selection-grant'
        document['grants'].append(another)
        fixtures.write(self.root / authority['source_path'], document)
        self.cli('authority-import', '--root', str(self.root), '--file', authority['source_path'],
                 '--expected-event', authority['event_sha256'])
        action = self.cli('status', '--root', str(self.root), '--run', run)['runs'][0]['next_action']
        self.assertEqual((action['command'], action['draft']), ('accept', acceptance))
        self.cli('draft-selection', '--root', str(self.root), '--run', run,
                 '--candidate', candidate, '--out', selection)
        action = self.cli('status', '--root', str(self.root), '--run', run)['runs'][0]['next_action']
        self.assertEqual(action['command'], 'status')
        self.assertNotIn('draft', action)
        self.assertEqual({(item['command'], item['draft']) for item in action['alternatives']},
                         {('accept', acceptance), ('select', selection)})
        self.review(run, candidate, conclusion='A new technical review of the retained fixture.')
        action = self.cli('status', '--root', str(self.root), '--run', run)['runs'][0]['next_action']
        self.assertEqual(action['command'], 'draft-acceptance')
        self.assertNotIn(action['draft'], {acceptance, selection})
        self.assertTrue((self.root / acceptance).is_file())
        self.assertTrue((self.root / selection).is_file())

    def test_custom_slot_acceptance_tracks_placement_without_overwriting_prior_draft(self):
        import studio_placement
        run, candidate = self.captured()
        self.review(run, candidate)
        previous, current = 'work/first-slot-acceptance.json', 'work/moved-slot-acceptance.json'
        self.cli('draft-acceptance', '--root', str(self.root), '--run', run,
                 '--candidate', candidate, '--scope', 'studio-slot', '--out', previous)
        original = (self.root / previous).read_bytes()
        action = self.cli('status', '--root', str(self.root), '--run', run)['runs'][0]['next_action']
        self.assertEqual((action['command'], action['draft']), ('accept', previous))

        placement = studio_placement.draft(self.root, 'robot', 'it-0001', 'scene.delivery')
        placement.update(by='Synthetic fixture curator', at='2026-11-11T00:00:00Z',
                         reason='Retain this fixture image under the authored scene destination.')
        studio_placement.reassign(self.root, placement)
        report = self.cli('status', '--root', str(self.root), '--run', run)
        action = report['runs'][0]['next_action']
        self.assertEqual(action['command'], 'draft-acceptance')
        self.assertNotEqual(action['draft'], previous)
        self.assertTrue(all(item.get('draft') != previous for item in action.get('alternatives', [])))
        self.assertIn(previous, [item['path'] for item in report['current_task']['authoring']['decision_drafts']])

        self.cli('draft-acceptance', '--root', str(self.root), '--run', run,
                 '--candidate', candidate, '--scope', 'studio-slot', '--out', current)
        action = self.cli('status', '--root', str(self.root), '--run', run)['runs'][0]['next_action']
        self.assertEqual((action['command'], action['draft']), ('accept', current))
        self.assertNotEqual(c.load(self.root / previous)['expected_placement'],
                            c.load(self.root / current)['expected_placement'])
        self.assertEqual((self.root / previous).read_bytes(), original)

    def test_custom_outcome_continues_original_claim_without_another_send(self):
        run = workflow.prepare(self.root, 'task.json')['run']
        with patch.object(transport_synthetic, 'send', side_effect=TimeoutError('Synthetic unanswered send')) as send:
            execution.execute(self.root, run, decisions_file=decisions(self.root, run))
            execution.resume(self.root, run)
            self.assertEqual(send.call_count, 1)
        custom = 'work/provider-outcome.json'
        draft = self.cli('draft-outcome', '--root', str(self.root), '--run', run, '--out', custom)
        before = workflow.read_run(self.root, run).rows
        action = self.cli('status', '--root', str(self.root), '--run', run)['runs'][0]['next_action']
        self.assertEqual(action['command'], 'resume')
        self.assertEqual(action['argv'][-2:], ['--outcome-file', custom])
        self.assertEqual(c.load(self.root / custom)['claim'], draft['claim'])
        self.assertEqual(workflow.read_run(self.root, run).rows, before)

    def test_current_sources_are_compared_only_while_a_send_can_follow(self):
        waiting = workflow.prepare(self.root, 'task.json')['run']
        sent, _ = self.captured()
        brief = self.root / 'brief.md'
        brief.write_bytes(brief.read_bytes() + b'\nA later synthetic edit.\n')
        report = execution.status(self.root)
        workflow.schema_check(report, 'status')
        runs = {item['run']: item for item in report['runs']}
        self.assertEqual(runs[waiting]['readiness'], 'blocked')
        self.assertEqual([item['code'] for item in runs[waiting]['freshness_diagnostics']], ['SOURCE_CHANGED'])
        self.assertEqual(runs[waiting]['next_action']['command'], 'prepare')
        # The sent run reports the edit and still continues from its retained candidate.
        self.assertEqual(runs[sent]['readiness'], 'blocked')
        self.assertEqual(runs[sent]['next_action']['command'], 'draft-review')
        self.assertIsNone(runs[sent]['authorization_requirements'])
        self.assertIsNotNone(runs[waiting]['authorization_requirements'])
        # Open runs left by closed work are compared when they are selected by their ID.
        import work_ledger
        task = work_ledger.read_current(self.root)
        task['work_state'] = 'completed'
        work_ledger.save_task(self.root, task)
        left = next(item for item in execution.status(self.root)['runs'] if item['run'] == waiting)
        self.assertEqual((left['readiness'], left['freshness_diagnostics']), ('unchecked', []))
        self.assertEqual(left['next_action']['command'], 'status')
        self.assertEqual(left['next_action']['argv'][-2:], ['--run', waiting])
        chosen = execution.status(self.root, waiting)['runs'][0]
        self.assertEqual(chosen['readiness'], 'blocked')
        self.assertEqual([item['code'] for item in chosen['freshness_diagnostics']], ['SOURCE_CHANGED'])
        # A sent one keeps its own continuation without the comparison.
        kept = next(item for item in execution.status(self.root)['runs'] if item['run'] == sent)
        self.assertEqual((kept['readiness'], kept['freshness_diagnostics']), ('unchecked', []))
        self.assertEqual(kept['next_action']['command'], 'draft-review')

    def test_blocked_run_prepared_from_choices_prepares_those_choices_again(self):
        draft = production_inputs.draft_inputs(self.root, 'task.json', 'authored')
        run = workflow.prepare(self.root, choices=draft['choices_file'])['run']
        prepared = workflow.read_run(self.root, run).prepared
        source = self.root / prepared['authoring']['source_map']['authoring.delivery']['file']
        source.write_bytes(source.read_bytes() + b'\nA later synthetic addition.\n')
        state = execution.status(self.root, run)['runs'][0]
        self.assertEqual(state['readiness'], 'blocked')
        action = state['next_action']
        self.assertEqual((action['command'], action['argv'][-2:]), ('prepare', ['--choices', draft['choices_file']]))
        # The run's own task file is its published copy and does not hold the edit.
        self.assertNotEqual(prepared['task_path'], 'task.json')
        again = workflow.prepare(self.root, choices=draft['choices_file'])['run']
        self.assertIn('A later synthetic addition.',
                      workflow.read_run(self.root, again).artifacts['package.json']['generation_payload']['prompt'])
        (self.root / draft['choices_file']).unlink()
        restored = execution.status(self.root, run)['runs'][0]['next_action']
        self.assertEqual((restored['command'], restored['argv'][-4:-2]), ('draft-inputs', ['--from-run', run]))

    def test_removed_published_draft_is_no_longer_a_branch_of_the_work(self):
        import shutil
        import production_authoring_state
        production_inputs.draft_inputs(self.root, 'task.json', 'work/first')
        production_inputs.draft_inputs(self.root, 'task.json', 'work/second')
        report = production_authoring_state.inspect(self.root)
        self.assertTrue(report['selection_required'])
        self.assertEqual({row['directory'] for row in report['inputs']}, {'work/first', 'work/second'})
        shutil.rmtree(self.root / 'work/first')
        report = production_authoring_state.inspect(self.root)
        self.assertFalse(report['selection_required'])
        self.assertEqual([(row['directory'], row['state']) for row in report['inputs']], [('work/second', 'choices')])
        authoring = execution.status(self.root)['current_task']['authoring']
        self.assertEqual([row['directory'] for row in authoring['inputs']], ['work/second'])

    def test_preparation_reading_that_no_longer_verifies_is_a_notice(self):
        run = workflow.prepare(self.root, 'task.json')['run']
        (self.root / 'work/reads.jsonl').write_bytes(b'')
        state = execution.status(self.root, run)['runs'][0]
        workflow.schema_check(execution.status(self.root, run), 'status')
        self.assertEqual(state['freshness_diagnostics'], [])
        [notice] = state['freshness_notices']
        self.assertEqual((notice['severity'], notice['phase']), ('warning', 'freshness'))
        self.assertNotEqual(state['readiness'], 'blocked')
        result = execution.execute(self.root, run, decisions_file=decisions(self.root, run))
        self.assertTrue(result['execution_completed'])

    def test_run_logs_come_from_each_operation_record_alone(self):
        import operation_context
        settings = self.case['settings']
        runtime = ['--state-file', str(settings.state_file.resolve()), '--cache-dir', str(settings.cache_dir.resolve()),
                   '--managed-root', str(settings.managed_root.resolve()), '--pack-root', str(self.case['pack'].resolve())]
        prepared = self.cli('prepare', '--root', str(self.root), '--task', 'task.json', *runtime)
        self.cli('status', '--root', str(self.root), '--run', prepared['run'])
        expected = {}
        for row in operation_context.list_operations(self.root):
            context = (row.get('metadata') or {}).get('context') or {}
            if isinstance(context.get('run'), str):
                expected.setdefault(context['run'], []).append(row['operation_id'])
        self.assertIn(prepared['run'], expected)
        # The run of each operation is in its operation.json; no event stream is read for it.
        with patch.object(operation_context, '_operation_last_event', side_effect=AssertionError('event stream read')):
            self.assertEqual(operation_context.operations_by_run(self.root), expected)
            report = execution.status(self.root, prepared['run'])
        self.assertEqual(report['runs'][0]['logs'], expected[prepared['run']])

    def test_an_unimported_authority_edit_is_reported_before_execution(self):
        from production_diagnostics import ProductionError
        run = workflow.prepare(self.root, 'task.json')['run']
        state = execution.status(self.root, run)['runs'][0]
        self.assertIsNone(state['authority']['source_edited'])
        self.assertNotIn('AUTHORITY_SOURCE_NOT_IMPORTED', [item['code'] for item in state['readiness_diagnostics']])
        decision_file = decisions(self.root, run)
        source = state['authority']['source_path']
        path = self.root / source
        imported = path.read_bytes()
        # The author adds a grant in the file and forgets to import it.
        document = json.loads(imported)
        document['grants'].append({**copy.deepcopy(document['grants'][0]), 'id': 'added-in-file-only'})
        fixtures.write(path, document)
        state = execution.status(self.root, run)['runs'][0]
        edited = state['authority']['source_edited']
        self.assertEqual((edited['path'], edited['imported_sha256']), (source, c.digest(imported)))
        self.assertEqual(edited['current_sha256'], c.digest(path.read_bytes()))
        self.assertIn('changed after its import', state['authority']['update_action']['reason'])
        [warning] = [item for item in state['readiness_diagnostics'] if item['code'] == 'AUTHORITY_SOURCE_NOT_IMPORTED']
        self.assertEqual((warning['severity'], warning['file']), ('warning', source))
        self.assertIn('authority-import', warning['required_action'])
        drafted = execution.draft_execution(self.root, run, 'fixture-grant')
        self.assertEqual(drafted['authority']['source_edited'], edited)
        chosen = c.load(self.root / decision_file)
        for item in chosen['decisions']:
            item['grant'] = 'added-in-file-only'
        fixtures.write(self.root / decision_file, chosen)
        with self.assertRaises(ProductionError) as caught:
            execution.execute(self.root, run, decisions_file=decision_file)
        self.assertTrue(caught.exception.diagnostic.required_action.startswith(source + ' changed after its import'))
        self.assertEqual(caught.exception.diagnostic.details['authority_source_edited'], edited)
        # Restoring the imported bytes clears the report.
        path.write_bytes(imported)
        self.assertIsNone(execution.status(self.root, run)['runs'][0]['authority']['source_edited'])

    def test_unsent_run_without_registered_authority_names_its_import(self):
        case = fixtures.create(self.base / 'unregistered', self.base / 'unregistered-runtime', with_authority=False)
        run = workflow.prepare(case['root'], 'task.json')['run']
        state = execution.status(case['root'], run)['runs'][0]
        self.assertEqual(state['readiness'], 'authorization_required')
        self.assertIsNone(state['authority']['event_sha256'])
        self.assertEqual(state['authority']['update_action']['command'], 'authority-import')
        self.assertTrue(state['readiness_diagnostics'][0]['required_action'].startswith(
            'The work task has no registered authority: import it first'))

    def test_summary_keeps_state_and_executable_full_evidence_without_mutation(self):
        draft = production_inputs.draft_inputs(self.root, 'task.json', 'authored')
        run = workflow.prepare(self.root, choices=draft['choices_file'])['run']
        full = execution.status(self.root, run)
        before = copy.deepcopy(full)
        result = production_status_view.summary(self.root, full, run=run)
        workflow.schema_check(result, 'status-summary')
        self.assertEqual(full, before)
        for field in ('diagnostics', 'execution_records', 'staging_details', 'unregistered_publications'):
            self.assertEqual(result[field], full[field])
        actual = result['runs'][0]
        original = full['runs'][0]
        for field in ('readiness', 'submission', 'capture', 'task_disposition', 'next_action',
                      'readiness_diagnostics', 'authorization_requirements'):
            self.assertEqual(actual[field], original[field])
        self.assertEqual(actual['authority']['event_sha256'], original['authority']['event_sha256'])
        self.assertNotIn('document', actual['authority'])
        self.assertIn('document', original['authority'])
        self.assertEqual(result['current_task']['authoring']['inputs'], full['current_task']['authoring']['inputs'])
        public = self.cli('status', '--root', str(self.root), '--run', run)
        workflow.schema_check(public, 'status-summary')
        action = public['details_action']['argv']
        retrieved = subprocess.run(action, capture_output=True, text=True, encoding='utf-8',
                                   env=dict(os.environ), check=False)
        self.assertEqual(retrieved.returncode, 0, retrieved.stdout + retrieved.stderr)
        complete = json.loads(retrieved.stdout)
        workflow.schema_check(complete, 'status')
        self.assertEqual(complete['runs'][0]['authority']['document'], original['authority']['document'])

    def test_multiple_candidates_each_offer_their_own_continuation(self):
        task = c.load(self.root / 'task.json')
        task['generation']['count'] = 2
        task['recording'] = None
        fixtures.write(self.root / 'task.json', task)
        run = workflow.prepare(self.root, 'task.json')['run']
        result = execution.execute(self.root, run, decisions_file=decisions(self.root, run))
        state = result['runs'][0]
        self.assertEqual(len(state['candidates']), 2)
        action = state['next_action']
        self.assertTrue(action['requires_author_input'])
        self.assertEqual(action['command'], 'status')
        alternatives = action['alternatives']
        self.assertEqual(len(alternatives), 2)
        candidates = set()
        for option in alternatives:
            self.assertEqual(option['command'], 'draft-review')
            candidates.add(option['argv'][option['argv'].index('--candidate') + 1])
            self.assertEqual([context['argv'][context['argv'].index('--phase') + 1]
                              for context in option['read_context']], ['observe', 'review'])
        self.assertEqual(candidates, set(state['candidates']))
        self.assertFalse(any(row['event'] == 'selection' for row in workflow.read_run(self.root, run).rows))

    def test_editing_review_draft_does_not_hide_saved_candidate_or_redirect_context(self):
        run = workflow.prepare(self.root, 'task.json')['run']
        result = execution.execute(self.root, run, decisions_file=decisions(self.root, run))
        original = result['runs'][0]
        action = original['next_action']
        path = self.root / action['draft']
        path.parent.mkdir(parents=True, exist_ok=True)
        for authored in ('{"candidate":', json.dumps({'candidate': '0' * 64})):
            path.write_text(authored, encoding='utf-8')
            state = execution.status(self.root, run)['runs'][0]
            self.assertEqual(state['integrity'], 'intact')
            self.assertEqual(state['candidates'], original['candidates'])
            self.assertEqual(state['next_action']['draft'], action['draft'])
            self.assertEqual(state['next_action']['read_context'], action['read_context'])

    def test_delivery_scope_and_work_diagnostics_are_independent_of_slot_navigation(self):
        run = workflow.prepare(self.root, 'task.json')['run']
        result = execution.execute(self.root, run, decisions_file=decisions(self.root, run))
        candidate = result['runs'][0]['candidates'][0]
        review = workflow.draft_review(self.root, run, candidate)
        review.update(reviewer='Synthetic technical reviewer',
            observations=[{'evidence': 'candidate', 'locator': {'kind': 'whole'},
                'observation': 'The synthetic protocol fixture saved its 32 by 32 PNG.',
                'interpretation': 'Technical fixture observation; no artistic claim.',
                'limitations': ['Synthetic service only.']}],
            checks=[{'criterion': 'output', 'verdict': 'pass', 'observation_indices': [0],
                     'reason': 'The synthetic fixture has its declared dimensions.'}],
            conclusion='Technical output is available.', unresolved=[])
        fixtures.write(self.root / 'review.json', review)
        workflow.review(self.root, run, 'review.json')
        with patch.object(production_acceptance, 'slot_state', side_effect=ValueError('Unreadable slot view.')):
            state = execution.status(self.root, run)['runs'][0]
        self.assertEqual(state['integrity'], 'intact')
        action = state['next_action']
        self.assertEqual(action['command'], 'draft-acceptance')
        self.assertEqual(action['argv'][action['argv'].index('--scope') + 1], 'delivery-only')
        self.assertIn('Unreadable slot view', action['alternatives'][0]['reason'])
        choice = production_acceptance.draft(self.root, run, candidate)
        choice['reason'] = 'Deliver this explicitly reviewed technical fixture.'
        fixtures.write(self.root / 'acceptance.json', choice)
        production_acceptance.accept(self.root, run, decision_file='acceptance.json')
        import work_ledger
        with patch.object(work_ledger, 'finish_state', side_effect=OSError('Unreadable work completion.')):
            report = execution.status(self.root, run)
        self.assertFalse(report['ok'])
        self.assertEqual(report['runs'][0]['integrity'], 'intact')
        self.assertEqual(report['runs'][0]['task_disposition'], 'completed')
        self.assertEqual(report['current_task']['next_actions'][0]['command'], 'show')
        self.assertEqual(report['current_task']['diagnostics'][0]['phase'], 'work-finish')


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
