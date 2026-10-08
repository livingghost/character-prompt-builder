"""Immutable sheet artwork, explicit candidates, and atomic author adoption.

The sidecar is the only mutable sheet selection record. Images and their source
records live in a content-addressed store inside that sheet. Adding a candidate
never changes the accepted projection; replacing a selection retains its exact
artifact and approval in history. This module does not call an image service.
"""
from __future__ import annotations
import copy
from contextlib import contextmanager
from datetime import datetime
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Iterator, Mapping, Sequence

import execution_contract as c

KINDS = frozenset({'generation', 'upscale', 'crop', 'resize', 'composite', 'shared'})
STORE = '.fills/artifacts'
APPROVALS = '.fills/approvals'


def empty_slot(*, fill_policy: str = 'auto') -> dict:
    return {'current': None, 'candidates': [], 'history': [], 'fill_policy': fill_policy}


def current_artifact(slot: Mapping[str, Any] | None) -> dict | None:
    current = slot.get('current') if isinstance(slot, Mapping) else None
    return current.get('artifact') if isinstance(current, Mapping) else None


def accepted_projection(sidecar: Mapping[str, Any]) -> dict:
    """The authored sheet plus current choices, not mutable candidate/history lists."""
    return {**{key: copy.deepcopy(value) for key, value in sidecar.items() if key != 'slots'},
            'slots': {key: {'current': copy.deepcopy(value['current']),
                            'fill_policy': value.get('fill_policy', 'auto')}
                      for key, value in sidecar['slots'].items()
                      if value['current'] is not None or value.get('fill_policy', 'auto') != 'auto'}}


def accepted_sha256(sidecar: Mapping[str, Any]) -> str:
    return c.content_id(accepted_projection(sidecar))


def selection_bytes(path: str, raw: bytes) -> tuple[str, bytes] | None:
    """Freshness concerns current accepted sources; the full raw snapshot remains archived."""
    import re
    if re.fullmatch(r'characters/[^/]+/sheet/sheet-data\.json', path):
        return 'sheet-current', c.encoded(accepted_projection(c.decode(raw)))
    if re.fullmatch(r'characters/[^/]+/iterations\.jsonl', path):
        rows = [c.decode(line) for line in raw.splitlines() if line.strip()]
        return 'studio-accepted', c.encoded([row for row in rows if row.get('status') == 'accepted'])
    return None


def dependency(space: str, path: str, raw: bytes) -> dict:
    entry = {'space': space, 'path': path, 'sha256': c.digest(raw), 'size': len(raw)}
    projection = selection_bytes(path, raw) if space == 'studio' else None
    if projection is not None:
        entry.update(selection_kind=projection[0], selection_sha256=c.digest(projection[1]))
    return entry


def upscale_source(root: Path, task: dict, request: dict) -> dict | None:
    """Tie an authored upscale input to exact current/candidate sheet pixels before sending."""
    selector = task.get('upscale', {}).get('derivation')
    if selector is None:
        return None
    c.exact(selector, {'sheet', 'slot', 'artifact_id'}, 'upscale sheet source')
    sidecar = c.local(root, selector['sheet'])
    state = _read(sidecar)
    slot = state['slots'].get(selector['slot'])
    if slot is None:
        raise ValueError('upscale derivation names an unknown source slot')
    artifacts = [*slot['candidates'], *([current_artifact(slot)] if current_artifact(slot) else [])]
    artifact = next((entry for entry in artifacts if entry['artifact_id'] == selector['artifact_id']), None)
    if artifact is None:
        raise ValueError('upscale derivation requires a current or recorded candidate source')
    verify_artifact(artifact, sidecar.parent)
    if artifact['image']['sha256'] != request['source']['sha256']:
        raise ValueError('upscale input pixels differ from the declared sheet source')
    if c.local(root, request['source']['path']) != _file(sidecar.parent, artifact['image']['path']):
        raise ValueError('upscale input path differs from its immutable sheet source')
    return artifact


def _file(root: Path, relative: str, expected: str | None = None) -> Path:
    from character_sheet import resolve_sheet_relative
    path = resolve_sheet_relative(relative, root=root, field='sheet artifact')
    if expected is not None and c.sha256_file(path) != expected:
        raise ValueError('sheet artifact hash mismatch: ' + relative)
    return path


