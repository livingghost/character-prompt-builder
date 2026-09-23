"""Render explicitly declared conversions and retain their source at write time."""
from __future__ import annotations
import copy
from typing import Any
import execution_contract as c
import request_contract as rc
from input_evidence import InputEvidence


def _binding_id(row:dict)->str:
    return 'reference:'+str(row['reference_number'])


def validate_bindings(rows:Any)->list[dict]:
    if not isinstance(rows,list):raise ValueError('reference bindings must be an array')
    identifiers=set()
    for row in rows:
        c.exact(row,{'reference_number','attachment_number','region_pixels','role','controls','must_not_control'},'reference binding')
        for key in ('reference_number','attachment_number'):
            if type(row[key]) is not int or row[key]<1:raise ValueError('reference positions must be positive integers')
        if row['reference_number'] in identifiers:raise ValueError('reference number repeats')
        identifiers.add(row['reference_number']);c.text(row['role'],'reference role')
        for key in ('controls','must_not_control'):
            if not isinstance(row[key],list):raise ValueError('reference authority must be a list')
            for value in row[key]:c.text(value,'reference authority')
        if set(row['controls']) & set(row['must_not_control']):raise ValueError('reference authority conflicts with itself')
        if row['region_pixels'] is not None:
            c.exact(row['region_pixels'],{'x','y','width','height'},'reference region')
            for key,value in row['region_pixels'].items():
                if type(value) is not int or value<(1 if key in {'width','height'} else 0):raise ValueError('invalid reference region')
    if identifiers!=set(range(1,len(rows)+1)):raise ValueError('reference numbers must cover the selected order')
    return rows


def _reference_prefix(rows:list[dict],renderer:str)->str:
    if renderer=='reference-delivery':
        lines=['Reference positions identify the attached inputs, not the requested output layout.']
        for row in rows:
            location='Image '+str(row['attachment_number']);region=row['region_pixels']
            if region is not None:
                location+=', pixels x={x}, y={y}, width={width}, height={height}'.format(**region)
            lines.append('Reference '+str(row['reference_number'])+' means '+location+'. Role: '+row['role']+'.')
            if row['controls']:lines.append('Use this reference for: '+'; '.join(row['controls'])+'.')
            if row['must_not_control']:lines.append('Retain no authority over: '+'; '.join(row['must_not_control'])+'.')
        return '\n'.join(lines)+'\n\n'
    if renderer=='reference-binding-json':
        return 'Declared reference bindings:\n'+c.encoded(rows).decode('utf-8')+'\n'
    raise ValueError('the reference render contract names no installed renderer')


def reference_contract(policy:dict|None,reader:InputEvidence,expected_target:dict,dialect:str|None,rows:list[dict])->dict|None:
    validate_bindings(rows)
    if not rows:return None
    if policy is None:raise ValueError('selected reference bindings require an explicit reference_instruction_transport')
    c.exact(policy,{'mode','contract'},'reference instruction transport')
    mode=policy['mode']
    if mode not in {'native-fields','authored-rendition','prompt-prefix','not-supported'}:raise ValueError('unknown reference instruction transport')
    document=reader.json(policy['contract']);local=reader.at(policy['contract'])
    c.exact(document,{'artifact_type','target','dialects','mode','renderer','fields','basis'},'reference render contract')
    if document['artifact_type']!='reference-render-contract' or document['target']!=expected_target or document['mode']!=mode:
        raise ValueError('reference render contract target or mode differs from selected execution')
    if not isinstance(document['dialects'],list) or not document['dialects']:raise ValueError('reference contract requires explicit supported dialects')
    if dialect not in document['dialects']:raise ValueError('reference render contract does not cover the selected dialect')
    local.basis(document['basis'])
    if mode=='not-supported':raise ValueError('the selected execution contract cannot deliver the required reference authority')
    if mode=='prompt-prefix':
        if document['renderer'] not in {'reference-delivery','reference-binding-json'} or document['fields']!=[]:
            raise ValueError('prefix mode requires one installed renderer and no native fields')
    elif mode=='authored-rendition':
        if document['renderer'] is not None or document['fields']!=[]:raise ValueError('authored reference instructions have no automatic transform')
    else:
        if document['renderer'] is not None or not isinstance(document['fields'],list) or not document['fields']:
            raise ValueError('native reference mode requires explicit structural mappings')
        allowed={'reference_number','attachment_number','region_pixels','role','controls','must_not_control'}
        mapped=set();destinations=[]
        for item in document['fields']:
            c.exact(item,{'binding_field','request_field','container'},'native reference mapping')
            if item['binding_field'] not in allowed or item['binding_field'] in mapped:raise ValueError('native binding field is absent or duplicated')
            mapped.add(item['binding_field']);path=rc.path_parts(item['request_field'])
            if item['container'] not in {'ordered-array','single'}:raise ValueError('native mapping needs an explicit container')
            if item['container']=='single' and len(rows)!=1:raise ValueError('single native control cannot carry several reference bindings')
            if any(rc.overlaps(path,x) for x in destinations):raise ValueError('native reference fields overlap')
            destinations.append(path)
        required={'attachment_number','role'}
        for key in ('controls','must_not_control','region_pixels'):
            if any(row[key] for row in rows):required.add(key)
        if not required<=mapped:raise ValueError('native reference controls omit declared authority or region fields: '+', '.join(sorted(required-mapped)))
    return document


