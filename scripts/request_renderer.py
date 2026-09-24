"""Build one exact generation request before authorization or external effects."""
from __future__ import annotations
import copy
from pathlib import Path
import execution_contract as c
import request_contract as rc
import model_rendition
import runtime_evidence
from execution_policy import load_policy


def prepare_forwarding(package:dict,verified:dict,*,root:Path|None,model_id:str,model:dict|None,offering:dict|None)->dict:
    record=package['request_validation'];reader=runtime_evidence.reader(root,snapshots=copy.deepcopy(package['input_snapshots']))
    expected=record['target'];policy,local=load_policy(record,reader,expected,dialect=(model or {}).get('prompt_dialect'))
    if offering is not None:
        if expected['service']!=offering['service'] or expected['model_identifier']!=offering['model_identifier']:
            raise ValueError('validation target differs from the selected offering')
        for key in ('production_context_transport','reference_instruction_transport'):
            declared=offering.get(key)
            if declared is not None and declared!=policy.get(key):raise ValueError('execution policy differs from its registered offering: '+key)
    selected=verified['selected_transport'];mode=selected['mode'];rendition=selected['rendition']
    integrated=mode in {'integrated-critical','retained-only'};original=rendition['text' if integrated else 'prompt']
    audit=package['generation_payload']['prompt_recommendations']['integrated' if integrated else 'positive']
    segments=audit['segments'] if audit is not None else None
    from reference_delivery import bindings
    prepared=package['prepared_reference_set'];rows=bindings(prepared['transport_mode'],prepared['selected_references'],prepared['single_board'])
    binding=package['production_binding'];consumer=binding['consumer'] if binding is not None else None
    result=model_rendition.compose(original,segments=segments,
        authored_source={'kind':'generation-rendition','sha256':c.digest(original.encode('utf-8'))},bindings=rows,
        reference_policy=policy.get('reference_instruction_transport'),production_consumer=consumer,
        context_policy=policy.get('production_context_transport'),policy_source=record['execution_policy'],
        reader=local,target=expected,dialect=policy.get('text_dialect') or (model or {}).get('prompt_dialect'))
    for limit,field in (((model or {}).get('max_positive_prompt_chars'),result['text']),):
        if type(limit) is int and len(field)>limit:raise ValueError('final prompt exceeds the selected model character limit')
    forwarding=copy.deepcopy(verified['host_forwarding']);forwarding.update(effective_prompt=result['text'],
        effective_prompt_sha256=c.digest(result['text'].encode('utf-8')),prompt_trace=result['trace'],
        native_reference_controls=result['native_reference_controls'],
        reference_media_role=package['render_contract']['model_card']['execution_profile']['modes'][package['render_contract']['intent']['execution_mode']]['media'])
    return {'host_forwarding':forwarding,'bindings':rows,'review_requirements':result['review_requirements'],
        'execution_policy':policy,'input_snapshots':reader.snapshots}


def generation(package:dict,verified:dict,model:dict,offering:dict,service:dict,transport,*,seed:int|None,count:int)->dict:
    if not hasattr(transport,'compile_request'):raise ValueError('transport must compile the complete request with a declared field layout')
    import render_contract_lib as rendering
    if rendering.encoded(rendering.model_card(model, offering)) != rendering.encoded(package['render_contract']['model_card']):
        raise ValueError('request renderer model/interface differs from the sealed render contract')
    rendering.dispatch_values(package['render_contract'], seed=seed, count=count)
    verified=copy.deepcopy(verified)
    intent=package['render_contract']['intent']
    profile=package['render_contract']['model_card']['execution_profile']
    verified['host_forwarding']['reference_media_role']=profile['modes'][intent['execution_mode']]['media']
    compiled=transport.compile_request(verified,offering,service,{},seed,count)
    rendering.check_wire(package['render_contract'], compiled['request'], compiled['layout'], seed=seed, count=count)
    rows=verified['bindings'];media=[]
    for i,item in enumerate(verified['host_forwarding']['selected_references']):
        item=rc.media_metadata(Path(item['resolved_path']),role=item['role'],
            binding_ids=['reference:'+str(r['reference_number']) for r in rows if r['attachment_number']==i+1]);media.append(item)
    expected=package['request_validation']['target']
    execution=rc.execution_hashes(service,offering,Path(transport.__file__),model=model,policy=verified['execution_policy'])
    value=package['visual_continuity'];context={'subjects':value['subjects'],'purpose':value['purpose'],'output_kind':'image'}
    return rc.seal(compiled['request'],compiled['layout'],media,expected,execution,compiled['request_trace'],rows,context)


def upscale(declaration:dict,model:dict,offering:dict,service:dict,transport,source:Path,settings:dict,*,root:Path)->dict:
    reader=runtime_evidence.reader(root,snapshots=copy.deepcopy(declaration['input_snapshots']))
    policy,_=load_policy(declaration['request_validation'],reader,declaration['request_validation']['target'])
    import render_contract_lib as rendering
    intent = declaration['render_intent']
    if intent['execution_mode'] != 'upscale':
        raise ValueError('upscale dispatch requires an upscale rendering intent')
    scale_path = (offering.get('parameter_keys') or {}).get('scale')
    if not scale_path:
        raise ValueError('upscale offering must declare parameter_keys.scale')
    authored = copy.deepcopy(settings)
    if rendering._get(authored, scale_path)[0]:
        raise ValueError('scale is supplied once, through the explicit scale option')
    rendering._put(authored, scale_path, declaration['scale_factor'])
    plan = rendering.compile_contract(model, offering, intent, authored,
        prompt=declaration['guidance_prompt'] or '', reference_count=1)
    rendering.dispatch_values(plan, seed=None, count=1)
    effective = copy.deepcopy(plan['parameters'])
    rc.remove(effective, rc.path_parts(scale_path))
    compiled=transport.compile_upscale(offering['model_identifier'],str(source),declaration['scale_factor'],effective,
        offering,service,{},declaration['guidance_prompt'])
    rendering.check_wire(plan, compiled['request'], compiled['layout'], seed=None, count=1)
    execution=rc.execution_hashes(service,offering,Path(transport.__file__),model=model,policy=policy)
    return rc.seal(compiled['request'],compiled['layout'],[rc.media_metadata(source,role='source-image')],
        declaration['request_validation']['target'],execution,compiled['request_trace'],[],
        {'output_kind':'image','render_contract':plan})


def envelope_fields(rendered:dict)->list[list]:
    """Only the adapter's declared management and operation fields are overlay slots."""
    operation=rendered['layout']['operation']
    return [*rendered['layout']['management'],*([operation] if operation is not None else [])]


def check_final(record:dict,reader,rendered:dict,*,known_schema:dict|None=None)->dict:
    from request_validation import require
    return require(record,reader,expected_target=rendered['sealed']['target'],execution=rendered['sealed']['execution'],
        rendered=rendered,envelope_fields=envelope_fields(rendered),known_schema=known_schema)
