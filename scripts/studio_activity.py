"""Durable operator events and rebuildable, chronological Studio projections.

Formal requests, approvals and images remain with their owning workflows. This
journal records transitions, never grants authority. Projection failures do not
undo a committed transition or turn it into a reason to submit another request.
"""
from __future__ import annotations
import read_context

from datetime import datetime, timezone
from contextlib import contextmanager, ExitStack
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
from owned_json import freeze, mutable


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


def _activity_values(root: Path) -> dict | None:
    """Retain immutable activity values acquired or emitted by this operation."""
    scope = read_context.call_scope()
    if scope is None:
        return None
    key = ('studio-activity-inputs', str(root.resolve()))
    return scope.setdefault(key, {'events': {}, 'written_events': set(), 'receipts': {}})


def owned_events(root: Path) -> frozenset[Path]:
    """Identify this operation's emissions when reconciling another writer."""
    values = _activity_values(root)
    return frozenset() if values is None else frozenset(values['written_events'])


def artwork_owner(root: Path, out: Path | None = None) -> Path:
    """The gallery's existing ownership document also orders its publishers."""
    import studio_workspace as studio
    from studio_gallery import output_owner
    return output_owner(root, studio.manifest(root)['studio_id'], out)


@contextmanager
def publication(owner: Path):
    """Order a display through the actual file that owns its published data.

    Canonical Studio writers and read-only consumers do not acquire this owner.
    Nested publishers share the operation's owned inputs. Admission orders
    output writes; it does not turn saved observations back into new inputs.
    """
    identity = os.getpid(), threading.get_ident(), str(owner.resolve())
    with c.file_lock(owner):
        held = _PUBLICATIONS.get() or {}
        if identity in held and held[identity].active:
            yield False
            return
        admission = _Publication()
        token = _PUBLICATIONS.set({**held, identity: admission})
        try:
            with read_context.public_call():
                yield True
        finally:
            # A copied context cannot prolong an owner's completed admission.
            admission.active = False
            _PUBLICATIONS.reset(token)


def publication_read(root: Path, read=None):
    """Reconcile other writers after admission, then keep the operation's model."""
    import studio_workspace as studio
    import production_store as store
    store.refresh_observation(root)
    studio._reconcile_written_iterations(root)
    scope = read_context.check_scope(root)
    key = ('studio-publication-model', str(root.resolve()))
    if read is None:
        read = scope.get(key) if scope is not None else None
        if read is None:
            read = studio.StudioRead(root)
    if read.root != root.resolve():
        raise ValueError('Studio read model belongs to another Studio')
    read.refresh()
    if scope is not None:
        scope[key] = read
    return read


@contextmanager
def reference_publication(root: Path, characters: set[str] | None, *, read=None):
    """Acquire affected reference outputs before their shared current model.

    A first output contains its actual calculated index. Canonical writers use
    their own files, so they can commit while display publishers are waiting.
    """
    import studio_workspace as studio
    if read is not None:
        read.require_root(root)
    else:
        scope = read_context.check_scope(root)
        read = scope.get(('studio-publication-model', str(root.resolve()))) if scope is not None else None
        if read is None:
            read = studio.StudioRead(root)
    while True:
        initial = set(read.characters)
        selected = initial if characters is None else initial & characters
        errors = []
        missing = []
        with ExitStack() as owners:
            for character in sorted(selected):
                path = studio.character_dir(root, character) / 'sheet/active-references.json'
                try:
                    owners.enter_context(publication(path))
                except FileNotFoundError:
                    missing.append((character, path))
                except (ValueError, OSError, KeyError, TypeError) as exc:
                    errors.append({'projection': 'active-references', 'character': character,
                                   'message': str(exc)})
            # First publications also keep their operation's owned values.
            owners.enter_context(read_context.public_call())
            current = publication_read(root, read)
            observed = set(current.characters) if characters is None else set(current.characters) & characters
            if observed != selected:
                # Release the complete ordered set before acquiring a changed
                # character set; a new name may sort before one already held.
                continue
            initialized = set()
            contested = False
            for character, path in missing:
                try:
                    c.atomic(path, c.encoded(current.reference_index(character)))
                except FileExistsError:
                    # A first publisher completed while this model was built.
                    # Its new file becomes an ordinary owner on the next pass.
                    contested = True
                    break
                except (ValueError, OSError, KeyError, TypeError) as exc:
                    errors.append({'projection': 'active-references', 'character': character,
                                   'message': str(exc)})
                else:
                    initialized.add(character)
            if contested:
                continue
            # These complete first publications already contain this model's
            # index. Replacing them again could erase a later publisher.
            yield current, errors, initialized
            return


