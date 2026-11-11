"""One compiler for task checking, complete preparation and package construction.

A check returns diagnostics and an ephemeral preview. Preparation publishes the
same compiled contents only when all required input checks passed. Permission,
and credentials are execution readiness, not malformed input.
"""
from __future__ import annotations
import copy
from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any

import execution_contract as c
import production_store as store
from production_diagnostics import CompilationError, Diagnostic, ProductionError, compare_exact, from_exception
from operation_context import current, stage
from pack_manager import generate_uuid7
from publication_artifacts import ArtifactSet, StagedArtifacts
from cli_invocation import python_argv, shown
from owned_json import freeze

ROOT=Path(__file__).resolve().parents[1]
GENERATION_FILES=('parameters','production_spec','plot','retrieval_record','creative_intent','negative',
                  'integrated_prompt','native_negative','negative_provenance','references','state_lineage',
                  'state_snapshot','state_graphs','visual_continuity','request_validation','mask_binding')
JSON_FILES=set(GENERATION_FILES)-{'negative','integrated_prompt','native_negative'}
# A derived run's own inputs live in its run directory and are never live studio sources.
RUN_INPUT=re.compile(r'^production/runs/[^/]+/inputs/')
# A run directory without a registration whose manifest is not a complete publication manifest.
UNRECOVERABLE_PUBLICATION=('This publication cannot be registered. List it with staging-cleanup, remove it with --apply '
                           '--operation once its owner operation has ended, then run the preparing command again.')
# A registered run whose registered manifest bytes are not a complete publication manifest.
REGISTERED_MANIFEST_DAMAGED=('The registration of this run records these exact manifest bytes, so no other copy of its '
                             'manifest is known, and a registered run is not corrected in place. Nothing is read from '
                             'this run, and other runs are unaffected. Prepare a new run of the task with prepare.')
REPORT_SCHEMA='schemas/authoring/production-compilation-report.schema.json'
PLAN_SCHEMA='schemas/authoring/production-execution-plan.schema.json'
PUBLICATION_CONTROLS=('manifest.json','owner.json','failure.json',c.LOCK_FILE)


def run_inputs(run: str) -> str:
    """The studio-relative directory that holds a derived run's own inputs."""
    return f'production/runs/{run}/inputs'


def dependency_space(path: str) -> str:
    """Inputs a run owns inside its own directory are task sources; every other file is a live studio source."""
    return 'task-source' if RUN_INPUT.match(path) else 'studio'


def read_input(root: Path, path: str, *, pointer: str | None, phase: str = 'source-read') -> bytes:
    """Read one declared input once; a failure names the file, the task pointer, the cause and its repair."""
    try:
        return store.stable_bytes(root, path)
    except ProductionError as exc:
        failure = exc.diagnostic
        if failure.code != 'EVIDENCE_CAPTURE_FAILED':
            if failure.pointer is None:
                failure.pointer = pointer
            raise
        raise ProductionError('INPUT_UNREADABLE', 'The declared input could not be read.', phase=phase, file=path,
                              pointer=pointer, required_action=failure.required_action,
                              **failure.details) from exc.__cause__


def validate_document(value: Any, schema_path: str, label: str) -> None:
    """Check a produced document against its published schema."""
    from state_protocol import read_schema, validate_against_schema
    errors = validate_against_schema(value, read_schema(ROOT / schema_path))
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
    artifacts: ArtifactSet | None = None
    runtime_read: Any = None


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


def authored_input_digest(prepared: dict, consumer: dict) -> str:
    """Hash what the author supplied: the input without the installation pins and the fixed pack runtime.

    A repeat keeps this identity. The installation and the packs may differ
    between the two preparations; each run pins its own.
    """
    reduced = {**prepared, 'runtime_snapshot': None,
               'dependencies': [x for x in prepared['dependencies'] if x['space'] != 'skill']}
    return input_digest(reduced, consumer)


def _file_inputs(task: dict) -> list[tuple[str,str]]:
    items=[]
    delivery=task.get('delivery')
    if isinstance(delivery,dict) and isinstance(delivery.get('path'),str):items.append(('$.delivery.path',delivery['path']))
    if isinstance(task.get('route_reading'),str):items.append(('$.route_reading',task['route_reading']))
    if isinstance(task.get('image_input'),str):items.append(('$.image_input',task['image_input']))
    if isinstance(task.get('semantic_edit'),str):items.append(('$.semantic_edit',task['semantic_edit']))
    basis = task.get('authored_basis')
    if isinstance(basis, dict):
        for index, source in enumerate(basis.get('sources', []) if isinstance(basis.get('sources'), list) else []):
            item = source.get('file') if isinstance(source, dict) else None
            if isinstance(item, dict) and isinstance(item.get('path'), str):
                items.append((f'$.authored_basis.sources[{index}].file.path', item['path']))
    for index,source in enumerate(task.get('sources',[]) if isinstance(task.get('sources'),list) else []):
        if isinstance(source,dict) and isinstance(source.get('path'),str):items.append((f'$.sources[{index}].path',source['path']))
    for index,source in enumerate(task.get('upload_sources',[]) if isinstance(task.get('upload_sources'),list) else []):
        if isinstance(source,dict) and isinstance(source.get('file'),str):items.append((f'$.upload_sources[{index}].file',source['file']))
    generation=task.get('generation')
    if isinstance(generation,dict):
        for name in GENERATION_FILES:
            if isinstance(generation.get(name),str):items.append(('$.generation.'+name,generation[name]))
    return items


NO_TASK_CHECKS=['task-schema','task-contract','sources','runtime-resolution','source-validation','package-compilation',
                'request-compilation','recording-validation','execution-plan','publication']


def _prerequisite(name: str) -> str:
    """How a repair names one prerequisite: a check, or the input file at a pointer of the task."""
    if name.startswith('input:'):
        return 'the input at ' + name.removeprefix('input:')
    if name.startswith('undeclared:'):
        return 'an input at ' + name.removeprefix('undeclared:') + ', which the task does not declare'
    return name


def _resolve_first(prerequisites: list[str], waiting: str) -> str:
    """The repair of `waiting`, which did not run: resolve its failed prerequisites first, each as its own diagnostic directs."""
    names = [_prerequisite(name) for name in prerequisites]
    if len(names) == 1:
        return (f'Resolve the error of {names[0]} first, as its own diagnostic in this report directs; '
                f'{waiting} runs once it passes. Then run the same command again.')
    return (f'Resolve the errors of {", ".join(names[:-1])} and {names[-1]} first, each as its own diagnostic in '
            f'this report directs; {waiting} runs once they pass. Then run the same command again.')


def inspect_task(root: Path, task_path: str) -> tuple[dict | None,list[dict],dict[str,bytes]]:
    """Read the task and every file it declares once, keeping each failure with its pointer and cause."""
    diagnostics=[]; captured={}
    def no_task(diagnostic: dict):
        diagnostics.append(diagnostic)
        blocked=[diagnostic['phase']]
        diagnostics.append(Diagnostic('CHECK_NOT_PERFORMED','No task object is available for dependent checks.',phase='task-read',
                                      file=task_path,blocked_checks=NO_TASK_CHECKS,details={'blocked_by':blocked},
                                      required_action=_resolve_first(blocked,'every check in blocked_checks')).as_dict())
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
    from state_protocol import read_schema, validate_against_schema
    errors=validate_against_schema(task,read_schema(ROOT/'schemas/authoring/production-task.schema.json'))
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


def specification_guidance(root: Path, file: str | None, pointer: str | None = None) -> dict:
    """Resolve specification help from structural field names and the selected file."""
    # These are schema field selectors, not words inferred from an error message.
    fields = (pointer or '$').replace('[', '.').replace(']', '').split('.')
    section = next((anchor for field, anchor in (
        ('camera', 'camera-framing-contract'), ('performance', 'performance-language'),
        ('layout', 'layout-and-local-views'), ('render_intent', 'rendering-intent'),
        ('state_context', 'state-modes'), ('subjects', 'subject-record')) if field in fields), 'ownership-boundary')
    result = {'document_path': 'references/production-specification.md#' + section,
              'schema': 'protocols/shared-state/schemas/production-spec.schema.json'}
    if file is not None:
        argv = python_argv(ROOT / 'scripts' / 'production_spec.py', 'validate',
                           str(root / file), '--require-content')
        result['validation'] = {'argv': argv, 'command': shown(argv),
                                'reason': 'Inspect this specification on its own; check and prepare already run the same validator.'}
    return result


