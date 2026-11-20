#!/usr/bin/env python3
"""Own acquired authoring material and one editable actual candidate.

Compose starts new content while retaining comparison material. Amend starts
from the acquired baseline. Exact edits update that content; changes are derived
from the values, and delivery reads the same candidate. These structural checks
establish content relationships, not creative quality or semantic authority.
"""
from __future__ import annotations

import base64
import binascii
import copy
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Sequence

import execution_contract as c
import protocol_contract


SCHEMA = Path(__file__).resolve().parents[1] / 'schemas/authoring/authoring-work.schema.json'
_UNSET = object()


class AuthoringWorkError(ValueError):
    """A current work cannot resolve under its structural contract."""

    def __init__(self, report: dict):
        self.report = report
        super().__init__('; '.join(f"{row['path']}: {row['message']}" for row in report['errors']))


def _json(value: Any, path: str = '$') -> None:
    if isinstance(value, str):
        value.encode('utf-8')
        return
    if value is None or isinstance(value, (bool, int)):
        return
    if isinstance(value, float) and math.isfinite(value):
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _json(item, f'{path}/{index}')
        return
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        for key, item in value.items():
            key.encode('utf-8')
            _json(item, path + '/' + _escape(key))
        return
    raise ValueError(f'{path}: expected a finite JSON value with string object keys')


def digest(value: Any) -> str:
    """Hash an actual JSON value using its canonical UTF-8 representation."""
    _json(value)
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False,
                     separators=(',', ':'), allow_nan=False).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def _text_digest(value: str | None) -> str | None:
    return hashlib.sha256(value.encode('utf-8')).hexdigest() if value is not None else None


def acquire_source(data: bytes | str, *, format: str = 'text', origin: dict | None = None) -> dict:
    """Acquire exact bytes and their provenance without applying the source."""
    if not isinstance(data, (bytes, str)):
        raise ValueError('source data must be bytes or UTF-8 text')
    if format not in ('text', 'json', 'binary'):
        raise ValueError('source format must be text, json or binary')
    if origin is not None and not isinstance(origin, dict):
        raise ValueError('source origin must be a JSON object')
    _json(origin)
    raw = data.encode('utf-8') if isinstance(data, str) else data
    text = base64.b64encode(raw).decode('ascii') if format == 'binary' else raw.decode('utf-8')
    if format == 'json':
        _json(c.decode(raw))
    return {'format': format, 'encoding': 'base64' if format == 'binary' else 'utf-8',
            'data': text, 'sha256': hashlib.sha256(raw).hexdigest(),
            'origin': copy.deepcopy(origin or {})}


def source_bytes(source: dict) -> bytes:
    """Return the acquired bytes after checking their format and digest."""
    if not isinstance(source, dict) or set(source) != {'format', 'encoding', 'data', 'sha256', 'origin'}:
        raise ValueError('source requires format, encoding, data, sha256 and origin')
    kind = source['format']
    if kind not in ('text', 'json', 'binary') or not isinstance(source['data'], str):
        raise ValueError('source requires a supported format and string data')
    expected = 'base64' if kind == 'binary' else 'utf-8'
    if source['encoding'] != expected:
        raise ValueError(f'{kind} source requires {expected} encoding')
    if not isinstance(source['origin'], dict):
        raise ValueError('source origin must be a JSON object')
    _json(source['origin'])
    try:
        raw = (base64.b64decode(source['data'], validate=True) if kind == 'binary'
               else source['data'].encode('utf-8'))
    except (ValueError, binascii.Error) as error:
        raise ValueError('source data does not match its encoding') from error
    if hashlib.sha256(raw).hexdigest() != source['sha256']:
        raise ValueError('source bytes differ from the acquired SHA-256')
    if kind == 'json':
        _json(c.decode(raw))
    return raw


def _escape(value: str) -> str:
    return value.replace('~', '~0').replace('/', '~1')


