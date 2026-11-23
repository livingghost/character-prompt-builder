"""Edit one actual Production choice through its existing authoring owner.

Pointers select meaningful choices, not generated task envelopes or bindings.
The shared mutation owner checks identity sources and publishes the proposed
choices and basis together. This module never writes an editable document,
acquires an approval or publishes part of a failed edit.
"""
from __future__ import annotations

import copy
from pathlib import Path
import re
from typing import Any

import authoring_work as pointers
import production_authoring as authoring
from production_diagnostics import ProductionError


_UNSET = object()
POINTER_SHELL_GUIDANCE = (
    'Pass the exact JSON Pointer, beginning with /, using only ~0 or ~1 escapes. '
    'In Windows Git Bash, prefix this command with MSYS_NO_PATHCONV=1; '
    'quoting alone does not disable its automatic path conversion.')
TASK_OWNERS = frozenset({'route', 'features', 'artifact', 'execution', 'criteria', 'direction',
    'recording', 'world_views', 'moment_views', 'scene_materials', 'upload_sources'})
TOP_OWNERS = frozenset({'target', 'reading', 'visual', 'validation', 'external'})
AUTHORING_OWNERS = frozenset({'delivery', 'generation', 'references', 'upscale'})
REFERENCE_FIELDS = frozenset({'transport_mode', 'max_side', 'reference_use_plan',
    'reference_selection', 'additional_references', 'image_input', 'zero_reference_reason', 'source_files'})
EXTERNAL_FIELDS = frozenset({'image_input', 'request', 'media_slots', 'source_files',
    'source_uploads', 'reference_delivery'})
IMAGE_FIELDS = frozenset({'artifact_type', 'references', 'prepared_references', 'external_request', 'model',
    'plan_sha256', 'binding_sha256', 'status', 'prepared_reference_set', 'prepared_references_sha256'})
GENERATED_IMAGE_FIELDS = frozenset({'model', 'plan_sha256', 'binding_sha256', 'status',
    'prepared_reference_set', 'prepared_references_sha256'})
GENERATED_REQUEST_FIELDS = frozenset({'file', 'sha256', 'reference_fields', 'request', 'request_sha256',
    'schema_validation', 'prompt_check', 'reference_text'})
IMAGE_REFERENCE_FIELDS = frozenset({'id', 'role', 'file', 'sha256', 'use_for', 'do_not_transfer',
    'subject_uses', 'transport'})
REQUEST_FIELDS = frozenset({'model_field', 'prompt_field', 'negative_field', 'count_field',
    'operation_field', 'count', 'schema', 'model_identity', 'vocabulary_record', 'prompt_syntax'})
TRANSPORT_FIELDS = frozenset({'field', 'local_file', 'value', 'evidence', 'uploaded_file'})
REFERENCE_ROOTS = (('authoring', 'references'), ('external', 'reference_delivery', 'choices'))
IMAGE_ROOTS = tuple(path + ('image_input',) for path in REFERENCE_ROOTS) + (('external', 'image_input'),)


def _pointer(parts) -> str:
    return ''.join('/' + pointers._escape(str(part)) for part in parts)


def _prefix(path: tuple, prefix: tuple) -> bool:
    return path[:len(prefix)] == prefix


def editable_owner(pointer: str) -> str | None:
    """Return the smallest public choice owner that contains this pointer."""
    parts = tuple(pointers._tokens(pointer))
    if parts and parts[0] in TOP_OWNERS:
        return _pointer(parts[:1])
    if parts[:2] == ('task_changes', 'semantic_edit'):
        return '/task_changes/semantic_edit'
    if len(parts) >= 2 and parts[0] == 'authoring':
        if parts[1] in AUTHORING_OWNERS:
            return _pointer(parts[:2])
        if len(parts) >= 3 and parts[1] == 'task' and parts[2] in TASK_OWNERS:
            return _pointer(parts[:3])
        if len(parts) >= 3 and parts[1] == 'documents' and parts[2] in authoring.DOCUMENTS:
            return _pointer(parts[:3])
    return None


def _error(message: str, *, file: str | None, pointer: str, cause: str,
           repair_owner: dict | None = None, required_action: str | None = None, **details):
    try:
        selected = editable_owner(pointer)
    except ValueError:
        selected = None
    owner = repair_owner or {'file': file, 'pointer': selected}
    raise ProductionError('INPUT_CONSISTENCY_ERROR', message, phase='authoring', file=file,
        pointer=pointer, cause=cause, evidence_owner={'file': file, 'pointer': pointer},
        repair_owner=owner, guidance={**authoring.EDITING_GUIDE,
            'schema': 'schemas/authoring/production-input-draft.schema.json'},
        required_action=required_action or 'Select the authored field exposed by explain-inputs, '
            'then apply the edit to that owner.', **details)


