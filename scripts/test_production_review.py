"""Review/Studio ownership tests. All decisions describe synthetic fixture PNGs."""
from __future__ import annotations
from contextlib import closing
import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import execution_contract as c
import production_case_fixtures as fixtures
import production_execution as execution
import production_fixtures as fixture
import production_workflow as workflow
import production_workspace as workspace
import production_store as store
import studio
import studio_gallery
import validate_studio
from production_diagnostics import ProductionError
from test_production_execution import decisions


class ReviewCase(unittest.TestCase):
    """One prepared and executed synthetic run whose candidates the Studio shows."""
    count = 1

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.case = fixtures.create(base / 'studio', base / 'runtime')
        self.root = self.case['root']
        task = c.load(self.root / 'task.json')
        task['criteria'].append({'id': 'palette', 'strength': 'hard', 'text': 'The fixture palette is inspectable.', 'evidence': 'image'})
        task['generation']['count'] = self.count
        self.configure_task(task)
        fixtures.write(self.root / 'task.json', task)
        self.run = workflow.prepare(self.root, 'task.json')['run']
        result = execution.execute(self.root, self.run, decisions_file=decisions(self.root, self.run))
        self.assertTrue(result['execution_completed'], result.get('warnings'))
        self.candidates = result['runs'][0]['candidates']
        self.candidate = self.candidates[0]
        self.home = studio.character_home(self.root, 'robot')
        self.iteration = self.row(self.candidate)['iteration_id']

    def configure_task(self, task):
        """Let a synthetic case select its sources before preparation."""

    def row(self, candidate):
        return next(row for row in studio.read_iterations(self.home) if row['production']['candidate'] == candidate)

    def review_data(self, checks, candidate=None, unresolved=None):
        value = workflow.draft_review(self.root, self.run, candidate or self.candidate)
        value.update(reviewer='Synthetic fixture reviewer - not user approval',
            observations=[{'evidence':'candidate', 'locator':{'kind':'whole'},
                'observation':'The local fixture is a decoded 32 by 32 PNG.',
                'interpretation':'Synthetic protocol assertion only; no generative model quality is assessed.',
                'limitations':['Only the local fixture is examined.']}],
            checks=[{'criterion':key, 'verdict':verdict, 'observation_indices':[] if verdict == 'not-assessed' else [0],
                     'reason':'Explicit synthetic fixture decision.'} for key,verdict in checks],
            conclusion='Synthetic fixture review.',
            unresolved=unresolved if unresolved is not None else (
                ['Palette criterion deliberately fails in this synthetic negative case.'] if any(v=='fail' for _,v in checks) else []))
        fixtures.write(self.root / 'review.json', value)
        return value

    def record_review(self, checks, candidate=None, **changes):
        self.review_data(checks, candidate, **changes)
        return workflow.review(self.root, self.run, 'review.json')

    def select(self, candidate=None):
        choice = workflow.draft_selection(self.root, self.run, candidate or self.candidate)
        choice.update(reason='Synthetic fixture delivery selection.')
        fixture.selection(self.root, self.run, choice)
        fixtures.write(self.root / 'selection.json', choice)
        return workflow.select(self.root, self.run, 'selection.json')

    def not_selected(self, candidate=None):
        value = workflow.draft_disposition(self.root, self.run, candidate or self.candidate)
        value.update(actor='Synthetic fixture selector', reason='Another synthetic candidate is preferred.')
        fixtures.write(self.root / 'disposition.json', value)
        return workflow.disposition(self.root, self.run, 'disposition.json')

    def state(self, candidate=None):
        return workflow.candidate_state(self.root, self.run, candidate or self.candidate)

    def assertCode(self, code, action):
        with self.assertRaises(ProductionError) as caught:
            action()
        self.assertEqual(caught.exception.diagnostic.code, code)


