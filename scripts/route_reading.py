#!/usr/bin/env python3
"""Deliver complete operation knowledge and retain its exact source scope."""
from __future__ import annotations
import runtime_paths
import operation_context as _operation_context

import argparse
import copy
import datetime
import json
import os
import re
import secrets
import sys
from pathlib import Path
from typing import Any, Callable, TextIO

import execution_contract as c
import execution_routes
from knowledge_documents import DocumentReader, SECTION_ID_PATTERN, record_path
from cli_invocation import python_argv, shown
from route_reading_output import TextReadingOutput

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PAGE_BYTES = 16384
MAX_AUTO_PAGE_BYTES = 262144
INDEX_SOURCE_STATES = {
    'pending': 'No source bytes have been delivered in this snapshot.',
    'partial': 'Some selected body bytes have been delivered; the remaining bytes are required.',
    'delivered': 'This snapshot has complete delivery evidence for this source.',
    'known': 'An explicitly selected complete reading supplies unchanged selected source content in this context.',
}
_NO_MODEL = object()
# An authoring reading made without a model holds every family's guide sections.
SAVED_INPUT_OPERATIONS = {'execute', 'review'}


def page_budget(value: int | str | None = None, host_page_bytes: int | None = None) -> tuple[int, dict]:
    """Select a bounded source-text page from a declared host capacity.

    The capacity covers source text, not the complete JSON response. The caller
    reserves room for response metadata when choosing its host page capacity.
    No successful write or saved receipt proves that a host displayed all text.
    """
    if host_page_bytes is not None and (type(host_page_bytes) is not int or host_page_bytes < 4):
        raise ValueError('host-page-bytes must be an integer of at least four source bytes')
    selected = DEFAULT_PAGE_BYTES if value is None else value
    if selected == 'auto':
        budget = min(host_page_bytes or DEFAULT_PAGE_BYTES, MAX_AUTO_PAGE_BYTES)
    else:
        if isinstance(selected, str) and selected.isdecimal():
            selected = int(selected)
        if type(selected) is not int or selected < 4:
            raise ValueError('page-bytes must be auto or an integer of at least four')
        budget = min(selected, host_page_bytes) if host_page_bytes is not None else selected
    return budget, {'mode': 'auto' if value == 'auto' else 'fixed',
        'source_bytes': budget, 'host_page_bytes': host_page_bytes,
        'meaning': 'Source-text budget; reserve separate room for JSON metadata and replay any truncated page.'}


def add_context_arguments(parser: argparse.ArgumentParser, *, pages: bool = True) -> None:
    """Share an explicit current-context contract with plan navigation."""
    context = parser.add_mutually_exclusive_group()
    context.add_argument('--reading-context', metavar='ID',
        help='The returned ID for this uninterrupted model context; automatically reuse only its complete readings. '
             'Never carry this ID across compaction or a new context.')
    context.add_argument('--fresh-context', action='store_true',
        help='Start a new reading context; read current required bodies again while preserving authored work.')
    if pages:
        parser.add_argument('--page-bytes', default=None, metavar='N|auto',
            help=f'Maximum UTF-8 source-text bytes per reading page (default: {DEFAULT_PAGE_BYTES}); '
                 f'auto uses declared --host-page-bytes up to {MAX_AUTO_PAGE_BYTES}, '
                 'or the default when no capacity is declared. This is not a total-response or token limit.')
        parser.add_argument('--host-page-bytes', type=int, metavar='N',
            help='Safe source-text capacity declared by this host, after reserving separate space for JSON metadata; '
                 'caps fixed and auto source pages, not the complete JSON response. '
                 'Keep the host tool output allowance larger; never infer capacity from a successful command.')


def resolve_context_options(args: argparse.Namespace) -> dict:
    """Resolve one invocation; persisted plans never select a knowledge context."""
    identifier = getattr(args, 'reading_context', None)
    fresh = getattr(args, 'fresh_context', False)
    if fresh and identifier is not None:
        raise ValueError('Choose --fresh-context or the current --reading-context ID.')
    if fresh:
        identifier = secrets.token_hex(16)
    elif identifier is not None:
        _hex(identifier, 32, 'reading context')
    requested = getattr(args, 'page_bytes', None)
    host = getattr(args, 'host_page_bytes', None)
    page_budget(requested, host)
    return {'reading_context': identifier, 'fresh_context': fresh,
            'page_bytes': requested, 'host_page_bytes': host}


def _context_path(ledger: Path, identifier: str) -> Path:
    return ledger.parent / 'reading-contexts' / (_hex(identifier, 32, 'reading context') + '.json')


def _context_keys(ledger: Path, identifier: str | None, root: Path) -> list[str]:
    if identifier is None:
        return []
    path = _context_path(ledger, identifier)
    if not path.exists():
        return []
    value = c.load(path)
    c.exact(value, {'context', 'root', 'keys'}, 'reading context')
    if value['context'] != identifier or value['root'] != str(root.absolute()):
        raise ValueError('The reading context belongs to another source root; start with --fresh-context.')
    keys = value['keys']
    if not isinstance(keys, list) or keys != list(dict.fromkeys(keys)):
        raise ValueError('The reading context needs distinct complete reading keys; start with --fresh-context.')
    for key in keys:
        _hex(key, 32, 'reading key')
    return keys


def _remember_context(ledger: Path, identifier: str, root: Path, keys: list[str]) -> None:
    path = _context_path(ledger, identifier)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _ledger_lock(ledger):
        previous = _context_keys(ledger, identifier, root)
        value = {'context': identifier, 'root': str(root.absolute()),
                 'keys': list(dict.fromkeys([*previous, *keys]))}
        c.atomic(path, c.encoded(value), replace=path.exists())


def decorate_context(report: dict, *, reading_context: str | None = None,
                     fresh_context: bool = False, page_bytes: int | str | None = None,
                     host_page_bytes: int | None = None) -> dict:
    """Carry invocation knowledge through returned actions, never into plan state.

    A different context restarts a saved page selection. No previously delivered
    page or complete receipt silently supplies its body to the new context.
    """
    result = copy.deepcopy(report)
    if reading_context is not None:
        _hex(reading_context, 32, 'reading context')
    page_budget(page_bytes, host_page_bytes)

    def visit(value, owner=None):
        if isinstance(value, list):
            for child in value:
                visit(child, owner)
            return
        if not isinstance(value, dict):
            return
        argv = value.get('argv')
        if isinstance(argv, list) and len(argv) >= 3:
            read_action = Path(argv[1]).name == 'execution_routes.py' and argv[2] == 'read'
            plan_action = Path(argv[1]).name == 'production_workflow.py' and argv[2] in {'plan', 'advance'}
            if read_action or plan_action:
                selected = list(argv)
                explicit_fresh = owner in {'fresh_context_action', 'restart'} and not fresh_context
                def remove(name, argument=True):
                    while name in selected:
                        index = selected.index(name)
                        del selected[index:index + (2 if argument else 1)]
                def option(name):
                    return selected[selected.index(name) + 1] if name in selected else None
                if read_action:
                    cursor = option('--continue') or option('--replay') or option('--restart')
                    sid = option('--snapshot') or (cursor.split(':')[0] if cursor else None)
                    ledger_value, studio_value = option('--reading-ledger'), option('--root')
                    ledger = ledger_candidates(studio=Path(studio_value) if studio_value else None,
                                               ledger=Path(ledger_value) if ledger_value else None)[0]
                    if sid is not None:
                        folder = _snapshot_dir(ledger, sid)
                        snapshot = c.load(folder / 'snapshot.json')
                        if (reading_context is None or snapshot.get('reading_context') != reading_context
                                or fresh_context or explicit_fresh):
                            if cursor is None:
                                continuation = c.load(folder / 'continuation.json')
                                cursor = sid + ':' + continuation['page']
                            delivery = any(flag in selected for flag in ('--continue', '--replay', '--section', '--all'))
                            for name in ('--continue', '--replay', '--restart', '--snapshot', '--section', '--index-source'):
                                remove(name)
                            selected.extend(('--restart', cursor))
                            if delivery and '--all' not in selected:
                                selected.append('--all')
                    remove('--known-reading')
                remove('--reading-context')
                remove('--fresh-context', False)
                if explicit_fresh:
                    selected.append('--fresh-context')
                elif reading_context is not None:
                    selected.extend(('--reading-context', reading_context))
                if page_bytes is not None:
                    remove('--page-bytes')
                    selected.extend(('--page-bytes', str(page_bytes)))
                if host_page_bytes is not None:
                    remove('--host-page-bytes')
                    selected.extend(('--host-page-bytes', str(host_page_bytes)))
                value['argv'] = selected
                if 'shown' in value:
                    value['shown'] = shown(selected)
                if value.get('command') not in {'read', 'plan', 'advance'} and 'command' in value:
                    value['command'] = shown(selected)
        for key, child in value.items():
            if key != 'argv':
                visit(child, key)

    visit(result)
    if reading_context is not None:
        result['reading_context'] = {'id': reading_context, 'fresh': fresh_context,
            'meaning': 'Only complete material actually delivered in this uninterrupted context is reused automatically.',
            'new_context': 'Use --fresh-context after compaction or in a new context; saved work remains intact.'}
    return result


def _hex(value: Any, length: int, label: str) -> str:
    if not isinstance(value, str) or len(value) != length or any(x not in '0123456789abcdef' for x in value):
        raise ValueError(f'{label}: expected {length} lowercase hexadecimal characters')
    return value


MANIFEST_FIELDS = {'route', 'operation', 'execution', 'scope', 'source_kind',
                   'features', 'documents', 'resources', 'model'}
OPTIONAL_MANIFEST_FIELDS = {'authoring_scope'}
GENERATION_ROUTES = {'generation', 'state-series', 'batch', 'repose', 'character-sheet'}


def manifest_fields(value: dict) -> set[str]:
    """The selected authoring scope is absent for ordinary operation readings."""
    return MANIFEST_FIELDS | (OPTIONAL_MANIFEST_FIELDS & value.keys() if isinstance(value, dict) else set())


def same_manifest(left: dict, right: dict) -> bool:
    return all(left.get(field) == right.get(field)
               for field in MANIFEST_FIELDS | OPTIONAL_MANIFEST_FIELDS)


def curation_action(studio: Path, *, execution: str, scope: str,
                    source_kind: str = 'production-candidate', operation: str = 'adopt') -> dict:
    """Begin complete paged delivery derived by the actual retained-result owner.

    This action makes no assertion of retained knowledge. A current context may
    explicitly append its complete --known-reading keys; a fresh context reads
    every required section before a delivery record is issued.
    """
    execution_routes.require_scope(operation, execution, scope, source_kind)
    argv = python_argv(ROOT / 'scripts/execution_routes.py', 'read', 'adoption',
                       '--root', str(studio.absolute()), '--operation', operation,
                       '--execution', execution, '--scope', scope, '--source-kind', source_kind, '--all')
    return {'argv': argv, 'command': 'read',
            'reason': 'Read the complete ' + scope + ' ' + operation + ' contract for the '
                      + source_kind + ', including its authority and recovery conditions.'}


def operation_reading_action(studio: Path, run: str, *, operation: str, loaded=None) -> dict:
    """Select the current execute/review contract from one retained request.

    Its model and writing guidance remain the exact saved workspace evidence.
    This action resolves neither a live model edition nor a different input;
    it makes no claim that a new context knows earlier authoring material.
    """
    if operation not in SAVED_INPUT_OPERATIONS:
        raise ValueError('A retained request reading selects execute or review.')
    if loaded is None:
        import production_operations
        loaded = production_operations.read_run(studio, run)
    if loaded.prepared['run'] != run:
        raise ValueError('The retained reading source belongs to another run.')
    task = loaded.prepared['task']
    argv = python_argv(ROOT / 'scripts/execution_routes.py', 'read', task['route'],
                       '--root', str(studio.absolute()), '--operation', operation,
                       '--execution', task['execution'])
    for feature in task.get('features', []):
        argv.extend(('--feature', feature))
    argv.append('--all')
    return {'argv': argv, 'command': 'read',
            'reason': 'Read the current ' + operation + ' contract for this saved request. '
                      'Use workspace.saved_knowledge for its exact retained model and source guidance.'}


class ReadingSourcesChanged(ValueError):
    """Name the source differences that require a current complete delivery."""

    def __init__(self, changes: list[dict], message: str = 'reading sources changed; read the current sources',
                 *, actions: dict | None = None):
        self.changes = changes
        self.actions = actions or {}
        self.required_action = 'Read the current complete material for the requested operation and select its issued reading key.'
        names = ', '.join(str(row.get('document_id') or row.get('path') or row.get('resource')
                             or row.get('id') or row['kind'])
                          for row in changes)
        super().__init__(message + (': ' + names if names else ''))

    def as_dict(self) -> dict:
        return {'code': 'READING_SOURCES_CHANGED', 'changes': self.changes,
                'required_action': self.required_action, 'actions': self.actions}


class ReadingInvocationConflict(ValueError):
    """Return a verified saved reading's recovery without delivering any bytes."""

    def __init__(self, message: str, details: dict):
        super().__init__(message)
        self.details = details

    def as_dict(self) -> dict:
        return {'code': 'READING_INVOCATION_CONFLICT', **self.details}


