#!/usr/bin/env python3
"""Deterministic public temporal semantics: explicit target scene and authored events."""
from __future__ import annotations
import copy
import re
from itertools import groupby
from typing import Any
from protocol_contract import canonical_json, validate_artifact, finalize_artifact, STATE_MUTATION_OPERATIONS, PROCESS_LIFECYCLE_OPERATIONS
_ARRAY_INDEX = re.compile(r"^(?:0|[1-9][0-9]*)$")
ENTITY_BUCKETS = {
    "character": "characters",
    "relationship": "relationships",
    "environment": "environments",
    "prop": "props",
    "world": "world",
}

def array_index(token: str, path: str) -> int:
    """Read one JSON Pointer token as an array index.

    RFC 6901 section 4 allows "0" or a digit string with no leading zero. Python's
    int() is wider than that: it reads "-1" as the last element and "01" as 1, so
    a pointer the contract refuses would otherwise resolve and its result would be
    written back as a legitimate state. The same token is still a valid object key,
    which is why this rule applies only where the container is an array.
    """

    if not _ARRAY_INDEX.match(token):
        raise ValueError(
            "array index must be 0 or a digit string with no leading zero, "
            f"got {token!r}: {path}"
        )
    return int(token)



def decode_pointer(path: str) -> list[str]:
    if path == "":
        return []
    if not path.startswith("/"):
        raise ValueError(f"JSON pointer must begin with '/': {path}")
    return [part.replace("~1", "/").replace("~0", "~") for part in path[1:].split("/")]



def get_pointer(root: Any, path: str, *, missing: Any = None, strict: bool = False) -> Any:
    current = root
    for token in decode_pointer(path):
        try:
            if isinstance(current, list):
                current = current[array_index(token, path)]
            elif isinstance(current, dict):
                current = current[token]
            else:
                raise KeyError(token)
        except (KeyError, IndexError, ValueError, TypeError):
            if strict:
                raise ValueError(f"path does not exist: {path}")
            return missing
    return current



def _parent_for_pointer(root: Any, path: str, *, create: bool) -> tuple[Any, str]:
    parts = decode_pointer(path)
    if not parts:
        raise ValueError("root replacement is not supported")
    current = root
    for token in parts[:-1]:
        if isinstance(current, list):
            index = array_index(token, path)
            if index >= len(current):
                if not create:
                    raise ValueError(f"path does not exist: {path}")
                while len(current) <= index:
                    current.append({})
            current = current[index]
        elif isinstance(current, dict):
            if token not in current:
                if not create:
                    raise ValueError(f"path does not exist: {path}")
                current[token] = {}
            current = current[token]
        else:
            raise ValueError(f"cannot traverse non-container at {token!r} for {path}")
    return current, parts[-1]



def apply_change(root: Any, change: dict[str, Any]) -> None:
    path = str(change["path"])
    operation = str(change["operation"])
    parent, key = _parent_for_pointer(root, path, create=operation in {"set", "replace", "merge", "append", "increment"})

    def current_value() -> Any:
        if isinstance(parent, list):
            index = array_index(key, path)
            return parent[index] if index < len(parent) else None
        return parent.get(key)

    if operation in {"set", "replace"}:
        value = copy.deepcopy(change.get("value"))
        if isinstance(parent, list):
            index = array_index(key, path)
            while len(parent) <= index:
                parent.append(None)
            parent[index] = value
        else:
            parent[key] = value
    elif operation == "merge":
        existing = current_value()
        incoming = change.get("value")
        if not isinstance(existing, dict) or not isinstance(incoming, dict):
            raise ValueError(f"merge requires object values at {path}")
        existing.update(copy.deepcopy(incoming))
    elif operation == "append":
        existing = current_value()
        if existing is None:
            existing = []
            if isinstance(parent, list):
                index = array_index(key, path)
                while len(parent) <= index:
                    parent.append(None)
                parent[index] = existing
            else:
                parent[key] = existing
        if not isinstance(existing, list):
            raise ValueError(f"append requires an array at {path}")
        incoming = change.get("value")
        if isinstance(incoming, list):
            existing.extend(copy.deepcopy(incoming))
        else:
            existing.append(copy.deepcopy(incoming))
    elif operation == "increment":
        existing = current_value()
        incoming = change.get("value")
        if not isinstance(existing, (int, float)) or isinstance(existing, bool):
            raise ValueError(f"increment requires an existing number at {path}")
        if not isinstance(incoming, (int, float)) or isinstance(incoming, bool):
            raise ValueError(f"increment requires a numeric value at {path}")
        result = existing + incoming
        if isinstance(parent, list):
            parent[array_index(key, path)] = result
        else:
            parent[key] = result
    elif operation == "remove":
        if isinstance(parent, list):
            index = array_index(key, path)
            if index >= len(parent):
                raise ValueError(f"remove path does not exist: {path}")
            parent.pop(index)
        else:
            if key not in parent:
                raise ValueError(f"remove path does not exist: {path}")
            del parent[key]
    else:
        raise ValueError(f"unsupported change operation: {operation}")



