"""Text measurement, CJK raster text collection, and SVG text emission."""
from __future__ import annotations

import base64
import functools
import html
import io
import os
import shutil
import subprocess
import textwrap
import unicodedata
from pathlib import Path
from typing import Any, Mapping, Sequence

from character_sheet_render.sheetdata import sha256_file


INK = "#26221c"
PAPER = "#f5f2ec"
PANEL = "#ffffff"
MUTED = "#6b6458"
SOFT = "#ece7dd"
DISABLED = "#f1eee8"
SCAFFOLD_GUIDE = "#b3261e"
REFERENCE_GUIDE = "#e9eef1"
FONT_FAMILY = (
    "'Noto Sans CJK JP', 'Noto Sans CJK KR', 'Noto Sans CJK SC', 'Noto Sans JP', "
    "'BIZ UDPGothic', 'Yu Gothic UI', 'Yu Gothic', Meiryo, 'Malgun Gothic', "
    "'Microsoft YaHei', 'Apple SD Gothic Neo', 'PingFang SC', 'DejaVu Sans', sans-serif"
)
_RASTER_TEXT_OVERLAYS: list[dict[str, Any]] | None = None


def begin_raster_text_collection() -> None:
    """Start collecting CJK raster text overlays for one render pass."""

    global _RASTER_TEXT_OVERLAYS
    _RASTER_TEXT_OVERLAYS = []


def take_raster_text_overlays() -> list[dict[str, Any]]:
    """Return every collected CJK raster overlay and reset the collector."""

    global _RASTER_TEXT_OVERLAYS
    overlays = _RASTER_TEXT_OVERLAYS if _RASTER_TEXT_OVERLAYS is not None else []
    _RASTER_TEXT_OVERLAYS = None
    return overlays


def contains_cjk(value: str) -> bool:
    """Return whether text needs an explicitly loaded CJK-capable raster font."""

    return any(
        "\u1100" <= character <= "\u11ff"
        or "\u2e80" <= character <= "\u9fff"
        or "\ua960" <= character <= "\ua97f"
        or "\uac00" <= character <= "\ud7ff"
        or "\uf900" <= character <= "\ufaff"
        or "\ufe30" <= character <= "\ufe4f"
        or "\uff00" <= character <= "\uffef"
        or "\U00020000" <= character <= "\U0003ffff"
        for character in value
    )


def raster_font_role(weight: str) -> str:
    try:
        return "bold" if int(weight) >= 600 else "regular"
    except (TypeError, ValueError):
        return "bold" if str(weight).lower() in {"bold", "bolder"} else "regular"


def cjk_font_candidates(role: str) -> list[Path]:
    """Candidate font files in preference order.

    Pan-CJK families come first, then the single-script families each
    platform ships. A run of text is printed by the first file that has
    every glyph it needs.
    """

    windows_dir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    windows_fonts = windows_dir / "Fonts"
    if role == "bold":
        windows_names = (
            "NotoSansCJK-Bold.ttc",
            "NotoSansCJKjp-Bold.otf",
            "SourceHanSans-Bold.ttc",
            "NotoSansJP-VF.ttf",
            "NotoSansJP-Bold.ttf",
            "BIZ-UDGothicB.ttc",
            "meiryob.ttc",
            "YuGothB.ttc",
            "malgunbd.ttf",
            "msyhbd.ttc",
            "msjhbd.ttc",
        )
        unix_names = (
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
            "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
            "/System/Library/Fonts/AppleSDGothicNeo.ttc",
            "/System/Library/Fonts/PingFang.ttc",
        )
    else:
        windows_names = (
            "NotoSansCJK-Regular.ttc",
            "NotoSansCJKjp-Regular.otf",
            "SourceHanSans-Regular.ttc",
            "NotoSansJP-VF.ttf",
            "NotoSansJP-Regular.ttf",
            "BIZ-UDGothicR.ttc",
            "meiryo.ttc",
            "YuGothR.ttc",
            "msgothic.ttc",
            "malgun.ttf",
            "msyh.ttc",
            "msjh.ttc",
            "simsun.ttc",
            "mingliu.ttc",
        )
        unix_names = (
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
            "/System/Library/Fonts/AppleSDGothicNeo.ttc",
            "/System/Library/Fonts/PingFang.ttc",
        )
    return [windows_fonts / name for name in windows_names] + [
        Path(name) for name in unix_names
    ]


FONTCONFIG_LANGUAGES = ("ja", "ko", "zh-cn", "zh-tw")


