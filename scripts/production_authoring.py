"""One editable source for authored production content and its derived files.

This layer retains decisions and delegates reference, retrieval and upscale
contracts to their existing owners. It never creates grants or execution
receipts. Original task identity and approval scope remain independently owned.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager
from pathlib import Path
import tempfile

import execution_contract as c
from production_diagnostics import choice_required
import production_document_contracts

DOCUMENTS = production_document_contracts.DOCUMENT_KEYS
TEXT_DOCUMENTS = frozenset({'negative', 'integrated_prompt', 'native_negative'})
TEXT_SOURCE_SUFFIXES = frozenset({'.md', '.txt', '.json', '.yaml', '.yml', '.csv', '.tsv'})
GENERATED_TASK_FIELDS = frozenset({'delivery', 'generation', 'route_reading', 'image_input', 'authored_basis'})
AUTHORING_SPACES = frozenset({'studio', 'task-source'})
# The sections that explain each authored choice this module reports.
EDITING_GUIDE = {'document_path': 'references/runtime/production-authoring.md#use-the-delivered-knowledge'}
DIRECTION_GUIDE = {'document_path': 'references/runtime/production-direction.md#record-the-production-direction'}
UPSCALE_GUIDE = {'document_path': 'references/adapters/upscale.md#prepare-the-exact-input'}
RENDER_GUIDE = {'document_path': 'references/runtime/render-contract.md#select-the-operation-and-optional-rendering-declaration'}
PLOT_GUIDE = {'document_path': 'references/runtime/prompt-only-core.md#specialized-prompt-artifact-export'}
IDENTITY_GUIDE = {'document_path': 'references/character-identity-contract.md#source-to-input-and-review-coverage'}
GRAPH_GUIDE = {'document_path': 'references/runtime/state-aware-series.md#authority-graph'}
UPLOAD_GUIDE = {'document_path': 'references/runtime/reference-delivery.md#upload-the-selected-media-for-one-generation'}
APPROVAL = '{"by": APPROVER, "at": RFC3339_UTC_TIME}'


class UnresolvedChoice(ValueError):
    """An edited choice that conflicts with its owner and needs the author's current judgment.

    The raising owner states what conflicts, the repair and the section that explains it.
    """

    def __init__(self, field: str, message: str, *, required_action: str, guidance: dict[str, str]):
        super().__init__(message)
        self.field = field
        self.required_action = required_action
        self.guidance = guidance

    def as_unresolved(self) -> dict:
        return choice_required(self.field, 'current-judgment-required', str(self), self.required_action,
                               self.guidance)


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
          initial: bool = False, captured=None, retained_prefix: str | None = None) -> dict:
    def selected_bytes(path):
        return captured.bytes(path) if captured is not None else source_bytes(root, path, reader, saved)

    authored_task = {key: copy.deepcopy(value) for key, value in task.items()
                     if key not in GENERATED_TASK_FIELDS and key != 'execution_decisions'}
    documents = {}
    generation = task.get('generation') or {}
    for field in DOCUMENTS:
        path = generation.get(field)
        if path:
            raw = selected_bytes(path)
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
    content = None if initial else selected_bytes(task['delivery']['path']).decode('utf-8')
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
        prepared = c.decode(selected_bytes(path)) if path else None
        package_root = c.local(root, path, exists=False).parent if path else root
        mirrored = False
        if path and task.get('image_input'):
            # An image input written from this set's rows is selected again as the mirrored form.
            mirrored = c.decode(selected_bytes(task['image_input'])).get('prepared_references') == path
        if captured is not None and path:
            references = captured.reference_choices(retained_prefix, mirrored_input=mirrored)
        else:
            references = production_reference_inputs.draft(prepared, package_root=package_root, root=root,
                                                           mirrored_input=mirrored)
    sources = {}
    owned_paths = {task['delivery']['path'], *(generation.get(key) for key in DOCUMENTS), generation.get('references'), generation.get('request_validation')}
    if not initial:
        for source in task.get('sources', []):
            path = source['path']
            if source.get('identity') or path in owned_paths or Path(path).suffix.lower() not in TEXT_SOURCE_SUFFIXES:
                continue
            raw = selected_bytes(path)
            format = 'json' if Path(path).suffix.lower() == '.json' else 'text'
            sources[source['id']] = {'format': format,
                'content': c.decode(raw) if format == 'json' else raw.decode('utf-8')}
    originals = {item['source']['id']: item for item in
                 (task.get('authored_basis') or {}).get('sources', [])}
    for source in authored_task.get('sources', []):
        original = originals.get(source['id'])
        if original is not None:
            # The source selector owns the comparison basis; the editable
            # body above retains the separately authored adaptation.
            source['path'] = original['file']['path']
    source_files = {}
    for source in task.get('sources', []):
        if source.get('identity'):
            source_files[source['path']] = c.digest(selected_bytes(source['path']))
    for source in task.get('upload_sources', []):
        c.exact(source, {'file', 'url'}, 'upload source selection')
        source_files[source['file']] = c.digest(selected_bytes(source['file']))
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
    def selected(item, field, *, text=False, document=None):
        c.exact(item, {'file', 'field'} if isinstance(item, dict) and 'field' in item else {'file'},
                field + ' selection')
        path=c.text(item['file'],field+' file')
        owner = production_document_contracts.guidance(document) if document is not None else dict(EDITING_GUIDE)
        locations[field]={'file':path,'pointer':item.get('field'),'guidance':owner}
        try:
            raw=reader.read(reader.select(path))
            result=raw.decode('utf-8') if text and 'field' not in item else c.decode(raw)
            for key in item.get('field',[]):
                result=result[key]
            if text and not isinstance(result,str):
                raise ValueError('selected text field must contain a string')
            return result
        except (OSError,ValueError,KeyError,TypeError,IndexError) as exc:
            missing.append({'field':field,'file':path,'code':'INPUT_UNREADABLE','cause':str(exc),
                'message':'The editable file that '+field+' selects cannot be read as selected.',
                'required_action':'Make '+path+' a readable file holding the selected content, or change '+
                    field+'.file (and '+field+'.field for a JSON selection) to the file and value to use.',
                'guidance':owner})
            return None
    delivery=value['delivery']
    if 'file' in delivery:
        delivery['content']=selected({key:delivery[key] for key in ('file','field') if key in delivery},
                                     'authoring.delivery',text='field' not in delivery)
        delivery.pop('file',None);delivery.pop('field',None)
    for name,item in value['documents'].items():
        value['documents'][name]=selected(item,'authoring.documents.'+name,text=name in TEXT_DOCUMENTS,
                                          document=name)
    for name,item in value['sources'].items():
        if 'file' in item:
            item['content']=selected({key:item[key] for key in ('file','field') if key in item},
                                     'authoring.sources.'+name,text=item['format']=='text')
            item.pop('file',None);item.pop('field',None)
    intent=value['generation'].get('render_intent')
    if isinstance(intent,dict) and intent.get('prompt_expression')=={'document':'delivery'}:
        intent['prompt_expression']=delivery.get('content') or ''
    return value,locations,missing


def export_documents(authored: dict, out_dir: str) -> dict[str, bytes]:
    """Give every selected document one editable file, retaining only its selector in choices.

    Draft construction uses resolved values until this publication boundary.
    Compilation measures the selected current bytes and captures those hashes;
    an editable selector does not ask the author to maintain a content hash.
    """
    files = {}
    documents = authored['documents']
    for name in sorted(documents):
        value = documents[name]
        filename = name.replace('_', '-') + ('.txt' if name in TEXT_DOCUMENTS else '.json')
        files[filename] = value.encode('utf-8') if name in TEXT_DOCUMENTS else c.encoded(value)
        documents[name] = {'file': (Path(out_dir) / filename).as_posix()}
    return files


def locate_unresolved(items: list[dict], locations: dict) -> list[dict]:
    """Locate an authored-content repair at the file that owns the selected value."""
    result = copy.deepcopy(items)
    for item in result:
        field = item.get('field', '')
        selected = next((key for key in sorted(locations, key=len, reverse=True)
                         if field == key or field.startswith(key + '.')), None)
        if selected is None:
            continue
        location = locations[selected]
        item['file'] = location['file']
        suffix = field[len(selected):].lstrip('.')
        if selected == 'authoring.delivery' or selected.startswith('authoring.sources.'):
            suffix = suffix.removeprefix('content.').removeprefix('content')
        pointer = list(location.get('pointer') or [])
        if suffix:
            pointer.extend(int(part) if part.isdecimal() else part for part in suffix.split('.'))
        item['source_field'] = pointer
        guidance = {**location['guidance'], **(item.get('guidance') or {})}
        if location['guidance'].get('schema'):
            guidance['schema'] = location['guidance']['schema']
        item['guidance'] = guidance
        destination = location['file'] + (' at ' + '.'.join(map(str, pointer)) if pointer else '')
        item['message'] = item['message'].replace(field, destination)
        item['required_action'] = 'Edit ' + destination + '. ' + item['required_action'].replace(field, destination)
    return result


@contextmanager
def _document_context(name: str, locations: dict):
    """Keep a document builder's refusal attached to its editable source."""
    from production_diagnostics import ProductionError, from_exception, DIAGNOSTIC_FIELDS
    field = 'authoring.documents.' + name
    location = locations.get(field)
    try:
        yield
    except UnresolvedChoice:
        raise
    except (ValueError, OSError, KeyError, TypeError, IndexError, AttributeError) as exc:
        if location is None:
            raise
        diagnostic = from_exception(exc, phase='authoring', file=location['file'], pointer=field)
        owner = {**location['guidance'], **(diagnostic.get('guidance') or {})}
        if location['guidance'].get('schema'):
            owner['schema'] = location['guidance']['schema']
        raise ProductionError(diagnostic['code'], diagnostic['message'], phase=diagnostic['phase'],
            file=location['file'], pointer=diagnostic['pointer'] or field, guidance=owner,
            required_action='Edit ' + location['file'] + '. ' + diagnostic['required_action'],
            authoring_field=field, source_field=location.get('pointer'),
            **{key: value for key, value in diagnostic.items() if key not in DIAGNOSTIC_FIELDS}) from exc


