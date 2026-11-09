"""Acquire the semantic inputs shared by package building and task compilation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from owned_json import freeze


@dataclass(frozen=True,init=False)
class GenerationInputs:
    """Values produced by successful domain checks, with no partial constructor."""

    values: dict
    target: Any
    profile: dict
    effective_parameters: dict
    parameter_decisions: list
    text: dict
    references: dict
    validation: Any
    policy: dict|None

    def __init__(self):
        raise TypeError('acquire generation inputs through their domain checks')

    @classmethod
    def acquire(cls,values:dict,*,resolve_target,prepare_references,preflight_references=None,
                evidence,check=None,validation_factory=None):
        """Run the same checks under an aggregate reporter or a standalone call.

        The reporter invokes each action and records its diagnostics. Only
        actions that actually return supply values to the result. A blocked or
        failed action leaves no completed GenerationInputs to consume.
        """
        import build_generation_payload as builder
        import render_contract_lib as render
        from production_spec import require as require_spec
        from prompt_plot import validate_prompt_plot
        from revision_contract import require_intent_revision
        from prompt_weighting import selected as selected_weighting
        from prompt_retrieval import require_generation_retrieval
        from model_prompt_input import resolve_prompt_input

        values=dict(values)
        specification=values.get('production_spec')
        selected_intent=values.get('render_intent')
        if isinstance(specification,dict) and selected_intent is None:
            values['render_intent']=specification.get('render_intent')
        authored=freeze(values)
        facts={}

        def perform(name,action):
            def acquire():
                result=action()
                facts[name]=result
                return result
            return check(name,acquire) if check is not None else acquire()

        def specification():
            value=authored.get('production_spec')
            if value is not None:
                require_spec(value)
                if selected_intent is not None and selected_intent!=value['render_intent']:
                    raise ValueError('selected render intent differs from its production specification')
            elif any(authored.get(key) is not None for key in ('state_snapshot','state_graphs','state_lineage')):
                raise ValueError('selected state artifacts require their production specification')
            return value
        perform('specification',specification)

        def plot():
            value=authored.get('plot')
            if value is None:return None
            report=validate_prompt_plot(value)
            errors=report.get('errors',[])+report.get('approval_errors',[])
            if errors or not report['approved']:
                raise ValueError('; '.join(errors) or 'plot approval is required')
            return value
        perform('plot',plot)

        def creative():
            value=authored.get('creative_intent')
            if value is None:return None
            if not isinstance(value,dict):raise ValueError('creative intent must be an object')
            require_intent_revision(value)
            return value
        perform('creative-intent',creative)
        perform('target-contract',resolve_target)
        if authored.get('prepared_reference_set') is not None:
            if preflight_references is not None:
                perform('dependency-preflight',preflight_references)
            perform('reference-preparation',prepare_references)
        else:
            facts['reference-preparation']=builder.empty_stateless_reference_set()

        def intent():
            value=authored.get('render_intent')
            render.validate_intent(value,prompt=authored['prompt'])
            return value
        perform('render-intent',intent)
        perform('execution-profile',lambda:freeze(render.selected_profile(
            facts['target-contract'].model,facts['target-contract'].offering)))

        def controls():
            target=facts['target-contract'];profile=facts['execution-profile']
            return freeze(render._parameters_from_profile(target.model,profile,
                authored['render_intent']['execution_mode'],authored['parameters']))
        perform('execution-controls',controls)
        if 'count' in authored:
            def quantity():
                contract={'model_card':{'execution_profile':facts['execution-profile']},
                          'intent':facts['render-intent']}
                return render.dispatch_values(contract,seed=authored['seed'],count=authored['count'])
            perform('execution-quantity',quantity)
        if authored.get('request_validation') is not None or validation_factory is not None:
            def validation():
                from input_contracts import acquire_validation
                record=authored.get('request_validation')
                if record is None:return validation_factory(facts['target-contract'])
                return acquire_validation(record,evidence)
            perform('request-validation-evidence',validation)
        if authored.get('negative_provenance') is not None:
            perform('negative-provenance',lambda:freeze(builder.normalize_negative_provenance(authored['negative_provenance'])))
        else:
            facts['negative-provenance']=freeze(builder.normalize_negative_provenance(None))

        def channels():
            target=facts['target-contract'];profile=facts['execution-profile']
            mode=facts['render-intent']['execution_mode']
            return freeze(builder.prepare_text_transports(model_id=target.model_id,model_record=target.model,
                prompt=authored['prompt'],negative_prompt=authored['negative_prompt'],
                integrated_prompt=authored['integrated_prompt'],native_negative=authored['native_negative'],
                negative_transport=authored['negative_transport'],
                critical_avoidance_integrated=authored['critical_avoidance_integrated'],
                weighting_syntax=selected_weighting(facts['execution-controls'][0],profile['modes'][mode]['prompt_syntax'])))
        perform('negative-transport',channels)

        def retrieval():
            target=facts['target-contract']
            tag_input=resolve_prompt_input(target.model)['mode']=='tag-based'
            syntax=selected_weighting(facts['execution-controls'][0],
                facts['execution-profile']['modes'][facts['render-intent']['execution_mode']]['prompt_syntax']) if tag_input else 'literal'
            return require_generation_retrieval(authored.get('retrieval_record'),prompt=authored['prompt'],plot=authored.get('plot'),
                model_record=target.model,negative=authored['negative_prompt'] if tag_input else '',syntax=syntax)
        perform('retrieval',retrieval)
        required={'specification','plot','creative-intent','target-contract','reference-preparation','render-intent',
                  'execution-profile','execution-controls','negative-provenance','negative-transport','retrieval'}
        if authored.get('prepared_reference_set') is not None and preflight_references is not None:
            required.add('dependency-preflight')
        if authored.get('request_validation') is not None or validation_factory is not None:required.add('request-validation-evidence')
        if 'count' in authored:required.add('execution-quantity')
        if not required<=facts.keys():return None
        result=object.__new__(cls)
        actual={**authored,'negative_provenance':facts['negative-provenance']}
        if 'request-validation-evidence' in facts:
            actual['request_validation']=facts['request-validation-evidence'][0].record
        fields={'values':freeze(actual),'target':facts['target-contract'],'profile':facts['execution-profile'],
                'effective_parameters':facts['execution-controls'][0],'parameter_decisions':facts['execution-controls'][1],
                'text':facts['negative-transport'],'references':freeze(facts['reference-preparation']),
                'validation':facts.get('request-validation-evidence',(None,None))[0],
                'policy':facts.get('request-validation-evidence',(None,None))[1]}
        for name,value in fields.items():object.__setattr__(result,name,value)
        return result
