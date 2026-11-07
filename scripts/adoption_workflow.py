#!/usr/bin/env python3
"""Adopt an iteration through an explicitly approved scope, resumably.

python scripts/adoption_workflow.py --studio DIR --character ID status
python scripts/adoption_workflow.py --studio DIR --character ID adopt --iteration ID --approval FILE
python scripts/adoption_workflow.py --studio DIR --character ID references --out selections.json

See references/runtime/adoption-workflow.md. No image API is called here.
A Production candidate is adopted with production_workflow.py adopt, which
records the claim this module checks.
"""
from __future__ import annotations
import operation_context as _operation_context

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
from character_sheet import resolve_sheet_relative, validate_sidecar, _validate_ready_package
from sheet_artifacts import current_artifact
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


def _bind_sheet(root: Path, home: Path, row: dict[str, Any], approval: dict, journal: dict) -> dict[str, Any]:
    import sheet_artifacts as fills
    sheet = home / 'sheet'
    sidecar_path = sheet / 'sheet-data.json'
    artifact = fills.from_iteration(root, row['character'], row)
    # The adoption journal pins expected_current before its first bind. Retrying
    # does not replace a different selection made after that author decision.
    decision = journal.get('sheet_decision')
    if decision is None:
        decision = fills.draft_adoption(sidecar_path, row['slot'], artifact['artifact_id'])
        evidence_file = _journal_path(home, row['iteration_id']).with_suffix('.approval.json')
        if evidence_file.exists() and studio.read_json(evidence_file) != approval:
            raise ValueError('recorded adoption approval differs from its immutable evidence')
        if not evidence_file.exists(): atomic_write_json(evidence_file, approval)
        decision.update(by=approval['by'], at=approval['at'],
            reason=approval.get('note') or 'Explicit author approval for the named Studio iteration.',
            evidence={'path': evidence_file.relative_to(root).as_posix(), 'sha256': studio.sha256_file(evidence_file), 'locator': 'whole approval'})
        if row.get('production'):
            decision['basis'] = {'kind': 'production', 'claim': journal['production_claim'], 'approval': approval}
        journal['sheet_decision'] = decision
        atomic_write_json(_journal_path(home, row['iteration_id']), journal)
    fills.adopt(sidecar_path, decision, evidence_root=root)
    return studio.read_json(sidecar_path)['slots'][row['slot']]


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


def require_production_claim(root: Path, character: str, row: dict[str, Any], approval: Any,
                             claim: str | None, *, require_current: bool = False) -> None:
    """Refuse adopting a Production candidate outside the claim its own adopt operation recorded.

    `production_workflow.py adopt` records that claim under an adopt
    authorization; it names the candidate, character, iteration and approval.
    """
    origin = row["production"]
    if claim is None:
        raise ValueError(f"{row['iteration_id']} is a Production candidate; adopt it with production_workflow.py adopt "
                         f"under its own adopt authorization")
    import production_workflow as workflow
    _, prepared, _, rows = workflow.load_run(root, origin["run"])
    found = [event for event in rows if event["event"] == "adoption-claim" and event["sha256"] == claim]
    payload = found[0]["data"]["intent"]["payload"] if found else None
    from execution_contract import content_id
    if payload is None or payload["candidate"] != origin["candidate"] or payload["character"] != character \
            or payload["iteration"] != row["iteration_id"] or payload["approval_sha256"] != content_id(approval):
        raise ValueError("the Production adoption claim does not name this candidate, iteration and approval")
    recorded = found[0]
    tokens = recorded['data']['authorizations']
    if len(tokens) != 1:
        raise ValueError('the Production adoption claim needs its exact authorization')
    request = workflow.find(rows, 'authorization', tokens[0])['data']['request']
    from production_diagnostics import compare_exact
    compare_exact(recorded['data']['intent'],
                  {key: request[key] for key in ('operation', 'targets', 'payload')}, phase='adoption')
    if request['actor'] != approval['by']:
        raise ValueError('adoption approver differs from the recorded authorized actor')
    if require_current:
        workflow._permission(root, prepared, rows, tokens[0], **recorded['data']['intent'])
        if not any(event['event'] == 'operation-start'
                   and event['data'].get('claim') == claim
                   and event['data'].get('authorization_sha256') == tokens[0]
                   and event['data'].get('effect') == 'local-action' for event in rows):
            raise ValueError('the Production adoption claim has no recorded local operation boundary')


