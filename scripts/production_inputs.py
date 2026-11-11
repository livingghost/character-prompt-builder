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
from production_diagnostics import ProductionError, choice_required, from_exception, from_unresolved
from production_diagnostics import guidance as phase_guidance

ROOT = Path(__file__).resolve().parents[1]
COMMANDS = frozenset({'inspect-inputs', 'draft-inputs', 'build-inputs'})
# Each kind of identity coverage gap: the field that settles it, what is missing and how to add it.
IDENTITY_GAPS = {
    'uncovered': ('authoring.task.criteria',
        'Identity source values have no criterion binding for every subject they define.',
        'For each listed source, pointer and subject, add an identity_bindings entry to an independent criterion '
        'in authoring.task.criteria that names the source, its subject_ids, a selector covering the pointer, the '
        'scene treatment, a reason and its carriers.'),
    'missing_carriers': ('authoring.task.criteria',
        'Active identity bindings name no carrier in the model input.',
        'Add to the carriers of each listed binding in authoring.task.criteria the text or reference that conveys '
        'it, or give the binding the treatment not-exposed or not-applicable with its reason.'),
    'missing_subject_sources': ('authoring.task.sources',
        'Identity subjects have no identity source.',
        'Declare an identity source for each listed subject in authoring.task.sources, with identity.subject_ids '
        'and identity.selectors, from its adopted definition.'),
    'missing_whole_reviews': ('authoring.task.criteria',
        'Identity subjects have no whole-subject review criterion.',
        'Add a hard criterion to authoring.task.criteria whose identity_review names each listed subject and '
        'compares it with its complete applicable source.'),
    'unknown_subject_ids': ('authoring.task.criteria',
        'Identity sources, bindings or reviews name subjects that the model input does not contain.',
        'Change each listed subject ID in identity.subject_ids, identity_bindings and identity_review of '
        'authoring.task to a Production Specification subject ID, or remove it.'),
    'requires_identity_source': ('authoring.task.sources',
        'The recurring-identity feature is selected, and no identity source is declared.',
        'Declare the adopted identity source in authoring.task.sources with identity.subject_ids and '
        'identity.selectors, or remove recurring-identity from the task features.'),
}


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


class SourceRuns:
    """The source runs one inspection observed, each compared with its current sources once.

    The inspection owns this value and passes it where a run reader is taken.
    Several drafts reopened from one run then share that run's observation.
    Another inspection, and every preparation, observes the run again.
    """

    def __init__(self, read_run):
        self.read_run = read_run
        # The drafts of one inspection resolve their targets against one pack acquisition.
        self.runtime = production_target.SharedRuntime()
        self._observed: dict[str, dict] = {}

    def __call__(self, identifier: str):
        return self.read_run(identifier)

    def observed(self, root: Path, identifier: str) -> dict:
        if identifier not in self._observed:
            self._observed[identifier] = _source_run(root, identifier, read_run=self.read_run)
        return copy.deepcopy(self._observed[identifier])


