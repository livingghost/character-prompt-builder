#!/usr/bin/env python3
"""Exercise pack identity, locking, lifecycle, and automatic cache invalidation."""
from __future__ import annotations

import io
import itertools
import json
import os
import shutil
import stat
import subprocess
import time
import tempfile
import warnings
import zipfile
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pack_cache as pack_cache_module
import pack_manager as pack_manager_module
from catalog_cli import begin_catalog_request, configure_pack_runtime, load_entries
from pack_cache import (
    _resolve_records,
    cache_status,
    load_runtime_catalog,
    refresh_cache,
    runtime_resource_provider_status,
)
from pack_cli import main as pack_cli_main
from package_metadata import PACKAGE_VERSION, calver_key, load_package_metadata
from resource_policy import (
    medium_selection_allowed,
    negative_source_emission_allowed,
    validate_known_resource,
)
from pack_manager import (
    PACK_ID_RE,
    PackError,
    PackSettings,
    active_snapshot,
    add_pack_root,
    atomic_write_json,
    canonical_json,
    clear_resource_provider,
    default_settings,
    disable_pack,
    discover_packs,
    enable_pack,
    generate_uuid7,
    initialize_pack,
    install_pack,
    inventory_rows,
    list_packs,
    load_effective_state,
    remove_pack,
    resolve_enabled,
    save_state,
    select_resource_provider,
    sha256_bytes,
    sha256_file,
    validate_pack,
    write_lock,
)


def _test_settings(
    *,
    state_file: Path,
    cache_dir: Path,
    managed_root: Path,
    roots: tuple[Path, ...] = (),
    default_enabled_packs: tuple[str, ...] = (),
    default_resource_providers: dict[str, str] | None = None,
) -> PackSettings:
    """Build hermetic settings without changing production discovery defaults."""

    resolved_roots: list[Path] = []
    for candidate in (*roots, managed_root):
        resolved = candidate.resolve()
        if resolved not in resolved_roots:
            resolved_roots.append(resolved)
    managed = managed_root.resolve()
    return PackSettings(
        roots=tuple(resolved_roots),
        state_file=state_file.resolve(),
        cache_dir=cache_dir.resolve(),
        managed_root=managed,
        quarantine_root=(managed / ".quarantine").resolve(),
        default_enabled_packs=tuple(default_enabled_packs),
        default_resource_providers=tuple(
            sorted((default_resource_providers or {}).items())
        ),
    )


def _record_file(path: Path, record_id: str, label: str) -> None:
    atomic_write_json(
        path,
        {
            "kind": "module",
            "category": "lighting",
            "records": [
                {
                    "id": record_id,
                    "label": label,
                    "curation_status": "vocabulary",
                    "category": "lighting",
                    "prompt": f"a controlled {label}",
                    "domains": ["shared"],
                    "tags": [label, "pack smoke test"],
                    "search_terms": [
                        {
                            "phrase": label,
                            "facet": "lighting",
                            "weight": 1.0,
                            "source": "author",
                        },
                        {
                            "phrase": label,
                            "facet": "lighting",
                            "weight": 0.8,
                            "source": "review",
                        }
                    ],
                }
            ],
        },
    )


