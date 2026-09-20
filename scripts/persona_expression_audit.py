#!/usr/bin/env python3
"""Read-only drafting hygiene, never a rating of individuality or emotion.

    python scripts/persona_expression_audit.py persona.md [other.md ...]

Report existing form gaps and literal reuse of authored descriptions in known
portrayal fields. No network, series, pack, generation, migration or approval.
See references/narrative-authoring.md#inspect-expression-drafting-hygiene.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Sequence

from narrative_index import placeholder_details

from io_budget import optional_count, read_stream
# A deliberately explicit list, not an inference of what arbitrary prose means.
# Field/table inventories outside this list remain a human review responsibility.
PORTRAYAL_FIELDS = frozenset({
    "identity_scope_and_basis", "inner_core", "recognizable_portrayal", "protected_dimensions",
    "signature_dynamics", "permitted_variation", "meaningful_boundaries",
    "identity_and_intent_binding", "identity_realization",
    "first_person", "second_person", "voice", "habitual_gestures", "thinking_pose", "nervous_habits",
    "relaxed_posture", "gait", "combat_stance", "laugh_and_cry",
    "facial_expressiveness", "embodied_baseline_context",
    "expressive_channels_and_limits", "attention_and_movement_baseline",
    "emotional_baseline", "fatigue_response", "rest_style", "burnout_signs",
    "decision_style", "decision_priorities", "problem_approach",
    "information_processing", "when_surprised", "when_angry", "when_sad",
    "when_happy", "when_praised", "when_insulted", "when_confused",
    "under_pressure", "when_succeeded", "when_failed", "when_others_succeed",
    "when_others_fail", "when_sick_or_injured", "when_others_sick",
    "when_apologizing", "when_thanking", "under_stress",
    "perceived_situation_and_access", "appraisal_and_purpose",
    "display_control_and_initial_response", "response_components",
    "development_and_recovery", "overlap_and_exceptions",
    "speech_baseline_context", "address_and_register", "sentence_construction",
    "conversational_initiative", "sentence_endings", "rhythm",
    "characteristic_expressions", "speech_style", "vocabulary_level",
    "speech_taboos", "activation_and_scope", "communicative_purpose",
    "speech_delta", "vocal_delivery_delta", "listening_delta",
    "held_features_and_body_link", "overlap_resolution", "switch_release_and_repair",
    "languages", "dialect_accent", "code_switching", "listening_style",
    "backchanneling", "questioning_style", "silence_tolerance", "humor_style",
    "what_makes_laugh", "sarcasm_level", "lying_behavior", "when_hiding_something",
    "emotional_expression", "emotional_distance", "relationship_conditions_and_audience",
    "baseline_shift", "speech_realization", "reaction_realization",
    "decision_realization", "overlap_switch_and_hold", "body_language_realization",
    "physical_distance_realization",
})
EXAMINED_STATES = frozenset({"unknown", "n/a", "not applicable", "none", "undecided"})
FIELD = re.compile(r"^(\s*)[-*+]\s+\*\*([^*]+)\*\*:\s*(.*)$")
HEADING = re.compile(r"^\s*#{1,6}\s+(.+?)\s*$")
FENCE = re.compile(r"^\s*(`{3,}|~{3,})(.*)$")


def _mask_comment(match: re.Match[str]) -> str:
    return re.sub(r"[^\n]", " ", match.group())


def visible_lines(text: str) -> tuple[list[str], list[dict[str, Any]]]:
    """Hide instructions, quoted/fenced examples and metadata; keep line numbers.

    An unclosed delimiter is not silently a successful parse. Its remaining
    region stays hidden (instructions are not data) and a parse note is emitted.
    """
    notes: list[dict[str, Any]] = []
    for match in re.finditer(r"<!--.*?(?:-->|\Z)", text, flags=re.DOTALL):
        if not match.group().endswith("-->"):
            notes.append({"line": text.count("\n", 0, match.start()) + 1,
                          "kind": "unclosed-comment"})
    masked = re.sub(r"<!--.*?(?:-->|\Z)", _mask_comment, text, flags=re.DOTALL)
    lines = masked.splitlines()
    if lines and lines[0].strip() == "---":
        end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
        if end is None:
            notes.append({"line": 1, "kind": "unclosed-front-matter"})
            return ["" for _ in lines], notes
        lines[:end + 1] = ["" for _ in range(end + 1)]
    fence: str | None = None
    fence_length = 0
    fence_start = 0
    for index, line in enumerate(lines):
        if fence is not None:
            match = FENCE.match(line)
            if (match and match[1][0] == fence and len(match[1]) >= fence_length
                    and not match[2].strip()):
                fence = None
            lines[index] = ""
            continue
        if line.lstrip().startswith(">"):
            lines[index] = ""
            continue
        match = FENCE.match(line)
        if match:
            fence = match[1][0]
            fence_length = len(match[1])
            fence_start = index + 1
            lines[index] = ""
    if fence is not None:
        notes.append({"line": fence_start, "kind": "unclosed-fence"})
    return lines, sorted(notes, key=lambda item: (item["line"], item["kind"]))


def authored_fields(text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Extract known labeled leaf descriptions, not examples or semantic modes.

    Supports inline/multiline Markdown bullet fields. Containers are not leaves.
    Tables and arbitrary prose are intentionally not interpreted as field data.
    """
    lines, notes = visible_lines(text)
    fields: list[dict[str, Any]] = []
    heading = ""
    for index, line in enumerate(lines):
        title = HEADING.match(line)
        if title:
            heading = title[1]
        match = FIELD.match(line)
        if not match or match[2] not in PORTRAYAL_FIELDS:
            continue
        indent = len(match[1].expandtabs(4))
        chunks = [match[3].strip()] if match[3].strip() else []
        container = False
        for following in lines[index + 1:]:
            if not following.strip():
                continue
            if (HEADING.match(following)
                    or re.fullmatch(r"\s*(?:---+|___+|\*\*\*+)\s*", following)):
                break
            other = FIELD.match(following)
            if other:
                if len(other[1].expandtabs(4)) > indent:
                    container = True
                break
            bullet = re.match(r"^(\s*)[-*+]\s", following)
            if bullet and len(bullet[1].expandtabs(4)) <= indent:
                break
            # Outdented prose ends a nested field; top-level fields may have
            # unindented wrapped prose before the next heading/bullet.
            if indent and len(following) - len(following.lstrip()) <= indent:
                break
            if following.lstrip().startswith("|"):
                break
            chunks.append(following.strip())
        value = " ".join(" ".join(chunks).split())
        if container or not value or value.casefold() in EXAMINED_STATES:
            continue
        fields.append({"line": index + 1, "field": match[2],
                       "heading": heading, "normalized_text": value})
    return fields, notes


