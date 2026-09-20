#!/usr/bin/env python3
"""Validate pack-owned prompt-writing-guide resources."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from state_protocol import unsupported_schema_keywords, validate_against_schema


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "prompt-writing-guide.schema.json"


class PromptWritingGuideError(ValueError):
    """Raised when a prompt-writing guide violates its structural contract."""


def _normalize_identity(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def load_schema() -> dict[str, Any]:
    value = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise PromptWritingGuideError("prompt-writing-guide schema must be a JSON object")
    unsupported = unsupported_schema_keywords(value)
    if unsupported:
        raise PromptWritingGuideError(
            "prompt-writing-guide schema contains unsupported keywords: "
            + ", ".join(unsupported)
        )
    return value


def validate_prompt_writing_guide(
    value: Any,
    *,
    path: Path | None = None,
) -> dict[str, Any]:
    label = str(path) if path is not None else "prompt writing guide"
    if not isinstance(value, dict):
        raise PromptWritingGuideError(f"{label} must contain a JSON object")
    errors = validate_against_schema(value, load_schema())
    if errors:
        raise PromptWritingGuideError(
            f"{label} failed schema validation: " + "; ".join(errors)
        )

    section_ids: set[str] = set()
    section_titles: set[str] = set()
    syntax_forms: set[str] = set()
    for section_index, section in enumerate(value["sections"]):
        section_id = str(section["id"])
        title_key = _normalize_identity(str(section["title"]))
        if section_id in section_ids:
            raise PromptWritingGuideError(
                f"{label} contains duplicate section id {section_id!r}"
            )
        if title_key in section_titles:
            raise PromptWritingGuideError(
                f"{label} contains duplicate section title {section['title']!r}"
            )
        section_ids.add(section_id)
        section_titles.add(title_key)

        rule_keys: set[str] = set()
        for rule_index, raw_rule in enumerate(section["rules"]):
            key = _normalize_identity(str(raw_rule))
            if not key:
                raise PromptWritingGuideError(
                    f"{label} sections[{section_index}].rules[{rule_index}] is empty"
                )
            if key in rule_keys:
                raise PromptWritingGuideError(
                    f"{label} section {section_id!r} contains a duplicate rule"
                )
            rule_keys.add(key)

        for example in section.get("examples") or []:
            syntax_key = _normalize_identity(str(example["syntax"]))
            if syntax_key in syntax_forms:
                raise PromptWritingGuideError(
                    f"{label} repeats syntax example {example['syntax']!r}"
                )
            syntax_forms.add(syntax_key)
    return value


def load_prompt_writing_guide(path: Path) -> dict[str, Any]:
    resolved = path.expanduser().resolve(strict=True)
    if resolved.is_symlink() or not resolved.is_file():
        raise PromptWritingGuideError(f"guide must be a regular file: {path}")
    try:
        value = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PromptWritingGuideError(f"cannot read prompt writing guide {path}: {exc}") from exc
    return validate_prompt_writing_guide(value, path=resolved)