class ReviewTests(ReviewCase):
    def test_current_status_rechecks_changed_run_without_a_dirty_receipt(self):
        import production_compiler
        path = workflow.run_dir(self.root, self.run)/'consumer.json'
        path.write_bytes(path.read_bytes() + b' ')
        with patch.object(production_compiler, 'acquire_publication', wraps=production_compiler.acquire_publication) as acquire:
            text = studio.status(self.root)
        self.assertEqual(acquire.call_count, 1)
        self.assertIn('artwork problem robot/' + self.iteration, text)
        self.assertEqual(c.load(self.root/'gallery.json')['entries'][0]['availability'], 'unavailable')

    def test_status_retains_closed_history_and_sync_rechecks_its_actual_source(self):
        import studio_activity
        import work_ledger
        self.record_review([('output', 'pass'), ('palette', 'pass')])
        self.select()
        studio.accept(self.root, 'robot', self.iteration)
        workflow.complete(self.root, self.run)
        for step in work_ledger.read_current(self.root)['steps']:
            work_ledger.step_done(self.root, step['n'])
        work_ledger.finish(self.root, self.run)
        original = self.row(self.candidate)
        current = studio.iterate(self.root, 'robot', original['slot'], self.root/original['result']['path'],
            package=None, request=None, response=None, note='Independent current synthetic import.')
        studio.accept(self.root, 'robot', current['iteration_id'])
        path = workflow.run_dir(self.root, self.run)/'consumer.json'
        path.write_bytes(path.read_bytes() + b' ')
        with patch.object(workflow, 'read_run', wraps=workflow.read_run) as read_run:
            text = studio.status(self.root)
        read_run.assert_not_called()
        self.assertIn('retained historical displays', text)
        history = next(row for row in c.load(self.root/'gallery.json')['entries'] if row['iteration_id'] == self.iteration)
        self.assertEqual(history['availability'], 'present')
        with patch.object(workflow, 'read_run', wraps=workflow.read_run) as read_run:
            self.assertTrue(studio_activity.refresh(self.root)['ok'])
        self.assertEqual([call.args[1] for call in read_run.call_args_list], [self.run])
        history = next(row for row in c.load(self.root/'gallery.json')['entries'] if row['iteration_id'] == self.iteration)
        self.assertEqual(history['availability'], 'unavailable')

    def test_compact_answers_use_the_complete_prepared_review_basis(self):
        draft = workflow.draft_review(self.root, self.run, self.candidate)
        basis = workflow.review_basis(self.root, self.run, self.candidate)
        task = c.load(self.root / 'task.json')
        checks = {row['criterion']: row for row in draft['checks']}
        criteria = {row['id']: row for row in basis['criteria']}
        decision = task['direction']['decisions'][0]
        selected = next(option for option in decision['options'] if option['id'] == decision['selected'])
        self.assertEqual(basis['purpose'], task['direction']['purpose'])
        self.assertEqual(basis['intended_effect'], task['direction']['intended_effect'])
        for criterion in task['criteria']:
            self.assertEqual(criteria[criterion['id']]['text'], criterion['text'])
            self.assertEqual(criteria[criterion['id']]['evidence'], criterion['evidence'])
            self.assertEqual(checks[criterion['id']]['reason'], '')
            self.assertEqual(checks[criterion['id']]['verdict'], 'not-assessed')
            self.assertEqual(checks[criterion['id']]['observation_indices'], [])
        self.assertEqual(criteria['output']['realizations'][0]['expression'], selected['expression'])
        self.assertEqual(criteria['output']['realizations'][0]['instructions'], selected['realization']['instructions'])
        self.assertEqual(criteria['palette']['realizations'], [])
        for option in decision['options']:
            if option['id'] != decision['selected']:
                self.assertNotIn(option['realization']['instructions'], json.dumps(criteria['output']))
        self.assertEqual((draft['observations'], draft['evidence'], draft['conclusion']), ([], [], ''))
        task['direction']['purpose'] = 'A later live task serves another artifact.'
        task['direction']['intended_effect'] = 'A later intended effect is outside this prepared run.'
        task['criteria'][0]['text'] = 'A later live task has a different criterion.'
        task['direction']['decisions'][0]['options'][0]['expression'] = 'Changed after preparation.'
        fixtures.write(self.root / 'task.json', task)
        self.assertEqual(workflow.draft_review(self.root, self.run, self.candidate), draft)
        self.assertEqual(workflow.review_basis(self.root, self.run, self.candidate), basis)

    def test_input_workspace_supplies_the_whole_request_before_assessment_context(self):
        before = store.event_rows(self.root, self.run)
        view = workspace.workspace(self.root, self.run, phase='input')
        directory, prepared, _, _ = workflow.load_run(self.root, self.run)
        rendered = c.load(directory / 'request-contract.json')
        self.assertEqual(view['prepared_input']['request'], rendered['request'])
        self.assertEqual(view['prepared_input']['target'], rendered['sealed']['target'])
        self.assertEqual(view['prepared_input']['request_sha256'], rendered['request_sha256'])
        self.assertEqual(view['input_sha256'], prepared['input_sha256'])
        self.assertEqual(set(view), {'phase', 'run', 'input_sha256', 'reading', 'prepared_input', 'instruction'})
        self.assertTrue(view['reading']['documents'])
        self.assertTrue(all(Path(item['path']).is_file() for item in view['reading']['documents']))
        self.assertEqual(store.event_rows(self.root, self.run), before)

    def test_input_workspace_preserves_prepared_carriers_and_every_request_mapping(self):
        import shutil
        import production_variation as variation
        from prepare_generation_references import prepare_references
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="32" height="16" viewBox="0 0 32 16">'
               '<rect width="32" height="16" fill="#5078a0"/></svg>').encode('utf-8')
        for mode in ('multi-image', 'single-board'):
            with self.subTest(mode=mode):
                folder = self.root / 'workspace-media' / mode
                source = folder / 'source.svg'
                c.atomic(source, svg)
                selections = [{'role': role,
                    'source': {'kind': 'supplied-file', 'reference_id': mode + '-' + role,
                               'resolved_path': str(source)},
                    'subject_uses': [{'subject_id': 'robot', 'use': use, 'priority': 0}]}
                    for role, use in (('palette', 'local-color'), ('finish', 'surface-finish'))]
                references = prepare_references(selections, model=fixtures.MODEL_ID,
                    output_dir=folder / 'prepared', max_side=64, transport_mode=mode)
                fixtures.write(folder / 'references.json', references)
                fixtures.write(self.root / 'workspace-changes.json', {
                    'changes': {'references': {'path': (folder / 'references.json').relative_to(self.root).as_posix()},
                                'execution-mode': 'reference-guided'},
                    'reason': 'Inspect the exact prepared synthetic media in the input workspace.'})
                run = variation.derive(self.root, self.run, changes_file='workspace-changes.json', prepare=True)['run']
                directory, _, _, _ = workflow.load_run(self.root, run)
                rendered = c.load(directory / 'request-contract.json')
                self.assertEqual(len(rendered['sealed']['bindings']), 2)
                self.assertEqual({item['attachment_number'] for item in rendered['sealed']['bindings']}, {1})
                shutil.rmtree(folder)
                before = store.event_rows(self.root, run)
                view = workspace.workspace(self.root, run, phase='input')['prepared_input']
                self.assertEqual(view['request'], rendered['request'])
                self.assertEqual(len(view['media']), len(rendered['media']))
                for index, (shown, pinned) in enumerate(zip(view['media'], rendered['media'], strict=True)):
                    self.assertEqual(shown['request_fields'], [row['field'] for row in rendered['layout']['media']
                                                             if row['index'] == index])
                    self.assertEqual(shown['sha256'], pinned['sha256'])
                    self.assertNotEqual(shown['sha256'], c.digest(svg))
                    path = Path(shown['path'])
                    path.relative_to(directory)
                    self.assertEqual(c.digest(path.read_bytes()), pinned['sha256'])
                    self.assertEqual(shown['media']['format'], 'PNG')
                    self.assertEqual((shown['media']['width'], shown['media']['height']),
                                     (pinned['dimensions']['width'], pinned['dimensions']['height']))
                self.assertEqual(store.event_rows(self.root, run), before)

    def test_observation_workspace_has_only_saved_candidate_and_technical_context(self):
        before = store.event_rows(self.root, self.run)
        view = workspace.workspace(self.root, self.run, phase='observe', candidate=self.candidate)
        self.assertEqual(set(view), {'phase', 'run', 'candidate', 'instruction'})
        actual = view['candidate']
        self.assertEqual(set(actual), {'id', 'files', 'media'})
        self.assertEqual(actual['id'], self.candidate)
        self.assertEqual((actual['media']['width'], actual['media']['height']), (32, 32))
        for item in actual['files']:
            raw = Path(item['path']).read_bytes()
            self.assertEqual(c.digest(raw), item['sha256'])
            self.assertEqual(len(raw), item['size'])
        self.assertEqual(store.event_rows(self.root, self.run), before)

    def test_assessment_workspace_uses_frozen_sources_and_distinct_answers(self):
        view = workspace.workspace(self.root, self.run, phase='review', candidate=self.candidate)
        self.assertEqual(view['basis'], workflow.review_basis(self.root, self.run, self.candidate))
        self.assertTrue(view['sources'])
        original = view['sources'][0]
        Path(self.root / original['path']).write_text('Later source content.', encoding='utf-8')
        again = workspace.workspace(self.root, self.run, phase='review', candidate=self.candidate)
        self.assertEqual(again['sources'], view['sources'])
        self.assertEqual(c.digest(Path(original['saved_path']).read_bytes()), original['sha256'])
        draft = workflow.draft_review(self.root, self.run, self.candidate)
        self.assertTrue(all(item['reason'] == '' and item['verdict'] == 'not-assessed' for item in draft['checks']))

    def test_reused_run_source_is_available_in_decision_and_review_workspaces(self):
        import production_variation as variation
        prepared = workflow.load_run(self.root, self.run)[1]
        sources = [*prepared['task']['sources'],
            {'id': 'native-settings', 'path': prepared['task']['generation']['parameters'],
             'role': 'model-controls', 'disposition': 'applied', 'locator': 'whole',
             'reason': 'The synthetic source records the selected native dimensions and settings.'}]
        fixtures.write(self.root / 'workspace-source-changes.json', {
            'changes': {'source-materials': sources, 'parameter:steps': 22},
            'reason': 'Prepare revised native settings as a retained source of this synthetic image.'})
        changed = variation.derive(self.root, self.run,
            changes_file='workspace-source-changes.json', prepare=True)['run']
        run = variation.derive(self.root, changed, prepare=True)['run']
        _, reused, _, _ = workflow.load_run(self.root, run)
        source = next(item for item in reused['task']['sources'] if item['id'] == 'native-settings')
        self.assertTrue(source['path'].startswith('production/runs/' + changed + '/inputs/'))
        dependency = next(item for item in reused['dependencies']
                          if item['space'] == 'task-source' and item['path'] == source['path'])
        expected = (self.root / source['path']).read_bytes()
        self.assertEqual(c.decode(expected)['steps'], 22)
        before = store.event_rows(self.root, run)
        decision = workspace.workspace(self.root, run, phase='decision')
        self.assertEqual(store.event_rows(self.root, run), before)
        result = execution.execute(self.root, run, decisions_file=decisions(self.root, run))
        self.assertTrue(result['execution_completed'])
        candidate = result['runs'][0]['candidates'][0]
        before = store.event_rows(self.root, run)
        review = workspace.workspace(self.root, run, phase='review', candidate=candidate)
        self.assertEqual(store.event_rows(self.root, run), before)
        for view in (decision, review):
            shown = next(item for item in view['sources'] if item['id'] == source['id'])
            self.assertEqual(shown['path'], source['path'])
            self.assertEqual(shown['sha256'], dependency['sha256'])
            self.assertEqual(shown['text'], expected.decode('utf-8'))
            self.assertEqual(Path(shown['saved_path']).read_bytes(), expected)

    def test_unassessed_check_needs_no_authored_reason_but_judgment_does(self):
        value = self.review_data([('output', 'pass'), ('palette', 'not-assessed')])
        value['checks'][1]['reason'] = ''
        fixtures.write(self.root / 'review.json', value)
        recorded = workflow.review(self.root, self.run, 'review.json')
        self.assertEqual(recorded['data']['review']['checks'][1]['verdict'], 'not-assessed')
        value['checks'][0]['reason'] = ''
        fixtures.write(self.root / 'review.json', value)
        with self.assertRaises(ValueError):
            workflow.review(self.root, self.run, 'review.json')

    def test_unreviewed_rejection_is_not_quality_failure(self):
        before = (self.home / 'iterations.jsonl').read_bytes()
        result = studio.reject(self.root, 'robot', self.iteration, 'Another result is preferred.', actor='Synthetic fixture selector')
        self.assertEqual(result['evaluation'], 'unreviewed')
        self.assertEqual(result['disposition'], 'not_selected')
        self.assertEqual(result['status'], 'candidate')
        self.assertEqual((self.home / 'iterations.jsonl').read_bytes(), before)
        events = store.event_rows(self.root, self.run)
        self.assertEqual(sum(e['event']=='disposition' for e in events), 1)
        self.assertFalse(any(e['event']=='review' for e in events))

    def test_partial_failure_preserves_unassessed_criterion(self):
        self.record_review([('output','fail')])
        state = self.state()
        self.assertEqual(state['evaluation'], 'nonconforming')
        self.assertEqual(state['unassessed_criteria'], ['palette'])
        studio.reject(self.root, 'robot', self.iteration, 'Stop after decisive fixture mismatch.', actor='Synthetic fixture selector')
        self.assertEqual(studio.read_iterations(self.home)[0]['unassessed_criteria'], ['palette'])

    def test_partial_pass_is_not_eligible_for_selection(self):
        record = self.record_review([('output','pass')])
        self.assertEqual(self.state()['evaluation'], 'partially_reviewed')
        with self.assertRaises(ProductionError) as caught:
            workflow.eligible(workflow.load_run(self.root,self.run)[1], record)
        self.assertEqual(caught.exception.diagnostic.code, 'REVIEW_INCOMPLETE')
        with self.assertRaises(ProductionError):
            studio.accept(self.root, 'robot', self.iteration)

    def test_conforming_and_not_selected_are_independent(self):
        record = self.record_review([('output','pass'),('palette','pass')])
        workflow.eligible(workflow.load_run(self.root,self.run)[1], record)
        studio.reject(self.root,'robot',self.iteration,'Alternative composition is preferred.',actor='Synthetic fixture selector')
        state=self.state()
        self.assertEqual((state['evaluation'],state['disposition']), ('conforming','not_selected'))
        self.assertEqual(list((self.home/'accepted').glob('*')), [])

    def test_evaluation_follows_the_latest_review(self):
        nothing = self.record_review([('output','not-assessed'),('palette','not-assessed')])
        self.assertEqual((self.state()['evaluation'], self.state()['review']), ('unreviewed', nothing['sha256']))
        earlier = self.record_review([('output','pass'),('palette','not-applicable')])
        self.assertEqual(self.state()['evaluation'], 'conforming')
        self.record_review([('output','pass'),('palette','indeterminate')])
        self.assertEqual(self.state()['evaluation'], 'indeterminate')
        self.record_review([('output','pass'),('palette','pass')], unresolved=['The fixture border is not yet compared.'])
        self.assertEqual(self.state()['evaluation'], 'indeterminate')
        again = self.record_review([('output','pass'),('palette','not-applicable')])
        self.assertNotEqual(again['sha256'], earlier['sha256'])
        self.assertEqual((self.state()['evaluation'], self.state()['review']), ('conforming', again['sha256']))
        self.assertEqual(self.record_review([('output','pass'),('palette','not-applicable')])['sha256'], again['sha256'])

    def test_indeterminate_verdict_cites_observations(self):
        value = self.review_data([('output','pass'),('palette','indeterminate')])
        value['checks'][1]['observation_indices'] = []
        fixtures.write(self.root / 'review.json', value)
        with self.assertRaisesRegex(ValueError, 'cite actual observations'):
            workflow.review(self.root, self.run, 'review.json')

    def test_hard_indeterminate_prevents_selection(self):
        self.record_review([('output','pass'),('palette','indeterminate')])
        self.assertEqual(self.state()['evaluation'], 'indeterminate')
        self.assertCode('OWNER_ACCEPTANCE_REQUIRED', self.select)
        state = self.state()
        self.assertEqual((state['evaluation'], state['disposition']), ('indeterminate', 'pending'))
        self.assertFalse(any(row['event'] == 'selection' for row in store.event_rows(self.root, self.run)))

    def test_review_of_history_does_not_require_live_prompt(self):
        (self.root/'prompt.txt').unlink()
        record = self.record_review([('output','pass')])
        self.assertEqual(record['event'], 'review')
        self.assertEqual(self.state()['evaluation'], 'partially_reviewed')

    def test_formal_decisions_keep_the_studio_projection_current(self):
        self.record_review([('output','pass')])
        self.assertEqual(validate_studio.validate(self.root), [])
        self.not_selected()
        self.assertEqual(validate_studio.validate(self.root), [])
        entry = c.load(self.root/'gallery.json')['entries'][0]
        self.assertEqual((entry['evaluation'], entry['disposition'], entry['decision_kind']),
                         ('partially_reviewed', 'not_selected', 'disposition'))
        self.assertIn('disposition reason: Another synthetic candidate is preferred.', studio_gallery.detail_file(self.root/'gallery.html', entry['entry_id']).read_text(encoding='utf-8'))

    def test_accepted_image_keeps_its_selection(self):
        self.record_review([('output','pass'),('palette','pass')])
        self.assertCode('SELECTION_REQUIRED', lambda: studio.accept(self.root, 'robot', self.iteration))
        self.select()
        self.assertEqual(validate_studio.validate(self.root), [])
        entry = c.load(self.root/'gallery.json')['entries'][0]
        html = studio_gallery.detail_file(self.root/'gallery.html', entry['entry_id']).read_text(encoding='utf-8')
        self.assertNotIn('rejected:', html)
        self.assertIn('selection reason: Synthetic fixture delivery selection.', html)
        self.assertIn('<b>evaluation</b> conforming', html)
        studio.accept(self.root, 'robot', self.iteration)
        self.assertCode('SELECTED_CANDIDATE', lambda: self.not_selected())
        self.assertCode('SELECTED_CANDIDATE', lambda: studio.reject(
            self.root, 'robot', self.iteration, 'Attempted withdrawal of the accepted image.', actor='Synthetic fixture selector'))
        self.assertEqual((self.state()['disposition'], self.state()['selection_current']), ('selected', True))
        workflow.complete(self.root, self.run)
        self.assertEqual(validate_studio.validate(self.root), [])
        entry = c.load(self.root/'gallery.json')['entries'][0]
        self.assertEqual((entry['status'], entry['disposition'], entry['decision_kind']), ('accepted', 'selected', 'selection'))

    def test_projection_failure_does_not_lose_formal_decision(self):
        with patch.object(studio,'write_gallery',side_effect=OSError('Synthetic display failure')):
            result=studio.reject(self.root,'robot',self.iteration,'Fixture discarded.',actor='Synthetic fixture selector')
        self.assertIn('projection_warning',result)
        self.assertEqual(self.state()['disposition'],'not_selected')
        studio.write_gallery(self.root)
        entry=c.load(self.root/'gallery.json')['entries'][0]
        self.assertEqual(entry['disposition'],'not_selected')
        self.assertEqual(entry['evaluation'],'unreviewed')

    def test_selection_retry_releases_database_writer_before_view_publication(self):
        self.record_review([('output', 'pass'), ('palette', 'pass')])
        selected = self.select()
        original = studio.write_gallery
        observed = []

        def independent_writer(root, *args, **kwargs):
            # An unrelated SQLite writer must be admitted while a display builds.
            # A second connection detects a retained transaction even in one process.
            with closing(sqlite3.connect(store.database(root), timeout=0.1)) as connection, connection:
                connection.execute('BEGIN IMMEDIATE')
                observed.append(connection.in_transaction)
            return original(root, *args, **kwargs)

        with patch.object(studio, 'write_gallery', side_effect=independent_writer):
            retried = workflow.select_value(self.root, self.run, selected['data']['selection'])
        self.assertEqual(retried['sha256'], selected['sha256'])
        self.assertEqual(observed, [True])
        self.assertNotIn('projection_warning', retried)
        self.assertEqual(sum(row['event'] == 'selection' for row in store.event_rows(self.root, self.run)), 1)

    def test_studio_projection_cannot_overwrite_official_state(self):
        rows=studio.read_iterations(self.home)
        rows[0].update(status='rejected', evaluation='nonconforming', disposition='not_selected', decision_kind='disposition')
        studio.write_iterations(self.home,rows)
        stored=json.loads((self.home/'iterations.jsonl').read_text(encoding='utf-8').splitlines()[0])
        for name in ('status','evaluation','disposition','decision_kind'):
            self.assertNotIn(name,stored)
        actual=studio.read_iterations(self.home)[0]
        self.assertEqual((actual['evaluation'],actual['disposition']),('unreviewed','pending'))

    def test_disposition_file_cannot_select(self):
        value=workflow.draft_disposition(self.root,self.run,self.candidate)
        value.update(actor='Synthetic fixture selector',reason='Attempted unsupported transition.',disposition='selected')
        with self.assertRaises(ValueError):
            workflow.disposition_value(self.root,self.run,value)
        self.assertFalse(any(e['event']=='selection' for e in store.event_rows(self.root,self.run)))

    def test_rejection_needs_real_actor_field(self):
        with self.assertRaises(ValueError):
            studio.reject(self.root,'robot',self.iteration,'Explicit reason.',actor=' ')
        self.assertEqual(self.state()['disposition'],'pending')

    def test_studio_validator_accepts_formal_production_projection(self):
        self.assertEqual(validate_studio.validate(self.root), [])
        studio.reject(self.root, 'robot', self.iteration, 'Synthetic selection decision.', actor='Synthetic fixture selector')
        self.assertEqual(validate_studio.validate(self.root), [])

    def test_studio_validator_reports_independent_stored_judgment(self):
        row=json.loads((self.home/'iterations.jsonl').read_text(encoding='utf-8').splitlines()[0])
        row['disposition']='not_selected'
        (self.home/'iterations.jsonl').write_text(json.dumps(row)+'\n',encoding='utf-8')
        errors=validate_studio.validate(self.root)
        self.assertTrue(any('must not be stored' in e for e in errors),errors)
        self.assertEqual(self.state()['disposition'],'pending')

    def test_unreadable_run_is_reported_once(self):
        (self.root/'production').rename(self.root/'production-elsewhere')
        row = studio.read_iterations(self.home)[0]
        self.assertEqual((row['status'], row['production_diagnostic']['code']), ('unavailable', 'RUN_NOT_REGISTERED'))
        errors = validate_studio.validate(self.root)
        self.assertEqual(sum('RUN_NOT_REGISTERED' in e for e in errors), 1, errors)
        self.assertFalse(any('is not one of' in e for e in errors), errors)
        recipe = studio.recipe(self.root, 'robot', row['slot'], iteration=row['iteration_id'])
        self.assertEqual((recipe['source_status'], recipe['production_diagnostic']['code']), ('unavailable', 'RUN_NOT_REGISTERED'))

    def test_candidate_without_studio_row_names_resume(self):
        (self.home/'iterations.jsonl').write_bytes(b'')
        errors = validate_studio.validate(self.root)
        expected = f'candidate {self.candidate} has no iteration row'
        self.assertTrue(any(expected in e and f'resume --root {self.root} --run {self.run}' in e for e in errors), errors)

    def test_corrupt_saved_answer_is_not_used_for_recovery(self):
        import transport_synthetic
        claim=workflow.find(store.event_rows(self.root,self.run),'dispatch-claim')
        answer=self.root/claim['data']['journal']/'answer.json'
        observation=answer.with_name('send-observation.json')
        original=observation.read_bytes()
        before=store.event_rows(self.root,self.run)
        changed=b'{"data": []}'
        answer.write_bytes(changed)
        with patch.object(transport_synthetic,'send') as send, patch.object(transport_synthetic,'lookup') as lookup, \
                self.assertRaises(ProductionError) as caught:
            execution.resume(self.root,self.run)
        # Existing candidate registration pins the answer too, so either the
        # general artifact verifier or response boundary may identify corruption.
        self.assertIn(caught.exception.diagnostic.code, {'RESPONSE_CORRUPT','EVIDENCE_SNAPSHOT_CORRUPT','ARTIFACT_CORRUPT'})
        send.assert_not_called();lookup.assert_not_called()
        self.assertEqual(answer.read_bytes(),changed)
        self.assertEqual(observation.read_bytes(),original)
        self.assertEqual(store.event_rows(self.root,self.run),before)