def entity_root(world: dict[str, Any], entity_type: str, entity_id: str, *, create: bool) -> dict[str, Any]:
    bucket_name = ENTITY_BUCKETS.get(entity_type)
    if not bucket_name:
        raise ValueError(f"unknown entity_type: {entity_type}")
    if bucket_name == "world":
        value = world.setdefault("world", {})
        if not isinstance(value, dict):
            raise ValueError("world bucket must be an object")
        return value
    bucket = world.setdefault(bucket_name, {})
    if not isinstance(bucket, dict):
        raise ValueError(f"world bucket must be an object: {bucket_name}")
    if entity_id not in bucket:
        if not create:
            raise ValueError(f"entity does not exist: {entity_type}:{entity_id}")
        bucket[entity_id] = {}
    value = bucket[entity_id]
    if not isinstance(value, dict):
        raise ValueError(f"entity state must be an object: {entity_type}:{entity_id}")
    return value



def precondition_holds(world: dict[str, Any], condition: dict[str, Any]) -> bool:
    entity_type = str(condition["entity_type"])
    entity_id = str(condition["entity_id"])
    bucket_name = ENTITY_BUCKETS.get(entity_type)
    if not bucket_name:
        raise ValueError(f"unknown entity_type: {entity_type}")
    marker = object()
    current: Any = marker
    # An entity the world has not introduced yet reads as an absent path rather
    # than as a failure to evaluate, so an event that introduces one can guard
    # itself with not-exists and every other operator fails this precondition
    # alone instead of stopping the whole resolve.
    if bucket_name == "world" or (
        isinstance(world.get(bucket_name), dict) and entity_id in world[bucket_name]
    ):
        root = entity_root(world, entity_type, entity_id, create=False)
        current = get_pointer(root, str(condition["path"]), missing=marker)
    operator = str(condition["operator"])
    target = condition.get("value")
    if operator == "exists":
        return current is not marker
    if operator == "not-exists":
        return current is marker
    if current is marker:
        return False
    if operator == "equals":
        return current == target
    if operator == "not-equals":
        return current != target
    if operator == "contains":
        try:
            return target in current
        except TypeError:
            return False
    raise ValueError(f"unsupported precondition operator: {operator}")



def _is_lifecycle_change(change: dict[str, Any]) -> bool:
    return str(change.get("operation")) in PROCESS_LIFECYCLE_OPERATIONS



def _state_path_key(change: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(change.get("entity_type")),
        str(change.get("entity_id")),
        str(change.get("path")),
    )



