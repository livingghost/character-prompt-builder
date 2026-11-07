#!/usr/bin/env python3
"""Pin an accepted Studio image and its approval for reference preparation.

The source identifies one current slot, not an arbitrary file of matching pixels.
Live preparation checks that selection again. Recorded verification reads the
same approval and artwork from the package companion, without granting a send.
"""
from __future__ import annotations
import operation_context as _operation_context
import copy
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
import json
import re
from typing import Any, Mapping, TYPE_CHECKING

import execution_contract as c
import runtime_snapshot
from owned_json import mutable

if TYPE_CHECKING:
    from studio import StudioRead

SOURCE_FIELDS = frozenset({'kind', 'studio_root', 'studio_id', 'character', 'sheet', 'slot',
    'artifact_id', 'acceptance_sha256', 'proof_sha256', 'resolved_path', 'media_type', 'sha256'})
PROOF_FIELDS = frozenset({'artifact_type', 'studio_root', 'studio_id', 'character', 'sheet', 'slot',
    'acceptance', 'adoption', 'identity'})
ID = re.compile(r'^[a-z0-9][a-z0-9._-]*$')


class ReferenceReads:
    """Own current Studio inputs for one stable reference read phase.

    A resolver can cover several Studios. Each root belongs to its current
    public or transaction scope, and an owned mutation ends its phase. Source,
    identity and continuity checks receive the same decoded StudioRead instead
    of independently reopening the same records.
    """

    def __init__(self) -> None:
        self._studios: dict[str, tuple[object | None, StudioRead]] = {}

    def studio(self, root: Path) -> StudioRead:
        import studio
        root = studio.require_studio(root).resolve()
        identity = str(root)
        scope = runtime_snapshot.check_scope(root)
        phase = None
        if scope is not None:
            key = ('studio-read-phase', identity)
            if key not in scope:
                scope[key] = object()
            phase = scope[key]
        held = self._studios.get(identity)
        if held is None or held[0] is not phase:
            held = phase, studio.StudioRead(root)
            self._studios[identity] = held
        return held[1]


def reference_reads() -> ReferenceReads:
    """Acquire the reference owner at a public API's current read boundary."""
    scope = runtime_snapshot.call_scope()
    if scope is None:
        return ReferenceReads()
    key = ('studio-reference-reads',)
    if key not in scope:
        scope[key] = ReferenceReads()
    return scope[key]


def _origin_root(value: str) -> PurePosixPath | PureWindowsPath:
    """Interpret a recorded origin without requiring its operating system or files."""
    windows = PureWindowsPath(value)
    if windows.drive and windows.is_absolute():
        return windows
    posix = PurePosixPath(value)
    if not posix.is_absolute():
        raise ValueError('Studio reference root must be an absolute path')
    return posix


def _owner(source: Mapping[str, Any]) -> None:
    c.exact(source, SOURCE_FIELDS, 'Studio reference source')
    if source['kind'] != 'studio-artifact':
        raise ValueError('Studio reference source kind must be studio-artifact')
    for key in ('studio_root', 'studio_id', 'character', 'sheet', 'slot', 'resolved_path', 'media_type'):
        c.text(source[key], 'Studio reference ' + key)
    for key in ('artifact_id', 'acceptance_sha256', 'proof_sha256', 'sha256'):
        c.sha(source[key])
        if source[key] == '0' * 64:
            raise ValueError('Studio reference ' + key + ' must be a nonzero hash')
    if not ID.fullmatch(source['slot']):
        raise ValueError('Studio reference slot requires a canonical identifier')
    import studio
    if not studio.valid_character_id(source['character']):
        raise ValueError('Studio reference requires a canonical Studio character ID')
    _origin_root(source['studio_root'])
    if source['sheet'] != f"characters/{source['character']}/sheet/sheet-data.json":
        raise ValueError('Studio reference sheet differs from its character owner')
    if source['media_type'] not in {'image/png', 'image/jpeg', 'image/webp'}:
        raise ValueError('Studio artwork must be a supported raster image')


