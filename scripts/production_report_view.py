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
               'next_action', 'full_report', 'full_report_sha256', 'full_report_action',
               'diagnostics', 'unresolved')
    return {**{name: value[name] for name in leading if name in value},
            **{name: item for name, item in value.items() if name not in leading}}


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
            return {'items': values, 'total': len(value), 'omitted': len(value) - VALUE_LIMIT}
        return values
    if isinstance(value, str) and len(value) > 1600:
        return {'excerpt': value[:1600], 'characters': len(value), 'details': 'full_report'}
    return copy.deepcopy(value)


def diagnostic(value: dict) -> dict:
    """Keep a diagnostic's cause, source owner and executable repair in reach."""
    result = fields(value, ('code', 'severity', 'phase', 'message', 'file', 'pointer',
        'run', 'source', 'operation', 'grant', 'field', 'path', 'required_action',
        'repair_owner', 'repair_action', 'next_action', 'guidance', 'blocked_checks'))
    for name, item in value.items():
        if name not in result and name != 'authorization_requirements':
            result[name] = brief(item)
    if 'authorization_requirements' in value:
        result['authorization_requirements'] = authorization_requirements(value['authorization_requirements'])
    return result


def diagnostics(values) -> list[dict]:
    return [diagnostic(value) for value in values or []]


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


def _input_row(value: dict) -> dict:
    result = fields(value, ('state', 'kind', 'directory', 'choices', 'context', 'source_task',
        'source_run', 'prepared_run', 'current', 'task', 'source_available', 'changed_since_save',
        'editable_locations', 'selection_required', 'assessment_required', 'next_actions',
        'source_requirements'))
    if value.get('route_scope') is not None:
        scope = value['route_scope']
        result['route_scope'] = fields(scope, ('route', 'operation', 'execution', 'features', 'model', 'service'))
        result['route_scope']['document_count'] = len(scope.get('documents', []))
    result['unresolved'] = diagnostics(value.get('unresolved'))
    if value.get('working_copy'):
        result['working_copy'] = _input_row(value['working_copy'])
    if value.get('diagnostics'):
        result['diagnostics'] = diagnostics(value['diagnostics'])
    return result


def authoring_state(root: Path, value: dict, *, choices: str | None = None) -> dict:
    result = fields(value, ('state', 'task_id', 'pending', 'selection_required', 'external_effect', 'next_actions'))
    result['diagnostics'] = diagnostics(value.get('diagnostics'))
    inputs = value.get('inputs', [])
    result['inputs'] = [_input_row(row) for row in inputs if row.get('current') or row.get('working_copy')
                        or row.get('changed_since_save') or row.get('unresolved') or not row.get('prepared_run')]
    result['input_count'] = len(inputs)
    result['historical_inputs_omitted'] = len(inputs) - len(result['inputs'])
    result['input_options'] = [{**fields(row, ('choices', 'directory', 'source_run', 'action')),
                               'unresolved': diagnostics(row.get('unresolved'))}
                              for row in value.get('input_options', [])]
    result['readings'] = [fields(row, ('state', 'route', 'operation', 'execution', 'current', 'snapshot',
        'reading', 'remaining', 'next_actions', 'applicability', 'progress'))
        for row in value.get('readings', []) if row.get('current')]
    result['reading_count'] = len(value.get('readings', []))
    result['decision_drafts'] = [fields(row, ('kind', 'run', 'candidate', 'path', 'available', 'ownership'))
                               for row in value.get('decision_drafts', []) if row.get('available')]
    selected = (value.get('context') or {}).get('input')
    result['context'] = {'work_file': (value.get('context') or {}).get('work_file'),
        'work': fields((value.get('context') or {}).get('work') or {},
            ('task_id', 'goal', 'next', 'questions', 'blocked_on', 'production_run')),
        'input': (fields(selected, ('state', 'directory', 'source_task', 'source_run', 'choices_file',
            'published_task', 'prepared_run', 'changed_since_build', 'editable_locations',
            'assessment_required', 'instruction', 'source_requirements')) if selected is not None else None),
        'read_action': action(root, 'inspect-inputs', ['--choices', choices] if choices else [],
            'Read the complete authoring context and editable source for the selected branch.')}
    if selected is not None:
        result['context']['input']['unresolved'] = diagnostics(selected.get('unresolved'))
    if value.get('last_check'):
        check = value['last_check']
        result['last_check'] = fields(check, ('task', 'operation_id', 'created_at', 'ok', 'path', 'state'))
        result['last_check']['diagnostics'] = diagnostics(check.get('diagnostics'))
    if value.get('saved'):
        result['saved'] = fields(value['saved'], ('run', 'state', 'working_changes', 'next_action', 'artifact', 'delivery'))
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
    if value.get('run') and not result.get('read_action'):
        result['read_action'] = action(root, 'inspect-inputs', ['--from-run', value['run'], '--view', 'full'],
            'Read this saved source run\'s complete task, source selections and remaining assessments.')
    return result


