"""Durable operator events and rebuildable, chronological Studio projections.

Formal requests, approvals and images remain with their owning workflows. This
journal records transitions, never grants authority. Projection failures do not
undo a committed transition or turn it into a reason to submit another request.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import os
import uuid

import execution_contract as c


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def chronological(value: str | None) -> float:
    """Sort timezone-aware recorded times, never filesystem modification times."""
    try:
        stamp = datetime.fromisoformat((value or '').replace('Z', '+00:00'))
        return stamp.timestamp() if stamp.tzinfo is not None else float('-inf')
    except (ValueError, TypeError, OverflowError):
        return float('-inf')


def scope(path: Path) -> Path:
    import studio
    selected = path if path.is_dir() else path.parent
    return studio.studio_root(selected.resolve()) or selected.resolve()


def event(root: Path, kind: str, subject: str, *, revision: str | None = None,
          details: dict[str, Any] | None = None, at: str | None = None) -> dict:
    """Append an immutable, redacted event; an explicit revision makes retries idempotent."""
    from operation_context import current_operation_id, safe_value, known_secrets
    root = root.resolve()
    identity = c.content_id({'kind': kind, 'subject': subject, 'revision': revision}) if revision else uuid.uuid4().hex
    target = c.local(root, f'work/activity/events/{identity[:2]}/{identity}.json', exists=False)
    with c.lock(root):
        if target.exists():
            return c.load(target)
        value = {'event_id': identity, 'at': at or timestamp(), 'event': kind, 'subject': subject,
                 'revision': revision, 'operation_id': current_operation_id(),
                 'details': safe_value(details or {}, secrets=known_secrets())}
        c.atomic(target, c.encoded(value))
        dirty = root / 'work/activity/projections-pending.json'
        c.atomic_write_json(dirty, {'event_id': identity, 'at': value['at']})
    return value


def read_events(root: Path) -> tuple[list[dict], list[dict]]:
    rows, diagnostics = [], []
    directory = root / 'work/activity/events'
    for path in sorted(directory.glob('*/*.json')):
        try:
            value = c.load(path)
            if not isinstance(value, dict) or value.get('event_id') != path.stem:
                raise ValueError('event identifier differs from its file')
            if any(not isinstance(value.get(key), str) or not value[key] for key in ('at', 'event', 'subject')):
                raise ValueError('event time, kind and subject must be nonempty strings')
            if chronological(value['at']) == float('-inf') or not isinstance(value.get('details'), dict):
                raise ValueError('event needs a timezone-aware time and object details')
            rows.append(value)
        except (ValueError, OSError, KeyError) as exc:
            diagnostics.append({'path': path.relative_to(root).as_posix(), 'message': str(exc)})
    rows.sort(key=lambda row: (chronological(row.get('at')), row['event_id']))
    return rows, diagnostics


def write_timeline(root: Path) -> dict:
    """JSONL and Markdown are displays of immutable event records, not another authority."""
    rows, diagnostics = read_events(root)
    target = root / 'work/activity'
    target.mkdir(parents=True, exist_ok=True)
    raw = b''.join((json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n').encode('utf-8') for row in rows)
    c.atomic(target / 'timeline.jsonl', raw, replace=True)
    lines = ['# Activity timeline', '', 'Generated from immutable operator events. Approval evidence remains with its owner.', '']
    for row in rows:
        text = json.dumps(row['details'], ensure_ascii=False, sort_keys=True).replace('\n', ' ')
        lines.extend([f"## {row['at']} | {row['event']}", '', f"Subject: `{row['subject']}`", '', text, ''])
    if diagnostics:
        lines.extend(['## Unavailable event records', '', json.dumps(diagnostics, ensure_ascii=False, indent=2), ''])
    c.atomic(target / 'timeline.md', '\n'.join(lines).encode('utf-8'), replace=True)
    return {'events': len(rows), 'diagnostics': diagnostics}


def refresh(root: Path) -> dict:
    """Rebuild displays after a commit. Keep a durable retry marker on failure."""
    import studio
    root = root.resolve()
    with c.lock(root):
        try:
            # A post-commit logging error may have left a redacted retry receipt.
            pending_errors = []
            for queued in sorted((root / 'work/activity/pending-events').glob('*.json')):
                try:
                    pending_event = c.load(queued)
                    c.exact(pending_event, {'kind', 'subject', 'revision', 'details', 'at'}, 'pending activity receipt')
                    for key in ('kind', 'subject', 'revision', 'at'):
                        c.text(pending_event[key], 'pending activity ' + key)
                    if chronological(pending_event['at']) == float('-inf') or not isinstance(pending_event['details'], dict):
                        raise ValueError('pending activity receipt has invalid time or details')
                    event(root, pending_event['kind'], pending_event['subject'],
                          revision=pending_event['revision'], details=pending_event['details'], at=pending_event['at'])
                    queued.unlink()
                except (ValueError, OSError, KeyError, TypeError) as exc:
                    # Keep this receipt and diagnose it; a broken old log must
                    # not prevent the current gallery from being published.
                    pending_errors.append({'path': queued.relative_to(root).as_posix(), 'message': str(exc)})
            timeline = write_timeline(root)
            if (root / studio.MANIFEST).is_file():
                studio.write_gallery(root)
            pending = root / 'work/activity/projections-pending.json'
            if pending_errors:
                warning = {'ok': False, 'code': 'ACTIVITY_RECORD_PENDING',
                           'message': 'Displays were refreshed; some activity receipts still need repair.',
                           'committed_state_retained': True, 'views_refreshed': True,
                           'diagnostics': pending_errors, 'timeline': timeline, 'retry': 'studio.py sync'}
                c.atomic_write_json(pending, warning)
                _warn_operation(warning)
                return warning
            if pending.exists():
                pending.unlink()
            return {'ok': True, 'timeline': timeline}
        except (ValueError, OSError, KeyError, TypeError) as exc:
            warning = {'ok': False, 'code': 'PROJECTION_REFRESH_PENDING', 'message': str(exc),
                       'committed_state_retained': True, 'retry': 'studio.py sync'}
            try:
                c.atomic_write_json(root / 'work/activity/projections-pending.json', warning)
            except OSError:
                pass
            _warn_operation(warning)
            return warning


def _warn_operation(warning: dict) -> None:
    """A committed transition must not look like a request to generate again."""
    from operation_context import current
    import sys
    operation = current()
    if operation is not None:
        operation.event('projection_pending', **warning)
        print(warning['code'] + ': committed work retained; run studio.py sync to refresh displays/logs.', file=sys.stderr)


def changed(path: Path, kind: str, *, subject: str | None = None, revision: str | None = None,
            details: dict | None = None, refresh_views: bool = True) -> dict:
    root = scope(path)
    from operation_context import current
    operation = current()
    if operation is not None:
        operation.bind_studio(root)
    name = subject or os.path.relpath(path, root).replace(os.sep, '/')
    from operation_context import safe_value, known_secrets
    # A revision also identifies a retry receipt if the first event append failed.
    revision = revision or uuid.uuid4().hex
    redacted = safe_value(details or {}, secrets=known_secrets())
    recorded_at = timestamp()
    try:
        event(root, kind, name, revision=revision, details=redacted, at=recorded_at)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        warning = {'ok': False, 'code': 'ACTIVITY_RECORD_PENDING', 'message': str(exc),
                   'committed_state_retained': True, 'retry': 'studio.py sync', 'retry_receipt_saved': False}
        pending = {'kind': kind, 'subject': name, 'revision': revision, 'details': redacted, 'at': recorded_at}
        try:
            c.atomic_write_json(root / 'work/activity/pending-events' / (c.content_id(pending) + '.json'), pending)
            warning['retry_receipt_saved'] = True
            c.atomic_write_json(root / 'work/activity/projections-pending.json', warning)
        except (ValueError, OSError):
            pass
        _warn_operation(warning)
        return warning
    return refresh(root) if refresh_views else {'ok': True, 'projection_pending': True}
