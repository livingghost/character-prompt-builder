#!/usr/bin/env python3
"""Walk one idea to a dispatch preview offline, never a production approval.

python examples/feature-walkthrough/run.py --out /tmp/cpb-walkthrough

The walkthrough uses the bundled commons pack in a new pack state under --out.
It prepares a production run, packages the prompt for grok-imagine-image-2.0
and prints the exact Runware request. It sends nothing and uses no credential;
any network connection attempt fails the run. Existing output is never replaced.

The same path as commands, from a directory holding the authored files:

  python scripts/studio.py init --out PROJECT --studio-id ID --title TITLE
  python scripts/work_ledger.py --studio PROJECT begin --goal GOAL --step STEP
  python scripts/execution_routes.py read generation --root PROJECT
  python scripts/production_workflow.py prepare --root PROJECT --task task.json
  python scripts/prompt_retrieval.py lookups.json --settle --prompt-file prompt.txt --plot-file plot.json --out retrieval.json
  python scripts/build_generation_payload.py --model grok-imagine-image-2.0 --prompt-file prompt.txt
      --plot-file plot.json --retrieval-record-file retrieval.json --production-spec-file production-spec.json
      --continuity C01=one-off --parameters '{"width":832,"height":1248}' --production-root PROJECT
      --out PROJECT/generation-package.json
  python scripts/dispatch.py PROJECT/generation-package.json --studio PROJECT --character C01 --slot explore
"""
from __future__ import annotations
import argparse
import contextlib
import copy
import io
import json
import socket
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import catalog_cli
import execution_contract as c
import pack_manager as pm
import production_workflow
import route_reading
import studio
import work_ledger
from build_generation_payload import main as build_main
from dispatch import main as dispatch_main
from generation_payload_smoke_test import APPROVED_PLOT, _production_spec, _stateless_lineage
from prompt_retrieval import main as retrieval_main

MODEL = 'grok-imagine-image-2.0'
COMMONS = c.load(ROOT / 'packs/commons/pack.json')['pack_id']
SYNTHETIC = 'OFFLINE WALKTHROUGH FIXTURE - NOT REAL USER CONSENT'
PROMPT = ('A poised gray wolf character stands centred against a plain ground, seen knee-up at eye height '
          'in quiet studio light, the declared proportions kept exact.')


def applications(route: str) -> dict:
    """Quote one paragraph of every routed document: synthetic, not a real reading."""
    manifest, bodies = route_reading.capture(route)
    always = set(c.load(ROOT / 'config/execution-routes.json')['always_read'])
    result = {'applied': [], 'resource_applied': []}
    for meta, raw in bodies:
        if meta['kind'] == 'document' and meta['path'] not in always:
            quote = next(b for b in route_reading.prose_blocks(raw.decode('utf-8')) if len(b.split()) >= 12)
            result['applied'].append({'path': meta['path'], 'quote': quote, 'why': SYNTHETIC})
        elif meta['kind'] == 'resource' and meta['resource'] == 'prompt-writing-guide':
            guide = c.decode(raw)
            i, j, rule = next((i, j, rule) for i, section in enumerate(guide['sections']) if not section.get('dialects')
                              for j, rule in enumerate(section['rules']) if isinstance(rule, str) and rule.strip())
            result['resource_applied'].append({'resource': 'prompt-writing-guide', 'pointer': f'/sections/{i}/rules/{j}',
                                               'quote': rule, 'why': SYNTHETIC})
    return result


