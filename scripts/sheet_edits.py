"""Apply authored sheet edits without ever importing runtime selections from HTML.

The editor exports a before/after authoring projection. Under the sheet lock,
only touched keys are compared and updated. Unrelated changes merge; conflicting
edits fail as a whole. Current artwork, candidates and acceptance history are
owned exclusively by sheet_artifacts.
"""
from __future__ import annotations
import copy
from pathlib import Path

import execution_contract as c
import sheet_artifacts as fills

SECTIONS = {'fields', 'tables', 'fill_policies'}
_MISSING = object()


def projection(sheet: dict) -> dict:
    return {'fields': copy.deepcopy(sheet['fields']), 'tables': copy.deepcopy(sheet['tables']),
            'fill_policies': {key: value.get('fill_policy', 'auto') for key, value in sheet['slots'].items()
                              if value.get('fill_policy', 'auto') != 'auto'}}


def draft(before: dict, after: dict) -> dict:
    return {'artifact_type': 'character-sheet-edit', 'before': projection(before), 'after': projection(after)}


def _validate(value: dict) -> None:
    from state_protocol import validate_against_schema
    schema = c.load(Path(__file__).resolve().parents[1] / 'schemas/authoring/character-sheet-edit.schema.json')
    errors = validate_against_schema(value, schema)
    if errors:
        raise ValueError('invalid authored sheet edit: ' + '; '.join(errors))
    c.exact(value, {'artifact_type', 'before', 'after'}, 'sheet edit')
    if value['artifact_type'] != 'character-sheet-edit':
        raise ValueError('expected a character-sheet-edit')
    for key in ('before', 'after'):
        c.exact(value[key], SECTIONS, 'authored sheet projection')
        if any(not isinstance(value[key][part], dict) for part in SECTIONS):
            raise ValueError('authored sections must be objects')
        for slot, policy in value[key]['fill_policies'].items():
            if policy not in {'auto', 'fill', 'keep', 'skip'}:
                raise ValueError('invalid authored fill policy: ' + slot)


def apply(sidecar: Path, value: dict) -> dict:
    _validate(value)
    with fills.sheet_lock(sidecar):
        state = fills._read(sidecar)
        current = projection(state)
        changes, conflicts = [], []
        for section in sorted(SECTIONS):
            before, after = value['before'][section], value['after'][section]
            for key in sorted(before.keys() | after.keys()):
                old, new = before.get(key, _MISSING), after.get(key, _MISSING)
                if old == new:
                    continue
                held = current[section].get(key, _MISSING)
                # Reapplying the same edit is a no-op. This also permits recovery
                # after the commit completed but the caller lost its response.
                if held == new:
                    continue
                if held != old:
                    conflicts.append(f'{section}.{key}')
                else:
                    changes.append((section, key, new))
        if conflicts:
            raise ValueError('SHEET_EDIT_CONFLICT: reload and reconcile ' + ', '.join(conflicts))
        for section, key, new in changes:
            if section == 'fill_policies':
                import re
                if not re.fullmatch(r'[a-z0-9][a-z0-9._-]*', key):
                    raise ValueError('invalid sheet slot ID')
                state['slots'].setdefault(key, fills.empty_slot())['fill_policy'] = 'auto' if new is _MISSING else new
            elif new is _MISSING:
                state[section].pop(key, None)
            else:
                state[section][key] = copy.deepcopy(new)
        if changes:
            fills._write(sidecar, state)
        import studio_activity as activity
        status = activity.changed(sidecar, 'sheet-edited', revision=c.content_id(state),
                                  details={'edit_sha256': c.content_id(value),
                                           'changed_keys': [section + '.' + key for section, key, _ in changes]})
        return {'ok': True, 'changed': bool(changes), 'sheet': str(sidecar),
                'accepted_sha256': fills.accepted_sha256(state), 'projection': status,
                'next': 'Reload the committed sheet-data.json in the editor before making another round of edits.'}