def execution_dispatcher(task: dict) -> bool:
    return task.get('execution') == 'dispatcher'


def select_upscale(root: Path, authored: dict, out_dir: str, *,
                   source_image: Path | None = None, scale: float | None = None,
                   purpose: str | None = None) -> tuple[dict[str, bytes], dict | None]:
    """Apply actual source and scale choices without inventing art direction."""
    from production_binding import normalize_upscale_factor
    from production_evidence import inspect
    task = authored['task']
    if task.get('route') != 'upscale' or task.get('execution') != 'dispatcher':
        chosen = [name for name, value in (('--source-image', source_image), ('--scale', scale),
                                           ('--purpose', purpose)) if value is not None]
        if chosen:
            from production_diagnostics import ProductionError
            raise ProductionError('INPUT_CONSISTENCY_ERROR', ', '.join(chosen) + ' select a dispatcher upscale '
                'input, and this draft is not a dispatcher upscale.', phase='authoring', guidance=dict(UPSCALE_GUIDE),
                options=chosen, required_action='Omit ' + ', '.join(chosen) + ', or draft the enlargement with '
                '--route upscale (dispatcher execution). To edit an adopted Studio image, select it with '
                '--edit-character CHARACTER --edit-slot SLOT and --route generation.')
        return {}, None
    upscale = authored['upscale']
    files, selected = {}, None
    if scale is not None:
        upscale['scale_factor'] = normalize_upscale_factor(scale)
    if purpose is not None:
        purpose = c.text(purpose, 'upscale purpose')
        for field in ('purpose', 'intended_effect'):
            if not task['direction'].get(field):
                task['direction'][field] = purpose
        if not task.get('criteria'):
            task['criteria'] = [{'id': 'requested-result', 'text': purpose,
                                 'strength': 'hard', 'evidence': 'image'}]
    if source_image is not None:
        source = Path(source_image)
        if not source.is_absolute():
            source = c.local(root, source.as_posix())
        raw = c.read(source)
        measured = inspect(raw, 'image')
        if measured['format'] == 'SVG':
            raise ValueError('upscale source must be an existing raster image')
        digest = c.digest(raw)
        try:
            path = source.resolve().relative_to(root.resolve()).as_posix()
            c.local(root, path)
        except ValueError:
            filename = 'source.' + measured['format'].lower()
            path = (Path(out_dir) / filename).as_posix()
            files[filename] = raw
        upscale['source'] = path
        authored['source_files'][path] = digest
        if not any(row['path'] == path for row in task.get('sources', [])):
            identifiers = {row['id'] for row in task.get('sources', [])}
            identifier = 'upscale-source'
            if identifier in identifiers:
                identifier += '-' + digest[:12]
            task.setdefault('sources', []).append({'id': identifier, 'path': path,
                'role': 'reference', 'disposition': 'applied', 'locator': 'whole image',
                'reason': 'The selected image is the source of this enlargement.'})
        selected = {'path': path, 'sha256': digest, **measured}
    return files, selected


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


