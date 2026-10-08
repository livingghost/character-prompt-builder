"""Located ledger diagnostics and reusable access to the shared temporal resolver.

An inspection compiles the input records once. Displays and validation call this
owner; neither sorts story labels as dates nor invents an event or a state change.
"""
from __future__ import annotations

from collections import defaultdict
import copy
import re
from typing import Any

import temporal_state as temporal
from protocol_contract import canonical_json, sha256_json


class Ledger:
    """One isolated set of authored inputs, indexed for validation and selected views."""
    def __init__(self, base: dict, events: list[dict], processes: list[dict] | None = None) -> None:
        self.base = copy.deepcopy(base)
        self.events = copy.deepcopy(events)
        self.processes = copy.deepcopy(processes if processes is not None else [])
        self.diagnostics: list[dict] = []
        if not isinstance(base, dict):
            self.diagnostics.append({'code': 'WORLD_BASE_INVALID', 'severity': 'error',
                                     'pointer': '/base', 'message': 'world-state-base must be an object'})
        else:
            for bucket in temporal.ENTITY_BUCKETS.values():
                value = base.get(bucket, {})
                if not isinstance(value, dict) or (bucket != 'world' and any(not isinstance(row, dict) for row in value.values())):
                    self.diagnostics.append({'code': 'WORLD_BASE_INVALID', 'severity': 'error',
                        'pointer': '/base/' + bucket, 'message': 'world buckets and their entity states must be objects'})
            try:
                canonical_json(base)
            except (ValueError, TypeError) as exc:
                self.diagnostics.append({'code': 'WORLD_BASE_INVALID', 'severity': 'error', 'pointer': '/base', 'message': str(exc)})
        temporal.validate_temporal_inputs(events=self.events, processes=self.processes, diagnostics=self.diagnostics)
        self.by_id = {e['event_id']: e for e in self.events if isinstance(e, dict) and isinstance(e.get('event_id'), str)} if isinstance(self.events, list) else {}
        self.by_timeline: dict[str, list[dict]] = defaultdict(list)
        self.processes_by_timeline: dict[str, list[dict]] = defaultdict(list)
        self.revisions: dict[str, list[str]] = defaultdict(list)
        if not self.diagnostics:
            for event in self.events:
                self.by_timeline[event['timeline_id']].append(event)
                for prior in event.get('supersedes_event_ids', []):
                    self.revisions[prior].append(event['event_id'])
            for rows in self.by_timeline.values():
                rows.sort(key=lambda e: (e['effective_order'], e['event_id']))
            for process in self.processes:
                self.processes_by_timeline[process['timeline_id']].append(process)
        self.timelines = sorted(set(self.by_timeline) | set(self.processes_by_timeline))

    def resolve(self, *, timeline_id: str, story_order: int, story_time: str,
                scene_context_id: str | None, view_id: str = 'selected', explain: bool = True) -> dict:
        if self.diagnostics:
            return {'ok': False, 'snapshot': None, 'diagnostics': copy.deepcopy(self.diagnostics), 'trace': []}
        if not isinstance(timeline_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]*', timeline_id):
            raise ValueError('a view needs an explicit timeline identifier')
        if type(story_order) is not int or not isinstance(story_time, str) or not story_time:
            raise ValueError('a view needs an integer story order and a nonempty story-time label')
        if scene_context_id is not None and (not isinstance(scene_context_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]*', scene_context_id)):
            raise ValueError('scene context must be null or a declared identifier')
        query = {'timeline_id': timeline_id, 'story_order': story_order, 'story_time': story_time, 'scene_context_id': scene_context_id}
        trace: list[dict] = []
        try:
            # Reference validation uses the complete ledger; replay needs only this timeline.
            snapshot = temporal._resolve_world_validated(base_state=self.base,
                events=self.by_timeline.get(timeline_id, []), processes=self.processes_by_timeline.get(timeline_id, []),
                timeline_id=timeline_id, story_order=story_order, story_time=story_time,
                snapshot_id='TIMELINE-' + sha256_json({'view_id': view_id, **query}),
                scene_context_id=scene_context_id, trace=trace if explain else None)
        except temporal.TemporalConflictError as exc:
            return {'ok': False, 'query': query, 'snapshot': None, 'trace': [], 'diagnostics': [
                {'code': 'TEMPORAL_CONFLICT', 'severity': 'error', 'message': str(exc),
                 'timeline_id': timeline_id, 'story_order': exc.order, 'scene_context_id': scene_context_id,
                 'event_ids': sorted({x[k] for x in exc.conflicts for k in ('left', 'right') if x[k] in self.by_id}),
                 'conflicts': exc.conflicts, 'paths': sorted({p for x in exc.conflicts for p in x.get('paths', [])})}]}
        except (ValueError, TypeError, KeyError, IndexError) as exc:
            return {'ok': False, 'query': query, 'snapshot': None, 'trace': [], 'diagnostics': [
                {'code': 'STATE_RESOLUTION_FAILED', 'severity': 'error', 'message': str(exc), **query}]}
        return {'ok': True, 'query': query, 'snapshot': snapshot, 'trace': trace,
                'diagnostics': [], 'event_status': self.event_status(query) if explain else {}}

    def event_status(self, query: dict) -> dict[str, dict]:
        """Explain membership in the resolver replay, not whether an event 'really happened'."""
        rows = self.by_timeline.get(query['timeline_id'], [])
        active = {e['event_id'] for e in temporal._approved_events_as_of(rows,
                    timeline_id=query['timeline_id'], story_order=query['story_order'])}
        output = {}
        for event in rows:
            code = 'applied-in-replay'
            if event['canon_status'] != 'approved':
                code = 'recorded-' + event['canon_status']
            elif event['effective_order'] > query['story_order']:
                code = 'after-selected-order'
            elif event['event_id'] not in active:
                code = 'revised-at-selected-order'
            else:
                flags = [temporal._change_is_active(change, event, story_order=query['story_order'],
                        scene_context_id=query['scene_context_id'], active_event_ids=active, event_by_id=self.by_id)
                         for change in event['changes'] if not temporal._is_lifecycle_change(change)]
                if flags and not any(flags):
                    if all(c.get('persistence') == 'scene-local' for c in event['changes']):
                        code = 'other-scene-only'
                    else:
                        code = 'expired-or-cleared'
                elif flags and not all(flags):
                    code = 'partly-applied-in-replay'
            output[event['event_id']] = {'status': code,
                'revised_by': sorted(e for e in self.revisions[event['event_id']] if e in active)}
        return output

    def declared_coordinates(self) -> dict[str, set[int]]:
        """Event positions and authored process offsets; no interpolation or date parsing."""
        result: dict[str, set[int]] = defaultdict(set)
        restarts: dict[str, list[int]] = defaultdict(list)
        for event in self.events:
            result[event['timeline_id']].add(event['effective_order'])
            for change in event['changes']:
                if change['operation'] == 'restart-process':
                    restarts[change['process_id']].append(event['effective_order'])
        for process in self.processes:
            for start in [process['started_order'], *restarts[process['process_id']]]:
                for milestone in process['milestones']:
                    at = start + milestone['offset']
                    until = process.get('effective_until_order')
                    if until is None or at < until:
                        result[process['timeline_id']].add(at)
        return result

    def default_views(self) -> list[dict]:
        if self.diagnostics:
            return []
        return [{'view_id': 'latest-' + sha256_json(timeline)[:16],
                 'label': timeline + ': last declared coordinate, shared state (no scene)',
                 'timeline_id': timeline, 'story_order': max(orders),
                 'story_time': 'order:' + str(max(orders)), 'scene_context_id': None,
                 'time_basis': 'generated order label; not an authored story_time'}
                for timeline, orders in sorted(self.declared_coordinates().items()) if orders]

    def audit(self) -> dict:
        """Inspect structure and relevant replay boundaries, without demanding sequential IDs.

        Common prefixes are replayed once per distinct query, never once per card.
        A failed earlier operation blocks later queries; those results are not states.
        """
        if self.diagnostics:
            return {'ok': False, 'diagnostics': copy.deepcopy(self.diagnostics),
                    'coverage': {'structure_valid': False, 'queries_checked': 0, 'unresolved_queries': 0}}
        queries: set[tuple[str, int, str | None]] = set()
        for timeline, positions in self.declared_coordinates().items():
            if positions:
                queries.add((timeline, max(positions), None))
        groups: dict[tuple[str, int, str, str], dict[str, set[str | None]]] = defaultdict(dict)
        contexts: dict[tuple[str, str], int] = {}
        restarts: dict[str, list[int]] = defaultdict(list)
        for event in self.events:
            if event['canon_status'] != 'approved':
                continue
            scene = event.get('scene_context_id')
            if scene is not None:
                key = (event['timeline_id'], scene)
                contexts[key] = max(contexts.get(key, event['effective_order']), event['effective_order'])
            if event['preconditions'] or event.get('supersedes_event_ids') or any(
                    c.get('effective_until_order') is not None or c.get('clear_event_id') for c in event['changes']):
                queries.add((event['timeline_id'], event['effective_order'], scene))
            for change in event['changes']:
                # The world entity is one aggregate bucket, not one bucket per arbitrary ID.
                owner = 'world' if change['entity_type'] == 'world' else change['entity_id']
                key = (event['timeline_id'], event['effective_order'], change['entity_type'], owner)
                scopes = groups[key].setdefault('event:' + event['event_id'], set())
                scopes.add(scene if change.get('persistence') == 'scene-local' else None)
                if change['operation'] == 'restart-process':
                    restarts[change['process_id']].append(event['effective_order'])
            for condition in event['preconditions']:
                key = (event['timeline_id'], event['effective_order'], condition['entity_type'],
                       'world' if condition['entity_type'] == 'world' else condition['entity_id'])
                groups[key].setdefault('event:' + event['event_id'], set()).add(scene)
        for process in self.processes:
            if process['canon_status'] != 'approved':
                continue
            owner = 'world' if process['entity_type'] == 'world' else process['entity_id']
            for start in [process['started_order'], *restarts[process['process_id']]]:
                for milestone in process['milestones']:
                    at = start + milestone['offset']
                    if process.get('effective_until_order') is not None and at >= process['effective_until_order']:
                        continue
                    groups[(process['timeline_id'], at, process['entity_type'], owner)].setdefault('process:' + process['process_id'], set()).add(None)
        for (timeline, order, _, _), owners in groups.items():
            if len(owners) > 1:
                for scope in {s for values in owners.values() for s in values}:
                    queries.add((timeline, order, scope))
        for (timeline, scene), order in contexts.items():
            queries.add((timeline, order, scene))
        unique: dict[str, dict] = {}
        unresolved = 0
        for timeline, order, scene in sorted(queries, key=lambda q: (q[0], q[1], q[2] or '')):
            result = self.resolve(timeline_id=timeline, story_order=order, story_time='order:' + str(order),
                                  scene_context_id=scene, explain=False)
            if not result['ok']:
                unresolved += 1
                for issue in result['diagnostics']:
                    key = canonical_json(issue)
                    if key not in unique:
                        unique[key] = issue
        return {'ok': not unique, 'diagnostics': list(unique.values()), 'coverage': {
            'structure_valid': True, 'queries_checked': len(queries), 'unresolved_queries': unresolved,
            'scope': 'last declared coordinate, scene endpoints, simultaneous entity operations, preconditions, revisions and temporary boundaries',
            'limits': 'A failed earlier operation blocks that query; no state is claimed for it. Labels and narrative disclosure are not compared as dates.'}}


def inspect_ledger(base: dict, events: list[dict], processes: list[dict] | None = None) -> dict:
    ledger = Ledger(base, events, processes)
    result = ledger.audit()
    return {'artifact_type': 'state-ledger-inspection', **result,
            'event_count': len(events) if isinstance(events, list) else None,
            'process_count': len(processes or []),
            'timelines': ledger.timelines, 'input_sha256': sha256_json({'base': base, 'events': events, 'processes': processes or []})}
