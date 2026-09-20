#!/usr/bin/env python3
"""Exercise the tag-rendition check against a self-contained vocabulary."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_tag_prompt as checker  # noqa: E402

EXPECTED_CHECKS = 21

DICTIONARY = {
    "format": "character-prompt-builder-prompt-vocabulary",
    "name": "Fixture vocabulary",
    "description": "A self-contained vocabulary for the regression test.",
    "categories": [
        {
            "id": "quality", "name": "Quality", "description": "Finish words.",
            "entries": [{"term": "masterpiece"}, {"term": "best quality"}],
        },
        {
            "id": "shot-types-and-views", "name": "Shots", "description": "One shot at a time.",
            "single_valued": True,
            "entries": [
                {"term": "close-up", "opposes": ["full body"], "aliases": ["closeup"]},
                {"term": "full body"},
                {"term": "Upper Body"},
            ],
        },
        {
            "id": "subject-count-and-groups", "name": "Counts", "description": "How many figures.",
            "multiple_figures_terms": ["2boys", "crowd"],
            "entries": [{"term": "solo"}, {"term": "1boy"}, {"term": "2boys"}, {"term": "crowd"}],
        },
        {
            "id": "colors", "name": "Colours", "description": "Colour words.",
            "entries": [{"term": "grey fur"}, {"term": "yellow eyes"}],
        },
    ],
}


def findings(prompt: str, negative: str = "", record: dict[str, Any] | None = None, vocabulary=None) -> list[dict[str, Any]]:
    return checker.check(prompt, negative, vocabulary, record)


def has(rows: list[dict[str, Any]], name: str) -> bool:
    return any(row["check"] == name for row in rows)


def main() -> int:
    results: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: Any = None) -> None:
        results.append({"name": name, "passed": bool(passed), "detail": detail})

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "dictionary.json"
        path.write_text(json.dumps(DICTIONARY), encoding="utf-8")
        vocabulary = checker.load_vocabulary(path)
        # A tag that is nothing but attention syntax used to strip forever. The
        # regression runs in a child process: in this one a return to the old
        # behaviour would hang the suite itself rather than fail one check.
        try:
            run = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "check_tag_prompt.py"), "--dictionary", str(path),
                 "--prompt", "1girl, (), solo"],
                capture_output=True, text=True, encoding="utf-8", timeout=30, check=False,
            )
            check("a tag that is only attention syntax does not hang the command", True, run.stdout[-300:])
        except subprocess.TimeoutExpired:
            check("a tag that is only attention syntax does not hang the command", False, "no answer within 30 seconds")

    check("an alias resolves to its category", vocabulary["category_of"]["closeup"] == "shot-types-and-views")
    check("an underscore spelling resolves like the spaced one", checker.normalize("grey_fur") == "grey fur")
    check("attention syntax is stripped before a term is looked up",
          checker.bare("(close-up:1.3)") == "close-up" and checker.bare("[grey fur]") == "grey fur")
    check("attention syntax with nothing inside strips to nothing",
          checker.bare("()") == "" and checker.bare("[]") == "" and checker.bare("{}") == ""
          and checker.bare("(())") == "" and checker.bare("( )") == "" and checker.bare("(a:1.2)") == "a")
    rows = findings("1boy, (), solo", "", None, vocabulary)
    check("a tag that carries no term is reported once and read as no term at all",
          len([row for row in rows if row["check"] == "empty tag"]) == 1
          and all(row["severity"] == "problem" for row in rows if row["check"] == "empty tag")
          and not has(rows, "repeated tag") and not has(rows, "not in the vocabulary"), rows)
    check("a chunk break divides the rendition",
          checker.chunks("1boy, solo BREAK sky") == [["1boy", "solo"], ["sky"]], checker.chunks("1boy, solo BREAK sky"))

    clean = findings("masterpiece, best quality, 1boy, solo, grey fur, close-up", "", None, vocabulary)
    check("a sound rendition reports nothing", clean == [], clean)

    rows = findings("masterpiece, (grey fur:1.2, yellow eyes), 1boy, solo", "", None, vocabulary)
    check("a weight that is not against the closing parenthesis is a problem",
          has(rows, "weight binding") and all(row["severity"] == "problem" for row in rows if row["check"] == "weight binding"))
    rows = findings("masterpiece, (grey fur:1.2), 1boy, solo", "", None, vocabulary)
    check("a weight that is against the closing parenthesis is not", not has(rows, "weight binding"), rows)

    rows = findings("1boy, solo, grey fur, grey fur", "", None, vocabulary)
    check("a repeated tag is a problem", has(rows, "repeated tag"))
    rows = findings("1boy, solo, close-up, full body", "", None, vocabulary)
    check("a pair the vocabulary calls opposed is a problem, in either order", has(rows, "opposed pair"), rows)
    check("two terms from a category that describes one at a time is a problem", has(rows, "one at a time"), rows)
    rows = findings("2boys, close-up, full body", "", None, vocabulary)
    check("a declared multiple-figures term excuses a property named twice",
          not has(rows, "one at a time") and has(rows, "opposed pair"), rows)
    rows = findings("solo, close-up, full body", "", None, vocabulary)
    check("without a multiple-figures term the same pair is still a problem",
          has(rows, "one at a time"), rows)
    rows = findings("1boy, solo, 2boys, grey fur", "", None, vocabulary)
    check("a crowd term beside solo is a problem", has(rows, "subject count"), rows)
    rows = findings("2boys, crowd, grey fur", "", None, vocabulary)
    check("two crowd terms are a problem", has(rows, "subject count"), rows)

    rows = findings("1boy, solo, Upper Body", "", None, vocabulary)
    check("a term the vocabulary carries in lower case is a note, not a problem",
          has(rows, "capitals") and all(row["severity"] == "note" for row in rows), rows)
    rows = findings("1boy, solo, a term nobody carries", "", None, vocabulary)
    check("a term outside the vocabulary is a note", has(rows, "not in the vocabulary")
          and all(row["severity"] == "note" for row in rows if row["check"] == "not in the vocabulary"))

    rows = findings("1boy, solo, grey fur", "grey fur, blurry", None, vocabulary)
    check("a term in both the prompt and the negative is a problem", has(rows, "in both"))
    rows = findings("1boy, solo, grey fur", "", {"max_positive_prompt_chars": 10}, vocabulary)
    check("a rendition past the record's declared length is a problem",
          any(row["check"] == "length" and row["severity"] == "problem" for row in rows), rows)

    passed = sum(1 for row in results if row["passed"])
    report = {"ok": len(results) == EXPECTED_CHECKS and passed == len(results), "checks": len(results),
              "expected_checks": EXPECTED_CHECKS, "passed": passed,
              "failures": [row for row in results if not row["passed"]]}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
