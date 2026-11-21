"""Present an operation's acquired result and retain its complete JSON report.

These projections describe an already completed read or operation. They neither
validate inputs nor decide authority. Effect owners continue to use complete
acquired values; a report snapshot is display evidence only.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
import copy
import os
from pathlib import Path
import sys
from typing import Any

import execution_contract as c
from cli_invocation import python_argv

SCRIPT = Path(__file__).with_name('production_workflow.py')
ELIGIBLE_GRANT_LIMIT = 8
DETAIL_LIMIT = 8
VALUE_LIMIT = 12


def action(root: Path, command: str, arguments: list[str], reason: str) -> dict:
    return {'command': command,
            'argv': python_argv(SCRIPT, command, '--root', str(root), *arguments),
            'reason': reason}


def fields(value: Mapping, names) -> dict:
    """Export named display fields without modifying their acquired owner."""
    return {name: copy.deepcopy(value[name]) for name in names if name in value}


def _summary_order(value: dict) -> dict:
    """Put the outcome, executable continuation and full report before detail."""
    leading = ('view', 'command', 'ok', 'state', 'run', 'task_id', 'required_action',
               'blockers', 'next_action', 'full_report', 'full_report_sha256', 'full_report_action',
               'diagnostics', 'unresolved', 'runs')
    return {**{name: value[name] for name in leading if name in value},
            **{name: item for name, item in value.items() if name not in leading}}


def collection(result: dict, name: str, values, *, pointer: str, selected=None,
               project=copy.deepcopy) -> None:
    """Bound a display list and name the exact complete list in its report.

    Selection affects presentation only. The complete count includes unrelated
    history, so total minus the displayed item count always equals omitted.
    """
    rows = values if selected is None else selected
    displayed = [project(row) for row in rows[:DETAIL_LIMIT]]
    result[name] = displayed
    result[name + '_summary'] = {'total': len(values), 'omitted': len(values) - len(displayed),
                                'full_report': 'full_report#' + pointer}
    if selected is not None:
        result[name + '_summary']['matching'] = len(rows)


def action_view(value: dict | None, *, pointer: str) -> dict | None:
    """Retain the actual command while bounding its explicit alternatives."""
    if value is None:
        return None
    result = fields(value, (name for name in value if name != 'alternatives'))
    if 'alternatives' in value:
        indexed = list(enumerate(value['alternatives']))
        collection(result, 'alternatives', indexed, pointer=pointer + '/alternatives',
            project=lambda pair: action_view(pair[1], pointer=pointer + '/alternatives/' + str(pair[0])))
        if len(indexed) <= DETAIL_LIMIT and 'alternatives_summary' not in value:
            result.pop('alternatives_summary')
        elif 'alternatives_summary' in value:
            result['alternatives_summary'] = copy.deepcopy(value['alternatives_summary'])
    return result


def actions_once(value: dict) -> dict:
    """Keep each identical executable action once, with the next action first.

    Equality includes the decision's context, reason and alternatives, not just
    argv. Two owners may legitimately request the same command for different
    judgments. Existing references survive repeated projection unchanged.
    """
    owners = {}

    def visit(item, pointer):
        if isinstance(item, dict):
            argv = item.get('argv')
            if isinstance(argv, list) and argv and all(isinstance(word, str) for word in argv):
                identity = c.content_id(item)
                if identity in owners:
                    return {'action_ref': owners[identity]}
                owners[identity] = '#' + pointer
            for name, child in list(item.items()):
                item[name] = visit(child, pointer + '/' + name.replace('~', '~0').replace('/', '~1'))
        elif isinstance(item, list):
            for number, child in enumerate(item):
                item[number] = visit(child, pointer + '/' + str(number))
        return item

    return visit(_summary_order(value), '')


def _reading_change(value: Mapping) -> Mapping | None:
    if value.get('code') == 'READING_SOURCES_CHANGED':
        return value
    changed = value.get('source_changes')
    return changed if isinstance(changed, Mapping) and changed.get('code') == 'READING_SOURCES_CHANGED' else None


def brief(value: Any, *, depth: int = 0) -> Any:
    """Bound diagnostic detail while preserving its explicit omitted count.

    Diagnostic identity, location, message and repair are kept outside this
    helper. Only potentially large values, such as expected source inventories,
    use it. The complete original is retained by the report publisher.
    """
    if isinstance(value, Mapping):
        if depth >= 5:
            return {'field_count': len(value), 'details': 'full_report'}
        keys = list(value)
        result = {key: brief(value[key], depth=depth + 1) for key in keys[:VALUE_LIMIT]}
        if len(keys) > VALUE_LIMIT:
            result['omitted_fields'] = len(keys) - VALUE_LIMIT
        return result
    if isinstance(value, (list, tuple)):
        values = [brief(item, depth=depth + 1) for item in value[:VALUE_LIMIT]]
        if len(value) > VALUE_LIMIT:
            return {'items': values, 'total': len(value), 'omitted': len(value) - VALUE_LIMIT,
                    'full_report': 'full_report'}
        return values
    if isinstance(value, str) and len(value) > 1600:
        return {'excerpt': value[:1600], 'characters': len(value), 'details': 'full_report'}
    return copy.deepcopy(value)


def diagnostic(value: dict) -> dict:
    """Keep a diagnostic's cause, source owner and executable repair in reach."""
    changed = _reading_change(value)
    implementation = value.get('code') == 'IMPLEMENTATION_CHANGED' and isinstance(value.get('changed_files'), list)
    result = fields(value, ('code', 'severity', 'phase', 'message', 'file', 'pointer',
        'run', 'source', 'operation', 'grant', 'field', 'path', 'required_action',
        'cause', 'draft_operation', 'change_kind', 'evidence_owner', 'repair_owner',
        'repair_action', 'inspect_action', 'next_action', 'guidance', 'blocked_checks'))
    if 'next_actions' in value and changed is None:
        result['next_actions'] = [action_view(item, pointer='/next_actions/' + str(index))
                                  for index, item in enumerate(value['next_actions'])]
    for name, item in value.items():
        if name not in result and name != 'authorization_requirements' and not (
                changed is not None and name in {'source_changes', 'changes', 'actions', 'next_actions'}) and not (
                implementation and name in {'expected', 'actual', 'changed_files'}):
            result[name] = brief(item)
    if implementation:
        changes = value['changed_files']
        visible = changes[:DETAIL_LIMIT]
        result['changed_files'] = [row['path'] for row in visible]
        for name, key in (('unavailable_files', 'actual'), ('added_files', 'expected')):
            paths = [row['path'] for row in visible if row.get(key) is None]
            if paths:
                result[name] = paths
        result['changed_files_summary'] = {'total': len(changes),
            'omitted': max(0, len(changes) - DETAIL_LIMIT), 'full_report': 'full_report'}
    if changed is not None:
        # The exception's message repeats the entire path inventory. Its
        # structured change rows own those names, and full_report owns hashes.
        result['message'] = 'The current route sources differ from the saved reading.'
        changes = changed.get('changes', [])
        result['changed_sources'] = [fields(row, ('kind', 'path', 'resource', 'id', 'change'))
                                     for row in changes[:DETAIL_LIMIT]]
        result['changed_sources_summary'] = {'total': len(changes),
            'omitted': max(0, len(changes) - DETAIL_LIMIT), 'full_report': 'full_report'}
        continuation = value.get('next_action') or next(iter(value.get('next_actions') or []), None)
        if continuation is None:
            continuation = next((item for item in changed.get('actions', {}).values() if item), None)
        if continuation is not None:
            result['next_action'] = action_view(continuation, pointer='')
    if 'authorization_requirements' in value:
        result['authorization_requirements'] = authorization_requirements(value['authorization_requirements'])
    return result


