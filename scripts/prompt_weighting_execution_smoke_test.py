#!/usr/bin/env python3
"""No-network weighting preparation, approval, transport and saved-result recovery."""
from __future__ import annotations
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import execution_contract as c
import production_case_fixtures as base
import production_execution as execution
import production_workflow as workflow
import prompt_weighting_fixtures as fixture
import request_contract as rc
import transport_synthetic


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)

    def create(self, **kwargs):
        case = fixture.create(self.home / 'studio', self.home / 'runtime', **kwargs)
        self.root = case['root']
        return case

    def prepare(self):
        return workflow.prepare(self.root, 'task.json')

    def test_and_and_negative_blend_survive_the_sealed_request(self):
        self.create()
        prepared = self.prepare()
        wire = execution.compiled(self.root, prepared['run'])[5]
        self.assertEqual(wire['request']['prompt'], fixture.PROMPT)
        self.assertEqual(wire['request']['negative_prompt'], fixture.NEGATIVE)
        self.assertEqual(wire['request']['promptWeighting'], 'compel')
        rc.validate_seal(wire)
        report = prepared['execution_plan']['prompt_check']
        self.assertEqual(report['syntax'], 'compel')
        self.assertEqual(report['channels']['positive']['operator'], 'and')
        self.assertEqual(report['channels']['negative']['operator'], 'blend')
        self.assertFalse(any(item['severity'] == 'problem' for item in report['findings']))
        self.assertEqual(report['request_sha256'], wire['request_sha256'])

    def test_same_tag_in_separate_clauses_is_not_flattened(self):
        self.create(prompt='("solo, blue eyes", "solo, green eyes").blend(1, 0.8)')
        findings = self.prepare()['execution_plan']['prompt_check']['findings']
        self.assertFalse(any(item['severity'] == 'problem' for item in findings), findings)
        self.assertTrue(any(item['check'] == 'conditioning clauses' for item in findings), findings)

    def test_bad_negative_grammar_fails_without_any_send_or_formal_run(self):
        self.create(negative='(lettering:1.2)')
        with patch.object(transport_synthetic, 'send', side_effect=AssertionError('must not send')), self.assertRaises(ValueError):
            self.prepare()
        self.assertEqual(workflow.run_ids(self.root), [])

    def test_unsupported_native_control_is_a_model_capability_failure(self):
        self.create(supported=('sdEmbeds',))
        with self.assertRaises(ValueError) as caught:
            self.prepare()
        self.assertIn('compel', str(getattr(caught.exception, 'report', caught.exception)))
        self.assertEqual(workflow.run_ids(self.root), [])

    def test_no_tag_family_still_inspects_weighting(self):
        self.create(family=False)
        report = self.prepare()['execution_plan']['prompt_check']
        self.assertEqual(report['state'], 'syntax-checked')
        self.assertEqual(report['channels']['positive']['operator'], 'and')

    def test_sdembeds_selected_by_native_control(self):
        self.create(prompt='solo, (blue eyes:1.2), [long hair]', negative='(lettering:1.3)', syntax='sdEmbeds')
        self.assertEqual(self.prepare()['execution_plan']['prompt_check']['syntax'], 'sdEmbeds')

    def test_explicit_model_default_is_resolved_before_recommendation(self):
        self.create(syntax=None, default='compel', recommended_negative='blurry')
        result = self.prepare()
        package = c.load(workflow.run_dir(self.root, result['run']) / 'package.json')
        self.assertEqual(package['render_contract']['parameters']['promptWeighting'], 'compel')
        audit = package['generation_payload']['prompt_recommendations']['negative']
        self.assertEqual(audit['weighting'], 'compel')
        self.assertFalse(audit['applied'])
        self.assertIn('conditioning-clauses-preserved', audit['reason'])

    def test_no_weighting_control_is_reported_literal_not_inferred(self):
        self.create(prompt='solo, blue eyes', negative='lettering', syntax=None)
        self.assertEqual(self.prepare()['execution_plan']['prompt_check']['syntax'], 'literal')

    def test_compound_recommendations_are_visible_not_silently_prepended(self):
        self.create(recommended_negative='blurry')
        result = self.prepare()
        package = c.load(workflow.run_dir(self.root, result['run']) / 'package.json')
        audit = package['generation_payload']['prompt_recommendations']['negative']
        self.assertFalse(audit['applied'])
        self.assertEqual(audit['recommended_text'], 'blurry')
        self.assertEqual(result['execution_plan']['prompt_check']['recommendations']['negative'], audit)
        self.assertIn('conditioning-clauses-preserved', audit['reason'])
        self.assertEqual(execution.compiled(self.root, result['run'])[5]['request']['negative_prompt'], fixture.NEGATIVE)

    def test_cross_syntax_recommendation_preserves_authored_text_and_is_visible(self):
        self.create(recommended_negative='(blurry:1.2)')
        result = self.prepare()
        report = result['execution_plan']['prompt_check']
        audit = report['recommendations']['negative']
        self.assertEqual(audit['reason'], 'recommendation-syntax-mismatch; author supplies matching grammar')
        self.assertEqual(audit['recommended_text'], '(blurry:1.2)')
        self.assertFalse(audit['applied'])
        self.assertEqual(execution.compiled(self.root, result['run'])[5]['request']['negative_prompt'], fixture.NEGATIVE)

    def test_native_syntax_change_invalidates_current_preparation(self):
        self.create()
        result = self.prepare()
        parameters = c.load(self.root / 'parameters.json'); parameters['promptWeighting'] = 'sdEmbeds'
        base.write(self.root / 'parameters.json', parameters)
        with self.assertRaises(ValueError):
            execution.execute(self.root, result['run'], decisions_file=base.fill_decisions(self.root, result['run'], 'approval.json'))

    def test_approved_send_and_resume_reuse_exact_original_text(self):
        self.create()
        result = self.prepare(); run = result['run']
        # Preparing alone has no authority to send.
        self.assertFalse(any(row['event'] == 'external-step' for row in workflow.load_run(self.root, run)[3]))
        original = transport_synthetic.send
        captured = []
        def send(*args, **kwargs):
            captured.append(copy.deepcopy(args[0]))
            return original(*args, **kwargs)
        with patch.object(transport_synthetic, 'send', side_effect=send):
            done = execution.execute(self.root, run, decisions_file=base.fill_decisions(self.root, run, 'approval.json'))
        self.assertTrue(done['execution_completed'], done)
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]['prompt'], fixture.PROMPT)
        self.assertEqual(captured[0]['negative_prompt'], fixture.NEGATIVE)
        self.assertEqual(captured[0]['promptWeighting'], 'compel')
        base.write(self.root / 'prompt.txt', 'A changed draft after the original send.')
        with patch.object(transport_synthetic, 'send', side_effect=AssertionError('resume must not resend')):
            self.assertTrue(execution.resume(self.root, run)['execution_completed'])

    def test_timeout_does_not_turn_into_new_weighted_request(self):
        self.create()
        run = self.prepare()['run']
        with patch.object(transport_synthetic, 'send', side_effect=TimeoutError('Synthetic uncertain outcome')) as send:
            first = execution.execute(self.root, run, decisions_file=base.fill_decisions(self.root, run, 'approval.json'))
            execution.resume(self.root, run)
        self.assertEqual(send.call_count, 1)
        self.assertFalse(first['execution_completed'])

    def test_guidance_uses_synthetic_service_capabilities_and_separate_family(self):
        case = self.create()
        import prompt_dialect
        args = __import__('argparse').Namespace(model=fixture.MODEL, dialect=None, dialects=None, guide=None, list=False,
            weighting='compel', service='synthetic', mode='text-to-image')
        with redirect_stdout(io.StringIO()) as captured:
            prompt_dialect.render_report(args, case['settings'])
        result = json.loads(captured.getvalue())
        self.assertEqual(result['dialect']['id'], 'synthetic-tags')
        self.assertEqual(result['weighting']['syntax'], 'compel')
        self.assertEqual(result['weighting_capabilities'][0]['control']['schema']['enum'], ['compel','sdEmbeds'])

    def test_guidance_refuses_unexposed_grammar(self):
        case = self.create(supported=('sdEmbeds',))
        import prompt_dialect
        args = __import__('argparse').Namespace(model=fixture.MODEL, dialect=None, dialects=None, guide=None, list=False,
            weighting='compel', service='synthetic', mode='text-to-image')
        from pack_manager import PackError
        with self.assertRaisesRegex(PackError, 'does not allow compel'):
            prompt_dialect.render_report(args, case['settings'])


