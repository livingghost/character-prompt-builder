#!/usr/bin/env python3
"""Resolve example state, exchange its artifact and verify shot bindings."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'scripts'))
from io_budget import environment_seconds
import protocol_contract as contract
import temporal_state


def exercise(out: Path) -> dict:
    out = out.absolute()
    if out.exists():
        raise ValueError('Use a new output directory; existing work is not overwritten')
    out.mkdir(parents=True)
    log = []
    env = {key: value for key, value in os.environ.items() if key != 'PYTHONPATH'}
    env['PYTHONDONTWRITEBYTECODE'] = '1'

    def call(script: str, *args: object) -> dict:
        command = [sys.executable, str(ROOT / 'scripts' / script), *map(str, args)]
        p = subprocess.run(command, cwd=out, env=env, capture_output=True, text=True, encoding="utf-8", timeout=environment_seconds("EXAMPLE_COMMAND_TIMEOUT_SECONDS"))
        log.append({'argv': command, 'returncode': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr})
        if p.returncode:
            raise ValueError(p.stdout + p.stderr)
        return json.loads(p.stdout)

    installed = call('protocol_exchange.py', 'check-installed')
    # No character, emotional arc, conflict or change is needed for a valid state.
    snapshot = temporal_state.resolve_world(
        base_state={'environments': {'room': {'light': 'dim'}}}, events=[], processes=[],
        timeline_id='main', story_order=0, story_time='opening', snapshot_id='room-opening',
        scene_context_id='room',
    )
    (out / 'snapshot.json').write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    call('protocol_exchange.py', 'inspect', '--root', out, '--artifact', 'snapshot.json')
    exported = call('protocol_exchange.py', 'export', '--root', out, '--artifact', 'snapshot.json', '--out', 'outgoing')
    (out / 'receiver').mkdir()
    shutil.copytree(out / 'outgoing', out / 'receiver' / 'incoming')
    received = call('protocol_exchange.py', 'verify', '--root', out / 'receiver', '--bundle', 'incoming')
    if exported['artifact_sha256'] != received['artifact_sha256']:
        raise ValueError('transport changed the artifact')

    # A separately declared synthetic scene proves the full inter-artifact links.
    scene = HERE / 'scene'
    request_path = sorted((scene / 'generated/shot-requests').glob('*.json'))[0]
    request = contract.load_json(request_path)
    args = [request_path, '--require-complete', '--scene-context', scene / 'generated/scene-context-snapshot.json',
            '--camera-spec', scene / 'generated/shots' / (request['shot_id'] + '.json'),
            '--shot-projection', scene / 'generated/shot-projections' / (request['shot_id'] + '.json')]
    for cid in request['identity_contract_sha256_by_character']:
        args += ['--species-profile', f'{cid}={scene / "source" / ("species-morphology-" + cid + ".json")}',
                 '--individual-morphology', f'{cid}={scene / "source" / ("individual-morphology-" + cid + ".json")}',
                 '--identity', f'{cid}={scene / "source" / ("character-identity-" + cid + ".json")}',
                 '--state', f'{cid}={scene / "generated" / ("character-state-snapshot-" + cid + ".json")}']
    linked = call('shot_request.py', *args)
    if not linked['complete']:
        raise ValueError('the worked shot is not completely bound')
    result = {'ok': True, 'synthetic': True, 'commands': len(log),
              'contract_set_sha256': installed['contract_set_sha256'],
              'transport_verified': True, 'complete_shot_binding': True,
              'canonical_adoption': False, 'referenced_media_verified': False, 'model_calls': 0}
    (out / 'command-log.json').write_text(json.dumps(log, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    try:
        report = exercise(args.out)
    except (ValueError, OSError, KeyError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)})); raise SystemExit(1)
    print(json.dumps(report, indent=2))
