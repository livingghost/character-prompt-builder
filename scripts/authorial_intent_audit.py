#!/usr/bin/env python3
"""Inspect current authorial-intent records and explicit links; never rate a portrayal.

    python scripts/authorial_intent_audit.py --root <project> <record.md> [other.md ...]

Reads only explicit Markdown inputs and their authorial_intent_refs dependencies.
Reports declared status, structural gaps, exact intent targets and source hashes.
No network, writes, approval, migration, applicability decision or spoiler filtering.
See references/narrative-authoring.md#inspect-authorial-intent-links.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import unquote, urlsplit

from persona_expression_audit import visible_lines

from io_budget import optional_count, read_stream
ID = r"[a-z][a-z0-9-]*"
INTENT = re.compile(rf"^### Intent ({ID})\s*$")
FIELD = re.compile(r"^- \*\*([a-z][a-z0-9_]*)\*\*:\s*(.*)$")
LINK = re.compile(r"\[[^\]\n]*\]\(([^()\s]+)\)")
STATUSES = frozenset({"user-anchor", "proposed", "adopted", "rejected", "deferred"})
REQUIRED_FIELDS = (
    "status", "basis", "subject_scope", "portrayal_aim", "recognition_anchors",
    "variation_envelope", "contrast_and_cadence", "departure_policy",
    "world_and_subject_dependencies", "priority_and_conflicts", "information_boundary",
    "realization_links", "review_basis",
)
UNRESOLVED = re.compile(r"^(?:undecided|unknown|tbd)(?:\b|:)", re.I)


def fields_in(lines: list[str], start: int = 0, end: int | None = None) -> list[dict[str, Any]]:
    """Read current top-level labeled Markdown fields with indented continuation.

    Instructions/fences have already been masked. Nested labels are neither
    aliases nor top-level answers. Line numbers always refer to the original file.
    """
    stop = len(lines) if end is None else end
    results: list[dict[str, Any]] = []
    index = start
    while index < stop:
        match = FIELD.fullmatch(lines[index])
        if not match:
            index += 1
            continue
        pieces = [match[2]] if match[2] else []
        line_no = index + 1
        index += 1
        while index < stop:
            following = lines[index]
            if not following.strip():
                index += 1
                continue
            if not following.startswith((" ", "\t")):
                break
            pieces.append(following.strip())
            index += 1
        results.append({"name": match[1], "line": line_no, "value": " ".join(pieces).strip()})
    return results


def parse_document(text: str) -> dict[str, Any]:
    """Parse one current Markdown contract without interpreting prose meaning."""
    lines, notes = visible_lines(text)
    errors: list[dict[str, Any]] = [
        {"line": item["line"], "message": item["kind"]} for item in notes
    ]
    gaps: list[dict[str, Any]] = []
    intents: dict[str, dict[str, Any]] = {}
    for index, line in enumerate(lines):
        match = INTENT.fullmatch(line)
        if not match:
            if line.startswith("### Intent "):
                # A template slot is an explicit drafting gap, not a real ID.
                if line.strip() == "### Intent {intent_id}":
                    gaps.append({"line": index + 1, "message": "intent_id is undecided"})
                else:
                    errors.append({"line": index + 1, "message": "invalid intent heading or ID"})
            continue
        identifier = match[1]
        if identifier in intents:
            errors.append({"line": index + 1, "message": f"duplicate intent ID: {identifier}"})
            continue
        end = next((j for j in range(index + 1, len(lines))
                    if re.match(r"^#{1,3}\s", lines[j])), len(lines))
        fields: dict[str, dict[str, Any]] = {}
        for field in fields_in(lines, index + 1, end):
            name = field["name"]
            if name in fields:
                errors.append({"line": field["line"], "message": f"duplicate field: {identifier}.{name}"})
            else:
                fields[name] = field
        for name in REQUIRED_FIELDS:
            field = fields.get(name)
            if field is None or not field["value"] or UNRESOLVED.match(field["value"]):
                gaps.append({"line": field["line"] if field else index + 1,
                             "message": f"unresolved intent field: {identifier}.{name}"})
        status = fields.get("status", {}).get("value", "")
        if status and not UNRESOLVED.match(status) and status not in STATUSES:
            errors.append({"line": fields["status"]["line"],
                           "message": f"invalid declared status: {identifier}"})
        intents[identifier] = {"id": identifier, "line": index + 1,
                               "declared_status": status,
                               "fields": {name: field["line"] for name, field in fields.items()}}
    refs: list[dict[str, Any]] = []
    for field in fields_in(lines):
        if field["name"] != "authorial_intent_refs":
            continue
        value = field["value"]
        links = LINK.findall(value)
        if not links:
            if not re.match(r"^(?:n/a|none):\s*\S", value, re.I):
                gaps.append({"line": field["line"], "message": "authorial_intent_refs needs links or n/a: reason"})
        refs.extend({"line": field["line"], "link": target} for target in links)
    return {"intents": intents, "references": refs, "errors": errors, "gaps": gaps}


def bounded_path(root: Path, supplied: Path) -> Path:
    """Allow regular local .md files within root, never symlinks or escapes."""
    candidate = supplied if supplied.is_absolute() else root / supplied
    # Check the uncollapsed path as well as its result, including symlink parents.
    for part in (candidate, *candidate.parents):
        if part == root.parent:
            break
        if part.is_symlink():
            raise ValueError("symbolic links are not allowed in inspected paths")
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("file is outside the declared project root")
    if resolved.suffix.lower() != ".md":
        raise ValueError("expected a Markdown (.md) file")
    if not resolved.is_file():
        raise ValueError("Markdown file does not exist or is not a regular file")
    return resolved


def link_target(root: Path, source: Path, href: str) -> tuple[Path, str]:
    value = urlsplit(href)
    if value.scheme or value.netloc or value.query or href.startswith(("/", "\\")):
        raise ValueError("intent links must be local relative Markdown paths without a query")
    path, fragment = unquote(value.path), unquote(value.fragment)
    if "\\" in path or "\x00" in path or path.startswith("/") or re.match(r"^[A-Za-z]:", path):
        raise ValueError("invalid relative intent path")
    match = re.fullmatch(rf"intent-({ID})", fragment)
    if not match:
        raise ValueError("intent link needs a #intent-<id> fragment")
    target = bounded_path(root, source.parent / path if path else source)
    return target, match[1]


def audit(root: str | Path, paths: Sequence[str | Path], *, max_bytes: int | None = None, max_files: int | None = None) -> dict[str, Any]:
    """Inspect the explicit dependency closure once, without adopting or choosing it."""
    optional_count(max_bytes, 'maximum input bytes')
    optional_count(max_files, 'maximum files')
    root_path = Path(root).expanduser().resolve()
    report: dict[str, Any] = {
        "ok": True, "root": str(root_path),
        "scope": "current authorial-intent records and explicit local links only",
        "mutates_files": False, "semantic_quality": "not_assessed", "adoption": "not_assessed",
        "applicability": "not_assessed", "consumer_filtering": "not_performed",
        "files": [], "links": [], "review_notes": [], "gaps": [], "errors": [],
    }
    errors, gaps = report["errors"], report["gaps"]
    if not root_path.is_dir():
        errors.append({"path": str(root_path), "message": "project root must be an existing directory"})
    if not paths:
        errors.append({"path": str(root_path), "message": "at least one explicit Markdown input is required"})
    pending: list[Path] = []
    for supplied in paths:
        try:
            pending.append(bounded_path(root_path, Path(supplied).expanduser()))
        except (OSError, ValueError, RuntimeError) as exc:
            errors.append({"path": str(supplied), "message": str(exc)})
    loaded: dict[Path, dict[str, Any]] = {}
    attempted: set[Path] = set()
    edges: list[tuple[str, int, Path, str]] = []
    while pending:
        path = pending.pop(0)
        if path in attempted:
            continue
        if max_files is not None and len(attempted) >= max_files:
            errors.append({"path": str(path), "message": f"dependency closure exceeds the explicitly supplied {max_files}-file budget; audit incomplete"})
            break
        attempted.add(path)
        relative = path.relative_to(root_path).as_posix()
        try:
            with path.open("rb") as stream:
                raw = read_stream(stream, max_bytes, label=str(path))
            parsed = parse_document(raw.decode("utf-8-sig"))
            loaded[path] = parsed
            report["files"].append({"path": relative, "sha256": hashlib.sha256(raw).hexdigest(),
                                    "size_bytes": len(raw), "intents": list(parsed["intents"].values())})
            errors.extend({"path": relative, **item} for item in parsed["errors"])
            gaps.extend({"path": relative, **item} for item in parsed["gaps"])
            for ref in parsed["references"]:
                try:
                    target, identifier = link_target(root_path, path, ref["link"])
                    edges.append((relative, ref["line"], target, identifier))
                    pending.append(target)
                except (OSError, ValueError, RuntimeError) as exc:
                    errors.append({"path": relative, "line": ref["line"], "message": str(exc)})
        except (OSError, ValueError, RuntimeError) as exc:
            errors.append({"path": relative, "message": str(exc)})
    for source, line, target, identifier in edges:
        record = loaded.get(target, {}).get("intents", {}).get(identifier)
        target_name = target.relative_to(root_path).as_posix()
        if record is None:
            errors.append({"path": source, "line": line,
                           "message": f"unresolved intent target: {target_name}#intent-{identifier}"})
            continue
        report["links"].append({"source": source, "line": line, "target": target_name,
                                "intent_id": identifier, "declared_status": record["declared_status"]})
        if record["declared_status"] in {"proposed", "rejected", "deferred"}:
            report["review_notes"].append({"path": source, "line": line,
                "message": f"referenced intent {identifier} is declared {record['declared_status']}; do not infer adoption"})
    report["files"].sort(key=lambda item: item["path"])
    report["links"].sort(key=lambda item: (item["source"], item["line"], item["target"], item["intent_id"]))
    report["ok"] = not errors
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--root", type=Path, required=True, help="Boundary for local inputs and referenced Markdown")
    parser.add_argument("paths", nargs="+", help="Explicit paths, absolute or relative to --root")
    parser.add_argument("--fail-on-gaps", action="store_true", help="Exit 2 for unresolved fields; does not assess meaning or adoption")
    parser.add_argument("--max-input-bytes", type=int, help="Optional operator budget per input; no default size ceiling")
    parser.add_argument("--max-files", type=int, help="Optional operator budget for the dependency closure; no default count ceiling")
    args = parser.parse_args(argv)
    result = audit(args.root, args.paths, max_bytes=args.max_input_bytes, max_files=args.max_files)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if not result["ok"] else 2 if args.fail_on_gaps and result["gaps"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
