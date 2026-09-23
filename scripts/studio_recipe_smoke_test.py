#!/usr/bin/env python3
"""Check explicit candidate recipes using synthetic local recording evidence."""
from __future__ import annotations
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
import execution_contract as c
import studio


class RecipeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = studio.init(Path(self.tmp.name) / 'studio', 'synthetic-studio', 'Synthetic recipe evidence')
        self.home = studio.add_character(self.root, 'subject-a', '')
        inputs = Path(self.tmp.name) / 'inputs'
        inputs.mkdir()
        self.sent = {'model': 'synthetic:target', 'positivePrompt': 'A synthetic neutral study.',
                     'seed': 19, 'width': 512, 'taskUUID': 'synthetic-request'}
        for name, value in [('request.json', self.sent), ('response.json', {'seed': 23}),
                            ('package.json', {'synthetic': True})]:
            (inputs / name).write_bytes(c.encoded(value))
        # Opaque bytes exercise recording integrity, not generated image quality.
        (inputs / 'result.bin').write_bytes(b'Synthetic retained output.\n')
        self.row = studio.iterate(self.root, 'subject-a', 'base.front', inputs / 'result.bin',
            package=inputs / 'package.json', request=inputs / 'request.json',
            response=inputs / 'response.json', note='Synthetic recipe fixture.')

    def read(self, **kwargs):
        return studio.recipe(self.root, 'subject-a', 'base.front', iteration=self.row['iteration_id'], **kwargs)

    def rewrite(self, row):
        studio.write_iterations(self.home, [row])

    def files(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes()
                for p in self.root.rglob('*') if p.is_file()}

    def test_candidate_request_is_exact_and_read_only(self):
        before = self.files()
        result = self.read()
        self.assertEqual(result['request'], self.sent)
        self.assertEqual(result['source_status'], 'candidate')
        self.assertEqual(result['seed'], 23)
        self.assertEqual(self.files(), before)
        self.assertFalse(list((self.home / 'accepted').iterdir()))

    def test_default_uses_current_accepted_iteration(self):
        studio.accept(self.root, 'subject-a', self.row['iteration_id'])
        result = studio.recipe(self.root, 'subject-a', 'base.front')
        self.assertEqual(result['iteration_id'], self.row['iteration_id'])
        self.assertEqual(result['source_status'], 'accepted')

    def test_default_does_not_select_a_candidate(self):
        with self.assertRaisesRegex(ValueError, 'no accepted iteration'):
            studio.recipe(self.root, 'subject-a', 'base.front')

    def test_explicit_iteration_must_belong_to_slot(self):
        with self.assertRaisesRegex(ValueError, 'slot'):
            studio.recipe(self.root, 'subject-a', 'outfit.back', iteration=self.row['iteration_id'])

    def test_absent_iteration_is_not_replaced_with_latest(self):
        with self.assertRaisesRegex(ValueError, 'no iteration'):
            studio.recipe(self.root, 'subject-a', 'base.front', iteration='it-9999')

    def test_duplicate_selector_is_rejected(self):
        studio.write_iterations(self.home, [self.row, copy.deepcopy(self.row)])
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            self.read()

    def test_missing_request_is_reported_without_inventing_settings(self):
        row = copy.deepcopy(self.row)
        row['request'] = None
        self.rewrite(row)
        with self.assertRaisesRegex(ValueError, 'recorded no request'):
            self.read()

    def test_changed_request_is_rejected(self):
        (self.root / self.row['request']['path']).write_bytes(c.encoded({'seed': 99}))
        with self.assertRaisesRegex(ValueError, 'evidence changed'):
            self.read()

    def test_changed_result_is_rejected(self):
        (self.root / self.row['result']['path']).write_bytes(b'Different synthetic result.')
        with self.assertRaisesRegex(ValueError, 'evidence changed'):
            self.read()

    def test_changed_response_is_rejected(self):
        (self.root / self.row['response']['path']).write_bytes(c.encoded({'seed': 99}))
        with self.assertRaisesRegex(ValueError, 'evidence changed'):
            self.read()

    def test_recorded_request_supplies_seed_when_response_has_none(self):
        row = copy.deepcopy(self.row)
        row['response'] = None
        row['seed'] = 999
        self.rewrite(row)
        self.assertEqual(self.read()['seed'], 19)

    def test_unknown_seed_is_not_fabricated(self):
        row = copy.deepcopy(self.row)
        row['response'] = None
        sent = dict(self.sent)
        del sent['seed']
        raw = c.encoded(sent)
        (self.root / row['request']['path']).write_bytes(raw)
        row['request']['sha256'] = c.digest(raw)
        self.rewrite(row)
        self.assertIsNone(self.read()['seed'])

    def test_superseded_selection_does_not_restore_acceptance(self):
        row = copy.deepcopy(self.row)
        row['status'] = 'superseded'
        self.rewrite(row)
        before = self.files()
        self.assertEqual(self.read()['source_status'], 'superseded')
        self.assertEqual(self.files(), before)

    def test_cli_explicit_candidate(self):
        before = self.files()
        result = subprocess.run([sys.executable, str(Path(studio.__file__)), '--studio', str(self.root),
            'recipe', '--character', 'subject-a', '--slot', 'base.front', '--iteration', self.row['iteration_id']],
            capture_output=True, text=True, encoding="utf-8", timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['request'], self.sent)
        self.assertEqual(self.files(), before)

    def test_cli_takes_the_studio_after_the_command(self):
        result = subprocess.run([sys.executable, str(Path(studio.__file__)), 'recipe', '--studio', str(self.root),
            '--character', 'subject-a', '--slot', 'base.front', '--iteration', self.row['iteration_id']],
            capture_output=True, text=True, encoding="utf-8", timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['request'], self.sent)


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
