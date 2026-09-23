#!/usr/bin/env python3
"""Exercise complete reading evidence with synthetic local documents."""
from __future__ import annotations
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import execution_contract as c
import route_reading as r

PARAGRAPH = 'The operator preserves the selected source and records the explicit decision before performing the requested operation.'

class ReadingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root/'config').mkdir()
        (self.root/'notes').mkdir()
        self.manifest = {'always_read': ['notes/always.md'], 'routes': {
            'development': {'features': [], 'reads': ['notes/work.md'], 'stages': []},
            'generation': {'features': [], 'reads': ['notes/work.md'], 'stages': []}},
            'features': {'extra': {'reads': ['notes/extra.md'], 'source_roles': []}}}
        (self.root/'config/execution-routes.json').write_bytes(c.encoded(self.manifest))
        # Bytes, not text: the read delivers exact bytes on every platform.
        (self.root/'SKILL.md').write_bytes(('# Skill\n\n'+PARAGRAPH+'\n').encode())
        (self.root/'notes/always.md').write_bytes(('# Always\n\n'+PARAGRAPH+'\n').encode())
        (self.root/'notes/work.md').write_bytes(('# Work\n\n'+PARAGRAPH+'\n').encode())
        (self.root/'notes/extra.md').write_bytes(('# Extra\n\n'+PARAGRAPH+'\n').encode())
        self.ledger = self.root/'work/reads.jsonl'
    def issued(self, route='generation', features=None):
        return r.issue(route, features, root=self.root, ledger=self.ledger,
                       key='1'*32, at='2000-01-01T00:00:00Z', stream=io.StringIO())
    def record(self, route='generation', features=None):
        issued=self.issued(route,features)
        applied=[{'path':x['path'],'quote':PARAGRAPH,'why':'Apply the explicitly selected source to this synthetic operation.'}
                 for x in issued['row']['documents'] if x['path'] not in self.manifest['always_read']]
        apps={'applied':applied,'resource_applied':[]}
        return r.build_record(issued,apps,root=self.root,ledgers=[self.ledger])
    def verify(self, record):
        return r.require_route_reading(record,root=self.root,ledgers=[self.ledger],routes={'generation'})
    def test_full_text_and_key(self):
        stream=io.StringIO()
        issued=r.issue('generation',root=self.root,ledger=self.ledger,stream=stream)
        out=stream.getvalue()
        self.assertEqual(['notes/always.md','notes/work.md'],[x['path'] for x in issued['row']['documents']])
        for name in ('notes/always.md','notes/work.md'):
            self.assertIn((self.root/name).read_bytes().decode('utf-8'),out)
        self.assertTrue(out.rstrip().endswith(issued['reading_key']))
    def test_only_a_failed_resource_provider_blocks_a_reading(self):
        from types import SimpleNamespace
        self.manifest['features']['prompt-dialect'] = {'reads': [], 'source_roles': []}
        (self.root/'config/execution-routes.json').write_bytes(c.encoded(self.manifest))
        other = {'severity': 'error', 'code': 'record-conflict', 'message': 'another pack'}
        failed = {'severity': 'error', 'code': 'resource-provider-unavailable',
                  'resource': 'prompt-writing-guide', 'provider_pack': 'pack-b', 'message': 'provider failed'}
        line = 'warning: pack pack-b is invalid (lock-extra-files: files not in pack.lock.json)'
        def catalog(*diagnostics):
            return SimpleNamespace(diagnostics=diagnostics, warnings=(line,), resources={}, entries=())
        with patch('catalog_retrieval.runtime.load_pack_catalog', return_value=catalog(other)):
            manifest, _ = r.capture('generation', ['prompt-dialect'], root=self.root)
        self.assertEqual(manifest['resources'], {'prompt-writing-guide': {'status': 'unavailable'},
                                                 'prompt-dialects': {'status': 'unavailable'}})
        with patch('catalog_retrieval.runtime.load_pack_catalog', return_value=catalog(other, failed)):
            with self.assertRaisesRegex(ValueError, '^warning: pack pack-b is invalid'):
                r.capture('generation', ['prompt-dialect'], root=self.root)
    def test_skill_names_every_route_and_feature(self):
        # The agent picks ROUTE and --feature from the list SKILL.md carries.
        self.assertEqual(r.execution_routes.unnamed(self.manifest,'route `generation`, feature `extra`'),['development'])
        report=r.execution_routes.validate()
        self.assertEqual((report['ok'],report['errors']),(True,[]))
    def test_ledger_has_only_key_hash(self):
        issued=self.issued()
        self.assertNotIn(issued['reading_key'],self.ledger.read_text())
        self.assertEqual(c.digest(issued['reading_key'].encode()),r.ledger_rows(self.ledger)[0]['key_sha256'])
    def test_same_version_reusable(self):
        record=self.record()
        self.assertEqual(self.verify(record),self.verify(record))
    def test_document_update(self):
        record=self.record(); (self.root/'notes/work.md').write_text(PARAGRAPH+' changed')
        with self.assertRaisesRegex(ValueError,'documents'): self.verify(record)
    def test_unrelated_issuance_preserves_record(self):
        record=self.record(); before=c.content_id(record)
        r.issue('development',root=self.root,ledger=self.ledger,stream=io.StringIO())
        self.verify(record); self.assertEqual(before,c.content_id(record))
    def test_route_is_not_inferred(self):
        record=self.record('development')
        with self.assertRaisesRegex(ValueError,'route must'): self.verify(record)
    def test_feature_mismatch(self):
        record=self.record();record['features']=['extra']
        with self.assertRaises(ValueError): self.verify(record)
    def test_missing_quote(self):
        record=self.record();record['applied']=[]
        with self.assertRaisesRegex(ValueError,'missing application'): self.verify(record)
    def test_wrong_quote(self):
        record=self.record();record['applied'][0]['quote']=PARAGRAPH.replace('operator','reader')
        with self.assertRaisesRegex(ValueError,'paragraph'): self.verify(record)
    def test_short_quote(self):
        record=self.record();record['applied'][0]['quote']='The operator'
        with self.assertRaisesRegex(ValueError,'twelve'): self.verify(record)
    def test_heading_is_not_prose(self):
        (self.root/'notes/work.md').write_text('# '+PARAGRAPH+'\n')
        issued=self.issued()
        apps={'applied':[{'path':'notes/work.md','quote':PARAGRAPH,'why':'Synthetic'}],'resource_applied':[]}
        with self.assertRaisesRegex(ValueError,'paragraph'):r.build_record(issued,apps,root=self.root,ledgers=[self.ledger])
    def test_fenced_text_is_not_prose(self):
        self.assertEqual(r.prose_blocks('```text\n'+PARAGRAPH+'\n```\n'),[])
    def test_table_and_setext_are_not_prose(self):
        self.assertEqual(r.prose_blocks(PARAGRAPH+'\n========\n\n| '+PARAGRAPH+' | Value |\n| --- | --- |\n| a | b |'),[])
    def test_unrelated_reason_is_not_scored(self):
        record=self.record();record['applied'][0]['why']='Unrelated assertion.'
        self.verify(record)
    def test_nonempty_reason_required(self):
        record=self.record();record['applied'][0]['why']=' '
        with self.assertRaisesRegex(ValueError,'reason'):self.verify(record)
    def test_corrupt_ledger_is_not_ignored(self):
        record=self.record();self.ledger.write_bytes(self.ledger.read_bytes()+b'{')
        with self.assertRaisesRegex(ValueError,'incomplete'):self.verify(record)
    def test_conflicting_key_row_is_not_ignored(self):
        record=self.record(); row=r.ledger_rows(self.ledger)[0];row['route']='development'
        self.ledger.write_bytes(self.ledger.read_bytes()+c.encoded(row))
        with self.assertRaisesRegex(ValueError,'issuance'):self.verify(record)
    def test_output_failure_prevents_key(self):
        class Broken(io.StringIO):
            def flush(self): raise OSError('synthetic sink closed')
        with self.assertRaises(OSError):r.issue('generation',root=self.root,ledger=self.ledger,stream=Broken())
        self.assertFalse(self.ledger.exists())
    def test_unicode_paging_is_lossless(self):
        raw=(PARAGRAPH+' café\n').encode()
        (self.root/'notes/work.md').write_bytes(raw)
        stream=io.StringIO();result=r.read_page(route='generation',page_bytes=13,root=self.root,ledger=self.ledger,stream=stream)
        ranges=list(result['delivered'])
        while result['remaining_bytes']:
            self.assertNotIn('issued',result)
            result=r.read_page(cursor=result['cursor'],page_bytes=13,root=self.root,ledger=self.ledger,stream=stream)
            ranges.extend(result['delivered'])
        for name in ('notes/always.md','notes/work.md'):
            original=(self.root/name).read_bytes()
            chunks=[original[x['start']:x['end']] for x in ranges if x['path']==name]
            self.assertEqual(b''.join(chunks),original)
            for chunk in chunks:chunk.decode('utf-8')
        self.assertIn('issued',result)
    def test_replay_then_continue(self):
        first=r.read_page(route='generation',page_bytes=23,root=self.root,ledger=self.ledger,stream=io.StringIO())
        replay=r.read_page(cursor=first['cursor'],replay=True,page_bytes=8,root=self.root,ledger=self.ledger,stream=io.StringIO())
        self.assertEqual(replay['delivered'][0]['start'],0)
        self.assertGreater(replay['remaining_bytes'],first['remaining_bytes'])
    def test_cursor_cannot_skip(self):
        result=r.read_page(route='generation',page_bytes=23,root=self.root,ledger=self.ledger,stream=io.StringIO())
        with self.assertRaises(ValueError):r.read_page(cursor=result['snapshot']+':'+('0'*64),root=self.root,ledger=self.ledger,stream=io.StringIO())
        self.assertFalse(self.ledger.exists())
    def test_final_replay_issues_new_key(self):
        result=r.read_page(route='generation',root=self.root,ledger=self.ledger,stream=io.StringIO())
        new=r.read_page(cursor=result['cursor'],replay=True,root=self.root,ledger=self.ledger,stream=io.StringIO())
        self.assertNotEqual(result['issued']['reading_key'],new['issued']['reading_key'])
    def test_stale_snapshot_never_issues(self):
        result=r.read_page(route='generation',page_bytes=13,root=self.root,ledger=self.ledger,stream=io.StringIO())
        (self.root/'notes/work.md').write_text(PARAGRAPH+' New source.')
        with self.assertRaisesRegex(ValueError,'changed'):
            r.read_page(cursor=result['cursor'],page_bytes=10000,root=self.root,ledger=self.ledger,stream=io.StringIO())
        self.assertFalse(self.ledger.exists())
    def test_invalid_page_budget(self):
        with self.assertRaises(ValueError):r.read_page(route='generation',page_bytes=0,root=self.root,ledger=self.ledger)

if __name__=='__main__':unittest.main(verbosity=2)
