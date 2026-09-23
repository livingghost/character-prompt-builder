#!/usr/bin/env python3
"""Every refusal a reader can make, against the cases that name it.

A reader refuses a document by appending a message. A case defends that refusal
by asserting a fragment of the message. A refusal no case names can be deleted
and every suite stays green, which is the one failure a suite cannot report
about itself. So the sites are read off the reader with the parser, the
fragments are read off the suites with the parser, and a site named by nothing
is an error here.

Both sides are read as source rather than run. On the reader, a site is an
append to one of the refusal lists, and its text is the literal part of what is
appended: an f-string's constant segments, a plain string, the strings joined
by `+`. On a suite, a fragment is any string a case asserts: the value under an
`error`, `notice`, `gap` or `approval_error` key wherever that dict is built,
including inside a generator function, and the left side of any `in` test.

A fragment names a site when one of the site's segments sits inside the
fragment or the fragment sits inside a segment. Segments shorter than a few
words are not compared, because `: ` would name everything. A site whose
segments are all that short is composed from its arguments and cannot be judged
from its own text; it is listed apart rather than counted either way.

    python scripts/refusal_coverage.py scripts/narrative.py scripts/narrative_smoke_test.py
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any

LISTS = ("errors", "approval_errors", "notices", "gaps")
FRAGMENT_KEYS = ("error", "notice", "gap", "approval_error")
SHORTEST = 8


def literal_segments(expression: ast.expr) -> list[str]:
    """The constant text an expression carries, in order, with the rest left out."""

    if isinstance(expression, ast.Constant) and isinstance(expression.value, str):
        return [expression.value]
    if isinstance(expression, ast.JoinedStr):
        parts: list[str] = []
        for value in expression.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
        return parts
    if isinstance(expression, ast.BinOp) and isinstance(expression.op, ast.Add):
        return literal_segments(expression.left) + literal_segments(expression.right)
    if isinstance(expression, ast.Call):
        parts = []
        for argument in expression.args:
            parts.extend(literal_segments(argument))
        return parts
    return []


def sites(reader: Path) -> list[dict[str, Any]]:
    """Each append to a refusal list, with the literal parts of what it appends."""

    found: list[dict[str, Any]] = []
    for node in ast.walk(ast.parse(reader.read_text(encoding="utf-8"))):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "append" and isinstance(node.func.value, ast.Name)
                and node.func.value.id in LISTS and node.args):
            continue
        segments = literal_segments(node.args[0])
        found.append({
            "line": node.lineno,
            "list": node.func.value.id,
            "segments": [segment.strip(" :;,.") for segment in segments
                         if len(segment.strip(" :;,.")) >= SHORTEST],
            "text": "".join(segments),
        })
    return found


def fragments(suite: Path) -> list[str]:
    """Every fragment a suite asserts, read from its source."""

    found: list[str] = []
    for node in ast.walk(ast.parse(suite.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if (isinstance(key, ast.Constant) and key.value in FRAGMENT_KEYS
                        and value is not None):
                    found.extend(literal_segments(value))
        elif isinstance(node, ast.Compare) and any(isinstance(op, ast.In) for op in node.ops):
            found.extend(literal_segments(node.left))
    return [fragment for fragment in found if fragment.strip()]


def named(site: dict[str, Any], asserted: list[str]) -> bool:
    for segment in site["segments"]:
        for fragment in asserted:
            if segment in fragment or fragment in segment:
                return True
    return False


def survey(reader: Path, suites: list[Path]) -> dict[str, Any]:
    asserted: list[str] = []
    for suite in suites:
        asserted.extend(fragments(suite))
    every = sites(reader)
    judged = [site for site in every if site["segments"]]
    return {
        "sites": len(every),
        "unjudged": [site for site in every if not site["segments"]],
        "uncovered": [site for site in judged if not named(site, asserted)],
        "fragments": len(asserted),
    }


def check(root: Path, pairs: list[tuple[str, list[str]]], errors: list[str]) -> None:
    """For a validator: one error per reader that has a refusal nothing names."""

    for reader_relative, suite_relatives in pairs:
        reader = root / reader_relative
        suites = [root / relative for relative in suite_relatives]
        missing = [path for path in [reader, *suites] if not path.is_file()]
        if missing:
            errors.append(f"refusal coverage cannot run: missing {[str(p) for p in missing]}")
            continue
        left = survey(reader, suites)["uncovered"]
        if left:
            shown = ", ".join(f"line {site['line']} {site['text'].strip()[:60]!r}" for site in left[:5])
            more = f" and {len(left) - 5} more" if len(left) > 5 else ""
            errors.append(
                f"{reader_relative}: {len(left)} refusal(s) no case names, so deleting any of them "
                f"leaves every suite green: {shown}{more}"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split(chr(10))[0])
    parser.add_argument("reader", type=Path)
    parser.add_argument("suites", type=Path, nargs="+")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = survey(args.reader, args.suites)
    if args.json:
        print(json.dumps({
            "reader": str(args.reader),
            "sites": report["sites"],
            "fragments": report["fragments"],
            "uncovered": [{"line": s["line"], "list": s["list"], "text": s["text"]}
                          for s in report["uncovered"]],
            "unjudged": [{"line": s["line"], "list": s["list"]} for s in report["unjudged"]],
        }, ensure_ascii=False, indent=2))
    else:
        print(f"{args.reader}: {report['sites']} refusal sites, {len(report['uncovered'])} named by "
              f"no case, {len(report['unjudged'])} composed from arguments and not judged")
        for site in report["uncovered"]:
            print(f"  line {site['line']:4} [{site['list']}] {site['text'].strip()[:110]}")
    return 1 if report["uncovered"] else 0


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
