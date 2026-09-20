#!/usr/bin/env python3
"""Validate and seal Series Viewpoint Protocol artifacts.

The code checks explicit camera, knowledge scope, audition, transition, and
continuity records. It does not invent shot design or artistic intent.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable, Sequence

from protocol_contract import (
    SUPPORTED_SCHEMA_KEYWORDS, unsupported_schema_keywords, canonical_json, sha256_json,
    load_json, schema_for, artifact_hash, finalize_artifact, validate_against_schema,
    validate_cross_invariants, validate_artifact,
)

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_DIR = ROOT / "protocols" / "viewpoint"
SCHEMA_DIR = ROOT / load_json(ROOT / "config/protocol-layout.json")["viewpoint"]
PROFILE_DIR = PROTOCOL_DIR / "profiles"

SELF_HASH_FIELDS = {
    "viewpoint-profile": "profile_sha256",
    "scene-viewpoint-plan": "scene_plan_sha256",
    "shot-camera-spec": "camera_spec_sha256",
    "viewpoint-transition": "transition_sha256",
    "shot-continuity-ledger": "ledger_sha256",
    "shot-visual-projection": "projection_sha256",
    "shot-request": "request_sha256",
}

EXTERNAL_RIG_MOVES = {"pan", "tilt", "track", "dolly", "crane", "arc", "orbit", "handheld-follow", "locked"}
EMBODIED_MOVES = {"held", "look", "turn", "lean", "crouch", "stand", "walk", "step", "stumble-recover"}
DEVICE_MOVES = {"held", "pan", "tilt", "walk", "step", "handheld-follow", "device-zoom", "locked"}
FIXED_MOVES = {"locked", "mechanical-pan", "mechanical-tilt"}








def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def artifact_type(data: dict[str, Any]) -> str:
    kind = str(data.get("artifact_type") or "")
    if not kind:
        raise ValueError("artifact_type is required")
    return kind














def load_profiles() -> dict[str, dict[str, Any]]:
    profiles: dict[str, dict[str, Any]] = {}
    for path in sorted(PROFILE_DIR.glob("*.json")):
        profile = load_json(path)
        profiles[str(profile.get("profile_id"))] = profile
    return profiles






def build_continuity_ledger(scene: dict[str, Any], shots: list[dict[str, Any]], transitions: list[dict[str, Any]]) -> dict[str, Any]:
    for item in [scene, *shots, *transitions]:
        report = validate_artifact(item)
        if not report["ok"]:
            raise ValueError("invalid ledger input: " + "; ".join(report["errors"]))
    if len({s["shot_id"] for s in shots}) != len(shots) or len({t["transition_id"] for t in transitions}) != len(transitions):
        raise ValueError("duplicate shot or transition input")
    if any(item["scene_id"] != scene["scene_id"] for item in [*shots, *transitions]):
        raise ValueError("ledger input belongs to a different scene")
    if scene.get("artifact_type") != "scene-viewpoint-plan" or any(s.get("artifact_type") != "shot-camera-spec" for s in shots) or any(t.get("artifact_type") != "viewpoint-transition" for t in transitions):
        raise ValueError("ledger requires scene, camera and transition artifacts of their declared types")
    shot_ids = {s["shot_id"] for s in shots}
    declared_ids = {s["shot_id"] for s in scene["shots"]}
    if shot_ids != declared_ids:
        raise ValueError("ledger camera inputs differ from the scene's declared shots")
    if {t["transition_id"] for t in transitions} != set(scene["transition_ids"]):
        raise ValueError("ledger transition inputs differ from the scene plan")
    for transition in transitions:
        if transition["from_shot"] not in shot_ids or transition["to_shot"] not in shot_ids:
            raise ValueError("transition references an unknown shot")
    by_id = {str(item.get("shot_id")): item for item in shots}
    transition_by_id = {str(item.get("transition_id")): item for item in transitions}
    entries: list[dict[str, Any]] = []
    unresolved: list[str] = []
    ordered = sorted(scene.get("shots", []), key=lambda item: int(item.get("order_index", 0)))
    for ref in ordered:
        shot_id = str(ref.get("shot_id"))
        shot = by_id.get(shot_id)
        if not shot:
            unresolved.append(f"missing camera spec for {shot_id}")
            continue
        entries.append({
            "shot_id": shot_id,
            "camera_spec_sha256": shot.get("camera_spec_sha256"),
            "start_anchor": shot.get("start_anchor"),
            "end_anchor": shot.get("end_anchor"),
            "screen_direction": shot.get("screen_direction"),
            "axis_side": shot.get("axis_side"),
            "visible_subjects": shot.get("visible_subjects", []),
            "prop_ownership": shot.get("prop_ownership", {}),
            "state_snapshot_sha256_by_character": shot.get("state_snapshot_sha256_by_character", {}),
        })
    trans_entries: list[dict[str, Any]] = []
    for transition_id in scene.get("transition_ids", []):
        transition = transition_by_id.get(str(transition_id))
        if not transition:
            unresolved.append(f"missing transition artifact {transition_id}")
            continue
        trans_entries.append({
            "transition_id": transition_id,
            "transition_sha256": transition.get("transition_sha256"),
            "from_shot": transition.get("from_shot"),
            "to_shot": transition.get("to_shot"),
            "continuity_requirements": transition.get("continuity_requirements", []),
        })
    ledger = {
        "artifact_type": "shot-continuity-ledger",
        "scene_id": scene.get("scene_id"),
        "scene_plan_sha256": scene.get("scene_plan_sha256"),
        "shot_entries": entries,
        "transition_entries": trans_entries,
        "unresolved_continuity": unresolved,
        "ledger_sha256": "0" * 64,
    }
    return finalize_artifact(ledger)


def validate_tree(root: Path, *, allow_templates: bool = False) -> dict[str, Any]:
    errors: list[str] = []
    files = 0
    artifacts = 0
    for path in sorted(root.rglob("*.json")):
        files += 1
        try:
            value = load_json(path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{path}: {exc}")
            continue
        if not value.get("artifact_type"):
            continue
        artifacts += 1
        report = validate_artifact(value, allow_placeholder_hashes=allow_templates)
        if not report.get("ok"):
            errors.extend(f"{path}: {message}" for message in report.get("errors", []))
    return {"ok": not errors, "files": files, "artifacts": artifacts, "errors": errors}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Series Viewpoint Protocol support tool")
    sub = parser.add_subparsers(dest="command", required=True)

    p_validate = sub.add_parser("validate", help="Validate one protocol artifact")
    p_validate.add_argument("path")
    p_validate.add_argument("--allow-placeholder-hash", action="store_true")

    p_seal = sub.add_parser("seal", help="Seal one protocol artifact with its canonical hash")
    p_seal.add_argument("path")
    p_seal.add_argument("--out")

    p_tree = sub.add_parser("validate-tree", help="Validate every protocol artifact under a directory")
    p_tree.add_argument("path")
    p_tree.add_argument("--allow-templates", action="store_true")

    p_ledger = sub.add_parser("build-ledger", help="Build a continuity ledger from a scene plan, shot specs, and transitions")
    p_ledger.add_argument("--scene-plan", required=True)
    p_ledger.add_argument("--shots-dir", required=True)
    p_ledger.add_argument("--transitions-dir", required=True)
    p_ledger.add_argument("--out", required=True)

    p_profiles = sub.add_parser("seal-profiles", help="Seal all built-in viewpoint profiles")

    args = parser.parse_args(argv)
    if args.command == "validate":
        report = validate_artifact(load_json(Path(args.path)), allow_placeholder_hashes=args.allow_placeholder_hash)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report.get("ok") else 1
    if args.command == "seal":
        value = finalize_artifact(load_json(Path(args.path)))
        target = Path(args.out) if args.out else Path(args.path)
        report = validate_artifact(value)
        if report["ok"]:
            write_json(target, value)
        print(json.dumps({"ok": report.get("ok"), "path": str(target), "hash": artifact_hash(value), "errors": report.get("errors", [])}, ensure_ascii=False, indent=2))
        return 0 if report.get("ok") else 1
    if args.command == "validate-tree":
        report = validate_tree(Path(args.path), allow_templates=args.allow_templates)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report.get("ok") else 1
    if args.command == "build-ledger":
        scene = load_json(Path(args.scene_plan))
        shots = [load_json(path) for path in sorted(Path(args.shots_dir).glob("*.json"))]
        transitions = [load_json(path) for path in sorted(Path(args.transitions_dir).glob("*.json"))]
        ledger = build_continuity_ledger(scene, shots, transitions)
        report = validate_artifact(ledger)
        if not report.get("ok"):
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 1
        write_json(Path(args.out), ledger)
        print(json.dumps({"ok": True, "out": args.out, "ledger_sha256": ledger["ledger_sha256"], "unresolved": ledger["unresolved_continuity"]}, ensure_ascii=False, indent=2))
        return 0
    if args.command == "seal-profiles":
        errors: list[str] = []
        count = 0
        for path in sorted(PROFILE_DIR.glob("*.json")):
            value = finalize_artifact(load_json(path))
            report = validate_artifact(value)
            if report["ok"]:
                write_json(path, value)
            count += 1
            if not report.get("ok"):
                errors.extend(f"{path.name}: {message}" for message in report.get("errors", []))
        print(json.dumps({"ok": not errors, "profiles": count, "errors": errors}, ensure_ascii=False, indent=2))
        return 0 if not errors else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
