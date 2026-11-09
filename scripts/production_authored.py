"""Save authored revisions and record their actual delivery and review.

The ordinary Production publication and event store own these artifacts.
Saving records authored bytes, not a fictitious external result. Delivery and
review refer to the exact saved revision and do not transfer to later edits.
"""
from __future__ import annotations

import copy
from pathlib import Path

import execution_contract as c
import production_store as store
from pack_manager import generate_uuid7
from production_diagnostics import CompilationError, ProductionError

EVENTS = {'authored-save', 'authored-delivery', 'authored-review'}


def requirements(task: dict) -> list[str]:
    """Results commissioned for this authored task, independently of candidates."""
    return list((task.get('authored') or {}).get('requirements', ['save']))


def completion_state(task: dict) -> str:
    """The commissioned maturity of the result, independent of its saved state."""
    state = (task.get('authored') or {}).get('completion_state', 'finished')
    if state not in {'draft', 'finished'}:
        raise ValueError('authored completion_state must be draft or finished')
    return state


def _frozen_read(prepared: dict, read_object):
    files = {row['path']: row for row in prepared['dependencies'] if row['space'] != 'skill'}
    def read(path: str) -> bytes:
        if path not in files:
            raise ValueError('saved authored input is not captured: ' + path)
        row = files[path]
        raw = read_object(row['sha256'])
        if c.digest(raw) != row['sha256'] or len(raw) != row['size']:
            raise ValueError('saved authored input differs from its captured bytes: ' + path)
        return raw
    return read


def finalize_compilation(compiled, *, state: str = 'finished', unresolved: list | None = None,
                         choices: dict | None = None) -> None:
    """Describe the actual authored revision before its single publication."""
    if compiled.prepared['task']['execution'] != 'authored':
        return
    from production_compiler import input_digest
    if state not in {'draft', 'finished'}:
        raise ValueError('authored state must be draft or finished')
    prepared, consumer = compiled.prepared, compiled.consumer
    raw = consumer['instructions'].encode('utf-8')
    artifact = {'path': 'delivery.txt', 'sha256': c.digest(raw), 'size': len(raw)}
    descriptor = {'state': state, 'input_verified': state == 'finished',
                  'artifact': artifact, 'unresolved': copy.deepcopy(unresolved or []),
                  'choices': choices}
    prepared['authored_revision'] = descriptor
    consumer['authored'] = {'state': state, 'requirements': requirements(prepared['task']),
                            'completion_state': completion_state(prepared['task'])}
    prepared['consumer_sha256'] = c.content_id(consumer)
    prepared['input_sha256'] = input_digest(prepared, consumer)
    compiled.execution_plan.update(input_sha256=prepared['input_sha256'],
        readiness={'state': 'not_applicable', 'executable': False, 'diagnostics': []})
    compiled.report.update(readiness=compiled.execution_plan['readiness'],
                           authored_revision=copy.deepcopy(descriptor))
    # Publication already writes delivery.txt. The same bytes remain available
    # through the object reader used by replay and exact delivery verification.
    object_path = 'objects/' + artifact['sha256']
    if not any(row['path'] == object_path for row in compiled.artifacts.files()):
        compiled.artifacts.write(object_path, raw)


