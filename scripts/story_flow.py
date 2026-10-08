"""Build a human story-reading flow from the existing story and state records.

Scenes carry the author's purpose, beats, exchanges and consequences. Events
carry their recorded notes, cause and changes. This projection writes no story,
assigns no motivation, and calls no second state resolver.
"""
from __future__ import annotations

from collections import defaultdict
import copy
from pathlib import Path
from typing import Any

import execution_contract as c
from protocol_contract import validate_artifact
from narrative import validate_narrative, content_sha256
from scene_plot import validate_scene_plot

NARRATIVE = 'narrative/narrative.json'
SCENES = 'narrative/scenes'


def rows(value: Any) -> list:
    return value if isinstance(value, list) else []


def text(value: Any) -> str:
    return value if isinstance(value, str) else ''


def objects(value: Any) -> list[dict]:
    return [row for row in rows(value) if isinstance(row, dict)]


def identifier(kind: str, source: str) -> str:
    return 'flow-' + c.content_id({'kind': kind, 'source': source})[:24]


def _source(inputs, path: str) -> dict:
    from story_timeline import _href, _path
    fact = inputs.dependencies.get(path, {})
    return {'path': path, 'sha256': fact.get('sha256'),
            'href': _href(_path(inputs.root, path), inputs.output) if fact.get('status') == 'present' else None}


def _notice(code: str, message: str, *, source: str, node: str | None = None) -> dict:
    return {'code': code, 'severity': 'warning', 'message': message, 'source_path': source,
            **({'flow_node': node} if node else {})}


def read_sources(inputs) -> dict:
    """Read only conventional authoring locations, each file once.

    The list of scene files is an input too: additions, removals and renames
    invalidate the publication. A broken draft stays visible without supplying
    a false scene/state association.
    """
    notices, scenes = [], []
    document, narrative_report = None, None
    try:
        document = inputs.json(NARRATIVE, optional=True)
        if document is not None:
            narrative_report = validate_narrative(document)
            if not narrative_report['ok']:
                notices.append(_notice('FLOW_NARRATIVE_INVALID',
                    '; '.join(narrative_report['errors']), source=NARRATIVE))
            if not isinstance(document, dict):
                document = None
    except (ValueError, OSError, TypeError, KeyError) as exc:
        notices.append(_notice('FLOW_NARRATIVE_UNAVAILABLE', str(exc), source=NARRATIVE))
    valid_narrative = document is not None and narrative_report is not None and narrative_report['ok']
    try:
        scene_paths = inputs.collection(SCENES)
    except (ValueError, OSError) as exc:
        scene_paths = []
        notices.append(_notice('FLOW_SCENE_COLLECTION_UNAVAILABLE', str(exc), source=SCENES))
    for path in scene_paths:
        key = identifier('scene', path)
        entry = {'key': key, 'path': path, 'record': None, 'report': None, 'context': None,
                 'context_source': None, 'messages': [], 'links_usable': False}
        try:
            value = inputs.json(path)
            if not isinstance(value, dict) or value.get('artifact_type') != 'scene-plot':
                # Other declared JSON material beside scenes is not a scene plot.
                continue
            entry['record'] = value
            report = validate_scene_plot(value)
            entry['report'] = report
            if not report['ok']:
                entry['messages'].append('Invalid scene draft: ' + '; '.join(report['errors']))
            else:
                entry['links_usable'] = True
                if valid_narrative:
                    if value['narrative_sha256'] != content_sha256(document):
                        entry['messages'].append('Written against a different narrative revision; review the story source.')
                    for field, collection in [('chapter', 'chapters')]:
                        if value[field] not in {row['id'] for row in document[collection]}:
                            entry['messages'].append('The narrative does not declare chapter ' + value[field] + '.')
                    cast = {row['id'] for row in document['characters']}
                    missing = [who for who in value['characters'] if who not in cast]
                    if missing:
                        entry['messages'].append('Cast not declared by the narrative: ' + ', '.join(missing))
                elif document is None:
                    entry['messages'].append('No narrative document is available; chapter order is not inferred.')
                context = value['setting'].get('scene_context')
                if context:
                    try:
                        snapshot = inputs.json(context)
                        context_report = validate_artifact(snapshot)
                        if not context_report['ok'] or snapshot.get('artifact_type') != 'scene-context-snapshot':
                            raise ValueError('scene_context is not a valid committed scene-context-snapshot')
                        entry['context'] = snapshot
                        entry['context_source'] = _source(inputs, context)
                    except (ValueError, OSError, TypeError, KeyError) as exc:
                        entry['messages'].append('Scene/state link unavailable: ' + str(exc))
        except (ValueError, OSError, KeyError, TypeError) as exc:
            entry['messages'].append('Scene source could not be read: ' + str(exc))
        entry['source'] = _source(inputs, path)
        for message in entry['messages']:
            notices.append(_notice('FLOW_SCENE_REVIEW', message, source=path, node=key))
        scenes.append(entry)
    ids = defaultdict(list)
    for scene in scenes:
        value = scene['record'] or {}
        if text(value.get('scene_id')):
            ids[value['scene_id']].append(scene)
    for ident, group in ids.items():
        if len(group) > 1:
            for scene in group:
                scene['links_usable'] = False
                scene['context'] = None
                message = 'Duplicate scene ID ' + ident + '; no source is chosen as the latest or canonical one.'
                scene['messages'].append(message)
                notices.append(_notice('FLOW_SCENE_ID_AMBIGUOUS', message,
                    source=scene['path'], node=scene['key']))
    return {'narrative': document, 'narrative_report': narrative_report,
            'narrative_source': _source(inputs, NARRATIVE),
            'narrative_usable': valid_narrative, 'scenes': scenes, 'diagnostics': notices}


