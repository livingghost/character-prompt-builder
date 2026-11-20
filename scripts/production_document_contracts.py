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
from cli_invocation import python_argv, shown

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
        'scripts/generation_inputs.py:GenerationInputs.acquire', example=_PILOT + 'creative-intent.json',
        remaining='The object preserves authored detail. Compilation binds it to the actual specification and state lineage; authoring_work owns candidate changes.'),
    'negative': _contract(
        'references/runtime/prompt-composition.md#negative-output',
        'scripts/generation_payload_builder.py:prepare_text_transports', representation='text',
        example=_PILOT + 'negative.txt', remaining='The target and selected transport determine whether and where this text is delivered.'),
    'integrated_prompt': _contract(
        'references/runtime/image-generation.md#model-and-negative-transport',
        'scripts/generation_payload_builder.py:prepare_text_transports', representation='text',
        example=_PILOT + 'integrated-prompt.txt',
        remaining='The target and selected transport determine whether this complete rendition is delivered.'),
    'native_negative': _contract(
        'references/runtime/image-generation.md#model-and-negative-transport',
        'scripts/generation_payload_builder.py:prepare_text_transports', representation='text',
        remaining='The target and selected transport determine the supported native negative rendition.'),
    'negative_provenance': _contract(
        'references/runtime/prompt-composition.md#negative-output',
        'scripts/generation_payload_builder.py:normalize_negative_provenance',
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
    'image_input': _contract(
        'references/runtime/production-external-inputs.md#edit-the-request-and-media-choices',
        'scripts/image_input.py:validate', schema='schemas/authoring/image-input-plan.schema.json',
        example='templates/image-input-plan.template.json', scope='task-context',
        remaining='This is the complete image-input plan contract. Editable external choices obtain model from '
                  'choices.target, request text from the delivery and hashes from selected files. '
                  'check --choices validates their assembled request, references and evidence together.'),
    'external_choices': _contract(
        'references/runtime/production-external-inputs.md#edit-the-request-and-media-choices',
        'scripts/production_external_inputs.py:unresolved',
        example='examples/input-assembly/README.md', scope='task-context',
        remaining='The external input owner accepts one existing-plan selector or its complete editable '
                  'envelope. Native request controls and reference transports need the actual interface evidence; '
                  'the builder derives repeated fields and exact file bindings.'),
    'external_target': _contract(
        'references/runtime/production-external-inputs.md#exact-target-and-provider-schema',
        'scripts/production_target.py:unresolved', scope='task-context',
        derived=('$.catalog_status', '$.catalog_model', '$.evidence.sha256'),
        remaining='The author selects the actual interface and its evidence. The builder derives catalog '
                  'status and evidence hashes. Include prompt_input only when the acquired model evidence '
                  'supports it; an unlisted interface can leave it absent. A supplied evidence hash remains '
                  'a commitment to those exact bytes.'),
    'model_prompt_input': _contract(
        'references/runtime/production-external-inputs.md#exact-target-and-provider-schema',
        'scripts/model_prompt_input.py:validate_prompt_input', schema='schemas/model-prompt-input.schema.json',
        remaining='This checks an acquired prompt-input declaration. It does not infer a model form, '
                  'establish provider support or demonstrate a visual effect.'),
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
    'principal_approval': _contract(
        'references/runtime/production-permissions.md#retain-a-direct-instruction-for-one-request',
        'scripts/production_authority_drafts.py:validate_principal_shape',
        schema='schemas/authoring/production-principal-approval.schema.json', scope='document-shape',
        derived=('$.binding', '$.instruction.sha256'),
        remaining='Drafting retains literal instruction text and derives the exact request binding. Import and '
                  'execution check that binding, current issuer and the authored approval. The host judges actual authority.'),
    'authority_update': _contract(
        'references/runtime/production-permissions.md#add-authority-for-a-prepared-run',
        'scripts/production_authority_drafts.py:validate_update_shape',
        schema='schemas/authoring/production-authority-update.schema.json', scope='document-shape',
        derived=('$.task_id', '$.issuer', '$.run', '$.input_sha256', '$.request_sha256', '$.expected_event',
                 '$.selection', '$.adoption', '$.grants[*].operation', '$.grants[*].targets'),
        remaining='Import verifies the current issuer, exact predecessor, run, operations, evidence and authored '
                  'additional grants. Selection and adoption use their current retained candidate, review and destination '
                  'owners. This local shape check neither imports authority nor authenticates the instruction.'),
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


def explain_action(name: str, pointer: str | None = None) -> dict:
    """Executable navigation to an existing document owner, without validation."""
    _selected(name)
    argv = python_argv(ROOT / 'scripts/production_document_contracts.py', 'explain', name)
    if pointer is not None:
        argv.extend(('--pointer', pointer))
    return {'operation': 'explain-document-contract', 'argv': argv, 'shown': shown(argv),
            'external_effect': False}


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
            from production_spec import TEMPLATE, authored_schema
            entry['published_required_keys'] = list(schema.get('required', []))
            entry['schema_projection'] = 'Editable specification: only the target_model requirement is supplied by choices.target.'
            schema = authored_schema(schema)
            draft_help = python_argv(ROOT / 'scripts/production_spec.py', 'draft', '--help')
            template_read = [draft_help[0], '-m', 'json.tool', str(TEMPLATE)]
            entry['scaffold'] = {
                'owner': 'scripts/production_spec.py:draft',
                'template_path': TEMPLATE.relative_to(ROOT).as_posix(),
                'help_action': {'operation': 'explain-production-spec-draft', 'argv': draft_help,
                                'shown': shown(draft_help), 'external_effect': False},
                'template_action': {'operation': 'read-production-spec-template', 'argv': template_read,
                                    'shown': shown(template_read), 'external_effect': False},
                'subject_schema_action': explain_action(name, '/properties/subjects/items'),
                'meaning': 'The existing draft command creates the smallest valid one-subject specification '
                           'from explicit arguments. Choose the actual subject, domain, brief, render intent '
                           'and continuity. The template supports an explicitly subject-free scene. '
                           'Select the resulting file in authoring.documents.production_spec; choices.target '
                           'owns the published target_model.'}
        entry['structure'] = _structure(schema)
        entry['required_keys'] = list(schema.get('required', []))
        entry['permitted_keys'] = sorted(schema.get('properties', {}))
        entry['additional_properties'] = schema.get('additionalProperties', True) is not False
    elif name == 'negative_provenance':
        from generation_payload_builder import NEGATIVE_PROVENANCE_FIELDS
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
    elif name == 'external_choices':
        from production_external_inputs import FIELDS, template
        entry.update(required_keys=sorted(FIELDS), permitted_keys=sorted(FIELDS), additional_properties=False,
                     template=template(), template_source='scripts/production_external_inputs.py:template')
        entry['representations'] = [
            {'kind': 'editable', 'required_keys': sorted(FIELDS), 'template': template()},
            {'kind': 'existing-plan', 'required_keys': ['image_input'],
             'example': {'image_input': 'inputs/selected-plan.json'},
             'source_contract': 'image_input'}]
        entry['template_scope'] = 'Unanswered editable envelope from its runtime owner; no target, native controls or references are selected.'
    elif name == 'external_target':
        from production_target import EXTERNAL_MODEL_FIELDS, EXTERNAL_TARGET_FIELDS
        from owned_json import mutable
        image_schema = _schema('image_input')
        model = mutable(image_schema['properties']['model'])
        for key in ('catalog_status', 'catalog_model'):
            model['properties'].pop(key)
        model['required'] = sorted({*EXTERNAL_MODEL_FIELDS, 'target'})
        model.pop('allOf', None)
        model['properties']['target'] = mutable(image_schema['$defs']['target'])
        evidence = mutable(image_schema['$defs']['evidence'])
        evidence['required'].remove('sha256')
        model['properties']['evidence'] = evidence
        entry.update(required_keys=model['required'], permitted_keys=sorted(model['properties']),
                     additional_properties=False, structure=_structure(model),
                     template={**{key: None for key in EXTERNAL_MODEL_FIELDS},
                         'target': {key: None for key in EXTERNAL_TARGET_FIELDS},
                         'evidence': {key: None for key in evidence['required']}},
                     source_schema={'schema': _selected('image_input')['schema'], 'pointer': '/properties/model',
                         'explain_command': 'python scripts/production_document_contracts.py explain image_input '
                                            '--pointer /properties/model'})
        entry['template_scope'] = 'Unanswered required fields from the target owner and image-input schema. Supply the actual interface evidence.'
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


def validate_document(name: str, value: Any, *, root: Path | None = None, render_presets=None) -> dict:
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
            from generation_payload_builder import normalize_negative_provenance
            report = {'ok': True, 'errors': [], 'normalized': normalize_negative_provenance(value)}
        elif name == 'production_spec':
            from production_spec import validate_authored
            report = validate_authored(value, require_content=True, render_presets=render_presets)
        elif name == 'plot':
            from prompt_plot import validate_authored_prompt_plot
            report = validate_authored_prompt_plot(value)
        elif name == 'retrieval_record':
            from prompt_retrieval import validate_prompt_retrieval_record
            report = validate_prompt_retrieval_record(value)
        elif name == 'creative_intent':
            if not isinstance(value, dict):
                raise ValueError('creative intent must be an object')
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
        elif name in {'principal_approval', 'authority_update'}:
            from production_authority_drafts import validate_principal_shape, validate_update_shape
            report = (validate_principal_shape(value) if name == 'principal_approval'
                      else validate_update_shape(value))
        elif name == 'render_intent':
            from render_contract_lib import validate_intent
            validate_intent(value, render_presets=render_presets)
            report = {'ok': True, 'errors': []}
        elif name == 'model_prompt_input':
            from model_prompt_input import validate_prompt_input
            validate_prompt_input(value)
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
