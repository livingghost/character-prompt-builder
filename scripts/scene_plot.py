#!/usr/bin/env python3
"""Validate a scene's presented material and supported realization.

A scene declares its setting, viewpoint, purpose and beats. Sourced statements
identify the beats supporting placement, preservation and realization in shots,
pages or passages. Context-only material cannot silently become visible output.

The scene can have no cast, dialogue, organizing threads or persistent changes.
A turn and named dramatic structure are optional; a depicted condition can
persist. A unit's focal_beat key points to its focal visible beat
without requiring transformation. Declared references and supplied typed fields
remain checked even when their containing lists may be empty.

The plot names no target model. Validation and approval establish a supported
artifact contract, not its artistic adequacy or the semantic coherence of linked
world, design and persona prose.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Sequence

ARTIFACT_TYPE = "scene-plot"
APPROVED_AT = re.compile(
    r"^[0-9]{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])"
    r"T(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](?:\.[0-9]+)?Z$"
)
SHA256 = re.compile(r"^[a-f0-9]{64}$")
# The shared protocol's id shape for a place, narrowed to what a file name can
# hold, because this id also names the file under narrative/world/locations.
# A colon is legal in the protocol and opens an alternate data stream on NTFS.
LOCATION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
# Genette's three, which is the vocabulary narratology settled on rather than a
# fourth one invented here. Zero knows more than anyone; internal is restricted
# to one character; external reaches nobody's interior.
FOCALIZATIONS = ("zero", "internal", "external")


# Which tradition a series works in, declared rather than assumed. Requiring a
# crisis and a best-bad-choice would refuse a four-act story driven by revelation
# and carrying no conflict at all.

# What a scene becomes, and the parts each medium actually has. A shot has a
# camera; a page has panels and an edge the reader turns; a passage has a mode.
REALIZATIONS = {
    "shots": ({"id", "focal_beat", "shows", "composition"}, ("shows", "composition")),
    "pages": ({"id", "focal_beat", "shows", "panels", "ends_on_turn", "spread"}, ("shows",)),
    "passages": ({"id", "focal_beat", "covers", "mode"}, ("covers",)),
}
# Scene and summary is the distinction prose craft settled on: one is shown at
# the pace it happens, the other tells what happened in less time than it took.
PASSAGE_MODES = ("scene", "summary")

VISIBILITIES = ("visible", "context")
SCENE_KINDS = ("placement", "must_preserve", "free")
UNSOURCED_KINDS = ("free",)
ROOT_KEYS = {
    "artifact_type", "scene_id", "narrative_sha256", "chapter", "order", "arcs",
    "characters", "themes", "focalization", "setting",
    "scene_function", "delivery_role", "turn", "structure", "exchanges",
    "proposition", "approved", "beats", "placement", "must_preserve", "free",
    "state_changes", "relationship_delta", "realization",
}
# Screenplay practice settled the parts of a scene heading long ago: whether it is
# inside or out, where, and what hour. The first of those decides light, sound and
# what the weather can reach, and a scene that never says it leaves each of those
# to whichever unit is realized first.
INTERIOR_EXTERIOR = ("interior", "exterior", "both")
SETTING_KEYS = {"interior_exterior", "location", "where", "time_of_day", "season",
                "weather", "scene_context"}
APPROVED_KEYS = {"by", "at", "content_sha256", "note"}


def content_sha256(value: dict[str, Any]) -> str:
    """The hash of everything the approval is about, which is the plot without it.

    An approval that names only a time is a claim about a document that can
    change after the claim. This binds it to the bytes that were approved.
    """

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


def _beats(value: Any, errors: list[str]) -> dict[str, str]:
    beats: dict[str, str] = {}
    if not isinstance(value, list) or not value:
        errors.append("beats must be a non-empty array")
        return beats
    for index, entry in enumerate(value):
        label = f"beats[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{label} must be an object")
            continue
        unknown = sorted(set(entry) - {"id", "beat", "visibility", "teaches"})
        if unknown:
            errors.append(f"{label} has unknown keys: {unknown}")
        beat_id = entry.get("id")
        if not isinstance(beat_id, str) or not beat_id.strip():
            errors.append(f"{label}.id must be a non-empty string")
            beat_id = None
        elif beat_id in beats:
            errors.append(f"{label}.id repeats {beat_id!r}")
        _text(entry.get("beat"), f"{label}.beat", errors)
        visibility = entry.get("visibility")
        if visibility not in VISIBILITIES:
            errors.append(f"{label}.visibility must be one of {list(VISIBILITIES)}, got {visibility!r}")
            visibility = None
        teaches = entry.get("teaches")
        if teaches is not None:
            if not isinstance(teaches, list) or not teaches:
                errors.append(f"{label}.teaches must be a non-empty array of who learns here")
            else:
                for position, who in enumerate(teaches):
                    if not isinstance(who, str) or not who.strip():
                        errors.append(f"{label}.teaches[{position}] must be a non-empty string")
            if visibility == "context":
                errors.append(
                    f"{label}.teaches does not belong to a context beat: a beat the scene "
                    "does not show teaches nobody"
                )
        if beat_id is not None and visibility is not None:
            beats[beat_id] = visibility
    return beats


def _source(source: Any, beats: dict[str, str], label: str, errors: list[str], referenced: set[str]) -> None:
    if not isinstance(source, str) or not source.strip():
        errors.append(f"{label} contains a non-string beat id")
        return
    if source not in beats:
        errors.append(f"{label} names a beat that does not exist: {source!r}")
        return
    if beats[source] == "context":
        errors.append(
            f"{label} names {source!r}, a context beat: a beat the scene does not show "
            "cannot put anything in a frame"
        )
        return
    referenced.add(source)


def _sources(value: Any, beats: dict[str, str], label: str, errors: list[str],
             referenced: set[str], missing: str) -> None:
    """A list of beat ids, each resolved against the beats the scene shows."""

    if not isinstance(value, list) or not value:
        errors.append(f"{label} {missing}")
        return
    for source in value:
        _source(source, beats, label, errors, referenced)
    hashable = [source for source in value if isinstance(source, str)]
    if len(hashable) != len(set(hashable)):
        errors.append(f"{label} repeats a beat id")


def _statements(
    value: Any,
    kind: str,
    label: str,
    beats: dict[str, str],
    errors: list[str],
    referenced: set[str],
) -> int:
    """One list of statements of a single kind, each naming the beats it follows from."""

    if not isinstance(value, list) or not value:
        errors.append(
            f"{label} must be a non-empty array; where there is nothing to say, "
            "say that in a statement"
        )
        return 0
    for index, entry in enumerate(value):
        entry_label = f"{label}[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{entry_label} must be an object")
            continue
        allowed = {"statement"} if kind in UNSOURCED_KINDS else {"statement", "from"}
        spare = sorted(set(entry) - allowed)
        if spare:
            errors.append(f"{entry_label} has unknown keys: {spare}")
        _text(entry.get("statement"), f"{entry_label}.statement", errors)
        if kind in UNSOURCED_KINDS:
            continue
        sources = entry.get("from")
        if not isinstance(sources, list) or not sources:
            errors.append(f"{entry_label}.from must name at least one beat")
            continue
        # The beat ids are checked before they are counted, because a list
        # where an id belongs cannot go into a set and the count would raise
        # before the check that refuses it.
        for source in sources:
            _source(source, beats, f"{entry_label}.from", errors, referenced)
        hashable = [source for source in sources if isinstance(source, str)]
        if len(hashable) != len(set(hashable)):
            errors.append(f"{entry_label}.from repeats a beat id")
    return len(value)



def _setting(value: Any, errors: list[str]) -> dict[str, Any]:
    """Where and when the scene happens.

    A scene plot that says only what happens leaves the place and the hour to
    whoever writes the first shot, and the second shot is written by someone
    reading that shot. The names here are the shared protocol's, so one id
    reaches the place file, the environment at that story point, and the scene
    context that binds them.
    """

    found: dict[str, Any] = {}
    if not isinstance(value, dict):
        errors.append(
            "setting must say where and when this scene happens: location, where, and time_of_day"
        )
        return found
    spare = sorted(set(value) - SETTING_KEYS)
    if spare:
        errors.append(f"setting has unknown keys: {spare}")

    inside = value.get("interior_exterior")
    if inside not in INTERIOR_EXTERIOR:
        errors.append(
            f"setting.interior_exterior must be one of {list(INTERIOR_EXTERIOR)}, got {inside!r}"
        )
    else:
        found["interior_exterior"] = inside

    location = value.get("location")
    if not isinstance(location, str) or not LOCATION_ID.fullmatch(location):
        errors.append(
            "setting.location must be the id of a place, matching the shared protocol's "
            f"location_id, got {location!r}"
        )
    else:
        found["location"] = location
    for field in ("where", "time_of_day"):
        found[field] = _text(value.get(field), f"setting.{field}", errors)
    # A series whose story does not turn on the season or the weather says
    # nothing about them rather than saying nothing in a field.
    for field in ("season", "weather"):
        item = value.get(field)
        if item is None:
            continue
        found[field] = _text(item, f"setting.{field}", errors)
    context = value.get("scene_context")
    if context is not None:
        if not isinstance(context, str) or not context.strip():
            errors.append("setting.scene_context must name a scene context snapshot in the project")
        elif not _inside_project(context):
            errors.append(
                f"setting.scene_context must be a path inside the project: {context!r}"
            )
        else:
            found["scene_context"] = context
    return found



def _focalization(value: Any, errors: list[str]) -> dict[str, Any]:
    """Through whom the scene is told, in the vocabulary narratology settled on.

    Zero focalization is a narrator who knows more than anyone in the scene.
    Internal focalization is restricted to what one character knows, and that
    character filters everything the audience receives. External focalization
    sees from outside and reaches nobody's interior.

    This is not the camera. A shot's viewpoint profile says where the lens is;
    this says whose knowledge the telling is limited to, which is why it sits
    beside the narrative's knowledge entries and not beside the camera.
    """

    found: dict[str, Any] = {}
    if not isinstance(value, dict):
        errors.append(
            "focalization must say how this scene is told: kind, one of "
            f"{list(FOCALIZATIONS)}, and for internal focalization, who it is through"
        )
        return found
    spare = sorted(set(value) - {"kind", "through", "note"})
    if spare:
        errors.append(f"focalization has unknown keys: {spare}")
    kind = value.get("kind")
    if kind not in FOCALIZATIONS:
        errors.append(f"focalization.kind must be one of {list(FOCALIZATIONS)}, got {kind!r}")
        return found
    found["kind"] = kind
    through = value.get("through")
    if kind == "internal":
        if not isinstance(through, str) or not through.strip():
            errors.append(
                "focalization.through must name the character this scene is restricted to; "
                "internal focalization is a restriction and a restriction needs a holder"
            )
        else:
            found["through"] = through
    elif kind == "external":
        # The camera may stay with somebody without reaching their interior.
        if through is not None:
            found["through"] = _text(through, "focalization.through", errors)
    elif through is not None:
        errors.append(
            "focalization.through does not belong to zero focalization, which is not "
            "restricted to anybody"
        )
    return found



def _turn(value: Any, errors: list[str]) -> dict[str, Any]:
    """Optional comparison of a condition, including deliberate persistence.

    Omission claims no turn. A provided object must still have the declared
    fields; identical endpoints do not make an observational scene invalid.
    """

    found: dict[str, Any] = {}
    if value is None:
        return found
    if not isinstance(value, dict):
        errors.append("turn must be an object when supplied")
        return found
    spare = sorted(set(value) - {"value", "from", "to", "note"})
    if spare:
        errors.append(f"turn has unknown keys: {spare}")
    for field in ("value", "from", "to"):
        found[field] = _text(value.get(field), f"turn.{field}", errors)
    return found


def _structure(value: Any, beats: dict[str, str], errors: list[str]) -> dict[str, Any]:
    """The named parts of whichever tradition this series works in.

    A profile is declared, not assumed. Each part it names points at a beat of
    this scene, so the shape is checked against what the scene actually contains
    rather than restated beside it.
    """

    found: dict[str, Any] = {}
    if value is None:
        return found
    if not isinstance(value, dict):
        errors.append("structure must be an object naming a profile and its parts")
        return found
    spare = sorted(set(value) - {"profile", "parts"})
    if spare:
        errors.append(f"structure has unknown keys: {spare}")
    profile = _text(value.get("profile"), "structure.profile", errors)
    found["profile"] = profile
    parts = value.get("parts")
    if not isinstance(parts, dict) or not parts:
        errors.append("structure.parts must be a non-empty map of authored names to beats")
        return found
    filled: dict[str, str] = {}
    for name, beat_id in parts.items():
        _text(name, "structure part name", errors)
        if not isinstance(beat_id, str) or not beat_id.strip():
            errors.append(f"structure.parts.{name} must name a beat of this scene")
            continue
        if beat_id not in beats:
            errors.append(f"structure.parts.{name} names a beat that does not exist: {beat_id!r}")
            continue
        filled[name] = beat_id
    found["parts"] = filled
    return found


def _realization(value: Any, beats: dict[str, str], errors: list[str],
                 referenced: set[str]) -> dict[str, Any]:
    """What the scene becomes, in the parts the medium actually has.

    A shot has a camera, a page has panels and an edge the reader turns, a
    passage has a mode and a length. A contract that offers only one of the
    three makes the other two write the first one's words for something it is
    not.
    """

    found: dict[str, Any] = {"kind": "", "units": 0, "unit_ids": [], "statements": 0}
    if not isinstance(value, dict):
        errors.append(
            f"realization must say what this scene becomes: kind, one of "
            f"{sorted(REALIZATIONS)}, and the units it breaks into"
        )
        return found
    spare = sorted(set(value) - {"kind", "units"})
    if spare:
        errors.append(f"realization has unknown keys: {spare}")
    kind = value.get("kind")
    if not _among(kind, REALIZATIONS):
        errors.append(f"realization.kind must be one of {sorted(REALIZATIONS)}, got {kind!r}")
        return found
    found["kind"] = kind
    allowed, required_statements = REALIZATIONS[kind]

    units = value.get("units")
    if not isinstance(units, list) or not units:
        errors.append(f"realization.units must be a non-empty array of {kind}")
        return found

    ids: list[str] = []
    statements = 0
    for index, unit in enumerate(units):
        label = f"realization.units[{index}]"
        if not isinstance(unit, dict):
            errors.append(f"{label} must be an object")
            continue
        extra = sorted(set(unit) - allowed)
        if extra:
            errors.append(f"{label} has keys {kind!r} does not have: {extra}")
        unit_id = unit.get("id")
        if not isinstance(unit_id, str) or not unit_id.strip():
            errors.append(f"{label}.id must be a non-empty string")
        elif unit_id in ids:
            errors.append(f"{label}.id repeats {unit_id!r}")
        else:
            ids.append(unit_id)
        change = unit.get("focal_beat")
        if not isinstance(change, str) or not change.strip():
            errors.append(f"{label}.focal_beat must name the beat this {kind[:-1]} carries")
        else:
            _source(change, beats, f"{label}.focal_beat", errors, referenced)
        for name in required_statements:
            statements += _statements(unit.get(name), name, f"{label}.{name}", beats, errors,
                                      referenced)
        if kind == "pages":
            panels = unit.get("panels")
            if not isinstance(panels, int) or isinstance(panels, bool) or panels < 1:
                errors.append(
                    f"{label}.panels must be how many panels this page holds, from 1, "
                    f"got {panels!r}"
                )
            for flag in ("ends_on_turn", "spread"):
                if unit.get(flag) is not None and not isinstance(unit.get(flag), bool):
                    errors.append(f"{label}.{flag} must be true or false")
        if kind == "passages":
            mode = unit.get("mode")
            if mode not in PASSAGE_MODES:
                errors.append(
                    f"{label}.mode must be one of {list(PASSAGE_MODES)}, got {mode!r}: a passage "
                    "shown at the pace it happens is not a passage that summarises"
                )
    found["units"] = len(ids)
    found["unit_ids"] = ids
    found["statements"] = statements
    return found



def _exchanges(value: Any, beats: dict[str, str], cast: list[str], errors: list[str],
               referenced: set[str]) -> int:
    """What is said, and what saying it accomplishes.

    A persona says how a character speaks. Nothing said who speaks in a scene or
    what the speaking is for, so dialogue was the one thing the whole chain had
    no place for. An exchange that accomplishes nothing is the failure this
    catches: it names what changes because the words were said.

    A scene where nobody speaks carries none, and says so by carrying none.
    """

    if value is None:
        return 0
    if not isinstance(value, list):
        errors.append("exchanges must be an array of what is said and what it accomplishes")
        return 0
    ids: list[str] = []
    for index, exchange in enumerate(value):
        label = f"exchanges[{index}]"
        if not isinstance(exchange, dict):
            errors.append(f"{label} must be an object")
            continue
        spare = sorted(set(exchange) - {"id", "between", "about", "achieves", "from"})
        if spare:
            errors.append(f"{label} has unknown keys: {spare}")
        exchange_id = exchange.get("id")
        if not isinstance(exchange_id, str) or not exchange_id.strip():
            errors.append(f"{label}.id must be a non-empty string")
        elif exchange_id in ids:
            errors.append(f"{label}.id repeats {exchange_id!r}")
        else:
            ids.append(exchange_id)
        _text(exchange.get("about"), f"{label}.about", errors)
        _text(exchange.get("achieves"), f"{label}.achieves", errors)
        between = exchange.get("between")
        if not isinstance(between, list) or not between:
            errors.append(f"{label}.between must name who is speaking")
        else:
            for position, who in enumerate(between):
                if not isinstance(who, str) or who not in cast:
                    errors.append(
                        f"{label}.between[{position}] names {who!r}, who the scene does not say "
                        "is in it"
                    )
        _sources(
            exchange.get("from"),
            beats,
            f"{label}.from",
            errors,
            referenced,
            "must name the beat this is said in",
        )
    return len(value)


def validate_scene_plot(value: Any) -> dict[str, Any]:
    """Return the plot's report.

    `ok` is whether the document answers the contract. `approved` is whether it
    carries an approval that still matches its own content; it is reported
    independently of `ok`, so a caller can tell an invalid plot from an
    unapproved one.
    """

    errors: list[str] = []
    report: dict[str, Any] = {
        "ok": False, "errors": errors, "scene_id": "", "beats": 0, "visible_beats": 0,
        "shots": 0, "shot_ids": [], "units": 0, "unit_ids": [], "realization": "",
        "turn": {}, "structure": {}, "exchanges": 0,
        "scene_statements": 0, "unit_statements": 0,
        "chapter": "", "order": 0, "arcs": [], "characters": [], "themes": [],
        "focalization": {}, "setting": {}, "narrative_sha256": "",
        "state_changes": 0, "relationship_delta": 0,
        "approved": False, "approval_errors": [],
    }
    approval_errors: list[str] = report["approval_errors"]

    if not isinstance(value, dict):
        errors.append("scene plot root must be an object")
        return report

    unknown = sorted(set(value) - ROOT_KEYS)
    if "target" in unknown or "model" in unknown:
        errors.append(
            "the scene plot names a target or a model; the plot is settled and approved first "
            "and the interface is chosen after it"
        )
        unknown = [key for key in unknown if key not in {"target", "model"}]
    if unknown:
        errors.append(f"scene plot has unknown keys: {unknown}")
    if value.get("artifact_type") != ARTIFACT_TYPE:
        errors.append(f"artifact_type must be {ARTIFACT_TYPE!r}, got {value.get('artifact_type')!r}")
    report["scene_id"] = _text(value.get("scene_id"), "scene_id", errors)
    report["chapter"] = _text(value.get("chapter"), "chapter", errors)
    # Which narrative this was approved against. A change above invalidates what
    # was approved below it, and without this nothing could tell which version
    # "above" meant.
    digest = value.get("narrative_sha256")
    if not isinstance(digest, str) or not SHA256.fullmatch(digest):
        errors.append(
            "narrative_sha256 must be the content hash of the narrative this plot was written "
            f"against, so a change above it can invalidate this approval, got {digest!r}"
        )
    else:
        report["narrative_sha256"] = digest
    # Where this scene falls inside its chapter. A chapter with five scenes and
    # no order is five scenes nobody can put in a row.
    order = value.get("order")
    if not isinstance(order, int) or isinstance(order, bool) or order < 1:
        errors.append(f"order must be this scene's place in its chapter, from 1, got {order!r}")
    else:
        report["order"] = order
    _text(value.get("proposition"), "proposition", errors)

    arcs = value.get("arcs")
    if not isinstance(arcs, list):
        errors.append("arcs must be an array naming the declared threads this scene uses")
    else:
        for index, arc in enumerate(arcs):
            if not isinstance(arc, str) or not arc.strip():
                errors.append(f"arcs[{index}] must be a non-empty string")
        report["arcs"] = list(arcs)
    # Who is in this scene. Statements say what a frame shows and a beat says
    # what happens, and neither is a list, so without this nothing answers
    # whether a character the series declares ever appears, or whether a
    # submission names somebody the scene does not contain.
    # Which of the series' themes this scene carries. A theme declared at the top
    # and dramatised in no scene is the failure this whole layer exists to catch,
    # and it is invisible unless a scene says which ones it is for.
    carried = value.get("themes")
    if not isinstance(carried, list):
        errors.append("themes must be an array naming the declared themes this scene carries")
    else:
        for index, theme in enumerate(carried):
            if not isinstance(theme, str) or not theme.strip():
                errors.append(f"themes[{index}] must be a non-empty string")
        report["themes"] = [theme for theme in carried if isinstance(theme, str)]

    cast = value.get("characters")
    if not isinstance(cast, list):
        errors.append("characters must be an array naming who is in this scene")
    else:
        for index, who in enumerate(cast):
            if not isinstance(who, str) or not who.strip():
                errors.append(f"characters[{index}] must be a non-empty string")
        report["characters"] = [who for who in cast if isinstance(who, str)]

    report["setting"] = _setting(value.get("setting"), errors)

    # Told through somebody the scene does not contain is a scene told through
    # a window onto another room.
    report["focalization"] = _focalization(value.get("focalization"), errors)
    through = report["focalization"].get("through")
    if through and through not in report["characters"]:
        errors.append(
            f"focalization.through names {through!r}, who the scene does not say is in it"
        )

    _text(value.get("scene_function"), "scene_function", errors)
    _text(value.get("delivery_role"), "delivery_role", errors)

    beats = _beats(value.get("beats"), errors)
    report["beats"] = len(beats)
    report["visible_beats"] = sum(1 for visibility in beats.values() if visibility == "visible")
    referenced: set[str] = set()

    changes = value.get("state_changes")
    if not isinstance(changes, list):
        errors.append(
            "state_changes must be an array of persistent consequences; use [] when none occur"
        )
    else:
        for index, change in enumerate(changes):
            label = f"state_changes[{index}]"
            if not isinstance(change, dict):
                errors.append(f"{label} must be an object")
                continue
            spare = sorted(set(change) - {"target", "change", "from"})
            if spare:
                errors.append(f"{label} has unknown keys: {spare}")
            _text(change.get("target"), f"{label}.target", errors)
            _text(change.get("change"), f"{label}.change", errors)
            _sources(change.get("from"), beats, f"{label}.from", errors, referenced,
                     "must name the beat this scene leaves it behind from")
    report["state_changes"] = len(changes) if isinstance(changes, list) else 0

    delta = value.get("relationship_delta")
    if delta is not None:
        if not isinstance(delta, list):
            errors.append("relationship_delta must be an array")
        else:
            for index, move in enumerate(delta):
                label = f"relationship_delta[{index}]"
                if not isinstance(move, dict):
                    errors.append(f"{label} must be an object")
                    continue
                spare = sorted(set(move) - {"channel", "between", "change", "from"})
                if spare:
                    errors.append(f"{label} has unknown keys: {spare}")
                _text(move.get("channel"), f"{label}.channel", errors)
                between = move.get("between")
                if not isinstance(between, list) or len(between) < 2:
                    errors.append(f"{label}.between must name at least two characters")
                else:
                    # The same rule the exchanges carry. Without it a real name
                    # is refused and an invented one passes, which is the wrong
                    # way round.
                    for position, who in enumerate(between):
                        if not isinstance(who, str) or who not in report["characters"]:
                            errors.append(
                                f"{label}.between[{position}] names {who!r}, who the scene does "
                                "not say is in it"
                            )
                _text(move.get("change"), f"{label}.change", errors)
                _sources(move.get("from"), beats, f"{label}.from", errors, referenced,
                         "must name the beat this moved in")
        report["relationship_delta"] = len(delta) if isinstance(delta, list) else 0

    scene_statements = 0
    for kind in SCENE_KINDS:
        scene_statements += _statements(value.get(kind), kind, kind, beats, errors, referenced)
    report["scene_statements"] = scene_statements

    report["exchanges"] = _exchanges(value.get("exchanges"), beats, report["characters"],
                                     errors, referenced)
    if "turn" in value and value["turn"] is None:
        errors.append("turn must be an object when supplied")
    report["turn"] = _turn(value.get("turn"), errors)
    report["structure"] = _structure(value.get("structure"), beats, errors)

    realization = _realization(value.get("realization"), beats, errors, referenced)
    report["realization"] = realization["kind"]
    report["unit_ids"] = realization["unit_ids"]
    report["units"] = realization["units"]
    report["unit_statements"] = realization["statements"]
    # A submission is a shot of a screen work, so the gate matches against the
    # units of that kind and finds none where the scene becomes pages or prose.
    report["shot_ids"] = realization["unit_ids"] if realization["kind"] == "shots" else []
    report["shots"] = len(report["shot_ids"])

    for beat_id, visibility in beats.items():
        if visibility == "visible" and beat_id not in referenced:
            errors.append(
                f"beat {beat_id!r} is marked visible but nothing takes anything from it: "
                "either the scene or one of its units carries it, or its visibility is 'context'"
            )

    approved = value.get("approved")
    if approved is not None:
        if not isinstance(approved, dict):
            approval_errors.append("approved must be an object")
        else:
            spare = sorted(set(approved) - APPROVED_KEYS)
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
                    "approved.content_sha256 must be the sha256 of the plot without its approval, "
                    f"got {recorded!r}"
                )
            elif recorded != content_sha256(value):
                approval_errors.append(
                    "the plot changed after it was approved: approved.content_sha256 does not "
                    "match the plot's current content"
                )

    report["ok"] = not errors
    report["approved"] = isinstance(approved, dict) and not approval_errors
    return report


def load_scene_plot(path: Path) -> dict[str, Any]:
    """Read and validate one plot. Raises on an unreadable or invalid document."""

    value = json.loads(path.read_text(encoding="utf-8"))
    report = validate_scene_plot(value)
    if not report["ok"]:
        raise ValueError(f"scene plot is invalid: {path}: " + "; ".join(report["errors"]))
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate one scene plot.")
    parser.add_argument("plot", type=Path)
    parser.add_argument("--content-sha256", action="store_true",
                        help="Print the hash an approval has to carry, and nothing else")
    args = parser.parse_args(argv)
    try:
        value = json.loads(args.plot.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, ensure_ascii=False, indent=2))
        return 1
    if args.content_sha256:
        print(content_sha256(value))
        return 0
    report = validate_scene_plot(value)
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
