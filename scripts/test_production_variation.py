"""Input-derived variants and repeats of the current prepared-run contract."""
from __future__ import annotations
import copy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import execution_contract as c
import production_case_fixtures as fixtures
import production_variation as variation
import production_workflow as workflow
import production_execution as execution
import production_store as store
from production_diagnostics import ProductionError, CompilationError


class VariationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        case = fixtures.create(base / 'studio', base / 'runtime')
        self.root = case['root']
        self.parent = workflow.prepare(self.root, 'task.json')
        self.run = self.parent['run']

    def change(self, values):
        fixtures.write(self.root / 'changes.json', {'changes': values, 'reason': 'Explicit synthetic input variation.'})
        return variation.derive(self.root, self.run, changes_file='changes.json', prepare=True)

    def identity_task(self):
        task = c.load(self.root / 'task.json')
        task['sources'][0]['identity'] = {'subject_ids': ['robot'], 'selectors': ['']}
        task['criteria'][0].update(evidence='image', identity_review=['robot'], identity_bindings=[{
            'source': 'brief', 'subject_ids': ['robot'], 'selectors': [''], 'treatment': 'preserve',
            'reason': 'Retain the original synthetic definition.', 'variation': None,
            'carriers': [{'kind': 'text', 'surface': 'primary', 'selection': {'text': 'synthetic robot', 'occurrence': 1}}]}])
        return task

    def test_parameter_variant_needs_no_candidate_or_claim(self):
        child = self.change({'parameter:steps': 22})
        self.assertNotEqual(child['run'], self.run)
        self.assertNotEqual(child['input_sha256'], self.parent['input_sha256'])
        self.assertEqual(child['request_preview']['steps'], 22)
        self.assertEqual(store.event_rows(self.root, self.run), [])
        self.assertEqual(store.event_rows(self.root, child['run']), [])
        a = workflow.load_run(self.root, self.run)[1]
        b = workflow.load_run(self.root, child['run'])[1]
        self.assertEqual(a['runtime_snapshot']['sha256'], b['runtime_snapshot']['sha256'])
        self.assertEqual(b['parent']['kind'], 'variant')
        self.assertEqual(b['parent']['basis'], [])

    def test_repeat_retains_input_but_has_its_own_run(self):
        child = variation.derive(self.root, self.run, prepare=True)
        self.assertNotEqual(child['run'], self.run)
        self.assertEqual(child['input_sha256'], self.parent['input_sha256'])
        self.assertEqual(child['execution_plan']['request_sha256'], self.parent['execution_plan']['request_sha256'])
        self.assertEqual(store.event_rows(self.root, child['run']), [])

    def test_declared_input_without_a_pinned_snapshot_stops_derivation_and_names_its_continuation(self):
        import types
        loaded = workflow.read_run(self.root, self.run)
        path = loaded.prepared['task']['delivery']['path']
        self.assertEqual(variation._captured(loaded, path), (self.root / path).read_bytes())
        unpinned = types.SimpleNamespace(evidence=loaded.evidence, prepared={'run': self.run,
            'dependencies': [row for row in loaded.prepared['dependencies'] if row['path'] != path]})
        with self.assertRaises(ProductionError) as caught:
            variation._captured(unpinned, path)
        found = caught.exception.diagnostic.as_dict()
        self.assertEqual((found['code'], found['file'], found['run'], found['pinned']),
                         ('EVIDENCE_SNAPSHOT_MISSING', path, self.run, 0))
        self.assertIn('Prepare a new run', found['required_action'])

    def test_unknown_field_creates_no_run(self):
        with self.assertRaises(ProductionError) as caught:
            self.change({'arbitrary-internal-path': 'not permitted'})
        self.assertEqual(caught.exception.diagnostic.code, 'CHANGES_UNKNOWN_FIELD')
        self.assertEqual(len(store.runs(self.root)), 1)

    def test_wrong_parameter_type_creates_no_run(self):
        with self.assertRaises(ProductionError) as caught:
            self.change({'parameter:steps': 'twenty'})
        self.assertEqual(caught.exception.diagnostic.code, 'CHANGES_TYPE_INVALID')
        self.assertEqual(len(store.runs(self.root)), 1)

    def test_no_op_creates_no_run(self):
        with self.assertRaises(ProductionError) as caught:
            self.change({'parameter:steps': 20})
        self.assertEqual(caught.exception.diagnostic.code, 'CHANGES_NO_OP')
        self.assertEqual(len(store.runs(self.root)), 1)

    def test_prompt_change_requires_real_retrieval_reassessment(self):
        with self.assertRaises(CompilationError) as caught:
            self.change({'prompt': fixtures.PROMPT + ' A small blue square sits on the ground.'})
        self.assertEqual(len(store.runs(self.root)), 1)
        self.assertIn('retrieval', str(caught.exception.report).lower())

    def test_prompt_change_with_explicit_reassessment(self):
        from prompt_retrieval import settle_retrieval_record
        prompt = fixtures.PROMPT + ' The same robot remains alone.'
        record = c.load(self.root / 'retrieval.json')
        # Authored by this test fixture; the runtime never creates this judgment.
        record = settle_retrieval_record(record, prompt=prompt, plot=c.load(self.root / 'plot.json'))
        fixtures.write(self.root / 'reassessed-retrieval.json', record)
        child = self.change({'prompt': prompt, 'retrieval-record': {'path': 'reassessed-retrieval.json'}})
        self.assertEqual(child['request_preview']['prompt'], prompt)

    def test_declared_task_fields_allow_reassessment_without_an_image(self):
        fields = self.parent['execution_plan']['mutable_fields']
        self.assertTrue({'direction','criteria','source-materials','route-reading',
                         'scene-materials','world-views','moment-views','features',
                         'state-lineage','state-snapshot'} <= set(fields))
        task = copy.deepcopy(workflow.load_run(self.root, self.run)[1]['task'])
        task['direction']['decisions'][0]['reason'] = 'An explicitly reassessed synthetic direction reason.'
        child = self.change({'direction': task['direction']})
        self.assertEqual(workflow.load_run(self.root, child['run'])[1]['task']['direction'], task['direction'])
        self.assertFalse(child['authorization_inherited'])

    def test_saved_field_schemas_validate_nested_identity_and_recording_values(self):
        from state_protocol import validate_against_schema
        task = self.identity_task()
        fields = workflow.read_run(self.root, self.run).artifacts['execution-plan.json']['mutable_fields']
        for field, name in [('criteria', 'criteria'), ('source-materials', 'sources'), ('recording', 'recording')]:
            with self.subTest(field=field):
                self.assertEqual(validate_against_schema(task[name], fields[field]['schema']), [])

    def test_cli_reassesses_identity_fields_from_retained_plan_without_changing_parent(self):
        import production_compiler as compiler
        task = self.identity_task()
        fixtures.write(self.root / 'identity-task.json', task)
        schema = c.load(Path(__file__).resolve().parents[1] / 'schemas/authoring/production-task.schema.json')
        # A retained field projection may omit its document context. The new
        # authored values still follow the current complete task contract.
        with patch.object(compiler, 'task_field_schema', side_effect=lambda name: copy.deepcopy(schema['properties'][name])):
            parent = workflow.prepare(self.root, 'identity-task.json')
        before = workflow.load_run(self.root, parent['run'])[1]
        plan_path = workflow.run_dir(self.root, parent['run']) / 'execution-plan.json'
        plan_bytes = plan_path.read_bytes()
        for field, name, changed_key in [('criteria', 'criteria', 'text'), ('source-materials', 'sources', 'reason')]:
            with self.subTest(field=field):
                value = copy.deepcopy(task[name])
                value[0][changed_key] += ' The synthetic wording is explicitly reassessed.'
                fixtures.write(self.root / 'changes.json', {'changes': {field: value}, 'reason': 'Synthetic identity reassessment.'})
                output = io.StringIO()
                argv = ['production_workflow.py', 'variant', '--root', str(self.root), '--from', parent['run'],
                        '--changes-file', 'changes.json', '--prepare']
                with patch.object(sys, 'argv', argv), redirect_stdout(output):
                    exit_code = workflow.main()
                self.assertEqual(exit_code, 0, output.getvalue())
                child = json.loads(output.getvalue())
                prepared = workflow.load_run(self.root, child['run'])[1]
                self.assertEqual(prepared['task'][name], value)
                self.assertEqual(prepared['parent']['run'], parent['run'])
                self.assertEqual(store.event_rows(self.root, child['run']), [])
                self.assertFalse(child['authorization_inherited'])
        self.assertEqual(workflow.load_run(self.root, parent['run'])[1], before)
        self.assertEqual(plan_path.read_bytes(), plan_bytes)
        self.assertEqual(c.load(self.root / 'identity-task.json'), task)

    def test_invalid_nested_identity_values_report_field_errors_without_a_run(self):
        task = self.identity_task()
        criteria = copy.deepcopy(task['criteria'])
        criteria[0]['identity_bindings'][0]['subject_ids'] = [7]
        sources = copy.deepcopy(task['sources'])
        sources[0]['identity']['selectors'] = ['/invalid~2escape']
        conditional = copy.deepcopy(task['criteria'])
        conditional[0]['identity_bindings'][0]['treatment'] = 'authorized-variation'
        for field, value, fragment in [('criteria', criteria, 'subject_ids[0]'),
                                      ('source-materials', sources, 'selectors[0]'),
                                      ('criteria', conditional, '.variation')]:
            with self.subTest(field=field, invalid=fragment):
                with self.assertRaises(ProductionError) as caught:
                    self.change({field: value})
                diagnostic = caught.exception.diagnostic
                self.assertEqual((diagnostic.code, diagnostic.pointer), ('CHANGES_TYPE_INVALID', '$.changes.' + field))
                self.assertIn(fragment, diagnostic.message)
                self.assertIn('expected', diagnostic.required_action)
        self.assertEqual(len(store.runs(self.root)), 1)

    def test_replaced_named_source_is_not_left_pointing_at_the_old_file(self):
        task = c.load(self.root/'task.json')
        task['sources'].append({'id':'intent-source','path':'creative-intent.json',
            'role':'intent','disposition':'applied','locator':'whole',
            'reason':'Synthetic authored intention source.'})
        fixtures.write(self.root/'source-task.json', task)
        self.run = workflow.prepare(self.root, 'source-task.json')['run']
        fixtures.write(self.root/'new-intent.json', {'image_promise':'Reassessed synthetic protocol demonstration.'})
        (self.root/'creative-intent.json').unlink()
        child = self.change({'creative-intent':{'path':'new-intent.json'}})
        prepared = workflow.load_run(self.root, child['run'])[1]
        self.assertEqual(next(x for x in prepared['task']['sources'] if x['id']=='intent-source')['path'], 'new-intent.json')
        self.assertNotIn('creative-intent.json', {d['path'] for d in prepared['dependencies'] if d['space']=='studio'})

    def test_repeat_mismatch_does_not_publish_a_run(self):
        import production_compiler as compiler
        original = compiler.compile_task
        def changed(*args, **kwargs):
            result = original(*args, **kwargs)
            result.consumer['instructions'] = 'A different synthetic delivery.'
            return result
        with patch.object(compiler, 'compile_task', side_effect=changed):
            with self.assertRaisesRegex(ProductionError, 'REPEAT_INPUT_MISMATCH'):
                variation.derive(self.root, self.run, prepare=True)
        self.assertEqual(len(store.runs(self.root)), 1)

    def test_parent_decisions_cannot_authorize_repeat(self):
        from test_production_execution import decisions
        path = decisions(self.root, self.run)
        child = variation.derive(self.root, self.run, prepare=True)
        with self.assertRaises(ProductionError) as caught:
            execution.execute(self.root, child['run'], decisions_file=path)
        self.assertEqual(caught.exception.diagnostic.code, 'AUTHORIZATION_MISMATCH')
        self.assertEqual(store.event_rows(self.root, child['run']), [])

    def test_missing_media_path_creates_no_run(self):
        with self.assertRaises(ProductionError) as caught:
            self.change({'references': {'path': 'missing-reference.json'}})
        diagnostic = caught.exception.diagnostic
        self.assertEqual((diagnostic.code, diagnostic.pointer, diagnostic.file),
                         ('CHANGES_PATH_INVALID', '$.changes.references.path', 'missing-reference.json'))
        self.assertEqual(len(store.runs(self.root)), 1)

    def test_every_invalid_field_is_reported_at_once(self):
        with self.assertRaises(ProductionError) as caught:
            self.change({'parameter:steps': 'twenty', 'arbitrary-internal-path': 1})
        rows = caught.exception.diagnostic.details['diagnostics']
        # The fixture writes keys in sorted order; problems follow the file order.
        self.assertEqual([(row['code'], row['pointer']) for row in rows],
                         [('CHANGES_UNKNOWN_FIELD', '$.changes.arbitrary-internal-path'),
                          ('CHANGES_TYPE_INVALID', '$.changes.parameter:steps')])
        self.assertEqual(caught.exception.diagnostic.code, 'CHANGES_UNKNOWN_FIELD')
        self.assertEqual(len(store.runs(self.root)), 1)

    def test_equal_json_in_the_same_directory_is_no_change(self):
        intent = c.load(self.root / 'creative-intent.json')
        (self.root / 'same-intent.json').write_text(json.dumps(intent, indent=4), encoding='utf-8')
        with self.assertRaises(ProductionError) as caught:
            self.change({'creative-intent': {'path': 'same-intent.json'}})
        self.assertEqual((caught.exception.diagnostic.code, caught.exception.diagnostic.pointer),
                         ('CHANGES_NO_OP', '$.changes.creative-intent'))

    def test_changes_from_stdin_equal_changes_from_a_file(self):
        value = {'changes': {'parameter:steps': 22}, 'reason': 'Explicit synthetic input variation.'}
        fixtures.write(self.root / 'changes.json', value)
        from_file = variation.derive(self.root, self.run, changes_file='changes.json')
        with patch('sys.stdin', io.TextIOWrapper(io.BytesIO(c.encoded(value)), encoding='utf-8')):
            from_stdin = variation.derive(self.root, self.run, changes_file='-')
        request = lambda result: {key: value for key, value in result['request_preview'].items() if key != 'request_id'}
        self.assertEqual(request(from_stdin), request(from_file))
        self.assertEqual(from_stdin['derivation']['changes'], from_file['derivation']['changes'])
        self.assertFalse(from_stdin['formal_run_created'])

    def test_target_fields_are_changed_by_retarget(self):
        specification = c.load(self.root / 'spec.json')
        specification['target_model'] = fixtures.ALTERNATE_MODEL_ID
        fixtures.write(self.root / 'other-spec.json', specification)
        for change, pointer in (({'model': fixtures.ALTERNATE_MODEL_ID}, '$.changes.model'),
                                ({'production-spec': {'path': 'other-spec.json'}}, '$.changes.production-spec.path')):
            with self.subTest(pointer=pointer):
                with self.assertRaises(ProductionError) as caught:
                    self.change(change)
                diagnostic = caught.exception.diagnostic
                self.assertEqual((diagnostic.code, diagnostic.pointer), ('TARGET_CHANGE_REQUIRED', pointer))
                self.assertIn('retarget --root', diagnostic.required_action)
        self.assertEqual(len(store.runs(self.root)), 1)

    def test_transport_mode_change_is_revalidated_before_any_run(self):
        with self.assertRaises(CompilationError) as caught:
            self.change({'execution-mode': 'reference-guided'})
        self.assertIn('reference', json.dumps(caught.exception.report['diagnostics']).lower())
        self.assertEqual(len(store.runs(self.root)), 1)
        with self.assertRaises(ProductionError) as caught:
            self.change({'references': None})
        self.assertEqual((caught.exception.diagnostic.code, caught.exception.diagnostic.pointer),
                         ('CHANGES_NO_OP', '$.changes.references'))

    def test_observed_candidate_and_its_review_are_the_recorded_basis(self):
        from test_production_execution import decisions
        result = execution.execute(self.root, self.run, decisions_file=decisions(self.root, self.run))
        candidate = result['runs'][0]['candidates'][0]
        review = workflow.draft_review(self.root, self.run, candidate)
        review.update(reviewer='Synthetic fixture reviewer - not user approval',
            observations=[{'evidence': 'candidate', 'locator': {'kind': 'whole'},
                'observation': 'The local fixture is a decoded 32 by 32 PNG.',
                'interpretation': 'Synthetic protocol assertion only; no model quality is assessed.',
                'limitations': ['Only the local fixture is examined.']}],
            checks=[{'criterion': 'output', 'verdict': 'pass', 'observation_indices': [0],
                     'reason': 'Explicit synthetic fixture decision.'}],
            conclusion='Synthetic fixture review.', unresolved=[])
        fixtures.write(self.root / 'review.json', review)
        recorded = workflow.review(self.root, self.run, 'review.json')
        fixtures.write(self.root / 'changes.json', {'changes': {'parameter:steps': 22}, 'reason': 'Answer the reviewed synthetic candidate.'})
        child = variation.derive(self.root, self.run, changes_file='changes.json', prepare=True, candidates=[candidate])
        prepared = workflow.load_run(self.root, child['run'])[1]
        self.assertEqual(prepared['parent']['basis'], [{'candidate': candidate, 'review': recorded['sha256']}])

    def test_unknown_candidate_creates_no_input(self):
        fixtures.write(self.root / 'changes.json', {'changes': {'parameter:steps': 22}, 'reason': 'Synthetic change.'})
        with self.assertRaises(ProductionError) as caught:
            variation.derive(self.root, self.run, changes_file='changes.json', prepare=True, candidates=['f' * 64])
        self.assertEqual(caught.exception.diagnostic.code, 'CANDIDATE_NOT_FOUND')
        self.assertFalse((self.root / 'production' / 'inputs').exists())
        self.assertEqual(len(store.runs(self.root)), 1)

    def test_derived_inputs_are_published_inside_the_new_run(self):
        child = self.change({'parameter:steps': 22})
        prepared = workflow.load_run(self.root, child['run'])[1]
        prefix = f"production/runs/{child['run']}/inputs/"
        self.assertTrue(prepared['task_path'].startswith(prefix))
        owned = {d['path']: d['space'] for d in prepared['dependencies'] if d['path'].startswith(prefix)}
        self.assertEqual(owned, {prefix + 'task.json': 'task-source', prefix + 'parameters.json': 'task-source'})
        self.assertEqual(c.load(self.root / prefix / 'parameters.json')['steps'], 22)
        self.assertEqual(c.load(self.root / prefix / 'requested-changes.json')['changes'], {'parameter:steps': 22})
        workflow.assert_current(self.root, child['run'])
        repeated = variation.derive(self.root, child['run'], prepare=True)
        self.assertEqual(repeated['input_sha256'], child['input_sha256'])
        self.assertFalse((self.root / 'production' / 'inputs').exists())

    def test_unprepared_and_failed_derivations_leave_no_inputs(self):
        fixtures.write(self.root / 'changes.json', {'changes': {'parameter:steps': 22}, 'reason': 'Synthetic check only.'})
        checked = variation.derive(self.root, self.run, changes_file='changes.json')
        self.assertIsNone(checked['run']);self.assertIsNone(checked['execution_plan']['run'])
        with self.assertRaises(CompilationError):
            self.change({'prompt': fixtures.PROMPT + ' A small blue square sits on the ground.'})
        self.assertFalse((self.root / 'production' / 'inputs').exists())
        self.assertEqual(len(store.runs(self.root)), 1)
        staged = [path for path in (self.root / 'production' / 'staging').iterdir() if (path / 'failure.json').is_file()]
        self.assertEqual(len(staged), 1)
        self.assertTrue((staged[0] / 'inputs' / 'prompt.txt').is_file())

    def test_a_run_without_references_gains_a_prepared_reference_set(self):
        from prepare_generation_references import prepare_references
        from transport_synthetic import _png
        c.atomic(self.root / 'variants/palette.png', _png(32, 32, b'\x50\x78\xa0'))
        references = prepare_references([{'role': 'palette', 'source': {'kind': 'supplied-file', 'reference_id': 'synthetic-palette',
            'resolved_path': str(self.root / 'variants/palette.png')}}], model=fixtures.MODEL_ID,
            output_dir=self.root / 'variants/reference-preparation')
        fixtures.write(self.root / 'variants/references.json', references)
        child = self.change({'references': {'path': 'variants/references.json'}, 'execution-mode': 'reference-guided'})
        self.assertEqual(len(child['request_preview']['inputs']['references']), 1)
        self.assertEqual(len(list(workflow.run_dir(self.root, child['run']).glob('package.*.references'))), 1)
        self.assertNotIn('inputs', self.parent['request_preview'])

    def test_review_retains_shared_carrier_scopes_after_original_sources_are_removed(self):
        import shutil
        import production_evidence as media
        from prepare_generation_references import prepare_references
        from test_production_execution import decisions
        from transport_synthetic import _png
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32">'
               '<path d="M0 0H32V32H0Z" fill="#5078a0"/></svg>').encode('utf-8')
        for name, mode, suffix, raw in (
            ('raster', 'multi-image', '.png', _png(32, 32, b'\x50\x78\xa0')),
            ('vector', 'multi-image', '.svg', svg),
            ('board', 'single-board', '.svg', svg),
        ):
            with self.subTest(name=name):
                folder = self.root / 'variants' / name
                source = folder / ('source' + suffix)
                c.atomic(source, raw)
                selections = [{'role': role,
                    'source': {'kind': 'supplied-file', 'reference_id': name + '-' + role,
                               'resolved_path': str(source)},
                    'subject_uses': [{'subject_id': 'robot', 'use': use, 'priority': 0}]}
                    for role, use in (('palette', 'local-color'), ('finish', 'surface-finish'))]
                references = prepare_references(selections, model=fixtures.MODEL_ID,
                    output_dir=folder / 'prepared', max_side=64, transport_mode=mode)
                fixtures.write(folder / 'references.json', references)
                child = self.change({'references': {'path': (folder / 'references.json').relative_to(self.root).as_posix()},
                                     'execution-mode': 'reference-guided'})
                run = child['run']
                result = execution.execute(self.root, run, decisions_file=decisions(self.root, run))
                self.assertTrue(result['execution_completed'], result.get('warnings'))
                candidate = result['runs'][0]['candidates'][0]
                directory, _, consumer, _ = workflow.load_run(self.root, run)
                self.assertNotIn('image_input', consumer)
                prepared = c.load(directory / 'package.json')['prepared_reference_set']
                shutil.rmtree(folder)
                draft = workflow.draft_review(self.root, run, candidate)
                evidence = workflow.review_basis(self.root, run, candidate)['evidence']
                self.assertEqual([item['id'] for item in evidence], ['delivered-reference:1', 'delivered-reference:2'])
                self.assertEqual(len({item['path'] for item in evidence}), 1)
                self.assertEqual(draft['observations'], [])
                self.assertTrue(all(check['verdict'] == 'not-assessed' for check in draft['checks']))
                assignments = [json.loads(item['relation'].split(': ', 1)[1]) for item in evidence]
                self.assertEqual([item['delivery']['attachment_number'] for item in assignments], [1, 1])
                self.assertEqual([item['delivery']['role'] for item in assignments], ['palette', 'finish'])
                for index, (item, assignment) in enumerate(zip(evidence, assignments, strict=True)):
                    selected = prepared['selected_references'][index]
                    self.assertEqual(assignment['source'], selected['source'])
                    self.assertEqual(assignment['derivation'], selected['transport']['derivation'])
                    self.assertEqual(assignment['delivery']['subject_uses'], selections[index]['subject_uses'])
                    self.assertEqual(assignment['delivery']['controls'], selected['authority']['controls'])
                    self.assertEqual(assignment['delivery']['must_not_control'], selected['authority']['must_not_control'])
                    pixels = c.read(c.local(self.root, item['path']))
                    measured = media.inspect(pixels, item['kind'])
                    self.assertEqual(measured['format'], 'PNG')
                    carrier = prepared['single_board'] if mode == 'single-board' else selected['transport']
                    self.assertEqual(c.digest(pixels), carrier['sha256'])
                    if suffix == '.svg':
                        self.assertEqual(assignment['source']['media_type'], 'image/svg+xml')
                        self.assertNotEqual(c.digest(pixels), assignment['source']['sha256'])
                    region = assignment['delivery']['region_pixels']
                    if mode == 'single-board':
                        self.assertEqual(region, prepared['single_board']['panels'][index]['box'])
                        locator = {'kind': 'image-region', 'x': region['x'] / measured['width'],
                            'y': region['y'] / measured['height'], 'width': region['width'] / measured['width'],
                            'height': region['height'] / measured['height']}
                    else:
                        self.assertIsNone(region)
                        locator = {'kind': 'whole'}
                    draft['observations'].append({'evidence': item['id'], 'locator': locator,
                        'observation': 'The saved synthetic reference carrier is a readable PNG.',
                        'interpretation': 'This observation concerns the declared ' + assignment['delivery']['role'] + ' use.',
                        'limitations': ['Candidate quality has not been assessed.']})
                draft.update(reviewer='Synthetic carrier reviewer',
                             conclusion='Prepared delivery remains inspectable within each source assignment.')
                fixtures.write(self.root / 'review.json', draft)
                recorded = workflow.review(self.root, run, 'review.json')
                self.assertEqual(recorded['data']['review']['evidence'], evidence)
                self.assertEqual(len(recorded['data']['review']['observations']), 2)

    def test_changed_unreplaced_source_uses_the_selected_parent_revision(self):
        parent = workflow.read_run(self.root, self.run)
        original = variation._captured(parent, 'creative-intent.json')
        fixtures.write(self.root / 'creative-intent.json', {'image_promise': 'A different current author intent.'})
        current = (self.root / 'creative-intent.json').read_bytes()
        child = self.change({'parameter:steps': 22})
        self.assertEqual(variation._captured(workflow.read_run(self.root, child['run']), 'creative-intent.json'), original)
        self.assertEqual((self.root / 'creative-intent.json').read_bytes(), current)
        self.assertEqual(workflow.read_run(self.root, self.run).prepared, parent.prepared)

    def test_repeat_uses_captured_sources_after_original_files_disappear(self):
        parent = workflow.read_run(self.root, self.run)
        removed = []
        for row in parent.prepared['dependencies']:
            if row['space'] == 'studio' and row['path'] != 'work/reads.jsonl':
                selected = self.root / row['path']
                if selected.is_file():
                    selected.unlink()
                    removed.append(selected)
        child = variation.derive(self.root, self.run, prepare=True)
        self.assertEqual(child['input_sha256'], self.parent['input_sha256'])
        self.assertEqual(child['execution_plan']['request_sha256'], self.parent['execution_plan']['request_sha256'])
        self.assertTrue(removed)
        self.assertTrue(all(not path.exists() for path in removed))
        self.assertEqual(store.event_rows(self.root, child['run']), [])

    def test_explicit_document_replacement_uses_current_bytes_at_the_same_path(self):
        original = c.load(self.root / 'creative-intent.json')
        current = {**original, 'image_promise': 'The authored synthetic character has a deliberately revised image promise.'}
        fixtures.write(self.root / 'creative-intent.json', current)
        child = self.change({'creative-intent': {'path': 'creative-intent.json'}})
        selected = c.decode(variation._captured(workflow.read_run(self.root, child['run']), 'creative-intent.json'))
        self.assertEqual(selected, current)
        self.assertEqual(c.decode(variation._captured(workflow.read_run(self.root, self.run), 'creative-intent.json')), original)

    def test_reopened_choices_explicitly_reselect_current_original_source(self):
        import production_inputs
        task = c.load(self.root / 'task.json')
        task['sources'].append({'id': 'auxiliary-source', 'path': 'source.bin', 'role': 'design',
            'disposition': 'applied', 'locator': 'whole file', 'reason': 'Explicit synthetic source selection.'})
        fixtures.write(self.root / 'source.bin', 'Original selected content.\n')
        original = (self.root / 'source.bin').read_bytes()
        fixtures.write(self.root / 'source-task.json', task)
        parent = workflow.prepare(self.root, 'source-task.json')
        fixtures.write(self.root / 'source.bin', 'Current content explicitly selected for this draft.\n')
        current = (self.root / 'source.bin').read_bytes()
        draft = production_inputs.draft_inputs(self.root, None, 'work/reselect-source', from_run=parent['run'])
        choices = draft['choices']
        row = next(row for row in choices['authoring']['task']['sources'] if row['id'] == 'auxiliary-source')
        restored_path = row['path']
        self.assertEqual((self.root / restored_path).read_bytes(), original)
        row['path'] = 'source.bin'
        fixtures.write(self.root / draft['choices_file'], choices)
        child = workflow.prepare(self.root, choices=draft['choices_file'])
        self.assertEqual(variation._captured(workflow.read_run(self.root, child['run']), 'source.bin'), current)
        self.assertEqual(variation._captured(workflow.read_run(self.root, parent['run']), 'source.bin'), original)
        self.assertEqual((self.root / restored_path).read_bytes(), original)
        self.assertEqual((self.root / 'source.bin').read_bytes(), current)

    def test_reopened_validation_retains_its_nested_graph_and_selects_current_replacements(self):
        import shutil
        import production_inputs
        import production_saved_inputs
        from input_evidence import InputEvidence
        parent = workflow.read_run(self.root, self.run)
        record = parent.artifacts['package.json']['request_validation']
        graph = {row['path']: parent.evidence.read(row['sha256'])
                 for row in parent.prepared['dependencies'] if row['path'].startswith('synthetic-validation/')}
        policy_path = record['execution_policy']['path']
        policy = c.decode(graph[policy_path])
        basis_path = policy['basis']['path']
        shutil.rmtree(self.root / 'synthetic-validation')
        draft = production_inputs.draft_inputs(self.root, None, 'work/retained-validation', from_run=self.run)
        self.assertEqual(draft['choices']['validation']['execution_policy'], '@run/' + self.run + '/' + policy_path)
        child = workflow.prepare(self.root, choices=draft['choices_file'])
        saved = workflow.read_run(self.root, child['run'])
        snapshots = saved.artifacts['package.json']['input_snapshots']
        self.assertEqual(InputEvidence._decode(snapshots['@run/' + self.run + '/' + basis_path]), graph[basis_path])
        self.assertFalse((self.root / 'synthetic-validation').exists())

        # Reopening this child consumes the graph it already owns. The named
        # source keeps its identity without rereading an ancestor publication.
        again = production_inputs.draft_inputs(self.root, None, 'work/validation-again', from_run=child['run'])
        with patch.object(production_saved_inputs, 'read_named', side_effect=AssertionError('ancestor source reread')):
            grandchild = workflow.prepare(self.root, choices=again['choices_file'])
        self.assertTrue(grandchild['formal_run_created'])
        self.assertEqual(again['choices']['validation'], draft['choices']['validation'])

        for path, raw in graph.items():
            c.atomic(self.root / path, raw)
        current_basis = b'Explicitly selected current synthetic interface evidence.\n'
        fixtures.write(self.root / basis_path, current_basis.decode('utf-8'))
        reference_path = policy['reference_instruction_transport']['contract']['path']
        reference = c.decode(graph[reference_path])
        reference['basis']['sha256'] = c.digest(current_basis)
        fixtures.write(self.root / reference_path, reference)
        policy['basis']['sha256'] = c.digest(current_basis)
        policy['reference_instruction_transport']['contract']['sha256'] = c.digest(c.encoded(reference))
        fixtures.write(self.root / policy_path, policy)
        choices = c.load(self.root / draft['choices_file'])
        choices['validation']['execution_policy'] = policy_path
        fixtures.write(self.root / draft['choices_file'], choices)
        changed = workflow.prepare(self.root, choices=draft['choices_file'])
        current = workflow.read_run(self.root, changed['run']).artifacts['package.json']
        self.assertEqual(current['request_validation']['execution_policy']['path'], policy_path)
        self.assertEqual(InputEvidence._decode(current['input_snapshots'][basis_path]), current_basis)
        self.assertEqual(parent.evidence.read(c.digest(graph[basis_path])), graph[basis_path])

    def test_retained_reference_graph_survives_removal_and_explicit_replacement_uses_current_media(self):
        import shutil
        from prepare_generation_references import prepare_references
        from transport_synthetic import _png
        folder = self.root / 'reference-revision'
        path = folder / 'source.png'
        old = _png(32, 32, b'\x50\x78\xa0')
        c.atomic(path, old)
        def reference_document(output):
            return prepare_references([{'role': 'palette', 'source': {'kind': 'supplied-file',
                'reference_id': 'synthetic-palette', 'resolved_path': str(path)}}],
                model=fixtures.MODEL_ID, output_dir=output)
        fixtures.write(folder / 'references.json', reference_document(folder / 'prepared'))
        parent = self.change({'references': {'path': 'reference-revision/references.json'},
                              'execution-mode': 'reference-guided'})
        parent_run = parent['run']
        parent_prepared = workflow.read_run(self.root, parent_run).prepared
        shutil.rmtree(folder)
        try:
            repeated = variation.derive(self.root, parent_run, prepare=True)
        except CompilationError as exc:
            self.fail(json.dumps(exc.report['diagnostics'], indent=2))
        self.assertEqual(repeated['input_sha256'], parent['input_sha256'])
        repeated_set = workflow.read_run(self.root, repeated['run']).artifacts['package.json']['prepared_reference_set']
        self.assertEqual(repeated_set['selected_references'][0]['source']['sha256'], c.digest(old))
        self.assertFalse(folder.exists())
        new = _png(32, 32, b'\xa0\x78\x50')
        c.atomic(path, new)
        fixtures.write(folder / 'references.json', reference_document(folder / 'new-prepared'))
        fixtures.write(self.root / 'changes.json', {'changes': {'references': {'path': 'reference-revision/references.json'}},
            'reason': 'Select the current source revision explicitly.'})
        changed = variation.derive(self.root, parent_run, changes_file='changes.json', prepare=True)
        changed_set = workflow.read_run(self.root, changed['run']).artifacts['package.json']['prepared_reference_set']
        self.assertEqual(changed_set['selected_references'][0]['source']['sha256'], c.digest(new))
        self.assertEqual(workflow.read_run(self.root, parent_run).prepared, parent_prepared)

    def test_changed_installation_is_a_notice_for_a_variant_and_a_repeat(self):
        import shutil
        installation = Path(self.temp.name) / 'installation'
        pinned = [source for source in workflow.load_run(self.root, self.run)[1]['dependencies'] if source['space'] == 'skill']
        for source in pinned:
            target = installation / source['path']
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(workflow.ROOT / source['path'], target)
        # A schema is pinned by content, and the implementation index names it without a digest.
        changed = next(source['path'] for source in pinned if source['path'].startswith('schemas/'))
        schema = installation / changed
        schema.write_bytes(schema.read_bytes() + b'\n')
        with patch.object(workflow, 'ROOT', installation):
            varied = self.change({'parameter:steps': 22})
            repeated = variation.derive(self.root, self.run, prepare=True)
        for result in (varied, repeated):
            [notice] = result['runtime_warnings']
            self.assertEqual((notice['code'], notice['severity'], notice['file']),
                             ('IMPLEMENTATION_CHANGED', 'warning', changed))
        self.assertEqual(len(store.runs(self.root)), 3)