def validate_publication(prepared: dict, consumer: dict, read_object) -> None:
    """Verify authored revision content without promoting drafts to input checks."""
    if prepared['task']['execution'] != 'authored':
        if prepared.get('authored_revision') is not None or prepared.get('authored_prompt') is not None:
            raise ValueError('authored revision metadata belongs to authored artifacts')
        return
    descriptor = prepared.get('authored_revision')
    c.exact(descriptor, {'state', 'input_verified', 'artifact', 'unresolved', 'choices'}, 'authored revision')
    if descriptor['state'] not in {'draft', 'finished'}:
        raise ValueError('invalid authored revision state')
    if descriptor['input_verified'] is not (descriptor['state'] == 'finished'):
        raise ValueError('authored input verification differs from its saved state')
    c.exact(descriptor['artifact'], {'path', 'sha256', 'size'}, 'authored artifact')
    raw = consumer['instructions'].encode('utf-8')
    expected = {'path': 'delivery.txt', 'sha256': c.digest(raw), 'size': len(raw)}
    if descriptor['artifact'] != expected or read_object(expected['sha256']) != raw:
        raise ValueError('authored revision differs from its exact saved text')
    if consumer.get('authored') != {'state': descriptor['state'], 'requirements': requirements(prepared['task']),
                                   'completion_state': completion_state(prepared['task'])}:
        raise ValueError('authored consumer state differs from the saved obligations')
    if not isinstance(descriptor['unresolved'], list):
        raise ValueError('authored unresolved choices must be a list')
    basis = prepared['task'].get('authored_basis')
    if basis is not None:
        c.exact(basis, {'origin_task', 'sources'}, 'authored assessment basis')
        if not isinstance(basis['origin_task'], dict):
            raise ValueError('authored original commission must be a task object')
        seen = set()
        for source in basis['sources']:
            c.exact(source, {'source', 'file'}, 'authored original source')
            identifier = source['source']['id']
            if identifier in seen:
                raise ValueError('duplicate authored original source')
            seen.add(identifier)
            item = source['file']
            c.exact(item, {'path', 'sha256', 'size'}, 'authored original source file')
            raw = _frozen_read(prepared, read_object)(item['path'])
            if c.digest(raw) != item['sha256'] or len(raw) != item['size']:
                raise ValueError('authored original source differs from its captured bytes')
    if descriptor['choices'] is not None:
        choice = descriptor['choices']
        c.exact(choice, {'path', 'sha256', 'size'}, 'authored editable source')
        selected = _frozen_read(prepared, read_object)(choice['path'])
        if c.digest(selected) != choice['sha256'] or len(selected) != choice['size']:
            raise ValueError('authored editable source differs from its saved revision')
    if descriptor['state'] == 'finished':
        if descriptor['unresolved']:
            raise ValueError('a finished authored revision retains unresolved input choices')
        import authored_prompt
        authored_prompt.validate_bound(prepared['task'], prepared.get('authored_prompt'),
                                       _frozen_read(prepared, read_object))
    elif prepared.get('authored_prompt') is not None:
        raise ValueError('a draft has no completed target prompt verification')


def _draft_compilation(root: Path, choices_path: str):
    """Capture the authoring owner's incomplete view without final-input claims."""
    import production_inputs
    import production_compiler as compiler
    from publication_artifacts import StagedArtifacts
    view = production_inputs.authoring_view(root, choices_path, register=True)
    task = copy.deepcopy(view['task'])
    task['authored_basis'] = copy.deepcopy(view['authored_basis'])
    if task.get('execution') != 'authored':
        raise ValueError('save accepts an authored artifact; use prepare for an image execution')
    if task.get('artifact') not in {'text', 'json'}:
        raise ValueError('authored saving requires text or JSON')
    identity = generate_uuid7()
    directory = compiler._staging(root, True)
    artifacts = StagedArtifacts(directory)
    captured = dict(view['captured'])
    import authored_prompt
    unresolved = copy.deepcopy(view['unresolved'])
    for path in authored_prompt.paths(task):
        if path in captured:
            continue
        try:
            captured[path] = store.stable_bytes(root, path)
        except (ValueError, OSError) as exc:
            unresolved.append({'field': 'authoring.task.authored', 'file': path,
                'code': 'authored-source-unavailable', 'message': str(exc)})
    choice_raw = captured[choices_path]
    raw = view['delivery']
    if not isinstance(raw, bytes):
        raise TypeError('the authoring owner must supply exact delivery bytes')
    instructions = raw.decode('utf-8')
    prefix = compiler.run_inputs(identity)
    task_path = prefix + '/task.json'
    task.setdefault('delivery', {})['path'] = prefix + '/delivery.txt'
    captured[task['delivery']['path']] = raw
    captured[task_path] = c.encoded(task)
    artifacts.write('inputs/task.json', captured[task_path])
    artifacts.write('inputs/delivery.txt', raw)
    artifacts.write('delivery.txt', raw)
    dependencies = []
    written = set()
    for path, content in captured.items():
        key = c.digest(content)
        dependencies.append({'space': 'task-source', 'path': path, 'sha256': key, 'size': len(content)})
        if key not in written:
            artifacts.write('objects/' + key, content)
            written.add(key)
    consumer = {'route': task['route'], 'instructions': instructions,
                'criteria': copy.deepcopy(task.get('criteria', [])),
                'direction': copy.deepcopy(task.get('direction', {})),
                'world_views': [], 'moment_views': [], 'authoring_materials': []}
    prepared = {'task_path': task_path, 'task': task, 'route': {'route': task['route'],
                'features': list(task.get('features', [])), 'reads': []},
                'authority': None, 'route_reading': None, 'route_reading_sha256': None,
                'reading_issuance': None, 'dependencies': sorted(dependencies, key=lambda row: row['path']),
                'runtime_snapshot': None, 'consumer_sha256': c.content_id(consumer), 'run': identity}
    prepared['input_sha256'] = compiler.input_digest(prepared, consumer)
    execution = {'run': identity, 'execution': 'authored', 'input_sha256': prepared['input_sha256'],
                 'request_sha256': None, 'operations': [], 'external_effects': [],
                 'readiness': {'state': 'not_applicable', 'executable': False, 'diagnostics': []}}
    report = {'ok': True, 'publishable': True, 'run': None, 'diagnostics': [], 'checks': [],
              'external_effect': False, 'formal_run_created': False, 'request_preview': None,
              'execution_plan': execution, 'authoring': {'choices': choices_path,
              'choices_ref': copy.deepcopy(view['choices_ref']),
              'unresolved': copy.deepcopy(unresolved)}}
    prepared['authoring'] = copy.deepcopy(report['authoring'])
    compiled = compiler.Compilation(report=report, directory=directory, prepared=prepared,
        consumer=consumer, execution_plan=execution, identity=identity, artifacts=artifacts)
    finalize_compilation(compiled, state='draft', unresolved=unresolved,
        choices={'path': choices_path, 'sha256': c.digest(choice_raw), 'size': len(choice_raw)})
    return compiled


