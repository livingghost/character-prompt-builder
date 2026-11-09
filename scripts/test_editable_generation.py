"""Editable ordinary image inputs compiled through the production owner.

Synthetic targets are test fixtures. No service is contacted and no image
quality or semantic judgment is inferred from these mechanical checks.
"""
from __future__ import annotations

import copy
from pathlib import Path
import shutil
import tempfile
import unittest

import execution_contract as c
import production_case_fixtures as fixtures
import production_compiler as compiler
import production_fixtures
import production_inputs as inputs
import production_workflow as workflow


class EditableGenerationTests(unittest.TestCase):
    def setUp(self):
        from catalog_retrieval import runtime
        self.temporary=tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base=Path(self.temporary.name)
        self.enterContext(production_fixtures.scratch_home(self.base/'home'))
        self.addCleanup(runtime.configure_pack_runtime,None)
        self.case=fixtures.create(self.base/'studio',self.base/'runtime')
        self.root=self.case['root']
        self.task=c.load(self.root/'task.json')
        specification=c.load(self.root/'spec.json')
        self.task['generation']={
            'model':fixtures.MODEL_ID,'render_intent':specification['render_intent'],
            'service':'synthetic','seed':None,'count':1,'continuity':{},
            'request_validation':'validation.json'}
        self.task.pop('recording',None)
        fixtures.write(self.root/'task.json',self.task)

    def editable(self):
        result=inputs.draft_inputs(self.root,'task.json','editor')
        self.choice_path=result['choices_file']
        self.choices=c.load(self.root/self.choice_path)
        reading=c.load(self.root/self.task['route_reading'])
        self.choices['reading']={'reading_key':reading['reading_key']}
        self.choices['authoring']['generation']['render_intent']['prompt_expression']={'document':'delivery'}
        fixtures.write(self.root/self.choice_path,self.choices)
        return self.root/self.choices['authoring']['delivery']['file']

    def test_ordinary_request_needs_no_unused_documents_or_character_destination(self):
        compiled=compiler.compile_task(self.root,'task.json')
        self.assertTrue(compiled.report['publishable'],compiled.report['diagnostics'])
        self.addCleanup(shutil.rmtree,compiled.directory,ignore_errors=True)
        for name in ('production_spec','plot','creative_intent','retrieval_record'):
            self.assertIsNone(compiled.package[name])
        self.assertIsNone(compiled.execution_plan['recording'])
        self.assertEqual(compiled.rendered['request']['prompt'],fixtures.PROMPT)
        from verify_generation_payload import verify
        verified=verify(compiled.package,package_root=compiled.directory,studio=self.root,
                        reading_ledgers=[compiled.directory/'reads.jsonl'])
        self.assertTrue(verified['verified'])

    def test_revised_editor_file_creates_exact_new_preparation_and_keeps_prior_input(self):
        prompt=self.editable()
        first=workflow.prepare(self.root,choices=self.choice_path)
        before=workflow.read_run(self.root,first['run'])
        changed='A flat graphic view of a small clock on an empty shelf.'
        prompt.write_text(changed,encoding='utf-8')
        second=workflow.prepare(self.root,choices=self.choice_path)
        after=workflow.read_run(self.root,second['run'])
        self.assertNotEqual(first['run'],second['run'])
        self.assertNotEqual(before.prepared['input_sha256'],after.prepared['input_sha256'])
        self.assertEqual(before.consumer['instructions'],fixtures.PROMPT)
        self.assertEqual(after.consumer['instructions'],changed)
        self.assertEqual(after.prepared['task']['criteria'],self.task['criteria'])
        self.assertEqual(after.prepared['authoring']['choices_ref']['files'][
            self.choices['authoring']['delivery']['file']],c.digest(changed.encode('utf-8')))
        self.assertFalse(any(row['event'] in {'review','authored-review','authored-delivery'} for row in after.rows))

    def test_independent_document_diagnostics_point_to_editable_sources(self):
        self.editable()
        fixtures.write(self.root/'editor/parameters.json',{'width':0})
        fixtures.write(self.root/'editor/intent.json',[])
        self.choices['authoring']['documents'].update({
            'parameters':{'file':'editor/parameters.json'},
            'creative_intent':{'file':'editor/intent.json'}})
        fixtures.write(self.root/self.choice_path,self.choices)
        report=inputs.compile_choices(self.root,self.choice_path).report
        self.assertFalse(report['publishable'])
        files={row.get('file') for row in report['diagnostics'] if row['severity']=='error'}
        self.assertTrue({'editor/parameters.json','editor/intent.json'}<=files,report['diagnostics'])
        self.assertFalse(report['formal_run_created'])


if __name__=='__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
