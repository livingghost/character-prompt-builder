"""Review/Studio ownership tests. All decisions describe synthetic fixture PNGs."""
from __future__ import annotations
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import execution_contract as c
import production_case_fixtures as fixtures
import production_execution as execution
import production_fixtures as fixture
import production_workflow as workflow
import production_store as store
import studio
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
        fixtures.write(self.root / 'task.json', task)
        self.run = workflow.prepare(self.root, 'task.json')['run']
        result = execution.execute(self.root, self.run, decisions_file=decisions(self.root, self.run))
        self.assertTrue(result['execution_completed'], result.get('warnings'))
        self.candidates = result['runs'][0]['candidates']
        self.candidate = self.candidates[0]
        self.home = studio.character_home(self.root, 'robot')
        self.iteration = self.row(self.candidate)['iteration_id']

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
        self.assertIn('disposition reason: Another synthetic candidate is preferred.', (self.root/'gallery.html').read_text(encoding='utf-8'))

    def test_accepted_image_keeps_its_selection(self):
        self.record_review([('output','pass'),('palette','pass')])
        self.assertCode('SELECTION_REQUIRED', lambda: studio.accept(self.root, 'robot', self.iteration))
        self.select()
        self.assertEqual(validate_studio.validate(self.root), [])
        html = (self.root/'gallery.html').read_text(encoding='utf-8')
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
        claim=workflow.find(store.event_rows(self.root,self.run),'dispatch-claim')
        answer=self.root/claim['data']['journal']/'answer.json'
        answer.write_text('{"data": []}',encoding='utf-8')
        with self.assertRaises(ProductionError) as caught:
            execution.resume(self.root,self.run)
        # Existing candidate registration pins the answer too, so either the
        # general artifact verifier or response boundary may identify corruption.
        self.assertIn(caught.exception.diagnostic.code, {'RESPONSE_CORRUPT','EVIDENCE_SNAPSHOT_CORRUPT','ARTIFACT_CORRUPT'})


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


class GalleryIsolationTests(ReviewCase):
    """Two runs with two candidates each, projected into one Studio slot."""
    count = 2

    def setUp(self):
        super().setUp()
        self.second = workflow.prepare(self.root, 'task.json')['run']
        result = execution.execute(self.root, self.second, decisions_file=decisions(self.root, self.second))
        self.assertTrue(result['execution_completed'], result.get('warnings'))

    def test_one_bad_run_marks_only_its_own_rows(self):
        candidate = workflow.find(store.event_rows(self.root, self.run), 'candidate', self.candidate)
        path = workflow.run_dir(self.root, self.run) / 'objects' / candidate['data']['files'][0]['sha256']
        path.write_bytes(b'not the captured PNG')
        original = workflow.load_run
        loads = []
        def counted(root, run):
            loads.append(run)
            return original(root, run)
        with patch.object(workflow, 'load_run', side_effect=counted):
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
