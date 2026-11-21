"""Acquire actual candidate inputs and retain refused proposals without editing a draft.

A proposal is an immutable candidate, not a program of edits to replay. Its
registration owns the exact choices, basis and selected file bytes. It grants
no authority and does not select a new active draft.
"""
from __future__ import annotations

import copy
from contextlib import ExitStack
from pathlib import Path
import shutil

import execution_contract as c
from input_evidence import InputEvidence


ROOT = Path(__file__).resolve().parents[1]
BOUNDED_FIELDS = ('world_views', 'moment_views', 'scene_materials')


class CapturedCandidate:
    """Supply acquired bounded domains to their existing retained-input owner."""

    def __init__(self, root, descriptor, fallback=None):
        self.root, self.descriptor, self.fallback = root, descriptor, fallback
        self.prepared = {'task': {**copy.deepcopy(fallback.prepared['task'] if fallback else {}),
                                 **copy.deepcopy(descriptor['task'])}}
        self.paths = {**(fallback.paths if fallback else {}),
            **{path: {'path': path, 'sha256': row['sha256'], 'size': row['size']}
               for path, row in descriptor['files'].items()}}
        if fallback is not None:
            self.loaded = fallback.loaded

    def bytes(self, path):
        selected = self.descriptor['files'].get(path)
        if selected is None:
            if self.fallback is None:
                raise ValueError('The captured candidate has no selected bounded input: ' + path)
            return self.fallback.bytes(path)
        from production_store import stable_bytes
        raw = stable_bytes(self.root, selected['path'])
        if c.digest(raw) != selected['sha256'] or len(raw) != selected['size']:
            raise ValueError('The acquired bounded input changed: ' + selected['path'])
        return raw

    def bind(self, reader):
        if self.fallback is not None:
            self.fallback.bind(reader)

    def references(self):
        return self.fallback.references() if self.fallback is not None else None

    def close(self):
        if self.fallback is not None:
            self.fallback.close()


def retained(root: Path, task: dict, descriptor: dict | None, fallback=None):
    from production_saved_inputs import RetainedSelection
    if not descriptor:
        return fallback.selected(task) if fallback is not None else None
    return RetainedSelection(CapturedCandidate(root, descriptor, fallback), task,
        current_paths=set(), current_fields=set(), inherit_task_inputs=False)


class _CapturedReader(InputEvidence):
    """Read an acquired proposal overlay, including named and absolute sources."""

    def __init__(self, root, overlay):
        super().__init__(root, named_roots={'@skill': ROOT})
        self.overlay = overlay

    def _live(self, path):
        selected = self.qualify(path)
        if selected in self.overlay:
            return self.overlay[selected]
        if Path(selected).is_absolute():
            from production_store import stable_bytes
            local = Path(selected)
            return stable_bytes(local.parent, local.name)
        return super()._live(selected)


def _name(root: Path, path: str) -> str:
    return c.local(root, path).relative_to(root.resolve()).as_posix()


def _selected_paths(choices: dict) -> set[str]:
    """Read declared file owners; arbitrary prompt and provider values stay literal."""
    authored = choices['authoring']
    task = authored['task']
    result = set()
    def take(value, key='path'):
        if isinstance(value, dict) and isinstance(value.get(key), str):
            result.add(value[key])
    take(authored['delivery'], 'file')
    for value in authored.get('documents', {}).values():
        take(value, 'file')
    for row in task.get('sources', []):
        take(row); take(row.get('origin'))
    for row in task.get('upload_sources', []):
        take(row, 'file')
    take((task.get('authored') or {}).get('negative'))
    for field in ('semantic_edit',):
        take(task, field); take(choices.get('task_changes'), field)
    take(authored.get('upscale'), 'source')
    target = choices.get('target') or {}
    for key in ('model_file', 'vocabulary_record'):
        take(target, key)
    if isinstance(target.get('model'), dict):
        take(target['model'].get('evidence'))
    import production_reference_inputs as refs
    def references(value):
        if not isinstance(value, dict):
            return
        for row in refs._authored_rows(value):
            take(row, 'file')
            source = row.get('source') or {}
            take(source, 'resolved_path')
        native = value.get('image_input') or {}
        take(native, 'prepared_references')
        if isinstance(native.get('model'), dict):
            take(native['model'].get('evidence'))
    references(authored.get('references'))
    external = choices.get('external') or {}
    references((external.get('reference_delivery') or {}).get('choices'))
    plan = external.get('image_input')
    if isinstance(plan, str):
        result.add(plan)
    elif isinstance(plan, dict):
        if isinstance(plan.get('model'), dict):
            take(plan['model'].get('evidence'))
        request = plan.get('external_request') or {}
        for key in ('schema', 'vocabulary_record'):
            take(request.get(key))
        take((request.get('model_identity') or {}).get('evidence'))
        for row in plan.get('references', []):
            take(row, 'file')
            take((row.get('transport') or {}).get('evidence'))
            take(row.get('transport'), 'uploaded_file')
    validation = choices.get('validation') or {}
    for key in ('contract', 'evidence', 'execution_policy'):
        take(validation, key)
    return result


