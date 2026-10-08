"""Derive a fresh input from a prepared run, independently of captured images.

Changes address compiler-declared fields. Unchanged sources and the fixed pack
runtime retain their identity. A changed request never inherits authorization,
claims, reviews or selections from its parent. A change made after looking at
an image names that candidate and its review as the basis.
"""
from __future__ import annotations

import copy
from pathlib import Path, PurePosixPath
from typing import Any, Sequence

import execution_contract as c
import production_store as store
from pack_manager import generate_uuid7
from production_diagnostics import ProductionError, CompilationError, same_json

# Every mapping is an authored input, never an arbitrary internal JSON pointer.
DOCUMENT_FIELDS = {
    'production-spec': 'production_spec', 'plot': 'plot', 'retrieval-record': 'retrieval_record',
    'creative-intent': 'creative_intent', 'request-validation': 'request_validation',
    'visual-continuity': 'visual_continuity', 'references': 'references',
    'state-lineage': 'state_lineage', 'state-snapshot': 'state_snapshot',
    'negative-provenance': 'negative_provenance'}
TASK_FIELDS = {
    'direction': 'direction', 'criteria': 'criteria', 'source-materials': 'sources',
    'route-reading': 'route_reading', 'scene-materials': 'scene_materials',
    'world-views': 'world_views', 'moment-views': 'moment_views', 'features': 'features'}
# A target is chosen by retargeting with a reassessed task, never by a field map.
TARGET_KEYS = {'model', 'service', 'offering', 'target', 'target-model'}
RETARGET = 'python scripts/production_workflow.py retarget --root {root} --from {run} --task TASK_FILE --reason REASON --prepare'


def _redirect_source(task: dict, old: str | None, new: str) -> None:
    """A declared replacement also replaces that input's named source role."""
    if old is not None:
        for source in task['sources']:
            if source['path'] == old:
                source['path'] = new


def _captured(directory: Path, prepared: dict, path: str) -> bytes:
    matches = [d for d in prepared['dependencies'] if d['space'] in {'studio', 'task-source'} and d['path'] == path]
    if len(matches) != 1:
        raise ProductionError('EVIDENCE_SNAPSHOT_MISSING', 'The source run does not own this declared input.', phase='variation', file=path)
    return c.object_read(directory, matches[0]['sha256'])


def _document(root: Path, field: str, value: dict) -> tuple[bytes, Any]:
    """Read one studio document named by a field's {"path": ...} value."""
    try:
        raw = store.stable_bytes(root, value['path'])
        return raw, c.decode(raw)
    except (OSError, ValueError) as exc:
        raise ProductionError('CHANGES_PATH_INVALID', 'The named document is missing or is not readable JSON.',
            phase='variation', file=value['path'], pointer='$.changes.' + field + '.path',
            required_action='Name an existing studio-relative file prepared for this field.') from exc


def _target_change(root: Path, run: str, pointer: str, message: str) -> ProductionError:
    studio = f'"{root}"' if ' ' in str(root) else str(root)
    return ProductionError('TARGET_CHANGE_REQUIRED', message, phase='variation', pointer=pointer,
        required_action='Retarget with a reassessed task: ' + RETARGET.format(root=studio, run=run))


def _unchanged(root: Path, run: str, prepared: dict, replaced: set[str], dependencies: list[dict]) -> None:
    import production_workflow as workflow
    retained = {(d['space'], d['path']) for d in dependencies}
    for source in prepared['dependencies']:
        if ((source['space'], source['path']) not in retained
                or source['space'] not in {'studio', 'skill'} or source['path'] in replaced):
            continue
        try:
            actual = workflow.current_sha256(root, source)
        except (ValueError, OSError):
            actual = None
        if actual != source.get('selection_sha256', source['sha256']) and source['space'] == 'skill':
            raise workflow.freshness_error(source, actual, run=run)
        if actual != source.get('selection_sha256', source['sha256']):
            raise ProductionError('SOURCE_CHANGED', 'An unchanged source differs from the prepared input.',
                phase='variation', file=source['path'], expected=source['sha256'], actual=actual,
                required_action='Review the source and replace it through its declared field, or restore the pinned contents.')


