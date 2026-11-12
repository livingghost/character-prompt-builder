"""Locate editable choices and their owning contracts without compiling a request.

This view supplies structure and navigation, not a validation result, permission
or inferred author decision. Schema and document owners supply all constraints.
"""
from __future__ import annotations

import copy
from pathlib import Path

import execution_contract as c
from cli_invocation import python_argv, shown

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = 'schemas/authoring/production-input-draft.schema.json'
DOCUMENT = 'references/runtime/production-authoring.md#discover-input-structures'
EXAMPLE = 'examples/input-authoring/README.md'

# These describe responsibilities. Allowed keys and required fields come from
# the schemas or the document's logical owner, never this navigation map.
OWNERS = {
    'target': ('Select the actual model, service and supported native controls once.',
               'references/runtime/production-authoring.md'),
    'reading': ('Select the key issued after the applicable source material was delivered.',
                'references/runtime/production-authoring.md#select-and-read-the-current-knowledge'),
    'visual': ('Select explicit visual continuity evidence when the work requires it.',
               'references/runtime/generation-package.md#generation-package'),
    'validation': ('Select request evidence and policy; compilation derives target bindings and hashes.',
                   'references/runtime/model-evidence.md'),
    'task_changes': ('Record intentional changes to the selected task; unmentioned choices remain.',
                     'references/runtime/production-variation.md'),
    'external': ('Own the native external request, reference transports and their actual evidence.',
                 'references/runtime/production-external-inputs.md'),
    'authoring': ('Keep editable task decisions, delivery and selected document files together.', DOCUMENT),
    'authoring.task': ('Own direction, independent criteria, sources and applicable task choices.',
                       'references/runtime/production-direction.md'),
    'authoring.delivery': ('Edit the exact prompt or authored deliverable at its selected source.', DOCUMENT),
    'authoring.documents': ('Select each specialist document at its single editable file.', DOCUMENT),
    'authoring.generation': ('Own generation choices not derived from the target or specialist files.',
                             'references/runtime/production-authoring.md'),
    'authoring.references': ('Select source images, their subject scope, influence and exclusions.',
                             'references/runtime/reference-delivery.md'),
    'authoring.upscale': ('Select the source image and actual enlargement choices when applicable.',
                          'references/runtime/production-authoring.md'),
    'authoring.sources': ('Own selected source text without rewriting the original source file.', DOCUMENT),
    'authoring.source_files': ('Retain source provenance; the builder captures actual file bytes.', DOCUMENT),
}


def action(root: Path, choices_path: str, *, field: str | None = None) -> dict:
    argv = python_argv(ROOT / 'scripts/production_workflow.py', 'explain-inputs',
                       '--root', str(root), '--choices', choices_path)
    if field is not None:
        argv.extend(('--field', field))
    return {'operation': 'explain-inputs', 'argv': argv, 'shown': shown(argv),
            'external_effect': False}


def summary(root: Path, choices_path: str, choices: dict) -> dict:
    """Small draft-time entry point; detailed requirements are an explicit read."""
    import production_document_contracts as contracts
    documents = (choices.get('authoring') or {}).get('documents') or {}
    selected = {}
    for name, selector in documents.items():
        if name not in contracts.DOCUMENT_KEYS:
            continue
        owner = contracts.guidance(name)
        selected[name] = {'source': copy.deepcopy(selector), **owner,
            'explain_action': action(root, choices_path, field='authoring.documents.' + name)}
    return {'document_path': DOCUMENT, 'schema': SCHEMA, 'example': EXAMPLE,
            'explain_action': action(root, choices_path),
            'documents': selected,
            'meaning': 'Structure and source navigation only. Complete the actual author decisions; '
                       'check or prepare validates the selected content and its context.'}


def _variants(schema: dict) -> list[dict]:
    return [schema, *schema.get('oneOf', []), *schema.get('anyOf', [])]


def _shape(schema: dict) -> dict:
    """Expose actual declarations, including alternatives, without inventing requirements."""
    keys = ('type', 'const', 'enum', 'description', 'required', 'additionalProperties',
            'minLength', 'minimum', 'maximum', 'minItems', '$ref')
    result = {key: copy.deepcopy(schema[key]) for key in keys if key in schema}
    if 'properties' in schema:
        result['permitted_keys'] = sorted(schema['properties'])
    for kind in ('oneOf', 'anyOf', 'allOf'):
        if kind in schema:
            result[kind] = [_shape(item) for item in schema[kind]]
    return result


