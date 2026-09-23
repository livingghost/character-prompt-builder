"""Validate exact schema sources, authorized probes and observed request tuples."""
from __future__ import annotations
import copy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import execution_contract as c
import request_contract as rc
from input_evidence import InputEvidence
from state_protocol import validate_against_schema, unsupported_schema_keywords

MODES=frozenset({'target-schema','bounded-probe','observed-profile'})
FIELDS={'mode','target','service_execution_sha256','offering_contract_sha256','transport_sha256',
        'execution_policy','contract','evidence','unmeasured'}


def _ref(ref:Any)->None:
    c.exact(ref,{'path','sha256'},'validation evidence reference');c.text(ref['path'],'evidence path');c.sha(ref['sha256'])


def _unknowns(value:Any)->list[dict]:
    if not isinstance(value,list):raise ValueError('unmeasured statements must be a list')
    seen=set()
    for item in value:
        c.exact(item,{'id','scope','statement'},'unmeasured statement')
        for k,v in item.items():c.text(v,'unmeasured '+k)
        if item['id'] in seen:raise ValueError('duplicate unmeasured statement ID')
        seen.add(item['id'])
    return value


def validate_content(record:Any)->dict:
    c.exact(record,FIELDS,'request validation')
    if record['mode'] not in MODES:raise ValueError('unknown request validation mode')
    rc.target(record['target'])
    for key in ('service_execution_sha256','offering_contract_sha256','transport_sha256'):c.sha(record[key])
    for key in ('contract','evidence'):_ref(record[key])
    if record['execution_policy'] is not None:_ref(record['execution_policy'])
    _unknowns(record['unmeasured']);return record


def pointer(value:Any,path:str)->Any:
    """Resolve RFC 6901 components, without treating arbitrary text as a path."""
    if path=='':return value
    if not isinstance(path,str) or not path.startswith('/'):raise ValueError('JSON pointer must begin at the document root')
    for encoded in path[1:].split('/'):
        part=encoded.replace('~1','/').replace('~0','~')
        if isinstance(value,list):
            if not part.isdecimal() or str(int(part))!=part:raise ValueError('JSON pointer has a noncanonical list index')
            index=int(part)
            if index>=len(value):raise ValueError('JSON pointer selects an absent element')
            value=value[index]
        elif isinstance(value,dict) and part in value:value=value[part]
        else:raise ValueError('JSON pointer selects an absent member')
    return value


def acquisition(data:Any,reader:InputEvidence,*,expected:dict|None=None,successful:bool=False)->dict:
    c.exact(data,{'artifact_type','target','source','acquired_at','response','status'},'schema acquisition')
    if data['artifact_type']!='schema-acquisition':raise ValueError('expected schema acquisition evidence')
    rc.target(data['target'])
    if expected is not None and data['target']!=expected:raise ValueError('schema source target differs from the declared target')
    c.exact(data['source'],{'kind','identifier','locator'},'acquisition source')
    for k,v in data['source'].items():c.text(v,'acquisition source '+k)
    c.text(data['acquired_at'],'acquisition time')
    try:stamp=datetime.fromisoformat(data['acquired_at'].replace('Z','+00:00'))
    except ValueError as exc:raise ValueError('acquisition needs an ISO timestamp') from exc
    if stamp.tzinfo is None:raise ValueError('acquisition time must include its timezone')
    status=data['status'];body=reader.read(data['response'])
    if data['source']['kind']=='http':
        c.exact(status,{'http_status','transport_outcome'},'HTTP acquisition status')
        code=status['http_status']
        if code is not None and (type(code) is not int or not 100<=code<=599):raise ValueError('invalid HTTP status')
        if status['transport_outcome'] not in {'completed','connection-failed','indeterminate'}:raise ValueError('unknown transport acquisition outcome')
        if successful and not (status['transport_outcome']=='completed' and code is not None and 200<=code<300):
            raise ValueError('this acquisition does not contain a successful schema response')
    elif data['source']['kind']=='document':
        c.exact(status,{'document_status'},'document acquisition status')
        if status['document_status'] not in {'schema-provided','schema-not-provided'}:raise ValueError('unknown documented schema status')
        if successful and status['document_status']!='schema-provided':raise ValueError('this document declares no target schema')
    else:raise ValueError('unknown acquisition source kind')
    return {'metadata':data,'body':body}


def _schema_shape(schema:Any)->None:
    if not isinstance(schema,dict):raise ValueError('schema must be an object')
    # External references require their own explicitly packaged source resolution.
    # The local contract accepts self-contained schemas; it never fetches references.
    def walk(node):
        if not isinstance(node,dict):return
        if '$ref' in node and (not isinstance(node['$ref'],str) or not node['$ref'].startswith('#')):
            raise ValueError('schema references must resolve within the supplied schema document')
        for key in ('items','additionalProperties','propertyNames','not','if','then','else','contains'):
            walk(node.get(key))
        for key in ('properties','$defs','definitions','dependentSchemas'):
            for child in (node.get(key) or {}).values():walk(child)
        for key in ('allOf','anyOf','oneOf'):
            for child in node.get(key) or []:walk(child)
    walk(schema)