class IdentityReviewCase(ReviewCase):
    treatment = 'preserve'

    def configure_task(self, task):
        self.original_identity = {'identity': {
            'unfamiliar': {'axis~rim/edge': 'The rim turns inward only when the two shell halves interlock.'},
            'relation': ['The rear rim stays thicker than the front rim in the same plane.'],
            'hidden': 'A shallow notch sits under the lower shell.'},
            'editor_notes': 'These notes are outside the authored identity selection.'}
        fixtures.write(self.root / 'identity.json', self.original_identity)
        task['sources'].append({'id': 'adopted', 'path': 'identity.json', 'role': 'identity definition',
            'disposition': 'applied', 'locator': '/identity',
            'reason': 'A synthetic original with arbitrary conditional details and a relation.',
            'identity': {'subject_ids': ['robot'], 'selectors': ['/identity']}})
        task['criteria'].extend([
            {'id': 'identity-scene', 'strength': 'hard', 'evidence': 'image',
             'text': 'Assess the selected identity treatment against the original and the candidate.',
             'identity_bindings': [{'source': 'adopted', 'subject_ids': ['robot'],
                 'selectors': ['/identity'], 'treatment': self.treatment,
                 'reason': 'Synthetic authored treatment; the fixture makes no claim of visual fidelity.',
                 'carriers': [{'kind': 'text', 'surface': 'primary', 'quote': fixtures.PROMPT}],
                 'variation': None}]},
            {'id': 'identity-whole', 'strength': 'hard', 'evidence': 'image',
             'text': 'Compare the whole subject with its original definitions and relations independently.',
             'identity_review': ['robot']}])

    def all_checks(self, **changes):
        return [(key, changes.get(key, 'pass'))
                for key in ('output', 'palette', 'identity-scene', 'identity-whole')]


