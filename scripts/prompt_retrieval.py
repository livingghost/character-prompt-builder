#!/usr/bin/env python3
"""Validate a prompt retrieval record against `schemas/prompt-retrieval-record.schema.json`."""
from __future__ import annotations

import argparse
import hashlib
import re
import json
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "prompt-retrieval-record.schema.json"

ARTIFACT_TYPE = "prompt-retrieval-record"
OUTCOMES = ("adopted", "composed")


def _string_list(value: Any, label: str, errors: list[str], *, required: bool) -> list[str]:
    if value is None:
        if required:
            errors.append(f"{label} is required")
        return []
    if not isinstance(value, list):
        errors.append(f"{label} must be an array")
        return []
    if required and not value:
        errors.append(f"{label} must not be empty")
    items: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{label}[{index}] must be a non-empty string")
            continue
        items.append(item)
    return items


def validate_prompt_retrieval_record(value: Any) -> dict[str, Any]:
    """Return {"ok", "errors", "elements", "adopted", "composed"} for one record."""

    errors: list[str] = []
    adopted = 0
    composed = 0
    element_names: list[str] = []

    if not isinstance(value, dict):
        return {"ok": False, "errors": ["record root must be an object"], "elements": 0, "adopted": 0, "composed": 0}
    if value.get("artifact_type") != ARTIFACT_TYPE:
        errors.append(f"artifact_type must be {ARTIFACT_TYPE!r}, got {value.get('artifact_type')!r}")
    unknown = sorted(set(value) - {"artifact_type", "elements", "pack_state", "settled", "context"})
    if unknown:
        errors.append(f"record has unknown keys: {unknown}")
    if "settled" in value and not isinstance(value["settled"], bool):
        errors.append("settled must be a boolean")
    context = value.get("context")
    if context is not None:
        if not isinstance(context, dict) or set(context) != {"prompt_sha256", "plot_content_sha256"}:
            errors.append("context must bind prompt_sha256 and plot_content_sha256")
        else:
            for key, digest in context.items():
                if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                    errors.append(f"context.{key} must be a SHA-256 digest")
    if value.get("settled") is True and context is None:
        errors.append("a settled retrieval record requires its context")
    pack_state = value.get("pack_state")
    if pack_state is not None and (not isinstance(pack_state, str) or not pack_state.strip()):
        errors.append("pack_state must be a non-empty string when present")

    entries = value.get("elements")
    if not isinstance(entries, list) or not entries:
        errors.append("elements must be a non-empty array")
        entries = []

    for index, entry in enumerate(entries):
        label = f"elements[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{label} must be an object")
            continue
        unknown = sorted(set(entry) - {
            "element", "queries", "inspected_records", "outcome",
            "adopted_record", "composed_wording", "reason",
        })
        if unknown:
            errors.append(f"{label} has unknown keys: {unknown}")

        name = entry.get("element")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{label}.element must be a non-empty string")
        else:
            if name in element_names:
                errors.append(f"{label}.element repeats {name!r}")
            element_names.append(name)

        _string_list(entry.get("queries"), f"{label}.queries", errors, required=True)
        _string_list(entry.get("inspected_records"), f"{label}.inspected_records", errors, required=False)

        outcome = entry.get("outcome")
        if outcome not in OUTCOMES:
            errors.append(f"{label}.outcome must be one of {list(OUTCOMES)}, got {outcome!r}")
            continue
        if outcome == "adopted":
            adopted += 1
            record = entry.get("adopted_record")
            if not isinstance(record, str) or not record.strip():
                errors.append(f"{label}.adopted_record is required when outcome is 'adopted'")
            if record not in (entry.get("inspected_records") or []):
                errors.append(f"{label}.adopted_record must have been inspected")
            for absent in ("composed_wording", "reason"):
                if entry.get(absent) is not None:
                    errors.append(f"{label}.{absent} does not belong to an adopted outcome")
        else:
            composed += 1
            for required_key in ("composed_wording", "reason"):
                item = entry.get(required_key)
                if not isinstance(item, str) or not item.strip():
                    errors.append(f"{label}.{required_key} is required when outcome is 'composed'")
            if entry.get("adopted_record") is not None:
                errors.append(f"{label}.adopted_record does not belong to a composed outcome")

    return {
        "ok": not errors,
        "errors": errors,
        "elements": len(entries),
        "adopted": adopted,
        "composed": composed,
    }


def load_prompt_retrieval_record(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    report = validate_prompt_retrieval_record(value)
    if not report["ok"]:
        raise ValueError(
            f"prompt retrieval record is invalid: {path}: " + "; ".join(report["errors"])
        )
    return report


def retrieval_context(prompt: str, plot: dict[str, Any]) -> dict[str, str]:
    from prompt_plot import content_sha256
    return {
        "prompt_sha256": hashlib.sha256(prompt.strip().encode("utf-8")).hexdigest(),
        "plot_content_sha256": content_sha256(plot),
    }


def settle_retrieval_record(value: Any, *, prompt: str, plot: dict[str, Any]) -> dict[str, Any]:
    """Explicit authoring operation; never called implicitly by generation."""
    report = validate_prompt_retrieval_record(value)
    if not report["ok"]:
        raise ValueError("invalid retrieval record: " + "; ".join(report["errors"]))
    from prompt_plot import validate_prompt_plot
    plot_report = validate_prompt_plot(plot)
    if not plot_report["ok"]:
        raise ValueError("invalid retrieval plot: " + "; ".join(plot_report["errors"]))
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("retrieval needs a non-empty authored prompt")
    result = json.loads(json.dumps(value))
    result["settled"] = True
    result["context"] = retrieval_context(prompt, plot)
    return result


def require_generation_retrieval(value: Any, *, prompt: str, plot: dict[str, Any]) -> dict[str, Any]:
    report = validate_prompt_retrieval_record(value)
    if not report["ok"]:
        raise ValueError("generation requires a valid retrieval record: " + "; ".join(report["errors"]))
    if value.get("settled") is not True:
        raise ValueError("generation requires a settled retrieval record")
    if value.get("context") != retrieval_context(prompt, plot):
        raise ValueError("retrieval record belongs to a different prompt or plot; repeat affected retrieval and settle explicitly")
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record", type=Path)
    parser.add_argument("--settle", action="store_true", help="Explicitly settle decisions for the supplied authored prompt and plot")
    parser.add_argument("--prompt-file", type=Path)
    parser.add_argument("--plot-file", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    try:
        value = json.loads(args.record.read_text(encoding="utf-8"))
        if args.settle:
            if not args.prompt_file or not args.plot_file or not args.out:
                raise ValueError("--settle requires --prompt-file, --plot-file and --out")
            value = settle_retrieval_record(value, prompt=args.prompt_file.read_text(encoding="utf-8"),
                                            plot=json.loads(args.plot_file.read_text(encoding="utf-8")))
            from pack_manager import atomic_write_json
            atomic_write_json(args.out, value)
        elif any((args.prompt_file, args.plot_file, args.out)):
            raise ValueError("binding arguments require --settle")
        report = validate_prompt_retrieval_record(value)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        report = {"ok": False, "errors": [str(exc)], "elements": 0, "adopted": 0, "composed": 0}
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
