#!/usr/bin/env python3
"""Deterministic integrity, safe local I/O and locking that every script shares."""
from __future__ import annotations

import contextlib
import contextvars
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


# Resolved studio roots of this process, keyed by the absolute path text and
# guarded by the identity of the root entry: a root replaced by another entry is
# verified again, and a root that does not exist yet is never remembered.
_ROOTS: dict[str, tuple[tuple[int, int, bool], Path]] = {}


def _root(root: Path) -> Path:
    """Verify current root ancestry before using a studio-relative path."""
    root = Path(root).absolute()
    key = str(root)
    try:
        info = os.lstat(root)
        identity = (info.st_dev, info.st_ino, stat.S_ISLNK(info.st_mode))
    except OSError:
        identity = None
    known = _ROOTS.get(key)
    if known is not None and identity is not None and known[0] == identity:
        return known[1]
    for parent in (root, *root.parents):
        if parent.is_symlink():
            raise ValueError('symbolic link in root')
    resolved = root.resolve()
    if identity is not None:
        _ROOTS[key] = (identity, resolved)
    return resolved


def recheck_roots() -> None:
    """Check each studio root's whole ancestry again on its next use."""
    _ROOTS.clear()


# Run inputs written into a staging directory before its publication:
# (resolved studio root, studio-relative prefix, staging directory).
_STAGED: contextvars.ContextVar[tuple[tuple[str, str, Path], ...]] = contextvars.ContextVar('cpb_staged_inputs', default=())


@contextlib.contextmanager
def staged_inputs(root: Path, prefix: str, directory: Path) -> Iterator[None]:
    """Resolve studio paths below `prefix` inside `directory` until it is published there.

    A derived run declares its inputs at their published place inside the run.
    While the run is compiled, those files exist only in its staging directory.
    """
    rel = PurePosixPath(prefix)
    if rel.is_absolute() or rel.as_posix() != prefix or any(x in {'.', '..'} for x in rel.parts):
        raise ValueError('staged input prefix must be a canonical studio-relative path')
    token = _STAGED.set(_STAGED.get() + ((str(_root(root)), prefix, Path(directory).absolute()),))
    try:
        yield
    finally:
        _STAGED.reset(token)


def _staged(resolved: Path, rel: PurePosixPath) -> Path | None:
    for owner, prefix, directory in _STAGED.get():
        if owner != str(resolved):
            continue
        try:
            rest = rel.relative_to(prefix)
        except ValueError:
            continue
        target = directory.joinpath(*rest.parts)
        for p in [target, *target.parents]:
            if p == directory:
                break
            if p.is_symlink():
                raise ValueError("symbolic link in studio path")
        target.resolve().relative_to(directory.resolve())
        return target
    return None


# Windows marks a junction, a mount point and other redirected entries with this attribute.
_REDIRECTED = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_PLAIN_TYPES = (stat.S_IFDIR, stat.S_IFREG)
# lstat failures that mean the entry is absent, as pathlib reads them.
_ABSENT_ERRNOS = frozenset({errno.ENOENT, errno.ENOTDIR, errno.EBADF, errno.ELOOP})
_ABSENT_WINERRORS = frozenset({21, 123, 1921})


def _plain_entries(root: Path, target: Path, rel: PurePosixPath) -> tuple[bool, os.stat_result | None]:
    """Read each entry of `rel` below `root` with one lstat, from the top down.

    A symbolic link raises at once. The result is (True, lstat of the target)
    when every present entry is an ordinary directory or file, with None for
    an absent target. The result is (False, None) when an entry needs the full
    check:

    - Windows trims its name (a trailing dot or space);
    - Windows redirects it;
    - it is another file type;
    - reading it failed for a reason other than absence.
    """
    if target.parts != root.parts + rel.parts:
        return False, None
    step = os.path.join(str(root), "")
    info = None
    for index, name in enumerate(rel.parts):
        if os.name == "nt" and name[-1] in " .":
            return False, None
        step = step + name if index == 0 else step + os.sep + name
        try:
            info = os.lstat(step)
        except OSError as error:
            if error.errno in _ABSENT_ERRNOS or getattr(error, "winerror", None) in _ABSENT_WINERRORS:
                return True, None
            return False, None
        if stat.S_ISLNK(info.st_mode):
            raise ValueError("symbolic link in studio path")
        if getattr(info, "st_file_attributes", 0) & _REDIRECTED or stat.S_IFMT(info.st_mode) not in _PLAIN_TYPES:
            return False, None
    return True, info


