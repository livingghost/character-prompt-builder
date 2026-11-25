"""Acquire authoritative knowledge records by document and section identity.

Each section owns its complete text. Markdown headings are part of that text;
they supply neither section boundaries nor machine identifiers. A reader owns
one acquisition of each record for its operation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import PurePosixPath, PureWindowsPath
import re
from types import MappingProxyType
from typing import Callable, Mapping

import execution_contract as c
from private_state import assert_public_path


RECORD_DIRECTORY = 'knowledge'
SECTION_ID_PATTERN = r'[a-z0-9][a-z0-9_-]*'
_IDENTIFIER = re.compile(SECTION_ID_PATTERN)
_DERIVATION_CACHE_MAX_BYTES = 1024 * 1024


def _document_id(value: str) -> str:
    """Require one portable logical path, independent of a file extension."""
    if not isinstance(value, str) or not value:
        raise ValueError('knowledge document ID must be a canonical relative logical path')
    parsed = PurePosixPath(value)
    if (parsed.is_absolute() or parsed.as_posix() != value
            or not parsed.parts or any(not _IDENTIFIER.fullmatch(part)
                                      or PureWindowsPath(part).is_reserved() for part in parsed.parts)):
        raise ValueError('knowledge document ID must be a canonical relative logical path')
    assert_public_path(RECORD_DIRECTORY + '/' + value + '.json')
    return value


def record_path(document_id: str) -> str:
    """Locate the sole editable record for a logical document."""
    return RECORD_DIRECTORY + '/' + _document_id(document_id) + '.json'


def record_id(path: str) -> str:
    """Read a document identity from its exact canonical record path."""
    prefix = RECORD_DIRECTORY + '/'
    if not isinstance(path, str) or not path.startswith(prefix) or not path.endswith('.json'):
        raise ValueError('knowledge record path must be knowledge/<document-id>.json')
    identifier = path[len(prefix):-len('.json')]
    if record_path(identifier) != path:
        raise ValueError('knowledge record path is not canonical')
    return identifier


def markdown_path(document_id: str) -> str:
    """Locate the human and host presentation generated from a record."""
    return _document_id(document_id) + '.md'


@dataclass(frozen=True, slots=True)
class AcquiredSection:
    """A declared identity and the exact complete body acquired for it."""

    section_id: str
    raw: bytes = field(repr=False)
    sha256: str

    @property
    def size(self) -> int:
        return len(self.raw)

    def metadata(self) -> dict:
        return {'section_id': self.section_id, 'sha256': self.sha256, 'size': self.size}


@dataclass(frozen=True, slots=True)
class AcquiredDocument:
    """One immutable record edition with direct section lookup."""

    document_id: str
    _record_sha256: str
    _record_size: int
    sections: tuple[AcquiredSection, ...]
    _by_id: Mapping[str, AcquiredSection] = field(repr=False, compare=False)

    @property
    def record(self) -> dict:
        return {'path': record_path(self.document_id),
                'sha256': self._record_sha256, 'size': self._record_size}

    def section(self, section_id: str) -> AcquiredSection:
        if not isinstance(section_id, str) or not _IDENTIFIER.fullmatch(section_id):
            raise ValueError('knowledge section ID is invalid')
        try:
            return self._by_id[section_id]
        except KeyError as exc:
            raise ValueError('knowledge section is not declared: ' + self.document_id + '#' + section_id) from exc


def _derive(document_id: str, encoded: bytes) -> tuple[str, tuple[AcquiredSection, ...]]:
    """Check a complete record and retain only immutable section values."""
    value = c.decode(encoded)
    c.exact(value, {'sections'}, 'knowledge record')
    rows = value['sections']
    if not isinstance(rows, list) or not rows:
        raise ValueError('knowledge record needs a nonempty ordered sections array')
    seen, sections = set(), []
    for row in rows:
        c.exact(row, {'id', 'body'}, 'knowledge section')
        identifier = row['id']
        if not isinstance(identifier, str) or not _IDENTIFIER.fullmatch(identifier):
            raise ValueError('knowledge section ID is invalid')
        if identifier in seen:
            raise ValueError('knowledge section ID is duplicated: ' + identifier)
        raw = c.text(row['body'], 'knowledge section body').encode('utf-8')
        sections.append(AcquiredSection(identifier, raw, c.digest(raw)))
        seen.add(identifier)
    return c.digest(encoded), tuple(sections)


@lru_cache(maxsize=64)
def _cached_derivation(document_id: str, encoded: bytes) -> tuple[str, tuple[AcquiredSection, ...]]:
    return _derive(document_id, encoded)


def decode_document(document_id: str, encoded: bytes) -> AcquiredDocument:
    """Validate already acquired record bytes without reading another file."""
    _document_id(document_id)
    if not isinstance(encoded, bytes):
        raise ValueError('knowledge record must be acquired as bytes')
    derive = _cached_derivation if len(encoded) <= _DERIVATION_CACHE_MAX_BYTES else _derive
    digest, sections = derive(document_id, encoded)
    return AcquiredDocument(document_id, digest, len(encoded), sections,
                            MappingProxyType({section.section_id: section for section in sections}))


class DocumentReader:
    """Read each authoritative record once within the caller's boundary."""

    def __init__(self, read_source: Callable[[str], bytes]):
        self._read_source = read_source
        self._documents: dict[str, AcquiredDocument] = {}

    def acquire(self, document_id: str) -> AcquiredDocument:
        path = record_path(document_id)
        if document_id not in self._documents:
            try:
                value = decode_document(document_id, self._read_source(path))
            except (OSError, ValueError, TypeError, KeyError) as exc:
                raise ValueError('knowledge record is missing or invalid: ' + path + ': ' + str(exc)
                                 + '. Restore or correct the authoritative record before reading it.') from exc
            self._documents[document_id] = value
        return self._documents[document_id]
