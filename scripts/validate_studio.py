#!/usr/bin/env python3
"""Check a studio: its layout, its manifest, every iteration's files, and the work trail.

    python scripts/validate_studio.py <studio-dir> [--json]

What it refuses: a manifest that is not what init writes, a character the
manifest lists without a directory or a directory it does not list, a character
id that ends in a dot or differs from another only by case, an iteration whose
files are missing or whose hashes no longer match, a slot with two accepted
iterations, an accepted iteration whose accepted copy is missing, an acceptance
history that names an iteration of another slot, and a work trail the ledger
cannot account for.
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
    "iteration_id", "at", "character", "slot", "status", "acceptances", "result", "package", "request",
    "request_layout", "response", "service", "seed", "note", "accepted_path", "superseded_by", "rejected_at", "reason",
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


def check_character_ids(listed: list[Any], on_disk: list[str], errors: list[str]) -> None:
    """A character id must name the same directory on every system."""
    for character in sorted({str(value) for value in (*listed, *on_disk)}):
        if not studio.valid_character_id(character):
            errors.append(f"character id {character!r} is not a valid character id; Windows cannot hold it as written")
    seen: dict[str, str] = {}
    for character in sorted({str(value) for value in listed}):
        other = seen.setdefault(character.casefold(), character)
        if other != character:
            errors.append(f"characters {other!r} and {character!r} differ only by case; Windows and macOS keep both in one directory")


def check_history(rows: list[dict[str, Any]], character: str, errors: list[str]) -> None:
    """Each acceptance names what it replaced in the same slot; only a superseded row says what replaced it.

    Accepting an earlier image again supersedes a later one, so an acceptance
    may name any other iteration of the slot, not only an earlier one.
    """
    slots = {str(row.get("iteration_id")): row.get("slot") for row in rows}
    for number, row in enumerate(rows, 1):
        label = f"characters/{character}/iterations.jsonl:{number}"
        acceptances = row.get("acceptances")
        if not isinstance(acceptances, list):
            errors.append(f"{label}: acceptances must be a list")
            continue
        for acceptance in acceptances:
            if not isinstance(acceptance, dict) or set(acceptance) != {"at", "supersedes"} or not isinstance(acceptance.get("at"), str):
                errors.append(f"{label}: an acceptance must carry exactly at and supersedes")
                continue
            replaced = acceptance["supersedes"]
            if replaced is not None and (replaced == row.get("iteration_id") or slots.get(str(replaced)) != row.get("slot")):
                errors.append(f"{label}: supersedes {replaced!r}, which is not another iteration of slot {row.get('slot')!r}")
        status = row.get("status")
        if status == "candidate" and acceptances:
            errors.append(f"{label}: a candidate has never been accepted, and lists acceptances")
        if status in ("accepted", "superseded") and not acceptances:
            errors.append(f"{label}: {status} and no acceptance is recorded")
        by = row.get("superseded_by")
        if status == "superseded":
            if by == row.get("iteration_id") or slots.get(str(by)) != row.get("slot"):
                errors.append(f"{label}: superseded by {by!r}, which is not another iteration of slot {row.get('slot')!r}")
        elif "superseded_by" in row:
            errors.append(f"{label}: superseded_by is recorded on an iteration that is {status}")


def check_layout(root: Path, row: dict[str, Any], label: str, errors: list[str]) -> None:
    layout = row.get("request_layout")
    if layout is None:
        return
    request = row.get("request")
    if not isinstance(request, dict) or not (root / str(request.get("path"))).is_file():
        errors.append(f"{label}: a request layout is recorded without its request")
        return
    try:
        studio.check_request_layout(layout, studio.read_json(root / str(request["path"])))
    except (ValueError, OSError) as exc:
        errors.append(f"{label}: {exc}")


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    if not root.exists():
        return [f"the directory {root} does not exist"]
    if not root.is_dir():
        return [f"{root} is not a directory"]
    if not (root / studio.MANIFEST).is_file():
        return [f"{root}: no {studio.MANIFEST}; this directory is not a studio"]
    try:
        document = studio.manifest(root)
    except (ValueError, OSError) as exc:
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
    check_character_ids(listed, on_disk, errors)
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
        except (ValueError, OSError) as exc:
            errors.append(str(exc))
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
            check_layout(root, row, label, errors)
            if row.get("status") == "accepted":
                if row["slot"] in accepted_slots:
                    errors.append(f"{label}: slot {row['slot']!r} is accepted twice ({accepted_slots[row['slot']]} and {row.get('iteration_id')})")
                accepted_slots[row["slot"]] = str(row.get("iteration_id"))
                copy = row.get("accepted_path")
                if not copy or not (root / str(copy)).is_file():
                    errors.append(f"{label}: accepted and its copy under accepted/ is missing")
                elif row.get("result") and studio.sha256_file(root / str(copy)) != row["result"]["sha256"]:
                    errors.append(f"{label}: the copy under accepted/ differs from the result")
        if len(ids) != len(set(ids)):
            errors.append(f"characters/{character}/iterations.jsonl: an iteration id repeats")
        check_history(rows, character, errors)
    from adoption_workflow import reference_index
    for character in on_disk:
        if not studio.valid_character_id(character):
            continue
        try:
            errors.extend(f"character {character}: {error}" for error in reference_index(root, character)["errors"])
        except (ValueError, OSError, RuntimeError) as exc:
            errors.append(f"character {character}: reference workflow: {exc}")
    # The gallery is written by every command that records, so one that does not
    # match the records means a record was written some other way.
    stale = studio.gallery_stale(root)
    if stale:
        errors.append(f"gallery: {stale}; python scripts/studio.py gallery rewrites it")
    try:
        errors.extend(work_ledger.check(root))
    except (ValueError, OSError) as exc:
        errors.append(f"work trail: {exc}")
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
