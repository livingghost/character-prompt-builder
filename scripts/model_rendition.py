"""Bind authored image instructions and explicit interface controls to their sources."""
from __future__ import annotations
import copy
import re
from typing import Any
import execution_contract as c
import request_contract as rc
from input_evidence import InputEvidence
from reference_delivery import validate_subject_uses


REVIEW_REQUIREMENTS = (
    {'id': 'finished-image',
     'statement': 'Reconstruct the selected artifact and depicted situation from only the final text, supported controls and actual supplied media. State what they establish about the subjects, present circumstances, action, relationships, intended degree, framing and finish, as applicable. Identify premises that the instructions require but the delivered input leaves unstated. Then compare that reading with the brief and selected production scope. Assess whether the chosen framing serves that purpose; inspection convenience is not a coverage requirement, and intentional offscreen continuation is not missing anatomy. Assess necessary exclusions together with the wanted result. Explain missing meaning, unsupported inferences and instructions that exceed the requested depiction; resolve those differences before a satisfied assessment.'},
    {'id': 'supplied-inputs',
     'statement': 'Inspect the actual supplied media and assign each relevant subject attribute to its source: retained identity, requested change, pose, clothing, finish or another declared use. Distinguish what the delivered images establish from knowledge available only in source records or prior conversation. Confirm that reference numbers, subject assignments, crops and delivered details match the final instructions. Resolve priorities and scoped exceptions together while preserving every required attribute and its evidence.'},
    {'id': 'ownership',
     'statement': 'Explain how each consequential instruction serves the selected artifact, including context that makes its present depiction intelligible and necessary use of supplied inputs. Keep production and story-management decisions outside that depiction in their owning records. Apply ambiguity or narrative outcomes as portrayal choices when the requested artifact includes them. Place production identifiers, provenance, review reasoning and execution values in their records or native controls. Trace the scoped intent through the final wording and any requested translation, including modifiers, degree and necessary exclusions.'},
)


def review_requirements() -> list[dict]:
    """The author's distinct judgments over every text field, control and supplied image."""
    return copy.deepcopy(list(REVIEW_REQUIREMENTS))


def draft_review(input_sha256: str, *, actor: str | None, binding_ids: list[str]) -> dict:
    """Name the complete input and its reference scopes; leave every judgment unanswered."""
    c.sha(input_sha256)
    return {'input_sha256': input_sha256, 'reviewer': actor, 'binding_ids': list(binding_ids),
            'assessments': [{'criterion': item['id'], 'conclusion': None, 'reason': ''}
                            for item in REVIEW_REQUIREMENTS]}


def validate_review(review: Any, *, input_sha256: str, actor: str, binding_ids: list[str]) -> None:
    """Verify exact coverage and the responsible actor's supplied judgments, never infer meaning."""
    c.exact(review, {'input_sha256', 'reviewer', 'binding_ids', 'assessments'}, 'rendition review')
    c.sha(input_sha256)
    if review['input_sha256'] != input_sha256:
        raise ValueError('rendition review belongs to another complete model input')
    c.text(actor, 'authorized rendition reviewer')
    if review['reviewer'] != actor:
        raise ValueError('the authorized actor must record the rendition assessment')
    reviewed = review['binding_ids']
    if (not isinstance(reviewed, list) or any(not isinstance(item, str) for item in reviewed)
            or len(set(reviewed)) != len(reviewed) or reviewed != binding_ids):
        raise ValueError('rendition review must cover every transported reference binding in order')
    assessments = review['assessments']
    if not isinstance(assessments, list):
        raise ValueError('rendition assessments must be an array')
    required = {item['id'] for item in REVIEW_REQUIREMENTS}
    seen = set()
    for item in assessments:
        c.exact(item, {'criterion', 'conclusion', 'reason'}, 'rendition criterion assessment')
        criterion = c.text(item['criterion'], 'rendition criterion')
        if criterion not in required or criterion in seen:
            raise ValueError('rendition assessment criterion is unknown or repeated')
        seen.add(criterion)
        c.text(item['reason'], 'rendition assessment reason')
        if item['conclusion'] != 'satisfied':
            raise ValueError('the rendition assessment is incomplete or not satisfied')
    if seen != required:
        raise ValueError('rendition assessment has missing criteria')


def _binding_id(row:dict)->str:
    return 'reference:'+str(row['reference_number'])


