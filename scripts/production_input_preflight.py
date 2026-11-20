"""Locate missing current input structure before authoring derives any files.

The schema owns required fields. This preflight reports missing structure and
container types; ordinary compilation still evaluates content and context.
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import execution_contract as c
from cli_invocation import python_argv, shown
from owned_json import mutable
from production_diagnostics import ProductionError, choice_required

ROOT = Path(__file__).resolve().parents[1]
TASK_SCHEMA = 'schemas/authoring/production-task.schema.json'
CHOICES_SCHEMA = 'schemas/authoring/production-input-draft.schema.json'
GUIDE = 'references/runtime/production-authoring.md#discover-input-structures'


def _part(value: str) -> str:
    return value.replace('~', '~0').replace('/', '~1')


def generation_scope(choices: dict, *, task: dict | None = None) -> dict:
    """Read generation field limits from the selected task's existing schema."""
    from state_protocol import schema_documents
    selected = dict(task if task is not None else (choices.get('authoring') or {}).get('task') or {})
    if task is None:
        selected.update(choices.get('task_changes') or {})
    if choices.get('external') is not None and selected.get('execution') != 'dispatcher':
        selected.update(execution='external', artifact='image')
    owner = schema_documents()
    schema = owner.read(ROOT / TASK_SCHEMA)
    allowed = set(schema['properties']['generation']['properties'])
    pointers = ['/properties/generation']
    for index, branch in enumerate(schema.get('allOf', [])):
        condition = branch.get('if')
        if not selected.get('execution') or condition is None or owner.validate(selected, condition, root_schema=schema):
            continue
        generation = (branch.get('then', {}).get('properties') or {}).get('generation', {})
        if generation.get('additionalProperties') is False:
            allowed.intersection_update(generation.get('properties', {}))
            pointers.append('/allOf/' + str(index) + '/then/properties/generation')
    return {'route': selected.get('route'), 'execution': selected.get('execution'),
            'execution_selected': bool(selected.get('execution')),
            'schema': TASK_SCHEMA, 'schema_pointers': pointers,
            'permitted_generation_fields': sorted(allowed)}


def generation_fields(root: Path, choices: dict, task: dict, *, choices_path: str | None = None) -> list[dict]:
    """Locate authored inline fields forbidden by the selected execution branch."""
    authored = (choices.get('authoring') or {}).get('generation')
    if not isinstance(authored, dict):
        return []
    scope = generation_scope(choices, task=task)
    if not scope['execution_selected']:
        return []
    from production_input_guide import action
    next_action = action(root, choices_path, field='authoring.generation') if choices_path else None
    result = []
    for name in sorted(set(authored) - set(scope['permitted_generation_fields'])):
        # The existing authoring builder omits this unanswered declaration.
        if name == 'render_intent' and authored[name] is None:
            continue
        pointer = '/authoring/generation/' + _part(name)
        result.append({'field': 'authoring.generation.' + name,
            'code': 'INPUT_SCHEMA_INVALID', 'cause': 'generation-field-not-permitted',
            'phase': 'authoring', 'file': choices_path, 'pointer': pointer,
            'message': 'authoring.generation.' + name + ' is not permitted by the selected ' +
                       scope['execution'] + ' generation contract.',
            'repair_owner': {'file': choices_path, 'pointer': pointer},
            'expected': {'execution': scope['execution'], 'permitted_keys': scope['permitted_generation_fields']},
            'actual': {'field': name},
            'required_action': 'Correct the inline declaration at ' + pointer +
                ' in ' + (choices_path or 'the selected choices') + '. Retain its authored content at its existing '
                'source owner. Use the generation guide for the permitted inline fields and the separate owners '
                'of derived fields' + (': ' + next_action['shown'] if next_action else '') + '.',
            'guidance': {'document_path': GUIDE, 'schema': TASK_SCHEMA,
                         'schema_pointers': scope['schema_pointers']},
            **({'next_action': next_action} if next_action else {})})
    return result


