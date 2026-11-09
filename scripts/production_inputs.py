"""Resolve authored choices into complete, atomically published production inputs.

The author supplies meaning and approval. This module preserves those choices
and delegates each input contract to its owning builder.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any
from contextlib import contextmanager

import execution_contract as c
import execution_routes
from input_evidence import InputEvidence
import route_reading
import production_input_adapters as adapters
import production_authoring as authoring
import production_target
from production_diagnostics import ProductionError, from_exception

ROOT = Path(__file__).resolve().parents[1]
COMMANDS = frozenset({'inspect-inputs', 'draft-inputs', 'build-inputs'})


def _task(root: Path, path: str | None, reader: InputEvidence, *,
          from_run: str | None = None, read_run=None) -> tuple[dict, dict, dict, dict | None]:
    if (path is None) == (from_run is None):
        raise ValueError('select one task file or source run')
    saved = _source_run(root, from_run, read_run=read_run) if from_run is not None else None
    if saved is None:
        ref = reader.select(path)
        value = reader.json(ref)
    else:
        value = copy.deepcopy(saved['task'])
        ref = {'run': from_run, 'input_sha256': saved['input_sha256']}
    if not isinstance(value, dict):
        raise ValueError('production task must be an object')
    for name in ('task_id', 'route'):
        c.text(value.get(name), 'task.' + name)
    features = value.get('features')
    if not isinstance(features, list):
        raise ValueError('task.features must be an explicit array')
    route = execution_routes.resolve(value['route'], features, execution=value['execution'],
        operation='author' if value.get('execution')=='authored' else 'prepare')
    return value, route, ref, saved


def _source_run(root: Path, selected: str | None, *, read_run=None) -> dict | None:
    if selected is None:
        return None
    import production_workflow as workflow
    loaded = read_run(selected) if read_run is not None else workflow.read_run(root, selected)
    prepared = loaded.prepared
    diagnostics = workflow.freshness_diagnostics(root, selected, loaded=loaded)
    return {'run': selected, 'input_sha256': prepared['input_sha256'],
            'task_path': prepared['task_path'], 'task': prepared['task'],
            'route_reading': copy.deepcopy(prepared.get('route_reading')),
            'freshness': {'current': not diagnostics, 'diagnostics': diagnostics},
            'assessment_required': ['Check copied applications against the current task and changed dependencies.']}


def _sources(root: Path, task: dict, reader: InputEvidence) -> list[dict]:
    output = []
    for source in task.get('sources', []):
        if not isinstance(source, dict):
            raise ValueError('task source must be a declared object')
        path = c.text(source.get('path'), 'source path')
        local = c.local(root, path, exists=False)
        item = {key: copy.deepcopy(source.get(key)) for key in
                ('id', 'path', 'role', 'disposition', 'locator')}
        item['present'] = local.is_file()
        if item['present']:
            item['file'] = reader.select(path)
        output.append(item)
    return output


def _identity_view(root: Path, task: dict, reader: InputEvidence, *, saved: dict | None = None,
                   files: dict[str, bytes] | None = None, out_dir: str | None = None) -> dict | None:
    """Expose original identity evidence beside choices, including saved runs.

    Authoring can be incomplete. Return its precise gaps without certifying
    actual delivery or blocking access to the editable choices themselves.
    """
    import production_identity
    import production_store
    from production_diagnostics import from_exception
    captured = {}
    stored = {}
    directory = None
    if saved is not None:
        import production_workflow
        directory, prepared, _, _ = production_workflow.read_run(root, saved['run'])
        stored = {item['path']: item['sha256'] for item in prepared['dependencies']
                  if item['space'] in authoring.AUTHORING_SPACES}
        stored.update({item['path']: item['sha256']
                       for item in (prepared.get('identity_coverage') or {}).get('sources', [])})
    prefix = out_dir.rstrip('/') + '/' if out_dir is not None else None
    def read(path):
        if path in captured:
            return captured[path]
        if prefix and path.startswith(prefix) and path[len(prefix):] in (files or {}):
            raw = files[path[len(prefix):]]
        elif path in stored:
            raw = c.object_read(directory, stored[path])
        elif Path(path).is_absolute():
            local = Path(path)
            raw = production_store.stable_bytes(local.parent, local.name)
        else:
            raw = reader.read(reader.select(path))
        captured[path] = raw
        return raw
    try:
        value = production_identity.inspect(task, read)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        return {'status': 'unresolved', 'request_verified': False,
                'diagnostics': [from_exception(exc, phase='identity-coverage')]}
    if (value['sources'] or value['required_subject_ids'] or value['requires_identity_source']
            or value['whole_reviews']):
        return value
    return None


def _identity_gaps(value: dict | None) -> list[dict]:
    if value is None:
        return []
    keys = ('uncovered', 'missing_carriers', 'missing_subject_sources', 'missing_whole_reviews',
            'unknown_subject_ids', 'requires_identity_source', 'diagnostics')
    return [{'field': 'authoring.task.sources' if key in {'missing_subject_sources', 'requires_identity_source'}
                     else 'authoring.task.criteria', 'code': 'identity-' + key.replace('_', '-'),
             'details': value[key]} for key in keys if value.get(key)]


def inspect_inputs(root: Path, task_path: str | None = None, *, from_run: str | None = None) -> dict:
    """Read declarations and saved records without issuing keys or permissions."""
    if task_path is None and from_run is None:
        import production_authoring_state
        return production_authoring_state.inspect(root)
    reader = InputEvidence(root)
    task, route, ref, saved = _task(root, task_path, reader, from_run=from_run)
    sources = _sources(root, task, reader)
    import craft_consultation
    craft = (craft_consultation.navigation(root, task_path, include_scope=task.get('artifact') in {'image', 'video'})
             if task_path is not None else {'next_actions': [], 'source_run': from_run})
    identity = _identity_view(root, task, reader, saved=saved)
    return {'state': 'inspection', 'task': ref,
            'route': {'id': task['route'], 'features': route['features'],
                      'reads': route['reads']},
            'source_run': saved, 'task_content': task, 'sources': sources,
            'candidates': adapters.inventory(root, task),
            'craft_lookup': craft,
            'authority': adapters.authority(root, task, saved),
            'required_choices': ['reading', *(['validation'] if adapters.validation_required(task) else [])],
            'choice_templates': {'visual': adapters.visual_template(task),
                                 'validation': adapters.validation_template(task)},
            **({'identity_coverage': identity} if identity is not None else {}),
            'judgments': 'Establish the intended result from the requested outcome and applicable original '
                         'sources, carrying adopted definitions and current state into later requests at '
                         'their authored meaning, scope and importance. Include necessary conditions of '
                         'use and the preservation required by authorized local changes. Set hard criteria '
                         'for required outcomes, including necessary source-based identity obligations, '
                         'and advisory criteria for nonblocking considerations and optional refinements. '
                         'Describe the properties, '
                         'relationships and actions to depict, and choose the subject, reference and '
                         'production treatments that realize them. Keep agent-selected staging, format '
                         'and incidental detail as choices within the available freedom, with coherent '
                         'alternatives able to satisfy the same criteria. Complete route applications '
                         'and required evidence, settle material gaps in their owning fields, and keep '
                         'technical provenance in its existing records.',
            'external_effect': False}


def draft_choices(task: dict) -> dict:
    applications = {'reading_key': None}
    # A null visual or validation choice builds no record here: the Generation
    # Package builder takes continuity decisions and derives request validation.
    return {'target': None, 'reading': applications, 'visual': None,
            'validation': adapters.validation_template(task) if adapters.validation_required(task) else None,
            'task_changes': {},
            'external': ({'image_input': task['image_input']}
                         if task.get('execution') == 'external' and task.get('image_input') else None)}


def _missing(choices: dict) -> list[dict]:
    """Name unanswered fields while preserving valid explicit null selectors."""
    _validate_choices(choices)
    unresolved = []
    reading = choices['reading']
    if reading is None:
        unresolved.append({'field': 'reading', 'code': 'reading-required'})
    elif not isinstance(reading, dict):
        raise ValueError('reading choices must be an object')
    else:
        if not reading.get('reading_key'):
            unresolved.append({'field': 'reading.reading_key', 'code': 'reading-required'})
    for field in ('visual', 'validation'):
        if choices[field] is not None and not isinstance(choices[field], dict):
            raise ValueError(field + ' choices must be an object or null')
    if isinstance(choices['visual'], dict):
        subjects = choices['visual'].get('subjects')
        if subjects is not None and not isinstance(subjects, dict):
            raise ValueError('visual.subjects must be an explicit subject map')
        for identifier, subject in (subjects or {}).items():
            if isinstance(subject, dict) and subject.get('continuity') is None:
                unresolved.append({'field': 'visual.subjects.' + identifier + '.continuity',
                                   'code': 'continuity-choice-required'})
    unresolved.extend(adapters.unresolved_choices(choices))
    return unresolved


def _unresolved(choices: dict, task: dict) -> list[dict]:
    unresolved = _missing(choices)
    unresolved.extend(production_target.unresolved(choices['target'], task))
    if choices['validation'] is None and adapters.validation_required(task):
        unresolved.append({'field': 'validation', 'code': 'selection-required'})
    unresolved.extend(authoring.unresolved(choices.get('authoring'), task))
    if choices['external'] is not None:
        import production_external_inputs
        unresolved.extend(production_external_inputs.unresolved(choices['external']))
    return unresolved


def _select_target(choices: dict, *, model: str | None, service: str | None) -> None:
    """Apply explicit target flags without changing the retained artistic choices."""
    if model is None and service is None:
        return
    selected = copy.deepcopy(choices.get('target'))
    if model is not None:
        previous = selected or {}
        actual = (previous.get('model') or {}).get('target', {}) if previous.get('kind') == 'external' else previous
        selected = {'kind': 'catalog', 'model': model, 'service': actual.get('service'),
                    **{key: copy.deepcopy(previous[key]) for key in
                       production_target.AUTHORED_FIELDS | production_target.COMMON_FIELDS if key in previous}}
        if actual.get('operation') is not None:
            selected['operation'] = actual['operation']
    if selected is None:
        selected = {'kind': 'catalog', 'model': None, 'service': None}
    if service is not None:
        if selected['kind'] == 'external':
            selected.setdefault('model', {}).setdefault('target', {})['service'] = service
        else:
            selected['service'] = service
    choices['target'] = selected


def _validation_choices(root: Path, task: dict, reader: InputEvidence, saved: dict | None) -> dict | None:
    """Recover applicable authored evidence from its exact source, not a success result."""
    if task.get('execution') != 'dispatcher':
        return None
    import base64
    import build_generation_payload as payload
    import request_validation
    import runtime_evidence
    record = None
    evidence = runtime_evidence.reader(root, snapshots=reader.snapshots) if saved is None else None
    source = None
    if saved is not None:
        import production_workflow
        import runtime_snapshot
        loaded = production_workflow.read_run(root, saved['run'])
        package = loaded.artifacts.get('package.json') or {}
        record = package.get('request_validation')
        snapshots = copy.deepcopy(package.get('input_snapshots') or {})
        for item in loaded.prepared['dependencies']:
            if item['space'] not in authoring.AUTHORING_SPACES:
                continue
            raw = loaded.evidence.read(item['sha256'])
            snapshots[item['path']] = {'sha256': item['sha256'], 'size': len(raw),
                                       'base64': base64.b64encode(raw).decode('ascii')}
        evidence = InputEvidence(None, snapshots=snapshots, live=False)
        descriptor = loaded.prepared['runtime_snapshot']
        fixed = runtime_snapshot.acquire_runtime(runtime_snapshot.path(root, descriptor), descriptor)
        source = runtime_snapshot.CompileRuntime.from_fixed(fixed, descriptor)
    generation = task.get('generation') or {}
    if task['route'] == 'upscale':
        declaration = c.decode(authoring.source_bytes(root, task['delivery']['path'], reader, saved))
        record = record or declaration.get('request_validation')
        model, service = declaration.get('model'), (task.get('upscale') or {}).get('service')
    else:
        if record is None and generation.get('request_validation'):
            record = c.decode(authoring.source_bytes(root, generation['request_validation'], reader, saved))
        model, service = generation.get('model'), generation.get('service')
        if model is None and generation.get('production_spec'):
            specification = c.decode(authoring.source_bytes(root, generation['production_spec'], reader, saved))
            model = specification.get('target_model')
    if record is None:
        return adapters.validation_template(task) if adapters.validation_required(task) else None
    if source is None:
        from catalog_retrieval.runtime import load_pack_catalog, selected_pack_settings
        from runtime_snapshot import CompileRuntime
        source = CompileRuntime.from_catalog(load_pack_catalog(), selected_pack_settings())
    original = payload.resolve_target(model, service, source=source)
    return request_validation.draft_choices(record, evidence, target=original)


def _reading_action(root: Path, task: dict, choices: dict, runtime_arguments: dict | None = None) -> dict:
    """Offer the real route reader; inspecting a target never fabricates delivery."""
    root = c._root(root)
    from cli_invocation import python_argv, shown
    operation = 'author' if task['execution'] == 'authored' else 'prepare'
    args = {'root': str(root), 'operation': operation, 'execution': task['execution'],
            'feature': task['features'], **(runtime_arguments or {})}
    selected = choices.get('target') or {}
    if selected.get('kind') in {'catalog', 'acquired'}:
        field = 'model' if selected['kind'] == 'catalog' else 'model_file'
        if selected.get(field):
            args[field.replace('_', '-')] = selected[field]
        if selected.get('service'):
            args['service'] = selected['service']
    elif selected.get('kind') == 'external' and (selected.get('model') or {}).get('prompt_dialect'):
        args['dialect'] = selected['model']['prompt_dialect']
    argv = python_argv(ROOT / 'scripts/execution_routes.py', 'read', task['route'])
    for name, value in args.items():
        for item in value if isinstance(value, list) else [value]:
            argv.extend(('--' + name, str(item)))
    return {'operation': 'read', 'script': 'scripts/execution_routes.py', 'args': args,
            'positional': [task['route']], 'argv': argv, 'shown': shown(argv),
            'external_effect': False}


def _guidance_gap(root: Path, task: dict, choices: dict, projected: dict,
                  runtime_arguments: dict | None = None) -> list[dict]:
    if not (choices.get('reading') or {}).get('reading_key') or projected['unresolved']:
        return []
    target = projected.get('resolved_target')
    if target is None:
        return []
    try:
        record = _reading(choices['reading'], root=root, task=task)
        model = target.model if choices['target']['kind'] != 'external' else None
        route_reading.require_route_reading(record, studio=root, routes={task['route']},
            features=task['features'], execution=task['execution'],
            dialect=target.model.get('prompt_dialect'), model_record=model,
            service=(target.offering or {}).get('service'))
    except (ValueError, OSError) as exc:
        action = _reading_action(root, task, choices, runtime_arguments)
        return [{'field': 'reading.reading_key', 'code': 'TARGET_GUIDANCE_REQUIRED',
                 'message': str(exc), 'required_action': 'Read the applicable current guidance and select its issued reading key.',
                 'next_action': action, 'next_actions': [action]}]
    return []


def _reading(choices: dict, *, root: Path, task: dict) -> dict:
    c.exact(choices, {'reading_key'}, 'reading choices')
    issued = route_reading.resolve_issuance(choices['reading_key'], studio=root)
    record = route_reading.build_record(issued, studio=root)
    route_reading.require_route_reading(record, studio=root,
        routes={task['route']}, features=task['features'], execution=task['execution'],
        operation='author' if task.get('execution')=='authored' else 'prepare')
    return record


def _destination(root: Path, out_dir: str) -> Path:
    target = c.local(root, out_dir, exists=False)
    if target == root.resolve() or target.exists():
        raise FileExistsError('select a new input directory: ' + out_dir)
    return target


def _publish(root: Path, out_dir: str, files: dict[str, bytes], *,
             reader: InputEvidence, before_publish=None) -> None:
    """Publish a complete directory only after every captured source still matches."""
    target = _destination(root, out_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.production-inputs-', dir=target.parent))
    try:
        for name, raw in files.items():
            c.atomic(c.local(stage, name, exists=False), raw)
        _destination(root, out_dir)
        with c.staged_inputs(root, out_dir, stage):
            for path in sorted(reader.read_paths):
                ref = {'path': path, 'sha256': reader.snapshots[path]['sha256']}
                reader.read(ref)
            if before_publish is not None:
                before_publish()
        c.publish_directory(stage, target)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


@contextmanager
def _staged_files(root: Path, out_dir: str, files: dict[str, bytes]):
    """Expose generated target evidence only for the dependent local builders."""
    with tempfile.TemporaryDirectory(prefix='production-target-inputs-') as temporary:
        stage = Path(temporary)
        for name, raw in files.items():
            c.atomic(c.local(stage, name, exists=False), raw)
        with c.staged_inputs(root, out_dir, stage):
            yield


def draft_inputs(root: Path, task_path: str | None, out_dir: str, *, from_run: str | None = None,
                 runtime_arguments: dict | None = None, route: str | None = None,
                 artifact: str | None = None, execution: str | None = None,
                 task_id: str | None = None, features: list[str] | None = None,
                 model: str | None = None, service: str | None = None) -> dict:
    reader = InputEvidence(root)
    initial = task_path is None and from_run is None
    if not initial and task_id is not None:
        import production_authoring_state
        if production_authoring_state.active_task_id(root)!=task_id:
            raise ValueError('--task-id must select the current open work task when reopening inputs')
    if from_run is not None:
        import production_authored
        unfinished = production_authored.draft_source(root, from_run)
        if unfinished is not None:
            if any(value is not None for value in (route, artifact, execution, features)):
                raise ValueError('restore the saved draft before changing its route')
            return _restore_draft(root, from_run, out_dir, unfinished,
                task_id=task_id, runtime_arguments=runtime_arguments, model=model, service=service)
    if initial:
        if route is None:
            raise ValueError('select --route for initial production authoring')
        task = authoring.seed(root, route=route, artifact=artifact or 'text', execution=execution or 'authored',
                              task_id=task_id, features=features)
        task_ref, saved = {'initial': True, 'task_id': task['task_id']}, None
    else:
        if any(value is not None for value in (route, artifact, execution, features)):
            raise ValueError('initial task flags cannot replace a selected task or run')
        task, _, task_ref, saved = _task(root, task_path, reader, from_run=from_run)
    choices = draft_choices(task)
    choices['authoring'] = authoring.draft(root, task, reader, saved=saved, initial=initial)
    if not initial and task_id is not None:
        task = copy.deepcopy(task)
        task['task_id'] = task_id
        choices['authoring']['task']['task_id'] = task_id
    if not initial:
        choices['validation'] = _validation_choices(root, task, reader, saved)
    if initial and task.get('execution') == 'external':
        import production_external_inputs
        choices['external'] = production_external_inputs.template()
    if not initial and task.get('execution') == 'external' and task.get('image_input'):
        import production_external_inputs
        plan = c.decode(authoring.source_bytes(root, task['image_input'], reader, saved))
        external_path = (plan.get('external_request') or {}).get('file')
        request = c.decode(authoring.source_bytes(root, external_path, reader, saved)) if external_path else None
        prepared_path = plan.get('prepared_references')
        prepared = c.decode(authoring.source_bytes(root, prepared_path, reader, saved)) if prepared_path else None
        choices['external'] = production_external_inputs.draft(plan, request,
            prepared=prepared, root=root,
            package_root=c.local(root, prepared_path, exists=False).parent if prepared_path else None)
    choices['target'] = production_target.extract(copy.deepcopy(task), choices['authoring'], choices['external'])
    _select_target(choices, model=model, service=service)
    previous = saved['route_reading'] if saved is not None else None
    if previous is None and not initial and saved is None:
        path = task.get('route_reading')
        if path and c.local(root, path, exists=False).is_file():
            previous = reader.json(reader.select(path))
    if previous is not None:
        route_reading.validate_record_content(previous)
        choices['reading']['reading_key'] = previous['reading_key']
    editable={}
    delivery=choices['authoring']['delivery']
    if choices['authoring'].get('upscale') is None:
        raw=delivery.pop('content',None)
        raw=b'' if raw is None else raw.encode('utf-8') if isinstance(raw,str) else c.encoded(raw)
        delivery['file']=(Path(out_dir)/'prompt.txt').as_posix()
        editable['prompt.txt']=raw
    for field in authoring.TEXT_DOCUMENTS:
        raw=choices['authoring']['documents'].get(field)
        if isinstance(raw,str):
            filename=field.replace('_','-')+'.txt'
            editable[filename]=raw.encode('utf-8')
            choices['authoring']['documents'][field]={'file':(Path(out_dir)/filename).as_posix()}
    import production_reference_inputs
    production_reference_inputs.identify_choices(choices)
    identity = _identity_view(root, task, reader, saved=saved)
    projected = production_target.project(choices, _chosen_task(task, choices), root, reader, out_dir)
    gaps = _unresolved(choices, task) + _identity_gaps(identity)
    gaps.extend(item for item in projected['unresolved'] if item not in gaps)
    gaps.extend(_guidance_gap(root, task, choices, projected, runtime_arguments))
    actions = [_reading_action(root, task, choices, runtime_arguments)] if any(
        item['field'].startswith('reading') for item in gaps) else []
    result = {'state': 'draft', 'choices': choices,
              'unresolved': gaps, 'target_knowledge': projected['knowledge'], 'next_actions': actions,
              **({'identity_coverage': identity} if identity is not None else {}),
              'derived_from': {'task': task_ref, 'source_run': saved},
              'external_effect': False}
    _validate_choices(choices)
    context = {key: value for key, value in result.items() if key != 'choices'}
    context['task_content'] = task
    if not initial and task_id is not None:
        context['task_binding']={'task_id':task_id}
    context_raw = c.encoded(context)
    _destination(root, out_dir)
    import production_authoring_state
    production_authoring_state.remember_inputs(root, task, 'draft-inputs', out_dir,
        task_path=task_path, from_run=from_run, runtime_arguments=runtime_arguments,
        context_sha256=c.digest(context_raw))
    _publish(root, out_dir, {**editable,'choices.json': c.encoded(choices),
                            'context.json': context_raw}, reader=reader)
    return {**result, 'choices_file': (Path(out_dir) / 'choices.json').as_posix(),
            'context_file': (Path(out_dir) / 'context.json').as_posix()}


def _restore_draft(root: Path, run: str, out_dir: str, saved_source: dict, *,
                   task_id: str | None, runtime_arguments: dict | None,
                   model: str | None = None, service: str | None = None) -> dict:
    """Reopen the captured editor files, preserving JSON selectors and unfinished choices."""
    import production_authoring_state
    choices=copy.deepcopy(saved_source['choices'])
    task=copy.deepcopy(saved_source['task'])
    authored=choices['authoring']
    if task_id is not None:
        task['task_id']=task_id
        authored['task']['task_id']=task_id
    files={}
    locations={}
    def restore(item, key):
        old=item.get(key)
        if old not in saved_source['files']:
            return
        if old not in locations:
            name='editable/'+str(len(locations)+1)+'-'+Path(old).name
            files[name]=saved_source['files'][old]
            locations[old]=(Path(out_dir)/name).as_posix()
        item[key]=locations[old]
    restore(authored['delivery'],'file')
    for item in authored.get('documents',{}).values():
        if isinstance(item,dict) and set(item)<= {'file','field'}:
            restore(item,'file')
    for item in authored.get('sources',{}).values():
        restore(item,'file')
    target=choices.get('target') or {}
    restore(target,'model_file')
    restore(target,'vocabulary_record')
    negative=(authored['task'].get('authored') or {}).get('negative')
    if negative is not None:
        restore(negative,'path')
    _select_target(choices, model=model, service=service)
    saved=_source_run(root,run)
    reference={'run':run,'input_sha256':saved['input_sha256']}
    unresolved=_unresolved(choices,task)
    unresolved.extend(item for item in copy.deepcopy(saved_source['unresolved'])
                      if item['field'] not in {gap['field'] for gap in unresolved}
                      and not item['field'].startswith(('target', 'reading')))
    for item in unresolved:
        if item.get('file') in locations:
            item['file']=locations[item['file']]
    with _staged_files(root, out_dir, files):
        projected = production_target.project(choices, _chosen_task(task, choices), root,
                                              InputEvidence(root, named_roots={'@skill': ROOT}), out_dir)
        unresolved.extend(item for item in projected['unresolved'] if item not in unresolved)
        unresolved.extend(_guidance_gap(root, task, choices, projected, runtime_arguments))
    actions = [_reading_action(root, task, choices, runtime_arguments)] if any(
        item['field'].startswith('reading') for item in unresolved) else []
    result={'state':'draft','choices':choices,'unresolved':unresolved,
        'target_knowledge':projected['knowledge'],'next_actions':actions,
        'derived_from':{'task':reference,'source_run':saved},'external_effect':False}
    context={key:value for key,value in result.items() if key!='choices'}
    context['task_content']=task
    if task_id is not None:
        context['task_binding']={'task_id':task_id}
    _validate_choices(choices)
    raw=c.encoded(context)
    _destination(root,out_dir)
    production_authoring_state.remember_inputs(root,task,'draft-inputs',out_dir,
        task_path=None,from_run=run,runtime_arguments=runtime_arguments,context_sha256=c.digest(raw))
    _publish(root,out_dir,{**files,'choices.json':c.encoded(choices),'context.json':raw},
        reader=InputEvidence(root))
    return {**result,'choices_file':(Path(out_dir)/'choices.json').as_posix(),
        'context_file':(Path(out_dir)/'context.json').as_posix()}


def _validate_choices(value: dict) -> None:
    from state_protocol import validate_against_schema
    schema = c.load(ROOT / 'schemas/authoring/production-input-draft.schema.json')
    errors = validate_against_schema(value, schema)
    if errors:
        raise ValueError('input choices: ' + '; '.join(errors))


def read_choices(value: Any) -> dict:
    _validate_choices(value)
    return value


TASK_CHOICES = frozenset({'route', 'features', 'sources', 'criteria', 'direction', 'delivery',
                          'world_views', 'moment_views', 'scene_materials', 'semantic_edit', 'generation',
                          'upload_sources'})


def _chosen_task(task: dict, choices: dict) -> dict:
    changes = choices['task_changes']
    if not isinstance(changes, dict) or set(changes) - TASK_CHOICES:
        raise ValueError('task_changes names only authored route, source, depiction or review fields')
    result = authoring.chosen_task(task, choices.get('authoring'))
    result.update(copy.deepcopy(changes))
    if choices['external'] is not None:
        if task.get('execution') == 'dispatcher':
            raise ValueError('select an authored or external task for external input assembly')
        result.update(artifact='image', execution='external')
        if isinstance(choices['external'].get('image_input'), str):
            result['image_input'] = choices['external']['image_input']
    return result


def _saved_delivery(root: Path, saved: dict, task: dict) -> bytes | None:
    if task['delivery'] != saved['task']['delivery']:
        return None
    import production_workflow as workflow
    directory, prepared, _, _ = workflow.read_run(root, saved['run'])
    if prepared['input_sha256'] != saved['input_sha256']:
        raise ValueError('source run input changed during input construction')
    path = task['delivery']['path']
    matches = [row for row in prepared['dependencies']
               if row['space'] in authoring.AUTHORING_SPACES and row['path'] == path]
    if len(matches) != 1:
        raise ValueError('source run has no unique saved delivery')
    return c.object_read(directory, matches[0]['sha256'])


def _retained_sources(root: Path, saved: dict | None, task: dict, reader: InputEvidence) -> None:
    """A source selected again retains its saved bytes until explicitly replaced."""
    if saved is None:
        return
    import production_workflow as workflow
    _, prepared, _, _ = workflow.read_run(root, saved['run'])
    paths = {row['path'] for row in task.get('sources', [])}
    for key in ('image_input', 'semantic_edit'):
        if task.get(key):
            paths.add(task[key])
    paths.update(value for value in (task.get('generation') or {}).values() if isinstance(value, str))
    paths.update(source['file'] for source in task.get('upload_sources', []))
    paths.discard(saved['task']['delivery']['path'])
    previous = {row['path']: row for row in prepared['dependencies']
                if row['space'] not in {'skill', 'evidence'}}
    for path in sorted(paths & previous.keys()):
        reader.read({'path': path, 'sha256': previous[path]['sha256']})


def _retained_identity_sources(root: Path, task: dict, choices_path: str, reader: InputEvidence,
                               choices: dict) -> None:
    """A mutable choices witness cannot erase a draft's original source evidence."""
    folder = Path(choices_path).parent.as_posix()
    path = (Path(folder) / 'context.json').as_posix()
    import production_authoring_state
    current_identity = any(source.get('identity') for source in task.get('sources', []))
    if not c.local(root, path, exists=False).is_file():
        production_authoring_state.require_input_context(root, task['task_id'], folder, b'', required=current_identity)
        return
    raw = reader.read(reader.select(path))
    registration = production_authoring_state.require_input_context(root, task['task_id'], folder, raw,
                                                                     required=current_identity)
    value = c.decode(raw)
    prior = (value.get('identity_coverage') or {}).get('sources', [])
    if prior and registration is None:
        production_authoring_state.require_input_context(root, task['task_id'], folder, raw, required=True)
    selected = {source['path'] for source in task.get('sources', [])}
    selected.update(item for item in (task.get('generation') or {}).values() if isinstance(item, str))
    from production_reference_inputs import _authored_rows
    reference_choices = (choices.get('authoring') or {}).get('references')
    external = choices.get('external') or {}
    for refs in (reference_choices, (external.get('reference_delivery') or {}).get('choices')):
        if refs is not None:
            for reference in _authored_rows(refs):
                original = reference.get('source') or {}
                if original.get('resolved_path'):
                    selected.add(original['resolved_path'])
                if reference.get('file'):
                    selected.add(reference['file'])
    external_input = external.get('image_input')
    if isinstance(external_input, dict):
        selected.update(row['file'] for row in external_input.get('references', []) if row.get('file'))
    for source in prior:
        candidates = {source['path']}
        original = (source.get('authority') or {}).get('source') or {}
        if original.get('resolved_path'):
            candidates.add(original['resolved_path'])
        for selected_path in candidates & selected:
            try:
                if Path(selected_path).is_absolute():
                    import production_store
                    local = Path(selected_path)
                    current = production_store.stable_bytes(local.parent, local.name)
                else:
                    current = reader._live(selected_path)
            except (ValueError, OSError) as exc:
                raise production_authoring_state.input_context_error(root, task['task_id'], folder,
                    code='IDENTITY_SOURCE_UNAVAILABLE', message='The selected identity source is unavailable.',
                    file=selected_path, expected_sha256=source['sha256'], cause=str(exc)) from exc
            actual = c.digest(current)
            if actual != source['sha256']:
                raise production_authoring_state.input_context_error(root, task['task_id'], folder,
                    code='IDENTITY_SOURCE_CHANGED', message='The selected identity source differs from the draft evidence.',
                    file=selected_path, expected_sha256=source['sha256'], actual_sha256=actual)
            if not Path(selected_path).is_absolute():
                reader.read({'path': selected_path, 'sha256': source['sha256']})


