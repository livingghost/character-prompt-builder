"""Check retained-edit knowledge against its actual production responsibilities."""
from __future__ import annotations

import unittest

import execution_routes as routes
from production_change_scope import PROFILE_BY_SCOPE


class AmendmentProfileTests(unittest.TestCase):
    features = ['recurring-identity', 'body-plan', 'adoption', 'geometry']

    def scope(self, changes, *, stage='depiction'):
        return {'stage': stage, 'composition': 'amend', 'source_formats': ['image', 'json'],
            'documents': [], 'render_operation': 'generation',
            'conditions': ['image-source', 'multiple-results', 'references', 'render-intent'],
            'change_scope': {'retain': [], 'change': changes},
            'profiles': sorted({PROFILE_BY_SCOPE[name.split('.')[0]] for name in changes}),
            'observed_changes': [], 'change_conflicts': [], 'comparison_notices': []}

    def resolve(self, changes, *, stage='depiction', features=None):
        return routes.resolve('character-sheet', features or self.features,
            execution='dispatcher', authoring_scope=self.scope(changes, stage=stage))

    def sections(self, result, path):
        return {row['section_id'] for row in result['section_owners'].get(path, [])}

    def size(self, result):
        return sum(section['size'] for doc in result['reads'] for section in doc['sections'])

    def test_view_retains_identity_and_review_without_new_definition_sources(self):
        result = self.resolve(['depiction.view'])
        paths = {row['document_id'] for row in result['reads']}
        self.assertNotIn('templates/narrative/design/design-template', paths)
        self.assertNotIn('references/species-architecture', paths)
        self.assertNotIn('establish-the-character-for-this-use',
                         self.sections(result, 'references/runtime/production-direction'))
        self.assertIn('identity-obligations-for-the-current-view',
                      self.sections(result, 'references/character-identity-contract'))
        self.assertIn('inspect-identity-coverage-and-retain-its-authority',
                      self.sections(result, 'references/character-identity-contract'))
        self.assertIn('performance-coverage-and-topology',
                      self.sections(result, 'references/runtime/character-sheet-discipline'))
        self.assertIn('references/camera-framing-contract', paths)

    def test_definition_changes_select_the_complete_definition_contracts(self):
        result = self.resolve(['definition'])
        for path in ('templates/narrative/design/design-template',
                     'references/species-architecture', 'references/character-identity-contract',
                     'references/morphology-and-species-contracts'):
            with self.subTest(path=path):
                source = next(row for row in result['reads'] if row['document_id'] == path)
                self.assertEqual(source['sections'], [section.metadata() for section in routes.DocumentReader(lambda name: (routes.ROOT / name).read_bytes()).acquire(path).sections])

    def test_reference_changes_read_acquisition_coverage_and_transport(self):
        result = self.resolve(['references'])
        self.assertIn('acquire-a-production-source',
                      self.sections(result, 'references/runtime/production-authoring'))
        selected = self.sections(result, 'references/runtime/reference-delivery')
        self.assertTrue({'selection-and-authority', 'reference-identities-and-coverage',
                         'bind-the-actual-transport', 'retain-source-and-carrier-evidence'} <= selected)
        self.assertNotIn('templates/narrative/design/design-template', result['section_owners'])

    def test_numeric_controls_do_not_reopen_writing_or_finishing(self):
        features = [*self.features, 'finishing']
        numeric = self.resolve(['controls.parameters'], features=features)
        paths = set(numeric['section_owners'])
        self.assertFalse(paths & {'references/creative-core', 'references/finishing-layers-specification',
                                 'references/runtime/prompt-writing-guide', 'references/runtime/prompt-weighting'})
        selected = self.sections(numeric, 'references/runtime/render-contract')
        self.assertIn('declare-controls-by-operation', selected)
        self.assertNotIn('choose-the-visual-treatment', selected)
        finishing = self.resolve(['controls.render-intent'], features=features)
        self.assertIn('choose-the-visual-treatment', self.sections(finishing, 'references/runtime/render-contract'))
        self.assertIn('references/finishing-layers-specification', finishing['section_owners'])

    def test_sparse_construction_and_explicit_finishing_keep_their_complete_scopes(self):
        path = 'references/finishing-layers-specification'
        amended = self.resolve(['depiction'], features=['sparse-retrieval'])
        scope = self.scope(['depiction'])
        for key in ('change_scope', 'profiles', 'observed_changes', 'change_conflicts', 'comparison_notices'):
            scope.pop(key)
        ordinary = routes.resolve('character-sheet', ['sparse-retrieval'], execution='dispatcher',
                                  authoring_scope=scope)
        self.assertEqual(self.sections(amended, path), self.sections(ordinary, path))
        self.assertEqual(len(self.sections(amended, path)), 11)
        for changes in (['definition'], ['depiction'], ['controls.render-intent']):
            with self.subTest(changes=changes):
                explicit = self.resolve(changes, features=['sparse-retrieval', 'finishing'])
                source = next(row for row in explicit['reads'] if row['document_id'] == path)
                self.assertEqual(source['sections'], [section.metadata() for section in routes.DocumentReader(lambda name: (routes.ROOT / name).read_bytes()).acquire(path).sections])
                self.assertIn('feature:finishing', explicit['read_owners'][path])

    def test_retarget_selects_new_target_and_wording_dependencies(self):
        result = self.resolve(['target'], features=[*self.features, 'gpt-image'])
        self.assertIn('select-and-change-the-target',
                      self.sections(result, 'references/runtime/production-authoring'))
        self.assertIn('compare-inputs-and-change-the-target',
                      self.sections(result, 'references/runtime/model-evidence'))
        self.assertIn('references/runtime/prompt-writing-guide', result['section_owners'])
        self.assertIn('bind-the-actual-transport',
                      self.sections(result, 'references/runtime/reference-delivery'))

    def test_recording_keeps_provenance_without_prompt_development(self):
        result = self.resolve(['recording.slot'], stage='prepare')
        self.assertIn('identify-the-recorded-subjects',
                      self.sections(result, 'references/runtime/production-authoring'))
        self.assertIn('references/runtime/production-preparation', result['section_owners'])
        self.assertIn('protected-criteria-across-runs',
                      self.sections(result, 'references/runtime/production-permissions'))
        self.assertNotIn('references/runtime/prompt-writing-guide', result['section_owners'])
        self.assertNotIn('references/species-architecture', result['section_owners'])

    def test_combined_edits_deliver_the_union_without_duplicate_sections(self):
        changes = ['depiction.view', 'references', 'recording.slot']
        combined = self.resolve(changes)
        expected = set()
        for change in changes:
            for path, rows in self.resolve([change])['section_owners'].items():
                expected.update((path, row['section_id']) for row in rows)
        actual = [(path, row['section_id'])
                  for path, rows in combined['section_owners'].items() for row in rows]
        self.assertEqual(set(actual), expected)
        self.assertEqual(len(actual), len(set(actual)))

    def test_stage_selection_alone_does_not_add_unchanged_design_work(self):
        selections = [self.resolve(['depiction.view'], stage=stage)['reads']
                      for stage in ('definition', 'depiction', 'rendition')]
        self.assertEqual(selections[0], selections[1])
        self.assertEqual(selections[1], selections[2])

    def test_compose_still_selects_the_full_definition_and_costs_are_separate(self):
        scope = self.scope(['definition'], stage='definition')
        for key in ('change_scope', 'profiles', 'observed_changes', 'change_conflicts', 'comparison_notices'):
            scope.pop(key)
        scope['composition'] = 'compose'
        original = routes.resolve('character-sheet', self.features, execution='dispatcher', authoring_scope=scope)
        self.assertIn('references/species-architecture', original['section_owners'])
        self.assertIn('templates/narrative/design/design-template', original['section_owners'])
        self.assertLess(self.size(self.resolve(['depiction.view'])), self.size(original))
        self.assertLess(self.size(self.resolve(['controls.parameters'])), self.size(original) // 2)


class CompositionStageTests(unittest.TestCase):
    """Definition retains its source knowledge before picture construction begins."""

    features = ['unlisted-interface', 'vocabulary', 'sparse-retrieval',
                'craft-consultation', 'body-plan', 'finishing', 'render-contract']

    def resolve(self, stage, *, features=None):
        scope = {'stage': stage, 'composition': 'compose', 'source_formats': ['text'],
                 'documents': [], 'render_operation': 'generation', 'conditions': []}
        return routes.resolve('generation', self.features if features is None else features,
                              execution='external', authoring_scope=scope)

    def assert_complete(self, result, path):
        source = next(row for row in result['reads'] if row['document_id'] == path)
        self.assertEqual(source['sections'], [section.metadata() for section in routes.DocumentReader(lambda name: (routes.ROOT / name).read_bytes()).acquire(path).sections])

    def test_definition_keeps_source_and_body_knowledge_before_finishing_decisions(self):
        result = self.resolve('definition')
        paths = set(result['read_owners'])
        self.assertNotIn('references/finishing-layers-specification', paths)
        self.assertNotIn('references/creative-core', paths)
        self.assertNotIn('references/adapters/unlisted-interface', paths)
        for path in ('references/species-architecture', 'references/morphology-and-species-contracts',
                     'references/prompt-knowledge-boundary'):
            self.assert_complete(result, path)
        selected = {row['section_id'] for row in result['section_owners']['references/runtime/prompt-vocabulary']}
        self.assertIn('define-a-character-with-usable-wording', selected)
        selected = {row['section_id'] for row in result['section_owners']['references/runtime/authoring-work']}
        self.assertIn('apply-sources-to-this-candidate', selected)

    def test_depiction_delivers_every_original_finishing_byte(self):
        result = self.resolve('depiction')
        for path in ('references/creative-core', 'references/finishing-layers-specification'):
            self.assert_complete(result, path)
            self.assertIn('feature:finishing', result['read_owners'][path])

    def test_rendition_and_preparation_keep_transfer_contracts_without_reconceiving(self):
        for stage in ('rendition', 'prepare'):
            with self.subTest(stage=stage):
                result = self.resolve(stage)
                paths = set(result['read_owners'])
                self.assertNotIn('references/species-architecture', paths)
                self.assertNotIn('references/runtime/craft-consultation', paths)
                selected = {row['section_id'] for row in result['section_owners']['references/finishing-layers-specification']}
                self.assertTrue({'1-purpose', '2-the-five-finishing-layers',
                    'carry-the-construction-through-the-selected-interface', '10-layer-specific-cautions'} <= selected)
                self.assertNotIn('a-personal-world-and-what-a-hero-faces', selected)
                self.assertNotIn('letters-that-organize-or-become-a-place', selected)
                morphology = {row['section_id'] for row in result['section_owners']['references/morphology-and-species-contracts']}
                self.assertTrue({'2-ownership-and-precedence', '14-identity-versus-state',
                    '17-resolved-morphology-for-a-shot', '19-which-authority-settles-what'} <= morphology)
                self.assertNotIn('20-review-checklist', morphology)
                if stage == 'prepare':
                    self.assertNotIn('references/creative-core', paths)
                    self.assertIn('9-observation-contract', selected)
                    weighting = {row['section_id'] for row in result['section_owners']['references/runtime/prompt-weighting']}
                    self.assertIn('inspect-the-complete-request-not-a-flattened-tag-list', weighting)
                    self.assertIn('approval-recording-and-recovery', weighting)
                    self.assertNotIn('author-the-matching-rendition', weighting)
                else:
                    creative = {row['section_id'] for row in result['section_owners']['references/creative-core']}
                    self.assertIn('meaning-before-vocabulary', creative)
                    self.assertNotIn('compare-complete-constructions', creative)

    def test_stage_rules_do_not_activate_unselected_finishing(self):
        for stage in ('definition', 'depiction', 'rendition', 'prepare'):
            with self.subTest(stage=stage):
                result = self.resolve(stage, features=['unlisted-interface', 'vocabulary', 'body-plan'])
                self.assertNotIn('references/finishing-layers-specification', result['read_owners'])
                self.assertNotIn('references/creative-core', result['read_owners'])

    def test_interface_recipes_follow_the_depiction_in_each_selected_adapter(self):
        adapters = {'gpt-image': 'gpt-image', 'midjourney': 'midjourney-niji',
            'sdxl': 'sdxl-comfyui', 'novelai': 'novelai', 'grok': 'grok-imagine',
            'instruction-edit': 'instruction-edit', 'unlisted-interface': 'unlisted-interface'}
        for feature, name in adapters.items():
            path = 'references/adapters/' + name
            with self.subTest(feature=feature):
                self.assertNotIn(path, self.resolve('definition', features=[feature])['read_owners'])
                for stage in ('depiction', 'rendition', 'prepare'):
                    self.assert_complete(self.resolve(stage, features=[feature]), path)


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