class InputChecks:
    """Track individual validator results and their actual prerequisites."""
    def __init__(self, diagnostics: list[dict], *, root: Path):
        self.diagnostics = diagnostics
        self.root = root
        self.states: dict[str, str] = {}
        self.values: dict[str, Any] = {}
        self.rows: list[dict] = []
        self.requires: dict[str, list[str]] = {}

    def record(self, name: str, state: str, requires=()) -> None:
        """Record the state of a check performed elsewhere in the compilation."""
        self.states[name] = state
        self.requires[name] = list(requires)
        self.rows.append({'phase': name, 'state': state, 'requires': list(requires)})

    def failed_behind(self, names: list[str]) -> list[str]:
        """The failed checks that keep `names` from passing, following prerequisites that did not run."""
        found, seen, pending = [], set(), list(names)
        while pending:
            name = pending.pop(0)
            if name in seen:
                continue
            seen.add(name)
            if self.states.get(name) == 'not-performed':
                pending.extend(self.requires.get(name, []))
            elif self.states.get(name) == 'failed':
                found.append(name)
        return found

    def check(self, name: str, action, *, requires=(), file=None, pointer=None, code=None,
              guidance=None, required_action=None):
        """Run one check unless a prerequisite failed; `code` names a failure that has no code of its own.

        A `ParameterErrors` failure reports each problem at `$.PARAMETER` with
        the code its status names. A check that knows more about one problem
        adds `code`, `pointer` and `required_action` to it, and those apply.
        """
        blocked = [key for key in requires if self.states.get(key) != 'passed']
        if blocked:
            self.record(name, 'not-performed', requires)
            # The failed checks behind the blocked ones each name their own repair.
            failed = self.failed_behind(blocked) or blocked
            self.diagnostics.append(Diagnostic('CHECK_NOT_PERFORMED',
                'This check did not run: it requires ' + ', '.join(blocked) + ', which did not pass.',
                phase=name, file=file, pointer=pointer, blocked_checks=[name], guidance=guidance,
                required_action=_resolve_first(failed, 'check ' + name),
                details={'blocked_by': blocked, **({'failed_prerequisites': failed} if failed != blocked else {})}).as_dict())
            return None
        try:
            with stage(name):
                value = action()
        except (ValueError, OSError, KeyError, TypeError, IndexError, ImportError) as exc:
            self.record(name, 'failed', requires)
            if isinstance(exc, ImportError):
                synchronize = shown(['uv', 'sync', '--locked', '--project', str(ROOT)])
                verify = shown(['uv', 'run', '--locked', '--project', str(ROOT),
                                'python', str(ROOT / 'scripts' / 'check_dependencies.py')])
                diagnostic = Diagnostic('DEPENDENCY_UNAVAILABLE', 'A Python dependency this check needs is not installed.',
                    phase=name, file=file, pointer=pointer, details={'cause': str(exc)},
                    required_action=f'Synchronize the project environment with {synchronize}, then verify it with {verify}.').as_dict()
            else:
                selected = _status_code(getattr(exc, 'status', None)) or code
                diagnostic = from_exception(exc, phase=name, file=file, pointer=pointer,
                                            guidance=guidance, required_action=required_action,
                                            **({'code': selected} if selected and not isinstance(exc, ProductionError) else {}))
            if diagnostic.get('file') is None: diagnostic['file'] = file
            if diagnostic.get('pointer') is None: diagnostic['pointer'] = pointer
            from render_contract_lib import ParameterErrors
            from production_spec import SpecificationError
            if isinstance(exc, ParameterErrors):
                for item in exc.problems:
                    problem = {**diagnostic, 'message': item['message'],
                               'pointer': item.get('pointer', '$.' + item['parameter']),
                               'required_action': item.get('required_action', diagnostic['required_action'])}
                    problem['code'] = item.get('code') or _status_code(item.get('status')) or diagnostic['code']
                    self.diagnostics.append(problem)
            elif isinstance(exc, SpecificationError):
                for message in exc.errors:
                    detail = message.removeprefix('production specification: ')
                    at = detail.split(':', 1)[0].split()[0] if detail.startswith('$') else pointer
                    self.diagnostics.append({**diagnostic, 'code': 'INPUT_SCHEMA_INVALID',
                        'message': detail, 'pointer': at,
                        'required_action': 'Correct the reported fields in this specification, then continue check or prepare.',
                        'guidance': specification_guidance(self.root, file, at)})
            else:
                self.diagnostics.append(diagnostic)
            return None
        self.states[name] = 'passed'
        self.values[name] = value
        self.rows.append({'phase': name, 'state': 'passed', 'requires': list(requires)})
        return value