def record_save(root: Path, run: str) -> dict:
    """Record the committed authored publication, including recovery after a stop."""
    import production_workflow as workflow
    with store.transaction(root):
        loaded = workflow.read_run(root, run)
        data = _save_data(loaded.prepared)
        receipt = workflow.append_record(loaded.directory, loaded.prepared, loaded.rows, 'authored-save', data)
    return {'ok': True, 'run': run, 'saved': True, 'state': data['state'],
            'artifact': str(loaded.directory / data['artifact']['path']),
            'save': receipt['sha256'], 'external_effect': False,
            'unresolved': copy.deepcopy(loaded.prepared['authored_revision']['unresolved'])}


def save(root: Path, choices_path: str, *, draft: bool = False) -> dict:
    """Save exact editable content; completed target input uses the common compiler."""
    import production_inputs
    import production_compiler as compiler
    root = c._root(root)
    compiled = (_draft_compilation(root, choices_path) if draft else
                production_inputs.compile_choices(root, choices_path, persist=True))
    if not compiled.report.get('publishable'):
        raise CompilationError(compiled.report)
    if compiled.prepared['task']['execution'] != 'authored':
        raise ValueError('save requires authored execution; prepare the selected image request instead')
    result = compiler.publish_compilation(root, compiled)
    result.update(record_save(root, result['run']))
    return result


def draft_source(root: Path, run: str) -> dict | None:
    """Return the exact incomplete editor source for the authoring owner to restore."""
    import production_workflow as workflow
    loaded = workflow.read_run(root, run)
    descriptor = loaded.prepared.get('authored_revision')
    if not descriptor or descriptor['state'] != 'draft' or descriptor['choices'] is None:
        return None
    files = {row['path']: loaded.evidence.read(row['sha256']) for row in loaded.prepared['dependencies']
             if row['space'] != 'skill'}
    return {'choices': c.decode(files[descriptor['choices']['path']]), 'files': files,
            'task': copy.deepcopy(loaded.prepared['task']),
            'unresolved': copy.deepcopy(descriptor['unresolved'])}


def _save_data(prepared: dict) -> dict:
    if prepared['task']['execution'] != 'authored':
        raise ValueError('this operation requires a saved authored revision')
    revision = prepared['authored_revision']
    return {'revision': prepared['run'], 'task_id': prepared['task']['task_id'],
            'state': revision['state'], 'artifact': copy.deepcopy(revision['artifact'])}


def _latest(rows, event: str):
    return next((row for row in reversed(rows) if row['event'] == event), None)


def _saved(prepared: dict, rows):
    saved = _latest(rows, 'authored-save')
    if saved is None or saved['data'] != _save_data(prepared):
        raise ValueError('record the authored save before its delivery, review or completion')
    return saved