def require_adoption_source(root: Path, character: str, row: dict[str, Any]) -> None:
    """Check retained source eligibility for both status and an actual adoption.

    This read establishes neither approval nor reference influence. A completed
    production decision remains usable evidence for the separately authorized
    adoption of its selected candidate.
    """
    from production_diagnostics import ProductionError
    if row['status'] in {'rejected', 'superseded'}:
        raise ValueError('record a new candidate before adopting a rejected or superseded iteration')
    if not row.get('result'):
        raise ValueError('iteration has no result')
    studio.validate_recording_target(root, character, row['slot'])
    origin = row.get('production')
    if origin is not None:
        import production_workflow as workflow
        _, prepared, _, rows = workflow.load_run(root, origin['run'])
        workflow.require_selected(prepared, rows, origin['candidate'], run=origin['run'])
    safe_file(root, row['result']['path'], row['result']['sha256'])
    if not row.get('package'):
        action = ('Recover this Production candidate\'s recorded package from its retained run evidence.'
                  if origin else
                  'Record the original package on this iteration with studio.py attach-package, '
                  'including the evidence that relates it to this image; then adopt the same iteration.')
        raise ProductionError('ADOPTION_PACKAGE_REQUIRED',
            'Sheet adoption needs the iteration\'s recorded generation package.',
            phase='adoption', iteration=row['iteration_id'], required_action=action)
    package_path = safe_file(root, row['package']['path'], row['package']['sha256'])
    _validate_ready_package(studio.read_json(package_path), field='adoption source')
    studio.validate_package_attachment(root, row)


def adoption_readiness(root: Path, character: str, row: dict[str, Any]) -> dict[str, Any]:
    """Expose the same mechanical prerequisites as preflight, without a decision."""
    from production_diagnostics import from_exception
    origin = row.get('production')
    result = {'owner': 'production' if origin else 'studio', 'source_ready': False,
              'production': origin, 'diagnostics': [], 'next_action': None}
    try:
        require_adoption_source(root, character, row)
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        diagnostic = from_exception(exc, phase='adoption')
        result['diagnostics'] = [diagnostic]
        if diagnostic['code'] == 'ADOPTION_PACKAGE_REQUIRED' and origin is None:
            result['next_action'] = 'record-generation-package'
        elif diagnostic['code'] in {'SELECTION_REQUIRED', 'SELECTION_WITHDRAWN', 'SELECTION_REVIEW_CHANGED'}:
            result['next_action'] = 'inspect-production-selection'
        else:
            result['next_action'] = 'repair-reference'
    else:
        result['source_ready'] = True
        result['next_action'] = 'adopt-production-candidate' if origin else 'adopt-with-sheet-scope'
    return result


