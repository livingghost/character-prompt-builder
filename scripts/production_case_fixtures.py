"""Complete synthetic cases for executable examples and current-contract tests.

Only test/example entrypoints use these authored fixture decisions. Operational
production code never imports this module to invent a reading, approval or
artistic decision on behalf of the user.
"""
from __future__ import annotations
import copy
import io
import json
import os
from pathlib import Path
from contextlib import contextmanager

import execution_contract as c
import pack_manager as packs
from render_contract_fixtures import profile,intent
from production_fixtures import ACTOR
from model_prompt_input_fixtures import prompt_input

ROOT=Path(__file__).resolve().parents[1]
PACK_ID='019a0290-1234-789a-8123-0123456789ab'
MODEL_ID='cpb-synthetic-image'
ALTERNATE_MODEL_ID='cpb-synthetic-alternate'
UPSCALE_MODEL_ID='cpb-synthetic-upscale'
ALTERNATE_UPSCALE_MODEL_ID='cpb-synthetic-upscale-alternate'
PROMPT='A flat graphic portrait of a simple synthetic robot standing against a plain background.'
REFERENCE_RETRY_PROMPT='A blue robot carrying a small yellow toolbox.'


def write(path:Path,value)->None:
    c.atomic(path,value.encode('utf-8') if isinstance(value,str) else c.encoded(value),replace=True)


def read_document(root: Path, choices: dict, name: str):
    """Read the selected editable fixture document through its public selector."""
    import production_authoring
    selected = choices['authoring']['documents'][name]
    path = c.local(root, selected['file'])
    value = path.read_text(encoding='utf-8') if name in production_authoring.TEXT_DOCUMENTS and 'field' not in selected else c.load(path)
    for part in selected.get('field', []):
        value = value[part]
    return value


def write_document(root: Path, choices: dict, name: str, value) -> None:
    """Author a fixture document in its standalone file and select it once."""
    import production_authoring
    documents = choices['authoring']['documents']
    if name not in documents:
        parent = Path(choices['authoring']['delivery']['file']).parent
        suffix = '.txt' if name in production_authoring.TEXT_DOCUMENTS else '.json'
        documents[name] = {'file': (parent / (name.replace('_', '-') + suffix)).as_posix()}
    selected = documents[name]
    path = c.local(root, selected['file'], exists=False)
    pointer = selected.get('field') or []
    if pointer:
        content = c.load(path)
        owner = content
        for part in pointer[:-1]:
            owner = owner[part]
        owner[pointer[-1]] = value
        value = content
    write(path, value)


@contextmanager
def edit_document(root: Path, choices: dict, name: str):
    """Keep a test's selected file edit explicit without copying bodies into choices."""
    value = read_document(root, choices, name)
    yield value
    write_document(root, choices, name, value)


def synthetic_profile()->dict:
    """The synthetic interface profile, with the output count on the synthetic service's `count` field."""
    declared=profile()
    for mode in declared['modes'].values():
        mode['controls']['count']=mode['controls'].pop('numberResults')
    return declared