def _basis(rows: list[dict], run: str, candidates: Sequence[str]) -> list[dict]:
    """The captured candidates, and their latest reviews, that a change answers."""
    import production_workflow as workflow
    basis = []
    for candidate in dict.fromkeys(candidates):
        try:
            workflow.find(rows, 'candidate', candidate)
        except ValueError as exc:
            raise ProductionError('CANDIDATE_NOT_FOUND', 'The source run captured no candidate with this ID.',
                phase='variation', run=run, actual=candidate,
                required_action='Name a candidate of the source run; status lists its candidates.') from exc
        try:
            review = workflow.latest_review(rows, candidate)['sha256']
        except ValueError:
            review = None
        basis.append({'candidate': candidate, 'review': review})
    return basis


def derive(root: Path, run: str, *, changes_file: str | None = None, prepare: bool = False,
           candidates: Sequence[str] = ()) -> dict:
    import production_workflow as workflow
    import production_compiler as compiler
    import runtime_snapshot
    from state_protocol import validate_against_schema

    root = c._root(root)
    directory, prepared, _, rows = workflow.load_run(root, run)
    if prepared['task']['execution'] != 'dispatcher':
        raise ProductionError('VARIANT_NOT_APPLICABLE', 'Input derivation needs a compiled model request.', phase='variation')
    runtime_warnings = runtime_snapshot.require_current(root, prepared['runtime_snapshot'], run=run)
    basis = _basis(rows, run, candidates)
    plan = c.load(directory / 'execution-plan.json')
    task = copy.deepcopy(prepared['task'])
    task.pop('execution_decisions', None)
    fields = plan['mutable_fields']
    changes = {}
    reason = 'Intentional additional run of the same fixed input.'
    if changes_file is not None:
        try:
            selected = c.read_json_input(changes_file, root=root)
            workflow.schema_check(selected, 'changes')
        except (OSError, ValueError) as exc:
            raise ProductionError('INPUT_SCHEMA_INVALID', str(exc), phase='variation', file=str(changes_file),
                required_action='Supply {"changes": {FIELD_ID: value}, "reason": text} as UTF-8 JSON.') from exc
        changes, reason = selected['changes'], selected['reason']
    generation = task.get('generation')
    parameters = c.decode(_captured(directory,prepared,generation['parameters'])) if generation is not None else {}
    spec = c.decode(_captured(directory,prepared,generation['production_spec'])) if generation is not None else {}
    original_model = copy.deepcopy(spec.get('target_model'))
    replacements: dict[str, bytes] = {}
    replaced: set[str] = set()
    difference = []
    checks: set[str] = set()
    problems: list[dict] = []

    def no_op(field: str, message: str) -> ProductionError:
        return ProductionError('CHANGES_NO_OP', message, phase='variation', pointer='$.changes.' + field,
                               required_action='Remove the unchanged field, or use repeat for another run of the same input.')

    def change_file(field: str, name: str, raw: bytes, before: Any, after: Any) -> None:
        if same_json(before, after):
            raise no_op(field, 'The declared field has not changed.')
        old = task['delivery']['path'] if field == 'prompt' else generation.get(name)
        if old is not None:
            replaced.add(old)
        replacements[name] = raw

    def apply(field: str, value: Any) -> Any:
        if field not in fields:
            if field in TARGET_KEYS:
                raise _target_change(root, run, '$.changes.' + field, 'A model or service is selected by retargeting, not by a field change.')
            raise ProductionError('CHANGES_UNKNOWN_FIELD', 'This field is not declared mutable by the compiler.',
                phase='variation', pointer='$.changes.' + field, actual=field, expected=sorted(fields))
        errors = validate_against_schema(value, fields[field]['schema'])
        if errors:
            raise ProductionError('CHANGES_TYPE_INVALID', '; '.join(errors), phase='variation', pointer='$.changes.' + field)
        checks.update(fields[field]['checks'])
        if field in TASK_FIELDS:
            name = TASK_FIELDS[field]
            before = copy.deepcopy(task.get(name))
            if same_json(before, value):
                raise no_op(field, 'The authored task field is unchanged.')
            if field == 'route-reading':
                replaced.add(task['route_reading'])
            elif field == 'source-materials':
                replaced.update(source['path'] for source in task['sources'])
            task[name] = copy.deepcopy(value)
            return before
        if field == 'prompt':
            before = _captured(directory, prepared, task['delivery']['path']).decode('utf-8')
            change_file(field, 'prompt', value.encode('utf-8'), before, value)
            return before
        if field == 'upscale-input':
            before = c.decode(_captured(directory,prepared,task['delivery']['path']))
            raw, after = _document(root, field, value)
            if same_json(before, after):
                raise no_op(field, 'The upscale declaration is unchanged.')
            if after.get('model') != before['model']:
                raise _target_change(root, run, '$.changes.upscale-input.path', 'Another upscale target needs retargeting with a reassessed task.')
            replaced.add(task['delivery']['path']);replacements['upscale-input']=raw
            if after.get('source',{}).get('path') != before['source']['path']:
                replaced.add(before['source']['path'])
                for source in task['sources']:
                    if source['path'] == before['source']['path']:source['path'] = after['source']['path']
            return c.content_id(before)
        if field == 'negative':
            before = _captured(directory, prepared, generation['negative']).decode('utf-8') if generation.get('negative') else ''
            change_file(field, 'negative', value.encode('utf-8'), before, value)
            return before
        if field.startswith('parameter:'):
            key = field.split(':', 1)[1]
            from render_contract_lib import _get, _put
            present, before = _get(parameters, key)
            if present and same_json(before, value):
                raise no_op(field, 'The parameter is unchanged.')
            _put(parameters, key, value)
            replaced.add(generation['parameters'])
            replacements['parameters'] = c.encoded(parameters)
            return before
        if field in {'seed', 'count'}:
            before = generation[field]
            if same_json(before, value):
                raise no_op(field, 'The execution quantity is unchanged.')
            generation[field] = copy.deepcopy(value)
            return before
        if field == 'execution-mode':
            before = spec['render_intent']['execution_mode']
            if same_json(before, value):
                raise no_op(field, 'The execution mode is unchanged.')
            spec['render_intent']['execution_mode'] = value
            replaced.add(generation['production_spec'])
            replacements['production_spec'] = c.encoded(spec)
            return before
        if field == 'recording':
            before = copy.deepcopy(task['recording'])
            if same_json(before, value):
                raise no_op(field, 'The recording contract is unchanged.')
            task['recording'] = copy.deepcopy(value)
            return before
        if field in DOCUMENT_FIELDS:
            name = DOCUMENT_FIELDS[field]
            old = generation.get(name)
            previous = c.decode(_captured(directory, prepared, old)) if old else None
            if value is None:
                if old is None:
                    raise no_op(field, 'No input is selected for this field.')
                generation.pop(name)
                replaced.add(old)
                return c.content_id(previous)
            raw, document = _document(root, field, value)
            # Relative locators inside a document resolve from its directory, so
            # equal JSON elsewhere may still name other media.
            if old is not None and same_json(previous, document) and PurePosixPath(value['path']).parent == PurePosixPath(old).parent:
                raise no_op(field, 'The named document has the same JSON content in the same directory.')
            # Referencing the actual supplied document preserves relative
            # media locators. The compiler snapshots the full dependency set.
            generation[name] = value['path']
            _redirect_source(task, old, value['path'])
            if old:
                replaced.add(old)
            if field == 'production-spec' and document.get('target_model') != original_model:
                raise _target_change(root, run, '$.changes.production-spec.path', 'A model change needs explicit retargeting and new guidance.')
            return c.content_id(previous) if old else None
        raise ProductionError('CONTROL_NOT_AVAILABLE', 'No input binding implements the declared field.', phase='variation',
                              pointer='$.changes.' + field, actual=field)

    for field, value in changes.items():
        try:
            before = apply(field, value)
        except ProductionError as exc:
            problems.append(exc.diagnostic.as_dict())
            continue
        difference.append({'field': field, 'before': before, 'after': copy.deepcopy(value)})
    if 'production-spec' in changes and 'execution-mode' in changes:
        problems.append(ProductionError('CHANGES_CONFLICT', 'Choose a complete specification or its execution-mode field, not both.',
                                        phase='variation', pointer='$.changes').diagnostic.as_dict())
    if problems:
        first = problems[0]
        details = {key: value for key, value in first.items()
                   if key not in {'code', 'severity', 'phase', 'file', 'pointer', 'message', 'required_action', 'blocked_checks'}}
        raise ProductionError(first['code'], first['message'], phase='variation', file=first['file'], pointer=first['pointer'],
                              required_action=first['required_action'], **{**details, 'diagnostics': problems})
    # Generation validation remains the authority for retrieval context. A
    # prompt edit requires an explicitly re-assessed retrieval record. Derivation
    # does not fabricate new lookups or silently mark an old lookup applicable.
    # The derived task and every replaced input belong to the new run. They are
    # written into its staging directory and published inside the run.
    identity = generate_uuid7()
    prefix = compiler.run_inputs(identity)
    derived: dict[str, bytes] = {}
    for name, raw in replacements.items():
        file = f'{name}.txt' if name in {'prompt', 'negative'} else f'{name}.json'
        derived[file] = raw
        path = f'{prefix}/{file}'
        if name in {'prompt','upscale-input'}:
            _redirect_source(task, task['delivery']['path'], path)
            task['delivery']['path'] = path
        else:
            _redirect_source(task, generation.get(name), path)
            generation[name] = path
    task_path = prefix + '/task.json'
    derived['task.json'] = c.encoded(task)
    if changes_file is not None:
        derived['requested-changes.json'] = c.encoded({'changes': changes, 'reason': reason})
    parent = {'run': run, 'input_sha256': prepared['input_sha256'], 'request_sha256': plan['request_sha256'],
              'kind': 'variant' if changes_file is not None else 'repeat', 'reason': reason, 'changes': difference,
              'basis': basis}
    # Compile once, compare only dependencies the child actually retains, and
    # publish that exact result. Removed references must not remain live pins.
    # A repeat mismatch is detected before any formal run can be registered.
    import work_ledger
    import shutil
    current_task = work_ledger.require_open(root) if prepare else None
    compiled = compiler.compile_task(root, task_path, persist=prepare, identity=identity,
                                     runtime_snapshot=prepared['runtime_snapshot'], derived=derived)
    if not compiled.report['publishable']:
        raise CompilationError(compiled.report)
    try:
        _unchanged(root, run, prepared, replaced, compiled.prepared['dependencies'])
        if changes_file is None and compiled.prepared['input_sha256'] != prepared['input_sha256']:
            raise ProductionError('REPEAT_INPUT_MISMATCH',
                'Repeated preparation did not retain the fixed input identity.', phase='variation')
        if prepare:
            result = compiler.publish_compilation(root, compiled, parent=parent, current_task=current_task)
        else:
            # A check creates no run, so its plan names none.
            compiled.report['execution_plan']['run'] = None
            result = {**compiled.report, 'formal_run_created': False}
    finally:
        if compiled.directory is not None and compiled.directory.exists():
            shutil.rmtree(compiled.directory)
    result['derivation'] = parent
    result['runtime_warnings'] = runtime_warnings
    result['revalidated_checks' if prepare else 'required_checks']=sorted(checks)
    result.update(external_effect=False, authorization_inherited=False, candidate_required=False)
    return result


