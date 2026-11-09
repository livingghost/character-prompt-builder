#!/usr/bin/env python3
"""Production-loop regressions on real bytes and explicit synthetic decisions."""
from __future__ import annotations

import base64
import copy
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import wave
from unittest.mock import patch

import execution_contract as c
import production_binding as binding
import production_evidence as media
import production_fixtures as fixture
import production_permissions as permissions
import production_plan as plan
import production_workflow as w
import work_ledger as ledger


def decision(ident='expression', basis=None):
    return {'id': ident, 'question': 'How should attention be held?', 'importance': 'material',
            'basis': basis or [],
            'options': [
                {'id': 'hold', 'expression': 'Preserve stillness rather than impose a reaction.',
                 'realization': {'method': 'authored image', 'instructions': 'Keep the sparse field and quiet interval.',
                                 'capability_source': None, 'limitations': ['Appearance must be observed in the result.']},
                 'tradeoffs': ['A quiet presentation may be less immediately conspicuous.']},
                {'id': 'shift', 'expression': 'Shift attention through placement, not a required gesture.',
                 'realization': {'method': 'local composition edit', 'instructions': 'Use the intended spacing.',
                                 'capability_source': None, 'limitations': ['No temporal behavior is proven by an image.']},
                 'tradeoffs': ['A placement change alters the emphasis.']}],
            'selected': 'hold', 'reason': 'The declared purpose favors persistence.',
            'criteria': ['read'], 'depends_on': [], 'deviations': []}


def png(value=64):
    from PIL import Image
    out = io.BytesIO()
    Image.new('RGB', (24, 16), (value, value, value)).save(out, format='PNG')
    return out.getvalue()


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.sources = [{'id': 'persona', 'disposition': 'applied'}]
        self.criteria = [{'id': 'read'}]
        self.direction = {'purpose': 'A diagram, abstract field or situated portrayal.',
                          'intended_effect': 'Hold attention without assuming a cast or dramatic turn.',
                          'basis': [], 'decisions': [decision()], 'action_slice': None, 'limitations': []}
    def validate(self):
        return plan.validate(self.direction, self.sources, self.criteria)
    def test_free_subject_and_no_action(self):
        self.validate()
    def test_no_decisions_when_no_choice_was_made(self):
        self.direction['decisions'] = []
        self.validate()
    def test_material_comparison_is_required(self):
        self.direction['decisions'][0]['options'].pop()
        with self.assertRaises(ValueError): self.validate()
    def test_fixed_instruction_needs_no_dummy_alternative(self):
        d = self.direction['decisions'][0]; d['importance'] = 'fixed'; d['options'].pop(); d['options'][0]['tradeoffs'] = []
        self.validate()
    def test_routine_choice_needs_no_dummy_alternative(self):
        d = self.direction['decisions'][0]; d['importance'] = 'routine'; d['options'].pop()
        self.validate()
    def test_unknown_selected_option(self):
        self.direction['decisions'][0]['selected'] = 'invented'
        with self.assertRaises(ValueError): self.validate()
    def test_unknown_source(self):
        self.direction['decisions'][0]['basis'] = ['invented']
        with self.assertRaises(ValueError): self.validate()
    def test_unused_source_is_not_positive_authority(self):
        self.sources[0]['disposition'] = 'considered-not-used'
        self.direction['decisions'][0]['basis'] = ['persona']
        with self.assertRaises(ValueError): self.validate()
    def test_unknown_criterion(self):
        self.direction['decisions'][0]['criteria'] = ['missing']
        with self.assertRaises(ValueError): self.validate()
    def test_unknown_dependency(self):
        self.direction['decisions'][0]['depends_on'] = ['missing']
        with self.assertRaises(ValueError): self.validate()
    def test_dependency_cycle(self):
        a = self.direction['decisions'][0]; b = decision('placement'); a['depends_on'] = ['placement']; b['depends_on'] = ['expression']
        self.direction['decisions'].append(b)
        with self.assertRaises(ValueError): self.validate()
    def test_selected_instructions_only_cross_boundary(self):
        self.direction['decisions'][0]['options'][1]['expression'] = 'PRIVATE REJECTED OPTION'
        self.direction['decisions'][0]['reason'] = 'PRIVATE AUTHOR REASON'
        text = json.dumps(plan.consumer(self.direction))
        self.assertIn('Keep the sparse field', text); self.assertNotIn('PRIVATE', text)
    def test_detailed_source_is_referenced_not_reduced_to_label(self):
        self.direction['basis'] = ['persona']; self.direction['decisions'][0]['basis'] = ['persona']
        self.validate(); self.assertEqual(self.direction['basis'], ['persona'])
    def test_deviation_has_scope_and_origin(self):
        self.direction['decisions'][0]['deviations'] = [{'source': 'persona', 'locator': 'section 4', 'scope': 'this depiction only', 'reason': 'Explicitly requested contrast.'}]
        self.validate()
    def test_deviation_unknown_origin(self):
        self.direction['decisions'][0]['deviations'] = [{'source': 'missing', 'locator': 'whole', 'scope': 'one image', 'reason': 'test'}]
        with self.assertRaises(ValueError): self.validate()
    def test_generic_nonhuman_action_relations(self):
        self.direction['action_slice'] = {'phase': 'while interlocked', 'before': 'apart', 'after': 'undetermined',
            'relations': [{'subject': 'element A', 'relation': 'supported by', 'object': 'surface B', 'note': 'No anatomical assumption.'}],
            'not_verified': ['The intervening trajectory is not observed.']}
        self.validate()
    def test_static_action_requires_honest_limit(self):
        self.direction['action_slice'] = {'phase': 'held', 'before': 'unknown', 'after': 'unknown', 'relations': [], 'not_verified': []}
        with self.assertRaises(ValueError): self.validate()
    def test_transitive_influence(self):
        a = decision(basis=['persona']); b = decision('placement'); b['depends_on'] = ['expression']
        self.direction['decisions'] = [a, b]
        affected = plan.affected({'direction': self.direction, 'criteria': self.criteria}, {'persona'})
        self.assertEqual(affected['decisions'], ['expression', 'placement'])
    def test_no_undeclared_dependency_inference(self):
        affected = plan.affected({'direction': self.direction, 'criteria': self.criteria}, {'unrelated'})
        self.assertEqual(affected['decisions'], [])


