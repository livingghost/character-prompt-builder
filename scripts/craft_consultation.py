"""Consult reusable craft knowledge and bind authored applications to production.

Catalog search supplies candidates. The agent chooses the records, their scope,
changes and review questions. Existing production sources preserve that work.
"""
from __future__ import annotations

import copy
from collections import Counter
from pathlib import Path
from typing import Any

import execution_contract as c
from input_evidence import InputEvidence
from catalog_retrieval import runtime
from catalog_retrieval.assets import asset_lookup
from catalog_retrieval.batch import execute_batch
from catalog_retrieval.retrieval import catalog_stats, inspect_record
from pack_manager import configured_roots, discover_packs, load_effective_state

# These are explicit navigation choices, not classifications of query text.
LAYERS = {
    'scene': (('scenes', ('scene',)), ('recipes', ('recipe',))),
    'detail': (('modules', ('module',)),),
    'finish': (('families', ('style-family',)), ('profiles', ('profile',)),
               ('aesthetic', ('aesthetic-core',)), ('realizations', ('domain-realization',))),
    'repair': (('corrections', ('correction',)),),
    'identity': (('archetypes', ('archetype',)),),
}
COMMANDS = frozenset({'consult-presets', 'apply-presets'})
ROLE = 'preset-application'


def strings(value: Any, label: str, *, empty: bool = False) -> list[str]:
    if not isinstance(value, list) or (not empty and not value):
        raise ValueError(label + ' must be an explicit array')
    for item in value:
        c.text(item, label)
    if len(value) != len(set(value)):
        raise ValueError(label + ' contains duplicate selections')
    return value


def scope(settings=None, *, catalog=None, entries=None) -> dict:
    """Expose discovery and active records without changing pack selection."""
    settings = settings or runtime.selected_pack_settings()
    catalog = catalog or runtime.load_pack_catalog()
    entries = runtime.load_entries() if entries is None else entries
    state = load_effective_state(settings)
    discovered, issues = discover_packs(settings, state)
    enabled = set(state['enabled_packs'])
    counts = Counter(entry.source_pack for entry in entries)
    return {
        'runtime_fingerprint': catalog.fingerprint,
        'state_file': str(settings.state_file),
        'configured_roots': [str(path) for path in configured_roots(settings, state)],
        'enabled_packs': sorted(enabled),
        'disabled_discovered_packs': sorted(set(discovered) - enabled),
        'unavailable_enabled_packs': sorted(enabled - set(discovered)),
        'packs': [{'pack_id': key, 'name': pack.manifest.get('name'),
                   'root': str(pack.root), 'enabled': key in enabled,
                   'searchable_records': counts[key]}
                  for key, pack in sorted(discovered.items())],
        'active_pack_count': catalog.active_pack_count,
        'searchable': catalog_stats(entries),
        'selected_providers': copy.deepcopy(state['resource_providers']),
        'resolved_providers': {key: value.source_pack for key, value in sorted(catalog.resources.items())},
        'diagnostics': [issue.to_dict() for issue in issues] + list(catalog.diagnostics),
        'coverage': 'Only this resolved catalog was searched. File presence is separate from activation.',
    }


def navigation(root: Path, task_path: str | None = None, *, include_scope: bool = False,
               runtime_arguments: dict | None = None) -> dict:
    args = {'root': str(root), **(runtime_arguments or {})}
    if task_path is not None:
        args['task'] = task_path
    return {'scope': scope() if include_scope else None,
            'focuses': {key: [name for name, _ in rows] for key, rows in LAYERS.items()},
            'next_actions': [{'operation': 'consult-presets', 'script': 'scripts/production_workflow.py',
                              'args': args, 'required_args': ['out-dir', *(['task'] if task_path is None else [])],
                              'external_effect': False, 'budget_effect': 'none'}],
            'use': 'Consult while choosing a direction, resolving one craft question, or investigating an observed failure.'}


