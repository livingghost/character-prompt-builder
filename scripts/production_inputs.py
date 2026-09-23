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


def _task(root: Path, path: str, reader: InputEvidence) -> tuple[dict, dict, dict]:
    ref = reader.select(path)
    value = reader.json(ref)
    if not isinstance(value, dict):
        raise ValueError('production task must be an object')
    for name in ('task_id', 'route'):
        c.text(value.get(name), 'task.' + name)
    features = value.get('features')
    if not isinstance(features, list):
        raise ValueError('task.features must be an explicit array')
    route = execution_routes.resolve(value['route'], features)
    return value, route, ref


def _source_run(root: Path, selected: str | None, task: dict) -> dict | None:
    if selected is None:
        return None
    import production_workflow as workflow
    _, prepared, _, _ = workflow.load_run(root, selected)
    if prepared['task']['task_id'] != task['task_id']:
        raise ValueError('source run belongs to a different work task')
    adapters.check_series(prepared['task'], task)
    from production_resume import report
    current = report(root, selected)
    if not current['integrity']['ok']:
        raise ValueError('source run integrity changed while inspecting its evidence')
    return {'run': selected, 'input_sha256': prepared['input_sha256'],
            'task_path': prepared['task_path'], 'task': prepared['task'],
            'route_reading': copy.deepcopy(prepared.get('route_reading')),
            'freshness': current['freshness'],
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


def inspect_inputs(root: Path, task_path: str, *, from_run: str | None = None) -> dict:
    """Read declarations and saved records without issuing keys or permissions."""
    reader = InputEvidence(root)
    task, route, ref = _task(root, task_path, reader)
    saved = _source_run(root, from_run, task)
    sources = _sources(root, task, reader)
    import craft_consultation
    craft = craft_consultation.navigation(root, task_path, include_scope=task.get('artifact') in {'image', 'video'})
    return {'state': 'inspection', 'task': ref,
            'route': {'id': task['route'], 'features': route['features'],
                      'reads': route['reads']},
            'source_run': saved, 'sources': sources,
            'candidates': adapters.inventory(root, task),
            'craft_lookup': craft,
            'authority': adapters.authority(root, task, saved),
            'required_choices': ['reading', *(['validation'] if adapters.validation_required(task) else [])],
            'choice_templates': {'visual': adapters.visual_template(task),
                                 'validation': adapters.validation_template(task)},
            'judgments': 'Select the route applications, subjects and evidence. Existing choices require current assessment.',
            'external_effect': False, 'budget_effect': 'none'}


def draft_choices(task: dict, *, from_run: str | None = None) -> dict:
    applications = {'snapshot_id': None, 'reading_key': None, 'applied': []}
    if route_reading.RECORD_RESOURCE_FIELDS:
        applications['resource_applied'] = []
    # A null visual or validation choice builds no record here: the Generation
    # Package builder takes continuity decisions and derives request validation.
    return {'reading': applications, 'visual': None,
            'validation': adapters.validation_template(task) if adapters.validation_required(task) else None,
            'source_run': from_run}


def _missing(choices: dict) -> list[dict]:
    """Name unanswered fields while preserving valid explicit null selectors."""
    c.exact(choices, {'reading', 'visual', 'validation', 'source_run'}, 'input choices')
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
    issued = route_reading.resolve_issuance(choices['reading_key'], project=root)
    snapshot = choices['snapshot_id']
    if snapshot is not None:
        route_reading.check_snapshot_issuance(snapshot, issued, project=root)
    applications = {'applied': choices['applied']}
    if route_reading.RECORD_RESOURCE_FIELDS:
        applications['resource_applied'] = choices['resource_applied']
    record = route_reading.build_record(issued, applications, project=root)
    route_reading.require_route_reading(record, project=root,
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


def draft_inputs(root: Path, task_path: str, out_dir: str, *, from_run: str | None = None) -> dict:
    reader = InputEvidence(root)
    task, _, task_ref = _task(root, task_path, reader)
    saved = _source_run(root, from_run, task)
    choices = draft_choices(task, from_run=from_run)
    if saved is not None and saved['route_reading'] is not None:
        previous = saved['route_reading']
        route_reading.validate_record_content(previous)
        choices['reading']['reading_key'] = previous['reading_key']
        choices['reading']['applied'] = copy.deepcopy(previous['applied'])
        if route_reading.RECORD_RESOURCE_FIELDS:
            choices['reading']['resource_applied'] = copy.deepcopy(previous['resource_applied'])
    result = {'state': 'draft', 'choices': choices, 'unresolved': _unresolved(choices, task),
              'derived_from': {'task': task_ref, 'source_run': saved},
              'external_effect': False, 'budget_effect': 'none'}
    _validate_draft(result)
    _publish(root, out_dir, {'choices.json': c.encoded(result)}, reader=reader)
    return {**result, 'choices_file': (Path(out_dir) / 'choices.json').as_posix()}


def _validate_draft(value: dict) -> None:
    from state_protocol import validate_against_schema
    schema = c.load(ROOT / 'schemas/authoring/production-input-draft.schema.json')
    errors = validate_against_schema(value, schema)
    if errors:
        raise ValueError('input draft: ' + '; '.join(errors))


def read_choices(value: Any) -> dict:
    if isinstance(value, dict) and value.get('state') == 'draft':
        # Report fields describe a draft. Builders always recompute unresolved
        # choices and evidence rather than trusting the saved report.
        allowed = {'state', 'choices', 'unresolved', 'derived_from', 'external_effect', 'budget_effect'}
        c.exact(value, allowed, 'draft input document')
        _validate_draft(value)
        return value['choices']
    return value


def build_inputs(root: Path, task_path: str, choices_path: str, out_dir: str, *,
                 from_run: str | None = None, runtime_arguments: dict | None = None) -> dict:
    reader = InputEvidence(root, named_roots={'@skill': ROOT})
    task, route, task_ref = _task(root, task_path, reader)
    choices_ref = reader.select(choices_path)
    choices = read_choices(reader.json(choices_ref))
    missing = _unresolved(choices, task)
    if missing:
        return {'state': 'draft', 'ok': False, 'inputs': {}, 'unresolved': missing,
                'derived_from': {'task': task_ref, 'choices': choices_ref},
                'next_actions': [{'operation': 'edit-choices', 'args': {'path': choices_path},
                                  'external_effect': False, 'budget_effect': 'none'}]}
    if choices['source_run'] != from_run:
        raise ValueError('choices.source_run must match the explicitly selected --from-run')
    saved = _source_run(root, from_run, task)
    if choices['validation'] is not None:
        import runtime_evidence
        original = reader
        reader = runtime_evidence.reader(root, snapshots=original.snapshots)
        reader.read_paths = original.read_paths
    _destination(root, out_dir)
    reading = _reading(choices['reading'], root=root, task=task)
    visual, visual_context = adapters.build_visual(choices['visual'], task, reader, root)
    validation, validation_context = adapters.build_validation(choices['validation'], task, reader, root)
    adapters.cross_check(visual_context, validation_context)
    if validation is not None:
        dialect = validation_context.get('dialect', route_reading._NO_MODEL)
        route_reading.require_route_reading(reading, project=root, routes={task['route']},
                                           features=task['features'], dialect=dialect)
    content = {'route-reading.json': reading}
    if visual is not None:
        content['visual-continuity.json'] = visual
    if validation is not None:
        content['request-validation.json'] = validation
    copied_task = copy.deepcopy(task)
    copied_task['route_reading'] = (Path(out_dir) / 'route-reading.json').as_posix()
    from production_workflow import validate_task
    validate_task(copied_task)
    content['production-task.json'] = copied_task
    content['input-snapshots.json'] = copy.deepcopy(reader.snapshots)
    encoded = {name: c.encoded(value) for name, value in content.items()}
    inputs = {name.removesuffix('.json'): {'path': (Path(out_dir) / name).as_posix(),
              'sha256': c.digest(raw)} for name, raw in encoded.items()}
    result = {'state': 'built', 'ok': True, 'inputs': inputs, 'unresolved': [],
              'execution_ready': False, 'request_state': 'not-rendered' if validation is not None else None,
              'derived_from': {'task': task_ref, 'choices': choices_ref,
                               'source_run': saved, 'sources': sorted(reader.read_paths)},
              'assessment_required': ['Apply the selected quotations to the current rendition and settings.'],
              'next_actions': adapters.next_actions(inputs, task, root, runtime_arguments=runtime_arguments),
              'external_effect': False, 'budget_effect': 'none'}
    encoded['input-report.json'] = c.encoded(result)
    def recheck():
        _reading(choices['reading'], root=root, task=task)
        # Reuse the domain builders, including current adoption and actual
        # reference checks. A concurrent change cannot publish stale bindings.
        current_visual, _ = adapters.build_visual(choices['visual'], task, reader, root)
        current_validation, _ = adapters.build_validation(choices['validation'], task, reader, root)
        if current_visual != visual or current_validation != validation:
            raise ValueError('selected input evidence changed during construction')
    _publish(root, out_dir, encoded, reader=reader, before_publish=recheck)
    return result


def add_arguments(subparsers) -> None:
    for name in sorted(COMMANDS):
        parser = subparsers.add_parser(name, help={
            'inspect-inputs': 'Show declared sources, candidates and required input choices.',
            'draft-inputs': 'Create an unanswered choices document in a new directory.',
            'build-inputs': 'Resolve authored choices into complete inputs without running production.'}[name])
        parser.add_argument('--root', type=Path, required=True)
        parser.add_argument('--task', required=True, help='Project-relative production task JSON.')
        parser.add_argument('--from-run', help='Explicit saved run from the same work task and production.')
        if name != 'inspect-inputs':
            parser.add_argument('--out-dir', required=True, help='New project-relative directory; existing files are preserved.')
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