def create_pack(path:Path, *, with_alternate:bool=False,with_upscale:bool=False,with_alternate_upscale:bool=False)->Path:
    write(path/'pack.json',{'pack_id':PACK_ID,'name':'CPB Synthetic Example','description':'Local synthetic protocol example; no provider capabilities are claimed.',
         'release':'2026.09.24.1','content':{'record_globs':['records/**/*.json'],'resource_globs':['resources/**/*'],
           'resource_bindings':{'service-profiles':'resources/services.json'}},
         'capabilities':['model-adapters'],'dependencies':[],'optional_dependencies':[],'replaces':[], 'license':'GPL-3.0-only'})
    model={'id':MODEL_ID,'label':'Local synthetic image fixture','aliases':['synthetic robot fixture'],'operation_kind':'generation',
        'prompt_input':prompt_input('descriptive'),
        'supports_negative_prompt':True,'prompt_style':'Authored synthetic prose.','negative_transport_mode':'separate-field',
        'negative_transport_notes':'Synthetic interface transports the declared negative field without a quality claim.',
        'ordering':['rendering','subject','composition','environment'],'reference_input_media_types':['image/png','image/jpeg','image/webp'],
        'search_terms':[{'phrase':'synthetic robot fixture','facet':'model','weight':1.0,'source':'author'}],
        'execution_profile':synthetic_profile(),
        'offerings':[{'service':'synthetic','model_identifier':'synthetic:robot','request_keys':{'model':['model'],'prompt':['prompt'],
            'negative prompt':['negative_prompt'],'reference images':['inputs.references'],'seed image':['seed_image']},
            'execution_profile':synthetic_profile(),'constraints':{'reference_images':{'max':4}},'observed_at':'2000-01-01'}]}
    models=[model]
    if with_alternate:
        alternate=copy.deepcopy(model)
        alternate.update(id=ALTERNATE_MODEL_ID,label='Alternative local synthetic fixture',aliases=['synthetic alternate fixture'])
        alternate['offerings'][0]['model_identifier']='synthetic:alternate'
        for declared in (alternate['execution_profile'], alternate['offerings'][0]['execution_profile']):
            declared['id']='synthetic-alternate-interface'
            for mode in declared['modes'].values():
                mode['controls']['steps']['schema']={'type':'integer','minimum':10,'maximum':24}
        models.append(alternate)
    if with_upscale:
        from render_contract_fixtures import control
        scaling=profile();scaling['id']='synthetic-upscale-interface'
        scaling['modes']={'upscale':{'media':'input-image','parameter_schema':{},
            'prompt_syntax':{'default':'literal','control':None},'controls':{
            'scale':control('required',schema={'type':'number','enum':[2,4]}),
            'count':control('not-applicable',binding='dispatch-count'),
            'seed':control('backend-managed',binding='dispatch-seed')}}}
        upscale={'id':UPSCALE_MODEL_ID,'label':'Local synthetic upscale fixture','aliases':['synthetic upscale fixture'],
            'prompt_input':prompt_input('none'),
            'operation_kind':'upscale','search_terms':[{'phrase':'synthetic upscale fixture','facet':'model','weight':1.0,'source':'author'}],'upscaler_class':'restorative','supported_scale_factors':[2,4],
            'input_image_count':1,'supports_guidance_prompt':False,'upscale_settings':{},
            'prompt_style':'Explicit image input and scale','ordering':['input-image','scale-parameters'],
            'execution_profile':scaling,'offerings':[{'service':'synthetic','model_identifier':'synthetic:upscale',
                'request_keys':{'input image':['image']},'parameter_keys':{'scale':'scale'},
                'execution_profile':scaling,'constraints':{},'observed_at':'2000-01-01'}]}
        models.append(upscale)
        if with_alternate_upscale:
            alternate_upscale=copy.deepcopy(upscale);alternate_upscale['id']=ALTERNATE_UPSCALE_MODEL_ID;alternate_upscale['label']='Alternative local synthetic upscale fixture'
            alternate_upscale['aliases']=['synthetic alternate upscale fixture'];alternate_upscale['offerings'][0]['model_identifier']='synthetic:upscale-alternate'
            alternate_upscale['execution_profile']['id']='synthetic-upscale-alternate-interface';alternate_upscale['offerings'][0]['execution_profile']['id']='synthetic-upscale-alternate-interface'
            models.append(alternate_upscale)
    write(path/'records/models.json',{'kind':'model','records':models})
    write(path/'resources/services.json',{'services':{'synthetic':{'label':'Synthetic non-network fixture','transport':'synthetic',
        'endpoint':{'base_url':'http://localhost/cpb-synthetic-no-network','method':'POST'},
        'operations':{'generate':{},'upscale':{}},'auth':{'scheme':'bearer','header':'Authorization'},
        'delivery':{'image':{'mode':'synchronous; an unfinished output is pending','poll':'lookup by request_id',
                             'terminal':'every output final','poll_interval_seconds':10}}}}})
    packs.write_lock(path)
    return path