def inspect_dependencies(root: Path, task: dict, task_path: str, captured: dict[str, bytes],
                         checks: InputChecks, *, runtime_ready: bool, directory: Path, artifacts: ArtifactSet,
                         runtime_source=None,evidence=None) -> None:
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
    checks.check('task-contract', lambda: workflow.validate_task(task), requires=whole, file=task_path,
                 required_action='Correct the declared task fields. If the route or features change, issue a reading for that selection and reuse only applications that still apply.')
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
                return freeze(c.decode(raw))
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
        c.decode(captured[task['route_reading']]), studio=root, routes={task['route']}, features=task['features'], execution=task['execution'],
        operation='author' if task.get('execution')=='authored' else 'prepare'),
        requires=[dependency('$.route_reading'),'task-contract'] + (['runtime-resolution'] if dispatcher else []),
        file=files.get('$.route_reading'), pointer='$.route_reading',
        required_action='Read the complete contract for this operation and selected target, then use its issued reading.')
    if task.get('execution') == 'authored':
        import authored_prompt
        checks.check('authored-prompt', lambda: authored_prompt.check(task, cached),
                     requires=['task-contract', 'delivery-content'], file=task_path, pointer='$.authored')
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
    if task.get('image_input'):
        import image_input
        checks.check('image-input', lambda: bounded(image_input.task_binding),
                     requires=['task-contract', dependency('$.image_input')],
                     file=task['image_input'], pointer='$.image_input')
    if task.get('semantic_edit'):
        from semantic_edit_plan import task_binding
        checks.check('semantic-edit', lambda: bounded(task_binding),
                     requires=['task-contract', dependency('$.semantic_edit'), 'image-input'],
                     file=task['semantic_edit'], pointer='$.semantic_edit')
    if task.get('execution') == 'external':
        import image_input
        from render_contract_lib import validate_intent
        documents = []
        document_checks = []
        for index, source in enumerate(image_input.external_document_sources(task)):
            path, role = source['path'], source['role']
            source_pointer = next(pointer for pointer, value in files.items() if value == path)
            name = 'external-document:' + str(index)
            owner = (specification_guidance(root, path) if role == 'production-spec' else
                     {'document_path': 'references/runtime/render-contract.md#external-image-work',
                      'schema': 'schemas/render-intent.schema.json'})
            def document(path=path, role=role):
                value = c.decode(cached(path))
                image_input.validate_external_document(value, role)
                return value
            value = checks.check(name, document, requires=[dependency(source_pointer)],
                                 file=path, guidance=owner)
            intent_name = 'external-render-intent:' + str(index)
            def intent(value=value, role=role):
                return validate_intent(value['render_intent'] if role == 'production-spec' else value,
                                       prompt=text('prompt'))
            checks.check(intent_name, intent, requires=[name, 'delivery-content'], file=path,
                         pointer='$.render_intent' if role == 'production-spec' else '$',
                         guidance={'document_path': 'references/runtime/render-contract.md#external-image-work'})
            document_checks.extend((name, intent_name))
            documents.append({**source, 'value': value})
        checks.check('external-image-contract', lambda: bounded(lambda base, value, add:
            image_input.external_documents(base, value, add,
                inputs=checks.values.get('image-input', (None, {}))[0], documents=documents)),
            requires=['task-contract', 'delivery-content', *document_checks] + (['image-input'] if task.get('image_input') else []),
            file=task_path)
    if task.get('authority'):
        def authority():
            value=c.decode(cached(task['authority'], '$.authority'))
            workflow.schema_check(value,'authority')
            cached(value['evidence']['path'])
            from input_evidence import EvidenceAcquisition
            return workflow.permissions.acquire(value,task['task_id'],EvidenceAcquisition(root))
        # A committed authority is the current one; the task's file is read only before the first import.
        if checks.states.get('task-schema') != 'passed' or store.authority_record(root, task['task_id']) is None:
            checks.check('authority-evidence',authority,requires=whole,file=task['authority'] if present(task['authority']) else task_path,
                         pointer='$.authority')
    if selected and selected.get('mask_binding'):
        import scene_mask_planner
        checks.check('scene-mask-binding', lambda: scene_mask_planner.check_task(
            root, task, doc('mask_binding'), read=cached),
            requires=['task-contract', dependency('$.generation.mask_binding')],
            file=selected['mask_binding'], pointer='$.generation.mask_binding')
    elif 'scene-mask-planning' in task.get('features', []):
        def require_mask_binding():
            raise ValueError('The scene-mask-planning feature requires generation.mask_binding.')
        checks.check('scene-mask-binding', require_mask_binding, requires=['task-contract'], file=task_path)
    if not dispatcher: return
    import build_generation_payload as builder
    import render_contract_lib as render
    def target(model_name, service):
        result=builder.resolve_target(model_name,service,source=runtime_source)
        if not result.matches(model_name) or result.offering is None or result.offering['service']!=service:
            raise ValueError('the selected packs resolve another model or service than the task declares')
        if result.service is None:
            raise ProductionError('MODEL_PROFILE_MISSING','The declared target has no selected offering.',phase='runtime-resolution')
        return result
    if selected is None:
        if task.get('route') != 'upscale' and upscale is None:
            return
        # The upscale source and settings are independent of the output slot.
        import production_binding, dispatch
        request=checks.check('upscale-document',lambda:c.decode(captured[delivery_path]),
                             requires=[prompt_key],file=delivery_path,pointer='$.delivery.path')
        if request is not None:
            checks.check('upscale-source', lambda: production_binding.validate_upscale_input(root, request,input_source=runtime_source),
                         requires=['upscale-document'],file=delivery_path)
            resolved=checks.check('target-contract',lambda:target(request['model'],upscale['service']),
                                 requires=['runtime-resolution','upscale-document']+gate((upscale or {}).get('service')),
                                 file=delivery_path,pointer='$.model')
            if resolved is not None:
                checks.check('upscale-model-controls',lambda:require_upscale_target(resolved.model_id,resolved.model,request),
                             requires=['target-contract'],file=delivery_path)
                def upscale_controls():
                    model,offering=resolved.model,resolved.offering
                    scale=(offering.get('parameter_keys') or {}).get('scale')
                    if not scale:
                        raise ProductionError('MODEL_PROFILE_MISSING','The upscale offering declares no request key for the scale factor.',
                            phase='execution-controls',file=delivery_path,pointer='$.scale_factor',actual=offering.get('service'),
                            required_action='Declare parameter_keys.scale on the selected offering of the upscale model record.')
                    dispatch.require_guidance_key(offering,request['guidance_prompt'])
                    settings=dispatch.mapped_settings(model,offering,request['settings'])
                    try:
                        contract=render.compile_contract(model,offering,request['render_intent'],{**settings,scale:request['scale_factor']},
                            prompt=request['guidance_prompt'] or '',reference_count=1)
                    except render.ParameterErrors as exc:
                        raise render.ParameterErrors([_upscale_scale_problem(item,scale=scale,model_id=resolved.model_id,
                            offering=offering,mode=request['render_intent']['execution_mode'],factor=request['scale_factor'])
                            for item in exc.problems]) from exc
                    render.dispatch_values(contract,seed=None,count=1)
                checks.check('execution-controls',upscale_controls,requires=['target-contract'],file=delivery_path)
        return
    from generation_inputs import GenerationInputs
    specpath=selected.get('production_spec')
    documents={name:checks.values.get(dependency('$.generation.'+name)) for name in JSON_FILES}
    def input_text(field):
        path=delivery_path if field=='prompt' else selected.get(field)
        raw=captured.get(path,b'') if path else b''
        try:return raw.decode('utf-8')
        except UnicodeDecodeError:return raw
    specification=documents.get('production_spec')
    values={**documents,'model':selected.get('model') or (specification.get('target_model') if isinstance(specification,dict) else None),
        'render_intent':selected.get('render_intent'),
        'parameters':documents.get('parameters') if selected.get('parameters') else {},
        'prompt':input_text('prompt'),'negative_prompt':input_text('negative'),
        'integrated_prompt':input_text('integrated_prompt'),'native_negative':input_text('native_negative'),
        'brief':selected.get('brief',''),'service':selected.get('service'),
        'negative_transport':selected.get('negative_transport','auto'),
        'critical_avoidance_integrated':selected.get('critical_avoidance_integrated',False),
        'prepared_reference_set':documents.get('references'),'route_reading':c.decode(captured[task['route_reading']]) if task.get('route_reading') in captured else None,
        'seed':selected.get('seed'),'count':selected.get('count')}
    def selected_target():
        result=builder.resolve_target(values['model'],selected['service'],source=runtime_source)
        if result.offering is None or result.service is None:
            raise ProductionError('MODEL_PROFILE_MISSING','The declared target has no selected offering or service.',phase='runtime-resolution')
        return result
    def preflight():
        from reference_runtime import preflight_dependencies, DependencyPreflightError
        prepared=documents['references']
        plan=prepared.get('reference_use_plan') if isinstance(prepared.get('reference_use_plan'),dict) else {}
        try:return preflight_dependencies({'transport_mode':prepared.get('transport_mode'),
            'reference_items':plan.get('reference_items') or prepared.get('selected_references') or []})
        except DependencyPreflightError as exc:
            raise ProductionError('DEPENDENCY_UNAVAILABLE',str(exc),phase='dependency-preflight',file=selected['references'],
                missing=exc.report.get('missing_packages') or [],incompatible=exc.report.get('incompatible_packages') or [],
                required_action='Complete the project environment with '+exc.report['check_command']+' --install, then check again.') from exc
    def references():
        prepared,_=builder.materialize_cli_reference_bundle(documents['references'],model=values['model'],
            source_root=c.local(root,selected['references']).parent,staging_root=directory,
            companion_name='package.'+c.content_id(documents['references'])[:24]+'.references',artifacts=artifacts)
        return prepared
    def validation(selected_target):
        reference_document=documents.get('references')
        if reference_document is not None and reference_document.get('transport_mode')!='none':
            raise ProductionError('VALIDATION_POLICY_REQUIRED','Reference delivery requires an explicitly authored request validation policy.',
                                  phase='request-validation-evidence',pointer='$.generation.request_validation',
                                  required_action='Author an execution policy that declares reference_instruction_transport for this target, '
                                                  'select it at choices.validation.execution_policy, then run the same command again.')
        from request_validation import acquire_offering
        return acquire_offering(selected_target,evidence)
    required={
        'specification':[dependency('$.generation.production_spec')] if specpath else [],
        'plot':[dependency('$.generation.plot')] if selected.get('plot') else [],
        'creative-intent':[dependency('$.generation.creative_intent')] if selected.get('creative_intent') else [],
        'target-contract':['specification','runtime-resolution']+gate(selected.get('service')),
        'dependency-preflight':[dependency('$.generation.references')],
        'reference-preparation':['target-contract','dependency-preflight',dependency('$.generation.references')],
        'render-intent':['specification','delivery-content'],
        'execution-profile':['target-contract'],
        'execution-controls':['execution-profile']+([dependency('$.generation.parameters')] if selected.get('parameters') else []),
        'execution-quantity':['execution-profile','render-intent']+whole,
        'request-validation-evidence':([dependency('$.generation.request_validation'),'runtime-resolution']
            if selected.get('request_validation') else ['target-contract']),
        'negative-provenance':[dependency('$.generation.negative_provenance')] if selected.get('negative_provenance') else [],
        'negative-transport':['delivery-content','execution-controls']+[dependency('$.generation.'+field)
            for field in ('negative','integrated_prompt','native_negative') if selected.get(field)],
        'retrieval':['plot','delivery-content','target-contract']+([dependency('$.generation.retrieval_record')] if selected.get('retrieval_record') else [])}
    field_for={'specification':'production_spec','plot':'plot','creative-intent':'creative_intent',
        'target-contract':'production_spec','dependency-preflight':'references','reference-preparation':'references',
        'render-intent':'production_spec','execution-profile':'production_spec','execution-controls':'parameters',
        'request-validation-evidence':'request_validation','negative-provenance':'negative_provenance',
        'negative-transport':'negative','retrieval':'retrieval_record'}
    def report(name,action):
        field=field_for.get(name)
        options={'requires':required[name],'file':selected.get(field) if field else task_path}
        if name=='retrieval' and 'target-contract' in checks.values:
            from model_prompt_input import resolve_prompt_input
            if resolve_prompt_input(checks.values['target-contract'].model)['mode']=='tag-based':
                options['requires']=[*options['requires'],'execution-controls',
                    *([dependency('$.generation.negative')] if selected.get('negative') else [])]
        if name=='specification':options['guidance']=specification_guidance(root,specpath)
        if name=='execution-profile':options['code']='MODEL_PROFILE_MISSING'
        if name=='execution-quantity':options['pointer']='$.generation.count'
        elif name in {'target-contract','execution-profile'}:options['pointer']='$.target_model'
        elif name=='render-intent':options['pointer']='$.render_intent'
        elif name=='execution-controls':options['pointer']='$.generation.parameters'
        return checks.check(name,action,**options)
    resolved=GenerationInputs.acquire(values,resolve_target=selected_target,prepare_references=references,
        preflight_references=preflight,evidence=evidence,check=report,validation_factory=validation)
    if resolved is not None:checks.values['generation-inputs']=resolved


def validate_recording(root: Path, task: dict, specification: dict, visual: dict | None = None) -> None:
    import studio
    recording=task.get('recording')
    if recording is None:
        return
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


def _runtime_binding(root:Path,prepared:dict,*,runtime_inputs,directory:Path,persist:bool,
                     target,package:dict,evidence_bytes=None):
    import runtime_snapshot
    descriptor,read=runtime_snapshot.capture_compilation(runtime_inputs.runtime,
        directory/'runtime' if persist else None,
        target={'model_id':target.model_id,'offering':target.offering},package=package,
        reading_resources={name:row for name,row in prepared['reading_issuance'].get('resources',{}).items()
                           if row.get('status')=='present'},evidence_bytes=evidence_bytes)
    warnings=runtime_snapshot.require_retained(root,runtime_inputs,descriptor)
    prepared['runtime_snapshot']=descriptor
    return read,warnings