def diagnostics(values) -> list[dict]:
    seen = set()
    result = []
    for value in values or []:
        key = _diagnostic_key(value)
        if key not in seen:
            seen.add(key)
            result.append(diagnostic(value))
    return result


def _diagnostic_key(value: dict) -> str:
    changed = _reading_change(value)
    if changed is None:
        return c.content_id(value)
    # Different historical digests can require the same current source read.
    # Keep every changed identity in this comparison, including omitted rows.
    current = diagnostic(value)
    current['changed_sources'] = [fields(row, ('kind', 'path', 'resource', 'id', 'change'))
                                  for row in changed.get('changes', [])]
    return c.content_id(current)


class DiagnosticIndex:
    """One display owner for unresolved choices repeated by authoring views."""

    def __init__(self):
        self.rows: list[dict] = []
        self._identities: dict[str, str] = {}

    def add(self, values, *, pointer: str) -> list[str]:
        identifiers = []
        for number, value in enumerate(values or []):
            key = _diagnostic_key(value)
            identifier = self._identities.get(key)
            if identifier is None:
                identifier = 'diagnostic-' + key[:16]
                self._identities[key] = identifier
                item = {'id': identifier, **diagnostic(value),
                        'full_report': 'full_report#' + pointer + '/' + str(number)}
                if 'changed_sources_summary' in item:
                    suffix = '/source_changes/changes' if 'source_changes' in value else '/changes'
                    item['changed_sources_summary']['full_report'] = item['full_report'] + suffix
                if 'changed_files_summary' in item:
                    item['changed_files_summary']['full_report'] = item['full_report'] + '/changed_files'
                self.rows.append(item)
            if identifier not in identifiers:
                identifiers.append(identifier)
        return identifiers


def _candidate_reasons(candidate: dict, requirement: dict) -> set[str]:
    """Count structural grant mismatches, without interpreting diagnostic prose."""
    reasons = set()
    if requirement.get('operation') not in candidate.get('operations', []):
        reasons.add('operation')
    if candidate.get('missing'):
        reasons.add('targets')
    for problem in candidate.get('diagnostics', []):
        code = problem.get('code')
        expected, actual = problem.get('expected'), problem.get('actual')
        if code == 'GRANT_SCOPE_EXCEEDED' and isinstance(expected, Mapping) and isinstance(actual, Mapping):
            if expected.get('actor') is not None and expected['actor'] != actual.get('actor'):
                reasons.add('actor')
            if expected.get('operation') is not None and expected['operation'] not in actual.get('operations', []):
                reasons.add('operation')
        elif code == 'GRANT_REVOKED':
            reasons.add('revoked-or-expired')
        elif code == 'GRANT_NOT_EFFECTIVE':
            reasons.add('not-effective')
        elif problem.get('cause') == 'protected-criteria-changed':
            reasons.add('protected-criteria')
        elif code != 'GRANT_SCOPE_EXCEEDED':
            reasons.add('other')
    return reasons or {'other'}


