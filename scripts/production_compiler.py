"""One compiler for task checking, complete preparation and package construction.

A check returns diagnostics and an ephemeral preview. Preparation publishes the
same compiled contents only when all required input checks passed. Permission,
and credentials are execution readiness, not malformed input.
"""
from __future__ import annotations
import copy
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any

import execution_contract as c
import production_store as store
from production_diagnostics import CompilationError, Diagnostic, ProductionError, from_exception
from operation_context import current, stage
from pack_manager import generate_uuid7

ROOT=Path(__file__).resolve().parents[1]
GENERATION_FILES=('parameters','production_spec','plot','retrieval_record','creative_intent','negative',
                  'integrated_prompt','native_negative','negative_provenance','references','state_lineage',
                  'state_snapshot','visual_continuity','request_validation')
JSON_FILES=set(GENERATION_FILES)-{'negative','integrated_prompt','native_negative'}
# A derived run's own inputs live in its run directory and are never live studio sources.
RUN_INPUT=re.compile(r'^production/runs/[^/]+/inputs/')
UNREADABLE_ACTION='Name an existing regular file by its path relative to the studio root, with / separators.'
REPORT_SCHEMA='schemas/authoring/production-compilation-report.schema.json'
PLAN_SCHEMA='schemas/authoring/production-execution-plan.schema.json'


def run_inputs(run: str) -> str:
    """The studio-relative directory that holds a derived run's own inputs."""
    return f'production/runs/{run}/inputs'


def dependency_space(path: str) -> str:
    """Inputs a run owns inside its own directory are task sources; every other file is a live studio source."""
    return 'task-source' if RUN_INPUT.match(path) else 'studio'


def read_input(root: Path, path: str, *, pointer: str | None, phase: str = 'source-read') -> bytes:
    """Read one declared input once; a failure names the file, the task pointer and the cause."""
    try:
        return store.stable_bytes(root, path)
    except ProductionError as exc:
        if exc.diagnostic.code != 'EVIDENCE_CAPTURE_FAILED':
            if exc.diagnostic.pointer is None:
                exc.diagnostic.pointer = pointer
            raise
        cause = exc.__cause__ or exc
        raise ProductionError('INPUT_UNREADABLE', 'The declared input could not be read.', phase=phase, file=path,
                              pointer=pointer, cause=str(cause), required_action=UNREADABLE_ACTION) from cause


def validate_document(value: Any, schema_path: str, label: str) -> None:
    """Check a produced document against its published schema."""
    from state_protocol import validate_against_schema
    errors = validate_against_schema(value, c.load(ROOT / schema_path))
    if errors:
        raise ValueError(label + ': ' + '; '.join(errors))


@dataclass
class Compilation:
    report: dict
    directory: Path | None = None
    prepared: dict | None = None
    consumer: dict | None = None
    package: dict | None = None
    rendered: dict | None = None
    execution_plan: dict | None = None
    identity: str | None = None


def input_digest(prepared: dict, consumer: dict) -> str:
    """Hash creative content, not grant files, log tails, envelope IDs or dates."""
    task=copy.deepcopy(prepared['task'])
    task.pop('authority',None)
    task.pop('execution_decisions',None)
    # The task file's content is the task itself. Every other task source is a
    # derived input that the run owns, and its content is part of the input.
    dependencies=[x for x in prepared['dependencies'] if x['space']!='evidence'
                  and not (x['space']=='task-source' and x['path']==prepared['task_path'])]
    value = {'task':task,'consumer':consumer,'dependencies':dependencies,
             'runtime':(prepared.get('runtime_snapshot') or {}).get('sha256')}
    if prepared.get('studio_reference_sources'):
        value['studio_reference_sources'] = prepared['studio_reference_sources']
    return c.content_id(value)


def _file_inputs(task: dict) -> list[tuple[str,str]]:
    items=[]
    delivery=task.get('delivery')
    if isinstance(delivery,dict) and isinstance(delivery.get('path'),str):items.append(('$.delivery.path',delivery['path']))
    if isinstance(task.get('route_reading'),str):items.append(('$.route_reading',task['route_reading']))
    for index,source in enumerate(task.get('sources',[]) if isinstance(task.get('sources'),list) else []):
        if isinstance(source,dict) and isinstance(source.get('path'),str):items.append((f'$.sources[{index}].path',source['path']))
    generation=task.get('generation')
    if isinstance(generation,dict):
        for name in GENERATION_FILES:
            if isinstance(generation.get(name),str):items.append(('$.generation.'+name,generation[name]))
    return items


NO_TASK_CHECKS=['task-schema','task-contract','sources','runtime-resolution','source-validation','package-compilation',
                'request-compilation','recording-validation','execution-plan','publication']


def inspect_task(root: Path, task_path: str) -> tuple[dict | None,list[dict],dict[str,bytes]]:
    """Read the task and every file it declares once, keeping each failure with its pointer and cause."""
    diagnostics=[]; captured={}
    def no_task(diagnostic: dict):
        diagnostics.append(diagnostic)
        diagnostics.append(Diagnostic('CHECK_NOT_PERFORMED','No task object is available for dependent checks.',phase='task-read',
                                      file=task_path,blocked_checks=NO_TASK_CHECKS).as_dict())
        return None,diagnostics,captured
    try:
        raw=read_input(root,task_path,pointer=None,phase='task-read')
    except ProductionError as exc:
        return no_task(exc.diagnostic.as_dict())
    captured[task_path]=raw
    try:
        task=c.decode(raw)
    except ValueError as exc:
        return no_task(Diagnostic('INPUT_SCHEMA_INVALID','The task is not UTF-8 JSON.',phase='task-read',file=task_path,pointer='$',
                                  details={'cause':str(exc)}).as_dict())
    from state_protocol import validate_against_schema
    errors=validate_against_schema(task,c.load(ROOT/'schemas/authoring/production-task.schema.json'))
    for message in errors:
        pointer=message.split(':',1)[0] if message.startswith('$') else '$'
        diagnostics.append(Diagnostic('INPUT_SCHEMA_INVALID',message,phase='task-schema',file=task_path,pointer=pointer).as_dict())
    if not isinstance(task,dict):
        return no_task(Diagnostic('INPUT_SCHEMA_INVALID','The task must be a JSON object.',phase='task-schema',file=task_path,pointer='$').as_dict())
    for pointer,path in _file_inputs(task):
        if path in captured:continue
        try:
            captured[path]=read_input(root,path,pointer=pointer)
        except ProductionError as exc:
            diagnostics.append(exc.diagnostic.as_dict())
    return task,diagnostics,captured


def _status_code(status: Any) -> str | None:
    """The diagnostic code a control problem's status names, if it names one."""
    from render_contract_lib import PROBLEM_CODES
    return PROBLEM_CODES.get(status)


class InputChecks:
    """Track individual validator results and their actual prerequisites."""
    def __init__(self, diagnostics: list[dict]):
        self.diagnostics = diagnostics
        self.states: dict[str, str] = {}
        self.values: dict[str, Any] = {}
        self.rows: list[dict] = []

    def record(self, name: str, state: str, requires=()) -> None:
        """Record the state of a check performed elsewhere in the compilation."""
        self.states[name] = state
        self.rows.append({'phase': name, 'state': state, 'requires': list(requires)})

    def check(self, name: str, action, *, requires=(), file=None, pointer=None, code=None):
        """Run one check unless a prerequisite failed; `code` names a failure that has no code of its own."""
        blocked = [key for key in requires if self.states.get(key) != 'passed']
        if blocked:
            self.record(name, 'not-performed', requires)
            self.diagnostics.append(Diagnostic('CHECK_NOT_PERFORMED',
                'Required inputs or checks are unavailable: ' + ', '.join(blocked),
                phase=name, file=file, pointer=pointer, blocked_checks=[name],
                details={'blocked_by': blocked}).as_dict())
            return None
        try:
            with stage(name):
                value = action()
        except (ValueError, OSError, KeyError, TypeError, IndexError, ImportError) as exc:
            self.record(name, 'failed', requires)
            if isinstance(exc, ImportError):
                diagnostic = Diagnostic('DEPENDENCY_UNAVAILABLE', 'A Python dependency this check needs is not installed.',
                    phase=name, file=file, pointer=pointer, details={'cause': str(exc)},
                    required_action='Install the declared dependency profile with python scripts/check_dependencies.py, then check again.').as_dict()
            else:
                selected = _status_code(getattr(exc, 'status', None)) or code
                diagnostic = from_exception(exc, phase=name, file=file, pointer=pointer,
                                            **({'code': selected} if selected and not isinstance(exc, ProductionError) else {}))
            if diagnostic.get('file') is None: diagnostic['file'] = file
            if diagnostic.get('pointer') is None: diagnostic['pointer'] = pointer
            from render_contract_lib import ParameterErrors
            if isinstance(exc, ParameterErrors):
                for item in exc.problems:
                    problem = {**diagnostic, 'message': item['message'], 'pointer': '$.' + item['parameter']}
                    problem['code'] = _status_code(item.get('status')) or diagnostic['code']
                    self.diagnostics.append(problem)
            else:
                self.diagnostics.append(diagnostic)
            return None
        self.states[name] = 'passed'
        self.values[name] = value
        self.rows.append({'phase': name, 'state': 'passed', 'requires': list(requires)})
        return value


