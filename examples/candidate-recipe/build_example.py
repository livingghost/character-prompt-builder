#!/usr/bin/env python3
"""Read a candidate recipe from synthetic local recording evidence."""
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
import studio


def build() -> dict:
    with tempfile.TemporaryDirectory(prefix='synthetic-candidate-recipe-') as temporary:
        parent = Path(temporary)
        root = studio.init(parent / 'studio', 'synthetic-studio', 'Synthetic recipe evidence')
        studio.add_character(root, 'subject-a', '')
        request = {'model': 'synthetic:target', 'prompt': 'A synthetic neutral study.',
                   'seed': 19, 'width': 512, 'height': 512, 'request_id': 'synthetic-request'}
        # The layout a transport records with its request: where the prompt, the
        # seed and this run's own identifier sit.
        layout = {'model': ['model'], 'operation': None, 'primary_text': ['prompt'], 'negative_text': None,
                  'output_count': None, 'fixed_output_count': 1, 'seed': ['seed'], 'media': [],
                  'management': [['request_id']], 'content': [{'id': 'prompt', 'field': ['prompt']}],
                  'fields': [{'id': 'prompt', 'field': ['prompt'], 'kind': 'content'}]}
        (parent / 'request.json').write_bytes(c.encoded(request))
        (parent / 'response.json').write_bytes(c.encoded({'seed': 23}))
        (parent / 'result.bin').write_bytes(b'Synthetic retained bytes; not generated artwork.\n')
        row = studio.iterate(root, 'subject-a', 'base.front', parent / 'result.bin', package=None,
            request=parent / 'request.json', response=parent / 'response.json', note='Synthetic local fixture.',
            layout=layout)
        before = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}
        command = [sys.executable, str(ROOT / 'scripts/studio.py'), '--studio', str(root), 'recipe',
                   '--character', 'subject-a', '--slot', 'base.front', '--iteration', row['iteration_id']]
        response = subprocess.run(command, capture_output=True, text=True, check=False, timeout=30)
        if response.returncode:
            raise ValueError(response.stdout + response.stderr)
        result = json.loads(response.stdout)
        after = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}
        if before != after:
            raise ValueError('Recipe inspection changed the synthetic studio.')
        return {'synthetic': True, 'source_status': result['source_status'], 'slot': result['slot'],
                'seed': result['seed'], 'request': result['request'], 'settings': result['settings'],
                'verified_evidence': sorted(result['evidence']), 'inspection_changed_studio': False}


def main() -> int:
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


if __name__ == '__main__':
    raise SystemExit(main())
