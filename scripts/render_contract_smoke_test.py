#!/usr/bin/env python3
"""Exercise explicit render choices and interface controls without image generation."""
from __future__ import annotations
import copy
import json
import unittest
import render_contract_lib as r
from render_contract_fixtures import control, intent, profile


class RenderContractTests(unittest.TestCase):
    def setUp(self):
        self.p=profile(seed=True,required={
            'steps':control('required',schema={'type':'integer','minimum':1,'maximum':60},recommendation='steps'),
            'CFGScale':control('required',schema={'type':'number','minimum':0,'maximum':20},recommendation='guidance')})
        self.model={'id':'synthetic-image-model','execution_profile':self.p,
                    'recommended_parameters':{'steps':24,'guidance':5.5}}
        self.prompt='Flat graphic illustration of an observatory.'
        self.intent=intent(self.prompt)

    def compile(self,params=None,**kwargs):
        return r.compile_contract(self.model,None,self.intent,params or {},prompt=self.prompt,reference_count=kwargs.get('reference_count',0))

    def test_public_contract_schema_matches_compiled_plan(self):
        from state_protocol import validate_against_schema
        schema=json.loads((r.ROOT/'schemas/render-contract.schema.json').read_text(encoding='utf-8'))
        self.assertEqual(validate_against_schema(self.compile(),schema),[])
        broken=self.compile();broken['unexpected']=True
        self.assertTrue(validate_against_schema(broken,schema))

    def test_wire_preserves_explicit_number_representation(self):
        plan=self.compile({'CFGScale':4.0})
        wire={**plan['parameters'],'seed':3,'numberResults':1}
        r.check_wire(plan,wire,seed=3,count=1)
        with self.assertRaisesRegex(ValueError,'differs'):
            r.check_wire(plan,{**wire,'CFGScale':4},seed=3,count=1)

    def test_img2img_cannot_mislabel_style_references_as_source(self):
        self.p['modes']['image-to-image']['media']='references'
        with self.assertRaisesRegex(ValueError,'source-image'):r.validate_profile(self.p)

    def test_upscale_cannot_mislabel_style_references_as_source(self):
        self.p['modes']['upscale']=copy.deepcopy(self.p['modes']['reference-guided'])
        with self.assertRaisesRegex(ValueError,'input-image'):r.validate_profile(self.p)

    def test_card_comparison_does_not_accept_boolean_number_substitution(self):
        self.model['recommended_parameters']['unused']=1
        plan=self.compile();self.model['recommended_parameters']['unused']=True
        with self.assertRaisesRegex(ValueError,'guidance differs'):
            r.verify_contract(plan,intent=self.intent,parameters=plan['parameters'],prompt=self.prompt,record=self.model,reference_count=0)

    def test_wire_seed_must_match_requested_seed(self):
        plan=self.compile();wire={**plan['parameters'],'seed':19,'numberResults':1}
        with self.assertRaisesRegex(ValueError,'dispatch value differs'):
            r.check_wire(plan,wire,seed=3,count=1)

    def test_wire_count_must_match_requested_count(self):
        plan=self.compile();wire={**plan['parameters'],'seed':3,'numberResults':2}
        with self.assertRaisesRegex(ValueError,'dispatch value differs'):
            r.check_wire(plan,wire,seed=3,count=1)

    def test_recommendations_materialize_with_provenance(self):
        plan=self.compile();self.assertEqual(plan['parameters'],{'steps':24,'CFGScale':5.5})
        self.assertEqual(next(x for x in plan['parameter_decisions'] if x['key']=='steps')['status'],'model-recommendation')

    def test_explicit_overrides_win(self):
        self.assertEqual(self.compile({'CFGScale':4})['parameters']['CFGScale'],4)

    def test_missing_profile_blocks(self):
        with self.assertRaisesRegex(ValueError,'profile is missing'):
            r.selected_profile({'id':'unconfigured'},None)

    def test_mode_is_deliberate(self):
        self.intent['execution_mode']='unknown'
        with self.assertRaises(ValueError):self.compile()

    def test_missing_finish_axis_blocks(self):
        del self.intent['axes']['shading']
        with self.assertRaises(ValueError):self.compile()

    def test_missing_selection_reason_blocks(self):
        self.intent['selection']['reason']=''
        with self.assertRaises(ValueError):self.compile()

    def test_finish_phrase_must_reach_prompt(self):
        self.intent['prompt_expression']='unwritten finish'
        with self.assertRaisesRegex(ValueError,'absent'):self.compile()

    def test_preset_cannot_silently_change_axes(self):
        self.intent['axes']['medium']='photographic'
        with self.assertRaisesRegex(ValueError,'custom intent'):self.compile()

    def test_custom_and_region_specific_finishes(self):
        self.intent['preset']=None;self.intent['axes']['medium']='mixed-media'
        self.intent['regional_overrides']=[{'region':'background','axes':{'shading':'wash'},'reason':'Deliberate background treatment.','prompt_expression':'observatory'}]
        self.compile()

    def test_range_is_not_a_value(self):
        self.model['recommended_parameters']['guidance']=[4,6]
        with self.assertRaisesRegex(ValueError,'range'):self.compile()
        self.assertEqual(self.compile({'CFGScale':4})['parameters']['CFGScale'],4)

    def test_no_recommendation_does_not_mean_default(self):
        del self.model['recommended_parameters']['steps']
        with self.assertRaisesRegex(ValueError,'required explicit'):self.compile()

    def test_inapplicable_controls_are_not_sent(self):
        plan=self.compile();self.assertNotIn('strength',plan['parameters'])
        with self.assertRaisesRegex(ValueError,'not-applicable'):self.compile({'strength':0.7})

    def test_wrong_parameter_case_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'undeclared'):self.compile({'cfgScale':4})

    def test_backend_managed_controls_refuse_fabricated_values(self):
        self.p['modes']['text-to-image']['controls']['seed']=control('backend-managed',binding='dispatch-seed')
        plan=self.compile()
        with self.assertRaisesRegex(ValueError,'backend-managed'):r.dispatch_values(plan,seed=3,count=1)

    def test_seed_is_explicit_for_exposed_seed(self):
        plan=self.compile()
        with self.assertRaisesRegex(ValueError,'explicit seed'):r.dispatch_values(plan,seed=None,count=1)
        self.assertEqual(r.dispatch_values(plan,seed=12,count=1),(12,1))

    def test_boolean_not_accepted_as_integer(self):
        with self.assertRaises(ValueError):self.compile({'steps':True})

    def test_non_finite_values(self):
        with self.assertRaises(ValueError):self.compile({'CFGScale':float('nan')})

    def test_references_need_explicit_mode(self):
        with self.assertRaisesRegex(ValueError,'text-only'):self.compile(reference_count=1)
        self.intent['execution_mode']='reference-guided';self.compile(reference_count=1)

    def test_reference_mode_is_not_img2img(self):
        self.intent['execution_mode']='reference-guided'
        with self.assertRaisesRegex(ValueError,'not-applicable'):self.compile({'strength':0.4},reference_count=1)

    def test_img2img_requires_source_and_valid_strength(self):
        self.intent['execution_mode']='image-to-image'
        with self.assertRaises(ValueError):self.compile({'strength':0.4})
        self.compile({'strength':0.4},reference_count=1)
        with self.assertRaises(ValueError):self.compile({'strength':2},reference_count=1)

    def test_target_switch_invalidates_contract(self):
        plan=self.compile();self.model['recommended_parameters']['steps']=25
        with self.assertRaisesRegex(ValueError,'guidance differs'):
            r.verify_contract(plan,intent=self.intent,parameters=plan['parameters'],prompt=self.prompt,record=self.model,reference_count=0)

    def test_compiled_contract_is_recomputed(self):
        plan=self.compile();r.verify_contract(plan,intent=self.intent,parameters=plan['parameters'],prompt=self.prompt,reference_count=0)
        plan['parameter_decisions'][0]['reason']='tampered'
        with self.assertRaisesRegex(ValueError,'inconsistent'):
            r.verify_contract(plan,intent=self.intent,parameters=plan['parameters'],prompt=self.prompt,reference_count=0)

    def test_wire_cannot_add_or_change_a_control(self):
        plan=self.compile();wire={**plan['parameters'],'seed':3,'numberResults':1}
        r.check_wire(plan,wire,seed=3,count=1)
        with self.assertRaisesRegex(ValueError,'unavailable'):r.check_wire(plan,{**wire,'strength':0.7},seed=3,count=1)
        with self.assertRaisesRegex(ValueError,'differs'):r.check_wire(plan,{**wire,'CFGScale':7},seed=3,count=1)

    def test_nested_required_control(self):
        self.p['modes']['text-to-image']['controls'].pop('settings')
        self.p['modes']['text-to-image']['controls']['settings.quality']=control('required',schema={'enum':['draft','final']})
        with self.assertRaises(ValueError):self.compile()
        plan=self.compile({'settings':{'quality':'draft'}});self.assertEqual(plan['parameters']['settings'],{'quality':'draft'})

    def test_alternative_geometry_is_explicit(self):
        mode=self.p['modes']['text-to-image']
        mode['parameter_schema']={'oneOf':[{'required':['width','height'],'not':{'required':['size']}},{'required':['size'],'not':{'anyOf':[{'required':['width']},{'required':['height']}]}}]}
        with self.assertRaises(ValueError):self.compile()
        self.compile({'width':896,'height':1152});self.compile({'size':'896x1152'})
        with self.assertRaises(ValueError):self.compile({'width':896})

    def test_profile_schema_defaults_are_refused(self):
        self.p['modes']['text-to-image']['controls']['steps']['schema']['default']=30
        with self.assertRaisesRegex(ValueError,'defaults'):self.compile()

    def test_preset_axes_are_generic(self):
        choices=r.presets();self.assertGreaterEqual(len(choices),10)
        for preset in choices.values():self.assertEqual(set(preset['axes']),set(r.AXES))

    def test_display_includes_prompt_guidance(self):
        self.model['recommended_positive_prompt']='Explicit synthetic quality cue.'
        card=r.model_card(self.model);self.assertIn('prompt_recipe',card['execution_profile'])
        self.assertEqual(card['recommended_positive_prompt'],'Explicit synthetic quality cue.')
        self.assertIn('strength: not-applicable',r.summary(self.compile()))

    def test_saved_sorted_json_reverifies(self):
        plan=json.loads(r.encoded(self.compile()))
        r.verify_contract(plan,intent=self.intent,parameters=plan['parameters'],prompt=self.prompt,record=self.model,reference_count=0)

    def test_seed_and_count_dispositions_are_required(self):
        del self.p['modes']['text-to-image']['controls']['seed']
        with self.assertRaisesRegex(ValueError,'disposition'):self.compile()

    def test_nested_schema_defaults_do_not_run(self):
        self.p['modes']['text-to-image']['controls']['settings']['schema']={'type':'object','properties':{'quality':{'type':'string','default':'high'}}}
        with self.assertRaisesRegex(ValueError,'defaults'):self.compile()

    def test_literal_default_property_is_not_schema_default(self):
        self.p['modes']['text-to-image']['controls']['settings']['schema']={'const':{'default':'authored'}}
        self.compile({'settings':{'default':'authored'}})

    def test_unknown_schema_keyword_is_not_silently_ignored(self):
        self.p['modes']['text-to-image']['controls']['steps']['schema']['unimplementedMaximum']=6
        with self.assertRaisesRegex(ValueError,'unsupported'):self.compile()

    def test_combined_mode_schema_defaults_are_refused(self):
        self.p['modes']['text-to-image']['parameter_schema']={'properties':{'width':{'default':100}}}
        with self.assertRaisesRegex(ValueError,'defaults'):self.compile()

    def test_reference_count_is_not_a_boolean(self):
        self.intent['execution_mode']='reference-guided'
        with self.assertRaisesRegex(ValueError,'nonnegative integer'):self.compile(reference_count=True)

    def test_required_img2img_control_has_no_implicit_denoise(self):
        self.p['modes']['image-to-image']['controls']['strength']['status']='required'
        self.intent['execution_mode']='image-to-image'
        with self.assertRaisesRegex(ValueError,'required explicit'):self.compile(reference_count=1)
        self.compile({'strength':0.35},reference_count=1)

    def test_wire_layout_cannot_introduce_undeclared_settings(self):
        plan=self.compile();wire={**plan['parameters'],'seed':3,'numberResults':1,'unselectedTuning':6}
        layout={'fields':[{'field':['unselectedTuning'],'kind':'parameter'}]}
        with self.assertRaisesRegex(ValueError,'undeclared'):r.check_wire(plan,wire,layout,seed=3,count=1)

    def test_wire_rejects_boolean_integer_substitution(self):
        self.p['modes']['text-to-image']['controls']['toggle']=control(schema={'type':['boolean','integer']})
        plan=self.compile({'toggle':True});wire={**plan['parameters'],'seed':3,'numberResults':1,'toggle':1}
        with self.assertRaisesRegex(ValueError,'differs'):r.check_wire(plan,wire,seed=3,count=1)

    def test_dual_media_interface_follows_selected_mode(self):
        from model_contract import generation_media_counts
        offered={'request_keys':{'reference images':['refs'],'seed image':['seedImage']}}
        self.assertEqual(generation_media_counts(offered,1,media_role='seed-image'),{'seed image':1})
        self.assertEqual(generation_media_counts(offered,1,media_role='references'),{'reference images':1})
        with self.assertRaises(ValueError):generation_media_counts(offered,2,media_role='seed-image')

    def test_unavailable_count_does_not_invent_a_batch(self):
        self.p['modes']['text-to-image']['controls']['numberResults']=control('backend-managed',binding='dispatch-count')
        plan=self.compile()
        with self.assertRaisesRegex(ValueError,'invented batch'):r.dispatch_values(plan,seed=3,count=2)



