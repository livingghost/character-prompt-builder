#!/usr/bin/env python3
"""Create a complete, explicitly synthetic no-network generation studio.

A scenario option prepares one more situation in the studio and prints the
commands that show it in `scenario.next`. Decisions, reviews and releases that a
scenario records are made by the labeled synthetic fixture operator, never by a
user, and authorize no real service.
"""
from __future__ import annotations
import argparse
import copy
import json
from pathlib import Path
import sys
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import execution_contract as c
import production_case_fixtures as fixtures

SCENARIOS = {
    'prompt-change': 'Change one prompt field, with the retrieval record reassessed for the new wording.',
    'reference': 'Change a run without references into one with a prepared reference set.',
    'sheet': 'Record the output into a character sheet slot.',
    'scope-shortage': 'Prepare under a grant that lacks one handoff target, so execute stops before any reservation.',
    'budget-change': 'Replace the grant with a larger cost limit and query the budget.',
    'outcome-unknown': 'Leave a send whose answer was lost, for resume.',
    'partial-review': 'Reject a candidate on one failed criterion and leave the other one unassessed.',
    'release': 'Query the budget and release a reservation that made no external effect.',
    'log-export': 'List and export the automatic operation logs.',
}


def command(*arguments: str) -> list[str]:
    return [sys.executable, str(ROOT / 'scripts/production_workflow.py'), *arguments]


def prepared(root: Path, task: str = 'task.json') -> str:
    import production_workflow as workflow
    return workflow.prepare(root, task)['run']


def executed(root: Path, run: str, decisions: str) -> dict:
    import production_execution as execution
    return execution.execute(root, run, decisions_file=fixtures.fill_decisions(root, run, decisions))


