"""Aggregate observed workflow effort from local diagnostic operation records.

The report measures recorded calls and intervals, never creative quality,
comprehension, authority or unobserved work outside these CLI operations.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import json
import math
from pathlib import Path

import execution_contract as c
import operation_context as operations


RECOVERY_COMMANDS = frozenset({'resume', 'receive-external', 'recover-publication', 'record-save'})
PROVIDER_PHASES = frozenset({'provider-wait', 'provider-lookup', 'reference-upload', 'provider-watch'})
STAGE_ENDS = frozenset({'stage_completed', 'stage_failed', 'stage_cancelled', 'stage_exited'})
READING_FIELDS = ('delivered_pages', 'delivered_bytes', 'reused_bytes')


def _number(value) -> float | None:
    return float(value) if (isinstance(value, (int, float)) and not isinstance(value, bool)
        and math.isfinite(value) and value >= 0) else None


def _time(value) -> float | None:
    try:
        stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return stamp.timestamp() if stamp.tzinfo is not None else None
    except (AttributeError, TypeError, ValueError, OverflowError):
        return None


def _counter() -> dict:
    return {'calls': 0, 'completed_calls': 0, 'failed_calls': 0, 'waiting_calls': 0,
            'incomplete_calls': 0, 'seconds': 0.0, 'timed_calls': 0}


def _events(folder: Path) -> tuple[list[dict], bool]:
    """Keep complete events of an interrupted final write and mark the gap."""
    rows, complete = [], True
    with c.local(folder, 'events.jsonl').open(encoding='utf-8') as stream:
        for line in stream:
            if not line.strip():
                continue
            if not line.endswith('\n'):
                complete = False
                break
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError('an operation event must be an object')
            rows.append(value)
    return rows, complete


def summarize(root: Path | None = None, *, run: str | None = None,
              operation_id: str | None = None) -> dict:
    """Read each selected metadata/event stream once, retaining incomplete scope.

    Stage durations are inclusive and may overlap. Command totals are process
    time sums; top-level totals omit child calls whose parent covers them.
    Neither is a measurement of session elapsed time or author thinking time.
    """
    active = operations.current()
    by_command = defaultdict(_counter)
    by_stage = defaultdict(lambda: {'calls': 0, 'seconds': 0.0, 'failed_calls': 0})
    reading = {key: 0 for key in READING_FIELDS}
    reading.update(reported_calls=0, snapshots=0)
    edits = {'calls': 0, 'changed_calls': 0, 'unchanged_calls': 0, 'targets': []}
    edit_targets = defaultdict(int)
    plans, snapshots, timeline, diagnostics = {}, set(), [], []
    categories = defaultdict(int)
    rows = []
    unchanged_retries = 0
    try:
        folders = operations._log_folders(root)
        for folder in folders:
            if (active is not None and folder.name == active.id) or (
                    operation_id is not None and folder.name != operation_id):
                continue
            try:
                metadata = c.load(c.local(folder, 'operation.json'))
                if (not isinstance(metadata, dict) or metadata.get('operation_id') != folder.name
                        or not isinstance(metadata.get('context'), dict)
                        or not isinstance(metadata.get('arguments'), dict)):
                    raise ValueError('operation metadata differs from its owner')
                if run is not None and metadata['context'].get('run') != run:
                    continue
                events, stream_complete = _events(folder)
                command = metadata.get('command', 'unknown')
                subcommand = metadata['arguments'].get('command')
                if not isinstance(command, str) or (subcommand is not None and not isinstance(subcommand, str)):
                    raise ValueError('operation command must be text')
                label = command + (':' + subcommand if subcommand else '')
                end = events[-1] if events and events[-1].get('event') == 'completed' else None
                completed = bool(end is not None and stream_complete)
                duration = _number(end.get('duration_seconds')) if completed else None
                exit_code = end.get('exit_code') if completed else None
                log_complete = bool(completed and end.get('complete'))
                failed = completed and exit_code not in {0, operations.WAITING_EXIT}
                row = {'operation_id': folder.name, 'command': label, 'subcommand': subcommand,
                    'parent': metadata.get('parent_operation'), 'created_at': metadata.get('created_at'),
                    'seconds': duration, 'completed': completed, 'failed': failed,
                    'waiting': completed and exit_code == operations.WAITING_EXIT,
                    'log_complete': log_complete}
                rows.append(row)
                counter = by_command[label]
                counter['calls'] += 1
                counter['completed_calls'] += int(completed)
                counter['failed_calls'] += int(failed)
                counter['waiting_calls'] += int(row['waiting'])
                counter['incomplete_calls'] += int(not completed)
                if duration is not None:
                    counter['seconds'] += duration
                    counter['timed_calls'] += 1
                if failed:
                    from production_diagnostics import failure_category
                    reported = next((event for event in reversed(events)
                        if event.get('event') == 'command_result'), {})
                    codes = {code for code in reported.get('failure_codes', []) if isinstance(code, str)}
                    terminal = end.get('diagnostic')
                    if isinstance(terminal, dict) and isinstance(terminal.get('code'), str):
                        codes.add(terminal['code'])
                    classified = {failure_category(code) for code in codes}
                    if reported.get('unclassified_failure') is True or not classified:
                        classified.add('unclassified')
                    for category in classified:
                        categories[category] += 1
                reported_reading = False
                for event in events:
                    kind = event.get('event')
                    if kind in STAGE_ENDS:
                        seconds = _number(event.get('duration_seconds'))
                        phase = event.get('phase')
                        if isinstance(phase, str) and seconds is not None:
                            stage = by_stage[phase]
                            stage['calls'] += 1
                            stage['seconds'] += seconds
                            stage['failed_calls'] += int(kind in {'stage_failed', 'stage_cancelled'}
                                or (kind == 'stage_exited' and event.get('exit_code', 0) != 0))
                    elif kind == 'reading_progress':
                        reported_reading = True
                        for key in READING_FIELDS:
                            value = _number(event.get(key))
                            if value is not None:
                                reading[key] += int(value)
                        if isinstance(event.get('snapshot'), str):
                            snapshots.add(event['snapshot'])
                    elif kind == 'authored_edit':
                        edits['calls'] += 1
                        changed = event.get('changed')
                        edits['changed_calls'] += int(changed is True)
                        edits['unchanged_calls'] += int(changed is False)
                        choices, pointer = event.get('choices'), event.get('pointer')
                        if isinstance(choices, str) and isinstance(pointer, str):
                            edit_targets[(choices, pointer)] += 1
                    elif kind == 'plan_continuation':
                        identifier = event.get('plan_id') or event.get('plan_file')
                        at = _time(event.get('at'))
                        if isinstance(identifier, str) and at is not None:
                            previous = plans.get(identifier)
                            if previous is None or (_time(previous.get('at')) or 0) <= at:
                                plans[identifier] = {key: event[key] for key in (
                                    'plan_id', 'plan_file', 'task_id', 'items', 'choices', 'run',
                                    'state', 'next_operation', 'at') if key in event}
                        unchanged_retries += int(event.get('unchanged_since_previous') is True)
                    elif kind in {'judgment_pending', 'judgment_answered', 'judgment_superseded'}:
                        timeline.append({'plan_id': metadata['context'].get('plan_id'), **event})
                reading['reported_calls'] += int(reported_reading)
            except (ValueError, OSError, TypeError, KeyError) as exc:
                diagnostics.append({'operation_id': folder.name, 'file': str(folder),
                    'code': 'LOG_RECORD_UNREADABLE', 'message': str(exc),
                    'required_action': 'Inspect this diagnostic directory or restore its original log copy; '
                        'the other operations remain in this partial measurement.'})
    except (ValueError, OSError, TypeError) as exc:
        diagnostics.append({'code': 'LOG_RECORD_UNREADABLE', 'file': str(root) if root else None,
            'message': str(exc), 'required_action': 'Restore access to the operation log directory and repeat logs --summary.'})
    reading['snapshots'] = len(snapshots)
    edits['targets'] = [{'choices': name, 'pointer': pointer, 'calls': count}
        for (name, pointer), count in sorted(edit_targets.items())]
    pending, intervals, superseded = {}, [], []
    for event in sorted(timeline, key=lambda item: _time(item.get('at')) or 0):
        key = (event.get('plan_id'), event.get('answer_file'))
        at = _time(event.get('at'))
        if at is None or not all(isinstance(value, str) for value in key):
            continue
        if event['event'] == 'judgment_pending':
            pending.setdefault(key, at)
        elif key in pending:
            target = superseded if event['event'] == 'judgment_superseded' else intervals
            target.append(max(0.0, at - pending.pop(key)))
    totals = _counter()
    for counter in by_command.values():
        for key, value in counter.items():
            totals[key] += value
    totals.update(recovery_calls=sum(row['subcommand'] in RECOVERY_COMMANDS for row in rows),
        unchanged_continuations=unchanged_retries,
        top_level_seconds=sum(row['seconds'] or 0 for row in rows if not row['parent']))
    result = {'ok': not diagnostics, 'partial': bool(diagnostics or any(not row['log_complete'] for row in rows)),
        'scope': {'root': str(root) if root else None, 'run': run, 'operation': operation_id},
        'totals': totals, 'by_command': [{'command': key, **value} for key, value in sorted(by_command.items())],
        'by_stage': [{'phase': key, **value} for key, value in sorted(by_stage.items())],
        'failures_by_category': dict(sorted(categories.items())),
        'reading': reading, 'editing': edits,
        'provider': {'stages': [{'phase': key, **value} for key, value in sorted(by_stage.items())
            if key in PROVIDER_PHASES], 'external_host_seconds': None},
        'judgment_pending': {'completed_intervals': len(intervals), 'seconds': sum(intervals) if intervals else None,
            'superseded_intervals': len(superseded), 'superseded_seconds': sum(superseded) if superseded else None,
            'open_intervals': len(pending), 'active_author_seconds': None},
        'plans': [plans[key] for key in sorted(plans)], 'diagnostics': diagnostics,
        'measurement': {
            'command_seconds': 'Sum of recorded command durations, including nested processes; not wall-clock elapsed time.',
            'top_level_seconds': 'Sum of commands with no recorded parent; concurrent commands can overlap.',
            'stage_seconds': 'Inclusive stage durations; nested stages can overlap and must not be added as elapsed time.',
            'reading': 'Source UTF-8 bytes and delivered pages recorded by the reader; not JSON output or comprehension.',
            'editing': 'Successful structured edit calls only; external editor actions and rejected edits are not counted here.',
            'recovery': 'Explicit resume, receive-external, recover-publication and record-save calls.',
            'unchanged_continuations': 'Plan observations whose compared current input did not change; no retry is blocked.',
            'judgment_pending': 'Recorded pending-to-answered intervals include downtime; an edited answer is not '
                'proof of successful application. Superseded unanswered intervals are separate, and active human thinking is unmeasured.',
            'failure_categories': 'Failed calls counted once in each current reported repair category; a call may have '
                'multiple categories. Uncoded failures remain unclassified; process exit meanings are unchanged.',
            'provider': 'Recorded in-process provider stages; host-tool time and image quality are not inferred.',
            'coverage': 'Missing logs, older uninstrumented calls and external work cannot be reconstructed.'}}
    return operations.safe_value(result, secrets=operations._secrets())
