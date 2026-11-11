"""Append-only placement decisions for retained Studio iterations.

The iteration's slot records where production first recorded it. A placement
decision changes its current destination without rewriting that provenance.
The character journal and accepted copies project any acceptance transfer;
the committed decision retains enough information to recover those writes.
"""
from __future__ import annotations

import copy
from datetime import datetime
from pathlib import Path

import execution_contract as c
import production_store as store
import runtime_snapshot
from production_diagnostics import ProductionError
from studio_activity import mutation


def scope(character: str) -> str:
    return 'studio-placement:' + character


def slot(row: dict) -> str:
    """Current placement of an acquired row; an unplaced row keeps its origin."""
    return row.get('placement', {}).get('slot', row['slot'])


def receipt_slot(row: dict, receipt: dict) -> str:
    """A receipt names its target; an initial receipt is scoped to recording."""
    return receipt.get('slot', row['slot'])


def origin(row: dict) -> dict:
    return {'character': row['character'], 'iteration_id': row['iteration_id'],
            'recorded_slot': row['slot'], 'image_sha256': (row.get('result') or {}).get('sha256'),
            'production': copy.deepcopy(row.get('production'))}


def initial(row: dict) -> dict:
    return {'slot': row['slot'], 'recorded_slot': row['slot'],
            'sha256': c.content_id({'artifact_type': 'studio-initial-placement', **origin(row)})}


def _status(row: dict) -> str:
    return row.get('adoption_status', 'none') if row.get('production') is not None else row.get('status', 'candidate')


def _set_status(row: dict, value: str) -> None:
    row['adoption_status' if row.get('production') is not None else 'status'] = value


def acceptance(rows: list[dict], target: str) -> dict | None:
    accepted = [row for row in rows if slot(row) == target and _status(row) == 'accepted']
    if len(accepted) > 1:
        raise ValueError('the Studio records more than one current acceptance for this slot')
    if not accepted:
        return None
    row = accepted[0]
    if not row.get('result') or not row.get('acceptances'):
        raise ValueError('the accepted iteration has no retained image or acceptance receipt')
    if receipt_slot(row, row['acceptances'][-1]) != target:
        raise ValueError('the latest acceptance receipt belongs to another slot')
    return {'iteration_id': row['iteration_id'], 'image_sha256': row['result']['sha256'],
            'acceptance_sha256': c.content_id(row['acceptances'][-1])}


def _conflict(message: str, **details):
    return ProductionError('PLACEMENT_CONFLICT', message, phase='placement', **details,
        required_action='Inspect studio.py status, then draft-reassignment again for the current source and destination. '
                        'A retry never restores an earlier placement or acceptance.')


def _corrupt(message: str, **details):
    return ProductionError('PLACEMENT_RECORD_CORRUPT', message, phase='placement', **details,
        required_action='Restore the exact placement event or original iteration evidence from a verified Studio copy. '
                        'Do not change its recorded slot, image or Production origin.')


def _validate_decision(value: dict) -> None:
    c.exact(value, {'artifact_type', 'origin', 'expected_placement', 'source_slot', 'destination_slot',
                    'expected_source', 'expected_destination', 'by', 'at', 'reason'}, 'Studio reassignment')
    if value['artifact_type'] != 'studio-reassignment':
        raise ValueError('expected a studio-reassignment decision')
    c.exact(value['origin'], {'character', 'iteration_id', 'recorded_slot', 'image_sha256', 'production'},
            'reassignment origin')
    c.sha(value['origin']['image_sha256'])
    c.sha(value['expected_placement'])
    import studio
    if not studio.valid_character_id(value['origin']['character']):
        raise ValueError('reassignment character is invalid')
    for key in ('recorded_slot',):
        if not isinstance(value['origin'][key], str) or not studio.SLOT.fullmatch(value['origin'][key]):
            raise ValueError('reassignment recorded slot is invalid')
    for key in ('source_slot', 'destination_slot'):
        if not isinstance(value[key], str) or not studio.SLOT.fullmatch(value[key]):
            raise ValueError('reassignment slot is invalid')
    if value['source_slot'] == value['destination_slot']:
        raise ValueError('choose a different destination slot for reassignment')
    for key in ('by', 'at', 'reason'):
        c.text(value[key], 'reassignment ' + key)
    try:
        stamp = datetime.fromisoformat(value['at'].replace('Z', '+00:00'))
    except (ValueError, AttributeError) as exc:
        raise ValueError('reassignment requires an actual ISO timestamp') from exc
    if stamp.tzinfo is None:
        raise ValueError('reassignment time must include a timezone')
    for key in ('expected_source', 'expected_destination'):
        state = value[key]
        if state is not None:
            c.exact(state, {'iteration_id', 'image_sha256', 'acceptance_sha256'}, key)
            c.text(state['iteration_id'], key + ' iteration')
            c.sha(state['image_sha256']); c.sha(state['acceptance_sha256'])


