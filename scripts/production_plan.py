#!/usr/bin/env python3
"""Validate authored production decisions and compute a bounded consumer view.

There is no emotion-to-gesture mapping or automatic artistic assessment here.
The author supplies decisions, alternatives, reasons and evidence requirements.
"""
from __future__ import annotations

from typing import Any
import execution_contract as c


def strings(value: Any, label: str, *, nonempty: bool = False) -> list[str]:
    if not isinstance(value, list) or (nonempty and not value):
        raise ValueError(f'{label}: a list is required')
    for item in value:
        c.text(item, label)
    if len(set(value)) != len(value):
        raise ValueError(f'{label}: duplicate values')
    return value


def validate(direction: Any, sources: list[dict], criteria: list[dict]) -> None:
    c.exact(direction, {'purpose', 'intended_effect', 'basis', 'decisions',
                        'action_slice', 'limitations'}, 'direction')
    c.text(direction['purpose'], 'purpose')
    c.text(direction['intended_effect'], 'intended effect')
    source_ids = {s['id'] for s in sources}
    applied = {s['id'] for s in sources if s['disposition'] == 'applied'}
    criterion_ids = {x['id'] for x in criteria}
    if set(strings(direction['basis'], 'direction basis')) - applied:
        raise ValueError('direction basis must reference applied task sources')
    strings(direction['limitations'], 'direction limitations')
    decisions = direction['decisions']
    if not isinstance(decisions, list):
        raise ValueError('decisions must be a list (an empty list is valid)')
    ids: set[str] = set()
    for decision in decisions:
        c.exact(decision, {'id', 'question', 'importance', 'basis', 'options',
                          'selected', 'reason', 'criteria', 'depends_on', 'deviations'}, 'decision')
        ident = c.text(decision['id'], 'decision id')
        if ident in ids:
            raise ValueError('duplicate decision id')
        ids.add(ident)
        c.text(decision['question'], 'decision question')
        c.text(decision['reason'], 'selection reason')
        if decision['importance'] not in {'fixed', 'routine', 'material'}:
            raise ValueError('decision importance must be fixed, routine or material')
        if set(strings(decision['basis'], 'decision basis')) - applied:
            raise ValueError('decision cites an unknown or unused source')
        if set(strings(decision['criteria'], 'decision criteria', nonempty=True)) - criterion_ids:
            raise ValueError('decision names an unknown criterion')
        strings(decision['depends_on'], 'decision dependencies')
        options = decision['options']
        if not isinstance(options, list) or not options:
            raise ValueError('a decision must have a selected option')
        if decision['importance'] == 'material' and len(options) < 2:
            raise ValueError('a material choice requires an actual comparison')
        option_ids: set[str] = set()
        for option in options:
            c.exact(option, {'id', 'expression', 'realization', 'tradeoffs'}, 'option')
            key = c.text(option['id'], 'option id')
            if key in option_ids:
                raise ValueError('duplicate option id')
            option_ids.add(key)
            c.text(option['expression'], 'expression')
            strings(option['tradeoffs'], 'tradeoffs', nonempty=decision['importance'] == 'material')
            realization = option['realization']
            c.exact(realization, {'method', 'instructions', 'capability_source', 'limitations'}, 'realization')
            c.text(realization['method'], 'realization method')
            c.text(realization['instructions'], 'realization instructions')
            capability = realization['capability_source']
            if capability is not None and capability not in applied:
                raise ValueError('capability evidence must identify an applied task source')
            strings(realization['limitations'], 'realization limitations')
        if decision['selected'] not in option_ids:
            raise ValueError('selected option does not exist')
        if not isinstance(decision['deviations'], list):
            raise ValueError('deviations must be a list')
        for deviation in decision['deviations']:
            c.exact(deviation, {'source', 'locator', 'scope', 'reason'}, 'intentional deviation')
            if deviation['source'] not in source_ids:
                raise ValueError('deviation must identify the condition it departs from')
            for field in ('locator', 'scope', 'reason'):
                c.text(deviation[field], 'deviation ' + field)
    graph = {d['id']: d['depends_on'] for d in decisions}
    visiting: set[str] = set()
    done: set[str] = set()
    def visit(ident: str) -> None:
        if ident not in graph:
            raise ValueError('unknown decision dependency')
        if ident in visiting:
            raise ValueError('cyclic decision dependency')
        if ident in done:
            return
        visiting.add(ident)
        for predecessor in graph[ident]:
            visit(predecessor)
        visiting.remove(ident)
        done.add(ident)
    for ident in graph:
        visit(ident)
    action = direction['action_slice']
    if action is not None:
        c.exact(action, {'phase', 'before', 'after', 'relations', 'not_verified'}, 'action slice')
        for field in ('phase', 'before', 'after'):
            c.text(action[field], 'action ' + field)
        if not isinstance(action['relations'], list):
            raise ValueError('action relations must be a list')
        for relation in action['relations']:
            c.exact(relation, {'subject', 'relation', 'object', 'note'}, 'action relation')
            for field in relation:
                c.text(relation[field], 'action relation ' + field)
        strings(action['not_verified'], 'action not verified', nonempty=True)


def consumer(direction: dict) -> dict:
    """Only selected realization enters a model-facing view, not the dossier."""
    return {'directives': [
        {'decision': d['id'], 'expression': selected['expression'],
         'method': selected['realization']['method'],
         'instructions': selected['realization']['instructions']}
        for d in direction['decisions']
        for selected in d['options'] if selected['id'] == d['selected']
    ]}


def validate_consumer(value: Any) -> None:
    """A sealed payload cannot grow private fields even if its hash is recomputed."""
    c.exact(value, {'directives'}, 'consumer direction')
    if not isinstance(value['directives'], list):
        raise ValueError('consumer directives must be a list')
    ids = set()
    for directive in value['directives']:
        c.exact(directive, {'decision', 'expression', 'method', 'instructions'}, 'consumer directive')
        for key in directive:
            c.text(directive[key], 'consumer ' + key)
        if directive['decision'] in ids:
            raise ValueError('duplicate consumer decision')
        ids.add(directive['decision'])


def affected(task: dict, changed_sources: set[str], *, all_inputs: bool = False) -> dict:
    """Transitive impact of declared edges; it is not a semantic change detector."""
    decisions = task['direction']['decisions']
    affected_ids = {d['id'] for d in decisions if all_inputs or changed_sources.intersection(d['basis'])
                    or any(o['realization']['capability_source'] in changed_sources for o in d['options'])
                    or any(x['source'] in changed_sources for x in d['deviations'])}
    while True:
        expanded = affected_ids | {d['id'] for d in decisions if affected_ids.intersection(d['depends_on'])}
        if expanded == affected_ids:
            break
        affected_ids = expanded
    checks = {x for d in decisions if d['id'] in affected_ids for x in d['criteria']}
    if all_inputs:
        checks.update(x['id'] for x in task['criteria'])
    return {'decisions': sorted(affected_ids), 'criteria': sorted(checks),
            'purpose': all_inputs or bool(changed_sources.intersection(task['direction']['basis']))}


def direction_targets(task: dict) -> list[str]:
    return sorted(['purpose'] + ['decision:' + d['id'] for d in task['direction']['decisions']])
