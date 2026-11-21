"""Project current status for navigation while keeping complete judgment views explicit."""
from __future__ import annotations

from pathlib import Path

from production_report_view import action, authority, authorization_requirements, authoring_state
from production_report_view import action_view, brief, collection, diagnostics, execution_records, fields
from production_report_view import actions_once, DETAIL_LIMIT


def _blockers(report: dict) -> list[dict]:
    """Locate every current finding once without repeating its full diagnostic."""
    import execution_contract as c
    result, seen = [], set()

    def add(rows, pointer, *, unresolved=False, scope='run'):
        for number, row in enumerate(rows or []):
            if row.get('severity') in {'warning', 'info'} or not (unresolved or row.get('severity') == 'error'):
                continue
            identity = row.get('id') or c.content_id(row)
            if identity in seen:
                continue
            seen.add(identity)
            current = fields(row, ('code', 'file', 'pointer', 'field', 'run'))
            current.update(diagnostic_id=identity, scope=scope, details='#' + pointer + '/' + str(number))
            if row.get('message'):
                current['message'] = row['message'][:240]
            result.append(current)

    add(report.get('diagnostics'), '/diagnostics')
    current = report.get('current_task') or {}
    add(current.get('diagnostics'), '/current_task/diagnostics', scope='work')
    add((current.get('authoring') or {}).get('diagnostics'), '/current_task/authoring/diagnostics',
        unresolved=True, scope='authoring')
    work = (((current.get('authoring') or {}).get('context') or {}).get('work') or {})
    questions = work.get('questions', [])
    for number, question in enumerate(questions):
        result.append({'question_id': question.get('question_id'), 'scope': 'work',
            'message': question['question'][:240],
            'details': '#/current_task/authoring/context/work/questions/' + str(number)})
    if work.get('blocked_on') and work['blocked_on'] not in {row['question'] for row in questions}:
        result.append({'kind': 'work-blocker', 'scope': 'work', 'message': work['blocked_on'][:240],
                       'details': '#/current_task/authoring/context/work/blocked_on'})
    for number, run in enumerate(report.get('runs', [])):
        for name in ('diagnostics', 'readiness_diagnostics', 'capture_diagnostics', 'selection_diagnostics'):
            add(run.get(name), '/runs/' + str(number) + '/' + name)
        add((run.get('authored') or {}).get('unresolved'), '/runs/' + str(number) + '/authored/unresolved',
            unresolved=True)
    return result


