#!/usr/bin/env python3
"""Focused runtime tests for catalog request, inspection, and batch contracts."""
from __future__ import annotations

import os
import tempfile
import unittest
import contextlib
import hashlib
import io
import json
import itertools
import subprocess
import sys
from collections import OrderedDict
from typing import Any, get_type_hints
from pathlib import Path
from unittest import mock

import catalog_cli
import catalog_retrieval.batch
import catalog_retrieval.retrieval
import catalog_retrieval.runtime
import catalog_retrieval.scoring
from catalog_retrieval.queries import validate_query_request
from pack_cache import RuntimePackCatalog, RuntimePackEntry
from search_discovery import CatalogQueryInput, SearchIndex, analyze_query


PACK_ID = "01a0043b-2250-720d-87b7-f1e6fd7ed230"

# Help text is read for what an option is called, not for how it is painted.
# argparse colours its output when the environment asks for colour, and an agent
# or CI harness that sets FORCE_COLOR turns every assertion about help text into
# an assertion about escape sequences.
UNPAINTED = {"PYTHON_COLORS": "0", "NO_COLOR": "1"}


def _runtime_entry(
    root: Path,
    kind: str,
    record: dict[str, object],
    category: str | None,
) -> RuntimePackEntry:
    return RuntimePackEntry(
        kind=kind,
        category=category,
        record=record,
        source_pack=PACK_ID,
        source_root=root,
        source_file=f"records/{record['id']}.json",
    )


def _asset(root: Path, asset_id: str, canonical_id: str, filename: str) -> RuntimePackEntry:
    relative = f"resources/{filename}"
    (root / "resources").mkdir(parents=True, exist_ok=True)
    resource = root / relative
    resource.write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")
    return _runtime_entry(
        root,
        "asset",
        {
            "id": asset_id,
            "label": f"Asset {asset_id}",
            "category": "visual-evidence",
            "asset_type": "visual-evidence-bundle",
            "description": "Complete fixture asset description.",
            "canonical_record_ids": [canonical_id],
            "primary_resource": relative,
            "resource_refs": [relative],
            "artifacts": [{
                "artifact_id": "primary-vector",
                "role": "identity-reference",
                "path": relative,
                "media_type": "image/svg+xml",
                "sha256": hashlib.sha256(resource.read_bytes()).hexdigest(),
            }],
        },
        "visual-evidence",
    )


