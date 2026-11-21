"""Author observed evidence with named citations; derive immutable review bindings.

The reviewer owns observations and verdicts. This adapter only binds those
answers to the retained artifact and translates named citations to indices.
"""
from __future__ import annotations

import copy
from pathlib import Path

import execution_contract as c


def observe(root: Path, run: str, candidate: str | None = None) -> dict:
    """Expose candidate access and unanswered observations before assessment criteria."""
    import production_operations as operations
    from production_workspace import workspace
    guide = operations.review_authoring_guide(root, run, candidate)
    template = guide['observation_template']
    return {'binding': {'run': run, 'candidate': candidate},
        'choices': {'reviewer': '', 'observations': [{'id': 'view', 'source': template['evidence'],
            'locator': copy.deepcopy(template['locator']), 'observation': '',
            'interpretation': '', 'limitations': []}]},
        'workspace': workspace(root, run, phase='observe', candidate=candidate),
        'instructions': 'Inspect the actual saved artifact and record its visible or measurable features with '
            'locators and limits. If an independent first observer is required, give that observer only this '
            'workspace and this unanswered form. Preserve that observation before continuing to assessment.'}


def observed(value: dict) -> dict:
    c.exact(value, {'reviewer', 'observations'}, 'first observation')
    c.text(value['reviewer'], 'actual observer')
    if not isinstance(value['observations'], list) or not value['observations']:
        raise ValueError('Record at least one actual observation before assessment.')
    names = set()
    for row in value['observations']:
        c.exact(row, {'id', 'source', 'locator', 'observation', 'interpretation', 'limitations'},
                'first observation entry')
        name = c.text(row['id'], 'observation name')
        if name in names:
            raise ValueError('Each first observation needs its own name.')
        names.add(name)
        if row['source'] != 'candidate':
            raise ValueError('First observations refer to the actual saved candidate.')
        c.text(row['observation'], 'actual observation')
        c.text(row['interpretation'], 'observation interpretation')
        if not isinstance(row['limitations'], list):
            raise ValueError('Record observation limitations as a list.')
    return copy.deepcopy(value)


def draft(root: Path, run: str, candidate: str | None = None) -> dict:
    import production_operations as operations
    loaded = operations.read_run(root, run)
    original = operations.draft_review(root, run, candidate)
    guide = operations.review_authoring_guide(root, run, candidate, loaded=loaded)
    template = guide['observation_template']
    from route_reading import operation_reading_action
    from cli_invocation import python_argv
    from production_workspace import workspace
    candidate_args = ['--candidate', candidate] if candidate else []
    return {
        'binding': {'run': run, 'candidate': candidate, 'original': original},
        'choices': {
            'reviewer': '',
            'observations': [{'id': 'view', 'source': template['evidence'],
                'locator': copy.deepcopy(template['locator']), 'observation': '',
                'interpretation': '', 'limitations': []}],
            'checks': {row['criterion']: {'verdict': 'not-assessed', 'supports': ['view'], 'reason': ''}
                       for row in original['checks']},
            'evidence': [], 'repairs': [], 'unresolved': [], 'conclusion': '',
        },
        'evidence': guide['automatic_evidence'],
        'reading_action': operation_reading_action(root, run, operation='review', loaded=loaded),
        'workspace': workspace(root, run, phase='review', candidate=candidate),
        'observation_action': {'command': 'workspace', 'argv': python_argv(
            Path(__file__).with_name('production_workflow.py'), 'workspace', '--root', str(root),
            '--run', run, '--phase', 'observe', *candidate_args),
            'reason': 'Supply only this candidate view to an independent first observer.'},
        'criteria': copy.deepcopy(loaded.prepared['task']['criteria']),
        'instructions': 'Inspect the saved artifact first. Write what you observed, its interpretation and limits. '
            'Assess every criterion. Supports names observations in this form; the recorder derives array positions '
            'and the exact artifact binding. Add comparison observations using the evidence sources shown here.',
    }


def compile_answers(binding: dict, answers: dict) -> dict:
    c.exact(answers, {'reviewer', 'observations', 'checks', 'evidence', 'repairs', 'unresolved', 'conclusion'},
            'review answers')
    original = copy.deepcopy(binding['original'])
    for key in ('reviewer', 'evidence', 'unresolved', 'conclusion'):
        original[key] = copy.deepcopy(answers[key])
    positions = {}
    original['observations'] = []
    for index, row in enumerate(answers['observations']):
        c.exact(row, {'id', 'source', 'locator', 'observation', 'interpretation', 'limitations'},
                'named observation')
        name = c.text(row['id'], 'observation name')
        if name in positions:
            raise ValueError('Each observation needs its own name: ' + name)
        positions[name] = index
        original['observations'].append({'evidence': row['source'],
            **{key: copy.deepcopy(row[key]) for key in ('locator', 'observation', 'interpretation', 'limitations')}})

    def citations(names):
        if not isinstance(names, list) or any(name not in positions for name in names):
            raise ValueError('Supports must name observations present in this review.')
        if len(names) != len(set(names)):
            raise ValueError('Cite each supporting observation once.')
        return [positions[name] for name in names]

    expected = [row['criterion'] for row in original['checks']]
    if not isinstance(answers['checks'], dict) or set(answers['checks']) != set(expected):
        raise ValueError('Assess each retained criterion exactly once; edit criteria at their input owner.')
    for row in original['checks']:
        answer = answers['checks'][row['criterion']]
        c.exact(answer, {'verdict', 'supports', 'reason'}, 'criterion answer')
        row.update(verdict=answer['verdict'], reason=answer['reason'],
                   observation_indices=citations(answer['supports']))
    original['repairs'] = []
    for row in answers['repairs']:
        c.exact(row, {'id', 'decisions', 'supports', 'operation', 'targets', 'reason'}, 'repair answer')
        original['repairs'].append({**{key: copy.deepcopy(value) for key, value in row.items() if key != 'supports'},
                                   'observation_indices': citations(row['supports'])})
    return original


def apply(root: Path, directory: Path, answers: dict, *, binding: dict) -> dict:
    import production_operations as operations
    value = compile_answers(binding, answers)
    filename = directory / ('review-' + c.content_id(value) + '.json')
    if not filename.exists():
        c.atomic(filename, c.encoded(value))
    relative = filename.relative_to(root).as_posix()
    if binding['candidate'] is None:
        result = operations.review_authored(root, binding['run'], relative)
    else:
        result = operations.review(root, binding['run'], relative)
    return {'run': binding['run'], 'candidate': binding['candidate'], 'review_file': relative,
            'result': result}