def validate_bindings(rows:Any)->list[dict]:
    if not isinstance(rows,list):raise ValueError('reference bindings must be an array')
    identifiers=set()
    for row in rows:
        c.exact(row,{'reference_number','attachment_number','region_pixels','role','controls','must_not_control'}
                | ({'reference_id'} if 'reference_id' in row else set())
                | ({'subject_uses'} if 'subject_uses' in row else set())
                | ({'subject_id'} if 'subject_id' in row else set()),'reference binding')
        if 'subject_id' in row:c.text(row['subject_id'],'state reference subject')
        if 'reference_id' in row:c.text(row['reference_id'],'selected reference use id')
        validate_subject_uses(row.get('subject_uses', []),
                              subject_ids={row['subject_id']} if 'subject_id' in row else None)
        for key in ('reference_number','attachment_number'):
            if type(row[key]) is not int or row[key]<1:raise ValueError('reference positions must be positive integers')
        if row['reference_number'] in identifiers:raise ValueError('reference number repeats')
        identifiers.add(row['reference_number']);c.text(row['role'],'reference role')
        for key in ('controls','must_not_control'):
            if not isinstance(row[key],list):raise ValueError('reference authority must be a list')
            for value in row[key]:c.text(value,'reference authority')
        if set(row['controls']) & set(row['must_not_control']):raise ValueError('reference authority conflicts with itself')
        if row['region_pixels'] is not None:
            c.exact(row['region_pixels'],{'x','y','width','height'},'reference region')
            for key,value in row['region_pixels'].items():
                if type(value) is not int or value<(1 if key in {'width','height'} else 0):raise ValueError('invalid reference region')
    if identifiers!=set(range(1,len(rows)+1)):raise ValueError('reference numbers must cover the selected order')
    return rows


_REFERENCE_MARKER = re.compile(r'\{\{reference:([^{}]+)\}\}')
_REFERENCE_FIELDS = frozenset({'attachment_number', 'controls', 'must_not_control',
                              'region', 'x', 'y', 'width', 'height'})


def reference_text_slots(bindings: list[dict]) -> list[dict]:
    """Expose editable source markers and their current model-facing values.

    The author writes the surrounding sentence or native tag grammar. The
    runtime substitutes selected contributions and actual delivery locations.
    It supplies no depiction, exclusion paragraph or assessment conclusion.
    """
    slots = []
    for row in bindings:
        identifier = c.text(row.get('reference_id'), 'selected reference use id')
        values = {'attachment_number': str(row['attachment_number']),
                  'controls': ', '.join(row['controls']),
                  'must_not_control': ', '.join(row['must_not_control'])}
        if row.get('region_pixels') is not None:
            region = row['region_pixels']
            values['region'] = ', '.join(str(region[key]) for key in ('x', 'y', 'width', 'height'))
            values.update({key: str(region[key]) for key in ('x', 'y', 'width', 'height')})
        slots.append({'reference_id': identifier,
                      'values': values,
                      'markers': {key: '{{reference:' + identifier + ':' + key + '}}' for key in values},
                      'required': ['attachment_number', 'controls'] + (['region'] if row.get('region_pixels') is not None else [])})
    return slots


