"""Neutral, explicitly synthetic Studio identity fixtures for reference tests.

Only tests and executable examples import this module. Every approval names a
synthetic decision, and the synthetic transport performs no network request.
"""
from __future__ import annotations
import copy
import base64
from unittest.mock import patch
from pathlib import Path

import execution_contract as c
import production_case_fixtures as fixture
import production_workflow as workflow
import production_execution as execution
import production_fixtures
import studio
import studio_reference
from test_production_execution import decisions


def adopted_case(test, *, work_id: str = 'C01'):
    import test_production_adoption as tests
    # This factory owns its template lifetime independently of unittest's class
    # runner (and of other fixture instances in the same process).
    fixture_type = type('ReferenceAdoptionFixture', (tests.AdoptionTests,), {})
    case = fixture_type('test_separate_authorized_adoption_and_completion')
    case.addCleanup(fixture_type.doClassCleanups)
    test.addCleanup(case.doCleanups)
    fixture_type.setUpClass()
    case.setUp()
    case.approval['continuity_decision']['character_id'] = work_id
    fixture.write(case.root / 'approval.json', case.approval)
    case.select(); case.adopt(case.authorize_adoption())
    return case


def adopt_second(case, character: str, *, work_id: str, pixels: bytes | None = None) -> dict:
    """Adopt a second synthetic PNG, using the first image's bytes by default."""
    root = case.root
    studio.add_character(root, character, 'general')
    task = copy.deepcopy(case.task)
    task['recording'].update(character=character, subject_map={'robot':character}, slot='base.front', sheet_panel=True)
    fixture.write(root / (character + '-task.json'), task)
    run = workflow.prepare(root, character + '-task.json')['run']
    import transport_synthetic
    original_send = transport_synthetic.send
    selected_pixels = c.read(root / case.row['result']['path']) if pixels is None else pixels
    def selected_response(*args, **kwargs):
        answer = original_send(*args, **kwargs)
        # The selected fixture bytes are captured before review and adoption.
        answer['data'][0]['data'] = base64.b64encode(selected_pixels).decode('ascii')
        return answer
    with patch.object(transport_synthetic, 'send', side_effect=selected_response):
        out = execution.execute(root, run, decisions_file=decisions(root, run))
    candidate = out['runs'][0]['candidates'][0]
    row = studio.read_iterations(studio.character_home(root, character))[0]
    review = workflow.draft_review(root, run, candidate)
    review.update(reviewer='Synthetic reviewer', observations=[{'evidence':'candidate','locator':{'kind':'whole'},
        'observation':'The local synthetic PNG exists.', 'interpretation':'Protocol fixture only.', 'limitations':['No visual quality or real user approval.']}], conclusion='Synthetic choice.')
    for check in review['checks']:
        check.update(verdict='pass', observation_indices=[0], reason='Synthetic authored assessment.')
    fixture.write(root / (character + '-review.json'), review)
    workflow.review(root, run, character + '-review.json')
    selection = workflow.draft_selection(root, run, candidate)
    selection['reason'] = 'Explicit synthetic selection.'
    production_fixtures.selection(root, run, selection)
    fixture.write(root / (character + '-selection.json'), selection)
    workflow.select(root, run, character + '-selection.json')
    approval = copy.deepcopy(case.approval)
    approval.update(character=character, iteration_id=row['iteration_id'], slot=row['slot'], image_sha256=row['result']['sha256'])
    approval['continuity_decision']['character_id'] = work_id
    filename = character + '-approval.json'; fixture.write(root / filename, approval)
    intent = workflow.adoption_intent(root, run, candidate, character, row['iteration_id'], approval)
    token = production_fixtures.grant(root, run, intent)
    workflow.adopt(root, run, candidate, character, row['iteration_id'], filename, token)
    return studio_reference.current_source(root, character, row['slot'])


def scope(binding_id: str = 'BIND-STUDIO') -> dict:
    return {'binding_id':binding_id, 'role':'identity', 'effective_story_range':{'from_order':0,'to_order':None},
            'visibly_supported_state':['identity-anchor'], 'unsupported_or_occluded_state':['current-clothing'],
            'intended_influence':['identity'], 'unsupported_assumptions':['Do not infer the current clothing from an identity reference.'],
            'review_dimensions':['identity']}


def reference_task(case) -> tuple[str, dict]:
    """Author one ordinary Production task using the exact newly supported source."""
    from prepare_generation_references import prepare_references
    from production_identity import reference_id
    from request_validation_fixtures import fixture_validation
    root = case.root
    source = studio_reference.current_source(root, 'robot', case.row['slot'])
    work_id = case.approval['continuity_decision']['character_id']
    refs = prepare_references([{'role':'identity','source':source,
        'subject_uses':[{'subject_id':work_id,'use':'identity','priority':0}]}],
        model=fixture.MODEL_ID, output_dir=root/'prepared-studio-refs')
    fixture.write(root/'studio-references.json', refs)
    task = copy.deepcopy(case.task)
    reference = reference_id(refs['selected_references'][0])
    task['criteria'].append({'id':'adopted-identity','strength':'hard','evidence':'image',
        'text':'Compare the whole recurring subject with the complete adopted identity image, '
               'including its visible definitions and relations within the scene evidence limits.',
        'identity_review':[work_id],
        'identity_bindings':[{'source':'reference:'+reference,'subject_ids':[work_id],'selectors':[''],
            'treatment':'preserve',
            'reason':'This synthetic trial uses the adopted image as its original identity source; '
                     'the assigned reference scope still excludes current clothing.',
            'carriers':[{'kind':'reference','reference':reference,'use':'identity'}],'variation':None}]})
    task['recording'].update(slot='scene.result', sheet_panel=False, subject_map={work_id:'robot'})
    task['generation'].update(references='studio-references.json', production_spec='reference-spec.json',
        request_validation='reference-validation.json', continuity={work_id:'recurring'})
    spec = c.load(root/'spec.json'); spec['render_intent']['execution_mode'] = 'reference-guided'
    spec['subjects'][0]['id'] = work_id
    spec['subjects'][0]['identity'] = [
        'The synthetic recurring subject retains the complete adopted identity from its assigned source image.']
    fixture.write(root/'reference-spec.json', spec)
    fixture.write(root/'reference-validation.json', fixture_validation(root,fixture.MODEL_ID,reference_mode='authored-rendition',service='synthetic'))
    fixture.write(root/'reference-task.json', task)
    return 'reference-task.json', source
