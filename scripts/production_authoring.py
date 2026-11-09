"""One editable source for authored production content and its derived files.

This layer retains decisions and delegates reference, retrieval and upscale
contracts to their existing owners. It never creates grants or execution
receipts. Original task identity and approval scope remain independently owned.
"""
from __future__ import annotations

import copy
from pathlib import Path
import tempfile

import execution_contract as c

DOCUMENTS = frozenset({'parameters', 'production_spec', 'plot', 'retrieval_record',
    'creative_intent', 'negative', 'integrated_prompt', 'native_negative',
    'negative_provenance', 'state_lineage', 'state_snapshot', 'state_graphs',
    'visual_continuity', 'mask_binding'})
TEXT_DOCUMENTS = frozenset({'negative', 'integrated_prompt', 'native_negative'})
TEXT_SOURCE_SUFFIXES = frozenset({'.md', '.txt', '.json', '.yaml', '.yml', '.csv', '.tsv'})
GENERATED_TASK_FIELDS = frozenset({'delivery', 'generation', 'route_reading', 'image_input', 'authored_basis'})
AUTHORING_SPACES = frozenset({'studio', 'task-source'})


class UnresolvedChoice(ValueError):
    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field


def seed(root: Path, *, route: str, artifact: str, execution: str,
         task_id: str | None = None, features: list[str] | None = None) -> dict:
    import production_authoring_state
    import execution_routes
    from pack_manager import generate_uuid7
    task_id = task_id or production_authoring_state.active_task_id(root)
    if task_id is None:
        raise ValueError('start the work task or select --task-id before drafting production inputs')
    features = features or []
    execution_routes.resolve(route, features, execution=execution)
    return {'task_id': task_id, 'production_id': generate_uuid7(), 'route': route,
        'features': features, 'artifact': artifact, 'execution': execution,
        'sources': [], 'delivery': {'path': 'delivery.txt', 'translation_notes': None},
        'criteria': [], 'world_views': [], 'direction': {'purpose': None,
        'intended_effect': None, 'basis': [], 'decisions': [], 'action_slice': None,
        'limitations': []}, 'authority': None, 'route_reading': 'route-reading.json'}


def source_bytes(root: Path, path: str, reader, saved: dict | None = None) -> bytes:
    """Use the captured run object for authored content, independent of live edits."""
    if saved is not None:
        import production_workflow
        directory, prepared, _, _ = production_workflow.read_run(root, saved['run'])
        if prepared['input_sha256'] != saved['input_sha256']:
            raise ValueError('source run changed during authoring extraction')
        rows = [row for row in prepared['dependencies']
                if row['space'] in AUTHORING_SPACES and row['path'] == path]
        if len(rows) == 1:
            return c.object_read(directory, rows[0]['sha256'])
        raise ValueError('source run has no unique captured authoring document: ' + path)
    return reader.read(reader.select(path))


def _plot_choice(value: dict) -> dict:
    value = copy.deepcopy(value)
    if isinstance(value.get('approved'), dict):
        value['approved'].pop('content_sha256', None)
    return value


