"""Model selection preserves scope, provenance and the cause of generation failures."""
from __future__ import annotations

import copy
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from unittest.mock import patch

import execution_contract as c
import model_suitability as s
import render_contract_lib as r
from render_contract_fixtures import profile, intent
from catalog_retrieval import runtime as catalog_runtime
import pack_manager as pm

ROOT = Path(__file__).resolve().parents[1]


def basis(kind='user-report'):
    return {'kind': kind, 'source': 'Synthetic author report.', 'observed_at': '2026-10-18',
            'limitations': ['No provider behavior is established by this fixture.']}


def preference(decision='discourage'):
    return {'id': 'reported-refusal-avoidance', 'selector': {'family': 'Synthetic family',
            'model_patterns': [{'field': 'model-identifier', 'pattern': 'synthetic:portrait@*'}],
            'service': 'synthetic-service', 'operations': ['generation'],
            'use_cases': ['benign-minor-depiction', 'policy-sensitive-use']},
            'preference': decision, 'reported_failure': 'provider-refusal',
            'reason': 'The author reports refusals for this use and prefers a different model.', 'basis': basis()}


def preferences(decision='discourage'):
    return {'artifact_type': 'model-selection-preferences', 'entries': [preference(decision)]}


def model():
    return {'id': 'synthetic-portrait', 'operation_kind': 'generation'}


def offering():
    return {'service': 'synthetic-service', 'model_identifier': 'synthetic:portrait@1',
            'constraints': {'reference_images': {'max': 3}}, 'execution_profile': profile(),
            'request_keys': {'prompt': ['prompt'], 'reference images': ['images']}, 'observed_at': '2026-10-18'}


def fixture_pack(root, value, *, dependencies=(), include_model=False):
    manifest = pm.initialize_pack(root, name='Synthetic preference pack', release='2026.10.18.1')
    resource = root / 'resources' / s.PREFERENCES_FILE
    resource.parent.mkdir()
    resource.write_bytes(c.encoded(value))
    manifest['content'].update(resource_globs=['resources/**/*'],
        resource_bindings={s.PREFERENCES_RESOURCE: 'resources/' + s.PREFERENCES_FILE})
    manifest['dependencies'] = [{'pack_id': pack_id} for pack_id in dependencies]
    if include_model:
        record = {**model(), 'label': 'Synthetic portrait', 'aliases': ['synthetic portrait alias'],
                  'curation_status': 'vocabulary', 'domains': ['shared'], 'tags': ['synthetic'],
                  'prompt_style': 'Natural language', 'ordering': ['subject', 'composition'],
                  'search_terms': [], 'supports_negative_prompt': False,
                  'negative_transport_mode': 'integrated-critical',
                  'negative_transport_notes': 'Synthetic interface uses inline constraints.', 'offerings': [offering()]}
        pm.atomic_write_json(root / 'records/models.json', {'kind': 'model', 'records': [record]})
    pm.atomic_write_json(root / 'pack.json', manifest)
    pm.write_lock(root)
    return manifest['pack_id'], resource


def fixture_runtime(root, packs=(), *, enabled=(), disabled=(), order=(), state=True):
    settings = pm.PackSettings(roots=tuple(packs), state_file=root / 'state.json',
        cache_dir=root / 'cache', managed_root=root / 'managed', quarantine_root=root / 'quarantine')
    if state:
        pm.save_state(settings.state_file, {'pack_roots': [str(path) for path in packs],
            'enabled_packs': list(enabled), 'disabled_packs': list(disabled), 'pack_order': list(order)})
    return settings


class SuitabilityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        # Resolve once: install records canonical spellings, so an 8.3 or
        # junction temporary directory would otherwise fail the comparisons.
        self.home = Path(temporary.name).resolve()
        self.environment = patch.dict(os.environ, {'CPB_HOME': str(self.home)})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.runtime = catalog_runtime.using_pack_runtime(fixture_runtime(self.home / 'runtime'))
        self.runtime.__enter__()
        self.addCleanup(self.runtime.__exit__, None, None, None)

    def assess(self, *, offered=None, use_case='benign-minor-depiction', count=2, prefs=None, **options):
        return s.assess(model(), offered or offering(), use_cases=[use_case], mode='reference-guided',
                        reference_count=count, preferences=preferences() if prefs is None else prefs, **options)

    def test_missing_guidance_is_unknown_without_discouragement(self):
        result = self.assess(prefs={'artifact_type': 'model-selection-preferences', 'entries': []})
        self.assertEqual(result['selection_status'], 'candidate')
        self.assertEqual(result['use_cases'][0]['recommendation'], 'unknown')
        self.assertEqual(result['use_cases'][0]['author_preference'], 'none')
        self.assertFalse(result['content_permission_assessed'])
        self.assertNotIn('warning', result)

    def test_user_report_discourages_only_declared_use(self):
        result = self.assess()
        self.assertEqual(result['selection_status'], 'discouraged')
        self.assertEqual(result['use_cases'][0]['author_preferences'][0]['basis']['kind'], 'user-report')
        self.assertEqual(self.assess(use_case='product-still-life')['selection_status'], 'candidate')

    def test_family_label_and_aliases_do_not_expand_an_explicit_model_selector(self):
        record = {'id': 'synthetic-general-adapter', 'label': 'Synthetic family',
                  'aliases': ['synthetic-portrait', 'synthetic:portrait@1'], 'offerings': []}
        prefs = preferences()
        prefs['entries'][0]['selector'].update(service=None, operations=['generation', 'instruction-edit'],
            model_patterns=[{'field': 'model-id', 'pattern': 'synthetic-portrait'}])
        for operation, mode in [('generation', 'reference-guided'), ('instruction-edit', 'instruction-edit')]:
            with self.subTest(operation=operation):
                result = s.assess(record, None, operation=operation, mode=mode, reference_count=2,
                                  use_cases=['benign-minor-depiction', 'policy-sensitive-use'], preferences=prefs)
                self.assertEqual(result['selection_status'], 'needs-interface-evidence')
                for row in result['use_cases']:
                    self.assertEqual(row['author_preference'], 'none')
                    self.assertEqual(row['author_preferences'], [])
                    self.assertEqual(row['recommendation'], 'unknown')

    def test_explicit_catalog_and_interface_patterns_select_their_own_targets(self):
        exact_offering = {'service': 'synthetic-service', 'model_identifier': 'synthetic:portrait@1'}
        targets = [({'id': 'synthetic-portrait'}, exact_offering),
                   ({'id': 'synthetic-portrait', 'offerings': []}, None), ({}, exact_offering)]
        prefs = preferences()
        prefs['entries'][0]['selector'].update(service=None, operations=['generation', 'instruction-edit'],
            model_patterns=[{'field': 'model-id', 'pattern': 'synthetic-portrait'},
                            {'field': 'model-identifier', 'pattern': 'synthetic:portrait@1'}])
        for record, offered in targets:
            for operation, mode in [('generation', 'reference-guided'), ('instruction-edit', 'instruction-edit')]:
                with self.subTest(record=record, offering=offered, operation=operation):
                    result = s.assess(record, offered, operation=operation, mode=mode, reference_count=2,
                                      use_cases=['benign-minor-depiction', 'policy-sensitive-use'], preferences=prefs)
                    self.assertEqual(result['selection_status'], 'discouraged')
                    for row in result['use_cases']:
                        self.assertEqual(row['author_preference'], 'discourage')
                        self.assertEqual(row['recommendation'], 'discourage')
                        self.assertEqual([item['id'] for item in row['author_preferences']],
                                         ['reported-refusal-avoidance'])

    def test_explicit_no_discouragement_is_not_a_provider_guarantee(self):
        result = self.assess(prefs=preferences('no-discouragement'))
        self.assertEqual(result['selection_status'], 'candidate')
        self.assertEqual(result['use_cases'][0]['author_preference'], 'no-discouragement')
        self.assertEqual(result['use_cases'][0]['recommendation'], 'unknown')

    def test_model_service_and_operation_scope_are_independent(self):
        for field, value in [('service', 'other-service'), ('model_identifier', 'synthetic:other@1')]:
            offered = offering(); offered[field] = value
            self.assertEqual(self.assess(offered=offered)['selection_status'], 'candidate')
        self.assertEqual(self.assess(operation='instruction-edit')['selection_status'], 'candidate')

    def test_exact_offering_facts_are_not_overridden_by_user_no_discouragement(self):
        offered = offering()
        offered['use_case_guidance'] = [{'id': 'scoped-provider-limitation', 'operation': 'generation',
            'use_case': 'benign-minor-depiction', 'recommendation': 'discourage', 'reason': 'Synthetic offering limitation.',
            'basis': basis('provider-statement')}]
        result = self.assess(offered=offered, prefs=preferences('no-discouragement'))
        self.assertEqual(result['selection_status'], 'discouraged')
        self.assertEqual(result['use_cases'][0]['offering_guidance'][0]['basis']['kind'], 'provider-statement')

    def test_no_discouragement_does_not_hide_reference_limit(self):
        result = self.assess(prefs=preferences('no-discouragement'), count=4)
        self.assertEqual(result['selection_status'], 'incompatible-inputs')
        self.assertEqual(result['input_compatibility']['reference_limit'], 3)

    def test_unrecorded_limit_needs_interface_evidence(self):
        offered = offering(); offered['constraints'] = {}
        self.assertEqual(self.assess(offered=offered, prefs=preferences('no-discouragement'))['selection_status'],
                         'needs-interface-evidence')

    def test_host_interface_uses_its_recorded_reference_limit(self):
        record = {**model(), 'offerings': [], 'execution_profile': profile(),
                  'max_reference_images': 3, 'reference_input_media_types': ['image/png']}
        empty = {'artifact_type': 'model-selection-preferences', 'entries': []}
        for count, status in [(2, 'candidate'), (4, 'incompatible-inputs')]:
            with self.subTest(reference_count=count):
                result = s.assess(record, None, use_cases=['product-still-life'], mode='reference-guided',
                                  reference_count=count, preferences=empty)
                self.assertEqual(result['selection_status'], status)
                self.assertEqual(result['input_compatibility']['reference_limit'], 3)

    def test_service_offering_does_not_inherit_host_reference_limit(self):
        record = {**model(), 'execution_profile': profile(), 'max_reference_images': 3}
        offered = offering(); offered['constraints'] = {}
        result = s.assess(record, offered, use_cases=['product-still-life'], mode='reference-guided',
                          reference_count=2, preferences=preferences('no-discouragement'))
        self.assertEqual(result['selection_status'], 'needs-interface-evidence')
        self.assertIsNone(result['input_compatibility']['reference_limit'])

    def test_mode_without_an_actual_media_field_cannot_be_suggested(self):
        offered = offering(); offered['request_keys'] = {'prompt': ['prompt']}
        result = self.assess(offered=offered, prefs=preferences('no-discouragement'))
        self.assertEqual(result['selection_status'], 'incompatible-inputs')
        self.assertIn('no transport', result['input_compatibility']['issues'][0])

    def test_unknown_external_model_still_receives_family_preference(self):
        result = s.assess({}, {'service': 'synthetic-service', 'model_identifier': 'synthetic:portrait@next'},
                          operation='generation', use_cases=['policy-sensitive-use'], mode='reference-guided',
                          reference_count=2, preferences=preferences())
        self.assertEqual(result['selection_status'], 'discouraged')
        self.assertEqual(result['input_compatibility']['status'], 'unknown')

    def test_install_is_persistent_and_cards_load_current_preferences(self):
        self.assertEqual(r.model_card(model(), offering())['use_case_suitability']['author_preferences'], [])
        result = s.install_preferences(preferences())
        self.assertEqual(Path(result['path']), self.home / s.PREFERENCES_FILE)
        first = r.model_card(model(), offering())['use_case_suitability']
        self.assertEqual(first['author_preferences'][0]['preference'], 'discourage')
        s.install_preferences(preferences('no-discouragement'))
        second = r.model_card(model(), offering())['use_case_suitability']
        self.assertEqual(second['author_preferences'][0]['preference'], 'no-discouragement')
        self.assertNotEqual(first['preferences_source']['sha256'], second['preferences_source']['sha256'])

    def test_selection_preferences_do_not_rewrite_sealed_parameter_contracts(self):
        record, offered = model(), offering()
        direction = intent('Flat graphic illustration.')
        contract = r.compile_contract(record, offered, direction, {}, prompt=direction['prompt_expression'], reference_count=0)
        s.install_preferences(preferences())
        r.verify_contract(contract, intent=direction, parameters=contract['parameters'], prompt=direction['prompt_expression'],
                          record=record, offering=offered, reference_count=0)

    def test_invalid_install_preserves_existing_preferences(self):
        s.install_preferences(preferences())
        previous = s.preferences_path().read_bytes()
        invalid = preferences(); invalid['entries'][0]['basis'] = basis('provider-statement')
        with self.assertRaisesRegex(ValueError, 'user preferences'):
            s.install_preferences(invalid)
        self.assertEqual(s.preferences_path().read_bytes(), previous)

    def test_invalid_file_is_reported_instead_of_silently_ignoring_user_preferences(self):
        s.preferences_path().write_text('{"entries": []}', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'expected fields'):
            r.model_card(model(), offering())

    def test_absent_policy_is_neutral_and_creates_no_override(self):
        value, witness = s.load_preferences()
        self.assertEqual(value, {'artifact_type': 'model-selection-preferences', 'entries': []})
        self.assertIsNone(witness)
        self.assertFalse(s.preferences_path().exists())

    def test_discovered_pack_cannot_initialize_preference_selection(self):
        pack = self.home / 'private-pack'
        fixture_pack(pack, preferences())
        settings = replace(fixture_runtime(self.home / 'fresh-runtime', [pack], state=False),
                           initialize_all_discovered=True)
        with catalog_runtime.using_pack_runtime(settings):
            with patch.object(catalog_runtime, 'load_pack_catalog', side_effect=AssertionError('unexpected discovery')):
                value, witness = s.load_preferences()
        self.assertEqual(value['entries'], [])
        self.assertIsNone(witness)
        self.assertFalse(settings.state_file.exists())
        self.assertFalse(s.preferences_path().exists())

    def test_preference_schema_and_semantic_checks_agree(self):
        from state_protocol import validate_against_schema
        schema = json.loads((ROOT / 'schemas/model-selection-preferences.schema.json').read_text(encoding='utf-8'))
        self.assertEqual(validate_against_schema(preferences(), schema), [])
        for mutation in ['operation', 'basis', 'id', 'selector', 'reported-failure', 'report-provenance']:
            value = preferences()
            if mutation == 'operation': value['entries'][0]['selector']['operations'] = ['invented']
            if mutation == 'basis': value['entries'][0]['basis'] = basis('provider-statement')
            if mutation == 'id': value['entries'][0]['id'] = ''
            if mutation == 'selector': value['entries'][0]['selector']['unknown'] = True
            if mutation == 'reported-failure': value['entries'][0]['reported_failure'] = 'timeout'
            if mutation == 'report-provenance': value['entries'][0]['basis'] = basis('author-preference')
            self.assertTrue(validate_against_schema(value, schema), mutation)
            with self.assertRaises(ValueError, msg=mutation): s.validate_preferences(value)

    def test_duplicate_scope_identifiers_are_rejected(self):
        value = preferences(); value['entries'].append(copy.deepcopy(value['entries'][0]))
        with self.assertRaisesRegex(ValueError, 'id repeats'): s.validate_preferences(value)
        value = preferences(); value['entries'][0]['selector']['model_patterns'] = [{'field': 'model-id', 'pattern': '*'}]
        with self.assertRaisesRegex(ValueError, 'name a model'): s.validate_preferences(value)

    def test_offering_guidance_uses_the_existing_pack_contract(self):
        from model_contract import validate_model_record
        from state_protocol import validate_against_schema
        record = {**model(), 'supports_negative_prompt': False, 'negative_transport_mode': 'integrated-critical',
                  'offerings': [offering()]}
        guidance = {'id': 'synthetic-report', 'operation': 'generation', 'use_case': 'policy-sensitive-use',
                    'recommendation': 'discourage', 'reason': 'Synthetic report only.', 'basis': basis()}
        record['offerings'][0]['use_case_guidance'] = [guidance]
        self.assertEqual(validate_model_record(record), [])
        pack_schema = json.loads((ROOT / 'schemas/pack-record-file.schema.json').read_text(encoding='utf-8'))
        single = json.loads((ROOT / 'schemas/model-use-case-guidance.schema.json').read_text(encoding='utf-8'))
        self.assertEqual(pack_schema['$defs']['model-use-case-guidance'], {k: v for k, v in single.items()
                                                                       if k not in {'$schema', '$id', 'title'}})
        self.assertEqual(validate_against_schema(guidance, single), [])
        record['offerings'][0]['use_case_guidance'][0]['recommendation'] = True
        self.assertTrue(validate_model_record(record))

    def test_external_assessment_cli_reads_persistent_preferences_without_catalog(self):
        s.install_preferences(preferences())
        command = [sys.executable, str(ROOT / 'scripts/render_contract.py'), 'assess', '--model-identifier',
                   'synthetic:portrait@next', '--service', 'synthetic-service', '--operation', 'generation',
                   '--use-case', 'policy-sensitive-use', '--mode', 'reference-guided', '--reference-count', '2']
        result = subprocess.run(command, text=True, encoding='utf-8', capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)['selected']['selection_status'], 'discouraged')

    def compare(self, alternatives, record):
        import render_contract
        args = ['assess', '--model-identifier', 'synthetic:portrait@1', '--service', 'synthetic-service',
                '--operation', 'generation', '--use-case', 'benign-minor-depiction',
                '--mode', 'reference-guided', '--reference-count', '2']
        for alternative in alternatives:
            args.extend(['--alternative-model', alternative])
        output = io.StringIO()
        with patch('prepare_generation_references.resolve_model_record', return_value=(record['id'], record)):
            with contextlib.redirect_stdout(output):
                code = render_contract.main(args)
        self.assertEqual(code, 0, output.getvalue())
        return json.loads(output.getvalue())

    def test_cross_service_alternative_uses_its_own_offering(self):
        other = offering(); other.update(service='another-service', model_identifier='other:portrait@1')
        record = {**model(), 'id': 'another-portrait', 'offerings': [other]}
        result = self.compare(['another-portrait'], record)
        self.assertEqual(result['suggested_models'], [{'model': 'another-portrait', 'service': 'another-service',
                                                      'model_identifier': 'other:portrait@1'}])
        self.assertEqual(result['selected']['service'], 'synthetic-service')
        self.assertEqual(result['alternative_resolution_errors'], [])

    def test_unresolved_alternative_keeps_selected_assessment_and_other_candidates(self):
        other = offering(); other.update(service='another-service', model_identifier='other:portrait@1')
        record = {**model(), 'id': 'another-portrait', 'offerings': [other]}
        result = self.compare(['another-portrait=absent-service', 'another-portrait'], record)
        self.assertEqual(len(result['alternative_resolution_errors']), 1)
        self.assertEqual(result['alternative_resolution_errors'][0]['service'], 'absent-service')
        self.assertEqual(len(result['suggested_models']), 1)
        self.assertEqual(result['selected']['model_identifier'], 'synthetic:portrait@1')

    def test_multiple_offerings_need_the_alternatives_explicit_service(self):
        other = offering(); other.update(service='another-service', model_identifier='other:portrait@1')
        record = {**model(), 'offerings': [offering(), other]}
        result = self.compare(['synthetic-portrait', 'synthetic-portrait=another-service'], record)
        self.assertIn('several services', result['alternative_resolution_errors'][0]['reason'])
        self.assertEqual(result['suggested_models'][0]['service'], 'another-service')


class PackPreferenceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()  # canonical spelling, as in SuitabilityTests
        environment = patch.dict(os.environ, {'CPB_HOME': str(self.root / 'home')})
        environment.start()
        self.addCleanup(environment.stop)

    def test_active_pack_owns_preferences_and_exact_source_witness(self):
        pack = self.root / 'pack'
        pack_id, path = fixture_pack(pack, preferences())
        settings = fixture_runtime(self.root / 'runtime', [pack], enabled=[pack_id])
        with catalog_runtime.using_pack_runtime(settings):
            value, witness = s.load_preferences()
            card = r.model_card(model(), offering())['use_case_suitability']
        self.assertEqual(value, preferences())
        self.assertEqual(witness, {'path': str(path), 'sha256': c.digest(path.read_bytes()),
                                  'source_pack': pack_id, 'relative_path': 'resources/' + s.PREFERENCES_FILE})
        self.assertEqual(card['author_preferences'], value['entries'])
        self.assertEqual(card['preferences_source'], witness)
        self.assertFalse(s.preferences_path().exists())

    def test_disabled_and_unselected_packs_supply_no_preferences(self):
        pack = self.root / 'pack'
        pack_id, _ = fixture_pack(pack, preferences())
        for disabled in [[], [pack_id]]:
            with self.subTest(disabled=bool(disabled)):
                settings = fixture_runtime(self.root / 'runtime', [pack], disabled=disabled)
                before = settings.state_file.read_bytes()
                with catalog_runtime.using_pack_runtime(settings):
                    value, witness = s.load_preferences()
                self.assertEqual(value['entries'], [])
                self.assertIsNone(witness)
                self.assertEqual(settings.state_file.read_bytes(), before)

    def test_empty_or_complete_home_override_replaces_pack_policy_without_catalog_reads(self):
        pack = self.root / 'pack'
        pack_id, path = fixture_pack(pack, preferences())
        original = path.read_bytes()
        settings = fixture_runtime(self.root / 'runtime', [pack], enabled=[pack_id])
        replacement = preferences('no-discouragement')
        replacement['entries'][0]['selector']['model_patterns'] = [
            {'field': 'model-id', 'pattern': 'synthetic-other'}]
        for value in [replacement, {'artifact_type': 'model-selection-preferences', 'entries': []}]:
            with self.subTest(entries=len(value['entries'])):
                s.install_preferences(value)
                with catalog_runtime.using_pack_runtime(settings):
                    with patch.object(catalog_runtime, 'load_pack_catalog', side_effect=AssertionError('catalog read')):
                        loaded, witness = s.load_preferences()
                        card = r.model_card(model(), offering())['use_case_suitability']
                self.assertEqual(loaded, value)
                self.assertEqual(card['author_preferences'], [])
                self.assertEqual(witness['path'], str(s.preferences_path()))
                self.assertEqual(path.read_bytes(), original)

    def test_two_runtimes_keep_distinct_pack_preferences(self):
        settings = []
        for index, decision in enumerate(['discourage', 'no-discouragement']):
            pack = self.root / ('pack-' + str(index))
            pack_id, _ = fixture_pack(pack, preferences(decision))
            settings.append(fixture_runtime(self.root / ('runtime-' + str(index)), [pack], enabled=[pack_id]))
        with catalog_runtime.using_pack_runtime(settings[0]):
            first = r.model_card(model(), offering())['use_case_suitability']
            with catalog_runtime.using_pack_runtime(settings[1]):
                second = r.model_card(model(), offering())['use_case_suitability']
            restored = r.model_card(model(), offering())['use_case_suitability']
        self.assertEqual(first['author_preferences'][0]['preference'], 'discourage')
        self.assertEqual(second['author_preferences'][0]['preference'], 'no-discouragement')
        self.assertNotEqual(first['preferences_source']['source_pack'], second['preferences_source']['source_pack'])
        self.assertEqual(first, restored)

    def test_dependency_and_explicit_rank_select_one_whole_file(self):
        lower = self.root / 'lower'
        lower_id, _ = fixture_pack(lower, preferences())
        empty = {'artifact_type': 'model-selection-preferences', 'entries': []}
        higher = self.root / 'higher'
        higher_id, _ = fixture_pack(higher, empty, dependencies=[lower_id])
        ordered = self.root / 'ordered'
        ordered_id, _ = fixture_pack(ordered, empty)
        for selected, selected_id, order in [(higher, higher_id, []), (ordered, ordered_id, [ordered_id, lower_id])]:
            with self.subTest(pack=selected.name):
                settings = fixture_runtime(self.root / 'runtime', [lower, selected],
                    enabled=[lower_id, selected_id], order=order)
                with catalog_runtime.using_pack_runtime(settings):
                    value, witness = s.load_preferences()
                self.assertEqual(value, empty)
                self.assertEqual(witness['source_pack'], selected_id)

    def test_conflicting_policy_keeps_the_existing_resource_diagnostic(self):
        first = self.root / 'first'
        first_id, _ = fixture_pack(first, preferences())
        second = self.root / 'second'
        second_id, _ = fixture_pack(second, preferences('no-discouragement'))
        settings = fixture_runtime(self.root / 'runtime', [first, second], enabled=[first_id, second_id])
        with catalog_runtime.using_pack_runtime(settings):
            with self.assertRaises(ValueError) as caught:
                s.load_preferences()
        self.assertIn(s.PREFERENCES_RESOURCE, str(caught.exception))
        self.assertIn(first_id, str(caught.exception))
        self.assertIn(second_id, str(caught.exception))
        self.assertIn('pack_order', str(caught.exception))

    def test_invalid_bound_policy_fails_validation_locking_and_loading(self):
        from resource_policy import validate_known_resource
        pack = self.root / 'pack'
        pack_id, path = fixture_pack(pack, preferences())
        invalid = {'artifact_type': 'model-selection-preferences', 'entries': [{'id': 'incomplete'}]}
        path.write_bytes(c.encoded(invalid))
        expected = validate_known_resource(s.PREFERENCES_RESOURCE, invalid)
        self.assertTrue(expected)
        report = pm.validate_pack(pack, require_lock=False, verify_lock=False)
        self.assertTrue(any(issue.code == 'known-resource-contract' and expected[0] in issue.message
                            for issue in report.issues))
        with self.assertRaisesRegex(pm.PackError, 'invalid pack'):
            pm.write_lock(pack)
        settings = fixture_runtime(self.root / 'runtime', [pack], enabled=[pack_id])
        with catalog_runtime.using_pack_runtime(settings):
            with self.assertRaisesRegex(ValueError, 'known-resource-contract'):
                s.load_preferences()
            s.install_preferences(preferences('no-discouragement'))
            self.assertEqual(s.load_preferences()[0], preferences('no-discouragement'))

    def test_changed_locked_policy_is_not_silently_absent(self):
        pack = self.root / 'pack'
        pack_id, path = fixture_pack(pack, preferences())
        path.write_bytes(c.encoded(preferences('no-discouragement')))
        settings = fixture_runtime(self.root / 'runtime', [pack], enabled=[pack_id])
        with catalog_runtime.using_pack_runtime(settings):
            with self.assertRaisesRegex(ValueError, 'lock-file-mismatch'):
                s.load_preferences()
        pm.write_lock(pack)
        self.assertTrue(pm.validate_pack(pack).valid)
        with catalog_runtime.using_pack_runtime(settings):
            self.assertEqual(s.load_preferences()[0], preferences('no-discouragement'))

    def test_valid_policy_remains_usable_when_another_binder_is_invalid(self):
        from pack_cache import resource_warning
        packs = [self.root / 'first', self.root / 'second']
        values = [preferences(), preferences('no-discouragement')]
        fixtures = [fixture_pack(path, value) for path, value in zip(packs, values)]
        pack_ids = [row[0] for row in fixtures]
        settings = fixture_runtime(self.root / 'runtime', packs, enabled=pack_ids, order=pack_ids)
        for invalid_index in [1, 0]:
            with self.subTest(invalid_index=invalid_index):
                invalid_id, invalid_path = fixtures[invalid_index]
                invalid_path.write_bytes(invalid_path.read_bytes() + b'\n')
                valid_index = 1 - invalid_index
                with catalog_runtime.using_pack_runtime(settings):
                    value, witness = s.load_preferences()
                    catalog = catalog_runtime.load_pack_catalog()
                self.assertEqual(value, values[valid_index])
                self.assertEqual(witness['source_pack'], pack_ids[valid_index])
                self.assertIsNone(resource_warning(catalog, s.PREFERENCES_RESOURCE))
                self.assertTrue(any(row.get('pack_id') == invalid_id and row['code'] == 'invalid-enabled-pack'
                                    for row in catalog.diagnostics))
                self.assertTrue(any(invalid_id in line for line in catalog.warnings))
                pm.write_lock(packs[invalid_index])

    def test_unrelated_pack_error_does_not_claim_a_preference_owner(self):
        pack = self.root / 'pack'
        pack_id, path = fixture_pack(pack, preferences())
        manifest = pm.load_json(pack / 'pack.json')
        manifest['content']['resource_bindings'] = {}
        pm.atomic_write_json(pack / 'pack.json', manifest)
        path.write_text('invalid opaque resource', encoding='utf-8')
        settings = fixture_runtime(self.root / 'runtime', [pack], enabled=[pack_id])
        with catalog_runtime.using_pack_runtime(settings):
            value, witness = s.load_preferences()
        self.assertEqual(value['entries'], [])
        self.assertIsNone(witness)

    def test_explicit_cli_runtime_applies_to_inspection_model_alias_and_external_assessment(self):
        import render_contract
        from pack_runtime_cli import PackRuntimeContext
        pack = self.root / 'pack'
        pack_id, path = fixture_pack(pack, preferences(), include_model=True)
        settings = fixture_runtime(self.root / 'runtime', [pack], enabled=[pack_id])
        runtime_args = PackRuntimeContext(settings, (pack,)).command_arguments()
        commands = [
            ['preferences'],
            ['model', '--model', 'synthetic portrait alias'],
            ['assess', '--model-identifier', 'synthetic:portrait@1', '--service', 'synthetic-service',
             '--operation', 'generation', '--use-case', 'policy-sensitive-use',
             '--mode', 'reference-guided', '--reference-count', '2'],
        ]
        for command in commands:
            with self.subTest(command=command[0]):
                output = io.StringIO()
                with patch.object(catalog_runtime, 'load_runtime_catalog', wraps=catalog_runtime.load_runtime_catalog) as loader:
                    with contextlib.redirect_stdout(output):
                        code = render_contract.main(command + runtime_args)
                self.assertEqual(code, 0, output.getvalue())
                self.assertEqual(loader.call_count, 1)
                value = json.loads(output.getvalue())
                if command[0] == 'preferences':
                    self.assertEqual(value['preferences'], preferences())
                    witness = value['source']
                elif command[0] == 'model':
                    self.assertEqual(value['model'], 'synthetic-portrait')
                    self.assertEqual(value['use_case_suitability']['author_preferences'], preferences()['entries'])
                    witness = value['use_case_suitability']['preferences_source']
                else:
                    self.assertEqual(value['selected']['selection_status'], 'discouraged')
                    witness = value['selected']['preferences_source']
                self.assertEqual(witness['source_pack'], pack_id)
                self.assertEqual(witness['sha256'], c.digest(path.read_bytes()))


class FailureTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        environment = patch.dict(os.environ, {'CPB_HOME': str(self.root / 'home')})
        environment.start(); self.addCleanup(environment.stop)
        self.runtime = catalog_runtime.using_pack_runtime(fixture_runtime(self.root / 'runtime'))
        self.runtime.__enter__()
        self.addCleanup(self.runtime.__exit__, None, None, None)
        raw = c.encoded({'error': {'code': 'synthetic_moderation_block', 'message': 'Synthetic provider response.'}})
        (self.root / 'answer.json').write_bytes(raw)
        self.failure = {'artifact_type': 'generation-failure-assessment',
            'target': {'service': 'synthetic-service', 'model_identifier': 'synthetic:portrait@1', 'operation': 'generation'},
            'use_cases': ['benign-minor-depiction'], 'category': 'provider-moderation', 'basis': 'provider-response',
            'evidence': {'path': 'answer.json', 'sha256': c.digest(raw)},
            'signal': {'pointer': '/error/code', 'value': 'synthetic_moderation_block'},
            'reason': 'The synthetic response explicitly reports a moderation block.',
            'unmeasured': ['This fixture does not establish whether any real provider accepts the content.']}

    def test_explicit_provider_signal_is_verified(self):
        result = s.diagnose(self.failure, self.root)
        self.assertEqual(result['policy_relevance'], 'explicit-provider-moderation')
        self.assertFalse(result['automatic_retry'])

    def test_an_edited_response_or_invented_signal_is_rejected(self):
        value = copy.deepcopy(self.failure); value['signal']['value'] = 'invented'
        with self.assertRaisesRegex(ValueError, 'signal differs'): s.diagnose(value, self.root)
        (self.root / 'answer.json').write_text('{}', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'evidence changed'): s.diagnose(self.failure, self.root)

    def test_provider_signal_is_not_inferred_from_prompt_keywords(self):
        value = copy.deepcopy(self.failure); value['basis'] = 'operator-hypothesis'
        with self.assertRaisesRegex(ValueError, 'provider-response'): s.diagnose(value, self.root)
        value['category'] = 'timeout'
        with self.assertRaisesRegex(ValueError, 'keeps the failure category unknown'): s.diagnose(value, self.root)

    def test_unknown_with_matching_report_is_possible_not_confirmed(self):
        s.install_preferences(preferences())
        value = copy.deepcopy(self.failure); value['category'] = 'unknown'; value['basis'] = 'operator-hypothesis'
        result = s.diagnose(value, self.root)
        self.assertEqual(result['category'], 'unknown')
        self.assertEqual(result['policy_relevance'], 'possible-from-author-report')

    def test_unknown_with_aesthetic_preference_has_no_reported_policy_cause(self):
        prefs = preferences()
        item = prefs['entries'][0]
        item.update(reported_failure=None, reason='The author dislikes the watercolor texture.',
                    basis=basis('author-preference'))
        s.install_preferences(prefs)
        value = copy.deepcopy(self.failure)
        value.update(category='unknown', basis='operator-hypothesis', signal=None)
        result = s.diagnose(value, self.root)
        self.assertEqual(result['category'], 'unknown')
        self.assertEqual(result['policy_relevance'], 'unestablished')
        self.assertEqual(result['matching_author_reports'], [])
        self.assertNotIn('provider restrictions', result['next_action'])

    def test_unknown_with_quality_report_has_no_reported_policy_cause(self):
        prefs = preferences()
        prefs['entries'][0].update(reported_failure=None,
            reason='The author reports poor line quality, with no measured refusal behavior.')
        s.install_preferences(prefs)
        value = copy.deepcopy(self.failure)
        value.update(category='unknown', basis='operator-hypothesis', signal=None)
        result = s.diagnose(value, self.root)
        self.assertEqual(result['policy_relevance'], 'unestablished')
        self.assertEqual(result['matching_author_reports'], [])

    def test_unknown_uses_only_explicitly_reported_failures(self):
        prefs = preferences()
        unrelated = copy.deepcopy(prefs['entries'][0])
        unrelated.update(id='preferred-finish', reported_failure=None,
                         reason='The author prefers a different finish.', basis=basis('author-preference'))
        prefs['entries'].insert(0, unrelated)
        s.install_preferences(prefs)
        value = copy.deepcopy(self.failure)
        value.update(category='unknown', basis='operator-hypothesis', signal=None)
        result = s.diagnose(value, self.root)
        self.assertEqual(result['policy_relevance'], 'possible-from-author-report')
        self.assertEqual([item['id'] for item in result['matching_author_reports']], ['reported-refusal-avoidance'])

    def test_catalog_id_preferences_apply_to_the_verified_failure_target(self):
        value = preferences()
        value['entries'][0]['selector']['model_patterns'] = [{'field': 'model-id', 'pattern': 'synthetic-portrait*'}]
        s.install_preferences(value)
        failure = copy.deepcopy(self.failure); failure.update(category='unknown', basis='operator-hypothesis')
        record = {**model(), 'offerings': [offering()]}
        result = s.diagnose(failure, self.root, record=record)
        self.assertEqual(result['policy_relevance'], 'possible-from-author-report')
        self.assertEqual(result['catalog_model'], 'synthetic-portrait')
        self.assertIn('assess alternatives', result['next_action'])

    def test_failure_rejects_a_catalog_record_for_another_interface(self):
        other = offering(); other['model_identifier'] = 'synthetic:another@1'
        record = {**model(), 'offerings': [other]}
        with self.assertRaisesRegex(ValueError, 'does not match the saved'):
            s.diagnose(self.failure, self.root, record=record)

    def test_external_diagnosis_uses_its_explicit_pack_runtime(self):
        from pack_runtime_cli import PackRuntimeContext
        pack = self.root / 'pack'
        pack_id, _ = fixture_pack(pack, preferences())
        settings = fixture_runtime(self.root / 'diagnostic-runtime', [pack], enabled=[pack_id])
        failure = copy.deepcopy(self.failure)
        failure.update(category='unknown', basis='operator-hypothesis', signal=None)
        (self.root / 'failure.json').write_bytes(c.encoded(failure))
        command = [sys.executable, '-B', str(ROOT / 'scripts/render_contract.py'), 'diagnose',
                   '--root', str(self.root), '--failure', 'failure.json']
        result = subprocess.run(command + PackRuntimeContext(settings, (pack,)).command_arguments(),
                                text=True, encoding='utf-8', capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        value = json.loads(result.stdout)
        self.assertEqual(value['policy_relevance'], 'possible-from-author-report')
        self.assertEqual(value['preferences_source']['source_pack'], pack_id)

    def test_operational_errors_do_not_become_moderation_due_to_a_preference(self):
        s.install_preferences(preferences())
        for category in ['authentication', 'quota', 'rate-limit', 'timeout', 'transport', 'request-schema', 'reference-input']:
            value = copy.deepcopy(self.failure); value['category'] = category; value['basis'] = 'runtime-error'
            result = s.diagnose(value, self.root)
            self.assertEqual(result['policy_relevance'], 'unestablished', category)
            self.assertEqual(result['matching_author_reports'], [], category)

    def test_visual_failure_requires_review_and_describes_output_defects(self):
        value = copy.deepcopy(self.failure); value['category'] = 'output-artifact'
        with self.assertRaisesRegex(ValueError, 'visual-review'): s.validate_failure(value)
        raw = c.encoded({'defect': 'The subject is cropped outside the authored composition.'})
        (self.root / 'review.json').write_bytes(raw)
        value.update(basis='visual-review', evidence={'path': 'review.json', 'sha256': c.digest(raw)},
                     signal=None, reason='The synthetic review records a composition defect.')
        result = s.diagnose(value, self.root)
        self.assertEqual(result['category'], 'output-artifact')
        self.assertEqual(result['policy_relevance'], 'unestablished')
        self.assertEqual(result['matching_author_reports'], [])
        self.assertIn('composition or output defect', result['next_action'])
        self.assertNotIn('transport', result['next_action'])
        self.assertFalse(result['automatic_retry'])

    def test_failure_schema_matches_saved_signal_contract(self):
        from state_protocol import validate_against_schema
        schema = json.loads((ROOT / 'schemas/authoring/generation-failure-assessment.schema.json').read_text(encoding='utf-8'))
        self.assertEqual(validate_against_schema(self.failure, schema), [])
        value = copy.deepcopy(self.failure); value['signal'] = None
        self.assertTrue(validate_against_schema(value, schema))
        with self.assertRaisesRegex(ValueError, 'exact response signal'): s.validate_failure(value)


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
