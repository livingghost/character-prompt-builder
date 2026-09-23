"""Draft an explicit request variation from a recorded candidate without execution."""
from __future__ import annotations
import copy
from pathlib import Path
import execution_contract as c
from input_evidence import InputEvidence
import production_inputs
import production_variation_adapter as adapter
import request_contract as rc


def apply_changes(rendered: dict, changes: dict, root: Path, reader: InputEvidence) -> tuple[dict,list[dict]]:
    """Change only fields that the original compiler declares as mutable inputs."""
    rc.validate_seal(rendered)
    if not isinstance(changes,dict) or not changes:raise ValueError('provide a nonempty explicit field change map')
    request=copy.deepcopy(rendered['request']);media=copy.deepcopy(rendered['media']);diff=[]
    for name,value in changes.items():
        if name not in rendered['fields']:raise ValueError('change names no declared request field: '+str(name))
        field=rendered['fields'][name];kind=field['kind'];path=field['field']
        if kind not in {'parameter','content','media'} or path is None:
            raise ValueError('start a separately declared production to change a fixed field: '+name)
        if kind=='media':
            c.exact(value,{'path'},'media change selector')
            ref=reader.select(value['path'])
            entries=[item for item in rendered['layout']['media'] if item['field']==path]
            if len(entries)!=1:raise ValueError('media field has no unique declared input index')
            index=entries[0]['index'];old=media[index]
            media[index]=rc.media_metadata(c.local(root,ref['path']),role=old['role'],binding_ids=old['binding_ids'])
            rc.put(request,path,rc.MANAGEMENT_VALUE)
            after={'path':ref['path'],'sha256':ref['sha256']}
        else:
            if kind=='content':c.text(value,'authored content change')
            c.encoded(value)
            rc.put(request,path,copy.deepcopy(value));after=copy.deepcopy(value)
        diff.append({'field':name,'kind':kind,'before':field['value'],'after':after})
    result=rc.seal(request,rendered['layout'],media,rendered['sealed']['target'],rendered['sealed']['execution'],[],
        rendered['sealed']['bindings'],rendered['sealed']['context'])
    if result['request_sha256']==rendered['request_sha256']:raise ValueError('variation does not change this request')
    return result,diff


def draft(root: Path, run: str, changes_path: str, out_dir: str, *, runtime_arguments: dict | None = None) -> dict:
    """Keep immutable evidence and existing authority; publish only a new input draft."""
    import production_workflow as workflow
    from production_resume import report
    root=root.resolve(strict=True);reader=InputEvidence(root)
    selected=reader.select(changes_path);requested=reader.json(selected)
    c.exact(requested,{'candidate','changes','reason'},'variation choices')
    c.sha(requested['candidate']);c.text(requested['reason'],'variation reason')
    directory,prepared,consumer,rows=workflow.load_run(root,run)
    candidate=workflow.find(rows,'candidate',requested['candidate'])
    for item in candidate['data']['files']:
        if reader.read({'path':item['path'],'sha256':item['sha256']})!=c.object_read(directory,item['sha256']):
            raise ValueError('selected candidate differs from its recorded bytes')
    claims=[row for row in rows if row['event']=='dispatch-claim']
    if len(claims)!=1:raise ValueError('candidate variation needs one recorded model request')
    rendered,source=adapter.source(root,directory,prepared,rows,claims[0],reader)
    proposed,difference=apply_changes(rendered,requested['changes'],root,reader)
    current=report(root,run)
    if not current['integrity']['ok']:raise ValueError('source run integrity changed during input inspection')
    files,choices,task,actions,unresolved=adapter.inputs(root,out_dir,prepared,source,rendered,proposed,difference,reader)
    choices['source_run']=run
    reading=source.get('route_reading',prepared['route_reading'])
    choices['reading']={'snapshot_id':None,'reading_key':reading['reading_key'],'applied':copy.deepcopy(reading['applied'])}
    if 'resource_applied' in reading:choices['reading']['resource_applied']=copy.deepcopy(reading['resource_applied'])
    if reading['route']!=task['route']:
        unresolved.append({'field':'reading','code':'select-stage-reading'})
    if not current['freshness']['reading']['current']:
        unresolved.append({'field':'reading','code':'current-reading-required'})
    changed_profile=proposed['profile']!=rendered['profile']
    if source['request_validation']['mode']=='observed-profile' and changed_profile:
        unresolved.append({'field':'validation.mode','code':'new-probe-or-target-schema-required'})
        choices['validation']['mode']=None
        choices['validation']['contract']=None
    if source['request_validation']['mode']=='bounded-probe':
        unresolved.append({'field':'validation.contract','code':'new-exact-probe-plan-required'})
        choices['validation']['contract']=None
    unresolved.extend(production_inputs._missing(choices))
    actions.append({'operation':'consult-presets','script':'scripts/production_workflow.py',
        'args':{'root':str(root),'task':out_dir+'/production-task.json',**(runtime_arguments or {})},'required_args':['query','out-dir'],
        'external_effect':False,'budget_effect':'none'})
    info={'source_run':run,'candidate':requested['candidate'],'source_input_sha256':prepared['input_sha256'],
        'source_request_sha256':rendered['request_sha256'],'changes':selected,'difference':difference,
        'profile_changed':changed_profile,'freshness':current['freshness'],
        'reuses':['recorded candidate','unchanged source selectors','same production identity','existing delegation subject to its scope'],
        'assessment_required':['Reconsider copied quotations for this variation.','Review the newly assembled request.','Assess stop conditions before fresh authorization.'],
        'unresolved':unresolved,'execution_ready':False,'external_effect':False,'budget_effect':'none',
        'next_actions':[{'operation':'build-inputs','script':'scripts/production_workflow.py',
            'args':{'root':str(root),'task':out_dir+'/production-task.json','choices':out_dir+'/choices.json','from-run':run,**(runtime_arguments or {})},
            'required_args':['out-dir'],'external_effect':False,'budget_effect':'none'},*actions]}
    draft={'state':'draft','choices':choices,'unresolved':unresolved,'derived_from':{'source_run':run,'changes':selected},
        'external_effect':False,'budget_effect':'none'}
    files.update({'choices.json':c.encoded(draft),'production-task.json':c.encoded(task),
        'variation-report.json':c.encoded(info),'requested-changes.json':c.encoded(requested)})
    production_inputs._validate_draft(draft)
    production_inputs._publish(root,out_dir,files,reader=reader)
    return {'state':'draft','report':{'path':out_dir+'/variation-report.json','sha256':c.content_id(info)},
            'choices':out_dir+'/choices.json',**info}


def add_arguments(subparsers) -> None:
    parser=subparsers.add_parser('draft-variation',help='Draft explicit changes from a recorded candidate; never sends or adopts.')
    parser.add_argument('--root',type=Path,required=True);parser.add_argument('--run',required=True)
    parser.add_argument('--changes',required=True,help='Project-relative candidate, explicit field map and reason JSON.')
    parser.add_argument('--out-dir',required=True,help='New project-relative draft directory.')
    production_inputs.adapters.add_runtime_arguments(parser)


def command(args, parser):
    runtime=production_inputs.adapters.configure_runtime(args,parser)
    return draft(args.root,args.run,args.changes,args.out_dir,runtime_arguments=runtime)
