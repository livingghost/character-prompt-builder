#!/usr/bin/env python3
"""Build a sealed Candidate Manifest from generated files and human inspection notes.

This utility measures files and preserves the inspector's declarations. It does
not infer visual support from pixels and therefore does not replace human
selection of canonical reference images.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path
from typing import Any, Sequence

from state_protocol import finalize_artifact, load_json, validate_artifact, write_json


def require_non_empty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def require_string_array(value: Any, field: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be an array")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item:
            raise ValueError(f"{field}[{index}] must be a non-empty string")
        result.append(item)
    if len(result) != len(set(result)):
        raise ValueError(f"{field} must contain unique values")
    return result


def sha256_file(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()


def image_dimensions(path: Path) -> tuple[int,int]:
    data=path.read_bytes()
    if data[:8]==b'\x89PNG\r\n\x1a\n' and len(data)>=24:
        return struct.unpack('>II',data[16:24])
    if data[:2]==b'\xff\xd8':
        i=2
        while i < len(data)-9:
            if data[i] != 0xFF: i+=1; continue
            marker=data[i+1]
            if marker in (0xC0,0xC1,0xC2,0xC3,0xC5,0xC6,0xC7,0xC9,0xCA,0xCB,0xCD,0xCE,0xCF):
                height,width=struct.unpack('>HH',data[i+5:i+9]); return width,height
            if marker in (0xD8,0x01) or 0xD0<=marker<=0xD7:
                i+=2; continue
            if i+4>len(data): break
            i += 2 + struct.unpack('>H',data[i+2:i+4])[0]
    try:
        from PIL import Image
        with Image.open(path) as im: return int(im.width),int(im.height)
    except Exception as exc:
        raise ValueError(f'unsupported or unreadable image file: {path}') from exc


def validate_candidate_manifest_lineage(
    *,
    plan: dict[str, Any],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    """Validate the plan-to-candidate edges that JSON Schema cannot resolve."""

    errors: list[str] = []
    for label, artifact, expected_type in (
        ("bundle plan", plan, "reference-bundle-plan"),
        ("candidate manifest", manifest, "candidate-manifest"),
    ):
        report = validate_artifact(artifact)
        if artifact.get("artifact_type") != expected_type:
            errors.append(f"{label} has the wrong artifact_type")
        if not report.get("ok"):
            errors.extend(f"{label}: {item}" for item in report.get("errors", []))

    for field in ("character_id", "identity_contract_sha256"):
        if plan.get(field) != manifest.get(field):
            errors.append(f"candidate manifest {field} differs from the bundle plan")
    if plan.get("bundle_plan_sha256") != manifest.get("bundle_plan_sha256"):
        errors.append("candidate manifest bundle_plan_sha256 does not identify the bundle plan")

    planned_assets = {
        str(row.get("asset_id"))
        for row in plan.get("assets", [])
        if isinstance(row, dict)
    }
    candidate_ids: list[str] = []
    for index, row in enumerate(manifest.get("candidates", [])):
        if not isinstance(row, dict):
            continue
        candidate_ids.append(str(row.get("candidate_id")))
        if str(row.get("asset_id")) not in planned_assets:
            errors.append(f"candidates[{index}] references an asset outside the bundle plan")
    if len(candidate_ids) != len(set(candidate_ids)):
        errors.append("candidate manifest candidate IDs must be unique")

    return {"ok": not errors, "errors": errors}


def validate_adoption_receipt(
    *,
    manifest: dict[str, Any],
    receipt: dict[str, Any],
) -> dict[str, Any]:
    """Validate an adoption receipt against its immutable manifest."""

    errors: list[str] = []
    for label, artifact, expected_type in (
        ("candidate manifest", manifest, "candidate-manifest"),
        ("adoption receipt", receipt, "adoption-receipt"),
    ):
        report = validate_artifact(artifact)
        if artifact.get("artifact_type") != expected_type:
            errors.append(f"{label} has the wrong artifact_type")
        if not report.get("ok"):
            errors.extend(f"{label}: {item}" for item in report.get("errors", []))

    if receipt.get("candidate_manifest_sha256") != manifest.get("candidate_manifest_sha256"):
        errors.append("adoption receipt does not identify the candidate manifest")
    if receipt.get("character_id") != manifest.get("character_id"):
        errors.append("adoption receipt character_id differs from the candidate manifest")

    candidates = {
        str(row.get("candidate_id")): row
        for row in manifest.get("candidates", [])
        if isinstance(row, dict)
    }
    adopted_candidate_ids: list[str] = []
    for index, adoption in enumerate(receipt.get("adoptions", [])):
        if not isinstance(adoption, dict):
            continue
        candidate_id = str(adoption.get("candidate_id"))
        adopted_candidate_ids.append(candidate_id)
        candidate = candidates.get(candidate_id)
        if candidate is None:
            errors.append(f"adoptions[{index}] references an unknown candidate_id")
        elif adoption.get("status") == "adopted" and candidate.get("recommendation") != "adopt":
            errors.append(f"adoptions[{index}] adopts a candidate not recommended for adoption")
    if len(adopted_candidate_ids) != len(set(adopted_candidate_ids)):
        errors.append("adoption receipt candidate IDs must be unique")

    return {"ok": not errors, "errors": errors}


def build_manifest(*,plan:dict[str,Any],inspection:dict[str,Any],base_dir:Path)->dict[str,Any]:
    report=validate_artifact(plan)
    if not report.get('ok') or plan.get('artifact_type')!='reference-bundle-plan':
        raise ValueError('invalid reference bundle plan')
    rows=inspection.get('candidates')
    if not isinstance(rows,list) or not rows: raise ValueError('inspection.candidates must be a non-empty array')
    planned={x['asset_id'] for x in plan.get('assets',[]) if isinstance(x,dict)}
    candidates=[]
    for i,row in enumerate(rows):
        if not isinstance(row,dict): raise ValueError(f'candidate {i} must be an object')
        asset_id=require_non_empty_string(row.get('asset_id'), f'candidates[{i}].asset_id')
        if asset_id not in planned: raise ValueError(f'candidate references unplanned asset_id: {asset_id}')
        rel=require_non_empty_string(row.get('file'), f'candidates[{i}].file')
        path=(base_dir/rel).resolve() if not Path(rel).is_absolute() else Path(rel).resolve()
        if not path.is_file(): raise ValueError(f'candidate file does not exist: {path}')
        width,height=image_dimensions(path)
        candidate_id = row.get('candidate_id', f'{asset_id}-candidate')
        recommendation = row.get('recommendation', 'needs-review')
        candidates.append({
            'candidate_id':require_non_empty_string(candidate_id, f'candidates[{i}].candidate_id'),
            'asset_id':asset_id,
            'file':rel,
            'file_sha256':sha256_file(path),
            'dimensions':{'width':width,'height':height},
            'visible_support':require_string_array(row.get('visible_support',[]), f'candidates[{i}].visible_support'),
            'unsupported_or_occluded':require_string_array(row.get('unsupported_or_occluded',[]), f'candidates[{i}].unsupported_or_occluded'),
            'contradictions':require_string_array(row.get('contradictions',[]), f'candidates[{i}].contradictions'),
            'recommendation':require_non_empty_string(recommendation, f'candidates[{i}].recommendation'),
        })
    manifest_id = inspection.get('manifest_id', f"CM-{plan['bundle_id']}")
    inspection_status = inspection.get('inspection_status', 'inspected')
    result=finalize_artifact({
        'artifact_type':'candidate-manifest',
        'manifest_id':require_non_empty_string(manifest_id, 'inspection.manifest_id'),
        'bundle_plan_sha256':plan['bundle_plan_sha256'],
        'character_id':plan['character_id'],
        'identity_contract_sha256':plan['identity_contract_sha256'],
        'candidates':candidates,
        'inspection_status':require_non_empty_string(inspection_status, 'inspection.inspection_status'),
        'candidate_manifest_sha256':'0'*64,
    })
    validation=validate_artifact(result)
    if not validation.get('ok'): raise ValueError('invalid candidate manifest: '+'; '.join(validation.get('errors',[])))
    lineage_validation = validate_candidate_manifest_lineage(plan=plan, manifest=result)
    if not lineage_validation.get('ok'):
        raise ValueError('invalid candidate manifest lineage: '+'; '.join(lineage_validation.get('errors',[])))
    return result


def main(argv: Sequence[str] | None=None)->int:
    p=argparse.ArgumentParser(description='Build a Candidate Manifest from human inspection notes.')
    p.add_argument('--bundle-plan',required=True); p.add_argument('--inspection',required=True); p.add_argument('--base-dir',default='.'); p.add_argument('--out',required=True)
    a=p.parse_args(argv)
    try:
        value=build_manifest(plan=load_json(Path(a.bundle_plan)),inspection=load_json(Path(a.inspection)),base_dir=Path(a.base_dir))
        write_json(Path(a.out),value); print(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)); return 0
    except (ValueError,OSError,json.JSONDecodeError) as exc:
        print(json.dumps({'ok':False,'errors':[str(exc)]},ensure_ascii=False,indent=2,allow_nan=False)); return 1
if __name__=='__main__': raise SystemExit(main())
