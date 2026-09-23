#!/usr/bin/env python3
"""Conformance of explicit, data-only protocol handoffs using synthetic fixtures."""
from __future__ import annotations
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import integration_contract as contract
import protocol_exchange
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
FIX=ROOT/'examples/protocol-exchange/fixtures'

class Boundary(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='public-data-');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        self.caps=contract.load_capabilities(ROOT)
        self.kind='shot-request'
        self.raw=(FIX/(self.kind+'.json')).read_bytes()
        (self.root/'artifact.json').write_bytes(self.raw)
        self.profile=contract.find_interface(self.caps,'produces','shot-request')
        self.envelope=self.make(self.raw,self.profile)
    def make(self,raw,profile):
        return contract.finalize({'artifact_type':'interchange-envelope','envelope_id':'IE-fixture',
            'contract_profile':profile['profile'],'profile_sha256':profile['profile_sha256'],
            'origin':{'capability_manifest_sha256':self.caps['manifest_sha256']},
            'payload':{'artifact_type':json.loads(raw)['artifact_type'],
                'artifact_id':contract.payload_identity(json.loads(raw)), 'media_type':'application/json',
                'path':'artifact.json','sha256':hashlib.sha256(raw).hexdigest()},
            'required_features':profile['required_features'],'optional_features':[],'extensions':{}},'envelope_sha256')
    def check(self,value=None,**kw):
        options={'capabilities':self.caps,'direction':'consumes','declaration':self.caps,'payload_root':self.root};options.update(kw)
        return contract.validate_envelope(value or self.envelope,**options)
    def command(self,*args):
        env={k:v for k,v in os.environ.items() if k not in {'PYTHONPATH'}};env['PYTHONDONTWRITEBYTECODE']='1';env['HOME']=str(self.root/'home');Path(env['HOME']).mkdir(exist_ok=True)
        return subprocess.run([sys.executable,str(ROOT/'scripts/build_interchange_envelope.py'),*map(str,args)],cwd=self.root,env=env,capture_output=True,text=True,encoding='utf-8',timeout=30)
    def args(self,out):
        return ['--profile','shot-request','--payload',self.root/'artifact.json','--payload-type',self.kind,'--payload-id',self.envelope['payload']['artifact_id'],'--out',out]
    def test_bundled_capability_declaration(self):
        self.assertTrue(contract.validate_capabilities(self.caps)['ok'])
    def test_identical_declarations_receive_direction_is_explicit(self):
        result=self.check();self.assertTrue(result['ok'],result);self.assertEqual(result['interface_role'],'consumes');self.assertTrue(result['payload_verified']);self.assertFalse(result['canonical_adoption'])
    def test_outgoing_direction(self):
        result=self.check(direction='produces',declaration=None);self.assertTrue(result['ok'],result);self.assertEqual(result['interface_role'],'produces')
    def test_receive_requires_supplied_declaration(self):
        self.assertFalse(self.check(declaration=None)['ok'])
    def test_origin_binds_supplied_declaration(self):
        changed=copy.deepcopy(self.caps);changed['interfaces']['consumes']=[];changed=contract.finalize(changed,'manifest_sha256')
        self.assertFalse(self.check(declaration=changed)['ok'])
    def test_arbitrary_valid_declaration_not_software_identity(self):
        changed=copy.deepcopy(self.caps);changed['interfaces']['consumes']=[];changed=contract.finalize(changed,'manifest_sha256')
        v=copy.deepcopy(self.envelope);v['origin']['capability_manifest_sha256']=changed['manifest_sha256'];v=contract.finalize(v,'envelope_sha256')
        self.assertTrue(self.check(v,declaration=changed)['ok'])
    def test_unrecognized_optional_is_preserved(self):
        changed=copy.deepcopy(self.caps);row=contract.find_interface(changed,'produces','shot-request');row['supported_features']=sorted(row['supported_features']+['opaque-test-note']);row.update(contract.finalize(row,'profile_sha256'));changed=contract.finalize(changed,'manifest_sha256')
        v=copy.deepcopy(self.envelope);v['origin']['capability_manifest_sha256']=changed['manifest_sha256'];v['profile_sha256']=row['profile_sha256'];v['optional_features']=['opaque-test-note'];v['extensions']={'opaque-test-note':{'evidence':'kept without interpreting'}};v=contract.finalize(v,'envelope_sha256');before=copy.deepcopy(v)
        self.assertTrue(self.check(v,declaration=changed)['ok']);self.assertEqual(v,before)
    def test_required_feature_checked(self):
        changed=copy.deepcopy(self.caps);row=contract.find_interface(changed,'produces','shot-request');row['supported_features']=sorted(row['supported_features']+['missing-required']);row['required_features']=sorted(row['required_features']+['missing-required']);row.update(contract.finalize(row,'profile_sha256'));changed=contract.finalize(changed,'manifest_sha256')
        v=copy.deepcopy(self.envelope);v['origin']['capability_manifest_sha256']=changed['manifest_sha256'];v['profile_sha256']=row['profile_sha256'];v['required_features']=row['required_features'];v=contract.finalize(v,'envelope_sha256');self.assertFalse(self.check(v,declaration=changed)['ok'])
    def test_payload_identifier(self):
        v=copy.deepcopy(self.envelope);v['payload']['artifact_id']='another-artifact';v=contract.finalize(v,'envelope_sha256');self.assertFalse(self.check(v)['ok'])
    def test_payload_bytes(self):
        (self.root/'artifact.json').write_bytes(self.raw+b' ');self.assertFalse(self.check()['ok'])
    def test_payload_media_cannot_bypass_structure(self):
        raw=b'not a public artifact';(self.root/'artifact.json').write_bytes(raw)
        v=copy.deepcopy(self.envelope);v['payload']['media_type']='text/plain';v['payload']['sha256']=hashlib.sha256(raw).hexdigest();v=contract.finalize(v,'envelope_sha256')
        self.assertFalse(self.check(v)['ok'])
    def test_payload_structure_after_rehash(self):
        raw=b'{}';(self.root/'artifact.json').write_bytes(raw);v=copy.deepcopy(self.envelope);v['payload']['sha256']=hashlib.sha256(raw).hexdigest();v=contract.finalize(v,'envelope_sha256');self.assertFalse(self.check(v)['ok'])
    def test_data_path_containment(self):
        v=copy.deepcopy(self.envelope);v['payload']['path']='../artifact.json';v=contract.finalize(v,'envelope_sha256');self.assertFalse(self.check(v)['ok'])
    def test_declared_capability_path(self):
        (self.root/'config').mkdir();(self.root/'data').mkdir();(self.root/'data/declaration.json').write_text(json.dumps(self.caps), encoding='utf-8');(self.root/'config/protocol-layout.json').write_text(json.dumps({'capabilities':'data/declaration.json'}), encoding='utf-8')
        (self.root/'irrelevant').mkdir();(self.root/'irrelevant/integration-capabilities.json').write_text('{}',encoding='utf-8');self.assertEqual(contract.load_capabilities(self.root),self.caps)
    def test_malformed_declaration_is_reported(self):
        result=self.check(declaration={'artifact_type':'integration-capability-manifest','interfaces':None,'manifest_sha256':'x'});self.assertFalse(result['ok'])
    def test_every_declared_payload_roundtrip(self):
        for profile in self.caps['interfaces']['produces']:
            for kind in profile['artifact_types']:
                with self.subTest(kind=kind):
                    raw=(FIX/(kind+'.json')).read_bytes();(self.root/'artifact.json').write_bytes(raw)
                    result=self.check(self.make(raw,profile));self.assertTrue(result['ok'],result)
    def test_cli_new_bundle(self):
        out=self.root/'bundle';result=self.command(*self.args(out));self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual({p.name for p in out.iterdir()},{'artifact.json','declaration.json','envelope.json'});self.assertEqual((out/'artifact.json').read_bytes(),self.raw)
        report=contract.validate_envelope(contract.read_json(out/'envelope.json'),capabilities=self.caps,direction='consumes',declaration=contract.read_json(out/'declaration.json'),payload_root=out);self.assertTrue(report['ok'],report)
    def test_cli_existing_output_preserved(self):
        out=self.root/'bundle';out.mkdir();(out/'keep').write_text('keep',encoding='utf-8');result=self.command(*self.args(out));self.assertNotEqual(result.returncode,0);self.assertEqual((out/'keep').read_text(encoding='utf-8'),'keep')
    def test_cli_existing_lock_preserved(self):
        out=self.root/'bundle';lock=self.root/'.bundle.publish.lock';lock.write_text('owned by another operation',encoding='utf-8');result=self.command(*self.args(out));self.assertNotEqual(result.returncode,0);self.assertEqual(lock.read_text(encoding='utf-8'),'owned by another operation');self.assertFalse(out.exists())
    def test_strict_json(self):
        p=self.root/'bad.json';p.write_text('{"x":1,"x":2}',encoding="utf-8");self.assertRaises(ValueError,contract.read_json,p)

    def test_cli_reports_capability_subject(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / 'scripts/validate_integration.py')],
            cwd=self.root, capture_output=True, text=True, encoding="utf-8", timeout=30,
            env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'},
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report['capabilities']['ok'])
        self.assertTrue(report['self_test']['ok'])
        self.assertIsNone(report['envelope'])

    def test_unsupported_operation_names_capability_subject(self):
        configured = copy.deepcopy(self.caps)
        configured['interfaces']['consumes'] = []
        configured = contract.finalize(configured, 'manifest_sha256')
        report = self.check(capabilities=configured)
        self.assertFalse(report['ok'])
        self.assertIn(
            'configured capability declaration does not support the requested operation/profile',
            report['errors'],
        )

    def test_file_exchange_does_not_request_network_or_adopt(self):
        with patch('urllib.request.urlopen', side_effect=AssertionError('unexpected network access')):
            outgoing = protocol_exchange.export(self.root, 'artifact.json', 'outgoing')
            received = protocol_exchange.verify_bundle(self.root, 'outgoing')
        self.assertTrue(outgoing['ok'])
        self.assertTrue(received['ok'])
        self.assertFalse(outgoing['canonical_adoption'])
        self.assertFalse(received['canonical_adoption'])
        self.assertFalse(received['referenced_media_verified'])
        self.assertEqual((self.root / 'outgoing/artifact.json').read_bytes(), self.raw)

    def test_declared_file_path_is_confined_to_its_directory(self):
        self.assertEqual(contract.confined_path(self.root, 'artifact.json'), self.root / 'artifact.json')
        with self.assertRaisesRegex(ValueError, 'declared input directory'):
            contract.confined_path(self.root, '../outside.json')

if __name__=='__main__':
    import stdio_utf8
    stdio_utf8.configure()
    stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Boundary));sys.stderr.write(stream.getvalue());print(json.dumps({'ok':result.wasSuccessful(),'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped)}));raise SystemExit(not result.wasSuccessful())