def _generation(root: Path, task: dict, prepared: dict, consumer: dict, directory: Path, identity: str, blobs: dict, *,
                inspected: InputChecks, captured: dict[str, bytes], artifacts: ArtifactSet,
                runtime_inputs,evidence,persist:bool) -> tuple:
    import build_generation_payload as builder
    import request_renderer
    from route_reading import copy_issuance, ledger_candidates
    selected=task['generation']
    inputs=inspected.values['generation-inputs']
    target=inputs.target
    specification=inputs.values['production_spec']
    reference_set=inputs.references
    if reference_set.get('image_input_binding') is not None and not consumer.get('image_input'):
        raise ValueError('scoped image references require the production task image_input plan')
    if consumer.get('image_input'):
        from image_input import require_prepared
        require_prepared(consumer['image_input'],reference_set,model_id=target.model_id,
            target={'service':target.offering['service'],'model_identifier':target.offering['model_identifier'],
                    'operation':target.transport.OPERATIONS['generation']})
    if selected.get('visual_continuity'):
        visual=inputs.values['visual_continuity']
    else:
        from visual_continuity import from_decisions
        visual=from_decisions(selected.get('continuity',{}),production_spec=specification,prepared=reference_set,root=root,
            characters=(task.get('recording') or {}).get('subject_map',{}),sheet_panel=(task.get('recording') or {}).get('sheet_panel',False),
            basis={'path':prepared['task_path'],'locator':'$.generation.continuity and $.recording'})
    issued=copy_issuance(prepared['route_reading'],directory/'reads.jsonl',ledgers=ledger_candidates(studio=root))
    artifacts.add('reads.jsonl',c.encoded(issued))
    with stage('package-compilation'):
        content=builder.acquire_generation(inputs,prepared_reference_root=directory,visual_root=root,
            production_root=root,evidence=evidence,visual_continuity=visual,recording=task.get('recording'))
        from sheet_artifacts import dependency
        known={(d['space'],d['path']):d for d in prepared['dependencies']}
        for path,raw in content.evidence.bytes.items():
            if not path.startswith('@') and path!=prepared['task_path']:
                space=dependency_space(path)
                known[(space,path)]=dependency(space,path,raw)
                blobs[c.digest(raw)]=raw
        prepared['dependencies']=sorted(known.values(),key=lambda d:(d['space'],d['path']))
        studio_sources=[copy.deepcopy(row['source']) for row in reference_set['selected_references']
                        if row['source']['kind']=='studio-artifact']
        if studio_sources:prepared['studio_reference_sources']=studio_sources
    with stage('request-compilation'):
        media=None
        if selected.get('mask_binding'):
            import scene_mask_planner
            staged=copy.deepcopy(content.forwarding)
            scene_mask_planner.stage_media(staged,inspected.values['scene-mask-binding'],target.offering,directory,artifacts=artifacts)
            media=staged['host_forwarding']['technical_media']
        rendered=request_renderer.generation_from_inputs(content,consumer,seed=selected['seed'],count=selected['count'],
            resource_reader=runtime_inputs.runtime.read_resource,technical_media=media,
            upload_sources=task.get('upload_sources',[]),upload_source_read=lambda path:captured[path])
        prompt_check=_prompt_check(content.fields,rendered,target.model)
    runtime_read,warnings=_runtime_binding(root,prepared,runtime_inputs=runtime_inputs,directory=directory,persist=persist,
        target=target,package=content.runtime_inputs,evidence_bytes=content.evidence.bytes)
    prepared['input_sha256']=input_digest(prepared,consumer)
    from production_binding import bind_consumer
    package=content.package(bind_consumer({'run':identity,'input_sha256':prepared['input_sha256'],'consumer':consumer},
                                         consumer['instructions']))
    package,rendered,plan=_execution_plan(root,task,prepared,package,rendered,directory,identity,target,
        seed=selected['seed'],count=selected['count'],fields=mutable_fields(package,rendered),artifacts=artifacts,
        prompt_check=prompt_check)
    return package,rendered,plan,runtime_read,warnings


def _external_effects(rendered: dict, count: int, transport) -> list[dict]:
    from production_request import external_effects
    return external_effects(rendered, count, transport)


def _external_reference_evidence(prepared: dict, consumer: dict, directory: Path, blobs: dict,
                                  artifacts: ArtifactSet, *, run: str) -> None:
    """Preserve external delivery pixels and accepted-source proof in the run.

    The production object store owns the exact prepared carriers. Studio proof
    retains every transitive source file through its existing archive owner.
    Live source activity still gates a new send; saved evidence supports later
    review after a source or its prepared carrier moves.
    """
    inputs = consumer.get('image_input') or {}
    canonical = inputs.get('prepared_reference_set') or {}
    from sheet_artifacts import dependency
    known = {(row['space'], row['path']): row for row in prepared['dependencies']}
    if canonical:
        from prepare_generation_references import host_reference_transports
        for carrier in host_reference_transports(canonical):
            path = Path(carrier['resolved_path'])
            raw = store.stable_bytes(path.parent, path.name)
            if c.digest(raw) != carrier['sha256']:
                raise ValueError('prepared external reference carrier checksum mismatch: ' + str(path))
            relative = 'production/runs/' + run + '/objects/' + carrier['sha256']
            known[('evidence', relative)] = dependency('evidence', relative, raw)
            blobs[carrier['sha256']] = raw
    sources = {c.content_id(row['source']): copy.deepcopy(row['source'])
               for row in canonical.get('selected_references', []) if row['source']['kind'] == 'studio-artifact'}
    if sources:
        from studio_reference import archive_source
        companion = directory / 'image-input.references'
        archived = ArtifactSet(companion)
        for source in sources.values():
            for item in archive_source(source, companion):
                archived.add_record(item)
        for item in archived.files():
            raw = archived.read(item['path'])
            relative = companion.name + '/' + item['path']
            artifacts.add_record({**item, 'path': relative})
            source_path = 'production/runs/' + run + '/' + relative
            known[('evidence', source_path)] = dependency('evidence', source_path, raw)
            blobs[c.digest(raw)] = raw
        prepared['studio_reference_sources'] = list(sources.values())
    prepared['dependencies'] = sorted(known.values(), key=lambda row: (row['space'], row['path']))
    prepared['input_sha256'] = input_digest(prepared, consumer)


def _prompt_check(package:dict,rendered:dict,model_record:dict)->dict:
    from check_tag_prompt import require_request
    from prompt_weighting import from_contract
    prompt_check = require_request(rendered, model_record,
        prompt_syntax=from_contract(package['render_contract']),
        vocabulary_selection=(package.get('retrieval_record') or {}).get('vocabulary')) if package.get('artifact_type') != 'upscale-request' else {
        'state': 'not-applicable', 'request_sha256': rendered['request_sha256'], 'findings': []}
    # This is the verified package's audit, not newly inferred guidance or text.
    # In particular a compound expression may preserve recommendations as advice.
    prompt_check['recommendations'] = package.get('generation_payload', {}).get('prompt_recommendations', {})
    return prompt_check


def _execution_plan(root:Path,task:dict,prepared:dict,package:dict,rendered:dict,directory:Path,identity:str,
                    target,*,seed:int|None,count:int,fields:dict,artifacts:ArtifactSet,prompt_check:dict)->tuple:
    import production_workflow as workflow
    from model_rendition import review_requirements
    model_id,model_record,offering,service,transport=(target.model_id,target.model,target.offering,target.service,target.transport)
    effects = _external_effects(rendered, count, transport)
    intent=workflow.submission_intent(package,rendered=rendered,seed=seed,count=count,offering=offering,service=service)
    direction={'operation':'direction','targets':workflow.plan.direction_targets(task),
               'payload':{'consumer_sha256':prepared['consumer_sha256'],'recipient':service['transport'],'method':'dispatcher'}}
    plan={'run':identity,'execution':task['execution'],'input_sha256':prepared['input_sha256'],'request_sha256':rendered['request_sha256'],
          'operations':[direction,intent],'recording':task.get('recording'),'quantities':{'submissions':1,'outputs':count},
          'service':offering['service'],'model':model_id,'transport':service['transport'],
          'handoff':{'recipient':service['transport'],'method':'dispatcher','consumer_sha256':prepared['consumer_sha256'],
                     'targets':direction['targets']},
          'external_effects':effects,'prompt_check':prompt_check,'review_requirements':review_requirements(),
          'request':rendered['request'],'validation':package['request_validation'],'mutable_fields':fields,
          'readiness':execution_readiness(prepared,operations=[direction,intent])}
    validate_document(plan,PLAN_SCHEMA,'execution plan')
    artifacts.write('execution-target.json',c.encoded({'model':model_record,'model_id':model_id,'offering':offering,'service':service,
                                                      'transport_sha256':target.transport_sha256}))
    return package,rendered,plan


