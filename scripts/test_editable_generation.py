"""Editable ordinary image inputs compiled through the production owner.

Synthetic targets are test fixtures. No service is contacted and no image
quality or semantic judgment is inferred from these mechanical checks.
"""
from __future__ import annotations
import production_fixtures as authoring_fixtures

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
import production_operations as workflow


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
        fixtures.write(self.root/'independent-definition.json',specification['subjects'][0])
        self.task['sources']=[row for row in self.task['sources'] if not row.get('definition_owner')]
        self.task['sources'].append({'id':'robot-definition','path':'independent-definition.json',
            'role':'definition','disposition':'applied','locator':'identity',
            'reason':'The fixture explicitly keeps this character definition while choosing ordinary prompt inputs.',
            'applications':[{'id':'robot-definition','pointer':'/identity','subjects':['robot'],'requirement':False}]})
        production_fixtures.bind_work_basis(self.root,self.task,
            request='Depict the synthetic robot defined in the selected source.',focus='character')
        fixtures.write(self.root/'task.json',self.task)

    def editable(self):
        result=authoring_fixtures.authoring_inputs(self.root,'task.json','editor')
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
        from generation_payload_validation import verify
        verified=verify(compiled.package,package_root=compiled.directory,studio=self.root,
                        reading_ledgers=[compiled.directory/'reads.jsonl'])
        self.assertTrue(verified['verified'])

    def test_complete_current_choices_export_the_declared_target_and_actual_input(self):
        self.editable()
        built=inputs.build_inputs(self.root,'task.json',self.choice_path,'complete-built')
        self.assertTrue(built['ok'],built)
        task_path=built['inputs']['production-task']['path']
        task=c.load(self.root/task_path)
        self.assertEqual(task['generation']['model'],fixtures.MODEL_ID)
        self.assertEqual(task['generation']['service'],'synthetic')
        prepared=workflow.prepare(self.root,task_path)
        self.assertEqual(prepared['request_preview']['model'],'synthetic:robot')
        self.assertEqual(prepared['request_preview']['prompt'],fixtures.PROMPT)

    def test_revised_editor_file_creates_exact_new_preparation_and_keeps_prior_input(self):
        prompt=self.editable()
        first=workflow.prepare(self.root,choices=self.choice_path)
        before=workflow.read_run(self.root,first['run'])
        changed='A flat graphic view of the simple synthetic robot beside an empty shelf.'
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

    def test_custom_axis_selection_changes_captured_input_without_rewriting_the_prompt(self):
        self.editable()
        selected=self.choices['authoring']['generation']['render_intent']
        selected.update(preset=None,axes={})
        prepared=[]
        for axes in ({},{'dimensionality':'flat-shapes'}):
            with self.subTest(axes=axes):
                selected['axes']=copy.deepcopy(axes)
                fixtures.write(self.root/self.choice_path,self.choices)
                result=workflow.prepare(self.root,choices=self.choice_path)
                view=workflow.read_run(self.root,result['run'])
                package=view.artifacts['package.json']
                actual=package['render_contract']['intent']
                self.assertEqual(actual,{**selected,'prompt_expression':fixtures.PROMPT})
                self.assertEqual(result['request_preview']['prompt'],fixtures.PROMPT)
                self.assertEqual(package['composition_prompt'],fixtures.PROMPT)
                self.assertEqual(view.prepared['task']['criteria'],self.task['criteria'])
                prepared.append(view)
        before,after=prepared
        self.assertNotEqual(before.prepared['input_sha256'],after.prepared['input_sha256'])
        self.assertNotEqual(before.artifacts['package.json']['generation_input_sha256'],
                            after.artifacts['package.json']['generation_input_sha256'])
        self.assertEqual(before.artifacts['package.json']['render_contract']['intent']['axes'],{})

    def test_prompt_revision_prepares_without_a_rendering_declaration(self):
        import render_contract_lib
        prompt=self.editable()
        operation=render_contract_lib.operation_intent('text-to-image')
        self.choices['authoring']['generation']['render_intent']=operation
        fixtures.write(self.root/self.choice_path,self.choices)
        proposed=['The simple synthetic robot stands beside a delivery bag.',
                  'The simple synthetic robot carries the torn delivery bag.']
        prepared=[]
        for content in proposed:
            prompt.write_text(content,encoding='utf-8')
            result=workflow.prepare(self.root,choices=self.choice_path)
            view=workflow.read_run(self.root,result['run'])
            package=view.artifacts['package.json']
            self.assertEqual(result['request_preview']['prompt'],content)
            self.assertEqual(package['composition_prompt'],content)
            self.assertEqual(package['render_contract']['intent'],operation)
            self.assertEqual(package['render_contract']['prompt_expression'],'')
            self.assertEqual(view.prepared['task']['criteria'],self.task['criteria'])
            prepared.append(view)
        before,after=prepared
        self.assertNotEqual(before.prepared['input_sha256'],after.prepared['input_sha256'])
        self.assertEqual(before.consumer['instructions'],proposed[0])
        self.assertEqual(after.consumer['instructions'],proposed[1])
        self.assertEqual(before.artifacts['package.json']['render_contract']['intent'],operation)

    def test_unselected_direct_intent_leaves_the_specification_as_owner(self):
        import render_contract_lib
        prompt=self.editable()
        content='A robot holding a delivery bag.'
        prompt.write_text(content,encoding='utf-8')
        operation=render_contract_lib.operation_intent('text-to-image')
        specification=c.load(self.root/'spec.json')
        specification['render_intent']=operation
        fixtures.write_document(self.root, self.choices, 'production_spec', specification)
        self.choices['authoring']['generation']['render_intent']=None
        self.choices['authoring']['generation']['continuity']={'robot':'one-off'}
        fixtures.write(self.root/self.choice_path,self.choices)
        result=workflow.prepare(self.root,choices=self.choice_path)
        view=workflow.read_run(self.root,result['run'])
        self.assertNotIn('render_intent',view.prepared['task']['generation'])
        self.assertEqual(result['request_preview']['prompt'],content)
        self.assertEqual(view.artifacts['package.json']['production_spec']['render_intent'],operation)
        self.assertEqual(view.artifacts['package.json']['render_contract']['intent'],operation)

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