def inspect_dependencies(root: Path, task: dict, task_path: str, captured: dict[str, bytes],
                         checks: InputChecks, *, runtime_ready: bool, directory: Path) -> None:
    """Use existing domain validators before package assembly, without short-circuiting peers.

    A task schema error blocks only the checks that need the whole task. Every
    check of a document the task names still runs on the captured bytes.
    """
    import production_workflow as workflow
    whole = ['task-schema']
    def present(value: Any) -> bool:
        return isinstance(value, str) and bool(value)
    def gate(*values: Any) -> list[str]:
        """Require a valid task schema where a value the check reads is absent or malformed."""
        return [] if all(present(value) for value in values) else whole
    def cached(path: str, pointer: str | None = None) -> bytes:
        if path not in captured:
            captured[path] = read_input(root, path, pointer=pointer)
        return captured[path]
    checks.check('task-contract', lambda: workflow.validate_task(task), requires=whole, file=task_path)
    selected = task.get('generation') if isinstance(task.get('generation'), dict) else None
    upscale = task.get('upscale') if isinstance(task.get('upscale'), dict) else None
    files = dict(_file_inputs(task))
    source_keys = {}
    for pointer, path in files.items():
        key = 'input:' + pointer
        source_keys[pointer] = key
        def decode_input(path=path, pointer=pointer):
            raw = captured[path]
            if pointer.startswith('$.generation.') and pointer.rsplit('.',1)[-1] in JSON_FILES:
                return c.decode(raw)
            return raw
        # A source-read diagnostic already names unavailable bytes. Keep its state
        # without adding a duplicate error for every use of that input.
        if path not in captured:
            checks.record(key, 'failed')
        else:
            checks.check(key, decode_input, file=path, pointer=pointer)
    def dependency(pointer): return source_keys.get(pointer, 'undeclared:' + pointer)
    def doc(field): return checks.values[dependency('$.generation.'+field)]
    delivery_path = files.get('$.delivery.path')
    def text(field):
        path = delivery_path if field == 'prompt' else (selected or {}).get(field)
        return captured[path].decode('utf-8') if path else ''
    dispatcher = task.get('execution') == 'dispatcher'
    checks.states['runtime-resolution'] = 'passed' if runtime_ready else 'failed'
    prompt_key = dependency('$.delivery.path')
    checks.check('delivery-content', lambda: c.text(captured[delivery_path].decode('utf-8'), 'delivery'),
                 requires=[prompt_key], file=delivery_path, pointer='$.delivery.path')
    if dispatcher:
        checks.check('recording-validation', lambda: validate_recording(root, task, {}), requires=whole,
                     file=task_path, pointer='$.recording')
    import route_reading
    checks.check('route-reading', lambda: route_reading.require_route_reading(
        c.decode(captured[task['route_reading']]), studio=root, routes={task['route']}, features=task['features']),
        requires=[dependency('$.route_reading'),'task-contract'] + (['runtime-resolution'] if dispatcher else []),
        file=files.get('$.route_reading'), pointer='$.route_reading')
    # Bounded views and scene material: each is checked against its own scope
    # here, and the bytes read are kept for the immutable capture.
    def bounded(function):
        reads = {}
        def add(base: Path, path: str, space: str = 'studio') -> bytes:
            raw = cached(path) if Path(base) == root else store.stable_bytes(base, path)
            reads[(space, path)] = raw
            return raw
        return function(root, task, add), reads
    for name, pointer, function in (('world-views', '$.world_views', workflow.world_views),
                                    ('moment-views', '$.moment_views', workflow.moment_views),
                                    ('scene-materials', '$.scene_materials', workflow.authoring_materials)):
        checks.check(name, lambda function=function: bounded(function), requires=['task-contract'], file=task_path, pointer=pointer)
    if task.get('authority'):
        def authority():
            value=c.decode(cached(task['authority'], '$.authority'))
            workflow.schema_check(value,'authority');workflow.permissions.validate(value,task['task_id'])
            cached(value['evidence']['path'])
            from input_evidence import InputEvidence
            import request_scope
            reader=InputEvidence(root)
            for grant in value['grants']: request_scope.verify_sources(grant['request_scope'],None,reader)
            return value
        # A committed authority is the current one; the task's file is read only before the first import.
        if checks.states.get('task-schema') != 'passed' or store.authority_record(root, task['task_id']) is None:
            checks.check('authority-evidence',authority,requires=whole,file=task['authority'] if present(task['authority']) else task_path,
                         pointer='$.authority')
    if not dispatcher: return
    import build_generation_payload as builder
    import render_contract_lib as render
    from catalog_retrieval.runtime import load_pack_catalog
    import service_profile, transport_contract
    def target(model_name, service):
        model_id, record = builder.resolve_model_record(model_name)
        offering = builder.select_offering(record, service)
        if offering is None:
            raise ProductionError('MODEL_PROFILE_MISSING','The declared target has no selected offering.',phase='runtime-resolution')
        resource=load_pack_catalog().resources.get('service-profiles')
        if resource is None: raise ProductionError('MODEL_PROFILE_MISSING','No service-profiles resource is selected.',phase='runtime-resolution')
        profile=service_profile.load_service(offering['service'],resource.path)
        return model_id,record,offering,profile,transport_contract.load(profile['transport'])
    if selected is None:
        if task.get('route') != 'upscale' and upscale is None:
            return
        # The upscale source and settings are independent of the output slot.
        import production_binding, dispatch
        request=checks.check('upscale-document',lambda:c.decode(captured[delivery_path]),
                             requires=[prompt_key],file=delivery_path,pointer='$.delivery.path')
        if request is not None:
            checks.check('upscale-source', lambda: production_binding.validate_upscale_input(root, request),
                         requires=['upscale-document'],file=delivery_path)
            resolved=checks.check('target-contract',lambda:target(request['model'],upscale['service']),
                                 requires=['runtime-resolution','upscale-document']+gate((upscale or {}).get('service')),
                                 file=delivery_path,pointer='$.model')
            if resolved is not None:
                checks.check('upscale-model-controls',lambda:require_upscale_target(resolved[0],resolved[1],request),
                             requires=['target-contract'],file=delivery_path)
                def upscale_controls():
                    _,model,offering,_,_=resolved
                    scale=(offering.get('parameter_keys') or {}).get('scale')
                    if not scale:
                        raise ProductionError('MODEL_PROFILE_MISSING','The upscale offering declares no request key for the scale factor.',
                            phase='execution-controls',file=delivery_path,pointer='$.scale_factor',actual=offering.get('service'),
                            required_action='Declare parameter_keys.scale on the selected offering of the upscale model record.')
                    dispatch.require_guidance_key(offering,request['guidance_prompt'])
                    settings=dispatch.mapped_settings(model,offering,request['settings'])
                    contract=render.compile_contract(model,offering,request['render_intent'],{**settings,scale:request['scale_factor']},
                        prompt=request['guidance_prompt'] or '',reference_count=1)
                    render.dispatch_values(contract,seed=None,count=1)
                checks.check('execution-controls',upscale_controls,requires=['target-contract'],file=delivery_path)
        return
    specpath=selected.get('production_spec')
    from production_spec import require as require_spec
    checks.check('specification',lambda:require_spec(doc('production_spec')),
                 requires=[dependency('$.generation.production_spec')],file=specpath)
    from prompt_plot import validate_prompt_plot
    def plot():
        result=validate_prompt_plot(doc('plot'))
        errors=result.get('errors',[])+result.get('approval_errors',[])
        if errors or not result['approved']: raise ValueError('; '.join(errors) or 'plot approval is required')
        return doc('plot')
    checks.check('plot',plot,requires=[dependency('$.generation.plot')],file=selected.get('plot'))
    from prompt_retrieval import require_generation_retrieval
    checks.check('retrieval',lambda:require_generation_retrieval(doc('retrieval_record'),prompt=text('prompt'),plot=doc('plot')),
        requires=[dependency('$.generation.retrieval_record'),'plot','delivery-content'],file=selected.get('retrieval_record'))
    from revision_contract import require_intent_revision
    def creative():
        value=doc('creative_intent')
        if not isinstance(value,dict):raise ValueError('creative intent must be an object')
        return require_intent_revision(value)
    checks.check('creative-intent',creative,requires=[dependency('$.generation.creative_intent')],file=selected.get('creative_intent'))
    resolved=checks.check('target-contract',lambda:target(doc('production_spec')['target_model'],selected['service']),
        requires=['specification','runtime-resolution']+gate(selected.get('service')),file=specpath,pointer='$.target_model')
    if selected.get('references'):
        def preflight():
            # Rasterizing SVG references or composing a board needs the visual dependency profile.
            from reference_runtime import preflight_visual_dependencies, VisualDependencyPreflightError
            prepared=doc('references')
            plan=prepared.get('reference_use_plan') if isinstance(prepared.get('reference_use_plan'),dict) else {}
            try:
                return preflight_visual_dependencies({'transport_mode':prepared.get('transport_mode'),
                    'reference_items':plan.get('reference_items') or prepared.get('selected_references') or []})
            except VisualDependencyPreflightError as exc:
                raise ProductionError('DEPENDENCY_UNAVAILABLE',str(exc),phase='dependency-preflight',file=selected['references'],
                    missing=exc.report.get('missing_packages') or [],incompatible=exc.report.get('incompatible_packages') or [],
                    required_action='Install the visual dependency profile with '+exc.report['check_command']+' --install, then check again.') from exc
        checks.check('dependency-preflight',preflight,requires=[dependency('$.generation.references')],file=selected['references'])
        def references():
            prepared, _ = builder.materialize_cli_reference_bundle(doc('references'),
                model=doc('production_spec')['target_model'], source_root=c.local(root,selected['references']).parent,
                staging_root=directory, companion_name='package.' + c.content_id(doc('references'))[:24] + '.references')
            return prepared
        checks.check('reference-preparation',references,
                     requires=['target-contract','dependency-preflight',dependency('$.generation.references')],file=selected['references'])
    checks.check('render-intent',lambda:render.validate_intent(doc('production_spec')['render_intent'],prompt=text('prompt')),
        requires=['specification','delivery-content'],file=specpath,pointer='$.render_intent')
    if resolved is None:
        checks.check('execution-controls',lambda:None,requires=['target-contract'],file=selected.get('parameters'))
    else:
        _,model,offering,_,_=resolved
        profile=checks.check('execution-profile',lambda:render.selected_profile(model,offering),requires=['target-contract'],
                             file=specpath,pointer='$.target_model',code='MODEL_PROFILE_MISSING')
        def controls():
            mode=doc('production_spec')['render_intent']['execution_mode']
            effective,decisions=render.resolve_parameters(model,profile,mode,doc('parameters'))
            return effective,decisions
        checks.check('execution-controls',controls,requires=['execution-profile','specification',dependency('$.generation.parameters')],
                     file=selected.get('parameters'),pointer='$.generation.parameters')
        def quantity():
            contract={'model_card':{'execution_profile':profile},'intent':doc('production_spec')['render_intent']}
            return render.dispatch_values(contract,seed=selected['seed'],count=selected['count'])
        checks.check('execution-quantity',quantity,requires=['execution-profile','specification']+whole,file=task_path,pointer='$.generation.count')
    if selected.get('request_validation'):
        from request_validation import require
        import runtime_evidence
        checks.check('request-validation-evidence',lambda:require(doc('request_validation'),runtime_evidence.reader(root)),
            requires=[dependency('$.generation.request_validation'),'runtime-resolution'],file=selected['request_validation'])
    if selected.get('negative_provenance'):
        checks.check('negative-provenance',lambda:builder.normalize_negative_provenance(doc('negative_provenance')),
                     requires=[dependency('$.generation.negative_provenance')],file=selected['negative_provenance'])
    def channels():
        positive,negative=text('prompt'),text('negative')
        integrated,native=text('integrated_prompt'),text('native_negative')
        if resolved is not None:
            positive,negative,_=builder.apply_prompt_recommendations(resolved[1],prompt=positive,negative_prompt=negative)
        transports=builder.build_transports(prompt=positive,negative_prompt=negative,integrated_prompt=integrated,
            critical_avoidance_integrated=selected.get('critical_avoidance_integrated',False),native_negative=native)
        if native and not negative:raise ValueError('native_negative requires a portable negative_prompt')
        if negative and not transports['integrated']['available']:
            raise ValueError('negative-bearing payloads require an agent-authored integrated prompt or declared critical avoidance integration')
    requirements=['delivery-content']+[dependency('$.generation.'+f) for f in ['negative','integrated_prompt','native_negative'] if selected.get(f)]
    checks.check('negative-transport',channels,requires=requirements,file=selected.get('negative') or task_path)