def draft(root: Path, task: dict, reader, *, saved: dict | None = None,
          initial: bool = False) -> dict:
    authored_task = {key: copy.deepcopy(value) for key, value in task.items()
                     if key not in GENERATED_TASK_FIELDS and key != 'execution_decisions'}
    documents = {}
    generation = task.get('generation') or {}
    for field in DOCUMENTS:
        path = generation.get(field)
        if path:
            raw = source_bytes(root, path, reader, saved)
            value = raw.decode('utf-8') if field in TEXT_DOCUMENTS else c.decode(raw)
            if field == 'plot':
                value = _plot_choice(value)
            if field == 'visual_continuity':
                value = copy.deepcopy(value)
                value['basis'].pop('sha256', None)
                for subject in value['subjects'].values():
                    for selected in subject['identity_refs']:
                        selected.pop('source_sha256', None)
                        selected.pop('reference_number', None)
            if field == 'retrieval_record':
                value = copy.deepcopy(value)
                value.pop('context', None)
                value.pop('settled', None)
            documents[field] = value
    content = None if initial else source_bytes(root, task['delivery']['path'], reader, saved).decode('utf-8')
    upscale = None
    if task.get('route') == 'upscale' and task.get('execution') == 'dispatcher' and content is not None:
        value = c.decode(content.encode('utf-8'))
        if value.get('artifact_type') == 'upscale-request':
            upscale = {key: copy.deepcopy(value[key]) for key in
                       ('model', 'scale_factor', 'settings', 'guidance_prompt', 'render_intent')}
            upscale['source'] = value['source']['path']
            content = None
    references = None
    if task.get('execution') == 'dispatcher' and task.get('route') != 'upscale':
        import production_reference_inputs
        path = generation.get('references')
        prepared = c.decode(source_bytes(root, path, reader, saved)) if path else None
        package_root = c.local(root, path, exists=False).parent if path else root
        references = production_reference_inputs.draft(prepared, package_root=package_root, root=root)
    sources = {}
    owned_paths = {task['delivery']['path'], *(generation.get(key) for key in DOCUMENTS), generation.get('references'), generation.get('request_validation')}
    if not initial:
        for source in task.get('sources', []):
            path = source['path']
            if source.get('identity') or path in owned_paths or Path(path).suffix.lower() not in TEXT_SOURCE_SUFFIXES:
                continue
            raw = source_bytes(root, path, reader, saved)
            format = 'json' if Path(path).suffix.lower() == '.json' else 'text'
            sources[source['id']] = {'format': format,
                'content': c.decode(raw) if format == 'json' else raw.decode('utf-8')}
    source_files = {}
    for source in task.get('sources', []):
        if source.get('identity'):
            source_files[source['path']] = c.digest(source_bytes(root, source['path'], reader, saved))
    for source in task.get('upload_sources', []):
        c.exact(source, {'file', 'url'}, 'upload source selection')
        source_files[source['file']] = c.digest(source_bytes(root, source['file'], reader, saved))
    result = {'task': authored_task, 'sources': sources,
        'delivery': {'content': content, 'translation_notes': task['delivery']['translation_notes']},
        'documents': documents,
        'generation': {key: copy.deepcopy(value) for key, value in generation.items()
                       if key not in DOCUMENTS and key not in {'references', 'request_validation'}},
        'references': references, 'upscale': upscale, 'source_files': source_files}
    if initial and execution_dispatcher(task):
        if task['route'] == 'upscale':
            result['upscale'] = {'source': None, 'model': None, 'scale_factor': None,
                'settings': {}, 'guidance_prompt': None,
                'render_intent': {'artifact_type': 'render-intent', 'execution_mode': 'upscale'}}
        else:
            result['documents'] = {'parameters': {}}
            result['generation'] = {'model': None, 'render_intent': None,
                'service': None, 'count': 1, 'seed': None, 'continuity': {}}
    return result


def read_editable(authored: dict, reader) -> tuple[dict, dict, list[dict]]:
    """Read the selected editable files once and retain their source locations."""
    value=copy.deepcopy(authored)
    locations={}
    missing=[]
    def selected(item, field, *, text=False):
        if not isinstance(item,dict) or 'file' not in item or set(item)-{'file','field'}:
            return item
        path=c.text(item['file'],field+' file')
        locations[field]={'file':path,'pointer':item.get('field')}
        try:
            raw=reader.read(reader.select(path))
            result=raw.decode('utf-8') if text and 'field' not in item else c.decode(raw)
            for key in item.get('field',[]):
                result=result[key]
            if text and not isinstance(result,str):
                raise ValueError('selected text field must contain a string')
            return result
        except (OSError,ValueError,KeyError,TypeError,IndexError) as exc:
            missing.append({'field':field,'file':path,'code':'editable-source-unavailable','message':str(exc)})
            return None
    delivery=value['delivery']
    if 'file' in delivery:
        delivery['content']=selected({key:delivery[key] for key in ('file','field') if key in delivery},
                                     'authoring.delivery',text='field' not in delivery)
        delivery.pop('file',None);delivery.pop('field',None)
    for name,item in value['documents'].items():
        value['documents'][name]=selected(item,'authoring.documents.'+name,text=name in TEXT_DOCUMENTS)
    for name,item in value['sources'].items():
        if 'file' in item:
            item['content']=selected({key:item[key] for key in ('file','field') if key in item},
                                     'authoring.sources.'+name,text=item['format']=='text')
            item.pop('file',None);item.pop('field',None)
    intent=value['generation'].get('render_intent')
    if isinstance(intent,dict) and intent.get('prompt_expression')=={'document':'delivery'}:
        intent['prompt_expression']=delivery.get('content') or ''
    return value,locations,missing