def retarget(root: Path, run: str, task_file: str, *, reason: str, prepare: bool = False) -> dict:
    """Recompile a dispatcher task against a reassessed target or the current runtime.

    Generation and upscale are both target-bearing dispatcher operations. The
    shared compiler is the authority for resolving the new model/service and
    all target-dependent contracts. The same target is accepted when the
    current pack runtime differs from the parent's fixed runtime. The parent
    contributes lineage only.
    """
    import production_workflow as workflow
    import production_compiler as compiler
    import work_ledger
    import shutil

    root = c._root(root)
    c.text(reason, 'retarget reason')
    directory, previous, _, _ = workflow.load_run(root, run)
    if previous['task']['execution'] != 'dispatcher':
        raise ProductionError('RETARGET_NOT_APPLICABLE', 'Retargeting starts from a compiled model request.', phase='retarget')
    task = c.decode(store.stable_bytes(root, task_file))
    workflow.validate_task(task)
    if task['execution'] != 'dispatcher':
        raise ProductionError('RETARGET_NOT_APPLICABLE', 'The reassessed task must declare a model request.', phase='retarget')
    for field in ('task_id', 'production_id'):
        if task[field] != previous['task'][field]:
            raise ProductionError('RETARGET_SCOPE_MISMATCH', 'Retargeting retains the work task and production series.',
                phase='retarget', pointer='$.' + field, expected=previous['task'][field], actual=task[field])
    current_task=work_ledger.require_open(root) if prepare else None
    compiled=compiler.compile_task(root,task_file,persist=prepare)
    if not compiled.report['publishable']:
        if prepare:raise CompilationError(compiled.report)
        return compiled.report
    before = c.load(directory / 'execution-plan.json')
    new_plan=compiled.execution_plan
    old_target = {'model': before['model'], 'service': before['service'], 'route': previous['task']['route']}
    new_target = {'model': new_plan['model'], 'service': new_plan['service'], 'route': task['route']}
    changes = []
    if not same_json(old_target, new_target):
        changes.append({'field': 'target', 'before': old_target, 'after': new_target})
    old_runtime = previous['runtime_snapshot']['sha256']
    new_runtime = compiled.prepared['runtime_snapshot']['sha256']
    if old_runtime != new_runtime:
        changes.append({'field': 'runtime', 'before': old_runtime, 'after': new_runtime})
    if not changes:
        if compiled.directory is not None:shutil.rmtree(compiled.directory,ignore_errors=True)
        raise ProductionError('RETARGET_NO_OP', 'Neither the target nor the pack runtime has changed.', phase='retarget',
            required_action='Use variant for same-target input changes, repeat for another run, or resume for recovery.')
    parent = {'run': run, 'input_sha256': previous['input_sha256'], 'request_sha256': before['request_sha256'],
              'kind': 'retarget', 'reason': reason, 'changes': changes, 'basis': []}
    if prepare:
        result=compiler.publish_compilation(root,compiled,parent=parent,current_task=current_task)
    else:
        result=compiled.report
        if compiled.directory is not None:shutil.rmtree(compiled.directory,ignore_errors=True)
    checks=['execution-profile','request-validation','recording','request','source-applicability']
    if task['route']=='generation':checks += ['target-guidance','retrieval','render-intent','reference-transport']
    elif task['route']=='upscale':checks += ['upscale-source','scale-factor','render-intent','transport']
    result.update(derivation=parent, external_effect=False, authorization_inherited=False,
                  candidate_required=False, required_checks=sorted(set(checks)))
    return result


