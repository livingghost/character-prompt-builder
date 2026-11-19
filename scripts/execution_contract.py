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
import weakref
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Callable, Iterator

from io_budget import read_stream
from private_state import assert_public_path
SHA = re.compile(r"^[0-9a-f]{64}$")
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
    assert_public_path(path)
    if Path(path).is_symlink():
        assert_public_path(Path(path).resolve())
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


def decode(raw: bytes, *, owned: bool = False) -> Any:
    """Parse strict JSON, finishing read-only containers at an owning boundary."""
    def bad(value: str) -> None:
        raise ValueError(f"non-finite JSON number: {value}")
    if owned:
        from owned_json import decoded_array, decoded_object
        return decoded_array(json.loads(raw.decode("utf-8"), object_pairs_hook=decoded_object, parse_constant=bad))
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
    root = (root if isinstance(root, Path) else Path(root)).absolute()
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
_STAGED: contextvars.ContextVar[tuple[tuple[str, str, Path, Any], ...]] = contextvars.ContextVar('cpb_staged_inputs', default=())


@contextlib.contextmanager
def staged_inputs(root: Path, prefix: str, directory: Path, *, on_resolve=None) -> Iterator[None]:
    """Resolve studio paths below `prefix` inside `directory` until it is published there.

    A derived run declares its inputs at their published place inside the run.
    While the run is compiled, those files exist only in its staging directory.
    """
    rel = PurePosixPath(prefix)
    if rel.is_absolute() or rel.as_posix() != prefix or any(x in {'.', '..'} for x in rel.parts):
        raise ValueError('staged input prefix must be a canonical studio-relative path')
    token = _STAGED.set(_STAGED.get() + ((str(_root(root)), prefix, Path(directory).absolute(), on_resolve),))
    try:
        yield
    finally:
        _STAGED.reset(token)


def _staged(resolved: Path, rel: PurePosixPath) -> Path | None:
    for owner, prefix, directory, on_resolve in _STAGED.get():
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
        if on_resolve is not None:
            on_resolve(rel.as_posix())
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


def _not_relative(root: Path, relative: str, parsed: PurePosixPath) -> str | None:
    """Why `relative` names no place below a root, or None when it starts at no drive or root.

    The operating system's own path rules decide: on Windows a drive such as
    C: or a leading separator starts the path, elsewhere a leading /. When the
    path lies below `root`, the reason also gives its root-relative form.
    """
    anchor = (PureWindowsPath(relative) if os.name == "nt" else parsed).anchor
    if not anchor:
        return None
    start = anchor.replace("\\", "/")
    reason = f"not relative to the root: {relative} starts at {start}"
    bases = [Path(root).absolute()]
    try:
        bases.append(_root(root))
    except (OSError, ValueError):
        pass
    for base in bases:
        try:
            below = Path(relative).relative_to(base)
        except ValueError:
            continue
        if below.parts:
            return reason + f"; below the root it is {below.as_posix()}"
    return reason


def _located(root: Path, relative: str, exists: bool) -> tuple[Path, os.stat_result | None]:
    """Return the checked path and, when the entry check read it, the target's lstat."""
    if not isinstance(relative, str) or not relative:
        raise ValueError("canonical studio-relative POSIX path required")
    rel = PurePosixPath(relative)
    reason = _not_relative(root, relative, rel)
    if reason is not None:
        raise ValueError(reason)
    if "\\" in relative:
        raise ValueError("canonical studio-relative POSIX path required")
    if rel.as_posix() != relative or any(x in {".", ".."} for x in rel.parts):
        raise ValueError("path must remain within the studio")
    assert_public_path(rel)
    root = root.absolute()
    resolved = _root(root)
    staged = _staged(resolved, rel) if _STAGED.get() else None
    if staged is not None:
        assert_public_path(staged)
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
    assert_public_path(path)
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


def _create(path: Path, raw: bytes, *, durable: bool = True) -> None:
    """Create `path` only when absent and write the complete `raw` contents.

    The file gets the ordinary creation mode. A failed write removes it again.
    """
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    descriptor = os.open(path, flags, 0o666)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            if durable:
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