def resolve_reference_text(text: str, bindings: list[dict], *, require_scopes: bool = True) -> dict:
    """Consume actual reference directions from one authored text source.

    This is exact token substitution, not semantic validation. A selected
    scope changes the delivered bytes. Marker traces retain their use IDs and
    source/final ranges, so reordering or board assembly needs no manual index
    rewrite. Required scope consumption establishes delivery, not correctness.
    """
    if not isinstance(text, str):
        raise ValueError('reference input must be authored text')
    slots = reference_text_slots(bindings)
    by_id = {row['reference_id']: row for row in slots}
    if len(by_id) != len(slots):
        raise ValueError('reference text requires distinct stable use ids')
    parts = []
    trace = []
    consumed: dict[str, set[str]] = {}
    source_end = target_end = 0
    for match in _REFERENCE_MARKER.finditer(text):
        identifier, separator, field = match.group(1).rpartition(':')
        if not separator or field not in _REFERENCE_FIELDS:
            raise ValueError('reference marker requires a stable use id and supported field: ' + match.group(0))
        if identifier not in by_id:
            raise ValueError('reference marker names an unselected use: ' + identifier)
        if field not in by_id[identifier]['values']:
            raise ValueError('reference marker requests an unavailable delivery location: ' + match.group(0))
        unchanged = text[source_end:match.start()]
        parts.append(unchanged)
        target_end += len(unchanged)
        replacement = by_id[identifier]['values'][field]
        parts.append(replacement)
        trace.append({'reference_id': identifier, 'field': field,
                      'source_range': {'start': match.start(), 'end': match.end()},
                      'target_range': {'start': target_end, 'end': target_end + len(replacement)},
                      'text': replacement})
        consumed.setdefault(identifier, set()).add(field)
        source_end = match.end()
        target_end += len(replacement)
    parts.append(text[source_end:])
    result = ''.join(parts)
    if '{{reference:' in result:
        raise ValueError('reference input contains an incomplete or unresolved marker')
    if require_scopes:
        missing = []
        for row in slots:
            used = consumed.get(row['reference_id'], set())
            needed = {'attachment_number', 'controls'} - used
            if 'region' in row['required'] and 'region' not in used and not {'x', 'y', 'width', 'height'} <= used:
                needed.add('region')
            if needed:
                missing.append(row['reference_id'] + ': ' + ', '.join(sorted(needed)))
        if missing:
            from production_diagnostics import ProductionError
            raise ProductionError('REFERENCE_TEXT_UNRESOLVED',
                'Selected reference contributions have no consumed input direction: ' + '; '.join(missing),
                phase='reference-input', required_action='Write the current reference-use direction in the editable prompt using '
                'the reference attachment_number and controls markers; include its region marker for a shared board. '
                'Inspect reference_text_slots for actual fields and values. Native reference controls use their declared mapping instead.',
                reference_text_slots=slots)
    return {'text': result, 'source_text': text, 'source_sha256': c.digest(text.encode('utf-8')),
            'sha256': c.digest(result.encode('utf-8')), 'trace': trace}


def resolve_reference_channels(values: dict, bindings: list[dict], *,
                               reference_mode: str, negative_transport: str) -> dict:
    """Resolve authored sources before parser, vocabulary, budget and hash checks."""
    if reference_mode not in {'none', 'authored-rendition', 'native-fields'}:
        raise ValueError('reference input requires a supported delivery mode')
    selected = ('integrated_prompt' if negative_transport in {'integrated-critical', 'retained-only'}
                and values.get('integrated_prompt', '').strip() else 'prompt')
    channels = {}
    for name in ('prompt', 'negative_prompt', 'integrated_prompt', 'native_negative'):
        channels[name] = resolve_reference_text(values.get(name, ''), bindings,
            require_scopes=bool(bindings) and reference_mode == 'authored-rendition' and name == selected)
    return {'mode': reference_mode, 'selected_channel': selected, 'channels': channels}


def validate_reference_channels(record: dict, bindings: list[dict], *,
                                reference_mode: str, negative_transport: str) -> dict:
    """Recompute the captured transformation from its retained authored sources."""
    c.exact(record, {'mode', 'selected_channel', 'channels'}, 'reference input transformation')
    channels = record['channels']
    names = {'prompt', 'negative_prompt', 'integrated_prompt', 'native_negative'}
    c.exact(channels, names, 'reference input channels')
    sources = {}
    for name, channel in channels.items():
        if not isinstance(channel, dict) or not isinstance(channel.get('source_text'), str):
            raise ValueError('reference input channel requires its authored source: ' + name)
        sources[name] = channel['source_text']
    expected = resolve_reference_channels(sources, bindings, reference_mode=reference_mode,
                                         negative_transport=negative_transport)
    if record != expected:
        raise ValueError('reference input transformation differs from its retained source and actual scope')
    return expected


REFERENCE_CONTRACT_FIELDS = frozenset({'artifact_type', 'target', 'dialects', 'mode', 'fields', 'basis'})


