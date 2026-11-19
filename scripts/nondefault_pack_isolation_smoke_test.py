#!/usr/bin/env python3
"""Verify that core behavior does not depend on one nondefault pack's contents.

The smoke test deliberately does not inspect any owner-maintained pack. It builds a
temporary core-only tree containing ``packs/commons`` and starts a fresh process
that uses the shipped catalog and a self-contained synthetic upscale input.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any




ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PACK = ROOT / "packs" / "commons"


def load_default_record_ids() -> set[str]:
    ids: set[str] = set()
    for path in sorted(DEFAULT_PACK.glob("records/**/*.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            continue
        for record in value.get("records") or []:
            if isinstance(record, dict) and isinstance(record.get("id"), str):
                ids.add(record["id"])
    return ids


def load_default_model_record_count() -> int:
    count = 0
    for path in sorted(DEFAULT_PACK.glob("records/**/*.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or value.get("kind") != "model":
            continue
        count += sum(1 for record in value.get("records") or [] if isinstance(record, dict))
    return count


def copy_core_only(destination: Path, *, source: Path = ROOT) -> None:
    """Copy the working tree without any nondefault pack or generated catalog."""

    ignored_at_root = {
        ".git",
        ".venv",
        "catalog",
        "dist",
        "packs",
        "FULL-MANIFEST.json",
        "validation-report.json",
        "preset-authoring-audit.json",
        "style-family-audit.json",
        "sparse-discovery-report.json",
    }

    def ignore(directory: str, names: list[str]) -> set[str]:
        base = Path(directory)
        ignored = {name for name in names if name in {"__pycache__", ".pytest_cache", ".mypy_cache"}}
        if base.resolve() == source.resolve():
            ignored.update(name for name in names if name in ignored_at_root)
        return ignored

    shutil.copytree(source, destination, ignore=ignore)
    shutil.copytree(source / "packs" / "commons", destination / "packs" / "commons")


def copy_boundary_probe(root: Path) -> dict[str, bool]:
    """Exercise the copy boundary with a malformed synthetic nondefault pack."""
    source, copied = root / "source", root / "copied"
    content = {
        "scripts/core.py": b"# Synthetic core source.\n",
        "packs/commons/pack.json": b'{}\n',
        "packs/commons/records/kept.json": b'{"synthetic":"shipped"}\n',
        "packs/unselected/pack.json": b"malformed synthetic nondefault manifest\n",
        "packs/unselected/records/broken.json": b"malformed synthetic record\n",
        ".venv/marker": b"synthetic interpreter marker\n",
    }
    for relative, raw in content.items():
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    copy_core_only(copied, source=source)
    return {
        "core_source_copied": (copied / "scripts/core.py").read_bytes() == content["scripts/core.py"],
        "default_pack_copied": all((copied / path).read_bytes() == raw for path, raw in content.items()
                                   if path.startswith("packs/commons/")),
        "unselected_pack_absent": not (copied / "packs/unselected").exists(),
        "environment_absent": not (copied / ".venv").exists(),
        "source_unchanged": all((source / path).read_bytes() == raw for path, raw in content.items()),
    }


def core_runtime_probe(work: Path) -> dict[str, Any]:
    """Use public core operations from the copied installation in a fresh process."""
    import contextlib
    import io
    import catalog_cli
    from catalog_retrieval import runtime
    import pack_cli
    import pack_manager
    from model_contract import validate_model_record
    from upscale_package import build_upscale_package, verify_upscale_package
    from upscale_package_smoke_test import make_image, model_rows

    work.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((DEFAULT_PACK / "pack.json").read_text(encoding="utf-8"))
    commons_id = manifest["pack_id"]
    unselected_id = "019a0290-1234-789a-8123-0123456789ac"
    unselected = work / "unselected-pack"
    unselected.mkdir()
    manifest.update(pack_id=unselected_id, name="Synthetic unselected pack")
    (unselected / "pack.json").write_text(json.dumps(manifest), encoding="utf-8")
    record = unselected / "records/broken.json"
    record.parent.mkdir()
    poisoned_bytes = b"Malformed synthetic content in an unselected pack.\n"
    record.write_bytes(poisoned_bytes)
    settings = pack_manager.default_settings(extra_roots=[unselected], state_file=work / "state.json",
        cache_dir=work / "cache", managed_root=work / "managed")
    pack_manager.save_state(settings.state_file, {"pack_roots": [], "enabled_packs": [commons_id],
        "disabled_packs": [unselected_id], "pack_order": [commons_id]})
    arguments = ["--state-file", str(settings.state_file), "--cache-dir", str(settings.cache_dir),
                 "--managed-root", str(settings.managed_root), "--pack-root", str(unselected)]

    def command(main, *words, structured=True):
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            status = main([*arguments, *words])
        if status != 0:
            raise AssertionError(output.getvalue() + errors.getvalue())
        return json.loads(output.getvalue()) if structured else output.getvalue()

    command(pack_cli.main, "ready", "--only", commons_id, structured=False)
    runtime.configure_pack_runtime(settings)
    try:
        catalog = runtime.load_pack_catalog()
        assert catalog.entries and {entry.source_pack for entry in catalog.entries} == {commons_id}
        models = sorted((entry.record for entry in catalog.entries if entry.kind == "model"), key=lambda row: row["id"])
        assert models
        for model in models:
            assert not validate_model_record(model)
    finally:
        runtime.configure_pack_runtime(None)
    selected = models[0]
    query = selected["search_terms"][0]["phrase"]
    searched = command(catalog_cli.main, "search", query, "--kind", "model", "--limit", str(len(models)))
    assert selected["id"] in {row["id"] for row in searched["results"]}
    assert {row["source_pack"] for row in searched["results"]} == {commons_id}
    inspected = command(catalog_cli.main, "inspect", selected["id"])
    assert inspected["record"] == selected and inspected["source_pack"] == commons_id

    synthetic = model_rows()[0]
    package_root = work / "upscale"
    source, output = package_root / "source.png", package_root / "output.png"
    make_image(source, (2, 2), 40)
    make_image(output, (4, 4), 80)
    package = build_upscale_package(model=synthetic["id"], model_record=synthetic,
        source_image=source, output_image=output, package_root=package_root,
        source_stored_path="source.png", output_stored_path="output.png", scale_factor=2,
        settings={"variant": "general"}, guidance_prompt=None, audit_status="not-required", audit_notes=[])
    assert package["status"] == "ready"
    assert verify_upscale_package(package, package_root=package_root, model_record=synthetic) == package
    assert record.read_bytes() == poisoned_bytes
    return {"ok": True, "installation": str(ROOT), "active_pack_ids": [commons_id],
            "model_count": len(models), "searched_model": selected["id"],
            "inspected_record": inspected["record_id"], "synthetic_upscale_verified": True,
            "unselected_pack_content_unchanged": True}


def run_core_probe(root: Path, work: Path) -> dict[str, Any]:
    program = (
        "import json, sys\nfrom pathlib import Path\n"
        "sys.path.insert(0, str(Path(sys.argv[1]) / 'scripts'))\n"
        "from nondefault_pack_isolation_smoke_test import core_runtime_probe\n"
        "print(json.dumps(core_runtime_probe(Path(sys.argv[2]))))\n"
    )
    process = subprocess.run(
        [sys.executable, "-I", "-B", "-c", program, str(root), str(work)],
        cwd=root,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "CPB_HOME": str(work / "home"),
             "CPB_READS_LEDGER": str(work / "home/reads.jsonl")},
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return {
        "returncode": process.returncode,
        "probe": json.loads(process.stdout) if process.returncode == 0 else None,
        "stdout": process.stdout.strip() if process.returncode != 0 else "",
        "stderr": process.stderr.strip(),
        "passed": process.returncode == 0,
    }


def main() -> int:
    results: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: Any = None) -> None:
        results.append({"name": name, "passed": bool(passed), "detail": detail})

    default_ids = load_default_record_ids()
    check("default pack exists", DEFAULT_PACK.is_dir())
    check("default pack exposes records", bool(default_ids), len(default_ids))

    sys.path.insert(0, str(ROOT / "scripts"))
    from audit_preset_quality import Record, check_global_integrity, check_near_duplicates

    def synthetic(record_id: str, source: str) -> Record:
        return Record(
            "domain-realization",
            "",
            {
                "id": record_id,
                "label": "Synthetic shared label",
                "domains": ["human"],
                "curation_status": "curated",
                "prompt": "a synthetic body of prompt text repeated verbatim in both fixtures",
                "visual_function": "a synthetic body of prompt text repeated verbatim in both fixtures",
            },
            source,
        )

    def collides(left_source: str, right_source: str) -> bool:
        errors: list[str] = []
        check_global_integrity(
            [synthetic("fixture-left", left_source), synthetic("fixture-right", right_source)],
            errors,
            [],
        )
        return any("label collision" in message for message in errors)

    def near_duplicates(left_source: str, right_source: str) -> bool:
        return bool(
            check_near_duplicates(
                [synthetic("fixture-left", left_source), synthetic("fixture-right", right_source)],
                [],
            )
        )

    check("label collision is reported inside one pack", collides("pack:fixture-a", "pack:fixture-a"))
    check(
        "a nondefault pack cannot raise a label collision against the default pack",
        not collides("pack:fixture-a", "pack:fixture-b"),
    )
    check("near-duplicate review is reported inside one pack", near_duplicates("pack:fixture-a", "pack:fixture-a"))
    check(
        "a nondefault pack cannot raise a near-duplicate against the default pack",
        not near_duplicates("pack:fixture-a", "pack:fixture-b"),
    )

    model_test = (ROOT / "scripts/model_contract_smoke_test.py").read_text(encoding="utf-8")
    check(
        "model regression loads only the package-owned default pack",
        'ROOT / "packs/commons"' in model_test and 'ROOT / "packs"' not in model_test,
    )
    check(
        "model regression declares synthetic fixtures",
        "def fixture_models()" in model_test and "fixture-" in model_test,
    )

    upscale_test = (ROOT / "scripts/upscale_package_smoke_test.py").read_text(encoding="utf-8")
    check(
        "upscale regression creates a temporary synthetic pack",
        "tempfile.TemporaryDirectory" in upscale_test
        and 'pack_parent = temp / "packs"' in upscale_test
        and "fixture-creative-upscaler" in upscale_test,
    )

    model_doc = (ROOT / "references/model-prompt-recommendations.md").read_text(encoding="utf-8")
    check(
        "core model recommendation document enumerates exactly the default pack's model records",
        "## Nondefault-pack boundary" in model_doc
        and "synthetic" in model_doc.lower()
        and model_doc.count("| `commons` |") == load_default_model_record_count(),
    )

    inspect_re = re.compile(r"python\s+scripts/catalog_cli\.py\s+inspect\s+([^\s`]+)")
    inspect_violations: list[dict[str, str]] = []
    for path in sorted((ROOT / "references").rglob("*.md")):
        for match in inspect_re.finditer(path.read_text(encoding="utf-8")):
            record_id = match.group(1)
            if "<" in record_id or "{" in record_id:
                continue
            if record_id not in default_ids:
                inspect_violations.append({"path": path.relative_to(ROOT).as_posix(), "id": record_id})
    check(
        "literal core inspection examples resolve in the default pack or use placeholders",
        not inspect_violations,
        inspect_violations,
    )

    frame_template = json.loads((ROOT / "templates/frame-character-template.json").read_text(encoding="utf-8"))
    frame_id = str(frame_template.get("frame_character_id", ""))
    check("frame template uses an example-owned ID", frame_id.startswith("example-"), frame_id)

    upscale_template = json.loads((ROOT / "templates/upscale-package-template.json").read_text(encoding="utf-8"))
    upscaler_id = str(upscale_template.get("upscaler_model", ""))
    check(
        "upscale template requires an explicit active upscaler ID",
        upscaler_id == "replace-with-active-upscaler-id",
        upscaler_id,
    )

    package_full = (ROOT / "scripts/package_full.py").read_text(encoding="utf-8")
    check(
        "full packaging preserves the complete packs tree",
        'output.append("packs")' in package_full,
    )

    package_metadata = (ROOT / "scripts/package_metadata.py").read_text(encoding="utf-8")
    check(
        "minimal core packaging remains limited to the default pack",
        'CORE_PACK_INCLUDES = frozenset({"packs/commons"})' in package_metadata,
    )

    packs_doc = (ROOT / "references/maintenance/packs.md").read_text(encoding="utf-8")
    check(
        "pack documentation distinguishes owner data from core fixtures without excluding it",
        "Every other pack is a personal pack." in packs_doc
        and "without deleting, moving, renaming, or excluding" in packs_doc
        and "full-package construction and catalog export preserve" in packs_doc,
    )

    with tempfile.TemporaryDirectory(prefix="cpb-core-only-") as raw:
        boundary = copy_boundary_probe(Path(raw) / "copy-boundary")
        check("core copy preserves shipped inputs and leaves synthetic nondefault inputs at source",
              all(boundary.values()), boundary)
        isolated = Path(raw) / "character-prompt-builder"
        copy_core_only(isolated)
        nondefault_dirs = sorted(
            path.name for path in (isolated / "packs").iterdir() if path.is_dir() and path.name != "commons"
        )
        check("isolated regression tree contains no nondefault packs", not nondefault_dirs, nondefault_dirs)
        probe = run_core_probe(isolated, Path(raw) / "runtime-probe")
        check(
            "fresh core catalog and synthetic upscale work with only the default pack selected",
            probe["passed"],
            probe,
        )

    passed = sum(1 for row in results if row["passed"])
    report = {
        "ok": passed == len(results),
        "checks": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "scope": "core defaults and regressions are independent of nondefault pack contents; full packaging still preserves the packs tree",
        "results": results,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