def transferred_receipt(decision: dict) -> dict | None:
    source = decision['expected_source']
    if source is None or source['iteration_id'] != decision['origin']['iteration_id']:
        return None
    destination = decision['expected_destination']
    return {'at': decision['at'], 'supersedes': destination['iteration_id'] if destination else None,
            'slot': decision['destination_slot'], 'placement': c.content_id(decision)}


def project(character: str, raw_rows: list[dict], records: list[dict]) -> list[dict]:
    """Replay one verified placement history over the character's acquired rows.

    Acceptance writes may have stopped after the event committed. Its exact
    transfer is projected until a journal write retains that receipt. Ordinary
    later acceptance keeps the receipt and therefore supersedes the transfer.
    """
    rows = copy.deepcopy(raw_rows)
    by_id = {row['iteration_id']: row for row in rows}
    if len(by_id) != len(rows):
        raise _corrupt('Studio iteration identifiers are not unique.', character=character)
    for row in rows:
        row['placement'] = initial(row)
    transfers = {}
    for event in records:
        try:
            if event['event'] != 'iteration-reassigned':
                raise ValueError('unknown placement event')
            c.exact(event['data'], {'decision'}, 'placement event')
            decision = event['data']['decision']
            _validate_decision(decision)
            row = by_id[decision['origin']['iteration_id']]
            if decision['origin'] != origin(row) or row['character'] != character:
                raise ValueError('placement differs from the iteration original evidence')
            if decision['expected_placement'] != row['placement']['sha256'] or decision['source_slot'] != slot(row):
                raise ValueError('placement does not follow its recorded predecessor')
            receipt = transferred_receipt(decision)
            if receipt is not None:
                transfers[receipt['placement']] = (row['iteration_id'], receipt)
            if receipt is not None and receipt not in row.get('acceptances', []):
                # Every later owner writes the acquired graph and retains past
                # receipts. Missing this one therefore means its write stopped.
                if acceptance(rows, decision['source_slot']) != decision['expected_source'] \
                        or acceptance(rows, decision['destination_slot']) != decision['expected_destination']:
                    raise ValueError('an unapplied acceptance transfer differs from its expected slot states')
                target = decision['expected_destination']
                if target is not None:
                    other = by_id[target['iteration_id']]
                    _set_status(other, 'superseded')
                    other['superseded_by'] = row['iteration_id']
                    other['superseded_in'] = decision['destination_slot']
                    other['accepted_path'] = None
                _set_status(row, 'accepted')
                row.pop('superseded_by', None); row.pop('superseded_in', None)
                row['acceptances'] = [*row.get('acceptances', []), receipt]
                suffix = Path(row['result']['path']).suffix
                row['accepted_path'] = f'characters/{character}/accepted/{decision["destination_slot"]}{suffix}'
            row['placement'] = {'slot': decision['destination_slot'], 'recorded_slot': row['slot'],
                                'sha256': event['sha256'], 'decision_sha256': c.content_id(decision),
                                'by': decision['by'], 'at': decision['at'], 'reason': decision['reason']}
        except (ValueError, KeyError, TypeError) as exc:
            raise _corrupt('The recorded placement cannot be replayed: ' + str(exc),
                           character=character, event=event['sha256']) from exc
    for row in rows:
        for receipt in row.get('acceptances', []):
            if 'placement' in receipt and transfers.get(receipt['placement']) != (row['iteration_id'], receipt):
                raise _corrupt('An acceptance transfer has no exact placement event.',
                               character=character, iteration=row['iteration_id'])
    return rows


def _withdrawal_error(root: Path, character: str, name: str, iteration: str):
    from cli_invocation import shown, python_argv
    sheet = root / 'characters' / character / 'sheet/sheet-data.json'
    command = shown(python_argv(Path(__file__).with_name('sheet_workflow.py'), 'draft-withdrawal',
        '--sheet', str(sheet), '--slot', name, '--out', 'withdrawal.json'))
    apply = shown(python_argv(Path(__file__).with_name('sheet_workflow.py'), 'withdraw',
        '--sheet', str(sheet), '--decision-file', 'withdrawal.json', '--evidence-root', str(root)))
    return ProductionError('PLACEMENT_SOURCE_ADOPTED', 'The placement would change an acceptance with current canonical artwork.',
        phase='placement', character=character, iteration=iteration, slot=name,
        required_action=f'Withdraw that exact adoption first: {command}. Complete its actual author decision '
                        f'and evidence, then run {apply}. Draft this reassignment again afterward; '
                        'the destination needs its own adoption approval.')


