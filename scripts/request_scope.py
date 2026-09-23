"""Match explicit delegation cases to the fields of one rendered request."""
from __future__ import annotations
import copy
import math
from typing import Any
import execution_contract as c
import request_contract as rc

MODES={'target-schema','bounded-probe','observed-profile'}


def _strings(values:Any,label:str,*,empty:bool=True)->list[str]:
    if not isinstance(values,list) or (not empty and not values):raise ValueError(label+' must be an explicit array')
    for value in values:c.text(value,label)
    if len(set(values))!=len(values):raise ValueError(label+' contains duplicate IDs')
    return values


def _basis(ref:Any)->None:
    c.exact(ref,{'path','sha256','locator'},'delegation basis');c.text(ref['path'],'basis path');c.sha(ref['sha256']);c.text(ref['locator'],'basis locator')


def validate(scope:Any,*,submit:bool,modes:Any)->None:
    _strings(modes,'submission validation modes')
    if set(modes)-MODES:raise ValueError('unknown delegated validation mode')
    if not submit:
        if scope is not None or modes:raise ValueError('non-submit permission has no request scope or validation mode')
        return
    if not modes:raise ValueError('submit permission requires explicit validation modes')
    if scope is None:return
    c.exact(scope,{'plan','cases'},'request scope');_basis(scope['plan'])
    if not isinstance(scope['cases'],list) or not scope['cases']:raise ValueError('delegation requires at least one explicit case')
    ids=set()
    for case in scope['cases']:
        c.exact(case,{'id','productions','targets','fixed','variations','review_criteria'},'request scope case')
        c.text(case['id'],'scope case ID')
        if case['id'] in ids:raise ValueError('duplicate request scope case ID')
        ids.add(case['id'])
        if not isinstance(case['productions'],list) or not case['productions']:raise ValueError('scope case requires explicit production selectors')
        for selected in case['productions']:
            if not (isinstance(selected,str) and selected or isinstance(selected,dict) and selected):raise ValueError('invalid production selector')
        if len({c.content_id(x) for x in case['productions']})!=len(case['productions']):raise ValueError('production selector repeats')
        if not isinstance(case['targets'],list) or not case['targets']:raise ValueError('scope requires explicit execution targets')
        for selected in case['targets']:
            c.exact(selected,{'target','execution'},'delegated execution target');rc.target(selected['target'])
            c.exact(selected['execution'],{'service_execution_sha256','offering_contract_sha256','transport_sha256'},'execution hashes')
            for value in selected['execution'].values():c.sha(value)
        if len({c.content_id(x) for x in case['targets']})!=len(case['targets']):raise ValueError('execution target repeats')
        if not isinstance(case['fixed'],dict) or not isinstance(case['variations'],dict):raise ValueError('scope needs fixed and variable field maps')
        if set(case['fixed'])&set(case['variations']):raise ValueError('a delegated field cannot be both fixed and variable')
        for name in set(case['fixed'])|set(case['variations']):c.text(name,'declared field ID')
        criteria=_strings(case['review_criteria'],'scope review criteria')
        for name,rule in case['variations'].items():
            if not isinstance(rule,dict):raise ValueError('variation rule must be an object')
            if rule.get('kind')=='values':
                c.exact(rule,{'kind','values'},'finite variation')
                if not isinstance(rule['values'],list) or not rule['values']:raise ValueError('finite variation requires explicit values')
                if len({c.content_id(x) for x in rule['values']})!=len(rule['values']):raise ValueError('variation values repeat')
            elif rule.get('kind')=='range':
                c.exact(rule,{'kind','type','minimum','maximum'},'numeric variation')
                if rule['type'] not in {'integer','number'}:raise ValueError('numeric variation needs a declared type')
                for value in (rule['minimum'],rule['maximum']):
                    if type(value) not in {int,float} or not math.isfinite(value):raise ValueError('variation bound must be finite numeric data')
                    if rule['type']=='integer' and type(value) is not int:raise ValueError('integer variation bounds must be integers')
                if rule['minimum']>rule['maximum']:raise ValueError('variation minimum exceeds maximum')
            elif rule.get('kind')=='authored-content':
                c.exact(rule,{'kind','source','criterion'},'authored content variation');_basis(rule['source'])
                if rule['criterion'] not in criteria:raise ValueError('content variation requires a declared review criterion')
            else:raise ValueError('unknown explicit variation rule')