def _choice_source(root: Path, choices_path: str, reader: InputEvidence, *, choices: dict | None = None,
                    read_run=None) -> tuple[dict, dict, dict | None, str | None, str | None]:
    """Recover the original input boundary; edited content never asserts origin."""
    path = (Path(choices_path).parent / 'context.json').as_posix()
    import production_authoring_state
    task_id = (((choices or {}).get('authoring') or {}).get('task') or {}).get('task_id')
    task_id = task_id or production_authoring_state.active_task_id(root)
    raw = reader.read(reader.select(path)) if c.local(root, path, exists=False).is_file() else b''
    production_authoring_state.require_input_context(root, task_id, Path(choices_path).parent.as_posix(), raw)
    context = c.decode(raw)
    def bound(task):
        binding=context.get('task_binding')
        if binding is None:
            return task
        c.exact(binding,{'task_id'},'reopened work task')
        import production_authoring_state
        production_authoring_state.require_input_context(root,binding['task_id'],
            Path(choices_path).parent.as_posix(),reader.read(reader.select(path)),required=True)
        return {**task,'task_id':binding['task_id']}
    origin = context['derived_from']
    reference = origin['task']
    saved = origin.get('source_run')
    if saved is not None:
        task, _, current, recovered = _task(root, None, reader, from_run=saved['run'], read_run=read_run)
        if current['input_sha256'] != saved['input_sha256']:
            raise ValueError('saved authoring context no longer matches its source run')
        return bound(task), current, recovered, None, saved['run']
    if reference.get('initial') is True:
        task = copy.deepcopy(context['task_content'])
        if task['task_id'] != reference['task_id']:
            raise ValueError('initial authoring context has a different work task')
        return task, reference, None, None, None
    task_path = reference['path']
    reader.read(reference)
    task, _, current, recovered = _task(root, task_path, reader)
    return bound(task), current, recovered, task_path, None


