#!/usr/bin/env python3
"""Discover authored document contracts and run their owning local validators.

The registry locates existing contracts. It does not define a second schema or
certify target compatibility, source authority, or the readiness of a task.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import operation_context

ROOT = Path(__file__).resolve().parents[1]
_PILOT = 'examples/state-aware-pilot/generated/'
_CHECK = 'python scripts/production_workflow.py check --root STUDIO --choices CHOICES'


def _contract(document: str, owner: str, *, schema: str | None = None,
              example: str | None = None, representation: str = 'json',
              scope: str = 'document', remaining: str | None = None,
              derived: Sequence[str] = ()) -> dict:
    return {'document_path': document, 'schema': schema, 'validator_source': owner,
            'representation': representation, 'validation_scope': scope,
            'example_paths': [example] if example else [],
            'derived_fields': list(derived), 'remaining_checks': remaining}


_CONTRACTS = {
    'parameters': _contract(
        'references/runtime/render-contract.md#declare-controls-by-operation',
        'scripts/render_contract_lib.py:_parameters_from_profile', scope='task-context',
        remaining='The selected model, offering, execution mode and evidence determine permitted controls.'),
    'production_spec': _contract(
        'references/production-specification.md#ownership-boundary',
        'scripts/production_spec.py:validate_authored',
        schema='protocols/shared-state/schemas/production-spec.schema.json',
        example=_PILOT + 'production-specification.json', scope='authored-document',
        derived=('$.target_model',),
        remaining='choices.target owns the model; compilation checks selected-target consistency and derives '
                  'target_model in the published specification. It also binds source files, continuity and prompt expression.'),
    'plot': _contract(
        'references/runtime/prompt-composition.md#scene-specification',
        'scripts/prompt_plot.py:validate_authored_prompt_plot',
        schema='schemas/prompt-plot.schema.json', example=_PILOT + 'prompt-plot.json',
        derived=('$.approved.content_sha256',),
        remaining='Preparation checks actual approval and whether a prior approval still covers the edited content.'),
    'retrieval_record': _contract(
        'references/runtime/prompt-composition.md#catalog-retrieval-and-inspection',
        'scripts/prompt_retrieval.py:validate_prompt_retrieval_record',
        schema='schemas/prompt-retrieval-record.schema.json', example=_PILOT + 'prompt-retrieval-record.json',
        derived=('$.settled', '$.context'),
        remaining='Compilation binds the current prompt, plot, model, syntax and dictionary investigations.'),
    'creative_intent': _contract(
        'references/runtime/prompt-composition.md#revision-contract',
        'scripts/revision_contract.py:require_intent_revision', example=_PILOT + 'creative-intent.json',
        remaining='The object preserves authored detail; its revision_contract, when selected, has semantic-diff checks.'),
    'negative': _contract(
        'references/runtime/prompt-composition.md#negative-output',
        'scripts/build_generation_payload.py:prepare_text_transports', representation='text',
        example=_PILOT + 'negative.txt', remaining='The target and selected transport determine whether and where this text is delivered.'),
    'integrated_prompt': _contract(
        'references/runtime/image-generation.md#model-and-negative-transport',
        'scripts/build_generation_payload.py:prepare_text_transports', representation='text',
        example=_PILOT + 'integrated-prompt.txt',
        remaining='The target and selected transport determine whether this complete rendition is delivered.'),
    'native_negative': _contract(
        'references/runtime/image-generation.md#model-and-negative-transport',
        'scripts/build_generation_payload.py:prepare_text_transports', representation='text',
        remaining='The target and selected transport determine the supported native negative rendition.'),
    'negative_provenance': _contract(
        'references/runtime/prompt-composition.md#negative-output',
        'scripts/build_generation_payload.py:normalize_negative_provenance',
        example=_PILOT + 'negative-provenance.json',
        remaining='The author selects applicable exclusions; this check validates the record shape only.'),
    'state_lineage': _contract(
        'references/runtime/state-aware-series.md#authority-graph',
        'scripts/state_protocol.py:validate_artifact',
        schema='protocols/shared-state/schemas/state-lineage.schema.json', example=_PILOT + 'state-lineage.json',
        remaining='Compilation checks the lineage against the selected specification and complete state graph.'),
    'state_snapshot': _contract(
        'references/runtime/state-aware-series.md#authority-graph',
        'scripts/state_protocol.py:validate_artifact',
        schema='protocols/shared-state/schemas/state-snapshot.schema.json', example=_PILOT + 'state-snapshot-C01.json',
        remaining='Compilation checks this snapshot against the selected lineage and subject graph.'),
    'state_graphs': _contract(
        'references/runtime/state-aware-series.md#authority-graph',
        'scripts/state_protocol.py:validate_subject_state_graphs', example=_PILOT + 'state-graphs.json',
        scope='task-context', remaining='Concrete subject graphs require their Production Specification, reference selection and lineage.'),
    'visual_continuity': _contract(
        'references/runtime/generation-package.md#generation-package',
        'scripts/visual_continuity.py:build_record', schema='schemas/visual-continuity.schema.json',
        example=_PILOT + 'visual-continuity.json', scope='task-context',
        derived=('$.basis.sha256', '$.subjects.*.identity_refs[*].source_sha256',
                 '$.subjects.*.identity_refs[*].reference_number'),
        remaining='Editable choices omit derived hashes and positions. The published schema describes the compiled record; '
                  'validation needs the current Studio, specification and prepared references.'),
    'mask_binding': _contract(
        'references/runtime/scene-mask-planning.md#use-the-existing-production-pipeline',
        'scripts/scene_mask_planner.py:validate_binding', scope='studio-context',
        remaining='Validation reads the selected mask, source regions, bundle and actual review from --root.'),
    'choices': _contract(
        'references/runtime/production-authoring.md#use-the-delivered-knowledge',
        'scripts/production_inputs.py:compile_choices', schema='schemas/authoring/production-input-draft.schema.json',
        scope='task-context', remaining='The choices schema describes selectors. check --choices reads each selected current file and validates the complete task.'),
    'production_direction': _contract(
        'references/runtime/production-direction.md#record-the-production-direction',
        'scripts/production_plan.py:validate', schema='schemas/authoring/production-direction.schema.json',
        scope='task-context', remaining='Direction uses the task sources, independent criteria and actual authority.'),
    'authority': _contract(
        'references/runtime/production-permissions.md#authorization-and-execution-records',
        'scripts/production_permissions.py:validate', schema='schemas/authoring/production-authority.schema.json',
        example='templates/realization/production-authority.json',
        remaining='This validates declared grants; preparation separately acquires evidence and execution checks current scope and expiry.'),
    'execution_decisions': _contract(
        'references/runtime/production-request-execution.md#execute-the-prepared-request',
        'scripts/production_decisions.py:validate_shape', schema='schemas/authoring/production-execution-decisions.schema.json',
        example='examples/production-execution/README.md', scope='document-shape',
        remaining='This local check validates document structure only. draft-execution derives the fields for the selected '
                  'prepared run. The authorized execution boundary separately checks exact run/request bindings, '
                  'operation order, current grants and the recorded judgments; input check --choices does not validate these decisions.'),
    'render_intent': _contract(
        'references/runtime/render-contract.md#select-the-operation-and-optional-rendering-declaration',
        'scripts/render_contract_lib.py:validate_intent', schema='schemas/render-intent.schema.json',
        remaining='The standalone file is a complete render intent with text prompt_expression when rendering is declared. '
                  'The editable choices selector {"document":"delivery"} requires check --choices to resolve its text. '
                  'Compilation checks the resulting expression against the exact task delivery.'),
    'scene_plot': _contract(
        'references/narrative-protocol.md#scene-plot',
        'scripts/scene_plot.py:validate_scene_plot',
        remaining='The logical validator owns this contract; no separate JSON Schema is published. '
                  'Narrative coverage checks the linked narrative and other scenes.'),
    'execution_policy': _contract(
        'references/runtime/model-evidence.md#execution-policy-for-reference-delivery',
        'scripts/execution_policy.py:load_policy', scope='task-context',
        remaining='The selected target, text dialect and acquired evidence determine policy validity.'),
    'reference_render_contract': _contract(
        'references/runtime/model-evidence.md#execution-policy-for-reference-delivery',
        'scripts/model_rendition.py:reference_contract', scope='task-context',
        remaining='The selected target, dialect, transport and reference bindings determine mapping coverage.'),
}

DOCUMENT_KEYS = frozenset({
    'parameters', 'production_spec', 'plot', 'retrieval_record', 'creative_intent',
    'negative', 'integrated_prompt', 'native_negative', 'negative_provenance',
    'state_lineage', 'state_snapshot', 'state_graphs', 'visual_continuity', 'mask_binding',
})
CONTRACT_KEYS = frozenset(_CONTRACTS)


def _selected(name: str) -> dict:
    if name not in _CONTRACTS:
        raise ValueError('Unknown authored document ' + repr(name) + '; permitted names: ' + ', '.join(sorted(CONTRACT_KEYS)))
    return _CONTRACTS[name]


def guidance(name: str) -> dict:
    """Locate the exact schema or logical owner without reading its body."""
    entry = _selected(name)
    return {'document_path': entry['document_path'],
            **({'schema': entry['schema']} if entry['schema'] else {'validator_source': entry['validator_source']})}


def _schema(name: str) -> Mapping | None:
    path = _selected(name)['schema']
    if path is None:
        return None
    from state_protocol import read_schema
    return read_schema(ROOT / path)


def _pointer_part(value: str) -> str:
    return value.replace('~', '~0').replace('/', '~1')


def _structure(schema: Mapping, pointer: str = '#') -> list[dict]:
    """Summarize declared object fields and branches without copying their rules."""
    rows = []
    properties = schema.get('properties')
    if isinstance(properties, Mapping):
        row = {'schema_pointer': pointer, 'required_keys': list(schema.get('required', [])),
               'permitted_keys': sorted(properties), 'additional_properties': schema.get('additionalProperties', True) is not False,
               'fields': {name: {'schema_pointer': pointer + '/properties/' + _pointer_part(name),
                                **{key: copy.deepcopy(value[key]) for key in ('type', 'const', 'enum', '$ref', 'description') if key in value}}
                          for name, value in properties.items() if isinstance(value, Mapping)}}
        rows.append(row)
    if '$ref' in schema:
        rows.append({'schema_pointer': pointer, '$ref': schema['$ref']})
    for key in ('properties', '$defs'):
        values = schema.get(key)
        if isinstance(values, Mapping):
            for name, value in values.items():
                if isinstance(value, Mapping):
                    rows.extend(_structure(value, pointer + '/' + key + '/' + _pointer_part(name)))
    for key in ('items', 'additionalProperties', 'if', 'then', 'else', 'not'):
        value = schema.get(key)
        if isinstance(value, Mapping):
            rows.extend(_structure(value, pointer + '/' + key))
    for key in ('allOf', 'oneOf', 'anyOf'):
        for index, value in enumerate(schema.get(key, [])):
            if isinstance(value, Mapping):
                rows.extend(_structure(value, pointer + '/' + key + '/' + str(index)))
    return rows


def metadata(name: str) -> dict:
    """Return source-backed discovery metadata for one authoring selection."""
    entry = copy.deepcopy(_selected(name))
    if name in {'choices', 'parameters', 'production_spec', 'plot', 'retrieval_record',
                'creative_intent', 'negative', 'negative_provenance', 'production_direction',
                'authority', 'render_intent', 'execution_policy', 'reference_render_contract'}:
        entry['example_paths'].insert(0, 'examples/input-authoring/README.md')
    schema = _schema(name)
    entry.update({'name': name, 'required_keys': None, 'permitted_keys': None,
                  'additional_properties': None, 'structure': []})
    if schema is not None:
        if name == 'production_spec':
            from production_spec import authored_schema
            entry['published_required_keys'] = list(schema.get('required', []))
            entry['schema_projection'] = 'Editable specification: only the target_model requirement is supplied by choices.target.'
            schema = authored_schema(schema)
        entry['structure'] = _structure(schema)
        entry['required_keys'] = list(schema.get('required', []))
        entry['permitted_keys'] = sorted(schema.get('properties', {}))
        entry['additional_properties'] = schema.get('additionalProperties', True) is not False
    elif name == 'negative_provenance':
        from build_generation_payload import NEGATIVE_PROVENANCE_FIELDS
        entry.update(required_keys=[], permitted_keys=sorted(NEGATIVE_PROVENANCE_FIELDS), additional_properties=False)
        entry['structure'] = [{'validator_source': entry['validator_source'], 'required_keys': [],
            'permitted_keys': sorted(NEGATIVE_PROVENANCE_FIELDS), 'additional_properties': False,
            'fields': {key: {'type': 'array', 'default': []} for key in sorted(NEGATIVE_PROVENANCE_FIELDS)}}]
    elif name == 'scene_plot':
        from scene_plot import ROOT_KEYS
        entry.update(permitted_keys=sorted(ROOT_KEYS), additional_properties=False)
    elif name == 'execution_policy':
        from execution_policy import REQUIRED_FIELDS, OPTIONAL_FIELDS
        entry.update(required_keys=sorted(REQUIRED_FIELDS), permitted_keys=sorted(REQUIRED_FIELDS | OPTIONAL_FIELDS),
                     additional_properties=False)
    elif name == 'reference_render_contract':
        from model_rendition import REFERENCE_CONTRACT_FIELDS
        entry.update(required_keys=sorted(REFERENCE_CONTRACT_FIELDS), permitted_keys=sorted(REFERENCE_CONTRACT_FIELDS),
                     additional_properties=False)
    elif name == 'mask_binding':
        from scene_mask_planner import BINDING_FIELDS
        entry.update(required_keys=sorted(BINDING_FIELDS), permitted_keys=sorted(BINDING_FIELDS), additional_properties=False)
    elif name in {'parameters', 'creative_intent'}:
        entry.update(required_keys=[], additional_properties=True)
    entry['validation_command'] = (_CHECK if entry['validation_scope'] == 'task-context' else
        'python scripts/production_document_contracts.py validate ' + name + ' FILE' +
        (' --root STUDIO' if entry['validation_scope'] == 'studio-context' else ''))
    entry['explain_command'] = 'python scripts/production_document_contracts.py explain ' + name
    return entry


def schema_fragment(name: str, pointer: str) -> Any:
    """Return an exact schema subtree by JSON Pointer; links remain explicit."""
    schema = _schema(name)
    if schema is None:
        raise ValueError(name + ' has a logical validator, not a JSON Schema; use its document_path and validator_source.')
    if pointer.startswith('#'):
        pointer = pointer[1:]
    if pointer and not pointer.startswith('/'):
        raise ValueError('--pointer must be a JSON Pointer beginning with / or #/')
    value = schema
    for part in pointer.split('/')[1:] if pointer else []:
        part = part.replace('~1', '/').replace('~0', '~')
        try:
            value = value[int(part)] if isinstance(value, (list, tuple)) else value[part]
        except (ValueError, IndexError, KeyError, TypeError) as exc:
            raise ValueError('schema pointer does not exist: ' + pointer) from exc
    from owned_json import mutable
    return mutable(value)


def validate_document(name: str, value: Any, *, root: Path | None = None) -> dict:
    """Invoke the actual local owner; contextual contracts keep their full gate."""
    entry = metadata(name)
    result = {'name': name, 'validation_scope': entry['validation_scope'], 'guidance': guidance(name),
              'remaining_checks': entry['remaining_checks'], 'permitted_keys': entry['permitted_keys']}
    try:
        if entry['validation_scope'] == 'task-context':
            raise ValueError(entry['remaining_checks'] + ' Run ' + _CHECK + '.')
        if entry['representation'] == 'text':
            if not isinstance(value, str):
                raise ValueError('The selected text document must contain UTF-8 text.')
            report = {'ok': True, 'errors': []}
        elif name == 'negative_provenance':
            from build_generation_payload import normalize_negative_provenance
            report = {'ok': True, 'errors': [], 'normalized': normalize_negative_provenance(value)}
        elif name == 'production_spec':
            from production_spec import validate_authored
            report = validate_authored(value, require_content=True)
        elif name == 'plot':
            from prompt_plot import validate_authored_prompt_plot
            report = validate_authored_prompt_plot(value)
        elif name == 'retrieval_record':
            from prompt_retrieval import validate_prompt_retrieval_record
            report = validate_prompt_retrieval_record(value)
        elif name == 'creative_intent':
            from revision_contract import require_intent_revision
            if not isinstance(value, dict):
                raise ValueError('creative intent must be an object')
            require_intent_revision(value)
            report = {'ok': True, 'errors': []}
        elif name in {'state_lineage', 'state_snapshot'}:
            from state_protocol import validate_artifact, validate_against_schema
            if not isinstance(value, dict):
                raise ValueError(name + ' must be an object')
            # Preserve the selected document's discriminator, including when a
            # different valid state artifact was accidentally selected here.
            errors = validate_against_schema(value, _schema(name))
            report = validate_artifact(value)
            report['errors'] = list(dict.fromkeys(errors + report['errors']))
            report['ok'] = not report['errors']
        elif name == 'authority':
            from production_permissions import validate
            from state_protocol import validate_against_schema
            if not isinstance(value, dict):
                raise ValueError('authority must be an object')
            errors = validate_against_schema(value, _schema(name))
            if errors:
                raise ValueError('; '.join(errors))
            validate(value, value.get('task_id'))
            report = {'ok': True, 'errors': []}
        elif name == 'execution_decisions':
            from production_decisions import validate_shape
            report = validate_shape(value)
        elif name == 'render_intent':
            from render_contract_lib import validate_intent
            validate_intent(value)
            report = {'ok': True, 'errors': []}
        elif name == 'scene_plot':
            from scene_plot import validate_scene_plot
            report = validate_scene_plot(value)
        elif name == 'mask_binding':
            from scene_mask_planner import validate_binding
            if root is None:
                raise ValueError('mask_binding validation requires --root STUDIO to read its declared source files.')
            validate_binding(root, value)
            report = {'ok': True, 'errors': []}
        else:
            raise ValueError('No local validator is declared for ' + name)
        result.update(report)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        result.update(ok=False, errors=[str(exc)])
    if not result['ok']:
        result['required_action'] = (_CHECK if entry['validation_scope'] == 'task-context' else
            'Correct the selected file using ' + entry['explain_command'] + ', then repeat this validation.')
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = operation_context.ArgumentParser(description=__doc__,
        epilog='Names are choices document keys. explain lists actual permitted fields and their source. '
               'Validation scopes: document checks local content; authored-document applies the owner\'s derived-field '
               'projection; document-shape checks schema structure only; studio-context also reads declared Studio '
               'files; task-context requires the selected complete task. Local validation grants no approval and '
               'never replaces the applicable preparation or execution boundary.')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('list', help='List the document names, owners and local or contextual validation command.')
    explain = sub.add_parser('explain', help='Show fields, exact schema or logical owner, examples and validation scope.')
    explain.add_argument('name', choices=sorted(CONTRACT_KEYS))
    explain.add_argument('--pointer', help='Show this exact JSON Pointer within the owning schema, for example /properties/subjects/items.')
    validate = sub.add_parser('validate', help='Validate one selected document through its actual local owner.')
    validate.add_argument('name', choices=sorted(CONTRACT_KEYS))
    validate.add_argument('file', type=Path, help='Authored document file; relative to the current working directory.')
    validate.add_argument('--root', type=Path, help='Studio root for a mask binding and its declared source files.')
    args = parser.parse_args(argv)
    try:
        if args.command == 'list':
            result = {'documents': [{key: value for key, value in metadata(name).items()
                                      if key in {'name', 'document_path', 'schema', 'validator_source',
                                                 'validation_scope', 'validation_command', 'explain_command'}}
                                    for name in sorted(CONTRACT_KEYS)]}
        elif args.command == 'explain':
            result = metadata(args.name)
            if args.pointer is not None:
                fragment = schema_fragment(args.name, args.pointer)
                result['structure'] = _structure(fragment, args.pointer) if isinstance(fragment, Mapping) else []
                result['schema_fragment'] = fragment
                result['schema_fragment_scope'] = 'The exact published schema; derived_fields identifies values supplied by compilation.'
        else:
            import execution_contract as c
            raw = args.file.read_bytes()
            value = raw.decode('utf-8') if _selected(args.name)['representation'] == 'text' else c.decode(raw)
            result = validate_document(args.name, value, root=args.root)
            result['file'] = str(args.file)
    except (OSError, ValueError) as exc:
        result = {'ok': False, 'errors': [str(exc)],
                  **({'guidance': guidance(args.name)} if hasattr(args, 'name') else {}),
                  **({'file': str(args.file)} if hasattr(args, 'file') else {})}
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if result.get('ok', True) else 2


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(operation_context.run_cli(main))
