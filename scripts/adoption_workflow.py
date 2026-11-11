#!/usr/bin/env python3
"""Adopt an iteration through an explicitly approved scope, resumably.

python scripts/adoption_workflow.py --studio DIR --character ID status
python scripts/adoption_workflow.py --studio DIR --character ID draft --iteration ID --scope sheet --influence identity --out approval.json
python scripts/adoption_workflow.py --studio DIR --character ID adopt --iteration ID --approval FILE
python scripts/adoption_workflow.py --studio DIR --character ID references --out selections.json

See references/runtime/adoption-workflow.md. No image API is called here.
A Production candidate is adopted with production_workflow.py adopt, which
records the claim this module checks. A failure prints
{"ok": false, "diagnostics": [...]} with the exit status its codes select in
production_diagnostics.
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
import runtime_snapshot
from studio_activity import mutation
from character_sheet import resolve_sheet_relative, validate_sidecar, _validate_ready_package
from sheet_artifacts import current_artifact
from pack_manager import (atomic_write_json, generate_uuid7, validate_pack, write_lock,
                          add_pack_root, enable_pack, load_effective_state)
from prompt_plot import APPROVED_AT
from revision_contract import digest
from reference_contract import INTENDED_INFLUENCES

SCOPES = ("sheet", "catalog")
INFLUENCES = INTENDED_INFLUENCES
APPROVAL_FIELDS = ("scope", "influence", "character", "iteration_id", "slot", "image_sha256", "by", "at")
JOURNAL_STATES = ("pending", "candidate-accepted", "sheet-bound", "catalog-registered")
JOURNAL_STEPS = ("accept-candidate", "bind-sheet", "register-pack", "activate-pack")


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


def _preserve_record(home: Path, kind: str, value: dict) -> dict:
    """Publish one immutable approval or prior adoption journal by its content."""
    import execution_contract as contract
    relative = f'adoptions/{kind}/{contract.content_id(value)}.json'
    path = contract.local(home, relative, exists=False)
    raw = contract.encoded(value)
    try:
        contract.atomic(path, raw)
    except FileExistsError:
        if contract.read(path) != raw:
            raise ValueError('immutable adoption evidence changed: ' + relative) from None
    return {'path': path.relative_to(home.parent.parent).as_posix(), 'sha256': contract.digest(raw)}


def journal_withdrawal(read: studio.StudioRead, character: str, journal: dict) -> dict | None:
    """Resolve the authored ending of this journal's exact sheet adoption."""
    import sheet_artifacts as fills
    accepted = (journal.get('sheet_binding') or {}).get('current')
    if accepted is None:
        return None
    slot_id = journal['approval']['slot']
    slot = read.sheet(character)['slots'].get(slot_id)
    record = fills.withdrawn_acceptance(slot, accepted)
    if record is None:
        return None
    decision = fills.verify_withdrawal(record, read.home(character) / 'sheet', slot_id, accepted,
                                       cache=read.artifacts)
    return {'receipt': copy.deepcopy(record), 'decision': decision}


def journal_problem(value: Any) -> str | None:
    """What makes a decoded adoption journal unusable, or None when it is well-formed.

    These are the fields its readers rely on. Agreement with the iteration,
    sheet and run is checked by the reader that needs it.
    """
    if not isinstance(value, dict) or value.get("artifact_type") != "studio-adoption":
        return "is not a studio-adoption object"
    approval = value.get("approval")
    if not isinstance(approval, dict) or any(not isinstance(approval.get(key), str) for key in APPROVAL_FIELDS):
        return "has no complete approval"
    if value.get("status") not in JOURNAL_STATES or value.get("next_action") not in (None, *JOURNAL_STEPS):
        return "has no known status and next action"
    if any(value.get(key) is not None and not isinstance(value[key], str)
           for key in ("production_claim", "registration_target")):
        return "has an invalid production claim or registration target"
    registration = value.get("registration")
    if registration is not None and (not isinstance(registration, dict) or any(
            not isinstance(registration.get(key), str) for key in ("pack_path", "pack_id"))):
        return "has an invalid registration"
    decision = value.get("sheet_decision")
    if decision is not None and (not isinstance(decision, dict) or "expected_current" not in decision):
        return "has an invalid sheet decision"
    if "sheet_binding" in value and (not isinstance(value["sheet_binding"], dict) or "current" not in value["sheet_binding"]):
        return "has an invalid sheet binding"
    return None


