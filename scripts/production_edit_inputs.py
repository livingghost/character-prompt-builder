"""Start an instruction edit of an adopted Studio image as ordinary editable choices.

The adopted slot supplies its exact Studio source with its adoption evidence.
The Production run that produced the image supplies its Production
Specification, controls and validation selection where they still apply. The
author decides what changes, what stays, the instruction text, the criteria and
where the result is recorded; those choices stay unanswered in the draft, and
the ordinary draft report names each one.
"""
from __future__ import annotations

import copy
from pathlib import Path, PurePosixPath

import execution_contract as c
from production_diagnostics import ProductionError

FEATURES = ('semantic-instruction-edit', 'instruction-edit')
# The reference and task-source ID of the adopted image in the draft.
SOURCE_ID = 'edit-source'
PLAN_FILE = 'edit-plan.json'
GUIDE = {'document_path': 'references/runtime/semantic-instruction-edit.md#start-from-the-adopted-image'}
STEPS = ['Prepare the requested edit of the adopted image.', 'Assess the edited image against its edit plan.']
DRAFT = ('scripts/production_workflow.py draft-inputs --root STUDIO --route generation --execution dispatcher '
         '(or external) --edit-character CHARACTER --edit-slot SLOT --out-dir NEW_DIRECTORY')


def _refuse(message: str, required_action: str, **details) -> ProductionError:
    return ProductionError('INPUT_CONSISTENCY_ERROR', message, phase='authoring', guidance=GUIDE,
                           required_action=required_action, **details)


def require_arguments(*, character: str | None, slot: str | None, initial: bool, route: str | None,
                      artifact: str | None, execution: str | None, upscale: dict) -> None:
    """Refuse a selector combination that does not start one edit draft."""
    if character is None or slot is None:
        raise _refuse('An adopted image is selected by its Studio character and slot together.',
                      'Give both --edit-character and --edit-slot: ' + DRAFT + '.')
    if not initial:
        raise _refuse('An edit of an adopted image starts a new draft; --task and --from-run reopen existing work.',
                      'Omit --task and --from-run: ' + DRAFT + '. To revise an earlier edit, reopen its run with '
                      'draft-inputs --from-run RUN instead.')
    if route != 'generation':
        raise _refuse('An edit of an adopted image uses the generation route.',
                      'Select --route generation: ' + DRAFT + '.', route=route)
    if execution not in {'dispatcher', 'external'}:
        raise _refuse('An edit of an adopted image needs its execution kind.',
                      'Add --execution dispatcher for a catalog offering that this Studio sends, or --execution '
                      'external for a host call that the agent performs and records: ' + DRAFT + '.',
                      execution=execution)
    if artifact not in {None, 'image'}:
        raise _refuse('An edit of an adopted image produces an image.', 'Omit --artifact or select --artifact image.',
                      artifact=artifact)
    chosen = sorted(name for name, value in upscale.items() if value is not None)
    if chosen:
        raise _refuse('--' + ', --'.join(chosen) + ' select a dispatcher upscale, not an edit.',
                      'Omit ' + ', '.join('--' + name for name in chosen) + ' from the edit draft. An enlargement '
                      'of the adopted image is a separate draft with --route upscale.', options=chosen)