def _draft_inputs(root: Path, report: dict, choices: str | None) -> dict:
    result = fields(report, ('state', 'choices_file', 'context_file', 'authoring_work',
        'external_effect', 'next_actions', 'required_source_roles', 'source_requirements'))
    if 'derived_from' in report:
        result['derived_from'] = fields(report['derived_from'],
                                      (name for name in report['derived_from'] if name != 'source_run'))
        if 'source_run' in report['derived_from']:
            result['derived_from']['source_run'] = _source_run(root, report['derived_from']['source_run'])
    result['unresolved'] = diagnostics(report.get('unresolved'))
    guide = report.get('authoring_guide')
    if guide:
        result['authoring_guide'] = fields(guide, ('document_path', 'schema', 'example', 'explain_action',
                                                  'meaning', 'source_acquisition', 'source_requirements', 'input_contracts'))
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
              choices: str | None = None) -> dict:
    """Project one acquired command result without reading or writing any input."""
    if 'runs' in report:
        from production_status_view import summary
        result = summary(root, report, run=run)
    elif command == 'inspect-inputs' and report.get('state') == 'authoring-state':
        result = authoring_state(root, report, choices=choices)
    elif command == 'draft-inputs' and report.get('state') == 'draft':
        result = _draft_inputs(root, report, choices)
    elif command == 'acquire-source' and report.get('state') == 'source-acquired':
        result = fields(report, ('ok', 'state', 'changed', 'source', 'source_row', 'acquired',
            'choices_file', 'basis_file', 'projected_source', 'applications', 'subjects',
            'next_actions', 'external_effect'))
        result['unresolved'] = diagnostics(report.get('unresolved'))
    elif command in {'draft-principal-approval', 'draft-authority-update'} and 'choices' in report:
        result = fields(report, ('state', 'schema', 'unanswered', 'required_action', 'limit',
            'draft_file', 'expected_event', 'required_validation_mode', 'approval_selection', 'phase',
            'selection_requirements'))
        authored = report['choices']
        result['binding'] = fields(authored.get('binding', authored),
            ('task_id', 'issuer', 'run', 'input_sha256', 'request_sha256', 'expected_event', 'selection'))
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
                                            'omitted': max(0, len(identifiers) - DETAIL_LIMIT)}
                                       for key, identifiers in report['changed_grants'].items()}
        else:
            result['grant_ids'] = [row['id'] for row in document['grants'][:DETAIL_LIMIT]]
            result['grant_ids_omitted'] = max(0, len(document['grants']) - DETAIL_LIMIT)
        result['next_action'] = action(root, 'status', ['--run', run] if run else [],
            'Inspect current requirements and continue the saved work under the imported authority.')
    elif command == 'draft-execution' and 'choices' in report:
        result = fields(report, ('decisions_file', 'next_action'))
        result.update(run=report['choices'].get('run'),
                      unresolved=_unanswered(report['choices']),
                      authority=authority(report.get('authority')),
                      authorization_requirements=authorization_requirements(report.get('authorization_requirements')))
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
    if report.get('diagnostics') is not None:
        result['diagnostics'] = diagnostics(report['diagnostics'])
    for name in ('warnings', 'runtime_warnings'):
        if name in report:
            result[name] = diagnostics(report[name])
    if 'next_action' not in result:
        result['next_action'] = _next_action(report)
    if result['next_action'] is None and report.get('selection_required'):
        result['next_action'] = {**action(root, 'inspect-inputs', [],
            'Choose an explicitly named editable branch; no branch was selected by this summary.'),
            'requires_author_input': True, 'alternatives': copy.deepcopy(report.get('next_actions', []))}
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
            result['next_action'] = action(root, 'prepare', selected,
                'Prepare this checked source when its authored choices are complete; execution remains separate.')
    return _summary_order(result)


def present(root: Path, report: dict, *, command: str, run: str | None = None,
            choices: str | None = None) -> dict:
    """Retain a complete report outside formal run history, then show its summary.

    Content-addressed snapshots are exclusive publications. Repeated identical
    reports reuse the same verified bytes. Failure to save a display must not
    turn a committed operation into a retry: include its full result inline and
    leave the caller's original outcome and exit-code calculation unchanged.
    """
    result = summarize(root, report, command=command, run=run, choices=choices)
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
    return _summary_order(result)