def _source(proof: dict) -> dict:
    accepted = proof['acceptance']
    artifact = accepted['artifact']
    image = artifact['image']
    root = _origin_root(proof['studio_root'])
    sheet_root = root / PurePosixPath(proof['sheet']).parent
    return {'kind': 'studio-artifact', **{k: proof[k] for k in ('studio_root', 'studio_id', 'character', 'sheet', 'slot')},
            'artifact_id': artifact['artifact_id'], 'acceptance_sha256': c.content_id(accepted),
            'proof_sha256': c.content_id(proof), 'resolved_path': str(sheet_root / image['path']),
            'media_type': image['media_type'], 'sha256': image['sha256']}


def _decision(accepted: dict, sheet_root: Path, owner_sheet: str, slot: str, *, cache=None) -> dict:
    import sheet_artifacts as fills
    value = fills.verify_acceptance(accepted, sheet_root, slot, cache=cache)
    c.exact(value, {'artifact_type', 'sheet', 'slot', 'artifact_id', 'expected_current', 'by', 'at', 'reason', 'evidence', 'basis'}, 'recorded adoption decision')
    if value['artifact_type'] != 'sheet-adoption-decision' or value['sheet'] != owner_sheet:
        raise ValueError('recorded adoption belongs to another sheet')
    for key in ('by', 'reason', 'at'):
        c.text(value[key], 'recorded adoption ' + key)
    try:
        timestamp = datetime.fromisoformat(value['at'].replace('Z', '+00:00'))
    except (ValueError, AttributeError) as exc:
        raise ValueError('recorded adoption has no valid timestamp') from exc
    if timestamp.tzinfo is None:
        raise ValueError('recorded adoption timestamp requires a timezone')
    c.exact(value['evidence'], {'path', 'sha256', 'locator'}, 'recorded adoption evidence')
    c.text(value['evidence']['locator'], 'recorded adoption evidence locator')
    return value


def _read_current(root: Path, character: str, slot: str, *, read=None) -> tuple[dict, dict]:
    import studio
    root = studio.require_studio(root)
    if str(root.resolve()) != str(root) or any(p.is_symlink() for p in [root, *root.parents]):
        raise ValueError('Studio reference root must be canonical and must not traverse a symlink')
    read = read or reference_reads().studio(root)
    read.require_root(root)
    return read.current_reference_view(character, slot)


