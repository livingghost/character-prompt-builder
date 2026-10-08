#!/usr/bin/env python3
"""Validate safe JSON sidecars and immutable artwork selections for the CPB Character Sheet."""
from __future__ import annotations
import operation_context as _operation_context

import argparse
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from execution_contract import atomic_write_json, sha256_file
from state_protocol import parse_json, validate_against_schema

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "character-sheet-data.schema.json"
BLANK_TEMPLATE_PATH = ROOT / "templates" / "character-sheet-data.blank.json"
PLACEHOLDERS = frozenset({"", "-", "unknown", "tbd", "n/a", "not applicable", "unspecified"})
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")


def meaningful_identity(value: Any) -> bool:
    return isinstance(value, str) and value.strip().casefold() not in PLACEHOLDERS


def sheet_status(value: Mapping[str, Any]) -> str:
    fields = value.get("fields") if isinstance(value.get("fields"), Mapping) else {}
    if not meaningful_identity(fields.get("identity.name")) or not meaningful_identity(
        fields.get("identity.species_domain")
    ):
        return "draft"
    slots = value.get("slots") if isinstance(value.get("slots"), Mapping) else {}
    primary = slots.get("canon.primary") if isinstance(slots.get("canon.primary"), Mapping) else {}
    from sheet_artifacts import current_artifact
    if current_artifact(primary) is not None:
        return "reference-ready"
    return "identity-ready"


def _validate_semantic_ids(value: Mapping[str, Any]) -> None:
    """Keep exported rows stable and scoped to their owning table."""

    tables = value.get("tables")
    if not isinstance(tables, Mapping):
        return
    seen_global: set[str] = set()
    for table_id, raw_rows in sorted(tables.items()):
        if not isinstance(table_id, str) or not isinstance(raw_rows, list):
            continue
        expected_prefix = f"{table_id}."
        seen_local: set[str] = set()
        for index, raw_row in enumerate(raw_rows):
            if not isinstance(raw_row, Mapping):
                continue
            row_id = raw_row.get("row_id")
            if not isinstance(row_id, str):
                continue
            if not row_id.startswith(expected_prefix):
                raise ValueError(
                    f"tables.{table_id}[{index}].row_id must start with "
                    f"{expected_prefix!r}"
                )
            if row_id in seen_local:
                raise ValueError(f"tables.{table_id} contains duplicate row_id {row_id!r}")
            if row_id in seen_global:
                raise ValueError(f"row_id {row_id!r} is duplicated across tables")
            seen_local.add(row_id)
            seen_global.add(row_id)


def _validate_ready_package(value: Any, *, field: str) -> None:
    if not isinstance(value, Mapping) or value.get("status") != "ready":
        raise ValueError(f"{field} must contain a ready package object")
    if value.get("artifact_type") == "upscale-package":
        from state_protocol import validate_artifact

        report = validate_artifact(dict(value))
        if report.get("ok") is not True:
            raise ValueError(
                f"{field} contains an invalid Upscale Package: "
                + "; ".join(report.get("errors", []))
            )
        return
    generation_hash = value.get("generation_input_sha256")
    if (
        not isinstance(generation_hash, str)
        or not SHA256_RE.fullmatch(generation_hash)
        or generation_hash == "0" * 64
        or not isinstance(value.get("generation_payload"), Mapping)
        or not isinstance(value.get("generation_contract"), Mapping)
        or not isinstance(value.get("model"), str)
        or not value.get("model", "").strip()
    ):
        raise ValueError(
            f"{field} must be a structurally committed Generation Package or Upscale Package"
        )


def resolve_sheet_relative(stored: str, *, root: Path, field: str) -> Path:
    if not isinstance(stored, str) or not stored or "\\" in stored:
        raise ValueError(f"{field} must be a non-empty POSIX path")
    pure = PurePosixPath(stored)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise ValueError(f"{field} must be a safe path relative to the sheet folder")
    base = root.resolve(strict=True)
    candidate = base / Path(stored)
    cursor = base
    for part in pure.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError(f"{field} must not traverse a symbolic link")
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"{field} escapes the sheet folder") from exc
    if not resolved.is_file():
        raise ValueError(f"{field} must identify a regular file")
    return resolved