def _tokens(pointer: str) -> list[str]:
    if not isinstance(pointer, str) or (pointer and not pointer.startswith('/')):
        raise ValueError('JSON Pointer must be empty or start with /')
    if not pointer:
        return []
    result = []
    for token in pointer[1:].split('/'):
        index = 0
        while index < len(token):
            if token[index] == '~':
                if index + 1 == len(token) or token[index + 1] not in '01':
                    raise ValueError('JSON Pointer uses only ~0 and ~1 escapes')
                index += 1
            index += 1
        result.append(token.replace('~1', '/').replace('~0', '~'))
    return result


def _index(token: str, length: int, *, append: bool = False) -> int:
    if append and token == '-':
        return length
    if not token or any(char not in '0123456789' for char in token) or (len(token) > 1 and token[0] == '0'):
        raise ValueError('array pointer requires a nonnegative decimal index')
    value = int(token)
    if value >= length + int(append):
        raise ValueError('array pointer index is outside the selected array')
    return value


def _select(value: Any, pointer: str) -> Any:
    current = value
    for token in _tokens(pointer):
        if isinstance(current, dict):
            if token not in current:
                raise ValueError(f'JSON Pointer member is absent: {token!r}')
            current = current[token]
        elif isinstance(current, list):
            current = current[_index(token, len(current))]
        else:
            raise ValueError('JSON Pointer traverses a scalar value')
    return current


def source_value(source: dict, pointer: str = '') -> Any:
    """Resolve a selection from acquired JSON, root text or root binary."""
    raw = source_bytes(source)
    if source['format'] == 'json':
        return copy.deepcopy(_select(c.decode(raw), pointer))
    if pointer != '':
        raise ValueError('text and binary sources use the empty root pointer')
    return copy.deepcopy(source) if source['format'] == 'binary' else raw.decode('utf-8')


def begin_work(*, operation: str, request: str | None = None,
               sources: dict | None = None, applications: dict | None = None,
               subjects: dict | None = None, requirements: list | None = None,
               baseline: dict | None = None, content: dict | None = None,
               focus: str = 'character') -> dict:
    """Acquire a basis and initialize the actual candidate for the operation."""
    if operation == 'amend':
        if baseline is None:
            raise ValueError('amend requires the actual baseline content')
        if content is not None:
            raise ValueError('amend starts from baseline; edit that candidate after beginning work')
        content = baseline
    if request is not None and not isinstance(request, str):
        raise ValueError('request must be exact UTF-8 text or null while drafting')
    basis = {'operation': operation, 'focus': focus,
             'request': request, 'request_sha256': _text_digest(request),
             'sources': sources if sources is not None else {},
             'applications': applications if applications is not None else {},
             'subjects': subjects if subjects is not None else {},
             'requirements': requirements if requirements is not None else [],
             'baseline': baseline, 'baseline_sha256': digest(baseline) if baseline is not None else None}
    result = {'basis': copy.deepcopy(basis),
              'content': copy.deepcopy(content if content is not None else {})}
    _checked(result, complete=False)
    return result


def revise_basis(basis: dict, *, request: Any = _UNSET, sources: Any = _UNSET,
                 applications: Any = _UNSET, subjects: Any = _UNSET,
                 requirements: Any = _UNSET, focus: Any = _UNSET) -> dict:
    """Replace supplied current selections, retaining the acquired baseline."""
    result = copy.deepcopy(basis)
    for key, value in [('sources', sources), ('applications', applications),
                       ('subjects', subjects), ('requirements', requirements), ('focus', focus)]:
        if value is not _UNSET:
            result[key] = copy.deepcopy(value)
    if request is not _UNSET:
        if request is not None and not isinstance(request, str):
            raise ValueError('request must be exact UTF-8 text or null while drafting')
        result.update(request=request, request_sha256=_text_digest(request))
    _checked({'basis': result, 'content': {}}, complete=False)
    return result


