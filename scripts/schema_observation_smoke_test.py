#!/usr/bin/env python3
"""Synthetic schema acquisition and atomic publication tests; no provider is called."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import execution_contract as c
from input_evidence import InputEvidence
import schema_observation as observation
import request_validation as rv

class AcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.target={'service':'synthetic','model_identifier':'synthetic:one','operation':'generate'}
        self.schema={'type':'object','properties':{'seed':{'type':'integer'}}}
        self.raw=b'{ "schema" : '+json.dumps(self.schema).encode()+b', "notes": "synthetic source" }\n'
        (self.root/'response.json').write_bytes(self.raw)
        self.acquisition={'artifact_type':'schema-acquisition','target':self.target,
            'source':{'kind':'document','identifier':'Synthetic source','locator':'schema'},
            'acquired_at':'2000-01-01T00:00:00Z','response':{'path':'response.json','sha256':c.digest(self.raw)},
            'status':{'document_status':'schema-provided'}}
        self.save()
    def save(self): (self.root/'acquisition.json').write_bytes(c.encoded(self.acquisition))
    def assemble(self,**changes):
        args=dict(target=self.target,acquisition='acquisition.json',pointer='/schema',prefix='evidence',kind='schema')
        args.update(changes);return observation.assemble(self.root,**args)
    def test_original_response_bytes_are_preserved(self):
        files,manifest=self.assemble();self.assertEqual(files['response.json'],self.raw)
        observation.publish(self.root,'evidence',files)
        rv.schema_contract(c.decode(files['contract.json']),c.decode(files['acquisition.json']),InputEvidence(self.root),self.target)
    def test_source_target_cannot_be_relabelled(self):
        self.acquisition['target']=dict(self.target,model_identifier='other');self.save()
        with self.assertRaises(ValueError):self.assemble()
        self.assertFalse((self.root/'evidence').exists())
    def test_reference_keeps_source_identity(self):
        self.acquisition['target']=dict(self.target,model_identifier='source-only');self.save()
        (self.root/'relationship.txt').write_text('Synthetic author-selected reference; not a target observation.')
        ref={'path':'relationship.txt','sha256':c.digest(c.read(self.root/'relationship.txt')),'locator':'whole'}
        files,manifest=self.assemble(kind='reference',relationship=ref)
        self.assertEqual(c.decode(files['reference.json'])['source_target'],self.acquisition['target'])
        self.assertNotIn('contract.json',files)
    def test_no_relationship_is_inferred_from_names(self):
        with self.assertRaises(ValueError):self.assemble(kind='reference')
    def test_overlay_never_changes_acquired_schema(self):
        (self.root/'basis.txt').write_text('Synthetic adapter envelope.')
        value={'artifact_type':'request-envelope-overlay','target':self.target,'fields':{'taskType':{'type':'string'}},
            'basis':{'path':'basis.txt','sha256':c.digest(c.read(self.root/'basis.txt')),'locator':'whole'}}
        (self.root/'overlay.json').write_bytes(c.encoded(value))
        files,_=self.assemble(overlay='overlay.json')
        self.assertEqual(c.decode(files['contract.json'])['schema'],self.schema)
        self.assertEqual(files['response.json'],self.raw);self.assertIn('overlay.json',files)
    def test_http_failure_is_not_schema_observation(self):
        self.acquisition.update(source={'kind':'http','identifier':'Synthetic endpoint','locator':'body'},
            status={'http_status':404,'transport_outcome':'completed'});self.save()
        with self.assertRaises(ValueError):self.assemble()
    def test_changed_response_witness_refused(self):
        (self.root/'response.json').write_text('{}')
        with self.assertRaises(ValueError):self.assemble()
    def test_existing_destination_is_preserved(self):
        files,_=self.assemble();observation.publish(self.root,'evidence',files)
        original=(self.root/'evidence/manifest.json').read_bytes()
        with self.assertRaises(FileExistsError):observation.publish(self.root,'evidence',files)
        self.assertEqual((self.root/'evidence/manifest.json').read_bytes(),original)
    def test_no_network_in_schema_assembly(self):
        with patch('urllib.request.urlopen',side_effect=AssertionError('unexpected network')):self.assemble()
    def test_pointer_selects_structure_not_words(self):
        with self.assertRaises(ValueError):self.assemble(pointer='/synthetic')

class PackImportTests(AcquisitionTests):
    def setUp(self):
        super().setUp()
        import generation_payload_smoke_test as fixtures
        import pack_manager as pm
        self.pack=self.root/'pack';fixtures._write_fixture_pack(self.pack);pm.write_lock(self.pack)
        from observe_model_schema import _selection
        _,self.document,i,j=_selection(self.pack,fixtures.OFFERED_MODEL_ID,'runware')
        offering=self.document['records'][i]['offerings'][j]
        self.target={'service':'runware','model_identifier':offering['model_identifier'],'operation':'imageInference'}
        self.schema=c.load(self.pack/offering['schema_snapshot'])['schema']
        self.raw=c.encoded({'schema':self.schema,'notes':'Synthetic source matching the fixture offering.'})
        (self.root/'response.json').write_bytes(self.raw)
        self.acquisition['response']['sha256']=c.digest(self.raw)
        self.acquisition['target']=self.target;self.save()
        self.args=SimpleNamespace(command='schema',root=self.root,pack=self.pack,out_pack=self.root/'published',
            release='2026.09.22.1',model=fixtures.OFFERED_MODEL_ID,service='runware',operation='imageInference',entry='trial',
            acquisition='acquisition.json',pointer='/schema',overlay=None)
    def test_schema_command_rebuilds_full_pack_lock(self):
        import observe_model_schema as cli,pack_manager as pm
        before=c.read(self.pack/'records/models.json')
        result=cli.publish(self.args)
        self.assertTrue(result['ok']);self.assertEqual(c.read(self.pack/'records/models.json'),before)
        self.assertTrue(pm.validate_pack(self.args.out_pack,require_lock=True,verify_lock=True).valid)
        _,document,i,j=cli._selection(self.args.out_pack,self.args.model,'runware')
        offering=document['records'][i]['offerings'][j]
        self.assertTrue((self.args.out_pack/offering['schema_contract']['path']).is_file())
    def test_schema_error_does_not_publish_partial_pack(self):
        import observe_model_schema as cli
        self.acquisition['target']=dict(self.target,model_identifier='other');self.save()
        with self.assertRaises(ValueError):cli.publish(self.args)
        self.assertFalse(self.args.out_pack.exists())

if __name__=='__main__':unittest.main(verbosity=2)