def validate_recording(root: Path, task: dict, specification: dict, visual: dict | None = None) -> None:
    import studio
    recording=task['recording']
    try:studio.validate_recording_target(root,recording['character'],recording['slot'])
    except (ValueError,OSError) as exc:
        raise ProductionError('RECORDING_CONTRACT_INVALID',str(exc),phase='recording-validation',pointer='$.recording',
                              required_action='Select an existing Studio character and recording slot before preparing.') from exc
    from visual_continuity import declared_sheet_slots
    if recording['slot'] in declared_sheet_slots(root,recording['character']):
        if not recording['sheet_panel']:
            raise ProductionError('RECORDING_CONTRACT_INVALID','A sheet slot requires a sheet-panel input.',phase='recording-validation',
                                  pointer='$.recording.sheet_panel',required_action='Declare sheet_panel=true for the intended single-subject panel.')
        if len(recording['subject_map'])!=1 or list(recording['subject_map'].values())!=[recording['character']]:
            raise ProductionError('SHEET_SUBJECT_MAPPING_MISSING','A sheet slot needs one declared subject mapped to its Studio character.',
                                  phase='recording-validation',pointer='$.recording.subject_map',required_action='Map the single declared subject to the selected Studio character.')


def _generation(root: Path, task: dict, prepared: dict, consumer: dict, directory: Path, identity: str, blobs: dict, *,
                inspected: InputChecks, captured: dict[str, bytes]) -> tuple[dict,dict,dict]:
    import build_generation_payload as builder
    import request_renderer
    import runtime_evidence
    import service_profile
    import transport_contract
    from verify_generation_payload import verify
    from catalog_retrieval.runtime import load_pack_catalog
    from route_reading import copy_issuance, ledger_candidates
    import production_workflow as workflow
    selected=task['generation']
    def raw(name: str) -> bytes:
        # Every declared document was read once, when the task was inspected.
        return captured[selected[name]] if selected.get(name) is not None else b''
    def document(name: str) -> dict | None:
        return c.decode(raw(name)) if selected.get(name) is not None else None
    specification=document('production_spec')
    model=specification['target_model']
    model_id,model_record=builder.resolve_model_record(model)
    offering=builder.select_offering(model_record,selected['service'])
    if offering is None:
        raise ProductionError('MODEL_PROFILE_MISSING','The declared target has no selected offering.',phase='runtime-resolution')
    resource=load_pack_catalog().resources.get('service-profiles')
    if resource is None:raise ProductionError('MODEL_PROFILE_MISSING','The runtime has no service-profiles resource.',phase='runtime-resolution')
    service=service_profile.load_service(offering['service'],resource.path)
    transport=transport_contract.load(service['transport'])
    references=inspected.values['reference-preparation'] if selected.get('references') is not None else None
    reference_set=references if references is not None else builder.empty_stateless_reference_set()
    if selected.get('visual_continuity'):
        visual=document('visual_continuity')
    else:
        from visual_continuity import from_decisions
        visual=from_decisions(selected['continuity'],production_spec=specification,prepared=reference_set,root=root,
            characters=task['recording']['subject_map'],sheet_panel=task['recording']['sheet_panel'],
            basis={'path':prepared['task_path'],'locator':'$.generation.continuity and $.recording'})
    with stage('recording-validation'):
        validate_recording(root,task,specification)
        from visual_continuity import require
        require(visual,production_spec=specification,prepared=reference_set,root=root,
                recording_character=task['recording']['character'],recording_slot=task['recording']['slot'])
    if selected.get('request_validation'):
        validation=document('request_validation')
    else:
        if references is not None or consumer['transport']!='authored-rendition':
            raise ProductionError('MODEL_PROFILE_MISSING','References or bounded context require an explicitly authored request validation policy.',
                                  phase='request-compilation',pointer='$.generation.request_validation')
        from request_validation import from_offering
        validation=from_offering(model_id,model_record,offering,service,transport,runtime_evidence.reader(root))
    copy_issuance(prepared['route_reading'],directory/'reads.jsonl',ledgers=ledger_candidates(studio=root))
    binding={'run':identity,'input_sha256':prepared['input_sha256'],'consumer':consumer}
    with stage('package-compilation'):
        package=builder.build_payload(model=model,prompt=consumer['instructions'],negative_prompt=raw('negative').decode('utf-8'),
            brief=selected.get('brief',''),creative_intent=document('creative_intent'),parameters=document('parameters'),
            negative_transport=selected.get('negative_transport','auto'),
            critical_avoidance_integrated=selected.get('critical_avoidance_integrated',False),
            integrated_prompt=raw('integrated_prompt').decode('utf-8'),native_negative=raw('native_negative').decode('utf-8'),
            negative_provenance=document('negative_provenance'),production_spec=specification,
            state_lineage=document('state_lineage'),state_snapshot=document('state_snapshot'),
            prepared_reference_set=references,prepared_reference_root=directory,
            plot=document('plot'),retrieval_record=document('retrieval_record'),visual_continuity=visual,visual_root=root,
            request_validation=validation,input_root=root,route_reading=prepared['route_reading'],reading_ledgers=[directory/'reads.jsonl'],
            service=selected['service'],production_root=root,production_context=binding)
        # Record every concrete source that the full validators consumed. The
        # task's visual basis is already a captured task source; authority is not
        # a live creative dependency. Named pack content belongs to the runtime.
        from input_evidence import InputEvidence
        known={(d['space'],d['path']):d for d in prepared['dependencies']}
        for path,item in package['input_snapshots'].items():
            data=InputEvidence._decode(item)
            if not path.startswith('@') and path!=prepared['task_path']:
                space=dependency_space(path)
                from sheet_artifacts import dependency
                known[(space,path)]=dependency(space,path,data)
                blobs[item['sha256']]=data
        prepared['dependencies']=sorted(known.values(),key=lambda d:(d['space'],d['path']))
        studio_sources = [copy.deepcopy(row['source']) for row in package['prepared_reference_set']['selected_references']
                          if row['source']['kind'] == 'studio-artifact']
        if studio_sources:
            prepared['studio_reference_sources'] = studio_sources
        prepared['input_sha256']=input_digest(prepared,consumer)
        from production_binding import bind_consumer
        package['production_binding']=bind_consumer({'run':identity,'input_sha256':prepared['input_sha256'],'consumer':consumer},consumer['instructions'])
        digest=builder.generation_input_sha256(package)
        package['generation_input_sha256']=digest;package['generation_contract']['generation_input_sha256']=digest
        verified=verify(package,package_root=directory,studio=root,reading_ledgers=[directory/'reads.jsonl'])
    with stage('request-compilation'):
        from dispatch import check_request
        check_request(verified,model_record,offering,model_id,transport,selected['seed'],selected['count'])
        rendered=request_renderer.generation(package,verified,model_record,offering,service,transport,seed=selected['seed'],count=selected['count'])
        request_renderer.check_final(validation,runtime_evidence.reader(root,snapshots=copy.deepcopy(package['input_snapshots'])),rendered)
    return _execution_plan(root,task,prepared,package,rendered,directory,identity,model_id,model_record,offering,service,transport,
                           seed=selected['seed'],count=selected['count'],
                           fields=mutable_fields(package,rendered))


