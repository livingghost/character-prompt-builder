#!/usr/bin/env python3
"""Walk one idea to a dispatch preview offline, never a production approval.

python examples/feature-walkthrough/run.py --out /tmp/cpb-walkthrough

The walkthrough uses the bundled commons pack in a new pack state under --out.
It runs each command below in order for one synthetic one-off portrait of a
person, packages the prompt for grok-imagine-image-2.0 and prints the exact
Runware request. It sends nothing and uses no credential; any network
connection attempt fails the run. Existing output is never replaced.
transcript.txt lists every command it ran with a short result.

  python scripts/studio.py init --out PROJECT --studio-id ID --title TITLE
  python scripts/studio.py character add C01 --studio PROJECT
  python scripts/work_ledger.py --studio PROJECT begin --goal GOAL --step STEP
  python scripts/execution_routes.py read generation --root PROJECT
  python scripts/production_workflow.py prepare --root PROJECT --task task.json
  python scripts/prompt_retrieval.py lookups.json --settle --prompt-file PROJECT/prompt.txt
      --plot-file plot.json --out retrieval.json
  python scripts/production_spec.py draft production-spec.json --model grok-imagine-image-2.0
      --brief TEXT --kind human --framing waist-up --continuity one-off
  python scripts/build_generation_payload.py --model grok-imagine-image-2.0 --prompt-file PROJECT/prompt.txt
      --plot-file plot.json --retrieval-record-file retrieval.json --production-spec-file production-spec.json
      --continuity C01=one-off --parameters '{"width":832,"height":1248}' --production-root PROJECT
      --out PROJECT/generation-package.json
  python scripts/dispatch.py PROJECT/generation-package.json --studio PROJECT --character C01 --slot explore
"""
from __future__ import annotations
import argparse
import contextlib
import importlib
import io
import json
import os
import shlex
import socket
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import catalog_cli
import execution_contract as c
import pack_manager as pm
import studio
from prompt_plot import content_sha256

MODEL = 'grok-imagine-image-2.0'
COMMONS = c.load(ROOT / 'packs/commons/pack.json')['pack_id']
SYNTHETIC = 'OFFLINE WALKTHROUGH FIXTURE - NOT REAL USER CONSENT'
BRIEF = 'A woman waits at a bus stop in light rain.'
PROMPT = ('A woman in a green raincoat waits at a bus stop in light rain, seen waist-up at eye level, '
          'soft grey daylight, the shelter glass beaded with drops behind her.')
PLOT = {
    'artifact_type': 'prompt-plot',
    'story': [{'id': 's1', 'beat': 'A woman waits for her bus on a rainy afternoon.', 'visibility': 'visible'}],
    'derived': [
        {'kind': 'shows', 'statement': 'one woman in a green raincoat at a bus stop', 'from': ['s1']},
        {'kind': 'placement', 'statement': 'she stands in front of the shelter glass', 'from': ['s1']},
        {'kind': 'composition', 'statement': 'a waist-up view at eye level', 'from': ['s1']},
        {'kind': 'must_preserve', 'statement': 'light rain and soft grey daylight', 'from': ['s1']},
        {'kind': 'free', 'statement': 'the exact street behind the shelter'},
    ],
}
PLOT['approved'] = {'by': SYNTHETIC, 'at': '2026-09-23T00:00:00Z', 'content_sha256': content_sha256(PLOT)}


def write(path: Path, value) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    path.write_text(text, encoding='utf-8', newline='\n')
    return path


def summary(text: str) -> str:
    """A short result: the plain lines a command printed, or a few fields of its JSON."""
    try:
        value = json.loads(text)
    except ValueError:
        value = None
    if isinstance(value, dict):
        fields = [f'{key}: {item}' for key, item in value.items()
                  if isinstance(item, (str, int, bool)) and len(str(item)) <= 80][:3]
        return '; '.join(fields)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    plain = []
    for line in lines:
        if line.startswith('{'):
            break
        plain.append(line)
    return '; '.join(plain[:8] or lines[:1])


