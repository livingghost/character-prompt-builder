#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

WORMS_EYE = {"worms-eye", "worm's-eye", "worm-eye", "extreme-low-angle"}
DISTANT_SCALES = {"wide", "extreme-wide", "long", "establishing", "full-establishing"}
DISTANT_DISTANCES = {"far", "distant", "remote", "establishing"}
LOW_HEIGHTS = {"ground", "floor", "ankle", "below-knee"}
UPWARD_PITCHES = {"upward", "steep-upward", "up"}


def validate_plan(plan: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    from state_protocol import load_json, validate_against_schema
    from structure_contract import validate_structure_map
    schema = load_json(Path(__file__).resolve().parents[1] / "schemas/prompt-semantic-preflight.schema.json")
    errors.extend(validate_against_schema(plan, schema))
    if errors:
        return {"ok": False, "errors": errors, "warnings": warnings, "stats": {}}
    structure_plan = plan["structure_plan"]
    expected = structure_plan.get("expected_counts") if isinstance(structure_plan.get("expected_counts"), dict) else {}
    normalized_expected = {}
    for name, limit in expected.items():
        normalized = name.strip().lower()
        if normalized in normalized_expected:
            errors.append(f"ambiguous normalized structure kind in expected_counts: {name!r}")
        normalized_expected[normalized] = limit
    expected = normalized_expected
    assigned = structure_plan.get("assigned_structures") if isinstance(structure_plan.get("assigned_structures"), list) else []
    actions = structure_plan.get("primary_actions") if isinstance(structure_plan.get("primary_actions"), list) else []

    structure_ids: list[str] = []
    kinds: Counter[str] = Counter()
    side_kinds: Counter[tuple[str, str]] = Counter()
    owner_kinds: Counter[tuple[str, str]] = Counter()
    owner_side_kinds: Counter[tuple[str, str, str]] = Counter()
    for index, structure in enumerate(assigned):
        if not isinstance(structure, dict):
            errors.append(f"structure_plan.assigned_structures[{index}] must be an object")
            continue
        structure_id = str(structure.get("structure_id") or "").strip()
        kind = str(structure.get("kind") or "").strip().lower()
        side = str(structure.get("side") or "none").strip().lower()
        if not structure_id:
            errors.append(f"structure_plan.assigned_structures[{index}] lacks structure_id")
        else:
            structure_ids.append(structure_id)
        if not kind:
            errors.append(f"structure_plan.assigned_structures[{index}] lacks kind")
        else:
            kinds[kind] += 1
            side_kinds[(kind, side)] += 1
            owner = str(structure.get("owner_id") or "").strip()
            owner_kinds[(owner, kind)] += 1
            owner_side_kinds[(owner, kind, side)] += 1
        if not str(structure.get("owner_id") or "").strip():
            warnings.append(f"{structure_id or index}: declared structure has no explicit owner_id")

    duplicates = sorted(item for item, count in Counter(structure_ids).items() if count > 1)
    if duplicates:
        errors.append(f"duplicate structure_id values: {duplicates}")

    for kind, count in kinds.items():
        limit = expected.get(kind)
        if isinstance(limit, int) and count > limit:
            errors.append(f"assigned {count} {kind} structures but body plan permits {limit}")
    for limit in structure_plan.get("side_limits", []):
        kind, side = limit["kind"].strip().lower(), limit["side"].strip().lower()
        owner = limit.get("owner_id")
        count = (owner_side_kinds[(owner, kind, side)] if owner is not None
                 else side_kinds[(kind, side)])
        if count > limit["max_count"]:
            errors.append(f"declared side limit exceeded for {owner or 'all owners'} {side} {kind}: {count} > {limit['max_count']}")
    for owner, limits in structure_plan.get("expected_by_owner", {}).items():
        seen_kinds = set()
        for kind, limit in limits.items():
            normalized = kind.strip().lower()
            if normalized in seen_kinds:
                errors.append(f"{owner}: ambiguous normalized structure kind: {kind!r}")
            seen_kinds.add(normalized)
            count = owner_kinds[(owner, normalized)]
            if count > limit:
                errors.append(f"{owner}: assigned {count} {kind} structures but declaration permits {limit}")
    relations = {str(row.get("structure_id")): row for row in assigned if isinstance(row, dict)}
    errors.extend(validate_structure_map(relations, "structure_plan"))

    known = set(structure_ids)
    by_structure: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for index, action in enumerate(actions):
        if not isinstance(action, dict):
            errors.append(f"structure_plan.primary_actions[{index}] must be an object")
            continue
        structure_id = str(action.get("structure_id") or "").strip()
        if structure_id not in known:
            errors.append(f"primary action references unknown structure_id: {structure_id or '<empty>'}")
        by_structure[structure_id].append(action)
    if not structure_plan.get("allow_multiple_primary_actions", False):
        for structure_id, values in by_structure.items():
            if len(values) > 1:
                groups = {str(value.get("compatible_group") or "").strip() for value in values}
                if "" in groups or len(groups) > 1:
                    errors.append(f"{structure_id}: multiple incompatible primary actions may duplicate the structure")

    camera = plan.get("camera") if isinstance(plan.get("camera"), dict) else {}
    angle = str(camera.get("angle") or "").strip().lower()
    if angle in WORMS_EYE:
        scale = str(camera.get("shot_scale") or "").strip().lower()
        distance = str(camera.get("distance") or "").strip().lower()
        height = str(camera.get("camera_height") or "").strip().lower()
        pitch = str(camera.get("pitch") or "").strip().lower()
        occupancy = camera.get("subject_frame_occupancy")
        if scale in DISTANT_SCALES:
            errors.append("worms-eye camera conflicts with a distant or establishing shot scale")
        if distance in DISTANT_DISTANCES:
            errors.append("worms-eye camera conflicts with distant camera distance")
        if height and height not in LOW_HEIGHTS:
            errors.append("worms-eye camera requires ground, floor, ankle, or below-knee camera height")
        if pitch not in UPWARD_PITCHES:
            errors.append("worms-eye camera requires an upward pitch")
        if not isinstance(occupancy, (int, float)) or occupancy < 0.55:
            errors.append("worms-eye camera requires subject_frame_occupancy of at least 0.55")
        if camera.get("establishing_context") is True:
            errors.append("worms-eye close-subject promise conflicts with establishing_context=true")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "stats": {
            "assigned_structure_count": len(assigned),
            "primary_action_count": len(actions),
            "worms_eye_checked": angle in WORMS_EYE,
        },
    }


