#!/usr/bin/env python3
"""Validate declared narrative intent and its typed references.

The shared document records whichever concerns, agents, organizing threads,
chapters, promises, questions and knowledge the author has declared. Its root
arrays may be empty; declared references must still resolve. It does not select
cast size, genre, theme, dramatic structure or the creative project's entry
point. World rules, design decisions and detailed personas remain in their
owning documents rather than being inferred from these tables.

A promise tracks an intended audience setup, a question an open inquiry, and a
knowledge entry who learned a fact and when. They are optional authored links,
not obligations for every work. Chapter order connects this declaration to
scene plots and, when used, a state timeline. Structural validity and approval
hashes do not establish semantic coherence, completed writing or user adoption.
"""
from __future__ import annotations

# The contract this reader answers, over the document with the block that
# publishes this file's own hash removed. Without that cut the two would
# each feed the other and neither could be computed.
CONTRACT_SHA256 = "cbdc3ce7f2977b9ef09df5695cb21dba7d82d4e22cb83062c8c7fc458eaf1dad"

import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Sequence

ARTIFACT_TYPE = "narrative"
APPROVED_AT = re.compile(
    r"^[0-9]{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])"
    r"T(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](?:\.[0-9]+)?Z$"
)
SHA256 = re.compile(r"^[a-f0-9]{64}$")

ARC_STATUS = ("planned", "in-progress", "resolved")
CHAPTER_STATUS = ("planned", "in-progress", "complete")
PROMISE_STATUS = ("planned", "planted", "paid-off", "dropped")
QUESTION_STATUS = ("open", "answered", "resolved", "dropped")
PROHIBITION_KINDS = ("surface", "judgement")
AUDIENCE = "audience"

# A promise planted this many chapters ago with no payoff is reported. It is not
# an error: a series may hold one deliberately. It is reported because the
# failure it catches is the one nobody notices, an unfired setup.
UNFIRED_GAP = 3

ROOT_KEYS = {
    "artifact_type", "series_id", "timeline_id", "medium", "approved", "themes",
    "arcs", "acts", "chapters", "characters", "relationships", "promises",
    "questions", "knowledge",
}

# What the series is made of, and what a scene of it becomes. A project whose
# scenes break into shots is not a novel, and nothing else would notice.
MEDIA = {
    "prose": "passages",
    "comics": "pages",
    "screen": "shots",
    "mixed": "",
}
# What a relationship is, before any scene moves it. The shared protocol carries
# the measured state at a story order; this is the authorial claim the state is
# a reading of.

# The shared protocol's id shape, so the narrative names the same timeline the
# events, snapshots and scene contexts are ordered on.
TIMELINE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")


def content_sha256(value: dict[str, Any]) -> str:
    """The hash of everything the approval is about, which is the document without it."""

    body = {key: item for key, item in value.items() if key != "approved"}
    canonical = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _listed(value: Any) -> list[Any]:
    """The entries of a field that is supposed to be a list, and none otherwise.

    A document is untrusted input. Where a list belongs and something else
    arrives, the shape check has already reported it, and walking it anyway
    turns a report into a traceback.
    """

    return value if isinstance(value, list) else []


def _among(value: Any, allowed: Any) -> bool:
    """Whether a value read from a document is one of a closed set.

    `in` against a dict or a set raises on an unhashable value, so a list where
    an id belongs would crash the reader rather than be refused by it.
    """

    try:
        return value in allowed
    except TypeError:
        return False


def _inside_project(path: str) -> bool:
    """Whether a path a document names stays inside the project.

    `Path.is_absolute()` is False for "/etc/passwd" on Windows, because pathlib
    asks for a drive, so a leading separator passes a check written that way and
    the reader joins it onto the project root. A path is outside when it names
    a root, names a drive, or walks up.
    """

    if not isinstance(path, str) or not path.strip():
        return False
    candidate = PurePosixPath(path.replace(chr(92), "/"))
    if candidate.is_absolute() or path.startswith(("/", chr(92))):
        return False
    if PureWindowsPath(path).drive or ":" in path.split("/")[0]:
        return False
    return ".." not in candidate.parts