def open_records(entries, identifiers: list[str]) -> list[dict]:
    """Open explicit choices and schema-declared recipe/profile dependencies."""
    strings(identifiers, 'record identifiers', empty=True)
    by_id = {str(entry.record['id']): entry for entry in entries}
    queue = list(identifiers)
    opened = {}
    while queue:
        identifier = queue.pop(0)
        if identifier in opened:
            continue
        if identifier not in by_id:
            raise ValueError('record is unavailable in the selected catalog: ' + identifier)
        entry = by_id[identifier]
        try:
            full = inspect_record(entries, identifier)
            assets = asset_lookup(identifier, summary=False)
        except SystemExit as exc:
            raise ValueError(str(exc)) from exc
        raw = c.read(c.local(entry.source_root, entry.source_file))
        dependencies = []
        fields = ('base_scene_id', 'render_profile_id') if entry.kind == 'recipe' else (
            ('render_profile_id',) if entry.kind == 'style-family' else ())
        for field in fields:
            value = entry.record.get(field)
            if value is not None:
                c.text(value, 'declared record dependency')
                dependencies.append({'field': field, 'record_id': value})
                queue.append(value)
        opened[identifier] = {**full, 'assets': assets, 'requested': identifier in identifiers,
                              'record_sha256': c.content_id(entry.record),
                              'source_file_sha256': c.digest(raw), 'dependencies': dependencies}
    return list(opened.values())


def consult(questions: list[dict], identifiers: list[str], *, settings=None,
            previous: dict | None = None) -> dict:
    """Run all questions on one fresh snapshot with separate knowledge layers."""
    if not isinstance(questions, list):
        raise ValueError('questions must be an array')
    catalog = runtime.begin_catalog_request()
    entries = runtime.load_entries()
    inventory = scope(settings, catalog=catalog, entries=entries)
    if previous is not None:
        if previous.get('artifact_type') != 'craft-consultation' or previous.get('ok') is not True:
            raise ValueError('previous consultation must be a successful saved report')
        if previous['scope']['runtime_fingerprint'] != catalog.fingerprint:
            raise ValueError('catalog changed; repeat the affected questions in the current runtime')
    requests = []
    ids = set()
    for question in questions:
        if not isinstance(question, dict):
            raise ValueError('each craft question must be an object')
        optional = {'domain', 'anchors', 'categories', 'limit', 'tier', 'source_brief', 'source_language'}
        c.exact(question, {'request_id', 'canonical_query', 'focus'} | (optional & question.keys()), 'craft question')
        identifier = c.text(question['request_id'], 'question ID')
        c.text(question['canonical_query'], 'canonical craft question')
        if identifier in ids:
            raise ValueError('duplicate question ID: ' + identifier)
        ids.add(identifier)
        focus = question['focus']
        if focus != 'all' and focus not in LAYERS:
            raise ValueError('select a declared focus')
        selected = LAYERS.values() if focus == 'all' else [LAYERS[focus]]
        for layer in selected:
            for name, kinds in layer:
                query = {key: value for key, value in question.items() if key not in {'request_id', 'focus'}}
                query.update(request_id=identifier + ':' + name, command='search', kind=list(kinds))
                query.setdefault('limit', 4)
                requests.append(query)
    search = execute_batch(entries, requests) if requests else {
        'request_count': 0, 'success_count': 0, 'error_count': 0, 'results': []}
    prior_ids = [row['record_id'] for row in previous.get('inspected', []) if row['requested']] if previous else []
    inspected = open_records(entries, list(dict.fromkeys([*prior_ids, *identifiers])))
    history = copy.deepcopy(previous.get('history', [])) if previous else []
    if previous is not None:
        history.append({'questions': previous['questions'], 'search': previous['search']})
    return {'artifact_type': 'craft-consultation', 'ok': search['error_count'] == 0,
            'scope': inventory, 'questions': copy.deepcopy(questions), 'search': search, 'inspected': inspected,
            'history': history,
            'application_template': {'source_id': None, 'reason': None, 'uses': [], 'not_used': []},
            'use_fields': ['record_id', 'borrowed', 'preserved', 'changed', 'targets', 'review_criteria', 'review_question'],
            'empty_result': 'An empty layer concerns these questions and this catalog. Refine the question or choose another layer.',
            'selection': 'Read the complete records. Choose fitting knowledge, including none; relevance is not acceptance.',
            'external_effect': False, 'budget_effect': 'none'}