def _schema_field(schema: dict, parts: list[str]) -> dict:
    selected = schema
    for part in parts:
        found = [variant['properties'][part] for variant in _variants(selected)
                 if part in variant.get('properties', {})]
        if not found:
            return {}
        selected = found[0] if len(found) == 1 else {'anyOf': found}
    return selected


def _value(choices: dict, parts: list[str]):
    value = choices
    for part in parts:
        if not isinstance(value, dict) or part not in value:
            return False, None
        value = value[part]
    return True, value


def explain(root: Path, choices_path: str, *, field: str | None = None) -> dict:
    """Describe current files and fields; do not publish or acquire a catalog/run."""
    import production_document_contracts as contracts
    root = c._root(root)
    choices = c.load(c.local(root, choices_path))
    if not isinstance(choices, dict):
        raise ValueError('choices must be an object; schema: ' + SCHEMA)
    schema = c.load(ROOT / SCHEMA)
    result = {'state': 'input-guide', 'choices_file': choices_path,
              'schema': SCHEMA, 'document_path': DOCUMENT, 'example': EXAMPLE,
              'validated': False, 'external_effect': False,
              'completion': 'The schema permits unfinished drafts. Current target, selected documents, '
                            'source meaning and actual authority still need their owning checks.'}
    prefix = 'authoring.documents.'
    if field and field.startswith(prefix):
        name = field[len(prefix):]
        if name not in contracts.DOCUMENT_KEYS:
            raise ValueError('unknown authoring document; permitted keys: ' + ', '.join(sorted(contracts.DOCUMENT_KEYS)))
        present, selected = _value(choices, ['authoring', 'documents', name])
        contract = contracts.metadata(name)
        # Deep schema traversal is an explicit registry explain/pointer read.
        # This source-location view does not repeat an entire schema closure.
        result.update(field=field, selected=present, source=selected if present else None,
                      contract={key: value for key, value in contract.items() if key != 'structure'})
        return result
    if field and field not in OWNERS:
        raise ValueError('select one input field: ' + ', '.join(OWNERS) +
                         ', or authoring.documents.<document-name>')
    selected_fields = [field] if field else list(OWNERS)
    fields = []
    for name in selected_fields:
        parts = name.split('.')
        actual = _schema_field(schema, parts)
        parent = _schema_field(schema, parts[:-1]) if len(parts) > 1 else schema
        present, value = _value(choices, parts)
        purpose, document = OWNERS[name]
        row = {'field': name, 'purpose': purpose, 'document_path': document,
               'schema_pointer': '/properties/' + '/properties/'.join(parts),
               'required_in_draft': parts[-1] in parent.get('required', []),
               'present': present, 'value_state': 'absent' if not present else 'null' if value is None else 'supplied',
               'declaration': _shape(actual)}
        if isinstance(value, dict) and 'file' in value:
            row['source'] = {key: copy.deepcopy(value[key]) for key in ('file', 'field') if key in value}
        if name == 'authoring.task':
            row['content_schema'] = 'schemas/authoring/production-task.schema.json'
            row['schema_scope'] = ('This is the compiled task contract. The draft owns authored task fields; '
                'delivery, generation, route_reading, image_input and authored_basis are derived by their builders.')
            row['child_contracts'] = {
                'direction': {'explain_command': 'python scripts/production_document_contracts.py explain production_direction',
                              **contracts.guidance('production_direction')},
                'authority': {'source': value.get('authority') if isinstance(value, dict) else None,
                              'explain_command': 'python scripts/production_document_contracts.py explain authority',
                              **contracts.guidance('authority')},
                **{key: {'schema': row['content_schema'], 'pointer': '/properties/' + key}
                   for key in ('sources', 'criteria', 'recording', 'world_views')},
            }
        if name == 'authoring.documents':
            row['available_documents'] = sorted(contracts.DOCUMENT_KEYS)
            row['selected_documents'] = copy.deepcopy(value) if isinstance(value, dict) else {}
            row['document_help'] = 'Select --field authoring.documents.NAME for its complete contract and current file.'
        fields.append(row)
    result['fields'] = fields
    return result
