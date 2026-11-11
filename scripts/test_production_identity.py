"""Exercise identity owners through production adapters and common authoring.

All images, sources and decisions are synthetic. Reference builders use an
isolated local model pack; no provider is contacted or visual verdict invented.
"""
from __future__ import annotations

import copy
import ctypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import execution_contract as c
import identity_coverage
import production_identity
import production_inputs
import production_inputs_smoke_test as input_fixtures
import production_reference_inputs as reference_inputs
import production_reference_inputs_smoke_test as reference_fixtures
import prepare_generation_references as references
from production_diagnostics import ProductionError
from reference_runtime_smoke_test import _fixture_png


def criterion(source_ids: list[str], subjects: list[str], *, carrier: dict | None = None,
              evidence='image') -> dict:
    """Explicit synthetic review choices, never used by operational authoring."""
    return {'id': 'continuity', 'strength': 'hard', 'evidence': evidence,
            'text': 'Compare the complete original identity sources and their conditions in this scene.',
            'identity_review': subjects,
            'identity_bindings': [{'source': ident, 'subject_ids': subjects, 'selectors': [''],
                'treatment': 'preserve', 'reason': 'The synthetic scene retains the selected original definition.',
                'variation': None, 'carriers': [copy.deepcopy(carrier or {
                    'kind': 'text', 'surface': 'primary', 'quote': 'Keep the adopted conditional details.'})]}
                for ident in source_ids]}


class IdentityAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='cpb-identity-adapter-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.spec = {'subjects': [{'id': 'A'}]}
        self.task = {'task_id': 'synthetic-scene', 'artifact': 'image', 'execution': 'external',
                     'features': [], 'sources': [], 'criteria': [], 'direction': {'decisions': []},
                     'generation': {'production_spec': 'spec.json'}}
        self.write('spec.json', self.spec)
        (self.root / 'original.png').write_bytes(_fixture_png())
        self.external = {'references': [{'id': 'accepted-angle', 'file': 'original.png', 'role': 'identity',
            'use_for': ['identity'], 'do_not_transfer': ['lighting'],
            'subject_uses': [{'subject_id': 'A', 'use': 'identity', 'priority': 0}]}],
            'external_request': {'request': {'prompt': 'Keep the adopted conditional details.', 'images': ['fixture-image']},
                'prompt_field': ['prompt'],
                'reference_fields': [{'reference': 'accepted-angle', 'field': ['images', 0], 'value': 'fixture-image'}]}}

    def read(self, path):
        return (self.root / path).read_bytes()

    def write(self, path, value):
        (self.root / path).write_bytes(c.encoded(value))

    def context(self, **kwargs):
        return production_identity.context(self.task, self.read, **kwargs)

    def compile(self, context):
        return identity_coverage.compile(self.task, self.read, context=context)

    def test_identity_reference_activates_without_recurring_feature_and_keeps_original(self):
        view = self.context(inputs=self.external)
        self.assertEqual(view['required_subject_ids'], ['A'])
        self.assertEqual([row['id'] for row in view['identity_sources']], ['reference:accepted-angle'])
        self.assertEqual(view['identity_sources'][0]['sha256'], c.digest(self.read('original.png')))
        with self.assertRaises(ProductionError):
            self.compile(view)
        self.task['criteria'] = [criterion(['reference:accepted-angle'], ['A'], carrier={
            'kind': 'reference', 'reference': 'accepted-angle', 'use': 'identity'})]
        report = self.compile(view)
        self.assertEqual(report['bindings'][0]['carriers'][0]['request_fields'], [['images', 0]])
        self.assertEqual(self.task['features'], [])

    def test_identity_reference_without_any_cast_cannot_silently_disappear(self):
        self.task['generation'] = {}
        self.external['references'][0]['subject_uses'] = []
        with self.assertRaisesRegex(ValueError, 'subject|cast'):
            self.context(inputs=self.external)

    def test_every_selected_graph_owner_is_inventoried_without_a_feature(self):
        nodes = {name: {'canon_status': 'adopted', 'arbitrary_condition': 'The new seam closes only after contact.'}
                 for name in production_identity.IDENTITY_NODES}
        nodes['identity_contract']['character_id'] = 'A'
        nodes['individual_morphology']['fine/free~form'] = {'relation': ['A fits inside its open frame only when turned.']}
        self.write('graph.json', [nodes])
        self.task['generation']['state_graphs'] = 'graph.json'
        view = self.context()
        expected = {'state:A:' + node for node in nodes}
        self.assertEqual({row['id'] for row in view['identity_sources']}, expected)
        self.assertEqual(view['required_subject_ids'], ['A'])
        self.assertEqual({row['sha256'] for row in view['identity_sources']}, {c.digest(self.read('graph.json'))})
        report = identity_coverage.inventory(self.task, self.read, context=view)
        self.assertEqual({row['source'] for row in report['uncovered']}, expected)
        with self.assertRaises(ProductionError):
            self.compile(view)

    def test_partial_explicit_source_cannot_hide_unprocessed_graph_owner(self):
        graph = [{'identity_contract': {'character_id': 'A', 'stable': {'shape': 'open loop'},
                                        'conditional_detail': 'The seam is offset while under tension.'}}]
        self.write('graph.json', graph)
        self.task['generation']['state_graphs'] = 'graph.json'
        self.task['sources'] = [{'id': 'selected-shape', 'path': 'graph.json', 'role': 'identity',
            'disposition': 'applied', 'locator': 'stable shape', 'reason': 'Explicit partial scope.',
            'identity': {'subject_ids': ['A'], 'selectors': ['/0/identity_contract/stable']}}]
        view = self.context()
        self.assertEqual([row['id'] for row in view['identity_sources']], ['state:A:identity_contract'])
        self.task['sources'][0]['identity']['selectors'] = ['/0/identity_contract']
        self.assertEqual(self.context()['identity_sources'], [])

    def test_optional_visual_owners_require_authored_treatment_without_becoming_canon(self):
        graph = [{'identity_contract': {'character_id': 'A', 'canon_status': 'adopted',
                                       'definition': 'An open loop with its adopted conditional split.'},
                  'visual_authority': {'mode': 'source-derived',
                      'authority_scope': 'The source governs finish evidence only when the rim is directly lit.',
                      'notes': ['If highlights obscure the split, the adopted identity definition has priority.']},
                  'visual_evidence_bundle': {'disposition': 'observed-not-adopted',
                      'evidence_relation': 'Shows the near surface; the far side remains outside this evidence.',
                      'semantic_summary': 'An observed bright edge does not establish a permanent marking.',
                      'notes': ['The lower seam note applies only to the source camera and recorded illumination.']}}]
        self.write('graph.json', graph)
        self.task['generation']['state_graphs'] = 'graph.json'
        self.task['criteria'] = [criterion(['state:A:identity_contract'], ['A'])]
        view = self.context(rendered={'request': {'prompt': 'Keep the adopted conditional details.'},
            'layout': {'primary_text': ['prompt'], 'negative_text': None, 'media': []}, 'media': []})
        report = identity_coverage.inventory(self.task, self.read, context=view)
        expected = {'state:A:visual_authority', 'state:A:visual_evidence_bundle'}
        self.assertEqual({row['source'] for row in report['uncovered']}, expected)
        sources = {row['id']: row for row in report['sources']}
        for node in ('visual_authority', 'visual_evidence_bundle'):
            selected = sources['state:A:' + node]
            self.assertEqual(selected['authority']['owner'], node)
            self.assertIsNone(selected['authority']['canon_status'])
            self.assertEqual(selected['value_sha256'], c.content_id(graph[0][node]))
            self.assertTrue(all(not terminal['coverage'] for terminal in selected['terminals']))
        bundle_values = {row['pointer']: row['value'] for row in sources['state:A:visual_evidence_bundle']['terminals']}
        self.assertEqual(bundle_values['/disposition'], 'observed-not-adopted')
        self.assertEqual(bundle_values['/evidence_relation'], graph[0]['visual_evidence_bundle']['evidence_relation'])
        with self.assertRaises(ProductionError):
            self.compile(view)
        context_check = criterion(sorted(expected), ['A'])
        context_check.update(id='visual-source-scope', strength='advisory')
        context_check.pop('identity_review')
        for obligation in context_check['identity_bindings']:
            obligation.update(treatment='not-applicable', carriers=[],
                reason='These original documents bound the fixture evidence; this scene does not adopt their observed finish as identity.')
        self.task['criteria'].append(context_check)
        covered = self.compile(view)
        self.assertTrue(covered['structural_only'])
        self.assertEqual(covered['uncovered'], [])
        self.assertTrue(all(row['treatment'] == 'not-applicable' for row in covered['bindings'][1:]))

    def test_actual_filtered_prompt_never_inherits_omitted_authoring_details(self):
        self.task['criteria'] = [criterion(['reference:accepted-angle'], ['A'])]
        self.task['delivery'] = {'path': 'authoring.txt'}
        (self.root / 'authoring.txt').write_text('Keep the adopted conditional details.', encoding='utf-8')
        self.external['external_request']['request']['prompt'] = 'An abbreviated description after rendering.'
        view = self.context(inputs=self.external)
        self.assertEqual(view['text']['primary']['text'], 'An abbreviated description after rendering.')
        with self.assertRaises(ProductionError) as caught:
            self.compile(view)
        self.assertEqual(caught.exception.diagnostic.code, 'IDENTITY_CARRIER_MISSING')

    def test_external_field_mismatch_does_not_claim_reference_delivery(self):
        self.external['external_request']['request']['images'][0] = 'different-image'
        with self.assertRaisesRegex(ValueError, 'external request'):
            self.context(inputs=self.external)

    def test_recurring_continuity_requires_identity_even_without_media_or_feature(self):
        for visual, generation in [({'subjects': {'A': {'continuity': 'recurring', 'identity_refs': []}}}, {}),
                                   (None, {'continuity': {'A': 'recurring'}})]:
            with self.subTest(visual=visual):
                self.task['generation'].update(generation)
                view = self.context(visual=visual)
                self.assertEqual(view['required_subject_ids'], ['A'])
                report = identity_coverage.inventory(self.task, self.read, context=view)
                self.assertEqual(report['missing_subject_sources'], ['A'])
                with self.assertRaises(ProductionError):
                    self.compile(view)

    def test_nonidentity_reference_use_does_not_invent_identity_authority(self):
        row = self.external['references'][0]
        row.update(use_for=['pose-camera'], do_not_transfer=['identity'],
                   subject_uses=[{'subject_id': 'A', 'use': 'pose-camera', 'priority': 0}])
        view = self.context(inputs=self.external)
        self.assertEqual(view['required_subject_ids'], [])
        self.assertEqual(view['identity_sources'], [])


