#!/usr/bin/env python3
"""Production-loop regressions on real bytes and explicit synthetic decisions."""
from __future__ import annotations

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


class EvidenceTests(unittest.TestCase):
    def test_actual_image_is_decoded(self):
        self.assertEqual(media.inspect(png(), 'image')['width'], 24)
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
        (self.root/'brief.md').write_text('A deliberately held abstract field. PRIVATE DOSSIER.\n')
        (self.root/'delivery.txt').write_text('Keep the sparse field.\n')
        self.task = {'task_id':entry['task_id'],'route':'development','features':[],
            'sources':[{'id':'brief','path':'brief.md','role':'design','disposition':'applied','locator':'whole','reason':'Declared fixture purpose.'}],
            'delivery':{'path':'delivery.txt','transport':'authored-rendition','translation_notes':'Use the selected expression.'},
            'criteria':[{'id':'read','strength':'hard','text':'The intended field is observable.'}],'world_views':[]}
        fixture.task(self.root, self.task, artifact='image')
        self.task['criteria'][0]['evidence'] = 'image'
        self.task['direction']['decisions'] = [decision(basis=['brief'])]
        self.write('task.json', self.task)
    def write(self, name, data):
        raw = data if isinstance(data, bytes) else c.encoded(data)
        (self.root/name).write_bytes(raw)
    def prepare(self):
        return w.prepare(self.root, 'task.json')['run']
    def candidate(self):
        run = self.prepare(); fixture.handoff(self.root, run, 'synthetic author', 'manual')
        self.write('image.png', png())
        return run, w.capture(self.root, run, 'image.png', 'Pillow-generated process fixture, not an artwork-quality test.')
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
    def test_complete_image_lifecycle_and_ledger(self):
        run, ca = self.candidate(); self.record_review(run, ca); self.selection(run, ca)
        w.select(self.root, run, 'selection.json'); done = w.complete(self.root, run)
        self.assertEqual(done['data']['scope'], 'delivery-only')
        for number in (1,2): ledger.step_done(self.root, number)
        ledger.finish(self.root)
        self.assertEqual(w.status(self.root, run)['next'], 'done')
        self.assertIsNone(ledger.read_current(self.root))
    def test_selected_instructions_reach_generation_binding(self):
        run = self.prepare(); b = binding.create(self.root, run, 'Keep the sparse field.')
        effective = binding.effective(b, 'Keep the sparse field.')
        self.assertIn('quiet interval', effective); self.assertNotIn('PRIVATE', effective)
        self.assertNotIn('placement change alters', effective)
    def test_handoff_needs_its_exact_authorization(self):
        run = self.prepare()
        with self.assertRaises(ValueError): w.handoff(self.root, run, 'author', 'manual', 'a'*64)
    def test_authorization_cannot_change_recipient(self):
        run = self.prepare(); auth = fixture.grant(self.root, run, w.handoff_intent(self.root, run, 'one', 'manual'))
        with self.assertRaises(ValueError): w.handoff(self.root, run, 'two', 'manual', auth)
    def test_submit_grant_does_not_authorize_selection(self):
        run, ca = self.candidate(); self.record_review(run, ca)
        d = w.draft_selection(self.root, run, ca['sha256']); d.update(selector=fixture.ACTOR,reason='test')
        intent = {'operation':'submit','targets':['delivery'],'payload':{'count':1}}
        d['authorization'] = fixture.grant(self.root, run, intent)
        self.write('selection.json', d)
        with self.assertRaises(ValueError): w.select(self.root, run, 'selection.json')
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
    def test_grant_uses_survive_repreparation(self):
        a=self.authority();a['grants'][0]['limits']['uses']=1;self.write('fixture-authority.json',a)
        run=self.prepare();fixture.grant(self.root,run,w.handoff_intent(self.root,run,'author','manual'))
        other=self.prepare()
        with self.assertRaises(ValueError):fixture.grant(self.root,other,w.handoff_intent(self.root,other,'author','manual'))
    def test_external_outputs_are_capped(self):
        self.task['execution']='external';self.write('task.json',self.task)
        run=self.prepare();fixture.handoff(self.root,run,'test host','manual')
        intent=w.external_intent(self.root,run,1);authorization=fixture.grant(self.root,run,intent)
        w.claim_external(self.root,run,1,authorization)
        self.write('first.png',png());w.capture(self.root,run,'first.png','Synthetic first result')
        self.write('second.png',png(128))
        with self.assertRaises(ValueError):w.capture(self.root,run,'second.png','Unapproved extra result')
    def test_external_capture_requires_prior_claim(self):
        self.task['execution']='external';self.write('task.json',self.task)
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
        self.assertEqual(w.status(self.root,run)['next'],'review-or-revise-candidate')
    def test_changed_source_reports_declared_impact(self):
        run=self.prepare();(self.root/'brief.md').write_text('Changed purpose.')
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
        with self.assertRaises(ValueError):w.draft_selection(self.root,run,ca['sha256'])
    def test_revision_links_observation_to_new_preparation(self):
        run,ca=self.candidate();d=self.review_data(run,ca,'fail')
        d['repairs']=[{'id':'spacing','decisions':['expression'],'observation_indices':[0],
                       'operation':'Adjust only the local composition.', 'targets':['delivery','decision:expression'], 'reason':'The fixture requires a different spacing.'}]
        self.write('review.json',d);w.review(self.root,run,'review.json')
        revised=copy.deepcopy(self.task);revised['direction']['decisions'][0]['selected']='shift'
        revised['delivery']['path']='revised-delivery.txt';(self.root/'revised-delivery.txt').write_text('Use the intended spacing.')
        self.write('revised-task.json',revised)
        intent=w.revision_intent(self.root,run,'revised-task.json',ca['sha256'],'spacing')
        authorization=fixture.grant(self.root,run,intent)
        child=w.revise(self.root,run,'revised-task.json',ca['sha256'],'spacing',authorization)
        prepared=w.load_run(self.root,child['run'])[1]
        self.assertEqual(prepared['parent']['candidate'],ca['sha256']);self.assertEqual(prepared['parent']['repair'],'spacing')
        self.assertNotEqual(child['run'],run);self.assertIsNone(next(r for r in w.load_run(self.root,run)[3] if r['event']=='review')['data']['review'].get('approved'))
        fixture.handoff(self.root,child['run'],'synthetic author','manual')
        self.write('revised.png',png(128));child_ca=w.capture(self.root,child['run'],'revised.png','Synthetic repaired result.')
        self.record_review(child['run'],child_ca,name='revised-review.json');self.selection(child['run'],child_ca)
        w.select(self.root,child['run'],'selection.json');w.complete(self.root,child['run'])
        self.assertEqual(w.status(self.root,child['run'])['next'],'done')
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
        (self.root / 'new-delivery.txt').write_text('Use the intended spacing.')
        self.write('new-task.json', revised)
        return revised
    def test_repair_cannot_hide_a_changed_decision(self):
        run, ca = self.candidate(); self.revised_input(run, ca, ['delivery'])
        with self.assertRaisesRegex(ValueError, 'reviewed scope'):
            w.revision_intent(self.root, run, 'new-task.json', ca['sha256'], 'repair')
    def test_repair_cannot_hide_a_changed_source(self):
        run, ca = self.candidate(); self.revised_input(run, ca)
        (self.root / 'brief.md').write_text('An unrelated replacement purpose.')
        with self.assertRaisesRegex(ValueError, 'reviewed scope'):
            w.revision_intent(self.root, run, 'new-task.json', ca['sha256'], 'repair')
    def test_in_place_delivery_revision_is_authorizable(self):
        run, ca = self.candidate(); revised = self.revised_input(run, ca)
        revised['delivery']['path'] = 'delivery.txt'; self.write('new-task.json', revised)
        (self.root / 'delivery.txt').write_text('Use the intended spacing.')
        intent = w.revision_intent(self.root, run, 'new-task.json', ca['sha256'], 'repair')
        authorization = fixture.grant(self.root, run, intent)
        child = w.revise(self.root, run, 'new-task.json', ca['sha256'], 'repair', authorization)
        self.assertNotEqual(child['run'], run)
    def test_revoked_authority_cannot_authorize_an_edit(self):
        run, ca = self.candidate(); self.revised_input(run, ca)
        intent = w.revision_intent(self.root, run, 'new-task.json', ca['sha256'], 'repair')
        authority = self.authority(); authority['grants'] = []; self.write('fixture-authority.json', authority)
        with self.assertRaisesRegex(ValueError, 'authority'):
            fixture.grant(self.root, run, intent)
    def test_revoked_authority_cannot_consume_reserved_edit(self):
        run, ca = self.candidate(); self.revised_input(run, ca)
        intent = w.revision_intent(self.root, run, 'new-task.json', ca['sha256'], 'repair')
        auth = fixture.grant(self.root, run, intent)
        (self.root / 'fixture-authority-basis.txt').write_text('Authority withdrawn.')
        with self.assertRaisesRegex(ValueError, 'authority'):
            w.revise(self.root, run, 'new-task.json', ca['sha256'], 'repair', auth)
    def test_empty_criteria_cannot_create_vacuous_completion(self):
        self.task['criteria'] = []; self.task['direction']['decisions'] = []; self.write('task.json', self.task)
        with self.assertRaises(ValueError): self.prepare()
    def test_private_consumer_fields_rejected_even_if_rehashed(self):
        run = self.prepare(); b = binding.create(self.root, run, 'Keep the sparse field.')
        b['consumer']['direction']['private_dossier'] = 'SECRET'
        b['consumer_sha256'] = c.content_id(b['consumer'])
        b['sha256'] = c.content_id({k:v for k,v in b.items() if k != 'sha256'})
        with self.assertRaises(ValueError): binding.validate(b, 'Keep the sparse field.')


