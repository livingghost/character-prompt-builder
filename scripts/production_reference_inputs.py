"""Turn authored reference choices into one portable prepared reference set.

Source roles, subject assignments, exclusions and state eligibility stay with
their existing owners. This adapter derives file hashes, plan ordering, model
transports and board placement from those choices.
"""
from __future__ import annotations

import copy
from pathlib import Path
import tempfile
from typing import Any

import execution_contract as c
import prepare_generation_references as references


FIELDS = frozenset({'transport_mode', 'max_side', 'reference_use_plan',
    'reference_selection', 'additional_references', 'image_input', 'zero_reference_reason',
    'source_files'})
PLAN_ITEM_FIELDS = frozenset({'canonical_record_id', 'intended_influence', 'asset_id',
    'artifact_id', 'technical_role', 'source'})


def _image_plan(binding: dict) -> dict:
    import image_input
    image_input.validate_binding(binding)
    plan = {key: copy.deepcopy(value) for key, value in binding.items()
            if key not in image_input.DERIVED}
    plan['artifact_type'] = 'image-input-plan'
    external = plan.get('external_request')
    if external is not None:
        for name in ('request', 'schema_validation', 'prompt_check'):
            external.pop(name, None)
    return plan


def draft(prepared: dict | None, *, package_root: Path, root: Path | None = None,
          mirrored_input: bool = False) -> dict:
    """Expose choices from a saved set without carrying its generated layout.

    `mirrored_input` states that the task's image input was written from this
    set's own rows, so the choices select the mirrored image input again.
    """
    if prepared is None:
        prepared = references.empty_stateless_reference_set()
    prepared = references.validate_prepared_reference_set(prepared, package_root=package_root)
    mode = prepared['transport_mode']
    maximum = 1536
    raster_sizes = [row['transport']['derivation'].get('max_side')
                   for row in prepared['selected_references']]
    raster_sizes = [value for value in raster_sizes if type(value) is int]
    if raster_sizes:
        maximum = max(raster_sizes)
    if prepared['single_board'] is not None:
        _, board_path = references._resolve_packaged_file(prepared['single_board']['resolved_path'],
            'single_board.resolved_path', package_root=package_root)
        maximum = max(references.image_dimensions(board_path, 'image/png'))
    binding = prepared.get('image_input_binding')
    if binding is not None and binding.get('prepared_reference_set') is not None:
        # A binding to an existing set mirrors its existing source authority.
        # The originating set owns the editable choices, including any earlier
        # direct image-input scopes; never turn a pack or state source into an
        # unrestricted caller-supplied image.
        source = copy.deepcopy(binding['prepared_reference_set'])
        for old, current in zip(source['selected_references'], prepared['selected_references'], strict=True):
            old['transport']['resolved_path'] = current['transport']['resolved_path']
        if source.get('single_board') is not None:
            source['single_board']['resolved_path'] = prepared['single_board']['resolved_path']
        for old, current in zip(source.get('prompt_artifacts', []), prepared['prompt_artifacts'], strict=True):
            old['delivered_path'] = current['delivered_path']
        source = references.finalize_prepared_reference_set(source, package_root=package_root)
        result = draft(source, package_root=package_root, root=root)
        result.update(transport_mode=mode, max_side=maximum)
        if result['image_input'] is None:
            result['image_input'] = {'model': copy.deepcopy(binding['model'])}
            pairs = list(zip(source['selected_references'], binding['references'], strict=True))
            pack_pairs = [(row, selected) for row, selected in pairs if row['source']['kind'] == 'pack-artifact']
            if result['reference_use_plan'] is not None:
                for item, (_, selected) in zip(result['reference_use_plan']['items'], pack_pairs, strict=True):
                    item['id'] = selected['id']
            if result['reference_selection'] is not None:
                for item in result['reference_selection']['selected_references']:
                    matches = [selected for row, selected in pairs
                               if row.get('subject_id') == item['subject_id']
                               and row.get('binding_id') == item['binding_id']]
                    if len(matches) != 1:
                        raise ValueError('state reference has no unique image input identity')
                    item['id'] = matches[0]['id']
            direct_pairs = [(row, selected) for row, selected in pairs
                            if row['source']['kind'] != 'pack-artifact' and 'subject_id' not in row]
            for item, (_, selected) in zip(result['additional_references'], direct_pairs, strict=True):
                item['id'] = selected['id']
        return result
    plan = prepared['reference_use_plan']
    authored_plan = None
    if plan is not None:
        surface = copy.deepcopy(plan['surface_lighting_plan'])
        for field in ('artifact_type', 'plan_id', 'source_evidence_roles', 'surface_lighting_plan_sha256'):
            surface.pop(field, None)
        authored_plan = {
            'items': [{key: copy.deepcopy(value) for key, value in item.items()
                       if key in PLAN_ITEM_FIELDS or key == 'subject_uses'} for item in plan['reference_items']],
            'unavailable_record_uses': (copy.deepcopy(plan['selected_records']) if not plan['reference_items'] else []),
            'surface_lighting': surface,
        }
    state = copy.deepcopy(prepared['reference_selection'])
    if state is not None:
        state.pop('selection_sha256', None)
    direct = []
    if binding is None:
        for row in prepared['selected_references']:
            if row['source']['kind'] == 'pack-artifact' or 'subject_id' in row:
                continue
            direct.append({key: copy.deepcopy(row[key]) for key in ('role', 'source', 'subject_uses')
                           if key in row})
            if row.get('reference_id'):
                direct[-1]['id']=row['reference_id']
    result = {'transport_mode': mode if mode != 'none' else 'multi-image',
            'max_side': maximum, 'reference_use_plan': authored_plan,
            'reference_selection': state, 'additional_references': direct,
            'image_input': _image_plan(binding) if binding is not None else {} if mirrored_input else None,
            'zero_reference_reason': copy.deepcopy(prepared['zero_reference_reason']),
            'source_files': {}}
    # Supplied-file bytes are observations of a selected path, not an extra
    # authoring choice. Keep their original witnesses separate so selecting a
    # different file never asks the author to repair a generated checksum.
    sources = [row['source'] for row in prepared['selected_references']]
    if state is not None:
        sources.extend(row['source'] for row in state['selected_references'])
    if authored_plan is not None:
        sources.extend(row['source'] for row in authored_plan['items'])
    for source in sources:
        if source['kind'] == 'supplied-file':
            result['source_files'][source['resolved_path']] = {
                field: source[field] for field in ('sha256', 'media_type')}
    for row in _authored_rows(result):
        source = row.get('source')
        if source is not None and source['kind'] == 'supplied-file':
            source.pop('sha256', None)
            source.pop('media_type', None)
        if source is None and result['image_input'] is not None:
            row.pop('sha256', None)
    return result