# What each empty authored field needs, the value to give it and the section that explains it.
MODES = 'text-to-image, image-to-image, reference-guided or instruction-edit, as the selected offering supports'
CARD = 'scripts/render_contract.py model --model MODEL_ID --service SERVICE'
AUTHORED_FIELDS = {
    'task.direction.purpose': (
        'so the task states no purpose.',
        'Set authoring.task.direction.purpose to what this work is for, stated from the commission.',
        DIRECTION_GUIDE),
    'task.direction.intended_effect': (
        'so the task states no intended effect.',
        'Set authoring.task.direction.intended_effect to the effect the result is meant to have, from the '
        'commission; it states an intention, not an observed response.', DIRECTION_GUIDE),
    'task.criteria': (
        'so the result has no review criterion.',
        'Add each requirement of the commissioned result to authoring.task.criteria as {"id": ID, "strength": '
        '"hard" or "advisory", "text": REQUIREMENT, "evidence": "artifact", "text", "image", "motion" or '
        '"audio"}, written from the commission independently of the prompt.', DIRECTION_GUIDE),
    'delivery.content': (
        'so there is no text to deliver.',
        'Write the delivered text into the file that authoring.delivery.file names (its selected field for '
        'JSON), or set authoring.delivery.content to it.', EDITING_GUIDE),
    'upscale.source': (
        'so no image is selected for enlargement.',
        'Draft the enlargement with scripts/production_workflow.py draft-inputs --route upscale --source-image '
        'IMAGE (or --source-run RUN --source-candidate CANDIDATE) into a new --out-dir, which selects the image '
        'and declares it as a task source; an image already declared in authoring.task.sources is selected by '
        'setting authoring.upscale.source to its Studio path.', UPSCALE_GUIDE),
    'upscale.scale_factor': (
        'so no enlargement factor is selected.',
        'Set authoring.upscale.scale_factor to the requested factor, one that the model\'s '
        'supported_scale_factors or its offering\'s scale control accepts, as ' + CARD + ' shows them.',
        UPSCALE_GUIDE),
    'upscale.render_intent': (
        'so the upscale declares no operation.',
        'Set authoring.upscale.render_intent to {"artifact_type": "render-intent", "execution_mode": "upscale"}.',
        RENDER_GUIDE),
    'generation.render_intent': (
        'and no Production Specification in authoring.documents owns the render intent.',
        'Set authoring.generation.render_intent to {"artifact_type": "render-intent", "execution_mode": MODE} '
        'with the operation this request performs (' + MODES + '), or to a complete declaration that '
        'scripts/render_contract.py intent --mode MODE writes.', RENDER_GUIDE),
    'generation.render_intent.execution_mode': (
        'so the render intent names no operation.',
        'Set authoring.generation.render_intent.execution_mode to the operation this request performs (' +
        MODES + '), one of the modes that ' + CARD + ' lists.', RENDER_GUIDE),
}