class MoneyTests(unittest.TestCase):
    def setUp(self):
        self.authority={'task_id':'fixture','issuer':'fixture','evidence':{'path':'a','locator':'whole'},
            'grants':[{'id':'grant','actor':'actor','mode':'delegated','operations':['submit'],'targets':['delivery'],
                       'limits':{'uses':5,'outputs':5,'cost':{'currency':'USD','amount':'0.3'}},'protected_criteria':[],'expires_at':None}], 'stop_conditions':[]}
        self.request={'grant':'grant','actor':'actor','operation':'submit','targets':['delivery'],'payload':{'count':1},
                      'outputs':1,'cost':{'currency':'USD','amount':'0.2','basis':'Declared fixture cap'},'stop_assessments':[],'reason':'test'}
    def test_decimal_reservations_are_exact(self):
        earlier=copy.deepcopy(self.request);earlier['cost']['amount']='0.1'
        permissions.check(self.authority,self.request,[earlier])
    def test_total_cost_exceeded(self):
        with self.assertRaises(ValueError):permissions.check(self.authority,self.request,[self.request])
    def test_unknown_cost_is_not_submission_permission(self):
        self.request['cost']=None
        with self.assertRaises(ValueError):permissions.check(self.authority,self.request,[])
    def test_count_mismatch(self):
        self.request['payload']['count']=2
        with self.assertRaises(ValueError):permissions.check(self.authority,self.request,[])
    def test_float_money_is_rejected(self):
        self.request['cost']['amount']=0.2
        with self.assertRaises(ValueError):permissions.check(self.authority,self.request,[])
    def test_nan_money_is_rejected(self):
        self.request['cost']['amount']='NaN'
        with self.assertRaises(ValueError):permissions.check(self.authority,self.request,[])
    def test_currency_mismatch(self):
        self.request['cost']['currency']='JPY'
        with self.assertRaises(ValueError):permissions.check(self.authority,self.request,[])
    def test_boolean_count_rejected(self):
        self.request['outputs']=True
        with self.assertRaises(ValueError):permissions.check(self.authority,self.request,[])
    def test_no_paid_cap_does_not_mean_unlimited(self):
        self.authority['grants'][0]['limits']['cost']=None
        with self.assertRaises(ValueError):permissions.check(self.authority,self.request,[])
    def test_no_output_budget(self):
        self.authority['grants'][0]['limits']['outputs']=0
        with self.assertRaises(ValueError):permissions.check(self.authority,self.request,[])

    def test_high_precision_spending_does_not_round_under_the_limit(self):
        exact = '1' + '0' * 60
        self.authority['grants'][0]['limits']['cost']['amount'] = exact
        earlier = copy.deepcopy(self.request); earlier['cost']['amount'] = exact
        self.request['cost']['amount'] = '0.000000000000000000000000000001'
        with self.assertRaisesRegex(ValueError, 'cost limit'):
            permissions.check(self.authority, self.request, [earlier])


if __name__ == '__main__':
    unittest.main(verbosity=2)