def _headline(event: dict) -> tuple[str, str]:
    notes = [note for note in rows(event.get('notes')) if isinstance(note, str) and note.strip()]
    if notes:
        return notes[0], 'notes[0]'
    cause = event.get('cause')
    if isinstance(cause, dict) and text(cause.get('reference')):
        return cause['reference'], 'cause.reference (recorded text)'
    return 'Recorded state change', 'display label; no scene description recorded'


def _chapter_nodes(sources: dict) -> tuple[dict, dict]:
    if not sources['narrative_usable']:
        return {}, {}
    narrative = sources['narrative']
    return ({row['id']: row for row in narrative['chapters']},
            {row['id']: row['name'] for row in narrative['characters']})


def build(model: dict, sources: dict) -> dict:
    """Index content and typed links without revalidating the ledger per card."""
    chapters, names = _chapter_nodes(sources)
    nodes, diagnostics = [], list(sources['diagnostics'])
    event_keys, context_events = defaultdict(list), defaultdict(list)
    context_scenes = defaultdict(list)
    state_paths = defaultdict(list)
    path_members = defaultdict(set)
    for card in model['events']:
        event = card['event']
        key = identifier('event', card['anchor'])
        title, basis = _headline(event)
        entities = [row for row in rows(event.get('targets')) if isinstance(row, str)]
        node = {'key': key, 'kind': 'event', 'title': title, 'title_basis': basis,
            'event_anchor': card['anchor'], 'event_id': text(event.get('event_id')),
            'timeline_id': text(event.get('timeline_id')) or None,
            'start_order': event.get('effective_order') if type(event.get('effective_order')) is int else None,
            'end_order': None, 'scene_context_id': text(event.get('scene_context_id')) or None,
            'participants': entities, 'entity_types': card['entity_types'],
            'chapter_id': None, 'source': {'path': model['source_paths']['events'], 'line': card['line'],
                                         'href': model['source_links'].get('events')},
            'scene_keys': [], 'event_keys': [], 'messages': [], 'scene_record': None}
        nodes.append(node)
        if node['event_id']:
            event_keys[node['event_id']].append(key)
        if node['scene_context_id']:
            context_events[(node['timeline_id'], node['scene_context_id'])].append(node)
        for change in objects(event.get('changes')):
            if all(isinstance(change.get(field), str) for field in ('entity_type', 'entity_id', 'path')):
                identity = (node['timeline_id'], change['entity_type'], change['entity_id'], change['path'])
                if key not in path_members[identity]:
                    path_members[identity].add(key)
                    state_paths[identity].append(key)
    event_count = len(nodes)
    chapter_scenes = defaultdict(list)
    for scene in sources['scenes']:
        record, context = scene['record'] or {}, scene['context']
        node = {'key': scene['key'], 'kind': 'scene', 'title': text(record.get('proposition')) or 'Unreadable scene draft',
            'title_basis': 'scene.proposition' if text(record.get('proposition')) else 'unavailable source',
            'scene_id': text(record.get('scene_id')), 'chapter_id': text(record.get('chapter')) or None,
            'scene_order': record.get('order') if type(record.get('order')) is int else None,
            'timeline_id': context['timeline_id'] if context else None,
            'start_order': context['story_order_start'] if context else None,
            'end_order': context['story_order_end'] if context else None,
            'scene_context_id': context['scene_context_id'] if context else None,
            'participants': [who for who in rows(record.get('characters')) if isinstance(who, str)],
            'entity_types': ['character'] if record.get('characters') else [],
            'source': scene['source'], 'context_source': scene['context_source'], 'scene_record': record,
            'report': scene['report'], 'messages': scene['messages'], 'event_keys': [], 'scene_keys': []}
        if context:
            context_scenes[(context['timeline_id'], context['scene_context_id'])].append(node)
        nodes.append(node)
        if scene['links_usable'] and node['chapter_id'] in chapters:
            chapter_scenes[node['chapter_id']].append(node)
    by_key = {node['key']: node for node in nodes}
    for context, scenes in context_scenes.items():
        for scene in scenes:
            for event in context_events.get(context, []):
                # Only exact scene context plus a declared interval binds the records.
                order = event['start_order']
                if order is not None and scene['start_order'] <= order <= scene['end_order']:
                    scene['event_keys'].append(event['key'])
                    event['scene_keys'].append(scene['key'])
    for index, process in enumerate(objects(model['processes'])):
        ident = text(process.get('process_id'))
        notes = [note for note in rows(process.get('notes')) if isinstance(note, str) and note.strip()]
        nodes.append({'key': identifier('process', str(index) + ':' + ident), 'kind': 'process',
            'title': notes[0] if notes else text(process.get('process_type')) or 'Declared process',
            'title_basis': 'process.notes[0]' if notes else 'process.process_type',
            'process_id': ident, 'process_record': process, 'timeline_id': text(process.get('timeline_id')) or None,
            'start_order': process.get('started_order') if type(process.get('started_order')) is int else None,
            'end_order': process.get('effective_until_order'), 'scene_context_id': None,
            'participants': [process['entity_id']] if isinstance(process.get('entity_id'), str) else [],
            'entity_types': [process['entity_type']] if isinstance(process.get('entity_type'), str) else [],
            'chapter_id': None, 'source': {'path': model['source_paths']['processes']},
            'event_keys': [], 'scene_keys': [], 'messages': [], 'scene_record': None})
    # Keep declared chapters with no scene visible. This is a missing source,
    # not a generated scene, an omitted beat, or a structural verdict.
    for chapter in chapters.values():
        if not chapter_scenes[chapter['id']]:
            node = {'key': identifier('chapter', chapter['id']), 'kind': 'chapter',
                'title': chapter['title'], 'title_basis': 'chapter.title', 'chapter_id': chapter['id'],
                'chapter_record': chapter, 'timeline_id': None, 'start_order': None, 'end_order': None,
                'scene_context_id': None, 'participants': [], 'entity_types': [],
                'source': sources['narrative_source'], 'event_keys': [], 'scene_keys': [],
                'scene_record': None, 'messages': ['No serialized scene plot is recorded for this chapter. This is not an invented scene.']}
            nodes.append(node); chapter_scenes[chapter['id']].append(node)
    relations = []
    for card, node in zip(model['events'], nodes[:event_count]):
        event = card['event']
        for old in rows(event.get('supersedes_event_ids')):
            if isinstance(old, str) and len(event_keys.get(old, [])) == 1:
                relations.append({'kind': 'revision', 'source': event_keys[old][0], 'target': node['key'],
                                  'label': 'Replaced as a whole by this later editorial revision'})
        cause = event.get('cause')
        # The cause schema is open. Only an explicitly typed event-ID reference
        # yields an edge; a coincidentally equal prose/reference string does not.
        if isinstance(cause, dict) and cause.get('type') == 'event':
            reference = cause.get('reference')
            targets = event_keys.get(reference, []) if isinstance(reference, str) else []
            if len(targets) == 1 and targets[0] != node['key'] and by_key[targets[0]]['timeline_id'] == node['timeline_id']:
                relations.append({'kind': 'cause', 'source': targets[0], 'target': node['key'],
                                  'label': 'Explicitly recorded cause (not inferred from order)'})
            else:
                message = 'The explicit cause event reference is missing, ambiguous, self-referential or in another timeline.'
                node['messages'].append(message)
                diagnostics.append(_notice('FLOW_CAUSE_UNRESOLVED', message,
                    source=node['source']['path'], node=node['key']))
    by_key = {node['key']: node for node in nodes}
    # Presentation order is not story time. Unknown chapter/order stays in its own track.
    presentation, placed = [], set()
    for chapter in sorted(chapters.values(), key=lambda row: row['number']):
        groups = defaultdict(list)
        for node in chapter_scenes[chapter['id']]:
            groups[node.get('scene_order') or 0].append(node['key']); placed.add(node['key'])
        presentation.append({'key': 'chapter:' + chapter['id'], 'label': chapter['title'],
            'kind': 'presentation', 'chapter_id': chapter['id'], 'record': chapter,
            'groups': [{'position': order, 'keys': sorted(keys)} for order, keys in sorted(groups.items())]})
    other_scenes = [node['key'] for node in nodes if node['kind'] == 'scene' and node['key'] not in placed]
    if other_scenes:
        presentation.append({'key': 'unplaced-scenes', 'label': 'Presentation position not established',
            'kind': 'unplaced', 'groups': [{'position': None, 'keys': other_scenes}]})
    # A scene supplies the human-readable card for its exactly associated events.
    # Unassociated events always remain in a separate chronological track.
    story_tracks = defaultdict(lambda: defaultdict(list))
    unplaced = []
    for node in nodes:
        if node['kind'] == 'chapter' or (node['kind'] == 'event' and node['scene_keys']):
            continue
        if node['timeline_id'] is None or node['start_order'] is None:
            if node['kind'] == 'scene':
                unplaced.append(node['key'])
            continue
        story_tracks[node['timeline_id']][node['start_order']].append(node['key'])
    story = [{'key': 'story:' + timeline, 'label': timeline, 'kind': 'story', 'timeline_id': timeline,
              'groups': [{'position': position, 'keys': keys} for position, keys in sorted(groups.items())]}
             for timeline, groups in sorted(story_tracks.items())]
    if unplaced:
        story.append({'key': 'unplaced-story', 'label': 'Story position not recorded',
            'kind': 'unplaced', 'groups': [{'position': None, 'keys': unplaced}]})
    for track in story:
        remaining = []
        for group in track['groups']:
            keys = [key for key in group['keys'] if by_key[key]['kind'] in {'event', 'process'}]
            if keys:
                remaining.append({'position': group['position'], 'keys': keys})
        if remaining:
            presentation.append({**track, 'key': 'unplaced-in-presentation:' + track['key'],
                'label': track['label'] + ' / records not attached to a scene', 'groups': remaining})
    return {'artifact_type': 'story-reading-flow', 'nodes': nodes, 'story_tracks': story,
        'presentation_tracks': presentation, 'default_order': 'presentation' if chapters else 'story',
        'relations': relations,
        'state_paths': [{'timeline_id': key[0], 'entity_type': key[1], 'entity_id': key[2], 'path': key[3], 'event_keys': values}
                        for key, values in state_paths.items()],
        'names': names, 'narrative': sources['narrative'], 'narrative_report': sources['narrative_report'],
        'narrative_source': sources['narrative_source'], 'diagnostics': diagnostics,
        'semantics': {
            'purpose': 'Human review of story development. No semantic consistency verdict is inferred.',
            'automatic': 'Generated from ordinary narrative, scene, event and process files. No separate diagram or synopsis is authored.',
            'sequence': 'Declared presentation or story position, never implied causation.',
            'scene_links': 'Exact scene-context reference and declared interval, not filenames or similar IDs.',
            'missing_text': 'Missing explanation is displayed, never completed by the projection.',
            'state': 'Declared changes are distinguished from the shared resolver results in the selected view.'}}
