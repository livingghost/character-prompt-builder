#!/usr/bin/env python3
"""Check a studio: its layout, its manifest, every iteration's files, and the work trail.

    python scripts/validate_studio.py <studio-dir> [--json]

What it refuses: a manifest that is not what init writes, a character the
manifest lists without a directory or a directory it does not list, an
iteration whose files are missing or whose hashes no longer match, a slot with
two accepted iterations, an accepted iteration whose accepted copy is missing,
and a work trail the ledger cannot account for.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import studio  # noqa: E402
import work_ledger  # noqa: E402

MANIFEST_FIELDS = {"studio_id", "title", "created_at", "characters"}
ITERATION_FIELDS = {
    "iteration_id", "at", "character", "slot", "status", "supersedes", "result", "package", "request",
    "response", "service", "seed", "note", "accepted_at", "accepted_path", "superseded_by", "rejected_at", "reason",
}


def check_file_reference(root: Path, reference: Any, label: str, errors: list[str]) -> None:
    if reference is None:
        return
    if not isinstance(reference, dict) or not reference.get("path") or not reference.get("sha256"):
        errors.append(f"{label}: must carry path and sha256")
        return
    path = root / str(reference["path"])
    if not path.is_file():
        errors.append(f"{label}: {reference['path']} is missing")
        return
    if studio.sha256_file(path) != reference["sha256"]:
        errors.append(f"{label}: {reference['path']} no longer matches its recorded sha256")


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    if not (root / studio.MANIFEST).is_file():
        return [f"{root}: no {studio.MANIFEST}; this directory is not a studio"]
    try:
        document = studio.manifest(root)
    except (ValueError, json.JSONDecodeError) as exc:
        return [f"{studio.MANIFEST}: {exc}"]
    missing = sorted(MANIFEST_FIELDS - set(document))
    extra = sorted(set(document) - MANIFEST_FIELDS)
    if missing:
        errors.append(f"{studio.MANIFEST}: missing {missing}")
    if extra:
        errors.append(f"{studio.MANIFEST}: unexpected {extra}")
    if not isinstance(document.get("studio_id"), str) or not studio.STUDIO_ID.match(document.get("studio_id") or ""):
        errors.append(f"{studio.MANIFEST}: studio_id is not a studio id")
    for name in studio.DIRECTORIES:
        if not (root / name).is_dir():
            errors.append(f"missing directory: {name}")
    listed = [entry.get("id") for entry in document.get("characters") or [] if isinstance(entry, dict)]
    if len(listed) != len(set(listed)):
        errors.append(f"{studio.MANIFEST}: a character is listed twice")
    on_disk = sorted(path.name for path in (root / "characters").iterdir() if path.is_dir()) if (root / "characters").is_dir() else []
    for character in listed:
        if character not in on_disk:
            errors.append(f"character {character!r} is listed and has no directory")
    for character in on_disk:
        if character not in listed:
            errors.append(f"characters/{character} is on disk and not listed in {studio.MANIFEST}")
    for character in on_disk:
        home = root / "characters" / character
        for name in studio.CHARACTER_DIRECTORIES:
            if not (home / name).is_dir():
                errors.append(f"characters/{character}: missing directory {name}")
        if not (home / "sheet" / "sheet-data.json").is_file():
            errors.append(f"characters/{character}: sheet/sheet-data.json is missing")
        try:
            rows = studio.read_iterations(home)
        except (ValueError, json.JSONDecodeError) as exc:
            errors.append(f"characters/{character}/iterations.jsonl: {exc}")
            continue
        accepted_slots: dict[str, str] = {}
        ids: list[str] = []
        for number, row in enumerate(rows, 1):
            label = f"characters/{character}/iterations.jsonl:{number}"
            unknown = sorted(set(row) - ITERATION_FIELDS)
            if unknown:
                errors.append(f"{label}: unknown fields {unknown}")
            if row.get("status") not in studio.STATUSES:
                errors.append(f"{label}: status {row.get('status')!r} is not one of {studio.STATUSES}")
            if not isinstance(row.get("slot"), str) or not studio.SLOT.match(row.get("slot") or ""):
                errors.append(f"{label}: slot is not a slot name")
            ids.append(str(row.get("iteration_id")))
            for name in ("result", "package", "request", "response"):
                check_file_reference(root, row.get(name), f"{label} {name}", errors)
            if row.get("status") == "accepted":
                if row["slot"] in accepted_slots:
                    errors.append(f"{label}: slot {row['slot']!r} is accepted twice ({accepted_slots[row['slot']]} and {row.get('iteration_id')})")
                accepted_slots[row["slot"]] = str(row.get("iteration_id"))
                copy = row.get("accepted_path")
                if not copy or not (root / str(copy)).is_file():
                    errors.append(f"{label}: accepted and its copy under accepted/ is missing")
                elif row.get("result") and studio.sha256_file(root / str(copy)) != row["result"]["sha256"]:
                    errors.append(f"{label}: the copy under accepted/ differs from the result")
            if row.get("supersedes") and row["supersedes"] not in ids:
                errors.append(f"{label}: supersedes {row['supersedes']!r}, which is not an earlier iteration")
        if len(ids) != len(set(ids)):
            errors.append(f"characters/{character}/iterations.jsonl: an iteration id repeats")
    from adoption_workflow import reference_index
    for character in on_disk:
        try:
            errors.extend(f"character {character}: {error}" for error in reference_index(root, character)["errors"])
        except (ValueError, OSError, RuntimeError) as exc:
            errors.append(f"character {character}: reference workflow: {exc}")
    # The gallery is written by every command that records, so one that does not
    # match the records means a record was written some other way.
    stale = studio.gallery_stale(root)
    if stale:
        errors.append(f"gallery: {stale}; python scripts/studio.py gallery rewrites it")
    errors.extend(work_ledger.check(root))
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("studio", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    errors = validate(args.studio.resolve())
    if args.json:
        print(json.dumps({"ok": not errors, "studio": str(args.studio.resolve()), "errors": errors}, ensure_ascii=False, indent=2))
    else:
        for error in errors:
            print(f"error: {error}")
        print("ok" if not errors else f"{len(errors)} error(s)")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
