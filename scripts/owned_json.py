"""Immutable JSON values and explicit editable exports at read boundaries.

The containers retain Python's JSON object/array interfaces, so validation and
serialization consume the owned value directly. Ordinary mutations fail at
every depth. An editable export is a separate graph made with ``mutable``;
``copy.deepcopy`` has the same export behavior for existing editing builders.
"""
from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any


_SCALAR_TYPES = frozenset((str, int, float, bool, bytes, type(None)))


def _immutable(*args, **kwargs):
    raise TypeError('owned JSON is read-only; request an editable export')


class FrozenDict(dict):
    """A JSON object whose values belong to its read owner."""

    __slots__ = ()
    __setitem__ = __delitem__ = clear = pop = popitem = setdefault = update = __ior__ = _immutable

    def __new__(cls, *args, **kwargs):
        result = dict.__new__(cls)
        dict.__init__(result, *args, **kwargs)
        return result

    def __init__(self, *args, **kwargs):
        # Construction happens in __new__; calling __init__ again cannot edit
        # an already acquired value.
        pass

    def __copy__(self):
        return dict(self)

    def __deepcopy__(self, memo):
        result = {}
        memo[id(self)] = result
        result.update((key, copy.deepcopy(value, memo)) for key, value in self.items())
        return result


class FrozenList(list):
    """A JSON array whose members belong to its read owner."""

    __slots__ = ()
    __setitem__ = __delitem__ = append = clear = extend = insert = pop = remove = reverse = sort = _immutable
    __iadd__ = __imul__ = _immutable

    def __new__(cls, *args):
        result = list.__new__(cls)
        list.__init__(result, *args)
        return result

    def __init__(self, *args):
        pass

    def __copy__(self):
        return list(self)

    def __deepcopy__(self, memo):
        result = []
        memo[id(self)] = result
        result.extend(copy.deepcopy(value, memo) for value in self)
        return result


def freeze(value: Any) -> Any:
    """Acquire a nested JSON value, sharing children that are already owned."""
    return _freeze(value, {})


def _freeze(value: Any, memo: dict[int, Any]) -> Any:
    kind = type(value)
    # Acquisition walks many scalar leaves. They already are immutable and
    # need neither container dispatch nor an entry in the alias memo.
    if kind in _SCALAR_TYPES:
        return value
    if isinstance(value, (FrozenDict, FrozenList)):
        return value
    identity = id(value)
    if identity in memo:
        return memo[identity]
    if kind is dict:
        result = FrozenDict((key, _freeze(item, memo)) for key, item in value.items())
    elif kind is list:
        result = FrozenList(_freeze(item, memo) for item in value)
    elif isinstance(value, Mapping):
        result = FrozenDict((key, _freeze(item, memo)) for key, item in value.items())
    elif isinstance(value, list):
        result = FrozenList(_freeze(item, memo) for item in value)
    elif isinstance(value, tuple):
        result = tuple(_freeze(item, memo) for item in value)
    elif isinstance(value, set):
        result = frozenset(_freeze(item, memo) for item in value)
    else:
        return value
    memo[identity] = result
    return result


def mutable(value: Any) -> Any:
    """Export independent editable JSON containers for an actual editing step."""
    if isinstance(value, Mapping):
        return {key: mutable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [mutable(item) for item in value]
    return value


def json_type(value: Any) -> type:
    """Identify JSON containers independently of ownership, keeping scalar types."""
    if isinstance(value, dict):
        return dict
    if isinstance(value, list):
        return list
    return type(value)
