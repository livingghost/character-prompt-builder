#!/usr/bin/env python3
"""Deterministic integrity, safe local I/O and locking for production records."""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import tempfile
import time
from pathlib import Path, PurePosixPath
from typing import Any, Iterator

from io_budget import read_stream
SHA = re.compile(r"^[0-9a-f]{64}$")


def encoded(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def content_id(value: Any) -> str:
    return digest(encoded(value))


def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def decode(raw: bytes) -> Any:
    def bad(value: str) -> None:
        raise ValueError(f"non-finite JSON number: {value}")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=bad)


def exact(value: Any, fields: set[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"{label}: expected fields {sorted(fields)}")


def text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}: nonempty text required")
    return value


def sha(value: Any) -> str:
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise ValueError("invalid SHA-256")
    return value


def local(root: Path, relative: str, *, exists: bool = True) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError("canonical project-relative POSIX path required")
    rel = PurePosixPath(relative)
    if rel.is_absolute() or rel.as_posix() != relative or any(x in {".", ".."} for x in rel.parts):
        raise ValueError("path must remain within the project")
    root = root.absolute()
    for p in [root, *root.parents]:
        if p.is_symlink():
            raise ValueError("symbolic link in root")
    target = root.joinpath(*rel.parts)
    for p in [target, *target.parents]:
        if p == root:
            break
        if p.is_symlink():
            raise ValueError("symbolic link in project path")
    target.resolve().relative_to(root.resolve())
    if exists and not target.exists():
        raise ValueError(f"missing file: {relative}")
    return target


def read(path: Path, maximum: int | None = None) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"not a regular file: {path.name}")
    with path.open("rb") as stream:
        return read_stream(stream, maximum, label=str(path))


def load(path: Path) -> Any:
    return decode(read(path))


def fsync_dir(path: Path) -> None:
    if os.name == "posix":
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def atomic(path: Path, raw: bytes, *, replace: bool = False) -> None:
    if path.is_symlink():
        raise ValueError("cannot write through symbolic link")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    temp = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            os.replace(temp, path)
        else:
            # Exclusive atomic publication. The caller holds the project lock.
            os.link(temp, path)
        fsync_dir(path.parent)
    finally:
        temp.unlink(missing_ok=True)


def publish_directory(staging: Path, target: Path, *, patience: float = 10.0) -> None:
    """Rename a completed staging directory into place.

    Windows refuses to rename a directory while another process holds a handle
    inside it, and a scanner or indexer opening freshly written files does
    exactly that for a moment. A refusal is retried for `patience` seconds and
    then raised as it came.
    """
    deadline = time.monotonic() + patience
    while True:
        try:
            staging.rename(target)
            return
        except PermissionError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.1)


@contextlib.contextmanager
def lock(root: Path) -> Iterator[None]:
    """Cross-process advisory lock; a process crash releases the OS lock."""
    root.mkdir(parents=True, exist_ok=True)
    path = local(root, ".production.lock", exists=False)
    with path.open("a+b") as stream:
        if os.name == "nt":
            import msvcrt
            # Another holder's byte lock refuses a read of that byte, so the
            # file is sized rather than read before locking. LK_LOCK gives up
            # after ten one-second attempts with a permission error; the POSIX
            # branch waits, so wait here as well.
            if os.fstat(stream.fileno()).st_size == 0:
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            while True:
                try:
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.05)
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def object_store(run: Path, raw: bytes) -> str:
    key = digest(raw)
    path = local(run, "objects/" + key, exists=False)
    if path.exists():
        if read(path) != raw:
            raise ValueError("content-addressed object is corrupt")
    else:
        atomic(path, raw)
    return key


def object_read(run: Path, key: str) -> bytes:
    raw = read(local(run, "objects/" + sha(key)))
    if digest(raw) != key:
        raise ValueError("content-addressed object hash mismatch")
    return raw
