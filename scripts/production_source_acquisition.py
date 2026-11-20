"""Acquire a public source row into the registered draft that owns its selection.

The basis retains exact source bytes and Production metadata. Choices hold the
derived task view beside the author's other current content. This operation
changes no saved run, authority, adoption record or external request.
"""
from __future__ import annotations

import copy
from pathlib import Path

import execution_contract as c
import production_authoring as authoring
import production_authoring_state as state
import production_authoring_work as work
from input_evidence import InputEvidence
from production_diagnostics import ProductionError


def _publish(root: Path, *, predecessors: dict[str, bytes], replacements: dict[str, bytes],
             sources: dict[str, bytes]) -> bool:
    """Replace the owned basis and its choices view, restoring them on failure.

    All values and existing content-addressed files are checked before a write.
    The caller owns both existing mutable files with execution_contract.file_lock.
    A partial immutable publication is removed only when this operation created
    it and its exact content is still present.
    """
    for name, raw in sources.items():
        path = c.local(root, name, exists=False)
        observed = c.read(path) if path.exists() else None
        if observed is not None and observed != raw:
            raise ProductionError('INPUT_CONSISTENCY_ERROR',
                'A projected source differs from its existing content-addressed file.',
                phase='source-acquisition', file=name, cause='projected-source-content-conflict',
                expected=c.digest(raw), actual=c.digest(observed), guidance=work.SOURCE_GUIDANCE,
                required_action='Restore the named acquired source file to its recorded content before '
                    'acquiring the source again. The current choices and basis have not changed.')
    changed = {name: raw for name, raw in replacements.items() if raw != predecessors[name]}
    created, applied = [], []
    try:
        for name, raw in sources.items():
            path = c.local(root, name, exists=False)
            if path.exists():
                continue
            try:
                c.atomic(path, raw)
            except FileExistsError:
                if c.read(path) != raw:
                    raise
            except BaseException:
                if path.is_file() and c.read(path) == raw:
                    created.append((path, raw))
                raise
            else:
                created.append((path, raw))
        for name, raw in predecessors.items():
            if c.read(c.local(root, name)) != raw:
                raise ProductionError('INPUT_CONSISTENCY_ERROR',
                    'The editable draft changed during source acquisition.',
                    phase='source-acquisition', file=name, cause='authoring-source-changed',
                    guidance=work.SOURCE_GUIDANCE,
                    required_action='Inspect the current draft edits, then run acquire-source again '
                        'against that current revision.')
        for name, raw in changed.items():
            applied.append((name, raw))
            c.atomic(c.local(root, name), raw, replace=True)
    except BaseException as failure:
        rollback_errors = []
        for name, raw in reversed(applied):
            try:
                path = c.local(root, name)
                current = c.read(path)
                if current == raw:
                    c.atomic(path, predecessors[name], replace=True)
                elif current != predecessors[name]:
                    raise ValueError('the file was changed outside the acquisition owner')
            except (OSError, ValueError) as error:
                rollback_errors.append({'file': name, 'message': str(error)})
        for path, raw in reversed(created):
            try:
                if path.is_file() and c.read(path) == raw:
                    path.unlink()
                    c.fsync_dir(path.parent)
            except (OSError, ValueError) as error:
                rollback_errors.append({'file': path.relative_to(root).as_posix(), 'message': str(error)})
        if rollback_errors:
            raise ProductionError('ARTIFACT_PUBLISH_FAILED',
                'Source acquisition failed and the listed draft files could not be restored.',
                phase='source-acquisition', cause='source-acquisition-rollback-incomplete',
                rollback_errors=rollback_errors, guidance=work.SOURCE_GUIDANCE,
                required_action='Inspect the listed files and restore the retained draft revision before '
                    'retrying acquire-source. No saved run or authority record was changed.') from failure
        raise
    return bool(changed or created)


