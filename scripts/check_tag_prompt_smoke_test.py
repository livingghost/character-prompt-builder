#!/usr/bin/env python3
"""Check grammar and vocabulary evidence, without grading depiction consistency."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


import prompt_weighting as weighting
import check_tag_prompt as checker  # noqa: E402
from prompt_dialect import load_dialects  # noqa: E402

COMMONS = ROOT / "packs" / "commons" / "resources"

DIALECTS = {
    "format": "character-prompt-builder-prompt-dialects",
    "name": "Fixture dialects",
    "description": "Two fixture families for the regression test.",
    "dialects": [
        {
            "id": "family-a", "name": "Family A", "description": "The first fixture family.",
            "tag_separator": "a comma followed by one space", "block_order": ["quality", "subject"],
            "quality_terms": ["masterpiece"], "rating_terms": ["general", "explicit"],
            "period_terms": ["newest", "old"],
        },
        {
            "id": "family-b", "name": "Family B", "description": "The second fixture family.",
            "tag_separator": "a comma followed by one space", "block_order": ["quality", "subject"],
        },
    ],
}

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
                {"term": "close-up", "opposes": ["full body"], "aliases": ["closeup"],
                 "description": "A close view of the selected subject.",
                 "usage_notes": ["Resolve the subject and crop from the authored scene."]},
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
    return checker.check(prompt, negative, vocabulary, record, syntax="sdEmbeds")


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
                 "--weighting", "sdEmbeds", "--prompt", "1girl, (), solo"],
                capture_output=True, text=True, encoding="utf-8", timeout=30, check=False,
            )
            check("a tag that is only attention syntax does not hang the command", True, run.stdout[-300:])
        except subprocess.TimeoutExpired:
            check("a tag that is only attention syntax does not hang the command", False, "no answer within 30 seconds")
        overlapping = {**DICTIONARY, "categories": [*DICTIONARY["categories"], {
            "id": "alternate-meaning", "name": "Alternate meaning", "description": "Another authored context.",
            "entries": [{"term": "closeup", "description": "A second dictionary meaning."}],
        }]}
        path.write_text(json.dumps(overlapping), encoding="utf-8")
        meanings = checker.inspect("closeup", "", checker.load_vocabulary(path), None)["meanings"]
        check("ambiguous dictionary matches preserve every definition for review",
              [row["term"] for row in meanings] == ["close-up", "closeup"]
              and meanings[1]["description"] == "A second dictionary meaning.", meanings)

    check("an alias resolves to its category", vocabulary["meanings"]["closeup"][0]["category"] == "shot-types-and-views")
    check("an underscore spelling resolves like the spaced one", checker.normalize("grey_fur") == "grey fur")
    parsed = weighting.parse('(close-up:1.3), [grey fur]', 'sdEmbeds')
    check("selected attention syntax yields the dictionary terms",
          [row['text'] for row in parsed['clauses'][0]['tags']] == ['close-up', 'grey fur'])
    errors = [weighting.inspect_pair(value, '', 'sdEmbeds')['findings'] for value in ['()', '[]', '(())', '( )']]
    check("empty weighted groups report a bounded syntax error", all(len(rows) == 1 and rows[0]['check'] == 'empty tag' for rows in errors))
    rows = findings("1boy, (), solo", "", None, vocabulary)
    check("a tag that carries no term is reported once and read as no term at all",
          len([row for row in rows if row["check"] == "empty tag"]) == 1
          and all(row["severity"] == "problem" for row in rows if row["check"] == "empty tag")
          and not has(rows, "repeated tag") and not has(rows, "not in the vocabulary"), rows)
    parsed = weighting.parse('1boy, solo BREAK sky', 'sdEmbeds')['clauses'][0]['tags']
    check("an sdEmbeds chunk break is retained independently from comma delimiters",
          [(row['text'],row['chunk']) for row in parsed] == [('1boy',0),('solo',0),('sky',1)])

    clean = findings("masterpiece, best quality, 1boy, solo, grey fur, close-up", "", None, vocabulary)
    check("a sound rendition reports nothing", clean == [], clean)

    rows = findings("masterpiece, (grey fur:1.2, yellow eyes), 1boy, solo", "", None, vocabulary)
    check("a weight that is not against the closing parenthesis is a problem",
          has(rows, "weight binding") and all(row["severity"] == "problem" for row in rows if row["check"] == "weight binding"))
    rows = findings("masterpiece, (grey fur:1.2), 1boy, solo", "", None, vocabulary)
    check("a weight that is against the closing parenthesis is not", not has(rows, "weight binding"), rows)

    for text in ("1boy, solo, grey fur, grey fur", "1boy, solo, close-up, full body",
                 "2boys, close-up, full body", "1boy, solo, 2boys, grey fur",
                 "2boys, crowd, grey fur", "1boy, solo, Upper Body"):
        rows = findings(text, "", None, vocabulary)
        check("valid syntax leaves scene meaning to the author: " + text, rows == [], rows)

    report = checker.inspect("closeup, full body", "", vocabulary, None)
    evidence = next(row for row in report["meanings"] if row["authored_term"] == "closeup")
    check("alias lookup retains complete entry and category guidance",
          evidence["term"] == "close-up" and evidence["opposes"] == ["full body"]
          and evidence["aliases"] == ["closeup"]
          and evidence["category_definition"]["single_valued"] is True
          and evidence["usage_notes"] == ["Resolve the subject and crop from the authored scene."], evidence)
    report = checker.inspect("1boy, a term nobody carries", "", vocabulary, None)
    check("dictionary coverage is evidence alongside valid grammar",
          report["findings"] == [] and report["unmatched_terms"] == [
              {"channel": "positive", "clause": 0, "term": "a term nobody carries"}], report)

    rows = findings("1boy, solo, grey fur", "grey fur, blurry", None, vocabulary)
    check("both valid channels retain their terms for author review", rows == [], rows)
    long_negative = ", ".join(f"excluded feature {index}" for index in range(64))
    report = checker.inspect("grey fur", long_negative, vocabulary, None)
    check("negative scope has no undeclared term quota",
          report["findings"] == []
          and len(report["channels"]["negative"]["clauses"][0]["tags"]) == 64, report["findings"])
    rows = findings("1boy, solo, grey fur", "", {"max_positive_prompt_chars": 10}, vocabulary)
    check("a rendition past the record's declared length is a problem",
          any(row["check"] == "length" and row["severity"] == "problem" for row in rows), rows)
    rows = findings("grey fur", "unwanted label", {"max_negative_prompt_chars": 5}, vocabulary)
    check("the declared negative character limit is enforced", has(rows, "length"), rows)
    rows = findings("grey fur", "unwanted label", {"supports_negative_prompt": False}, vocabulary)
    check("an unsupported negative channel is reported", has(rows, "negative transport"), rows)

    with tempfile.TemporaryDirectory() as tmp:
        dictionary = Path(tmp) / "dictionary.json"
        dictionary.write_text(json.dumps(DICTIONARY), encoding="utf-8")
        dialect_file = Path(tmp) / "dialects.json"
        dialect_file.write_text(json.dumps(DIALECTS), encoding="utf-8")

        def run(*extra: str) -> subprocess.CompletedProcess:
            return subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "check_tag_prompt.py"), "--dictionary", str(dictionary),
                 "--dialects", str(dialect_file), *extra],
                capture_output=True, text=True, encoding="utf-8", timeout=60, check=False,
            )

        named = run("--prompt", "general, explicit, 1boy", "--dialect", "family-a")
        report = json.loads(named.stdout or "{}")
        check("--dialect returns the complete family guidance beside grammar results",
              named.returncode == 0 and report.get("dialect") == "family-a"
              and report.get("dialect_guidance") == DIALECTS["dialects"][0]
              and report.get("findings") == [], named.stdout[-400:] + named.stderr[-400:])
        unnamed = run("--prompt", "general, explicit, 1boy")
        check("without a family the output names none and runs no family check",
              unnamed.returncode == 0 and json.loads(unnamed.stdout).get("dialect") is None, unnamed.stdout[-300:])
        unknown = run("--prompt", "1boy", "--dialect", "family-c")
        check("an unknown family id is answered with the ids the resource carries",
              unknown.returncode != 0 and "unknown dialect 'family-c'; the prompt-dialects resource carries: "
              "family-a, family-b" in unknown.stderr, unknown.stderr[-300:])
        family = load_dialects(dialect_file)["family-a"]

    report = checker.inspect("1boy, old man, grey fur", "", vocabulary, None, family)
    check("complete tag text is retained beside family evidence",
          report["findings"] == [] and report["dialect_guidance"] == family
          and report["channels"]["positive"]["clauses"][0]["tags"][1]["text"] == "old man", report)

    commons_vocabulary = checker.load_vocabulary(COMMONS / "prompt-vocabulary" / "dictionary.json")
    commons_dialects = load_dialects(COMMONS / "prompt-dialects" / "dialects.json")
    rows = checker.check("masterpiece, best quality, newest, 1boy, solo, old man, grey hair", "", commons_vocabulary,
                         None, commons_dialects["illustrious-noobai"])
    check("the commons family guidance leaves multiword meaning to the author", rows == [], rows)
    missing = {family_id: sorted(term for field in ("rating_terms", "period_terms", "quality_terms")
                                 for term in row.get(field) or []
                                 if checker.normalize(term) not in commons_vocabulary["meanings"])
               for family_id, row in commons_dialects.items()}
    check("every rating, period, and quality term of a commons family is carried by the commons vocabulary",
          not any(missing.values()), missing)
    rows = checker.check("masterpiece, newest, year 2025, 1girl, solo", "", commons_vocabulary, None,
                         commons_dialects["anima"])
    check("on the commons Anima family a year term sits beside the period term",
          not has(rows, "period term"), rows)

    passed = sum(1 for row in results if row["passed"])
    report = {"ok": passed == len(results), "checks": len(results), "passed": passed,
              "failures": [row for row in results if not row["passed"]]}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
