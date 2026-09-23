#!/usr/bin/env python3
"""A protocol bundle preserves its payload and never replaces existing work."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "examples" / "state-aware-pilot" / "character-identity-contract.json"
PROFILE = "visual-contract-package"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(script: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(Path(__file__).with_name(script)), *arguments],
        text=True, encoding="utf-8", capture_output=True, check=False,
    )


def build(payload: Path, out: Path) -> subprocess.CompletedProcess[str]:
    identity = json.loads(payload.read_text(encoding="utf-8"))["contract_id"]
    return run(
        "build_interchange_envelope.py",
        "--profile", PROFILE,
        "--payload", str(payload),
        "--payload-type", "character-identity-contract",
        "--payload-id", identity,
        "--out", str(out),
    )


def inventory(root: Path) -> dict[str, str]:
    return {path.relative_to(root).as_posix(): digest(path)
            for path in root.rglob("*") if path.is_file()}


def main() -> int:
    errors: list[str] = []
    if not SAMPLE.is_file():
        print(json.dumps({"ok": False, "errors": [f"sample payload missing: {SAMPLE}"]}, indent=2))
        return 1

    with tempfile.TemporaryDirectory(prefix="cpb-interchange-") as temp:
        root = Path(temp)
        payload = root / "payload.json"
        shutil.copy2(SAMPLE, payload)
        before = digest(payload)

        # A bundle destination must not replace its input file.
        same_path = build(payload, payload)
        payload_intact = digest(payload) == before
        if same_path.returncode == 0:
            errors.append("the builder accepted its payload file as a bundle destination")
        if not payload_intact:
            errors.append("the payload changed while the run was refused")

        # Existing work at the requested destination is preserved in full.
        occupied = root / "occupied"
        occupied.mkdir()
        (occupied / "artifact.json").write_text("someone else's file\n", encoding="utf-8")
        (occupied / "notes.txt").write_text("keep these notes\n", encoding="utf-8")
        occupied_before = inventory(occupied)
        clobber = build(payload, occupied)
        victim_intact = inventory(occupied) == occupied_before
        if clobber.returncode == 0:
            errors.append("the builder accepted an occupied bundle directory")
        if not victim_intact:
            errors.append("existing bundle-directory content changed")

        # A new directory receives the exact payload, declaration and envelope.
        output = root / "bundle"
        ordinary = build(payload, output)
        expected_members = {"artifact.json", "declaration.json", "envelope.json"}
        envelope_ok = (ordinary.returncode == 0 and output.is_dir()
                       and set(inventory(output)) == expected_members)
        recorded_matches = False
        validated = False
        retry_intact = False
        if envelope_ok:
            envelope = json.loads((output / "envelope.json").read_text(encoding="utf-8"))
            recorded_matches = (envelope["payload"]["path"] == "artifact.json"
                                and envelope["payload"]["sha256"] == digest(output / "artifact.json") == before
                                and (output / "artifact.json").read_bytes() == payload.read_bytes())
            checked = run(
                "validate_integration.py", "--direction", "consumes",
                "--envelope", str(output / "envelope.json"),
                "--declaration", str(output / "declaration.json"),
                "--payload-root", str(output),
            )
            validated = checked.returncode == 0 and json.loads(checked.stdout).get("ok") is True
            if not validated:
                errors.append("created bundle did not validate: " + checked.stdout + checked.stderr)
            bundle_before = inventory(output)
            retry = build(payload, output)
            retry_intact = retry.returncode != 0 and inventory(output) == bundle_before
            if not retry_intact:
                errors.append("repeated publication altered or replaced the existing bundle")
        else:
            errors.append(f"the ordinary build failed: {ordinary.returncode} {ordinary.stdout} {ordinary.stderr}")
        if envelope_ok and not recorded_matches:
            errors.append("the copied payload or its recorded hash differs from the source")
        if digest(payload) != before:
            errors.append("bundle publication changed the original payload")

    report = {
        "ok": not errors, "errors": errors,
        "stats": {
            "same_path_refused": same_path.returncode != 0,
            "payload_intact": payload_intact,
            "copy_clobber_refused": clobber.returncode != 0,
            "neighbour_intact": victim_intact,
            "ordinary_build_validates": envelope_ok and recorded_matches and validated,
            "published_bundle_preserved_on_retry": retry_intact,
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
