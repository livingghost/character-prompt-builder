"""Acquire installed implementation bytes without an import-analysis cache.

Every non-test Python module is owned, so computed imports need no inference.
Complete schema, protocol, configuration, reference and template families also
cover data-selected names. User packs remain separate runtime inputs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import stat
from types import MappingProxyType
from typing import Iterator, Mapping


DATA_DIRECTORIES = ("schemas", "protocols", "config", "references", "templates")
# This generated source inventory is not a semantic builder input. Root release
# metadata (including MANIFEST.json) is outside the acquired source families.
DERIVED_INVENTORIES = frozenset({"config/implementation-files.json"})


@dataclass(frozen=True)
class FileInput:
    path: str
    content: bytes = field(repr=False)
    sha256: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "sha256", hashlib.sha256(self.content).hexdigest())

    def row(self) -> dict[str, str | int]:
        return {"path": self.path, "sha256": self.sha256, "size": len(self.content)}


@dataclass(frozen=True)
class BuilderInputs:
    """One acquired implementation and its exact immutable file contents."""

    root: Path
    files: tuple[FileInput, ...]
    fingerprint: str = field(init=False)
    paths: frozenset[str] = field(init=False)
    _content: Mapping[str, bytes] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        files = tuple(sorted(self.files, key=lambda item: item.path))
        object.__setattr__(self, "files", files)
        content = {item.path: item.content for item in files}
        if len(content) != len(files):
            raise ValueError("duplicate implementation input path")
        object.__setattr__(self, "_content", MappingProxyType(content))
        object.__setattr__(self, "paths", frozenset(content))
        raw = json.dumps(self.rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        object.__setattr__(self, "fingerprint", hashlib.sha256(raw).hexdigest())

    @property
    def rows(self) -> list[dict[str, str | int]]:
        """Return an independent JSON inventory for diagnostics or persistence."""
        return [item.row() for item in self.files]

    def read_bytes(self, path: str | Path) -> bytes:
        """Read acquired bytes by relative path or an absolute path inside root."""
        selected = Path(path)
        if selected.is_absolute():
            selected = selected.resolve()
            try:
                selected = selected.relative_to(self.root)
            except ValueError as exc:
                raise ValueError(f"implementation input is outside its root: {path}") from exc
        if ".." in selected.parts:
            raise ValueError(f"implementation input is outside its root: {path}")
        relative = selected.as_posix()
        try:
            return self._content[relative]
        except KeyError as exc:
            raise FileNotFoundError(f"file is not in the acquired implementation: {relative}") from exc


def _regular_files(directory: Path, root: Path) -> Iterator[Path]:
    """Traverse a source family while rejecting file and directory links.

    Inspect directory entries before descending, since rglob can silently omit
    a linked package. Windows junctions and other reparse points are rejected
    alongside symbolic links. Missing optional source families are empty.
    """
    try:
        metadata = directory.lstat()
    except FileNotFoundError:
        return
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    if stat.S_ISLNK(metadata.st_mode) or getattr(metadata, "st_file_attributes", 0) & reparse:
        raise ValueError(f"implementation input is a link or reparse point: {directory.relative_to(root).as_posix()}")
    if not stat.S_ISDIR(metadata.st_mode):
        raise ValueError(f"implementation source family is not a directory: {directory.relative_to(root).as_posix()}")
    for path in sorted(directory.iterdir()):
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or getattr(metadata, "st_file_attributes", 0) & reparse:
            raise ValueError(f"implementation input is a link or reparse point: {path.relative_to(root).as_posix()}")
        if path.name == "__pycache__":
            continue
        if stat.S_ISDIR(metadata.st_mode):
            yield from _regular_files(path, root)
        elif stat.S_ISREG(metadata.st_mode):
            yield path
        else:
            raise ValueError(f"implementation input is not a regular file: {path.relative_to(root).as_posix()}")


def capture(root: Path) -> BuilderInputs:
    """Read the complete installed implementation once for this operation.

    Exact current bytes determine identity, including modules selected only by
    dynamic imports. There is no retained discovery graph, parse cache or
    validation result. A later operation observes additions, edits and removals.
    """
    root = Path(root).resolve()
    files = []
    for family in ("scripts", *DATA_DIRECTORIES):
        for path in _regular_files(root / family, root):
            relative = path.relative_to(root).as_posix()
            if relative in DERIVED_INVENTORIES:
                continue
            if family == "scripts":
                if path.suffix in {".pyc", ".pyo"}:
                    continue
                if path.suffix == ".py" and (path.name.startswith("test_") or path.name.endswith("_test.py")):
                    continue
            files.append(FileInput(relative, path.read_bytes()))
    return BuilderInputs(root, tuple(files))
