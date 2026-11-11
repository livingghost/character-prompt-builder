#!/usr/bin/env python3
"""Exercise reference editing through the authored choices and actual builders."""
from __future__ import annotations

import copy
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from PIL import Image
import catalog_cli
import execution_contract as c
import pack_manager
import prepare_generation_references as refs
import production_reference_inputs as inputs
from production_case_fixtures import create_pack, MODEL_ID, PACK_ID, write
from production_fixtures import scratch_home
from reference_delivery import bindings


class ReferenceInputTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='cpb-reference-inputs-')
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name)
        self.root = self.work / 'studio'
        self.root.mkdir()
        self.enterContext(scratch_home(self.work / 'home'))
        self.addCleanup(catalog_cli.configure_pack_runtime, None)
        self.pack = create_pack(self.work / 'model-pack')
        self.settings = pack_manager.PackSettings(roots=(self.pack,), state_file=self.work / 'state.json',
            cache_dir=self.work / 'cache', managed_root=self.work / 'managed',
            quarantine_root=self.work / 'managed/.quarantine')
        self.activate()
        for index, color in enumerate(((60, 90, 120), (150, 80, 40), (50, 150, 70))):
            with Image.new('RGB', (40 + index * 8, 24), color) as image:
                image.save(self.root / f'image-{index}.png')

    def activate(self, extra_pack=None, extra_id=None):
        roots = [str(self.pack)] + ([str(extra_pack)] if extra_pack is not None else [])
        identifiers = [PACK_ID] + ([extra_id] if extra_id is not None else [])
        pack_manager.save_state(self.settings.state_file, {'pack_roots': roots,
            'enabled_packs': identifiers, 'disabled_packs': [], 'pack_order': identifiers})
        catalog_cli.configure_pack_runtime(None)
        catalog_cli.configure_pack_runtime(self.settings)

    def direct(self, number, subject='A'):
        return {'role': 'identity', 'source': {'kind': 'supplied-file',
            'reference_id': f'image-{number}', 'resolved_path': f'image-{number}.png'},
            'subject_uses': [{'subject_id': subject, 'use': 'identity', 'priority': number}]}

    def build(self, choices, name):
        return inputs.build(choices, model=MODEL_ID, root=self.root, output_dir=self.root / name)

    def external_plan(self, prepared, directory):
        import image_input
        from semantic_edit_plan_smoke_test import setup_plan
        plan = setup_plan(self.root)
        selected, fields, uploaded = [], [], []
        for index, row in enumerate(prepared['selected_references']):
            identifier = f'external-{index}'
            board = prepared['transport_mode'] == 'single-board'
            carrier = prepared['single_board'] if board else row['transport']
            value = 'synthetic-board' if board else 'synthetic-' + identifier
            path = f'upload-{index}.json'
            raw = c.encoded({'synthetic': True, 'image_id': value, 'carrier_sha256': carrier['sha256']})
            (self.root / path).write_bytes(raw)
            reference = {'id': identifier, 'role': row['role'],
                'file': f"{directory}/references/sources/{row['source']['sha256']}",
                'sha256': row['source']['sha256'], 'use_for': copy.deepcopy(row['authority']['controls']),
                'do_not_transfer': copy.deepcopy(row['authority']['must_not_control'])}
            if 'subject_uses' in row:
                reference['subject_uses'] = copy.deepcopy(row['subject_uses'])
            selected.append(reference)
            fields.append({'reference': identifier, 'field': ['images', 0 if board else index],
                'value': value, 'evidence': {'path': path, 'sha256': c.digest(raw),
                    'locator': 'whole synthetic upload record'}})
            if value not in uploaded:
                uploaded.append(value)
        plan.update(references=selected, prepared_references=directory + '/prepared-reference-set.json')
        plan['external_request']['reference_fields'] = fields
        request = c.load(self.root / 'request.json')
        request['images'] = uploaded
        (self.root / 'request.json').write_bytes(c.encoded(request))
        image_input.validate(plan, self.root)
        return plan

    def external_build(self, selection, name):
        return inputs.build_external(selection, root=self.root, output_dir=self.root / name,
                                     publication_dir=name)

    def test_add_remove_reorder_derives_attachment_numbers_and_keeps_scopes(self):
        choices = inputs.draft(None, package_root=self.root)
        choices['additional_references'] = [self.direct(0)]
        first = self.build(choices, 'first')
        edited = inputs.draft(first, package_root=self.root / 'first')
        edited['additional_references'].append(self.direct(1, subject='B'))
        added = self.build(edited, 'added')
        self.assertEqual([row['attachment_number'] for row in bindings('multi-image', added['selected_references'])], [1, 2])
        selected = inputs.draft(added, package_root=self.root / 'added')
        selected['additional_references'].reverse()
        selected['additional_references'].pop()
        removed = self.build(selected, 'removed')
        row = removed['selected_references'][0]
        self.assertEqual(row['source']['reference_id'], 'image-1')
        self.assertEqual(row['subject_uses'], self.direct(1, subject='B')['subject_uses'])
        self.assertEqual(row['authority'], added['selected_references'][1]['authority'])
        self.assertEqual(bindings('multi-image', [row])[0]['attachment_number'], 1)
        for carrier in refs.host_reference_transports(removed, package_root=self.root / 'removed'):
            self.assertTrue(Path(carrier['resolved_path']).is_file())

    def test_remove_every_direct_reference_builds_the_canonical_empty_set(self):
        choices = inputs.draft(None, package_root=self.root)
        choices['additional_references'] = [self.direct(0)]
        original = self.build(choices, 'original')
        edited = inputs.draft(original, package_root=self.root / 'original')
        edited['additional_references'].clear()
        result = self.build(edited, 'empty')
        self.assertEqual(result['transport_mode'], 'none')
        self.assertEqual(result['selected_references'], [])
        self.assertIsNotNone(result['zero_reference_reason'])

    def test_board_cells_follow_current_order_without_editing_panel_records(self):
        choices = inputs.draft(None, package_root=self.root)
        choices.update(transport_mode='single-board', max_side=128)
        choices['additional_references'] = [self.direct(0), self.direct(1), self.direct(2)]
        first = self.build(choices, 'board-three')
        edited = inputs.draft(first, package_root=self.root / 'board-three')
        self.assertEqual(edited['max_side'], 128)
        edited['additional_references'] = edited['additional_references'][1:]
        second = self.build(edited, 'board-two')
        self.assertEqual(len(second['single_board']['panels']), 2)
        self.assertEqual(second['single_board']['panels'][0]['source_sha256'], first['selected_references'][1]['source']['sha256'])
        self.assertNotEqual(second['single_board']['sha256'], first['single_board']['sha256'])
        projected = bindings('single-board', second['selected_references'], second['single_board'])
        self.assertEqual([row['attachment_number'] for row in projected], [1, 1])
        self.assertEqual([row['region_pixels'] for row in projected], [row['box'] for row in second['single_board']['panels']])

    def test_saved_source_pins_refuse_changed_bytes_and_publish_nothing(self):
        choices = inputs.draft(None, package_root=self.root)
        choices['additional_references'] = [self.direct(0)]
        first = self.build(choices, 'first')
        edited = inputs.draft(first, package_root=self.root / 'first')
        (self.root / 'image-0.png').write_bytes((self.root / 'image-1.png').read_bytes())
        with self.assertRaisesRegex(ValueError, 'retained reference source changed'):
            self.build(edited, 'changed')
        self.assertFalse((self.root / 'changed').exists())

    def test_selecting_another_file_measures_it_without_editing_the_old_hash(self):
        choices = inputs.draft(None, package_root=self.root)
        choices['additional_references'] = [self.direct(0)]
        original = self.build(choices, 'original')
        edited = inputs.draft(original, package_root=self.root / 'original')
        selected = edited['additional_references'][0]
        self.assertNotIn('sha256', selected['source'])
        self.assertNotIn('media_type', selected['source'])
        self.assertEqual(edited['source_files'][str((self.root / 'image-0.png').resolve())]['sha256'],
                         original['selected_references'][0]['source']['sha256'])
        selected['source']['resolved_path'] = 'image-1.png'
        result = self.build(edited, 'replaced')
        row = result['selected_references'][0]
        self.assertEqual(row['source']['sha256'], c.sha256_file(self.root / 'image-1.png'))
        self.assertEqual(row['source']['reference_id'], original['selected_references'][0]['source']['reference_id'])
        self.assertEqual(row['authority'], original['selected_references'][0]['authority'])
        self.assertEqual(row['subject_uses'], original['selected_references'][0]['subject_uses'])

    def test_external_native_scopes_keep_source_identity_and_allow_file_replacement(self):
        from model_prompt_input_fixtures import prompt_input
        raw = (self.pack / 'records/models.json').read_bytes()
        (self.root / 'model.json').write_bytes(raw)
        choices = inputs.draft(None, package_root=self.root)
        choices['image_input'] = {'artifact_type': 'image-input-plan', 'model': {
            'requested': MODEL_ID, 'catalog_status': 'defined', 'catalog_model': MODEL_ID,
            'prompt_input': prompt_input('descriptive'),
            'target': {'service': 'synthetic', 'model_identifier': 'synthetic:robot', 'operation': 'generate'},
            'evidence': {'path': 'model.json', 'sha256': c.digest(raw), 'locator': 'whole synthetic model record'}},
            'references': [{'id': 'native-scene', 'role': 'scene', 'file': 'image-0.png',
                'use_for': ['the selected camera framing'], 'do_not_transfer': ['surface color'],
                'subject_uses': [{'subject_id': 'A', 'use': 'pose-camera', 'priority': 0}]}],
            'external_request': None}
        prepared = self.build(choices, 'native')
        plan = self.external_plan(prepared, 'native')
        edited = inputs.draft_external(plan, prepared, package_root=self.root / 'native', root=self.root)
        selected = edited['choices']['image_input']['references'][0]
        self.assertEqual((selected['id'], selected['delivery_id']), ('native-scene', 'external-0'))
        self.assertNotIn('sha256', selected)
        selected['file'] = 'image-1.png'
        result = self.external_build(edited, 'native-replaced')
        self.assertEqual(result['references'][0]['id'], 'external-0')
        self.assertEqual(result['references'][0]['use_for'], plan['references'][0]['use_for'])
        self.assertEqual(result['references'][0]['do_not_transfer'], plan['references'][0]['do_not_transfer'])
        source = result['prepared']['selected_references'][0]['source']
        self.assertEqual(source['reference_id'], 'native-scene')
        self.assertEqual(source['sha256'], c.sha256_file(self.root / 'image-1.png'))
        self.assertFalse((self.root / 'native-replaced/image-input.json').exists())

    def test_external_board_rebuild_exposes_new_carrier_bytes_and_retains_ids(self):
        choices = inputs.draft(None, package_root=self.root)
        choices.update(transport_mode='single-board', max_side=128)
        choices['additional_references'] = [self.direct(0), self.direct(1), self.direct(2)]
        prepared = self.build(choices, 'board')
        plan = self.external_plan(prepared, 'board')
        edited = inputs.draft_external(plan, prepared, package_root=self.root / 'board', root=self.root)
        self.assertEqual(edited['target_model'], MODEL_ID)
        self.assertIsNone(plan['model']['catalog_model'])
        edited['choices']['additional_references'].pop(0)
        result = self.external_build(edited, 'board-new')
        self.assertEqual([row['id'] for row in result['references']], ['external-1', 'external-2'])
        self.assertEqual([row['reference'] for row in result['carriers']], ['external-1', 'external-2'])
        self.assertEqual(len({row['path'] for row in result['carriers']}), 1)
        self.assertEqual(len({row['sha256'] for row in result['carriers']}), 1)
        self.assertNotEqual(result['carriers'][0]['sha256'], prepared['single_board']['sha256'])
        for carrier in result['carriers']:
            self.assertEqual(c.sha256_file(self.root / carrier['path']), carrier['sha256'])
        self.assertEqual(result['prepared']['selected_references'][0]['source'], prepared['selected_references'][1]['source'])
        edited['choices']['additional_references'].clear()
        empty = self.external_build(edited, 'external-empty')
        self.assertEqual(empty['prepared']['transport_mode'], 'none')
        self.assertEqual(empty['references'], [])
        self.assertEqual(empty['carriers'], [])
        self.assertTrue((self.root / 'external-empty/prepared-reference-set.json').is_file())

    def test_external_mixed_pack_state_and_direct_choices_keep_each_source_owner(self):
        from reference_runtime_smoke_test import _write_fixture_pack, FIXTURE_PACK_ID, DIRECT_RASTER_RECORD_ID
        from reference_runtime import build_reference_use_plan, execute_reference_use_plan
        from state_protocol import finalize_artifact
        fixture = _write_fixture_pack(self.work)
        self.activate(fixture, FIXTURE_PACK_ID)
        uses = [{'record_id': DIRECT_RASTER_RECORD_ID, 'intended_influence': 'pose-camera',
                 'subject_uses': [{'subject_id': subject, 'use': 'pose-camera', 'priority': 0}]} for subject in ('A', 'B')]
        plan = build_reference_use_plan(uses, transport_mode='multi-image', source_lighting_mode='replace',
            target_model=MODEL_ID, include_technical_roles=['subject-mask'],
            light_sources=[{'light_id': 'key', 'direction': 'upper left', 'apparent_size': 'large',
                'color': 'neutral', 'relative_intensity': 'primary', 'softness': 'soft'}],
            material_responses=[{'material': 'matte sample', 'roughness': 'matte', 'specular_strength': 'low',
                'highlight_shape': 'broad', 'wetness': 'dry', 'anisotropy': 'none'}])
        source = refs._prepare_supplied_source({'kind': 'supplied-file', 'reference_id': 'state',
            'resolved_path': str(self.root / 'image-2.png')}, 'state source')
        state = finalize_artifact({'artifact_type': 'reference-selection', 'selection_id': 'SEL-C',
            'subjects': [{'subject_id': 'C', 'identity_contract_sha256': 'a' * 64,
                'era_contract_sha256': None, 'appearance_variant_sha256': None,
                'state_snapshot_sha256': 'b' * 64, 'story_order': 1, 'required_state_features': ['coat']}],
            'selected_references': [{'subject_id': 'C', 'binding_id': 'BIND-C', 'role': 'identity',
                'source': source, 'covers': ['coat'], 'intended_influence': ['identity'],
                'review_dimensions': ['identity'], 'unsupported_or_occluded_state': [], 'unsupported_assumptions': [],
                'subject_uses': [{'subject_id': 'C', 'use': 'identity', 'priority': 0}]}],
            'unresolved_requirements': []})
        initial = execute_reference_use_plan(plan, output_dir=self.root / 'pack-source')
        choices = inputs.draft(initial, package_root=self.root / 'pack-source')
        choices['reference_selection'] = state
        choices['additional_references'] = [self.direct(1, 'D')]
        prepared = self.build(choices, 'mixed')
        external = self.external_plan(prepared, 'mixed')
        edited = inputs.draft_external(external, prepared, package_root=self.root / 'mixed', root=self.root)
        edited['choices']['reference_use_plan']['items'].pop(0)
        edited['choices']['additional_references'].append(self.direct(0, 'E'))
        result = self.external_build(edited, 'mixed-edited')
        self.assertEqual([row['id'] for row in result['references'][:3]], ['external-1', 'external-2', 'external-3'])
        for old, new in zip(prepared['selected_references'][1:], result['prepared']['selected_references'][:3], strict=True):
            self.assertEqual(new['source'], old['source'])
            self.assertEqual(new['authority'], old['authority'])
            self.assertEqual(new['subject_uses'], old['subject_uses'])
        self.assertEqual(result['prepared']['reference_selection'], prepared['reference_selection'])
        self.assertEqual(result['prepared']['selected_references'][0]['source']['kind'], 'pack-artifact')
        self.assertEqual(result['prepared']['selected_references'][1]['binding_id'], 'BIND-C')
        self.assertEqual(result['prepared']['reference_use_plan']['reference_items'][0]['precedence'], 0)
        edited['choices']['reference_selection']['selected_references'].clear()
        with self.assertRaisesRegex(ValueError, 'unresolved requirements'):
            self.external_build(edited, 'mixed-incomplete')
        self.assertFalse((self.root / 'mixed-incomplete').exists())

    def test_image_input_rebuild_keeps_authored_use_and_exclusions(self):
        from model_prompt_input_fixtures import prompt_input
        evidence = (self.pack / 'records/models.json').read_bytes()
        (self.root / 'model.json').write_bytes(evidence)
        plan = {'artifact_type': 'image-input-plan', 'model': {
            'requested': MODEL_ID, 'catalog_status': 'defined', 'catalog_model': MODEL_ID,
            'prompt_input': prompt_input('descriptive'),
            'target': {'service': 'synthetic', 'model_identifier': 'synthetic:robot', 'operation': 'generate'},
            'evidence': {'path': 'model.json', 'sha256': c.digest(evidence), 'locator': 'whole synthetic model record'}},
            'references': [{'id': 'image-0', 'role': 'scene', 'file': 'image-0.png',
                'use_for': ['the selected camera framing'], 'do_not_transfer': ['current surface color'],
                'subject_uses': [{'subject_id': 'A', 'use': 'pose-camera', 'priority': 0}]}],
            'external_request': None}
        choices = inputs.draft(None, package_root=self.root)
        choices['image_input'] = plan
        first = self.build(choices, 'image-first')
        edited = inputs.draft(first, package_root=self.root / 'image-first')
        edited['image_input']['references'].append({'id': 'image-1', 'role': 'geometry', 'file': 'image-1.png',
            'use_for': ['the declared silhouette'], 'do_not_transfer': ['lighting'],
            'subject_uses': [{'subject_id': 'A', 'use': 'identity', 'priority': 1}]})
        second = self.build(edited, 'image-second')
        self.assertEqual(second['selected_references'][0]['authority'], first['selected_references'][0]['authority'])
        self.assertEqual(second['selected_references'][1]['authority'],
            {'controls': ['the declared silhouette'], 'must_not_control': ['lighting']})
        self.assertEqual(second['selected_references'][1]['subject_uses'], edited['image_input']['references'][1]['subject_uses'])

        import image_input
        linked = copy.deepcopy(edited['image_input'])
        linked['prepared_references'] = 'image-second/prepared-reference-set.json'
        binding = image_input.validate(linked, self.root)
        self.assertEqual(binding['prepared_references_sha256'],
                         c.sha256_file(self.root / linked['prepared_references']))
        self.assertTrue(all(Path(row['transport']['resolved_path']).is_absolute()
                            for row in binding['prepared_reference_set']['selected_references']))
        prepared = refs.prepare_image_input_references(linked, studio=self.root, model=MODEL_ID,
            output_dir=self.root / 'linked-source')
        carried = inputs.draft(prepared, package_root=self.root)
        rebuilt = self.build(carried, 'linked-rebuilt')
        self.assertEqual([row['authority'] for row in rebuilt['selected_references']],
                         [row['authority'] for row in second['selected_references']])
        carried['image_input']['references'].clear()
        empty = self.build(carried, 'image-empty')
        self.assertEqual(empty['transport_mode'], 'none')
        self.assertNotIn('image_input_binding', empty)

    def test_pack_item_removal_rebuilds_plan_precedence_without_expanding_authority(self):
        from reference_runtime_smoke_test import _write_fixture_pack, FIXTURE_PACK_ID, DIRECT_RASTER_RECORD_ID
        from reference_runtime import build_reference_use_plan, execute_reference_use_plan
        fixture = _write_fixture_pack(self.work)
        self.activate(fixture, FIXTURE_PACK_ID)
        uses = [{'record_id': DIRECT_RASTER_RECORD_ID, 'intended_influence': 'pose-camera',
                 'subject_uses': [{'subject_id': subject, 'use': 'pose-camera', 'priority': 0}]} for subject in ('A', 'B')]
        plan = build_reference_use_plan(uses, transport_mode='multi-image', source_lighting_mode='replace',
            target_model=MODEL_ID, include_technical_roles=['subject-mask'],
            light_sources=[{'light_id': 'key', 'direction': 'upper left', 'apparent_size': 'large',
                'color': 'neutral', 'relative_intensity': 'primary', 'softness': 'soft'}],
            material_responses=[{'material': 'matte sample', 'roughness': 'matte', 'specular_strength': 'low',
                'highlight_shape': 'broad', 'wetness': 'dry', 'anisotropy': 'none'}])
        prepared = execute_reference_use_plan(plan, output_dir=self.root / 'pack-source')
        edited = inputs.draft(prepared, package_root=self.root / 'pack-source')
        edited['reference_use_plan']['items'].pop(0)
        result = self.build(edited, 'pack-result')
        item = result['reference_use_plan']['reference_items'][0]
        self.assertEqual(item['precedence'], 0)
        self.assertEqual(item['subject_uses'][0]['subject_id'], 'B')
        self.assertEqual(item['authority'], plan['reference_items'][1]['authority'])
        self.assertEqual(result['selected_references'][0]['source']['kind'], 'pack-artifact')
        self.assertEqual(len(result['reference_use_plan']['selected_records']), 1)

    def test_existing_image_input_ids_follow_sources_through_staged_publication(self):
        import image_input
        from model_prompt_input_fixtures import prompt_input
        evidence = (self.pack / 'records/models.json').read_bytes()
        (self.root / 'model.json').write_bytes(evidence)
        choices = inputs.draft(None, package_root=self.root)
        choices['additional_references'] = [self.direct(0), self.direct(1, subject='B')]
        original = self.build(choices, 'origin')
        linked = {'artifact_type': 'image-input-plan', 'model': {
            'requested': MODEL_ID, 'catalog_status': 'defined', 'catalog_model': MODEL_ID,
            'prompt_input': prompt_input('descriptive'),
            'target': {'service': 'synthetic', 'model_identifier': 'synthetic:robot', 'operation': 'generate'},
            'evidence': {'path': 'model.json', 'sha256': c.digest(evidence), 'locator': 'whole synthetic model record'}},
            'references': [{'id': f'stable-{index}', 'role': row['role'], 'file': f'image-{index}.png',
                'use_for': row['authority']['controls'], 'do_not_transfer': row['authority']['must_not_control'],
                'subject_uses': row['subject_uses']}
                for index, row in enumerate(original['selected_references'])],
            'prepared_references': 'origin/prepared-reference-set.json', 'external_request': None}
        wrapped = refs.prepare_image_input_references(linked, studio=self.root, model=MODEL_ID,
            output_dir=self.root / 'unused-original')
        edited = inputs.draft(wrapped, package_root=self.root)
        self.assertEqual(set(edited['image_input']), {'model'})
        self.assertEqual([row['id'] for row in edited['additional_references']], ['stable-0', 'stable-1'])
        edited['additional_references'].pop(0)
        edited['additional_references'].append(self.direct(2))
        staging = self.work / 'staged-outside-studio'
        built = inputs.build(edited, model=MODEL_ID, root=self.root, output_dir=staging,
            publication_dir='published')
        shutil.copytree(staging, self.root / 'published')
        generated = c.load(self.root / 'published/image-input.json')
        self.assertEqual(generated['references'][0]['id'], 'stable-1')
        self.assertNotEqual(generated['references'][1]['id'], 'stable-1')
        self.assertEqual(generated['prepared_references'], 'published/prepared-reference-set.json')
        self.assertTrue(all(row['file'].startswith('published/references/sources/')
                            for row in generated['references']))
        validated = image_input.validate(generated, self.root)
        self.assertEqual(validated['prepared_references_sha256'],
                         c.sha256_file(self.root / generated['prepared_references']))
        self.assertEqual(built['selected_references'][0]['source'], original['selected_references'][1]['source'])
        self.assertEqual(built['selected_references'][0]['authority'], original['selected_references'][1]['authority'])
        prepared = refs.prepare_image_input_references(generated, studio=self.root, model=MODEL_ID,
            output_dir=self.root / 'unused-published')
        redrafted = inputs.draft(prepared, package_root=self.root)
        self.assertEqual([row['id'] for row in redrafted['additional_references']],
                         [row['id'] for row in generated['references']])
        redrafted['additional_references'].clear()
        empty = self.build(redrafted, 'mirror-empty')
        self.assertEqual(empty['selected_references'], [])
        self.assertFalse((self.root / 'mirror-empty/image-input.json').exists())

    def test_explicit_image_input_names_the_rows_of_an_existing_set_by_its_own_ids(self):
        # An explicit image input over an existing prepared set labels each
        # inherited row with its own reference ID; the set's authority is unchanged.
        import image_input
        from model_prompt_input_fixtures import prompt_input
        from reference_delivery import prepared_origin_projection
        evidence = (self.pack / 'records/models.json').read_bytes()
        (self.root / 'model.json').write_bytes(evidence)
        choices = inputs.draft(None, package_root=self.root)
        choices['additional_references'] = [self.direct(0)]
        original = self.build(choices, 'origin')
        self.assertEqual(original['selected_references'][0]['reference_id'], 'image-0')
        row = original['selected_references'][0]
        choices = inputs.draft(None, package_root=self.root)
        choices['image_input'] = {'artifact_type': 'image-input-plan', 'model': {
            'requested': MODEL_ID, 'catalog_status': 'defined', 'catalog_model': MODEL_ID,
            'prompt_input': prompt_input('descriptive'),
            'target': {'service': 'synthetic', 'model_identifier': 'synthetic:robot', 'operation': 'generate'},
            'evidence': {'path': 'model.json', 'sha256': c.digest(evidence), 'locator': 'whole synthetic model record'}},
            'references': [{'id': 'edit-source', 'role': row['role'], 'file': 'image-0.png',
                'use_for': row['authority']['controls'], 'do_not_transfer': row['authority']['must_not_control'],
                'subject_uses': row['subject_uses']}],
            'prepared_references': 'origin/prepared-reference-set.json', 'external_request': None}
        built = self.build(choices, 'relabeled')
        selected = built['selected_references'][0]
        self.assertEqual(selected['reference_id'], 'edit-source')
        self.assertEqual((selected['source'], selected['authority']), (row['source'], row['authority']))
        self.assertEqual(prepared_origin_projection(built), prepared_origin_projection(original))
        generated = c.load(self.root / 'relabeled/image-input.json')
        self.assertEqual(generated['references'][0]['id'], 'edit-source')
        binding = image_input.validate(generated, self.root)
        image_input.require_prepared(binding, refs.validate_prepared_reference_set(
            built, package_root=self.root / 'relabeled'), model_id=MODEL_ID,
            target=binding['model']['target'])

    def test_removing_state_coverage_remains_an_unresolved_choice(self):
        from state_protocol import finalize_artifact
        source = refs._prepare_supplied_source({'kind': 'supplied-file', 'reference_id': 'state',
            'resolved_path': str(self.root / 'image-0.png')}, 'state source')
        state = finalize_artifact({'artifact_type': 'reference-selection', 'selection_id': 'SEL-A',
            'subjects': [{'subject_id': 'A', 'identity_contract_sha256': 'a' * 64,
                'era_contract_sha256': None, 'appearance_variant_sha256': None,
                'state_snapshot_sha256': 'b' * 64, 'story_order': 1, 'required_state_features': ['coat']}],
            'selected_references': [{'subject_id': 'A', 'binding_id': 'BIND-A', 'role': 'identity',
                'source': source, 'covers': ['coat'], 'intended_influence': ['identity'],
                'review_dimensions': ['identity'], 'unsupported_or_occluded_state': [], 'unsupported_assumptions': [],
                'subject_uses': [{'subject_id': 'A', 'use': 'identity', 'priority': 0}]}],
            'unresolved_requirements': []})
        choices = inputs.draft(None, package_root=self.root)
        choices['reference_selection'] = state
        original = self.build(choices, 'state-first')
        edited = inputs.draft(original, package_root=self.root / 'state-first')
        copied = self.build(edited, 'state-copy')
        self.assertEqual(copied['selected_references'][0]['binding_id'], 'BIND-A')
        self.assertEqual(copied['selected_references'][0]['intended_influence'], ['identity'])
        edited['reference_selection']['selected_references'].clear()
        with self.assertRaisesRegex(ValueError, 'unresolved requirements'):
            self.build(edited, 'state-incomplete')
        self.assertFalse((self.root / 'state-incomplete').exists())


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    import sys
    buffer = io.StringIO()
    result = unittest.TextTestRunner(stream=buffer, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    print(json.dumps({'ok': result.wasSuccessful(), 'checks': result.testsRun,
        'passed': result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped),
        'skipped': len(result.skipped), 'errors': [str(case) + ': ' + detail for case, detail in result.failures + result.errors],
        'details': buffer.getvalue(), 'scope': 'Synthetic reference authoring and actual local preparation; no generation.'},
        ensure_ascii=False, indent=2))
    raise SystemExit(0 if result.wasSuccessful() else 1)
