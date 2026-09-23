#!/usr/bin/env python3
"""Exercise craft lookup, authored applications and unassessed review transfer."""
from __future__ import annotations

import copy
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import execution_contract as c
import craft_consultation as tool
import production_workflow as workflow
import production_workflow_smoke_test as fixtures
import production_inputs
import production_spec
from pack_manager import default_settings, save_state
from catalog_retrieval import runtime
from catalog_retrieval.runtime import Entry

ROOT = Path(__file__).resolve().parents[1]


class ConsultationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ProductionTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.task = self.fixture.spec
        # The runtime sees commons alone, whatever personal packs sit beside it.
        self.settings = replace(default_settings(state_file=self.root / 'pack-state.json',
            cache_dir=self.root / 'cache', managed_root=self.root / 'managed'),
            roots=((ROOT / 'packs' / 'commons').resolve(),))
        save_state(self.settings.state_file, c.load(ROOT / 'config/default-pack-state.json'))
        self.context = runtime.using_pack_runtime(self.settings)
        self.context.__enter__(); self.addCleanup(self.context.__exit__, None, None, None)
        self.spec = c.load(ROOT / 'templates/production-spec-template.json')
        self.spec['source_brief'] = 'Synthetic local scene.'
        self.spec['lighting']['key_light'] = 'One window source with a readable shadow side.'
        self.write('spec.json', self.spec)
        self.report = tool.consult([{'request_id': 'light', 'canonical_query': 'window light interior', 'focus': 'detail'}],
                                   ['lighting-cool-window'], settings=self.settings)
        self.write('consult.json', self.report)
        self.choices = {'source_id': 'window-study', 'reason': 'Use the scoped lighting relationship.',
            'uses': [{'record_id': 'lighting-cool-window', 'borrowed': 'A single side light and retained shadow detail.',
                      'preserved': 'Keep the single source and shadow-side readability.', 'changed': 'Apply to the declared local subject.',
                      'targets': ['/lighting/key_light'], 'review_criteria': ['lamp'],
                      'review_question': 'Does the actual output keep readable detail on the shadow side?'}], 'not_used': []}
        self.write('decisions.json', self.choices)

    def write(self, path, value):
        return self.fixture.write(path, value)

    def apply(self):
        return tool.apply(self.root, 'task.json', 'consult.json', 'decisions.json', 'spec.json', 'applied', settings=self.settings)

    def test_scope_reports_only_current_records(self):
        self.assertEqual(self.report['scope']['searchable']['total_records'], 105)
        self.assertEqual(len(self.report['scope']['packs']), 1)
        self.assertFalse(self.report['external_effect'])
        self.assertIn('coverage', self.report['scope'])

    def test_disabled_pack_is_visible_without_activation(self):
        state = c.load(self.settings.state_file); state['enabled_packs'] = []
        save_state(self.settings.state_file, state)
        result = tool.consult([], [], settings=self.settings)
        self.assertEqual(result['scope']['searchable']['total_records'], 0)
        self.assertEqual(len(result['scope']['disabled_discovered_packs']), 1)
        self.assertEqual(c.load(self.settings.state_file)['enabled_packs'], [])

    def test_scene_and_recipe_are_distinct_layers(self):
        result = tool.consult([{'request_id': 'scene', 'canonical_query': 'portrait', 'focus': 'scene'}], [], settings=self.settings)
        self.assertEqual([row['request_id'] for row in result['search']['results']], ['scene:scenes', 'scene:recipes'])
        self.assertEqual(result['inspected'], [])
        self.assertEqual(result['application_template']['uses'], [])

    def test_all_questions_share_one_catalog_request(self):
        with patch.object(runtime, 'begin_catalog_request', wraps=runtime.begin_catalog_request) as begin:
            result = tool.consult([{'request_id': 'a', 'canonical_query': 'window', 'focus': 'scene'},
                                   {'request_id': 'b', 'canonical_query': 'shadow detail', 'focus': 'repair'}], [], settings=self.settings)
        self.assertEqual(begin.call_count, 1)
        self.assertEqual(result['search']['request_count'], 3)

    def test_empty_result_has_no_adoption(self):
        result = tool.consult([{'request_id': 'empty', 'canonical_query': 'synthetic nonmatching phrase qzxpv', 'focus': 'repair'}], [], settings=self.settings)
        self.assertEqual(result['search']['results'][0]['result']['results'], [])
        self.assertIn('empty layer', result['empty_result'])
        self.assertEqual(result['inspected'], [])

    def test_complete_records_preserve_invariants(self):
        item = self.report['inspected'][0]
        self.assertIn('invariants', item['record'])
        self.assertEqual(item['record_sha256'], c.content_id(item['record']))
        self.assertIn('assets', item)

    def test_changed_runtime_does_not_reuse_previous_search(self):
        changed = copy.deepcopy(self.report); changed['scope']['runtime_fingerprint'] = '0' * 64
        with self.assertRaises(ValueError):
            tool.consult([], [], settings=self.settings, previous=changed)

    def test_prior_lookup_keeps_full_selected_records(self):
        result = tool.consult([], ['camera-close-eye-level'], settings=self.settings, previous=self.report)
        self.assertEqual({row['record_id'] for row in result['inspected']}, {'lighting-cool-window', 'camera-close-eye-level'})

    def test_application_changes_only_selected_ids_in_spec(self):
        before = (self.root / 'task.json').read_bytes()
        output = self.apply(); updated = c.load(self.root / output['production_spec'])
        expected = copy.deepcopy(self.spec); expected['selected_preset_ids'] = ['lighting-cool-window']
        self.assertEqual(updated, expected)
        self.assertEqual((self.root / 'task.json').read_bytes(), before)
        self.assertEqual(c.load(self.root / 'spec.json'), self.spec)
        task = c.load(self.root / output['task']); workflow.validate_task(task)
        self.assertTrue(any(source['role'] == tool.ROLE for source in task['sources']))
        self.assertFalse(output['execution_ready'])
        self.assertFalse((self.root / 'production').exists())

    def test_targets_are_actual_authored_values(self):
        output = self.apply(); record = c.load(self.root / output['application'])
        self.assertEqual(record['applications'][0]['target_values']['/lighting/key_light'], self.spec['lighting']['key_light'])
        self.assertEqual(record['applications'][0]['source']['record'], self.report['inspected'][0]['record'])

    def test_nonuse_preserves_existing_intent(self):
        self.choices['uses'] = []
        self.choices['not_used'] = [{'record_id': 'lighting-cool-window', 'reason': 'The declared direction uses another light.'}]
        self.write('decisions.json', self.choices)
        output = self.apply()
        self.assertEqual(c.load(self.root / output['production_spec']), self.spec)
        task = c.load(self.root / output['task'])
        self.assertEqual(task['sources'][-1]['disposition'], 'considered-not-used')

    def test_existing_selections_survive_a_local_application(self):
        self.spec['selected_preset_ids'] = ['camera-close-eye-level']; self.write('spec.json', self.spec)
        result = self.apply()
        self.assertEqual(result['selected_preset_ids'], ['camera-close-eye-level', 'lighting-cool-window'])
        self.assertEqual(result['preserved_selected_preset_ids'], ['camera-close-eye-level'])
        self.assertEqual(result['applied_record_ids'], ['lighting-cool-window'])

    def test_uninspected_selection_fails_before_publication(self):
        self.choices['uses'][0]['record_id'] = 'camera-close-eye-level'; self.write('decisions.json', self.choices)
        with self.assertRaises(ValueError): self.apply()
        self.assertFalse((self.root / 'applied').exists())

    def test_fabricated_record_is_rejected(self):
        self.report['inspected'][0]['record']['label'] = 'Another record'
        self.write('consult.json', self.report)
        with self.assertRaises(ValueError): self.apply()

    def test_unknown_criterion_and_target_are_rejected(self):
        for field, value in [('review_criteria', ['not-declared']), ('targets', ['/lighting/missing'])]:
            changed = copy.deepcopy(self.choices); changed['uses'][0][field] = value
            self.write('decisions.json', changed)
            with self.assertRaises(ValueError): self.apply()
        self.assertFalse((self.root / 'applied').exists())

    def test_judgments_remain_required(self):
        self.choices['uses'][0]['preserved'] = ''
        self.write('decisions.json', self.choices)
        with self.assertRaises(ValueError): self.apply()

    def test_application_keeps_prior_authority_unchanged(self):
        before = (self.root / self.task['authority']).read_bytes()
        self.apply()
        self.assertEqual((self.root / self.task['authority']).read_bytes(), before)

    def test_output_directory_is_not_overwritten(self):
        self.apply()
        before = (self.root / 'applied/preset-application.json').read_bytes()
        with self.assertRaises(FileExistsError): self.apply()
        self.assertEqual((self.root / 'applied/preset-application.json').read_bytes(), before)

    def test_source_change_during_publication_is_detected(self):
        original = production_inputs._publish
        def altered(*args, **kwargs):
            self.write('decisions.json', {**self.choices, 'reason': 'Changed concurrently.'})
            return original(*args, **kwargs)
        with patch.object(production_inputs, '_publish', side_effect=altered):
            with self.assertRaises(ValueError): self.apply()
        self.assertFalse((self.root / 'applied').exists())

    def test_review_question_reaches_actual_prepared_run(self):
        output = self.apply()
        run = workflow.prepare(self.root, output['task'])['run']
        import production_fixtures
        production_fixtures.handoff(self.root, run, 'synthetic reviewer', 'manual')
        self.write('result.txt', 'One lamp with readable shadow detail.')
        candidate = workflow.capture(self.root, run, 'result.txt', 'Synthetic local text, not a model image.')
        draft = workflow.draft_review(self.root, run, candidate['sha256'])
        check = next(row for row in draft['checks'] if row['criterion'] == 'lamp')
        self.assertIn('shadow side', check['reason'])
        self.assertEqual(check['verdict'], 'not-assessed')
        self.assertEqual(check['observation_indices'], [])
        self.assertEqual(draft['conclusion'], '')

    def test_linked_asset_evidence_cannot_be_replaced(self):
        self.report['inspected'][0]['assets'] = {'fabricated': 'identity permission'}
        self.write('consult.json', self.report)
        with self.assertRaises(ValueError): self.apply()
        self.assertFalse((self.root / 'applied').exists())

    def test_two_techniques_retain_separate_scopes_and_questions(self):
        report = tool.consult([], ['camera-close-eye-level'], settings=self.settings, previous=self.report)
        self.write('consult.json', report)
        camera = copy.deepcopy(self.choices['uses'][0])
        camera.update(record_id='camera-close-eye-level', borrowed='Eye-level portrait framing.',
                      preserved='The declared identity proportions.', changed='Apply to this local frame.',
                      targets=['/camera/pitch_degrees'], review_question='Does the observed framing preserve the intended viewpoint?')
        self.choices['uses'].append(camera); self.write('decisions.json', self.choices)
        result = self.apply(); app = c.load(self.root / result['application'])
        self.assertEqual(len(app['applications']), 2)
        self.assertEqual(set(app['applications'][1]['target_values']), {'/camera/pitch_degrees'})
        self.assertEqual(len(tool.review_questions(self.root, c.load(self.root / result['task']))['lamp']), 2)

    def test_review_reads_the_prepared_application_snapshot(self):
        result = self.apply(); run = workflow.prepare(self.root, result['task'])['run']
        import production_fixtures
        production_fixtures.handoff(self.root, run, 'synthetic reviewer', 'manual')
        self.write('result.txt', 'One lamp with readable shadow detail.')
        candidate = workflow.capture(self.root, run, 'result.txt', 'Synthetic local text.')
        original = workflow.assert_current
        def changed_after_check(*args, **kwargs):
            snapshot = original(*args, **kwargs)
            app = c.load(self.root / result['application'])
            app['applications'][0]['review_question'] = 'Changed after freshness check.'
            self.write(result['application'], app)
            return snapshot
        with patch.object(workflow, 'assert_current', side_effect=changed_after_check):
            review = workflow.draft_review(self.root, run, candidate['sha256'])
        self.assertIn('shadow side', review['checks'][0]['reason'])
        self.assertNotIn('Changed after', review['checks'][0]['reason'])
        with self.assertRaises(ValueError): workflow.draft_review(self.root, run, candidate['sha256'])

    def test_recipe_dependencies_are_opened_not_selected(self):
        recipe = {'id': 'synthetic-recipe', 'base_scene_id': 'synthetic-scene', 'render_profile_id': 'synthetic-profile'}
        records = [('recipe', recipe), ('scene', {'id': 'synthetic-scene'}), ('profile', {'id': 'synthetic-profile'})]
        self.write('records.json', {'records': [row for _, row in records]})
        entries = [Entry(kind, None, record, 'synthetic-owner', self.root, 'records.json') for kind, record in records]
        with patch.object(tool, 'asset_lookup', return_value={'assets': []}):
            opened = tool.open_records(entries, ['synthetic-recipe'])
        self.assertEqual(len(opened), 3)
        self.assertEqual([row['record_id'] for row in opened if row['requested']], ['synthetic-recipe'])
        self.assertEqual(len(opened[0]['dependencies']), 2)

    def test_history_retains_searches_without_nested_full_reports(self):
        second = tool.consult([], ['camera-close-eye-level'], settings=self.settings, previous=self.report)
        third = tool.consult([], [], settings=self.settings, previous=second)
        self.assertEqual(len(third['history']), 2)
        self.assertEqual(set(third['history'][0]), {'questions', 'search'})
        self.assertEqual(len(third['inspected']), 2)

    def test_selection_list_cannot_stand_in_for_an_authored_target(self):
        self.choices['uses'][0]['targets'] = ['/selected_preset_ids']
        self.write('decisions.json', self.choices)
        with self.assertRaises(ValueError): self.apply()

    def test_nonuse_cannot_erase_prior_selection(self):
        self.spec['selected_preset_ids'] = ['lighting-cool-window']; self.write('spec.json', self.spec)
        self.choices['uses'] = []
        self.choices['not_used'] = [{'record_id': 'lighting-cool-window', 'reason': 'Different direction.'}]
        self.write('decisions.json', self.choices)
        with self.assertRaises(ValueError): self.apply()

    def test_workflow_consultation_stays_on_its_task_snapshot(self):
        self.report['task'] = {'path': 'task.json', 'sha256': '0' * 64}
        self.write('consult.json', self.report)
        with self.assertRaises(ValueError): self.apply()

    def test_unknown_record_and_malformed_question_fail(self):
        with self.assertRaises(ValueError): tool.consult([], ['not-a-record'], settings=self.settings)
        with self.assertRaises(ValueError): tool.consult([{'canonical_query': 'light', 'focus': 'detail'}], [], settings=self.settings)

    def test_public_cli_example_rebuilds_exactly(self):
        result = subprocess.run([sys.executable, str(ROOT / 'examples/craft-consultation/build_example.py'), '--check'],
                                cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report['full_record_preserved'])
        self.assertFalse(report['execution_ready'])

    def test_input_inspection_offers_contextual_lookup(self):
        result = production_inputs.inspect_inputs(self.root, 'task.json')
        action = result['craft_lookup']['next_actions'][0]
        self.assertEqual(action['args']['task'], 'task.json')
        self.assertFalse(action['external_effect'])


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