RECORDING_GUIDE = {'document_path': 'references/runtime/studio.md#production-owned-candidates'}
RECORDING_FIELDS = {
    'slot': ('so the result has no Studio slot to be recorded in.',
             'Set authoring.task.recording.slot to the slot of Studio character {character} that records the '
             'result. This is its initial destination; a candidate does not replace accepted artwork. Choose '
             'the intended scene or declared sheet panel, including the source slot for an edit that belongs '
             'there. A deliberate alternate destination is also valid. Correct an already recorded result '
             'through studio.py draft-reassignment and reassign; keep its generation evidence unchanged.'),
    'sheet_panel': ('so the recording does not state whether the result is a sheet panel.',
                    'Set authoring.task.recording.sheet_panel to true for a single-subject panel declared by '
                    'the character sheet render profile, and to false for an ordinary scene. A stored or '
                    'adopted scene reference does not by itself declare a sheet panel. Preserve every '
                    'production subject and its applicable continuity mapping.'),
    'role': ('so the recording does not say what the result is for.',
             'Set authoring.task.recording.role to a short label of what the recorded image is for.'),
}


def authored_choice(field: str) -> dict:
    """The unanswered entry of one AUTHORED_FIELDS choice."""
    consequence, required_action, owner = AUTHORED_FIELDS[field]
    empty = 'is null' if field.startswith(('upscale.', 'generation.')) else 'is empty'
    return choice_required('authoring.' + field, 'authored-choice-required',
                           'authoring.' + field + ' ' + empty + ', ' + consequence, required_action, owner)