def validate_work(work: Any, complete: bool = False, require_subject: bool = False) -> dict:
    """Check acquisition, actual selections and the requested completion scope."""
    errors = []

    def error(path: str, message: str) -> None:
        errors.append({'path': path, 'message': message})

    try:
        _json(work)
        from state_protocol import read_schema
        schema = read_schema(SCHEMA)
        for message in protocol_contract.validate_against_schema(work, schema):
            error('$', message)
    except (ValueError, TypeError, UnicodeError) as problem:
        error('$', str(problem))
    if errors:
        return {'ok': False, 'complete': complete, 'require_subject': require_subject, 'errors': errors}
    basis = work['basis']
    request = basis['request']
    if _text_digest(request) != basis['request_sha256']:
        error('/basis/request_sha256', 'current request differs from its acquired SHA-256')
    if complete and (request is None or not request.strip()):
        error('/basis/request', 'complete work requires the exact current request')
    if complete and not work['content']:
        error('/content', 'complete work requires actual candidate content')
    baseline = basis['baseline']
    if (digest(baseline) if baseline is not None else None) != basis['baseline_sha256']:
        error('/basis/baseline_sha256', 'baseline differs from its acquired JSON SHA-256')
    if basis['operation'] == 'amend' and baseline is None:
        error('/basis/baseline', 'amend requires actual baseline content')
    invalid_sources = set()
    for ident, source in basis['sources'].items():
        try:
            source_bytes(source)
        except (ValueError, TypeError, UnicodeError) as problem:
            invalid_sources.add(ident)
            error('/basis/sources/' + _escape(ident), str(problem))
    values = {}
    for ident, application in basis['applications'].items():
        path = '/basis/applications/' + _escape(ident)
        source_id = application['source']
        if source_id not in basis['sources']:
            error(path + '/source', 'selected source is absent from the acquired catalog')
        elif source_id not in invalid_sources:
            try:
                values[ident] = source_value(basis['sources'][source_id], application['pointer'])
            except (ValueError, TypeError, UnicodeError) as problem:
                error(path + '/pointer', str(problem))
    for ident, definitions in basis['subjects'].items():
        path = '/basis/subjects/' + _escape(ident)
        for definition in definitions:
            if definition not in basis['applications']:
                error(path, f'definition application is absent: {definition}')
            elif definition in values:
                value = values[definition]
                source = basis['sources'][basis['applications'][definition]['source']]
                empty_binary = source['format'] == 'binary' and not source_bytes(source)
                if empty_binary or value is None or value == {} or value == [] or (isinstance(value, str) and not value.strip()):
                    error(path, f'definition application selects empty material: {definition}')
    for ident in basis['requirements']:
        if ident not in basis['applications']:
            error('/basis/requirements', f'requirement application is absent: {ident}')
    if complete and require_subject and basis['focus'] == 'character' and not basis['subjects']:
        error('/basis/subjects', 'character work requires at least one selected subject definition')
    return {'ok': not errors, 'complete': complete, 'require_subject': require_subject, 'errors': errors}


def _checked(work: dict, *, complete: bool, require_subject: bool = False) -> None:
    report = validate_work(work, complete=complete, require_subject=require_subject)
    if not report['ok']:
        raise AuthoringWorkError(report)


def changes(before: Any, after: Any, pointer: str = '') -> list[dict]:
    """Derive actual JSON differences; these operations are a read-only report."""
    if digest(before) == digest(after):
        return []
    if isinstance(before, dict) and isinstance(after, dict):
        result = []
        for key in sorted(before.keys() | after.keys()):
            path = pointer + '/' + _escape(key)
            if key not in before:
                result.append({'operation': 'add', 'pointer': path, 'after': copy.deepcopy(after[key])})
            elif key not in after:
                result.append({'operation': 'remove', 'pointer': path, 'before': copy.deepcopy(before[key])})
            else:
                result.extend(changes(before[key], after[key], path))
        return result
    return [{'operation': 'replace', 'pointer': pointer,
             'before': copy.deepcopy(before), 'after': copy.deepcopy(after)}]


def resolve_work(work: dict, complete: bool = True, require_subject: bool = False) -> dict:
    """Resolve context and delivery from one acquired basis and actual content."""
    _checked(work, complete=complete, require_subject=require_subject)
    basis = work['basis']
    context = copy.deepcopy(basis)
    for ident, application in context['applications'].items():
        application['value'] = source_value(basis['sources'][application['source']], application['pointer'])
    result = {'content': copy.deepcopy(work['content']), 'context': context,
              'changes': changes(basis['baseline'] if basis['operation'] == 'amend' else {}, work['content'])}
    if basis['operation'] == 'compose' and basis['baseline'] is not None:
        result['comparison_changes'] = changes(basis['baseline'], work['content'])
    return result


