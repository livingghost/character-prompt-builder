#!/usr/bin/env python3
"""Focused regression tests for preset duplicate and removal maintenance."""
from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pack_manager import PackRecord, atomic_write_json, validate_pack, write_lock
from preset_maintenance import (
    MaintenanceError,
    _image_fingerprint,
    _parse_evidence_groups,
    _prepare_evidence_consolidation,
    _prepare_evidence_changes,
    _semantic_candidates,
    apply_removal,
    build_evidence_removal_plan,
    build_removal_plan,
    build_restore_plan,
    main,
)


SCRIPTS = Path(__file__).resolve().parent


PACK_ID = "0198b4e8-7c00-7a31-8c5a-2a6d9f18e4b7"


def _term(phrase: str) -> dict[str, object]:
    return {"phrase": phrase, "facet": "lighting", "weight": 1.0, "source": "label"}


def _module(record_id: str, label: str) -> dict[str, object]:
    return {
        "id": record_id,
        "label": label,
        "curation_status": "vocabulary",
        "category": "lighting",
        "prompt": f"a restrained {label} separating the subject from the darker background",
        "domains": ["shared"],
        "tags": [label, "subject separation"],
        "search_terms": [_term(label)],
    }


def _write_minimal_pack(root: Path, *, blocking: bool = False) -> None:
    atomic_write_json(root / "pack.json", {
        "pack_id": PACK_ID,
        "name": "Preset Maintenance Fixture",
        "description": "A fixture with two vocabulary records.",
        "release": "2026.08.23.1",
        "content": {
            "record_globs": ["records/**/*.json"],
            "resource_globs": [],
            "resource_bindings": {},
        },
        "capabilities": ["lighting"],
        "dependencies": [],
        "optional_dependencies": [],
        "replaces": [],
        "license": "GPL-3.0-only",
    })
    target = _module("fixture-light-target", "soft target rim")
    survivor = _module("fixture-light-survivor", "soft survivor rim")
    survivor["distinct_from"] = ["fixture-light-target"]
    if blocking:
        survivor["search_profile"] = {"variant_of": "fixture-light-target"}
    atomic_write_json(root / "records" / "lighting.json", {
        "kind": "module",
        "category": "lighting",
        "records": [target, survivor],
    })
    write_lock(root)