def _structure(value, schema, owner, *, pointer='', document=None):
    """Walk declared object/array requirements without rejecting open decisions."""
    document = schema if document is None else document
    if '$ref' in schema:
        selected, selected_document = owner.resolve_ref(schema['$ref'], document)
        yield from _structure(value, selected, owner, pointer=pointer, document=selected_document)
    declared = schema.get('type')
    types = [declared] if isinstance(declared, str) else declared or []
    if ('object' in types or 'array' in types) and not (
            isinstance(value, Mapping) and 'object' in types or
            isinstance(value, list) and 'array' in types or value is None and 'null' in types):
        yield {'pointer': pointer, 'cause': 'container-type', 'expected': mutable(schema),
               'actual': {'type': type(value).__name__}}
        return
    if isinstance(value, Mapping):
        properties = schema.get('properties', {})
        for name in schema.get('required', []):
            if name not in value:
                yield {'pointer': pointer + '/' + _part(name), 'cause': 'missing-required-field',
                       'expected': mutable(properties.get(name, {})), 'actual': {'present': False}}
        for name, child in properties.items():
            if name in value:
                yield from _structure(value[name], child, owner,
                    pointer=pointer + '/' + _part(name), document=document)
    elif isinstance(value, list) and isinstance(schema.get('items'), Mapping):
        for index, item in enumerate(value):
            yield from _structure(item, schema['items'], owner,
                pointer=pointer + '/' + str(index), document=document)
    for branch in schema.get('allOf', []):
        yield from _structure(value, branch, owner, pointer=pointer, document=document)
    if 'if' in schema:
        branch = 'else' if owner.validate(value, schema['if'], root_schema=document) else 'then'
        if branch in schema:
            yield from _structure(value, schema[branch], owner, pointer=pointer, document=document)
    for kind in ('anyOf', 'oneOf'):
        candidates = []
        for branch in schema.get(kind, []):
            types = branch.get('type')
            types = [types] if isinstance(types, str) else types or []
            if (isinstance(value, Mapping) and 'object' in types or
                    isinstance(value, list) and 'array' in types or value is None and 'null' in types):
                candidates.append(branch)
        if len(candidates) == 1:
            yield from _structure(value, candidates[0], owner, pointer=pointer, document=document)


def _rebuild_action(root: Path, task: dict) -> dict:
    folder = Path('work/rebuilt-inputs')
    index = 1
    while (root / folder).exists():
        folder = Path('work/rebuilt-inputs-' + str(index))
        index += 1
    argv = python_argv(ROOT / 'scripts/production_workflow.py', 'draft-inputs',
        '--root', str(root), '--operation', 'compose', '--route', task.get('route') or 'prompt-only',
        '--artifact', task.get('artifact') or 'text', '--execution', task.get('execution') or 'authored',
        '--out-dir', folder.as_posix())
    for feature in task.get('features', []) if isinstance(task.get('features'), list) else []:
        argv.extend(('--feature', str(feature)))
    return {'operation': 'draft-inputs', 'argv': argv, 'shown': shown(argv),
            'external_effect': False, 'purpose': 'Create an editable current-format scaffold; then carry over applicable authored content.'}


def _open_work_before(root: Path, action: dict) -> dict:
    """Expose the actual prerequisite instead of offering a draft that cannot open."""
    from production_authoring_state import active_task_id
    if active_task_id(root) is not None:
        return action
    argv = python_argv(ROOT / 'scripts/work_ledger.py', 'begin', '--studio', str(root),
        '--goal', 'Rebuild the selected authored input in the current format.',
        '--step', 'Carry applicable authored content into a new editable input and inspect it.')
    return {'operation': 'begin-work', 'argv': argv, 'shown': shown(argv),
            'external_effect': False, 'purpose': 'Open work for the new draft; this grants no execution authority.',
            'next_action': action}


def require_shape(value, *, schema_path: str, file: str | None, root: Path,
                  operation: str, source_run: str | None = None) -> None:
    from state_protocol import schema_documents
    owner = schema_documents()
    schema = owner.read(ROOT / schema_path)
    issues = list(_structure(value, schema, owner))
    task = value if schema_path == TASK_SCHEMA else (value.get('authoring', {}).get('task', {})
        if isinstance(value, dict) and isinstance(value.get('authoring'), dict) else {})
    # Draft task fields omit compiler-owned fields, but selected direction keeps
    # the same shape as its public owner, including explicitly unanswered values.
    if schema_path == CHOICES_SCHEMA and isinstance(task, dict) and 'direction' in task:
        direction = owner.read(ROOT / 'schemas/authoring/production-direction.schema.json')
        issues.extend(_structure(task['direction'], direction, owner, pointer='/authoring/task/direction'))
    if not issues:
        return
    unique = {row['pointer']: row for row in issues}
    first = next(iter(unique.values()))
    scaffold = _rebuild_action(root, task if isinstance(task, dict) else {})
    action = _open_work_before(root, scaffold)
    prerequisite = ('First open a work task with ' + action['shown'] + '. ' if action is not scaffold else '')
    repair = (prerequisite + 'Create new editable input with ' + scaffold['shown'] + '. Retain the selected run unchanged; '
              'copy applicable authored content and select current evidence in the new draft.' if source_run else
              'Correct ' + (file or 'the selected input') + ' at the reported JSON Pointer using the expected '
              'schema. ' + prerequisite + 'To obtain a current editable scaffold, run ' + scaffold['shown'] + '.')
    raise ProductionError('INPUT_CONSISTENCY_ERROR',
        'The selected input lacks the current structure required by ' + operation + ': ' +
        ', '.join(unique) + '.', phase='authoring', file=file, pointer=first['pointer'],
        cause=first['cause'], expected=first['expected'], actual=first['actual'],
        current_operation=operation, selected_input={'file': file, 'run': source_run},
        repair_owner={'kind': 'new-draft' if source_run else 'authored-file',
                      'file': None if source_run else file},
        missing_structure=list(unique.values()), repair_action=action,
        preservation={'authored_content': ['request', 'source selections', 'direction', 'prompt', 'criteria'],
                      'reassess': ['current source evidence', 'authority', 'exact request bindings'],
                      'historical_run': 'retained unchanged'},
        required_action=repair, guidance={'document_path': GUIDE, 'schema': schema_path})


