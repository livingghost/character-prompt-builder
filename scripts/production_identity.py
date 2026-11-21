"""Expose retained identity owners and actual request carriers to binding checks.

This adapter reads declared source ownership and reference influence. It does
not classify prose, adopt a source, infer hidden anatomy or assess image pixels.
Whole owners remain comparison context independently of which scene obligations
are explicitly bound. The engine receives the bytes production preparation saves.
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
    import identity_coverage
    import production_identity_boundary as boundary
    wanted = set(source['subject_ids'])
    candidate = None
    for item in task.get('sources', []):
        identity = item.get('identity')
        if not identity or wanted != set(identity['subject_ids']):
            continue
        if boundary._authority(identity.get('authority')) != boundary._authority(source.get('authority')):
            # Identical pixels or graph bytes do not make two scoped uses the
            # same source owner. Keep the current scope independently visible.
            continue
        try:
            if candidate is None:
                candidate = boundary.normalize_source(identity_coverage._source_record(source, read, derived=True))
            direct = boundary.normalize_source(identity_coverage._source_record(item, read))
            # The declared source can name the same owner under its own source
            # ID. Authority, original content, subjects and full scope must all
            # agree before one representation can stand for both.
            direct['id'] = candidate['id']
            if boundary._comparison_key(direct) == boundary._comparison_key(candidate):
                return True
        except (OSError, ValueError, KeyError, IndexError, TypeError):
            # Its source owner reports unresolved acquisition or invalid scope.
            continue
    return False


def _specification_path(task: dict) -> str | None:
    path = (task.get('generation') or {}).get('production_spec')
    if path is None:
        path = next((source['path'] for source in task.get('sources', [])
                     if source.get('role') == 'production-spec'
                     and source.get('disposition') == 'applied'), None)
    return path


def _specification(task: dict, read, package: dict | None) -> dict | None:
    if package is not None:
        return package.get('production_spec')
    path = _specification_path(task)
    return c.decode(read(path)) if path else None


def reference_id(row: dict) -> str:
    """Use the owning reference identity, independent of its transport position."""
    # references/runtime/reference-delivery.md#reference-identities-and-coverage
    # distinguishes this use ID from the reference: identity-source prefix.
    from reference_delivery import reference_id as selected_reference_id
    return selected_reference_id(row)


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
            source_reader=None, production_spec: dict | None = None) -> dict:
    """Resolve retained source context and carriers from the selected owners.

    With no rendered request the result is an authoring view. Text and media
    are not certified as model input until the compiler supplies the exact
    rendered request or the validated external input binding. A draft that has
    not written its Production Specification yet supplies it as production_spec.
    Retaining a complete owner does not require exposing or binding each value
    in the current image; criteria own explicit scene obligations.
    """
    source_reader = source_reader or read
    specification = production_spec if production_spec is not None else _specification(task, read, package)
    subjects = [row['id'] for row in specification['subjects']] if specification else []
    declaration = {'owner': 'production_spec', 'present': specification is not None,
                   'pointer': '/subjects'}
    specification_path = _specification_path(task)
    if specification_path is not None:
        declaration['file'] = specification_path
    if not subjects:
        recording = task.get('recording') or {}
        subjects = list(recording.get('subject_map', {}))
        if 'subject_map' in recording and (subjects or specification is None):
            declaration = {'owner': 'recording.subject_map', 'present': True,
                           'pointer': '/recording/subject_map'}
    if not subjects and task.get('artifact') != 'image':
        subjects = sorted({subject for row in task.get('sources', [])
                           for subject in (row.get('identity') or {}).get('subject_ids', [])})
        declaration = {'owner': 'source.identity', 'present': True, 'pointer': '/sources'}
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
            # Coverage source IDs add a namespace; the reference use keeps row['id'].
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
    return {'subject_ids': subjects, 'subject_declaration': declaration,
            'required_subject_ids': sorted(required),
            'identity_sources': extra, 'text': text, 'references': rows}


def inspect(task: dict, read, *, choices: dict | None = None,
            basis: dict | None = None, **kwargs) -> dict:
    """Show retained identity and declared bindings without claiming delivery."""
    import identity_coverage
    if choices is None:
        view = context(task, read, **kwargs)
        result = identity_coverage.inventory(task, read, context=view)
    else:
        selected, captured, current_task, view = _source_selection(task, read, choices=choices, basis=basis)
        def acquired(path):
            return captured[path] if path in captured else read(path)
        try:
            result = identity_coverage.inventory(current_task, acquired, context=view)
        except (OSError, ValueError, KeyError, TypeError) as error:
            from production_diagnostics import from_exception
            result = {'status': 'unresolved', 'sources': copy.deepcopy(selected['sources']),
                'required_subject_ids': view['required_subject_ids'],
                'requires_identity_source': 'recurring-identity' in task.get('features', []),
                'whole_reviews': [{'criterion': row['id'], 'subject_ids': row['identity_review']}
                                  for row in task.get('criteria', []) if 'identity_review' in row],
                'diagnostics': [from_exception(error, phase='identity-coverage')]}
        if selected['unresolved']:
            from production_diagnostics import ProductionError, from_exception
            result['status'] = 'unresolved'
            result.setdefault('diagnostics', []).extend(from_exception(ProductionError(
                'IDENTITY_SOURCE_UNAVAILABLE', row['message'], phase='identity-coverage',
                **{key: copy.deepcopy(value) for key, value in row.items() if key != 'message'},
                required_action='Resolve the named source selection in its existing editable owner. '
                    'Keep its acquired source bytes and assign an explicit identity use to its actual subject.'),
                phase='identity-coverage') for row in selected['unresolved'])
    result['request_verified'] = False
    result['reference_choices'] = view['references']
    return result


def source_snapshot(task: dict, read, *, choices: dict | None = None,
                    basis: dict | None = None) -> dict:
    """Acquire the current identity selection before delivery or scene coverage.

    The caller supplies one acquired read view, including unpublished projected
    bytes. Editable document and reference selections override their compiled
    copies. A retained witness is not an independently active reference. Missing
    owners remain explicit so an unfinished draft never acquires an empty
    identity selection merely because its input binding has not been built.
    """
    return _source_selection(task, read, choices=choices, basis=basis)[0]


def _source_selection(task: dict, read, *, choices: dict | None, basis: dict | None):
    """Share one current owner acquisition between retention and draft coverage."""
    import identity_coverage
    import production_identity_boundary as boundary

    result = {'sources': [], 'unresolved': []}
    reference_choices = []
    captured = {}
    failed = {}
    basis_sources = (basis or {}).get('sources') or {}
    active_task = {**task, 'sources': [source for source in task.get('sources', [])
        if (basis_sources.get(source.get('id'), {}).get('origin') or {}).get('kind')
        != 'retained-identity']}

    def acquire(path):
        if path in failed:
            raise failed[path]
        if path not in captured:
            try:
                raw = read(path)
                if not isinstance(raw, bytes):
                    raise ValueError('The source reader must return original bytes.')
                captured[path] = raw
            except (OSError, ValueError, KeyError, TypeError) as error:
                failed[path] = error
                raise
        return captured[path]

    def gap(owner, error, *, source=None, pointer=None):
        result['unresolved'].append(boundary.unknown(owner=owner, source=source,
            pointer=pointer, message=str(error)))

    def record(source, *, derived=False, owner='task.sources'):
        identity = source if derived else source.get('identity') or {}
        known = {key: copy.deepcopy(source[key]) for key in ('id', 'path', 'source_pointer') if key in source}
        known.update({key: copy.deepcopy(identity[key]) for key in
                      ('subject_ids', 'selectors', 'authority') if key in identity})
        known['derived'] = derived
        if derived and 'format' in source:
            known['format'] = source['format']
        try:
            raw = acquire(source['path'])
            known['sha256'] = c.digest(raw)
            # Keep certain byte changes even when a stale authority witness or
            # invalid selector prevents the full source record from resolving.
            kind, value = identity_coverage._source_value(raw, source['path'], source if derived else None)
            known['format'] = kind
            known['value_sha256'] = c.content_id(value)
            known['scopes'] = [{'pointer': selector, 'value_sha256': c.content_id(_pointer(value, selector))}
                               for selector in identity.get('selectors', [])]
            row = identity_coverage._source_record(source, acquire, derived=derived)
            if derived and _declared(active_task, acquire, source):
                return
            known = {key: copy.deepcopy(row[key]) for key in boundary.SOURCE_FIELDS if key in row}
        except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
            gap(owner, error, source=source.get('id'))
        result['sources'].append(known)

    for source in task.get('sources', []):
        if 'identity' not in source:
            continue
        acquired = ((basis or {}).get('sources') or {}).get(source.get('id'), {})
        if (acquired.get('origin') or {}).get('kind') == 'retained-identity':
            continue
        record(source)

    authored = (choices or {}).get('authoring') or {}
    documents = authored.get('documents') or {}

    def document(name, fallback):
        if name in documents:
            value = documents[name]
            if isinstance(value, dict) and 'file' in value:
                loaded = c.decode(acquire(value['file']))
                selected = request.get(loaded, value['field']) if value.get('field') else loaded
                return selected, value['file']
            return value, 'authoring.documents.' + name
        if choices is not None and 'authoring' in choices:
            return None, None
        if fallback:
            return c.decode(acquire(fallback)), fallback
        return None, None

    generation = task.get('generation') or {}
    specification = None
    specification_path = None
    try:
        specification, specification_path = document('production_spec', _specification_path(task))
        subjects = [row['id'] for row in specification['subjects']] if specification else []
    except (OSError, ValueError, KeyError, TypeError) as error:
        subjects = []
        gap('authoring.documents.production_spec', error)
    declaration = {'owner': 'production_spec', 'present': specification is not None, 'pointer': '/subjects'}
    if specification_path:
        declaration['file'] = specification_path
    if not subjects:
        recording = task.get('recording') or {}
        subjects = list(recording.get('subject_map', {}))
        if 'subject_map' in recording and (subjects or specification is None):
            declaration = {'owner': 'recording.subject_map', 'present': True, 'pointer': '/recording/subject_map'}
    if not subjects and task.get('artifact') != 'image':
        subjects = sorted({subject for row in task.get('sources', [])
                           for subject in (row.get('identity') or {}).get('subject_ids', [])})
        declaration = {'owner': 'source.identity', 'present': True, 'pointer': '/sources'}

    try:
        graphs, graph_path = document('state_graphs', generation.get('state_graphs'))
        if isinstance(graphs, dict):
            from state_protocol import acquire_subject_state_graphs
            graphs = acquire_subject_state_graphs(graphs, acquire, production_spec=specification)
        if graphs is not None:
            if not isinstance(graphs, list):
                raise ValueError('The selected state graphs must be an array or an explicit lineage selection.')
            if graph_path not in captured or c.decode(captured[graph_path]) != graphs:
                graph_path = 'authoring.documents.state_graphs'
                captured[graph_path] = c.encoded(graphs)
            graph_raw = acquire(graph_path)
            for index, graph in enumerate(graphs):
                try:
                    subject = graph['identity_contract']['character_id']
                    for node in IDENTITY_NODES:
                        value = graph.get(node)
                        if value is None:
                            continue
                        record({'id': 'state:' + subject + ':' + node,
                            'path': graph_path, 'source_pointer': '/' + str(index) + '/' + node,
                            'subject_ids': [subject], 'selectors': [''], 'format': 'json',
                            'sha256': c.digest(graph_raw), 'value': copy.deepcopy(value),
                            'authority': {'owner': node, 'character_id': subject,
                                          'canon_status': value.get('canon_status')}},
                            derived=True, owner='authoring.documents.state_graphs')
                except (KeyError, TypeError, ValueError) as error:
                    gap('authoring.documents.state_graphs', error, pointer='/' + str(index))
    except (OSError, ValueError, KeyError, TypeError) as error:
        gap('authoring.documents.state_graphs', error)

    def source_proof(source, witnesses, raw):
        proof = copy.deepcopy(source)
        path = proof['resolved_path']
        if proof.get('kind') == 'supplied-file':
            # These fields describe acquired bytes. A Studio adoption proof has
            # its own authority and is never rewritten by this measurement.
            proof['sha256'] = c.digest(raw)
            witness = witnesses.get(path) or {}
            if 'media_type' not in proof:
                if raw.startswith(b'\x89PNG\r\n\x1a\n'):
                    proof['media_type'] = 'image/png'
                elif raw.startswith(b'\xff\xd8\xff'):
                    proof['media_type'] = 'image/jpeg'
                elif len(raw) >= 12 and raw[:4] == b'RIFF' and raw[8:12] == b'WEBP':
                    proof['media_type'] = 'image/webp'
                elif witness.get('media_type'):
                    proof['media_type'] = witness['media_type']
                else:
                    from xml.etree import ElementTree
                    try:
                        element = ElementTree.fromstring(raw)
                        if element.tag in {'svg', '{http://www.w3.org/2000/svg}svg'}:
                            proof['media_type'] = 'image/svg+xml'
                    except ElementTree.ParseError:
                        pass
        return proof

    def reference(row, original=None, *, influences=(), witnesses=None, owner):
        ident = row.get('id')
        source_id = 'reference:' + ident if isinstance(ident, str) else None
        known = None
        try:
            controls = boundary._strings(row.get('use_for', []), 'reference use_for')
            selected = set(influences) | {use['use'] for use in row.get('subject_uses', [])}
            use = copy.deepcopy(row)
            use['use_for'] = sorted(set(controls) | selected)
            use.setdefault('do_not_transfer', [])
            boundary._strings(use['do_not_transfer'], 'reference do_not_transfer')
            assigned, identity_subjects = _reference_subjects(use, subjects)
            display = {'id': ident, 'subject_ids': assigned, 'use_for': list(use['use_for']),
                'do_not_transfer': list(use['do_not_transfer']), 'controls': controls,
                'intended_influence': sorted(selected), 'subject_uses': copy.deepcopy(row.get('subject_uses', [])),
                'source_sha256': None, 'carrier_sha256': None, 'request_fields': [], 'region_pixels': None}
            reference_choices.append(display)
            if 'identity' not in set(controls) | selected:
                # An unfinished role alone selects no identity authority. If
                # identity is explicitly selected later it is an added owner.
                return
            c.text(ident, 'reference use id')
            if selected & set(use['do_not_transfer']):
                raise ValueError('A selected reference influence is excluded by its authority.')
            if 'identity' not in use['use_for'] or 'identity' in use['do_not_transfer']:
                return
            if not identity_subjects:
                raise ValueError('The identity reference needs its actual subject assignment.')
            known = {'id': source_id, 'path': row['file'], 'subject_ids': identity_subjects,
                'selectors': [''], 'format': 'image', 'derived': True,
                'authority': {'reference': ident, 'use_for': use['use_for'], 'controls': controls,
                    'intended_influence': sorted(selected), 'do_not_transfer': copy.deepcopy(use['do_not_transfer']),
                    'subject_uses': copy.deepcopy(row.get('subject_uses', []))}}
            raw = acquire(row['file'])
            known['sha256'] = c.digest(raw)
            display['source_sha256'] = known['sha256']
            if original is not None:
                known['authority']['source'] = source_proof(original, witnesses or {}, raw)
            record({**known, 'value': None}, derived=True, owner=owner)
        except (OSError, ValueError, KeyError, TypeError) as error:
            if known is not None:
                result['sources'].append(known)
            gap(owner, error, source=source_id)

    def prepared(prepared_set, inputs, *, owner):
        native = (prepared_set or {}).get('selected_references', [])
        declared = (inputs or {}).get('references')
        originals = {reference_id(row): row for row in native}
        plan = iter(((prepared_set or {}).get('reference_use_plan') or {}).get('reference_items', []))
        plan_influences = {}
        for original in native:
            if original['source']['kind'] == 'pack-artifact':
                item = next(plan, None)
                if item is None:
                    raise ValueError('The selected pack reference needs its Reference Use Plan.')
                plan_influences[reference_id(original)] = [item['intended_influence']]
        rows = declared if declared is not None else [
            {'id': reference_id(row), 'file': row['source']['resolved_path'],
             'use_for': row['authority']['controls'], 'do_not_transfer': row['authority']['must_not_control'],
             'subject_uses': copy.deepcopy(row.get('subject_uses', []))} for row in native]
        for row in rows:
            original = originals.get(row.get('id'))
            selected = list(plan_influences.get(row.get('id'), []))
            current = copy.deepcopy(row)
            if original is not None:
                selected += original.get('intended_influence', [])
                if original.get('subject_id'):
                    current['subject_id'] = original['subject_id']
            reference(current, (original or {}).get('source'), influences=selected, owner=owner)

    def editable(selection, *, owner, portable=True):
        from production_reference_inputs import identity_selection
        native = selection.get('image_input')
        if isinstance(native, dict) and 'references' in native:
            existing = native.get('prepared_reference_set')
            if existing is None and native.get('prepared_references'):
                existing = c.decode(acquire(native['prepared_references']))
            if existing is not None:
                prepared(existing, native, owner=owner)
                return
            for row in native['references']:
                proof = ({'kind': 'supplied-file', 'reference_id': row.get('id'), 'resolved_path': row.get('file')}
                         if portable else None)
                reference(row, proof, witnesses=selection.get('source_files'), owner=owner)
            return
        for row in identity_selection(selection):
            reference({'id': row['reference_id'], 'file': row['source']['resolved_path'],
                'use_for': row['authority']['controls'], 'do_not_transfer': row['authority']['must_not_control'],
                'subject_uses': row.get('subject_uses', []),
                **({'subject_id': row['subject_id']} if row.get('subject_id') else {})},
                row['source'], influences=row.get('intended_influence', []),
                witnesses=selection.get('source_files'), owner=owner)

    external = (choices or {}).get('external') or {}
    selections = []
    if isinstance(authored.get('references'), dict):
        selections.append(('authoring.references', authored['references'], True))
    delivery = external.get('reference_delivery') or {}
    if isinstance(delivery.get('choices'), dict):
        selections.append(('external.reference_delivery.choices', delivery['choices'], True))
    elif isinstance(external.get('image_input'), dict):
        selections.append(('external.image_input', {'image_input': external['image_input']}, False))
    elif isinstance(external.get('image_input'), str):
        try:
            selected_input = c.decode(acquire(external['image_input']))
            if not isinstance(selected_input, dict):
                raise ValueError('The selected external image input must be an object.')
            selections.append(('external.image_input', {'image_input': selected_input}, False))
        except (OSError, ValueError, KeyError, TypeError) as error:
            gap('external.image_input', error)
    if selections:
        for owner, selection, portable in selections:
            try:
                editable(selection, owner=owner, portable=portable)
            except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
                gap(owner, error)
    elif choices is None or 'authoring' not in choices:
        try:
            inputs = c.decode(acquire(task['image_input'])) if task.get('image_input') else None
            selected = (inputs or {}).get('prepared_reference_set')
            path = (inputs or {}).get('prepared_references') or generation.get('references')
            if selected is None and path:
                selected = c.decode(acquire(path))
            prepared(selected, inputs, owner='task.references')
        except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
            gap('task.references', error)
    current_generation = authored.get('generation') if choices is not None and 'authoring' in choices else generation
    required = {subject for subject, continuity in (current_generation or {}).get('continuity', {}).items()
                if continuity == 'recurring'}
    required.update(subject for source in result['sources'] if source.get('derived')
                    for subject in source.get('subject_ids', []))
    visual = documents.get('visual_continuity')
    if isinstance(visual, dict) and isinstance(visual.get('subjects'), dict):
        required.update(subject for subject, value in visual['subjects'].items()
                        if value.get('continuity') == 'recurring' or value.get('identity_refs'))
    view = {'subject_ids': subjects, 'subject_declaration': declaration,
        'required_subject_ids': sorted(required), 'text': {}, 'references': reference_choices,
        'identity_sources': [copy.deepcopy(source) for source in result['sources'] if source.get('derived')]}
    return result, captured, active_task, view