def _load_current(root: Path, character: str, slot: str, *, read) -> tuple[dict, dict]:
    import studio
    import sheet_artifacts as fills
    import adoption_workflow as adoption
    home = read.home(character)
    studio.validate_recording_target(root, character, slot, writable=False, read=read)
    sheet = c.local(root, (home / 'sheet/sheet-data.json').relative_to(root).as_posix())
    current = read.sheet(character)['slots'].get(slot, {}).get('current')
    if current is None:
        raise ValueError(f'{character}/{slot}: no current accepted artwork; candidates and history are not canon')
    decision = _decision(current, sheet.parent, str(sheet), slot, cache=read.artifacts)
    proof = {'artifact_type': 'studio-reference-proof', 'studio_root': str(root),
             'studio_id': read.document['studio_id'],
             'character': character, 'sheet': sheet.relative_to(root).as_posix(), 'slot': slot,
             'acceptance': copy.deepcopy(current), 'adoption': None, 'identity': None}
    provenance = fills.verify_artifact(current['artifact'], sheet.parent, cache=read.artifacts)
    origin = provenance.get('origin') or {}
    iteration = origin.get('iteration_id')
    if iteration is not None:
        if origin.get('character') != character:
            raise ValueError('accepted artwork was recorded for another Studio character')
        # A current reference concerns this exact adoption, not every historical
        # Production run stored beside it. The run below verifies its own origin.
        row = copy.deepcopy(studio._find(read.raw_iterations(character), iteration))
        if row.get('production') is not None:
            row['status'] = row.get('adoption_status', 'none')
        journal = read.journal(character, iteration)
        if (row['status'] != 'accepted' or row['slot'] != slot or
                row['result']['sha256'] != current['artifact']['image']['sha256'] or
                journal.get('status') not in {'sheet-bound', 'catalog-registered'} or journal.get('next_action') is not None):
            raise ValueError('selected Studio adoption is incomplete or no longer accepted')
        approval = adoption.validate_approval(journal.get('approval'), character, row)
        # The same pixels with another author's acceptance remain distinct.
        if decision != journal.get('sheet_decision') or current != (journal.get('sheet_binding') or {}).get('current'):
            raise ValueError('current sheet acceptance differs from its recorded Studio decision')
        initial = adoption.validate_approval(
            c.load(fills._file(sheet.parent, current['approval']['evidence_path'])), character, row)
        if initial != approval and not (initial['scope'] == 'sheet' and approval['scope'] == 'catalog'
                                       and initial['influence'] == approval['influence']):
            raise ValueError('current Studio adoption differs from its original sheet approval')
        if journal['status'] != {'sheet': 'sheet-bound', 'catalog': 'catalog-registered'}[approval['scope']]:
            raise ValueError('current Studio adoption has not completed its approved scope')
        if decision.get('basis') and decision['basis'].get('kind') == 'production':
            if origin.get('kind') != 'production' or row.get('production') != {
                    'run': origin.get('run'), 'candidate': origin.get('candidate')}:
                raise ValueError('current sheet acceptance differs from its Production candidate')
            if decision['basis'].get('approval') != initial:
                raise ValueError('current sheet decision differs from its original approval evidence')
            # A catalog promotion keeps the original sheet decision and adds a
            # separate approval and claim for registering that same reference.
            loaded = read.run(origin['run'])
            fills._production_decision(provenance, decision, sheet, loaded=loaded)
            adoption.require_production_claim(root, character, row, initial, decision['basis']['claim'], read=read)
            adoption.require_production_claim(root, character, row, approval, journal.get('production_claim'), read=read)
            import production_workflow as workflow
            _, _, _, records = loaded
            workflow._studio_adoption_result(
                {'character': character, 'iteration_id': iteration, 'scope': approval['scope']},
                current['artifact']['image']['sha256'], records, journal, row)
        elif origin.get('kind') == 'production':
            raise ValueError('Production artwork needs its completed adoption claim')
        proof['adoption'] = {'iteration_id': iteration, 'approval': copy.deepcopy(approval)}
        if approval['influence'] == 'identity':
            from visual_continuity import adoption_subject
            subject = adoption_subject(root, character, row, approval, read=read)
            proof['identity'] = {key: copy.deepcopy(subject[key]) for key in ('character_id', 'continuity')}
    return _source(proof), proof


@runtime_snapshot.operation
def current_source(root: Path, character: str, slot: str, *, read=None) -> dict:
    """Resolve a current selection; read all IDs and hashes from authoritative records."""
    import studio
    root = studio.require_studio(root).absolute()
    source, _ = _read_current(root, character, slot, read=read)
    _owner(source)
    return mutable(source)