def record_corrupt(character: str, iteration: str, problem: str, origin: dict[str, str] | None,
                   rows: list[dict[str, Any]] | None, *, required_action: str | None = None, **details: Any):
    """The ADOPTION_RECORD_CORRUPT diagnostic of an iteration's adoption journal.

    Its repair is the one restore_action gives, unless the caller that read a
    saved copy of the journal supplies the repair of that copy.
    """
    from production_diagnostics import ProductionError
    file = f"characters/{character}/adoptions/{iteration}.json"
    return ProductionError("ADOPTION_RECORD_CORRUPT", f"The adoption record {file} {problem}.",
                           phase="adoption-integrity", file=file, character=character, iteration=iteration,
                           required_action=required_action or restore_action(character, iteration, origin, rows),
                           **details)


def read_journal(read: studio.StudioRead, character: str, iteration: str) -> dict[str, Any]:
    """Decode one well-formed adoption journal of a Studio read.

    A missing, unreadable or malformed journal raises ADOPTION_RECORD_CORRUPT
    whose required action names the repair this owner supports.
    """
    path = _journal_path(read.home(character), iteration)
    try:
        value = studio.read_json(path)
    except FileNotFoundError:
        problem = "is missing"
    except ValueError as exc:
        problem = f"is not JSON ({exc})"
    else:
        problem = journal_problem(value)
        if problem is None:
            return value
    row = studio._find(read.raw_iterations(character), iteration)
    origin, rows = row.get("production"), None
    if origin is not None:
        try:
            rows = read.run(origin["run"]).rows
        except (ValueError, OSError, KeyError, TypeError):
            rows = None
    raise record_corrupt(character, iteration, problem, origin, rows)


def recorded_adoptions(rows: list[dict[str, Any]], character: str,
                       iteration: str) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """This iteration's adoption claims in its Production run, by digest, and their results in recorded order."""
    claims = {}
    for row in rows:
        if row["event"] == "adoption-claim":
            payload = row["data"]["intent"]["payload"]
            if payload["character"] == character and payload["iteration"] == iteration:
                claims[row["sha256"]] = row
    return claims, [row for row in rows if row["event"] == "adoption-result" and row["data"]["claim"] in claims]


def journal_disagreement(journal: dict[str, Any], rows: list[dict[str, Any]], character: str,
                         iteration: str) -> str | None:
    """What makes a well-formed Production adoption journal disagree with its run, or None when it agrees.

    The journal agrees when it is the latest adoption result the run records
    for the iteration, or when it names an adoption claim of the iteration
    whose result the run does not record yet: that adoption is still in
    progress, and its journal is its only record. These are the journals that
    restore_journal leaves as they are.
    """
    claims, results = recorded_adoptions(rows, character, iteration)
    claim = journal.get("production_claim")
    if claim not in claims:
        return "names no adoption claim of this iteration in its run"
    own = [row for row in results if row["data"]["claim"] == claim]
    if not own:
        return None
    if own[0]["data"]["result"] != {"ok": True, **journal}:
        return "differs from the result its run recorded for its claim"
    if results[-1] is not own[0]:
        return "holds the result of an earlier adoption of this iteration than the latest one its run records"
    return None


def require_journal_agreement(journal: dict[str, Any], character: str, iteration: str,
                              origin: dict[str, str], rows: list[dict[str, Any]]) -> None:
    """Refuse a Production adoption journal that disagrees with its run with ADOPTION_RECORD_CORRUPT."""
    problem = journal_disagreement(journal, rows, character, iteration)
    if problem is not None:
        raise record_corrupt(character, iteration, problem, origin, rows)


def _adopt_command(character: str, iteration: str, origin: dict[str, str], claim: dict[str, Any]) -> tuple[str, bool]:
    """The production_workflow.py adopt command of one recorded adoption claim, and whether it is a catalog adoption."""
    from cli_invocation import shown
    payload = claim["data"]["intent"]["payload"]
    arguments = ["production_workflow.py", "adopt", "--run", origin["run"], "--claim", claim['sha256']]
    return shown(arguments), payload["pack_dir"] is not None


def restore_action(character: str, iteration: str, origin: dict[str, str] | None,
                   rows: list[dict[str, Any]] | None) -> str:
    """The repair of an adoption journal that is missing, malformed or differs from its run's result.

    `rows` are the events of the iteration's Production run, or None when that run cannot be read.
    """
    if origin is None:
        return ("The current imported adoption has no recorded Production result that can restore this journal; "
                "restore the named file from a verified Studio copy. Earlier retained adoptions do not establish "
                "the current decision.")
    if rows is None:
        return (f"Once run {origin['run']} can be read, find the latest completed adoption claim of {iteration} "
                f"and use production_workflow.py adopt --run {origin['run']} --claim CLAIM. "
                "It writes this record again from the adoption result the run "
                "recorded and does not adopt the image again.")
    claims, results = recorded_adoptions(rows, character, iteration)
    if not results:
        return (f"The run {origin['run']} records no completed adoption of {iteration}, so no recorded result can "
                "restore this record and no command writes it again; restore the file from a copy of this Studio.")
    command, catalog = _adopt_command(character, iteration, origin, claims[results[-1]["data"]["claim"]])
    return ("Repeat the completed adoption with " + command + ". It writes this record again from the "
            "adoption result the run recorded and does not adopt the image again."
            + (" Supply the catalog adoption's pack runtime arguments." if catalog else ""))