def _write_evidence_fixture(root: Path) -> SimpleNamespace:
    # The maintenance code resolves every path it stages or deletes. A TEMP that
    # reaches the process through a link or an 8.3 short name - the GitHub
    # Windows runner exposes both - would otherwise leave the fixture holding the
    # unresolved spelling and every path comparison below would miss.
    root = root.resolve()
    sha = "a" * 64
    prefix = sha[:16]
    corpus = root / "resources" / "reference-corpus"
    bundle_dir = corpus / "visual-evidence" / prefix
    semantic_path = bundle_dir / "derived-visual" / "semantic-regions.json"
    authority_path = bundle_dir / "visual-authority.json"
    bundle_path = bundle_dir / "visual-evidence-bundle.json"
    atomic_write_json(semantic_path, {
        "canonical_record_refs": ["fixture-target"],
        "semantic_region_map_sha256": "b" * 64,
    })
    atomic_write_json(authority_path, {
        "authority_id": f"VA-{prefix}",
        "canonical_record_refs": ["fixture-target"],
        "visual_authority_sha256": "c" * 64,
    })
    atomic_write_json(bundle_path, {
        "bundle_id": f"VE-{prefix}",
        "canonical_record_refs": ["fixture-target"],
        "disposition": "canonical-preset-evidence",
        "visual_authority_ref": {"sha256": "c" * 64},
        "artifacts": [{
            "artifact_id": "semantic-regions",
            "role": "semantic-region-map",
            "path": "derived-visual/semantic-regions.json",
            "sha256": "d" * 64,
        }],
        "visual_evidence_bundle_sha256": "e" * 64,
    })
    manifest_path = corpus / "manifest.json"
    atomic_write_json(manifest_path, {
        "source_file_count": 1,
        "unique_source_count": 1,
        "evidence_bundle_count": 1,
        "canonical_evidence_count": 1,
        "excluded_noncanonical_count": 0,
        "entries": [{
            "source_sha256": sha,
            "disposition": "canonical-preset-evidence",
            "evidence_relation": "existing-family-variant",
            "canonical_record_ids": ["fixture-target"],
            "visual_authority_ref": {
                "id": f"VA-{prefix}",
                "path": f"visual-evidence/{prefix}/visual-authority.json",
                "sha256": "c" * 64,
            },
            "visual_evidence_bundle_ref": {
                "id": f"VE-{prefix}",
                "path": f"visual-evidence/{prefix}/visual-evidence-bundle.json",
                "sha256": "e" * 64,
            },
        }],
        "reference_corpus_manifest_sha256": "f" * 64,
    })
    thumbnail_path = corpus / "catalog-thumbnails.json"
    atomic_write_json(thumbnail_path, {
        "assets": {f"visual-evidence-{prefix}": {"path": "thumbnail.webp"}},
    })
    # The mapping points at a real raster: an unreferenced one left behind in the
    # corpus is what validate_reference_corpus.py refuses.
    thumbnail_file = root / "thumbnail.webp"
    thumbnail_file.write_bytes(b"RIFF0000WEBPVP8 fixture")
    asset_path = root / "records" / "visual-evidence.json"
    asset = {
        "id": f"visual-evidence-{prefix}",
        "asset_type": "visual-evidence-bundle",
        "source_sha256": sha,
        "canonical_record_ids": ["fixture-target"],
        "artifacts": [{
            "role": "semantic-region-map",
            "sha256": "d" * 64,
        }],
    }
    atomic_write_json(asset_path, {"kind": "asset", "records": [asset]})
    return SimpleNamespace(
        root=root,
        pack_id=PACK_ID,
        release="2026.08.23.1",
        resource_bindings={
            "reference-corpus-manifest": "resources/reference-corpus/manifest.json",
            "catalog-thumbnails": "resources/reference-corpus/catalog-thumbnails.json",
        },
        records=[PackRecord("asset", None, asset, "records/visual-evidence.json")],
        sha=sha,
        bundle_dir=bundle_dir,
        manifest_path=manifest_path,
        asset_path=asset_path,
        thumbnail_path=thumbnail_path,
        thumbnail_file=thumbnail_file,
    )


def _extend_evidence_fixture_with_duplicate(fixture: SimpleNamespace) -> tuple[str, str]:
    duplicate_sha = "b" * 64
    duplicate_prefix = duplicate_sha[:16]
    duplicate_id = f"visual-evidence-{duplicate_prefix}"
    duplicate_dir = fixture.bundle_dir.parent / duplicate_prefix
    duplicate_dir.mkdir(parents=True)

    manifest = json.loads(fixture.manifest_path.read_text(encoding="utf-8"))
    duplicate_entry = json.loads(json.dumps(manifest["entries"][0]))
    duplicate_entry["source_sha256"] = duplicate_sha
    duplicate_entry["visual_authority_ref"]["id"] = f"VA-{duplicate_prefix}"
    duplicate_entry["visual_authority_ref"]["path"] = f"visual-evidence/{duplicate_prefix}/visual-authority.json"
    duplicate_entry["visual_evidence_bundle_ref"]["id"] = f"VE-{duplicate_prefix}"
    duplicate_entry["visual_evidence_bundle_ref"]["path"] = f"visual-evidence/{duplicate_prefix}/visual-evidence-bundle.json"
    manifest["entries"].append(duplicate_entry)
    manifest["source_file_count"] = 2
    manifest["unique_source_count"] = 2
    manifest["evidence_bundle_count"] = 2
    manifest["canonical_evidence_count"] = 2
    atomic_write_json(fixture.manifest_path, manifest)

    thumbnails = json.loads(fixture.thumbnail_path.read_text(encoding="utf-8"))
    thumbnails["assets"][duplicate_id] = {"path": "duplicate-thumbnail.webp"}
    atomic_write_json(fixture.thumbnail_path, thumbnails)

    document = json.loads(fixture.asset_path.read_text(encoding="utf-8"))
    duplicate_asset = json.loads(json.dumps(document["records"][0]))
    duplicate_asset["id"] = duplicate_id
    duplicate_asset["source_sha256"] = duplicate_sha
    document["records"].append(duplicate_asset)
    atomic_write_json(fixture.asset_path, document)
    fixture.records.append(PackRecord("asset", None, duplicate_asset, "records/visual-evidence.json"))
    return document["records"][0]["id"], duplicate_id