def summary(root: Path, report: dict, *, run: str | None = None) -> dict:
    """Show current states and continuations with bounded historical alternatives.

    This presentation performs no new reads and does not alter the acquired status.
    It cannot be used as a source of authorization or review evidence. The owning
    operations still acquire and verify their current complete inputs.
    """
    result = fields(report, ('ok', 'external_effect', 'execution_completed'))
    result.update(view='summary', runs=[], current_task=None,
                  diagnostics=diagnostics(report.get('diagnostics')),
                  execution_records=execution_records(report.get('execution_records', {})))
    if run is not None:
        result['run'] = run
    result['details_action'] = action(root, 'status',
        (['--run', run] if run is not None else []) + ['--view', 'full'],
        'Inspect complete current status, including authority declarations and authored source content.')
    current = report.get('current_task')
    if current is not None:
        shown = fields(current, ('task_id', 'goal', 'next', 'production_run', 'production_plan', 'focus', 'authoring_action'))
        collection(shown, 'next_actions', list(enumerate(current.get('next_actions', []))),
            pointer='/current_task/next_actions', project=lambda pair: action_view(pair[1],
                pointer='/current_task/next_actions/' + str(pair[0])))
        shown['diagnostics'] = diagnostics(current.get('diagnostics'))
        if current.get('authoring'):
            shown['authoring'] = authoring_state(root, current['authoring'], run=run,
                                                pointer='/current_task/authoring')
        if current.get('work_completion'):
            shown['work_completion'] = brief(current['work_completion'])
        if current.get('preparation_completion'):
            completion = current['preparation_completion']
            prepared = fields(completion, ('task_id', 'run', 'completion_scope', 'ready_to_finish',
                'finished', 'reason', 'argv', 'incomplete_steps', 'open_questions', 'blocked_on'))
            prepared['diagnostics'] = diagnostics(completion.get('diagnostics'))
            if 'prepared_input' in completion:
                prepared['evidence'] = 'full_report#/current_task/preparation_completion/prepared_input'
            shown['preparation_completion'] = prepared
        result['current_task'] = shown
    for number, original in enumerate(report.get('runs', [])):
        item = fields(original, ('run', 'task_id', 'integrity', 'preparation', 'readiness',
            'submission', 'send_started', 'effects', 'capture', 'registration', 'review',
            'task_disposition', 'candidates', 'selection_ready', 'settlement_open',
            'execution', 'journal', 'authentication', 'recording'))
        item['next_action'] = action_view(original.get('next_action'), pointer='/runs/' + str(number) + '/next_action')
        identifier = item['run']
        detail = action(root, 'status', ['--run', identifier, '--view', 'full'],
            'Read this run\'s complete current evidence and authority without changing it.')
        item['details_action'] = detail
        if 'adoption_actions' in original:
            collection(item, 'adoption_actions', original['adoption_actions'],
                pointer='/runs/' + str(number) + '/adoption_actions')
        if isinstance(item.get('recording'), dict) and 'outputs' in item['recording']:
            collection(item['recording'], 'outputs', original['recording']['outputs'],
                pointer='/runs/' + str(number) + '/recording/outputs')
        for name in ('diagnostics', 'readiness_diagnostics', 'capture_diagnostics',
                     'freshness_diagnostics', 'freshness_notices', 'selection_diagnostics'):
            if name in original:
                item[name] = diagnostics(original[name])
        if 'authority' in original:
            item['authority'] = authority(original['authority'])
            if item['authority'] is not None:
                item['authority']['read_action'] = detail
        if 'authorization_requirements' in original:
            item['authorization_requirements'] = authorization_requirements(original['authorization_requirements'])
        if 'authored' in original:
            item['authored'] = fields(original['authored'], ('state', 'input_verified', 'saved',
                'delivered', 'reviewed', 'requirements', 'completion_state', 'missing', 'artifact'))
            item['authored']['unresolved'] = diagnostics(original['authored'].get('unresolved'))
        if 'cleanup' in original:
            item['cleanup'] = fields(original['cleanup'], ('state', 'eligible', 'uploaded', 'deleted', 'retained'))
            item['cleanup']['diagnostics'] = diagnostics(original['cleanup'].get('diagnostics'))
        item['candidate_states'] = []
        for source in original.get('candidate_states', []):
            candidate = fields(source, ('run', 'candidate', 'candidate_sha256', 'evaluation', 'disposition',
                'unassessed_criteria', 'review', 'decision', 'reviewed_at', 'decided_at',
                'selection_basis', 'selection_requirements', 'selection_current'))
            candidate['selection_diagnostics'] = diagnostics(source.get('selection_diagnostics'))
            candidate['details_action'] = action(root, 'candidate-status',
                ['--run', identifier, '--candidate', candidate['candidate']],
                'Read the complete decision, exceptions and review state for this candidate.')
            item['candidate_states'].append(candidate)
        item['log_count'] = len(original.get('logs', []))
        result['runs'].append(item)
    result['inventory'] = {}
    for name in ('staging_details', 'unclaimed_journals', 'unregistered_publications'):
        rows = report.get(name, [])
        # An explicit run only displays inventory that names that run. Unknown
        # ownership remains visible through counts and the full audit action.
        selected = [row for row in rows if run is None or row.get('run', row.get('run_id')) == run]
        result['inventory'][name] = {'total': len(rows), 'matching': len(selected),
            'items': [brief(row) for row in selected[:DETAIL_LIMIT]],
            'omitted': len(rows) - min(len(selected), DETAIL_LIMIT),
            'full_report': 'full_report#/' + name,
            'diagnostics': diagnostics([problem for row in selected for problem in row.get('diagnostics', [])])}
    if 'warnings' in report:
        result['warnings'] = diagnostics(report['warnings'])
    continuations = ([item.get('next_action') for item in result['runs']] if run is not None else
                     (report.get('current_task') or {}).get('next_actions', []))
    if (run is None and not (result.get('current_task') or {}).get('production_plan')
            and ((result.get('current_task') or {}).get('authoring') or {}).get('selection_required')):
        result['next_action'] = {**action(root, 'inspect-inputs', [],
            'Choose an explicitly named editable branch; no branch was selected by this summary.'),
            'requires_author_input': True}
        collection(result['next_action'], 'alternatives', continuations, pointer='/current_task/next_actions',
            project=lambda row: action_view(row, pointer='/current_task/next_actions'))
        if not result['next_action']['alternatives_summary']['omitted']:
            result['next_action'].pop('alternatives_summary')
    else:
        result['next_action'] = action_view(next((item for item in continuations if item is not None), None),
                                           pointer='/current_task/next_actions/0')
    result['blockers'] = _blockers(result)
    return actions_once(result)
