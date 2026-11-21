"""Compare acquired identity selections without reading or changing their owners.

An amend retains a registered source selection. A compose owns a new current
selection. These comparisons establish content and scope equality, not source
approval, execution authority or the quality of a depiction.
"""
from __future__ import annotations

import copy
from typing import Any

import execution_contract as c
from production_diagnostics import ProductionError


GUIDANCE = {'document_path': 'references/runtime/production-authoring.md#keep-branches-and-reopen-completed-work'}
SOURCE_FIELDS = ('id', 'path', 'sha256', 'format', 'source_pointer', 'subject_ids',
                 'selectors', 'authority', 'derived', 'value_sha256', 'scopes')


def unknown(*, owner: str, message: str, source: str | None = None,
            pointer: str | None = None, **details: Any) -> dict:
    """Keep an unresolved owner visible instead of certifying an empty selection."""
    return {'owner': owner, 'message': message,
            **({'source': source} if source is not None else {}),
            **({'pointer': pointer} if pointer is not None else {}), **details}


def from_coverage(value: dict | None) -> dict:
    """Retain acquired source rows independently of scene coverage completeness."""
    if not isinstance(value, dict):
        return {'sources': [], 'unresolved': [unknown(owner='retained_identity_sources',
            message='The retained identity selection has not been acquired.')]}
    sources = value.get('sources')
    unresolved = copy.deepcopy(value.get('unresolved', [])) if 'bindings' not in value else []
    if not isinstance(sources, list):
        sources = []
        unresolved.append(unknown(owner='retained_identity_sources',
            message='The retained identity source inventory is unavailable.'))
    unresolved.extend(copy.deepcopy(value.get('diagnostics', [])))
    acquired = []
    for row in sources:
        if not isinstance(row, dict):
            unresolved.append(unknown(owner='retained_identity_sources',
                message='A retained identity source record is invalid.'))
            continue
        acquired.append({key: copy.deepcopy(row[key]) for key in SOURCE_FIELDS if key in row})
    return {'sources': acquired, 'unresolved': unresolved}


def _strings(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(field + ' must be an array of strings')
    if len(value) != len(set(value)):
        raise ValueError(field + ' repeats a value')
    return sorted(value)


def _pointer(value: str) -> str:
    from identity_coverage import _tokens
    return ''.join('/' + token.replace('~', '~0').replace('/', '~1') for token in _tokens(value))


def _authority(value: Any) -> Any:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError('identity authority must be an object')
    result = copy.deepcopy(value)
    for field in ('use_for', 'controls', 'intended_influence', 'do_not_transfer'):
        if field in result:
            result[field] = _strings(result[field], 'authority.' + field)
    if 'subject_uses' in result:
        rows = result['subject_uses']
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError('authority.subject_uses must be an array of objects')
        result['subject_uses'] = sorted(rows, key=c.content_id)
    if isinstance(result.get('source'), dict):
        # The source kind, stable owner, content and acceptance proof remain.
        # This locator only tells the reader where the same evidence is held.
        result['source'].pop('resolved_path', None)
    return result


def normalize_source(source: dict) -> dict:
    """Compare original scope across direct, derived and relocated representations."""
    if not isinstance(source, dict):
        raise ValueError('identity source must be an object')
    ident = c.text(source.get('id'), 'identity source id')
    digest = source.get('sha256')
    if digest is not None:
        c.sha(digest)
    prefix = _pointer(source.get('source_pointer', ''))
    relative = _strings(source.get('selectors', []), 'identity selectors')
    selectors = sorted(_pointer(prefix + _pointer(value)) for value in relative)
    kind = source.get('format')
    if kind in {'image', 'media'}:
        kind = 'binary'
    result = {'id': ident, 'sha256': digest, 'format': kind,
            'subject_ids': _strings(source.get('subject_ids', []), 'identity subject ids'),
            'selectors': selectors, 'authority': _authority(source.get('authority'))}
    authority = result['authority'] or {}
    if 'owner' in authority and 'character_id' in authority:
        # A graph is a container for independently owned nodes, including
        # editable scene state. Compare the selected identity owner values and
        # retain the container digest as evidence rather than freezing its scene.
        from identity_coverage import _tokens
        scopes = {row['pointer']: row['value_sha256'] for row in source.get('scopes', [])}
        if not scopes and relative == [''] and source.get('value_sha256') is not None:
            scopes[''] = source['value_sha256']
        owned = []
        for relative_pointer in relative:
            tokens = _tokens(prefix + _pointer(relative_pointer))
            if len(tokens) < 2 or not tokens[0].isdigit() or tokens[1] != authority['owner']:
                result['value_sha256'] = None
                result['unresolved'] = 'The graph identity scope does not identify its declared owner.'
                return result
            selected_hash = scopes.get(relative_pointer)
            if selected_hash is None:
                result['unresolved'] = 'The selected graph identity owner value has not been acquired.'
            else:
                c.sha(selected_hash)
            pointer = ''.join('/' + token.replace('~', '~0').replace('/', '~1') for token in tokens[1:])
            owned.append({'pointer': pointer, 'sha256': selected_hash})
        owned.sort(key=lambda row: row['pointer'])
        result['selectors'] = [row['pointer'] for row in owned]
        result['value_sha256'] = None if 'unresolved' in result else c.content_id(owned)
    return result


def _comparison_key(source: dict) -> dict:
    result = copy.deepcopy(source)
    if 'value_sha256' in result:
        result.pop('sha256', None)
    return result


def _index(snapshot: Any, *, side: str) -> tuple[dict[str, list[dict]], list[dict]]:
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get('sources'), list):
        return {}, [unknown(owner=side, comparison_side=side,
                            message='The identity selection has not been acquired.')]
    unresolved = copy.deepcopy(snapshot.get('unresolved', []))
    if not isinstance(unresolved, list):
        unresolved = [unknown(owner=side, message='The unresolved identity owners are invalid.')]
    result: dict[str, list[dict]] = {}
    for row in snapshot['sources']:
        try:
            normalized = normalize_source(row)
        except (TypeError, ValueError, KeyError) as error:
            unresolved.append(unknown(owner=side, source=row.get('id') if isinstance(row, dict) else None,
                message=str(error)))
            continue
        if normalized.get('unresolved'):
            unresolved.append(unknown(owner=side, source=normalized['id'], message=normalized.pop('unresolved')))
        variants = result.setdefault(normalized['id'], [])
        if not any(_comparison_key(normalized) == _comparison_key(other) for other in variants):
            variants.append(normalized)
        if normalized['sha256'] is None:
            unresolved.append(unknown(owner=side, source=normalized['id'],
                message='The selected identity source bytes have not been acquired.'))
    return result, [{**row, 'comparison_side': side} for row in unresolved]


