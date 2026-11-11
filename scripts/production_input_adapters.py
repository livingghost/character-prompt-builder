"""Connect input choices to studio records and the active model catalog."""
from __future__ import annotations

import copy
from pathlib import Path

import execution_contract as c
import request_validation
import visual_continuity
from owned_json import mutable
from production_diagnostics import choice_required


def inventory(root: Path, task: dict) -> dict:
    import studio
    import adoption_workflow
    characters = []
    folder = root / 'characters'
    if folder.is_dir():
        for home in sorted(folder.iterdir()):
            if not home.is_dir():
                continue
            c.local(root, home.relative_to(root).as_posix())
            rows = studio.read_iterations(home)
            index = adoption_workflow.reference_index(root, home.name)
            characters.append({'studio_character': home.name,
                'iterations': [{key: row.get(key) for key in ('iteration_id', 'slot', 'status')}
                               for row in rows],
                'references': index['bindings'], 'reference_errors': index['errors']})
    return {'studio_characters': characters,
            'declared_sources': [{key: source.get(key) for key in ('id', 'role', 'path')}
                                 for source in task.get('sources', [])]}


def authority(root: Path, task: dict, saved: dict | None) -> dict:
    import production_store
    held = production_store.read_authority(root, task['task_id'], required=False)
    if held is not None:
        snapshot = production_store.authority_snapshot(root, task['task_id'], held,
                                                       source_path=task.get('authority'))
        value = snapshot['document']
        return {'present': True, 'path': snapshot['source_path'], 'issuer': value['issuer'],
                'grants': value['grants'], 'stop_conditions': value['stop_conditions'],
                'eligibility_evaluated': False, 'current': snapshot}
    path = task.get('authority')
    if not isinstance(path, str) or not c.local(root, path, exists=False).is_file():
        return {'present': False, 'path': path, 'eligibility_evaluated': False}
    value = c.load(c.local(root, path))
    import production_permissions
    from input_evidence import EvidenceAcquisition
    value = production_permissions.acquire(value, task['task_id'], EvidenceAcquisition(root))
    return {'present': True, 'path': path, 'issuer': value['issuer'],
            'grants': value['grants'], 'stop_conditions': value['stop_conditions'],
            'eligibility_evaluated': False}


def validation_required(task: dict) -> bool:
    """Upscaling takes request validation from an explicit input choice.

    Image preparation resolves observed schema evidence and requires a selected
    reference contract when images accompany the authored instructions.
    """
    return task.get('execution') == 'dispatcher' and task.get('route') == 'upscale'



def build_visual(choices: dict | None, task: dict, reader, root: Path) -> tuple[dict | None, dict]:
    if choices is None:
        return None, {}
    fields = {'purpose', 'basis', 'subjects', 'production_spec', 'prepared_reference_set'}
    c.exact(choices, fields, 'visual input choices')
    spec_ref = reader.select(choices['production_spec'])
    prepared_ref = reader.select(choices['prepared_reference_set'])
    spec = reader.json(spec_ref)
    prepared = reader.json(prepared_ref)
    from prepare_generation_references import validate_prepared_reference_set
    validate_prepared_reference_set(prepared, package_root=reader.resolve(prepared_ref['path']).parent)
    authored = {key: copy.deepcopy(choices[key]) for key in ('purpose', 'basis', 'subjects')}
    result = visual_continuity.build_record(authored, production_spec=spec, prepared=prepared, root=root)
    reader.basis(result['basis'])
    return result, {'model': prepared['target_model'], 'production_spec': spec_ref,
                    'prepared_reference_set': prepared_ref}


def build_validation(choices: dict | None, task: dict, reader, root: Path, *, target=None) -> tuple[dict | None, dict]:
    """Compile selected evidence for the target resolved by production authoring."""
    if choices is None:
        if validation_required(task):
            raise ValueError('this dispatcher production needs its request validation choice')
        return None, {}
    validation, _ = request_validation.acquire_target_choices(choices, target, reader)
    return mutable(validation.record), {'model': target.model_id, 'dialect': target.model.get('prompt_dialect')}


def cross_check(visual: dict, validation: dict) -> None:
    if visual and validation and visual['model'] is not None and visual['model'] != validation['model']:
        raise ValueError('prepared references and validation select different models')


def build_external(selection: dict, task: dict, reader, root: Path, out_dir: str,
                   delivery: bytes, *, derived_files: dict[str, bytes] | None = None) -> tuple[dict[str, bytes], dict]:
    """Delegate native request construction to its common editable input owner."""
    import production_external_inputs
    return production_external_inputs.build(selection, task, reader, root, out_dir, delivery,
                                            derived_files=derived_files)


def next_actions(inputs: dict, task: dict, root: Path, *, runtime_arguments: dict | None = None) -> list[dict]:
    """The commands that follow built inputs, in order.

    Prepare compiles the task and publishes its Generation Package, exact request
    and execution plan together. A dispatcher run then needs its decision file
    from draft-execution, and execute sends the one request the run owns.
    """
    workflow = 'scripts/production_workflow.py'
    requires = ['Complete the declared delivery, source and authority files.']
    actions = [{'operation': 'prepare', 'script': workflow,
                'args': {'root': str(root), 'task': inputs['production-task']['path'], **(runtime_arguments or {})},
                'external_effect': False, 'requires': requires}]
    if task.get('execution') not in {'dispatcher', 'external'}:
        return actions
    if task.get('route') == 'upscale' and 'delivery' not in inputs:
        actions.insert(0, {'operation': 'build-upscale-request', 'script': 'scripts/production_binding.py',
            'args': {'root': str(root), 'request-validation-file': str(root / inputs['request-validation']['path'])},
            'requires': ['Select source, model, scale, settings, and render-intent.',
                         'Write the declaration to the task delivery path before prepare.'],
            'external_effect': False})
    actions += [
        {'operation': 'draft-execution', 'script': workflow, 'args': {'root': str(root)},
         'required_args': ['run', 'grant', 'out'], 'external_effect': False},
        {'operation': 'execute', 'script': workflow, 'args': {'root': str(root)},
         'required_args': ['run', 'decisions-file'],
         'requires': ['Answer every decision in the file draft-execution wrote.'],
         'external_effect': task.get('execution') == 'dispatcher'},
    ]
    return actions


