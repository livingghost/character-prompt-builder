#!/usr/bin/env python3
"""End-to-end dispatch recovery with actual task snapshots and no public service.

Synthetic image data and the optional test-created loopback endpoint are the
only transports. Authority, publication, sealed requests, accounting, capture,
image bytes and Studio projection use their production implementations.
"""
from __future__ import annotations
import argparse
import base64
import contextlib
import copy
import importlib
import io
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch

import execution_contract as c
import dispatch
import production_case_fixtures as cases
import production_execution as execution
import production_fixtures
import production_workflow as workflow
import production_store as store
import production_variation as variation
import execution_lifecycle as accounting
import studio
import transport_synthetic
from test_production_execution import decisions


class DispatchRecoveryTests(unittest.TestCase):
    """Each test works on its own copy of one prepared studio and its own home.

    The class builds the pack, runtime state, catalog cache, studio, prepared
    run and decision file once. No test here edits the pack or the runtime state.
    """
    @classmethod
    def setUpClass(cls):
        from catalog_retrieval import runtime
        temp=tempfile.TemporaryDirectory();cls.addClassCleanup(temp.cleanup)
        base=Path(temp.name);cls.enterClassContext(production_fixtures.scratch_home(base/'home'))
        cls.addClassCleanup(runtime.configure_pack_runtime,None)
        cls.case=cases.create(base/'studio',base/'runtime');cls.origin=cls.case['root']
        task=c.load(cls.origin/'task.json');task['generation']['count']=2
        cases.write(cls.origin/'task.json',task)
        cls.prepared_run=workflow.prepare(cls.origin,'task.json')['run']
        cls.prepared_decisions=decisions(cls.origin,cls.prepared_run)

    def setUp(self):
        from catalog_retrieval import runtime
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.enterContext(production_fixtures.scratch_home(self.base/'home'))
        runtime.configure_pack_runtime(self.case['settings'])
        self.root=cases.copy_studio(self.origin,self.base/'studio')
        self.run=self.prepared_run;self.decision_file=self.prepared_decisions
        # Every copy carries the same request_id, so each test meets a synthetic service that has answered nothing.
        self.enterContext(patch.dict(transport_synthetic._ANSWERED,clear=True))
        self.actual_send=transport_synthetic.send
        self.send=self.enterContext(patch.object(transport_synthetic,'send',wraps=self.actual_send))
        self.upload=self.enterContext(patch.object(transport_synthetic,'upload_bytes',wraps=transport_synthetic.upload_bytes))
        self.key=self.enterContext(patch.object(dispatch,'api_key',side_effect=AssertionError('No real credentials in synthetic execution')))

    def call(self):return execution.execute(self.root,self.run,decisions_file=self.decision_file)
    def rows(self):return store.event_rows(self.root,self.run)
    def journal(self):
        return dispatch.RunJournal.open(c.local(self.root,workflow.find(self.rows(),'dispatch-claim')['data']['journal']))
    def candidates(self):return [row for row in self.rows() if row['event']=='candidate']
    def no_effect(self):
        self.send.assert_not_called();self.upload.assert_not_called();self.assertEqual(accounting.all_states(self.root),[])
    def low_level_options(self):
        """The dispatcher preview of the run's own sealed package."""
        saved=execution.compiled(self.root,self.run)
        return argparse.Namespace(package=saved[0]/'package.json',character='robot',slot='candidate',
            pack_settings=self.case['settings'],preview_out=None)

    def preview_refusal(self,options):
        with contextlib.redirect_stdout(io.StringIO()),self.assertRaises(ValueError) as caught:
            dispatch.dispatch_generation(options,self.root)
        self.no_effect()
        return caught.exception.diagnostic.code

    def test_success_records_exact_wire_request_and_each_output(self):
        report=self.call();journal=self.journal()
        self.assertTrue(report['execution_completed']);self.assertEqual(len(self.candidates()),2)
        self.assertEqual(c.load(journal.path/'request.json'),self.send.call_args.args[0])
        self.assertEqual(len(studio.read_iterations(studio.character_dir(self.root,'robot'))),2)
        self.key.assert_not_called()

    def test_low_level_preview_writes_no_events_or_claim(self):
        options=self.low_level_options();before=self.rows()
        with contextlib.redirect_stdout(io.StringIO()):self.assertEqual(dispatch.dispatch_generation(options,self.root),0)
        self.assertEqual(self.rows(),before);self.no_effect()

    def test_low_level_preview_target_recording_is_exact(self):
        options=self.low_level_options();options.slot='another-candidate'
        self.assertEqual(self.preview_refusal(options),'INPUT_CONSISTENCY_ERROR')

    def test_low_level_preview_refuses_changed_input(self):
        options=self.low_level_options()
        (self.root/'prompt.txt').write_text('A different, unreviewed source.',encoding='utf-8')
        self.assertEqual(self.preview_refusal(options),'SOURCE_CHANGED')

    def test_low_level_preview_refuses_another_package(self):
        options=self.low_level_options();package=c.load(options.package);package['source_brief']='Changed brief.'
        changed=self.root/'changed-package.json';changed.write_bytes(c.encoded(package));options.package=changed
        self.assertEqual(self.preview_refusal(options),'INPUT_CONSISTENCY_ERROR')

    def test_recording_write_failure_stops_before_claim(self):
        actual=studio.validate_recording_target
        def check(*args,**kwargs):
            if kwargs.get('writable'):raise PermissionError('Synthetic recording access denial')
            return actual(*args,**kwargs)
        with patch.object(studio,'validate_recording_target',side_effect=check),self.assertRaises(PermissionError):self.call()
        self.no_effect();self.assertEqual(self.rows(),[])

    def test_changed_input_is_not_sent(self):
        (self.root/'prompt.txt').write_text('A different, unreviewed source.',encoding='utf-8')
        with self.assertRaises(ValueError):self.call()
        self.no_effect()

    def test_incomplete_permission_rolls_back_before_claim(self):
        value=c.load(self.root/self.decision_file);value['authorizations']=value['authorizations'][:1]
        cases.write(self.root/self.decision_file,value)
        with self.assertRaises(ValueError):self.call()
        self.no_effect();self.assertEqual(self.rows(),[])


    def test_publication_failure_does_not_send(self):
        with patch.object(execution,'_journal',side_effect=OSError('Synthetic durable storage failure')),self.assertRaises(OSError):self.call()
        self.no_effect();self.assertEqual(self.rows(),[])

    def test_claim_failure_precedes_irreversible_request(self):
        with patch.object(workflow,'claim_dispatch',side_effect=OSError('Synthetic claim transaction failure')),self.assertRaises(OSError):self.call()
        self.no_effect();self.assertEqual(self.rows(),[])
        # The journal written for the failed claim is listed, never as eligible while its owner process runs.
        listed=execution.status(self.root)['unclaimed_journals']
        self.assertEqual([(row['production_run'],row['eligible']) for row in listed],[(self.run,False)])
        self.assertEqual(listed[0]['pid'],os.getpid())

    def test_claimed_journal_is_never_listed_as_unclaimed(self):
        self.call()
        self.assertEqual(execution.unclaimed_journals(self.root),[])
        self.assertEqual(self.journal().document['owner']['pid'],os.getpid())

    def test_timeout_retains_one_unknown_claim(self):
        self.send.side_effect=TimeoutError('Synthetic response loss')
        report=self.call();again=execution.resume(self.root,self.run)
        self.assertEqual(report['runs'][0]['submission'],'outcome_unknown')
        self.assertEqual(again['runs'][0]['submission'],'outcome_unknown');self.assertEqual(self.send.call_count,1)
        self.assertEqual(accounting.all_states(self.root)[0]['status'],'started')

    def test_lost_answer_is_recovered_by_lookup_without_resend(self):
        def lose(*args):
            self.actual_send(*args);raise TimeoutError('Synthetic answer loss after the service carried out the request')
        self.send.side_effect=lose
        first=self.call();self.assertEqual(first['runs'][0]['submission'],'outcome_unknown')
        again=execution.resume(self.root,self.run)
        self.assertTrue(again['execution_completed']);self.assertEqual(len(self.candidates()),2)
        self.assertEqual(self.send.call_count,1);self.key.assert_not_called()
        self.assertEqual(again['runs'][0]['submission'],'acknowledged')
        lookup=c.load(self.journal().path/'lookup-001.json')
        self.assertEqual((lookup['outcome'],lookup['transport']),('found','synthetic'))

    def test_refusal_has_saved_response_and_no_invented_candidate(self):
        self.send.return_value={'errors':[{'code':'synthetic-refusal','message':'Synthetic fixture refusal.'}]};self.send.side_effect=lambda *args:self.send.return_value
        report=self.call();self.assertFalse(report['execution_completed']);self.assertEqual(self.candidates(),[])
        self.assertTrue((self.journal().path/'answer.json').is_file());self.assertTrue(self.journal().document['refused'])

    def test_refusal_does_not_discard_returned_images(self):
        def answer(*args):
            result=self.actual_send(*args);result['errors']=[{'code':'synthetic-partial','message':'A synthetic supplementary refusal.'}];return result
        self.send.side_effect=answer;report=self.call()
        self.assertEqual(len(self.candidates()),2);self.assertTrue(self.journal().document['refused'])
        self.assertFalse(report['execution_completed'])

    def test_empty_answer_does_not_trigger_another_send(self):
        self.send.side_effect=lambda *args:{'data':[]}
        first=self.call();second=execution.resume(self.root,self.run)
        self.assertFalse(first['execution_completed']);self.assertFalse(second['execution_completed']);self.assertEqual(self.send.call_count,1)

    def test_partial_count_keeps_real_candidate(self):
        def answer(*args):
            result=self.actual_send(*args);result['data']=result['data'][:1];return result
        self.send.side_effect=answer;result=self.call()
        self.assertFalse(result['execution_completed']);self.assertEqual(len(self.candidates()),1)
        self.assertEqual(self.journal().document['received'],1)

    def test_extra_count_does_not_become_authorized_success(self):
        def answer(*args):
            result=self.actual_send(*args);result['data'].append({**result['data'][0],'id':'extra-output'});return result
        self.send.side_effect=answer;result=self.call()
        self.assertFalse(result['execution_completed']);self.assertEqual(len(self.candidates()),3)
        self.assertEqual(accounting.summary(self.root)['captured_outputs'],3)

    def test_failed_decode_preserves_other_acquired_output(self):
        original=dispatch.inline_image;seen=[]
        def decode(value):
            seen.append(value)
            if len(seen)==1:raise ValueError('Synthetic incomplete inline bytes')
            return original(value)
        with patch.object(dispatch,'inline_image',side_effect=decode):first=self.call()
        self.assertEqual(len(self.candidates()),1);self.assertFalse(first['execution_completed'])
        second=execution.resume(self.root,self.run)
        self.assertTrue(second['execution_completed']);self.assertEqual(len(self.candidates()),2);self.assertEqual(self.send.call_count,1)

    def test_completed_inline_files_are_not_rewritten(self):
        self.call();journal=self.journal();paths=sorted(journal.path.glob('result-*'))
        before={p.name:(p.stat().st_mtime_ns,p.read_bytes()) for p in paths}
        execution.resume(self.root,self.run)
        self.assertEqual(before,{p.name:(p.stat().st_mtime_ns,p.read_bytes()) for p in paths})

    def test_corrupt_response_provenance_stops_registration(self):
        with patch.object(workflow,'record_dispatch_results',side_effect=OSError('Synthetic interrupted registration')),self.assertRaises(OSError):self.call()
        response=self.journal().path/'response-1.json';value=c.load(response);value['answer_sha256']='a'*64;cases.write(response,value)
        with self.assertRaises(ValueError):execution.resume(self.root,self.run)
        self.assertEqual(self.candidates(),[]);self.assertEqual(self.send.call_count,1)

    def test_corrupt_answer_is_not_reinterpreted_as_new_result(self):
        with patch.object(workflow,'record_dispatch_results',side_effect=OSError('Synthetic interrupted registration')),self.assertRaises(OSError):self.call()
        cases.write(self.journal().path/'answer.json',{'data':[]})
        with self.assertRaises(ValueError):execution.resume(self.root,self.run)
        self.assertEqual(self.send.call_count,1)

    def test_missing_answer_after_send_remains_unknown(self):
        self.send.side_effect=TimeoutError('Synthetic timeout');self.call()
        result=execution.resume(self.root,self.run)
        self.assertEqual(result['runs'][0]['submission'],'outcome_unknown');self.assertEqual(self.send.call_count,1)

    def test_projection_failure_preserves_formal_candidates(self):
        with patch.object(studio,'iterate',side_effect=OSError('Synthetic projection failure')):first=self.call()
        self.assertFalse(first['execution_completed']);self.assertEqual(len(self.candidates()),2)
        self.assertEqual(first['runs'][0]['registration'],'projection-missing')
        self.assertEqual(self.journal().document['status'],'projection-missing')
        self.assertEqual(first['runs'][0]['next_action']['command'],'resume')
        second=execution.resume(self.root,self.run);self.assertTrue(second['execution_completed'])
        self.assertEqual(second['runs'][0]['registration'],'registered')
        self.assertEqual(self.send.call_count,1)

    def test_partial_projection_is_idempotent(self):
        actual=studio.iterate;calls=[]
        def fail_second(*args,**kwargs):
            calls.append(1)
            if len(calls)==2:raise OSError('Synthetic second projection failure')
            return actual(*args,**kwargs)
        with patch.object(studio,'iterate',side_effect=fail_second):self.call()
        execution.resume(self.root,self.run);execution.resume(self.root,self.run)
        self.assertEqual(len(studio.read_iterations(studio.character_dir(self.root,'robot'))),2)
        self.assertEqual(len(self.candidates()),2);self.assertEqual(self.send.call_count,1)

    def test_original_sources_are_not_needed_for_saved_answer(self):
        with patch.object(workflow,'record_dispatch_results',side_effect=OSError('Synthetic interrupted registration')),self.assertRaises(OSError):self.call()
        (self.root/'prompt.txt').unlink();(self.root/'fixture-authority-basis.txt').unlink()
        result=execution.resume(self.root,self.run)
        self.assertTrue(result['execution_completed']);self.assertEqual(self.send.call_count,1)

    def test_source_change_does_not_hide_unknown_result(self):
        self.send.side_effect=TimeoutError('Synthetic timeout');self.call();(self.root/'prompt.txt').unlink()
        result=execution.status(self.root,self.run)['runs'][0]
        self.assertEqual(result['submission'],'outcome_unknown');self.assertEqual(result['integrity'],'intact')

    def test_repeated_execute_does_not_create_second_claim(self):
        self.call()
        with self.assertRaises(ValueError):self.call()
        self.assertEqual(self.send.call_count,1);self.assertEqual(len([r for r in self.rows() if r['event']=='dispatch-claim']),1)

    def test_intentional_repeat_creates_distinct_journal(self):
        self.call();first=self.journal().path
        child=variation.derive(self.root,self.run,prepare=True)['run']
        execution.execute(self.root,child,decisions_file=decisions(self.root,child))
        claim=workflow.find(store.event_rows(self.root,child),'dispatch-claim')
        self.assertNotEqual(c.local(self.root,claim['data']['journal']),first);self.assertEqual(self.send.call_count,2)


