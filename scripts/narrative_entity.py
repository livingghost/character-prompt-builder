#!/usr/bin/env python3
"""Create, rename and remove the files the narrative directory holds.

A naming rule nobody can run is a naming rule, and a series finds a persona,
a place, a faction, a system, an object or a term by its file name. Writing one
by hand means writing the front matter by hand, and a file whose id and name
disagree is found by nothing.

Renaming is the case that has to be a command. An id appears in the file, in the
narrative's persona pointers, in every scene plot that happens at that place, and
in the references other files declare. Renaming by hand means finding all of them.

    python scripts/narrative_entity.py --series <dir> add location kanda-station \\
        --name "Kanda station, east side"
    python scripts/narrative_entity.py --series <dir> add persona c01-school \\
        --character C01 --phase school
    python scripts/narrative_entity.py --series <dir> rename kanda-station kanda-east
    python scripts/narrative_entity.py --series <dir> remove kanda-east
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import quote, unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from narrative_index import ENTITY_ID, FRONT_MATTER, KINDS, scan  # noqa: E402

NL = chr(10)

# The one front matter field that holds ids, the file's own id, and the form's
# own opening. `parse_front_matter` strips each line before reading it and
# strips one layer of quotes off the value, so both of these allow the leading
# space and the quotes it accepts: a line the reader registers and the rename
# cannot see is a reference the rename leaves dangling, or an id that stays on
# the file the rename has already moved.
REFERENCES = re.compile(r"(?m)^([ \t]*references:[ \t]*)(.*)$")
IDENTIFIER = r"(?m)^([ \t]*id:[ \t]*)(['\"]?)%s\2[ \t]*$"
SELF_DESCRIPTION = re.compile(r"\A\s*#[^\n]*\n(?:.*?\n)??---[ \t]*\n", re.DOTALL)

# What each kind of file is asked for, taken from the readme that ships beside
# it. The prompts are headings, not fields: the file is prose and this is a
# starting shape for it.
BODIES = {
    "location": [
        "Identity, scope and design status",
        "Spatial relations, conditions, contents and access",
        "Uses and perspectives, where relevant",
        "Time-scoped changes and dependencies on other world records",
        "Basis, unknowns and unresolved choices",
    ],
    "faction": [
        "Identity, scope and design status",
        "Composition, roles, practices and internal differences",
        "Aims where applicable, external relations and actual constraints",
        "Time-scoped changes and dependencies on other world records",
        "Basis, unknowns and unresolved choices",
    ],
    "system": [
        "Identity, scope and design status",
        "Conditions, operation, effects and persistence",
        "Actual limits, exceptions and costs only where applicable",
        "Material and social implications, and dependencies on other world records",
        "Established conditions versus beliefs; basis and unresolved choices",
    ],
    "artifact": [
        "Identity, scope and design status",
        "Properties, uses, access and actual constraints",
        "Provenance where known and relevant",
        "Time-scoped possession or changes, and dependencies on other world records",
        "Basis, unknowns and unresolved choices",
    ],
    "term": [
        "The definition a reader needs to follow a scene",
        "Who uses it and who does not",
        "What it is not",
        "The chapter it is first heard in",
    ],
}


def front_matter(kind: str, identifier: str, name: str, character: str, phase: str) -> str:
    lines = ["---", f"kind: {kind}", f"id: {identifier}"]
    if name:
        lines.append(f"name: {name}")
    if kind == "persona":
        lines.append(f"character: {character}")
        if phase:
            lines.append(f"phase: {phase}")
    lines.append("references: []")
    lines.append("---")
    return NL.join(lines) + NL




def persona_form() -> str:
    """Read the installed current full form, the sole source for new personas."""
    return (ROOT / "templates/narrative/personas/persona-template.md").read_text(encoding="utf-8")


def form_body(form: str, name: str, phase: str) -> str:
    """The form as one character's file: its own preamble off, its blanks filled.

    The shipped form opens by describing itself, and a persona started from it
    kept that opening, so every character's file was headed with the form's
    title instead of the character's. The instructions that belong to a field
    sit beside that field and travel with it; this drops only the part that is
    about the form.
    """

    head = FRONT_MATTER.match(form)
    body = form[len(head.group(0)):] if head else form
    opening = SELF_DESCRIPTION.search(body)
    if opening:
        body = body[opening.end():]
    body = body.replace("{name}", name).replace("{phase_name}", phase or "{phase_name}")
    return body.lstrip(NL)


def stub(kind: str, identifier: str, name: str, character: str, phase: str) -> str:
    body = [front_matter(kind, identifier, name, character, phase), "",
            f"# {name or identifier}", ""]
    for heading in BODIES[kind]:
        body.append(f"## {heading}")
        body.append("")
        body.append("undecided")
        body.append("")
    return NL.join(body).rstrip() + NL


def persona_document(identifier: str, name: str, character: str, phase: str = "") -> str:
    """Create one phase using the installed full identity-led persona contract."""
    form = persona_form()
    if not form or not form.strip():
        raise ValueError("the full persona form is missing or empty; restore the installed template")
    return (front_matter("persona", identifier, name, character, phase)
            + form_body(form, name or identifier, phase))


def design_document(identifier: str, name: str = "") -> str:
    """Create a current design record including the authorial intent register."""
    source = ROOT / "templates/narrative/design/design-template.md"
    form = source.read_text(encoding="utf-8")
    if not form.strip():
        raise ValueError("the full design form is empty; restore the installed template")
    head = FRONT_MATTER.match(form)
    body = form[len(head.group(0)):] if head else form
    body = re.sub(r"\A\s*# [^\n]*\n", "", body, count=1).lstrip(NL)
    return (front_matter("design", identifier, name or identifier, "", "")
            + f"\n# {name or identifier}\n\n" + body)


def locate(series: Path, identifier: str) -> tuple[str, Path] | None:
    """Where the file carrying an id is, wherever under its kind it sits.

    The whole tree, because the index registers the whole tree. Probing only
    the direct children of each kind's directory meant a file one level down
    was an entity the index listed, the rename said did not exist, the remove
    said did not exist, and `add` wrote a second file for.
    """

    for kind, relative in KINDS.items():
        directory = series / relative
        if not directory.is_dir():
            continue
        # Matched on the stem rather than passed to rglob as a pattern: an id
        # is not always one, and `[a-b]` is a character class to a glob.
        for path in sorted(directory.rglob("*.md")):
            if path.stem == identifier and path.is_file():
                return kind, path
    return None


def rewrite_references(series: Path, old: str, new: str) -> list[str]:
    """Every place that names an id, so a rename reaches all of them.

    Only the one field that holds ids is rewritten. A front matter block also
    carries `kind`, `name` and `phase`, and those hold words: `persona`,
    `location`, `system`, `artifact` and `term` are each a legal id and each a
    value of `kind`, so rewriting the block rewrote what every file of that
    kind said it was, and said ok.
    """

    touched: list[str] = []
    pattern = re.compile(rf"(?<![A-Za-z0-9._:-]){re.escape(old)}(?![A-Za-z0-9._:-])")

    def references_only(head: str) -> str:
        return REFERENCES.sub(lambda found: found.group(1) + pattern.sub(new, found.group(2)), head)

    for relative in KINDS.values():
        directory = series / relative
        if not directory.is_dir():
            continue
        # The whole tree, matching the index, the coverage report and
        # `locate` above. Walking one level meant a rename reported `ok` with
        # every reference in a subdirectory left pointing at the old id.
        for path in sorted(directory.rglob("*.md")):
            text = path.read_text(encoding="utf-8")
            found = FRONT_MATTER.match(text)
            if not found:
                continue
            head = found.group(0)
            replaced = references_only(head)
            if replaced != head:
                path.write_text(replaced + text[len(head):], encoding="utf-8", newline=NL)
                touched.append(str(path.relative_to(series)).replace("\\", "/"))

    narrative = series / "narrative" / "narrative.json"
    if narrative.is_file():
        text = narrative.read_text(encoding="utf-8")
        replaced = text.replace(f"/{old}.md", f"/{new}.md")
        if replaced != text:
            # The same rule the scene plots get below. The approval was a claim
            # about bytes this rewrite has just changed, and leaving it there
            # moves the narrative's own hash under every plot that names it.
            dropped = ""
            try:
                value = json.loads(replaced)
            except json.JSONDecodeError:
                value = None
            if isinstance(value, dict) and "approved" in value:
                value.pop("approved", None)
                replaced = json.dumps(value, ensure_ascii=False, indent=2) + NL
                dropped = " (approval dropped)"
            narrative.write_text(replaced, encoding="utf-8", newline=NL)
            touched.append("narrative/narrative.json" + dropped)

    scenes = series / "narrative" / "scenes"
    if scenes.is_dir():
        # The whole tree again: the index and the coverage report both read
        # every plot under scenes/, and a plot they read and this missed kept
        # an approval of a place that no longer has that name.
        for path in sorted(scenes.rglob("*.json")):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            setting = value.get("setting") if isinstance(value, dict) else None
            if isinstance(setting, dict) and setting.get("location") == old:
                setting["location"] = new
                # The plot's approval covered the old id, and no longer holds.
                value.pop("approved", None)
                path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + NL,
                                encoding="utf-8", newline=NL)
                touched.append(
                    str(path.relative_to(series)).replace("\\", "/") + " (approval dropped)"
                )
    return touched


def rewrite_intent_paths(series: Path, previous: Path, target: Path) -> list[str]:
    """Follow a current entity rename in explicitly authored intent-link fields.

    Only active authorial_intent_refs fields are edited. Quoted/fenced instructions,
    ordinary prose links, remote paths and ID fragments remain untouched. A rename
    changes a file address, not an intent's scope, status or creator approval.
    """
    from authorial_intent_audit import FIELD, ID, LINK
    from persona_expression_audit import visible_lines

    root = series.resolve()
    previous = previous.resolve()
    target = target.resolve()
    touched: list[str] = []
    for path in sorted(root.rglob("*.md")):
        relative = path.relative_to(root)
        if any(part.startswith(".") for part in relative.parts):
            continue
        if any(part.is_symlink() for part in (path, *path.parents)):
            continue
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        visible, _ = visible_lines(text)
        lines = text.splitlines(keepends=True)
        active = False
        changed = False
        for index, line in enumerate(visible):
            match = FIELD.fullmatch(line)
            if match:
                active = match[1] == "authorial_intent_refs"
            elif line.strip() and not line.startswith((" ", "\t")):
                active = False
            if not active or not line.strip():
                continue
            # Match only addresses actually visible in the parsed current field.
            addresses = set(LINK.findall(line))
            def replace(found: re.Match[str]) -> str:
                nonlocal changed
                href = found[1]
                if href not in addresses:
                    return found[0]
                try:
                    url = urlsplit(href)
                    decoded = unquote(url.path)
                    if (not decoded or url.scheme or url.netloc or url.query
                            or decoded.startswith(("/", "\\")) or "\\" in decoded
                            or re.match(r"^[A-Za-z]:", decoded)
                            or not re.fullmatch(rf"intent-({ID})", unquote(url.fragment))):
                        return found[0]
                    resolved = (path.parent / decoded).resolve()
                except (OSError, ValueError, RuntimeError):
                    return found[0]
                if resolved != previous:
                    return found[0]
                address = quote(Path(os.path.relpath(target, path.parent)).as_posix(), safe="/._-")
                replacement = address + "#" + url.fragment
                changed = True
                offset = found.start(1) - found.start(0)
                return found[0][:offset] + replacement + found[0][offset + len(href):]
            lines[index] = LINK.sub(replace, lines[index])
        if changed:
            path.write_text("".join(lines), encoding="utf-8", newline=NL)
            touched.append(relative.as_posix())
    return touched


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split(NL)[0])
    parser.add_argument("--series", type=Path, required=True)
    sub = parser.add_subparsers(dest="action", required=True)

    creator = sub.add_parser("add", help="Create one entity file")
    creator.add_argument("kind", choices=sorted(KINDS))
    creator.add_argument("id")
    creator.add_argument("--name", default="")
    creator.add_argument("--character", default="",
                         help="For a persona: whose life this file describes")
    creator.add_argument("--phase", default="",
                         help="For a persona: which phase of that life")

    renamer = sub.add_parser("rename", help="Rename one entity and every reference to it")
    renamer.add_argument("old")
    renamer.add_argument("new")

    remover = sub.add_parser("remove", help="Remove one entity file")
    remover.add_argument("id")
    remover.add_argument("--force", action="store_true",
                         help="Remove it even though something still names it")

    args = parser.parse_args(argv)
    series = args.series.resolve()
    if not series.is_dir():
        print(json.dumps({"ok": False, "errors": [f"no series at {series}"]}, indent=2))
        return 1

    if args.action == "add":
        if any(char in text for text in (args.name, args.character, args.phase) for char in "\r\n"):
            print(json.dumps({"ok": False, "errors": ["front matter values must be single-line text"]}, indent=2))
            return 1
        if not ENTITY_ID.fullmatch(args.id):
            print(json.dumps({"ok": False, "errors": [
                f"an id is letters, digits and . _ : - starting with a letter or digit, "
                f"got {args.id!r}"]}, ensure_ascii=False, indent=2))
            return 1
        if args.kind == "persona" and not args.character:
            print(json.dumps({"ok": False, "errors": [
                "a persona describes one person: pass --character with the id the narrative "
                "gives them"]}, ensure_ascii=False, indent=2))
            return 1
        if args.kind != "persona" and (args.character or args.phase):
            print(json.dumps({"ok": False, "errors": [
                "--character and --phase belong to a persona"]}, ensure_ascii=False, indent=2))
            return 1
        existing = locate(series, args.id)
        if existing is not None:
            # Forward slashes, like every other path this file reports and like
            # the index report a reader has open beside it. `locate` searching
            # the whole tree is what made this message reachable for a file in
            # a subdirectory, and it was the one path here that still came out
            # in whichever separator the platform happens to use, so the same
            # file was named two ways in one session.
            where = existing[1].relative_to(series).as_posix()
            print(json.dumps({"ok": False, "errors": [
                f"{args.id!r} already exists at {where}"]},
                ensure_ascii=False, indent=2))
            return 1
        path = series / KINDS[args.kind] / f"{args.id}.md"
        try:
            body = (persona_document(args.id, args.name, args.character, args.phase)
                    if args.kind == "persona" else
                    design_document(args.id, args.name) if args.kind == "design" else
                    stub(args.kind, args.id, args.name, args.character, args.phase))
        except (OSError, ValueError) as exc:
            print(json.dumps({"ok": False, "errors": [str(exc)]}, indent=2))
            return 1
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8", newline=NL)
        print(json.dumps({
            "ok": True,
            "written": str(path.relative_to(series)).replace("\\", "/"),
            "next": (
                "point the narrative at it"
                if args.kind == "persona"
                else "record scope and declared dependencies; a design root is not approval"
                if args.kind == "design"
                else "name it from the design, scene, persona or world file that uses it, or "
                     "narrative_index.py will report it as named by nothing"
            ),
        }, ensure_ascii=False, indent=2))
        return 0

    if args.action == "rename":
        found = locate(series, args.old)
        if found is None:
            print(json.dumps({"ok": False, "errors": [f"no entity named {args.old!r}"]},
                             ensure_ascii=False, indent=2))
            return 1
        if not ENTITY_ID.fullmatch(args.new):
            print(json.dumps({"ok": False, "errors": [f"not an id: {args.new!r}"]},
                             ensure_ascii=False, indent=2))
            return 1
        if locate(series, args.new) is not None:
            print(json.dumps({"ok": False, "errors": [f"{args.new!r} already exists"]},
                             ensure_ascii=False, indent=2))
            return 1
        path = found[1]
        text = path.read_text(encoding="utf-8")
        head = FRONT_MATTER.match(text)
        if head:
            # Keep the line as it was written, quotes and indent and all, and
            # change only the id inside it. Matching a bare, unindented value
            # left `id: "kanda-station"` alone on a file now named
            # kanda-east.md, which is a file the index finds by nothing.
            replaced = re.sub(
                IDENTIFIER % re.escape(args.old),
                lambda found: found.group(1) + found.group(2) + args.new + found.group(2),
                head.group(0))
            text = replaced + text[len(head.group(0)):]
        target = path.with_name(f"{args.new}.md")
        path.write_text(text, encoding="utf-8", newline=NL)
        path.rename(target)
        touched = rewrite_references(series, args.old, args.new)
        touched.extend(rewrite_intent_paths(series, path, target))
        touched = list(dict.fromkeys(touched))
        print(json.dumps({
            "ok": True,
            "renamed": f"{path.relative_to(series)} -> {target.relative_to(series)}".replace("\\", "/"),
            "rewritten": touched,
        }, ensure_ascii=False, indent=2))
        return 0

    found = locate(series, args.id)
    if found is None:
        print(json.dumps({"ok": False, "errors": [f"no entity named {args.id!r}"]},
                         ensure_ascii=False, indent=2))
        return 1
    report = scan(series)
    sources = [source for source in report["named"].get(args.id, [])
               if source != "authoring design root"]
    if sources and not args.force:
        print(json.dumps({
            "ok": False,
            "errors": [f"{args.id!r} is named by {', '.join(sources)}; removing it leaves those "
                       "names with nothing behind them"],
            "named_by": sources,
        }, ensure_ascii=False, indent=2))
        return 1
    path = found[1]
    path.unlink()
    print(json.dumps({
        "ok": True,
        "removed": str(path.relative_to(series)).replace("\\", "/"),
        "left_dangling": sources,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
