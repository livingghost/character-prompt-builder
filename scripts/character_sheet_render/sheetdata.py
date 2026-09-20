"""Sidecar table access, shared utilities, and shared contract constants."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from character_sheet import validate_sidecar
from state_protocol import parse_json

ROOT = Path(__file__).resolve().parents[2]


PLACEHOLDERS = frozenset(
    {"", "-", "unknown", "tbd", "n/a", "not applicable", "unspecified"}
)
HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = parse_json(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise ValueError(f"{label} is not valid UTF-8 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object: {path}")
    return value


def load_sheet(sheet_dir: Path) -> tuple[dict[str, Any], Path | None]:
    data_path = sheet_dir / "sheet-data.json"
    if not data_path.is_file():
        return {"fields": {}, "tables": {}, "slots": {}}, None
    sheet = load_json_object(data_path, label="sheet-data.json")
    return validate_sidecar(sheet, sheet_root=sheet_dir, verify_files=False), data_path


def row_values(row: Any) -> dict[str, str]:
    """Return values from a current-format sidecar table row."""

    if not isinstance(row, Mapping):
        return {}
    candidate = row.get("values")
    if not isinstance(candidate, Mapping):
        return {}
    return {str(k): str(v) for k, v in candidate.items() if isinstance(k, str)}


def table_values(sheet: Mapping[str, Any], table_id: str) -> list[dict[str, str]]:
    return [entry["values"] for entry in table_entries(sheet, table_id)]


def table_entries(sheet: Mapping[str, Any], table_id: str) -> list[dict[str, Any]]:
    """Return rows with their persistent identity as well as their values."""

    tables = sheet.get("tables")
    if not isinstance(tables, Mapping):
        return []
    rows = tables.get(table_id)
    if not isinstance(rows, list):
        return []
    entries: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        row_id = row.get("row_id") if isinstance(row, Mapping) else None
        if not isinstance(row_id, str) or not row_id:
            continue
        entries.append({"row_id": row_id, "index": index, "values": row_values(row)})
    return entries


def source_entry(
    box: Mapping[str, Any], sheet: Mapping[str, Any], table_id: str
) -> dict[str, Any] | None:
    """Resolve a table-bound panel by persistent row id or profile source index."""

    entries = table_entries(sheet, table_id)
    source_row_id = meaningful(box.get("source_row_id", ""))
    if source_row_id:
        return next((entry for entry in entries if entry["row_id"] == source_row_id), None)
    index = int(box.get("source_index", 0))
    conventional_id = f"{table_id}.{index + 1:02d}"
    exact = next((entry for entry in entries if entry["row_id"] == conventional_id), None)
    if exact is not None:
        return exact
    return entries[index] if index < len(entries) else None


def box_source_row_id(box: Mapping[str, Any], table_id: str) -> str:
    """Persistent row id a table-bound profile box intends to represent."""

    declared = meaningful(box.get("source_row_id", ""))
    if declared:
        return declared
    return f"{table_id}.{int(box.get('source_index', 0)) + 1:02d}"


def meaningful(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    stripped = value.strip()
    return "" if stripped.casefold() in PLACEHOLDERS else stripped


def compact_join(parts: Sequence[Any], *, separator: str = "; ") -> str:
    values = [meaningful(value) for value in parts if isinstance(value, str)]
    return separator.join(value for value in values if value)


def first_matching_part(rows: Sequence[Mapping[str, str]]) -> Mapping[str, str] | None:
    for row in rows:
        part = meaningful(row.get("part", "")).casefold()
        if any(token in part for token in ("eye", "iris", "sensor", "lens", "optic")):
            return row
    for row in rows:
        if meaningful(row.get("attribute", "")):
            return row
    return None


def row_has_visual_data(row: Mapping[str, str], columns: Sequence[str]) -> bool:
    return any(meaningful(row.get(column, "")) for column in columns)


COVERAGE_MARK_COLUMNS = (
    "mark_id",
    "landmark_anchor",
    "shape_path",
    "laterality",
    "counterpart_rule",
    "continuity_rule",
    "visibility_rule",
)
COVERAGE_PART_COLUMNS = (
    "part",
    "attribute",
    "laterality",
    "counterpart_rule",
    "continuity_rule",
    "visibility_rule",
)
COVERAGE_EXPRESSION_COLUMNS = (
    "state",
    "overall_read",
    "channel_states",
    "fixed_identity_cues",
    "notes",
)
COVERAGE_VIEW_COLUMNS = ("view_id", "label", "specification", "must_prove")
COVERAGE_ITEM_COLUMNS = (
    "item",
    "visual_identity",
    "scale_attachment",
    "role_rule",
    "continuity_rule",
    "visibility_rule",
)
COVERAGE_OUTFIT_COLUMNS = (
    "outfit",
    "description",
    "notes",
    "continuity_rule",
    "visibility_rule",
)
COVERAGE_COLOR_COLUMNS = (
    "zone",
    "base",
    "shadow",
    "highlight",
    "visibility_rule",
)
COVERAGE_EVIDENCE_COLUMNS = (
    "subject_table",
    "subject_row_id",
    "view_id",
    "orientation_configuration",
    "specification",
    "must_prove",
)
COVERAGE_POSE_COLUMNS = ("posture", "gesture", "kind_channels", "distance_orientation")
# Performance series: one panel per row, showing how this identity moves.
COVERAGE_PART_STATE_COLUMNS = ("part", "state", "configuration", "read")
COVERAGE_MOTION_COLUMNS = ("region", "range", "limit", "must_prove")
COVERAGE_ACTION_COLUMNS = ("action", "phase", "mechanics", "kind_channels")
COVERAGE_GESTURE_COLUMNS = ("gesture", "context", "body", "props")

# A row has two kinds of column. The drawing columns say what the picture
# shows and go into a prompt; the rule columns say how a returned picture is
# judged and go to the review record and the coverage audit, never to a model.
DRAW_COLUMNS = {
    "marks": ("mark_id", "landmark_anchor", "shape_path", "laterality"),
    "parts": ("part", "attribute", "laterality"),
    "items": ("item", "visual_identity", "scale_attachment"),
    "outfits": ("outfit", "description", "notes"),
    "colors": ("zone", "base", "shadow", "highlight"),
}
RULE_COLUMNS = {
    "marks": ("counterpart_rule", "continuity_rule", "visibility_rule"),
    "parts": ("counterpart_rule", "continuity_rule", "visibility_rule"),
    "items": ("role_rule", "continuity_rule", "visibility_rule"),
    "outfits": ("continuity_rule", "visibility_rule"),
    "colors": ("visibility_rule",),
    "views": ("must_prove",),
    "evidence": ("must_prove",),
    "motion": ("limit", "must_prove"),
}


def review_text(table_id: str, row: Mapping[str, str]) -> str:
    """The judging criteria a row carries, joined for the request record."""

    return compact_join(tuple(row.get(column, "") for column in RULE_COLUMNS.get(table_id, ())))


FIXED_BINDINGS = frozenset({"kind-fixed", "character-fixed", "individual-fixed"})
FIXED_VISUAL_TABLES = {
    "marks": (COVERAGE_MARK_COLUMNS, True),
    "parts": (COVERAGE_PART_COLUMNS, True),
    "items": (COVERAGE_ITEM_COLUMNS, True),
    "outfits": (COVERAGE_OUTFIT_COLUMNS, True),
    "colors": (COVERAGE_COLOR_COLUMNS, False),
}

PAIRED_PART_TOKENS = frozenset(
    {
        "eye",
        "ear",
        "arm",
        "leg",
        "hand",
        "paw",
        "foot",
        "feet",
        "wing",
        "horn",
        "antenna",
        "sensor",
        "shoulder",
        "hip",
    }
)
SYMMETRIC_LATERALITY_TERMS = (
    "bilateral",
    "both",
    "symmetric",
    "symmetrical",
    "center",
    "central",
    "midline",
    "none",
)
# Values that name a topology with no left/right counterpart to compare
# against. The validator itself blesses these as deliberate unpaired
# declarations, so they are not "asymmetric" rows and must not demand a
# counterpart_rule naming an opposite side that does not exist.
UNPAIRED_LATERALITY_TERMS = (
    "single",
    "unpaired",
    "radial",
    "distributed",
    "unique",
)


def paired_part_declared(part: str) -> bool:
    return bool(_part_tokens(part).intersection(PAIRED_PART_TOKENS))


def asymmetric_laterality(value: str) -> bool:
    """True when the laterality names a left/right counterpart to compare.

    Explicit side-taking terms (unilateral, left only, different sides) are
    asymmetric. Deliberately unpaired declarations (single, unpaired, radial,
    distributed) are symmetric in the counterpart sense: there is no opposite
    side, so they raise no counterpart requirement.
    """

    normalized = meaningful(value).casefold()
    if not normalized:
        return False
    if any(
        term in normalized
        for term in (
            "asymmetric",
            "asymmetrical",
            "unilateral",
            "left only",
            "right only",
            "left side only",
            "right side only",
            "different sides",
        )
    ):
        return True
    if any(term in normalized for term in UNPAIRED_LATERALITY_TERMS):
        return False
    return not any(term in normalized for term in SYMMETRIC_LATERALITY_TERMS)


def _part_tokens(value: str) -> set[str]:
    found = re.findall(r"[a-z0-9]+", value.casefold())
    normalized = set()
    for token in found:
        if token in {"a", "an", "and", "or", "of", "the"}:
            continue
        normalized.add(token[:-1] if len(token) > 3 and token.endswith("s") else token)
    return normalized


def _part_match_score(source_keys: Sequence[str], part_value: str) -> int:
    """Rank a parts row for one authored panel without fuzzy substring collisions."""

    part_tokens = _part_tokens(part_value)
    if not part_tokens:
        return 0
    best = 0
    for source_key in source_keys:
        source_tokens = _part_tokens(source_key)
        overlap = source_tokens.intersection(part_tokens)
        if not overlap:
            continue
        exact = source_tokens == part_tokens
        score = len(overlap) * 100 - abs(len(source_tokens) - len(part_tokens))
        if exact:
            score += 10_000
        best = max(best, score)
    return best


def _part_names_overlap(source_key: str, part_value: str) -> bool:
    """Match a declared source_part to a parts row by bounded semantic tokens."""

    return _part_match_score([source_key], part_value) > 0


def _part_source_keys(box: Mapping[str, Any]) -> list[str]:
    """Part names a panel binds to; source_part may list slash-separated synonyms."""

    raw = meaningful(str(box.get("source_part", "")))
    if not raw:
        return []
    keys: list[str] = []
    for token in re.split(r"[/,]", raw):
        key = meaningful(token).casefold()
        if key:
            keys.append(key)
    return keys


def color_rows(sheet: Mapping[str, Any]) -> list[dict[str, str]]:
    rows = []
    for row in table_values(sheet, "colors"):
        zone = meaningful(row.get("zone", ""))
        base = meaningful(row.get("base", "") or row.get("zonebase", ""))
        shadow = meaningful(row.get("shadow", ""))
        highlight = meaningful(row.get("highlight", ""))
        if zone or any(HEX_RE.fullmatch(value) for value in (base, shadow, highlight)):
            rows.append(
                {
                    "zone": zone,
                    "base": base,
                    "shadow": shadow,
                    "highlight": highlight,
                    "binding": meaningful(row.get("binding", "")),
                }
            )
    return rows


# The panel set is resolved, not authored in full: the layout profile is the
# design baseline, and the declared state rows in sheet-data complete it. Each
# kind below covers one sheet-data state table, and every declared visual row
# gets a same-kind panel frame as part of the sheet's initial state, with no
# hand-editing of profile JSON. Resolved panels bind through persistent
# source_row_id (source_index is profile authoring metadata only), then pick up the
# row's label and drawing details from apply_sheet_context, so coverage holds by
# construction.
STATE_PANEL_SOURCES = {
    "mark_detail": ("marks", COVERAGE_MARK_COLUMNS),
    "part_detail": ("parts", COVERAGE_PART_COLUMNS),
    "expression_variant": ("expressions", COVERAGE_EXPRESSION_COLUMNS),
    "pose_state": ("bodylang", COVERAGE_POSE_COLUMNS),
    "items": ("items", COVERAGE_ITEM_COLUMNS),
    "evidence_view": ("evidence", COVERAGE_EVIDENCE_COLUMNS),
    "outfit_variant": ("outfits", COVERAGE_OUTFIT_COLUMNS),
    "part_state": ("partstates", COVERAGE_PART_STATE_COLUMNS),
    "range_of_motion": ("motion", COVERAGE_MOTION_COLUMNS),
    "action_pose": ("actions", COVERAGE_ACTION_COLUMNS),
    "idle_gesture": ("gestures", COVERAGE_GESTURE_COLUMNS),
}
# Kinds whose rows describe how the identity moves rather than what it is.
PERFORMANCE_SERIES_KINDS = ("part_state", "range_of_motion", "action_pose", "idle_gesture")
