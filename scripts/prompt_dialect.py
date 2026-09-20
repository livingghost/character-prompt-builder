#!/usr/bin/env python3
"""Settle everything one model wants from its own family, and nothing another family taught.

Usage:
  python scripts/prompt_dialect.py --list
  python scripts/prompt_dialect.py --dialect <dialect-id>
  python scripts/prompt_dialect.py --model <model-id>
      [--dialects <dialects.json>] [--guide <guide.json>]
      [--state-file PATH] [--cache-dir PATH] [--managed-root PATH]

Models do not read a prompt the same way. One family takes a rating term the
next has never seen, spells a multi-word tag differently, wants a different
explicit weight, builds the rendition from different blocks in a different
order, and renders at a different size. A rule proven on one family, handed to
another, is worse than no rule: it spends the budget and steers nothing.

So the family is a thing with a name. The `prompt-dialects` resource holds one
entry per family, a model record names the one it belongs to, and a guide section
names the families it applies to. This command puts them together: given a model,
it returns that family's grammar, blocks, and vocabulary, the guide rules that
apply to it, and the record's own recommended text, parameters, and sizes. A
section belonging to another family is left out rather than filtered by the
reader.

A record that names no dialect is not a tag target. That is reported as such, and
the universal rules are still returned.

Output is JSON on stdout.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from pack_cache import load_runtime_catalog  # noqa: E402
from pack_manager import PackError, default_settings  # noqa: E402

DIALECTS = "prompt-dialects"
GUIDE = "prompt-writing-guide"


def resolve_resource(name: str, explicit: str | None, *, state_file: str | None, cache_dir: str | None,
                     managed_root: str | None, required: bool = True) -> Path | None:
    if explicit:
        return Path(explicit)
    settings = default_settings(
        state_file=Path(state_file) if state_file else None,
        cache_dir=Path(cache_dir) if cache_dir else None,
        managed_root=Path(managed_root) if managed_root else None,
    )
    resource = load_runtime_catalog(settings).resources.get(name)
    if resource is None:
        if required:
            raise PackError(f"no enabled pack provides the {name} resource")
        return None
    return Path(resource.path)


SCHEMA_PATH = ROOT / "schemas" / "prompt-dialect.schema.json"


def validate_dialects(value: Any) -> Any:
    """Refuse a prompt-dialects resource that does not meet its contract."""

    from state_protocol import validate_against_schema

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = validate_against_schema(value, schema)
    if errors:
        raise PackError("prompt-dialects resource is invalid: " + "; ".join(errors))
    seen: set[str] = set()
    for row in value["dialects"]:
        if row["id"] in seen:
            raise PackError(f"prompt-dialects resource repeats the dialect {row['id']!r}")
        seen.add(row["id"])
    return value


def load_dialects(path: Path) -> dict[str, dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("dialects"), list):
        raise PackError(f"{path}: not a prompt-dialects resource")
    validate_dialects(data)
    return {str(row["id"]): row for row in data["dialects"]}


def applicable_sections(guide_path: Path | None, dialect_id: str | None) -> dict[str, list[dict[str, Any]]]:
    """The guide split into what applies to every target and what this family owns."""

    if guide_path is None:
        return {"universal": [], "dialect": [], "withheld": []}
    data = json.loads(guide_path.read_text(encoding="utf-8"))
    universal, owned, withheld = [], [], []
    for section in data.get("sections") or []:
        named = section.get("dialects")
        row = {"id": section["id"], "title": section["title"], "rules": section["rules"]}
        if "examples" in section:
            row["examples"] = section["examples"]
        if not named:
            universal.append(row)
        elif dialect_id is not None and dialect_id in named:
            owned.append(row)
        else:
            withheld.append({"id": section["id"], "dialects": named})
    return {"universal": universal, "dialect": owned, "withheld": withheld}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--list", action="store_true", help="The families the resource carries")
    parser.add_argument("--dialect", help="A family, by its id")
    parser.add_argument("--model", help="A model record, whose own family is used")
    parser.add_argument("--dialects", help="A prompt-dialects JSON file, instead of the active pack's")
    parser.add_argument("--guide", help="A prompt-writing-guide JSON file, instead of the active pack's")
    parser.add_argument("--state-file")
    parser.add_argument("--cache-dir")
    parser.add_argument("--managed-root")
    args = parser.parse_args(argv)
    if not (args.list or args.dialect or args.model):
        parser.error("one of --list, --dialect, or --model")

    scope = {"state_file": args.state_file, "cache_dir": args.cache_dir, "managed_root": args.managed_root}
    dialects = load_dialects(resolve_resource(DIALECTS, args.dialects, **scope))
    if args.list and not (args.dialect or args.model):
        print(json.dumps({"dialects": [{"id": row["id"], "name": row["name"], "description": row["description"]}
                                       for row in dialects.values()]}, ensure_ascii=False, indent=2))
        return 0

    record: dict[str, Any] | None = None
    model_id = None
    if args.model:
        from prepare_generation_references import resolve_model_record

        model_id, record = resolve_model_record(args.model)
        dialect_id = record.get("prompt_dialect")
    else:
        dialect_id = args.dialect
    if dialect_id is not None and dialect_id not in dialects:
        raise SystemExit(f"no dialect {dialect_id!r}; the resource carries {sorted(dialects)}")

    guide_path = resolve_resource(GUIDE, args.guide, **scope, required=False)
    report: dict[str, Any] = {
        "model": model_id,
        "dialect": dialects.get(dialect_id) if dialect_id else None,
        "reads_tags": dialect_id is not None,
        "guide": applicable_sections(guide_path, dialect_id),
    }
    if record is not None:
        report["record"] = {
            "prompt_style": record.get("prompt_style"),
            "ordering": record.get("ordering"),
            "recommended_positive_prompt": record.get("recommended_positive_prompt"),
            "recommended_negative_prompt": record.get("recommended_negative_prompt"),
            "recommended_negative_preset": record.get("recommended_negative_preset"),
            "recommendation_merge_mode": record.get("recommendation_merge_mode"),
            "recommended_parameters": record.get("recommended_parameters"),
            "size_hints": record.get("size_hints"),
            "negative_transport_mode": record.get("negative_transport_mode"),
            "offerings": [{"service": row.get("service"), "model_identifier": row.get("model_identifier"),
                           "parameter_keys": row.get("parameter_keys"), "observed_at": row.get("observed_at")}
                          for row in record.get("offerings") or []],
        }
        if dialect_id is None:
            report["note"] = (
                f"model record {model_id!r} names no dialect, so it is not read as a tag target; "
                "compose from the record's own prompt_style and ordering"
            )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
