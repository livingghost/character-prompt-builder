"""Check declared requirement authority and the evidence a medium can supply.

The author judges meaning. These checks follow explicit source, decision and
evidence declarations; they never classify prose or infer approval from it.
"""
from __future__ import annotations

from production_diagnostics import ProductionError


GUIDANCE = {'document_path': 'references/runtime/production-direction.md#record-the-production-direction'}
ROLES = frozenset({'visible', 'secondary-figurative', 'context-only', 'author-only', 'unresolved'})


def _fail(code: str, message: str, pointer: str, action: str, **details) -> None:
    raise ProductionError(code, message, phase='task-contract', pointer=pointer,
                          required_action=action, guidance=GUIDANCE, **details)


def role(decision: dict) -> str:
    """Ordinary selected instructions describe the visible primary depiction."""
    return decision.get('representation', {}).get('role', 'visible')


def validate(task: dict) -> None:
    """Validate a new authored task without changing historical saved records."""
    sources = {item['id']: item for item in task['sources'] if item['disposition'] == 'applied'}
    direction = task['direction']
    decisions = {item['id']: item for item in direction['decisions']}
    artifact = task['artifact']
    image_format = direction.get('image_format', 'single-still')
    if 'image_format' in direction and artifact != 'image':
        _fail('MEDIUM_REPRESENTATION_UNRESOLVED', 'image_format describes an image artifact.',
              '$.direction.image_format', 'Remove image_format for this non-image artifact; '
              'select criteria evidence that its actual medium supports.')

    for index, decision in enumerate(direction['decisions']):
        current = role(decision)
        pointer = f'$.direction.decisions[{index}].representation'
        representation = decision.get('representation', {})
        if current == 'unresolved':
            _fail('MEDIUM_REPRESENTATION_UNRESOLVED',
                  'A selected decision still has no resolved representation.', pointer,
                  'Resolve its visible instructions, retain necessary context as context-only, '
                  'or keep private material author-only before completing this task.', decision=decision['id'])
        if current == 'secondary-figurative':
            primary = decisions.get(representation.get('primary'))
            if primary is None or role(primary) != 'visible' or primary['id'] == decision['id']:
                _fail('PRIMARY_VISIBLE_DEPICTION_REQUIRED',
                      'A figurative impression requires its own resolved primary visible depiction.', pointer,
                      'Name the visible decision in representation.primary. Its subject, action, '
                      'expression and framing must remain understandable without the figurative impression.',
                      decision=decision['id'])
        elif 'primary' in representation:
            _fail('MEDIUM_REPRESENTATION_UNRESOLVED',
                  'Only a secondary figurative impression names a primary decision.', pointer,
                  'Keep primary only on a secondary-figurative representation.')

    for index, criterion in enumerate(task['criteria']):
        pointer = f'$.criteria[{index}]'
        hard = criterion['strength'] == 'hard'
        origin = criterion.get('origin')
        observation = criterion.get('observation')
        if hard and origin is None:
            _fail('UNAUTHORIZED_REQUIREMENT_PROMOTION',
                  'A hard criterion needs its actual request or adopted-source origin.', pointer + '.origin',
                  'Declare origin.kind as user-request for an actual commission requirement, or '
                  'adopted-source with its applied source ID. Keep an agent realization advisory.',
                  criterion=criterion['id'])
        if origin is not None:
            kind = origin['kind']
            if kind == 'agent-realization':
                if hard:
                    _fail('UNAUTHORIZED_REQUIREMENT_PROMOTION',
                          'An agent realization cannot by itself establish a hard requirement.', pointer + '.origin',
                          'Make this criterion advisory, or cite the actual user instruction or '
                          'adopted source that independently requires this result.', criterion=criterion['id'])
                if origin.get('decision') not in decisions:
                    _fail('UNAUTHORIZED_REQUIREMENT_PROMOTION',
                          'The criterion names no current realization decision.', pointer + '.origin.decision',
                          'Select the existing decision ID that owns this advisory realization.',
                          criterion=criterion['id'])
            elif kind == 'adopted-source' and origin.get('source') not in sources:
                _fail('UNAUTHORIZED_REQUIREMENT_PROMOTION',
                      'The criterion origin is not an applied source.', pointer + '.origin.source',
                      'Select its actual applied source ID and preserve that source\'s conditions and '
                      'permitted variation. An unused source supplies no requirement.', criterion=criterion['id'])
        if hard and observation is None:
            _fail('MEDIUM_REPRESENTATION_UNRESOLVED',
                  'A hard criterion needs its observable scope.', pointer + '.observation',
                  'Declare observation.scope for what the selected evidence can establish. '
                  'Use impression for an appearance such as happiness, and keep hidden facts out of image requirements.',
                  criterion=criterion['id'])
        if observation is None:
            continue
        scope = observation['scope']
        decision_id = observation.get('decision')
        selected = decisions.get(decision_id)
        if decision_id is not None and selected is None:
            _fail('MEDIUM_REPRESENTATION_UNRESOLVED', 'The observation names an unknown decision.',
                  pointer + '.observation.decision', 'Select the existing decision that this criterion assesses.',
                  criterion=criterion['id'])
        if not hard:
            continue
        if scope in {'context-only', 'author-only', 'unresolved'} or (
                selected is not None and role(selected) in {'secondary-figurative', 'context-only', 'author-only', 'unresolved'}):
            _fail('MEDIUM_UNREPRESENTABLE_REQUIREMENT',
                  'This declared context, private fact or secondary impression cannot be a hard visible requirement.',
                  pointer + '.observation', 'Assess the primary observable result, keep the secondary impression '
                  'advisory, or provide a medium and scope that can establish the actual requirement.',
                  criterion=criterion['id'])
        evidence = criterion['evidence']
        supported = {'image': {'artifact', 'image'}, 'video': {'artifact', 'image', 'motion', 'audio'},
                     'audio': {'artifact', 'audio'}, 'text': {'artifact', 'text'},
                     'json': {'artifact', 'text'}, 'binary': {'artifact'}}[artifact]
        if evidence not in supported:
            _fail('MEDIUM_UNREPRESENTABLE_REQUIREMENT',
                  'The artifact cannot supply the evidence required by this hard criterion.', pointer + '.evidence',
                  'Use evidence carried by the selected artifact, or select a compatible output medium.',
                  criterion=criterion['id'], artifact=artifact, evidence=evidence)
        if scope == 'sequence' and not ((artifact == 'image' and image_format == 'multi-panel' and evidence == 'image')
                                       or (artifact == 'video' and evidence == 'motion')
                                       or (artifact == 'audio' and evidence == 'audio')
                                       or (artifact in {'text', 'json'} and evidence == 'text')):
            _fail('MEDIUM_UNREPRESENTABLE_REQUIREMENT',
                  'The selected evidence cannot establish an ordered sequence.', pointer + '.observation.scope',
                  'For one still, select a simultaneous visible state and retain unshown order as context. '
                  'Use multi-panel image_format with image evidence, motion evidence, or another sequence-capable medium '
                  'when the sequence itself is required.', criterion=criterion['id'])
        if scope == 'duration' and not ((artifact == 'video' and evidence in {'motion', 'audio'})
                                      or (artifact == 'audio' and evidence == 'audio')
                                      or (artifact in {'text', 'json'} and evidence == 'text')):
            _fail('MEDIUM_UNREPRESENTABLE_REQUIREMENT',
                  'The selected evidence cannot establish the declared duration.', pointer + '.observation.scope',
                  'Use measured motion or audio evidence for playback duration, or text evidence for '
                  'an explicitly stated narrative interval. For a still, review the depicted state '
                  'or a visible time label as observable content instead of proof that time elapsed.',
                  criterion=criterion['id'])
        if scope == 'comparison' and observation.get('baseline') not in sources:
            _fail('MEDIUM_REPRESENTATION_UNRESOLVED',
                  'A comparison has no applied baseline source.', pointer + '.observation.baseline',
                  'Name the applied comparison source in observation.baseline, or replace the comparison with '
                  'an independently observable description.', criterion=criterion['id'])
