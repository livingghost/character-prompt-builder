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
from contextlib import contextmanager, nullcontext

import execution_contract as c
import execution_routes
from input_evidence import InputEvidence
import route_reading
import production_input_adapters as adapters
import production_authoring as authoring
import production_authoring_work as authoring_work
import production_edit_inputs
import production_target
import production_reading_scope as reading_scope
import production_input_preflight as input_preflight
from production_diagnostics import ProductionError, choice_required, from_exception, from_unresolved
from production_diagnostics import guidance as phase_guidance

ROOT = Path(__file__).resolve().parents[1]
# Each kind of identity coverage gap: the field that settles it, what is missing and how to add it.
IDENTITY_GAPS = {
    'missing_carriers': ('authoring.task.criteria',
        'Active identity bindings name no carrier in the model input.',
        'Add to the carriers of each listed binding in authoring.task.criteria the text or reference that conveys '
        'it, or give the binding the treatment not-exposed or not-applicable with its reason.'),
    'missing_subject_sources': ('authoring.task.sources',
        'Identity subjects have no identity source.',
        'Acquire each adopted definition with scripts/production_workflow.py acquire-source --root STUDIO '
        '--choices CHOICES --source-row SOURCE_ROW. Declare its actual role, identity.subject_ids and '
        'identity.selectors in that source row; the builder derives task sources and applications.'),
    'missing_whole_reviews': ('authoring.task.criteria',
        'Identity subjects have no whole-subject review criterion.',
        'Add a hard criterion to authoring.task.criteria whose identity_review names each listed subject and '
        'compares it with its complete applicable source.'),
    'unknown_subject_ids': ('authoring.task.criteria',
        'Identity sources or reviews name subjects outside the declared input subject scope.',
        'Compare the actual input subject declaration with source and criterion subject scopes, then correct '
        'the mistaken declaration at its existing owner.'),
    'requires_identity_source': ('authoring.task.sources',
        'The recurring-identity feature is selected, and no identity source is declared.',
        'Acquire the adopted identity source with acquire-source using its subject_ids and selectors, '
        'or revise the actual feature selection if this work has no recurring identity.'),
}


def _task(root: Path, path: str | None, reader: InputEvidence, *,
          from_run: str | None = None, read_run=None,
          operation: str = 'inspect-inputs') -> tuple[dict, dict, dict, dict | None]:
    if (path is None) == (from_run is None):
        raise ValueError('select one task file or source run')
    saved = _source_run(root, from_run, read_run=read_run) if from_run is not None else None
    if saved is None:
        ref = reader.select(path)
        value = reader.json(ref)
    else:
        value = copy.deepcopy(saved['task'])
        ref = {'run': from_run, 'input_sha256': saved['input_sha256']}
    input_preflight.require_shape(value, schema_path=input_preflight.TASK_SCHEMA,
        file=path if saved is None else saved['task_path'], root=root,
        operation=operation, source_run=from_run)
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
        # Drafts share acquisition only when they select the same pack runtime.
        self._target_runtimes = {}
        self._observed: dict[str, dict] = {}

    def target_runtime(self):
        from catalog_retrieval.runtime import selected_pack_settings
        settings = selected_pack_settings()
        if settings not in self._target_runtimes:
            self._target_runtimes[settings] = production_target.SharedRuntime()
        return self._target_runtimes[settings]

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
    import production_operations as workflow
    loaded = read_run(selected) if read_run is not None else workflow.read_run(root, selected)
    prepared = loaded.prepared
    diagnostics, notices = workflow.freshness(root, selected, loaded=loaded)
    result = {'run': selected, 'input_sha256': prepared['input_sha256'],
            'task_path': prepared['task_path'], 'task': prepared['task'],
            'target_identity': production_target.prepared_identity(prepared['task'], loaded.artifacts.get('execution-plan.json'),
                loaded.consumer, loaded.artifacts.get('package.json')),
            'route_reading': copy.deepcopy(prepared.get('route_reading')),
            'freshness': {'diagnostics': diagnostics, 'notices': notices},
            'assessment_required': ['Check copied applications against the current task and changed dependencies.']}
    if prepared['task']['artifact'] == 'image':
        from cli_invocation import python_argv, shown
        argv = python_argv(ROOT / 'scripts/production_workflow.py', 'status',
                           '--root', str(root), '--run', selected, '--view', 'full')
        result['input_reuse'] = {
            'meaning': 'Amending with --from-run restores the saved authored inputs, including their input images. '
                       'It does not replace those images with a captured output of the run. Keep the restored '
                       'definitions, documents and source applications that remain applicable; they need no re-entry.',
            'automatic_output_selection': False,
            'captured_outputs': [{'candidate': row['sha256'], 'artifact': 'image',
                'files': [{'path': (loaded.directory / 'objects' / item['sha256']).relative_to(root).as_posix(),
                           'sha256': item['sha256'], 'size': item['size']}
                          for item in row['data']['files']]}
                for row in loaded.rows if row['event'] == 'candidate'],
            'read_action': {'operation': 'status', 'argv': argv, 'shown': shown(argv), 'external_effect': False},
            'required_action': 'For an edit of a captured output, select its candidate and actual file above. '
                'In the new draft, authoring_guide.source_acquisition gives the existing source-row schema and '
                'acquire-source command when that output needs to become a task source. Select its media file '
                'at external.image_input.references for external execution or authoring.references for dispatcher '
                'execution; use explain-inputs --field for that owner. Source role, identity uses, change scope, '
                'preservation and current authority remain author choices. Inspect the saved result and its '
                'selection with read_action.'}
    return result


def _sources(root: Path, task: dict, reader: InputEvidence) -> list[dict]:
    output = []
    for source in task.get('sources', []):
        if not isinstance(source, dict):
            raise ValueError('task source must be a declared object')
        path = c.text(source.get('path'), 'source path')
        local = c.local(root, path, exists=False)
        item = {key: copy.deepcopy(source.get(key)) for key in
                ('id', 'path', 'role', 'disposition', 'locator')}
        for name in ('origin', 'applications', 'definition_owner'):
            if source.get(name) is not None:
                item[name] = copy.deepcopy(source[name])
        item['present'] = local.is_file()
        if item['present']:
            item['file'] = reader.select(path)
        output.append(item)
    return output


def _identity_view(root: Path, task: dict, reader: InputEvidence, *, saved: dict | None = None,
                   files: dict[str, bytes] | None = None, out_dir: str | None = None,
                   choices: dict | None = None, basis: dict | None = None) -> dict | None:
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
        import production_operations as production_workflow
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
        value = production_identity.inspect(task, read, choices=choices, basis=basis)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        return {'status': 'unresolved', 'request_verified': False,
                'diagnostics': [from_exception(exc, phase='identity-coverage')]}
    if (value['sources'] or value['required_subject_ids'] or value['requires_identity_source']
            or value['whole_reviews'] or value.get('diagnostics')):
        return value
    return None


def _identity_subject_gap(value: dict, *, root: Path | None, choices_path: str | None,
                          locations: dict | None) -> dict:
    import identity_coverage
    import production_input_guide as guide
    result = identity_coverage.subject_gap(value)
    declaration = value.get('subject_declaration') or {}
    if declaration.get('owner') == 'production_spec':
        selected_field = 'authoring.documents.production_spec'
        location = (locations or {}).get(selected_field)
        result['field'] = selected_field + '.subjects' if declaration['present'] else selected_field
        if location:
            path = [*(location.get('pointer') or []), 'subjects']
            result.update(file=location['file'], pointer='/' + '/'.join(
                str(part).replace('~', '~0').replace('/', '~1') for part in path))
        elif declaration.get('file'):
            result.update(file=declaration['file'], pointer='/subjects')
        else:
            result.update(pointer='/authoring/documents/production_spec')
            if choices_path is not None:
                result['file'] = choices_path
        result['repair_owner'] = {'owner': 'production_spec',
            'file': location['file'] if location else declaration.get('file'),
            'pointer': result['pointer'] if location else '/subjects',
            'selection_pointer': '/authoring/documents/production_spec'}
    elif declaration.get('owner') == 'recording.subject_map':
        selected_field = 'authoring.task.recording'
        result.update(field=selected_field + '.subject_map', pointer='/authoring/task/recording/subject_map')
        if choices_path is not None:
            result['file'] = choices_path
        result['repair_owner'] = {'owner': 'recording.subject_map', 'file': choices_path,
                                  'pointer': result['pointer']}
    else:
        selected_field = 'authoring.task'
    if root is not None and choices_path is not None:
        result['next_action'] = guide.action(root, choices_path, field=selected_field)
        result['next_actions'] = [result['next_action']]
        result['required_action'] += ' Inspect the current owner with ' + result['next_action']['shown'] + '.'
    return result


def _identity_gaps(value: dict | None, *, root: Path | None = None,
                   choices_path: str | None = None, locations: dict | None = None) -> list[dict]:
    """One IDENTITY_COVERAGE_INCOMPLETE entry per kind of gap, and each failed identity inspection."""
    if value is None:
        return []
    result = [{**diagnostic, 'field': 'authoring.task'} for diagnostic in value.get('diagnostics', [])]
    for key, (field, message, required_action) in IDENTITY_GAPS.items():
        if value.get(key):
            result.append({'field': field, 'code': 'IDENTITY_COVERAGE_INCOMPLETE', 'phase': 'identity-coverage',
                           'message': message, 'required_action': required_action,
                           'guidance': phase_guidance('identity-coverage'), 'gaps': {key: value[key]},
                           **(_identity_subject_gap(value, root=root, choices_path=choices_path,
                                                    locations=locations) if key == 'unknown_subject_ids' else {})})
    return result


def inspect_inputs(root: Path, task_path: str | None = None, *, from_run: str | None = None,
                   choices_path: str | None = None, runtime_arguments: dict | None = None) -> dict:
    """Read declarations and saved records without issuing keys or permissions."""
    if task_path is None and from_run is None:
        if choices_path is not None:
            import production_candidate_snapshot
            proposal = production_candidate_snapshot.inspect(root, choices_path)
            if proposal is not None:
                return proposal
        import production_authoring_state
        return production_authoring_state.inspect(root, choices=choices_path, runtime_arguments=runtime_arguments)
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
                      'reads': route['reads'], 'source_roles': route['source_roles']},
            'source_requirements': input_preflight.source_roles(root, task, resolved_route=route,
                task_path=task_path, source_run=from_run),
            'unresolved': input_preflight.missing_source_roles(root, task, task_path=task_path, source_run=from_run),
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
            'authoring': authoring.blank(task),
            'external': ({'image_input': task['image_input']}
                         if task.get('execution') == 'external' and task.get('image_input') else None)}


def _reading_required(field: str, root: Path, task: dict, choices: dict,
                      runtime_arguments: dict | None, choices_path: str | None = None) -> dict:
    """The unanswered route reading, with the read command that issues its key."""
    action = _reading_action(root, task, choices, runtime_arguments, choices_path=choices_path)
    if field == 'reading':
        message = 'reading is null, so these choices select no completed route reading.'
        value = 'reading to {"reading_key": KEY} with the issued reading.key as KEY'
    else:
        message = 'reading.reading_key is empty, so these choices select no completed route reading.'
        value = 'reading.reading_key to the issued reading.key'
    return choice_required(field, 'reading-required', message,
        'Read the complete current scope with ' + action['shown'] + '. Follow actions.continue through '
        'its bounded pages until reading is non-null. actions.index exposes the exact source scope '
        'and optional section selection. Then set ' + value + '.',
        {'document_path': 'references/runtime/production-authoring.md#select-and-read-the-current-knowledge'},
        next_action=action, next_actions=[action])


