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


def inspect_inputs(root: Path, task_path: str | None = None, *, from_run: str | None = None) -> dict:
    """Read declarations and saved records without issuing keys or permissions."""
    reader = InputEvidence(root)
    task, route, ref, saved = _task(root, task_path, reader, from_run=from_run)
    sources = _sources(root, task, reader)
    import craft_consultation
    craft = (craft_consultation.navigation(root, task_path, include_scope=task.get('artifact') in {'image', 'video'})
             if task_path is not None else {'next_actions': [], 'source_run': from_run})
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
            'judgments': 'Select the route applications, subjects and evidence. Existing choices require current assessment.',
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


def _unresolved(choices: dict, task: dict) -> list[dict]:
    unresolved = _missing(choices)
    if choices['validation'] is None and adapters.validation_required(task):
        unresolved.append({'field': 'validation', 'code': 'selection-required'})
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


def draft_inputs(root: Path, task_path: str | None, out_dir: str, *, from_run: str | None = None) -> dict:
    reader = InputEvidence(root)
    task, _, task_ref, saved = _task(root, task_path, reader, from_run=from_run)
    choices = draft_choices(task)
    if saved is not None and saved['route_reading'] is not None:
        previous = saved['route_reading']
        route_reading.validate_record_content(previous)
        choices['reading']['reading_key'] = previous['reading_key']
        choices['reading']['applied'] = copy.deepcopy(previous['applied'])
        if route_reading.RECORD_RESOURCE_FIELDS:
            choices['reading']['resource_applied'] = copy.deepcopy(previous['resource_applied'])
    result = {'state': 'draft', 'choices': choices, 'unresolved': _unresolved(choices, task),
              'derived_from': {'task': task_ref, 'source_run': saved},
              'external_effect': False}
    _validate_choices(choices)
    context = {key: value for key, value in result.items() if key != 'choices'}
    context['task_content'] = task
    _publish(root, out_dir, {'choices.json': c.encoded(choices),
                            'context.json': c.encoded(context)}, reader=reader)
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
                          'world_views', 'moment_views', 'scene_materials', 'semantic_edit', 'generation'})


def _chosen_task(task: dict, choices: dict) -> dict:
    changes = choices['task_changes']
    if not isinstance(changes, dict) or set(changes) - TASK_CHOICES:
        raise ValueError('task_changes names only authored route, source, depiction or review fields')
    result = copy.deepcopy(task)
    result.update(copy.deepcopy(changes))
    if choices['external'] is not None:
        if task.get('execution') == 'dispatcher':
            raise ValueError('select an authored or external task for external input assembly')
        result.update(artifact='image', execution='external',
                      image_input=choices['external']['image_input'])
    return result


def _saved_delivery(root: Path, saved: dict, task: dict) -> bytes | None:
    if task['delivery'] != saved['task']['delivery']:
        return None
    import production_workflow as workflow
    directory, prepared, _, _ = workflow.load_run(root, saved['run'])
    if prepared['input_sha256'] != saved['input_sha256']:
        raise ValueError('source run input changed during input construction')
    path = task['delivery']['path']
    matches = [row for row in prepared['dependencies'] if row['space'] != 'skill' and row['path'] == path]
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
    paths.discard(saved['task']['delivery']['path'])
    previous = {row['path']: row for row in prepared['dependencies']
                if row['space'] not in {'skill', 'evidence'}}
    for path in sorted(paths & previous.keys()):
        reader.read({'path': path, 'sha256': previous[path]['sha256']})


def build_inputs(root: Path, task_path: str | None, choices_path: str, out_dir: str, *,
                 from_run: str | None = None, runtime_arguments: dict | None = None) -> dict:
    reader = InputEvidence(root, named_roots={'@skill': ROOT})
    base_task, _, task_ref, saved = _task(root, task_path, reader, from_run=from_run)
    choices_ref = reader.select(choices_path)
    choices = read_choices(reader.json(choices_ref))
    task = _chosen_task(base_task, choices)
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
    _destination(root, out_dir)
    _retained_sources(root, saved, task, reader)
    reading = _reading(choices['reading'], root=root, task=task)
    visual, visual_context = adapters.build_visual(choices['visual'], task, reader, root)
    validation, validation_context = adapters.build_validation(choices['validation'], task, reader, root)
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
    copied_task = copy.deepcopy(task)
    copied_task['route_reading'] = (Path(out_dir) / 'route-reading.json').as_posix()
    if copied_task.get('execution') == 'dispatcher' and copied_task.get('generation') is not None:
        for name, field in (('visual-continuity', 'visual_continuity'), ('request-validation', 'request_validation')):
            if name + '.json' in content:
                copied_task['generation'][field] = (Path(out_dir) / (name + '.json')).as_posix()
    encoded = {name: c.encoded(value) for name, value in content.items()}
    delivery = _saved_delivery(root, saved, task) if saved is not None else None
    if delivery is not None:
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
              'assessment_required': ['Apply the selected quotations to the current rendition and settings.'],
              'next_actions': adapters.next_actions(inputs, copied_task, root, runtime_arguments=runtime_arguments),
              'external_effect': False}
    encoded['input-report.json'] = c.encoded(result)
    def recheck():
        _reading(choices['reading'], root=root, task=task)
        _retained_sources(root, saved, task, reader)
        current_visual, _ = adapters.build_visual(choices['visual'], task, reader, root)
        current_validation, _ = adapters.build_validation(choices['validation'], task, reader, root)
        if current_visual != visual or current_validation != validation:
            raise ValueError('selected input evidence changed during construction')
        if external_context is not None:
            current_files, current_context = adapters.build_external(
                choices['external'], copied_task, reader, root, out_dir, delivery)
            if current_files != external_files or current_context != external_context:
                raise ValueError('selected external input changed during construction')
    _publish(root, out_dir, encoded, reader=reader, before_publish=recheck)
    return result


def add_arguments(subparsers) -> None:
    for name in sorted(COMMANDS):
        parser = subparsers.add_parser(name, help={
            'inspect-inputs': 'Show declared sources, candidates and required input choices.',
            'draft-inputs': 'Create an unanswered choices document in a new directory.',
            'build-inputs': 'Resolve authored choices into complete inputs without running production.'}[name])
        parser.add_argument('--root', type=Path, required=True)
        source = parser.add_mutually_exclusive_group(required=True)
        source.add_argument('--task', help='Studio-relative authored production task JSON.')
        source.add_argument('--from-run', help='Use the saved task and delivery of this existing run.')
        if name != 'inspect-inputs':
            parser.add_argument('--out-dir', required=True, help='New studio-relative directory; existing files are preserved.')
        if name == 'build-inputs':
            parser.add_argument('--choices', required=True, help='Edited choices.json from draft-inputs, or a complete choices object.')
        adapters.add_runtime_arguments(parser)


def command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> dict:
    runtime_arguments = adapters.configure_runtime(args, parser)
    root = args.root.resolve(strict=True)
    if args.command == 'inspect-inputs':
        result = inspect_inputs(root, args.task, from_run=args.from_run)
        for action in result['craft_lookup']['next_actions']:
            action['args'].update(runtime_arguments or {})
        return result
    if args.command == 'draft-inputs':
        return draft_inputs(root, args.task, args.out_dir, from_run=args.from_run)
    return build_inputs(root, args.task, args.choices, args.out_dir, from_run=args.from_run, runtime_arguments=runtime_arguments)
