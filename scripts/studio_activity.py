"""Durable operator events and rebuildable, chronological Studio projections.

Formal requests, approvals and images remain with their owning workflows. This
journal records transitions, never grants authority. Projection failures do not
undo a committed transition or turn it into a reason to submit another request.
"""
from __future__ import annotations

from datetime import datetime, timezone
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
from pathlib import Path
from typing import Any
import json
import os
import threading
import uuid

import execution_contract as c
import runtime_snapshot


ALL_VIEWS = frozenset({'gallery', 'active-references', 'story-timeline', 'activity-timeline'})


@dataclass
class _Update:
    views: set[str] = field(default_factory=set)
    receipts: list[dict] = field(default_factory=list)
    result: dict = field(default_factory=lambda: {'ok': True})


_UPDATES: ContextVar[dict[str, _Update] | None] = ContextVar('studio_view_updates', default=None)


@dataclass
class _Publication:
    active: bool = True


_PUBLICATIONS: ContextVar[dict[tuple[int, int, str], _Publication] | None] = ContextVar(
    'studio_projection_publications', default=None)


def artwork_owner(root: Path, out: Path | None = None) -> Path:
    """Gallery and active references share one publication and one decoded model."""
    root = root.resolve()
    output = Path(out or root / 'gallery.html').absolute().resolve()
    if output == root / 'gallery.html':
        return root / 'work/activity/publications/artwork'
    return output.parent / ('.' + output.name + '.publication')


@contextmanager
def publication(owner: Path):
    """Order one display's readers, publishers and receipt acknowledgements.

    Canonical Studio writers and read-only consumers do not acquire this owner.
    Nested publishers share the fresh read boundary established after admission.
    """
    identity = os.getpid(), threading.get_ident(), str(owner.resolve())
    with c.lock(owner):
        held = _PUBLICATIONS.get() or {}
        if identity in held and held[identity].active:
            yield False
            return
        admission = _Publication()
        token = _PUBLICATIONS.set({**held, identity: admission})
        try:
            with runtime_snapshot.public_call(fresh=True):
                yield True
        finally:
            # A copied context cannot prolong an owner's completed admission.
            admission.active = False
            _PUBLICATIONS.reset(token)


def publication_read(root: Path, read=None):
    """Begin a model only after its publisher has captured pending receipts."""
    import studio
    if read is None:
        return studio.StudioRead(root)
    if read.root != root.resolve():
        raise ValueError('Studio read model belongs to another Studio')
    read.reload()
    return read


def _dirty_receipts(root: Path, view: str) -> list[Path]:
    # An atomic writer's temporary file has not become a receipt yet.
    return [path for path in (root / 'work/activity/dirty' / view).glob('*')
            if not path.name.startswith(c.TEMPORARY_PREFIX)]


def _failed_view(root: Path, view: str) -> None:
    """A failed explicit refresh needs recovery even without an earlier event."""
    try:
        c.atomic(root / 'work/activity/dirty' / view / ('refresh-' + uuid.uuid4().hex), b'')
    except OSError:
        # The failure response still tells the caller to retry when storage is available.
        pass


def _acknowledge(root: Path, view: str, paths: list[Path], errors: list[dict]) -> None:
    if any(error.get('projection') == view for error in errors):
        _failed_view(root, view)
        return
    for path in paths:
        path.unlink(missing_ok=True)


def _settle_pending(root: Path) -> bool:
    """Clear first, then reconcile durable receipts so a concurrent append survives."""
    pending = root / 'work/activity/projections-pending.json'
    pending.unlink(missing_ok=True)
    outstanding = any(_dirty_receipts(root, view) for view in ALL_VIEWS) or any(
        (root / 'work/activity/pending-events').glob('*.json'))
    if outstanding:
        c.atomic_write_json(pending, {'ok': True, 'projection_pending': True,
                                    'retry': 'studio.py sync'})
    return outstanding


@contextmanager
def operation(root: Path):
    """Publish affected displays once after the outer owner operation completes.

    Events are durable immediately. Nested owners share the result dictionary,
    which is filled on exit even when an already committed operation raises.
    """
    key = str(root.resolve())
    updates = _UPDATES.get() or {}
    if key in updates:
        yield updates[key].result
        return
    update = _Update()
    token = _UPDATES.set({**updates, key: update})
    try:
        with runtime_snapshot.public_call():
            try:
                yield update.result
            finally:
                if update.views:
                    try:
                        result = refresh(root, views=update.views)
                    except (ValueError, OSError, KeyError, TypeError) as exc:
                        result = {'ok': False, 'code': 'PROJECTION_REFRESH_PENDING',
                                  'message': str(exc), 'committed_state_retained': True,
                                  'retry': 'studio.py sync'}
                        _warn_operation(result)
                    update.result.clear()
                    update.result.update(result)
                    for receipt in update.receipts:
                        receipt.clear()
                        receipt.update(result)
    finally:
        _UPDATES.reset(token)