def compare(retained: dict, proposed: dict) -> dict:
    """Return every certain source change and each unresolved comparison owner."""
    previous, old_gaps = _index(retained, side='retained_identity_sources')
    current, new_gaps = _index(proposed, side='current_identity_sources')
    changes = []

    def uncertain(gaps, ident):
        return any(not row.get('source') or row['source'] == ident for row in gaps)

    def change(ident, kind, before, after):
        value = {'source': ident, 'change_kind': kind,
                 'before': copy.deepcopy(before), 'after': copy.deepcopy(after)}
        if value not in changes:
            changes.append(value)

    for ident in sorted(set(previous) - set(current)):
        if not uncertain(new_gaps, ident):
            change(ident, 'removed', previous[ident][0], None)
    for ident in sorted(set(current) - set(previous)):
        if not uncertain(old_gaps, ident):
            change(ident, 'added', None, current[ident][0])
    for ident in sorted(set(previous) & set(current)):
        if len(previous[ident]) != 1:
            old_gaps.append(unknown(owner='retained_identity_sources', source=ident,
                message='The retained source ID has conflicting acquired owners.'))
            continue
        before = previous[ident][0]
        for after in current[ident]:
            previous_hash = before.get('value_sha256', before['sha256'])
            current_hash = after.get('value_sha256', after['sha256'])
            if (('value_sha256' in before) == ('value_sha256' in after)
                    and previous_hash is not None and current_hash is not None
                    and (previous_hash, before['format']) != (current_hash, after['format'])):
                change(ident, 'content', {key: before[key] for key in ('sha256', 'format', 'value_sha256') if key in before},
                       {key: after[key] for key in ('sha256', 'format', 'value_sha256') if key in after})
            for field, kind in (('selectors', 'scope'), ('subject_ids', 'subjects'), ('authority', 'authority')):
                if before[field] != after[field]:
                    change(ident, kind, before[field], after[field])
    return {'changes': changes, 'unresolved': old_gaps + new_gaps}


def require_unchanged(context: dict, basis: dict, proposed: dict, *, file: str | None = None) -> None:
    """Enforce the registered operation and its retained amend source selection."""
    operation = (context.get('authoring_work') or {}).get('operation')
    if operation not in {'compose', 'amend'} or basis.get('operation') != operation:
        raise ProductionError('AUTHORING_WORK_MISMATCH',
            'The editable basis operation differs from the registered draft operation.',
            phase='authoring-context', file=file, pointer='/operation',
            cause='draft-operation-mismatch', expected=operation, actual=basis.get('operation'),
            guidance=GUIDANCE, required_action='Continue the registered operation in this draft, or start '
                'a new compose draft from its current choices to change the source selection.')
    if operation == 'compose':
        return
    retained = context.get('retained_identity_sources')
    if retained is None:
        retained = from_coverage(context.get('identity_coverage'))
    result = compare(retained, proposed)
    if result['changes']:
        first = result['changes'][0]
        raise ProductionError('IDENTITY_SOURCE_CHANGED',
            'This amend draft retains its original identity sources. The proposed selection changes that evidence.',
            phase='authoring-context', file=file, pointer='/retained_identity_sources',
            cause='retained-identity-source-changed', draft_operation=operation,
            source=first['source'], change_kind=first['change_kind'], before=first['before'], after=first['after'],
            changes=result['changes'], unresolved=result['unresolved'],
            repair_owner={'owner': 'retained-identity-context', 'file': file,
                          'pointer': '/retained_identity_sources'},
            guidance=GUIDANCE, required_action='Keep the retained evidence unchanged and start a compose draft '
                'from the current request and edited choices, applying the proposed source selection there.')
    if result['unresolved']:
        raise ProductionError('IDENTITY_SOURCE_UNAVAILABLE',
            'The retained identity comparison has unresolved source owners.',
            phase='authoring-context', file=file, pointer='/retained_identity_sources',
            cause='retained-identity-source-unresolved', draft_operation=operation,
            unresolved=result['unresolved'], guidance=GUIDANCE,
            required_action='Resolve the named source owner from its acquired evidence, or use a compose '
                'draft to complete a new current source selection. An unknown selection is not an empty one.')