def require_upscale_target(model_id: str, model: dict, package: dict) -> None:
    """The declared upscale operation, scale and text channel must be supported.

    A model record lists its known request factors in supported_scale_factors.
    Without the field, or with null, those factors are unknown: the offering's
    execution profile and the selected request evidence then constrain the scale.
    """
    if model.get('operation_kind')!='upscale':
        raise ProductionError('MODEL_PROFILE_MISSING','The selected model is not an upscaler.',phase='runtime-resolution',
            required_action='Select a model record whose operation_kind is upscale, at choices.target or as the model of the '
                            'upscale declaration, then run the same command again.')
    if model_id!=package['model']:
        raise ProductionError('INPUT_CONSISTENCY_ERROR','Use the canonical selected model identifier in the upscale declaration.',phase='runtime-resolution',expected=model_id,actual=package['model'],
            required_action='Name the model by its record ID, given as expected, in the upscale declaration, then run the same command again.')
    supported=model.get('supported_scale_factors')
    if supported is not None and package['scale_factor'] not in supported:
        raise ProductionError('CONTROL_NOT_AVAILABLE','The model does not declare this scale factor.',phase='request-compilation',pointer='$.scale_factor',
            required_action='Select a scale factor that supported_scale_factors of the model record lists, or record this factor '
                            'there when request evidence establishes it, then run the same command again.')
    if package['guidance_prompt'] and model.get('supports_guidance_prompt') is not True:
        raise ProductionError('CONTROL_NOT_AVAILABLE','The upscaler does not accept guidance text.',phase='request-compilation',pointer='$.guidance_prompt',
            required_action='Set guidance_prompt to null in the upscale declaration, or select an upscaler whose record sets '
                            'supports_guidance_prompt to true, then run the same command again.')


def _upscale_scale_problem(item: dict, *, scale: str, model_id: str, offering: dict, mode: str, factor: Any) -> dict:
    """Report a scale factor that the offering's execution profile refuses at the declaration's scale_factor.

    Without supported_scale_factors in the model record, the schema of the
    scale control in the selected offering's execution profile lists the
    factors the interface takes. Every other control problem is kept as it is.
    """
    if item['parameter'] != scale or item['status'] != 'schema-invalid':
        return item
    where = (f'the schema of the {scale} control in modes.{mode}.controls of the execution_profile of the '
             f'{offering["service"]} offering in model record {model_id}')
    return {**item, 'code': 'CONTROL_NOT_AVAILABLE', 'pointer': '$.scale_factor',
            'message': f'The execution profile of the selected offering does not allow scale factor {factor}: {item["message"]}',
            'required_action': f'Select a scale_factor that {where} allows, or record the factor there when request '
                               'evidence establishes it, then run the same command again.'}


def _upscale(root:Path,task:dict,prepared:dict,consumer:dict,directory:Path,identity:str,blobs:dict,*,
             captured:dict[str,bytes],artifacts:ArtifactSet,inspected:InputChecks,runtime_inputs,persist:bool)->tuple:
    import dispatch, request_renderer, runtime_evidence
    from input_evidence import InputEvidence
    from route_reading import copy_issuance,ledger_candidates
    package=copy.deepcopy(inspected.values['upscale-document'])
    import sheet_artifacts
    source_artifact = sheet_artifacts.upscale_source(root, task, package)
    if source_artifact is not None:
        artifacts.write('sheet-derivation.json', c.encoded(source_artifact))
    target=inspected.values['target-contract']
    model_id,model,offering,service,transport=(target.model_id,target.model,target.offering,target.service,target.transport)
    from route_reading import require_model_reading
    require_model_reading(prepared['route_reading'],model_record=model,service=offering['service'],
        resource_reader=runtime_inputs.runtime.read_resource)
    dispatch.require_guidance_key(offering,package['guidance_prompt'])
    settings=dispatch.mapped_settings(model,offering,package['settings'])
    path=package['source']['path']
    source=c.local(root,path)
    raw=captured[path] if path in captured else read_input(root,path,pointer='$.source.path')
    compare=c.digest(raw)
    if compare!=package['source']['sha256']:
        raise ProductionError('SOURCE_CHANGED','The upscale source changed during capture.',phase='source-read',file=str(source),expected=package['source']['sha256'],actual=compare,
            required_action='Finish writing the upscale source image, then run the same command again. If the image was replaced on '
                            'purpose, select it again as the source with draft-inputs --route upscale, so that the new '
                            'input pins its bytes.')
    from production_evidence import inspect
    inspect(raw,'image')
    carrier=directory/'upscale.references'/('source'+source.suffix.lower());artifacts.write(carrier,raw)
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
    with stage('recording-validation'):validate_recording(root,task,{})
    issued=copy_issuance(prepared['route_reading'],directory/'reads.jsonl',ledgers=ledger_candidates(studio=root))
    artifacts.add('reads.jsonl',c.encoded(issued))
    with stage('request-compilation'):
        rendered=request_renderer.upscale(package,model,offering,service,transport,carrier,settings,
            root=root,upload_sources=task.get('upload_sources', []),upload_source_read=lambda path:captured[path],
            input_source=runtime_inputs.runtime)
        from model_contract import validate_request_schema
        import request_contract
        instance=copy.deepcopy(rendered['request'])
        for path in request_renderer.envelope_fields(rendered):request_contract.remove(instance,path)
        validate_request_schema(offering,instance,target.parameter_schema)
        request_renderer.check_final(package['request_validation'],runtime_evidence.reader(root,
            snapshots=copy.deepcopy(package['input_snapshots']),source=runtime_inputs.runtime),rendered)
        prompt_check=_prompt_check(package,rendered,model)
    runtime_read,warnings=_runtime_binding(root,prepared,runtime_inputs=runtime_inputs,directory=directory,persist=persist,
        target=target,package=package)
    prepared['input_sha256']=input_digest(prepared,consumer)
    task_schema=c.load(ROOT/'schemas/authoring/production-task.schema.json')
    package,rendered,plan=_execution_plan(root,task,prepared,package,rendered,directory,identity,target,
                           seed=None,count=1,artifacts=artifacts,prompt_check=prompt_check,fields={
            'upscale-input':_field('An explicitly authored upscale input declaration; the target model stays fixed.',PATH_VALUE,
                required=True,value_form='studio-file',document_type='upscale-request',
                checks=['upscale-document','upscale-source','target-contract','upscale-model-controls','execution-controls',
                        'request-compilation','recording-validation']),
            'recording':_field('The complete output recording contract.',task_schema['properties']['recording'],
                required=True,checks=['recording-validation'])})
    return package,rendered,plan,runtime_read,warnings


def execution_readiness(prepared: dict, *, operations: list[dict]) -> dict:
    import production_permissions as permissions
    authority=prepared.get('authority')
    requirements=permissions.grant_requirements(authority,operations)
    diagnostics=[{**item,'phase':'readiness','severity':'warning'} for item in requirements['diagnostics']]
    diagnostics.append(Diagnostic('AUTHORIZATION_REQUIRED','Exact execution receipts require the actual actor assessment of this preview.',phase='readiness',severity='warning',
                                  required_action='Provide execution decisions or existing exact receipts; invoking execute is not approval.').as_dict())
    return {'state':'authorization_required', 'executable':False, 'diagnostics':diagnostics,
            'authorization_requirements':requirements}


# A studio file named as {"path": STUDIO_RELATIVE_FILE}.
PATH_VALUE={'type':'object','properties':{'path':{'type':'string','minLength':1}},'required':['path'],'additionalProperties':False}
REQUEST=['request-compilation']
# Document fields: the document a named file holds, whether the request needs
# it, whether null removes it, and the compiler checks that run again.
DOCUMENT_DECLARATIONS={
    'production-spec':('production-spec',False,True,['specification','target-contract','render-intent','execution-profile','execution-controls']+REQUEST),
    'plot':('prompt-plot',False,True,['plot','retrieval','package-compilation']+REQUEST),
    'retrieval-record':('prompt-retrieval-record',False,True,['retrieval','package-compilation']),
    'creative-intent':('creative-intent',False,True,['creative-intent','package-compilation']),
    'request-validation':('request-validation',False,True,['request-validation-evidence']+REQUEST),
    'visual-continuity':('visual-continuity',False,True,['recording-validation','package-compilation']),
    'state-lineage':('state-lineage',False,True,['source-validation','package-compilation']),
    'state-snapshot':('state-snapshot',False,True,['source-validation','package-compilation']),
    'state-graphs':('state artifact graph array',False,True,['source-validation','package-compilation']),
    'negative-provenance':('negative-provenance',False,True,['negative-provenance','negative-transport']),
    'references':('prepared-reference-set',False,True,['dependency-preflight','reference-preparation','recording-validation']+REQUEST)}
# Task fields: whether the task needs a value, the checks that run again, and
# whether a change keeps, rechecks or redefines the protected criteria.
TASK_DECLARATIONS={
    'direction':(True,['task-contract','execution-plan'],'redefine'),
    'criteria':(True,['task-contract','execution-plan'],'redefine'),
    'source-materials':(True,['task-contract','source-validation'],'recheck'),
    'upload-sources':(False,['task-contract','source-validation']+REQUEST,'recheck'),
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
                               required=False,nullable=True,checks=['recording-validation'])
    mode=package['render_contract']['intent']['execution_mode']
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
        # Resolve the system temporary spelling: an 8.3 or junction-spelled
        # temporary directory must match resolved carrier paths.
        directory=Path(tempfile.mkdtemp(prefix='cpb-check-')).resolve()
    operation=current()
    owner={'operation_id':operation.id if operation else str(__import__('uuid').uuid4()),'pid':os.getpid(),'created_at':c.now(),'phase':'compiling'}
    c.atomic(directory/'owner.json',c.encoded(owner),durable=persist)
    return directory