def _safe_directory(root: Path, relative: str) -> Path:
    path = c.local(root, relative, exists=False)
    path.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def sheet_lock(sidecar: Path) -> Iterator[None]:
    import studio
    root = studio.studio_root(sidecar.parent) or sidecar.parent
    with c.lock(root):
        yield


def _read(sidecar: Path, *, verify_files: bool = False) -> dict:
    from character_sheet import validate_sidecar
    return validate_sidecar(c.load(sidecar), sheet_root=sidecar.parent, verify_files=verify_files)


def _write(sidecar: Path, value: dict) -> None:
    from character_sheet import sheet_status, validate_sidecar
    value['sheet_status'] = sheet_status(value)
    validate_sidecar(value, sheet_root=sidecar.parent, verify_files=False)
    c.atomic_write_json(sidecar, value)


def _image_metadata(raw: bytes) -> dict:
    from PIL import Image
    with Image.open(io.BytesIO(raw)) as image:
        width, height = image.size
        fmt = image.format
        image.verify()
    formats = {'PNG': ('image/png', '.png'), 'JPEG': ('image/jpeg', '.jpg'), 'WEBP': ('image/webp', '.webp')}
    if fmt not in formats or min(width, height) < 1:
        raise ValueError('a sheet artifact must be a decoded PNG, JPEG or WebP image')
    media, suffix = formats[fmt]
    return {'sha256': c.digest(raw), 'width': width, 'height': height, 'media_type': media, 'suffix': suffix}


def _descriptor(image: dict, provenance_sha256: str, kind: str) -> dict:
    identifier = c.content_id({'image_sha256': image['sha256'], 'provenance_sha256': provenance_sha256})
    folder = f'{STORE}/{identifier}'
    return {'artifact_id': identifier,
            'image': {key: value for key, value in image.items() if key != 'suffix'} | {'path': folder + '/image' + image['suffix']},
            'provenance': {'kind': kind, 'path': folder + '/provenance.json', 'sha256': provenance_sha256}}


def _package_files(package: Path) -> dict[str, bytes]:
    from character_sheet import _validate_ready_package
    from build_generation_payload import validate_generation_package_carrier_paths
    value = c.load(package)
    _validate_ready_package(value, field='sheet artwork package')
    result = {'package.json': c.read(package)}
    prepared = value.get('prepared_reference_set')
    if isinstance(prepared, dict):
        companion = validate_generation_package_carrier_paths(prepared, package_root=package.parent)
        if companion:
            directory = package.parent / companion
            if directory.is_symlink():
                raise ValueError('package companion must not be a symbolic link')
            for path in sorted(directory.rglob('*')):
                if path.is_symlink():
                    raise ValueError('package companion must contain no symbolic links')
                if path.is_file():
                    result[path.relative_to(package.parent).as_posix()] = c.read(path)
    if value.get('artifact_type') == 'upscale-package':
        from upscale_package import verify_upscale_package
        verify_upscale_package(value, package_root=package.parent)
        for key in ('source_image', 'output_image'):
            item = value[key]
            result[item['path']] = c.read(c.local(package.parent, item['path']))
    return result


