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
        return {row['anchor'] for row in result['section_owners'].get(path, [])}

    def size(self, result):
        return sum(row['end'] - row['start'] for doc in result['reads'] for row in doc['ranges'])

    def test_view_retains_identity_and_review_without_new_definition_sources(self):
        result = self.resolve(['depiction.view'])
        paths = {row['path'] for row in result['reads']}
        self.assertNotIn('templates/narrative/design/design-template.md', paths)
        self.assertNotIn('references/species-architecture.md', paths)
        self.assertNotIn('establish-the-character-for-this-use',
                         self.sections(result, 'references/runtime/production-direction.md'))
        self.assertIn('identity-obligations-for-the-current-view',
                      self.sections(result, 'references/character-identity-contract.md'))
        self.assertIn('inspect-identity-coverage-and-retain-its-authority',
                      self.sections(result, 'references/character-identity-contract.md'))
        self.assertIn('performance-coverage-and-topology',
                      self.sections(result, 'references/runtime/character-sheet-discipline.md'))
        self.assertIn('references/camera-framing-contract.md', paths)

    def test_definition_changes_select_the_complete_definition_contracts(self):
        result = self.resolve(['definition'])
        for path in ('templates/narrative/design/design-template.md',
                     'references/species-architecture.md', 'references/character-identity-contract.md',
                     'references/morphology-and-species-contracts.md'):
            with self.subTest(path=path):
                source = next(row for row in result['reads'] if row['path'] == path)
                self.assertEqual(sum(row['end'] - row['start'] for row in source['ranges']), source['size'])

    def test_reference_changes_read_acquisition_coverage_and_transport(self):
        result = self.resolve(['references'])
        self.assertIn('acquire-a-production-source',
                      self.sections(result, 'references/runtime/production-authoring.md'))
        selected = self.sections(result, 'references/runtime/reference-delivery.md')
        self.assertTrue({'selection-and-authority', 'reference-identities-and-coverage',
                         'bind-the-actual-transport', 'retain-source-and-carrier-evidence'} <= selected)
        self.assertNotIn('templates/narrative/design/design-template.md', result['section_owners'])

    def test_numeric_controls_do_not_reopen_writing_or_finishing(self):
        features = [*self.features, 'finishing']
        numeric = self.resolve(['controls.parameters'], features=features)
        paths = set(numeric['section_owners'])
        self.assertFalse(paths & {'references/creative-core.md', 'references/finishing-layers-specification.md',
                                 'references/runtime/prompt-writing-guide.md', 'references/runtime/prompt-weighting.md'})
        selected = self.sections(numeric, 'references/runtime/render-contract.md')
        self.assertIn('declare-controls-by-operation', selected)
        self.assertNotIn('choose-the-visual-treatment', selected)
        finishing = self.resolve(['controls.render-intent'], features=features)
        self.assertIn('choose-the-visual-treatment', self.sections(finishing, 'references/runtime/render-contract.md'))
        self.assertIn('references/finishing-layers-specification.md', finishing['section_owners'])

    def test_sparse_construction_and_explicit_finishing_keep_their_complete_scopes(self):
        path = 'references/finishing-layers-specification.md'
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
                source = next(row for row in explicit['reads'] if row['path'] == path)
                self.assertEqual(sum(row['end'] - row['start'] for row in source['ranges']), source['size'])
                self.assertIn('feature:finishing', explicit['read_owners'][path])

    def test_retarget_selects_new_target_and_wording_dependencies(self):
        result = self.resolve(['target'], features=[*self.features, 'gpt-image'])
        self.assertIn('select-and-change-the-target',
                      self.sections(result, 'references/runtime/production-authoring.md'))
        self.assertIn('compare-inputs-and-change-the-target',
                      self.sections(result, 'references/runtime/model-evidence.md'))
        self.assertIn('references/runtime/prompt-writing-guide.md', result['section_owners'])
        self.assertIn('bind-the-actual-transport',
                      self.sections(result, 'references/runtime/reference-delivery.md'))

    def test_recording_keeps_provenance_without_prompt_development(self):
        result = self.resolve(['recording.slot'], stage='prepare')
        self.assertIn('identify-the-recorded-subjects',
                      self.sections(result, 'references/runtime/production-authoring.md'))
        self.assertIn('references/runtime/production-preparation.md', result['section_owners'])
        self.assertIn('protected-criteria-across-runs',
                      self.sections(result, 'references/runtime/production-permissions.md'))
        self.assertNotIn('references/runtime/prompt-writing-guide.md', result['section_owners'])
        self.assertNotIn('references/species-architecture.md', result['section_owners'])

    def test_combined_edits_deliver_the_union_without_duplicate_ranges(self):
        changes = ['depiction.view', 'references', 'recording.slot']
        combined = self.resolve(changes)
        expected = set()
        for change in changes:
            for path, rows in self.resolve([change])['section_owners'].items():
                expected.update((path, row['start'], row['end']) for row in rows)
        actual = [(path, row['start'], row['end'])
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
        self.assertIn('references/species-architecture.md', original['section_owners'])
        self.assertIn('templates/narrative/design/design-template.md', original['section_owners'])
        self.assertLess(self.size(self.resolve(['depiction.view'])), self.size(original))
        self.assertLess(self.size(self.resolve(['controls.parameters'])), self.size(original) // 2)


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