def _located(root: Path, relative: str, exists: bool) -> tuple[Path, os.stat_result | None]:
    """Return the checked path and, when the entry check read it, the target's lstat."""
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError("canonical studio-relative POSIX path required")
    rel = PurePosixPath(relative)
    if rel.is_absolute() or rel.as_posix() != relative or any(x in {".", ".."} for x in rel.parts):
        raise ValueError("path must remain within the studio")
    root = root.absolute()
    resolved = _root(root)
    staged = _staged(resolved, rel) if _STAGED.get() else None
    if staged is not None:
        if exists and not staged.exists():
            raise ValueError(f"missing file: {relative}")
        return staged, None
    target = root.joinpath(*rel.parts)
    plain, info = _plain_entries(root, target, rel)
    if plain:
        if exists and info is None:
            raise ValueError(f"missing file: {relative}")
        return target, info
    # A redirected or unusual entry: resolve the whole path and require it below the root.
    for p in [target, *target.parents]:
        if p == root:
            break
        if p.is_symlink():
            raise ValueError("symbolic link in studio path")
    target.resolve().relative_to(resolved)
    if exists and not target.exists():
        raise ValueError(f"missing file: {relative}")
    return target, None


def local(root: Path, relative: str, *, exists: bool = True) -> Path:
    """Return `root` joined with a canonical relative path that stays inside it.

    Each entry below the root is read with one lstat. A symbolic link is
    refused. A Windows junction or another redirected entry is resolved, and
    the resolved path must stay below the resolved root.
    """
    return _located(root, relative, exists)[0]


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


def _identity_of(info: os.stat_result) -> tuple[int, ...] | None:
    if not stat.S_ISREG(info.st_mode):
        return None
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _identity(path: Path) -> tuple[int, ...] | None:
    try:
        info = os.lstat(path)
    except OSError:
        return None
    return _identity_of(info)


def file_digest(root: Path, relative: str) -> tuple[str, int]:
    """Return the SHA-256 and size of one regular file below `root`.

    A repeated call reuses the earlier reading while the file keeps its identity,
    size and timestamps, and was already settled when it was read. A rewrite
    within one timestamp tick is therefore read again, like every other change.
    Every call checks the path as `local` does; the target's lstat from that
    check confirms the identity, so a reused reading costs no further lookup.
    """
    path, info = _located(root, relative, True)
    key = (str(root.absolute()), relative)
    known = _file_digests.get(key)
    if known is not None:
        current = _identity_of(info) if info is not None and path == known[0] else _identity(known[0])
        if current == known[1]:
            return known[2], known[3]
    started = time.time_ns()
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
            # Exclusive publication. The caller holds the studio lock.
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
        from operation_context import current
        if current() is not None:
            current().artifact(path.absolute(), content_sha256=digest(raw), size=len(raw))
    finally:
        temp.unlink(missing_ok=True)


def atomic_write_json(path: Path, value: Any) -> None:
    """Replace `path` with `value` as indented JSON, whole and flushed to disk."""
    raw = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    atomic(path, raw, replace=True)


