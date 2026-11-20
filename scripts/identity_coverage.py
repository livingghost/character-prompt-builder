"""Retain identity context and trace explicit scene obligations to actual input.

Selectors and scene treatments are judgments owned by task sources and criteria.
Original definitions remain the independent whole-subject comparison basis;
their values need not each become a depiction instruction or scene binding.
This module measures declared bindings, hashes and carrier equality. It neither
interprets prose or images nor certifies that a depiction preserves identity.
The returned report belongs with prepared assessment context, never model input.
"""
from __future__ import annotations

import copy
from pathlib import PurePath
from typing import Any, Callable

import execution_contract as c
from production_diagnostics import ProductionError


TREATMENTS = frozenset({'preserve', 'indirect', 'not-exposed', 'not-applicable',
                        'authorized-variation', 'unresolved'})
ACTIVE = TREATMENTS - {'not-exposed', 'not-applicable'}
DERIVED_PREFIXES = ('reference:', 'state:')
ReadSource = Callable[[str], bytes]


REPAIR = ('Correct the named criterion identity_bindings or identity_review at its authored task location. '
          'For a draft source identity, correct the public source-row descriptor and run '
          'production_workflow.py acquire-source --root STUDIO --choices CHOICES --source-row SOURCE_ROW; '
          'the acquired descriptor owns the projected source identity. A complete standalone ProductionTask '
          'owns its source rows directly. Then run check or prepare again.')


def _fail(message: str, *, code: str = 'IDENTITY_CONTRACT_INVALID',
          required_action: str = REPAIR, **details: Any) -> None:
    raise ProductionError(code, message, phase='identity-coverage', required_action=required_action, **details)


def _strings(value: Any, label: str, *, empty: bool = False) -> list[str]:
    if not isinstance(value, list) or (not empty and not value):
        _fail(label + ' must be an array' + ('.' if empty else ' with at least one item.'))
    for item in value:
        c.text(item, label)
    if len(set(value)) != len(value):
        _fail(label + ' repeats an item.')
    return value


def _tokens(pointer: Any) -> tuple[str, ...]:
    if not isinstance(pointer, str) or (pointer and not pointer.startswith('/')):
        _fail('A selector must be a JSON Pointer, using an empty string for the whole source.')
    if not pointer:
        return ()
    result = []
    for raw in pointer[1:].split('/'):
        index = 0
        while index < len(raw):
            if raw[index] == '~':
                if index + 1 == len(raw) or raw[index + 1] not in '01':
                    _fail('A JSON Pointer contains an invalid escape.', selector=pointer)
                index += 1
            index += 1
        result.append(raw.replace('~1', '/').replace('~0', '~'))
    return tuple(result)


def _pointer(tokens: tuple[str, ...]) -> str:
    return ''.join('/' + token.replace('~', '~0').replace('/', '~1') for token in tokens)


def _below(tokens: tuple[str, ...], scope: tuple[str, ...]) -> bool:
    return tokens[:len(scope)] == scope