def result_action(character: str, iteration: str, origin: dict[str, str], claim: dict[str, Any]) -> str:
    """The repair of an adoption under `claim` that stopped before its run recorded its result.

    The Studio may have completed that adoption or stopped within it; repeating
    its command continues the same claim in both cases.
    """
    command, catalog = _adopt_command(character, iteration, origin, claim)
    return ("Repeat that adoption with " + command + ". It finishes the adoption under that claim and records its "
            "result in the run; it starts no other adoption and adds no iteration."
            + (" Give the pack runtime arguments of that catalog adoption." if catalog else ""))


def validate_approval(value: Any, character: str, row: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("adoption requires an explicit approval object")
    required = {"scope", "influence", "character", "iteration_id", "slot", "image_sha256", "by", "at"}
    if required - set(value) or set(value) - required - {"note", "license", "registration_record_sha256", "continuity_decision", "source_state", "authority_sha256"}:
        raise ValueError("approval fields must be scope, influence, character, iteration_id, slot, image_sha256, by, at; optional note, license, registration_record_sha256, continuity_decision, source_state and authority_sha256")
    if value["scope"] not in SCOPES or value["influence"] not in INFLUENCES:
        raise ValueError("unknown adoption scope or influence")
    slot = studio.placement_slot(row)
    expected = {"character": character, "iteration_id": row["iteration_id"], "slot": slot,
                "image_sha256": row["result"]["sha256"]}
    for key, item in expected.items():
        if value.get(key) != item:
            raise ValueError(f"approval does not match {key}")
    if not isinstance(value["by"], str) or not value["by"].strip() or not isinstance(value["at"], str) or not APPROVED_AT.fullmatch(value["at"]):
        raise ValueError("approval requires who approved and the actual UTC approval timestamp")
    if "license" in value and (not isinstance(value["license"], str) or not value["license"].strip()):
        raise ValueError("license must be a nonempty explicit license identifier")
    if value["influence"] != "identity" and slot.startswith(("base.", "canon.")):
        raise ValueError("base/canon identity slots cannot be replaced by outfit or scene references")
    if 'source_state' in value:
        import execution_contract as contract
        contract.exact(value['source_state'], {'placement', 'slot_acceptance', 'adoption'}, 'adoption source state')
        contract.sha(value['source_state']['placement'])
        receipt = value['source_state']['slot_acceptance']
        if receipt is not None:
            contract.exact(receipt, {'iteration_id', 'image_sha256', 'acceptance_sha256'}, 'adoption slot receipt')
            contract.text(receipt['iteration_id'], 'accepted iteration')
            contract.sha(receipt['image_sha256'])
            contract.sha(receipt['acceptance_sha256'])
        if value['source_state']['adoption'] is not None:
            contract.sha(value['source_state']['adoption'])
    if 'authority_sha256' in value:
        import execution_contract as contract
        contract.sha(value['authority_sha256'])
    return copy.deepcopy(value)


def _check_source_state(root: Path, character: str, row: dict, approval: dict, read: studio.StudioRead,
                        journal: dict | None, production_claim: str | None) -> None:
    """Bind a new authored destination; a pending owner may retain its own effects."""
    expected = approval.get('source_state')
    if expected is None:
        return
    import execution_contract as contract
    from production_diagnostics import ProductionError
    slot = studio.placement_slot(row)
    accepted = studio.acceptance_state(root, character, slot, read=read)
    current = (read.sheet(character)['slots'].get(slot) or {}).get('current')
    actual = {'placement': row['placement']['sha256'], 'slot_acceptance': accepted,
              'adoption': None if current is None else contract.content_id(current)}
    own = (journal is not None and journal['approval'] == approval
           and production_claim is not None and journal.get('production_claim') == production_claim)
    same_slot = actual['slot_acceptance'] == expected['slot_acceptance'] or (
        own and accepted is not None and accepted['iteration_id'] == row['iteration_id'])
    same_adoption = actual['adoption'] == expected['adoption'] or (
        own and current is not None and journal.get('sheet_decision') is not None
        and current['approval']['decision_sha256'] == contract.content_id(journal['sheet_decision']))
    if actual['placement'] != expected['placement'] or not same_slot or not same_adoption:
        raise ProductionError('ADOPTION_DECISION_CHANGED',
            'The adoption destination changed after the author decision.', phase='adoption',
            expected=expected, actual=actual,
            required_action='Inspect the current Studio destination and use draft-adoption for a new decision. '
                            'A saved adoption never replaces a later placement or canonical choice.')


def validate_registration_record(record: Any) -> dict[str, Any]:
    """Validate the selected canonical module before binding its exact content."""
    if not isinstance(record, dict):
        raise ValueError('registration record must be a canonical module object')
    from pack_manager import _schema_issues, PACK_RECORD_SCHEMA_PATH
    issues = _schema_issues({'kind': 'module', 'category': record.get('category'),
                             'records': [record]}, PACK_RECORD_SCHEMA_PATH, Path('registration-record.json'))
    if issues:
        raise ValueError('registration record is not a valid canonical module: ' + '; '.join(i.message for i in issues))
    return record


@runtime_snapshot.operation
def draft_approval(root: Path, character: str, iteration: str, *, scope: str, influence: str,
                   registration_record: dict[str, Any] | None = None) -> dict[str, Any]:
    """Bind the requested adoption subject without asserting a decision or approver."""
    if scope not in SCOPES or influence not in INFLUENCES:
        raise ValueError('unknown adoption scope or influence')
    root = studio.require_studio(root).resolve()
    read = studio.StudioRead(root)
    row = studio._find(read.iterations(character), iteration)
    require_adoption_source(root, character, row, read=read)
    slot = studio.placement_slot(row)
    if influence != 'identity' and slot.startswith(('base.', 'canon.')):
        raise ValueError('base/canon identity slots cannot be replaced by outfit or scene references')
    result = {'scope': scope, 'influence': influence, 'character': character,
              'iteration_id': row['iteration_id'], 'slot': slot,
              'image_sha256': row['result']['sha256'], 'by': None, 'at': None}
    if scope == 'catalog':
        result['registration_record_sha256'] = digest(validate_registration_record(registration_record))
    elif registration_record is not None:
        raise ValueError('registration arguments require catalog scope')
    return result


def _bind_sheet(root: Path, home: Path, row: dict[str, Any], approval: dict, journal: dict, *,
                read: studio.StudioRead | None = None) -> dict[str, Any]:
    import sheet_artifacts as fills
    sheet = home / 'sheet'
    sidecar_path = sheet / 'sheet-data.json'
    artifact = fills.from_iteration(root, row['character'], row, read=read)
    slot_id = studio.placement_slot(row)
    # The adoption journal pins expected_current before its first bind. Retrying
    # does not replace a different selection made after that author decision.
    decision = journal.get('sheet_decision')
    if decision is None:
        decision = fills.draft_adoption(sidecar_path, slot_id, artifact['artifact_id'])
        evidence = _preserve_record(home, 'approvals', approval)
        decision.update(by=approval['by'], at=approval['at'],
            reason=approval.get('note') or 'Explicit author approval for the named Studio iteration.',
            evidence={**evidence, 'locator': 'whole approval'})
        if row.get('production'):
            decision['basis'] = {'kind': 'production', 'claim': journal['production_claim'], 'approval': approval}
        journal['sheet_decision'] = decision
        atomic_write_json(_journal_path(home, row['iteration_id']), journal)
    fills.adopt(sidecar_path, decision, evidence_root=root,
                loaded=read.run(row['production']['run']) if read and row.get('production') else None)
    return studio.read_json(sidecar_path)['slots'][slot_id]


def _registration(root: Path, row: dict[str, Any], journal: dict[str, Any], record: dict[str, Any], target: Path) -> dict[str, Any]:
    """Create the adoption's pack at `target`, or keep the one this adoption created there.

    An existing target belongs to this adoption when it is a valid locked pack
    whose adoption receipt names this Studio, the journal's approval and the
    pack's own ID. The journal then takes that ID, also after the journal was
    written again without the ID it generated before the pack was created.
    """
    from pack_manager import initial_pack_release
    from prepare_generation_references import detect_image_media_type, image_dimensions
    target = target.absolute()
    if target.is_symlink() or any(parent.is_symlink() for parent in target.parents):
        raise ValueError("registration target must not traverse symbolic links")
    target = target.resolve()
    if target.exists():
        report = validate_pack(target, require_lock=True)
        receipt = studio.read_json(target / "resources" / "adoption-receipt.json")
        if (not report.valid or receipt.get("approval") != journal["approval"] or receipt.get("pack_id") != report.pack_id
                or receipt.get("studio_id") != studio.manifest(root)["studio_id"]):
            raise ValueError("registration target belongs to another adoption or its content changed; it will not be overwritten")
        journal["registration_pack_id"] = report.pack_id
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
                             claim: str | None, *, require_current: bool = False,
                             read: studio.StudioRead | None = None) -> None:
    """Refuse adopting a Production candidate outside the claim its own adopt operation recorded.

    `production_workflow.py adopt` records that claim under an adopt
    authorization; it names the candidate, character, iteration and approval.
    """
    origin = row["production"]
    if claim is None:
        raise ValueError(f"{row['iteration_id']} is a Production candidate; adopt it with production_workflow.py adopt "
                         f"under its own adopt authorization")
    import production_workflow as workflow
    _, prepared, _, rows = read.run(origin['run']) if read else workflow.read_run(root, origin['run'])
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
        from execution_lifecycle import current_adoption_authorization
        token, reassessed = current_adoption_authorization(rows, recorded)
        current = workflow._permission(root, prepared, rows, token, **recorded['data']['intent'])
        from production_adoption import require_approval_authority
        require_approval_authority(root, prepared, approval, current, reassessed=reassessed, claim=claim)
        if not any(event['event'] == 'operation-start'
                   and event['data'].get('claim') == claim
                   and event['data'].get('effect') == 'local-action' for event in rows):
            raise ValueError('the Production adoption claim has no recorded local operation boundary')