def self_test() -> dict[str, Any]:
    good = {
        "structure_plan": {
            "expected_counts": {"arm": 2, "hand": 2},
            "assigned_structures": [
                {"structure_id": "left-arm", "kind": "arm", "side": "left", "owner_id": "C01"},
                {"structure_id": "right-arm", "kind": "arm", "side": "right", "owner_id": "C01"},
                {"structure_id": "left-hand", "kind": "hand", "side": "left", "owner_id": "C01"},
                {"structure_id": "right-hand", "kind": "hand", "side": "right", "owner_id": "C01"},
            ],
            "primary_actions": [
                {"structure_id": "left-hand", "action": "rests on knee"},
                {"structure_id": "right-hand", "action": "holds cup"},
            ],
        },
        "camera": {
            "angle": "worms-eye", "shot_scale": "medium-close", "distance": "near",
            "camera_height": "below-knee", "pitch": "upward", "subject_frame_occupancy": 0.7,
            "establishing_context": False,
        },
    }
    duplicate = json.loads(json.dumps(good))
    duplicate["structure_plan"]["assigned_structures"].append(
        {"structure_id": "left-arm-duplicate", "kind": "arm", "side": "left", "owner_id": "C01"}
    )
    distant = json.loads(json.dumps(good))
    distant["camera"].update({"shot_scale": "wide", "distance": "distant", "subject_frame_occupancy": 0.25})
    reports = {"good": validate_plan(good), "duplicate": validate_plan(duplicate), "distant": validate_plan(distant)}
    ok = reports["good"]["ok"] and not reports["duplicate"]["ok"] and not reports["distant"]["ok"]
    return {"ok": ok, "errors": [] if ok else ["semantic preflight self-test failed"], "reports": reports}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("plan", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test or args.plan is None:
        report = self_test()
    else:
        try:
            plan = json.loads(args.plan.read_text(encoding="utf-8"))
            if not isinstance(plan, dict):
                raise ValueError("plan root must be an object")
            report = validate_plan(plan)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            report = {"ok": False, "errors": [str(exc)], "warnings": [], "stats": {}}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