def _load_editable(root: Path, choices_path: str, reader: InputEvidence, *, register: bool = True) -> tuple[dict,dict,dict,list]:
    path=c.local(root,choices_path)
    raw=c.read(path)
    choices=read_choices(c.decode(raw))
    import production_reference_inputs
    if register and production_reference_inputs.identify_choices(choices):
        if c.read(path)!=raw:
            raise ValueError('editable choices changed while assigning reference uses')
        c.atomic(path,c.encoded(choices),replace=True)
    ref=reader.select(choices_path)
    locations={}
    gaps=[]
    if choices.get('authoring') is not None:
        choices['authoring'],locations,gaps=authoring.read_editable(choices['authoring'],reader)
    ref={**ref,'files':{path:item['sha256'] for path,item in reader.snapshots.items()
                       if path!=choices_path and not path.startswith('@')}}
    return choices,ref,locations,gaps


def _authored_basis(root: Path, task: dict, origin_task: dict, reader: InputEvidence,
                    saved: dict | None, *, allow_missing: bool = False) -> dict | None:
    """Retain the commission and original sources before editable adaptations."""
    if task.get('execution') != 'authored':
        return None
    previous = None
    if saved is not None:
        import production_workflow as workflow
        previous = workflow.read_run(root, saved['run'])
    basis = (previous.prepared['task'].get('authored_basis') or {}) if previous else (origin_task.get('authored_basis') or {})
    originals = {item['source']['id']: item for item in basis.get('sources', [])}
    previous_sources = {item['id']: item for item in
                        (previous.prepared['task'] if previous else origin_task).get('sources', [])}
    retained = []
    for source in task.get('sources', []):
        original = originals.get(source['id'])
        if original and previous_sources.get(source['id'], {}).get('path') == source['path']:
            path = ((previous.directory / 'objects' / original['file']['sha256']).relative_to(root).as_posix()
                    if previous else original['file']['path'])
            definition = original['source']
            selected = {'path': path, 'sha256': original['file']['sha256']}
        else:
            path, definition = source['path'], source
            selected = None
        try:
            selected = selected or reader.select(path)
            raw = reader.read(selected)
        except (ValueError, OSError):
            if allow_missing:
                continue
            raise
        retained.append({'source': copy.deepcopy(definition),
                         'file': {**selected, 'size': len(raw)}})
    return {'origin_task': copy.deepcopy(basis.get('origin_task', origin_task)), 'sources': retained}


