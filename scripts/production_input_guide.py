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
EXTERNAL_DOCUMENT = 'references/runtime/production-external-inputs.md'
IMAGE_SCHEMA = 'schemas/authoring/image-input-plan.schema.json'

# These describe responsibilities. Allowed keys and required fields come from
# the schemas or the document's logical owner, never this navigation map.
OWNERS = {
    'authoring_stage': ('Select definition, depiction, rendition or prepare with stage-inputs while keeping the same editable work.',
                        'references/runtime/production-authoring.md#select-and-read-the-current-knowledge'),
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
    'authoring.task': ('Own direction, independent criteria and task choices; sources are projected from work-basis.json.',
                       'references/runtime/production-direction.md'),
    'authoring.delivery': ('Edit the exact prompt or authored deliverable at its selected source.', DOCUMENT),
    'authoring.documents': ('Select each specialist document at its single editable file.', DOCUMENT),
    'authoring.generation': ('Own generation choices not derived from the target or specialist files.',
                             'references/runtime/production-authoring.md'),
    'authoring.references': ('Select source images, their subject scope, influence and exclusions.',
                             'references/runtime/reference-delivery.md'),
    'authoring.upscale': ('Select the source image and actual enlargement choices when applicable.',
                          'references/runtime/production-authoring.md'),
    'authoring.source_files': ('Retain source provenance; the builder captures actual file bytes.', DOCUMENT),
}

# These are navigation locations within existing contracts, not additional
# authoring fields or validation rules. The selected target kind remains an
# explicit choice even when the task uses an external execution branch.
CHILD_OWNERS = {
    'task_changes.semantic_edit': ('Select the editable semantic edit plan; the selected file owns its edit and review content.',
                                   'references/runtime/production-authoring.md#start-an-existing-image-edit'),
    'authoring.task.direction': ('Own the task direction at this existing choices field; its production contract keeps its contextual checks.',
                                 'references/runtime/production-direction.md#record-the-production-direction'),
    'authoring.task.criteria': ('Own independent review criteria, subject comparisons and their declared identity bindings.',
                               'references/character-identity-contract.md#source-to-input-and-review-coverage'),
    'authoring.task.recording': ('Own explicit subject IDs and their Studio character assignments for recording.',
                                'references/character-identity-contract.md#source-to-input-and-review-coverage'),
    'target.model': ('Select the actual model name or acquired external interface.', EXTERNAL_DOCUMENT),
    'target.model.target': ('Name the exact service, model identifier and wire operation from evidence.', EXTERNAL_DOCUMENT),
    'target.model.evidence': ('Select the saved evidence identifying this external interface.', EXTERNAL_DOCUMENT),
    'target.model.prompt_input': ('Declare only prompt-form knowledge supported by acquired model evidence.', EXTERNAL_DOCUMENT),
    'external.image_input': ('Select the image plan and current reference scope; choices.target owns its model.', EXTERNAL_DOCUMENT),
    'external.image_input.external_request': ('Map the actual native prompt, model, count and operation fields.', EXTERNAL_DOCUMENT),
    'external.image_input.external_request.model_identity': ('Identify an endpoint or tool when the native request has no model parameter.', EXTERNAL_DOCUMENT),
    'external.image_input.external_request.schema': ('Select the exact acquired native request schema.', EXTERNAL_DOCUMENT),
    'external.image_input.references': ('Choose actual image sources, their intended uses and delivery transports.', EXTERNAL_DOCUMENT),
    'external.request': ('Edit independent controls supported by the selected native interface.', EXTERNAL_DOCUMENT),
    'external.media_slots': ('Declare existing native media leaves while retaining unrelated request values.', EXTERNAL_DOCUMENT),
}


def action(root: Path, choices_path: str, *, field: str | None = None) -> dict:
    argv = python_argv(ROOT / 'scripts/production_workflow.py', 'explain-inputs',
                       '--root', str(root), '--choices', choices_path)
    if field is not None:
        argv.extend(('--field', field))
    return {'operation': 'explain-inputs', 'argv': argv, 'shown': shown(argv),
            'external_effect': False}


def _contract_action(name: str, pointer: str | None = None) -> dict:
    import production_document_contracts as contracts
    return contracts.explain_action(name, pointer)


