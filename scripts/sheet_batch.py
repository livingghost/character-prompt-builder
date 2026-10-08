"""Sequential sheet fills through the existing sealed Production execution path.

A batch maps renderer requests to fully authored Production tasks. It never
invents prompts, vocabulary decisions, reference choices or author approvals.
The journal owns one prepared run per request. Recovery asks that run for its
saved answer instead of turning missing files into another submission.
"""
from __future__ import annotations
import copy
import json
from pathlib import Path
from typing import Any

import execution_contract as c
import sheet_artifacts as fills


def _relative(root: Path, path: str, *, exists: bool = True) -> Path:
    return c.local(root, path, exists=exists)


def read_plan(root: Path, plan_path: str) -> tuple[dict, dict]:
    plan = c.load(_relative(root, plan_path))
    from state_protocol import validate_against_schema
    errors = validate_against_schema(plan, c.load(Path(__file__).resolve().parents[1] / 'schemas/authoring/sheet-fill-plan.schema.json'))
    if errors: raise ValueError('invalid sheet fill plan: ' + '; '.join(errors))
    c.exact(plan, {'artifact_type', 'manifest', 'sheet', 'results', 'panels'}, 'sheet fill plan')
    if plan['artifact_type'] != 'sheet-fill-plan':
        raise ValueError('expected a sheet-fill-plan')
    manifest = c.load(_relative(root, plan['manifest']))
    if not isinstance(manifest.get('requests'), list) or not manifest['requests']:
        raise ValueError('the panel manifest must contain requests')
    _relative(root, plan['sheet']); _relative(root, plan['results'], exists=False)
    requests = {}
    names = set()
    for request in manifest['requests']:
        key = c.text(request.get('request_id'), 'request id')
        name = c.text(request.get('result_file'), 'result file')
        if Path(name).name != name or '\\' in name or not name.lower().endswith('.png') or name.casefold() in names:
            raise ValueError('each result_file must be a unique plain PNG filename')
        if key in requests:
            raise ValueError('duplicate request id')
        c.text(request.get('resolved_slot_id'), 'resolved slot id')
        if type(request.get('generation_stage')) is not int or request['generation_stage'] < 1:
            raise ValueError('each panel needs a positive generation_stage')
        target = request.get('target')
        if not isinstance(target, dict) or any(type(target.get(key)) is not int or target[key] < 1 for key in ('generation_w', 'generation_h')):
            raise ValueError('each manifest panel must declare its positive generation dimensions')
        requests[key] = request; names.add(name.casefold())
    if not isinstance(plan['panels'], list) or not plan['panels']:
        raise ValueError('name at least one explicitly authored panel task')
    seen = set(); tasks = set()
    for panel in plan['panels']:
        c.exact(panel, {'request_id', 'task', 'references'}, 'panel task')
        key = panel['request_id']
        if key not in requests or key in seen:
            raise ValueError('panel tasks must identify distinct manifest requests')
        seen.add(key); _relative(root, panel['task'])
        if panel['task'] in tasks:
            raise ValueError('each panel needs a distinct authored task path')
        tasks.add(panel['task'])
        if not isinstance(panel['references'], list):
            raise ValueError('references must be an explicit list of accepted artifact selectors')
        refs = set()
        for source in panel['references']:
            c.exact(source, {'slot', 'artifact_id', 'role'}, 'accepted reference')
            c.text(source['slot'], 'reference slot'); c.text(source['role'], 'reference role')
            if source['artifact_id'] is not None: c.sha(source['artifact_id'])
            if source['slot'] in refs:
                raise ValueError('duplicate selected reference artifact')
            refs.add(source['slot'])
    return plan, manifest


def _request(manifest: dict, key: str) -> dict:
    return next(row for row in manifest['requests'] if row['request_id'] == key)