def _missing(choices: dict, task: dict, root: Path, runtime_arguments: dict | None,
             choices_path: str | None = None) -> list[dict]:
    """Name unanswered resolved choices after their persisted selectors were validated."""
    unresolved = []
    reading = choices['reading']
    if reading is None:
        unresolved.append(_reading_required('reading', root, task, choices, runtime_arguments, choices_path))
    elif not isinstance(reading, dict):
        raise ValueError('reading choices must be an object')
    else:
        if not reading.get('reading_key'):
            unresolved.append(_reading_required('reading.reading_key', root, task, choices, runtime_arguments, choices_path))
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


def _unresolved(choices: dict, task: dict, *, root: Path, runtime_arguments: dict | None,
                choices_path: str | None = None) -> list[dict]:
    task = _chosen_task(task, choices)
    unresolved = _missing(choices, task, root, runtime_arguments, choices_path)
    unresolved.extend(production_target.unresolved(choices['target'], task))
    if choices['validation'] is None and adapters.validation_required(task):
        unresolved.append(choice_required('validation', 'selection-required',
            'validation is null, and this dispatcher upscale needs a request-validation selection.',
            'Set validation to {"mode": "target-schema", "contract": null, "evidence": null, '
            '"execution_policy": null} to use the selected offering\'s parameter schema, or select contract and '
            'evidence paths for an acquired schema, a bounded probe or an adopted observed profile.',
            adapters.VALIDATION_GUIDE))
    unresolved.extend(authoring.unresolved(choices.get('authoring'), task))
    unresolved.extend(input_preflight.generation_fields(root, choices, task, choices_path=choices_path))
    unresolved.extend(input_preflight.missing_source_roles(root, task, choices_path=choices_path))
    if (choices['visual'] is None and task.get('execution') == 'dispatcher'
            and task.get('route') != 'upscale' and choices.get('authoring') is not None):
        unresolved.extend(authoring.continuity_unresolved(choices['authoring']))
    if choices['external'] is not None:
        import production_external_inputs
        unresolved.extend(production_external_inputs.unresolved(choices['external']))
        unresolved.extend(production_external_inputs.media_location_diagnostics(
            choices['external'], root=root, choices_path=choices_path))
    if isinstance(task.get('semantic_edit'), str):
        import semantic_edit_plan
        try:
            plan = c.load(c.local(root, task['semantic_edit']))
        except (OSError, ValueError):
            # An unreadable plan is reported where preparation reads it.
            plan = None
        unresolved.extend(semantic_edit_plan.unresolved(plan, path=task['semantic_edit'],
                                                        criteria=task.get('criteria', [])))
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
    import generation_payload_builder as payload
    import request_validation
    import runtime_evidence
    record = None
    evidence = runtime_evidence.reader(root, snapshots=reader.snapshots) if saved is None else None
    source = None
    if saved is not None:
        import production_operations as production_workflow
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
    choices = request_validation.draft_choices(record, evidence, target=original)
    if saved is not None:
        for field in ('contract', 'evidence', 'execution_policy'):
            path = choices[field]
            if path is not None and not path.startswith('@'):
                choices[field] = '@run/' + saved['run'] + '/' + path
    return choices


def _reading_action(root: Path, task: dict, choices: dict, runtime_arguments: dict | None = None, *,
                    choices_path: str | None = None, authoring_scope: dict | None = None) -> dict:
    """Begin bounded delivery of the current scope through the real route reader."""
    root = c._root(root)
    from cli_invocation import python_argv, shown
    operation = (reading_scope.operation((authoring_scope or {}).get('stage') or reading_scope.stage(choices, task),
                                        task['execution']) if 'authoring_stage' in choices or authoring_scope is not None
                 else 'author' if task['execution'] == 'authored' else 'prepare')
    args = {'root': str(root), 'operation': operation, 'execution': task['execution'], 'all': True,
            'feature': task['features'], **(runtime_arguments or {})}
    if choices_path is not None and 'authoring_stage' in choices:
        args['choices'] = choices_path
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
        if isinstance(value, bool):
            if value:
                argv.append('--' + name)
            continue
        for item in value if isinstance(value, list) else [value]:
            argv.extend(('--' + name, str(item)))
    return {'operation': 'read', 'script': 'scripts/execution_routes.py', 'args': args,
            'positional': [task['route']], 'argv': argv, 'shown': shown(argv),
            'external_effect': False}


def _guidance_gap(root: Path, task: dict, choices: dict, projected: dict,
                  runtime_arguments: dict | None = None, *, choices_path: str | None = None,
                  authoring_scope: dict | None = None) -> list[dict]:
    if not (choices.get('reading') or {}).get('reading_key') or projected['unresolved']:
        return []
    target = projected.get('resolved_target')
    try:
        record = _reading(choices['reading'], root=root, task=task, authoring_scope=authoring_scope)
        model = target.model if target is not None and choices['target']['kind'] != 'external' else None
        route_reading.require_route_reading(record, studio=root, routes={task['route']},
            features=task['features'], execution=task['execution'],
            operation=reading_scope.operation(authoring_scope['stage'], task['execution']) if authoring_scope
                      else 'author' if task['execution'] == 'authored' else 'prepare',
            authoring_scope=authoring_scope,
            dialect=target.model.get('prompt_dialect') if target is not None else route_reading._NO_MODEL,
            model_record=model, service=(target.offering or {}).get('service') if target is not None else None)
    except (ValueError, OSError) as exc:
        action = _reading_action(root, task, choices, runtime_arguments, choices_path=choices_path,
                                 authoring_scope=authoring_scope)
        if authoring_scope and authoring_scope['stage'] != reading_scope.stage(choices, task) and choices_path:
            action = next(item for item in reading_scope.actions(root, choices_path,
                reading_scope.stage(choices, task), runtime_arguments) if item['stage'] == authoring_scope['stage'])
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
    path = (Path(out_dir) / 'choices.json').as_posix()
    current_gaps = reading_scope.projection(choices, task, gaps)['unresolved'] if 'authoring_stage' in choices else gaps
    actions = []
    for gap in current_gaps:
        for action in gap.get('next_actions', []):
            if action not in actions:
                actions.append(action)
    if any(item['field'].startswith('reading') for item in current_gaps) and not any(
            item.get('operation') == 'read' for item in actions):
        actions.append(_reading_action(root, task, choices, runtime_arguments, choices_path=path))
    if not gaps:
        actions.append(continuation_action(root, task, path, runtime_arguments, saved,
                                          production_target.projected_identity(projected)))
    elif current_gaps:
        actions.append({'operation': 'edit-choices', 'args': {'path': path},
                        'unresolved_fields': [row['field'] for row in current_gaps], 'external_effect': False})
    if 'authoring_stage' in choices:
        actions.extend(reading_scope.actions(root, path, reading_scope.stage(choices, task), runtime_arguments))
    return actions


def _reading(choices: dict, *, root: Path, task: dict, authoring_scope: dict | None = None) -> dict:
    c.exact(choices, {'reading_key'}, 'reading choices')
    issued = route_reading.resolve_issuance(choices['reading_key'], studio=root)
    operation = (reading_scope.operation(authoring_scope['stage'], task['execution']) if authoring_scope is not None
                 else 'author' if task.get('execution') == 'authored' else 'prepare')
    record = route_reading.build_record(issued, studio=root, operation=operation,
        execution=task['execution'], features=task['features'], authoring_scope=authoring_scope)
    route_reading.require_route_reading(record, studio=root,
        routes={task['route']}, features=task['features'], execution=task['execution'],
        operation=operation, authoring_scope=authoring_scope)
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
    import production_operations as production_workflow
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


def _upscale_refusal(message: str, required_action: str) -> ProductionError:
    """A selector of the upscale draft used outside it."""
    return ProductionError('INPUT_CONSISTENCY_ERROR', message, phase='authoring', required_action=required_action,
                           guidance=dict(authoring.UPSCALE_GUIDE))


