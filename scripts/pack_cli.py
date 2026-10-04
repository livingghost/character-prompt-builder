#!/usr/bin/env python3
"""Manage Character Prompt Builder content packs and their search cache."""
from __future__ import annotations
import operation_context as _operation_context

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from pack_runtime_cli import add_pack_runtime_arguments, resolve_pack_runtime
from production_diagnostics import Diagnostic, from_exception

from pack_cache import (
    CONFLICT_KEY,
    RuntimePackResource,
    cache_status,
    load_runtime_catalog,
    pack_warnings,
    refresh_cache,
)
from pack_manager import (
    PackError,
    PackSettings,
    add_pack_root,
    build_lock_data,
    configured_roots,
    disable_pack,
    discover_packs,
    enable_pack,
    initialize_pack,
    initialize_state_file,
    is_commons_pack,
    install_pack,
    list_packs,
    load_effective_state,
    load_state,
    pack_cli_command,
    remove_pack,
    remove_pack_root,
    state_lock,
    validate_pack,
    write_lock,
)


def _settings(args: argparse.Namespace) -> PackSettings:
    """Reuse the context resolved at the CLI boundary for every suboperation."""
    return args.runtime_context.settings


def _print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def _write_release_lock(path: Path) -> dict[str, Any]:
    """Build a lock while preserving an existing released identity.

    Direct ``write_lock`` callers remain suitable for temporary development
    fixtures. The public release-facing CLI refuses to publish changed bytes
    under an already locked UUID and CalVer pair.
    """

    root = path.resolve()
    if is_commons_pack(root):
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
    with state_lock(settings):
        state = operation(settings)
    try:
        cache = refresh_cache(settings, force=True)
    except Exception as exc:
        raise PackError(
            "Pack state was committed, but the derived cache could not be refreshed; "
            f"the stale cache will not be used: {exc}"
        ) from exc
    return {"ok": True, "state": state, "cache": cache}


def _init_pack(settings: PackSettings, path: Path, options: dict[str, Any]) -> dict[str, Any]:
    """Create a pack where the author wants it and make it part of this runtime."""
    manifest = initialize_pack(path, **options)
    pack_id = str(manifest["pack_id"])
    with state_lock(settings):
        discovered, _ = discover_packs(settings)
        registered = pack_id not in discovered
        if registered:
            add_pack_root(settings, path)
        state = enable_pack(settings, pack_id)
    return {
        "ok": True,
        "operation": "init",
        "path": str(path.resolve()),
        "pack_id": pack_id,
        "root_registered": registered,
        "enabled": pack_id in state["enabled_packs"],
        "manifest": manifest,
    }


def _label(pack_id: str, root: Path | None, manifest: dict[str, Any] | None = None) -> str:
    """A pack's directory name, which is how a person finds it, then its ID."""
    if root is None:
        return pack_id
    name = root.name if root.name != pack_id else str((manifest or {}).get("name") or pack_id)
    return f"{name} {pack_id}"


def ready(
    settings: PackSettings,
    without: set[str],
    only: list[str] | None = None,
) -> tuple[bool, list[str]]:
    """Settle the runtime a session retrieves from, and say what the author must decide.

    The state file is created on first use, enabling every discovered pack or
    exactly `only`, and left as it is afterwards. `without` disables packs as
    `disable` does. A pack the author disabled stays disabled and is one line.
    These are decisions for the author, printed first with the command that
    settles each:

    - a pack that appeared since;
    - an enabled pack the catalog cannot use;
    - packs that bind one resource name with different files and that neither
      a required dependency nor pack_order orders.

    A disabled pack is never validated or indexed, only its manifest is read.
    """

    roots = configured_roots(settings, load_state(settings.state_file))
    print(f"scanning packs in {', '.join(str(root) for root in roots)}", file=sys.stderr, flush=True)
    created = initialize_state_file(settings, only=only)
    for pack_id in sorted(without):
        disable_pack(settings, pack_id)
    state = load_effective_state(settings)
    enabled = set(state["enabled_packs"])
    disabled = set(state["disabled_packs"])
    discovered, _ = discover_packs(settings, state)
    catalog = load_runtime_catalog(settings, quiet=True)
    problems = pack_warnings(catalog.diagnostics, settings)
    command = pack_cli_command(settings)
    decide: list[str] = []
    notes: list[str] = []
    left_out: set[str] = set()
    for key, line in problems.items():
        members = set(key.removeprefix(CONFLICT_KEY).split(",")) & enabled
        if not key.startswith(CONFLICT_KEY):
            left_out |= members
        if members:
            decide.append(f"decide: {line}")
        else:
            notes.append(f"warning: {line}")
    for pack_id in sorted(set(discovered) - enabled):
        pack = discovered[pack_id]
        name = _label(pack_id, pack.root, pack.manifest)
        if pack_id in disabled:
            notes.append(f"left out: {name} (disabled)")
            continue
        decide.append(
            f"decide: pack {name} is new and not enabled; ask the author whether to use it, "
            f"then run {command} enable {pack_id} or {command} disable {pack_id}"
        )
    in_use = sorted(set(discovered) & enabled - left_out)
    if not in_use:
        decide.append(f"decide: no pack is in use; enable one: {command} enable <pack-id>")
    lines = list(decide)
    if not decide:
        lines.append(f"ready: retrieval can use {len(in_use)} pack(s)")
    lines.extend(
        f"in use: {_label(pack_id, discovered[pack_id].root, discovered[pack_id].manifest)}"
        for pack_id in in_use
    )
    lines.extend(notes)
    lines.append(f"state: {settings.state_file}" + (" (created now)" if created else ""))
    return not decide, lines


