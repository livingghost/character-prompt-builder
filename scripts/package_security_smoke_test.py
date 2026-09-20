#!/usr/bin/env python3
"""Exercise release-packaging rejection of symbolic-link inputs."""
from __future__ import annotations

import json
import os
import tempfile
from types import SimpleNamespace
from pathlib import Path
from typing import Any
from unittest import mock

from package import (
    copy_runtime_tree,
    tree_file_hashes,
    validate_keep_stage_destination,
    write_deterministic_zip,
)
from package_full import (
    build_full_manifest,
    main as package_full_main,
    verify_full_manifest,
)
from package_metadata import load_package_metadata


ROOT = Path(__file__).resolve().parents[1]


def _make_symlink(target: Path, link: Path) -> tuple[bool, str | None]:
    try:
        os.symlink(target, link, target_is_directory=target.is_dir())
        return True, None
    except (OSError, NotImplementedError) as exc:
        return False, str(exc)


def _path_key(path: Path) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def _simulate_symlink(path: Path) -> Any:
    """Make one ordinary fixture path report as a symlink without OS privilege."""

    original = Path.is_symlink
    target = _path_key(path)

    def simulated(candidate: Path) -> bool:
        if _path_key(candidate) == target:
            return True
        return original(candidate)

    return mock.patch.object(Path, "is_symlink", simulated)