def _generated(path: tuple) -> bool:
    """Recognize generated fields by their owner, never by a global key name."""
    if _prefix(path, ('authoring', 'upscale', 'model')):
        return True
    if _prefix(path, ('visual', 'basis', 'sha256')):
        return True
    for base in REFERENCE_ROOTS:
        if _prefix(path, base + ('source_files',)):
            return True
        tail = path[len(base):] if _prefix(path, base) else ()
        if tail[:2] == ('reference_selection', 'selection_sha256'):
            return True
        if tail[:2] == ('reference_selection', 'unresolved_requirements'):
            return True
        if tail[:2] == ('reference_use_plan', 'surface_lighting') and len(tail) >= 3:
            if tail[2] in {'artifact_type', 'plan_id', 'source_evidence_roles', 'surface_lighting_plan_sha256'}:
                return True
    for base in IMAGE_ROOTS:
        if _prefix(path, base) and len(path) > len(base):
            tail = path[len(base):]
            if tail[0] in GENERATED_IMAGE_FIELDS:
                return True
            if len(tail) >= 3 and tail[0] == 'references' and tail[2] == 'sha256':
                return True
            if len(tail) >= 2 and tail[0] == 'external_request' and tail[1] in GENERATED_REQUEST_FIELDS:
                return True
            if tail[:1] == ('references',) and len(tail) >= 5:
                if tail[2:4] == ('transport', 'evidence') and tail[4] == 'sha256':
                    return True
            if tail[:1] == ('external_request',) and len(tail) >= 3:
                if tail[1] in {'schema', 'vocabulary_record'} and tail[2] == 'sha256':
                    return True
                if tail[1:3] == ('model_identity', 'evidence') and len(tail) >= 4 and tail[3] == 'sha256':
                    return True
    if any(_prefix(path, ('external', field)) for field in ('source_files', 'source_uploads')):
        return True
    if path[:2] == ('target', 'model') and len(path) >= 3:
        return path[2] in {'catalog_status', 'catalog_model'} or path[2:4] == ('evidence', 'sha256')
    return False


def _source_measurement(path: tuple) -> bool:
    for base in REFERENCE_ROOTS:
        if not _prefix(path, base):
            continue
        tail = path[len(base):]
        row = (len(tail) >= 4 and tail[0] == 'additional_references' and tail[2] == 'source')
        row = row or (len(tail) >= 5 and tail[:2] in {
            ('reference_use_plan', 'items'), ('reference_selection', 'selected_references')}
            and tail[3] == 'source')
        if row and tail[-1] in {'sha256', 'media_type'}:
            return True
    return False


def _lookup(value: Any, parts: tuple):
    try:
        return pointers._select(value, _pointer(parts))
    except (ValueError, TypeError):
        return _UNSET


def _preserve_measurements(before: dict, after: dict) -> None:
    """A parent replacement omitting measurements keeps their original owner."""
    for base, fields in [(path, ('source_files',)) for path in REFERENCE_ROOTS] + [
            (('external',), ('source_files', 'source_uploads'))]:
        previous, current = _lookup(before, base), _lookup(after, base)
        if not isinstance(current, dict) or (base == ('external',) and isinstance(current.get('image_input'), str)):
            continue
        for field in fields:
            if field not in current:
                current[field] = copy.deepcopy(previous.get(field, {} if field == 'source_files' else [])
                    if isinstance(previous, dict) else {} if field == 'source_files' else [])