def _validate_job(root: Path, plan: dict, manifest: dict, panel: dict) -> dict:
    import production_workflow as workflow
    import studio
    task = c.load(_relative(root, panel['task']))
    workflow.validate_task(task)
    request = _request(manifest, panel['request_id'])
    recording = task.get('recording') or {}
    if task['execution'] != 'dispatcher' or task.get('artifact') != 'image' or not task.get('generation'):
        raise ValueError('a panel fill needs a dispatcher image-generation task')
    if recording.get('sheet_panel') is not True or recording.get('slot') != request['resolved_slot_id']:
        raise ValueError('the task must explicitly record this sheet panel')
    expected_sheet = studio.character_home(root, recording['character']) / 'sheet/sheet-data.json'
    if expected_sheet != _relative(root, plan['sheet']):
        raise ValueError('the task recording character does not own the selected sheet')
    if task['generation']['count'] != 1:
        raise ValueError('a panel request records exactly one returned artwork')
    state = fills._read(expected_sheet)
    for reference in panel['references']:
        source = fills.current_artifact(state['slots'].get(reference['slot']))
        if source is None or (reference['artifact_id'] is not None and source['artifact_id'] != reference['artifact_id']):
            raise ValueError('a selected reference is not the exact current accepted artifact: ' + reference['slot'])
        fills.verify_acceptance(state['slots'][reference['slot']]['current'], expected_sheet.parent, reference['slot'])
    # A later stage must cite its accepted anchor, not every canonical view.
    chosen = {reference['slot'] for reference in panel['references']}
    for required in request['required_accepted_reference_results']:
        slot = _request(manifest, required)['resolved_slot_id']
        if slot not in chosen:
            raise ValueError('this panel requires an explicitly selected accepted anchor: ' + slot)
    return task


def _verify_request_references(root: Path, plan: dict, panel: dict, run: str, selected: list[dict]) -> None:
    """Verify the pinned accepted artifacts, not whatever occupies their slots later."""
    import production_execution as execution
    compiled = execution.compiled(root, run)
    package, rendered = compiled[4], compiled[5]
    manifest = c.load(_relative(root, plan['manifest']))
    target = _request(manifest, panel['request_id'])['target']
    parameters = package['render_contract']['parameters']
    if (parameters.get('width'), parameters.get('height')) != (target['generation_w'], target['generation_h']):
        raise ValueError('the authored request dimensions differ from the panel manifest; choose supported panel geometries before rendering')
    current = fills._read(_relative(root, plan['sheet']))
    expected = []
    for source in selected:
        artifact = fills.current_artifact(current['slots'].get(source['slot']))
        if artifact != source['artifact']:
            raise ValueError('the accepted reference changed after this panel was prepared: ' + source['slot'])
        fills.verify_artifact(artifact, _relative(root, plan['sheet']).parent)
        expected.append(artifact['image']['sha256'])
    actual = [item['sha256'] for item in rendered['media']]
    if sorted(expected) != sorted(actual):
        raise ValueError('the sealed request attachments differ from the explicit accepted panel references')


def _resolve_task(root: Path, plan: dict, panel: dict, entry: dict, state_file: Path) -> str:
    """Bind declared slots at preparation, preserving all authored creative inputs.

    A null artifact selector means the explicitly adopted current image at this
    boundary, never a candidate. The chosen bytes are then pinned and presented
    by normal Production approval. No prompt, model mode or control is invented.
    """
    task = c.load(_relative(root, panel['task']))
    sheet = _relative(root, plan['sheet'])
    if entry['selected_references'] is None:
        document = fills._read(sheet)
        entry['selected_references'] = [{'slot': ref['slot'], 'role': ref['role'],
                'artifact': fills.current_artifact(document['slots'].get(ref['slot']))}
                for ref in panel['references']]
    selected = entry['selected_references']
    if not selected:
        entry['compiled_task'] = panel['task']
        return panel['task']
    from prepare_generation_references import prepare_references
    directory = _relative(root, entry['inputs'], exists=False) / 'resolved'
    directory.mkdir(parents=True, exist_ok=True)
    sources = []
    for row in selected:
        artifact = row['artifact']
        fills.verify_artifact(artifact, sheet.parent)
        sources.append({'role': row['role'], 'source': {'kind': 'supplied-file',
                        'reference_id': artifact['artifact_id'],
                        'resolved_path': str(fills._file(sheet.parent, artifact['image']['path']))}})
    specification = c.load(_relative(root, task['generation']['production_spec']))
    references = directory / 'references.json'
    if references.exists():
        # Publication can have completed before the batch journal was saved.
        prepared = c.load(references)
        actual = [row['source']['sha256'] for row in prepared['selected_references']]
        if actual != [row['artifact']['image']['sha256'] for row in selected]:
            raise ValueError('the frozen batch reference preparation differs from its selected artifacts')
    else:
        prepared = prepare_references(sources, model=specification['target_model'], output_dir=directory / 'references',
                max_side=max(max(row['artifact']['image']['width'], row['artifact']['image']['height']) for row in selected))
        c.atomic(references, c.encoded(prepared))
    task['generation']['references'] = references.relative_to(root).as_posix()
    target = directory / 'task.json'; _same_file(target, c.encoded(task))
    entry['compiled_task'] = target.relative_to(root).as_posix()
    return entry['compiled_task']


