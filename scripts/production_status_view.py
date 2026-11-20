"""Project current status for navigation while keeping complete judgment views explicit."""
from __future__ import annotations

from pathlib import Path

from production_report_view import action, authority, authorization_requirements, authoring_state
from production_report_view import brief, diagnostics, execution_records, fields, DETAIL_LIMIT


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
    result['details_action'] = action(root, 'status',
        (['--run', run] if run is not None else []) + ['--view', 'full'],
        'Inspect complete current status, including authority declarations and authored source content.')
    current = report.get('current_task')
    if current is not None:
        shown = fields(current, ('task_id', 'goal', 'next', 'production_run', 'focus',
                                 'next_actions', 'authoring_action'))
        shown['diagnostics'] = diagnostics(current.get('diagnostics'))
        if current.get('authoring'):
            shown['authoring'] = authoring_state(root, current['authoring'])
        if current.get('work_completion'):
            shown['work_completion'] = brief(current['work_completion'])
        result['current_task'] = shown
    for original in report.get('runs', []):
        item = fields(original, ('run', 'task_id', 'integrity', 'preparation', 'readiness',
            'submission', 'send_started', 'effects', 'capture', 'registration', 'review',
            'task_disposition', 'candidates', 'selection_ready', 'settlement_open',
            'execution', 'journal', 'next_action', 'authentication', 'adoption_actions', 'recording'))
        identifier = item['run']
        detail = action(root, 'status', ['--run', identifier, '--view', 'full'],
            'Read this run\'s complete current evidence and authority without changing it.')
        item['details_action'] = detail
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
            'diagnostics': diagnostics([problem for row in rows for problem in row.get('diagnostics', [])])}
    if 'warnings' in report:
        result['warnings'] = diagnostics(report['warnings'])
    continuations = ([item.get('next_action') for item in result['runs']] if run is not None else
                     (result.get('current_task') or {}).get('next_actions', []))
    if run is None and ((result.get('current_task') or {}).get('authoring') or {}).get('selection_required'):
        result['next_action'] = {**action(root, 'inspect-inputs', [],
            'Choose an explicitly named editable branch; no branch was selected by this summary.'),
            'requires_author_input': True, 'alternatives': continuations}
    else:
        result['next_action'] = next((item for item in continuations if item is not None), None)
    return result