def _require_no_adoption(root: Path, character: str, row: dict, read, *, destination: str | None = None) -> None:
    import sheet_artifacts as fills
    sidecar = read.sheet(character)
    sheet = read.home(character) / 'sheet'
    for name, selected in sidecar['slots'].items():
        current = selected['current']
        if current is None:
            continue
        if name != destination and current['artifact']['image']['sha256'] != row['result']['sha256']:
            continue
        provenance = fills.verify_artifact(current['artifact'], sheet, cache=read.artifacts)
        named = provenance.get('origin') or {}
        if name != destination and (named.get('character') != character or named.get('iteration_id') != row['iteration_id']):
            continue
        fills.verify_acceptance(current, sheet, name, cache=read.artifacts)
        raise _withdrawal_error(root, character, name, row['iteration_id'])


@runtime_snapshot.operation
def draft(root: Path, character: str, iteration: str, destination: str) -> dict:
    """Pin the exact source and both current slot states without inventing approval."""
    import studio
    root = studio.require_studio(root)
    read = studio.StudioRead(root)
    studio.validate_recording_target(root, character, destination, read=read)
    row = studio._find(read.placed_iterations(character), iteration)
    if slot(row) == destination:
        raise ValueError('this iteration already has that current slot')
    _require_no_adoption(root, character, row, read, destination=destination if _status(row) == 'accepted' else None)
    return {'artifact_type': 'studio-reassignment', 'origin': origin(row),
            'expected_placement': row['placement']['sha256'], 'source_slot': slot(row),
            'destination_slot': destination,
            'expected_source': studio.acceptance_state(root, character, slot(row), read=read),
            'expected_destination': studio.acceptance_state(root, character, destination, read=read),
            'by': '', 'at': '', 'reason': ''}


def _project_sheet(root: Path, character: str, iteration: str, sources: set[str], destination: str) -> None:
    """Move existing candidate membership; history and adopted artwork stay intact."""
    import sheet_artifacts as fills
    import studio
    sheet = studio.character_home(root, character) / 'sheet'
    sidecar = sheet / 'sheet-data.json'
    with fills.sheet_lock(sidecar):
        state = fills._read(sidecar)
        moved = []
        for source in sorted(sources - {destination}):
            old = state['slots'].get(source)
            if old is None:
                continue
            kept = []
            for artifact in old['candidates']:
                named = fills.verify_artifact(artifact, sheet).get('origin') or {}
                (moved if named.get('character') == character and named.get('iteration_id') == iteration else kept).append(artifact)
            old['candidates'] = kept
        if not moved:
            return
        target = state['slots'].setdefault(destination, fills.empty_slot())
        current = fills.current_artifact(target)
        present = {item['artifact_id'] for item in target['candidates']}
        if current is not None:
            present.add(current['artifact_id'])
        for item in moved:
            if item['artifact_id'] not in present:
                target['candidates'].append(item)
                present.add(item['artifact_id'])
        fills._write(sidecar, state)


def _owned_slots(row: dict, records: list[dict]) -> set[str]:
    result = {row['slot'], *(receipt_slot(row, item) for item in row.get('acceptances', []))}
    for event in records:
        decision = event['data']['decision']
        if decision['origin']['iteration_id'] == row['iteration_id']:
            result.update((decision['source_slot'], decision['destination_slot']))
    return result


def _clean_accepted(root: Path, character: str, row: dict, read, owned_slots: set[str]) -> None:
    """Remove only this iteration's unowned copies, including interrupted older moves."""
    import studio
    if not row.get('acceptances'):
        return
    for name in owned_slots:
        accepted = studio.acceptance_state(root, character, name, read=read)
        for path in (read.home(character) / 'accepted').glob(name + '.*'):
            if not path.is_file() or path.stem != name:
                continue
            unowned = accepted is None and c.sha256_file(path) == row['result']['sha256']
            duplicate = (accepted is not None and accepted['iteration_id'] == row['iteration_id']
                         and row.get('accepted_path') and path != c.local(root, row['accepted_path'], exists=False))
            if unowned or duplicate:
                path.unlink()