def draft_inputs(root: Path, task_path: str | None, out_dir: str, *, from_run: str | None = None,
                 source_choices: str | None = None,
                 runtime_arguments: dict | None = None, route: str | None = None,
                 artifact: str | None = None, execution: str | None = None,
                 task_id: str | None = None, features: list[str] | None = None,
                 model: str | None = None, service: str | None = None,
                 source_image: Path | None = None, scale: float | None = None,
                 purpose: str | None = None, new_task: str | None = None,
                 source_run: str | None = None, source_candidate: str | None = None,
                 edit_character: str | None = None, edit_slot: str | None = None,
                 operation: str | None = None, request_file: str | None = None,
                 apply_sources: list[str] | None = None, focus: str | None = None,
                 stage: str | None = None, change_scope: dict | None = None) -> dict:
    _destination(root, out_dir)
    if source_choices is not None and (task_path is not None or from_run is not None):
        raise ValueError('select choices, a task or a source run as the candidate input')
    operation = operation or ('compose' if source_choices is not None else None)
    if source_choices is not None and operation != 'compose':
        raise ProductionError('INPUT_CONSISTENCY_ERROR',
            'A choices input begins a fresh compose from that candidate.',
            phase='authoring', file=source_choices, pointer='/operation',
            cause='candidate-source-operation',
            required_action='Use draft-inputs --choices with operation compose, or omit --operation. '
                'Continue an existing amend by editing its current choices.')
    if operation not in {'compose', 'amend'}:
        raise ValueError('select the authoring operation: compose or amend')
    reading_scope.validate_change_scope(change_scope)
    if change_scope is not None and (operation != 'amend' or (task_path is None and from_run is None)):
        raise ValueError('A change scope requires amend of an existing --task or --from-run input.')
    if stage is not None and stage not in reading_scope.STAGES:
        raise ValueError('select an authoring stage: ' + ', '.join(reading_scope.STAGES))
    constructor_actions = _constructor_identity_actions(root, out_dir, {
        'task': task_path, 'from-run': from_run, 'choices': source_choices,
        'request-file': request_file, 'apply-source': apply_sources, 'focus': focus,
        'task-id': task_id, 'new-task': new_task, 'route': route, 'artifact': artifact,
        'execution': execution, 'feature': features, 'model': model, 'service': service,
        'source-image': source_image, 'scale': scale, 'purpose': purpose,
        'source-run': source_run, 'source-candidate': source_candidate,
        'edit-character': edit_character, 'edit-slot': edit_slot, 'stage': stage,
    }, runtime_arguments)
    reader = InputEvidence(root)
    initial = task_path is None and from_run is None and source_choices is None
    candidate = None
    if source_choices is not None:
        import production_candidate_snapshot
        candidate = production_candidate_snapshot.acquire(root, source_choices)
        source_choices = candidate['source_choices']
        if runtime_arguments is None:
            runtime_arguments = candidate['runtime_arguments']
    source_result = None
    edit = None
    if edit_character is not None or edit_slot is not None:
        production_edit_inputs.require_arguments(character=edit_character, slot=edit_slot, initial=initial,
            route=route, artifact=artifact, execution=execution,
            upscale={'source-image': source_image, 'source-run': source_run,
                     'source-candidate': source_candidate, 'scale': scale, 'purpose': purpose})
        edit = production_edit_inputs.select(root, edit_character, edit_slot)
        features = production_edit_inputs.features(edit, features)
        artifact = 'image'
    if source_run is not None or source_candidate is not None:
        if source_run is None or source_candidate is None:
            raise _upscale_refusal('A captured image is selected by its run and candidate together.',
                'Give both --source-run RUN and --source-candidate CANDIDATE with --route upscale.')
        if not initial or route != 'upscale' or source_image is not None:
            raise _upscale_refusal('--source-run and --source-candidate select the image of a new upscale draft.',
                'Use them with --route upscale, without --task, --from-run or --source-image. To edit an accepted '
                'image instead, select it with --edit-character CHARACTER --edit-slot SLOT and --route generation.')
        if execution not in {None, 'dispatcher'}:
            raise _upscale_refusal('A captured image is enlarged by a dispatcher upscale.',
                'Omit --execution or select --execution dispatcher for the upscale draft.')
        source_result = _captured_image_source(root, source_run, source_candidate)
        source_image = Path(source_result['file']['path'])
    if candidate is not None:
        candidate_task = _chosen_task(candidate['context']['task_content'], candidate['choices'])
        candidate_run = (candidate['context'].get('derived_from') or {}).get('source_run')
        candidate_ref = ({'run': candidate_run['run'], 'input_sha256': candidate_run['input_sha256']}
                         if candidate_run is not None else {'initial': True, 'task_id': candidate_task['task_id']})
        selected_source = (candidate_task, None, candidate_ref, candidate_run)
    else:
        selected_source = _task(root, task_path, reader, from_run=from_run, operation='draft-inputs') if not initial else None
    import production_authoring_state
    import work_ledger
    # Work this call opens. The draft is built for its reserved ID first; the
    # task is opened only when every selected input has produced that draft.
    opening = None
    if new_task is not None:
        if task_id is not None:
            raise ValueError('select --new-task or --task-id, not both')
        if initial and source_result is None and edit is None:
            raise ValueError('--new-task reopens a selected task or run; start initial work with work_ledger begin')
        opening = (c.text(new_task, 'new work goal'),
                   production_edit_inputs.STEPS if edit is not None else
                   ['Prepare the requested revision.', 'Assess and finish the selected result.'])
    elif edit is not None and task_id is None and production_authoring_state.active_task_id(root) is None:
        raise ProductionError('INPUT_CONSISTENCY_ERROR', 'No work task is open for the edit.', phase='authoring',
            guidance=production_edit_inputs.GUIDE,
            required_action='Add --new-task GOAL with the requested edit as its goal; the task opens when the draft '
                            'is published. A refused command opens no work.')
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
        task = authoring.seed(route=route, artifact=artifact or ('image' if route == 'upscale' else 'text'),
                              execution=execution or ('dispatcher' if route == 'upscale' else 'authored'),
                              task_id=task_id or production_authoring_state.active_task_id(root), features=features)
        task_ref, saved = {'initial': True, 'task_id': task['task_id']}, None
    else:
        task, _, task_ref, saved = selected_source
    if (from_run is not None or source_choices is not None) and task_id is None:
        active = production_authoring_state.active_task_id(root)
        if active != task['task_id']:
            from cli_invocation import python_argv, shown
            arguments = ['--root', str(root), *(['--choices', source_choices] if source_choices else
                         ['--from-run', from_run] if from_run else ['--task', task_path]),
                         '--out-dir', out_dir, '--operation', operation]
            if request_file is not None:
                arguments += ['--request-file', request_file]
            for source in apply_sources or []:
                arguments += ['--apply-source', source]
            for feature in features or []:
                arguments += ['--feature', feature]
            for key, values in (change_scope or {}).items():
                for value in values:
                    arguments += ['--' + key, value]
            arguments += ['--task-id', active] if active else ['--new-task', '<revision-goal>']
            for key, value in {'model': model, 'service': service, 'focus': focus, 'route': route,
                               'artifact': artifact, 'execution': execution, 'source-image': source_image,
                               'scale': scale, 'purpose': purpose, 'stage': stage}.items():
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
                source_image=source_image, scale=scale, purpose=purpose, open_work=open_work,
                operation=operation, request_file=request_file, apply_sources=apply_sources, focus=focus,
                route=route, artifact=artifact, execution=execution, features=features, stage=stage,
                change_scope=change_scope, constructor_actions=constructor_actions)
    if candidate is not None:
        return _draft_candidate(root, candidate, out_dir, task_id=task_id,
            runtime_arguments=runtime_arguments, operation=operation, request_file=request_file,
            apply_sources=apply_sources, focus=focus, model=model, service=service,
            source_image=source_image, scale=scale, purpose=purpose, open_work=open_work,
            route=route, artifact=artifact, execution=execution, features=features, stage=stage,
            change_scope=change_scope, constructor_actions=constructor_actions)
    choices = draft_choices(task)
    choices['authoring_stage'] = stage or ('prepare' if task.get('route') == 'upscale'
        else reading_scope.initial_stage(change_scope))
    captured = _captured_inputs(root, saved)
    retained_identity = None
    with captured if captured is not None else nullcontext():
        if operation == 'amend':
            if captured is not None:
                retained_identity = captured.identity_sources()
            else:
                original_basis = reader.json(reader.select(task['work_basis'])) if task.get('work_basis') else None
                retained_identity = _current_identity_sources(task, None, original_basis, reader)
        choices['authoring'] = authoring.draft(root, task, reader, saved=saved, initial=initial,
            captured=captured, retained_prefix=out_dir + '/retained' if captured is not None else None)
        if not initial and task_id is not None:
            task = _bind_task(task, task_id)
            choices['authoring']['task'] = _bind_task(choices['authoring']['task'], task_id)
        if not initial:
            choices['validation'] = _validation_choices(root, task, reader, saved)
        if initial and task.get('execution') == 'external':
            import production_external_inputs
            choices['external'] = production_external_inputs.template()
        if edit is not None:
            edit_files = production_edit_inputs.apply(root, edit, choices, task, out_dir, reader=reader)
        else:
            edit_files = production_edit_inputs.reopen(root, task, choices, out_dir, reader=reader, saved=saved)
        if not initial and task.get('execution') == 'external' and task.get('image_input'):
            import production_external_inputs
            if captured is not None:
                plan = copy.deepcopy(captured.loaded.consumer['image_input'])
                request = copy.deepcopy(plan['external_request']['request'])
                retained = captured.references()
                prepared = retained['prepared'] if retained is not None else None
                package_root = retained['root'] if retained is not None else None
                source_archive = retained['source_archive'] if retained is not None else None
            else:
                plan = c.decode(authoring.source_bytes(root, task['image_input'], reader, saved))
                external_path = (plan.get('external_request') or {}).get('file')
                request = c.decode(authoring.source_bytes(root, external_path, reader, saved)) if external_path else None
                prepared_path = plan.get('prepared_references')
                prepared = c.decode(authoring.source_bytes(root, prepared_path, reader, saved)) if prepared_path else None
                package_root = c.local(root, prepared_path, exists=False).parent if prepared_path else None
                source_archive = None
            choices['external'] = production_external_inputs.draft(plan, request,
                prepared=prepared, root=root, package_root=package_root, source_archive=source_archive)
        choices['target'] = production_target.extract(copy.deepcopy(task), choices['authoring'], choices['external'])
        if edit is not None and choices['target'] is None:
            choices['target'] = production_edit_inputs.target(edit)
        retained_files, retained_paths = _restore_selected_sources(choices, captured, out_dir)
        if choices['external'] is not None and retained_paths:
            import production_external_inputs
            choices['external'] = production_external_inputs.relocate_sources(choices['external'], retained_paths)
        retained_owners = _retained_source_owners(captured)
        if operation == 'amend':
            _retain_identity_context(choices['authoring'], captured, retained_paths, retained_files, out_dir)
        prior_basis = _saved_work_basis(captured)
        _select_identity_owners(choices, prior_basis, retained_owners, operation=operation)
        task, choices, work_basis, request = _begin_work(root, task, choices, retained_files, out_dir, reader,
            operation=operation, request_file=request_file, apply_sources=apply_sources,
            prior_basis=prior_basis, initial=initial, focus=focus,
            route=route, artifact=artifact, execution=execution, features=features, change_scope=change_scope)
        _mark_identity_owners(work_basis, retained_owners)
        retained_files['work-basis.json'] = c.encoded(work_basis)
        imported, selected_image = authoring.select_upscale(root, choices['authoring'], out_dir,
            source_image=source_image, scale=scale, purpose=purpose)
        if source_result is not None:
            if selected_image['sha256'] != source_result['file']['sha256']:
                raise ValueError('the selected captured image changed during drafting')
            selected_image.update(source_run=source_result['run'], source_candidate=source_result['candidate'])
    _select_target(choices, model=model, service=service)
    previous = saved['route_reading'] if saved is not None else None
    if previous is None and not initial and saved is None:
        path = task.get('route_reading')
        if path and c.local(root, path, exists=False).is_file():
            previous = reader.json(reader.select(path))
    if previous is not None:
        route_reading.validate_record_content(previous)
        choices['reading']['reading_key'] = previous['reading_key']
    editable={**retained_files,**imported,**edit_files}
    delivery=choices['authoring']['delivery']
    empty_delivery=False
    if choices['authoring'].get('upscale') is None:
        raw=delivery.pop('content',None)
        raw=b'' if raw is None else raw.encode('utf-8') if isinstance(raw,str) else c.encoded(raw)
        delivery['file']=(Path(out_dir)/'prompt.txt').as_posix()
        editable['prompt.txt']=raw
        empty_delivery=not raw.strip()
    editable.update(authoring.export_documents(choices['authoring'], out_dir))
    import production_reference_inputs
    production_reference_inputs.identify_choices(choices)
    _validate_choices(choices)
    chosen = _chosen_task(task, choices)
    with _staged_files(root, out_dir, editable):
        # The draft's editable files are read where they will be published.
        resolved = copy.deepcopy(choices)
        resolved['authoring'], locations, file_gaps = authoring.read_editable(choices['authoring'], reader)
        identity = _identity_view(root, chosen, reader, saved=saved, files=editable, out_dir=out_dir,
                                  choices=choices, basis=work_basis)
        boundary = _current_identity_sources(chosen, choices, work_basis, reader)
        _require_constructor_identity(retained_identity, boundary, work_basis,
            file=task_path or (saved or {}).get('task_path'), out_dir=out_dir,
            actions=constructor_actions)
        projected = production_target.project(resolved, chosen, root, reader, out_dir)
        gaps = _unresolved(resolved, task, root=root, runtime_arguments=runtime_arguments,
            choices_path=(Path(out_dir) / 'choices.json').as_posix()) + file_gaps
    if empty_delivery and not any(row['field'] == 'authoring.delivery.content' for row in gaps):
        gaps.append(authoring.authored_choice('delivery.content'))
    gaps += _identity_gaps(identity, root=root,
        choices_path=(Path(out_dir) / 'choices.json').as_posix(), locations=locations)
    gaps.extend(item for item in projected['unresolved'] if item not in gaps)
    gaps.extend(_target_gaps(choices, chosen, projected))
    current_scope = reading_scope.selection(root, resolved, chosen, basis=work_basis,
        context={'derived_from': {'source_run': saved}})
    gaps.extend(_guidance_gap(root, task, choices, projected, runtime_arguments,
        choices_path=(Path(out_dir) / 'choices.json').as_posix(), authoring_scope=current_scope))
    gaps = authoring.locate_unresolved(gaps, locations)
    actions = _draft_actions(root, chosen, choices, gaps, out_dir, runtime_arguments, saved, projected)
    result = {'state': 'draft', 'choices': choices,
              'unresolved': gaps, 'target_knowledge': projected['knowledge'], 'next_actions': actions,
              'selected_image': selected_image,
              **({'edit_source': production_edit_inputs.report(edit)} if edit is not None else {}),
              **({'identity_coverage': identity} if identity is not None else {}),
              'retained_identity_sources': retained_identity if operation == 'amend' else boundary,
              'identity_owners': retained_owners,
              'derived_from': {'task': task_ref, 'source_run': saved},
              'external_effect': False}
    result['authoring_work'] = {'operation': operation,
        'basis': (Path(out_dir) / 'work-basis.json').as_posix(),
        'content': (Path(out_dir) / 'choices.json').as_posix()}
    if request is not None:
        result['current_request'] = request
    gaps.extend(authoring_work.unresolved(work_basis, resolved, require_subject=authoring_work.requires_subject(task),
        root=root, choices_path=(Path(out_dir) / 'choices.json').as_posix(),
        basis_path=(Path(out_dir) / 'work-basis.json').as_posix()))
    result.update(authoring_scope=current_scope,
        authoring_stage=reading_scope.projection(choices, chosen, gaps, scope=current_scope),
        stage_actions=reading_scope.actions(root, (Path(out_dir) / 'choices.json').as_posix(),
                                            choices['authoring_stage'], runtime_arguments),
        next_actions=_draft_actions(root, chosen, choices, gaps, out_dir, runtime_arguments, saved, projected))
    import production_input_guide
    result['authoring_guide'] = production_input_guide.summary(
        root, (Path(out_dir) / 'choices.json').as_posix(), choices)
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
        request=request['text'] if request is not None else None,
        context_sha256=c.digest(context_raw), input_arguments=({key: str(value) for key, value in {
            'source-run': source_run, 'source-candidate': source_candidate,
            'source-image': source_image if source_result is None else None, 'scale': scale,
            'purpose': purpose, 'edit-character': edit_character, 'edit-slot': edit_slot,
            'model': model, 'service': service, 'operation': operation, 'stage': choices['authoring_stage'],
            'request-file': request_file, 'focus': focus}.items() if value is not None} if initial else
            _authoring_arguments(task, operation=operation, request_file=request_file,
                apply_sources=apply_sources, focus=focus, route=route, artifact=artifact,
                execution=execution, features=features, model=model, service=service,
                stage=choices['authoring_stage'], source_image=source_image, scale=scale, purpose=purpose,
                change_scope=change_scope)))
    _publish(root, out_dir, {**editable,'choices.json': c.encoded(choices),
                            'context.json': context_raw}, reader=reader)
    production_authoring_state.published_draft(root, task, out_dir)
    return {**result, 'choices_file': (Path(out_dir) / 'choices.json').as_posix(),
            'context_file': (Path(out_dir) / 'context.json').as_posix()}


