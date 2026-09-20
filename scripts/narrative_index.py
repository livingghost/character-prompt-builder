#!/usr/bin/env python3
"""Walk the narrative directory and settle what exists against what is named.

A series directory is any directory holding a `narrative/`. It holds one file
per person, place, group, system, object and term, and
prose cannot be asked whether anything points at it. So a file written once and
never referenced again looks the same as one the whole series turns on, and a
name used in three scenes for a place nobody wrote down looks the same as a name
with a file behind it.

Each of those files carries a small front matter block: what kind of thing it
is, the id the rest of the series calls it by, and the ids it names. These
fields carry machine-readable links. The body is authored prose; the index
also locates unfinished form syntax without judging its meaning.

    ---
    kind: location
    id: kanda-station
    name: Kanda station, east side
    references: [C01, folding-umbrella]
    ---

A persona carries two more, because it describes one period of one life and the
narrative says which period is in force:

    character: C01
    phase: school

The check runs both ways. A file nothing names is an orphan, and a name with no
file behind it is dangling; neither is visible from inside a single document.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from narrative import validate_narrative  # noqa: E402
from scene_plot import validate_scene_plot  # noqa: E402

# Where each kind of thing lives. The directory is what the file is, so a file
# in the wrong place is a file whose kind nobody can read off its path.
KINDS = {
    "design": "narrative/design",
    "persona": "narrative/personas",
    "location": "narrative/world/locations",
    "faction": "narrative/world/factions",
    "system": "narrative/world/systems",
    "artifact": "narrative/world/artifacts",
    "term": "narrative/glossary",
}
# An id becomes a file name. A colon is legal in the shared protocol's ids and
# is not legal in a name: on NTFS it opens an alternate data stream, so the
# content goes somewhere nothing lists and the visible file is empty.
ENTITY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
FRONT_MATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)
FRONT_MATTER_KEYS = {"kind", "id", "name", "references", "character", "phase"}
# The one key that holds several ids. Reading every bracketed value as a list
# turned the blank form's `name: [name]` into a one-item list, and a name is a
# name whatever punctuation it happens to start with.
LIST_KEYS = {"references"}
# The suite ships these beside the author's files and they describe nothing.
SHIPPED = {"README.md", "persona-template.md", "design-template.md"}
# The same blanks in the narrative, which is data rather than prose: a whole
# string value the form left behind. `undecided` is never a line of its own
# there, so the line rule above cannot see it.
JSON_BLANKS = ("undecided", "[name]", "[title]")


def parse_front_matter(text: str) -> tuple[dict[str, Any] | None, list[str]]:
    """Read the block a machine reads, and nothing below it.

    This reads the small subset the contract uses rather than all of YAML:
    `key: value` and `key: [a, b]`. A file that needs more than that is a file
    putting structure where the prose belongs.
    """

    errors: list[str] = []
    found = FRONT_MATTER.match(text)
    if not found:
        return None, ["carries no front matter block"]
    value: dict[str, Any] = {}
    for number, line in enumerate(found.group(1).split("\n"), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            errors.append(f"front matter line {number} is not 'key: value': {line!r}")
            continue
        key, _, item = line.partition(":")
        key = key.strip()
        item = item.strip()
        if key in value:
            errors.append(f"front matter repeats {key!r}")
            continue
        if key in LIST_KEYS:
            if item.startswith("[") and item.endswith("]"):
                inside = item[1:-1].strip()
                value[key] = [part.strip().strip("'\"")
                              for part in inside.split(",") if part.strip()]
            elif not item:
                value[key] = []
            else:
                # Kept out of the block rather than stored as written. A string
                # is iterable, so one unbracketed id was read as one id per
                # letter and reported as that many names with nothing behind
                # them, each blaming this file.
                errors.append(
                    f"front matter line {number}: {key!r} is a list, written [a, b] or [], "
                    f"got {item!r}"
                )
        else:
            value[key] = item.strip("'\"")
    return value, errors


def _mask(found: re.Match[str]) -> str:
    """Hide quoted examples without moving diagnostic line numbers."""

    return re.sub(r"[^\n]", " ", found.group(0))


def placeholder_details(text: str) -> list[dict[str, Any]]:
    """Locate unfinished Markdown form syntax, not the quality of its prose.

    Comments never fill a field. Nested fields are containers, not blanks of
    their own. Multiline prose, inline code and fenced answers do fill a field;
    quoted examples do not themselves introduce diagnostics. Custom prose
    formats remain valid and need not imitate the shipped twenty sections.
    """

    visible = re.sub(r"<!--.*?-->", _mask, text, flags=re.DOTALL)
    # Match same-character closing fences of at least the opening length.
    lines = visible.splitlines()
    structure = list(lines)
    fence: str | None = None
    length = 0
    for index, line in enumerate(lines):
        match = re.match(r"^\s*(`{3,}|~{3,})(.*)$", line)
        if fence is not None:
            structure[index] = " " * len(line)
            if (match and match[1][0] == fence and len(match[1]) >= length
                    and not match[2].strip()):
                fence = None
        elif match:
            fence, length = match[1][0], len(match[1])
            structure[index] = " " * len(line)
    prose = re.sub(r"(`+)[^\n]*?\1", _mask, "\n".join(structure))
    findings: list[dict[str, Any]] = []

    def add(line: int, kind: str, label: str) -> None:
        findings.append({"line": line + 1, "kind": kind, "label": label})

    tokens = re.compile(
        r"\[(?:name|title)\](?![(\[:])|\{(?:name|phase_name|this_phase|events|"
        r"One sentence description of this character in this phase|"
        r"person or structural relationship type|quote in the character's language|"
        r"exact form or syntactic sequence|term|explanation|intent_id)\}")
    for index, line in enumerate(prose.splitlines()):
        for match in tokens.finditer(line):
            add(index, "placeholder-token", match[0])
        if re.fullmatch(r"\s*(?:[-*+]\s+)?undecided(?:\s*[:;(-].*)?\s*", line):
            add(index, "undecided", "undecided")
        if re.match(r"^\s*[-*+]\s+\[ \](?:\s|$)", line):
            add(index, "unchecked-item", "unchecked audit item")

    field = re.compile(r"^(\s*)[-*+]\s+\*\*(.+?)\*\*:\s*(.*)$")
    bullet = re.compile(r"^(\s*)[-*+]\s*(.*)$")

    def continuation(index: int, indent: int) -> bool:
        for following in lines[index + 1:]:
            if not following.strip():
                continue
            if re.match(r"^\s*#{1,6}\s|^\s*(?:---+|___+|\*\*\*+)\s*$", following):
                return False
            sibling = bullet.match(following)
            if sibling and len(sibling[1].expandtabs(4)) <= indent:
                return False
            return True
        return False

    for index, line in enumerate(structure):
        match = field.match(line)
        if match:
            if not match[3].strip() and not continuation(index, len(match[1].expandtabs(4))):
                add(index, "empty-field", match[2])
            elif re.fullmatch(r"undecided(?:\s*[:;(-].*)?\s*", match[3]):
                add(index, "undecided", match[2])
        else:
            match = bullet.match(line)
            if (match and not match[2].strip()
                    and not continuation(index, len(match[1].expandtabs(4)))):
                add(index, "empty-item", "empty list item")

    def cells(line: str) -> list[str] | None:
        # A pipe inside a code token or an escaped pipe is not a cell boundary.
        if not line.strip().startswith("|"):
            return None
        safe = re.sub(r"(`+)[^\n]*?\1", lambda m: m[0].replace("|", "\x00"), line.strip())
        return [cell.strip() for cell in re.split(r"(?<!\\)\|", safe)[1:-1]]

    in_table = False
    for index, line in enumerate(structure):
        row = cells(line)
        if row is None:
            in_table = False
            continue
        if row and all(re.fullmatch(r":?-{3,}:?", cell) for cell in row):
            in_table = index > 0 and cells(structure[index - 1]) is not None
            continue
        if in_table:
            empty = [str(column + 1) for column, cell in enumerate(row) if not cell]
            if empty:
                add(index, "empty-table-cells", "empty table cell(s): " + ", ".join(empty))
    return sorted(findings, key=lambda item: (item["line"], item["kind"], item["label"]))


def placeholders(text: str) -> int:
    """How many syntactic drafting gaps remain; not a semantic approval."""

    return len(placeholder_details(text))


def json_placeholders(value: Any, trail: str = "") -> list[str]:
    """Where a JSON document still carries the words initialization wrote.

    The narrative is data, so a blank in it is a whole string value rather
    than a line: `"undecided"` where a statement goes, `"[name]"` where a name
    goes. Nothing read the narrative for them while the readme shipped beside
    it said this is what reports them.
    """

    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            found.extend(json_placeholders(item, f"{trail}.{key}" if trail else str(key)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(json_placeholders(item, f"{trail}[{index}]"))
    elif isinstance(value, str) and value.strip() in JSON_BLANKS:
        found.append(f"{trail} = {value.strip()}")
    return found


def entity_files(series: Path, kind: str) -> list[Path]:
    directory = series / KINDS[kind]
    if not directory.is_dir():
        return []
    # The whole tree, because the coverage report walks the whole tree. Two
    # readers of one directory that disagree about its depth report the same
    # file as present and as missing.
    return sorted(path for path in directory.rglob("*.md") if path.name not in SHIPPED)


def scan(series: Path) -> dict[str, Any]:
    """What the narrative directory holds, and what the series names."""

    errors: list[str] = []
    gaps: list[str] = []
    entities: dict[str, dict[str, Any]] = {}
    unfilled: dict[str, list[dict[str, Any]]] = {}
    # Every reference, as {id: [where it was named]}, so a dangling one can say
    # which document to open.
    named: dict[str, list[str]] = {}

    def name(target: Any, source: str) -> None:
        if isinstance(target, str) and target.strip():
            named.setdefault(target.strip(), []).append(source)

    for kind in KINDS:
        for path in entity_files(series, kind):
            # The path as it is on disk, because the walk reaches the whole
            # tree. Naming the kind's directory and the file's own name instead
            # printed a path no file sits at for anything in a subdirectory,
            # and printed the same one twice when two of them collided.
            where = path.relative_to(series).as_posix()
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                errors.append(f"{where}: could not read the entity: {exc}")
                continue
            details = placeholder_details(text)
            if details:
                unfilled[where] = details
                shown = "; ".join(f"line {item['line']}: {item['label']}" for item in details[:3])
                gaps.append(f"{where}: {len(details)} blank(s) nobody has filled ({shown})")
            value, problems = parse_front_matter(text)
            for message in problems:
                errors.append(f"{where}: {message}")
            if value is None:
                continue
            spare = sorted(set(value) - FRONT_MATTER_KEYS)
            if spare:
                errors.append(f"{where}: front matter has unknown keys: {spare}")
            declared = value.get("kind")
            if declared != kind:
                errors.append(
                    f"{where}: front matter says kind {declared!r} and the file sits where a "
                    f"{kind!r} goes"
                )
            identifier = value.get("id")
            if not isinstance(identifier, str) or not ENTITY_ID.fullmatch(identifier):
                errors.append(f"{where}: front matter id must be an id, got {identifier!r}")
                continue
            if identifier != path.stem:
                errors.append(
                    f"{where}: front matter id is {identifier!r} and the file is named "
                    f"{path.stem!r}; the rest of the series finds this file by its name"
                )
                continue
            if identifier in entities:
                errors.append(
                    f"{where}: id {identifier!r} is already used by {entities[identifier]['file']}"
                )
                continue
            references = value.get("references")
            entities[identifier] = {
                "kind": kind,
                "file": where,
                "name": value.get("name") or "",
                "references": [item for item in (references if isinstance(references, list)
                                                 else []) if isinstance(item, str)],
                "character": value.get("character") or "",
                "phase": value.get("phase") or "",
            }

    for identifier, entity in entities.items():
        # Design notes are declared authoring roots. Being reachable from a
        # proposal is not adoption; prose decision status is not inferred here.
        if entity["kind"] == "design":
            name(identifier, "authoring design root")
        for target in entity["references"]:
            name(target, entity["file"])

    # The narrative names its characters' persona documents and nothing else by id.
    narrative_path = series / "narrative" / "narrative.json"
    characters: dict[str, Any] = {}
    if narrative_path.is_file():
        try:
            document = json.loads(narrative_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"narrative/narrative.json: {exc}")
            document = {}
        # The narrative's own blanks, which the entity walk above cannot reach:
        # it reads markdown, and these are string values in a JSON document.
        # They are the first decisions a series makes and were reported by
        # nothing.
        json_blanks = json_placeholders(document)
        if json_blanks:
            shown = ", ".join(json_blanks[:3])
            rest = f", and {len(json_blanks) - 3} more" if len(json_blanks) > 3 else ""
            gaps.append(
                f"narrative/narrative.json: {len(json_blanks)} blank(s) nobody has filled: "
                f"{shown}{rest}"
            )
        report = validate_narrative(document) if isinstance(document, dict) else {"ok": False}
        if not report.get("ok"):
            # Without this the report blames every character in the file for
            # having no persona, when the cause is that the file is invalid.
            shown = "; ".join(report.get("errors") or []) or "it is not an object"
            errors.append(f"narrative/narrative.json does not answer its contract: {shown}")
        if report.get("ok"):
            characters = {str(entry.get("id")): entry
                          for entry in document.get("characters") or []
                          if isinstance(entry, dict)}
            for character_id, entry in characters.items():
                pointers = [(entry.get("persona"), "")]
                for phase in entry.get("phases") or []:
                    if isinstance(phase, dict):
                        pointers.append((phase.get("persona"), str(phase.get("id") or "")))
                for pointer, phase_id in pointers:
                    if not isinstance(pointer, str) or not pointer.strip():
                        continue
                    path = series / pointer
                    label = f"characters[{character_id}]" + (f".phases[{phase_id}]" if phase_id else "")
                    if not path.is_file():
                        gaps.append(
                            f"narrative/narrative.json: {label} names the persona document "
                            f"{pointer}, which nobody has written"
                        )
                        continue
                    entity = entities.get(path.stem)
                    if entity is None:
                        errors.append(
                            f"narrative/narrative.json: {label} names {pointer}, whose front "
                            "matter did not register it; the reasons are reported against that "
                            "file"
                        )
                        continue
                    if entity["kind"] != "persona":
                        errors.append(
                            f"narrative/narrative.json: {label} names {pointer}, which declares "
                            f"itself a {entity['kind']!r}"
                        )
                        continue
                    named.setdefault(path.stem, []).append(f"narrative/narrative.json {label}")
                    # The pointer and the file have to agree about who and when.
                    if entity["character"] != character_id:
                        errors.append(
                            f"{entity['file']}: front matter says character "
                            f"{entity['character'] or 'nobody'!r} and "
                            f"narrative/narrative.json points at it for {character_id}"
                        )
                    if phase_id and entity["phase"] != phase_id:
                        errors.append(
                            f"{entity['file']}: front matter says phase "
                            f"{entity['phase'] or 'none'!r} and narrative/narrative.json points at "
                            f"it as phase {phase_id!r}"
                        )

    # Every scene plot names the place it happens at.
    scenes = series / "narrative" / "scenes"
    if scenes.is_dir():
        for path in sorted(scenes.rglob("*.json")):
            # As above: the path on disk, so a plot in a subdirectory of
            # scenes/ is one the reader of this report can open.
            where = path.relative_to(series).as_posix()
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                errors.append(f"{where}: {exc}")
                continue
            if not isinstance(value, dict) or value.get("artifact_type") != "scene-plot":
                continue
            report = validate_scene_plot(value)
            name(report["setting"].get("location"), where)
            for character_id in report["characters"]:
                name(character_id, where)

    # Both directions. A name with no file behind it, and a file no name reaches.
    dangling: dict[str, list[str]] = {}
    for target, sources in sorted(named.items()):
        if target in entities or target in characters:
            continue
        dangling[target] = sorted(set(sources))
        errors.append(
            f"{target!r} is named by {', '.join(sorted(set(sources)))} and no file under "
            "narrative/ describes it"
        )
    orphans = sorted(
        identifier for identifier, entity in entities.items()
        if identifier not in named and entity["kind"] != "persona"
    )
    for identifier in orphans:
        gaps.append(
            f"{entities[identifier]['file']}: nothing in the series names {identifier!r}"
        )
    # A persona nothing points at is a phase of a life the narrative dropped.
    for identifier, entity in sorted(entities.items()):
        if entity["kind"] == "persona" and identifier not in named:
            gaps.append(
                f"{entity['file']}: the narrative points at no character or phase for "
                f"{identifier!r}"
            )

    counts = {kind: 0 for kind in KINDS}
    for entity in entities.values():
        counts[entity["kind"]] += 1
    return {
        "ok": not errors,
        "series": str(series),
        "counts": counts,
        "entities": entities,
        "unfilled": unfilled,
        "named": {key: sorted(set(value)) for key, value in sorted(named.items())},
        "dangling": dangling,
        "orphans": orphans,
        "errors": errors,
        "gaps": gaps,
    }


def render(report: dict[str, Any]) -> str:
    out = [
        "  ".join(f"{kind}: {count}" for kind, count in sorted(report["counts"].items())),
        "",
    ]
    for identifier, entity in sorted(report["entities"].items()):
        reached = len(report["named"].get(identifier) or [])
        out.append(f"{entity['kind']:<9} {identifier:<28} named by {reached}")
    for label, key in (("errors", "errors"), ("gaps", "gaps")):
        items = report.get(key) or []
        out.append("")
        out.append(f"{label}: {len(items)}")
        for message in items:
            out.append(f"  {message}")
    return "\n".join(out)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Settle what the narrative directory holds against what the series names.")
    parser.add_argument("series", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true",
                        help="Exit non-zero on any gap, including unfilled forms and orphan files")
    args = parser.parse_args(argv)
    report = scan(args.series.resolve())
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else render(report))
    if not report["ok"]:
        return 1
    return 1 if args.strict and report["gaps"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