class RunwareWireTests(unittest.TestCase):
    def test_compel_native_fields_and_text_are_forwarded_without_library_or_network(self):
        import transport_runware as adapter
        import prompt_weighting
        offering = {'service':'runware', 'model_identifier':'synthetic:fixture-only',
                    'request_keys':{'prompt':['positivePrompt'], 'negative prompt':['negativePrompt']}}
        verified = {'host_forwarding':{'effective_prompt':fixture.PROMPT,
                    'selected_transport':{'mode':'separate-field','rendition':{'negative':fixture.NEGATIVE}},
                    'parameters':{'promptWeighting':'compel','width':1024,'height':1024}}}
        with patch.object(adapter, '_post', side_effect=AssertionError('wire test makes no service request')):
            wire = adapter.compile_request(verified, offering, {'operations':{'imageInference':{}}}, count=1)
        self.assertEqual(wire['request']['positivePrompt'], fixture.PROMPT)
        self.assertEqual(wire['request']['negativePrompt'], fixture.NEGATIVE)
        self.assertEqual(wire['request']['promptWeighting'], 'compel')
        self.assertEqual(prompt_weighting.wire_selection(wire), 'compel')
        self.assertEqual(prompt_weighting.require_pair(wire['request']['positivePrompt'],wire['request']['negativePrompt'],'compel')['channels']['positive']['operator'],'and')


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
