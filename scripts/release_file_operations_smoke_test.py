#!/usr/bin/env python3
"""Focused regression for additive release staging and explicit inventory."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from collections import Counter
from pathlib import Path
from unittest import mock

import package as package_module
from package import (
    _cleanup_attempt_directory,
    _copy_file_writable,
    _copy_tree_writable,
    _remove_owned_output,
    archive_content_sha256,
    copy_runtime_tree,
    publish_validated_outputs,
    resolve_archive_path,
    validate_keep_stage_destination,
    verify_archive_reproducibility,
    write_deterministic_zip,
)
from package_metadata import (
    CORE_EVALUATION_INCLUDES,
    CORE_EXAMPLE_INCLUDES,
    load_package_metadata,
    pep440_version_for_calver,
    iter_release_files,
    validate_core_release_includes,
    validate_pack_gitignore_contract,
    validate_pyproject_release_identity,
    validate_skill_frontmatter_contract,
)
from rebuild_metadata import build_catalog_document

ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_owner_writable(path: Path) -> bool:
    return bool(stat.S_IMODE(path.stat().st_mode) & stat.S_IWUSR)


def _make_read_only(path: Path) -> None:
    path.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)


def main() -> int:
    errors: list[str] = []
    checks = 0
    with tempfile.TemporaryDirectory(prefix="cpb-release-files-") as temp:
        # Resolve once: the inventories compared below are resolved, so a
        # non-canonical temporary directory would fail relative_to().
        root = Path(temp).resolve()
        metadata = load_package_metadata(ROOT)
        expected_pyproject_version = pep440_version_for_calver(metadata.version)
        observed_identity = {
            "product_release": metadata.version,
            "pyproject": metadata.pyproject_version,
            "artifact": metadata.release_artifact_name,
        }
        expected_identity = {
            "product_release": metadata.version,
            "pyproject": expected_pyproject_version,
            "artifact": f"{metadata.name}-{metadata.version}.zip",
        }
        if observed_identity != expected_identity:
            errors.append(
                f"product release identity mismatch: expected {expected_identity}, "
                f"got {observed_identity}"
            )
        else:
            checks += 1

        with (ROOT / metadata.pyproject_file).open("rb") as stream:
            pyproject = tomllib.load(stream)
        validated_pyproject_version = validate_pyproject_release_identity(
            pyproject,
            package_name=metadata.name,
            package_version=metadata.version,
        )
        if validated_pyproject_version != expected_pyproject_version:
            errors.append("valid normalized pyproject release identity was not retained")
        else:
            checks += 1
        for invalid_version in (
            "0" + expected_pyproject_version,
            expected_pyproject_version + ".0",
        ):
            invalid_pyproject = {
                **pyproject,
                "project": {
                    **pyproject["project"],
                    "version": invalid_version,
                },
            }
            try:
                validate_pyproject_release_identity(
                    invalid_pyproject,
                    package_name=metadata.name,
                    package_version=metadata.version,
                )
                errors.append(
                    f"invalid pyproject release spelling was accepted: {invalid_version!r}"
                )
            except ValueError:
                checks += 1

        try:
            skill_fields = validate_skill_frontmatter_contract(
                ROOT / "SKILL.md", expected_name=metadata.name
            )
            if set(skill_fields) != {"name", "description"}:
                errors.append(
                    f"SKILL front matter retained unexpected fields: {sorted(skill_fields)}"
                )
            else:
                checks += 1
        except ValueError as exc:
            errors.append(f"canonical SKILL front matter was rejected: {exc}")

        skill_contract_mutations = (
            (
                "extra version field",
                "---\n"
                f"name: {metadata.name}\n"
                'description: "Build character prompts."\n'
                f"version: {metadata.version}\n"
                "---\n",
            ),
            (
                "nested metadata field",
                "---\n"
                f"name: {metadata.name}\n"
                'description: "Build character prompts."\n'
                "metadata:\n"
                "  release: forbidden\n"
                "---\n",
            ),
            (
                "missing description",
                f"---\nname: {metadata.name}\n---\n",
            ),
            (
                "wrong skill name",
                "---\n"
                "name: another-skill\n"
                'description: "Build character prompts."\n'
                "---\n",
            ),
            (
                "null description",
                f"---\nname: {metadata.name}\ndescription: null\n---\n",
            ),
            (
                "boolean description",
                f"---\nname: {metadata.name}\ndescription: true\n---\n",
            ),
            (
                "array description",
                f"---\nname: {metadata.name}\ndescription: []\n---\n",
            ),
            (
                "object description",
                f"---\nname: {metadata.name}\ndescription: {{}}\n---\n",
            ),
            (
                "date description",
                f"---\nname: {metadata.name}\ndescription: 2026-08-16\n---\n",
            ),
            (
                "positive infinity description",
                f"---\nname: {metadata.name}\ndescription: .inf\n---\n",
            ),
            (
                "not-a-number description",
                f"---\nname: {metadata.name}\ndescription: .nan\n---\n",
            ),
            (
                "hexadecimal description",
                f"---\nname: {metadata.name}\ndescription: 0x10\n---\n",
            ),
            (
                "sexagesimal description",
                f"---\nname: {metadata.name}\ndescription: 1:20\n---\n",
            ),
            (
                "mapping-key description",
                f"---\nname: {metadata.name}\ndescription: ? question\n---\n",
            ),
            (
                "sequence-item description",
                f"---\nname: {metadata.name}\ndescription: - item\n---\n",
            ),
            (
                "directive description",
                f"---\nname: {metadata.name}\ndescription: %TAG\n---\n",
            ),
            (
                "terminal-colon description",
                f"---\nname: {metadata.name}\ndescription: a:\n---\n",
            ),
            (
                "double-terminal-colon description",
                f"---\nname: {metadata.name}\ndescription: a::\n---\n",
            ),
            (
                "tab description",
                f"---\nname: {metadata.name}\ndescription: a\tb\n---\n",
            ),
            (
                "nul description",
                f"---\nname: {metadata.name}\ndescription: a\x00b\n---\n",
            ),
            (
                "missing name separator space",
                f"---\nname:{metadata.name}\ndescription: Build prompts.\n---\n",
            ),
            (
                "missing description separator space",
                f"---\nname: {metadata.name}\ndescription:Build prompts.\n---\n",
            ),
            (
                "leading tab after separator",
                f"---\nname: {metadata.name}\ndescription:\tBuild prompts.\n---\n",
            ),
            (
                "trailing tab description",
                f"---\nname: {metadata.name}\ndescription: Build prompts.\t\n---\n",
            ),
            (
                "leading nul description",
                f"---\nname: {metadata.name}\ndescription: \x00Build prompts.\n---\n",
            ),
            (
                "trailing nul description",
                f"---\nname: {metadata.name}\ndescription: Build prompts.\x00\n---\n",
            ),
            (
                "vertical-tab description",
                f"---\nname: {metadata.name}\ndescription: Build\x0bprompts.\n---\n",
            ),
            (
                "form-feed description",
                f"---\nname: {metadata.name}\ndescription: Build\x0cprompts.\n---\n",
            ),
            (
                "file-separator description",
                f"---\nname: {metadata.name}\ndescription: Build\x1cprompts.\n---\n",
            ),
            (
                "c1-control description",
                f"---\nname: {metadata.name}\ndescription: Build\x80prompts.\n---\n",
            ),
            (
                "fffe-noncharacter description",
                f"---\nname: {metadata.name}\ndescription: Build\ufffeprompts.\n---\n",
            ),
            (
                "ffff-noncharacter description",
                f"---\nname: {metadata.name}\ndescription: Build\uffffprompts.\n---\n",
            ),
            (
                "escaped tab description",
                f'---\nname: {metadata.name}\ndescription: "Build\\tprompts."\n---\n',
            ),
            (
                "escaped c1-control description",
                f'---\nname: {metadata.name}\ndescription: "Build\\u0080prompts."\n---\n',
            ),
            (
                "escaped noncharacter description",
                f'---\nname: {metadata.name}\ndescription: "Build\\ufffeprompts."\n---\n',
            ),
            (
                "next-line description",
                f"---\nname: {metadata.name}\ndescription: Build\u0085prompts.\n---\n",
            ),
            (
                "line-separator description",
                f"---\nname: {metadata.name}\ndescription: Build\u2028prompts.\n---\n",
            ),
            (
                "paragraph-separator description",
                f"---\nname: {metadata.name}\ndescription: Build\u2029prompts.\n---\n",
            ),
        )
        for label, source in skill_contract_mutations:
            mutation_path = root / f"skill-{label.replace(' ', '-')}.md"
            mutation_path.write_text(source, encoding="utf-8")
            try:
                validate_skill_frontmatter_contract(
                    mutation_path, expected_name=metadata.name
                )
                errors.append(f"SKILL front matter accepted {label}")
            except ValueError:
                checks += 1

        try:
            validate_core_release_includes(metadata.release_include)
            checks += 1
        except ValueError as exc:
            errors.append(f"canonical core release includes were rejected: {exc}")
        invalid_include_sets = (
            (
                "broad evals directory",
                [
                    value
                    for value in metadata.release_include
                    if value not in CORE_EVALUATION_INCLUDES
                ]
                + ["evals"],
            ),
            (
                "broad examples directory",
                [
                    value
                    for value in metadata.release_include
                    if value not in CORE_EXAMPLE_INCLUDES
                ]
                + ["examples"],
            ),
            (
                "non-default pack",
                [*metadata.release_include, "packs/third-party-fixture"],
            ),
        )
        for label, invalid_include in invalid_include_sets:
            try:
                validate_core_release_includes(invalid_include)
                errors.append(f"core release accepted {label}")
            except ValueError:
                checks += 1

        gitignore_text = (ROOT / ".gitignore").read_text(encoding="utf-8")
        try:
            validate_pack_gitignore_contract(gitignore_text)
            checks += 1
        except ValueError as exc:
            errors.append(f"canonical pack .gitignore contract was rejected: {exc}")
        gitignore_mutations = (
            (
                "non-default unignore",
                gitignore_text + "\n!packs/third-party-fixture/**\n",
            ),
            (
                "missing pack ignore",
                gitignore_text.replace("/packs/*\n", "", 1),
            ),
            (
                "reordered default unignores",
                gitignore_text.replace(
                    "!/packs/commons/\n!/packs/commons/**",
                    "!/packs/commons/**\n!/packs/commons/",
                    1,
                ),
            ),
        )
        for label, mutation in gitignore_mutations:
            try:
                validate_pack_gitignore_contract(mutation)
                errors.append(f"pack .gitignore accepted {label}")
            except ValueError:
                checks += 1

        validate_source = (ROOT / "scripts" / "validate.py").read_text(
            encoding="utf-8"
        )
        current_scope_phrase = (
            "pack-declared reference-corpus disposition and full "
            "declared-bundle validation"
        )
        if current_scope_phrase not in validate_source:
            errors.append("validation scope omits the reference-corpus contract")
        else:
            checks += 1

        canonical_archive = (ROOT / metadata.release_output).resolve()
        if resolve_archive_path(ROOT, metadata.release_output, None) != canonical_archive:
            errors.append("default archive path differs from release.output")
        else:
            checks += 1
        alternate_archive = root / "alternate" / metadata.release_artifact_name
        if (
            resolve_archive_path(
                ROOT, metadata.release_output, str(alternate_archive)
            )
            != alternate_archive.resolve()
        ):
            errors.append("canonical archive filename was rejected in an alternate directory")
        else:
            checks += 1
        try:
            resolve_archive_path(
                ROOT,
                metadata.release_output,
                str(root / "character-prompt-builder-stale.zip"),
            )
            errors.append("release archive accepted a filename without canonical identity")
        except ValueError:
            checks += 1

        zip_mode_root = root / "zip-mode"
        left_root = zip_mode_root / "left" / metadata.name
        right_root = zip_mode_root / "right" / metadata.name
        for source_root in (left_root, right_root):
            (source_root / "nested").mkdir(parents=True)
            (source_root / "README.md").write_text(
                "same content\n", encoding="utf-8"
            )
            (source_root / "nested" / "tool.py").write_text(
                "print('same')\n", encoding="utf-8"
            )
        left_files = (left_root / "README.md", left_root / "nested" / "tool.py")
        right_files = (
            right_root / "README.md",
            right_root / "nested" / "tool.py",
        )
        try:
            for path in left_files:
                os.chmod(path, 0o400)
            for path in right_files:
                os.chmod(path, 0o600)
            left_source_modes = tuple(
                stat.S_IMODE(path.stat().st_mode) for path in left_files
            )
            right_source_modes = tuple(
                stat.S_IMODE(path.stat().st_mode) for path in right_files
            )
            left_zip = zip_mode_root / "left.zip"
            right_zip = zip_mode_root / "right.zip"
            write_deterministic_zip(left_root, left_zip)
            write_deterministic_zip(right_root, right_zip)
        finally:
            for path in (*left_files, *right_files):
                if path.exists():
                    os.chmod(path, 0o600)

        if (
            left_source_modes == right_source_modes
            or left_zip.read_bytes() != right_zip.read_bytes()
        ):
            errors.append(
                "deterministic ZIP bytes changed with host permissions: "
                f"left={left_source_modes}, right={right_source_modes}"
            )
        else:
            checks += 1

        with zipfile.ZipFile(left_zip) as archive:
            file_modes = {
                info.filename: (
                    info.create_system,
                    (info.external_attr >> 16) & 0o7777,
                )
                for info in archive.infolist()
                if not info.is_dir()
            }
            directory_modes = {
                info.filename: (
                    info.create_system,
                    (info.external_attr >> 16) & 0o7777,
                )
                for info in archive.infolist()
                if info.is_dir()
            }
        if (
            not file_modes
            or any(value != (3, 0o644) for value in file_modes.values())
            or not directory_modes
            or any(value != (3, 0o755) for value in directory_modes.values())
        ):
            errors.append(
                "deterministic ZIP did not record canonical Unix modes: "
                f"files={file_modes}, directories={directory_modes}"
            )
        else:
            checks += 1

        stored_zip = zip_mode_root / "stored.zip"
        with zipfile.ZipFile(left_zip) as source_archive:
            with zipfile.ZipFile(stored_zip, "w") as target_archive:
                for info in source_archive.infolist():
                    stored_info = copy.copy(info)
                    stored_info.compress_type = zipfile.ZIP_STORED
                    target_archive.writestr(
                        stored_info, source_archive.read(info.filename)
                    )
        deflated_content_hash = archive_content_sha256(left_zip)
        stored_content_hash = archive_content_sha256(stored_zip)
        if (
            deflated_content_hash != stored_content_hash
            or left_zip.read_bytes() == stored_zip.read_bytes()
        ):
            errors.append(
                "archive content digest changed with compression method: "
                f"deflated={deflated_content_hash}, stored={stored_content_hash}"
            )
        else:
            checks += 1

        # A reproducibility claim nothing rebuilds is a claim nothing checks.
        reproducible_root = root / "archive-reproducibility"
        reproducible_stage = reproducible_root / metadata.name
        (reproducible_stage / "nested").mkdir(parents=True)
        (reproducible_stage / "README.md").write_text(
            "reproducible content\n" * 20, encoding="utf-8", newline="\n"
        )
        (reproducible_stage / "nested" / "tool.py").write_text(
            "print('reproducible')\n", encoding="utf-8", newline="\n"
        )
        clean_archive = reproducible_root / "clean.zip"
        write_deterministic_zip(reproducible_stage, clean_archive)
        clean_reproducibility = verify_archive_reproducibility(
            reproducible_stage, clean_archive, reproducible_root / "clean-work"
        )
        if clean_reproducibility != {
            "zip_crc_ok": True,
            "deterministic_rebuild": True,
            "failed_member": None,
        }:
            errors.append(
                f"clean archive was not reported reproducible: {clean_reproducibility}"
            )
        else:
            checks += 1

        # Stored members make the injected damage a CRC mismatch on every zlib
        # build, rather than a decompression error whose type varies by
        # implementation. The check under test is the member CRC either way.
        corrupt_archive = reproducible_root / "corrupt.zip"
        with zipfile.ZipFile(clean_archive) as source_archive:
            with zipfile.ZipFile(corrupt_archive, "w") as target_archive:
                for info in source_archive.infolist():
                    stored_info = copy.copy(info)
                    stored_info.compress_type = zipfile.ZIP_STORED
                    target_archive.writestr(
                        stored_info, source_archive.read(info.filename)
                    )
        with zipfile.ZipFile(corrupt_archive) as archive_handle:
            damaged_member = next(
                info
                for info in archive_handle.infolist()
                if not info.is_dir() and info.file_size
            )
        corrupt_bytes = bytearray(corrupt_archive.read_bytes())
        header = damaged_member.header_offset
        name_length = int.from_bytes(corrupt_bytes[header + 26:header + 28], "little")
        extra_length = int.from_bytes(corrupt_bytes[header + 28:header + 30], "little")
        corrupt_bytes[header + 30 + name_length + extra_length] ^= 0xFF
        corrupt_archive.write_bytes(bytes(corrupt_bytes))
        corrupt_reproducibility = verify_archive_reproducibility(
            reproducible_stage, corrupt_archive, reproducible_root / "corrupt-work"
        )
        packager_source = (ROOT / "scripts" / "package.py").read_text(encoding="utf-8")
        if (
            corrupt_reproducibility["zip_crc_ok"]
            or corrupt_reproducibility["failed_member"] != damaged_member.filename
            or corrupt_reproducibility["deterministic_rebuild"]
            or "candidate ZIP CRC failed at" not in packager_source
            or "candidate archive rebuild is not byte-identical" not in packager_source
        ):
            errors.append(
                "corrupt archive member was not reported or does not stop publication: "
                f"{corrupt_reproducibility}"
            )
        else:
            checks += 1

        source = root / "source"
        runtime = source / "runtime"
        nested = runtime / "nested"
        nested.mkdir(parents=True)
        (runtime / "one.txt").write_text("one\n", encoding="utf-8")
        (nested / "two.txt").write_text("two\n", encoding="utf-8")
        (runtime / "validation-report.json").write_text("{}\n", encoding="utf-8")
        (source / "outside.txt").write_text("outside\n", encoding="utf-8")

        inventory = iter_release_files(source, ["runtime"])
        relative_inventory = [
            path.relative_to(source).as_posix() for path in inventory
        ]
        expected = ["runtime/nested/two.txt", "runtime/one.txt"]
        if relative_inventory != expected:
            errors.append(
                f"explicit inventory mismatch: expected {expected}, got {relative_inventory}"
            )
        else:
            checks += 1
        if "outside.txt" in relative_inventory:
            errors.append("undeclared sibling entered explicit release inventory")
        else:
            checks += 1
        if "runtime/validation-report.json" in relative_inventory:
            errors.append("generated report entered explicit release inventory")
        else:
            checks += 1

        stage = root / "stage"
        copy_runtime_tree(source, stage, ["runtime"])
        staged = sorted(
            path.relative_to(stage).as_posix()
            for path in stage.rglob("*")
            if path.is_file()
        )
        if staged != expected:
            errors.append(f"staged tree does not match shared inventory: {staged}")
        else:
            checks += 1

        readonly_source = root / "readonly-metadata-source"
        copy_runtime_tree(
            ROOT,
            readonly_source,
            metadata.release_include,
            exclude_names=metadata.release_exclude_names,
        )
        generated_relative_paths = (
            Path("references/catalog-index.md"),
            Path("config/integration-capabilities.json"),
            Path("templates/handoff/interchange-envelope.template.json"),
        )
        readonly_generated = tuple(
            readonly_source / relative for relative in generated_relative_paths
        )
        source_hashes_before = {
            relative.as_posix(): _sha256(readonly_source / relative)
            for relative in generated_relative_paths
        }
        for path in readonly_generated:
            _make_read_only(path)
        source_modes_before = {
            relative.as_posix(): stat.S_IMODE((readonly_source / relative).stat().st_mode)
            for relative in generated_relative_paths
        }
        metadata_stage = root / "writable-metadata-stage"
        try:
            copy_runtime_tree(
                readonly_source,
                metadata_stage,
                metadata.release_include,
                exclude_names=metadata.release_exclude_names,
            )
            staged_hashes_before = {
                relative.as_posix(): _sha256(metadata_stage / relative)
                for relative in generated_relative_paths
            }
            if staged_hashes_before != source_hashes_before:
                errors.append(
                    "release stage changed generated metadata bytes while removing source permissions"
                )
            else:
                checks += 1
            if not all(
                _is_owner_writable(metadata_stage / relative)
                for relative in generated_relative_paths
            ):
                errors.append("release stage inherited a read-only generated metadata mode")
            else:
                checks += 1

            rebuild_result = subprocess.run(
                [sys.executable, "scripts/rebuild_metadata.py"],
                cwd=metadata_stage,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                text=True,
                encoding="utf-8",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            if rebuild_result.returncode != 0:
                errors.append(
                    "atomic metadata rebuild failed in a stage copied from read-only sources: "
                    f"{rebuild_result.stderr.strip()}"
                )
            elif not all(
                _is_owner_writable(metadata_stage / relative)
                for relative in generated_relative_paths
            ):
                errors.append("atomic metadata rebuild left generated stage files read-only")
            else:
                checks += 1

            source_hashes_after = {
                relative.as_posix(): _sha256(readonly_source / relative)
                for relative in generated_relative_paths
            }
            source_modes_after = {
                relative.as_posix(): stat.S_IMODE(
                    (readonly_source / relative).stat().st_mode
                )
                for relative in generated_relative_paths
            }
            if (
                source_hashes_after != source_hashes_before
                or source_modes_after != source_modes_before
            ):
                errors.append("staging or metadata rebuild modified a read-only source")
            else:
                checks += 1
        finally:
            for path in readonly_generated:
                if path.exists():
                    path.chmod(stat.S_IRUSR | stat.S_IWUSR)

        occupied = root / "occupied"
        occupied.mkdir()
        sentinel = occupied / "user-data.txt"
        sentinel.write_text("preserve\n", encoding="utf-8")
        try:
            validate_keep_stage_destination(occupied, source, ["runtime"])
            errors.append("pre-existing retained-stage destination was accepted")
        except FileExistsError:
            checks += 1
        if sentinel.read_text(encoding="utf-8") != "preserve\n":
            errors.append("retained-stage validation modified pre-existing data")
        else:
            checks += 1

        try:
            iter_release_files(source, ["missing"])
            errors.append("missing explicit release input was accepted")
        except FileNotFoundError:
            checks += 1

        metadata_paths = (ROOT / "MANIFEST.json", ROOT / "references" / "catalog-index.md")
        before = {path: _sha256(path) for path in metadata_paths}
        help_result = subprocess.run(
            [sys.executable, "scripts/rebuild_metadata.py", "--help"],
            cwd=ROOT,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        after = {path: _sha256(path) for path in metadata_paths}
        if help_result.returncode != 0 or "usage:" not in help_result.stdout.lower():
            errors.append("rebuild_metadata.py --help did not exit successfully")
        else:
            checks += 1
        if before != after:
            errors.append("rebuild_metadata.py --help modified release metadata")
        else:
            checks += 1

        try:
            build_catalog_document(
                {
                    "record_families": {},
                    "module_categories": {},
                    "total_records": 0,
                },
                Counter(),
                Counter(),
                0,
            )
            errors.append("metadata rebuild accepted a release with no authored default pack")
        except ValueError:
            checks += 1

        main_failure_root = root / "main-extracted-validation-failure"
        main_failure_archive = main_failure_root / metadata.release_artifact_name
        main_failure_sha = main_failure_archive.with_suffix(
            main_failure_archive.suffix + ".sha256"
        )
        main_failure_reports = main_failure_root / "reports"
        main_failure_stage = main_failure_root / "retained-stage"
        injected_extracted_validation_error = RuntimeError(
            "injected extracted candidate validation failure"
        )
        validation_prefixes: list[str] = []

        def fail_extracted_candidate_validation(
            stage_root: Path,
            reports_dir: Path,
            prefix: str,
            runtime_root: Path,
            *,
            expected_contract: dict[str, object] | None = None,
        ) -> tuple[dict[str, object], dict[str, object]]:
            del reports_dir, runtime_root
            validation_prefixes.append(prefix)
            if prefix == "staged":
                if expected_contract is not None:
                    raise AssertionError(
                        "staged validation unexpectedly received an extracted contract"
                    )
                return {}, {"fixture": "staged-contract"}
            if prefix == "extracted":
                if expected_contract != {"fixture": "staged-contract"}:
                    raise AssertionError(
                        "extracted validation did not receive the staged contract"
                    )
                if not stage_root.is_dir():
                    raise AssertionError("extracted candidate tree is absent")
                raise injected_extracted_validation_error
            raise AssertionError(f"unexpected validation prefix: {prefix}")

        try:
            with (
                mock.patch.object(
                    package_module,
                    "validate_stage",
                    side_effect=fail_extracted_candidate_validation,
                ),
                mock.patch.object(package_module, "progress"),
            ):
                package_module.main(
                    [
                        "--source",
                        str(ROOT),
                        "--out",
                        str(main_failure_archive),
                        "--reports-dir",
                        str(main_failure_reports),
                        "--keep-stage",
                        str(main_failure_stage),
                    ]
                )
            errors.append("package.main accepted failed extracted validation")
        except RuntimeError as exc:
            leaked_attempts = (
                list(
                    main_failure_root.glob(
                        f".{main_failure_archive.stem}-candidate-*"
                    )
                )
                if main_failure_root.is_dir()
                else []
            )
            final_targets = (
                main_failure_archive,
                main_failure_sha,
                main_failure_reports,
                main_failure_stage,
            )
            if (
                exc is injected_extracted_validation_error
                and validation_prefixes == ["staged", "extracted"]
                and not any(path.exists() or path.is_symlink() for path in final_targets)
                and not leaked_attempts
            ):
                checks += 1
            else:
                errors.append(
                    "failed extracted validation did not remain fully unpublished: "
                    f"error={exc!r}, prefixes={validation_prefixes}, "
                    f"existing={[str(path) for path in final_targets if path.exists() or path.is_symlink()]}, "
                    f"attempts={[str(path) for path in leaked_attempts]}"
                )

        publication = root / "publication"
        candidate = publication / "candidate"
        candidate_reports = candidate / "reports"
        candidate_stage = candidate / "retained-stage"
        candidate_reports.mkdir(parents=True)
        candidate_archive = candidate / "release.zip"
        candidate_sha = candidate / "release.zip.sha256"
        candidate_archive.write_bytes(b"validated archive candidate\n")
        candidate_sha.write_text("digest  release.zip\n", encoding="utf-8")
        (candidate_reports / "release-success.json").write_text(
            '{"ok": true}\n', encoding="utf-8"
        )
        retained_source = candidate / "validated-stage-source"
        retained_source.mkdir()
        retained_source_file = retained_source / "runtime.txt"
        retained_source_file.write_text(
            "validated stage\n", encoding="utf-8"
        )
        retained_source_hash = _sha256(retained_source_file)
        _make_read_only(retained_source_file)
        retained_source_mode = stat.S_IMODE(retained_source_file.stat().st_mode)
        _copy_tree_writable(retained_source, candidate_stage)
        candidate_stage_file = candidate_stage / "runtime.txt"
        if (
            _sha256(candidate_stage_file) != retained_source_hash
            or not _is_owner_writable(candidate_stage_file)
            or _sha256(retained_source_file) != retained_source_hash
            or stat.S_IMODE(retained_source_file.stat().st_mode) != retained_source_mode
        ):
            errors.append(
                "candidate retained-stage copy changed bytes, inherited read-only mode, "
                "or modified its source"
            )
        else:
            checks += 1
        _make_read_only(candidate_stage_file)
        published_archive = publication / "published" / "release.zip"
        published_sha = publication / "published" / "release.zip.sha256"
        published_reports = publication / "published" / "reports"
        published_stage = publication / "published" / "retained-stage"
        publish_validated_outputs(
            candidate_archive=candidate_archive,
            candidate_sha_path=candidate_sha,
            candidate_reports_dir=candidate_reports,
            archive=published_archive,
            sha_path=published_sha,
            reports_dir=published_reports,
            candidate_keep_stage=candidate_stage,
            keep_stage=published_stage,
        )
        if not all(
            path.exists()
            for path in (
                published_archive,
                published_sha,
                published_reports / "release-success.json",
                published_stage / "runtime.txt",
            )
        ):
            errors.append("validated publication did not produce every release output")
        else:
            checks += 1
        if candidate_archive.exists():
            errors.append("archive publication did not use the final atomic move")
        else:
            checks += 1
        if (
            _sha256(published_stage / "runtime.txt") != retained_source_hash
            or not _is_owner_writable(published_stage / "runtime.txt")
        ):
            errors.append(
                "published retained stage changed bytes or inherited read-only mode"
            )
        else:
            checks += 1
        retained_source_file.chmod(stat.S_IRUSR | stat.S_IWUSR)
        candidate_stage_file.chmod(stat.S_IRUSR | stat.S_IWUSR)

        rollback_candidate = publication / "rollback-candidate"
        rollback_reports = rollback_candidate / "reports"
        rollback_reports.mkdir(parents=True)
        rollback_archive = rollback_candidate / "release.zip"
        rollback_sha = rollback_candidate / "release.zip.sha256"
        rollback_stage = rollback_candidate / "retained-stage"
        rollback_stage.mkdir()
        rollback_stage_file = rollback_stage / "runtime.txt"
        rollback_stage_file.write_text("read-only candidate stage\n", encoding="utf-8")
        _make_read_only(rollback_stage_file)
        rollback_archive.write_bytes(b"must remain unpublished\n")
        rollback_sha.write_text("digest  release.zip\n", encoding="utf-8")
        (rollback_reports / "release-success.json").write_text(
            '{"ok": true}\n', encoding="utf-8"
        )
        failed_root = publication / "failed-publication"
        failed_archive = failed_root / "release.zip"
        failed_sha = failed_root / "release.zip.sha256"
        failed_reports = failed_root / "reports"
        failed_stage = failed_root / "retained-stage"
        injected_checksum_error = OSError("injected checksum failure")

        def fail_checksum_copy(
            source_path: str | os.PathLike[str],
            destination_path: str | os.PathLike[str],
            *,
            follow_symlinks: bool = True,
        ) -> str:
            if Path(source_path) == rollback_sha:
                raise injected_checksum_error
            return _copy_file_writable(
                source_path,
                destination_path,
                follow_symlinks=follow_symlinks,
            )

        try:
            with mock.patch(
                "package._copy_file_writable", side_effect=fail_checksum_copy
            ):
                publish_validated_outputs(
                    candidate_archive=rollback_archive,
                    candidate_sha_path=rollback_sha,
                    candidate_reports_dir=rollback_reports,
                    archive=failed_archive,
                    sha_path=failed_sha,
                    reports_dir=failed_reports,
                    candidate_keep_stage=rollback_stage,
                    keep_stage=failed_stage,
                )
            errors.append("publication accepted an injected pre-archive failure")
        except OSError as exc:
            if exc is not injected_checksum_error:
                errors.append(
                    f"publication did not preserve the original checksum OSError: {exc}"
                )
            else:
                checks += 1
        if any(
            path.exists() or path.is_symlink()
            for path in (failed_archive, failed_sha, failed_reports, failed_stage)
        ):
            errors.append("failed pre-archive publication left a release output behind")
        else:
            checks += 1
        if not rollback_archive.is_file():
            errors.append("failed pre-archive publication consumed its candidate archive")
        else:
            checks += 1
        rollback_stage_file.chmod(stat.S_IRUSR | stat.S_IWUSR)

        incomplete_candidate = publication / "incomplete-rollback-candidate"
        incomplete_reports = incomplete_candidate / "reports"
        incomplete_reports.mkdir(parents=True)
        incomplete_archive = incomplete_candidate / "release.zip"
        incomplete_sha = incomplete_candidate / "release.zip.sha256"
        incomplete_archive.write_bytes(b"must remain a candidate\n")
        incomplete_sha.write_text("digest  release.zip\n", encoding="utf-8")
        (incomplete_reports / "release-success.json").write_text(
            '{"ok": true}\n', encoding="utf-8"
        )
        incomplete_root = publication / "incomplete-rollback-output"
        incomplete_output_archive = incomplete_root / "release.zip"
        incomplete_output_sha = incomplete_root / "release.zip.sha256"
        incomplete_output_reports = incomplete_root / "reports"
        original_publication_error = OSError("injected original publication failure")
        rollback_cleanup_error = OSError("injected rollback cleanup failure")

        def fail_incomplete_checksum_copy(
            source_path: str | os.PathLike[str],
            destination_path: str | os.PathLike[str],
            *,
            follow_symlinks: bool = True,
        ) -> str:
            if Path(source_path) == incomplete_sha:
                raise original_publication_error
            return _copy_file_writable(
                source_path,
                destination_path,
                follow_symlinks=follow_symlinks,
            )

        def fail_reports_rollback(path: Path) -> None:
            if path == incomplete_output_reports:
                raise rollback_cleanup_error
            _remove_owned_output(path)

        try:
            with (
                mock.patch(
                    "package._copy_file_writable",
                    side_effect=fail_incomplete_checksum_copy,
                ),
                mock.patch(
                    "package._remove_owned_output",
                    side_effect=fail_reports_rollback,
                ),
            ):
                publish_validated_outputs(
                    candidate_archive=incomplete_archive,
                    candidate_sha_path=incomplete_sha,
                    candidate_reports_dir=incomplete_reports,
                    archive=incomplete_output_archive,
                    sha_path=incomplete_output_sha,
                    reports_dir=incomplete_output_reports,
                )
            errors.append("publication accepted an incomplete rollback")
        except RuntimeError as exc:
            if (
                exc.__cause__ is not original_publication_error
                or str(original_publication_error) not in str(exc)
                or str(rollback_cleanup_error) not in str(exc)
            ):
                errors.append(
                    "incomplete rollback did not preserve the original exception as its "
                    f"cause and in its message: {exc}"
                )
            else:
                checks += 1
        finally:
            _remove_owned_output(incomplete_output_reports)

        attempt_parent = publication / "attempts"
        attempt_parent.mkdir()
        attempt_prefix = ".release-candidate-"
        attempt_root = Path(
            tempfile.mkdtemp(prefix=attempt_prefix, dir=str(attempt_parent))
        )
        attempt_nested = attempt_root / "nested"
        attempt_nested.mkdir()
        attempt_file = attempt_nested / "readonly.txt"
        attempt_file.write_text("transaction-owned\n", encoding="utf-8")
        _make_read_only(attempt_file)
        attempt_nested.chmod(stat.S_IRUSR | stat.S_IXUSR)
        _cleanup_attempt_directory(attempt_root, attempt_parent, attempt_prefix)
        if attempt_root.exists() or attempt_root.is_symlink():
            errors.append("read-only transaction attempt candidate survived cleanup")
        else:
            checks += 1

    report = {
        "ok": not errors,
        "checks": checks,
        "skipped": 0,
        "errors": errors,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
