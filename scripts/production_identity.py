"""Expose existing identity owners and actual request carriers to coverage checks.

This adapter reads declared source ownership and reference influence. It does
not classify prose, adopt a source, infer hidden anatomy or assess image pixels.
The coverage engine receives the same bytes that production preparation saves.
"""
from __future__ import annotations

import copy
from pathlib import Path

import execution_contract as c
import request_contract as request


# These are independently validated graph owners, not a vocabulary of traits.
IDENTITY_NODES = ('identity_contract', 'species_profile', 'individual_morphology',
                  'era_contract', 'form_contract', 'appearance_variant',
                  'visual_authority', 'visual_evidence_bundle')


def _pointer(value, pointer: str):
    if pointer == '':
        return value
    if not isinstance(pointer, str) or not pointer.startswith('/'):
        raise ValueError('identity source selector must be a JSON Pointer')
    for part in pointer[1:].split('/'):
        part = part.replace('~1', '/').replace('~0', '~')
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def _declared(task: dict, read, source: dict) -> bool:
    """Reuse an explicitly selected whole owner instead of duplicating its data."""
    wanted = set(source['subject_ids'])
    for item in task.get('sources', []):
        identity = item.get('identity')
        if not identity or not wanted <= set(identity['subject_ids']):
            continue
        raw = read(item['path'])
        selectors = identity['selectors']
        if source['format'] == 'image':
            if '' in selectors and c.digest(raw) == source['sha256']:
                return True
            continue
        try:
            value = c.decode(raw)
        except (ValueError, UnicodeDecodeError):
            continue
        if item['path'] == source['path']:
            point = source.get('source_pointer', '')
            if any(point == chosen or point.startswith(chosen + '/') for chosen in selectors):
                return True
        for chosen in selectors:
            try:
                if c.content_id(_pointer(value, chosen)) == c.content_id(source['value']):
                    return True
            except (KeyError, IndexError, TypeError, ValueError):
                # The engine reports the invalid selection at its owning field.
                continue
    return False


def _specification(task: dict, read, package: dict | None) -> dict | None:
    if package is not None:
        return package.get('production_spec')
    path = (task.get('generation') or {}).get('production_spec')
    if path is None:
        path = next((source['path'] for source in task.get('sources', [])
                     if source.get('role') == 'production-spec'
                     and source.get('disposition') == 'applied'), None)
    return c.decode(read(path)) if path else None


def reference_id(row: dict) -> str:
    """Use the owning reference identity, independent of its transport position."""
    # Match the reference input builder's default logical ID. A source artifact
    # can be used twice with different subject scopes; its artifact ID alone
    # cannot distinguish those uses. Explicit image-input IDs take precedence
    # in context(), where their owning rows are available.
    return 'reference-' + c.content_id({key: row[key] for key in row if key != 'transport'})[:20]


def _reference_subjects(row: dict, subjects: list[str]) -> tuple[list[str], list[str]]:
    uses = row.get('subject_uses', [])
    assigned = sorted({use['subject_id'] for use in uses})
    identity = sorted({use['subject_id'] for use in uses if use['use'] == 'identity'})
    if row.get('subject_id'):
        assigned = sorted(set(assigned) | {row['subject_id']})
        if 'identity' in row['use_for']:
            identity = sorted(set(identity) | {row['subject_id']})
    if not assigned and len(subjects) == 1:
        assigned = list(subjects)
        if 'identity' in row['use_for']:
            identity = list(subjects)
    if 'identity' not in row['use_for'] or 'identity' in row['do_not_transfer']:
        identity = []
    return assigned, identity