# The compilation stages after the input checks, in order, and what each one blocks.
STAGES=['source-validation','package-compilation','request-compilation','execution-plan','identity-coverage']


def compile_task(root: Path, task_path: str, *, persist: bool=False, identity: str | None=None,
                 runtime_inputs=None, derived: dict[str, bytes] | None=None,
                 source_inputs: dict[str,bytes] | None=None) -> Compilation:
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
    artifacts=None
    runtime_read=None
    runtime_source=None
    evidence=None
    try:
        import production_workflow as workflow
        with ExitStack() as context:
            if derived is not None:
                directory=_staging(root,persist)
                artifacts=StagedArtifacts(directory)
                for name,raw in derived.items():
                    artifacts.write('inputs/'+name,raw)
                context.enter_context(c.staged_inputs(root,run_inputs(identity),directory/'inputs'))
            with stage('input-validation'):
                task,found,captured=inspect_task(root,task_path)
            diagnostics.extend(found)
            if task is None:
                raise CompilationError(report)
            checks=InputChecks(diagnostics, root=root)
            report['checks']=checks.rows
            checks.record('task-schema','failed' if any(d['phase']=='task-schema' for d in found) else 'passed')
            if directory is None:
                directory=_staging(root,persist)
                artifacts=StagedArtifacts(directory)
            active_phase='runtime-resolution'
            runtime_ready=True
            if task.get('execution')=='dispatcher':
                try:
                    with stage('runtime-resolution'):
                        if runtime_inputs is None:runtime_inputs=fixed_runtime.compilation_inputs(root)
                        if not isinstance(runtime_inputs,fixed_runtime.CompileInputs):
                            raise TypeError('compile a task from acquired runtime inputs')
                        runtime_source=runtime_inputs.runtime
                        context.enter_context(runtime_source.using())
                        import runtime_evidence
                        evidence=runtime_evidence.acquisition(root,source=runtime_source)
                except (ValueError,OSError,KeyError,TypeError) as exc:
                    runtime_ready=False
                    diagnostics.append(from_exception(exc,phase='runtime-resolution',file=task_path))
            active_phase='input-checks'
            inspect_dependencies(root,task,task_path,captured,checks,runtime_ready=runtime_ready,directory=directory,
                                 artifacts=artifacts,runtime_source=runtime_source,evidence=evidence)
            if any(d.get('severity','error')=='error' for d in diagnostics):
                raise CompilationError(report)
            active_phase='source-validation'
            with stage('source-validation'):
                prepared,consumer,_,blobs=workflow.snapshot(root,task_path,captured=captured,checked=checks.values)
            from sheet_artifacts import dependency
            extra_inputs=dict(source_inputs or {})
            if task.get('execution') == 'authored':
                prepared['authored_prompt']=checks.values.get('authored-prompt')
                extra_inputs.update({path:raw for path,raw in captured.items()
                                     if path not in {row['path'] for row in prepared['dependencies']}})
            for path,raw in extra_inputs.items():
                if c.read(c.local(root,path)) != raw:
                    raise ValueError('authoring source changed during compilation: ' + path)
                prepared['dependencies'].append(dependency(dependency_space(path),path,raw))
                blobs[c.digest(raw)]=raw
            prepared['dependencies']=list({(row['space'],row['path']):row for row in prepared['dependencies']}.values())
            checks.record('source-validation','passed')
            prepared['runtime_snapshot']=None
            prepared['input_sha256']=input_digest(prepared,consumer)
            package=rendered=None
            active_phase='package-compilation'
            if task['execution']=='dispatcher':
                if task['route']=='upscale':
                    package,rendered,execution_plan,runtime_read,warnings=_upscale(root,task,prepared,consumer,directory,identity,blobs,
                        captured=captured,artifacts=artifacts,inspected=checks,runtime_inputs=runtime_inputs,persist=persist)
                else:
                    package,rendered,execution_plan,runtime_read,warnings=_generation(root,task,prepared,consumer,directory,identity,blobs,
                        inspected=checks,captured=captured,artifacts=artifacts,runtime_inputs=runtime_inputs,
                        evidence=evidence,persist=persist)
                if warnings:report['runtime_warnings']=warnings
            else:
                if task['execution'] == 'external':
                    _external_reference_evidence(prepared, consumer, directory, blobs, artifacts, run=identity)
                execution_plan={'run':identity,'execution':task['execution'],'input_sha256':prepared['input_sha256'],
                    'request_sha256':None,'operations':[],'external_effects':[],
                    'readiness':{'state':'authorization_required','executable':False,'diagnostics':[]}}
                external = (consumer.get('image_input') or {}).get('external_request')
                if external is not None:
                    from model_rendition import review_requirements
                    from production_request import external_intent
                    from production_plan import direction_targets
                    target = consumer['image_input']['model']['target']
                    handoff = {'recipient': target['service'], 'method': 'manual',
                               'consumer_sha256': c.content_id(consumer), 'targets': direction_targets(task)}
                    operations = [
                        {'operation': 'direction', 'targets': handoff['targets'],
                         'payload': {key: handoff[key] for key in ('recipient', 'method', 'consumer_sha256')}},
                        external_intent(consumer, handoff['recipient'])]
                    execution_plan.update(request=external['request'], service=target['service'],
                                          model=target['model_identifier'],
                                          request_sha256=consumer['image_input']['binding_sha256'],
                                          handoff=handoff, operations=operations,
                                          external_effects=[{'operation': 'send', 'count': 1, 'outputs': external['count']}],
                                          readiness=execution_readiness(prepared, operations=operations),
                                          prepared_request_sha256=external['sha256'],
                                          model_identity=external.get('model_identity'),
                                          validation=external['schema_validation'],
                                          review_requirements=review_requirements(),
                                          quantities={'submissions': 1, 'outputs': external['count']})
                    if external.get('prompt_check') is not None:
                        execution_plan['prompt_check'] = external['prompt_check']
                validate_document(execution_plan,PLAN_SCHEMA,'execution plan')
            active_phase='identity-coverage'
            import identity_coverage
            import production_identity
            def identity_read(path):
                if path not in captured:
                    selected_path = Path(path)
                    captured[path] = (store.stable_bytes(selected_path.parent, selected_path.name)
                                      if selected_path.is_absolute() else read_input(root, path, pointer=None,
                                                                                  phase='identity-coverage'))
                raw = captured[path]
                blobs[c.digest(raw)] = raw
                return raw
            identity_context = production_identity.context(task, identity_read,
                package=package, rendered=rendered, inputs=consumer.get('image_input'))
            if task['execution'] == 'authored':
                text = consumer['instructions']
                identity_context['text']['primary'] = {'text': text, 'field': ['delivery'],
                                                       'sha256': c.digest(text.encode('utf-8'))}
            coverage = identity_coverage.compile(task, identity_read, context=identity_context)
            coverage['request_verified'] = task['execution'] != 'authored'
            if coverage['sources']:
                prepared['identity_coverage'] = coverage
                report['identity_coverage'] = coverage
            checks.record('identity-coverage', 'passed' if coverage['sources'] else 'not-applicable')
            for name in STAGES[1:]:
                if name == 'identity-coverage':
                    continue
                checks.record(name,'passed' if package is not None or name=='execution-plan' else 'not-applicable')
            active_phase='publication-verification'
            artifacts.write('delivery.txt',consumer['instructions'].encode('utf-8'))
            for digest,raw in blobs.items():
                written=artifacts.write('objects/'+digest,raw)
                if written['sha256']!=digest:
                    raise ValueError('captured object bytes differ from their owned digest')
            prepared['run']=identity
            report.update(ok=True,publishable=True,readiness=execution_plan['readiness'],
                          request_preview=rendered['request'] if rendered else execution_plan.get('request'),execution_plan=execution_plan)
            compiled=Compilation(report,directory,prepared,consumer,package,rendered,execution_plan,identity,artifacts,
                                 runtime_read)
            if task['execution']=='authored':
                import production_authored
                production_authored.finalize_compilation(compiled)
            # Checks consume the compiled values directly. Publication is the
            # only writer of the final JSON documents and their carrier paths.
            relocate_compiled_media(compiled,media_root=directory)
            if not persist:
                # A check exercises the same JSON encoding constraints without
                # writing files that are immediately discarded with the stage.
                for value in compiled_documents(compiled).values():
                    c.encoded(value)
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
        # The phases of the errors listed before this one; each error names its own repair.
        failed=list(dict.fromkeys(item['phase'] for item in report['diagnostics']
                                  if item.get('severity','error')=='error' and item['code']!='CHECK_NOT_PERFORMED')) or [active_phase]
        report['diagnostics'].append(Diagnostic('CHECK_NOT_PERFORMED','Full compilation is blocked by the listed errors.',
            phase='compilation',blocked_checks=blocked,details={'blocked_by':failed},
            required_action=_resolve_first(failed,'the rest of the compilation')).as_dict())
        if directory is not None and persist:
            try:c.atomic(directory/'failure.json',c.encoded(report))
            except OSError:pass
            report['staging']=str(directory)
        elif directory is not None:
            shutil.rmtree(directory,ignore_errors=True);directory=None
        return Compilation(report,directory=directory)