def require_adoption_source(root: Path, character: str, row: dict[str, Any], *,
                            read: studio.StudioRead | None = None) -> None:
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
    studio.validate_recording_target(root, character, studio.placement_slot(row), read=read)
    origin = row.get('production')
    if origin is not None:
        import production_workflow as workflow
        _, prepared, _, rows = read.run(origin['run']) if read else workflow.read_run(root, origin['run'])
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
    if read is None:
        package_path = safe_file(root, row['package']['path'], row['package']['sha256'])
        package = studio.read_json(package_path)
    else:
        _, package = read._package(row['package'])
    _validate_ready_package(package, field='adoption source')
    studio.validate_package_attachment(root, row, read=read)


def adoption_readiness(root: Path, character: str, row: dict[str, Any], *,
                       read: studio.StudioRead | None = None) -> dict[str, Any]:
    """Expose the same mechanical prerequisites as preflight, without a decision."""
    from production_diagnostics import from_exception
    origin = row.get('production')
    result = {'owner': 'production' if origin else 'studio', 'source_ready': False,
              'production': origin, 'diagnostics': [], 'next_action': None}
    try:
        require_adoption_source(root, character, row, read=read)
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


@runtime_snapshot.operation
def preflight(root: Path, character: str, iteration: str, approval: Any, *,
              expected_production: dict[str, str] | None = None, expected_image: str | None = None,
              registration_record: dict[str, Any] | None = None, pack_dir: Path | None = None,
              settings: Any = None, production_claim: str | None = None,
              require_claim: bool = False, read: studio.StudioRead | None = None) -> tuple[dict, dict]:
    """Read canonical eligibility before an authorization, claim or Studio mutation.

    Production supplies its exact origin at intent time. The mutating owner
    additionally requires its recorded claim and catalog runtime. Imported rows
    keep their own ordinary adoption path even when their image bytes match a
    Production candidate. Once the run of a Production iteration records an
    adoption result for it, a later adoption continues from its journal, so
    that journal must exist and agree with the run.
    """
    from production_diagnostics import ProductionError
    root = studio.require_studio(root).resolve()
    read = read or studio.StudioRead(root)
    home = read.home(character)
    row = read.iteration(character, iteration)
    origin = row.get('production')
    if expected_production is not None and origin != expected_production:
        action = ('Use studio.py accept for slot acceptance or adoption_workflow.py adopt for sheet/catalog adoption.'
                  if origin is None else 'Use the Production run and candidate recorded by this exact iteration.')
        raise ProductionError('ADOPTION_OWNER_MISMATCH',
            'Canonical Production adoption requires this iteration to belong to the exact run and candidate.',
            phase='adoption', expected=expected_production, actual=origin, required_action=action)
    require_adoption_source(root, character, row, read=read)
    if expected_image is not None and row['result']['sha256'] != expected_image:
        raise ValueError('adoption targets a different candidate')
    if origin is not None:
        if require_claim:
            require_production_claim(root, character, row, approval, production_claim, require_current=True, read=read)
    elif production_claim is not None:
        raise ValueError(f'{iteration} is an external import; a Production adoption claim does not apply')
    confirmed = validate_approval(approval, character, row)
    if confirmed['influence'] == 'identity':
        from visual_continuity import adoption_subject
        adoption_subject(root, character, row, confirmed, read=read)
    if confirmed['scope'] == 'catalog':
        if not isinstance(registration_record, dict) or pack_dir is None or (require_claim and settings is None):
            raise ValueError('catalog adoption requires --registration-record, --pack-dir and a resolved pack runtime')
        validate_registration_record(registration_record)
        if confirmed.get('registration_record_sha256') != digest(registration_record):
            raise ValueError('catalog approval must bind registration_record_sha256')
    elif registration_record is not None or pack_dir is not None:
        raise ValueError('registration arguments require catalog scope')
    path = _journal_path(home, iteration)
    rows = read.run(origin['run']).rows if origin is not None else None
    journal = None
    if path.exists() or (rows is not None and recorded_adoptions(rows, character, iteration)[1]):
        journal = read.journal(character, iteration)
        if origin is not None:
            require_journal_agreement(journal, character, iteration, origin, rows)
        prior = journal['approval']
        withdrawal = journal_withdrawal(read, character, journal)
        if withdrawal is not None:
            if prior == confirmed:
                action = (f'Use production_workflow.py draft-adoption --run {origin["run"]} '
                          f'--candidate {origin["candidate"]} --scope {confirmed["scope"]} '
                          f'--influence {confirmed["influence"]} --out NEW-DECISION.json, record the actual '
                          'new decision and apply it with adopt --file NEW-DECISION.json.' if origin else
                          'Draft a new approval with adoption_workflow.py --studio STUDIO --character '
                          + character + ' draft --iteration ' + iteration
                          + ' --scope ' + confirmed['scope'] + ' --influence ' + confirmed['influence']
                          + ' --out APPROVAL.json, record the actual new approval, and adopt under its own authority.')
                raise ProductionError('INPUT_CONSISTENCY_ERROR',
                    'This exact canonical adoption was withdrawn; an earlier approval cannot restore it.',
                    phase='adoption', character=character, iteration=iteration,
                    required_action=action)
            _check_source_state(root, character, row, confirmed, read, journal, production_claim)
            return row, confirmed
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
            slot = read.sheet(character)['slots'][studio.placement_slot(row)]
            current = slot['current']
            current_id = current['artifact']['artifact_id'] if current else None
            applied = current is not None and current['approval']['decision_sha256'] == contract.content_id(decision)
            if not applied and current_id != decision['expected_current']:
                raise ValueError('current artwork changed after the adoption decision was drafted')
    _check_source_state(root, character, row, confirmed, read, journal, production_claim)
    return row, confirmed


