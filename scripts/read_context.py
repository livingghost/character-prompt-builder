"""Own acquired values for a complete operation, including its persistence.

Successful transactions publish their in-memory successors to the operation.
Rollback restores the previous observation. Only a new observation of external
change or an explicit fresh acquisition discards acquired content.
"""
from __future__ import annotations
import contextlib
import contextvars
import functools
import os
import threading
from pathlib import Path
from typing import Iterator

_PUBLIC_CALL: contextvars.ContextVar[dict|None] = contextvars.ContextVar('cpb_public_call', default=None)
class _Resources(dict):
    """A copied context cannot extend a completed operation's resource life."""

    def __init__(self):
        super().__init__()
        self.active = True
        self.execution = (os.getpid(), threading.get_ident())
        self.observation = object()

    @property
    def usable(self):
        return self.active and self.execution == (os.getpid(), threading.get_ident())


_RESOURCES: contextvars.ContextVar[_Resources|None] = contextvars.ContextVar('cpb_read_resources', default=None)

_TRANSACTIONS: contextvars.ContextVar[dict[int,tuple[object,dict]]] = contextvars.ContextVar(
    'cpb_transaction_reads', default={})

@contextlib.contextmanager
def public_call(*, fresh: bool = False, isolated: bool = False) -> Iterator[None]:
    """Share verified content among the stages of one public call.

    Nested blocks share their caller unless ``fresh`` requests a new external
    observation. A new boundary ends reuse in its enclosing call as well;
    leaving it must not restore an older successful read after a newer failure.
    Active transaction readers also discard their earlier observations.
    Resource handles live until the owning operation finishes.
    An isolated operation owns a different SQL snapshot and leaves its caller's
    in-progress snapshot intact.
    """
    resources = _RESOURCES.get()
    expired = resources is not None and not resources.usable
    if not fresh and not isolated and _PUBLIC_CALL.get() is not None and not expired:
        yield
        return
    inherited_tokens = None
    if expired or isolated:
        import production_store as store
        inherited_tokens = (store._CONNECTIONS.set({}), store._READERS.set({}), _TRANSACTIONS.set({}))
    if fresh:
        forget_observation()
        import production_store as store
        enclosing = [call_scope(), *(_transaction_scope(connection)
                                    for connection in store._CONNECTIONS.get().values())]
    else:
        enclosing = []
    for scope in enclosing:
        if scope is not None:
            scope.clear()
    resource_token = _RESOURCES.set(_Resources()) if resources is None or expired or isolated else None
    token=_PUBLIC_CALL.set({})
    try:
        import protocol_contract
        with protocol_contract.read_scope(fresh=fresh):
            yield
    finally:
        for scope in enclosing:
            if scope is not None:
                scope.clear()
        _PUBLIC_CALL.reset(token)
        if resource_token is not None:
            resources = _RESOURCES.get()
            resources.active = False
            _RESOURCES.reset(resource_token)
            for resource in reversed(tuple(resources.values())):
                resource.close()
        if inherited_tokens is not None:
            store._CONNECTIONS.reset(inherited_tokens[0])
            store._READERS.reset(inherited_tokens[1])
            _TRANSACTIONS.reset(inherited_tokens[2])

def resource(key, acquire):
    """Keep an I/O handle through the current operation and close it once."""
    resources = _RESOURCES.get()
    if resources is None or not resources.usable:
        raise RuntimeError('resource acquisition requires a public operation')
    if key not in resources:
        resources[key] = acquire()
    return resources[key]

def begin_transaction(connection) -> None:
    """Branch the operation's owned values without copying their contents."""
    parent = call_scope()
    scope = dict(parent) if parent is not None else {}
    scope[('transaction-owner',)] = object()
    _TRANSACTIONS.set({**_TRANSACTIONS.get(), id(connection): (connection, scope)})

def transaction_token(connection):
    """Identify this transaction, even when its connection is reused later."""
    resources = _RESOURCES.get()
    if resources is not None and not resources.usable:
        return None
    return _transaction_scope(connection).setdefault(('transaction-owner',), object())

def forget_observation() -> None:
    """Make explicit reacquisition survive a later SQL savepoint rollback."""
    resources = _RESOURCES.get()
    if resources is not None and resources.usable:
        resources.observation = object()

def transaction_checkpoint(connection):
    return (dict(_transaction_scope(connection)), _RESOURCES.get().observation)

