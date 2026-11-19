#!/usr/bin/env python3
"""Manage Character Prompt Builder content packs and their search cache."""
from __future__ import annotations
import operation_context as _operation_context
import argparse


from pathlib import Path
from typing import Any, Sequence
from pack_runtime_cli import PACK_RUNTIME_SELECTION_HELP, add_pack_runtime_arguments


def _add_pack_target_arguments(command: argparse.ArgumentParser) -> None:
    group = command.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--pack",
        metavar="PACK_ID_OR_UNIQUE_NAME",
        help="Resolve one discovered pack by exact pack ID or unique authored name.",
    )
    group.add_argument(
        "--directory",
        metavar="PACK_DIRECTORY",
        help="Use this absolute directory containing pack.json; it is not interpreted as a pack name.",
    )

def build_parser() -> argparse.ArgumentParser:
    parser = _operation_context.ArgumentParser(
        description=(
            "Validate, discover, install, activate, update, and remove Character "
            "Prompt Builder content packs. Output is JSON."
        )
    )
    add_pack_runtime_arguments(parser)

    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser(
        "init",
        help=(
            "Create an empty pack, register its location when no pack root holds it, "
            "and enable it, so records added to it are used at once."
        ),
    )
    init.add_argument("path")
    init.add_argument("--name", required=True)
    init.add_argument("--release")
    init.add_argument("--description", default="")
    init.add_argument("--license", default="GPL-3.0-only")

    validate = commands.add_parser(
        "validate",
        help="Return the manifest and validation report of one discovered pack or one absolute pack directory.",
    )
    _add_pack_target_arguments(validate)
    validate.add_argument(
        "--released",
        action="store_true",
        help="Require and fully verify pack.lock.json.",
    )

    lock = commands.add_parser(
        "build-lock",
        help="Generate pack.lock.json from the complete current pack inventory.",
    )
    _add_pack_target_arguments(lock)

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

    ready_command = commands.add_parser(
        "ready",
        help=(
            "Create the state on first use, then print which packs retrieval uses "
            "and what the author must decide. Exits 1 while a decision is open."
        ),
    )
    ready_command.add_argument(
        "--without",
        action="append",
        default=[],
        metavar="PACK_ID",
        help="Disable this pack, as disable does, before the check; repeat for each.",
    )
    ready_command.add_argument(
        "--only",
        action="append",
        metavar="PACK_ID",
        help="When the state is new, enable only this pack; repeat for each. The rest are left out.",
    )

    root_add_help = (
        "Register either an exact directory containing pack.json or a "
        "container whose immediate subdirectories are packs in the selected pack state. "
        "The registered root is used by subsequent invocations."
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
    commands.add_parser(
        "resources",
        help="List each named resource and the enabled pack that supplies it.",
    )
    resource = commands.add_parser(
        "resource",
        help="Resolve one named resource to the file of the highest-ranked enabled pack that binds it.",
    )
    resource.add_argument("name")
    parser.epilog = "Place pack runtime options before the subcommand."
    for name, command_parser in commands.choices.items():
        arguments = "PACK_OR_CONTAINER" if name in {"root-add", "root-remove"} else "[arguments]"
        command_parser.formatter_class = argparse.RawDescriptionHelpFormatter
        command_parser.epilog = (
            PACK_RUNTIME_SELECTION_HELP + "\n\n"
            "Place pack runtime options before the subcommand:\n"
            f"  {parser.prog} --state-file STATE --cache-dir CACHE --managed-root MANAGED {name} {arguments}\n"
            "Use root-add to persist a discovery root in the selected state."
        )
    return parser

def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    import pack_commands as implementation
    args.runtime_context = implementation.resolve_pack_runtime(parser, args)
    if args.command == "ready":
        try:
            settled, lines = implementation.ready(implementation._settings(args), set(args.without), args.only)
        except (implementation.PackError, OSError, ValueError) as exc:
            print(f"error: {exc}")
            return 2
        for line in lines:
            print(line)
        return 0 if settled else 1
    try:
        settings = implementation._settings(args)
        if args.command == "init":
            kwargs: dict[str, Any] = {
                "name": args.name,
                "description": args.description,
                "license_id": args.license,
            }
            if args.release:
                kwargs["release"] = args.release
            result = implementation._init_pack(settings, Path(args.path).expanduser(), kwargs)
        elif args.command == "validate":
            target, discovery_issues = implementation._resolve_pack_target(args)
            report = implementation.validate_pack(target, require_lock=args.released)
            result = report.to_dict()
            result["resolved_root"] = str(target)
            result["manifest"] = report.manifest
            result["discovery_issues"] = discovery_issues
        elif args.command == "build-lock":
            target, _ = implementation._resolve_pack_target(args)
            lock, changes = implementation._write_release_lock(target)
            result = {
                "ok": True,
                "operation": "build-lock",
                "path": str((target / "pack.lock.json")),
                "pack_id": lock["pack_id"],
                "release": lock["release"],
                "file_count": len(lock["files"]),
                "content_sha256": lock["content_sha256"],
                "inventory_changes": changes,
                "reading_guidance": "A lock release alone does not invalidate a delivered reading. The route reader compares the current operation's documents, selected resources and model guidance.",
            }
        elif args.command == "list":
            result = implementation.list_packs(settings, verify_lock=not args.skip_lock)
        elif args.command == "root-add":
            result = implementation._mutate_enabled_state(
                args,
                lambda value: implementation.add_pack_root(value, Path(args.path)),
            )
            result["operation"] = "root-add"
        elif args.command == "root-remove":
            result = implementation._mutate_enabled_state(
                args,
                lambda value: implementation.remove_pack_root(value, Path(args.path)),
            )
            result["operation"] = "root-remove"
        elif args.command == "enable":
            result = implementation._mutate_enabled_state(
                args,
                lambda value: implementation.enable_pack(value, args.pack_id),
            )
            result["operation"] = "enable"
            result["pack_id"] = args.pack_id
        elif args.command == "disable":
            result = implementation._mutate_enabled_state(
                args,
                lambda value: implementation.disable_pack(value, args.pack_id, cascade=args.cascade),
            )
            result["operation"] = "disable"
            result["pack_id"] = args.pack_id
        elif args.command == "install":
            result = implementation.install_pack(settings, Path(args.source), update=False)
        elif args.command == "update":
            result = implementation.install_pack(settings, Path(args.source), update=True)
        elif args.command == "remove":
            result = implementation.remove_pack(settings, args.pack_id)
        elif args.command == "cache-status":
            result = implementation.cache_status(settings)
            result["visual_catalog"] = implementation.browser_catalog_status(settings, result["expected_fingerprint"])
        elif args.command == "cache-refresh":
            views = implementation._refresh_views(settings, force=args.force)
            result = {**views["cache"], "visual_catalog": views["visual_catalog"]}
        elif args.command == "resources":
            result = implementation._list_resources(args)
        elif args.command == "resource":
            result = implementation._resolve_resource(args)
        else:
            raise implementation.PackError(f"Unsupported command: {args.command}")
        if args.command in {"init", "build-lock", "install", "update", "remove"}:
            if settings.state_file.is_file():
                result.update(implementation._refresh_views(settings))
            else:
                result["visual_catalog"] = implementation.unselected_catalog(settings)
    except (implementation.PackError, OSError, ValueError) as exc:
        implementation._print(implementation._failure(exc, args.command))
        return 2
    implementation._print(result)
    return 0 if result.get("ok", False) else 1


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(_operation_context.run_cli(main))