def create(root:Path,runtime_root:Path,*,with_authority:bool=True,with_alternate:bool=False,with_upscale:bool=False,with_alternate_upscale:bool=False)->dict:
    import studio,work_ledger,production_spec,prompt_plot,prompt_retrieval,production_fixtures
    from catalog_retrieval import runtime
    from request_validation_fixtures import fixture_validation
    from reading_fixtures import task_reading
    root=studio.init(root,'synthetic-example','Synthetic production-contract example')
    studio.add_character(root,'robot','general')
    pack=create_pack(runtime_root/'packs/example',with_alternate=with_alternate,with_upscale=with_upscale,with_alternate_upscale=with_alternate_upscale)
    settings=packs.default_settings(extra_roots=[pack],state_file=runtime_root/'state.json',cache_dir=runtime_root/'cache',managed_root=runtime_root/'managed')
    initial=packs.load_state(packs.DEFAULT_PACK_STATE_PATH)
    # The synthetic pack's service profile outranks the commons one it does not require.
    state={'pack_roots':[],'enabled_packs':initial['enabled_packs']+[PACK_ID],'disabled_packs':[],
           'pack_order':[PACK_ID,*initial['enabled_packs']]}
    packs.save_state(settings.state_file,state);runtime.configure_pack_runtime(settings)
    catalog=runtime.load_pack_catalog()
    if not any(e.record.get('id')==MODEL_ID for e in catalog.entries):raise ValueError('Synthetic example pack did not validate.')
    begun=work_ledger.begin(root,'Synthetic no-network generation',['prepare','execute','inspect'])
    specification=production_spec.draft(model=MODEL_ID,brief='A synthetic robot demonstrates the input and execution contracts.',
                                       subject='robot',kind='robot',render_intent=intent(PROMPT))
    specification['subjects'][0]['identity']=['A deliberately unspecified synthetic test robot, not a real recurring character.']
    plot={'artifact_type':'prompt-plot','story':[{'id':'s1','beat':'The synthetic robot stands for a protocol demonstration.','visibility':'visible'}],
          'derived':[{'kind':'shows','statement':'one synthetic robot','from':['s1']},
                     {'kind':'placement','statement':'standing centred against a plain ground','from':['s1']},
                     {'kind':'must_preserve','statement':'the authored flat graphic presentation','from':['s1']},
                     {'kind':'composition','statement':'a centred full-body view at eye level','from':['s1']},
                     {'kind':'free','statement':'the precise plain background tone is not constrained'}]}
    plot['approved']={'by':'SYNTHETIC FIXTURE AUTHOR - NOT USER CONSENT','at':'2000-01-01T00:00:00Z','content_sha256':prompt_plot.content_sha256(plot)}
    # Actually execute the lookup; the fixture author elects composed wording.
    from catalog_retrieval.retrieval import search_entries
    found=search_entries(runtime.load_entries(),'synthetic robot fixture',kinds={'model'},categories=set(),domain=None,limit=5,diverse=False)
    write(root/'synthetic-search-results.json',found)
    record={'artifact_type':'prompt-retrieval-record','pack_state':catalog.fingerprint,
        'elements':[{'element':'synthetic robot fixture','queries':['synthetic robot fixture'],'inspected_records':[],
            'outcome':'composed','composed_wording':PROMPT,
            'reason':'Authored fixture wording after the recorded lookup; returned model records were not adopted as subject design.'}]}
    retrieval=prompt_retrieval.settle_retrieval_record(record,prompt=PROMPT,plot=plot)
    write(root/'prompt.txt',PROMPT);write(root/'spec.json',specification);write(root/'plot.json',plot);write(root/'retrieval.json',retrieval)
    write(root/'parameters.json',{'width':32,'height':32,'steps':20})
    write(root/'creative-intent.json',{'image_promise':'An explicitly synthetic protocol demonstration, not provider-quality evidence.'})
    validation=fixture_validation(root,MODEL_ID,reference_mode='authored-rendition',service='synthetic')
    write(root/'validation.json',validation)
    write(root/'brief.md','# Synthetic brief\n\nShow one simple robot as a protocol fixture. The image only has to be an identifiable '
          'small PNG; no artistic quality is asked for or judged.\n')
    task={'task_id':begun['task_id'],'production_id':packs.generate_uuid7(),'route':'generation','features':[],
          'sources':[{'id':'brief','path':'brief.md','role':'design','disposition':'applied','locator':'whole',
                      'reason':'The synthetic brief states what the fixture image has to show.'}],
          'delivery':{'path':'prompt.txt','translation_notes':'One canonical authored synthetic prompt.'},
          'criteria':[{'id':'output','strength':'hard','text':'The received fixture is an identifiable PNG with the declared dimensions.'}], 'world_views':[]}
    production_fixtures.task(root,task,artifact='image',execution='dispatcher')
    task['direction']['decisions']=[{'id':'expression','question':'How should this synthetic protocol fixture be presented?',
        'importance':'material','basis':['brief'],
        'options':[{'id':'flat','expression':'flat graphic portrait','realization':{'method':'authored prompt','instructions':PROMPT,
                        'capability_source':None,'limitations':['No artistic result is inferred from the mock response.']},
                    'tradeoffs':['Reads as a plain protocol figure rather than an illustration.']},
                   {'id':'outline','expression':'thin line drawing of the robot',
                    'realization':{'method':'authored prompt','instructions':'A thin line drawing of a simple synthetic robot on a plain background.',
                        'capability_source':None,'limitations':['Not prepared; the comparison is recorded, not generated.']},
                    'tradeoffs':['Thin lines can disappear at 32 by 32 pixels.']}],
        'selected':'flat','reason':'Explicit example-author choice for a legible small fixture; not a model inference.',
        'criteria':['output'],'depends_on':[],'deviations':[]}]
    task['generation']={'parameters':'parameters.json','production_spec':'spec.json','plot':'plot.json','retrieval_record':'retrieval.json',
        'creative_intent':'creative-intent.json','request_validation':'validation.json','service':'synthetic','count':1,'seed':None,
        'continuity':{'robot':'one-off'}}
    task['recording']={'character':'robot','slot':'candidate','subject_map':{},'sheet_panel':False,'role':'synthetic-example'}
    if not with_authority:task['authority']=None
    # Stable issuer ledger belongs to this studio so another CLI can verify it.
    from reading_fixtures import fixture_reading
    reading=fixture_reading(route='generation',studio=root,ledger=root/'work/reads.jsonl',model=MODEL_ID,service='synthetic', execution='dispatcher')
    write(root/'reading.json',reading);task['route_reading']='reading.json';write(root/'task.json',task)
    return {'root':root,'task':task,'settings':settings,'pack':pack,'model':MODEL_ID}