def authorization_requirements(value: dict | None) -> dict | None:
    """Bound grant alternatives while retaining every current operation's need.

    The selected grant and its diagnostics remain explicit, even if it is not
    among the displayed alternatives. Multiple partial grants never imply one
    eligible grant. An empty missing-target list alone does not mean authority
    is available; `eligible` and the operation's diagnostics retain that result.
    """
    if value is None:
        return None
    result = fields(value, ('state', 'limit'))
    if value.get('protected_criteria') is not None:
        constraint = value['protected_criteria']
        result['protected_criteria'] = fields(constraint, ('run', 'production_id', 'comparison_run', 'comparison',
            'meaning', 'authoring', 'repair_owner', 'repair_action'))
        result['protected_criteria']['changes'] = brief(constraint.get('changes', []))
    result['requirements'] = []
    for requirement in value.get('requirements', []):
        candidates = requirement.get('candidates', [])
        eligible = [candidate for candidate in candidates if candidate.get('eligible')]
        rejected = [candidate for candidate in candidates if not candidate.get('eligible')]
        selected = next((candidate for candidate in candidates
                         if candidate.get('grant') == requirement.get('selected_grant')), None)
        counts = Counter(reason for candidate in rejected for reason in _candidate_reasons(candidate, requirement))
        current = fields(requirement, ('operation', 'targets', 'selected_grant', 'selected_actor', 'eligible'))
        current['eligible_grants'] = [fields(candidate, ('grant', 'actor'))
                                      for candidate in eligible[:ELIGIBLE_GRANT_LIMIT]]
        current['eligible_grant_count'] = len(eligible)
        current['eligible_grants_omitted'] = max(0, len(eligible) - ELIGIBLE_GRANT_LIMIT)
        current['eligible_grants_summary'] = {'total': len(eligible),
            'omitted': max(0, len(eligible) - ELIGIBLE_GRANT_LIMIT), 'full_report': 'full_report'}
        current['selection_required'] = requirement.get('selected_grant') is None and bool(eligible)
        current['ineligible_grant_count'] = len(rejected)
        current['ineligible_reasons'] = dict(sorted(counts.items()))
        if selected is not None:
            current['missing_targets'] = copy.deepcopy(selected.get('missing', []))
            current['missing_targets_basis'] = 'selected-grant'
        elif eligible:
            current['missing_targets'] = []
            current['missing_targets_basis'] = 'eligible-alternatives'
        else:
            # Only grants with current actor/operation eligibility contribute
            # target coverage. This describes a common deficiency; it does not
            # merge their separate permissions into an eligible selection.
            applicable = [candidate for candidate in rejected
                          if _candidate_reasons(candidate, requirement) <= {'targets', 'protected-criteria'}]
            granted = {target for candidate in applicable for target in candidate.get('granted', [])}
            current['missing_targets'] = sorted(set(requirement.get('targets', [])) - granted)
            current['missing_targets_basis'] = 'not-covered-by-current-operation-grants'
        current['diagnostics'] = diagnostics(requirement.get('diagnostics'))
        result['requirements'].append(current)
    result['diagnostics'] = diagnostics(value.get('diagnostics'))
    result['display_limit'] = ELIGIBLE_GRANT_LIMIT
    result['coverage_note'] = ('Each operation requires one eligible grant covering every target. '
        'A missing-target list does not combine partial grants or approve a request; '
        'read the complete report for every alternative and its individual diagnostics.')
    return result


def authority(value: dict | None) -> dict | None:
    if value is None:
        return None
    return fields(value, ('event_sha256', 'source_path', 'source_edited', 'update_action', 'read_action'))


def _next_action(report: dict) -> dict | None:
    """Use the producer's actual continuation before offering any navigation."""
    if report.get('next_action') is not None:
        return copy.deepcopy(report['next_action'])
    for problem in report.get('diagnostics', []):
        if problem.get('repair_action'):
            return copy.deepcopy(problem['repair_action'])
    if report.get('next_actions') and not report.get('selection_required'):
        return copy.deepcopy(report['next_actions'][0])
    for problem in report.get('diagnostics', []):
        for name in ('repair_action', 'next_action'):
            if problem.get(name):
                return copy.deepcopy(problem[name])
    return None


def execution_records(value: dict) -> dict:
    result = fields(value, ('complete', 'submissions', 'captured_outputs', 'reported_cost', 'usage_complete'))
    result['diagnostics'] = diagnostics(value.get('diagnostics'))
    result['execution_count'] = len(value.get('executions', []))
    return result


def _readiness(value: dict) -> dict:
    result = fields(value, ('state', 'executable'))
    result['diagnostics'] = diagnostics(value.get('diagnostics'))
    if 'authorization_requirements' in value:
        result['authorization_requirements'] = authorization_requirements(value['authorization_requirements'])
    return result


def _plan(value: dict | None) -> dict | None:
    if value is None:
        return None
    result = fields(value, ('run', 'execution', 'input_sha256', 'request_sha256', 'service',
                            'model', 'quantities', 'external_effects'))
    result['operations'] = [fields(row, ('operation', 'targets')) for row in value.get('operations', [])]
    if value.get('readiness') is not None:
        result['readiness'] = _readiness(value['readiness'])
    return result


def _unanswered(choices: dict) -> list[dict]:
    """Locate required answers, keeping alternative scope choices together."""
    result = []
    def add(pointer, reason, **details):
        result.append({'pointer': pointer, 'state': 'unanswered', 'required_action': reason, **details})
    def stops(values, pointer):
        for index, row in enumerate(values):
            if row.get('clear') is not True or not row.get('evidence'):
                add(pointer + '/' + str(index), 'Assess this stop condition from actual evidence.',
                    stop=row.get('id'))
    stops(choices.get('shared_stop_assessments', []), '/shared_stop_assessments')
    for index, decision in enumerate(choices.get('decisions', [])):
        pointer = '/decisions/' + str(index)
        if not decision.get('grant'):
            add(pointer + '/grant', 'Select one eligible grant for this operation.')
        if not decision.get('reason'):
            add(pointer + '/reason', 'Record the actual reason for this operation.')
        for name in ('stop_assessments', 'additional_stop_assessments'):
            stops(decision.get(name, []), pointer + '/' + name)
        request = decision.get('request_decision')
        if request is None:
            continue
        request_pointer = pointer + '/request_decision'
        if 'case' in request and request['case'] is None and request.get('principal_approval') is None:
            add(request_pointer, 'Select the applicable delegated scope case or actual principal approval evidence.',
                alternatives=[request_pointer + '/case', request_pointer + '/principal_approval'])
        for number, assessment in enumerate((request.get('rendition_review') or {}).get('assessments', [])):
            if not assessment.get('conclusion') or not assessment.get('reason'):
                add(request_pointer + '/rendition_review/assessments/' + str(number),
                    'Assess the exact rendition from its actual request and source evidence.')
    return result


def _prepared_unchanged(value: dict) -> bool:
    """Recognize saved input with no current authoring work to resume."""
    changed = value.get('changed_since_save', value.get('changed_since_build'))
    return (bool(value.get('prepared_run')) and changed is False
            and value.get('source_available') is not False
            and not value.get('working_copy') and not value.get('unresolved')
            and not value.get('diagnostics')
            and not (value.get('authoring_stage') or {}).get('unresolved'))


