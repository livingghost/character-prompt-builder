#!/usr/bin/env python3
"""Adopt an iteration through an explicitly approved scope, resumably.

python scripts/adoption_workflow.py --studio DIR --character ID status
python scripts/adoption_workflow.py --studio DIR --character ID adopt --iteration ID --approval FILE
python scripts/adoption_workflow.py --studio DIR --character ID references --out selections.json

See references/runtime/adoption-workflow.md. No image API is called here.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import shutil
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Sequence

import studio
from character_sheet import bind_sidecar, resolve_sheet_relative, validate_sidecar, _validate_ready_package
from pack_manager import (atomic_write_json, generate_uuid7, validate_pack, write_lock,
                          add_pack_root, enable_pack, load_effective_state)
from prompt_plot import APPROVED_AT
from revision_contract import digest
from reference_contract import INTENDED_INFLUENCES

SCOPES = ("sheet", "catalog")
INFLUENCES = INTENDED_INFLUENCES


def safe_file(root: Path, relative: str, expected: str | None = None) -> Path:
    path = resolve_sheet_relative(relative, root=root, field="studio file")
    if expected is not None and studio.sha256_file(path) != expected:
        raise ValueError(f"studio file hash changed: {relative}")
    return path


def _journal_path(home: Path, iteration: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", iteration):
        raise ValueError("invalid iteration identifier")
    folder = home / "adoptions"
    if folder.is_symlink():
        raise ValueError("adoption journal folder must not be a symbolic link")
    path = folder / f"{iteration}.json"
    if path.is_symlink():
        raise ValueError("adoption journal must not be a symbolic link")
    return path


def validate_approval(value: Any, character: str, row: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("adoption requires an explicit approval object")
    required = {"scope", "influence", "character", "iteration_id", "slot", "image_sha256", "by", "at"}
    if required - set(value) or set(value) - required - {"note", "license", "registration_record_sha256", "continuity_decision"}:
        raise ValueError("approval fields must be scope, influence, character, iteration_id, slot, image_sha256, by, at; optional note, license, registration_record_sha256 and continuity_decision")
    if value["scope"] not in SCOPES or value["influence"] not in INFLUENCES:
        raise ValueError("unknown adoption scope or influence")
    expected = {"character": character, "iteration_id": row["iteration_id"], "slot": row["slot"],
                "image_sha256": row["result"]["sha256"]}
    for key, item in expected.items():
        if value.get(key) != item:
            raise ValueError(f"approval does not match {key}")
    if not isinstance(value["by"], str) or not value["by"].strip() or not isinstance(value["at"], str) or not APPROVED_AT.fullmatch(value["at"]):
        raise ValueError("approval requires who approved and the actual UTC approval timestamp")
    if "license" in value and (not isinstance(value["license"], str) or not value["license"].strip()):
        raise ValueError("license must be a nonempty explicit license identifier")
    if value["influence"] != "identity" and row["slot"].startswith(("base.", "canon.")):
        raise ValueError("base/canon identity slots cannot be replaced by outfit or scene references")
    return copy.deepcopy(value)


def _bind_sheet(root: Path, home: Path, row: dict[str, Any]) -> dict[str, Any]:
    sheet = home / "sheet"
    sidecar_path = sheet / "sheet-data.json"
    safe_file(root, sidecar_path.relative_to(root).as_posix())
    sidecar = studio.read_json(sidecar_path)
    validate_sidecar(sidecar, sheet_root=sheet, verify_files=True)
    source = safe_file(root, row["result"]["path"], row["result"]["sha256"])
    if not row.get("package"):
        raise ValueError("sheet adoption requires the recorded generation package; record its provenance before adopting")
    package = safe_file(root, row["package"]["path"], row["package"]["sha256"])
    package_value = studio.read_json(package)
    _validate_ready_package(package_value, field="iteration package")
    # Copies remain inside the sheet. Never weaken its containment rules.
    bindings = sheet / "bindings"
    if bindings.is_symlink():
        raise ValueError("sheet bindings must not be a symbolic link")
    bindings.mkdir(exist_ok=True)
    destination = bindings / row["iteration_id"]
    if destination.is_symlink():
        raise ValueError("sheet binding must not be a symbolic link")
    image_name = "image" + source.suffix.lower()
    if not destination.exists():
        staging = Path(tempfile.mkdtemp(prefix=".binding-", dir=bindings))
        try:
            shutil.copyfile(source, staging / image_name)
            shutil.copyfile(package, staging / "package.json")
            # Preserve portable carriers under their committed names. A copy of
            # the package without its companion is not a reusable provenance file.
            from build_generation_payload import validate_generation_package_carrier_paths
            prepared = package_value.get("prepared_reference_set")
            if isinstance(prepared, dict):
                companion = validate_generation_package_carrier_paths(prepared, package_root=package.parent)
                if companion:
                    source_dir = package.parent / companion
                    if source_dir.is_symlink() or any(p.is_symlink() for p in source_dir.rglob("*")):
                        raise ValueError("package companion must contain no symbolic links")
                    shutil.copytree(source_dir, staging / companion)
            os.rename(staging, destination)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
    safe_file(sheet, (destination / image_name).relative_to(sheet).as_posix(), row["result"]["sha256"])
    safe_file(sheet, (destination / "package.json").relative_to(sheet).as_posix(), row["package"]["sha256"])
    existing = sidecar["slots"].get(row["slot"], {})
    sidecar["slots"][row["slot"]] = {
        **existing,
        "image_path": (destination / image_name).relative_to(sheet).as_posix(),
        "generation_package": (destination / "package.json").relative_to(sheet).as_posix(),
        "image_sha256": row["result"]["sha256"],
        "generation_package_sha256": row["package"]["sha256"],
    }
    bound = bind_sidecar(sidecar, sheet_root=sheet)
    atomic_write_json(sidecar_path, bound)
    return bound["slots"][row["slot"]]


def _registration(root: Path, row: dict[str, Any], journal: dict[str, Any], record: dict[str, Any], target: Path) -> dict[str, Any]:
    from pack_manager import initial_pack_release
    from prepare_generation_references import detect_image_media_type, image_dimensions
    target = target.absolute()
    if target.is_symlink() or any(parent.is_symlink() for parent in target.parents):
        raise ValueError("registration target must not traverse symbolic links")
    target = target.resolve()
    if target.exists():
        report = validate_pack(target, require_lock=True)
        receipt = studio.read_json(target / "resources" / "adoption-receipt.json")
        if not report.valid or report.pack_id != journal["registration_pack_id"] or receipt.get("approval") != journal["approval"]:
            raise ValueError("registration target belongs to another adoption or its content changed; it will not be overwritten")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".adoption-pack-", dir=target.parent))
        try:
            (staging / "records").mkdir()
            (staging / "resources").mkdir()
            source = safe_file(root, row["result"]["path"], row["result"]["sha256"])
            media = detect_image_media_type(source)
            width, height = image_dimensions(source, media)
            image_rel = "resources/reference" + source.suffix.lower()
            shutil.copyfile(source, staging / image_rel)
            atomic_write_json(staging / "pack.json", {
                "pack_id": journal["registration_pack_id"], "name": record["label"] + " adopted reference",
                "description": "Explicitly adopted studio reference with bounded visual authority.",
                "release": initial_pack_release(),
                "content": {"record_globs": ["records/**/*.json"], "resource_globs": ["resources/**/*"], "resource_bindings": {}},
                "capabilities": ["atomic-modules", "visual-reference-assets", "searchable-assets", "evidence-artifact-reference"], "dependencies": [],
                "optional_dependencies": [], "replaces": [], "license": journal["approval"].get("license", "UNLICENSED"),
            })
            atomic_write_json(staging / "records" / "canonical.json", {"kind": "module", "category": record["category"], "records": [record]})
            asset_id = record["id"] + "-reference"
            atomic_write_json(staging / "records" / "assets.json", {"kind": "asset", "records": [{
                "id": asset_id, "label": record["label"] + " reference", "curation_status": "curated",
                "category": "visual-reference", "asset_type": "reference-guide",
                "description": "User-adopted reference; controls only " + journal["approval"]["influence"],
                "source_ref_id": row["iteration_id"], "source_sha256": row["result"]["sha256"],
                "source_media_type": media, "source_dimensions": {"width": width, "height": height},
                "disposition": "user-adopted-reference", "evidence_relation": journal["approval"]["influence"],
                "canonical_record_ids": [record["id"]], "primary_resource": image_rel,
                "resource_refs": [image_rel, "resources/adoption-receipt.json"],
                "artifacts": [{"artifact_id": "adopted-image", "role": "adopted-reference", "path": image_rel,
                               "media_type": media, "sha256": row["result"]["sha256"]}],
                "tags": ["adopted reference", journal["approval"]["influence"]],
                "adoption_scope": {"intended_influence": journal["approval"]["influence"],
                                   "receipt_resource": "resources/adoption-receipt.json"},
            }]})
            atomic_write_json(staging / "resources" / "adoption-receipt.json", {
                "artifact_type": "studio-adoption-receipt", "approval": journal["approval"],
                "studio_id": studio.manifest(root)["studio_id"], "pack_id": journal["registration_pack_id"],
                "canonical_record_id": record["id"], "asset_id": asset_id,
                "image_sha256": row["result"]["sha256"], "record_sha256": digest(record),
                "authority": {"controls": [journal["approval"]["influence"]],
                              "must_not_control": [role for role in INFLUENCES if role != journal["approval"]["influence"]]},
            })
            write_lock(staging)
            report = validate_pack(staging, require_lock=True)
            if not report.valid:
                raise ValueError("registration pack is invalid: " + "; ".join(i.message for i in report.issues))
            os.rename(staging, target)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
    return {"pack_path": str(target), "pack_id": journal["registration_pack_id"],
            "record_id": record["id"], "asset_id": record["id"] + "-reference", "artifact_id": "adopted-image"}


def adopt(root: Path, character: str, iteration: str, approval: Any, *,
          registration_record: dict[str, Any] | None = None, pack_dir: Path | None = None,
          settings: Any = None) -> dict[str, Any]:
    root = studio.require_studio(root).resolve()
    with studio.recording_lock(root):
        home = studio.character_dir(root, character)
        row = studio._find(studio.read_iterations(home), iteration)
        studio.validate_recording_target(root, character, row["slot"], writable=True)
        if row["status"] in {"rejected", "superseded"}:
            raise ValueError("record a new candidate before adopting a rejected or superseded iteration")
        if not row.get("result"):
            raise ValueError("iteration has no result")
        confirmed = validate_approval(approval, character, row)
        safe_file(root, row["result"]["path"], row["result"]["sha256"])
        if not row.get("package"):
            raise ValueError("sheet adoption needs the recorded generation package")
        safe_file(root, row["package"]["path"], row["package"]["sha256"])
        if confirmed['influence'] == 'identity':
            from visual_continuity import adoption_subject
            adoption_subject(root, character, row, confirmed)
        if confirmed["scope"] == "catalog":
            if not isinstance(registration_record, dict) or pack_dir is None or settings is None:
                raise ValueError("catalog adoption requires --registration-record, --pack-dir and a resolved pack runtime")
            from pack_manager import _schema_issues, PACK_RECORD_SCHEMA_PATH
            issues = _schema_issues({"kind": "module", "category": registration_record.get("category"), "records": [registration_record]}, PACK_RECORD_SCHEMA_PATH, Path("registration-record.json"))
            if issues:
                raise ValueError("registration record is not a valid canonical module: " + "; ".join(i.message for i in issues))
            if confirmed.get("registration_record_sha256") != digest(registration_record):
                raise ValueError("catalog approval must bind registration_record_sha256")
        elif registration_record is not None or pack_dir is not None:
            raise ValueError("registration arguments require catalog scope")
        path = _journal_path(home, iteration)
        journal = studio.read_json(path) if path.exists() else {
            "artifact_type": "studio-adoption", "approval": confirmed, "status": "pending",
            "next_action": "accept-candidate", "registration": None,
        }
        # Promotion from sheet to catalog requires a new explicit catalog approval.
        if journal["approval"] != confirmed:
            if journal["approval"]["scope"] == "sheet" and confirmed["scope"] == "catalog" and all(
                journal["approval"][k] == confirmed[k] for k in ("character", "iteration_id", "slot", "image_sha256", "influence")):
                journal["previous_approval"] = journal["approval"]
                journal["approval"] = confirmed
            else:
                raise ValueError("resume approval differs from the recorded adoption")
        if confirmed["scope"] == "catalog":
            target = str(pack_dir.resolve())
            if journal.get("registration_target") not in {None, target}:
                raise ValueError("resume registration target differs from the recorded adoption")
            journal["registration_target"] = target
            journal.setdefault("registration_pack_id", generate_uuid7())
            journal["runtime_state_file"] = str(settings.state_file)
        atomic_write_json(path, journal)
        try:
            if row["status"] != "accepted":
                row = studio._record_accept(root, character, iteration)
            journal.update(status="candidate-accepted", next_action="bind-sheet")
            atomic_write_json(path, journal)
            slot = _bind_sheet(root, home, row)
            journal.update(status="sheet-bound", sheet_binding=slot,
                           next_action="register-pack" if confirmed["scope"] == "catalog" else None)
            atomic_write_json(path, journal)
            if confirmed["scope"] == "catalog":
                journal["registration"] = _registration(root, row, journal, registration_record, pack_dir)
                journal["next_action"] = "activate-pack"
                atomic_write_json(path, journal)
                add_pack_root(settings, Path(journal["registration"]["pack_path"]))
                enable_pack(settings, journal["registration_pack_id"])
                journal.update(status="catalog-registered", next_action=None, runtime_restart_required=True)
                atomic_write_json(path, journal)
            journal.pop("last_error", None)
            atomic_write_json(path, journal)
            atomic_write_json(home / "sheet" / "active-references.json", reference_index(root, character))
        except (OSError, ValueError, RuntimeError) as exc:
            journal["last_error"] = str(exc)
            try:
                atomic_write_json(path, journal)
            except OSError:
                pass
            raise
        return {"ok": True, **journal}


def reference_index(root: Path, character: str) -> dict[str, Any]:
    home = studio.character_dir(root, character)
    sheet = home / "sheet"
    sidecar = studio.read_json(sheet / "sheet-data.json")
    validate_sidecar(sidecar, sheet_root=sheet, verify_files=True)
    rows = studio.read_iterations(home)
    accepted = {row["slot"]: row for row in rows if row.get("status") == "accepted"}
    errors: list[str] = []
    pending: list[dict[str, Any]] = []
    accepted_ids = {row["iteration_id"] for row in accepted.values()}
    for row in rows:
        path = _journal_path(home, row["iteration_id"])
        if row["iteration_id"] not in accepted_ids and path.is_file():
            journal = studio.read_json(path)
            if journal.get("next_action") and row.get("status") not in {"rejected", "superseded"}:
                pending.append({"iteration_id": row["iteration_id"], "next_action": journal["next_action"]})
                errors.append(f"{row['slot']}: adoption incomplete; resume {row['iteration_id']}: {journal['next_action']}")
    bindings: list[dict[str, Any]] = []
    for slot, row in sorted(accepted.items()):
        safe_file(root, row["result"]["path"], row["result"]["sha256"])
        path = _journal_path(home, row["iteration_id"])
        journal = studio.read_json(path) if path.is_file() else None
        bound = sidecar["slots"].get(slot)
        has_binding = bool(bound and bound.get("image_path"))
        complete = has_binding and bound.get("image_sha256") == row["result"]["sha256"]
        state = "sheet-bound" if complete else "candidate-accepted"
        if has_binding and not complete:
            errors.append(f"{slot}: latest accepted image is not bound to the sheet; resume adoption of {row['iteration_id']}")
        if journal and journal.get("next_action"):
            errors.append(f"{slot}: adoption incomplete; next action: {journal['next_action']}")
        if journal and journal.get("registration") and complete:
            registration = journal["registration"]
            report = validate_pack(Path(registration["pack_path"]), require_lock=True)
            if not report.valid or report.pack_id != registration["pack_id"]:
                errors.append(f"{slot}: registered pack changed or is missing")
            else:
                state = "catalog-registered"
        bindings.append({"slot": slot, "iteration_id": row["iteration_id"], "status": state,
                         "image_sha256": row["result"]["sha256"],
                         "image_path": str((sheet / bound["image_path"]).resolve()) if complete else None,
                         "influence": journal["approval"]["influence"] if journal else "identity",
                         "registration": journal.get("registration") if journal else None,
                         "next_action": journal.get("next_action") if journal else (None if complete else "adopt-with-sheet-scope")})
    return {"artifact_type": "studio-reference-index", "ok": not errors, "character": character,
            "bindings": bindings, "pending_adoptions": pending, "errors": errors}


def supplied_selection(root: Path, character: str) -> list[dict[str, Any]]:
    index = reference_index(root, character)
    if not index["ok"]:
        raise ValueError("reference workflow is incomplete: " + "; ".join(index["errors"]))
    return [{"role": item["influence"], "source": {"kind": "supplied-file",
             "reference_id": (character + "-" + item["slot"] + "-" + item["iteration_id"]).lower(),
             "resolved_path": item["image_path"]}}
            for item in index["bindings"] if item["image_path"]]


def validate_for_generation(root: Path, character: str, package: dict[str, Any]) -> None:
    index = reference_index(root, character)
    if not index["ok"]:
        raise ValueError("reference workflow is incomplete: " + "; ".join(index["errors"]))
    bound = [item for item in index["bindings"] if item["image_path"]]
    selected = (package.get("prepared_reference_set") or {}).get("selected_references") or []
    plan_items = ((package.get("prepared_reference_set") or {}).get("reference_use_plan") or {}).get("reference_items") or []
    planned_scopes: dict[str, set[str]] = {}
    for item in plan_items:
        planned_scopes.setdefault(digest(item.get("source")), set()).add(item.get("intended_influence"))
    selected_by_scope: dict[str, set[str]] = {}
    for item in selected:
        scopes = set(planned_scopes.get(digest(item.get("source")), set()))
        declared = item.get("intended_influence") or []
        scopes.update([declared] if isinstance(declared, str) else declared)
        if item.get("role") in INFLUENCES:
            scopes.add(item["role"])
        sha = (item.get("source") or {}).get("sha256")
        for scope in scopes & set(INFLUENCES):
            selected_by_scope.setdefault(scope, set()).add(sha)
    current_by_scope: dict[str, set[str]] = {}
    for item in bound:
        current_by_scope.setdefault(item["influence"], set()).add(item["image_sha256"])
    identities = current_by_scope.get("identity", set())
    if identities and not selected_by_scope.get("identity", set()).intersection(identities):
        raise ValueError("generation does not reference a current adopted identity image; export references and rebuild the package")
    home = studio.character_dir(root, character)
    for row in studio.read_iterations(home):
        if row.get("status") != "superseded":
            continue
        journal_path = _journal_path(home, row["iteration_id"])
        # A superseded candidate without adoption has no granted reference scope.
        journal = studio.read_json(journal_path) if journal_path.is_file() else None
        scope = journal["approval"]["influence"] if journal else "identity"
        old_hash = (row.get("result") or {}).get("sha256")
        if old_hash in selected_by_scope.get(scope, set()) and old_hash not in current_by_scope.get(scope, set()):
            raise ValueError(f"generation includes a superseded {scope} image; replace it with the latest adopted reference")


def main(argv: Sequence[str] | None = None) -> int:
    from pack_runtime_cli import add_pack_runtime_arguments, resolve_pack_runtime
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--studio", type=Path, required=True)
    parser.add_argument("--character", required=True)
    add_pack_runtime_arguments(parser)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    adopt_parser = sub.add_parser("adopt")
    adopt_parser.add_argument("--iteration", required=True)
    adopt_parser.add_argument("--approval", required=True, type=Path)
    adopt_parser.add_argument("--registration-record", type=Path)
    adopt_parser.add_argument("--pack-dir", type=Path)
    refs = sub.add_parser("references")
    refs.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        root = studio.require_studio(args.studio)
        if args.command == "adopt":
            approval = studio.read_json(args.approval)
            runtime = resolve_pack_runtime(parser, args) if approval.get("scope") == "catalog" else None
            result = adopt(root, args.character, args.iteration, approval,
                           registration_record=studio.read_json(args.registration_record) if args.registration_record else None,
                           pack_dir=args.pack_dir, settings=runtime.settings if runtime else None)
        elif args.command == "references":
            selections = supplied_selection(root, args.character)
            atomic_write_json(args.out, selections)
            result = {"ok": True, "selection_count": len(selections), "output": str(args.out)}
        else:
            result = reference_index(root, args.character)
    except (OSError, ValueError, RuntimeError) as exc:
        result = {"ok": False, "errors": [str(exc)]}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