class RetainedUpscaleTests(unittest.TestCase):
    def test_repeat_keeps_upscale_source_and_validation_after_original_removal(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = fixtures.create(base / 'studio', base / 'runtime', with_upscale=True)['root']
            parent = workflow.prepare(root, fixtures.upscale_task(root))
            loaded = workflow.read_run(root, parent['run'])
            removed = []
            for source in loaded.prepared['dependencies']:
                path = root / source['path']
                if source['space'] == 'studio' and path.is_file() and source['path'] != 'work/reads.jsonl':
                    path.unlink()
                    removed.append(path)
            child = variation.derive(root, parent['run'], prepare=True)
            self.assertEqual(child['input_sha256'], parent['input_sha256'])
            self.assertEqual(child['execution_plan']['request_sha256'], parent['execution_plan']['request_sha256'])
            self.assertTrue(all(not path.exists() for path in removed))
            self.assertEqual(store.event_rows(root, child['run']), [])


class HierarchicalParameterTests(unittest.TestCase):
    def test_nested_control_is_changed_without_a_literal_dotted_key(self):
        import pack_manager
        original=fixtures.create_pack
        def nested(path,**kwargs):
            result=original(path,**kwargs);document=c.load(path/'records/models.json')
            for model in document['records']:
                for profile in [model['execution_profile'],*[offering['execution_profile'] for offering in model['offerings']]]:
                    for mode in profile['modes'].values():
                        control=mode['controls'].pop('settings')
                        control['schema']={'type':'integer','minimum':1,'maximum':10}
                        mode['controls']['settings.guidance']=control
            fixtures.write(path/'records/models.json',document);pack_manager.write_lock(path)
            return result
        with tempfile.TemporaryDirectory() as temporary,patch.object(fixtures,'create_pack',side_effect=nested):
            base=Path(temporary);root=fixtures.create(base/'studio',base/'runtime')['root']
            params=c.load(root/'parameters.json');params['settings']={'guidance':2};fixtures.write(root/'parameters.json',params)
            parent=workflow.prepare(root,'task.json')
            fixtures.write(root/'changes.json',{'changes':{'parameter:settings.guidance':3},'reason':'Synthetic nested control change.'})
            child=variation.derive(root,parent['run'],changes_file='changes.json',prepare=True)
            self.assertEqual(child['request_preview']['settings']['guidance'],3)
            self.assertNotIn('settings.guidance',child['request_preview'])
            self.assertEqual(parent['request_preview']['settings']['guidance'],2)
            self.assertEqual(store.event_rows(root,child['run']),[])


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
