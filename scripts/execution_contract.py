#!/usr/bin/env python3
"""Deterministic integrity, safe local I/O and locking that every script shares."""
from __future__ import annotations

import contextlib
import errno
import hashlib
import json
import os
import re
import stat
import time
import threading
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterator

from io_budget import read_stream
SHA = re.compile(r"^[0-9a-f]{64}$")
# The file `lock` holds in the directory it locks.
LOCK_FILE = ".cpb.lock"
# The name `atomic` writes under before it publishes; one left behind is from an interrupted write.
TEMPORARY_PREFIX = ".pending-"
# How a file system without hard links refuses one: FAT and exFAT answer EPERM
# on Linux and ENOTSUP on macOS, some network and synced file systems EOPNOTSUPP
# or ENOSYS, and Windows ERROR_INVALID_FUNCTION (1) or ERROR_NOT_SUPPORTED (50).
_NO_LINKS_ERRNOS = frozenset({errno.EPERM, errno.ENOTSUP, errno.EOPNOTSUPP, errno.ENOSYS})
_NO_LINKS_WINERRORS = frozenset({1, 50})


def encoded(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    """Hash a file to its end, one chunk at a time."""
    hasher = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def now() -> str:
    """The current UTC time to the second, as ISO 8601 text ending in Z."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


# Roots already checked for symbolic links, with their resolved form.
_checked_roots: dict[str, Path] = {}


def _root(root: Path) -> Path:
    """Refuse a root reached through a symbolic link; each root is checked once per process."""
    resolved = _checked_roots.get(str(root))
    if resolved is None:
        for p in [root, *root.parents]:
            if p.is_symlink():
                raise ValueError("symbolic link in root")
        resolved = _checked_roots[str(root)] = root.resolve()
    return resolved


def local(root: Path, relative: str, *, exists: bool = True) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError("canonical project-relative POSIX path required")
    rel = PurePosixPath(relative)
    if rel.is_absolute() or rel.as_posix() != relative or any(x in {".", ".."} for x in rel.parts):
        raise ValueError("path must remain within the project")
    root = root.absolute()
    resolved = _root(root)
    target = root.joinpath(*rel.parts)
    for p in [target, *target.parents]:
        if p == root:
            break
        if p.is_symlink():
            raise ValueError("symbolic link in project path")
    target.resolve().relative_to(resolved)
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


# Earlier readings by (root, relative path): the file, its identity, SHA-256 and size.
_file_digests: dict[tuple[str, str], tuple[Path, tuple[int, ...], str, int]] = {}
# A reading is reused only for a file modified this long before it was read,
# longer than the coarsest common timestamp resolution (two seconds on FAT).
_SETTLED_NS = 3_000_000_000


def _identity(path: Path) -> tuple[int, ...] | None:
    try:
        info = os.lstat(path)
    except OSError:
        return None
    if not stat.S_ISREG(info.st_mode):
        return None
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def file_digest(root: Path, relative: str) -> tuple[str, int]:
    """Return the SHA-256 and size of one regular file below `root`.

    A repeated call reuses the earlier reading while the file keeps its identity,
    size and timestamps, and was already settled when it was read. A rewrite
    within one timestamp tick is therefore read again, like every other change.
    """
    key = (str(root.absolute()), relative)
    known = _file_digests.get(key)
    if known is not None and _identity(known[0]) == known[1]:
        return known[2], known[3]
    started = time.time_ns()
    path = local(root, relative)
    before = _identity(path)
    raw = read(path)
    result = digest(raw), len(raw)
    if before is not None and before == _identity(path) and before[3] < started - _SETTLED_NS:
        _file_digests[key] = (path, before, *result)
    return result


def fsync_dir(path: Path) -> None:
    if os.name == "posix":
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _create(path: Path, raw: bytes) -> None:
    """Create `path` only when it is absent, write `raw` and flush it to disk.

    The file gets the ordinary creation mode. A failed write removes it again.
    """
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    descriptor = os.open(path, flags, 0o666)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _no_hard_links(error: OSError) -> bool:
    """True when os.link failed because the file system makes no hard links."""
    if isinstance(error, FileExistsError):
        return False
    winerror = getattr(error, "winerror", None)
    if winerror is not None:
        return winerror in _NO_LINKS_WINERRORS
    return error.errno in _NO_LINKS_ERRNOS


def atomic(path: Path, raw: bytes, *, replace: bool = False) -> None:
    """Write `raw` to `path` whole: replace it, or create it only when it is absent.

    The bytes reach the disk under a temporary name first. A replacement is a
    rename and a new name is a hard link, so a reader sees the old file or the
    whole new one. Without hard links, Windows renames the temporary file, which
    refuses an existing name. Elsewhere a rename would replace, so the new name
    is created exclusively and written in place.
    """
    if path.is_symlink():
        raise ValueError("cannot write through symbolic link")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.parent / (TEMPORARY_PREFIX + os.urandom(8).hex())
    try:
        _create(temp, raw)
        if replace:
            os.replace(temp, path)
        else:
            # Exclusive publication. The caller holds the project lock.
            try:
                os.link(temp, path)
            except OSError as error:
                if not _no_hard_links(error):
                    raise
                if os.name == "nt":
                    os.rename(temp, path)
                else:
                    _create(path, raw)
        fsync_dir(path.parent)
    finally:
        temp.unlink(missing_ok=True)


def atomic_write_json(path: Path, value: Any) -> None:
    """Replace `path` with `value` as indented JSON, whole and flushed to disk."""
    raw = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    atomic(path, raw, replace=True)


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


_thread_locks: dict[str, Any] = {}
_lock_registry_guard = threading.Lock()
_held_locks = threading.local()


def _reset_process_locks() -> None:
    global _thread_locks, _lock_registry_guard, _held_locks
    _thread_locks = {}
    _lock_registry_guard = threading.Lock()
    _held_locks = threading.local()


if hasattr(os, 'register_at_fork'):
    os.register_at_fork(after_in_child=_reset_process_locks)


@contextlib.contextmanager
def lock(root: Path) -> Iterator[None]:
    """Hold one project lock across nested calls, threads and processes."""
    root = root.absolute()
    root.mkdir(parents=True, exist_ok=True)
    key = str(root.resolve())
    with _lock_registry_guard:
        mutex = _thread_locks.setdefault(key, threading.RLock())
    with mutex:
        held = getattr(_held_locks, 'roots', None)
        if held is None:
            held = _held_locks.roots = set()
        if key in held:
            yield
            return
        with _os_lock(root):
            held.add(key)
            try:
                yield
            finally:
                held.remove(key)


@contextlib.contextmanager
def _os_lock(root: Path) -> Iterator[None]:
    """Cross-process advisory lock; a process crash releases the OS lock."""
    root.mkdir(parents=True, exist_ok=True)
    path = local(root, LOCK_FILE, exists=False)
    with path.open("a+b") as stream:
        if os.name == "nt":
            import msvcrt
            # Another holder's byte lock refuses a read of that byte, so the
            # file is sized rather than read before locking. LK_LOCK gives up
            # after ten one-second attempts with a permission error; the POSIX
            # branch waits, so wait here as well. Only another holder's lock
            # is waited out; any other error is raised.
            if os.fstat(stream.fileno()).st_size == 0:
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            while True:
                try:
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as exc:
                    if exc.errno not in (errno.EACCES, errno.EDEADLOCK):
                        raise
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
