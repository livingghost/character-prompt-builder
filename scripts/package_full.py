#!/usr/bin/env python3
"""Build a deterministic full CPB release with every validated pack and catalog."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any, Sequence

from catalog_html import discover_pack_tree
from package import (
    _cleanup_attempt_directory,
    _validate_publication_targets,
    archive_content_sha256,
    clean_artifacts,
    copy_runtime_tree,
    ensure_output_is_not_release_input,
    publish_validated_outputs,
    sha256_file,
    tree_file_hashes,
    validate_keep_stage_destination,
    validate_stage,
    write_deterministic_zip,
)
from package_metadata import load_package_metadata



def progress(message: str, started: float) -> None:
    elapsed = time.monotonic() - started
    print(f"[package-full {elapsed:9.1f}s] {message}", file=sys.stderr, flush=True)

def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def run_json(
    command: Sequence[str],
    cwd: Path,
    *,
    require_ok: bool = True,
) -> dict[str, Any]:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    process = subprocess.run(
        list(command),
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        check=False,
    )
    try:
        value = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"command did not return JSON: {' '.join(command)}: {exc}\n"
            f"stdout={process.stdout}\nstderr={process.stderr}"
        ) from exc
    if (
        process.returncode
        or not isinstance(value, dict)
        or (require_ok and value.get("ok") is not True)
    ):
        raise RuntimeError(
            f"command failed: {' '.join(command)}\n"
            f"stdout={process.stdout}\nstderr={process.stderr}"
        )
    return value


def full_include(core_include: Sequence[str]) -> tuple[str, ...]:
    output = [
        value
        for value in core_include
        if not (Path(value).parts and Path(value).parts[0] == "packs")
    ]
    output.append("packs")
    return tuple(output)


def build_full_manifest(root: Path, version: str, pack_rows: list[dict[str, Any]]) -> dict[str, Any]:
    files = []
    for path in sorted(
        (item for item in root.rglob("*") if item.is_file() and item.name != "FULL-MANIFEST.json"),
        key=lambda value: value.relative_to(root).as_posix(),
    ):
        if path.is_symlink():
            raise ValueError(f"symbolic links are forbidden in full releases: {path}")
        files.append(
            {
                "path": path.relative_to(root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return {
        "format": "character-prompt-builder-full-release-manifest",
        "package": root.name,
        "version": version,
        "variant": "full",
        "pack_count": len(pack_rows),
        "packs": pack_rows,
        "file_count_excluding_manifest": len(files),
        "total_bytes_excluding_manifest": sum(row["bytes"] for row in files),
        "files": files,
    }


def verify_full_manifest(root: Path) -> dict[str, Any]:
    manifest_path = root / "FULL-MANIFEST.json"
    value = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    if not isinstance(value, dict):
        return {
            "ok": False,
            "checks": 1,
            "file_count": 0,
            "errors": ["FULL-MANIFEST must be a JSON object"],
        }

    metadata = load_package_metadata(root)
    expected_pack_rows = validate_all_packs(root)["packs"]
    expected = {
        path.relative_to(root).as_posix(): path
        for path in root.rglob("*")
        if path.is_file() and path != manifest_path
    }
    expected_fields = {
        "format",
        "package",
        "version",
        "variant",
        "pack_count",
        "packs",
        "file_count_excluding_manifest",
        "total_bytes_excluding_manifest",
        "files",
    }
    if set(value) != expected_fields:
        errors.append("FULL-MANIFEST top-level fields differ from the contract")
    expected_headers = {
        "format": "character-prompt-builder-full-release-manifest",
        "package": metadata.name,
        "version": metadata.version,
        "variant": "full",
        "pack_count": len(expected_pack_rows),
        "packs": expected_pack_rows,
        "file_count_excluding_manifest": len(expected),
        "total_bytes_excluding_manifest": sum(
            path.stat().st_size for path in expected.values()
        ),
    }
    for field, expected_value in expected_headers.items():
        if value.get(field) != expected_value:
            errors.append(f"FULL-MANIFEST {field} differs from the release tree")

    rows = value.get("files")
    if not isinstance(rows, list):
        rows = []
        errors.append("FULL-MANIFEST files must be an array")
    observed: dict[str, dict[str, Any]] = {}
    observed_order: list[str] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != {"path", "bytes", "sha256"}:
            errors.append(f"FULL-MANIFEST files[{index}] has invalid fields")
            continue
        name = row.get("path")
        if not isinstance(name, str) or not name:
            errors.append(f"FULL-MANIFEST files[{index}].path is invalid")
            continue
        if name in observed:
            errors.append(f"FULL-MANIFEST contains a duplicate path: {name}")
            continue
        observed[name] = row
        observed_order.append(name)
    if observed_order != sorted(expected):
        errors.append("FULL-MANIFEST file rows are not the exact sorted inventory")
    if set(expected) != set(observed):
        errors.append("FULL-MANIFEST file inventory differs from the release tree")
    for name in sorted(set(expected) & set(observed)):
        row = observed[name]
        path = expected[name]
        if row.get("bytes") != path.stat().st_size or row.get("sha256") != sha256_file(path):
            errors.append(f"FULL-MANIFEST mismatch: {name}")
    return {
        "ok": not errors,
        "checks": len(expected) + len(expected_headers) + 2,
        "file_count": len(expected),
        "errors": errors,
    }


def run_bundled_pack_release_gates(
    root: Path,
    *,
    label: str,
    reports_dir: Path,
    runtime_root: Path,
) -> dict[str, Any]:
    """Run each bundled released pack's actual owner-declared gate."""

    packs = discover_pack_tree(root / "packs", require_lock=True)
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for pack in packs:
        pack_runtime = runtime_root / pack.pack_id
        state_file = pack_runtime / "state.json"
        cache_dir = pack_runtime / "cache"
        managed_root = pack_runtime / "managed"
        managed_root.mkdir(parents=True, exist_ok=True)
        state = {
            "pack_roots": [str(pack.root.resolve())],
            "enabled_packs": [pack.pack_id],
            "resource_providers": {
                name: pack.pack_id
                for name in sorted(pack.validation.resource_bindings)
            },
        }
        write_json(state_file, state)
        report_path = reports_dir / f"{label}-pack-gate-{pack.pack_id}.json"
        try:
            report = run_json(
                [
                    sys.executable,
                    "scripts/pack_release_gate.py",
                    str(pack.root.resolve()),
                    "--state-file",
                    str(state_file),
                    "--cache-dir",
                    str(cache_dir),
                    "--managed-root",
                    str(managed_root),
                    "--report-out",
                    str(report_path),
                ],
                root,
            )
        except Exception as exc:
            errors.append(f"{pack.pack_id}@{pack.release}: {exc}")
            continue
        rows.append(
            {
                "pack_id": pack.pack_id,
                "name": pack.name,
                "release": pack.release,
                "ok": report.get("ok") is True,
                "suite_results": report.get("suites") or report.get("checks") or {},
            }
        )
        if report.get("ok") is not True:
            errors.append(f"{pack.pack_id}@{pack.release}: release gate returned ok=false")
    output = {
        "ok": not errors and len(rows) == len(packs),
        "checks": len(packs),
        "pack_count": len(packs),
        "packs": rows,
        "errors": errors,
    }
    write_json(reports_dir / f"{label}-bundled-pack-gates.json", output)
    if output["ok"] is not True:
        raise RuntimeError(
            "one or more bundled pack release gates failed: " + "; ".join(errors)
        )
    return output