def _delivery(prepared: dict, receipt: dict, read) -> dict:
    import production_workflow as workflow
    workflow.schema_check(receipt, 'authored-delivery')
    evidence = receipt['evidence']
    evidence_raw = read(evidence['path'])
    if 'field' in evidence:
        from request_contract import get
        observed = get(c.decode(evidence_raw), evidence['field'])
    else:
        observed = evidence_raw.decode('utf-8')
    c.text(observed, 'actual delivery evidence')
    artifact = prepared['authored_revision']['artifact']
    delivered = read(receipt['artifact']) if 'artifact' in receipt else observed.encode('utf-8')
    if c.digest(delivered) != artifact['sha256'] or len(delivered) != artifact['size']:
        raise ValueError('actual delivered content differs from this saved revision')
    return {'recipient': receipt['recipient'], 'channel': receipt['channel'],
            'kind': 'attachment' if 'artifact' in receipt else 'text',
            'state': prepared['authored_revision']['state'],
            'evidence_path': evidence['path'], 'evidence_field': evidence.get('field'),
            'evidence_sha256': c.digest(evidence_raw), 'note': receipt['note']}


def deliver(root: Path, run: str, receipt_file: str | None = None, *, destination: str | None = None) -> dict:
    """Copy exact saved bytes locally, or retain actual external delivery evidence.

    Exclusive file publication precedes its event. An interruption between them
    leaves the complete file; retry verifies those bytes and records that fact.
    """
    import production_workflow as workflow
    if (receipt_file is None) == (destination is None):
        raise ValueError('delivery selects exactly one local destination or external evidence file')
    root = c._root(root)
    with store.transaction(root):
        loaded = workflow.read_run(root, run)
        _saved(loaded.prepared, loaded.rows)
        revision = loaded.prepared['authored_revision']
        if destination is not None:
            path = c.local(root, destination, exists=False)
            if path.is_relative_to(loaded.directory.parent.parent):
                raise ValueError('a delivery destination must be outside the Production publication namespace')
            raw = loaded.evidence.read(revision['artifact']['sha256'])
            try:
                c.atomic(path, raw)
            except FileExistsError:
                if store.stable_bytes(root, destination) != raw:
                    raise ValueError('delivery destination already contains different bytes: ' + destination) from None
            if store.stable_bytes(root, destination) != raw:
                raise ValueError('local delivery changed before its completed event')
            artifact = revision['artifact']
            observed = {'kind': 'local-file', 'path': destination, 'sha256': artifact['sha256'],
                        'size': artifact['size'], 'state': revision['state']}
            files = [{'path': destination, 'sha256': artifact['sha256'], 'size': artifact['size']}]
            return workflow.append_record(loaded.directory, loaded.prepared, loaded.rows, 'authored-delivery',
                {'revision': run, 'artifact_sha256': artifact['sha256'], 'receipt': None,
                 'delivery': observed, 'files': files})
        captured = {}
        def read(path):
            if path not in captured:
                captured[path] = store.stable_bytes(root, path)
            return captured[path]
        receipt = c.decode(read(receipt_file))
        observed = _delivery(loaded.prepared, receipt, read)
        files = [{'path': path, 'sha256': c.object_store(loaded.directory, raw), 'size': len(raw)}
                 for path, raw in captured.items()]
        return workflow.append_record(loaded.directory, loaded.prepared, loaded.rows, 'authored-delivery',
            {'revision': run, 'artifact_sha256': revision['artifact']['sha256'],
             'receipt': receipt_file, 'delivery': observed, 'files': files})