def project_result(receipt: dict, projection: dict) -> dict:
    """Keep the owner's successful receipt and expose a deferred repair warning."""
    if not projection.get('ok', True):
        receipt['projection_warning'] = projection
    return receipt


def mutation(function=None, *, receipt: bool = True):
    """An owner command commits state before publishing its affected displays."""
    if function is None:
        return lambda selected: mutation(selected, receipt=receipt)
    @wraps(function)
    def call(path, *args, **kwargs):
        root = scope(path)
        with operation(root) as projection:
            runtime_snapshot.invalidate_studio(root)
            try:
                result = function(path, *args, **kwargs)
            finally:
                runtime_snapshot.invalidate_studio(root)
        return project_result(result, projection) if receipt and isinstance(result, dict) else result
    return call


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
          details: dict[str, Any] | None = None, at: str | None = None, views=None) -> dict:
    """Append an immutable, redacted event; an explicit revision makes retries idempotent."""
    from operation_context import current_operation_id, safe_value, known_secrets
    root = root.resolve()
    identity = c.content_id({'kind': kind, 'subject': subject, 'revision': revision}) if revision else uuid.uuid4().hex
    target = c.local(root, f'work/activity/events/{identity[:2]}/{identity}.json', exists=False)
    if target.exists():
        value = c.load(target)
    else:
        value = {'event_id': identity, 'at': at or timestamp(), 'event': kind, 'subject': subject,
                 'revision': revision, 'operation_id': current_operation_id(),
                 'details': safe_value(details or {}, secrets=known_secrets())}
        try:
            c.atomic(target, c.encoded(value))
        except FileExistsError:
            # Exclusive publication is the arbitration point for concurrent retries.
            value = c.load(target)
    # Every emission owns its receipts, including an idempotent event retry.
    # A retry during projection must not merge into the receipt being consumed.
    receipt = identity + '-' + uuid.uuid4().hex
    for view in set({'activity-timeline'} if views is None else views):
        if view not in ALL_VIEWS:
            raise ValueError('unknown Studio projection: ' + str(view))
        try:
            c.atomic(root / 'work/activity/dirty' / view / receipt, b'')
        except FileExistsError:
            pass
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
    with publication(root / 'work/activity/publications/activity-timeline'):
        return _write_timeline(root)


def _write_timeline(root: Path) -> dict:
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