def build_case(rendered:dict,*,identifier:str,productions:list,variations:dict,review_criteria:list)->dict:
    """Draft fixed values from a baseline; the principal still supplies the delegation."""
    rc.validate_seal(rendered)
    absent=set(variations)-set(rendered['fields'])
    if absent:raise ValueError('variation names undeclared request fields: '+', '.join(sorted(absent)))
    case={'id':identifier,'productions':copy.deepcopy(productions),
        'targets':[{'target':rendered['sealed']['target'],'execution':rendered['sealed']['execution']}],
        'fixed':{key:copy.deepcopy(item['value']) for key,item in rendered['fields'].items() if key not in variations},
        'variations':copy.deepcopy(variations),'review_criteria':list(review_criteria)}
    return case


def assess(scope:dict|None,*,case_id:str|None,rendered:dict,production:Any,mode:str,modes:list[str],
           assessments:list[dict]|None=None,principal_approval:dict|None=None)->dict:
    """Return structural eligibility separately from supplied human or actor judgments."""
    validate(scope,submit=True,modes=modes);rc.validate_seal(rendered)
    reasons=[];needs=[]
    if mode not in modes:reasons.append({'code':'validation-mode-outside-scope','field':'validation_mode','actual':mode})
    if scope is None:
        if case_id is not None:raise ValueError('a scope case was selected without a delegated plan')
        if principal_approval is None:
            reasons.append({'code':'exact-principal-approval-required','field':'principal_approval'})
        else:
            c.exact(principal_approval,{'request_sha256','principal','evidence'},'exact request approval')
            c.text(principal_approval['principal'],'approving principal');_basis(principal_approval['evidence'])
            if principal_approval['request_sha256']!=rendered['request_sha256']:
                reasons.append({'code':'principal-approval-request-mismatch','field':'request_sha256'})
        case=None
    else:
        cases=[x for x in scope['cases'] if x['id']==case_id]
        if len(cases)!=1:raise ValueError('select one explicit delegation case; cases are not merged')
        case=cases[0]
        if production not in case['productions']:reasons.append({'code':'production-outside-scope','field':'production','actual':production})
        selected={'target':rendered['sealed']['target'],'execution':rendered['sealed']['execution']}
        if selected not in case['targets']:reasons.append({'code':'target-outside-scope','field':'target','actual':selected})
        fields=rendered['fields'];declared=set(case['fixed'])|set(case['variations'])
        if declared!=set(fields):reasons.append({'code':'request-field-set-changed','field':'fields','missing':sorted(set(fields)-declared),'extra':sorted(declared-set(fields))})
        for name,wanted in case['fixed'].items():
            if name in fields and fields[name]['value']!=wanted:reasons.append({'code':'fixed-field-changed','field':name,'actual':fields[name]['value'],'expected':wanted})
        for name,rule in case['variations'].items():
            if name not in fields:continue
            item=fields[name];value=item['value'];accepted=False
            if rule['kind']=='authored-content':
                if item['kind'] not in {'content','media'}:reasons.append({'code':'noncontent-variation','field':name})
                else:accepted=True
            elif item['kind']!='parameter':
                reasons.append({'code':'nonparameter-variation','field':name})
            elif rule['kind']=='values':accepted=any(type(value) is type(x) and value==x for x in rule['values'])
            else:
                accepted=type(value) in {int,float} and math.isfinite(value) and (rule['type']!='integer' or type(value) is int) and rule['minimum']<=value<=rule['maximum']
            if not accepted and not any(x.get('field')==name for x in reasons):reasons.append({'code':'variation-outside-scope','field':name,'actual':value})
        supplied={}
        for item in assessments or []:
            c.exact(item,{'criterion','request_sha256','conclusion','reason'},'scope criterion assessment')
            c.text(item['reason'],'criterion reason')
            if item['criterion'] in supplied:raise ValueError('scope criterion assessment repeats')
            if item['criterion'] not in case['review_criteria']:raise ValueError('assessment names an undeclared criterion')
            if item['request_sha256']!=rendered['request_sha256']:raise ValueError('criterion assessment covers another request')
            if item['conclusion'] not in {'satisfied','not-satisfied','unmeasured'}:raise ValueError('unknown assessor conclusion')
            supplied[item['criterion']]=item
        needs=[key for key in case['review_criteria'] if supplied.get(key,{}).get('conclusion')!='satisfied']
    state='principal-decision-required' if reasons else 'actor-assessment-required' if needs else 'delegated-ready'
    return {'state':state,'case':case_id,'request_sha256':rendered['request_sha256'],'scope_blockers':reasons,'assessment_required':needs,
        'limit':'Structural scope matching records the supplied authority; it does not authenticate a principal or judge creative meaning.'}


def verify_sources(scope:dict|None,approval:dict|None,reader)->None:
    if scope is not None:
        reader.basis(scope['plan'])
        for case in scope['cases']:
            for rule in case['variations'].values():
                if rule['kind']=='authored-content':reader.basis(rule['source'])
    if approval is not None:reader.basis(approval['evidence'])