def _expression_unresolved(specification: dict) -> list[dict]:
    """A rendering declaration whose prompt spans are not chosen yet."""
    intent = specification.get('render_intent') if isinstance(specification, dict) else None
    if not isinstance(intent, dict) or 'prompt_expression' not in intent:
        return []
    base = 'authoring.documents.production_spec.render_intent'
    spans = [(base + '.prompt_expression', intent['prompt_expression'])]
    spans += [(base + '.regional_overrides.' + str(index) + '.prompt_expression', row.get('prompt_expression'))
              for index, row in enumerate(intent.get('regional_overrides') or []) if isinstance(row, dict)]
    return [choice_required(field, 'authored-choice-required',
        field + ' is null, so the rendering declaration names no passage of the delivered prompt.',
        'Set ' + field + ' to the exact passage of the delivered prompt that states this finish, or remove the '
        'rendering fields (preset, axes, presentation, selection, prompt_expression and regional_overrides) from '
        'the render intent so that only artifact_type and execution_mode remain and the finish stays with the '
        'model and its source images.', RENDER_GUIDE) for field, value in spans if value is None]


def continuity_unresolved(authored: dict) -> list[dict]:
    """Subjects of the selected Production Specification without a continuity decision."""
    specification = (authored.get('documents') or {}).get('production_spec')
    if (not isinstance(specification, dict)
            or (authored.get('documents') or {}).get('visual_continuity') is not None):
        return []
    decided = (authored.get('generation') or {}).get('continuity') or {}
    result = []
    for subject in specification.get('subjects') or []:
        identifier = subject.get('id') if isinstance(subject, dict) else None
        if isinstance(identifier, str) and identifier not in decided:
            field = 'authoring.generation.continuity.' + identifier
            result.append(choice_required(field, 'continuity-choice-required',
                field + ' is not set, so Production Specification subject ' + identifier + ' has no continuity '
                'decision.', 'Set ' + field + ' to the author\'s decision: "recurring" for a subject that is a Studio '
                'character with an accepted identity image among the references (map it to that character in '
                'authoring.task.recording.subject_map), "one-off" for a subject that does not recur, or '
                '"undecided" for a single-subject exploration before an identity image is accepted.',
                {'document_path': 'references/runtime/generation-package.md#generation-package'}))
    return result


def unresolved(authored: dict | None, task: dict) -> list[dict]:
    if authored is None:
        return []
    result = []
    def missing(field):
        result.append(authored_choice(field))
    for key in ('purpose', 'intended_effect'):
        if not (task.get('direction') or {}).get(key):
            missing('task.direction.' + key)
    if not task.get('criteria'):
        missing('task.criteria')
    if authored['upscale'] is None and not authored['delivery'].get('file') and not authored['delivery'].get('content'):
        missing('delivery.content')
    result.extend(_expression_unresolved((authored.get('documents') or {}).get('production_spec')))
    recording = task.get('recording')
    if isinstance(recording, dict):
        for key, (consequence, required_action) in RECORDING_FIELDS.items():
            if recording.get(key) is None:
                field = 'authoring.task.recording.' + key
                result.append(choice_required(field, 'authored-choice-required', field + ' is null, ' + consequence,
                    required_action.format(character=recording.get('character')), RECORDING_GUIDE))
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
                result.append(choice_required('authoring.documents.plot.approved', 'plot-approval-required',
                    'authoring.documents.plot.approved is null, so the selected plot has no approval.',
                    'After the author approves this plot, set authoring.documents.plot.approved to ' + APPROVAL +
                    '; the builder adds its content_sha256. Remove plot from authoring.documents when this work '
                    'does not use one.', PLOT_GUIDE))
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
                raise UnresolvedChoice('authoring.documents.plot.approved',
                    'changed plot content needs its actual approval; previous approval covers the saved plot only',
                    required_action='After the author approves the changed plot, replace '
                        'authoring.documents.plot.approved with that approval, ' + APPROVAL + ', or restore the '
                        'plot content that the earlier approval covers.', guidance=PLOT_GUIDE)
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
            field = f'authoring.task.upload_sources.{index}.file'
            raise UnresolvedChoice(field,
                path + ' is not a media carrier that this preparation produces, so its URL binds no input.',
                required_action='Set ' + field + ' to the Studio path of the prepared carrier file whose exact '
                    'bytes are hosted at its url, or remove that upload_sources entry when no prepared carrier is '
                    'hosted there.', guidance=UPLOAD_GUIDE)
        from request_contract import validate_upload_source
        validate_upload_source({'kind': 'url', 'url': source['url']})
        retained.append(copy.deepcopy(source))
    task['upload_sources'] = retained


