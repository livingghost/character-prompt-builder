"""Bounded sheet status and gallery metadata, with failures scoped to their owner."""
from __future__ import annotations
import copy
from pathlib import Path, PurePosixPath
from typing import Any

import execution_contract as c
import sheet_artifacts as fills
from studio_activity import chronological


def artwork_record(sheet_root: Path, artifact: dict) -> dict:
    """Read small provenance metadata, not every image in the sheet."""
    value = c.load(fills._file(sheet_root, artifact['provenance']['path'], artifact['provenance']['sha256']))
    publication = c.load(fills._file(sheet_root, str(PurePosixPath(artifact['provenance']['path']).parent / 'publication.json')))
    if publication.get('artifact_id') != artifact['artifact_id']:
        raise ValueError('publication metadata names a different artifact')
    return {'recorded_at': publication['recorded_at'], 'origin': value.get('origin') or {},
            'kind': value['kind'], 'recipe': value['recipe']}


def entries(sidecar: Path, *, state: dict | None = None) -> list[dict]:
    state = fills._read(sidecar) if state is None else state
    rows = []
    metadata = {}
    for slot_id, slot in state['slots'].items():
        found = {}
        for accepted in slot['history']:
            art = accepted['artifact']
            row = found.setdefault(art['artifact_id'], {'artifact': art, 'state': 'history', 'acceptances': []})
            row['acceptances'].append(accepted['approval'])
        for art in slot['candidates']:
            found.setdefault(art['artifact_id'], {'artifact': art, 'acceptances': []})['state'] = 'candidate'
        if slot['current'] is not None:
            art = slot['current']['artifact']
            row = found.setdefault(art['artifact_id'], {'artifact': art, 'acceptances': []})
            row['state'] = 'current'; row['acceptances'].append(slot['current']['approval'])
        for identifier, value in found.items():
            row = {'slot': slot_id, 'artifact_id': identifier, **copy.deepcopy(value),
                   'recorded_at': None, 'origin': {}, 'availability': 'unchecked', 'diagnostics': []}
            if identifier not in metadata:
                try:
                    metadata[identifier] = artwork_record(sidecar.parent, row['artifact'])
                except (ValueError, OSError, KeyError, TypeError) as exc:
                    metadata[identifier] = exc
            if isinstance(metadata[identifier], Exception):
                row['availability'] = 'unavailable'
                row['diagnostics'].append(str(metadata[identifier]))
            else:
                row.update(metadata[identifier])
            rows.append(row)
    rows.sort(key=lambda row: (chronological(row['recorded_at']), row['artifact_id'], row['slot']), reverse=True)
    return rows


def _dispositions(sidecar: Path, rows: list[dict]) -> None:
    """Read each formal run only once; do not copy its decisions into the sidecar."""
    import studio
    import production_workflow as workflow
    root = studio.studio_root(sidecar.parent)
    cache: dict[str, Any] = {}
    for row in rows:
        origin = row['origin']
        row['disposition'] = 'unreviewed'
        if row['state'] == 'current':
            row['disposition'] = 'accepted'
        elif row['state'] == 'history':
            row['disposition'] = 'superseded'
        if origin.get('kind') != 'production':
            continue
        try:
            if root is None:
                raise ValueError('Production origin has no owning Studio')
            run = origin['run']
            if run not in cache:
                try:
                    cache[run] = workflow.load_run(root, run)
                except (ValueError, OSError, KeyError, TypeError) as exc:
                    cache[run] = exc
            if isinstance(cache[run], Exception):
                raise cache[run]
            value = workflow.candidate_state(root, run, origin['candidate'], loaded=cache[run])
            row.update(disposition=value['disposition'], evaluation=value['evaluation'],
                       review=value['review'], selection_diagnostics=value['selection_diagnostics'])
        except (ValueError, OSError, KeyError, TypeError) as exc:
            row['disposition'] = 'unavailable'; row['availability'] = 'unavailable'
            row['diagnostics'].append(str(exc))


def status(sidecar: Path, *, slot: str | None = None, state_filter: str | None = None,
           disposition: str | None = None, limit: int = 50, offset: int = 0, verify: bool = True) -> dict:
    if type(limit) is not int or not 1 <= limit <= 500 or type(offset) is not int or offset < 0:
        raise ValueError('limit must be 1..500 and offset must be nonnegative')
    state = fills._read(sidecar)
    rows = entries(sidecar, state=state)
    if slot is not None:
        rows = [row for row in rows if row['slot'] == slot]
    if state_filter is not None:
        rows = [row for row in rows if row['state'] == state_filter]
    # A disposition filter is about formal decisions, not stored candidate membership.
    if disposition is not None:
        _dispositions(sidecar, rows)
        rows = [row for row in rows if row['disposition'] == disposition]
    total = len(rows)
    page = rows[offset:offset + limit]
    if disposition is None:
        _dispositions(sidecar, page)
    verified = {}
    for row in page:
        if not verify:
            continue
        try:
            fills.verify_artifact(row['artifact'], sidecar.parent, cache=verified)
            if row['state'] == 'current':
                fills.verify_acceptance(state['slots'][row['slot']]['current'], sidecar.parent, row['slot'], cache=verified)
            if row['availability'] != 'unavailable':
                row['availability'] = 'verified'
        except (ValueError, OSError, KeyError, TypeError) as exc:
            row['availability'] = 'unavailable'; row['diagnostics'].append(str(exc))
    return {'ok': True, 'sheet': str(sidecar), 'sheet_status': state['sheet_status'],
            'accepted_sha256': fills.accepted_sha256(state), 'order': 'recorded_at_desc',
            'total': total, 'offset': offset, 'limit': limit,
            'next_offset': offset + limit if offset + limit < total else None,
            'entries': page, 'unavailable_on_page': sum(row['availability'] == 'unavailable' for row in page)}