def publish(sheet_root: Path, image: Path | bytes, *, kind: str, recipe: dict,
            sources: Sequence[dict] = (), package: Path | None = None,
            origin: dict | None = None, attachments: Mapping[str, bytes] | None = None) -> dict:
    """Freeze image, complete provenance and portable package in one immutable directory.

    Source artifacts must already be present in this sheet's store. Copying from
    another sheet uses copy_artifact first, retaining the source content ID.
    Publication may leave an unselected immutable object after interruption;
    retrying uses that same object, and never overwrites another result.
    """
    sheet_root = sheet_root.resolve(strict=True)
    if kind not in KINDS or not isinstance(recipe, dict):
        raise ValueError('unknown sheet artwork kind or recipe')
    raw = c.read(image) if isinstance(image, Path) else image
    if not isinstance(raw, bytes):
        raise ValueError('sheet artwork needs image bytes')
    metadata = _image_metadata(raw)
    for source in sources:
        verify_artifact(source, sheet_root)
    files = dict(attachments or {})
    if package is not None:
        overlap = set(files) & set(_package_files(package))
        if overlap:
            raise ValueError('package attachments collide: ' + ', '.join(sorted(overlap)))
        files.update(_package_files(package))
    if kind in {'generation', 'upscale'} and package is None:
        raise ValueError('generated or upscaled artwork requires its committed package')
    if kind in {'crop', 'resize', 'composite', 'shared'} and not sources:
        raise ValueError('local artwork requires exact source artifacts')
    provenance = {'artifact_type': 'sheet-fill-provenance', 'kind': kind,
                  'image': metadata, 'recipe': copy.deepcopy(recipe),
                  'sources': copy.deepcopy(list(sources)), 'origin': copy.deepcopy(origin),
                  'files': {name: c.digest(contents) for name, contents in sorted(files.items())}}
    prov_raw = c.encoded(provenance)
    descriptor = _descriptor(metadata, c.digest(prov_raw), kind)
    parent = _safe_directory(sheet_root, STORE)
    destination = c.local(sheet_root, f'{STORE}/{descriptor["artifact_id"]}', exists=False)
    with c.lock(sheet_root):
        if destination.exists():
            verify_artifact(descriptor, sheet_root)
            return descriptor
        staging = Path(tempfile.mkdtemp(prefix='.publish-', dir=parent))
        try:
            c.atomic(staging / ('image' + metadata['suffix']), raw)
            c.atomic(staging / 'provenance.json', prov_raw)
            from studio_activity import timestamp
            c.atomic(staging / 'publication.json', c.encoded({'artifact_id': descriptor['artifact_id'],
                     'recorded_at': timestamp(), 'origin': copy.deepcopy(origin)}))
            for name, contents in files.items():
                path = c.local(staging, name, exists=False)
                if name in {'provenance.json', 'image' + metadata['suffix']}:
                    raise ValueError('attachment collides with immutable artwork')
                c.atomic(path, contents)
            c.publish_directory(staging, destination)
            c.fsync_dir(parent)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
    verify_artifact(descriptor, sheet_root)
    return descriptor


def verify_artifact(artifact: Any, sheet_root: Path, *, seen: set[str] | None = None,
                    cache: dict | None = None) -> dict:
    """Verify identity, decoded image, complete attachments and recursive sources."""
    cache_key = (str(sheet_root.resolve()), c.content_id(artifact))
    if cache is not None and cache_key in cache:
        return cache[cache_key]
    c.exact(artifact, {'artifact_id', 'image', 'provenance'}, 'sheet artifact')
    image, provenance = artifact['image'], artifact['provenance']
    c.exact(image, {'path', 'sha256', 'width', 'height', 'media_type'}, 'sheet image')
    c.exact(provenance, {'kind', 'path', 'sha256'}, 'sheet provenance')
    c.sha(artifact['artifact_id']); c.sha(image['sha256']); c.sha(provenance['sha256'])
    if provenance['kind'] not in KINDS:
        raise ValueError('unknown sheet provenance kind')
    expected_id = c.content_id({'image_sha256': image['sha256'], 'provenance_sha256': provenance['sha256']})
    if artifact['artifact_id'] != expected_id:
        raise ValueError('sheet artifact ID differs from its image/provenance pair')
    folder = f'{STORE}/{expected_id}'
    if provenance['path'] != folder + '/provenance.json':
        raise ValueError('provenance is not in its immutable artifact directory')
    raw = c.read(_file(sheet_root, provenance['path'], provenance['sha256']))
    value = c.decode(raw)
    c.exact(value, {'artifact_type', 'kind', 'image', 'recipe', 'sources', 'origin', 'files'}, 'sheet provenance record')
    if value['artifact_type'] != 'sheet-fill-provenance' or value['kind'] != provenance['kind']:
        raise ValueError('sheet provenance type differs from its descriptor')
    if not isinstance(value['recipe'], dict) or not isinstance(value['sources'], list) or not isinstance(value['files'], dict):
        raise ValueError('invalid sheet provenance recipe, sources or files')
    observed = _image_metadata(c.read(_file(sheet_root, image['path'], image['sha256'])))
    if _descriptor(observed, provenance['sha256'], value['kind']) != artifact or value['image'] != observed:
        raise ValueError('decoded image differs from its committed descriptor')
    for name, sha in value['files'].items():
        _file(sheet_root / folder, name, c.sha(sha))
    if value['kind'] in {'generation', 'upscale'}:
        from character_sheet import _validate_ready_package
        if 'package.json' not in value['files']:
            raise ValueError('generated artwork lacks its package')
        _validate_ready_package(c.load(sheet_root / folder / 'package.json'), field='sheet artwork')
    if value['kind'] in {'crop', 'resize', 'composite', 'shared'} and not value['sources']:
        raise ValueError('local artwork lacks its exact source artifacts')
    visited = set() if seen is None else seen
    if expected_id in visited:
        raise ValueError('cyclic sheet provenance')
    visited.add(expected_id)
    try:
        for source in value['sources']:
            verify_artifact(source, sheet_root, seen=visited, cache=cache)
    finally:
        visited.remove(expected_id)
    if cache is not None:
        cache[cache_key] = value
    return value


