#!/usr/bin/env python3
"""Shared command-line boundary for selecting one exact pack runtime."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from pack_manager import PackSettings, default_settings


@dataclass(frozen=True)
class PackRuntimeContext:
    """Resolved runtime paths plus the explicit discovery roots to propagate."""

    settings: PackSettings
    pack_roots: tuple[Path, ...]

    def command_arguments(self) -> list[str]:
        """Return a complete runtime argument vector for a child process."""
        output = [
            "--state-file",
            str(self.settings.state_file),
            "--cache-dir",
            str(self.settings.cache_dir),
            "--managed-root",
            str(self.settings.managed_root),
        ]
        for root in self.pack_roots:
            output.extend(("--pack-root", str(root)))
        return output


def add_pack_runtime_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the complete pack-runtime selector shared by catalog-aware CLIs."""
    parser.add_argument("--state-file", type=Path, help="Explicit pack-state path")
    parser.add_argument("--cache-dir", type=Path, help="Explicit derived-cache directory")
    parser.add_argument("--managed-root", type=Path, help="Explicit managed-pack root")
    parser.add_argument(
        "--pack-root",
        action="append",
        type=Path,
        default=[],
        help="Additional pack discovery root; repeat for multiple roots",
    )


def has_pack_runtime_arguments(args: argparse.Namespace) -> bool:
    """Return whether the caller supplied any runtime-selection argument."""
    return bool(
        getattr(args, "state_file", None)
        or getattr(args, "cache_dir", None)
        or getattr(args, "managed_root", None)
        or getattr(args, "pack_root", None)
    )


def resolve_pack_runtime(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
) -> PackRuntimeContext:
    """Validate and resolve CLI runtime paths without partial fallbacks."""
    runtime_paths = (
        getattr(args, "state_file", None),
        getattr(args, "cache_dir", None),
        getattr(args, "managed_root", None),
    )
    if any(value is not None for value in runtime_paths) and not all(
        value is not None for value in runtime_paths
    ):
        parser.error("--state-file, --cache-dir, and --managed-root must be supplied together")
    pack_roots = tuple(Path(value).resolve() for value in getattr(args, "pack_root", ()) or ())
    if pack_roots and not all(value is not None for value in runtime_paths):
        parser.error("--pack-root requires explicit --state-file, --cache-dir, and --managed-root")

    settings = default_settings(
        extra_roots=pack_roots,
        state_file=runtime_paths[0],
        cache_dir=runtime_paths[1],
        managed_root=runtime_paths[2],
    )
    return PackRuntimeContext(settings=settings, pack_roots=pack_roots)