def _selectors(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        _fail(label + ' requires at least one JSON Pointer.')
    tokens = [_tokens(pointer) for pointer in value]
    for index, current in enumerate(tokens):
        if any(_below(current, other) or _below(other, current) for other in tokens[:index]):
            _fail(label + ' contains duplicate or overlapping selectors; a subtree already includes its descendants.')
    return value


def _at(value: Any, pointer: str) -> Any:
    current = value
    for token in _tokens(pointer):
        if isinstance(current, dict) and token in current:
            current = current[token]
        elif isinstance(current, list) and token.isascii() and token.isdigit() and (
                token == '0' or not token.startswith('0')) and int(token) < len(current):
            current = current[int(token)]
        else:
            _fail('A source selector does not resolve.', code='IDENTITY_SELECTOR_MISSING', selector=pointer)
    return current


def _terminals(value: Any, tokens: tuple[str, ...] = ()):
    if isinstance(value, dict) and value:
        for key in sorted(value):
            yield from _terminals(value[key], tokens + (key,))
    elif isinstance(value, list) and value:
        for index, item in enumerate(value):
            yield from _terminals(item, tokens + (str(index),))
    else:
        # Empty collections are values too; null in opaque media is not a
        # declaration that an identity fact is absent or unresolved.
        yield _pointer(tokens), value


def _variations(task: dict) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    for variation in task.get('direction', {}).get('source_allowances', []):
        result.setdefault(variation['id'], []).append(variation)
    return result


def _variation(task: dict, criterion: dict, binding: dict, source: dict | None = None) -> dict | None:
    ident = binding['variation']
    if binding['treatment'] != 'authorized-variation':
        if ident is not None:
            _fail('Only an authorized-variation treatment may name an accepted variation.')
        return None
    c.text(ident, 'accepted variation id')
    matches = _variations(task).get(ident, [])
    if len(matches) != 1:
        _fail('An identity variation must resolve one existing accepted variation.', variation=ident)
    variation = matches[0]
    from production_plan import validate_source_allowances
    applied = {row['id'] for row in task['sources'] if row.get('disposition') == 'applied'}
    validate_source_allowances([variation], applied, {row['id'] for row in task['criteria']},
                               task_id=task.get('task_id'))
    if criterion['id'] not in variation['criteria']:
        _fail('The accepted variation does not govern this identity criterion.', variation=ident)
    scope = variation['scope']
    if scope['kind'] == 'source':
        if scope['source'] != binding['source']:
            _fail('The accepted variation governs another source.', variation=ident)
        if source is not None and scope['sha256'] != source['sha256']:
            _fail('The accepted variation source changed; reassess its existing scope.',
                  code='IDENTITY_SOURCE_CHANGED', variation=ident)
    return variation


def _criterion_strength(task: dict, criterion: dict) -> None:
    if criterion.get('strength') != 'hard' or (
            task.get('artifact') == 'image' and criterion.get('evidence') != 'image'):
        _fail('An active identity obligation or whole-subject review requires a hard criterion '
              'and image evidence for an image task.', criterion=criterion.get('id'))


def _authority(value: Any, subjects: list[str], *, source: str) -> None:
    """Validate retained owner scope without treating it as a current reference use."""
    if not isinstance(value, dict):
        _fail('Retained identity authority must be an object.', source=source)
    if 'reference' in value:
        fields = {'reference', 'use_for', 'controls', 'intended_influence', 'do_not_transfer', 'subject_uses'}
        c.exact(value, fields | ({'source'} if 'source' in value else set()), 'identity reference authority')
        reference = c.text(value['reference'], 'identity authority reference')
        if source.startswith('reference:') and source != 'reference:' + reference:
            _fail('Retained reference authority names another source.', source=source)
        for field in ('use_for', 'controls', 'intended_influence', 'do_not_transfer'):
            _strings(value[field], 'identity authority ' + field,
                     empty=field in {'intended_influence', 'do_not_transfer'})
        from reference_contract import INTENDED_INFLUENCES
        if set(value['intended_influence']) - set(INTENDED_INFLUENCES):
            _fail('Retained reference authority names an unknown influence.', source=source)
        if 'identity' not in value['use_for'] or 'identity' in value['do_not_transfer']:
            _fail('Retained reference authority does not include identity influence.', source=source)
        from reference_delivery import validate_subject_uses
        uses = validate_subject_uses(value['subject_uses'],
                                    allowed_uses=set(value['intended_influence']) | set(value['use_for']))
        assigned = {row['subject_id'] for row in uses if row['use'] == 'identity'}
        if not assigned <= set(subjects):
            _fail('Retained identity authority differs from its subject assignment.', source=source)
        if 'source' in value:
            from state_protocol import validate_against_schema
            schema = {'oneOf': [{'$ref': 'prepared-generation-reference.schema.json#/$defs/' + kind}
                               for kind in ('pack-artifact-source', 'supplied-file-source',
                                            'studio-artifact-source', 'studio-accepted-image-source')]}
            errors = validate_against_schema(value['source'], schema)
            if errors:
                _fail('Retained reference authority has an invalid original source.', source=source, errors=errors)
    else:
        c.exact(value, {'owner', 'character_id', 'canon_status'}, 'identity graph authority')
        c.text(value['owner'], 'identity authority graph owner')
        character = c.text(value['character_id'], 'identity authority character')
        if set(subjects) != {character}:
            _fail('Retained graph authority differs from its character assignment.', source=source)
        if value['canon_status'] is not None:
            c.text(value['canon_status'], 'identity authority canon status')


def _authority_source(authority: dict, record: dict, raw: bytes) -> None:
    """Bind retained scope to its original media or graph owner bytes."""
    if 'reference' in authority:
        original = authority.get('source')
        if original is not None and original['sha256'] != record['sha256']:
            _fail('Retained reference authority differs from the original source bytes.',
                  code='IDENTITY_SOURCE_CHANGED', source=record['id'])
        return
    if record['format'] != 'json':
        _fail('Retained graph authority requires its original JSON graph.', source=record['id'])
    graphs = c.decode(raw)
    for selector in record['selectors']:
        tokens = _tokens(record['source_pointer'] + selector)
        if (len(tokens) < 2 or tokens[1] != authority['owner']
                or not isinstance(graphs, list)):
            _fail('Retained graph authority does not own the selected source scope.', source=record['id'])
        graph = _at(graphs, _pointer(tokens[:1]))
        if (not isinstance(graph, dict)
                or (graph.get('identity_contract') or {}).get('character_id') != authority['character_id']
                or not isinstance(graph.get(authority['owner']), dict)
                or graph[authority['owner']].get('canon_status') != authority['canon_status']):
            _fail('Retained graph authority differs from its original owner.',
                  code='IDENTITY_SOURCE_CHANGED', source=record['id'])


def _validate_task(task: dict) -> None:
    sources = {}
    for source in task.get('sources', []):
        ident = c.text(source['id'], 'source id')
        if ident in sources:
            _fail('Task source IDs must be unique.', source=ident)
        sources[ident] = source
        if 'identity' in source:
            identity = source['identity']
            fields = {'subject_ids', 'selectors'}
            c.exact(identity, fields | ({'authority'} if isinstance(identity, dict) and 'authority' in identity else set()),
                    'source identity')
            subjects = _strings(identity['subject_ids'], 'identity subject IDs')
            _selectors(identity['selectors'], 'source identity selectors')
            if 'authority' in identity:
                _authority(identity['authority'], subjects, source=ident)
            if source.get('disposition') != 'applied':
                _fail('An identity source must be applied as retained comparison context; '
                      'criterion bindings describe explicit scene obligations.',
                      source=ident)
    criterion_ids = set()
    for criterion_index, criterion in enumerate(task.get('criteria', [])):
        ident = c.text(criterion['id'], 'criterion id')
        if ident in criterion_ids:
            _fail('Task criterion IDs must be unique.', criterion=ident)
        criterion_ids.add(ident)
        if 'identity_review' in criterion:
            _strings(criterion['identity_review'], 'whole-review subject IDs')
            _criterion_strength(task, criterion)
        bindings = criterion.get('identity_bindings', [])
        if not isinstance(bindings, list):
            _fail('identity_bindings must be an array.', criterion=ident)
        seen = set()
        for binding_index, binding in enumerate(bindings):
            c.exact(binding, {'source', 'subject_ids', 'selectors', 'treatment', 'reason', 'carriers', 'variation'},
                    'identity binding')
            source_id = c.text(binding['source'], 'identity binding source')
            source = sources.get(source_id)
            binding_pointer = '/criteria/' + str(criterion_index) + '/identity_bindings/' + str(binding_index)
            if source is None and not source_id.startswith(DERIVED_PREFIXES):
                _fail('An identity binding names an unknown source.', source=source_id, criterion=ident,
                      cause='identity-binding-source-unknown', pointer=binding_pointer + '/source',
                      repair_owner={'kind': 'criterion', 'pointer': binding_pointer + '/source'},
                      required_action='Set this criterion binding source to its intended applied source ID, '
                          'or acquire that source through acquire-source before binding it. '
                          'For draft criteria, edit authoring.task.criteria in choices.json.')
            if source is not None and 'identity' not in source:
                _fail('An identity binding requires the source identity selection.', source=source_id,
                      criterion=ident, cause='source-identity-not-declared',
                      pointer=binding_pointer + '/source')
            subjects = _strings(binding['subject_ids'], 'binding subject IDs')
            if source is not None and set(subjects) - set(source['identity']['subject_ids']):
                _fail('An identity binding exceeds its source subject scope.', source=source_id,
                      criterion=ident, cause='identity-binding-subject-scope',
                      pointer=binding_pointer + '/subject_ids',
                      expected_subject_ids=source['identity']['subject_ids'], actual_subject_ids=subjects,
                      repair_owner={'kind': 'criterion', 'pointer': binding_pointer + '/subject_ids'},
                      required_action='Bind only subjects within the selected source identity scope. '
                          'If the source scope itself was selected incorrectly, reacquire its Production '
                          'source-row descriptor using the actual source authority before checking again.')
            _selectors(binding['selectors'], 'binding selectors')
            if binding['treatment'] not in TREATMENTS:
                _fail('Unknown identity scene treatment.')
            c.text(binding['reason'], 'identity treatment reason')
            if binding['treatment'] in ACTIVE:
                _criterion_strength(task, criterion)
            if not isinstance(binding['carriers'], list):
                _fail('Identity carriers must be an array.')
            carrier_ids = set()
            for carrier in binding['carriers']:
                if not isinstance(carrier, dict):
                    _fail('An identity carrier must be an object.')
                if carrier.get('kind') == 'text':
                    selector='selection' if 'selection' in carrier else 'quote'
                    c.exact(carrier, {'kind', 'surface', selector}, 'identity text carrier')
                    if carrier['surface'] not in {'primary', 'negative'}:
                        _fail('A text carrier must select the actual primary or negative surface.')
                    if selector=='quote':
                        c.text(carrier['quote'], 'identity carrier quote')
                    else:
                        selection=carrier['selection']
                        if selection=={'whole':True}:
                            pass
                        elif isinstance(selection,dict) and set(selection)<= {'text','occurrence'} and 'text' in selection:
                            c.text(selection['text'],'selected carrier text')
                            if 'occurrence' in selection and (type(selection['occurrence']) is not int or selection['occurrence']<1):
                                _fail('Text selection occurrence must be a positive integer.')
                        else:
                            _fail('Select the whole text surface or an exact text occurrence.')
                elif carrier.get('kind') == 'reference':
                    c.exact(carrier, {'kind', 'reference', 'use'}, 'identity reference carrier')
                    c.text(carrier['reference'], 'identity reference id')
                    c.text(carrier['use'], 'identity reference influence')
                else:
                    _fail('An identity carrier must be text or reference media.')
                key = c.content_id(carrier)
                if key in carrier_ids:
                    _fail('An identity binding repeats a carrier.')
                carrier_ids.add(key)
            _variation(task, criterion, binding)
            key = c.content_id({**binding, 'subject_ids': sorted(subjects),
                                'selectors': sorted(binding['selectors'])})
            if key in seen:
                _fail('A criterion repeats an identity binding.', criterion=ident)
            seen.add(key)


def validate_task(task: dict) -> None:
    """Validate authored structure; derived source IDs resolve during inventory."""
    try:
        _validate_task(task)
    except ProductionError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        _fail(str(error))


def _source_value(raw: bytes, path: str, derived: dict | None) -> tuple[str, Any]:
    declared = derived.get('format') if derived is not None else None
    if declared not in {None, 'json', 'text', 'image'}:
        _fail('A derived identity source has an unknown format.')
    if declared == 'image':
        if derived.get('value') is not None:
            _fail('An image identity source carries original media, not invented extracted facts.')
        return 'image', None
    if declared == 'text':
        value = raw.decode('utf-8')
        kind = 'text'
    else:
        try:
            value = c.decode(raw)
            kind = 'json'
        except (UnicodeError, ValueError):
            if declared == 'json' or PurePath(path).suffix.lower() == '.json':
                _fail('An identity JSON source cannot be decoded.', source_path=path)
            try:
                value = raw.decode('utf-8')
                kind = 'text'
            except UnicodeError:
                value, kind = None, 'media'
    if derived is not None:
        origin = derived.get('source_pointer', '')
        if kind != 'json' and origin:
            _fail('Only a JSON source can select a node inside its original file.')
        value = _at(value, origin)
        if 'value' in derived and not c.content_id(value) == c.content_id(derived['value']):
            _fail('The derived identity source value differs from its original file and pointer.',
                  code='IDENTITY_SOURCE_CHANGED', source=derived['id'])
    return kind, value


def _source_record(source: dict, read_source: ReadSource, *, derived: bool = False) -> dict:
    path = c.text(source['path'], 'identity source path')
    raw = read_source(path)
    if not isinstance(raw, bytes):
        _fail('The identity source reader must return original bytes.', source=source['id'])
    digest = c.digest(raw)
    if derived and c.sha(source['sha256']) != digest:
        _fail('An original identity source changed after context capture.',
              code='IDENTITY_SOURCE_CHANGED', source=source['id'])
    identity = source if derived else source['identity']
    subjects = _strings(identity['subject_ids'], 'identity subject IDs')
    selectors = _selectors(identity['selectors'], 'source identity selectors')
    kind, value = _source_value(raw, path, source if derived else None)
    scopes, terminals = [], []
    for selector in selectors:
        if kind != 'json' and selector:
            _fail('Text and media identity sources use the whole-source selector.', source=source['id'])
        selected = _at(value, selector)
        scopes.append({'pointer': selector, 'value_sha256': c.content_id(selected)})
        for pointer, item in _terminals(selected, _tokens(selector)):
            terminals.append({'pointer': pointer, 'value': copy.deepcopy(item),
                              'value_sha256': c.content_id(item), 'coverage': []})
    result = {'id': source['id'], 'path': path, 'format': kind, 'sha256': digest,
              'value_sha256': c.content_id(value), 'source_pointer': source.get('source_pointer', '') if derived else '',
              'subject_ids': list(subjects), 'selectors': list(selectors), 'scopes': scopes,
              'terminals': terminals, 'derived': derived}
    if 'authority' in identity:
        _authority(identity['authority'], subjects, source=source['id'])
        _authority_source(identity['authority'], result, raw)
        result['authority'] = copy.deepcopy(identity['authority'])
    return result


def _inventory(task: dict, read_source: ReadSource, context: dict) -> dict:
    validate_task(task)
    sources = {source['id']: _source_record(source, read_source)
               for source in task.get('sources', []) if 'identity' in source}
    for source in context.get('identity_sources', []):
        ident = c.text(source['id'], 'derived source id')
        if not ident.startswith(DERIVED_PREFIXES) or ident in sources:
            _fail('Derived identity sources need distinct reference: or state: IDs.', source=ident)
        if any(row['id'] == ident for row in task.get('sources', [])):
            _fail('A derived identity source ID collides with a task source.', source=ident)
        sources[ident] = _source_record(source, read_source, derived=True)
    subjects = {subject for source in sources.values() for subject in source['subject_ids']}
    actual = set(_strings(context.get('subject_ids', []), 'actual subject IDs', empty=True))
    required = set(_strings(context.get('required_subject_ids', []), 'required identity subject IDs', empty=True))
    bindings, whole_reviews, unresolved, missing_carriers = [], [], [], []
    by_terminal: dict[tuple[str, str, str], list[tuple[int, int]]] = {}
    for criterion in task.get('criteria', []):
        if 'identity_review' in criterion:
            whole_reviews.append({'criterion': criterion['id'], 'subject_ids': list(criterion['identity_review'])})
        for number, binding in enumerate(criterion.get('identity_bindings', [])):
            source = sources.get(binding['source'])
            if source is None:
                _fail('An identity binding does not resolve an original source.',
                      code='IDENTITY_SOURCE_MISSING', source=binding['source'])
            if set(binding['subject_ids']) - set(source['subject_ids']):
                _fail('An identity binding exceeds its source subject scope.', source=source['id'])
            selected: dict[str, int] = {}
            for selector in binding['selectors']:
                tokens = _tokens(selector)
                if not any(_below(tokens, _tokens(scope)) for scope in source['selectors']):
                    _fail('A criterion selector exceeds the declared identity source scope.',
                          source=source['id'], selector=selector)
                matching = [row['pointer'] for row in source['terminals'] if _below(_tokens(row['pointer']), tokens)]
                if not matching:
                    _fail('A criterion selector does not resolve an inventoried value.',
                          code='IDENTITY_SELECTOR_MISSING', source=source['id'], selector=selector)
                for pointer in matching:
                    selected[pointer] = len(tokens)
            _variation(task, criterion, binding, source)
            row = {'criterion': criterion['id'], 'binding_index': number, **copy.deepcopy(binding),
                   'source_sha256': source['sha256'], 'terminals': sorted(selected)}
            index = len(bindings)
            bindings.append(row)
            for pointer, specificity in selected.items():
                for subject in binding['subject_ids']:
                    by_terminal.setdefault((source['id'], pointer, subject), []).append((specificity, index))
            if binding['treatment'] in ACTIVE and not binding['carriers']:
                missing_carriers.append({'criterion': criterion['id'], 'binding_index': number})
            if binding['treatment'] == 'unresolved':
                unresolved.append({'criterion': criterion['id'], 'binding_index': number,
                                   'source': source['id'], 'reason': binding['reason']})
    unbound_source_values = []
    for source in sources.values():
        for terminal in source['terminals']:
            unbound_subjects = []
            for subject in source['subject_ids']:
                candidates = by_terminal.get((source['id'], terminal['pointer'], subject), [])
                if not candidates:
                    unbound_subjects.append(subject)
                    continue
                specificity = max(level for level, _ in candidates)
                effective = [index for level, index in candidates if level == specificity]
                meanings = {(bindings[index]['treatment'], bindings[index]['variation']) for index in effective}
                if len(meanings) != 1:
                    _fail('Equally specific identity bindings have conflicting scene treatments.',
                          code='IDENTITY_TREATMENT_CONFLICT', source=source['id'],
                          selector=terminal['pointer'], subject_id=subject)
                terminal['coverage'].append({'subject_id': subject, 'bindings': effective,
                    'treatment': bindings[effective[0]]['treatment'], 'variation': bindings[effective[0]]['variation']})
            if unbound_subjects:
                unbound_source_values.append({'source': source['id'], 'pointer': terminal['pointer'],
                                              'subject_ids': unbound_subjects})
    reviewed = {subject for row in whole_reviews for subject in row['subject_ids']}
    unknown = (subjects | reviewed | required) - actual if 'subject_ids' in context else reviewed - subjects
    return {'artifact_type': 'identity-coverage', 'structural_only': True, 'status': 'inventory',
            'sources': list(sources.values()), 'bindings': bindings, 'whole_reviews': whole_reviews,
            'subject_ids': sorted(subjects), 'actual_subject_ids': sorted(actual),
            **({'subject_declaration': copy.deepcopy(context['subject_declaration'])}
               if 'subject_declaration' in context else {}),
            'required_subject_ids': sorted(required), 'unbound_source_values': unbound_source_values,
            'unresolved': unresolved,
            'missing_carriers': missing_carriers, 'missing_subject_sources': sorted(required - subjects),
            'missing_whole_reviews': sorted((subjects | required) - reviewed),
            'unknown_subject_ids': sorted(unknown),
            'requires_identity_source': 'recurring-identity' in task.get('features', []) and not sources}


def inventory(task: dict, read_source: ReadSource, *, context: dict | None = None) -> dict:
    """Return original context, declared obligations and structural review gaps.

The caller reads committed original bytes. Optional derived sources retain their
original path/hash and a source_pointer when their value is a JSON graph node.
Unbound source values remain comparison context; they are not missing depiction
instructions, visibility decisions or findings of correctness. Explicit bindings
and whole-subject review requirements remain available for normal authoring.
"""
    try:
        return _inventory(task, read_source, context or {})
    except ProductionError:
        raise
    except (KeyError, TypeError, ValueError, OSError) as error:
        _fail(str(error))


def _field(value: Any) -> list[str | int]:
    if not isinstance(value, list) or not value or any(
            not isinstance(item, (str, int)) or isinstance(item, bool) or
            (isinstance(item, int) and item < 0) for item in value):
        _fail('An actual input carrier needs its concrete request field path.')
    return value


def _text_carrier(carrier: dict, context: dict) -> dict:
    surface = context.get('text', {}).get(carrier['surface'])
    if not isinstance(surface, dict) or not isinstance(surface.get('text'), str):
        _fail('The claimed text surface is absent from the actual model input.', code='IDENTITY_CARRIER_MISSING')
    text=surface['text']
    selection=carrier.get('selection')
    quote=(text if selection=={'whole':True} else selection['text']) if selection is not None else carrier['quote']
    field = _field(surface.get('field'))
    digest = c.digest(text.encode('utf-8'))
    if c.sha(surface.get('sha256')) != digest:
        _fail('The actual text surface hash differs from its supplied bytes.', code='IDENTITY_CARRIER_CHANGED')
    starts, offset = [], 0
    while (offset := text.find(quote, offset)) != -1:
        starts.append([offset, offset + len(quote)])
        offset += 1
    if not starts:
        _fail('An identity text quote is absent from the actual model input.', code='IDENTITY_CARRIER_MISSING')
    if selection is not None:
        occurrence=selection.get('occurrence')
        if occurrence is not None:
            if occurrence>len(starts):
                _fail('The selected text occurrence is absent.',code='IDENTITY_CARRIER_MISSING')
            starts=[starts[occurrence-1]]
        elif len(starts)!=1:
            _fail('The text selection is ambiguous; select its occurrence.',code='IDENTITY_CARRIER_MISSING')
    ranges=[[len(text[:start].encode('utf-8')),len(text[:end].encode('utf-8'))] for start,end in starts]
    return {**carrier,'quote':quote, 'field': copy.deepcopy(field), 'surface_sha256': digest,
            'ranges': ranges, 'range_unit': 'utf-8-bytes'}


def _reference_carrier(carrier: dict, binding: dict, references: dict) -> dict:
    reference = references.get(carrier['reference'])
    if reference is None:
        _fail('An identity reference is absent from the actual model input.', code='IDENTITY_CARRIER_MISSING',
              reference=carrier['reference'])
    use = carrier['use']
    uses = _strings(reference.get('use_for', []), 'reference allowed uses', empty=True)
    excluded = _strings(reference.get('do_not_transfer', []), 'reference excluded uses', empty=True)
    if use not in uses or use in excluded:
        _fail('The actual reference does not permit the selected influence.', code='IDENTITY_REFERENCE_SCOPE',
              reference=carrier['reference'], use=use)
    subjects = set(_strings(reference.get('subject_ids', []), 'reference subject IDs', empty=True))
    subject_uses = reference.get('subject_uses', [])
    if not isinstance(subject_uses, list):
        _fail('Actual reference subject uses must be an array.')
    assigned = set()
    for row in subject_uses:
        c.exact(row, {'subject_id', 'use', 'priority'}, 'actual reference subject use')
        c.text(row['subject_id'], 'reference subject id')
        c.text(row['use'], 'reference use')
        if type(row['priority']) is not int or row['priority'] < 0:
            _fail('Actual reference subject priorities must be nonnegative integers.')
        if (row['subject_id'], row['use']) in assigned:
            _fail('An actual reference repeats a subject/use assignment.')
        assigned.add((row['subject_id'], row['use']))
    covered = [subject for subject in binding['subject_ids']
               if subject in subjects and (not subject_uses or (subject, use) in assigned)]
    if not covered:
        _fail('The actual reference influence is not assigned to any subject of this binding.',
              code='IDENTITY_REFERENCE_SUBJECT', reference=carrier['reference'],
              subject_ids=binding['subject_ids'])
    source_hash, carrier_hash = c.sha(reference.get('source_sha256')), c.sha(reference.get('carrier_sha256'))
    fields = reference.get('request_fields')
    if not isinstance(fields, list) or not fields:
        _fail('An identity reference has no attached request field.', code='IDENTITY_CARRIER_MISSING')
    for field in fields:
        _field(field)
    return {**carrier, 'subject_ids': covered, 'reference_source_sha256': source_hash,
            'carrier_sha256': carrier_hash, 'request_fields': copy.deepcopy(fields),
            'region_pixels': copy.deepcopy(reference.get('region_pixels')),
            'derivation': copy.deepcopy(reference.get('derivation')),
            'use_for': list(uses), 'do_not_transfer': list(excluded), 'subject_uses': copy.deepcopy(subject_uses),
            **{key: copy.deepcopy(reference[key]) for key in ('controls', 'intended_influence') if key in reference}}


def subject_gap(report: dict) -> dict:
    """Explain absent input declarations separately from a declared scope mismatch.

    Only the adapter knows which existing input declared the actual subjects.
    Source names and prompt prose never supply that declaration implicitly.
    """
    declaration = copy.deepcopy(report.get('subject_declaration') or {})
    missing = declaration.get('present') is False
    owner = declaration.get('owner')
    location = ('Production Specification /subjects' if owner == 'production_spec' else
                'task recording.subject_map' if owner == 'recording.subject_map' else
                'actual input subject declaration')
    if missing:
        message = 'Identity sources or reviews name subjects, but this image input has no subject declaration.'
        repair = ('Declare the actual image subjects in a selected Production Specification at /subjects. '
                  'Use production_document_contracts.py explain production_spec --pointer /properties/subjects/items '
                  'and the existing production_spec.py draft owner. Acquired source assignments and prompt '
                  'text do not declare the image subjects.')
    else:
        message = 'Identity sources or reviews name subjects outside the declared subject scope.'
        repair = ('Compare ' + location + ' with the listed unknown IDs and actual_subject_ids. Correct the '
                  'mistaken input declaration or the source/criterion subject scope at its existing owner. '
                  'For an acquired draft source, correct its public source-row descriptor and reacquire it '
                  'with acquire-source; do not edit a projected source row.')
    result = {'cause': 'input-subject-declaration-missing' if missing else 'identity-subject-scope-mismatch',
              'message': message, 'required_action': repair,
              'actual_subject_ids': list(report.get('actual_subject_ids', [])),
              **({'subject_declaration': declaration, 'repair_owner': copy.deepcopy(declaration)}
                 if declaration else {})}
    if owner == 'production_spec':
        import production_document_contracts as contracts
        result['guidance'] = contracts.guidance('production_spec')
        result['schema_pointer'] = '/properties/subjects/items'
        result['schema_action'] = contracts.explain_action('production_spec', result['schema_pointer'])
        result['next_action'] = result['schema_action']
    elif owner == 'recording.subject_map':
        result['guidance'] = {'document_path': 'references/character-identity-contract.md#source-to-input-and-review-coverage',
                              'schema': 'schemas/authoring/production-task.schema.json'}
        result['schema_pointer'] = '/properties/recording/properties/subject_map'
    return result


def compile(task: dict, read_source: ReadSource, *, context: dict) -> dict:
    """Verify explicit obligations and retain their complete source context.

Context contains subject_ids, required_subject_ids, optional identity_sources,
text.{primary,negative} ({text, field, sha256}), and references carrying stable
IDs, subject/use scopes, original/delivered hashes and concrete request fields.
Values without an explicit binding remain in the whole-subject comparison basis.
A verified binding still needs independent rendition and candidate assessment.
"""
    report = inventory(task, read_source, context=context)
    gaps = {key: report[key] for key in ('missing_carriers', 'missing_subject_sources',
             'missing_whole_reviews', 'unknown_subject_ids', 'requires_identity_source') if report[key]}
    if gaps:
        if report['unknown_subject_ids']:
            diagnostic = subject_gap(report)
            _fail(diagnostic.pop('message'), code='IDENTITY_COVERAGE_INCOMPLETE',
                  gaps=gaps, **diagnostic)
        _fail('An explicit identity obligation or its independent review basis is incomplete.',
              code='IDENTITY_COVERAGE_INCOMPLETE', gaps=gaps)
    try:
        references = {}
        for reference in context.get('references', []):
            ident = c.text(reference['id'], 'actual reference id')
            if ident in references:
                _fail('Actual logical reference IDs must be unique.', reference=ident)
            references[ident] = reference
        for binding in report['bindings']:
            binding['carriers'] = [
                {**_text_carrier(carrier, context), 'subject_ids': list(binding['subject_ids'])}
                if carrier['kind'] == 'text' else
                _reference_carrier(carrier, binding, references)
                for carrier in binding['carriers']]
            covered = {subject for carrier in binding['carriers'] for subject in carrier['subject_ids']}
            missing = set(binding['subject_ids']) - covered
            if binding['treatment'] in ACTIVE and missing:
                _fail('Actual identity carriers do not cover every subject of this binding.',
                      code='IDENTITY_REFERENCE_SUBJECT', criterion=binding['criterion'],
                      binding_index=binding['binding_index'], subject_ids=sorted(missing))
    except ProductionError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        _fail(str(error))
    report['status'] = 'bindings-verified'
    return report


validate = compile