def add_runtime_arguments(parser) -> None:
    from pack_runtime_cli import add_pack_runtime_arguments
    add_pack_runtime_arguments(parser)


def configure_runtime(args, parser) -> dict:
    from pack_runtime_cli import resolve_pack_runtime
    from catalog_retrieval.runtime import configure_pack_runtime
    runtime = resolve_pack_runtime(parser, args)
    configure_pack_runtime(runtime.settings)
    return {'state-file': str(runtime.settings.state_file), 'cache-dir': str(runtime.settings.cache_dir),
            'managed-root': str(runtime.settings.managed_root), 'pack-root': [str(path) for path in runtime.pack_roots]}


def visual_template(task: dict) -> dict | None:
    if task.get('route') == 'upscale' and task.get('artifact') == 'image' and task.get('execution') == 'dispatcher':
        return None
    if task.get('artifact') not in {'image', 'video'} and task.get('route') not in {'generation', 'state-series', 'repose', 'character-sheet'}:
        return None
    return {'purpose': None, 'basis': {'path': None, 'locator': None},
            'subjects': None, 'production_spec': None, 'prepared_reference_set': None}


def validation_template(task: dict) -> dict | None:
    if task.get('execution') != 'dispatcher':
        return None
    return {'mode': 'target-schema', 'contract': None, 'evidence': None, 'execution_policy': None}


# What each field of a visual continuity choice holds; examples/input-assembly/README.md shows the choice.
VISUAL_FIELDS = {
    'purpose': '"image", or "sheet-panel" for a character sheet panel with exactly one production subject',
    'basis': '{"path": FILE, "locator": SECTION}: the Studio file that records the author\'s continuity '
             'decisions and the part of it that states them',
    'subjects': 'one entry per Production Specification subject ID, each {"continuity": DECISION, '
                '"character_id": ID or null, "studio_character": NAME or null, "identity_refs": '
                '[{"slot": SLOT, "iteration_id": ITERATION}]}',
    'production_spec': 'the Studio path of the Production Specification whose subjects these decisions cover',
    'prepared_reference_set': 'the Studio path of the prepared reference set that holds the identity references',
}
BASIS_FIELDS = {'path': 'the Studio file that records the author\'s continuity decisions',
                'locator': 'the part of that file that states the decisions'}
VISUAL_GUIDE = {'document_path': 'examples/input-assembly/README.md#visual-choices'}
VALIDATION_GUIDE = {'document_path': 'references/runtime/model-evidence.md#editable-selections-and-compiled-evidence'}


def unresolved_choices(choices: dict) -> list[dict]:
    """Describe unanswered selection fields without filling any authored value.

    The schema of the choices refuses a null validation mode, so validation
    reports only its contract and evidence selectors.
    """
    output = []
    visual = choices.get('visual')
    if isinstance(visual, dict):
        for key, value in VISUAL_FIELDS.items():
            if key in visual and visual[key] is None:
                output.append(choice_required('visual.' + key, 'selection-required',
                    'visual.' + key + ' is null, so the visual continuity choice cannot build its record.',
                    'Set visual.' + key + ' to ' + value + '.', VISUAL_GUIDE))
        basis = visual.get('basis')
        if isinstance(basis, dict):
            for key, value in BASIS_FIELDS.items():
                if not basis.get(key):
                    output.append(choice_required('visual.basis.' + key, 'source-selection-required',
                        'visual.basis.' + key + ' is empty, so the continuity decisions have no cited source.',
                        'Set visual.basis.' + key + ' to ' + value + '.', VISUAL_GUIDE))
    validation = choices.get('validation')
    if isinstance(validation, dict):
        mode = validation.get('mode')
        for key in ('contract', 'evidence'):
            other = 'evidence' if key == 'contract' else 'contract'
            if validation.get(key) is not None:
                continue
            if mode != 'target-schema':
                output.append(choice_required('validation.' + key, 'source-selection-required',
                    'validation.' + key + ' is null, and mode ' + str(mode) + ' needs its contract and evidence.',
                    'Set validation.' + key + ' to the Studio path or @pack/PACK_ID/PATH selector of the ' +
                    str(mode) + ' ' + key + ' file.', VALIDATION_GUIDE))
            elif validation.get(other) is not None:
                output.append(choice_required('validation.' + key, 'source-selection-required',
                    'validation.' + key + ' is null while validation.' + other + ' is selected.',
                    'Set validation.' + key + ' to the selector of the same schema contract as validation.' +
                    other + ' (an active offering schema uses @pack/PACK_ID/SCHEMA_SNAPSHOT in both), or set both '
                    'to null to use the selected offering\'s parameter schema.', VALIDATION_GUIDE))
    return output