def _source_run(root: Path, selected: str | None, *, read_run=None) -> dict | None:
    if selected is None:
        return None
    if isinstance(read_run, SourceRuns):
        return read_run.observed(root, selected)
    import production_workflow as workflow
    loaded = read_run(selected) if read_run is not None else workflow.read_run(root, selected)
    prepared = loaded.prepared
    diagnostics, notices = workflow.freshness(root, selected, loaded=loaded)
    return {'run': selected, 'input_sha256': prepared['input_sha256'],
            'task_path': prepared['task_path'], 'task': prepared['task'],
            'target_identity': production_target.prepared_identity(prepared['task'], loaded.artifacts.get('execution-plan.json'),
                loaded.consumer, loaded.artifacts.get('package.json')),
            'route_reading': copy.deepcopy(prepared.get('route_reading')),
            'freshness': {'current': not diagnostics, 'diagnostics': diagnostics, 'notices': notices},
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
    """One IDENTITY_COVERAGE_INCOMPLETE entry per kind of gap, and each failed identity inspection."""
    if value is None:
        return []
    result = [{**diagnostic, 'field': 'authoring.task'} for diagnostic in value.get('diagnostics', [])]
    for key, (field, message, required_action) in IDENTITY_GAPS.items():
        if value.get(key):
            result.append({'field': field, 'code': 'IDENTITY_COVERAGE_INCOMPLETE', 'phase': 'identity-coverage',
                           'message': message, 'required_action': required_action,
                           'guidance': phase_guidance('identity-coverage'), 'gaps': {key: value[key]}})
    return result


def inspect_inputs(root: Path, task_path: str | None = None, *, from_run: str | None = None,
                   choices_path: str | None = None) -> dict:
    """Read declarations and saved records without issuing keys or permissions."""
    if task_path is None and from_run is None:
        import production_authoring_state
        return production_authoring_state.inspect(root, choices=choices_path)
    if choices_path is not None:
        raise ValueError('select saved choices or a task/run source for inspection')
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


def _reading_required(field: str, root: Path, task: dict, choices: dict,
                      runtime_arguments: dict | None) -> dict:
    """The unanswered route reading, with the read command that issues its key."""
    action = _reading_action(root, task, choices, runtime_arguments)
    if field == 'reading':
        message = 'reading is null, so these choices select no completed route reading.'
        value = 'reading to {"reading_key": KEY} with the issued reading.key as KEY'
    else:
        message = 'reading.reading_key is empty, so these choices select no completed route reading.'
        value = 'reading.reading_key to the issued reading.key'
    return choice_required(field, 'reading-required', message,
        'Read the route with ' + action['shown'] + ', run each returned actions.continue until it is null, '
        'then set ' + value + '.',
        {'document_path': 'references/runtime/production-authoring.md#read-the-route-to-completion'},
        next_action=action, next_actions=[action])


def _missing(choices: dict, task: dict, root: Path, runtime_arguments: dict | None) -> list[dict]:
    """Name unanswered fields while preserving valid explicit null selectors."""
    _validate_choices(choices)
    unresolved = []
    reading = choices['reading']
    if reading is None:
        unresolved.append(_reading_required('reading', root, task, choices, runtime_arguments))
    elif not isinstance(reading, dict):
        raise ValueError('reading choices must be an object')
    else:
        if not reading.get('reading_key'):
            unresolved.append(_reading_required('reading.reading_key', root, task, choices, runtime_arguments))
    for field in ('visual', 'validation'):
        if choices[field] is not None and not isinstance(choices[field], dict):
            raise ValueError(field + ' choices must be an object or null')
    if isinstance(choices['visual'], dict):
        subjects = choices['visual'].get('subjects')
        if subjects is not None and not isinstance(subjects, dict):
            raise ValueError('visual.subjects must be an explicit subject map')
        for identifier, subject in (subjects or {}).items():
            if isinstance(subject, dict) and subject.get('continuity') is None:
                field = 'visual.subjects.' + identifier + '.continuity'
                unresolved.append(choice_required(field, 'continuity-choice-required',
                    field + ' is null, so production subject ' + identifier + ' has no continuity decision.',
                    'Set ' + field + ' to the author\'s decision: "undecided" for a single-subject exploration '
                    'before an identity image of a new character is accepted, "recurring" once an accepted '
                    'identity image of its Studio character is among the prepared references (with character_id, '
                    'studio_character and identity_refs), or "one-off" for a subject that does not recur.',
                    {'document_path': 'references/runtime/generation-package.md#generation-package'}))
    unresolved.extend(adapters.unresolved_choices(choices))
    return unresolved


def _unresolved(choices: dict, task: dict, *, root: Path, runtime_arguments: dict | None) -> list[dict]:
    task = _chosen_task(task, choices)
    unresolved = _missing(choices, task, root, runtime_arguments)
    unresolved.extend(production_target.unresolved(choices['target'], task))
    if choices['validation'] is None and adapters.validation_required(task):
        unresolved.append(choice_required('validation', 'selection-required',
            'validation is null, and this dispatcher upscale needs a request-validation selection.',
            'Set validation to {"mode": "target-schema", "contract": null, "evidence": null, '
            '"execution_policy": null} to use the selected offering\'s parameter schema, or select contract and '
            'evidence paths for an acquired schema, a bounded probe or an adopted observed profile.',
            adapters.VALIDATION_GUIDE))
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
            operation='author' if task['execution'] == 'authored' else 'prepare',
            dialect=target.model.get('prompt_dialect'), model_record=model,
            service=(target.offering or {}).get('service'))
    except (ValueError, OSError) as exc:
        action = _reading_action(root, task, choices, runtime_arguments)
        return [{'field': 'reading.reading_key', 'code': 'TARGET_GUIDANCE_REQUIRED',
                 'message': str(exc), 'required_action': 'Read the applicable current guidance and select its issued reading key.',
                 'guidance': phase_guidance('route-reading'),
                 **({'source_changes': exc.as_dict()} if isinstance(exc, route_reading.ReadingSourcesChanged) else {}),
                 'next_action': action, 'next_actions': [action]}]
    return []


def _target_gaps(choices: dict, task: dict, projected: dict) -> list[dict]:
    if task.get('execution') != 'dispatcher' or projected.get('resolved_target') is None:
        return []
    import request_validation
    return request_validation.target_readiness(projected['resolved_target'],
        choices=choices.get('validation'))['unresolved']