def _rename_directory_exclusive(staging: Path, target: Path) -> None:
    """Use an OS-level no-replace rename, including an empty destination race."""
    if os.name == 'nt':
        os.rename(staging, target)
        return
    import ctypes
    import sys
    libc = ctypes.CDLL(None, use_errno=True)
    source, destination = os.fsencode(staging), os.fsencode(target)
    if sys.platform.startswith('linux'):
        function = getattr(libc, 'renameat2', None)
        if function is None:
            raise OSError(errno.ENOTSUP, 'No exclusive directory rename is available')
        function.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        function.restype = ctypes.c_int
        # AT_FDCWD and RENAME_NOREPLACE are Linux ABI constants.
        result = function(-100, source, -100, destination, 1)
    elif sys.platform == 'darwin':
        function = getattr(libc, 'renamex_np', None)
        if function is None:
            raise OSError(errno.ENOTSUP, 'No exclusive directory rename is available')
        function.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        function.restype = ctypes.c_int
        result = function(source, destination, 0x00000004)  # RENAME_EXCL
    else:
        raise OSError(errno.ENOTSUP, 'No exclusive directory rename is available')
    if result != 0:
        number = ctypes.get_errno()
        raise OSError(number, os.strerror(number), str(target))


def publish_directory(staging: Path, target: Path, *, patience: float = 10.0) -> None:
    """Publish a complete directory without replacing any competing destination.

    A transient permission/handle refusal is retried for the supplied budget.
    Missing atomic no-replace support and other failures leave staging intact
    and return an actionable publication diagnostic, never a replacing rename.
    """
    from production_diagnostics import ProductionError
    staging, target = Path(staging), Path(target)
    if staging.is_symlink() or not staging.is_dir():
        raise ProductionError('ARTIFACT_PUBLISH_FAILED', 'Publication source must be an owned regular directory.',
                              phase='publication', file=str(staging))
    deadline = time.monotonic() + max(0.0, patience)
    while True:
        if target.exists() or target.is_symlink():
            raise ProductionError('OUTPUT_ALREADY_EXISTS', 'Publication destination is already occupied.',
                                  phase='publication', file=str(target), source=str(staging),
                                  required_action='Keep the existing destination and select a new output path.')
        try:
            _rename_directory_exclusive(staging, target)
        except OSError as exc:
            if exc.errno in {errno.EEXIST, errno.ENOTEMPTY} or target.exists() or target.is_symlink():
                raise ProductionError('OUTPUT_ALREADY_EXISTS', 'Another writer occupied the publication destination.',
                                      phase='publication', file=str(target), source=str(staging),
                                      required_action='Keep both contents; select a new output path.') from exc
            transient = isinstance(exc, PermissionError) or getattr(exc, 'winerror', None) in {5, 32, 33}
            if transient and time.monotonic() < deadline:
                time.sleep(min(0.1, max(0.0, deadline - time.monotonic())))
                continue
            raise ProductionError('ARTIFACT_PUBLISH_FAILED', 'The complete staging directory could not be published.',
                                  phase='publication', file=str(target), source=str(staging),
                                  actual={'errno': exc.errno, 'winerror': getattr(exc, 'winerror', None)},
                                  required_action='Keep staging. Check handles, permissions and atomic rename support on this filesystem.') from exc
        # The running operation's artifact index follows the files to their published place.
        from operation_context import relocate_artifacts
        relocate_artifacts(staging, target)
        return


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
    """Hold one studio lock across nested calls, threads and processes."""
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


def read_input_bytes(source: str | Path, *, root: Path | None = None) -> bytes:
    """Read the exact bytes of one input file, or of stdin for `-`."""
    import sys
    if str(source)=='-':
        stream=getattr(sys.stdin,'buffer',None)
        return stream.read() if stream is not None else sys.stdin.read().encode('utf-8')
    path=Path(source)
    if root is not None and not path.is_absolute():path=local(root,str(source))
    return read(path)


def read_json_input(source: str | Path, *, root: Path | None = None) -> Any:
    """Read one UTF-8 JSON file or stdin without shell JSON interpretation."""
    return decode(read_input_bytes(source, root=root))


def read_json_object(source: str | Path | None, *, root: Path | None = None, label: str = "JSON input") -> dict:
    """Use one file/stdin contract for declared parameter and settings objects."""
    value = {} if source is None else read_json_input(source, root=root)
    if not isinstance(value, dict):
        raise ValueError(f"{label}: expected a JSON object")
    return value
