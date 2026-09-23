#!/usr/bin/env python3
"""Verify that core behavior does not depend on one nondefault pack's contents.

The smoke test deliberately does not inspect any owner-maintained pack. It builds a
temporary core-only tree containing ``packs/commons`` and proves that the relevant
regressions remain self-contained there.
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
SELECTED_SMOKES = (
    "scripts/model_contract_smoke_test.py",
    "scripts/upscale_package_smoke_test.py",
    "scripts/search_discovery_smoke_test.py",
    "scripts/catalog_cli_runtime_smoke_test.py",
)


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


def copy_core_only(destination: Path) -> None:
    """Copy the working tree without any nondefault pack or generated catalog."""

    ignored_at_root = {
        ".git",
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
        if base.resolve() == ROOT.resolve():
            ignored.update(name for name in names if name in ignored_at_root)
        return ignored

    shutil.copytree(ROOT, destination, ignore=ignore)
    shutil.copytree(DEFAULT_PACK, destination / "packs" / "commons")


def run_smoke(root: Path, relative_script: str) -> dict[str, Any]:
    process = subprocess.run(
        [sys.executable, relative_script],
        cwd=root,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return {
        "script": relative_script,
        "returncode": process.returncode,
        "stdout": process.stdout.strip(),
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

    packs_doc = (ROOT / "PACKS.md").read_text(encoding="utf-8")
    check(
        "pack documentation distinguishes owner data from core fixtures without excluding it",
        "Personal packs" in packs_doc
        and "without deleting, moving, renaming, or excluding" in packs_doc
        and "full-package construction and catalog export may preserve" in packs_doc,
    )

    with tempfile.TemporaryDirectory(prefix="cpb-core-only-") as raw:
        isolated = Path(raw) / "character-prompt-builder"
        copy_core_only(isolated)
        nondefault_dirs = sorted(
            path.name for path in (isolated / "packs").iterdir() if path.is_dir() and path.name != "commons"
        )
        check("isolated regression tree contains no nondefault packs", not nondefault_dirs, nondefault_dirs)
        smoke_rows = [run_smoke(isolated, script) for script in SELECTED_SMOKES]
        check(
            "selected core regressions pass with only the default pack present",
            all(row["passed"] for row in smoke_rows),
            smoke_rows,
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
    raise SystemExit(main())