def _input_row(value: dict, *, index: DiagnosticIndex, pointer: str) -> dict:
    result = fields(value, ('state', 'kind', 'directory', 'choices', 'context', 'source_task',
        'source_run', 'prepared_run', 'current', 'task', 'source_available', 'changed_since_save',
        'editable_locations', 'selection_required', 'assessment_required',
        'source_requirements'))
    if value.get('route_scope') is not None:
        scope = value['route_scope']
        result['route_scope'] = fields(scope, ('route', 'operation', 'execution', 'scope', 'source_kind',
                                             'features', 'model', 'service', 'authoring_scope'))
        result['route_scope']['document_count'] = len(scope.get('documents', []))
    stage = value.get('authoring_stage')
    if stage is not None:
        result['authoring_stage'] = fields(stage, ('stage', 'purpose', 'structural_ready',
                                                   'final_inputs_ready', 'meaning'))
        result['authoring_stage']['pending_summary'] = {'total': len(stage.get('pending', [])),
            'full_report': 'full_report#' + pointer + '/authoring_stage/pending'}
        result['diagnostic_ids'] = index.add(stage.get('unresolved'),
            pointer=pointer + '/authoring_stage/unresolved')
        result['authoring_stage']['diagnostic_ids'] = list(result['diagnostic_ids'])
    else:
        result['diagnostic_ids'] = index.add(value.get('unresolved'), pointer=pointer + '/unresolved')
    result['diagnostic_ids'].extend(identifier for identifier in index.add(
        value.get('diagnostics'), pointer=pointer + '/diagnostics') if identifier not in result['diagnostic_ids'])
    collection(result, 'next_actions', list(enumerate(value.get('next_actions', []))),
        pointer=pointer + '/next_actions',
        project=lambda pair: action_view(pair[1], pointer=pointer + '/next_actions/' + str(pair[0])))
    if not result['next_actions_summary']['omitted']:
        result.pop('next_actions_summary')
    if value.get('fresh_context_action') is not None and not _prepared_unchanged(value):
        result['fresh_context_action'] = action_view(value['fresh_context_action'],
            pointer=pointer + '/fresh_context_action')
    if value.get('stage_actions') is not None:
        result['stage_actions_summary'] = {'total': len(value['stage_actions']),
            'full_report': 'full_report#' + pointer + '/stage_actions'}
    if value.get('future_authoring') is not None:
        future = value['future_authoring']
        result['future_authoring'] = {'reason': future['reason'],
            'unresolved_count': len(future.get('unresolved', [])),
            'full_report': 'full_report#' + pointer + '/future_authoring'}
    if value.get('working_copy'):
        result['working_copy'] = _input_row(value['working_copy'], index=index, pointer=pointer + '/working_copy')
    return result