def pointer_value(value: Any, pointer: str) -> Any:
    c.text(pointer, 'production field pointer')
    if not pointer.startswith('/'):
        raise ValueError('target must be a JSON Pointer to an existing production field')
    node = value
    for part in pointer[1:].split('/'):
        # JSON Pointer escape syntax, not text meaning or a path search.
        index = 0
        while index < len(part):
            if part[index] == '~':
                if index + 1 == len(part) or part[index + 1] not in '01':
                    raise ValueError('invalid JSON Pointer escape')
                index += 1
            index += 1
        key = part.replace('~1', '/').replace('~0', '~')
        if isinstance(node, list):
            if not key.isascii() or not key.isdecimal() or str(int(key)) != key or int(key) >= len(node):
                raise ValueError('target array position does not exist')
            node = node[int(key)]
        elif isinstance(node, dict) and key in node:
            node = node[key]
        else:
            raise ValueError('target field does not exist: ' + pointer)
    return copy.deepcopy(node)


def apply(root: Path, task_path: str, report_path: str, decisions_path: str,
          spec_path: str, out_dir: str, *, settings=None, runtime_arguments: dict | None = None) -> dict:
    """Snapshot selected knowledge and annotate existing sources, never compose text."""
    import production_inputs as inputs
    import production_workflow as workflow
    import production_spec
    root = root.resolve(strict=True)
    reader = InputEvidence(root)
    task_ref = reader.select(task_path); task = reader.json(task_ref)
    workflow.validate_task(task)
    report_ref = reader.select(report_path); report = reader.json(report_ref)
    decisions_ref = reader.select(decisions_path); decisions = reader.json(decisions_ref)
    spec_ref = reader.select(spec_path); spec = reader.json(spec_ref)
    checked = production_spec.validate(spec)
    if not checked['ok']:
        raise ValueError('production specification: ' + '; '.join(checked['errors']))
    if report.get('artifact_type') != 'craft-consultation' or report.get('ok') is not True:
        raise ValueError('select a successful craft consultation')
    if 'task' in report and report['task'] != task_ref:
        raise ValueError('consultation names a different task snapshot; consult the current task')
    catalog = runtime.begin_catalog_request(); entries = runtime.load_entries()
    if report['scope']['runtime_fingerprint'] != catalog.fingerprint:
        raise ValueError('catalog changed; repeat affected retrieval before applying it')
    originals = {row['record_id']: row for row in report['inspected']}
    current = {row['record_id']: row for row in open_records(entries, list(originals))}
    for identifier, row in originals.items():
        if type(row.get('requested')) is not bool:
            raise ValueError('inspected record selection must be explicit')
        expected = {**current[identifier], 'requested': row['requested']}
        if c.content_id(row) != c.content_id(expected):
            raise ValueError('inspected record or linked asset evidence differs: ' + identifier)
    c.exact(decisions, {'source_id', 'reason', 'uses', 'not_used'}, 'preset decisions')
    source_id = c.text(decisions['source_id'], 'application source ID')
    c.text(decisions['reason'], 'application reason')
    if source_id in {row['id'] for row in task['sources']}:
        raise ValueError('application source ID already exists; select a distinct source ID')
    if not isinstance(decisions['uses'], list) or not isinstance(decisions['not_used'], list):
        raise ValueError('uses and not_used must be explicit arrays')
    known_criteria = {row['id'] for row in task['criteria']}
    applications = []; selected = []; rejected = []
    for use in decisions['uses']:
        c.exact(use, {'record_id', 'borrowed', 'preserved', 'changed', 'targets', 'review_criteria', 'review_question'}, 'preset application')
        identifier = c.text(use['record_id'], 'record ID')
        if identifier not in originals or identifier in selected:
            raise ValueError('select each inspected record once: ' + str(identifier))
        for key in ('borrowed', 'preserved', 'changed', 'review_question'):
            c.text(use[key], key)
        targets = strings(use['targets'], 'application targets')
        criteria = strings(use['review_criteria'], 'review criteria')
        if set(criteria) - known_criteria:
            raise ValueError('application names an unknown review criterion')
        if any(path == '/selected_preset_ids' or path.startswith('/selected_preset_ids/') for path in targets):
            raise ValueError('target an authored production field, not the derived selection list')
        values = {path: pointer_value(spec, path) for path in targets}
        applications.append({**copy.deepcopy(use), 'target_values': values,
                             'source': copy.deepcopy(originals[identifier])})
        selected.append(identifier)
    for unused in decisions['not_used']:
        c.exact(unused, {'record_id', 'reason'}, 'unused preset')
        identifier = c.text(unused['record_id'], 'record ID'); c.text(unused['reason'], 'nonuse reason')
        if identifier not in originals or identifier in selected or identifier in rejected:
            raise ValueError('nonuse must name a distinct inspected, unselected record')
        rejected.append(identifier)
    if not applications and not rejected:
        raise ValueError('record a deliberate application or nonuse decision')
    if set(spec['selected_preset_ids']) & set(rejected):
        raise ValueError('nonuse cannot remove an existing selection; revise that authored choice explicitly')
    # Existing choices and their task sources survive a later, local lookup.
    preserved = list(spec['selected_preset_ids'])
    selected_ids = list(dict.fromkeys([*preserved, *selected]))
    changed_spec = copy.deepcopy(spec); changed_spec['selected_preset_ids'] = selected_ids
    app_path = out_dir + '/preset-application.json'; new_spec = out_dir + '/production-spec.json'
    output_task = copy.deepcopy(task)
    spec_sources = [row for row in output_task['sources'] if row['path'] == spec_path]
    for row in spec_sources:
        row['path'] = new_spec
    if not spec_sources:
        spec_id = source_id + '-spec'
        if spec_id in {row['id'] for row in task['sources']}:
            raise ValueError('derived specification source ID conflicts with an existing source')
        output_task['sources'].append({'id': spec_id, 'path': new_spec, 'role': 'production-spec',
            'disposition': 'applied', 'locator': 'selected_preset_ids and authored fields',
            'reason': decisions['reason']})
    output_task['sources'].append({'id': source_id, 'path': app_path, 'role': ROLE,
        'disposition': 'applied' if applications else 'considered-not-used',
        'locator': 'applications and not_used', 'reason': decisions['reason']})
    output_task['delivery']['translation_notes'] += '\nRead source ' + source_id + ' for scoped craft applications and review questions.'
    workflow.validate_task(output_task)
    application = {'artifact_type': ROLE, 'task_id': task['task_id'], 'reason': decisions['reason'],
        'consultation': report, 'consultation_file': report_ref, 'decisions_file': decisions_ref,
        'production_spec_sha256': production_spec.digest(changed_spec),
        'applications': applications, 'not_used': copy.deepcopy(decisions['not_used']),
        'assessment': 'Intended application only. Review the actual candidate against its declared criteria.'}
    # Existing input publication rechecks all selected project bytes under its lock.
    # Also retain witnesses of the selected pack files and activation state.
    settings = settings or runtime.selected_pack_settings()
    witnesses = {entry.source_root / entry.source_file: current[str(entry.record['id'])]['source_file_sha256']
                 for entry in entries if str(entry.record['id']) in originals}
    state_bytes = settings.state_file.read_bytes() if settings.state_file.is_file() else None
    def recheck():
        now = settings.state_file.read_bytes() if settings.state_file.is_file() else None
        if now != state_bytes or any(c.digest(c.read(path)) != digest for path, digest in witnesses.items()):
            raise ValueError('selected preset inputs changed before publication')
    files = {'preset-application.json': c.encoded(application), 'production-spec.json': c.encoded(changed_spec),
             'production-task.json': c.encoded(output_task), 'input-snapshots.json': c.encoded(reader.snapshots)}
    inputs._publish(root, out_dir, files, reader=reader, before_publish=recheck)
    return {'ok': True, 'task': out_dir + '/production-task.json', 'production_spec': new_spec,
            'application': app_path, 'selected_preset_ids': selected_ids,
            'preserved_selected_preset_ids': preserved, 'applied_record_ids': selected, 'execution_ready': False,
            'external_effect': False, 'budget_effect': 'none',
            'next_actions': [{'operation': 'draft-inputs', 'script': 'scripts/production_workflow.py',
                'args': {'root': str(root), 'task': out_dir + '/production-task.json', **(runtime_arguments or {})},
                'required_args': ['out-dir'], 'external_effect': False, 'budget_effect': 'none'}]}