def preflight(root: Path, character: str, iteration: str, approval: Any, *,
              expected_production: dict[str, str] | None = None, expected_image: str | None = None,
              registration_record: dict[str, Any] | None = None, pack_dir: Path | None = None,
              settings: Any = None, production_claim: str | None = None,
              require_claim: bool = False) -> tuple[dict, dict]:
    """Read canonical eligibility before an authorization, claim or Studio mutation.

    Production supplies its exact origin at intent time. The mutating owner
    additionally requires its recorded claim and catalog runtime. Imported rows
    keep their own ordinary adoption path even when their image bytes match a
    Production candidate.
    """
    from production_diagnostics import ProductionError
    root = studio.require_studio(root).resolve()
    home = studio.character_home(root, character)
    row = studio._find(studio.read_iterations(home), iteration)
    origin = row.get('production')
    if expected_production is not None and origin != expected_production:
        action = ('Use studio.py accept for slot acceptance or adoption_workflow.py adopt for sheet/catalog adoption.'
                  if origin is None else 'Use the Production run and candidate recorded by this exact iteration.')
        raise ProductionError('ADOPTION_OWNER_MISMATCH',
            'Canonical Production adoption requires this iteration to belong to the exact run and candidate.',
            phase='adoption', expected=expected_production, actual=origin, required_action=action)
    require_adoption_source(root, character, row)
    if expected_image is not None and row['result']['sha256'] != expected_image:
        raise ValueError('adoption targets a different candidate')
    if origin is not None:
        if require_claim:
            require_production_claim(root, character, row, approval, production_claim, require_current=True)
    elif production_claim is not None:
        raise ValueError(f'{iteration} is an external import; a Production adoption claim does not apply')
    confirmed = validate_approval(approval, character, row)
    if confirmed['influence'] == 'identity':
        from visual_continuity import adoption_subject
        adoption_subject(root, character, row, confirmed)
    if confirmed['scope'] == 'catalog':
        if not isinstance(registration_record, dict) or pack_dir is None or (require_claim and settings is None):
            raise ValueError('catalog adoption requires --registration-record, --pack-dir and a resolved pack runtime')
        from pack_manager import _schema_issues, PACK_RECORD_SCHEMA_PATH
        issues = _schema_issues({'kind': 'module', 'category': registration_record.get('category'),
                                 'records': [registration_record]}, PACK_RECORD_SCHEMA_PATH, Path('registration-record.json'))
        if issues:
            raise ValueError('registration record is not a valid canonical module: ' + '; '.join(i.message for i in issues))
        if confirmed.get('registration_record_sha256') != digest(registration_record):
            raise ValueError('catalog approval must bind registration_record_sha256')
    elif registration_record is not None or pack_dir is not None:
        raise ValueError('registration arguments require catalog scope')
    path = _journal_path(home, iteration)
    if path.exists():
        journal = studio.read_json(path)
        prior = journal['approval']
        promotion = (prior['scope'] == 'sheet' and confirmed['scope'] == 'catalog'
                     and all(prior[key] == confirmed[key]
                             for key in ('character', 'iteration_id', 'slot', 'image_sha256', 'influence')))
        if prior != confirmed and not promotion:
            raise ValueError('resume approval differs from the recorded adoption')
        if confirmed['scope'] == 'catalog' and journal.get('registration_target') not in {None, str(pack_dir.resolve())}:
            raise ValueError('resume registration target differs from the recorded adoption')
        decision = journal.get('sheet_decision')
        if decision is not None:
            import execution_contract as contract
            slot = studio.read_json(home / 'sheet' / 'sheet-data.json')['slots'][row['slot']]
            current = slot['current']
            current_id = current['artifact']['artifact_id'] if current else None
            applied = current is not None and current['approval']['decision_sha256'] == contract.content_id(decision)
            if not applied and current_id != decision['expected_current']:
                raise ValueError('current artwork changed after the adoption decision was drafted')
    return row, confirmed


