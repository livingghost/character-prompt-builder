#!/usr/bin/env python3
"""Draft, validate, inspect, and hash the Production Specification of one image.

The specification records the scene the author decided for one image. A field
the author leaves open holds the string "unspecified". Stable identity and
temporal canon live in separate contracts; a specification that uses them
records their exact references.

    python scripts/production_spec.py draft production-spec.json --model MODEL \\
        --render-intent render-intent.json --brief TEXT --kind human --framing waist-up --continuity one-off
    python scripts/production_spec.py validate production-spec.json --require-content
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

from state_protocol import find_non_finite_numbers, parse_json, validate_against_schema

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "production-spec-template.json"
UNSPECIFIED = "unspecified"
PRODUCTION_SPEC_SCHEMA = json.loads((ROOT / "schemas" / "production-spec.schema.json").read_text(encoding="utf-8"))
PERFORMANCE_SCHEMA = json.loads((ROOT / "schemas" / "performance-language.schema.json").read_text(encoding="utf-8"))
CAMERA_SCHEMA = json.loads((ROOT / "schemas" / "camera-framing-contract.schema.json").read_text(encoding="utf-8"))
DOMAINS = tuple(PRODUCTION_SPEC_SCHEMA["properties"]["subjects"]["items"]["properties"]["domain"]["enum"])
FRAMINGS = tuple(value for value in CAMERA_SCHEMA["properties"]["shot_scale"]["enum"] if value != UNSPECIFIED)
CONTINUITIES = ("one-off", "undecided", "recurring")
ART_FIELDS = tuple(PRODUCTION_SPEC_SCHEMA["properties"]["art_direction"]["required"])
STATE_AWARE_ONLY = ("$.state_context.state_lineage_sha256", "$.state_context.scene_context_ref")
# Items that other parts of the specification address by ID.
KEYED_ARRAYS = (
    ("distinctive_details", "id"),
    ("load_bearing_part_measurements", "measurement_id"),
    ("accessory_geometry", "accessory_id"),
    ("garment_geometry", "garment_id"),
)


class SpecificationError(ValueError):
    """An invalid Production Specification, carrying each error once."""

    def __init__(self, errors: Sequence[str]):
        self.errors = [f"production specification: {item}" for item in errors]
        super().__init__("; ".join(self.errors))


def canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def load(path: Path) -> dict[str, Any]:
    data = parse_json(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("production spec must be a JSON object")
    return data


def _subject_errors(index: int, subject: dict[str, Any]) -> list[str]:
    """What the schema cannot state: unique item IDs and one resolved morphology."""
    errors: list[str] = []
    for field, key in KEYED_ARRAYS:
        items = subject.get(field)
        if not isinstance(items, list):
            continue
        seen: set[str] = set()
        for item in items:
            value = item.get(key) if isinstance(item, dict) else None
            if isinstance(value, str) and value in seen:
                errors.append(f"$.subjects[{index}].{field}: duplicate {key} {value!r}")
            if isinstance(value, str):
                seen.add(value)
    resolved = subject.get("resolved_morphology")
    if isinstance(resolved, dict):
        for field in ("frame_character", "load_bearing_part_measurements"):
            if field in subject and subject[field] != resolved.get(field):
                errors.append(f"$.subjects[{index}].{field} differs from resolved_morphology.{field}")
    return errors


def validate(data: dict[str, Any], *, require_content: bool = False) -> dict[str, Any]:
    non_finite = find_non_finite_numbers(data)
    errors = [f"{path}: number must be finite" for path in non_finite]
    for error in validate_against_schema(data, PRODUCTION_SPEC_SCHEMA):
        path = error.split(":", 1)[0]
        if path in STATE_AWARE_ONLY and error.endswith("value satisfies a forbidden schema"):
            error = f"{path}: only a state-aware specification names this; the builder seals the stateless lineage"
        errors.append(error)
    subjects = data.get("subjects") if isinstance(data, dict) else None
    if isinstance(subjects, list):
        seen: set[str] = set()
        for index, subject in enumerate(subjects):
            if not isinstance(subject, dict):
                continue
            subject_id = subject.get("id")
            if isinstance(subject_id, str) and subject_id in seen:
                errors.append(f"$.subjects[{index}].id: duplicate subject id {subject_id!r}")
            if isinstance(subject_id, str):
                seen.add(subject_id)
            errors.extend(_subject_errors(index, subject))
    if isinstance(data, dict) and isinstance(data.get("render_intent"), dict):
        from render_contract_lib import validate_intent
        try:
            validate_intent(data["render_intent"], for_generation=require_content)
        except ValueError as exc:
            errors.append(str(exc))
    if require_content and isinstance(data, dict):
        if isinstance(data.get("target_model"), str) and not data["target_model"].strip():
            errors.append("$.target_model is empty; name the model record")
        texts = [(f"$.{field}", data.get(field)) for field in ("source_brief", "image_promise")]
        art = data.get("art_direction")
        if isinstance(art, dict):
            texts += [(f"$.art_direction.{field}", art.get(field)) for field in ART_FIELDS]
        errors.extend(f"{path} is empty; state it or write {UNSPECIFIED!r}"
                      for path, value in texts if isinstance(value, str) and not value.strip())
    state_context = data.get("state_context") if isinstance(data, dict) else None
    errors = list(dict.fromkeys(errors))
    return {
        "ok": not errors,
        "errors": errors,
        "sha256": digest(data) if not non_finite else None,
        "state_mode": state_context.get("mode") if isinstance(state_context, dict) else None,
    }


def require(data: Any, *, require_content: bool = True) -> dict[str, Any]:
    """Return the validation report, or raise every error of the specification once."""
    if not isinstance(data, dict) or not data:
        raise SpecificationError(["$: expected a JSON object"])
    report = validate(data, require_content=require_content)
    if not report["ok"]:
        raise SpecificationError(report["errors"])
    return report


def require_lineage(spec: dict[str, Any], lineage: dict[str, Any]) -> None:
    """Refuse a specification whose state context disagrees with the sealed lineage.

    A stateless specification names no lineage: the builder seals the stateless
    one. A state-aware specification names the hash of its own lineage.
    """
    context = spec.get("state_context") if isinstance(spec.get("state_context"), dict) else {}
    if context.get("mode") != lineage.get("mode"):
        raise ValueError("production specification state mode differs from the state lineage")
    if context.get("mode") == "state-aware" and context.get("state_lineage_sha256") != lineage.get("lineage_sha256"):
        raise ValueError("production specification state-lineage hash mismatch")


def draft(*, model: str, brief: str, subject: str, kind: str, framing: str, render_intent: dict) -> dict[str, Any]:
    """The smallest specification the builder accepts for one subject."""
    spec = load(TEMPLATE)
    spec["render_intent"] = render_intent
    spec["source_brief"] = brief
    spec["image_promise"] = brief
    spec["target_model"] = model
    spec["camera"]["shot_scale"] = framing
    spec["subjects"] = [{
        "id": subject,
        "domain": kind,
        "identity": UNSPECIFIED,
        "current_state": {},
        "proportions_and_form": UNSPECIFIED,
        "surfaces_and_markings": UNSPECIFIED,
        "distinctive_details": [],
        "performance": {field: UNSPECIFIED for field in PERFORMANCE_SCHEMA["required"]},
        "wardrobe_and_accessories": UNSPECIFIED,
        "pose_and_body_geometry": UNSPECIFIED,
        "props_and_contacts": UNSPECIFIED,
    }]
    require(spec, require_content=False)
    return spec


def build_arguments(path: str, subject: str, continuity: str, character: str | None) -> list[str]:
    """The builder arguments that state this subject's continuity."""
    arguments = ["--production-spec-file", path, "--continuity", f"{subject}={continuity}"]
    if character:
        arguments += ["--character", f"{subject}={character}"]
    return arguments


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Draft, validate, show or hash a Production Specification.")
    sub = parser.add_subparsers(dest="command", required=True)
    make = sub.add_parser("draft", help="Write the smallest valid specification for one subject")
    make.add_argument("out", help="New file to write; an existing file is never replaced")
    make.add_argument("--render-intent", required=True, help="Explicit finish choice JSON from render_contract.py intent")
    make.add_argument("--model", required=True, help="The model record the image is made with")
    make.add_argument("--brief", required=True, help="The request in one sentence")
    make.add_argument("--subject", default="C01", help="Subject ID the builder's --continuity names (default C01)")
    make.add_argument("--kind", required=True, choices=DOMAINS)
    make.add_argument("--framing", required=True, choices=FRAMINGS)
    make.add_argument("--continuity", required=True, choices=CONTINUITIES,
                      help="one-off, or undecided for the first images of a character that may recur; "
                           "recurring once the author has accepted an identity image")
    make.add_argument("--character", help="The studio character the subject is recorded under; needed for recurring")
    val = sub.add_parser("validate")
    val.add_argument("spec")
    val.add_argument("--require-content", action="store_true")
    show = sub.add_parser("show")
    show.add_argument("spec")
    hs = sub.add_parser("hash")
    hs.add_argument("spec")
    args = parser.parse_args(argv)
    if args.command == "draft" and args.continuity == "recurring" and not args.character:
        parser.error("--continuity recurring needs --character, the studio character it is recorded under")

    result: Any
    try:
        if args.command == "draft":
            out = Path(args.out)
            if out.exists():
                raise ValueError(f"{out} already exists; choose a new path")
            spec = draft(model=args.model, brief=args.brief, subject=args.subject,
                         kind=args.kind, framing=args.framing, render_intent=load(Path(args.render_intent)))
            with out.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(spec, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
            result = {"created": args.out, "sha256": digest(spec),
                      "build_with": build_arguments(args.out, args.subject, args.continuity, args.character)}
        else:
            data = load(Path(args.spec))
            if args.command == "validate":
                result = validate(data, require_content=args.require_content)
            elif args.command == "show":
                result = data
            else:
                result = {"sha256": digest(data)}
    except (ValueError, OSError) as exc:
        result = {"ok": False, "errors": getattr(exc, "errors", None) or [str(exc)]}
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if not isinstance(result, dict) or result.get("ok", True) else 1


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