def _same_file(path: Path, raw: bytes) -> None:
    if path.exists():
        if c.read(path) != raw:
            raise ValueError('an immutable batch output already contains different bytes: ' + str(path))
    else:
        c.atomic(path, raw)


def initialize(root: Path, plan_path: str, state_path: str | None = None) -> dict:
    """Own a dated attempt, freeze its inputs, and reserve every result before sending."""
    import studio_activity as activity
    from pack_manager import generate_uuid7
    with c.lock(root):
        plan, manifest = read_plan(root, plan_path)
        original_sha = c.sha256_file(_relative(root, plan_path))
        if state_path is not None:
            target = _relative(root, state_path, exists=False)
            if target.exists():
                state = load(root, state_path)
                if state['plan'] != plan_path or state['plan_sha256'] != original_sha:
                    raise ValueError('BATCH_PLAN_CONFLICT: this journal belongs to another plan or snapshot')
                if state['source_manifest_sha256'] != c.sha256_file(_relative(root, plan['manifest'])):
                    raise ValueError('BATCH_PLAN_CONFLICT: the renderer manifest changed')
                for panel in plan['panels']:
                    if state['panels'][panel['request_id']]['task_sha256'] != c.sha256_file(_relative(root, panel['task'])):
                        raise ValueError('BATCH_PLAN_CONFLICT: a batch task changed; create a new attempt')
                _register(root, state)
                return state
        identifier, created = generate_uuid7(), activity.timestamp()
        home_path = plan['results'].rstrip('/') + '/' + created[:10] + '/' + created[11:26].replace(':', '').replace('.', '') + 'Z-' + identifier
        home = _relative(root, home_path, exists=False)
        if home.exists():
            raise ValueError('batch attempt directory already exists')
        home.mkdir(parents=True)
        state_path = state_path or home_path + '/batch.json'
        target = _relative(root, state_path, exists=False)
        frozen = copy.deepcopy(plan)
        frozen['manifest'] = home_path + '/inputs/manifest.json'
        _same_file(_relative(root, frozen['manifest'], exists=False), c.encoded(manifest))
        panels = {}
        for panel in frozen['panels']:
            key = panel['request_id']; source_task = panel['task']
            slug = ''.join(ch if ch.isascii() and (ch.isalnum() or ch in '._-') else '-' for ch in key)[:64].strip('.') or 'panel'
            slug += '-' + c.digest(key.encode())[:10]
            folder = home_path + '/panels/' + slug
            task_raw = c.read(_relative(root, source_task))
            panel['task'] = folder + '/inputs/task.json'
            _same_file(_relative(root, panel['task'], exists=False), task_raw)
            outputs = folder + '/results'
            owner = {'batch_id': identifier, 'request_id': key, 'state': state_path}
            _same_file(_relative(root, outputs + '/owner.json', exists=False), c.encoded(owner))
            panels[key] = {'source_task': source_task, 'task_sha256': c.digest(task_raw),
                           'inputs': folder + '/inputs', 'results': outputs, 'owner': owner,
                           'run': None, 'compiled_task': None, 'selected_references': None,
                           'status': 'unprepared', 'artifact': None, 'diagnostic': None}
        snapshot_path = home_path + '/inputs/plan.json'
        _same_file(_relative(root, snapshot_path, exists=False), c.encoded(frozen))
        state = {'artifact_type': 'sheet-fill-batch', 'batch_id': identifier,
                 'created_at': created, 'updated_at': created, 'state': state_path, 'home': home_path,
                 'plan': plan_path, 'plan_sha256': original_sha,
                 'source_manifest_sha256': c.sha256_file(_relative(root, plan['manifest'])),
                 'snapshot': snapshot_path, 'snapshot_sha256': c.sha256_file(_relative(root, snapshot_path)),
                 'manifest_sha256': c.sha256_file(_relative(root, frozen['manifest'])), 'panels': panels}
        c.atomic(target, c.encoded(state))
        _register(root, state)
        activity.changed(target, 'batch-created', revision=c.content_id(state),
                         details={'batch_id': identifier, 'plan': plan_path, 'home': home_path, 'panels': len(panels)})
        return state


