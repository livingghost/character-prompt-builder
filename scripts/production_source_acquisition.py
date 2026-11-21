"""Acquire a public source row into the registered draft that owns its selection.

The basis retains exact source bytes and Production metadata. Choices hold the
derived task view beside the author's other current content. This operation
changes no saved run, authority, adoption record or external request.
"""
from __future__ import annotations

import copy
from pathlib import Path

import execution_contract as c
import production_authoring_work as work
from production_diagnostics import ProductionError


def _publish(root: Path, *, predecessors: dict[str, bytes], replacements: dict[str, bytes],
             sources: dict[str, bytes], operation: str = 'acquire-source') -> bool:
    """Replace the owned basis and its choices view, restoring them on failure.

    All values and existing content-addressed files are checked before a write.
    The caller owns both existing mutable files with execution_contract.file_lock.
    A partial immutable publication is removed only when this operation created
    it and its exact content is still present.
    """
    phase = 'source-acquisition' if operation == 'acquire-source' else 'authoring'

    def predecessor_bytes(name: str) -> bytes:
        path = Path(name)
        if path.is_absolute():
            from production_store import stable_bytes
            return stable_bytes(path.parent, path.name)
        return c.read(c.local(root, name))

    def verify_predecessors() -> None:
        for name, raw in predecessors.items():
            if predecessor_bytes(name) != raw:
                raise ProductionError('INPUT_CONSISTENCY_ERROR',
                    'The editable draft or its selected evidence changed during its candidate update.',
                    phase=phase, file=name, cause='authoring-source-changed',
                    guidance=work.SOURCE_GUIDANCE,
                    required_action='Inspect the current draft edits and source evidence, then run ' + operation + ' again '
                        'against that current revision.')

    verify_predecessors()
    for name, raw in sources.items():
        path = c.local(root, name, exists=False)
        observed = c.read(path) if path.exists() else None
        if observed is not None and observed != raw:
            raise ProductionError('INPUT_CONSISTENCY_ERROR',
                'A projected source differs from its existing content-addressed file.',
                phase=phase, file=name, cause='projected-source-content-conflict',
                expected=c.digest(raw), actual=c.digest(observed), guidance=work.SOURCE_GUIDANCE,
                required_action='Restore the named acquired source file to its recorded content before '
                    'retrying the candidate update. The current choices and basis have not changed.')
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
        verify_predecessors()
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
                'The candidate update failed and the listed draft files could not be restored.',
                phase=phase, cause='source-acquisition-rollback-incomplete',
                rollback_errors=rollback_errors, guidance=work.SOURCE_GUIDANCE,
                required_action='Inspect the listed files and restore the retained draft revision before '
                    'retrying ' + operation + '. No saved run or authority record was changed.') from failure
        raise
    return bool(changed or created)


def acquire_source(root: Path, choices_path: str, source_row_path: str) -> dict:
    """Acquire a public source row through the shared candidate mutation owner."""
    from production_draft_mutation import update_draft

    root = c._root(root)
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
    source_path = (source.get('origin') or {}).get('path', source['path'])

    def transform(choices, basis, reader):
        retained = basis['sources'].get(source['id'])
        if source['disposition'] == 'considered-not-used' and retained is not None:
            # Excluding an acquired source changes its application, and needs no
            # second acquisition of an original that may no longer be present.
            import authoring_work
            raw = authoring_work.source_bytes(retained)
        else:
            try:
                raw = reader.read(reader.select(source_path))
            except (OSError, ValueError) as error:
                raise ProductionError('INPUT_UNREADABLE', 'The selected source original cannot be read.',
                    phase='source-acquisition', file=source_row_path, pointer='/path',
                    cause='source-original-unreadable', source=source['id'], source_file=source_path,
                    detail=str(error), guidance=work.SOURCE_GUIDANCE,
                    repair_owner={'file': source_row_path, 'pointer': '/path'},
                    required_action='Select a readable Studio-relative source path in the descriptor, '
                        'then run acquire-source again. The previous draft is unchanged.') from error
        revised = work.acquire_source_row(basis, source, raw, file=source_row_path)
        projected, _, _ = work.project(revised, choices, Path(choices_path).parent.as_posix())
        return choices, revised, {
            'source': source['id'], 'source_row': source_row_path,
            'acquired': {'sha256': revised['sources'][source['id']]['sha256'], 'path': source_path},
            'projected_source': next((row for row in projected['authoring']['task']['sources']
                                      if row['id'] == source['id']), None),
            'applications': {key: copy.deepcopy(row) for key, row in revised['applications'].items()
                             if row['source'] == source['id']},
            'subjects': {key: [item for item in assigned
                              if revised['applications'][item]['source'] == source['id']]
                         for key, assigned in revised['subjects'].items()
                         if any(revised['applications'][item]['source'] == source['id'] for item in assigned)},
        }

    return update_draft(root, choices_path, transform, operation='acquire-source')