def _child(root: Path, choices_path: str, field: str, *, contract: str | None = None,
           pointer: str | None = None) -> dict:
    result = {'field': field, 'explain_action': action(root, choices_path, field=field)}
    if contract is not None:
        import production_document_contracts as contracts
        result.update(contracts.guidance(contract))
        result['schema_action'] = _contract_action(contract, pointer)
        if pointer is not None:
            result['schema_pointer'] = pointer
    return result


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
    from production_reference_inputs import text_guide
    basis_path = (Path(choices_path).parent / 'work-basis.json').as_posix()
    context_argv = python_argv(ROOT / 'scripts/authoring_work.py', 'context', str(root / basis_path), '--basis-only')
    source_row_path = (Path(choices_path).parent / 'source-row.json').as_posix()
    source_argv = python_argv(ROOT / 'scripts/production_workflow.py', 'acquire-source',
        '--root', str(root), '--choices', choices_path, '--source-row', source_row_path)
    edit_help = python_argv(ROOT / 'scripts/production_workflow.py', 'edit-choices', '--help')
    import production_input_preflight
    task = (choices.get('authoring') or {}).get('task') or {}
    input_contracts = {'target': _child(root, choices_path, 'target'),
                      'authoring_stage': _child(root, choices_path, 'authoring_stage')}
    if task.get('execution') == 'external' or choices.get('external') is not None:
        input_contracts['external'] = _child(root, choices_path, 'external', contract='external_choices')
    return {'document_path': DOCUMENT, 'schema': SCHEMA, 'example': EXAMPLE,
            'explain_action': action(root, choices_path),
            'input_contracts': input_contracts,
            'documents': selected,
            'reference_text': text_guide(choices),
            'structured_edit': {'operation': 'edit-choices', 'choices_file': choices_path,
                'document_path': 'references/runtime/production-authoring.md#edit-an-authored-choices-field',
                'help_action': {'argv': edit_help, 'shown': shown(edit_help)},
                'meaning': 'Edit one authored JSON Pointer with add, replace or remove. The current draft may '
                           'remain unfinished. Source acquisition and generated bindings keep their own owners.'},
            'source_acquisition': {'operation': 'acquire-source', 'argv': source_argv, 'shown': shown(source_argv),
                'source_row_file': source_row_path, 'schema': production_input_preflight.TASK_SCHEMA,
                'schema_pointer': '/properties/sources/items',
                'meaning': 'Write one complete Production source row, including its role and any identity selection. '
                           'The command acquires bytes and derives applications, subjects and task sources.'},
            **({'source_requirements': production_input_preflight.source_roles(root, task, choices_path=choices_path)}
               if task.get('route') and task.get('execution') else {}),
            'authoring_work': {'basis': basis_path, 'actual_content': choices_path,
                'context_argv': context_argv,
                'context_command': shown(context_argv),
                'inputs': '--request FILE; --application APP=SOURCE#POINTER; '
                          '--subject SUBJECT=APP[,APP...]; --requirement APP; --focus character|supporting-setting; '
                          'plan or draft-inputs --retain OWNER --change SCOPE for a retained amendment',
                'change_scope': {'file': basis_path, 'pointer': '/change_scope',
                    'schema': 'schemas/authoring/authoring-work.schema.json',
                    'document_path': 'references/runtime/production-authoring.md#declare-a-retained-amendment',
                    'meaning': 'Declare retained owners and intended changes once in the basis. Actual changed '
                               'values can expand required knowledge; retained conflicts need an explicit correction.'},
                'ownership': 'The basis owns acquired originals, current applications and the amendment change_scope. Task sources are a derived '
                             'view. Acquire Production sources with source_acquisition; the generic context command '
                             'does not declare Production role or identity metadata. A Production Specification '
                             'subject supplies its actual identity owner when no '
                             'independent adopted definition is selected.'},
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
    for kind in ('items', 'if', 'then', 'else', 'not'):
        if isinstance(schema.get(kind), dict):
            result[kind] = _shape(schema[kind])
    return result


def _field_shape(schema: dict) -> dict:
    return {**_shape(schema), 'fields': {key: _shape(value)
            for key, value in schema.get('properties', {}).items()}}


def _fragment(row: dict, pointer: str) -> dict:
    """Expose an exact published schema and keep its editable projection explicit."""
    import production_document_contracts as contracts
    fragment = contracts.schema_fragment('image_input', pointer)
    row.update(content_schema=IMAGE_SCHEMA, content_schema_pointer=pointer,
               schema_action=_contract_action('image_input', pointer),
               published_declaration=_field_shape(fragment))
    return fragment


def _external_fields(root: Path, choices_path: str, choices: dict, name: str, row: dict,
                     *, detailed: bool) -> None:
    """Navigate the real external input owners without selecting interface values."""
    import production_document_contracts as contracts
    target = choices.get('target')
    kind = target.get('kind') if isinstance(target, dict) else None
    selected = choices.get('external')
    selected_plan = selected.get('image_input') if isinstance(selected, dict) else None
    if name == 'target':
        row['selected_kind'] = kind
        row['child_contracts'] = {'model': _child(root, choices_path, 'target.model')}
        if detailed:
            row['branches'] = [{
                'kind': variant['properties']['kind']['const'],
                'schema_pointer': '/properties/target/oneOf/' + str(index),
                'declaration': _field_shape(variant)}
                for index, variant in enumerate(contracts.schema_fragment('choices', '/properties/target')['oneOf'])
                if 'kind' in variant.get('properties', {})]
            row['required_action'] = ('Keep the selected kind, or choose catalog, acquired or external from the '
                'actual target evidence. Follow the model child contract for that selection.')
        return
    if name.startswith('target.model'):
        row['selected_kind'] = kind
        if kind != 'external':
            variants = contracts.schema_fragment('choices', '/properties/target')['oneOf']
            row['target_branches'] = [{
                'kind': variant['properties']['kind']['const'],
                'model_field': 'model_file' if variant['properties']['kind']['const'] == 'acquired' else 'model',
                'declaration': _shape(variant['properties'].get('model', variant['properties'].get('model_file', {})))}
                for variant in variants if 'kind' in variant.get('properties', {})]
            row['external_contract'] = {**contracts.guidance('external_target'),
                                       'explain_action': _contract_action('external_target')}
            if kind is not None:
                selected_branch = next((item for item in row['target_branches'] if item['kind'] == kind), None)
                if selected_branch is not None:
                    row['declaration'] = selected_branch['declaration']
            row['required_action'] = ('Select target.kind explicitly from the actual model/interface evidence. '
                'The external model object applies only to kind external; a catalog model uses its ID string '
                'and an acquired model uses model_file.')
            return
        if name == 'target.model':
            entry = contracts.metadata('external_target')
            row['contract'] = {key: value for key, value in entry.items() if key != 'structure'}
            row['declaration'] = entry['structure'][0]
            row['template'] = entry['template']
            row['child_contracts'] = {
                'target': _child(root, choices_path, name + '.target', contract='image_input', pointer='/$defs/target'),
                'evidence': _child(root, choices_path, name + '.evidence', contract='image_input', pointer='/$defs/evidence'),
                'prompt_input': _child(root, choices_path, name + '.prompt_input', contract='model_prompt_input')}
            row['required_action'] = ('Fill requested, target and evidence from the selected interface. '
                'Omit catalog_status, catalog_model and unacquired prompt_input; the builder derives catalog '
                'facts and evidence hashes. Follow a child action for its exact shape.')
        elif name == 'target.model.prompt_input':
            entry = contracts.metadata('model_prompt_input')
            row['contract'] = {key: value for key, value in entry.items() if key != 'structure'}
            row['declaration'] = _field_shape(contracts.schema_fragment('model_prompt_input', ''))
            row['schema_action'] = _contract_action('model_prompt_input', '')
            row['required_action'] = ('Include this optional declaration only when acquired evidence supports '
                'the selected model form. Leaving it absent records unresolved knowledge for an unlisted '
                'interface; it does not select natural language or tags.')
        else:
            child = name.rsplit('.', 1)[1]
            fragment = _fragment(row, '/$defs/' + child)
            if child == 'evidence':
                fragment['required'].remove('sha256')
            row['declaration'] = _field_shape(fragment)
            row['template'] = {key: None for key in fragment['required']}
            row['required_action'] = ('Select these values from the actual acquired interface evidence. '
                'For evidence, path is Studio-relative and locator identifies the relevant section; '
                'an omitted sha256 is derived from the selected bytes.')
        return
    if name == 'external':
        row['contract'] = {key: value for key, value in contracts.metadata('external_choices').items()
                           if key != 'structure' and (detailed or key not in {'template', 'representations'})}
        row['selected_representation'] = ('existing-plan' if isinstance(selected_plan, str) else
                                          'editable' if isinstance(selected, dict) else 'unselected')
        row['child_contracts'] = {
            'image_input': _child(root, choices_path, 'external.image_input', contract='image_input'),
            'request': _child(root, choices_path, 'external.request'),
            'media_slots': _child(root, choices_path, 'external.media_slots')}
        if detailed:
            row['template'] = contracts.metadata('external_choices')['template']
            row['required_action'] = ('Use the complete editable template for a new request, then fill '
                'image_input and the native request through their child contracts. To select an existing '
                'complete plan instead, use only {"image_input": STUDIO_RELATIVE_PLAN_PATH}.')
        return
    if name == 'external.image_input':
        fragment = _fragment(row, '')
        fragment['required'].remove('model')
        fragment['properties'].pop('model')
        row['declaration'] = _field_shape(fragment)
        row['template'] = {'artifact_type': fragment['properties']['artifact_type']['const'],
                           'references': [], 'external_request': None}
        row['template_scope'] = 'An unanswered inline plan. Select the actual references or an exact request with none.'
        row['derived_fields'] = {'model': 'choices.target'}
        row['child_contracts'] = {
            'external_request': _child(root, choices_path, name + '.external_request',
                                      contract='image_input', pointer='/properties/external_request'),
            'references': _child(root, choices_path, name + '.references',
                                contract='image_input', pointer='/$defs/reference')}
        if isinstance(selected_plan, str):
            row['source'] = {'file': selected_plan}
            row['required_action'] = ('The selected file owns the complete plan. Use its published schema, '
                'including its model and request file; the inline template applies when authoring the '
                'complete external envelope instead.')
        else:
            row['required_action'] = ('Fill external_request from the native interface field mappings and '
                'select the actual ordered references. Keep model at choices.target; the builder supplies '
                'it here. Follow the child actions for request and reference shapes.')
        return
    if name == 'external.image_input.external_request':
        fragment = _fragment(row, '/properties/external_request/anyOf/0')
        generated = {'file', 'sha256', 'reference_fields', 'reference_text'}
        fragment['required'] = [key for key in fragment['required'] if key not in generated]
        fragment['properties'] = {key: value for key, value in fragment['properties'].items() if key not in generated}
        row['declaration'] = _field_shape(fragment)
        row['template'] = {key: None for key in fragment['required']}
        row['derived_fields'] = sorted(generated)
        row['field_paths'] = 'Paths are arrays of object keys and array indices in the native request.'
        row['child_contracts'] = {
            'model_identity': _child(root, choices_path, name + '.model_identity',
                                     contract='image_input', pointer='/$defs/model-identity'),
            'schema': _child(root, choices_path, name + '.schema',
                             contract='image_input', pointer='/properties/external_request/anyOf/0/properties/schema')}
        row['required_action'] = ('Set prompt_field to the actual prompt path and count to the expected output '
            'count. Set model_field to its native parameter path, or null and fill model_identity for an '
            'evidenced endpoint/tool. operation_field and count_field are null when absent from the native '
            'interface. Select the acquired request schema through its child contract. Tag input also '
            'requires its negative_field, prompt_syntax and acquired vocabulary_record.')
        return
    if name in {'external.image_input.external_request.model_identity',
                'external.image_input.external_request.schema'}:
        identity = name.endswith('.model_identity')
        pointer = '/$defs/model-identity' if identity else '/properties/external_request/anyOf/0/properties/schema/anyOf/0'
        fragment = _fragment(row, pointer)
        if identity:
            evidence = contracts.schema_fragment('image_input', '/$defs/evidence')
            evidence['required'].remove('sha256')
            fragment['properties']['evidence'] = evidence
            row['template'] = {'kind': None, 'value': None,
                               'evidence': {key: None for key in evidence['required']}}
        else:
            fragment['required'].remove('sha256')
            row['template'] = {'path': None, 'pointer': []}
        row['declaration'] = _field_shape(fragment)
        row['required_action'] = (
            'Use kind endpoint or tool, the exact interface value and saved evidence when model_field is null. '
            'When model_field names a native parameter, omit model_identity or set it to null.' if identity else
            'Set path to the Studio-relative acquired schema file and pointer to its exact keys/indices; '
            '[] selects the complete document. The builder captures sha256. Native parameters remain '
            'governed by this selected schema.')
        return
    if name == 'external.image_input.references':
        fragment = _fragment(row, '/$defs/reference')
        row['declaration'] = {'type': 'array', 'items': _field_shape(fragment)}
        row['direct_reference_template'] = {key: [] if fragment['properties'][key].get('type') == 'array' else None
                                            for key in fragment['required']}
        row['direct_reference_template']['transport'] = None
        row['transport_choices'] = [
            {'local_file': True}, {'value': None, 'evidence': {'path': None, 'locator': None}}]
        row['canonical_reference_template'] = {'id': None, 'transport': None}
        row['selected_source_owner'] = ('external.reference_delivery.choices'
            if isinstance(selected, dict) and selected.get('reference_delivery') is not None else name)
        row['required_action'] = ('Select actual source files, uses, exclusions and subject assignments. '
            'Use local_file only when the host accepts local carriers; otherwise retain the actual returned '
            'upload value and evidence. transport.field selects a native media path when its mapping is '
            'ambiguous or no media array is declared yet. Declare each enclosing native media array in '
            'external.request; [] starts a new empty media array. For canonical reference_delivery, '
            'its choices own source scope and these rows own '
            'only ID and transport. An exact request with no references uses an empty array.')
        row['request_action'] = action(root, choices_path, field='external.request')
        return
    if name == 'external.media_slots':
        fragment = _fragment(row, '/$defs/field-path')
        row['declaration'] = {'type': 'array', 'items': _shape(fragment)}
        row['validator_source'] = 'scripts/production_external_inputs.py:_media'
        row['required_action'] = ('List the exact field paths of existing media leaves in external.request. '
            'The builder may reorder or remove only those declared media items; it retains unrelated native '
            'values. For a new empty media array, declare that array as [] in external.request, leave '
            'media_slots empty, and give each selected reference its explicit transport.field. Never mark '
            'independent prompt, model, count, operation or control fields as media slots.')
        row['request_action'] = action(root, choices_path, field='external.request')
        return
    if name == 'external.request':
        row['declaration'] = {'anyOf': [{'type': 'object'}, {'type': 'array'}]}
        row['validator_source'] = 'scripts/production_external_inputs.py:build'
        schema = ((selected_plan or {}).get('external_request') or {}).get('schema') if isinstance(selected_plan, dict) else None
        row['native_schema'] = copy.deepcopy(schema)
        row['child_contracts'] = {'schema': _child(root, choices_path,
            'external.image_input.external_request.schema', contract='image_input',
            pointer='/properties/external_request/anyOf/0/properties/schema'),
            'media_slots': _child(root, choices_path, 'external.media_slots')}
        row['derived_values'] = {'prompt': 'authoring.delivery', 'model': 'choices.target',
                                'count': 'external.image_input.external_request.count',
                                'media': 'external.image_input.references'}
        row['required_action'] = ('Use the actual native request object or array and its independent controls '
            'from the acquired schema. The declared field mappings supply prompt, model, operation, count '
            'and media during assembly. Declare each enclosing media array explicitly: [] starts a new '
            'empty media array, with reference transport.field selecting its item location. Keep native '
            'operation records and independent controls; media_slots identifies existing media leaves '
            'when retaining a populated array. A schema for another interface does not define these controls.')
        from production_external_inputs import media_location_diagnostics
        row['media_location_diagnostics'] = media_location_diagnostics(
            selected, root=root, choices_path=choices_path)


def _schema_field(schema: dict, parts: list[str]) -> dict:
    selected = schema
    for part in parts:
        selected = _resolve_schema_reference(schema, selected)
        found = [variant['properties'][part] for variant in _variants(selected)
                 if part in variant.get('properties', {})]
        if not found:
            return {}
        selected = found[0] if len(found) == 1 else {'anyOf': found}
    return _resolve_schema_reference(schema, selected)


def _schema_reference(schema: dict, parts: list[str]) -> str | None:
    """Return the declared local reference for an exact choices path, if any."""
    selected = schema
    for part in parts:
        selected = _resolve_schema_reference(schema, selected)
        found = [variant['properties'][part] for variant in _variants(selected)
                 if part in variant.get('properties', {})]
        if len(found) != 1:
            return None
        selected = found[0]
    reference = selected.get('$ref') if isinstance(selected, dict) else None
    return reference if isinstance(reference, str) else None


def _resolve_schema_reference(schema: dict, selected: dict) -> dict:
    """Follow local JSON Schema references so a public field shows its real shape."""
    seen = set()
    while isinstance(selected, dict):
        reference = selected.get('$ref')
        if not isinstance(reference, str) or not reference.startswith('#/') or reference in seen:
            return selected
        seen.add(reference)
        target = schema
        try:
            for part in reference[2:].split('/'):
                part = part.replace('~1', '/').replace('~0', '~')
                target = target[int(part)] if isinstance(target, list) else target[part]
        except (ValueError, IndexError, KeyError, TypeError):
            return selected
        siblings = {key: value for key, value in selected.items() if key != '$ref'}
        if siblings:
            return {'allOf': [target, siblings]}
        selected = target
    return selected


def _value(choices: dict, parts: list[str]):
    value = choices
    for part in parts:
        if not isinstance(value, dict) or part not in value:
            return False, None
        value = value[part]
    return True, value


def _reference_fields(schema: dict) -> dict[str, tuple[dict, str, bool]]:
    """Locate declared reference children at their exact published schema paths."""
    selected = schema['properties']['authoring']['properties']['references']
    base = '/properties/authoring/properties/references'
    result = {}
    for index, branch in enumerate(selected['oneOf']):
        for key, declaration in branch.get('properties', {}).items():
            result['authoring.references.' + key] = (
                declaration, base + '/oneOf/' + str(index) + '/properties/' + key,
                key in branch.get('required', []))
    return result


def _reference_guide(root: Path, choices_path: str, name: str, row: dict,
                     declarations: dict) -> None:
    if name == 'authoring.references':
        row['child_contracts'] = {child.rsplit('.', 1)[1]: _child(root, choices_path, child,
            contract='choices', pointer=declaration[1]) for child, declaration in declarations.items()}
        row['required_action'] = ('Keep null when no references are selected. To add or change references, '
            'follow the child contracts for the actual source selections and image_input behavior; '
            'the builder derives file hashes, reference IDs and attachment positions.')
        return
    declaration, pointer, required = declarations[name]
    row.update(declaration=_field_shape(declaration), schema_pointer=pointer,
               schema_action=_contract_action('choices', pointer),
               required_when_parent_supplied=required)
    row.pop('required_in_draft', None)
    if name.endswith('.additional_references'):
        row['item_declaration'] = _field_shape(declaration['items'])
        help_argv = python_argv(ROOT / 'scripts/studio_reference.py', '--help')
        row['source_navigation'] = {
            'studio': {'argv': help_argv, 'shown': shown(help_argv), 'external_effect': False,
                'meaning': 'source pins current canonically adopted artwork; accepted-source pins current '
                           'slot acceptance without granting canonical identity authority.',
                'required_inputs': '--studio STUDIO --character CHARACTER --slot SLOT source|accepted-source --out FILE',
                'current_studio': str(root)},
            'supplied_file': {'kind': 'supplied-file', 'reference_id': None, 'resolved_path': None},
            'meaning': 'Use the returned Studio source object unchanged, or select an actual supplied file. '
                       'Keep its applicable source authority; do not reclassify adopted artwork as an '
                       'unrestricted file. The source object belongs in each selected row at source.'}
        row['required_action'] = ('Add or reorder only the requested direct sources. Each row owns role, source '
            'and any subject_uses. Preparation derives missing use IDs and file hashes; retain existing IDs '
            'when other authored choices refer to them. A captured output becomes input only when explicitly '
            'selected for this request. Then inspect image_input to choose how the selected sources are bound.')
        row['image_input_action'] = action(root, choices_path, field='authoring.references.image_input')


def _document_execution_scope(choices: dict) -> dict:
    """Read current generation-document limits from the existing task schema."""
    import production_document_contracts as contracts
    from production_input_preflight import generation_scope
    scope = generation_scope(choices)
    allowed = set(scope['permitted_generation_fields'])
    return {**scope,
            'permitted_generation_documents': sorted(allowed & contracts.DOCUMENT_KEYS),
            'not_permitted_generation_documents': sorted(contracts.DOCUMENT_KEYS - allowed),
            'meaning': 'These are the current task schema limits for execution inputs under generation. '
                       'A known document key is not permission to send it through this execution branch. '
                       'Keep applicable research or source evidence at its existing source owner; '
                       'select documents as execution inputs only where permitted. Other route, content '
                       'and evidence checks still apply.'}


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
                      choices_pointer='/authoring/documents/' + name,
                      contract={key: value for key, value in contract.items() if key != 'structure'},
                      contract_action=contracts.explain_action(name))
        scope = _document_execution_scope(choices)
        result['execution_input'] = {'permitted_as_generation_document':
            name in scope['permitted_generation_documents'] if scope['execution_selected'] else None, **scope}
        return result
    reference_fields = _reference_fields(schema)
    if field and field not in OWNERS and field not in CHILD_OWNERS and field not in reference_fields:
        raise ValueError('select one input field: ' + ', '.join((*OWNERS, *CHILD_OWNERS)) +
                         ', ' + ', '.join(reference_fields) + ', or authoring.documents.<document-name>')
    selected_fields = [field] if field else list(OWNERS)
    fields = []
    for name in selected_fields:
        parts = name.split('.')
        actual = _schema_field(schema, parts)
        parent = _schema_field(schema, parts[:-1]) if len(parts) > 1 else schema
        present, value = _value(choices, parts)
        purpose, document = ((OWNERS | CHILD_OWNERS)[name] if name not in reference_fields else
                             OWNERS['authoring.references'])
        row = {'field': name, 'purpose': purpose, 'document_path': document,
               'choices_pointer': '/' + '/'.join(parts),
               'required_in_draft': parts[-1] in parent.get('required', []),
               'present': present, 'value_state': 'absent' if not present else 'null' if value is None else 'supplied',
               'declaration': _shape(actual)}
        if name in OWNERS:
            row['schema_pointer'] = '/properties/' + '/properties/'.join(parts)
        if isinstance(value, dict) and 'file' in value:
            row['source'] = {key: copy.deepcopy(value[key]) for key in ('file', 'field') if key in value}
        if name in {'task_changes', 'task_changes.semantic_edit'}:
            from production_choice_edits import editable_owner
            pointer = editable_owner('/task_changes/semantic_edit')
            edit_help = python_argv(ROOT / 'scripts/production_workflow.py', 'edit-choices', '--help')
            edit_action = {'operation': 'edit-choices', 'choices_file': choices_path, 'pointer': pointer,
                'help_action': {'argv': edit_help, 'shown': shown(edit_help)},
                'required_inputs': 'Select --operation add|replace|remove. For add or replace, supply --value-file '
                                   'containing the JSON string of the Studio-relative plan path; remove takes no value.'}
            if name == 'task_changes':
                child = _child(root, choices_path, 'task_changes.semantic_edit')
                child.update(choices_pointer=pointer, edit_action=edit_action)
                row.update(editable_container=False, child_contracts={'semantic_edit': child},
                    task_choices_action=action(root, choices_path, field='authoring.task'),
                    required_action='task_changes is a display selector and mixed-owner container, not an editable '
                    'parent. Follow the semantic_edit child for its exact plan selector. Other authored task '
                    'choices belong under authoring.task; use their individual owner pointers.')
            else:
                row.update(edit_action=edit_action, source={'file': value} if isinstance(value, str) else None,
                    content_schema='schemas/authoring/semantic-edit-plan.schema.json',
                    required_action='Edit this selector to choose the plan file. Edit /edit/target, /edit/change, '
                    '/edit/preserve and /review_criteria in that selected file; its contents are not children '
                    'of this choices pointer.')
        if name == 'authoring.task':
            row['content_schema'] = 'schemas/authoring/production-task.schema.json'
            row['schema_scope'] = ('This is the compiled task contract. The draft owns authored task fields; '
                'delivery, generation, route_reading, image_input and authored_basis are derived by their builders.')
            direction = _child(root, choices_path, 'authoring.task.direction', contract='production_direction')
            direction['explain_command'] = 'python scripts/production_document_contracts.py explain production_direction'
            row['child_contracts'] = {
                'direction': direction,
                'authority': {'source': value.get('authority') if isinstance(value, dict) else None,
                              'explain_command': 'python scripts/production_document_contracts.py explain authority',
                              **contracts.guidance('authority')},
                **{key: {'schema': row['content_schema'], 'pointer': '/properties/' + key}
                   for key in ('sources', 'criteria', 'recording', 'world_views')},
            }
            for child in ('criteria', 'recording'):
                row['child_contracts'][child]['explain_action'] = action(
                    root, choices_path, field='authoring.task.' + child)
        if name == 'authoring.task.direction':
            row['declaration'] = _field_shape(actual)
            contract = contracts.metadata('production_direction')
            row['contract'] = {key: value for key, value in contract.items() if key != 'structure'}
            row['contract_action'] = contracts.explain_action('production_direction')
            reference = _schema_reference(schema, parts)
            if reference is not None:
                row['referenced_schema_pointer'] = reference[1:]
                row['schema_pointer'] = reference[1:]
                row['choices_schema_pointer'] = '/properties/' + '/properties/'.join(parts)
            row['required_action'] = ('Edit this declared direction in the current choices file. Follow contract_action '
                'for its production-direction schema and contextual checks; task sources, independent criteria and '
                'actual authority remain separate inputs.')
        if name in {'authoring.task.criteria', 'authoring.task.recording'}:
            row['content_schema'] = 'schemas/authoring/production-task.schema.json'
            row['schema_pointer'] = '/properties/' + parts[-1]
            fragment = c.load(ROOT / row['content_schema'])['properties'][parts[-1]]
            row['declaration'] = _field_shape(fragment)
            row['schema_fragment'] = fragment
        if name == 'authoring.task.recording':
            row['subject_declaration'] = {'choices_pointer': '/authoring/task/recording/subject_map',
                'schema_pointer': '/properties/recording/properties/subject_map',
                'meaning': 'Each key is an explicitly declared image subject ID; its value is the Studio character ID. '
                           'The other recording choices retain their existing required fields.'}
        if name == 'authoring.documents':
            row['available_documents'] = sorted(contracts.DOCUMENT_KEYS)
            row['selected_documents'] = copy.deepcopy(value) if isinstance(value, dict) else {}
            row['document_help'] = 'Select --field authoring.documents.NAME for its complete contract and current file.'
            row['execution_inputs'] = _document_execution_scope(choices)
        if name == 'authoring.generation':
            scope = _document_execution_scope(choices)
            allowed = set(scope['permitted_generation_fields'])
            declaration = copy.deepcopy(actual)
            declaration['properties'] = {key: value for key, value in actual.get('properties', {}).items()
                                         if key in allowed}
            row['declaration'] = _field_shape(declaration)
            row['content_schema'] = scope['schema']
            row['content_schema_pointers'] = scope['schema_pointers']
            row['schema_scope'] = 'Editable inline choices within the selected execution contract; derived fields retain their own owners.'
            row['execution_inputs'] = scope
            row['derived_owners'] = {}
            documents = (choices.get('authoring') or {}).get('documents') or {}
            for key in sorted(allowed - set(declaration['properties'])):
                if key in contracts.DOCUMENT_KEYS:
                    child = _child(root, choices_path, 'authoring.documents.' + key, contract=key)
                    child['choices_pointer'] = '/authoring/documents/' + key
                    if key in documents:
                        child['source'] = copy.deepcopy(documents[key])
                else:
                    field_owner = {'model': 'target', 'service': 'target',
                                   'references': 'authoring.references', 'request_validation': 'validation'}.get(key)
                    if field_owner is None:
                        continue
                    child = _child(root, choices_path, field_owner)
                    child['choices_pointer'] = '/' + field_owner.replace('.', '/')
                row['derived_owners'][key] = child
            row['required_action'] = ('Edit the listed inline fields for the selected execution. '
                if declaration['properties'] else 'Keep authoring.generation empty for the selected execution. ')
            row['required_action'] += ('Use derived_owners to select compiled generation documents and bindings '
                'through their existing owners. Retain the brief at its existing source, specification, direction '
                'or prompt owner; this guide does not move or duplicate its content.')
        if name in {'authoring.references', 'external', 'authoring.delivery'}:
            from production_reference_inputs import text_guide
            row['reference_text'] = text_guide(choices)
        if name == 'authoring.references' or name in reference_fields:
            _reference_guide(root, choices_path, name, row, reference_fields)
        if name == 'target' or name.startswith('target.model') or name == 'external' or name.startswith('external.'):
            _external_fields(root, choices_path, choices, name, row, detailed=field is not None)
        fields.append(row)
    result['fields'] = fields
    if field == 'authoring':
        result['authoring_guide'] = summary(root, choices_path, choices)
    if field is not None:
        check = python_argv(ROOT / 'scripts/production_workflow.py', 'check', '--root', str(root),
                            '--choices', choices_path)
        result['next_actions'] = [{'operation': 'check', 'argv': check, 'shown': shown(check),
                                   'reason': 'After editing the owning fields, check this complete current draft.',
                                   'external_effect': False}]
    return result
