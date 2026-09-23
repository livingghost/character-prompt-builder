#!/usr/bin/env python3
"""Exercise public craft consultation commands with synthetic local authoring."""
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


def call(root, operation, *args):
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/production_workflow.py'), operation,
        '--root', str(root), '--task', 'task.json', *args], capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise ValueError(result.stdout + result.stderr)
    return json.loads(result.stdout)


def build(root):
    task = {'task_id': 'synthetic-craft', 'route': 'development', 'features': [],
            'sources': [], 'route_reading': 'reading.json',
            'delivery': {'path': 'delivery.txt', 'transport': 'authored-rendition',
                         'translation_notes': 'Use only the authored synthetic scope.'},
            'criteria': [{'id': 'readability', 'text': 'Keep the declared subject information readable.',
                          'strength': 'hard', 'evidence': 'text'}]}
    (root / 'delivery.txt').write_text('Synthetic local direction with readable subject information.\n', encoding='utf-8')
    task.update(artifact='text', execution='authored', production_id='01900000-0000-7000-8000-000000000030',
                authority='authority.json', world_views=[], direction={'purpose': 'Synthetic craft consultation.',
                    'intended_effect': 'Inspect the planned lighting relation.', 'basis': [], 'decisions': [],
                    'action_slice': None, 'limitations': ['Synthetic local example, not a generated image.']})
    (root / 'task.json').write_bytes(c.encoded(task))
    spec = c.load(ROOT / 'templates/production-spec-template.json')
    spec['lighting']['key_light'] = 'A single side window with retained detail on the shadow side.'
    (root / 'spec.json').write_bytes(c.encoded(spec))
    original_task = (root / 'task.json').read_bytes()
    original_spec = (root / 'spec.json').read_bytes()
    runtime = ['--state-file', str(ROOT / 'config/default-pack-state.json'),
               '--managed-root', str(ROOT / 'packs'), '--cache-dir', str(root / 'cache')]
    search = call(root, 'consult-presets', '--query', 'window light interior', '--focus', 'detail',
                  '--out-dir', 'search', *runtime)
    candidates = [hit['id'] for result in search['search']['results'] for hit in result['result']['results']]
    selected = 'lighting-cool-window'  # Explicit synthetic author choice, not the highest-ranked result.
    if selected not in candidates:
        raise ValueError('The declared example choice is not in the observed search results.')
    opened = call(root, 'consult-presets', '--previous', search['consultation'], '--inspect', selected,
                  '--out-dir', 'opened', *runtime)
    decisions = {'source_id': 'window-method', 'reason': 'Retain the declared readability while applying a side-window relation.',
        'uses': [{'record_id': selected, 'borrowed': 'One side window with readable face planes.',
                  'preserved': 'Shadow-side identity detail and the authored subject color.',
                  'changed': 'Apply the relation to this neutral scene, without adopting the original setting.',
                  'targets': ['/lighting/key_light'], 'review_criteria': ['readability'],
                  'review_question': 'Does the actual output preserve readable subject detail in the shadow?'}], 'not_used': []}
    (root / 'decisions.json').write_bytes(c.encoded(decisions))
    result = call(root, 'apply-presets', '--consultation', opened['consultation'], '--decisions', 'decisions.json',
                  '--spec', 'spec.json', '--out-dir', 'applied', *runtime)
    application = c.load(root / result['application'])
    new_spec = c.load(root / result['production_spec'])
    expected = dict(spec, selected_preset_ids=[selected])
    if new_spec != expected or (root / 'spec.json').read_bytes() != original_spec:
        raise ValueError('Authored fields were changed by application.')
    import preset_consultation
    questions = preset_consultation.review_questions(root, c.load(root / result['task']))
    if questions['readability'] != [decisions['uses'][0]['review_question']]:
        raise ValueError('The authored review question was not carried to its declared criterion.')
    return {'synthetic': True, 'searchable_records': search['scope']['searchable']['total_records'],
            'search_layers': [row['request_id'] for row in search['search']['results']],
            'selected_preset_ids': new_spec['selected_preset_ids'],
            'full_record_preserved': application['applications'][0]['source']['record'] == opened['inspected'][0]['record'],
            'authored_fields_preserved': new_spec == expected,
            'original_task_preserved': (root / 'task.json').read_bytes() == original_task,
            'review_questions': questions, 'execution_ready': result['execution_ready'],
            'external_effect': result['external_effect'], 'budget_effect': result['budget_effect']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--out', type=Path, default=Path(__file__).with_name('report.json'))
    parser.add_argument('--workspace', type=Path, help='New external directory retaining the actual commands and files.')
    args = parser.parse_args()
    if args.workspace is not None:
        args.workspace.mkdir(parents=True, exist_ok=False)
        result = build(args.workspace.resolve())
    else:
        with tempfile.TemporaryDirectory(prefix='synthetic-craft-example-') as temporary:
            result = build(Path(temporary))
    raw = c.encoded(result)
    if args.check:
        if not args.out.is_file() or args.out.read_bytes() != raw:
            raise SystemExit('Synthetic output differs. Rebuild this example.')
    else:
        args.out.write_bytes(raw)
    print(raw.decode(), end='')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
