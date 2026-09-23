#!/usr/bin/env python3
"""Bind declared subjects to author decisions, accepted images and delivered bytes."""
from __future__ import annotations
import copy
from pathlib import Path
from typing import Any
import execution_contract as c

ROOT = Path(__file__).resolve().parents[1]
CONTINUITIES = {'recurring', 'one-off', 'undecided'}


def file_ref(root: Path, path: str, *, locator: str | None = None) -> dict:
    source = c.local(root, path)
    value = {'path': path, 'sha256': c.digest(c.read(source))}
    if locator is not None:
        value['locator'] = c.text(locator, 'source locator')
    return value


def check_file(root: Path, value: Any, *, basis: bool = False) -> Path:
    c.exact(value, {'path', 'sha256'} | ({'locator'} if basis else set()), 'source reference')
    c.sha(value['sha256'])
    if basis:
        c.text(value['locator'], 'source locator')
    path = c.local(root, value['path'])
    if c.digest(c.read(path)) != value['sha256']:
        raise ValueError('source bytes changed: ' + value['path'])
    return path


def validate_content(value: Any, production_spec: dict) -> None:
    """Validate the declared relationships without consulting current adoptions."""
    c.exact(value, {'purpose', 'basis', 'subjects'}, 'visual continuity')
    if value['purpose'] not in {'sheet-panel', 'image'}:
        raise ValueError('visual purpose must be sheet-panel or image')
    c.exact(value['basis'], {'path', 'sha256', 'locator'}, 'continuity basis')
    c.text(value['basis']['path'], 'continuity source')
    c.text(value['basis']['locator'], 'continuity locator')
    c.sha(value['basis']['sha256'])
    originals = production_spec.get('subjects')
    if not isinstance(originals, list) or not isinstance(value['subjects'], dict):
        raise ValueError('visual continuity requires the production subject collection')
    ids = [item.get('id') for item in originals if isinstance(item, dict)]
    if len(ids) != len(originals) or len(ids) != len(set(ids)) or any(not isinstance(x, str) or not x for x in ids):
        raise ValueError('production subjects need unique explicit IDs')
    if set(value['subjects']) != set(ids):
        raise ValueError('continuity subjects must match production subjects exactly')
    if value['purpose'] == 'sheet-panel' and len(ids) != 1:
        raise ValueError('a sheet panel requires exactly one production subject')
    for ident, item in value['subjects'].items():
        c.exact(item, {'continuity', 'character_id', 'studio_character', 'identity_refs'}, 'subject ' + ident)
        if item['continuity'] not in CONTINUITIES:
            raise ValueError(ident + ': select recurring, one-off or undecided explicitly')
        if item['continuity'] == 'undecided' and len(ids) != 1:
            raise ValueError(ident + ': an undecided character may only enter a single-subject exploration')
        for field in ('character_id', 'studio_character'):
            if item[field] is not None:
                c.text(item[field], ident + '.' + field)
        if item['continuity'] == 'recurring' and item['character_id'] is None:
            raise ValueError(ident + ': a recurring subject needs its work character ID')
        if not isinstance(item['identity_refs'], list):
            raise ValueError(ident + ': identity_refs must be an array')
        seen = set()
        for ref in item['identity_refs']:
            c.exact(ref, {'slot', 'iteration_id', 'source_sha256', 'reference_number'}, 'identity selector')
            c.text(ref['slot'], 'identity slot'); c.text(ref['iteration_id'], 'identity iteration')
            c.sha(ref['source_sha256'])
            if type(ref['reference_number']) is not int or ref['reference_number'] < 1:
                raise ValueError('identity reference_number must identify an ordered prepared reference')
            key = (ref['slot'], ref['iteration_id'], ref['reference_number'])
            if key in seen:
                raise ValueError(ident + ': duplicate identity selection')
            seen.add(key)
        if item['identity_refs'] and item['studio_character'] is None:
            raise ValueError(ident + ': identity selectors need their studio character')
        if item['continuity'] == 'recurring' and not item['identity_refs']:
            raise ValueError(ident + ': recurring needs an accepted identity image among the references. '
                             'The first images of a new recurring character are undecided exploration; '
                             'they become recurring once the author accepts one.')