def schema_contract(contract:Any,evidence:Any,reader:InputEvidence,expected:dict,*,evidence_reader:InputEvidence|None=None)->dict:
    c.exact(contract,{'artifact_type','target','schema','schema_sha256','response_pointer','local_overlay'},'target schema contract')
    if contract['artifact_type']!='model-schema-contract' or contract['target']!=expected:raise ValueError('schema contract target mismatch')
    found=acquisition(evidence,evidence_reader or reader,expected=expected,successful=True)
    actual=pointer(c.decode(found['body']),contract['response_pointer'])
    _schema_shape(actual)
    if actual!=contract['schema'] or c.content_id(actual)!=contract['schema_sha256']:raise ValueError('schema differs from the acquired original bytes')
    overlay=reader.json(contract['local_overlay']) if contract['local_overlay'] is not None else None
    if overlay is not None:
        c.exact(overlay,{'artifact_type','target','fields','basis'},'local envelope overlay')
        if overlay['artifact_type']!='request-envelope-overlay' or overlay['target']!=expected:raise ValueError('envelope overlay target mismatch')
        reader.basis(overlay['basis'])
        if not isinstance(overlay['fields'],dict):raise ValueError('envelope overlay fields must be an object')
        for field,node in overlay['fields'].items():rc.path_parts(field);_schema_shape(node)
    return {'schema':actual,'overlay':overlay,'source':found['metadata']}


OBSERVED_FIELDS={'artifact_type','model_id','service','model_identifier','observed_at','source','schema'}


def observed_schema(record:dict,snapshot:Any,expected:dict)->dict:
    """Read the parameter schema an active pack records as observed for one offering.

    The pack file is both contract and evidence. It describes the model's
    parameters, so the fields a transport's layout declares as its envelope are
    checked by that layout, not by this schema.
    """
    if record['contract']!=record['evidence']:raise ValueError('an observed parameter schema is its own evidence')
    if not record['contract']['path'].startswith('@pack/'):raise ValueError('an observed parameter schema is read from an active pack')
    if not isinstance(snapshot,dict) or not OBSERVED_FIELDS<=set(snapshot) or set(snapshot)-OBSERVED_FIELDS-{'unenforced'}:
        raise ValueError('invalid observed parameter schema fields')
    if snapshot['artifact_type']!='observed-parameter-schema':raise ValueError('expected an observed parameter schema')
    if snapshot['service']!=expected['service'] or snapshot['model_identifier']!=expected['model_identifier']:
        raise ValueError('observed parameter schema belongs to another service or model')
    _schema_shape(snapshot['schema'])
    return {'schema':snapshot['schema'],'overlay':None,'source':snapshot,'transport_envelope':True}


def from_offering(model_id:str,model:dict,offering:dict,service:dict,transport,reader:InputEvidence)->dict:
    """Build a target-schema record from the observed schema an active pack's offering names.

    The record names that pack file and its hash as contract and evidence. It
    carries no execution policy, so the caller refuses references and bounded
    production context, which need the operator's policy.
    """
    for key in ('production_context_transport','reference_instruction_transport'):
        if key in offering:
            raise ValueError(f"the offering on {offering['service']!r} registers {key}; supply a request validation record with its execution policy")
    relative=offering.get('schema_snapshot')
    if not relative:raise ValueError(f"the offering on {offering['service']!r} names no observed schema; supply a request validation record")
    import runtime_evidence
    path=runtime_evidence.model_space(model_id)+'/'+relative
    snapshot=reader.json(reader.select(path))
    if not isinstance(snapshot,dict) or snapshot.get('model_id')!=model_id or any(
            snapshot.get(key)!=offering.get(key) for key in ('service','model_identifier','observed_at')):
        raise ValueError('observed schema '+path+' does not record this offering')
    operations=getattr(transport,'OPERATIONS',None)
    if not isinstance(operations,dict):raise ValueError('the transport declares no OPERATIONS')
    target={'service':offering['service'],'model_identifier':offering['model_identifier'],
            'operation':c.text(operations.get(model.get('operation_kind') or 'generation'),'transport operation')}
    execution=rc.execution_hashes(service,offering,Path(transport.__file__),model=model,policy=None)
    return build_record({'mode':'target-schema','contract':path,'evidence':path,'execution_policy':None},
                        reader,expected_target=target,execution=execution)


