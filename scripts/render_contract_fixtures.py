"""Synthetic rendering fixtures for contract tests, never provider evidence."""
from __future__ import annotations
import copy
from render_contract_lib import make_intent


def control(status='optional', *, schema=None, recommendation=None, binding='package', reason='Synthetic interface choice.'):
    return {'status':status, 'binding':binding,
            'schema':schema if status in {'required','optional'} else None,
            'recommendation':recommendation, 'reason':reason}


def intent(prompt: str, mode: str = 'text-to-image') -> dict:
    return make_intent('flat-graphic',mode=mode,chosen_by='agent',reason='Synthetic fixture choice.',
                       presentation='single illustration',prompt_expression=prompt)


def profile(*, seed: bool = False, required: dict | None = None) -> dict:
    """A permissive synthetic interface; real profiles use observed limits."""
    integer={'type':'integer','minimum':1}
    string={'type':'string','minLength':1}
    number={'type':'number','minimum':0}
    controls={k:control(schema=s) for k,s in {
        'width':integer,'height':integer,'size':string,'quality':string,'steps':integer,
        'CFGScale':number,'cfg':number,'guidance':number,'scheduler':string,'sampler':string,
        'promptWeighting':string,'settings':{'type':'object'},'hiresFix':{'type':'object'},
        'clipSkip':integer,'outputFormat':string,'outputType':string,
    }.items()}
    controls['seed']=control('required' if seed else 'backend-managed',schema={'type':'integer','minimum':0,'maximum':4294967295},binding='dispatch-seed')
    controls['numberResults']=control('required',schema={'type':'integer','minimum':1,'maximum':20},binding='dispatch-count')
    controls['strength']=control('not-applicable',reason='This text-only synthetic operation has no denoising input.')
    if required:
        controls.update(required)
    p={'id':'synthetic-render-interface','basis':{'kind':'synthetic','source':'Synthetic interface declaration','limitations':['No provider capability or image quality is claimed.']},
       'prompt_recipe':{'order':['rendering','subject','composition','environment'],
                        'guidance':['Author a coherent rendering phrase after retrieval. Keep content and finish decisions separate.']},
       'modes':{}}
    for mode,media in [('text-to-image','none'),('image-to-image','seed-image'),('reference-guided','references'),('instruction-edit','references')]:
        rules=copy.deepcopy(controls)
        if mode=='image-to-image':
            rules['strength']=control('optional',schema={'type':'number','minimum':0,'maximum':1},reason='Synthetic source-image transformation control.')
        p['modes'][mode]={'media':media,'controls':rules,'parameter_schema':{}}
    return p


def decorate(record: dict, *, seed: bool = False) -> dict:
    """Explicitly equip a synthetic model fixture with the current contract."""
    value=copy.deepcopy(record)
    value['execution_profile']=profile(seed=seed)
    for offering in value.get('offerings',[]):
        required={}
        for name,key in offering.get('parameter_keys',{}).items():
            item=value.get('recommended_parameters',{}).get(name)
            if not isinstance(item,list) and item is not None:
                typ='string' if isinstance(item,str) else 'number'
                required[key]=control('required',schema={'type':typ},recommendation=name)
        offering['execution_profile']=profile(seed=seed,required=required)
    return value
