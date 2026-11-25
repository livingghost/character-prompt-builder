#!/usr/bin/env python3
"""Rebuild core release metadata from explicitly configured default packs."""
from __future__ import annotations
import operation_context as _operation_context

import argparse
import json
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Sequence

from execution_contract import atomic, digest, local, sha256_file
from integration_contract import (
    content_hash,
    profile_hash,
    validate_capabilities,
)
from package_metadata import (
    LICENSE_ID,
    PACKAGE_NAME,
    PACKAGE_VERSION,
    VERSION_SCHEME,
    RELEASE_TIMEZONE,
    PACKAGE_DESCRIPTION,
    host_manifests,
    iter_release_files,
    load_package_metadata,
)

ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, data: Any) -> None:
    write_text_atomic(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


# When this holds a mapping, every generated artifact is collected here instead
# of written. The generation is the same either way, which is what makes the
# comparison meaningful.
_CAPTURED: dict[Path, str] | None = None
_REMOVED: set[Path] = set()


def write_text_atomic(path: Path, text: str) -> None:
    path = Path(path)
    if _CAPTURED is not None:
        _CAPTURED[path] = text
        return
    atomic(path, text.encode("utf-8"), replace=True)


REPOSITORY_GUIDE_TEMPLATE = "hosts/shared/repository-guide.md.template"
# A host reads one name or the other and never both, so the two outputs are the
# same document under two names. Two templates would drift, and the drift would
# be invisible to whichever host reads only one of them.
REPOSITORY_GUIDES = ("AGENTS.md", "CLAUDE.md")
REPOSITORY_GUIDE_MAX_BYTES = 32000


def rebuild_repository_guides() -> list[str]:
    template = (ROOT / REPOSITORY_GUIDE_TEMPLATE).read_text(encoding="utf-8")
    rendered = template.format(
        name=PACKAGE_NAME, version=PACKAGE_VERSION, description=PACKAGE_DESCRIPTION
    )
    if len(rendered.encode("utf-8")) > REPOSITORY_GUIDE_MAX_BYTES:
        raise ValueError("repository guides exceed 32000 bytes; preserve their requirements when editing the template")
    for relative in REPOSITORY_GUIDES:
        write_text_atomic(ROOT / relative, rendered)
    return list(REPOSITORY_GUIDES)


def rebuild_knowledge_documents() -> list[str]:
    """Render human and host documents from their authoritative section records."""
    from knowledge_document_build import generated_documents

    outputs, obsolete = generated_documents(ROOT)
    for relative, raw in outputs.items():
        write_text_atomic(ROOT / relative, raw.decode("utf-8"))
    for relative in obsolete:
        path = local(ROOT, relative, exists=False)
        if _CAPTURED is not None:
            _REMOVED.add(path)
        else:
            path.unlink()
    return sorted(outputs)


def manifest_file_records(files: Iterable[Path]) -> list[dict]:
    """Describe the generated tree, including captured outputs and removals."""
    paths = set(files) - _REMOVED
    if _CAPTURED is not None:
        paths.update(_CAPTURED)
    paths.discard(ROOT / "MANIFEST.json")
    records = []
    for path in sorted(paths, key=lambda value: value.relative_to(ROOT).as_posix()):
        captured = _CAPTURED.get(path) if _CAPTURED is not None else None
        if captured is None:
            size, sha256 = path.stat().st_size, sha256_file(path)
        else:
            raw = captured.encode("utf-8")
            size, sha256 = len(raw), digest(raw)
        records.append({"path": path.relative_to(ROOT).as_posix(),
                        "bytes": size, "sha256": sha256})
    return records


def rebuild_host_manifests() -> dict[str, Any]:
    documents = host_manifests()
    for relative, value in documents.items():
        dump_json(ROOT / relative, value)
    return documents


def rebuild_implementation_index() -> list[str]:
    """Write the files a prepared run pins, computed once here from the import closure.

    The digest of each module is written beside the list, so a preparation can
    tell an index written for other sources from the current one.
    """
    import production_operations as production_workflow
    from execution_contract import sha256_file
    files = production_workflow.implementation_closure()
    sources = {path: sha256_file(ROOT / path) for path in files if path.endswith(".py")}
    dump_json(ROOT / production_workflow.IMPLEMENTATION_INDEX, {"files": files, "sources": sources})
    return files


def rebuild_integration_capabilities() -> dict[str, Any]:
    """Derive and validate capability declarations from their authored fields.

    Generation needs no already sealed installation. validate_integration.py
    checks each produced profile against the completed public contract and
    actual payloads during repository and release validation.
    """

    path = ROOT / "config" / "integration-capabilities.json"
    value = load_json(path)
    if not isinstance(value, dict):
        raise RuntimeError("integration capability manifest must be an object")
    interfaces = value.get("interfaces")
    if not isinstance(interfaces, dict) or set(interfaces) != {"produces", "consumes"}:
        raise RuntimeError("integration capability interfaces are invalid")
    for direction in ("produces", "consumes"):
        rows = interfaces.get(direction)
        if not isinstance(rows, list):
            raise RuntimeError(f"integration capability interfaces.{direction} must be an array")
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise RuntimeError(
                    f"integration capability interfaces.{direction}[{index}] must be an object"
                )
            row["profile_sha256"] = profile_hash(row)
    value["manifest_sha256"] = content_hash(value, "manifest_sha256")
    report = validate_capabilities(value)
    if not report.get("ok"):
        raise RuntimeError(
            "finalized integration capability manifest is invalid: "
            + "; ".join(report.get("errors", []))
        )
    dump_json(path, value)
    return value


def build_catalog_document(
    counts: dict[str, Any],
    tier_counts: Counter[str],
    domains: Counter[str],
    default_pack_count: int,
) -> str:
    family_rows = "\n".join(
        f"| `{name}` | {count:,} |"
        for name, count in counts["record_families"].items()
    )
    module_rows = "\n".join(
        f"| `{name}` | {count:,} |"
        for name, count in counts["module_categories"].items()
    )
    tier_rows = "\n".join(
        f"| `{name}` | {count:,} |"
        for name, count in sorted(tier_counts.items())
    )
    if default_pack_count < 1:
        raise ValueError("catalog metadata requires at least one authored default pack")
    pack_label = "pack" if default_pack_count == 1 else "packs"
    default_summary = (
        f"This index describes {default_pack_count} explicitly configured default {pack_label}."
    )
    return f"""# Catalog Index

{default_summary} User-owned and third-party packs remain outside these totals. `python scripts/pack_cli.py list` reports the active set selected by user state.

## Totals

| Record family | Count |
|---|---:|
{family_rows}
| **All default-pack records** | **{counts['total_records']:,}** |

## Record roles

| Role | Count |
|---|---:|
{tier_rows}

`curated` records contain complete production knowledge. `vocabulary` records provide compact model-legible names and options. These are different jobs, not a quality ranking.

## Atomic module categories

| Category | Count |
|---|---:|
{module_rows}

## Domains

```json
{json.dumps(dict(sorted(domains.items())), indent=2)}
```

## Runtime-derived search cache

Pack-authored records and search rows are authoritative. The active pack state is materialized in a disposable SQLite cache that refreshes automatically when pack content, activation state, or cache-builder logic changes.

Use `python scripts/catalog_cli.py inspect <record-id>` for the complete canonical record and compact linked-asset activation summary. Add `--out <path>` when the complete UTF-8 JSON record should be written instead of printed. Use `asset-lookup <record-or-asset-id> --summary` for compact asset IDs and technical roles, and full `asset-lookup` only for artifact resources, media, paths, hashes, and ownership needed by planning. Use `catalog_cli.py batch --input <json-file-or-stdin>` for several ordered queries so the active catalog and index load once. For linked visual evidence, build one record-scoped plan with `python scripts/build_reference_use_plan.py --record-use <record-id>=<intended-influence> ...`, then materialize the canonical `prepared-reference-set` before generation-package construction. Use `python scripts/pack_cli.py resource <name>` to resolve a named resource: the document merged from every enabled pack, or each pack's own copy of a pack-scoped resource. `pack_cli.py ready` and pack-changing operations maintain the selected enabled-runtime browser catalog and print or return its entry point, reusing unchanged files. For an explicit inspection or distribution scope, `python scripts/catalog_html.py --pack-tree packs --output catalog` discovers every pack below `packs/` and writes a separate split inspector. Its script-free `index.html` links to the Visual Evidence gallery, linked-preset gallery, kind browsing, pack summaries, and the separate search page. Complete records live on per-record pages, while `data/record-asset-map.json` records both canonical-record-to-Visual-Evidence and reverse relationships. See `references/maintenance/catalog-export.md`.
"""


def main(argv: Sequence[str] | None = None) -> int:
    global _CAPTURED
    _REMOVED.clear()
    parser = _operation_context.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Generate without writing and report every artifact that differs from the tree.",
    )
    arguments = parser.parse_args(argv)
    from catalog_api import canonical_domain, catalog_stats, configure_pack_runtime, load_entries, load_pack_catalog, record_tier
    from runtime_paths import PackSettings
    _CAPTURED = {} if arguments.check else None
    metadata = load_package_metadata(ROOT)
    with tempfile.TemporaryDirectory(prefix="cpb-metadata-") as temp:
        temp_root = Path(temp)
        managed_root = (temp_root / "managed").resolve()
        configure_pack_runtime(
            PackSettings(
                roots=tuple(
                    (ROOT / relative).resolve()
                    for relative in metadata.release_pack_dirs
                ),
                state_file=(temp_root / "pack-state.json").resolve(),
                cache_dir=(temp_root / "cache").resolve(),
                managed_root=managed_root,
                quarantine_root=(managed_root / ".quarantine").resolve(),
                default_enabled_packs=tuple(metadata.default_pack_ids),
            )
        )
        entries = load_entries()
        pack_catalog = load_pack_catalog()
        observed_record_packs = {entry.source_pack for entry in entries}
        expected_record_packs = set(metadata.default_pack_ids)
        if observed_record_packs != expected_record_packs:
            missing = sorted(expected_record_packs - observed_record_packs)
            unexpected = sorted(observed_record_packs - expected_record_packs)
            raise RuntimeError(
                "default release catalog must contain records from every configured "
                f"default pack and no others; missing={missing}, unexpected={unexpected}"
            )
        counts = catalog_stats(entries)
        tier_counts = Counter(record_tier(entry.record) for entry in entries)
        domains: Counter[str] = Counter()
        for entry in entries:
            values: list[str] = []
            raw = entry.record.get("domains")
            if isinstance(raw, list):
                values.extend(str(item) for item in raw)
            single = entry.record.get("domain")
            if single not in (None, ""):
                values.append(str(single))
            for value in values or ["shared"]:
                domains[canonical_domain(value)] += 1

        # The defaults the shipped packs resolve to.
        shipped_defaults = pack_catalog.resources.get("pack-defaults")
        defaults = (
            load_json(shipped_defaults.path)
            if shipped_defaults is not None and shipped_defaults.source_pack in metadata.default_pack_ids
            else {}
        )
        default_pack_count = len(metadata.default_pack_ids)
        write_text_atomic(
            ROOT / "references" / "catalog-index.md",
            build_catalog_document(counts, tier_counts, domains, default_pack_count),
        )

        rebuild_host_manifests()
        rebuild_repository_guides()
        rebuild_integration_capabilities()
        rebuild_knowledge_documents()
        rebuild_implementation_index()

        files = iter_release_files(
            ROOT,
            metadata.release_include,
            exclude_names=metadata.release_exclude_names,
        )
        file_records = manifest_file_records(files)
        manifest = {
            "package": PACKAGE_NAME,
            "version": PACKAGE_VERSION,
            "version_scheme": VERSION_SCHEME,
            "release_timezone": RELEASE_TIMEZONE,
            "generated_at": PACKAGE_VERSION.rsplit(".", 1)[0].replace(".", "-"),
            "license": LICENSE_ID,
            "language": "English project content and canonical English retrieval; user-language interpretation belongs to the calling agent",
            "purpose": "state-aware expansion of character ideas into coherent model-aware image prompts",
            "documentation": {
                "readme": "README.md",
                "contributing": "CONTRIBUTING.md",
                "license": "LICENSE",
                "package_manifest": "package-manifest.toml",
            },
            "pack_catalog": {
                "default_state": "config/default-pack-state.json",
                "default_pack_count": default_pack_count,
                "record_counts": counts,
                "tier_counts": dict(sorted(tier_counts.items())),
                "named_resources": sorted(pack_catalog.resources),
            },
            "behavior": {
                "pack_state_is_activation_authority": True,
                "environment_variable_pack_activation": False,
                "derived_cache_rebuilds_on_content_change": True,
                "search_results_require_full_inspection": True,
                "default_render_profile": defaults.get("default_render_profile"),
                "default_domain_realization_by_domain": defaults.get(
                    "default_domain_realization_by_domain", {}
                ),
            },
            "release_reports": {
                "distribution": "generated externally by scripts/package.py",
                "included_in_archive": False,
            },
            "file_count_excluding_manifest": len(file_records),
            "total_bytes_excluding_manifest": sum(item["bytes"] for item in file_records),
            "files": file_records,
        }
        dump_json(ROOT / "MANIFEST.json", manifest)
        if _CAPTURED is not None:
            captured = _CAPTURED
            _CAPTURED = None
            stale = sorted({
                path.relative_to(ROOT).as_posix()
                for path, text in captured.items()
                if not path.is_file() or path.read_bytes() != text.encode("utf-8")
            } | {path.relative_to(ROOT).as_posix() for path in _REMOVED})
            print(json.dumps({
                "ok": not stale,
                "generated_artifacts": len(captured),
                "stale": stale,
            }, ensure_ascii=False, indent=2))
            return 0 if not stale else 1
        print(
            json.dumps(
                {
                    "catalog": counts,
                    "tiers": dict(tier_counts),
                    "files": len(file_records),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(_operation_context.run_cli(main))
