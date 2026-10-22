"""Generic edit bindings and external production recovery on real local images."""
from __future__ import annotations

import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import execution_contract as c
import semantic_edit_plan as edits
import image_input as inputs

PROMPT = 'Change the wall color behind the vase. Preserve the vase geometry and cafe interior.'
TARGET = {'service': 'synthetic-host', 'model_identifier': 'vendor:example-editor@1', 'operation': 'edit'}


def png(color, size=(24, 16)):
    from PIL import Image
    output = io.BytesIO()
    Image.new('RGB', size, color).save(output, format='PNG')
    return output.getvalue()


def write(root, name, value):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value if isinstance(value, bytes) else c.encoded(value))


def sync_external_prompt(root, plan, body=PROMPT):
    """Author the complete synthetic delivery and saved request from shared text."""
    from request_contract import put
    external = plan['external_request']
    request = c.load(root / external['file'])
    instructions = inputs.reference_instructions(plan, base=root)
    prompt = body + ('\n\n' + instructions if instructions else '')
    put(request, external['prompt_field'], prompt)
    write(root, external['file'], request)
    write(root, 'prompt.txt', prompt.encode('utf-8'))
    return prompt


def setup_plan(root):
    """A generic product scene and construction view, with synthetic evidence."""
    root.mkdir(parents=True, exist_ok=True)
    write(root, 'scene.png', png((20, 80, 100)))
    write(root, 'design.png', png((120, 30, 80), (32, 24)))
    write(root, 'model-evidence.json', {'synthetic': True, 'requested': 'Example Editor 1',
                                      'catalog_status': 'missing', 'offered_target': TARGET})
    write(root, 'upload-evidence.json', {'synthetic': True, 'images': [
        {'source_sha256': c.sha256_file(root / 'scene.png'), 'image_id': 'synthetic-scene'},
        {'source_sha256': c.sha256_file(root / 'design.png'), 'image_id': 'synthetic-design'}]})
    write(root, 'request.json', {'model': TARGET['model_identifier'], 'operation': TARGET['operation'],
                                'prompt': PROMPT, 'count': 1, 'images': ['synthetic-scene', 'synthetic-design']})
    write(root, 'prompt.txt', PROMPT.encode('utf-8'))
    plan = {'artifact_type': 'semantic-edit-plan', 'source': 'scene',
            'edit': {'target': 'wall behind the vase', 'change': 'replace the wall color',
                     'preserve': ['vase geometry', 'camera framing'], 'required_reference_roles': ['scene', 'geometry']},
            'model': {'requested': 'Example Editor 1', 'catalog_status': 'missing', 'catalog_model': None,
                      'target': copy.deepcopy(TARGET), 'evidence': {'path': 'model-evidence.json',
                      'sha256': c.sha256_file(root / 'model-evidence.json'), 'locator': 'whole synthetic lookup'}},
            'references': [
                {'id': 'scene', 'role': 'scene', 'file': 'scene.png', 'use_for': ['composition', 'camera framing'],
                 'do_not_transfer': ['old wall color']},
                {'id': 'design', 'role': 'geometry', 'file': 'design.png', 'use_for': ['vase geometry'],
                 'do_not_transfer': ['reference pose', 'reference background']}],
            'review_criteria': ['wall', 'geometry'],
            'external_request': {'file': 'request.json', 'model_field': ['model'], 'prompt_field': ['prompt'],
                                 'count_field': ['count'], 'operation_field': ['operation'], 'count': 1,
                                 'reference_fields': [
                                     {'reference': ident, 'field': ['images', i], 'value': 'synthetic-' + ident,
                                      'evidence': {'path': 'upload-evidence.json',
                                      'sha256': c.sha256_file(root / 'upload-evidence.json'),
                                      'locator': 'synthetic image ' + str(i)}} for i, ident in enumerate(('scene', 'design'))]}}
    edit = {key: plan.pop(key) for key in ('source', 'edit', 'review_criteria')}
    edit['artifact_type'] = 'semantic-edit-plan'
    plan['artifact_type'] = 'image-input-plan'
    write(root, 'edit-plan.json', edit)
    sync_external_prompt(root, plan)
    write(root, 'image-input.json', plan)
    return plan


def setup_text_only_plan(root):
    """An exact synthetic image request with no source image or media field."""
    root.mkdir(parents=True, exist_ok=True)
    target = {'service': 'synthetic-host', 'model_identifier': 'vendor:example-generator@1', 'operation': 'generate'}
    prompt = 'A blue glass vase stands on a square table.'
    write(root, 'model-evidence.json', {'synthetic': True, 'offered_target': target})
    write(root, 'request.json', {'model': target['model_identifier'], 'operation': target['operation'],
                                'prompt': prompt, 'count': 1})
    write(root, 'request-schema.json', {'type': 'object', 'additionalProperties': False,
        'required': ['model', 'operation', 'prompt', 'count'],
        'properties': {'model': {'const': target['model_identifier']}, 'operation': {'const': 'generate'},
                       'prompt': {'type': 'string', 'minLength': 1}, 'count': {'type': 'integer', 'minimum': 1}}})
    write(root, 'prompt.txt', prompt.encode('utf-8'))
    plan = {'artifact_type': 'image-input-plan',
        'model': {'requested': 'Example Generator 1', 'catalog_status': 'missing', 'catalog_model': None,
            'target': target, 'evidence': {'path': 'model-evidence.json',
                'sha256': c.sha256_file(root / 'model-evidence.json'), 'locator': 'whole synthetic target'}},
        'references': [], 'external_request': {'file': 'request.json',
            'sha256': c.sha256_file(root / 'request.json'), 'model_field': ['model'], 'operation_field': ['operation'],
            'prompt_field': ['prompt'], 'count_field': ['count'], 'count': 1, 'reference_fields': [],
            'schema': {'path': 'request-schema.json', 'sha256': c.sha256_file(root / 'request-schema.json'),
                       'pointer': []}}}
    write(root, 'image-input.json', plan)
    return plan


class SemanticEditPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.plan = setup_plan(self.root)

    def validate(self):
        return inputs.validate(self.plan, self.root)

    def test_binding_keeps_generic_roles_exact_target_and_all_original_hashes(self):
        result = self.validate()
        self.assertEqual(result['status'], 'prepared-not-generated')
        self.assertEqual(result['model']['catalog_status'], 'missing')
        self.assertIsNone(result['model']['catalog_model'])
        self.assertEqual(result['model']['requested'], 'Example Editor 1')
        self.assertEqual([x['role'] for x in result['references']], ['scene', 'geometry'])
        self.assertEqual(result['references'][1]['sha256'], c.sha256_file(self.root / 'design.png'))
        self.assertEqual(result['external_request']['schema_validation'],
                         {'mode': 'bounded-probe', 'unmeasured': ['schema-unavailable']})
        inputs.validate_binding(result)

    def test_missing_required_reference_role_is_rejected(self):
        edit = c.load(self.root / 'edit-plan.json')
        edit['edit']['required_reference_roles'].append('surface-material')
        with self.assertRaisesRegex(ValueError, 'missing required reference roles'):
            edits.validate(edit, self.validate())

    def test_duplicate_or_missing_source_reference_is_rejected(self):
        self.plan['references'][1]['id'] = 'scene'
        with self.assertRaisesRegex(ValueError, 'duplicate reference id'):
            self.validate()
        self.plan = setup_plan(self.root)
        edit = c.load(self.root / 'edit-plan.json')
        edit['source'] = 'absent'
        with self.assertRaisesRegex(ValueError, 'scene role'):
            edits.validate(edit, self.validate())

    def test_references_need_actual_decodable_images(self):
        write(self.root, 'design.png', b'not image pixels')
        with self.assertRaisesRegex(ValueError, 'actual image'):
            self.validate()

    def test_reference_free_plan_requires_a_complete_external_request(self):
        from state_protocol import validate_against_schema
        schema = c.load(inputs.SCHEMA)
        for request in ('null', 'absent', 'incomplete'):
            self.plan = setup_text_only_plan(self.root)
            if request == 'absent':
                self.plan.pop('external_request')
            else:
                self.plan['external_request'] = None if request == 'null' else {}
            with self.subTest(request=request):
                errors = validate_against_schema(self.plan, schema)
                self.assertTrue(any('external_request' in error for error in errors), errors)
                with self.assertRaisesRegex(ValueError, 'external_request'):
                    self.validate()

    def test_text_only_external_binding_pins_request_and_schema(self):
        from state_protocol import validate_against_schema
        self.plan = setup_text_only_plan(self.root)
        for name in ('scene.png', 'design.png', 'upload-evidence.json'):
            (self.root / name).unlink()
        self.assertEqual(validate_against_schema(self.plan, c.load(inputs.SCHEMA)), [])
        binding = self.validate()
        self.assertEqual(binding['references'], [])
        self.assertEqual(inputs.reference_bindings(self.plan), [])
        self.assertEqual(inputs.reference_instructions(self.plan), '')
        external = binding['external_request']
        self.assertEqual(external['request'], c.load(self.root / 'request.json'))
        self.assertEqual(external['sha256'], c.sha256_file(self.root / 'request.json'))
        self.assertEqual(external['schema']['sha256'], c.sha256_file(self.root / 'request-schema.json'))
        self.assertEqual(external['schema_validation'], {'mode': 'target-schema', 'unmeasured': []})
        inputs.validate_binding(binding)
        changed = copy.deepcopy(binding)
        changed['external_request']['request']['prompt'] = 'An uncommitted different instruction.'
        with self.assertRaisesRegex(ValueError, 'integrity mismatch'):
            inputs.validate_binding(changed)

    def test_reference_free_plan_rejects_declared_media_fields(self):
        from state_protocol import validate_against_schema
        media = copy.deepcopy(self.plan['external_request']['reference_fields'][:1])
        self.plan = setup_text_only_plan(self.root)
        self.plan['external_request']['reference_fields'] = media
        errors = validate_against_schema(self.plan, c.load(inputs.SCHEMA))
        self.assertEqual(errors, ['$.external_request.reference_fields: array is longer than maxItems'])
        with self.assertRaisesRegex(ValueError, 'reference_fields: array is longer than maxItems'):
            self.validate()

    def test_text_only_binding_cannot_supply_a_semantic_edit_source(self):
        self.plan = setup_text_only_plan(self.root)
        with self.assertRaisesRegex(ValueError, 'source must name a reference with the scene role'):
            edits.validate(c.load(self.root / 'edit-plan.json'), self.validate())

    def test_pinned_reference_change_is_rejected(self):
        self.plan['references'][1]['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            self.validate()

    def test_scope_types_and_explicit_conflicts_are_rejected(self):
        self.plan['references'][1]['use_for'] = 'shape'
        with self.assertRaisesRegex(ValueError, 'image input plan'):
            self.validate()
        self.plan = setup_plan(self.root)
        self.plan['references'][1]['do_not_transfer'] = ['vase geometry']
        with self.assertRaisesRegex(ValueError, 'allows and forbids'):
            self.validate()

    def test_paths_cannot_escape_the_studio(self):
        self.plan['references'][1]['file'] = '../design.png'
        with self.assertRaises(ValueError):
            self.validate()

    def test_external_request_cannot_substitute_model_or_upload(self):
        request = c.load(self.root / 'request.json')
        request['model'] = 'vendor:different-editor@1'
        write(self.root, 'request.json', request)
        with self.assertRaisesRegex(ValueError, 'substitutes'):
            self.validate()
        request['model'] = TARGET['model_identifier']
        request['images'].reverse()
        write(self.root, 'request.json', request)
        with self.assertRaisesRegex(ValueError, 'reference is missing or changed'):
            self.validate()

    def test_external_request_cannot_drop_or_add_undeclared_images(self):
        self.plan['external_request']['reference_fields'].pop()
        with self.assertRaisesRegex(ValueError, 'every selected reference'):
            self.validate()
        self.plan = setup_plan(self.root)
        request = c.load(self.root / 'request.json')
        request['images'].append('unselected-image')
        write(self.root, 'request.json', request)
        with self.assertRaisesRegex(ValueError, 'undeclared or missing reference'):
            self.validate()

    def test_media_overlap_names_both_references_and_complete_paths(self):
        fields = self.plan['external_request']['reference_fields']
        source_path = ['messages', 0, 'content', 1, 'image_url', 'url']
        fields[0]['field'] = source_path
        for conflicting_path in (source_path, source_path[:-1]):
            fields[1]['field'] = conflicting_path
            with self.subTest(path=conflicting_path):
                with self.assertRaises(ValueError) as raised:
                    self.validate()
                self.assertEqual(str(raised.exception),
                    'external media fields overlap without identical bytes and value: '
                    f"reference 'design' at {json.dumps(conflicting_path)} conflicts with "
                    f"reference 'scene' at {json.dumps(source_path)}")

    def test_media_control_overlap_names_reference_and_complete_paths(self):
        external = self.plan['external_request']
        media_path = ['messages', 0, 'content', 1, 'image_url', 'url']
        prompt_path = ['messages', 0, 'content']
        external['prompt_field'] = prompt_path
        external['reference_fields'][0]['field'] = media_path
        with self.assertRaises(ValueError) as raised:
            self.validate()
        self.assertEqual(str(raised.exception),
            f"external request fields overlap: reference 'scene' at {json.dumps(media_path)} "
            f'conflicts with request field {json.dumps(prompt_path)}')

    def test_nested_media_objects_cannot_hide_an_unbound_array_entry(self):
        request = c.load(self.root / 'request.json')
        request['images'] = [{'uri': value} for value in request['images']]
        for row in self.plan['external_request']['reference_fields']:
            row['field'].append('uri')
        write(self.root, 'request.json', request)
        sync_external_prompt(self.root, self.plan)
        self.validate()
        request = c.load(self.root / 'request.json')
        request['images'].append({'uri': 'unbound-extra-image'})
        write(self.root, 'request.json', request)
        with self.assertRaisesRegex(ValueError, 'undeclared or missing reference'):
            self.validate()

    def test_nested_mixed_content_checks_every_image_field_and_keeps_text_entries(self):
        request = c.load(self.root / 'request.json')
        scene, design = request.pop('images')
        request['messages'] = [
            {'content': [{'text': 'Synthetic text content'}, {'image_url': {'url': scene}}]},
            {'content': [{'image_url': {'url': design}}, {'text': 'More synthetic text'}]}]
        fields = self.plan['external_request']['reference_fields']
        fields[0]['field'] = ['messages', 0, 'content', 1, 'image_url', 'url']
        fields[1]['field'] = ['messages', 1, 'content', 0, 'image_url', 'url']
        write(self.root, 'request.json', request)
        sync_external_prompt(self.root, self.plan)
        self.validate()
        request = c.load(self.root / 'request.json')
        request['messages'].append({'content': [{'text': 'Text stays valid'},
            {'image_url': {'url': 'unbound-extra-image'}}]})
        write(self.root, 'request.json', request)
        with self.assertRaisesRegex(ValueError, 'undeclared or missing reference'):
            self.validate()

    def test_saved_scope_metadata_without_canonical_prompt_text_is_rejected(self):
        request = c.load(self.root / 'request.json')
        request['prompt'] = PROMPT
        write(self.root, 'request.json', request)
        write(self.root, 'prompt.txt', PROMPT.encode('utf-8'))
        with self.assertRaisesRegex(ValueError, 'canonical reference delivery instructions'):
            self.validate()

    def test_changed_scope_subject_use_or_priority_requires_updated_prompt_text(self):
        # Two sources share (subject a, identity), so the priority order reaches
        # the canonical text and every mutation, including priority, drifts it.
        self.plan['references'][0]['subject_uses'] = [{'subject_id': 'a', 'use': 'identity', 'priority': 0}]
        self.plan['references'][1]['subject_uses'] = [{'subject_id': 'a', 'use': 'identity', 'priority': 1}]
        sync_external_prompt(self.root, self.plan)
        original = copy.deepcopy(self.plan)
        for change in ('scope', 'exclusion', 'subject', 'use', 'priority'):
            self.plan = copy.deepcopy(original)
            row = self.plan['references'][0]
            if change == 'scope':
                row['use_for'].append('new scoped construction')
            elif change == 'exclusion':
                row['do_not_transfer'].append('source lighting')
            else:
                key, value = {'subject': ('subject_id', 'b'), 'use': ('use', 'outfit'),
                              'priority': ('priority', 1)}[change]
                row['subject_uses'][0][key] = value
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'canonical reference delivery instructions'):
                self.validate()

    def test_reference_text_can_be_authored_before_the_saved_request_with_named_fields(self):
        import contextlib
        import reference_delivery
        fields = self.plan['external_request']['reference_fields']
        fields[0]['field'] = ['source_image']
        fields[1]['field'] = ['reference_image']
        (self.root / 'request.json').unlink()
        text = inputs.reference_instructions(self.plan)
        self.assertIn('Reference 1 means request field ["source_image"]', text)
        self.assertIn('Reference 2 means request field ["reference_image"]', text)
        self.assertNotIn('means Image', text)
        self.assertIn('Do not inherit: old wall color.', text)
        write(self.root, 'image-input.json', self.plan)
        output = io.StringIO()
        with patch('sys.argv', ['reference_delivery.py', '--image-input-plan', str(self.root / 'image-input.json')]), \
                contextlib.redirect_stdout(output):
            self.assertEqual(reference_delivery.main(), 0)
        self.assertEqual(json.loads(output.getvalue())['reference_preamble'], text)

    def test_missing_catalog_record_cannot_masquerade_as_defined(self):
        self.plan['model']['catalog_status'] = 'defined'
        with self.assertRaisesRegex(ValueError, 'catalog record'):
            self.validate()

    def test_acquired_schema_checks_actual_media_dimensions_and_unknown_keywords(self):
        schema = {'type': 'object', 'required': ['model', 'prompt', 'images'],
                  'properties': {'model': {'const': TARGET['model_identifier']}, 'prompt': {'type': 'string'},
                                 'images': {'type': 'array', 'minItems': 2, 'maxItems': 2}},
                  'x-constraints': [{'operation': 'width', 'parameters': ['images'], 'scope': 'each', 'minimum': 16}],
                  'x-unmeasured-rendering': True}
        write(self.root, 'schema-evidence.json', {'schema': json.dumps(schema)})
        self.plan['external_request']['schema'] = {'path': 'schema-evidence.json',
            'sha256': c.sha256_file(self.root / 'schema-evidence.json'), 'pointer': ['schema']}
        result = self.validate()
        self.assertEqual(result['external_request']['schema_validation']['mode'], 'target-schema')
        self.assertIn('$.x-unmeasured-rendering', result['external_request']['schema_validation']['unmeasured'])
        write(self.root, 'design.png', png((0, 0, 0), (8, 24)))
        with self.assertRaisesRegex(ValueError, 'violates acquired schema'):
            self.validate()

    def test_dispatch_reference_binding_rejects_reorder_scope_loss_and_target_change(self):
        self.plan['external_request'] = None
        self.plan['model'].update(catalog_status='defined', catalog_model='example-editor')
        binding = self.validate()
        prepared = {'transport_mode': 'multi-image', 'selected_references': [
            {'source': {'sha256': row['sha256']}, 'role': row['role'],
             'authority': {'controls': row['use_for'], 'must_not_control': row['do_not_transfer']}}
            for row in binding['references']]}
        inputs.require_prepared(binding, prepared, model_id='example-editor', target=TARGET)
        for change in ('order', 'scope', 'missing'):
            current = copy.deepcopy(prepared)
            if change == 'order':
                current['selected_references'].reverse()
            elif change == 'scope':
                current['selected_references'][1]['authority']['must_not_control'] = []
            else:
                current['selected_references'].pop()
            with self.subTest(change=change), self.assertRaises(ValueError):
                inputs.require_prepared(binding, current, model_id='example-editor', target=TARGET)
        with self.assertRaisesRegex(ValueError, 'compiled target'):
            inputs.require_prepared(binding, prepared, model_id='another-editor', target=TARGET)

    def test_external_preview_does_not_relax_dispatcher_plan_requirements(self):
        from state_protocol import validate_against_schema
        schema = c.load(edits.ROOT / 'schemas/authoring/production-execution-plan.schema.json')
        value = {'run': None, 'execution': 'external', 'input_sha256': '0' * 64,
                 'request_sha256': None, 'operations': [], 'external_effects': [],
                 'readiness': {'state': 'authorization_required', 'executable': False, 'diagnostics': []},
                 'request': c.load(self.root / 'request.json'), 'service': TARGET['service'],
                 'model': TARGET['model_identifier'], 'quantities': {'submissions': 1, 'outputs': 1},
                 'prepared_request_sha256': c.sha256_file(self.root / 'request.json'),
                 'model_identity': None, 'validation': {'mode': 'bounded-probe', 'unmeasured': ['schema-unavailable']}}
        self.assertEqual(validate_against_schema(value, schema), [])
        value['execution'] = 'dispatcher'
        value.pop('validation')
        errors = validate_against_schema(value, schema)
        for field in ('recording', 'transport', 'handoff', 'validation', 'mutable_fields'):
            self.assertTrue(any('requires ' + repr(field) in error for error in errors), errors)

    def test_new_scene_references_need_no_scene_source_or_edit_contract(self):
        self.plan['references'][0].update(id='subject-a', role='identity')
        self.plan['references'][1].update(id='subject-b', role='identity')
        for field, ident in zip(self.plan['external_request']['reference_fields'], ('subject-a', 'subject-b')):
            field['reference'] = ident
        binding = self.validate()
        self.assertNotIn('source', binding)
        self.assertNotIn('edit', binding)
        self.assertEqual([row['role'] for row in binding['references']], ['identity', 'identity'])
        with self.assertRaisesRegex(ValueError, 'scene role'):
            edits.validate(c.load(self.root / 'edit-plan.json'), binding)

    def test_endpoint_or_tool_model_identity_does_not_require_a_model_parameter(self):
        request = c.load(self.root / 'request.json')
        request.pop('model')
        write(self.root, 'request.json', request)
        self.plan['external_request']['model_field'] = None
        for kind in ('endpoint', 'tool'):
            self.plan['external_request']['model_identity'] = {
                'kind': kind, 'value': 'synthetic/' + kind + '/example-editor',
                'evidence': copy.deepcopy(self.plan['model']['evidence'])}
            binding = self.validate()
            self.assertNotIn('model', binding['external_request']['request'])
            self.assertEqual(binding['external_request']['model_identity']['kind'], kind)
        self.plan['external_request'].pop('model_identity')
        with self.assertRaisesRegex(ValueError, 'model_identity'):
            self.validate()

    def test_one_attachment_keeps_multiple_logical_roles_with_the_same_bytes(self):
        self.plan['references'][1]['file'] = 'scene.png'
        self.plan['external_request']['reference_fields'][1].update(field=['images', 0], value='synthetic-scene')
        request = c.load(self.root / 'request.json')
        request['images'] = ['synthetic-scene']
        write(self.root, 'request.json', request)
        sync_external_prompt(self.root, self.plan)
        binding = self.validate()
        self.assertEqual(len(binding['references']), 2)
        self.assertEqual(len(binding['external_request']['request']['images']), 1)
        self.plan['references'][1]['file'] = 'design.png'
        with self.assertRaisesRegex(ValueError, 'identical bytes'):
            self.validate()

    def test_four_logical_subject_references_name_their_three_actual_carriers(self):
        write(self.root, 'outfit.png', png((90, 60, 30)))
        refs = []
        fields = []
        uploads = []
        for ident, subject, use, name, number in (
            ('a-face', 'a', 'identity', 'scene.png', 0),
            ('a-outfit', 'a', 'outfit', 'scene.png', 0),
            ('b-face', 'b', 'identity', 'design.png', 1),
            ('b-outfit', 'b', 'outfit', 'outfit.png', 2),
        ):
            refs.append({'id': ident, 'role': use, 'file': name, 'use_for': [subject + ' ' + use + ' construction'],
                'do_not_transfer': ['source pose', 'source background'],
                'subject_uses': [{'subject_id': subject, 'use': use, 'priority': 0}]})
            fields.append({'reference': ident, 'field': ['images', number], 'value': 'synthetic-image-' + str(number),
                'evidence': {'path': 'upload-evidence.json', 'sha256': '0' * 64, 'locator': 'image ' + str(number)}})
            uploads.append({'source_sha256': c.sha256_file(self.root / name), 'value': fields[-1]['value']})
        write(self.root, 'upload-evidence.json', {'synthetic': True, 'uploads': uploads})
        for row in fields:
            row['evidence']['sha256'] = c.sha256_file(self.root / 'upload-evidence.json')
        self.plan['references'] = refs
        self.plan['external_request']['reference_fields'] = fields
        request = c.load(self.root / 'request.json')
        request['images'] = ['synthetic-image-' + str(index) for index in range(3)]
        write(self.root, 'request.json', request)
        prompt = sync_external_prompt(self.root, self.plan, 'Two characters converse across a desk.')
        binding = self.validate()
        self.assertEqual(len(binding['references']), 4)
        self.assertEqual(len(binding['external_request']['request']['images']), 3)
        self.assertIn('Reference 1 means request field ["images",0]', prompt)
        self.assertIn('Reference 2 means request field ["images",0]', prompt)
        self.assertIn('Reference 3 means request field ["images",1]', prompt)
        self.assertIn('Reference 4 means request field ["images",2]', prompt)
        self.assertIn('subject a, outfit', prompt)
        self.assertIn('subject b, identity', prompt)
        self.assertNotIn('means Image', prompt)

    def test_subject_assignments_cannot_drift_after_reference_preparation(self):
        self.plan['external_request'] = None
        self.plan['model'].update(catalog_status='defined', catalog_model='example-editor')
        self.plan['references'][0]['subject_uses'] = [{'subject_id': 'a', 'use': 'identity', 'priority': 0}]
        binding = self.validate()
        prepared = {'transport_mode': 'multi-image', 'selected_references': [
            {'source': {'sha256': row['sha256']}, 'role': row['role'],
             'authority': {'controls': row['use_for'], 'must_not_control': row['do_not_transfer']},
             'subject_uses': copy.deepcopy(row.get('subject_uses', []))} for row in binding['references']]}
        inputs.require_prepared(binding, prepared, model_id='example-editor', target=TARGET)
        for key, value in (('subject_id', 'b'), ('use', 'outfit'), ('priority', 1)):
            current = copy.deepcopy(prepared)
            current['selected_references'][0]['subject_uses'][0][key] = value
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'subject uses'):
                inputs.require_prepared(binding, current, model_id='example-editor', target=TARGET)

    def test_saved_json_and_actual_recorded_host_call_are_separate_evidence(self):
        binding = self.validate()
        self.assertEqual(inputs.submission_evidence(binding, None, None), {'status': 'not-provided'})
        selector = {'path': 'request.json', 'sha256': c.sha256_file(self.root / 'request.json'),
                    'locator': 'whole', 'request_pointer': [], 'model_identity_pointer': None}
        read = lambda path: (self.root / path).read_bytes()
        with self.assertRaisesRegex(ValueError, 'not evidence of an actual host call'):
            inputs.submission_evidence(binding, selector, read)
        call = {'synthetic': True, 'call_id': 'synthetic-call-1', 'arguments': c.load(self.root / 'request.json')}
        write(self.root, 'host-call.json', call)
        selector.update(path='host-call.json', sha256=c.sha256_file(self.root / 'host-call.json'), request_pointer=['arguments'])
        self.assertEqual(inputs.submission_evidence(binding, selector, read)['status'], 'matched-recorded-call')
        call['arguments']['prompt'] += ' A different instruction.'
        write(self.root, 'host-call.json', call)
        selector['sha256'] = c.sha256_file(self.root / 'host-call.json')
        with self.assertRaisesRegex(ValueError, 'differs from the prepared request'):
            inputs.submission_evidence(binding, selector, read)

    def test_recorded_endpoint_identity_must_match_the_selected_target(self):
        request = c.load(self.root / 'request.json')
        request.pop('model')
        write(self.root, 'request.json', request)
        self.plan['external_request'].update(model_field=None, model_identity={
            'kind': 'tool', 'value': 'synthetic_tool', 'evidence': copy.deepcopy(self.plan['model']['evidence'])})
        binding = self.validate()
        call = {'synthetic': True, 'tool': 'synthetic_tool', 'arguments': request}
        write(self.root, 'host-call.json', call)
        selector = {'path': 'host-call.json', 'sha256': c.sha256_file(self.root / 'host-call.json'),
                    'locator': 'whole', 'request_pointer': ['arguments'], 'model_identity_pointer': ['tool']}
        read = lambda path: (self.root / path).read_bytes()
        self.assertEqual(inputs.submission_evidence(binding, selector, read)['status'], 'matched-recorded-call')
        call['tool'] = 'different_tool'
        write(self.root, 'host-call.json', call)
        selector['sha256'] = c.sha256_file(self.root / 'host-call.json')
        with self.assertRaisesRegex(ValueError, 'endpoint or tool differs'):
            inputs.submission_evidence(binding, selector, read)


