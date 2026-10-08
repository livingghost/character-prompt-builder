"""Completed transport evidence never promotes itself into a model profile."""
from __future__ import annotations
from pathlib import Path
import unittest
from unittest.mock import patch
import model_observation as observation
import copy
import tempfile
import execution_contract as c
import production_case_fixtures as fixtures
import production_workflow as workflow
import production_execution as execution
from test_production_execution import decisions
import request_validation as rv
from input_evidence import InputEvidence


TARGET={'service':'synthetic','model_identifier':'synthetic:model','operation':'generation'}
RESULT='a'*64
DERIVED={'target':TARGET,'outcome':'completed','request':{'sealed':{'execution':{'service_execution_sha256':'1'*64,'offering_contract_sha256':'2'*64,'transport_sha256':'3'*64}},'profile':{'seed':1},'profile_sha256':'4'*64},'claim':'5'*64,'execution':'execution','results':[RESULT],'observed_at':'2026-10-01T00:00:00Z'}
PLAN={'purpose':'output_quality','question':'Does the exact completed trial produce the observed synthetic output?'}
SOURCE={'prepared':{'dependencies':[]}}

def adoption(**changes):
    value={'artifact_type':'model-profile-adoption','run':'019a0000-0000-7000-8000-000000000001','target':TARGET,
        'question':PLAN['question'],'purpose':PLAN['purpose'],'conclusion':'supported','observations':[{'kind':'observed_output','statement':'The saved synthetic output exists for the exact completed request.','result_sha256':RESULT}],
        'unmeasured':[{'id':'other-tuples','scope':'parameters','statement':'Other parameter tuples and new authored content remain unmeasured.'}],
        'decision':'adopt-profile','reason':'Adopt only the exact completed tuple represented by this evidence.',
        'decided_by':'Synthetic fixture author','decided_at':'2026-10-01T00:00:00Z'}
    value.update(changes);return value

def measurement(**changes):
    value={'kind':'measurement','statement':'The synthetic output is 32 pixels wide.','result_sha256':RESULT,
        'method':'Read the width from the saved PNG header.','scope':'This exact synthetic request on the synthetic service.',
        'limitations':['A header width says nothing about the depicted content.']}
    value.update(changes);return value

class ObservationAdoptionTests(unittest.TestCase):
    def bundle(self,decision=None):
        with patch.object(observation,'capture',return_value=SOURCE),patch.object(observation,'_derive',return_value=DERIVED),patch.object(observation,'trial_plan',return_value=PLAN):
            return observation.bundle(Path('.'),'019a0000-0000-7000-8000-000000000001',relative_prefix='evidence/trial',adoption=decision)
    def test_completed_trial_without_adoption_has_no_profile(self):
        files,result=self.bundle();self.assertIsNone(result['profile']);self.assertNotIn('profile.json',files);self.assertNotIn('adoption.json',files)
    def test_explicit_bounded_adoption_creates_profile_and_links_decision(self):
        files,result=self.bundle(adoption());self.assertIsNotNone(result['profile']);profile=__import__('json').loads(files['profile.json'])
        self.assertEqual(profile['adoption']['path'],'evidence/trial/adoption.json');self.assertEqual(profile['question'],PLAN['question']);self.assertEqual(profile['unmeasured'],adoption()['unmeasured'])
    def test_hypothesis_alone_cannot_adopt_profile(self):
        value=adoption(observations=[{'kind':'hypothesis','statement':'Maybe the parameter caused the output.','result_sha256':None}])
        with self.assertRaisesRegex(ValueError,'hypothesis alone'):self.bundle(value)
    def test_observed_output_must_belong_to_this_trial(self):
        value=adoption(observations=[measurement(result_sha256='b'*64)])
        with self.assertRaisesRegex(ValueError,'outside this trial'):self.bundle(value)
    def test_measurement_states_method_scope_and_limits(self):
        files,result=self.bundle(adoption(observations=[measurement()]));self.assertIsNotNone(result['profile'])
        bare={k:v for k,v in measurement().items() if k not in {'method','scope','limitations'}}
        with self.assertRaisesRegex(ValueError,"missing required property 'method'"):self.bundle(adoption(observations=[bare]))
    def test_unmeasured_scope_is_required(self):
        with self.assertRaisesRegex(ValueError,'unmeasured'):self.bundle(adoption(unmeasured=[]))
    def test_decision_time_carries_its_timezone(self):
        with self.assertRaisesRegex(ValueError,'decided_at'):self.bundle(adoption(decided_at='2026-10-01T00:00:00'))


    def test_request_acceptance_cannot_answer_visual_question(self):
        value=adoption(observations=[{'kind':'request_acceptance','statement':'The request was accepted.','result_sha256':None}])
        with self.assertRaisesRegex(ValueError,'acceptance alone'):self.bundle(value)

    def test_indeterminate_trial_cannot_create_profile(self):
        with self.assertRaisesRegex(ValueError,'conclusion'):self.bundle(adoption(conclusion='indeterminate'))

    def test_provider_statement_is_not_measured_behavior(self):
        value=adoption(observations=[{'kind':'provider_statement','statement':'Provider claims an effect.','result_sha256':None}])
        with self.assertRaisesRegex(ValueError,'provider statement'):self.bundle(value)

    def test_adoption_from_another_run_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'another run'):self.bundle(adoption(run='019a0000-0000-7000-8000-000000000002'))

class RecordedObservationTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        import production_case_fixtures as fixtures
        import production_workflow as workflow
        import production_execution as execution
        from test_production_execution import decisions
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        base = Path(self.temporary.name)
        case = fixtures.create(base / 'studio', base / 'runtime')
        self.root = case['root']
        self.run = workflow.prepare(self.root, 'task.json')['run']
        execution.execute(self.root, self.run, decisions_file=decisions(self.root, self.run))
        self.source = observation.capture(self.root, self.run)

    def test_export_keeps_recorded_observation_time_and_identity(self):
        first, _ = observation.bundle(self.root, self.run, relative_prefix='observed')
        second, _ = observation.bundle(self.root, self.run, relative_prefix='observed')
        self.assertEqual(first, second)
        value = c.decode(first['observation.json'])
        rows = self.source['records']
        captured = [row for row in rows if row['event'] == 'dispatch-results'][-1]
        self.assertEqual(value['observed_at'], captured['created_at'])

    def test_observation_time_cannot_be_changed_independently_of_evidence(self):
        files, result = observation.bundle(self.root, self.run, relative_prefix='observed')
        (self.root/'observed').mkdir()
        for name, raw in files.items():
            (self.root/'observed'/name).write_bytes(raw)
        value = c.decode(files['observation.json'])
        value['observed_at'] = '2000-01-01T00:00:00Z'
        with self.assertRaisesRegex(ValueError, 'recorded dispatch evidence'):
            observation.validate_observation(value, InputEvidence(self.root))

    def test_completed_formal_run_can_be_captured_without_recreating_a_run(self):
        import execution_lifecycle as accounting
        state = accounting.all_states(self.root)[0]
        derived = observation._derive(self.source)
        self.assertEqual(derived['outcome'], 'completed')
        self.assertEqual(derived['execution'], state['execution_id'])
        self.assertEqual(state['status'], 'complete')
        self.assertEqual(len(derived['results']), 1)

    def test_recorded_evidence_survives_removal_of_source_studio(self):
        import shutil
        shutil.rmtree(self.root)
        derived = observation._derive(self.source)
        self.assertEqual(derived['outcome'], 'completed')

    def test_observation_reads_only_formal_evidence(self):
        import shutil
        import production_workflow as workflow
        import production_store as store
        rows=store.event_rows(self.root,self.run)
        claim=workflow.find(rows,'dispatch-claim')
        shutil.rmtree(self.root/claim['data']['journal'])
        source=observation.capture(self.root,self.run)
        self.assertEqual(source['journal'],self.source['journal'])
        self.assertEqual(sorted(source['journal']),['answer.json','request-contract.json','request.json','transport-outcome.json'])
        self.assertEqual(observation._derive(source)['outcome'],'completed')

    def test_changed_event_export_is_rejected(self):
        import copy
        changed = copy.deepcopy(self.source)
        changed['records'][-1]['data']['synthetic_tampering'] = True
        with self.assertRaisesRegex(ValueError, 'EVENT_CHAIN_CORRUPT'):
            observation._derive(changed)

    def test_changed_recorded_output_is_rejected(self):
        import copy
        changed = copy.deepcopy(self.source)
        key = observation._derive(changed)['results'][0]
        changed['objects'][key]['base64'] = 'AA=='
        with self.assertRaisesRegex(ValueError, 'byte witness changed'):
            observation._derive(changed)