def copy_artifact(artifact: dict, source_root: Path, target_root: Path) -> dict:
    """Replicate immutable artwork without changing its identity or origin."""
    value = verify_artifact(artifact, source_root)
    for source in value['sources']:
        copy_artifact(source, source_root, target_root)
    folder = f'{STORE}/{artifact["artifact_id"]}'
    target = c.local(target_root, folder, exists=False)
    if source_root.resolve() == target_root.resolve():
        return copy.deepcopy(artifact)
    parent = _safe_directory(target_root, STORE)
    with c.lock(target_root):
        if not target.exists():
            staging = Path(tempfile.mkdtemp(prefix='.copy-', dir=parent))
            try:
                source_dir = c.local(source_root, folder)
                for path in source_dir.rglob('*'):
                    if path.is_symlink():
                        raise ValueError('immutable artwork contains a symbolic link')
                    if path.is_file():
                        c.atomic(c.local(staging, path.relative_to(source_dir).as_posix(), exists=False), c.read(path))
                c.publish_directory(staging, target)
                c.fsync_dir(parent)
            finally:
                if staging.exists(): shutil.rmtree(staging)
        verify_artifact(artifact, target_root)
    return copy.deepcopy(artifact)


def register_candidates(sidecar: Path, values: Sequence[tuple[str, dict]]) -> dict:
    """Atomically add fully verified candidates to any number of slots."""
    with sheet_lock(sidecar):
        state = _read(sidecar)
        original_sha = c.content_id(state)
        for slot_id, artifact in values:
            if not isinstance(slot_id, str) or not __import__('re').fullmatch(r'[a-z0-9][a-z0-9._-]*', slot_id):
                raise ValueError('invalid sheet slot ID')
            verify_artifact(artifact, sidecar.parent)
            slot = state['slots'].setdefault(slot_id, empty_slot())
            current = current_artifact(slot)
            if current is not None and current['artifact_id'] == artifact['artifact_id']:
                continue
            if not any(item['artifact_id'] == artifact['artifact_id'] for item in slot['candidates']):
                slot['candidates'].append(copy.deepcopy(artifact))
        if c.content_id(state) != original_sha:
            _write(sidecar, state)
        import studio_activity as activity
        projection_status = activity.changed(sidecar, 'sheet-candidates-recorded', revision=c.content_id(state),
            details={'candidates': [{'slot': slot, 'artifact_id': item['artifact_id']} for slot, item in values]})
        return {'projection': projection_status, 'path': str(sidecar), 'sha256': c.sha256_file(sidecar),
                'accepted_sha256': accepted_sha256(state),
                'candidates': [{'slot': slot, 'artifact_id': value['artifact_id']} for slot, value in values]}


def reject_candidate(sidecar: Path, slot_id: str, artifact_id: str, *, by: str, reason: str) -> dict:
    """Dismiss a recorded candidate with a stated reason; the artifact stays in the store."""
    with sheet_lock(sidecar):
        state = _read(sidecar)
        slot = state['slots'].get(slot_id)
        if slot is None:
            raise ValueError('unknown sheet slot')
        c.text(by, 'rejection author')
        c.text(reason, 'rejection reason')
        artifact = next((item for item in slot['candidates'] if item['artifact_id'] == artifact_id), None)
        if artifact is None:
            raise ValueError('rejection names a candidate that is not recorded in this slot')
        verify_artifact(artifact, sidecar.parent)
        slot['candidates'] = [item for item in slot['candidates'] if item['artifact_id'] != artifact_id]
        _write(sidecar, state)
        import studio_activity as activity
        projection_status = activity.changed(sidecar, 'sheet-candidate-rejected', revision=c.content_id(state),
            details={'slot': slot_id, 'artifact_id': artifact_id, 'by': by, 'reason': reason})
        return {'ok': True, 'rejected': artifact_id, 'projection': projection_status}


