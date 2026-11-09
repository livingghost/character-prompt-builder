#!/usr/bin/env python3
"""Exercise target ownership using declared local fixtures and no image provider."""
from __future__ import annotations

import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import execution_contract as c
from input_evidence import InputEvidence
import pack_manager as packs
from pack_cache import load_runtime_catalog
import production_case_fixtures as fixtures
import production_external_inputs as external_inputs
import production_target as target
from model_prompt_input_fixtures import prompt_input
from runtime_snapshot import CompileRuntime


class TargetProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.home = Path(cls.temp.name)
        environment = patch.dict(os.environ, {'CPB_HOME': str(cls.home / 'runtime-home')})
        environment.start()
        cls.addClassCleanup(environment.stop)
        pack = fixtures.create_pack(cls.home / 'packs/synthetic', with_alternate=True,
            with_upscale=True, with_alternate_upscale=True)
        settings = packs.default_settings(extra_roots=[pack], state_file=cls.home / 'state.json',
            cache_dir=cls.home / 'cache', managed_root=cls.home / 'managed',
            default_enabled_packs=[fixtures.PACK_ID])
        packs.save_state(settings.state_file, {'pack_roots': [], 'enabled_packs': [fixtures.PACK_ID],
            'disabled_packs': [], 'pack_order': [fixtures.PACK_ID]})
        cls.source = CompileRuntime.from_catalog(load_runtime_catalog(settings), settings)

    def setUp(self):
        self.temp_work = tempfile.TemporaryDirectory(dir=self.home)
        self.addCleanup(self.temp_work.cleanup)
        self.root = Path(self.temp_work.name)
        self.reader = InputEvidence(self.root)
        self.task = {'route': 'generation', 'execution': 'dispatcher',
            'generation': {'model': fixtures.MODEL_ID, 'service': 'synthetic', 'count': 2, 'seed': 17},
            'sources': [{'id': 'unusual-spec-name', 'role': 'production-spec'},
                        {'id': 'model-card', 'role': 'design'},
                        {'id': 'model-direction', 'role': 'design'}],
            'direction': {'decisions': [{'selected': 'authored-option', 'reason': 'Synthetic author reason.'}]},
            'criteria': [{'id': 'preserve', 'text': 'Keep the authored composition.'}],
            'authority': 'original-authority.json'}
        self.authored = {'task': copy.deepcopy(self.task),
            'generation': copy.deepcopy(self.task['generation']),
            'delivery': {'content': fixtures.PROMPT},
            'documents': {'production_spec': {'target_model': fixtures.MODEL_ID,
                'brief': 'Keep the authored brief.'}, 'parameters': {'steps': 20}},
            'sources': {'unusual-spec-name': {'format': 'json', 'content': {
                'target_model': fixtures.MODEL_ID, 'brief': 'Keep the applied source.'}},
                'model-card': {'format': 'json', 'content': {'target_model': fixtures.MODEL_ID,
                    'claim': 'This is generic author content, not a replaceable generated card.'}},
                'model-direction': {'format': 'text', 'content': 'Keep the author direction.'}},
            'references': None, 'upscale': None}

    def project(self, selection, *, authored=True, task=None, external=None):
        choices = {'target': selection, 'external': external}
        if authored:
            choices['authoring'] = self.authored
        return target.project(choices, task or self.task, self.root, self.reader, 'built', source=self.source)

    def test_extract_removes_only_target_projections(self):
        original = copy.deepcopy((self.task, self.authored))
        selected = target.extract(self.task, self.authored, None)
        self.assertEqual(selected, {'kind': 'catalog', 'model': fixtures.MODEL_ID, 'service': 'synthetic'})
        self.assertEqual(self.authored['generation'], {'count': 2, 'seed': 17})
        self.assertNotIn('target_model', self.authored['documents']['production_spec'])
        self.assertNotIn('target_model', self.authored['sources']['unusual-spec-name']['content'])
        for identifier in ('model-card', 'model-direction'):
            self.assertEqual(self.authored['sources'][identifier], original[1]['sources'][identifier])
        for field in ('direction', 'criteria', 'authority'):
            self.assertEqual(self.task[field], original[0][field])

    def test_switch_derives_canonical_ids_and_card_without_rewriting_author_content(self):
        target.extract(self.task, self.authored, None)
        before = copy.deepcopy((self.task, self.authored))
        result = self.project({'kind': 'catalog', 'model': 'synthetic alternate fixture', 'service': 'synthetic'})
        self.assertEqual(result['unresolved'], [])
        self.assertEqual((self.task, self.authored), before)
        built = result['choices']['authoring']
        self.assertEqual(result['task']['generation']['model'], fixtures.ALTERNATE_MODEL_ID)
        self.assertEqual(built['generation'], {'model': fixtures.ALTERNATE_MODEL_ID,
            'service': 'synthetic', 'count': 2, 'seed': 17})
        self.assertEqual(built['documents']['production_spec']['target_model'], fixtures.ALTERNATE_MODEL_ID)
        self.assertEqual(built['sources']['unusual-spec-name']['content']['target_model'], fixtures.ALTERNATE_MODEL_ID)
        for identifier in ('model-card', 'model-direction'):
            self.assertEqual(built['sources'][identifier], self.authored['sources'][identifier])
        self.assertEqual(built['documents']['parameters'], {'steps': 20})
        self.assertEqual(built['delivery']['content'], fixtures.PROMPT)
        for field in ('direction', 'criteria', 'authority'):
            self.assertEqual(result['task'][field], self.task[field])
        knowledge = result['knowledge']
        self.assertEqual(knowledge['model_cards'][0]['model_identifier'], 'synthetic:alternate')
        self.assertEqual(knowledge['offering'], result['resolved_target'].offering)
        self.assertEqual(knowledge['parameter_schema'], result['resolved_target'].parameter_schema)
        self.assertIsNone(knowledge['assessment'])
        self.assertNotIn('reading_key', knowledge)
        self.assertNotIn('authorization', knowledge)

    def test_required_service_is_not_selected_from_single_offering(self):
        result = self.project({'kind': 'catalog', 'model': fixtures.MODEL_ID, 'service': None})
        self.assertEqual([row['field'] for row in result['unresolved']], ['target.service'])
        self.assertIsNone(result['resolved_target'])
        self.assertEqual(result['files'], {})

    def test_unknown_model_returns_unresolved_without_replacement(self):
        result = self.project({'kind': 'catalog', 'model': 'not-a-fixture-model', 'service': 'synthetic'})
        self.assertEqual(result['unresolved'][0]['code'], 'target-evidence-required')
        self.assertIsNone(result['resolved_target'])
        self.assertEqual(result['choices']['authoring'], self.authored)

    def test_explicit_assessment_conditions_produce_no_permission_or_quality_claim(self):
        selected = {'kind': 'catalog', 'model': fixtures.MODEL_ID, 'service': 'synthetic',
            'assessment': {'use_cases': ['synthetic-example'], 'mode': 'text-to-image', 'reference_count': 0}}
        result = self.project(selected)
        self.assertEqual(result['unresolved'], [])
        assessment = result['knowledge']['assessment'][0]
        self.assertEqual(assessment['input_compatibility']['status'], 'compatible')
        self.assertFalse(assessment['content_permission_assessed'])
        self.assertFalse(assessment['visual_quality_assessed'])
        self.assertEqual(selected['assessment']['use_cases'], ['synthetic-example'])

    def test_upscale_selection_preserves_source_scale_controls_and_validation(self):
        self.task.update(route='upscale', upscale={'service': 'synthetic'})
        self.task.pop('generation')
        self.authored.update(task=copy.deepcopy(self.task), generation=None,
            upscale={'model': fixtures.UPSCALE_MODEL_ID, 'source': 'original.png', 'scale_factor': 4,
                'settings': {}, 'guidance_prompt': None, 'request_validation': 'original-validation.json'})
        before = copy.deepcopy(self.authored['upscale'])
        selected = target.extract(self.task, self.authored, None)
        self.assertEqual(selected['model'], fixtures.UPSCALE_MODEL_ID)
        selected['model'] = fixtures.ALTERNATE_UPSCALE_MODEL_ID
        result = self.project(selected)
        self.assertEqual(result['unresolved'], [])
        self.assertEqual(result['choices']['authoring']['upscale'],
            {**before, 'model': fixtures.ALTERNATE_UPSCALE_MODEL_ID})
        self.assertEqual(result['task']['upscale']['service'], 'synthetic')

    def test_selector_only_task_remains_supported(self):
        self.task['generation']['production_spec'] = 'original-spec.json'
        result = self.project({'kind': 'catalog', 'model': fixtures.MODEL_ID, 'service': 'synthetic'}, authored=False)
        self.assertEqual(result['unresolved'], [])
        self.assertNotIn('authoring', result['choices'])
        self.assertEqual(result['task'], self.task)

    def test_authored_portable_and_supplied_model_keep_their_meaning(self):
        task = {'execution': 'authored', 'route': 'development'}
        result = self.project(None, task=task, authored=False)
        self.assertEqual(result['unresolved'], [])
        self.assertIsNone(result['knowledge'])
        record = {'id': 'acquired-fixture', 'prompt_input': prompt_input('descriptive'),
            'prompt_style': 'Retain this independently acquired author guidance.'}
        (self.root / 'acquired.json').write_bytes(c.encoded(record))
        selected = {'kind': 'acquired', 'model_file': 'acquired.json', 'service': None,
            'parameters': {'explicit': 'authored'}, 'syntax': 'literal'}
        result = self.project(selected, task=task, authored=False)
        self.assertEqual(result['unresolved'], [])
        self.assertEqual(result['task']['authored']['target'], {
            'model_file': 'acquired.json', 'parameters': {'explicit': 'authored'}, 'syntax': 'literal'})
        self.assertEqual(result['knowledge']['model_record'], record)
        self.assertIn('acquired.json', self.reader.read_paths)

    def test_explicit_portable_choice_clears_only_prior_compiled_target(self):
        task = {'execution': 'authored', 'route': 'development', 'authored': {
            'target': {'model': fixtures.MODEL_ID, 'service': 'synthetic'},
            'requirements': ['Preserve the original authored instruction.']}}
        choices = {'target': None, 'authoring': {'task': copy.deepcopy(task)}}
        previous = copy.deepcopy((task, choices))
        result = target.project(choices, task, self.root, self.reader, 'portable', source=self.source)
        self.assertEqual(result['unresolved'], [])
        for projected in (result['task'], result['choices']['authoring']['task']):
            self.assertEqual(projected['authored'], {'requirements': ['Preserve the original authored instruction.']})
        self.assertEqual((task, choices), previous)
        self.assertIsNone(result['resolved_target'])

    def external_choices(self):
        return {'image_input': {'artifact_type': 'image-input-plan', 'references': [],
            'external_request': {'model_field': ['model'], 'prompt_field': ['prompt'],
                'prompt_syntax': {'default': 'literal', 'control': None}, 'count_field': ['count'],
                'operation_field': None, 'count': 2}},
            'request': {'model': None, 'prompt': None, 'count': None, 'steps': 20},
            'media_slots': [], 'source_files': {}, 'source_uploads': [], 'reference_delivery': None}

    def test_catalog_external_uses_same_target_evidence_and_preserves_native_controls(self):
        task = {'route': 'generation', 'execution': 'external'}
        external = self.external_choices()
        before = copy.deepcopy(external)
        result = self.project({'kind': 'catalog', 'model': fixtures.ALTERNATE_MODEL_ID,
            'service': 'synthetic', 'operation': 'generate'}, task=task, external=external)
        self.assertEqual(result['unresolved'], [])
        self.assertEqual(external, before)
        model = result['choices']['external']['image_input']['model']
        self.assertEqual(model['target'], {'service': 'synthetic',
            'model_identifier': 'synthetic:alternate', 'operation': 'generate'})
        self.assertEqual(c.decode(result['files']['target/model.json'])['id'], fixtures.ALTERNATE_MODEL_ID)
        self.assertEqual(model['evidence']['sha256'], c.digest(result['files']['target/model.json']))
        self.assertIsNone(result['resolved_target'].transport)
        with self.source.using():
            files, trace = external_inputs.build(result['choices']['external'], task, self.reader,
                self.root, 'built', fixtures.PROMPT.encode(), derived_files=result['files'])
        self.assertEqual(trace['state'], 'materialized')
        self.assertEqual(trace['request'], {'model': 'synthetic:alternate', 'prompt': fixtures.PROMPT,
            'count': 2, 'steps': 20})
        self.assertEqual(files['target/model.json'], result['files']['target/model.json'])

    def test_external_evidence_and_native_binding_survive_extraction_and_projection(self):
        (self.root / 'interface.txt').write_text('Explicit synthetic interface evidence.', encoding='utf-8')
        external = self.external_choices()
        external['image_input']['model'] = {'requested': 'Independent synthetic target',
            'catalog_status': 'missing', 'catalog_model': None,
            'target': {'service': 'unlisted-synthetic', 'model_identifier': 'unlisted:fixture', 'operation': 'infer'},
            'evidence': {'path': 'interface.txt', 'locator': 'whole'},
            'prompt_input': prompt_input('descriptive')}
        authored = copy.deepcopy(self.authored)
        task = {'route': 'generation', 'execution': 'external'}
        authored['task'] = copy.deepcopy(task)
        selected = target.extract(task, authored, external)
        self.assertNotIn('model', external['image_input'])
        self.assertEqual(external_inputs.unresolved(external), [])
        self.assertEqual(selected['kind'], 'external')
        result = target.project({'target': selected, 'authoring': authored, 'external': external},
            task, self.root, self.reader, 'built', source=self.source)
        self.assertEqual(result['unresolved'], [])
        model = result['choices']['external']['image_input']['model']
        self.assertEqual(model['target'], selected['model']['target'])
        self.assertEqual(model['evidence']['sha256'], c.sha256_file(self.root / 'interface.txt'))
        self.assertEqual(result['choices']['external']['request'], external['request'])
        self.assertEqual(result['choices']['external']['image_input']['external_request'],
            external['image_input']['external_request'])
        self.assertIsNone(result['resolved_target'].transport)

    def test_external_evidence_pin_is_checked_without_inventing_replacement(self):
        (self.root / 'interface.txt').write_text('Updated synthetic evidence.', encoding='utf-8')
        selected = {'kind': 'external', 'model': {'requested': 'Synthetic interface',
            'target': {'service': 'unlisted-synthetic', 'model_identifier': 'unlisted:fixture', 'operation': 'infer'},
            'evidence': {'path': 'interface.txt', 'sha256': c.digest(b'Previous evidence.'), 'locator': 'whole'},
            'prompt_input': prompt_input('descriptive')}}
        result = self.project(selected, task={'route': 'generation', 'execution': 'external'},
            external=self.external_choices())
        self.assertEqual(result['unresolved'][0]['code'], 'target-evidence-required')
        self.assertIn('changed', result['unresolved'][0]['message'])
        self.assertIsNone(result['resolved_target'])

    def test_external_public_plan_selects_its_target_and_retains_native_choices(self):
        task = {'route': 'generation', 'execution': 'external'}
        existing = self.project({'kind': 'catalog', 'model': fixtures.MODEL_ID,
            'service': 'synthetic', 'operation': 'generate'}, task=task, external=self.external_choices())
        with self.source.using():
            files, _ = external_inputs.build(existing['choices']['external'], task, self.reader,
                self.root, 'built', fixtures.PROMPT.encode(), derived_files=existing['files'])
        for path, raw in files.items():
            c.atomic(self.root / 'built' / path, raw)
        original = {path: (self.root / 'built' / path).read_bytes() for path in files}
        choices = {'target': None, 'external': {'image_input': 'built/image-input.json'}}
        result = target.project(choices, task, self.root, self.reader, 'next', source=self.source)
        self.assertEqual(result['unresolved'], [])
        self.assertEqual(result['choices']['target'], {'kind': 'catalog', 'model': fixtures.MODEL_ID,
            'service': 'synthetic', 'operation': 'generate'})
        self.assertIsNone(choices['target'])
        self.assertEqual(result['choices']['external']['request']['steps'], 20)
        self.assertEqual(original, {path: (self.root / 'built' / path).read_bytes() for path in files})
        choices['target'] = {'kind': 'catalog', 'model': fixtures.ALTERNATE_MODEL_ID,
            'service': 'synthetic', 'operation': 'generate'}
        switched = target.project(choices, task, self.root, self.reader, 'next', source=self.source)
        self.assertEqual(switched['unresolved'], [])
        self.assertEqual(switched['choices']['external']['image_input']['model']['target']['model_identifier'],
            'synthetic:alternate')
        self.assertEqual(switched['choices']['external']['request']['steps'], 20)


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
