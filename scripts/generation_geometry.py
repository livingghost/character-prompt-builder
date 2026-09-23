#!/usr/bin/env python3
"""Settle the delivery geometry for a model record: the sizes it declares, and what a ratio it does not declare comes to.

Usage:
  python scripts/generation_geometry.py --model <model-id> --list
  python scripts/generation_geometry.py --model <model-id> --ratio 2:3
  python scripts/generation_geometry.py --model <model-id> --width 832 --height 1216
      [--service ID] [--multiple N] [--pixels N]
      [--state-file PATH --cache-dir DIR --managed-root DIR [--pack-root DIR]]

Sizes in a record are declared choices, not proof of a model's training
resolution. A matching declared ratio uses that recorded choice. For other
ratios, a pixel budget is either explicitly supplied or proposed from the median
of the record's declared areas. That proposal is not a universal quality limit.

An undeclared ratio needs an explicit positive --multiple: this tool does not
assume every model uses an 8-pixel latent grid. Copy the grid requirement from
the applicable model/service contract, or explicitly choose 1 for integer pixels.

Every answer is then put to the service's observed parameter schema, when the
record's offering points at one, so a size is refused here rather than by the
service. The size goes on the keys the offering's request_keys give it: a
width and a height, or one size text that the offering's size_format writes.
An aspect ratio in that text is the one requested or declared, not the sides
reduced. Only the size is judged; the rest of the request is the package's
business. An offering that records no size key leaves the size unchecked, and
the report's size_fields is null.

Output is JSON on stdout. The exit status is 1 when a size is refused.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from catalog_retrieval.runtime import configure_pack_runtime  # noqa: E402
from model_contract import offering_schema, request_instance, select_offering, size_fields  # noqa: E402
from pack_runtime_cli import add_pack_runtime_arguments, resolve_pack_runtime  # noqa: E402
from prepare_generation_references import model_pack_root, resolve_model_record  # noqa: E402

SIZE = re.compile(r"([1-9]\d*)\s*[x×]\s*([1-9]\d*)")
RATIO = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*[:x/]\s*(\d+(?:\.\d+)?)\s*$")
# A stand-in for the text the package carries, so that a schema which requires a
# prompt is answered about the geometry rather than about the missing prompt.
PROBE_PROMPT = "a character"


def declared_sizes(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Every width and height the record declares, with the ratio key it sat under."""

    rows: list[dict[str, Any]] = []
    for key, value in (record.get("size_hints") or {}).items():
        for width, height in SIZE.findall(str(value)):
            rows.append({"declared_under": key, "width": int(width), "height": int(height),
                         "pixels": int(width) * int(height), "ratio": simplify(int(width), int(height))})
    return rows


def simplify(width: int, height: int) -> str:
    divisor = math.gcd(width, height)
    return f"{width // divisor}:{height // divisor}"


def parse_ratio(text: str) -> float:
    found = RATIO.match(text)
    if not found:
        raise SystemExit(f"--ratio must be written as width:height, such as 2:3, not {text!r}")
    width, height = float(found.group(1)), float(found.group(2))
    if width <= 0 or height <= 0:
        raise SystemExit("--ratio must have two positive sides")
    return width / height


def budget_of(sizes: list[dict[str, Any]]) -> int:
    counts = sorted(row["pixels"] for row in sizes)
    middle = len(counts) // 2
    return counts[middle] if len(counts) % 2 else (counts[middle - 1] + counts[middle]) // 2


def resolve(ratio: float, pixels: int, multiple: int) -> tuple[int, int]:
    """The width and height nearest that pixel count at that ratio, each a multiple of the step."""

    # The height comes from the untrimmed width, so that trimming both sides to
    # the step lands on the ratio rather than drifting away from it.
    untrimmed_width = int(math.sqrt(pixels * ratio))
    if untrimmed_width < 1:
        raise SystemExit(f"a ratio of {ratio:.4f} at {pixels} pixels leaves no width at all")
    untrimmed_height = int(pixels / untrimmed_width)
    width = untrimmed_width - untrimmed_width % multiple
    height = untrimmed_height - untrimmed_height % multiple
    if width < multiple or height < multiple:
        raise SystemExit(
            f"a ratio of {ratio:.4f} at {pixels} pixels leaves no side that is a multiple of {multiple}"
        )
    return width, height


def ratio_sides(text: str | None) -> tuple[str, str] | None:
    """The two numbers of a ratio label as written, such as ("2", "3"), or None for text that is no ratio."""

    found = RATIO.match(text or "")
    return (found.group(1), found.group(2)) if found else None