def _text(value: Any, label: str, errors: list[str]) -> str:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{label} must be a non-empty string")
        return ""
    return value


def _ids(entries: Any, label: str, errors: list[str], required: bool = True) -> list[str]:
    """Read a list of objects carrying unique `id` values, reporting duplicates."""

    found: list[str] = []
    if not isinstance(entries, list) or (required and not entries):
        shape = "a non-empty array" if required else "an array"
        errors.append(f"{label} must be {shape}")
        return found
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"{label}[{index}] must be an object")
            continue
        value = entry.get("id")
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{label}[{index}].id must be a non-empty string")
            continue
        if value in found:
            errors.append(f"{label}[{index}].id repeats {value!r}")
            continue
        found.append(value)
    return found


def _refs(values: Any, known: Sequence[str], label: str, errors: list[str],
          required: bool = False, *, allow_empty: bool = False) -> None:
    if values is None:
        if required:
            errors.append(f"{label} is required")
        return
    if not isinstance(values, list) or (required and not allow_empty and not values):
        shape = "a non-empty array" if required and not allow_empty else "an array"
        errors.append(f"{label} must be {shape}")
        return
    for index, value in enumerate(values):
        if not isinstance(value, str) or value not in known:
            errors.append(f"{label}[{index}] names something that does not exist: {value!r}")