def materialize(root: Path, task: dict, authored: dict | None, reader, out_dir: str,
                *, saved: dict | None = None, validation: dict | None = None,
                locations: dict | None = None) -> tuple[dict, dict[str, bytes], bytes | None]:
    if authored is None:
        return copy.deepcopy(task), {}, None
    result = copy.deepcopy(task)
    locations = locations or {}
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
                    'Identity source changed since these choices were drafted: ' + source['path'] + '.',
                    required_action='Read the current ' + source['path'] + ', then draft these choices again from '
                        'their task or run with scripts/production_workflow.py draft-inputs into a new --out-dir and '
                        'reassess its identity scope and criteria in authoring.task.sources and '
                        'authoring.task.criteria; restoring the bytes this draft measured also resolves it.',
                    guidance=IDENTITY_GUIDE)
            if selected is not None:
                same = (selected.get('content') == c.decode(raw) if selected.get('format') == 'json'
                        else selected.get('content') == raw.decode('utf-8'))
                if not same:
                    field = 'authoring.sources.' + source['id']
                    raise UnresolvedChoice(field,
                        field + ' edits an identity source, and an editable production copy cannot redefine '
                        'its owning source.',
                        required_action='Remove ' + field + ' or restore it to the current content of ' +
                            source['path'] + '; revise the identity itself in that owning source through its '
                            'adoption workflow, then draft again.', guidance=IDENTITY_GUIDE)
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
        with _document_context('state_graphs', locations):
            documents['state_graphs']=acquire_subject_state_graphs(documents['state_graphs'],
                lambda path:reader.read(reader.select(path)),production_spec=documents.get('production_spec'))
    if documents.get('state_graphs') is not None and old_generation.get('state_graphs'):
        from production_identity import IDENTITY_NODES
        previous_graphs = c.decode(source_bytes(root, old_generation['state_graphs'], reader, saved))
        previous = {graph['identity_contract']['character_id']: graph for graph in previous_graphs}
        for graph in documents['state_graphs']:
            subject = graph['identity_contract']['character_id']
            before = previous.get(subject)
            changed = [node for node in IDENTITY_NODES if before is not None and before.get(node) != graph.get(node)]
            if changed:
                raise UnresolvedChoice('authoring.documents.state_graphs',
                    'The owner nodes ' + ', '.join(changed) + ' of subject ' + str(subject) + ' changed inside an '
                    'editable scene graph; scene authoring cannot adopt a replacement identity.',
                    required_action='Restore ' + ', '.join(changed) + ' of subject ' + str(subject) + ' in '
                        'authoring.documents.state_graphs to the selected graph, or select the current approved '
                        'graph from its owning workflow and draft again.', guidance=GRAPH_GUIDE)
    plot = documents.get('plot')
    if plot is not None:
        original = old_generation.get('plot')
        previous = c.decode(source_bytes(root, original, reader, saved)) if original else None
        with _document_context('plot', locations):
            documents['plot'] = _approved_plot(plot, previous)
    delivery = authored['delivery']['content']
    if delivery is not None:
        delivery = delivery.encode('utf-8') if isinstance(delivery, str) else c.encoded(delivery)
    if documents.get('retrieval_record') is not None and delivery is not None:
        from prompt_retrieval import settle_retrieval_record
        with _document_context('retrieval_record', locations):
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
        specification = documents.get('production_spec')
        model = (specification.get('target_model') if isinstance(specification, dict) else None) or generation.get('model')
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
    elif execution_dispatcher(task) and task['route'] != 'upscale':
        generation.pop('references', None)
        # Image-input is the compiled projection of the selected references,
        # not a second editable selection that can survive their removal.
        result.pop('image_input', None)
    if visual_choices is not None:
        import visual_continuity
        if prepared is None:
            from prepare_generation_references import empty_stateless_reference_set
            prepared = empty_stateless_reference_set()
        with _document_context('visual_continuity', locations):
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
        with _document_context('mask_binding', locations):
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