class PreparedIdentityCarrierTests(unittest.TestCase):
    setUp = reference_fixtures.ReferenceInputTests.setUp
    activate = reference_fixtures.ReferenceInputTests.activate
    direct = reference_fixtures.ReferenceInputTests.direct
    build = reference_fixtures.ReferenceInputTests.build

    def read(self, path):
        selected = Path(path)
        if selected.is_absolute():
            return selected.read_bytes()
        if (self.root / selected).is_file():
            return (self.root / selected).read_bytes()
        return (self.prepared_root / selected).read_bytes()

    def prepared(self, name, *, mode='multi-image'):
        choices = reference_inputs.draft(None, package_root=self.root)
        choices.update(transport_mode=mode, max_side=128 if mode == 'single-board' else 16)
        choices['additional_references'] = [self.direct(0), self.direct(1, subject='B')]
        (self.root / 'shape.svg').write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="24" viewBox="0 0 40 24">'
            '<rect width="40" height="24" fill="#3c5a78"/></svg>', encoding='utf-8')
        choices['additional_references'][0]['source']['resolved_path'] = 'shape.svg'
        result = self.build(choices, name)
        self.prepared_root = self.root / name
        return result

    def rendered(self, prepared):
        media = references.host_reference_transports(prepared, package_root=self.prepared_root)
        for row in media:
            self.assertEqual(c.digest(Path(row['resolved_path']).read_bytes()), row['sha256'])
        return {'request': {'prompt': 'Keep the adopted conditional details.',
                            'negative': 'Do not merge the subjects.',
                            'images': ['synthetic-media-' + str(index) for index in range(len(media))]},
                'layout': {'primary_text': ['prompt'], 'negative_text': ['negative'],
                           'media': [{'index': index, 'field': ['images', index]} for index in range(len(media))]},
                'media': media}

    def task_context(self, prepared, rendered):
        task = {'task_id': 'prepared-scene', 'artifact': 'image', 'features': [],
                'sources': [], 'criteria': [], 'direction': {'decisions': []}}
        package = {'production_spec': {'subjects': [{'id': 'A'}, {'id': 'B'}]},
                   'prepared_reference_set': prepared}
        view = production_identity.context(task, self.read, package=package, rendered=rendered)
        task['criteria'] = []
        for index, row in enumerate(view['references']):
            check = criterion(['reference:' + row['id']], row['subject_ids'], carrier={
                'kind': 'reference', 'reference': row['id'], 'use': 'identity'})
            check['id'] += '-' + str(index)
            task['criteria'].append(check)
        return task, view

    def test_real_resized_media_retains_original_and_every_actual_request_mapping(self):
        prepared = self.prepared('scaled')
        rendered = self.rendered(prepared)
        rendered['request']['auxiliary'] = [rendered['request']['images'][0]]
        rendered['layout']['media'].append({'index': 0, 'field': ['auxiliary', 0]})
        task, view = self.task_context(prepared, rendered)
        report = identity_coverage.compile(task, self.read, context=view)
        carrier = report['bindings'][0]['carriers'][0]
        self.assertNotEqual(carrier['reference_source_sha256'], carrier['carrier_sha256'])
        self.assertEqual(carrier['request_fields'], [['images', 0], ['auxiliary', 0]])
        self.assertEqual(carrier['derivation'], prepared['selected_references'][0]['transport']['derivation'])
        self.assertEqual(carrier['controls'], prepared['selected_references'][0]['authority']['controls'])
        self.assertIn('identity', carrier['intended_influence'])

    def test_board_regions_share_one_delivered_carrier_and_preserve_subject_assignments(self):
        prepared = self.prepared('board', mode='single-board')
        rendered = self.rendered(prepared)
        task, view = self.task_context(prepared, rendered)
        report = identity_coverage.compile(task, self.read, context=view)
        witnesses = [row['carriers'][0] for row in report['bindings']]
        self.assertEqual({row['carrier_sha256'] for row in witnesses}, {prepared['single_board']['sha256']})
        self.assertEqual([row['region_pixels'] for row in witnesses],
                         [panel['box'] for panel in prepared['single_board']['panels']])
        self.assertEqual([row['subject_ids'] for row in witnesses], [['A'], ['B']])
        self.assertEqual([row['request_fields'] for row in witnesses], [[['images', 0]], [['images', 0]]])

    def test_native_ids_survive_reordering_and_distinguish_shared_artifact_scopes(self):
        prepared = self.prepared('first')
        original = self.task_context(prepared, self.rendered(prepared))[1]
        edited = reference_inputs.draft(prepared, package_root=self.prepared_root)
        edited['additional_references'].reverse()
        reordered = self.build(edited, 'reordered')
        self.prepared_root = self.root / 'reordered'
        changed = self.task_context(reordered, self.rendered(reordered))[1]
        self.assertEqual([row['id'] for row in changed['references']],
                         list(reversed([row['id'] for row in original['references']])))
        selected = reference_inputs.draft(prepared, package_root=self.root / 'first')
        another_use = copy.deepcopy(selected['additional_references'][0])
        another_use.pop('id')
        another_use['subject_uses'] = [{'subject_id': 'B', 'use': 'identity', 'priority': 0}]
        selected['additional_references'].append(another_use)
        shared = self.build(selected, 'shared-source')
        left, right = shared['selected_references'][0], shared['selected_references'][2]
        self.assertEqual(left['source']['sha256'], right['source']['sha256'])
        self.assertNotEqual(production_identity.reference_id(left), production_identity.reference_id(right))
        moved = copy.deepcopy(left)
        moved['transport']['resolved_path'] = 'elsewhere.png'
        self.assertEqual(production_identity.reference_id(left), production_identity.reference_id(moved))