def _external_effects(rendered: dict, count: int) -> list[dict]:
    effects = []
    if rendered['media']:
        effects.append({'operation': 'upload', 'count': len(rendered['media'])})
    effects.append({'operation': 'send', 'count': 1, 'outputs': count})
    return effects


def _execution_plan(root:Path,task:dict,prepared:dict,package:dict,rendered:dict,directory:Path,identity:str,
                    model_id:str,model_record:dict,offering:dict,service:dict,transport,*,seed:int|None,count:int,fields:dict)->tuple:
    import production_workflow as workflow
    effects = _external_effects(rendered, count)
    from check_tag_prompt import require_request
    prompt_check = require_request(rendered, model_record) if package.get('artifact_type') != 'upscale-request' else {
        'state': 'not-applicable', 'request_sha256': rendered['request_sha256'], 'findings': []}
    intent=workflow.submission_intent(package,rendered=rendered,seed=seed,count=count,offering=offering,service=service)
    direction={'operation':'direction','targets':workflow.plan.direction_targets(task),
               'payload':{'consumer_sha256':prepared['consumer_sha256'],'recipient':service['transport'],'method':'dispatcher'}}
    plan={'run':identity,'execution':task['execution'],'input_sha256':prepared['input_sha256'],'request_sha256':rendered['request_sha256'],
          'operations':[direction,intent],'recording':task['recording'],'quantities':{'submissions':1,'outputs':count},
          'service':offering['service'],'model':model_id,'transport':service['transport'],
          'handoff':{'recipient':service['transport'],'method':'dispatcher','consumer_sha256':prepared['consumer_sha256'],
                     'targets':direction['targets']},
          'external_effects':effects,'prompt_check':prompt_check,
          'request':rendered['request'],'validation':package['request_validation'],'mutable_fields':fields,
          'readiness':execution_readiness(prepared,operations=[direction,intent])}
    validate_document(plan,PLAN_SCHEMA,'execution plan')
    c.atomic(directory/'execution-target.json',c.encoded({'model':model_record,'model_id':model_id,'offering':offering,'service':service,
                                                      'transport_sha256':c.sha256_file(Path(transport.__file__))}))
    return package,rendered,plan


def require_upscale_target(model_id: str, model: dict, package: dict) -> None:
    """The declared upscale operation, scale and text channel must be supported."""
    if model.get('operation_kind')!='upscale':
        raise ProductionError('MODEL_PROFILE_MISSING','The selected model is not an upscaler.',phase='runtime-resolution')
    if model_id!=package['model']:
        raise ProductionError('INPUT_CONSISTENCY_ERROR','Use the canonical selected model identifier in the upscale declaration.',phase='runtime-resolution',expected=model_id,actual=package['model'])
    if package['scale_factor'] not in model.get('supported_scale_factors',[]):
        raise ProductionError('CONTROL_NOT_AVAILABLE','The model does not declare this scale factor.',phase='request-compilation',pointer='$.scale_factor')
    if package['guidance_prompt'] and model.get('supports_guidance_prompt') is not True:
        raise ProductionError('CONTROL_NOT_AVAILABLE','The upscaler does not accept guidance text.',phase='request-compilation',pointer='$.guidance_prompt')


