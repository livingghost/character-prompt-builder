#!/usr/bin/env python3
"""Generic model-selection regression; no provider is the fixture default."""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import prepare_generation_references as references

ROOT = Path(__file__).resolve().parents[1]


class ModelNeutralityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cpb-model-neutrality-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "supplied.json").write_text('[]', encoding='utf-8')
        (self.root / "state.json").write_text('{}', encoding='utf-8')
        (self.root / "studio.json").write_text('[]', encoding='utf-8')
        (self.root / "edit.json").write_text(json.dumps({"model": {"catalog_model": "fixture-model"}}), encoding='utf-8')

    def invoke(self, mode: str, file_name: str, *, model: str | None = None):
        argv = [mode, str(self.root / file_name), '--output-dir', str(self.root / 'carriers'), '--out', str(self.root / 'prepared.json')]
        if mode in ('--studio-selection-file', '--semantic-edit-plan-file'):
            argv.extend(['--studio', str(self.root)])
        if model is not None:
            argv.extend(['--model', model])
        buf = io.StringIO()
        with patch.object(references, 'resolve_pack_runtime', return_value=SimpleNamespace(settings='fixture-runtime')):
            with patch.object(references, 'configure_pack_runtime'):
                with contextlib.redirect_stdout(buf):
                    result = references.main(argv)
        return result, json.loads(buf.getvalue())

    def test_no_implicit_model_for_supplied_state_or_studio(self):
        for option, file_name in [
            ('--supplied-selection-file', 'supplied.json'),
            ('--state-selection-file', 'state.json'),
            ('--studio-selection-file', 'studio.json'),
        ]:
            with self.subTest(mode=option):
                code, report = self.invoke(option, file_name)
                self.assertEqual(code, 1)
                self.assertFalse(report['ok'])
                self.assertIn('--model is required', report['errors'][0])
                self.assertFalse((self.root / 'prepared.json').exists())

    def test_supplied_model_is_forwarded_unchanged(self):
        named = 'fixture-image-model'
        with patch.object(references, 'prepare_references', return_value={'fixture': True}) as stub:
            code, report = self.invoke('--supplied-selection-file', 'supplied.json', model=named)
        self.assertEqual(code, 0)
        self.assertTrue(report['fixture'])
        self.assertEqual(stub.call_args.kwargs['model'], named)

    def test_plan_may_supply_its_own_selected_model(self):
        with patch.object(references, 'prepare_semantic_edit_references', return_value={'fixture': True}) as stub:
            code, report = self.invoke('--semantic-edit-plan-file', 'edit.json')
        self.assertEqual(code, 0)
        self.assertTrue(report['fixture'])
        self.assertIsNone(stub.call_args.kwargs['model'])

    def test_cli_fixture_validation_follows_the_authored_model(self):
        from smoke_fixtures import cli_with_fixture_retrieval
        spec_path = self.root / 'production-spec.json'
        prompt_path = self.root / 'prompt.txt'
        prompt_path.write_text('Synthetic object on a table.', encoding='utf-8')
        base = ['--production-root', str(self.root), '--production-run', 'fixture-run',
                '--production-spec-file', str(spec_path), '--prompt-file', str(prompt_path),
                '--visual-continuity-file', 'supplied-visual.json',
                '--retrieval-record-file', 'supplied-retrieval.json']

        def inspect(argv):
            if '--request-validation-file' not in argv:
                return None
            return json.loads(Path(argv[argv.index('--request-validation-file') + 1]).read_text(encoding='utf-8'))

        for specification, explicit, expected in [
            ('fixture-model-from-spec', None, 'fixture-model-from-spec'),
            ('fixture-model-from-spec', 'fixture-model-from-cli', 'fixture-model-from-cli'),
            ('', None, None),
        ]:
            with self.subTest(specification=specification, explicit=explicit):
                spec_path.write_text(json.dumps({'target_model': specification}), encoding='utf-8')
                argv = base + (['--model', explicit] if explicit else [])
                with patch('catalog_retrieval.runtime.configure_pack_runtime'), \
                     patch('visual_fixtures.fixture_root', return_value=self.root), \
                     patch('request_validation_fixtures.fixture_validation',
                           side_effect=lambda root, model, **kwargs: {'selected_model': model}) as validation:
                    result = cli_with_fixture_retrieval(inspect, argv)
                if expected is None:
                    self.assertIsNone(result)
                    validation.assert_not_called()
                else:
                    self.assertEqual(result, {'selected_model': expected})
                    self.assertTrue(all(call.args[1] == expected for call in validation.call_args_list))

    def test_generic_templates_hold_no_provider_selection(self):
        brief = json.loads((ROOT / 'templates/brief-template.json').read_text(encoding='utf-8'))
        package = json.loads((ROOT / 'templates/generation-package-template.json').read_text(encoding='utf-8'))
        self.assertEqual(brief['target_model'], '')
        self.assertEqual(package['status'], 'template')
        self.assertEqual(package['model'], '')
        self.assertEqual(package['generation_payload']['prompt_recommendations']['resolved_model_id'], '')
        self.assertEqual(package['generation_payload']['negative_transport']['mode'], '')
        self.assertFalse(any(package['generation_payload']['transports'][x]['available']
                         for x in ('separate', 'integrated', 'native_subset')))

    def test_general_readme_has_no_one_model_footnote(self):
        readme = (ROOT / 'README.md').read_text(encoding='utf-8')
        self.assertNotIn('## Commons model note:', readme)
        self.assertIn('selected model', readme)

    def test_common_guide_does_not_force_one_subject_or_location(self):
        guide = json.loads((ROOT / 'packs/commons/resources/prompt-writing-guide/guide.json').read_text(encoding='utf-8'))
        rules = '\n'.join(rule for section in guide['sections'] for rule in section.get('rules', []))
        self.assertNotIn('Treat one character as the default', rules)
        self.assertIn('scene without characters', rules)
        self.assertIn('unless the task changes it', rules)
        self.assertIn('Do not invent a setting or props', rules)
        self.assertIn('do not reframe without specific authorization', rules)
        self.assertNotIn('Give every rendition a concrete situation block', rules)
        self.assertNotIn('Force a crop with three supports', rules)


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main(verbosity=2)