def review_questions(root: Path, task: dict, *, directory: Path | None = None,
                     dependencies: list[dict] | None = None) -> dict[str, list[str]]:
    """Copy authored questions into unassessed review checks."""
    output = {}
    for source in task['sources']:
        if source['role'] != ROLE or source['disposition'] != 'applied':
            continue
        if directory is None:
            record = c.load(c.local(root, source['path']))
        else:
            matches = [item for item in dependencies or []
                       if item['space'] == 'project' and item['path'] == source['path']]
            if len(matches) != 1:
                raise ValueError('application source has no unique prepared dependency')
            record = c.decode(c.object_read(directory, matches[0]['sha256']))
        if record.get('artifact_type') != ROLE or record.get('task_id') != task['task_id']:
            raise ValueError('preset application belongs to a different task')
        for row in record['applications']:
            for criterion in row['review_criteria']:
                output.setdefault(criterion, []).append(row['review_question'])
    return output


def add_arguments(subparsers) -> None:
    from pack_runtime_cli import add_pack_runtime_arguments
    for name in sorted(COMMANDS):
        parser = subparsers.add_parser(name, help='Consult craft assets or record their scoped application without execution.')
        parser.add_argument('--root', type=Path, required=True)
        parser.add_argument('--task', required=True)
        parser.add_argument('--out-dir', required=True, help='New project-relative directory.')
        add_pack_runtime_arguments(parser)
        if name == 'consult-presets':
            group = parser.add_mutually_exclusive_group()
            group.add_argument('--query', help='Agent-authored canonical craft question.')
            group.add_argument('--questions', help='Project-relative array of explicit questions and focuses.')
            parser.add_argument('--focus', choices=['all', *LAYERS], default='all')
            parser.add_argument('--inspect', nargs='*', default=[], metavar='ID')
            parser.add_argument('--previous', help='Previous project-relative consultation report from this runtime.')
        else:
            parser.add_argument('--consultation', required=True)
            parser.add_argument('--decisions', required=True)
            parser.add_argument('--spec', required=True)


