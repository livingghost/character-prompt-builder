"""Finished authored prompts use the shared syntax and real vocabulary owners."""
from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import authored_prompt
import execution_contract as c
from model_prompt_input_fixtures import prompt_input
from production_fixtures import scratch_home
import prompt_vocabulary_selection as vocabulary
import render_contract_fixtures as render
import route_reading


class AuthoredPromptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.enterContext(scratch_home(self.root / 'home'))
        self.dictionary = self.root / 'dictionary.json'
        self.dialects = self.root / 'dialects.json'
        self.dictionary.write_bytes(c.encoded({'format': 'character-prompt-builder-prompt-vocabulary',
            'name': 'Synthetic paper vocabulary', 'description': 'Synthetic local material meanings.',
            'categories': [{'id': 'surface', 'name': 'Surface', 'description': 'Paper finish.',
                'entries': [{'term': 'matte paper', 'aliases': ['uncoated paper'],
                             'description': 'Paper with a non-glossy surface.'},
                            {'term': 'printed text', 'description': 'Text printed on a surface.'}]}]}))
        dialects = {'format': 'character-prompt-builder-prompt-dialects',
            'name': 'Synthetic families', 'description': 'Fictional input family.',
            'dialects': [{'id': 'fixture-paper', 'name': 'Paper fixture',
                'description': 'Synthetic family used only in tests.', 'vocabularies': ['fixture-paper'],
                'tag_separator': 'comma and space', 'block_order': ['content', 'optional controls']} ]}
        self.dialects.write_bytes(c.encoded(dialects))
        guide = {'sections': [{'id': 'paper', 'dialects': ['fixture-paper'],
                              'text': 'Retain the intended paper surface meaning.'}]}
        self.resources = {'prompt-dialects': c.encoded(dialects), 'prompt-writing-guide': c.encoded(guide)}
        self.enterContext(patch.object(route_reading, '_live_resource_reader', return_value=self.resource))
        real = vocabulary._resources
        self.enterContext(patch.object(vocabulary, '_resources', side_effect=lambda model, **kwargs:
            real(model, dictionary_path=self.dictionary, dialect_path=self.dialects)))
        self.files = {}

    def resource(self, name):
        raw = self.resources[name]
        return {'source_pack': 'synthetic-paper', 'path': 'data/' + name + '.json',
                'sha256': c.digest(raw)}, raw

    def task(self, *, mode='descriptive', prompt='An empty market after the rain.', negative='',
             syntax=None, model_fields=None, target=None, reading_service=None):
        model = {'id': 'synthetic-authored-model', 'prompt_input': prompt_input(mode,
            vocabularies=('fixture-paper',) if mode == 'tag-based' else ())}
        features, dialect = [], None
        if mode == 'tag-based':
            model.update(prompt_input=prompt_input(mode, vocabularies=('fixture-paper',)),
                         prompt_dialect='fixture-paper')
            features, dialect = ['prompt-dialect'], 'fixture-paper'
        model.update(copy.deepcopy(model_fields or {}))
        model_file = self.root / 'model.json'
        model_file.write_bytes(c.encoded(model))
        reading, _ = route_reading.capture('development', features, operation='author',
            execution='authored', dialect=dialect, resource_reader=self.resource,
            model_file=model_file, service=reading_service)
        self.files.update({'model.json': c.encoded(model), 'reading.json': c.encoded(reading),
                           'body.txt': prompt.encode('utf-8'), 'negative.txt': negative.encode('utf-8')})
        selected = {'model_file': 'model.json', **(target or {})}
        if syntax is not None:
            selected['syntax'] = syntax
        return {'delivery': {'path': 'body.txt'}, 'route_reading': 'reading.json',
                'authored': {'target': selected,
                             'negative': {'path': 'negative.txt'}}}

    @staticmethod
    def profile(syntax='literal', *, modes=('text-to-image',), native=False):
        profile = render.profile()
        profile['modes'] = {name: profile['modes'][name] for name in modes}
        for mode in profile['modes'].values():
            mode['prompt_syntax'] = {'default': syntax, 'control': None}
            if native:
                mode['controls']['conditioning'] = render.control('required',
                    schema={'type': 'string', 'enum': ['plain', 'emphasis']})
                mode['prompt_syntax']['control'] = {'field': ['conditioning'], 'values': [
                    {'value': 'plain', 'syntax': 'literal'}, {'value': 'emphasis', 'syntax': 'compel'}]}
        return profile

    @staticmethod
    def offering(service, profile):
        return {'service': service, 'model_identifier': 'synthetic-text-interface',
                'request_keys': {'prompt': ['text']}, 'constraints': {},
                'observed_at': '2000-01-01', 'execution_profile': profile}

    def test_descriptive_target_preserves_exact_text_without_dictionary_requirement(self):
        task = self.task(prompt='  An empty market after the rain.\n')
        with patch.object(vocabulary.VocabularyIndex, 'search', side_effect=AssertionError('unexpected tag search')):
            bound = authored_prompt.check(task, self.files.__getitem__)
        self.assertIsNone(bound['vocabulary'])
        self.assertEqual(bound['prompt_sha256'], c.digest(self.files['body.txt']))
        authored_prompt.validate_bound(task, bound, self.files.__getitem__)

    def test_tag_finalization_searches_even_when_no_receipt_is_available(self):
        task = self.task(mode='tag-based', prompt='matte paper', negative='printed text')
        observed = []
        real = vocabulary.VocabularyIndex.search
        def search(index, query, **kwargs):
            observed.append(query)
            return real(index, query, **kwargs)
        with patch.object(vocabulary.VocabularyIndex, 'search', new=search):
            with self.assertRaisesRegex(ValueError, 'PROMPT_VOCABULARY_REQUIRED'):
                authored_prompt.check(task, self.files.__getitem__)
        self.assertEqual(observed, ['matte paper', 'printed text'])

    def searched_task(self):
        task = self.task(mode='tag-based', prompt='uncoated paper', negative='printed text')
        selected = vocabulary.search_selection(prompt='uncoated paper', negative='printed text',
            model_record=c.decode(self.files['model.json']))
        self.files['retrieval.json'] = c.encoded({'vocabulary': selected})
        task['authored']['target']['vocabulary_record'] = 'retrieval.json'
        return task

    def test_tag_save_binds_meaning_and_refuses_receipt_after_text_change(self):
        task = self.searched_task()
        bound = authored_prompt.check(task, self.files.__getitem__)
        self.assertEqual(bound['vocabulary']['entries'][0]['choice']['kind'], 'dictionary')
        authored_prompt.validate_bound(task, bound, self.files.__getitem__)
        self.files['body.txt'] = b'matte paper'
        with self.assertRaisesRegex(ValueError, 'PROMPT_VOCABULARY_REQUIRED'):
            authored_prompt.check(task, self.files.__getitem__)

    def test_saved_target_rechecks_grammar_and_refuses_missing_or_recorded_problem(self):
        task = self.task(syntax='compel', model_fields={'execution_profile': self.profile('compel')})
        bound = authored_prompt.check(task, self.files.__getitem__)
        for inspection in (None, {}, {'findings': [{'severity': 'problem', 'check': 'synthetic',
                                'message': 'Recorded grammar error.', 'terms': []}]}):
            altered = copy.deepcopy(bound)
            altered['inspection'] = inspection
            with self.subTest(inspection=inspection), self.assertRaisesRegex(ValueError, 'missing or records a problem'):
                authored_prompt.validate_bound(task, altered, self.files.__getitem__)
        self.files['body.txt'] = b'(unclosed'
        altered = copy.deepcopy(bound)
        altered['prompt_sha256'] = c.digest(self.files['body.txt'])
        with self.assertRaisesRegex(ValueError, 'TAG_PROMPT_PROBLEM'):
            authored_prompt.validate_bound(task, altered, self.files.__getitem__)

    def test_literal_profile_cannot_be_overridden_by_an_authored_syntax(self):
        task = self.task(model_fields={'execution_profile': self.profile()})
        for syntax in ('compel', 'sdEmbeds'):
            task['authored']['target']['syntax'] = syntax
            with self.subTest(syntax=syntax), self.assertRaisesRegex(ValueError, 'PROMPT_SYNTAX_MISMATCH'):
                authored_prompt.check(task, self.files.__getitem__)

    def test_profile_free_text_supports_literal_without_inventing_weighting(self):
        task = self.task(prompt='A literal (unfinished parenthesis', syntax='literal')
        bound = authored_prompt.check(task, self.files.__getitem__)
        self.assertEqual(bound['inspection']['syntax'], 'literal')
        authored_prompt.validate_bound(task, bound, self.files.__getitem__)
        task['authored']['target']['syntax'] = 'compel'
        with self.assertRaisesRegex(ValueError, 'PROMPT_SYNTAX_MISMATCH'):
            authored_prompt.check(task, self.files.__getitem__)

    def test_supported_weighting_is_derived_without_a_syntax_assertion(self):
        task = self.task(prompt='(quiet market)1.4',
                         model_fields={'execution_profile': self.profile('compel')})
        bound = authored_prompt.check(task, self.files.__getitem__)
        self.assertEqual(bound['inspection']['syntax'], 'compel')
        self.assertEqual(bound['model'], c.decode(self.files['model.json']))
        authored_prompt.validate_bound(task, bound, self.files.__getitem__)
        self.files['body.txt'] = b'(unclosed'
        with self.assertRaisesRegex(ValueError, 'TAG_PROMPT_PROBLEM'):
            authored_prompt.check(task, self.files.__getitem__)

    def test_native_grammar_control_preserves_search_of_exact_both_channels(self):
        prompt, negative = '(uncoated paper)1.2', '(printed text)0.7'
        task = self.task(mode='tag-based', prompt=prompt, negative=negative,
            model_fields={'execution_profile': self.profile(native=True)},
            target={'parameters': {'conditioning': 'emphasis'}})
        selected = vocabulary.search_selection(prompt=prompt, negative=negative,
            model_record=c.decode(self.files['model.json']), syntax='compel')
        self.files['retrieval.json'] = c.encoded({'vocabulary': selected})
        task['authored']['target']['vocabulary_record'] = 'retrieval.json'
        observed = []
        real = vocabulary.VocabularyIndex.search
        def search(index, query, **kwargs):
            observed.append(query)
            return real(index, query, **kwargs)
        with patch.object(vocabulary.VocabularyIndex, 'search', new=search):
            bound = authored_prompt.check(task, self.files.__getitem__)
        self.assertEqual(observed, ['uncoated paper', 'printed text'])
        self.assertEqual(bound['inspection']['syntax'], 'compel')
        self.assertEqual(bound['prompt_sha256'], c.digest(prompt.encode('utf-8')))
        self.assertEqual(bound['negative_sha256'], c.digest(negative.encode('utf-8')))
        authored_prompt.validate_bound(task, bound, self.files.__getitem__)
        task['authored']['target']['parameters']['conditioning'] = 'plain'
        with self.assertRaisesRegex(ValueError, 'PROMPT_VOCABULARY_REQUIRED'):
            authored_prompt.check(task, self.files.__getitem__)

    def test_required_grammar_control_needs_its_declared_native_value(self):
        task = self.task(model_fields={'execution_profile': self.profile(native=True)})
        with self.assertRaisesRegex(ValueError, 'conditioning: required explicit value'):
            authored_prompt.check(task, self.files.__getitem__)
        task['authored']['target']['parameters'] = {'conditioning': 'unsupported'}
        with self.assertRaisesRegex(ValueError, 'conditioning'):
            authored_prompt.check(task, self.files.__getitem__)
        task['authored']['target']['parameters'] = {'conditioning': 'emphasis'}
        self.assertEqual(authored_prompt.check(task, self.files.__getitem__)['inspection']['syntax'], 'compel')

    def test_shared_grammar_needs_no_service_mode_or_image_generation_controls(self):
        profile = self.profile(modes=('text-to-image', 'reference-guided'))
        for mode in profile['modes'].values():
            mode['controls']['width'] = render.control('required', schema={'type': 'integer', 'minimum': 1})
            mode['parameter_schema'] = {'type': 'object', 'required': ['width']}
        task = self.task(model_fields={'offerings': [
            self.offering('synthetic-first', profile), self.offering('synthetic-second', profile)]})
        bound = authored_prompt.check(task, self.files.__getitem__)
        self.assertEqual(bound['inspection']['syntax'], 'literal')
        authored_prompt.validate_bound(task, bound, self.files.__getitem__)
        task['authored']['target']['parameters'] = {'width': -1}
        with self.assertRaisesRegex(ValueError, 'width'):
            authored_prompt.check(task, self.files.__getitem__)

    def test_different_mode_grammars_require_the_mode_that_owns_the_text(self):
        profile = self.profile(modes=('text-to-image', 'reference-guided'))
        profile['modes']['reference-guided']['prompt_syntax']['default'] = 'compel'
        task = self.task(model_fields={'execution_profile': profile})
        with self.assertRaisesRegex(ValueError, 'PROMPT_SYNTAX_SELECTION_REQUIRED'):
            authored_prompt.check(task, self.files.__getitem__)
        task['authored']['target']['execution_mode'] = 'reference-guided'
        bound = authored_prompt.check(task, self.files.__getitem__)
        self.assertEqual(bound['inspection']['syntax'], 'compel')
        authored_prompt.validate_bound(task, bound, self.files.__getitem__)

    def test_selected_offering_owns_grammar_and_its_reading_scope(self):
        model = {'execution_profile': self.profile('sdEmbeds'), 'offerings': [
            self.offering('synthetic-literal', self.profile()),
            self.offering('synthetic-weighted', self.profile('compel'))]}
        task = self.task(model_fields=model)
        with self.assertRaisesRegex(ValueError, 'PROMPT_SYNTAX_SELECTION_REQUIRED'):
            authored_prompt.check(task, self.files.__getitem__)
        task['authored']['target']['service'] = 'synthetic-weighted'
        bound = authored_prompt.check(task, self.files.__getitem__)
        self.assertEqual(bound['inspection']['syntax'], 'compel')
        authored_prompt.validate_bound(task, bound, self.files.__getitem__)
        task = self.task(model_fields=model, reading_service='synthetic-literal',
                         target={'service': 'synthetic-weighted'})
        with self.assertRaisesRegex(ValueError, 'different service'):
            authored_prompt.check(task, self.files.__getitem__)

    def test_changed_model_contract_requires_current_full_reading_and_invalidates_captured_file(self):
        task = self.task(model_fields={'execution_profile': self.profile('compel')})
        bound = authored_prompt.check(task, self.files.__getitem__)
        changed = c.decode(self.files['model.json'])
        changed['execution_profile']['modes']['text-to-image']['prompt_syntax']['default'] = 'literal'
        self.files['model.json'] = c.encoded(changed)
        with self.assertRaisesRegex(ValueError, 'selected model edition'):
            authored_prompt.check(task, self.files.__getitem__)
        with self.assertRaisesRegex(ValueError, 'captured model file'):
            authored_prompt.validate_bound(task, bound, self.files.__getitem__)

    def test_catalog_revision_uses_frozen_profile_when_rechecked(self):
        task = self.task(syntax='compel', model_fields={'execution_profile': self.profile('compel')})
        model = c.decode(self.files['model.json'])
        task['authored']['target'].pop('model_file')
        task['authored']['target']['model'] = model['id']
        with patch('prepare_generation_references.resolve_model_record', return_value=(model['id'], model)):
            bound = authored_prompt.check(task, self.files.__getitem__)
        with patch('prepare_generation_references.resolve_model_record', side_effect=AssertionError('unexpected live model lookup')):
            authored_prompt.validate_bound(task, bound, self.files.__getitem__)
        bound['model']['execution_profile']['modes']['text-to-image']['prompt_syntax']['default'] = 'literal'
        with self.assertRaisesRegex(ValueError, 'PROMPT_SYNTAX_MISMATCH'):
            authored_prompt.validate_bound(task, bound, self.files.__getitem__)

    def test_selected_text_limits_and_negative_channel_remain_enforced(self):
        for fields, prompt, negative, message in [
                ({'max_positive_prompt_chars': 4}, 'longer', '', 'prompt is 6 characters'),
                ({'max_negative_prompt_chars': 3}, 'scene', 'blur', 'negative is 4 characters'),
                ({'supports_negative_prompt': False}, 'scene', 'blur', 'no negative channel')]:
            with self.subTest(fields=fields):
                task = self.task(prompt=prompt, negative=negative, model_fields=fields)
                with self.assertRaisesRegex(ValueError, message):
                    authored_prompt.check(task, self.files.__getitem__)

    def test_json_prompt_and_negative_fields_are_the_selected_surfaces(self):
        task = self.task()
        self.files['body.txt'] = c.encoded({'prompt': 'A quiet river.', 'author_notes': 'This field is not model input.'})
        self.files['negative.txt'] = c.encoded({'negative': 'blur'})
        task['authored']['prompt_field'] = ['prompt']
        task['authored']['negative']['field'] = ['negative']
        bound = authored_prompt.check(task, self.files.__getitem__)
        self.assertEqual(bound['prompt_sha256'], c.digest(b'A quiet river.'))
        self.assertEqual(bound['negative_sha256'], c.digest(b'blur'))
        authored_prompt.validate_bound(task, bound, self.files.__getitem__)

    def test_finished_portable_json_requires_a_complete_json_artifact(self):
        task = {'artifact': 'json', 'delivery': {'path': 'body.json'}}
        self.files['body.json'] = b'{"title":'
        with self.assertRaises(ValueError):
            authored_prompt.check(task, self.files.__getitem__)
        with self.assertRaises(ValueError):
            authored_prompt.validate_bound(task, None, self.files.__getitem__)
        self.files['body.json'] = b'{"title":"A quiet river"}'
        self.assertIsNone(authored_prompt.check(task, self.files.__getitem__))
        authored_prompt.validate_bound(task, None, self.files.__getitem__)


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main(verbosity=2)