def _compare_values(values: list[Any], candidates: list[str], pointer: str = '') -> dict:
    """Compare actual JSON values without assigning meaning to their paths."""
    present = [value is not _UNSET for value in values]
    if all(present) and len({digest(value) for value in values}) == 1:
        return {'common': [{'pointer': pointer, 'value': copy.deepcopy(values[0])}],
                'differences': []}
    children = []
    if all(present) and all(isinstance(value, dict) for value in values):
        for key in sorted(set().union(*(value.keys() for value in values))):
            children.append((pointer + '/' + _escape(key),
                             [value.get(key, _UNSET) for value in values]))
    elif all(present) and all(isinstance(value, list) for value in values):
        for index in range(max(map(len, values))):
            children.append((pointer + '/' + str(index),
                             [value[index] if index < len(value) else _UNSET for value in values]))
    if children:
        result = {'common': [], 'differences': []}
        for path, selected in children:
            comparison = _compare_values(selected, candidates, path)
            for kind in result:
                result[kind].extend(comparison[kind])
        return result
    selections = []
    for candidate, value, exists in zip(candidates, values, present):
        selection = {'candidate': candidate, 'present': exists}
        if exists:
            selection['value'] = copy.deepcopy(value)
        selections.append(selection)
    return {'common': [], 'differences': [{'pointer': pointer, 'values': selections}]}


def compare_works(works: Sequence[dict], *, labels: Sequence[str] | None = None) -> dict:
    """Read actual candidates and derive shared selections and differences.

    This is an intermediate working view. It neither completes a candidate nor
    judges the significance of equal or different content. Source applications
    outside subject definitions and requirements retain their actual values;
    their meaning and authority are not inferred from a name or field path.
    """
    if not works:
        raise ValueError('comparison requires at least one actual work')
    if labels is not None and (len(labels) != len(works) or
                              any(not isinstance(label, str) for label in labels)):
        raise ValueError('comparison labels must supply one text label per work')
    candidates = []
    for index, actual in enumerate(works):
        resolved = resolve_work(actual, complete=False)
        context = resolved['context']
        applications = {}
        for ident, application in context['applications'].items():
            source = context['sources'][application['source']]
            applications[ident] = {
                'source': application['source'], 'pointer': application['pointer'],
                'source_sha256': source['sha256'], 'source_format': source['format'],
                'origin': source['origin'], 'value': application['value']}
        retained = set(context['requirements'])
        for assigned in context['subjects'].values():
            retained.update(assigned)
        view = {
            'request': context['request'], 'focus': context['focus'],
            'subjects': {subject: [{'application': ident, **copy.deepcopy(applications[ident])}
                                  for ident in assigned]
                         for subject, assigned in context['subjects'].items()},
            'requirements': [{'application': ident, **copy.deepcopy(applications[ident])}
                             for ident in context['requirements']],
            'content': resolved['content'],
            'other_applications': {ident: application for ident, application in applications.items()
                                   if ident not in retained},
            'baseline': context['baseline'],
        }
        ident = f'candidate-{index + 1}'
        candidates.append({'id': ident, 'label': labels[index] if labels is not None else ident,
                           'work_digest': digest(actual), 'operation': context['operation'],
                           'view': view,
                           'baseline_changes': changes(context['baseline'], resolved['content'])
                           if context['baseline'] is not None else None})
    comparison = _compare_values([candidate['view'] for candidate in candidates],
                                 [candidate['id'] for candidate in candidates])
    return {'artifact_type': 'authoring-work-comparison', 'state': 'intermediate',
            'candidates': candidates, **comparison}


def candidate_value(work: dict, pointer: str = '', *, complete: bool = True,
                    require_subject: bool = False) -> Any:
    """Select an actual resolved candidate value for its delivery owner."""
    resolved = resolve_work(work, complete=complete, require_subject=require_subject)
    return copy.deepcopy(_select(resolved['content'], pointer))