def validate_sidecar(
    value: Any,
    *,
    sheet_root: Path | None = None,
    verify_files: bool = False,
) -> dict[str, Any]:
    schema = parse_json(SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = validate_against_schema(value, schema)
    if errors:
        raise ValueError("invalid character sheet sidecar: " + "; ".join(errors))
    assert isinstance(value, dict)
    _validate_semantic_ids(value)
    expected = sheet_status(value)
    if value.get("sheet_status") != expected:
        raise ValueError(
            f"sheet_status must be {expected!r} for the committed minimum identity/provenance fields"
        )
    for table_id, rows in sorted(value.get("tables", {}).items()):
        row_ids = [row.get("row_id") for row in rows if isinstance(row, Mapping)]
        if len(row_ids) != len(set(row_ids)):
            raise ValueError(f"tables.{table_id} contains duplicate row_id values")
    from sheet_artifacts import verify_artifact, verify_acceptance
    for slot_id, slot in value['slots'].items():
        candidate_ids = [item['artifact_id'] for item in slot['candidates']]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError(f'slots.{slot_id} contains duplicate candidates')
        current = slot['current']
        if current is not None and current['artifact']['artifact_id'] in candidate_ids:
            raise ValueError(f'slots.{slot_id} current artwork must not also be a candidate')
        if verify_files:
            if sheet_root is None:
                raise ValueError('verify_files requires sheet_root')
            for item in slot['candidates']:
                verify_artifact(item, sheet_root)
            for accepted in [*slot['history'], *([current] if current is not None else [])]:
                verify_acceptance(accepted, sheet_root, slot_id)
    return json.loads(json.dumps(value, ensure_ascii=False))




def initialize_sidecar(sheet_dir: Path, *, profile: str = "") -> Path:
    """Create a current blank sidecar without overwriting an existing one."""

    template = parse_json(BLANK_TEMPLATE_PATH.read_text(encoding="utf-8"))
    if not isinstance(template, dict):
        raise ValueError("the blank Character Sheet template must be a JSON object")
    fields = template.get("fields")
    if not isinstance(fields, dict):
        raise ValueError("the blank Character Sheet template must contain fields")
    fields["field.sheet_layout_profile"] = profile.strip()
    normalized = validate_sidecar(template)

    target_dir = sheet_dir.resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    output_path = target_dir / "sheet-data.json"
    if output_path.exists():
        raise ValueError(f"refusing to overwrite existing sidecar: {output_path}")
    atomic_write_json(output_path, normalized)
    return output_path


def main(argv: Sequence[str] | None = None) -> int:
    parser = _operation_context.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    init_parser = sub.add_parser(
        "init", help="create a current blank sheet-data.json in a new or empty folder"
    )
    init_parser.add_argument("sheet_dir", type=Path)
    init_parser.add_argument(
        "--profile",
        default="",
        help="optional bundled layout profile id or authored layout profile path",
    )
    validate_parser = sub.add_parser("validate")
    validate_parser.add_argument("sidecar", type=Path)
    validate_parser.add_argument("--verify-files", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "init":
        output_path = initialize_sidecar(args.sheet_dir, profile=args.profile)
        print(
            json.dumps(
                {"ok": True, "sheet_status": "draft", "sidecar": str(output_path)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    sidecar_path = args.sidecar.resolve(strict=True)
    value = parse_json(sidecar_path.read_text(encoding="utf-8"))
    result = validate_sidecar(value, sheet_root=sidecar_path.parent, verify_files=args.verify_files)
    print(json.dumps({"ok": True, "sheet_status": result["sheet_status"]}, indent=2))
    return 0


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(_operation_context.run_cli(main))