def audit(paths: Sequence[str | Path], min_chars: int = 24, *, max_bytes: int | None = None) -> dict[str, Any]:
    """Read explicit inputs once. Repetition is always advisory, not an error."""
    optional_count(max_bytes, 'maximum input bytes')
    if min_chars < 1:
        raise ValueError("min_chars must be positive")
    files: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    seen: set[Path] = set()
    grouped: dict[str, list[dict[str, Any]]] = {}
    for supplied in paths:
        try:
            path = Path(supplied).expanduser().resolve()
            if path in seen:
                continue
            seen.add(path)
            if path.suffix.lower() != ".md":
                raise ValueError("expected an explicit Markdown (.md) file")
            with path.open("rb") as stream:
                raw = read_stream(stream, max_bytes, label=str(path))
            text = raw.decode("utf-8-sig")
            fields, notes = authored_fields(text)
            item = {
                "path": str(path), "sha256": hashlib.sha256(raw).hexdigest(),
                "size_bytes": len(raw), "recognized_fields": len(fields),
                "unfilled": placeholder_details(text), "parse_notes": notes,
            }
            files.append(item)
            for field in fields:
                value = field["normalized_text"]
                if len(value) >= min_chars:
                    location = {key: field[key] for key in ("line", "field", "heading")}
                    location["path"] = str(path)
                    grouped.setdefault(value, []).append(location)
        except (OSError, ValueError, RuntimeError) as exc:
            errors.append({"path": str(supplied), "message": str(exc)})
    duplicates = []
    for value in sorted(grouped):
        locations = sorted(grouped[value], key=lambda item: (item["path"], item["line"]))
        if len(locations) > 1:
            duplicates.append({
                "kind": "repeated-field-text", "advisory": True,
                "scope": "across-files" if len({item["path"] for item in locations}) > 1
                         else "within-file",
                "normalized_text": value, "locations": locations,
            })
    return {
        "ok": not errors,
        "scope": "literal drafting hygiene only",
        "semantic_quality": "not_assessed", "adoption": "not_assessed",
        "mutates_files": False, "minimum_duplicate_characters": min_chars,
        "files": files, "duplicate_groups": duplicates, "errors": errors,
    }


def positive_integer(value: str) -> int:
    try:
        result = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if result < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("personas", nargs="+", help="explicit Markdown file paths; inspected once each")
    parser.add_argument("--min-chars", type=positive_integer, default=24,
                        help="minimum Unicode length for literal duplicate triage (default: 24)")
    parser.add_argument("--fail-on-unfilled", action="store_true",
                        help="exit 2 for form gaps only; repetition remains advisory")
    parser.add_argument("--max-input-bytes", type=positive_integer, help="Optional operator byte budget per input; omitted means no application limit")
    args = parser.parse_args(argv)
    report = audit(args.personas, args.min_chars, max_bytes=args.max_input_bytes)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["ok"]:
        return 1
    if args.fail_on_unfilled and any(item["unfilled"] for item in report["files"]):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
