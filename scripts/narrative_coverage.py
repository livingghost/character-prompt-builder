#!/usr/bin/env python3
"""Report what a series declares against what its scenes cover.

Every other check in this suite reads one document. A narrative declares five
chapters and three arcs, a directory of scene plots covers some of them, and the
failure nobody notices is the one that leaves no trace in either file: a chapter
with no scene, an arc that no scene advances, a fact the narrative says a
character learned in a chapter where nothing teaches it.

This reads the narrative and every scene plot beside it and reports three
things.

- Contradictions, which are errors: a scene naming a chapter, an arc or a
  character the narrative does not carry, two scenes with the same id, a beat
  teaching someone who is not in the series, a relationship change between
  people the scene does not say are in it.
- Gaps, which are not errors: something declared and not yet covered. A series
  in progress has gaps by definition, and the point of the report is to name
  them rather than to refuse them.
- A table of what each chapter holds, so the shape of the series is readable
  without opening every file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from narrative import (  # noqa: E402
    AUDIENCE,
    content_sha256 as narrative_sha256,
    persona_in_force,
    validate_narrative,
)
from narrative_index import SHIPPED, placeholder_details  # noqa: E402
from scene_plot import validate_scene_plot  # noqa: E402

# Delivery edges are diagnostic vocabulary, not a required dramatic pattern.
# A standalone short is already a complete delivery unit.
EDGE_ROLES = ("chapter_opening", "chapter_closing", "standalone_short")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def scene_paths(directory: Path) -> list[Path]:
    """Every scene plot under the scenes directory, in a stable order."""

    if not directory.is_dir():
        return []
    found = []
    for path in sorted(directory.rglob("*.json")):
        try:
            value = read_json(path)
        except (OSError, json.JSONDecodeError):
            found.append(path)
            continue
        if isinstance(value, dict) and value.get("artifact_type") == "scene-plot":
            found.append(path)
    return found


def cover(narrative_path: Path, scenes_directory: Path,
          series: Path | None = None) -> dict[str, Any]:
    """Compare one narrative against the scene plots that are supposed to cover it.

    `series` is the directory the paths inside those documents resolve from. It
    is what lets the report walk a join out of the narrative: a place named by a
    scene, a scene context named by a scene, a persona named by a character.
    """

    errors: list[str] = []
    gaps: list[str] = []
    report: dict[str, Any] = {
        "ok": False, "narrative": str(narrative_path), "scenes_directory": str(scenes_directory),
        "errors": errors, "gaps": gaps, "notices": [], "chapters": [], "scenes": 0,
    }

    try:
        value = read_json(narrative_path)
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"the narrative could not be read: {narrative_path}: {exc}")
        return report
    narrative_report = validate_narrative(value)
    if not narrative_report["ok"]:
        errors.extend(f"narrative: {message}" for message in narrative_report["errors"])
        return report
    report["notices"] = [f"narrative: {notice}" for notice in narrative_report["notices"]]
    if not narrative_report["approved"]:
        gaps.append(
            "the narrative is not approved, so everything below is measured against a document "
            "nobody has signed off"
        )

    current = narrative_sha256(value)
    themes = {str(entry.get("id")) for entry in value.get("themes") or []
              if isinstance(entry, dict)}
    wanted_realization = narrative_report["realization"]

    numbers: dict[str, int] = narrative_report["chapter_numbers"]
    chapters = {str(entry.get("id")): entry for entry in value.get("chapters") or []
                if isinstance(entry, dict)}
    arcs = {str(entry.get("id")): entry for entry in value.get("arcs") or []
            if isinstance(entry, dict)}
    characters = {str(entry.get("id")): entry for entry in value.get("characters") or []
                  if isinstance(entry, dict)}
    knowers = set(characters) | {AUDIENCE}

    # Read every scene once, and keep only what the comparison needs.
    scenes: list[dict[str, Any]] = []
    seen_ids: dict[str, str] = {}
    for path in scene_paths(scenes_directory):
        relative = path.name
        try:
            plot = read_json(path)
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{relative}: the scene plot could not be read: {exc}")
            continue
        plot_report = validate_scene_plot(plot)
        if not plot_report["ok"]:
            errors.append(
                f"{relative}: the scene plot is invalid, so it covers nothing that can be "
                "counted: " + "; ".join(plot_report["errors"])
            )
            continue
        scene_id = plot_report["scene_id"]
        if scene_id in seen_ids:
            errors.append(
                f"{relative}: scene_id {scene_id!r} is already used by {seen_ids[scene_id]}"
            )
            continue
        seen_ids[scene_id] = relative
        chapter = plot_report["chapter"]
        if chapter not in chapters:
            errors.append(
                f"{relative}: names chapter {chapter!r}, which the narrative does not carry"
            )
            continue
        for arc in plot_report["arcs"]:
            if arc not in arcs:
                errors.append(
                    f"{relative}: names arc {arc!r}, which the narrative does not carry"
                )
        # Invariant: a change to the narrative invalidates what was approved
        # against the version before it. This is the check that makes that true.
        if plot_report["narrative_sha256"] != current:
            errors.append(
                f"{relative}: was written against narrative {plot_report['narrative_sha256'][:12]} "
                f"and the narrative is now {current[:12]}; approve it against what it now says"
            )
        for theme in plot_report["themes"]:
            if theme not in themes:
                errors.append(
                    f"{relative}: carries theme {theme!r}, which the narrative does not carry"
                )
        if wanted_realization and plot_report["realization"] != wanted_realization:
            errors.append(
                f"{relative}: breaks into {plot_report['realization']!r} and the series is "
                f"{narrative_report['medium']!r}, which breaks into {wanted_realization!r}"
            )

        taught: dict[str, list[str]] = {}
        for beat in plot.get("beats") or []:
            if not isinstance(beat, dict):
                continue
            for who in beat.get("teaches") or []:
                if who not in knowers:
                    errors.append(
                        f"{relative}: beat {beat.get('id')!r} teaches {who!r}, who is neither a "
                        "character in the narrative nor the audience"
                    )
                    continue
                taught.setdefault(str(who), []).append(str(beat.get("beat") or ""))
        present: set[str] = set()
        for who in plot_report["characters"]:
            if who not in characters:
                errors.append(
                    f"{relative}: names character {who!r}, which the narrative does not carry"
                )
            else:
                present.add(who)
        scenes.append({
            "file": relative,
            "scene_id": scene_id,
            "order": plot_report["order"],
            "themes": list(plot_report["themes"]),
            "focalization": plot_report["focalization"].get("kind", ""),
            "setting": plot_report["setting"],
            "chapter": chapter,
            "arcs": list(plot_report["arcs"]),
            "scene_function": plot.get("scene_function"),
            "delivery_role": plot.get("delivery_role"),
            "shots": plot_report["shots"],
            "approved": plot_report["approved"],
            "teaches": taught,
            "characters": sorted(present),
            "state_changes": plot_report["state_changes"],
        })
    report["scenes"] = len(scenes)

    # A place named by a scene and by no file is a place whose facts live in
    # whichever scene was written first.
    if series is not None:
        places = series / "narrative" / "world" / "locations"
        # Markdown only, and the whole tree, which is what the entity index
        # reads. A place the two readers disagree about is a place reported as
        # present by one and missing by the other.
        # Kept as {id: the file it is in}, so the gap below can name a file
        # that exists. Printing the directory and the id spelled a path that
        # nothing sits at for any place written in a subdirectory.
        known = ({path.stem: path.relative_to(series).as_posix()
                  for path in sorted(places.rglob("*.md")) if path.name not in SHIPPED}
                 if places.is_dir() else {})
        for scene in scenes:
            location = scene["setting"].get("location")
            if location and location not in known:
                gaps.append(
                    f"{scene['file']}: happens at {location!r}, and no file under "
                    "narrative/world/locations describes it"
                )
            context = scene["setting"].get("scene_context")
            if context and not (series / context).is_file():
                errors.append(
                    f"{scene['file']}: names the scene context {context}, which does not exist"
                )
        for location, where in sorted(known.items()):
            if not any(item["setting"].get("location") == location for item in scenes):
                gaps.append(f"{where}: no scene happens there")

    # A chapter the narrative declares and no scene covers. This is the whole
    # reason the report exists: the chapter list and the scenes directory are two
    # independent statements about the same series, and no single-document check
    # can compare them.
    by_chapter: dict[str, list[dict[str, Any]]] = {key: [] for key in chapters}
    for scene in scenes:
        by_chapter[scene["chapter"]].append(scene)

    # Read each selected persona once. A valid pointer string is not a written
    # or complete persona; fingerprints are review evidence, not approvals.
    persona_files: dict[str, dict[str, Any]] = {}

    def persona_file(pointer: str) -> dict[str, Any]:
        if pointer in persona_files:
            return persona_files[pointer]
        status: dict[str, Any] = {"file_sha256": None, "unfilled_count": None}
        persona_files[pointer] = status
        path = series / pointer
        if not path.is_file():
            gaps.append(f"persona {pointer}: the selected persona file is missing")
            return status
        try:
            data = path.read_bytes()
            details = placeholder_details(data.decode("utf-8"))
        except (OSError, UnicodeError) as exc:
            errors.append(f"persona {pointer}: could not read the selected persona: {exc}")
            return status
        status.update(file_sha256=hashlib.sha256(data).hexdigest(), unfilled_count=len(details))
        if details:
            gaps.append(f"persona {pointer}: {len(details)} blank(s) nobody has filled; "
                        "run narrative_index.py for line-numbered findings")
        return status

    for chapter_id, chapter in sorted(chapters.items(), key=lambda item: numbers.get(item[0], 0)):
        held = by_chapter.get(chapter_id) or []
        functions = sorted({str(scene["scene_function"]) for scene in held})
        roles = sorted({str(scene["delivery_role"]) for scene in held})
        phases: dict[str, Any] = {}
        for character_id, character in characters.items():
            phase_id, document = persona_in_force(character, numbers.get(chapter_id, 0), numbers)
            phases[character_id] = {"phase": phase_id, "persona": document}
            if series is not None and document is not None:
                phases[character_id].update(persona_file(document))
            if document is None:
                gaps.append(
                    f"chapter {chapter_id}: {character_id} has no persona document in force here; "
                    "every declared phase begins later"
                )
        report["chapters"].append({
            "id": chapter_id,
            "number": numbers.get(chapter_id),
            "story_order": [chapter.get("story_order_start"), chapter.get("story_order_end")],
            "focalization": sorted({scene["focalization"] for scene in held
                                    if scene["focalization"]}),
            "places": sorted({str(scene["setting"].get("location")) for scene in held
                              if scene["setting"].get("location")}),
            "title": chapter.get("title"),
            "status": chapter.get("status"),
            "arcs": list(chapter.get("arcs") or []),
            "scenes": [scene["scene_id"] for scene in held],
            "shots": sum(scene["shots"] for scene in held),
            "scene_functions": functions,
            "delivery_roles": roles,
            "unapproved_scenes": [scene["scene_id"] for scene in held if not scene["approved"]],
            "personas": phases,
        })
        if not held:
            gaps.append(
                f"chapter {chapter_id} ({chapter.get('status')}) is declared and no scene covers it"
            )
            continue
        if not any(role in EDGE_ROLES for role in roles):
            gaps.append(
                f"chapter {chapter_id} has {len(held)} scene(s) and none of them opens or closes it"
            )
    # A chapter's scenes come in an order, and the order is a run from 1.
    for chapter_id, held in sorted(by_chapter.items()):
        orders = sorted(scene["order"] for scene in held)
        if not orders:
            continue
        if len(orders) != len(set(orders)):
            errors.append(
                f"chapter {chapter_id} has two scenes claiming the same place in it: {orders}"
            )
        elif orders != list(range(1, len(orders) + 1)):
            errors.append(
                f"chapter {chapter_id} orders its scenes {orders}, which is not a run from 1"
            )

    # A theme declared at the top and carried by no scene is the failure this
    # whole layer exists to catch.
    carried: set[str] = set()
    for scene in scenes:
        carried.update(scene["themes"])
    for theme in sorted(themes):
        if theme not in carried and scenes:
            gaps.append(f"theme {theme} is declared and no scene carries it")

    # An arc the narrative declares and no scene advances.
    advanced: dict[str, int] = {}
    for scene in scenes:
        for arc in scene["arcs"]:
            advanced[arc] = advanced.get(arc, 0) + 1
    for arc_id, arc in arcs.items():
        if arc_id not in advanced:
            gaps.append(
                f"arc {arc_id} ({arc.get('status')}) is declared and no scene advances it"
            )

    # The narrative says a fact was learned in a chapter. A scene in that chapter
    # has to be where it is learned, or the chapter order rests on nothing.
    for index, entry in enumerate(value.get("knowledge") or []):
        if not isinstance(entry, dict):
            continue
        learned = entry.get("learned_in")
        if learned is None:
            gaps.append(
                f"knowledge[{index}] names no chapter it was learned in, so nothing can cover it"
            )
            continue
        held = by_chapter.get(str(learned)) or []
        if not held:
            continue
        for who in entry.get("known_by") or []:
            if not any(str(who) in scene["teaches"] for scene in held):
                gaps.append(
                    f"knowledge[{index}] says {who} learns this in chapter {learned}, and no "
                    f"beat in that chapter's {len(held)} scene(s) teaches {who}"
                )

    # A character the series declares and no scene uses, and a character in a
    # scene outside the chapters they are in the series for.
    used: set[str] = set()
    for scene in scenes:
        used.update(scene["characters"])
    spans: dict[str, list[Any]] = narrative_report["character_spans"]
    for character_id, character in characters.items():
        if character_id not in used and scenes:
            gaps.append(
                f"character {character_id} ({character.get('name')}) appears in no scene"
            )
        first, last = (spans.get(character_id) or [None, None])[:2]
        for scene in scenes:
            if character_id not in scene["characters"]:
                continue
            at = numbers.get(scene["chapter"])
            if at is None:
                continue
            if first in numbers and at < numbers[first]:
                errors.append(
                    f"{scene['file']}: {character_id} is in this scene, in chapter {at}, and "
                    f"first appears in chapter {numbers[first]}"
                )
            if last in numbers and at > numbers[last]:
                errors.append(
                    f"{scene['file']}: {character_id} is in this scene, in chapter {at}, and "
                    f"was written out in chapter {numbers[last]}"
                )

    # A promise or a question the narrative opened and the chapters ran past.
    for index, promise in enumerate(value.get("promises") or []):
        if isinstance(promise, dict) and promise.get("status") == "planned":
            gaps.append(f"promises[{index}] is planned and not yet planted in any chapter")
    last = max(numbers.values()) if numbers else 0
    for index, question in enumerate(value.get("questions") or []):
        if not isinstance(question, dict) or question.get("status") != "open":
            continue
        introduced = question.get("introduced")
        if introduced in numbers and numbers[introduced] < last:
            gaps.append(
                f"questions[{index}] was introduced in chapter {numbers[introduced]} and is "
                f"still open at chapter {last}"
            )

    report["ok"] = not errors
    return report


def render(report: dict[str, Any]) -> str:
    """The same report as lines, for reading rather than for a machine."""

    out: list[str] = []
    out.append(f"scenes: {report['scenes']}   chapters: {len(report['chapters'])}")
    out.append("")
    header = (f"{'ch':<6} {'#':>2} {'story order':<13} {'status':<12} {'scenes':>6} "
              f"{'shots':>5}  places")
    out.append(header)
    out.append("-" * len(header))
    for chapter in report["chapters"]:
        first, last = chapter["story_order"]
        span = f"{first} to {last}" if first is not None else "-"
        places = ",".join(chapter["places"]) or "-"
        out.append(
            f"{chapter['id']:<6} {chapter['number'] or '':>2} {span:<13} "
            f"{str(chapter['status']):<12} {len(chapter['scenes']):>6} {chapter['shots']:>5}  "
            f"{places}"
        )
        functions = ",".join(chapter["scene_functions"]) or "-"
        roles = ",".join(chapter["delivery_roles"]) or "-"
        out.append(f"{'':<6} {'':>2} {'':<13} {'':<12} {'':>6} {'':>5}  {functions} / {roles}")
    for label, key in (("errors", "errors"), ("gaps", "gaps"), ("notices", "notices")):
        items = report.get(key) or []
        out.append("")
        out.append(f"{label}: {len(items)}")
        for message in items:
            out.append(f"  {message}")
    return "\n".join(out)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Report what a series declares against what its scenes cover.")
    parser.add_argument("series", type=Path, help="The series directory, or the narrative itself")
    parser.add_argument("--scenes", type=Path, default=None,
                        help="Where the scene plots are, when they are not in narrative/scenes")
    parser.add_argument("--json", action="store_true", help="Print the report as JSON")
    parser.add_argument("--strict", action="store_true",
                        help="Exit non-zero when anything is declared and not covered")
    args = parser.parse_args(argv)

    if args.series.is_dir():
        narrative_path = args.series / "narrative" / "narrative.json"
        scenes = args.scenes or (args.series / "narrative" / "scenes")
    else:
        narrative_path = args.series
        scenes = args.scenes or (narrative_path.parent / "scenes")

    # A series directory is the one holding `narrative/`, so a narrative inside
    # one sits two levels down from it. A narrative named anywhere else is still
    # a narrative and simply has no series to walk out of. The path is made
    # absolute and not resolved: a bare file name has to become one before it
    # has a parent to read, and following a link through `narrative/` to
    # wherever it really stores its files answered the store's name instead,
    # which left this whole report with no series and every location check
    # silently skipped.
    absolute = narrative_path.absolute()
    if args.series.is_dir():
        series = args.series
    elif absolute.parent.name == "narrative":
        series = absolute.parent.parent
    else:
        series = None
    report = cover(narrative_path, scenes, series=series)
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else render(report))
    if not report["ok"]:
        return 1
    return 1 if args.strict and report["gaps"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