def timeline_owner(root: Path) -> Path:
    """Initialize the real generated journal with the currently recorded events."""
    target = root / 'work/activity/timeline.jsonl'
    if not target.is_file():
        rows, _ = read_events(root)
        raw = b''.join((json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n').encode('utf-8') for row in rows)
        try:
            c.atomic(target, raw)
        except FileExistsError:
            pass
    return target


def _dirty_receipts(root: Path, view: str) -> list[Path]:
    # An atomic writer's temporary file has not become a receipt yet.
    return [path for path in (root / 'work/activity/dirty' / view).glob('*')
            if not path.name.startswith(c.TEMPORARY_PREFIX)]


def _character_scope(value) -> set[str] | None:
    import studio_workspace as studio
    if value is None:
        return None
    if not isinstance(value, (set, frozenset, list, tuple)) or any(not studio.valid_character_id(item) for item in value):
        raise ValueError('artwork scope must contain character identifiers')
    return set(value)


def _receipt_characters(paths: list[Path]) -> set[str] | None:
    """Union exact producer scopes; an unscoped receipt requests the complete view."""
    selected: set[str] = set()
    complete = False
    for path in paths:
        values = _activity_values(path.parents[4])
        if values is not None and path in values['receipts']:
            names = values['receipts'][path]
            if names is None:
                complete = True
            else:
                selected.update(names)
            continue
        try:
            raw = c.read(path)
        except (FileNotFoundError, ValueError):
            # c.read's regular-file check can observe the deletion before its
            # open and report ValueError. Only absence of this immutable
            # receipt means another publisher consumed it. Corrupt files,
            # directories and dangling symbolic links retain their error.
            try:
                path.lstat()
            except FileNotFoundError:
                continue
            raise
        if not raw:
            if values is not None:
                values['receipts'][path] = None
            complete = True
            continue
        value = c.decode(raw)
        c.exact(value, {'characters'}, 'artwork projection receipt')
        names = _character_scope(value['characters'])
        if values is not None:
            values['receipts'][path] = None if names is None else frozenset(names)
        if names is None:
            complete = True
        else:
            selected.update(names)
    return None if complete else selected


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
        with read_context.public_call():
            try:
                yield update.result
            finally:
                if update.views:
                    try:
                        result = refresh(root, views=update.views, scoped=True)
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
            try:
                result = function(path, *args, **kwargs)
            except BaseException:
                # A filesystem mutation may have committed a partial result
                # before raising. Successful writers publish their own change;
                # an unchanged retry does not end the operation's read phase.
                read_context.invalidate_studio(root)
                raise
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
    import studio_workspace as studio
    selected = path if path.is_dir() else path.parent
    return studio.studio_root(selected.resolve()) or selected.resolve()


def event(root: Path, kind: str, subject: str, *, revision: str | None = None,
          details: dict[str, Any] | None = None, at: str | None = None, views=None,
          characters: set[str] | None = None) -> dict:
    """Append an immutable, redacted event; an explicit revision makes retries idempotent."""
    from operation_context import current_operation_id, safe_value, known_secrets
    root = root.resolve()
    characters = _character_scope(characters)
    identity = c.content_id({'kind': kind, 'subject': subject, 'revision': revision}) if revision else uuid.uuid4().hex
    target = c.local(root, f'work/activity/events/{identity[:2]}/{identity}.json', exists=False)
    owned = _activity_values(root)
    if target.exists():
        value = (mutable(owned['events'][target])
                 if owned is not None and target in owned['events'] else c.load(target))
    else:
        value = {'event_id': identity, 'at': at or timestamp(), 'event': kind, 'subject': subject,
                 'revision': revision, 'operation_id': current_operation_id(),
                 'details': safe_value(details or {}, secrets=known_secrets())}
        try:
            c.atomic(target, c.encoded(value))
        except FileExistsError:
            # Exclusive publication is the arbitration point for concurrent retries.
            value = c.load(target)
        else:
            if owned is not None:
                owned['written_events'].add(target)
    if owned is not None:
        owned['events'][target] = freeze(value)
    # Every emission owns its receipts, including an idempotent event retry.
    # A retry during projection must not merge into the receipt being consumed.
    receipt = identity + '-' + uuid.uuid4().hex
    for view in set({'activity-timeline'} if views is None else views):
        if view not in ALL_VIEWS:
            raise ValueError('unknown Studio projection: ' + str(view))
        try:
            raw = (c.encoded({'characters': sorted(characters)})
                   if characters is not None and view in {'gallery', 'active-references'} else b'')
            receipt_path = root / 'work/activity/dirty' / view / receipt
            c.atomic(receipt_path, raw)
        except FileExistsError:
            pass
        else:
            if owned is not None:
                owned['receipts'][receipt_path] = (
                    frozenset(characters) if characters is not None and view in {'gallery', 'active-references'}
                    else None)
    dirty = root / 'work/activity/projections-pending.json'
    c.atomic_write_json(dirty, {'event_id': identity, 'at': value['at']})
    return value


def read_events(root: Path) -> tuple[list[dict], list[dict]]:
    rows, diagnostics = [], []
    owned = _activity_values(root)
    directory = root / 'work/activity/events'
    for path in sorted(directory.glob('*/*.json')):
        try:
            value = (owned['events'][path]
                     if owned is not None and path in owned['events'] else c.load(path))
            if not isinstance(value, dict) or value.get('event_id') != path.stem:
                raise ValueError('event identifier differs from its file')
            if any(not isinstance(value.get(key), str) or not value[key] for key in ('at', 'event', 'subject')):
                raise ValueError('event time, kind and subject must be nonempty strings')
            if chronological(value['at']) == float('-inf') or not isinstance(value.get('details'), dict):
                raise ValueError('event needs a timezone-aware time and object details')
            if owned is not None:
                owned['events'][path] = freeze(value)
            rows.append(mutable(value))
        except (ValueError, OSError, KeyError) as exc:
            diagnostics.append({'path': path.relative_to(root).as_posix(), 'message': str(exc)})
    rows.sort(key=lambda row: (chronological(row.get('at')), row['event_id']))
    return rows, diagnostics


def write_timeline(root: Path) -> dict:
    """JSONL and Markdown are displays of immutable event records, not another authority."""
    with publication(timeline_owner(root)):
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


@read_context.operation
def refresh(root: Path, *, read=None, views=None, scoped: bool = False,
            current_only: bool = False) -> dict:
    """Rebuild independent displays; one unavailable view cannot undo committed work."""
    import studio_workspace as studio
    root = root.resolve()
    selected = set(ALL_VIEWS if views is None else views)
    if selected - ALL_VIEWS:
        raise ValueError('unknown Studio projection: ' + ', '.join(sorted(selected - ALL_VIEWS)))
    pending_errors, projection_errors = [], []
    for queued in sorted((root / 'work/activity/pending-events').glob('*.json')):
        try:
            pending_event = c.load(queued)
            required = {'kind', 'subject', 'revision', 'details', 'at'}
            c.exact(pending_event, required | ({'characters'} if 'characters' in pending_event else set()),
                    'pending activity receipt')
            for key in ('kind', 'subject', 'revision', 'at'):
                c.text(pending_event[key], 'pending activity ' + key)
            if chronological(pending_event['at']) == float('-inf') or not isinstance(pending_event['details'], dict):
                raise ValueError('pending activity receipt has invalid time or details')
            event(root, pending_event['kind'], pending_event['subject'], revision=pending_event['revision'],
                  details=pending_event['details'], at=pending_event['at'], views=ALL_VIEWS,
                  characters=_character_scope(pending_event.get('characters')))
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
        with ExitStack() as owners:
            gallery_ready = 'gallery' in artwork
            gallery_owner = None
            initialized_references = set()
            if present:
                if gallery_ready:
                    try:
                        gallery_owner = artwork_owner(root)
                        owners.enter_context(publication(gallery_owner))
                        dirty['gallery'] = _dirty_receipts(root, 'gallery')
                    except (ValueError, OSError, KeyError, TypeError) as exc:
                        gallery_ready = False
                        projection_errors.append({'projection': 'gallery', 'message': str(exc)})
                try:
                    if 'active-references' in artwork:
                        affected = _receipt_characters(dirty['active-references']) if scoped and not current_only else None
                        read, errors, initialized_references = owners.enter_context(
                            reference_publication(root, affected, read=read))
                        projection_errors.extend(errors)
                    else:
                        read = publication_read(root, read) if (root / studio.MANIFEST).is_file() else None
                except (ValueError, OSError, KeyError, TypeError) as exc:
                    read = None
                    projection_errors.extend({'projection': view, 'message': str(exc)} for view in sorted(artwork))
            else:
                read = None
            if read is not None:
                if gallery_ready:
                    try:
                        affected = _receipt_characters(dirty['gallery']) if scoped or current_only else None
                        studio.write_gallery(root, read=read,
                            characters=affected if scoped and not current_only else None,
                            current_only=current_only and affected is not None,
                            full_characters=affected, publication_owner=gallery_owner)
                    except (ValueError, OSError, KeyError, TypeError) as exc:
                        projection_errors.append({'projection': 'gallery', 'message': str(exc)})
                if 'active-references' in artwork:
                    try:
                        affected = _receipt_characters(dirty['active-references']) if scoped and not current_only else None
                    except (ValueError, OSError, KeyError, TypeError) as exc:
                        projection_errors.append({'projection': 'active-references', 'message': str(exc)})
                    else:
                        unavailable = {error.get('character') for error in projection_errors
                                       if error.get('projection') == 'active-references'}
                        for character in read.characters:
                            if (character in unavailable or character in initialized_references
                                    or (affected is not None and character not in affected)):
                                continue
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
        # The story publisher owns its actual self-contained HTML. Captured
        # receipts precede its fresh input read; later emissions stay pending.
        if configured:
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
        with publication(timeline_owner(root)):
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
            details: dict | None = None, refresh_views: bool = True, views=None,
            characters: set[str] | None = None) -> dict:
    root = scope(path)
    if characters is None:
        try:
            relative = path.resolve().relative_to(root).parts
        except ValueError:
            relative = ()
        if len(relative) >= 2 and relative[0] == 'characters':
            characters = {relative[1]}
    characters = _character_scope(characters)
    read_context.invalidate_studio(root)
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
        event(root, kind, name, revision=revision, details=redacted, at=recorded_at, views=selected,
              characters=characters)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        warning = {'ok': False, 'code': 'ACTIVITY_RECORD_PENDING', 'message': str(exc),
                   'committed_state_retained': True, 'retry': 'studio.py sync', 'retry_receipt_saved': False}
        pending = {'kind': kind, 'subject': name, 'revision': revision, 'details': redacted, 'at': recorded_at}
        if characters is not None:
            pending['characters'] = sorted(characters)
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
    return refresh(root, views=selected, scoped=True)
