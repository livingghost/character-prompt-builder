"""Deserialized run values owned by one production read boundary.

Storage and evidence loading belong to the reader. Domain operations receive
the resulting values, rather than reopening the publication for each check.
Read-only consumers share a verified read state. Editing boundaries request an
independent export and cannot alter another consumer's verified state.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, NamedTuple

import execution_contract as c
import production_store as store
from production_diagnostics import ProductionError
from owned_json import freeze, mutable


class RunSnapshot(NamedTuple):
    """A complete, caller-owned view of one verified run history."""

    directory: Path
    prepared: dict
    consumer: dict
    rows: list[dict]


@dataclass
class EvidenceReader:
    """Load each small immutable object once within the owning read boundary.

Large media is streamed by publication verification and is not retained in
this cache. A consumer that needs its bytes receives them for that call only.
The bound limits retained evidence, not the size of supported source files.
"""

    directory: Path
    limit: int = 8 * 1024 * 1024
    _objects: dict[str, bytes] = field(default_factory=dict)
    _size: int = 0

    def read(self, key: str) -> bytes:
        if key in self._objects:
            return self._objects[key]
        raw = c.object_read(self.directory, key)
        if self._size + len(raw) <= self.limit:
            self._objects[key] = raw
            self._size += len(raw)
        return raw


@dataclass(frozen=True)
class VerifiedPublication:
    """A checked publication and evidence belonging to the current read phase."""

    directory: Path
    registered: dict
    prepared: dict
    consumer: dict
    evidence: EvidenceReader
    verified_objects: dict[str, int]
    acquired: Any

    @property
    def artifacts(self) -> Mapping[str, Any]:
        return self.acquired.documents


@dataclass(frozen=True)
class RunView:
    """One immutable publication and event history for internal consumers.

    Tuple access exposes the four ordinary run components without exporting
    them. The lifecycle carries the indexes derived while checking history;
    explicitly used artifacts are decoded from the bytes verification read.
    """

    directory: Path
    registered: dict
    prepared: dict
    consumer: dict
    rows: list[dict]
    evidence: EvidenceReader
    lifecycle: Any
    artifacts: Mapping[str, Any]
    manifest: Mapping[str, Any]

    def __iter__(self):
        return iter((self.directory, self.prepared, self.consumer, self.rows))

    def __len__(self):
        return 4

    def __getitem__(self, index):
        return (self.directory, self.prepared, self.consumer, self.rows)[index]

    def snapshot(self) -> RunSnapshot:
        """Export an independent graph for a caller that needs editable data."""
        return RunSnapshot(self.directory, mutable(self.prepared),
                           mutable(self.consumer), mutable(self.rows))


@dataclass
class RunReader:
    """Own persistence reads and pass decoded values to the supplied validators.

    Each read phase acquires all publication bytes and decodes its documents.
    A new transaction or forced check acquires new values from current bytes;
    it does not carry a prior phase's decoded documents or success state.
    Own event writes invalidate history within the current phase. Consumers
    receive an immutable RunView; editable callers request an export.
    """

    root: Path
    validate_publication: Callable
    validate_history: Callable

    def read(self, run: str, *, force: bool = False) -> RunView:
        import runtime_snapshot
        from production_compiler import acquire_publication, validate_execution_documents
        root = self.root
        identity = str(Path(root).resolve())
        scope = runtime_snapshot.check_scope(root)
        key = ('verified-run', identity, run)
        if scope is not None and not force and key in scope:
            return scope[key]
        publication_key = ('verified-publication', identity, run)
        publication = scope.get(publication_key) if scope is not None else None
        if force:
            # A failed forced acquisition must not reveal an older view to
            # any nested or enclosing read in this public operation.
            for owner in (scope, runtime_snapshot.call_scope()):
                if owner is not None:
                    owner.pop(key, None)
                    owner.pop(publication_key, None)
            publication = None
        # A publication can outlive a rolled-back registration. Every new
        # event history must still belong to a committed/current transaction
        # registration, even when its immutable bytes were already decoded.
        # Evict forced reads before this lookup, which can itself fail.
        registered = store.registered_run(root, run)
        if publication is not None and publication.registered != registered:
            publication = None
        if publication is None:
            directory = c.local(root, registered['directory'])
            acquired = acquire_publication(directory, expected=registered['manifest_sha256'], registered=True,
                documents={'prepared.json', 'consumer.json', 'package.json', 'request-contract.json',
                           'execution-plan.json', 'execution-target.json'})
            manifest = acquired.manifest
            prepared = acquired.documents['prepared.json']
            consumer = acquired.documents['consumer.json']
            if (prepared['envelope_sha256'] != registered['envelope_sha256']
                    or prepared['input_sha256'] != registered['input_sha256']):
                raise ProductionError('INPUT_SNAPSHOT_CORRUPT', 'Run content differs from the registered envelope.',
                                      phase='integrity', run=run, file='prepared.json', expected=registered['envelope_sha256'],
                                      actual=prepared['envelope_sha256'], impact=store.RUN_EVIDENCE_IMPACT,
                                      required_action=store.RESTORE_EVIDENCE)
            evidence = EvidenceReader(directory)
            known = {item['sha256']: item['size'] for item in manifest['files']
                     if item['path'] == 'objects/' + item['sha256']}
            self.validate_publication(run, prepared, consumer, evidence.read, known)
            validate_execution_documents(prepared, acquired.documents)
            publication = VerifiedPublication(directory, freeze(registered), prepared, consumer,
                                              evidence, known, acquired)
        history = store.read_history(root, run)
        state = self.validate_history(run, publication.prepared, history, publication.evidence.read,
                                      publication.verified_objects)
        state.seal()
        held = RunView(publication.directory, publication.registered, publication.prepared,
                       publication.consumer, state.rows, publication.evidence, state, publication.artifacts,
                       publication.acquired.manifest)
        # A failed validation never becomes reusable state.
        if scope is not None:
            scope[publication_key] = publication
            scope[key] = held
        return held