def authoring_view(root: Path, choices_path: str, *, register: bool = False,
                   task_path: str | None = None, from_run: str | None = None, read_run=None,
                   runtime_arguments: dict | None = None) -> dict:
    """Expose the actual editable revision, including its unfinished choices."""
    reader=InputEvidence(root,named_roots={'@skill':ROOT})
    choices,ref,locations,gaps=_load_editable(root,choices_path,reader,register=register)
    if task_path is not None or from_run is not None:
        base,_,origin,saved=_task(root,task_path,reader,from_run=from_run,read_run=read_run)
    else:
        base,origin,saved,task_path,from_run=_choice_source(root,choices_path,reader,choices=choices,read_run=read_run)
    task=_chosen_task(base,choices)
    projected = production_target.project(choices, task, root, reader,
                                          (Path(choices_path).parent / 'view').as_posix())
    task = projected['task']
    for source in task.get('sources',[]):
        path=source.get('path')
        if not path:continue
        try:reader.read(reader.select(path))
        except (ValueError,OSError) as exc:
            gaps.append({'field':'authoring.task.sources','file':path,'code':'source-unavailable','message':str(exc)})
    basis = _authored_basis(root, task, base, reader, saved, allow_missing=True)
    unresolved=_unresolved(choices,task)+gaps
    unresolved.extend(item for item in projected['unresolved'] if item not in unresolved)
    unresolved.extend(_guidance_gap(root, task, choices, projected, runtime_arguments))
    content=((choices.get('authoring') or {}).get('delivery') or {}).get('content')
    delivery=b'' if content is None else content.encode('utf-8') if isinstance(content,str) else c.encoded(content)
    captured={path:reader._decode(value) for path,value in reader.snapshots.items() if not path.startswith('@')}
    return {'task':task,'choices':c.decode(captured[choices_path]),'resolved_choices':choices,
        'files':{},'delivery':delivery,'unresolved':unresolved,'source_map':locations,'captured':captured,
        'origin':origin,'source_run':saved,'task_path':task_path,'from_run':from_run,'choices_ref':ref,
        'authored_basis':basis,'target_knowledge':projected['knowledge']}