class AuthoringTargetScopeTests(unittest.TestCase):
    def test_current_scope_names_the_single_selected_target(self):
        from production_authoring_state import _scope
        with tempfile.TemporaryDirectory(prefix='cpb-target-scope-') as temporary:
            root = Path(temporary)
            (root / 'model.json').write_bytes(c.encoded({'id': 'synthetic-acquired-model'}))
            cases = [
                ('authored', {'kind': 'catalog', 'model': 'model:synthetic', 'service': 'service:synthetic'},
                 'model:synthetic', 'service:synthetic'),
                ('authored', {'kind': 'acquired', 'model_file': 'model.json', 'service': None},
                 'synthetic-acquired-model', None),
                ('external', {'kind': 'external', 'model': {'requested': 'Synthetic external target',
                    'target': {'model_identifier': 'synthetic-wire-model', 'service': 'synthetic-host',
                               'operation': 'image-generation'}}}, 'synthetic-wire-model', 'synthetic-host'),
                ('authored', None, None, None),
            ]
            for execution, target, model, service in cases:
                with self.subTest(target=target):
                    task = {'route': 'prompt-only' if execution == 'authored' else 'generation',
                            'features': [], 'execution': execution}
                    scope = _scope(task, root=root, choices={'target': target})
                    self.assertEqual((scope['model'], scope['service']), (model, service))