@mutation
def adopt(root: Path, character: str, iteration: str, approval: Any, *,
          registration_record: dict[str, Any] | None = None, pack_dir: Path | None = None,
          settings: Any = None, production_claim: str | None = None) -> dict[str, Any]:
    root = studio.require_studio(root).resolve()
    home = studio.character_dir(root, character)
    import execution_contract as contract
    with studio.recording_lock(root, character=character), contract.lock(home / 'sheet'):
        raw = studio._find(studio.read_iteration_records(home), iteration)
        origin = raw.get('production')
        from contextlib import nullcontext
        import production_store as store
        # The durable claim is already recorded by Production. The filesystem
        # owner starts its local effect only after obtaining its character RMW
        # scope, with current permission and selection checked in one DB view.
        with store.transaction(root) if origin is not None else nullcontext():
            if origin is not None:
                import execution_lifecycle as lifecycle
                import production_workflow as workflow
                require_production_claim(root, character, raw, approval, production_claim)
                _, _, _, records = workflow.read_run(root, origin['run'])
                claim = workflow.find(records, 'adoption-claim', production_claim)
                token, _ = lifecycle.current_adoption_authorization(records, claim)
                if not any(record['event'] == 'operation-start'
                           and record['data'].get('claim') == production_claim
                           and record['data'].get('effect') == 'local-action' for record in records):
                    lifecycle.begin(root, origin['run'], token, effect='local-action', claim=production_claim)
            # Starting changes the run revision. Carry the newly loaded values
            # through every subsequent owner check; rollback start on failure.
            read = studio.StudioRead(root)
            row, confirmed = preflight(root, character, iteration, approval,
                registration_record=registration_record, pack_dir=pack_dir, settings=settings,
                production_claim=production_claim, require_claim=True, read=read)
            studio.validate_recording_target(root, character, studio.placement_slot(row), writable=True, read=read)
        path = _journal_path(home, iteration)
        journal = studio.read_json(path) if path.exists() else {
            "artifact_type": "studio-adoption", "approval": confirmed, "status": "pending",
            "next_action": "accept-candidate", "registration": None,
        }
        _preserve_record(home, 'approvals', confirmed)
        if journal['approval'] != confirmed and journal_withdrawal(read, character, journal) is not None:
            previous = _preserve_record(home, 'history', journal)
            journal = {'artifact_type': 'studio-adoption', 'approval': confirmed, 'status': 'pending',
                       'next_action': 'accept-candidate', 'registration': None, 'previous_adoption': previous}
        # Promotion from sheet to catalog requires a new explicit catalog approval.
        if journal["approval"] != confirmed:
            if journal["approval"]["scope"] == "sheet" and confirmed["scope"] == "catalog" and all(
                journal["approval"][k] == confirmed[k] for k in ("character", "iteration_id", "slot", "image_sha256", "influence")):
                journal['previous_adoption'] = _preserve_record(home, 'history', journal)
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
                row = studio._record_accept(root, character, iteration, read=read)
            journal.update(status="candidate-accepted", next_action="bind-sheet")
            atomic_write_json(path, journal)
            slot = _bind_sheet(root, home, row, confirmed, journal, read=read)
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
            import studio_activity as activity
            activity.changed(path, 'studio-adopted', subject=character + '/' + iteration,
                             revision=digest(journal), details={'status': journal['status'],
                                                               'scope': confirmed['scope']})
        except (OSError, ValueError, RuntimeError) as exc:
            journal["last_error"] = str(exc)
            try:
                atomic_write_json(path, journal)
            except OSError:
                pass
            raise
        return {"ok": True, **journal}