def continuation_action(root: Path, task: dict, choices_path: str,
                        runtime_arguments: dict | None, source_run: dict | None,
                        target: dict | None) -> dict:
    """Select continuation from the actual source request and current target."""
    from cli_invocation import python_argv, shown
    command = 'save' if task.get('execution') == 'authored' else 'prepare'
    args = {'root': str(root), 'choices': choices_path, **(runtime_arguments or {})}
    source_task = (source_run or {}).get('task', {})
    previous = (source_run or {}).get('target_identity')
    retarget = (previous is not None and target is not None and previous != target
        and source_task.get('production_id') == task.get('production_id'))
    if retarget:
        command = 'retarget'
        args.update({'from': source_run['run'], 'reason': '<retarget-reason>', 'prepare': True})
    argv = python_argv(ROOT / 'scripts/production_workflow.py', command)
    for key, value in args.items():
        if value is True:
            argv.append('--' + key)
        elif value is not None and value is not False:
            for item in value if isinstance(value, list) else [value]:
                argv.extend(('--' + key, str(item)))
    return {'operation': command, 'command': command, 'script': 'scripts/production_workflow.py',
            'args': args, 'argv': argv, 'shown': shown(argv), 'external_effect': False,
            'requires_author_input': retarget,
            'reason': ('State the actual target-change reason and prepare the new request with its parent run.'
                       if retarget else 'Compile the current editable choices and ' +
                       ('save the authored revision.' if command == 'save' else 'prepare the exact model input.'))}


def _draft_actions(root: Path, task: dict, choices: dict, gaps: list[dict],
                   out_dir: str, runtime_arguments: dict | None, saved: dict | None,
                   projected: dict) -> list[dict]:
    actions = []
    for gap in gaps:
        for action in gap.get('next_actions', []):
            if action not in actions:
                actions.append(action)
    if any(item['field'].startswith('reading') for item in gaps) and not any(
            item.get('operation') == 'read' for item in actions):
        actions.append(_reading_action(root, task, choices, runtime_arguments))
    path = (Path(out_dir) / 'choices.json').as_posix()
    if not gaps:
        actions.append(continuation_action(root, task, path, runtime_arguments, saved,
                                          production_target.projected_identity(projected)))
    else:
        actions.append({'operation': 'edit-choices', 'args': {'path': path},
                        'unresolved_fields': [row['field'] for row in gaps], 'external_effect': False})
    return actions


def _reading(choices: dict, *, root: Path, task: dict) -> dict:
    c.exact(choices, {'reading_key'}, 'reading choices')
    issued = route_reading.resolve_issuance(choices['reading_key'], studio=root)
    record = route_reading.build_record(issued, studio=root,
        operation='author' if task.get('execution') == 'authored' else 'prepare',
        execution=task['execution'], features=task['features'])
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


def _captured_image_source(root: Path, run: str, candidate: str) -> dict:
    """Select one retained candidate and verify its actual image bytes."""
    import production_workflow
    from production_evidence import inspect
    loaded = production_workflow.read_run(root, run)
    row = production_workflow.find(loaded.rows, 'candidate', candidate)
    files = row['data']['files']
    if len(files) != 1:
        raise ValueError('the selected candidate must contain one image; choose an explicit image file for other artifacts')
    item = files[0]
    raw = loaded.evidence.read(item['sha256'])
    measured = inspect(raw, 'image')
    if measured['format'] == 'SVG':
        raise ValueError('upscale source must be an existing raster image')
    try:
        reviewed = production_workflow.latest_review(loaded.rows, candidate)['sha256']
    except ValueError:
        reviewed = None
    return {'run': run, 'candidate': candidate, 'input_sha256': loaded.prepared['input_sha256'],
            'request_sha256': (loaded.artifacts.get('execution-plan.json') or {}).get('request_sha256'),
            'file': {'path': (loaded.directory / 'objects' / item['sha256']).relative_to(root).as_posix(),
                     'sha256': item['sha256'], 'size': len(raw)}, 'review': reviewed, 'media': measured}