def _upscale(root:Path,task:dict,prepared:dict,consumer:dict,directory:Path,identity:str,blobs:dict,*,captured:dict[str,bytes])->tuple:
    import dispatch, request_renderer, runtime_evidence
    from production_binding import validate_upscale_input
    from input_evidence import InputEvidence
    from route_reading import copy_issuance,ledger_candidates
    package=c.decode(consumer['instructions'].encode('utf-8'))
    validate_upscale_input(root,package)
    import sheet_artifacts
    source_artifact = sheet_artifacts.upscale_source(root, task, package)
    if source_artifact is not None:
        c.atomic(directory / 'sheet-derivation.json', c.encoded(source_artifact))
    model_id,model=dispatch.resolve_model_record(package['model'])
    require_upscale_target(model_id,model,package)
    offering=dispatch.select_offering(model,task['upscale']['service'])
    if offering is None:raise ProductionError('MODEL_PROFILE_MISSING','The upscaler has no selected service offering.',phase='runtime-resolution')
    from catalog_retrieval.runtime import load_pack_catalog
    import service_profile,transport_contract
    resource=load_pack_catalog().resources.get('service-profiles')
    if resource is None:raise ProductionError('MODEL_PROFILE_MISSING','The runtime has no service-profiles resource.',phase='runtime-resolution')
    service=service_profile.load_service(offering['service'],resource.path)
    transport=transport_contract.load(service['transport'])
    dispatch.require_guidance_key(offering,package['guidance_prompt'])
    settings=dispatch.mapped_settings(model,offering,package['settings'])
    path=package['source']['path']
    source=c.local(root,path)
    raw=captured[path] if path in captured else read_input(root,path,pointer='$.source.path')
    compare=c.digest(raw)
    if compare!=package['source']['sha256']:
        raise ProductionError('SOURCE_CHANGED','The upscale source changed during capture.',phase='source-read',file=str(source),expected=package['source']['sha256'],actual=compare)
    from production_evidence import inspect
    inspect(raw,'image')
    carrier=directory/'upscale.references'/('source'+source.suffix.lower());c.atomic(carrier,raw)
    dependencies={(item['space'],item['path']):item for item in prepared['dependencies']}
    space=dependency_space(path)
    from sheet_artifacts import dependency
    dependencies[(space,path)]=dependency(space,path,raw)
    blobs[compare]=raw
    for name,item in package['input_snapshots'].items():
        data=InputEvidence._decode(item)
        if not name.startswith('@'):
            space=dependency_space(name)
            dependencies[(space,name)]=dependency(space,name,data)
            blobs[item['sha256']]=data
    prepared['dependencies']=sorted(dependencies.values(),key=lambda item:(item['space'],item['path']))
    prepared['input_sha256']=input_digest(prepared,consumer)
    with stage('recording-validation'):validate_recording(root,task,{})
    copy_issuance(prepared['route_reading'],directory/'reads.jsonl',ledgers=ledger_candidates(studio=root))
    with stage('request-compilation'):
        rendered=request_renderer.upscale(package,model,offering,service,transport,carrier,settings,root=root)
        dispatch.check_upscale(rendered,offering,model_id)
        request_renderer.check_final(package['request_validation'],runtime_evidence.reader(root,snapshots=copy.deepcopy(package['input_snapshots'])),rendered)
    task_schema=c.load(ROOT/'schemas/authoring/production-task.schema.json')
    return _execution_plan(root,task,prepared,package,rendered,directory,identity,model_id,model,offering,service,transport,
                           seed=None,count=1,fields={
            'upscale-input':_field('An explicitly authored upscale input declaration; the target model stays fixed.',PATH_VALUE,
                required=True,value_form='studio-file',document_type='upscale-request',
                checks=['upscale-document','upscale-source','target-contract','upscale-model-controls','execution-controls',
                        'request-compilation','recording-validation']),
            'recording':_field('The complete output recording contract.',task_schema['properties']['recording'],
                required=True,checks=['recording-validation'])})


def execution_readiness(prepared: dict, *, operations: list[dict]) -> dict:
    import production_permissions as permissions
    diagnostics=[]
    authority=prepared.get('authority')
    if authority is None:
        diagnostics.append(Diagnostic('AUTHORIZATION_REQUIRED','No authority declaration is available.',phase='readiness',severity='warning',
                                      required_action='Import actual approval or delegation for these operations.').as_dict())
    else:
        for intent in operations:
            coverage=permissions.target_coverage(authority,intent['operation'],intent['targets'])
            if not any(not item['missing'] for item in coverage):
                missing=sorted(set().union(*(set(item['missing']) for item in coverage))) if coverage else sorted(intent['targets'])
                diagnostics.append(Diagnostic('GRANT_SCOPE_EXCEEDED','No current grant covers all targets of the prepared operation.',phase='readiness',severity='warning',
                    pointer='$.operations.'+intent['operation'],details={'expected':intent['targets'],'coverage':coverage,'missing':missing},
                    required_action=permissions.SCOPE_ACTION).as_dict())
        diagnostics.append(Diagnostic('AUTHORIZATION_REQUIRED','Exact execution receipts require the actual actor assessment of this preview.',phase='readiness',severity='warning',
                                      required_action='Provide execution decisions or existing exact receipts; invoking execute is not approval.').as_dict())
    return {'state':'authorization_required', 'executable':False, 'diagnostics':diagnostics}


# A studio file named as {"path": STUDIO_RELATIVE_FILE}.
PATH_VALUE={'type':'object','properties':{'path':{'type':'string','minLength':1}},'required':['path'],'additionalProperties':False}
REQUEST=['request-compilation']
# Document fields: the document a named file holds, whether the request needs
# it, whether null removes it, and the compiler checks that run again.
DOCUMENT_DECLARATIONS={
    'production-spec':('production-spec',True,False,['specification','target-contract','render-intent','execution-profile','execution-controls']+REQUEST),
    'plot':('prompt-plot',True,False,['plot','retrieval','package-compilation']+REQUEST),
    'retrieval-record':('prompt-retrieval-record',True,False,['retrieval','package-compilation']),
    'creative-intent':('creative-intent',True,False,['creative-intent','package-compilation']),
    'request-validation':('request-validation',False,True,['request-validation-evidence']+REQUEST),
    'visual-continuity':('visual-continuity',False,True,['recording-validation','package-compilation']),
    'state-lineage':('state-lineage',False,True,['source-validation','package-compilation']),
    'state-snapshot':('state-snapshot',False,True,['source-validation','package-compilation']),
    'negative-provenance':('negative-provenance',False,True,['negative-provenance','negative-transport']),
    'references':('prepared-reference-set',False,True,['dependency-preflight','reference-preparation','recording-validation']+REQUEST)}
# Task fields: whether the task needs a value, the checks that run again, and
# whether a change keeps, rechecks or redefines the protected criteria.
TASK_DECLARATIONS={
    'direction':(True,['task-contract','execution-plan'],'redefine'),
    'criteria':(True,['task-contract','execution-plan'],'redefine'),
    'source-materials':(True,['task-contract','source-validation'],'recheck'),
    'scene-materials':(False,['task-contract','scene-materials','source-validation'],'recheck'),
    'world-views':(False,['task-contract','world-views','source-validation'],'recheck'),
    'moment-views':(False,['task-contract','moment-views','source-validation'],'recheck'),
    'route-reading':(True,['route-reading'],'recheck'),
    'features':(True,['task-contract','route-reading']+REQUEST,'recheck')}


def _field(description: str, schema: dict, *, required: bool, nullable: bool = False, value_form: str = 'inline',
           document_type: str | None = None, checks: list[str], rebuild: tuple[str, ...] = ('package','request'),
           protected: str = 'recheck') -> dict:
    return {'description':description,'schema':schema,'required':required,'nullable':nullable,'value_form':value_form,
            'document_type':document_type,'checks':list(checks),'rebuild':list(rebuild),'protected_criteria':protected}


def mutable_fields(package: dict, rendered: dict) -> dict:
    """Every field a variant may change, with its value form and the checks a change runs again."""
    from production_variation import DOCUMENT_FIELDS, TASK_FIELDS
    profile=package['render_contract']['model_card']['execution_profile']
    fields={'prompt':_field('The canonical authored prompt, preserved byte for byte.',{'type':'string','minLength':1},
                            required=True,checks=['delivery-content','retrieval','plot','render-intent']+REQUEST),
            'negative':_field('The exact authored negative prompt.',{'type':'string'},required=False,
                              checks=['negative-transport']+REQUEST),
            'execution-mode':_field('An execution mode supported by the selected target profile.',{'enum':list(profile['modes'])},
                                    required=True,checks=['render-intent','target-contract','reference-preparation','execution-controls']+REQUEST)}
    for label in DOCUMENT_FIELDS:
        document_type,required,nullable,checks=DOCUMENT_DECLARATIONS[label]
        schema={'anyOf':[{'type':'null'},PATH_VALUE]} if nullable else PATH_VALUE
        removal=', or null to remove it' if nullable else ''
        fields[label]=_field(f'A studio file holding a complete {document_type} document{removal}.',schema,required=required,
                             nullable=nullable,value_form='studio-file',document_type=document_type,checks=checks)
    task_schema=c.load(ROOT/'schemas/authoring/production-task.schema.json')
    for label,name in TASK_FIELDS.items():
        required,checks,protected=TASK_DECLARATIONS[label]
        fields[label]=_field('The complete reassessed '+label+' declaration of the task.',task_schema['properties'][name],
                             required=required,checks=checks,protected=protected)
    fields['recording']=_field('The complete Studio recording contract.',task_schema['properties']['recording'],
                               required=True,checks=['recording-validation'])
    mode=package['production_spec']['render_intent']['execution_mode']
    for name,control in profile['modes'][mode]['controls'].items():
        if control['status'] not in {'required','optional'}:continue
        label='seed' if control.get('binding')=='dispatch-seed' else 'count' if control.get('binding')=='dispatch-count' else 'parameter:'+name
        quantity=label in {'seed','count'}
        fields[label]=_field(control['reason'],control['schema'],required=control['status']=='required',
                             checks=['execution-profile','execution-quantity' if quantity else 'execution-controls']+REQUEST,
                             rebuild=('request',) if quantity else ('package','request'),protected='unchanged' if quantity else 'recheck')
    return fields