def adopted_case(root:Path,runtime_root:Path)->dict:
    """Generate, review, select and adopt the synthetic robot as the identity of slot base.front.

    Every decision is the labeled synthetic fixture author's, never user consent.
    The returned case adds the adopted run, candidate, iteration and its current
    Studio source to the case that `create` returns.
    """
    import production_execution as execution
    import production_fixtures
    import production_workflow as workflow
    import studio
    import studio_reference
    from visual_continuity import file_ref
    case=create(root,runtime_root)
    root=case['root'];task=case['task']
    task['recording'].update(slot='base.front',sheet_panel=True,subject_map={'robot':'robot'})
    task['generation']['continuity']['robot']='undecided'
    write(root/'task.json',task)
    run=workflow.prepare(root,'task.json')['run']
    candidate=execution.execute(root,run,decisions_file=fill_decisions(root,run,f'decisions-{run}.json'))['runs'][0]['candidates'][0]
    row=studio.read_iterations(studio.character_home(root,'robot'))[0]
    review=workflow.draft_review(root,run,candidate)
    review.update(reviewer='Synthetic test reviewer',observations=[{'evidence':'candidate','locator':{'kind':'whole'},
        'observation':'A real local synthetic PNG was captured.','interpretation':'Protocol fixture only.',
        'limitations':['No generative quality or user approval is asserted.']}],conclusion='Synthetic test decision.')
    for check in review['checks']:
        check.update(verdict='pass',observation_indices=[0],reason='Explicit synthetic fixture assessment.')
    write(root/'review.json',review);workflow.review(root,run,'review.json')
    write(root/'adoption-basis.txt','Explicit synthetic author decision to adopt this fixture identity. Not user consent.')
    approval={'scope':'sheet','influence':'identity','character':'robot','iteration_id':row['iteration_id'],
        'slot':row['slot'],'image_sha256':row['result']['sha256'],'by':ACTOR,'at':'2000-01-01T00:00:00Z',
        'continuity_decision':{'character_id':'robot','continuity':'recurring',
            'basis':file_ref(root,'adoption-basis.txt',locator='whole'),'by':ACTOR,'at':'2000-01-01T00:00:00Z'}}
    write(root/'approval.json',approval)
    choice=workflow.draft_selection(root,run,candidate)
    choice.update(reason='Synthetic delivery-only selection.')
    production_fixtures.selection(root,run,choice);write(root/'selection.json',choice)
    workflow.select(root,run,'selection.json')
    token=production_fixtures.grant(root,run,workflow.adoption_intent(root,run,candidate,'robot',row['iteration_id'],approval))
    workflow.adopt(root,run,candidate,'robot',row['iteration_id'],'approval.json',token)
    workflow.complete(root,run)
    import work_ledger
    for number in (1,2,3):
        work_ledger.step_done(root,number)
    work_ledger.finish(root,run)
    return {**case,'run':run,'candidate':candidate,'iteration_id':row['iteration_id'],'slot':row['slot'],
            'source':studio_reference.current_source(root,'robot',row['slot'])}