class AcceptedVariationTests(unittest.TestCase):
    def setUp(self):
        self.source_raw = b'Synthetic adopted outfit: blue fabric and a single clasp.'
        self.sources = [{'id': 'approval', 'disposition': 'applied'},
                        {'id': 'outfit', 'disposition': 'applied'}]
        self.criteria = [{'id': 'read'}]
        self.allowance = {'id': 'fabric-folds', 'source': 'approval',
                          'locator': 'wardrobe variation', 'author': 'request owner',
                          'scope': {'kind': 'source', 'source': 'outfit', 'sha256': c.digest(self.source_raw)},
                          'allowance': 'Fabric folds may follow the declared arm pose.',
                          'limits': ['Keep the blue fabric and single clasp.'], 'criteria': ['read']}
        self.choice = decision(basis=['approval', 'outfit'])
        self.choice['accepted_variations'] = [self.allowance]
        self.direction = {'purpose': 'A new pose with the adopted outfit.',
                          'intended_effect': 'An identifiable outfit in natural motion.',
                          'basis': ['approval', 'outfit'], 'decisions': [self.choice],
                          'action_slice': None, 'limitations': []}
        self.task = {'task_id': 'outfit-study', 'direction': self.direction,
                     'sources': self.sources, 'criteria': self.criteria}

    def validate(self):
        plan.validate(self.direction, self.sources, self.criteria, task_id=self.task['task_id'])
        plan.validate_variation_bindings(self.task, {'outfit': c.digest(self.source_raw)})

    def test_same_source_allowance_survives_another_work_task(self):
        self.validate()
        self.task['task_id'] = 'another-pose'
        self.validate()

    def test_task_allowance_stays_with_its_work_task(self):
        self.allowance['scope'] = {'kind': 'task', 'task_id': 'outfit-study'}
        self.validate()
        self.task['task_id'] = 'another-scene'
        with self.assertRaisesRegex(ValueError, 'different task'):
            self.validate()

    def test_changed_outfit_cannot_inherit_the_old_allowance(self):
        self.source_raw = b'Synthetic changed outfit: red fabric and two clasps.'
        with self.assertRaisesRegex(ValueError, 'source changed'):
            self.validate()

    def test_unused_approval_is_not_an_allowance(self):
        self.sources[0]['disposition'] = 'considered-not-used'
        with self.assertRaises(ValueError):
            self.validate()

    def test_allowance_cannot_relax_an_unrelated_criterion(self):
        self.allowance['criteria'] = ['identity']
        self.criteria.append({'id': 'identity'})
        with self.assertRaisesRegex(ValueError, 'criteria of its decision'):
            self.validate()

    def test_bare_global_scope_is_rejected(self):
        self.allowance['scope'] = {'kind': 'all-future-images'}
        with self.assertRaisesRegex(ValueError, 'task or source'):
            self.validate()

    def test_allowance_keeps_its_author_and_limits(self):
        self.allowance['author'] = ''
        with self.assertRaisesRegex(ValueError, 'nonempty text'):
            self.validate()

    def test_allowance_is_review_context_not_private_prompt_prose(self):
        self.validate()
        result = json.dumps(plan.consumer(self.direction))
        self.assertNotIn('request owner', result)
        self.assertNotIn('Fabric folds may follow', result)
        self.assertIn('Keep the sparse field', result)
        affected = plan.affected(self.task, {'outfit'})
        self.assertEqual(affected['criteria'], ['read'])