def execution_dispatcher(task: dict) -> bool:
    return task.get('execution') == 'dispatcher'


def chosen_task(base: dict, authored: dict | None) -> dict:
    if authored is None:
        return copy.deepcopy(base)
    c.exact(authored, {'task', 'sources', 'delivery', 'documents', 'generation', 'references', 'upscale', 'source_files'}, 'authoring choices')
    if not isinstance(authored['task'], dict):
        raise ValueError('authoring.task must be an object')
    result = copy.deepcopy(base)
    result.pop('execution_decisions', None)
    for name in ('task_id', 'production_id'):
        if name in base and authored['task'].get(name) != base[name]:
            raise ValueError('authoring preserves the selected ' + name)
    if set(authored['task']) & GENERATED_TASK_FIELDS:
        raise ValueError('authoring.task cannot own derived delivery or generation file paths')
    result.update(copy.deepcopy(authored['task']))
    result.setdefault('route_reading', 'route-reading.json')
    result.setdefault('delivery', {'path': 'delivery.txt', 'translation_notes': None})
    result['delivery']['translation_notes'] = authored['delivery']['translation_notes']
    return result


def unresolved(authored: dict | None, task: dict) -> list[dict]:
    if authored is None:
        return []
    result = []
    def missing(field, code='authored-choice-required'):
        result.append({'field': 'authoring.' + field, 'code': code})
    for key in ('purpose', 'intended_effect'):
        if not (task.get('direction') or {}).get(key):
            missing('task.direction.' + key)
    if not task.get('criteria'):
        missing('task.criteria')
    if authored['upscale'] is None and not authored['delivery'].get('file') and not authored['delivery'].get('content'):
        missing('delivery.content')
    if execution_dispatcher(task):
        if task.get('route') == 'upscale':
            upscale = authored.get('upscale') or {}
            for key in ('source', 'scale_factor', 'render_intent'):
                if upscale.get(key) is None:
                    missing('upscale.' + key)
        else:
            if authored['documents'].get('production_spec') is None:
                intent = authored['generation'].get('render_intent')
                if intent is None:
                    missing('generation.render_intent')
                elif isinstance(intent, dict) and intent.get('execution_mode') is None:
                    missing('generation.render_intent.execution_mode')
            plot = authored['documents'].get('plot')
            if isinstance(plot, dict) and plot.get('approved') is None:
                missing('documents.plot.approved', 'plot-approval-required')
    return result


def _redirect(task: dict, before: str | None, after: str) -> None:
    if before is not None:
        for source in task.get('sources', []):
            if source.get('path') == before and not source.get('identity'):
                source['path'] = after


def materialize_file(task: dict, files: dict[str, bytes], output_dir: str, *,
                     field: str, filename: str, raw: bytes) -> str:
    """The common path/role projection for choices and bounded variations."""
    path = (Path(output_dir) / filename).as_posix()
    if field == 'delivery':
        before = task['delivery']['path']
        task['delivery']['path'] = path
    else:
        before = task.setdefault('generation', {}).get(field)
        task['generation'][field] = path
    _redirect(task, before, path)
    files[filename] = raw
    return path


def _approved_plot(value: dict, previous: dict | None) -> dict:
    """A previous approval only covers unchanged plot content, never a new edit."""
    import prompt_plot
    result = copy.deepcopy(value)
    approval = result.get('approved')
    if approval is None:
        return result
    previous_approval = previous.get('approved') if previous else None
    if previous_approval is not None:
        old_choice = {key: item for key, item in previous_approval.items() if key != 'content_sha256'}
        new_choice = {key: item for key, item in approval.items() if key != 'content_sha256'}
        if old_choice == new_choice:
            result['approved'] = copy.deepcopy(previous_approval)
            if prompt_plot.content_sha256(result) != prompt_plot.content_sha256(previous):
                raise UnresolvedChoice('authoring.documents.plot.approved', 'changed plot content needs its actual approval; previous approval covers the saved plot only')
            return result
    result['approved']['content_sha256'] = prompt_plot.content_sha256(result)
    return result