class IdentityAuthoringTests(unittest.TestCase):
    setUp = input_fixtures.InputToolsTests.setUp
    save_choices = input_fixtures.InputToolsTests.save_choices

    def draft_identity(self, *, graph=False, visual_context=False):
        import work_ledger
        self.task['task_id'] = work_ledger.begin(self.root, 'Synthetic identity authoring.', ['Compose'])['task_id']
        value = {'identity': {'outline': 'An open loop with one split only while under tension.'}}
        selector = ''
        if graph:
            value = [{'identity_contract': {'character_id': 'A', 'canon_status': 'adopted', **value},
                      'state_snapshot': {'scene_state': 'At rest.'}}]
            if visual_context:
                value[0]['visual_authority'] = {'mode': 'source-derived',
                    'authority_scope': 'Visible finish only, subordinate to adopted shape.',
                    'notes': ['The far side remains outside this evidence.']}
                value[0]['visual_evidence_bundle'] = {'disposition': 'observed-not-adopted',
                    'evidence_relation': 'The original camera exposes the near rim only.'}
            selector = '/0/identity_contract'
            self.task['generation'] = {'state_graphs': 'canon.json'}
        self.raw = c.encoded(value)
        (self.root / 'canon.json').write_bytes(self.raw)
        self.task['sources'] = [{'id': 'canon', 'path': 'canon.json', 'role': 'identity',
            'disposition': 'applied', 'locator': 'whole original', 'reason': 'Explicit fixture authority.',
            'identity': {'subject_ids': ['A'], 'selectors': [selector]}}]
        self.task['criteria'] = [criterion(['canon'], ['A'], evidence='text')]
        self.task['criteria'][0]['identity_bindings'][0]['selectors'] = [selector]
        (self.root / 'task.json').write_bytes(c.encoded(self.task))
        result = production_inputs.draft_inputs(self.root, 'task.json', 'identity-draft')
        choices = c.load(self.root / result['choices_file'])
        choices['reading'] = copy.deepcopy(self.choices['reading'])
        return result, choices

    def build_identity(self, result, choices, destination='identity-built'):
        (self.root / result['choices_file']).write_bytes(c.encoded(choices))
        return production_inputs.build_inputs(self.root, None, result['choices_file'], destination)

    def compile_identity(self, result, choices):
        (self.root / result['choices_file']).write_bytes(c.encoded(choices))
        return production_inputs.compile_choices(self.root, result['choices_file']).report

    def recovery(self, diagnostic):
        action = diagnostic['next_action']
        self.assertEqual(diagnostic['next_actions'], [action])
        result = subprocess.run(action['argv'], cwd=self.root, capture_output=True,
                                text=True, encoding='utf-8', check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_common_draft_exposes_original_values_and_build_preserves_source_owner(self):
        result, choices = self.draft_identity()
        self.assertNotIn('canon', choices['authoring']['sources'])
        self.assertEqual(choices['authoring']['source_files']['canon.json'], c.digest(self.raw))
        self.assertEqual(result['identity_coverage']['sources'][0]['sha256'], c.digest(self.raw))
        self.assertFalse(result['identity_coverage']['request_verified'])
        built = self.build_identity(result, choices)
        self.assertTrue(built['ok'], built.get('unresolved'))
        task = c.load(self.root / built['inputs']['production-task']['path'])
        self.assertEqual(task['sources'][0]['path'], 'canon.json')
        self.assertEqual((self.root / 'canon.json').read_bytes(), self.raw)
        self.assertEqual(task['criteria'], self.task['criteria'])

    def test_missing_whole_subject_review_names_the_criterion_to_add(self):
        from validate import markdown_anchor_slugs
        result, choices = self.draft_identity()
        for check in choices['authoring']['task']['criteria']:
            check.pop('identity_review', None)
        report = self.compile_identity(result, choices)
        self.assertFalse(report['ok'])
        diagnostic = next(row for row in report['diagnostics'] if row['code'] == 'IDENTITY_COVERAGE_INCOMPLETE')
        self.assertEqual((diagnostic['pointer'], diagnostic['phase'], diagnostic['gaps']),
                         ('authoring.task.criteria', 'identity-coverage', {'missing_whole_reviews': ['A']}))
        self.assertIn('identity_review', diagnostic['required_action'])
        self.assertIn('authoring.task.criteria', diagnostic['required_action'])
        path, _, anchor = diagnostic['guidance']['document_path'].partition('#')
        self.assertIn(anchor, markdown_anchor_slugs(production_inputs.ROOT / path))

    def test_changed_original_requires_current_judgment_before_reusing_draft(self):
        result, choices = self.draft_identity()
        changed = c.encoded({'identity': {'new_condition': 'The split now closes at rest.'}})
        (self.root / 'canon.json').write_bytes(changed)
        report = self.compile_identity(result, choices)
        self.assertFalse(report['ok'])
        diagnostic = report['diagnostics'][0]
        self.assertEqual(diagnostic['code'], 'IDENTITY_SOURCE_CHANGED')
        self.assertEqual(diagnostic['file'], 'canon.json')
        self.assertEqual(diagnostic['expected_sha256'], c.digest(self.raw))
        self.assertEqual(diagnostic['actual_sha256'], c.digest(changed))
        self.assertEqual(diagnostic['next_action']['command'], 'draft-inputs')
        restored = self.recovery(diagnostic)
        self.assertEqual(restored['identity_coverage']['sources'][0]['sha256'], c.digest(changed))
        self.assertEqual(c.load(self.root / result['choices_file']), choices)
        self.assertNotEqual(restored['choices_file'], result['choices_file'])
        self.assertFalse((self.root / 'identity-built').exists())

    def test_unregistered_copy_identifies_registration_and_inspects_owned_work(self):
        result, choices = self.draft_identity()
        shutil.copytree(self.root / 'identity-draft', self.root / 'copied-draft')
        copied = {**result, 'choices_file': 'copied-draft/choices.json'}
        context_path = self.root / 'copied-draft/context.json'
        context = c.load(context_path)
        context['derived_from']['source_run'] = {'run': 'untrusted-origin', 'input_sha256': 'f' * 64}
        context_path.write_bytes(c.encoded(context))
        report = self.compile_identity(copied, choices)
        diagnostic = report['diagnostics'][0]
        self.assertEqual(diagnostic['code'], 'AUTHORING_DRAFT_UNREGISTERED')
        self.assertEqual(diagnostic['file'], 'copied-draft/context.json')
        self.assertEqual(diagnostic['next_action']['command'], 'inspect-inputs')
        self.assertNotIn('untrusted-origin', diagnostic['next_action']['argv'])
        inspected = self.recovery(diagnostic)
        self.assertEqual(inspected['task_id'], self.task['task_id'])
        self.assertIn('identity-draft', [row['directory'] for row in inspected['inputs']])

    def test_missing_context_names_its_file_and_returns_executable_redraft(self):
        result, choices = self.draft_identity()
        (self.root / result['context_file']).unlink()
        report = self.compile_identity(result, choices)
        diagnostic = report['diagnostics'][0]
        self.assertEqual(diagnostic['code'], 'AUTHORING_CONTEXT_MISSING')
        self.assertEqual(diagnostic['file'], result['context_file'])
        self.assertEqual(diagnostic['next_action']['command'], 'draft-inputs')
        restored = self.recovery(diagnostic)
        self.assertTrue((self.root / restored['context_file']).is_file())
        self.assertEqual(c.load(self.root / result['choices_file']), choices)

    def test_unavailable_identity_source_names_source_inspection(self):
        result, choices = self.draft_identity()
        (self.root / 'canon.json').unlink()
        report = self.compile_identity(result, choices)
        diagnostic = report['diagnostics'][0]
        self.assertEqual(diagnostic['code'], 'IDENTITY_SOURCE_UNAVAILABLE')
        self.assertEqual(diagnostic['file'], 'canon.json')
        self.assertEqual(diagnostic['next_action']['command'], 'inspect-inputs')
        inspected = self.recovery(diagnostic)
        self.assertFalse(next(row for row in inspected['sources'] if row['id'] == 'canon')['present'])

    def test_editable_copy_cannot_redefine_original_identity(self):
        result, choices = self.draft_identity()
        choices['authoring']['sources']['canon'] = {'format': 'json', 'content': {'identity': 'a different design'}}
        built = self.build_identity(result, choices)
        self.assertFalse(built['ok'])
        self.assertIn('owning source', built['unresolved'][0]['message'])
        self.assertEqual((self.root / 'canon.json').read_bytes(), self.raw)

    def test_missing_editable_hash_cannot_erase_the_drafts_original_source_snapshot(self):
        result, choices = self.draft_identity()
        choices['authoring']['source_files'].pop('canon.json')
        (self.root / 'canon.json').write_bytes(c.encoded({'identity': {'new_detail': 'A newly added fine break.'}}))
        built = self.build_identity(result, choices)
        self.assertFalse(built['ok'])
        self.assertFalse((self.root / 'identity-built').exists())

    def test_replacing_editable_hash_cannot_approve_changed_original_source(self):
        result, choices = self.draft_identity()
        changed = c.encoded({'identity': {'new_detail': 'A fine break not examined in this draft.'}})
        (self.root / 'canon.json').write_bytes(changed)
        choices['authoring']['source_files']['canon.json'] = c.digest(changed)
        built = self.build_identity(result, choices)
        self.assertFalse(built['ok'])
        self.assertEqual(built['unresolved'][0]['code'], 'IDENTITY_SOURCE_CHANGED')
        self.assertFalse((self.root / 'identity-built').exists())

    def test_removing_derived_context_evidence_cannot_bypass_registered_originals(self):
        result, choices = self.draft_identity()
        context_path = self.root / result['context_file']
        context = c.load(context_path)
        context.pop('identity_coverage')
        context_path.write_bytes(c.encoded(context))
        choices['authoring']['source_files'].pop('canon.json')
        report = self.compile_identity(result, choices)
        self.assertFalse(report['ok'])
        diagnostic = report['diagnostics'][0]
        self.assertEqual(diagnostic['code'], 'AUTHORING_CONTEXT_MISMATCH')
        self.assertEqual(diagnostic['file'], result['context_file'])
        self.assertEqual(diagnostic['next_action']['command'], 'draft-inputs')
        state = production_inputs.inspect_inputs(self.root)
        current = next(row for row in state['inputs'] if row['current'])
        self.assertEqual(current['diagnostics'][0]['code'], diagnostic['code'])
        self.assertEqual(current['next_actions'], diagnostic['next_actions'])
        restored = self.recovery(diagnostic)
        self.assertIn('identity_coverage', c.load(self.root / restored['context_file']))
        self.assertFalse((self.root / 'identity-built').exists())

    @unittest.skipUnless(os.name == 'nt', 'Windows 8.3 path aliases require Windows')
    def test_identity_recovery_uses_the_same_canonical_root_as_continuation(self):
        result, choices = self.draft_identity()
        context_path = self.root / result['context_file']
        context = c.load(context_path)
        context.pop('identity_coverage')
        context_path.write_bytes(c.encoded(context))
        choices['authoring']['source_files'].pop('canon.json')
        buffer = ctypes.create_unicode_buffer(1024)
        available = ctypes.windll.kernel32.GetShortPathNameW(str(self.root), buffer, len(buffer))
        if not available:
            self.skipTest('8.3 short names are unavailable on this volume')
        report = production_inputs.compile_choices(Path(buffer.value), result['choices_file']).report
        diagnostic = report['diagnostics'][0]
        current = next(row for row in production_inputs.inspect_inputs(self.root)['inputs'] if row['current'])
        self.assertEqual(current['next_actions'], diagnostic['next_actions'])
        self.assertEqual(diagnostic['next_action']['argv'][4], str(self.root.resolve()))
        restored = self.recovery(diagnostic)
        self.assertIn('identity_coverage', c.load(self.root / restored['context_file']))

    def test_editing_graph_owner_requires_its_existing_authority_workflow(self):
        result, choices = self.draft_identity(graph=True)
        choices['authoring']['documents']['state_graphs'][0]['identity_contract']['identity']['outline'] = 'A closed solid disc.'
        built = self.build_identity(result, choices)
        self.assertFalse(built['ok'])
        gap = built['unresolved'][0]
        self.assertEqual((gap['code'], gap['reason'], gap['field']),
                         ('AUTHORED_CHOICE_REQUIRED', 'current-judgment-required', 'authoring.documents.state_graphs'))
        self.assertIn('authoring.documents.state_graphs', gap['required_action'])
        self.assertEqual((self.root / 'canon.json').read_bytes(), self.raw)

    def test_scene_snapshot_edit_preserves_original_graph_identity_source(self):
        result, choices = self.draft_identity(graph=True)
        choices['authoring']['documents']['state_graphs'][0]['state_snapshot']['scene_state'] = 'Under the selected tension.'
        built = self.build_identity(result, choices)
        self.assertTrue(built['ok'], built.get('unresolved'))
        task = c.load(self.root / built['inputs']['production-task']['path'])
        self.assertEqual(task['sources'][0]['path'], 'canon.json')
        self.assertNotEqual(task['generation']['state_graphs'], 'canon.json')
        materialized = c.load(self.root / task['generation']['state_graphs'])
        self.assertEqual(materialized[0]['state_snapshot']['scene_state'], 'Under the selected tension.')
        self.assertEqual((self.root / 'canon.json').read_bytes(), self.raw)

    def test_optional_visual_owner_scope_cannot_be_rewritten_in_a_retained_scene_draft(self):
        result, choices = self.draft_identity(graph=True, visual_context=True)
        graph = choices['authoring']['documents']['state_graphs'][0]
        graph['visual_authority']['authority_scope'] = 'Now governs every permanent shape without the original limit.'
        graph['visual_evidence_bundle']['disposition'] = 'adopted'
        built = self.build_identity(result, choices)
        self.assertFalse(built['ok'])
        gap = built['unresolved'][0]
        self.assertEqual((gap['code'], gap['reason'], gap['field']),
                         ('AUTHORED_CHOICE_REQUIRED', 'current-judgment-required', 'authoring.documents.state_graphs'))
        self.assertEqual((self.root / 'canon.json').read_bytes(), self.raw)


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