def _review_context(prepared: dict, read_object) -> tuple[dict, bytes, dict, list[dict]]:
    """Use the saved artifact and original sources with the common review owner."""
    import production_evidence as media
    artifact = prepared['authored_revision']['artifact']
    raw = read_object(artifact['sha256'])
    kind = prepared['task']['artifact']
    if kind == 'json' and prepared['authored_revision']['state'] == 'draft':
        try:
            c.decode(raw)
        except ValueError:
            kind = 'text'
    measured = (media.inspect(raw, kind) if raw else
                {'kind': 'text', 'bytes': 0, 'lines': 0})
    candidate = {'sha256': artifact['sha256'], 'data': {'media': measured}}
    material, evidence = {}, []
    dependencies = {item['path']: item for item in prepared['dependencies'] if item['space'] != 'skill'}
    originals = {item['source']['id']: item for item in (prepared['task'].get('authored_basis') or {}).get('sources', [])}
    prefix = 'production/runs/' + prepared['run'] + '/objects/'

    def add(identifier: str, source: dict, item: dict, relation: str) -> None:
        contents = read_object(item['sha256'])
        source_kind = source.get('format', 'text')
        if source_kind not in media.KINDS:
            source_kind = 'binary'
        try:
            source_media = media.inspect(contents, source_kind) if contents else {'kind': source_kind, 'bytes': 0, 'lines': 0}
        except (UnicodeError, ValueError):
            source_kind = 'binary'
            source_media = media.inspect(contents, source_kind)
        material[identifier] = (contents, source_media)
        evidence.append({'id': identifier, 'path': prefix + item['sha256'], 'kind': source_kind,
                         'relation': relation, 'limitations': []})

    for source in prepared['task'].get('sources', []):
        current = dependencies.get(source['path'])
        original = originals.get(source['id'])
        if original is not None:
            add('source:' + source['id'], original['source'], original['file'],
                'Original selected source in its recorded scope: ' + str(original['source'].get('use', source['id'])))
            if current is not None and current['sha256'] != original['file']['sha256']:
                add('adaptation:' + source['id'], source, current,
                    'Authored adaptation; compare it with source:' + source['id'])
        elif current is not None:
            add('source:' + source['id'], source, current,
                'Selected source in its recorded scope: ' + str(source.get('use', source['id'])))
    return candidate, raw, material, evidence


def draft_review(prepared: dict) -> dict:
    """An unanswered common review form bound to the saved artifact."""
    return {'input_sha256': prepared['input_sha256'],
            'candidate': prepared['authored_revision']['artifact']['sha256'], 'reviewer': '',
            'evidence': [], 'observations': [],
            'checks': [{'criterion': item['id'], 'verdict': 'not-assessed',
                        'observation_indices': [], 'reason': ''} for item in prepared['task'].get('criteria', [])],
            'repairs': [], 'unresolved': [], 'conclusion': ''}


def review_basis(loaded) -> dict:
    """Expose the original commission and evidence independently of the rendition."""
    prepared = loaded.prepared
    task = prepared['task']
    origin = (task.get('authored_basis') or {}).get('origin_task', task)
    _, _, _, evidence = _review_context(prepared, loaded.evidence.read)
    artifact = prepared['authored_revision']['artifact']
    return {'revision': prepared['run'], 'input_sha256': prepared['input_sha256'],
            'purpose': task.get('direction', {}).get('purpose'),
            'intended_effect': task.get('direction', {}).get('intended_effect'),
            'commission': copy.deepcopy(origin.get('direction', {})),
            'original_criteria': copy.deepcopy(origin.get('criteria', [])),
            'direction': copy.deepcopy(task.get('direction', {})),
            'criteria': copy.deepcopy(task.get('criteria', [])),
            'evidence': evidence, 'sources': copy.deepcopy((task.get('authored_basis') or {}).get('sources', [])),
            'artifact': {**artifact, 'path': str(loaded.directory / artifact['path'])},
            'unresolved': copy.deepcopy(prepared['authored_revision']['unresolved']),
            'draft': draft_review(prepared),
            'instruction': 'Read the exact saved artifact before assessing it against the original commission '
                'and source documents. source:ID names the original; adaptation:ID names a separate authored '
                'rendition. Current criteria and automatic target checks do not redefine source meaning. '
                'A prompt review assesses the text and what it instructs, without claiming a generated image.'}


def _review(prepared: dict, value: dict, read_object, read_evidence) -> dict:
    import production_workflow as workflow
    import production_evidence as media
    workflow.schema_check(value, 'review')
    candidate, raw, material, evidence = _review_context(prepared, read_object)
    for spec in value['evidence']:
        if spec['id'] == 'candidate' or spec['id'] in material:
            raise ValueError('duplicate or reserved evidence id')
        contents = read_evidence(spec['path'])
        material[spec['id']] = (contents, media.inspect(contents, spec['kind']))
    reviewed = copy.deepcopy(value)
    reviewed['evidence'] = evidence + reviewed['evidence']
    workflow.validate_review(reviewed, prepared, candidate, raw, material)
    return reviewed


