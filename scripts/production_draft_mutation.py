"""Publish a current candidate only after its registered source boundary passes.

Source acquisition and structured choices edits share the choices/basis locks,
one acquired byte view and the same rollback owner. A rejected candidate can be
continued explicitly from its immutable input snapshot.
"""
from __future__ import annotations

import copy
from pathlib import Path

import execution_contract as c
import production_authoring as authoring
import production_authoring_state as state
import production_authoring_work as work
from cli_invocation import python_argv, shown
from input_evidence import InputEvidence
from production_diagnostics import ProductionError


def update_draft(root: Path, choices_path: str, transform, *, operation: str = 'edit-choices') -> dict:
    """Transform acquired choices and basis in memory, then publish together.

    ``transform(choices, basis, reader)`` returns the proposed choices and basis,
    optionally followed by public result fields. It must not write files. The
    reader captures every selected local input used by the transformation.
    """
    import production_identity
    import production_identity_boundary as boundary
    import production_inputs
    from production_source_acquisition import _publish

    root = c._root(root)
    choices_file = c.local(root, choices_path)
    folder = Path(choices_path).parent.as_posix()
    context_path = (Path(folder) / 'context.json').as_posix()
    with c.file_lock(choices_file):
        choices_raw = c.read(choices_file)
        choices = production_inputs.read_choices(c.decode(choices_raw), file=choices_path, root=root)
        context_file = c.local(root, context_path, exists=False)
        context_raw = c.read(context_file) if context_file.is_file() else b''
        task_id = choices['authoring']['task']['task_id']
        state.require_input_context(root, task_id, folder, context_raw)
        context = c.decode(context_raw)
        selected_work = context['authoring_work']
        if selected_work['content'] != choices_path:
            raise ProductionError('AUTHORING_WORK_MISMATCH',
                'The registered authoring work identifies another actual candidate.',
                phase='authoring-context', file=context_path, pointer='/authoring_work/content',
                expected=choices_path, actual=selected_work['content'],
                required_action='Select the choices file named by the registered authoring work.')
        basis_path = selected_work['basis']
        basis_file = c.local(root, basis_path)
        with c.file_lock(basis_file):
            basis_raw = c.read(basis_file)
            basis = c.decode(basis_raw)
            reader = InputEvidence(root)
            proposed = transform(copy.deepcopy(choices), copy.deepcopy(basis), reader)
            if not isinstance(proposed, tuple) or len(proposed) not in {2, 3}:
                raise TypeError('a draft transform must return choices, basis and optional result fields')
            selected, revised = proposed[:2]
            extra = proposed[2] if len(proposed) == 3 else {}
            import production_reference_inputs
            production_reference_inputs.identify_choices(selected)
            resolved = copy.deepcopy(selected)
            resolved['authoring'], _, document_gaps = authoring.read_editable(resolved['authoring'], reader)
            if not any(row['field'] == 'authoring.documents.production_spec' for row in document_gaps):
                revised = work.bind_task_subjects(revised, resolved)
            projected, files, _ = work.project(revised, selected, folder)
            staged = {(Path(folder) / name).as_posix(): raw for name, raw in files.items()}
            reader.add_derived(staged)
            resolved['authoring']['task'] = copy.deepcopy(projected['authoring']['task'])
            observed = {}

            def read(path: str) -> bytes:
                if path in staged:
                    return staged[path]
                if Path(path).is_absolute():
                    from production_store import stable_bytes
                    selected_path = Path(path)
                    raw = stable_bytes(selected_path.parent, selected_path.name)
                else:
                    raw = reader.read(reader.select(path))
                if path in observed and observed[path] != raw:
                    raise ValueError('selected identity evidence changed during acquisition: ' + path)
                observed[path] = raw
                return raw

            task = production_inputs._chosen_task(context['task_content'], resolved)
            snapshot = production_identity.source_snapshot(task, read, choices=projected, basis=revised)
            from production_saved_inputs import identity_context
            retained_context = identity_context(root, context)
            try:
                boundary.require_unchanged(retained_context, revised, snapshot, file=context_path)
            except ProductionError as error:
                if state.identity_repairable(error):
                    from production_candidate_snapshot import preserve_proposal
                    captured = {name: reader._decode(item) for name, item in reader.snapshots.items()}
                    proposal = preserve_proposal(root, choices_path, choices=projected, basis=revised,
                        files={**captured, **observed, **staged}, details={'operation': operation,
                            'changes': copy.deepcopy(error.diagnostic.details.get('changes', [])),
                            'unresolved': copy.deepcopy(error.diagnostic.details.get('unresolved', []))})
                    state.attach_identity_repair(root, choices_path, error,
                        proposal_choices_path=proposal['choices_file'])
                raise
            diagnostics = work.projection_diagnostics(revised, selected, projected=projected,
                root=root, choices_path=choices_path, basis_path=basis_path)
            gaps = [*document_gaps, *diagnostics, *work.unresolved(revised, resolved,
                require_subject=work.requires_subject(projected['authoring']['task']),
                root=root, choices_path=choices_path, basis_path=basis_path)]
            predecessors = {basis_path: basis_raw, choices_path: choices_raw, context_path: context_raw}
            for name, acquired in reader.snapshots.items():
                if name not in staged and not name.startswith('@'):
                    predecessors.setdefault(name, reader._decode(acquired))
            for name, raw in observed.items():
                if name not in staged and not name.startswith('@'):
                    predecessors.setdefault(name, raw)
            replacements = {basis_path: c.encoded(revised), choices_path: c.encoded(projected)}
            changed = _publish(root, predecessors=predecessors, replacements=replacements,
                               sources=staged, operation=operation)
    inspect_argv = python_argv(Path(__file__).with_name('production_workflow.py'), 'inspect-inputs',
        '--root', str(root), '--choices', choices_path)
    return {'ok': True, 'state': 'choices-edited' if operation == 'edit-choices' else 'source-acquired',
        'changed': changed, 'choices_file': choices_path, 'basis_file': basis_path, 'unresolved': gaps,
        'next_actions': [{'command': 'inspect-inputs', 'argv': inspect_argv, 'shown': shown(inspect_argv),
            'reason': 'Inspect the current draft and continue its remaining authored choices.'}],
        'external_effect': False, **extra}