def _transient_refusal(error: OSError) -> bool:
    """True for a transient permission or handle refusal that a retry outlasts."""
    return isinstance(error, PermissionError) or getattr(error, "winerror", None) in {5, 32, 33}


def _patiently(operation: Callable[[], None], *, patience: float = 10.0) -> None:
    """Run `operation`, waiting out transient refusals for the supplied budget.

    A scanner or indexer can hold a name for a moment; the operation is retried
    until the budget runs out, then the refusal is raised.
    """
    deadline = time.monotonic() + max(0.0, patience)
    while True:
        try:
            operation()
            return
        except OSError as error:
            if not _transient_refusal(error) or time.monotonic() >= deadline:
                raise
            time.sleep(min(0.1, max(0.0, deadline - time.monotonic())))


def atomic(path: Path, raw: bytes, *, replace: bool = False, durable: bool = True) -> None:
    """Write `raw` to `path` whole: replace it, or create it only when it is absent.

    Durable writes reach disk under a temporary name first. A replacement is a
    rename and a new name is a hard link, so a reader sees the old file or the
    whole new one. A replacing rename waits out a transient permission or handle
    refusal within a bounded budget. Without hard links, an OS-level exclusive
    rename publishes the complete temporary file while refusing an existing
    destination. A
    private staging owner can defer durability until publication. It must flush
    file contents and then directory entries before publishing any part of that
    private tree.
    """
    assert_public_path(path)
    if path.is_symlink():
        raise ValueError("cannot write through symbolic link")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.parent / (TEMPORARY_PREFIX + os.urandom(8).hex())
    try:
        _create(temp, raw, durable=durable)
        if replace:
            retain_replacement_lock(temp, path)
            _patiently(lambda: replace_file(temp, path))
        else:
            # Exclusive publication is decided by the filesystem operation.
            try:
                os.link(temp, path)
            except OSError as error:
                if not _no_hard_links(error):
                    raise
                _patiently(lambda: _rename_exclusive(temp, path))
        if durable:
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


def _rename_exclusive(staging: Path, target: Path) -> None:
    """Publish a complete file or directory with an OS-level no-replace rename."""
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
            raise OSError(errno.ENOTSUP, 'No atomic exclusive rename is available')
        function.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        function.restype = ctypes.c_int
        # AT_FDCWD and RENAME_NOREPLACE are Linux ABI constants.
        result = function(-100, source, -100, destination, 1)
    elif sys.platform == 'darwin':
        function = getattr(libc, 'renamex_np', None)
        if function is None:
            raise OSError(errno.ENOTSUP, 'No atomic exclusive rename is available')
        function.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        function.restype = ctypes.c_int
        result = function(source, destination, 0x00000004)  # RENAME_EXCL
    else:
        raise OSError(errno.ENOTSUP, 'No atomic exclusive rename is available')
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
            _rename_exclusive(staging, target)
        except OSError as exc:
            if exc.errno in {errno.EEXIST, errno.ENOTEMPTY} or target.exists() or target.is_symlink():
                raise ProductionError('OUTPUT_ALREADY_EXISTS', 'Another writer occupied the publication destination.',
                                      phase='publication', file=str(target), source=str(staging),
                                      required_action='Keep both contents; select a new output path.') from exc
            transient = _transient_refusal(exc)
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


PUBLISHED_CONTINUATION = ('Use the published directory; it is complete. If it is missing after a crash or power loss, '
                          'run the same command again.')


def flush_published(target: Path, *, phase: str = 'publication', continuation: str = PUBLISHED_CONTINUATION) -> None:
    """Flush the directory that holds a published directory.

    The publication is complete when this runs. A failed flush reports that,
    with `published` true and the caller's continuation; it is not a failure
    to read an input or to publish.
    """
    from production_diagnostics import ProductionError
    target = Path(target)
    try:
        fsync_dir(target.parent)
    except OSError as exc:
        raise ProductionError('ARTIFACT_PUBLISH_FAILED',
            'The directory is published and complete, but the directory that holds it could not be flushed to disk.',
            phase=phase, file=str(target), published=True,
            actual={'errno': exc.errno, 'winerror': getattr(exc, 'winerror', None)},
            required_action=continuation) from exc


