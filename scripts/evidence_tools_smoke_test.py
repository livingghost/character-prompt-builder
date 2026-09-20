#!/usr/bin/env python3
"""Executable, explicitly synthetic integration checks for evidence tools."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import unittest

import artifact_review as ar
import evaluation_evidence as ev
import execution_contract as c
import production_workflow as w
import production_workflow_smoke_test as fixtures


class EvidenceToolsTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ProductionTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root

    def captured(self):
        return self.fixture.candidate()

    def reviewed(self):
        run, candidate = self.fixture.candidate()
        self.fixture.record_review(run, candidate)
        return run, candidate

    def study(self, run=None, candidate=None):
        if run:
            task = w.load_run(self.root, run)[1]['task']
        else:
            task = self.fixture.spec
        criterion = task['criteria'][0]
        return {'purpose': 'Synthetic exercise of evidence handling, not image quality.',
                'cases': [{'id': 'empty-scene', 'origin': 'constructed-case',
                           'origin_note': 'An explicitly synthetic no-cast test.',
                           'inputs': [task['sources'][0]['path']],
                           'criteria': [{'id': criterion['id'], 'dimension': 'declared condition',
                                         'kind': 'technical', 'text': criterion['text']}]}],
                'conditions': [{'id': 'condition-secret-alpha', 'description': 'Synthetic condition, not an older product.'}],
                'trials': [{'id': 'trial-1', 'case': 'empty-scene', 'condition': 'condition-secret-alpha',
                            'run': run, 'candidate': candidate, 'measurements': None}]}

    def save_study(self, study):
        (self.root / 'study.json').write_bytes(c.encoded(study))
        return 'study.json'

    def test_review_uses_pinned_inputs_and_real_output(self):
        run, candidate = self.captured()
        data, files = ar.build(self.root, run)
        self.assertTrue(data['current'])
        self.assertEqual(data['candidates'][0]['id'], candidate['sha256'])
        self.assertTrue(data['sources'][0]['file']['download'] in files)
        self.assertEqual(len(data['candidates']), 1)
        self.assertFalse(data['completion_recorded'])

    def test_no_artifact_is_not_a_generated_result(self):
        run = self.fixture.prepare()
        data, _ = ar.build(self.root, run)
        self.assertEqual(data['candidates'], [])
        self.assertIn('No candidate has been captured', ar.render(data))

    def test_every_candidate_is_visible(self):
        run, _ = self.captured()
        (self.root / 'extra.txt').write_text('Different synthetic candidate.')
        w.capture(self.root, run, 'extra.txt', 'Synthetic candidate, not a model result.')
        data, _ = ar.build(self.root, run)
        self.assertEqual(len(data['candidates']), 2)

    def test_stale_file_shows_original_saved_bytes(self):
        run, _ = self.captured()
        data, original = ar.build(self.root, run)
        f = data['candidates'][0]['files'][0]
        (self.root / f['path']).write_text('CHANGED AFTER CAPTURE')
        changed, files = ar.build(self.root, run)
        self.assertFalse(changed['current'])
        self.assertEqual(files[f['download']], original[f['download']])
        self.assertIn('STALE', ar.render(changed))

    def test_source_change_is_separate_from_saved_evidence(self):
        run, _ = self.captured()
        task = w.load_run(self.root, run)[1]['task']
        (self.root / task['sources'][0]['path']).write_text('Changed source')
        self.assertFalse(ar.build(self.root, run)[0]['current'])

    def test_html_is_escaped(self):
        run, _ = self.captured()
        data, _ = ar.build(self.root, run)
        data['direction']['purpose'] = '</pre><script>bad()</script>'
        output = ar.render(data)
        self.assertNotIn('<script>', output)
        self.assertIn('&lt;script&gt;', output)

    def test_active_file_types_are_not_published_as_html(self):
        self.assertEqual(ar.attachment(b'<html><script>bad()</script>'), ('.txt', 'text'))
        self.assertEqual(ar.attachment(b'<svg onload="bad()"/>'), ('.txt', 'text'))

    def test_export_does_not_change_production_receipts(self):
        run, _ = self.reviewed()
        before = w.load_run(self.root, run)[3]
        result = ar.export(self.root, run, 'reviews/actual')
        self.assertTrue(Path(result['html']).is_file())
        self.assertEqual(before, w.load_run(self.root, run)[3])
        inventory = json.loads((Path(result['output']) / 'files.json').read_text())
        for name, entry in inventory.items():
            self.assertEqual(c.digest((Path(result['output']) / name).read_bytes()), entry['sha256'])

    def test_export_never_overwrites_existing_output(self):
        run, _ = self.captured()
        ar.export(self.root, run, 'reviews/snapshot')
        with self.assertRaises(ValueError):
            ar.export(self.root, run, 'reviews/snapshot')

    def test_export_path_escape_and_canon_target(self):
        run, _ = self.captured()
        for path in ['../outside', 'canon/report', 'reviews/../../outside']:
            with self.subTest(path=path), self.assertRaises(ValueError):
                ar.export(self.root, run, path)

    def test_export_symlink_refused(self):
        run, _ = self.captured()
        (self.root / 'reviews').symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            ar.export(self.root, run, 'reviews/report')

    def test_corrupt_saved_artifact_refused(self):
        run, candidate = self.captured()
        directory = w.load_run(self.root, run)[0]
        (directory / 'objects' / candidate['data']['files'][0]['sha256']).write_bytes(b'corrupt')
        with self.assertRaises(ValueError):
            ar.build(self.root, run)

    def test_pending_trial_does_not_become_a_zero_measurement(self):
        data, _, _ = ev.build(self.root, self.save_study(self.study()))
        self.assertEqual(data['trials'][0]['state'], 'not-run')
        self.assertIsNone(data['summary'][0]['assessed_pass_fraction'])
        self.assertEqual(data['summary'][0]['counts']['missing'], 1)
        self.assertIsNone(data['metrics'][0]['reported_metrics']['total_tokens']['mean'])

    def test_unreviewed_is_not_failure(self):
        run, candidate = self.captured()
        data, _, _ = ev.build(self.root, self.save_study(self.study(run, candidate['sha256'])))
        self.assertEqual(data['trials'][0]['state'], 'not-reviewed')
        self.assertEqual(data['summary'][0]['counts']['fail'], 0)
        self.assertIsNone(data['summary'][0]['assessed_pass_fraction'])

    def test_review_aggregation_uses_actual_receipt(self):
        run, candidate = self.reviewed()
        data, _, _ = ev.build(self.root, self.save_study(self.study(run, candidate['sha256'])))
        self.assertEqual(data['trials'][0]['state'], 'reviewed')
        self.assertEqual(data['summary'][0]['counts']['pass'], 1)
        self.assertEqual(data['summary'][0]['kind'], 'technical')
        self.assertIsNone(data['metrics'][0]['reported_metrics']['elapsed_seconds']['mean'])

    def test_repeated_same_output_is_not_an_independent_trial(self):
        run, candidate = self.captured()
        spec = self.study(run, candidate['sha256'])
        spec['trials'].append({**spec['trials'][0], 'id': 'trial-2'})
        with self.assertRaisesRegex(ValueError, 'independent'):
            ev.build(self.root, self.save_study(spec))

    def test_other_candidate_from_same_run_not_independent(self):
        run, candidate = self.captured()
        (self.root / 'other.txt').write_text('Another synthetic candidate.')
        other = w.capture(self.root, run, 'other.txt', 'Synthetic second candidate.')
        spec = self.study(run, candidate['sha256'])
        spec['trials'].append({**spec['trials'][0], 'id': 'trial-2', 'candidate': other['sha256']})
        with self.assertRaisesRegex(ValueError, 'independent'):
            ev.build(self.root, self.save_study(spec))

    def test_evaluation_preserves_source_bytes_and_missing_counts(self):
        run, candidate = self.captured()
        data, _, files = ev.build(self.root, self.save_study(self.study(run, candidate['sha256'])))
        source = data['trials'][0]['sources'][0]['file']
        self.assertEqual(c.digest(files[source['download']]), source['sha256'])
        self.assertEqual(data['trial_states'][0]['counts']['not-reviewed'], 1)
        self.assertEqual(data['trials'][0]['candidate_count'], 1)

    def test_candidate_must_be_explicit(self):
        run, _ = self.captured()
        with self.assertRaisesRegex(ValueError, 'specify the actual candidate'):
            ev.build(self.root, self.save_study(self.study(run)))

    def test_changed_case_inputs_not_treated_as_same_task(self):
        run, candidate = self.captured()
        spec = self.study(run, candidate['sha256'])
        (self.root / spec['cases'][0]['inputs'][0]).write_text('Different case')
        with self.assertRaisesRegex(ValueError, 'case input bytes'):
            ev.build(self.root, self.save_study(spec))

    def test_matching_criterion_id_with_different_text_refused(self):
        run, candidate = self.captured()
        spec = self.study(run, candidate['sha256'])
        spec['cases'][0]['criteria'][0]['text'] = 'A different test of expression.'
        with self.assertRaisesRegex(ValueError, 'criterion'):
            ev.build(self.root, self.save_study(spec))

    def test_nonfinite_and_boolean_metrics_refused(self):
        (self.root / 'meter.log').write_text('Synthetic meter evidence.')
        for value in [True, -1, 'unknown']:
            (self.root / 'measure.json').write_bytes(c.encoded({'values': {'elapsed_seconds': value, 'total_tokens': None, 'tool_calls': None},
                'basis': 'Synthetic input validation.', 'evidence_path': 'meter.log'}))
            with self.assertRaises(ValueError):
                ev._measurements(self.root, 'measure.json')
        self.assertIsNone(ev._stats([3])['sample_stddev'])
        self.assertIsNone(ev._stats([])['mean'])
        self.assertEqual(ev._stats([1, 3])['mean'], 2)

    def test_blind_cards_do_not_contain_condition_labels_or_operator_key(self):
        run, candidate = self.reviewed()
        spec = self.study(run, candidate['sha256'])
        result = ev.export(self.root, self.save_study(spec), 'evaluations/blind', blind=True)
        folder = Path(result['output'])
        self.assertNotIn('condition-secret-alpha', (folder / 'index.html').read_text())
        self.assertFalse(Path(result['operator_key']).is_relative_to(folder))
        self.assertIn('condition-secret-alpha', Path(result['operator_key']).read_text())
        self.assertFalse((folder / 'evidence.json').exists())

    def test_evaluation_export_does_not_invoke_or_mutate_production(self):
        run, candidate = self.reviewed()
        before = w.load_run(self.root, run)[3]
        result = ev.export(self.root, self.save_study(self.study(run, candidate['sha256'])), 'evaluations/summary')
        self.assertEqual(result['models_called'], 0)
        self.assertEqual(before, w.load_run(self.root, run)[3])


if __name__ == '__main__':
    import io
    import json
    buffer = io.StringIO()
    result = unittest.TextTestRunner(stream=buffer, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(__import__('sys').modules[__name__]))
    errors = [str(test) + ': ' + detail for test, detail in result.failures + result.errors]
    print(json.dumps({'ok': result.wasSuccessful(), 'checks': result.testsRun,
                      'passed': result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped),
                      'skipped': len(result.skipped), 'errors': errors,
                      'scope': 'constructed correctness tests; no model-quality claim',
                      'details': buffer.getvalue()}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result.wasSuccessful() else 1)