def _register(root: Path, state: dict) -> None:
    """Small immutable ownership index; status never searches all production runs."""
    index = {key: state[key] for key in ('batch_id', 'created_at', 'state', 'home', 'plan')}
    target = c.local(root, 'work/batches/' + state['batch_id'] + '.json', exists=False)
    _same_file(target, c.encoded(index))


def list_batches(root: Path, *, limit: int = 50, offset: int = 0) -> dict:
    """Discover attempt journals with page-local diagnostics, newest first."""
    import studio_activity as activity
    if type(limit) is not int or not 1 <= limit <= 500 or type(offset) is not int or offset < 0:
        raise ValueError('limit must be 1..500 and offset must be nonnegative')
    rows, diagnostics = [], []
    for path in (root / 'work/batches').glob('*.json'):
        try:
            item = c.load(path)
            if item['batch_id'] != path.stem:
                raise ValueError('batch index identity differs')
            rows.append(item)
        except (ValueError, OSError, KeyError, TypeError) as exc:
            diagnostics.append({'path': path.relative_to(root).as_posix(), 'message': str(exc)})
    rows.sort(key=lambda item:(activity.chronological(item['created_at']), item['batch_id']), reverse=True)
    page = []
    for item in rows[offset:offset+limit]:
        result = copy.deepcopy(item)
        try:
            held = load(root,item['state'])
            if held['batch_id'] != item['batch_id']:
                raise ValueError('journal ownership differs from batch index')
            result['panels'] = {key:{'status':entry['status'],'run':entry['run']} for key,entry in held['panels'].items()}
            result['availability'] = 'readable'
        except (ValueError, OSError, KeyError, TypeError) as exc:
            result.update(availability='unavailable', diagnostic=str(exc))
        page.append(result)
    return {'ok':True, 'order':'created_at_desc', 'entries':page, 'total':len(rows), 'offset':offset, 'limit':limit,
            'next_offset':offset+limit if offset+limit<len(rows) else None, 'diagnostics':diagnostics}


def snapshot(root: Path, state: dict) -> tuple[dict, dict]:
    path = _relative(root, state['snapshot'])
    if c.sha256_file(path) != state['snapshot_sha256']:
        raise ValueError('the frozen batch plan changed')
    plan = c.load(path)
    manifest_path = _relative(root, plan['manifest'])
    if c.sha256_file(manifest_path) != state['manifest_sha256']:
        raise ValueError('the frozen renderer manifest changed')
    return plan, c.load(manifest_path)


def load(root: Path, state_path: str) -> dict:
    state = c.load(_relative(root, state_path))
    if state.get('artifact_type') != 'sheet-fill-batch' or state.get('state') != state_path:
        raise ValueError('expected the named sheet-fill-batch journal')
    snapshot(root, state)
    return state


def _source_unchanged(root: Path, panel: dict, entry: dict) -> None:
    frozen = _relative(root, panel['task'])
    if c.sha256_file(frozen) != entry['task_sha256']:
        raise ValueError('the frozen batch task changed')
    source = _relative(root, entry['source_task'], exists=False)
    if source.exists() and c.sha256_file(source) != entry['task_sha256']:
        raise ValueError('a batch task changed; author a new task and new redo batch')


def _save(root: Path, state_path: str, state: dict) -> None:
    import studio_activity as activity
    path = _relative(root, state_path)
    if c.load(path) == state:
        return
    state['updated_at'] = activity.timestamp()
    c.atomic_write_json(path, state)
    activity.changed(path, 'batch-progress', revision=c.content_id(state), refresh_views=False,
                     details={'batch_id': state['batch_id'],
                              'panels': {key: {'run': row['run'], 'status': row['status'], 'diagnostic': row['diagnostic']}
                                         for key, row in state['panels'].items()}})


