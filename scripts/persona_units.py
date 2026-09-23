#!/usr/bin/env python3
"""Divide a Markdown definition into anchored units, each with a content hash.

A unit is one of:

- a field, `- **name**:` at the left margin, with everything nested under it;
- the text under a heading, before its first field or subheading;
- the front matter block.

Its anchor is the heading path and, for a field, the field name, joined by
` > `, such as `13. RELATIONSHIPS > Important People` or
`7. SPEECH > Speech Patterns > first_person`. A document with one level-1
heading treats it as the title, and paths start below it. Template comments are
instructions, not content: the text and the hash leave them out, so a comment
that changes changes no unit. A second hash leaves out the unit's own heading
line or field label, so a renamed heading or field can be matched with what it
was.

An anchor written shorter than the full path names the one unit or heading whose
path ends with it. A heading anchor covers every unit below the heading.

    python scripts/persona_units.py narrative/personas/c01.md
    python scripts/persona_units.py narrative/personas/c01.md --anchor "Speech Patterns"
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

SEPARATOR = " > "
FRONT_MATTER = "front matter"
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
FIELD = re.compile(r"^[-*+]\s+\*\*(.+?)\*\*:")
FENCE = re.compile(r"^\s*(`{3,}|~{3,})(.*)$")
RULE = re.compile(r"^\s*(?:-{3,}|_{3,}|\*{3,})\s*$")
COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
# What initialization writes where an answer goes, as the narrative index reads it.
BLANK_WORDS = re.compile(r"\[(?:name|title)\]|\{[A-Za-z_' ]+\}|\bundecided\b")


def _masked(text: str) -> str:
    """The text with each comment emptied, every line kept where it was."""
    return COMMENT.sub(lambda found: re.sub(r"[^\n]", " ", found.group(0)), text)


def _normalized(lines: list[str]) -> str:
    """A unit's text as it is hashed: comment-only lines dropped, blank runs collapsed."""
    kept: list[str] = []
    for original, visible in lines:
        line = visible.rstrip()
        if not line and original.strip():
            continue
        if not line and (not kept or not kept[-1]):
            continue
        kept.append(line)
    while kept and not kept[-1]:
        kept.pop()
    return "\n".join(kept)


def _body(text: str, kind: str) -> str:
    """A unit's text without its own heading line or field label, which a rename changes."""
    lines = text.split("\n")
    if kind == "heading" and lines and HEADING.match(lines[0]):
        lines = lines[1:]
    elif kind == "field" and lines:
        lines[0] = FIELD.sub("", lines[0], count=1).strip()
    return "\n".join(lines).strip("\n")


def _blank(text: str, kind: str) -> bool:
    """Whether a unit carries no answer: only its label, table rules and initialization words."""
    body = text.split("\n")
    if kind == "heading" and body and HEADING.match(body[0]):
        body = body[1:]
    elif kind == "field" and body:
        body[0] = FIELD.sub("", body[0], count=1)
    prose = [line for line in body if not line.lstrip().startswith("|")]
    rest = BLANK_WORDS.sub("", "\n".join(prose))
    rest = re.sub(r"^\s*[-*+]\s+\*\*.+?\*\*:", "", rest, flags=re.M)
    if re.search(r"\w", rest):
        return False
    # A table is answered when one data row answers every column. The header,
    # the rule under it and the defaults a form ships in a row are not answers.
    def rule(row: list[str]) -> bool:
        return all(re.fullmatch(r":?-{3,}:?", cell) for cell in row)

    rows = [[cell.strip() for cell in line.strip().strip("|").split("|")]
            for line in body if line.lstrip().startswith("|")]
    if len(rows) > 1 and rule(rows[1]):
        rows = rows[2:]
    return not any(all(re.search(r"\w", BLANK_WORDS.sub("", cell)) for cell in row)
                   for row in rows if not rule(row))