def relocate_compiled_media(compiled:Compilation,*,media_root:Path)->None:
    """Keep local carriers inside the stage without changing request semantics."""
    directory=compiled.directory
    if compiled.rendered is not None:
        import request_contract as rc
        # Local carrier paths are not request semantics, but must resolve after
        # publication. No target, content, order or authored parameter changes.
        for item in compiled.rendered['media']:
            relative=Path(item['path']).relative_to(directory)
            item['path']=str(media_root/relative)
        rc.validate_seal(compiled.rendered)


def compiled_documents(compiled:Compilation)->dict:
    """The output values shared by check previews and final publication."""
    pairs={'execution-plan.json':compiled.execution_plan}
    if compiled.package is not None:
        pairs.update({'package.json':compiled.package,'request-contract.json':compiled.rendered,
                      'request-preview.json':compiled.rendered['request']})
    elif compiled.execution_plan.get('request') is not None:
        pairs['request-preview.json'] = compiled.execution_plan['request']
    return pairs


def write_compiled(compiled:Compilation,*,media_root:Path)->None:
    """Serialize each final document once and bind the exact published bytes."""
    if compiled.artifacts is None:
        raise ValueError('compiled artifacts must have a producer-owned set')
    relocate_compiled_media(compiled,media_root=media_root)
    pairs=compiled_documents(compiled)
    records={name:compiled.artifacts.write(name,c.encoded(value)) for name,value in pairs.items()}
    compiled.prepared['compiled']={
        'package_sha256':records['package.json']['sha256'] if compiled.package is not None else None,
        'request_sha256':compiled.rendered['request_sha256'] if compiled.rendered else None,
        'plan_sha256':records['execution-plan.json']['sha256']}

def check_task(root: Path, task_path: str) -> dict:
    """Compile without publishing; the report names no run because a check creates none."""
    compiled=compile_task(root,task_path)
    try:
        if compiled.report.get('execution_plan') is not None:
            compiled.report['execution_plan']['run']=None
        return compiled.report
    finally:
        if compiled.directory is not None:shutil.rmtree(compiled.directory)


def write_manifest(directory: Path, artifacts: ArtifactSet) -> dict:
    """Seal exactly the producers' outputs after checking the entire stage."""
    if artifacts.root != c._root(directory):
        raise ValueError('publication artifacts belong to another staging directory')
    artifacts.require_membership(controls=PUBLICATION_CONTROLS)
    manifest={'files':artifacts.files(),'complete':True}
    c.atomic(directory/'manifest.json',c.encoded(manifest))
    return manifest


def read_manifest(directory: Path, *, expected: str | None=None) -> dict:
    """Read the sealed ownership rows of a publication that no run registers yet.

    `expected` is the digest of the manifest the calling operation wrote.
    """
    return _read_publication_manifest(directory, expected=expected)[0]


def _read_publication_manifest(directory: Path, *, expected: str | None = None,
                               registered: bool = False) -> tuple[dict, str]:
    """Read and check a publication manifest; `registered` says that `expected` is a run's registered digest.

    A manifest that is not a complete file array is repaired by who holds it:
    a publication without a registration is removed and prepared again, while
    a registered run keeps the manifest bytes its registration records.
    """
    path=directory/'manifest.json'
    raw=c.read(c.local(directory,'manifest.json'))
    digest = c.digest(raw)
    damaged=REGISTERED_MANIFEST_DAMAGED if registered else UNRECOVERABLE_PUBLICATION
    where={'file':str(path),**({'run':directory.name} if registered else {})}
    if expected is not None and digest!=expected:
        if registered:
            raise ProductionError('ARTIFACT_MANIFEST_CORRUPT','Publication manifest differs from the registered digest.',
                                  phase='integrity',expected=expected,actual=digest,required_action=store.RESTORE_EVIDENCE,**where)
        raise ProductionError('ARTIFACT_MANIFEST_CORRUPT','Publication manifest differs from the one this operation wrote.',
                              phase='integrity',expected=expected,actual=digest,required_action=damaged,**where)
    manifest=c.decode(raw)
    c.exact(manifest,{'files','complete'},'publication manifest')
    if manifest['complete'] is not True:
        raise ProductionError('ARTIFACT_INCOMPLETE','Publication has not completed.',phase='integrity',
                              required_action=damaged,**where)
    if not isinstance(manifest['files'],list):
        raise ProductionError('ARTIFACT_MANIFEST_CORRUPT','Publication files must be an array.',phase='integrity',
                              required_action=damaged,**where)
    ArtifactSet(directory,manifest['files'],damaged=damaged)
    return manifest, digest


@dataclass(frozen=True)
class PublicationRead:
    """The verified manifest and decoded documents from one read boundary."""

    manifest: dict
    documents: Mapping[str, Any]
    directory: Path
    manifest_sha256: str


def acquire_publication(directory: Path, *, expected: str | None = None, registered: bool = False,
                        documents=()) -> PublicationRead:
    """Acquire a publication and decode its requested JSON at the I/O boundary.

    Every boundary reads its own current bytes. Large media is streamed;
    requested documents are decoded from the bytes that were checked. The
    returned values have no lazy readers or cross-boundary success state.
    `registered` says that `expected` is the manifest digest a run's
    registration records; otherwise the publication has no registration yet.
    """
    manifest, manifest_sha256 = _read_publication_manifest(directory, expected=expected, registered=registered)
    requested = frozenset(documents)
    acquired = {}
    for item in manifest['files']:
        path=c.local(directory,item['path'],exists=False)
        snapshot=item['path'].startswith('objects/')
        if not path.is_file():
            if snapshot:
                raise store.evidence_error('EVIDENCE_SNAPSHOT_MISSING','A saved source snapshot of the run is missing.',file=str(path),
                                           expected=item['sha256'],run=directory.name,artifact=item['path'])
            raise ProductionError('ARTIFACT_MISSING','A published artifact is missing.',phase='integrity',file=str(path),expected=item['sha256'],run=directory.name,
                                  required_action=store.RESTORE_EVIDENCE)
        raw = None
        if item['path'] in requested:
            raw = c.read(path)
            actual, size = c.digest(raw), len(raw)
        else:
            digest = hashlib.sha256()
            size = 0
            with path.open('rb') as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    size += len(chunk)
                    digest.update(chunk)
            actual = digest.hexdigest()
        if actual!=item['sha256'] or size!=item['size']:
            if snapshot:
                raise store.evidence_error('EVIDENCE_SNAPSHOT_CORRUPT','A saved source snapshot of the run differs from its committed contents.',
                                           file=str(path),expected=item['sha256'],actual=actual,run=directory.name,artifact=item['path'])
            raise ProductionError('ARTIFACT_CORRUPT','A published artifact differs from its committed contents.',phase='integrity',file=str(path),expected=item['sha256'],actual=actual,run=directory.name,
                                  required_action=store.RESTORE_EVIDENCE)
        if raw is not None:
            acquired[item['path']] = c.decode(raw)
    return PublicationRead(freeze(manifest), freeze(acquired),
                           Path(directory).absolute(), manifest_sha256)


def verify_publication(directory: Path, *, expected: str | None=None) -> dict:
    """Verify a publication that no run registers yet when no caller needs decoded artifact contents."""
    return acquire_publication(directory, expected=expected).manifest


def validate_execution_artifact(prepared: dict, name: str, document: Any) -> None:
    """Check a decoded dispatcher document against its prepared binding."""
    if prepared['task']['execution'] != 'dispatcher':
        return
    expected = prepared['compiled']
    if name == 'package.json':
        compare_exact({'package_sha256': expected['package_sha256']},
                      {'package_sha256': c.content_id(document)}, phase='integrity')
    elif name == 'execution-plan.json':
        compare_exact({'plan_sha256': expected['plan_sha256']},
                      {'plan_sha256': c.content_id(document)}, phase='integrity')
        compare_exact(document['request_sha256'], expected['request_sha256'], phase='integrity')
    elif name == 'request-contract.json':
        import request_contract
        compare_exact({'request_sha256': expected['request_sha256']},
                      {'request_sha256': document['request_sha256']}, phase='integrity')
        request_contract.validate_seal(document)


def validate_execution_documents(prepared: dict, documents: Mapping[str, Any]) -> None:
    """Validate the complete execution binding before exposing a RunView."""
    if prepared['task']['execution'] != 'dispatcher':
        return
    expected = prepared['compiled']
    fields = ('package_sha256', 'request_sha256', 'plan_sha256')
    compare_exact(expected, {key: expected.get(key) for key in fields}, phase='integrity')
    for key in fields:
        c.sha(expected[key])
    for name in ('package.json', 'request-contract.json', 'execution-plan.json'):
        validate_execution_artifact(prepared, name, documents[name])