def validate_temporal_inputs(
    *,
    events: list[dict[str, Any]],
    processes: list[dict[str, Any]],
) -> list[str]:
    """Validate ledger/process references that cannot be checked in isolation."""
    errors: list[str] = []
    event_by_id: dict[str, dict[str, Any]] = {}
    process_by_id: dict[str, dict[str, Any]] = {}

    for index, event in enumerate(events):
        report = validate_artifact(event)
        if not report["ok"]:
            errors.extend(
                f"events[{index}] {event.get('event_id')!r}: {item}"
                for item in report["errors"]
            )
        event_id = str(event.get("event_id") or "")
        if event_id in event_by_id:
            errors.append(f"duplicate event_id: {event_id}")
        else:
            event_by_id[event_id] = event

    for index, process in enumerate(processes):
        report = validate_artifact(process)
        if not report["ok"]:
            errors.extend(
                f"processes[{index}] {process.get('process_id')!r}: {item}"
                for item in report["errors"]
            )
        process_id = str(process.get("process_id") or "")
        if process_id in process_by_id:
            errors.append(f"duplicate process_id: {process_id}")
        else:
            process_by_id[process_id] = process

    linked_sources: dict[str, list[tuple[dict[str, Any], dict[str, Any], int]]] = {}
    for event in events:
        event_id = str(event.get("event_id") or "")
        timeline_id = str(event.get("timeline_id") or "")
        event_order = event.get("effective_order")
        if not isinstance(event_order, int):
            continue
        for superseded_id in event.get("supersedes_event_ids", []):
            superseded = event_by_id.get(str(superseded_id))
            if superseded is None:
                errors.append(f"event {event_id}: unknown supersedes_event_id {superseded_id!r}")
                continue
            if superseded.get("timeline_id") != timeline_id:
                errors.append(
                    f"event {event_id}: superseded event {superseded_id} is on another timeline"
                )
            superseded_order = superseded.get("effective_order")
            if isinstance(superseded_order, int) and event_order <= superseded_order:
                errors.append(
                    f"event {event_id}: supersession must be strictly later than {superseded_id}"
                )

        for change_index, change in enumerate(event.get("changes", [])):
            if not isinstance(change, dict):
                continue
            process_id = change.get("process_id")
            if _is_lifecycle_change(change):
                process = process_by_id.get(str(process_id))
                if process is None:
                    errors.append(
                        f"event {event_id} changes[{change_index}]: unknown process_id {process_id!r}"
                    )
                    continue
                if process.get("timeline_id") != timeline_id:
                    errors.append(
                        f"event {event_id} changes[{change_index}]: process is on another timeline"
                    )
                if _state_path_key(change) != _state_path_key(process):
                    errors.append(
                        f"event {event_id} changes[{change_index}]: lifecycle entity/path does not match process"
                    )
                policy = process.get("interruption_policy")
                if policy != "restartable":
                    errors.append(
                        f"event {event_id} changes[{change_index}]: {policy} process rejects lifecycle actions"
                    )
                started = process.get("started_order")
                until = process.get("effective_until_order")
                if isinstance(started, int) and event_order < started:
                    errors.append(
                        f"event {event_id} changes[{change_index}]: lifecycle action precedes process start"
                    )
                if isinstance(until, int) and event_order >= until:
                    errors.append(
                        f"event {event_id} changes[{change_index}]: lifecycle action is outside process lifetime"
                    )
                if event.get("canon_status") == "approved" and process.get("canon_status") != "approved":
                    errors.append(
                        f"event {event_id} changes[{change_index}]: approved lifecycle action requires approved process"
                    )
                continue

            clear_event_id = change.get("clear_event_id")
            if clear_event_id:
                clearing = event_by_id.get(str(clear_event_id))
                if clearing is None:
                    errors.append(
                        f"event {event_id} changes[{change_index}]: unknown clear_event_id {clear_event_id!r}"
                    )
                else:
                    if clearing.get("timeline_id") != timeline_id:
                        errors.append(
                            f"event {event_id} changes[{change_index}]: clear event is on another timeline"
                        )
                    clear_order = clearing.get("effective_order")
                    if isinstance(clear_order, int) and clear_order <= event_order:
                        errors.append(
                            f"event {event_id} changes[{change_index}]: clear event must be strictly later"
                        )
                    matching_clear = any(
                        isinstance(item, dict)
                        and not _is_lifecycle_change(item)
                        and _state_path_key(item) == _state_path_key(change)
                        for item in clearing.get("changes", [])
                    )
                    if not matching_clear:
                        errors.append(
                            f"event {event_id} changes[{change_index}]: clear event has no matching entity/path change"
                        )
                    if event.get("canon_status") == "approved" and clearing.get("canon_status") != "approved":
                        errors.append(
                            f"event {event_id} changes[{change_index}]: approved state requires an approved clear event"
                        )

            if process_id:
                process = process_by_id.get(str(process_id))
                if process is None:
                    errors.append(
                        f"event {event_id} changes[{change_index}]: unknown process_id {process_id!r}"
                    )
                    continue
                linked_sources.setdefault(str(process_id), []).append(
                    (event, change, change_index)
                )
                if process.get("timeline_id") != timeline_id:
                    errors.append(
                        f"event {event_id} changes[{change_index}]: process is on another timeline"
                    )
                if _state_path_key(change) != _state_path_key(process):
                    errors.append(
                        f"event {event_id} changes[{change_index}]: process entity/path does not match change"
                    )
                if process.get("started_order") != event_order:
                    errors.append(
                        f"event {event_id} changes[{change_index}]: process must start at the event order"
                    )
                milestones = process.get("milestones", [])
                if milestones and canonical_json(milestones[0].get("state")) != canonical_json(change.get("value")):
                    errors.append(
                        f"event {event_id} changes[{change_index}]: offset-0 milestone must equal the initiating value"
                    )
                if event.get("canon_status") == "approved" and process.get("canon_status") != "approved":
                    errors.append(
                        f"event {event_id} changes[{change_index}]: approved state requires an approved process"
                    )

    for process_id, sources in linked_sources.items():
        if len(sources) > 1:
            labels = [
                f"{event.get('event_id')}[{index}]" for event, _, index in sources
            ]
            errors.append(
                f"process {process_id} has multiple initiating changes: {labels}"
            )
    return errors



