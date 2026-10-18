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
    path = task.get('semantic_edit')
    if path is None:
        return None
    if inputs is None:
        inputs = image_input.task_binding(root, task, add)
    if inputs is None:
        raise ValueError('semantic editing requires its shared image_input plan')
    result = validate(c.decode(add(root, path)), inputs)
    source = next(row for row in inputs['references'] if row['id'] == result['source'])
    if not any(row['path'] == source['file'] and row['role'] == 'accepted-source'
               and row['disposition'] == 'applied' for row in task['sources']):
        raise ValueError('semantic edit source must be the applied accepted-source in the task')
    criteria = {row['id'] for row in task['criteria']}
    if not set(result['review_criteria']) <= criteria:
        raise ValueError('semantic edit names an undeclared production review criterion')
    return result


def request_context(binding: dict) -> dict:
    validate_binding(binding)
    return {'binding_sha256': binding['binding_sha256'], 'image_input_sha256': binding['image_input_sha256'],
            'source': binding['source'], 'edit': copy.deepcopy(binding['edit'])}


def main() -> int:
    from production_binding import report_failure, new_output, write_new
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan', type=Path)
    parser.add_argument('--image-input', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    try:
        source = args.plan if args.plan.is_absolute() else c.local(args.root, str(args.plan))
        inputs = args.image_input if args.image_input.is_absolute() else c.local(args.root, str(args.image_input))
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