@runtime_snapshot.operation
def refresh(root: Path, *, read=None, views=None) -> dict:
    """Rebuild independent displays; one unavailable view cannot undo committed work."""
    import studio
    root = root.resolve()
    selected = set(ALL_VIEWS if views is None else views)
    if selected - ALL_VIEWS:
        raise ValueError('unknown Studio projection: ' + ', '.join(sorted(selected - ALL_VIEWS)))
    pending_errors, projection_errors = [], []
    for queued in sorted((root / 'work/activity/pending-events').glob('*.json')):
        try:
            pending_event = c.load(queued)
            c.exact(pending_event, {'kind', 'subject', 'revision', 'details', 'at'}, 'pending activity receipt')
            for key in ('kind', 'subject', 'revision', 'at'):
                c.text(pending_event[key], 'pending activity ' + key)
            if chronological(pending_event['at']) == float('-inf') or not isinstance(pending_event['details'], dict):
                raise ValueError('pending activity receipt has invalid time or details')
            event(root, pending_event['kind'], pending_event['subject'], revision=pending_event['revision'],
                  details=pending_event['details'], at=pending_event['at'], views=ALL_VIEWS)
            queued.unlink(missing_ok=True)
        except FileNotFoundError:
            # A competing repair completed this immutable receipt first.
            continue
        except (ValueError, OSError, KeyError, TypeError) as exc:
            pending_errors.append({'path': queued.relative_to(root).as_posix(), 'message': str(exc)})

    artwork = selected & {'gallery', 'active-references'}
    if artwork:
        # An absent Studio has no artwork to publish. Capture first so a
        # manifest/event arriving during that check keeps its later receipts.
        dirty = {view: _dirty_receipts(root, view) for view in artwork}
        try:
            present = (root / studio.MANIFEST).is_file()
        except (ValueError, OSError) as exc:
            present = False
            projection_errors.extend({'projection': view, 'message': str(exc)} for view in sorted(artwork))
        with publication(artwork_owner(root)) if present else nullcontext():
            if present:
                # Capture again after admission, before loading the fresh model.
                dirty = {view: _dirty_receipts(root, view) for view in artwork}
                try:
                    read = publication_read(root, read) if (root / studio.MANIFEST).is_file() else None
                except (ValueError, OSError, KeyError, TypeError) as exc:
                    read = None
                    projection_errors.extend({'projection': view, 'message': str(exc)} for view in sorted(artwork))
            else:
                read = None
            if read is not None:
                if 'gallery' in artwork:
                    try:
                        studio.write_gallery(root, read=read)
                    except (ValueError, OSError, KeyError, TypeError) as exc:
                        projection_errors.append({'projection': 'gallery', 'message': str(exc)})
                if 'active-references' in artwork:
                    for character in read.characters:
                        try:
                            reference_view = studio.character_dir(root, character) / 'sheet/active-references.json'
                            c.atomic_write_json(reference_view, read.reference_index(character))
                        except (ValueError, OSError, KeyError, TypeError) as exc:
                            projection_errors.append({'projection': 'active-references', 'character': character,
                                                      'message': str(exc)})
            for view, paths in dirty.items():
                _acknowledge(root, view, paths, projection_errors)

    story = None
    if 'story-timeline' in selected:
        import story_timeline
        paths = _dirty_receipts(root, 'story-timeline')
        try:
            configured = story_timeline.configured(root)
        except (ValueError, OSError, KeyError, TypeError) as exc:
            configured = False
            projection_errors.append({'projection': 'story-timeline', 'message': str(exc)})
        # No output means no publisher to exclude. A configured story uses its
        # existing owner and rechecks the source after admission.
        with publication(root / '.timeline.publication') if configured else nullcontext():
            if configured:
                paths = _dirty_receipts(root, 'story-timeline')
                try:
                    if story_timeline.configured(root):
                        story = story_timeline.refresh(root)
                        if not story['ok']:
                            projection_errors.append({'projection': 'story-timeline', **story})
                except (ValueError, OSError, KeyError, TypeError) as exc:
                    projection_errors.append({'projection': 'story-timeline', 'message': str(exc)})
            _acknowledge(root, 'story-timeline', paths, projection_errors)
    timeline = None
    if 'activity-timeline' in selected:
        with publication(root / 'work/activity/publications/activity-timeline'):
            # Include the story projection's event in this same refresh.
            paths = _dirty_receipts(root, 'activity-timeline')
            try:
                timeline = write_timeline(root)
            except (ValueError, OSError, KeyError, TypeError) as exc:
                projection_errors.append({'projection': 'activity-timeline', 'message': str(exc)})
            _acknowledge(root, 'activity-timeline', paths, projection_errors)

    pending = root / 'work/activity/projections-pending.json'
    result = {'ok': not pending_errors and not projection_errors, 'timeline': timeline}
    if story is not None:
        result['story_timeline'] = story
    if pending_errors or projection_errors:
        warning = {**result,
            'code': 'PROJECTION_REFRESH_PENDING' if projection_errors else 'ACTIVITY_RECORD_PENDING',
            'message': 'Committed state retained. Some displays or activity receipts need repair.',
            'committed_state_retained': True, 'views_refreshed': not projection_errors,
            'diagnostics': pending_errors + projection_errors, 'retry': 'studio.py sync'}
        try:
            c.atomic_write_json(pending, warning)
        except OSError:
            pass
        _warn_operation(warning)
        return warning
    if _settle_pending(root):
        result['projection_pending'] = True
    return result


def _warn_operation(warning: dict) -> None:
    """A committed transition must not look like a request to generate again."""
    from operation_context import current
    import sys
    operation = current()
    if operation is not None:
        operation.event('projection_pending', **warning)
        print(warning['code'] + ': committed work retained; run studio.py sync to refresh displays/logs.', file=sys.stderr)


def changed(path: Path, kind: str, *, subject: str | None = None, revision: str | None = None,
            details: dict | None = None, refresh_views: bool = True, views=None) -> dict:
    root = scope(path)
    runtime_snapshot.invalidate_studio(root)
    selected = set(ALL_VIEWS if views is None else views)
    update = (_UPDATES.get() or {}).get(str(root.resolve()))
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
        event(root, kind, name, revision=revision, details=redacted, at=recorded_at, views=selected)
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
        if update is not None:
            update.views.update(selected)
            update.receipts.append(warning)
            update.result.update(warning)
        return warning
    if not refresh_views:
        return {'ok': True, 'projection_pending': True}
    if update is not None:
        update.views.update(selected)
        receipt = {'ok': True, 'projection_pending': True}
        update.receipts.append(receipt)
        return receipt
    return refresh(root, views=selected)