def _upload_sources(task: dict, witnesses: dict, carriers: set[str], reader) -> None:
    """Retain URL choices only for their current, unchanged carrier bytes."""
    if not isinstance(witnesses, dict):
        raise ValueError('authoring.source_files must contain the measured source files')
    for path, digest in witnesses.items():
        c.text(path, 'measured source file')
        c.sha(digest)
    if 'upload_sources' not in task:
        return
    retained = []
    for index, source in enumerate(task['upload_sources']):
        c.exact(source, {'file', 'url'}, 'upload source selection')
        path = c.text(source['file'], 'upload source file')
        previous = witnesses.get(path)
        # An inherited URL for removed or changed media has no current use.
        # It does not require rereading a source the author no longer selected.
        if previous is not None and previous not in carriers:
            continue
        selected = {'path': path, 'sha256': previous} if previous is not None else reader.select(path)
        reader.read(selected)
        if selected['sha256'] not in carriers:
            raise UnresolvedChoice(f'authoring.task.upload_sources.{index}.file',
                'select the exact prepared carrier file made available at this URL')
        from request_contract import validate_upload_source
        validate_upload_source({'kind': 'url', 'url': source['url']})
        retained.append(copy.deepcopy(source))
    task['upload_sources'] = retained


def materialize(root: Path, task: dict, authored: dict | None, reader, out_dir: str,
                *, saved: dict | None = None, validation: dict | None = None) -> tuple[dict, dict[str, bytes], bytes | None]:
    if authored is None:
        return copy.deepcopy(task), {}, None
    result = copy.deepcopy(task)
    files = {}
    for index, source in enumerate(result.get('sources', []), 1):
        selected = authored['sources'].get(source['id'])
        if source.get('identity'):
            # An editable rendition is not the authority of an adopted source.
            # Preserve the original source and the draft's exact byte witness.
            raw = reader.read(reader.select(source['path']))
            witness = authored['source_files'].get(source['path'])
            if witness is not None and c.digest(raw) != witness:
                raise UnresolvedChoice('authoring.task.sources',
                    'Identity source changed since these choices were drafted: ' + source['path'] +
                    '. Read the current owning source and draft its current scope and criteria again.')
            if selected is not None:
                same = (selected.get('content') == c.decode(raw) if selected.get('format') == 'json'
                        else selected.get('content') == raw.decode('utf-8'))
                if not same:
                    raise UnresolvedChoice('authoring.sources.' + source['id'],
                        'Revise identity in its owning source and authority workflow before selecting it; '
                        'an editable production copy cannot redefine that source.')
            continue
        if selected is None:
            continue
        c.exact(selected, {'format', 'content'}, 'authored source ' + source['id'])
        if selected['format'] not in {'text', 'json'}:
            raise ValueError('authored source format must be text or json')
        name = f"sources/source-{index:03d}." + ('json' if selected['format'] == 'json' else 'txt')
        files[name] = c.encoded(selected['content']) if selected['format'] == 'json' else selected['content'].encode('utf-8')
        source['path'] = (Path(out_dir) / name).as_posix()
    generation = result.setdefault('generation', {}) if execution_dispatcher(task) and task['route'] != 'upscale' else result.get('generation', {})
    old_generation = copy.deepcopy(generation)
    for key in list(generation):
        if key not in DOCUMENTS and key != 'references':
            generation.pop(key)
    generation.update(copy.deepcopy(authored['generation']))
    if generation.get('render_intent') is None:
        generation.pop('render_intent', None)
    documents = copy.deepcopy(authored['documents'])
    if set(documents) - DOCUMENTS:
        raise ValueError('authoring.documents names an unknown production document')
    if isinstance(documents.get('state_graphs'),dict):
        from state_protocol import acquire_subject_state_graphs
        documents['state_graphs']=acquire_subject_state_graphs(documents['state_graphs'],
            lambda path:reader.read(reader.select(path)),production_spec=documents.get('production_spec'))
    if documents.get('state_graphs') is not None and old_generation.get('state_graphs'):
        from production_identity import IDENTITY_NODES
        previous_graphs = c.decode(source_bytes(root, old_generation['state_graphs'], reader, saved))
        previous = {graph['identity_contract']['character_id']: graph for graph in previous_graphs}
        for graph in documents['state_graphs']:
            subject = graph['identity_contract']['character_id']
            before = previous.get(subject)
            if before is not None and any(before.get(node) != graph.get(node) for node in IDENTITY_NODES):
                raise UnresolvedChoice('authoring.documents.state_graphs',
                    'An existing identity, morphology, Era, Form or Appearance owner changed inside an editable '
                    'scene graph. Select the current approved graph from its owning workflow and draft again; '
                    'scene authoring cannot adopt a replacement identity.')
    plot = documents.get('plot')
    if plot is not None:
        original = old_generation.get('plot')
        previous = c.decode(source_bytes(root, original, reader, saved)) if original else None
        documents['plot'] = _approved_plot(plot, previous)
    delivery = authored['delivery']['content']
    if delivery is not None:
        delivery = delivery.encode('utf-8') if isinstance(delivery, str) else c.encoded(delivery)
    if documents.get('retrieval_record') is not None and delivery is not None:
        from prompt_retrieval import settle_retrieval_record
        documents['retrieval_record'] = settle_retrieval_record(documents['retrieval_record'],
            prompt=delivery.decode('utf-8'), plot=documents.get('plot'))
    visual_choices = documents.pop('visual_continuity', None)
    for field in DOCUMENTS:
        if field not in documents or documents[field] is None:
            generation.pop(field, None)
            continue
        name = field.replace('_', '-') + ('.txt' if field in TEXT_DOCUMENTS else '.json')
        value = documents[field]
        raw = value.encode('utf-8') if field in TEXT_DOCUMENTS else c.encoded(value)
        materialize_file(result, files, out_dir, field=field, filename=name, raw=raw)
    references = authored.get('references')
    prepared = None
    carriers = set()
    if references is not None:
        import production_reference_inputs
        model = (documents.get('production_spec') or {}).get('target_model') or generation.get('model')
        if model is None:
            raise ValueError('select choices.target before preparing references')
        with tempfile.TemporaryDirectory(prefix='production-reference-inputs-') as folder:
            folder = Path(folder)
            # The reference owner requires a fresh output directory.
            generated = folder / 'references'
            prepared = production_reference_inputs.build(references, model=model, root=root,
                output_dir=generated, reader=reader, publication_dir=out_dir)
            for path in sorted(generated.rglob('*')):
                if path.is_file():
                    files[path.relative_to(generated).as_posix()] = path.read_bytes()
        generation['references'] = (Path(out_dir) / 'prepared-reference-set.json').as_posix()
        _redirect(result, old_generation.get('references'), generation['references'])
        if 'image-input.json' in files:
            result['image_input'] = (Path(out_dir) / 'image-input.json').as_posix()
        else:
            # Selected reference choices own this derived pointer, including
            # its absence when the current build produces no image input.
            result.pop('image_input', None)
        if prepared['transport_mode'] == 'single-board':
            carriers.add(prepared['single_board']['sha256'])
        elif prepared['transport_mode'] == 'multi-image':
            carriers.update(row['transport']['sha256'] for row in prepared['selected_references'])
    elif 'references' in generation:
        generation.pop('references')
    if visual_choices is not None:
        import visual_continuity
        if prepared is None:
            raise ValueError('visual continuity needs the selected prepared references')
        visual = visual_continuity.build_record(visual_choices,
            production_spec=documents.get('production_spec'), prepared=prepared, root=root)
        reader.basis(visual['basis'])
        files['visual-continuity.json'] = c.encoded(visual)
        generation['visual_continuity'] = (Path(out_dir) / 'visual-continuity.json').as_posix()
        _redirect(result, old_generation.get('visual_continuity'), generation['visual_continuity'])
    upscale = authored.get('upscale')
    if upscale is not None:
        import production_binding
        record = validation
        if record is None:
            raise ValueError('select request validation for the new upscale input')
        request = production_binding.upscale_request(root, c.local(root, upscale['source']),
            upscale['model'], upscale['scale_factor'], upscale['settings'], upscale['guidance_prompt'],
            request_validation=record, render_intent=upscale['render_intent'])
        delivery = c.encoded(request)
        carriers.add(request['source']['sha256'])
    if documents.get('mask_binding') is not None and result.get('upload_sources'):
        import scene_mask_planner
        mask = scene_mask_planner.check_task(root, result, documents['mask_binding'],
            read=lambda path: reader.read(reader.select(path)))
        carriers.add(mask['bundle']['mask']['sha256'])
        if mask['binding']['guidance'] is not None:
            carriers.add(mask['binding']['guidance']['sha256'])
    _upload_sources(result, authored['source_files'], carriers, reader)
    if delivery is not None:
        name = 'delivery.json' if upscale is not None else 'delivery.txt'
        materialize_file(result, files, out_dir, field='delivery', filename=name, raw=delivery)
    return result, files, delivery