def _source(source: Any, *, root: Path, reader=None, source_files: dict | None = None) -> dict:
    if not isinstance(source, dict):
        raise ValueError('reference source must be an object')
    result = copy.deepcopy(source)
    if result.get('kind') != 'supplied-file':
        # Pack and Studio declarations carry their own exact identity and
        # acceptance evidence. Their validators resolve and verify that owner.
        return references.validate_committed_source(result)
    required = {'kind', 'reference_id', 'resolved_path'}
    optional = {'sha256', 'media_type'}
    if not required <= set(result) or set(result) - required - optional:
        raise ValueError('supplied reference requires kind, reference_id and resolved_path')
    selected = c.text(result['resolved_path'], 'supplied reference path')
    if selected.startswith('@'):
        if reader is None:
            raise ValueError('named reference paths require the selected input reader')
        path = reader.resolve(selected)
    elif Path(selected).is_absolute():
        path = Path(selected).resolve(strict=True)
    else:
        path = c.local(root, selected)
    result['resolved_path'] = str(path)
    canonical = references._prepare_supplied_source(
        {key: result[key] for key in required}, 'supplied reference')
    for field in optional:
        if field in result and result[field] != canonical[field]:
            raise ValueError('retained reference source changed: ' + selected)
    witness = (source_files or {}).get(str(path))
    if witness is not None and any(canonical[field] != witness[field] for field in optional):
        raise ValueError('retained reference source changed: ' + selected)
    if reader is not None:
        if selected.startswith('@'):
            reader.read(reader.select(selected))
        else:
            try:
                relative = path.relative_to(root.resolve()).as_posix()
            except ValueError:
                pass
            else:
                reader.read(reader.select(relative))
    return canonical