class ExternalPackGuidanceTests(unittest.TestCase):
    """Use an isolated, synthetic pack to exercise public model-reading paths."""

    @classmethod
    def setUpClass(cls):
        import tempfile
        from pathlib import Path
        from pack_manager import write_lock
        cls.temp = tempfile.TemporaryDirectory(prefix='cpb-external-guidance-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        cls.pack = cls.root / 'external-content'
        cls.pack_id = '0190c000-0000-7000-8000-000000000088'
        cls.alias = 'external sample engine'
        cls.model_id = 'fixture-external-renderer'
        cls.model = {
            'id': cls.model_id, 'label': 'External renderer fixture',
            'aliases': [cls.alias], 'operation_kind': 'generation',
            'prompt_style': 'Explicitly synthetic instruction text.',
            'prompt_dialect': 'external-family',
            'ordering': ['rendering', 'subject', 'composition'],
            'supports_negative_prompt': True, 'negative_transport_mode': 'separate-field',
            'negative_transport_notes': 'Synthetic independent negative channel.',
            'recommended_parameters': {'steps': 17, 'guidance': 3.5},
            'recommended_positive_prompt': 'Synthetic external positive cue.',
            'recommended_negative_prompt': 'Synthetic external exclusion.',
            'recommendation_merge_mode': 'advisory-only',
            'search_terms': [{'phrase': cls.alias, 'facet': 'model', 'weight': 1.0, 'source': 'author'}],
            'offerings': [],
            'execution_profile': profile(seed=True, required={
                'steps': control('required', schema={'type':'integer', 'minimum':1}, recommendation='steps'),
                'CFGScale': control('required', schema={'type':'number', 'minimum':0}, recommendation='guidance'),
            }),
        }
        offered = copy.deepcopy(cls.model)
        offered['id'] = 'fixture-external-offered'
        offered['aliases'] = []
        del offered['execution_profile']
        offered['offerings'] = [{
            'service': 'synthetic-service', 'model_identifier': 'synthetic:renderer',
            'request_keys': {'prompt': ['positivePrompt']}, 'constraints': {},
            'observed_at': '2026-01-01', 'execution_profile': copy.deepcopy(cls.model['execution_profile']),
        }]
        unconfigured = copy.deepcopy(cls.model)
        unconfigured['id'] = 'fixture-external-unconfigured'
        unconfigured['aliases'] = []
        del unconfigured['execution_profile']
        cls.write(cls.pack / 'pack.json', {
            'pack_id': cls.pack_id, 'name': 'External guidance fixture', 'release': '2026.01.01.1',
            'description': 'Synthetic model guidance, with no provider claims.',
            'content': {'record_globs': ['records/**/*.json'], 'resource_globs': ['resources/**/*'],
                        'resource_bindings': {'prompt-dialects': 'resources/dialects.json',
                                              'prompt-writing-guide': 'resources/guide.json'}},
            'capabilities': ['model-adapters'], 'dependencies': [], 'optional_dependencies': [],
            'replaces': [], 'license': 'GPL-3.0-only',
        })
        cls.write(cls.pack / 'records/models.json', {'kind':'model', 'records':[cls.model, offered, unconfigured]})
        cls.write(cls.pack / 'resources/dialects.json', {
            'format': 'character-prompt-builder-prompt-dialects', 'name':'External fixture family',
            'description':'Synthetic wording family.',
            'dialects':[{'id':'external-family', 'name':'External family', 'description':'Synthetic grammar.',
                         'tag_separator': ', ', 'block_order':['rendering','subject']}],
        })
        cls.write(cls.pack / 'resources/guide.json', {
            'format':'character-prompt-builder-prompt-writing-guide', 'name':'External fixture guide',
            'description':'Synthetic guide.', 'sections':[
                {'id':'external-rule', 'title':'External rule', 'dialects':['external-family'],
                 'rules':['Synthetic rule selected from the same pack as the model.']},
            ],
        })
        write_lock(cls.pack)
        for variant, roots, enabled in [('registered',[str(cls.pack)],[cls.pack_id]),
                                         ('extra',[],[cls.pack_id]), ('disabled',[str(cls.pack)],[])]:
            cls.write(cls.root / variant / 'state.json', {
                'pack_roots': roots, 'enabled_packs': enabled,
                'resource_providers': {k:cls.pack_id for k in ('prompt-dialects','prompt-writing-guide')} if enabled else {},
            })

    @staticmethod
    def write(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')

    def selectors(self, variant='registered'):
        base = self.root / variant
        args = ['--state-file',str(base/'state.json'), '--cache-dir',str(base/'cache'),
                '--managed-root',str(base/'managed')]
        if variant == 'extra':
            args += ['--pack-root',str(self.pack)]
        return args

    def command(self, script, *args, variant='registered', succeeds=True):
        import os
        import subprocess
        import sys
        tail = [*self.selectors(variant),*args] if script == 'catalog_cli.py' else [*args,*self.selectors(variant)]
        process = subprocess.run([sys.executable,'-B',str(r.ROOT/'scripts'/script),*tail],
            cwd=self.root, capture_output=True, text=True, encoding='utf-8', timeout=60,
            env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','NO_COLOR':'1'})
        if succeeds:
            self.assertEqual(process.returncode,0,process.stdout+process.stderr)
        else:
            self.assertNotEqual(process.returncode,0,process.stdout+process.stderr)
        return process

    def check_card(self, card):
        self.assertEqual(card['recommended_parameters'], self.model['recommended_parameters'])
        self.assertEqual(card['recommended_positive_prompt'], self.model['recommended_positive_prompt'])
        self.assertEqual(card['recommended_negative_prompt'], self.model['recommended_negative_prompt'])

    def test_catalog_inspection_exposes_external_model_advice(self):
        result = json.loads(self.command('catalog_cli.py','inspect',self.model_id).stdout)
        self.assertEqual(result['source_pack'],self.pack_id)
        self.check_card(result['execution_guidance'][0])

    def test_model_card_resolves_external_alias_and_exact_service(self):
        self.check_card(json.loads(self.command('render_contract.py','model','--model',self.alias).stdout))
        offered = json.loads(self.command('render_contract.py','model','--model','fixture-external-offered',
                                           '--service','synthetic-service').stdout)
        self.check_card(offered)
        self.assertEqual(offered['model_identifier'],'synthetic:renderer')
        self.assertTrue(offered['ready_for_parameter_resolution'])

    def test_dialect_and_model_share_registered_or_extra_runtime(self):
        for variant in ('registered','extra'):
            with self.subTest(variant=variant):
                result = json.loads(self.command('prompt_dialect.py','--model',self.alias,variant=variant).stdout)
                self.assertEqual(result['model'],self.model_id)
                self.assertEqual(result['dialect']['id'],'external-family')
                self.assertEqual(result['guide']['dialect'][0]['id'],'external-rule')
                self.check_card(result['execution_guidance'][0])

    def test_route_reading_shows_external_model_card(self):
        project = self.root/'project'
        project.mkdir(exist_ok=True)
        output = self.command('execution_routes.py','read','generation','--feature','prompt-dialect',
                               '--model',self.alias,'--root',str(project),'--page-bytes','1024').stdout
        line = next(s for s in output.splitlines() if s.startswith('model-guidance: '))
        self.check_card(json.loads(line.partition(': ')[2])[0])

    def test_missing_profile_keeps_advice_visible_but_blocks_compile(self):
        model = 'fixture-external-unconfigured'
        card = json.loads(self.command('render_contract.py','model','--model',model).stdout)
        self.check_card(card)
        self.assertFalse(card['ready_for_parameter_resolution'])
        prompt = 'Flat graphic observatory.'
        self.write(self.root/'intent.json',intent(prompt))
        self.write(self.root/'parameters.json',{})
        (self.root/'prompt.txt').write_text(prompt,encoding='utf-8')
        result = self.command('render_contract.py','compile','--model',model,'--intent',str(self.root/'intent.json'),
            '--parameters',str(self.root/'parameters.json'),'--prompt-file',str(self.root/'prompt.txt'),
            '--reference-count','0',succeeds=False)
        self.assertIn('execution profile is missing',result.stdout)

    def test_disabled_pack_model_is_not_resolved_from_another_runtime(self):
        for script, args in [('render_contract.py',('model','--model',self.alias)),
                              ('prompt_dialect.py',('--model',self.alias))]:
            with self.subTest(script=script):
                result = self.command(script,*args,variant='disabled',succeeds=False)
                self.assertIn('model',result.stdout+result.stderr)

if __name__=='__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main(verbosity=2)