def acquire_source(root: Path, choices_path: str, source_row_path: str) -> dict:
    """Acquire one complete public source row, then publish its current task projection.

    Source paths use the Studio root and the CLI resolves the descriptor at
    its ordinary file-input boundary. All current draft selection and source
    checks finish before any file is changed.
    """
    import production_inputs
    from cli_invocation import python_argv, shown

    root = c._root(root)
    choices_file = c.local(root, choices_path)
    folder = Path(choices_path).parent.as_posix()
    context_path = (Path(folder) / 'context.json').as_posix()
    try:
        source = c.read_json_input(source_row_path, root=root)
    except (OSError, ValueError, TypeError) as error:
        raise ProductionError('INPUT_UNREADABLE', 'The Production source-row descriptor cannot be read.',
            phase='source-acquisition', file=source_row_path, pointer='', cause='source-row-unreadable',
            detail=str(error), guidance=work.SOURCE_GUIDANCE,
            repair_owner={'file': source_row_path, 'pointer': ''},
            required_action='Save a readable JSON source-row descriptor at this path, then run '
                'acquire-source with that descriptor again.') from error
    work.validate_source_row(source, file=source_row_path)
    with c.file_lock(choices_file):
        choices_raw = c.read(choices_file)
        choices = production_inputs.read_choices(c.decode(choices_raw), file=choices_path, root=root)
        context_raw = c.read(c.local(root, context_path)) if c.local(root, context_path, exists=False).is_file() else b''
        task_id = choices['authoring']['task']['task_id']
        state.require_input_context(root, task_id, folder, context_raw)
        context = c.decode(context_raw)
        selected_work = context['authoring_work']
        if selected_work['content'] != choices_path:
            raise ProductionError('AUTHORING_WORK_MISMATCH',
                'The registered authoring work identifies another actual candidate.',
                phase='source-acquisition', file=context_path, pointer='/authoring_work/content',
                expected=choices_path, actual=selected_work['content'], guidance=work.SOURCE_GUIDANCE,
                required_action='Select the choices file named by the registered authoring work, '
                    'then run acquire-source for that draft.')
        basis_path = selected_work['basis']
        basis_file = c.local(root, basis_path)
        with c.file_lock(basis_file):
            basis_raw = c.read(basis_file)
            basis = c.decode(basis_raw)
            source_path = (source.get('origin') or {}).get('path', source['path'])
            try:
                raw = c.read(c.local(root, source_path))
            except (OSError, ValueError) as error:
                raise ProductionError('INPUT_UNREADABLE', 'The selected source original cannot be read.',
                    phase='source-acquisition', file=source_row_path, pointer='/path',
                    cause='source-original-unreadable', source=source['id'], source_file=source_path,
                    detail=str(error), guidance=work.SOURCE_GUIDANCE,
                    repair_owner={'file': source_row_path, 'pointer': '/path'},
                    required_action='Select a readable Studio-relative source path in the descriptor, '
                        'then run acquire-source again. The previous draft is unchanged.') from error
            revised = work.acquire_source_row(basis, source, raw, file=source_row_path)
            reader = InputEvidence(root)
            resolved = copy.deepcopy(choices)
            resolved['authoring'], _, document_gaps = authoring.read_editable(resolved['authoring'], reader)
            if not any(row['field'] == 'authoring.documents.production_spec' for row in document_gaps):
                revised = work.bind_task_subjects(revised, resolved)
            projected, files, _ = work.project(revised, choices, folder)
            diagnostics = work.projection_diagnostics(revised, choices, projected=projected,
                root=root, choices_path=choices_path, basis_path=basis_path)
            resolved['authoring']['task'] = copy.deepcopy(projected['authoring']['task'])
            gaps = [*document_gaps, *diagnostics, *work.unresolved(revised, resolved,
                require_subject=work.requires_subject(projected['authoring']['task']),
                root=root, choices_path=choices_path, basis_path=basis_path)]
            replacements = {basis_path: c.encoded(revised), choices_path: c.encoded(projected)}
            sources = {(Path(folder) / name).as_posix(): value for name, value in files.items()}
            changed = _publish(root, predecessors={basis_path: basis_raw, choices_path: choices_raw},
                replacements=replacements, sources=sources)
    inspect_argv = python_argv(Path(__file__).with_name('production_workflow.py'), 'inspect-inputs',
        '--root', str(root), '--choices', choices_path)
    return {'ok': True, 'state': 'source-acquired', 'changed': changed,
        'source': source['id'], 'source_row': source_row_path,
        'acquired': {'sha256': revised['sources'][source['id']]['sha256'], 'path': source_path},
        'choices_file': choices_path, 'basis_file': basis_path,
        'projected_source': next((row for row in projected['authoring']['task']['sources']
                                  if row['id'] == source['id']), None),
        'applications': {key: copy.deepcopy(row) for key, row in revised['applications'].items()
                         if row['source'] == source['id']},
        'subjects': {key: [item for item in assigned
                          if revised['applications'][item]['source'] == source['id']]
                     for key, assigned in revised['subjects'].items()
                     if any(revised['applications'][item]['source'] == source['id'] for item in assigned)},
        'unresolved': gaps,
        'next_actions': [{'command': 'inspect-inputs', 'argv': inspect_argv, 'shown': shown(inspect_argv),
                          'reason': 'Inspect the current draft and continue its remaining authored choices.'}],
        'external_effect': False}