class ResumeOffersDownload(unittest.TestCase):
    """The complete setup from an empty folder, run end to end in one test so the uncopied path stays covered."""
    def test_saved_answer_is_recovered_through_resume(self):
        with tempfile.TemporaryDirectory() as t:
            b=Path(t);case=cases.create(b/'studio',b/'runtime');root=case['root'];run=workflow.prepare(root,'task.json')['run']
            with patch.object(workflow,'record_dispatch_results',side_effect=OSError('Synthetic interrupted registration')):
                with self.assertRaises(OSError):execution.execute(root,run,decisions_file=decisions(root,run))
            self.assertEqual(execution.status(root,run)['runs'][0]['next_action']['command'],'resume')
            with patch.object(transport_synthetic,'send',side_effect=AssertionError('No retransmission')):
                self.assertTrue(execution.resume(root,run)['execution_completed'])


SECOND_TRANSPORT = '"""A synthetic second service for the dispatch tests; it reaches only the test\'s loopback service."""\nimport json\n\nfrom model_contract import NEGATIVE_ROLE, PROMPT_ROLE, required_request_key\nfrom request_contract import RequestWriter, path_parts\nfrom transport_contract import address, post\n\nOPERATIONS = {"generation": "text-to-image"}\nRESULT_HOSTS = frozenset()\n\n\ndef endpoint(service):\n    return address(service["endpoint"]["base_url"])\n\n\ndef compile_request(verified, offering, service, media_ids=None, seed=None, count=1):\n    forwarding = verified["host_forwarding"]\n    writer = RequestWriter()\n    source = [{"kind": "offering", "service": offering["service"], "model_identifier": offering["model_identifier"]}]\n\n    def write(path, value, kind, transform):\n        writer.write(path, value, source_kind=kind, source_refs=source, transform_id=transform)\n\n    prompt = path_parts(required_request_key(offering, PROMPT_ROLE))\n    write(prompt, forwarding["effective_prompt"], "authored", "selected-rendition")\n    layout = {"model": None, "operation": None, "primary_text": prompt, "negative_text": None,\n              "output_count": ["num_images"], "fixed_output_count": None, "seed": None, "media": [],\n              "management": [], "content": [{"id": "prompt", "field": prompt}],\n              "fields": [{"id": "prompt", "field": prompt, "kind": "content"},\n                         {"id": "count", "field": ["num_images"], "kind": "parameter"}]}\n    selected = forwarding["selected_transport"]\n    negative = selected["rendition"].get("negative") or ""\n    if selected["mode"] in {"separate-field", "native-subset"} and negative:\n        field = path_parts(required_request_key(offering, NEGATIVE_ROLE))\n        write(field, negative, "authored", "selected-negative-channel")\n        layout["negative_text"] = field\n        layout["content"].append({"id": "negative", "field": field})\n        layout["fields"].append({"id": "negative", "field": field, "kind": "content"})\n    for name, value in sorted((forwarding.get("parameters") or {}).items()):\n        write(path_parts(name), value, "model-setting", "selected-parameter")\n        layout["fields"].append({"id": "parameter:" + name, "field": path_parts(name), "kind": "parameter"})\n    write(["num_images"], count, "model-setting", "explicit-output-count")\n    if seed is not None:\n        write(["seed"], seed, "model-setting", "explicit-seed")\n        layout["seed"] = ["seed"]\n        layout["fields"].append({"id": "seed", "field": ["seed"], "kind": "parameter"})\n    return {"request": writer.request, "layout": layout, "request_trace": writer.trace}\n\n\ndef added_parameters(offering, seed=None, count=1):\n    return {"num_images": count, **({"seed": seed} if seed is not None else {})}\n\n\ndef upload_bytes(data, media_type, service, key):\n    raise ValueError("the fixture service takes no media")\n\n\ndef send(request, service, key):\n    status, body = post(endpoint(service), json.dumps(request).encode("utf-8"),\n                        {"Content-Type": "application/json", "Authorization": "Key " + key})\n    answer = json.loads(body.decode("utf-8"))\n    return answer if status == 200 else {"errors": [{"status": status, **answer}]}\n\n\ndef rejections(answer):\n    return list(answer.get("errors") or [])\n\n\ndef results(answer):\n    return [{"data": item["b64"], "seed": item.get("seed"), "id": item.get("id")} for item in answer.get("images") or []]\n\n\ndef observation_outcome(answer):\n    return "rejected" if rejections(answer) else "accepted" if results(answer) else "indeterminate"\n\n\ndef usage(answer):\n    return None\n'