def _state_selection(choices: dict, files: dict):
    selected = choices['authoring'].get('documents', {}).get('state_graphs')
    if not isinstance(selected, dict) or selected.get('file') not in files:
        return None
    try:
        document = c.decode(files[selected['file']])
        value = document
        for token in selected.get('field', []):
            value = value[token]
        return (selected, document, value) if isinstance(value, dict) and set(value) == {'lineages', 'artifacts'} else None
    except (ValueError, TypeError, KeyError, IndexError):
        return None


def relocate(choices: dict, paths: dict[str, str], measured: dict[str, bytes]) -> dict:
    """Move only each owner's declared locators, preserving shared field selectors."""
    result = copy.deepcopy(choices)
    authored = result['authoring']
    task = authored['task']
    def move(value, key='path'):
        if isinstance(value, dict) and value.get(key) in paths:
            value[key] = paths[value[key]]
    move(authored['delivery'], 'file')
    for value in authored.get('documents', {}).values():
        move(value, 'file')
    for row in task.get('sources', []):
        move(row); move(row.get('origin'))
    for row in task.get('upload_sources', []):
        move(row, 'file')
    move((task.get('authored') or {}).get('negative'))
    move(task, 'semantic_edit'); move(result.get('task_changes'), 'semantic_edit')
    move(authored.get('upscale'), 'source')
    target = result.get('target') or {}
    for key in ('model_file', 'vocabulary_record'):
        move(target, key)
    if isinstance(target.get('model'), dict):
        move(target['model'].get('evidence'))
    import production_reference_inputs
    if authored.get('references') is not None:
        authored['references'] = production_reference_inputs.relocate_sources(authored['references'], paths)
    if result.get('external') is not None:
        import production_external_inputs
        result['external'] = production_external_inputs.relocate_sources(result['external'], paths)
    for key in ('contract', 'evidence', 'execution_policy'):
        move(result.get('validation'), key)
    authored['source_files'] = {paths.get(path, path): c.digest(measured[path]) if path in measured else digest
        for path, digest in authored.get('source_files', {}).items() if path in paths}
    return result


def _bounded_inputs(root: Path, choices: dict, reader, context: dict) -> dict:
    """Capture selected plan/query sources and exact bundle trees without rewriting them."""
    import production_inputs as inputs
    task = choices['authoring']['task']
    descriptor = context.get('candidate_inputs')
    source = (context.get('derived_from') or {}).get('source_run')
    saved = inputs._captured_inputs(root, source) if source is not None else None
    captured = CapturedCandidate(root, descriptor, saved) if descriptor else saved
    files, selected = {}, {}
    try:
        for field in BOUNDED_FIELDS:
            rows = task.get(field, [])
            if not rows:
                continue
            selected[field] = copy.deepcopy(rows)
            held = captured is not None and captured.prepared['task'].get(field, []) == rows

            def read(path):
                c.local(root, path, exists=False)
                raw = captured.bytes(path) if held else reader.read(reader.select(path))
                if path in files and files[path] != raw:
                    raise ValueError('One bounded input selects different acquired revisions: ' + path)
                files[path] = raw
                return raw

            for row in rows:
                for key in ('plan', 'query', 'artifact'):
                    if key not in row:
                        continue
                    value = c.decode(read(row[key]))
                    if key != 'artifact':
                        for original in value.get('sources', []):
                            read(original['path'])
                if 'bundle' in row:
                    prefix = row['bundle'].rstrip('/') + '/'
                    if held:
                        members = [path for path in captured.paths if path.startswith(prefix)]
                    else:
                        directory = c.local(root, row['bundle'])
                        members = [path.relative_to(root).as_posix() for path in directory.rglob('*')
                                   if path.is_file() or path.is_symlink()]
                    for path in sorted(members):
                        read(path)
    finally:
        if captured is not None:
            captured.close()
    return {'task': selected, 'files': files}


