#!/usr/bin/env python3
"""Validate selected production choices and their independent source allowances.

The consumer receives the actual chosen expression and realization. Alternative
works belong to authoring candidates; their number is not evidence of judgment.
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


def validate(direction: Any, sources: list[dict], criteria: list[dict], *, task_id: str | None = None) -> None:
    c.exact(direction, {'purpose', 'intended_effect', 'basis', 'decisions', 'source_allowances',
                        'action_slice', 'limitations'} |
            ({'image_format'} if isinstance(direction, dict) and 'image_format' in direction else set()), 'direction')
    if direction.get('image_format', 'single-still') not in {'single-still', 'multi-panel'}:
        raise ValueError('image_format must be single-still or multi-panel')
    c.text(direction['purpose'], 'purpose')
    c.text(direction['intended_effect'], 'intended effect')
    source_ids = {s['id'] for s in sources}
    applied = {s['id'] for s in sources if s['disposition'] == 'applied'}
    criterion_ids = {x['id'] for x in criteria}
    invalid_basis = set(strings(direction['basis'], 'direction basis')) - applied
    if invalid_basis:
        from production_diagnostics import ProductionError
        raise ProductionError('INPUT_CONSISTENCY_ERROR',
            'Direction basis names sources that are not applied to this task: ' + ', '.join(sorted(invalid_basis)) + '.',
            phase='task-contract', pointer='$.direction.basis',
            invalid_sources=sorted(invalid_basis), available_sources=sorted(applied),
            required_action='Edit direction.basis to cite the applicable IDs in available_sources, or apply '
                            'the intended source to the task first. The commission itself remains the request; '
                            'its request identifier is not an applied source ID.')
    strings(direction['limitations'], 'direction limitations')
    decisions = direction['decisions']
    if not isinstance(decisions, list):
        raise ValueError('decisions must be a list (an empty list is valid)')
    ids: set[str] = set()
    for index, decision in enumerate(decisions):
        c.exact(decision, {'id', 'basis', 'expression', 'realization', 'criteria', 'depends_on', 'deviations'} |
                          ({key for key in ('note', 'representation') if key in decision}
                           if isinstance(decision, dict) else set()),
                'decision')
        ident = c.text(decision['id'], 'decision id')
        if ident in ids:
            raise ValueError('duplicate decision id')
        ids.add(ident)
        c.text(decision['expression'], 'decision expression')
        if 'note' in decision:
            c.text(decision['note'], 'decision note')
        if 'representation' in decision:
            from production_expression import ROLES
            representation = decision['representation']
            c.exact(representation, {'role'} | ({'primary'} if isinstance(representation, dict)
                                              and 'primary' in representation else set()), 'representation')
            if representation['role'] not in ROLES:
                raise ValueError('unknown representation role')
            if 'primary' in representation:
                c.text(representation['primary'], 'primary visible decision')
        if set(strings(decision['basis'], 'decision basis')) - applied:
            raise ValueError('decision cites an unknown or unused source')
        invalid_criteria = set(strings(decision['criteria'], 'decision criteria', nonempty=True)) - criterion_ids
        if invalid_criteria:
            from production_diagnostics import ProductionError
            raise ProductionError('INPUT_CONSISTENCY_ERROR',
                'Decision names an unknown criterion: ' + ', '.join(sorted(invalid_criteria)) + '.',
                phase='task-contract', pointer=f'$.direction.decisions[{index}].criteria',
                decision=ident, invalid_criteria=sorted(invalid_criteria), available_criteria=sorted(criterion_ids),
                required_action='Edit this decision.criteria to cite the applicable IDs in available_criteria. '
                                'Keep criterion descriptions in the task criteria; these references name their IDs.')
        strings(decision['depends_on'], 'decision dependencies')
        realization = decision['realization']
        c.exact(realization, {'method', 'instructions', 'capability_source', 'limitations'}, 'realization')
        c.text(realization['method'], 'realization method')
        c.text(realization['instructions'], 'realization instructions')
        capability = realization['capability_source']
        if capability is not None and capability not in applied:
            raise ValueError('capability evidence must identify an applied task source')
        strings(realization['limitations'], 'realization limitations')
        if not isinstance(decision['deviations'], list):
            raise ValueError('deviations must be a list')
        for deviation in decision['deviations']:
            c.exact(deviation, {'source', 'locator', 'scope', 'reason'}, 'intentional deviation')
            if deviation['source'] not in source_ids:
                raise ValueError('deviation must identify the condition it departs from')
            for field in ('locator', 'scope', 'reason'):
                c.text(deviation[field], 'deviation ' + field)
    validate_source_allowances(direction['source_allowances'], applied, criterion_ids, task_id=task_id)
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


def validate_source_allowances(variations: Any, applied: set[str], criterion_ids: set[str], *, task_id: str | None) -> None:
    """Keep source authority independent of any selected depiction or technique."""
    if not isinstance(variations, list):
        raise ValueError('source allowances must be a list')
    seen = set()
    for variation in variations:
        c.exact(variation, {'id', 'source', 'locator', 'author', 'scope', 'allowance', 'limits', 'criteria'},
                'source allowance')
        ident = c.text(variation['id'], 'source allowance id')
        if ident in seen:
            raise ValueError('duplicate source allowance id')
        seen.add(ident)
        for field in ('source', 'locator', 'author', 'allowance'):
            c.text(variation[field], 'source allowance ' + field)
        if variation['source'] not in applied:
            raise ValueError('source allowance must cite an applied task source')
        strings(variation['limits'], 'source allowance limits')
        if set(strings(variation['criteria'], 'source allowance criteria', nonempty=True)) - criterion_ids:
            raise ValueError('source allowance must name known task criteria')
        scope = variation['scope']
        if not isinstance(scope, dict):
            raise ValueError('source allowance scope must identify a task or source')
        if scope.get('kind') == 'task':
            c.exact(scope, {'kind', 'task_id'}, 'source allowance task scope')
            c.text(scope['task_id'], 'source allowance task id')
            if task_id is None or scope['task_id'] != task_id:
                raise ValueError('source allowance belongs to a different task')
        elif scope.get('kind') == 'source':
            c.exact(scope, {'kind', 'source', 'sha256'}, 'source allowance source scope')
            c.text(scope['source'], 'source allowance scope source')
            if scope['source'] not in applied:
                raise ValueError('source allowance scope must identify an applied task source')
            c.sha(scope['sha256'])
        else:
            raise ValueError('source allowance scope must identify a task or source')


def validate_variation_bindings(task: dict, source_hashes: dict[str, str]) -> None:
    """Check source-scoped allowances against bytes captured by the source owner."""
    for variation in task['direction']['source_allowances']:
        scope = variation['scope']
        if scope['kind'] == 'source' and source_hashes.get(scope['source']) != scope['sha256']:
            raise ValueError('source allowance source changed; reassess its scope before use')


def consumer(direction: dict) -> dict:
    """Only selected realization enters a model-facing view, not the dossier."""
    from production_expression import role
    return {'directives': [
        {'decision': d['id'], 'expression': d['expression'],
         'method': d['realization']['method'],
         'instructions': d['realization']['instructions']}
        for d in direction['decisions'] if role(d) not in {'author-only', 'unresolved'}
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
                    or d['realization']['capability_source'] in changed_sources
                    or any(x['source'] in changed_sources for x in d['deviations'])}
    while True:
        expanded = affected_ids | {d['id'] for d in decisions if affected_ids.intersection(d['depends_on'])
                                   or d.get('representation', {}).get('primary') in affected_ids}
        if expanded == affected_ids:
            break
        affected_ids = expanded
    checks = {x for d in decisions if d['id'] in affected_ids for x in d['criteria']}
    checks.update(item['id'] for item in task['criteria']
                  if item.get('origin', {}).get('source') in changed_sources
                  or item.get('observation', {}).get('baseline') in changed_sources)
    for allowance in task['direction']['source_allowances']:
        if (all_inputs or allowance['source'] in changed_sources
                or allowance['scope'].get('source') in changed_sources):
            checks.update(allowance['criteria'])
    if all_inputs:
        checks.update(x['id'] for x in task['criteria'])
    return {'decisions': sorted(affected_ids), 'criteria': sorted(checks),
            'purpose': all_inputs or bool(changed_sources.intersection(task['direction']['basis']))}


def direction_targets(task: dict) -> list[str]:
    return sorted(['purpose'] + ['decision:' + d['id'] for d in task['direction']['decisions']])