def scenario(name: str, root: Path, runtime: list[str]) -> dict:
    """Prepare one scenario; return its run and the commands that show it."""
    import production_store as store
    import production_workflow as workflow
    R = str(root)
    if name == 'prompt-change':
        from prompt_retrieval import settle_retrieval_record
        run = prepared(root)
        prompt = fixtures.PROMPT + ' The same robot stays alone in the frame.'
        record = settle_retrieval_record(c.load(root / 'retrieval.json'), prompt=prompt, plot=c.load(root / 'plot.json'))
        fixtures.write(root / 'variants/retrieval.json', record)
        fixtures.write(root / 'variants/prompt.json', {'changes': {'prompt': prompt, 'retrieval-record': {'path': 'variants/retrieval.json'}},
            'reason': 'Reword the prompt; the retrieval record is reassessed for the new wording.'})
        return {'run': run, 'next': [command('variant', '--root', R, '--from', run, '--changes-file', 'variants/prompt.json', '--prepare')]}
    if name == 'reference':
        from prepare_generation_references import prepare_references
        from transport_synthetic import _png
        run = prepared(root)
        c.atomic(root / 'variants/palette.png', _png(32, 32, b'\x50\x78\xa0'))
        references = prepare_references([{'role': 'palette', 'source': {'kind': 'supplied-file', 'reference_id': 'synthetic-palette',
            'resolved_path': str(root / 'variants/palette.png')}}], model=fixtures.MODEL_ID, output_dir=root / 'variants/reference-preparation')
        fixtures.write(root / 'variants/references.json', references)
        fixtures.write(root / 'variants/reference.json', {'changes': {'references': {'path': 'variants/references.json'},
            'execution-mode': 'reference-guided'}, 'reason': 'Guide the palette with one prepared synthetic reference image.'})
        return {'run': run, 'next': [command('variant', '--root', R, '--from', run, '--changes-file', 'variants/reference.json', '--prepare')]}
    if name == 'sheet':
        task = c.load(root / 'task.json')
        task['recording'].update(slot='canon.primary', sheet_panel=True, subject_map={'robot': 'robot'})
        task['generation']['continuity']['robot'] = 'undecided'
        fixtures.write(root / 'sheet/task.json', task)
        run = prepared(root, 'sheet/task.json')
        fixtures.fill_decisions(root, run, 'sheet/decisions.json')
        return {'run': run, 'next': [command('execute', '--root', R, '--run', run, '--decisions-file', 'sheet/decisions.json')]}
    if name == 'scope-shortage':
        authority = c.load(root / 'fixture-authority.json')
        authority['grants'][0]['targets'].remove('decision:expression')
        fixtures.write(root / 'scope/authority.json', authority)
        task = c.load(root / 'task.json')
        task['authority'] = 'scope/authority.json'
        fixtures.write(root / 'scope/task.json', task)
        run = prepared(root, 'scope/task.json')
        fixtures.fill_decisions(root, run, 'scope/decisions.json')
        return {'run': run, 'next': [command('status', '--root', R, '--run', run),
                                     command('execute', '--root', R, '--run', run, '--decisions-file', 'scope/decisions.json')]}
    if name == 'budget-change':
        run = prepared(root)
        task_id = c.load(root / 'task.json')['task_id']
        document = copy.deepcopy(store.authority(root, task_id))
        document['grants'][0]['limits']['cost']['amount'] = '250'
        fixtures.write(root / 'budget/authority.json', document)
        event = store.authority_record(root, task_id)['sha256']
        return {'run': run, 'authority_event': event,
                'next': [command('authority-import', '--root', R, '--file', 'budget/authority.json', '--expected-event', event),
                         command('status', '--root', R, '--budget')]}
    if name == 'outcome-unknown':
        import transport_synthetic
        run = prepared(root)
        # The synthetic send times out once, as an answer lost on the way back would.
        with patch.object(transport_synthetic, 'send', side_effect=TimeoutError('Synthetic lost answer')):
            executed(root, run, 'outcome/decisions.json')
        return {'run': run, 'next': [command('resume', '--root', R, '--run', run),
                                     command('draft-outcome', '--root', R, '--run', run, '--out', 'outcome/statement.json')]}
    if name == 'partial-review':
        from production_fixtures import ACTOR
        task = c.load(root / 'task.json')
        task['criteria'].append({'id': 'colour', 'strength': 'hard', 'text': 'The robot is drawn in red.', 'evidence': 'artifact'})
        fixtures.write(root / 'review/task.json', task)
        run = prepared(root, 'review/task.json')
        candidate = executed(root, run, 'review/decisions.json')['runs'][0]['candidates'][0]
        review = workflow.draft_review(root, run, candidate)
        review.update(reviewer=ACTOR, conclusion='Synthetic fixture review; not user approval.',
            observations=[{'evidence': 'candidate', 'locator': {'kind': 'whole'},
                'observation': 'The decoded synthetic PNG is one flat blue-grey field with no red.',
                'interpretation': 'The colour criterion fails on this observation alone.',
                'limitations': ['Only the local synthetic fixture bytes are examined.']}],
            checks=[{'criterion': 'colour', 'verdict': 'fail', 'observation_indices': [0],
                     'reason': 'No red appears anywhere in the image.'},
                    {'criterion': 'output', 'verdict': 'not-assessed', 'observation_indices': [],
                     'reason': 'Not checked; the colour failure already decides this candidate.'}],
            repairs=[], unresolved=['The synthetic transport cannot draw a red robot.'])
        fixtures.write(root / 'review/review.json', review)
        recorded = workflow.review(root, run, 'review/review.json')
        disposition = workflow.draft_disposition(root, run, candidate)
        disposition.update(actor=ACTOR, review=recorded['sha256'],
                           reason='Rejected on the observed colour failure; the output criterion stays unassessed.')
        fixtures.write(root / 'review/disposition.json', disposition)
        status = command('candidate-status', '--root', R, '--run', run, '--candidate', candidate)
        return {'run': run, 'candidate': candidate,
                'next': [status, command('disposition', '--root', R, '--run', run, '--file', 'review/disposition.json'), status]}
    if name == 'release':
        import production_execution as execution
        from production_fixtures import ACTOR
        run = prepared(root)
        # The execution stops after its reservation and before any external effect.
        with patch.object(execution, '_transmit', return_value={'stopped_before_effect': True}):
            executed(root, run, 'release/decisions.json')
        import reservation_lifecycle as accounting
        reservation = accounting.all_states(root, run=run)[0]['reservation_id']
        return {'run': run, 'reservation': reservation, 'release_actor': ACTOR,
                'next': [command('status', '--root', R, '--budget'),
                         command('draft-release', '--root', R, '--run', run, '--reservation', reservation, '--out', 'release/request.json'),
                         command('release-reservation', '--root', R, '--run', run, '--request', 'release/request.json')]}
    if name == 'log-export':
        return {'run': None, 'next': [command('prepare', '--root', R, '--task', 'task.json', *runtime),
                                      command('logs', '--root', R),
                                      command('logs-export', '--root', R, '--out', 'exported-logs', '--without-streams')]}
    raise ValueError(name)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True, help='New directory for the synthetic studio and its pack runtime.')
    parser.add_argument('--include-retarget', action='store_true', help='Include a second synthetic target and explicitly reassessed task.')
    parser.add_argument('--include-upscale',action='store_true',help='Include an explicitly synthetic source image and upscale task.')
    # One scenario per studio: each one sets the grant or the runs that it shows.
    group = parser.add_mutually_exclusive_group()
    for name, text in SCENARIOS.items():
        group.add_argument('--include-' + name, dest='scenario', action='store_const', const=name, help=text)
    args = parser.parse_args()
    out = args.out.resolve()
    if out.exists():
        parser.error('Use a new output directory; an example studio is not overwritten.')
    case = fixtures.create(out / 'studio', out / 'runtime', with_alternate=args.include_retarget,with_upscale=args.include_upscale)
    if args.include_retarget:
        fixtures.alternate_task(case['root'])
    if args.include_upscale:
        fixtures.upscale_task(case['root'])
    settings = case['settings']
    runtime = ['--state-file', str(settings.state_file), '--cache-dir', str(settings.cache_dir),
               '--managed-root', str(settings.managed_root), '--pack-root', str(case['pack'])]
    prepare = command('prepare', '--root', str(case['root']), '--task', 'task.json', *runtime)
    c.atomic(out / 'prepare-argv.json', c.encoded(prepare))
    shown = {'name': args.scenario, **scenario(args.scenario, case['root'], runtime)} if args.scenario else None
    print(json.dumps({'synthetic': True, 'task': str(case['root'] / 'task.json'), 'prepare_argv': prepare,
                      'retarget_task': str(case['root'] / 'retarget/task.json') if args.include_retarget else None,
                      'upscale_task': str(case['root']/'upscale/task.json') if args.include_upscale else None,
                      'scenario': shown, 'network_generation': False,
                      'approval': 'Synthetic fixture only, not authority for any real service.'}, indent=2))
    return 0


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