def _direct(value: Any, *, root: Path, reader=None, source_files: dict | None = None) -> list[dict]:
    if not isinstance(value, list):
        raise ValueError('additional_references must be an ordered array')
    result = []
    for row in value:
        c.exact(row, {'role', 'source'} | (set(row) & {'id', 'subject_uses'}),
                'additional reference')
        selected = copy.deepcopy(row)
        if 'id' in selected:
            c.text(selected.pop('id'), 'reference id')
        source = _source(selected['source'], root=root, reader=reader, source_files=source_files)
        if source['kind'] == 'pack-artifact':
            raise ValueError('pack references belong to the explicit Reference Use Plan')
        # The direct preparation API measures new files. Verify retained source
        # pins above, then pass its authored selector rather than its output.
        selected['source'] = ({key: source[key] for key in references.SUPPLIED_SELECTION_FIELDS}
                              if source['kind'] == 'supplied-file' else source)
        result.append(selected)
    return result


def _selection(value: Any, *, root: Path, reader=None, source_files: dict | None = None) -> dict | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError('reference_selection must be an object or null')
    from state_protocol import finalize_artifact
    selected = copy.deepcopy(value)
    for row in selected.get('selected_references', []):
        if 'id' in row:
            c.text(row.pop('id'), 'reference id')
        row['source'] = _source(row['source'], root=root, reader=reader, source_files=source_files)
    # Coverage follows explicit state features and their declared covered sets.
    # No interpretation of image content or free text participates here.
    selected['unresolved_requirements'] = [
        {'subject_id': subject['subject_id'], 'feature': feature}
        for subject in selected.get('subjects', [])
        for feature in subject.get('required_state_features', [])
        if not any(row.get('subject_id') == subject['subject_id'] and feature in row.get('covers', [])
                   for row in selected.get('selected_references', []))]
    selected = finalize_artifact(selected)
    return references._validated_reference_selection(selected)


def _plan(value: Any, *, mode: str, model: str, zero_reason: dict | None,
          root: Path, reader=None, source_files: dict | None = None) -> dict | None:
    if value is None:
        return None
    c.exact(value, {'items', 'unavailable_record_uses', 'surface_lighting'}, 'reference plan choices')
    from reference_contract import build_reference_item, finalize_reference_use_plan, source_lighting_evidence_roles
    if not isinstance(value['items'], list):
        raise ValueError('reference plan items must be an ordered array')
    items = []
    selected = []
    for index, raw in enumerate(value['items']):
        c.exact(raw, set(PLAN_ITEM_FIELDS) | (set(raw) & {'id', 'subject_uses'}),
                'reference plan item')
        item = copy.deepcopy(raw)
        if 'id' in item:
            c.text(item.pop('id'), 'reference id')
        item['source'] = _source(item['source'], root=root, reader=reader, source_files=source_files)
        items.append(build_reference_item(precedence=index, **item))
        record = {'record_id': raw['canonical_record_id'], 'intended_influence': raw['intended_influence']}
        if 'subject_uses' in raw:
            record['subject_uses'] = copy.deepcopy(raw['subject_uses'])
        if record not in selected:
            selected.append(record)
    if items and value['unavailable_record_uses']:
        raise ValueError('unavailable record uses require an explicit resolution before model-facing preparation')
    if not items:
        selected = copy.deepcopy(value['unavailable_record_uses'])
        if not selected:
            return None
    surface = copy.deepcopy(value['surface_lighting'])
    if not isinstance(surface, dict):
        raise ValueError('surface_lighting must contain the authored lighting decisions')
    roles = source_lighting_evidence_roles(items)
    surface.update(artifact_type='surface-lighting-plan', source_evidence_roles=roles,
        plan_id='SLP-' + c.content_id({'surface': surface, 'source_evidence_roles': roles})[:20])
    plan = {'artifact_type': 'reference-use-plan', 'transport_mode': mode,
        'target_model': model if mode in {'multi-image', 'single-board'} else None,
        'selected_records': selected, 'reference_items': items, 'surface_lighting_plan': surface,
        'zero_reference_reason': None if items else copy.deepcopy(zero_reason)}
    plan['plan_id'] = 'RUP-' + c.content_id(plan)[:20]
    return finalize_reference_use_plan(plan)