def _assemble_inputs(root: Path, task_path: str | None, choices_path: str, out_dir: str, *,
                 from_run: str | None = None, runtime_arguments: dict | None = None,
                 publish: bool = True) -> dict:
    try:
        return _assemble_current(root, task_path, choices_path, out_dir, from_run=from_run,
                                 runtime_arguments=runtime_arguments, publish=publish)
    except ProductionError as exc:
        diagnostic = from_exception(exc, phase='authoring', file=choices_path)
        return {'state': 'draft', 'ok': False, 'inputs': {}, 'diagnostics': [diagnostic],
                'unresolved': [{**diagnostic, 'field': diagnostic.get('pointer') or 'authoring'}],
                'next_actions': diagnostic.get('next_actions', []), 'external_effect': False}


def _assemble_current(root: Path, task_path: str | None, choices_path: str, out_dir: str, *,
                 from_run: str | None = None, runtime_arguments: dict | None = None,
                 publish: bool = True) -> dict:
    import runtime_evidence
    reader = runtime_evidence.reader(root)
    choices,choices_ref,locations,file_gaps = _load_editable(root,choices_path,reader)
    if task_path is None and from_run is None:
        base_task, task_ref, saved, task_path, from_run = _choice_source(root, choices_path, reader, choices=choices)
    else:
        base_task, _, task_ref, saved = _task(root, task_path, reader, from_run=from_run)
    task = _chosen_task(base_task, choices)
    _retained_identity_sources(root, task, choices_path, reader, choices)
    basis = _authored_basis(root, task, base_task, reader, saved)
    if choices.get('authoring') is None and task.get('execution') == 'dispatcher':
        # An explicit complete task owns authored inputs too. Route it through
        # the same materialization boundary so a selected target updates its
        # specification and derives validation from the retained evidence.
        choices['authoring'] = authoring.draft(root, task, reader, saved=saved)
        choices['target'] = production_target.extract(copy.deepcopy(task), choices['authoring'], choices['external'])
        if choices['validation'] is None:
            choices['validation'] = _validation_choices(root, task, reader, saved)
    _destination(root, out_dir)
    import production_authoring_state
    if publish:
        production_authoring_state.remember_inputs(root, task, 'build-inputs', out_dir,
            task_path=task_path, from_run=from_run, choices_path=choices_path, runtime_arguments=runtime_arguments)
    projected = production_target.project(choices, task, root, reader, out_dir)
    choices['target'] = copy.deepcopy(projected['choices']['target'])
    missing = _unresolved(choices, task)+file_gaps
    missing.extend(item for item in projected['unresolved'] if item not in missing)
    missing.extend(_guidance_gap(root, task, choices, projected, runtime_arguments))
    if missing:
        actions = [_reading_action(root, task, choices, runtime_arguments)] if any(
            item['field'].startswith('reading') for item in missing) else []
        return {'state': 'draft', 'ok': False, 'inputs': {}, 'unresolved': missing,
                'target_knowledge': projected['knowledge'],
                'derived_from': {'task': task_ref, 'choices': choices_ref},
                'next_actions': [*actions, {'operation': 'edit-choices', 'args': {'path': choices_path},
                                  'external_effect': False}]}
    task, material_choices = projected['task'], projected['choices']
    target_files = projected['files']
    reading = _reading(choices['reading'], root=root, task=task)
    visual, visual_context = adapters.build_visual(choices['visual'], task, reader, root)
    validation, validation_context = adapters.build_validation(choices['validation'], task, reader, root,
                                                              target=projected['resolved_target'])
    adapters.cross_check(visual_context, validation_context)
    if validation is not None:
        dialect = validation_context.get('dialect', route_reading._NO_MODEL)
        route_reading.require_route_reading(reading, studio=root, routes={task['route']},
                                           features=task['features'], execution=task['execution'], dialect=dialect)
    content = {'route-reading.json': reading}
    if visual is not None:
        content['visual-continuity.json'] = visual
    if validation is not None:
        content['request-validation.json'] = validation
    try:
        with _staged_files(root, out_dir, target_files):
            copied_task, authored_files, authored_delivery = authoring.materialize(
                root, task, material_choices.get('authoring'), reader, out_dir, saved=saved, validation=validation)
    except authoring.UnresolvedChoice as exc:
        return {'state': 'draft', 'ok': False, 'inputs': {},
                'unresolved': [{'field': exc.field, 'code': 'current-judgment-required', 'message': str(exc)}],
                'derived_from': {'task': task_ref, 'choices': choices_ref},
                'next_actions': [{'operation': 'edit-choices', 'args': {'path': choices_path},
                                  'external_effect': False}]}
    copied_task['route_reading'] = (Path(out_dir) / 'route-reading.json').as_posix()
    if copied_task.get('execution') == 'dispatcher' and copied_task.get('generation') is not None:
        for name, field in (('visual-continuity', 'visual_continuity'), ('request-validation', 'request_validation')):
            if name + '.json' in content:
                path = (Path(out_dir) / (name + '.json')).as_posix()
                authoring._redirect(copied_task, (base_task.get('generation') or {}).get(field), path)
                copied_task['generation'][field] = path
    _retained_sources(root, saved, copied_task, reader)
    encoded = {**target_files, **authored_files}
    if basis is not None:
        exported_basis = copy.deepcopy(basis)
        for index, original in enumerate(exported_basis['sources'], 1):
            item = original['file']
            raw = reader.read({key: item[key] for key in ('path', 'sha256')})
            name = 'basis/source-' + str(index).zfill(3) + Path(original['source']['path']).suffix
            encoded[name] = raw
            item['path'] = (Path(out_dir) / name).as_posix()
        copied_task['authored_basis'] = exported_basis
    encoded.update({name: c.encoded(value) for name, value in content.items()})
    delivery = authored_delivery
    if delivery is None and saved is not None:
        delivery = _saved_delivery(root, saved, task)
    if delivery is not None and authored_delivery is None:
        original_path = copied_task['delivery']['path']
        delivery_path = (Path(out_dir) / 'delivery.txt').as_posix()
        copied_task['delivery']['path'] = delivery_path
        for source in copied_task['sources']:
            if source['path'] == original_path:
                source['path'] = delivery_path
        encoded['delivery.txt'] = delivery
    if choices['external'] is not None:
        if delivery is None:
            delivery = reader.read(reader.select(copied_task['delivery']['path']))
        with _staged_files(root, out_dir, target_files):
            external_files, external_context = adapters.build_external(
                material_choices['external'], copied_task, reader, root, out_dir, delivery,
                derived_files=target_files)
        encoded.update(external_files)
        copied_task['image_input'] = (Path(out_dir) / 'image-input.json').as_posix()
        route_reading.require_route_reading(reading, studio=root, routes={copied_task['route']},
            features=copied_task['features'], execution=copied_task['execution'], dialect=external_context['dialect'])
    else:
        external_context = None
    identity = _identity_view(root, copied_task, reader, files=encoded, out_dir=out_dir)
    identity_gaps = _identity_gaps(identity)
    def recheck():
        _reading(choices['reading'], root=root, task=task)
        _retained_identity_sources(root, task, choices_path, reader, choices)
        _retained_sources(root, saved, copied_task, reader)
        current_visual, _ = adapters.build_visual(choices['visual'], task, reader, root)
        current_validation, _ = adapters.build_validation(choices['validation'], task, reader, root,
                                                         target=projected['resolved_target'])
        if current_visual != visual or current_validation != validation:
            raise ValueError('selected input evidence changed during construction')
        if external_context is not None:
            with _staged_files(root, out_dir, target_files):
                current_files, current_context = adapters.build_external(
                    material_choices['external'], copied_task, reader, root, out_dir, delivery,
                    derived_files=target_files)
            if current_files != external_files or current_context != external_context:
                raise ValueError('selected external input changed during construction')
    if identity_gaps or (external_context is not None and external_context.get('unresolved')):
        # The canonical carriers are useful authored-work output. Their actual
        # upload is still missing, so publish them without an executable task.
        encoded['input-snapshots.json'] = c.encoded(reader.snapshots)
        result = {'state': 'draft', 'ok': False,
                  'inputs': {Path(name).stem: {'path': (Path(out_dir) / name).as_posix(),
                             'sha256': c.digest(raw)} for name, raw in encoded.items()},
                  'unresolved': (external_context or {}).get('unresolved', []) + identity_gaps,
                  'execution_ready': False,
                  'request_state': (external_context or {}).get('state', 'identity-choices-required'),
                  'derived_from': {'task': task_ref, 'choices': choices_ref,
                                   'source_run': saved, 'sources': sorted(reader.read_paths)},
                  'external_input': external_context,
                  **({'identity_coverage': identity} if identity is not None else {}),
                  'next_actions': [{'operation': 'edit-choices', 'args': {'path': choices_path},
                                    'external_effect': False}],
                  'external_effect': False}
        encoded['input-report.json'] = c.encoded(result)
        if publish:_publish(root, out_dir, encoded, reader=reader, before_publish=recheck)
        return result
    from production_workflow import validate_task
    if publish:
        validate_task(copied_task)
    encoded['production-task.json'] = c.encoded(copied_task)
    encoded['input-snapshots.json'] = c.encoded(reader.snapshots)
    inputs = {Path(name).stem: {'path': (Path(out_dir) / name).as_posix(),
              'sha256': c.digest(raw)} for name, raw in encoded.items()}
    result = {'state': 'built', 'ok': True, 'inputs': inputs, 'unresolved': [],
              'target_knowledge': projected['knowledge'],
              'execution_ready': False,
              'request_state': 'materialized' if external_context is not None else 'not-rendered' if validation is not None else None,
              'derived_from': {'task': task_ref, 'choices': choices_ref,
                               'source_run': saved, 'sources': sorted(reader.read_paths)},
              'changes': [{'field': key, 'before': base_task.get(key), 'after': value}
                          for key, value in copied_task.items() if value != base_task.get(key)],
              'external_input': external_context,
              **({'identity_coverage': identity} if identity is not None else {}),
              'assessment_required': ['Judge the depiction and selected sources against the commission.'],
              'next_actions': adapters.next_actions(inputs, copied_task, root, runtime_arguments=runtime_arguments),
              'external_effect': False}
    encoded['input-report.json'] = c.encoded(result)
    if publish:
        _publish(root, out_dir, encoded, reader=reader, before_publish=recheck)
    else:
        recheck()
        result['_files']=encoded
        result['_captured']={path:reader._decode(item) for path,item in reader.snapshots.items() if not path.startswith('@')}
        result['_source_map']=locations
        result['_task']=copied_task
    return result


