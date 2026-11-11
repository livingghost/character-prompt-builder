#!/usr/bin/env python3
"""Bind an edit's existing scene, requested change and explicit preservation.

python scripts/semantic_edit_plan.py PLAN.json --image-input INPUT.json --root STUDIO --out BINDING.json
Production tasks name the two plans as semantic_edit and image_input. Ordinary
reference generation uses image_input alone; it does not invent an edit source.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

import execution_contract as c
import image_input

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / 'schemas/authoring/semantic-edit-plan.schema.json'
DERIVED = {'plan_sha256', 'binding_sha256', 'image_input_sha256', 'status'}


def _structure(plan: Any) -> None:
    from state_protocol import validate_against_schema
    errors = validate_against_schema(plan, c.load(SCHEMA))
    if errors:
        raise ValueError('semantic edit plan: ' + '; '.join(errors))


def require_input(binding: dict, inputs: dict) -> None:
    """The source is an actual scene in the single shared reference owner."""
    image_input.validate_binding(inputs)
    if binding['image_input_sha256'] != inputs['binding_sha256']:
        raise ValueError('semantic edit image input differs from its prepared binding')
    selected = next((row for row in inputs['references'] if row['id'] == binding['source']), None)
    if selected is None or selected['role'] != 'scene':
        raise ValueError('source must name a reference with the scene role')
    missing = set(binding['edit']['required_reference_roles']) - {row['role'] for row in inputs['references']}
    if missing:
        raise ValueError('missing required reference roles: ' + ', '.join(sorted(missing)))


def validate(plan: dict, inputs: dict) -> dict:
    _structure(plan)
    image_input.validate_binding(inputs)
    result = copy.deepcopy(plan)
    result.update(artifact_type='semantic-edit-binding', plan_sha256=c.content_id(plan),
                  image_input_sha256=inputs['binding_sha256'], status='prepared-not-generated')
    result['binding_sha256'] = c.content_id(result)
    validate_binding(result)
    require_input(result, inputs)
    return result


def validate_binding(binding: Any) -> None:
    if not isinstance(binding, dict) or binding.get('artifact_type') != 'semantic-edit-binding':
        raise ValueError('semantic edit binding required')
    c.sha(binding.get('binding_sha256'))
    if c.content_id({key: value for key, value in binding.items() if key != 'binding_sha256'}) != binding['binding_sha256']:
        raise ValueError('semantic edit binding integrity mismatch')
    c.sha(binding.get('plan_sha256'))
    c.sha(binding.get('image_input_sha256'))
    if binding.get('status') != 'prepared-not-generated':
        raise ValueError('a semantic edit binding records preparation, not generation success')
    plan = {key: copy.deepcopy(value) for key, value in binding.items() if key not in DERIVED}
    plan['artifact_type'] = 'semantic-edit-plan'
    _structure(plan)


def task_binding(root: Path, task: dict, add, *, inputs: dict | None = None) -> dict | None:
    """Bind the task's edit plan to its image input, accepted source and criteria.

    The scene reference identifies the edited image by its bytes. A prepared
    reference set delivers the scene from a derived carrier path, so the task's
    applied accepted-source is matched by the SHA-256 of its file, not its path.
    """
    from production_diagnostics import ProductionError
    path = task.get('semantic_edit')
    if path is None:
        return None
    if inputs is None:
        inputs = image_input.task_binding(root, task, add)
    if inputs is None:
        raise ProductionError('INPUT_CONSISTENCY_ERROR', 'The task names a semantic edit plan and no image input.',
            phase='semantic-edit', file=path, pointer='$.image_input',
            required_action='Select the edited image as a scene reference of the task\'s image input: '
                'authoring.references (dispatcher) or external.image_input (external) in editable choices, '
                'or task.image_input in a complete task.')
    result = validate(c.decode(add(root, path)), inputs)
    source = next(row for row in inputs['references'] if row['id'] == result['source'])
    accepted = [row for row in task['sources']
                if row['role'] == 'accepted-source' and row['disposition'] == 'applied']
    if not any(c.digest(add(root, row['path'])) == source['sha256'] for row in accepted):
        raise ProductionError('INPUT_CONSISTENCY_ERROR',
            'The scene reference "' + result['source'] + '" that the semantic edit plan names delivers bytes '
            '(sha256 ' + source['sha256'] + ') that no applied accepted-source of the task holds.',
            phase='semantic-edit', file=path, pointer='$.source', reference=result['source'],
            reference_sha256=source['sha256'], accepted_sources=[row['path'] for row in accepted],
            required_action='Declare the image being edited as an applied accepted-source in the task sources '
                '(authoring.task.sources in editable choices) at the file whose bytes the scene reference "' +
                result['source'] + '" delivers, or set source in ' + path + ' to the scene reference that '
                'delivers the accepted-source image.')
    criteria = {row['id'] for row in task['criteria']}
    undeclared = [name for name in result['review_criteria'] if name not in criteria]
    if undeclared:
        raise ProductionError('INPUT_CONSISTENCY_ERROR',
            'The semantic edit plan names review criteria that the task does not declare: ' +
            ', '.join(undeclared) + '.', phase='semantic-edit', file=path, pointer='$.review_criteria',
            criteria=undeclared,
            required_action='Add each listed criterion to the task criteria (authoring.task.criteria in editable '
                'choices) as an independent requirement of the edit, or remove its ID from review_criteria in ' +
                path + '.')
    return result


PLAN_GUIDE = {'document_path': 'references/runtime/semantic-instruction-edit.md#resolve-the-intended-change'}
# Each authored part of an edit plan: what its absence leaves open and the value to write there.
PLAN_FIELDS = {
    'edit.target': ('so the edit names no part of the source image to change.',
                    'Write at edit.target in {path} the depicted part of the source image that the commission '
                    'changes, such as the region, object or property it names.'),
    'edit.change': ('so the edit states no change.',
                    'Write at edit.change in {path} the change that edit.target receives, as the commission '
                    'states it.'),
    'edit.preserve': ('so the edit states nothing that must stay as the source image shows it.',
                      'Write at edit.preserve in {path} the array of properties of the source image that must stay '
                      'unchanged; an empty array states that the edit fixes none.'),
}


def unresolved(plan: Any, *, path: str, criteria: list) -> list[dict]:
    """Name each unanswered authored part of an editable edit plan.

    The plan file is selected at task_changes.semantic_edit, so each entry's
    field is that selector followed by the part inside the plan, and `file`
    names the plan. `validate` owns the complete contract when it is prepared.
    """
    from production_diagnostics import choice_required
    if not isinstance(plan, dict):
        return []
    edit = plan.get('edit') if isinstance(plan.get('edit'), dict) else {}
    result = []

    def missing(part, message, required_action):
        field = 'task_changes.semantic_edit.' + part
        result.append(choice_required(field, 'authored-choice-required', part + ' in ' + path + ', the edit plan '
            'that task_changes.semantic_edit selects, ' + message, required_action, PLAN_GUIDE, file=path))
    for part, (consequence, required_action) in PLAN_FIELDS.items():
        if edit.get(part.split('.', 1)[1]) is None:
            missing(part, 'is null, ' + consequence, required_action.format(path=path))
    declared = {row.get('id') for row in criteria if isinstance(row, dict)}
    review = plan.get('review_criteria')
    if not review:
        missing('review_criteria', 'is empty, so no criterion reviews the edit.',
                'Add to authoring.task.criteria an independent criterion for the requested change and one for each '
                'preserved property whose result matters, then list their IDs at review_criteria in ' + path + '.')
    elif isinstance(review, list):
        undeclared = [name for name in review if name not in declared]
        if undeclared:
            missing('review_criteria', 'names criteria that authoring.task.criteria does not declare: ' +
                    ', '.join(map(str, undeclared)) + '.',
                    'Add each listed criterion to authoring.task.criteria, or remove its ID from review_criteria in ' +
                    path + '.')
    return result


def request_context(binding: dict) -> dict:
    validate_binding(binding)
    return {'binding_sha256': binding['binding_sha256'], 'image_input_sha256': binding['image_input_sha256'],
            'source': binding['source'], 'edit': copy.deepcopy(binding['edit'])}


def main() -> int:
    from production_binding import report_failure, new_output, studio_file, write_new
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan', help='Edit plan: an absolute path, or a /-separated path below --root.')
    parser.add_argument('--image-input', required=True,
                        help='Image input plan: an absolute path, or a /-separated path below --root.')
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--out', required=True, help='New binding file: an absolute path, or a /-separated path below --root.')
    args = parser.parse_args()
    try:
        source = studio_file(args.root, args.plan, option='plan')
        inputs = studio_file(args.root, args.image_input, option='--image-input')
        output = new_output(args.root, args.out, option='--out')
        result = validate(c.load(source), image_input.validate(c.load(inputs), args.root))
        write_new(output, c.encoded(result), option='--out', value=str(args.out))
        print(json.dumps({'ok': True, 'binding': str(output), 'binding_sha256': result['binding_sha256'],
                          'status': result['status']}))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        return report_failure(exc, phase='semantic-edit')


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