class PackSelectionError(PackError):
    """A pack selector that names no pack, more than one pack, or a relative directory."""

    def __init__(self, code: str, message: str, *, required_action: str, **details: Any):
        super().__init__(message)
        self.code = code
        self.required_action = required_action
        self.details = details


def _failure(error: Exception, command: str) -> dict[str, Any]:
    """One failed pack command in the common diagnostic form."""
    if isinstance(error, PackSelectionError):
        diagnostic = Diagnostic(error.code, str(error), phase="pack-selection",
                                required_action=error.required_action, details=error.details).as_dict()
    elif isinstance(error, PackError):
        diagnostic = Diagnostic("PACK_OPERATION_FAILED", str(error), phase=command,
                                required_action="Correct the pack or state the message names, then retry.").as_dict()
    else:
        diagnostic = from_exception(error, phase=command)
    return {"ok": False, "diagnostics": [diagnostic]}


def _resolve_pack_target(args: argparse.Namespace) -> tuple[Path, list[dict[str, Any]]]:
    """Resolve an absolute directory or one discovered pack ID / unique authored name.

    A directory is used exactly as given, so it must be absolute; `~` expands to
    the home directory. A name is matched only against discovered manifests.
    """
    directory = getattr(args, "directory", None)
    selector = getattr(args, "pack", None)
    if directory:
        path = Path(directory).expanduser()
        if not path.is_absolute():
            raise PackSelectionError(
                "PACK_DIRECTORY_NOT_ABSOLUTE",
                "A pack directory must be an absolute path.",
                required_action="Pass the absolute path of the directory holding pack.json, or select a discovered pack with --pack.",
                actual=directory,
            )
        return path.resolve(), []

    settings = _settings(args)
    discovered, issues = discover_packs(settings)
    rows = [issue.to_dict() for issue in issues]
    exact = discovered.get(selector)
    if exact is not None:
        return exact.root, rows

    matches = [
        (pack_id, pack)
        for pack_id, pack in discovered.items()
        if str(pack.manifest.get("name") or "") == selector
    ]
    if len(matches) == 1:
        return matches[0][1].root, rows
    if len(matches) > 1:
        raise PackSelectionError(
            "PACK_NAME_AMBIGUOUS",
            f"Pack name {selector!r} is not unique.",
            required_action="Select one of the candidates with --pack PACK_ID.",
            candidates=[
                {"pack_id": pack_id, "name": selector, "root": str(pack.root)}
                for pack_id, pack in sorted(matches)
            ],
        )
    raise PackSelectionError(
        "PACK_NOT_FOUND",
        f"No discovered pack has the ID or unique name {selector!r}.",
        required_action="Select a discovered pack ID or unique name, or an absolute directory with --directory.",
        actual=selector,
        discovered=sorted(discovered),
        discovery_issues=[row for row in rows if row.get("pack_id") == selector],
    )


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


def _resource_row(resource: RuntimePackResource) -> dict[str, Any]:
    return {
        "path": str(resource.path),
        "media_type": resource.media_type,
        "source_pack": resource.source_pack,
        "relative_path": resource.relative_path,
    }


def _list_resources(args: argparse.Namespace) -> dict[str, Any]:
    catalog = load_runtime_catalog(_settings(args))
    return {
        "ok": True,
        "resources": {
            name: _resource_row(resource) for name, resource in sorted(catalog.resources.items())
        },
        "diagnostics": list(catalog.diagnostics),
    }


def _resolve_resource(args: argparse.Namespace) -> dict[str, Any]:
    catalog = load_runtime_catalog(_settings(args))
    resource = catalog.resources.get(args.name)
    if resource is None:
        raise PackError(f"Unknown or unresolved named resource: {args.name}")
    return {"ok": True, "name": resource.name, **_resource_row(resource)}


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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.runtime_context = resolve_pack_runtime(parser, args)
    if args.command == "ready":
        try:
            settled, lines = ready(_settings(args), set(args.without), args.only)
        except (PackError, OSError, ValueError) as exc:
            print(f"error: {exc}")
            return 2
        for line in lines:
            print(line)
        return 0 if settled else 1
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
            result = _init_pack(settings, Path(args.path).expanduser(), kwargs)
        elif args.command == "validate":
            target, discovery_issues = _resolve_pack_target(args)
            report = validate_pack(target, require_lock=args.released)
            result = report.to_dict()
            result["resolved_root"] = str(target)
            result["manifest"] = report.manifest
            result["discovery_issues"] = discovery_issues
        elif args.command == "build-lock":
            target, _ = _resolve_pack_target(args)
            lock = _write_release_lock(target)
            result = {
                "ok": True,
                "operation": "build-lock",
                "path": str((target / "pack.lock.json")),
                "pack_id": lock["pack_id"],
                "release": lock["release"],
                "file_count": len(lock["files"]),
                "content_sha256": lock["content_sha256"],
            }
        elif args.command == "list":
            result = list_packs(settings, verify_lock=not args.skip_lock)
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
        else:
            raise PackError(f"Unsupported command: {args.command}")
    except (PackError, OSError, ValueError) as exc:
        _print(_failure(exc, args.command))
        return 2
    _print(result)
    return 0 if result.get("ok", False) else 1


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(_operation_context.run_cli(main))
