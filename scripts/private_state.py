"""The Studio authentication owner's private paths and ordinary-artifact boundary."""
from __future__ import annotations

import os
from pathlib import Path
import stat

PRIVATE_CREDENTIALS_FILE = "credentials.json"
PRIVATE_TEMPORARY_PREFIX = ".pending-auth-"
PRIVATE_IGNORE_BLOCK = (
    b"# Private Studio authentication.\n"
    b"/credentials.json\n"
    b"/.pending-auth-*\n"
)


class PrivateStateError(ValueError):
    """A private authentication path was offered to an ordinary artifact owner."""


def is_private_path(path: str | Path) -> bool:
    """Recognize the declared private names, including their containing paths.

    Names use Windows' case, trailing-dot and stream aliases on every host.
    This identifies owned filesystem locations, not the contents of an input.
    """
    names = (part.partition(":")[0].rstrip(" .").lower()
             for part in str(path).replace("\\", "/").split("/"))
    return any(name == PRIVATE_CREDENTIALS_FILE or name.startswith(PRIVATE_TEMPORARY_PREFIX)
               for name in names)


def assert_public_path(path: str | Path) -> None:
    """Require a production input, artifact or release path."""
    if is_private_path(path):
        raise PrivateStateError(
            "Private Studio credentials belong to authentication management. "
            "Choose a production source or artifact file for this operation."
        )


def assert_public_tree(path: Path) -> None:
    """Check an entire copy input before publishing any of its entries."""
    path = Path(path)
    assert_public_path(path)
    assert_public_path(path.resolve())
    for entry in path.rglob("*"):
        assert_public_path(entry)
        # Copies may follow a selected alias; check its destination as well.
        assert_public_path(entry.resolve())


def _ignore_info(path: Path) -> os.stat_result:
    for entry in (path, *path.parents):
        if entry.is_symlink() or entry.is_junction():
            raise PrivateStateError("The Studio ignore file requires an ordinary path under the Studio.")
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise PrivateStateError("The Studio ignore file requires a regular file with one link.")
    return info


def _ignore_identity(info: os.stat_result) -> tuple[int, int, int, int]:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def ensure_private_ignored(root: Path) -> None:
    """Append the private-file rules while preserving every authored ignore byte.

    The authentication owner holds the Studio lock. The final block takes
    precedence over earlier negations, and an existing final block is retained.
    A separate editor can still replace files outside that advisory lock.
    """
    root = Path(root).absolute()
    path = root / ".gitignore"
    flags = os.O_RDWR | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    created = False
    try:
        before = _ignore_info(path)
    except FileNotFoundError:
        descriptor = os.open(path, flags | os.O_CREAT | os.O_EXCL, 0o666)
        created = True
        before = None
    else:
        descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1 or
                before is not None and _ignore_identity(opened) != _ignore_identity(before)):
            raise PrivateStateError("The Studio ignore file changed while it was opened. Repeat preparation with the current file.")
        os.lseek(descriptor, max(0, opened.st_size - len(PRIVATE_IGNORE_BLOCK)), os.SEEK_SET)
        tail = os.read(descriptor, len(PRIVATE_IGNORE_BLOCK))
        current = _ignore_info(path)
        if (_ignore_identity(os.fstat(descriptor)) != _ignore_identity(opened) or
                _ignore_identity(current) != _ignore_identity(opened)):
            raise PrivateStateError("The Studio ignore file changed while it was checked. Repeat preparation with the current file.")
        if not tail.endswith(PRIVATE_IGNORE_BLOCK):
            separator = b"\n" if opened.st_size and not tail.endswith(b"\n") else b""
            pending = memoryview(separator + PRIVATE_IGNORE_BLOCK)
            while pending:
                written = os.write(descriptor, pending)
                if written <= 0:
                    raise OSError("The Studio ignore rules could not be appended.")
                pending = pending[written:]
            os.fsync(descriptor)
            after = _ignore_info(path)
            if _ignore_identity(after) != _ignore_identity(os.fstat(descriptor)):
                raise PrivateStateError("The Studio ignore file changed during preparation. Repeat preparation with the current file.")
    finally:
        os.close(descriptor)
    if created and os.name == "posix":
        directory = os.open(root, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