def _staging(root: Path, persist: bool) -> Path:
    """An owned staging directory: inside the studio for publication, elsewhere for a check."""
    if persist:
        parent=c.local(root,'production/staging',exists=False);parent.mkdir(parents=True,exist_ok=True)
        directory=Path(tempfile.mkdtemp(prefix='compile-',dir=parent))
    else:
        directory=Path(tempfile.mkdtemp(prefix='cpb-check-'))
    operation=current()
    owner={'operation_id':operation.id if operation else str(__import__('uuid').uuid4()),'pid':os.getpid(),'created_at':c.now(),'phase':'compiling'}
    c.atomic(directory/'owner.json',c.encoded(owner))
    return directory


# The compilation stages after the input checks, in order, and what each one blocks.
STAGES=['source-validation','package-compilation','request-compilation','execution-plan']


def compile_task(root: Path, task_path: str, *, persist: bool=False, identity: str | None=None,
                 runtime_snapshot: dict | None=None, derived: dict[str, bytes] | None=None) -> Compilation:
    """Check and compile one task in one context, reading each declared input once.

    `derived` holds the inputs a derivation writes for this run, by file name.
    They are written into the staging directory and declared at their published
    place, `run_inputs(identity)`, where the task at `task_path` names them.
    """
    from contextlib import ExitStack
    import runtime_snapshot as fixed_runtime
    root=c._root(root)
    identity=identity or generate_uuid7()
    report={'ok':False,'publishable':False,'run':None,'diagnostics':[],'checks':[],'external_effect':False,
            'formal_run_created':False}
    diagnostics=report['diagnostics']
    active_phase='input-validation'
    directory=None
    try:
        import production_workflow as workflow
        with ExitStack() as context:
            if derived is not None:
                directory=_staging(root,persist)
                for name,raw in derived.items():
                    c.atomic(directory/'inputs'/name,raw)
                context.enter_context(c.staged_inputs(root,run_inputs(identity),directory/'inputs'))
            with stage('input-validation'):
                task,found,captured=inspect_task(root,task_path)
            diagnostics.extend(found)
            if task is None:
                raise CompilationError(report)
            checks=InputChecks(diagnostics)
            report['checks']=checks.rows
            checks.record('task-schema','failed' if any(d['phase']=='task-schema' for d in found) else 'passed')
            if directory is None:
                directory=_staging(root,persist)
            active_phase='runtime-resolution'
            runtime_ready=True
            if task.get('execution')=='dispatcher':
                try:
                    with stage('runtime-resolution'):
                        if runtime_snapshot is not None:
                            fixed_runtime.require_current(root,runtime_snapshot)
                            runtime_directory=fixed_runtime.path(root,runtime_snapshot)
                        else:
                            from catalog_retrieval import runtime
                            from pack_manager import default_settings
                            settings=runtime._PACK_SETTINGS or default_settings()
                            if not settings.state_file.is_file():
                                raise ProductionError('PACK_RUNTIME_REQUIRED','Pack state has not been initialized.',phase='runtime-resolution',
                                    required_action='Run pack_cli.py ready with the selected runtime; check never changes pack selection.')
                            catalog=runtime.load_pack_catalog()
                            if not catalog.active_pack_count:
                                raise ProductionError('PACK_NOT_ENABLED','No active pack satisfies the declared runtime.',phase='runtime-resolution')
                            runtime_directory=directory/'runtime'
                            runtime_snapshot=fixed_runtime.capture(catalog,settings,runtime_directory)
                        # This run binds the parts it uses when compilation completes.
                        runtime_snapshot=fixed_runtime.descriptor(runtime_snapshot)
                        context.enter_context(fixed_runtime.using(runtime_directory,runtime_snapshot,binding=directory))
                except (ValueError,OSError,KeyError,TypeError) as exc:
                    runtime_ready=False
                    diagnostics.append(from_exception(exc,phase='runtime-resolution',file=task_path))
            active_phase='input-checks'
            inspect_dependencies(root,task,task_path,captured,checks,runtime_ready=runtime_ready,directory=directory)
            if any(d.get('severity','error')=='error' for d in diagnostics):
                raise CompilationError(report)
            active_phase='source-validation'
            with stage('source-validation'):
                prepared,consumer,_,blobs=workflow.snapshot(root,task_path,captured=captured,checked=checks.values)
            checks.record('source-validation','passed')
            prepared['runtime_snapshot']=runtime_snapshot
            prepared['input_sha256']=input_digest(prepared,consumer)
            package=rendered=None
            active_phase='package-compilation'
            if task['execution']=='dispatcher':
                if task['route']=='upscale':
                    package,rendered,execution_plan=_upscale(root,task,prepared,consumer,directory,identity,blobs,captured=captured)
                else:
                    package,rendered,execution_plan=_generation(root,task,prepared,consumer,directory,identity,blobs,
                                                                inspected=checks,captured=captured)
            else:
                execution_plan={'run':identity,'execution':task['execution'],'input_sha256':prepared['input_sha256'],
                    'request_sha256':None,'operations':[],'external_effects':[],
                    'readiness':{'state':'authorization_required','executable':False,'diagnostics':[]}}
                validate_document(execution_plan,PLAN_SCHEMA,'execution plan')
            for name in STAGES[1:]:
                checks.record(name,'passed' if package is not None or name=='execution-plan' else 'not-applicable')
            active_phase='publication-verification'
            c.atomic(directory/'delivery.txt',consumer['instructions'].encode('utf-8'))
            for raw in blobs.values():c.object_store(directory,raw)
            prepared['run']=identity
            report.update(ok=True,publishable=True,readiness=execution_plan['readiness'],
                          request_preview=rendered['request'] if rendered else None,execution_plan=execution_plan)
            compiled=Compilation(report,directory,prepared,consumer,package,rendered,execution_plan,identity)
            write_compiled(compiled,media_root=directory)
            return compiled
    except (ValueError,OSError,KeyError,TypeError) as exc:
        # A changed installation is not a defect of this task: the caller reports it as such.
        if isinstance(exc,ProductionError) and exc.diagnostic.phase=='implementation':raise
        if not isinstance(exc,CompilationError):
            report['diagnostics'].append(from_exception(exc,phase=active_phase,file=task_path))
            if active_phase in STAGES:
                report['checks'].append({'phase':active_phase,'state':'failed','requires':[]})
        if active_phase in STAGES:
            blocked=STAGES[STAGES.index(active_phase)+1:]+['publication']
        elif active_phase=='publication-verification':
            blocked=['publication']
        else:
            blocked=STAGES+['publication']
        report['diagnostics'].append(Diagnostic('CHECK_NOT_PERFORMED','Full compilation is blocked by the listed errors.',
            phase='compilation',blocked_checks=blocked).as_dict())
        if directory is not None and persist:
            try:c.atomic(directory/'failure.json',c.encoded(report))
            except OSError:pass
            report['staging']=str(directory)
        elif directory is not None:
            shutil.rmtree(directory,ignore_errors=True);directory=None
        return Compilation(report,directory=directory)


def write_compiled(compiled:Compilation,*,media_root:Path)->None:
    directory=compiled.directory;prepared=compiled.prepared
    if compiled.rendered is not None:
        import request_contract as rc
        # Local carrier paths are not request semantics, but must resolve after
        # publication. No target, content, order or authored parameter changes.
        for item in compiled.rendered['media']:
            relative=Path(item['path']).relative_to(directory)
            item['path']=str(media_root/relative)
        rc.validate_seal(compiled.rendered)
    prepared['compiled']={'package_sha256':c.content_id(compiled.package) if compiled.package is not None else None,
                         'request_sha256':compiled.rendered['request_sha256'] if compiled.rendered else None,
                         'plan_sha256':c.content_id(compiled.execution_plan)}
    pairs={'execution-plan.json':compiled.execution_plan}
    if compiled.package is not None:
        pairs.update({'package.json':compiled.package,'request-contract.json':compiled.rendered,
                      'request-preview.json':compiled.rendered['request']})
    for name,value in pairs.items():c.atomic(directory/name,c.encoded(value),replace=True)