def _registration(root: Path, choices_path: str):
    """A nearby document alone cannot declare a snapshot or choose its task owner."""
    import production_authoring_state as state
    path = c.local(root, choices_path)
    manifest_path = path.parent / 'snapshot.json'
    if not manifest_path.is_file():
        return None
    raw = c.read(manifest_path)
    try:
        manifest = c.decode(raw)
    except ValueError:
        return None
    if not isinstance(manifest, dict) or manifest.get('artifact_type') != 'production-candidate-snapshot':
        return None
    task_id = manifest['task_id']
    registration = state._directory(root, task_id) / ('candidate-snapshot-' + c.content_id(choices_path) + '.json')
    registered = c.load(registration)
    details = registered['details']
    if (registered.get('kind') != 'candidate-snapshot' or registered.get('task_id') != task_id
            or details.get('choices') != choices_path or details.get('manifest_sha256') != c.digest(raw)):
        raise ValueError('candidate snapshot differs from its task-owned registration')
    files = {}
    for row in manifest['files']:
        local = c.local(path.parent, row['path'])
        content = c.read(local)
        if c.digest(content) != row['sha256'] or len(content) != row['size']:
            raise ValueError('candidate snapshot member changed: ' + row['path'])
        files[local.relative_to(root).as_posix()] = content
    if (choices_path not in files or manifest.get('choices_file') != choices_path
            or manifest.get('basis_file') not in files):
        raise ValueError('candidate snapshot has no registered choices and basis')
    expected = {c.local(path.parent, item['path']).relative_to(path.parent).as_posix()
                for item in manifest['files']} | {'snapshot.json'}
    actual = {item.relative_to(path.parent).as_posix() for item in path.parent.rglob('*') if item.is_file()}
    if actual != expected or len(manifest['files']) != len(files):
        raise ValueError('candidate snapshot membership differs from its registered manifest')
    return manifest, files