def _approved_events_as_of(
    events: list[dict[str, Any]],
    *,
    timeline_id: str,
    story_order: int,
) -> list[dict[str, Any]]:
    candidates = [
        event for event in events
        if event.get("timeline_id") == timeline_id
        and event.get("canon_status") == "approved"
        and int(event.get("effective_order", story_order + 1)) <= story_order
    ]
    superseded = {
        str(superseded_id)
        for event in candidates
        for superseded_id in event.get("supersedes_event_ids", [])
    }
    return sorted(
        (
            event for event in candidates
            if str(event.get("event_id")) not in superseded
        ),
        key=lambda event: (int(event["effective_order"]), str(event["event_id"])),
    )



def _change_is_active(
    change: dict[str, Any],
    event: dict[str, Any],
    *,
    story_order: int,
    scene_context_id: str,
    active_event_ids: set[str],
    event_by_id: dict[str, dict[str, Any]],
) -> bool:
    if int(event["effective_order"]) > story_order:
        return False
    if change.get("persistence") == "scene-local":
        return scene_context_id is not None and event.get("scene_context_id") == scene_context_id
    until = change.get("effective_until_order")
    if until is not None and story_order >= int(until):
        return False
    clear_event_id = change.get("clear_event_id")
    if clear_event_id and str(clear_event_id) in active_event_ids:
        clearing = event_by_id[str(clear_event_id)]
        if int(clearing["effective_order"]) <= story_order:
            return False
    return True



def _restartable_epochs(
    process: dict[str, Any],
    actions: list[tuple[int, str, int, str]],
) -> list[tuple[str, int, int | None]]:
    process_id = str(process["process_id"])
    epochs: list[list[Any]] = [["initial", int(process["started_order"]), None]]
    active = True
    for order, event_id, change_index, operation in sorted(actions):
        if operation == "interrupt-process":
            if not active:
                raise ValueError(
                    f"process {process_id}: interrupt at {event_id}[{change_index}] targets an inactive epoch"
                )
            epochs[-1][2] = order
            active = False
        elif operation == "restart-process":
            if active:
                raise ValueError(
                    f"process {process_id}: restart at {event_id}[{change_index}] requires a prior interrupt"
                )
            epochs.append([f"restart-{event_id}-{change_index}", order, None])
            active = True
    return [(str(name), int(start), end if end is None else int(end)) for name, start, end in epochs]