class IdentityReviewTests(IdentityReviewCase):
    def test_original_identity_is_frozen_independent_context_only_after_blind_views(self):
        directory, prepared, consumer, _ = workflow.load_run(self.root, self.run)
        original = copy.deepcopy(prepared['identity_coverage'])
        detail = self.original_identity['identity']['unfamiliar']['axis~rim/edge']
        self.assertNotIn(detail, consumer['instructions'])
        before = store.event_rows(self.root, self.run)
        for phase in ('decision', 'review'):
            view = workspace.workspace(self.root, self.run, phase=phase,
                candidate=self.candidate if phase == 'review' else None)
            self.assertEqual(view['identity_coverage'], original)
            self.assertEqual(view['basis']['identity_coverage'], original)
            self.assertIn(detail, json.dumps(view['basis'], ensure_ascii=False))
        observation = workspace.workspace(self.root, self.run, phase='observe', candidate=self.candidate)
        self.assertEqual(set(observation), {'phase', 'run', 'candidate', 'instruction'})
        blind_input = workspace.workspace(self.root, self.run, phase='input')
        self.assertEqual(set(blind_input), {'phase', 'run', 'input_sha256', 'reading', 'prepared_input', 'instruction'})
        self.assertNotIn(detail, json.dumps(blind_input))
        draft = workflow.draft_review(self.root, self.run, self.candidate)
        self.assertTrue(all(row['verdict'] == 'not-assessed' and row['reason'] == '' for row in draft['checks']))
        self.assertEqual((draft['observations'], draft['evidence'], draft['unresolved']), ([], [], []))
        self.assertNotIn('identity_coverage', draft)
        fixtures.write(self.root / 'identity.json', {'identity': 'Later unrelated live definition.'})
        (self.root / 'prompt.txt').unlink()
        again = workspace.workspace(self.root, self.run, phase='review', candidate=self.candidate)
        self.assertEqual(again['identity_coverage'], original)
        saved = next(row for row in again['sources'] if row['id'] == 'adopted')
        self.assertEqual(c.decode(Path(saved['saved_path']).read_bytes()), self.original_identity)
        self.assertEqual(c.digest(Path(saved['saved_path']).read_bytes()), original['sources'][0]['sha256'])
        self.assertEqual(store.event_rows(self.root, self.run), before)

    def test_original_identity_evidence_is_resolved_without_live_source_or_editable_copy(self):
        value = self.review_data(self.all_checks())
        value['observations'].append({'evidence': 'identity-source:adopted', 'locator': {'kind': 'whole'},
            'observation': 'The saved JSON contains the synthetic original definition and relation.',
            'interpretation': 'This original supplies an independent comparison basis, not output proof.',
            'limitations': ['The candidate remains a protocol fixture; no visual fidelity is asserted.']})
        value['checks'][-1]['observation_indices'].append(1)
        fixtures.write(self.root / 'review.json', value)
        (self.root / 'identity.json').unlink()
        recorded = workflow.review(self.root, self.run, 'review.json')
        source = next(row for row in recorded['data']['review']['evidence'] if row['id'] == 'identity-source:adopted')
        self.assertEqual(source['kind'], 'json')
        self.assertEqual(c.decode((self.root / source['path']).read_bytes()), self.original_identity)
        self.assertIn('source_pointer', source['relation'])
        self.assertEqual(c.load(self.root / 'review.json')['evidence'], [])

    def test_omitted_or_unassessed_whole_identity_check_cannot_be_selected_or_waived(self):
        prepared = workflow.load_run(self.root, self.run)[1]
        for verdict in (None, 'not-assessed'):
            with self.subTest(verdict=verdict):
                checks = self.all_checks(**{'identity-whole': verdict})
                reviewed = self.record_review([(key, item) for key, item in checks if item is not None])
                needed = workflow.selection_requirements(prepared, reviewed)
                self.assertEqual(needed['unassessed_hard_criteria'], ['identity-whole'])
                self.assertCode('REVIEW_INCOMPLETE', lambda: workflow.eligible(prepared, reviewed,
                    {'criteria': ['identity-whole']}))
                self.assertCode('REVIEW_INCOMPLETE', self.select)
        self.assertFalse(any(row['event'] == 'selection' for row in store.event_rows(self.root, self.run)))

    def test_concern_outside_extracted_criteria_uses_existing_unresolved_selection_block(self):
        concern = 'The original relationship may not be decidable at the fixture scale; it is not an extracted check.'
        reviewed = self.record_review(self.all_checks(), unresolved=[concern])
        self.assertEqual(reviewed['data']['review']['unresolved'], [concern])
        self.assertEqual(self.state()['evaluation'], 'indeterminate')
        self.assertCode('OWNER_ACCEPTANCE_REQUIRED', self.select)

    def test_passing_identity_review_cannot_cite_only_reference_pixels(self):
        value = self.review_data(self.all_checks())
        image = self.row(self.candidate)['result']['path']
        value['evidence'] = [{'id': 'reference-only', 'path': image, 'kind': 'image',
            'relation': 'Synthetic supplementary image, not a candidate observation.', 'limitations': []}]
        value['observations'][0]['evidence'] = 'reference-only'
        fixtures.write(self.root / 'review.json', value)
        with self.assertRaisesRegex(ValueError, 'actual candidate'):
            workflow.review(self.root, self.run, 'review.json')