def draft_inputs(root: Path, task_path: str | None, out_dir: str, *, from_run: str | None = None,
                 runtime_arguments: dict | None = None, route: str | None = None,
                 artifact: str | None = None, execution: str | None = None,
                 task_id: str | None = None, features: list[str] | None = None,
                 model: str | None = None, service: str | None = None,
                 source_image: Path | None = None, scale: float | None = None,
                 purpose: str | None = None, new_task: str | None = None,
                 source_run: str | None = None, source_candidate: str | None = None) -> dict:
    _destination(root, out_dir)
    reader = InputEvidence(root)
    initial = task_path is None and from_run is None
    source_result = None
    if source_run is not None or source_candidate is not None:
        if source_run is None or source_candidate is None:
            raise ValueError('select both --source-run and --source-candidate for a captured image')
        if not initial or route != 'upscale' or source_image is not None:
            raise ValueError('a captured image selects a new upscale input; use --route upscale without --task, --from-run or --source-image')
        if execution not in {None, 'dispatcher'}:
            raise ValueError('captured image inputs use dispatcher upscale execution')
        source_result = _captured_image_source(root, source_run, source_candidate)
        source_image = Path(source_result['file']['path'])
    if not initial and any(value is not None for value in (route, artifact, execution, features)):
        from cli_invocation import python_argv, shown
        arguments = ['--root', str(root), *(['--from-run', from_run] if from_run else ['--task', task_path]),
                     '--out-dir', out_dir]
        for key, value in {'task-id': task_id, 'new-task': new_task, 'model': model, 'service': service,
                           'source-image': source_image, 'scale': scale, 'purpose': purpose,
                           **(runtime_arguments or {})}.items():
            if value is not None:
                for item in value if isinstance(value, list) else [value]:
                    arguments.extend(('--' + key, str(item)))
        argv = python_argv(ROOT / 'scripts/production_workflow.py', 'draft-inputs', *arguments)
        fields = {'authoring.task.' + key: value for key, value in
                  {'route': route, 'artifact': artifact, 'execution': execution, 'features': features}.items()
                  if value is not None}
        raise ProductionError('INPUT_CONSISTENCY_ERROR',
            'Initial task flags cannot replace a selected task or run. Reopen its editable input before changing its scope.',
            phase='authoring-context', requested_fields=fields,
            choices_file=(Path(out_dir) / 'choices.json').as_posix(),
            required_action='Run the supplied draft-inputs action, then apply the requested scope at the listed '
                            'authoring.task fields in choices.json. Preserve still-applicable feature selections; '
                            'inspect-inputs validates the edited scope and supplies its read action.',
            next_actions=[{'operation': 'draft-inputs', 'argv': argv, 'shown': shown(argv),
                'external_effect': False, 'reason': 'Restore the selected source without discarding its authored content.'}])
    selected_source = _task(root, task_path, reader, from_run=from_run) if not initial else None
    import production_authoring_state
    import work_ledger
    # Work this call opens. The draft is built for its reserved ID first; the
    # task is opened only when every selected input has produced that draft.
    opening = None
    if new_task is not None:
        if task_id is not None:
            raise ValueError('select --new-task or --task-id, not both')
        if initial and source_result is None:
            raise ValueError('--new-task reopens a selected task or run; start initial work with work_ledger begin')
        opening = (c.text(new_task, 'new work goal'),
                   ['Prepare the requested revision.', 'Assess and finish the selected result.'])
    elif not initial and task_id is not None:
        if production_authoring_state.active_task_id(root)!=task_id:
            raise ValueError('--task-id must select the current open work task when reopening inputs')
    elif (initial and route == 'upscale' and purpose is not None and task_id is None
            and production_authoring_state.active_task_id(root) is None):
        opening = (c.text(purpose, 'upscale purpose'),
                   ['Prepare the requested enlargement.', 'Save and assess the returned image.'])
    if opening is not None:
        work_ledger.require_beginnable(root, *opening)
        task_id = work_ledger.new_task_id(root)

    def open_work() -> None:
        if opening is not None:
            work_ledger.begin(root, *opening, task_id=task_id)
    if initial:
        if route is None:
            raise ValueError('select --route for initial production authoring')
        task = authoring.seed(root, route=route, artifact=artifact or ('image' if route == 'upscale' else 'text'),
                              execution=execution or ('dispatcher' if route == 'upscale' else 'authored'),
                              task_id=task_id, features=features)
        task_ref, saved = {'initial': True, 'task_id': task['task_id']}, None
    else:
        task, _, task_ref, saved = selected_source
    if from_run is not None and task_id is None:
        active = production_authoring_state.active_task_id(root)
        if active != task['task_id']:
            from cli_invocation import python_argv, shown
            arguments = ['--root', str(root), *(['--from-run', from_run] if from_run else ['--task', task_path]),
                         '--out-dir', out_dir]
            arguments += ['--task-id', active] if active else ['--new-task', '<revision-goal>']
            for key, value in {'model': model, 'service': service, 'source-image': source_image,
                               'scale': scale, 'purpose': purpose}.items():
                if value is not None:
                    arguments.extend(('--' + key, str(value)))
            for key, value in (runtime_arguments or {}).items():
                for item in value if isinstance(value, list) else [value]:
                    arguments.extend(('--' + key, str(item)))
            argv = python_argv(ROOT / 'scripts/production_workflow.py', 'draft-inputs', *arguments)
            raise ProductionError('AUTHORING_TASK_SELECTION_REQUIRED',
                'The selected source belongs to another work task. Select the current task or open new revision work.',
                phase='authoring', required_action=shown(argv),
                guidance={'document_path': 'references/runtime/production-authoring.md#keep-branches-and-reopen-completed-work'},
                source_task_id=task['task_id'], active_task_id=active,
                next_actions=[{'operation': 'draft-inputs', 'argv': argv, 'shown': shown(argv),
                    'requires_author_input': active is None, 'external_effect': False,
                    'reason': 'Use the stated revision goal for a new task while retaining the source result.'
                              if active is None else 'Explicitly bind this source to the open work task.'}])
    if from_run is not None:
        import production_authored
        unfinished = production_authored.draft_source(root, from_run)
        if unfinished is not None:
            return _restore_draft(root, from_run, out_dir, unfinished,
                task_id=task_id, runtime_arguments=runtime_arguments, model=model, service=service,
                source_image=source_image, scale=scale, purpose=purpose, open_work=open_work)
    choices = draft_choices(task)
    choices['authoring'] = authoring.draft(root, task, reader, saved=saved, initial=initial)
    imported, selected_image = authoring.select_upscale(root, choices['authoring'], out_dir,
        source_image=source_image, scale=scale, purpose=purpose)
    if source_result is not None:
        if selected_image['sha256'] != source_result['file']['sha256']:
            raise ValueError('the selected captured image changed during drafting')
        selected_image.update(source_run=source_result['run'], source_candidate=source_result['candidate'])
    if not initial and task_id is not None:
        task = _bind_task(task, task_id)
        choices['authoring']['task'] = _bind_task(choices['authoring']['task'], task_id)
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
    editable=dict(imported)
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
    chosen = _chosen_task(task, choices)
    identity = _identity_view(root, chosen, reader, saved=saved, files=editable, out_dir=out_dir)
    projected = production_target.project(choices, chosen, root, reader, out_dir)
    gaps = _unresolved(choices, task, root=root, runtime_arguments=runtime_arguments) + _identity_gaps(identity)
    gaps.extend(item for item in projected['unresolved'] if item not in gaps)
    gaps.extend(_target_gaps(choices, chosen, projected))
    gaps.extend(_guidance_gap(root, task, choices, projected, runtime_arguments))
    actions = _draft_actions(root, chosen, choices, gaps, out_dir, runtime_arguments, saved, projected)
    result = {'state': 'draft', 'choices': choices,
              'unresolved': gaps, 'target_knowledge': projected['knowledge'], 'next_actions': actions,
              'selected_image': selected_image,
              **({'identity_coverage': identity} if identity is not None else {}),
              'derived_from': {'task': task_ref, 'source_run': saved},
              'external_effect': False}
    _validate_choices(choices)
    context = {key: value for key, value in result.items() if key != 'choices'}
    context['task_content'] = task
    if source_result is not None:
        context['source_result'] = source_result
    if not initial and task_id is not None:
        context['task_binding']={'task_id':task_id}
    context_raw = c.encoded(context)
    _destination(root, out_dir)
    open_work()
    production_authoring_state.remember_inputs(root, task, 'draft-inputs', out_dir,
        task_path=task_path, from_run=from_run, runtime_arguments=runtime_arguments,
        context_sha256=c.digest(context_raw), input_arguments=({key: str(value) for key, value in {
            'source-run': source_run, 'source-candidate': source_candidate,
            'source-image': source_image if source_result is None else None, 'scale': scale,
            'purpose': purpose, 'model': model, 'service': service}.items() if value is not None} if initial else None))
    _publish(root, out_dir, {**editable,'choices.json': c.encoded(choices),
                            'context.json': context_raw}, reader=reader)
    production_authoring_state.published_draft(root, task, out_dir)
    return {**result, 'choices_file': (Path(out_dir) / 'choices.json').as_posix(),
            'context_file': (Path(out_dir) / 'context.json').as_posix()}