def command(args, parser) -> dict:
    from pack_runtime_cli import resolve_pack_runtime
    import production_inputs as inputs
    runtime_context = resolve_pack_runtime(parser, args)
    runtime_arguments = {'state-file': str(runtime_context.settings.state_file),
        'cache-dir': str(runtime_context.settings.cache_dir), 'managed-root': str(runtime_context.settings.managed_root),
        'pack-root': [str(path) for path in runtime_context.pack_roots]}
    with runtime.using_pack_runtime(runtime_context.settings):
        if args.command == 'apply-presets':
            return apply(args.root, args.task, args.consultation, args.decisions, args.spec, args.out_dir,
                         settings=runtime_context.settings, runtime_arguments=runtime_arguments)
        root = args.root.resolve(strict=True); reader = InputEvidence(root)
        task_ref = reader.select(args.task); task = reader.json(task_ref)
        c.text(task.get('task_id'), 'work task ID')
        questions = reader.json(reader.select(args.questions)) if args.questions else (
            [{'request_id': 'craft', 'canonical_query': args.query, 'focus': args.focus}] if args.query else [])
        previous = reader.json(reader.select(args.previous)) if args.previous else None
        result = consult(questions, args.inspect, settings=runtime_context.settings, previous=previous)
        result['task'] = task_ref
        result['next_actions'] = [
            {'operation': 'consult-presets', 'script': 'scripts/production_workflow.py',
             'args': {'root': str(root), 'task': args.task, 'previous': args.out_dir + '/consultation.json',
                      **runtime_arguments}, 'required_args': ['out-dir'],
             'external_effect': False, 'budget_effect': 'none'},
            {'operation': 'apply-presets', 'script': 'scripts/production_workflow.py',
             'args': {'root': str(root), 'task': args.task, 'consultation': args.out_dir + '/consultation.json',
                      'decisions': args.out_dir + '/decisions.json', **runtime_arguments},
             'required_args': ['spec', 'out-dir'], 'external_effect': False, 'budget_effect': 'none'}]
        files = {'consultation.json': c.encoded(result), 'decisions.json': c.encoded(result['application_template'])}
        inputs._publish(root, args.out_dir, files, reader=reader)
        return {**result, 'consultation': args.out_dir + '/consultation.json',
                'decisions': args.out_dir + '/decisions.json'}
