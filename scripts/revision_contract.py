#!/usr/bin/env python3
"""Validate edit/explore/retarget semantic differences without judging prose.

python scripts/revision_contract.py revision.json [--out report.json]
See references/runtime/revision-contract.md for the input and authority model.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _escape(key: str) -> str:
    return key.replace("~", "~0").replace("/", "~1")


def changed_paths(before: Any, after: Any, prefix: str = "") -> list[str]:
    """Objects differ recursively; arrays are atomic so reordering is visible."""
    if type(before) is not type(after):
        return [prefix]
    if isinstance(before, dict):
        result: list[str] = []
        for key in sorted(set(before) | set(after)):
            path = prefix + "/" + _escape(key)
            if key not in before or key not in after:
                result.append(path)
            else:
                result.extend(changed_paths(before[key], after[key], path))
        return result
    return [] if before == after else [prefix]


def _pointers(value: Any, name: str) -> list[str]:
    import re
    if not isinstance(value, list) or any(not isinstance(p, str) or not p.startswith("/")
        or re.search(r"~(?![01])", p) for p in value):
        raise ValueError(f"{name} must contain non-root RFC6901 JSON pointers")
    if len(value) != len(set(value)):
        raise ValueError(f"{name} contains duplicates")
    return value


def _overlaps(left: str, right: str) -> bool:
    return left == right or left.startswith(right + "/") or right.startswith(left + "/")


def validate_revision(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("revision must be an object")
    fields = {"operation", "baseline", "candidate", "requested_paths", "consistency_changes",
              "frozen_paths", "scope", "canonical_approval", "note"}
    if set(value) - fields:
        raise ValueError("unknown revision fields: " + ", ".join(sorted(set(value) - fields)))
    mode = value.get("operation")
    if mode not in {"edit", "explore", "retarget"}:
        raise ValueError("operation must be edit, explore or retarget")
    before, after = value.get("baseline"), value.get("candidate")
    if not isinstance(before, dict) or not isinstance(after, dict):
        raise ValueError("baseline and candidate must be structured semantic objects")
    paths = changed_paths(before, after)
    requested = _pointers(value.get("requested_paths", []), "requested_paths")
    frozen = _pointers(value.get("frozen_paths", []), "frozen_paths")
    consistency = value.get("consistency_changes", [])
    if not isinstance(consistency, list):
        raise ValueError("consistency_changes must be an array")
    consistency_paths: list[str] = []
    for item in consistency:
        if not isinstance(item, dict) or set(item) != {"path", "reason"}:
            raise ValueError("each consistency change must carry path and reason")
        _pointers([item["path"]], "consistency_changes.path")
        if not isinstance(item["reason"], str) or not item["reason"].strip():
            raise ValueError("each consistency change needs an explicit reason")
        consistency_paths.append(item["path"])
    errors: list[str] = []
    if mode == "edit":
        if not requested:
            errors.append("edit requires the user's requested_paths")
        allowed = requested + consistency_paths
        for path in paths:
            # Replacing an ancestor can delete unrelated fields, so only changes
            # inside an approved subtree count; overlap alone would be too broad.
            if not any(path == p or path.startswith(p + "/") for p in allowed):
                errors.append(f"unrequested semantic change: {path}")
    if mode == "retarget" and paths:
        errors.append("retarget must preserve all structured semantics; change target-specific wording separately")
    for path in paths:
        if any(_overlaps(path, frozen_path) for frozen_path in frozen):
            errors.append(f"frozen semantic field changed: {path}")
    scope = value.get("scope", "scene")
    if scope not in {"scene", "identity"}:
        errors.append("scope must be scene or identity")
    identity_changes = [p for p in paths if any(_overlaps(p, owner) for owner in ("/identity", "/identity_slots"))]
    if identity_changes:
        from prompt_plot import APPROVED_AT
        if scope != "identity":
            errors.append("scene changes must preserve /identity and /identity_slots, including identity.fixed_wardrobe")
        else:
            approval = value.get("canonical_approval")
            if not isinstance(approval, dict) or approval.get("baseline_sha256") != digest(before) or approval.get("candidate_sha256") != digest(after) or not isinstance(approval.get("by"), str) or not approval["by"].strip() or not isinstance(approval.get("at"), str) or not APPROVED_AT.fullmatch(approval["at"]):
                errors.append("identity update requires explicit canonical approval bound to both semantic versions")
    return {"ok": not errors, "operation": mode, "scope": scope, "changed_paths": paths,
            "baseline_sha256": digest(before), "candidate_sha256": digest(after),
            "consistency_changes": consistency, "errors": errors,
            "note": "Checks declared structure and scope, not image quality or the truth of recorded user consent."}


def require_intent_revision(intent: dict[str, Any]) -> dict[str, Any] | None:
    """Apply the same semantic-diff gate wherever a production intent is used."""
    if "revision_contract" not in intent:
        return None
    report = validate_revision(intent["revision_contract"])
    if not report["ok"]:
        raise ValueError("revision preflight failed: " + "; ".join(report["errors"]))
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("revision", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    try:
        report = validate_revision(json.loads(args.revision.read_text(encoding="utf-8")))
    except (ValueError, OSError) as exc:
        report = {"ok": False, "errors": [str(exc)]}
    if args.out:
        from pack_manager import atomic_write_json
        atomic_write_json(args.out, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
