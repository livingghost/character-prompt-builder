#!/usr/bin/env python3
"""Positive retrieval regression for the compact default release pack."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from catalog_cli import (
    configure_pack_runtime,
    inspire,
    load_entries,
    load_pack_catalog,
    recommend,
    search_entries,
)
from package_metadata import CORE_RELEASE_REGRESSION_CONTRACT, load_package_metadata
from pack_manager import PackSettings

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path(CORE_RELEASE_REGRESSION_CONTRACT)


def _record_ids(rows: Any) -> set[str]:
    if not isinstance(rows, list):
        return set()
    return {
        str(row.get("id"))
        for row in rows
        if isinstance(row, dict) and row.get("id")
    }


def evaluate_default_release(root: Path = ROOT) -> dict[str, Any]:
    metadata = load_package_metadata(root)
    fixture_path = root / FIXTURE
    try:
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "fixture": FIXTURE.as_posix(),
            "total_cases": 0,
            "passed": 0,
            "failed": 1,
            "skipped": 0,
            "details": [],
            "errors": [f"default release fixture is unreadable: {exc}"],
        }
    cases = fixture.get("cases") if isinstance(fixture, dict) else None
    if not isinstance(cases, list) or not cases:
        return {
            "ok": False,
            "fixture": FIXTURE.as_posix(),
            "total_cases": 0,
            "passed": 0,
            "failed": 1,
            "skipped": 0,
            "details": [],
            "errors": ["default release fixture must contain at least one case"],
        }

    try:
        entries = load_entries()
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "fixture": FIXTURE.as_posix(),
            "total_cases": len(cases),
            "passed": 0,
            "failed": len(cases),
            "skipped": 0,
            "details": [],
            "errors": [f"default release catalog could not be loaded: {exc}"],
        }

    errors: list[str] = []
    details: list[dict[str, Any]] = []
    active_pack_ids = {entry.source_pack for entry in entries}
    if active_pack_ids != set(metadata.default_pack_ids):
        errors.append(
            "positive release regression must run against exactly the configured default packs: "
            f"expected {sorted(metadata.default_pack_ids)}, got {sorted(active_pack_ids)}"
        )
    active_record_ids = {
        str(entry.record.get("id"))
        for entry in entries
        if entry.record.get("id")
    }
    pack_catalog = load_pack_catalog()

    passed = 0
    for index, case in enumerate(cases):
        case_errors: list[str] = []
        case_id = (
            str(case.get("id") or f"case-{index + 1}")
            if isinstance(case, dict)
            else f"case-{index + 1}"
        )
        operation = str(case.get("operation") or "") if isinstance(case, dict) else ""
        observed: dict[str, Any] = {}
        if not isinstance(case, dict):
            case_errors.append("case must be an object")
        else:
            try:
                if operation == "resource-providers":
                    expected_names = {
                        str(value) for value in case.get("expected_names") or []
                    }
                    observed_providers = {
                        name: resource.source_pack
                        for name, resource in pack_catalog.resources.items()
                    }
                    observed = {"resource_providers": observed_providers}
                    if not expected_names:
                        case_errors.append("resource-providers case has no expected_names")
                    for name in sorted(expected_names):
                        expected_pack = metadata.resource_providers.get(name)
                        if expected_pack is None:
                            case_errors.append(
                                f"default state does not select a provider for {name!r}"
                            )
                        elif observed_providers.get(name) != expected_pack:
                            case_errors.append(
                                f"resource {name!r} resolved from {observed_providers.get(name)!r}, "
                                f"expected {expected_pack!r}"
                            )
                elif operation == "search":
                    expected_ids = {
                        str(value) for value in case.get("expected_ids") or []
                    }
                    rows = search_entries(
                        entries,
                        str(case.get("query") or ""),
                        kinds={"module"},
                        categories={str(case.get("category") or "")},
                        domain=str(case.get("domain") or "") or None,
                        limit=8,
                        diverse=False,
                    )
                    found_ids = _record_ids(rows)
                    observed = {"result_ids": sorted(found_ids)}
                    if not expected_ids:
                        case_errors.append("search case has no expected_ids")
                    missing = sorted(expected_ids - found_ids)
                    if missing:
                        case_errors.append(f"missing expected search IDs: {missing}")
                elif operation == "recommend":
                    result = recommend(
                        entries,
                        str(case.get("query") or ""),
                        str(case.get("domain") or "") or None,
                        int(case.get("directions") or 4),
                    )
                    identity = result.get("identity_modules") or {}
                    direction_cards = result.get("direction_cards") or []
                    observed_identity = (
                        {
                            str(category): sorted(_record_ids(rows))
                            for category, rows in identity.items()
                        }
                        if isinstance(identity, dict)
                        else {}
                    )
                    observed = {
                        "identity_modules": observed_identity,
                        "direction_cards": (
                            len(direction_cards)
                            if isinstance(direction_cards, list)
                            else 0
                        ),
                    }
                    expected_identity = case.get("expected_identity_modules") or {}
                    if not isinstance(expected_identity, dict) or not expected_identity:
                        case_errors.append(
                            "recommend case has no expected_identity_modules"
                        )
                    else:
                        for category, expected_id in expected_identity.items():
                            if str(expected_id) not in set(
                                observed_identity.get(str(category), [])
                            ):
                                case_errors.append(
                                    f"identity module {category!r} is missing {expected_id!r}"
                                )
                    minimum_cards = int(case.get("minimum_direction_cards") or 1)
                    if observed["direction_cards"] < minimum_cards:
                        case_errors.append(
                            f"expected at least {minimum_cards} direction cards, "
                            f"got {observed['direction_cards']}"
                        )
                elif operation == "inspire":
                    categories = [
                        str(value) for value in case.get("categories") or []
                    ]
                    result = inspire(
                        entries,
                        str(case.get("query") or ""),
                        categories,
                        str(case.get("domain") or "") or None,
                        int(case.get("per_category") or 4),
                    )
                    result_categories = result.get("categories") or {}
                    observed_categories = (
                        {
                            str(category): sorted(_record_ids(rows))
                            for category, rows in result_categories.items()
                        }
                        if isinstance(result_categories, dict)
                        else {}
                    )
                    observed = {"category_ids": observed_categories}
                    expected_categories = case.get("expected_category_ids") or {}
                    if not isinstance(expected_categories, dict) or not expected_categories:
                        case_errors.append(
                            "inspire case has no expected_category_ids"
                        )
                    else:
                        for category, expected_id in expected_categories.items():
                            if str(expected_id) not in set(
                                observed_categories.get(str(category), [])
                            ):
                                case_errors.append(
                                    f"inspire category {category!r} is missing "
                                    f"{expected_id!r}"
                                )
                else:
                    case_errors.append(f"unsupported operation: {operation!r}")
            except Exception as exc:  # noqa: BLE001
                case_errors.append(f"operation failed: {exc}")

        referenced_ids: set[str] = set()
        if isinstance(case, dict):
            referenced_ids.update(
                str(value) for value in case.get("expected_ids") or []
            )
            expected_identity = case.get("expected_identity_modules") or {}
            if isinstance(expected_identity, dict):
                referenced_ids.update(
                    str(value) for value in expected_identity.values()
                )
            expected_categories = case.get("expected_category_ids") or {}
            if isinstance(expected_categories, dict):
                referenced_ids.update(
                    str(value) for value in expected_categories.values()
                )
        absent_fixture_ids = sorted(referenced_ids - active_record_ids)
        if absent_fixture_ids:
            case_errors.append(
                "fixture references records outside the active default pack: "
                f"{absent_fixture_ids}"
            )

        case_ok = not case_errors
        if case_ok:
            passed += 1
        details.append(
            {
                "id": case_id,
                "operation": operation,
                "ok": case_ok,
                "observed": observed,
                "errors": case_errors,
            }
        )

    failed = len(cases) - passed
    for detail in details:
        for message in detail["errors"]:
            errors.append(f"{detail['id']}: {message}")
    return {
        "ok": not errors and len(cases) > 0 and failed == 0,
        "fixture": FIXTURE.as_posix(),
        "default_pack_ids": list(metadata.default_pack_ids),
        "total_cases": len(cases),
        "passed": passed,
        "failed": failed,
        "skipped": 0,
        "details": details,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=ROOT)
    parser.add_argument("--state-file", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--managed-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    metadata = load_package_metadata(root)
    managed_root = args.managed_root.resolve()
    configure_pack_runtime(
        PackSettings(
            roots=tuple(
                (root / relative).resolve()
                for relative in metadata.release_pack_dirs
            ),
            state_file=args.state_file.resolve(),
            cache_dir=args.cache_dir.resolve(),
            managed_root=managed_root,
            quarantine_root=(managed_root / ".quarantine").resolve(),
            default_enabled_packs=tuple(metadata.default_pack_ids),
            default_resource_providers=tuple(
                sorted(metadata.resource_providers.items())
            ),
        )
    )
    report = evaluate_default_release(root)
    configure_pack_runtime(None)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