_KILLED_REMOVAL = textwrap.dedent(
    """\
    import os
    import sys
    from pathlib import Path

    sys.dont_write_bytecode = True
    sys.path.insert(0, {scripts!r})
    import preset_maintenance

    # os._exit is the SIGKILL an out-of-memory kill delivers: no except clause,
    # no finally clause and no atexit handler is ever evaluated.
    preset_maintenance.write_lock = lambda *args, **kwargs: os._exit(137)
    plan = preset_maintenance.build_removal_plan(
        Path({root!r}), "fixture-light-target", evidence_mode="keep"
    )
    preset_maintenance.apply_removal(
        plan,
        new_release="2026.08.23.2",
        confirm="fixture-light-target",
        quarantine_root=Path({quarantine!r}),
    )
    """
)


def _kill_removal_midway(root: Path, quarantine: Path) -> None:
    script = _KILLED_REMOVAL.format(
        scripts=str(SCRIPTS),
        root=str(root),
        quarantine=str(quarantine),
    )
    completed = subprocess.run(
        [sys.executable, "-B", "-c", script],
        capture_output=True,
        text=True,
    )
    if completed.returncode != 137:
        raise AssertionError(
            f"child exited {completed.returncode}: {completed.stdout}{completed.stderr}"
        )


def _record_ids(root: Path) -> list[str]:
    document = json.loads((root / "records" / "lighting.json").read_text(encoding="utf-8"))
    return [row["id"] for row in document["records"]]


def _release(root: Path) -> str:
    return json.loads((root / "pack.json").read_text(encoding="utf-8"))["release"]