def review(root: Path, run: str, review_file: str) -> dict:
    """Record a common evidence-backed review of the exact saved artifact."""
    import production_workflow as workflow
    with store.transaction(root):
        loaded = workflow.read_run(root, run)
        _saved(loaded.prepared, loaded.rows)
        raw = store.stable_bytes(root, review_file)
        captured = {}
        def read(path):
            if path not in captured:
                captured[path] = store.stable_bytes(root, path)
            return captured[path]
        value = _review(loaded.prepared, c.decode(raw), loaded.evidence.read, read)
        file = {'path': review_file, 'sha256': c.object_store(loaded.directory, raw), 'size': len(raw)}
        evidence = [{'path': path, 'sha256': c.object_store(loaded.directory, body), 'size': len(body)}
                    for path, body in sorted(captured.items())]
        recorded = {'revision': run, 'artifact_sha256': loaded.prepared['authored_revision']['artifact']['sha256'],
                    'review': value, 'files': [file], 'evidence': evidence}
        previous = _latest(loaded.rows, 'authored-review')
        if previous is not None and {key: item for key, item in previous['data'].items() if key != 'previous_review'} == recorded:
            return previous
        return workflow.append_record(loaded.directory, loaded.prepared, loaded.rows, 'authored-review',
            {**recorded, 'previous_review': previous['sha256'] if previous else None})


def _review_evaluation(prepared: dict, rows) -> tuple[str, list[str]]:
    import production_workflow as workflow
    reviewed = _latest(rows, 'authored-review')
    return workflow.review_evaluation(prepared['task'].get('criteria', []),
                                      reviewed['data']['review'] if reviewed else None)


def pending(prepared: dict, rows) -> list[str]:
    """One outcome rule for completion, status and continuation."""
    missing = [name for name, event in [('save', 'authored-save'), ('delivery', 'authored-delivery')]
               if (name == 'save' or name in requirements(prepared['task'])) and _latest(rows, event) is None]
    evaluation, unassessed = _review_evaluation(prepared, rows)
    if 'review' in requirements(prepared['task']) and (evaluation == 'unreviewed' or unassessed):
        missing.append('review')
    if completion_state(prepared['task']) == 'finished' and prepared['authored_revision']['state'] != 'finished':
        missing.insert(0, 'finished-revision')
    return missing


def completion_data(prepared: dict, rows) -> dict:
    """The actual facts that satisfy this revision's commissioned obligations."""
    saved = _saved(prepared, rows)
    delivery = _latest(rows, 'authored-delivery')
    reviewed = _latest(rows, 'authored-review')
    needed = requirements(prepared['task'])
    missing = pending(prepared, rows)
    if missing:
        raise ValueError('authored completion still requires actual ' + ', '.join(missing) + ' for this revision')
    return {'scope': 'authored', 'run': prepared['run'], 'revision': prepared['run'],
            'task_id': prepared['task']['task_id'], 'saved': saved['sha256'], 'requirements': needed,
            'completion_state': completion_state(prepared['task']),
            'state': prepared['authored_revision']['state'],
            'delivery': delivery['sha256'] if 'delivery' in needed else None,
            'review': reviewed['sha256'] if 'review' in needed else None}


def validate_event(prepared: dict, rows, event: str, data: dict, read_object) -> None:
    """Use identical authored event contracts for append and historical replay."""
    if event == 'authored-save':
        if data != _save_data(prepared):
            raise ValueError('authored save differs from its published revision')
        return
    if event == 'completion':
        if data != completion_data(prepared, rows):
            raise ValueError('authored completion differs from its actual saved results')
        return
    if event not in EVENTS:
        return
    _saved(prepared, rows)
    expected = {'revision', 'artifact_sha256', 'files'} | (
        {'receipt', 'delivery'} if event == 'authored-delivery' else {'review', 'evidence', 'previous_review'})
    c.exact(data, expected, 'authored event')
    if data['revision'] != prepared['run'] or data['artifact_sha256'] != prepared['authored_revision']['artifact']['sha256']:
        raise ValueError('authored event belongs to another revision or artifact')
    records = {row['path']: row for row in data['files'] + data.get('evidence', [])}
    def read(path):
        record = records[path]
        raw = read_object(record['sha256'])
        if c.digest(raw) != record['sha256'] or len(raw) != record['size']:
            raise ValueError('authored event evidence differs from its recorded bytes')
        return raw
    if event == 'authored-delivery':
        if data['delivery']['kind'] == 'local-file':
            artifact = prepared['authored_revision']['artifact']
            target = data['delivery']['path']
            expected = {'kind': 'local-file', 'path': target, 'sha256': artifact['sha256'],
                        'size': artifact['size'], 'state': prepared['authored_revision']['state']}
            if (data['receipt'] is not None or data['delivery'] != expected
                    or data['files'] != [{'path': target, 'sha256': artifact['sha256'], 'size': artifact['size']}]
                    or read(target) != read_object(artifact['sha256'])):
                raise ValueError('local authored delivery differs from its saved artifact')
        else:
            receipt = c.decode(read(data['receipt']))
            if data['delivery'] != _delivery(prepared, receipt, read):
                raise ValueError('authored delivery differs from its actual evidence')
    else:
        if len(data['files']) != 1:
            raise ValueError('authored review must retain its supplied report')
        value = c.decode(read(data['files'][0]['path']))
        if _review(prepared, value, read_object, read) != data['review']:
            raise ValueError('authored review differs from its supplied report')
        previous = _latest(rows, 'authored-review')
        if data['previous_review'] != (previous['sha256'] if previous else None):
            raise ValueError('authored review differs from its recorded predecessor')