def reference_contract(policy:dict|None,reader:InputEvidence,expected_target:dict,dialect:str|None,rows:list[dict])->dict|None:
    validate_bindings(rows)
    if not rows:return None
    if policy is None:
        from production_diagnostics import ProductionError
        raise ProductionError('VALIDATION_POLICY_REQUIRED',
            'The selected references need an execution policy that declares reference_instruction_transport.',
            phase='request-validation-evidence',pointer='$.validation.execution_policy',
            required_action='Author an execution policy that declares reference_instruction_transport for this target, '
                            'select it at choices.validation.execution_policy, then run the same command again.')
    c.exact(policy,{'mode','contract'},'reference instruction transport')
    mode=policy['mode']
    if mode not in {'native-fields','authored-rendition','not-supported'}:raise ValueError('unknown reference instruction transport')
    document=reader.json(policy['contract']);local=reader.at(policy['contract'])
    c.exact(document,REFERENCE_CONTRACT_FIELDS,'reference render contract')
    if document['artifact_type']!='reference-render-contract' or document['target']!=expected_target or document['mode']!=mode:
        raise ValueError('reference render contract target or mode differs from selected execution')
    if not isinstance(document['dialects'],list) or not document['dialects']:raise ValueError('reference contract requires explicit supported dialects')
    if dialect not in document['dialects']:raise ValueError('reference render contract does not cover the selected dialect')
    local.basis(document['basis'])
    if mode=='not-supported':raise ValueError('the selected execution contract cannot deliver the required reference authority')
    if mode=='authored-rendition':
        if document['fields']!=[]:raise ValueError('authored reference instructions have no native fields')
    else:
        if not isinstance(document['fields'],list) or not document['fields']:
            raise ValueError('native reference mode requires explicit structural mappings')
        allowed={'attachment_number','region_pixels','role','controls','must_not_control'}
        mapped=set();destinations=[]
        for item in document['fields']:
            c.exact(item,{'binding_field','request_field','container'},'native reference mapping')
            if item['binding_field'] not in allowed or item['binding_field'] in mapped:raise ValueError('native binding field is absent or duplicated')
            mapped.add(item['binding_field']);path=rc.path_parts(item['request_field'])
            if item['container'] not in {'ordered-array','single'}:raise ValueError('native mapping needs an explicit container')
            if item['container']=='single' and len(rows)!=1:raise ValueError('single native control cannot carry several reference bindings')
            if any(rc.overlaps(path,x) for x in destinations):raise ValueError('native reference fields overlap')
            destinations.append(path)
        required={'attachment_number','role'}
        for key in ('controls','must_not_control','region_pixels'):
            if any(row.get(key) for row in rows):required.add(key)
        if not required<=mapped:raise ValueError('native reference controls omit declared authority or region fields: '+', '.join(sorted(required-mapped)))
    return document


def compose(original:str,*,segments:list[dict]|None,authored_source:dict,bindings:list[dict],
            reference_policy:dict|None,reader:InputEvidence,target:dict,dialect:str|None)->dict:
    """Preserve the selected depiction and keep production records in the review context."""
    if not isinstance(original,str):raise ValueError('rendition must be a string')
    validate_bindings(bindings)
    parts=[];trace=[];controls=[];offset=0
    def append(text,kind,refs,transform,binding_ids=None):
        nonlocal offset
        if not text:return
        parts.append(text);trace.append({'source_kind':kind,'source_refs':copy.deepcopy(refs),'transform_id':transform,
            'target_field':None,'target_range':{'start':offset,'end':offset+len(text)},'binding_ids':list(binding_ids or [])})
        offset+=len(text)
    contract=reference_contract(reference_policy,reader,target,dialect,bindings)
    if contract is not None:
        ids=[_binding_id(row) for row in bindings]
        if contract['mode']=='native-fields':
            for item in contract['fields']:
                values=[row[item['binding_field']] for row in bindings]
                controls.append({'id':'reference-control:'+item['binding_field'],'field':rc.path_parts(item['request_field']),
                    'value':values if item['container']=='ordered-array' else values[0],'binding_ids':ids})
    if segments is None:
        append(original,'authored',[authored_source],'selected-rendition')
    else:
        end=0
        for segment in segments:
            c.exact(segment,{'source_kind','start','end','text'},'rendition segment')
            if segment['source_kind'] not in {'authored','model-setting'}:raise ValueError('unknown rendition segment source')
            if type(segment['start']) is not int or type(segment['end']) is not int or segment['start']!=end or segment['end']<end:
                raise ValueError('rendition segments have a gap or overlap')
            if original[segment['start']:segment['end']]!=segment['text']:raise ValueError('rendition segment differs from the assembled text')
            append(segment['text'],segment['source_kind'],[authored_source],'authored-rendition' if segment['source_kind']=='authored' else 'chosen-recommendation')
            end=segment['end']
        if end!=len(original):raise ValueError('rendition segments do not cover the complete text')
    return {'text':''.join(parts),'trace':trace,'native_reference_controls':controls,'review_requirements':review_requirements()}
