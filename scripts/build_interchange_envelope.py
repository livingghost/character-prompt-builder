#!/usr/bin/env python3
"""Write a new protocol bundle containing payload, declaration and envelope.

Only files explicitly supplied to this command and the installed declaration are
read. No discovery, network access, adoption, model execution or project mutation
is performed. --out must name a new directory in the user's workspace.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from integration_contract import finalize, find_interface, load_capabilities, validate_envelope, canonical_json, sha256_json
from io_budget import read_stream

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--payload", required=True)
    parser.add_argument("--payload-type", required=True)
    parser.add_argument("--payload-id", required=True)
    parser.add_argument("--media-type", default="application/json")
    parser.add_argument("--optional-feature", action="append", default=[])
    parser.add_argument("--out", required=True, help="New bundle directory")
    a = parser.parse_args()
    temporary = None
    lock = None
    acquired = False
    try:
        payload = Path(a.payload)
        if payload.is_symlink() or not payload.is_file():
            raise ValueError("payload must be a regular file")
        with payload.open("rb") as handle:
            raw = read_stream(handle)
        output = Path(a.out).absolute()
        if output.exists() or output.is_symlink():
            raise ValueError("output already exists; use a new bundle directory")
        if output.resolve().is_relative_to(ROOT.resolve()):
            raise ValueError("bundle output must not be inside the installed skill")
        output.parent.mkdir(parents=True, exist_ok=True)
        lock = output.parent / ("." + output.name + ".publish.lock")
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        acquired = True
        if output.exists():
            raise ValueError("output already exists")
        caps = load_capabilities(ROOT)
        profile = find_interface(caps, "produces", a.profile)
        if profile is None:
            raise ValueError("profile is not declared for export")
        optional = sorted(set(a.optional_feature))
        if set(optional) - set(profile["supported_features"]):
            raise ValueError("unsupported optional export feature")
        value = {
            "artifact_type": "interchange-envelope", "envelope_id": "",
            "contract_profile": a.profile, "profile_sha256": profile["profile_sha256"],
            "origin": {"capability_manifest_sha256": caps["manifest_sha256"]},
            "payload": {"artifact_type": a.payload_type, "artifact_id": a.payload_id,
                        "media_type": a.media_type, "path": "artifact.json",
                        "sha256": hashlib.sha256(raw).hexdigest()},
            "required_features": profile["required_features"], "optional_features": optional,
            "extensions": {},
        }
        value["envelope_id"] = "IE-" + sha256_json({k:v for k,v in value.items() if k != "envelope_id"})
        value = finalize(value, "envelope_sha256")
        temporary = Path(tempfile.mkdtemp(prefix=".protocol-stage-", dir=output.parent))
        (temporary / "artifact.json").write_bytes(raw)
        for name, data in [("declaration.json", caps), ("envelope.json", value)]:
            (temporary / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report = validate_envelope(value, capabilities=caps, direction="produces", payload_root=temporary)
        if not report["ok"]:
            raise ValueError("; ".join(report["errors"]))
        for path in temporary.iterdir():
            with path.open("rb") as handle: os.fsync(handle.fileno())
        temporary.rename(output)
        temporary = None
        print(json.dumps({"ok":True, "out":str(output), "envelope_sha256":value["envelope_sha256"], "canonical_adoption":False}, indent=2))
        return 0
    except (ValueError, OSError, TypeError, KeyError, UnicodeError) as exc:
        print(json.dumps({"ok":False, "errors":[str(exc)]}));return 1
    finally:
        if temporary is not None: shutil.rmtree(temporary)
        if acquired and lock is not None: lock.unlink(missing_ok=True)

if __name__ == "__main__":
    raise SystemExit(main())
