"""Select knowledge for the actual editable work, without inheriting knowledge.

The choices file owns the current stage. Saved definitions, depictions and text
remain actual source material; a previous stage's delivery receipt is never a
substitute for reading the current operation's complete source contracts.
"""
from __future__ import annotations

import base64
import copy
from pathlib import Path

import execution_contract as c

STAGES = ('definition', 'depiction', 'rendition', 'prepare')
CONDITIONS = frozenset({'image-source', 'unknown-sources', 'references', 'accepted-variation',
    'state', 'action-slice', 'multiple-results', 'target-change', 'semantic-edit',
    'render-intent', 'production-spec', 'plot'})
FIELDS = {'stage', 'composition', 'source_formats', 'documents', 'render_operation', 'conditions'}
STAGE_MEANINGS = {
    'definition': 'Establish or revise the concrete character and source applications for this use.',
    'depiction': 'Develop the intended depiction, actual candidate and independent assessment criteria.',
    'rendition': 'Carry the chosen depiction into the actual prompt, negative text and rendering controls.',
    'prepare': 'Bind the saved authored content and carriers to the exact native request without changing their meaning.',
}


def stage(choices: dict, task: dict | None = None) -> str:
    """An unscoped existing task retains its final input operation until selected."""
    selected = choices.get('authoring_stage')
    if selected is None:
        selected = 'prepare'
    if selected not in STAGES:
        raise ValueError('authoring_stage must be one of: ' + ', '.join(STAGES))
    return selected


def operation(selected: str, execution: str) -> str:
    if selected not in STAGES:
        raise ValueError('unknown authoring stage: ' + str(selected))
    return 'prepare' if selected == 'prepare' and execution != 'authored' else 'author'


def validate(value: dict | None, *, reading_operation: str | None = None, execution: str | None = None) -> None:
    if value is None:
        return
    c.exact(value, FIELDS, 'authoring reading scope')
    if value['stage'] not in STAGES or value['composition'] not in {'compose', 'amend'}:
        raise ValueError('authoring reading needs its actual stage and compose/amend operation')
    for key in ('source_formats', 'documents', 'conditions'):
        rows = value[key]
        if not isinstance(rows, list) or any(not isinstance(item, str) or not item for item in rows) or rows != sorted(set(rows)):
            raise ValueError('authoring reading ' + key + ' must be normalized unique strings')
    if set(value['source_formats']) - {'text', 'json', 'image', 'binary', 'unknown'}:
        raise ValueError('unknown authoring source format')
    if set(value['conditions']) - CONDITIONS:
        raise ValueError('unknown authoring reading condition')
    if value['render_operation'] is not None:
        c.text(value['render_operation'], 'selected render operation')
    if reading_operation is not None and execution is not None and reading_operation != operation(value['stage'], execution):
        raise ValueError('the authoring stage and reading operation differ')


def matches(rule: dict, value: dict) -> bool:
    """Only explicit structure selects scope; prose is never classified."""
    if 'stages' in rule and value['stage'] not in rule['stages']:
        return False
    if 'compositions' in rule and value['composition'] not in rule['compositions']:
        return False
    conditions = set(value['conditions'])
    # An unreadable selected original must not be used as evidence of absence.
    # Its ordinary input diagnostic still requires source repair.
    if 'unknown-sources' in conditions:
        conditions.update({'image-source', 'accepted-variation', 'state', 'action-slice'})
    if 'conditions_any' in rule and not conditions.intersection(rule['conditions_any']):
        return False
    if 'conditions_all' in rule and not set(rule['conditions_all']).issubset(conditions):
        return False
    if 'conditions_none' in rule and conditions.intersection(rule['conditions_none']):
        # Retain both conception paths while an actual source is unresolved.
        return 'unknown-sources' in conditions
    return True


def _selected_value(root: Path, value):
    if not isinstance(value, dict) or not isinstance(value.get('file'), str):
        return value
    path = c.local(root, value['file'])
    raw = c.read(path)
    result = c.decode(raw) if path.suffix.lower() == '.json' or value.get('field') else raw.decode('utf-8')
    for part in value.get('field', []):
        result = result[part]
    return result


def _is_image(source: dict) -> bool:
    if source.get('format') != 'binary':
        return False
    raw = base64.b64decode(source['data'], validate=True)
    return (raw.startswith((b'\x89PNG\r\n\x1a\n', b'\xff\xd8\xff', b'GIF87a', b'GIF89a', b'BM', b'II*\x00', b'MM\x00*'))
            or raw[:4] == b'RIFF' and raw[8:12] == b'WEBP'
            or len(raw) > 12 and raw[4:8] == b'ftyp' and raw[8:12] in {b'avif', b'avis', b'heic', b'heif'})


