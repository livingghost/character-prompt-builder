#!/usr/bin/env python3
"""Check a semantic plan for structure-count, action and camera contradictions before a prompt is delivered."""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas/prompt-semantic-preflight.schema.json"
TEMPLATE_PATH = ROOT / "templates/prompt-semantic-preflight.json"

WORMS_EYE = {"worms-eye", "worm's-eye", "worm-eye", "extreme-low-angle"}
DISTANT_SCALES = {"wide", "extreme-wide", "long", "establishing", "full-establishing"}
DISTANT_DISTANCES = {"far", "distant", "remote", "establishing"}
LOW_HEIGHTS = {"ground", "floor", "ankle", "below-knee"}
UPWARD_PITCHES = {"upward", "steep-upward", "up"}

# What to write in each field the check reads. `[]` is a list item, `*` a key the author names.
FIELDS = {
    "subject_id": "optional label for the plan; not checked",
    "camera": "an object with angle, shot_scale, distance, pitch and subject_frame_occupancy;"
              " --template prints a plan to start from",
    "camera.angle": "text such as eye-level, high, low or worms-eye; worms-eye (also worm's-eye,"
                    " extreme-low-angle) adds the low-camera checks",
    "camera.shot_scale": "text such as close-up, medium or wide",
    "camera.distance": "text such as near, medium or far",
    "camera.camera_height": "optional text such as eye, waist, below-knee or ground",
    "camera.pitch": "text such as level, upward or downward",
    "camera.subject_frame_occupancy": "a number from 0 to 1, the share of the frame the subject fills, such as 0.5",
    "camera.establishing_context": "optional true or false: the frame sets out the surrounding place",
    "structure_plan": "an object with expected_counts and assigned_structures, which may be {} and [];"
                      " --template prints a plan to start from",
    "structure_plan.expected_counts": 'an object of kind and the most allowed, such as {"wing": 2}; {} limits nothing',
    "structure_plan.expected_counts.*": "a whole number, the most structures of this kind",
    "structure_plan.assigned_structures": "a list of the structures the prompt gives a side, an owner or an action;"
                                          " [] declares none",
    "structure_plan.assigned_structures[]": 'an object such as {"structure_id": "left-wing", "kind": "wing"}',
    "structure_plan.assigned_structures[].structure_id": "a name you choose for the structure, unique in the plan;"
                                                         " primary_actions refer to it",
    "structure_plan.assigned_structures[].kind": "what the structure is, such as arm, wing or tail",
    "structure_plan.assigned_structures[].side": "optional text such as left or right",
    "structure_plan.assigned_structures[].owner_id": "optional: the subject the structure belongs to",
    "structure_plan.assigned_structures[].parent_id": "optional: the structure_id it grows from, or null",
    "structure_plan.assigned_structures[].attachment_ids": "optional list of the structure_id values it connects to",
    "structure_plan.primary_actions": "optional list of what each structure does",
    "structure_plan.primary_actions[]": 'an object such as {"structure_id": "left-wing", "action": "shields the face"}',
    "structure_plan.primary_actions[].structure_id": "the structure_id of an assigned structure",
    "structure_plan.primary_actions[].action": "text: what the structure does",
    "structure_plan.primary_actions[].compatible_group": "optional text; actions with one group may share a structure",
    "structure_plan.allow_multiple_primary_actions": "optional true or false: any structure may take several actions",
    "structure_plan.side_limits": 'optional list such as [{"kind": "wing", "side": "left", "max_count": 1}]',
    "structure_plan.side_limits[]": 'an object with kind, side and max_count, and optionally owner_id',
    "structure_plan.side_limits[].kind": "the kind the limit counts",
    "structure_plan.side_limits[].side": "the side the limit counts",
    "structure_plan.side_limits[].owner_id": "optional: count only this subject's structures",
    "structure_plan.side_limits[].max_count": "a whole number, the most structures of this kind on this side",
    "structure_plan.expected_by_owner": 'optional object such as {"C01": {"wing": 2}}: the most of each kind per subject',
    "structure_plan.expected_by_owner.*": 'an object of kind and the most allowed, such as {"wing": 2}',
    "structure_plan.expected_by_owner.*.*": "a whole number, the most structures of this kind",
}
MOVED = {("structure_plan.assigned_structures[]", "action"):
         'an action goes in structure_plan.primary_actions as {"structure_id": "...", "action": "..."}'}


