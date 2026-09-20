#!/usr/bin/env python3
"""Manage Character Prompt Builder content packs and their search cache."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from pack_cache import (
    cache_status,
    load_runtime_catalog,
    refresh_cache,
    runtime_resource_provider_status,
)
from pack_manager import (
    PackError,
    add_pack_root,
    build_lock_data,
    clear_resource_provider,
    default_settings,
    disable_pack,
    discover_packs,
    enable_pack,
    initialize_pack,
    initialize_state_file,
    is_project_pack,
    install_pack,
    list_packs,
    load_effective_state,
    remove_pack,
    remove_pack_root,
    select_resource_provider,
    validate_pack,
    write_lock,
)


def _settings(args: argparse.Namespace):
    return default_settings(
        state_file=Path(args.state_file) if args.state_file else None,
        cache_dir=Path(args.cache_dir) if args.cache_dir else None,
        managed_root=Path(args.managed_root) if args.managed_root else None,
    )


def _print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def _write_release_lock(path: Path) -> dict[str, Any]:
    """Build a lock while preserving an existing released identity.

    Direct ``write_lock`` callers remain suitable for temporary development
    fixtures. The public release-facing CLI refuses to publish changed bytes
    under an already locked UUID and CalVer pair.
    """

    root = path.resolve()
    if is_project_pack(root):
        raise PackError("Bundled commons is core-managed; no pack.lock.json is required or written")
    candidate = build_lock_data(root)
    lock_path = root / "pack.lock.json"
    if lock_path.is_file():
        try:
            existing = json.loads(lock_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PackError(f"Could not read existing pack.lock.json: {exc}") from exc
        if not isinstance(existing, dict):
            raise PackError("Existing pack.lock.json must be a JSON object")
        same_identity = (
            existing.get("pack_id") == candidate.get("pack_id")
            and existing.get("release") == candidate.get("release")
        )
        if (
            same_identity
            and existing.get("content_sha256") != candidate.get("content_sha256")
        ):
            raise PackError(
                "Refusing to publish different bytes under the existing pack UUID "
                "and release. Increment pack.json release before rebuilding "
                "pack.lock.json."
            )
    return write_lock(root)


def _mutate_enabled_state(args: argparse.Namespace, operation) -> dict[str, Any]:
    settings = _settings(args)
    state = operation(settings)
    try:
        cache = refresh_cache(settings, force=True)
    except Exception as exc:
        raise PackError(
            "Pack state was committed, but the derived cache could not be refreshed; "
            f"the stale cache will not be used: {exc}"
        ) from exc
    return {"ok": True, "state": state, "cache": cache}


def _inspect_pack(args: argparse.Namespace) -> dict[str, Any]:
    settings = _settings(args)
    discovered, issues = discover_packs(settings)
    pack = discovered.get(args.pack_id)
    if pack is None:
        raise PackError(f"Unknown pack ID: {args.pack_id}")
    report = validate_pack(pack.root, require_lock=args.released)
    output = report.to_dict()
    output["manifest"] = report.manifest
    output["discovery_issues"] = [issue.to_dict() for issue in issues]
    return output


def _list_resources(args: argparse.Namespace) -> dict[str, Any]:
    catalog = load_runtime_catalog(_settings(args))
    return {
        "ok": True,
        "resources": {
            name: {
                "path": str(resource.path),
                "media_type": resource.media_type,
                "source_pack": resource.source_pack,
            }
            for name, resource in sorted(catalog.resources.items())
        },
        "diagnostics": list(catalog.diagnostics),
    }


def _resolve_resource(args: argparse.Namespace) -> dict[str, Any]:
    catalog = load_runtime_catalog(_settings(args))
    resource = catalog.resources.get(args.name)
    if resource is None:
        raise PackError(f"Unknown or unresolved named resource: {args.name}")
    return {
        "ok": True,
        "name": resource.name,
        "path": str(resource.path),
        "media_type": resource.media_type,
        "source_pack": resource.source_pack,
    }


def _list_resource_providers(args: argparse.Namespace) -> dict[str, Any]:
    return runtime_resource_provider_status(_settings(args))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate, discover, install, activate, update, and remove Character "
            "Prompt Builder content packs. Output is JSON."
        )
    )
    parser.add_argument("--state-file", help="Override the enabled-pack state file.")
    parser.add_argument("--cache-dir", help="Override the generated catalog-cache directory.")
    parser.add_argument("--managed-root", help="Override the managed installation directory.")

    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="Create an empty UUIDv7-identified development pack.")
    init.add_argument("path")
    init.add_argument("--name", required=True)
    init.add_argument("--release")
    init.add_argument("--description", default="")
    init.add_argument("--license", default="GPL-3.0-only")

    validate = commands.add_parser("validate", help="Validate one pack directory.")
    validate.add_argument("path")
    validate.add_argument(
        "--released",
        action="store_true",
        help="Require and fully verify pack.lock.json.",
    )

    lock = commands.add_parser(
        "build-lock",
        help="Generate pack.lock.json from the complete current pack inventory.",
    )
    lock.add_argument("path")

    list_command = commands.add_parser(
        "list", help="List discovered packs and enabled state."
    )
    list_command.add_argument(
        "--skip-lock",
        action="store_true",
        help=(
            "Skip pack.lock.json verification for structural inventory only. "
            "Rows then report valid as null and lock_verified as false."
        ),
    )

    commands.add_parser(
        "state-init",
        help=(
            "Persist the resolved state file from the shipped initial state "
            "when absent, then report discovered packs and enabled status."
        ),
    )

    root_add_help = (
        "Register either an exact directory containing pack.json or a "
        "container whose immediate subdirectories are packs."
    )
    root_add = commands.add_parser(
        "root-add",
        help=root_add_help,
        description=root_add_help,
    )
    root_add.add_argument("path")

    root_remove = commands.add_parser(
        "root-remove",
        help="Unregister a pack root after disabling packs that depend on it.",
    )
    root_remove.add_argument("path")

    inspect = commands.add_parser("inspect", help="Return one discovered manifest and validation report.")
    inspect.add_argument("pack_id")
    inspect.add_argument("--released", action="store_true")

    enable = commands.add_parser("enable", help="Enable one installed or discovered pack.")
    enable.add_argument("pack_id")

    disable = commands.add_parser("disable", help="Disable one pack.")
    disable.add_argument("pack_id")
    disable.add_argument(
        "--cascade",
        action="store_true",
        help="Also disable enabled packs that require this pack.",
    )

    install = commands.add_parser(
        "install",
        help="Validate and install a locked pack directory or ZIP into the managed root.",
    )
    install.add_argument("source")

    update = commands.add_parser(
        "update",
        help="Atomically replace an installed pack with a newer locked release.",
    )
    update.add_argument("source")

    remove = commands.add_parser(
        "remove",
        help="Move a disabled managed pack into recoverable quarantine.",
    )
    remove.add_argument("pack_id")

    commands.add_parser("cache-status", help="Report cache freshness without rebuilding it.")
    refresh = commands.add_parser("cache-refresh", help="Refresh a stale pack search cache.")
    refresh.add_argument("--force", action="store_true")
    commands.add_parser("resources", help="List named resources from enabled packs.")
    resource = commands.add_parser("resource", help="Resolve one named resource to its active file.")
    resource.add_argument("name")
    commands.add_parser(
        "provider-list",
        help="List logical resources, candidate packs, and explicit provider selections.",
    )
    provider_select = commands.add_parser(
        "provider-select",
        help="Select the enabled provider pack for one logical resource.",
    )
    provider_select.add_argument("name")
    provider_select.add_argument("pack_id")
    provider_clear = commands.add_parser(
        "provider-clear",
        help="Clear the explicit provider selection for one logical resource.",
    )
    provider_clear.add_argument("name")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        settings = _settings(args)
        if args.command == "init":
            kwargs: dict[str, Any] = {
                "name": args.name,
                "description": args.description,
                "license_id": args.license,
            }
            if args.release:
                kwargs["release"] = args.release
            manifest = initialize_pack(Path(args.path), **kwargs)
            result = {
                "ok": True,
                "operation": "init",
                "path": str(Path(args.path).resolve()),
                "manifest": manifest,
            }
        elif args.command == "validate":
            result = validate_pack(
                Path(args.path),
                require_lock=args.released,
            ).to_dict()
        elif args.command == "build-lock":
            lock = _write_release_lock(Path(args.path))
            result = {
                "ok": True,
                "operation": "build-lock",
                "path": str((Path(args.path).resolve() / "pack.lock.json")),
                "pack_id": lock["pack_id"],
                "release": lock["release"],
                "file_count": len(lock["files"]),
                "content_sha256": lock["content_sha256"],
            }
        elif args.command == "list":
            result = list_packs(settings, verify_lock=not args.skip_lock)
        elif args.command == "state-init":
            result = initialize_state_file(settings)
        elif args.command == "root-add":
            result = _mutate_enabled_state(
                args,
                lambda value: add_pack_root(value, Path(args.path)),
            )
            result["operation"] = "root-add"
        elif args.command == "root-remove":
            result = _mutate_enabled_state(
                args,
                lambda value: remove_pack_root(value, Path(args.path)),
            )
            result["operation"] = "root-remove"
        elif args.command == "inspect":
            result = _inspect_pack(args)
        elif args.command == "enable":
            result = _mutate_enabled_state(
                args,
                lambda value: enable_pack(value, args.pack_id),
            )
            result["operation"] = "enable"
            result["pack_id"] = args.pack_id
        elif args.command == "disable":
            result = _mutate_enabled_state(
                args,
                lambda value: disable_pack(value, args.pack_id, cascade=args.cascade),
            )
            result["operation"] = "disable"
            result["pack_id"] = args.pack_id
        elif args.command == "install":
            result = install_pack(settings, Path(args.source), update=False)
        elif args.command == "update":
            result = install_pack(settings, Path(args.source), update=True)
            state = load_effective_state(settings)
            if result["pack_id"] in state["enabled_packs"]:
                result["cache"] = refresh_cache(settings, force=True)
        elif args.command == "remove":
            result = remove_pack(settings, args.pack_id)
        elif args.command == "cache-status":
            result = cache_status(settings)
        elif args.command == "cache-refresh":
            result = refresh_cache(settings, force=args.force)
        elif args.command == "resources":
            result = _list_resources(args)
        elif args.command == "resource":
            result = _resolve_resource(args)
        elif args.command == "provider-list":
            result = _list_resource_providers(args)
        elif args.command == "provider-select":
            result = _mutate_enabled_state(
                args,
                lambda value: select_resource_provider(value, args.name, args.pack_id),
            )
            result["operation"] = "provider-select"
            result["name"] = args.name
            result["pack_id"] = args.pack_id
        elif args.command == "provider-clear":
            result = _mutate_enabled_state(
                args,
                lambda value: clear_resource_provider(value, args.name),
            )
            result["operation"] = "provider-clear"
            result["name"] = args.name
        else:
            raise PackError(f"Unsupported command: {args.command}")
    except (PackError, OSError, ValueError) as exc:
        _print({"ok": False, "error": str(exc)})
        return 2
    _print(result)
    return 0 if result.get("ok", False) else 1


if __name__ == "__main__":
    raise SystemExit(main())