def declared_sheet_slots(root: Path, character: str) -> set[str]:
    import studio
    from character_sheet import validate_sidecar
    from character_sheet_render.profiles import select_profile_path, load_profile
    from character_sheet_render.resolution import resolve_state_panels
    home = studio.character_dir(root, character)
    path = c.local(root, (home / 'sheet/sheet-data.json').relative_to(root).as_posix())
    sheet = c.load(path)
    validate_sidecar(sheet)
    profile_path, _ = select_profile_path(sheet, None, sheet_dir=path.parent)
    profile = load_profile(profile_path)
    profile, _ = resolve_state_panels(profile, sheet)
    slots = set(sheet['slots'])
    slots.update(box['slot_id'] for row in profile['rows'] for box in row['boxes']
                 if isinstance(box.get('slot_id'), str))
    return slots


def _decision(root: Path, value: Any, *, character_id: str | None = None) -> dict:
    c.exact(value, {'character_id', 'continuity', 'basis', 'by', 'at'}, 'continuity decision')
    c.text(value['character_id'], 'decision character')
    if value['continuity'] not in {'recurring', 'one-off'}:
        raise ValueError('adoption needs a decided continuity')
    c.text(value['by'], 'decision author'); c.text(value['at'], 'decision time')
    check_file(root, value['basis'], basis=True)
    if character_id is not None and value['character_id'] != character_id:
        raise ValueError('continuity decision belongs to another character')
    return value


def adoption_subject(root: Path, character: str, row: dict, approval: dict) -> dict:
    """Read the original single-subject candidate and an explicit later decision."""
    import adoption_workflow as adoption
    from verify_generation_payload import verify_content
    if not row.get('package'):
        raise ValueError('identity adoption needs recorded single-subject provenance')
    path = adoption.safe_file(root, row['package']['path'], row['package']['sha256'])
    package = c.load(path)
    if package.get('artifact_type') == 'upscale-package':
        # An upscale has a separately validated source Generation Package.
        source = package.get('source_generation_package')
        if not isinstance(source, dict):
            raise ValueError('identity adoption needs the source generation provenance')
        path = check_file(root, source)
        package = c.load(path)
    verify_content(package, package_root=path.parent)
    visual = package['visual_continuity']
    if len(visual['subjects']) != 1:
        raise ValueError('identity adoption requires a single-subject candidate')
    subject = next(iter(visual['subjects'].values()))
    if subject['studio_character'] not in {None, character}:
        raise ValueError('candidate was recorded for another studio character')
    decision = approval.get('continuity_decision')
    if decision is not None:
        chosen = _decision(root, decision, character_id=subject['character_id'])
        return {**subject, 'character_id': chosen['character_id'], 'continuity': chosen['continuity'],
                'decision_basis': chosen['basis']}
    if subject['continuity'] == 'undecided' or subject['character_id'] is None:
        raise ValueError('identity adoption needs an explicit author continuity decision for this candidate')
    return {**subject, 'decision_basis': visual['basis']}


def accepted_identity(root: Path, character: str, selector: dict, *, character_id: str | None) -> dict:
    import studio
    import adoption_workflow as adoption
    index = adoption.reference_index(root, character)
    if not index['ok']:
        raise ValueError('incomplete reference workflow: ' + '; '.join(index['errors']))
    matches = [item for item in index['bindings']
               if item['slot'] == selector['slot'] and item['iteration_id'] == selector['iteration_id']]
    if len(matches) != 1 or matches[0]['status'] not in {'sheet-bound', 'catalog-registered'}:
        raise ValueError(character + ': the selected identity is not currently accepted and bound')
    binding = matches[0]
    home = studio.character_dir(root, character)
    path = adoption._journal_path(home, selector['iteration_id'])
    if not path.is_file():
        raise ValueError(character + ': an explicit identity approval record is required')
    journal = c.load(path)
    if journal.get('status') not in {'sheet-bound', 'catalog-registered'} or journal.get('next_action') is not None:
        raise ValueError(character + ': identity adoption is incomplete')
    row = studio._find(studio.read_iterations(home), selector['iteration_id'])
    approval = adoption.validate_approval(journal.get('approval'), character, row)
    if row['status'] != 'accepted' or approval['influence'] != 'identity':
        raise ValueError(character + ': the selected receipt does not grant current identity influence')
    adopted = adoption_subject(root, character, row, approval)
    if character_id is not None and adopted['character_id'] != character_id:
        raise ValueError(character + ': the adopted image belongs to another work character')
    if binding['image_sha256'] != row['result']['sha256']:
        raise ValueError(character + ': accepted image and recorded candidate differ')
    image = Path(binding['image_path'])
    if c.digest(c.read(image)) != row['result']['sha256']:
        raise ValueError(character + ': accepted image bytes changed')
    return {**binding, 'adopted_subject': adopted, 'approval': approval,
            'approval_sha256': c.content_id(approval)}