@runtime_snapshot.operation
def validate_source(source: Any, *, active: bool = True, source_archive: Path | None = None,
                    read=None, reads: ReferenceReads | None = None) -> dict:
    """Live current-selection validation or recorded byte evidence, never a fallback between them."""
    if not isinstance(source, Mapping):
        raise ValueError('Studio reference source must be an object')
    _owner(source)
    if active:
        import studio
        root = studio.require_studio(Path(source['studio_root']))
        read = read or (reads or reference_reads()).studio(root)
        expected, proof = _read_current(root, source['character'], source['slot'], read=read)
        if expected != source:
            raise ValueError('Studio reference no longer matches the exact current artifact and adoption')
        return proof
    if source_archive is None:
        raise ValueError('recorded Studio reference requires its package proof archive')
    archive = Path(source_archive).parent / 'studio' / source['proof_sha256']
    proof_path = c.local(archive, 'proof.json')
    proof = c.load(proof_path)
    c.exact(proof, PROOF_FIELDS, 'recorded Studio reference proof')
    if proof['artifact_type'] != 'studio-reference-proof' or _source(proof) != source:
        raise ValueError('recorded Studio reference proof differs from its sealed source')
    _decision(proof['acceptance'], archive / 'sheet', str(_origin_root(source['studio_root']) / source['sheet']), source['slot'])
    return proof


def _artifact_files(artifact: dict, root: Path, result: dict[str, bytes], seen: set[str]) -> None:
    import sheet_artifacts as fills
    ident = artifact['artifact_id']
    if ident in seen:
        return
    seen.add(ident)
    for key in ('image', 'provenance'):
        item = artifact[key]
        path = fills._file(root, item['path'], item['sha256'])
        result[item['path']] = c.read(path)
    provenance = c.decode(result[artifact['provenance']['path']])
    folder = PurePosixPath(artifact['provenance']['path']).parent
    for relative, sha in provenance['files'].items():
        stored = (folder / relative).as_posix()
        result[stored] = c.read(fills._file(root, stored, sha))
    for parent in provenance['sources']:
        _artifact_files(parent, root, result, seen)


@runtime_snapshot.operation
def archive_source(source: dict, companion: Path, *, read=None) -> list[dict]:
    """Copy exact approval and transitive artwork evidence into one portable companion."""
    import sheet_artifacts as fills
    import studio
    from publication_artifacts import ArtifactSet
    artifacts = ArtifactSet(companion)
    root = studio.require_studio(Path(source['studio_root']))
    with runtime_snapshot.public_call():
        read = read or reference_reads().studio(root)
        proof = validate_source(source, read=read)
        sheet_root = Path(source['studio_root']) / PurePosixPath(source['sheet']).parent
        files: dict[str, bytes] = {}
        accepted = proof['acceptance']
        _artifact_files(accepted['artifact'], sheet_root, files, set())
        approval = accepted['approval']
        for key, digest in (('decision_path', None), ('evidence_path', approval['evidence_sha256'])):
            path = approval[key]
            files[path] = c.read(fills._file(sheet_root, path, digest))
        target = companion / 'studio' / source['proof_sha256']
        for relative, raw in files.items():
            destination = c.local(target / 'sheet', relative, exists=False)
            if destination.exists():
                if c.read(destination) != raw:
                    raise ValueError('Studio reference evidence archive collision')
            else:
                c.atomic(destination, raw)
            artifacts.add(destination, raw)
        proof_path = target / 'proof.json'
        raw = c.encoded(proof)
        if proof_path.exists():
            if c.read(proof_path) != raw:
                raise ValueError('Studio reference proof archive collision')
        else:
            c.atomic(proof_path, raw)
        artifacts.add(proof_path, raw)
        validate_source(source, active=False, source_archive=companion / 'sources')
        return artifacts.files()


def identity_source(source: dict, *, root: Path, character_id: str | None, read=None,
                    reads: ReferenceReads | None = None) -> dict:
    if source['studio_root'] != str(root.absolute()):
        raise ValueError('Studio reference belongs to another Studio')
    proof = validate_source(source, read=read, reads=reads)
    identity = proof['identity']
    if not isinstance(identity, dict):
        raise ValueError('this accepted artwork has no explicit Studio identity adoption')
    if character_id is not None and identity['character_id'] != character_id:
        raise ValueError('Studio reference identity adoption belongs to another work character')
    return proof