def publish_compilation(root: Path, compiled: Compilation, *, parent: dict | None=None, current_task: dict | None=None) -> dict:
    """Publish one already compiled staging tree as the single formal run.

    This is the publication half of prepare. Retarget and other high-level
    operations can compile once, inspect the result, and publish that same
    immutable staging tree instead of performing a second runtime resolution.
    """
    import work_ledger
    root=c._root(root)
    if not compiled.report['publishable']:raise CompilationError(compiled.report)
    if (compiled.directory is None or compiled.prepared is None or compiled.consumer is None
            or compiled.identity is None or compiled.artifacts is None):
        raise ProductionError('ARTIFACT_PUBLISH_FAILED','No complete compiled staging tree is available for publication.',phase='publication')
    if current_task is None:current_task=work_ledger.require_open(root)
    directory=compiled.directory;prepared=compiled.prepared;run=compiled.identity
    target=c.local(root, 'production/runs/'+run, exists=False)
    try:
        with stage('artifact-publication'), store.transaction(root):
            active=work_ledger.require_open(root)
            if active['task_id']!=prepared['task']['task_id']:
                # A derived task exists only in the staging of this preparation, so only a Studio task file is named.
                live=dependency_space(prepared['task_path'])=='studio'
                raise ProductionError('TASK_CHANGED','The task names another work task than the open one.',
                    phase='publication',file=prepared['task_path'] if live else None,pointer='$.task_id' if live else None,
                    expected=active['task_id'],actual=prepared['task']['task_id'],
                    required_action='Show the open work task with work_ledger.py show and prepare a task that names its task_id, '
                                    'given as expected. Reopen a run of other work with draft-inputs --from-run and --task-id or --new-task.')
            if active['task_id']!=current_task['task_id']:
                raise ProductionError('TASK_CHANGED','The open work task changed during preparation.',
                    phase='publication',expected=current_task['task_id'],actual=active['task_id'],
                    required_action='Run the same preparing command again. The task names the work task that is open now, '
                                    'given as actual; expected is the one that was open when this preparation started.')
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
                    fixed_runtime.publish(root,directory/'runtime',prepared['runtime_snapshot'],read=compiled.runtime_read)
                fixed_runtime.require_current(root,prepared['runtime_snapshot'],run=run)
            from studio_reference import ReferenceReads, validate_source
            reference_reads = ReferenceReads()
            for source in prepared.get('studio_reference_sources', []):
                validate_source(source, read=reference_reads.studio(Path(source['studio_root'])))
            write_compiled(compiled,media_root=target)
            prepared['envelope_sha256']=c.content_id(prepared)
            compiled.artifacts.write('prepared.json',c.encoded(prepared))
            compiled.artifacts.write('consumer.json',c.encoded(compiled.consumer))
            manifest=write_manifest(directory,compiled.artifacts)
            manifest_sha256=c.content_id(manifest)
            verify_publication(directory,expected=manifest_sha256)
            target.parent.mkdir(parents=True,exist_ok=True)
            if target.exists():
                raise ProductionError('OUTPUT_ALREADY_EXISTS','A run already occupies the publication destination.',phase='publication',file=str(target),
                    required_action='Continue with the run that holds this ID. status reports it among runs, or among '
                                    'unregistered_publications when recover-publication --run still has to register it.')
            if isinstance(compiled.artifacts,StagedArtifacts):
                compiled.artifacts.flush_files()
                compiled.artifacts.flush_directories(controls=PUBLICATION_CONTROLS)
            c.publish_directory(directory,target)
            # The run directory is in place; only its registration is left when this flush fails.
            c.flush_published(target,continuation='Register the published run with recover-publication --run '+run+'.')
            if ((prepared.get('authored_revision') or {}).get('state')!='draft' and
                prepared['task'].get('authority') and store.read_authority(root,prepared['task']['task_id'],required=False) is None):
                store.import_authority(root,prepared['task']['authority'],initial=True)
            read_manifest(target,expected=manifest_sha256)
            ArtifactSet(target,manifest['files']).require_membership(controls=PUBLICATION_CONTROLS)
            store.register_run(root,run,prepared,target)
        warnings=[]
        try:
            recorded = work_ledger.record_prepared(root, prepared['task']['task_id'], run)
            if recorded.get('projection_warning'):
                warnings.append(recorded['projection_warning'])
        except (ValueError,OSError) as exc:
            warnings.append({'code':'WORK_PROJECTION_FAILED','message':str(exc),'formal_run_retained':True})
        operation=current()
        if operation:
            operation.link(run=run,task=prepared['task']['task_id'])
        return _preparation_result(run,target,prepared['input_sha256'],package=bool(compiled.package),
            request_preview=compiled.report['request_preview'],execution_plan=compiled.execution_plan,
            warnings=warnings,created=True)
    except BaseException:
        if directory.exists():
            try:c.atomic(directory/'failure.json',c.encoded({'state':'publication-interrupted','target':str(target)}))
            except OSError:pass
        raise


def _preparation_result(run:str,directory:Path,input_sha256:str,*,package:bool,request_preview:Any,
                        execution_plan:dict,warnings:list,created:bool)->dict:
    """What a preparation returns for its formal run; formal_run_created says whether this call published it."""
    return {'ok':True,'run':run,'input_sha256':input_sha256,'consumer':str(directory/'consumer.json'),
            'package':str(directory/'package.json') if package else None,'request_preview':request_preview,
            'execution_plan':execution_plan,'warnings':warnings,'formal_run_created':created}


def published_preparation(root: Path, run: str) -> dict:
    """The preparation result of a registered run, read from its verified publication; it creates no run."""
    import production_workflow as workflow
    from owned_json import mutable
    root=c._root(root)
    loaded=workflow.read_run(root,run)
    plan=mutable(loaded.artifacts['execution-plan.json'])
    rendered=loaded.artifacts.get('request-contract.json')
    return _preparation_result(run,c.local(root,loaded.registered['directory']),loaded.prepared['input_sha256'],
        package='package.json' in loaded.artifacts,
        request_preview=mutable(rendered['request']) if rendered is not None else plan.get('request'),
        execution_plan=plan,warnings=[],created=False)



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
                              phase='cleanup', file=str(path), actual=type(exc).__name__,
                              required_action='Check open handles and permissions on this path, then run staging-cleanup again; '
                                              'its listing shows what remains.') from exc


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


def _staging_parent(root: Path) -> Path:
    try:
        return c.local(root, 'production/staging', exists=False)
    except (OSError, ValueError) as exc:
        raise ProductionError('STAGING_CLEANUP_REFUSED', 'Staging is outside the owned studio tree or contains a symbolic link.',
                              phase='cleanup', file=str(root/'production/staging'),
                              required_action='Replace the symbolic link or redirected directory on the path to production/staging '
                                              'with a regular directory inside the studio, then run the command again.') from exc


def inspect_staging(root: Path) -> list[dict]:
    """Inspect owned staging without auditing journals or published runs."""
    root = Path(root).absolute()
    return _staging_items(root, _staging_parent(root), None, False)


def staging_cleanup(root: Path, *, operation_id: str | None = None, apply: bool = False) -> dict:
    """Inspect or remove one dead operation's unreferenced staging, dispatch journals and publications.

    The dry run only observes. Applying cleanup checks ownership, live process
    state and formal references in the store transaction used by publication,
    immediately before removal. A symlink is never traversed. A journal named
    by a claim is never listed.
    """
    root = Path(root).absolute()
    parent = _staging_parent(root)
    if apply and not operation_id:
        raise ProductionError('INPUT_CONSISTENCY_ERROR', 'Applying staging cleanup requires --operation.',
                              phase='cleanup', required_action='Inspect the dry run and select its exact owner operation ID.')
    from contextlib import nullcontext
    with (store.transaction(root) if apply else nullcontext()):
        rows = _staging_items(root, parent, operation_id, apply)
        journals = _journal_items(root, operation_id, apply)
        publications = _publication_items(root, operation_id, apply)
    deleted = sum(1 for item in rows + journals + publications if item.get('deleted'))
    return {'ok': True, 'apply': apply, 'items': rows, 'journals': journals, 'publications': publications,
            'deleted': deleted, 'external_effect': False}


def prepare_task(root: Path, task_path: str, *, parent: dict | None=None, identity: str | None=None,
                 runtime_inputs=None) -> dict:
    import work_ledger
    current_task=work_ledger.require_open(root)
    compiled=compile_task(root,task_path,persist=True,identity=identity,runtime_inputs=runtime_inputs)
    if parent is None:
        from production_inputs import export_parent
        parent=export_parent(root,task_path,compiled)
    return publish_compilation(root,compiled,parent=parent,current_task=current_task)


def inspect_publication(root: Path, run: str) -> tuple[Path, dict, dict]:
    """Verify an unregistered completion without changing authority or live sources."""
    import production_workflow as workflow
    run = workflow.run_identifier(run)
    directory = c.local(root, 'production/runs/' + run)
    acquired = acquire_publication(directory, documents={'prepared.json', 'consumer.json'})
    manifest = acquired.manifest
    ArtifactSet(directory, manifest['files']).require_membership(controls=PUBLICATION_CONTROLS)
    prepared = acquired.documents['prepared.json']
    consumer = acquired.documents['consumer.json']
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
            workflow.read_run(root, run)
        else:
            directory, prepared, _ = inspect_publication(root, run)
            store.register_run(root, run, prepared, directory)
        return {'ok': True, 'run': run, 'recovered': not bool(existing), 'external_effect': False,
                'authority_restored': False, 'next_action': 'status'}
