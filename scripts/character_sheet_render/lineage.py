"""Multi-form spine validation and hash-bound form lineage records."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

from character_sheet import validate_sidecar

from character_sheet_render.coverage import coverage_exception_records, sheet_coverage
from character_sheet_render.profiles import (
    load_profile,
    select_profile_path,
    validate_profile_semantics,
)
from character_sheet_render.resolution import apply_sheet_context, resolve_state_panels
from character_sheet_render.sheetdata import (
    json_bytes,
    load_json_object,
    meaningful,
    row_has_visual_data,
    sha256_bytes,
    sha256_file,
    table_entries,
)


FORM_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
FORM_REGISTRY_COLUMNS = (
    "form_id",
    "display_name",
    "kind_ref",
    "trigger_transition",
    "persists",
    "sheet_path",
)
INVARIANT_COLUMNS = ("invariant", "value", "binding", "visible_expression")


def _safe_linked_path(
    root: Path,
    value: str,
    *,
    label: str,
    containment_root: Path | None = None,
) -> Path:
    declared = Path(value)
    if declared.is_absolute() or declared.drive:
        raise ValueError(f"{label} must be a safe relative path")
    resolved = (root / declared).resolve()
    boundary = (containment_root or root).resolve()
    try:
        resolved.relative_to(boundary)
    except ValueError as exc:
        raise ValueError(f"{label} escapes the character spine folder") from exc
    return resolved


def resolve_form_lineage(
    sheet: Mapping[str, Any],
    *,
    sheet_dir: Path,
    sidecar_path: Path | None,
) -> dict[str, Any] | None:
    """Validate and hash-bind the spine's declared full-sheet form roster.

    A form registry is not a request to squeeze transformations into the
    current profile. Each substantive row must point to another complete,
    current-format sheet below the spine directory. The linked sheet declares
    its own form id, reverse link, profile, arbitrary canonical view set, and
    state/detail rows. Cross-form invariants remain on the spine and are hashed
    into the lineage record carried by render-package.json.
    """

    form_entries = [
        entry
        for entry in table_entries(sheet, "formreg")
        if row_has_visual_data(entry["values"], FORM_REGISTRY_COLUMNS)
    ]
    if not form_entries:
        return None
    if sidecar_path is None:
        raise ValueError("a form registry requires a committed spine sheet-data.json path")

    invariant_entries = [
        entry
        for entry in table_entries(sheet, "invariants")
        if row_has_visual_data(entry["values"], INVARIANT_COLUMNS)
    ]
    if not invariant_entries:
        raise ValueError(
            "a multi-form spine must declare at least one cross-form invariant that "
            "makes the forms recognizably one character"
        )
    canonical_invariants: list[dict[str, Any]] = []
    for entry in invariant_entries:
        values = entry["values"]
        missing = [column for column in INVARIANT_COLUMNS if not meaningful(values.get(column, ""))]
        if missing:
            raise ValueError(
                f"cross-form invariant {entry['row_id']} is incomplete: "
                + ", ".join(missing)
            )
        if meaningful(values.get("binding", "")) != "character-fixed":
            raise ValueError(
                f"cross-form invariant {entry['row_id']} must use character-fixed binding"
            )
        canonical_invariants.append(
            {"row_id": entry["row_id"], "values": dict(values)}
        )

    seen_form_ids: set[str] = set()
    linked_forms: list[dict[str, Any]] = []
    spine_path = sidecar_path.resolve()
    for entry in form_entries:
        values = entry["values"]
        missing = [column for column in FORM_REGISTRY_COLUMNS if not meaningful(values.get(column, ""))]
        if missing:
            raise ValueError(
                f"form registry row {entry['row_id']} is incomplete: " + ", ".join(missing)
            )
        form_id = meaningful(values["form_id"])
        if not FORM_ID_RE.fullmatch(form_id):
            raise ValueError(
                f"form registry row {entry['row_id']} has invalid semantic form_id {form_id!r}"
            )
        folded_form_id = form_id.casefold()
        if folded_form_id in seen_form_ids:
            raise ValueError(f"form registry contains duplicate form_id {form_id!r}")
        seen_form_ids.add(folded_form_id)

        linked = _safe_linked_path(
            sheet_dir,
            meaningful(values["sheet_path"]),
            label=f"form registry row {entry['row_id']} sheet_path",
        )
        linked_sidecar = linked / "sheet-data.json" if linked.is_dir() else linked
        if linked_sidecar.name != "sheet-data.json" or not linked_sidecar.is_file():
            raise ValueError(
                f"form registry row {entry['row_id']} must link to an existing "
                "sheet-data.json or its containing directory"
            )
        if linked_sidecar.resolve() == spine_path:
            raise ValueError(
                f"form registry row {entry['row_id']} points back to the spine instead "
                "of a separate full form sheet"
            )
        form_dir = linked_sidecar.parent
        linked_sheet = validate_sidecar(
            load_json_object(linked_sidecar, label=f"form {form_id} sheet-data.json"),
            sheet_root=form_dir,
            verify_files=False,
        )
        linked_fields = (
            linked_sheet.get("fields")
            if isinstance(linked_sheet.get("fields"), Mapping)
            else {}
        )
        declared_form_id = meaningful(linked_fields.get("field.form_id", ""))
        if declared_form_id != form_id:
            raise ValueError(
                f"linked form {form_id!r} must declare field.form_id={form_id!r}; "
                f"found {declared_form_id!r}"
            )
        spine_reference = meaningful(linked_fields.get("field.form_spine_path", ""))
        if not spine_reference:
            raise ValueError(
                f"linked form {form_id!r} must declare field.form_spine_path back to "
                "the spine sheet-data.json"
            )
        linked_spine_path = _safe_linked_path(
            form_dir,
            spine_reference,
            label=f"linked form {form_id!r} field.form_spine_path",
            containment_root=sheet_dir,
        )
        if linked_spine_path.resolve() != spine_path:
            raise ValueError(
                f"linked form {form_id!r} field.form_spine_path does not resolve to "
                "this spine sheet-data.json"
            )

        linked_profile_path, linked_profile_selection = select_profile_path(
            linked_sheet, None, sheet_dir=form_dir
        )
        if not linked_profile_path.is_file():
            raise ValueError(
                f"linked form {form_id!r} profile does not exist: {linked_profile_path}"
            )
        linked_profile = load_profile(linked_profile_path)
        linked_resolved, linked_state_panels = resolve_state_panels(
            linked_profile, linked_sheet
        )
        linked_resolved = apply_sheet_context(linked_resolved, linked_sheet)
        validate_profile_semantics(linked_resolved)
        linked_coverage = sheet_coverage(linked_resolved, linked_sheet)
        if linked_coverage["structural_errors"]:
            raise ValueError(
                f"linked form {form_id!r} violates identity structure: "
                + "; ".join(linked_coverage["structural_errors"])
            )
        if linked_coverage["gaps"]:
            exceptions = meaningful(
                linked_fields.get("field.sheet_coverage_exceptions", "")
            )
            coverage_exception_records(linked_coverage["gaps"], exceptions)

        linked_forms.append(
            {
                "row_id": entry["row_id"],
                "form_id": form_id,
                "display_name": meaningful(values["display_name"]),
                "kind_ref": meaningful(values["kind_ref"]),
                "trigger_transition": meaningful(values["trigger_transition"]),
                "persists": meaningful(values["persists"]),
                "sheet_path": linked_sidecar.relative_to(sheet_dir.resolve()).as_posix(),
                "sheet_data_sha256": sha256_file(linked_sidecar),
                "profile": linked_resolved["id"],
                "profile_sha256": sha256_file(linked_profile_path),
                "profile_selection": linked_profile_selection,
                "canonical_view_count": sum(
                    1
                    for row in linked_resolved["rows"]
                    for box in row["boxes"]
                    if box.get("kind") == "canonical_view"
                ),
                "state_panels": linked_state_panels,
                "coverage_gaps": linked_coverage["gaps"],
                "coverage_warnings": linked_coverage["warnings"],
            }
        )

    return {
        "spine_sheet_data_sha256": sha256_file(sidecar_path),
        "cross_form_invariants": canonical_invariants,
        "cross_form_invariants_sha256": sha256_bytes(json_bytes(canonical_invariants)),
        "forms": linked_forms,
    }