def reoffer(sidecar: Path, slot_id: str, artifact_id: str) -> dict:
    """Re-present an exact historical artifact; this is not adoption or new provenance."""
    with sheet_lock(sidecar):
        state = _read(sidecar)
        slot = state['slots'].get(slot_id)
        if slot is None:
            raise ValueError('unknown sheet slot')
        current = current_artifact(slot)
        if current is not None and current['artifact_id'] == artifact_id:
            return {'ok': True, 'already_current': True, 'artifact_id': artifact_id}
        source = next((entry['artifact'] for entry in reversed(slot['history'])
                       if entry['artifact']['artifact_id'] == artifact_id), None)
        if source is None:
            raise ValueError('reoffer requires an exact historical artifact in this slot')
        verify_artifact(source, sidecar.parent)
        result = register_candidates(sidecar, [(slot_id, source)])
        import studio_activity as activity
        result['projection'] = activity.changed(sidecar, 'sheet-history-reoffered', revision=c.content_id(_read(sidecar)),
            details={'slot': slot_id, 'artifact_id': artifact_id, 'adopted': False})
        return {'ok': True, **result, 'adopted': False}


def draft_adoption(sidecar: Path, slot_id: str, artifact_id: str) -> dict:
    state = _read(sidecar)
    slot = state['slots'].get(slot_id)
    if slot is None or not any(item['artifact_id'] == artifact_id for item in slot['candidates']):
        raise ValueError('adoption must choose a recorded candidate')
    current = current_artifact(slot)
    return {'artifact_type': 'sheet-adoption-decision', 'sheet': str(sidecar.resolve()), 'slot': slot_id,
            'artifact_id': artifact_id, 'expected_current': current['artifact_id'] if current else None,
            'by': '', 'at': '', 'reason': '', 'evidence': {'path': '', 'sha256': '', 'locator': ''}, 'basis': None}


def _validate_decision(decision: dict, sidecar: Path, evidence_root: Path) -> bytes:
    c.exact(decision, {'artifact_type', 'sheet', 'slot', 'artifact_id', 'expected_current', 'by', 'at', 'reason', 'evidence', 'basis'}, 'sheet adoption')
    if decision['artifact_type'] != 'sheet-adoption-decision' or decision['sheet'] != str(sidecar.resolve()):
        raise ValueError('adoption is scoped to another sheet')
    for key in ('slot', 'by', 'at', 'reason'): c.text(decision[key], 'adoption ' + key)
    c.sha(decision['artifact_id'])
    if decision['expected_current'] is not None: c.sha(decision['expected_current'])
    try:
        stamp = datetime.fromisoformat(decision['at'].replace('Z', '+00:00'))
    except (ValueError, AttributeError) as exc:
        raise ValueError('adoption requires an actual ISO timestamp') from exc
    if stamp.tzinfo is None:
        raise ValueError('adoption time must include a timezone')
    evidence = decision['evidence']
    c.exact(evidence, {'path', 'sha256', 'locator'}, 'adoption evidence')
    c.text(evidence['locator'], 'adoption evidence locator')
    raw = c.read(c.local(evidence_root, evidence['path']))
    if c.digest(raw) != c.sha(evidence['sha256']):
        raise ValueError('adoption evidence bytes changed')
    return raw


def _production_decision(provenance: dict, decision: dict, sidecar: Path) -> None:
    """A Production candidate is adopted only under its own recorded adopt claim."""
    origin = provenance.get('origin') or {}
    if origin.get('kind') != 'production':
        return
    import production_workflow as w
    import studio
    root = studio.require_studio(sidecar.parent)
    basis = decision.get('basis')
    if not isinstance(basis, dict) or set(basis) != {'kind', 'claim', 'approval'} or basis['kind'] != 'production':
        raise ValueError('use production_workflow adopt for a Production sheet candidate')
    _, _, _, rows = w.load_run(root, origin['run'])
    claim = w.find(rows, 'adoption-claim', basis['claim'])
    payload = claim['data']['intent']['payload']
    if payload['candidate'] != origin['candidate'] or payload['iteration'] != origin['iteration_id'] or payload['character'] != origin['character'] or payload['approval_sha256'] != c.content_id(basis['approval']):
        raise ValueError('sheet adoption claim differs from its Production candidate')