def check_task(root: Path, task_path: str) -> dict:
    """Compile without publishing; the report names no run because a check creates none."""
    compiled=compile_task(root,task_path)
    try:
        if compiled.report.get('execution_plan') is not None:
            compiled.report['execution_plan']['run']=None
        return compiled.report
    finally:
        if compiled.directory is not None:shutil.rmtree(compiled.directory)


def write_manifest(directory: Path) -> dict:
    items=[]
    for path in sorted(directory.rglob('*')):
        relative = path.relative_to(directory).as_posix()
        if path.is_symlink():raise ProductionError('ARTIFACT_PUBLISH_FAILED','Publication cannot contain symbolic links.',phase='publication',file=str(path))
        # Only these root metadata files are outside the publication digest.
        # A reference bundle can itself own a manifest/owner/failure document;
        # those nested bytes are part of the immutable production input.
        if relative in {'manifest.json','owner.json','failure.json'}:continue
        if path.is_file():items.append({'path':relative,'sha256':c.sha256_file(path),'size':path.stat().st_size})
    manifest={'files':items,'complete':True}
    c.atomic(directory/'manifest.json',c.encoded(manifest))
    return manifest


def verify_publication(directory: Path, *, expected: str | None=None) -> dict:
    raw=c.read(c.local(directory,'manifest.json'))
    if expected is not None and c.digest(raw)!=expected:
        raise ProductionError('ARTIFACT_MANIFEST_CORRUPT','Publication manifest differs from the registered digest.',phase='integrity',file=str(directory/'manifest.json'),expected=expected,actual=c.digest(raw))
    manifest=c.decode(raw)
    c.exact(manifest,{'files','complete'},'publication manifest')
    if manifest['complete'] is not True:raise ProductionError('ARTIFACT_INCOMPLETE','Publication has not completed.',phase='integrity')
    seen=set()
    for item in manifest['files']:
        if item['path'] in seen:raise ProductionError('ARTIFACT_MANIFEST_CORRUPT','Publication lists a file twice.',phase='integrity')
        seen.add(item['path']);path=c.local(directory,item['path'],exists=False)
        snapshot=item['path'].startswith('objects/')
        if not path.is_file():
            if snapshot:
                raise store.evidence_error('EVIDENCE_SNAPSHOT_MISSING','A saved source snapshot of the run is missing.',file=str(path),
                                           expected=item['sha256'],run=directory.name,artifact=item['path'])
            raise ProductionError('ARTIFACT_MISSING','A published artifact is missing.',phase='integrity',file=str(path),expected=item['sha256'],run=directory.name)
        actual=c.sha256_file(path)
        if actual!=item['sha256'] or path.stat().st_size!=item['size']:
            if snapshot:
                raise store.evidence_error('EVIDENCE_SNAPSHOT_CORRUPT','A saved source snapshot of the run differs from its committed contents.',
                                           file=str(path),expected=item['sha256'],actual=actual,run=directory.name,artifact=item['path'])
            raise ProductionError('ARTIFACT_CORRUPT','A published artifact differs from its committed contents.',phase='integrity',file=str(path),expected=item['sha256'],actual=actual,run=directory.name)
    return manifest


def publish_compilation(root: Path, compiled: Compilation, *, parent: dict | None=None, current_task: dict | None=None) -> dict:
    """Publish one already compiled staging tree as the single formal run.

    This is the publication half of prepare. Retarget and other high-level
    operations can compile once, inspect the result, and publish that same
    immutable staging tree instead of performing a second runtime resolution.
    """
    import work_ledger
    root=c._root(root)
    if not compiled.report['publishable']:raise CompilationError(compiled.report)
    if compiled.directory is None or compiled.prepared is None or compiled.consumer is None or compiled.identity is None:
        raise ProductionError('ARTIFACT_PUBLISH_FAILED','No complete compiled staging tree is available for publication.',phase='publication')
    if current_task is None:current_task=work_ledger.require_open(root)
    directory=compiled.directory;prepared=compiled.prepared;run=compiled.identity
    target=c.local(root, 'production/runs/'+run, exists=False)
    try:
        with stage('artifact-publication'), store.transaction(root):
            active=work_ledger.require_open(root)
            if active['task_id']!=prepared['task']['task_id'] or active['task_id']!=current_task['task_id']:
                raise ProductionError('TASK_CHANGED','The open work task changed during preparation.',phase='publication')
            prepared['parent']=parent
            prepared['predecessor']=store.latest_run(root,prepared['task']['task_id'])
            import production_workflow as workflow
            prepared['criteria_predecessor']=workflow.criteria_predecessor(root,prepared['predecessor'],prepared['task'])
            for dependency in prepared['dependencies']:
                if dependency['space'] in {'evidence','task-source'}:continue
                try:actual=workflow.current_sha256(root,dependency)
                except (ValueError,OSError):actual=None
                if actual!=dependency.get('selection_sha256', dependency['sha256']):
                    raise workflow.freshness_error(dependency,actual,run=None,phase='publication')
            if prepared.get('runtime_snapshot') is not None:
                import runtime_snapshot as fixed_runtime
                if (directory/'runtime').exists():
                    fixed_runtime.publish(root,directory/'runtime',prepared['runtime_snapshot'])
                fixed_runtime.require_current(root,prepared['runtime_snapshot'],run=run)
            for source in prepared.get('studio_reference_sources', []):
                from studio_reference import validate_source
                validate_source(source)
            write_compiled(compiled,media_root=target)
            prepared['envelope_sha256']=c.content_id(prepared)
            c.atomic(directory/'prepared.json',c.encoded(prepared));c.atomic(directory/'consumer.json',c.encoded(compiled.consumer))
            write_manifest(directory);verify_publication(directory)
            target.parent.mkdir(parents=True,exist_ok=True)
            if target.exists():raise ProductionError('OUTPUT_ALREADY_EXISTS','A run already occupies the publication destination.',phase='publication',file=str(target))
            c.publish_directory(directory,target);c.fsync_dir(target.parent)
            if prepared['task'].get('authority') and store.authority(root,prepared['task']['task_id'],required=False) is None:
                store.import_authority(root,prepared['task']['authority'],initial=True)
            store.register_run(root,run,prepared,target)
        warnings=[]
        try:
            with c.lock(root):
                active=work_ledger.require_open(root)
                if active['task_id']==prepared['task']['task_id']:
                    active['production_run']=run;work_ledger.write_current(root,active)
                    work_ledger.append(root,{'at':c.now(),'task_id':active['task_id'],'event':'note','text':'prepared production run '+run})
        except (ValueError,OSError) as exc:
            warnings.append({'code':'WORK_PROJECTION_FAILED','message':str(exc),'formal_run_retained':True})
        operation=current()
        if operation:
            operation.link(run=run,task=prepared['task']['task_id'])
        return {'ok':True,'run':run,'input_sha256':prepared['input_sha256'],'consumer':str(target/'consumer.json'),
                'package':str(target/'package.json') if compiled.package else None,'request_preview':compiled.report['request_preview'],
                'execution_plan':compiled.execution_plan,'warnings':warnings,'formal_run_created':True}
    except BaseException:
        if directory.exists():
            try:c.atomic(directory/'failure.json',c.encoded({'state':'publication-interrupted','target':str(target)}))
            except OSError:pass
        raise



def _windows_pid_active(pid: int) -> bool:
    """Query a process handle without sending a signal or terminating a process."""
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE only
    if not handle:
        return ctypes.get_last_error() != 87  # No such PID; denied/unknown stays protected.
    try:
        # A zero timeout queries process termination without waiting or signaling.
        return kernel.WaitForSingleObject(handle, 0) != 0
    finally:
        kernel.CloseHandle(handle)


def _pid_active(pid: int) -> bool:
    if type(pid) is not int or pid <= 0:
        return False
    if os.name == 'nt':
        try:
            return _windows_pid_active(pid)
        except (OSError, OverflowError):
            return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except (PermissionError, OSError, OverflowError):
        return True
    return True


def _remove_owned(path: Path, label: str) -> None:
    try:
        shutil.rmtree(path)
    except OSError as exc:
        raise ProductionError('ARTIFACT_PUBLISH_FAILED', f'Owned {label} could not be removed.',
                              phase='cleanup', file=str(path), actual=type(exc).__name__) from exc


