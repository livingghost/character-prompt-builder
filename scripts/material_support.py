#!/usr/bin/env python3
"""Local, content-addressed material I/O. No semantic inference or execution."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import shutil
import tempfile
from typing import Any

from io_budget import read_stream
from execution_contract import publish_directory


def encoded(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                       allow_nan=False) + '\n').encode('utf-8')


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def content_hash(value: Any) -> str:
    return digest(json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(',', ':'), allow_nan=False).encode('utf-8'))


def decode(raw: bytes) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict:
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate JSON key: ' + key)
            result[key] = value
        return result
    def reject(value: str) -> None:
        raise ValueError('non-finite JSON number: ' + value)
    return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=reject)


def root_path(root: Path) -> Path:
    root = root.absolute()
    if any(p.is_symlink() for p in [root, *root.parents]):
        raise ValueError('material root must not contain symbolic links')
    if not root.is_dir():
        raise ValueError('material root must be a directory')
    return root.resolve()


def local(root: Path, relative: str, *, exists: bool = True) -> Path:
    root = root_path(root)
    if (not isinstance(relative, str) or not relative or '\\' in relative or
            '\x00' in relative or PureWindowsPath(relative).drive):
        raise ValueError('expected a portable project-relative path')
    parts = relative.split('/')
    if any(p in {'', '.', '..'} or ':' in p for p in parts) or Path(relative).is_absolute():
        raise ValueError('path must stay inside the supplied project')
    path = root
    for part in parts:
        path = path / part
        if path.is_symlink():
            raise ValueError('symbolic links are not material inputs or outputs')
    if not path.resolve().is_relative_to(root):
        raise ValueError('path escapes project')
    if exists and not path.exists():
        raise ValueError('missing material: ' + relative)
    return path


def read(path: Path, limit: int | None = None) -> bytes:
    if any(p.is_symlink() for p in [path, *path.parents]) or not path.is_file():
        raise ValueError('material must be a regular file without symbolic links')
    with path.open('rb') as handle:
        return read_stream(handle, limit, label=str(path))


def load(root: Path, relative: str) -> dict:
    value = decode(read(local(root, relative)))
    if not isinstance(value, dict):
        raise ValueError('material must be a JSON object')
    return value


def exact(value: Any, required: set[str], optional: set[str] = frozenset(), label: str = 'object') -> None:
    if not isinstance(value, dict):
        raise ValueError(label + ' must be an object')
    if required - value.keys() or value.keys() - required - optional:
        raise ValueError(f'{label}: missing {sorted(required - value.keys())}, unexpected {sorted(value.keys() - required - optional)}')


def text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + ' must be nonempty text')
    return value


def strings(value: Any, label: str, *, nonempty: bool = False) -> list[str]:
    if not isinstance(value, list) or (nonempty and not value):
        raise ValueError(label + ' must be a list')
    for entry in value:
        text(entry, label)
    if len(set(value)) != len(value):
        raise ValueError(label + ' contains duplicates')
    return value


def indexed(rows: Any, key: str, label: str) -> dict[str, dict]:
    if not isinstance(rows, list):
        raise ValueError(label + ' must be a list')
    result = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(label + ' must contain objects')
        identifier = text(row.get(key), key)
        if identifier in result:
            raise ValueError('duplicate ' + key + ': ' + identifier)
        result[identifier] = row
    return result


def line_span(raw: bytes, start: int, end: int, encoding: str = 'utf-8') -> str:
    source = raw.decode(encoding)
    if not isinstance(source, str):
        raise ValueError('source encoding must decode text')
    lines = source.splitlines(keepends=True)
    if (type(start) is not int or type(end) is not int or
            not 1 <= start <= end <= len(lines)):
        raise ValueError('invalid inclusive source line range')
    return ''.join(lines[start - 1:end])


def quote(value: str) -> str:
    # A quoted source is data, including any imperative sentences it contains.
    return '\n'.join('> ' + line for line in value.splitlines())


def fsync_directory(path: Path) -> None:
    if os.name == 'posix':
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def publish(root: Path, output: str, files: dict[str, bytes]) -> dict:
    """Publish an immutable complete directory; an identical rerun is a no-op."""
    target = local(root, output, exists=False)
    target.parent.mkdir(parents=True, exist_ok=True)
    guard = target.parent / ('.' + target.name + '.material-lock')
    try:
        descriptor = os.open(guard, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise ValueError('material output is reserved; inspect the active or interrupted build') from exc
    stage = None
    try:
        os.close(descriptor)
        if target.exists():
            mismatches = compare(target, files)
            if mismatches:
                raise ValueError('material output differs; choose a fresh output path or explicitly remove the discarded derived bundle')
            return {'written': False, 'files': sorted(files)}
        stage = Path(tempfile.mkdtemp(prefix='.material-', dir=target.parent))
        for name, raw in sorted(files.items()):
            path = local(stage, name, exists=False)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
        for path in sorted((p for p in stage.rglob('*') if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
            fsync_directory(path)
        fsync_directory(stage)
        # Check again while holding the output reservation.
        local(root, output, exists=False)
        if target.exists():
            raise ValueError('material output appeared during publication')
        publish_directory(stage, target)
        fsync_directory(target.parent)
        return {'written': True, 'files': sorted(files)}
    finally:
        if stage is not None and stage.exists():
            shutil.rmtree(stage)
        guard.unlink(missing_ok=True)


def compare(directory: Path, files: dict[str, bytes]) -> list[str]:
    directory = root_path(directory)
    different = []
    for name, expected in files.items():
        try:
            if read(local(directory, name)) != expected:
                different.append(name)
        except (OSError, ValueError):
            different.append(name)
    actual = {p.relative_to(directory).as_posix() for p in directory.rglob('*') if p.is_file() or p.is_symlink()}
    different.extend(actual - set(files))
    return sorted(set(different))


def sealed(value: dict) -> dict:
    value = dict(value)
    value.pop('content_sha256', None)
    value['content_sha256'] = content_hash(value)
    return value


def check_seal(value: dict) -> None:
    if sealed(value)['content_sha256'] != value.get('content_sha256'):
        raise ValueError('material content hash mismatch')