def _identity_scope(prepared: dict, number: int, ident: str) -> dict:
    rows = prepared['selected_references']
    if number > len(rows):
        raise ValueError(ident + ': selected prepared reference does not exist')
    row = rows[number - 1]
    scopes = set(row.get('intended_influence', []))
    if row['role'] == 'identity':
        scopes.add('identity')
    plan = prepared.get('reference_use_plan')
    if plan is not None:
        item = plan['reference_items'][number - 1]
        if item['source'] != row['source']:
            raise ValueError(ident + ': reference source differs from its scoped use plan')
        scopes.add(item['intended_influence'])
    if 'identity' not in scopes:
        raise ValueError(ident + ': prepared reference does not carry identity influence')
    return row


def require(value: Any, *, production_spec: dict, prepared: dict, root: Path | None,
            recording_character: str | None = None, recording_slot: str | None = None) -> dict:
    validate_content(value, production_spec)
    if root is None:
        raise ValueError('visual continuity requires an explicit source or studio root')
    root = root.absolute()
    check_file(root, value['basis'], basis=True)
    subjects = value['subjects']
    if recording_slot is not None:
        if recording_character is None:
            raise ValueError('a recording slot requires its character selector')
        if recording_slot in declared_sheet_slots(root, recording_character):
            if value['purpose'] != 'sheet-panel' or len(subjects) != 1:
                raise ValueError('the recording slot requires a single-subject sheet-panel input')
        if value['purpose'] == 'sheet-panel':
            if len(subjects) != 1 or next(iter(subjects.values()))['studio_character'] != recording_character:
                raise ValueError('sheet panel does not identify the recording character')
    evidence = []
    from reference_delivery import bindings
    delivered = bindings(prepared['transport_mode'], prepared['selected_references'], prepared['single_board'])
    for ident, subject in subjects.items():
        character = subject['studio_character']
        if subject['continuity'] == 'recurring' or value['purpose'] == 'sheet-panel':
            if character is None:
                raise ValueError(ident + ': select the studio record for this subject')
        if character is not None:
            import studio
            studio.validate_recording_target(root, character, recording_slot or 'candidate', writable=False)
            import adoption_workflow as adoption
            index = adoption.reference_index(root, character)
            if not index['ok']:
                raise ValueError(ident + ': reference workflow is incomplete: ' + '; '.join(index['errors']))
            current = [x for x in index['bindings'] if x['influence'] == 'identity' and x['image_path']]
            if current and not subject['identity_refs']:
                raise ValueError(ident + ': generation must include the current accepted identity')
        for ref in subject['identity_refs']:
            accepted = accepted_identity(root, character, ref, character_id=subject['character_id'])
            if accepted['image_sha256'] != ref['source_sha256']:
                raise ValueError(ident + ': selected identity source hash mismatch')
            row = _identity_scope(prepared, ref['reference_number'], ident)
            if row['source']['sha256'] != ref['source_sha256']:
                raise ValueError(ident + ': identity is not the selected prepared source')
            adopted = accepted['adopted_subject']
            if adopted['continuity'] == 'recurring' and subject['continuity'] != 'recurring':
                raise ValueError(ident + ': a current recurring character needs an explicit new author decision before changing continuity')
            if ref['reference_number'] > len(delivered):
                raise ValueError(ident + ': identity carrier is not actually delivered')
            evidence.append({'subject_id': ident, 'character_id': adopted['character_id'],
                             'approval_sha256': accepted['approval_sha256'],
                             'image_sha256': ref['source_sha256'], **delivered[ref['reference_number'] - 1]})
    return {'subjects': len(subjects), 'identity_bindings': evidence}