@runtime_snapshot.operation
def build_binding(root: Path, character: str, slot: str, *, scope: dict, identity: dict,
                  era: dict | None = None, appearance: dict | None = None, snapshot: dict | None = None) -> dict:
    """Combine an authored scope with actual accepted image and supplied state contracts."""
    from state_protocol import artifact_hash, finalize_artifact, validate_artifact
    import studio
    root = studio.require_studio(root)
    c.exact(scope, {'binding_id', 'role', 'effective_story_range', 'visibly_supported_state',
                   'unsupported_or_occluded_state', 'intended_influence', 'unsupported_assumptions', 'review_dimensions'}
            | ({'subject_uses'} if 'subject_uses' in scope else set()), 'authored Studio reference scope')
    expected = [(identity, 'character-identity-contract'), (era, 'era-contract'),
                (appearance, 'appearance-variant-contract'), (snapshot, 'state-snapshot')]
    for value, kind in expected:
        if value is None:
            continue
        report = validate_artifact(value)
        if value.get('artifact_type') != kind or not report['ok']:
            raise ValueError('invalid ' + kind + ': ' + '; '.join(report['errors']))
        if value.get('character_id') != identity.get('character_id'):
            raise ValueError(kind + ' belongs to another work character')
    identity_hash = artifact_hash(identity)
    for value in (era, appearance):
        if value is not None and value.get('parent_identity_contract_sha256') != identity_hash:
            raise ValueError('state contract names another identity')
    if snapshot is not None:
        pairs = {'identity_contract_sha256': identity_hash,
                 'era_contract_sha256': artifact_hash(era) if era else None,
                 'appearance_variant_sha256': artifact_hash(appearance) if appearance else None}
        if any(snapshot.get(k) != v for k, v in pairs.items()):
            raise ValueError('state snapshot does not bind the supplied state contracts')
    read = reference_reads().studio(root)
    source = current_source(root, character, slot, read=read)
    if 'identity' in scope['intended_influence']:
        identity_source(source, root=root, character_id=identity['character_id'], read=read)
    result = finalize_artifact({'artifact_type': 'state-aware-reference-binding', **copy.deepcopy(scope),
        'character_id': identity['character_id'], 'source': source,
        'identity_contract_sha256': identity_hash, 'era_contract_sha256': artifact_hash(era) if era else None,
        'appearance_variant_sha256': artifact_hash(appearance) if appearance else None,
        'state_snapshot_sha256': artifact_hash(snapshot) if snapshot else None})
    report = validate_artifact(result)
    if not report['ok']:
        raise ValueError('invalid Studio state binding: ' + '; '.join(report['errors']))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = _operation_context.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--studio', type=Path, required=True)
    parser.add_argument('--character', required=True)
    parser.add_argument('--slot', required=True)
    sub = parser.add_subparsers(dest='command', required=True)
    source = sub.add_parser('source', help='Pin the current source without inventing a state scope')
    source.add_argument('--out', type=Path, required=True)
    bind = sub.add_parser('bind', help='Build a state binding from authored scope and actual contracts')
    bind.add_argument('--scope', type=Path, required=True)
    bind.add_argument('--identity-contract', type=Path, required=True)
    bind.add_argument('--era-contract', type=Path)
    bind.add_argument('--appearance-variant', type=Path)
    bind.add_argument('--state-snapshot', type=Path)
    bind.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'source':
            result = current_source(args.studio, args.character, args.slot)
        else:
            result = build_binding(args.studio, args.character, args.slot, scope=c.load(args.scope),
                identity=c.load(args.identity_contract), era=c.load(args.era_contract) if args.era_contract else None,
                appearance=c.load(args.appearance_variant) if args.appearance_variant else None,
                snapshot=c.load(args.state_snapshot) if args.state_snapshot else None)
        c.atomic(args.out, c.encoded(result))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({'ok': False, 'errors': [str(exc)]}, ensure_ascii=False, indent=2))
        return 1


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(_operation_context.run_cli(main))
