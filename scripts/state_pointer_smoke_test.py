#!/usr/bin/env python3
"""A JSON Pointer array index means what RFC 6901 says it means.

An array index is "0" or a digit string with no leading zero (RFC 6901 section
4). Python's int() is wider: it reads "-1" as the last element and "01" as 1, so
a pointer the contract refuses resolved anyway, changed an inventory, and the
resulting snapshot validated as legitimate. The same tokens remain valid object
keys, which is why the rule applies only where the container is an array.

Section 5 also separates the two pointers that look like a root: "" addresses the
whole document, and "/" addresses the member whose name is the empty string.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import state_protocol as sp  # noqa: E402

WORLD = {"inventory_state": {"items": ["P01", "P02", "P03"]}}

REFUSED_INDEXES = ("-1", "01", "+1", "1.0", "", " 1", "-0")
ACCEPTED_INDEXES = ("0", "1", "2")


def main() -> int:
    errors: list[str] = []
    stats: dict[str, object] = {}

    # Every operation that reaches an array refuses a token the contract does not allow.
    refused: dict[str, list[str]] = {}
    for operation in ("remove", "set", "replace", "append", "increment"):
        refused[operation] = []
        for token in REFUSED_INDEXES:
            world = copy.deepcopy(WORLD)
            change = {"operation": operation, "path": f"/inventory_state/items/{token}", "value": "X"}
            if operation == "increment":
                change["value"] = 1
            try:
                sp.apply_change(world, change)
            except ValueError:
                refused[operation].append(token)
                continue
            errors.append(f"{operation} accepted array index {token!r}")
        if world["inventory_state"]["items"] != WORLD["inventory_state"]["items"]:
            errors.append(f"{operation} changed the document while being refused")
    stats["refused_indexes"] = refused

    # A well formed index still works.
    for token in ACCEPTED_INDEXES:
        world = copy.deepcopy(WORLD)
        try:
            sp.apply_change(world, {"operation": "remove", "path": f"/inventory_state/items/{token}"})
        except ValueError as error:
            errors.append(f"remove refused a valid index {token!r}: {error}")
            continue
        if len(world["inventory_state"]["items"]) != 2:
            errors.append(f"remove at {token!r} did not remove exactly one item")

    # An index past the end is refused rather than silently appended to.
    world = copy.deepcopy(WORLD)
    try:
        sp.apply_change(world, {"operation": "remove", "path": "/inventory_state/items/9"})
        errors.append("remove accepted an index past the end")
        out_of_range_refused = False
    except ValueError:
        out_of_range_refused = True
    stats["out_of_range_refused"] = out_of_range_refused

    # Reading follows the same rule and reports the absence rather than the last element.
    read_last = sp.get_pointer({"a": [1, 2, 3]}, "/a/-1", missing="MISSING")
    read_leading_zero = sp.get_pointer({"a": [1, 2, 3]}, "/a/01", missing="MISSING")
    read_valid = sp.get_pointer({"a": [1, 2, 3]}, "/a/1", missing="MISSING")
    if read_last != "MISSING":
        errors.append(f"get_pointer resolved '/a/-1' to {read_last!r}")
    if read_leading_zero != "MISSING":
        errors.append(f"get_pointer resolved '/a/01' to {read_leading_zero!r}")
    if read_valid != 2:
        errors.append(f"get_pointer resolved '/a/1' to {read_valid!r}")

    # The same tokens remain ordinary object keys.
    object_keys = {
        token: sp.get_pointer({"m": {token: "ok"}}, f"/m/{token}", missing="MISSING")
        for token in ("-1", "01")
    }
    for token, value in object_keys.items():
        if value != "ok":
            errors.append(f"object key {token!r} is no longer reachable: {value!r}")
    stats["object_keys_reachable"] = all(value == "ok" for value in object_keys.values())

    # "" is the whole document; "/" is the member named by the empty string.
    root_tokens = sp.decode_pointer("")
    empty_key_tokens = sp.decode_pointer("/")
    if root_tokens != []:
        errors.append(f"decode_pointer('') returned {root_tokens!r}")
    if empty_key_tokens != [""]:
        errors.append(f"decode_pointer('/') returned {empty_key_tokens!r}")
    empty_key_read = sp.get_pointer({"": "value"}, "/", missing="MISSING")
    if empty_key_read != "value":
        errors.append(f"get_pointer('/') returned {empty_key_read!r}")
    stats["root_and_empty_key_separated"] = root_tokens == [] and empty_key_tokens == [""]

    # A broken escape is a name, not a crash.
    broken = sp.get_pointer({"a~b": "value"}, "/a~b", missing="MISSING")
    stats["unfinished_escape_reads_literally"] = broken == "value"
    if broken != "value":
        errors.append(f"get_pointer('/a~b') returned {broken!r}")

    report = {"ok": not errors, "errors": errors, "stats": stats}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
