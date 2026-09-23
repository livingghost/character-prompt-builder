#!/usr/bin/env python3
"""Exercise delivery-geometry resolution, and hold it to a published size table."""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generation_geometry as geometry  # noqa: E402

EXPECTED_CHECKS = 32

# One megapixel with both sides a multiple of 8, the size table published for
# this lineage. Two rows are labelled 4:3 because the table resolves one of them
# from 1.33 and the other from four thirds.
PUBLISHED = {
    "2:3": (832, 1248),
    "3:4": (880, 1176),
    "4:5": (912, 1144),
    "1:1": (1024, 1024),
    "1.33:1": (1176, 888),
    "4:3": (1176, 880),
    "1.43:1": (1224, 856),
    "1.66:1": (1312, 792),
    "16:9": (1360, 768),
    "1.85:1": (1392, 752),
    "2.35:1": (1568, 664),
    "2.39:1": (1576, 656),
    "1.618:1": (1296, 800),
}
SNAPSHOT = "resources/observed-schemas/fixture.svc.json"
# Where the fixture service takes the model identifier, the prompt and the two sides.
KEYS = {"model": ["model"], "prompt": ["prompt"], "width": ["width"], "height": ["height"]}
# A service that takes the size as one text field and refuses any key it does not name.
TEXT_SNAPSHOT = "resources/observed-schemas/fixture.text.json"
TEXT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["prompt"],
    "properties": {
        "prompt": {"type": "string", "minLength": 1},
        "size": {"enum": ["1024x1024", "1024x1536", "1536x1024"]},
    },
}
# A service that takes an aspect ratio in place of a size.
RATIO_SNAPSHOT = "resources/observed-schemas/fixture.ratio.json"
RATIO_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"input": {"type": "object", "additionalProperties": False, "properties": {
        "prompt": {"type": "string"}, "aspect_ratio": {"enum": ["1:1", "2:3", "16:9"]}}}},
}
SCHEMA = {
    "type": "object",
    "properties": {
        "model": {"type": "string", "const": "vendor:fixture@1"},
        "width": {"type": "integer", "minimum": 128, "maximum": 2048},
        "height": {"type": "integer", "minimum": 128, "maximum": 2048},
    },
}
# A service that takes its sizes in buckets: neither side is bounded on its own,
# the pair is, and a request that names no size must name a resolution instead.
BUCKET_SNAPSHOT = "resources/observed-schemas/fixture.buckets.json"
BUCKET_SCHEMA = {
    "type": "object",
    "properties": {
        "model": {"type": "string", "const": "vendor:fixture@1"},
        "width": {"type": "integer"},
        "height": {"type": "integer"},
        "resolution": {"type": "string"},
    },
    "allOf": [
        {
            "if": {"anyOf": [{"required": ["width"]}, {"required": ["height"]}]},
            "then": {
                "required": ["width", "height"],
                "oneOf": [
                    {"properties": {"width": {"const": 1024}, "height": {"const": 1024}}},
                    {"properties": {"width": {"const": 832}, "height": {"const": 1248}}},
                ],
            },
        },
        {"if": {"not": {"required": ["width"]}}, "then": {"required": ["resolution"]}},
    ],
}


def fixture_record(offerings: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "id": "fixture-model",
        "size_hints": {
            "1:1": "1024x1024",
            "2:3": "832x1216",
            "3:2": "1216x832",
            "9:16": "720x1280, 1584x2816",
            "default": "editing follows the first input image when the ratio is omitted",
        },
        "offerings": offerings or [],
    }


def write_snapshot(pack: Path, relative: str, service: str, model_identifier: str, schema: dict[str, Any]) -> None:
    (pack / relative).parent.mkdir(parents=True, exist_ok=True)
    (pack / relative).write_text(json.dumps({
        "artifact_type": "observed-parameter-schema", "model_id": "fixture-model", "service": service,
        "model_identifier": model_identifier, "observed_at": "2026-09-13",
        "source": "the fixture service's model schema endpoint", "unenforced": [], "schema": schema,
    }), encoding="utf-8")


def ratio_offering() -> dict[str, Any]:
    """An offering on a service that takes an aspect ratio inside an input object."""

    return {"service": "ratio", "model_identifier": "vendor/fixture", "observed_at": "2026-09-13",
            "request_keys": {"prompt": ["input.prompt"], "size": ["input.aspect_ratio"]},
            "size_format": "{ratio_width}:{ratio_height}", "constraints": {}, "schema_snapshot": RATIO_SNAPSHOT}


