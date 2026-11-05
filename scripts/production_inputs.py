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

import execution_contract as c
import execution_routes
from input_evidence import InputEvidence
import route_reading
import production_input_adapters as adapters
import production_authoring as authoring

ROOT = Path(__file__).resolve().parents[1]
COMMANDS = frozenset({'inspect-inputs', 'draft-inputs', 'build-inputs'})


def _task(root: Path, path: str | None, reader: InputEvidence, *,
          from_run: str | None = None) -> tuple[dict, dict, dict, dict | None]:
    if (path is None) == (from_run is None):
        raise ValueError('select one task file or source run')
    saved = _source_run(root, from_run) if from_run is not None else None
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
    route = execution_routes.resolve(value['route'], features)
    return value, route, ref, saved


def _source_run(root: Path, selected: str | None) -> dict | None:
    if selected is None:
        return None
    import production_workflow as workflow
    _, prepared, _, _ = workflow.load_run(root, selected)
    from production_execution import status
    current = status(root, selected)['runs'][0]
    if current['integrity'] != 'intact':
        raise ValueError('source run integrity changed while inspecting its evidence')
    return {'run': selected, 'input_sha256': prepared['input_sha256'],
            'task_path': prepared['task_path'], 'task': prepared['task'],
            'route_reading': copy.deepcopy(prepared.get('route_reading')),
            'freshness': {'current': not current['freshness_diagnostics'], 'diagnostics': current['freshness_diagnostics']},
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
        directory, prepared, _, _ = production_workflow.load_run(root, saved['run'])
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
    applications = {'snapshot_id': None, 'reading_key': None, 'applied': []}
    if route_reading.RECORD_RESOURCE_FIELDS:
        applications['resource_applied'] = []
    # A null visual or validation choice builds no record here: the Generation
    # Package builder takes continuity decisions and derives request validation.
    return {'reading': applications, 'visual': None,
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
        for key in ('applied',) + (('resource_applied',) if route_reading.RECORD_RESOURCE_FIELDS else ()):
            if key not in reading:
                unresolved.append({'field': 'reading.' + key, 'code': 'application-selection-required'})
            elif not isinstance(reading[key], list):
                raise ValueError('reading.' + key + ' must be an array')
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


def _retained_validation(choices: dict) -> dict | None:
    return ((choices.get('authoring') or {}).get('upscale') or {}).get('request_validation')


def _validation_task(task: dict, choices: dict) -> dict:
    result = copy.deepcopy(task)
    if _retained_validation(choices) is not None:
        result['_authoring_validation_retained'] = True
    return result


def _unresolved(choices: dict, task: dict) -> list[dict]:
    unresolved = _missing(choices)
    if choices['validation'] is None and adapters.validation_required(_validation_task(task, choices)):
        unresolved.append({'field': 'validation', 'code': 'selection-required'})
    unresolved.extend(authoring.unresolved(choices.get('authoring'), task))
    if choices['external'] is not None:
        import production_external_inputs
        unresolved.extend(production_external_inputs.unresolved(choices['external']))
    return unresolved


def _reading(choices: dict, *, root: Path, task: dict) -> dict:
    fields = {'snapshot_id', 'reading_key', 'applied'}
    if route_reading.RECORD_RESOURCE_FIELDS:
        fields.add('resource_applied')
    c.exact(choices, fields, 'reading choices')
    issued = route_reading.resolve_issuance(choices['reading_key'], studio=root)
    snapshot = choices['snapshot_id']
    if snapshot is not None:
        route_reading.check_snapshot_issuance(snapshot, issued, studio=root)
    applications = {'applied': choices['applied']}
    if route_reading.RECORD_RESOURCE_FIELDS:
        applications['resource_applied'] = choices['resource_applied']
    record = route_reading.build_record(issued, applications, studio=root)
    route_reading.require_route_reading(record, studio=root,
                                       routes={task['route']}, features=task['features'])
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
        with c.lock(root):
            _destination(root, out_dir)
            for path in sorted(reader.read_paths):
                ref = {'path': path, 'sha256': reader.snapshots[path]['sha256']}
                reader.read(ref)
            if before_publish is not None:
                before_publish()
            c.publish_directory(stage, target)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def draft_inputs(root: Path, task_path: str | None, out_dir: str, *, from_run: str | None = None,
                 runtime_arguments: dict | None = None, route: str | None = None,
                 artifact: str | None = None, execution: str | None = None,
                 task_id: str | None = None, features: list[str] | None = None) -> dict:
    reader = InputEvidence(root)
    initial = task_path is None and from_run is None
    if initial:
        if route is None:
            raise ValueError('select --route for initial production authoring')
        task = authoring.seed(root, route=route, artifact=artifact or 'text', execution=execution or 'authored',
                              task_id=task_id, features=features)
        task_ref, saved = {'initial': True, 'task_id': task['task_id']}, None
    else:
        if any(value is not None for value in (route, artifact, execution, task_id, features)):
            raise ValueError('initial task flags cannot replace a selected task or run')
        task, _, task_ref, saved = _task(root, task_path, reader, from_run=from_run)
    choices = draft_choices(task)
    choices['authoring'] = authoring.draft(root, task, reader, saved=saved, initial=initial)
    if _retained_validation(choices) is not None:
        choices['validation'] = None
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
    previous = saved['route_reading'] if saved is not None else None
    if previous is None and not initial and saved is None:
        path = task.get('route_reading')
        if path and c.local(root, path, exists=False).is_file():
            previous = reader.json(reader.select(path))
    if previous is not None:
        route_reading.validate_record_content(previous)
        choices['reading']['reading_key'] = previous['reading_key']
        choices['reading']['applied'] = copy.deepcopy(previous['applied'])
        if route_reading.RECORD_RESOURCE_FIELDS:
            choices['reading']['resource_applied'] = copy.deepcopy(previous['resource_applied'])
    identity = _identity_view(root, task, reader, saved=saved)
    result = {'state': 'draft', 'choices': choices,
              'unresolved': _unresolved(choices, task) + _identity_gaps(identity),
              **({'identity_coverage': identity} if identity is not None else {}),
              'derived_from': {'task': task_ref, 'source_run': saved},
              'external_effect': False}
    _validate_choices(choices)
    context = {key: value for key, value in result.items() if key != 'choices'}
    context['task_content'] = task
    context_raw = c.encoded(context)
    _destination(root, out_dir)
    import production_authoring_state
    production_authoring_state.remember_inputs(root, task, 'draft-inputs', out_dir,
        task_path=task_path, from_run=from_run, runtime_arguments=runtime_arguments,
        context_sha256=c.digest(context_raw))
    _publish(root, out_dir, {'choices.json': c.encoded(choices),
                            'context.json': context_raw}, reader=reader)
    return {**result, 'choices_file': (Path(out_dir) / 'choices.json').as_posix(),
            'context_file': (Path(out_dir) / 'context.json').as_posix()}


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
    directory, prepared, _, _ = workflow.load_run(root, saved['run'])
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
    _, prepared, _, _ = workflow.load_run(root, saved['run'])
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
    try:
        current_identity = any(source.get('identity') for source in task.get('sources', []))
        if not c.local(root, path, exists=False).is_file():
            production_authoring_state.require_input_context(root, task['task_id'], folder, b'', required=current_identity)
            return
        raw = reader.read(reader.select(path))
        value = c.decode(raw)
        prior = (value.get('identity_coverage') or {}).get('sources', [])
        production_authoring_state.require_input_context(root, task['task_id'], folder, raw,
                                                         required=bool(prior) or current_identity)
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
                if Path(selected_path).is_absolute():
                    import production_store
                    local = Path(selected_path)
                    if c.digest(production_store.stable_bytes(local.parent, local.name)) != source['sha256']:
                        raise ValueError('retained identity source bytes differ: ' + selected_path)
                else:
                    reader.read({'path': selected_path, 'sha256': source['sha256']})
    except (ValueError, OSError) as exc:
        raise authoring.UnresolvedChoice('authoring.task.sources',
            'Identity source evidence changed since this draft. Read the current owning sources '
            'and draft their current application and criteria again. ' + str(exc)) from exc


def _choice_source(root: Path, choices_path: str, reader: InputEvidence) -> tuple[dict, dict, dict | None, str | None, str | None]:
    """Recover the original input boundary; edited content never asserts origin."""
    path = (Path(choices_path).parent / 'context.json').as_posix()
    context = reader.json(reader.select(path))
    origin = context['derived_from']
    reference = origin['task']
    saved = origin.get('source_run')
    if saved is not None:
        task, _, current, recovered = _task(root, None, reader, from_run=saved['run'])
        if current['input_sha256'] != saved['input_sha256']:
            raise ValueError('saved authoring context no longer matches its source run')
        return task, current, recovered, None, saved['run']
    if reference.get('initial') is True:
        task = copy.deepcopy(context['task_content'])
        if task['task_id'] != reference['task_id']:
            raise ValueError('initial authoring context has a different work task')
        return task, reference, None, None, None
    task_path = reference['path']
    reader.read(reference)
    task, _, current, recovered = _task(root, task_path, reader)
    return task, current, recovered, task_path, None


def build_inputs(root: Path, task_path: str | None, choices_path: str, out_dir: str, *,
                 from_run: str | None = None, runtime_arguments: dict | None = None) -> dict:
    reader = InputEvidence(root, named_roots={'@skill': ROOT})
    choices_ref = reader.select(choices_path)
    choices = read_choices(reader.json(choices_ref))
    if task_path is None and from_run is None:
        base_task, task_ref, saved, task_path, from_run = _choice_source(root, choices_path, reader)
    else:
        base_task, _, task_ref, saved = _task(root, task_path, reader, from_run=from_run)
    task = _chosen_task(base_task, choices)
    _destination(root, out_dir)
    import production_authoring_state
    production_authoring_state.remember_inputs(root, task, 'build-inputs', out_dir,
        task_path=task_path, from_run=from_run, choices_path=choices_path, runtime_arguments=runtime_arguments)
    missing = _unresolved(choices, task)
    if missing:
        return {'state': 'draft', 'ok': False, 'inputs': {}, 'unresolved': missing,
                'derived_from': {'task': task_ref, 'choices': choices_ref},
                'next_actions': [{'operation': 'edit-choices', 'args': {'path': choices_path},
                                  'external_effect': False}]}
    if choices['validation'] is not None:
        import runtime_evidence
        original = reader
        reader = runtime_evidence.reader(root, snapshots=original.snapshots)
        reader.read_paths = original.read_paths
    reading = _reading(choices['reading'], root=root, task=task)
    visual, visual_context = adapters.build_visual(choices['visual'], task, reader, root)
    validation_task = _validation_task(task, choices)
    validation, validation_context = adapters.build_validation(choices['validation'], validation_task, reader, root)
    adapters.cross_check(visual_context, validation_context)
    if validation is not None:
        dialect = validation_context.get('dialect', route_reading._NO_MODEL)
        route_reading.require_route_reading(reading, studio=root, routes={task['route']},
                                           features=task['features'], dialect=dialect)
    content = {'route-reading.json': reading}
    if visual is not None:
        content['visual-continuity.json'] = visual
    if validation is not None:
        content['request-validation.json'] = validation
    try:
        _retained_identity_sources(root, task, choices_path, reader, choices)
        copied_task, authored_files, authored_delivery = authoring.materialize(
            root, task, choices.get('authoring'), reader, out_dir, saved=saved, validation=validation)
    except authoring.UnresolvedChoice as exc:
        return {'state': 'draft', 'ok': False, 'inputs': {},
                'unresolved': [{'field': exc.field, 'code': 'current-judgment-required', 'message': str(exc)}],
                'derived_from': {'task': task_ref, 'choices': choices_ref},
                'next_actions': [{'operation': 'edit-choices', 'args': {'path': choices_path},
                                  'external_effect': False}]}
    _retained_sources(root, saved, copied_task, reader)
    copied_task['route_reading'] = (Path(out_dir) / 'route-reading.json').as_posix()
    if copied_task.get('execution') == 'dispatcher' and copied_task.get('generation') is not None:
        for name, field in (('visual-continuity', 'visual_continuity'), ('request-validation', 'request_validation')):
            if name + '.json' in content:
                copied_task['generation'][field] = (Path(out_dir) / (name + '.json')).as_posix()
    encoded = dict(authored_files)
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
        external_files, external_context = adapters.build_external(
            choices['external'], copied_task, reader, root, out_dir, delivery)
        encoded.update(external_files)
        copied_task['image_input'] = (Path(out_dir) / 'image-input.json').as_posix()
        route_reading.require_route_reading(reading, studio=root, routes={copied_task['route']},
            features=copied_task['features'], dialect=external_context['dialect'])
    else:
        external_context = None
    identity = _identity_view(root, copied_task, reader, files=encoded, out_dir=out_dir)
    identity_gaps = _identity_gaps(identity)
    def recheck():
        _reading(choices['reading'], root=root, task=task)
        _retained_identity_sources(root, task, choices_path, reader, choices)
        _retained_sources(root, saved, copied_task, reader)
        current_visual, _ = adapters.build_visual(choices['visual'], task, reader, root)
        current_validation, _ = adapters.build_validation(choices['validation'], validation_task, reader, root)
        if current_visual != visual or current_validation != validation:
            raise ValueError('selected input evidence changed during construction')
        if external_context is not None:
            current_files, current_context = adapters.build_external(
                choices['external'], copied_task, reader, root, out_dir, delivery)
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
        _publish(root, out_dir, encoded, reader=reader, before_publish=recheck)
        return result
    from production_workflow import validate_task
    validate_task(copied_task)
    encoded['production-task.json'] = c.encoded(copied_task)
    encoded['input-snapshots.json'] = c.encoded(reader.snapshots)
    inputs = {Path(name).stem: {'path': (Path(out_dir) / name).as_posix(),
              'sha256': c.digest(raw)} for name, raw in encoded.items()}
    result = {'state': 'built', 'ok': True, 'inputs': inputs, 'unresolved': [],
              'execution_ready': False,
              'request_state': 'materialized' if external_context is not None else 'not-rendered' if validation is not None else None,
              'derived_from': {'task': task_ref, 'choices': choices_ref,
                               'source_run': saved, 'sources': sorted(reader.read_paths)},
              'changes': [{'field': key, 'before': base_task.get(key), 'after': value}
                          for key, value in copied_task.items() if value != base_task.get(key)],
              'external_input': external_context,
              **({'identity_coverage': identity} if identity is not None else {}),
              'assessment_required': ['Apply the selected quotations to the current rendition and settings.'],
              'next_actions': adapters.next_actions(inputs, copied_task, root, runtime_arguments=runtime_arguments),
              'external_effect': False}
    encoded['input-report.json'] = c.encoded(result)
    _publish(root, out_dir, encoded, reader=reader, before_publish=recheck)
    return result


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
                            execution=args.execution, task_id=args.task_id, features=args.features)
    return build_inputs(root, args.task, args.choices, args.out_dir, from_run=args.from_run, runtime_arguments=runtime_arguments)
