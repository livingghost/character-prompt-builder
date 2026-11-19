"""Deserialized run values owned by one production read boundary.

Storage and evidence loading belong to the reader. Domain operations receive
the resulting values, rather than reopening the publication for each check.
Read-only consumers share a verified read state. Editing boundaries request an
independent export and cannot alter another consumer's verified state.
"""
from __future__ import annotations
import read_context

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
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
    """Own acquired evidence bytes and their domain documents for one read.

Large media is streamed by publication verification and is not retained in
this owner. Retained JSON and sidecar checks belong to these exact acquired
bytes. A new operation or forced read constructs another reader. The byte
bound limits retained evidence, not the size of supported source files.
"""

    read_object: Callable[[str], bytes]
    limit: int = 8 * 1024 * 1024
    _objects: dict[str, bytes] = field(default_factory=dict)
    _documents: dict[str, Any] = field(default_factory=dict)
    _line_documents: dict[str, Any] = field(default_factory=dict)
    _sidecars: dict[str, Any] = field(default_factory=dict)
    _size: int = 0

    @property
    def remaining(self) -> int:
        """The byte budget available to this acquisition's publication reader."""
        return max(0, self.limit - self._size)

    def retain_verified(self, key: str, raw: bytes) -> None:
        """Retain exact bytes already checked by this acquisition's I/O owner."""
        if key not in self._objects and len(raw) <= self.remaining:
            self._objects[key] = raw
            self._size += len(raw)

    def read(self, key: str) -> bytes:
        if key in self._objects:
            return self._objects[key]
        raw = self.read_object(key)
        self.retain_verified(key, raw)
        return raw

    def document(self, key: str) -> Any:
        """Expose a read-only JSON document from this reader's exact bytes."""
        if key in self._documents:
            return self._documents[key]
        value = c.decode(self.read(key), owned=True)
        if key in self._objects:
            self._documents[key] = value
        return value

    def lines(self, key: str) -> Any:
        """Interpret each nonempty JSONL line once inside this evidence read."""
        if key in self._line_documents:
            return self._line_documents[key]
        value = freeze([c.decode(line, owned=True) for line in self.read(key).splitlines() if line.strip()])
        if key in self._objects:
            self._line_documents[key] = value
        return value

    def sidecar(self, key: str) -> Any:
        """Check an acquired sheet document before sharing its meaning."""
        if key in self._sidecars:
            return self._sidecars[key]
        from character_sheet import check_sidecar
        value = self.document(key)
        check_sidecar(value)
        if key in self._objects:
            self._sidecars[key] = value
        return value


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


def _registered_input(run: str, prepared: dict, registered: dict) -> None:
    if (prepared['envelope_sha256'] != registered['envelope_sha256']
            or prepared['input_sha256'] != registered['input_sha256']):
        raise ProductionError('INPUT_SNAPSHOT_CORRUPT', 'Run content differs from the registered envelope.',
                              phase='integrity', run=run, file='prepared.json', expected=registered['envelope_sha256'],
                              actual=prepared['envelope_sha256'], impact=store.RUN_EVIDENCE_IMPACT,
                              required_action=store.RESTORE_EVIDENCE)


@dataclass(frozen=True)
class DecisionRead:
    """Candidate decisions for navigation, without a run or mutation capability.

    The acquisition checks registered input records and the current complete
    event chain, including the evidence that gives those events meaning.
    No publication integrity, execution readiness or permission is asserted.
    An effect owner independently acquires its complete RunView.
    """

    run: str
    candidates: Mapping[str, Any]

    def candidate(self, identifier: str) -> Mapping[str, Any]:
        if identifier not in self.candidates:
            raise ValueError('missing candidate evidence')
        return self.candidates[identifier]


@dataclass
class DecisionReader:
    """Own current decision records and publish only their display projection."""

    root: Path
    validate_inputs: Callable
    validate_history: Callable
    project_candidate: Callable

    def read(self, run: str) -> DecisionRead:
        from production_compiler import acquire_decision_records
        identity = str(Path(self.root).resolve())
        scope = read_context.check_scope(self.root)
        key = ('run-decisions', identity, run)
        if scope is not None and key in scope:
            return scope[key]
        full = scope.get(('verified-run', identity, run)) if scope is not None else None
        if full is not None:
            prepared, state = full.prepared, full.lifecycle
        else:
            registered = store.registered_run(self.root, run)
            records = acquire_decision_records(c.local(self.root, registered['directory']),
                                               expected=registered['manifest_sha256'])
            prepared = records.prepared
            _registered_input(run, prepared, registered)
            self.validate_inputs(run, prepared, records.consumer)
            history = store.read_history(self.root, run)
            state = self.validate_history(run, prepared, history, records.evidence, records.verified_objects)
            state.seal()
        decisions = {row['sha256']: self.project_candidate(run, prepared, state, row['sha256'])
                     for row in state.rows if row['event'] == 'candidate'}
        held = DecisionRead(run, freeze(decisions))
        if scope is not None:
            scope[key] = held
        return held


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
    mutation: RunMutation | None = field(default=None, repr=False, compare=False)

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

    def append(self, event: str, data: dict) -> dict:
        """Append through the writer that acquired this exact current view."""
        if self.mutation is None:
            raise ValueError('acquire the run inside its writer transaction before appending')
        return self.mutation.append(self, event, data)