def _authored_rows(choices: dict) -> list[dict]:
    """Follow the native source owners' compiled order without duplicating scopes."""
    native = choices['image_input']
    if native is not None and 'references' in native:
        return list(native['references'])
    result = list((choices['reference_use_plan'] or {}).get('items', []))
    result += [row for row in (choices['reference_selection'] or {}).get('selected_references', [])
               if row['source']['kind'] != 'pack-artifact']
    result += choices['additional_references']
    return result


def provisional_inputs(choices: dict, *, root: Path) -> dict | None:
    """The image-input rows that the selected sources will deliver, before any carrier exists.

    A draft's identity view reads these rows. An explicit image input names
    its own rows. A direct source takes the authority that preparation gives it
    from its role and subject uses. Plan and state rows keep their authority
    with those owners, so a selection that uses them has no provisional rows.
    """
    native = choices.get('image_input')
    if isinstance(native, dict) and isinstance(native.get('references'), list):
        return {'references': [{key: copy.deepcopy(row[key]) for key in
                                ('id', 'role', 'file', 'use_for', 'do_not_transfer', 'subject_uses') if key in row}
                               for row in native['references']]}
    if choices.get('reference_use_plan') is not None or choices.get('reference_selection') is not None:
        return None
    rows = []
    for row in choices.get('additional_references') or []:
        path = (row.get('source') or {}).get('resolved_path')
        if not isinstance(row.get('id'), str) or not isinstance(path, str) or path.startswith('@'):
            return None
        if Path(path).is_absolute():
            try:
                path = Path(path).resolve().relative_to(root.resolve()).as_posix()
            except ValueError:
                return None
        authority = references.direct_reference_authority(row['role'], row.get('subject_uses', []))
        rows.append({'id': row['id'], 'role': row['role'], 'file': path, 'use_for': authority['controls'],
                     'do_not_transfer': authority['must_not_control'],
                     **({'subject_uses': copy.deepcopy(row['subject_uses'])} if 'subject_uses' in row else {})})
    return {'references': rows}


def identify(choices: dict) -> bool:
    """Assign stable use identities at the editable selection boundary."""
    from pack_manager import generate_uuid7
    changed=False
    seen=set()
    for row in _authored_rows(choices):
        if not row.get('id'):
            source=row.get('source') or {}
            identifier=source.get('reference_id')
            if not identifier or identifier in seen:
                identifier='reference-'+generate_uuid7()
            row['id']=identifier
            changed=True
        if row['id'] in seen:
            raise ValueError('duplicate reference use id: '+row['id'])
        seen.add(row['id'])
        source=row.get('source')
        if source is not None and source.get('kind')=='supplied-file' and not source.get('reference_id'):
            source['reference_id']=row['id'];changed=True
    return changed


def identify_choices(choices: dict) -> bool:
    changed=False
    refs=(choices.get('authoring') or {}).get('references')
    if refs is not None:changed=identify(refs) or changed
    external=choices.get('external') or {}
    refs=(external.get('reference_delivery') or {}).get('choices')
    if refs is not None:changed=identify(refs) or changed
    plan=external.get('image_input')
    if isinstance(plan,dict):
        from pack_manager import generate_uuid7
        for row in plan.get('references',[]):
            if not row.get('id'):
                row['id']='reference-'+generate_uuid7();changed=True
    return changed