def runtime_pack(folder: Path) -> list[str]:
    """One enabled pack holding one model record, and the selectors that name its runtime."""

    from pack_manager import atomic_write_json, initialize_pack, save_state

    models = json.loads((ROOT / "packs/commons/records/models.json").read_text(encoding="utf-8"))
    record = {**models["records"][0], "id": "fixture-runtime-model", "aliases": ["fixture runtime model"],
              "offerings": [ratio_offering()], "size_hints": {"1:1": "1024x1024", "2:3": "832x1216", "16:9": "1360x768"}}
    manifest = initialize_pack(folder / "packs" / "fixture", name="Geometry Runtime Fixture")
    write_snapshot(folder / "packs" / "fixture", RATIO_SNAPSHOT, "ratio", "vendor/fixture", RATIO_SCHEMA)
    atomic_write_json(folder / "packs" / "fixture" / "records" / "models.json", {"kind": "model", "records": [record]})
    save_state(folder / "state.json", {"pack_roots": [str(folder / "packs")],
                                        "enabled_packs": [manifest["pack_id"]], "resource_providers": {}})
    return ["--state-file", str(folder / "state.json"), "--cache-dir", str(folder / "cache"),
            "--managed-root", str(folder / "managed")]


def main() -> int:
    results: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: Any = None) -> None:
        results.append({"name": name, "passed": bool(passed), "detail": detail})

    sizes = geometry.declared_sizes(fixture_record())
    check("every size a record declares is read, including two under one ratio",
          [(row["declared_under"], row["width"], row["height"]) for row in sizes] ==
          [("1:1", 1024, 1024), ("2:3", 832, 1216), ("3:2", 1216, 832), ("9:16", 720, 1280), ("9:16", 1584, 2816)], sizes)
    check("prose in a size hint contributes no size", all(row["declared_under"] != "default" for row in sizes))
    check("a size is reported at its true ratio", sizes[1]["ratio"] == geometry.simplify(832, 1216) == "13:19")
    check("the pixel budget is the median of the declared sizes, so one outsized entry does not move it",
          geometry.budget_of(sizes) == 832 * 1216, geometry.budget_of(sizes))
    check("an even number of sizes averages the two middle counts",
          geometry.budget_of(sizes[:2]) == (1024 * 1024 + 832 * 1216) // 2)

    table = {ratio: geometry.resolve(float(ratio.split(":")[0]) / float(ratio.split(":")[1]), 1048576, 8)
             for ratio in PUBLISHED}
    check("resolution at one megapixel reproduces the published size table",
          table == PUBLISHED, {k: v for k, v in table.items() if v != PUBLISHED[k]})
    check("both sides are multiples of the step", all(w % 8 == 0 and h % 8 == 0 for w, h in table.values()))
    check("a larger step is honoured", geometry.resolve(1.0, 1048576, 64) == (1024, 1024))
    check("a ratio is read from any of the accepted separators",
          geometry.parse_ratio("2:3") == geometry.parse_ratio(" 2 / 3 ") == 2 / 3)
    for bad in ("2", "2:0", "wide", "-2:3"):
        check(f"a ratio written as {bad!r} is refused", refused(lambda: geometry.parse_ratio(bad)))
    check("a step no side can satisfy is refused",
          refused(lambda: geometry.resolve(1.0, 4096, 512)))

    with tempfile.TemporaryDirectory() as tmp:
        pack = Path(tmp)
        (pack / SNAPSHOT).parent.mkdir(parents=True, exist_ok=True)
        (pack / SNAPSHOT).write_text(json.dumps({
            "artifact_type": "observed-parameter-schema", "model_id": "fixture-model", "service": "svc",
            "model_identifier": "vendor:fixture@1", "observed_at": "2026-09-13",
            "source": "the fixture service's model schema endpoint", "unenforced": [], "schema": SCHEMA,
        }), encoding="utf-8")
        offering = {"service": "svc", "model_identifier": "vendor:fixture@1", "request_keys": KEYS,
                    "constraints": {}, "observed_at": "2026-09-13", "schema_snapshot": SNAPSHOT}
        record = fixture_record([offering])
        refusals, service = geometry.schema_refusals(record, None, "fixture-model", 832, 1216, pack)
        check("a size the observed schema accepts is not refused", refusals == [] and service["service"] == "svc", refusals)
        refusals, _ = geometry.schema_refusals(record, None, "fixture-model", 4096, 64, pack)
        check("a size outside the observed schema is refused on both sides",
              len(refusals) == 2 and any("width 4096" in row for row in refusals) and any("height 64" in row for row in refusals), refusals)
        refusals, service = geometry.schema_refusals(fixture_record(), None, "fixture-model", 4096, 64, pack)
        check("a record exposed on no service is judged by the record alone", refusals == [] and service is None)

        (pack / BUCKET_SNAPSHOT).write_text(json.dumps({
            "artifact_type": "observed-parameter-schema", "model_id": "fixture-model", "service": "buckets",
            "model_identifier": "vendor:fixture@1", "observed_at": "2026-09-13",
            "source": "the fixture service's model schema endpoint", "unenforced": [], "schema": BUCKET_SCHEMA,
        }), encoding="utf-8")
        buckets = fixture_record([{"service": "buckets", "model_identifier": "vendor:fixture@1", "request_keys": KEYS,
                                   "constraints": {}, "observed_at": "2026-09-13", "schema_snapshot": BUCKET_SNAPSHOT}])
        for width, height in ((1024, 1024), (832, 1248)):
            refusals, _ = geometry.schema_refusals(buckets, None, "fixture-model", width, height, pack)
            check(f"a pair the schema carries as a bucket is not refused ({width}x{height})", refusals == [], refusals)
        for width, height in ((832, 1216), (1760, 1408)):
            refusals, _ = geometry.schema_refusals(buckets, None, "fixture-model", width, height, pack)
            check(f"a pair outside every bucket is refused as a pair ({width}x{height})",
                  len(refusals) == 1 and refusals[0].startswith(f"{width}x{height}: "), refusals)

        # Services that name the size differently: one text field, or an aspect ratio.
        write_snapshot(pack, TEXT_SNAPSHOT, "text", "vendor/fixture", TEXT_SCHEMA)
        text_offering = {"service": "text", "model_identifier": "vendor/fixture", "observed_at": "2026-09-13",
                         "request_keys": {"prompt": ["prompt"], "size": ["size"]}, "size_format": "{width}x{height}",
                         "constraints": {}, "schema_snapshot": TEXT_SNAPSHOT}
        text = fixture_record([text_offering])
        refusals, service = geometry.schema_refusals(text, None, "fixture-model", 1024, 1536, pack)
        check("a service that takes the size as one text field accepts a size it lists",
              refusals == [] and service["size_fields"] == {"size": "1024x1536"}, (refusals, service))
        refusals, _ = geometry.schema_refusals(text, None, "fixture-model", 832, 1216, pack)
        check("a size that service does not list is refused on its size field alone",
              len(refusals) == 1 and refusals[0].startswith("size 832x1216: "), refusals)
        write_snapshot(pack, RATIO_SNAPSHOT, "ratio", "vendor/fixture", RATIO_SCHEMA)
        ratios = fixture_record([ratio_offering()])
        refusals, service = geometry.schema_refusals(ratios, None, "fixture-model", 1360, 768, pack, ("16", "9"))
        check("a service that takes an aspect ratio is asked for the ratio named, not the sides reduced",
              refusals == [] and service["size_fields"] == {"input.aspect_ratio": "16:9"}, (refusals, service))
        refusals, _ = geometry.schema_refusals(ratios, None, "fixture-model", 1360, 768, pack)
        check("with no ratio named, the sides in lowest terms are asked for and a ratio the service lacks is refused",
              len(refusals) == 1 and refusals[0].startswith("input.aspect_ratio 85:48: "), refusals)
        keyless = fixture_record([{**offering, "request_keys": {"model": ["model"], "prompt": ["prompt"]}}])
        refusals, service = geometry.schema_refusals(keyless, None, "fixture-model", 4096, 64, pack)
        check("an offering that records no size key leaves the size unchecked",
              refusals == [] and service["size_fields"] is None, (refusals, service))

    # The commons offering on Runware takes the sides on its width and height keys.
    models = json.loads((ROOT / "packs/commons/records/models.json").read_text(encoding="utf-8"))
    offered = next(record for record in models["records"] if record["offerings"])
    refusals, service = geometry.schema_refusals(offered, None, offered["id"], 832, 1248, ROOT / "packs/commons")
    check("the commons offering puts a listed pair on its width and height keys and accepts it",
          refusals == [] and service["size_fields"] == {"width": 832, "height": 1248}, (refusals, service))
    refusals, _ = geometry.schema_refusals(offered, None, offered["id"], 832, 1216, ROOT / "packs/commons")
    check("the commons offering refuses a pair its observed schema does not list",
          len(refusals) == 1 and refusals[0].startswith("832x1216: "), refusals)

    # The runtime selectors go together, as everywhere else, and name the runtime
    # the model record is read from.
    with tempfile.TemporaryDirectory(prefix="cpb-geometry-") as tmp:
        selectors = runtime_pack(Path(tmp))
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            code = geometry.main([*selectors, "--model", "fixture-runtime-model", "--list"])
        listed = json.loads(printed.getvalue()) if code == 0 else {}
        check("the runtime selectors choose the runtime the model record is read from",
              code == 0 and sorted((row["width"], row["height"]) for row in listed.get("declared_sizes", []))
              == [(832, 1216), (1024, 1024), (1360, 768)], printed.getvalue()[-400:])
        with contextlib.redirect_stderr(io.StringIO()):
            check("one runtime selector without the others is refused",
                  refused(lambda: geometry.main([*selectors[:2], "--model", "fixture-runtime-model", "--list"])))
        for arguments, label in ((["--ratio", "16:9"], "a requested ratio"),
                                 (["--width", "1360", "--height", "768"], "a size declared under a ratio")):
            printed = io.StringIO()
            with contextlib.redirect_stdout(printed):
                code = geometry.main([*selectors, "--model", "fixture-runtime-model", *arguments])
            report = json.loads(printed.getvalue())
            check(f"{label} reaches an aspect-ratio service as the ratio the record declares",
                  code == 0 and report["service"]["size_fields"] == {"input.aspect_ratio": "16:9"}, report)

    passed = sum(1 for row in results if row["passed"])
    report = {"ok": len(results) == EXPECTED_CHECKS and passed == len(results), "checks": len(results),
              "expected_checks": EXPECTED_CHECKS, "passed": passed,
              "failures": [row for row in results if not row["passed"]]}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


def refused(call) -> bool:
    try:
        call()
    except SystemExit:
        return True
    return False


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