class Walkthrough:
    """Run each command in process, as its command line, and keep a short transcript."""

    def __init__(self, out: Path):
        self.out = out
        self.lines = ['# Every command the walkthrough ran, in order, with paths relative to its output directory.']

    def relative(self, text: str) -> str:
        """Paths from the output directory, and scripts from the directory holding SKILL.md."""
        for base in (self.out, ROOT):
            for prefix in (str(base) + '\\', str(base) + '/'):
                text = text.replace(prefix, '')
        return text.replace(str(self.out), '.').replace('\\', '/')

    def note(self, text: str) -> None:
        self.lines.append('# ' + text)

    def run(self, script: str, *argv: str, result=summary) -> str:
        module = importlib.import_module(script)
        stdout = io.StringIO()
        with patch.object(sys, 'argv', [script + '.py', *argv]), contextlib.redirect_stdout(stdout):
            try:
                code = module.main() or 0
            except SystemExit as exc:
                code = exc.code if isinstance(exc.code, int) else 1
        text = stdout.getvalue()
        self.lines.append('$ python scripts/' + script + '.py ' + ' '.join(shlex.quote(self.relative(a)) for a in argv))
        self.lines.append(f'  exit {code}: ' + self.relative(result(text) if code == 0 else summary(text)))
        if code != 0:
            raise RuntimeError(f'{script}.py failed: {summary(text)}')
        return text