def _field_check(before: Any, after: Any, path: tuple, *, file: str | None) -> None:
    """Check every descendant so replacing a parent cannot inject a binding."""
    if _generated(path):
        empty_measurement = before is _UNSET and path[-1] in {'source_files', 'source_uploads'} and after in ({}, [])
        if not empty_measurement and (before is _UNSET or after != before):
            _error('This field is derived by its input owner.', file=file, pointer=_pointer(path),
                cause='choice-owner-protected', required_action='Edit the source selection or authored content; '
                    'its builder derives this binding or measurement.')
        return
    if isinstance(after, dict):
        allowed = None
        if path in REFERENCE_ROOTS:
            allowed = REFERENCE_FIELDS
        elif path in IMAGE_ROOTS:
            allowed = IMAGE_FIELDS
        elif path == ('external',):
            allowed = {'image_input'} if isinstance(after.get('image_input'), str) else EXTERNAL_FIELDS
        for base in IMAGE_ROOTS:
            if not _prefix(path, base):
                continue
            tail = path[len(base):]
            if len(tail) == 2 and tail[0] == 'references':
                allowed = IMAGE_REFERENCE_FIELDS
            elif len(tail) == 3 and tail[0] == 'references' and tail[2] == 'transport':
                allowed = TRANSPORT_FIELDS
            elif len(tail) == 4 and tail[0] == 'references' and tail[2:] == ('transport', 'evidence'):
                allowed = {'path', 'locator', 'sha256'}
            elif tail == ('external_request',):
                allowed = REQUEST_FIELDS | GENERATED_REQUEST_FIELDS
        for base in REFERENCE_ROOTS:
            if not _prefix(path, base):
                continue
            tail = path[len(base):]
            if tail == ('reference_use_plan',):
                allowed = {'items', 'unavailable_record_uses', 'surface_lighting'}
            elif len(tail) == 3 and tail[:2] == ('reference_use_plan', 'items'):
                from production_reference_inputs import PLAN_ITEM_FIELDS, PLAN_SCOPE_FIELDS
                allowed = PLAN_ITEM_FIELDS | PLAN_SCOPE_FIELDS | {'id', 'subject_uses', 'delivery_id'}
        if allowed is not None and set(after) - allowed:
            name = sorted(set(after) - allowed)[0]
            _error('The selected owner has no editable field named ' + name + '.', file=file,
                pointer=_pointer(path + (name,)), cause='choice-field-unknown', permitted_fields=sorted(allowed))
        for name, value in after.items():
            old = before.get(name, _UNSET) if isinstance(before, dict) else _UNSET
            selected = path + (name,)
            if _source_measurement(selected) and after.get('kind') == 'supplied-file':
                if old is _UNSET or old != value:
                    _error('Supplied-file measurements belong to the source reader.', file=file,
                        pointer=_pointer(selected), cause='choice-owner-protected',
                        required_action='Select source.resolved_path and let the source reader measure its bytes.')
            _field_check(old, value, selected, file=file)
    elif isinstance(after, list):
        prior = before if isinstance(before, list) else []
        by_id = {row['id']: row for row in prior if isinstance(row, dict) and isinstance(row.get('id'), str)}
        for index, value in enumerate(after):
            old = prior[index] if index < len(prior) else _UNSET
            if isinstance(value, dict) and isinstance(value.get('id'), str):
                old = by_id.get(value['id'], _UNSET)
            _field_check(old, value, path + (str(index),), file=file)


def _native_fields(choices: dict) -> list[tuple[tuple, tuple]]:
    """Return request fields whose real values have another authored owner."""
    external = choices.get('external')
    if not isinstance(external, dict) or not isinstance(external.get('image_input'), dict):
        return []
    plan = external['image_input']
    contract = plan.get('external_request')
    if not isinstance(contract, dict):
        return []
    owners = {'model_field': ('target',), 'prompt_field': ('authoring', 'delivery'),
        'count_field': ('external', 'image_input', 'external_request', 'count'),
        'operation_field': ('target',)}
    result = []
    for name, owner in owners.items():
        field = contract.get(name)
        if isinstance(field, list) and field:
            result.append((('external', 'request', *map(str, field)), owner))
    references = plan.get('references')
    for index, row in enumerate(references if isinstance(references, list) else []):
        transport = row.get('transport') if isinstance(row, dict) else None
        field = transport.get('field') if isinstance(transport, dict) else None
        if isinstance(field, list) and field:
            result.append((('external', 'request', *map(str, field)),
                ('external', 'image_input', 'references', str(index), 'transport')))
    return result


