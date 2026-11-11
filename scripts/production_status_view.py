"""Project current status for navigation while keeping complete judgment views explicit."""
from __future__ import annotations

import copy
from pathlib import Path

from cli_invocation import python_argv

SCRIPT = Path(__file__).with_name('production_workflow.py')


def _action(root: Path, command: str, arguments: list[str], reason: str) -> dict:
    return {'command': command, 'argv': python_argv(SCRIPT, command, '--root', str(root), *arguments),
            'reason': reason}


def summary(root: Path, report: dict, *, run: str | None = None) -> dict:
    """Keep every state, blocker and continuation; link complete decision evidence once.

    This presentation performs no new reads and does not alter the acquired status.
    It cannot be used as a source of authorization or review evidence. The owning
    operations still acquire and verify their current complete inputs.
    """
    result = copy.deepcopy(report)
    result['view'] = 'summary'
    result['details_action'] = _action(root, 'status',
        (['--run', run] if run is not None else []) + ['--view', 'full'],
        'Inspect complete current status, including authority declarations and authored source content.')
    current = result.get('current_task')
    if current and current.get('authoring'):
        authoring = current['authoring']
        context = authoring.get('context')
        if context is not None:
            selected = context.get('input')
            if selected is not None:
                for field in ('choices', 'task_content', 'sources'):
                    selected.pop(field, None)
            context['read_action'] = _action(root, 'inspect-inputs', [],
                'Read complete authoring context and its editable source; choose an explicit draft when several remain.')
    for item in result['runs']:
        identifier = item['run']
        detail = _action(root, 'status', ['--run', identifier, '--view', 'full'],
            'Read this run\'s complete current evidence and authority without changing it.')
        item['details_action'] = detail
        authority = item.get('authority')
        if authority is not None:
            authority.pop('document', None)
            authority['read_action'] = detail
        for candidate in item.get('candidate_states', []):
            for field in ('decision_detail', 'owner_acceptance'):
                candidate.pop(field, None)
            candidate['details_action'] = _action(root, 'candidate-status',
                ['--run', identifier, '--candidate', candidate['candidate']],
                'Read the complete decision, exceptions and review state for this candidate.')
    return result