def validate_all_packs(root: Path) -> dict[str, Any]:
    packs = discover_pack_tree(root / "packs", require_lock=True)
    rows = [
        {
            "pack_id": pack.pack_id,
            "name": pack.name,
            "release": pack.release,
            "root": pack.root.relative_to(root).as_posix(),
            "record_count": len(pack.validation.records),
            "resource_file_count": len(pack.validation.resource_files),
        }
        for pack in packs
    ]
    return {
        "ok": True,
        "checks": len(rows),
        "pack_count": len(rows),
        "packs": rows,
        "errors": [],
    }


def chmod_variation(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_symlink():
            continue
        if path.is_dir():
            path.chmod(0o700)
        elif path.is_file():
            path.chmod(0o600)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out", type=Path)
    parser.add_argument("--reports-dir", type=Path)
    parser.add_argument("--keep-stage", type=Path)
    args = parser.parse_args(argv)
    started = time.monotonic()

    source = args.source.expanduser().resolve()
    metadata = load_package_metadata(source)
    canonical_name = f"{metadata.name}-{metadata.version}-full.zip"
    archive = (args.out or (source / "dist" / canonical_name)).expanduser().resolve()
    if archive.name != canonical_name:
        raise ValueError(f"full release archive must be named {canonical_name}")
    reports_dir = (
        args.reports_dir.expanduser().resolve()
        if args.reports_dir
        else archive.with_suffix("").with_name(archive.stem + "-reports")
    )
    sha_path = archive.with_suffix(archive.suffix + ".sha256")
    release_include = full_include(metadata.release_include)
    keep_stage = (
        validate_keep_stage_destination(args.keep_stage, source, release_include)
        if args.keep_stage
        else None
    )
    ensure_output_is_not_release_input(
        archive, source, release_include, label="full release archive"
    )
    ensure_output_is_not_release_input(
        sha_path, source, release_include, label="full release checksum"
    )
    ensure_output_is_not_release_input(
        reports_dir, source, release_include, label="full release reports"
    )
    _validate_publication_targets(archive, sha_path, reports_dir, keep_stage)
    archive.parent.mkdir(parents=True, exist_ok=True)
    attempt_prefix = f".{archive.stem}-candidate-"
    publish_root = Path(
        tempfile.mkdtemp(prefix=attempt_prefix, dir=str(archive.parent))
    )
    candidate_archive = publish_root / archive.name
    candidate_sha_path = publish_root / (archive.name + ".sha256")
    candidate_reports = publish_root / "reports"
    candidate_reports.mkdir()
    candidate_keep_stage = (
        publish_root / "retained-stage" if keep_stage is not None else None
    )
    reports: dict[str, Any] | None = None

    progress("starting full release", started)
    try:
        with tempfile.TemporaryDirectory(prefix="cpb-full-package-") as temp:
            temp_root = Path(temp)
            stage = temp_root / metadata.name
            progress("copying runtime tree and every pack", started)
            copy_runtime_tree(
                source,
                stage,
                release_include,
                exclude_names=metadata.release_exclude_names,
            )
            clean_artifacts(stage)

            progress("rebuilding core metadata", started)
            run_json(
                [sys.executable, "scripts/rebuild_metadata.py"],
                stage,
                require_ok=False,
            )
            progress("generating catalog from staged packs", started)
            catalog_report = run_json(
                [
                    sys.executable,
                    "scripts/catalog_html.py",
                    "--pack-tree",
                    "packs",
                    "--released",
                    "--output",
                    "catalog",
                ],
                stage,
            )
            progress("validating every staged pack", started)
            pack_report = validate_all_packs(stage)
            progress("running every staged pack's declared release gate", started)
            bundled_pack_gates = run_bundled_pack_release_gates(
                stage,
                label="staged",
                reports_dir=candidate_reports,
                runtime_root=temp_root / "staged-pack-gates",
            )
            write_json(
                stage / "FULL-MANIFEST.json",
                build_full_manifest(stage, metadata.version, pack_report["packs"]),
            )

            before_validation = tree_file_hashes(stage)
            progress("running complete production gates on staged release", started)
            staged_gate_reports, staged_contract = validate_stage(
                stage,
                candidate_reports,
                "staged",
                temp_root / "staged-runtime",
                strict_release_tree=False,
            )
            catalog_validation = run_json(
                [sys.executable, "scripts/validate_catalog_site.py", "catalog"],
                stage,
            )
            full_manifest_validation = verify_full_manifest(stage)
            if full_manifest_validation["ok"] is not True:
                raise RuntimeError("full manifest validation failed")
            if before_validation != tree_file_hashes(stage):
                raise RuntimeError("full release validation modified the staged tree")

            progress("writing deterministic full ZIP", started)
            write_deterministic_zip(stage, candidate_archive)
            digest = sha256_file(candidate_archive)
            content_digest = archive_content_sha256(candidate_archive)
            candidate_sha_path.write_text(
                f"{digest}  {archive.name}\n", encoding="utf-8", newline="\n"
            )
            with zipfile.ZipFile(candidate_archive) as zf:
                bad = zf.testzip()
                if bad:
                    raise RuntimeError(f"candidate ZIP CRC failed at {bad}")

            progress("extracting and comparing full ZIP", started)
            extract_parent = temp_root / "extracted"
            extract_parent.mkdir()
            with zipfile.ZipFile(candidate_archive) as zf:
                zf.extractall(extract_parent)
            extracted = extract_parent / metadata.name
            if tree_file_hashes(stage) != tree_file_hashes(extracted):
                raise RuntimeError("extracted full release differs from staged tree")

            progress("running complete production gates on extracted release", started)
            extracted_gate_reports, extracted_contract = validate_stage(
                extracted,
                candidate_reports,
                "extracted",
                temp_root / "extracted-runtime",
                expected_contract=staged_contract,
                strict_release_tree=False,
            )
            if extracted_contract != staged_contract:
                raise RuntimeError("extracted production gate coverage differs from stage")
            extracted_pack_report = validate_all_packs(extracted)
            progress("running every extracted pack's declared release gate", started)
            extracted_bundled_pack_gates = run_bundled_pack_release_gates(
                extracted,
                label="extracted",
                reports_dir=candidate_reports,
                runtime_root=temp_root / "extracted-pack-gates",
            )
            extracted_catalog_validation = run_json(
                [sys.executable, "scripts/validate_catalog_site.py", "catalog"],
                extracted,
            )
            extracted_manifest_validation = verify_full_manifest(extracted)
            if extracted_manifest_validation["ok"] is not True:
                raise RuntimeError("extracted full manifest validation failed")

            repeat = temp_root / "repeat.zip"
            write_deterministic_zip(stage, repeat)
            deterministic = candidate_archive.read_bytes() == repeat.read_bytes()
            if not deterministic:
                raise RuntimeError("normal full rebuild is not byte-identical")
            chmod_variation(stage)
            permission_repeat = temp_root / "permission-repeat.zip"
            write_deterministic_zip(stage, permission_repeat)
            permission_deterministic = (
                candidate_archive.read_bytes() == permission_repeat.read_bytes()
            )
            if not permission_deterministic:
                raise RuntimeError("permission-varied full rebuild is not byte-identical")

            if candidate_keep_stage is not None:
                shutil.copytree(extracted, candidate_keep_stage)

            reports = {
                "ok": True,
                "release": metadata.version,
                "variant": "full",
                "archive": archive.name,
                "archive_bytes": candidate_archive.stat().st_size,
                "archive_sha256": digest,
                "archive_content_sha256": content_digest,
                "catalog_generation": catalog_report,
                "pack_validation": pack_report,
                "bundled_pack_release_gates": bundled_pack_gates,
                "staged_core_gate_contract": staged_contract,
                "extracted_core_gate_contract": extracted_contract,
                "catalog_full_validation": catalog_validation,
                "full_manifest_validation": full_manifest_validation,
                "extracted_pack_validation": extracted_pack_report,
                "extracted_bundled_pack_release_gates": extracted_bundled_pack_gates,
                "extracted_catalog_validation": extracted_catalog_validation,
                "extracted_full_manifest_validation": extracted_manifest_validation,
                "stage_archive_tree_match": True,
                "zip_crc_ok": True,
                "deterministic_rebuild": deterministic,
                "permission_varied_rebuild": permission_deterministic,
                "publication_mode": "fresh-attempt-archive-last",
                "staged_gate_reports": sorted(staged_gate_reports),
                "extracted_gate_reports": sorted(extracted_gate_reports),
            }
            write_json(candidate_reports / "full-release-summary.json", reports)
            write_json(candidate_reports / "catalog-generation.json", catalog_report)
            write_json(candidate_reports / "catalog-full-validation.json", catalog_validation)
            write_json(candidate_reports / "pack-validation.json", pack_report)
            write_json(
                candidate_reports / "bundled-pack-release-gates.json",
                bundled_pack_gates,
            )
            write_json(
                candidate_reports / "extracted-bundled-pack-release-gates.json",
                extracted_bundled_pack_gates,
            )
            write_json(
                candidate_reports / "full-manifest-validation.json",
                full_manifest_validation,
            )
            write_json(
                candidate_reports / "extracted-catalog-validation.json",
                extracted_catalog_validation,
            )
            write_json(
                candidate_reports / "extracted-full-manifest-validation.json",
                extracted_manifest_validation,
            )

        progress("publishing validated reports, checksum, and archive", started)
        publish_validated_outputs(
            candidate_archive=candidate_archive,
            candidate_sha_path=candidate_sha_path,
            candidate_reports_dir=candidate_reports,
            archive=archive,
            sha_path=sha_path,
            reports_dir=reports_dir,
            candidate_keep_stage=candidate_keep_stage,
            keep_stage=keep_stage,
        )
    except BaseException:
        _cleanup_attempt_directory(publish_root, archive.parent, attempt_prefix)
        raise

    _cleanup_attempt_directory(publish_root, archive.parent, attempt_prefix)
    progress("full release completed", started)
    if reports is not None:
        print(json.dumps(reports, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