def _publish(root: Path, character: str, event: dict, read) -> dict:
    """Recover derived files only while this exact decision remains current."""
    import studio
    decision = event['data']['decision']
    row = studio._find(read.placed_iterations(character), decision['origin']['iteration_id'])
    current = row['placement']['sha256'] == event['sha256']
    receipt = transferred_receipt(decision)
    transfer_current = receipt is None or (_status(row) == 'accepted' and row['acceptances'][-1] == receipt)
    owned_slots = _owned_slots(row, read.placement_records(character))
    if current and transfer_current:
        rows = copy.deepcopy(read.placed_iterations(character))
        if receipt is not None:
            image = c.read(c.local(root, row['result']['path']))
            if c.digest(image) != row['result']['sha256']:
                raise ValueError('the reassigned image differs from its recorded bytes')
            target = c.local(root, row['accepted_path'], exists=False)
            c.atomic(target, image, replace=True)
            studio.write_iterations(read.home(character), rows)
    if current:
        _project_sheet(root, character, row['iteration_id'], owned_slots, decision['destination_slot'])
    _clean_accepted(root, character, row, studio.StudioRead(root), owned_slots)
    return {'ok': True, 'placement': event['sha256'], 'character': character, 'iteration_id': row['iteration_id'],
            'recorded_slot': row['slot'], 'source_slot': decision['source_slot'],
            'destination_slot': decision['destination_slot'], 'current_slot': slot(row),
            'current': current, 'acceptance_transferred': receipt is not None,
            'acceptance_current': receipt is not None and current and transfer_current,
            'image_sha256': row['result']['sha256']}


@mutation
def reassign(root: Path, decision: dict) -> dict:
    """Commit or recover one authored correction without recreating production."""
    import studio
    import studio_activity as activity
    root = studio.require_studio(root)
    _validate_decision(decision)
    character = decision['origin']['character']
    home = studio.character_home(root, character)
    # This operation owns both the character's acceptance journal and the
    # sheet membership it moves. Hold their existing owners in that order.
    with studio.recording_lock(root, character=character), c.lock(home / 'sheet'):
        with store.transaction(root):
            read = studio.StudioRead(root)
            records = read.placement_records(character)
            event = next((item for item in records if item['data']['decision'] == decision), None)
            if event is None:
                row = studio._find(read.placed_iterations(character), decision['origin']['iteration_id'])
                if origin(row) != decision['origin']:
                    raise _conflict('The decision names different original iteration evidence.')
                if row['placement']['sha256'] != decision['expected_placement'] or slot(row) != decision['source_slot']:
                    raise _conflict('The iteration placement changed after this decision was drafted.')
                for key, name in (('expected_source', 'source_slot'), ('expected_destination', 'destination_slot')):
                    actual = studio.acceptance_state(root, character, decision[name], read=read)
                    if actual != decision[key]:
                        raise _conflict('The source or destination acceptance changed after this decision was drafted.',
                                        slot=decision[name], expected=decision[key], actual=actual)
                studio.validate_recording_target(root, character, decision['destination_slot'], writable=True, read=read)
                _require_no_adoption(root, character, row, read,
                    destination=decision['destination_slot'] if transferred_receipt(decision) is not None else None)
                image = c.read(c.local(root, row['result']['path']))
                if c.digest(image) != row['result']['sha256']:
                    raise _corrupt('The retained image differs from its original hash.')
                if row.get('production') is not None:
                    loaded = read.run(row['production']['run'])
                    import production_workflow as workflow
                    candidate = workflow.find(loaded.rows, 'candidate', row['production']['candidate'])
                    if candidate['data']['files'][0]['sha256'] != row['result']['sha256']:
                        raise _corrupt('The iteration differs from its exact Production candidate.')
                    if transferred_receipt(decision) is not None:
                        workflow.require_selected(loaded.prepared, loaded.rows, row['production']['candidate'],
                                                  run=row['production']['run'])
                event = store.append(root, scope(character), None, 'iteration-reassigned', {'decision': copy.deepcopy(decision)},
                    expected_previous=records[-1]['sha256'] if records else None, check_previous=True)
        runtime_snapshot.invalidate_studio(root)
        try:
            result = _publish(root, character, event, studio.StudioRead(root))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ProductionError('PLACEMENT_PROJECTION_PENDING', 'The placement decision committed; its files need recovery.',
                phase='placement', placement=event['sha256'], committed_state_retained=True, cause=str(exc),
                required_action='Repeat studio.py reassign --file with the same decision file. '
                                'It recovers that placement without changing a newer decision or generating again.') from exc
        activity.changed(root, 'iteration-reassigned', subject=character + '/' + decision['origin']['iteration_id'],
                         revision=event['sha256'], details=result, characters={character})
        return result