def reference_retarget_case(case: dict) -> dict:
    """Prepare a synthetic reference parent and author a different target's retry.

    The first interface accepts reference-guided requests; the second accepts
    instruction edits. Each owns its parameter schema and reference policy.
    These are explicit fixture-author selections, not inferred provider advice.
    """
    import production_inputs
    import production_workflow
    from catalog_retrieval import runtime
    from reading_fixtures import fixture_reading
    from request_validation_fixtures import fixture_validation
    from transport_synthetic import _png

    root = case['root']
    models = c.load(case['pack'] / 'records/models.json')
    modes = {MODEL_ID: 'reference-guided', ALTERNATE_MODEL_ID: 'instruction-edit'}
    targets = [model for model in models['records'] if model['id'] in modes]
    if len(targets) != 2:
        raise ValueError('The synthetic reference retry requires both example targets.')
    for model in targets:
        mode = modes[model['id']]
        if model['id'] == ALTERNATE_MODEL_ID:
            model['operation_kind'] = 'instruction-edit'
        offering = model['offerings'][0]
        for declared in (model['execution_profile'], offering['execution_profile']):
            declared['modes'] = {mode: declared['modes'][mode]}
            if model['id'] == ALTERNATE_MODEL_ID:
                declared['modes'][mode]['controls']['seed'].update(status='optional',
                    schema={'type': 'integer', 'minimum': 0, 'maximum': 100})
        schema = {'type': 'object', 'properties': {'width': {'const': 32}, 'height': {'const': 32}}}
        if model['id'] == ALTERNATE_MODEL_ID:
            # A deliberately unmeasured media rule exercises fresh evidence
            # derivation. The fixture claims no live reference-size check.
            schema['x-constraints'] = [{'parameters': ['inputs.references'],
                'constraint': 'reference-bytes', 'maximum': 4096}]
        offering['schema_snapshot'] = 'resources/' + model['id'] + '-parameters.json'
        write(case['pack'] / offering['schema_snapshot'], {
            'artifact_type': 'observed-parameter-schema', 'model_id': model['id'],
            'service': offering['service'], 'model_identifier': offering['model_identifier'],
            'observed_at': offering['observed_at'],
            'source': 'Synthetic target-specific reference retry fixture.', 'schema': schema})
    write(case['pack'] / 'records/models.json', models)
    packs.write_lock(case['pack'])
    runtime.configure_pack_runtime(case['settings'])
    policies = {model['id']: fixture_validation(root, model['id'], service='synthetic',
        reference_mode='authored-rendition')['execution_policy']['path'] for model in targets}

    task = c.load(root / 'task.json')
    for field in ('plot', 'retrieval_record', 'creative_intent', 'request_validation'):
        task['generation'].pop(field)
    task['direction']['decisions'] = []
    specification = c.load(root / 'spec.json')
    specification['render_intent'] = {'artifact_type': 'render-intent', 'execution_mode': 'reference-guided'}
    write(root / 'spec.json', specification)
    write(root / 'prompt.txt', REFERENCE_RETRY_PROMPT)
    write(root / 'reading.json', fixture_reading(route='generation', studio=root, ledger=root / 'work/reads.jsonl',
        model=MODEL_ID, service='synthetic', execution='dispatcher'))
    write(root / 'task.json', task)
    c.atomic(root / 'reference.png', _png(32, 32, b'\x20\x50\x90'))
    authored = production_inputs.draft_inputs(root, 'task.json', 'reference-parent')
    choices = authored['choices']
    choices['validation'] = {'mode': 'target-schema', 'contract': None, 'evidence': None,
        'execution_policy': policies[MODEL_ID]}
    choices['authoring']['references']['additional_references'] = [{'role': 'identity',
        'source': {'kind': 'supplied-file', 'reference_id': 'character-source', 'resolved_path': 'reference.png'},
        'subject_uses': [{'subject_id': 'robot', 'use': 'identity', 'priority': 1}]}]
    choices['authoring']['task']['criteria'].append({'id': 'continuity', 'strength': 'hard', 'evidence': 'image',
        'text': 'Compare the complete original identity reference and preserve its robot identity.',
        'identity_review': ['robot'], 'identity_bindings': [{'source': 'reference:character-source',
            'subject_ids': ['robot'], 'selectors': [''], 'treatment': 'preserve',
            'reason': 'Both synthetic trials retain the same original identity source.', 'variation': None,
            'carriers': [{'kind': 'reference', 'reference': 'character-source', 'use': 'identity'}]}]})
    write(root / authored['choices_file'], choices)
    parent = production_workflow.prepare(root, choices=authored['choices_file'])

    draft = production_inputs.draft_inputs(root, None, 'reference-retarget', from_run=parent['run'],
        model=ALTERNATE_MODEL_ID, service='synthetic')
    choices = draft['choices']
    inherited = copy.deepcopy(choices)
    reading = fixture_reading(route='generation', studio=root, ledger=root / 'work/reads.jsonl',
        model=ALTERNATE_MODEL_ID, service='synthetic', execution='dispatcher')
    choices['reading']['reading_key'] = reading['reading_key']
    choices['validation']['execution_policy'] = policies[ALTERNATE_MODEL_ID]
    with edit_document(root, choices, 'production_spec') as document:
        document['render_intent']['execution_mode'] = 'instruction-edit'
    with edit_document(root, choices, 'parameters') as document:
        document['steps'] = 22
    write(root / draft['choices_file'], choices)
    return {'parent': parent, 'parent_choices_file': authored['choices_file'],
        'choices_file': draft['choices_file'], 'inherited_choices': inherited}