class CatalogAnnotationTest(unittest.TestCase):
    """Resolve concrete cache types without loading packs or warming imports."""

    def test_runtime_cache_annotations_resolve_to_scoring_types(self) -> None:
        runtime = catalog_retrieval.runtime
        scoring = catalog_retrieval.scoring
        with mock.patch.object(runtime, "load_runtime_catalog", side_effect=AssertionError("unexpected pack I/O")):
            hints = get_type_hints(runtime)
        self.assertEqual(hints["_CORPUS_CACHE"], OrderedDict[tuple[Any, ...], scoring.Corpus])
        self.assertEqual(hints["_INDEXED_ENTRY_CACHE"], OrderedDict[tuple[str, str], scoring.IndexedEntry])

    def test_scoring_annotations_resolve_to_runtime_entry(self) -> None:
        runtime = catalog_retrieval.runtime
        scoring = catalog_retrieval.scoring
        self.assertIs(get_type_hints(scoring.IndexedEntry)["entry"], runtime.Entry)
        self.assertIs(get_type_hints(scoring._build_indexed_entry)["entry"], runtime.Entry)
        self.assertIs(get_type_hints(scoring._build_indexed_entry)["return"], scoring.IndexedEntry)
        self.assertIs(get_type_hints(scoring.Corpus.indexed_at)["return"], scoring.IndexedEntry)
        # Resolve all locally defined annotated functions and class methods too.
        # No custom globalns/localns: ordinary reflection must work on its own.
        for module in (runtime, scoring):
            for value in vars(module).values():
                if getattr(value, "__module__", None) != module.__name__:
                    continue
                if callable(value) and hasattr(value, "__annotations__"):
                    get_type_hints(value)
                if isinstance(value, type):
                    for member in vars(value).values():
                        if isinstance(member, (staticmethod, classmethod)):
                            member = member.__func__
                        if callable(member) and hasattr(member, "__annotations__"):
                            get_type_hints(member)

    def test_fresh_import_orders_resolve_annotations_without_pack_io(self) -> None:
        script_dir = Path(__file__).resolve().parent
        modules = ("catalog_retrieval.runtime", "catalog_retrieval.scoring", "catalog_cli")
        probe = r"""
import importlib
import sys
from typing import Any, get_type_hints
from collections import OrderedDict
from unittest import mock
sys.path.insert(0, sys.argv[1])
import pack_cache
with mock.patch.object(pack_cache, "load_runtime_catalog", side_effect=AssertionError("unexpected pack I/O")):
    for name in sys.argv[2:]:
        importlib.import_module(name)
    runtime = importlib.import_module("catalog_retrieval.runtime")
    scoring = importlib.import_module("catalog_retrieval.scoring")
    facade = importlib.import_module("catalog_cli")
    hints = get_type_hints(runtime)
    assert hints["_CORPUS_CACHE"] == OrderedDict[tuple[Any, ...], scoring.Corpus]
    assert hints["_INDEXED_ENTRY_CACHE"] == OrderedDict[tuple[str, str], scoring.IndexedEntry]
    assert get_type_hints(scoring.IndexedEntry)["entry"] is runtime.Entry
    assert facade.Corpus is scoring.Corpus
    assert facade.Entry is runtime.Entry
    assert runtime._PACK_CATALOG_CACHE is None
    assert not runtime._CORPUS_CACHE and not runtime._INDEXED_ENTRY_CACHE
"""
        for order in itertools.permutations(modules):
            with self.subTest(import_order=order):
                result = subprocess.run(
                    [sys.executable, "-B", "-c", probe, str(script_dir), *order],
                    cwd=script_dir.parent,
                    env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                    capture_output=True, text=True, encoding="utf-8", timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_scoring_reuses_and_clears_runtime_owned_cache(self) -> None:
        runtime = catalog_retrieval.runtime
        scoring = catalog_retrieval.scoring
        runtime.clear_runtime_caches()
        try:
            entry = runtime.Entry(
                kind="module", category="composition",
                record={"id": "annotation-fixture", "label": "Layered arrangement", "tags": ["layout"]},
                source_pack="fixture", source_root=Path("."), source_file="fixture.json",
            )
            index = SearchIndex({"records": {}, "phrases": {}})
            corpus = scoring.Corpus([entry], search_index=index)
            indexed = corpus.indexed_at(0)
            self.assertIs(indexed.entry, entry)
            self.assertIs(corpus.indexed_at(0), indexed)
            self.assertIs(runtime._INDEXED_ENTRY_CACHE[(index.fingerprint, entry.fingerprint)], indexed)
            runtime._CORPUS_CACHE[("annotation-fixture",)] = corpus
            get_type_hints(runtime)
            self.assertIs(runtime._CORPUS_CACHE[("annotation-fixture",)], corpus)
            runtime.clear_runtime_caches()
            self.assertFalse(runtime._CORPUS_CACHE)
            self.assertFalse(runtime._INDEXED_ENTRY_CACHE)
        finally:
            runtime.clear_runtime_caches()


class CatalogRuntimeTest(unittest.TestCase):
    def tearDown(self) -> None:
        catalog_cli.clear_runtime_caches()

    def _install_fixture_catalog(self, root: Path) -> tuple[list[catalog_cli.Entry], list[str]]:
        canonical_ids = ["fixture-zero", "fixture-one", "fixture-many"]
        canonical = [
            _runtime_entry(
                root,
                "module",
                {
                    "id": record_id,
                    "label": record_id.replace("-", " "),
                    "category": "species",
                    "curation_status": "curated",
                    "tags": ["fixture identity"],
                    "prompt": "Fixture identity wording.",
                },
                "species",
            )
            for record_id in canonical_ids
        ]
        asset_a = _asset(root, "asset-a", canonical_ids[1], "a.svg")
        asset_b = _asset(root, "asset-b", canonical_ids[2], "b.svg")
        asset_c = _asset(root, "asset-c", canonical_ids[2], "c.svg")
        all_entries = tuple([*canonical, asset_a, asset_b, asset_c])
        catalog = RuntimePackCatalog(
            fingerprint="fixture-catalog",
            active_pack_count=1,
            entries=all_entries,
            phrases={},
            profiles={},
            resources={},
            assets_by_canonical_record={
                canonical_ids[1]: (asset_a,),
                canonical_ids[2]: (asset_b, asset_c),
            },
            diagnostics=(),
        )
        catalog_cli.clear_runtime_caches()
        catalog_retrieval.runtime._PACK_CATALOG_CACHE = catalog
        return catalog_cli.load_entries(), canonical_ids

    def test_inspect_and_search_expose_compact_asset_activation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            entries, canonical_ids = self._install_fixture_catalog(Path(temporary))
            expected = [0, 1, 2]
            for record_id, count in zip(canonical_ids, expected, strict=True):
                inspected = catalog_cli.inspect_record(entries, record_id)
                activation = inspected["linked_asset_activation"]
                self.assertEqual(activation["asset_count"], count)
                self.assertEqual(len(activation["asset_ids"]), count)
                self.assertNotIn("linked_assets", inspected)
                self.assertNotIn("resources", inspected)
                self.assertNotIn("resolved_asset_resources", inspected)
                self.assertEqual(
                    inspected["record"]["prompt"],
                    "Fixture identity wording.",
                )
                self.assertEqual(catalog_cli.asset_lookup(record_id)["asset_count"], count)
                hits = catalog_cli.search_entries(
                    entries,
                    record_id.replace("-", " "),
                    kinds={"module"},
                    categories={"species"},
                    domain=None,
                    limit=1,
                    diverse=False,
                )
                self.assertEqual(len(hits), 1)
                self.assertEqual(
                    hits[0]["linked_asset_activation"]["asset_count"],
                    count,
                )
                self.assertNotIn("linked_assets", hits[0])
            self.assertEqual(
                catalog_cli.asset_lookup(canonical_ids[0]),
                {
                    "lookup_id": canonical_ids[0],
                    "lookup_mode": "canonical-record-id",
                    "asset_count": 0,
                    "assets": [],
                },
            )
            with self.assertRaisesRegex(SystemExit, "Unknown asset or canonical"):
                catalog_cli.asset_lookup("not-in-active-catalog")

    def test_asset_lookup_is_discovery_output_not_a_generation_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self._install_fixture_catalog(Path(temporary))
            discovered = catalog_cli.asset_lookup("asset-b")
            self.assertEqual(
                set(discovered),
                {"lookup_id", "lookup_mode", "asset_count", "assets"},
            )
            self.assertEqual(discovered["lookup_mode"], "asset-id")
            self.assertEqual(discovered["asset_count"], 1)
            asset = discovered["assets"][0]
            self.assertEqual(
                set(asset),
                {
                    "kind",
                    "asset_id",
                    "source_pack",
                    "source_file",
                    "record",
                    "resources",
                },
            )
            self.assertEqual(asset["asset_id"], "asset-b")
            self.assertEqual(asset["resources"][0]["role"], "identity-reference")
            self.assertTrue(Path(asset["resources"][0]["resolved_path"]).is_absolute())
            for generation_field in (
                "intended_influence",
                "precedence",
                "authority",
                "reference_use_plan_sha256",
            ):
                self.assertNotIn(generation_field, asset)

    def test_asset_lookup_summary_is_technical_and_compact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self._install_fixture_catalog(Path(temporary))
            summary = catalog_cli.asset_lookup("fixture-many", summary=True)
            self.assertEqual(summary["asset_count"], 2)
            self.assertEqual(
                [asset["asset_id"] for asset in summary["assets"]],
                ["asset-b", "asset-c"],
            )
            self.assertEqual(
                set(summary["assets"][0]),
                {"asset_id", "artifacts"},
            )
            self.assertEqual(
                summary["assets"][0]["artifacts"],
                [{
                    "artifact_id": "primary-vector",
                    "role": "identity-reference",
                    "media_type": "image/svg+xml",
                }],
            )

            def object_keys(value: object) -> set[str]:
                if isinstance(value, dict):
                    return set(value) | {
                        key
                        for nested in value.values()
                        for key in object_keys(nested)
                    }
                if isinstance(value, list):
                    return {
                        key
                        for nested in value
                        for key in object_keys(nested)
                    }
                return set()

            keys = object_keys(summary)
            for excluded in ("record", "resources", "resolved_path", "sha256"):
                self.assertNotIn(excluded, keys)

    def test_inspect_out_writes_utf8_json_without_stdout(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _entries, _ = self._install_fixture_catalog(root)
            fixture_catalog = catalog_cli.load_pack_catalog()
            output_path = root / "nested" / "inspection.json"
            stdout = io.StringIO()
            with mock.patch.object(
                catalog_retrieval.runtime,
                "load_runtime_catalog",
                return_value=fixture_catalog,
            ):
                with contextlib.redirect_stdout(stdout):
                    exit_code = catalog_cli.main([
                        "inspect",
                        "fixture-many",
                        "--out",
                        str(output_path),
                    ])
            self.assertEqual(exit_code, 0)
            self.assertEqual(stdout.getvalue(), "")
            raw = output_path.read_bytes()
            self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
            report = json.loads(raw.decode("utf-8"))
            self.assertEqual(report["record_id"], "fixture-many")
            self.assertEqual(report["linked_asset_activation"]["asset_count"], 2)

    def test_inspect_rejects_asset_ids_in_favor_of_asset_lookup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            entries, _ = self._install_fixture_catalog(Path(temporary))
            with self.assertRaisesRegex(SystemExit, "Use asset-lookup"):
                catalog_cli.inspect_record(entries, "asset-a")

    def test_catalog_cli_has_no_parallel_reference_selection_command(self) -> None:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as raised:
                catalog_cli.main(["select-references", "identity=asset-a"])
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("invalid choice", stderr.getvalue())

    def test_cli_explicit_state_cache_and_managed_root_do_not_use_ambient_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state_file = root / "state.json"
            state_file.write_text(
                json.dumps({
                    "pack_roots": [],
                    "enabled_packs": [],
                    "resource_providers": {},
                }),
                encoding="utf-8",
            )
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = catalog_cli.main([
                    "--state-file", str(state_file),
                    "--cache-dir", str(root / "cache"),
                    "--managed-root", str(root / "managed"),
                    "stats",
                ])
            self.assertEqual(exit_code, 0)
            report = json.loads(output.getvalue())
            self.assertEqual(report["active_pack_count"], 0)

            incomplete_runtime_arguments = [
                ["--state-file", str(state_file)],
                ["--cache-dir", str(root / "partial-cache")],
                ["--managed-root", str(root / "partial-managed")],
                [
                    "--state-file", str(state_file),
                    "--cache-dir", str(root / "partial-cache"),
                ],
                ["--pack-root", str(root)],
            ]
            for runtime_arguments in incomplete_runtime_arguments:
                with self.subTest(runtime_arguments=runtime_arguments):
                    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
                        io.StringIO()
                    ):
                        with self.assertRaises(SystemExit) as raised:
                            catalog_cli.main([*runtime_arguments, "stats"])
                    self.assertEqual(raised.exception.code, 2)

    def test_asset_resource_cannot_escape_owning_pack(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "pack"
            root.mkdir()
            entry = catalog_cli.Entry(
                "asset",
                "visual-evidence",
                {
                    "id": "asset-escape",
                    "primary_resource": "../escape.svg",
                    "artifacts": [{
                        "artifact_id": "escape",
                        "role": "identity-reference",
                        "path": "../escape.svg",
                        "media_type": "image/svg+xml",
                        "sha256": "c" * 64,
                    }],
                },
                PACK_ID,
                root,
                "records/assets.json",
            )
            with self.assertRaisesRegex(ValueError, "invalid pack-relative path|escapes"):
                catalog_cli.resolve_asset_resources(entry)

    def test_request_boundary_loads_runtime_catalog_once(self) -> None:
        catalog = RuntimePackCatalog(
            fingerprint="empty-fixture",
            active_pack_count=0,
            entries=(),
            phrases={},
            profiles={},
            resources={},
            assets_by_canonical_record={},
            diagnostics=(),
        )
        with mock.patch.object(catalog_retrieval.runtime, "load_runtime_catalog", return_value=catalog) as loader:
            catalog_cli.begin_catalog_request()
            catalog_cli.load_pack_catalog()
            catalog_cli.load_pack_catalog()
            self.assertEqual(loader.call_count, 1)

    def test_retrieval_cache_keys_separate_record_and_index_fingerprints(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            def entry(label: str, prompt: str) -> catalog_cli.Entry:
                return catalog_cli.Entry(
                    "module",
                    "camera",
                    {
                        "id": "cache-probe",
                        "label": label,
                        "category": "camera",
                        "domains": ["shared"],
                        "prompt": prompt,
                    },
                    PACK_ID,
                    root,
                    "records/cache-probe.json",
                )

            amber = entry("amber prism camera", "amber prism framing")
            amber_clone = entry("amber prism camera", "amber prism framing")
            cobalt = entry("cobalt spiral camera", "cobalt spiral framing")
            amber_index = SearchIndex({
                "records": {},
                "phrases": {
                    "amber prism": [{
                        "id": "cache-probe",
                        "facet": "camera",
                        "weight": 1.0,
                        "source": "fixture",
                    }],
                },
            })
            cobalt_index = SearchIndex({
                "records": {},
                "phrases": {
                    "cobalt spiral": [{
                        "id": "cache-probe",
                        "facet": "camera",
                        "weight": 1.0,
                        "source": "fixture",
                    }],
                },
            })

            self.assertEqual(amber.fingerprint, amber_clone.fingerprint)
            self.assertNotEqual(amber.fingerprint, cobalt.fingerprint)
            self.assertNotEqual(amber_index.fingerprint, cobalt_index.fingerprint)

            catalog_retrieval.runtime._PACK_CATALOG_CACHE = RuntimePackCatalog(
                fingerprint="cache-key-fixture",
                active_pack_count=1,
                entries=(),
                phrases={},
                profiles={},
                resources={},
                assets_by_canonical_record={},
                diagnostics=(),
            )

            def retrieve(
                candidate: catalog_cli.Entry,
                query: str,
                index: SearchIndex,
            ) -> list[dict[str, object]]:
                return catalog_cli.search_entries(
                    [candidate],
                    query,
                    kinds={"module"},
                    categories={"camera"},
                    domain=None,
                    limit=1,
                    diverse=False,
                    search_index=index,
                )

            first = retrieve(amber, "amber prism camera", amber_index)
            same_content = retrieve(amber_clone, "amber prism camera", amber_index)
            changed_record = retrieve(cobalt, "cobalt spiral camera", amber_index)
            changed_index = retrieve(amber, "amber prism camera", cobalt_index)

            self.assertEqual(first, same_content)
            self.assertEqual(first[0]["prompt"], "amber prism framing")
            self.assertEqual(changed_record[0]["prompt"], "cobalt spiral framing")

            expected_derived_keys = {
                (amber_index.fingerprint, amber.fingerprint),
                (amber_index.fingerprint, cobalt.fingerprint),
                (cobalt_index.fingerprint, amber.fingerprint),
            }
            self.assertEqual(set(catalog_retrieval.runtime._RUNTIME_PROFILE_CACHE), expected_derived_keys)
            self.assertEqual(set(catalog_retrieval.runtime._INDEXED_ENTRY_CACHE), expected_derived_keys)

            amber_signature = hashlib.sha256(
                amber.fingerprint.encode("utf-8")
            ).hexdigest()
            cobalt_signature = hashlib.sha256(
                cobalt.fingerprint.encode("utf-8")
            ).hexdigest()
            expected_corpus_keys = {
                (
                    amber_signature,
                    ("module",),
                    ("camera",),
                    "any",
                    "",
                    amber_index.fingerprint,
                ),
                (
                    cobalt_signature,
                    ("module",),
                    ("camera",),
                    "any",
                    "",
                    amber_index.fingerprint,
                ),
                (
                    amber_signature,
                    ("module",),
                    ("camera",),
                    "any",
                    "",
                    cobalt_index.fingerprint,
                ),
            }
            self.assertEqual(set(catalog_retrieval.runtime._CORPUS_CACHE), expected_corpus_keys)

    def test_all_retrieval_lru_caches_enforce_bounds_and_recency(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            entries = [
                catalog_cli.Entry(
                    "module",
                    "camera",
                    {
                        "id": f"lru-probe-{position}",
                        "label": f"lru marker {position} camera",
                        "category": "camera",
                        "domains": ["shared"],
                        "prompt": f"lru marker {position} framing",
                    },
                    PACK_ID,
                    root,
                    f"records/lru-probe-{position}.json",
                )
                for position in range(3)
            ]
            index = SearchIndex({"records": {}, "phrases": {}})
            expected_fingerprints = {
                entries[0].fingerprint,
                entries[2].fingerprint,
            }

            with mock.patch.object(catalog_retrieval.runtime, "_MAX_RUNTIME_PROFILE_CACHE", 2):
                catalog_cli.runtime_profile(entries[0], index)
                catalog_cli.runtime_profile(entries[1], index)
                catalog_cli.runtime_profile(entries[0], index)
                catalog_cli.runtime_profile(entries[2], index)
            self.assertEqual(len(catalog_retrieval.runtime._RUNTIME_PROFILE_CACHE), 2)
            self.assertEqual(
                {key[1] for key in catalog_retrieval.runtime._RUNTIME_PROFILE_CACHE},
                expected_fingerprints,
            )

            catalog_retrieval.runtime._INDEXED_ENTRY_CACHE.clear()
            with mock.patch.object(catalog_retrieval.runtime, "_MAX_INDEXED_ENTRY_CACHE", 2):
                catalog_retrieval.scoring._build_indexed_entry(entries[0], index)
                catalog_retrieval.scoring._build_indexed_entry(entries[1], index)
                catalog_retrieval.scoring._build_indexed_entry(entries[0], index)
                catalog_retrieval.scoring._build_indexed_entry(entries[2], index)
            self.assertEqual(len(catalog_retrieval.runtime._INDEXED_ENTRY_CACHE), 2)
            self.assertEqual(
                {key[1] for key in catalog_retrieval.runtime._INDEXED_ENTRY_CACHE},
                expected_fingerprints,
            )

            catalog_retrieval.runtime._CORPUS_CACHE.clear()
            catalog_retrieval.runtime._PACK_CATALOG_CACHE = RuntimePackCatalog(
                fingerprint="lru-fixture",
                active_pack_count=1,
                entries=(),
                phrases={},
                profiles={},
                resources={},
                assets_by_canonical_record={},
                diagnostics=(),
            )

            def retrieve(position: int) -> None:
                catalog_cli.search_entries(
                    [entries[position]],
                    f"lru marker {position} camera",
                    kinds={"module"},
                    categories={"camera"},
                    domain=None,
                    limit=1,
                    diverse=False,
                    search_index=index,
                )

            with mock.patch.object(catalog_retrieval.runtime, "_MAX_CORPUS_CACHE", 2):
                retrieve(0)
                retrieve(1)
                retrieve(0)
                retrieve(2)
            self.assertEqual(len(catalog_retrieval.runtime._CORPUS_CACHE), 2)
            self.assertEqual(
                [
                    corpus.entries[0].record["id"]
                    for corpus in catalog_retrieval.runtime._CORPUS_CACHE.values()
                ],
                ["lru-probe-0", "lru-probe-2"],
            )

    def test_raw_non_english_cli_query_is_rejected_with_actionable_guidance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self._install_fixture_catalog(Path(temporary))
            fixture_catalog = catalog_cli.load_pack_catalog()
            with mock.patch.object(
                catalog_retrieval.runtime,
                "load_runtime_catalog",
                return_value=fixture_catalog,
            ):
                brief = "아침 안개 속의 회색 왜가리 배달부"
                with self.assertRaises(SystemExit) as raised:
                    catalog_cli.main(["search", brief])

            guidance = str(raised.exception)
            for required in (
                "canonical English retrieval text",
                "not raw user-language prose",
                "Translate the complete brief semantically",
                "calling agent",
                "--query-json",
                "source_brief",
                "original wording",
                "no per-language alias table",
            ):
                with self.subTest(required=required):
                    self.assertIn(required, guidance)

            structured = catalog_cli.catalog_query_from_mapping({
                "canonical_query": "gray heron courier in morning fog",
                "anchors": {
                    "species": ["heron"],
                    "body_build": ["slender"],
                },
                "source_brief": brief,
                "source_language": "ko",
            })
            validated = catalog_cli.validate_query_request(structured)
            self.assertEqual(validated.source_brief, brief)
            self.assertEqual(validated.source_language, "ko")

    def test_public_inspire_and_recommend_help_expose_working_controls(self) -> None:
        help_by_command: dict[str, str] = {}
        for command in ("inspire", "recommend"):
            stdout = io.StringIO()
            with self.subTest(command=command):
                with mock.patch.dict(os.environ, UNPAINTED):
                    with contextlib.redirect_stdout(stdout):
                        with self.assertRaises(SystemExit) as stopped:
                            catalog_cli.main([command, "--help"])
                self.assertEqual(stopped.exception.code, 0)
                help_by_command[command] = stdout.getvalue()

        inspire_help = help_by_command["inspire"]
        self.assertIn("--tier {any,curated,vocabulary}", inspire_help)
        for option in (
            "--profile-limit",
            "--core-limit",
            "--style-family-limit",
            "--realization-limit",
        ):
            with self.subTest(option=option):
                self.assertIn(option, inspire_help)
        self.assertIn("--directions", help_by_command["recommend"])

        with tempfile.TemporaryDirectory() as temporary:
            self._install_fixture_catalog(Path(temporary))
            fixture_catalog = catalog_cli.load_pack_catalog()
            stdout = io.StringIO()
            with mock.patch.object(
                catalog_retrieval.runtime,
                "load_runtime_catalog",
                return_value=fixture_catalog,
            ):
                with mock.patch.object(
                    catalog_retrieval.batch,
                    "inspire",
                    return_value={"mode": "public-inspire-fixture"},
                ) as inspire_call:
                    with contextlib.redirect_stdout(stdout):
                        self.assertEqual(catalog_cli.main([
                            "inspire",
                            "fixture identity",
                            "--tier",
                            "vocabulary",
                            "--profile-limit",
                            "1",
                            "--core-limit",
                            "2",
                            "--style-family-limit",
                            "3",
                            "--realization-limit",
                            "4",
                        ]), 0)
            inspire_args = inspire_call.call_args.args
            self.assertEqual(inspire_args[5:10], ("vocabulary", 1, 2, 3, 4))
            self.assertEqual(json.loads(stdout.getvalue())["mode"], "public-inspire-fixture")

            stdout = io.StringIO()
            with mock.patch.object(
                catalog_retrieval.runtime,
                "load_runtime_catalog",
                return_value=fixture_catalog,
            ):
                with mock.patch.object(
                    catalog_retrieval.batch,
                    "recommend",
                    return_value={"mode": "public-recommend-fixture"},
                ) as recommend_call:
                    with contextlib.redirect_stdout(stdout):
                        self.assertEqual(catalog_cli.main([
                            "recommend",
                            "fixture identity",
                            "--directions",
                            "7",
                        ]), 0)
            self.assertEqual(recommend_call.call_args.args[3], 7)
            self.assertEqual(
                json.loads(stdout.getvalue())["mode"],
                "public-recommend-fixture",
            )

    def test_inspect_distinguishes_curated_knowledge_from_vocabulary_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime_entries = (
                _runtime_entry(
                    root,
                    "module",
                    {
                        "id": "fixture-curated-camera",
                        "label": "Fixture curated camera construction",
                        "category": "camera",
                        "curation_status": "curated",
                        "visual_function": "Constructs a complete fixture camera decision.",
                        "prompt": "A fully authored fixture camera construction.",
                    },
                    "camera",
                ),
                _runtime_entry(
                    root,
                    "module",
                    {
                        "id": "fixture-vocabulary-token",
                        "label": "fixture token",
                        "category": "prop",
                        "curation_status": "vocabulary",
                        "prompt": "fixture token",
                        "tags": ["fixture token"],
                    },
                    "prop",
                ),
            )
            catalog_retrieval.runtime._PACK_CATALOG_CACHE = RuntimePackCatalog(
                fingerprint="inspect-tier-fixture",
                active_pack_count=1,
                entries=runtime_entries,
                phrases={},
                profiles={},
                resources={},
                assets_by_canonical_record={},
                diagnostics=(),
            )
            entries = catalog_cli.load_entries()
            curated = catalog_cli.inspect_record(entries, "fixture-curated-camera")
            vocabulary = catalog_cli.inspect_record(entries, "fixture-vocabulary-token")

            self.assertEqual(curated["tier"], "curated")
            self.assertIn("complete curated canonical record", curated["note"])
            self.assertEqual(vocabulary["tier"], "vocabulary")
            self.assertIn("VOCABULARY record", vocabulary["note"])
            self.assertIn("this is the whole record, not a summary", vocabulary["note"])
            self.assertIn("supply the craft decisions", vocabulary["note"])
            self.assertEqual(
                set(vocabulary["record"]),
                {"id", "label", "category", "curation_status", "prompt", "tags"},
            )
            self.assertNotIn("visual_function", vocabulary["record"])
            self.assertNotIn("invariants", vocabulary["record"])

    def test_batch_preserves_order_and_matches_individual_search(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            entries, canonical_ids = self._install_fixture_catalog(Path(temporary))
            requests = catalog_cli.load_batch_requests(json.dumps([
                {
                    "request_id": f"probe-{position}",
                    "command": "search",
                    "canonical_query": record_id.replace("-", " "),
                    "kind": ["module"],
                    "categories": ["species"],
                    "limit": 1,
                    "group_variants": False,
                }
                for position, record_id in enumerate([
                    canonical_ids[2],
                    canonical_ids[0],
                    canonical_ids[1],
                    canonical_ids[2],
                ])
            ]))

            with mock.patch.object(
                catalog_retrieval.batch,
                "load_search_index",
                wraps=catalog_retrieval.batch.load_search_index,
            ) as index_loader:
                report = catalog_cli.execute_batch(entries, requests)
            self.assertEqual(index_loader.call_count, 1)
            self.assertEqual(report["request_count"], 4)
            self.assertEqual(report["error_count"], 0)
            self.assertEqual(
                [row["request_id"] for row in report["results"]],
                ["probe-0", "probe-1", "probe-2", "probe-3"],
            )

            index = catalog_cli.load_search_index()
            for item, batch_row in zip(requests, report["results"], strict=True):
                request = catalog_retrieval.batch._batch_query_request(item)
                individual = catalog_cli.execute_query_command(
                    entries,
                    "search",
                    request,
                    item,
                    search_index=index,
                )
                self.assertEqual(batch_row["result"], individual)

    def test_batch_rejects_invalid_top_level_contract(self) -> None:
        with self.assertRaisesRegex(ValueError, "top-level JSON array"):
            catalog_cli.load_batch_requests('{"request_id":"not-an-array"}')
        with self.assertRaisesRegex(ValueError, "duplicate batch request_id"):
            catalog_cli.load_batch_requests(json.dumps([
                {"request_id": "same", "command": "search"},
                {"request_id": "same", "command": "search"},
            ]))

    def test_batch_help_exposes_copyable_input_contract(self) -> None:
        stdout = io.StringIO()
        with self.assertRaises(SystemExit) as stopped:
            with contextlib.redirect_stdout(stdout):
                catalog_cli.main(["batch", "--help"])
        self.assertEqual(stopped.exception.code, 0)
        help_text = stdout.getvalue()
        example = catalog_cli.batch_help_example()
        self.assertIn("request_id", help_text)
        self.assertIn("canonical_query", help_text)
        self.assertIn("search, recommend, and inspire", help_text)
        self.assertIn(example, help_text)
        self.assertEqual(
            catalog_cli.load_batch_requests(example)[0]["request_id"],
            "identity",
        )

    def test_batch_returns_query_errors_without_losing_later_results(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            entries, _ = self._install_fixture_catalog(Path(temporary))
            report = catalog_cli.execute_batch(entries, [
                {
                    "request_id": "bad-command",
                    "command": "unknown",
                    "canonical_query": "fixture zero",
                },
                {
                    "request_id": "bad-query",
                    "command": "search",
                    "canonical_query": "",
                },
                {
                    "request_id": "good-search",
                    "command": "search",
                    "canonical_query": "fixture one",
                    "kind": ["module"],
                    "categories": ["species"],
                    "limit": 1,
                },
            ])
            self.assertEqual(report["success_count"], 1)
            self.assertEqual(report["error_count"], 2)
            self.assertFalse(report["results"][0]["ok"])
            self.assertEqual(
                report["results"][0]["error"]["type"],
                "query-error",
            )
            self.assertFalse(report["results"][1]["ok"])
            self.assertTrue(report["results"][2]["ok"])
            self.assertEqual(report["results"][2]["request_id"], "good-search")

    def test_batch_does_not_hide_runtime_or_catalog_failures(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            entries, _ = self._install_fixture_catalog(Path(temporary))
            with mock.patch.object(
                catalog_retrieval.batch,
                "recommend",
                side_effect=SystemExit("Required named pack resource is unavailable"),
            ):
                with self.assertRaisesRegex(SystemExit, "Required named pack resource"):
                    catalog_cli.execute_batch(entries, [{
                        "request_id": "runtime-failure",
                        "command": "recommend",
                        "canonical_query": "fixture identity",
                    }])

    def test_batch_dispatches_recommend_and_inspire_with_shared_index(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            entries, _ = self._install_fixture_catalog(Path(temporary))
            with mock.patch.object(
                catalog_retrieval.batch,
                "recommend",
                return_value={"mode": "recommend-fixture"},
            ) as recommendation:
                with mock.patch.object(
                    catalog_retrieval.batch,
                    "inspire",
                    return_value={"mode": "inspire-fixture"},
                ) as inspiration:
                    report = catalog_cli.execute_batch(entries, [
                        {
                            "request_id": "recommend",
                            "command": "recommend",
                            "canonical_query": "fixture identity",
                            "directions": 2,
                        },
                        {
                            "request_id": "inspire",
                            "command": "inspire",
                            "canonical_query": "fixture identity",
                            "categories": ["species"],
                            "profile_limit": 0,
                            "core_limit": 0,
                            "style_family_limit": 0,
                            "realization_limit": 0,
                            "archetype_limit": 0,
                        },
                    ])
            self.assertEqual(report["error_count"], 0)
            self.assertEqual(
                [row["result"]["mode"] for row in report["results"]],
                ["recommend-fixture", "inspire-fixture"],
            )
            self.assertIsNotNone(recommendation.call_args.kwargs["search_index"])
            self.assertIs(
                recommendation.call_args.kwargs["search_index"],
                inspiration.call_args.kwargs["search_index"],
            )

    def test_batch_cli_loads_catalog_and_entries_once(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._install_fixture_catalog(root)
            fixture_catalog = catalog_cli.load_pack_catalog()
            batch_path = root / "batch.json"
            batch_path.write_text(
                json.dumps([
                    {
                        "request_id": "first",
                        "command": "search",
                        "canonical_query": "fixture zero",
                        "kind": ["module"],
                        "categories": ["species"],
                        "limit": 1,
                    },
                    {
                        "request_id": "second",
                        "command": "search",
                        "canonical_query": "fixture one",
                        "kind": ["module"],
                        "categories": ["species"],
                        "limit": 1,
                    },
                ]),
                encoding="utf-8",
            )
            stdout = io.StringIO()
            with mock.patch.object(
                catalog_retrieval.runtime,
                "load_runtime_catalog",
                return_value=fixture_catalog,
            ) as catalog_loader:
                with mock.patch.object(
                    catalog_cli,
                    "load_entries",
                    wraps=catalog_cli.load_entries,
                ) as entry_loader:
                    with contextlib.redirect_stdout(stdout):
                        exit_code = catalog_cli.main([
                            "batch",
                            "--input",
                            str(batch_path),
                        ])
            self.assertEqual(exit_code, 0)
            self.assertEqual(catalog_loader.call_count, 1)
            self.assertEqual(entry_loader.call_count, 1)
            report = json.loads(stdout.getvalue())
            self.assertEqual(
                [row["request_id"] for row in report["results"]],
                ["first", "second"],
            )

    def test_batch_handles_catalog_larger_than_eleven_thousand_records(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime_entries = tuple(
                _runtime_entry(
                    root,
                    "module",
                    {
                        "id": f"large-fixture-{position:05d}",
                        "label": f"large fixture marker {position}",
                        "category": "species",
                        "curation_status": "curated",
                        "prompt": "Large fixture marker.",
                    },
                    "species",
                )
                for position in range(11_001)
            )
            catalog_retrieval.runtime._PACK_CATALOG_CACHE = RuntimePackCatalog(
                fingerprint="large-batch-fixture",
                active_pack_count=1,
                entries=runtime_entries,
                phrases={},
                profiles={},
                resources={},
                assets_by_canonical_record={},
                diagnostics=(),
            )
            entries = catalog_cli.load_entries()
            self.assertGreater(len(entries), 11_000)
            report = catalog_cli.execute_batch(entries, [{
                "request_id": "large-search",
                "command": "search",
                "canonical_query": "large fixture marker 11000",
                "kind": ["module"],
                "categories": ["species"],
                "limit": 1,
            }])
            self.assertEqual(report["success_count"], 1)
            self.assertEqual(report["error_count"], 0)

    def test_no_active_pack_is_diagnosed_before_search(self) -> None:
        catalog = RuntimePackCatalog(
            fingerprint="empty-fixture",
            active_pack_count=0,
            entries=(),
            phrases={},
            profiles={},
            resources={},
            assets_by_canonical_record={},
            diagnostics=(),
        )
        with mock.patch.object(catalog_retrieval.runtime, "load_runtime_catalog", return_value=catalog):
            with self.assertRaisesRegex(SystemExit, "No active content pack"):
                catalog_cli.main(["search", "fixture query"])

    def test_absent_category_is_a_valid_empty_result(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            entries, _ = self._install_fixture_catalog(Path(temporary))
            self.assertEqual(
                catalog_cli.search_entries(
                    entries,
                    "quiet authority",
                    kinds={"module"},
                    categories={"not-present-in-active-pack"},
                    domain=None,
                    limit=2,
                    diverse=False,
                ),
                [],
            )

    def test_inspiration_preserves_full_query_with_scoped_analysis(self) -> None:
        index = SearchIndex({
            "records": {},
            "phrases": {
                "close portrait": [{"id": "camera", "facet": "camera", "weight": 1.0, "source": "author"}],
                "window light": [{"id": "light", "facet": "lighting", "weight": 1.0, "source": "author"}],
                "quiet authority": [{"id": "emotion", "facet": "performance", "weight": 1.0, "source": "author"}],
            },
        })
        query = "close portrait, window light, quiet authority"
        analysis = analyze_query(query, index)
        with mock.patch.object(catalog_retrieval.retrieval, "load_search_index", return_value=index):
            with mock.patch.object(catalog_retrieval.retrieval, "search_entries", return_value=[]) as search:
                result = catalog_cli.inspire(
                    [],
                    query,
                    ["camera", "lighting", "emotion-nuance", "rendering"],
                    None,
                    2,
                    profile_limit=0,
                    core_limit=0,
                    style_family_limit=0,
                    realization_limit=0,
                    archetype_limit=0,
                    analysis=analysis,
                )
        category_calls = [
            call for call in search.call_args_list
            if call.kwargs.get("kinds") == {"module"}
        ]
        self.assertEqual(len(category_calls), 4)
        self.assertTrue(all(call.args[1] == query for call in category_calls))
        self.assertTrue(all(call.kwargs.get("analysis") is analysis for call in category_calls))
        self.assertEqual(
            result["category_queries"],
            {
                "camera": query,
                "lighting": query,
                "emotion-nuance": query,
                "rendering": query,
            },
        )

    def test_hair_texture_uses_contextual_permanent_identity_facet(self) -> None:
        self.assertEqual(
            catalog_cli.semantic_primary_facet("module", "hair-texture"),
            "hair_texture",
        )

    def test_category_anchor_excludes_incidental_same_category_match(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime_entries = (
                _runtime_entry(
                    root,
                    "module",
                    {
                        "id": "fixture-tool-torque-key",
                        "label": "wrench",
                        "category": "prop",
                        "prompt": "wrench",
                    },
                    "prop",
                ),
                _runtime_entry(
                    root,
                    "module",
                    {
                        "id": "prop-tall-soda-float",
                        "label": "tall soda float",
                        "category": "prop",
                        "prompt": "one tall stemmed soda glass",
                    },
                    "prop",
                ),
            )
            catalog_retrieval.runtime._PACK_CATALOG_CACHE = RuntimePackCatalog(
                fingerprint="category-anchor-fixture",
                active_pack_count=1,
                entries=runtime_entries,
                phrases={},
                profiles={},
                resources={},
                assets_by_canonical_record={},
                diagnostics=(),
            )
            entries = catalog_cli.load_entries()
            index = SearchIndex({
                "records": {},
                "phrases": {
                    "wrench": [{
                        "id": "fixture-tool-torque-key",
                        "facet": "prop",
                        "weight": 1.0,
                        "source": "label",
                    }],
                },
            })
            query = "tall maintenance robot holding an oversized wrench"
            analysis = analyze_query(query, index, "robot")

            hits = catalog_cli.search_entries(
                entries,
                query,
                kinds={"module"},
                categories={"prop"},
                domain="robot",
                limit=4,
                diverse=False,
                search_index=index,
                analysis=analysis,
            )

            self.assertEqual(["fixture-tool-torque-key"], [row["id"] for row in hits])
            self.assertEqual(query, analysis.query)

    def test_semantic_association_scores_once_at_max_weight(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime = _runtime_entry(
                root,
                "module",
                {
                    "id": "quiet-authority",
                    "label": "Quiet authority",
                    "category": "emotion-nuance",
                    "curation_status": "curated",
                },
                "emotion-nuance",
            )
            entry = catalog_retrieval.runtime._entry_from_runtime(runtime)
            duplicate_index = SearchIndex({
                "records": {},
                "phrases": {
                    "quiet authority": [
                        {"id": "quiet-authority", "facet": "mood", "weight": 0.5, "source": "generated"},
                        {"id": "quiet-authority", "facet": "mood", "weight": 1.5, "source": "author"},
                    ]
                },
            })
            max_only_index = SearchIndex({
                "records": {},
                "phrases": {
                    "quiet authority": [
                        {"id": "quiet-authority", "facet": "mood", "weight": 1.5, "source": "author"},
                    ]
                },
            })

            def score(index: SearchIndex) -> tuple[float, list[dict[str, object]]]:
                corpus = catalog_cli.Corpus([entry], index)
                analysis = analyze_query("quiet authority", index)
                value, _matched, _strong, evidence = corpus.score(
                    corpus.indexed_at(0),
                    ["quiet", "authority"],
                    "quiet authority",
                    None,
                    analysis,
                )
                return value, evidence

            duplicate_score, duplicate_evidence = score(duplicate_index)
            max_only_score, _ = score(max_only_index)
            self.assertAlmostEqual(duplicate_score, max_only_score)
            sources = {
                row["source"]
                for row in duplicate_evidence
                if str(row.get("source", "")).startswith("search-association:")
            }
            self.assertEqual(
                sources,
                {"search-association:generated", "search-association:author"},
            )


class CatalogInspirationGroupingTest(unittest.TestCase):
    """Preserve layered inspiration and tier behavior without a user pack."""

    QUERY = (
        "gentle giant warmth polished soft cel portrait anthropomorphic character "
        "protective two hand gesture fragile lantern carry cool window light "
        "soft rim light polished character illustration"
    )
    CATEGORIES = ("pose-action", "lighting")

    def tearDown(self) -> None:
        catalog_cli.clear_runtime_caches()

    def _install_catalog(
        self,
        root: Path,
    ) -> tuple[list[catalog_cli.Entry], SearchIndex]:
        records: tuple[tuple[str, str | None, dict[str, object]], ...] = (
            (
                "aesthetic-core",
                None,
                {
                    "id": "aesthetic-core-gentle-giant-fixture",
                    "label": "gentle giant warmth",
                    "curation_status": "curated",
                    "domains": ["shared"],
                    "aesthetic_promise": "Gentle giant warmth.",
                },
            ),
            (
                "style-family",
                None,
                {
                    "id": "style-family-soft-cel-fixture",
                    "label": "polished soft cel portrait",
                    "curation_status": "curated",
                    "domains": ["shared"],
                    "style_promise": "Polished soft cel portrait drawing grammar.",
                },
            ),
            (
                "domain-realization",
                None,
                {
                    "id": "domain-realization-anthropomorphic-fixture",
                    "label": "anthropomorphic character realization",
                    "curation_status": "curated",
                    "domains": ["anthropomorphic-animal"],
                    "subject_domain": "anthropomorphic-animal",
                    "base_realization": True,
                    "realization_promise": "Anthropomorphic character realization.",
                },
            ),
            (
                "profile",
                None,
                {
                    "id": "render-profile-character-illustration-fixture",
                    "label": "polished character illustration",
                    "curation_status": "curated",
                    "domains": ["shared"],
                    "rendering": "Polished character illustration.",
                },
            ),
            (
                "module",
                "pose-action",
                {
                    "id": "pose-protective-gesture-curated-fixture",
                    "label": "protective two hand gesture",
                    "category": "pose-action",
                    "curation_status": "curated",
                    "domains": ["shared"],
                    "prompt": "Protective two hand gesture.",
                },
            ),
            (
                "module",
                "pose-action",
                {
                    "id": "pose-lantern-carry-vocabulary-fixture",
                    "label": "fragile lantern carry",
                    "category": "pose-action",
                    "domains": ["shared"],
                    "prompt": "Fragile lantern carry.",
                },
            ),
            (
                "module",
                "lighting",
                {
                    "id": "lighting-window-curated-fixture",
                    "label": "cool window light",
                    "category": "lighting",
                    "curation_status": "curated",
                    "domains": ["shared"],
                    "prompt": "Cool window light.",
                },
            ),
            (
                "module",
                "lighting",
                {
                    "id": "lighting-rim-vocabulary-fixture",
                    "label": "soft rim light",
                    "category": "lighting",
                    "domains": ["shared"],
                    "prompt": "Soft rim light.",
                },
            ),
            # Same wording, one mapped category and one the facet table does
            # not name. The unmapped record must stay reachable from a scoped
            # query instead of being silenced by the fallback facet.
            (
                "module",
                "outfit",
                {
                    "id": "outfit-navy-lacquer-fixture",
                    "label": "navy lacquer",
                    "category": "outfit",
                    "curation_status": "curated",
                    "domains": ["shared"],
                    "tags": ["navy", "lacquer"],
                    "prompt": "Navy lacquer.",
                },
            ),
            (
                "module",
                "nail-style",
                {
                    "id": "nail-style-navy-lacquer-fixture",
                    "label": "navy lacquer",
                    "category": "nail-style",
                    "curation_status": "curated",
                    "domains": ["shared"],
                    "tags": ["navy", "lacquer"],
                    "prompt": "Navy lacquer.",
                },
            ),
            (
                "recipe",
                None,
                {
                    "id": "recipe-soft-rim-light-fixture",
                    "label": "soft rim light",
                    "curation_status": "curated",
                    "domain": "anthropomorphic-animal",
                    "domains": ["anthropomorphic-animal"],
                    "base_scene_id": "scene-fixture",
                    "render_profile_id": (
                        "render-profile-character-illustration-fixture"
                    ),
                    "rendering": "Soft rim light.",
                    "aspect_ratio": "2:3",
                    "search_terms": ["soft rim light"],
                    "tags": ["lighting"],
                },
            ),
        )
        runtime_entries = tuple(
            _runtime_entry(root, kind, record, category)
            for kind, category, record in records
        )
        catalog_cli.clear_runtime_caches()
        catalog_retrieval.runtime._PACK_CATALOG_CACHE = RuntimePackCatalog(
            fingerprint="inspiration-grouping-fixture",
            active_pack_count=1,
            entries=runtime_entries,
            phrases={},
            profiles={},
            resources={},
            assets_by_canonical_record={},
            diagnostics=(),
        )
        return catalog_cli.load_entries(), SearchIndex({"records": {}, "phrases": {}})

    def _inspire(
        self,
        entries: list[catalog_cli.Entry],
        index: SearchIndex,
        *,
        tier: str = "any",
    ) -> dict[str, object]:
        return catalog_cli.inspire(
            entries,
            self.QUERY,
            self.CATEGORIES,
            "anthropomorphic-animal",
            4,
            tier=tier,
            profile_limit=2,
            core_limit=2,
            style_family_limit=2,
            realization_limit=2,
            archetype_limit=0,
            search_index=index,
        )

    def test_inspire_keeps_each_curated_layer_in_a_separate_group(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            entries, index = self._install_catalog(Path(temporary))
            result = self._inspire(entries, index)

            expected_kinds = {
                "aesthetic_cores": "aesthetic-core",
                "style_families": "style-family",
                "domain_realizations": "domain-realization",
                "render_profiles": "profile",
            }
            grouped_ids: set[str] = set()
            for group, expected_kind in expected_kinds.items():
                with self.subTest(group=group):
                    candidates = result[group]
                    self.assertTrue(candidates)
                    self.assertTrue(
                        all(item["kind"] == expected_kind for item in candidates)
                    )
                    ids = {str(item["id"]) for item in candidates}
                    self.assertTrue(grouped_ids.isdisjoint(ids))
                    grouped_ids.update(ids)
            self.assertTrue(
                all(
                    item["kind"] == "module"
                    for candidates in result["categories"].values()
                    for item in candidates
                )
            )

    def test_inspire_emits_only_supported_relevance_bands(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            entries, index = self._install_catalog(Path(temporary))
            result = self._inspire(entries, index)
            groups = [
                *result["categories"].values(),
                result["aesthetic_cores"],
                result["style_families"],
                result["domain_realizations"],
                result["render_profiles"],
            ]
            candidates = [item for group in groups for item in group]
            self.assertTrue(candidates)
            self.assertTrue(
                all(
                    item["relevance"]
                    in {"strong", "moderate", "domain-foundation"}
                    for item in candidates
                )
            )

    def test_atomic_any_retains_both_roles_and_curated_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            entries, index = self._install_catalog(Path(temporary))
            broad = self._inspire(entries, index, tier="any")
            curated = self._inspire(entries, index, tier="curated")

            broad_atomic = [
                item
                for candidates in broad["categories"].values()
                for item in candidates
            ]
            curated_atomic = [
                item
                for candidates in curated["categories"].values()
                for item in candidates
            ]
            self.assertEqual(broad["tier"], "any")
            self.assertEqual(
                {item["tier"] for item in broad_atomic},
                {"curated", "vocabulary"},
            )
            self.assertTrue(curated_atomic)
            self.assertTrue(all(item["tier"] == "curated" for item in curated_atomic))
            self.assertGreaterEqual(
                sum(bool(candidates) for candidates in broad["categories"].values()),
                sum(bool(candidates) for candidates in curated["categories"].values()),
            )
            self.assertGreaterEqual(len(broad_atomic), len(curated_atomic))

    def test_search_tier_filter_exercises_curated_and_vocabulary_roles(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            entries, index = self._install_catalog(Path(temporary))

            def search(tier: str) -> list[dict[str, object]]:
                return catalog_cli.search_entries(
                    entries,
                    self.QUERY,
                    kinds={"module"},
                    categories=set(self.CATEGORIES),
                    domain="anthropomorphic-animal",
                    limit=8,
                    diverse=False,
                    tier=tier,
                    search_index=index,
                )

            curated = search("curated")
            vocabulary = search("vocabulary")
            self.assertEqual(
                {item["id"] for item in curated},
                {
                    "pose-protective-gesture-curated-fixture",
                    "lighting-window-curated-fixture",
                },
            )
            self.assertTrue(all(item["tier"] == "curated" for item in curated))
            self.assertEqual(
                {item["id"] for item in vocabulary},
                {
                    "pose-lantern-carry-vocabulary-fixture",
                    "lighting-rim-vocabulary-fixture",
                },
            )
            self.assertTrue(
                all(item["tier"] == "vocabulary" for item in vocabulary)
            )

    def _query_kinds(
        self,
        entries: list[catalog_cli.Entry],
        index: SearchIndex,
        options: dict[str, object],
    ) -> set[str]:
        result = catalog_cli.execute_query_command(
            entries,
            "search",
            CatalogQueryInput(canonical_query=self.QUERY),
            options,
            search_index=index,
        )
        return {str(row["kind"]) for row in result["results"]}

    def test_recipe_kind_is_requested_explicitly_and_never_discarded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            entries, index = self._install_catalog(Path(temporary))

            self.assertEqual(
                {"recipe"},
                self._query_kinds(entries, index, {"kind": "recipe", "limit": 20}),
            )
            self.assertIn(
                "recipe",
                self._query_kinds(
                    entries, index, {"include_recipes": True, "limit": 30}
                ),
            )
            self.assertNotIn(
                "recipe", self._query_kinds(entries, index, {"limit": 30})
            )
            with self.assertRaises(ValueError):
                self._query_kinds(entries, index, {"kind": ""})

    def test_structured_anchor_facet_names_are_validated(self) -> None:
        with self.assertRaises(ValueError):
            validate_query_request(
                CatalogQueryInput(
                    canonical_query="elderly botanist",
                    anchors={"age_appearance": ["elderly"]},
                )
            )
        request = validate_query_request(
            CatalogQueryInput(
                canonical_query="elderly botanist",
                anchors={"age": ["elderly"]},
            )
        )
        self.assertEqual({"age": ["elderly"]}, request.anchors)

    def test_unmapped_record_categories_survive_a_scoped_query(self) -> None:
        self.assertEqual(
            catalog_retrieval.scoring.UNMAPPED_PRIMARY_FACET,
            catalog_retrieval.scoring.semantic_primary_facet("module", "nail-style"),
        )
        with tempfile.TemporaryDirectory() as temporary:
            entries, index = self._install_catalog(Path(temporary))

            def found(query: str) -> set[str]:
                return {
                    str(row["id"])
                    for row in catalog_cli.search_entries(
                        entries,
                        query,
                        kinds={"module"},
                        categories=set(),
                        domain=None,
                        limit=12,
                        diverse=False,
                        search_index=index,
                    )
                }

            both = {
                "outfit-navy-lacquer-fixture",
                "nail-style-navy-lacquer-fixture",
            }
            self.assertEqual(both, found("navy lacquer") & both)
            self.assertEqual(both, found("navy uniform") & both)

    def test_a_narrowing_count_of_zero_is_refused_rather_than_rounded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            entries, index = self._install_catalog(Path(temporary))

            def search(limit: int) -> list[dict[str, object]]:
                return catalog_cli.search_entries(
                    entries,
                    self.QUERY,
                    kinds={"module"},
                    categories=set(),
                    domain=None,
                    limit=limit,
                    diverse=False,
                    search_index=index,
                )

            self.assertEqual([], search(0))
            self.assertEqual([], search(-1))
            self.assertEqual(1, len(search(1)))
            self.assertEqual(3, len(search(3)))

            request = CatalogQueryInput(canonical_query=self.QUERY)
            with self.assertRaises(ValueError):
                catalog_cli.execute_query_command(
                    entries, "search", request, {"limit": 0}, search_index=index
                )
            with self.assertRaises(ValueError):
                catalog_cli.execute_query_command(
                    entries,
                    "inspire",
                    request,
                    {"per_category": 0},
                    search_index=index,
                )
            catalog_cli.execute_query_command(
                entries,
                "inspire",
                request,
                {"profile_limit": 0},
                search_index=index,
            )


class ScopedRuntimeTests(unittest.TestCase):
    def test_restores_explicit_caller_after_failure(self):
        from pack_manager import default_settings
        from catalog_retrieval import runtime
        previous = runtime._PACK_SETTINGS
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            caller = default_settings(state_file=home/'caller.json')
            nested = default_settings(state_file=home/'nested.json')
            try:
                runtime.configure_pack_runtime(caller)
                with self.assertRaises(ValueError):
                    with runtime.using_pack_runtime(nested):
                        self.assertIs(runtime._PACK_SETTINGS, nested)
                        raise ValueError('Synthetic bounded operation failure.')
                self.assertIs(runtime._PACK_SETTINGS, caller)
            finally:
                runtime.configure_pack_runtime(previous)


class RetrievalRecordingTests(unittest.TestCase):
    """Lookups append themselves to the retrieval record; the author marks outcomes."""

    def tearDown(self) -> None:
        catalog_cli.clear_runtime_caches()

    def run_cli(self, root: Path, *arguments: str) -> tuple[int, str]:
        state = root / "state.json"
        if not state.exists():
            state.write_text(json.dumps({"pack_roots": [], "enabled_packs": [], "resource_providers": {}}),
                             encoding="utf-8")
        runtime = ["--state-file", str(state), "--cache-dir", str(root / "cache"),
                   "--managed-root", str(root / "managed")]
        stdout = io.StringIO()
        with mock.patch.object(catalog_retrieval.runtime, "load_runtime_catalog",
                               return_value=self.catalog):
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(io.StringIO()):
                try:
                    code = catalog_cli.main([*runtime, *arguments])
                except SystemExit as stopped:
                    code = stopped.code
        return code, stdout.getvalue()

    def test_lookups_are_recorded_and_outcomes_marked(self) -> None:
        import prompt_retrieval
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            CatalogRuntimeTest._install_fixture_catalog(self, root)
            self.catalog = catalog_cli.load_pack_catalog()
            record = root / "lookups.json"
            batch = json.dumps([{"request_id": "pose", "command": "search", "canonical_query": "fixture one",
                                 "kind": ["module"], "categories": ["species"], "limit": 1}])
            steps = [
                ["search", "fixture zero", "--kind", "module", "--record", str(record), "--element", "identity"],
                ["batch", "--input", batch, "--record", str(record)],
                ["inspect-many", "fixture-zero", "fixture-one", "--record", str(record),
                 "--element", "identity", "--element", "pose"],
            ]
            for step in steps:
                self.assertEqual(self.run_cli(root, *step)[0], 0, step)
            value = json.loads(record.read_text(encoding="utf-8"))
            self.assertEqual(value["pack_state"], "fixture-catalog")
            self.assertEqual(value["elements"], [
                {"element": "identity", "queries": ["fixture zero"], "inspected_records": ["fixture-zero"]},
                {"element": "pose", "queries": ["fixture one"], "inspected_records": ["fixture-one"]},
            ])
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(prompt_retrieval.main([str(record), "--element", "identity",
                                                        "--adopted", "fixture-many"]), 1)
                self.assertEqual(prompt_retrieval.main([str(record), "--element", "identity",
                                                        "--adopted", "fixture-zero"]), 0)
                self.assertEqual(prompt_retrieval.main([str(record), "--element", "pose", "--composed",
                                                        "arms folded", "--reason", "No inspected pose fits."]), 0)
            report = prompt_retrieval.validate_prompt_retrieval_record(json.loads(record.read_text(encoding="utf-8")))
            self.assertEqual((report["ok"], report["adopted"], report["composed"]), (True, 1, 1))

    def test_changed_runtime_and_missing_element_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            CatalogRuntimeTest._install_fixture_catalog(self, root)
            self.catalog = catalog_cli.load_pack_catalog()
            record = root / "lookups.json"
            self.assertEqual(self.run_cli(root, "search", "fixture zero", "--record", str(record))[0], 2)
            self.assertFalse(record.exists())
            earlier = {"artifact_type": "prompt-retrieval-record", "pack_state": "earlier-runtime",
                       "elements": [{"element": "identity", "queries": ["fixture"], "inspected_records": []}]}
            record.write_text(json.dumps(earlier), encoding="utf-8")
            code, output = self.run_cli(root, "search", "fixture zero", "--record", str(record),
                                        "--element", "identity")
            self.assertEqual((code, output), (2, ""))
            self.assertEqual(json.loads(record.read_text(encoding="utf-8")), earlier)


class LeftOutPackWarningTests(unittest.TestCase):
    """A pack the catalog leaves out is named in one line by every catalog command."""

    def _pack(self, root: Path, *, broken: bool) -> str:
        from pack_manager import atomic_write_json, initialize_pack, write_lock

        manifest = initialize_pack(root, name=root.name)
        label = f"{root.name} quiet light"
        atomic_write_json(root / "records" / "record.json", {
            "kind": "module", "category": "lighting",
            "records": [{"id": f"{root.name}-record", "label": label, "curation_status": "vocabulary",
                         "category": "lighting", "prompt": f"a controlled {label}", "domains": ["shared"],
                         "tags": [label],
                         "search_terms": [{"phrase": label, "facet": "lighting", "weight": 1.0,
                                           "source": "author"}]}],
        })
        write_lock(root)
        if broken:
            (root / "NOTES.txt").write_text("added after the lock\n", encoding="utf-8")
        return str(manifest["pack_id"])

    def _run(self, folder: Path, enabled: list[str], *command: str) -> subprocess.CompletedProcess[str]:
        from pack_manager import save_state

        save_state(folder / "state.json", {"pack_roots": [str(folder / "packs")],
                                           "enabled_packs": enabled, "resource_providers": {}})
        return subprocess.run(
            [sys.executable, str(Path(catalog_cli.__file__)), "--state-file", str(folder / "state.json"),
             "--cache-dir", str(folder / "cache"), "--managed-root", str(folder / "managed"), *command],
            capture_output=True, text=True, encoding="utf-8", timeout=600,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", **UNPAINTED},
        )

    def test_left_out_pack_is_one_line_and_first_when_nothing_else_is_left(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cpb-left-out-") as temporary:
            folder = Path(temporary).resolve()
            kept = self._pack(folder / "packs" / "kept-shelf", broken=False)
            broken = self._pack(folder / "packs" / "broken-shelf", broken=True)
            warning = (
                "warning: pack broken-shelf is invalid (lock-extra-files: files not in pack.lock.json); "
                "remove the extra files or disable it: python scripts/pack_cli.py "
                f"--state-file {folder / 'state.json'} --cache-dir {folder / 'cache'} "
                f"--managed-root {folder / 'managed'} disable {broken}"
            )
            searched = self._run(folder, [kept, broken], "search", "kept-shelf quiet light")
            self.assertEqual(searched.returncode, 0, searched.stderr)
            self.assertEqual(searched.stderr.splitlines(), [warning])
            self.assertIn("kept-shelf-record", searched.stdout)
            alone = self._run(folder, [broken], "search", "broken-shelf quiet light")
            self.assertNotEqual(alone.returncode, 0)
            self.assertEqual(alone.stderr.splitlines()[0], warning)


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