def acquire(root: Path, choices_path: str, *, choices: dict | None = None,
            basis: dict | None = None, files: dict[str, bytes] | None = None) -> dict:
    """Acquire live registered choices or an immutable proposal without publishing input."""
    import production_inputs as inputs
    import production_authoring_state as state
    import production_authoring_work as work
    root = root.resolve()
    choices_path = _name(root, choices_path)
    snapshot = _registration(root, choices_path)
    if snapshot is not None:
        if choices is not None or basis is not None or files:
            raise ValueError('an immutable candidate input cannot receive mutable overrides')
        manifest, captured = snapshot
        selected = inputs.normalize_task_choices(inputs.read_choices(c.decode(captured[choices_path]),
            file=choices_path, root=root))
        if selected['authoring']['task']['task_id'] != manifest['task_id']:
            raise ValueError('candidate snapshot choices identify another task')
        return {'choices': selected, 'basis': c.decode(captured[manifest['basis_file']]),
            'files': captured, 'context': copy.deepcopy(manifest['source_context']),
            'source_choices': choices_path, 'origin': copy.deepcopy(manifest['origin']),
            'runtime_arguments': copy.deepcopy(manifest.get('runtime_arguments')),
            'identity_owners': copy.deepcopy(manifest.get('identity_owners', {})),
            'bounded': {'task': copy.deepcopy((manifest.get('candidate_inputs') or {}).get('task', {})),
                        'files': {path: captured[row['path']] for path, row in
                                  (manifest.get('candidate_inputs') or {}).get('files', {}).items()}}}
    folder = Path(choices_path).parent
    choices_file = c.local(root, choices_path)
    context_file = c.local(root, (folder / 'context.json').as_posix())
    with ExitStack() as stack:
        stack.enter_context(c.file_lock(choices_file))
        original_raw = c.read(choices_file)
        original = inputs.read_choices(c.decode(original_raw), file=choices_path, root=root)
        context_raw = c.read(context_file)
        task_id = original['authoring']['task']['task_id']
        registration = state.require_input_context(root, task_id, folder.as_posix(), context_raw)
        context = c.decode(context_raw)
        if context['authoring_work']['content'] != choices_path:
            raise ValueError('candidate input differs from its registered choices owner')
        basis_path = context['authoring_work']['basis']
        stack.enter_context(c.file_lock(c.local(root, basis_path)))
        basis_raw = c.read(c.local(root, basis_path))
        selected = inputs.normalize_task_choices(copy.deepcopy(choices if choices is not None else original))
        selected_basis = copy.deepcopy(basis if basis is not None else c.decode(basis_raw))
        overlay = dict(files or {})
        reader = _CapturedReader(root, overlay)
        source_run = (context.get('derived_from') or {}).get('source_run')
        if source_run is not None:
            with inputs._captured_inputs(root, source_run) as retained:
                retained.bind(reader)
        if isinstance((selected.get('external') or {}).get('image_input'), str):
            import production_external_inputs
            selected['external'], _ = production_external_inputs.read_selection(selected['external'], reader, root)
        resolved = copy.deepcopy(selected)
        resolved['authoring'], _, missing = inputs.authoring.read_editable(resolved['authoring'], reader)
        if not any(row['field'] == 'authoring.documents.production_spec' for row in missing):
            selected_basis = work.bind_task_subjects(selected_basis, resolved)
        selected, projected, _ = work.project(selected_basis, selected, folder.as_posix())
        overlay.update({(folder / name).as_posix(): raw for name, raw in projected.items()})
        captured = {}
        for path in sorted(_selected_paths(selected)):
            captured[path] = reader.read(reader.select(path))
        state_selection = _state_selection(selected, captured)
        if state_selection is not None:
            for field in ('lineages', 'artifacts'):
                for path in state_selection[2][field]:
                    captured[path] = reader.read(reader.select(path))
        bounded = _bounded_inputs(root, selected, reader, context)
        # A coherent acquisition remains independent of later edits. Reject a
        # concurrent replacement before making its proposal visible.
        if c.read(choices_file) != original_raw or c.read(c.local(root, basis_path)) != basis_raw:
            raise ValueError('candidate editing sources changed while acquiring the input')
        for path, raw in captured.items():
            if path in overlay or path.startswith('@'):
                continue
            local = Path(path) if Path(path).is_absolute() else c.local(root, path)
            if c.read(local) != raw:
                raise ValueError('candidate file changed while acquiring the input: ' + path)
        origin = {'choices': choices_path, 'choices_sha256': c.digest(original_raw),
            'context_sha256': c.digest(context_raw), 'basis_sha256': c.digest(basis_raw)}
        return {'choices': selected, 'basis': selected_basis, 'files': captured,
            'context': context, 'source_choices': choices_path, 'origin': origin,
            'runtime_arguments': registration['details'].get('runtime_arguments'),
            'identity_owners': copy.deepcopy(context.get('identity_owners', {})), 'bounded': bounded}


def materialize(candidate: dict, out_dir: str) -> tuple[dict, dict, dict[str, bytes], dict]:
    """Give a candidate independent editable files while keeping literal content."""
    files, paths = {}, {}
    selected_paths = _selected_paths(candidate['choices'])
    state_selection = _state_selection(candidate['choices'], candidate['files'])
    if state_selection is not None:
        selected_paths.update(state_selection[2]['lineages'])
        selected_paths.update(state_selection[2]['artifacts'])
    for index, (path, raw) in enumerate(sorted(candidate['files'].items())):
        # Membership comes from typed input owners. A user's document may
        # itself be named context.json, snapshot.json or work-basis.json.
        if path not in selected_paths:
            continue
        name = 'editable/' + str(index + 1) + '-' + Path(path).name
        files[name] = raw
        paths[path] = (Path(out_dir) / name).as_posix()
    choices = relocate(candidate['choices'], paths, candidate['files'])
    if state_selection is not None:
        selection, document, value = state_selection
        original = copy.deepcopy(document)
        for field in ('lineages', 'artifacts'):
            value[field] = [paths.get(path, path) for path in value[field]]
        if document != original:
            destination = paths[selection['file']]
            files[destination.removeprefix(out_dir.rstrip('/') + '/')] = c.encoded(document)
    basis = copy.deepcopy(candidate['basis'])
    choices['authoring']['task']['work_basis'] = (Path(out_dir) / 'work-basis.json').as_posix()
    bounded = candidate.get('bounded') or {'task': {}, 'files': {}}
    acquired = {'task': copy.deepcopy(bounded['task']), 'files': {}}
    for path, raw in bounded['files'].items():
        name = 'bounded-inputs/' + path
        files[name] = raw
        acquired['files'][path] = {'path': (Path(out_dir) / name).as_posix(),
                                  'sha256': c.digest(raw), 'size': len(raw)}
    return choices, basis, files, acquired