def _input_references(choices: dict, prepared: dict, *, publication_dir: str,
                      identity_field: str = 'id') -> list[dict]:
    authored_rows = _authored_rows(choices)
    if len(authored_rows) != len(prepared['selected_references']):
        raise ValueError('source choices differ from the compiled reference order')
    selected = []
    seen = set()
    for index, (choice, row) in enumerate(zip(authored_rows, prepared['selected_references'], strict=True)):
        identifier = choice.get(identity_field) or row.get('reference_id')
        if identifier is None:
            identifier = row['source'].get('reference_id') or row.get('binding_id')
            if identifier is None:
                raise ValueError('select the reference use before materializing its input')
            if identifier in seen:
                identifier += '-' + str(index + 1)
        identifier = c.text(identifier, 'reference id')
        if identifier in seen:
            raise ValueError('duplicate image input reference id: ' + identifier)
        seen.add(identifier)
        item = {'id': identifier, 'role': row['role'],
            'file': (Path(publication_dir) / 'references' / 'sources' / row['source']['sha256']).as_posix(),
            'sha256': row['source']['sha256'], 'use_for': copy.deepcopy(row['authority']['controls']),
            'do_not_transfer': copy.deepcopy(row['authority']['must_not_control'])}
        if 'subject_uses' in row:
            item['subject_uses'] = copy.deepcopy(row['subject_uses'])
        selected.append(item)
    return selected


def _input_plan(choices: dict, prepared: dict, *, publication_dir: str, model: str,
                root: Path, reader=None) -> dict:
    """Rebind the existing input identity to the current source choices."""
    import image_input
    wrapper = choices['image_input']
    c.exact(wrapper, {'model'}, 'existing image input model')
    declared = copy.deepcopy(wrapper['model'])
    image_input._model_contract(declared)
    if declared['catalog_model'] != model:
        raise ValueError('image input model differs from the selected reference target')
    evidence = declared['evidence']
    if reader is not None:
        reader.basis(evidence)
    elif c.sha256_file(c.local(root, evidence['path'])) != evidence['sha256']:
        raise ValueError('image input model evidence changed')
    selected = _input_references(choices, prepared, publication_dir=publication_dir)
    plan = {'artifact_type': 'image-input-plan', 'model': declared, 'references': selected,
        'prepared_references': (Path(publication_dir) / 'prepared-reference-set.json').as_posix(),
        'external_request': None}
    image_input._structure(plan)
    image_input._reference_rows(plan, prepared)
    return plan