def reference_schema(ref:dict,reader:InputEvidence)->dict:
    value=reader.json(ref);reader=reader.at(ref)
    c.exact(value,{'artifact_type','target','source_target','acquisition','schema','response_pointer','relationship'},'reference schema')
    if value['artifact_type']!='model-schema-reference':raise ValueError('expected an explicitly attributed reference schema')
    rc.target(value['target']);rc.target(value['source_target']);reader.basis(value['relationship'])
    source=acquisition(reader.json(value['acquisition']),reader,expected=value['source_target'],successful=True)
    actual=pointer(c.decode(source['body']),value['response_pointer']);_schema_shape(actual)
    if actual!=value['schema']:raise ValueError('reference schema changed from its original source')
    return value


def _mentions_property(schema:dict,path:list[str])->bool:
    """Keep every declared constraint, including properties declared in branches."""
    nodes=[schema];seen=set()
    while nodes:
        node=nodes.pop()
        if not isinstance(node,dict) or id(node) in seen:continue
        seen.add(id(node));properties=node.get('properties',{})
        if path[0] in properties:
            if len(path)==1 or _mentions_property(properties[path[0]],path[1:]):return True
        nodes.extend((node.get('$defs') or {}).values());nodes.extend((node.get('definitions') or {}).values())
        for key in ('allOf','anyOf','oneOf'):nodes.extend(node.get(key) or [])
        for key in ('if','then','else','not'):nodes.append(node.get(key))
    return False


def check_schema(instance:dict,found:dict,*,envelope_fields:list[list]|None=None)->list[dict]:
    schema=found['schema'];projected=copy.deepcopy(instance);overlay=found['overlay']
    if overlay is not None:
        allowed=envelope_fields or []
        for key,rule in overlay['fields'].items():
            path=rc.path_parts(key)
            if path not in allowed:raise ValueError('overlay attempts to alter a non-envelope request field: '+key)
            if rc.present(projected,path):
                errors=validate_against_schema(rc.get(projected,path),rule)
                if errors:raise ValueError('request envelope '+key+': '+'; '.join(errors))
                if not _mentions_property(schema,path):rc.remove(projected,path)
    elif found.get('transport_envelope'):
        for path in envelope_fields or []:
            if rc.present(projected,path) and not _mentions_property(schema,path):rc.remove(projected,path)
    errors=validate_against_schema(projected,schema)
    if errors:raise ValueError('target schema refuses the built request: '+'; '.join(dict.fromkeys(errors)))
    return [{'id':'schema-keyword:'+x,'scope':x,'statement':'This schema keyword is not enforced by the local checker.'}
            for x in unsupported_schema_keywords(schema)]


def _merge_unknowns(*groups:list[dict])->list[dict]:
    found={}
    for group in groups:
        for item in _unknowns(group):
            if item['id'] in found and found[item['id']]!=item:raise ValueError('unmeasured statement ID has conflicting meanings')
            found[item['id']]=item
    return [found[k] for k in sorted(found)]