@mutation
def restore_journal(root: Path, character: str, iteration: str, *, production_claim: str) -> str | None:
    """Write a Production adoption journal again from the result its run recorded for this claim.

    Only the latest adoption result the run records for the iteration writes
    the journal. A journal that agrees with the run stays as it is: one equal
    to that result, and a well-formed journal of another claim of the
    iteration whose result is not recorded, which that operation wrote after
    this result (journal_disagreement). Nothing else in the Studio changes.
    Returns the Studio-relative path of a journal written again, otherwise None.
    """
    import production_store as store
    import production_workflow as workflow
    root = studio.require_studio(root).resolve()
    with studio.recording_lock(root, character=character):
        home = studio.character_dir(root, character)
        origin = studio._find(studio.read_iteration_records(home), iteration).get("production")
        if origin is None:
            raise ValueError(f"{iteration} is an external import; no Production result holds its adoption journal")
        with store.transaction(root):
            rows = workflow.read_run(root, origin["run"]).rows
        claims, results = recorded_adoptions(rows, character, iteration)
        own = [row for row in results if row["data"]["claim"] == production_claim]
        if (len(own) != 1 or own[0]["data"]["result"].get("production_claim") != production_claim
                or claims[production_claim]["data"]["intent"]["payload"]["candidate"] != origin["candidate"]):
            raise ValueError("the run records no result of this adoption claim for this candidate and iteration")
        if results[-1] is not own[0]:
            return None
        recorded = {key: value for key, value in own[0]["data"]["result"].items() if key != "ok"}
        path = _journal_path(home, iteration)
        try:
            current = studio.read_json(path)
        except (FileNotFoundError, ValueError):
            current = None
        if journal_problem(current) is None and journal_disagreement(current, rows, character, iteration) is None:
            return None
        atomic_write_json(path, recorded)
        import studio_activity as activity
        activity.changed(path, "studio-adoption-restored", subject=character + "/" + iteration,
                         details={"claim": production_claim, "status": recorded["status"]})
        return path.relative_to(root).as_posix()