def write(path: Path, value) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    path.write_text(text, encoding='utf-8', newline='\n')
    return path


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

    transcript = io.StringIO()
    try:
        with patch.object(socket.socket, 'connect', refuse), patch.object(socket, 'create_connection', refuse), \
                contextlib.redirect_stdout(transcript):
            # A studio, an open work task, and a complete read of the generation route.
            root = studio.init(out / 'project', 'offline-walkthrough', 'Offline walkthrough')
            studio.add_character(root, 'C01', '')
            opened = work_ledger.begin(root, 'Preview one wolf portrait', ['prepare', 'package', 'preview'])
            issued = route_reading.issue('generation', project=root, stream=transcript)
            write(root / 'route-reading.json', route_reading.build_record(issued, applications('generation'), project=root))
            # The authored task, its prompt and the principal's authority.
            write(root / 'prompt.txt', PROMPT + '\n')
            write(root / 'authority-basis.txt', 'Synthetic walkthrough declaration, not a real user instruction.\n')
            write(root / 'authority.json', {
                'task_id': opened['task_id'], 'issuer': SYNTHETIC,
                'evidence': {'path': 'authority-basis.txt', 'locator': 'whole'}, 'stop_conditions': [],
                'grants': [{'id': 'walkthrough', 'actor': SYNTHETIC, 'mode': 'direct', 'operations': ['direction', 'submit'],
                            'targets': ['purpose', 'delivery'],
                            'limits': {'uses': 1, 'outputs': 1, 'cost': {'currency': 'USD', 'amount': '0'}},
                            'protected_criteria': [], 'expires_at': None, 'request_scope': None,
                            'submission_validation_modes': ['target-schema']}]})
            write(root / 'task.json', {
                'task_id': opened['task_id'], 'production_id': pm.generate_uuid7(), 'route': 'generation', 'features': [],
                'sources': [], 'world_views': [], 'authority': 'authority.json', 'route_reading': 'route-reading.json',
                'artifact': 'image', 'execution': 'dispatcher',
                'delivery': {'path': 'prompt.txt', 'transport': 'authored-rendition',
                             'translation_notes': 'The prompt is sent exactly as written.'},
                'criteria': [{'id': 'framing', 'strength': 'hard', 'evidence': 'image',
                              'text': 'One wolf character stands centred, knee-up, against a plain ground.'}],
                'direction': {'purpose': 'Preview the request for one exploratory portrait.',
                              'intended_effect': 'A calm, readable first look at the character.',
                              'basis': [], 'decisions': [], 'action_slice': None, 'limitations': [SYNTHETIC]}})
            run_id = production_workflow.prepare(root, 'task.json')['run']
            # Approved plot, settled retrieval and the production specification.
            plot = copy.deepcopy(APPROVED_PLOT)
            plot['approved']['by'] = SYNTHETIC
            write(out / 'plot.json', plot)
            write(out / 'lookups.json', {'artifact_type': 'prompt-retrieval-record', 'pack_state': 'offline-walkthrough',
                'elements': [{'element': 'wolf portrait', 'queries': ['wolf portrait studio light'], 'inspected_records': [],
                              'outcome': 'composed', 'composed_wording': PROMPT, 'reason': SYNTHETIC}]})
            retrieval_main([str(out / 'lookups.json'), '--settle', '--prompt-file', str(root / 'prompt.txt'),
                            '--plot-file', str(out / 'plot.json'), '--out', str(out / 'retrieval.json')])
            write(out / 'production-spec.json', _production_spec(MODEL, _stateless_lineage()))
            package = root / 'generation-package.json'
            builder = ['--model', MODEL, '--prompt-file', str(root / 'prompt.txt'), '--plot-file', str(out / 'plot.json'),
                       '--retrieval-record-file', str(out / 'retrieval.json'),
                       '--production-spec-file', str(out / 'production-spec.json'), '--continuity', 'C01=one-off',
                       '--parameters', json.dumps({'width': 832, 'height': 1248}),
                       '--production-root', str(root), '--out', str(package), *runtime]
            write(out / 'builder-arguments.json', builder)
            if build_main(builder) != 0:
                raise RuntimeError('the builder refused the package')
            preview = out / 'preview.json'
            if dispatch_main([str(package), '--studio', str(root), '--character', 'C01', '--slot', 'explore',
                              '--preview-out', str(preview), *runtime]) != 0:
                raise RuntimeError('the dispatcher refused the preview')
    finally:
        write(out / 'transcript.txt', transcript.getvalue())
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