def _owner(directory: Path) -> dict:
    """The operation and process that own a staging or publication directory."""
    owner = c.load(c.local(directory, 'owner.json'))
    if not isinstance(owner, dict) or not isinstance(owner.get('operation_id'), str) or not owner['operation_id']:
        raise ValueError('owner operation is not declared')
    if type(owner.get('pid')) is not int or owner['pid'] < 0:
        raise ValueError('owner process is not declared')
    return owner


def _owned_tree(root: Path, directory: Path) -> dict:
    """Refuse a path outside the studio, a link anywhere inside, or an undeclared owner."""
    c.local(root, directory.relative_to(root).as_posix())
    if not directory.is_dir() or directory.is_symlink():
        raise ValueError('not a regular directory')
    # Refuse unexpected linked descendants, even if their target would not be removed by rmtree.
    if any(p.is_symlink() for p in directory.rglob('*')):
        raise ValueError('linked contents')
    return _owner(directory)


def _staging_items(root: Path, parent: Path, operation_id: str | None, apply: bool) -> list[dict]:
    rows = []
    if not parent.exists():
        return rows
    references = [c.local(root, item['directory'], exists=False) for item in store.runs(root)]
    for directory in sorted(parent.iterdir()):
        item = {'path': str(directory), 'name': directory.name, 'eligible': False, 'reasons': []}
        try:
            owner = _owned_tree(root, directory)
            item.update(operation_id=owner['operation_id'], pid=owner['pid'], created_at=owner.get('created_at'), phase=owner.get('phase'))
        except (ValueError, OSError, TypeError):
            item['reasons'].append('owner metadata or staging path is unsafe')
        else:
            if operation_id and owner['operation_id'] != operation_id:
                item['reasons'].append('owned by a different operation')
            elif _pid_active(owner['pid']):
                item['reasons'].append('owner process may still be active')
            elif any(p == directory or directory in p.parents or p in directory.parents for p in references):
                item['reasons'].append('referenced by a formal Production run')
            else:
                item['eligible'] = True
                item['reasons'].append('unpublished staging owned by a non-running operation')
                if apply:
                    _remove_owned(directory, 'staging')
                    item['deleted'] = True
        rows.append(item)
    return rows


def _journal_items(root: Path, operation_id: str | None, apply: bool) -> list[dict]:
    """Dispatch journals that no claim names; only an ended owner's journal is removable."""
    from production_execution import unclaimed_journals
    rows = unclaimed_journals(root)
    for item in rows:
        if not item['eligible']:
            continue
        if operation_id and item.get('operation_id') != operation_id:
            item['eligible'] = False
            item['reasons'].append('owned by a different operation')
        elif apply:
            directory = Path(item['path'])
            c.local(root, directory.relative_to(root).as_posix())
            if directory.is_symlink() or not directory.is_dir() or any(p.is_symlink() for p in directory.rglob('*')):
                item['eligible'] = False
                item['reasons'].append('not a regular journal directory')
                continue
            _remove_owned(directory, 'dispatch journal')
            item['deleted'] = True
    return rows


def _publication_items(root: Path, operation_id: str | None, apply: bool) -> list[dict]:
    """Unregistered publications: a recoverable one is recovered; an unrecoverable one is removable by its owner."""
    rows = []
    for found in unregistered_publications(root):
        item = {**found, 'eligible': False, 'reasons': []}
        if found.get('run') is None:
            item['reasons'].append('the publication directory cannot be listed')
        elif found['recoverable']:
            item['reasons'].append('recoverable: register it with recover-publication')
        else:
            directory = Path(found['path'])
            try:
                owner = _owned_tree(root, directory)
                item.update(operation_id=owner['operation_id'], pid=owner['pid'])
            except (ValueError, OSError, TypeError):
                item['reasons'].append('owner metadata or publication path is unsafe')
            else:
                if operation_id and owner['operation_id'] != operation_id:
                    item['reasons'].append('owned by a different operation')
                elif _pid_active(owner['pid']):
                    item['reasons'].append('owner process may still be active')
                else:
                    item['eligible'] = True
                    item['reasons'].append('unregistered publication that cannot be recovered; its owner operation has ended')
                    if apply:
                        _remove_owned(directory, 'publication')
                        item['deleted'] = True
        rows.append(item)
    return rows


def staging_cleanup(root: Path, *, operation_id: str | None = None, apply: bool = False) -> dict:
    """Inspect or remove one dead operation's unreferenced staging, dispatch journals and publications.

    Paths, ownership, live process state and formal references are listed again
    while holding the same studio lock as publication, right before any removal.
    A symlink is never traversed. A journal a claim names is never listed.
    """
    root = Path(root).absolute()
    try:
        parent = c.local(root, 'production/staging', exists=False)
    except (OSError, ValueError) as exc:
        raise ProductionError('STAGING_CLEANUP_REFUSED', 'Staging is outside the owned studio tree or contains a symbolic link.',
                              phase='cleanup', file=str(root/'production/staging')) from exc
    if apply and not operation_id:
        raise ProductionError('INPUT_CONSISTENCY_ERROR', 'Applying staging cleanup requires --operation.',
                              phase='cleanup', required_action='Inspect the dry run and select its exact owner operation ID.')
    with c.lock(root):
        rows = _staging_items(root, parent, operation_id, apply)
        journals = _journal_items(root, operation_id, apply)
        publications = _publication_items(root, operation_id, apply)
    deleted = sum(1 for item in rows + journals + publications if item.get('deleted'))
    return {'ok': True, 'apply': apply, 'items': rows, 'journals': journals, 'publications': publications,
            'deleted': deleted, 'external_effect': False}


def prepare_task(root: Path, task_path: str, *, parent: dict | None=None, identity: str | None=None,
                 runtime_snapshot: dict | None=None) -> dict:
    import work_ledger
    current_task=work_ledger.require_open(root)
    compiled=compile_task(root,task_path,persist=True,identity=identity,runtime_snapshot=runtime_snapshot)
    return publish_compilation(root,compiled,parent=parent,current_task=current_task)


def inspect_publication(root: Path, run: str) -> tuple[Path, dict, dict]:
    """Verify an unregistered completion without changing authority or live sources."""
    import production_workflow as workflow
    run = workflow.run_identifier(run)
    directory = c.local(root, 'production/runs/' + run)
    verify_publication(directory)
    prepared = c.load(c.local(directory, 'prepared.json'))
    consumer = c.load(c.local(directory, 'consumer.json'))
    workflow.validate_run_content(run, prepared, consumer, [], lambda key: c.object_read(directory, key))
    descriptor = prepared.get('runtime_snapshot')
    if descriptor is not None:
        import runtime_snapshot
        runtime_snapshot.read(runtime_snapshot.path(root, descriptor), descriptor)
    return directory, prepared, consumer


def unregistered_publications(root: Path, registered: list[dict] | None = None) -> list[dict]:
    """Expose durable publications whose database registration was interrupted."""
    known = {row['run_id'] for row in (store.runs(root) if registered is None else registered)}
    output = []
    try:
        parent = c.local(root, 'production/runs', exists=False)
        if not parent.exists():
            return output
        children = sorted(parent.iterdir())
    except (OSError, ValueError) as exc:
        return [{'run': None, 'recoverable': False, 'diagnostics': [from_exception(exc, phase='publication-recovery')]}]
    for directory in children:
        if directory.name in known:
            continue
        item = {'run': directory.name, 'path': str(directory), 'recoverable': False}
        try:
            _, prepared, _ = inspect_publication(root, directory.name)
            item.update(recoverable=True, input_sha256=prepared['input_sha256'], next_action='recover-publication')
        except (OSError, ValueError, KeyError, TypeError) as exc:
            item['diagnostics'] = [from_exception(exc, phase='publication-recovery')]
        output.append(item)
    return output


def recover_publication(root: Path, run: str) -> dict:
    """Register verified saved contents, never resurrect an old grant or send."""
    import production_workflow as workflow
    run = workflow.run_identifier(run)
    with store.transaction(root):
        existing = [row for row in store.runs(root) if row['run_id'] == run]
        if existing:
            workflow.load_run(root, run)
        else:
            directory, prepared, _ = inspect_publication(root, run)
            store.register_run(root, run, prepared, directory)
        return {'ok': True, 'run': run, 'recovered': not bool(existing), 'external_effect': False,
                'authority_restored': False, 'next_action': 'status'}