def adopt(sidecar: Path, decision: dict, *, evidence_root: Path) -> dict:
    """Compare-and-swap one selection; record exact approval and retain the prior one."""
    with sheet_lock(sidecar):
        evidence = _validate_decision(decision, sidecar, evidence_root)
        state = _read(sidecar)
        slot = state['slots'].get(decision['slot'])
        if slot is None:
            raise ValueError('adoption names an unknown slot')
        current = slot['current']
        decision_sha = c.content_id(decision)
        if current is not None and current['approval']['decision_sha256'] == decision_sha:
            return {'adopted': True, 'already_adopted': True, 'current': current}
        current_id = current['artifact']['artifact_id'] if current else None
        if current_id != decision['expected_current']:
            raise ValueError('current artwork changed after the adoption decision was drafted')
        artifact = next((item for item in slot['candidates'] if item['artifact_id'] == decision['artifact_id']), None)
        if artifact is None:
            raise ValueError('adoption must choose a recorded candidate')
        provenance = verify_artifact(artifact, sidecar.parent)
        _production_decision(provenance, decision, sidecar)
        folder = _safe_directory(sidecar.parent, f'{APPROVALS}/{decision_sha}')
        for name, raw in [('decision.json', c.encoded(decision)), ('evidence', evidence)]:
            target = c.local(folder, name, exists=False)
            if target.exists() and c.read(target) != raw:
                raise ValueError('immutable adoption evidence changed')
            if not target.exists(): c.atomic(target, raw)
        approval = {'decision_sha256': decision_sha,
                    'decision_path': f'{APPROVALS}/{decision_sha}/decision.json',
                    'evidence_path': f'{APPROVALS}/{decision_sha}/evidence',
                    'evidence_sha256': c.digest(evidence)}
        accepted = {'artifact': copy.deepcopy(artifact), 'approval': approval}
        if current is not None:
            slot['history'].append(copy.deepcopy(current))
        slot['current'] = accepted
        slot['candidates'] = [item for item in slot['candidates'] if item['artifact_id'] != artifact['artifact_id']]
        _write(sidecar, state)
        import studio_activity as activity
        projection_status = activity.changed(sidecar, 'sheet-adopted', revision=c.content_id(state),
            details={'slot': decision['slot'], 'artifact_id': artifact['artifact_id'],
                     'superseded': current_id, 'decision_sha256': decision_sha})
        return {'projection': projection_status, 'adopted': True, 'already_adopted': False, 'current': accepted}


def verify_acceptance(accepted: Any, sheet_root: Path, slot_id: str, *, cache: dict | None = None) -> None:
    c.exact(accepted, {'artifact', 'approval'}, 'sheet acceptance')
    verify_artifact(accepted['artifact'], sheet_root, cache=cache)
    approval = accepted['approval']
    c.exact(approval, {'decision_sha256', 'decision_path', 'evidence_path', 'evidence_sha256'}, 'sheet acceptance evidence')
    decision = c.load(_file(sheet_root, approval['decision_path']))
    if c.content_id(decision) != approval['decision_sha256'] or decision.get('artifact_id') != accepted['artifact']['artifact_id'] or decision.get('slot') != slot_id:
        raise ValueError('sheet approval differs from its exact selected artwork')
    _file(sheet_root, approval['evidence_path'], approval['evidence_sha256'])
    if decision.get('evidence', {}).get('sha256') != approval['evidence_sha256']:
        raise ValueError('sheet approval differs from the saved author evidence')