def authoring_state(root: Path, value: dict, *, choices: str | None = None,
                    run: str | None = None, pointer: str = '') -> dict:
    result = fields(value, ('state', 'task_id', 'pending', 'selection_required', 'external_effect'))
    index = DiagnosticIndex()
    index.add(value.get('diagnostics'), pointer=pointer + '/diagnostics')
    def stage_view(owner, at):
        stage = owner.get('authoring_stage')
        if stage is None:
            return None
        return {**fields(stage, ('stage', 'purpose', 'structural_ready', 'final_inputs_ready', 'meaning')),
            'diagnostic_ids': index.add(stage.get('unresolved'), pointer=at + '/authoring_stage/unresolved'),
            'pending_summary': {'total': len(stage.get('pending', [])),
                'full_report': 'full_report#' + at + '/authoring_stage/pending'}}

    inputs = value.get('inputs', [])
    current_inputs = [row for row in inputs if row.get('current')]
    prepared_unchanged = (not value.get('pending') and not value.get('selection_required')
                          and len(current_inputs) == 1 and _prepared_unchanged(current_inputs[0]))
    stage = stage_view(value, pointer)
    if stage is not None:
        result['authoring_stage'] = stage
    if value.get('fresh_context_action') is not None and not prepared_unchanged:
        result['fresh_context_action'] = action_view(value['fresh_context_action'],
            pointer=pointer + '/fresh_context_action')
    if value.get('stage_actions') is not None:
        if prepared_unchanged:
            result['stage_actions_summary'] = {'total': len(value['stage_actions']),
                'omitted': len(value['stage_actions']), 'full_report': 'full_report#' + pointer + '/stage_actions'}
        else:
            result['stage_actions'] = [action_view(row, pointer=pointer + '/stage_actions/' + str(number))
                                       for number, row in enumerate(value['stage_actions'])]
    collection(result, 'next_actions', list(enumerate(value.get('next_actions', []))),
        pointer=pointer + '/next_actions',
        project=lambda pair: action_view(pair[1], pointer=pointer + '/next_actions/' + str(pair[0])))
    # Acquire every current finding before applying the list's display limit.
    # A branch outside the shown prefix must not lose its unresolved choices.
    projected = [_input_row(row, index=index, pointer=pointer + '/inputs/' + str(number))
                 for number, row in enumerate(inputs)]
    if prepared_unchanged:
        for source, row in zip(inputs, projected):
            if source.get('current'):
                if source.get('authoring_stage') == value.get('authoring_stage'):
                    row.pop('authoring_stage', None)
                if source.get('stage_actions') == value.get('stage_actions'):
                    row.pop('stage_actions_summary', None)
    shown = [row for row in projected if row.get('current') or row.get('working_copy')
             or row.get('changed_since_save') or row.get('diagnostic_ids') or not row.get('prepared_run')]
    shown.sort(key=lambda row: not row.get('current', False))
    collection(result, 'inputs', inputs, selected=shown, pointer=pointer + '/inputs')
    result['input_count'] = len(inputs)
    result['historical_inputs_omitted'] = len(inputs) - len(result['inputs'])
    options = []
    for number, row in enumerate(value.get('input_options', [])):
        option_pointer = pointer + '/input_options/' + str(number)
        option = {**fields(row, ('choices', 'directory', 'source_run')),
            'action': action_view(row.get('action'), pointer=option_pointer + '/action')}
        stage = stage_view(row, option_pointer)
        if stage is not None:
            option.update(authoring_stage=stage, diagnostic_ids=list(stage['diagnostic_ids']))
        else:
            option['diagnostic_ids'] = index.add(row.get('unresolved'), pointer=option_pointer + '/unresolved')
        if row.get('fresh_context_action') is not None and not prepared_unchanged:
            option['fresh_context_action'] = action_view(row['fresh_context_action'],
                pointer=option_pointer + '/fresh_context_action')
        options.append(option)
    collection(result, 'input_options', options, pointer=pointer + '/input_options')
    readings = value.get('readings', [])
    current_readings = [(number, row) for number, row in enumerate(readings) if row.get('current')]
    def reading(pair):
        number, row = pair
        current = fields(row, ('state', 'route', 'operation', 'execution', 'current', 'snapshot',
            'reading', 'remaining', 'applicability', 'progress', 'source_freshness',
            'scope', 'source_kind', 'delivered_bytes', 'remaining_bytes', 'required_bytes',
            'reused_bytes', 'same_context_required', 'authoring_scope', 'choices'))
        collection(current, 'next_actions', list(enumerate(row.get('next_actions', []))),
            selected=[] if row.get('applicability') == 'future-authoring' else None,
            pointer=pointer + '/readings/' + str(number) + '/next_actions',
            project=lambda item: action_view(item[1], pointer=pointer + '/readings/' + str(number) +
                                            '/next_actions/' + str(item[0])))
        if row.get('fresh_context_action') is not None and not prepared_unchanged:
            current['fresh_context_action'] = action_view(row['fresh_context_action'],
                pointer=pointer + '/readings/' + str(number) + '/fresh_context_action')
        return current
    collection(result, 'readings', readings, selected=current_readings,
               pointer=pointer + '/readings', project=reading)
    result['reading_count'] = len(readings)
    drafts = value.get('decision_drafts', [])
    available = [row for row in drafts if row.get('available') and
                 (run is None or row.get('run') == run or row.get('relation') in {'source-run', 'reopened-run'})]
    available.sort(key=lambda row: (run is not None and row.get('run') == run, row.get('created_at', '')),
                   reverse=True)
    collection(result, 'decision_drafts', drafts, selected=available, pointer=pointer + '/decision_drafts',
        project=lambda row: {**fields(row, ('kind', 'run', 'candidate', 'path', 'available', 'ownership', 'relation')),
                             **({'relation': 'selected-run'} if run is not None and row.get('run') == run else {})})
    if run is not None:
        result['decision_drafts_summary']['unrelated'] = sum(row.get('run') != run and
            row.get('relation') not in {'source-run', 'reopened-run'} for row in drafts)
    selected = (value.get('context') or {}).get('input')
    work = (value.get('context') or {}).get('work') or {}
    work_view = fields(work, ('task_id', 'goal', 'next', 'blocked_on', 'production_run'))
    questions = work.get('questions', [])
    work_view['questions'] = [copy.deepcopy(row) for row in questions if row.get('state') == 'open']
    work_view['questions_summary'] = {'total': len(questions),
        'omitted': len(questions) - len(work_view['questions']),
        'full_report': 'full_report#' + pointer + '/context/work/questions'}
    result['context'] = {'work_file': (value.get('context') or {}).get('work_file'),
        'work': work_view,
        'input': (fields(selected, ('state', 'directory', 'source_task', 'source_run', 'choices_file',
            'published_task', 'prepared_run', 'changed_since_build', 'editable_locations',
            'assessment_required', 'instruction', 'source_requirements')) if selected is not None else None),
        'read_action': action(root, 'inspect-inputs', ['--choices', choices] if choices else [],
            'Read the complete authoring context and editable source for the selected branch.')}
    if selected is not None:
        stage = stage_view(selected, pointer + '/context/input')
        if stage is not None:
            result['context']['input'].update(authoring_stage=stage,
                diagnostic_ids=list(stage['diagnostic_ids']))
        else:
            result['context']['input']['diagnostic_ids'] = index.add(selected.get('unresolved'),
                pointer=pointer + '/context/input/unresolved')
        if selected.get('fresh_context_action') is not None and not _prepared_unchanged(selected):
            result['context']['input']['fresh_context_action'] = action_view(selected['fresh_context_action'],
                pointer=pointer + '/context/input/fresh_context_action')
        result['context']['input']['input_ref'] = next(('#' + pointer + '/inputs/' + str(number)
            for number, row in enumerate(result['inputs']) if row.get('current')), None)
        selected_path = selected.get('choices_file')
        matching = next((row for row in result['inputs'] if row.get('current') and row.get('choices')
            and selected_path is not None
            and Path(selected_path) in {Path(row['choices']), root / row['choices']}), None)
        if matching is not None:
            current_input = result['context']['input']
            for name in ('state', 'source_task', 'source_run', 'prepared_run', 'editable_locations',
                         'assessment_required', 'source_requirements'):
                if name in matching and current_input.get(name) == matching[name]:
                    current_input.pop(name, None)
            for name, field in (('choices_file', 'choices'), ('directory', 'directory')):
                if name in current_input and field in matching and Path(current_input[name]) in {
                        Path(matching[field]), root / matching[field]}:
                    current_input.pop(name)
            if (current_input.get('changed_since_build') is not None
                    and current_input['changed_since_build'] == matching.get('changed_since_save')):
                current_input.pop('changed_since_build')
            owner = next((row for row in current_inputs if row.get('choices') == matching['choices']), None)
            if owner is not None and selected.get('authoring_stage') == owner.get('authoring_stage'):
                current_input.pop('authoring_stage', None)
    if value.get('last_check'):
        check = value['last_check']
        result['last_check'] = fields(check, ('task', 'operation_id', 'created_at', 'ok', 'path', 'state'))
        result['last_check']['diagnostic_ids'] = index.add(check.get('diagnostics'),
            pointer=pointer + '/last_check/diagnostics')
    if value.get('saved'):
        result['saved'] = fields(value['saved'], ('run', 'state', 'working_changes', 'next_action', 'artifact', 'delivery'))
    result['diagnostics'] = index.rows
    return result


