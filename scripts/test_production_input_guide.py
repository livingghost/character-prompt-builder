"""Public field guidance reaches actual target and external request owners."""
from __future__ import annotations

import contextlib
import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import execution_contract as c
import production_document_contracts as contracts
import production_external_inputs as external
import production_input_guide as guide
import production_fixtures as fixtures
from test_production_report_view import resolved_action


class InputGuideTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.enterContext(fixtures.scratch_home(self.root / 'home'))
        self.choices = {'target': None, 'external': None,
                        'authoring': {'task': {'route': 'generation', 'execution': 'external'}}}
        self.path = 'choices.json'
        self.save()

    def save(self):
        (self.root / self.path).write_bytes(c.encoded(self.choices))

    def field(self, name):
        return guide.explain(self.root, self.path, field=name)['fields'][0]

    def test_external_parent_returns_the_runtime_envelope_and_navigable_child_contracts(self):
        result = self.field('external')
        self.assertEqual(result['template'], external.template())
        self.assertEqual(set(result['contract']['required_keys']), external.FIELDS)
        self.assertEqual(result['contract']['template_source'], 'scripts/production_external_inputs.py:template')
        self.assertEqual(result['selected_representation'], 'unselected')
        for child in result['child_contracts'].values():
            self.assertEqual(child['explain_action']['argv'][-2:], ['--field', child['field']])
            self.assertEqual(self.field(child['field'])['field'], child['field'])
        selected = {'image_input': 'saved-plan.json'}
        self.choices['external'] = selected
        self.save()
        self.assertEqual(self.field('external')['selected_representation'], 'existing-plan')
        self.assertEqual(self.field('external.image_input')['source'], {'file': 'saved-plan.json'})
        self.assertEqual(c.load(self.root / self.path)['external'], selected)

    def test_target_guidance_does_not_infer_an_external_kind_or_prompt_form(self):
        unselected = self.field('target.model')
        self.assertIsNone(unselected['selected_kind'])
        self.assertNotIn('template', unselected)
        self.assertEqual({row['kind'] for row in unselected['target_branches']},
                         {'catalog', 'acquired', 'external'})
        self.choices['target'] = {'kind': 'catalog', 'model': 'synthetic-model', 'service': 'synthetic'}
        self.save()
        selected = self.field('target.model')
        self.assertEqual(selected['declaration']['type'], ['string', 'null'])
        self.assertNotIn('template', selected)
        self.choices['target'] = {'kind': 'external', 'model': None}
        self.save()
        model = self.field('target.model')
        self.assertEqual(set(model['template']), {'requested', 'target', 'evidence'})
        self.assertEqual(set(model['template']['target']), {'service', 'model_identifier', 'operation'})
        self.assertEqual(model['template']['evidence'], {'path': None, 'locator': None})
        self.assertNotIn('prompt_input', model['template'])
        self.assertNotIn('catalog_status', model['template'])
        self.assertIn('optional', self.field('target.model.prompt_input')['required_action'])

    def test_nested_task_direction_field_reaches_its_choices_shape_and_contract(self):
        self.choices['authoring']['task']['direction'] = {
            'purpose': 'Retain the declared purpose.',
            'intended_effect': None,
        }
        self.save()
        before = (self.root / self.path).read_bytes()

        command = guide.action(self.root, self.path, field='authoring.task.direction')['argv']
        response = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(response.returncode, 0, response.stdout + response.stderr)
        report = json.loads(response.stdout)
        [row] = report['fields']
        self.assertEqual(row['field'], 'authoring.task.direction')
        self.assertEqual(row['choices_pointer'], '/authoring/task/direction')
        self.assertEqual(row['schema_pointer'], '/$defs/draftDirection')
        self.assertEqual(row['choices_schema_pointer'],
                         '/properties/authoring/properties/task/properties/direction')
        self.assertEqual(row['value_state'], 'supplied')
        self.assertEqual(row['declaration']['permitted_keys'], [
            'action_slice', 'basis', 'decisions', 'image_format', 'intended_effect', 'limitations',
            'purpose', 'source_allowances'])
        self.assertEqual(row['declaration']['fields']['purpose']['type'], ['string', 'null'])
        self.assertEqual(row['declaration']['fields']['intended_effect']['type'], ['string', 'null'])
        self.assertEqual(row['declaration']['fields']['basis']['type'], 'array')
        self.assertNotIn('required', row['declaration'])
        self.assertEqual(row['contract']['name'], 'production_direction')
        self.assertEqual(row['contract']['document_path'],
                         'references/runtime/production-direction.md#record-the-production-direction')
        self.assertEqual(row['contract']['schema'], 'schemas/authoring/production-direction.schema.json')
        self.assertIn('remaining_checks', row['contract'])
        self.assertEqual(row['contract_action']['argv'][-2:], ['explain', 'production_direction'])
        self.assertIn('actual authority remain separate', row['required_action'])
        self.assertFalse(report['external_effect'])

        parent = self.field('authoring.task')
        direction = parent['child_contracts']['direction']
        self.assertEqual(direction['explain_action']['argv'][-2:],
                         ['--field', 'authoring.task.direction'])
        self.assertEqual(direction['schema_action']['argv'][-2:], ['explain', 'production_direction'])
        self.assertEqual((self.root / self.path).read_bytes(), before)

    def test_editable_request_distinguishes_derived_fields_and_reaches_exact_schema_fragments(self):
        self.choices['target'] = {'kind': 'external', 'model': None}
        self.save()
        plan = self.field('external.image_input')
        self.assertNotIn('model', plan['template'])
        self.assertNotIn('model', plan['declaration']['required'])
        self.assertIn('model', plan['published_declaration']['required'])
        request = self.field('external.image_input.external_request')
        self.assertEqual(set(request['template']),
                         {'prompt_field', 'model_field', 'operation_field', 'count_field', 'count'})
        self.assertNotIn('file', request['declaration']['permitted_keys'])
        self.assertNotIn('reference_fields', request['declaration']['permitted_keys'])
        self.assertEqual(request['declaration']['fields']['count']['minimum'], 1)
        for name in ('target.model.target', 'target.model.evidence',
                     'external.image_input.external_request',
                     'external.image_input.external_request.model_identity',
                     'external.image_input.external_request.schema', 'external.image_input.references'):
            with self.subTest(field=name):
                row = self.field(name)
                command = row['schema_action']['argv']
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    status = contracts.main(command[2:])
                self.assertEqual(status, 0)
                report = json.loads(output.getvalue())
                self.assertEqual(report['schema_fragment'],
                                 contracts.schema_fragment('image_input', row['content_schema_pointer']))
        evidence = self.field('target.model.evidence')
        self.assertIn('sha256', evidence['published_declaration']['required'])
        self.assertNotIn('sha256', evidence['declaration']['required'])
        schema = self.field('external.image_input.external_request.schema')
        self.assertEqual(schema['template'], {'path': None, 'pointer': []})

    def test_native_controls_reference_scope_and_compact_entry_remain_at_their_owners(self):
        self.choices['external'] = external.template()
        self.choices['external']['image_input'] = {'references': [], 'external_request': {
            'schema': {'path': 'actual-schema.json', 'pointer': ['input_schema']}}}
        self.save()
        before = (self.root / self.path).read_bytes()
        request = self.field('external.request')
        self.assertEqual(request['native_schema'], {'path': 'actual-schema.json', 'pointer': ['input_schema']})
        self.assertNotIn('template', request)
        references = self.field('external.image_input.references')
        self.assertEqual(references['selected_source_owner'], 'external.image_input.references')
        self.assertIn({'local_file': True}, references['transport_choices'])
        self.choices['external']['reference_delivery'] = {'choices': {'synthetic': 'selected canonical owner'}}
        self.save()
        self.assertEqual(self.field('external.image_input.references')['selected_source_owner'],
                         'external.reference_delivery.choices')
        summary = guide.summary(self.root, self.path, self.choices)
        self.assertEqual(set(summary['input_contracts']), {'authoring_stage', 'target', 'external'})
        self.assertNotIn('template', json.dumps(summary['input_contracts']))
        self.choices['external']['reference_delivery'] = None
        self.save()
        self.assertEqual((self.root / self.path).read_bytes(), before)

    def test_public_reference_children_reach_exact_schemas_and_source_operations(self):
        self.choices['authoring']['task']['execution'] = 'dispatcher'
        self.choices['authoring']['references'] = None
        self.save()
        before = (self.root / self.path).read_bytes()

        def public(command):
            response = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(response.returncode, 0, response.stdout + response.stderr)
            return json.loads(response.stdout)

        parent = public(guide.action(self.root, self.path, field='authoring.references')['argv'])['fields'][0]
        self.assertEqual(parent['value_state'], 'null')
        child = parent['child_contracts']['additional_references']
        row = public(child['explain_action']['argv'])['fields'][0]
        self.assertEqual(row['choices_pointer'], '/authoring/references/additional_references')
        self.assertEqual(row['value_state'], 'absent')
        self.assertTrue(row['required_when_parent_supplied'])
        self.assertNotIn('required_in_draft', row)
        schema = public(row['schema_action']['argv'])['schema_fragment']
        self.assertEqual(schema['items']['required'], row['item_declaration']['required'])
        self.assertEqual(schema['description'], row['declaration']['description'])
        self.assertEqual(set(parent['child_contracts']),
                         set(contracts.schema_fragment('choices',
                             '/properties/authoring/properties/references/oneOf/1')['properties']))
        source_help = subprocess.run(row['source_navigation']['studio']['argv'], capture_output=True,
                                     text=True, encoding='utf-8')
        self.assertEqual(source_help.returncode, 0, source_help.stdout + source_help.stderr)
        self.assertIn('accepted-source', source_help.stdout)
        mirrored = public(row['image_input_action']['argv'])['fields'][0]
        self.assertEqual(mirrored['field'], 'authoring.references.image_input')
        self.assertIn('mirrors', mirrored['declaration']['description'])
        self.assertEqual((self.root / self.path).read_bytes(), before)

        selected = {'additional_references': [{'role': 'identity', 'source': {
            'kind': 'supplied-file', 'reference_id': 'author-selected', 'resolved_path': 'reference.png'}}]}
        self.choices['authoring']['references'] = selected
        self.save()
        row = public(child['explain_action']['argv'])['fields'][0]
        self.assertEqual(row['value_state'], 'supplied')
        self.assertEqual(c.load(self.root / self.path)['authoring']['references'], selected)


    def test_document_keys_report_the_current_external_generation_schema_scope(self):
        selected = {'file': 'research.json'}
        self.choices['authoring']['documents'] = {'retrieval_record': selected}
        self.save()
        before = (self.root / self.path).read_bytes()
        scope = self.field('authoring.documents')['execution_inputs']
        self.assertEqual(scope['permitted_generation_documents'], ['production_spec', 'state_graphs'])
        self.assertIn('retrieval_record', scope['not_permitted_generation_documents'])
        schema = c.load(guide.ROOT / scope['schema'])
        fragment = schema
        for part in scope['schema_pointers'][-1][1:].split('/'):
            fragment = fragment[int(part)] if isinstance(fragment, list) else fragment[part]
        self.assertFalse(fragment['additionalProperties'])
        self.assertEqual(sorted(fragment['properties']), scope['permitted_generation_documents'])
        explanation = guide.explain(self.root, self.path, field='authoring.documents.retrieval_record')
        self.assertFalse(explanation['execution_input']['permitted_as_generation_document'])
        self.assertEqual(explanation['source'], selected)
        self.assertEqual((self.root / self.path).read_bytes(), before)
        self.choices['authoring']['task']['execution'] = 'dispatcher'
        self.save()
        explanation = guide.explain(self.root, self.path, field='authoring.documents.retrieval_record')
        self.assertTrue(explanation['execution_input']['permitted_as_generation_document'])

    def test_public_generation_guide_distinguishes_inline_fields_and_derived_document_owners(self):
        self.choices['authoring']['generation'] = {'brief': 'Retain this authored text.'}
        self.choices['authoring']['documents'] = {'production_spec': {'file': 'spec.json'}}
        self.save()
        before = (self.root / self.path).read_bytes()
        command = guide.action(self.root, self.path, field='authoring.generation')['argv']
        response = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(response.returncode, 0, response.stdout + response.stderr)
        row = json.loads(response.stdout)['fields'][0]
        self.assertEqual(row['declaration']['permitted_keys'], [])
        self.assertFalse(row['declaration']['additionalProperties'])
        self.assertEqual(row['execution_inputs']['permitted_generation_fields'], ['production_spec', 'state_graphs'])
        self.assertEqual(set(row['derived_owners']), {'production_spec', 'state_graphs'})
        owner = row['derived_owners']['production_spec']
        self.assertEqual(owner['choices_pointer'], '/authoring/documents/production_spec')
        self.assertEqual(owner['source'], {'file': 'spec.json'})
        response = subprocess.run(owner['explain_action']['argv'], capture_output=True,
                                  text=True, encoding='utf-8')
        self.assertEqual(response.returncode, 0, response.stdout + response.stderr)
        self.assertTrue(json.loads(response.stdout)['execution_input']['permitted_as_generation_document'])
        self.assertEqual((self.root / self.path).read_bytes(), before)
        self.assertIsNone(c.load(self.root / self.path)['target'])
        self.choices['authoring']['task']['execution'] = 'dispatcher'
        self.save()
        row = self.field('authoring.generation')
        self.assertIn('brief', row['declaration']['permitted_keys'])
        self.assertIn('count', row['declaration']['permitted_keys'])
        self.assertEqual(row['derived_owners']['model']['choices_pointer'], '/target')
        self.assertEqual(row['derived_owners']['request_validation']['choices_pointer'], '/validation')


    def test_media_array_diagnostic_locates_request_owner_and_preserves_two_subject_scopes(self):
        self.choices['external'] = external.template()
        self.choices['external']['request'] = {'independent': {'seed': 17}}
        self.choices['external']['image_input'] = {
            'external_request': {'prompt_field': ['prompt']},
            'references': [
                {'id': 'person-a', 'subject_uses': [{'subject_id': 'A', 'use': 'identity', 'priority': 0}],
                 'transport': {'local_file': True, 'field': ['media/images~', 0]}},
                {'id': 'person-b', 'subject_uses': [{'subject_id': 'B', 'use': 'identity', 'priority': 0}],
                 'transport': {'local_file': True, 'field': ['media/images~', 1]}},
            ]}
        self.save()
        before = (self.root / self.path).read_bytes()
        request_guide = self.field('external.request')
        diagnostics = request_guide['media_location_diagnostics']
        self.assertEqual([item['reference'] for item in diagnostics], ['person-a', 'person-b'])
        self.assertEqual(diagnostics[0]['repair_owner'],
                         {'file': self.path, 'pointer': '/external/request/media~1images~0'})
        self.assertEqual(diagnostics[1]['mapping_owner']['pointer'],
                         '/external/image_input/references/1/transport/field')
        self.assertEqual(diagnostics[0]['actual'], {'present': False, 'type': 'missing'})
        action = diagnostics[0]['next_action']['argv']
        response = subprocess.run(action, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(response.returncode, 0, response.stdout + response.stderr)
        self.assertIn('[]', json.loads(response.stdout)['fields'][0]['required_action'])
        self.assertEqual((self.root / self.path).read_bytes(), before)
        # Follow the reported repair without changing either identity scope.
        self.choices['external']['request']['media/images~'] = []
        self.save()
        self.assertEqual(self.field('external.request')['media_location_diagnostics'], [])
        rows = [{'reference': row['id'], 'field': row['transport']['field'], 'value': row['id'] + '.png'}
                for row in self.choices['external']['image_input']['references']]
        native, _ = external._media(copy.deepcopy(self.choices['external']['request']), rows, [],
                                    self.choices['external']['image_input']['external_request'])
        self.assertEqual(native, {'independent': {'seed': 17},
                                  'media/images~': ['person-a.png', 'person-b.png']})
        self.assertEqual(json.loads(before)['external']['image_input'],
                         self.choices['external']['image_input'])
        slots = self.field('external.media_slots')
        self.assertEqual(slots['declaration']['items'],
                         guide._shape(contracts.schema_fragment('image_input', '/$defs/field-path')))
        with self.assertRaisesRegex(ValueError, 'declare the existing media slots'):
            external._media({'media/images~': [None]}, copy.deepcopy(rows), [], {'prompt_field': ['prompt']})

    def test_media_location_checks_distinguish_absent_array_and_wrong_native_type(self):
        selected = {'request': [{'images': None, 'prompt': 'retain'}],
                    'image_input': {'references': [{'id': 'A', 'transport': {'field': [0, 'images', 0]}}]}}
        issue = external.media_location_diagnostics(selected, choices_path='draft/choices.json')[0]
        self.assertEqual(issue['pointer'], '/external/request/0/images')
        self.assertEqual(issue['actual'], {'present': True, 'type': 'null'})
        selected['request'][0]['images'] = []
        self.assertEqual(external.media_location_diagnostics(selected), [])
        # Object leaves can be created by the existing builder. Missing field
        # choices and existing-plan inputs remain with their current owners.
        selected['image_input']['references'][0]['transport']['field'] = ['uncreated', 'image']
        self.assertEqual(external.media_location_diagnostics(selected), [])
        self.assertEqual(external.media_location_diagnostics({'image_input': 'saved-plan.json'}), [])

    def test_media_guide_preserves_fixed_record_leaves_and_handles_unfinished_prompt_controls(self):
        selected = external.template()
        selected['request'] = {'inputs': [{'image': None, 'mask': None, 'independent': 17}]}
        selected['image_input'] = {'external_request': {'prompt_field': ['prompt']}, 'references': [
            {'id': 'image', 'transport': {'field': ['inputs', 0, 'image']}},
            {'id': 'mask', 'transport': {'field': ['inputs', 0, 'mask']}}]}
        before = copy.deepcopy(selected)
        self.assertEqual(external.media_location_diagnostics(selected), [])
        rows = [{'reference': item['id'], 'field': item['transport']['field'], 'value': item['id'] + '.png'}
                for item in selected['image_input']['references']]
        native, _ = external._media(copy.deepcopy(selected['request']), rows, [],
                                    selected['image_input']['external_request'])
        self.assertEqual(native['inputs'], [{'image': 'image.png', 'mask': 'mask.png', 'independent': 17}])
        self.assertEqual(selected, before)
        selected['image_input']['external_request']['prompt_syntax'] = {'control': {}}
        self.choices['external'] = selected
        self.save()
        self.assertEqual(self.field('external.request')['media_location_diagnostics'], [])
        self.assertEqual(c.load(self.root / self.path), self.choices)


class PublicExternalAuthoringTests(unittest.TestCase):
    def test_external_inline_brief_is_located_before_inspection_and_check_build_files(self):
        import production_inputs
        import production_store
        import work_ledger
        from catalog_retrieval.runtime import configure_pack_runtime

        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / 'studio'
            root.mkdir()
            with fixtures.scratch_home(base / 'home'):
                configure_pack_runtime(None)
                self.addCleanup(configure_pack_runtime, None)
                work_ledger.begin(root, 'Synthetic external generation ownership.', ['Inspect its authored fields'])
                (root / 'request.txt').write_text('Keep this complete original source brief.', encoding='utf-8')
                draft = production_inputs.draft_inputs(root, None, 'draft', operation='compose',
                    request_file='request.txt', route='generation', execution='external', artifact='image',
                    features=['unlisted-interface'])
                path = draft['choices_file']
                choices = c.load(root / path)
                choices['authoring']['generation']['brief'] = 'A separate inline copy that this execution forbids.'
                (root / path).write_bytes(c.encoded(choices))
                before = {name: (root / name).read_bytes() for name in (path, 'request.txt', 'draft/work-basis.json')}
                for command, code in (('inspect-inputs', 0), ('check', 2)):
                    response = subprocess.run([sys.executable, str(guide.ROOT / 'scripts/production_workflow.py'),
                        command, '--root', str(root), '--choices', path, '--view', 'full'], capture_output=True,
                        text=True, encoding='utf-8')
                    self.assertEqual(response.returncode, code, response.stdout + response.stderr)
                    report = json.loads(response.stdout)
                    diagnostics = ([item for row in report['inputs'] for item in row['unresolved']]
                                   if command == 'inspect-inputs' else report['diagnostics'])
                    [issue] = [item for item in diagnostics if item.get('cause') == 'generation-field-not-permitted']
                    self.assertEqual((issue['code'], issue['file'], issue['pointer']),
                                     ('INPUT_SCHEMA_INVALID', path, '/authoring/generation/brief'))
                    self.assertEqual(issue['repair_owner'], {'file': path, 'pointer': '/authoring/generation/brief'})
                    self.assertEqual(issue['expected']['permitted_keys'], ['production_spec', 'state_graphs'])
                    self.assertEqual(resolved_action(report, issue['next_action'])['argv'][-2:],
                                     ['--field', 'authoring.generation'])
                    self.assertNotIn('authoring.documents.production_task', json.dumps(diagnostics))
                    self.assertFalse(report['external_effect'])
                self.assertEqual({name: (root / name).read_bytes() for name in before}, before)
                self.assertEqual(production_store.runs(root), [])

    def test_dispatcher_keeps_legal_brief_and_compiler_names_the_actual_inline_owner(self):
        import production_case_fixtures as cases
        from catalog_retrieval.runtime import configure_pack_runtime

        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            with fixtures.scratch_home(base / 'home'):
                self.addCleanup(configure_pack_runtime, None)
                case = cases.create(base / 'studio', base / 'runtime')
                root, settings = case['root'], case['settings']
                draft = fixtures.authoring_inputs(root, 'task.json', 'draft')
                path = draft['choices_file']
                choices = c.load(root / path)
                choices['authoring']['generation']['brief'] = 'An explicit dispatcher brief remains legal.'
                (root / path).write_bytes(c.encoded(choices))
                command = [sys.executable, str(guide.ROOT / 'scripts/production_workflow.py'),
                    'check', '--root', str(root), '--choices', path,
                    '--state-file', str(settings.state_file), '--cache-dir', str(settings.cache_dir),
                    '--managed-root', str(settings.managed_root), '--pack-root', str(case['pack'])]
                response = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
                self.assertEqual(response.returncode, 0, response.stdout + response.stderr)
                self.assertTrue(json.loads(response.stdout)['publishable'])
                self.assertEqual(c.load(root / path), choices)
                # Draft-shaped objects reach the compiled task schema. Both
                # the container and a nested defect retain their mutable owner.
                for intent, generated_pointer in (
                    ({}, '$.generation.render_intent'),
                    ({'artifact_type': 'render-intent', 'execution_mode': 'synthetic-invalid-mode'},
                     '$.generation.render_intent.execution_mode')):
                    with self.subTest(pointer=generated_pointer):
                        choices['authoring']['generation']['render_intent'] = intent
                        (root / path).write_bytes(c.encoded(choices))
                        response = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
                        self.assertEqual(response.returncode, 2, response.stdout + response.stderr)
                        diagnostics = json.loads(response.stdout)['diagnostics']
                        issues = [item for item in diagnostics if item.get('generated_pointer') == generated_pointer]
                        self.assertTrue(issues, diagnostics)
                        for issue in issues:
                            self.assertEqual((issue['file'], issue['pointer'], issue['authoring_field']),
                                (path, '/authoring/generation/render_intent', 'authoring.generation.render_intent'))
                            self.assertEqual(issue['repair_owner'],
                                {'file': path, 'pointer': '/authoring/generation/render_intent'})
                        self.assertNotIn('authoring.documents.production_task', json.dumps(diagnostics))
                        self.assertEqual(c.load(root / path), choices)

    def test_public_inspection_reports_missing_media_array_before_native_assembly(self):
        import production_inputs
        import work_ledger
        from catalog_retrieval.runtime import configure_pack_runtime

        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / 'studio'
            root.mkdir()
            with fixtures.scratch_home(base / 'home'):
                configure_pack_runtime(None)
                self.addCleanup(configure_pack_runtime, None)
                work_ledger.begin(root, 'Synthetic first reference after a text-only request.', ['inspect'])
                (root / 'request.txt').write_text('Show the two fictional subjects together.', encoding='utf-8')
                draft = production_inputs.draft_inputs(root, None, 'draft', operation='compose',
                    request_file='request.txt', route='generation', execution='external', artifact='image',
                    features=['unlisted-interface'])
                path = draft['choices_file']
                choices = c.load(root / path)
                choices['external']['request'] = {'transparent': False}
                choices['external']['image_input'] = {
                    'artifact_type': 'image-input-plan', 'external_request': {'prompt_field': ['prompt']},
                    'references': [{'id': 'A', 'transport': {'local_file': True, 'field': ['pictures', 0]}}]}
                (root / path).write_bytes(c.encoded(choices))
                command = [sys.executable, str(guide.ROOT / 'scripts/production_workflow.py'),
                           'inspect-inputs', '--root', str(root), '--choices', path]
                response = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
                self.assertEqual(response.returncode, 0, response.stdout + response.stderr)
                report = json.loads(response.stdout)
                issues = [item for item in report['diagnostics']
                          if item.get('cause') == 'native-media-array-not-declared']
                self.assertEqual(len(issues), 1, report)
                self.assertEqual(issues[0]['file'], path)
                self.assertEqual(issues[0]['pointer'], '/external/request/pictures')
                self.assertFalse(report['external_effect'])
                choices['external']['request']['pictures'] = [None]
                (root / path).write_bytes(c.encoded(choices))
                response = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
                self.assertEqual(response.returncode, 0, response.stdout + response.stderr)
                issues = [item for item in json.loads(response.stdout)['diagnostics']
                          if item.get('cause') == 'native-media-slots-not-declared']
                self.assertEqual(len(issues), 1)
                self.assertEqual(issues[0]['repair_owner'], {'file': path, 'pointer': '/external/media_slots'})
                self.assertEqual(issues[0]['request_owner'], {'file': path, 'pointer': '/external/request/pictures'})
                self.assertEqual(c.load(root / path), choices)
                choices['external']['request']['pictures'] = []
                (root / path).write_bytes(c.encoded(choices))
                response = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
                self.assertEqual(response.returncode, 0, response.stdout + response.stderr)
                self.assertFalse(any(item.get('cause', '').startswith('native-media-')
                    for item in json.loads(response.stdout)['diagnostics']))
                self.assertEqual(c.load(root / path), choices)

    def test_public_field_output_completes_a_new_draft_and_materializes_the_evidenced_native_request(self):
        import production_inputs
        import production_target
        import work_ledger
        from catalog_retrieval.runtime import configure_pack_runtime
        from input_evidence import InputEvidence

        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / 'studio'
            root.mkdir()
            with fixtures.scratch_home(base / 'home'):
                configure_pack_runtime(None)
                self.addCleanup(configure_pack_runtime, None)
                work_ledger.begin(root, 'Synthetic public external input discovery.', ['Author an exact request'])
                (root / 'request.txt').write_text('Draw a synthetic segmented shell observer.', encoding='utf-8')
                draft = production_inputs.draft_inputs(root, None, 'draft', operation='compose',
                    request_file='request.txt', route='generation', execution='external', artifact='image',
                    features=['unlisted-interface'])
                path = draft['choices_file']
                choices = c.load(root / path)

                def public_field(field):
                    command = guide.action(root, path, field=field)['argv']
                    result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    return json.loads(result.stdout)['fields'][0]

                def save():
                    (root / path).write_bytes(c.encoded(choices))

                # The synthetic interface evidence, not the guide, selects the
                # model kind, native operation and exact provider field names.
                evidence = {'tool': 'synthetic.paint', 'service': 'synthetic-host',
                            'model': 'synthetic-unlisted-model', 'operation': 'paint'}
                (root / 'interface.json').write_bytes(c.encoded(evidence))
                native_schema = {'type': 'object', 'required': ['instruction', 'transparent'],
                    'properties': {'instruction': {'type': 'string'}, 'transparent': {'type': 'boolean'}},
                    'additionalProperties': False}
                (root / 'native-schema.json').write_bytes(c.encoded(native_schema))
                choices['target'] = {'kind': 'external', 'model': None}
                save()
                model = public_field('target.model')['template']
                model['requested'] = evidence['model']
                model['target'].update(service=evidence['service'], model_identifier=evidence['model'],
                                       operation=evidence['operation'])
                model['evidence'].update(path='interface.json', locator='synthetic tool identity')
                choices['target']['model'] = model
                choices['external'] = public_field('external')['template']
                save()
                plan = public_field('external.image_input')['template']
                request = public_field('external.image_input.external_request')['template']
                request.update(prompt_field=['instruction'], count=1)
                model_identity = public_field('external.image_input.external_request.model_identity')['template']
                model_identity.update(kind='tool', value=evidence['tool'])
                model_identity['evidence'].update(path='interface.json', locator='synthetic tool identity')
                request['model_identity'] = model_identity
                request['schema'] = public_field('external.image_input.external_request.schema')['template']
                request['schema']['path'] = 'native-schema.json'
                plan['external_request'] = request
                choices['external']['image_input'] = plan
                choices['external']['request'] = {'transparent': False}
                save()
                request_guide = public_field('external.request')
                self.assertEqual(request_guide['native_schema'], {'path': 'native-schema.json', 'pointer': []})
                self.assertEqual(production_target.unresolved(choices['target'], choices['authoring']['task']), [])
                self.assertEqual(external.unresolved(choices['external']), [])
                before = copy.deepcopy(choices)
                reader = InputEvidence(root)
                projected = production_target.project(choices, choices['authoring']['task'], root, reader, 'built')
                self.assertEqual(projected['unresolved'], [])
                delivery = b'A synthetic segmented shell observer rests beside a ledge.'
                files, trace = external.build(projected['choices']['external'], projected['task'], reader,
                    root, 'built', delivery, derived_files=projected['files'])
                self.assertEqual(trace['request'], {'instruction': delivery.decode(), 'transparent': False})
                self.assertEqual(trace['schema_validation']['mode'], 'target-schema')
                compiled_plan = c.decode(files['image-input.json'])
                self.assertEqual(compiled_plan['model']['prompt_input']['mode'], 'unresolved')
                self.assertEqual(compiled_plan['external_request']['model_identity']['value'], evidence['tool'])
                self.assertEqual(compiled_plan['references'], [])
                self.assertEqual(c.load(root / path), before)


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
