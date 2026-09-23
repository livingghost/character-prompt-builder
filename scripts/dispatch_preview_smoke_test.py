#!/usr/bin/env python3
"""Synthetic public-preview outputs from the real compiled upscale request."""
import contextlib
import copy
import io
import json
from pathlib import Path
import unittest

from smoke_fixtures import isolate_home

isolate_home()
from unittest.mock import patch
import execution_contract as c
import production_workflow as workflow
import production_request
import reimplementation_smoke_test as fixture

class PreviewTests(unittest.TestCase):
    setUp=fixture.UpscaleIntegration.setUp
    def preview(self, **changes):
        import dispatch
        options=copy.copy(self.options)
        options.send=False
        options.preview_out=self.root/'preview.json'
        options.intent_out=self.root/'intent.json'
        for key,value in changes.items():setattr(options,key,value)
        before=copy.deepcopy(workflow.load_run(self.root,self.run)[3])
        self.output=io.StringIO()
        with contextlib.redirect_stdout(self.output): result=dispatch.dispatch_upscale(options,self.root)
        self.assertEqual(workflow.load_run(self.root,self.run)[3],before)
        self.transport.send.assert_not_called();self.transport.upload_bytes.assert_not_called()
        return result
    def test_exact_intent_file_and_review_identifiers(self):
        self.assertEqual(self.preview(),0)
        view=c.load(self.root/'preview.json');intent=c.load(self.root/'intent.json')
        self.assertEqual(view['request_contract']['request_sha256'],intent['payload']['request_sha256'])
        self.assertEqual(intent['payload']['input_sha256'],
                         {path:item['sha256'] for path,item in self.request['input_snapshots'].items()})
        self.assertNotIn('base64',(self.root/'intent.json').read_text(encoding='utf-8'))
        decision=production_request.draft_decision(view['request_contract'],actor='synthetic selector')
        self.assertIsNone(decision['rendition_review']['conclusion'])
        self.assertIsNone(decision['principal_approval'])
        self.assertFalse(view['execution_ready'])
    def test_existing_file_is_preserved(self):
        (self.root/'preview.json').write_text('Existing result.', encoding='utf-8')
        with self.assertRaises(FileExistsError):self.preview()
        self.assertEqual((self.root/'preview.json').read_text(encoding='utf-8'),'Existing result.')
        self.assertFalse((self.root/'intent.json').exists())
    def test_intent_needs_its_prepared_context(self):
        import work_ledger
        current=work_ledger.read_current(self.root);current.pop('production_run')
        work_ledger.write_current(self.root,current)
        with self.assertRaises(ValueError):self.preview()
        self.assertFalse((self.root/'preview.json').exists())
    def test_upscale_goes_under_the_open_task_run(self):
        import dispatch
        self.assertEqual(dispatch.open_run(self.root),self.run)
    def test_screen_shows_plain_lines_then_the_exact_request(self):
        self.assertEqual(self.preview(),0)
        text=self.output.getvalue()
        head,_,body=text.partition('request (sha256 ')
        for line in ('model: '+self.model,'service: synthetic at https://example.invalid','outputs: 1',
                     'negative prompt: none; an upscale takes no negative prompt',
                     'cost: unknown; the author states the upper bound in the authorization',
                     'production run: '+self.run,'saved: trace and validation in','shown, not sent'):
            self.assertIn(line,head)
        view=c.load(self.root/'preview.json')
        self.assertEqual(json.loads(body.partition('\n')[2]),view['request_contract']['request'])
        self.assertTrue(view['request_contract']['request_trace'])
        for long in ('request_trace','input_snapshots','base64'):self.assertNotIn(long,text)
        self.assertLess(len(text.splitlines()),40)

if __name__=='__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main(verbosity=2)
