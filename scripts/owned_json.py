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
        result.update((key, memo.get(id(value), value) if type(value) in _SCALAR_TYPES
                       else copy.deepcopy(value, memo)) for key, value in self.items())
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
        result.extend(memo.get(id(value), value) if type(value) in _SCALAR_TYPES
                      else copy.deepcopy(value, memo) for value in self)
        return result


def decoded_array(value: Any) -> Any:
    """Own JSON arrays after the decoder has already owned every object.

    JSON decoding creates an acyclic tree with no shared mutable containers.
    Objects arrive bottom up through ``decoded_object``; only arrays still
    need an owner, including an array at the document root.
    """
    if type(value) is list:
        return FrozenList([decoded_array(item) if type(item) is list else item for item in value])
    return value


def decoded_object(items: list[tuple[str, Any]]) -> FrozenDict:
    """Finish one decoded object, rejecting duplicate keys before ownership."""
    # Populate the unpublished owned object directly. Building an intermediate
    # dict and then copying it costs another allocation for every JSON object.
    result = dict.__new__(FrozenDict)
    dict.__init__(result, items)
    if len(result) != len(items):
        # Duplicate keys are invalid. Recover the first duplicate only on this
        # failure path, preserving the decoder's existing diagnostic.
        seen = set()
        for key, value in items:
            if key in seen:
                raise ValueError(f'duplicate JSON key: {key}')
            seen.add(key)
    for key, value in items:
        if type(value) is list:
            dict.__setitem__(result, key, decoded_array(value))
    return result


def freeze(value: Any) -> Any:
    """Acquire a nested JSON value, sharing children that are already owned."""
    return _freeze(value, {})


def json_value(value: Any) -> Any:
    """Own a value in its JSON form before deriving its serialized bytes.

    Python tuples encode as JSON arrays. Normalize them here so the in-memory
    result and a later recovery read describe the same value without decoding
    an outgoing serialization. JSON object names are strings.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError('JSON object names must be strings')
        children = {key: json_value(item) for key, item in value.items()}
        if isinstance(value, FrozenDict) and all(children[key] is item for key, item in value.items()):
            return value
        return FrozenDict(children)
    if isinstance(value, (list, tuple)):
        children = [json_value(item) for item in value]
        if isinstance(value, FrozenList) and all(left is right for left, right in zip(children, value)):
            return value
        return FrozenList(children)
    raise TypeError('value is not JSON serializable: ' + type(value).__name__)


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
        result = FrozenDict({key: item if type(item) in _SCALAR_TYPES else _freeze(item, memo)
                             for key, item in value.items()})
    elif kind is list:
        result = FrozenList([item if type(item) in _SCALAR_TYPES else _freeze(item, memo)
                             for item in value])
    elif isinstance(value, Mapping):
        result = FrozenDict({key: item if type(item) in _SCALAR_TYPES else _freeze(item, memo)
                             for key, item in value.items()})
    elif isinstance(value, list):
        result = FrozenList([item if type(item) in _SCALAR_TYPES else _freeze(item, memo)
                             for item in value])
    elif isinstance(value, tuple):
        result = tuple(item if type(item) in _SCALAR_TYPES else _freeze(item, memo) for item in value)
    elif isinstance(value, set):
        result = frozenset(item if type(item) in _SCALAR_TYPES else _freeze(item, memo) for item in value)
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
