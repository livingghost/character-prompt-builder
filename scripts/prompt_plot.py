#!/usr/bin/env python3
"""Validate a prompt plot: its shape against the schema, its rules here.

The schema settles what fields exist and what types they hold. It cannot settle
that every visible beat is taken up by the derived statements, that a statement
names a beat the plot shows, or that `free` is the one kind with no beat behind
it, because each of those is a relation between two parts of the document. Both
run, in that order, so a plot that passes here has passed the shape as well.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "prompt-plot.schema.json"

ARTIFACT_TYPE = "prompt-plot"
APPROVED_AT = re.compile(
    r"^[0-9]{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])"
    r"T(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](?:\.[0-9]+)?Z$"
)
SHA256 = re.compile(r"^[a-f0-9]{64}$")
VISIBILITIES = ("visible", "context")
KINDS = ("shows", "placement", "composition", "must_preserve", "free")
UNSOURCED_KINDS = ("free",)


def content_sha256(value: dict[str, Any]) -> str:
    """The hash of everything the approval is about, which is the plot without it.

    An approval that names only a time is a claim about a document that can
    change after the claim. This binds it to the bytes that were approved.
    """

    body = {key: item for key, item in value.items() if key != "approved"}
    canonical = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _story(value: Any, errors: list[str]) -> dict[str, str]:
    """Return {id: visibility} for the story beats that parse."""

    beats: dict[str, str] = {}
    if not isinstance(value, list) or not value:
        errors.append("story must be a non-empty array")
        return beats
    for index, entry in enumerate(value):
        label = f"story[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{label} must be an object")
            continue
        unknown = sorted(set(entry) - {"id", "beat", "visibility"})
        if unknown:
            errors.append(f"{label} has unknown keys: {unknown}")
        beat_id = entry.get("id")
        if not isinstance(beat_id, str) or not beat_id.strip():
            errors.append(f"{label}.id must be a non-empty string")
            beat_id = None
        elif beat_id in beats:
            errors.append(f"{label}.id repeats {beat_id!r}")
        text = entry.get("beat")
        if not isinstance(text, str) or not text.strip():
            errors.append(f"{label}.beat must be a non-empty string")
        visibility = entry.get("visibility")
        if visibility not in VISIBILITIES:
            errors.append(f"{label}.visibility must be one of {list(VISIBILITIES)}, got {visibility!r}")
            visibility = None
        if beat_id is not None and visibility is not None:
            beats[beat_id] = visibility
    return beats


def schema_errors(value: Any) -> list[str]:
    """The plot against the schema, where one is installed beside this file."""

    if not SCHEMA_PATH.is_file():
        return []
    try:
        import sys as _sys
        _sys.path.insert(0, str(ROOT / "scripts"))
        from state_protocol import parse_json, validate_against_schema
        schema = parse_json(SCHEMA_PATH.read_text(encoding="utf-8"))
    except Exception as reason:  # noqa: BLE001
        return [f"the prompt plot schema could not be read: {reason}"]
    return [f"schema: {message}" for message in validate_against_schema(value, schema)]


def validate_prompt_plot(value: Any) -> dict[str, Any]:
    """Return {"ok", "errors", "beats", "visible_beats", "derived", "kinds", "source", "approved"}."""

    errors: list[str] = []
    if not isinstance(value, dict):
        return {
            "ok": False, "errors": ["plot root must be an object"],
            "beats": 0, "visible_beats": 0, "derived": 0, "kinds": {},
            "source": None, "approved": False, "approval_errors": [],
        }
    # The shape first, from the document that states it. What follows are the
    # relations between two parts of the plot, which no schema expresses, and
    # running only those left the schema an authority nothing consulted.
    errors.extend(schema_errors(value))
    unknown = sorted(set(value) - {"artifact_type", "approved", "source", "story", "derived"})
    if "target" in unknown or "model" in unknown:
        errors.append(
            "the plot names a target or a model; the plot is settled and approved first "
            "and the interface is chosen after it"
        )
        unknown = [key for key in unknown if key not in {"target", "model"}]
    if unknown:
        errors.append(f"plot has unknown keys: {unknown}")
    if value.get("artifact_type") != ARTIFACT_TYPE:
        errors.append(f"artifact_type must be {ARTIFACT_TYPE!r}, got {value.get('artifact_type')!r}")

    approved = value.get("approved")
    approval_errors: list[str] = []
    if approved is not None:
        if not isinstance(approved, dict):
            approval_errors.append("approved must be an object")
        else:
            extra = sorted(set(approved) - {"by", "at", "content_sha256", "note"})
            if extra:
                approval_errors.append(f"approved has unknown keys: {extra}")
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

    # Where this plot came from, when it came from somewhere. A plot written
    # from a brief has no source and the brief is its root; a plot written from
    # an approved upstream artifact names it, so one image carries one approval
    # chain rather than two that do not mention each other.
    source = value.get("source")
    if source is not None:
        if not isinstance(source, dict):
            errors.append("source must be an object")
            source = None
        else:
            spare = sorted(set(source) - {"artifact_type", "id", "content_sha256", "shot_id", "note"})
            if spare:
                errors.append(f"source has unknown keys: {spare}")
            for field in ("artifact_type", "id"):
                item = source.get(field)
                if not isinstance(item, str) or not item.strip():
                    errors.append(f"source.{field} must be a non-empty string")
            recorded = source.get("content_sha256")
            if not isinstance(recorded, str) or not SHA256.match(recorded):
                errors.append(
                    "source.content_sha256 must be the hash the upstream artifact was approved "
                    f"under, got {recorded!r}"
                )
            shot = source.get("shot_id")
            if shot is not None and (not isinstance(shot, str) or not shot.strip()):
                errors.append("source.shot_id must be a non-empty string when present")

    beats = _story(value.get("story"), errors)

    entries = value.get("derived")
    if not isinstance(entries, list) or not entries:
        errors.append("derived must be a non-empty array")
        entries = []

    counts = {kind: 0 for kind in KINDS}
    referenced: set[str] = set()
    for index, entry in enumerate(entries):
        label = f"derived[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{label} must be an object")
            continue
        extra = sorted(set(entry) - {"kind", "statement", "from"})
        if extra:
            errors.append(f"{label} has unknown keys: {extra}")
        statement = entry.get("statement")
        if not isinstance(statement, str) or not statement.strip():
            errors.append(f"{label}.statement must be a non-empty string")
        kind = entry.get("kind")
        if kind not in KINDS:
            errors.append(f"{label}.kind must be one of {list(KINDS)}, got {kind!r}")
            continue
        counts[kind] += 1

        sources = entry.get("from")
        if kind in UNSOURCED_KINDS:
            if sources is not None:
                errors.append(f"{label}.from does not belong to a {kind!r} statement, which is what the story leaves open")
            continue
        if not isinstance(sources, list) or not sources:
            errors.append(f"{label}.from must name at least one story beat")
            continue
        if len(sources) != len(set(sources)):
            errors.append(f"{label}.from repeats a beat id")
        for beat_id in sources:
            if not isinstance(beat_id, str) or not beat_id.strip():
                errors.append(f"{label}.from contains a non-string beat id")
                continue
            if beat_id not in beats:
                errors.append(f"{label}.from names a beat that does not exist: {beat_id!r}")
                continue
            if beats[beat_id] == "context":
                errors.append(
                    f"{label}.from names {beat_id!r}, a context beat: a beat the frame does not "
                    "show cannot put anything in the frame"
                )
                continue
            referenced.add(beat_id)

    for kind in KINDS:
        if counts[kind] == 0:
            errors.append(
                f"derived carries no {kind!r} statement; state it, and where there is nothing to say, "
                "say that in the statement"
            )

    for beat_id, visibility in beats.items():
        if visibility == "visible" and beat_id not in referenced:
            errors.append(
                f"story beat {beat_id!r} is marked visible but nothing derives from it: "
                "either it puts something in the frame or its visibility is 'context'"
            )

    visible = sum(1 for visibility in beats.values() if visibility == "visible")
    return {
        "ok": not errors,
        "errors": errors,
        "beats": len(beats),
        "visible_beats": visible,
        "derived": len(entries),
        "kinds": counts,
        "source": source if isinstance(source, dict) else None,
        "approved": isinstance(approved, dict) and not approval_errors,
        "approval_errors": approval_errors,
    }


def load_prompt_plot(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    report = validate_prompt_plot(value)
    if not report["ok"]:
        raise ValueError(f"prompt plot is invalid: {path}: " + "; ".join(report["errors"]))
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plot", type=Path)
    parser.add_argument("--content-sha256", action="store_true",
                        help="Print the hash an approval has to carry, and nothing else")
    args = parser.parse_args(argv)
    try:
        value = json.loads(args.plot.read_text(encoding="utf-8"))
        if args.content_sha256:
            print(content_sha256(value))
            return 0
        report = validate_prompt_plot(value)
    except (OSError, json.JSONDecodeError) as exc:
        report = {"ok": False, "errors": [str(exc)], "beats": 0, "visible_beats": 0,
                  "derived": 0, "kinds": {}, "approved": False, "approval_errors": []}
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