def create_probe(base,upscale=False):
    case=fixtures.create(base/'studio',base/'runtime',with_upscale=upscale)
    root=case['root'];task_path=fixtures.upscale_task(root) if upscale else 'task.json'
    task=c.load(root/task_path)
    baseline=workflow.prepare(root,task_path)['run']
    directory=workflow.run_dir(root,baseline)
    rendered=c.load(directory/'request-contract.json')
    validation=c.load(root/task['delivery']['path'])['request_validation'] if upscale else c.load(root/task['generation']['request_validation'])
    basis=copy.deepcopy(c.load(root/validation['evidence']['path']))
    basis['status']={'document_status':'schema-not-provided'}
    fixtures.write(root/'trial/acquisition.json',basis)
    basis_ref={'path':'trial/acquisition.json','sha256':c.sha256_file(root/'trial/acquisition.json')}
    plan={'artifact_type':'model-trial-plan','target':rendered['sealed']['target'],'purpose':'request_acceptance',
          'question':'Does this exact synthetic request produce one captured PNG?',
          'basis':basis_ref,'reference_schemas':[],'fixed_request_profile':rendered['sealed'],
          'change_factor':{'id':'exact-request','statement':'The exact sealed synthetic request is the only trial tuple.'},
          'fixed_conditions':['Synthetic target, exact source or prompt, parameters and output count are fixed.'],
          'comparison':'Compare the saved response with the declared single output.',
          'observation_targets':['Request receipt and actual PNG bytes.'],
          'decision_method':'Use the saved transport response and inspect the PNG header; infer no artistic quality.',
          'indeterminate_handling':'Retain inconclusive evidence without an observed profile.',
          'recommendation_deviation':{'deviates':False,'reason':'This synthetic service has no sampling recommendation.'},
          'quantity':{'uses':1,'outputs':1},
          'stop_conditions':['Stop after one response or any uncertain outcome.'],'unknowns':[]}
    fixtures.write(root/'trial/plan.json',plan)
    record=rv.build_record({'mode':'bounded-probe','contract':'trial/plan.json','evidence':'trial/acquisition.json',
                            'execution_policy':validation['execution_policy']['path']},
                           InputEvidence(root),expected_target=rendered['sealed']['target'],execution=rendered['sealed']['execution'],rendered=rendered)
    if upscale:
        import input_contracts
        input_path=root/task['delivery']['path']
        value=c.load(input_path);reader,_=input_contracts.capture_validation(record,root=root)
        input_contracts.attach(value,record,reader);fixtures.write(input_path,value)
    else:
        fixtures.write(root/task['generation']['request_validation'],record)
    run=workflow.prepare(root,task_path)['run']
    execution.execute(root,run,decisions_file=decisions(root,run))
    source=observation.capture(root,run);derived=observation._derive(source)
    adoption={'artifact_type':'model-profile-adoption','run':run,'target':derived['target'],
              'purpose':plan['purpose'],'question':plan['question'],'conclusion':'supported',
              'observations':[{'kind':'request_acceptance','statement':'The locally executed fixture returned a PNG for this exact request.','result_sha256':None}],
              'unmeasured':[{'id':'quality','scope':'artistic-quality','statement':'No artistic or provider-quality conclusion is made.'}],
              'decision':'adopt-profile','reason':'Explicit synthetic test author adopts only the witnessed tuple.',
              'decided_by':'SYNTHETIC TEST AUTHOR','decided_at':'2026-10-02T00:00:00Z'}
    result=observation.publish(root,run,root/'trial/observed',relative_prefix='trial/observed',adoption=adoption)
    value=rv.build_record({'mode':'observed-profile','contract':result['profile']['path'],'evidence':result['observation']['path'],
                          'execution_policy':validation['execution_policy']['path']},InputEvidence(root),
                         expected_target=rendered['sealed']['target'],execution=rendered['sealed']['execution'],rendered=rendered)
    assert rv.require(value,InputEvidence(root),rendered=rendered)['checked']==['observed-fixed-tuple']
    return root,run,result,rendered,value




class CaptureProgressObservationTests(unittest.TestCase):
    def test_partial_capture_then_resume_has_one_observed_output_without_resending(self):
        import dispatch
        import transport_synthetic
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory)
            root=fixtures.create(base/'studio',base/'runtime')['root']
            run=workflow.prepare(root,'task.json')['run']
            incomplete={'entries':1,'refused':[],'acquired':[],'failed':[{'index':1,'error':'Synthetic interrupted local capture'}],'downloaded':0}
            with patch.object(dispatch,'acquire',return_value=incomplete):
                first=execution.execute(root,run,decisions_file=decisions(root,run))
            self.assertEqual(first['runs'][0]['capture'],'partial')
            self.assertEqual(observation._derive(observation.capture(root,run))['outcome'],'indeterminate')
            with patch.object(transport_synthetic,'send',side_effect=AssertionError('Resume does not send')):
                execution.resume(root,run)
            result=observation._derive(observation.capture(root,run))
            self.assertEqual(result['outcome'],'completed')
            self.assertEqual(len(result['results']),1)

class RecordedProbeProfileTests(unittest.TestCase):
    def test_generated_trial_explicit_profile_and_consumer_use_real_records(self):
        with tempfile.TemporaryDirectory() as directory:
            root,run,refs,rendered,record=create_probe(Path(directory))
            self.assertEqual(record['mode'],'observed-profile')
            files,result=observation.bundle(root,run,relative_prefix='trial/no-adoption')
            self.assertIsNone(result['profile'])
            self.assertNotIn('profile.json',files)

    def test_upscale_trial_profile_and_consumer_use_real_records(self):
        with tempfile.TemporaryDirectory() as directory:
            root,run,refs,rendered,record=create_probe(Path(directory),upscale=True)
            self.assertEqual(record['mode'],'observed-profile')
            self.assertEqual(rendered['sealed']['target']['operation'],'upscale')

    def test_profile_consumer_rejects_adoption_from_another_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root,run,refs,rendered,record=create_probe(Path(directory))
            profile=c.load(root/record['contract']['path'])
            adoption_path=root/profile['adoption']['path']
            changed=c.load(adoption_path)
            from pack_manager import generate_uuid7
            changed['run']=generate_uuid7()
            fixtures.write(adoption_path,changed)
            profile['adoption']['sha256']=c.sha256_file(adoption_path)
            fixtures.write(root/record['contract']['path'],profile)
            record['contract']['sha256']=c.sha256_file(root/record['contract']['path'])
            with self.assertRaisesRegex(ValueError,'another run'):
                rv.require(record,InputEvidence(root),rendered=rendered)


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
