#!/usr/bin/env python3
"""Self-contained regression checks for prompt-writing-guide validation."""
from __future__ import annotations

import copy
import json
import tempfile
from pathlib import Path
from typing import Any, Callable

from prompt_writing_guide import (
    PromptWritingGuideError,
    load_prompt_writing_guide,
    validate_prompt_writing_guide,
)


def fixture() -> dict[str, Any]:
    return {
        "format": "character-prompt-builder-prompt-writing-guide",
        "name": "Synthetic Prompt Guide",
        "description": "Fictional prompt-writing data used only by the regression test.",
        "sections": [
            {
                "id": "tag-order",
                "title": "Tag order",
                "rules": [
                    "Put the fictional subject token before the fictional finish token."
                ],
            },
            {
                "id": "attention",
                "title": "Attention syntax",
                "rules": [
                    "Use the fictional syntax only when the fictional parser supports it."
                ],
                "examples": [
                    {
                        "syntax": "(fixture:0.25)",
                        "effect": "Explicit 0.25x fixture attention."
                    }
                ],
            },
        ],
    }


def expect_error(fn: Callable[[], Any]) -> bool:
    try:
        fn()
    except PromptWritingGuideError:
        return True
    return False


def main() -> int:
    value = fixture()
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, detail: Any = None) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    add("valid synthetic guide passes validation", validate_prompt_writing_guide(value) is value)

    duplicate_section = copy.deepcopy(value)
    duplicate_section["sections"].append(copy.deepcopy(duplicate_section["sections"][0]))
    add(
        "duplicate section ids are rejected",
        expect_error(lambda: validate_prompt_writing_guide(duplicate_section)),
    )

    duplicate_title = copy.deepcopy(value)
    duplicate_title["sections"][1]["title"] = " TAG   ORDER "
    add(
        "duplicate normalized section titles are rejected",
        expect_error(lambda: validate_prompt_writing_guide(duplicate_title)),
    )

    duplicate_rule = copy.deepcopy(value)
    duplicate_rule["sections"][0]["rules"].append(
        "  PUT THE FICTIONAL SUBJECT TOKEN BEFORE THE FICTIONAL FINISH TOKEN.  "
    )
    add(
        "duplicate normalized rules within a section are rejected",
        expect_error(lambda: validate_prompt_writing_guide(duplicate_rule)),
    )

    duplicate_syntax = copy.deepcopy(value)
    duplicate_syntax["sections"][0]["examples"] = [
        {"syntax": " (FIXTURE:0.25) ", "effect": "Duplicate fictional syntax."}
    ]
    add(
        "duplicate normalized syntax examples are rejected",
        expect_error(lambda: validate_prompt_writing_guide(duplicate_syntax)),
    )

    forbidden_extra = copy.deepcopy(value)
    forbidden_extra["sections"][0]["source_section"] = "not allowed"
    add(
        "undeclared source metadata is rejected by the schema",
        expect_error(lambda: validate_prompt_writing_guide(forbidden_extra)),
    )

    missing_rules = copy.deepcopy(value)
    del missing_rules["sections"][0]["rules"]
    add(
        "sections without executable rules are rejected",
        expect_error(lambda: validate_prompt_writing_guide(missing_rules)),
    )

    with tempfile.TemporaryDirectory(prefix="cpb-prompt-writing-guide-") as temp:
        path = Path(temp) / "guide.json"
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        add(
            "a UTF-8 guide round-trips through the file loader",
            load_prompt_writing_guide(path) == value,
        )

    fields = {
        key
        for section in value["sections"]
        for key in section
    }
    add(
        "the fixture contains no per-section provenance, review, or exclusion fields",
        not bool(fields & {"source", "source_section", "review_state", "blocked", "exclude"}),
        sorted(fields),
    )

    output = {
        "ok": all(row["passed"] for row in checks),
        "checks": len(checks),
        "results": checks,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if output["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