def context(task: dict, read, *, package: dict | None = None,
            rendered: dict | None = None, inputs: dict | None = None,
            reference_set: dict | None = None, visual: dict | None = None,
            source_reader=None) -> dict:
    """Resolve source inventories and carriers from the owners already selected.

    With no rendered request the result is an authoring view. Text and media
    are not certified as model input until the compiler supplies the exact
    rendered request or the validated external input binding.
    """
    source_reader = source_reader or read
    specification = _specification(task, read, package)
    subjects = [row['id'] for row in specification['subjects']] if specification else []
    if not subjects:
        subjects = list((task.get('recording') or {}).get('subject_map', {}))
    if not subjects and task.get('artifact') != 'image':
        subjects = sorted({subject for row in task.get('sources', [])
                           for subject in (row.get('identity') or {}).get('subject_ids', [])})
    if package is not None:
        reference_set = package.get('prepared_reference_set')
        visual = package.get('visual_continuity')
    if inputs is None and task.get('image_input'):
        inputs = c.decode(read(task['image_input']))
    if reference_set is None and inputs:
        reference_set = inputs.get('prepared_reference_set')
        if reference_set is None and inputs.get('prepared_references'):
            reference_set = c.decode(read(inputs['prepared_references']))
    if reference_set is None and (task.get('generation') or {}).get('references'):
        reference_set = c.decode(read(task['generation']['references']))
    if visual is None and (task.get('generation') or {}).get('visual_continuity'):
        visual = c.decode(read(task['generation']['visual_continuity']))

    required = {subject for subject, value in (visual or {}).get('subjects', {}).items()
                if value.get('continuity') == 'recurring' or value.get('identity_refs')}
    required.update(subject for subject, choice in (task.get('generation') or {}).get('continuity', {}).items()
                    if choice == 'recurring')
    extra = []
    graph_path = (task.get('generation') or {}).get('state_graphs')
    if graph_path:
        raw = read(graph_path)
        graphs = c.decode(raw)
        for index, graph in enumerate(graphs):
            subject = graph['identity_contract']['character_id']
            required.add(subject)
            for node in IDENTITY_NODES:
                value = graph.get(node)
                if value is None:
                    continue
                source = {'id': 'state:' + subject + ':' + node,
                    'path': graph_path, 'source_pointer': '/' + str(index) + '/' + node,
                    'subject_ids': [subject], 'selectors': [''], 'format': 'json',
                    'sha256': c.digest(raw), 'value': copy.deepcopy(value),
                    'authority': {'owner': node, 'character_id': subject,
                                  'canon_status': value.get('canon_status')}}
                if not _declared(task, read, source):
                    extra.append(source)

    native = (reference_set or {}).get('selected_references', [])
    declared = (inputs or {}).get('references', [])
    if declared and native and len(declared) != len(native):
        raise ValueError('identity reference inventory differs from the prepared source count')
    scopes = []
    if reference_set:
        from reference_delivery import bindings
        scopes = bindings(reference_set['transport_mode'], native, reference_set.get('single_board'))
    rows = []
    plan_items = iter(((reference_set or {}).get('reference_use_plan') or {}).get('reference_items', []))
    for index in range(len(declared) if declared else len(native)):
        original = native[index] if native else None
        if declared:
            row = copy.deepcopy(declared[index])
        else:
            row = {'id': reference_id(original), 'file': original['source']['resolved_path'],
                   'sha256': original['source']['sha256'], 'role': original['role'],
                   'use_for': original['authority']['controls'],
                   'do_not_transfer': original['authority']['must_not_control'],
                   'subject_uses': copy.deepcopy(original.get('subject_uses', []))}
        if original and original.get('subject_id'):
            row['subject_id'] = original['subject_id']
        # Native controls describe the permitted scope in prose. Influence IDs
        # come from their explicit owners, never from searching those words.
        controls = list(row['use_for'])
        influences = {use['use'] for use in row.get('subject_uses', [])}
        if original:
            influences.update(original.get('intended_influence', []))
            if original['source']['kind'] == 'pack-artifact':
                plan_item = next(plan_items, None)
                if plan_item is None:
                    raise ValueError('identity source inventory needs the selected Reference Use Plan')
                influences.add(plan_item['intended_influence'])
        row['use_for'] = sorted(set(row['use_for']) | influences)
        if influences & set(row['do_not_transfer']):
            from production_diagnostics import ProductionError
            raise ProductionError('IDENTITY_REFERENCE_SCOPE',
                'A declared reference influence is explicitly excluded by its source scope.',
                phase='identity-coverage', reference=row['id'],
                required_action='Resolve the conflicting intended use and exclusion in the existing reference choices.')
        assigned, identity_subjects = _reference_subjects(row, subjects)
        if 'identity' in row['use_for'] and not row.get('subject_uses') and not assigned:
            from production_diagnostics import ProductionError
            raise ProductionError('IDENTITY_SUBJECT_REQUIRED',
                'An identity reference needs its actual subject assignment.', phase='identity-coverage',
                reference=row['id'], required_action='Select the Production Specification subjects and '
                'assign this reference\'s identity influence to the intended subject in the existing reference choices.')
        source_path = row['file']
        source_raw = source_reader(source_path)
        source_hash = c.digest(source_raw)
        if row.get('sha256') is not None and source_hash != row['sha256']:
            raise ValueError('identity reference source changed: ' + source_path)
        carrier = {'id': row['id'], 'subject_ids': assigned,
                   'use_for': list(row['use_for']), 'do_not_transfer': list(row['do_not_transfer']),
                   'controls': controls, 'intended_influence': sorted(influences),
                   'subject_uses': copy.deepcopy(row.get('subject_uses', [])),
                   'source_sha256': source_hash, 'carrier_sha256': None,
                   'request_fields': [], 'region_pixels': None}
        scope = scopes[index] if scopes else None
        if scope is not None:
            carrier['region_pixels'] = scope.get('region_pixels')
            carrier['reference_number'] = scope['reference_number']
            carrier['attachment_number'] = scope['attachment_number']
            carrier['derivation'] = copy.deepcopy(original['transport'].get('derivation'))
        if rendered is not None and scope is not None:
            number = scope['attachment_number'] - 1
            media = rendered['media'][number]
            carrier['carrier_sha256'] = media['sha256']
            carrier['request_fields'] = [field['field'] for field in rendered['layout']['media']
                                         if field['index'] == number]
        elif (inputs or {}).get('external_request'):
            external = inputs['external_request']
            if 'request' in external:
                field = external['reference_fields'][index]
                if request.get(external['request'], field['field']) != field['value']:
                    raise ValueError('identity carrier differs from its external request')
                carrier['request_fields'] = [field['field']]
                if scope is None:
                    carrier['carrier_sha256'] = source_hash
                elif reference_set['transport_mode'] == 'single-board':
                    carrier['carrier_sha256'] = reference_set['single_board']['sha256']
                else:
                    carrier['carrier_sha256'] = original['transport']['sha256']
        rows.append(carrier)
        if identity_subjects:
            required.update(identity_subjects)
            source = {'id': 'reference:' + row['id'], 'path': source_path,
                'subject_ids': identity_subjects, 'selectors': [''], 'format': 'image',
                'sha256': source_hash, 'value': None,
                'authority': {'reference': row['id'], 'use_for': list(row['use_for']),
                              'controls': controls, 'intended_influence': sorted(influences),
                              'do_not_transfer': list(row['do_not_transfer']),
                              'subject_uses': copy.deepcopy(row.get('subject_uses', []))}}
            if original:
                source['authority']['source'] = copy.deepcopy(original['source'])
            if not _declared(task, read, source):
                extra.append(source)

    text = {}
    if rendered is not None:
        pairs = (('primary', rendered['layout'].get('primary_text')),
                 ('negative', rendered['layout'].get('negative_text')))
        actual = rendered['request']
    elif ((inputs or {}).get('external_request') or {}).get('request') is not None:
        external = inputs['external_request']
        pairs = (('primary', external['prompt_field']), ('negative', external.get('negative_field')))
        actual = external['request']
    else:
        pairs, actual = [], None
    for name, field in pairs:
        if field is None:
            continue
        value = request.get(actual, field)
        if not isinstance(value, str):
            raise ValueError('identity text carrier is not a text request surface')
        text[name] = {'text': value, 'field': field, 'sha256': c.digest(value.encode('utf-8'))}
    return {'subject_ids': subjects, 'required_subject_ids': sorted(required),
            'identity_sources': extra, 'text': text, 'references': rows}


def inspect(task: dict, read, **kwargs) -> dict:
    """Show source coverage during authoring without claiming request delivery."""
    import identity_coverage
    view = context(task, read, **kwargs)
    result = identity_coverage.inventory(task, read, context=view)
    result['request_verified'] = False
    result['reference_choices'] = view['references']
    return result