def _image_plan(root: Path, value) -> dict:
    if isinstance(value, str):
        value = c.load(c.local(root, value))
    if not isinstance(value, dict):
        raise ValueError('selected image input must be a plan object or a readable plan file')
    return value


def _reference_conditions(root: Path, authored: dict, external: dict, task: dict) -> set[str]:
    """Follow current source owners; retained witnesses and transports select no sources."""
    from production_reference_inputs import _authored_rows
    from production_target import _reference_choices
    result = set()
    try:
        selected = any(_authored_rows(value) for value in _reference_choices(authored, external))
        # Canonical reference choices replace external transport rows, which can
        # remain after their source was deselected. A current inline plan also
        # replaces the original task's image-input path.
        if external.get('reference_delivery') is not None:
            delivery = external['reference_delivery']
            if not isinstance(delivery, dict) or not isinstance(delivery.get('choices'), dict):
                raise ValueError('selected reference delivery requires its source choices')
            plan = None
        elif 'image_input' in external:
            plan = external['image_input']
        elif authored.get('references') is not None:
            plan = None
        else:
            plan = task.get('image_input')
        if plan is not None:
            rows = _image_plan(root, plan).get('references')
            if not isinstance(rows, list):
                raise ValueError('selected image input requires its reference rows')
            selected = selected or bool(rows)
        if selected:
            result.update({'references', 'image-source'})
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        # An unreadable selected plan cannot establish that no image is used.
        # The ordinary input diagnostics still require its repair.
        result.update({'references', 'image-source', 'unknown-sources'})
    return result


def _selected_target_identity(root: Path, target: dict, task: dict, external: dict, *, read_source=None) -> dict:
    """Compare explicit target identity without acquiring a different model runtime."""
    result = {'route': task.get('route'), 'execution': task.get('execution')}
    kind = target.get('kind')
    if kind == 'catalog':
        result.update(model=target.get('model'), service=target.get('service'))
        # A dispatcher chooses its native operation from the current model
        # guidance. Only an explicitly selected operation is comparable here.
        if target.get('operation') is not None:
            result['operation'] = target['operation']
    elif kind == 'acquired':
        path = target.get('model_file')
        model = c.decode(read_source(path)) if read_source is not None else c.load(c.local(root, path))
        result.update(model=model.get('id'), service=target.get('service'))
    else:
        model = target.get('model') if kind == 'external' else None
        if model is None and not target and external.get('image_input') is not None:
            plan = external['image_input']
            if isinstance(plan, str) and read_source is not None:
                plan = c.decode(read_source(plan))
            model = _image_plan(root, plan).get('model')
        actual = (model or {}).get('target') or {}
        result.update(model=actual.get('model_identifier'), service=actual.get('service'),
                      operation=actual.get('operation'))
    return result