def validate_narrative(value: Any) -> dict[str, Any]:
    """Return the narrative's report.

    `ok` is whether the document answers the contract. `approved` is reported
    separately, and `notices` carries what is worth saying but is not wrong.
    """

    errors: list[str] = []
    notices: list[str] = []
    approval_errors: list[str] = []
    report: dict[str, Any] = {
        "ok": False, "errors": errors, "notices": notices, "approval_errors": approval_errors,
        "series_id": "", "themes": 0, "arcs": 0, "chapters": 0, "characters": 0,
        "promises": 0, "questions": 0, "knowledge": 0, "approved": False,
        "timeline_id": "", "medium": "", "realization": "", "acts": 0,
        "relationships": 0, "chapter_spans": {}, "character_spans": {},
    }
    if not isinstance(value, dict):
        errors.append("narrative root must be an object")
        return report

    unknown = sorted(set(value) - ROOT_KEYS)
    if "target" in unknown or "model" in unknown:
        errors.append(
            "the narrative names a target or a model; the narrative is about the story "
            "and the interface is chosen much later"
        )
        unknown = [key for key in unknown if key not in {"target", "model"}]
    if unknown:
        errors.append(f"narrative has unknown keys: {unknown}")
    if value.get("artifact_type") != ARTIFACT_TYPE:
        errors.append(f"artifact_type must be {ARTIFACT_TYPE!r}, got {value.get('artifact_type')!r}")
    report["series_id"] = _text(value.get("series_id"), "series_id", errors)
    # A narrative may have no clock. Declared story coordinates still require
    # a real named timeline; presentation chapter numbers are not story time.
    timeline = value.get("timeline_id")
    coordinates = any(isinstance(chapter, dict) and
                      any(chapter.get(key) is not None for key in ("story_order_start", "story_order_end"))
                      for chapter in _listed(value.get("chapters")))
    if (timeline is not None or coordinates) and (not isinstance(timeline, str) or not TIMELINE_ID.fullmatch(timeline)):
        errors.append(
            "timeline_id must name the timeline these chapters are ordered on, the same "
            f"one the state artifacts carry, got {timeline!r}"
        )
    report["timeline_id"] = timeline if isinstance(timeline, str) else None

    # The medium, because a scene of a novel and a scene of a film do not break
    # into the same parts, and a contract that assumes one makes the other write
    # its words for something it is not.
    medium = value.get("medium")
    if not _among(medium, MEDIA):
        errors.append(f"medium must be one of {sorted(MEDIA)}, got {medium!r}")
    report["medium"] = medium if _among(medium, MEDIA) else ""
    report["realization"] = MEDIA.get(str(medium), "")

    # A work may have no explicit theme, agents, organizing arcs or chapters
    # yet, or intentionally use none. Prose design records distinguish those
    # cases; an empty array is not a quality or completion claim.
    theme_ids = _ids(value.get("themes"), "themes", errors, required=False)
    for index, theme in enumerate(_listed(value.get("themes"))):
        if isinstance(theme, dict):
            extra = sorted(set(theme) - {"id", "statement", "note"})
            if extra:
                errors.append(f"themes[{index}] has unknown keys: {extra}")
            _text(theme.get("statement"), f"themes[{index}].statement", errors)
    report["themes"] = len(theme_ids)

    character_ids = _ids(value.get("characters"), "characters", errors, required=False)
    report["characters"] = len(character_ids)
    for index, character in enumerate(_listed(value.get("characters"))):
        if not isinstance(character, dict):
            continue
        label = f"characters[{index}]"
        extra = sorted(set(character) - {"id", "name", "persona", "phases", "prohibitions",
                                         "first_appears", "written_out_in"})
        if extra:
            errors.append(f"{label} has unknown keys: {extra}")
        _text(character.get("name"), f"{label}.name", errors)
        persona = character.get("persona")
        if not isinstance(persona, str) or not persona.strip():
            errors.append(f"{label}.persona must name the persona document for this character")
        elif not _inside_project(persona):
            errors.append(f"{label}.persona must be a path inside the project: {persona!r}")
        # A persona is phase-fixed: it describes one period of a life, and a
        # character who has changed enough gets the next phase as its own file
        # rather than an edit that makes the earlier chapters unverifiable.
        # The chapter each phase begins in is checked once chapters are read.
        phases = character.get("phases")
        if phases is not None:
            if not isinstance(phases, list) or not phases:
                errors.append(f"{label}.phases must be a non-empty array when it is present")
            else:
                seen: list[str] = []
                for position, phase in enumerate(phases):
                    phase_label = f"{label}.phases[{position}]"
                    if not isinstance(phase, dict):
                        errors.append(f"{phase_label} must be an object")
                        continue
                    spare = sorted(set(phase) - {"id", "persona", "from_chapter", "changed", "held"})
                    if spare:
                        errors.append(f"{phase_label} has unknown keys: {spare}")
                    phase_id = phase.get("id")
                    if not isinstance(phase_id, str) or not phase_id.strip():
                        errors.append(f"{phase_label}.id must be a non-empty string")
                    elif phase_id in seen:
                        errors.append(f"{phase_label}.id repeats {phase_id!r}")
                    else:
                        seen.append(phase_id)
                    document = phase.get("persona")
                    if not isinstance(document, str) or not document.strip():
                        errors.append(f"{phase_label}.persona must name this phase's persona document")
                    elif not _inside_project(document):
                        errors.append(
                            f"{phase_label}.persona must be a path inside the project: "
                            f"{document!r}"
                        )
                    # The first phase has no predecessor, so it has nothing to
                    # have changed from. Every later one does, and a phase
                    # boundary that does not say what moved and what held is a
                    # second file with no stated reason to exist.
                    if position == 0:
                        for field in ("changed", "held"):
                            if phase.get(field) is not None:
                                errors.append(
                                    f"{phase_label}.{field} has no earlier phase to compare against"
                                )
                    else:
                        for field in ("changed", "held"):
                            _text(phase.get(field), f"{phase_label}.{field}", errors)
        bans = character.get("prohibitions")
        if bans is not None:
            if not isinstance(bans, list):
                errors.append(f"{label}.prohibitions must be an array")
            else:
                for position, ban in enumerate(bans):
                    ban_label = f"{label}.prohibitions[{position}]"
                    if not isinstance(ban, dict):
                        errors.append(f"{ban_label} must be an object")
                        continue
                    spare = sorted(set(ban) - {"kind", "surface", "statement", "note"})
                    if spare:
                        errors.append(f"{ban_label} has unknown keys: {spare}")
                    kind = ban.get("kind")
                    if kind not in PROHIBITION_KINDS:
                        errors.append(f"{ban_label}.kind must be one of {list(PROHIBITION_KINDS)}, got {kind!r}")
                        continue
                    if kind == "surface":
                        _text(ban.get("surface"), f"{ban_label}.surface", errors)
                        if ban.get("statement") is not None:
                            errors.append(f"{ban_label}.statement does not belong to a surface prohibition")
                    else:
                        _text(ban.get("statement"), f"{ban_label}.statement", errors)
                        if ban.get("surface") is not None:
                            errors.append(f"{ban_label}.surface does not belong to a judgement prohibition")

    arc_ids = _ids(value.get("arcs"), "arcs", errors, required=False)
    report["arcs"] = len(arc_ids)
    for index, arc in enumerate(_listed(value.get("arcs"))):
        if not isinstance(arc, dict):
            continue
        label = f"arcs[{index}]"
        extra = sorted(set(arc) - {"id", "name", "type", "status", "themes", "characters",
                                   "setup", "rising", "climax", "resolution", "want", "need"})
        if extra:
            errors.append(f"{label} has unknown keys: {extra}")
        _text(arc.get("name"), f"{label}.name", errors)
        _text(arc.get("type"), f"{label}.type", errors)
        if arc.get("status") not in ARC_STATUS:
            errors.append(f"{label}.status must be one of {list(ARC_STATUS)}, got {arc.get('status')!r}")
        # A thread may preserve a state, observe a subject, or use an authored
        # organization without requiring a transformation or a want/need pair.
        for field in ("want", "need"):
            if field in arc:
                _text(arc[field], f"{label}.{field}", errors)
        _refs(arc.get("themes"), theme_ids, f"{label}.themes", errors, required=True,
              allow_empty=arc.get("type") != "thematic")
        _refs(arc.get("characters"), character_ids, f"{label}.characters", errors, required=True,
              allow_empty=arc.get("type") != "character")
        # Developmental sections are optional. A declared thread need not be
        # dramatic escalation, a character transformation, or a closed ending.
        for field in ("setup", "climax", "resolution"):
            if field in arc:
                _text(arc[field], f"{label}.{field}", errors)
        if "rising" in arc:
            rising = arc["rising"]
            if not isinstance(rising, list):
                errors.append(f"{label}.rising must be an array of development stages")
            else:
                for position, stage in enumerate(rising):
                    _text(stage, f"{label}.rising[{position}]", errors)

    chapter_ids = _ids(value.get("chapters"), "chapters", errors, required=False)
    report["chapters"] = len(chapter_ids)
    numbers: dict[str, int] = {}
    spans: dict[int, tuple[int, int]] = {}
    seen_numbers: list[int] = []
    for index, chapter in enumerate(_listed(value.get("chapters"))):
        if not isinstance(chapter, dict):
            continue
        label = f"chapters[{index}]"
        extra = sorted(set(chapter) - {"id", "number", "title", "status", "arcs",
                                       "depicts", "story_order_start", "story_order_end"})
        if extra:
            errors.append(f"{label} has unknown keys: {extra}")
        _text(chapter.get("title"), f"{label}.title", errors)
        if chapter.get("status") not in CHAPTER_STATUS:
            errors.append(f"{label}.status must be one of {list(CHAPTER_STATUS)}, got {chapter.get('status')!r}")
        number = chapter.get("number")
        if not isinstance(number, int) or isinstance(number, bool) or number < 1:
            errors.append(f"{label}.number must be a positive integer")
        elif number in seen_numbers:
            errors.append(f"{label}.number repeats {number}")
        else:
            seen_numbers.append(number)
            identifier = chapter.get("id")
            if isinstance(identifier, str):
                numbers[identifier] = number
        _refs(chapter.get("arcs"), arc_ids, f"{label}.arcs", errors, required=True, allow_empty=True)
        depicts = chapter.get("depicts")
        if not isinstance(depicts, list) or not depicts:
            errors.append(
                f"{label}.depicts must name what this chapter presents or holds"
            )
        # A chapter is a unit of telling and story order is a unit of happening.
        # A chapter that names its span makes the difference between them
        # readable: the span of a flashback sits before the chapter before it,
        # and a fact learned here can be checked against the state at that order.
        first = chapter.get("story_order_start")
        last = chapter.get("story_order_end")
        for field, item in (("story_order_start", first), ("story_order_end", last)):
            if timeline is None and first is None and last is None:
                continue
            if item is None:
                errors.append(
                    f"{label}.{field} must say which story order this chapter covers, on the "
                    "timeline the state artifacts are ordered on"
                )
            elif not isinstance(item, int) or isinstance(item, bool) or item < 0:
                errors.append(f"{label}.{field} must be a story order, a non-negative integer")
        if isinstance(first, int) and isinstance(last, int) and not isinstance(first, bool) \
                and not isinstance(last, bool) and last < first:
            errors.append(
                f"{label} ends at story order {last} and begins at {first}"
            )
        if isinstance(number, int) and not isinstance(number, bool) and isinstance(first, int) \
                and not isinstance(first, bool):
            spans[number] = (first, last if isinstance(last, int) else first)
    if seen_numbers and sorted(seen_numbers) != list(range(1, len(seen_numbers) + 1)):
        errors.append(f"chapter numbers must run from 1 without gaps, got {sorted(seen_numbers)}")

    # Told out of order. Not an error: a series may do it deliberately, and the
    # point of recording both orders is that a reader can see which chapters do.
    for number in sorted(spans):
        previous = [item for item in sorted(spans) if item < number]
        if previous and spans[number][1] < spans[previous[-1]][0]:
            notices.append(
                f"chapter {number} covers story order {spans[number][0]} to {spans[number][1]}, "
                f"which ends before chapter {previous[-1]} begins: it is told out of order"
            )
    report["chapter_spans"] = {str(number): list(span) for number, span in sorted(spans.items())}

    # Acts, which is the grouping above chapters. A series of forty chapters and
    # no shape above them is a list, and the shape is the thing a reader feels.
    # Absent is not the same as wrong. A container that is not a list is
    # refused rather than read as no entries.
    declared_acts = value.get("acts")
    act_ids = _ids([] if declared_acts is None else declared_acts, "acts", errors,
                   required=False)
    report["acts"] = len(act_ids)
    act_numbers: list[int] = []
    grouped: dict[str, str] = {}
    for index, act in enumerate(_listed(value.get("acts"))):
        if not isinstance(act, dict):
            continue
        label = f"acts[{index}]"
        extra = sorted(set(act) - {"id", "number", "name", "chapters", "does"})
        if extra:
            errors.append(f"{label} has unknown keys: {extra}")
        _text(act.get("name"), f"{label}.name", errors)
        _text(act.get("does"), f"{label}.does", errors)
        number = act.get("number")
        if not isinstance(number, int) or isinstance(number, bool) or number < 1:
            errors.append(f"{label}.number must be a positive integer")
        elif number in act_numbers:
            errors.append(f"{label}.number repeats {number}")
        else:
            act_numbers.append(number)
        held = act.get("chapters")
        if not isinstance(held, list) or not held:
            errors.append(f"{label}.chapters must name the chapters this act groups")
            continue
        for position, chapter_id in enumerate(held):
            if not isinstance(chapter_id, str) or chapter_id not in chapter_ids:
                errors.append(
                    f"{label}.chapters[{position}] names a chapter that does not exist: "
                    f"{chapter_id!r}"
                )
                continue
            if chapter_id in grouped:
                errors.append(
                    f"{label}.chapters names {chapter_id!r}, which act {grouped[chapter_id]} "
                    "already holds"
                )
                continue
            grouped[chapter_id] = str(act.get("id"))
    # An act holds its chapters in the order they are told, because an act that
    # lists them in another order is an act nobody can read off the series.
    for index, act in enumerate(_listed(value.get("acts"))):
        if not isinstance(act, dict) or not isinstance(act.get("chapters"), list):
            continue
        held = [numbers[chapter_id] for chapter_id in act["chapters"]
                if isinstance(chapter_id, str) and chapter_id in numbers]
        if held and held != sorted(held):
            errors.append(f"acts[{index}].chapters are not in chapter order: {held}")

    if act_numbers and sorted(act_numbers) != list(range(1, len(act_numbers) + 1)):
        errors.append(f"act numbers must run from 1 without gaps, got {sorted(act_numbers)}")
    if act_ids:
        loose = [chapter_id for chapter_id in chapter_ids if chapter_id not in grouped]
        if loose:
            errors.append(f"the series declares acts and these chapters are in none: {loose}")

    # Who these people are to each other before any scene moves it.
    declared_relationships = value.get("relationships")
    relationship_ids = _ids([] if declared_relationships is None else declared_relationships,
                            "relationships", errors,
                            required=False)
    report["relationships"] = len(relationship_ids)
    seen_pairs: list[tuple[str, str]] = []
    for index, bond in enumerate(_listed(value.get("relationships"))):
        if not isinstance(bond, dict):
            continue
        label = f"relationships[{index}]"
        extra = sorted(set(bond) - {"id", "from", "to", "bond_type", "at_start", "arcs"})
        if extra:
            errors.append(f"{label} has unknown keys: {extra}")
        _text(bond.get("bond_type"), f"{label}.bond_type", errors)
        _text(bond.get("at_start"), f"{label}.at_start", errors)
        for field in ("from", "to"):
            who = bond.get(field)
            if not isinstance(who, str) or who not in character_ids:
                errors.append(
                    f"{label}.{field} names somebody the series does not carry: {who!r}"
                )
        _refs(bond.get("arcs"), arc_ids, f"{label}.arcs", errors)
        pair = (str(bond.get("from")), str(bond.get("to")))
        if pair in seen_pairs:
            errors.append(f"{label} repeats the relationship from {pair[0]} to {pair[1]}")
        else:
            seen_pairs.append(pair)
        if pair[0] == pair[1]:
            errors.append(f"{label} is from {pair[0]} to themselves")
    # A relationship is directional, because what one owes the other is not what
    # the other owes back. Declaring one way and never the other is a series that
    # has decided only half of it.
    for first, second in seen_pairs:
        if (second, first) not in seen_pairs:
            notices.append(
                f"the series declares the relationship from {first} to {second} and not the one "
                f"from {second} to {first}; what one owes the other is not what comes back"
            )

    latest = max(seen_numbers) if seen_numbers else 0

    # A series writes people in and writes them out. A cast list that never says
    # so leaves nothing able to notice somebody in a scene three chapters after
    # they left, which is the failure `died-in` exists for in other suites and
    # which this generalises to every way of leaving.
    for index, character in enumerate(_listed(value.get("characters"))):
        if not isinstance(character, dict):
            continue
        label = f"characters[{index}]"
        first = character.get("first_appears")
        last = character.get("written_out_in")
        for field, item in (("first_appears", first), ("written_out_in", last)):
            if item is None:
                continue
            if not _among(item, numbers):
                errors.append(f"{label}.{field} names a chapter that does not exist: {item!r}")
        if _among(first, numbers) and _among(last, numbers) \
                and numbers[last] < numbers[first]:
            errors.append(
                f"{label} is written out in chapter {numbers[last]} and first appears in "
                f"chapter {numbers[first]}"
            )

    # Phases are anchored once the chapters they start in are known. A phase
    # list out of chapter order reads as a history and is not one, and the
    # persona on the character is the one in force now, which is the last
    # phase's. Where the two disagree, a session reads whichever it opened first.
    for index, character in enumerate(_listed(value.get("characters"))):
        if not isinstance(character, dict) or not isinstance(character.get("phases"), list):
            continue
        label = f"characters[{index}]"
        starts: list[int] = []
        for position, phase in enumerate(character["phases"]):
            if not isinstance(phase, dict):
                continue
            start = phase.get("from_chapter")
            if start is None:
                errors.append(f"{label}.phases[{position}].from_chapter must name the chapter this phase begins in")
            elif not _among(start, numbers):
                errors.append(
                    f"{label}.phases[{position}].from_chapter names a chapter that does not exist: {start!r}"
                )
            else:
                starts.append(numbers[start])
        if len(starts) != len(set(starts)):
            errors.append(f"{label}.phases begins two phases in the same chapter")
        elif starts != sorted(starts):
            errors.append(f"{label}.phases must run in chapter order, got chapters {starts}")
        phases = _listed(character.get("phases"))
        if not phases:
            continue
        last = phases[-1]
        if isinstance(last, dict) and isinstance(last.get("persona"), str):
            if character.get("persona") != last["persona"]:
                errors.append(
                    f"{label}.persona must be the document of the last phase, which is "
                    f"{last['persona']!r}, and is {character.get('persona')!r}"
                )

    promise_ids = _ids(value.get("promises"), "promises", errors, required=False)
    report["promises"] = len(promise_ids)
    for index, promise in enumerate(_listed(value.get("promises"))):
        if not isinstance(promise, dict):
            continue
        label = f"promises[{index}]"
        extra = sorted(set(promise) - {"id", "statement", "status", "planted", "payoff",
                                       "arcs", "characters"})
        if extra:
            errors.append(f"{label} has unknown keys: {extra}")
        _text(promise.get("statement"), f"{label}.statement", errors)
        status = promise.get("status")
        known = status in PROMISE_STATUS
        if not known:
            errors.append(f"{label}.status must be one of {list(PROMISE_STATUS)}, got {status!r}")
        # The rest of the promise is checked whichever status it carries, because
        # one unknown word should not hide three other things that are wrong.
        _refs(promise.get("arcs"), arc_ids, f"{label}.arcs", errors, required=True)
        _refs(promise.get("characters"), character_ids, f"{label}.characters", errors)
        planted = promise.get("planted")
        payoff = promise.get("payoff")
        for field, item in (("planted", planted), ("payoff", payoff)):
            if item is not None and not _among(item, numbers):
                errors.append(f"{label}.{field} names a chapter that does not exist: {item!r}")
        if status in ("planted", "paid-off") and not planted:
            errors.append(f"{label} is {status!r} and names no chapter it was planted in")
        if status == "paid-off" and not payoff:
            errors.append(f"{label} is paid off and names no chapter it was paid off in")
        if status == "planned" and planted:
            errors.append(f"{label} is still planned and already names a planted chapter")
        if status == "planned" and payoff:
            errors.append(f"{label} is still planned and already names a payoff chapter")
        if _among(planted, numbers) and _among(payoff, numbers) \
                and numbers[payoff] < numbers[planted]:
            errors.append(
                f"{label} pays off in chapter {numbers[payoff]} before it is planted in "
                f"chapter {numbers[planted]}"
            )
        if status == "planted" and _among(planted, numbers) \
                and latest - numbers[planted] >= UNFIRED_GAP:
            notices.append(
                f"{label} was planted in chapter {numbers[planted]} and is still unpaid "
                f"{latest - numbers[planted]} chapters later"
            )

    question_ids = _ids(value.get("questions"), "questions", errors, required=False)
    report["questions"] = len(question_ids)
    for index, question in enumerate(_listed(value.get("questions"))):
        if not isinstance(question, dict):
            continue
        label = f"questions[{index}]"
        extra = sorted(set(question) - {"id", "statement", "status", "introduced", "resolved",
                                        "arcs", "characters"})
        if extra:
            errors.append(f"{label} has unknown keys: {extra}")
        _text(question.get("statement"), f"{label}.statement", errors)
        status = question.get("status")
        if status not in QUESTION_STATUS:
            errors.append(f"{label}.status must be one of {list(QUESTION_STATUS)}, got {status!r}")
        # The rest of the question is checked whichever status it carries, because
        # one unknown word should not hide three other things that are wrong.
        _refs(question.get("arcs"), arc_ids, f"{label}.arcs", errors)
        _refs(question.get("characters"), character_ids, f"{label}.characters", errors)
        introduced = question.get("introduced")
        resolved = question.get("resolved")
        for field, item in (("introduced", introduced), ("resolved", resolved)):
            if item is not None and not _among(item, numbers):
                errors.append(f"{label}.{field} names a chapter that does not exist: {item!r}")
        # An open question with no introduced chapter is one the series intends to
        # raise and has not raised yet. Answering it, though, requires both ends.
        if status in ("answered", "resolved") and not introduced:
            errors.append(f"{label} is {status!r} and names no chapter it was introduced in")
        if status in ("answered", "resolved") and not resolved:
            errors.append(f"{label} is {status!r} and names no chapter it was answered in")
        if status == "open" and resolved:
            errors.append(f"{label} is still open and already names a resolved chapter")
        if _among(introduced, numbers) and _among(resolved, numbers) \
                and numbers[resolved] < numbers[introduced]:
            errors.append(
                f"{label} resolves in chapter {numbers[resolved]} before it is introduced in "
                f"chapter {numbers[introduced]}"
            )

    knowledge_ids = _ids(value.get("knowledge"), "knowledge", errors, required=False)
    report["knowledge"] = len(knowledge_ids)
    knowers = list(character_ids) + [AUDIENCE]
    for index, entry in enumerate(_listed(value.get("knowledge"))):
        if not isinstance(entry, dict):
            continue
        label = f"knowledge[{index}]"
        extra = sorted(set(entry) - {"id", "fact", "known_by", "learned_in", "note"})
        if extra:
            errors.append(f"{label} has unknown keys: {extra}")
        _text(entry.get("fact"), f"{label}.fact", errors)
        _refs(entry.get("known_by"), knowers, f"{label}.known_by", errors, required=True)
        learned = entry.get("learned_in")
        if learned is not None and not _among(learned, numbers):
            errors.append(f"{label}.learned_in names a chapter that does not exist: {learned!r}")

    approved = value.get("approved")
    if approved is not None:
        if not isinstance(approved, dict):
            approval_errors.append("approved must be an object")
        else:
            spare = sorted(set(approved) - {"by", "at", "content_sha256", "note"})
            if spare:
                approval_errors.append(f"approved has unknown keys: {spare}")
            if not isinstance(approved.get("by"), str) or not str(approved.get("by")).strip():
                approval_errors.append("approved.by must be a non-empty string")
            when = approved.get("at")
            if not isinstance(when, str) or not APPROVED_AT.match(when):
                approval_errors.append(f"approved.at must be an RFC3339 UTC timestamp, got {when!r}")
            recorded = approved.get("content_sha256")
            if not isinstance(recorded, str) or not SHA256.match(recorded):
                approval_errors.append(
                    "approved.content_sha256 must be the sha256 of the narrative without its "
                    f"approval, got {recorded!r}"
                )
            elif recorded != content_sha256(value):
                approval_errors.append(
                    "the narrative changed after it was approved: approved.content_sha256 does "
                    "not match its current content"
                )

    report["ok"] = not errors
    report["approved"] = isinstance(approved, dict) and not approval_errors
    report["chapter_numbers"] = numbers
    report["character_spans"] = {
        str(character.get("id")): [character.get("first_appears"), character.get("written_out_in")]
        for character in _listed(value.get("characters"))
        if isinstance(character, dict)
    }
    return report