def select(root: Path, character: str, slot: str) -> dict:
    """The adopted image: its Studio source, identity adoption and producing Production run."""
    import sheet_artifacts as fills
    import studio_reference
    try:
        source = studio_reference.current_source(root, character, slot)
        proof = studio_reference.validate_source(source)
    except ProductionError:
        raise
    except (ValueError, OSError, KeyError, TypeError) as exc:
        raise ProductionError('INPUT_CONSISTENCY_ERROR', 'Studio character ' + str(character) + ', slot ' +
            str(slot) + ' has no current adopted image to edit: ' + str(exc), phase='authoring',
            guidance={'document_path': 'references/runtime/studio-canon-references.md#choose-the-current-source-and-its-influence'},
            required_action='Select a character and slot whose current artwork is accepted; '
                'scripts/studio.py status --studio STUDIO lists each character\'s slots and their accepted images. '
                'Accept or adopt the intended image through its own workflow before editing it.',
            character=character, slot=slot) from exc
    sheet_root = root / PurePosixPath(source['sheet']).parent
    provenance = fills.verify_artifact(proof['acceptance']['artifact'], sheet_root)
    origin = provenance.get('origin') or {}
    try:
        path = Path(source['resolved_path']).resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise _refuse('The adopted image lies outside this Studio: ' + source['resolved_path'] + '.',
                      'Run draft-inputs with --root naming the Studio that holds the adopted image.') from exc
    return {'character': character, 'slot': slot, 'source': source, 'path': path,
            'identity': copy.deepcopy(proof.get('identity')),
            'origin': ({'run': origin['run'], 'candidate': origin.get('candidate')}
                       if origin.get('kind') == 'production' and origin.get('run') else None)}


def features(edit: dict, selected: list[str] | None) -> list[str]:
    """The edit features, then the identity contract for an identity adoption, then the author's own."""
    result = list(FEATURES)
    if edit['identity'] is not None:
        result.append('recurring-identity')
    for name in selected or []:
        if name not in result:
            result.append(name)
    return result


def _origin(root: Path, edit: dict, reader) -> dict:
    """The applicable documents and controls of the run that produced the adopted image."""
    import production_authoring as authoring
    import production_inputs
    empty = {'task': None, 'saved': None, 'production_spec': None, 'parameters': None, 'model': None,
             'service': None}
    if edit['origin'] is None:
        return empty
    saved = production_inputs._source_run(root, edit['origin']['run'])
    task = saved['task']
    generation = task.get('generation') or {}
    result = {**empty, 'task': task, 'saved': saved}
    for field in ('production_spec', 'parameters'):
        if generation.get(field):
            result[field] = c.decode(authoring.source_bytes(root, generation[field], reader, saved))
    specification = result['production_spec']
    result['model'] = generation.get('model') or (specification or {}).get('target_model')
    result['service'] = generation.get('service')
    return result


def _specification(value: dict | None) -> dict | None:
    """The source depiction, now performed as an instruction edit.

    A rendering declaration stays an explicit choice. Its prompt spans bound the
    earlier prompt, so each becomes unanswered until the edit instruction states it.
    """
    if value is None:
        return None
    result = copy.deepcopy(value)
    intent = result['render_intent']
    intent['execution_mode'] = 'instruction-edit'
    if 'prompt_expression' in intent:
        intent['prompt_expression'] = None
        for row in intent.get('regional_overrides') or []:
            row['prompt_expression'] = None
    return result


def _subject(edit: dict, origin: dict) -> str | None:
    """The Production Specification subject that the adopted character is, when the run states it."""
    specification = origin['production_spec']
    if specification is None:
        return edit['character'] if edit['identity'] is not None else None
    subjects = [row['id'] for row in specification.get('subjects', [])]
    mapped = [subject for subject, character in
              ((origin['task'] or {}).get('recording') or {}).get('subject_map', {}).items()
              if character == edit['character'] and subject in subjects]
    if len(mapped) == 1:
        return mapped[0]
    return subjects[0] if len(subjects) == 1 else None


def reference_choices(edit: dict, subject: str | None) -> dict:
    """The adopted image as the scene reference, with the identity use its adoption grants."""
    row = {'id': SOURCE_ID, 'role': 'scene', 'source': copy.deepcopy(edit['source'])}
    if edit['identity'] is not None and subject is not None:
        row['subject_uses'] = [{'subject_id': subject, 'use': 'identity', 'priority': 0}]
    return {'transport_mode': 'multi-image', 'max_side': 1536, 'reference_use_plan': None,
            'reference_selection': None, 'additional_references': [row], 'image_input': None,
            'zero_reference_reason': None, 'source_files': {}}