HELP = {
    'variant': 'Prepare a new input from a run with declared field changes; nothing is claimed or sent.',
    'repeat': 'Prepare another run of a run\'s unchanged input, with its own claim and authorization.',
    'retarget': 'Prepare a run from another one against a reassessed target or the current pack runtime.'}


def add_arguments(subparsers) -> None:
    for name in ('variant', 'repeat', 'retarget'):
        parser = subparsers.add_parser(name, help=HELP[name], description=HELP[name])
        parser.add_argument('--root', type=Path, required=True, help='The studio directory that owns the run.')
        parser.add_argument('--from', dest='source_run', required=True, metavar='RUN', help='The prepared run to derive from.')
        parser.add_argument('--prepare', action='store_true', help='Publish the new run; without it the result is a check only.')
        if name == 'variant':
            parser.add_argument('--changes-file', required=True, metavar='FILE',
                                help='JSON {"changes": {FIELD_ID: value}, "reason": text}, studio-relative, absolute, or - for stdin.')
            parser.add_argument('--candidate', action='append', default=[], metavar='CANDIDATE_ID',
                                help='A captured candidate of the source run that this change answers; repeat for each.')
        elif name == 'retarget':
            parser.add_argument('--task', required=True, help='Complete reassessed task with the new model, service, guidance and validation inputs.')
            parser.add_argument('--reason', required=True, help='Authored reason for changing the target or adopting the current runtime.')
            from pack_runtime_cli import add_pack_runtime_arguments
            add_pack_runtime_arguments(parser)


def command(args, parser):
    if args.command == 'retarget':
        return retarget(args.root, args.source_run, args.task, reason=args.reason, prepare=args.prepare)
    return derive(args.root, args.source_run, changes_file=getattr(args, 'changes_file', None), prepare=args.prepare,
                  candidates=getattr(args, 'candidate', []))