def build_inputs(root: Path, task_path: str | None, choices_path: str, out_dir: str, *,
                 from_run: str | None = None, runtime_arguments: dict | None = None) -> dict:
    """Export derived files for explicit inspection or interchange."""
    return _assemble_inputs(root,task_path,choices_path,out_dir,from_run=from_run,runtime_arguments=runtime_arguments)


def compile_choices(root: Path, choices_path: str, *, persist: bool = False,
                    identity: str | None = None, draft: bool = False,
                    runtime_arguments: dict | None = None):
    """Compile the editable source with the same validators used by task input."""
    import production_compiler as compiler
    from production_diagnostics import from_exception
    from pack_manager import generate_uuid7
    identity=identity or generate_uuid7()
    if draft:
        raise ValueError('unfinished revisions use the authored save owner and authoring_view')
    output=compiler.run_inputs(identity)
    try:
        assembled=_assemble_inputs(root,None,choices_path,output,publish=False,runtime_arguments=runtime_arguments)
        if not assembled.get('ok'):
            diagnostics = assembled.get('diagnostics') or [
                {'code':item.get('code','AUTHORED_CHOICE_REQUIRED'),'message':item.get('message','Resolve this authored choice.'),
                 'file':item.get('file',choices_path),'pointer':item['field'],'phase':'authoring','severity':'error',
                 'required_action':'Complete the named current choice.', **item}
                for item in assembled.get('unresolved',[])]
            return compiler.Compilation({'ok':False,'publishable':False,'diagnostics':diagnostics,
                'checks':[], 'authoring':assembled,
                'external_effect':False,'formal_run_created':False})
        path=(Path(output)/'production-task.json').as_posix()
        compiled=compiler.compile_task(root,path,persist=persist,identity=identity,
            derived=assembled['_files'],source_inputs=assembled['_captured'])
        compiled.report['authoring']={'choices':choices_path,
            'choices_ref':assembled['derived_from']['choices'],'source_map':assembled['_source_map'],
            'source_run': (assembled['derived_from'].get('source_run') or {}).get('run')}
        if compiled.prepared is not None:
            compiled.prepared['authoring']=copy.deepcopy(compiled.report['authoring'])
        reverse={item['path']:key for key,item in assembled['inputs'].items()}
        for diagnostic in compiled.report.get('diagnostics',[]):
            generated=diagnostic.get('file')
            name=reverse.get(generated)
            field='authoring.delivery' if name=='delivery' else 'authoring.documents.'+name.replace('-','_') if name else None
            origin=assembled['_source_map'].get(field)
            if origin is not None:
                diagnostic['generated_file']=generated
                diagnostic['file']=origin['file']
                if origin.get('pointer') is not None:diagnostic['source_field']=origin['pointer']
            elif generated and generated.startswith(output+'/'):
                diagnostic['generated_file']=generated;diagnostic['file']=choices_path
                diagnostic['authoring_field']=field or 'authoring.task'
        return compiled
    except (ValueError,OSError,KeyError,TypeError) as exc:
        return compiler.Compilation({'ok':False,'publishable':False,'diagnostics':[
            from_exception(exc,phase='authoring',file=choices_path)],'checks':[],
            'external_effect':False,'formal_run_created':False})