class SharedIdentitySourceReviewTests(IdentityReviewCase):
    def configure_task(self, task):
        super().configure_task(task)
        source = copy.deepcopy(task['sources'][-1])
        source.update(id='adopted-condition', locator='/identity/unfamiliar')
        source['identity']['selectors'] = ['/identity/unfamiliar']
        task['sources'].append(source)
        bindings = task['criteria'][-2]['identity_bindings']
        bindings.append({**copy.deepcopy(bindings[0]), 'source': source['id'],
                         'selectors': ['/identity/unfamiliar']})

    def test_same_saved_original_is_inlined_once_while_both_identity_scopes_remain(self):
        view = workspace.workspace(self.root, self.run, phase='review', candidate=self.candidate)
        sources = {row['id']: row for row in view['sources'] if row['id'].startswith('adopted')}
        self.assertEqual(set(sources), {'adopted', 'adopted-condition'})
        self.assertEqual(sum('text' in row for row in sources.values()), 1)
        self.assertEqual(c.decode(sources['adopted']['text'].encode('utf-8')), self.original_identity)
        self.assertEqual(sources['adopted-condition']['content_ref'], 'adopted')
        for source in sources.values():
            self.assertEqual(c.decode(Path(source['saved_path']).read_bytes()), self.original_identity)
        coverage = {row['id']: row for row in view['identity_coverage']['sources']}
        self.assertEqual(coverage['adopted']['selectors'], ['/identity'])
        self.assertEqual(coverage['adopted-condition']['selectors'], ['/identity/unfamiliar'])
        self.assertEqual(sources['adopted-condition']['identity'],
                         {'subject_ids': ['robot'], 'selectors': ['/identity/unfamiliar']})


