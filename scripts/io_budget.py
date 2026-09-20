#!/usr/bin/env python3
"""Complete I/O with optional caller-owned limits, never a guessed content ceiling.

A chunk size is a working-buffer choice: every chunk is processed until EOF.
It does not reject or truncate an input. See references/resource-handling.md.
"""
from __future__ import annotations

import hashlib
import math
import os
from pathlib import Path
from typing import BinaryIO


def optional_count(value: int | None, label: str) -> int | None:
    if value is not None and (type(value) is not int or value < 1):
        raise ValueError(label + ' must be a positive integer or null (no application limit)')
    return value


def optional_seconds(value: float | None, label: str) -> float | None:
    if value is not None and (type(value) not in {int, float} or not math.isfinite(value) or value <= 0):
        raise ValueError(label + ' must be a finite positive number or null (no application deadline)')
    return value


def read_stream(stream: BinaryIO, maximum: int | None = None, *, label: str = 'input') -> bytes:
    """Read all bytes, or reject an explicitly budgeted read without returning a prefix."""
    optional_count(maximum, 'maximum bytes')
    raw = stream.read() if maximum is None else stream.read(maximum + 1)
    if maximum is not None and len(raw) > maximum:
        raise ValueError(f'{label} exceeds the explicitly supplied {maximum}-byte budget; no partial input accepted')
    return raw


def file_identity(path: Path) -> dict:
    """Hash a regular file to EOF without allocating its complete content in memory."""
    if any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file():
        raise ValueError('expected a regular file without symbolic links')
    digest = hashlib.sha256()
    size = 0
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            size += len(chunk)
            digest.update(chunk)
    return {'bytes': size, 'sha256': digest.hexdigest()}


def environment_seconds(name: str) -> float | None:
    """Optional operator deadline; an absent variable does not invent one."""
    raw = os.environ.get(name)
    if raw is None:
        return None
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(name + ' must be a finite positive number of seconds') from exc
    return optional_seconds(value, name)