def replace_content(work: dict, content: dict) -> dict:
    """Replace the actual editable candidate without changing acquired context."""
    _checked(work, complete=False)
    result = copy.deepcopy(work)
    result['content'] = copy.deepcopy(content)
    _checked(result, complete=False)
    return result


def edit_value(work: dict, pointer: str, value: Any = _UNSET, *, operation: str = 'replace') -> dict:
    """Apply one exact JSON Pointer edit to the actual candidate."""
    _checked(work, complete=False)
    if operation not in ('add', 'replace', 'remove'):
        raise ValueError('edit operation must be add, replace or remove')
    if (operation == 'remove') != (value is _UNSET):
        raise ValueError('add and replace require a value; remove has no value')
    tokens = _tokens(pointer)
    result = copy.deepcopy(work)
    if not tokens:
        if operation == 'remove':
            raise ValueError('the candidate root must remain a JSON object')
        result['content'] = copy.deepcopy(value)
    else:
        parent_pointer = ''.join('/' + _escape(token) for token in tokens[:-1])
        parent, key = _select(result['content'], parent_pointer), tokens[-1]
        if isinstance(parent, dict):
            if operation != 'add' and key not in parent:
                raise ValueError('edit pointer does not select an existing value')
            if operation == 'remove':
                del parent[key]
            else:
                parent[key] = copy.deepcopy(value)
        elif isinstance(parent, list):
            index = _index(key, len(parent), append=operation == 'add')
            if operation == 'add':
                parent.insert(index, copy.deepcopy(value))
            elif operation == 'remove':
                parent.pop(index)
            else:
                parent[index] = copy.deepcopy(value)
        else:
            raise ValueError('edit pointer parent is a scalar')
    _checked(result, complete=False)
    return result


def replace_text(work: dict, pointer: str, old: str, new: str) -> dict:
    """Replace one unambiguous literal span and preserve every other character."""
    _checked(work, complete=False)
    current = _select(work['content'], pointer)
    if not isinstance(current, str) or not isinstance(old, str) or not isinstance(new, str):
        raise ValueError('literal replacement requires a selected string and text values')
    if not old:
        raise ValueError('literal replacement requires a nonempty existing span')
    start = current.find(old)
    if start < 0 or current.find(old, start + 1) >= 0:
        raise ValueError('literal replacement requires exactly one occurrence of the existing span')
    return edit_value(work, pointer, current[:start] + new + current[start + len(old):])


def _assignment(value: str) -> tuple[str, str]:
    name, separator, body = value.partition('=')
    if not separator or not name.strip():
        raise ValueError('named input must use ID=VALUE')
    return name, body


def _read_source(path: Path) -> dict:
    raw = path.read_bytes()
    if path.suffix.lower() == '.json':
        kind = 'json'
    else:
        try:
            raw.decode('utf-8')
            kind = 'text'
        except UnicodeDecodeError:
            kind = 'binary'
    return acquire_source(raw, format=kind, origin={'path': str(path.absolute())})


def _selection_arguments(parser) -> None:
    parser.add_argument('--request', type=Path, help='Acquire the exact current request from UTF-8 text')
    parser.add_argument('--source', action='append', default=[], metavar='ID=FILE', help='Acquire a source without applying it')
    parser.add_argument('--application', action='append', default=[], metavar='APP=SOURCE#POINTER', help='Select actual acquired material')
    parser.add_argument('--subject', action='append', default=[], metavar='SUBJECT=APP[,APP...]', help='Assign selected definitions to a subject')
    parser.add_argument('--requirement', action='append', metavar='APP', help='Select current requirement applications')
    parser.add_argument('--focus', choices=['character', 'supporting-setting'])