def _request_text(path: str | None, reader: InputEvidence) -> str | None:
    """Acquire the actual current instruction; a work-ledger title is navigation."""
    if path is None:
        return None
    selected = Path(path)
    if selected.is_absolute():
        import production_store
        raw = production_store.stable_bytes(selected.parent, selected.name)
    else:
        raw = reader.read(reader.select(path))
    return raw.decode('utf-8')


def _saved_work_basis(captured) -> dict | None:
    if captured is None:
        return None
    selected = captured.prepared['task'].get('work_basis')
    return c.decode(captured.bytes(selected)) if selected is not None else None


def _begin_work(root: Path, task: dict, choices: dict, files: dict, out_dir: str,
                reader: InputEvidence, *, operation: str, request_file: str | None,
                apply_sources: list[str] | None, prior_basis: dict | None,
                initial: bool = False, editable: bool = False, focus: str | None = None,
                route: str | None = None, artifact: str | None = None,
                execution: str | None = None, features: list[str] | None = None,
                change_scope: dict | None = None) -> tuple[dict, dict, dict, dict | None]:
    """Apply the shared content operation after either acquisition adapter."""
    import production_store
    choices = normalize_task_choices(choices)
    task = _chosen_task(task, choices)
    held = production_store.read_authority(root, task['task_id'], required=False)
    protected = {key for grant in held.document['grants'] for key in grant['protected_criteria']} if held else set()
    prefix = out_dir.rstrip('/') + '/'
    def read(path):
        return files[path[len(prefix):]] if path.startswith(prefix) and path[len(prefix):] in files else reader.read(reader.select(path))
    if prior_basis is None and task.get('work_basis') is not None:
        prior_basis = c.decode(read(task['work_basis']))
    resolved = copy.deepcopy(choices)
    if editable:
        with _staged_files(root, out_dir, files):
            resolved['authoring'], _, _ = authoring.read_editable(resolved['authoring'], reader)
    selected_stage = choices.get('authoring_stage')
    choices, basis, task = authoring_work.begin(resolved, task=task, operation=operation,
        request=_request_text(request_file, reader), read_source=read, prior_basis=prior_basis,
        applied_sources=apply_sources, protected_criteria=protected, initial=initial,
        route=route, artifact=artifact, execution=execution, features=features, focus=focus)
    reading_scope.validate_change_scope(change_scope)
    if change_scope is not None:
        basis['change_scope'] = copy.deepcopy(change_scope)
    if selected_stage is not None:
        choices['authoring_stage'] = selected_stage
    choices, selected_files, request = authoring_work.project(basis, choices, out_dir)
    files.update(selected_files)
    files['work-basis.json'] = c.encoded(basis)
    task = _chosen_task(task, choices)
    return task, choices, basis, request


def _retained_source_owners(captured) -> dict:
    """Identify promoted witnesses from their actual source ownership, not wording."""
    if captured is None:
        return {}
    basis = _saved_work_basis(captured) or {}
    owners = {ident: copy.deepcopy(record['origin'].get('identity_owner', {}))
              for ident, record in basis.get('sources', {}).items()
              if (record.get('origin') or {}).get('kind') == 'retained-identity'}
    direct = {row['id'] for row in captured.prepared['task'].get('sources', [])}
    for source in (captured.prepared.get('identity_coverage') or {}).get('sources', []):
        if not source.get('derived') or source['id'] in direct:
            continue
        authority = source.get('authority') or {}
        if 'reference' in authority:
            owners[source['id']] = {'kind': 'reference-use', 'reference': authority['reference']}
        elif 'owner' in authority and 'character_id' in authority:
            owners[source['id']] = {'kind': 'state-node', 'owner': authority['owner'],
                                   'character_id': authority['character_id']}
    return owners


def _mark_identity_owners(basis: dict, owners: dict) -> None:
    for ident, owner in owners.items():
        if ident in basis['sources']:
            origin = basis['sources'][ident].setdefault('origin', {})
            origin.update(kind='retained-identity', identity_owner=copy.deepcopy(owner))


def _select_identity_owners(choices: dict, basis: dict | None, owners: dict, *, operation: str) -> None:
    """A compose selects current owners, while old implicit witnesses remain comparison."""
    if basis is not None:
        owners.update({ident: copy.deepcopy(record['origin'].get('identity_owner', {}))
            for ident, record in basis.get('sources', {}).items()
            if (record.get('origin') or {}).get('kind') == 'retained-identity'})
    if operation != 'compose' or not owners:
        return
    authored = choices['authoring']
    removed_paths = {row['path'] for row in authored['task'].get('sources', []) if row['id'] in owners}
    authored['task']['sources'] = [row for row in authored['task'].get('sources', []) if row['id'] not in owners]
    authored['source_files'] = {path: value for path, value in authored['source_files'].items() if path not in removed_paths}
    if basis is not None:
        removed = {key for key, row in basis['applications'].items() if row['source'] in owners}
        basis['applications'] = {key: row for key, row in basis['applications'].items() if key not in removed}
        basis['subjects'] = {key: [item for item in values if item not in removed]
                             for key, values in basis['subjects'].items()}
        basis['subjects'] = {key: values for key, values in basis['subjects'].items() if values}
        basis['requirements'] = [key for key in basis['requirements'] if key not in removed]


def _current_identity_sources(task: dict, choices: dict | None, basis: dict | None,
                              reader: InputEvidence) -> dict:
    import production_identity
    def read(path):
        if Path(path).is_absolute():
            return c.read(Path(path))
        return reader.read(reader.select(path))
    return production_identity.source_snapshot(task, read, choices=choices, basis=basis)


def _constructor_identity_actions(root: Path, out_dir: str, selections: dict,
                                  runtime_arguments: dict | None) -> dict:
    """Inspect the acquired owner or repeat its selected content as a new compose."""
    from cli_invocation import python_argv, shown
    arguments = ['--root', str(root), '--out-dir', out_dir, '--operation', 'compose']
    for key, value in {**selections, **(runtime_arguments or {})}.items():
        if value is not None:
            for item in value if isinstance(value, list) else [value]:
                arguments.extend(('--' + key, str(item)))
    argv = python_argv(ROOT / 'scripts/production_workflow.py', 'draft-inputs', *arguments)
    repair = {'command': 'draft-inputs', 'operation': 'draft-inputs', 'argv': argv, 'shown': shown(argv),
              'external_effect': False,
              'reason': 'Compose the same selected content and current request with the proposed source selection.'}
    source = {key: selections[key] for key in ('task', 'from-run', 'choices') if selections.get(key) is not None}
    arguments = ['--root', str(root)]
    for key, value in {**source, **(runtime_arguments or {})}.items():
        if value is not None:
            for item in value if isinstance(value, list) else [value]:
                arguments.extend(('--' + key, str(item)))
    argv = python_argv(ROOT / 'scripts/production_workflow.py', 'inspect-inputs', *arguments)
    inspect = {'command': 'inspect-inputs', 'operation': 'inspect-inputs', 'argv': argv, 'shown': shown(argv),
               'external_effect': False,
               'reason': 'Inspect the selected input and the source owners it acquired.'}
    if 'from-run' in source:
        owner = {'run': source['from-run'], 'pointer': '/task'}
    elif 'task' in source:
        owner = {'file': source['task'], 'pointer': ''}
    elif 'choices' in source:
        owner = {'file': source['choices'], 'pointer': '/authoring'}
    else:
        owner = {'owner': 'initial-constructor-input'}
    return {'repair': repair, 'inspect': inspect, 'evidence_owner': owner}


def _require_constructor_identity(retained: dict | None, current: dict, basis: dict, *,
                                  file: str | None, out_dir: str, actions: dict) -> None:
    """Compare against the acquired input before new constructor selections are applied."""
    import production_identity_boundary
    import production_authoring_state
    context = {'authoring_work': {'operation': basis['operation']},
               'retained_identity_sources': retained}
    try:
        production_identity_boundary.require_unchanged(context, basis, current, file=file)
    except ProductionError as error:
        if production_authoring_state.identity_repairable(error):
            repair, inspect = copy.deepcopy(actions['repair']), copy.deepcopy(actions['inspect'])
            error.diagnostic.details.update(repair_action=repair, inspect_action=inspect, next_action=repair,
                next_actions=[repair, inspect], evidence_owner=copy.deepcopy(actions['evidence_owner']),
                repair_owner={'file': (Path(out_dir) / 'choices.json').as_posix(), 'operation': 'compose'})
            error.diagnostic.required_action = repair['shown']
        raise