def _bind_task(task: dict, task_id: str) -> dict:
    """Carry creative input into the selected task without importing another task's grant."""
    result = copy.deepcopy(task)
    if result['task_id'] != task_id:
        result['authority'] = None
        result.pop('execution_decisions', None)
    result['task_id'] = task_id
    return result


def _restore_draft(root: Path, run: str, out_dir: str, saved_source: dict, *,
                   task_id: str | None, runtime_arguments: dict | None,
                   model: str | None = None, service: str | None = None,
                   source_image: Path | None = None, scale: float | None = None,
                   purpose: str | None = None, open_work=lambda: None) -> dict:
    """Reopen the captured editor files, preserving JSON selectors and unfinished choices."""
    import production_authoring_state
    choices=copy.deepcopy(saved_source['choices'])
    task=copy.deepcopy(saved_source['task'])
    authored=choices['authoring']
    if task_id is not None:
        task=_bind_task(task,task_id)
        authored['task']=_bind_task(authored['task'],task_id)
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
    imported, selected_image = authoring.select_upscale(root, authored, out_dir,
        source_image=source_image, scale=scale, purpose=purpose)
    files.update(imported)
    saved=_source_run(root,run)
    reference={'run':run,'input_sha256':saved['input_sha256']}
    unresolved=_unresolved(choices,task,root=root,runtime_arguments=runtime_arguments)
    for item in unresolved:
        if item.get('file') in locations:
            item['file']=locations[item['file']]
    with _staged_files(root, out_dir, files):
        projected = production_target.project(choices, _chosen_task(task, choices), root,
                                              InputEvidence(root, named_roots={'@skill': ROOT}), out_dir)
        unresolved.extend(item for item in projected['unresolved'] if item not in unresolved)
        unresolved.extend(_target_gaps(choices, _chosen_task(task, choices), projected))
        unresolved.extend(_guidance_gap(root, task, choices, projected, runtime_arguments))
    actions = _draft_actions(root, _chosen_task(task, choices), choices, unresolved, out_dir,
                            runtime_arguments, saved, projected)
    result={'state':'draft','choices':choices,'unresolved':unresolved,
        'target_knowledge':projected['knowledge'],'next_actions':actions,'selected_image':selected_image,
        'derived_from':{'task':reference,'source_run':saved},'external_effect':False}
    context={key:value for key,value in result.items() if key!='choices'}
    context['task_content']=task
    if task_id is not None:
        context['task_binding']={'task_id':task_id}
    _validate_choices(choices)
    raw=c.encoded(context)
    _destination(root,out_dir)
    open_work()
    production_authoring_state.remember_inputs(root,task,'draft-inputs',out_dir,
        task_path=None,from_run=run,runtime_arguments=runtime_arguments,context_sha256=c.digest(raw))
    _publish(root,out_dir,{**files,'choices.json':c.encoded(choices),'context.json':raw},
        reader=InputEvidence(root))
    production_authoring_state.published_draft(root,task,out_dir)
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
        return _bind_task(task,binding['task_id'])
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


