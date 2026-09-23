"""Resolve recorded package inputs for a studio candidate variation."""
from __future__ import annotations
import copy
from pathlib import Path
import tempfile
import execution_contract as c
import production_inputs
import request_contract as rc


def source(root,directory,prepared,rows,claim,reader):
    import production_workflow as w
    results=w.find(rows,'dispatch-results')
    if results['data']['claim']!=claim['sha256']:raise ValueError('candidate results belong to another claim')
    path=claim['data']['journal']+'/package.json'
    refs=[item for item in results['data']['evidence'] if item['path']==path]
    if len(refs)!=1:raise ValueError('recorded variation needs the original package witness')
    package=c.decode(reader.read({'path':path,'sha256':refs[0]['sha256']}))
    if c.content_id(package)!=claim['data']['package_sha256']:raise ValueError('package witness differs from the claimed input')
    if package.get('artifact_type')=='upscale-request':
        from input_contracts import verify_fields
        verify_fields(package,root=None,live=False)
    else:
        from verify_generation_payload import verify_content
        verify_content(package,package_root=(root/path).parent)
    return claim['data']['intent']['payload']['request_contract'],{**package,'_journal':claim['data']['journal'],'_offering_sha256':claim['data']['intent']['payload']['offering_sha256']}


def inputs(root,out,prepared,package,rendered,proposed,difference,reader):
    files={};task=copy.deepcopy(prepared['task']);choices=production_inputs.draft_choices(task);issues=[];actions=[]
    def put(name,value):files[name]=c.encoded(value);return out+'/'+name
    validation=package['request_validation']
    choices['validation']={'mode':validation['mode'],'model':package['model'],'target':validation['target'],
        'service_profiles':None,'contract':validation['contract']['path'],'evidence':validation['evidence']['path'],
        'execution_policy':validation['execution_policy']['path'] if validation['execution_policy'] else None}
    delivery=task['delivery']['path']
    old_prompt=package.get('composition_prompt',package.get('guidance_prompt') or '')
    prompt=old_prompt;dispatch_args={}
    if rendered['layout']['seed'] is not None:dispatch_args['seed']=rc.get(proposed['request'],rendered['layout']['seed'])
    dispatch_args['count']=proposed['output_count']
    if package.get('artifact_type')=='upscale-request':
        choices['visual']=None
        settings=copy.deepcopy(package['settings']);scale=package['scale_factor'];upscale_source=package['source']['path']
        for change in difference:
            name=change['field']
            if name=='scale':scale=change['after']
            elif change['kind']=='parameter':
                import dispatch
                _, model = dispatch.resolve_model_record(package['model'])
                offering = dispatch.select_offering(model,validation['target']['service'])
                if offering is None or c.content_id(offering)!=package['_offering_sha256']:
                    raise ValueError('the selected setting map differs from the recorded offering')
                destination = rendered['fields'][name]['field']
                matches = [key for key,value in (offering.get('setting_keys') or {}).items()
                           if rc.path_parts(value)==destination]
                if len(matches)!=1:raise ValueError('changed upscale parameter has no unique declared model setting')
                settings[matches[0]]=change['after']
            elif change['kind']=='content':prompt=change['after']
            elif change['kind']=='media':
                upscale_source=change['after']['path']
                for item in task['sources']:
                    if item['path']==package['source']['path']:item['path']=upscale_source
        files['upscale-guidance.txt']=prompt.encode('utf-8');put('upscale-settings.json',settings)
        actions.append({'operation':'build-upscale-request','script':'scripts/production_binding.py',
            'args':{'root':str(root),'model':package['model'],'source':upscale_source,
                    'scale':scale,'settings':settings,**({'guidance':prompt} if prompt else {})},
            'requires':['new request-validation file','out: write the new declaration to the draft task delivery path before prepare'],
            'external_effect':False,'budget_effect':'none'})
    else:
        visual=package['visual_continuity'];spec_path=put('production-spec.json',package['production_spec'])
        from build_generation_payload import materialize_cli_reference_bundle
        with tempfile.TemporaryDirectory(prefix='variation-media-') as tmp:
            stage=Path(tmp)
            refs,_=materialize_cli_reference_bundle(package['prepared_reference_set'],model=package['model'],
                source_root=root/package['_journal'],staging_root=stage,companion_name='references')
            for path in stage.rglob('*'):
                if path.is_file():files[path.relative_to(stage).as_posix()]=c.read(path)
        refs_path=put('prepared-reference-set.json',refs)
        subjects={ident:{'continuity':item['continuity'],'character_id':item['character_id'],
            'studio_character':item['studio_character'],'identity_refs':[{'slot':ref['slot'],'iteration_id':ref['iteration_id']}
                for ref in item['identity_refs']]} for ident,item in visual['subjects'].items()}
        choices['visual']={'purpose':visual['purpose'],'basis':{k:visual['basis'][k] for k in ('path','locator')},
            'subjects':subjects,'production_spec':spec_path,'prepared_reference_set':refs_path}
        payload=package['generation_payload'];parameters=copy.deepcopy(payload['parameters'])
        negative=payload['negative_prompt'];native=payload['native_negative'];integrated=payload['transports'].get('integrated',{}).get('text')
        for change in difference:
            name=change['field'];entry=rendered['fields'][name]
            if change['kind']=='parameter':
                if name in {'seed','count'}:continue
                parameters['.'.join(entry['field'])]=change['after']
            elif change['kind']=='content':
                if entry['field']==rendered['layout']['primary_text']:
                    if payload['negative_transport']['mode'] in {'integrated-critical','retained-only'}:integrated=change['after']
                    else:prompt=change['after']
                    issues.append({'field':'retrieval','code':'settle-retrieval-for-new-rendition'})
                elif entry['field']==rendered['layout']['negative_text']:
                    if payload['negative_transport']['mode']=='native-subset':native=change['after']
                    else:negative=change['after']
                    issues.append({'field':'negative-provenance','code':'assess-negative-translation'})
            else:issues.append({'field':'visual.prepared_reference_set','code':'prepare-selected-media-and-rebind-identities'})
        # Dispatch count and seed override only the package parameters on the fields the layout declares for them.
        for slot,name in (('seed','seed'),('output_count','count')):
            key='.'.join(str(part) for part in rendered['layout'][slot] or [])
            if key in parameters and name in dispatch_args:parameters[key]=dispatch_args[name]
        files['prompt.txt']=prompt.encode('utf-8');files['negative.txt']=(negative or '').encode('utf-8')
        files['native-negative.txt']=(native or '').encode('utf-8')
        put('parameters.json',parameters);plot=put('plot.json',package['plot']);retrieval=put('retrieval.json',package['retrieval_record'])
        intent=put('creative-intent.json',package['creative_intent']);provenance=put('negative-provenance.json',payload['negative_provenance'])
        args={'model':package['model'],'prompt-file':str(root/out/'prompt.txt'),'negative-file':str(root/out/'negative.txt'),
            'production-spec-file':str(root/spec_path),'plot-file':str(root/plot),'retrieval-record-file':str(root/retrieval),
            'intent-file':str(root/intent),'references-file':str(root/refs_path),'parameters':parameters,
            'production-root':str(root),'negative-provenance-file':str(root/provenance),
            'negative-transport':payload['negative_transport']['mode']}
        if native:args['native-negative-file']=str(root/out/'native-negative.txt')
        if integrated:
            files['integrated-prompt.txt']=integrated.encode('utf-8');args['integrated-prompt-file']=str(root/out/'integrated-prompt.txt')
            if prompt!=old_prompt:issues.append({'field':'integrated-prompt','code':'review-related-rendition'})
        if package['state_lineage'].get('mode')=='state-aware':
            issues.append({'field':'state-series','code':'use-recorded-state-artifact-graph'})
            script='scripts/build_state_generation_package.py'
        else:script='scripts/build_generation_payload.py'
        actions.append({'operation':'build-generation-payload','script':script,'args':args,
            'requires':['formal inputs from build-inputs','new production run','out','current rendition and retrieval assessment'],
            'external_effect':False,'budget_effect':'none'})
    if package.get('artifact_type')=='upscale-request':
        files['delivery.txt']=c.encoded({key:value for key,value in package.items() if key not in {'_journal','_offering_sha256'}})
        issues.append({'field':'task.delivery','code':'build-new-upscale-declaration-from-selected-changes'})
    else:
        files['delivery.txt']=prompt.encode('utf-8')
    task['delivery']['path']=out+'/delivery.txt'
    for item in task['sources']:
        if item['path']==delivery:item['path']=out+'/delivery.txt'
    actions.append({'operation':'dispatch-preview','script':'scripts/dispatch.py','args':dispatch_args,
        'requires':['new package or upscale request','recording character and slot','new production run'],
        'external_effect':False,'budget_effect':'none'})
    return files,choices,task,actions,issues