_held_file_locks = threading.local()
# Resource ownership for fork cleanup, not an acquisition cache or a mutex.
_file_lock_streams: weakref.WeakSet = weakref.WeakSet()
# Keep the coordination range outside the data so locked bytes remain readable.
_WINDOWS_LOCK_OFFSET = (1 << 63) - 2


def _reset_file_locks_after_fork() -> None:
    global _held_file_locks, _file_lock_streams
    # flock ownership belongs to an open file description inherited by fork.
    # Close the child's copies; explicitly unlocking would unlock the parent.
    try:
        with contextlib.ExitStack() as cleanup:
            for stream in tuple(_file_lock_streams):
                cleanup.callback(stream.close)
    finally:
        _held_file_locks = threading.local()
        _file_lock_streams = weakref.WeakSet()


if hasattr(os, 'register_at_fork'):
    os.register_at_fork(after_in_child=_reset_file_locks_after_fork)


def _file_lock_key(path: Path) -> str:
    return os.path.normcase(os.path.abspath(path))


def _open_lock_stream(path: Path, *, read_only: bool = False, for_rename: bool = False):
    """Open an existing data file with sharing that permits its coordinated replacement."""
    if os.name == 'nt':
        import ctypes
        import msvcrt
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        create = kernel.CreateFileW
        create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                           wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        create.restype = wintypes.HANDLE
        access = 0x80000000 if read_only else 0xC0000000
        if for_rename:
            access |= 0x00010000
        handle = create(str(path), access, 0x7, None, 3, 0x00200000, None)
        if handle == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            descriptor = msvcrt.open_osfhandle(handle, (os.O_RDONLY if read_only else os.O_RDWR) | os.O_BINARY)
        except BaseException:
            close = kernel.CloseHandle
            close.argtypes = [wintypes.HANDLE]
            close.restype = wintypes.BOOL
            close(handle)
            raise
    else:
        descriptor = os.open(path, (os.O_RDONLY if read_only else os.O_RDWR)
                             | getattr(os, 'O_CLOEXEC', 0) | getattr(os, 'O_NOFOLLOW', 0))
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or getattr(info, 'st_file_attributes', 0) & _REDIRECTED:
            raise ValueError('file locking requires an existing regular data file')
        stream = os.fdopen(descriptor, 'rb' if read_only else 'r+b', buffering=0)
    except BaseException:
        os.close(descriptor)
        raise
    _file_lock_streams.add(stream)
    return stream


def _acquire_file_lock(stream) -> None:
    if os.name == 'nt':
        import msvcrt
        stream.seek(_WINDOWS_LOCK_OFFSET)
        while True:
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                return
            except OSError as exc:
                if exc.errno not in (errno.EACCES, errno.EDEADLOCK):
                    raise
                time.sleep(0.05)
    else:
        import fcntl
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)


def _release_file_lock(stream) -> None:
    if stream.closed:
        return
    try:
        if os.name == 'nt':
            import msvcrt
            stream.seek(_WINDOWS_LOCK_OFFSET)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    finally:
        stream.close()