def _authoring_source(root: Path, choices_path: str, reader: InputEvidence, choices: dict, *,
                      task_path: str | None = None, from_run: str | None = None,
                      read_run=None) -> tuple[dict, dict, dict | None, str | None, str | None]:
    """Resolve an explicit source and a registered task binding through one owner."""
    if task_path is None and from_run is None:
        return _choice_source(root, choices_path, reader, choices=choices, read_run=read_run)
    base, _, origin, saved = _task(root, task_path, reader, from_run=from_run, read_run=read_run)
    context_path = (Path(choices_path).parent / 'context.json').as_posix()
    if choices.get('authoring') is not None and c.local(root, context_path, exists=False).is_file():
        bound = _choice_source(root, choices_path, reader, choices=choices, read_run=read_run)
        if origin != bound[1]:
            raise ValueError('explicit source differs from the registered choices source')
        return bound
    return base, origin, saved, task_path, from_run


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
    base,origin,saved,task_path,from_run=_authoring_source(root,choices_path,reader,choices,
        task_path=task_path,from_run=from_run,read_run=read_run)
    task=_chosen_task(base,choices)
    projected = production_target.project(choices, task, root, reader,
                                          (Path(choices_path).parent / 'view').as_posix(),
                                          source=read_run.runtime if isinstance(read_run, SourceRuns) else None)
    task = projected['task']
    for source in task.get('sources',[]):
        path=source.get('path')
        if not path:continue
        try:reader.read(reader.select(path))
        except (ValueError,OSError) as exc:
            gaps.append({'field':'authoring.task.sources','file':path,'code':'INPUT_UNREADABLE','cause':str(exc),
                'phase':'source-read','message':'The task source '+path+' cannot be read.',
                'required_action':'Restore '+path+' as a readable file, or change or remove its row in '
                    'authoring.task.sources.','guidance':phase_guidance('source-read')})
    basis = _authored_basis(root, task, base, reader, saved, allow_missing=True)
    unresolved=_unresolved(choices,task,root=root,runtime_arguments=runtime_arguments)+gaps
    unresolved.extend(item for item in projected['unresolved'] if item not in unresolved)
    unresolved.extend(_target_gaps(choices, task, projected))
    unresolved.extend(_guidance_gap(root, task, choices, projected, runtime_arguments))
    content=((choices.get('authoring') or {}).get('delivery') or {}).get('content')
    delivery=b'' if content is None else content.encode('utf-8') if isinstance(content,str) else c.encoded(content)
    captured={path:reader._decode(value) for path,value in reader.snapshots.items() if not path.startswith('@')}
    return {'task':task,'choices':c.decode(captured[choices_path]),'resolved_choices':choices,
        'files':{},'delivery':delivery,'unresolved':unresolved,'source_map':locations,'captured':captured,
        'origin':origin,'source_run':saved,'task_path':task_path,'from_run':from_run,'choices_ref':ref,
        'authored_basis':basis,'target_knowledge':projected['knowledge'],
        'target_identity':production_target.projected_identity(projected)}


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
    base_task, task_ref, saved, task_path, from_run = _authoring_source(
        root, choices_path, reader, choices, task_path=task_path, from_run=from_run)
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
    missing = _unresolved(choices, task, root=root, runtime_arguments=runtime_arguments)+file_gaps
    missing.extend(item for item in projected['unresolved'] if item not in missing)
    missing.extend(_target_gaps(choices, task, projected))
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
                                           features=task['features'], execution=task['execution'], dialect=dialect,
                                           operation='author' if task['execution'] == 'authored' else 'prepare')
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
                'unresolved': [exc.as_unresolved()],
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
    context_path = (Path(choices_path).parent / 'context.json').as_posix()
    context_snapshot = reader.snapshots.get(context_path)
    context = c.decode(reader._decode(context_snapshot)) if context_snapshot is not None else {}
    if context.get('source_result') is not None:
        result['derived_from']['source_result'] = context['source_result']
    if choices.get('authoring') is not None and context and (saved is not None or context.get('source_result')):
        result['next_actions'][0] = continuation_action(root, copied_task, choices_path,
            runtime_arguments, saved, production_target.projected_identity(projected))
    encoded['input-report.json'] = c.encoded(result)
    if publish:
        production_authoring_state.remember_inputs(root, copied_task, 'build-inputs', out_dir,
            task_path=task_path, from_run=from_run, choices_path=choices_path, runtime_arguments=runtime_arguments,
            publication={'task': (Path(out_dir) / 'production-task.json').as_posix(),
                'task_sha256': c.digest(encoded['production-task.json']),
                'report': (Path(out_dir) / 'input-report.json').as_posix(),
                'report_sha256': c.digest(encoded['input-report.json'])})
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
            # Each unresolved entry already states its choice, its repair and the section that explains it.
            diagnostics = assembled.get('diagnostics') or [
                from_unresolved(item, file=choices_path) for item in assembled.get('unresolved', [])]
            return compiler.Compilation({'ok':False,'publishable':False,'run':None,'diagnostics':diagnostics,
                'checks':[], 'authoring':assembled,
                'external_effect':False,'formal_run_created':False})
        path=(Path(output)/'production-task.json').as_posix()
        compiled=compiler.compile_task(root,path,persist=persist,identity=identity,
            derived=assembled['_files'],source_inputs=assembled['_captured'])
        compiled.report['authoring']={'choices':choices_path,
            'choices_ref':assembled['derived_from']['choices'],'source_map':assembled['_source_map'],
            'source_run': (assembled['derived_from'].get('source_run') or {}).get('run')}
        context_path = (Path(choices_path).parent / 'context.json').as_posix()
        context_raw = assembled['_captured'].get(context_path)
        if context_raw is not None:
            source_result = c.decode(context_raw).get('source_result')
            if source_result is not None:
                # The source declaration follows its selected bytes. A later
                # explicit image replacement keeps its own input and does not
                # claim to enlarge the old candidate.
                actual = (compiled.package or {}).get('source') or {}
                if actual.get('sha256') == source_result['file']['sha256']:
                    compiled.report['authoring']['source_result'] = source_result
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
        return compiler.Compilation({'ok':False,'publishable':False,'run':None,'diagnostics':[
            from_exception(exc,phase='authoring',file=choices_path)],'checks':[],
            'external_effect':False,'formal_run_created':False})


