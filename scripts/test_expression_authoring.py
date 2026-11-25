"""Requirements and medium scope from independently authored synthetic briefs."""
from __future__ import annotations

import copy
import json
import unittest

from production_diagnostics import ProductionError
import production_expression as expression
import production_plan


def depiction(ident='expression', text='The character looks happy, with a slight smile.'):
    return {'id': ident, 'basis': [], 'expression': text,
            'realization': {'method': 'authored image', 'instructions': text,
                            'capability_source': None, 'limitations': []},
            'criteria': ['happy'], 'depends_on': [], 'deviations': []}


def task():
    return {'artifact': 'image', 'sources': [],
            'criteria': [{'id': 'happy', 'strength': 'hard', 'text': 'The requested happiness is readable.',
                          'evidence': 'image', 'origin': {'kind': 'user-request'},
                          'observation': {'scope': 'impression', 'decision': 'expression'}}],
            'direction': {'purpose': 'Show the commissioned happy expression.',
                          'intended_effect': 'A readable happy expression.', 'basis': [],
                          'decisions': [depiction()], 'source_allowances': [],
                          'action_slice': None, 'limitations': []}}


class ExpressionAuthoringTests(unittest.TestCase):
    def setUp(self):
        self.task = task()

    def validate(self):
        production_plan.validate(self.task['direction'], self.task['sources'], self.task['criteria'])
        expression.validate(self.task)

    def refusal(self, code):
        before = copy.deepcopy(self.task)
        with self.assertRaises(ProductionError) as caught:
            self.validate()
        self.assertEqual(caught.exception.diagnostic.code, code)
        self.assertEqual(self.task, before, 'A refusal must preserve the author\'s actual work.')
        self.assertNotEqual(caught.exception.diagnostic.required_action, 'Correct the declared input and retry the operation.')

    def test_direct_emotion_needs_no_muscle_inventory(self):
        self.validate()
        self.assertIn('looks happy', json.dumps(production_plan.consumer(self.task['direction'])))

    def test_agent_ear_choice_is_advisory_without_new_approval(self):
        criterion = self.task['criteria'][0]
        criterion.update(text='The selected ears point upright.', origin={'kind': 'agent-realization', 'decision': 'expression'})
        self.refusal('UNAUTHORIZED_REQUIREMENT_PROMOTION')
        criterion['strength'] = 'advisory'
        self.validate()

    def test_missing_hard_origin_is_actionable(self):
        del self.task['criteria'][0]['origin']
        self.refusal('UNAUTHORIZED_REQUIREMENT_PROMOTION')

    def test_missing_hard_observation_is_actionable(self):
        del self.task['criteria'][0]['observation']
        self.refusal('MEDIUM_REPRESENTATION_UNRESOLVED')

    def test_only_applied_adopted_source_supplies_declared_origin(self):
        self.task['criteria'][0]['origin'] = {'kind': 'adopted-source', 'source': 'profile'}
        self.task['sources'] = [{'id': 'profile', 'disposition': 'considered-not-used'}]
        self.refusal('UNAUTHORIZED_REQUIREMENT_PROMOTION')
        self.task['sources'][0]['disposition'] = 'applied'
        self.validate()

    def test_hidden_thought_is_not_image_proof(self):
        criterion = self.task['criteria'][0]
        criterion.update(text='A pleasant memory actually occurred just before this moment.',
                         observation={'scope': 'context-only'})
        self.refusal('MEDIUM_UNREPRESENTABLE_REQUIREMENT')

    def test_subordinate_metaphor_keeps_primary_happiness(self):
        secondary = depiction('thought', 'As if a pleasant thought has just crossed their mind.')
        secondary['representation'] = {'role': 'secondary-figurative', 'primary': 'expression'}
        self.task['direction']['decisions'].append(secondary)
        self.validate()
        self.assertEqual(len(production_plan.consumer(self.task['direction'])['directives']), 2)
        self.task['criteria'][0]['observation']['decision'] = 'thought'
        self.refusal('MEDIUM_UNREPRESENTABLE_REQUIREMENT')
        self.task['criteria'][0]['strength'] = 'advisory'
        self.validate()

    def test_figurative_clause_cannot_supply_its_own_primary(self):
        selected = self.task['direction']['decisions'][0]
        selected['representation'] = {'role': 'secondary-figurative', 'primary': 'expression'}
        self.refusal('PRIMARY_VISIBLE_DEPICTION_REQUIRED')
        selected['representation']['primary'] = 'missing'
        self.refusal('PRIMARY_VISIBLE_DEPICTION_REQUIRED')

    def test_author_only_information_stays_out_of_consumer(self):
        private = depiction('memory', 'PRIVATE: the character remembers a hidden event.')
        private['representation'] = {'role': 'author-only'}
        self.task['direction']['decisions'].append(private)
        self.validate()
        self.assertNotIn('PRIVATE', json.dumps(production_plan.consumer(self.task['direction'])))
        self.assertIn('PRIVATE', json.dumps(self.task))

    def test_necessary_context_is_allowed_but_not_literal_hard_proof(self):
        premise = depiction('gift', 'A friend has given the character a welcome gift.')
        premise['representation'] = {'role': 'context-only'}
        self.task['direction']['decisions'].append(premise)
        self.validate()
        self.assertIn('welcome gift', json.dumps(production_plan.consumer(self.task['direction'])))
        self.task['criteria'][0]['observation']['decision'] = 'gift'
        self.refusal('MEDIUM_UNREPRESENTABLE_REQUIREMENT')

    def test_selected_unresolved_depiction_stays_draft(self):
        self.task['direction']['decisions'][0]['representation'] = {'role': 'unresolved'}
        self.refusal('MEDIUM_REPRESENTATION_UNRESOLVED')

    def test_comparison_requires_a_real_applied_baseline(self):
        criterion = self.task['criteria'][0]
        criterion.update(text='The expression differs from the adopted neutral expression.',
                         observation={'scope': 'comparison'})
        self.refusal('MEDIUM_REPRESENTATION_UNRESOLVED')
        criterion['observation']['baseline'] = 'neutral'
        self.task['sources'] = [{'id': 'neutral', 'disposition': 'applied'}]
        self.validate()

    def test_single_still_cannot_establish_order_but_panels_can(self):
        self.task['criteria'][0]['observation'] = {'scope': 'sequence'}
        self.refusal('MEDIUM_UNREPRESENTABLE_REQUIREMENT')
        self.task['direction']['image_format'] = 'multi-panel'
        self.validate()
        self.task['criteria'][0]['observation']['scope'] = 'duration'
        self.refusal('MEDIUM_UNREPRESENTABLE_REQUIREMENT')

    def test_video_and_audio_can_support_their_actual_temporal_evidence(self):
        for artifact, evidence in [('video', 'motion'), ('audio', 'audio')]:
            with self.subTest(artifact=artifact):
                self.task['artifact'] = artifact
                self.task['criteria'][0].update(evidence=evidence, observation={'scope': 'duration'})
                self.validate()

    def test_a_silent_still_does_not_supply_audio(self):
        self.task['criteria'][0].update(evidence='audio', observation={'scope': 'observable'})
        self.refusal('MEDIUM_UNREPRESENTABLE_REQUIREMENT')

    def test_text_can_state_narrative_duration_without_proving_playback_time(self):
        for artifact in ('text', 'json'):
            with self.subTest(artifact=artifact):
                self.task['artifact'] = artifact
                self.task['criteria'][0].update(
                    text='The story explicitly states that the character waited ten minutes before leaving.',
                    evidence='text', observation={'scope': 'duration'})
                self.validate()
                self.task['criteria'][0]['evidence'] = 'artifact'
                self.refusal('MEDIUM_UNREPRESENTABLE_REQUIREMENT')

    def test_prompt_words_and_length_are_not_a_semantic_filter(self):
        text = 'The curious robot leans toward the sample, its ring-shaped optic bright. '
        selected = self.task['direction']['decisions'][0]
        selected['expression'] = text + 'A sign reads: before and after. '
        selected['realization']['instructions'] = text * 100
        self.validate()

    def test_unknown_realization_and_observation_decisions_are_actionable(self):
        self.task['criteria'][0].update(strength='advisory', origin={'kind': 'agent-realization', 'decision': 'missing'})
        self.refusal('UNAUTHORIZED_REQUIREMENT_PROMOTION')
        self.task['criteria'][0].update(origin={'kind': 'user-request'}, observation={'scope': 'impression', 'decision': 'missing'})
        self.refusal('MEDIUM_REPRESENTATION_UNRESOLVED')

    def test_source_and_comparison_changes_reopen_their_criteria(self):
        self.task['criteria'][0]['origin'] = {'kind': 'adopted-source', 'source': 'adopted'}
        self.task['criteria'][0]['observation'] = {'scope': 'comparison', 'baseline': 'neutral'}
        for source in ('adopted', 'neutral'):
            with self.subTest(source=source):
                result = production_plan.affected(self.task, {source})
                self.assertEqual(result['criteria'], ['happy'])

    def test_primary_change_reopens_its_secondary_impression(self):
        self.task['direction']['decisions'][0]['basis'] = ['profile']
        secondary = depiction('thought', 'As if remembering a pleasant moment.')
        secondary['representation'] = {'role': 'secondary-figurative', 'primary': 'expression'}
        self.task['direction']['decisions'].append(secondary)
        self.assertEqual(production_plan.affected(self.task, {'profile'})['decisions'], ['expression', 'thought'])

    def test_editable_schema_accepts_the_same_owned_criteria_contract(self):
        from state_protocol import validate_against_schema
        schema = {'$ref': 'authoring/production-input-draft.schema.json#/$defs/draftCriterion'}
        self.assertEqual(validate_against_schema(self.task['criteria'][0], schema), [])
        self.task['criteria'][0]['origin']['kind'] = 'invented-authority'
        self.assertTrue(validate_against_schema(self.task['criteria'][0], schema))


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