def _selections(args, basis: dict | None = None) -> dict:
    result = {key: copy.deepcopy((basis or {}).get(key, {})) for key in ('sources', 'applications', 'subjects')}
    for field, identifiers in [('applications', getattr(args, 'remove_application', [])),
                                ('subjects', getattr(args, 'remove_subject', []))]:
        for ident in identifiers:
            if ident not in result[field]:
                raise ValueError(f'{field} has no current selection named {ident!r}')
            del result[field][ident]
    for value in args.source:
        ident, path = _assignment(value)
        result['sources'][ident] = _read_source(Path(path))
    for value in args.application:
        ident, selection = _assignment(value)
        source, separator, pointer = selection.partition('#')
        if not separator:
            raise ValueError('application must use APP=SOURCE#POINTER; root selection ends with #')
        result['applications'][ident] = {'source': source, 'pointer': pointer}
    for value in args.subject:
        ident, definitions = _assignment(value)
        result['subjects'][ident] = definitions.split(',')
    if args.request is not None:
        result['request'] = args.request.read_bytes().decode('utf-8')
    if args.requirement is not None:
        result['requirements'] = args.requirement
    if args.focus is not None:
        result['focus'] = args.focus
    return result


def main(argv: Sequence[str] | None = None) -> int:
    import operation_context
    parser = operation_context.ArgumentParser(description=__doc__.split('\n')[0])
    commands = parser.add_subparsers(dest='command', required=True)
    begin = commands.add_parser('begin', help='Acquire context and initialize one actual candidate')
    begin.add_argument('--operation', choices=['compose', 'amend'], required=True)
    _selection_arguments(begin)
    begin.add_argument('--baseline', type=Path, help='Acquire actual previous content for amendment or comparison')
    initial = begin.add_mutually_exclusive_group()
    initial.add_argument('--content', type=Path, help='Acquire new actual candidate JSON for compose')
    initial.add_argument('--prompt', type=Path, help='Import UTF-8 prompt text into new candidate content')
    begin.add_argument('--negative', type=Path, help='Import UTF-8 negative text into new candidate content')
    begin.add_argument('--out', type=Path, required=True)
    context = commands.add_parser('context', help='Update acquired sources and current selections')
    context.add_argument('work', type=Path)
    context.add_argument('--basis-only', action='store_true', help='Edit an explicit basis document whose candidate is owned by a saved adapter')
    _selection_arguments(context)
    context.add_argument('--remove-application', action='append', default=[], metavar='APP', help='Remove a current application, retaining its acquired source')
    context.add_argument('--remove-subject', action='append', default=[], metavar='SUBJECT', help='Remove a current subject assignment')
    edit = commands.add_parser('edit', help='Apply an exact JSON Pointer operation to actual content')
    edit.add_argument('work', type=Path)
    edit.add_argument('--pointer', required=True)
    edit.add_argument('--operation', choices=['add', 'replace', 'remove'], default='replace')
    edit_input = edit.add_mutually_exclusive_group()
    edit_input.add_argument('--value-file', type=Path, help='Read the actual value as JSON')
    edit_input.add_argument('--text-file', type=Path, help='Read the actual value as UTF-8 text')
    replace = commands.add_parser('replace-text', help='Replace one exact literal span in actual content')
    replace.add_argument('work', type=Path)
    replace.add_argument('--pointer', required=True)
    replace.add_argument('--old-file', type=Path, required=True)
    replace.add_argument('--new-file', type=Path, required=True)
    for name, help_text in [('inspect', 'Resolve the current draft, including unfinished work'),
                            ('check', 'Check completed work and its selected character definitions')]:
        sub = commands.add_parser(name, help=help_text)
        sub.add_argument('work', type=Path)
    compare = commands.add_parser('compare', help='Read actual candidates together and derive shared values and differences')
    compare.add_argument('works', type=Path, nargs='+', metavar='WORK')
    compare.add_argument('--out', type=Path, help='Save the derived intermediate comparison report')
    from pack_runtime_cli import add_pack_runtime_arguments, resolve_pack_runtime
    for name, help_text in [('extract', 'Extract actual intermediate content for authoring or investigation'),
                            ('export', 'Validate and export an actual completed candidate value')]:
        output = commands.add_parser(name, help=help_text)
        output.add_argument('work', type=Path)
        output.add_argument('--pointer', help='JSON Pointer within the selected value; defaults to /prompt for content or the root for --basis')
        output.add_argument('--out', type=Path, required=True)
        if name == 'export':
            add_pack_runtime_arguments(output)
        else:
            output.add_argument('--basis', action='store_true', help='Extract the actual acquired basis for a production task; this remains an intermediate artifact')
    args = parser.parse_args(argv)
    try:
        if args.command == 'begin':
            content = c.decode(args.content.read_bytes()) if args.content else None
            if args.prompt or args.negative:
                content = {} if content is None else content
                for key in ('prompt', 'negative'):
                    path = getattr(args, key)
                    if path:
                        content[key] = path.read_bytes().decode('utf-8')
            work = begin_work(operation=args.operation, **_selections(args),
                              baseline=c.decode(args.baseline.read_bytes()) if args.baseline else None,
                              content=content)
            c.atomic_write_json(args.out, work)
            report = {'ok': True, 'work': str(args.out), 'validation': validate_work(work)}
        elif args.command == 'compare':
            if args.out is not None and args.out.resolve() in {path.resolve() for path in args.works}:
                raise ValueError('comparison output must differ from the candidate files')
            report = compare_works([c.decode(path.read_bytes()) for path in args.works],
                                   labels=[str(path) for path in args.works])
            if args.out is not None:
                c.atomic_write_json(args.out, report)
        else:
            from contextlib import nullcontext
            changes_work = args.command in ('context', 'edit', 'replace-text')
            # Share the actual document lock with Production source acquisition.
            # Read the current revision only after obtaining ownership.
            with c.file_lock(args.work) if changes_work else nullcontext():
                work = c.decode(args.work.read_bytes())
                if args.command == 'context':
                    basis = work if args.basis_only else work['basis']
                    updated = revise_basis(basis, **_selections(args, basis))
                    if args.basis_only:
                        work = updated
                    else:
                        work['basis'] = updated
                elif args.command == 'edit':
                    value = (c.decode(args.value_file.read_bytes()) if args.value_file else
                             args.text_file.read_bytes().decode('utf-8') if args.text_file else _UNSET)
                    work = edit_value(work, args.pointer, value, operation=args.operation)
                elif args.command == 'replace-text':
                    work = replace_text(work, args.pointer, args.old_file.read_bytes().decode('utf-8'),
                                        args.new_file.read_bytes().decode('utf-8'))
                if args.command in ('context', 'edit', 'replace-text'):
                    c.atomic_write_json(args.work, work)
                    basis_only = args.command == 'context' and args.basis_only
                    report = {'ok': True, 'basis' if basis_only else 'work': str(args.work),
                              'validation': validate_work({'basis': work, 'content': {}} if basis_only else work)}
                elif args.command == 'inspect':
                    report = resolve_work(work, complete=False)
                elif args.command == 'check':
                    report = validate_work(work, complete=True, require_subject=True)
                elif args.command in ('extract', 'export'):
                    complete = args.command == 'export'
                    resolved = resolve_work(work, complete=complete, require_subject=complete)
                    content = resolved['content']
                    basis_selected = not complete and args.basis
                    pointer = args.pointer if args.pointer is not None else '' if basis_selected else '/prompt'
                    value = _select(work['basis'] if basis_selected else content, pointer)
                    inspection = None
                    if complete:
                        from catalog_api import configure_pack_runtime
                        configure_pack_runtime(resolve_pack_runtime(parser, args).settings)
                        if 'prompt' in content and pointer in ('/prompt', '/negative'):
                            from build_prompt_artifacts import check_content, inspect_content
                            inspection = inspect_content(check_content(content), generation=False,
                                                         require_semantics=False)
                    raw = value.encode('utf-8') if isinstance(value, str) else (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
                    c.atomic(args.out, raw, replace=True)
                    report = {'ok': True, 'output': str(args.out), 'pointer': pointer,
                              'selection': 'basis' if basis_selected else 'content',
                              'state': 'complete' if complete else 'intermediate',
                              'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
                    if inspection is not None:
                        report.update(input_validation=inspection['input_validation'], target=inspection['target'])
    except AuthoringWorkError as error:
        report = error.report
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get('ok', True) else 1


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    import operation_context
    raise SystemExit(operation_context.run_cli(main))