def plan_template() -> dict:
    """The editable edit plan: its source and required role, with the author's choices unanswered."""
    return {'artifact_type': 'semantic-edit-plan', 'source': SOURCE_ID,
            'edit': {'target': None, 'change': None, 'preserve': None, 'required_reference_roles': ['scene']},
            'review_criteria': None}


def apply(root: Path, edit: dict, choices: dict, task: dict, out_dir: str, *, reader) -> dict[str, bytes]:
    """Prefill one initial draft for the edit and return its editable plan file."""
    import production_inputs
    authored = choices['authoring']
    owned = authored['task']
    dispatcher = task['execution'] == 'dispatcher'
    origin = _origin(root, edit, reader)
    edit['origin_target'] = {'model': origin['model'], 'service': origin['service']}
    subject = _subject(edit, origin)
    owned['sources'] = [{'id': SOURCE_ID, 'path': edit['path'], 'role': 'accepted-source',
        'disposition': 'applied', 'locator': 'whole image',
        'reason': 'The accepted ' + edit['slot'] + ' image of Studio character ' + edit['character'] +
                  ', selected as the image to edit.'}]
    specification = _specification(origin['production_spec'])
    if specification is not None:
        authored['documents']['production_spec'] = specification
    references = reference_choices(edit, subject)
    if dispatcher:
        generation = authored['generation']
        generation.update(model=origin['model'], service=origin['service'])
        if specification is None:
            generation['render_intent'] = {'artifact_type': 'render-intent', 'execution_mode': 'instruction-edit'}
        if origin['parameters'] is not None:
            authored['documents']['parameters'] = copy.deepcopy(origin['parameters'])
        identity = edit['identity'] or {}
        if subject is not None and identity.get('continuity') in {'recurring', 'one-off', 'undecided'}:
            generation['continuity'] = {subject: identity['continuity']}
        owned['recording'] = {'character': edit['character'], 'slot': None,
            'subject_map': {subject: edit['character']} if subject is not None else {},
            'sheet_panel': None, 'role': None}
        # The mirrored image input: the prepared Studio source supplies its rows.
        references['image_input'] = {}
        authored['references'] = references
        if origin['task'] is not None and origin['task'].get('execution') == 'dispatcher':
            choices['validation'] = production_inputs._validation_choices(
                root, origin['task'], reader, origin['saved'])
    else:
        import production_external_inputs
        external = production_external_inputs.template()
        external['image_input'] = {'artifact_type': 'image-input-plan', 'references': [{'id': SOURCE_ID}],
                                   'external_request': None}
        external['reference_delivery'] = {'target_model': None, 'choices': references}
        choices['external'] = external
    path = (Path(out_dir) / PLAN_FILE).as_posix()
    choices['task_changes']['semantic_edit'] = path
    return {PLAN_FILE: c.encoded(plan_template())}


def reopen(root: Path, task: dict, choices: dict, out_dir: str, *, reader, saved: dict | None) -> dict[str, bytes]:
    """A reopened edit task or run keeps its edit plan as an editable file of the new draft."""
    import production_authoring as authoring
    path = task.get('semantic_edit')
    if not isinstance(path, str) or choices.get('authoring') is None:
        return {}
    raw = authoring.source_bytes(root, path, reader, saved)
    choices['authoring']['task'].pop('semantic_edit', None)
    choices['task_changes']['semantic_edit'] = (Path(out_dir) / PLAN_FILE).as_posix()
    return {PLAN_FILE: raw}


def report(edit: dict) -> dict:
    """The selected adopted image and the run it came from, as the draft reports them."""
    return {'character': edit['character'], 'slot': edit['slot'], 'path': edit['path'],
            'source': copy.deepcopy(edit['source']), 'origin': copy.deepcopy(edit['origin']),
            'identity': copy.deepcopy(edit['identity'])}


def target(edit: dict) -> dict | None:
    """The catalog model and service of the run that produced the image, when it named them."""
    selected = edit.get('origin_target') or {}
    if not selected.get('model'):
        return None
    return {'kind': 'catalog', 'model': selected['model'], 'service': selected.get('service')}