class UnresolvedIdentityReviewTests(IdentityReviewCase):
    treatment = 'unresolved'

    def test_unresolved_binding_blocks_its_criterion_and_whole_subject_pass(self):
        for passing in ('identity-scene', 'identity-whole'):
            with self.subTest(passing=passing):
                changes = {'identity-scene': 'indeterminate', 'identity-whole': 'indeterminate', passing: 'pass'}
                self.review_data(self.all_checks(**changes))
                with self.assertRaisesRegex(ValueError, 'unresolved identity obligation'):
                    workflow.review(self.root, self.run, 'review.json')
        reviewed = self.record_review(self.all_checks(**{
            'identity-scene': 'indeterminate', 'identity-whole': 'indeterminate'}))
        self.assertEqual([row['verdict'] for row in reviewed['data']['review']['checks']][-2:],
                         ['indeterminate', 'indeterminate'])
        self.assertCode('OWNER_ACCEPTANCE_REQUIRED', self.select)

    def test_narrower_resolved_and_not_exposed_treatments_replace_effective_unresolved_scope(self):
        import identity_coverage
        directory, prepared, _, rows = workflow.load_run(self.root, self.run)
        revised = copy.deepcopy(prepared)
        criterion = revised['task']['criteria'][-2]
        base = criterion['identity_bindings'][0]
        for selectors, treatment in [(['/identity/unfamiliar', '/identity/relation'], 'preserve'),
                                     (['/identity/hidden'], 'not-exposed')]:
            criterion['identity_bindings'].append({**copy.deepcopy(base), 'selectors': selectors,
                'treatment': treatment, 'reason': 'Explicit narrower synthetic scene choice.',
                'carriers': base['carriers'] if treatment == 'preserve' else []})
        revised['identity_coverage'] = identity_coverage.compile(revised['task'],
            lambda path: (self.root / path).read_bytes(), context={
                'subject_ids': ['robot'], 'required_subject_ids': ['robot'],
                'text': {'primary': {'text': fixtures.PROMPT, 'field': ['prompt'],
                                    'sha256': c.digest(fixtures.PROMPT.encode('utf-8'))}}})
        self.assertTrue(revised['identity_coverage']['unresolved'])
        value = self.review_data(self.all_checks())
        candidate = workflow.find(rows, 'candidate', self.candidate)
        raw = c.object_read(directory, candidate['data']['files'][0]['sha256'])
        workflow.validate_review(value, revised, candidate, raw)
        hidden = next(row for row in revised['identity_coverage']['sources'][0]['terminals']
                      if row['pointer'] == '/identity/hidden')
        self.assertEqual(hidden['value'], self.original_identity['identity']['hidden'])
        self.assertEqual(hidden['coverage'][0]['treatment'], 'not-exposed')


class IdentityMediaReviewCase(ReviewCase):
    image_format = 'SVG'
    declare_source = False

    def configure_task(self, task):
        from prepare_generation_references import prepare_references
        from production_identity import reference_id
        extension = self.image_format.lower()
        self.original = self.root.parent / ('original-identity.' + extension)
        if self.image_format == 'SVG':
            self.original.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="32" height="16">'
                                     '<rect width="32" height="16" fill="#5078a0"/></svg>', encoding='utf-8')
        else:
            from PIL import Image
            Image.new('RGB', (32, 16), '#5078a0').save(self.original, format=self.image_format)
        self.original_bytes = self.original.read_bytes()
        references = prepare_references([{'role': 'identity',
            'source': {'kind': 'supplied-file', 'reference_id': 'original-identity',
                       'resolved_path': str(self.original)},
            'subject_uses': [{'subject_id': 'robot', 'use': 'identity', 'priority': 0}]}],
            model=fixtures.MODEL_ID, output_dir=self.root / 'identity-media',
            max_side=64, transport_mode='single-board')
        fixtures.write(self.root / 'identity-references.json', references)
        task['generation']['references'] = 'identity-references.json'
        specification = c.load(self.root / 'spec.json')
        specification['render_intent']['execution_mode'] = 'reference-guided'
        fixtures.write(self.root / 'spec.json', specification)
        reference = reference_id(references['selected_references'][0])
        self.source_id = 'reference:' + reference
        if self.declare_source:
            self.source_id = 'adopted-pixels'
            self.declared_path = 'identity-original.' + extension
            c.atomic(self.root / self.declared_path, self.original_bytes)
            task['sources'].append({'id': self.source_id, 'path': self.declared_path,
                'role': 'identity definition', 'disposition': 'applied', 'locator': 'whole',
                'reason': 'The task directly selects these original synthetic identity pixels.',
                'identity': {'subject_ids': ['robot'], 'selectors': ['']}})
        task['criteria'].append({'id': 'identity-media', 'strength': 'hard', 'evidence': 'image',
            'text': 'Independently compare the complete synthetic original and its actual carrier.',
            'identity_review': ['robot'], 'identity_bindings': [{
                'source': self.source_id, 'subject_ids': ['robot'], 'selectors': [''],
                'treatment': 'preserve', 'reason': 'A synthetic media scope and provenance test.',
                'carriers': [{'kind': 'reference', 'reference': reference, 'use': 'identity'}],
                'variation': None}]})


class IdentityMediaReviewTests(IdentityMediaReviewCase):
    def test_derived_original_and_actual_delivery_are_available_after_external_original_is_removed(self):
        self.original.unlink()
        view = workspace.workspace(self.root, self.run, phase='review', candidate=self.candidate)
        source = next(row for row in view['sources'] if row['id'] == self.source_id)
        self.assertEqual(Path(source['saved_path']).read_bytes(), self.original_bytes)
        self.assertEqual(source['path'], str(self.original))
        carrier = view['identity_coverage']['bindings'][0]['carriers'][0]
        self.assertEqual(carrier['reference_source_sha256'], source['sha256'])
        self.assertNotEqual(carrier['carrier_sha256'], source['sha256'])
        evidence = view['basis']['evidence']
        original = next(row for row in evidence if row['id'] == 'identity-source:' + self.source_id)
        delivered = next(row for row in evidence if row['id'].startswith('delivered-reference:'))
        self.assertEqual((self.root / original['path']).read_bytes(), self.original_bytes)
        self.assertEqual(c.sha256_file(self.root / delivered['path']), carrier['carrier_sha256'])
        recorded = self.record_review([('output', 'pass'), ('palette', 'pass'), ('identity-media', 'pass')])
        self.assertEqual(recorded['data']['media'][original['id']]['format'], 'SVG')
        self.assertEqual(recorded['data']['media'][delivered['id']]['format'], 'PNG')


