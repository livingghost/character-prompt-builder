#!/usr/bin/env python3
"""Exercise real schema-valid shot-request bindings, including a hashless identity."""
from __future__ import annotations

import copy
import json
import tempfile
from pathlib import Path
from typing import Any

from shot_request import (
    plot_link_notes,
    validate_bound_artifact,
    validate_bundle,
    validate_request,
    viewpoint_hash,
)
from state_protocol import (
    SELF_HASH_FIELDS,
    artifact_hash,
    load_json,
    validate_against_schema,
    validate_artifact,
)

ROOT = Path(__file__).resolve().parents[1]


def run(root: Path = ROOT) -> dict[str, Any]:
    pilot = root / "examples" / "state-aware-pilot"
    species_path = pilot / "species-morphology-profile.json"
    individual_path = pilot / "individual-morphology-contract.json"
    identity_path = pilot / "character-identity-contract.json"
    state_path = pilot / "generated" / "state-snapshot-C01.json"
    scene_path = pilot / "generated" / "scene-context-snapshot.json"
    species = load_json(species_path)
    individual = load_json(individual_path)
    identity = load_json(identity_path)
    state = load_json(state_path)
    scene = load_json(scene_path)

    checks = 0
    errors: list[str] = []
    if not validate_artifact(identity).get("ok"):
        errors.append("pilot identity is not schema-valid")
    elif "character-identity-contract" in SELF_HASH_FIELDS:
        errors.append("character identity unexpectedly declares a self-hash field")
    else:
        checks += 1

    character_id = str(identity.get("character_id") or "")
    features = [
        str(row.get("feature_id"))
        for row in individual.get("feature_realizations", [])
        if isinstance(row, dict) and row.get("feature_id")
    ]
    report: dict[str, Any] = {"checked_bindings": []}
    with tempfile.TemporaryDirectory(prefix="shot-binding-") as temp:
        temp_root = Path(temp)
        request = {
            "artifact_type": "shot-request",
            "request_id": "SHOT-BINDING-SMOKE",
            "scene_id": scene["scene_context_id"],
            "shot_id": "SC-SMOKE-SH01",
            "deliverable": "start-frame",
            "species_profile_sha256_by_character": {
                character_id: artifact_hash(species)
            },
            "individual_morphology_sha256_by_character": {
                character_id: artifact_hash(individual)
            },
            "identity_contract_sha256_by_character": {
                character_id: artifact_hash(identity)
            },
            "state_snapshot_sha256_by_character": {
                character_id: artifact_hash(state)
            },
            "scene_context_sha256": artifact_hash(scene),
            "camera_spec_sha256": "a" * 64,
            "shot_projection_sha256": "b" * 64,
            "viewpoint_profile_id": "external-character-aligned-third-person",
            "visible_morphology_feature_refs_by_character": {
                character_id: features[:2]
            },
            "visible_identity_obligations": [f"{character_id} face and silhouette"],
            "visible_state_obligations": [f"{character_id} current posture"],
            "selected_reference_candidates": [f"{character_id}-front"],
            "required_output": {
                "prompt_language": "English",
                "aspect_ratio": "16:9",
                "camera_and_crop": "external character-aligned medium shot",
                "style_family_policy": "use one approved series style family",
                "state_lineage_required": True,
            },
            "request_sha256": "0" * 64,
        }
        request["request_sha256"] = viewpoint_hash(request)
        request_schema = load_json(
            root / "schemas" / "viewpoint" / "shot-request.schema.json"
        )
        request_schema_errors = validate_against_schema(request, request_schema)
        report = validate_bundle(
            request,
            species_profile_files={character_id: species_path},
            individual_morphology_files={character_id: individual_path},
            identity_files={character_id: identity_path},
            state_files={character_id: state_path},
            scene_context=scene_path,
            camera_spec=None,
            shot_projection=None,
        )
        if request_schema_errors:
            errors.append(
                "a real shot-request is not schema-valid: "
                + "; ".join(request_schema_errors)
            )
        elif not report.get("ok"):
            errors.append(
                "a schema-valid binding bundle failed: "
                + "; ".join(report.get("errors", []))
            )
        elif f"identity:{character_id}" not in report.get("checked_bindings", []):
            errors.append("schema-valid identity binding was not checked")
        else:
            checks += 1

        # Where the shot came from. The link is optional, because a request may
        # be made for something that has no scene plot; what it must never be is
        # silently absent, because then one frame carries two approvals that do
        # not mention each other.
        def resealed(**fields: Any) -> dict[str, Any]:
            candidate = {key: value for key, value in copy.deepcopy(request).items()
                         if key != "request_sha256"}
            for key, value in fields.items():
                if value is None:
                    candidate.pop(key, None)
                else:
                    candidate[key] = value
            candidate["request_sha256"] = viewpoint_hash(candidate)
            return candidate

        link_cases = [
            ("a request that carries the plot it was planned in",
             resealed(scene_plot_sha256="c" * 64, narrative_sha256="d" * 64), [], None),
            ("a request that carries no link at all",
             resealed(), [], "names no scene_plot_sha256"),
            ("a link whose hash is not a hash",
             resealed(scene_plot_sha256="not-a-hash"),
             ["scene_plot_sha256: string does not match pattern"],
             "names a scene plot and no narrative_sha256"),
            ("a narrative named with no scene plot beside it",
             resealed(narrative_sha256="d" * 64),
             ["scene_plot_sha256"],
             "names no scene_plot_sha256"),
            ("a scene plot with no narrative beside it",
             resealed(scene_plot_sha256="c" * 64), [],
             "names a scene plot and no narrative_sha256"),
        ]
        for name, candidate, expected_errors, expected_note in link_cases:
            found = validate_request(candidate)
            for fragment in expected_errors:
                if not any(fragment in item for item in found):
                    errors.append(f"{name}: expected {fragment!r}, got {found or 'no error'}")
            if not expected_errors and found:
                errors.append(f"{name}: expected no error, got {found}")
            notes = plot_link_notes(candidate)
            if expected_note is None:
                if notes:
                    errors.append(f"{name}: expected nothing unmeasured, got {notes}")
            elif not any(expected_note in item for item in notes):
                errors.append(f"{name}: expected {expected_note!r} unmeasured, got {notes}")
            checks += 1

        changed_identity = copy.deepcopy(identity)
        changed_identity["canon_status"] = (
            "proposed"
            if changed_identity.get("canon_status") != "proposed"
            else "approved"
        )
        changed_identity_path = temp_root / "changed-identity.json"
        changed_identity_path.write_text(
            json.dumps(changed_identity, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        changed_identity_schema = validate_artifact(changed_identity)
        changed_errors = validate_bound_artifact(
            changed_identity_path,
            "character-identity-contract",
            artifact_hash(identity),
            state=True,
        )
        if not changed_identity_schema.get("ok"):
            errors.append(
                "identity hash mutation is not schema-valid: "
                + "; ".join(changed_identity_schema.get("errors", []))
            )
        elif not any(
            "canonical hash does not match request binding" in message
            for message in changed_errors
        ):
            errors.append("changed hashless identity was accepted against the old binding")
        else:
            checks += 1

        changed_state = copy.deepcopy(state)
        changed_state["story_order"] = int(changed_state.get("story_order") or 0) + 1
        changed_state_path = temp_root / "changed-state.json"
        changed_state_path.write_text(
            json.dumps(changed_state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        changed_state_errors = validate_bound_artifact(
            changed_state_path,
            "state-snapshot",
            artifact_hash(state),
            state=True,
        )
        if not any(
            "state_snapshot_sha256 does not match canonical content" in message
            for message in changed_state_errors
        ):
            errors.append("state artifact self-hash mismatch was not rejected")
        else:
            checks += 1

    return {
        "ok": not errors,
        "checks": checks,
        "schema_valid_identity_without_self_hash": True,
        "checked_bindings": report.get("checked_bindings", []),
        "errors": errors,
    }


def main() -> int:
    report = run()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