def _output_preflight(root: Path, entry: dict, *, before_send: bool) -> Path:
    folder = _relative(root, entry['results'])
    if c.load(c.local(folder, 'owner.json')) != entry['owner']:
        raise ValueError('BATCH_OUTPUT_OWNER_CONFLICT: results belong to another attempt')
    if before_send and any(path.name != 'owner.json' for path in folder.iterdir()):
        raise ValueError('BATCH_OUTPUT_CONFLICT: output files exist before the first send')
    return folder


def _export(root: Path, plan: dict, manifest: dict, panel: dict, entry: dict) -> dict | None:
    import production_workflow as workflow
    import studio
    _, prepared, _, _ = workflow.load_run(root, entry['run'])
    character = prepared['task']['recording']['character']
    home = studio.character_home(root, character)
    rows = [row for row in studio.read_iterations(home)
            if (row.get('production') or {}).get('run') == entry['run']]
    if not rows:
        return None
    if len(rows) != 1:
        raise ValueError('one panel request must project exactly one Studio iteration')
    row = rows[0]
    artifact = fills.from_iteration(root, character, row)
    sheet = _relative(root, plan['sheet']).parent
    provenance = fills.verify_artifact(artifact, sheet)
    source = fills._file(sheet, artifact['provenance']['path']).parent
    folder = _output_preflight(root, entry, before_send=False)
    request = _request(manifest, panel['request_id']); filename = request['result_file']; stem = Path(filename).stem
    target = request['target']
    if (artifact['image']['width'], artifact['image']['height']) != (target['generation_w'], target['generation_h']):
        raise ValueError('received image dimensions differ from the manifest; exact bytes remain in Studio')
    raw = c.read(fills._file(sheet, artifact['image']['path'], artifact['image']['sha256']))
    if artifact['image']['media_type'] != 'image/png':
        raise ValueError('the panel manifest requests PNG; preserve non-PNG received bytes in Studio and author a local conversion')
    _same_file(folder / filename, raw)
    for name in provenance['files']:
        contents = c.read(c.local(source, name))
        if name in {'package.json', 'request.json', 'response.json', 'answer.json'}:
            out = folder / (stem + '.' + name)
        else:
            out = c.local(folder, name, exists=False)
        _same_file(out, contents)
    marker = {'artifact_type': 'sheet-fill-result', 'request_id': panel['request_id'],
              'run': entry['run'], 'character': character, 'iteration_id': row['iteration_id'],
              'batch_id': entry['owner']['batch_id'], 'generated_at': row['at'],
              'sheet': plan['sheet'], 'artifact': artifact,
              'files': {'image': filename, 'package': stem + '.package.json', 'request': stem + '.request.json',
                        'response': stem + '.response.json', 'answer': stem + '.answer.json'}}
    # The marker is the last output, never a claim that incomplete copies are complete.
    _same_file(folder / (stem + '.artifact.json'), c.encoded(marker))
    # This pointer is a rebuildable convenience, never the owner of an image.
    with c.lock(root):
        latest_path = _relative(root, plan['results'].rstrip('/') + '/latest.json', exists=False)
        latest = c.load(latest_path) if latest_path.exists() else {'artifact_type': 'sheet-fill-latest', 'panels': {}}
        old = latest['panels'].get(panel['request_id'])
        from studio_activity import chronological
        if old is None or (chronological(row['at']), entry['run']) >= (chronological(old['generated_at']), old['run']):
            latest['panels'][panel['request_id']] = {'run': entry['run'], 'batch_id': entry['owner']['batch_id'],
                'generated_at': row['at'], 'result': (folder / filename).relative_to(root).as_posix(),
                'marker': (folder / (stem + '.artifact.json')).relative_to(root).as_posix(),
                'artifact_id': artifact['artifact_id']}
            c.atomic_write_json(latest_path, latest)
    return artifact