def schema_refusals(record: dict[str, Any], service: str | None, model_id: str, width: int, height: int,
                    pack_root: Path | None, ratio: tuple[str, str] | None = None
                    ) -> tuple[list[str], dict[str, Any] | None]:
    """What the service's observed parameter schema says about this size, on the keys the offering gives it."""

    offering = select_offering(record, service)
    if offering is None:
        return [], None
    fields = size_fields(offering, width, height, ratio)
    found = offering_schema(offering, pack_root if pack_root is not None else model_pack_root(model_id))
    summary = {"service": offering["service"], "model_identifier": offering["model_identifier"],
               "observed_at": offering.get("observed_at"), "size_fields": fields}
    if found is None or fields is None:
        return [], summary
    from state_protocol import validate_against_schema

    # A service that takes its sizes in buckets writes the condition over the pair
    # rather than over either side, so one side at a time cannot read it. The
    # request is put to the schema twice, once carrying the size and once without
    # it, and only what the size adds is a refusal of the size: what the probe is
    # missing otherwise is the package's business and is subtracted here.
    sized = request_instance(offering, fields, prompt=PROBE_PROMPT)
    unsized = request_instance(offering, {}, prompt=PROBE_PROMPT)
    without = set(validate_against_schema(unsized, found["schema"]))
    named = {f"$.{key}": f"{key} {value}" for key, value in fields.items()}
    refusals: list[str] = []
    for message in validate_against_schema(sized, found["schema"]):
        if message in without:
            continue
        where, separator, detail = message.partition(": ")
        if not separator:
            where, detail = "", message
        refusals.append(f"{named.get(where, f'{width}x{height}')}: {detail}")
    return sorted(dict.fromkeys(refusals)), summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--model", required=True, help="A model record in the active pack runtime")
    parser.add_argument("--service", help="The service, when the record is exposed on more than one")
    parser.add_argument("--list", action="store_true", help="Print the sizes the record declares")
    parser.add_argument("--ratio", help="A ratio written as width:height, such as 2:3")
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--multiple", type=int, help="Explicit pixel grid for a ratio not declared by the record; no model-family default")
    parser.add_argument("--pixels", type=int, help="The pixel count to resolve at, instead of the record's own")
    add_pack_runtime_arguments(parser)
    args = parser.parse_args(argv)
    if args.multiple is not None and args.multiple < 1:
        parser.error("--multiple must be at least 1")
    if (args.width is None) != (args.height is None):
        parser.error("--width and --height go together")
    if not args.list and args.ratio is None and args.width is None:
        parser.error("one of --list, --ratio, or --width with --height")
    configure_pack_runtime(resolve_pack_runtime(parser, args).settings)
    try:
        return settle(parser, args)
    finally:
        configure_pack_runtime(None)


def settle(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    model_id, record = resolve_model_record(args.model)
    sizes = declared_sizes(record)
    if args.list and args.ratio is None and args.width is None:
        print(json.dumps({"model": model_id, "declared_sizes": sizes,
                          "pixel_budget": budget_of(sizes) if sizes else None}, ensure_ascii=False, indent=2))
        return 0

    if args.width is not None and (args.width < 1 or args.height < 1):
        parser.error("width and height must be positive")
    if args.pixels is not None and args.pixels < 1:
        parser.error("pixels must be positive")
    requested = None
    if args.width is not None:
        width, height = args.width, args.height
        source = "given"
    else:
        requested = args.ratio.strip()
        ratio = parse_ratio(requested)
        # The record's own label for a ratio wins: a family's 2:3 bucket is
        # 832x1216, which is not exactly two thirds, and that bucket is the
        # trained one.
        match = [row for row in sizes if row["declared_under"].strip() == requested]
        match += [row for row in sizes if abs(row["width"] / row["height"] - ratio) < 1e-6 and row not in match]
        if match:
            width, height = match[0]["width"], match[0]["height"]
            source = f"declared by the record under {match[0]['declared_under']!r}"
        else:
            if args.multiple is None:
                parser.error("an undeclared ratio needs --multiple from the model/service contract or an explicit chosen pixel grid")
            pixels = args.pixels if args.pixels is not None else (budget_of(sizes) if sizes else None)
            if pixels is None:
                raise SystemExit(
                    f"model record {model_id!r} declares no size, so a ratio it does not declare has no pixel "
                    "count to resolve at; pass --pixels"
                )
            width, height = resolve(ratio, pixels, args.multiple)
            source = f"proposed at {pixels} pixels using " + ("the explicitly supplied budget" if args.pixels is not None else "the median declared area (a proposal, not a training guarantee)")
    # A service that takes an aspect ratio is asked for the ratio requested, or
    # the one the record declares this size under.
    labels = [requested, *(row["declared_under"] for row in sizes if (row["width"], row["height"]) == (width, height))]
    ratio_label = next((sides for label in labels if (sides := ratio_sides(label))), None)
    refusals, service = schema_refusals(record, args.service, model_id, width, height, None, ratio_label)
    report: dict[str, Any] = {
        "model": model_id,
        "requested_ratio": requested,
        "width": width,
        "height": height,
        "pixels": width * height,
        "ratio": simplify(width, height),
        "ratio_as_decimal": round(width / height, 4),
        "multiple": args.multiple,
        "sides_are_multiples": None if args.multiple is None else width % args.multiple == 0 and height % args.multiple == 0,
        "source": source,
        "service": service,
        "refused_by_the_observed_schema": refusals,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if refusals else 0


if __name__ == "__main__":
    raise SystemExit(main())