def _draft_candidate(root: Path, candidate: dict, out_dir: str, *, task_id: str | None,
                     runtime_arguments: dict | None, operation: str, request_file: str | None,
                     apply_sources: list[str] | None, focus: str | None, model: str | None,
                     service: str | None, source_image: Path | None, scale: float | None,
                     purpose: str | None, open_work, route: str | None, artifact: str | None,
                     execution: str | None, features: list[str] | None, stage: str | None,
                     constructor_actions: dict, change_scope: dict | None = None) -> dict:
    """Compose an acquired actual candidate without replaying a refused mutation."""
    import production_candidate_snapshot as snapshots
    import production_authoring_state as state
    choices, prior_basis, files, candidate_inputs = snapshots.materialize(candidate, out_dir)
    choices = normalize_task_choices(choices)
    original_context = candidate['context']
    task = _chosen_task(original_context['task_content'], choices)
    if task_id is not None:
        task = _bind_task(task, task_id)
        choices['authoring']['task'] = _bind_task(choices['authoring']['task'], task_id)
    choices['authoring_stage'] = stage or (reading_scope.initial_stage(change_scope)
        if change_scope is not None else choices.get('authoring_stage') or 'definition')
    owners = copy.deepcopy(candidate['identity_owners'])
    _select_identity_owners(choices, prior_basis, owners, operation=operation)
    # Preserve actual file selectors and aliases while the work owner examines
    # their resolved content. This avoids normalizing literal prompt newlines or
    # splitting several JSON field selections into independently editable copies.
    selected_delivery = copy.deepcopy(choices['authoring']['delivery'])
    selected_documents = copy.deepcopy(choices['authoring']['documents'])
    reader = InputEvidence(root, named_roots={'@skill': ROOT})
    task, choices, work_basis, request = _begin_work(root, task, choices, files, out_dir, reader,
        operation=operation, request_file=request_file, apply_sources=apply_sources,
        prior_basis=prior_basis, editable=True, focus=focus,
        route=route, artifact=artifact, execution=execution, features=features, change_scope=change_scope)
    choices['authoring']['delivery'] = selected_delivery
    choices['authoring']['documents'] = selected_documents
    _mark_identity_owners(work_basis, owners)
    files['work-basis.json'] = c.encoded(work_basis)
    _select_target(choices, model=model, service=service)
    imported, selected_image = authoring.select_upscale(root, choices['authoring'], out_dir,
        source_image=source_image, scale=scale, purpose=purpose)
    files.update(imported)
    import production_reference_inputs
    production_reference_inputs.identify_choices(choices)
    _validate_choices(choices)
    task = _chosen_task(task, choices)
    saved = (original_context.get('derived_from') or {}).get('source_run')
    reference = ({'run': saved['run'], 'input_sha256': saved['input_sha256']}
                 if saved is not None else {'initial': True, 'task_id': task['task_id']})
    origin = {'task': reference, 'source_run': saved, 'source_choices': copy.deepcopy(candidate['origin'])}
    with _staged_files(root, out_dir, files):
        resolved = copy.deepcopy(choices)
        resolved['authoring'], locations, file_gaps = authoring.read_editable(resolved['authoring'], reader)
        held = _current_identity_sources(task, choices, work_basis, reader)
        _require_constructor_identity(candidate.get('identity_baseline'), held, work_basis,
            file=(saved or {}).get('task_path') or candidate.get('source_choices'),
            out_dir=out_dir, actions=constructor_actions)
        identity = _identity_view(root, task, reader, saved=saved, choices=choices, basis=work_basis)
        projected = production_target.project(resolved, task, root, reader, out_dir)
        scope = reading_scope.selection(root, resolved, task, basis=work_basis, context={'derived_from': origin})
        gaps = _unresolved(resolved, task, root=root, runtime_arguments=runtime_arguments,
            choices_path=(Path(out_dir) / 'choices.json').as_posix()) + file_gaps
        gaps.extend(projected['unresolved'])
        gaps.extend(_target_gaps(choices, task, projected))
        gaps.extend(_identity_gaps(identity, root=root, choices_path=(Path(out_dir) / 'choices.json').as_posix(), locations=locations))
        gaps.extend(authoring_work.unresolved(work_basis, resolved,
            require_subject=authoring_work.requires_subject(task), root=root,
            choices_path=(Path(out_dir) / 'choices.json').as_posix(),
            basis_path=(Path(out_dir) / 'work-basis.json').as_posix()))
        gaps.extend(_guidance_gap(root, task, choices, projected, runtime_arguments,
            choices_path=(Path(out_dir) / 'choices.json').as_posix(), authoring_scope=scope))
    gaps = authoring.locate_unresolved(gaps, locations)
    choice_path = (Path(out_dir) / 'choices.json').as_posix()
    result = {'state': 'draft', 'choices': choices, 'unresolved': gaps,
        'derived_from': origin, 'external_effect': False, 'selected_image': selected_image,
        'authoring_work': {'operation': operation, 'basis': (Path(out_dir) / 'work-basis.json').as_posix(),
                          'content': choice_path}, 'identity_owners': owners,
        'retained_identity_sources': candidate.get('identity_baseline') if operation == 'amend' else held,
        'identity_coverage': identity,
        'candidate_inputs': candidate_inputs,
        'target_knowledge': projected['knowledge'], 'authoring_scope': scope,
        'authoring_stage': reading_scope.projection(choices, task, gaps, scope=scope),
        'stage_actions': reading_scope.actions(root, choice_path, choices['authoring_stage'], runtime_arguments),
        'next_actions': _draft_actions(root, task, choices, gaps, out_dir, runtime_arguments, saved, projected)}
    if request is not None:
        result['current_request'] = request
    import production_input_guide
    result['authoring_guide'] = production_input_guide.summary(root, choice_path, choices)
    context = {key: value for key, value in result.items() if key != 'choices'}
    context['task_content'] = task
    if task_id is not None:
        context['task_binding'] = {'task_id': task_id}
    raw = c.encoded(context)
    open_work()
    state.remember_inputs(root, task, 'draft-inputs', out_dir, task_path=None,
        from_run=saved['run'] if saved else None, source_choices_path=candidate.get('source_choices'),
        runtime_arguments=runtime_arguments, context_sha256=c.digest(raw),
        request=request['text'] if request is not None else None,
        input_arguments=_authoring_arguments(task, operation=operation, request_file=request_file,
            apply_sources=apply_sources, focus=focus, route=route, artifact=artifact,
            execution=execution, features=features, model=model, service=service,
            stage=choices['authoring_stage'], source_image=source_image, scale=scale, purpose=purpose,
            change_scope=change_scope))
    _publish(root, out_dir, {**files, 'choices.json': c.encoded(choices), 'context.json': raw}, reader=reader)
    state.published_draft(root, task, out_dir)
    return {**result, 'choices_file': choice_path, 'context_file': (Path(out_dir) / 'context.json').as_posix()}


def _authoring_arguments(task: dict, *, operation: str, request_file: str | None,
                        apply_sources: list[str] | None, focus: str | None, route: str | None, artifact: str | None,
                        execution: str | None, features: list[str] | None,
                        model: str | None, service: str | None, stage: str | None = None,
                        source_image: Path | None = None, scale: float | None = None,
                        purpose: str | None = None, change_scope: dict | None = None) -> dict:
    """Recover the actual operation, request and source selections after interruption."""
    return {key: value for key, value in {
        'operation': operation, 'request-file': request_file, 'apply-source': apply_sources, 'focus': focus,
        'task-id': task['task_id'], 'route': route, 'artifact': artifact,
        'execution': execution, 'feature': features, 'model': model, 'service': service, 'stage': stage,
        'source-image': str(source_image) if source_image is not None else None, 'scale': scale, 'purpose': purpose,
        **(copy.deepcopy(change_scope) if change_scope is not None else {}),
    }.items() if value is not None}


def _retain_identity_context(authored: dict, captured, paths: dict, files: dict, out_dir: str) -> None:
    """Retain implicit state/reference owners as sources before reopening depiction choices."""
    if captured is None:
        return
    rows = authored['task']['sources']
    existing = {row['id'] for row in rows}
    for source in (captured.prepared.get('identity_coverage') or {}).get('sources', []):
        if source['id'] in existing:
            continue
        path = paths.get(source['path'])
        if path is None:
            extension = '.json' if source['format'] == 'json' else Path(source['path']).suffix
            name = 'retained/identity/' + source['sha256'] + extension
            files[name] = captured.loaded.evidence.read(source['sha256'])
            path = (Path(out_dir) / name).as_posix()
        prefix = source.get('source_pointer', '')
        rows.append({'id': source['id'], 'path': path, 'role': 'identity', 'disposition': 'applied',
            'locator': prefix or 'whole source',
            'reason': 'Retained original identity definition at its existing subject and source scope.',
            'identity': {'subject_ids': list(source['subject_ids']),
                         'selectors': [prefix + point for point in source['selectors']]}})
        if source.get('authority'):
            rows[-1]['identity']['authority'] = copy.deepcopy(source['authority'])
        authored['source_files'][path] = source['sha256']
        existing.add(source['id'])


def _bind_task(task: dict, task_id: str) -> dict:
    """Carry creative input into the selected task without importing another task's grant."""
    result = copy.deepcopy(task)
    if result['task_id'] != task_id:
        result['authority'] = None
        result.pop('execution_decisions', None)
    result['task_id'] = task_id
    return result


def _captured_inputs(root: Path, saved: dict | None, *, read_run=None):
    """Acquire the selected source revision once for a new editable draft."""
    if saved is None:
        return None
    import production_operations as production_workflow
    from production_saved_inputs import CapturedInputs
    loaded = read_run(saved['run']) if read_run is not None else production_workflow.read_run(root, saved['run'])
    if loaded.prepared['input_sha256'] != saved['input_sha256']:
        raise ValueError('source run changed during draft extraction')
    return CapturedInputs(root, loaded)


def _restore_selected_sources(choices: dict, captured, out_dir: str) -> tuple[dict, dict]:
    """Give retained source selections their own durable files in the new draft.

    Each owner redirects only declared file locators. Source identities, source
    scope and any provider values remain separate from these filesystem paths.
    Bounded world and moment inputs are acquired by their compiler owner from
    the source revision, preserving their path-bound compiled bundles.
    """
    if captured is None:
        return {}, {}
    authored = choices['authoring']
    task = authored['task']
    selected = {row['path'] for row in task.get('sources', [])}
    selected.update(row['origin']['path'] for row in task.get('sources', []) if row.get('origin'))
    selected.update(row['file'] for row in task.get('upload_sources', []))
    selected.update(authored['source_files'])
    if authored.get('upscale') is not None:
        selected.add(authored['upscale'].get('source'))
    negative = (task.get('authored') or {}).get('negative')
    if negative is not None:
        selected.add(negative.get('path'))
    target = choices.get('target') or {}
    selected.update(target.get(field) for field in ('model_file', 'vocabulary_record'))
    target_model_evidence = ((target.get('model') or {}).get('evidence')
                             if isinstance(target.get('model'), dict) else None)
    if target_model_evidence is not None:
        selected.add(target_model_evidence.get('path'))
    references = authored.get('references') or {}
    reference_model = (references.get('image_input') or {}).get('model')
    if reference_model is not None:
        selected.add(reference_model['evidence']['path'])
    binding = captured.loaded.consumer.get('image_input')
    if binding is not None:
        selected.add(binding['model']['evidence']['path'])
        selected.update(row['file'] for row in binding['references'])
        external = binding.get('external_request') or {}
        evidence = [external.get('schema'), external.get('vocabulary_record'),
                    (external.get('model_identity') or {}).get('evidence')]
        evidence.extend(row.get('evidence') for row in external.get('reference_fields', []))
        selected.update(item['path'] for item in evidence if item is not None)
    exported, paths = captured.export(out_dir + '/retained', selected_paths=selected)
    files = {'retained/' + path: raw for path, raw in exported.items()}
    paths = dict(paths)
    for before, after in list(paths.items()):
        if not Path(before).is_absolute():
            paths[str(captured.root / before)] = after

    def redirect(row, key):
        if row.get(key) in paths:
            row[key] = paths[row[key]]

    for row in task.get('sources', []):
        redirect(row, 'path')
        if row.get('origin'):
            redirect(row['origin'], 'path')
    for row in task.get('upload_sources', []):
        redirect(row, 'file')
    if negative is not None:
        redirect(negative, 'path')
    if authored.get('upscale') is not None:
        redirect(authored['upscale'], 'source')
    authored['source_files'] = {paths.get(path, path): digest
                                for path, digest in authored['source_files'].items()}
    references = authored.get('references')
    if references is not None:
        from production_reference_inputs import _authored_rows
        for row in _authored_rows(references):
            if row.get('source', {}).get('kind') == 'supplied-file':
                redirect(row['source'], 'resolved_path')
            redirect(row, 'file')
        references['source_files'] = {paths.get(path, path): value
                                     for path, value in references.get('source_files', {}).items()}
        model = (references.get('image_input') or {}).get('model')
        if model is not None:
            redirect(model['evidence'], 'path')
    for field in ('model_file', 'vocabulary_record'):
        redirect(target, field)
    if target_model_evidence is not None:
        redirect(target_model_evidence, 'path')
    return files, paths


