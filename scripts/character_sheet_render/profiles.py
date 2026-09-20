"""Layout profile library, selection, semantic validation, and geometry."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from state_protocol import validate_against_schema

from character_sheet_render.sheetdata import ROOT, load_json_object, meaningful


DEFAULT_PROFILE_PATH = ROOT / "templates" / "character-sheet-layout.humanoid.json"
ANTHRO_PROFILE_PATH = ROOT / "templates" / "character-sheet-layout.anthro.json"
GENERAL_PROFILE_PATH = ROOT / "templates" / "character-sheet-layout.general.json"
PROFILE_SCHEMA_PATH = ROOT / "schemas" / "character-sheet-render-profile.schema.json"
PROFILE_LIBRARY_DIR = ROOT / "templates"
BORDER = 4
HEADER_HEIGHT = 48
DEFAULT_FOOTER_HEIGHT = 62
ROW_GAP = 22
SIDE_MARGIN = 40
PANEL_GAP = 18
MIN_PANEL_WIDTH = 180
SECTION_HEADER_HEIGHT = 42
# The scaffold canvas grows in both dimensions to hold resolved state panels.
# The sheet composes as a landscape board: once the resolved rows would make
# it taller than wide, the canvas widens until the width covers the height.
ASPECT_LIMIT = 1.0
# Every panel is a drawing surface holding exactly one drawing, so its shape
# must fit what that kind draws: full-body views and poses draw well portrait,
# head and close-up studies draw well square, a tail or an item row draws well
# wide. Each kind declares that shape as a width-to-height aspect, and the
# renderer sizes every panel to aspect x row height. Widening the canvas adds
# columns or centers rows; it never stretches a panel past its kind's shape.
KIND_PANEL_ASPECT = {
    "canonical_view": 0.7,
    "outfit_turnaround": 0.7,
    "outfit": 0.7,
    "outfit_detail": 1.6,
    "signature_pose": 0.7,
    # A pose panel must have enough vertical drawing area for an unchanged
    # standing figure. A wider frame caused image models to bend or crouch the
    # subject merely to fit the box. Horizontal bodies still fit by scaling the
    # complete figure down; the renderer must not imply a posture change.
    "pose_state": 0.5,
    "outfit_variant": 0.7,
    "head_study": 0.95,
    "part_detail": 1.0,
    "icon": 1.0,
    "expression_variant": 1.0,
    "mark_detail": 1.0,
    "tail_detail": 1.4,
    "items": 1.6,
    "size_reference": 0.8,
    # A part in one state, or a region at both ends of its range, reads as a
    # wide study; a figure mid-action or in an everyday gesture needs width
    # for reach and props without losing standing height.
    "part_state": 1.4,
    "range_of_motion": 1.5,
    "action_pose": 0.85,
    "idle_gesture": 0.8,
}
RESOLVED_ROW_HEIGHT = 560
# The panel a model draws is not the box on the board. The box shows a reduced
# copy; the panel itself is generated at this long side unless the profile or
# the box says otherwise.
DEFAULT_PANEL_LONG_SIDE = 2048
# A drawing row is scaled up until its panels span the canvas width, so a row of
# three figures on a wide board is three large figures rather than three small
# ones between margins. The cap keeps a one-panel row from becoming a page.
MAX_ROW_FILL_SCALE = 2.5
PALETTE_CELL_MIN_HEIGHT = 110
SCAFFOLD_TOP_OF_ROWS = 330
REFERENCE_TOP_OF_ROWS = 232
BOTTOM_MARGIN = 40
FILL_POLICIES = frozenset({"auto", "fill", "keep", "skip"})
REFERENCE_ROLES = frozenset({"identity", "performance", "support"})


def load_profile(path: Path) -> dict[str, Any]:
    profile = load_json_object(path, label="character sheet render profile")
    schema = load_json_object(PROFILE_SCHEMA_PATH, label="render profile schema")
    errors = validate_against_schema(profile, schema)
    if errors:
        raise ValueError("invalid character sheet render profile: " + "; ".join(errors))
    validate_profile_semantics(profile)
    return profile


def available_profiles() -> list[Path]:
    return sorted(PROFILE_LIBRARY_DIR.glob("character-sheet-layout.*.json"))


def resolve_profile_reference(reference: str, *, sheet_dir: Path | None = None) -> Path:
    """Resolve a declared profile id (``anthro``) or path to a profile file.

    Paths are tried relative to the sheet folder first, then the working
    directory, then the skill root; bare ids resolve inside the bundled
    profile library.
    """

    candidate = Path(reference).expanduser()
    if candidate.suffix != ".json":
        return PROFILE_LIBRARY_DIR / f"character-sheet-layout.{reference}.json"
    if candidate.is_absolute():
        return candidate
    for base in (sheet_dir, Path.cwd(), ROOT):
        if base is None:
            continue
        merged = base / candidate
        if merged.is_file():
            return merged
    return candidate


def select_profile_path(
    sheet: Mapping[str, Any],
    explicit_path: Path | None,
    *,
    sheet_dir: Path | None = None,
) -> tuple[Path, dict[str, str]]:
    """Resolve the layout profile this character's sheet declares, never improvised.

    The agent designs the panel set from the character definition: which views,
    close-ups, marks, items, and expressions this individual actually needs,
    and records that design as a layout profile: either a bundled profile id in
    ``field.sheet_layout_profile`` or a path to the character's own authored
    profile JSON. The renderer only resolves that declaration; ``--profile``
    overrides it, and an undeclared profile falls back to the bundled
    domain-neutral baseline. The reason is recorded in render-package.json.
    """

    if explicit_path is not None:
        declared = str(Path(explicit_path).expanduser())
        candidate = resolve_profile_reference(declared, sheet_dir=sheet_dir)
        if not candidate.is_file():
            names = ", ".join(
                path.stem.removeprefix("character-sheet-layout.")
                for path in available_profiles()
            )
            raise ValueError(
                "--profile names an unknown layout profile "
                f"{declared!r}; bundled profiles: {names} (a path to an authored "
                "profile JSON may also be supplied)"
            )
        return candidate, {
            "method": "explicit-argument",
            "reason": "caller supplied --profile " f"{declared!r}",
        }
    fields = sheet.get("fields") if isinstance(sheet.get("fields"), Mapping) else {}
    declared = meaningful(fields.get("field.sheet_layout_profile", ""))
    if declared:
        candidate = resolve_profile_reference(declared, sheet_dir=sheet_dir)
        if not candidate.is_file():
            names = ", ".join(
                path.stem.removeprefix("character-sheet-layout.")
                for path in available_profiles()
            )
            raise ValueError(
                "field.sheet_layout_profile names an unknown layout profile "
                f"{declared!r}; bundled profiles: {names} (a path to an authored "
                "profile JSON may also be declared)"
            )
        return candidate, {
            "method": "sheet-field",
            "reason": "sheet-data.json field.sheet_layout_profile declares "
            f"{declared!r}",
        }
    return GENERAL_PROFILE_PATH, {
        "method": "default",
        "reason": "field.sheet_layout_profile is not declared; using the bundled "
        "domain-neutral general profile",
    }


def validate_profile_semantics(profile: Mapping[str, Any]) -> None:
    width, height = profile["canvas"]
    required_height = SCAFFOLD_TOP_OF_ROWS + sum(row["height"] for row in profile["rows"])
    required_height += ROW_GAP * max(0, len(profile["rows"]) - 1) + BOTTOM_MARGIN
    if required_height > height:
        raise ValueError(
            "render profile rows do not fit the declared scaffold canvas: "
            f"requires at least {required_height}px, canvas is {height}px"
        )
    if width <= SIDE_MARGIN * 2:
        raise ValueError("render profile canvas is too narrow for fixed side margins")

    primary_ids: set[str] = set()
    known_ids: set[str] = set()
    output_names: set[str] = set()
    panel_codes: set[str] = set()
    for row_index, row in enumerate(profile["rows"]):
        boxes = row["boxes"]
        for box_index, box in enumerate(boxes):
            slot_id = box["slot_id"]
            if slot_id in known_ids:
                raise ValueError(f"render profile contains duplicate slot_id {slot_id!r}")
            primary_ids.add(slot_id)
            known_ids.add(slot_id)
            for alias in box.get("aliases", []):
                if alias in known_ids:
                    raise ValueError(f"render profile contains duplicate slot alias {alias!r}")
                known_ids.add(alias)
            panel_code = box.get("panel_code", "")
            if panel_code:
                if panel_code in panel_codes:
                    raise ValueError(f"render profile contains duplicate panel_code {panel_code!r}")
                panel_codes.add(panel_code)
            role = box.get("reference_role", "identity")
            if role not in REFERENCE_ROLES:
                raise ValueError(
                    f"render profile panel {slot_id} has unsupported reference_role {role!r}"
                )
            policy = box.get("default_fill_policy", "auto")
            if policy not in FILL_POLICIES:
                raise ValueError(
                    f"render profile panel {slot_id} has unsupported default_fill_policy {policy!r}"
                )
            output_name = box.get("output_name")
            if box.get("kind") not in {"palette", "profile"} and not output_name:
                raise ValueError(
                    f"render profile row {row_index + 1} panel {box_index + 1} "
                    "must declare output_name for deterministic harvesting"
                )
            if output_name:
                if output_name in output_names:
                    raise ValueError(f"render profile contains duplicate output_name {output_name!r}")
                output_names.add(output_name)

        # Enforce the section-label drawable-height rule at load time so an
        # authoring mistake fails here instead of crashing mid-render.
        row_panel_height(row)

        # Renderer-owned palette/profile strips draw at the full canvas inner
        # width wherever they sit in a row. Any drawing panel beside one
        # starts beyond the right margin, and a second strip would too; the
        # render canvas only grows wide enough for drawing-only rows
        # (row_natural_width ignores the strips), so this mixing cannot be
        # saved by a wider canvas and must fail here instead of silently
        # rendering panels off the canvas.
        strip_boxes = [
            box for box in boxes if box.get("kind") in {"palette", "profile"}
        ]
        drawing_boxes = [
            box for box in boxes if box.get("kind") not in {"palette", "profile"}
        ]
        if strip_boxes and (len(strip_boxes) > 1 or drawing_boxes):
            overflow = [str(box.get("slot_id", "<unnamed>")) for box in strip_boxes[1:]]
            overflow.extend(str(box.get("slot_id", "<unnamed>")) for box in drawing_boxes)
            raise ValueError(
                "render profile row mixes renderer-owned palette/profile strips with "
                "panels that would overflow the canvas: " + ", ".join(overflow)
                + "; each strip alone already consumes the entire row width, so a "
                "strip row must contain exactly one strip and no drawing panels"
            )


def row_panel_height(row: Mapping[str, Any]) -> int:
    """Drawable panel height after an optional visual section heading."""

    height = int(row["height"])
    if meaningful(str(row.get("section_label", ""))):
        height -= SECTION_HEADER_HEIGHT
    if height < 120:
        raise ValueError("render profile row leaves less than 120px below its section label")
    return height


def desired_panel_width(box: Mapping[str, Any], row_height: int) -> int:
    """Width a panel of this kind draws well at for the given row height."""

    if box.get("kind") == "palette":
        return 0  # the palette is a full-width key strip, not a drawing frame
    aspect = KIND_PANEL_ASPECT.get(str(box.get("kind", "drawing")), 1.0)
    return max(MIN_PANEL_WIDTH, round(aspect * row_height))


def parse_panel_geometries(text: str) -> list[tuple[int, int]]:
    """Read a target's geometry set written as WIDTHxHEIGHT values separated by commas or spaces."""

    geometries: list[tuple[int, int]] = []
    for token in text.replace(",", " ").split():
        width_text, separator, height_text = token.lower().partition("x")
        if not separator or not width_text.isdigit() or not height_text.isdigit():
            raise ValueError(f"panel geometry must be WIDTHxHEIGHT: {token!r}")
        geometry = (int(width_text), int(height_text))
        if min(geometry) < 1:
            raise ValueError(f"panel geometry must be positive: {token!r}")
        if geometry not in geometries:
            geometries.append(geometry)
    if not geometries:
        raise ValueError("panel geometries must name at least one WIDTHxHEIGHT value")
    return geometries