def apply_edit(choices: dict, pointer: str, value: Any = _UNSET, *, operation: str = 'replace',
               file: str | None = None) -> dict:
    """Return one structurally valid partial draft, leaving its input untouched."""
    from production_inputs import _validate_choices, normalize_task_choices
    if operation not in {'add', 'replace', 'remove'} or (operation == 'remove') != (value is _UNSET):
        _error('Add and replace require a JSON value; remove takes no value.', file=file, pointer=pointer,
            cause='choice-edit-arguments', required_action='Use --value-file with add or replace; omit it with remove.')
    try:
        parts = tuple(pointers._tokens(pointer))
        owner = editable_owner(pointer)
    except ValueError as error:
        _error(str(error), file=file, pointer=pointer, cause='choice-pointer-invalid',
            received_pointer=pointer, required_action=POINTER_SHELL_GUIDANCE)
    if owner is None and isinstance(pointer, str) and (
            re.match(r'^/?[A-Za-z]:[/\\]', pointer) or pointer.startswith('\\\\')):
        _error('The received pointer has filesystem-path syntax instead of an authored JSON Pointer.',
            file=file, pointer=pointer, cause='choice-pointer-invalid', received_pointer=pointer,
            required_action=POINTER_SHELL_GUIDANCE)
    if owner is None or _generated(parts) or _source_measurement(parts):
        action = 'Select a specific authored owner from explain-inputs; mixed-owner parents and generated fields are protected.'
        if parts[:3] == ('authoring', 'task', 'sources'):
            action = 'Use acquire-source with the actual source row; work-basis.json owns source applications.'
        elif parts[:1] == ('authoring_stage',):
            action = 'Use stage-inputs to select the current work stage and its reading scope.'
        _error('The pointer does not select an editable Production choice.', file=file, pointer=pointer,
            cause='choice-owner-protected', required_action=action)
    before = normalize_task_choices(choices)
    delivery = before['authoring']['delivery']
    if _prefix(parts, ('authoring', 'delivery', 'content')) and 'file' in delivery:
        _error('The selected delivery file owns this content.', file=file, pointer=pointer,
            cause='choice-content-owned-by-file',
            repair_owner={'file': delivery['file'], 'pointer': _pointer(delivery.get('field', []))},
            required_action='Edit the selected delivery file, or replace authoring.delivery with one explicit new selector.')
    for protected, actual_owner in _native_fields(before):
        if _prefix(parts, protected):
            _error('This native request field is derived from another authored choice.', file=file,
                pointer=pointer, cause='choice-owner-protected',
                repair_owner={'file': file, 'pointer': _pointer(actual_owner)})
    after = copy.deepcopy(before)
    try:
        container = pointers._select(after, _pointer(parts[:-1]))
        key = parts[-1]
        if isinstance(container, dict):
            if operation != 'add' and key not in container:
                raise ValueError('JSON Pointer member is absent: ' + key)
            if operation == 'remove':
                del container[key]
            else:
                container[key] = copy.deepcopy(value)
        elif isinstance(container, list):
            index = pointers._index(key, len(container), append=operation == 'add')
            if operation == 'add':
                container.insert(index, copy.deepcopy(value))
            elif operation == 'remove':
                container.pop(index)
            else:
                container[index] = copy.deepcopy(value)
        else:
            raise ValueError('JSON Pointer selects a scalar parent')
    except (ValueError, TypeError) as error:
        _error(str(error), file=file, pointer=pointer, cause='choice-pointer-invalid',
            required_action='Select an existing parent and member for replace/remove, or an insertion position for add.')
    _preserve_measurements(before, after)
    _field_check(before, after, (), file=file)
    for protected, actual_owner in _native_fields(after):
        previous, current = _lookup(before, protected), _lookup(after, protected)
        # Empty native slots declare a container for the builder. Populated
        # prompt, target and media values must come from their actual owners.
        if current is not _UNSET and current is not None and current != previous:
            _error('The parent replacement changes a native field owned by another choice.', file=file,
                pointer=_pointer(protected), cause='choice-owner-protected',
                repair_owner={'file': file, 'pointer': _pointer(actual_owner)})
    _validate_choices(after, file=file)
    return after


def edit_choices(root: Path, choices_path: str, pointer: str, *, operation: str = 'replace',
                 value_file: str | None = None) -> dict:
    """Acquire one value and publish one guarded edit through the shared owner."""
    from production_draft_mutation import update_draft
    if (operation == 'remove') != (value_file is None):
        _error('Add and replace require --value-file; remove takes no --value-file.',
            file=choices_path, pointer=pointer, cause='choice-edit-arguments',
            required_action='Supply one JSON value file for add or replace, or omit it for remove.')

    def transform(choices, basis, reader):
        value = _UNSET if value_file is None else reader.json(reader.select(value_file))
        updated = apply_edit(choices, pointer, value, operation=operation, file=choices_path)
        from production_inputs import normalize_task_choices
        return updated, basis, {'edit': {'pointer': pointer, 'operation': operation,
            'owner': {'file': choices_path, 'pointer': editable_owner(pointer)},
            'changes': pointers.changes(normalize_task_choices(choices), updated)}}

    result = update_draft(root, choices_path, transform, operation='edit-choices')
    import operation_context
    current = operation_context.current()
    if current is not None:
        current.link(choices=choices_path)
        current.event('authored_edit', choices=choices_path, pointer=pointer, operation=operation,
                      changed=bool(result['changed']), owner=result['edit']['owner'])
    return result
