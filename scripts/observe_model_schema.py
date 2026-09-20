#!/usr/bin/env python3
"""Store a service's parameter schema for one model offering, so requests can be checked against it.

Usage: python scripts/observe_model_schema.py --pack <pack-dir> <model-id> <service-id> <schema.json> [--source "<where it came from>"]

The schema file is what the service returned for the model (its schema endpoint,
its documentation, or a tool that exposes it). It is stored as observed, with the
date, the source, and the keywords the checker here does not enforce, under
<pack>/resources/observed-schemas/<model-id>.<service-id>.json, and the offering
in the model record is pointed at it. The record must already carry an offering
on that service. Re-run to refresh; the date moves with the file.

The pack's lock covers the file and the record, so rebuild it afterwards:
python -B scripts/pack_cli.py build-lock <pack-dir>
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from state_protocol import unsupported_schema_keywords  # noqa: E402


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Store an observed parameter schema for a model offering")
    parser.add_argument("model_id")
    parser.add_argument("service")
    parser.add_argument("schema_file")
    parser.add_argument("--pack", required=True, help="The pack directory that holds the model record")
    parser.add_argument("--source", default="the service's model schema endpoint",
                        help="Where the schema came from, as a name and not a story")
    parser.add_argument("--descriptions-ascii", action="store_true",
                        help="Record that non-ASCII punctuation in the schema's descriptions was written as ASCII")
    args = parser.parse_args()
    pack = Path(args.pack).resolve()
    records_path = pack / "records" / "models.json"
    if not records_path.is_file():
        raise SystemExit(f"{records_path}: no model records in this pack")
    document = json.loads(records_path.read_text(encoding="utf-8"))
    records = [r for r in document.get("records") or [] if isinstance(r, dict)]
    record = next((r for r in records if r.get("id") == args.model_id), None)
    if record is None:
        raise SystemExit(f"{records_path}: no model record {args.model_id!r}")
    offerings = [o for o in record.get("offerings") or [] if isinstance(o, dict) and o.get("service") == args.service]
    if not offerings:
        raise SystemExit(f"model record {args.model_id!r} records no offering on {args.service!r}; write the offering first")
    schema = json.loads(Path(args.schema_file).read_text(encoding="utf-8"))
    if isinstance(schema, dict) and "schema" in schema and "properties" not in schema:
        schema = schema["schema"]
    if not isinstance(schema, dict):
        raise SystemExit(f"{args.schema_file}: not a schema object")
    relative = f"resources/observed-schemas/{args.model_id}.{args.service}.json"
    today = date.today().isoformat()
    wrapper = {
        "artifact_type": "observed-parameter-schema",
        "model_id": args.model_id,
        "service": args.service,
        "model_identifier": offerings[0].get("model_identifier"),
        "observed_at": today,
        "source": args.source,
        "unenforced": unsupported_schema_keywords(schema),
        "schema": schema,
    }
    if args.descriptions_ascii:
        wrapper["descriptions_ascii"] = True
    write_json(pack / relative, wrapper)
    offerings[0]["schema_snapshot"] = relative
    offerings[0]["observed_at"] = today
    write_json(records_path, document)
    print(json.dumps({
        "ok": True,
        "snapshot": relative,
        "observed_at": today,
        "unenforced": wrapper["unenforced"],
        "record": str(records_path.relative_to(pack)),
        "next": f"python -B scripts/pack_cli.py build-lock {pack}",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