def copy_studio(origin:Path,target:Path)->Path:
    """Copy a prepared synthetic studio to `target` for one test, symbolic links kept as links.

    The helper refuses a studio holding a directory junction, because the copy
    would hold a plain folder in its place. Build that studio from an empty
    folder instead.

    Every studio record names its files relative to the studio, so the copy
    is a separate studio. It shares the pack runtime `create` configured, and
    stays current only while that runtime is unchanged.
    """
    import shutil,stat
    folders=[os.fspath(origin)]
    while folders:
        with os.scandir(folders.pop()) as entries:
            for entry in entries:
                info=entry.stat(follow_symlinks=False)
                if os.name=='nt' and info.st_reparse_tag==stat.IO_REPARSE_TAG_MOUNT_POINT:
                    raise ValueError(f'{entry.path} is a directory junction; build this studio from an empty folder, '
                                     'because a copy holds a plain folder in its place.')
                if stat.S_ISDIR(info.st_mode):folders.append(entry.path)
    shutil.copytree(origin,target,symlinks=True)
    return target.resolve()


def alternate_task(root: Path, *, steps: int = 22) -> str:
    """Author a labeled synthetic retarget case, not a production decision helper."""
    from catalog_retrieval import runtime
    from catalog_retrieval.retrieval import search_entries
    from prompt_retrieval import settle_retrieval_record
    from reading_fixtures import fixture_reading
    from request_validation_fixtures import fixture_validation
    task=c.load(root/'task.json')
    specification=c.load(root/task['generation']['production_spec'])
    specification['target_model']=ALTERNATE_MODEL_ID
    write(root/'retarget/spec.json',specification)
    parameters=c.load(root/task['generation']['parameters']);parameters['steps']=steps
    write(root/'retarget/parameters.json',parameters)
    found=search_entries(runtime.load_entries(),'synthetic alternate fixture',kinds={'model'},categories=set(),domain=None,limit=5,diverse=False)
    write(root/'retarget/search-results.json',found)
    record=c.load(root/task['generation']['retrieval_record'])
    record['pack_state']=runtime.load_pack_catalog().fingerprint
    record['elements'][0]['queries'].append('synthetic alternate fixture')
    record['elements'][0]['reason']='Explicit synthetic author reassessment after the recorded alternate-model lookup.'
    prompt=(root/task['delivery']['path']).read_text(encoding='utf-8')
    record=settle_retrieval_record(record,prompt=prompt,plot=c.load(root/task['generation']['plot']))
    write(root/'retarget/retrieval.json',record)
    validation=fixture_validation(root,ALTERNATE_MODEL_ID,reference_mode='authored-rendition',service='synthetic')
    write(root/'retarget/validation.json',validation)
    reading=fixture_reading(route=task['route'],features=task['features'],studio=root,ledger=root/'work/reads.jsonl',model=ALTERNATE_MODEL_ID,service='synthetic', execution=task['execution'])
    write(root/'retarget/reading.json',reading)
    task['route_reading']='retarget/reading.json'
    task['generation'].update(production_spec='retarget/spec.json',parameters='retarget/parameters.json',
                             retrieval_record='retarget/retrieval.json',request_validation='retarget/validation.json')
    write(root/'retarget/task.json',task)
    return 'retarget/task.json'