def selection(root: Path, choices: dict, task: dict, *, basis: dict | None = None,
              context: dict | None = None, selected_stage: str | None = None, read_source=None) -> dict:
    """Project the one authored selection into reproducible reading conditions."""
    authored = choices.get('authoring') or {}
    documents = authored.get('documents') or {}
    conditions, formats = set(), set()
    if basis is None:
        basis_path = ((context or {}).get('authoring_work') or {}).get('basis')
        try:
            basis = c.load(c.local(root, basis_path)) if basis_path else {}
        except (ValueError, OSError, TypeError):
            basis = {}
            conditions.add('unknown-sources')
    applied = {row['source'] for row in basis.get('applications', {}).values()}
    for identifier in applied:
        source = basis.get('sources', {}).get(identifier)
        if not isinstance(source, dict):
            formats.add('unknown'); conditions.add('unknown-sources'); continue
        kind = source.get('format', 'unknown')
        try:
            if _is_image(source):
                kind = 'image'
                conditions.add('image-source')
            elif kind == 'binary':
                conditions.add('unknown-sources')
        except (ValueError, TypeError):
            conditions.add('unknown-sources')
        formats.add(kind if kind in {'text', 'json', 'image', 'binary'} else 'unknown')
    external = choices.get('external') or {}
    conditions.update(_reference_conditions(root, authored, external, task))
    direction = task.get('direction') or {}
    if direction.get('action_slice') is not None:
        conditions.add('action-slice')
    if direction.get('source_allowances'):
        conditions.add('accepted-variation')
    if any(binding.get('treatment') == 'authorized-variation'
           for row in task.get('criteria', []) if isinstance(row, dict)
           for binding in (row.get('identity_bindings') or []) if isinstance(binding, dict)):
        conditions.add('accepted-variation')
    if (set(documents).intersection({'state_graphs', 'state_lineage', 'state_snapshot', 'visual_continuity'})
            or choices.get('visual') is not None or task.get('route') == 'state-series'):
        conditions.add('state')
    if task.get('semantic_edit') or (choices.get('task_changes') or {}).get('semantic_edit'):
        conditions.update({'semantic-edit', 'image-source', 'references'})
    generation = authored.get('generation') or {}
    if generation.get('render_intent') is not None or (task.get('generation') or {}).get('render_intent') is not None:
        conditions.add('render-intent')
    if isinstance(generation.get('count'), int) and generation['count'] > 1 or task.get('route') in {'batch', 'state-series', 'character-sheet'}:
        conditions.add('multiple-results')
    if ('production_spec' in documents or any(row.get('role') == 'production-spec'
            and row.get('disposition') == 'applied' for row in task.get('sources', []))):
        conditions.add('production-spec')
    if 'plot' in documents:
        conditions.add('plot')
    target = choices.get('target') or {}
    previous = (((context or {}).get('derived_from') or {}).get('source_run') or {}).get('target_identity')
    if previous is not None:
        try:
            now = _selected_target_identity(root, target, task, external, read_source=read_source)
            changed = (not now.get('model') or not now.get('service')
                       or any(previous.get(key) != value for key, value in now.items()))
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            changed = True
        if changed:
            conditions.add('target-change')
    value = {'stage': selected_stage or stage(choices, task),
             'composition': basis.get('operation') or ((context or {}).get('authoring_work') or {}).get('operation') or 'compose',
             'source_formats': sorted(formats), 'documents': sorted(documents),
             'render_operation': target.get('operation') or ('upscale' if task.get('route') == 'upscale' else 'generation'),
             'conditions': sorted(conditions)}
    validate(value)
    return value


def from_choices(root: Path, path: str, *, selected_stage: str | None = None,
                 include_choices: bool = False) -> tuple:
    root = c._root(root)
    choices = c.load(c.local(root, path))
    context = c.load(c.local(root, (Path(path).parent / 'context.json').as_posix()))
    import production_inputs
    task = production_inputs._chosen_task(context['task_content'], choices)
    result = (selection(root, choices, task, context=context, selected_stage=selected_stage), task)
    return (*result, choices) if include_choices else result


def _task_selection(root: Path, task: dict, read_source) -> dict:
    """Read a completed task's actual selectors, without a reading receipt."""
    from production_authoring import DOCUMENTS
    from production_target import extract
    task = copy.deepcopy(task)
    generation = task.get('generation') or {}
    documents = {name: None for name in DOCUMENTS if generation.get(name) is not None}
    if generation.get('production_spec'):
        documents['production_spec'] = c.decode(read_source(generation['production_spec']))
    else:
        specifications = [row for row in task.get('sources', [])
                          if row['disposition'] == 'applied' and row['role'] == 'production-spec']
        if specifications:
            documents['production_spec'] = c.decode(read_source(specifications[0]['path']))
    plan = c.decode(read_source(task['image_input'])) if task.get('image_input') else None
    references = None
    if generation.get('references'):
        prepared = c.decode(read_source(generation['references']))
        references = {'image_input': {'references': prepared['selected_references']}}
    if plan is not None:
        references = {'image_input': {'references': plan['references']}}
    authored = {'task': task, 'documents': documents, 'generation': copy.deepcopy(generation),
                'references': references, 'upscale': None}
    if task.get('route') == 'upscale' and task.get('execution') == 'dispatcher':
        authored['upscale'] = c.decode(read_source(task['delivery']['path']))
    external = {'image_input': plan} if task.get('execution') == 'external' else None
    target = extract(task, authored, external)
    return {'authoring_stage': 'prepare', 'authoring': authored, 'target': target,
            'external': external, 'task_changes': {}}