def preserve_proposal(root: Path, source_choices_path: str, *, choices: dict, basis: dict,
                      files: dict[str, bytes] | None = None, details: dict | None = None) -> dict:
    """Retain a refused operation's complete proposed candidate beside its task."""
    import production_authoring_state as state
    import production_inputs as inputs
    import production_authoring_work as work
    from pack_manager import generate_uuid7
    root = root.resolve()
    candidate = acquire(root, source_choices_path, choices=choices, basis=basis, files=files)
    task_id = candidate['choices']['authoring']['task']['task_id']
    folder = (state._directory(root, task_id) / 'candidate-inputs' / generate_uuid7()).relative_to(root).as_posix()
    relocated, proposed_basis, staged, candidate_inputs = materialize(candidate, folder)
    relocated, projected, _ = work.project(proposed_basis, relocated, folder)
    staged.update(projected)
    choices_path = (Path(folder) / 'choices.json').as_posix()
    basis_path = (Path(folder) / 'work-basis.json').as_posix()
    staged.update({'choices.json': c.encoded(relocated), 'work-basis.json': c.encoded(proposed_basis)})
    manifest = {'artifact_type': 'production-candidate-snapshot', 'task_id': task_id,
        'choices_file': choices_path, 'basis_file': basis_path, 'origin': candidate['origin'],
        'source_context': candidate['context'], 'runtime_arguments': candidate['runtime_arguments'],
        'candidate_inputs': candidate_inputs,
        'identity_owners': candidate['identity_owners'], 'proposal': copy.deepcopy(details or {}),
        'files': [{'path': name, 'sha256': c.digest(raw), 'size': len(raw)}
                  for name, raw in sorted(staged.items())]}
    raw = c.encoded(manifest)
    staged['snapshot.json'] = raw
    details = {'choices': choices_path, 'manifest_sha256': c.digest(raw),
               'source_choices': candidate['source_choices']}
    registered = state._directory(root, task_id) / ('candidate-snapshot-' + c.content_id(choices_path) + '.json')
    published = c.local(root, folder, exists=False)
    try:
        inputs._publish(root, folder, staged, reader=InputEvidence(root))
        # The task pointer is the visibility boundary. A failed publication
        # never leaves a registered candidate that has no exact input bytes.
        state._remember(root, task_id, 'candidate-snapshot', choices_path, details)
    except BaseException:
        if registered.is_file() and c.load(registered).get('details') == details:
            registered.unlink()
        if published.is_dir():
            actual = {path.relative_to(published).as_posix(): c.read(path)
                      for path in published.rglob('*') if path.is_file()}
            if actual == staged:
                shutil.rmtree(published)
        raise
    return {'state': 'proposed-input', 'choices_file': choices_path, 'basis_file': basis_path,
        'snapshot_file': (Path(folder) / 'snapshot.json').as_posix(), 'external_effect': False}


def inspect(root: Path, choices_path: str) -> dict | None:
    """Expose a registered proposal without selecting or mutating an active draft."""
    root = root.resolve()
    choices_path = _name(root, choices_path)
    snapshot = _registration(root, choices_path)
    if snapshot is None:
        return None
    manifest, files = snapshot
    from cli_invocation import python_argv, shown
    folder = Path(choices_path).parent
    destination = 'work/compose-' + folder.name
    argv = python_argv(ROOT / 'scripts/production_workflow.py', 'draft-inputs',
        '--root', str(root), '--choices', choices_path, '--out-dir', destination)
    return {'state': 'proposed-input', 'choices_file': choices_path,
        'choices': c.decode(files[choices_path]), 'basis_file': manifest['basis_file'],
        'source': manifest['origin'], 'proposal': manifest['proposal'],
        'next_actions': [{'command': 'draft-inputs', 'argv': argv, 'shown': shown(argv),
                          'reason': 'Compose this retained proposed candidate in its own editable directory.',
                          'external_effect': False}], 'external_effect': False}