@functools.lru_cache(maxsize=None)
def fontconfig_cjk_font_files(role: str) -> tuple[Path, ...]:
    """Font files fontconfig lists for CJK text at the role's weight.

    Japanese fonts come first, then Korean, Simplified and Traditional
    Chinese, each language's files in path order. Without fc-list the list
    is empty.
    """

    fc_list = shutil.which("fc-list")
    if fc_list is None:
        return ()
    weight = "bold" if role == "bold" else "regular"
    files: list[Path] = []
    for language in FONTCONFIG_LANGUAGES:
        try:
            listed = subprocess.run(
                [fc_list, "--format", "%{file}\\n", f":lang={language}:weight={weight}"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
        except OSError:
            break
        for line in sorted({line.strip() for line in listed.stdout.splitlines()} - {""}):
            if Path(line) not in files:
                files.append(Path(line))
    return tuple(files)


_PROBE_FONTS: dict[Path, Any] = {}
_GLYPH_COVERAGE: dict[tuple[Path, str], bool] = {}


def _probe_font(path: Path) -> Any:
    from PIL import ImageFont

    if path not in _PROBE_FONTS:
        _PROBE_FONTS[path] = ImageFont.truetype(str(path), 16)
    return _PROBE_FONTS[path]


def _loadable(candidates: Sequence[Path]) -> list[Path]:
    usable: list[Path] = []
    for candidate in candidates:
        if not candidate.is_file():
            continue
        try:
            _probe_font(candidate)
        except OSError:
            continue
        usable.append(candidate)
    return usable


def usable_cjk_font_files(role: str) -> list[Path]:
    """The font files that exist and load, in preference order.

    The known paths come first. When none of them loads, fontconfig names
    the installed CJK fonts, wherever the distribution put them.
    """

    return _loadable(cjk_font_candidates(role)) or _loadable(fontconfig_cjk_font_files(role))


def font_has_glyph(path: Path, character: str) -> bool:
    """Whether the font file prints the character with a glyph of its own.

    A code point the font does not map renders as its missing-glyph box, the
    same image a noncharacter such as U+FFFE renders as. A character whose
    image differs from that box has a real glyph.
    """

    key = (path, character)
    if key not in _GLYPH_COVERAGE:
        font = _probe_font(path)
        missing = bytes(font.getmask("\ufffe"))
        _GLYPH_COVERAGE[key] = bytes(font.getmask(character)) != missing
    return _GLYPH_COVERAGE[key]


def segment_text_by_font(role: str, text: str) -> list[tuple[Path, str]]:
    """Split text into runs, each with the first font file that prints all of it.

    Latin text stays with the font of the run around it. A character that no
    installed font prints raises, naming the character and the files tried,
    so a missing platform font surfaces as an error rather than as a
    replacement box in the sheet.
    """

    usable = usable_cjk_font_files(role)
    if not usable:
        raise RuntimeError(
            "CJK text is declared but no usable CJK font file was found for "
            f"the {role} raster text layer"
        )
    runs: list[tuple[Path, str]] = []
    current: Path | None = None
    for character in text:
        if contains_cjk(character) and not character.isspace():
            if current is not None and font_has_glyph(current, character):
                chosen = current
            else:
                chosen = next(
                    (path for path in usable if font_has_glyph(path, character)),
                    None,
                )
            if chosen is None:
                tried = ", ".join(path.name for path in usable)
                raise RuntimeError(
                    f"no installed CJK font prints {character!r} "
                    f"(U+{ord(character):04X}); tried {tried}"
                )
        else:
            chosen = current if current is not None else usable[0]
        if runs and runs[-1][0] == chosen:
            runs[-1] = (chosen, runs[-1][1] + character)
        else:
            runs.append((chosen, character))
        current = chosen
    if len(runs) > 1 and not contains_cjk(runs[0][1]):
        # Leading Latin text joins the font of the first CJK run.
        runs[1] = (runs[1][0], runs[0][1] + runs[1][1])
        del runs[0]
    return runs


def resolve_cjk_fonts(overlays: Sequence[Mapping[str, Any]]) -> dict[str, Path]:
    """Every font file the overlays print with, keyed by file stem."""

    resolved: dict[str, Path] = {}
    for overlay in overlays:
        for path, _ in segment_text_by_font(
            str(overlay["font_role"]), str(overlay["text"])
        ):
            resolved[path.stem] = path
    return resolved


def build_raster_text_layer(
    *, width: int, height: int, overlays: Sequence[Mapping[str, Any]]
) -> tuple[str, dict[str, Any]]:
    """Render CJK text with an explicit font file and return an SVG image layer."""

    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    fonts: dict[str, Path] = {}
    loaded_fonts: dict[tuple[Path, int], Any] = {}
    printed: list[dict[str, Any]] = []
    for overlay in overlays:
        role = str(overlay["font_role"])
        size = int(overlay["size"])
        runs = segment_text_by_font(role, str(overlay["text"]))
        for path, _ in runs:
            fonts[path.stem] = path
            if (path, size) not in loaded_fonts:
                loaded_fonts[(path, size)] = ImageFont.truetype(str(path), size)
        advances = [
            loaded_fonts[(path, size)].getlength(segment) for path, segment in runs
        ]
        x = float(overlay["x"])
        anchor = str(overlay["anchor"])
        if anchor == "middle":
            x -= sum(advances) / 2
        elif anchor == "end":
            x -= sum(advances)
        for (path, segment), advance in zip(runs, advances):
            draw.text(
                (x, float(overlay["y"])),
                segment,
                font=loaded_fonts[(path, size)],
                fill=str(overlay["fill"]),
                anchor="ls",
            )
            x += advance
        printed.append({**overlay, "fonts": [path.stem for path, _ in runs]})
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    manifest = {
        "engine": "Pillow explicit-font raster layer embedded in SVG",
        "fonts": {
            stem: {
                "semantic_id": stem,
                "file_name": path.name,
                "sha256": sha256_file(path),
            }
            for stem, path in sorted(fonts.items())
        },
        "overlays": printed,
    }
    return f"data:image/png;base64,{encoded}", manifest


LATIN_TEXT_UNIT = 0.62
FULLWIDTH_TEXT_UNIT = 1.0


def estimated_text_units(value: str) -> float:
    """Estimate rendered advance width in em-weighted units.

    Full-width East Asian glyphs advance about one em per character, so a
    plain per-character count under-estimates CJK wording by nearly a half.
    Latin glyphs average about 0.62 em. Zero-width combining marks count for
    nothing.
    """
    units = 0.0
    for character in value:
        if unicodedata.combining(character):
            continue
        if unicodedata.east_asian_width(character) in ("W", "F"):
            units += FULLWIDTH_TEXT_UNIT
        else:
            units += LATIN_TEXT_UNIT
    return units


def contains_fullwidth_glyphs(value: str) -> bool:
    """Whether the text needs mid-run breaking to fit a fixed pixel width."""

    return any(
        unicodedata.east_asian_width(character) in ("W", "F")
        for character in value
    )


def wrap_lines(value: str, *, width_px: int, font_size: int, max_lines: int) -> list[str]:
    """Wrap complete text and reject any layout that would omit a line."""

    value = " ".join(value.split())
    if not value:
        return []
    average_unit = estimated_text_units(value) / max(1, len(value))
    characters = max(8, int(width_px / max(1.0, font_size * average_unit)))
    lines = textwrap.wrap(
        value,
        width=characters,
        break_long_words=contains_fullwidth_glyphs(value),
        break_on_hyphens=True,
    )
    if len(lines) > max_lines:
        raise ValueError(
            f"text does not fit without omission at {font_size}px in "
            f"{width_px}px x {max_lines} lines: {value!r}"
        )
    return lines


def fit_wrapped_text(
    value: str,
    *,
    width_px: int,
    base_size: int,
    available_height: int,
    minimum_size: int = 9,
) -> tuple[int, list[str], int]:
    """Shrink text and grow the line count until the full wording fits.

    Returns (font_size, lines, line_height). Model-facing wording is never
    clipped or elided; if the complete value cannot fit at the minimum size,
    rendering fails with a precise error.
    """
    normalized = " ".join(value.split())
    size = base_size
    while True:
        line_height = size + 3
        max_lines = max(1, available_height // line_height)
        average_unit = estimated_text_units(normalized) / max(1, len(normalized))
        characters = max(8, int(width_px / max(1.0, size * average_unit)))
        lines = textwrap.wrap(
            normalized,
            width=characters,
            break_long_words=contains_fullwidth_glyphs(normalized),
            break_on_hyphens=True,
        )
        if len(lines) <= max_lines:
            return size, lines, line_height
        if size <= minimum_size:
            raise ValueError(
                f"text does not fit without omission at minimum {minimum_size}px "
                f"in {width_px}px x {available_height}px: {normalized!r}"
            )
        size -= 1


def fit_title_size(value: str, width_px: int, base_size: int, minimum_size: int = 10) -> int:
    """Pick the largest header font size whose estimated width fits the band."""
    size = base_size
    while size > minimum_size and estimated_text_units(value) * size > width_px:
        size -= 1
    return size


def make_svg_text(
    svg: list[str],
    x: float,
    y: float,
    value: Any,
    size: int,
    *,
    anchor: str = "start",
    weight: str = "700",
    fill: str = INK,
) -> None:
    text = str(value)
    if contains_cjk(text):
        if _RASTER_TEXT_OVERLAYS is None:
            raise RuntimeError("CJK raster text collection was not initialized")
        _RASTER_TEXT_OVERLAYS.append(
            {
                "x": x,
                "y": y,
                "text": text,
                "size": size,
                "anchor": anchor,
                "weight": weight,
                "font_role": raster_font_role(weight),
                "fill": fill,
            }
        )
        return
    svg.append(
        f'<text x="{x}" y="{y}" font-family="{FONT_FAMILY}" '
        f'font-size="{size}" font-weight="{weight}" fill="{fill}" '
        f'text-anchor="{anchor}">{html.escape(text)}</text>'
    )


def make_wrapped_svg_text(
    svg: list[str],
    x: float,
    y: float,
    value: str,
    size: int,
    *,
    width_px: int,
    max_lines: int,
    line_height: int,
    anchor: str = "middle",
    weight: str = "400",
    fill: str = MUTED,
) -> None:
    lines = wrap_lines(value, width_px=width_px, font_size=size, max_lines=max_lines)
    if not lines:
        return
    for index, line in enumerate(lines):
        make_svg_text(
            svg,
            x,
            y + index * line_height,
            line,
            size,
            anchor=anchor,
            weight=weight,
            fill=fill,
        )