@contextlib.contextmanager
def file_lock(path: Path, *, follow_symlinks: bool = False, read_only: bool = False) -> Iterator[None]:
    """Own an existing mutable data file across nested calls and processes.

    A waiter verifies the acquired file identity against the current path. A
    replacement is locked before publication and remains owned by the outer
    scope. An explicit private alias may follow its current target while
    retaining the logical destination as owner for a later local replacement.
    """
    path = Path(path)
    path = _root(path.parent) / path.name
    key = _file_lock_key(path)
    held = getattr(_held_file_locks, 'paths', None)
    if held is None:
        held = _held_file_locks.paths = {}
    if key in held:
        yield
        return
    while True:
        source = path.resolve(strict=True) if follow_symlinks else path
        stream = _open_lock_stream(source, read_only=read_only)
        try:
            _acquire_file_lock(stream)
            current = path.stat() if follow_symlinks else path.lstat()
            if stat.S_ISLNK(current.st_mode) or getattr(current, 'st_file_attributes', 0) & _REDIRECTED:
                raise ValueError('file locking requires a regular data path')
            if os.path.samestat(os.fstat(stream.fileno()), current):
                break
        except BaseException:
            stream.close()
            raise
        _release_file_lock(stream)
    streams = held[key] = [stream]
    try:
        yield
    finally:
        held.pop(key, None)
        with contextlib.ExitStack() as cleanup:
            for owned in streams:
                cleanup.callback(_release_file_lock, owned)


def retain_replacement_lock(source: Path, target: Path) -> None:
    """Lock the complete replacement before its publication at the owned target."""
    held = getattr(_held_file_locks, 'paths', None)
    if not held:
        return
    streams = held.get(_file_lock_key(target))
    if streams is None:
        return
    current = Path(target).stat()
    retained = [stream for stream in streams
                if os.path.samestat(os.fstat(stream.fileno()), current)]
    if len(retained) != 1:
        raise ValueError('the owned data file was replaced outside its update scope')
    obsolete = [stream for stream in streams if stream is not retained[0]]
    streams[:] = retained
    with contextlib.ExitStack() as cleanup:
        for stream in obsolete:
            cleanup.callback(_release_file_lock, stream)
    stream = _open_lock_stream(Path(source))
    try:
        _acquire_file_lock(stream)
    except BaseException:
        stream.close()
        raise
    streams.append(stream)


def _rename_open_windows(source: Path, target: Path) -> None:
    """Rename through a temporary delete handle, leaving the locked handle readable."""
    import ctypes
    import msvcrt
    from ctypes import wintypes
    name = str(target.absolute())
    class RenameInfo(ctypes.Structure):
        _fields_ = [('Flags', wintypes.DWORD), ('RootDirectory', wintypes.HANDLE),
                    ('FileNameLength', wintypes.DWORD),
                    ('FileName', wintypes.WCHAR * (len(name) + 1))]
    info = RenameInfo()
    info.Flags = 0x1 | 0x2
    info.FileNameLength = len(name.encode('utf-16-le'))
    info.FileName = name
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    setinfo = kernel.SetFileInformationByHandle
    setinfo.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
    setinfo.restype = wintypes.BOOL
    stream = _open_lock_stream(source, for_rename=True)
    try:
        handle = msvcrt.get_osfhandle(stream.fileno())
        if not setinfo(handle, 22, ctypes.byref(info), ctypes.sizeof(info)):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        stream.close()


def replace_file(source: Path, target: Path) -> None:
    """Publish a replacement while retaining its independent lock handle."""
    if os.name == 'nt':
        held = getattr(_held_file_locks, 'paths', None)
        streams = held.get(_file_lock_key(Path(target))) if held else None
        if streams:
            stream = streams[-1]
            if os.path.samestat(os.fstat(stream.fileno()), Path(source).stat()):
                _rename_open_windows(Path(source), Path(target))
                return
    os.replace(source, target)


def object_store(run: Path, raw: bytes) -> str:
    key = digest(raw)
    path = local(run, "objects/" + key, exists=False)
    if path.exists():
        if read(path) != raw:
            raise ValueError("content-addressed object is corrupt")
    else:
        try:
            atomic(path, raw)
        except FileExistsError:
            if read(path) != raw:
                raise ValueError("content-addressed object is corrupt")
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
    if root is not None and not path.is_absolute():
        # A Path built by code joins its parts with the platform separator; a
        # string is the caller's own text and keeps the '/'-separated contract.
        path=local(root,source if isinstance(source,str) else path.as_posix())
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