class IdentityDeclaredSvgReviewTests(IdentityMediaReviewCase):
    declare_source = True

    def test_direct_declared_image_remains_region_observable_at_saved_bytes(self):
        prepared = workflow.load_run(self.root, self.run)[1]
        sources = prepared['identity_coverage']['sources']
        self.assertEqual([row['id'] for row in sources], [self.source_id])
        self.assertFalse(sources[0]['derived'])
        self.assertEqual(sources[0]['format'], 'text' if self.image_format == 'SVG' else 'media')
        value = self.review_data([('output', 'pass'), ('palette', 'pass'), ('identity-media', 'pass')])
        evidence_id = 'identity-source:' + self.source_id
        value['observations'].append({'evidence': evidence_id,
            'locator': {'kind': 'image-region', 'x': 0, 'y': 0, 'width': 0.5, 'height': 1},
            'observation': 'The selected original region is a locally decoded synthetic image.',
            'interpretation': 'This is source provenance and access evidence, not generated fidelity.',
            'limitations': ['Only the declared synthetic region is inspected.']})
        value['checks'][-1]['observation_indices'].append(1)
        fixtures.write(self.root / 'review.json', value)
        self.original.unlink()
        (self.root / self.declared_path).unlink()
        recorded = workflow.review(self.root, self.run, 'review.json')
        self.assertEqual(recorded['data']['media'][evidence_id]['kind'], 'image')
        self.assertEqual(recorded['data']['media'][evidence_id]['format'], self.image_format)


class IdentityDeclaredPngReviewTests(IdentityDeclaredSvgReviewTests):
    image_format = 'PNG'


class StoredContentTests(ReviewCase):
    """Reused verification still catches a changed stored object in the next check scope."""

    def corrupt(self, key):
        path = workflow.run_dir(self.root, self.run) / 'objects' / key
        path.write_bytes(path.read_bytes() + b'corrupt')

    def assertRefused(self, key, code):
        with self.assertRaises(ProductionError) as caught:
            workflow.load_run(self.root, self.run)
        refused = caught.exception.diagnostic.as_dict()
        self.assertEqual((refused['code'], refused['artifact']), (code, 'objects/' + key))

    def test_corrupt_manifest_object_is_caught_after_reuse(self):
        import runtime_snapshot
        prepared = workflow.load_run(self.root, self.run)[1]
        key = next(item for item in prepared['dependencies'] if item['space'] == 'studio')['sha256']
        with runtime_snapshot.public_call():
            workflow.load_run(self.root, self.run)
            self.corrupt(key)
            with store.transaction(self.root):
                self.assertRefused(key, 'EVIDENCE_SNAPSHOT_CORRUPT')
        self.assertRefused(key, 'EVIDENCE_SNAPSHOT_CORRUPT')

    def test_a_recorded_selection_that_breaks_the_selection_schema_names_its_event(self):
        self.record_review([('output', 'pass'), ('palette', 'pass')])
        selected = self.select()
        data = copy.deepcopy(selected['data'])
        data['selection'].pop('slot')
        data['selection']['replaces'] = selected['sha256']
        recorded = store.append(self.root, self.run, selected['input_sha256'], 'selection', data)
        with self.assertRaises(ProductionError) as caught:
            workflow.load_run(self.root, self.run)
        found = caught.exception.diagnostic.as_dict()
        self.assertEqual((found['code'], found['run'], found['event'], found['kind'], found['sequence']),
                         ('EVENT_CHAIN_CORRUPT', self.run, recorded['sha256'], 'selection', recorded['sequence']))
        self.assertIn(f"The recorded selection event at sequence {recorded['sequence']} is not valid", found['message'])
        self.assertIn("missing required property 'slot'", found['message'])

    def test_corrupt_evidence_object_is_caught_after_reuse(self):
        import runtime_snapshot
        key = workflow.find(store.event_rows(self.root, self.run), 'candidate', self.candidate)['data']['files'][0]['sha256']
        with runtime_snapshot.public_call():
            workflow.load_run(self.root, self.run)
            self.corrupt(key)
            # The object reader refuses bytes that differ from the object's name.
            with store.transaction(self.root):
                self.assertRefused(key, 'EVIDENCE_SNAPSHOT_MISSING')
        self.assertRefused(key, 'EVIDENCE_SNAPSHOT_MISSING')


class CompletedDispositionTests(ReviewCase):
    """Retained candidates can be retired without reopening completed production."""
    count = 2

    def completed(self, *, accept=False):
        self.record_review([('output', 'pass'), ('palette', 'pass')])
        selected = self.select()
        if accept:
            studio.accept(self.root, 'robot', self.iteration)
        return selected, workflow.complete(self.root, self.run)

    def test_completed_run_disposes_unselected_studio_candidate_once(self):
        import work_ledger
        _, done = self.completed(accept=True)
        for step in work_ledger.read_current(self.root)['steps']:
            work_ledger.step_done(self.root, step['n'])
        finished = work_ledger.finish(self.root, self.run)
        task_path = work_ledger.task_path(self.root, finished['task_id'])
        other = self.candidates[1]
        iteration = self.row(other)['iteration_id']
        before = (self.home / 'iterations.jsonl').read_bytes()
        task_before = task_path.read_bytes()
        self.assertEqual(finished['work_state'], 'completed')
        self.assertIsNone(work_ledger.read_current(self.root))
        events_before = store.event_rows(self.root, self.run)
        runs_before = store.runs(self.root)
        self.assertIn('1 candidate waiting', studio.status(self.root))
        reason = 'The other retained synthetic image is not selected.'
        result = studio.reject(self.root, 'robot', iteration, reason, actor='Synthetic fixture selector')
        repeated = studio.reject(self.root, 'robot', iteration, reason, actor='Synthetic fixture selector')
        self.assertEqual(result['production_decision'], repeated['production_decision'])
        self.assertEqual((result['status'], result['evaluation'], result['disposition']),
                         ('candidate', 'unreviewed', 'not_selected'))
        self.assertIn('0 candidates waiting', studio.status(self.root))
        self.assertEqual((self.home / 'iterations.jsonl').read_bytes(), before)
        self.assertEqual(task_path.read_bytes(), task_before)
        self.assertIsNone(work_ledger.read_current(self.root))
        loaded = workflow.load_run(self.root, self.run, force=True)
        self.assertEqual(loaded.rows[:len(events_before)], events_before)
        self.assertEqual([row['event'] for row in loaded.rows[len(events_before):]], ['disposition'])
        self.assertEqual(store.runs(self.root), runs_before)
        self.assertEqual(sum(row['event'] == 'disposition' for row in loaded.rows), 1)
        entry = next(row for row in c.load(self.root / 'gallery.json')['entries']
                     if (row.get('production') or {}).get('candidate') == other)
        self.assertEqual(entry['disposition'], 'not_selected')
        self.assertEqual(workflow.complete(self.root, self.run)['sha256'], done['sha256'])
        self.assertEqual(work_ledger.finish(self.root, self.run), finished)
        status = execution.status(self.root, self.run)['runs'][0]
        self.assertEqual(status['task_disposition'], 'completed')
        self.assertIsNone(status['next_action'])
        self.assertEqual(validate_studio.validate(self.root), [])

    def test_completed_selection_can_be_retired_without_changing_completion(self):
        _, done = self.completed()
        task_before = (self.root / 'work/current.json').read_bytes()
        result = studio.reject(self.root, 'robot', self.iteration,
                               'Retire this previously delivered synthetic candidate.',
                               actor='Synthetic fixture selector')
        self.assertEqual((result['evaluation'], result['disposition']), ('conforming', 'not_selected'))
        loaded = workflow.load_run(self.root, self.run, force=True)
        self.assertCode('SELECTION_WITHDRAWN', lambda: workflow.current_selection(loaded.prepared, loaded.rows))
        self.assertEqual(workflow.verify_completion(self.root, self.run, loaded.prepared['task']['task_id']), done)
        self.assertEqual(workflow.complete(self.root, self.run)['sha256'], done['sha256'])
        pending = workflow.draft_disposition(self.root, self.run, self.candidate)
        pending.update(disposition='pending', actor='Synthetic fixture selector', reason='Attempt to reopen candidate attention.')
        with self.assertRaisesRegex(ValueError, 'run is complete'):
            workflow.disposition_value(self.root, self.run, pending)
        with self.assertRaisesRegex(ValueError, 'run is complete'):
            self.record_review([('output', 'pass')])
        status = execution.status(self.root, self.run)['runs'][0]
        self.assertEqual(status['task_disposition'], 'completed')
        self.assertFalse(status['selection_ready'])
        self.assertIsNone(status['next_action'])
        self.assertEqual([item['code'] for item in status['selection_diagnostics']], ['SELECTION_WITHDRAWN'])
        self.assertIn('run is closed', status['selection_diagnostics'][0]['required_action'])
        self.assertEqual((self.root / 'work/current.json').read_bytes(), task_before)
        self.assertEqual(sum(row['event'] == 'completion' for row in store.event_rows(self.root, self.run)), 1)

    def test_completed_candidate_must_be_superseded_before_disposition(self):
        _, done = self.completed(accept=True)
        self.assertCode('SELECTED_CANDIDATE', lambda: studio.reject(
            self.root, 'robot', self.iteration, 'Attempt to discard the accepted image.',
            actor='Synthetic fixture selector'))
        original = self.row(self.candidate)
        imported = studio.iterate(self.root, 'robot', original['slot'], self.root / original['result']['path'],
                                  package=None, request=None, response=None,
                                  note='Independent synthetic import of the same pixels.')
        studio.accept(self.root, 'robot', imported['iteration_id'])
        # Identical image bytes do not decide either iteration's disposition.
        self.assertEqual(self.state()['disposition'], 'selected')
        result = studio.reject(self.root, 'robot', self.iteration,
                               'The separately imported iteration now owns the slot.',
                               actor='Synthetic fixture selector')
        self.assertEqual((result['status'], result['disposition']), ('superseded', 'not_selected'))
        accepted = studio.acceptance_state(self.root, 'robot', original['slot'])
        self.assertEqual(accepted['iteration_id'], imported['iteration_id'])
        self.assertEqual(workflow.complete(self.root, self.run)['sha256'], done['sha256'])
        self.assertEqual(validate_studio.validate(self.root), [])


