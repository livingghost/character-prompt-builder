"""Build one exact generation request before authorization or external effects."""
from __future__ import annotations
import copy
from pathlib import Path
import execution_contract as c
import request_contract as rc
import model_rendition
import runtime_evidence
from execution_policy import load_policy


def prepare_forwarding(package:dict,verified:dict,*,root:Path|None,model_id:str,model:dict|None,offering:dict|None,
                       live_inputs:bool=True,input_source=None)->dict:
    record=package['request_validation'];reader=runtime_evidence.reader(root,snapshots=copy.deepcopy(package['input_snapshots']),live=live_inputs,source=input_source)
    expected=record['target'];policy,local=load_policy(record,reader,expected,dialect=(model or {}).get('prompt_dialect'))
    result=_forwarding(package,verified,model=model,offering=offering,policy=policy,local=local)
    return {**result,'input_snapshots':reader.snapshots}


def forwarding_from_inputs(package:dict,verified:dict,*,model:dict,offering:dict|None,policy:dict,evidence)->dict:
    """Compose forwarding from acquired immutable evidence without I/O."""
    from input_evidence import EvidenceInputs
    if not isinstance(evidence,EvidenceInputs):raise TypeError('forwarding requires acquired immutable evidence')
    reference=package['request_validation']['execution_policy']
    local=evidence.at(reference) if reference is not None else evidence
    return _forwarding(package,verified,model=model,offering=offering,policy=policy,local=local)


def _forwarding(package:dict,verified:dict,*,model:dict|None,offering:dict|None,policy:dict,local)->dict:
    expected=package['request_validation']['target']
    dialect=(model or {}).get('prompt_dialect')
    if policy and dialect is not None and policy['text_dialect']!=dialect:
        raise ValueError('execution policy text dialect differs from the selected model record')
    if offering is not None:
        if expected['service']!=offering['service'] or expected['model_identifier']!=offering['model_identifier']:
            raise ValueError('validation target differs from the selected offering')
        for key in ('reference_instruction_transport',):
            declared=offering.get(key)
            if declared is not None and declared!=policy.get(key):raise ValueError('execution policy differs from its registered offering: '+key)
    selected=verified['selected_transport'];mode=selected['mode'];rendition=selected['rendition']
    integrated=mode in {'integrated-critical','retained-only'};original=rendition['text' if integrated else 'prompt']
    audit=package['generation_payload']['prompt_recommendations']['integrated' if integrated else 'positive']
    segments=audit['segments'] if audit is not None else None
    from reference_delivery import bindings
    prepared=package['prepared_reference_set'];rows=bindings(prepared['transport_mode'],prepared['selected_references'],prepared['single_board'])
    result=model_rendition.compose(original,segments=segments,
        authored_source={'kind':'generation-rendition','sha256':c.digest(original.encode('utf-8'))},bindings=rows,
        reference_policy=policy.get('reference_instruction_transport'),
        reader=local,target=expected,dialect=policy.get('text_dialect') or (model or {}).get('prompt_dialect'))
    from prompt_weighting import selected as selected_weighting, from_contract, require_pair
    require_pair(result['text'], rendition.get('negative') or '',
                 selected_weighting(package['render_contract']['parameters'], from_contract(package['render_contract'])))
    for limit,field in (((model or {}).get('max_positive_prompt_chars'),result['text']),):
        if type(limit) is int and len(field)>limit:raise ValueError('final prompt exceeds the selected model character limit')
    forwarding=copy.deepcopy(verified['host_forwarding']);forwarding.update(effective_prompt=result['text'],
        effective_prompt_sha256=c.digest(result['text'].encode('utf-8')),prompt_trace=result['trace'],
        native_reference_controls=result['native_reference_controls'],
        reference_media_role=package['render_contract']['model_card']['execution_profile']['modes'][package['render_contract']['intent']['execution_mode']]['media'])
    return {'host_forwarding':forwarding,'bindings':rows,'review_requirements':result['review_requirements'],
        'execution_policy':policy}


def generation(package:dict,verified:dict,model:dict,offering:dict,service:dict,transport,*,seed:int|None,count:int,
               upload_sources:list|None=None,upload_source_read=None)->dict:
    if not hasattr(transport,'compile_request'):raise ValueError('transport must compile the complete request with a declared field layout')
    import render_contract_lib as rendering
    contract = package['render_contract']
    rendering.verify_contract(contract, intent=contract['intent'], parameters=contract['parameters'],
        prompt=package['composition_prompt'], record=model, offering=offering, reference_count=contract['reference_count'])
    rendering.dispatch_values(package['render_contract'], seed=seed, count=count)
    execution=rc.execution_hashes(service,offering,Path(transport.__file__),model=model,policy=verified['execution_policy'])
    return _generation_request(package,verified,model,offering,service,transport,
        consumer=(package.get('production_binding') or {}).get('consumer',{}),execution=execution,
        seed=seed,count=count,upload_sources=upload_sources,upload_source_read=upload_source_read)