def main() -> int:
    checks = 0
    errors: list[str] = []
    real_symlink_integration: dict[str, object] = {
        "available": False,
        "checks": 0,
        "ok": None,
        "unavailable_reason": None,
    }
    with tempfile.TemporaryDirectory(prefix="cpb-package-security-") as temp:
        # Resolve once: rejection errors quote resolved paths, so a
        # non-canonical temporary directory would not match the expectations.
        root = Path(temp).resolve()
        source = root / "source"
        source.mkdir()
        (source / "README.md").write_text("safe\n", encoding="utf-8")
        outside = root / "outside-secret.txt"
        outside.write_text("must not be packaged\n", encoding="utf-8")

        simulated_top_link = source / "simulated-linked-secret.txt"
        simulated_top_link.write_text("simulated link target\n", encoding="utf-8")
        with _simulate_symlink(simulated_top_link):
            try:
                copy_runtime_tree(
                    source,
                    root / "stage-simulated-top",
                    [simulated_top_link.name],
                )
                errors.append("copy_runtime_tree followed a top-level symbolic link")
            except ValueError as exc:
                if "symbolic link" not in str(exc):
                    errors.append(f"top-level symlink rejection raised the wrong error: {exc}")
                else:
                    checks += 1

        nested = source / "assets"
        nested.mkdir()
        simulated_nested_link = nested / "simulated-linked-secret.txt"
        simulated_nested_link.write_text("simulated link target\n", encoding="utf-8")
        with _simulate_symlink(simulated_nested_link):
            try:
                copy_runtime_tree(source, root / "stage-simulated-nested", ["assets"])
                errors.append("copy_runtime_tree followed a nested symbolic link")
            except ValueError as exc:
                if "symbolic link" not in str(exc):
                    errors.append(f"nested symlink rejection raised the wrong error: {exc}")
                else:
                    checks += 1

        clean_stage = root / "clean-stage"
        clean_stage.mkdir()
        (clean_stage / "file.txt").write_text("safe\n", encoding="utf-8")
        simulated_stage_link = clean_stage / "simulated-linked-secret.txt"
        simulated_stage_link.write_text("simulated link target\n", encoding="utf-8")
        with _simulate_symlink(simulated_stage_link):
            try:
                tree_file_hashes(clean_stage)
                errors.append("tree_file_hashes accepted a symbolic link")
            except ValueError as exc:
                if "symbolic link" not in str(exc):
                    errors.append(f"tree hash symlink rejection raised the wrong error: {exc}")
                else:
                    checks += 1
            try:
                write_deterministic_zip(clean_stage, root / "simulated-unsafe.zip")
                errors.append("write_deterministic_zip followed a symbolic link")
            except ValueError as exc:
                if "symbolic link" not in str(exc):
                    errors.append(f"ZIP symlink rejection raised the wrong error: {exc}")
                else:
                    checks += 1

        real_source = root / "real-symlink-source"
        real_nested = real_source / "assets"
        real_nested.mkdir(parents=True)
        real_stage = root / "real-symlink-stage"
        real_stage.mkdir()
        real_top_link = real_source / "linked-secret.txt"
        created, reason = _make_symlink(outside, real_top_link)
        if created:
            real_symlink_integration["available"] = True
            real_symlink_integration["ok"] = True
            real_nested_link = real_nested / "linked-secret.txt"
            real_stage_link = real_stage / "linked-secret.txt"
            for link in (real_nested_link, real_stage_link):
                linked, link_reason = _make_symlink(outside, link)
                if not linked:
                    real_symlink_integration["ok"] = False
                    errors.append(
                        "real symlink integration became unavailable after its "
                        f"positive capability probe: {link_reason}"
                    )
            real_operations = (
                (
                    "top-level copy",
                    lambda: copy_runtime_tree(
                        real_source,
                        root / "stage-real-top",
                        [real_top_link.name],
                    ),
                ),
                (
                    "nested copy",
                    lambda: copy_runtime_tree(
                        real_source,
                        root / "stage-real-nested",
                        ["assets"],
                    ),
                ),
                ("tree hash", lambda: tree_file_hashes(real_stage)),
                (
                    "ZIP write",
                    lambda: write_deterministic_zip(
                        real_stage, root / "real-unsafe.zip"
                    ),
                ),
            )
            if real_symlink_integration["ok"] is True:
                for label, operation in real_operations:
                    try:
                        operation()
                        real_symlink_integration["ok"] = False
                        errors.append(f"real symlink integration {label} was accepted")
                    except ValueError as exc:
                        if "symbolic link" not in str(exc):
                            real_symlink_integration["ok"] = False
                            errors.append(
                                f"real symlink integration {label} raised the wrong error: {exc}"
                            )
                        else:
                            real_symlink_integration["checks"] = int(
                                real_symlink_integration["checks"]
                            ) + 1
        else:
            real_symlink_integration["unavailable_reason"] = reason

        release_input = source / "scripts"
        release_input.mkdir()
        retained_input = release_input / "retained-stage"
        try:
            validate_keep_stage_destination(retained_input, source, ["scripts"])
            errors.append("retained stage was accepted inside a release input")
        except ValueError:
            checks += 1

        occupied = root / "occupied-retained-stage"
        occupied.mkdir()
        sentinel = occupied / "user-data.txt"
        sentinel.write_text("preserve me\n", encoding="utf-8")
        try:
            validate_keep_stage_destination(occupied, source, ["README.md"])
            errors.append("pre-existing retained-stage destination was accepted")
        except FileExistsError:
            checks += 1
        if sentinel.read_text(encoding="utf-8") != "preserve me\n":
            errors.append("pre-existing retained-stage content was modified")
        else:
            checks += 1

        empty_retained_stage = root / "empty-retained-stage"
        empty_retained_stage.mkdir()
        try:
            validate_keep_stage_destination(
                empty_retained_stage, source, ["README.md"]
            )
            errors.append("pre-existing empty retained-stage destination was accepted")
        except FileExistsError:
            checks += 1

        try:
            validate_keep_stage_destination(source, source, ["README.md"])
            errors.append("skill source was accepted as a retained-stage destination")
        except ValueError:
            checks += 1

        new_retained_stage = root / "new-retained-stage"
        resolved = validate_keep_stage_destination(
            new_retained_stage, source, ["README.md"]
        )
        if resolved != new_retained_stage.resolve() or resolved.exists():
            errors.append("new retained-stage destination was not resolved safely")
        else:
            checks += 1

        metadata = load_package_metadata(ROOT)
        full_archive_name = f"{metadata.name}-{metadata.version}-full.zip"
        source_sentinel = ROOT / "README.md"
        source_sentinel_hash = source_sentinel.read_bytes()
        try:
            package_full_main(
                [
                    "--source",
                    str(ROOT),
                    "--out",
                    str(root / full_archive_name),
                    "--reports-dir",
                    str(ROOT),
                ]
            )
            errors.append("full release reports accepted the source tree as output")
        except ValueError:
            if source_sentinel.read_bytes() == source_sentinel_hash:
                checks += 1
            else:
                errors.append("full release output validation modified the source tree")

        occupied_full_archive = root / full_archive_name
        occupied_full_archive.write_text("preserve me\n", encoding="utf-8")
        try:
            package_full_main(
                [
                    "--source",
                    str(ROOT),
                    "--out",
                    str(occupied_full_archive),
                    "--reports-dir",
                    str(root / "full-reports"),
                ]
            )
            errors.append("full release accepted an occupied archive destination")
        except FileExistsError:
            if occupied_full_archive.read_text(encoding="utf-8") == "preserve me\n":
                checks += 1
            else:
                errors.append("full release modified an occupied archive destination")

        manifest_root = root / "full-manifest-fixture"
        manifest_root.mkdir()
        (manifest_root / "payload.txt").write_text("payload\n", encoding="utf-8")
        manifest = build_full_manifest(manifest_root, "2026.08.23.1", [])
        manifest_path = manifest_root / "FULL-MANIFEST.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        metadata_probe = SimpleNamespace(
            name=manifest_root.name,
            version="2026.08.23.1",
        )
        with (
            mock.patch("package_full.load_package_metadata", return_value=metadata_probe),
            mock.patch(
                "package_full.validate_all_packs",
                return_value={"packs": []},
            ),
        ):
            if verify_full_manifest(manifest_root).get("ok") is True:
                checks += 1
            else:
                errors.append("valid full manifest failed verification")

            invalid_version = dict(manifest)
            invalid_version["version"] = "2026.08.22.1"
            manifest_path.write_text(
                json.dumps(invalid_version, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            if verify_full_manifest(manifest_root).get("ok") is False:
                checks += 1
            else:
                errors.append("full manifest verification accepted a stale version")

            duplicate_inventory = dict(manifest)
            duplicate_inventory["files"] = [
                *manifest["files"],
                manifest["files"][0],
            ]
            manifest_path.write_text(
                json.dumps(duplicate_inventory, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            if verify_full_manifest(manifest_root).get("ok") is False:
                checks += 1
            else:
                errors.append("full manifest verification accepted a duplicate path")

            invalid_count = dict(manifest)
            invalid_count["file_count_excluding_manifest"] = 999
            manifest_path.write_text(
                json.dumps(invalid_count, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            if verify_full_manifest(manifest_root).get("ok") is False:
                checks += 1
            else:
                errors.append("full manifest verification accepted a stale file count")

    report = {
        "ok": not errors,
        "checks": checks,
        "skipped": 0,
        "real_symlink_integration": real_symlink_integration,
        "errors": errors,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
