"""Connect input choices to studio records and the active model catalog."""
from __future__ import annotations

import copy
from pathlib import Path

import execution_contract as c
import request_contract
import request_validation
import visual_continuity
from execution_policy import load_policy


def check_series(before: dict, after: dict) -> None:
    if before.get('production_id') != after.get('production_id'):
        raise ValueError('source run belongs to a different production series')


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
    path = task.get('authority')
    if not isinstance(path, str) or not c.local(root, path, exists=False).is_file():
        return {'present': False, 'path': path, 'eligibility_evaluated': False}
    value = c.load(c.local(root, path))
    import production_permissions
    production_permissions.validate(value, task['task_id'])
    return {'present': True, 'path': path, 'issuer': value['issuer'],
            'grants': value['grants'], 'stop_conditions': value['stop_conditions'],
            'eligibility_evaluated': False}


def validation_required(task: dict) -> bool:
    """Whether request validation must come from an input choice.

    An upscale and bounded production context always take it from here. For an
    authored rendition, the Generation Package builder derives it from the observed
    schema, and a package with selected references takes a validation choice from here.
    The builder takes visual continuity as its own --continuity decisions.
    """
    return task.get('execution') == 'dispatcher' and (
        task.get('route') == 'upscale' or (task.get('delivery') or {}).get('transport') != 'authored-rendition')


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


def build_validation(choices: dict | None, task: dict, reader, root: Path) -> tuple[dict | None, dict]:
    if choices is None:
        if validation_required(task):
            raise ValueError('this dispatcher production needs its request validation choice')
        return None, {}
    c.exact(choices, {'mode', 'model', 'target', 'service_profiles', 'contract', 'evidence',
                      'execution_policy'}, 'validation input choices')
    target = request_contract.target(choices['target'])
    from prepare_generation_references import resolve_model_record
    from model_contract import select_offering
    from dispatch import load_transport
    model_id, model = resolve_model_record(choices['model'])
    if model_id != choices['model']:
        raise ValueError('select the canonical model ID displayed by the runtime catalog')
    offering = select_offering(model, target['service'] if model.get('offerings') else None)
    if offering is None:
        if target['model_identifier'] != model_id:
            raise ValueError('host target differs from the selected canonical model')
        import request_renderer as transport
    else:
        if offering['model_identifier'] != target['model_identifier']:
            raise ValueError('model identifier differs from the selected offering')
        transport = load_transport(target['service'])
    if choices['service_profiles'] is None:
        from catalog_retrieval.runtime import load_pack_catalog
        catalog = load_pack_catalog()
        resource = catalog.resources.get('service-profiles')
        if resource is None:
            raise ValueError('select a service-profiles source or activate its provider')
        name = '@pack/' + resource.source_pack
        if name not in reader.named_roots:
            raise ValueError('service provider has no active source root')
        relative = Path(resource.path).resolve().relative_to(reader.named_roots[name]).as_posix()
        service_ref = reader.select(name + '/' + relative)
    else:
        service_ref = reader.select(choices['service_profiles'])
    services = reader.json(service_ref).get('services')
    if not isinstance(services, dict) or target['service'] not in services:
        raise ValueError('service-profiles has no exact selected service')
    service = services[target['service']]
    if target['operation'] not in service.get('operations', {}):
        raise ValueError('the selected service does not declare this operation')
    selected = {key: choices[key] for key in ('mode', 'contract', 'evidence', 'execution_policy')}
    policy_ref = reader.select(choices['execution_policy']) if choices['execution_policy'] is not None else None
    policy, local = load_policy({'execution_policy': policy_ref}, reader, target, dialect=model.get('prompt_dialect'))
    reference = policy.get('reference_instruction_transport')
    if reference is not None:
        contract = local.json(reference['contract'])
        local.at(reference['contract']).basis(contract['basis'])
    execution = request_contract.execution_hashes(service, offering or {}, Path(transport.__file__), model=model, policy=policy)
    record = request_validation.build_record(selected, reader, expected_target=target, execution=execution)
    return record, {'model': model_id, 'dialect': model.get('prompt_dialect'),
                    'service_profiles': service_ref}


def cross_check(visual: dict, validation: dict) -> None:
    if visual and validation and visual['model'] is not None and visual['model'] != validation['model']:
        raise ValueError('prepared references and validation select different models')


STATE_BUILDER_FILES = ['state-lineage-file', 'species-profile-file', 'individual-morphology-file',
                       'identity-contract-file', 'state-snapshot-file', 'scene-context-file',
                       'visual-projection-file', 'asset-render-spec-file', 'references-file']


def next_actions(inputs: dict, task: dict, root: Path, *, runtime_arguments: dict | None = None) -> list[dict]:
    actions = [{'operation': 'prepare', 'script': 'scripts/production_workflow.py',
                'args': {'root': str(root), 'task': inputs['production-task']['path']},
                'external_effect': False, 'budget_effect': 'none',
                'requires': ['Complete the declared delivery, source and authority files.']}]
    if task.get('execution') != 'dispatcher':
        return actions
    if task.get('route') == 'upscale':
        actions.insert(0, {'operation': 'build-upscale-request', 'script': 'scripts/production_binding.py',
            'args': {'root': str(root), 'request-validation-file': str(root / inputs['request-validation']['path'])},
            'requires': ['Select source, model, scale and settings.',
                         'Write the declaration to the task delivery path before prepare.'],
            'external_effect': False, 'budget_effect': 'none'})
        return actions
    required = ['model', 'prompt-file', 'plot-file', 'retrieval-record-file', 'production-spec-file']
    script = 'scripts/build_generation_payload.py'
    if 'state-series' in [task.get('route'), *task.get('features', [])]:
        # A state-aware package has its own builder and artifact graph.
        script = 'scripts/build_state_generation_package.py'
        required += STATE_BUILDER_FILES
    if 'visual-continuity' not in inputs:
        required.append('continuity')
    required.append('out')
    actions.append({'operation': 'build-generation-payload', 'script': script,
                    'args': {**{key + '-file': str(root / inputs[key]['path']) for key in
                              ('visual-continuity', 'request-validation') if key in inputs},
                             'production-root': str(root), **(runtime_arguments or {})},
                    'required_args': required, 'external_effect': False, 'budget_effect': 'none'})
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
    return {'mode': None, 'model': None,
            'target': {'service': None, 'model_identifier': None, 'operation': None},
            'service_profiles': None, 'contract': None, 'evidence': None, 'execution_policy': None}


OPTIONAL_FIELDS = {'visual': set(), 'validation': {'service_profiles', 'execution_policy'}}


def unresolved_choices(choices: dict) -> list[dict]:
    """Describe unanswered selection fields without filling any authored value."""
    output = []
    for field in ('visual', 'validation'):
        value = choices.get(field)
        if not isinstance(value, dict):
            continue
        template = visual_template({'artifact': 'image', 'execution': 'dispatcher'}) if field == 'visual' else validation_template({'artifact': 'image', 'execution': 'dispatcher'})
        for key in template:
            if key in OPTIONAL_FIELDS[field]:
                continue
            if key in value and value[key] is None:
                output.append({'field': field + '.' + key, 'code': 'selection-required'})
        basis = value.get('basis')
        if isinstance(basis, dict):
            for key in ('path', 'locator'):
                if not basis.get(key):
                    output.append({'field': field + '.basis.' + key, 'code': 'source-selection-required'})
        target = value.get('target')
        if isinstance(target, dict):
            for key in ('service', 'model_identifier', 'operation'):
                if not target.get(key):
                    output.append({'field': field + '.target.' + key, 'code': 'target-selection-required'})
    return output
