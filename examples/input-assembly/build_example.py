#!/usr/bin/env python3
"""Record actual input-helper CLI results from a local synthetic text task."""
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
import reading_fixtures


def command(root, name, *args, expected=0):
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/production_workflow.py'), name,
        '--root', str(root), '--task', 'task.json', *args], capture_output=True, text=True, encoding='utf-8', timeout=environment_seconds('EXAMPLE_COMMAND_TIMEOUT_SECONDS'))
    if result.returncode != expected:
        raise ValueError(result.stdout + result.stderr)
    return json.loads(result.stdout)


def build():
    with tempfile.TemporaryDirectory(prefix='synthetic-input-example-') as directory:
        root = Path(directory)
        task = {'task_id': 'synthetic-input-example', 'route': 'development', 'features': [],
                'sources': [], 'route_reading': 'reading.json',
                'delivery': {'path': 'delivery.txt', 'transport': 'authored-rendition',
                             'translation_notes': 'Retain the authored synthetic local text.'},
                'criteria': [{'id': 'output', 'text': 'Inspect the local synthetic result.',
                              'strength': 'hard', 'evidence': 'text'}]}
        task.update(artifact='text', execution='authored', production_id='01900000-0000-7000-8000-000000000010',
                    authority='authority.json', world_views=[], direction={'purpose': 'Synthetic local input assembly.',
                        'intended_effect': 'Inspect local files.', 'basis': [], 'decisions': [], 'action_slice': None,
                        'limitations': ['Synthetic exercise, not approval or service evidence.']})
        (root / 'task.json').write_bytes(c.encoded(task))
        (root / 'delivery.txt').write_text('Synthetic input assembly exercise.\n', encoding='utf-8')
        original = (root / 'task.json').read_bytes()
        # Fixed quotations belong only to this synthetic exercise.
        # A real operator reads the source and supplies its applications.
        reading = reading_fixtures.fixture_reading(route='development', project=root,
                                                   ledger=root / 'work/reads.jsonl')
        inspection = command(root, 'inspect-inputs')
        draft = command(root, 'draft-inputs', '--out-dir', 'draft')
        missing = command(root, 'build-inputs', '--choices', draft['choices_file'],
                          '--out-dir', 'missing', expected=1)
        if (root / 'missing').exists():
            raise ValueError('Unanswered choices published formal files.')
        authored = c.load(root / draft['choices_file'])
        choices = authored['choices']
        choices['reading']['reading_key'] = reading['reading_key']
        choices['reading']['applied'] = reading['applied']
        choices['reading']['resource_applied'] = reading['resource_applied']
        (root / draft['choices_file']).write_bytes(c.encoded(authored))
        result = command(root, 'build-inputs', '--choices', draft['choices_file'], '--out-dir', 'built')
        correct = all(c.digest((root / ref['path']).read_bytes()) == ref['sha256'] for ref in result['inputs'].values())
        if not correct or (root / 'task.json').read_bytes() != original:
            raise ValueError('Formal file integrity or the authored task changed.')
        return {'synthetic': True, 'inspection_state': inspection['state'],
                'draft_state': draft['state'], 'unanswered': [entry['field'] for entry in missing['unresolved']],
                'incomplete_output_published': False, 'built_state': result['state'],
                'input_names': sorted(result['inputs']), 'file_hashes_match': correct,
                'original_task_preserved': True, 'execution_ready': result['execution_ready'],
                'external_effect': result['external_effect'], 'budget_effect': result['budget_effect'],
                'production_created': (root / 'production').exists()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--out', type=Path, default=Path(__file__).with_name('report.json'))
    args = parser.parse_args()
    raw = c.encoded(build())
    if args.check:
        if not args.out.is_file() or args.out.read_bytes() != raw:
            raise SystemExit('Synthetic output differs. Rebuild this example.')
    else:
        args.out.write_bytes(raw)
    print(raw.decode(), end='')
    return 0


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
