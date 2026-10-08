"""Neutral artwork selections for tests and executable synthetic examples only.

The helper authors labeled synthetic evidence. Runtime commands never import it
or use its declarations as a real user's approval.
"""
from __future__ import annotations
import copy
from pathlib import Path
import uuid

import execution_contract as c
import sheet_artifacts as fills


def accepted_slot(root: Path, image: str, *, package: str | None = None,
                  slot_id: str = 'canon.primary', fill_policy: str = 'auto') -> dict:
    root.mkdir(parents=True, exist_ok=True)
    package_path = root / package if package else root / 'synthetic-artwork.package.json'
    if package is None:
        c.atomic_write_json(package_path, {'status': 'ready', 'model': 'synthetic-sheet-model',
            'generation_payload': {'fixture': True}, 'generation_contract': {},
            'generation_input_sha256': c.digest(b'explicit synthetic sheet fixture')})
    sidecar = root / ('.synthetic-selection-' + str(uuid.uuid4()) + '.json')
    try:
        c.atomic(sidecar, c.encoded({'sheet_status': 'identity-ready',
            'fields': {'identity.name': 'Synthetic', 'identity.species_domain': 'robot'}, 'tables': {}, 'slots': {}}))
        artifact = fills.publish(root, root / image, kind='generation', recipe={'fixture': True}, package=package_path,
                                 origin={'kind': 'external-import', 'note': 'Synthetic test artifact, not a user decision.'})
        fills.register_candidates(sidecar, [(slot_id, artifact)])
        evidence = root / 'synthetic-artwork-choice.txt'
        if not evidence.exists(): c.atomic(evidence, b'Synthetic fixture evidence, not user consent.\n')
        decision = fills.draft_adoption(sidecar, slot_id, artifact['artifact_id'])
        decision.update(by='SYNTHETIC FIXTURE AUTHOR', at='2000-01-01T00:00:00Z', reason='Exercise exact recorded artifact adoption.',
                        evidence={'path': evidence.name, 'sha256': c.sha256_file(evidence), 'locator': 'whole'})
        fills.adopt(sidecar, decision, evidence_root=root)
        slot = c.load(sidecar)['slots'][slot_id]; slot['fill_policy'] = fill_policy
        return slot
    finally:
        sidecar.unlink(missing_ok=True)


def unverified_slot(image: str, *, fill_policy: str = 'auto') -> dict:
    """A structurally declared selection for tests that deliberately fail path verification."""
    artifact = {'artifact_id': '1'*64, 'image': {'path': image, 'sha256': '2'*64,
                'width': 1, 'height': 1, 'media_type': 'image/png'},
                'provenance': {'kind': 'generation', 'path': 'synthetic-provenance.json', 'sha256': '3'*64}}
    return {'current': {'artifact': artifact, 'approval': {'decision_path': 'synthetic-decision.json',
                'evidence_path': 'synthetic-evidence.txt', 'decision_sha256': '4'*64, 'evidence_sha256': '5'*64}},
            'candidates': [], 'history': [], 'fill_policy': fill_policy}