def _restore_draft(root: Path, run: str, out_dir: str, saved_source: dict, *,
                   task_id: str | None, runtime_arguments: dict | None,
                   operation: str, request_file: str | None, apply_sources: list[str] | None, focus: str | None,
                   constructor_actions: dict,
                   model: str | None = None, service: str | None = None,
                   source_image: Path | None = None, scale: float | None = None,
                   purpose: str | None = None, open_work=lambda: None,
                   route: str | None = None, artifact: str | None = None,
                   execution: str | None = None, features: list[str] | None = None,
                   stage: str | None = None, change_scope: dict | None = None) -> dict:
    """Acquire an unfinished saved candidate, then use the common authoring operation."""
    choices = normalize_task_choices(saved_source['choices'])
    saved = _source_run(root, run)
    with _captured_inputs(root, saved) as captured:
        identity_baseline = captured.identity_sources() if operation == 'amend' else None
        restored, paths = _restore_selected_sources(choices, captured, out_dir)
        if choices.get('external') is not None:
            import production_external_inputs
            choices['external'] = production_external_inputs.relocate_sources(choices['external'], paths)
        owners = _retained_source_owners(captured)
        if operation == 'amend':
            _retain_identity_context(choices['authoring'], captured, paths, restored, out_dir)
        prior_basis = _saved_work_basis(captured)
        files = {**saved_source['files'], **{(Path(out_dir) / name).as_posix(): raw
                  for name, raw in restored.items()}}
    candidate = {'choices': choices, 'basis': prior_basis, 'files': files,
        'context': {'task_content': saved_source['task'],
                    'derived_from': {'source_run': saved}},
        'source_choices': None, 'origin': {'run': run, 'input_sha256': saved['input_sha256']},
        'runtime_arguments': runtime_arguments, 'identity_owners': owners,
        'identity_baseline': identity_baseline}
    import production_candidate_snapshot
    candidate['bounded'] = production_candidate_snapshot._bounded_inputs(root, choices,
        InputEvidence(root), candidate['context'])
    return _draft_candidate(root, candidate, out_dir, task_id=task_id,
        runtime_arguments=runtime_arguments, operation=operation, request_file=request_file,
        apply_sources=apply_sources, focus=focus, model=model, service=service,
        source_image=source_image, scale=scale, purpose=purpose, open_work=open_work,
        route=route, artifact=artifact, execution=execution, features=features, stage=stage,
        change_scope=change_scope, constructor_actions=constructor_actions)


def _validate_choices(value: dict, *, file: str | None = None) -> None:
    from state_protocol import validate_against_schema
    schema_path = 'schemas/authoring/production-input-draft.schema.json'
    schema = c.load(ROOT / schema_path)
    errors = validate_against_schema(value, schema)
    if errors:
        raise ProductionError('INPUT_CONSISTENCY_ERROR', 'input choices: ' + '; '.join(errors),
            phase='authoring', file=file,
            guidance={**authoring.EDITING_GUIDE, 'schema': schema_path},
            required_action='Correct the named choices field using ' + schema_path +
                '. Each authoring.documents value selects its editable file with {"file": STUDIO_PATH} '
                'and an optional "field" array for a JSON value.')


def read_choices(value: Any, *, file: str | None = None, root: Path | None = None) -> dict:
    input_preflight.require_shape(value, schema_path=input_preflight.CHOICES_SCHEMA,
        file=file, root=root or Path.cwd(), operation='read-choices')
    _validate_choices(value, file=file)
    return value


TASK_CHOICES = frozenset({'route', 'features', 'criteria', 'direction', 'delivery',
                          'world_views', 'moment_views', 'scene_materials', 'semantic_edit', 'generation',
                          'upload_sources'})
AUTHORED_TASK_CHOICES = frozenset({'route', 'features', 'criteria', 'direction',
                                  'world_views', 'moment_views', 'scene_materials', 'upload_sources'})


def normalize_task_choices(choices: dict) -> dict:
    """Keep each authored task value at its current editable owner."""
    result = copy.deepcopy(choices)
    changes = result.get('task_changes', {})
    if not isinstance(changes, dict) or set(changes) - TASK_CHOICES:
        raise ValueError('task_changes names authored route, depiction or review fields; source applications belong to work-basis.json')
    task = result['authoring']['task']
    for key in tuple(changes):
        if key in AUTHORED_TASK_CHOICES:
            task[key] = changes.pop(key)
    # Existing-image edits expose their plan at this selector. Keep its public
    # owner and remove an imported task copy that could shadow later edits.
    if 'semantic_edit' in task:
        if 'semantic_edit' not in changes and task['semantic_edit'] is not None:
            changes['semantic_edit'] = task['semantic_edit']
        task.pop('semantic_edit')
    result['task_changes'] = changes
    return result


def _chosen_task(task: dict, choices: dict) -> dict:
    changes = choices['task_changes']
    if not isinstance(changes, dict) or set(changes) - TASK_CHOICES:
        raise ValueError('task_changes names authored route, depiction or review fields; source applications belong to work-basis.json')
    result = authoring.chosen_task(task, choices['authoring'])
    if 'semantic_edit' not in choices['authoring']['task']:
        result.pop('semantic_edit', None)
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
    import production_operations as workflow
    directory, prepared, _, _ = workflow.read_run(root, saved['run'])
    if prepared['input_sha256'] != saved['input_sha256']:
        raise ValueError('source run input changed during input construction')
    path = task['delivery']['path']
    matches = [row for row in prepared['dependencies']
               if row['space'] in authoring.AUTHORING_SPACES and row['path'] == path]
    if len(matches) != 1:
        raise ValueError('source run has no unique saved delivery')
    return c.object_read(directory, matches[0]['sha256'])


def _retained_identity_sources(root: Path, task: dict, choices_path: str, reader: InputEvidence,
                               choices: dict) -> None:
    """Check the registered operation boundary from the actual current owners."""
    folder = Path(choices_path).parent.as_posix()
    path = (Path(folder) / 'context.json').as_posix()
    import production_authoring_state
    raw = reader.read(reader.select(path)) if c.local(root, path, exists=False).is_file() else b''
    production_authoring_state.require_input_context(root, task['task_id'], folder, raw)
    context = c.decode(raw)
    from production_saved_inputs import identity_context
    context = identity_context(root, context)
    basis = reader.json(reader.select(context['authoring_work']['basis']))
    current = InputEvidence(root, named_roots=reader.named_roots, read_source=reader.read_source,
        retained_snapshots=copy.deepcopy(reader.retained_snapshots), derived_inputs=dict(reader.derived_inputs))
    proposed = _current_identity_sources(task, choices, basis, current)
    import production_identity_boundary
    try:
        production_identity_boundary.require_unchanged(context, basis, proposed, file=path)
    except ProductionError as error:
        production_authoring_state.attach_identity_repair(root, choices_path, error)
        raise
    for selected, snapshot in current.snapshots.items():
        reader.read({'path': selected, 'sha256': snapshot['sha256']})


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
        return bound(copy.deepcopy(context['task_content'])), current, recovered, None, saved['run']
    if reference.get('initial') is True:
        task = copy.deepcopy(context['task_content'])
        if task['task_id'] != reference['task_id']:
            raise ValueError('initial authoring context has a different work task')
        return task, reference, None, None, None
    task_path = reference['path']
    reader.read(reference)
    task, _, current, recovered = _task(root, task_path, reader)
    return bound(copy.deepcopy(context['task_content'])), current, recovered, task_path, None