def compose(original:str,*,segments:list[dict]|None,authored_source:dict,bindings:list[dict],
            reference_policy:dict|None,production_consumer:dict|None,context_policy:str|None,
            policy_source:dict|None,reader:InputEvidence,target:dict,dialect:str|None)->dict:
    """Keep authored text intact and apply only the registered conversion operations."""
    if not isinstance(original,str):raise ValueError('rendition must be a string')
    validate_bindings(bindings)
    parts=[];trace=[];controls=[];requirements=[];offset=0
    def append(text,kind,refs,transform,binding_ids=None):
        nonlocal offset
        if not text:return
        parts.append(text);trace.append({'source_kind':kind,'source_refs':copy.deepcopy(refs),'transform_id':transform,
            'target_field':None,'target_range':{'start':offset,'end':offset+len(text)},'binding_ids':list(binding_ids or [])})
        offset+=len(text)
    if production_consumer is not None:
        mode=production_consumer['transport']
        if mode=='bounded-context':
            if context_policy!='prompt-prefix' or policy_source is None:
                raise ValueError('bounded production context requires a sourced prompt-prefix contract')
            context={key:production_consumer[key] for key in ('direction','criteria','world_views','moment_views')}
            append('Production context (hard constraints and advisory choices are distinct):\n'+c.encoded(context).decode('utf-8')+'\n',
                'production-context',[policy_source],'declared-production-context')
        elif mode!='authored-rendition':raise ValueError('unknown production consumer transport')
        requirements.append({'id':'production-direction','kind':'meaning','binding_ids':[],
            'sources':[authored_source],'statement':'Assess the selected direction against this exact rendition.'})
    contract=reference_contract(reference_policy,reader,target,dialect,bindings)
    if contract is not None:
        ids=[_binding_id(row) for row in bindings]
        if contract['mode']=='prompt-prefix':
            append(_reference_prefix(bindings,contract['renderer']),'reference-binding',[reference_policy['contract']],contract['renderer'],ids)
        elif contract['mode']=='native-fields':
            for item in contract['fields']:
                values=[row[item['binding_field']] for row in bindings]
                controls.append({'id':'reference-control:'+item['binding_field'],'field':rc.path_parts(item['request_field']),
                    'value':values if item['container']=='ordered-array' else values[0],'binding_ids':ids})
        requirements.append({'id':'reference-rendition','kind':'meaning','binding_ids':ids,
            'sources':[reference_policy['contract']],'statement':'Assess how the declared reference bindings reach this exact request.'})
    if segments is None:
        append(original,'authored',[authored_source],'selected-rendition')
    else:
        end=0
        for segment in segments:
            c.exact(segment,{'source_kind','start','end','text'},'rendition segment')
            if segment['source_kind'] not in {'authored','model-setting'}:raise ValueError('unknown rendition segment source')
            if type(segment['start']) is not int or type(segment['end']) is not int or segment['start']!=end or segment['end']<end:
                raise ValueError('rendition segments have a gap or overlap')
            if original[segment['start']:segment['end']]!=segment['text']:raise ValueError('rendition segment differs from the assembled text')
            append(segment['text'],segment['source_kind'],[authored_source],'authored-rendition' if segment['source_kind']=='authored' else 'chosen-recommendation')
            end=segment['end']
        if end!=len(original):raise ValueError('rendition segments do not cover the complete text')
    return {'text':''.join(parts),'trace':trace,'native_reference_controls':controls,'review_requirements':requirements}


def validate_review(review:Any,rendered:dict,requirements:list[dict],reader:InputEvidence)->None:
    """Verify assessment coverage, not the truth of the assessor's creative judgment."""
    c.exact(review,{'request_sha256','actor','assessments','guide_applied','evidence'},'request assessment')
    if review['request_sha256']!=rendered['request_sha256']:raise ValueError('request assessment covers a different rendered request')
    c.text(review['actor'],'request assessor');reader.basis(review['evidence'])
    if not isinstance(review['guide_applied'],list):raise ValueError('guide application selectors must be an array')
    seen=set()
    for item in review['assessments']:
        c.exact(item,{'id','binding_ids','conclusion','reason'},'request criterion assessment')
        c.text(item['reason'],'request assessment reason')
        if item['id'] in seen:raise ValueError('request assessment criterion repeats')
        seen.add(item['id'])
        requirement=next((r for r in requirements if r['id']==item['id']),None)
        if requirement is None or item['binding_ids']!=requirement['binding_ids']:raise ValueError('request assessment binding coverage differs')
        if item['conclusion']!='satisfied':raise ValueError('the assigned assessor has not accepted this request criterion')
    if seen!={r['id'] for r in requirements}:raise ValueError('request assessment has missing criteria')