def persona_in_force(character: dict[str, Any], chapter_number: int,
                     numbers: dict[str, int]) -> tuple[str | None, str | None]:
    """Which persona document describes this character during that chapter.

    Returns the phase id and the document. A character with no declared phases
    has one persona for the whole series, and it is in force throughout. A
    character whose first phase begins later than the chapter asked about has no
    document for it, which is the honest answer: the file that exists describes
    a different period of that life.
    """

    phases = character.get("phases")
    if not isinstance(phases, list) or not phases:
        document = character.get("persona")
        return (None, document if isinstance(document, str) else None)
    found: tuple[str | None, str | None] = (None, None)
    for phase in phases:
        if not isinstance(phase, dict):
            continue
        start = numbers.get(str(phase.get("from_chapter")))
        if start is not None and start <= chapter_number:
            found = (phase.get("id"), phase.get("persona"))
    return found


def load_narrative(path: Path) -> dict[str, Any]:
    """Read and validate one narrative. Raises on an unreadable or invalid document."""

    value = json.loads(path.read_text(encoding="utf-8"))
    report = validate_narrative(value)
    if not report["ok"]:
        raise ValueError(f"narrative is invalid: {path}: " + "; ".join(report["errors"]))
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate one series narrative.")
    parser.add_argument("narrative", type=Path)
    parser.add_argument("--content-sha256", action="store_true",
                        help="Print the hash an approval has to carry, and nothing else")
    args = parser.parse_args(argv)
    try:
        value = json.loads(args.narrative.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, ensure_ascii=False, indent=2))
        return 1
    if args.content_sha256:
        print(content_sha256(value))
        return 0
    report = validate_narrative(value)
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
