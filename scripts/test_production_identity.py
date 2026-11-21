"""Exercise identity owners through production adapters and common authoring.

All images, sources and decisions are synthetic. Reference builders use an
isolated local model pack; no provider is contacted or visual verdict invented.
"""
from __future__ import annotations
import production_fixtures as authoring_fixtures

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
import authoring_work as common_work
import production_case_fixtures as cases
import identity_coverage
import production_identity
import production_inputs
import production_inputs_smoke_test as input_fixtures
import production_reference_inputs as reference_inputs
import production_reference_inputs_smoke_test as reference_fixtures
import generation_references as references
from production_diagnostics import CompilationError, ProductionError
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
        self.assertEqual({row['source'] for row in report['unbound_source_values']}, expected)
        with self.assertRaises(ProductionError):
            self.compile(view)
        self.task['criteria'] = [{'id': 'whole-identity', 'strength': 'hard', 'evidence': 'image',
            'text': 'Compare the depicted identity with every applicable retained source at this view.',
            'identity_review': ['A']}]
        retained = self.compile(view)
        self.assertEqual({row['id'] for row in retained['sources']}, expected)
        self.assertEqual(retained['bindings'], [])

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
        self.assertEqual([row['id'] for row in self.context()['identity_sources']], ['state:A:identity_contract'])
        self.task['sources'][0]['identity']['authority'] = copy.deepcopy(view['identity_sources'][0]['authority'])
        self.assertEqual(self.context()['identity_sources'], [])

    def test_retained_scoped_reference_does_not_replace_a_distinct_current_use(self):
        view = self.context(inputs=self.external)
        authority = copy.deepcopy(view['identity_sources'][0]['authority'])
        authority['reference'] = 'prior-angle'
        authority['controls'] = ['outer silhouette only']
        self.task['sources'] = [{'id': 'retained-angle', 'path': 'original.png', 'role': 'identity',
            'disposition': 'applied', 'locator': 'whole original', 'reason': 'Retained scoped source.',
            'identity': {'subject_ids': ['A'], 'selectors': [''], 'authority': authority}}]
        view = self.context(inputs=self.external)
        self.assertEqual([row['id'] for row in view['identity_sources']], ['reference:accepted-angle'])
        self.task['criteria'] = [{'id': 'whole', 'strength': 'hard', 'evidence': 'image',
            'text': 'Compare the observed subject with the retained scoped originals.', 'identity_review': ['A']}]
        report = self.compile(view)
        sources = {row['id']: row for row in report['sources']}
        self.assertEqual(sources['retained-angle']['authority'], authority)
        self.assertEqual(sources['reference:accepted-angle']['authority'], view['identity_sources'][0]['authority'])
        self.assertEqual(report['bindings'], [])

    def test_optional_visual_owners_remain_context_without_forcing_scene_treatments(self):
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
        self.assertEqual({row['source'] for row in report['unbound_source_values']}, expected)
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
        retained = self.compile(view)
        self.assertEqual({row['source'] for row in retained['unbound_source_values']}, expected)
        self.assertEqual(len(retained['bindings']), 1)
        context_check = criterion(sorted(expected), ['A'])
        context_check.update(id='visual-source-scope', strength='advisory')
        context_check.pop('identity_review')
        for obligation in context_check['identity_bindings']:
            obligation.update(treatment='not-applicable', carriers=[],
                reason='These original documents bound the fixture evidence; this scene does not adopt their observed finish as identity.')
        self.task['criteria'].append(context_check)
        covered = self.compile(view)
        self.assertTrue(covered['structural_only'])
        self.assertEqual(covered['unbound_source_values'], [])
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
    save_choices = input_fixtures.InputToolsTests.save_choices

    def setUp(self):
        input_fixtures.InputToolsTests.setUp(self, draft=False)

    def draft_identity(self, *, graph=False, visual_context=False, retained_authority=False):
        import work_ledger
        self.task['task_id'] = work_ledger.begin(self.root, 'Synthetic identity authoring.', ['Compose'])['task_id']
        self.task['authority'] = None
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
        if retained_authority:
            self.task['sources'][0]['identity']['authority'] = {
                'owner': 'identity_contract', 'character_id': 'A', 'canon_status': 'adopted'}
        self.task['criteria'] = [criterion(['canon'], ['A'], evidence='text')]
        self.task['criteria'][0]['identity_bindings'][0]['selectors'] = [selector]
        self.task['direction']['basis'] = ['canon']
        (self.root / self.task['delivery']['path']).write_text(
            'Keep the adopted conditional details.\n', encoding='utf-8')
        authoring_fixtures.bind_work_basis(self.root, self.task,
            request='Depict the acquired synthetic identity while retaining its adopted conditions.')
        (self.root / 'task.json').write_bytes(c.encoded(self.task))
        result = authoring_fixtures.authoring_inputs(self.root, 'task.json', 'identity-draft')
        choices = c.load(self.root / result['choices_file'])
        choices['reading'] = copy.deepcopy(self.choices['reading'])
        return result, choices

    def build_identity(self, result, choices, destination='identity-built'):
        (self.root / result['choices_file']).write_bytes(c.encoded(choices))
        return production_inputs.build_inputs(self.root, None, result['choices_file'], destination)

    def compile_identity(self, result, choices):
        (self.root / result['choices_file']).write_bytes(c.encoded(choices))
        compiled = production_inputs.compile_choices(self.root, result['choices_file'])
        if compiled.directory is not None:
            self.addCleanup(shutil.rmtree, compiled.directory, ignore_errors=True)
        return compiled.report

    def work_basis(self, result):
        path = self.root / result['authoring_work']['basis']
        return path, c.load(path)

    def selected_source(self, task, ident='canon'):
        return next(row for row in task['sources'] if row['id'] == ident)

    def recovery(self, diagnostic):
        action = diagnostic['next_action']
        self.assertEqual(diagnostic['next_actions'], [action])
        result = subprocess.run(action['argv'], cwd=self.root, capture_output=True,
                                text=True, encoding='utf-8', check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_common_draft_exposes_original_values_and_build_preserves_source_owner(self):
        result, choices = self.draft_identity()
        _, basis = self.work_basis(result)
        self.assertEqual(common_work.source_bytes(basis['sources']['canon']), self.raw)
        self.assertEqual(basis['applications']['canon'], {'source': 'canon', 'pointer': ''})
        self.assertEqual(basis['subjects'], {'A': ['canon']})
        self.assertEqual(result['identity_coverage']['sources'][0]['sha256'], c.digest(self.raw))
        self.assertFalse(result['identity_coverage']['request_verified'])
        built = self.build_identity(result, choices)
        self.assertTrue(built['ok'], built.get('unresolved'))
        task = c.load(self.root / built['inputs']['production-task']['path'])
        source = self.selected_source(task)
        self.assertEqual((self.root / source['path']).read_bytes(), self.raw)
        self.assertEqual(source['identity'], self.task['sources'][0]['identity'])
        self.assertEqual((self.root / 'canon.json').read_bytes(), self.raw)
        self.assertEqual(task['criteria'], self.task['criteria'])

    def test_preparation_keeps_definition_and_whole_review_without_per_value_bindings(self):
        result, choices = self.draft_identity()
        choices['authoring']['task']['criteria'][0].pop('identity_bindings')
        choices['authoring']['task']['authority'] = None
        built = self.build_identity(result, choices)
        self.assertTrue(built['ok'], built.get('unresolved'))
        import production_operations as production_workflow
        try:
            prepared = production_workflow.prepare(self.root, choices=result['choices_file'])
        except CompilationError as error:
            self.fail(error.report)
        run = production_workflow.read_run(self.root, prepared['run']).prepared
        context = run['identity_coverage']
        self.assertEqual(context['status'], 'bindings-verified')
        self.assertEqual(context['bindings'], [])
        self.assertEqual(context['sources'][0]['sha256'], c.digest(self.raw))
        self.assertEqual(context['unbound_source_values'], [{'source': 'canon',
            'pointer': '/identity/outline', 'subject_ids': ['A']}])
        self.assertEqual(run['task']['criteria'], choices['authoring']['task']['criteria'])
        self.assertEqual((self.root / 'canon.json').read_bytes(), self.raw)

    def test_reopened_run_keeps_identity_bytes_after_original_removal(self):
        import production_operations as production_workflow
        result, choices = self.draft_identity()
        choices['authoring']['task']['authority'] = None
        (self.root / choices['authoring']['delivery']['file']).write_text(
            'Keep the adopted conditional details.\n', encoding='utf-8')
        (self.root / result['choices_file']).write_bytes(c.encoded(choices))
        parent = production_workflow.prepare(self.root, choices=result['choices_file'])['run']
        before = production_workflow.read_run(self.root, parent).prepared['input_sha256']
        (self.root / 'canon.json').unlink()

        reopened = authoring_fixtures.authoring_inputs(self.root, None, 'reopened-identity', from_run=parent)
        selected = reopened['choices']['authoring']['task']['sources'][0]
        self.assertEqual(selected['id'], 'canon')
        self.assertNotEqual(selected['path'], 'canon.json')
        self.assertEqual((self.root / selected['path']).read_bytes(), self.raw)
        self.assertEqual(reopened['identity_coverage']['sources'][0]['sha256'], c.digest(self.raw))
        compiled = production_inputs.compile_choices(self.root, reopened['choices_file'])
        if compiled.directory is not None:
            self.addCleanup(shutil.rmtree, compiled.directory, ignore_errors=True)
        self.assertTrue(compiled.report['publishable'], compiled.report)
        self.assertEqual(compiled.prepared['task']['criteria'], self.task['criteria'])
        self.assertEqual(production_workflow.read_run(self.root, parent).prepared['input_sha256'], before)

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

    def test_changed_external_file_preserves_the_acquired_identity(self):
        result, choices = self.draft_identity()
        changed = c.encoded({'identity': {'new_condition': 'The split now closes at rest.'}})
        (self.root / 'canon.json').write_bytes(changed)
        report = self.compile_identity(result, choices)
        self.assertTrue(report['ok'], report)
        _, basis = self.work_basis(result)
        self.assertEqual(common_work.source_bytes(basis['sources']['canon']), self.raw)
        self.assertEqual(c.load(self.root / result['choices_file']), choices)
        self.assertEqual((self.root / 'canon.json').read_bytes(), changed)

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

    def test_acquired_identity_remains_available_after_external_file_removal(self):
        result, choices = self.draft_identity()
        (self.root / 'canon.json').unlink()
        report = self.compile_identity(result, choices)
        self.assertTrue(report['ok'], report)
        _, basis = self.work_basis(result)
        self.assertEqual(common_work.source_bytes(basis['sources']['canon']), self.raw)

    def test_changed_acquired_bytes_require_a_matching_acquisition(self):
        result, choices = self.draft_identity()
        path, basis = self.work_basis(result)
        basis['sources']['canon']['data'] = c.encoded({'identity': 'a different design'}).decode('utf-8')
        path.write_bytes(c.encoded(basis))
        report = self.compile_identity(result, choices)
        self.assertFalse(report['ok'])
        self.assertTrue(any('source bytes differ from the acquired SHA-256' in row['message']
                            for row in report['diagnostics']), report)
        self.assertEqual((self.root / 'canon.json').read_bytes(), self.raw)

    def test_source_witnesses_are_derived_from_the_acquired_identity(self):
        result, choices = self.draft_identity()
        source = self.selected_source(choices['authoring']['task'])
        choices['authoring']['source_files'].pop(source['path'])
        built = self.build_identity(result, choices)
        self.assertTrue(built['ok'], built.get('unresolved'))
        task = c.load(self.root / built['inputs']['production-task']['path'])
        selected = self.selected_source(task)
        self.assertEqual((self.root / selected['path']).read_bytes(), self.raw)
        self.assertEqual(built['identity_coverage']['sources'][0]['sha256'], c.digest(self.raw))

    def test_removing_an_unbound_original_source_still_loses_required_context(self):
        result, choices = self.draft_identity()
        path, basis = self.work_basis(result)
        applications = {key: value for key, value in basis['applications'].items() if value['source'] != 'canon'}
        basis = common_work.revise_basis(basis, applications=applications, subjects={})
        path.write_bytes(c.encoded(basis))
        choices['authoring']['task'].update(criteria=[], features=[])
        report = self.compile_identity(result, choices)
        self.assertFalse(report['ok'])
        self.assertEqual(report['diagnostics'][0]['code'], 'IDENTITY_SOURCE_CHANGED')
        self.assertEqual(report['diagnostics'][0]['source'], 'canon')

    def test_same_source_id_cannot_move_to_replacement_bytes(self):
        result, choices = self.draft_identity()
        replacement = c.encoded({'identity': {'outline': 'A closed ring with an invented projection.'}})
        (self.root / 'replacement.json').write_bytes(replacement)
        path, basis = self.work_basis(result)
        sources = copy.deepcopy(basis['sources'])
        sources['canon'] = common_work.acquire_source(replacement, format='json', origin=sources['canon']['origin'])
        path.write_bytes(c.encoded(common_work.revise_basis(basis, sources=sources)))
        report = self.compile_identity(result, choices)
        self.assertFalse(report['ok'])
        self.assertEqual(report['diagnostics'][0]['code'], 'IDENTITY_SOURCE_CHANGED')
        diagnostic = report['diagnostics'][0]
        self.assertEqual(diagnostic['cause'], 'retained-identity-source-changed')
        changed = next(row for row in diagnostic['changes']
                       if (row['source'], row['change_kind']) == ('canon', 'content'))
        self.assertEqual(changed['before']['sha256'], c.digest(self.raw))
        self.assertEqual(changed['after']['sha256'], c.digest(replacement))

    def test_retained_identity_scope_cannot_be_silently_changed_in_choices(self):
        result, original = self.draft_identity(graph=True, retained_authority=True)
        path, original_basis = self.work_basis(result)
        for kind, change in [('authority', lambda value: value['sources']['canon']['origin']['source']['identity'].pop('authority')),
                       ('authority', lambda value: value['sources']['canon']['origin']['source']['identity']['authority'].update(canon_status='proposed')),
                       ('scope', lambda value: value['applications']['canon'].update(pointer='')),
                       ('subjects', lambda value: value['subjects'].update(B=['canon']))]:
            with self.subTest(change=change):
                choices = copy.deepcopy(original)
                basis = copy.deepcopy(original_basis)
                change(basis)
                path.write_bytes(c.encoded(basis))
                report = self.compile_identity(result, choices)
                self.assertFalse(report['ok'])
                diagnostic = report['diagnostics'][0]
                self.assertEqual(diagnostic['code'], 'IDENTITY_SOURCE_CHANGED')
                self.assertEqual(diagnostic['cause'], 'retained-identity-source-changed')
                self.assertTrue(any((row['source'], row['change_kind']) == ('canon', kind)
                                    for row in diagnostic['changes']), diagnostic)
                self.assertEqual(diagnostic['next_action']['command'], 'draft-inputs')

    def test_removing_derived_context_evidence_cannot_bypass_registered_originals(self):
        result, choices = self.draft_identity()
        context_path = self.root / result['context_file']
        context = c.load(context_path)
        context.pop('identity_coverage')
        context_path.write_bytes(c.encoded(context))
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
        with cases.edit_document(self.root, choices, 'state_graphs') as document:
            document[0]['identity_contract']['identity']['outline'] = 'A closed solid disc.'
        built = self.build_identity(result, choices)
        self.assertFalse(built['ok'])
        gap = built['unresolved'][0]
        self.assertEqual((gap['code'], gap['cause']), ('IDENTITY_SOURCE_CHANGED', 'retained-identity-source-changed'))
        changed = next(row for row in gap['changes']
                       if (row['source'], row['change_kind']) == ('state:A:identity_contract', 'content'))
        self.assertNotEqual(changed['before']['value_sha256'], changed['after']['value_sha256'])
        self.assertEqual(gap['next_action']['command'], 'draft-inputs')
        self.assertEqual((self.root / 'canon.json').read_bytes(), self.raw)

    def test_scene_snapshot_edit_preserves_original_graph_identity_source(self):
        result, choices = self.draft_identity(graph=True)
        with cases.edit_document(self.root, choices, 'state_graphs') as document:
            document[0]['state_snapshot']['scene_state'] = 'Under the selected tension.'
        built = self.build_identity(result, choices)
        self.assertTrue(built['ok'], built.get('unresolved'))
        task = c.load(self.root / built['inputs']['production-task']['path'])
        source = self.selected_source(task)
        self.assertEqual((self.root / source['path']).read_bytes(), self.raw)
        self.assertNotEqual(task['generation']['state_graphs'], 'canon.json')
        materialized = c.load(self.root / task['generation']['state_graphs'])
        self.assertEqual(materialized[0]['state_snapshot']['scene_state'], 'Under the selected tension.')
        self.assertEqual((self.root / 'canon.json').read_bytes(), self.raw)

    def test_optional_visual_owner_scope_cannot_be_rewritten_in_a_retained_scene_draft(self):
        result, choices = self.draft_identity(graph=True, visual_context=True)
        with cases.edit_document(self.root, choices, 'state_graphs') as graphs:
            graph = graphs[0]
            graph['visual_authority']['authority_scope'] = 'Now governs every permanent shape without the original limit.'
            graph['visual_evidence_bundle']['disposition'] = 'adopted'
        built = self.build_identity(result, choices)
        self.assertFalse(built['ok'])
        gap = built['unresolved'][0]
        self.assertEqual((gap['code'], gap['cause']), ('IDENTITY_SOURCE_CHANGED', 'retained-identity-source-changed'))
        changed = {(row['source'], row['change_kind']) for row in gap['changes']}
        self.assertTrue({('state:A:visual_authority', 'content'), ('state:A:visual_evidence_bundle', 'content')} <= changed)
        self.assertEqual(gap['next_action']['command'], 'draft-inputs')
        self.assertEqual((self.root / 'canon.json').read_bytes(), self.raw)


class SubjectDeclarationGuidanceTests(unittest.TestCase):
    """A public repair reaches the declared input owner without guessing a cast."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='cpb-subject-guide-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.enterContext(authoring_fixtures.scratch_home(self.root / 'home'))
        self.original = c.encoded({'subject_id': 'A', 'shape': 'A segmented open shell.'})
        (self.root / 'definition.json').write_bytes(self.original)
        self.task = {'task_id': 'synthetic-subject-guide', 'route': 'generation', 'artifact': 'image',
            'execution': 'external', 'features': [], 'direction': {'decisions': []},
            'sources': [{'id': 'definition', 'path': 'definition.json', 'role': 'identity-contract',
                'disposition': 'applied', 'locator': 'whole document', 'reason': 'Synthetic adopted definition.',
                'identity': {'subject_ids': ['A'], 'selectors': ['']}}],
            'criteria': [{'id': 'whole', 'text': 'Compare the complete selected identity.',
                'strength': 'hard', 'evidence': 'image', 'identity_review': ['A']}]}
        self.choices = {'target': None, 'external': None,
                        'authoring': {'task': self.task, 'documents': {}}}
        self.path = 'choices.json'
        self.save()

    def save(self):
        (self.root / self.path).write_bytes(c.encoded(self.choices))

    def read(self, path):
        return (self.root / path).read_bytes()

    def report(self, **kwargs):
        return production_identity.inspect(self.task, self.read, **kwargs)

    def gap(self, report, **kwargs):
        return next(row for row in production_inputs._identity_gaps(
            report, root=self.root, choices_path=self.path, **kwargs)
            if 'unknown_subject_ids' in row.get('gaps', {}))

    def invoke(self, action, *, json_output=True):
        result = subprocess.run(action['argv'], cwd=self.root, capture_output=True,
                                text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout) if json_output else result.stdout

    def test_missing_input_subjects_reach_public_explain_and_the_existing_draft_owner(self):
        # A source's structured subject ID and a name in the real prompt are not
        # an image-input subject declaration, even when both use the same ID.
        inputs = {'references': [], 'external_request': {
            'request': {'prompt': 'Show A, the synthetic segmented shell.'}, 'prompt_field': ['prompt']}}
        report = self.report(inputs=inputs)
        self.assertEqual(report['subject_ids'], ['A'])
        self.assertEqual(report['actual_subject_ids'], [])
        diagnostic = self.gap(report)
        self.assertEqual(diagnostic['cause'], 'input-subject-declaration-missing')
        self.assertEqual((diagnostic['field'], diagnostic['file'], diagnostic['pointer']),
            ('authoring.documents.production_spec', self.path, '/authoring/documents/production_spec'))
        self.assertEqual(diagnostic['repair_owner']['pointer'], '/subjects')
        before = self.read(self.path)
        public = self.invoke(diagnostic['next_action'])
        self.assertFalse(public['selected'])
        scaffold = public['contract']['scaffold']
        help_text = self.invoke(scaffold['help_action'], json_output=False)
        for flag in ('--kind', '--subject', '--continuity', '--render-intent'):
            self.assertIn(flag, help_text)
        template = self.invoke(scaffold['template_action'])
        self.assertEqual(template, c.load(production_inputs.ROOT / scaffold['template_path']))
        shape = self.invoke(diagnostic['schema_action'])['schema_fragment']
        self.assertIn('id', shape['required'])
        self.assertIn('robot', shape['properties']['domain']['enum'])
        self.assertEqual(self.read(self.path), before)

        # Supply independent explicit choices to the original draft command.
        # The guide contributes no subject, domain, target or appearance value.
        (self.root / 'render.json').write_bytes(c.encoded({
            'artifact_type': 'render-intent', 'execution_mode': 'text-to-image'}))
        create = {'argv': [*scaffold['help_action']['argv'][:-1], 'spec.json',
            '--root', str(self.root), '--model', 'synthetic-interface',
            '--brief', 'Depict the selected synthetic shell.', '--subject', 'A',
            '--kind', 'robot', '--continuity', 'one-off', '--render-intent', 'render.json']}
        self.invoke(create)
        self.choices['authoring']['documents']['production_spec'] = {'file': 'spec.json'}
        self.save()
        selected = self.invoke(diagnostic['next_action'])
        self.assertEqual(selected['source'], {'file': 'spec.json'})
        specification = c.load(self.root / 'spec.json')
        view = production_identity.context(self.task, self.read, production_spec=specification, inputs=inputs)
        repaired = identity_coverage.compile(self.task, self.read, context=view)
        self.assertEqual(repaired['actual_subject_ids'], ['A'])
        self.assertEqual(repaired['unknown_subject_ids'], [])
        self.assertEqual(self.read('definition.json'), self.original)

    def test_explicit_specification_scope_and_nested_file_pointer_are_not_missing_declarations(self):
        for subjects in ([], [{'id': 'B'}]):
            with self.subTest(subjects=subjects):
                specification = {'subjects': subjects}
                (self.root / 'bundle.json').write_bytes(c.encoded({'input/spec': specification}))
                self.choices['authoring']['documents']['production_spec'] = {
                    'file': 'bundle.json', 'field': ['input/spec']}
                self.save()
                diagnostic = self.gap(self.report(production_spec=specification), locations={
                    'authoring.documents.production_spec': {'file': 'bundle.json', 'pointer': ['input/spec']}})
                self.assertEqual(diagnostic['cause'], 'identity-subject-scope-mismatch')
                self.assertEqual(diagnostic['actual_subject_ids'], [row['id'] for row in subjects])
                self.assertEqual((diagnostic['file'], diagnostic['pointer']),
                                 ('bundle.json', '/input~1spec/subjects'))
                self.assertTrue(diagnostic['subject_declaration']['present'])
                self.assertEqual(diagnostic['repair_owner']['pointer'], '/input~1spec/subjects')
                public = self.invoke(diagnostic['next_action'])
                self.assertEqual(public['source']['field'], ['input/spec'])

    def test_recording_scope_reaches_its_actual_map_and_task_schema(self):
        import production_input_guide
        for mapping in ({}, {'B': 'studio-character'}):
            with self.subTest(mapping=mapping):
                self.task['recording'] = {'character': 'studio-character', 'slot': 'image',
                    'subject_map': mapping, 'sheet_panel': False, 'role': 'candidate'}
                self.save()
                report = self.report()
                self.assertEqual(report['subject_declaration']['owner'], 'recording.subject_map')
                diagnostic = self.gap(report)
                self.assertEqual(diagnostic['cause'], 'identity-subject-scope-mismatch')
                self.assertEqual(diagnostic['field'], 'authoring.task.recording.subject_map')
                self.assertEqual(diagnostic['pointer'], '/authoring/task/recording/subject_map')
                public = self.invoke(diagnostic['next_action'])['fields'][0]
                fragment = c.load(production_input_guide.ROOT / public['content_schema'])['properties']['recording']
                self.assertEqual(public['schema_fragment'], fragment)
                self.assertEqual(public['subject_declaration']['schema_pointer'],
                                 '/properties/recording/properties/subject_map')
                self.assertEqual(c.load(self.root / self.path)['authoring']['task']['recording']['subject_map'], mapping)

    def test_compile_preserves_missing_owner_diagnostic_and_specification_precedence(self):
        with self.assertRaises(ProductionError) as caught:
            identity_coverage.compile(self.task, self.read,
                context=production_identity.context(self.task, self.read))
        diagnostic = caught.exception.diagnostic.as_dict()
        self.assertEqual(diagnostic['code'], 'IDENTITY_COVERAGE_INCOMPLETE')
        self.assertEqual(diagnostic['cause'], 'input-subject-declaration-missing')
        self.assertEqual(diagnostic['repair_owner']['owner'], 'production_spec')
        self.assertEqual(diagnostic['gaps'], {'unknown_subject_ids': ['A']})
        self.assertIn('schema_fragment', self.invoke(diagnostic['next_action']))
        self.task['recording'] = {'subject_map': {'A': 'studio-character'}}
        view = production_identity.context(self.task, self.read, production_spec={'subjects': [{'id': 'B'}]})
        self.assertEqual(view['subject_ids'], ['B'])
        self.assertEqual(view['subject_declaration']['owner'], 'production_spec')
        view = production_identity.context(self.task, self.read, production_spec={'subjects': []})
        self.assertEqual(view['subject_ids'], ['A'])
        self.assertEqual(view['subject_declaration']['owner'], 'recording.subject_map')


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