def analyze(record:dict,reader:InputEvidence,*,rendered:dict|None=None,envelope_fields:list[list]|None=None)->dict:
    validate_content(record);expected=record['target'];contract=reader.json(record['contract']);evidence=reader.json(record['evidence'])
    contract_reader=reader.at(record['contract']);evidence_reader=reader.at(record['evidence'])
    if record['execution_policy'] is not None:
        policy=reader.json(record['execution_policy'])
        if policy.get('target')!=expected:raise ValueError('execution policy belongs to a different target')
    unknown=[];checked=[]
    if record['mode']=='target-schema':
        if isinstance(contract,dict) and contract.get('artifact_type')=='observed-parameter-schema':
            found=observed_schema(record,contract,expected)
            unknown=[{'id':'observed-schema-source','scope':'schema-source','statement':'The schema is the observed parameter schema '
                      +record['contract']['path']+' in an active pack; no original service response is kept beside it.'}]
        else:
            found=schema_contract(contract,evidence,contract_reader,expected,evidence_reader=evidence_reader)
        unknown+=[{'id':'schema-keyword:'+x,'scope':x,'statement':'This schema keyword is not enforced by the local checker.'}
                  for x in unsupported_schema_keywords(found['schema'])]
        if rendered is not None:
            check_schema(rendered['request'],found,envelope_fields=envelope_fields);checked.append('target-schema')
    elif record['mode']=='bounded-probe':
        c.exact(contract,{'artifact_type','target','reason','basis','reference_schemas','fixed_request_profile','unknowns'},'bounded probe plan')
        if contract['artifact_type']!='model-probe-plan' or contract['target']!=expected:raise ValueError('probe plan target mismatch')
        c.text(contract['reason'],'probe reason');_ref(contract['basis'])
        if {**contract['basis'],'path':contract_reader.qualify(contract['basis']['path'])}!=record['evidence']:raise ValueError('probe evidence differs from its declared basis')
        acquisition(evidence,evidence_reader,expected=expected)
        if not isinstance(contract['reference_schemas'],list):raise ValueError('reference schemas must be a list')
        for ref in contract['reference_schemas']:
            reference=reference_schema(ref,contract_reader)
            if reference['target']!=expected:raise ValueError('reference schema was selected for another target')
        profile=contract['fixed_request_profile']
        if not isinstance(profile,dict) or profile.get('target')!=expected or (type(profile.get('output_count')) is not int or profile['output_count']!=1):
            raise ValueError('a probe fixes exactly one output for the declared target')
        if profile.get('execution')!={k:record[k] for k in ('service_execution_sha256','offering_contract_sha256','transport_sha256')}:raise ValueError('probe execution contract differs from its fixed request')
        if rendered is not None and rendered['sealed']!=profile:raise ValueError('probe request differs from the fixed trial request')
        unknown=_merge_unknowns(contract['unknowns'],[{'id':'target-parameters-unobserved','scope':'request',
            'statement':'The model-specific acceptance of this exact trial request is not established.'}])
        checked.append('bounded-probe-one-output')
    else:
        c.exact(contract,{'artifact_type','target','execution','observation','profile','profile_sha256'},'observed request profile')
        if contract['artifact_type']!='observed-request-profile' or contract['target']!=expected:raise ValueError('observed profile target mismatch')
        if {**contract['observation'],'path':contract_reader.qualify(contract['observation']['path'])}!=record['evidence']:raise ValueError('profile and success observation differ')
        from model_observation import validate_observation
        observed=validate_observation(evidence,evidence_reader)
        if observed['target']!=expected or observed['outcome']!='completed':raise ValueError('a completed observation of this target is required')
        if contract['profile']!=observed['request']['profile'] or contract['profile_sha256']!=c.content_id(contract['profile']):
            raise ValueError('profile differs from the exact successful request tuple')
        if contract['execution']!=observed['request']['sealed']['execution']:raise ValueError('profile execution contract changed')
        execution={k:record[k] for k in ('service_execution_sha256','offering_contract_sha256','transport_sha256')}
        if contract['execution']!=execution:raise ValueError('observation does not cover the selected execution contract')
        if rendered is not None and rendered['profile']!=contract['profile']:raise ValueError('fixed request values changed; explicitly prepare another probe or use a target schema')
        unknown=[{'id':'new-content-unobserved','scope':'authored-content',
            'statement':'The fixed parameter tuple and input form succeeded before; changed content has not been tested by that observation.'}]
        checked.append('observed-fixed-tuple')
    if rendered is not None:
        rc.validate_seal(rendered)
        if rendered['sealed']['target']!=expected:raise ValueError('built request target differs from validation')
        execution={k:record[k] for k in ('service_execution_sha256','offering_contract_sha256','transport_sha256')}
        if rendered['sealed']['execution']!=execution:raise ValueError('built request execution contract differs from validation')
    return {'mode':record['mode'],'target':expected,'checked':checked,'unmeasured':_merge_unknowns(unknown)}


def build_record(choices:dict,reader:InputEvidence,*,expected_target:dict,execution:dict,rendered:dict|None=None,envelope_fields:list[list]|None=None)->dict:
    c.exact(choices,{'mode','contract','evidence','execution_policy'},'validation choices')
    value={'mode':choices['mode'],'target':rc.target(expected_target),**execution,
        'contract':reader.select(choices['contract']),'evidence':reader.select(choices['evidence']),
        'execution_policy':reader.select(choices['execution_policy']) if choices['execution_policy'] is not None else None,'unmeasured':[]}
    result=analyze(value,reader,rendered=rendered,envelope_fields=envelope_fields)
    value['unmeasured']=result['unmeasured'];return value


def require(record:dict,reader:InputEvidence,*,expected_target:dict|None=None,execution:dict|None=None,
            rendered:dict|None=None,envelope_fields:list[list]|None=None,known_schema:dict|None=None)->dict:
    validate_content(record)
    if expected_target is not None and record['target']!=expected_target:raise ValueError('validation target differs from selected execution')
    if execution is not None and any(record[k]!=v for k,v in execution.items()):raise ValueError('validation was prepared for a different execution contract')
    result=analyze(record,reader,rendered=rendered,envelope_fields=envelope_fields)
    if result['unmeasured']!=record['unmeasured']:raise ValueError('unmeasured statements were changed instead of derived from their evidence')
    if known_schema is not None and rendered is not None:
        check_schema(rendered['request'],known_schema,envelope_fields=envelope_fields)
        result['checked'].append('current-known-target-constraints')
    return result