def from_task(root: Path, task: dict, *, read_source=None) -> dict:
    """Derive final-input knowledge from actual task sources at publication.

    Editable choices, exported tasks and direct task preparation share this
    boundary. The supplied receipt cannot choose its own stage or conditions.
    The caller supplies its captured reader so source selection and compilation
    observe the same bytes.
    """
    read_source = read_source or (lambda path: c.read(c.local(root, path)))
    basis = c.decode(read_source(task['work_basis']))
    choices = _task_selection(root, task, read_source)
    context = None
    baseline = basis.get('baseline') or {}
    previous_task = (baseline.get('authoring') or {}).get('task') or baseline.get('task')
    if previous_task is not None and previous_task.get('execution') in {'dispatcher', 'external'}:
        try:
            if baseline.get('authoring') is not None:
                previous = _selected_target_identity(root, baseline.get('target') or {}, previous_task,
                                                     baseline.get('external') or {}, read_source=read_source)
            else:
                prior = _task_selection(root, previous_task, read_source)
                previous = _selected_target_identity(root, prior.get('target') or {}, previous_task,
                                                     prior.get('external') or {}, read_source=read_source)
            context = {'derived_from': {'source_run': {'target_identity': previous}}}
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            # An unavailable selected baseline establishes no target equality.
            context = {'derived_from': {'source_run': {'target_identity': {}}}}
    return selection(root, choices, task, basis=basis, context=context, selected_stage='prepare',
                     read_source=read_source)


def actions(root: Path, path: str, selected: str, runtime_arguments: dict | None = None) -> list[dict]:
    from cli_invocation import python_argv, shown
    result = []
    for target in STAGES:
        if target == selected:
            continue
        arguments = {'root': str(root), 'choices': path, 'stage': target, **(runtime_arguments or {})}
        argv = python_argv(Path(__file__).with_name('production_workflow.py'), 'stage-inputs')
        for name, value in arguments.items():
            for item in value if isinstance(value, list) else [value]:
                argv.extend(('--' + name, str(item)))
        result.append({'operation': 'stage-inputs', 'stage': target, 'args': arguments,
                       'argv': argv, 'shown': shown(argv), 'reason': STAGE_MEANINGS[target],
                       'external_effect': False})
    return result


def _diagnostic_stage(row: dict) -> str:
    field = row.get('field') or row.get('pointer') or ''
    if field.startswith(('reading', '/reading', 'work_basis', 'basis', '/basis')) or 'IDENTITY' in row.get('code', ''):
        return 'definition'
    if any(part in field for part in ('subjects', '.identity', '.sources', 'source_roles')):
        return 'definition'
    if any(part in field for part in ('direction', 'criteria', 'creative_intent', 'semantic_edit', 'render_intent')):
        return 'depiction'
    if field.startswith(('authoring.delivery', 'authoring.documents.negative', 'authoring.documents.parameters',
                         'authoring.documents.integrated_prompt', 'authoring.documents.native_negative',
                         'target', 'authoring.generation')):
        return 'rendition'
    if field.startswith(('validation', 'external', 'visual', 'authoring.references', 'authoring.upscale')):
        return 'prepare'
    return 'current'


def projection(choices: dict, task: dict, unresolved: list[dict]) -> dict:
    """Separate current work from final-input omissions, preserving every defect."""
    selected = stage(choices, task)
    current, pending = [], []
    for row in unresolved:
        owner = _diagnostic_stage(row)
        # A selected model must be usable while considering model-dependent
        # depiction. Preparation still checks every original final-input defect.
        relevant = (selected == 'prepare' or owner in {'definition', 'current', selected}
                    or selected == 'depiction' and owner == 'rendition' and str(row.get('field', '')).startswith('target')
                    and choices.get('target') is not None)
        (current if relevant else pending).append(row)
    return {'stage': selected, 'purpose': STAGE_MEANINGS[selected],
            'structural_ready': not current, 'final_inputs_ready': selected == 'prepare' and not unresolved,
            'unresolved': current, 'pending': pending,
            'meaning': 'Structural readiness does not establish artistic completion, source authority or final publishability.'}


def select(root: Path, path: str, selected: str) -> None:
    if selected not in STAGES:
        raise ValueError('unknown authoring stage: ' + str(selected))
    import production_store as store
    with store.transaction(root):
        file = c.local(root, path)
        choices = c.load(file)
        if choices.get('authoring_stage') == selected:
            return
        choices['authoring_stage'] = selected
        # Keep all previous actual source files and issuance history. The new
        # current scope makes no claim of retained knowledge or current reading.
        choices['reading'] = {'reading_key': None}
        c.atomic(file, c.encoded(choices), replace=True)