def build(choices: dict, *, model: str, root: Path, output_dir: Path, reader=None,
          publication_dir: str | None = None, emit_image_input: bool = True) -> dict:
    """Build portable bytes in an unpublished directory; perform no generation."""
    c.exact(choices, set(FIELDS), 'reference input choices')
    identify(choices)
    source_files = choices['source_files']
    if not isinstance(source_files, dict):
        raise ValueError('reference source_files must contain original file witnesses')
    for path, witness in source_files.items():
        if not Path(c.text(path, 'reference witness path')).is_absolute():
            raise ValueError('reference source witnesses require their resolved original paths')
        c.exact(witness, {'sha256', 'media_type'}, 'reference source witness')
        c.sha(witness['sha256'])
        c.text(witness['media_type'], 'reference source media type')
    output_dir = Path(output_dir).resolve()
    if output_dir.exists() and (not output_dir.is_dir() or any(output_dir.iterdir())):
        raise ValueError('reference input output directory must be new or empty')
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    maximum = choices['max_side']
    if type(maximum) is not int or maximum < 1:
        raise ValueError('reference max_side must be a positive integer')
    mode = choices['transport_mode']
    if mode not in {'multi-image', 'single-board', 'prompt-artifacts', 'svg-bundle'}:
        raise ValueError('select a model-image or prompt-artifact reference transport')
    with tempfile.TemporaryDirectory(prefix='.reference-inputs-', dir=output_dir.parent) as temporary:
        work = Path(temporary)
        image_plan = copy.deepcopy(choices['image_input'])
        mirrored_input = isinstance(image_plan, dict) and set(image_plan) == {'model'}
        if image_plan is not None and not mirrored_input:
            if choices['reference_use_plan'] is not None or choices['reference_selection'] is not None or choices['additional_references']:
                raise ValueError('image_input owns its ordered reference sources; edit that plan without duplicate selections')
            if mode not in {'multi-image', 'single-board'}:
                raise ValueError('image_input requires model-facing reference transport')
            if not isinstance(image_plan, dict) or image_plan.get('external_request') is not None:
                raise ValueError('reference image_input choices require a dispatcher image input plan')
            if image_plan.get('references') == []:
                # The editable selection can become empty. Its generated
                # counterpart is the canonical no-reference set, not an empty
                # image-input plan that would claim an image operation.
                prepared = references.empty_stateless_reference_set(zero_reference_reason=choices['zero_reference_reason'])
            else:
                for row in image_plan['references']:
                    source = {'kind': 'supplied-file', 'reference_id': row['id'], 'resolved_path': row['file']}
                    if 'sha256' in row:
                        source['sha256'] = row['sha256']
                    measured = _source(source, root=root, reader=reader, source_files=source_files)
                    row['sha256'] = measured['sha256']
                prepared = references.prepare_image_input_references(image_plan, studio=root, model=model,
                    output_dir=work / 'prepared', max_side=maximum, transport_mode=mode)
            source_root = work
        else:
            direct = _direct(choices['additional_references'], root=root, reader=reader, source_files=source_files)
            state = _selection(choices['reference_selection'], root=root, reader=reader, source_files=source_files)
            plan = _plan(choices['reference_use_plan'], mode=mode, model=model,
                zero_reason=choices['zero_reference_reason'], root=root, reader=reader, source_files=source_files)
            if plan is not None:
                from reference_runtime import execute_reference_use_plan
                prepared = execute_reference_use_plan(plan, output_dir=work / 'prepared',
                    reference_selection=state, additional_references=direct, max_side=maximum)
                source_root = work / 'prepared'
            elif mode in {'prompt-artifacts', 'svg-bundle'}:
                if direct or state is not None:
                    raise ValueError('prompt artifacts require an explicit catalog reference plan')
                prepared = references.empty_stateless_reference_set(zero_reference_reason=choices['zero_reference_reason'])
                source_root = work
            else:
                prepared = references.prepare_references(direct, model=model, output_dir=work / 'prepared',
                    max_side=maximum, transport_mode=mode, reference_selection=state)
                source_root = work
                if not prepared['selected_references'] and choices['zero_reference_reason'] is not None:
                    prepared = references.build_prepared_reference_set(transport_mode='none', target_model=None,
                        reference_selection=state, zero_reference_reason=choices['zero_reference_reason'])
        rows=_authored_rows(choices)
        if len(rows)!=len(prepared['selected_references']):
            raise ValueError('selected reference uses differ from prepared sources')
        for choice,row in zip(rows,prepared['selected_references'],strict=True):
            row['reference_id']=choice['id']
        prepared=references.finalize_prepared_reference_set(prepared,package_root=source_root)
        from build_generation_payload import materialize_cli_reference_bundle
        staged = work / 'output'
        staged.mkdir()
        portable, _ = materialize_cli_reference_bundle(prepared, model=model, source_root=source_root,
            staging_root=staged, companion_name='references')
        references.write_json_atomic(staged / 'prepared-reference-set.json', portable)
        if emit_image_input and image_plan is not None and portable['selected_references']:
            if mirrored_input:
                if publication_dir is None:
                    try:
                        publication_dir = output_dir.relative_to(root.resolve()).as_posix()
                    except ValueError as exc:
                        raise ValueError('a staged image input requires its final Studio-relative publication_dir') from exc
                c.local(root, publication_dir, exists=False)
                image_plan = _input_plan(choices, portable, publication_dir=publication_dir,
                    model=model, root=root, reader=reader)
            references.write_json_atomic(staged / 'image-input.json', image_plan)
        references.validate_prepared_reference_set(portable, model=model, package_root=staged)
        import os
        if output_dir.exists():
            output_dir.rmdir()
        os.replace(staged, output_dir)
    return references.validate_prepared_reference_set(portable, model=model, package_root=output_dir)


