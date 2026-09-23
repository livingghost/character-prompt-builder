#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Mapping

sys.dont_write_bytecode = True

from execution_contract import sha256_file
from visual_evidence import validate_bundle
from catalog_cli import load_pack_catalog
from pack_manager import validate_pack

ROOT = Path(__file__).resolve().parents[1]


def positive_worker_count(value: Any) -> int:
    """Return one explicit positive worker request or reject it."""

    if isinstance(value, bool):
        raise ValueError("workers must be a positive integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("workers must be a positive integer") from exc
    if parsed <= 0 or str(value).strip() != str(parsed):
        raise ValueError("workers must be a positive integer")
    return parsed


def worker_argument(value: str) -> int:
    try:
        return positive_worker_count(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def canonical(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def self_hash(obj: dict[str, Any]) -> str:
    clone = dict(obj)
    clone.pop("reference_corpus_manifest_sha256", None)
    return hashlib.sha256(canonical(clone).encode("utf-8")).hexdigest()


def _resolve_manifest(root: Path | None) -> Path | None:
    if root is not None:
        resolved = root.resolve()
        candidate = resolved / "resources" / "reference-corpus" / "manifest.json"
        if not candidate.is_file():
            return None
        try:
            document = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return (
            candidate
            if isinstance(document, dict) and "reference_corpus_manifest_sha256" in document
            else None
        )
    resource = load_pack_catalog().resources.get("reference-corpus-manifest")
    return resource.path if resource is not None else None


def _owning_pack_root(manifest_path: Path) -> Path | None:
    for parent in manifest_path.parents:
        if (parent / "pack.json").is_file():
            return parent
    return None


def _has_webp_signature(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            header = handle.read(12)
    except OSError:
        return False
    return len(header) == 12 and header[:4] == b"RIFF" and header[8:] == b"WEBP"


def _declared_catalog_thumbnails(
    pack_root: Path,
    corpus: Path,
) -> tuple[set[str], list[str]]:
    """Return pack-declared display thumbnails that may coexist with the corpus."""

    errors: list[str] = []
    try:
        pack = json.loads((pack_root / "pack.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return set(), [f"catalog thumbnail declaration is unavailable: {exc}"]
    content = pack.get("content") if isinstance(pack, Mapping) else None
    bindings = content.get("resource_bindings") if isinstance(content, Mapping) else None
    binding = bindings.get("catalog-thumbnails") if isinstance(bindings, Mapping) else None
    if binding is None:
        return set(), []
    binding_path = Path(str(binding))
    if binding_path.is_absolute() or ".." in binding_path.parts:
        return set(), ["catalog-thumbnails binding is not a portable pack-relative path"]
    declaration_path = pack_root / binding_path
    try:
        declaration = json.loads(declaration_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return set(), [f"catalog thumbnail declaration is invalid: {exc}"]
    if declaration.get("format") != "character-prompt-builder-catalog-thumbnails":
        errors.append("catalog thumbnail declaration has an unsupported format")
    assets = declaration.get("assets")
    if not isinstance(assets, Mapping):
        return set(), errors + ["catalog thumbnail declaration lacks an assets object"]

    corpus_resolved = corpus.resolve()
    declared: set[str] = set()
    for asset_id, raw_entry in assets.items():
        prefix = f"catalog thumbnail {asset_id!r}"
        if not isinstance(raw_entry, Mapping):
            errors.append(f"{prefix} is not an object")
            continue
        relative = Path(str(raw_entry.get("path") or ""))
        if not relative.parts or relative.is_absolute() or ".." in relative.parts:
            errors.append(f"{prefix} path is not portable")
            continue
        if raw_entry.get("media_type") != "image/webp" or relative.suffix.lower() != ".webp":
            errors.append(f"{prefix} must declare one WebP display resource")
            continue
        candidate = pack_root / relative
        try:
            corpus_relative = candidate.resolve().relative_to(corpus_resolved).as_posix()
        except ValueError:
            errors.append(f"{prefix} is outside the reference corpus")
            continue
        if corpus_relative in declared:
            errors.append(f"{prefix} duplicates a declared thumbnail path")
            continue
        declared.add(corpus_relative)
        if not candidate.is_file():
            errors.append(f"{prefix} file is missing")
            continue
        if not _has_webp_signature(candidate):
            errors.append(f"{prefix} content is not WebP")
        expected_sha = str(raw_entry.get("sha256") or "")
        if expected_sha != sha256_file(candidate):
            errors.append(f"{prefix} sha256 mismatch")
    return declared, errors


def _pack_record_closure(
    pack_root: Path,
) -> tuple[dict[str, tuple[str, str, Mapping[str, Any]]], list[str], int]:
    """Load records from one pack and its required sibling dependencies."""
    roots_by_id: dict[str, Path] = {}
    for child in sorted(pack_root.parent.iterdir(), key=lambda value: value.name.lower()):
        manifest_path = child / "pack.json"
        if not child.is_dir() or not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        pack_id = str(manifest.get("pack_id") or "") if isinstance(manifest, Mapping) else ""
        if pack_id:
            roots_by_id[pack_id] = child.resolve()

    records: dict[str, tuple[str, str, Mapping[str, Any]]] = {}
    errors: list[str] = []
    visited: set[str] = set()

    def visit(current_root: Path) -> None:
        report = validate_pack(current_root, verify_lock=False)
        pack_id = str(report.pack_id or current_root.name)
        if pack_id in visited:
            return
        visited.add(pack_id)
        if not report.valid:
            messages = [issue.message for issue in report.issues if issue.severity == "error"]
            errors.append(f"pack {pack_id} is invalid: {'; '.join(messages)}")
            return
        for pack_record in report.records:
            record_id = str(pack_record.record.get("id") or "")
            existing = records.get(record_id)
            if existing is not None:
                errors.append(
                    f"record ID {record_id!r} is ambiguous across packs {existing[0]} and {pack_id}"
                )
                continue
            records[record_id] = (pack_id, pack_record.kind, pack_record.record)
        for dependency in report.manifest.get("dependencies") or []:
            if not isinstance(dependency, Mapping):
                continue
            dependency_id = str(dependency.get("pack_id") or "")
            dependency_root = roots_by_id.get(dependency_id)
            if dependency_root is None:
                errors.append(
                    f"required pack {dependency_id!r} is not present beside {pack_root.name}"
                )
                continue
            visit(dependency_root)

    visit(pack_root.resolve())
    return records, errors, len(visited)


def validate(
    root: Path | None = None,
    *,
    require_bundles: bool | None = None,
    workers: int = 1,
) -> dict[str, Any]:
    requested_workers = positive_worker_count(workers)
    manifest_path = _resolve_manifest(root)
    errors: list[str] = []
    warnings: list[str] = []
    if manifest_path is None:
        return {
            "ok": require_bundles is not True,
            "errors": ["the required reference-corpus resource is unavailable"] if require_bundles else [],
            "warnings": [] if require_bundles else ["no enabled pack provides the reference-corpus resource"],
            "stats": {},
        }
    corpus = manifest_path.parent
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "errors": [str(exc)], "warnings": [], "stats": {}}
    if manifest.get("reference_corpus_manifest_sha256") != self_hash(manifest):
        errors.append("reference_corpus_manifest_sha256 mismatch")

    pack_root = _owning_pack_root(manifest_path)
    available_records: dict[str, tuple[str, str, Mapping[str, Any]]] = {}
    pack_closure_count = 0
    if pack_root is None:
        errors.append("reference corpus is not owned by a content pack")
    else:
        available_records, pack_errors, pack_closure_count = _pack_record_closure(pack_root)
        errors.extend(pack_errors)
    evidence_assets = {
        str(record.get("source_sha256") or ""): record
        for _, kind, record in available_records.values()
        if kind == "asset" and record.get("asset_type") == "visual-evidence-bundle"
    }

    entries = manifest.get("entries") if isinstance(manifest.get("entries"), list) else []
    visual_root = corpus / "visual-evidence"
    bundles_present = visual_root.is_dir()
    if require_bundles is True and not bundles_present:
        errors.append("visual-evidence resources are required but the bundle directory is absent")
    validate_bundles = bundles_present if require_bundles is None else bool(require_bundles)
    if not validate_bundles:
        if bundles_present:
            warnings.append(
                "visual corpus bundle validation was intentionally skipped; manifest and canonical dispositions were validated"
            )
        else:
            warnings.append(
                "reference-corpus resources are unavailable; manifest and canonical dispositions were validated without SVG bundles"
            )

    symlinks = [
        path.relative_to(corpus).as_posix()
        for path in corpus.rglob("*")
        if path.is_symlink()
    ]
    if symlinks:
        errors.append(f"symbolic links are forbidden in reference corpus: {symlinks}")

    declared_thumbnails: set[str] = set()
    if pack_root is not None:
        declared_thumbnails, thumbnail_errors = _declared_catalog_thumbnails(pack_root, corpus)
        errors.extend(thumbnail_errors)

    raster_suffix = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
    rasters = [
        path.relative_to(corpus).as_posix()
        for path in corpus.rglob("*")
        if path.is_file() and path.suffix.lower() in raster_suffix
    ]
    standalone_rasters = [path for path in rasters if path not in declared_thumbnails]
    if standalone_rasters:
        errors.append("standalone raster files are forbidden in reference corpus")

    hashes: list[str] = []
    bundles: list[str] = []
    authorities: list[str] = []
    canonical_count = 0
    excluded_count = 0
    canonical_record_refs: set[str] = set()
    bundle_jobs: list[tuple[str, Path]] = []

    for index, entry in enumerate(entries):
        prefix = f"entries[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{prefix}: not object")
            continue
        source_sha = str(entry.get("source_sha256") or "")
        hashes.append(source_sha)
        if len(source_sha) != 64 or any(ch not in "0123456789abcdef" for ch in source_sha):
            errors.append(f"{prefix}: invalid source_sha256")
        disposition = entry.get("disposition")
        record_ids = entry.get("canonical_record_ids") or []
        if disposition == "canonical-preset-evidence":
            canonical_count += 1
            if not record_ids:
                errors.append(f"{prefix}: canonical evidence lacks record IDs")
            canonical_record_refs.update(str(value) for value in record_ids)
            asset = evidence_assets.get(source_sha)
            if asset is None:
                errors.append(f"{prefix}: canonical evidence lacks a searchable asset record")
            elif set(str(value) for value in asset.get("canonical_record_ids") or []) != set(
                str(value) for value in record_ids
            ):
                errors.append(f"{prefix}: asset and corpus canonical_record_ids disagree")
        elif disposition == "excluded-noncanonical-artifact":
            excluded_count += 1
            if record_ids:
                errors.append(f"{prefix}: excluded artifact claims record IDs")
            if source_sha in evidence_assets:
                errors.append(f"{prefix}: excluded artifact has a searchable asset record")

        authority_ref = entry.get("visual_authority_ref") or {}
        bundle_ref = entry.get("visual_evidence_bundle_ref") or {}
        authority_rel = str(authority_ref.get("path") or "")
        bundle_rel = str(bundle_ref.get("path") or "")
        authorities.append(authority_rel)
        bundles.append(bundle_rel)
        if not authority_rel or not bundle_rel:
            errors.append(f"{prefix}: visual authority or bundle reference is missing")
            continue
        if Path(authority_rel).is_absolute() or ".." in Path(authority_rel).parts:
            errors.append(f"{prefix}: authority path is not portable")
        if Path(bundle_rel).is_absolute() or ".." in Path(bundle_rel).parts:
            errors.append(f"{prefix}: bundle path is not portable")
        if not validate_bundles:
            continue
        authority_path = corpus / authority_rel
        bundle_path = corpus / bundle_rel
        if not authority_path.is_file():
            errors.append(f"{prefix}: missing authority")
            continue
        if not bundle_path.is_file():
            errors.append(f"{prefix}: missing bundle")
            continue
        try:
            authority = json.loads(authority_path.read_text(encoding="utf-8"))
            bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{prefix}: {exc}")
            continue
        if authority.get("source_sha256") != source_sha or bundle.get("source_sha256") != source_sha:
            errors.append(f"{prefix}: source hash disagreement")
        if (
            authority.get("authority_id") != authority_ref.get("id")
            or authority.get("visual_authority_sha256") != authority_ref.get("sha256")
        ):
            errors.append(f"{prefix}: authority reference mismatch")
        if (
            bundle.get("bundle_id") != bundle_ref.get("id")
            or bundle.get("visual_evidence_bundle_sha256") != bundle_ref.get("sha256")
        ):
            errors.append(f"{prefix}: bundle reference mismatch")
        bundle_jobs.append((prefix, bundle_path.parent))

    worker_count = 0
    if validate_bundles:
        # Each worker streams one SVG in bounded chunks. A small capped pool
        # makes complete-file safety inspection practical for a large corpus
        # without loading any SVG wholesale.
        # Sequential streaming avoids seek amplification on large release media.
        # The scanner itself is linear and bounded-memory.
        worker_count = max(1, min(requested_workers, 2, len(bundle_jobs) or 1))
        if worker_count == 1:
            for completed, (prefix, path) in enumerate(bundle_jobs, 1):
                try:
                    report = validate_bundle(path)
                except Exception as exc:  # keep release output structured
                    errors.append(f"{prefix}: bundle validation crashed: {exc}")
                    continue
                errors.extend(f"{prefix}: {value}" for value in report.get("errors", []))
                if completed % 10 == 0 or completed == len(bundle_jobs):
                    print(
                        f"[reference-corpus] validated {completed}/{len(bundle_jobs)} bundles",
                        file=sys.stderr,
                        flush=True,
                    )
        else:
            with ThreadPoolExecutor(max_workers=worker_count) as pool:
                futures = {pool.submit(validate_bundle, path): prefix for prefix, path in bundle_jobs}
                completed = 0
                for future in as_completed(futures):
                    prefix = futures[future]
                    completed += 1
                    try:
                        report = future.result()
                    except Exception as exc:  # keep release output structured
                        errors.append(f"{prefix}: bundle validation crashed: {exc}")
                        continue
                    errors.extend(f"{prefix}: {value}" for value in report.get("errors", []))
                    if completed % 10 == 0 or completed == len(futures):
                        print(
                            f"[reference-corpus] validated {completed}/{len(futures)} bundles",
                            file=sys.stderr,
                            flush=True,
                        )

    if any(value != 1 for value in Counter(hashes).values()):
        errors.append("each source hash must appear exactly once")
    if any(value != 1 for value in Counter(bundles).values()):
        errors.append("each bundle path must appear exactly once")
    if any(value != 1 for value in Counter(authorities).values()):
        errors.append("each authority path must appear exactly once")

    missing_record_ids = sorted(canonical_record_refs - set(available_records))
    if missing_record_ids:
        errors.append(
            "canonical evidence refers to missing records: " + ", ".join(missing_record_ids)
        )
    orphan_asset_hashes = sorted(set(evidence_assets) - set(hashes))
    if orphan_asset_hashes:
        errors.append(
            "searchable visual-evidence assets are absent from the corpus manifest: "
            + ", ".join(orphan_asset_hashes)
        )

    expected = {
        "unique_source_count": len(entries),
        "evidence_bundle_count": len(entries),
        "canonical_evidence_count": canonical_count,
        "excluded_noncanonical_count": excluded_count,
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            errors.append(f"{key} mismatch")

    stats = {
        "validation_mode": "full" if validate_bundles else "index-only",
        "visual_resources_present": bundles_present,
        "pack_closure_count": pack_closure_count,
        "available_record_count": len(available_records),
        "canonical_record_reference_count": len(canonical_record_refs),
        "searchable_asset_count": len(evidence_assets),
        "source_file_count": manifest.get("source_file_count"),
        "unique_source_count": len(entries),
        "evidence_bundle_count": len(entries),
        "validated_bundle_count": len(bundle_jobs) if validate_bundles else 0,
        "bundle_validation_workers": worker_count,
        "canonical_evidence_count": canonical_count,
        "excluded_noncanonical_count": excluded_count,
        "catalog_thumbnail_count": len(declared_thumbnails),
        "standalone_raster_count": len(standalone_rasters),
        "symlink_count": len(symlinks),
    }
    return {"ok": not errors, "errors": errors, "warnings": warnings, "stats": stats}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "root",
        nargs="?",
        help="The root of the pack that owns the reference corpus.",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--require-bundles", action="store_true")
    group.add_argument("--index-only", action="store_true")
    parser.add_argument(
        "--workers",
        type=worker_argument,
        default=1,
        help="explicit positive worker request; execution is capped at two (default: 1)",
    )
    args = parser.parse_args()
    require: bool | None
    if args.require_bundles:
        require = True
    elif args.index_only:
        require = False
    else:
        require = None
    report = validate(
        Path(args.root) if args.root else None,
        require_bundles=require,
        workers=args.workers,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