def generation_from_inputs(content,consumer:dict,*,seed:int|None,count:int,resource_reader,
                           technical_media:list|None=None,upload_sources:list|None=None,upload_source_read=None)->dict:
    """Build a request from acquired meaning, with explicit media acquisition.

    Imported packages use ``generation`` and its independent contract validator.
    This path owns the model-specific execution checks that were formerly run
    after exporting and importing the compiler's own package.
    """
    from build_generation_payload import GenerationContent
    if not isinstance(content,GenerationContent):raise TypeError('request compilation requires acquired generation content')
    target=content.target
    if target.offering is None or target.service is None or target.transport is None:
        raise ValueError('request compilation requires an acquired execution offering')
    fields=content.fields
    reading=fields['route_reading']
    if fields['state_lineage']['mode']=='state-aware' and reading['route']!='state-series' and 'state-series' not in reading['features']:
        raise ValueError('state-aware generation requires the state-series reading')
    from route_reading import require_model_applications
    require_model_applications(reading,dialect=target.model.get('prompt_dialect'),resource_reader=resource_reader)
    verified=copy.deepcopy(content.forwarding)
    forwarding=verified['host_forwarding']
    selected=forwarding['selected_transport'];rendition=selected['rendition']
    prompt=rendition['text' if selected['mode'] in {'integrated-critical','retained-only'} else 'prompt']
    negative=rendition.get('negative','')
    from prompt_weighting import selected as selected_weighting,from_contract,require_pair
    syntax=selected_weighting(fields['generation_payload']['parameters'],from_contract(fields['render_contract']))
    require_pair(prompt,negative,syntax)
    from model_prompt_input import resolve_prompt_input
    if resolve_prompt_input(target.model)['mode']=='tag-based':
        from prompt_vocabulary_selection import require_final_selection
        require_final_selection(fields['retrieval_record'].get('vocabulary'),prompt=prompt,negative=negative,
                                model_record=target.model,syntax=syntax)
    if technical_media is not None:forwarding['technical_media']=copy.deepcopy(technical_media)
    from model_contract import generation_media_counts,request_instance,validate_request_schema,validate_output_count
    validate_output_count(target.model,count)
    parameters={**forwarding['parameters'],**target.transport.added_parameters(target.offering,seed,count)}
    counts=generation_media_counts(target.offering,len(forwarding['selected_references']),
                                  media_role=forwarding['reference_media_role'])
    for item in forwarding.get('technical_media',[]):counts[item['role']]=counts.get(item['role'],0)+1
    instance=request_instance(target.offering,parameters,prompt=forwarding['effective_prompt'],
        negative_prompt=negative if selected['mode'] in {'separate-field','native-subset'} else None,media_counts=counts)
    validate_request_schema(target.offering,instance,target.parameter_schema)
    execution=rc.execution_hash_values(target.service,target.offering,target.transport_sha256,
                                       model=target.model,policy=verified['execution_policy'])
    rendered=_generation_request(fields,verified,target.model,target.offering,target.service,target.transport,
        consumer=consumer,execution=execution,seed=seed,count=count,upload_sources=upload_sources,
        upload_source_read=upload_source_read)
    content.validation.check(expected_target=rendered['sealed']['target'],execution=rendered['sealed']['execution'],
                             rendered=rendered,envelope_fields=envelope_fields(rendered))
    return rendered


def _generation_request(package:dict,verified:dict,model:dict,offering:dict,service:dict,transport,*,
                        consumer:dict,execution:dict,seed:int|None,count:int,
                        upload_sources:list|None,upload_source_read)->dict:
    if not hasattr(transport,'compile_request'):raise ValueError('transport must compile the complete request with a declared field layout')
    import render_contract_lib as rendering
    contract=package['render_contract']
    verified=copy.deepcopy(verified)
    intent=package['render_contract']['intent']
    profile=package['render_contract']['model_card']['execution_profile']
    verified['host_forwarding']['reference_media_role']=profile['modes'][intent['execution_mode']]['media']
    compiled=transport.compile_request(verified,offering,service,{},seed,count)
    rendering.check_wire(package['render_contract'], compiled['request'], compiled['layout'], seed=seed, count=count)
    from prompt_weighting import wire_selection, from_contract, require_pair
    layout = compiled['layout']
    require_pair(rc.get(compiled['request'], layout['primary_text']),
        rc.get(compiled['request'], layout['negative_text']) if layout['negative_text'] is not None else '',
        wire_selection(compiled, from_contract(contract)))
    rows=verified['bindings'];media=[]
    for i,item in enumerate(verified['host_forwarding']['selected_references']):
        item=rc.media_metadata(Path(item['resolved_path']),role=item['role'],
            binding_ids=['reference:'+str(r['reference_number']) for r in rows if r['attachment_number']==i+1]);media.append(item)
    for item in verified['host_forwarding'].get('technical_media', []):
        media.append(rc.media_metadata(Path(item['resolved_path']), role=item['role']))
    media=rc.bind_upload_sources(media, [] if upload_sources is None else upload_sources, transport.UPLOAD_SOURCE,
        read=upload_source_read)
    expected=package['request_validation']['target']
    value=package['visual_continuity'];context={'subjects':value['subjects'],'purpose':value['purpose'],'output_kind':'image'}
    inputs = consumer.get('image_input')
    if inputs is not None:
        import image_input
        image_input.require_prepared(inputs, package['prepared_reference_set'], model_id=model['id'], target=expected)
        context['image_input'] = image_input.request_context(inputs)
    binding = consumer.get('semantic_edit')
    if binding is not None:
        import semantic_edit_plan
        semantic_edit_plan.require_input(binding, inputs)
        context['semantic_edit'] = semantic_edit_plan.request_context(binding)
    return rc.seal(compiled['request'],compiled['layout'],media,expected,execution,compiled['request_trace'],rows,context)


def upscale(declaration:dict,model:dict,offering:dict,service:dict,transport,source:Path,settings:dict,*,root:Path,
            upload_sources:list|None=None,upload_source_read=None,input_source=None)->dict:
    reader=runtime_evidence.reader(root,snapshots=copy.deepcopy(declaration['input_snapshots']),source=input_source)
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
    media=rc.bind_upload_sources([rc.media_metadata(source,role='source-image')],
        [] if upload_sources is None else upload_sources, transport.UPLOAD_SOURCE,read=upload_source_read)
    return rc.seal(compiled['request'],compiled['layout'],media,
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