class GalleryIsolationTests(ReviewCase):
    """Two runs with two candidates each, projected into one Studio slot."""
    count = 2

    def setUp(self):
        super().setUp()
        self.second = workflow.prepare(self.root, 'task.json')['run']
        result = execution.execute(self.root, self.second, decisions_file=decisions(self.root, self.second))
        self.assertTrue(result['execution_completed'], result.get('warnings'))

    def test_recipe_verifies_selected_run_without_projecting_other_candidates(self):
        with patch.object(workflow, 'read_run', wraps=workflow.read_run) as read_run:
            recipe = studio.recipe(self.root, 'robot', 'candidate', iteration=self.iteration)
        self.assertEqual(recipe['iteration_id'], self.iteration)
        self.assertEqual([call.args[1] for call in read_run.call_args_list], [self.run])

    def test_one_bad_run_marks_only_its_own_rows(self):
        candidate = workflow.find(store.event_rows(self.root, self.run), 'candidate', self.candidate)
        path = workflow.run_dir(self.root, self.run) / 'objects' / candidate['data']['files'][0]['sha256']
        path.write_bytes(b'not the captured PNG')
        original = workflow.read_run
        loads = []
        def counted(root, run):
            loads.append(run)
            return original(root, run)
        with patch.object(workflow, 'read_run', side_effect=counted):
            rows = studio.read_iterations(self.home)
        self.assertEqual(sorted(loads), sorted([self.run, self.second]))
        by_run = {}
        for row in rows:
            by_run.setdefault(row['production']['run'], []).append(row)
        self.assertEqual({run: len(items) for run, items in by_run.items()}, {self.run: 2, self.second: 2})
        for row in by_run[self.run]:
            self.assertEqual((row['status'], row['production_diagnostic']['artifact']),
                             ('unavailable', 'objects/' + candidate['data']['files'][0]['sha256']))
        for row in by_run[self.second]:
            self.assertNotIn('production_diagnostic', row)
            self.assertEqual((row['status'], row['evaluation']), ('candidate', 'unreviewed'))


class SelectionTests(ReviewCase):
    """Two candidates of one run: one holds the run's selection at a time."""
    count = 2

    def setUp(self):
        super().setUp()
        self.other = self.candidates[1]
        for candidate in self.candidates:
            self.record_review([('output','pass'),('palette','pass')], candidate)

    def test_another_candidate_needs_a_prior_disposition(self):
        self.select()
        self.assertCode('SELECTION_CONFLICT', lambda: self.select(self.other))
        self.assertEqual((self.state()['disposition'], self.state()['selection_current']), ('selected', True))
        self.not_selected()
        self.select(self.other)
        self.assertEqual(self.state()['disposition'], 'not_selected')
        self.assertEqual((self.state(self.other)['disposition'], self.state(self.other)['selection_current']), ('selected', True))
        self.assertEqual(validate_studio.validate(self.root), [])

    def test_a_selection_drafted_before_another_one_is_refused(self):
        earlier = workflow.draft_selection(self.root, self.run, self.candidate)
        earlier.update(reason='Synthetic selection drafted before another one was recorded.')
        fixture.selection(self.root, self.run, earlier)
        fixtures.write(self.root / 'earlier-selection.json', earlier)
        first = self.select()
        self.assertEqual((earlier['replaces'], first['data']['selection']['replaces']), (None, None))
        self.assertEqual(workflow.draft_selection(self.root, self.run, self.candidate)['replaces'], first['sha256'])
        before = store.event_rows(self.root, self.run)
        self.assertCode('SELECTION_REPLACED', lambda: workflow.select(self.root, self.run, 'earlier-selection.json'))
        self.assertEqual(workflow.select(self.root, self.run, 'selection.json'), first)
        self.assertEqual(store.event_rows(self.root, self.run), before)

    def test_a_newer_review_ends_the_selection(self):
        self.select()
        self.record_review([('output','pass'),('palette','fail')])
        state = self.state()
        self.assertEqual((state['evaluation'], state['disposition'], state['selection_current']), ('nonconforming', 'selected', False))
        self.assertEqual([d['code'] for d in state['selection_diagnostics']], ['SELECTION_REVIEW_CHANGED'])
        self.select(self.other)
        self.assertEqual([d['code'] for d in self.state()['selection_diagnostics']], ['SELECTION_REVIEW_CHANGED', 'SELECTION_REPLACED'])
        self.assertTrue(self.state(self.other)['selection_current'])
        entry = next(e for e in c.load(self.root/'gallery.json')['entries'] if e['production']['candidate'] == self.candidate)
        self.assertEqual([d['code'] for d in entry['selection_diagnostics']], ['SELECTION_REVIEW_CHANGED', 'SELECTION_REPLACED'])


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
