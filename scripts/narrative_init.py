#!/usr/bin/env python3
"""Create a persistent authoring workspace without a prescribed story.

A series directory is any directory holding narrative/. Neutral initialization
creates the full project design workspace, entity templates and a narrative
with no declared cast, themes, arcs or chapters. It does not adopt an absence or
claim a finished work. The explicit example seed adds a teaching scaffold;
existing series directories are not overwritten or migrated.

Usage:

    python scripts/narrative_init.py --out <directory> --series-id <id> \
        --title "<title>" [--medium screen|comics|prose|mixed] [--seed neutral|example]

Inspect with narrative.py, narrative_index.py and narrative_coverage.py. Add
world or design entries as useful and full personas when individualized
portrayal matters; none is a requirement to invent characters or a plot.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from narrative import MEDIA, validate_narrative  # noqa: E402
from narrative_entity import design_document, persona_document  # noqa: E402

TEMPLATES = ROOT / "templates" / "narrative"
SERIES_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]+$")
NL = chr(10)

# Which directories a narrative holds. A scene plot lives with the story rather
# than with the pictures of it, because it is what the two have to agree on.
SUBDIRECTORIES = (
    "design",
    "personas",
    "world/locations",
    "world/factions",
    "world/systems",
    "world/artifacts",
    "glossary",
    "scenes",
)

# Templates carrying the series placeholders. Anything else is copied as it is.
RENDERED = {".md", ".json"}


def render(source: Path, title: str, series_id: str, updated_at: str) -> str:
    return (source.read_text(encoding="utf-8")
            .replace("{{SERIES_TITLE}}", title)
            .replace("{{SERIES_ID}}", series_id)
            .replace("{{UPDATED_AT}}", updated_at))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create a series directory holding a narrative and its entity files.")
    parser.add_argument("--out", required=True, help="New series directory")
    parser.add_argument("--series-id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument(
        "--medium", choices=sorted(MEDIA), default="screen",
        help="What the series is made of, which decides what a scene of it becomes: shots, "
             "pages of panels, or passages of prose. Changing it later means editing "
             "narrative/narrative.json.")
    parser.add_argument(
        "--seed", choices=("neutral", "example"), default="neutral",
        help="Neutral starts with no cast, themes, arcs or chapters. Example explicitly "
             "adds one placeholder character and a teaching outline, not creative defaults.")
    args = parser.parse_args(argv)

    if not args.title.strip() or any(char in args.title for char in "\r\n"):
        raise SystemExit("title must be non-empty single-line text")
    if not SERIES_ID.fullmatch(args.series_id):
        raise SystemExit(
            "series-id must be 2 to 64 ASCII letters, digits, dots, underscores, or hyphens")
    if not TEMPLATES.is_dir():
        raise SystemExit(f"the narrative templates are missing: {TEMPLATES}")
    out = Path(args.out).resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"output already exists and is not empty: {out}")

    updated_at = (datetime.now(timezone.utc).replace(microsecond=0)
                  .isoformat().replace("+00:00", "Z"))
    narrative_root = out / "narrative"
    narrative_root.mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    for source in sorted(TEMPLATES.rglob("*")):
        relative = source.relative_to(TEMPLATES)
        target = narrative_root / relative
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix.lower() in RENDERED:
            target.write_text(render(source, args.title, args.series_id, updated_at),
                              encoding="utf-8", newline="\n")
        else:
            target.write_bytes(source.read_bytes())
        written.append(f"narrative/{relative.as_posix()}")

    for name in SUBDIRECTORIES:
        (narrative_root / name).mkdir(parents=True, exist_ok=True)

    # The medium decides what a scene of this series becomes, and a series that
    # starts with the wrong one is refused the first time a scene is planned.
    document = narrative_root / "narrative.json"
    if args.seed == "example":
        seed = ROOT / "templates/narrative-seeds/example.json"
        value = json.loads(render(seed, args.title, args.series_id, updated_at))
    else:
        value = json.loads(document.read_text(encoding="utf-8"))
    value["medium"] = args.medium
    document.write_text(json.dumps(value, ensure_ascii=False, indent=2) + NL,
                        encoding="utf-8", newline="\n")

    design_path = narrative_root / "design/project.md"
    if not design_path.exists():
        design_path.write_text(design_document("project", args.title),
                               encoding="utf-8", newline=NL)
        written.append("narrative/design/project.md")

    # The seed and add-persona use the same full form. Do not ship a second,
    # abbreviated c01 template which silently bypasses persona authoring.
    # Keep any explicitly supplied project seed rather than overwriting it.
    persona_root = (narrative_root / "personas").resolve()
    for character in value.get("characters", []):
        entries = character.get("phases") or [{"persona": character["persona"]}]
        for entry in entries:
            target = (out / entry["persona"]).resolve()
            if not target.is_relative_to(persona_root) or target.suffix != ".md":
                raise SystemExit("a seeded persona must be a Markdown file under narrative/personas")
            if target.is_file():
                continue
            try:
                body = persona_document(target.stem, character.get("name", ""),
                                        character["id"], entry.get("id", ""))
            except (OSError, ValueError) as exc:
                raise SystemExit(str(exc)) from exc
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding="utf-8", newline=NL)
            written.append(target.relative_to(out).as_posix())

    report = validate_narrative(value)
    print(json.dumps({
        "ok": bool(report.get("ok")),
        "series": str(out),
        "series_id": args.series_id,
        "medium": args.medium,
        "seed": args.seed,
        "written": sorted(written),
        "directories": [f"narrative/{name}" for name in SUBDIRECTORIES],
        "errors": report.get("errors", []),
    }, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