class EvidenceTests(unittest.TestCase):
    def test_actual_image_is_decoded(self):
        self.assertEqual(media.inspect(png(), 'image')['width'], 24)
    def test_svg_source_remains_an_image_in_observations_and_export(self):
        import artifact_review
        raw = (b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 32">'
               b'<rect width="48" height="32" fill="#5078a0"/></svg>')
        info = media.inspect(raw, 'image')
        self.assertEqual((info['width'], info['height'], info['format'], info['bytes']),
                         (48, 32, 'SVG', len(raw)))
        self.assertIn('image', media.locator(
            {'kind': 'image-region', 'x': 0.25, 'y': 0.25, 'width': 0.5, 'height': 0.5}, info, raw))
        self.assertEqual(artifact_review.attachment(raw), ('.svg', 'image'))
    def test_svg_evidence_rejects_active_external_and_invalid_content(self):
        import artifact_review
        for content in (b'<script>window.alert(1)</script>',
                        b'<image href="https://example.invalid/image.png"/>',
                        b'<rect width="20" height="20" onclick="event.stopPropagation()"/>',
                        b'<path d="M0 0L20 20">'):
            raw = b'<svg xmlns="http://www.w3.org/2000/svg" width="48" height="32">' + content + b'</svg>'
            with self.subTest(content=content):
                with self.assertRaises(ValueError):
                    media.inspect(raw, 'image')
                self.assertEqual(artifact_review.attachment(raw), ('.txt', 'text'))
    def test_image_extension_does_not_prove_an_image(self):
        with self.assertRaises(ValueError): media.inspect(b'\x89PNG-not-an-image', 'image')
    def test_json_duplicate_keys(self):
        with self.assertRaises(ValueError): media.inspect(b'{"a":1,"a":2}', 'json')
    def test_declared_binary_is_supported(self):
        self.assertEqual(media.inspect(b'\x00\xff', 'binary')['bytes'], 2)
    def test_empty_is_not_a_candidate(self):
        with self.assertRaises(ValueError): media.inspect(b'', 'binary')
    def test_normalized_image_region(self):
        raw = png(); info = media.inspect(raw, 'image')
        self.assertIn('image', media.locator({'kind':'image-region','x':0.2,'y':0.1,'width':0.5,'height':0.5}, info, raw))
    def test_outside_image_region(self):
        raw = png(); info = media.inspect(raw, 'image')
        with self.assertRaises(ValueError): media.locator({'kind':'image-region','x':0.8,'y':0,'width':0.5,'height':1}, info, raw)
    def test_nan_region(self):
        raw = png(); info = media.inspect(raw, 'image')
        with self.assertRaises(ValueError): media.locator({'kind':'image-region','x':float('nan'),'y':0,'width':1,'height':1}, info, raw)
    def test_boolean_region(self):
        raw = png(); info = media.inspect(raw, 'image')
        with self.assertRaises(ValueError): media.locator({'kind':'image-region','x':False,'y':0,'width':1,'height':1}, info, raw)
    def test_static_image_cannot_be_motion_evidence(self):
        raw = png(); info = media.inspect(raw, 'image')
        self.assertNotIn('motion', media.locator({'kind':'whole'}, info, raw))
        with self.assertRaises(ValueError): media.locator({'kind':'time','stream':0,'start_seconds':'0','end_seconds':'1'}, info, raw)
    def test_text_is_not_image_evidence(self):
        self.assertNotIn('image', media.locator({'kind':'whole'}, media.inspect(b'picture', 'text'), b'picture'))
    def test_actual_audio_stream_and_range(self):
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as output:
            output.setnchannels(1); output.setsampwidth(2); output.setframerate(8000); output.writeframes(b'\0\0' * 8000)
        raw = buffer.getvalue(); info = media.inspect(raw, 'audio')
        self.assertIn('audio', media.locator({'kind':'time','stream':0,'start_seconds':'0.25','end_seconds':'0.75'}, info, raw))
        with self.assertRaises(ValueError): media.locator({'kind':'time','stream':0,'start_seconds':'0','end_seconds':'2'}, info, raw)
    def test_unknown_stream_is_not_observed(self):
        info = {'kind':'audio','streams':[{'index':1,'kind':'audio','duration_seconds':'1'}]}
        with self.assertRaises(ValueError): media.locator({'kind':'time','stream':0,'start_seconds':'0','end_seconds':'1'}, info, b'x')
    def test_whole_video_is_not_precise_motion_evidence(self):
        self.assertNotIn('motion', media.locator({'kind':'whole'}, {'kind':'video'}, b'x'))
    def test_short_motion_range_rejected(self):
        info = {'kind':'video','streams':[{'index':0,'kind':'video','duration_seconds':'2','frame_rate':'24/1'}]}
        with self.assertRaises(ValueError): media.locator({'kind':'time','stream':0,'start_seconds':'0','end_seconds':'0.0001'}, info, b'x')
    def test_seconds_nonfinite_rejected(self):
        for value in ('NaN', 'Infinity', '-1'):
            with self.subTest(value=value), self.assertRaises(ValueError): media.seconds(value)


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        entry = ledger.begin(self.root, 'Synthetic complete production loop', ['prepare', 'deliver'])
        (self.root/'brief.md').write_bytes(b'A deliberately held abstract field. PRIVATE DOSSIER.\n')
        (self.root/'delivery.txt').write_bytes(b'Keep the sparse field.\n')
        self.task = {'task_id':entry['task_id'],'route':'development','features':[], 'execution':'external',
            'sources':[{'id':'brief','path':'brief.md','role':'design','disposition':'applied','locator':'whole','reason':'Declared fixture purpose.'}],
            'delivery':{'path':'delivery.txt','translation_notes':'Use the selected expression.'},
            'criteria':[{'id':'read','strength':'hard','text':'The intended field is observable.'}],'world_views':[]}
        fixture.task(self.root, self.task, artifact='image', execution='external')
        fixture.external_image_input(self.root, self.task)
        self.task['criteria'][0]['evidence'] = 'image'
        self.task['direction']['decisions'] = [decision(basis=['brief'])]
        self.write('task.json', self.task)
    def write(self, name, data):
        raw = data if isinstance(data, bytes) else c.encoded(data)
        (self.root/name).write_bytes(raw)
    def prepare(self):
        return w.prepare(self.root, 'task.json')['run']
    def candidate(self):
        run, _, _ = self.external_case()
        self.write('image.png', png())
        candidate = w.capture(self.root, run, 'image.png', 'Pillow-generated process fixture, not an artwork-quality test.')
        self.external_response(amount=None)
        self.receive(run, artifacts=['image.png'])
        return run, candidate
    def review_data(self, run, candidate, verdict='pass'):
        data = w.draft_review(self.root, run, candidate['sha256'])
        data.update(reviewer=fixture.ACTOR, observations=[{'evidence':'candidate',
            'locator':{'kind':'image-region','x':0,'y':0,'width':1,'height':1},
            'observation':'The decoded synthetic image is a constant field.',
            'interpretation':'The fixture can exercise a declared still-image criterion.',
            'limitations':['No personality, motion or audience response is tested.']}], conclusion='Synthetic process evidence only.')
        data['checks'][0].update(verdict=verdict, observation_indices=[0], reason='Actual fixture byte and pixel inspection.')
        return data
    def record_review(self, run, candidate, verdict='pass', name='review.json'):
        data = self.review_data(run, candidate, verdict)
        self.write(name, data); return w.review(self.root, run, name)
    def selection(self, run, candidate):
        data = w.draft_selection(self.root, run, candidate['sha256'])
        data.update(selector=fixture.ACTOR, reason='Complete the explicitly synthetic delivery.')
        fixture.selection(self.root, run, data)
        self.write('selection.json', data)
        return data
    def authority(self):
        return c.load(self.root/'fixture-authority.json')
    def test_changed_variation_source_blocks_check_and_prepare(self):
        from production_compiler import check_task, prepare_task
        from production_diagnostics import CompilationError
        import production_store as store
        self.task['direction']['decisions'][0]['accepted_variations'] = [{
            'id': 'spacing', 'source': 'brief', 'locator': 'whole', 'author': fixture.ACTOR,
            'scope': {'kind': 'source', 'source': 'brief',
                      'sha256': c.digest((self.root/'brief.md').read_bytes())},
            'allowance': 'Spacing may vary within the approved sparse field.',
            'limits': ['Preserve the sparse field.'], 'criteria': ['read']}]
        self.write('task.json', self.task)
        valid = check_task(self.root, 'task.json')
        self.assertTrue(valid['ok'], valid['diagnostics'])
        self.assertTrue(valid['publishable'])
        self.assertFalse(valid['formal_run_created'])
        self.assertEqual(store.runs(self.root), [])

        self.write('brief.md', b'A dense field with uneven spacing.\n')
        checked = check_task(self.root, 'task.json')
        self.assertEqual(store.runs(self.root), [])
        with self.assertRaises(CompilationError) as caught:
            prepare_task(self.root, 'task.json')
        for operation, report in [('check', checked), ('prepare', caught.exception.report)]:
            with self.subTest(operation=operation):
                self.assertFalse(report['ok'])
                self.assertFalse(report['publishable'])
                self.assertFalse(report['formal_run_created'])
                errors = [(row['code'], row['phase'], row['file'], row['message'])
                          for row in report['diagnostics'] if row['code'] != 'CHECK_NOT_PERFORMED']
                self.assertEqual(errors, [('INPUT_CONSISTENCY_ERROR', 'source-validation', 'task.json',
                    'accepted variation source changed; reassess its scope before reuse')])
        self.assertEqual(store.runs(self.root), [])
        self.assertEqual(list((self.root/'production/runs').glob('*/prepared.json')), [])
    def test_complete_image_lifecycle_and_ledger(self):
        run, ca = self.candidate(); self.record_review(run, ca); self.selection(run, ca)
        w.select(self.root, run, 'selection.json'); done = w.complete(self.root, run)
        self.assertEqual(done['data']['scope'], 'delivery-only')
        for number in (1,2): ledger.step_done(self.root, number)
        ledger.finish(self.root, run)
        self.assertEqual(w.status(self.root, run)['runs'][0]['task_disposition'], 'completed')
        self.assertIsNone(ledger.read_current(self.root))
    def test_selected_instructions_reach_generation_binding(self):
        run = self.prepare(); b = binding.create(self.root, run, 'Keep the sparse field.\n')
        effective = b['consumer']['instructions']
        self.assertEqual(effective, 'Keep the sparse field.\n')
        self.assertIn('quiet interval', str(b['consumer']['direction']))
        self.assertNotIn('PRIVATE', effective)
    def test_handoff_needs_its_exact_authorization(self):
        run = self.prepare()
        with self.assertRaises(ValueError): w.handoff(self.root, run, 'author', 'manual', 'a'*64)
    def test_authorization_cannot_change_recipient(self):
        run = self.prepare(); auth = fixture.grant(self.root, run, w.handoff_intent(self.root, run, 'one', 'manual'))
        with self.assertRaises(ValueError): w.handoff(self.root, run, 'two', 'manual', auth)
    def test_submit_grant_does_not_authorize_selection(self):
        run, submit_authorization, _ = self.external_case()
        self.write('image.png', png())
        ca = w.capture(self.root, run, 'image.png', 'Actual synthetic delegated image.')
        self.external_response(amount=None)
        self.receive(run, artifacts=['image.png'])
        self.record_review(run, ca)
        d = w.draft_selection(self.root, run, ca['sha256']); d.update(selector=fixture.ACTOR,reason='test')
        d['authorization'] = submit_authorization
        self.write('selection.json', d)
        with self.assertRaisesRegex(ValueError, 'AUTHORIZATION_MISMATCH'):
            w.select(self.root, run, 'selection.json')
    def test_selection_reason_cannot_change_after_authorization(self):
        run, ca = self.candidate(); self.record_review(run, ca); d = self.selection(run, ca)
        d['reason'] = 'A different decision'; self.write('selection.json', d)
        with self.assertRaises(ValueError): w.select(self.root, run, 'selection.json')
    def test_stop_condition_requires_an_explicit_assessment(self):
        a = self.authority(); a['stop_conditions'] = [{'id':'cease','text':'Stop on a changed purpose.'}]; self.write('fixture-authority.json', a)
        run = self.prepare()
        with self.assertRaises(ValueError): fixture.grant(self.root,run,w.handoff_intent(self.root,run,'author','manual'))
    def test_expired_grant(self):
        a = self.authority(); a['grants'][0]['expires_at']='2000-01-01T00:00:00Z'; self.write('fixture-authority.json',a)
        run = self.prepare()
        with self.assertRaises(ValueError): fixture.grant(self.root,run,w.handoff_intent(self.root,run,'author','manual'))
    def test_scope_not_granted(self):
        a=self.authority();a['grants'][0]['targets']=['delivery'];self.write('fixture-authority.json',a)
        run=self.prepare()
        with self.assertRaises(ValueError):fixture.grant(self.root,run,w.handoff_intent(self.root,run,'author','manual'))
    def external_case(self, count=1):
        self.task['execution'] = 'external'
        fixture.external_image_input(self.root, self.task, count=count)
        self.write('task.json', self.task)
        run = self.prepare(); fixture.handoff(self.root, run, 'synthetic external host', 'manual')
        token = fixture.grant(self.root, run, w.external_intent(self.root, run, count))
        claim = w.claim_external(self.root, run, count, token)
        return run, token, claim

    def external_response(self, *, amount='0', inline=False):
        response = {'synthetic': True, 'status': 'received',
                    'cost': None if amount is None else {'currency': 'USD', 'amount': amount}}
        if inline:
            response['result'] = {'image': 'data:image/png;base64,' + base64.b64encode(png()).decode('ascii')}
        self.write('host-response.json', response)
        return response

    def receive(self, run, *, artifacts=None, image_pointers=None, final=True):
        return w.receive_external(self.root, run, response_file='host-response.json',
            artifacts=artifacts, image_pointers=image_pointers, final=final, cost_pointer=['cost'],
            reason='Synthetic returned files; no real provider, billing or artwork-quality claim.')

    def prepared_external_case(self):
        self.task['execution'] = 'external'
        fixture.external_image_input(self.root, self.task)
        self.write('task.json', self.task)
        return self.prepare()

    def test_external_specification_peers_report_every_defect_with_their_owner(self):
        import production_spec
        import subprocess
        from production_compiler import check_task, validate_document, REPORT_SCHEMA
        from render_contract_fixtures import intent
        self.task['execution'] = 'external'
        fixture.external_image_input(self.root, self.task)
        valid = production_spec.draft(model='synthetic-external-image',
            brief='Synthetic specification for local compiler diagnostics.', subject='subject-1', kind='robot',
            render_intent=intent('Keep the sparse field.'))
        first, second = copy.deepcopy(valid), copy.deepcopy(valid)
        first['camera'] = {}
        first['subjects'][0]['performance'] = {}
        second.pop('scene')
        second['constraints'] = []
        broken = {'first-spec.json': first, 'second-spec.json': second}
        expected = {path: set(production_spec.validate(value, require_content=True)['errors'])
                    for path, value in broken.items()}
        for index, (path, value) in enumerate(broken.items()):
            self.write(path, value)
            self.task['sources'].append({'id': 'spec-' + str(index), 'path': path, 'role': 'production-spec',
                'disposition': 'applied', 'locator': 'whole', 'reason': 'Synthetic independent source contract.'})
        plan = c.load(self.root / self.task['image_input'])
        request_path = plan['external_request']['file']
        request = c.load(self.root / request_path)
        request['prompt'] = 'A different synthetic delivery.'
        self.write(request_path, request)
        self.write('task.json', self.task)
        report = check_task(self.root, 'task.json')
        validate_document(report, REPORT_SCHEMA, 'compilation report')
        self.assertFalse(report['publishable'])
        self.assertIn('PROMPT_DELIVERY_MISMATCH', {row['code'] for row in report['diagnostics']})
        for path, messages in expected.items():
            errors = [row for row in report['diagnostics'] if row['file'] == path and row['code'] == 'INPUT_SCHEMA_INVALID']
            self.assertEqual({row['message'] for row in errors}, messages)
            self.assertEqual(len(errors), len(messages))
            for row in errors:
                self.assertTrue(row['pointer'].startswith('$'))
                self.assertEqual(row['guidance']['schema'], 'protocols/shared-state/schemas/production-spec.schema.json')
                action = row['guidance']['validation']
                self.assertIn(str((self.root / path).resolve()), action['argv'])
                self.assertEqual(action['argv'][-1], '--require-content')
        camera = next(row for row in report['diagnostics'] if row['file'] == 'first-spec.json'
                      and row['pointer'] == '$.camera' and row['code'] == 'INPUT_SCHEMA_INVALID')
        self.assertTrue(camera['guidance']['document_path'].endswith('#camera-framing-contract'))
        standalone = subprocess.run(camera['guidance']['validation']['argv'], cwd=self.root,
                                    capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(standalone.returncode, 1, standalone.stderr)
        self.assertEqual(set(json.loads(standalone.stdout)['errors']), expected['first-spec.json'])

        for path in broken:
            self.write(path, valid)
        request['prompt'] = (self.root / self.task['delivery']['path']).read_bytes().decode('utf-8')
        self.write(request_path, request)
        with patch.object(production_spec, 'require', wraps=production_spec.require) as require:
            corrected = check_task(self.root, 'task.json')
        self.assertTrue(corrected['publishable'], corrected['diagnostics'])
        self.assertEqual(require.call_count, len(broken))
        self.assertFalse(corrected['formal_run_created'])

    def test_prompt_newline_diagnostic_names_both_files_and_keeps_exact_comparison(self):
        from production_compiler import check_task
        prompt = 'Keep the sparse field near the caf\u00e9.\n'
        self.write('delivery.txt', prompt.encode('utf-8'))
        self.task['execution'] = 'external'
        fixture.external_image_input(self.root, self.task)
        self.write('task.json', self.task)
        self.write('delivery.txt', prompt.replace('\n', '\r\n').encode('utf-8'))
        report = check_task(self.root, 'task.json')
        error = next(row for row in report['diagnostics'] if row['code'] == 'PROMPT_DELIVERY_MISMATCH')
        plan = c.load(self.root / self.task['image_input'])
        self.assertEqual((error['file'], error['pointer'], error['delivery_file']),
                         (plan['external_request']['file'], '$["prompt"]', 'delivery.txt'))
        self.assertEqual(error['request_newlines'], {'crlf': 0, 'lf': 1, 'cr': 0})
        self.assertEqual(error['delivery_newlines'], {'crlf': 1, 'lf': 0, 'cr': 0})
        self.assertTrue(error['newline_only_difference'])
        self.assertIn('build-inputs', error['required_action'])
        self.assertIn('CRLF', error['required_action'])
        self.write('delivery.txt', prompt.encode('utf-8'))
        corrected = check_task(self.root, 'task.json')
        self.assertTrue(corrected['publishable'], corrected['diagnostics'])

    def test_unified_external_execution_receives_and_reviews_one_claimed_request(self):
        import execution_lifecycle as life
        import production_case_fixtures as cases
        import production_execution as execution
        import production_workspace
        from production_diagnostics import ProductionError
        run = self.prepared_external_case()
        input_view = production_workspace.workspace(self.root, run, phase='input')
        decisions_file = cases.fill_decisions(self.root, run, 'execution-decisions.json')
        choices = c.load(self.root / decisions_file)
        direction, submit = choices['decisions']
        direction['reason'] = 'Synthetic direction decision for the declared abstract-field depiction.'
        submit['reason'] = 'Synthetic submission decision for one exact host request.'
        self.write(decisions_file, choices)
        result = execution.execute(self.root, run, decisions_file=decisions_file)
        self.assertEqual(result['state'], 'host-call-required')
        self.assertFalse(result['external_effect'])
        call = result['host_request']
        self.write('prepared-host-instruction.json', result)
        from image_input import submission_evidence
        instruction = {'path': 'prepared-host-instruction.json',
            'sha256': c.sha256_file(self.root / 'prepared-host-instruction.json'),
            'locator': 'generated instruction', 'request_pointer': ['host_request', 'request'],
            'model_identity_pointer': None}
        with self.assertRaisesRegex(ValueError, 'prepared host instruction'):
            submission_evidence(w.load_run(self.root, run)[2]['image_input'], instruction,
                                lambda path: (self.root / path).read_bytes())
        self.assertEqual(call['request'], input_view['prepared_input']['request'])
        rows = w.load_run(self.root, run)[3]
        authorizations = [row for row in rows if row['event'] == 'authorization']
        self.assertEqual([row['data']['request']['operation'] for row in authorizations], ['direction', 'submit'])
        self.assertEqual([row['data']['request']['reason'] for row in authorizations],
                         [direction['reason'], submit['reason']])
        self.assertEqual([row['data']['request']['actor'] for row in authorizations], [fixture.ACTOR] * 2)
        for row in authorizations:
            self.assertIn(c.sha256_file(self.root / decisions_file),
                          [item['sha256'] for item in row['data']['files']])
        handoff = w.find(rows, 'handoff')
        claim = w.find(rows, 'external-claim')
        self.assertEqual(handoff['data']['authorizations'], [authorizations[0]['sha256']])
        self.assertEqual(claim['data']['authorizations'], [authorizations[1]['sha256']])
        self.assertEqual(claim['sha256'], call['claim'])
        self.assertLess(rows.index(handoff), rows.index(claim))
        self.assertEqual(life.summary(self.root, run=run)['submissions'], 1)
        before_repeat = copy.deepcopy(rows)
        with self.assertRaises(ProductionError) as caught:
            execution.execute(self.root, run, decisions_file=decisions_file)
        self.assertEqual(caught.exception.diagnostic.code, 'DISPATCH_ALREADY_CLAIMED')
        self.assertEqual(w.load_run(self.root, run)[3], before_repeat)
        status = execution.status(self.root, run)['runs'][0]
        self.assertEqual(status['next_action']['command'], 'receive-external')

        # This local synthetic host observation is distinct from the prepared handoff.
        self.write('observed-host-call.json', {'synthetic': True, 'call_id': 'local-fixture-call',
                                             'arguments': copy.deepcopy(call['request'])})
        self.external_response(inline=True)
        received = w.receive_external(self.root, run, response_file='host-response.json',
            image_pointers=[['result', 'image']], submission_file='observed-host-call.json',
            request_pointer=['arguments'], final=True,
            reason='Synthetic host observation returned the local constant-field PNG.')
        self.assertTrue(received['execution_completed'])
        self.assertEqual(received['request_evidence']['status'], 'matched-recorded-call')
        self.assertEqual(life.summary(self.root, run=run)['submissions'], 1)
        candidate = received['candidates'][0]
        observed = production_workspace.workspace(self.root, run, phase='observe', candidate=candidate)
        self.assertEqual(set(observed), {'phase', 'run', 'candidate', 'instruction'})
        saved = Path(observed['candidate']['files'][0]['path'])
        self.assertEqual(saved.read_bytes(), png())
        review_view = production_workspace.workspace(self.root, run, phase='review', candidate=candidate)
        self.assertEqual(review_view['candidate'], observed['candidate'])
        self.assertEqual(review_view['prepared_input'], input_view['prepared_input'])
        self.assertEqual(review_view['basis']['criteria'][0]['id'], 'read')
        rows = w.load_run(self.root, run)[3]
        self.assertFalse(any(row['event'] == 'review' for row in rows))
        draft = w.draft_review(self.root, run, candidate)
        self.assertEqual(draft['observations'], [])
        self.assertEqual(draft['checks'][0]['verdict'], 'not-assessed')
        recorded = self.record_review(run, w.find(rows, 'candidate', candidate))
        self.assertEqual(recorded['data']['review']['checks'][0]['verdict'], 'pass')

    def test_unified_external_decisions_are_atomic_when_meaning_or_direction_is_unresolved(self):
        import production_case_fixtures as cases
        import production_execution as execution
        import execution_lifecycle as life
        run = self.prepared_external_case()
        path = cases.fill_decisions(self.root, run, 'execution-decisions.json')
        complete = c.load(self.root / path)
        for defect in ('missing-direction', 'unfilled-rendition'):
            with self.subTest(defect=defect):
                choices = copy.deepcopy(complete)
                if defect == 'missing-direction':
                    choices['decisions'] = [item for item in choices['decisions'] if item['operation'] != 'direction']
                else:
                    submit = next(item for item in choices['decisions'] if item['operation'] == 'submit')
                    submit['request_decision']['rendition_review']['assessments'][0].update(conclusion=None, reason='')
                self.write(path, choices)
                with self.assertRaises(ValueError):
                    execution.execute(self.root, run, decisions_file=path)
                self.assertEqual(w.load_run(self.root, run)[3], [])
                self.assertEqual(life.all_states(self.root, run=run), [])

    def test_external_claim_protects_unknown_result_records_and_logs(self):
        import operation_context as ops
        import execution_lifecycle as life
        from test_production_operations import OperationTests
        run, token, claim = self.external_case()
        prepared, rows = w.load_run(self.root, run)[1::2]
        state = life.by_authorization(rows, prepared, run, token)
        self.assertEqual(len(state['steps']), 1)
        self.assertEqual(state['steps'][0]['operation'], 'send')
        self.assertEqual(state['status'],'started')
        self.assertTrue(ops._run_has_unresolved_external_effect(self.root, run))
        folder = OperationTests._fake_operation(self, self.root, 'external-host-diagnostics', run=run)
        result = ops.cleanup_logs(self.root, operation_id=folder.name, apply=True)
        self.assertEqual(result['deleted'], [])
        self.assertTrue(folder.is_dir())
        from production_execution import status
        report = status(self.root, run)['runs'][0]
        self.assertEqual(report['submission'], 'outcome_unknown')
        self.assertEqual(w.claim_external(self.root, run, 1, token)['sha256'], claim['sha256'])
        self.assertEqual(len(life.by_authorization(w.load_run(self.root, run)[3], prepared, run, token)['steps']), 1)

    def test_external_boundary_failure_rolls_back_execution_claim(self):
        import execution_lifecycle as life
        self.task['execution'] = 'external'
        fixture.external_image_input(self.root, self.task)
        self.write('task.json', self.task)
        run = self.prepare(); fixture.handoff(self.root, run, 'synthetic host', 'manual')
        token = fixture.grant(self.root, run, w.external_intent(self.root, run, 1))
        with patch.object(life, 'begin_step', side_effect=OSError('Synthetic durable boundary failure')):
            with self.assertRaises(OSError): w.claim_external(self.root, run, 1, token)
        prepared, rows = w.load_run(self.root, run)[1::2]
        self.assertFalse(any(row['event'] == 'external-claim' for row in rows))
        self.assertEqual(life.derive(rows, prepared, run), {})

    def test_external_result_capture_survives_source_deletion_and_is_idempotent(self):
        run, token, claim = self.external_case()
        (self.root/'brief.md').unlink(); (self.root/'fixture-authority-basis.txt').unlink()
        self.write('external.png', png())
        first = w.capture(self.root, run, 'external.png', 'Synthetic received image.')
        self.assertEqual(w.capture(self.root, run, 'external.png', 'Repeated receipt of the same result.')['sha256'], first['sha256'])
        self.assertEqual(len([row for row in w.load_run(self.root, run)[3] if row['event'] == 'candidate']), 1)

    def test_external_result_cannot_replace_an_already_counted_path(self):
        run, _, _ = self.external_case()
        self.write('external.png', png()); w.capture(self.root, run, 'external.png', 'First actual result.')
        self.write('external.png', png(128))
        with self.assertRaisesRegex(ValueError, 'output count'):
            w.capture(self.root, run, 'external.png', 'Different bytes at the same path.')

    def test_external_settlement_is_evidenced_idempotent_and_releases_diagnostic_protection(self):
        import operation_context as ops
        import execution_lifecycle as life
        from production_execution import status
        run, token, claim = self.external_case()
        self.write('external.png', png())
        self.external_response()
        first = self.receive(run, artifacts=['external.png'])
        second = self.receive(run, artifacts=['external.png'])
        self.assertTrue(first['recorded']); self.assertTrue(first['execution_completed'])
        self.assertEqual(first['receipt']['sha256'], second['receipt']['sha256'])
        self.assertFalse(ops._run_has_unresolved_external_effect(self.root, run))
        state = life.by_authorization(w.load_run(self.root, run)[3], w.load_run(self.root, run)[1], run, token)
        self.assertEqual(state['submissions'], 1); self.assertEqual(state['captured_outputs'], 1)
        self.assertEqual(status(self.root, run)['runs'][0]['capture'], 'complete')
        rows = w.load_run(self.root, run)[3]
        self.assertLess(next(i for i, row in enumerate(rows) if row['event'] == 'candidate'),
                        next(i for i, row in enumerate(rows) if row['event'] == 'execution-result'))
        self.assertFalse(any(row['event'] in {'review', 'selection', 'adoption-result'} for row in rows))

    def test_external_completion_does_not_require_reported_price(self):
        import operation_context as ops
        import execution_lifecycle as life
        run, token, claim = self.external_case()
        self.write('external.png', png())
        self.external_response(amount=None)
        result = self.receive(run, artifacts=['external.png'])
        self.assertTrue(result['recorded'])
        self.assertTrue(result['execution_completed'])
        self.assertFalse(ops._run_has_unresolved_external_effect(self.root, run))
        self.assertFalse(life.summary(self.root, run=run)['usage_complete'])

    def test_external_receipt_derives_claim_actor_count_and_hashes(self):
        run, token, claim = self.external_case()
        self.external_response(inline=True)
        result = self.receive(run, image_pointers=[['result', 'image']])
        receipt = c.load(self.root / result['receipt_file'])
        self.assertEqual((receipt['claim'], receipt['actor'], receipt['outputs']),
                         (claim['sha256'], fixture.ACTOR, 1))
        self.assertEqual(receipt['response']['sha256'], c.sha256_file(self.root / 'host-response.json'))
        candidate = w.find(w.load_run(self.root, run)[3], 'candidate', result['candidates'][0])
        self.assertEqual(candidate['data']['files'][0]['sha256'], c.digest(png()))
        self.assertEqual((candidate['data']['media']['width'], candidate['data']['media']['height']), (24, 16))

    def test_external_receive_recovers_partial_capture_without_sending(self):
        import execution_lifecycle as life
        run, token, claim = self.external_case(count=2)
        self.external_response()
        self.write('first.png', png())
        self.write('second.png', b'incomplete image')
        with self.assertRaises(ValueError):
            self.receive(run, artifacts=['first.png', 'second.png'])
        rows = w.load_run(self.root, run)[3]
        self.assertEqual(len([row for row in rows if row['event'] == 'candidate']), 1)
        self.assertFalse(any(row['event'] == 'execution-result' for row in rows))
        self.write('second.png', png(128))
        result = self.receive(run, artifacts=['first.png', 'second.png'])
        self.assertTrue(result['execution_completed'])
        self.assertEqual(len(result['candidates']), 2)
        self.assertEqual(life.summary(self.root, run=run)['submissions'], 1)

    def test_external_receive_recovers_failed_settlement_from_saved_results(self):
        import production_external
        import execution_lifecycle as life
        run, token, claim = self.external_case()
        self.external_response(inline=True)
        with patch.object(production_external.lifecycle, 'record_result', side_effect=OSError('Synthetic interrupted result write')):
            with self.assertRaises(OSError):
                self.receive(run, image_pointers=[['result', 'image']])
        (self.root / 'brief.md').unlink()
        (self.root / 'fixture-authority-basis.txt').unlink()
        result = self.receive(run, image_pointers=[['result', 'image']])
        self.assertTrue(result['execution_completed'])
        self.assertEqual(len(result['candidates']), 1)
        self.assertEqual(life.summary(self.root, run=run)['submissions'], 1)

    def test_external_inline_selector_decodes_actual_images_only(self):
        run, token, claim = self.external_case()
        for value in ('https://example.invalid/result.png', 'data:text/plain;base64,SGVsbG8=',
                      base64.b64encode(b'not an image').decode('ascii')):
            with self.subTest(value=value):
                self.write('host-response.json', {'result': value, 'cost': None})
                with self.assertRaises(ValueError):
                    self.receive(run, image_pointers=[['result']])
        self.assertFalse(any(row['event'] == 'candidate' for row in w.load_run(self.root, run)[3]))

    def test_external_pending_response_can_be_completed_with_actual_result(self):
        run, token, claim = self.external_case()
        self.external_response(amount=None)
        pending = self.receive(run, final=False)
        self.assertFalse(pending['recorded'])
        self.assertFalse(pending['execution_completed'])
        self.external_response(amount=None, inline=True)
        final = self.receive(run, image_pointers=[['result', 'image']])
        self.assertTrue(final['execution_completed'])

    def test_external_receive_compares_actual_call_without_discarding_pixels(self):
        run, token, claim = self.external_case()
        self.external_response(amount=None)
        self.write('external.png', png())
        input_plan = c.load(self.root / self.task['image_input'])
        request_file = input_plan['external_request']['file']
        arguments = c.load(self.root / request_file)
        self.write('host-call.json', {'synthetic': True, 'arguments': {**arguments, 'prompt': 'different input'}})
        options = {'response_file': 'host-response.json', 'artifacts': ['external.png'],
                   'final': True, 'reason': 'Synthetic recorded host call and locally received image.'}
        with self.assertRaisesRegex(ValueError, 'recorded external call differs'):
            w.receive_external(self.root, run, **options, submission_file='host-call.json', request_pointer=['arguments'])
        rows = w.load_run(self.root, run)[3]
        self.assertEqual(len([row for row in rows if row['event'] == 'candidate']), 1)
        self.assertFalse(any(row['event'] == 'execution-result' for row in rows))
        with self.assertRaisesRegex(ValueError, 'prepared request is not evidence'):
            w.receive_external(self.root, run, **options, submission_file=request_file, request_pointer=[])
        self.write('host-call.json', {'synthetic': True, 'arguments': arguments})
        result = w.receive_external(self.root, run, **options,
            submission_file='host-call.json', request_pointer=['arguments'])
        self.assertTrue(result['execution_completed'])
        self.assertEqual(result['request_evidence']['status'], 'matched-recorded-call')

    def test_external_receive_requires_prior_claim(self):
        self.task['execution'] = 'external'
        fixture.external_image_input(self.root, self.task)
        self.write('task.json', self.task)
        run = self.prepare()
        fixture.handoff(self.root, run, 'synthetic host', 'manual')
        self.external_response(inline=True)
        with self.assertRaisesRegex(ValueError, 'missing external-claim'):
            self.receive(run, image_pointers=[['result', 'image']])
        self.assertFalse(any(row['event'] == 'candidate' for row in w.load_run(self.root, run)[3]))

    def test_external_outputs_are_capped(self):
        self.task['execution']='external'
        fixture.external_image_input(self.root,self.task)
        self.write('task.json',self.task)
        run=self.prepare();fixture.handoff(self.root,run,'test host','manual')
        intent=w.external_intent(self.root,run,1);authorization=fixture.grant(self.root,run,intent)
        w.claim_external(self.root,run,1,authorization)
        self.write('first.png',png());w.capture(self.root,run,'first.png','Synthetic first result')
        self.write('second.png',png(128))
        with self.assertRaises(ValueError):w.capture(self.root,run,'second.png','Unapproved extra result')
    def test_external_capture_requires_prior_claim(self):
        self.task['execution']='external'
        fixture.external_image_input(self.root,self.task)
        self.write('task.json',self.task)
        run=self.prepare();fixture.handoff(self.root,run,'test host','manual');self.write('first.png',png())
        with self.assertRaises(ValueError):w.capture(self.root,run,'first.png','Unclaimed result')
    def test_static_candidate_cannot_pass_motion(self):
        self.task['criteria'][0]['evidence']='motion';self.write('task.json',self.task)
        run,ca=self.candidate();d=self.review_data(run,ca);self.write('review.json',d)
        with self.assertRaises(ValueError):w.review(self.root,run,'review.json')
    def test_two_static_images_still_cannot_pass_motion(self):
        self.task['criteria'][0]['evidence']='motion';self.write('task.json',self.task)
        run,ca=self.candidate();self.write('second.png',png(128));d=self.review_data(run,ca)
        d['evidence']=[{'id':'after','path':'second.png','kind':'image','relation':'Another static pose.','limitations':['Trajectory is not observed.']}]
        d['observations'].append({**d['observations'][0],'evidence':'after'})
        d['checks'][0]['observation_indices']=[0,1];self.write('review.json',d)
        with self.assertRaises(ValueError):w.review(self.root,run,'review.json')
    def test_unassessed_motion_is_not_silently_passed(self):
        self.task['criteria'][0].update(evidence='motion',strength='advisory');self.write('task.json',self.task)
        run,ca=self.candidate();d=self.review_data(run,ca);d['checks'][0].update(verdict='not-assessed',observation_indices=[],reason='No temporal evidence available.')
        self.write('review.json',d);w.review(self.root,run,'review.json')
    def test_hard_unassessed_blocks_selection(self):
        run,ca=self.candidate();d=self.review_data(run,ca);d['checks'][0].update(verdict='not-assessed',observation_indices=[],reason='Not inspected.')
        self.write('review.json',d);w.review(self.root,run,'review.json');self.selection(run,ca)
        with self.assertRaises(ValueError):w.select(self.root,run,'selection.json')
    def test_new_failed_review_invalidates_selection_and_status(self):
        run,ca=self.candidate();self.record_review(run,ca);self.selection(run,ca);w.select(self.root,run,'selection.json')
        failed=self.review_data(run,ca,'fail');failed['unresolved']=['The new observed defect needs a correction decision.']
        self.write('second-review.json',failed);w.review(self.root,run,'second-review.json')
        with self.assertRaises(ValueError):w.complete(self.root,run)
        self.assertEqual(w.status(self.root,run)['runs'][0]['next_action']['command'],'draft-selection')
    def test_changed_source_reports_declared_impact(self):
        run=self.prepare();(self.root/'brief.md').write_text('Changed purpose.', encoding='utf-8')
        result=w.impact(self.root,run)
        self.assertFalse(result['ok']);self.assertEqual(result['affected']['decisions'],['expression']);self.assertIn('read',result['affected']['criteria'])
    def test_impact_does_not_rewrite_state(self):
        run=self.prepare();folder=w.run_dir(self.root,run)
        before={p.relative_to(folder).as_posix():p.read_bytes() for p in folder.rglob('*') if p.is_file()}
        w.impact(self.root,run);w.status(self.root,run)
        after={p.relative_to(folder).as_posix():p.read_bytes() for p in folder.rglob('*') if p.is_file()}
        self.assertEqual(before,after)
    def test_changed_candidate_cannot_reuse_review(self):
        run,ca=self.candidate();self.record_review(run,ca);self.write('image.png',png(128))
        self.assertEqual(w.draft_selection(self.root,run,ca['sha256'])['candidate'],ca['sha256'])
        # The external original may change, but the captured formal bytes may not.
        stored=w.run_dir(self.root,run)/'objects'/ca['data']['files'][0]['sha256']
        stored.write_bytes(png(128))
        with self.assertRaises(ValueError):w.draft_selection(self.root,run,ca['sha256'])
    def test_revision_links_observation_to_new_preparation(self):
        run,ca=self.candidate();d=self.review_data(run,ca,'fail')
        d['repairs']=[{'id':'spacing','decisions':['expression'],'observation_indices':[0],
                       'operation':'Adjust only the local composition.', 'targets':['delivery','decision:expression'], 'reason':'The fixture requires a different spacing.'}]
        self.write('review.json',d);w.review(self.root,run,'review.json')
        revised=copy.deepcopy(self.task);revised['direction']['decisions'][0]['selected']='shift'
        revised['delivery']['path']='revised-delivery.txt';(self.root/'revised-delivery.txt').write_text('Use the intended spacing.', encoding='utf-8')
        fixture.external_image_input(self.root, revised)
        self.write('revised-task.json',revised)
        intent=w.revision_intent(self.root,run,'revised-task.json',ca['sha256'],'spacing')
        authorization=fixture.grant(self.root,run,intent)
        child=w.revise(self.root,run,'revised-task.json',ca['sha256'],'spacing',authorization)
        prepared=w.load_run(self.root,child['run'])[1]
        self.assertEqual(prepared['parent']['candidate'],ca['sha256']);self.assertEqual(prepared['parent']['repair'],'spacing')
        self.assertNotEqual(child['run'],run);self.assertIsNone(next(r for r in w.load_run(self.root,run)[3] if r['event']=='review')['data']['review'].get('approved'))
        fixture.handoff(self.root,child['run'],'synthetic author','manual')
        token=fixture.grant(self.root,child['run'],w.external_intent(self.root,child['run'],1))
        w.claim_external(self.root,child['run'],1,token)
        self.write('revised.png',png(128));child_ca=w.capture(self.root,child['run'],'revised.png','Synthetic repaired result.')
        self.external_response(amount=None);self.receive(child['run'],artifacts=['revised.png'])
        self.record_review(child['run'],child_ca,name='revised-review.json');self.selection(child['run'],child_ca)
        w.select(self.root,child['run'],'selection.json');w.complete(self.root,child['run'])
        self.assertEqual(w.status(self.root,child['run'])['runs'][0]['task_disposition'],'completed')
    def test_declared_output_kind_is_not_inferred_from_extension(self):
        run=self.prepare();fixture.handoff(self.root,run,'synthetic author','manual');self.write('image.png',b'not pixels')
        with self.assertRaises(ValueError):w.capture(self.root,run,'image.png','Invalid synthetic candidate')


    def revised_input(self, run, ca, targets=None):
        data = self.review_data(run, ca, 'fail')
        data['repairs'] = [{'id': 'repair', 'decisions': ['expression'], 'observation_indices': [0],
                            'operation': 'Change the selected local expression.',
                            'targets': targets or ['delivery', 'decision:expression'], 'reason': 'Actual fixture review.'}]
        self.write('repair-review.json', data); w.review(self.root, run, 'repair-review.json')
        revised = copy.deepcopy(self.task)
        revised['direction']['decisions'][0]['selected'] = 'shift'
        revised['delivery']['path'] = 'new-delivery.txt'
        (self.root / 'new-delivery.txt').write_text('Use the intended spacing.', encoding='utf-8')
        fixture.external_image_input(self.root, revised)
        self.write('new-task.json', revised)
        return revised
    def test_repair_cannot_hide_a_changed_decision(self):
        run, ca = self.candidate(); self.revised_input(run, ca, ['delivery'])
        with self.assertRaisesRegex(ValueError, 'reviewed scope'):
            w.revision_intent(self.root, run, 'new-task.json', ca['sha256'], 'repair')
    def test_repair_cannot_hide_a_changed_source(self):
        run, ca = self.candidate(); self.revised_input(run, ca)
        (self.root / 'brief.md').write_text('An unrelated replacement purpose.', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'reviewed scope'):
            w.revision_intent(self.root, run, 'new-task.json', ca['sha256'], 'repair')
    def test_in_place_delivery_revision_is_authorizable(self):
        run, ca = self.candidate(); revised = self.revised_input(run, ca)
        revised['delivery']['path'] = 'delivery.txt'; self.write('new-task.json', revised)
        (self.root / 'delivery.txt').write_text('Use the intended spacing.', encoding='utf-8')
        intent = w.revision_intent(self.root, run, 'new-task.json', ca['sha256'], 'repair')
        authorization = fixture.grant(self.root, run, intent)
        child = w.revise(self.root, run, 'new-task.json', ca['sha256'], 'repair', authorization)
        self.assertNotEqual(child['run'], run)
    def test_grant_explanation_update_does_not_change_reviewed_repair(self):
        run, ca = self.candidate(); self.revised_input(run, ca)
        intent = w.revision_intent(self.root, run, 'new-task.json', ca['sha256'], 'repair')
        authorization = fixture.grant(self.root, run, intent)
        import production_store as store
        authority = self.authority()
        authority['grants'][0]['expires_at'] = '2099-01-01T00:00:00Z'
        self.write('amended-authority.json', authority)
        prior = store.authority_record(self.root, self.task['task_id'])
        store.import_authority(self.root, 'amended-authority.json', expected=prior['sha256'])
        after = w.revision_intent(self.root, run, 'new-task.json', ca['sha256'], 'repair')
        self.assertEqual(after, intent)
        self.assertNotIn('authority', after['targets'])
        child = w.revise(self.root, run, 'new-task.json', ca['sha256'], 'repair', authorization)
        self.assertNotEqual(child['run'], run)

    def test_grant_update_alone_is_not_a_creative_repair(self):
        run, ca = self.candidate(); self.revised_input(run, ca)
        self.write('unchanged-task.json', self.task)
        import production_store as store
        authority = self.authority(); authority['grants'][0]['expires_at'] = '2099-01-01T00:00:00Z'
        self.write('amended-authority.json', authority)
        prior = store.authority_record(self.root, self.task['task_id'])
        store.import_authority(self.root, 'amended-authority.json', expected=prior['sha256'])
        with self.assertRaisesRegex(ValueError, 'no changed production inputs'):
            w.revision_intent(self.root, run, 'unchanged-task.json', ca['sha256'], 'repair')

    def test_creative_scopes_do_not_require_authority_documents(self):
        run = self.prepare()
        before = w.load_run(self.root, run)[1]
        after = copy.deepcopy(before)
        before['authority'] = after['authority'] = None
        before['task']['authority'] = after['task']['authority'] = None
        self.assertEqual(w.changed_scopes(before, after), [])

    def test_revoked_authority_cannot_authorize_an_edit(self):
        run, ca = self.candidate(); self.revised_input(run, ca)
        intent = w.revision_intent(self.root, run, 'new-task.json', ca['sha256'], 'repair')
        authority = self.authority(); authority['grants'] = []; self.write('fixture-authority.json', authority)
        import production_store as store
        prior=store.authority_record(self.root,self.task['task_id'])
        store.import_authority(self.root,'fixture-authority.json',expected=prior['sha256'])
        with self.assertRaisesRegex(ValueError, 'grant|GRANT_REVOKED'):
            fixture.grant(self.root, run, intent)
    def test_revoked_authority_cannot_execute_claimed_edit(self):
        run, ca = self.candidate(); self.revised_input(run, ca)
        intent = w.revision_intent(self.root, run, 'new-task.json', ca['sha256'], 'repair')
        auth = fixture.grant(self.root, run, intent)
        import production_store as store
        authority=self.authority();authority['grants'][0]['revoked_at']='2000-01-01T00:00:00Z'
        self.write('fixture-authority.json',authority)
        prior=store.authority_record(self.root,self.task['task_id'])
        store.import_authority(self.root,'fixture-authority.json',expected=prior['sha256'])
        with self.assertRaisesRegex(ValueError, 'GRANT_REVOKED'):
            w.revise(self.root, run, 'new-task.json', ca['sha256'], 'repair', auth)
    def test_empty_criteria_cannot_create_vacuous_completion(self):
        self.task['criteria'] = []; self.task['direction']['decisions'] = []; self.write('task.json', self.task)
        with self.assertRaises(ValueError): self.prepare()
    def test_private_consumer_fields_rejected_even_if_rehashed(self):
        run = self.prepare(); b = binding.create(self.root, run, 'Keep the sparse field.\n')
        b['consumer']['direction']['private_dossier'] = 'SECRET'
        b['consumer_sha256'] = c.content_id(b['consumer'])
        b['sha256'] = c.content_id({k:v for k,v in b.items() if k != 'sha256'})
        with self.assertRaises(ValueError): binding.validate(b, 'Keep the sparse field.\n')


class SubmissionCountTests(unittest.TestCase):
    def setUp(self):
        self.authority = {'task_id': 'fixture', 'issuer': 'fixture', 'evidence': {'path': 'a', 'locator': 'whole'},
            'grants': [{'id': 'grant', 'actor': 'actor', 'mode': 'delegated', 'operations': ['submit'],
                'targets': ['delivery'], 'protected_criteria': [], 'expires_at': None,
                'request_scope': None, 'submission_validation_modes': ['target-schema']}], 'stop_conditions': []}
        self.request = {'grant': 'grant', 'actor': 'actor', 'operation': 'submit', 'targets': ['delivery'],
            'payload': {'count': 1}, 'outputs': 1, 'stop_assessments': [], 'reason': 'Synthetic exact count.'}

    def test_count_mismatch(self):
        self.request['payload']['count'] = 2
        with self.assertRaises(ValueError):
            permissions.check(self.authority, self.request)

    def test_boolean_count_rejected(self):
        self.request['outputs'] = True
        with self.assertRaises(ValueError):
            permissions.check(self.authority, self.request)

    def test_exact_count_is_permission_not_consumption(self):
        self.assertEqual(permissions.check(self.authority, self.request)['id'], 'grant')




if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main(verbosity=2)