class SemanticEditSuppliedDispatchTests(unittest.TestCase):
    """Public scoped preparation, real carrier bytes and frozen dispatcher evidence."""

    def setUp(self):
        import production_case_fixtures as cases
        import production_fixtures as fixture
        import prepare_generation_references as refs
        self.refs = refs
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.enterContext(fixture.scratch_home(self.base / 'home'))
        self.case = cases.create(self.base / 'studio', self.base / 'runtime')
        self.addCleanup(refs.configure_pack_runtime, None)
        self.root = self.case['root']
        self.model = cases.MODEL_ID
        self.plan = setup_plan(self.root)
        self.plan['external_request'] = None
        write(self.root, 'prompt.txt', PROMPT.encode('utf-8'))
        self.plan['model'].update(catalog_status='defined', catalog_model=self.model,
            target={'service': 'synthetic', 'model_identifier': 'synthetic:robot', 'operation': 'generate'})
        write(self.root, 'model-evidence.json', {'synthetic': True, 'model': self.plan['model']['target']})
        self.plan['model']['evidence']['sha256'] = c.sha256_file(self.root / 'model-evidence.json')
        write(self.root, 'image-input.json', self.plan)

    def prepare(self, **kwargs):
        return self.refs.prepare_image_input_references(self.plan, studio=self.root,
            output_dir=self.base / 'carriers', **kwargs)

    def ordinary_selections(self):
        return [{'role': row['role'], 'source': {'kind': 'supplied-file',
            'reference_id': row['id'], 'resolved_path': str(self.root / row['file'])}}
            for row in self.plan['references']]

    def test_public_cli_derives_model_files_and_exact_scopes_without_selection_json(self):
        import contextlib
        from pack_runtime_cli import PackRuntimeContext
        output = self.root / 'prepared.json'
        arguments = ['--studio', str(self.root), '--image-input-plan-file', 'image-input.json',
            '--output-dir', str(self.base / 'carriers'), '--out', str(output)]
        arguments += PackRuntimeContext(self.case['settings'], (self.case['pack'],)).command_arguments()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.refs.main(arguments), 0)
        self.refs.configure_pack_runtime(self.case['settings'])
        value = c.load(output)
        self.assertEqual(value['target_model'], self.model)
        self.assertEqual(value['image_input_binding'], inputs.validate(self.plan, self.root))
        self.assertEqual([row['source']['reference_id'] for row in value['selected_references']], ['scene', 'design'])
        for expected, actual in zip(self.plan['references'], value['selected_references']):
            self.assertEqual(actual['authority'], {'controls': expected['use_for'],
                                                   'must_not_control': expected['do_not_transfer']})
        self.assertIn('vase geometry', value['reference_preamble'])
        self.assertIn('Reference 2 means Image 2', value['reference_preamble'])

    def test_external_binding_keeps_canonical_studio_provenance_and_its_scope(self):
        import studio_reference
        import production_workflow as workflow
        import production_execution as execution
        import production_fixtures as fixture
        from sheet_artifacts_smoke_test import accepted
        sheet = self.root / 'characters/robot/sheet/sheet-data.json'
        accepted(sheet)
        source = studio_reference.current_source(self.root, 'robot', 'canon.primary')
        prepared = self.refs.prepare_references([{'role': 'identity', 'source': source}],
            model=self.model, output_dir=self.base / 'adopted-reference-carriers')
        write(self.root, 'canonical-references.json', prepared)
        external = setup_plan(self.root)
        row = prepared['selected_references'][0]
        external['references'] = [{'id': 'adopted', 'role': row['role'],
            'file': Path(source['resolved_path']).relative_to(self.root).as_posix(),
            'use_for': row['authority']['controls'], 'do_not_transfer': row['authority']['must_not_control'],
            'subject_uses': row.get('subject_uses', [])}]
        external['prepared_references'] = 'canonical-references.json'
        external['external_request']['reference_fields'] = external['external_request']['reference_fields'][:1]
        external['external_request']['reference_fields'][0]['reference'] = 'adopted'
        request = c.load(self.root / 'request.json')
        request['images'] = request['images'][:1]
        write(self.root, 'request.json', request)
        write(self.root, 'upload-evidence.json', {'synthetic': True, 'source_sha256': source['sha256'],
                                                'image_id': 'synthetic-scene'})
        external['external_request']['reference_fields'][0]['evidence']['sha256'] = c.sha256_file(self.root / 'upload-evidence.json')
        sync_external_prompt(self.root, external)
        binding = inputs.validate(external, self.root)
        selected = binding['prepared_reference_set']['selected_references'][0]
        self.assertEqual(selected['source'], source)
        self.assertEqual(selected['source']['kind'], 'studio-artifact')
        self.assertEqual(inputs.request_context(binding)['references'][0]['source']['acceptance_sha256'], source['acceptance_sha256'])
        changed = copy.deepcopy(external)
        changed['references'][0]['use_for'].append('unapproved current outfit')
        with self.assertRaisesRegex(ValueError, 'authority differs'):
            inputs.validate(changed, self.root)
        task = copy.deepcopy(self.case['task'])
        task.pop('generation')
        task.pop('recording')
        task.update(execution='external', image_input='external-input.json')
        write(self.root, 'external-input.json', external)
        write(self.root, 'external-task.json', task)
        run = workflow.prepare(self.root, 'external-task.json')['run']
        fixture.handoff(self.root, run, 'synthetic-host', 'manual')
        token = fixture.grant(self.root, run, workflow.external_intent(self.root, run, 1))
        claim = workflow.claim_external(self.root, run, 1, token)
        directory, snapshot, _, _ = workflow.load_run(self.root, run)
        archive = directory / 'image-input.references'
        proof = studio_reference.validate_source(source, active=False, source_archive=archive / 'sources')
        self.assertEqual(proof['acceptance']['artifact']['artifact_id'], source['artifact_id'])
        records = [row for row in snapshot['dependencies'] if row['path'].startswith('image-input.references/')]
        self.assertGreater(len(records), 3)
        self.assertTrue(any('/sheet/' in row['path'] for row in records))
        for record in records:
            self.assertEqual(c.object_read(directory, record['sha256']), (directory / record['path']).read_bytes())
        accepted(sheet, marker='new-adoption', color=(40, 80, 120))
        with self.assertRaisesRegex(ValueError, 'no longer matches'):
            inputs.validate(external, self.root)
        import shutil
        shutil.rmtree(sheet.parent / '.fills')
        # The recorded proof has all transitive files and needs no live source.
        studio_reference.validate_source(source, active=False, source_archive=archive / 'sources')
        write(self.root, 'external-result.png', png((80, 120, 40)))
        workflow.capture(self.root, run, 'external-result.png', 'Synthetic recovered external result.')
        write(self.root, 'external-response.json', {'synthetic': True, 'status': 'received'})
        receipt = {'claim': claim['sha256'], 'actor': fixture.ACTOR, 'outputs': 1, 'cost': None, 'final': True,
            'response': {'path': 'external-response.json', 'sha256': c.sha256_file(self.root / 'external-response.json'),
                         'locator': 'whole'}, 'reason': 'Synthetic result after the live adoption changed.'}
        write(self.root, 'external-receipt.json', receipt)
        settled = workflow.settle_external(self.root, run, 'external-receipt.json')
        self.assertTrue(settled['execution_completed'])
        self.assertEqual(settled['request_evidence']['status'], 'not-provided')
        execution.resume(self.root, run)

    def test_external_prompt_keeps_state_origin_subject_without_optional_subject_uses(self):
        from multi_subject_reference_smoke_test import selection_for
        from state_generation_smoke_test import _load_graph
        from state_protocol import finalize_artifact
        ordinary = self.refs.prepare_references([{'role': 'identity', 'source': {
            'kind': 'supplied-file', 'reference_id': 'state-face',
            'resolved_path': str(self.root / 'scene.png')}}], model=self.model,
            output_dir=self.base / 'state-source-carriers')
        selection = selection_for(_load_graph(), feature='left-ear-anchor')
        selection['selected_references'][0]['source'] = ordinary['selected_references'][0]['source']
        selection['selected_references'][0].pop('subject_uses')
        prepared = self.refs.prepare_state_reference_selection(finalize_artifact(selection), model=self.model,
            output_dir=self.base / 'state-carriers')
        write(self.root, 'state-references.json', prepared)
        external = setup_plan(self.root)
        row = prepared['selected_references'][0]
        external['references'] = [{'id': 'state-face', 'role': row['role'], 'file': 'scene.png',
            'use_for': row['authority']['controls'], 'do_not_transfer': row['authority']['must_not_control']}]
        external['prepared_references'] = 'state-references.json'
        external['external_request']['reference_fields'] = external['external_request']['reference_fields'][:1]
        external['external_request']['reference_fields'][0]['reference'] = 'state-face'
        request = c.load(self.root / 'request.json')
        request['images'] = request['images'][:1]
        write(self.root, 'request.json', request)
        prompt = sync_external_prompt(self.root, external)
        binding = inputs.validate(external, self.root)
        self.assertNotIn('subject_uses', binding['references'][0])
        self.assertEqual(inputs.request_context(binding)['references'][0]['subject_id'], 'C01')
        self.assertIn('Reference 1 means request field ["images",0]', prompt)
        self.assertIn('Apply this reference only to subject C01.', prompt)
        request = c.load(self.root / 'request.json')
        request['prompt'] = request['prompt'].replace(' Apply this reference only to subject C01.', '')
        write(self.root, 'request.json', request)
        with self.assertRaisesRegex(ValueError, 'canonical reference delivery instructions'):
            inputs.validate(external, self.root)

    def test_empty_authored_exclusions_remain_empty_only_in_the_bound_branch(self):
        from state_protocol import finalize_artifact, validate_artifact
        self.plan['references'][1]['do_not_transfer'] = []
        value = self.prepare()
        self.assertEqual(value['selected_references'][1]['authority']['must_not_control'], [])
        self.assertNotIn('Do not inherit: .', value['reference_preamble'])
        unbound = copy.deepcopy(value)
        unbound.pop('image_input_binding')
        unbound = finalize_artifact(unbound)
        self.assertFalse(validate_artifact(unbound)['ok'])
        with self.assertRaises(ValueError):
            self.refs.validate_prepared_reference_set(unbound)
        with self.assertRaisesRegex(ValueError, 'must not be empty'):
            self.refs._validate_authority(value['selected_references'][1]['authority'], 'ordinary authority')

    def test_bound_rows_reject_resealed_scope_role_order_identity_and_file_drift(self):
        value = self.prepare()
        for change in ('scope', 'role', 'order', 'identity', 'omission'):
            current = copy.deepcopy(value)
            if change == 'scope':
                current['selected_references'][1]['authority']['controls'] = ['scene lighting']
            elif change == 'role':
                current['selected_references'][1]['role'] = 'style'
            elif change == 'order':
                current['selected_references'].reverse()
            elif change == 'identity':
                current['selected_references'][1]['source']['reference_id'] = 'another-design'
            else:
                current['selected_references'].pop()
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.refs.finalize_prepared_reference_set(current, model=self.model)
        write(self.root, 'design.png', png((1, 2, 3)))
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            self.refs.validate_prepared_reference_set(value)

    def test_exact_model_external_and_state_owners_cannot_be_substituted(self):
        with self.assertRaisesRegex(ValueError, 'differs from the image input plan'):
            self.prepare(model='grok-imagine-image-2.0')
        self.plan['model']['target']['model_identifier'] = 'synthetic:other-model'
        with self.assertRaisesRegex(ValueError, 'active model offering'):
            self.prepare()
        self.plan['model']['target']['model_identifier'] = 'synthetic:robot'
        self.plan['model']['target']['operation'] = 'instruction-edit'
        with self.assertRaisesRegex(ValueError, "expected 'generate', received 'instruction-edit'"):
            self.prepare()
        self.plan['model']['target']['operation'] = 'generate'
        bound = inputs.validate(self.plan, self.root)
        with self.assertRaises(ValueError):
            self.refs.validate_prepared_references([], model=self.model,
                image_input_binding=bound, reference_selection={})
        with self.assertRaises(ValueError):
            self.refs.validate_prepared_references([], model=self.model,
                image_input_binding=bound, reference_use_plan={})
        external = setup_plan(self.root)
        external['model'].update(catalog_status='defined', catalog_model=self.model)
        with self.assertRaisesRegex(ValueError, 'external_request null'):
            self.refs.prepare_image_input_references(external, studio=self.root, output_dir=self.base / 'external')

    def test_pinned_and_concurrently_changed_files_fail_before_a_scoped_set_is_published(self):
        self.plan['references'][1]['sha256'] = c.sha256_file(self.root / 'design.png')
        write(self.root, 'design.png', png((1, 2, 3)))
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            self.prepare()
        self.plan['references'][1].pop('sha256')
        original = self.refs._preflight_selection_item
        def change_file(raw, index):
            if index == 1:
                write(self.root, 'design.png', png((3, 2, 1)))
            return original(raw, index)
        with patch.object(self.refs, '_preflight_selection_item', side_effect=change_file):
            with self.assertRaisesRegex(ValueError, 'changed during reference preparation'):
                self.prepare()

    def test_ordinary_supplied_path_keeps_conservative_authority_and_rejects_scope_injection(self):
        selected = self.ordinary_selections()
        ordinary = self.refs.prepare_references(selected, model=self.model, output_dir=self.base / 'ordinary')
        self.assertNotIn('image_input_binding', ordinary)
        self.assertEqual(ordinary['selected_references'][1]['authority'], self.refs.conservative_authority('geometry'))
        self.refs.validate_prepared_reference_set(ordinary)
        selected[1]['authority'] = {'controls': ['vase geometry'], 'must_not_control': ['scene lighting']}
        with self.assertRaisesRegex(ValueError, 'invalid shape'):
            self.refs.prepare_references(selected, model=self.model, output_dir=self.base / 'injected')
        selected = self.ordinary_selections()
        selected[1]['source']['kind'] = 'pack-artifact'
        with self.assertRaisesRegex(ValueError, 'Reference Use Plan'):
            self.refs.prepare_references(selected, model=self.model, output_dir=self.base / 'pack')

    def test_frozen_reference_bundle_keeps_binding_and_verifies_without_original_studio(self):
        import shutil
        from build_generation_payload import materialize_cli_reference_bundle
        from reference_delivery import bindings
        self.plan['references'][1]['do_not_transfer'] = []
        original = self.prepare(transport_mode='single-board')
        staging = self.base / 'portable'
        staging.mkdir()
        value, _ = materialize_cli_reference_bundle(original, model=self.model,
            source_root=self.root, staging_root=staging, companion_name='image.references')
        self.assertEqual(value['image_input_binding'], original['image_input_binding'])
        moved = self.base / 'moved'
        shutil.move(staging, moved)
        shutil.rmtree(self.root)
        self.refs.configure_pack_runtime(None)
        with patch.object(self.refs, 'resolve_model_record', side_effect=AssertionError('Frozen evidence needs no live model')):
            self.assertEqual(self.refs.validate_prepared_reference_content(value, package_root=moved), value)
        self.assertEqual([row['attachment_number'] for row in bindings('single-board', value['selected_references'],
                                                                     value['single_board'])], [1, 1])
        source = moved / 'image.references' / 'sources' / value['selected_references'][1]['source']['sha256']
        source.write_bytes(png((4, 5, 6)))
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            self.refs.validate_prepared_reference_content(value, package_root=moved)

    def object_task(self, model_name=None):
        import studio
        import production_spec
        import prompt_plot
        import prompt_retrieval
        from reading_fixtures import fixture_reading
        from render_contract_fixtures import intent
        from request_validation_fixtures import fixture_validation
        task = self.case['task']
        task['features'] = ['semantic-instruction-edit', 'instruction-edit']
        task['semantic_edit'] = 'edit-plan.json'
        task['image_input'] = 'image-input.json'
        task['sources'] += [{'id': 'source-scene', 'path': 'scene.png', 'role': 'accepted-source',
            'disposition': 'applied', 'locator': 'whole', 'reason': 'Synthetic product scene selected for this edit.'}]
        task['criteria'] += [{'id': ident, 'strength': 'hard', 'text': text, 'evidence': 'image'}
            for ident, text in [('wall', 'The wall change is visible.'), ('geometry', 'The vase geometry remains fixed.')]]
        spec = production_spec.load(production_spec.TEMPLATE)
        spec.update(source_brief=PROMPT, target_model=model_name or self.model, image_promise=PROMPT,
                    render_intent=intent(PROMPT, 'instruction-edit'))
        spec['scene']['environment'] = 'A ceramic vase on a cafe table with a painted wall behind it.'
        spec['constraints']['construction_invariants'] = ['Preserve the vase geometry and source framing.']
        write(self.root, 'spec.json', spec)
        plot = c.load(self.root / 'plot.json')
        plot['story'] = [{'id': 's1', 'beat': 'A ceramic vase stands against a repainted cafe wall.', 'visibility': 'visible'}]
        plot['derived'] = [{'kind': kind, 'statement': statement, 'from': ['s1']} for kind, statement in (
            ('shows', 'one ceramic vase'), ('placement', 'on the existing cafe table'),
            ('composition', 'retain the source framing'), ('must_preserve', 'retain the vase geometry'))]
        plot['derived'].append({'kind': 'free', 'statement': 'The new wall color is the selected change.'})
        plot['approved']['content_sha256'] = prompt_plot.content_sha256(plot)
        write(self.root, 'plot.json', plot)
        retrieval = c.load(self.root / 'retrieval.json')
        retrieval['elements'][0]['composed_wording'] = PROMPT
        write(self.root, 'retrieval.json', prompt_retrieval.settle_retrieval_record(retrieval, prompt=PROMPT, plot=plot))
        write(self.root, 'validation.json', fixture_validation(self.root, self.model,
            reference_mode='prompt-prefix', service='synthetic'))
        write(self.root, 'references.json', self.prepare())
        task['generation'].update(references='references.json', continuity={})
        studio.add_character(self.root, 'product-scene', 'general')
        task['recording'].update(character='product-scene', slot='candidate', subject_map={}, sheet_panel=False)
        write(self.root, 'reading.json', fixture_reading(route=task['route'], features=task['features'],
                                                        studio=self.root, ledger=self.root / 'work/reads.jsonl'))
        write(self.root, 'task.json', task)
        return task

    def test_object_only_dispatcher_prepares_exact_scopes_and_recovers_frozen_evidence(self):
        import production_workflow as workflow
        import production_execution as execution
        import execution_lifecycle as accounting
        import transport_synthetic
        from production_compiler import check_task
        from test_production_execution import decisions
        from verify_generation_payload import verify_content
        self.object_task()
        check = check_task(self.root, 'task.json')
        self.assertTrue(check['ok'], check)
        self.assertIn('vase geometry', check['request_preview']['prompt'])
        run = workflow.prepare(self.root, 'task.json')['run']
        directory, prepared, consumer, _ = workflow.load_run(self.root, run)
        package = c.load(directory / 'package.json')
        self.assertEqual(package['production_spec']['subjects'], [])
        self.assertEqual(package['visual_continuity']['subjects'], {})
        self.assertEqual(package['prepared_reference_set']['image_input_binding'], consumer['image_input'])
        result = execution.execute(self.root, run, decisions_file=decisions(self.root, run))
        self.assertEqual(result['runs'][0]['capture'], 'complete')
        for name in ('scene.png', 'design.png', 'edit-plan.json', 'image-input.json', 'model-evidence.json'):
            (self.root / name).unlink()
        verify_content(package, package_root=directory)
        before = accounting.summary(self.root)
        with patch.object(transport_synthetic, 'send', side_effect=AssertionError('Recovery must not send again')):
            execution.resume(self.root, run)
        self.assertEqual(accounting.summary(self.root), before)
        self.assertEqual((before['submissions'], before['captured_outputs']), (1, 1))

    def test_alias_declared_target_still_seals_the_request(self):
        import production_workflow as workflow
        import production_execution as execution
        from production_compiler import check_task
        from test_production_execution import decisions
        self.object_task(model_name='synthetic robot fixture')
        check = check_task(self.root, 'task.json')
        self.assertTrue(check['ok'], check)
        run = workflow.prepare(self.root, 'task.json')['run']
        directory = workflow.load_run(self.root, run)[0]
        package = c.load(directory / 'package.json')
        self.assertEqual(package['model'], 'synthetic robot fixture')
        result = execution.execute(self.root, run, decisions_file=decisions(self.root, run))
        self.assertEqual(result['runs'][0]['capture'], 'complete')

    def test_task_cannot_change_or_drop_the_plan_that_owns_prepared_scopes(self):
        from production_compiler import check_task
        task = self.object_task()
        self.plan['references'][1]['use_for'] = ['different geometry scope']
        write(self.root, 'image-input.json', self.plan)
        check = check_task(self.root, 'task.json')
        self.assertFalse(check['ok'])
        self.assertIn('prepared image input binding differs', str(check))
        task.pop('semantic_edit')
        task.pop('image_input')
        task['features'].remove('semantic-instruction-edit')
        from reading_fixtures import fixture_reading
        write(self.root, 'reading.json', fixture_reading(route=task['route'], features=task['features'],
                                                        studio=self.root, ledger=self.root / 'work/reads.jsonl'))
        write(self.root, 'task.json', task)
        check = check_task(self.root, 'task.json')
        self.assertFalse(check['ok'])
        self.assertIn('scoped image references require', str(check))