def units(text: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Every unit of a Markdown document in order, and the anchors that repeat."""
    text = text.replace("\r\n", "\n")
    raw_lines = text.split("\n")
    visible_lines = _masked(text).split("\n")
    found: list[dict[str, Any]] = []
    start = 0
    if raw_lines and raw_lines[0].strip() == "---":
        for index in range(1, len(raw_lines)):
            if raw_lines[index].strip() == "---":
                body = list(zip(raw_lines[:index + 1], visible_lines[:index + 1]))
                found.append({"anchor": FRONT_MATTER, "path": [FRONT_MATTER], "kind": "front-matter",
                              "line": 1, "text": _normalized(body)})
                start = index + 1
                break

    fence: str | None = None
    headings: list[tuple[int, int, str]] = []
    for index in range(start, len(raw_lines)):
        match = FENCE.match(visible_lines[index])
        if fence is not None:
            if match and match[1][0] == fence and not match[2].strip():
                fence = None
            continue
        if match:
            fence = match[1][0]
            continue
        heading = HEADING.match(visible_lines[index])
        if heading:
            headings.append((index, len(heading[1]), heading[2].strip()))
    title = [h for h in headings if h[1] == 1]
    title_line = title[0][0] if len(title) == 1 else None

    stack: list[tuple[int, str]] = []
    current: dict[str, Any] | None = None
    lines: list[tuple[str, str]] = []

    def close() -> None:
        if current is not None:
            current["text"] = _normalized(lines)
            found.append(current)

    heading_at = {index: (level, name) for index, level, name in headings}
    fence = None
    for index in range(start, len(raw_lines)):
        original, visible = raw_lines[index], visible_lines[index]
        match = FENCE.match(visible)
        in_fence = fence is not None
        if in_fence:
            if match and match[1][0] == fence and not match[2].strip():
                fence = None
        elif match:
            fence = match[1][0]
        if not in_fence and index in heading_at:
            close()
            level, name = heading_at[index]
            if index == title_line:
                current = {"anchor": name, "path": [name], "kind": "heading", "line": index + 1}
            else:
                while stack and stack[-1][0] >= level:
                    stack.pop()
                stack.append((level, name))
                path = [item[1] for item in stack]
                current = {"anchor": SEPARATOR.join(path), "path": path, "kind": "heading", "line": index + 1}
            lines = [(original, visible)]
            continue
        # A line that opens or closes a fence, or sits inside one, is content.
        structural = not in_fence and fence is None
        field = FIELD.match(visible) if structural else None
        if field:
            close()
            path = [item[1] for item in stack] + [field[1].strip()]
            current = {"anchor": SEPARATOR.join(path), "path": path, "kind": "field", "line": index + 1}
            lines = [(original, visible)]
            continue
        if structural and RULE.match(visible):
            continue
        if current is None:
            if not visible.strip():
                continue
            current = {"anchor": "preamble", "path": ["preamble"], "kind": "heading", "line": index + 1}
            lines = []
        lines.append((original, visible))
    close()

    counts: dict[str, int] = {}
    for unit in found:
        unit["sha256"] = hashlib.sha256(unit["text"].encode("utf-8")).hexdigest()
        unit["body_sha256"] = hashlib.sha256(_body(unit["text"], unit["kind"]).encode("utf-8")).hexdigest()
        unit["blank"] = _blank(unit["text"], unit["kind"])
        counts[unit["anchor"]] = counts.get(unit["anchor"], 0) + 1
    repeated = sorted(anchor for anchor, count in counts.items() if count > 1)
    return found, [f"anchor {anchor!r} names {counts[anchor]} units; give each heading a distinct name"
                   for anchor in repeated]


def resolve(found: list[dict[str, Any]], anchor: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """The unit an anchor names, and every unit it covers.

    The anchor names the one unit whose path ends with it. A heading covers its
    own text and every unit below it.
    """
    wanted = [part.strip() for part in anchor.split(">") if part.strip()]
    if not wanted:
        raise ValueError("an anchor names at least one heading or field")
    matches = [unit for unit in found if unit["path"][-len(wanted):] == wanted]
    if not matches:
        raise ValueError(f"no heading or field is named {anchor!r}")
    if len(matches) > 1:
        raise ValueError(f"{anchor!r} names {len(matches)} places; write more of the path: "
                         + "; ".join(unit["anchor"] for unit in matches[:4]))
    target = matches[0]
    if target["kind"] != "heading" or target["path"] == ["preamble"]:
        return target, [target]
    depth = len(target["path"])
    covered = [unit for unit in found if unit["kind"] != "front-matter"
               and unit["path"][:depth] == target["path"] and unit["line"] >= target["line"]]
    return target, covered


def text_of(covered: list[dict[str, Any]]) -> str:
    """The definition text a set of covered units carries, in document order."""
    return "\n\n".join(unit["text"] for unit in covered if unit["text"])


def index(text: str) -> dict[str, str]:
    """Each anchor with its content hash, the record a reading keeps."""
    found, _ = units(text)
    return {unit["anchor"]: unit["sha256"] for unit in found}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("file", type=Path, help="A Markdown definition, such as a persona")
    parser.add_argument("--anchor", help="Print the text this anchor names and the units it covers")
    args = parser.parse_args(argv)
    try:
        found, repeated = units(args.file.read_text(encoding="utf-8"))
        if args.anchor:
            target, covered = resolve(found, args.anchor)
            report = {"ok": not repeated, "errors": repeated, "anchor": target["anchor"],
                      "covers": [unit["anchor"] for unit in covered],
                      "blank": [unit["anchor"] for unit in covered if unit["blank"]],
                      "text": text_of(covered)}
        else:
            report = {"ok": not repeated, "errors": repeated, "file": str(args.file),
                      "units": len(found), "filled": sum(not unit["blank"] for unit in found),
                      "anchors": [("blank   " if unit["blank"] else "filled  ") + unit["anchor"]
                                  for unit in found]}
    except (OSError, UnicodeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