def draft_external(plan: dict, prepared: dict, *, package_root: Path,
                   root: Path | None = None) -> dict:
    """Keep canonical source choices separate from an external upload's evidence.

    The preparation target belongs to the saved reference set. It does not
    select or change the external request's model or provider. Delivery IDs
    identify those logical references without replacing native source IDs.
    """
    import image_input
    prepared = references.validate_prepared_reference_set(prepared, package_root=package_root)
    if prepared['transport_mode'] not in {'none', 'multi-image', 'single-board'}:
        raise ValueError('external image inputs require model-facing prepared references')
    image_input._reference_rows(plan, prepared, require_hash=False)
    choices = draft(prepared, package_root=package_root, root=root)
    authored_rows = _authored_rows(choices)
    if len(authored_rows) != len(plan['references']):
        raise ValueError('canonical source choices differ from the external reference order')
    for row, reference in zip(authored_rows, plan['references'], strict=True):
        row['delivery_id'] = c.text(reference['id'], 'external reference id')
    target = prepared['target_model']
    if target is None and prepared['reference_use_plan'] is not None:
        target = prepared['reference_use_plan']['target_model']
    if target is None and not authored_rows:
        target = (plan.get('model') or {}).get('catalog_model')
    return {'target_model': target, 'choices': choices}


def build_external(selection: dict, *, root: Path, output_dir: Path,
                   publication_dir: str, reader=None) -> dict:
    """Rebuild canonical sources and expose the exact bytes an upload must send.

    The external owner supplies actual uploaded values and evidence after this
    local preparation. This function neither manufactures those facts nor
    substitutes caller-supplied provenance for an accepted canonical source.
    """
    c.exact(selection, {'target_model', 'choices'}, 'external reference delivery')
    c.exact(selection['choices'], set(FIELDS), 'external canonical reference choices')
    c.local(root, publication_dir, exists=False)
    choices = copy.deepcopy(selection['choices'])
    authored_rows = _authored_rows(choices)
    for row in authored_rows:
        if 'delivery_id' in row:
            c.text(row.pop('delivery_id'), 'external reference id')
    target = selection['target_model']
    if target is not None:
        c.text(target, 'canonical reference preparation model')
    elif authored_rows:
        raise ValueError('canonical reference preparation requires its selected target_model')
    if choices['transport_mode'] not in {'multi-image', 'single-board'}:
        raise ValueError('external image inputs require model-facing reference transport')
    prepared = build(choices, model=target or '', root=root, output_dir=output_dir,
        reader=reader, publication_dir=publication_dir, emit_image_input=False)
    rows = _input_references(selection['choices'], prepared, publication_dir=publication_dir,
                             identity_field='delivery_id')
    carriers = []
    for reference, selected in zip(rows, prepared['selected_references'], strict=True):
        carrier = prepared['single_board'] if prepared['transport_mode'] == 'single-board' else selected['transport']
        stored_path = Path(carrier['resolved_path'])
        if stored_path.is_absolute():
            raise ValueError('a rebuilt external reference carrier must use its portable output path')
        carriers.append({'reference': reference['id'],
            'path': (Path(publication_dir) / stored_path).as_posix(),
            'sha256': carrier['sha256'], 'media_type': carrier['media_type']})
    return {'prepared': prepared, 'references': rows, 'carriers': carriers}