class SemanticEditProductionTests(unittest.TestCase):
    def setUp(self):
        import production_fixtures as fixture
        import work_ledger as ledger
        self.fixture = fixture
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.enterContext(fixture.scratch_home(base / 'home'))
        self.root = base / 'studio'
        self.plan = setup_plan(self.root)
        entry = ledger.begin(self.root, 'Synthetic product background editing', ['prepare', 'review'])
        self.task = {'task_id': entry['task_id'], 'route': 'generation',
                     'features': ['semantic-instruction-edit', 'instruction-edit'],
                     'sources': [{'id': 'source-scene', 'path': 'scene.png', 'role': 'accepted-source',
                                  'disposition': 'applied', 'locator': 'whole', 'reason': 'Synthetic product scene.'},
                                 {'id': 'product-design', 'path': 'design.png', 'role': 'reference-images',
                                  'disposition': 'applied', 'locator': 'whole', 'reason': 'Synthetic geometry reference.'}],
                     'delivery': {'path': 'prompt.txt', 'transport': 'authored-rendition',
                                  'translation_notes': 'Synthetic instruction uses explicit reference roles.'},
                     'criteria': [{'id': 'wall', 'strength': 'hard', 'text': 'Requested wall edit is visible.'},
                                  {'id': 'geometry', 'strength': 'hard', 'text': 'Product geometry remains stable.'}],
                     'world_views': [], 'semantic_edit': 'edit-plan.json', 'image_input': 'image-input.json'}
        fixture.task(self.root, self.task, artifact='image', execution='external')
        for row in self.task['criteria']:
            row['evidence'] = 'image'
        write(self.root, 'task.json', self.task)

    def prepared(self):
        import production_workflow as workflow
        result = workflow.prepare(self.root, 'task.json')
        run = result['run']
        self.fixture.handoff(self.root, run, 'synthetic-host', 'manual')
        token = self.fixture.grant(self.root, run, workflow.external_intent(self.root, run, 1))
        return run, token

    def update_authority(self, authority):
        import production_store as store
        prior = store.authority_record(self.root, self.task['task_id'])
        write(self.root, 'amended-authority.json', authority)
        store.import_authority(self.root, 'amended-authority.json', expected=prior['sha256'])

    def new_scene_task(self):
        import production_spec
        from render_contract_fixtures import intent
        from reading_fixtures import fixture_reading
        self.task.pop('semantic_edit')
        self.task['features'] = []
        self.task['sources'][0]['role'] = 'reference-images'
        for index, row in enumerate(self.plan['references']):
            row['role'] = 'identity'
            row['subject_uses'] = [{'subject_id': 'a' if index == 0 else 'b', 'use': 'identity', 'priority': 0}]
        spec = production_spec.draft(model=self.plan['model']['requested'], brief='Synthetic scene using two source identities.',
            subject='a', kind='robot', render_intent=intent(PROMPT, 'reference-guided'))
        second = copy.deepcopy(spec['subjects'][0])
        second['id'] = 'b'
        spec['subjects'].append(second)
        write(self.root, 'external-spec.json', spec)
        self.task['sources'].append({'id': 'specification', 'path': 'external-spec.json', 'role': 'production-spec',
            'disposition': 'applied', 'locator': 'whole', 'reason': 'Explicit synthetic new scene specification.'})
        write(self.root, 'reading.json', fixture_reading(route=self.task['route'], features=[], studio=self.root,
            ledger=self.root / 'work/reads.jsonl'))
        self.task['route_reading'] = 'reading.json'
        sync_external_prompt(self.root, self.plan)
        write(self.root, 'image-input.json', self.plan)
        write(self.root, 'task.json', self.task)
        return spec

    def test_ordinary_external_reference_generation_uses_the_shared_binding(self):
        import production_workflow as workflow
        from production_compiler import check_task
        self.new_scene_task()
        check = check_task(self.root, 'task.json')
        self.assertTrue(check['ok'], check)
        run, token = self.prepared()
        consumer = workflow.load_run(self.root, run)[2]
        self.assertNotIn('semantic_edit', consumer)
        self.assertEqual([row['subject_uses'][0]['subject_id'] for row in consumer['image_input']['references']], ['a', 'b'])
        claim = workflow.claim_external(self.root, run, 1, token)
        self.assertEqual(claim['data']['image_input_sha256'], consumer['image_input']['binding_sha256'])

    def test_text_only_external_check_prepare_and_settlement_keep_exact_request(self):
        import production_workflow as workflow
        from production_compiler import check_task
        from reading_fixtures import fixture_reading
        self.plan = setup_text_only_plan(self.root)
        self.task.pop('semantic_edit')
        self.task['features'] = []
        self.task['sources'] = []
        self.task['criteria'] = [{'id': 'vase', 'strength': 'hard', 'evidence': 'image',
                                 'text': 'Inspect the vase and table in the returned image.'}]
        self.task['delivery']['translation_notes'] = 'Exact synthetic text-only image request.'
        write(self.root, 'reading.json', fixture_reading(route=self.task['route'], features=[], studio=self.root,
            ledger=self.root / 'work/reads.jsonl'))
        self.task['route_reading'] = 'reading.json'
        write(self.root, 'task.json', self.task)
        request = c.load(self.root / 'request.json')
        checked = check_task(self.root, 'task.json')
        self.assertTrue(checked['ok'], checked)
        self.assertEqual(checked['request_preview'], request)
        run, token = self.prepared()
        _, snapshot, consumer, _ = workflow.load_run(self.root, run)
        self.assertNotIn('semantic_edit', consumer)
        binding = consumer['image_input']
        inputs.validate_binding(binding)
        self.assertEqual(binding['references'], [])
        self.assertEqual(binding['external_request']['reference_fields'], [])
        self.assertEqual(binding['external_request']['request'], request)
        dependencies = {row['path'] for row in snapshot['dependencies']}
        self.assertTrue({'image-input.json', 'model-evidence.json', 'request.json', 'request-schema.json'} <= dependencies)
        self.assertTrue({'scene.png', 'design.png', 'upload-evidence.json'}.isdisjoint(dependencies))
        claim = workflow.claim_external(self.root, run, 1, token)
        self.assertEqual(claim['data']['image_input_sha256'], binding['binding_sha256'])
        self.assertEqual(claim['data']['external_request_sha256'], c.sha256_file(self.root / 'request.json'))
        self.assertEqual(claim['data']['target'], self.plan['model']['target'])
        write(self.root, 'output.png', png((10, 60, 100)))
        workflow.capture(self.root, run, 'output.png', 'Synthetic local image for exact-call verification.')
        write(self.root, 'host-response.json', {'synthetic': True, 'status': 'received'})
        write(self.root, 'host-call.json', {'synthetic': True, 'call_id': 'synthetic-text-call', 'arguments': request})
        receipt = {'claim': claim['sha256'], 'actor': self.fixture.ACTOR, 'outputs': 1, 'cost': None, 'final': True,
            'response': {'path': 'host-response.json', 'sha256': c.sha256_file(self.root / 'host-response.json'), 'locator': 'whole'},
            'submission': {'path': 'host-call.json', 'sha256': c.sha256_file(self.root / 'host-call.json'),
                'locator': 'synthetic actual call', 'request_pointer': ['arguments'], 'model_identity_pointer': None},
            'reason': 'Synthetic host-call and result records.'}
        write(self.root, 'receipt.json', receipt)
        result = workflow.settle_external(self.root, run, 'receipt.json')
        self.assertTrue(result['execution_completed'])
        self.assertEqual(result['request_evidence']['status'], 'matched-recorded-call')

    def test_check_and_prepare_reject_subject_scope_saved_only_in_metadata(self):
        import production_workflow as workflow
        from production_compiler import check_task
        from production_diagnostics import CompilationError
        self.new_scene_task()
        request = c.load(self.root / 'request.json')
        request['prompt'] = PROMPT
        write(self.root, 'request.json', request)
        write(self.root, 'prompt.txt', PROMPT.encode('utf-8'))
        check = check_task(self.root, 'task.json')
        self.assertFalse(check['ok'], check)
        self.assertIn('canonical reference delivery instructions', str(check))
        with self.assertRaises(CompilationError) as caught:
            workflow.prepare(self.root, 'task.json')
        self.assertIn('canonical reference delivery instructions', str(caught.exception.report))

    def test_external_specification_and_render_checks_are_not_dispatcher_only(self):
        from production_compiler import check_task
        spec = self.new_scene_task()
        for change in ('unknown-subject', 'model', 'render-expression', 'invalid-spec'):
            current = copy.deepcopy(spec)
            if change == 'unknown-subject':
                current['subjects'][1]['id'] = 'not-b'
            elif change == 'model':
                current['target_model'] = 'different-model'
            elif change == 'render-expression':
                current['render_intent']['prompt_expression'] = 'An instruction absent from delivery.'
            else:
                current.pop('scene')
            write(self.root, 'external-spec.json', current)
            with self.subTest(change=change):
                check = check_task(self.root, 'task.json')
                self.assertFalse(check['ok'], check)
                self.assertIn('external-image-contract', str(check))

    def test_external_shared_generation_inputs_need_no_dispatcher_parameters(self):
        import production_workflow as workflow
        from production_compiler import check_task
        self.new_scene_task()
        self.task['sources'] = [row for row in self.task['sources'] if row['role'] != 'production-spec']
        write(self.root, 'state-graphs.json', [])
        self.task['generation'] = {'production_spec': 'external-spec.json', 'state_graphs': 'state-graphs.json'}
        write(self.root, 'task.json', self.task)
        check = check_task(self.root, 'task.json')
        self.assertTrue(check['ok'], check)
        self.assertEqual(check['request_preview'], c.load(self.root / 'request.json'))
        run, token = self.prepared()
        prepared = workflow.load_run(self.root, run)[1]
        self.assertIn('external-spec.json', [row['path'] for row in prepared['dependencies']])
        self.assertIn('state-graphs.json', [row['path'] for row in prepared['dependencies']])
        workflow.claim_external(self.root, run, 1, token)

    def test_external_settlement_records_actual_call_comparison(self):
        import production_workflow as workflow
        self.new_scene_task()
        run, token = self.prepared()
        claim = workflow.claim_external(self.root, run, 1, token)
        write(self.root, 'output.png', png((10, 60, 100)))
        workflow.capture(self.root, run, 'output.png', 'Synthetic local result, no quality claim.')
        write(self.root, 'host-response.json', {'synthetic': True, 'status': 'received'})
        write(self.root, 'host-call.json', {'synthetic': True, 'call_id': 'synthetic-call-1',
            'arguments': c.load(self.root / 'request.json')})
        receipt = {'claim': claim['sha256'], 'actor': self.fixture.ACTOR, 'outputs': 1, 'cost': None, 'final': True,
            'response': {'path': 'host-response.json', 'sha256': c.sha256_file(self.root / 'host-response.json'), 'locator': 'whole'},
            'submission': {'path': 'host-call.json', 'sha256': c.sha256_file(self.root / 'host-call.json'),
                'locator': 'synthetic actual call', 'request_pointer': ['arguments'], 'model_identity_pointer': None},
            'reason': 'Synthetic host-call and result records.'}
        write(self.root, 'receipt.json', receipt)
        result = workflow.settle_external(self.root, run, 'receipt.json')
        self.assertTrue(result['execution_completed'])
        self.assertEqual(result['request_evidence']['status'], 'matched-recorded-call')

    def test_one_source_edit_needs_no_auxiliary_image(self):
        import production_workflow as workflow
        self.plan['references'] = self.plan['references'][:1]
        edit = c.load(self.root / 'edit-plan.json')
        edit['edit']['required_reference_roles'] = ['scene']
        write(self.root, 'edit-plan.json', edit)
        self.plan['external_request']['reference_fields'] = self.plan['external_request']['reference_fields'][:1]
        request = c.load(self.root / 'request.json')
        request['images'] = request['images'][:1]
        self.task['sources'] = self.task['sources'][:1]
        write(self.root, 'request.json', request)
        sync_external_prompt(self.root, self.plan)
        write(self.root, 'image-input.json', self.plan)
        write(self.root, 'task.json', self.task)
        (self.root / 'design.png').unlink()
        run, token = self.prepared()
        consumer = workflow.load_run(self.root, run)[2]
        self.assertEqual(len(consumer['image_input']['references']), 1)
        self.assertEqual(consumer['image_input']['external_request']['request']['images'], ['synthetic-scene'])
        self.assertEqual(workflow.claim_external(self.root, run, 1, token)['data']['count'], 1)

    def test_scene_must_match_the_applied_task_source(self):
        self.task['sources'][0]['path'] = 'design.png'
        with self.assertRaisesRegex(ValueError, 'applied accepted-source'):
            edits.task_binding(self.root, self.task, lambda base, path: (base / path).read_bytes())

    def test_external_readiness_requires_exact_current_submission_authority(self):
        import production_workflow as workflow
        import execution_lifecycle as lifecycle
        run = workflow.prepare(self.root, 'task.json')['run']
        directory = workflow.load_run(self.root, run)[0]
        self.assertEqual(c.load(directory / 'execution-plan.json')['readiness']['state'], 'authorization_required')

        def status_without_events():
            before = workflow.load_run(self.root, run)[3]
            result = workflow.status(self.root, run)['runs'][0]
            self.assertEqual(workflow.load_run(self.root, run)[3], before)
            self.assertEqual(result['submission'], 'unclaimed')
            self.assertFalse(result['send_started'])
            return result

        initial = status_without_events()
        self.assertEqual(initial['readiness'], 'authorization_required')
        self.assertEqual(initial['next_action']['command'], 'handoff')
        self.fixture.handoff(self.root, run, 'synthetic-host', 'manual')
        handed = status_without_events()
        self.assertEqual(handed['readiness'], 'authorization_required')
        self.assertEqual(handed['next_action']['command'], 'claim-external')
        self.fixture.grant(self.root, run, workflow.external_intent(self.root, run, 1))
        self.assertEqual(status_without_events()['readiness'], 'ready')

        authority = c.load(self.root / self.task['authority'])
        authority['grants'][0]['submission_validation_modes'] = ['target-schema']
        self.update_authority(authority)
        narrowed = status_without_events()
        self.assertEqual(narrowed['readiness'], 'authorization_required')
        self.assertIn('GRANT_SCOPE_EXCEEDED', {item['code'] for item in narrowed['readiness_diagnostics']})
        self.assertEqual(lifecycle.summary(self.root)['submissions'], 0)

    def test_bounded_probe_uses_actual_validation_mode_authority(self):
        import production_workflow as workflow
        import execution_lifecycle as lifecycle
        from production_diagnostics import ProductionError
        authority = c.load(self.root / self.task['authority'])
        authority['grants'][0]['submission_validation_modes'] = ['target-schema']
        write(self.root, self.task['authority'], authority)
        run = workflow.prepare(self.root, 'task.json')['run']
        self.fixture.handoff(self.root, run, 'synthetic-host', 'manual')
        intent = workflow.external_intent(self.root, run, 1)
        with self.assertRaises(ProductionError) as caught:
            self.fixture.grant(self.root, run, intent)
        self.assertEqual(caught.exception.diagnostic.code, 'GRANT_SCOPE_EXCEEDED')
        self.assertEqual(lifecycle.summary(self.root)['submissions'], 0)
        authority['grants'][0]['submission_validation_modes'] = ['bounded-probe']
        self.update_authority(authority)
        token = self.fixture.grant(self.root, run, intent)
        self.assertEqual(workflow.claim_external(self.root, run, 1, token)['data']['count'], 1)

    def test_changed_validation_mode_authority_blocks_a_prepared_claim(self):
        import production_workflow as workflow
        import execution_lifecycle as lifecycle
        from production_diagnostics import ProductionError
        run, token = self.prepared()
        authority = c.load(self.root / self.task['authority'])
        authority['grants'][0]['submission_validation_modes'] = ['target-schema']
        self.update_authority(authority)
        with self.assertRaises(ProductionError) as caught:
            workflow.claim_external(self.root, run, 1, token)
        self.assertEqual(caught.exception.diagnostic.code, 'GRANT_SCOPE_EXCEEDED')
        self.assertEqual(lifecycle.summary(self.root)['submissions'], 0)

    def test_external_request_cannot_use_an_unassessed_dispatcher_scope(self):
        import production_workflow as workflow
        import execution_lifecycle as lifecycle
        from production_diagnostics import ProductionError
        authority = c.load(self.root / self.task['authority'])
        authority['grants'][0]['request_scope'] = {
            'plan': {'path': 'model-evidence.json', 'sha256': c.sha256_file(self.root / 'model-evidence.json'),
                     'locator': 'whole synthetic declaration'},
            'cases': [{'id': 'synthetic-dispatcher-case', 'productions': [self.task['production_id']],
                       'targets': [{'target': TARGET, 'execution': {key: '0' * 64 for key in (
                           'service_execution_sha256', 'offering_contract_sha256', 'transport_sha256')}}],
                       'fixed': {}, 'variations': {}, 'review_criteria': []}]}
        write(self.root, self.task['authority'], authority)
        run = workflow.prepare(self.root, 'task.json')['run']
        self.fixture.handoff(self.root, run, 'synthetic-host', 'manual')
        with self.assertRaises(ProductionError) as caught:
            self.fixture.grant(self.root, run, workflow.external_intent(self.root, run, 1))
        self.assertEqual(caught.exception.diagnostic.code, 'GRANT_SCOPE_EXCEEDED')
        self.assertIn('dispatcher request scope', str(caught.exception))
        self.assertEqual(lifecycle.summary(self.root)['submissions'], 0)

    def test_check_prepare_external_capture_and_resume_keep_exact_input_and_result(self):
        import production_workflow as workflow
        import production_execution as execution
        import execution_lifecycle as lifecycle
        from production_compiler import check_task
        result = check_task(self.root, 'task.json')
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['request_preview'], c.load(self.root / 'request.json'))
        run, token = self.prepared()
        _, prepared, consumer, _ = workflow.load_run(self.root, run)
        bound = consumer['image_input']
        self.assertEqual(bound['references'][1]['sha256'], c.sha256_file(self.root / 'design.png'))
        self.assertIn('design.png', [x['path'] for x in prepared['dependencies']])
        claim = workflow.claim_external(self.root, run, 1, token)
        self.assertEqual(claim['data']['target'], TARGET)
        self.assertEqual(claim['data']['external_request_sha256'], c.sha256_file(self.root / 'request.json'))
        self.assertEqual(workflow.claim_external(self.root, run, 1, token)['sha256'], claim['sha256'])
        output = png((40, 120, 70))
        write(self.root, 'output.png', output)
        (self.root / 'scene.png').unlink()
        candidate = workflow.capture(self.root, run, 'output.png', 'Synthetic returned pixels; no model-quality claim.')
        self.assertEqual(workflow.capture(self.root, run, 'output.png', 'Repeated synthetic receipt.')['sha256'], candidate['sha256'])
        write(self.root, 'host-response.json', {'synthetic': True, 'output_sha256': c.digest(output), 'cost': '0'})
        receipt = {'claim': claim['sha256'], 'actor': self.fixture.ACTOR, 'outputs': 1,
                   'response': {'path': 'host-response.json', 'sha256': c.sha256_file(self.root / 'host-response.json'), 'locator': 'whole'},
                   'cost': {'currency': 'USD', 'amount': '0'}, 'final': True,
                   'reason': 'Synthetic external host receipt of one local PNG.'}
        write(self.root, 'receipt.json', receipt)
        self.assertTrue(workflow.settle_external(self.root, run, 'receipt.json')['execution_completed'])
        before = lifecycle.summary(self.root)
        execution.resume(self.root, run)
        self.assertEqual(lifecycle.summary(self.root), before)
        self.assertEqual((before['submissions'], before['captured_outputs']), (1, 1))
        review = workflow.draft_review(self.root, run, candidate['sha256'])
        self.assertTrue(all(x['verdict'] == 'not-assessed' for x in review['checks']))

    def test_changed_required_reference_blocks_claim_before_any_send(self):
        import production_workflow as workflow
        import execution_lifecycle as lifecycle
        from production_diagnostics import ProductionError
        run, token = self.prepared()
        write(self.root, 'design.png', png((1, 2, 3)))
        with self.assertRaises(ProductionError) as caught:
            workflow.claim_external(self.root, run, 1, token)
        self.assertEqual(caught.exception.diagnostic.code, 'SOURCE_CHANGED')
        self.assertEqual(lifecycle.summary(self.root)['submissions'], 0)

    def test_claim_count_and_delivery_prompt_must_match_exact_request(self):
        import production_workflow as workflow
        run, _ = self.prepared()
        with self.assertRaisesRegex(ValueError, 'claim count'):
            workflow.external_intent(self.root, run, 2)
        other = Path(self.temp.name) / 'other'
        plan = setup_plan(other)
        task = copy.deepcopy(self.task)
        write(other, 'prompt.txt', b'Different instruction')
        with self.assertRaisesRegex(ValueError, 'production delivery'):
            edits.task_binding(other, task, lambda base, path: (base / path).read_bytes())


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