def _invocation_conflict(args: argparse.Namespace, message: str) -> ReadingInvocationConflict:
    """Keep continuation ownership and explicit knowledge context at an input error."""
    details = {'required_action': 'Use the complete reading action from the current input inspection.',
               'actions': {}}
    try:
        ledger = ledger_candidates(studio=args.root, ledger=args.reading_ledger)[0]
        studio = args.root.absolute() if args.root is not None else (_studio(Path.cwd()) or _studio(ledger.parent))
        cursor = args.cursor or args.replay or args.restart
        if cursor is None:
            folder = _snapshot_dir(ledger, args.snapshot_id)
            continuation = c.load(folder / 'continuation.json')
            cursor = args.snapshot_id + ':' + continuation['page']
        _, snapshot, _ = _cursor(ledger, cursor)
        if snapshot['root'] != str(ROOT.absolute()):
            raise ValueError('The saved reading belongs to another Skill directory; inspect the current draft with the selected Skill.')
        details['owner'] = {'snapshot': cursor.split(':')[0], 'choices': snapshot.get('choices'),
                            'reading_ledger': str(ledger.absolute()),
                            'reading_context': snapshot.get('reading_context')}
        budget = DEFAULT_PAGE_BYTES if args.page_bytes is None else args.page_bytes
        base = python_argv(ROOT / 'scripts/execution_routes.py', 'read',
                           '--reading-ledger', str(ledger.absolute()), '--page-bytes', str(budget))
        if studio is not None:
            base.extend(('--root', str(studio.absolute())))
        if args.host_page_bytes is not None:
            base.extend(('--host-page-bytes', str(args.host_page_bytes)))
        restart = [*base, '--restart', cursor, '--fresh-context']
        if args.cursor or args.replay or args.all or args.section:
            restart.append('--all')
        actions = details['actions']
        actions['restart'] = {'argv': restart, 'command': 'read',
            'reason': 'Read the current required bodies in a new context, retaining all authored work.'}
        # A stored context ID is information, not a claim that this caller
        # still knows its bodies. Only an explicitly matching invocation can
        # recover that context; a fresh or different context always restarts.
        if (not args.fresh_context and args.restart is None and args.reading_context is not None
                and args.reading_context == snapshot.get('reading_context')):
            if args.snapshot_id is not None or (args.all and args.cursor):
                resume = [*base, '--snapshot', cursor.split(':')[0]]
                if args.all:
                    resume.append('--all')
                elif args.section is not None:
                    resume.extend(('--section', args.section))
                elif args.index_source is not None:
                    resume.extend(('--index-source', args.index_source))
            else:
                selector = '--continue' if args.cursor else '--replay' if args.replay else '--restart'
                resume = [*base, selector, cursor]
            if args.reading_context is not None:
                resume.extend(('--reading-context', args.reading_context))
            actions['resume'] = {'argv': resume, 'command': 'read',
                'reason': 'Continue this saved selection only in the same uninterrupted context; do not append initial route or feature selectors.'}
            details['required_action'] = ('In this same context, run actions.resume.argv unchanged. '
                'After compaction or in a new context, run actions.restart.argv instead.')
        else:
            details['required_action'] = ('Run actions.restart.argv to read the current required bodies in a new context. '
                + ('A restart reacquires current source bodies instead of continuing stored pages.'
                   if args.restart is not None else
                   'No matching current context was explicitly selected; saved receipts do not supply knowledge.'))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        details['recovery_unavailable'] = str(exc)
    return ReadingInvocationConflict(message, details)


def source_changes(previous: dict, current: dict, *, required_only: bool = False,
                   include_model: bool = True) -> list[dict]:
    """Compare complete section content and independently selected source owners."""
    changes = []
    before = {row['document_id']: row for row in previous.get('documents', [])}
    after = {row['document_id']: row for row in current.get('documents', [])}
    for name in sorted(set(after) if required_only else set(before) | set(after)):
        old, new = before.get(name), after.get(name)
        old_sections = {row['section_id']: row for row in (old or {}).get('sections', [])}
        new_sections = {row['section_id']: row for row in (new or {}).get('sections', [])}
        changed = [identifier for identifier in
                   sorted(set(new_sections) if required_only else set(old_sections) | set(new_sections))
                   if old_sections.get(identifier) != new_sections.get(identifier)]
        reordered = not required_only and not changed and list(old_sections) != list(new_sections)
        if not changed and not reordered:
            continue
        missing = [identifier for identifier in new_sections if identifier not in old_sections]
        changes.append({'kind': 'document', 'document_id': name,
            'change': ('added' if old is None else 'removed' if new is None else 'reordered' if reordered else
                       'scope-expanded' if missing and all(old_sections.get(key) == value
                           for key, value in new_sections.items() if key in old_sections) else 'modified'),
            'before': (old or {}).get('sections'), 'after': (new or {}).get('sections'),
            'required_sections': list(new_sections.values()), 'changed_sections': changed,
            'missing_sections': missing})
    before_resources, after_resources = previous.get('resources', {}), current.get('resources', {})
    for name in sorted(set(after_resources) if required_only else set(before_resources) | set(after_resources)):
        old, new = before_resources.get(name), after_resources.get(name)
        if old != new:
            changes.append({'kind': 'resource', 'resource': name,
                'change': 'added' if name not in before_resources else 'removed' if name not in after_resources else 'modified',
                'before': old, 'after': new})
    before_features = set(previous.get('features', [])); after_features = set(current.get('features', []))
    for name in sorted(after_features - before_features if required_only else before_features ^ after_features):
        changes.append({'kind': 'feature', 'id': name,
                        'change': 'added' if name in after_features else 'removed'})
    if include_model and previous.get('model') != current.get('model'):
        changes.append({'kind': 'model', 'id': (current.get('model') or previous.get('model') or {}).get('id'),
                        'before': previous.get('model'), 'after': current.get('model')})
    return changes


def _read_once(root: Path, reader: Callable[[str], bytes] | None = None):
    source = reader or (lambda path: c.read(c.local(root, path)))
    acquired = {}
    def read(path: str) -> bytes:
        if path not in acquired:
            acquired[path] = source(path)
        return acquired[path]
    return read


def _studio(path: Path | None) -> Path | None:
    if path is None:
        return None
    path = path.absolute()
    for folder in [path, *path.parents]:
        if (folder / 'studio.json').is_file():
            return folder
    return None


def ledger_candidates(*, studio: Path | None = None, package_root: Path | None = None,
                      ledger: Path | None = None) -> list[Path]:
    if ledger is not None:
        return [ledger.absolute()]
    explicit = os.environ.get('CPB_READS_LEDGER')
    if explicit is not None:
        if not explicit.strip():
            raise ValueError('CPB_READS_LEDGER must name a file')
        return [Path(explicit).absolute()]
    output = []
    if studio is not None:
        output.append(studio.absolute() / 'work/reads.jsonl')
    if package_root is not None:
        output.append(package_root.absolute() / 'reads.jsonl')
    for value in (Path.cwd(), package_root):
        found = _studio(value)
        if found is not None:
            output.append(found / 'work/reads.jsonl')
    output.append(runtime_paths.user_data_home() / 'reads.jsonl')
    return list(dict.fromkeys(output))


def _family(name: str, value: dict, dialect: str | None) -> bytes:
    """The resource as one model family reads it. Another family's section keeps its name and families."""
    if name == 'prompt-writing-guide':
        value = {**value, 'sections': [section if not section.get('dialects') or dialect in section['dialects']
                                       else {'id': section['id'], 'dialects': section['dialects']}
                                       for section in value['sections']]}
    else:
        value = {**value, 'dialects': [row for row in value['dialects'] if row['id'] == dialect]}
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def bound_dialect(value: dict) -> Any:
    """The declared model family, or None for interface-neutral guidance."""
    found = {json.dumps(item['dialect']) for item in value['resources'].values() if 'dialect' in item}
    if len(found) > 1:
        raise ValueError('reading resources name different model families')
    return json.loads(found.pop()) if found else None


def _live_resource_reader():
    """Acquire the live catalogue at the route API's input boundary."""
    from catalog_retrieval.runtime import load_pack_catalog
    from pack_cache import resource_warning
    catalog = load_pack_catalog()
    if catalog.resource_reader is not None:
        return catalog.resource_reader
    def read_named(name):
        problem = resource_warning(catalog, name)
        if problem:
            raise ValueError(problem)
        resource = catalog.resources.get(name)
        if resource is None:
            return None
        if resource.source_pack not in catalog.pack_roots:
            raise ValueError(f'named resource {name} comes from a pack without an active root: {resource.source_pack}')
        base=Path(catalog.pack_roots[resource.source_pack])
        if catalog.inputs is not None:
            from production_store import stable_bytes
            acquired=catalog.inputs.packs[resource.source_pack].files[resource.relative_path]
            raw=acquired.bytes_for_capture(lambda relative:stable_bytes(base,relative))
        else:
            raw=c.read(c.local(base,resource.relative_path))
        return {'source_pack':resource.source_pack,'path':resource.relative_path,'sha256':c.digest(raw)},raw
    return read_named


def _knowledge_requirements(manifest: dict) -> dict[str, bool]:
    """Select knowledge for the current decisions, never from prompt words.

    Exact request, target, source and permission validators keep their own
    effect-boundary responsibilities. This selection only defers instructions
    for decisions that the current stage or retained amendment does not make.
    Definition establishes source meaning and dictionary-backed terminology;
    depiction constructs the picture; the writing guide serves its rendition
    and final request inspection. An
    explicitly selected model still supplies its complete guidance card.
    """
    scope = manifest.get('authoring_scope') or {}
    profiles = set(scope.get('profiles') or [])
    if (not scope or 'target-change' in scope.get('conditions', [])
            or 'unknown-sources' in scope.get('conditions', [])):
        return {'writing': True, 'model': True}
    if scope.get('change_scope') is None:
        return {'writing': scope.get('stage') in {'rendition', 'prepare'}, 'model': True}
    if not profiles:
        return {'writing': True, 'model': True}
    limited = profiles.issubset({'amend-controls', 'amend-recording'})
    return {'writing': not limited,
            'model': scope.get('stage') == 'prepare' or profiles != {'amend-recording'}}


def _capture_resources(manifest: dict, bodies: list, dialect: Any, resource_reader) -> None:
    manifest['resources'] = {}
    if 'prompt-dialect' not in manifest['features']:
        if dialect is not None:
            raise ValueError('a model or prompt family selects writing guide sections; add --feature prompt-dialect')
        return
    # A saved-request operation interprets its captured input. With no new
    # family selected, do not reacquire every family's authoring material.
    # An explicit family/model inspection still delivers its requested guide.
    if manifest.get('operation') in SAVED_INPUT_OPERATIONS and dialect is None:
        return
    if not _knowledge_requirements(manifest)['writing']:
        return
    selected={name:resource_reader(name) for name in ('prompt-writing-guide','prompt-dialects')}
    for name,resource in selected.items():
        if resource is None:
            manifest['resources'][name]={'status':'unavailable'}
            continue
        origin,raw=resource
        meta={'status':'present',**origin}
        value=c.decode(raw)
        if name == 'prompt-dialects' and dialect is not None:
            from pack_manager import PackError
            from prompt_dialect import validate_dialects
            try:
                validate_dialects(value)
                carried={str(item['id']) for item in value['dialects']}
                if dialect not in carried:
                    raise PackError(f"unknown dialect {dialect!r}; the prompt-dialects resource carries: "+', '.join(sorted(carried)))
            except PackError as exc:
                raise ValueError(str(exc)) from None
        meta['dialect'] = dialect
        raw = _family(name, value, dialect)
        manifest['resources'][name] = meta
        # The delivered bytes carry their own digest; the manifest binds the source file.
        bodies.append(({'kind': 'resource', 'resource': name, **meta,
                        'source_sha256': meta['sha256'], 'sha256': c.digest(raw)}, raw))


def _validate_resources(value: dict) -> None:
    resources = value.get('resources')
    if value.get('operation') in SAVED_INPUT_OPERATIONS and resources == {}:
        return
    expected = ({'prompt-writing-guide', 'prompt-dialects'}
                if 'prompt-dialect' in value['features'] and _knowledge_requirements(value)['writing'] else set())
    if not isinstance(resources, dict) or set(resources) != expected:
        raise ValueError('reading resource set differs from its feature requirements')
    fields = {'status', 'source_pack', 'path', 'sha256'}
    for item in resources.values():
        if isinstance(item, dict) and item.get('status') == 'unavailable':
            c.exact(item, {'status'}, 'unavailable resource')
        else:
            c.exact(item, fields | {'dialect'}, 'reading resource')
            if item['status'] != 'present':
                raise ValueError('invalid resource status')
            c.sha(item['sha256']); c.text(item['source_pack'], 'resource pack')
            c.local(ROOT, item['path'], exists=False)
            if item['dialect'] is not None:
                c.text(item['dialect'], 'reading model family')
    bound_dialect(value)


def _require_dialect(record: dict, bodies: list, dialect: Any) -> None:
    if not _knowledge_requirements(record)['writing']:
        return
    bound = bound_dialect(record)
    if dialect is not _NO_MODEL and bound != dialect:
        raise ValueError(f'the delivered writing guide is scoped to {bound!r}; read the current model or prompt family')
    if dialect is not _NO_MODEL and dialect is not None:
        available = {meta['resource']: c.decode(raw) for meta, raw in bodies if meta['kind'] == 'resource'}
        ids = {row['id'] for row in available.get('prompt-dialects', {}).get('dialects', [])}
        if dialect not in ids:
            raise ValueError('model dialect is absent from the delivered resource: ' + dialect)