def _source_run(root: Path, value: Any) -> Any:
    """Locate retained source work without repeating its task or reading index."""
    if not isinstance(value, Mapping):
        return copy.deepcopy(value)
    result = fields(value, (name for name in value if name not in {'task', 'route_reading', 'freshness', 'input_reuse'}))
    if value.get('freshness') is not None:
        result['freshness'] = {name: diagnostics(rows) for name, rows in value['freshness'].items()}
    if isinstance(value.get('input_reuse'), Mapping):
        reuse = value['input_reuse']
        result['input_reuse'] = fields(reuse, (name for name in reuse if name != 'captured_outputs'))
        if 'captured_outputs' in reuse:
            outputs = reuse['captured_outputs']
            result['input_reuse'].update(captured_outputs=copy.deepcopy(outputs[:DETAIL_LIMIT]),
                captured_output_count=len(outputs), captured_outputs_omitted=max(0, len(outputs) - DETAIL_LIMIT))
            result['input_reuse']['captured_outputs_summary'] = {'total': len(outputs),
                'omitted': max(0, len(outputs) - DETAIL_LIMIT), 'full_report': 'full_report'}
    if value.get('run') and not result.get('read_action'):
        result['read_action'] = action(root, 'inspect-inputs', ['--from-run', value['run'], '--view', 'full'],
            'Read this saved source run\'s complete task, source selections and remaining assessments.')
    return result


def _draft_inputs(root: Path, report: dict) -> dict:
    result = fields(report, ('state', 'choices_file', 'context_file', 'authoring_work',
        'external_effect', 'next_actions', 'required_source_roles', 'source_requirements', 'authoring_scope'))
    if 'derived_from' in report:
        result['derived_from'] = fields(report['derived_from'],
                                      (name for name in report['derived_from'] if name != 'source_run'))
        if 'source_run' in report['derived_from']:
            result['derived_from']['source_run'] = _source_run(root, report['derived_from']['source_run'])
    stage = report.get('authoring_stage')
    result['unresolved'] = diagnostics(stage['unresolved'] if stage else report.get('unresolved'))
    if stage:
        result['authoring_stage'] = fields(stage, ('stage', 'purpose', 'structural_ready', 'final_inputs_ready', 'meaning'))
        result['authoring_stage']['pending_count'] = len(stage['pending'])
        result['authoring_stage']['pending_details'] = 'full_report#/authoring_stage/pending'
    guide = report.get('authoring_guide')
    if guide:
        result['authoring_guide'] = fields(guide, ('document_path', 'schema', 'example', 'explain_action',
                                                  'meaning', 'source_acquisition', 'structured_edit',
                                                  'source_requirements', 'input_contracts'))
        result['authoring_guide']['documents'] = {key: fields(value, ('source', 'schema', 'document_path', 'explain_action'))
                                                 for key, value in guide.get('documents', {}).items()}
    authored = (report.get('choices') or {}).get('authoring', {})
    result['editable_locations'] = []
    def locate(value, pointer):
        if isinstance(value, Mapping):
            if isinstance(value.get('file'), str):
                result['editable_locations'].append({'pointer': pointer, **fields(value, ('file', 'field'))})
            for key, item in value.items():
                if key != 'task':
                    locate(item, pointer + '/' + key.replace('~', '~0').replace('/', '~1'))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                locate(item, pointer + '/' + str(index))
    locate(authored, '/authoring')
    return result