def compilation_parent(root: Path, compiled) -> dict | None:
    """Derive lineage from the registered editing source and the exact new input."""
    if not compiled.report.get('publishable') or compiled.prepared is None:
        return None
    authored = (compiled.prepared or {}).get('authoring') or compiled.report.get('authoring') or {}
    result_source = authored.get('source_result')
    if result_source is not None:
        checked = _captured_image_source(root, result_source['run'], result_source['candidate'])
        if any(checked[key] != result_source[key] for key in ('input_sha256', 'file')):
            raise ValueError('the captured source differs from the registered upscale selection')
        return {'run': checked['run'], 'input_sha256': checked['input_sha256'],
                'request_sha256': checked['request_sha256'], 'kind': 'upscale',
                'reason': 'Enlarge the explicitly selected captured image.',
                'changes': [{'field': 'operation', 'before': 'captured-image', 'after': 'upscale'}],
                'basis': [{'candidate': checked['candidate'], 'review': result_source['review']}]}
    source = authored.get('source_run')
    if source is None:
        return None
    import production_workflow
    loaded = production_workflow.read_run(root, source)
    before, after = loaded.prepared, compiled.prepared
    if before['task']['production_id'] != after['task']['production_id']:
        raise ValueError('a source revision retains its production series')
    previous = loaded.artifacts.get('execution-plan.json') or {}
    changes = []
    if before['task']['task_id'] != after['task']['task_id']:
        changes.append({'field': 'task', 'before': before['task']['task_id'], 'after': after['task']['task_id']})
    if before['input_sha256'] != after['input_sha256']:
        changes.append({'field': 'input', 'before': before['input_sha256'], 'after': after['input_sha256']})
    return {'run': source, 'input_sha256': before['input_sha256'],
            'request_sha256': previous.get('request_sha256'), 'kind': 'revision',
            'reason': 'Prepared from the explicitly selected saved input and current editable choices.',
            'changes': changes, 'basis': []}


