#!/usr/bin/env python3
"""Read how one service is called: endpoint, auth shape, envelope, operations, delivery, and when that was observed.

Usage: python scripts/service_profile.py <service-id> [--profiles <services.json>] [--json]
       [--state-file PATH] [--cache-dir PATH] [--managed-root PATH]

The record is the `service-profiles` resource of the active pack runtime, so
nothing here carries an endpoint of its own. Print it beside anything sent to
the service, so an ageing record is seen before it fails.
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

RESOURCE = "service-profiles"


def resolve_path(explicit: str | None, *, state_file: str | None, cache_dir: str | None, managed_root: str | None,
                 settings: Any = None) -> Path:
    """The service-profiles resource of a pack runtime: the one given, or the one these three paths settle.

    A caller that already resolved a runtime passes its settings, so the service
    record and the model record that names it come from the same set of packs.
    """
    if explicit:
        return Path(explicit)
    if settings is None:
        settings = default_settings(
            state_file=Path(state_file) if state_file else None,
            cache_dir=Path(cache_dir) if cache_dir else None,
            managed_root=Path(managed_root) if managed_root else None,
        )
    catalog = load_runtime_catalog(settings)
    resource = catalog.resources.get(RESOURCE)
    if resource is None:
        raise PackError(f"no enabled pack provides the {RESOURCE} resource")
    return Path(resource.path)


def load_service(service: str, path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    services = data.get("services") if isinstance(data, dict) else None
    if not isinstance(services, dict):
        raise PackError(f"{path}: not a service-profiles record")
    record = services.get(service)
    if record is None:
        raise PackError(f"{path}: no service {service!r}; it records {sorted(services)}")
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("service")
    parser.add_argument("--profiles", help="Path to a service-profiles JSON file, instead of the active pack's")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--state-file")
    parser.add_argument("--cache-dir")
    parser.add_argument("--managed-root")
    args = parser.parse_args(argv)
    try:
        path = resolve_path(args.profiles, state_file=args.state_file, cache_dir=args.cache_dir, managed_root=args.managed_root)
        record = load_service(args.service, path)
    except (PackError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({"service": args.service, "path": str(path), "record": record}, ensure_ascii=False, indent=2))
        return 0
    endpoint = record.get("endpoint") or {}
    auth = record.get("auth") or {}
    print(f"{args.service}: {record.get('label')} (observed {record.get('observed_at')}, read from {path})")
    print(f"  endpoint   {endpoint.get('method', 'POST')} {endpoint.get('base_url')}")
    print(f"  auth       {auth.get('scheme')} in {auth.get('header')}" + (f", key from {auth['env_var']}" if auth.get("env_var") else ""))
    print(f"  request    {(record.get('envelope') or {}).get('request')}")
    print("  operations")
    for name, operation in (record.get("operations") or {}).items():
        print(f"    {name:<16} {operation.get('purpose')}; returns {operation.get('returns')}")
    print("  delivery")
    for name, delivery in (record.get("delivery") or {}).items():
        print(f"    {name:<16} {delivery.get('mode')}; poll {delivery.get('poll')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