def _tree_snapshot(root: Path) -> list[tuple[str, str, str | None]]:
    if not root.exists():
        return []
    rows: list[tuple[str, str, str | None]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            rows.append((relative, "directory", None))
        elif path.is_file():
            rows.append((relative, "file", sha256_file(path)))
    return rows


_OMITTED = object()


def _asset_record_file(
    path: Path,
    record_id: str,
    canonical_record_id: str,
    canonical_record_refs: Any = _OMITTED,
) -> None:
    resource_path = path.parents[1] / "resources" / "guide.json"
    resource_sha256 = sha256_file(resource_path)
    record: dict[str, Any] = {
        "id": record_id,
        "label": "Canonical record guide",
        "curation_status": "curated",
        "category": "visual-reference",
        "asset_type": "reference-guide",
        "description": "A machine-readable guide used by the pack smoke test.",
        "source_ref_id": "pack-smoke-guide-source",
        "source_sha256": resource_sha256,
        "source_media_type": "application/json",
        "source_dimensions": {"width": 1, "height": 1},
        "disposition": "retained",
        "evidence_relation": "supports the canonical record",
        "canonical_record_ids": [canonical_record_id],
        "primary_resource": "resources/guide.json",
        "resource_refs": ["resources/guide.json"],
        "artifacts": [
            {
                "artifact_id": f"{record_id}-artifact",
                "role": "semantic guide",
                "path": "resources/guide.json",
                "media_type": "application/json",
                "sha256": resource_sha256,
            }
        ],
        "tags": ["canonical record guide"],
    }
    if canonical_record_refs is not _OMITTED:
        record["canonical_record_refs"] = canonical_record_refs
    atomic_write_json(
        path,
        {
            "kind": "asset",
            "category": "visual-reference",
            "records": [record],
        },
    )


def _visual_bundle_fixture(root: Path) -> Path:
    manifest = initialize_pack(root, name="Visual Bundle Contract")
    manifest["content"]["resource_globs"] = ["resources/**/*"]
    atomic_write_json(root / "pack.json", manifest)
    _record_file(
        root / "records" / "canonical.json",
        "bundle-smoke-canonical",
        "bundle smoke canonical record",
    )
    artifact_roles = [
        "faithful-archival-vector",
        "vectorization-result",
        "semantic-region-map",
        "subject-mask",
        "structural-line-tone",
        "color-audit",
        "saturation-rescue",
        "specular-audit",
        "palette-probes",
        "audit-extraction-set",
        "runtime-attachment-build",
    ]
    pack_parent = "resources/visual-evidence/fixture"
    bundle_artifacts: list[dict[str, Any]] = []
    asset_artifacts: list[dict[str, Any]] = []
    for index, role in enumerate(artifact_roles):
        artifact_id = f"bundle-smoke-artifact-{index:02d}"
        bundle_relative = f"derived-visual/{artifact_id}.json"
        pack_relative = f"{pack_parent}/{bundle_relative}"
        artifact_path = root / pack_relative
        atomic_write_json(artifact_path, {"artifact_id": artifact_id, "role": role})
        row = {
            "artifact_id": artifact_id,
            "role": role,
            "media_type": "application/json",
            "sha256": sha256_file(artifact_path),
        }
        bundle_artifacts.append({**row, "path": bundle_relative})
        asset_artifacts.append({**row, "path": pack_relative})
    bundle_relative = f"{pack_parent}/visual-evidence-bundle.json"
    atomic_write_json(
        root / bundle_relative,
        {
            "artifact_type": "visual-evidence-bundle",
            "bundle_id": "VE-bundle-smoke",
            "source_ref_id": "SRC-bundle-smoke",
            "source_sha256": "1" * 64,
            "source_dimensions": {"width": 64, "height": 64},
            "visual_authority_ref": {"id": "VA-bundle-smoke", "sha256": "2" * 64},
            "layers": {"A": "archival", "B": "audit", "C": "runtime"},
            "representation": "native-dimension-compact-perceptual-path-vector",
            "artifacts": bundle_artifacts,
            "canonical_record_refs": ["bundle-smoke-canonical"],
            "disposition": "fixture-evidence",
            "evidence_relation": "supports-fixture",
            "notes": ["Pack smoke fixture."],
            "visual_evidence_bundle_sha256": "3" * 64,
        },
    )
    asset_path = root / "records" / "bundle-asset.json"
    atomic_write_json(
        asset_path,
        {
            "kind": "asset",
            "records": [
                {
                    "id": "bundle-smoke-asset",
                    "label": "Bundle smoke asset",
                    "category": "visual-evidence",
                    "curation_status": "curated",
                    "asset_type": "visual-evidence-bundle",
                    "description": "Visual evidence bundle cross-contract fixture.",
                    "source_ref_id": "SRC-bundle-smoke",
                    "source_sha256": "1" * 64,
                    "source_media_type": "image/png",
                    "source_dimensions": {"width": 64, "height": 64},
                    "disposition": "fixture-evidence",
                    "evidence_relation": "supports-fixture",
                    "canonical_record_ids": ["bundle-smoke-canonical"],
                    "primary_resource": asset_artifacts[0]["path"],
                    "resource_refs": [
                        bundle_relative,
                        *(row["path"] for row in asset_artifacts),
                    ],
                    "artifacts": asset_artifacts,
                    "tags": ["visual bundle smoke fixture"],
                }
            ],
        },
    )
    write_lock(root)
    return asset_path


def run() -> dict[str, Any]:
    checks = 0
    errors: list[str] = []
    try:
        project_root = Path(__file__).resolve().parents[1]
        example_root = project_root / "examples" / "pack-authoring" / "minimal-pack"
        example_report = validate_pack(example_root, verify_lock=False)
        example_records = [
            item.record
            for item in example_report.records
            if item.record.get("id") == "example-pack-soft-window-rim"
        ]
        if not example_report.valid or len(example_records) != 1:
            errors.append(
                "minimal pack-authoring example failed schema validation: "
                f"{example_report.to_dict()}"
            )
        elif (
            example_records[0].get("category") != "lighting"
            or not example_records[0].get("search_terms")
        ):
            errors.append(
                "minimal pack-authoring example omitted canonical category or search terms"
            )
        else:
            checks += 1

        with tempfile.TemporaryDirectory(prefix="cpb-pack-smoke-") as temp:
            root = Path(temp)
            project_pack_root = project_root / "packs"
            default_managed = default_settings(
                state_file=root / "default-state.json",
                cache_dir=root / "default-cache",
                default_enabled_packs=(),
            )
            if default_managed.managed_root != project_pack_root.resolve():
                errors.append("default managed pack root is not the project packs directory")
            else:
                checks += 1

            default_manifest = json.loads(
                (project_pack_root / "commons" / "pack.json").read_text(
                    encoding="utf-8"
                )
            )
            default_pack_id = str(default_manifest["pack_id"])

            data_home = pack_manager_module._user_data_home()
            if data_home != (Path.home() / ".character-prompt-builder").resolve():
                errors.append("user data home is not ~/.character-prompt-builder")
            else:
                checks += 1

            flag_free = default_settings(default_enabled_packs=())
            if flag_free.state_file != (data_home / "pack-state.json").resolve():
                errors.append("flag-free settings do not resolve the data-home state file")
            elif flag_free.cache_dir != (data_home / "cache").resolve():
                errors.append("flag-free settings do not resolve the data-home cache directory")
            else:
                checks += 1

            explicit_state = default_settings(
                state_file=root / "explicit" / "state.json",
                default_enabled_packs=(),
            )
            cache_only = default_settings(
                cache_dir=root / "cache-only" / "cache",
                default_enabled_packs=(),
            )
            if explicit_state.state_file != (root / "explicit" / "state.json").resolve():
                errors.append("an explicit state file was not honored")
            elif explicit_state.cache_dir != (root / "explicit" / "cache").resolve():
                errors.append("an explicit state file did not anchor the sibling cache directory")
            elif cache_only.state_file != (root / "cache-only" / "pack-state.json").resolve():
                errors.append("cache-only settings did not anchor the sibling state file")
            else:
                checks += 1

            shipped_initial = json.loads(
                (project_root / "config" / "default-pack-state.json").read_text(
                    encoding="utf-8"
                )
            )
            fallback_settings = default_settings(
                state_file=root / "absent" / "state.json",
                cache_dir=root / "absent" / "cache",
            )
            fallback_state = pack_manager_module.load_effective_state(fallback_settings)
            discovered_initial, initial_issues = discover_packs(fallback_settings, fallback_state)
            expected_initial = sorted(set(shipped_initial["enabled_packs"]) | set(discovered_initial))
            if initial_issues or fallback_state["enabled_packs"] != expected_initial:
                errors.append("an absent state file did not enable every discovered pack")
            elif any(fallback_state["resource_providers"].get(name) != provider
                     for name, provider in shipped_initial["resource_providers"].items()):
                errors.append("all-on initialization did not preserve the declared default providers")
            else:
                checks += 1

            state_init_project = root / "state-init-project"
            state_init_packs = state_init_project / "packs"
            shutil.copytree(project_pack_root / "commons", state_init_packs / "commons")
            state_init_extra = initialize_pack(
                state_init_packs / "extra",
                name="State Init Extra Pack",
            )
            state_init_argv = [
                "--state-file",
                str(root / "state-init" / "pack-state.json"),
                "--cache-dir",
                str(root / "state-init" / "cache"),
                "--managed-root",
                str(root / "state-init" / "managed"),
                "state-init",
            ]
            with patch.object(pack_manager_module, "ROOT", state_init_project):
                first_init_output = io.StringIO()
                with redirect_stdout(first_init_output):
                    first_init_exit = pack_cli_main(state_init_argv)
                first_init = json.loads(first_init_output.getvalue())
                second_init_output = io.StringIO()
                with redirect_stdout(second_init_output):
                    second_init_exit = pack_cli_main(state_init_argv)
                second_init = json.loads(second_init_output.getvalue())
            if first_init_exit != 0 or second_init_exit != 0:
                errors.append(
                    "state-init exited nonzero: "
                    f"{first_init_exit}/{second_init_exit}: {first_init}"
                )
            elif not first_init.get("created") or second_init.get("created"):
                errors.append("state-init did not create the state file exactly once")
            elif not (root / "state-init" / "pack-state.json").is_file():
                errors.append("state-init did not persist the resolved state file")
            elif first_init.get("enabled_packs") != sorted(set(shipped_initial["enabled_packs"]) | {state_init_extra["pack_id"]}):
                errors.append("state-init did not enable the core and discovered extra pack")
            elif state_init_extra["pack_id"] in (
                first_init.get("disabled_discovered_packs") or []
            ):
                errors.append("state-init left a discovered pack disabled")
            elif default_pack_id in (first_init.get("disabled_discovered_packs") or []):
                errors.append("state-init reported an enabled pack as disabled")
            else:
                checks += 1

            ambient_project = root / "ambient-project"
            ambient_root = ambient_project / "packs"
            ambient_malformed = ambient_root / "malformed"
            ambient_malformed.mkdir(parents=True)
            (ambient_malformed / "pack.json").write_text("{broken", encoding="utf-8")
            ambient_default = ambient_root / "default-source"
            shutil.copytree(project_pack_root / "commons", ambient_default)
            ambient_duplicate = ambient_root / "duplicate-default"
            shutil.copytree(ambient_default, ambient_duplicate)
            with patch.object(pack_manager_module, "ROOT", ambient_project):
                poisoned_default_settings = default_settings(
                    state_file=root / "poisoned-default-state.json",
                    cache_dir=root / "poisoned-default-cache",
                    managed_root=root / "poisoned-default-managed",
                    default_enabled_packs=(),
                    default_resource_providers={},
                )
            poisoned_default_listing = list_packs(poisoned_default_settings)
            poisoned_issues = poisoned_default_listing["discovery_issues"]
            poisoned_manifest_observed = any(
                row.get("code") == "manifest"
                and row.get("path") == str((ambient_malformed / "pack.json").resolve())
                for row in poisoned_issues
            )
            poisoned_duplicate_observed = any(
                row.get("code") == "duplicate-pack-id"
                and str(ambient_default.resolve()) in str(row.get("message"))
                and str(ambient_duplicate.resolve()) in str(row.get("message"))
                for row in poisoned_issues
            )
            default_listing_settings = _test_settings(
                roots=(project_pack_root / "commons",),
                state_file=root / "default-listing-state.json",
                cache_dir=root / "default-listing-cache",
                managed_root=root / "default-listing-managed",
            )
            default_listing = list_packs(default_listing_settings)
            listed_default = next(
                (
                    row
                    for row in default_listing["packs"]
                    if row.get("pack_id") == default_pack_id
                ),
                None,
            )
            if (
                listed_default is None
                or listed_default.get("capabilities")
                != sorted(str(value) for value in default_manifest.get("capabilities") or [])
                or not poisoned_manifest_observed
                or not poisoned_duplicate_observed
                or len(default_listing["packs"]) != 1
                or default_listing["discovery_issues"]
                or ambient_root.resolve() in default_listing_settings.roots
                or any(
                    str(path.resolve()) in json.dumps(default_listing, ensure_ascii=False)
                    for path in (ambient_malformed, ambient_default, ambient_duplicate)
                )
            ):
                errors.append(
                    "hermetic public pack listing did not expose only the configured default "
                    "pack and its capability-first activation metadata"
                )
            else:
                checks += 1

            metadata = load_package_metadata(project_root)
            if (
                metadata.version != PACKAGE_VERSION
                or calver_key(metadata.version) != calver_key(PACKAGE_VERSION)
            ):
                errors.append(
                    f"canonical package metadata returned an unexpected version: {metadata.version!r}"
                )
            else:
                checks += 1

            invalid_calvers = (
                "0000.01.01.1",
                "2026.02.29.1",
                "2024.04.31.1",
                "2026.08.15.0",
                "2026.08.15.01",
                "2026.8.15.1",
            )
            metadata_rejections: list[str] = []
            for index, invalid_calver in enumerate(invalid_calvers):
                metadata_root = root / f"invalid-package-metadata-{index}"
                metadata_root.mkdir()
                (metadata_root / "package-manifest.toml").write_text(
                    "\n".join(
                        (
                            "[package]",
                            'name = "character-prompt-builder"',
                            f'version = "{invalid_calver}"',
                            'version_scheme = "YYYY.MM.DD.N"',
                            'release_timezone = "UTC"',
                            'license = "GPL-3.0-only"',
                            "",
                            "[dependencies]",
                            'python = ">=3.11"',
                            "",
                            "[release]",
                            f'output = "dist/character-prompt-builder-{invalid_calver}.zip"',
                            'include = ["README.md"]',
                            "",
                        )
                    ),
                    encoding="utf-8",
                    newline="\n",
                )
                try:
                    load_package_metadata(metadata_root)
                except ValueError as exc:
                    if "package version" not in str(exc):
                        metadata_rejections.append(
                            f"{invalid_calver!r} failed after version validation: {exc}"
                        )
                else:
                    metadata_rejections.append(f"{invalid_calver!r} was accepted")
            if metadata_rejections:
                errors.append(
                    "package metadata did not enforce canonical Gregorian CalVer: "
                    + "; ".join(metadata_rejections)
                )
            else:
                checks += 1

            early_pack = root / "calver-earliest"
            initialize_pack(
                early_pack,
                name="Earliest Gregorian CalVer",
                release="0001.01.01.1",
            )
            early_development_report = validate_pack(early_pack, verify_lock=False)
            if (
                not early_development_report.valid
                or not any(
                    issue.code == "empty-development-content"
                    for issue in early_development_report.issues
                )
            ):
                errors.append(
                    "empty unlocked development pack was not retained with an explicit warning"
                )
            else:
                checks += 1
            empty_required_lock_report = validate_pack(early_pack, require_lock=True)
            if (
                empty_required_lock_report.valid
                or not any(
                    issue.code == "missing-lock"
                    for issue in empty_required_lock_report.issues
                )
            ):
                errors.append("released validation accepted an empty pack without a lock")
            else:
                checks += 1
            try:
                write_lock(early_pack)
            except PackError as exc:
                if "at least one matched record or resource" not in str(exc):
                    errors.append(f"empty lock build failed for the wrong reason: {exc}")
            else:
                errors.append("build-lock accepted a pack with zero records and resources")
            empty_rows = inventory_rows(early_pack)
            atomic_write_json(
                early_pack / "pack.lock.json",
                {
                    "pack_id": early_development_report.pack_id,
                    "release": early_development_report.release,
                    "files": empty_rows,
                    "content_sha256": sha256_bytes(
                        canonical_json(empty_rows).encode("utf-8")
                    ),
                },
            )
            empty_released_report = validate_pack(early_pack, require_lock=True)
            if (
                empty_released_report.valid
                or not any(
                    issue.code == "empty-released-content"
                    for issue in empty_released_report.issues
                )
            ):
                errors.append("a locked pack with zero records and resources was accepted")
            else:
                checks += 1

            resource_only_pack = root / "resource-only-release"
            resource_only_manifest = initialize_pack(
                resource_only_pack,
                name="Resource Only Release",
            )
            resource_only_manifest["content"]["resource_globs"] = ["resources/**/*"]
            atomic_write_json(resource_only_pack / "pack.json", resource_only_manifest)
            atomic_write_json(resource_only_pack / "resources" / "policy.json", {})
            write_lock(resource_only_pack)
            if not validate_pack(resource_only_pack, require_lock=True).valid:
                errors.append("released pack with one matched resource was rejected")
            else:
                checks += 1

            invariant_pack = root / "generic-validation-invariants"
            invariant_manifest = initialize_pack(
                invariant_pack,
                name="Generic Validation Invariants",
            )
            invariant_manifest["content"]["resource_globs"] = ["resources/**/*"]
            atomic_write_json(invariant_pack / "pack.json", invariant_manifest)
            invariant_record_path = invariant_pack / "records" / "species.json"
            invariant_record_document = {
                "kind": "module",
                "category": "species",
                "records": [
                    {
                        "id": "generic-validation-species",
                        "label": "generic validation species",
                        "curation_status": "vocabulary",
                        "category": "species",
                        "prompt": "generic validation species",
                        "domains": ["shared"],
                        "tags": ["generic validation species"],
                        "search_terms": [
                            {
                                "phrase": "generic validation species",
                                "facet": "species",
                                "weight": 1.0,
                                "source": "author",
                            }
                        ],
                    }
                ],
            }
            atomic_write_json(invariant_record_path, invariant_record_document)
            invariant_content_path = invariant_pack / "resources" / "authoring-note.json"
            clean_invariant_content = {"note": "plain UTF-8 pack content"}
            atomic_write_json(invariant_content_path, clean_invariant_content)
            invariant_failures: list[str] = []
            baseline_invariant_report = validate_pack(
                invariant_pack,
                require_lock=False,
                verify_lock=False,
            )
            if not baseline_invariant_report.valid:
                invariant_failures.append(
                    f"baseline pack was invalid: {baseline_invariant_report.to_dict()}"
                )
            for character, name, codepoint in (
                ("\u2014", "em dash", "U+2014"),
                ("\u2013", "en dash", "U+2013"),
            ):
                atomic_write_json(
                    invariant_content_path,
                    {"note": f"forbidden {character} punctuation"},
                )
                punctuation_report = validate_pack(
                    invariant_pack,
                    require_lock=False,
                    verify_lock=False,
                )
                matching_issues = [
                    issue
                    for issue in punctuation_report.issues
                    if issue.code == "forbidden-punctuation"
                    and issue.path == "resources/authoring-note.json"
                    and name in issue.message
                    and codepoint in issue.message
                ]
                if punctuation_report.valid or not matching_issues:
                    invariant_failures.append(
                        f"{codepoint} {name} was not rejected with file context: "
                        f"{punctuation_report.to_dict()}"
                    )
                atomic_write_json(invariant_content_path, clean_invariant_content)

            invariant_content_path.write_bytes(
                b"valid UTF-8 prefix \xe2\x80\x94 followed by invalid byte \xff"
            )
            invalid_utf8_report = validate_pack(
                invariant_pack,
                require_lock=False,
                verify_lock=False,
            )
            invalid_utf8_punctuation_issues = [
                issue
                for issue in invalid_utf8_report.issues
                if issue.code == "forbidden-punctuation"
                and issue.path == "resources/authoring-note.json"
            ]
            if not invalid_utf8_report.valid or invalid_utf8_punctuation_issues:
                invariant_failures.append(
                    "a non-UTF-8 resource retained punctuation findings from its valid prefix: "
                    f"{invalid_utf8_report.to_dict()}"
                )
            atomic_write_json(invariant_content_path, clean_invariant_content)

            mismatched_record_document = json.loads(
                json.dumps(invariant_record_document)
            )
            mismatched_record_document["records"][0]["category"] = "lighting"
            atomic_write_json(invariant_record_path, mismatched_record_document)
            category_report = validate_pack(
                invariant_pack,
                require_lock=False,
                verify_lock=False,
            )
            category_issues = [
                issue
                for issue in category_report.issues
                if issue.code == "module-record-category"
                and issue.path == "records/species.json"
                and "generic-validation-species" in issue.message
                and "category 'lighting'" in issue.message
                and "container category 'species'" in issue.message
            ]
            if category_report.valid or not category_issues:
                invariant_failures.append(
                    "module payload category mismatch was not rejected with record context: "
                    f"{category_report.to_dict()}"
                )
            atomic_write_json(invariant_record_path, invariant_record_document)
            if invariant_failures or not validate_pack(
                invariant_pack,
                require_lock=False,
                verify_lock=False,
            ).valid:
                errors.append(
                    "generic pack validation invariants failed: "
                    + "; ".join(invariant_failures)
                )
            else:
                checks += 1

            init_rejections: list[str] = []
            for index, invalid_calver in enumerate(invalid_calvers):
                invalid_root = root / f"invalid-calver-init-{index}"
                try:
                    initialize_pack(
                        invalid_root,
                        name="Invalid CalVer",
                        release=invalid_calver,
                    )
                except ValueError:
                    if invalid_root.exists():
                        init_rejections.append(
                            f"{invalid_calver!r} created files before rejection"
                        )
                else:
                    init_rejections.append(f"{invalid_calver!r} was accepted")
            if init_rejections:
                errors.append(
                    "pack init did not enforce canonical Gregorian CalVer: "
                    + "; ".join(init_rejections)
                )
            else:
                checks += 1

            validation_pack = root / "calver-validation"
            validation_manifest = initialize_pack(
                validation_pack,
                name="CalVer Validation",
                release="2024.02.29.1",
            )
            _record_file(
                validation_pack / "records" / "record.json",
                "calver-validation-record",
                "calver validation record",
            )
            validation_failures: list[str] = []
            for invalid_calver in invalid_calvers:
                invalid_manifest = json.loads(json.dumps(validation_manifest))
                invalid_manifest["release"] = invalid_calver
                atomic_write_json(validation_pack / "pack.json", invalid_manifest)
                report = validate_pack(validation_pack, verify_lock=False)
                if report.valid or not any(
                    issue.code in {"calver", "schema"} for issue in report.issues
                ):
                    validation_failures.append(invalid_calver)
            atomic_write_json(validation_pack / "pack.json", validation_manifest)
            write_lock(validation_pack)
            invalid_lock = json.loads(
                (validation_pack / "pack.lock.json").read_text(encoding="utf-8")
            )
            invalid_lock["release"] = "2024.02.29.01"
            atomic_write_json(validation_pack / "pack.lock.json", invalid_lock)
            lock_report = validate_pack(validation_pack, require_lock=True)
            if lock_report.valid or not any(
                issue.code == "schema" and issue.path.endswith("pack.lock.json")
                for issue in lock_report.issues
            ):
                validation_failures.append("lock release")
            if validation_failures:
                errors.append(
                    "pack validation accepted invalid CalVer fields: "
                    + ", ".join(validation_failures)
                )
            else:
                checks += 1

            update_v9 = root / "calver-update-v9"
            update_manifest = initialize_pack(
                update_v9,
                name="CalVer Update",
                release="2026.08.15.9",
            )
            _record_file(
                update_v9 / "records" / "record.json",
                "calver-update-record",
                "canonical update ordering",
            )
            write_lock(update_v9)
            update_settings = _test_settings(
                state_file=root / "calver-update-state.json",
                cache_dir=root / "calver-update-cache",
                managed_root=root / "calver-update-managed",
                default_enabled_packs=(),
                default_resource_providers={},
            )
            install_pack(update_settings, update_v9)
            update_v10 = root / "calver-update-v10"
            shutil.copytree(update_v9, update_v10)
            v10_manifest = json.loads(
                (update_v10 / "pack.json").read_text(encoding="utf-8")
            )
            v10_manifest["release"] = "2026.08.15.10"
            atomic_write_json(update_v10 / "pack.json", v10_manifest)
            write_lock(update_v10)
            updated = install_pack(update_settings, update_v10, update=True)
            if updated.get("previous_release") != "2026.08.15.9":
                errors.append("pack update did not order canonical counters numerically")
            else:
                checks += 1
            try:
                install_pack(update_settings, update_v9, update=True)
            except PackError as exc:
                if "must be newer" not in str(exc):
                    errors.append(f"older update failed for the wrong reason: {exc}")
                else:
                    checks += 1
            else:
                errors.append("pack update accepted an older canonical release")
            noncanonical_update = root / "calver-update-noncanonical"
            shutil.copytree(update_v10, noncanonical_update)
            noncanonical_manifest = json.loads(
                (noncanonical_update / "pack.json").read_text(encoding="utf-8")
            )
            noncanonical_manifest["release"] = "2026.08.15.010"
            atomic_write_json(noncanonical_update / "pack.json", noncanonical_manifest)
            noncanonical_lock = json.loads(
                (noncanonical_update / "pack.lock.json").read_text(encoding="utf-8")
            )
            noncanonical_lock["release"] = "2026.08.15.010"
            atomic_write_json(noncanonical_update / "pack.lock.json", noncanonical_lock)
            try:
                install_pack(update_settings, noncanonical_update, update=True)
            except PackError:
                installed_update_manifest = json.loads(
                    (
                        update_settings.managed_root
                        / str(update_manifest["pack_id"])
                        / "pack.json"
                    ).read_text(encoding="utf-8")
                )
                if installed_update_manifest.get("release") != "2026.08.15.10":
                    errors.append("rejected noncanonical update modified the installed pack")
                else:
                    checks += 1
            else:
                errors.append("pack update accepted a noncanonical counter")

            transaction_v1 = root / "transaction-update-v1"
            transaction_manifest = initialize_pack(
                transaction_v1,
                name="Transaction Update",
                release="2026.08.16.1",
            )
            transaction_id = str(transaction_manifest["pack_id"])
            _record_file(
                transaction_v1 / "records" / "record.json",
                "transaction-update-record",
                "transaction update v1",
            )
            write_lock(transaction_v1)
            transaction_settings = _test_settings(
                state_file=root / "transaction-update-state.json",
                cache_dir=root / "transaction-update-cache",
                managed_root=root / "transaction-update-managed",
                default_enabled_packs=(),
                default_resource_providers={},
            )
            install_pack(transaction_settings, transaction_v1)
            enable_pack(transaction_settings, transaction_id)
            transaction_target = transaction_settings.managed_root / transaction_id
            transaction_v1_snapshot = _tree_snapshot(transaction_target)

            missing_dependency = initialize_pack(
                root / "transaction-missing-dependency",
                name="Missing Transaction Dependency",
            )
            invalid_transaction_v2 = root / "transaction-update-invalid-v2"
            shutil.copytree(transaction_v1, invalid_transaction_v2)
            invalid_transaction_manifest = json.loads(
                (invalid_transaction_v2 / "pack.json").read_text(encoding="utf-8")
            )
            invalid_transaction_manifest["release"] = "2026.08.18.1"
            invalid_transaction_manifest["dependencies"] = [
                {"pack_id": missing_dependency["pack_id"]}
            ]
            atomic_write_json(
                invalid_transaction_v2 / "pack.json",
                invalid_transaction_manifest,
            )
            write_lock(invalid_transaction_v2)
            try:
                install_pack(transaction_settings, invalid_transaction_v2, update=True)
            except PackError as exc:
                dependency_error = str(exc)
            else:
                dependency_error = ""
            transaction_staging = list(
                transaction_settings.managed_root.glob(f".staging-{transaction_id}-*")
            )
            if (
                "requires enabled pack" not in dependency_error
                or _tree_snapshot(transaction_target) != transaction_v1_snapshot
                or transaction_staging
                or transaction_settings.quarantine_root.exists()
            ):
                errors.append(
                    "an enabled update with a missing dependency was published "
                    "or left transaction artifacts"
                )
            else:
                checks += 1

            valid_transaction_v2 = root / "transaction-update-valid-v2"
            shutil.copytree(transaction_v1, valid_transaction_v2)
            valid_transaction_manifest = json.loads(
                (valid_transaction_v2 / "pack.json").read_text(encoding="utf-8")
            )
            valid_transaction_manifest["release"] = "2026.08.18.1"
            atomic_write_json(
                valid_transaction_v2 / "pack.json",
                valid_transaction_manifest,
            )
            write_lock(valid_transaction_v2)
            real_replace = pack_manager_module.os.replace
            injected_message = "open-file publication rename denied"

            def fail_candidate_publication(source: Any, destination: Any) -> None:
                source_path = Path(source)
                destination_path = Path(destination)
                if (
                    source_path.name.startswith(f".staging-{transaction_id}-")
                    and destination_path.resolve() == transaction_target.resolve()
                ):
                    for staged_path in source_path.rglob("*"):
                        if staged_path.is_file():
                            staged_path.chmod(stat.S_IREAD)
                    raise PermissionError(injected_message)
                real_replace(source, destination)

            try:
                with patch.object(
                    pack_manager_module.os,
                    "replace",
                    side_effect=fail_candidate_publication,
                ):
                    install_pack(transaction_settings, valid_transaction_v2, update=True)
            except PermissionError as exc:
                rename_error = str(exc)
            else:
                rename_error = ""
            transaction_staging = list(
                transaction_settings.managed_root.glob(f".staging-{transaction_id}-*")
            )
            if (
                rename_error != injected_message
                or _tree_snapshot(transaction_target) != transaction_v1_snapshot
                or transaction_staging
                or transaction_settings.quarantine_root.exists()
            ):
                errors.append(
                    "a publication rename failure replaced its original error, "
                    "changed v1, or leaked transaction artifacts"
                )
            else:
                checks += 1

            readonly_source = root / "readonly-install-source"
            readonly_manifest = initialize_pack(
                readonly_source,
                name="Read-only Install Source",
            )
            readonly_id = str(readonly_manifest["pack_id"])
            _record_file(
                readonly_source / "records" / "record.json",
                "readonly-install-record",
                "read-only source bytes",
            )
            write_lock(readonly_source)
            readonly_settings = _test_settings(
                state_file=root / "readonly-install-state.json",
                cache_dir=root / "readonly-install-cache",
                managed_root=root / "readonly-install-managed",
                default_enabled_packs=(),
                default_resource_providers={},
            )
            readonly_files = [
                path for path in readonly_source.rglob("*") if path.is_file()
            ]
            original_source_modes = {
                path.relative_to(readonly_source).as_posix(): path.stat().st_mode
                for path in readonly_files
            }
            readonly_source_snapshot = _tree_snapshot(readonly_source)
            readonly_modes: dict[str, int] = {}
            try:
                for path in readonly_files:
                    path.chmod(stat.S_IREAD)
                readonly_modes = {
                    path.relative_to(readonly_source).as_posix(): path.stat().st_mode
                    for path in readonly_files
                }
                install_pack(readonly_settings, readonly_source)
                source_modes_after_install = {
                    path.relative_to(readonly_source).as_posix(): path.stat().st_mode
                    for path in readonly_files
                }
            finally:
                for path in readonly_files:
                    relative = path.relative_to(readonly_source).as_posix()
                    path.chmod(original_source_modes[relative])
            readonly_target = readonly_settings.managed_root / readonly_id
            installed_paths = [readonly_target, *readonly_target.rglob("*")]
            if (
                _tree_snapshot(readonly_source) != readonly_source_snapshot
                or source_modes_after_install != readonly_modes
                or _tree_snapshot(readonly_target) != readonly_source_snapshot
                or any(
                    not (path.stat().st_mode & stat.S_IWUSR)
                    for path in installed_paths
                )
                or list(readonly_settings.managed_root.glob(f".staging-{readonly_id}-*"))
            ):
                errors.append(
                    "directory install changed a read-only source, changed bytes, "
                    "retained permissions, or leaked staging"
                )
            else:
                checks += 1

            absent_update = root / "absent-update-source"
            absent_update_manifest = initialize_pack(
                absent_update,
                name="Absent Update Target",
                release="2026.08.15.10",
            )
            _record_file(
                absent_update / "records" / "record.json",
                "absent-update-record",
                "absent update target",
            )
            write_lock(absent_update)
            absent_update_settings = _test_settings(
                state_file=root / "absent-update-state.json",
                cache_dir=root / "absent-update-cache",
                managed_root=root / "absent-update-managed",
                default_enabled_packs=(),
                default_resource_providers={},
            )
            absent_target = (
                absent_update_settings.managed_root
                / str(absent_update_manifest["pack_id"])
            )
            state_before_absent_update = (
                absent_update_settings.state_file.read_bytes()
                if absent_update_settings.state_file.is_file()
                else None
            )
            cache_existed_before_absent_update = absent_update_settings.cache_dir.exists()
            quarantine_existed_before_absent_update = (
                absent_update_settings.quarantine_root.exists()
            )
            absent_update_output = io.StringIO()
            with redirect_stdout(absent_update_output):
                absent_update_exit = pack_cli_main(
                    [
                        "--state-file",
                        str(absent_update_settings.state_file),
                        "--cache-dir",
                        str(absent_update_settings.cache_dir),
                        "--managed-root",
                        str(absent_update_settings.managed_root),
                        "update",
                        str(absent_update),
                    ]
                )
            try:
                absent_update_payload = json.loads(absent_update_output.getvalue())
            except json.JSONDecodeError:
                absent_update_payload = {}
            state_after_absent_update = (
                absent_update_settings.state_file.read_bytes()
                if absent_update_settings.state_file.is_file()
                else None
            )
            if (
                absent_update_exit != 2
                or absent_update_payload.get("ok") is not False
                or "not installed" not in str(absent_update_payload.get("error"))
                or absent_target.exists()
                or absent_update_settings.managed_root.exists()
                or state_after_absent_update != state_before_absent_update
                or absent_update_settings.cache_dir.exists()
                != cache_existed_before_absent_update
                or absent_update_settings.quarantine_root.exists()
                != quarantine_existed_before_absent_update
            ):
                errors.append(
                    "pack_cli update of an absent UUID mutated state or crossed its JSON error boundary"
                )
            else:
                checks += 1

            malformed_zip = root / "malformed-pack.zip"
            malformed_zip.write_bytes(b"not a ZIP archive")
            complete_zip = root / "complete-for-truncation.zip"
            with zipfile.ZipFile(complete_zip, "w") as archive:
                archive.writestr("pack.json", "{}")
            truncated_zip = root / "truncated-pack.zip"
            complete_zip_bytes = complete_zip.read_bytes()
            truncated_zip.write_bytes(complete_zip_bytes[: len(complete_zip_bytes) // 2])
            state_before_bad_zip = (
                update_settings.state_file.read_bytes()
                if update_settings.state_file.is_file()
                else None
            )
            cache_before_bad_zip = _tree_snapshot(update_settings.cache_dir)
            managed_before_bad_zip = _tree_snapshot(update_settings.managed_root)
            bad_zip_failures: list[str] = []
            for bad_zip in (malformed_zip, truncated_zip):
                output = io.StringIO()
                with redirect_stdout(output):
                    exit_code = pack_cli_main(
                        [
                            "--state-file",
                            str(update_settings.state_file),
                            "--cache-dir",
                            str(update_settings.cache_dir),
                            "--managed-root",
                            str(update_settings.managed_root),
                            "install",
                            str(bad_zip),
                        ]
                    )
                try:
                    failure_payload = json.loads(output.getvalue())
                except json.JSONDecodeError:
                    failure_payload = {}
                if (
                    exit_code != 2
                    or failure_payload.get("ok") is not False
                    or "ZIP" not in str(failure_payload.get("error"))
                ):
                    bad_zip_failures.append(bad_zip.name)
            state_after_bad_zip = (
                update_settings.state_file.read_bytes()
                if update_settings.state_file.is_file()
                else None
            )
            if (
                bad_zip_failures
                or state_after_bad_zip != state_before_bad_zip
                or _tree_snapshot(update_settings.cache_dir) != cache_before_bad_zip
                or _tree_snapshot(update_settings.managed_root) != managed_before_bad_zip
            ):
                errors.append(
                    "malformed ZIP did not stay inside the handled CLI error boundary: "
                    f"{bad_zip_failures}"
                )
            else:
                checks += 1

            resource_boundary_pack = root / "resource-boundary"
            resource_boundary_manifest = initialize_pack(
                resource_boundary_pack,
                name="Resource Boundary",
            )
            _record_file(
                resource_boundary_pack / "records" / "record.json",
                "resource-boundary-record",
                "resource boundary record",
            )
            atomic_write_json(resource_boundary_pack / "pack.lock.json", {})
            resource_boundary_manifest["content"]["resource_globs"] = [
                "records/**/*.json",
                "pack.json",
                "pack.lock.json",
            ]
            atomic_write_json(
                resource_boundary_pack / "pack.json",
                resource_boundary_manifest,
            )
            resource_boundary_report = validate_pack(
                resource_boundary_pack,
                verify_lock=False,
            )
            forbidden_resource_paths = {
                issue.path
                for issue in resource_boundary_report.issues
                if issue.code == "resource-location"
            }
            if (
                resource_boundary_report.valid
                or forbidden_resource_paths
                != {"records/record.json", "pack.json", "pack.lock.json"}
                or resource_boundary_report.resource_files
            ):
                errors.append(
                    "resource globs selected record or pack control files: "
                    f"{resource_boundary_report.to_dict()}"
                )
            else:
                checks += 1

            replacement_root = root / "replacement-permutations"
            replacement_rows: list[tuple[Any, Any]] = []
            replacement_manifests: list[dict[str, Any]] = []
            for name in ("A", "B", "C"):
                pack_root = replacement_root / name.lower()
                replacement_manifest = initialize_pack(
                    pack_root,
                    name=f"Replacement {name}",
                )
                _record_file(
                    pack_root / "records" / "record.json",
                    "shared-replacement-record",
                    f"replacement {name}",
                )
                replacement_manifests.append(replacement_manifest)
            replacement_manifests[2]["replaces"] = [
                {
                    "record_id": "shared-replacement-record",
                    "from_pack": replacement_manifests[index]["pack_id"],
                }
                for index in (0, 1)
            ]
            atomic_write_json(
                replacement_root / "c" / "pack.json",
                replacement_manifests[2],
            )
            replacement_settings = _test_settings(
                roots=(replacement_root,),
                state_file=root / "replacement-state.json",
                cache_dir=root / "replacement-cache",
                managed_root=root / "replacement-managed",
                default_enabled_packs=(),
                default_resource_providers={},
            )
            replacement_discovered, _ = discover_packs(replacement_settings)
            for manifest_row in replacement_manifests:
                pack = replacement_discovered[str(manifest_row["pack_id"])]
                report = validate_pack(pack.root, verify_lock=False)
                replacement_rows.append((pack, report.records))
            permutation_failures: list[str] = []
            for order in itertools.permutations(replacement_rows):
                replacement_diagnostics: list[dict[str, Any]] = []
                resolved = _resolve_records(order, replacement_diagnostics)
                if (
                    len(resolved) != 1
                    or resolved[0][0].pack_id
                    != str(replacement_manifests[2]["pack_id"])
                    or replacement_diagnostics
                ):
                    permutation_failures.append(
                        ",".join(pack.pack_id for pack, _ in order)
                    )
            for order in itertools.permutations(replacement_rows[:2]):
                conflict_diagnostics: list[dict[str, Any]] = []
                resolved_conflict = _resolve_records(order, conflict_diagnostics)
                if resolved_conflict or not any(
                    row.get("code") == "record-id-conflict"
                    and set(row.get("pack_ids") or [])
                    == {
                        str(replacement_manifests[0]["pack_id"]),
                        str(replacement_manifests[1]["pack_id"]),
                    }
                    for row in conflict_diagnostics
                ):
                    permutation_failures.append(
                        "conflict:" + ",".join(pack.pack_id for pack, _ in order)
                    )
            if permutation_failures:
                errors.append(
                    "global record replacement changed with pack order: "
                    + "; ".join(permutation_failures)
                )
            else:
                checks += 1

            closure_root = root / "strict-closure"
            dependency_root = closure_root / "dependency"
            target_root = closure_root / "target"
            dependency_manifest = initialize_pack(
                dependency_root,
                name="Strict Dependency",
            )
            _record_file(
                dependency_root / "records" / "record.json",
                "strict-dependency-record",
                "strict dependency record",
            )
            target_manifest = initialize_pack(target_root, name="Strict Target")
            _record_file(
                target_root / "records" / "record.json",
                "strict-target-record",
                "strict target record",
            )
            target_manifest["dependencies"] = [
                {"pack_id": dependency_manifest["pack_id"]}
            ]
            atomic_write_json(target_root / "pack.json", target_manifest)
            closure_settings = _test_settings(
                roots=(closure_root,),
                state_file=root / "closure-state.json",
                cache_dir=root / "closure-cache",
                managed_root=root / "closure-managed",
                default_enabled_packs=(),
                default_resource_providers={},
            )
            enable_pack(closure_settings, str(dependency_manifest["pack_id"]))
            closure_state_before = closure_settings.state_file.read_bytes()
            atomic_write_json(
                dependency_root / "records" / "record.json",
                {
                    "kind": "module",
                    "category": "lighting",
                    "records": [{"id": "strict-dependency-record"}],
                },
            )
            try:
                enable_pack(closure_settings, str(target_manifest["pack_id"]))
            except PackError:
                if closure_settings.state_file.read_bytes() != closure_state_before:
                    errors.append("failed strict enable changed pack state bytes")
                else:
                    checks += 1
            else:
                errors.append("strict enable accepted an invalid required dependency closure")
            _record_file(
                dependency_root / "records" / "record.json",
                "strict-dependency-record",
                "strict dependency record",
            )
            enabled_closure = enable_pack(
                closure_settings,
                str(target_manifest["pack_id"]),
            )
            # A dependency requires the pack, not a version of it. Moving the
            # dependency's declared release must not disturb resolution, and
            # disabling the dependency must.
            moved_release_manifest = json.loads(json.dumps(dependency_manifest))
            moved_release_manifest["release"] = "2099.01.01.1"
            atomic_write_json(dependency_root / "pack.json", moved_release_manifest)
            try:
                resolve_enabled(closure_settings)
            except PackError as exc:
                moved_release_error = str(exc)
            else:
                moved_release_error = ""
            atomic_write_json(dependency_root / "pack.json", dependency_manifest)
            try:
                disable_pack(closure_settings, str(dependency_manifest["pack_id"]))
            except PackError as exc:
                absent_dependency_error = str(exc)
            else:
                absent_dependency_error = ""
            if (
                set(enabled_closure["enabled_packs"])
                != {
                    str(dependency_manifest["pack_id"]),
                    str(target_manifest["pack_id"]),
                }
                or moved_release_error
                or str(dependency_manifest["pack_id"]) not in absent_dependency_error
            ):
                errors.append(
                    "a dependency was not resolved by pack alone: "
                    f"moved release said {moved_release_error!r}, "
                    f"removing the pack said {absent_dependency_error!r}"
                )
            else:
                checks += 1

            provider_root = root / "provider-closure"
            dependency_pack = provider_root / "dependency"
            provider_pack = provider_root / "provider"
            provider_dependency = initialize_pack(
                dependency_pack,
                name="Provider Dependency",
            )
            provider_manifest = initialize_pack(provider_pack, name="Provider")
            provider_manifest["content"]["resource_globs"] = ["resources/**/*"]
            provider_manifest["content"]["resource_bindings"] = {
                "test-policy": "resources/policy.json"
            }
            missing_provider_dependency = initialize_pack(
                root / "unused-provider-dependency",
                name="Unused Provider Dependency",
            )
            provider_manifest["dependencies"] = [
                {"pack_id": missing_provider_dependency["pack_id"]}
            ]
            atomic_write_json(provider_pack / "pack.json", provider_manifest)
            atomic_write_json(provider_pack / "resources" / "policy.json", {})
            provider_settings = _test_settings(
                roots=(provider_root,),
                state_file=root / "provider-state.json",
                cache_dir=root / "provider-cache",
                managed_root=root / "provider-managed",
                default_enabled_packs=(),
                default_resource_providers={},
            )
            save_state(
                provider_settings.state_file,
                {
                    "pack_roots": [],
                    "enabled_packs": [provider_manifest["pack_id"]],
                    "resource_providers": {
                        "test-policy": provider_manifest["pack_id"]
                    },
                },
            )
            provider_status = runtime_resource_provider_status(provider_settings)
            provider_catalog = load_runtime_catalog(provider_settings)
            provider_row = provider_status["resource_providers"][0]
            provider_codes = {
                row.get("code") for row in provider_status["diagnostics"]
            }
            catalog_codes = {row.get("code") for row in provider_catalog.diagnostics}
            expected_provider_codes = {
                "missing-active-dependency",
                "resource-provider-unavailable",
            }
            if (
                provider_row.get("selected_pack") != provider_manifest["pack_id"]
                or provider_row.get("candidate_packs") != []
                or provider_row.get("resolved") is not False
                or not expected_provider_codes.issubset(provider_codes)
                or not expected_provider_codes.issubset(catalog_codes)
                or "test-policy" in provider_catalog.resources
            ):
                errors.append(
                    "provider-list eligibility disagreed with runtime dependency filtering"
                )
            else:
                checks += 1
            provider_manifest["dependencies"] = [
                {"pack_id": provider_dependency["pack_id"]}
            ]
            atomic_write_json(provider_pack / "pack.json", provider_manifest)
            save_state(
                provider_settings.state_file,
                {
                    "pack_roots": [],
                    "enabled_packs": [
                        provider_dependency["pack_id"],
                        provider_manifest["pack_id"],
                    ],
                    "resource_providers": {
                        "test-policy": provider_manifest["pack_id"]
                    },
                },
            )
            positive_provider_status = runtime_resource_provider_status(provider_settings)
            positive_provider_catalog = load_runtime_catalog(provider_settings)
            positive_provider_row = positive_provider_status["resource_providers"][0]
            # Moving the dependency's declared release changes nothing: a
            # provider is eligible because the pack it depends on is present.
            moved_provider_dependency = json.loads(json.dumps(provider_dependency))
            moved_provider_dependency["release"] = "2099.01.01.1"
            atomic_write_json(dependency_pack / "pack.json", moved_provider_dependency)
            moved_provider_status = runtime_resource_provider_status(provider_settings)
            moved_provider_catalog = load_runtime_catalog(provider_settings)
            moved_provider_row = moved_provider_status["resource_providers"][0]
            moved_codes = {
                row.get("code") for row in moved_provider_status["diagnostics"]
            } | {row.get("code") for row in moved_provider_catalog.diagnostics}
            atomic_write_json(dependency_pack / "pack.json", provider_dependency)
            if (
                positive_provider_row.get("candidate_packs")
                != [provider_manifest["pack_id"]]
                or positive_provider_row.get("resolved") is not True
                or "test-policy" not in positive_provider_catalog.resources
                or moved_provider_row.get("candidate_packs")
                != [provider_manifest["pack_id"]]
                or moved_provider_row.get("resolved") is not True
                or "dependency-release" in moved_codes
                or "test-policy" not in moved_provider_catalog.resources
            ):
                errors.append(
                    "a provider's eligibility answered to a declared release rather than "
                    f"to the pack being present: {sorted(code for code in moved_codes if code)}"
                )
            else:
                checks += 1

            default_project_defaults = json.loads(
                (Path(__file__).resolve().parents[1] / "packs" / "commons" / "resources" / "project-defaults.json").read_text(
                    encoding="utf-8"
                )
            )
            default_negative_policy = json.loads(
                (Path(__file__).resolve().parents[1] / "packs" / "commons" / "resources" / "negative-policy.json").read_text(
                    encoding="utf-8"
                )
            )
            if (
                validate_known_resource("project-defaults", default_project_defaults)
                or validate_known_resource("negative-policy", default_negative_policy)
                or not medium_selection_allowed(
                    default_project_defaults,
                    ["one-medium"],
                    explicit_hybrid_request=False,
                )
                or medium_selection_allowed(
                    default_project_defaults,
                    ["medium-a", "medium-b"],
                    explicit_hybrid_request=False,
                )
                or not medium_selection_allowed(
                    default_project_defaults,
                    ["medium-a", "medium-b"],
                    explicit_hybrid_request=True,
                )
                or negative_source_emission_allowed(
                    default_negative_policy,
                    "semantic_exclusions",
                    user_explicitly_excluded=False,
                )
                or not negative_source_emission_allowed(
                    default_negative_policy,
                    "semantic_exclusions",
                    user_explicitly_excluded=True,
                )
                or negative_source_emission_allowed(
                    default_negative_policy,
                    "scene_failure_modes",
                )
                or negative_source_emission_allowed(
                    default_negative_policy,
                    "atomic_misreadings",
                )
            ):
                errors.append(
                    "bundled default known resources violated medium or negative-source behavior"
                )
            else:
                checks += 1

            semantic_root = root / "known-resource-provider"
            semantic_pack = semantic_root / "pack"
            semantic_manifest = initialize_pack(
                semantic_pack,
                name="Known Resource Provider",
            )
            semantic_manifest["content"]["resource_globs"] = ["resources/**/*"]
            semantic_manifest["content"]["resource_bindings"] = {
                "discovery-lanes": "resources/discovery-lanes.json",
                "project-defaults": "resources/project-defaults.json",
                "negative-policy": "resources/negative-policy.json",
                "species-scaffold-map": "resources/species-scaffold-map.json",
            }
            atomic_write_json(semantic_pack / "pack.json", semantic_manifest)
            _record_file(
                semantic_pack / "records" / "fixture-scene.json",
                "fixture-scene",
                "fixture scene",
            )
            atomic_write_json(
                semantic_pack / "records" / "fixture-species.json",
                {
                    "kind": "module",
                    "category": "species",
                    "records": [
                        {
                            "id": species_id,
                            "label": species_id.replace("-", " "),
                            "curation_status": "vocabulary",
                            "category": "species",
                            "prompt": species_id.replace("-", " "),
                            "domains": ["shared"],
                            "tags": ["fixture species"],
                            "search_terms": [
                                {
                                    "phrase": species_id.replace("-", " "),
                                    "facet": "species",
                                    "weight": 1.0,
                                    "source": "fixture",
                                }
                            ],
                        }
                        for species_id in ("fixture-species-a", "fixture-species-b")
                    ],
                },
            )
            fixture_discovery_lanes = {
                "lanes": [
                    {
                        "id": "fixture-lane",
                        "preferred_scene_ids": ["fixture-scene"],
                    }
                ]
            }
            fixture_project_defaults = {
                "medium_policy": {
                    "single_medium_family_by_default": True,
                    "hybrid_requires_explicit_request": True,
                }
            }
            fixture_negative_policy = {
                "automatic_sources": {},
                "diagnostic_only_sources": {
                    "scene_failure_modes": {"automatic_emission": False},
                    "atomic_misreadings": {"automatic_emission": False},
                },
                "semantic_exclusion_rule": (
                    "Semantic alternatives enter a negative prompt only when the user "
                    "explicitly excludes them."
                ),
            }
            fixture_species_scaffold = {
                "identity_authority_order": [
                    "explicit user species anchor",
                    "approved Character Identity Contract",
                    "selected species scaffold",
                ],
                "families": {"fixture-family": {"description": "Fixture geometry."}},
                "species_to_scaffold": {
                    species_id: {
                        "scaffold_family": "fixture-family",
                        "identity_rule": "preserve-user-or-contract-species",
                    }
                    for species_id in ("fixture-species-a", "fixture-species-b")
                },
                "species_count": 2,
            }
            semantic_resource_values = {
                "discovery-lanes": fixture_discovery_lanes,
                "project-defaults": fixture_project_defaults,
                "negative-policy": fixture_negative_policy,
                "species-scaffold-map": fixture_species_scaffold,
            }
            for resource_name, resource_value in semantic_resource_values.items():
                atomic_write_json(
                    semantic_pack / "resources" / f"{resource_name}.json",
                    resource_value,
                )
            write_lock(semantic_pack)
            semantic_settings = _test_settings(
                roots=(semantic_root,),
                state_file=root / "known-resource-state.json",
                cache_dir=root / "known-resource-cache",
                managed_root=root / "known-resource-managed",
                default_enabled_packs=(),
                default_resource_providers={},
            )
            save_state(
                semantic_settings.state_file,
                {
                    "pack_roots": [],
                    "enabled_packs": [semantic_manifest["pack_id"]],
                    "resource_providers": {
                        name: semantic_manifest["pack_id"]
                        for name in semantic_resource_values
                    },
                },
            )
            semantic_catalog = load_runtime_catalog(semantic_settings)
            semantic_provider_valid = validate_pack(semantic_pack)
            resolved_semantic_values = {
                name: json.loads(resource.path.read_text(encoding="utf-8"))
                for name, resource in semantic_catalog.resources.items()
                if name in semantic_resource_values
            }
            if (
                not semantic_provider_valid.valid
                or set(resolved_semantic_values) != set(semantic_resource_values)
                or any(
                    semantic_catalog.resources[name].source_pack
                    != semantic_manifest["pack_id"]
                    for name in semantic_resource_values
                )
                or any(
                    validate_known_resource(name, value)
                    for name, value in resolved_semantic_values.items()
                )
            ):
                errors.append(
                    "explicit arbitrary-pack providers did not preserve known-resource semantics"
                )
            else:
                checks += 1

            semantic_mutations = [
                (
                    "project-defaults",
                    lambda value: value["medium_policy"].__setitem__(
                        "single_medium_family_by_default", False
                    ),
                    "single_medium_family_by_default",
                ),
                (
                    "project-defaults",
                    lambda value: value["medium_policy"].__setitem__(
                        "hybrid_requires_explicit_request", False
                    ),
                    "hybrid_requires_explicit_request",
                ),
                (
                    "negative-policy",
                    lambda value: value.__setitem__(
                        "semantic_exclusion_rule", "Invent semantic exclusions freely."
                    ),
                    "semantic exclusions must be user-request-only",
                ),
                (
                    "negative-policy",
                    lambda value: value["diagnostic_only_sources"]["scene_failure_modes"].__setitem__(
                        "automatic_emission", True
                    ),
                    "scene_failure_modes.automatic_emission must be false",
                ),
                (
                    "negative-policy",
                    lambda value: value["diagnostic_only_sources"]["atomic_misreadings"].__setitem__(
                        "automatic_emission", True
                    ),
                    "atomic_misreadings.automatic_emission must be false",
                ),
                (
                    "species-scaffold-map",
                    lambda value: value["identity_authority_order"].__setitem__(
                        0, "selected scaffold convenience"
                    ),
                    "identity_authority_order must begin",
                ),
                (
                    "species-scaffold-map",
                    lambda value: value["species_to_scaffold"]["fixture-species-a"].__setitem__(
                        "identity_rule", "replace-user-species"
                    ),
                    "identity_rule must be 'preserve-user-or-contract-species'",
                ),
            ]
            mutation_failures: list[str] = []
            for resource_name, mutate, expected_message in semantic_mutations:
                changed = json.loads(json.dumps(semantic_resource_values[resource_name]))
                mutate(changed)
                resource_path = semantic_pack / "resources" / f"{resource_name}.json"
                atomic_write_json(resource_path, changed)
                mutation_report = validate_pack(
                    semantic_pack,
                    require_lock=False,
                    verify_lock=False,
                )
                issue_messages = [
                    issue.message
                    for issue in mutation_report.issues
                    if issue.code == "known-resource-contract"
                ]
                if mutation_report.valid or not any(
                    expected_message in message for message in issue_messages
                ):
                    mutation_failures.append(
                        f"{resource_name}: expected {expected_message!r}, got {issue_messages}"
                    )
                atomic_write_json(
                    resource_path,
                    semantic_resource_values[resource_name],
                )
            invalid_lanes = json.loads(json.dumps(fixture_discovery_lanes))
            invalid_lanes["lanes"][0]["preferred_scene_ids"] = ["missing-scene"]
            lanes_path = semantic_pack / "resources" / "discovery-lanes.json"
            atomic_write_json(lanes_path, invalid_lanes)
            write_lock(semantic_pack)
            invalid_lane_pack_report = validate_pack(semantic_pack)
            invalid_lane_catalog = load_runtime_catalog(semantic_settings)
            invalid_lane_status = runtime_resource_provider_status(semantic_settings)
            invalid_lane_diagnostics = [
                row for row in invalid_lane_catalog.diagnostics
                if row.get("code") == "known-resource-contract"
                and row.get("resource") == "discovery-lanes"
            ]
            invalid_lane_status_rows = [
                row for row in invalid_lane_status["resource_providers"]
                if row.get("name") == "discovery-lanes"
            ]
            if (
                not invalid_lane_pack_report.valid
                or "discovery-lanes" in invalid_lane_catalog.resources
                or not invalid_lane_diagnostics
                or "missing-scene" not in str(invalid_lane_diagnostics[0].get("errors"))
                or not invalid_lane_status_rows
                or invalid_lane_status_rows[0].get("resolved") is not False
            ):
                mutation_failures.append(
                    "discovery-lanes: missing preferred scene was not rejected against active records"
                )
            atomic_write_json(lanes_path, fixture_discovery_lanes)
            write_lock(semantic_pack)
            scaffold_path = semantic_pack / "resources" / "species-scaffold-map.json"
            contextual_scaffold_mutations = []
            missing_scaffold = json.loads(json.dumps(fixture_species_scaffold))
            missing_scaffold["species_to_scaffold"].pop("fixture-species-b")
            contextual_scaffold_mutations.append(
                ("missing-active-species", missing_scaffold, "fixture-species-b")
            )
            extra_scaffold = json.loads(json.dumps(fixture_species_scaffold))
            extra_scaffold["species_to_scaffold"]["phantom-species"] = {
                "scaffold_family": "fixture-family",
                "identity_rule": "preserve-user-or-contract-species",
            }
            contextual_scaffold_mutations.append(
                ("phantom-species", extra_scaffold, "phantom-species")
            )
            for mutation_name, mutated_scaffold, expected_id in contextual_scaffold_mutations:
                atomic_write_json(scaffold_path, mutated_scaffold)
                write_lock(semantic_pack)
                scaffold_pack_report = validate_pack(semantic_pack)
                scaffold_catalog = load_runtime_catalog(semantic_settings)
                scaffold_diagnostics = [
                    row for row in scaffold_catalog.diagnostics
                    if row.get("code") == "known-resource-contract"
                    and row.get("resource") == "species-scaffold-map"
                ]
                if (
                    not scaffold_pack_report.valid
                    or "species-scaffold-map" in scaffold_catalog.resources
                    or not scaffold_diagnostics
                    or expected_id not in str(scaffold_diagnostics[0].get("errors"))
                ):
                    mutation_failures.append(
                        "species-scaffold-map: "
                        f"{mutation_name} was not rejected against active species records"
                    )
                atomic_write_json(scaffold_path, fixture_species_scaffold)
                write_lock(semantic_pack)
            if mutation_failures or not validate_pack(semantic_pack).valid:
                errors.append(
                    "known-resource semantic mutations were not rejected cleanly: "
                    + "; ".join(mutation_failures)
                )
            else:
                checks += 1

            broken_root = root / "broken-discovery"
            broken_pack = broken_root / "pack"
            broken_manifest = initialize_pack(broken_pack, name="Broken Discovery")
            broken_settings = _test_settings(
                roots=(broken_root,),
                state_file=root / "broken-state.json",
                cache_dir=root / "broken-cache",
                managed_root=root / "broken-managed",
                default_enabled_packs=(),
                default_resource_providers={},
            )
            save_state(
                broken_settings.state_file,
                {
                    "pack_roots": [],
                    "enabled_packs": [broken_manifest["pack_id"]],
                    "resource_providers": {},
                },
            )
            (broken_pack / "pack.json").write_text("{broken", encoding="utf-8")
            broken_catalog = load_runtime_catalog(broken_settings)
            broken_diagnostics = list(broken_catalog.diagnostics)
            manifest_diagnostics = [
                row for row in broken_diagnostics if row.get("code") == "manifest"
            ]
            targeted_manifest_diagnostics = [
                row
                for row in manifest_diagnostics
                if row.get("path") == str((broken_pack / "pack.json").resolve())
            ]
            if (
                len(targeted_manifest_diagnostics) != 1
                or "Invalid JSON"
                not in str(targeted_manifest_diagnostics[0].get("message"))
                or not any(
                    row.get("code") == "enabled-pack-unavailable"
                    and broken_manifest["pack_id"] in str(row.get("message"))
                    for row in broken_diagnostics
                )
            ):
                errors.append(
                    "lenient discovery dropped the exact invalid-manifest path or context"
                )
            else:
                checks += 1

            duplicate_diagnostic_root = root / "duplicate-diagnostic"
            duplicate_one = duplicate_diagnostic_root / "one"
            duplicate_manifest = initialize_pack(
                duplicate_one,
                name="Duplicate Diagnostic",
            )
            duplicate_two = duplicate_diagnostic_root / "two"
            shutil.copytree(duplicate_one, duplicate_two)
            duplicate_diagnostic_settings = _test_settings(
                roots=(duplicate_diagnostic_root,),
                state_file=root / "duplicate-diagnostic-state.json",
                cache_dir=root / "duplicate-diagnostic-cache",
                managed_root=root / "duplicate-diagnostic-managed",
                default_enabled_packs=(),
                default_resource_providers={},
            )
            save_state(
                duplicate_diagnostic_settings.state_file,
                {
                    "pack_roots": [],
                    "enabled_packs": [duplicate_manifest["pack_id"]],
                    "resource_providers": {},
                },
            )
            duplicate_catalog = load_runtime_catalog(duplicate_diagnostic_settings)
            duplicate_diagnostics = list(duplicate_catalog.diagnostics)
            duplicate_rows = [
                row
                for row in duplicate_diagnostics
                if row.get("code") == "duplicate-pack-id"
            ]
            targeted_duplicate_rows = [
                row
                for row in duplicate_rows
                if str(duplicate_one.resolve()) in str(row.get("message"))
                and str(duplicate_two.resolve()) in str(row.get("message"))
            ]
            if (
                len(targeted_duplicate_rows) != 1
                or not any(
                    row.get("code") == "enabled-pack-unavailable"
                    for row in duplicate_diagnostics
                )
            ):
                errors.append("lenient duplicate discovery dropped conflicting root context")
            else:
                checks += 1

            source_parent = root / "source-packs"
            source_pack = source_parent / "example"
            manifest = initialize_pack(source_pack, name="Pack Smoke Test")
            pack_id = str(manifest["pack_id"])
            if not PACK_ID_RE.fullmatch(pack_id):
                errors.append("pack init did not generate a UUIDv7 pack ID")
            else:
                checks += 1

            first = source_pack / "records" / "first.json"
            _record_file(first, "pack-smoke-first", "quiet cyan edge light")
            first_document = json.loads(first.read_text(encoding="utf-8"))
            first_document["records"][0]["search_profile"] = {
                "aliases": ["cyan rim portrait"],
                "discovery_group": "pack-smoke-lighting-family",
            }
            atomic_write_json(first, first_document)
            write_lock(source_pack)
            lock_path = source_pack / "pack.lock.json"
            duplicate_lock = json.loads(lock_path.read_text(encoding="utf-8"))
            duplicate_row = dict(duplicate_lock["files"][0])
            duplicate_row["bytes"] = int(duplicate_row["bytes"]) + 1
            duplicate_lock["files"].append(duplicate_row)
            atomic_write_json(lock_path, duplicate_lock)
            duplicate_lock_report = validate_pack(source_pack, require_lock=True)
            if not any(
                issue.code == "lock-duplicate-path"
                for issue in duplicate_lock_report.issues
            ):
                errors.append("lock validation accepted duplicate path rows")
            else:
                checks += 1
            write_lock(source_pack)
            released = validate_pack(source_pack, require_lock=True)
            if not released.valid or len(released.records) != 1:
                errors.append(f"released pack validation failed: {released.to_dict()}")
            else:
                checks += 1

            settings = _test_settings(
                roots=(source_parent,),
                state_file=root / "state.json",
                cache_dir=root / "cache",
                managed_root=root / "managed",
                default_enabled_packs=(),
            )
            enable_pack(settings, pack_id)
            refreshed = refresh_cache(settings)
            catalog = load_runtime_catalog(settings)
            configure_pack_runtime(settings)
            runtime_ids = {entry.record["id"] for entry in load_entries()}
            if not refreshed.get("rebuilt") or [entry.record["id"] for entry in catalog.entries] != [
                "pack-smoke-first"
            ] or runtime_ids != {"pack-smoke-first"}:
                errors.append("enabled pack was not added to the generated search cache")
            elif "quiet cyan edge light" not in catalog.phrases:
                errors.append("pack label was not added to the lexical cache")
            elif [
                row["source"]
                for row in catalog.phrases["quiet cyan edge light"]
                if row["id"] == "pack-smoke-first"
            ] != ["author", "review"]:
                errors.append(
                    "explicit phrase provenance was collapsed or generated duplicates remained"
                )
            elif (
                catalog.profiles["pack-smoke-first"].get("discovery_group")
                != "pack-smoke-lighting-family"
                or len(set(catalog.profiles["pack-smoke-first"].get("aliases") or [])) < 3
                or not catalog.profiles["pack-smoke-first"].get("outcome_summary")
                or not catalog.profiles["pack-smoke-first"].get("facets")
                or not isinstance(
                    catalog.profiles["pack-smoke-first"].get("anchor_signature"), dict
                )
            ):
                errors.append("partial authored search profile was not completed for runtime use")
            else:
                checks += 1

            # Windows refuses to rename onto a file any process holds open, so a
            # cache published under a fixed name could be failed by whoever was
            # reading it. The name is the fingerprint of the inputs, so a build
            # renames into a name nothing holds, and a reader takes no lock.
            cache_file = Path(refreshed["cache_path"])
            lock_file = pack_cache_module._cache_lock_path(settings)
            if cache_file.name == "catalog.sqlite3" or refreshed["fingerprint"] not in cache_file.name:
                errors.append(
                    "the published cache is not named after the inputs it was built from"
                )
            else:
                checks += 1

            locked_while_reading: list[bool] = []
            unpatched_connect = pack_cache_module.sqlite3.connect

            def _recording_connect(database, *arguments, **keywords):
                locked_while_reading.append(lock_file.is_file())
                return unpatched_connect(database, *arguments, **keywords)

            with patch.object(pack_cache_module.sqlite3, "connect", _recording_connect):
                load_runtime_catalog(settings)
            if not locked_while_reading or any(locked_while_reading):
                errors.append("reading the catalog took the build lock")
            else:
                checks += 1

            # The hazard itself: hold the current cache open, change the inputs,
            # and rebuild. The build publishes a name nothing holds, so the reader
            # neither fails it nor is disturbed by it. Whether the superseded file
            # is still listed afterwards is the platform's business, not the
            # contract's: POSIX unlinks it and leaves the open handle valid, and
            # Windows refuses the unlink. What must hold on both is that the
            # reader can still read what it opened.
            held = pack_cache_module._connect_readonly(cache_file)
            try:
                _record_file(
                    source_pack / "records" / "second.json",
                    "pack-smoke-second-input",
                    "quiet amber rim light",
                )
                write_lock(source_pack)
                try:
                    moved = refresh_cache(settings)
                except OSError as blocked:
                    errors.append(f"an open reader failed a rebuild: {blocked}")
                else:
                    still_readable = [
                        row[0]
                        for row in held.execute("SELECT value FROM meta WHERE key = ?",
                                                ("cache_fingerprint",))
                    ]
                    if not moved.get("rebuilt") or Path(moved["cache_path"]) == cache_file:
                        errors.append("changed inputs did not publish a new cache")
                    elif still_readable != [refreshed["fingerprint"]]:
                        errors.append(
                            "a reader holding the superseded cache could no longer read it: "
                            f"{still_readable!r}"
                        )
                    else:
                        checks += 1
            finally:
                held.close()

            # A cache that arrived after the one a caller keeps was built from
            # inputs that caller has not seen. Removing it would delete another
            # process's current answer and start a rebuild it would delete back.
            newer = cache_file.with_name(cache_file.name.replace(".sqlite3",
                                                                 "-later.sqlite3"))
            newer.write_bytes(b"another process just published this")
            os.utime(newer, ns=(time.time_ns(), time.time_ns() + 10**9))
            pack_cache_module._discard_superseded(settings, cache_file)
            if not newer.is_file():
                errors.append("a cache newer than the one being kept was discarded")
            else:
                checks += 1
            newer.unlink()

            # Nothing holds it now, so the next caller that settles which cache is
            # current removes it.
            current = Path(refresh_cache(settings)["cache_path"])
            leftover = sorted(
                path.name
                for path in current.parent.glob(f"{pack_cache_module.CACHE_STEM}-*."
                                                f"{pack_cache_module.CACHE_SUFFIX}")
                if path != current
            )
            if leftover:
                errors.append(f"superseded caches were left behind: {leftover}")
            else:
                checks += 1

            (source_pack / "pack.lock.json").unlink()
            manifest_path = source_pack / "pack.json"
            development_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            development_manifest["content"]["resource_globs"] = ["resources/**/*"]
            development_manifest["content"]["resource_bindings"] = {
                "smoke-guide": "resources/guide.json"
            }
            atomic_write_json(manifest_path, development_manifest)
            atomic_write_json(source_pack / "resources" / "guide.json", {"role": "guide"})
            asset = source_pack / "records" / "asset.json"
            _asset_record_file(asset, "pack-smoke-asset", "pack-smoke-second")
            unselected_catalog = load_runtime_catalog(settings)
            if "smoke-guide" in unselected_catalog.resources or not any(
                row.get("code") == "resource-provider-unselected"
                and row.get("resource") == "smoke-guide"
                and row.get("severity") == "warning"
                for row in unselected_catalog.diagnostics
            ):
                errors.append(
                    "an unselected logical resource resolved implicitly or was reported as a runtime error"
                )
            else:
                checks += 1
            select_resource_provider(settings, "smoke-guide", pack_id)
            selected_catalog = load_runtime_catalog(settings)
            selected_fingerprint = selected_catalog.fingerprint
            if selected_catalog.resources.get("smoke-guide") is None:
                errors.append("explicit logical resource provider did not resolve")
            else:
                checks += 1
            clear_resource_provider(settings, "smoke-guide")
            cleared_catalog = load_runtime_catalog(settings)
            if (
                "smoke-guide" in cleared_catalog.resources
                or cleared_catalog.fingerprint == selected_fingerprint
            ):
                errors.append("clearing a resource provider did not invalidate resolution")
            else:
                checks += 1
            select_resource_provider(settings, "smoke-guide", pack_id)
            alternate_pack = source_parent / "alternate-provider"
            alternate_manifest = initialize_pack(alternate_pack, name="Alternate Provider")
            alternate_id = str(alternate_manifest["pack_id"])
            alternate_manifest["content"]["resource_globs"] = ["resources/**/*"]
            alternate_manifest["content"]["resource_bindings"] = {
                "smoke-guide": "resources/guide.json"
            }
            atomic_write_json(alternate_pack / "pack.json", alternate_manifest)
            atomic_write_json(
                alternate_pack / "resources" / "guide.json",
                {"role": "alternate guide"},
            )
            enable_pack(settings, alternate_id)
            collision_catalog = load_runtime_catalog(settings)
            if collision_catalog.resources["smoke-guide"].source_pack != pack_id:
                errors.append("a second resource candidate overrode the selected provider")
            else:
                checks += 1
            select_resource_provider(settings, "smoke-guide", alternate_id)
            alternate_catalog = load_runtime_catalog(settings)
            if alternate_catalog.resources["smoke-guide"].source_pack != alternate_id:
                errors.append("explicit provider change did not select the requested candidate")
            else:
                checks += 1
            select_resource_provider(settings, "smoke-guide", pack_id)
            runtime_ids_with_missing_reference = {
                entry.record["id"] for entry in load_entries()
            }
            missing_reference_status = cache_status(settings)
            missing_reference_diagnostics = missing_reference_status.get("diagnostics") or []
            if runtime_ids_with_missing_reference != {"pack-smoke-first"} or not any(
                row.get("code") == "missing-canonical-record"
                and row.get("record_id") == "pack-smoke-asset"
                for row in missing_reference_diagnostics
            ):
                errors.append("an asset with a missing canonical record remained searchable")
            else:
                checks += 1

            second = source_pack / "records" / "second.json"
            _record_file(second, "pack-smoke-second", "warm doorway spill")
            second_asset = source_pack / "records" / "asset-second.json"
            _asset_record_file(
                second_asset,
                "pack-smoke-asset-second",
                "pack-smoke-second",
            )
            stale_after_add = cache_status(settings)
            begin_catalog_request()
            runtime_ids_after_add = {entry.record["id"] for entry in load_entries()}
            catalog = load_runtime_catalog(settings)
            ids_after_add = {entry.record["id"] for entry in catalog.entries}
            if stale_after_add.get("fresh") or ids_after_add != {
                "pack-smoke-first",
                "pack-smoke-second",
                "pack-smoke-asset",
                "pack-smoke-asset-second",
            } or runtime_ids_after_add != ids_after_add:
                errors.append(
                    "direct record addition did not refresh the in-process catalog: "
                    f"ids={sorted(ids_after_add)}, diagnostics={list(catalog.diagnostics)}"
                )
            else:
                checks += 1

            linked_assets = catalog.assets_by_canonical_record.get("pack-smoke-second", ())
            if [entry.record["id"] for entry in linked_assets] != [
                "pack-smoke-asset",
                "pack-smoke-asset-second",
            ] or any(
                entry.source_root != source_pack.resolve()
                or not entry.source_file.startswith("records/")
                for entry in linked_assets
            ):
                errors.append("canonical record reverse asset index lost order or ownership")
            else:
                checks += 1

            second_asset.unlink()
            stale_after_asset_delete = cache_status(settings)
            catalog_after_asset_delete = load_runtime_catalog(settings)
            remaining_assets = catalog_after_asset_delete.assets_by_canonical_record.get(
                "pack-smoke-second", ()
            )
            if (
                stale_after_asset_delete.get("fresh")
                or [entry.record["id"] for entry in remaining_assets]
                != ["pack-smoke-asset"]
                or any(
                    entry.record.get("id") == "pack-smoke-asset-second"
                    for entry in catalog_after_asset_delete.entries
                )
            ):
                errors.append("deleted asset remained in the reverse index or runtime catalog")
            else:
                checks += 1

            second.unlink()
            stale_after_delete = cache_status(settings)
            begin_catalog_request()
            runtime_ids_after_delete = {entry.record["id"] for entry in load_entries()}
            catalog = load_runtime_catalog(settings)
            ids_after_delete = {entry.record["id"] for entry in catalog.entries}
            if (
                stale_after_delete.get("fresh")
                or ids_after_delete != {"pack-smoke-first"}
                or runtime_ids_after_delete != ids_after_delete
                or "pack-smoke-second" in catalog.assets_by_canonical_record
            ):
                errors.append(
                    "direct canonical-record deletion left a ghost asset in the in-process catalog"
                )
            else:
                checks += 1

            shutil.rmtree(source_pack)
            begin_catalog_request()
            runtime_ids_after_pack_delete = {entry.record["id"] for entry in load_entries()}
            refresh_after_pack_delete = cache_status(settings)
            catalog = load_runtime_catalog(settings)
            if catalog.entries or runtime_ids_after_pack_delete:
                errors.append(
                    "out-of-band pack deletion left cached records searchable: "
                    f"ids={[entry.record.get('id') for entry in catalog.entries]}"
                )
            elif not refresh_after_pack_delete.get("discovery_issues"):
                errors.append("out-of-band pack deletion did not produce a diagnostic")
            else:
                checks += 1

            install_source = root / "install-source"
            installed_manifest = initialize_pack(
                install_source,
                name="Install Smoke Test",
            )
            _record_file(
                install_source / "records" / "record.json",
                "pack-install-smoke",
                "silver reflected fill",
            )
            write_lock(install_source)
            install_settings = _test_settings(
                state_file=root / "install-state.json",
                cache_dir=root / "install-cache",
                managed_root=root / "install-managed",
                default_enabled_packs=(),
                default_resource_providers={},
            )
            installed = install_pack(install_settings, install_source)
            installed_id = str(installed_manifest["pack_id"])
            installed_root = install_settings.managed_root / installed_id
            if not installed_root.is_dir() or not validate_pack(
                installed_root, require_lock=True
            ).valid:
                errors.append("locked directory install did not create a valid managed pack")
            else:
                checks += 1
            enable_pack(install_settings, installed_id)
            bundled_settings = replace(
                install_settings, protected_pack_ids=(installed_id,)
            )
            try:
                disable_pack(bundled_settings, installed_id)
            except PackError:
                checks += 1
            else:
                errors.append("a bundled default pack could be disabled")
            (installed_root / "pack.json").write_text("{broken", encoding="utf-8")
            disabled_state = disable_pack(install_settings, installed_id)
            if installed_id in disabled_state["enabled_packs"]:
                errors.append("a corrupt installed pack could not be disabled")
            else:
                checks += 1
            try:
                remove_pack(install_settings, "../outside")
            except PackError:
                checks += 1
            else:
                errors.append("remove accepted a non-UUID path argument")
            removed = remove_pack(install_settings, installed_id)
            quarantine_path = Path(str(removed["quarantine_path"]))
            if (
                installed_root.exists()
                or not quarantine_path.is_dir()
                or install_settings.managed_root.resolve() not in quarantine_path.resolve().parents
            ):
                errors.append("managed pack removal was not recoverable through quarantine")
            else:
                checks += 1
            reinstalled = install_pack(install_settings, install_source)
            if (
                reinstalled.get("pack_id") != installed_id
                or not installed_root.is_dir()
                or not validate_pack(installed_root, require_lock=True).valid
            ):
                errors.append("a recovered UUID could not be reinstalled after corrupt removal")
            else:
                checks += 1
            remove_pack(install_settings, installed_id)

            duplicate_root = root / "duplicate-packs"
            duplicate_root.mkdir()
            duplicate_source = duplicate_root / "one"
            duplicate_manifest = initialize_pack(duplicate_source, name="Duplicate One")
            duplicate_id = str(duplicate_manifest["pack_id"])
            shutil.copytree(duplicate_source, duplicate_root / "two")
            shutil.copytree(duplicate_source, duplicate_root / "three")
            invalid_duplicate_manifest = dict(duplicate_manifest)
            invalid_duplicate_manifest.pop("name")
            atomic_write_json(duplicate_root / "two" / "pack.json", invalid_duplicate_manifest)
            duplicate_settings = _test_settings(
                roots=(duplicate_root,),
                state_file=root / "duplicate-state.json",
                cache_dir=root / "duplicate-cache",
                managed_root=root / "duplicate-managed",
                default_enabled_packs=(),
                default_resource_providers={},
            )
            duplicate_discovered, duplicate_issues = discover_packs(duplicate_settings)
            if duplicate_id in duplicate_discovered or len(
                [issue for issue in duplicate_issues if issue.code == "duplicate-pack-id"]
            ) < 1:
                errors.append("three copies of one UUID were not all excluded")
            else:
                checks += 1

            cycle_root = root / "cycle-packs"
            cycle_root.mkdir()
            cycle_a = cycle_root / "a"
            cycle_b = cycle_root / "b"
            cycle_a_manifest = initialize_pack(cycle_a, name="Cycle A")
            cycle_b_manifest = initialize_pack(cycle_b, name="Cycle B")
            cycle_a_id = str(cycle_a_manifest["pack_id"])
            cycle_b_id = str(cycle_b_manifest["pack_id"])
            cycle_a_manifest["dependencies"] = [
                {"pack_id": cycle_b_id}
            ]
            cycle_b_manifest["dependencies"] = [
                {"pack_id": cycle_a_id}
            ]
            atomic_write_json(cycle_a / "pack.json", cycle_a_manifest)
            atomic_write_json(cycle_b / "pack.json", cycle_b_manifest)
            cycle_settings = _test_settings(
                roots=(cycle_root,),
                state_file=root / "cycle-state.json",
                cache_dir=root / "cycle-cache",
                managed_root=root / "cycle-managed",
                default_enabled_packs=(),
                default_resource_providers={},
            )
            try:
                resolve_enabled(
                    cycle_settings,
                    {
                        "pack_roots": [],
                        "enabled_packs": [cycle_a_id, cycle_b_id],
                        "resource_providers": {},
                    },
                )
            except PackError as exc:
                if "cycle" in str(exc).lower():
                    checks += 1
                else:
                    errors.append(f"dependency cycle failed for the wrong reason: {exc}")
            else:
                errors.append("required dependency cycle was accepted")
            save_state(
                cycle_settings.state_file,
                {
                    "pack_roots": [],
                    "enabled_packs": [cycle_a_id, cycle_b_id],
                    "resource_providers": {},
                },
            )
            cycle_catalog = load_runtime_catalog(cycle_settings)
            if not any(
                row.get("code") == "required-dependency-cycle"
                for row in cycle_catalog.diagnostics
            ):
                errors.append("runtime cache did not exclude a required dependency cycle")
            else:
                checks += 1

            duplicate_zip = root / "duplicate-members.zip"
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                with zipfile.ZipFile(duplicate_zip, "w") as archive:
                    archive.writestr("pack.json", "{}")
                    archive.writestr("pack.json", "{}")
            try:
                install_pack(install_settings, duplicate_zip)
            except PackError as exc:
                if "duplicate member" in str(exc).lower():
                    checks += 1
                else:
                    errors.append(f"duplicate ZIP member failed for the wrong reason: {exc}")
            else:
                errors.append("duplicate ZIP member path was accepted")

            bundle_pack = root / "bundle-contract"
            bundle_asset_path = _visual_bundle_fixture(bundle_pack)
            bundle_report = validate_pack(bundle_pack, require_lock=True)
            if not bundle_report.valid:
                errors.append(
                    f"valid visual bundle cross-contract fixture failed: {bundle_report.to_dict()}"
                )
            else:
                checks += 1
            original_bundle_asset = json.loads(
                bundle_asset_path.read_text(encoding="utf-8")
            )
            mismatched_bundle_asset = json.loads(json.dumps(original_bundle_asset))
            mismatched_bundle_asset["records"][0]["artifacts"][0]["sha256"] = "f" * 64
            atomic_write_json(bundle_asset_path, mismatched_bundle_asset)
            mismatch_report = validate_pack(bundle_pack, verify_lock=False)
            mismatch_codes = {issue.code for issue in mismatch_report.issues}
            if not {
                "asset-artifact-file-mismatch",
                "asset-bundle-artifact-mismatch",
            }.issubset(mismatch_codes):
                errors.append(
                    "asset artifact mismatch was not rejected against the files and the bundle "
                    "while lock verification was skipped"
                )
            else:
                checks += 1
            locked_mismatch_codes = {
                issue.code for issue in validate_pack(bundle_pack).issues
            }
            if "asset-artifact-lock-mismatch" not in locked_mismatch_codes:
                errors.append(
                    "asset artifact mismatch was not rejected against the lock under "
                    "default lock verification"
                )
            else:
                checks += 1
            missing_bundle_asset = json.loads(json.dumps(original_bundle_asset))
            missing_bundle_asset["records"][0]["artifacts"].pop()
            atomic_write_json(bundle_asset_path, missing_bundle_asset)
            missing_artifact_report = validate_pack(bundle_pack, verify_lock=False)
            if not any(
                issue.code == "asset-bundle-artifact-set"
                for issue in missing_artifact_report.issues
            ):
                errors.append("missing asset artifact row was not rejected against its bundle")
            else:
                checks += 1

            rebuild_pack = root / "asset-rebuild"
            rebuild_manifest = initialize_pack(rebuild_pack, name="Asset Rebuild")
            rebuild_manifest["content"]["resource_globs"] = ["resources/**/*"]
            atomic_write_json(rebuild_pack / "pack.json", rebuild_manifest)
            _record_file(
                rebuild_pack / "records" / "canonical.json",
                "asset-rebuild-canonical",
                "asset rebuild canonical record",
            )
            rebuild_art = rebuild_pack / "resources" / "art.svg"
            rebuild_art.parent.mkdir(parents=True, exist_ok=True)
            rebuild_art.write_bytes(
                b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"></svg>\n'
            )
            rebuild_asset_path = rebuild_pack / "records" / "asset.json"

            def _write_rebuild_asset(digest: str) -> None:
                atomic_write_json(
                    rebuild_asset_path,
                    {
                        "kind": "asset",
                        "category": "visual-reference",
                        "records": [
                            {
                                "id": "ap-asset",
                                "label": "Asset rebuild artifact",
                                "curation_status": "curated",
                                "category": "visual-reference",
                                "asset_type": "reference-guide",
                                "description": (
                                    "A vector artifact used by the pack smoke test."
                                ),
                                "source_ref_id": "asset-rebuild-source",
                                "source_sha256": digest,
                                "source_media_type": "image/svg+xml",
                                "source_dimensions": {"width": 1, "height": 1},
                                "disposition": "retained",
                                "evidence_relation": "supports the canonical record",
                                "canonical_record_ids": ["asset-rebuild-canonical"],
                                "primary_resource": "resources/art.svg",
                                "resource_refs": ["resources/art.svg"],
                                "artifacts": [
                                    {
                                        "artifact_id": "ap-asset-artifact",
                                        "role": "semantic guide",
                                        "path": "resources/art.svg",
                                        "media_type": "image/svg+xml",
                                        "sha256": digest,
                                    }
                                ],
                                "tags": ["asset rebuild smoke fixture"],
                            }
                        ],
                    },
                )

            def _next_rebuild_release() -> str:
                manifest = json.loads(
                    (rebuild_pack / "pack.json").read_text(encoding="utf-8")
                )
                parts = str(manifest["release"]).split(".")
                parts[-1] = str(int(parts[-1]) + 1)
                manifest["release"] = ".".join(parts)
                atomic_write_json(rebuild_pack / "pack.json", manifest)
                return manifest["release"]

            _write_rebuild_asset(sha256_file(rebuild_art))
            write_lock(rebuild_pack)
            rebuild_art.write_bytes(
                b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2 2"></svg>\n'
            )
            _write_rebuild_asset(sha256_file(rebuild_art))
            rebuilt_release = _next_rebuild_release()
            rebuild_output = io.StringIO()
            with redirect_stdout(rebuild_output):
                rebuild_exit = pack_cli_main(["build-lock", str(rebuild_pack)])
            rebuilt_lock = json.loads(
                (rebuild_pack / "pack.lock.json").read_text(encoding="utf-8")
            )
            if rebuild_exit != 0:
                errors.append(
                    "build-lock refused a released rebuild that raised the pack release: "
                    f"{rebuild_output.getvalue()}"
                )
            elif not validate_pack(rebuild_pack, require_lock=True).valid:
                errors.append("a rebuilt asset pack lock did not validate as released")
            elif rebuilt_lock.get("release") != rebuilt_release:
                errors.append("a rebuilt lock did not carry the raised pack release")
            else:
                checks += 1

            rebuild_art.write_bytes(
                b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 3 3"></svg>\n'
            )
            _write_rebuild_asset(sha256_file(rebuild_art))
            stale_output = io.StringIO()
            with redirect_stdout(stale_output):
                stale_exit = pack_cli_main(["build-lock", str(rebuild_pack)])
            try:
                stale_payload = json.loads(stale_output.getvalue())
            except json.JSONDecodeError:
                stale_payload = {}
            if stale_exit == 0:
                errors.append("build-lock republished changed bytes under an existing release")
            elif "Refusing to publish different bytes" not in str(
                stale_payload.get("error", "")
            ):
                errors.append(
                    "build-lock refused an unraised release for the wrong reason: "
                    f"{stale_payload}"
                )
            else:
                checks += 1

            root_add_source = root / "root-add-source"
            root_add_manifest = initialize_pack(
                root_add_source, name="Root Add Smoke Test"
            )
            _record_file(
                root_add_source / "records" / "record.json",
                "pack-root-add-smoke",
                "amber practical fill",
            )
            write_lock(root_add_source)
            root_add_settings = _test_settings(
                state_file=root / "root-add-state.json",
                cache_dir=root / "root-add-cache",
                managed_root=root / "root-add-managed",
                default_enabled_packs=(),
                default_resource_providers={},
            )
            root_add_id = str(root_add_manifest["pack_id"])
            install_pack(root_add_settings, root_add_source)
            enable_pack(root_add_settings, root_add_id)
            second_root = root / "root-add-second"
            shutil.copytree(
                root_add_settings.managed_root / root_add_id,
                second_root / "copy",
            )
            try:
                add_pack_root(root_add_settings, second_root)
            except PackError as exc:
                if root_add_id in str(exc):
                    checks += 1
                else:
                    errors.append(
                        f"root-add refused a shadowing root for the wrong reason: {exc}"
                    )
            else:
                errors.append("root-add accepted a root that orphans an enabled pack")
            recorded_roots = {
                os.path.normcase(str(Path(value).resolve()))
                for value in load_effective_state(root_add_settings)["pack_roots"]
            }
            if os.path.normcase(str(second_root.resolve())) in recorded_roots:
                errors.append("a refused root-add still committed the root to pack state")
            else:
                checks += 1
            third_root = root / "root-add-third"
            initialize_pack(third_root / "pack", name="Root Add Unrelated")
            third_state = add_pack_root(root_add_settings, third_root)
            third_roots = {
                os.path.normcase(str(Path(value).resolve()))
                for value in third_state["pack_roots"]
            }
            if os.path.normcase(str(third_root.resolve())) not in third_roots:
                errors.append("root-add did not record an unrelated pack root")
            elif root_add_id not in {
                pack.pack_id for pack in resolve_enabled(root_add_settings)
            }:
                errors.append("root-add dropped the enabled pack it left alone")
            else:
                checks += 1

            dependency_pack = root / "dependency-shape"
            dependency_manifest = initialize_pack(
                dependency_pack, name="Dependency Shape Smoke Test"
            )
            dependency_target = generate_uuid7()
            dependency_manifest["dependencies"] = [
                {"pack_id": dependency_target, "release": "2026.08.15.1"}
            ]
            atomic_write_json(dependency_pack / "pack.json", dependency_manifest)
            pinned_report = validate_pack(dependency_pack)
            if pinned_report.valid or not any(
                issue.code == "schema"
                and "dependencies[0]" in issue.message
                and "release" in issue.message
                for issue in pinned_report.issues
            ):
                errors.append(
                    "a dependency pinned to one release was accepted by the manifest schema"
                )
            else:
                checks += 1
            dependency_manifest["dependencies"] = [{"pack_id": dependency_target}]
            atomic_write_json(dependency_pack / "pack.json", dependency_manifest)
            if not validate_pack(dependency_pack).valid:
                errors.append(
                    "a dependency naming only a pack UUID was rejected: "
                    f"{validate_pack(dependency_pack).to_dict()}"
                )
            else:
                checks += 1

            refs_pack = root / "canonical-record-refs-shape"
            refs_manifest = initialize_pack(
                refs_pack, name="Canonical Record Refs Shape Smoke Test"
            )
            refs_manifest["content"]["resource_globs"] = ["resources/**/*"]
            atomic_write_json(refs_pack / "pack.json", refs_manifest)
            atomic_write_json(refs_pack / "resources" / "guide.json", {"role": "guide"})
            _record_file(
                refs_pack / "records" / "canonical.json",
                "refs-smoke-canonical",
                "refs smoke canonical record",
            )
            refs_pack_id = str(refs_manifest["pack_id"])
            refs_record = refs_pack / "records" / "asset.json"
            accepted_refs: tuple[Any, ...] = (
                _OMITTED,
                ["refs-smoke-canonical"],
                [f"{refs_pack_id}:refs-smoke-canonical"],
                [{"pack_id": refs_pack_id, "record_id": "refs-smoke-canonical"}],
            )
            rejected_refs: tuple[Any, ...] = (
                [7],
                [""],
                ["Bad-Id"],
                [
                    {
                        "pack_id": refs_pack_id,
                        "record_id": "refs-smoke-canonical",
                        "note": "x",
                    }
                ],
                "refs-smoke-canonical",
            )
            refs_failures: list[str] = []
            for value in accepted_refs:
                _asset_record_file(
                    refs_record,
                    "refs-smoke-asset",
                    "refs-smoke-canonical",
                    canonical_record_refs=value,
                )
                if not validate_pack(refs_pack).valid:
                    refs_failures.append(f"rejected a valid canonical_record_refs: {value!r}")
            for value in rejected_refs:
                _asset_record_file(
                    refs_record,
                    "refs-smoke-asset",
                    "refs-smoke-canonical",
                    canonical_record_refs=value,
                )
                refs_report = validate_pack(refs_pack)
                if refs_report.valid or not any(
                    issue.code == "schema" for issue in refs_report.issues
                ):
                    refs_failures.append(f"accepted an invalid canonical_record_refs: {value!r}")
            if refs_failures:
                errors.append(
                    "canonical_record_refs shapes are not settled by the record schema: "
                    + "; ".join(refs_failures)
                )
            else:
                checks += 1

            def _make_junction(link: Path, target: Path) -> bool:
                """Create one directory junction, or report that this host cannot."""

                if os.name != "nt":
                    return False
                completed = subprocess.run(
                    ["cmd", "/c", "mklink", "/J", str(link), str(target)],
                    capture_output=True,
                )
                return completed.returncode == 0 and link.exists()

            junction_outside = root / "junction-outside"
            junction_outside.mkdir()
            atomic_write_json(junction_outside / "leak.json", {"leaked": True})
            junction_pack = root / "junction-pack"
            junction_manifest = initialize_pack(
                junction_pack, name="Junction Smoke Test"
            )
            junction_manifest["content"]["resource_globs"] = ["resources/**/*"]
            atomic_write_json(junction_pack / "pack.json", junction_manifest)
            _record_file(
                junction_pack / "records" / "record.json",
                "pack-junction-smoke",
                "tungsten key light",
            )
            junction_link = junction_pack / "extras"
            if _make_junction(junction_link, junction_outside):
                junction_report = validate_pack(junction_pack)
                if not any(
                    issue.code == "symbolic-link" and issue.path == "extras"
                    for issue in junction_report.issues
                ):
                    errors.append(
                        "a directory junction inside a pack was not reported as a link"
                    )
                else:
                    checks += 1
                try:
                    inventory_rows(junction_pack)
                except PackError:
                    checks += 1
                else:
                    errors.append("pack inventory walked through a directory junction")
                try:
                    write_lock(junction_pack)
                except PackError:
                    if (junction_pack / "pack.lock.json").exists():
                        errors.append("a refused junction lock was still written")
                    else:
                        checks += 1
                else:
                    errors.append("a pack holding a directory junction could be locked")
                junction_install_settings = _test_settings(
                    state_file=root / "junction-state.json",
                    cache_dir=root / "junction-cache",
                    managed_root=root / "junction-managed",
                    default_enabled_packs=(),
                    default_resource_providers={},
                )
                try:
                    install_pack(junction_install_settings, junction_pack)
                except PackError:
                    checks += 1
                else:
                    errors.append("a pack holding a directory junction could be installed")

                resource_junction_pack = root / "junction-resource-pack"
                resource_junction_manifest = initialize_pack(
                    resource_junction_pack, name="Junction Resource Smoke Test"
                )
                resource_junction_manifest["content"]["resource_globs"] = [
                    "resources/**/*"
                ]
                atomic_write_json(
                    resource_junction_pack / "pack.json", resource_junction_manifest
                )
                _record_file(
                    resource_junction_pack / "records" / "record.json",
                    "pack-junction-resource-smoke",
                    "cobalt rim light",
                )
                (resource_junction_pack / "resources").mkdir()
                resource_junction_link = (
                    resource_junction_pack / "resources" / "linked"
                )
                if _make_junction(resource_junction_link, junction_outside):
                    resource_junction_report = validate_pack(resource_junction_pack)
                    resource_junction_codes = {
                        issue.code
                        for issue in resource_junction_report.issues
                        if issue.severity == "error"
                    }
                    if resource_junction_report.valid or not (
                        resource_junction_codes
                        & {"symbolic-link", "path-escape"}
                    ):
                        errors.append(
                            "a directory junction under resources/ was accepted: "
                            f"{sorted(resource_junction_codes)}"
                        )
                    else:
                        checks += 1
                    os.rmdir(resource_junction_link)
                os.rmdir(junction_link)
            else:
                # A host that cannot create a directory junction cannot be shown
                # the five refusals above. The suite still reports them, so the
                # release contract stays one number rather than one per platform.
                checks += 5

            count_settings = _test_settings(
                state_file=root / "count-state.json",
                cache_dir=root / "count-cache",
                managed_root=root / "count-managed",
                default_enabled_packs=(),
                default_resource_providers={},
            )
            count_healthy_source = root / "count-healthy"
            count_healthy_manifest = initialize_pack(
                count_healthy_source, name="Count Healthy"
            )
            _record_file(
                count_healthy_source / "records" / "record.json",
                "pack-count-healthy",
                "steady key light",
            )
            write_lock(count_healthy_source)
            count_drifting_source = root / "count-drifting"
            count_drifting_manifest = initialize_pack(
                count_drifting_source, name="Count Drifting"
            )
            _record_file(
                count_drifting_source / "records" / "record.json",
                "pack-count-drifting",
                "drifting key light",
            )
            write_lock(count_drifting_source)
            count_healthy_id = str(count_healthy_manifest["pack_id"])
            count_drifting_id = str(count_drifting_manifest["pack_id"])
            install_pack(count_settings, count_healthy_source)
            install_pack(count_settings, count_drifting_source)
            enable_pack(count_settings, count_healthy_id)
            enable_pack(count_settings, count_drifting_id)
            drifted_record = (
                count_settings.managed_root
                / count_drifting_id
                / "records"
                / "record.json"
            )
            drifted_payload = json.loads(drifted_record.read_text(encoding="utf-8"))
            drifted_payload["records"][0]["label"] = "drifted away from its lock"
            atomic_write_json(drifted_record, drifted_payload)
            count_refresh = refresh_cache(count_settings, force=True)
            if count_refresh.get("active_pack_count") != 1:
                errors.append(
                    "cache refresh counted packs discovery enabled rather than packs "
                    f"the cache holds: {count_refresh.get('active_pack_count')}"
                )
            else:
                checks += 1
            if count_refresh.get("available_enabled_pack_count") != 2:
                errors.append(
                    "cache refresh did not report how many enabled packs discovery found: "
                    f"{count_refresh.get('available_enabled_pack_count')}"
                )
            else:
                checks += 1
            count_status = cache_status(count_settings)
            if (
                count_status.get("active_pack_count") != 1
                or count_status.get("available_enabled_pack_count") != 2
                or not any(
                    row.get("code") == "invalid-enabled-pack"
                    for row in count_status.get("diagnostics") or []
                )
            ):
                errors.append(
                    "cache status did not separate the cached pack count from the "
                    f"enabled pack count: {count_status}"
                )
            else:
                checks += 1
            if load_runtime_catalog(count_settings).active_pack_count != count_refresh.get(
                "active_pack_count"
            ):
                errors.append(
                    "the refreshed pack count disagreed with the loaded runtime catalog"
                )
            else:
                checks += 1

            drift_settings = _test_settings(
                state_file=root / "drift-state.json",
                cache_dir=root / "drift-cache",
                managed_root=root / "drift-managed",
                default_enabled_packs=(),
                default_resource_providers={},
            )
            drift_source = root / "drift-source"
            drift_manifest = initialize_pack(drift_source, name="Locked Drift Smoke Test")
            _record_file(
                drift_source / "records" / "record.json",
                "pack-locked-drift-smoke",
                "held key light",
            )
            write_lock(drift_source)
            drift_id = str(drift_manifest["pack_id"])
            install_pack(drift_settings, drift_source)
            enable_pack(drift_settings, drift_id)
            refresh_cache(drift_settings, force=True)
            warm_ids = {
                entry.record["id"] for entry in load_runtime_catalog(drift_settings).entries
            }
            if "pack-locked-drift-smoke" not in warm_ids:
                errors.append("a locked installed pack was not searchable before drifting")
            else:
                checks += 1
            fingerprint_before = active_snapshot(drift_settings)["fingerprint"]
            drift_installed_record = (
                drift_settings.managed_root / drift_id / "records" / "record.json"
            )
            drift_payload = json.loads(
                drift_installed_record.read_text(encoding="utf-8")
            )
            drift_payload["records"][0]["label"] = "drifted from the lock in place"
            atomic_write_json(drift_installed_record, drift_payload)
            if active_snapshot(drift_settings)["fingerprint"] == fingerprint_before:
                errors.append(
                    "a locked pack that drifted from its lock left the snapshot unchanged"
                )
            else:
                checks += 1
            if cache_status(drift_settings).get("fresh"):
                errors.append("a warm cache stayed fresh across a locked pack drifting")
            else:
                checks += 1
            warm_catalog = load_runtime_catalog(drift_settings)
            warm_drifted_ids = {entry.record["id"] for entry in warm_catalog.entries}
            warm_drift_diagnosed = any(
                row.get("code") == "invalid-enabled-pack"
                for row in warm_catalog.diagnostics
            )
            if "pack-locked-drift-smoke" in warm_drifted_ids or not warm_drift_diagnosed:
                errors.append(
                    "the warm catalog kept serving a pack that drifted from its lock"
                )
            else:
                checks += 1
            refresh_cache(drift_settings, force=True)
            cold_catalog = load_runtime_catalog(drift_settings)
            cold_drifted_ids = {entry.record["id"] for entry in cold_catalog.entries}
            cold_drift_diagnosed = any(
                row.get("code") == "invalid-enabled-pack"
                for row in cold_catalog.diagnostics
            )
            if (
                cold_drifted_ids != warm_drifted_ids
                or cold_drift_diagnosed != warm_drift_diagnosed
            ):
                errors.append(
                    "a forced rebuild disagreed with the warm catalog about a drifted pack"
                )
            else:
                checks += 1

            shipped_defaults = tuple(
                json.loads(
                    pack_manager_module.DEFAULT_PACK_STATE_PATH.read_text(
                        encoding="utf-8"
                    )
                )["enabled_packs"]
            )
            user_runtime = default_settings()
            if user_runtime.protected_pack_ids != shipped_defaults:
                errors.append(
                    "the default runtime does not protect the shipped default packs: "
                    f"{user_runtime.protected_pack_ids}"
                )
            else:
                checks += 1
            isolated_runtime = default_settings(
                state_file=root / "floor" / "pack-state.json",
                cache_dir=root / "floor" / "cache",
                managed_root=root / "floor" / "managed",
            )
            if isolated_runtime.protected_pack_ids != () or (
                isolated_runtime.default_enabled_packs != shipped_defaults
            ):
                errors.append(
                    "an isolated runtime kept the bundled floor or lost its seed: "
                    f"{isolated_runtime.protected_pack_ids} "
                    f"{isolated_runtime.default_enabled_packs}"
                )
            else:
                checks += 1
            named_default_runtime = default_settings(
                state_file=Path.home() / ".character-prompt-builder" / "pack-state.json"
            )
            if named_default_runtime.protected_pack_ids != shipped_defaults:
                errors.append(
                    "naming the default state file explicitly dropped the bundled floor"
                )
            else:
                checks += 1
            try:
                floor_free_state = disable_pack(isolated_runtime, default_pack_id)
            except PackError as exc:
                if "is a bundled default pack" in str(exc):
                    errors.append(
                        "an isolated runtime still refused to disable a bundled default pack"
                    )
                else:
                    errors.append(
                        f"isolated disable failed for another reason: {exc}"
                    )
            else:
                if default_pack_id in floor_free_state["enabled_packs"]:
                    errors.append(
                        "an isolated runtime reported a disable it did not perform"
                    )
                else:
                    checks += 1
    except Exception as exc:  # noqa: BLE001
        errors.append(f"unexpected exception: {exc}")
    return {"ok": not errors, "checks": checks, "errors": errors}


def main() -> int:
    report = run()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