def source_roles(root: Path, task: dict, *, choices_path: str | None = None,
                 resolved_route: dict | None = None, task_path: str | None = None,
                 source_run: str | None = None) -> dict:
    import execution_routes
    route = resolved_route or execution_routes.resolve(task['route'], task.get('features', []),
        execution=task['execution'], operation='author' if task['execution'] == 'authored' else 'prepare')
    required = route['source_roles']
    applied = sorted({row.get('role') for row in task.get('sources', [])
                      if isinstance(row, dict) and row.get('disposition') == 'applied' and row.get('role')})
    missing = sorted(set(required) - set(applied))
    examples = []
    for role in missing:
        row_path = (Path(choices_path).parent / (role + '-source.json')).as_posix() if choices_path else (
            'work/draft/' + role + '-source.json')
        argv = python_argv(ROOT / 'scripts/production_workflow.py', 'acquire-source', '--root', str(root),
            '--choices', choices_path or 'work/draft/choices.json', '--source-row', row_path)
        entry = {'role': role, 'source_row_file': row_path,
            'source_row_example': {'id': role, 'path': 'inputs/' + role + '.json', 'role': role,
                'disposition': 'applied', 'locator': 'The selected authored source section.',
                'reason': 'State why this source applies to the current request.'},
            'repair_owner': {'kind': 'production-source-row', 'file': row_path},
            'repair_action': {'operation': 'acquire-source', 'argv': argv, 'shown': shown(argv), 'external_effect': False}}
        if choices_path:
            entry['required_action'] = ('Write the complete source row to ' + row_path +
                ', selecting its actual file, locator and reason, then run ' + shown(argv) +
                '. The builder derives task.sources.')
        else:
            # A standalone task owns its public sources. A retained run must
            # first become a new registered draft; neither owns imaginary choices.
            entry['source_row_file'] = None
            if task_path and source_run is None:
                argv = python_argv(ROOT / 'scripts/production_workflow.py', 'inspect-inputs',
                    '--root', str(root), '--task', task_path)
                entry['repair_owner'] = {'kind': 'production-task', 'file': task_path, 'pointer': '/sources'}
                entry['repair_action'] = {'operation': 'inspect-inputs', 'argv': argv, 'shown': shown(argv),
                    'requires_author_input': True, 'external_effect': False}
                entry['required_action'] = ('Add the complete applied source row to ' + task_path +
                    ' at /sources, selecting its actual file, locator and reason; then run ' + shown(argv) + '.')
            else:
                action = _rebuild_action(root, task)
                if source_run:
                    destination = action['argv'][action['argv'].index('--out-dir') + 1]
                    argv = python_argv(ROOT / 'scripts/production_workflow.py', 'draft-inputs',
                        '--root', str(root), '--from-run', source_run, '--operation', 'amend',
                        '--out-dir', destination)
                    from production_authoring_state import active_task_id
                    if active_task_id(root) is None:
                        argv.extend(('--new-task', 'Reassess the retained source selection.'))
                    action.update(argv=argv, shown=shown(argv))
                else:
                    action = _open_work_before(root, action)
                entry['repair_owner'] = {'kind': 'new-draft', 'file': None}
                entry['repair_action'] = action
                entry['required_action'] = ('Create editable inputs with ' + action['shown'] +
                    ', then follow that draft\'s acquire-source action. Retain the selected run unchanged.')
        examples.append(entry)
    return {'required': required, 'applied': applied, 'missing': missing, 'source_rows': examples}


def missing_source_roles(root: Path, task: dict, *, choices_path: str | None = None,
                         task_path: str | None = None, source_run: str | None = None) -> list[dict]:
    report = source_roles(root, task, choices_path=choices_path, task_path=task_path, source_run=source_run)
    return [choice_required('authoring.task.sources', 'source-selection-required',
        'The selected route requires an applied source with role ' + entry['role'] + '.',
        entry['required_action'],
        {'document_path': GUIDE, 'schema': TASK_SCHEMA}, cause='missing-applied-source-role',
        **{key: value for key, value in entry.items() if key != 'required_action'})
        for entry in report['source_rows']]