def _model_material(record: dict, service: str | None) -> tuple[dict, bytes]:
    from render_contract_lib import model_card
    identifier = c.text(record.get('id'), 'reading model id')
    offerings = list(record.get('offerings') or [])
    if service is not None:
        offerings = [row for row in offerings if row['service'] == service]
        if len(offerings) != 1:
            raise ValueError('selected model has no unique offering for service: ' + service)
    cards = [model_card(record, row) for row in offerings] if offerings else [model_card(record)]
    raw = (json.dumps(cards, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')
    return {'id': identifier, 'record_sha256': c.content_id(record), 'service': service,
            'guidance_sha256': c.digest(raw)}, raw


def _validate_model(value: Any) -> None:
    if value is None:
        return
    c.exact(value, {'id', 'record_sha256', 'service', 'guidance_sha256'}, 'reading model')
    c.text(value['id'], 'reading model id')
    c.sha(value['record_sha256']); c.sha(value['guidance_sha256'])
    if value['service'] is not None:
        c.text(value['service'], 'reading model service')


def require_model_reading(record: dict, *, dialect: Any = _NO_MODEL, resource_reader,
                          model_record: dict | None = None, service: str | None = None) -> None:
    """Check delivered guidance against the model and resources acquired by its consumer.

    A family-only delivery serves work whose target remains at that scope.
    A selected model requires its exact model edition and offering guidance.
    Complete all-offering guidance covers any one of those offerings. This
    records source delivery; it never certifies an author's understanding.
    """
    _validate_resources(record)
    _validate_model(record['model'])
    manifest = {'features': record['features'], 'operation': record.get('operation'),
                'authoring_scope': record.get('authoring_scope')}
    bodies = []
    _capture_resources(manifest, bodies, bound_dialect(record), resource_reader)
    if manifest['resources'] != record['resources']:
        raise ReadingSourcesChanged(source_changes(record, manifest, required_only=True, include_model=False),
                                    'reading resources differ from the acquired sources; read again')
    if model_record is not None:
        dialect = model_record.get('prompt_dialect')
        if record['model'] is None:
            raise ReadingSourcesChanged([{'kind': 'model', 'id': model_record.get('id'),
                                          'change': 'added'}],
                                        'read the complete selected model guidance with --model before using this target')
        selected = record['model']['service']
        if selected is not None and service is not None and selected != service:
            raise ReadingSourcesChanged([{'kind': 'model', 'id': model_record.get('id'),
                                          'before': selected, 'after': service}],
                                        'delivered model guidance belongs to a different service')
        if (record['model']['id'] != model_record.get('id') or
                record['model']['record_sha256'] != c.content_id(model_record)):
            raise ReadingSourcesChanged([{'kind': 'model', 'id': model_record.get('id'),
                                          'before': record['model']['record_sha256'],
                                          'after': c.content_id(model_record)}],
                                        'delivered model guidance differs from the selected model edition')
        if selected is not None and len([row for row in model_record.get('offerings', [])
                                         if row.get('service') == selected]) != 1:
            raise ValueError('delivered model guidance names no unique offering in the acquired model')
        current, _ = _model_material(model_record, selected)
        if record['model']['guidance_sha256'] != current['guidance_sha256']:
            raise ReadingSourcesChanged([{'kind': 'model', 'id': current['id'],
                                          'before': record['model'], 'after': current}],
                                        'delivered model guidance differs from the current guidance')
    if _knowledge_requirements(manifest)['writing']:
        _require_dialect(record, bodies, dialect)


def _add_runtime_arguments(parser: argparse.ArgumentParser) -> None:
    from pack_runtime_cli import add_pack_runtime_arguments
    add_pack_runtime_arguments(parser)


def _configure_runtime(args: argparse.Namespace, parser: argparse.ArgumentParser) -> dict | None:
    from pack_runtime_cli import resolve_pack_runtime
    from catalog_retrieval.runtime import configure_pack_runtime
    runtime = resolve_pack_runtime(parser, args)
    configure_pack_runtime(runtime.settings)
    return {'state_file': str(runtime.settings.state_file), 'cache_dir': str(runtime.settings.cache_dir),
            'managed_root': str(runtime.settings.managed_root), 'extra_roots': [str(p) for p in runtime.pack_roots]}


def _runtime_context(runtime: dict | None):
    """Resolve the exact runtime paths captured with a reading snapshot."""
    if runtime is None:
        return None
    from pack_manager import default_settings
    from pack_runtime_cli import PackRuntimeContext
    roots = tuple(Path(p) for p in runtime['extra_roots'])
    settings = default_settings(state_file=Path(runtime['state_file']), cache_dir=Path(runtime['cache_dir']),
                                managed_root=Path(runtime['managed_root']), extra_roots=roots)
    return PackRuntimeContext(settings, roots)


def _restore_runtime(runtime: dict | None) -> None:
    context = _runtime_context(runtime)
    if context is not None:
        from catalog_retrieval.runtime import configure_pack_runtime
        configure_pack_runtime(context.settings)



def ledger_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    raw = c.read(path)
    if raw and not raw.endswith(b'\n'):
        raise ValueError(f'incomplete reading ledger: {path}')
    rows = []
    for line in raw.splitlines():
        if not line.strip():
            raise ValueError(f'empty reading ledger row: {path}')
        row = c.decode(line)
        c.exact(row, manifest_fields(row) | {'at', 'key_sha256', 'cwd', 'delivery'}, 'reading ledger row')
        c.sha(row['key_sha256'])
        c.text(row['at'], 'reading timestamp'); c.text(row['cwd'], 'reading cwd')
        _validate_manifest(row)
        _validate_delivery(row)
        rows.append(row)
    return rows


def _body_identity(metadata: dict) -> str:
    """Identify delivered bytes together with their exact source and model scope."""
    return c.content_id(metadata)


def _document_body(document_id: str, section) -> dict:
    return {'kind': 'document-section', 'document_id': document_id, **section.metadata()}


def _section_content_available(metadata: dict, issuance: dict, ledger: Path, *, read_body=None) -> bool:
    """Confirm the retained complete section bytes before same-context reuse."""
    if metadata.get('kind') != 'document-section':
        return False
    snapshot = issuance['delivery']['snapshot']
    try:
        folder = (_snapshot_dir(ledger, snapshot) if snapshot is not None
                  else ledger.parent / 'reading-content')
        acquire = read_body or c.object_read
        return len(acquire(folder, metadata['sha256'])) == metadata['size']
    except (ValueError, OSError):
        return False


def _store_document_content(folder: Path, acquired: list[tuple[dict, bytes]], required: list[dict]) -> None:
    """Retain each selected complete section with its owning delivery snapshot."""
    actual = {_body_identity(meta): raw for meta, raw in acquired}
    for body in required:
        if body['kind'] != 'document-section':
            continue
        raw = actual.get(_body_identity(body))
        if raw is None or len(raw) != body['size'] or c.digest(raw) != body['sha256']:
            raise ValueError('retained reading section differs from its acquired body')
        path = c.local(folder, 'objects/' + body['sha256'], exists=False)
        if path.exists():
            if c.read(path) != raw:
                c.atomic(path, raw, replace=True)
        else:
            c.object_store(folder, raw)


def _reuse_provenance(available: dict, body: dict) -> dict:
    return {'body': body, 'origin': available['origin'], 'reused_from': available['reused_from'],
            'source_body': available['body']}


def _uncovered_ranges(required: list[tuple[int, int]], available: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Find unshown byte intervals within one immutable section or resource body."""
    missing = []
    for start, end in _merged_ranges(required):
        reach = start
        for low, high in _merged_ranges(available):
            if high <= reach or low >= end:
                continue
            if low > reach:
                missing.append((reach, min(low, end)))
            reach = max(reach, min(high, end))
        if reach < end:
            missing.append((reach, end))
    return missing


def _body_covers(known: dict, required: dict) -> bool:
    """A complete retained unit proves only that exact selected unit."""
    return known == required


def _validate_body_scope(manifest: dict, metadata: list[dict]) -> None:
    """Require one complete body for every selected knowledge unit."""
    required = {('document-section', document['document_id'], section['section_id']): section
                for document in manifest['documents'] for section in document['sections']}
    required.update({('resource', name): value for name, value in manifest['resources'].items()
                     if value['status'] == 'present'})
    if manifest['model'] is not None:
        required[('model', 'model-guidance/' + manifest['model']['id'])] = manifest['model']
    seen = set()
    for item in metadata:
        kind = item.get('kind')
        identity = (('document-section', item.get('document_id'), item.get('section_id'))
                    if kind == 'document-section' else
                    (kind, item.get('resource') if kind == 'resource' else item.get('path')))
        if identity not in required or identity in seen:
            raise ValueError('reading delivery body differs from its required source scope')
        seen.add(identity)
        expected = required[identity]
        if type(item.get('size')) is not int or item['size'] < 0:
            raise ValueError('reading delivery body has an invalid byte size')
        if kind == 'document-section':
            c.exact(item, {'kind', 'document_id', 'section_id', 'sha256', 'size'}, 'delivered section')
            valid = all(item[key] == expected[key] for key in ('section_id', 'sha256', 'size'))
        elif kind == 'resource':
            c.exact(item, {'kind', 'resource', 'status', 'source_pack', 'path', 'sha256',
                           'source_sha256', 'dialect', 'size'}, 'delivered resource')
            valid = all(item[field] == expected[field]
                        for field in ('status', 'source_pack', 'path', 'dialect'))
            valid = valid and item['source_sha256'] == expected['sha256']
        else:
            c.exact(item, {'kind', 'path', 'sha256', 'size', 'id', 'record_sha256',
                           'service', 'guidance_sha256'}, 'delivered model')
            valid = all(item[field] == expected[field] for field in expected)
            valid = valid and item['sha256'] == expected['guidance_sha256']
        c.sha(item['sha256'])
        if not valid:
            raise ValueError('reading delivery body differs from its manifest')
    if seen != set(required):
        raise ValueError('reading delivery does not cover all required bodies')


def _validate_delivery(row: dict) -> None:
    delivery = row['delivery']
    c.exact(delivery, {'snapshot', 'known_readings', 'bodies'}, 'reading delivery')
    if delivery['snapshot'] is not None:
        c.sha(delivery['snapshot'])
    known = delivery['known_readings']
    if not isinstance(known, list) or known != sorted(set(known)):
        raise ValueError('known readings must be unique key hashes')
    for key in known:
        c.sha(key)
    if not isinstance(delivery['bodies'], list):
        raise ValueError('reading delivery bodies must be an array')
    for item in delivery['bodies']:
        c.exact(item, {'body', 'origin', 'reused_from', 'source_body'}, 'reading body provenance')
        c.exact(item['origin'], {'key_sha256', 'snapshot'}, 'reading body origin')
        c.sha(item['origin']['key_sha256'])
        if item['origin']['snapshot'] is not None:
            c.sha(item['origin']['snapshot'])
        if item['reused_from'] is None:
            if (item['source_body'] is not None or
                    item['origin'] != {'key_sha256': row['key_sha256'], 'snapshot': delivery['snapshot']}):
                raise ValueError('newly delivered body has a different issuance origin')
        elif item['reused_from'] not in known:
            raise ValueError('reused body has no explicit same-context source reading')
        elif not isinstance(item['source_body'], dict) or not _body_covers(item['source_body'], item['body']):
            raise ValueError('reused body exceeds its complete source delivery')
    _validate_body_scope(row, [item['body'] for item in delivery['bodies']])


def _known_bodies(keys: list[str], ledger: Path) -> tuple[list[str], list[dict]]:
    """Select only complete issued readings explicitly asserted by this context."""
    if not keys:
        return [], []
    rows = _issuance_index(ledger_rows(ledger))
    known, bodies = [], {}
    contents = {}
    def read_body(folder: Path, digest: str) -> bytes:
        identity = (folder, digest)
        if identity not in contents:
            contents[identity] = c.object_read(folder, digest)
        return contents[identity]
    for key in dict.fromkeys(keys):
        digest = c.digest(_hex(key, 32, 'reading key').encode('ascii'))
        row = rows.get(digest)
        if row is None:
            raise ValueError('reading key has no issuance row in the selected ledgers')
        known.append(row['key_sha256'])
        for item in row['delivery']['bodies']:
            bodies[_body_identity(item['body'])] = {
                'body': item['body'], 'origin': item['origin'], 'reused_from': row['key_sha256'],
                'section_content_available': _section_content_available(item['body'], row, ledger,
                                                                         read_body=read_body)}
    return sorted(known), list(bodies.values())


def _reuse_acquired(acquired: list[tuple[dict, bytes]], available: list[dict]) -> tuple[list, list, list]:
    """Reuse complete explicitly known section identities and unchanged bytes."""
    indexed = {_body_identity(item['body']): item for item in available
               if item['body']['kind'] != 'document-section' or item['section_content_available']}
    required, reused, pending = [], [], []
    for metadata, raw in acquired:
        body = dict(metadata, size=len(raw))
        required.append(body)
        found = indexed.get(_body_identity(body))
        if found is None:
            pending.append((body, raw))
        else:
            reused.append(_reuse_provenance(found, body))
    return required, reused, pending


def _current_bodies(acquired: list[tuple[dict, bytes]], required: list[dict]) -> bool:
    """Match each required unit to its newly acquired complete body bytes."""
    actual = {_body_identity(dict(metadata, size=len(raw))): raw for metadata, raw in acquired}
    if set(actual) != {_body_identity(body) for body in required}:
        return False
    return all(len(actual[_body_identity(body)]) == body['size']
               and c.digest(actual[_body_identity(body)]) == body['sha256'] for body in required)


def _issuance_index(rows: list[dict]) -> dict[str, dict]:
    indexed = {}
    for row in rows:
        key = row['key_sha256']
        if key in indexed and (not same_manifest(row, indexed[key]) or row['delivery'] != indexed[key]['delivery']):
            raise ValueError('reading key has conflicting issuance records')
        indexed[key] = row
    return indexed


def _check_reused_bodies(snapshot: dict, ledger: Path) -> None:
    """Recheck complete issuance and retained bytes for each reused section."""
    rows = _issuance_index(ledger_rows(ledger)) if snapshot['reused_bodies'] else {}
    source_bodies = {}
    for item in snapshot['reused_bodies']:
        key = item['reused_from']
        if key not in snapshot['known_readings'] or key not in rows:
            raise ValueError('same-context body has no complete source issuance')
        if key not in source_bodies:
            source_bodies[key] = {_body_identity(previous['body']): previous
                                  for previous in rows[key]['delivery']['bodies']}
        available = source_bodies[key]
        previous = available.get(_body_identity(item['source_body']))
        if (previous is None or previous['origin'] != item['origin'] or
                not _body_covers(previous['body'], item['body'])):
            raise ValueError('same-context body differs from its complete source issuance')
        if (item['body']['kind'] == 'document-section'
                and not _section_content_available(item['body'], rows[key], ledger)):
            raise ValueError('same-context section content is unavailable; start the current reading again '
                             'to redeliver the required section bodies')
    selected = [item['body'] for item in snapshot['reused_bodies']] + snapshot['bodies']
    if sorted(map(_body_identity, selected)) != sorted(map(_body_identity, snapshot['required_bodies'])):
        raise ValueError('reading snapshot does not cover its required bodies')
    _validate_body_scope(snapshot['manifest'], snapshot['required_bodies'])


def _validate_manifest(value: dict[str, Any]) -> None:
    c.text(value.get('route'), 'reading route')
    execution_routes.require_scope(value.get('operation'), value.get('execution'),
                                   value.get('scope'), value.get('source_kind'))
    execution_routes.require_authoring_scope(value.get('authoring_scope'), value.get('operation'), value.get('execution'))
    _validate_model(value.get('model'))
    features = value.get('features')
    if not isinstance(features, list) or any(not isinstance(x, str) or not x for x in features):
        raise ValueError('reading features must be explicit strings')
    if features != sorted(set(features)):
        raise ValueError('reading features must be normalized and unique')
    documents = value.get('documents')
    if not isinstance(documents, list) or not documents:
        raise ValueError('reading documents must be a nonempty array')
    seen = set()
    for item in documents:
        c.exact(item, {'document_id', 'sections'}, 'reading document')
        identifier = item['document_id']
        record_path(identifier)
        if identifier in seen:
            raise ValueError('duplicate reading document')
        seen.add(identifier)
        sections = item['sections']
        if not isinstance(sections, list) or not sections:
            raise ValueError('reading document needs complete selected sections')
        section_ids = set()
        for section in sections:
            c.exact(section, {'section_id', 'sha256', 'size'}, 'reading section')
            name = section['section_id']
            if (not isinstance(name, str) or not re.fullmatch(SECTION_ID_PATTERN, name)
                    or name in section_ids):
                raise ValueError('reading section ID is invalid or duplicated')
            section_ids.add(name); c.sha(section['sha256'])
            if type(section['size']) is not int or section['size'] <= 0:
                raise ValueError('reading section needs its complete body size')
    _validate_resources(value)


def capture(route: str, features: list[str] | None = None, *, execution: str, root: Path = ROOT,
            operation: str | None = None, dialect: str | None = None, resource_reader=None,
            scope: str | None = None, source_kind: str | None = None,
            authoring_scope: dict | None = None,
            model: str | None = None, service: str | None = None, model_record: dict | None = None,
            model_file: Path | None = None,
            read_source: Callable[[str], bytes] | None = None,
            document_reader: DocumentReader | None = None) -> tuple[dict, list[tuple[dict, bytes]]]:
    if model_file is not None:
        if model is not None or model_record is not None:
            raise ValueError('select one catalog model or acquired model file')
        model_record = c.load(model_file)
    if model is not None:
        if model_record is None:
            model, model_record = _selected_model(model)
        elif model_record.get('id') != model:
            raise ValueError('acquired model differs from the requested reading target')
    if model_record is not None:
        family = model_record.get('prompt_dialect')
        if dialect is not None and dialect != family:
            raise ValueError('selected model and prompt family differ')
        dialect = family
    if service is not None and model_record is None:
        raise ValueError('a service selection requires a selected model')
    read_once = _read_once(root, read_source)
    documents = document_reader or DocumentReader(read_once)
    resolved = execution_routes.resolve(route, features, operation=operation, execution=execution,
                                        root=root, read_source=read_once, scope=scope, source_kind=source_kind,
                                        authoring_scope=authoring_scope, document_reader=documents)
    bodies = []
    for entry in resolved['reads']:
        document = documents.acquire(entry['document_id'])
        for selected in entry['sections']:
            section = document.section(selected['section_id'])
            bodies.append((_document_body(document.document_id, section), section.raw))
    manifest = {'route': resolved['route'], 'operation': resolved['operation'], 'execution': resolved['execution'],
                'scope': resolved['scope'], 'source_kind': resolved['source_kind'], 'features': resolved['features'],
                **({'authoring_scope': resolved['authoring_scope']} if 'authoring_scope' in resolved else {}),
                'documents': resolved['reads'], 'model': None}
    knowledge = _knowledge_requirements(manifest)
    if resource_reader is None and knowledge['writing'] and 'prompt-dialect' in resolved['features'] and not (
            resolved['operation'] in SAVED_INPUT_OPERATIONS and dialect is None):
        resource_reader = _live_resource_reader()
    _capture_resources(manifest, bodies, dialect, resource_reader)
    if model_record is not None and knowledge['model']:
        metadata, raw = _model_material(model_record, service)
        manifest['model'] = metadata
        bodies.append(({'kind': 'model', 'path': 'model-guidance/' + metadata['id'],
                        'sha256': c.digest(raw), **metadata}, raw))
    return manifest, bodies


def _ledger_lock(ledger: Path):
    """Initialize the real issuance journal and own one read/replace cycle."""
    if not ledger.exists():
        try:
            c.atomic(ledger, b'')
        except FileExistsError:
            pass
    return c.file_lock(ledger)


def _issue(manifest: dict, ledger: Path, *, bodies: list[dict], reused: list[dict] | None = None,
           known_readings: list[str] | None = None, snapshot: str | None = None,
           key: str | None = None, at: str | None = None, cwd: str | None = None) -> dict:
    """Serialize only the ledger read and append. Fixed values support fixtures."""
    key = _hex(key or secrets.token_hex(16), 32, 'reading key')
    row = {**manifest, 'at': at or datetime.datetime.now(datetime.timezone.utc).isoformat(),
           'cwd': cwd if cwd is not None else str(Path.cwd()), 'key_sha256': c.digest(key.encode('ascii'))}
    row['delivery'] = {'snapshot': snapshot, 'known_readings': known_readings or [],
                       'bodies': [*({'body': metadata,
                                    'origin': {'key_sha256': row['key_sha256'], 'snapshot': snapshot},
                                    'reused_from': None, 'source_body': None} for metadata in bodies), *(reused or [])]}
    _validate_delivery(row)
    with _ledger_lock(ledger):
        existing = ledger_rows(ledger)
        for old in existing:
            if old['key_sha256'] == row['key_sha256'] and (not same_manifest(old, row) or old['delivery'] != row['delivery']):
                raise ValueError('reading key already belongs to different documents or route')
        if row in existing:
            return {'reading_key': key, 'row': row}
        c.atomic(ledger, b''.join(c.encoded(x) for x in existing) + c.encoded(row), replace=ledger.exists())
        return {'reading_key': key, 'row': row}


def _begin_output(stream: TextIO, body: list[dict], metadata: dict) -> None:
    """Flush actual source text before publishing its successful delivery."""
    if isinstance(stream, TextReadingOutput):
        stream.begin(body, metadata)
        return
    stream.write('{"metadata": ' + json.dumps(metadata, ensure_ascii=False))
    stream.write(', "body": ' + json.dumps(body, ensure_ascii=False))
    stream.flush()


def _finish_output(stream: TextIO, result: dict) -> None:
    visible = {key: value for key, value in result.items() if key not in {'body', 'metadata', 'issued', 'delivered'}}
    if result.get('mode') in {'all', 'section'}:
        # Text pages need their current continuation and recovery commands.
        # The complete source index owns optional whole-scope navigation and
        # selection attribution; repeating those alongside every page obscures
        # the remaining text and increases the host's output allowance.
        if 'actions' in result:
            visible['actions'] = {name: value for name, value in result['actions'].items() if name != 'all'}
            if not result.get('body'):
                visible['actions']['replay'] = None
        if 'selection_summary' in result:
            visible['selection_summary'] = {'action_ref': '#/actions/index',
                'reason': 'Inspect the complete selected scope and source-selection reasons.'}
    if isinstance(stream, TextReadingOutput):
        stream.finish(visible)
        return
    stream.write(', ' + json.dumps(visible, ensure_ascii=False)[1:] + '\n')
    stream.flush()


def _failed_output(stream: TextIO, exc: Exception) -> None:
    """Finish an already begun structured response without a successful receipt."""
    value = {'ok': False, 'error': str(exc), 'reading': None,
             **(exc.as_dict() if isinstance(exc, (ReadingSourcesChanged, ReadingInvocationConflict)) else {})}
    try:
        _finish_output(stream, value)
    except OSError:
        return
    exc.reading_result_written = True


def issue(route: str, features: list[str] | None = None, *, execution: str, root: Path = ROOT,
          studio: Path | None = None, ledger: Path | None = None, stream: TextIO | None = None,
          key: str | None = None, at: str | None = None, cwd: str | None = None,
          dialect: str | None = None, operation: str | None = None,
          scope: str | None = None, source_kind: str | None = None,
          authoring_scope: dict | None = None,
          model: str | None = None, service: str | None = None,
          model_file: Path | None = None, model_record: dict | None = None) -> dict:
    """Output all bytes before issuing evidence. Fixed key/time are fixture inputs."""
    stream = sys.stdout if stream is None else stream
    target = ledger if ledger is not None else ledger_candidates(studio=studio)[0]
    ledger_rows(target)
    manifest, bodies = capture(route, features, root=root, dialect=dialect, operation=operation, execution=execution, model=model,
                               service=service, model_file=model_file, model_record=model_record,
                               scope=scope, source_kind=source_kind, authoring_scope=authoring_scope)
    _begin_output(stream, [{'metadata': meta, 'text': raw.decode('utf-8')}
                           for meta, raw in bodies], manifest)
    try:
        current, _ = capture(route, features, root=root, dialect=dialect, operation=operation, execution=execution,
                             model=model, service=service, model_file=model_file, model_record=model_record,
                             scope=scope, source_kind=source_kind, authoring_scope=authoring_scope)
        if manifest != current:
            raise ReadingSourcesChanged(source_changes(manifest, current))
        _store_document_content(target.parent / 'reading-content', bodies,
                                [dict(meta, size=len(raw)) for meta, raw in bodies])
        issued = _issue(manifest, target, bodies=[dict(meta, size=len(raw)) for meta, raw in bodies],
                        key=key, at=at, cwd=cwd)
    except (ValueError, OSError) as exc:
        _failed_output(stream, exc)
        raise
    _finish_output(stream, {'ok': True, 'reading': {'key': issued['reading_key'], 'record': None},
                            'actions': {'continue': None}})
    return issued


def _find_row(record: dict, ledgers: list[Path]) -> dict:
    key_hash = c.digest(_hex(record.get('reading_key'), 32, 'reading key').encode('ascii'))
    matching = []
    for path in dict.fromkeys(ledgers):
        for row in ledger_rows(path):
            if row['key_sha256'] == key_hash:
                matching.append(row)
    if not matching:
        raise ValueError('reading key has no issuance row in the selected ledgers')
    if any(not same_manifest(row, record) for row in matching):
        raise ValueError('reading issuance differs from the supplied route, features or document versions')
    if any(row['delivery'] != matching[0]['delivery'] for row in matching[1:]):
        raise ValueError('reading key has conflicting delivery provenance')
    return matching[0]


def validate_record_content(record: Any) -> None:
    """Validate a source-delivery receipt without claiming understanding or authority."""
    c.exact(record, manifest_fields(record) | {'reading_key'}, 'route reading')
    _validate_manifest(record)
    _hex(record['reading_key'], 32, 'reading key')


def require_route_reading(record: Any, *, root: Path = ROOT, ledgers: list[Path] | None = None,
                          studio: Path | None = None, package_root: Path | None = None,
                          routes: set[str] | None = None, features: list[str] | None = None,
                          operation: str | None = None, execution: str | None = None,
                          scope: str | None = None, source_kind: str | None = None,
                          authoring_scope: dict | None = None,
                          dialect: Any = _NO_MODEL, resource_reader=None,
                          model_record: dict | None = None, service: str | None = None,
                          read_source: Callable[[str], bytes] | None = None) -> dict:
    """Verify actual full delivery and coverage of the current operation.

    A delivered superset can cover a narrower operation only when all its
    required source editions match. Consumers supply the task's actual execution
    kind; integrity-only copies retain the delivered scope. A prior receipt remains a delivery fact,
    not evidence that a new agent has read or understood those documents.
    """
    validate_record_content(record)
    if routes is not None and record['route'] not in routes:
        raise ValueError('reading route must be one of: ' + ', '.join(sorted(routes)))
    row = _find_row(record, ledgers if ledgers is not None else ledger_candidates(studio=studio, package_root=package_root))
    selected_features = features if features is not None else record['features']
    read_source = _read_once(root, read_source)
    documents = DocumentReader(read_source)
    selected_operation = operation or record['operation']
    selected_authoring = authoring_scope if authoring_scope is not None else record.get('authoring_scope')
    if selected_operation in {'adopt', 'withdraw'}:
        scope = scope if scope is not None else record['scope']
        source_kind = source_kind if source_kind is not None else record['source_kind']
    expected = execution_routes.resolve(record['route'], selected_features,
                                        operation=selected_operation, scope=scope, source_kind=source_kind,
                                        execution=execution if execution is not None else record['execution'],
                                        root=root, read_source=read_source, authoring_scope=selected_authoring,
                                        document_reader=documents)
    current, bodies = capture(record['route'], selected_features, root=root,
                              operation=expected['operation'], execution=expected['execution'],
                              scope=expected['scope'], source_kind=expected['source_kind'],
                              authoring_scope=selected_authoring,
                              dialect=bound_dialect(record) if 'prompt-dialect' in expected['features'] else None,
                              resource_reader=resource_reader, read_source=read_source,
                              document_reader=documents)
    changes = source_changes(record, current, required_only=True, include_model=False)
    if changes:
        missing_features = any(change['kind'] == 'feature' for change in changes)
        message = ('reading features do not cover the execution features' if missing_features else
                   'reading documents do not cover the current operation and execution; read their complete contract')
        raise ReadingSourcesChanged(changes, message)
    if _knowledge_requirements(current)['writing']:
        _require_dialect(record, bodies, dialect)
    if model_record is not None and _knowledge_requirements({'authoring_scope': selected_authoring})['model']:
        require_model_reading(record, model_record=model_record, service=service,
                              resource_reader=resource_reader or (_live_resource_reader()
                                  if _knowledge_requirements(record)['writing'] else lambda name: None))
    return row


def require_task_reading(record: Any, *, task: dict, studio: Path, read_input=None,
                         root: Path = ROOT, **arguments) -> dict:
    """Check final-input coverage from the task's current, captured owners.

    Receipt integrity can retain the delivered scope. Publishing a completed
    task instead derives its required final scope independently of that receipt.
    """
    from production_reading_scope import from_task
    expected = from_task(studio, task, read_source=read_input)
    return require_route_reading(record, root=root, studio=studio, routes={task['route']},
        features=task['features'], execution=task['execution'],
        operation='author' if task['execution'] == 'authored' else 'prepare',
        authoring_scope=expected, **arguments)


def resolve_issuance(key: str, *, studio: Path | None = None,
                     ledgers: list[Path] | None = None) -> dict:
    """Resolve a supplied key to one consistent locally issued document edition."""
    digest = c.digest(_hex(key, 32, 'reading key').encode('ascii'))
    matches = [row for path in dict.fromkeys(ledgers if ledgers is not None else ledger_candidates(studio=studio))
               for row in ledger_rows(path) if row['key_sha256'] == digest]
    if not matches:
        raise ValueError('reading key has no issuance row in the selected ledgers')
    if any(not same_manifest(row, matches[0]) or row['delivery'] != matches[0]['delivery'] for row in matches[1:]):
        raise ValueError('reading key has conflicting issuance records')
    return {'reading_key': key, 'row': matches[0]}


def check_snapshot_issuance(snapshot: str, issued: dict, *, studio: Path | None = None) -> None:
    """Check a supplied delivery selector without making retention a key condition."""
    _hex(snapshot, 64, 'reading snapshot')
    paths = [path.parent / 'reading-snapshots' / snapshot / 'snapshot.json'
             for path in ledger_candidates(studio=studio)]
    existing = [path for path in dict.fromkeys(paths) if path.is_file()]
    if not existing:
        # A completed delivery snapshot may be discarded. The issuance row
        # remains the authoritative key witness.
        return
    for path in existing:
        value = c.load(path)
        if c.content_id(value) != snapshot:
            raise ValueError('reading snapshot address mismatch')
        if any(issued['row'][key] != item for key, item in value['manifest'].items()):
            raise ValueError('selected delivery snapshot belongs to another reading')


def build_record(issued: dict, *, root: Path = ROOT, studio: Path | None = None,
                 ledgers: list[Path] | None = None, dialect: Any = _NO_MODEL,
                 operation: str | None = None, execution: str | None = None,
                 scope: str | None = None, source_kind: str | None = None,
                 authoring_scope: dict | None = None,
                 features: list[str] | None = None) -> dict:
    """Resolve the delivery record from its issuance; the author copies no source metadata."""
    c.exact(issued, {'reading_key', 'row'}, 'issued reading')
    result = draft_record(issued)
    require_route_reading(result, root=root, studio=studio, ledgers=ledgers, dialect=dialect,
                          operation=operation, execution=execution, features=features,
                          scope=scope, source_kind=source_kind, authoring_scope=authoring_scope)
    return result


def copy_issuance(record: dict, destination: Path, *, root: Path = ROOT, studio: Path | None = None,
                  ledgers: list[Path] | None = None, package_root: Path | None = None) -> dict:
    """Copy issuance integrity; the consumer checks applicability to its own scope."""
    validate_record_content(record)
    row = _find_row(record, ledgers if ledgers is not None else ledger_candidates(studio=studio, package_root=package_root))
    with _ledger_lock(destination):
        rows = ledger_rows(destination)
        matching = [old for old in rows if old['key_sha256'] == row['key_sha256']]
        if any(not same_manifest(old, row) or old['delivery'] != row['delivery'] for old in matching):
            raise ValueError('destination ledger has a conflicting issuance')
        if not matching:
            c.atomic(destination, b''.join(c.encoded(old) for old in rows) + c.encoded(row), replace=destination.exists())
    return row

def _snapshot_dir(ledger: Path, snapshot: str) -> Path:
    return c.local(ledger.parent, 'reading-snapshots/' + _hex(snapshot, 64, 'reading snapshot'))


def _cursor(ledger: Path, cursor: str) -> tuple[Path, dict, dict]:
    parts = cursor.split(':')
    if len(parts) != 2:
        raise ValueError('reading cursor must identify a snapshot and a delivered page')
    folder = _snapshot_dir(ledger, parts[0])
    snapshot = c.load(c.local(folder, 'snapshot.json'))
    if c.content_id(snapshot) != parts[0]:
        raise ValueError('reading snapshot address mismatch')
    receipt = c.load(c.local(folder, 'pages/' + _hex(parts[1], 64, 'reading page') + '.json'))
    if c.content_id(receipt) != parts[1] or receipt['snapshot'] != parts[0]:
        raise ValueError('reading page address mismatch')
    return folder, snapshot, receipt


def _position_value(snapshot: dict, position: dict) -> tuple[int, int]:
    """Validate a cursor within one immutable body, then normalize its boundary."""
    c.exact(position, {'body', 'offset'}, 'reading position')
    index, offset = position['body'], position['offset']
    if (type(index) is not int or type(offset) is not int or index < 0 or offset < 0
            or index > len(snapshot['bodies'])):
        raise ValueError('reading position is outside its section bodies')
    if index == len(snapshot['bodies']):
        if offset:
            raise ValueError('reading position is beyond its final body')
        return index, 0
    if offset > snapshot['bodies'][index]['size']:
        raise ValueError('reading position exceeds its section body')
    while index < len(snapshot['bodies']) and offset == snapshot['bodies'][index]['size']:
        index, offset = index + 1, 0
    return index, offset


def _position_data(position: tuple[int, int]) -> dict:
    return {'body': position[0], 'offset': position[1]}


def _span_size(snapshot: dict, start: tuple[int, int], end: tuple[int, int]) -> int:
    """Count transport bytes across an ordered sequence of complete units."""
    if start > end:
        raise ValueError('reading transport span is reversed')
    if start[0] == end[0]:
        return end[1] - start[1]
    return (snapshot['bodies'][start[0]]['size'] - start[1]
            + sum(body['size'] for body in snapshot['bodies'][start[0] + 1:end[0]]) + end[1])


def _pending_span(snapshot: dict, coverage: dict) -> tuple[tuple[int, int], tuple[int, int]]:
    missing = coverage['missing']
    if not missing:
        final = (len(snapshot['bodies']), 0)
        return final, final
    first = missing[0]
    start = (first['body'], first['start'])
    end = _position_value(snapshot, {'body': first['body'], 'offset': first['end']})
    for item in missing[1:]:
        if (item['body'], item['start']) != end:
            break
        end = _position_value(snapshot, {'body': item['body'], 'offset': item['end']})
    return start, end


def _publish_page(path: Path, value: dict) -> None:
    """Commit a content-addressed page once, accepting an identical publisher."""
    raw = c.encoded(value)
    try:
        c.atomic(path, raw)
    except FileExistsError:
        if c.read(path) != raw:
            raise ValueError('reading page collision')


def _remember_page(folder: Path, snapshot: str, page: str) -> None:
    """Own the selected continuation explicitly, independently of source order."""
    c.atomic(folder / 'continuation.json', c.encoded({'snapshot': snapshot, 'page': page}), replace=True)


def _merged_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Combine overlapping delivered chunks within one body only."""
    merged = []
    for start, end in sorted(ranges):
        if start == end:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def snapshot_coverage(folder: Path, snapshot: dict) -> dict:
    """Verify and combine delivered intervals within each immutable body."""
    sid = c.content_id(snapshot)
    bodies = {_body_identity(metadata): (number, metadata)
              for number, metadata in enumerate(snapshot['bodies'])}
    intervals = {number: [] for number in range(len(snapshot['bodies']))}
    pages = []
    for path in (folder / 'pages').glob('*.json'):
        page = c.load(path)
        if c.content_id(page) != path.stem or page['snapshot'] != sid:
            raise ValueError('reading page address mismatch')
        c.exact(page, {'snapshot', 'from', 'to', 'ranges', 'page_bytes'}
                | ({'section'} if 'section' in page else set())
                | ({'index'} if 'index' in page else set())
                | ({'replay_until'} if 'replay_until' in page else set()), 'reading page')
        start, end = _position_value(snapshot, page['from']), _position_value(snapshot, page['to'])
        if start > end or type(page['page_bytes']) is not int or page['page_bytes'] < 4:
            raise ValueError('reading page has an invalid delivery or byte budget')
        if 'replay_until' in page and _position_value(snapshot, page['replay_until']) < end:
            raise ValueError('reading replay ends before its delivered page')
        reach = start
        for item in page['ranges']:
            metadata = {key: value for key, value in item.items()
                        if key not in {'snapshot', 'start', 'end', 'total'}}
            match = bodies.get(_body_identity(metadata))
            if match is None or item['snapshot'] != sid:
                raise ValueError('reading page differs from its source scope')
            number, body = match
            low, high = item['start'], item['end']
            if (type(low) is not int or type(high) is not int
                    or not 0 <= low < high <= body['size']
                    or item['total'] != body['size'] or (number, low) != reach):
                raise ValueError('reading page has an invalid section-local range')
            intervals[number].append((low, high))
            reach = _position_value(snapshot, {'body': number, 'offset': high})
        if reach != end:
            raise ValueError('reading page does not contain its declared body bytes')
        if page.get('index') and page['ranges']:
            raise ValueError('reading navigation cannot declare delivered bytes')
        pages.append((path.stem, page))
    covered, missing, delivered = {}, [], 0
    for number, body in enumerate(snapshot['bodies']):
        ranges = _merged_ranges(intervals[number])
        covered[_body_identity(body)] = ranges
        delivered += sum(end - start for start, end in ranges)
        missing.extend({'body': number, 'start': start, 'end': end}
                       for start, end in _uncovered_ranges([(0, body['size'])], ranges))
    total = sum(body['size'] for body in snapshot['bodies'])
    return {'pages': pages, 'covered': covered, 'missing': missing,
            'total_bytes': total, 'delivered_bytes': delivered,
            'remaining_bytes': total - delivered}


def _json_headings(raw: bytes, metadata: dict) -> list[tuple[int, str, int]]:
    """Locate exact resource sections or offering cards in their serialized body."""
    text = raw.decode('utf-8')
    decoder = json.JSONDecoder()
    def whitespace(index):
        while index < len(text) and text[index].isspace():
            index += 1
        return index
    index = whitespace(0)
    if metadata['kind'] == 'resource':
        wanted = 'sections' if metadata['resource'] == 'prompt-writing-guide' else 'dialects'
        if text[index:index + 1] != '{':
            return []
        index = whitespace(index + 1)
        while text[index:index + 1] != '}':
            key, index = decoder.raw_decode(text, index)
            index = whitespace(index)
            if text[index:index + 1] != ':':
                raise ValueError('invalid resource section boundary')
            index = whitespace(index + 1)
            if key == wanted:
                break
            _, index = decoder.raw_decode(text, index)
            index = whitespace(index)
            if text[index:index + 1] == ',':
                index = whitespace(index + 1)
        else:
            return []
    if text[index:index + 1] != '[':
        return []
    headings = []
    index = whitespace(index + 1)
    while text[index:index + 1] != ']':
        start = index
        value, index = decoder.raw_decode(text, index)
        title = None
        if isinstance(value, dict):
            title = value.get('title') or value.get('heading') or value.get('id') or value.get('service')
        headings.append((len(text[:start].encode('utf-8')), str(title or 'Item ' + str(len(headings) + 1)), 1))
        index = whitespace(index)
        if text[index:index + 1] == ',':
            index = whitespace(index + 1)
    return headings


def _source_selector(metadata: dict) -> str:
    if metadata['kind'] == 'document-section':
        return metadata['document_id']
    if metadata['kind'] == 'resource':
        return 'resource:' + metadata['resource']
    return 'model:' + metadata['id']


def _sections(folder: Path, snapshot: dict, read_body=None) -> list[dict]:
    """Navigate complete stable section identities and explicit non-document units."""
    read_body = read_body or (lambda digest: c.object_read(folder, digest))
    result = []
    for number, metadata in enumerate(snapshot['bodies']):
        source = _source_selector(metadata)
        if metadata['kind'] == 'document-section':
            parts = [{'selector': source + '#' + metadata['section_id'],
                      'section_id': metadata['section_id'], 'document_id': metadata['document_id'],
                      'start': 0, 'end': metadata['size']}]
        else:
            raw = read_body(metadata['sha256'])
            if len(raw) != metadata['size']:
                raise ValueError('reading body size differs from its snapshot')
            headings = _json_headings(raw, metadata)
            if not headings or headings[0][0] > 0:
                headings.insert(0, (0, 'Source opening' if headings else 'Complete source', 0))
            parts = [{'selector': source + '#' + str(index + 1),
                      'heading': heading, 'level': level, 'start': start,
                      'end': headings[index + 1][0] if index + 1 < len(headings) else len(raw)}
                     for index, (start, heading, level) in enumerate(headings)]
        for part in parts:
            result.append({**part, 'source': source, 'body': number,
                'from': {'body': number, 'offset': part['start']},
                'to': _position_data(_position_value(snapshot, {'body': number, 'offset': part['end']}))})
    return result


def _section_scope(sections: list[dict], selector: str) -> dict:
    exact = [row for row in sections if row['selector'] == selector]
    if exact:
        return exact[0]
    source = [row for row in sections if row['source'] == selector]
    if source:
        return {'selector': selector, 'source': selector, 'from': source[0]['from'], 'to': source[-1]['to']}
    raise ValueError('unknown pending source or section: ' + selector +
                     '; open the snapshot index and select an exact returned selector')


def _remaining_in(number: int, low: int, high: int, missing: list[dict]) -> int:
    return sum(max(0, min(high, item['end']) - max(low, item['start']))
               for item in missing if item['body'] == number)


def _navigation(snapshot: dict, coverage: dict, sections: list[dict],
                index_source: str | None = None) -> tuple[list[dict], dict[str, str]]:
    """Group exact required sections under their document and source identities."""
    known = {_body_identity(item['body']): item for item in snapshot['reused_bodies']}
    grouped = {}
    for metadata in snapshot['required_bodies']:
        grouped.setdefault(_source_selector(metadata), []).append(metadata)
    sources, reasons = [], {}
    def reason_ids(values):
        result = []
        for value in dict.fromkeys(values):
            identifier = next((key for key, text in reasons.items() if text == value), None)
            if identifier is None:
                identifier = str(len(reasons) + 1); reasons[identifier] = value
            result.append(identifier)
        return result
    for source, bodies in grouped.items():
        if index_source is not None and index_source != source:
            continue
        document = bodies[0]['kind'] == 'document-section'
        scope = snapshot.get('section_owners', {}).get(source, []) if document else []
        selected_by = snapshot.get('read_owners', {}).get(source, ['selected:' + bodies[0]['kind']])
        fallback = ['Complete selected ' + bodies[0]['kind'] + ' guidance is required for this target.']
        source_reasons = list(dict.fromkeys(item['reason'] for item in scope)) or fallback
        complete = not scope or all(item['whole_source'] for item in scope)
        expanded = index_source is not None or not complete
        visible, states, remaining = [], [], 0
        for metadata in bodies:
            witness = known.get(_body_identity(metadata))
            rows = [row for row in sections if row['source'] == source and
                    (not document or row.get('section_id') == metadata['section_id'])]
            missing = sum(_remaining_in(row['body'], row['start'], row['end'], coverage['missing']) for row in rows)
            remaining += missing
            state = ('known' if witness is not None else 'pending' if missing == metadata['size'] else
                     'partial' if missing else 'delivered')
            states.append(state)
            choices = [item['reason'] for item in scope
                       if item['section_id'] == metadata.get('section_id')] or source_reasons
            if document:
                visible.append({'selector': None if witness is not None else source + '#' + metadata['section_id'],
                    'section_id': metadata['section_id'], 'bytes': metadata['size'],
                    'content_sha256': metadata['sha256'], 'selection_reason_ids': reason_ids(choices),
                    'state': state, 'remaining_bytes': missing,
                    **({'reuse': {'reading_key_sha256': witness['reused_from'], 'origin': witness['origin']}}
                       if witness is not None else {})})
            else:
                visible.extend({'selector': row['selector'], 'heading': row['heading'],
                    'bytes': row['end'] - row['start'], 'selection_reason_ids': reason_ids(choices),
                    'remaining_bytes': _remaining_in(row['body'], row['start'], row['end'], coverage['missing'])}
                    for row in rows)
        state = states[0] if len(set(states)) == 1 else 'partial'
        metadata = ({'kind': 'document', 'document_id': source, 'size': sum(body['size'] for body in bodies)}
                    if document else bodies[0])
        sources.append({'selector': None if state == 'known' else source, **metadata,
            'selected_by': selected_by, 'selection_reason_ids': reason_ids(source_reasons),
            'selection_scope': 'complete-source' if complete else 'selected-sections',
            'state': state, 'remaining_bytes': remaining, 'section_count': len(visible),
            'sections_expanded': expanded, 'sections': visible if expanded else []})
    if index_source is not None and not sources:
        raise ValueError('unknown source index selector: ' + index_source
                         + '; open the snapshot index and choose a source selector')
    return sources, reasons


def _selection_summary(snapshot: dict) -> dict:
    """Measure selected knowledge independently of current-context reuse."""
    reused = {_body_identity(item['body']) for item in snapshot['reused_bodies']}
    owners = {}
    for body in snapshot['required_bodies']:
        selected = snapshot.get('read_owners', {}).get(body.get('document_id', body.get('path')), ['selected:' + body['kind']])
        for owner in selected:
            row = owners.setdefault(owner, {'selected_bytes': 0, 'reused_bytes': 0})
            row['selected_bytes'] += body['size']
            if _body_identity(body) in reused:
                row['reused_bytes'] += body['size']
    scope = snapshot['manifest'].get('authoring_scope') or {}
    return {'operation': snapshot['manifest']['operation'], 'route': snapshot['manifest']['route'],
            'execution': snapshot['manifest']['execution'], 'scope': snapshot['manifest']['scope'],
            'stage': scope.get('stage'), 'composition': scope.get('composition'),
            'change_scope': scope.get('change_scope'), 'profiles': scope.get('profiles', []),
            'by_selection': owners,
            'attribution': 'A source can have several selection owners; owner totals overlap and must not be added.',
            'fresh_context': 'Read every selected current section body; a saved receipt supplies no knowledge to a fresh context.'}


def _record_delivery(result: dict, snapshot: dict, body: list[dict], *, new_snapshot: bool,
                     failed: bool = False) -> None:
    """Count actually flushed body text, including a later source-check failure."""
    context = _operation_context.current()
    if context is None:
        return
    delivered = sum(len(item['text'].encode('utf-8')) for item in body)
    reused = sum(item['body']['size'] for item in snapshot['reused_bodies'])
    progress = result.get('progress') or {}
    context.event('reading_progress', delivered_bytes=delivered,
        reused_bytes=reused if new_snapshot else 0,
        remaining_bytes=progress.get('remaining_bytes'),
        required_bytes=sum(item['size'] for item in snapshot['required_bodies']),
        delivered_pages=int(bool(body)), snapshot=result['snapshot'],
        reading_record=None if failed else (result.get('reading') or {}).get('key'),
        operation=snapshot['manifest']['operation'], choices=snapshot.get('choices'), failed=failed)


def read_page(*, route: str | None = None, features: list[str] | None = None,
              cursor: str | None = None, replay: bool = False, page_bytes: int | str = DEFAULT_PAGE_BYTES,
              root: Path = ROOT, studio: Path | None = None, ledger: Path | None = None,
              stream: TextIO | None = None, runtime: dict | None = None,
              dialect: str | None = None, operation: str | None = None, execution: str | None = None,
              scope: str | None = None, source_kind: str | None = None,
              authoring_scope: dict | None = None, choices_path: str | None = None,
              bind_choices: bool = False, choices_sha256: str | None = None,
              model: str | None = None, service: str | None = None,
              model_file: Path | None = None, known_reading_keys: list[str] | None = None,
              reading_context: str | None = None, host_page_bytes: int | None = None,
              publish_record: bool = False, navigation: bool = False,
              snapshot_id: str | None = None, section: str | None = None,
              index_source: str | None = None) -> dict:
    """Index or deliver exact section bodies; only complete coverage issues a record."""
    page_bytes, page_sizing = page_budget(page_bytes, host_page_bytes)
    if reading_context is not None:
        _hex(reading_context, 32, 'reading context')
    if bind_choices and (studio is None or choices_path is None or choices_sha256 is None):
        raise ValueError('Binding a reading requires the exact --root, --choices and captured authored content.')
    if navigation and (cursor is not None or section is not None):
        raise ValueError('choose a snapshot index or a delivery action')
    if index_source is not None and (not navigation or snapshot_id is None):
        raise ValueError('a source section index requires --snapshot ID --index-source SELECTOR and delivers no body')
    if cursor is not None and (snapshot_id is not None or section is not None):
        raise ValueError('a page cursor fixes its source selection; use --snapshot with --section to choose another')
    stream = sys.stdout if stream is None else stream
    ledger = ledger if ledger is not None else ledger_candidates(studio=studio)[0]
    authoring_studio = studio or _studio(ledger.parent)
    previous = None
    if cursor is None and snapshot_id is None:
        if route is None:
            raise ValueError('a route is required to start reading')
        ledger_rows(ledger)
        read_source = _read_once(root)
        documents = DocumentReader(read_source)
        manifest, acquired = capture(route, features, root=root, dialect=dialect, operation=operation,
                                    execution=execution, model=model, service=service, model_file=model_file,
                                    scope=scope, source_kind=source_kind, authoring_scope=authoring_scope,
                                    read_source=read_source, document_reader=documents)
        resolved = execution_routes.resolve(route, features, operation=operation, execution=execution,
                                            root=root, read_source=read_source, scope=scope, source_kind=source_kind,
                                            authoring_scope=authoring_scope, document_reader=documents)
        automatic_keys = _context_keys(ledger, reading_context, root)
        context_keys = list(dict.fromkeys([*automatic_keys, *(known_reading_keys or [])]))
        known, available = _known_bodies(context_keys, ledger)
        required, reused, pending_bodies = _reuse_acquired(acquired, available)
        bodies = [meta for meta, raw in pending_bodies]
        import production_authoring_state
        task_id = production_authoring_state.active_task_id(authoring_studio)
        snapshot = {'manifest': manifest, 'root': str(root.absolute()), 'runtime': runtime,
                    **({'choices': choices_path} if choices_path is not None else {}),
                    **({'bind_choices': True, 'choices_sha256': _hex(choices_sha256, 64, 'choices content')}
                       if bind_choices else {}),
                    'task_id': task_id, 'model_file': str(model_file.absolute()) if model_file is not None else None,
                    'nonce': secrets.token_hex(16), 'bodies': bodies, 'required_bodies': required,
                    **({'reading_context': reading_context, 'automatic_readings': len(automatic_keys)}
                       if reading_context is not None else {}),
                    'reused_bodies': reused, 'known_readings': known, 'context_keys': context_keys,
                    'read_owners': resolved['read_owners'], 'section_owners': resolved['section_owners']}
        _validate_body_scope(manifest, required)
        sid = c.content_id(snapshot)
        production_authoring_state.remember_reading(authoring_studio, ledger, sid, snapshot, page_bytes)
        folder = c.local(ledger.parent, 'reading-snapshots/' + sid, exists=False)
        folder.mkdir(parents=True)
        c.atomic(folder / 'snapshot.json', c.encoded(snapshot))
        for meta, raw in pending_bodies:
            if meta['kind'] != 'document-section':
                c.object_store(folder, raw)
        _store_document_content(folder, acquired, required)
    else:
        if (route is not None or features or dialect is not None or operation is not None or execution is not None
                or scope is not None or source_kind is not None or authoring_scope is not None or choices_path is not None
                or model is not None or service is not None or model_file is not None or known_reading_keys
                or bind_choices or choices_sha256 is not None):
            raise ValueError('a snapshot fixes its route, operation, execution, destination, source kind, features, model scope and known readings')
        if cursor is not None:
            folder, snapshot, previous = _cursor(ledger, cursor)
        else:
            folder = _snapshot_dir(ledger, snapshot_id)
            snapshot = c.load(c.local(folder, 'snapshot.json'))
            if c.content_id(snapshot) != snapshot_id:
                raise ValueError('reading snapshot address mismatch')
        sid = c.content_id(snapshot)
        if str(root.absolute()) != snapshot['root']:
            raise ValueError('reading snapshot belongs to a different skill root')
        if snapshot.get('reading_context') != reading_context:
            raise ValueError('This snapshot belongs to another reading context. Use its --restart action '
                             'with --fresh-context to read the current complete material again.')
        _restore_runtime(snapshot['runtime'])
        _check_reused_bodies(snapshot, ledger)
    coverage = snapshot_coverage(folder, snapshot)
    total = coverage['total_bytes']
    read_body = _read_once(folder, lambda digest: c.object_read(folder, digest))
    selection = section if section is not None else (previous or {}).get('section')
    sections = _sections(folder, snapshot, read_body) if navigation or selection is not None else []
    navigation_rows = _navigation(snapshot, coverage, sections, index_source) if navigation else None
    selected = _section_scope(sections, selection) if selection is not None else None
    if previous is not None and previous.get('index'):
        raise ValueError('an index has no delivered source page; use its actions.next or --all action')
    if navigation:
        start = limit = (0, 0)
    elif replay:
        start = _position_value(snapshot, previous['from'])
        limit = _position_value(snapshot, previous.get('replay_until', previous['to']))
    elif previous is not None and _position_value(snapshot, previous.get('replay_until', previous['to'])) > _position_value(snapshot, previous['to']):
        start = _position_value(snapshot, previous['to'])
        limit = _position_value(snapshot, previous['replay_until'])
    elif selected is not None:
        start = _position_value(snapshot, selected['from'] if previous is None else previous['to'])
        limit = _position_value(snapshot, selected['to'])
        if start >= limit:
            raise ValueError('selected section is complete; use its actions.next or --all action for the remaining required scope')
    else:
        start, limit = _pending_span(snapshot, coverage)
    index, offset = start
    budget, end = page_bytes, start
    ranges, body = [], []
    pending = {'snapshot': sid, 'from': _position_data(start), 'to': _position_data(start),
               'ranges': [], 'page_bytes': page_bytes}
    if selected is not None:
        pending['section'] = selection
    if navigation:
        pending['index'] = True
    if replay or (previous is not None and _position_value(snapshot, previous.get('replay_until', previous['to'])) > _position_value(snapshot, previous['to'])):
        pending['replay_until'] = _position_data(limit)
    pending_id = c.content_id(pending)
    _publish_page(folder / 'pages' / (pending_id + '.json'), pending)
    _remember_page(folder, sid, pending_id)
    while index < len(snapshot['bodies']) and budget and end < limit:
        meta = snapshot['bodies'][index]
        raw = read_body(meta['sha256'])
        if len(raw) != meta['size']:
            raise ValueError('reading body size differs from its snapshot')
        stop = min(len(raw), offset + budget, limit[1] if index == limit[0] else len(raw))
        while stop > offset and stop < len(raw) and raw[stop] & 0xC0 == 0x80:
            stop -= 1
        if stop == offset and offset < len(raw):
            break
        segment = raw[offset:stop]
        header = {**meta, 'snapshot': sid, 'start': offset, 'end': stop, 'total': len(raw)}
        ranges.append(header)
        body.append({'metadata': header, 'text': segment.decode('utf-8')})
        budget -= len(segment)
        end = _position_value(snapshot, {'body': index, 'offset': stop})
        index, offset = end
    page = {**pending, 'to': _position_data(end), 'ranges': ranges}
    page_id = c.content_id(page)
    metadata = {key: snapshot['manifest'][key] for key in ('route', 'operation', 'execution', 'scope', 'source_kind', 'features', 'model')}
    if snapshot['manifest'].get('authoring_scope') is not None:
        metadata['authoring_scope'] = snapshot['manifest']['authoring_scope']
    # Only knowledge retained before this response creates a context dependency;
    # newly emitted source text is available in this response itself.
    result = {'ok': True, 'snapshot': sid, 'cursor': sid + ':' + page_id,
              'mode': 'index' if navigation else 'section' if selected is not None else 'all',
              'body': body, 'delivered': ranges, 'metadata': metadata,
              'section': ({key: selected[key] for key in ('selector', 'document_id', 'section_id', 'heading') if key in selected}
                          if selected is not None else None),
              'reading': None, 'context_reuse': None,
              'reading_context': reading_context, 'page_sizing': page_sizing,
              'reuse_selection': {'automatic_readings': snapshot.get('automatic_readings', 0),
                  'selected_readings': len(snapshot['context_keys']),
                  'reason': ('Complete readings explicitly associated with this uninterrupted context; '
                             'only unchanged current required section bodies are reused.' if reading_context else
                             'Only explicitly selected --known-reading values; no saved context is inferred.')},
              'same_context_required': bool(snapshot['context_keys'] or coverage['delivered_bytes'])}
    # Navigation never contributes delivered bytes. Actual text is flushed
    # before its page receipt can contribute to whole-source coverage.
    _begin_output(stream, body, metadata)
    try:
        _publish_page(folder / 'pages' / (page_id + '.json'), page)
        _remember_page(folder, sid, page_id)
        coverage = snapshot_coverage(folder, snapshot)
        reused_bytes = sum(item['body']['size'] for item in snapshot['reused_bodies'])
        result['remaining_bytes'] = coverage['remaining_bytes']
        result['progress'] = {key: coverage[key] for key in ('total_bytes', 'delivered_bytes', 'remaining_bytes')}
        result['progress'].update(page_from=_position_data(start), page_to=_position_data(end),
            required_bytes=total + reused_bytes, reused_bytes=reused_bytes,
            fresh_context_bytes=total + reused_bytes, same_context_new_bytes=total,
            required_bodies=len(snapshot['required_bodies']), reused_bodies=len(snapshot['reused_bodies']),
            section_remaining_bytes=_span_size(snapshot, end, _position_value(snapshot, selected['to'])) if selected is not None else None,
            replay_remaining_bytes=_span_size(snapshot, end, _position_value(snapshot, pending['replay_until'])) if 'replay_until' in pending else 0)
        result['actions'] = _reading_actions(result, ledger=ledger, studio=studio, page_bytes=page_bytes,
                                            acquired=(folder, snapshot, page), coverage=coverage, sections=sections)
        result['selection_summary'] = _selection_summary(snapshot)
        if navigation:
            result['index'], result['selection_reasons'] = navigation_rows
            result['index_source'] = index_source
            result['source_states'] = dict(INDEX_SOURCE_STATES)
            result['section_selection'] = {
                'argv': result['actions']['index']['argv'], 'append': ['--section', 'SELECTOR'],
                'reason': 'Append --section and an exact source or section selector from this index; only source bodies count toward delivery.'}
            result['source_navigation'] = {
                'action_ref': '#/actions/index', 'append': ['--index-source', 'SELECTOR'],
                'reason': 'Append --index-source and a source selector to actions.index.argv to inspect its declared sections; this delivers no body and issues no reading.'}
        if (not navigation and not coverage['remaining_bytes']
                and (selected is None or end == _position_value(snapshot, selected['to']))
                and not result['progress']['replay_remaining_bytes']):
            current, acquired = capture(snapshot['manifest']['route'], snapshot['manifest']['features'], root=root,
                                 dialect=bound_dialect(snapshot['manifest']), operation=snapshot['manifest']['operation'],
                                 execution=snapshot['manifest']['execution'],
                                 scope=snapshot['manifest']['scope'], source_kind=snapshot['manifest']['source_kind'],
                                 authoring_scope=snapshot['manifest'].get('authoring_scope'),
                                 model=(snapshot['manifest']['model'] or {}).get('id') if snapshot['model_file'] is None else None,
                                 model_file=Path(snapshot['model_file']) if snapshot['model_file'] is not None else None,
                                 service=(snapshot['manifest']['model'] or {}).get('service'))
            # The immutable snapshot retains the author's selected presentation
            # order through issuance. A new read can reuse completed unchanged
            # section bodies after an author reorders them.
            if current != snapshot['manifest'] or not _current_bodies(acquired, snapshot['required_bodies']):
                raise ReadingSourcesChanged(source_changes(snapshot['manifest'], current),
                    'sources changed during reading; start a new read',
                    actions={'restart': result['actions']['restart']})
            _check_reused_bodies(snapshot, ledger)
            result['issued'] = _issue(current, ledger, bodies=snapshot['bodies'], reused=snapshot['reused_bodies'],
                                      known_readings=snapshot['known_readings'], snapshot=sid)
            issued = result['issued']
            result['reading'] = {'key': issued['reading_key'], 'record': None}
            if publish_record:
                path = write_draft(issued, ledger, studio=studio, snapshot=sid)
                location = (path.relative_to(studio).as_posix()
                            if studio is not None and path.is_relative_to(studio) else str(path))
                result['reading']['record'] = location
                result['reading']['record_absolute'] = str(path.absolute())
            result['context_reuse'] = _context_reuse(result, snapshot=snapshot, ledger=ledger,
                                                       studio=studio, page_bytes=page_bytes)
            if snapshot.get('bind_choices'):
                import production_inputs
                result['choices_binding'] = production_inputs.bind_reading(
                    authoring_studio, snapshot['choices'], issued,
                    expected_choices_sha256=snapshot['choices_sha256'], ledger=ledger, source_root=root)
    except (ValueError, OSError) as exc:
        _failed_output(stream, exc)
        _record_delivery(result, snapshot, body,
                         new_snapshot=cursor is None and snapshot_id is None, failed=True)
        raise
    _finish_output(stream, result)
    _record_delivery(result, snapshot, body, new_snapshot=cursor is None and snapshot_id is None)
    if reading_context is not None and result.get('issued') is not None:
        _remember_context(ledger, reading_context, root,
                          [*snapshot['context_keys'], result['issued']['reading_key']])
    return result


def draft_record(issued: dict) -> dict:
    """Return the complete machine-owned delivery record from its issued scope."""
    row = issued['row']
    return {**{field: row[field] for field in sorted(manifest_fields(row))}, 'reading_key': issued['reading_key']}


def write_draft(issued: dict, ledger: Path, *, studio: Path | None = None,
                snapshot: str | None = None) -> Path:
    """Publish the derived delivery record beside its issuance ledger."""
    row = issued['row']
    path = ledger.parent / 'readings' / (row['route'] + '-' + row['key_sha256'][:16] + '.json')
    raw = (json.dumps(draft_record(issued), ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    import production_authoring_state
    task_id = (c.load(_snapshot_dir(ledger, snapshot) / 'snapshot.json').get('task_id')
               if snapshot is not None else None)
    production_authoring_state.remember_reading_record(studio or _studio(ledger.parent), ledger, path,
                                                       snapshot=snapshot, task_id=task_id)
    try:
        c.atomic(path, raw)
    except FileExistsError:
        if c.read(path) != raw:
            raise ValueError('saved delivery record differs from its issuance')
    return path


def _selected_model(model: str) -> tuple[str, dict]:
    """Resolve the selected model or return an actionable catalog/family choice."""
    from catalog_retrieval.runtime import load_pack_catalog
    from generation_references import resolve_model_record
    try:
        return resolve_model_record(model)
    except ValueError as exc:
        catalog = load_pack_catalog()
        models = sorted({str(entry.record['id']) for entry in catalog.entries
                         if entry.kind == 'model' and entry.record.get('id')})
        resource = catalog.resources.get('prompt-dialects')
        families = sorted(row['id'] for row in c.load(Path(resource.path))['dialects']) if resource else []
        raise ValueError(f"{exc}; model ids: {', '.join(models) or 'none'}; a prompt-only read can name "
                         f"the prompt family instead with --dialect ID: {', '.join(families) or 'none'}; "
                         'for an acquired model definition use --model-file FILE. For an unlisted host tool, '
                         'select execution external and target.kind external in the owning choices, then use '
                         'their returned reading action. See references/runtime/production-external-inputs.md'
                         '#exact-target-and-provider-schema; do not invent a catalog ID or undisclosed backend.') from None


def add_read_arguments(parser: argparse.ArgumentParser) -> None:
    parser.epilog = ('Index source states: ' + ' '.join(name + ': ' + meaning for name, meaning in INDEX_SOURCE_STATES.items())
                     + ' An index issues no reading; completion is a non-null reading record.')
    parser.add_argument('route', nargs='?', help='Route to index; omit for a saved snapshot or page action')
    parser.add_argument('--feature', action='append', default=[], help='Feature to include when beginning a route')
    parser.add_argument('--root', type=Path, help='Studio root for the reading ledger')
    parser.add_argument('--choices', help='Studio-relative input choices; derive the current stage, route, execution, features and target')
    parser.add_argument('--bind-choices', action='store_true',
        help='With --choices, bind the issued key to that exact unchanged draft after complete delivery; '
             'generated authoring actions select this automatically. Changed authored content is never overwritten.')
    parser.add_argument('--view', choices=['json', 'text'], default='json',
        help='json returns the complete response (default); text displays every original body with section-local byte ranges '
             'and short continuation controls, retaining the complete JSON in a new response file.')
    parser.add_argument('--response-dir', type=Path,
        help='Directory for new response files with --view text; defaults to reading-responses beside the reading ledger. '
             'Each read or replay uses a new file. Source selection and reading requirements are unchanged.')
    parser.add_argument('--operation', choices=execution_routes.OPERATIONS,
                        help='Current operation; defaults to the route owner')
    parser.add_argument('--execution', choices=execution_routes.EXECUTIONS,
                        help='Execution kind selected by the task; required for a new reading')
    parser.add_argument('--scope', choices=execution_routes.CURATION_SCOPES,
                        help='Destination for adopt or withdraw: delivery-only, Studio slot, sheet or catalog; independent of source ownership')
    parser.add_argument('--source-kind', choices=execution_routes.SOURCE_KINDS,
                        help='Retained artifact owner for adopt or withdraw: Production candidate or imported iteration')
    parser.add_argument('--service', help='Selected offering service; with --model, omit to compare all offerings')
    family = parser.add_mutually_exclusive_group()
    family.add_argument('--model', help="Deliver the selected model guidance and its complete applicable writing guide")
    family.add_argument('--model-file', type=Path, help='Acquired model definition, relative to the Studio or absolute')
    family.add_argument('--dialect', metavar='ID',
                        help='Read only the writing guide sections for this prompt family, without a model record')
    add_context_arguments(parser)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--continue', dest='cursor',
                       help='Continue with the complete emitted action and its current context; do not append initial route, feature or choices selectors. Conflicts return recovery actions.')
    group.add_argument('--replay', dest='replay', metavar='CURSOR',
                       help='Read the selected snapshot page again using the emitted action')
    group.add_argument('--restart', metavar='CURSOR',
                       help='Index current sources for a fresh context using saved selections, with no known readings')
    group.add_argument('--snapshot', dest='snapshot_id', metavar='ID',
                       help='Open the saved source index, or deliver its selected --section or --all scope')
    delivery = parser.add_mutually_exclusive_group()
    delivery.add_argument('--all', action='store_true',
                          help='Explicitly deliver all still-required source bytes in bounded pages; indexes issue no reading')
    delivery.add_argument('--section', metavar='SELECTOR',
                          help='With --snapshot, deliver the exact source or section selector from its index; complete coverage is still required')
    delivery.add_argument('--index-source', metavar='SELECTOR',
                          help='With --snapshot, expand one source section index without delivery; '
                               'selection_reason_ids resolve in selection_reasons; progress compares fresh-context and reused bytes')
    parser.add_argument('--known-reading', action='append', default=[], metavar='KEY',
                        help='Complete reading still known in this context; repeat to reuse unchanged selected sections '
                             'after unrelated content or section order changes, and deliver missing complete bodies; omit in a fresh context')
    parser.add_argument('--reading-ledger', type=Path,
                        help='Reading ledger for the selected Studio or explicit continuation context')
    _add_runtime_arguments(parser)


def _reading_actions(result: dict, *, ledger: Path, studio: Path | None, page_bytes: int,
                     acquired: tuple | None = None, coverage: dict | None = None,
                     sections: list[dict] | None = None) -> dict:
    """Build executable next actions from the delivered snapshot's own context."""
    folder, snapshot, page = acquired or _cursor(ledger, result['cursor'])
    coverage = coverage if coverage is not None else snapshot_coverage(folder, snapshot)
    sections = sections if sections is not None else (_sections(folder, snapshot) if 'section' in page else [])
    base = python_argv(ROOT / 'scripts' / 'execution_routes.py', 'read',
                       '--reading-ledger', str(ledger.absolute()), '--page-bytes', str(page_bytes))
    if studio is not None:
        base.extend(('--root', str(studio.absolute())))
    # The snapshot owns its exact runtime. A continuation restores that value
    # before acquiring any resources; repeating every runtime selector in six
    # commands merely makes navigation grow with the installation's paths.

    def action(*arguments: str, reason: str) -> dict:
        argv = [*base, *arguments]
        return {'argv': argv, 'command': 'read', 'reason': reason}

    sid = c.content_id(snapshot)
    actions = {'continue': None, 'next': None, 'replay': None}
    if not page.get('index'):
        position = _position_value(snapshot, page['to'])
        remaining = _span_size(snapshot, position, _position_value(snapshot, page.get('replay_until', page['to'])))
        if not remaining:
            remaining = (_span_size(snapshot, position, _position_value(snapshot,
                         _section_scope(sections, page['section'])['to']))
                         if 'section' in page else coverage['remaining_bytes'])
        if remaining:
            actions['continue'] = action('--continue', result['cursor'],
                reason=f'Read the remaining {remaining} bytes of this selected delivery in the same live model context.')
        actions['replay'] = action('--replay', result['cursor'],
            reason='Replay this page with smaller --page-bytes after tool-output truncation; '
                   'after model-context compaction, use actions.restart.')
    if coverage['missing'] and actions['continue'] is None:
        actions['next'] = action('--snapshot', sid, '--all',
            reason='Read the complete remaining required scope in bounded pages in the same live model context; '
                   'individual section selection is optional through actions.index.')
    actions['index'] = action('--snapshot', sid,
        reason='Inspect required sources, selected sections, shared selection reasons and exact remaining coverage without issuing a reading.')
    actions['all'] = action('--snapshot', sid, '--all',
        reason='Deliver all remaining required source bytes in bounded pages, then check current sources and issue the reading.')
    actions['restart'] = action('--restart', result['cursor'],
        reason='Index all current required knowledge after compaction, a summary handoff or a new agent; '
               'keep choices, images and saved progress.')
    if snapshot.get('reading_context') is not None:
        for name, value in actions.items():
            if value is not None:
                value['argv'].extend(['--fresh-context'] if name == 'restart' else
                                     ['--reading-context', snapshot['reading_context']])
    return actions


def _context_reuse(result: dict, *, snapshot: dict, ledger: Path,
                   studio: Path | None, page_bytes: int) -> dict:
    """Offer complete read invocations without inferring a later context's knowledge."""
    keys = list(dict.fromkeys([*snapshot['context_keys'], result['issued']['reading_key']]))
    arguments = (['--reading-context', snapshot['reading_context']] if snapshot.get('reading_context') else
                 [word for key in keys for word in ('--known-reading', key)])
    manifest = snapshot['manifest']
    base = python_argv(ROOT / 'scripts/execution_routes.py', 'read', manifest['route'],
                       '--reading-ledger', str(ledger.absolute()), '--page-bytes', str(page_bytes),
                       '--execution', manifest['execution'])
    if studio is not None:
        base.extend(('--root', str(studio.absolute())))
    for feature in manifest['features']:
        base.extend(('--feature', feature))
    if snapshot['model_file'] is not None:
        base.extend(('--model-file', snapshot['model_file']))
    elif manifest['model'] is not None:
        base.extend(('--model', manifest['model']['id']))
    elif bound_dialect(manifest) is not None:
        base.extend(('--dialect', bound_dialect(manifest)))
    if manifest['model'] is not None and manifest['model']['service'] is not None:
        base.extend(('--service', manifest['model']['service']))
    runtime = _runtime_context(snapshot['runtime'])
    if runtime is not None:
        base.extend(runtime.command_arguments())
    operations, curations = {}, []
    curation = manifest['operation'] in {'adopt', 'withdraw'}
    authoring_scope = manifest.get('authoring_scope')
    # A later draft owns the next operation's actual scope. Offer current
    # inspection plus reusable knowledge keys, rather than manufacture one
    # command for every possible next operation and destination.
    for operation in (manifest['operation'],):
        if authoring_scope is not None:
            if operation != manifest['operation'] or snapshot.get('choices') is None:
                continue
            argv = python_argv(ROOT / 'scripts/execution_routes.py', 'read',
                '--reading-ledger', str(ledger.absolute()), '--page-bytes', str(page_bytes),
                '--choices', snapshot['choices'])
            if snapshot.get('bind_choices'):
                argv.append('--bind-choices')
            if studio is not None:
                argv.extend(('--root', str(studio.absolute())))
            if runtime is not None:
                argv.extend(runtime.command_arguments())
            argv.extend(arguments)
            operations[operation] = {'argv': argv, 'command': 'read',
                'reason': 'Read the current editable stage, reusing only complete material still known in this context.'}
            continue
        if operation in {'adopt', 'withdraw'}:
            if not curation:
                continue
            for scope, source_kind in [(manifest['scope'], manifest['source_kind'])]:
                if source_kind != manifest['source_kind']:
                    continue
                argv = [*base, '--operation', operation, '--scope', scope, '--source-kind', source_kind, *arguments]
                action = {'argv': argv, 'command': 'read',
                    'reason': 'Read the current ' + scope + ' ' + operation + ' contract for ' + source_kind
                              + ', adding only missing or changed sections still needed in this context.'}
                if operation == manifest['operation'] and scope == manifest['scope']:
                    operations[operation] = action
                else:
                    curations.append({'operation': operation, 'scope': scope, 'source_kind': source_kind, 'action': action})
            continue
        if curation:
            continue
        argv = [*base, '--operation', operation, *arguments]
        operations[operation] = {'argv': argv, 'command': 'read',
            'reason': 'Read the current ' + operation + ' contract, reusing only complete material still known in this context.'}
    return {'same_context_required': True, 'known_reading_keys': keys,
            'arguments': arguments, 'operations': operations, 'curation_scopes': curations,
            **({'authoring_stage': authoring_scope['stage'],
                'authoring_guidance': 'Select the next stage with stage-inputs, follow its reading action and append '
                    'these reuse arguments only while the earlier complete material remains in this context.'}
               if authoring_scope is not None else {}),
            'curation_guidance': "Use the actual next draft's reading_action and append these reuse arguments; "
                'its operation, destination and source kind determine the required sections.',
            'fresh_context': {'action_ref': '#/actions/restart'}}


def _choice_selection(args: argparse.Namespace) -> tuple[dict | None, str | None]:
    """Acquire one editable selection for a public reading invocation."""
    if args.choices is None:
        return None, None
    if args.root is None:
        raise ValueError('--choices requires --root STUDIO to acquire the selected editable input')
    from production_reading_scope import from_choices, operation
    selected, task, choices = from_choices(args.root, args.choices, include_choices=True)
    if args.bind_choices:
        from production_inputs import reading_choice_identity
        args.choices_sha256 = reading_choice_identity(choices)
    for field in ('route', 'execution'):
        supplied = getattr(args, field)
        if supplied is not None and supplied != task[field]:
            raise ValueError(field + ' differs from --choices; follow its current reading action')
        setattr(args, field, task[field])
    args.operation = args.operation or operation(selected['stage'], task['execution'])
    args.feature = list(dict.fromkeys([*task.get('features', []), *args.feature]))
    target = choices.get('target') or {}
    selectors = {}
    if target.get('kind') in {'catalog', 'acquired'}:
        field = 'model' if target['kind'] == 'catalog' else 'model_file'
        if target.get(field):
            selectors[field] = Path(target[field]) if field == 'model_file' else target[field]
        if target.get('service'):
            selectors['service'] = target['service']
    elif target.get('kind') == 'external' and (target.get('model') or {}).get('prompt_dialect'):
        selectors['dialect'] = target['model']['prompt_dialect']
    for field in ('model', 'model_file', 'dialect', 'service'):
        supplied = getattr(args, field)
        expected = selectors.get(field)
        same = supplied == expected
        if field == 'model_file' and supplied is not None and expected is not None:
            supplied_path = supplied if supplied.is_absolute() else args.root / supplied
            expected_path = expected if expected.is_absolute() else args.root / expected
            same = supplied_path.resolve() == expected_path.resolve()
        if supplied is not None and not same:
            raise ValueError('--' + field.replace('_', '-') + ' differs from --choices; edit its target or follow its current reading action')
        setattr(args, field, expected)
    return selected, args.choices


def _read_command(args: argparse.Namespace, parser: argparse.ArgumentParser, *, stream=None) -> dict:
    """Start with navigation unless the caller selects exact source delivery."""
    options = resolve_context_options(args)
    if options['fresh_context'] and args.known_reading:
        raise ValueError('--fresh-context cannot assert --known-reading; read current required bodies again.')
    if options['fresh_context'] and (args.cursor is not None or args.replay is not None or args.snapshot_id is not None):
        raise _invocation_conflict(args, 'Use --restart CURSOR --fresh-context; continuing saved pages cannot supply knowledge to a new context.')
    continuation = args.cursor is not None or args.replay is not None or args.restart is not None or args.snapshot_id is not None
    if continuation and (args.route is not None or args.feature or args.model is not None or args.model_file is not None or args.dialect is not None
                         or args.operation is not None or args.execution is not None or args.scope is not None or args.source_kind is not None
                         or args.service is not None or args.known_reading or args.choices is not None or args.bind_choices):
        raise _invocation_conflict(args, 'a cursor or snapshot fixes its route, operation, execution, destination, source kind, features, model scope and known readings; execute its complete reading action')
    if args.section is not None and args.snapshot_id is None:
        raise ValueError('--section requires --snapshot ID from the source index; begin with read ROUTE and its actual task selections')
    if args.index_source is not None and args.snapshot_id is None:
        raise ValueError('--index-source requires --snapshot ID from the source index; it expands sections and delivers no body')
    if args.all and (args.cursor is not None or args.replay is not None):
        raise ValueError('a cursor fixes its delivery selection; use --snapshot ID --all to select all remaining bytes')
    if args.bind_choices and args.choices is None:
        raise ValueError('--bind-choices requires --choices FILE; follow the current draft reading action.')
    authoring_scope, choices_path = _choice_selection(args) if not continuation else (None, None)
    if not continuation and args.execution is None:
        raise ValueError('a new reading requires --execution authored, external or dispatcher from the task')
    # A cursor or snapshot is a complete retained selection, including the
    # pack runtime. Avoid consulting a different cwd's defaults before that
    # selection is restored. A new read still resolves its actual selectors.
    runtime = None if continuation else _configure_runtime(args, parser)
    ledger = ledger_candidates(studio=args.root, ledger=args.reading_ledger)[0]
    studio = args.root.absolute() if args.root is not None else (_studio(Path.cwd()) or _studio(ledger.parent))
    dialect = args.dialect
    if not continuation and args.route is None:
        raise ValueError('read requires a route, saved snapshot or continuation cursor')
    page_bytes = DEFAULT_PAGE_BYTES if args.page_bytes is None else args.page_bytes
    cursor = args.cursor if args.cursor is not None else args.replay
    model_file = args.model_file
    if model_file is not None and not model_file.is_absolute():
        model_file = (studio or Path.cwd()) / model_file
    if args.restart is not None:
        _, snapshot, _ = _cursor(ledger, args.restart)
        if snapshot['root'] != str(ROOT.absolute()):
            raise ValueError('reading cursor belongs to a different skill root')
        _restore_runtime(snapshot['runtime'])
        manifest = snapshot['manifest']
        if snapshot.get('bind_choices'):
            args.root, args.choices, args.bind_choices = studio, snapshot['choices'], True
            authoring_scope, choices_path = _choice_selection(args)
            model_file = args.model_file
            if model_file is not None and not model_file.is_absolute():
                model_file = studio / model_file
            return read_page(route=args.route, features=args.feature, root=ROOT,
                stream=stream,
                operation=args.operation, execution=args.execution, authoring_scope=authoring_scope,
                choices_path=choices_path, bind_choices=True, choices_sha256=args.choices_sha256,
                dialect=args.dialect, model_file=model_file, model=args.model, service=args.service,
                page_bytes=page_bytes, reading_context=options['reading_context'],
                host_page_bytes=options['host_page_bytes'], ledger=ledger, studio=studio,
                runtime=snapshot['runtime'], publish_record=True, navigation=not args.all)
        result = read_page(route=manifest['route'], features=manifest['features'], root=ROOT,
            stream=stream,
            operation=manifest['operation'], execution=manifest['execution'],
            scope=manifest['scope'], source_kind=manifest['source_kind'],
            authoring_scope=manifest.get('authoring_scope'), choices_path=snapshot.get('choices'),
            dialect=bound_dialect(manifest), model_file=Path(snapshot['model_file']) if snapshot['model_file'] else None,
            model=(manifest['model'] or {}).get('id') if snapshot['model_file'] is None else None,
            service=(manifest['model'] or {}).get('service'), page_bytes=page_bytes,
            reading_context=options['reading_context'], host_page_bytes=options['host_page_bytes'],
            ledger=ledger, studio=studio, runtime=snapshot['runtime'], publish_record=True,
            navigation=not args.all)
    else:
        result = read_page(route=args.route, features=args.feature, cursor=cursor, root=ROOT,
                           stream=stream,
                           replay=args.replay is not None, page_bytes=page_bytes,
                           ledger=ledger, studio=studio, runtime=runtime, dialect=dialect,
                           operation=args.operation, execution=args.execution, model=args.model, service=args.service,
                           scope=args.scope, source_kind=args.source_kind,
                           authoring_scope=authoring_scope, choices_path=choices_path,
                           bind_choices=args.bind_choices, choices_sha256=getattr(args, 'choices_sha256', None),
                           model_file=model_file, known_reading_keys=args.known_reading, publish_record=True,
                           reading_context=options['reading_context'], host_page_bytes=options['host_page_bytes'],
                           snapshot_id=args.snapshot_id, section=args.section, index_source=args.index_source,
                           navigation=cursor is None and not args.all and args.section is None)
    return result


def read_command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> dict:
    """Keep source delivery and its retained response within one public read."""
    if getattr(args, 'view', 'json') == 'json':
        if getattr(args, 'response_dir', None) is not None:
            raise ValueError('--response-dir requires --view text; JSON output can also be captured directly.')
        return _read_command(args, parser)
    directory = (getattr(args, 'response_dir', None)
        or ledger_candidates(studio=args.root, ledger=args.reading_ledger)[0].parent / 'reading-responses')
    output = TextReadingOutput(directory, sys.stdout)
    try:
        return _read_command(args, parser, stream=output)
    except (ValueError, OSError) as exc:
        if not getattr(exc, 'reading_result_written', False):
            try:
                if not output.begun:
                    _begin_output(output, [], {})
                _failed_output(output, exc)
            except OSError:
                pass
            exc.reading_result_written = True
        raise
    finally:
        output.close()


def main() -> int:
    parser = _operation_context.ArgumentParser(description=__doc__)
    parser.add_argument('record', type=Path)
    parser.add_argument('--root', type=Path)
    args = parser.parse_args()
    try:
        row = require_route_reading(c.load(args.record), studio=args.root, package_root=args.record.parent)
        print(json.dumps({'ok': True, 'route': row['route'], 'operation': row['operation'],
                          'execution': row['execution'], 'scope': row['scope'], 'source_kind': row['source_kind'],
                          'evidence': 'complete selected section-body delivery'}, indent=2))
        return 0
    except (ValueError, OSError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc),
                         **(exc.as_dict() if isinstance(exc, ReadingSourcesChanged) else {})})); return 1


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(_operation_context.run_cli(main))