def build_record(choices: dict, *, production_spec: dict, prepared: dict, root: Path) -> dict:
    """Resolve only explicitly selected records; preserve all authored decisions."""
    c.exact(choices, {'purpose', 'basis', 'subjects'}, 'visual choices')
    c.exact(choices['basis'], {'path', 'locator'}, 'visual basis choice')
    result = copy.deepcopy(choices)
    result['basis'] = file_ref(root, choices['basis']['path'], locator=choices['basis']['locator'])
    for ident, subject in result['subjects'].items():
        c.exact(subject, {'continuity', 'character_id', 'studio_character', 'identity_refs'}, 'visual subject choice')
        refs = []
        for selected in subject['identity_refs']:
            c.exact(selected, {'slot', 'iteration_id'}, 'identity choice')
            image = accepted_identity(root, subject['studio_character'], selected, character_id=subject['character_id'])
            matches = [i for i, row in enumerate(prepared['selected_references'], 1)
                       if row['source']['sha256'] == image['image_sha256']]
            if len(matches) != 1:
                raise ValueError(ident + ': identity choice must identify one ordered prepared source')
            refs.append({**selected, 'source_sha256': image['image_sha256'], 'reference_number': matches[0]})
        subject['identity_refs'] = refs
    require(result, production_spec=production_spec, prepared=prepared, root=root)
    return result


def from_decisions(decisions: dict[str, str], *, production_spec: dict, prepared: dict, root: Path,
                   characters: dict[str, str] | None = None, work_ids: dict[str, str] | None = None,
                   sheet_panel: bool = False) -> dict:
    """Build the record from the author's stated decisions and the studio's accepted identity.

    The decisions are written under the project's work/continuity/ as the basis. A
    subject bound to a studio character selects that character's current
    accepted identity images, which the prepared references must carry.
    """
    import adoption_workflow as adoption
    characters = dict(characters or {})
    work_ids = dict(work_ids or {})
    ids = [item.get('id') for item in production_spec.get('subjects') or [] if isinstance(item, dict)]
    if set(decisions) != set(ids):
        raise ValueError('state one continuity decision for each production subject: ' + ', '.join(map(str, ids)))
    if set(characters) - set(ids):
        raise ValueError('studio characters name no production subject: ' + ', '.join(sorted(set(characters) - set(ids))))
    subjects = {}
    for ident in ids:
        character = characters.get(ident)
        continuity = decisions[ident]
        if continuity == 'recurring' and character is None:
            raise ValueError(ident + ': name the studio character of a recurring subject')
        refs = []
        if character is not None:
            index = adoption.reference_index(root, character)
            if not index['ok']:
                raise ValueError(ident + ': reference workflow is incomplete: ' + '; '.join(index['errors']))
            refs = [{'slot': x['slot'], 'iteration_id': x['iteration_id']} for x in index['bindings']
                    if x['influence'] == 'identity' and x['image_path']]
        character_id = None
        if continuity == 'recurring':
            character_id = work_ids.get(ident)
            if character_id is None and refs:
                character_id = accepted_identity(root, character, refs[0], character_id=None)['adopted_subject']['character_id']
            character_id = character_id or character
        subjects[ident] = {'continuity': continuity, 'character_id': character_id,
                           'studio_character': character, 'identity_refs': refs}
    purpose = 'sheet-panel' if sheet_panel else 'image'
    raw = c.encoded({'purpose': purpose, 'subjects': {ident: {key: subject[key] for key in ('continuity', 'studio_character')}
                                                     for ident, subject in subjects.items()}})
    path = 'work/continuity/' + c.digest(raw)[:16] + '.json'
    target = c.local(root, path, exists=False)
    try:
        c.atomic(target, raw)
    except FileExistsError:
        if c.read(target) != raw:
            raise ValueError('continuity record changed: ' + path)
    return build_record({'purpose': purpose, 'basis': {'path': path, 'locator': 'whole'}, 'subjects': subjects},
                        production_spec=production_spec, prepared=prepared, root=root)