@dataclass(frozen=True)
class RunMutation:
    """The acquired history that one writer observation can advance.

    The existing transaction scope publishes the current view. Superseded
    views retain their immutable observations, and cannot write through this
    owner after another append, rollback, forced read or transaction boundary.
    """

    root: Path
    history: store.VerifiedHistory
    publication: VerifiedPublication
    key: tuple
    validate_append: Callable

    def append(self, observed: RunView, event: str, data: dict) -> dict:
        scope = read_context.check_scope(self.root) if store.owns_history(self.root, self.history) else None
        if scope is None or scope.get(self.key) is not observed or observed.mutation is not self:
            raise ProductionError('EVENT_CONFLICT', 'The run view is not the current writer observation.',
                phase='storage', run=self.history.scope,
                required_action='Read the run again with status --run, then repeat this command if its step is still open.')
        proposal = store.propose_append(self.history, observed.prepared['input_sha256'], event, data,
                                        expected_previous=observed.lifecycle.tail, check_previous=True)
        if proposal.raw is None:
            store.commit_append(self.root, proposal)
            return mutable(proposal.row)
        state = self.validate_append(self.history.scope, observed.prepared, observed.lifecycle,
            proposal.row, self.publication.evidence, self.publication.verified_objects)
        # The existing writer's savepoint keeps an interrupted event journal
        # or successor publication from leaving a partially staged append.
        with store.transaction(self.root):
            history = store.commit_append(self.root, proposal)
            read_context.invalidate_studio(self.root)
            scope.pop(('run-decisions', str(Path(self.root).resolve()), self.history.scope), None)
            successor = replace(self, history=history)
            scope[self.key] = replace(observed, rows=state.rows, lifecycle=state, mutation=successor)
        return mutable(proposal.row)


@dataclass
class RunReader:
    """Own persistence reads and pass decoded values to the supplied validators.

    Each operation acquires publication bytes and decodes its documents once.
    Its transactions retain those values and advance only the new event.
    A new operation or forced check acquires current persisted content.
    A writer advances its acquired history after each checked event. Consumers
    retain immutable RunViews; editable callers request an export.
    """

    root: Path
    validate_publication: Callable
    validate_history: Callable
    validate_append: Callable

    def _publication(self, run: str, registered: dict, acquired) -> VerifiedPublication:
        """Validate domain bindings on the exact documents their I/O owner read."""
        from production_compiler import validate_execution_documents
        prepared = acquired.documents['prepared.json']
        consumer = acquired.documents['consumer.json']
        _registered_input(run, prepared, registered)
        self.validate_publication(run, prepared, consumer, acquired.evidence.read,
                                  acquired.verified_objects)
        validate_execution_documents(prepared, acquired.documents)
        return VerifiedPublication(acquired.directory, freeze(registered), prepared, consumer,
                                   acquired.evidence, acquired.verified_objects, acquired)

    def retain_publication(self, run: str, acquired) -> None:
        """Give a newly registered run the producer's checked publication value.

        Registration and the current transaction own admission. Rollback drops
        this value with that registration; a new operation acquires storage.
        """
        registered = store.registered_run(self.root, run)
        directory = c.local(self.root, registered['directory'])
        if (acquired.directory != directory
                or acquired.manifest_sha256 != registered['manifest_sha256']):
            raise ProductionError('ARTIFACT_MANIFEST_CORRUPT',
                'The acquired publication differs from the registered run.',
                phase='integrity', run=run, expected=registered['manifest_sha256'],
                actual=acquired.manifest_sha256, required_action=store.RESTORE_EVIDENCE)
        publication = self._publication(run, registered, acquired)
        scope = read_context.check_scope(self.root)
        if scope is not None:
            identity = str(Path(self.root).resolve())
            scope[('verified-publication', identity, run)] = publication

    def read(self, run: str, *, force: bool = False) -> RunView:
        from production_compiler import RUN_DOCUMENTS, acquire_publication
        root = self.root
        identity = str(Path(root).resolve())
        scope = read_context.check_scope(root)
        key = ('verified-run', identity, run)
        if scope is not None and not force and key in scope:
            held = scope[key]
            connection = store._CONNECTIONS.get().get(identity)
            if connection is None:
                if held.mutation is not None:
                    held = scope[key] = replace(held, mutation=None)
                return held
            if held.mutation is not None and store.owns_history(root, held.mutation.history):
                return held
            publication = scope[('verified-publication', identity, run)]
            history = store.bind_history(root, store.VerifiedHistory(run, held.rows))
            mutation = RunMutation(root, history, publication, key, self.validate_append)
            held = scope[key] = replace(held, mutation=mutation)
            scope[('verified-history', identity, run)] = history
            return held
        publication_key = ('verified-publication', identity, run)
        publication = scope.get(publication_key) if scope is not None else None
        if force:
            read_context.forget_observation()
            # A failed forced acquisition must not reveal an older view to
            # any nested or enclosing read in this public operation.
            for owner in (scope, read_context.call_scope()):
                if owner is not None:
                    owner.pop(key, None)
                    owner.pop(publication_key, None)
                    owner.pop(('run-decisions', identity, run), None)
                    owner.pop(('verified-history', identity, run), None)
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
                documents=RUN_DOCUMENTS)
            publication = self._publication(run, registered, acquired)
        history = store.read_history(root, run)
        state = self.validate_history(run, publication.prepared, history, publication.evidence,
                                      publication.verified_objects)
        state.seal()
        mutation = (RunMutation(root, history, publication, key, self.validate_append)
                    if scope is not None and store.owns_history(root, history) else None)
        held = RunView(publication.directory, publication.registered, publication.prepared,
                       publication.consumer, state.rows, publication.evidence, state, publication.artifacts,
                       publication.acquired.manifest, mutation)
        # A failed validation never becomes reusable state.
        if scope is not None:
            scope[publication_key] = publication
            scope[key] = held
        return held
