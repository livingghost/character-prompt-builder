#!/usr/bin/env python3
"""Exercise a real-image review -> scoped repair -> fresh run through the CLI.

Synthetic pixels and explicit synthetic authority demonstrate processing only.
They do not measure character performance, model quality or user acceptance.
"""
from __future__ import annotations
import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import sys

SKILL = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL / 'scripts'))
import production_fixtures as fixture
from io_budget import environment_seconds
from PIL import Image, ImageDraw


def run(out: Path) -> dict:
    if out.exists():
        raise ValueError('choose a new output directory')
    out.mkdir(parents=True)
    log = []
    def write(name, value):
        (out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    def command(script, *args, parse=True):
        argv = [sys.executable, '-B', str(SKILL / 'scripts' / script), *map(str, args)]
        result = subprocess.run(argv, cwd=out, capture_output=True, text=True, encoding="utf-8",
                                env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'},
                                timeout=environment_seconds('EXAMPLE_COMMAND_TIMEOUT_SECONDS'))
        log.append({'argv': argv, 'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr})
        write('commands.json', log)
        if result.returncode:
            raise ValueError(result.stdout + result.stderr)
        return json.loads(result.stdout) if parse else result.stdout
    def workflow(rid, operation, *args):
        return command('production_workflow.py', operation, '--root', out, '--run', rid, *args)
    def authorize(rid, intent):
        n = len(log); ip = f'intent-{n}.json'; rp = f'authorization-{n}.json'
        write(ip, intent)
        request = workflow(rid, 'draft-authorization', '--grant', 'fixture-grant', '--intent', ip, '--out', rp)
        request['reason'] = 'Explicit synthetic fixture instruction; no user consent or paid generation is claimed.'
        write(rp, request)
        return workflow(rid, 'authorize', '--file', rp)['sha256']
    command('work_ledger.py', '--studio', out, 'begin', '--goal', 'Synthetic localized image repair',
            '--step', 'observe', '--step', 'repair', parse=False)
    task_id = json.loads((out / 'work/current.json').read_text(encoding='utf-8'))['task_id']
    (out / 'brief.txt').write_text('Processing fixture: a central region must differ from the surrounding field. No cast, story or audience claim.\n', encoding='utf-8')
    (out / 'delivery.txt').write_text('Use an unbroken field for the initial diagnostic fixture.\n', encoding='utf-8')
    task = {'task_id': task_id, 'route': 'development', 'features': [],
            'sources': [{'id': 'brief', 'path': 'brief.txt', 'role': 'world', 'disposition': 'applied',
                         'locator': 'whole', 'reason': 'Explicit synthetic processing requirement.'}],
            'delivery': {'path': 'delivery.txt', 'transport': 'authored-rendition', 'translation_notes': 'Only selected expression instructions.'},
            'criteria': [{'id': 'region', 'strength': 'hard', 'text': 'Actual central and peripheral pixels differ.'}],
            'world_views': []}
    fixture.task(out, task, artifact='image')
    task['criteria'][0]['evidence'] = 'image'
    task['direction'].update(purpose='Demonstrate a scoped correction from an actual failed image observation.',
        intended_effect='A distinct central region, measured only as a synthetic pixel condition.', basis=['brief'])
    def option(key, expression, instruction):
        return {'id': key, 'expression': expression,
                'realization': {'method': 'authored raster composition', 'instructions': instruction,
                                'capability_source': None, 'limitations': ['No temporal behavior or audience effect tested.']},
                'tradeoffs': ['This option changes the intended central/peripheral contrast.']}
    task['direction']['decisions'] = [{'id': 'expression', 'question': 'How is the region separated?', 'importance': 'material',
        'basis': ['brief'], 'options': [option('uniform', 'An uninterrupted field.', 'Fill the whole image uniformly.'),
                                      option('local', 'A differentiated central area.', 'Change only the central region.')],
        'selected': 'uniform', 'reason': 'A deliberately failing initial diagnostic fixture.', 'criteria': ['region'],
        'depends_on': [], 'deviations': []}]
    write('task.json', task)
    first = command('production_workflow.py', 'prepare', '--root', out, '--task', 'task.json')['run']
    def capture_and_review(rid, filename, corrected):
        intent = workflow(rid, 'handoff-intent', '--recipient', 'synthetic raster fixture', '--method', 'manual')
        workflow(rid, 'handoff', '--recipient', 'synthetic raster fixture', '--method', 'manual',
                 '--authorization', authorize(rid, intent))
        image = Image.new('RGB', (32, 24), (64, 64, 64))
        if corrected:
            ImageDraw.Draw(image).rectangle((12, 8, 19, 15), fill=(192, 192, 192))
        image.save(out / filename)
        candidate = workflow(rid, 'capture', '--artifact', filename, '--note', 'Authored synthetic pixels, not model artwork.')
        rp = filename + '.review.json'
        review = workflow(rid, 'draft-review', '--candidate', candidate['sha256'], '--out', rp)
        with Image.open(out / filename) as actual:
            center, corner = actual.getpixel((16, 12)), actual.getpixel((0, 0))
        verdict = 'pass' if center != corner else 'fail'
        review.update(reviewer=fixture.ACTOR,
            observations=[{'evidence': 'candidate', 'locator': {'kind': 'image-region', 'x': 0, 'y': 0, 'width': 1, 'height': 1},
                           'observation': f'Center pixel {center}; peripheral pixel {corner}.',
                           'interpretation': 'The declared contrast condition is ' + ('present.' if corrected else 'absent.'),
                           'limitations': ['Pixel processing only; no aesthetic, character or audience claim.']}],
            conclusion='Located synthetic processing observation; not user approval.')
        review['checks'][0].update(verdict=verdict, observation_indices=[0], reason='Compare the actual captured pixels.')
        if not corrected:
            review['repairs'] = [{'id': 'separate-region', 'decisions': ['expression'], 'observation_indices': [0],
                                  'operation': 'Local raster composition edit.', 'targets': ['delivery', 'decision:expression'],
                                  'reason': 'The actual image lacks the explicitly required pixel distinction.'}]
        write(rp, review)
        workflow(rid, 'review', '--file', rp)
        return candidate
    initial = capture_and_review(first, 'initial.png', False)
    revised = copy.deepcopy(task)
    revised['direction']['decisions'][0].update(selected='local', reason='The actual initial artifact failed the declared contrast check.')
    revised['delivery']['path'] = 'revised-delivery.txt'
    (out / 'revised-delivery.txt').write_text('Change only the central image region.\n', encoding='utf-8')
    write('revised-task.json', revised)
    intent = workflow(first, 'revision-intent', '--task', 'revised-task.json', '--candidate', initial['sha256'], '--repair', 'separate-region')
    child = workflow(first, 'revise', '--task', 'revised-task.json', '--candidate', initial['sha256'], '--repair', 'separate-region',
                     '--authorization', authorize(first, intent))['run']
    final = capture_and_review(child, 'revised.png', True)
    choice = workflow(child, 'draft-selection', '--candidate', final['sha256'], '--out', 'selection.json')
    choice.update(selector=fixture.ACTOR, reason='Select only the demonstrated fixture deliverable; no canon adoption.')
    write('selection.json', choice)
    intent = workflow(child, 'selection-intent', '--file', 'selection.json')
    choice['authorization'] = authorize(child, intent)
    write('selection.json', choice)
    workflow(child, 'select', '--file', 'selection.json')
    workflow(child, 'complete')
    for index in (1, 2):
        command('work_ledger.py', '--studio', out, 'step', index, parse=False)
    command('work_ledger.py', '--studio', out, 'finish', parse=False)
    result = {'ok': workflow(child, 'resume')['next'] == 'done', 'parent': first, 'run': child,
              'commands': len(log), 'fixture_only': True, 'network_calls': 0}
    write('result.json', result)
    return result


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.out.absolute()), indent=2))
