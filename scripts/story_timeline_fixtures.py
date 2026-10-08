"""Authored synthetic timelines for tests and the executable example only."""
from __future__ import annotations
import copy
from pathlib import Path
import execution_contract as c


def event(identifier='E1', order=10, value='apprentice', *, path='/social_role_state/occupation',
          entity='C01', kind='character', scene=None, timeline='main', status='approved',
          supersedes=None, operation='set', persistence=None) -> dict:
    row = {'artifact_type': 'state-event', 'event_id': identifier, 'timeline_id': timeline,
           'event_scope': 'editorial-revision' if supersedes else 'social-role-state',
           'targets': [entity], 'effective_order': order, 'effective_from': 'story:' + str(order),
           'recorded_at': '2000-01-01T00:00:00Z', 'disclosed_at': None,
           'occurrence': 'editorial' if supersedes else 'offscreen', 'canon_status': status,
           'atomic': False, 'cause': {'type': 'synthetic-authored-event', 'reference': 'fixture-decision'},
           'preconditions': [], 'changes': [{'entity_type': kind, 'entity_id': entity, 'path': path,
               'operation': operation, 'value': value,
               'persistence': persistence or ('scene-local' if scene else 'persistent-until-superseded')}],
           'evidence': [{'source_id': 'fixture-author', 'locator': 'whole', 'basis': 'Synthetic test decision, not user consent.'}],
           'supersedes_event_ids': supersedes or [], 'notes': []}
    if scene is not None:
        row['scene_context_id'] = scene
    return row


def process(identifier='P1', *, order=10, timeline='main', path='/physical_state/strength',
            milestones=None, policy='fixed') -> dict:
    return {'artifact_type': 'state-process', 'process_id': identifier, 'timeline_id': timeline,
            'entity_type': 'character', 'entity_id': 'C01', 'path': path,
            'process_type': 'authored-fixture-progress', 'started_order': order,
            'effective_until_order': None, 'milestones': milestones or [{'offset': 0, 'state': 0}, {'offset': 5, 'state': 10}],
            'interruption_policy': policy, 'canon_status': 'approved',
            'evidence': [{'source_id': 'fixture-author', 'locator': 'whole', 'basis': 'Synthetic process fixture.'}], 'notes': []}


def view(identifier, order, *, scene=None, timeline='main') -> dict:
    return {'view_id': identifier, 'label': identifier, 'timeline_id': timeline,
            'story_order': order, 'story_time': 'chapter:' + str(order), 'scene_context_id': scene}


def setup(root: Path, *, events=None, processes=None, views=None, create_studio=True) -> dict:
    if create_studio:
        import studio
        studio.init(root, 'timeline-fixture', 'Synthetic story timeline')
    else:
        root.mkdir(parents=True, exist_ok=True)
    (root / 'state').mkdir(exist_ok=True)
    base = {'characters': {'C01': {'social_role_state': {'occupation': 'unassigned'},
                                  'physical_state': {'strength': 0}}},
            'relationships': {}, 'environments': {}, 'props': {}, 'world': {}}
    c.atomic_write_json(root / 'state/world-state-base.json', base)
    rows = events if events is not None else [event('E1', 1), event('E2', 20, 'craftsperson')]
    write_events(root, rows)
    (root / 'decision.txt').write_text('Synthetic authored test evidence. Not a real approval.\n', encoding='utf-8')
    config = {'artifact_type': 'story-timeline-view', 'base_state': 'state/world-state-base.json',
              'events': 'state/events.jsonl', 'processes': 'state/processes.json' if processes is not None else None,
              'views': views if views is not None else [view('earlier', 1), view('later', 20)],
              'scene_artwork': [], 'evidence_sources': [{'source_id': 'fixture-author', 'path': 'decision.txt'}]}
    c.atomic_write_json(root / 'state/timeline-view.json', config)
    if processes is not None:
        c.atomic_write_json(root / 'state/processes.json', processes)
    return {'base': base, 'events': rows, 'processes': processes or [], 'config': config}


def write_events(root: Path, rows: list[dict]) -> None:
    import json
    c.atomic(root / 'state/events.jsonl', ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows).encode('utf-8'), replace=True)