def from_iteration(root: Path, character: str, row: dict) -> dict:
    """The Studio iteration remains the Production candidate's owner."""
    import studio
    sheet = studio.character_home(root, character) / 'sheet'
    if not row.get('package') or not row.get('result'):
        raise ValueError('sheet candidate requires recorded image and package provenance')
    image = c.local(root, row['result']['path'])
    package = c.local(root, row['package']['path'])
    if c.sha256_file(image) != row['result']['sha256'] or c.sha256_file(package) != row['package']['sha256']:
        raise ValueError('Studio image/package bytes changed')
    value = c.load(package)
    kind = 'upscale' if value.get('artifact_type') == 'upscale-package' else 'generation'
    origin = {'kind': 'production' if row.get('production') else 'external-import',
              'character': character, 'iteration_id': row['iteration_id'], **(row.get('production') or {})}
    attachments = {}
    for key in ('request', 'response', 'answer'):
        item = row.get(key)
        if item:
            raw = c.read(c.local(root, item['path']))
            if c.digest(raw) != item['sha256']:
                raise ValueError('Studio response/request evidence changed')
            attachments[key + '.json'] = raw
    sources = []
    recipe = {'model': value.get('upscaler_model') if kind == 'upscale' else value.get('model')}
    if kind == 'upscale' and row.get('production'):
        import production_workflow as workflow
        run_dir, prepared, _, _ = workflow.load_run(root, row['production']['run'])
        selector = prepared['task']['upscale'].get('derivation')
        if selector is not None:
            source_sheet = c.local(root, selector['sheet']).parent
            # Execution froze the exact descriptor before dispatch. Recovery does
            # not require that it still be the current selection afterward.
            source = c.load(run_dir / 'sheet-derivation.json')
            verify_artifact(source, source_sheet)
            if source['image']['sha256'] != value['source_image']['sha256']:
                raise ValueError('recorded upscale source differs from its frozen sheet derivation')
            copy_artifact(source, source_sheet, sheet)
            sources = [source]
            recipe.update(source_slot=selector['slot'], scale_factor=value['scale_factor'])
    artifact = publish(sheet, image, kind=kind, recipe=recipe, sources=sources,
                       package=package, origin=origin, attachments=attachments)
    register_candidates(sheet / 'sheet-data.json', [(row['slot'], artifact)])
    return artifact


def source_from_current(sidecar: Path, slot_id: str) -> dict:
    state = _read(sidecar)
    artifact = current_artifact(state['slots'].get(slot_id))
    if artifact is None:
        raise ValueError('source panel has no accepted artwork: ' + slot_id)
    verify_acceptance(state['slots'][slot_id]['current'], sidecar.parent, slot_id)
    return artifact


def crop(sidecar: Path, source_slot: str, target_slot: str, rectangle: Sequence[int], *, scale: int = 1) -> dict:
    """Crop accepted bytes; optional local Lanczos scaling is named, never called neural upscale."""
    from PIL import Image
    if len(rectangle) != 4 or any(type(v) is not int for v in rectangle):
        raise ValueError('crop must be integer x,y,width,height')
    if type(scale) is not int or not 1 <= scale <= 16:
        raise ValueError('local scale must be an integer from 1 to 16')
    with sheet_lock(sidecar):
        source = source_from_current(sidecar, source_slot)
        x, y, width, height = rectangle
        if x < 0 or y < 0 or min(width, height) < 1 or x + width > source['image']['width'] or y + height > source['image']['height']:
            raise ValueError('crop rectangle is outside the accepted source image')
        with Image.open(_file(sidecar.parent, source['image']['path'], source['image']['sha256'])) as original:
            image = original.convert('RGBA').crop((x, y, x + width, y + height))
        if scale != 1:
            image = image.resize((width * scale, height * scale), Image.Resampling.LANCZOS)
        output = io.BytesIO(); image.save(output, format='PNG')
        artifact = publish(sidecar.parent, output.getvalue(), kind='crop', sources=[source],
            recipe={'source_slot': source_slot, 'crop': {'x': x, 'y': y, 'width': width, 'height': height},
                    'resize': {'algorithm': 'Pillow.LANCZOS', 'scale': scale}})
        register_candidates(sidecar, [(target_slot, artifact)])
        return artifact


def share(source_sidecar: Path, source_slot: str, targets: Sequence[tuple[Path, str]]) -> dict:
    """Supply the same accepted pixels to other slots; each target still needs its own approval.

    Registration is idempotent per target. All target sidecars are checked before
    any is written; an interrupted multi-sheet supply can be safely repeated.
    It does not transfer the source author's adoption to the target slots.
    """
    source = source_from_current(source_sidecar, source_slot)
    source_state = _read(source_sidecar)
    acceptance = source_state['slots'][source_slot]['current']
    for sidecar, _ in targets: _read(sidecar)
    result = []
    for sidecar, slot_id in targets:
        with sheet_lock(sidecar):
            copy_artifact(source, source_sidecar.parent, sidecar.parent)
            artifact = publish(sidecar.parent, _file(sidecar.parent, source['image']['path']), kind='shared', sources=[source],
                recipe={'source_slot': source_slot, 'source_acceptance_sha256': c.content_id(acceptance)},
                attachments={'source-acceptance.json': c.encoded(acceptance)})
            register_candidates(sidecar, [(slot_id, artifact)])
            result.append({'sheet': str(sidecar), 'slot': slot_id, 'artifact': artifact})
    return {'shared_image_sha256': source['image']['sha256'], 'targets': result, 'adopted': False}