def _load_editable(root: Path, choices_path: str, reader: InputEvidence, *, register: bool = True) -> tuple[dict,dict,dict,list,dict]:
    path = c.local(root, choices_path)
    raw = c.read(path)
    acquired = reader
    reader = InputEvidence(root, snapshots=copy.deepcopy(acquired.snapshots), live=acquired.live,
        named_roots=acquired.named_roots, space=acquired.space, read_source=acquired.read_source,
        retained_snapshots=copy.deepcopy(acquired.retained_snapshots),
        derived_inputs=dict(acquired.derived_inputs))
    reader.read({'path': choices_path, 'sha256': c.digest(raw)})
    selected = normalize_task_choices(read_choices(c.decode(raw), file=choices_path, root=root))
    import production_reference_inputs
    production_reference_inputs.identify_choices(selected)
    choices = copy.deepcopy(selected)
    locations, gaps = {}, []
    choices['authoring'], locations, gaps = authoring.read_editable(choices['authoring'], reader)
    folder = Path(choices_path).parent.as_posix()
    context_path = (Path(folder) / 'context.json').as_posix()
    import production_authoring_state
    task_id = ((choices.get('authoring') or {}).get('task') or {}).get('task_id')
    task_id = task_id or production_authoring_state.active_task_id(root)
    context_raw = reader.read(reader.select(context_path)) if c.local(root, context_path, exists=False).is_file() else b''
    production_authoring_state.require_input_context(root, task_id, folder, context_raw)
    context = c.decode(context_raw)
    from production_saved_inputs import identity_context
    context = identity_context(root, context)
    work = context['authoring_work']
    if work['content'] != choices_path:
        raise ValueError('the authoring work identifies a different actual candidate')
    basis_path = c.local(root, work['basis'])
    basis_raw = c.read(basis_path)
    basis = c.decode(basis_raw)
    current_basis = (basis if any(row['field'] == 'authoring.documents.production_spec' for row in gaps)
                     else authoring_work.bind_task_subjects(basis, choices))
    projected, selected_files, _ = authoring_work.project(current_basis, selected, folder)
    reader.add_derived({(Path(folder) / name).as_posix(): content for name, content in selected_files.items()})
    task = _chosen_task(context['task_content'], projected)
    proposed = _current_identity_sources(task, projected, current_basis, reader)
    import production_identity_boundary
    try:
        if selected['authoring']['task'].get('sources') != projected['authoring']['task'].get('sources'):
            production_identity_boundary.require_unchanged(context, current_basis,
                _current_identity_sources(_chosen_task(context['task_content'], selected),
                                          selected, current_basis, reader), file=context_path)
        production_identity_boundary.require_unchanged(context, current_basis, proposed, file=context_path)
    except ProductionError as error:
        production_authoring_state.attach_identity_repair(root, choices_path, error)
        raise
    # Registration happens only after the complete operation boundary. In
    # particular, changed task-local identity cannot first become a new basis.
    if register and selected != c.decode(raw):
        if c.read(path) != raw:
            raise ValueError('editable choices changed while acquiring the candidate')
        raw = c.encoded(selected)
        c.atomic(path, raw, replace=True)
        # The owner assigned derived IDs after checking the author revision.
        # Capture its new bytes only after its own replacement has succeeded.
        reader.snapshots.pop(choices_path, None)
    ref = {'path': choices_path, 'sha256': c.digest(raw)}
    reader.read(ref)
    if register and current_basis != basis:
        if c.read(basis_path) != basis_raw:
            raise ValueError('authoring applications changed while acquiring the task subject definition')
        basis_raw = c.encoded(current_basis)
        c.atomic(basis_path, basis_raw, replace=True)
    reader.read({'path': work['basis'], 'sha256': c.digest(basis_raw)})
    gaps.extend(authoring_work.projection_diagnostics(current_basis, choices, root=root,
        choices_path=choices_path, basis_path=work['basis']))
    choices, selected_files, _ = authoring_work.project(current_basis, choices, folder)
    if register:
        authoring_work.publish_sources(root, folder, selected_files)
    else:
        reader.add_derived({(Path(folder) / name).as_posix(): raw for name, raw in selected_files.items()})
    for name in selected_files:
        reader.read(reader.select((Path(folder) / name).as_posix()))
    gaps.extend(authoring_work.unresolved(current_basis, choices,
        require_subject=authoring_work.requires_subject(choices['authoring']['task']),
        root=root, choices_path=choices_path, basis_path=work['basis']))
    ref = {**ref, 'files': {path: item['sha256'] for path, item in reader.snapshots.items()
                           if path != choices_path and not path.startswith('@')}}
    acquired.snapshots.update(reader.snapshots)
    acquired.retained_snapshots.update(reader.retained_snapshots)
    acquired.derived_inputs.update(reader.derived_inputs)
    acquired.read_paths.update(reader.read_paths)
    acquired.locators.update(reader.locators)
    return choices, ref, locations, gaps, current_basis


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
                    saved: dict | None, *, current_sources: bool,
                    allow_missing: bool = False) -> dict | None:
    """Retain the commission and original sources before editable adaptations."""
    if task.get('execution') != 'authored':
        return None
    previous = None
    if saved is not None:
        import production_operations as workflow
        previous = workflow.read_run(root, saved['run'])
    basis = (previous.prepared['task'].get('authored_basis') or {}) if previous else (origin_task.get('authored_basis') or {})
    originals = {item['source']['id']: item for item in basis.get('sources', [])}
    previous_sources = {item['id']: item for item in
                        (previous.prepared['task'] if previous else origin_task).get('sources', [])}
    retained = []
    for source in task.get('sources', []):
        original = originals.get(source['id'])
        if (not current_sources and original
                and previous_sources.get(source['id'], {}).get('path') == source['path']):
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
                   runtime_arguments: dict | None = None, runtime_sources: dict | None = None) -> dict:
    """Expose the actual editable revision, including its unfinished choices."""
    reader=InputEvidence(root,named_roots={'@skill':ROOT})
    choices,ref,locations,gaps,current_basis=_load_editable(root,choices_path,reader,register=register)
    if runtime_arguments is None:
        # A prepared producer supplies a runtime only for the exact acquired
        # editable source, including every authored file in this reference.
        runtime_arguments = (runtime_sources or {}).get(c.content_id(ref))
    with adapters.using_runtime(runtime_arguments):
        base,origin,saved,task_path,from_run=_authoring_source(root,choices_path,reader,choices,
            task_path=task_path,from_run=from_run,read_run=read_run)
        if saved is not None:
            with _captured_inputs(root, saved, read_run=read_run) as captured:
                captured.bind(reader)
        task=_chosen_task(base,choices)
        projected = production_target.project(choices, task, root, reader,
                                              (Path(choices_path).parent / 'view').as_posix(),
                                              source=read_run.target_runtime() if isinstance(read_run, SourceRuns) else None)
        task = projected['task']
        for source in task.get('sources',[]):
            path=source.get('path')
            if not path:continue
            try:reader.read(reader.select(path))
            except (ValueError,OSError) as exc:
                gaps.append({'field':'authoring.task.sources','file':path,'code':'INPUT_UNREADABLE','cause':str(exc),
                    'phase':'source-read','message':'The task source '+path+' cannot be read.',
                    'required_action':'Restore the selected original or reacquire its complete Production source row '
                        'with acquire-source. The next projection regenerates '+path+'; task.sources is derived.',
                    'guidance':phase_guidance('source-read')})
        basis = _authored_basis(root, task, base, reader, saved, allow_missing=True,
            current_sources=choices.get('authoring') is not None or 'sources' in choices['task_changes'])
        context_path = (Path(choices_path).parent / 'context.json').as_posix()
        context = c.decode(reader._decode(reader.snapshots[context_path]))
        current_scope = reading_scope.selection(root, choices, task, basis=current_basis, context=context)
        unresolved=_unresolved(choices,task,root=root,runtime_arguments=runtime_arguments,choices_path=choices_path)+gaps
        unresolved.extend(item for item in projected['unresolved'] if item not in unresolved)
        unresolved.extend(_target_gaps(choices, task, projected))
        unresolved.extend(_guidance_gap(root, task, choices, projected, runtime_arguments,
            choices_path=choices_path, authoring_scope=current_scope if 'authoring_stage' in choices else None))
        unresolved = authoring.locate_unresolved(unresolved, locations)
        content=((choices.get('authoring') or {}).get('delivery') or {}).get('content')
        delivery=b'' if content is None else content.encode('utf-8') if isinstance(content,str) else c.encoded(content)
        captured={path:reader._decode(value) for path,value in reader.snapshots.items() if not path.startswith('@')}
        if context.get('candidate_inputs'):
            from production_candidate_snapshot import CapturedCandidate
            bounded = CapturedCandidate(root, context['candidate_inputs'])
            for path in context['candidate_inputs']['files']:
                raw = bounded.bytes(path)
                if path in captured and captured[path] != raw:
                    raise ValueError('One authoring input selects different acquired revisions: ' + path)
                captured[path] = raw
        work_basis = c.decode(captured[(Path(choices_path).parent / 'context.json').as_posix()])['authoring_work']['basis']
        return {'task':task,'choices':c.decode(captured[choices_path]),'resolved_choices':choices,
            'files':{},'delivery':delivery,'unresolved':unresolved,'source_map':locations,'captured':captured,
            'origin':origin,'source_run':saved,'task_path':task_path,'from_run':from_run,'choices_ref':ref,
            'authored_basis':basis,'work_basis':work_basis,'target_knowledge':projected['knowledge'],
            'target_identity':production_target.projected_identity(projected),
            'runtime_arguments': runtime_arguments,
            'authoring_scope': current_scope,
            'authoring_stage': reading_scope.projection(choices, task, unresolved, scope=current_scope),
            'stage_actions': reading_scope.actions(root, choices_path, current_scope['stage'], runtime_arguments),
            'authoring_work': {'basis': current_basis, 'content': copy.deepcopy(choices)}}


