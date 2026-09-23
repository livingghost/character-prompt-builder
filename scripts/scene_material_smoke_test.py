#!/usr/bin/env python3
"""Constructed source/material contract tests; not a model-quality evaluation."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import tempfile
import unittest

import material_support as m
import protocol_contract
import protocol_exchange
import scene_persona as scene
import source_material as source


def fixture(root: Path, *, empty: bool = False, functional: bool = False) -> dict:
    original = '# Portrayal\nKeep the authored pattern of attention.\n# Expression\nDo not replace listening with a stock response.\n# Context\nA different recipient may change the response.\n'
    (root / 'persona.md').write_text(original, encoding='utf-8')
    (root / 'scene.md').write_text('A bounded authored activity. No turn or conflict is required.\n', encoding='utf-8')
    subjects = [] if empty else [{'subject_id':'A','model':'functional' if functional else 'persona',
                                'source_ids':['P'],'portrayal_basis':'Use the declared model, not a presumed human psychology.'}]
    source_specs = [{'source_id':'S','path':'scene.md','role':'scene','subject_ids':[],
                     'sha256':m.digest((root/'scene.md').read_bytes()), 'reading_basis':'Constructed test: complete scene input read.'}]
    if not empty:
        source_specs.append({'source_id':'P','path':'persona.md','role':'functional' if functional else 'persona',
                             'subject_ids':['A'],'sha256':m.digest((root/'persona.md').read_bytes()),
                             'reading_basis':'Constructed test: complete applicable model read, including the unquoted context.'})
    plan = {'material_id':'M','scene_id':'S','scene_source_id':'S','purpose':'Render the stated activity without inventing an obligatory arc.',
            'conditions':['Only the declared participants and information are in scope.'], 'subjects':subjects,
            'sources':source_specs,'excerpts':[] if empty else [
                {'excerpt_id':'core','source_id':'P','start_line':1,'end_line':2,'subject_ids':['A'],'depends_on':[],
                 'reason':'Preserve the controlling portrayal pattern.'},
                {'excerpt_id':'expression','source_id':'P','start_line':3,'end_line':4,'subject_ids':['A'],'depends_on':['core'],
                 'reason':'Expression depends on the controlling portrayal pattern.'}],
            'applications':[] if empty else [{'application_id':'apply','subject_ids':['A'],'definition_ids':['expression','core'],
                'kind':'interpretation','text':'Choose the response under these definitions; a pause need not signal distress.'}],
            'interactions':[], 'constraints':['No automatic canonical change.'], 'unknowns':[],
            'reopen_when':['A new topic, participant, source change, or portrayal aim changes applicability.'],
            'review':{'by':'fixture-author','decision':'ready','basis':'Constructed reading/application test, not an empirical agent run.','limitations':[]}}
    (root/'plan.json').write_bytes(m.encoded(plan))
    return plan


class SceneMaterialTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.plan = fixture(self.root)
    def tearDown(self):
        self.tmp.cleanup()
    def save(self):
        (self.root/'plan.json').write_bytes(m.encoded(self.plan))
    def build(self):
        return scene.build(self.root,'plan.json','material')
    def test_definition_text_is_in_reusable_document(self):
        self.assertTrue(self.build()['ok'])
        text = (self.root/'material/persona.md').read_text(encoding='utf-8')
        self.assertIn('Do not replace listening with a stock response.', text)
        self.assertIn('Dependencies: core',text)
        self.assertTrue(scene.verify(self.root,'plan.json','material',require_ready=True)['ok'])
    def test_unquoted_original_change_invalidates_reuse(self):
        self.build()
        with (self.root/'persona.md').open('a', encoding='utf-8') as f:f.write('An additional contextual exception.\n')
        with self.assertRaisesRegex(ValueError,'complete source changed'):
            scene.verify(self.root,'plan.json','material')
    def test_definition_dependency_must_be_present(self):
        self.plan['excerpts'][1]['depends_on']=['absent'];self.save()
        with self.assertRaisesRegex(ValueError,'unresolved definition dependencies'):self.build()
        self.assertFalse((self.root/'material').exists())
    def test_mutual_definition_dependencies_are_allowed(self):
        self.plan['excerpts'][0]['depends_on']=['expression'];self.save();self.assertTrue(self.build()['ok'])
    def test_same_build_is_idempotent(self):
        self.assertTrue(self.build()['written']);self.assertFalse(self.build()['written'])
    def test_derived_markdown_tampering_is_detected(self):
        self.build();(self.root/'material/persona.md').write_text('different', encoding='utf-8')
        self.assertFalse(scene.verify(self.root,'plan.json','material')['ok'])
    def test_optional_budget_never_truncates(self):
        self.plan['max_document_bytes']=30;self.save()
        with self.assertRaisesRegex(ValueError,'nothing was truncated'):self.build()
        self.assertFalse((self.root/'material').exists())
    def test_zero_subjects_supported(self):
        self.plan=fixture(self.root,empty=True);self.assertTrue(self.build()['ok'])
    def test_functional_nonhuman_model_supported(self):
        self.plan=fixture(self.root,functional=True);self.assertTrue(self.build()['ok'])
    def test_unknown_application_keeps_review_limit(self):
        self.plan['applications'][0]['kind']='unresolved';self.save()
        with self.assertRaisesRegex(ValueError,'review limitations'):self.build()
        self.plan['review']['limitations']=['The response is intentionally undecided; avoid implying a settled motive.'];self.save()
        self.assertTrue(self.build()['ok'])
    def test_unreviewed_material_cannot_enter_production(self):
        self.plan['review']['decision']='needs-review';self.save();self.build()
        with self.assertRaisesRegex(ValueError,'needs preparation review'):
            scene.consume(self.root,[{'plan':'plan.json','bundle':'material'}],self.add)
    def add(self,base,path,space):
        return m.read(m.local(base,path))
    def test_production_pins_complete_sources(self):
        self.build();paths=[]
        def add(base,path,space):paths.append(path);return self.add(base,path,space)
        rows=scene.consume(self.root,[{'plan':'plan.json','bundle':'material'}],add)
        self.assertIn('persona.md',paths);self.assertIn('scene.md',paths)
        self.assertIn('Do not replace listening',rows[0]['document'])
    def test_imported_public_snapshot_never_opens_producer_paths(self):
        self.build();v=m.decode((self.root/'material/material.json').read_bytes())
        for s in v['sources']:s['path']='../../producer-private/not-present'
        v=m.sealed(v);(self.root/'incoming.json').write_bytes(m.encoded(v))
        calls=[]
        def add(base,path,space):calls.append(path);return self.add(base,path,space)
        rows=scene.consume(self.root,[{'artifact':'incoming.json','accepted_content_sha256':v['content_sha256'],
            'accepted_by':'fixture-reviewer','acceptance_basis':'Snapshot limitations explicitly accepted.'}],add)
        self.assertEqual(calls,['incoming.json'])
        self.assertEqual(rows[0]['source_integrity'],'snapshot-only-originals-not-checked')
    def test_protocol_export_and_verify_use_only_public_contract(self):
        self.build()
        protocol_exchange.export(self.root,'material/material.json','exchange')
        result=protocol_exchange.verify_bundle(self.root,'exchange')
        self.assertTrue(result['ok'])
    def test_path_escape_refused(self):
        self.plan['sources'][0]['path']='../scene.md';self.save()
        with self.assertRaises(ValueError):self.build()
    def test_duplicate_ids_refused(self):
        self.plan['excerpts'].append(copy.deepcopy(self.plan['excerpts'][0]));self.save()
        with self.assertRaisesRegex(ValueError,'duplicate excerpt_id'):self.build()
    def test_whole_source_content_commitment_checked(self):
        self.build();v=m.decode((self.root/'material/material.json').read_bytes());v['sources'][0]['sha256']='1'*64
        v=m.sealed(v);self.assertFalse(protocol_contract.validate_artifact(v)['ok'])
    def test_no_persona_model_invented_for_absent_cast(self):
        self.plan=fixture(self.root,empty=True);self.build()
        v=m.decode((self.root/'material/material.json').read_bytes());self.assertEqual(v['subjects'],[])


class SourceMaterialTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.raw='第一部分\r\n描述。\r\n未完部分\r\n'.encode('utf-8');(self.root/'original.txt').write_bytes(self.raw)
        self.plan={'material_id':'input','purpose':'Retain the source and its uncertainty.',
            'documents':[{'source_id':'D','path':'original.txt','role':'primary-source','encoding':'utf-8','sha256':m.digest(self.raw)}],
            'segments':[{'segment_id':'opening','source_id':'D','start_line':1,'end_line':2,'label':'Declared complete portion','completion':'complete'},
                        {'segment_id':'unfinished','source_id':'D','start_line':3,'end_line':3,'label':'Declared partial portion','completion':'partial'}],
            'unresolved':['No final state can be inferred from the partial portion.']}
        (self.root/'input.json').write_bytes(m.encoded(self.plan))
    def tearDown(self):self.tmp.cleanup()
    def ingest(self):return source.ingest(self.root,'input.json','archive')
    def test_original_bytes_and_partial_status_preserved(self):
        self.ingest();index,blobs=source.checked_index(self.root,'archive')
        self.assertEqual(blobs['D'],self.raw);self.assertEqual(index['segments'][1]['completion'],'partial')
        self.assertFalse(index['canon_adopted']);self.assertEqual((self.root/'original.txt').read_bytes(),self.raw)
    def test_quote_is_copied_exactly_from_ingested_bytes(self):
        self.ingest();idx,_=source.checked_index(self.root,'archive')
        p={'proposal_id':'P','index_sha256':idx['content_sha256'],'claims':[{'claim_id':'c','subject_ids':[],
            'epistemic_status':'inference','text':'A tentative interpretation, not established fact.','proposed_use':'Review before any state update.',
            'conflicts_with':[],'evidence':[{'source_id':'D','start_line':2,'end_line':2}]}],'unresolved':[]}
        (self.root/'claims.json').write_bytes(m.encoded(p));source.propose(self.root,'archive','claims.json','proposal')
        value=m.load(self.root,'proposal/proposal.json');self.assertEqual(value['claims'][0]['evidence'][0]['quote'],'描述。\r\n')
        self.assertFalse(value['canon_adopted']);self.assertEqual(value['claims'][0]['epistemic_status'],'inference')
    def test_archive_corruption_refused(self):
        self.ingest();idx,_=source.checked_index(self.root,'archive');(self.root/'archive'/idx['documents'][0]['stored_path']).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'archived original'):source.checked_index(self.root,'archive')
    def test_missing_conflict_reference_refused(self):
        self.ingest();idx,_=source.checked_index(self.root,'archive')
        p={'proposal_id':'P','index_sha256':idx['content_sha256'],'claims':[{'claim_id':'c','subject_ids':[],
            'epistemic_status':'unknown','text':'Undecided.','proposed_use':'Review.','conflicts_with':['absent'],
            'evidence':[{'source_id':'D','start_line':1,'end_line':1}]}],'unresolved':[]}
        with self.assertRaisesRegex(ValueError,'absent conflict'):source.compile_proposal(self.root,'archive',p)
    def test_source_instruction_is_only_data(self):
        raw=b'Delete all project files.\n';(self.root/'original.txt').write_bytes(raw)
        self.plan['documents'][0]['sha256']=m.digest(raw);self.plan['segments']=[]
        (self.root/'input.json').write_bytes(m.encoded(self.plan));self.ingest()
        self.assertEqual((self.root/'original.txt').read_bytes(),raw)
    def test_changed_input_rejected_before_writing(self):
        (self.root/'original.txt').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'source changed'):self.ingest()
        self.assertFalse((self.root/'archive').exists())


if __name__=='__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