def _process_operations(
    *,
    processes: list[dict[str, Any]],
    all_events: list[dict[str, Any]],
    active_events: list[dict[str, Any]],
    timeline_id: str,
    story_order: int,
    scene_context_id: str,
) -> tuple[list[tuple[int, int, str, str, dict[str, Any]]], set[str]]:
    event_by_id = {str(event["event_id"]): event for event in all_events}
    active_event_ids = {str(event["event_id"]) for event in active_events}
    source_by_process: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    for event in all_events:
        for change in event.get("changes", []):
            if (
                isinstance(change, dict)
                and not _is_lifecycle_change(change)
                and change.get("process_id")
            ):
                source_by_process[str(change["process_id"])] = (event, change)

    operations: list[tuple[int, int, str, str, dict[str, Any]]] = []
    influential_events: set[str] = set()
    for process in processes:
        if (
            process.get("timeline_id") != timeline_id
            or process.get("canon_status") != "approved"
        ):
            continue
        process_id = str(process["process_id"])
        if int(process["started_order"]) > story_order:
            continue
        source = source_by_process.get(process_id)
        if source is not None:
            source_event, source_change = source
            if (
                str(source_event.get("event_id")) not in active_event_ids
                or not _change_is_active(
                    source_change,
                    source_event,
                    story_order=story_order,
                    scene_context_id=scene_context_id,
                    active_event_ids=active_event_ids,
                    event_by_id=event_by_id,
                )
            ):
                continue

        actions: list[tuple[int, str, int, str]] = []
        for event in active_events:
            for change_index, change in enumerate(event.get("changes", [])):
                if (
                    isinstance(change, dict)
                    and _is_lifecycle_change(change)
                    and str(change.get("process_id")) == process_id
                ):
                    actions.append(
                        (
                            int(event["effective_order"]),
                            str(event["event_id"]),
                            change_index,
                            str(change["operation"]),
                        )
                    )
                    influential_events.add(str(event["event_id"]))

        policy = str(process["interruption_policy"])
        if policy == "restartable":
            epochs = _restartable_epochs(process, actions)
        else:
            epochs = [("initial", int(process["started_order"]), None)]

        if policy == "supersedable-by-event":
            cutoff_rows: list[tuple[int, str]] = []
            process_key = _state_path_key(process)
            for event in active_events:
                order = int(event["effective_order"])
                if order <= int(process["started_order"]):
                    continue
                for change in event.get("changes", []):
                    if (
                        isinstance(change, dict)
                        and not _is_lifecycle_change(change)
                        and _state_path_key(change) == process_key
                    ):
                        cutoff_rows.append((order, str(event["event_id"])))
            if cutoff_rows:
                cutoff_order, cutoff_event_id = min(cutoff_rows)
                epochs[0] = (epochs[0][0], epochs[0][1], cutoff_order)
                influential_events.add(cutoff_event_id)

        process_until = process.get("effective_until_order")
        for epoch_name, epoch_start, epoch_end in epochs:
            for milestone in process.get("milestones", []):
                offset = int(milestone["offset"])
                absolute = epoch_start + offset
                if absolute > story_order:
                    continue
                if epoch_end is not None and absolute >= epoch_end:
                    continue
                if process_until is not None and absolute >= int(process_until):
                    continue
                milestone_id = f"{process_id}@epoch-{epoch_name}:offset-{offset}"
                operations.append(
                    (
                        absolute,
                        0,
                        milestone_id,
                        "process",
                        {
                            "process_id": process_id,
                            "milestone": milestone,
                            "entity_type": process["entity_type"],
                            "entity_id": process["entity_id"],
                            "path": process["path"],
                        },
                    )
                )
    return operations, influential_events