def run(out: Path) -> dict:
    out = out.resolve()
    if out.exists():
        raise ValueError('walkthrough output already exists; choose a new directory')
    out.mkdir(parents=True)
    state = out / 'pack-state.json'
    pm.save_state(state, {'pack_roots': [], 'enabled_packs': [COMMONS], 'resource_providers': {
        name: COMMONS for name in ('service-profiles', 'prompt-writing-guide', 'prompt-dialects')}})
    runtime = ['--state-file', str(state), '--cache-dir', str(out / 'cache'), '--managed-root', str(out / 'managed')]
    catalog_cli.configure_pack_runtime(pm.default_settings(state_file=state, cache_dir=out / 'cache',
                                                           managed_root=out / 'managed'))
    attempts = []

    def refuse(*args, **kwargs):
        attempts.append(args[1:] or args)
        raise OSError('the offline walkthrough makes no network connection')

    walk = Walkthrough(out)
    root = out / 'project'
    package = root / 'generation-package.json'
    preview = out / 'preview.json'
    # The reading is recorded in this project's own ledger, whatever ledger the caller names.
    environment = {key: value for key, value in os.environ.items() if key != 'CPB_READS_LEDGER'}
    try:
        with patch.object(socket.socket, 'connect', refuse), patch.object(socket, 'create_connection', refuse), \
                patch.dict(os.environ, environment, clear=True):
            # A studio with one character, an open work task, and a complete read of the generation route.
            walk.run('studio', 'init', '--out', str(root), '--studio-id', 'offline-walkthrough',
                     '--title', 'Offline walkthrough')
            walk.run('studio', 'character', 'add', 'C01', '--studio', str(root))
            walk.run('work_ledger', '--studio', str(root), 'begin', '--goal', 'Preview one portrait request',
                     '--step', 'prepare', '--step', 'package', '--step', 'preview')
            task_id = c.load(root / 'work/current.json')['task_id']
            reading = walk.run('execution_routes', 'read', 'generation', '--root', str(root), *runtime,
                               result=lambda text: f'{len(text)} characters read; ' + text.strip().splitlines()[-1])
            record = reading.strip().splitlines()[-1].removeprefix('reading-record: ')
            # The authored task, its prompt and the principal's authority.
            write(root / 'prompt.txt', PROMPT + '\n')
            write(root / 'authority-basis.txt', 'Synthetic walkthrough declaration, not a real user instruction.\n')
            write(root / 'authority.json', {
                'task_id': task_id, 'issuer': SYNTHETIC,
                'evidence': {'path': 'authority-basis.txt', 'locator': 'whole'}, 'stop_conditions': [],
                'grants': [{'id': 'walkthrough', 'actor': SYNTHETIC, 'mode': 'direct', 'operations': ['direction', 'submit'],
                            'targets': ['purpose', 'delivery'],
                            'limits': {'uses': 1, 'outputs': 1, 'cost': {'currency': 'USD', 'amount': '0'}},
                            'protected_criteria': [], 'expires_at': None, 'request_scope': None,
                            'submission_validation_modes': ['target-schema']}]})
            write(root / 'task.json', {
                'task_id': task_id, 'production_id': pm.generate_uuid7(), 'route': 'generation', 'features': [],
                'sources': [], 'world_views': [], 'authority': 'authority.json', 'route_reading': record,
                'artifact': 'image', 'execution': 'dispatcher',
                'delivery': {'path': 'prompt.txt', 'transport': 'authored-rendition',
                             'translation_notes': 'The prompt is sent exactly as written.'},
                'criteria': [{'id': 'framing', 'strength': 'hard', 'evidence': 'image',
                              'text': 'One woman in a green raincoat, waist-up, at a bus stop in light rain.'}],
                'direction': {'purpose': 'Preview the request for one one-off portrait.',
                              'intended_effect': 'A quiet, readable rainy-day portrait.',
                              'basis': [], 'decisions': [], 'action_slice': None, 'limitations': [SYNTHETIC]}})
            walk.note('wrote project/prompt.txt, project/authority.json and project/task.json (synthetic, not consent)')
            prepared = walk.run('production_workflow', 'prepare', '--root', str(root), '--task', 'task.json')
            run_id = json.loads(prepared)['run']
            # Approved plot, settled retrieval and the drafted production specification.
            write(out / 'plot.json', PLOT)
            write(out / 'lookups.json', {'artifact_type': 'prompt-retrieval-record', 'pack_state': 'offline-walkthrough',
                'elements': [{'element': 'rainy bus stop portrait', 'queries': ['woman raincoat bus stop rain'],
                              'inspected_records': [], 'outcome': 'composed', 'composed_wording': PROMPT,
                              'reason': SYNTHETIC}]})
            walk.note('wrote plot.json (approved by a synthetic principal) and lookups.json')
            walk.run('prompt_retrieval', str(out / 'lookups.json'), '--settle', '--prompt-file', str(root / 'prompt.txt'),
                     '--plot-file', str(out / 'plot.json'), '--out', str(out / 'retrieval.json'))
            drafted = walk.run('production_spec', 'draft', str(out / 'production-spec.json'), '--model', MODEL,
                               '--brief', BRIEF, '--kind', 'human', '--framing', 'waist-up', '--continuity', 'one-off')
            builder = ['--model', MODEL, '--prompt-file', str(root / 'prompt.txt'), '--plot-file', str(out / 'plot.json'),
                       '--retrieval-record-file', str(out / 'retrieval.json'), *json.loads(drafted)['build_with'],
                       '--parameters', json.dumps({'width': 832, 'height': 1248}),
                       '--production-root', str(root), '--out', str(package), *runtime]
            write(out / 'builder-arguments.json', builder)
            walk.run('build_generation_payload', *builder, result=lambda text: 'status: {status}; '
                     'generation_input_sha256: {generation_input_sha256}'.format(**json.loads(text)))
            walk.run('dispatch', str(package), '--studio', str(root), '--character', 'C01', '--slot', 'explore',
                     '--preview-out', str(preview), *runtime)
    finally:
        write(out / 'transcript.txt', '\n'.join(walk.lines) + '\n')
        catalog_cli.configure_pack_runtime(None)
    built = c.load(package)
    shown = c.load(preview)
    report = {'ok': True, 'offline_fixture': True, 'external_requests': len(attempts), 'sent': False,
              'production_run': run_id, 'package_run': built['production_binding']['run'],
              'request_validation': {'mode': built['request_validation']['mode'],
                                     'contract': built['request_validation']['contract']['path']},
              'request': shown['request_contract']['request'], 'validation': shown['validation'],
              'iterations': len(studio.read_iterations(studio.character_dir(root, 'C01'))),
              'output': str(out), 'note': 'Synthetic reading, authority and approval exercise structure, not real consent.'}
    write(out / 'walkthrough-report.json', report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        report = run(args.out)
    except (ValueError, OSError, RuntimeError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
