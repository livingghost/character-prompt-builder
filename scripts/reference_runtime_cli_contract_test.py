#!/usr/bin/env python3
"""Focused checks for reference-plan CLI discovery and Visual preflight."""
from __future__ import annotations

import contextlib
import io
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

from reference_plan_cli_contract import (
    compact_json,
    surface_lighting_argument_contract,
    surface_lighting_schema,
)
from reference_runtime import (
    VisualDependencyPreflightError,
    preflight_visual_dependencies,
    visual_dependency_requirement,
)


ROOT = Path(__file__).resolve().parents[1]


def _run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *arguments],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _record(
    checks: list[dict[str, Any]], name: str, passed: bool, detail: Any
) -> None:
    checks.append({"name": name, "passed": bool(passed), "detail": str(detail)})


def run() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    contract = surface_lighting_argument_contract()
    schema = surface_lighting_schema()
    schema_properties = schema["properties"]
    light_required = schema_properties["light_sources"]["items"]["required"]
    material_required = schema_properties["material_responses"]["items"]["required"]
    _record(
        checks,
        "argument-contract-is-derived-from-canonical-schema",
        contract["light_source"]["required_fields"] == light_required
        and contract["material_response"]["required_fields"]
        == material_required,
        contract,
    )

    plan_help = _run("scripts/reference_runtime.py", "plan", "--help")
    compact_light = compact_json(contract["light_source"]["example"])
    compact_material = compact_json(contract["material_response"]["example"])
    _record(
        checks,
        "plan-help-shows-complete-copyable-surface-examples",
        plan_help.returncode == 0
        and all(field in plan_help.stdout for field in light_required + material_required)
        and compact_light in plan_help.stdout
        and compact_material in plan_help.stdout
        and contract["canonical_schema"] in plan_help.stdout,
        plan_help.stdout,
    )

    standalone_help = _run("scripts/build_reference_use_plan.py", "--help")
    plan_options = frozenset(re.findall(r"--[a-z][a-z0-9-]*", plan_help.stdout))
    standalone_options = frozenset(
        re.findall(r"--[a-z][a-z0-9-]*", standalone_help.stdout)
    )
    expected_plan_options = frozenset(
        {
            "--help",
            "--record-use",
            "--transport-mode",
            "--target-model",
            "--source-lighting-mode",
            "--light-source-json",
            "--material-response-json",
            "--unresolved-decision",
            "--max-assets-per-record",
            "--max-references",
            "--technical-role",
            "--out",
            "--state-file",
            "--cache-dir",
            "--managed-root",
            "--pack-root",
        }
    )
    _record(
        checks,
        "standalone-builder-uses-the-complete-plan-argument-contract",
        standalone_help.returncode == 0
        and plan_options == expected_plan_options
        and standalone_options == expected_plan_options
        and compact_light in standalone_help.stdout
        and compact_material in standalone_help.stdout,
        {
            "reference_runtime_plan": sorted(plan_options),
            "standalone_builder": sorted(standalone_options),
        },
    )

    schema_result = _run(
        "scripts/reference_runtime.py", "schema", "surface-lighting-plan"
    )
    _record(
        checks,
        "schema-command-returns-the-canonical-schema",
        schema_result.returncode == 0 and json.loads(schema_result.stdout) == schema,
        schema_result.stderr,
    )

    example_result = _run("scripts/reference_runtime.py", "example", "plan")
    example = json.loads(example_result.stdout) if example_result.returncode == 0 else {}
    _record(
        checks,
        "plan-example-carries-schema-derived-required-fields-and-values",
        example_result.returncode == 0
        and example.get("surface_lighting_arguments") == contract
        and compact_light in example.get("argv", [])
        and compact_material in example.get("argv", [])
        and all(
            option in example.get("argv", [])
            for option in ("--state-file", "--cache-dir", "--managed-root")
        ),
        example,
    )

    svg_item = {"source": {"media_type": "image/svg+xml"}}
    png_item = {"source": {"media_type": "image/png"}}
    prompt_requirement = visual_dependency_requirement(
        {"transport_mode": "prompt-artifacts", "reference_items": [svg_item]}
    )
    bundle_requirement = visual_dependency_requirement(
        {"transport_mode": "svg-bundle", "reference_items": [svg_item]}
    )
    multi_svg_requirement = visual_dependency_requirement(
        {"transport_mode": "multi-image", "reference_items": [svg_item]}
    )
    multi_png_requirement = visual_dependency_requirement(
        {"transport_mode": "multi-image", "reference_items": [png_item]}
    )
    board_requirement = visual_dependency_requirement(
        {"transport_mode": "single-board", "reference_items": [png_item]}
    )
    _record(
        checks,
        "visual-profile-is-gated-by-actual-model-facing-raster-work",
        prompt_requirement["required"] is False
        and bundle_requirement["required"] is False
        and multi_svg_requirement["required"] is True
        and multi_png_requirement["required"] is False
        and board_requirement["required"] is True,
        {
            "prompt": prompt_requirement,
            "svg_bundle": bundle_requirement,
            "multi_svg": multi_svg_requirement,
            "multi_png": multi_png_requirement,
            "single_board": board_requirement,
        },
    )

    failed_dependency_report = {
        "ok": False,
        "profile": "visual",
        "definition": "requirements-visual.txt",
        "python": sys.version.split()[0],
        "dependencies": [],
        "errors": ["CairoSVG is not installed"],
        "check_command": "python scripts/check_dependencies.py --profile visual",
        "install_command": "python -m pip install -r requirements-visual.txt",
        "missing_packages": ["CairoSVG"],
        "incompatible_packages": [],
    }
    with patch("reference_runtime.check_profile", return_value=failed_dependency_report):
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                preflight_visual_dependencies(
                    {"transport_mode": "multi-image", "reference_items": [svg_item]}
                )
            structured_failure = False
            structured_detail: Any = "preflight unexpectedly succeeded"
        except VisualDependencyPreflightError as exc:
            structured_detail = exc.report
            structured_failure = (
                exc.report["check_command"]
                == "python scripts/check_dependencies.py --profile visual"
                and exc.report["install_command"]
                == "python -m pip install -r requirements-visual.txt"
                and exc.report["missing_packages"] == ["CairoSVG"]
            )
    _record(
        checks,
        "failed-visual-preflight-is-structured-and-actionable",
        structured_failure,
        structured_detail,
    )

    failed = [row for row in checks if not row["passed"]]
    return {
        "ok": not failed,
        "summary": {
            "passed": len(checks) - len(failed),
            "failed": len(failed),
            "total": len(checks),
        },
        "checks": checks,
    }


if __name__ == "__main__":
    report = run()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["ok"] else 1)
