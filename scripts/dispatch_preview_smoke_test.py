#!/usr/bin/env python3
"""Synthetic previews of the real sealed upscale request; nothing is reserved, uploaded or sent."""
import contextlib
import copy
import io
import json
from pathlib import Path
import unittest

import execution_contract as c
import production_workflow as workflow
import production_request
import reimplementation_smoke_test as fixture


class PreviewTests(unittest.TestCase):
    setUp = fixture.UpscaleIntegration.setUp

    def preview(self, **changes):
        import dispatch
        options = copy.copy(self.options)
        options.preview_out = 'preview.json'
        for key, value in changes.items():
            setattr(options, key, value)
        before = copy.deepcopy(workflow.load_run(self.root, self.run)[3])
        self.output = io.StringIO()
        try:
            with contextlib.redirect_stdout(self.output):
                return dispatch.dispatch_upscale(options, self.root)
        finally:
            self.assertEqual(workflow.load_run(self.root, self.run)[3], before)
            self.transport.send.assert_not_called()
            self.transport.upload_bytes.assert_not_called()

    def refused(self, **changes) -> str:
        with self.assertRaises(ValueError) as caught:
            self.preview(**changes)
        self.assertFalse((self.root / 'preview.json').exists())
        return caught.exception.diagnostic.code

    def test_preview_file_holds_the_sealed_request_and_its_validation(self):
        self.assertEqual(self.preview(), 0)
        view = c.load(self.root / 'preview.json')
        plan = c.load(workflow.load_run(self.root, self.run)[0] / 'execution-plan.json')
        self.assertEqual(view['request_contract']['request_sha256'], plan['request_sha256'])
        self.assertEqual(view['validation']['mode'], self.request['request_validation']['mode'])
        decision = production_request.draft_decision(view['request_contract'], actor='synthetic selector')
        self.assertIsNone(decision['rendition_review']['conclusion'])
        self.assertIsNone(decision['principal_approval'])
        self.assertFalse(view['execution_ready'])

    def test_existing_preview_file_is_kept(self):
        (self.root / 'preview.json').write_text('Existing result.', encoding='utf-8')
        with self.assertRaises(ValueError) as caught:
            self.preview()
        self.assertEqual(caught.exception.diagnostic.code, 'OUTPUT_ALREADY_EXISTS')
        self.assertEqual((self.root / 'preview.json').read_text(encoding='utf-8'), 'Existing result.')

    def test_upscale_needs_the_open_task_run(self):
        import work_ledger
        current = work_ledger.read_current(self.root)
        current.pop('production_run')
        work_ledger.write_current(self.root, current)
        self.assertEqual(self.refused(), 'EXECUTION_NOT_APPLICABLE')

    def test_upscale_goes_under_the_open_task_run(self):
        import dispatch
        self.assertEqual(dispatch.open_run(self.root), self.run)

    def test_preview_refuses_what_execute_refuses(self):
        self.assertEqual(self.refused(scale=4), 'INPUT_CONSISTENCY_ERROR')
        self.assertEqual(self.refused(slot='another-candidate'), 'INPUT_CONSISTENCY_ERROR')
        self.source.write_bytes(self.source.read_bytes() + b'changed')
        self.assertEqual(self.refused(), 'SOURCE_CHANGED')

    def test_preview_refuses_a_run_that_owns_an_execution(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.execution.execute(self.root, self.run, decisions_file=self.decision_file)
        import dispatch
        options = copy.copy(self.options)
        with self.assertRaises(ValueError) as caught:
            dispatch.dispatch_upscale(options, self.root)
        self.assertEqual(caught.exception.diagnostic.code, 'DISPATCH_ALREADY_CLAIMED')

    def test_inputs_are_paths_below_the_studio(self):
        relative = {'source': 'upscale/source.png', 'render_intent': 'upscale/render-intent.json',
                    'request_validation_file': 'upscale/validation.json'}
        self.assertEqual(self.preview(**relative), 0)
        (self.root / 'preview.json').unlink()
        self.assertEqual(self.refused(**{**relative, 'source': 'upscale\\source.png'}), 'INPUT_SCHEMA_INVALID')

    def test_upscale_declaration_keeps_an_existing_out_and_reads_stdin_once(self):
        import production_binding
        arguments = ['--root', str(self.root), '--source', 'upscale/source.png', '--model', self.model, '--scale', '2',
                     '--render-intent', 'upscale/render-intent.json', '--request-validation-file', 'upscale/validation.json']
        before = (self.root / 'upscale/input.json').read_bytes()
        for extra, code in ((['--out', 'upscale/input.json'], 'OUTPUT_ALREADY_EXISTS'),
                            (['--settings-file', '-', '--render-intent', '-', '--out', 'upscale/new.json'], 'INPUT_SCHEMA_INVALID')):
            output = io.StringIO()
            with self.subTest(code=code), contextlib.redirect_stdout(output):
                self.assertEqual(production_binding.main([*arguments, *extra]), 2)
            self.assertEqual([row['code'] for row in json.loads(output.getvalue())['diagnostics']], [code])
        self.assertEqual((self.root / 'upscale/input.json').read_bytes(), before)
        self.assertFalse((self.root / 'upscale/new.json').exists())
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(production_binding.main([*arguments, '--out', 'upscale/new.json']), 0)
        self.assertEqual(c.load(self.root / 'upscale/new.json'), c.load(self.root / 'upscale/input.json'))

    def test_screen_shows_plain_lines_then_the_exact_request(self):
        self.assertEqual(self.preview(), 0)
        text = self.output.getvalue()
        head, _, body = text.partition('request (sha256 ')
        for line in ('model: ' + self.model, 'service: synthetic at http://localhost/cpb-synthetic-no-network', 'outputs: 1',
                     'negative prompt: none; an upscale takes no negative prompt', 'cost: 0 USD at most (',
                     'production run: ' + self.run, 'saved: trace and validation in preview.json', 'shown, not sent'):
            self.assertIn(line, head)
        view = c.load(self.root / 'preview.json')
        self.assertEqual(json.loads(body.partition('\n')[2]), view['request_contract']['request'])
        self.assertTrue(view['request_contract']['request_trace'])
        for long in ('request_trace', 'input_snapshots', 'base64'):
            self.assertNotIn(long, text)
        self.assertLess(len(text.splitlines()), 40)


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main(verbosity=2)