def add_arguments(subparsers) -> None:
    for name in sorted(COMMANDS):
        parser = subparsers.add_parser(name, help={
            'inspect-inputs': 'Show declared sources, candidates and required input choices.',
            'draft-inputs': 'Create an unanswered choices document in a new directory.',
            'build-inputs': 'Resolve authored choices into complete inputs without running production.'}[name])
        parser.add_argument('--root', type=Path, required=True)
        source = parser.add_mutually_exclusive_group()
        source.add_argument('--task', help='Studio-relative authored production task JSON.')
        source.add_argument('--from-run', help='Use the saved task and delivery of this existing run.')
        if name == 'draft-inputs':
            parser.add_argument('--model',help='Select the canonical model in a new or reopened draft.')
            parser.add_argument('--service',help='Select the offering service in a new or reopened draft.')
            parser.add_argument('--route', help='Initial production route; no prebuilt task is needed.')
            parser.add_argument('--artifact', dest='artifact_kind',
                choices=('text', 'json', 'image', 'video', 'audio', 'binary'),
                help='Initial output kind; defaults to text. Existing tasks retain their kind.')
            parser.add_argument('--execution', choices=('authored', 'external', 'dispatcher'),
                help='Initial execution method; defaults to authored. Existing tasks retain their method.')
            parser.add_argument('--task-id', help='Existing work task ID; defaults to the open work task.')
            parser.add_argument('--feature', action='append', dest='features',
                help='Feature applied to an initial task; repeat for several features.')
        if name != 'inspect-inputs':
            parser.add_argument('--out-dir', required=True, help='New studio-relative directory; existing files are preserved.')
        if name == 'build-inputs':
            parser.add_argument('--choices', required=True, help='Edited choices.json from draft-inputs, or a complete choices object.')
        adapters.add_runtime_arguments(parser)


def command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> dict:
    root = args.root.resolve(strict=True)
    if args.command == 'inspect-inputs' and args.task is None and args.from_run is None:
        return inspect_inputs(root)
    runtime_arguments = adapters.configure_runtime(args, parser)
    if args.command == 'inspect-inputs':
        result = inspect_inputs(root, args.task, from_run=args.from_run)
        for action in result['craft_lookup']['next_actions']:
            action['args'].update(runtime_arguments or {})
        return result
    if args.command == 'draft-inputs':
        return draft_inputs(root, args.task, args.out_dir, from_run=args.from_run,
                            runtime_arguments=runtime_arguments, route=args.route, artifact=args.artifact_kind,
                            execution=args.execution, task_id=args.task_id, features=args.features,
                            model=args.model,service=args.service)
    return build_inputs(root, args.task, args.choices, args.out_dir, from_run=args.from_run, runtime_arguments=runtime_arguments)