def summarize(root: Path, report: dict, *, command: str, run: str | None = None,
              choices: str | None = None, runtime_arguments: dict | None = None) -> dict:
    """Project one acquired command result without reading or writing any input."""
    if 'runs' in report:
        from production_status_view import summary
        result = summary(root, report, run=run)
    elif command in {'inspect-inputs', 'stage-inputs'} and report.get('state') == 'authoring-state':
        result = authoring_state(root, report, choices=choices)
    elif command == 'draft-inputs' and report.get('state') == 'draft':
        result = _draft_inputs(root, report)
    elif command == 'acquire-source' and report.get('state') == 'source-acquired':
        result = fields(report, ('ok', 'state', 'changed', 'source', 'source_row', 'acquired',
            'choices_file', 'basis_file', 'projected_source', 'applications', 'subjects',
            'next_actions', 'external_effect'))
        result['unresolved'] = diagnostics(report.get('unresolved'))
    elif command == 'workspace' and 'phase' in report:
        from production_workspace import summary
        result = summary(root, report)
    elif command == 'sheet-batch' and isinstance(report.get('panels'), Mapping):
        result = fields(report, ('ok', 'outcome', 'exit_code', 'batch', 'batch_id', 'home', 'adopted'))
        result['panels'] = {}
        for name, panel in report['panels'].items():
            pointer = '/panels/' + name.replace('~', '~0').replace('/', '~1')
            shown = fields(panel, ('status', 'run', 'source_task', 'compiled_task', 'inputs', 'decision_file'))
            shown['full_report'] = 'full_report#' + pointer
            if panel.get('selected_references') is not None:
                shown['selected_references'] = [
                    {**fields(reference, ('slot', 'role')),
                     'artifact_id': reference['artifact']['artifact_id'],
                     'image_sha256': reference['artifact']['image']['sha256']}
                    for reference in panel['selected_references']]
            if panel.get('diagnostic'):
                shown['diagnostic'] = diagnostic(panel['diagnostic'])
                shown['diagnostic']['full_report'] = 'full_report#' + pointer + '/diagnostic'
                if isinstance(panel['diagnostic'].get('report'), Mapping):
                    compilation = panel['diagnostic']['report']
                    shown['diagnostic']['report'] = {
                        **fields(compilation, ('ok', 'publishable')),
                        'diagnostics': diagnostics(compilation.get('diagnostics', [])),
                        'full_report': 'full_report#' + pointer + '/diagnostic/report'}
            shown['omitted_fields'] = [key for key in panel if key not in shown]
            result['panels'][name] = shown
        result['panel_count'] = len(report['panels'])
        result['omitted_fields'] = [key for key in report if key not in result]
    elif command == 'draft-review' and 'choices' in report:
        guide = report.get('review_guide', {})
        result = fields(report, ('draft_file', 'next_action'))
        result['binding'] = fields(report['choices'], ('input_sha256', 'candidate'))
        result['review_guide'] = fields(guide, (key for key in guide if key != 'next_action'))
        result['unresolved'] = [{'file': report.get('draft_file'), 'pointer': '/' + name,
            'state': 'unanswered', 'required_action': 'Record your actual ' + name + ' in the saved review.'}
            for name in ('reviewer', 'observations', 'checks', 'conclusion') if not report['choices'].get(name)]
    elif command in {'draft-principal-approval', 'draft-authority-update'} and 'choices' in report:
        result = fields(report, ('state', 'schema', 'unanswered', 'required_action', 'limit',
            'draft_file', 'expected_event', 'required_validation_mode', 'approval_selection', 'phase',
            'selection_requirements'))
        authored = report['choices']
        result['binding'] = fields(authored.get('binding', authored),
            ('task_id', 'issuer', 'run', 'input_sha256', 'request_sha256', 'expected_event', 'selection', 'adoption'))
        if command == 'draft-authority-update':
            result['grants'] = [fields(row, ('id', 'operation', 'targets', 'actor', 'mode'))
                                for row in authored.get('grants', [])]
            result['authorization_requirements'] = authorization_requirements(report.get('authorization_requirements'))
            result['current_stop_conditions'] = fields(report, ('current_stop_conditions',)).get('current_stop_conditions', [])
            if report.get('draft_file') and report.get('expected_event'):
                result['next_action'] = {**action(root, 'authority-import',
                    ['--file', report['draft_file'], '--expected-event', report['expected_event']],
                    'Complete the actual authority choices in the saved draft before importing it with this predecessor.'),
                    'requires_author_input': True}
        else:
            result['actor'] = authored.get('actor')
            result['instruction'] = fields(authored.get('instruction', {}), ('path', 'sha256', 'encoding'))
            if result['binding'].get('run'):
                result['next_action'] = {**action(root, 'status', ['--run', result['binding']['run']],
                    'Answer the saved approval draft from the actual instruction, then continue this run\'s execution decisions.'),
                    'requires_author_input': True}
    elif command == 'authority-import' and report.get('event') == 'authority-updated':
        document = report['data']['authority']
        result = fields(report, ('sequence', 'sha256', 'created_at', 'event'))
        result.update(task_id=document['task_id'], issuer=document['issuer'],
                      previous_event=report['data'].get('previous_state'), grant_count=len(document['grants']))
        if 'changed_grants' in report:
            result['changed_grants'] = {key: {'ids': identifiers[:DETAIL_LIMIT], 'total': len(identifiers),
                                            'omitted': max(0, len(identifiers) - DETAIL_LIMIT),
                                            'full_report': 'full_report#/changed_grants/' + key}
                                       for key, identifiers in report['changed_grants'].items()}
        else:
            result['grant_ids'] = [row['id'] for row in document['grants'][:DETAIL_LIMIT]]
            result['grant_ids_omitted'] = max(0, len(document['grants']) - DETAIL_LIMIT)
            result['grant_ids_summary'] = {'total': len(document['grants']),
                'omitted': result['grant_ids_omitted'], 'full_report': 'full_report#/data/authority/grants'}
        result['next_action'] = action_view(report.get('next_action'), pointer='/next_action') or action(
            root, 'status', ['--run', run] if run else [],
            'Inspect current requirements and continue the saved work under the imported authority.')
    elif command == 'draft-execution' and 'choices' in report:
        result = fields(report, ('decisions_file', 'next_action'))
        result.update(run=report['choices'].get('run'),
                      unresolved=_unanswered(report['choices']),
                      authority=authority(report.get('authority')),
                      authorization_requirements=authorization_requirements(report.get('authorization_requirements')))
    elif command in {'draft-acceptance', 'draft-adoption'} and 'choices' in report:
        result = fields(report, ('state', 'draft_file', 'schema', 'reading_action', 'next_action', 'required_action'))
        authored = report['choices']
        result['binding'] = fields(authored, ('run', 'candidate', 'review', 'selection', 'character',
            'iteration', 'slot', 'scope', 'influence', 'grant', 'claim'))
        result['unresolved'] = []
        for name in ('grant', 'reason'):
            if not authored.get(name):
                result['unresolved'].append({'pointer': '/' + name, 'file': report.get('draft_file'), 'state': 'unanswered',
                    'required_action': 'Record the actual ' + name + ' for this operation in the saved draft.'})
        shared = authored.get('shared_stop_assessments')
        if isinstance(shared, Mapping):
            result['shared_stop_assessments'] = fields(shared, ('authorization', 'authority_event', 'confirmed'))
            result['shared_stop_assessments'].update(assessment_count=len(shared.get('assessments', [])),
                full_report='full_report#/choices/shared_stop_assessments')
            if shared.get('confirmed') is None:
                result['unresolved'].append({'pointer': '/shared_stop_assessments/confirmed', 'file': report.get('draft_file'),
                    'state': 'unanswered', 'required_action': 'Confirm whether the proposed assessments still apply '
                    'to this candidate, review, destination and actual instruction; the operation rechecks that basis.'})
        for name in ('stop_assessments', 'additional_stop_assessments'):
            for number, assessment in enumerate(authored.get(name, [])):
                if assessment.get('clear') is not True or not assessment.get('evidence'):
                    result['unresolved'].append({'pointer': '/' + name + '/' + str(number), 'file': report.get('draft_file'),
                        'stop': assessment.get('id'), 'state': 'unanswered',
                        'required_action': 'Assess this stop condition from actual evidence.'})
        if authored.get('owner_acceptance') is not None:
            result['owner_acceptance'] = brief(authored['owner_acceptance'])
    elif report.get('artifact_type') == 'external-execution-instruction':
        result = fields(report, ('artifact_type', 'run', 'state', 'external_effect', 'instruction'))
        result['host_request'] = fields(report['host_request'], ('claim', 'service', 'model', 'count', 'request_sha256'))
        result['request_location'] = 'full_report#/host_request'
    else:
        result = fields(report, ('ok', 'run', 'task', 'task_id', 'input_sha256', 'consumer', 'package',
            'publishable', 'formal_run_created', 'external_effect', 'state', 'saved', 'artifact',
            'next_action', 'next_actions', 'choices_file', 'context_file', 'staging', 'draft_file',
            'required_action', 'required_choices', 'source_requirements', 'source_run', 'route'))
        if 'unresolved' in report:
            result['unresolved'] = diagnostics(report['unresolved'])
        if 'execution_plan' in report:
            result['execution_plan'] = _plan(report['execution_plan'])
        if 'readiness' in report:
            result['readiness'] = _readiness(report['readiness'])
        if 'authorization_requirements' in report:
            result['authorization_requirements'] = authorization_requirements(report['authorization_requirements'])
        if 'checks' in report:
            result['checks'] = dict(Counter(row.get('state', 'unknown') for row in report['checks']))
    result.update(view='summary', command=command)
    if 'ok' in report:
        result['ok'] = report['ok']
    if report.get('diagnostics') is not None and 'diagnostics' not in result:
        result['diagnostics'] = diagnostics(report['diagnostics'])
    for name in ('warnings', 'runtime_warnings'):
        if name in report:
            result[name] = diagnostics(report[name])
    if 'next_action' not in result:
        result['next_action'] = action_view(_next_action(report), pointer='/next_action')
    if result['next_action'] is None and report.get('selection_required'):
        result['next_action'] = {**action(root, 'inspect-inputs', [],
            'Choose an explicitly named editable branch; no branch was selected by this summary.'),
            'requires_author_input': True}
        collection(result['next_action'], 'alternatives', report.get('next_actions', []), pointer='/next_actions')
        if not result['next_action']['alternatives_summary']['omitted']:
            result['next_action'].pop('alternatives_summary')
    identifier = run or report.get('run')
    if result['next_action'] is None and identifier and command in {'prepare', 'check'} and report.get('ok', True):
        result['next_action'] = action(root, 'status', ['--run', identifier],
            'Inspect this saved run and follow its next operation; preparation grants no execution authority.')
    if choices is not None:
        result.setdefault('choices_file', choices)
    if 'source_run' in result:
        result['source_run'] = _source_run(root, result['source_run'])
    if result['next_action'] is None and command == 'check' and report.get('ok'):
        selected = ['--choices', choices] if choices else ['--task', report['task']] if report.get('task') else None
        if selected is not None:
            for name, value in (runtime_arguments or {}).items():
                for item in value if isinstance(value, list) else [value]:
                    selected.extend(('--' + name, str(item)))
            result['next_action'] = action(root, 'prepare', selected,
                'Prepare this checked source when its authored choices are complete; execution remains separate.')
    return actions_once(result)