def compare_inputs(root: Path, choices_paths: list[str], *, runtime_arguments: dict | None = None) -> dict:
    """Compare current editable works through the common read-only owner."""
    from authoring_work import compare_works
    views = [authoring_view(root, path, register=False, runtime_arguments=runtime_arguments)
             for path in choices_paths]
    return compare_works([view['authoring_work'] for view in views], labels=choices_paths)


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
    choices,choices_ref,locations,file_gaps,current_basis = _load_editable(root,choices_path,reader)
    base_task, task_ref, saved, task_path, from_run = _authoring_source(
        root, choices_path, reader, choices, task_path=task_path, from_run=from_run)
    if saved is not None:
        with _captured_inputs(root, saved) as captured:
            captured.bind(reader)
    task = _chosen_task(base_task, choices)
    context_path = (Path(choices_path).parent / 'context.json').as_posix()
    context = c.decode(reader._decode(reader.snapshots[context_path]))
    final_scope = (reading_scope.selection(root, choices, task, basis=current_basis, context=context,
                                          selected_stage='prepare') if 'authoring_stage' in choices else None)
    _retained_identity_sources(root, task, choices_path, reader, choices)
    basis = _authored_basis(root, task, base_task, reader, saved,
        current_sources=choices.get('authoring') is not None or 'sources' in choices['task_changes'])
    _destination(root, out_dir)
    import production_authoring_state
    if publish:
        production_authoring_state.remember_inputs(root, task, 'build-inputs', out_dir,
            task_path=task_path, from_run=from_run, choices_path=choices_path, runtime_arguments=runtime_arguments)
    projected = production_target.project(choices, task, root, reader, out_dir)
    choices['target'] = copy.deepcopy(projected['choices']['target'])
    missing = _unresolved(choices, task, root=root, runtime_arguments=runtime_arguments,
        choices_path=choices_path)+file_gaps
    missing.extend(item for item in projected['unresolved'] if item not in missing)
    missing.extend(_target_gaps(choices, task, projected))
    missing.extend(_guidance_gap(root, task, choices, projected, runtime_arguments,
        choices_path=choices_path, authoring_scope=final_scope))
    missing = authoring.locate_unresolved(missing, locations)
    if missing:
        actions = [_reading_action(root, task, choices, runtime_arguments, choices_path=choices_path,
                                   authoring_scope=final_scope)] if any(
            item['field'].startswith('reading') for item in missing) else []
        if actions and final_scope is not None and reading_scope.stage(choices, task) != 'prepare':
            if any(not item['field'].startswith('reading') for item in missing):
                advance = production_authoring_state._action(root, 'inspect-inputs',
                    '--choices', choices_path, *production_authoring_state._arguments(runtime_arguments or {}),
                    reason='Resolve the named authored choices in their current stage before final input binding.')
                instruction = ('Continue the named incomplete choices in their current stage with ' + advance['shown'] +
                    '. Final input-binding guidance is still required after the content is complete.')
            else:
                advance = next(item for item in reading_scope.actions(root, choices_path,
                    reading_scope.stage(choices, task), runtime_arguments) if item['stage'] == 'prepare')
                instruction = ('Continue the completed authored content at prepare with ' + advance['shown'] +
                    ', then read its current input-binding contract and select the issued reading key.')
            actions = [advance]
            for item in missing:
                if item['field'].startswith('reading'):
                    item.update(next_action=advance, next_actions=[advance],
                        required_action=instruction)
        return {'state': 'draft', 'ok': False, 'inputs': {}, 'unresolved': missing,
                'target_knowledge': projected['knowledge'],
                'derived_from': {'task': task_ref, 'choices': choices_ref},
                'next_actions': [*actions, {'operation': 'edit-choices', 'args': {'path': choices_path},
                                  'external_effect': False}]}
    task, material_choices = projected['task'], projected['choices']
    target_files = projected['files']
    reading = _reading(choices['reading'], root=root, task=task, authoring_scope=final_scope)
    visual, visual_context = adapters.build_visual(choices['visual'], task, reader, root)
    validation, validation_context = adapters.build_validation(choices['validation'], task, reader, root,
                                                              target=projected['resolved_target'])
    adapters.cross_check(visual_context, validation_context)
    if validation is not None:
        dialect = validation_context.get('dialect', route_reading._NO_MODEL)
        route_reading.require_route_reading(reading, studio=root, routes={task['route']},
                                           features=task['features'], execution=task['execution'], dialect=dialect,
                                           operation='author' if task['execution'] == 'authored' else 'prepare',
                                           authoring_scope=final_scope)
    content = {'route-reading.json': reading}
    if visual is not None:
        content['visual-continuity.json'] = visual
    if validation is not None:
        content['request-validation.json'] = validation
    try:
        with _staged_files(root, out_dir, target_files):
            copied_task, authored_files, authored_delivery = authoring.materialize(
                root, task, material_choices.get('authoring'), reader, out_dir, saved=saved, validation=validation,
                locations=locations)
    except authoring.UnresolvedChoice as exc:
        return {'state': 'draft', 'ok': False, 'inputs': {},
                'unresolved': authoring.locate_unresolved([exc.as_unresolved()], locations),
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
    encoded = {**target_files, **authored_files}
    encoded['work-basis.json'] = reader.read(reader.select(task['work_basis']))
    copied_task['work_basis'] = (Path(out_dir) / 'work-basis.json').as_posix()
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
        if 'image-input.json' in external_files:
            copied_task['image_input'] = (Path(out_dir) / 'image-input.json').as_posix()
        else:
            # A reference that still awaits its upload has no image input yet;
            # the identity view reads its rows from the reference choices.
            copied_task.pop('image_input', None)
        route_reading.require_route_reading(reading, studio=root, routes={copied_task['route']},
            features=copied_task['features'], execution=copied_task['execution'], dialect=external_context['dialect'],
            authoring_scope=final_scope)
    else:
        external_context = None
    identity = _identity_view(root, copied_task, reader, files=encoded, out_dir=out_dir,
                              choices=choices, basis=current_basis)
    identity_gaps = _identity_gaps(identity, root=root, choices_path=choices_path, locations=locations)
    def recheck():
        _reading(choices['reading'], root=root, task=task, authoring_scope=final_scope)
        _retained_identity_sources(root, task, choices_path, reader, choices)
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
    from production_operations import validate_task
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
    if context.get('candidate_inputs'):
        result['derived_from']['candidate_inputs'] = context['candidate_inputs']
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
        source = assembled['derived_from'].get('source_run')
        captured = _captured_inputs(root, source)
        from production_candidate_snapshot import retained as retained_candidate
        retained = retained_candidate(root, assembled['_task'],
            assembled['derived_from'].get('candidate_inputs'), captured)
        compiled=compiler.compile_task(root,path,persist=persist,identity=identity,
            derived=assembled['_files'],source_inputs=assembled['_captured'],retained_inputs=retained)
        compiled.report['authoring']={'choices':choices_path,
            'choices_ref':assembled['derived_from']['choices'],'source_map':assembled['_source_map'],
            'source_run': (assembled['derived_from'].get('source_run') or {}).get('run'),
            'work_basis': assembled['_task']['work_basis']}
        context_path = (Path(choices_path).parent / 'context.json').as_posix()
        context_raw = assembled['_captured'].get(context_path)
        if context_raw is not None:
            context = c.decode(context_raw)
            source_result = context.get('source_result')
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
        choices_raw = assembled['_captured'].get(choices_path)
        source_choices = c.decode(choices_raw) if choices_raw is not None else {}
        inline_generation = (source_choices.get('authoring') or {}).get('generation') or {}
        for diagnostic in compiled.report.get('diagnostics',[]):
            generated=diagnostic.get('file')
            name=reverse.get(generated)
            field='authoring.delivery' if name=='delivery' else 'authoring.documents.'+name.replace('-','_') if name else None
            if name == 'production-task':
                field = 'authoring.task'
                pointer = diagnostic.get('pointer') or ''
                key = next((key for key in inline_generation if pointer == '$.generation.' + key or
                    pointer.startswith(('$.generation.' + key + '.', '$.generation.' + key + '['))), None)
                if pointer == '$.generation' or key is not None:
                    field = 'authoring.generation' + ('.' + key if key is not None else '')
                    diagnostic['generated_pointer'] = pointer
                    diagnostic['pointer'] = '/authoring/generation' + (
                        '/' + key.replace('~', '~0').replace('/', '~1') if key is not None else '')
                    diagnostic['repair_owner'] = {'file': choices_path, 'pointer': diagnostic['pointer']}
                    from production_input_guide import action
                    diagnostic['next_action'] = action(root, choices_path, field='authoring.generation')
                    if diagnostic['code'] != 'CHECK_NOT_PERFORMED':
                        diagnostic['required_action'] = ('Edit ' + choices_path + ' at ' +
                            diagnostic['pointer'] + '. ' + diagnostic['required_action'])
            origin=assembled['_source_map'].get(field)
            if origin is not None:
                diagnostic['generated_file']=generated
                diagnostic['file']=origin['file']
                diagnostic['authoring_field']=field
                if origin.get('pointer') is not None:diagnostic['source_field']=origin['pointer']
                owner = origin.get('guidance') or {}
                diagnostic['guidance'] = {**owner, **(diagnostic.get('guidance') or {})}
                if owner.get('schema'):
                    diagnostic['guidance']['schema'] = owner['schema']
                if diagnostic['code'] != 'CHECK_NOT_PERFORMED':
                    diagnostic['required_action'] = 'Edit ' + origin['file'] + '. ' + diagnostic['required_action']
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
    import production_operations as production_workflow
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


def _read_export(root: Path, task_path: str, task_id: str, *, acquired=None, task=None):
    """Acquire the registered exported inputs and their existing source revision."""
    import production_authoring_state
    import production_store
    publication = production_authoring_state.input_publication(root, task_id, task_path)
    if publication is None:
        return None
    acquired = acquired or {}
    def unchanged(path, expected, *, fresh=False):
        raw = production_store.stable_bytes(root, path) if fresh or path not in acquired else None
        actual = c.digest(raw) if raw is not None else acquired[path]
        if actual != expected:
            raise ProductionError('INPUT_PUBLICATION_CHANGED',
                'The exported input differs from its registered publication.', phase='authoring-context',
                file=path, required_action='Edit the owning choices and build a new export directory; keep published input files intact.')
        return raw
    task_raw = unchanged(task_path, publication['task_sha256'])
    report = c.decode(unchanged(publication['report'], publication['report_sha256'], fresh=True))
    for value in report['inputs'].values():
        unchanged(value['path'], value['sha256'])
    return (task if task is not None else c.decode(task_raw)), report


def retained_export_inputs(root: Path, task_path: str, task_id: str, *, acquired=None, task=None):
    exported = _read_export(root, task_path, task_id, acquired=acquired, task=task)
    if exported is None:
        return None
    task, report = exported
    captured = _captured_inputs(root, report['derived_from'].get('source_run'))
    from production_candidate_snapshot import retained as retained_candidate
    return retained_candidate(root, task, report['derived_from'].get('candidate_inputs'), captured)


def export_parent(root: Path, task_path: str, compiled) -> dict | None:
    """Retain verified source lineage when an exported task is prepared directly."""
    if not compiled.report.get('publishable'):
        return None
    acquired = {item['path']: item.get('selection_sha256', item['sha256'])
                for item in compiled.prepared['dependencies'] if item['space'] in authoring.AUTHORING_SPACES}
    exported = _read_export(root, task_path, compiled.prepared['task']['task_id'],
                            acquired=acquired, task=compiled.prepared['task'])
    if exported is None:
        return None
    _, report = exported
    origin = report['derived_from']
    authored = {'choices': origin['choices']['path'], 'choices_ref': origin['choices'],
                'source_run': (origin.get('source_run') or {}).get('run')}
    source_result = origin.get('source_result')
    if source_result is not None and (compiled.package or {}).get('source', {}).get('sha256') == source_result['file']['sha256']:
        authored['source_result'] = source_result
    compiled.prepared['authoring'] = copy.deepcopy(authored)
    compiled.report['authoring'] = authored
    return compilation_parent(root, compiled)




def stage_inputs(root: Path, choices_path: str, stage: str, *,
                 runtime_arguments: dict | None = None) -> dict:
    """Select the current work without replacing its authored sources or results."""
    from production_authoring_state import registered_runtime_arguments
    selected_runtime = registered_runtime_arguments(root, choices_path) or runtime_arguments
    with adapters.using_runtime(selected_runtime):
        # Validate the actual editable owner before recording its navigation choice.
        authoring_view(root, choices_path, register=False, runtime_arguments=selected_runtime)
        reading_scope.select(root, choices_path, stage)
        return inspect_inputs(root, choices_path=choices_path, runtime_arguments=selected_runtime)


def command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> dict:
    root = args.root.resolve(strict=True)
    if args.command == 'explain-inputs':
        import production_input_guide
        return production_input_guide.explain(root, args.choices, field=args.field)
    if args.command == 'stage-inputs':
        from pack_runtime_cli import has_pack_runtime_arguments
        runtime_arguments = adapters.configure_runtime(args, parser) if has_pack_runtime_arguments(args) else None
        return stage_inputs(root, args.choices, args.stage, runtime_arguments=runtime_arguments)
    if args.command == 'inspect-inputs' and args.task is None and args.from_run is None:
        from pack_runtime_cli import has_pack_runtime_arguments
        if has_pack_runtime_arguments(args):
            from catalog_retrieval.runtime import selected_pack_settings, using_pack_runtime
            # A registered producer keeps its own runtime. These CLI paths
            # supply only drafts that have no recorded runtime selection.
            with using_pack_runtime(selected_pack_settings()):
                runtime_arguments = adapters.configure_runtime(args, parser)
                return inspect_inputs(root, choices_path=args.choices, runtime_arguments=runtime_arguments)
        return inspect_inputs(root, choices_path=args.choices)
    runtime_arguments = adapters.configure_runtime(args, parser)
    if args.command == 'compare-inputs':
        return compare_inputs(root, args.choices, runtime_arguments=runtime_arguments)
    if args.command == 'inspect-inputs':
        result = inspect_inputs(root, args.task, from_run=args.from_run, choices_path=args.choices)
        for action in result['craft_lookup']['next_actions']:
            action['args'].update(runtime_arguments or {})
        return result
    if args.command == 'draft-inputs':
        from production_cli_arguments import change_scope_from_arguments
        return draft_inputs(root, args.task, args.out_dir, from_run=args.from_run,
                            source_choices=getattr(args, 'choices', None),
                            runtime_arguments=runtime_arguments, route=args.route, artifact=args.artifact_kind,
                            execution=args.execution, task_id=args.task_id, features=args.features,
                            model=args.model,service=args.service,source_image=args.source_image,
                            scale=args.scale,purpose=args.purpose,new_task=args.new_task,
                            source_run=args.source_run,source_candidate=args.source_candidate,
                            edit_character=args.edit_character,edit_slot=args.edit_slot,
                            operation=args.operation,request_file=args.request_file,apply_sources=args.apply_sources,focus=args.focus,
                            stage=args.stage, change_scope=change_scope_from_arguments(args))
    return build_inputs(root, args.task, args.choices, args.out_dir, from_run=args.from_run, runtime_arguments=runtime_arguments)