class TemporalConflictError(ValueError):
    """Two unordered changes interfere at the requested story coordinate."""
    def __init__(self, order: int, conflicts: list[dict[str, Any]]) -> None:
        self.order = order
        self.conflicts = conflicts
        detail = "; ".join(f"{x['left']} / {x['right']}: {x['reason']}" for x in conflicts[:8])
        super().__init__(f"ambiguous operations at story_order {order}: {detail}; "
                         "use separate story coordinates or one ordered atomic event")


def _absolute_path(change: dict[str, Any]) -> tuple[str, ...]:
    kind = change['entity_type']
    return (ENTITY_BUCKETS[kind],) + (() if kind == 'world' else (change['entity_id'],)) + tuple(decode_pointer(change['path']))


def _overlap(a: tuple[str, ...], b: tuple[str, ...]) -> bool:
    return a[:len(b)] == b or b[:len(a)] == a


def _write_footprint(world: dict[str, Any], change: dict[str, Any]) -> tuple[str, ...]:
    """Array deletion/extension changes the whole indexed container, not one leaf."""
    address = _absolute_path(change)
    current: Any = world
    for index, part in enumerate(address):
        if isinstance(current, list):
            position = array_index(part, change['path'])
            if position >= len(current) or (index == len(address)-1 and change['operation'] == 'remove'):
                return address[:index]
            current = current[position]
        elif isinstance(current, dict):
            current = current.get(part)
        else:
            break
    return address


def _check_batch(world: dict[str, Any], batch: list[tuple]) -> None:
    """Check operations within a phase; clocks advance before discrete events."""
    records = []
    for order, _, identifier, kind, payload in batch:
        changes = payload['changes'] if kind == 'event' else [{**payload, 'operation': 'set'}]
        writes = [_write_footprint(world, c) for c in changes]
        reads = [_absolute_path(c) for c in payload.get('preconditions', [])] if kind == 'event' else []
        records.append((identifier, writes, reads))
    conflicts = []
    for index, (left, writes, reads) in enumerate(records):
        for right, other_writes, other_reads in records[index+1:]:
            if any(_overlap(a,b) for a in writes for b in other_writes):
                conflicts.append({'left':left, 'right':right, 'reason':'overlapping writes or array structure changes'})
            elif any(_overlap(a,b) for a in writes for b in other_reads) or any(_overlap(a,b) for a in reads for b in other_writes):
                conflicts.append({'left':left, 'right':right, 'reason':'write changes another operation precondition'})
    if conflicts:
        raise TemporalConflictError(batch[0][0], conflicts)


def apply_event(world: dict[str, Any], event: dict[str, Any]) -> None:
    for condition in event.get("preconditions", []):
        if not precondition_holds(world, condition):
            raise ValueError(f"event precondition failed: {event['event_id']}")
    staged = copy.deepcopy(world) if event.get("atomic") else world
    for change in event.get("changes", []):
        root = entity_root(staged, str(change["entity_type"]), str(change["entity_id"]), create=True)
        apply_change(root, change)
    if event.get("atomic"):
        world.clear()
        world.update(staged)