def present(root: Path, report: dict, *, command: str, run: str | None = None,
            choices: str | None = None, runtime_arguments: dict | None = None) -> dict:
    """Retain a complete report outside formal run history, then show its summary.

    Content-addressed snapshots are exclusive publications. Repeated identical
    reports reuse the same verified bytes. Failure to save a display must not
    turn a committed operation into a retry: include its full result inline and
    leave the caller's original outcome and exit-code calculation unchanged.
    """
    result = summarize(root, report, command=command, run=run, choices=choices,
                       runtime_arguments=runtime_arguments)
    try:
        if not command or any(character not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for character in command):
            raise ValueError('report command must be a lowercase command name')
        raw = c.encoded(report)
        relative = 'work/reports/' + command + '/' + c.digest(raw) + '.json'
        destination = c.local(root, relative, exists=False)
        try:
            c.atomic(destination, raw)
        except FileExistsError:
            if c.read(destination) != raw:
                raise ValueError('the saved report differs from its content-addressed name')
    except (OSError, ValueError, TypeError) as exc:
        result['full_report'] = None
        result['complete_report'] = copy.deepcopy(report)
        result['report_warning'] = {'message': 'The complete report could not be saved and is included in complete_report.',
            'file': 'work/reports/' + command, 'cause': str(exc),
            'required_action': 'Use complete_report for this operation. Repair the report directory before a later summary; '
                               'this display failure does not request another execution.'}
    else:
        result['full_report'] = relative
        result['full_report_sha256'] = c.digest(raw)
        result['full_report_action'] = {'command': 'read-report',
            'argv': [os.path.abspath(sys.executable), '-m', 'json.tool', str(destination)],
            'reason': 'Read this exact complete operation report; this action performs no production operation.'}
        if report.get('artifact_type') == 'external-execution-instruction':
            result['next_action'] = {**result['full_report_action'],
                'reason': 'Read the exact host_request and invoke it once as instructed; after interruption recover '
                          'that same host call without executing the run again.'}
    def locate(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key == 'complete_report':
                    continue
                if key == 'full_report' and isinstance(item, str) and (
                        item == 'full_report' or item.startswith('full_report#')):
                    value[key] = (result['full_report'] or 'complete_report') + item[len('full_report'):]
                else:
                    locate(item)
        elif isinstance(value, list):
            for item in value:
                locate(item)
    locate(result)
    return _summary_order(result)