def panel_generation_size(
    profile: Mapping[str, Any],
    box: Mapping[str, Any],
    content_size: tuple[int, int],
    geometries: Sequence[tuple[int, int]] | None = None,
) -> tuple[int, int]:
    """Pixel size the model is asked for.

    Without a geometry set this is the box's aspect at the declared long side.
    With one, it is the target's geometry whose aspect is nearest the box's,
    the larger one when two are equally near, because a target that offers a
    fixed set of sizes returns one of them whatever the prompt asks for.
    """

    width, height = content_size
    if width <= 0 or height <= 0:
        raise ValueError(f"panel {box.get('slot_id')} has no drawable content area")
    if geometries:
        wanted = math.log(width / height)
        return min(
            geometries,
            key=lambda geometry: (
                abs(math.log(geometry[0] / geometry[1]) - wanted),
                -(geometry[0] * geometry[1]),
            ),
        )
    long_side = int(box.get("long_side") or profile.get("panel_long_side") or DEFAULT_PANEL_LONG_SIDE)
    if width >= height:
        return long_side, max(1, round(long_side * height / width))
    return max(1, round(long_side * width / height)), long_side


def fill_rows_to_width(rows: list[dict[str, Any]], width: int) -> None:
    """Scale each drawing row's height so its panels span the canvas width.

    Panels keep their kind aspect, so widening a row means making it taller.
    Renderer-owned strips already span the width and are left alone, and a
    row that is wider than the canvas is not shrunk here.
    """

    available = width - SIDE_MARGIN * 2
    for row in rows:
        boxes = row["boxes"]
        if any(box.get("kind") in {"palette", "profile"} for box in boxes):
            continue
        # The scale is taken from the row as authored, not from the row as last
        # scaled, so calling this again for a wider canvas re-derives the height
        # instead of compounding it.
        if "_authored_panel_height" not in row:
            row["_authored_panel_height"] = row_panel_height(row)
            row["_chrome_height"] = int(row["height"]) - row["_authored_panel_height"]
        authored_height = int(row["_authored_panel_height"])
        natural = sum(desired_panel_width(box, authored_height) for box in boxes)
        natural += PANEL_GAP * max(0, len(boxes) - 1)
        if natural <= 0:
            continue
        scale = max(1.0, min(MAX_ROW_FILL_SCALE, available / natural))
        row["height"] = int(row["_chrome_height"]) + int(round(authored_height * scale))


def row_natural_width(row: Mapping[str, Any]) -> int:
    """Total width a row's panels occupy at their kind-appropriate shapes."""

    boxes = row["boxes"]
    panel_height = row_panel_height(row)
    inner = sum(
        desired_panel_width(box, panel_height) for box in boxes
    )
    return inner + PANEL_GAP * max(0, len(boxes) - 1)
