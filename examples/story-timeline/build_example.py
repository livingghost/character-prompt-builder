#!/usr/bin/env python3
"""Write a synthetic story Studio and read-only timeline to a fresh directory."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import story_timeline as timeline
from story_timeline_fixtures import setup, event, process, view


def build(out: Path) -> dict:
    rows = [event('E-arrival', 1, 'apprentice'), event('E-qualified', 20, 'craftsperson'),
            event('E-coat', 20, 'work coat', path='/appearance_state/coat', scene='SC-workshop'),
            event('E-title-correction', 30, 'senior craftsperson', supersedes=['E-qualified'])]
    rows[0]['recorded_at'] = '2000-01-01T08:00:00Z'
    rows[1]['recorded_at'] = '2000-01-01T08:05:00Z'
    rows[2]['recorded_at'] = '2000-01-01T08:06:00Z'
    rows[3]['recorded_at'] = '2000-01-01T09:00:00Z'
    rows[3]['disclosed_at'] = 'chapter:4; an authored disclosure label'
    data = setup(out, events=rows, processes=[process()], views=[view('arrival',1),
        view('workshop',20,scene='SC-workshop'),view('outside-workshop',20,scene='SC-road'),view('revised-title',30)])
    result = timeline.refresh(out)
    if not result['ok'] or not result['ledger_ok']:
        raise ValueError(json.dumps(result))
    return {'ok': True, 'synthetic': True, 'studio': str(out), 'view': str(out / timeline.OUTPUT),
            'events': len(data['events']), 'views': len(data['config']['views'])}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True, help='new synthetic Studio directory')
    args = parser.parse_args()
    print(json.dumps(build(args.out.resolve()), indent=2))
    return 0


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
