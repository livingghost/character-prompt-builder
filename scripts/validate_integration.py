#!/usr/bin/env python3
"""Validate the installed declaration or explicitly supplied protocol data."""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import tempfile
from pathlib import Path
from integration_contract import finalize, load_capabilities, validate_capabilities, validate_envelope, read_json, payload_identity

ROOT = Path(__file__).resolve().parents[1]


def self_test(capabilities: dict) -> dict:
    """Exercise profile directions using synthetic protocol data, not software."""
    errors = []
    count = 0
    for emitted in capabilities.get("interfaces", {}).get("produces", []):
        kind = emitted["artifact_types"][0]
        source = ROOT / "examples/protocol-exchange/fixtures" / (kind + ".json")
        if not source.is_file():
            errors.append("missing conformance payload: " + kind);continue
        with tempfile.TemporaryDirectory(prefix="envelope-fixture-") as tmp:
            root = Path(tmp)
            raw = source.read_bytes();(root/"artifact.json").write_bytes(raw)
            envelope = finalize({
                "artifact_type":"interchange-envelope", "envelope_id":"IE-fixture",
                "contract_profile":emitted["profile"],"profile_sha256":emitted["profile_sha256"],
                "origin":{"capability_manifest_sha256":capabilities["manifest_sha256"]},
                "payload":{"artifact_type":kind,"artifact_id":payload_identity(read_json(source)),"media_type":"application/json","path":"artifact.json","sha256":hashlib.sha256(raw).hexdigest()},
                "required_features":emitted["required_features"],"optional_features":[],"extensions":{}
            },"envelope_sha256")
            result=validate_envelope(envelope,capabilities=capabilities,direction="produces",payload_root=root)
            errors.extend(result["errors"]);count+=1
            consumer=finalize({"artifact_type":"integration-capability-manifest","interfaces":{"produces":[],"consumes":[copy.deepcopy(emitted)]}},"manifest_sha256")
            result=validate_envelope(envelope,capabilities=consumer,direction="consumes",declaration=capabilities,payload_root=root)
            errors.extend(result["errors"]);count+=1
    return {"ok":not errors,"checks":count,"errors":errors}


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--envelope",type=Path)
    parser.add_argument("--declaration",type=Path,help="Supplied public capability declaration")
    parser.add_argument("--payload-root",type=Path)
    parser.add_argument("--direction",choices=["produces","consumes"],default="consumes")
    args=parser.parse_args()
    try:
        caps=load_capabilities(ROOT);report=validate_capabilities(caps)
        tests=self_test(caps);errors=report["errors"]+tests["errors"]
        checked=None
        if args.envelope:
            checked=validate_envelope(read_json(args.envelope),capabilities=caps,direction=args.direction,
                declaration=read_json(args.declaration) if args.declaration else None,
                payload_root=args.payload_root or args.envelope.resolve().parent)
            errors+=checked["errors"]
        print(json.dumps({"ok":not errors,"capabilities":report,"self_test":tests,"envelope":checked,"errors":errors},ensure_ascii=False,indent=2))
        return int(bool(errors))
    except (ValueError,OSError,TypeError,KeyError,UnicodeError) as exc:
        print(json.dumps({"ok":False,"errors":[str(exc)]}));return 1
if __name__=="__main__":raise SystemExit(main())