@runtime_snapshot.operation
def reference_index(root: Path, character: str, *, read: studio.StudioRead | None = None) -> dict[str, Any]:
    """Export the current character index from its owning Studio read phase."""
    from owned_json import mutable
    from studio_reference import reference_reads
    read = read or reference_reads().studio(root)
    read.require_root(root)
    return mutable(read.reference_index(character))


def _recorded_journal(read: studio.StudioRead, character: str, row: dict[str, Any]) -> dict[str, Any]:
    """The adoption journal of a current or pending iteration, refused when it disagrees with its run.

    A run that cannot be read leaves the journal unchecked here; the
    iteration's adoption readiness reports that run.
    """
    journal = read.journal(character, row["iteration_id"])
    origin = row.get("production")
    if origin is not None:
        try:
            rows = read.run(origin["run"]).rows
        except (ValueError, OSError, KeyError, TypeError):
            return journal
        require_journal_agreement(journal, character, row["iteration_id"], origin, rows)
    return journal


def _reference_index(root: Path, character: str, *, read: studio.StudioRead) -> dict[str, Any]:
    """Derive current references from the supplied Studio inputs exactly once.

    A damaged adoption journal is reported for its own slot: an accepted
    iteration's binding carries its diagnostic, and the error of any other
    iteration names its repair. The journal of an accepted or pending
    Production iteration is also checked against its run; a superseded or
    rejected iteration's journal is history, decoded without reading its run.
    """
    from production_diagnostics import ProductionError, from_exception
    home = read.home(character)
    sheet = home / "sheet"
    sidecar = read.sheet(character)
    rows = read.adoption_rows(character)
    accepted = {studio.placement_slot(row): row for row in rows if row.get("status") == "accepted"}
    errors: list[str] = []
    pending: list[dict[str, Any]] = []
    accepted_ids = {row["iteration_id"] for row in accepted.values()}
    for row in rows:
        path = _journal_path(home, row["iteration_id"])
        if row["iteration_id"] not in accepted_ids and path.is_file():
            history = row.get("status") in {"rejected", "superseded"}
            try:
                journal = (read.journal(character, row['iteration_id']) if history
                           else _recorded_journal(read, character, row))
            except ProductionError as exc:
                damaged = from_exception(exc, phase='adoption-integrity')
                errors.append(f"{row['slot']}: {damaged['message']} {damaged['required_action']}")
                continue
            if journal.get("next_action") and not history:
                readiness = adoption_readiness(root, character, row, read=read)
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
                cache = read.artifacts
                verify_acceptance(current, sheet, slot, cache=cache)
                origin = verify_artifact(current['artifact'], sheet, cache=cache).get('origin')
        except (ValueError, OSError, KeyError) as exc:
            errors.append(f"{slot}: accepted reference is unavailable: {exc}")
            bindings.append({"slot": slot, "iteration_id": row["iteration_id"], "status": "unavailable",
                             "image_sha256": row["result"]["sha256"], "image_path": None,
                             "influence": None, "registration": None, "next_action": "repair-reference"})
            continue
        path = _journal_path(home, row["iteration_id"])
        journal = damaged = None
        if path.is_file():
            try:
                journal = _recorded_journal(read, character, row)
            except ProductionError as exc:
                damaged = from_exception(exc, phase='adoption-integrity')
        readiness = adoption_readiness(root, character, row, read=read)
        withdrawal = None
        if journal is not None:
            try:
                withdrawal = journal_withdrawal(read, character, journal)
            except (ValueError, OSError, KeyError, TypeError) as exc:
                damaged = from_exception(exc, phase='adoption-integrity')
        bound = current_artifact(sidecar["slots"].get(slot))
        has_binding = bool(bound and bound.get("image"))
        expected_origin = {'kind': 'production' if row.get('production') else 'external-import',
                           'character': character, 'iteration_id': row['iteration_id'],
                           **(row.get('production') or {})}
        bound_here = (has_binding and bound["image"]["sha256"] == row["result"]["sha256"]
                      and origin == expected_origin)
        state = "sheet-bound" if bound_here else ("withdrawn" if withdrawal is not None else "candidate-accepted")
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
        completion_diagnostic = damaged
        if damaged is not None:
            readiness['diagnostics'].append(damaged)
            errors.append(f"{slot}: {damaged['message']}")
        elif bound_here and not (journal and journal.get('next_action')):
            try:
                from studio_reference import current_source
                current_source(root, character, slot, read=read)
            except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
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
        elif journal and withdrawal is None:
            next_action = 'repair-reference'
            errors.append(f"{slot}: the recorded adoption no longer has its sheet binding")
        else:
            next_action = readiness['next_action']
        bindings.append({"slot": slot, "iteration_id": row["iteration_id"], "status": state,
                         "image_sha256": row["result"]["sha256"],
                         "image_path": str((sheet / bound["image"]["path"]).resolve()) if bound_here else None,
                         "influence": journal["approval"]["influence"] if journal else None,
                         "registration": journal.get("registration") if journal else None,
                         "adoption": readiness, "next_action": next_action,
                         "withdrawal": withdrawal})
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