def adopt(root: Path, character: str, iteration: str, approval: Any, *,
          registration_record: dict[str, Any] | None = None, pack_dir: Path | None = None,
          settings: Any = None, production_claim: str | None = None) -> dict[str, Any]:
    root = studio.require_studio(root).resolve()
    with studio.recording_lock(root):
        home = studio.character_dir(root, character)
        row, confirmed = preflight(root, character, iteration, approval,
            registration_record=registration_record, pack_dir=pack_dir, settings=settings,
            production_claim=production_claim, require_claim=True)
        studio.validate_recording_target(root, character, row["slot"], writable=True)
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
        if production_claim is not None: journal['production_claim'] = production_claim
        atomic_write_json(path, journal)
        try:
            if row["status"] != "accepted":
                row = studio._record_accept(root, character, iteration)
            journal.update(status="candidate-accepted", next_action="bind-sheet")
            atomic_write_json(path, journal)
            slot = _bind_sheet(root, home, row, confirmed, journal)
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
    validate_sidecar(sidecar, sheet_root=sheet, verify_files=False)
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
                readiness = adoption_readiness(root, character, row)
                pending.append({"iteration_id": row["iteration_id"], "next_action": journal["next_action"],
                                "adoption": readiness})
                errors.append(f"{row['slot']}: adoption incomplete; resume {row['iteration_id']}: {journal['next_action']}")
    bindings: list[dict[str, Any]] = []
    for slot, row in sorted(accepted.items()):
        origin = None
        try:
            safe_file(root, row["result"]["path"], row["result"]["sha256"])
            current = (sidecar["slots"].get(slot) or {}).get("current")
            if current:
                from sheet_artifacts import verify_acceptance, verify_artifact
                cache: dict = {}
                verify_acceptance(current, sheet, slot, cache=cache)
                origin = verify_artifact(current['artifact'], sheet, cache=cache).get('origin')
        except (ValueError, OSError, KeyError) as exc:
            errors.append(f"{slot}: accepted reference is unavailable: {exc}")
            bindings.append({"slot": slot, "iteration_id": row["iteration_id"], "status": "unavailable",
                             "image_sha256": row["result"]["sha256"], "image_path": None,
                             "influence": None, "registration": None, "next_action": "repair-reference"})
            continue
        path = _journal_path(home, row["iteration_id"])
        journal = studio.read_json(path) if path.is_file() else None
        readiness = adoption_readiness(root, character, row)
        bound = current_artifact(sidecar["slots"].get(slot))
        has_binding = bool(bound and bound.get("image"))
        expected_origin = {'kind': 'production' if row.get('production') else 'external-import',
                           'character': character, 'iteration_id': row['iteration_id'],
                           **(row.get('production') or {})}
        bound_here = (has_binding and bound["image"]["sha256"] == row["result"]["sha256"]
                      and origin == expected_origin)
        state = "sheet-bound" if bound_here else "candidate-accepted"
        if has_binding and not bound_here:
            errors.append(f"{slot}: latest accepted image is not bound to the sheet; resume adoption of {row['iteration_id']}")
        if journal and journal.get("next_action"):
            errors.append(f"{slot}: adoption incomplete; next action: {journal['next_action']}")
        if bound_here and not readiness['source_ready']:
            errors.extend(f"{slot}: adopted source is unavailable: {item['message']}"
                          for item in readiness['diagnostics'])
        registration_unavailable = False
        if journal and journal.get("registration") and bound_here:
            registration = journal["registration"]
            report = validate_pack(Path(registration["pack_path"]), require_lock=True)
            if not report.valid or report.pack_id != registration["pack_id"]:
                registration_unavailable = True
                errors.append(f"{slot}: registered pack changed or is missing")
            else:
                state = "catalog-registered"
        completion_diagnostic = None
        if bound_here and not (journal and journal.get('next_action')):
            try:
                from studio_reference import current_source
                current_source(root, character, slot)
            except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
                from production_diagnostics import from_exception
                completion_diagnostic = from_exception(exc, phase='adoption-integrity')
                readiness['diagnostics'].append(completion_diagnostic)
                errors.append(f"{slot}: {completion_diagnostic['message']}")
        if registration_unavailable:
            next_action = 'repair-reference'
        elif journal and journal.get('next_action'):
            next_action = journal['next_action'] if readiness['source_ready'] else readiness['next_action']
        elif completion_diagnostic is not None:
            next_action = ('record-adoption-result' if completion_diagnostic['code'] == 'ADOPTION_RESULT_MISSING'
                           else 'repair-reference')
        elif bound_here:
            next_action = None if readiness['source_ready'] else readiness['next_action']
        elif journal:
            next_action = 'repair-reference'
            errors.append(f"{slot}: the recorded adoption no longer has its sheet binding")
        else:
            next_action = readiness['next_action']
        bindings.append({"slot": slot, "iteration_id": row["iteration_id"], "status": state,
                         "image_sha256": row["result"]["sha256"],
                         "image_path": str((sheet / bound["image"]["path"]).resolve()) if bound_here else None,
                         "influence": journal["approval"]["influence"] if journal else None,
                         "registration": journal.get("registration") if journal else None,
                         "adoption": readiness, "next_action": next_action})
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
    visual_subjects = (package.get('visual_continuity') or {}).get('subjects') or {}
    subject_ids = {ident for ident, row in visual_subjects.items() if row.get('studio_character') == character}
    for item in selected:
        uses = item.get('subject_uses', [])
        if uses:
            scopes = {use['use'] for use in uses if not visual_subjects or use['subject_id'] in subject_ids}
        else:
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
    parser = _operation_context.ArgumentParser(description=__doc__.split("\n")[0])
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
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(_operation_context.run_cli(main))