def compose_scale(target_sidecar: Path, target_slot: str, entries: Sequence[dict], *,
                  pixels_per_unit: float, padding: int = 24, gap: int = 24, background: str = '#ffffff') -> dict:
    """Align declared baselines and measured height segments, retaining all source pixels.

    Each entry names an accepted source, a crop bbox, the top/baseline y values
    used to measure its declared height, and a label. Anatomy is never inferred
    from opaque-pixel bounds; ears, tails and clothing are included only through
    the author's explicit measurement segment.
    """
    from PIL import Image, ImageColor, ImageDraw
    import math
    if not entries or isinstance(pixels_per_unit, bool) or not isinstance(pixels_per_unit, (int, float)) or not math.isfinite(pixels_per_unit) or pixels_per_unit <= 0:
        raise ValueError('scale composition requires sources and finite positive pixels_per_unit')
    if type(padding) is not int or type(gap) is not int or min(padding, gap) < 0:
        raise ValueError('padding and gap must be nonnegative integers')
    bg = ImageColor.getrgb(background)
    images, sources, recipes = [], [], []
    for entry in entries:
        c.exact(entry, {'sheet', 'slot', 'bbox', 'height', 'measurement_top', 'baseline', 'label'}, 'scale source')
        source_sidecar = Path(entry['sheet']).resolve(strict=True)
        source = source_from_current(source_sidecar, entry['slot'])
        bbox = entry['bbox']
        if not isinstance(bbox, list) or len(bbox) != 4 or any(type(v) is not int for v in bbox):
            raise ValueError('scale bbox must be integer x,y,width,height')
        x, y, width, height = bbox
        top, baseline, declared_height = entry['measurement_top'], entry['baseline'], entry['height']
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in (top, baseline, declared_height)) or declared_height <= 0 or not y <= top < baseline <= y + height:
            raise ValueError('measurement_top and baseline must delimit the declared height within the crop')
        if x < 0 or y < 0 or min(width, height) < 1 or x + width > source['image']['width'] or y + height > source['image']['height']:
            raise ValueError('scale bbox is outside the accepted source image')
        factor = float(declared_height) * pixels_per_unit / (baseline - top)
        new_size = (max(1, round(width * factor)), max(1, round(height * factor)))
        if new_size[0] * new_size[1] > 100_000_000:
            raise ValueError('scale composition source exceeds 100 megapixels')
        with Image.open(_file(source_sidecar.parent, source['image']['path'], source['image']['sha256'])) as im:
            scaled = im.convert('RGBA').crop((x, y, x + width, y + height)).resize(new_size, Image.Resampling.LANCZOS)
        above = round((baseline - y) * factor)
        images.append((scaled, above, str(entry['label'])))
        copy_artifact(source, source_sidecar.parent, target_sidecar.parent)
        sources.append(source)
        recipes.append({key: value for key, value in entry.items() if key != 'sheet'} | {'artifact_id': source['artifact_id'], 'factor': factor, 'output_size': list(new_size), 'baseline_offset': above})
    ascent = max(row[1] for row in images); descent = max(row[0].height - row[1] for row in images)
    size = (2 * padding + sum(row[0].width for row in images) + gap * (len(images) - 1), 2 * padding + ascent + descent + 30)
    if size[0] * size[1] > 100_000_000:
        raise ValueError('scale composition canvas exceeds 100 megapixels')
    canvas = Image.new('RGBA', size, (*bg, 255)); draw = ImageDraw.Draw(canvas); left = padding
    for image, above, label in images:
        canvas.alpha_composite(image, (left, padding + ascent - above))
        draw.text((left, size[1] - padding - 18), label, fill='#000000')
        left += image.width + gap
    raw = io.BytesIO(); canvas.save(raw, format='PNG')
    artifact = publish(target_sidecar.parent, raw.getvalue(), kind='composite', sources=sources,
        recipe={'operation': 'declared-scale-comparison', 'pixels_per_unit': pixels_per_unit,
                'padding': padding, 'gap': gap, 'background': background, 'entries': recipes,
                'baseline_y': padding + ascent})
    register_candidates(target_sidecar, [(target_slot, artifact)])
    return artifact
