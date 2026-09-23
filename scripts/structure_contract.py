#!/usr/bin/env python3
"""Validate and inspect author-declared structures without inventing anatomy.

Schema checks are shared with state_protocol. Relational checks are deterministic:
IDs, attachment/parent references, acyclic containment and explicit local overrides.
The inspector copies the declared contract and exposes stable source pointers.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
KINDS = ("growth-geometry", "terminal-growth-contract", "frame-character", "garment-geometry")


def validate_structure_map(value: Any, path: str = "$.structures") -> list[str]:
    """Relational constraints that JSON Schema cannot express by itself.

    Geometry text is authored, not interpreted. Overlap of natural-language
    locations cannot be inferred: local exceptions name both their target and
    the properties they replace. Global values are never overwritten in place.
    """
    if not isinstance(value, dict) or any(not isinstance(row, dict) for row in value.values()):
        return []  # Structural/type failures are reported by the schema.
    errors: list[str] = []
    parents: dict[str, list[str]] = {}
    overrides: dict[str, list[str]] = {}
    for sid, row in value.items():
        parent = row.get("parent_id")
        parents[sid] = [parent] if isinstance(parent, str) else []
        attachments = row.get("attachment_ids", [])
        attachments = attachments if isinstance(attachments, list) else []
        overrides[sid] = []
        rules = row.get("overrides", [])
        rules = rules if isinstance(rules, list) else []
        seen_rules: set[tuple[str, str]] = set()
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            target = rule.get("structure_id")
            if not isinstance(target, str):
                continue
            overrides[sid].append(target)
            properties = rule.get("properties", [])
            for prop in properties if isinstance(properties, list) else []:
                if not isinstance(prop, str):
                    continue
                if (target, prop) in seen_rules:
                    errors.append(f"{path}.{sid}: duplicate override of {target}.{prop}")
                seen_rules.add((target, prop))
                source_geometry = row.get("geometry", {})
                target_geometry = value.get(target, {}).get("geometry", {})
                if not isinstance(source_geometry, dict) or prop not in source_geometry:
                    errors.append(f"{path}.{sid}: override property {prop!r} has no local value")
                if target in value and (not isinstance(target_geometry, dict) or prop not in target_geometry):
                    errors.append(f"{path}.{sid}: override property {prop!r} is not declared by {target}")
        for target in parents[sid] + attachments + overrides[sid]:
            if not isinstance(target, str):
                continue
            if target == sid:
                errors.append(f"{path}.{sid}: self reference is not permitted")
            elif target not in value:
                errors.append(f"{path}.{sid}: unknown structure reference {target!r}")
            elif row.get("presence") in {"present", "partial"} and value[target].get("presence") == "absent":
                errors.append(f"{path}.{sid}: present structure references explicitly absent carrier {target!r}")

    # Parent and override graphs are DAGs. Attachments may legitimately form rings.
    # Use iterative traversal so hostile/deep declarations cannot exhaust recursion.
    for name, graph in (("parent", parents), ("override", overrides)):
        done: set[str] = set()
        active: set[str] = set()
        for start in graph:
            if start in done:
                continue
            stack: list[tuple[str, bool]] = [(start, False)]
            while stack:
                node, leaving = stack.pop()
                if leaving:
                    active.discard(node)
                    done.add(node)
                    continue
                if node in active:
                    errors.append(f"{path}: cyclic {name} relation at {node!r}")
                    continue
                if node in done or node not in graph:
                    continue
                active.add(node)
                stack.append((node, True))
                stack.extend((target, False) for target in graph[node])
    return errors


def structure_view(value: dict[str, Any], kind: str) -> dict[str, Any]:
    """Return a detached view of the declared structures and their source pointers."""
    if kind not in KINDS:
        raise ValueError(f"unsupported structure contract: {kind}")
    return {
        "contract_kind": kind,
        "structures": {
            sid: {
                "source_pointer": "/structures/" + sid.replace("~", "~0").replace("/", "~1"),
                "presence": row["presence"],
                "definition": copy.deepcopy(row),
            }
            for sid, row in value["structures"].items()
        },
        "source_contract": copy.deepcopy(value),
    }


def inspect_contract(value: dict[str, Any], kind: str) -> dict[str, Any]:
    from state_protocol import load_json, validate_against_schema
    errors = validate_against_schema(value, load_json(ROOT / "schemas" / f"{kind}.schema.json"))
    return {"ok": not errors, "errors": errors,
            "view": structure_view(value, kind) if not errors else None}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("validate", "inspect"))
    parser.add_argument("contract", type=Path)
    parser.add_argument("--kind", required=True, choices=KINDS)
    args = parser.parse_args()
    try:
        from state_protocol import load_json
        value = load_json(args.contract)
        result = inspect_contract(value, args.kind)
        if args.action == "validate":
            result.pop("view", None)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result = {"ok": False, "errors": [str(exc)]}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