def advance(root: Path, state_path: str, *, grant: str | None = None,
            decisions: dict[str, str] | None = None, unreceived_only: bool = False) -> dict:
    """Advance independent jobs; recover started requests without consulting raw author drafts."""
    import production_workflow as workflow
    import production_execution as execution
    import production_store as store
    import studio_activity as activity
    from pack_manager import generate_uuid7
    state_file = _relative(root, state_path)
    lock_root = state_file.parent / ('.' + state_file.stem + '.lock')
    lock_root.mkdir(parents=True, exist_ok=True)
    with c.lock(lock_root):
        state = load(root, state_path)
        plan, manifest = snapshot(root, state)
        decisions = decisions or {}
        if set(decisions) - set(state['panels']):
            raise ValueError('execution decisions name an unknown batch panel')
        positions = {row['request_id']: index for index, row in enumerate(manifest['requests'])}
        ordered = sorted(plan['panels'], key=lambda row: (_request(manifest, row['request_id'])['generation_stage'], positions[row['request_id']]))
        for panel in ordered:
            key = panel['request_id']; entry = state['panels'][key]
            try:
                # The reserved identity is journaled BEFORE prepare. Recovery
                # inspects only that owner, never every past run in the Studio.
                has_run = entry['run'] is not None and workflow.run_dir(root, entry['run'], exists=False).exists()
                if not has_run:
                    _source_unchanged(root, panel, entry)
                    _validate_job(root, plan, manifest, panel)
                    _output_preflight(root, entry, before_send=True)
                    entry['status'] = 'preparing'
                    task_path = _resolve_task(root, plan, panel, entry, state_file)
                    entry['run'] = entry['run'] or generate_uuid7()
                    _save(root, state_path, state)
                    workflow.prepare(root, task_path, identity=entry['run'])
                    entry['status'] = 'prepared'; _save(root, state_path, state)
                else:
                    _, prepared, _, _ = workflow.load_run(root, entry['run'])
                    if prepared['task_path'] != entry['compiled_task']:
                        raise ValueError('the reserved run belongs to another panel task')
                run = entry['run']
                rows = store.event_rows(root, run)
                started = any(row['event'] in {'dispatch-claim', 'external-step', 'execution-result'} for row in rows)
                if started:
                    report = ({'ok': True} if unreceived_only and entry['status'] == 'received'
                              else execution.resume(root, run))
                    artifact = _export(root, plan, manifest, panel, entry)
                    entry.update(artifact=artifact, status='received' if artifact is not None else 'recovery-required',
                                 diagnostic=None if report.get('ok') else report)
                else:
                    _source_unchanged(root, panel, entry)
                    _validate_job(root, plan, manifest, panel)
                    _verify_request_references(root, plan, panel, run, entry['selected_references'])
                    _output_preflight(root, entry, before_send=True)
                    if key in decisions:
                        report = execution.execute(root, run, decisions_file=decisions[key])
                        artifact = _export(root, plan, manifest, panel, entry)
                        entry.update(artifact=artifact, status='received' if artifact is not None else 'recovery-required',
                                     diagnostic=None if report.get('ok') else report)
                    else:
                        entry['status'] = 'approval-required'
                        if grant is not None:
                            value = execution.draft_execution(root, run, grant)
                            draft = _relative(root, entry['inputs'], exists=False).parent / 'decisions/execution' / (c.content_id(value)+'.json')
                            if not draft.exists():
                                c.atomic(draft, c.encoded(value))
                            else:
                                held = c.load(draft)
                                if held.get('run') != value.get('run'):
                                    raise ValueError('the execution draft belongs to another run')
                            entry['decision_file'] = draft.relative_to(root).as_posix()
                            entry['prompt_check'] = execution.compiled(root, run)[6].get('prompt_check')
                        entry['diagnostic'] = None
            except (ValueError, OSError, KeyError, TypeError) as exc:
                from production_diagnostics import from_exception, CompilationError
                entry['diagnostic'] = {**from_exception(exc, phase='sheet-batch'), 'type': type(exc).__name__}
                if isinstance(exc, CompilationError):
                    entry['diagnostic']['report'] = exc.report
                entry['status'] = 'blocked'
            _save(root, state_path, state)
        complete = all(row['status'] == 'received' for row in state['panels'].values())
        blocked = any(row['status'] == 'blocked' for row in state['panels'].values())
        recovering = any(row['status'] == 'recovery-required' for row in state['panels'].values())
        from production_diagnostics import result_exit
        code = 0 if complete else (result_exit(row['diagnostic'] for row in state['panels'].values() if row['status']=='blocked')
                                  if blocked else (4 if recovering else 3))
        projection = activity.refresh(root)
        return {'ok': complete, 'outcome': 'complete' if complete else ('blocked' if blocked else ('recovery-required' if recovering else 'waiting')),
                'exit_code': code, 'batch': state_path,
                'batch_id': state['batch_id'], 'home': state['home'],
                'panels': copy.deepcopy(state['panels']), 'adopted': False, 'projection': projection}