class SecondServiceTests(unittest.TestCase):
    """A separately implemented transport and loopback endpoint, with no provider calls.

    Each test edits its pack and runtime state, so each builds its own setup.
    """
    def setUp(self):
        from dispatch_smoke_test import LoopbackService
        from catalog_retrieval import runtime
        from request_validation_fixtures import interface_validation
        from reading_fixtures import fixture_reading
        import service_profile
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        base=Path(self.temp.name);case=cases.create(base/'studio',base/'runtime');self.root=case['root'];self.case=case
        self.loopback=LoopbackService();self.addCleanup(self.loopback.__exit__)
        module_dir=base/'transport';module_dir.mkdir();(module_dir/'transport_loopback_fixture.py').write_text(SECOND_TRANSPORT,encoding='utf-8')
        sys.path.insert(0,str(module_dir));self.addCleanup(sys.path.remove,str(module_dir));self.addCleanup(sys.modules.pop,'transport_loopback_fixture',None)
        self.transport=importlib.import_module('transport_loopback_fixture')
        service={'label':'Synthetic loopback test interface','transport':'loopback_fixture',
                 'endpoint':{'base_url':self.loopback.url+'/model/text-to-image','method':'POST'},
                 'auth':{'env_var':'CPB_SECOND_SYNTHETIC_KEY'},'operations':{'text-to-image':{}}}
        services=c.load(case['pack']/'resources/services.json');services['services']['second-fixture']=service
        cases.write(case['pack']/'resources/services.json',services)
        records=c.load(case['pack']/'records/models.json');model=records['records'][0]
        offering=model['offerings'][0];offering.update(service='second-fixture',model_identifier='loopback-model',
            request_keys={'prompt':['prompt'],'negative prompt':['negative_prompt']})
        for profile in (model['execution_profile'],offering['execution_profile']):
            for mode in profile['modes'].values():
                mode['controls']['num_images']=mode['controls'].pop('count')
        cases.write(case['pack']/'records/models.json',records);cases.packs.write_lock(case['pack']);runtime.configure_pack_runtime(case['settings'])
        catalog=runtime.load_pack_catalog();loaded=service_profile.load_service('second-fixture',case['pack']/'resources/services.json')
        validation=interface_validation(self.root,target={'service':'second-fixture','model_identifier':'loopback-model','operation':'text-to-image'},
                                       record=model,offering=offering,service_record=loaded,transport=self.transport,reference_mode='authored-rendition')
        cases.write(self.root/'validation.json',validation)
        retrieval=c.load(self.root/'retrieval.json');retrieval['pack_state']=catalog.fingerprint;cases.write(self.root/'retrieval.json',retrieval)
        task=c.load(self.root/'task.json');task['generation'].update(service='second-fixture',count=2)
        cases.write(self.root/'reading.json',fixture_reading(route='generation',studio=self.root,ledger=self.root/'work/reads.jsonl'))
        cases.write(self.root/'task.json',task)
        self.run=workflow.prepare(self.root,'task.json')['run'];self.decisions=decisions(self.root,self.run)
        self.enterContext(patch.dict(os.environ,{'CPB_SECOND_SYNTHETIC_KEY':'SYNTHETIC-LOOPBACK-KEY'}))
        real_connect=socket.create_connection;port=self.loopback.server.server_address[1]
        def loopback_only(address,*args,**kwargs):
            if tuple(address[:2])!=('127.0.0.1',port):raise AssertionError('Test attempted a non-loopback connection')
            return real_connect(address,*args,**kwargs)
        self.enterContext(patch.object(socket,'create_connection',loopback_only))
        self.enterContext(patch.object(dispatch,'save',side_effect=AssertionError('Inline output is not downloaded')))

    def execute(self):
        # The selected module is a separate implementation; request rendering
        # and execution cannot quietly fall back to Runware.
        with patch.dict(sys.modules,{'transport_runware':None}):
            return execution.execute(self.root,self.run,decisions_file=self.decisions)

    def test_preview_send_and_inline_recovery_through_second_service(self):
        raw=transport_synthetic._png(32,32,b'\x30\x50\x70')
        answer={'images':[{'id':'a','b64':base64.b64encode(raw).decode('ascii')},
                          {'id':'b','b64':base64.b64encode(raw).decode('ascii')}]}
        self.loopback.reply=(200,{'Content-Type':'application/json'},c.encoded(answer))
        with patch.object(studio,'iterate',side_effect=OSError('Synthetic projection interruption')):first=self.execute()
        self.assertFalse(first['execution_completed']);self.assertEqual(len(first['runs'][0]['candidates']),2)
        second=execution.resume(self.root,self.run);self.assertTrue(second['execution_completed'])
        self.assertEqual(len(self.loopback.received),1)
        self.assertEqual(json.loads(self.loopback.received[0]['body'])['num_images'],2)
        self.assertEqual(self.loopback.received[0]['headers']['Authorization'],'Key SYNTHETIC-LOOPBACK-KEY')
        for path in self.root.rglob('*.json'):
            self.assertNotIn('SYNTHETIC-LOOPBACK-KEY',path.read_text(encoding='utf-8'))

    def test_5xx_retains_unknown_outcome_and_never_retries(self):
        self.loopback.reply=(503,{},b'synthetic busy')
        result=self.execute();again=execution.resume(self.root,self.run)
        self.assertEqual(result['runs'][0]['submission'],'outcome_unknown')
        self.assertEqual(again['runs'][0]['submission'],'outcome_unknown');self.assertEqual(len(self.loopback.received),1)
        # This transport defines no lookup, so resume asks nothing and records no new fact.
        self.assertEqual([item['code'] for item in again['warnings']],['PROVIDER_LOOKUP_UNSUPPORTED'])
        self.assertFalse(any(row['event']=='execution-outcome' and row['data'].get('lookup')
                             for row in store.event_rows(self.root,self.run)))

    def test_dropped_connection_retains_unknown_outcome(self):
        self.loopback.reply='drop'
        result=self.execute();execution.resume(self.root,self.run)
        self.assertEqual(result['runs'][0]['submission'],'outcome_unknown');self.assertEqual(len(self.loopback.received),1)


def main():
    stream=io.StringIO()
    suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(case)
                             for case in (DispatchRecoveryTests,ResumeOffersDownload,SecondServiceTests))
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    print(json.dumps({'ok':result.wasSuccessful(),'checks':result.testsRun,
        'failures':len(result.failures),'error_count':len(result.errors),
        'errors':[case.id()+': '+detail for case,detail in result.failures+result.errors],
        'detail':stream.getvalue()},indent=2))
    return 0 if result.wasSuccessful() else 1


if __name__=='__main__':
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