def _schema() -> dict[str, Any]:
    from state_protocol import load_json
    return load_json(SCHEMA_PATH)


def _field_key(path: str, schema: dict[str, Any]) -> str | None:
    """`$.structure_plan.assigned_structures[0].kind` becomes `structure_plan.assigned_structures[].kind`."""
    key = ""
    for name, index in re.findall(r"\.([^.\[\]]+)|\[(\d+)\]", path[1:]):
        if index:
            schema, key = schema.get("items") or {}, key + "[]"
        elif name in (schema.get("properties") or {}):
            schema, key = schema["properties"][name], f"{key}.{name}"
        elif isinstance(schema.get("additionalProperties"), dict):
            schema, key = schema["additionalProperties"], f"{key}.*"
        else:
            return None
    return key.lstrip(".")


def _with_hint(error: str, schema: dict[str, Any]) -> str:
    path, _, problem = error.partition(": ")
    missing = re.fullmatch(r"missing required property '([^']+)'", problem)
    key = _field_key(f"{path}.{missing.group(1)}" if missing else path, schema)
    hint = FIELDS.get(key or "")
    return f"{error}; write {hint}" if hint else error


def _unknown_fields(value: Any, schema: dict[str, Any], path: str, key: str) -> list[str]:
    lines: list[str] = []
    properties = schema.get("properties") or {}
    extra = schema.get("additionalProperties")
    if isinstance(value, dict):
        for name, child in value.items():
            if name in properties:
                lines += _unknown_fields(child, properties[name], f"{path}.{name}", f"{key}.{name}".lstrip("."))
            elif isinstance(extra, dict):
                lines += _unknown_fields(child, extra, f"{path}.{name}", f"{key}.*".lstrip("."))
            elif extra is False:
                where = MOVED.get((key, name)) or "this object takes " + ", ".join(properties)
                lines.append(f"{path}.{name}: unknown field; {where}")
    elif isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, item in enumerate(value):
            lines += _unknown_fields(item, schema["items"], f"{path}[{index}]", f"{key}[]")
    return lines


def schema_errors(plan: Any) -> list[str]:
    """Schema errors that each say what to write, and one line for every unknown field."""
    from state_protocol import validate_against_schema
    schema = _schema()
    errors = [_with_hint(error, schema) for error in validate_against_schema(plan, schema)
              if ": unexpected properties " not in error]
    return list(dict.fromkeys(errors + _unknown_fields(plan, schema, "$", "")))


def validate_plan(plan: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    from structure_contract import validate_structure_map
    errors.extend(schema_errors(plan))
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


def _help_epilog() -> str:
    shown = [(key.count("."), key.rsplit(".", 1)[-1], text) for key, text in FIELDS.items()
             if not key.endswith(("[]", "*"))]
    width = max(2 * depth + len(name) for depth, name, _ in shown)
    rows = [f"  {('  ' * depth + name).ljust(width)}  {text}" for depth, name, text in shown]
    return ("Every field the check reads; any other field is refused:\n" + "\n".join(rows)
            + "\n\nA valid plan to start from (--template prints it):\n" + TEMPLATE_PATH.read_text(encoding="utf-8"))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, epilog=_help_epilog(),
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("plan", nargs="?", type=Path, help="the plan JSON file")
    parser.add_argument("--template", action="store_true", help="print a valid plan to start from")
    parser.add_argument("--self-test", action="store_true", help="run the built-in checks")
    args = parser.parse_args(argv)
    if args.template:
        sys.stdout.write(TEMPLATE_PATH.read_text(encoding="utf-8"))
        return 0
    if args.self_test:
        report = self_test()
    elif args.plan is None:
        parser.error("give a plan file; --template prints one to start from")
    else:
        try:
            plan = json.loads(args.plan.read_text(encoding="utf-8"))
            if not isinstance(plan, dict):
                raise ValueError("plan root must be an object; --template prints one to start from")
            report = validate_plan(plan)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            report = {"ok": False, "errors": [str(exc)], "warnings": [], "stats": {}}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
