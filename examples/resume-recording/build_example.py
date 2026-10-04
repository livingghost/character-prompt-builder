#!/usr/bin/env python3
"""Build a deterministic summary from a synthetic, locally prepared production run."""
from __future__ import annotations
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import execution_contract as c
from io_budget import environment_seconds
import production_workflow as w
import work_ledger


def summary(value):
    row = value['runs'][0]
    action = row['next_action']
    # The action's argv names the temporary Studio, so the recorded summary keeps its command and reason.
    return {'integrity': row['integrity'],
            'current_inputs': not row['freshness_diagnostics'],
            'readiness': row['readiness'], 'submission': row['submission'],
            'task_disposition': row['task_disposition'],
            'next_action': None if action is None else {'command': action['command'], 'reason': action['reason']},
            'freshness_codes': [item['code'] for item in row['freshness_diagnostics']]}


def build():
    with tempfile.TemporaryDirectory(prefix='synthetic-resume-example-') as temporary:
        root = Path(temporary)
        started = work_ledger.begin(root, 'Synthetic recovery example', ['inspect retained evidence'])
        (root / 'delivery.txt').write_text('Synthetic local instructions.\n', encoding='utf-8')
        task = {'task_id': started['task_id'], 'route': 'development', 'features': [], 'sources': [],
                'delivery': {'path': 'delivery.txt', 'transport': 'authored-rendition',
                             'translation_notes': 'Synthetic authored fixture.'},
                'criteria': [{'id': 'output', 'strength': 'hard', 'text': 'Inspect retained output.'}]}
        run = prepare_fixture(root, task)
        command = [sys.executable, str(ROOT / 'scripts/production_workflow.py'), 'resume', '--root', str(root), '--run', run]
        before = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", check=False, timeout=environment_seconds("EXAMPLE_COMMAND_TIMEOUT_SECONDS"))
        if before.returncode != 0:
            raise ValueError(before.stdout + before.stderr)
        (root / 'delivery.txt').write_text('Revised synthetic local instructions.\n', encoding='utf-8')
        after = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", check=False, timeout=environment_seconds("EXAMPLE_COMMAND_TIMEOUT_SECONDS"))
        if after.returncode != 0:
            raise ValueError('A changed live source must not make saved history unreadable: ' + after.stdout + after.stderr)
        before_summary, after_summary = summary(json.loads(before.stdout)), summary(json.loads(after.stdout))
        if after_summary['integrity'] != 'intact' or after_summary['readiness'] != 'blocked' or after_summary['current_inputs']:
            raise ValueError('The changed fixture must retain history and diagnose execution freshness.')
        import production_store as store
        reservations = [row for row in store.event_rows(root, run) if row['event'] == 'reservation-created']
        if reservations:
            raise ValueError('Preparing or authorizing a local example must not reserve a generation request.')
        return {'synthetic': True, 'reservation_count': len(reservations),
                'before_change': before_summary, 'after_change': after_summary}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--out', type=Path, default=Path(__file__).with_name('report.json'))
    args = parser.parse_args()
    raw = (json.dumps(build(), indent=2, sort_keys=True) + '\n').encode()
    if args.check:
        if not args.out.is_file() or args.out.read_bytes() != raw:
            raise SystemExit('Synthetic report differs; rebuild it with this script.')
    else:
        args.out.write_bytes(raw)
    print(raw.decode(), end='')
    return 0


def prepare_fixture(root, task):
    import production_fixtures as fixture
    task['world_views'] = []
    fixture.task(root, task)
    (root / 'task.json').write_bytes(c.encoded(task))
    run = w.prepare(root, 'task.json')['run']
    fixture.grant(root, run, {'operation': 'submit', 'targets': ['delivery'], 'payload': {'count': 1, 'synthetic': True}})
    return run


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