def status(root: Path, loaded, *, logs: list | None = None) -> dict:
    """Project saved, delivered and reviewed facts for this exact authored revision."""
    root = c._root(root)
    from cli_invocation import python_argv
    import production_workflow as workflow
    prepared, rows = loaded.prepared, loaded.rows
    run = prepared['run']
    revision = prepared['authored_revision']
    saved, delivered, reviewed = (_latest(rows, name) for name in
                                  ('authored-save', 'authored-delivery', 'authored-review'))
    completed, abandoned = _latest(rows, 'completion'), _latest(rows, 'abandoned')
    needed = requirements(prepared['task'])
    missing = pending(prepared, rows)
    evaluation, unassessed = _review_evaluation(prepared, rows)
    review_state = 'unreviewed' if evaluation == 'unreviewed' else 'partial' if unassessed else 'complete'
    next_action = None
    if not completed and not abandoned:
        if saved is None:
            command, arguments, reason = 'record-save', [], 'Record the already published authored revision; no external result is needed.'
        elif 'finished-revision' in missing:
            command, arguments, reason = 'draft-inputs', ['--from-run', run, '--out-dir', '<editable-directory>'], 'Continue the saved draft and save a finished revision for this requested result.'
        elif 'delivery' in missing:
            command, arguments, reason = 'deliver', ['--to', '<delivery-path>'], 'Copy this exact saved revision to its requested local destination, or use --file for actual external presentation or attachment evidence.'
        elif 'review' in missing:
            command, arguments, reason = 'review-authored', ['--file', '<actual-review.json>'], 'Read the saved artifact and its independent review basis, then record the evidence-backed assessment.'
        else:
            command, arguments, reason = 'finish', [], 'The requested authored results exist; finish the owning work task after resolving its open author questions.'
        selected = [] if command == 'draft-inputs' else ['--run', run]
        script = 'work_ledger.py' if command == 'finish' else 'production_workflow.py'
        root_option = '--studio' if command == 'finish' else '--root'
        next_action = {'command': command, 'argv': python_argv(workflow.ROOT / 'scripts' / script,
            command, root_option, str(root), *selected, *arguments), 'reason': reason}
    return {'run': run, 'task_id': prepared['task']['task_id'], 'integrity': 'intact',
            'preparation': 'authored', 'readiness': 'saved' if saved else 'published',
            'readiness_diagnostics': [], 'submission': 'not-applicable', 'send_started': False,
            'effects': [], 'capture': 'not-applicable', 'capture_diagnostics': [],
            'registration': 'work-task', 'review': review_state,
            'task_disposition': 'completed' if completed else 'abandoned' if abandoned else 'open',
            'authored': {'state': revision['state'], 'input_verified': revision['input_verified'],
                'saved': saved['sha256'] if saved else None, 'delivered': delivered['sha256'] if delivered else None,
                'reviewed': reviewed['sha256'] if reviewed else None, 'requirements': needed,
                'completion_state': completion_state(prepared['task']),
                'missing': missing, 'unresolved': copy.deepcopy(revision['unresolved']),
                'artifact': str(loaded.directory / revision['artifact']['path'])},
            'candidates': [], 'candidate_states': [], 'freshness_diagnostics': [],
            'selection_diagnostics': [], 'selection_ready': False, 'settlement_open': False,
            'execution': None, 'journal': None, 'logs': logs or [], 'authentication': None,
            'cleanup': {'state': 'not-needed', 'eligible': False, 'uploaded': 0, 'deleted': 0,
                        'retained': 0, 'items': []}, 'next_action': next_action}