def commit_transaction(connection, before: dict) -> None:
    """Publish changed owned values after SQL commit, without reading storage."""
    current = _transaction_scope(connection)
    parent = call_scope()
    if parent is None or parent is current:
        return
    absent = object()
    for key in before.keys() - current.keys():
        if parent.get(key, absent) is before[key]:
            parent.pop(key, None)
    for key, value in current.items():
        if key != ('transaction-owner',) and before.get(key, absent) is not value:
            parent[key] = value

def restore_transaction(connection, checkpoint) -> None:
    """Restore a savepoint's predecessor values and retire its writer handles."""
    scope = _transaction_scope(connection)
    scope.clear()
    before, observation = checkpoint
    if _RESOURCES.get().observation is observation:
        scope.update(before)
    scope[('transaction-owner',)] = object()

def _transaction_scope(connection) -> dict:
    import production_store as store
    scopes = _TRANSACTIONS.get()
    held = scopes.get(id(connection))
    if held is None or held[0] is not connection:
        open_now = {id(item) for item in store._CONNECTIONS.get().values()}
        scopes = {key: item for key, item in scopes.items() if key in open_now}
        held = (connection, {})
        scopes[id(connection)] = held
        _TRANSACTIONS.set(scopes)
    return held[1]

def release_transaction(connection) -> None:
    """Dispose the completed connection's read state in its execution context."""
    scopes = _TRANSACTIONS.get()
    if id(connection) in scopes:
        _TRANSACTIONS.set({key: value for key, value in scopes.items() if key != id(connection)})

def operation(function):
    """Give a public Python operation the same read boundary as a CLI call."""
    @functools.wraps(function)
    def call(*args, **kwargs):
        with public_call():
            return function(*args, **kwargs)
    return call

def invalidate_runs(root: Path, *, source_boundary: bool = False) -> None:
    """Discard observations changed outside their in-memory mutation owner."""
    import production_store as store
    identity = str(Path(root).resolve())
    invalidate_studio(root)
    scopes = []
    connection = store._CONNECTIONS.get().get(identity)
    if connection is not None:
        scopes.append(_transaction_scope(connection))
    if connection is None or source_boundary:
        scopes.append(call_scope())
    for scope in scopes:
        if scope is not None:
            for key in tuple(scope):
                if (isinstance(key, tuple) and len(key) >= 2 and key[1] == identity
                        and key[0] in {'verified-run', 'run-decisions', 'verified-history', 'run-journal',
                                       'current-authority'}):
                    del scope[key]
                elif source_boundary and isinstance(key, tuple) and key[:2] == ('verified-publication',identity):
                    del scope[key]

def invalidate_studio(root: Path) -> None:
    """End the current Studio read phase after an owned write or rollback.

    Reference readers retain the phase identity with their decoded values. A
    new marker makes even a resolver passed through nested calls reacquire its
    mutable Studio inputs before using them again. Immutable run content stays
    with the operation across persistence boundaries.

    """
    import production_store as store
    identity = str(Path(root).resolve())
    # A run can reference another Studio, including while its own transaction
    # remains open. Every active reference reader must observe an owned source
    # write, not only readers in the changed Studio's transaction.
    scopes = [call_scope(), *(_transaction_scope(connection)
                             for connection in store._CONNECTIONS.get().values())]
    marker = object()
    for scope in scopes:
        if scope is not None:
            scope[('studio-read-phase', identity)] = marker

def call_scope() -> dict|None:
    """What the current public call has verified, or None outside any call.

    The call is the open `public_call()` block, else the current operation, else
    the outermost open production transaction. Fixed runtime and execution
    journal owners share this operation lifetime as well.
    """
    import production_store as store
    resources = _RESOURCES.get()
    if resources is not None and not resources.usable:
        return None
    scope=_PUBLIC_CALL.get()
    if scope is not None:return scope
    from operation_context import current
    operation=current()
    if operation is not None:
        scope=getattr(operation,'_verified_content',None)
        if scope is None:scope=operation._verified_content={}
        return scope
    connections=store._CONNECTIONS.get()
    return _transaction_scope(next(iter(connections.values()))) if connections else None

def check_scope(root:Path) -> dict|None:
    """The operation's current values, including an active writer's successors."""
    import production_store as store
    resources = _RESOURCES.get()
    if resources is not None and not resources.usable:
        return None
    connection=store._CONNECTIONS.get().get(str(Path(root).resolve()))
    return _transaction_scope(connection) if connection is not None else call_scope()