def export_parent(root: Path, task_path: str, compiled) -> dict | None:
    """Retain verified source lineage when an exported task is prepared directly."""
    if not compiled.report.get('publishable'):
        return None
    import production_authoring_state
    import production_store
    publication = production_authoring_state.input_publication(root,
        compiled.prepared['task']['task_id'], task_path)
    if publication is None:
        return None
    acquired = {item['path']: item.get('selection_sha256', item['sha256'])
                for item in compiled.prepared['dependencies'] if item['space'] in authoring.AUTHORING_SPACES}
    def unchanged(path, expected, *, fresh=False):
        raw = production_store.stable_bytes(root, path) if fresh or path not in acquired else None
        actual = c.digest(raw) if raw is not None else acquired[path]
        if actual != expected:
            raise ProductionError('INPUT_PUBLICATION_CHANGED',
                'The exported input differs from its registered publication.', phase='authoring-context',
                file=path, required_action='Edit the owning choices and build a new export directory; keep published input files intact.')
        return raw
    unchanged(task_path, publication['task_sha256'])
    report = c.decode(unchanged(publication['report'], publication['report_sha256'], fresh=True))
    for value in report['inputs'].values():
        unchanged(value['path'], value['sha256'])
    origin = report['derived_from']
    authored = {'choices': origin['choices']['path'], 'choices_ref': origin['choices'],
                'source_run': (origin.get('source_run') or {}).get('run')}
    source_result = origin.get('source_result')
    if source_result is not None and (compiled.package or {}).get('source', {}).get('sha256') == source_result['file']['sha256']:
        authored['source_result'] = source_result
    compiled.prepared['authoring'] = copy.deepcopy(authored)
    compiled.report['authoring'] = authored
    return compilation_parent(root, compiled)


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
        if name == 'inspect-inputs':
            parser.add_argument('--choices', help='Select this registered editable draft when several are pending.')
        if name == 'draft-inputs':
            image_source = parser.add_mutually_exclusive_group()
            image_source.add_argument('--source-image', type=Path,
                help='Existing raster image, Studio-relative or an absolute local path to import.')
            image_source.add_argument('--source-candidate', help='Exact captured candidate ID to enlarge.')
            parser.add_argument('--source-run', help='Run owning the selected --source-candidate for a new upscale input.')
            parser.add_argument('--scale', type=float, help='Requested upscale factor.')
            parser.add_argument('--purpose', help='Actual upscale request; initializes unanswered purpose and criteria.')
            parser.add_argument('--model',help='Select the canonical model in a new or reopened draft.')
            parser.add_argument('--service',help='Select the offering service in a new or reopened draft.')
            parser.add_argument('--route', help='Initial production route; no prebuilt task is needed.')
            parser.add_argument('--artifact', dest='artifact_kind',
                choices=('text', 'json', 'image', 'video', 'audio', 'binary'),
                help='Initial output kind; defaults to image for upscale, otherwise text. Existing tasks retain their kind.')
            parser.add_argument('--execution', choices=('authored', 'external', 'dispatcher'),
                help='Initial execution method; defaults to dispatcher for upscale, otherwise authored. Existing tasks retain their method.')
            parser.add_argument('--task-id', help='Existing work task ID; defaults to the open work task.')
            parser.add_argument('--new-task', metavar='GOAL',
                help='Open a new work task for this selected saved source; preserves the earlier task and completion.')
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
        return inspect_inputs(root, choices_path=args.choices)
    runtime_arguments = adapters.configure_runtime(args, parser)
    if args.command == 'inspect-inputs':
        result = inspect_inputs(root, args.task, from_run=args.from_run, choices_path=args.choices)
        for action in result['craft_lookup']['next_actions']:
            action['args'].update(runtime_arguments or {})
        return result
    if args.command == 'draft-inputs':
        return draft_inputs(root, args.task, args.out_dir, from_run=args.from_run,
                            runtime_arguments=runtime_arguments, route=args.route, artifact=args.artifact_kind,
                            execution=args.execution, task_id=args.task_id, features=args.features,
                            model=args.model,service=args.service,source_image=args.source_image,
                            scale=args.scale,purpose=args.purpose,new_task=args.new_task,
                            source_run=args.source_run,source_candidate=args.source_candidate)
    return build_inputs(root, args.task, args.choices, args.out_dir, from_run=args.from_run, runtime_arguments=runtime_arguments)