def upscale_task(root:Path,*,source:str='upscale/source.png',scale:int=2)->str:
    """Author a complete synthetic upscale task with explicitly local permission."""
    import production_fixtures
    from request_validation_fixtures import fixture_validation
    from production_binding import upscale_request
    from reading_fixtures import fixture_reading
    from transport_synthetic import _png
    if not (root/source).exists():
        c.atomic(root/source,_png(32,32,b'\x50\x80\xa0'))
    task=c.load(root/'task.json')
    task['route']='upscale';task['features']=[];task.pop('generation')
    task['delivery']={'path':'upscale/input.json',
                      'translation_notes':'An exact upscale input declaration; not a natural-language approximation.'}
    task['sources']=[{'id':'source','path':source,'role':'upscale-source','disposition':'applied','locator':'whole image',
                     'reason':'The explicitly declared synthetic image to enlarge.'}]
    production_fixtures.task(root,task,artifact='image',execution='dispatcher')
    task['upscale']={'service':'synthetic'}
    validation=fixture_validation(root,UPSCALE_MODEL_ID,reference_mode='authored-rendition',service='synthetic')
    request=upscale_request(root,root/source,UPSCALE_MODEL_ID,scale,{},None,request_validation=validation,render_intent=intent('','upscale'))
    write(root/'upscale/input.json',request)
    reading=fixture_reading(route='upscale',studio=root,ledger=root/'work/reads.jsonl',model=UPSCALE_MODEL_ID,service='synthetic', execution='dispatcher')
    write(root/'upscale/reading.json',reading);task['route_reading']='upscale/reading.json'
    write(root/'upscale/task.json',task)
    return 'upscale/task.json'


def alternate_upscale_task(root:Path,*,source:str='upscale/source.png',scale:int=2)->str:
    """Author a second complete upscale target for retarget contract tests."""
    from request_validation_fixtures import fixture_validation
    from production_binding import upscale_request
    from reading_fixtures import fixture_reading
    task=c.load(root/upscale_task(root,source=source,scale=scale))
    validation=fixture_validation(root,ALTERNATE_UPSCALE_MODEL_ID,reference_mode='authored-rendition',service='synthetic')
    write(root/'upscale/alternate-validation.json',validation)
    request=upscale_request(root,root/source,ALTERNATE_UPSCALE_MODEL_ID,scale,{},None,request_validation=validation,render_intent=intent('','upscale'))
    write(root/'upscale/alternate-input.json',request)
    task['delivery']['path']='upscale/alternate-input.json'
    reading=fixture_reading(route='upscale',studio=root,ledger=root/'work/reads.jsonl',model=ALTERNATE_UPSCALE_MODEL_ID,service='synthetic', execution='dispatcher')
    write(root/'upscale/alternate-reading.json',reading);task['route_reading']='upscale/alternate-reading.json'
    write(root/'upscale/alternate-task.json',task)
    return 'upscale/alternate-task.json'


def fill_decisions(root:Path,run:str,path:str)->str:
    """Write the execution decisions of a run as the labeled synthetic fixture operator; never user consent."""
    import production_execution as execution
    import production_store as store
    import production_workflow as workflow
    value=execution.draft_execution(root,run,'fixture-grant')['choices']
    authority=store.authority(root,workflow.load_run(root,run)[1]['task']['task_id'])
    for request in value['decisions']:
        request['reason']='Explicit synthetic fixture decision. Not user consent.'
        if request['operation']=='submit':
            if 'principal_approval' in request['request_decision']:
                request['request_decision']['principal_approval'] = {
                    'path': authority['evidence']['path'], 'locator': authority['evidence']['locator']}
            from production_fixtures import assess_rendition
            assess_rendition(request['request_decision']['rendition_review'])
    write(root/path,value)
    return path