def resolve_world(
    *,
    base_state: dict[str, Any],
    events: list[dict[str, Any]],
    processes: list[dict[str, Any]],
    timeline_id: str,
    story_order: int,
    story_time: str,
    snapshot_id: str,
    scene_context_id: str | None,
) -> dict[str, Any]:
    if scene_context_id is not None and (not isinstance(scene_context_id, str) or not scene_context_id):
        raise ValueError("scene_context_id must be a non-empty explicit target")
    temporal_errors = validate_temporal_inputs(events=events, processes=processes)
    if temporal_errors:
        raise ValueError("invalid temporal inputs: " + "; ".join(temporal_errors))
    world = copy.deepcopy(base_state)
    for bucket in ("characters", "relationships", "environments", "props", "world"):
        world.setdefault(bucket, {})

    approved_events = _approved_events_as_of(
        events,
        timeline_id=timeline_id,
        story_order=story_order,
    )
    event_by_id = {str(event["event_id"]): event for event in events}
    active_event_ids = {str(event["event_id"]) for event in approved_events}
    operations, influential_events = _process_operations(
        processes=[
            process for process in processes
            if process.get("timeline_id") == timeline_id
        ],
        all_events=events,
        active_events=approved_events,
        timeline_id=timeline_id,
        story_order=story_order,
        scene_context_id=scene_context_id,
    )
    for event in approved_events:
        event_id = str(event["event_id"])
        active_changes: list[dict[str, Any]] = []
        lifecycle_present = False
        for change in event.get("changes", []):
            if _is_lifecycle_change(change):
                lifecycle_present = True
                continue
            if _change_is_active(
                change,
                event,
                story_order=story_order,
                scene_context_id=scene_context_id,
                active_event_ids=active_event_ids,
                event_by_id=event_by_id,
            ):
                active_changes.append(change)
            clear_event_id = change.get("clear_event_id")
            if clear_event_id and str(clear_event_id) in active_event_ids:
                influential_events.add(str(clear_event_id))
        if event.get("supersedes_event_ids"):
            influential_events.add(event_id)
        if active_changes or lifecycle_present or event_id in influential_events:
            payload = copy.deepcopy(event)
            payload["changes"] = active_changes
            operations.append(
                (int(event["effective_order"]), 1, event_id, "event", payload)
            )

    # An initiating event and its offset-zero milestone express the same start.
    # Apply the event once (including its preconditions), retain both provenance IDs.
    starts = {str(c['process_id']): e for e in approved_events for c in e['changes']
              if c.get('process_id') and not _is_lifecycle_change(c)}
    aliases: dict[str, list[str]] = {}
    selected = []
    for op in operations:
        _, _, identifier, kind, payload = op
        source = starts.get(payload.get('process_id')) if kind == 'process' else None
        if source is not None and identifier.endswith('@epoch-initial:offset-0'):
            aliases.setdefault(source['event_id'], []).append(identifier)
        else:
            selected.append(op)
    # Lifecycle changes to the same process need authored ordering too.
    lifecycle: dict[tuple[int,str], set[str]] = {}
    for event in approved_events:
        for change in event['changes']:
            if _is_lifecycle_change(change):
                key = (event['effective_order'], change['process_id'])
                lifecycle.setdefault(key,set()).add(event['event_id'])
    for (at, process), owners in lifecycle.items():
        if len(owners)>1:
            ordered = sorted(owners)
            raise TemporalConflictError(at,[{'left':ordered[0], 'right':ordered[1], 'reason':'unordered lifecycle actions for '+process}])

    applied_events: list[str] = []
    applied_milestones: list[str] = []
    ordered = sorted(selected, key=lambda item: (item[0], item[1], item[2]))
    for _, group in groupby(ordered, key=lambda item: (item[0], item[1])):
        batch = list(group)
        _check_batch(world, batch)
        for _, _, operation_id, operation_type, payload in batch:
            if operation_type == "event":
                apply_event(world, payload)
                applied_events.append(operation_id)
                applied_milestones.extend(sorted(aliases.get(operation_id, [])))
            else:
                root = entity_root(world, str(payload["entity_type"]), str(payload["entity_id"]), create=True)
                apply_change(root, {"path": payload["path"], "operation": "set", "value": payload["milestone"]["state"]})
                applied_milestones.append(operation_id)

    result = {
        "artifact_type": "world-state-snapshot",
        "snapshot_id": snapshot_id,
        "timeline_id": timeline_id,
        "scene_context_id": scene_context_id,
        "story_order": story_order,
        "story_time": story_time,
        "entities": world,
        "applied_event_ids": applied_events,
        "applied_process_milestones": applied_milestones,
        "uncertainties": [],
        "world_state_sha256": "0" * 64,
    }
    return finalize_artifact(result)