@runtime_snapshot.operation
def validate_for_generation(root: Path, character: str, package: dict[str, Any]) -> None:
    from studio_reference import reference_reads
    read = reference_reads().studio(root)
    index = read.reference_index(character)
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
    for row in read.iterations(character):
        if row.get("status") != "superseded":
            continue
        journal_path = _journal_path(home, row["iteration_id"])
        # A superseded candidate without adoption has no granted reference scope.
        journal = read.journal(character, row['iteration_id']) if journal_path.is_file() else None
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
    sub.add_parser("status", help='report candidate-accepted, sheet-bound, catalog-registered, withdrawn or unavailable canonical scope',
                   description='A withdrawn canonical scope retains Studio acceptance and its historical approval. A new adoption requires a new approval.')
    draft_parser = sub.add_parser('draft', help='bind the selected adoption subject for an actual approval')
    draft_parser.add_argument('--iteration', required=True)
    draft_parser.add_argument('--scope', required=True, choices=SCOPES)
    draft_parser.add_argument('--influence', required=True, choices=INFLUENCES)
    draft_parser.add_argument('--registration-record', type=Path)
    draft_parser.add_argument('--out', required=True, type=Path)
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
        if args.command == 'draft':
            from execution_contract import encoded
            from production_binding import write_new
            approval = draft_approval(root, args.character, args.iteration, scope=args.scope,
                influence=args.influence,
                registration_record=studio.read_json(args.registration_record) if args.registration_record else None)
            write_new(args.out, encoded(approval), option='--out', value=str(args.out))
            result = {'ok': True, 'output': str(args.out), 'approval': approval,
                      'unresolved': ['Record the actual approver and approval time for this exact subject.']}
        elif args.command == "adopt":
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
        from production_binding import report_failure
        return report_failure(exc, phase='adoption')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(_operation_context.run_cli(main))