class PresetMaintenanceTest(unittest.TestCase):
    def test_evidence_removal_plan_has_no_keeper_and_requires_exact_confirmation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cpb-preset-evidence-remove-plan-") as temporary:
            fixture = _write_evidence_fixture(Path(temporary))
            asset_id = f"visual-evidence-{fixture.sha[:16]}"
            with patch("preset_maintenance._validated_pack", return_value=fixture):
                plan = build_evidence_removal_plan(fixture.root, [asset_id])
            self.assertTrue(plan["can_apply"])
            self.assertEqual("remove-evidence-plan", plan["operation"])
            self.assertEqual(1, plan["delete_count"])
            self.assertIsNone(plan["groups"][0]["keeper"])
            self.assertEqual("delete", plan["groups"][0]["members"][0]["role"])
            self.assertEqual("DELETE-1-VISUAL-EVIDENCE", plan["safety"]["confirmation_required"])

    def test_explicit_evidence_groups_preserve_first_member(self) -> None:
        groups = _parse_evidence_groups([
            "visual-evidence-aaaaaaaaaaaaaaaa,visual-evidence-bbbbbbbbbbbbbbbb"
        ])
        self.assertEqual("visual-evidence-aaaaaaaaaaaaaaaa", groups[0][0])
        with self.assertRaisesRegex(Exception, "more than one group"):
            _parse_evidence_groups([
                "visual-evidence-aaaaaaaaaaaaaaaa,visual-evidence-bbbbbbbbbbbbbbbb",
                "visual-evidence-cccccccccccccccc,visual-evidence-bbbbbbbbbbbbbbbb",
            ])

    def test_semantic_overlap_crosses_categories_without_deleting(self) -> None:
        common = {
            "curation_status": "curated",
            "image_promise": "A gray wolf holds an orange cocktail at a warmly lit bar counter.",
            "tags": ["gray wolf", "orange cocktail", "bar portrait"],
        }
        records = [
            PackRecord("scene", "bar-wide", {"id": "wide", "label": "wide bar portrait", **common}, "a.json"),
            PackRecord("scene", "bar-close", {"id": "close", "label": "close bar portrait", **common}, "b.json"),
        ]
        candidates, groups, truncated = _semantic_candidates(
            records,
            threshold=0.60,
            include_vocabulary=False,
            max_pairs=10,
        )
        self.assertEqual([], groups)
        self.assertFalse(truncated)
        self.assertEqual("semantic-overlap", candidates[0]["classification"])
        self.assertEqual("human-review-for-grouping-or-lossless-merge", candidates[0]["recommended_action"])

    def test_pixel_hash_ignores_container_encoding(self) -> None:
        try:
            from PIL import Image
            import numpy  # noqa: F401
        except ImportError:
            self.skipTest("visual dependency profile is unavailable")
        with tempfile.TemporaryDirectory(prefix="cpb-preset-fingerprint-") as temporary:
            root = Path(temporary)
            image = Image.new("RGB", (48, 32), (40, 100, 180))
            png = root / "same.png"
            bmp = root / "same.bmp"
            image.save(png)
            image.save(bmp)
            left = _image_fingerprint(png, identifier="png", scope="source-file")
            right = _image_fingerprint(bmp, identifier="bmp", scope="source-file")
            self.assertNotEqual(left["raw_sha256"], right["raw_sha256"])
            self.assertEqual(left["normalized_pixel_sha256"], right["normalized_pixel_sha256"])
            self.assertEqual(left["phash64"], right["phash64"])

    def test_removal_plan_blocks_hard_reference(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cpb-preset-remove-block-") as temporary:
            root = Path(temporary) / "pack"
            _write_minimal_pack(root, blocking=True)
            plan = build_removal_plan(root, "fixture-light-target", evidence_mode="keep")
            self.assertFalse(plan["can_apply"])
            self.assertTrue(any(row["field"] == "variant_of" for row in plan["blocking_references"]))

    def test_apply_removal_is_confirmed_recoverable_and_locked(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cpb-preset-remove-apply-") as temporary:
            root = Path(temporary) / "pack"
            _write_minimal_pack(root)
            plan = build_removal_plan(root, "fixture-light-target", evidence_mode="keep")
            self.assertTrue(plan["can_apply"])
            result = apply_removal(
                plan,
                new_release="2026.08.23.2",
                confirm="fixture-light-target",
                quarantine_root=Path(temporary) / "quarantine",
            )
            self.assertTrue(result["recoverable"])
            document = json.loads((root / "records" / "lighting.json").read_text(encoding="utf-8"))
            self.assertEqual(["fixture-light-survivor"], [row["id"] for row in document["records"]])
            self.assertNotIn("distinct_from", document["records"][0])
            validation = validate_pack(root, require_lock=True, verify_lock=True)
            self.assertTrue(validation.valid, validation.to_dict())

    def test_removal_plan_blocks_external_evaluation_reference(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cpb-preset-external-block-") as temporary:
            product = Path(temporary)
            (product / "package-manifest.toml").write_text(
                "[package]\nname = \"fixture\"\n", encoding="utf-8", newline="\n"
            )
            root = product / "packs" / "fixture"
            _write_minimal_pack(root)
            atomic_write_json(product / "config" / "default-release.json", {
                "cases": [{
                    "id": "x",
                    "operation": "search",
                    "expected_ids": ["fixture-light-target"],
                }],
            })
            plan = build_removal_plan(root, "fixture-light-target", evidence_mode="keep")
            self.assertTrue(plan["external_scan"]["executed"])
            self.assertFalse(plan["can_apply"])
            external = [
                row for row in plan["blocking_references"]
                if row.get("type") == "external-evaluation-reference"
            ]
            self.assertEqual(1, len(external), plan["blocking_references"])
            self.assertEqual("config/default-release.json", external[0]["path"])

    def test_changelog_prose_does_not_block_removal(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cpb-preset-external-prose-") as temporary:
            product = Path(temporary)
            (product / "package-manifest.toml").write_text(
                "[package]\nname = \"fixture\"\n", encoding="utf-8", newline="\n"
            )
            root = product / "packs" / "fixture"
            _write_minimal_pack(root)
            atomic_write_json(product / "config" / "default-release.json", {"cases": []})
            (product / "CHANGELOG.md").write_text(
                "# Changelog\n\n## 2026.08.23.1\n\n- retired fixture-light-target upstream\n",
                encoding="utf-8",
                newline="\n",
            )
            plan = build_removal_plan(root, "fixture-light-target", evidence_mode="keep")
            self.assertTrue(plan["can_apply"], plan["blocking_references"])
            self.assertEqual(
                [{"path": "CHANGELOG.md", "line": 5, "type": "external-text-occurrence"}],
                plan["external_references"],
            )

    def test_removal_plan_reports_an_unavailable_product_root(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cpb-preset-external-none-") as temporary:
            root = Path(temporary) / "pack"
            _write_minimal_pack(root)
            plan = build_removal_plan(root, "fixture-light-target", evidence_mode="keep")
            self.assertEqual(
                {"executed": False, "reason": "product root is unavailable"},
                plan["external_scan"],
            )
            self.assertEqual([], plan["external_references"])
            self.assertTrue(plan["can_apply"], plan["blocking_references"])

    def test_keyboard_interrupt_rolls_back_removal(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cpb-preset-remove-interrupt-") as temporary:
            root = Path(temporary) / "pack"
            _write_minimal_pack(root)
            plan = build_removal_plan(root, "fixture-light-target", evidence_mode="keep")
            with patch("preset_maintenance.write_lock", side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    apply_removal(
                        plan,
                        new_release="2026.08.23.2",
                        confirm="fixture-light-target",
                        quarantine_root=Path(temporary) / "quarantine",
                    )
            self.assertTrue((root / "pack.lock.json").is_file())
            self.assertEqual("2026.08.23.1", _release(root))
            self.assertEqual(
                ["fixture-light-target", "fixture-light-survivor"],
                _record_ids(root),
            )
            validation = validate_pack(root, require_lock=True, verify_lock=True)
            self.assertTrue(validation.valid, validation.to_dict())

    def test_restore_recovers_a_killed_transaction(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cpb-preset-restore-") as temporary:
            root = Path(temporary) / "pack"
            quarantine = Path(temporary) / "quarantine"
            _write_minimal_pack(root)
            _kill_removal_midway(root, quarantine)
            self.assertEqual("2026.08.23.2", _release(root))
            self.assertEqual(["fixture-light-survivor"], _record_ids(root))

            orphan = root / "records" / (".lighting.json.tmp-1-" + "a" * 32)
            orphan.write_text("{}\n", encoding="utf-8", newline="\n")

            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(SCRIPTS / "preset_maintenance.py"),
                    "restore",
                    str(root),
                    "--quarantine-root",
                    str(quarantine),
                    "--apply",
                    "--confirm",
                    PACK_ID,
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
            self.assertFalse(orphan.exists())
            self.assertEqual("2026.08.23.1", _release(root))
            self.assertEqual(
                ["fixture-light-target", "fixture-light-survivor"],
                _record_ids(root),
            )
            validation = validate_pack(root, require_lock=True, verify_lock=True)
            self.assertTrue(validation.valid, validation.to_dict())

    def test_restore_refuses_a_completed_transaction(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cpb-preset-restore-refuse-") as temporary:
            root = Path(temporary) / "pack"
            quarantine = Path(temporary) / "quarantine"
            _write_minimal_pack(root)
            plan = build_removal_plan(root, "fixture-light-target", evidence_mode="keep")
            apply_removal(
                plan,
                new_release="2026.08.23.2",
                confirm="fixture-light-target",
                quarantine_root=quarantine,
            )
            release_before = _release(root)
            records_before = _record_ids(root)

            with self.assertRaisesRegex(MaintenanceError, "completed"):
                build_restore_plan(root, quarantine_root=quarantine)
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                status = main([
                    "restore",
                    str(root),
                    "--quarantine-root",
                    str(quarantine),
                    "--apply",
                    "--confirm",
                    PACK_ID,
                ])
            self.assertEqual(1, status)
            self.assertIn("completed", stream.getvalue())
            self.assertEqual(release_before, _release(root))
            self.assertEqual(records_before, _record_ids(root))

    def test_evidence_keep_converts_last_link_to_noncanonical(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cpb-preset-evidence-keep-") as temporary:
            fixture = _write_evidence_fixture(Path(temporary))
            staged: dict[Path, object | None] = {}
            quarantined = _prepare_evidence_changes(
                fixture, "fixture-target", "keep", {}, staged
            )
            self.assertEqual([fixture.thumbnail_file], quarantined)
            manifest = staged[fixture.manifest_path]
            self.assertEqual("excluded-noncanonical-artifact", manifest["entries"][0]["disposition"])
            self.assertEqual([], manifest["entries"][0]["canonical_record_ids"])
            self.assertIsNone(staged[fixture.asset_path])
            self.assertEqual({}, staged[fixture.thumbnail_path]["assets"])

    def test_evidence_keep_quarantines_the_orphaned_thumbnail(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cpb-preset-evidence-orphan-") as temporary:
            fixture = _write_evidence_fixture(Path(temporary))
            staged: dict[Path, object | None] = {}
            quarantined = _prepare_evidence_changes(
                fixture, "fixture-target", "keep", {}, staged
            )
            self.assertIn(fixture.thumbnail_file, quarantined)
            self.assertTrue(fixture.thumbnail_file.is_file())

    def test_evidence_keep_preserves_a_shared_thumbnail(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cpb-preset-evidence-shared-") as temporary:
            fixture = _write_evidence_fixture(Path(temporary))
            manifest = json.loads(fixture.manifest_path.read_text(encoding="utf-8"))
            manifest["entries"][0]["canonical_record_ids"] = ["fixture-target", "fixture-other"]
            atomic_write_json(fixture.manifest_path, manifest)
            document = json.loads(fixture.asset_path.read_text(encoding="utf-8"))
            document["records"][0]["canonical_record_ids"] = ["fixture-target", "fixture-other"]
            atomic_write_json(fixture.asset_path, document)
            fixture.records[0].record["canonical_record_ids"] = ["fixture-target", "fixture-other"]

            staged: dict[Path, object | None] = {}
            quarantined = _prepare_evidence_changes(
                fixture, "fixture-target", "keep", {}, staged
            )
            self.assertEqual([], quarantined)
            self.assertNotIn(fixture.thumbnail_path, staged)
            self.assertTrue(fixture.thumbnail_file.is_file())

    def test_evidence_purge_removes_manifest_thumbnail_and_directory(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cpb-preset-evidence-purge-") as temporary:
            fixture = _write_evidence_fixture(Path(temporary))
            staged: dict[Path, object | None] = {}
            evidence_dirs = _prepare_evidence_changes(
                fixture, "fixture-target", "purge", {}, staged
            )
            self.assertEqual([fixture.bundle_dir], evidence_dirs)
            self.assertEqual([], staged[fixture.manifest_path]["entries"])
            self.assertEqual(0, staged[fixture.manifest_path]["source_file_count"])
            self.assertEqual({}, staged[fixture.thumbnail_path]["assets"])
            self.assertIsNone(staged[fixture.asset_path])

    def test_evidence_consolidation_deletes_only_later_members(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cpb-preset-evidence-consolidate-") as temporary:
            fixture = _write_evidence_fixture(Path(temporary))
            keeper_id, duplicate_id = _extend_evidence_fixture_with_duplicate(fixture)
            plan = {
                "groups": [{
                    "keeper": keeper_id,
                    "members": [
                        {"asset_id": keeper_id, "role": "keep", "source_sha256": fixture.sha},
                        {"asset_id": duplicate_id, "role": "delete", "source_sha256": "b" * 64},
                    ],
                }],
                "delete_count": 1,
                "source_occurrences": {},
            }
            staged: dict[Path, object | None] = {}
            evidence_dirs = _prepare_evidence_consolidation(fixture, plan, staged)
            self.assertEqual([fixture.bundle_dir.parent / ("b" * 16)], evidence_dirs)
            self.assertEqual(1, staged[fixture.manifest_path]["source_file_count"])
            self.assertEqual([fixture.sha], [row["source_sha256"] for row in staged[fixture.manifest_path]["entries"]])
            self.assertEqual([keeper_id], list(staged[fixture.thumbnail_path]["assets"]))
            self.assertEqual([keeper_id], [row["id"] for row in staged[fixture.asset_path]["records"]])


if __name__ == "__main__":
    unittest.main(verbosity=2)
