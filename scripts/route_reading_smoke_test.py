#!/usr/bin/env python3
"""Exercise complete reading evidence with synthetic local documents."""
from __future__ import annotations
import copy
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
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
    def test_species_doctrine_comes_only_with_body_plan(self):
        manifest=c.load(r.ROOT/r.execution_routes.MANIFEST)
        species={'references/morphology-and-species-contracts.md','references/species-architecture.md'}
        carriers={name for group in ('features','routes') for name,entry in manifest[group].items()
                  if species & set(entry['reads'])}
        self.assertEqual(carriers,{'body-plan'})
        self.assertEqual(manifest['features']['recurring-identity']['reads'],['references/character-identity-contract.md'])
    def test_a_route_reads_only_what_its_tasks_use(self):
        manifest=c.load(r.ROOT/r.execution_routes.MANIFEST)
        prompt_only=r.execution_routes.resolve('prompt-only')
        self.assertEqual([x['path'] for x in prompt_only['reads']],
                         manifest['always_read']+['references/runtime/prompt-only-core.md'])
        self.assertEqual(r.execution_routes.resolve('repose')['features'],['prompt-dialect','reference-delivery','studio'])
    def test_draft_holds_the_read_and_no_application(self):
        issued=self.issued()
        draft=r.draft_record(issued)
        self.assertEqual((draft['route'],draft['features'],draft['reading_key'],draft['documents'],draft['resources']),
                         ('generation',[],issued['reading_key'],issued['row']['documents'],{}))
        self.assertEqual((draft['applied'],draft['resource_applied']),([],[]))
        self.verify(draft)
        draft['applied'].append({'path':'notes/work.md','quote':None,'why':None})
        with self.assertRaisesRegex(ValueError,'notes/work.md: quotation'):self.verify(draft)
        draft['applied'][0].update(quote=PARAGRAPH,why='Apply the selected source to this synthetic operation.')
        self.verify(draft)
    def test_only_the_documents_the_author_applies_carry_quotations(self):
        self.manifest['routes']['generation']['features']=['extra']
        (self.root/'config/execution-routes.json').write_bytes(c.encoded(self.manifest))
        issued=self.issued()
        self.assertEqual([x['path'] for x in issued['row']['documents']],['notes/always.md','notes/work.md','notes/extra.md'])
        record=r.draft_record(issued)
        record['applied'].append({'path':'notes/extra.md','quote':PARAGRAPH,'why':'Synthetic application of one read document.'})
        self.verify(record)
        record['applied'][0]['quote']='The operator preserves the selected source.'
        with self.assertRaisesRegex(ValueError,'twelve words of paragraph text: notes/extra.md'):self.verify(record)
    def test_draft_is_written_once(self):
        issued=self.issued()
        path=r.write_draft(issued,self.ledger)
        self.assertEqual(path,self.root/'work/readings'/('generation-'+issued['row']['key_sha256'][:16]+'.json'))
        filled=c.load(path);filled['applied'].append({'path':'notes/work.md','quote':PARAGRAPH,'why':'Synthetic application.'})
        path.write_text(json.dumps(filled), encoding="utf-8")
        self.assertEqual(r.write_draft(issued,self.ledger),path)
        self.assertEqual(c.load(path),filled)
    def test_cli_read_prints_the_draft_path(self):
        env={k:v for k,v in os.environ.items() if k!='CPB_READS_LEDGER'}
        state=self.root/'runtime'
        run=subprocess.run([sys.executable,str(r.ROOT/'scripts/execution_routes.py'),'read','development',
                            '--root',str(self.root),'--state-file',str(state/'state.json'),
                            '--cache-dir',str(state/'cache'),'--managed-root',str(state/'managed')],
                           capture_output=True,text=True,encoding='utf-8',env=env,check=False)
        self.assertEqual(run.returncode,0,run.stdout[-2000:]+run.stderr)
        last=run.stdout.rstrip().splitlines()[-1]
        self.assertTrue(last.startswith('reading-record: work/readings/development-'),last)
        draft=c.load(self.root/last.split(': ',1)[1])
        self.assertEqual((draft['route'],draft['applied'],draft['resource_applied']),('development',[],[]))
    def family_catalog(self):
        pack=self.root/'pack';(pack/'resources').mkdir(parents=True)
        rule='Synthetic rule for {} gives the rendition one clear priority and records it in the delivered prompt.'
        guide={'format':'synthetic','name':'Synthetic guide','description':'Synthetic fixture.','sections':[
            {'id':'every','title':'Every family','rules':[rule.format('every family')]},
            {'id':'first','title':'First family','dialects':['family-a'],'rules':[rule.format('the first family')]},
            {'id':'second','title':'Second family','dialects':['family-b'],'rules':[rule.format('the second family')]}]}
        family=lambda name:{'id':name,'name':name,'description':'Synthetic family.','tag_separator':', ',
                            'block_order':['subject','scene']}
        dialects={'format':'character-prompt-builder-prompt-dialects','name':'Synthetic dialects',
                  'description':'Synthetic fixture.','dialects':[family('family-a'),family('family-b')]}
        (pack/'resources/guide.json').write_text(json.dumps(guide), encoding='utf-8')
        (pack/'resources/dialects.json').write_text(json.dumps(dialects), encoding='utf-8')
        self.manifest['features']['prompt-dialect']={'reads':[],'source_roles':[]}
        (self.root/'config/execution-routes.json').write_bytes(c.encoded(self.manifest))
        resources={'prompt-writing-guide':SimpleNamespace(path=str(pack/'resources/guide.json'),source_pack='synthetic-pack'),
                   'prompt-dialects':SimpleNamespace(path=str(pack/'resources/dialects.json'),source_pack='synthetic-pack')}
        catalog=SimpleNamespace(diagnostics=(),warnings=(),resources=resources,
                                entries=(SimpleNamespace(source_pack='synthetic-pack',source_root=pack),))
        return patch('catalog_retrieval.runtime.load_pack_catalog',return_value=catalog),guide
    def family_record(self,dialect,section):
        stream=io.StringIO()
        issued=r.issue('generation',['prompt-dialect'],root=self.root,ledger=self.ledger,stream=stream,dialect=dialect)
        record=r.draft_record(issued)
        record['applied'].append({'path':'notes/work.md','quote':PARAGRAPH,'why':'Synthetic application.'})
        record['resource_applied'].append({'resource':'prompt-writing-guide','pointer':f'/sections/{section}/rules/0',
                                           'why':'Synthetic rule application.','quote':self.guide['sections'][section]['rules'][0]})
        return record,stream.getvalue()
    def test_model_family_reading_withholds_other_family_sections(self):
        catalog,self.guide=self.family_catalog()
        with catalog:
            record,out=self.family_record('family-a',1)
            self.assertIn(self.guide['sections'][1]['rules'][0],out)
            self.assertNotIn(self.guide['sections'][2]['rules'][0],out)
            self.assertIn('"id": "second",\n      "dialects": [\n        "family-b"\n      ]\n    }',out)
            self.assertEqual({x['dialect'] for x in record['resources'].values()},{'family-a'})
            r.require_route_reading(record,root=self.root,ledgers=[self.ledger],dialect='family-a')
            with self.assertRaisesRegex(ValueError,'read the route again with --model'):
                r.require_route_reading(record,root=self.root,ledgers=[self.ledger],dialect='family-b')
            withheld,_=self.family_record('family-a',2)
            with self.assertRaisesRegex(ValueError,'guide pointer has no rule'):
                r.require_route_reading(withheld,root=self.root,ledgers=[self.ledger])
            universal,out=self.family_record(None,0)
            self.assertNotIn(self.guide['sections'][1]['rules'][0],out)
            r.require_route_reading(universal,root=self.root,ledgers=[self.ledger],dialect=None)
            with self.assertRaisesRegex(ValueError,'read the route again'):
                r.require_route_reading(universal,root=self.root,ledgers=[self.ledger],dialect='family-a')
    def test_reading_without_a_model_holds_every_family(self):
        catalog,self.guide=self.family_catalog()
        with catalog:
            record,out=self.family_record(r.EVERY_FAMILY,2)
            self.assertIn(self.guide['sections'][1]['rules'][0],out)
            self.assertIn(self.guide['sections'][2]['rules'][0],out)
            self.assertFalse(any('dialect' in x for x in record['resources'].values()))
            r.require_route_reading(record,root=self.root,ledgers=[self.ledger],dialect='family-b')
            with self.assertRaisesRegex(ValueError,'does not apply'):
                r.require_route_reading(record,root=self.root,ledgers=[self.ledger],dialect='family-a')
    def test_paged_family_reading_issues_its_family(self):
        catalog,self.guide=self.family_catalog()
        with catalog:
            stream=io.StringIO()
            result=r.read_page(route='generation',features=['prompt-dialect'],page_bytes=300,dialect='family-a',
                               root=self.root,ledger=self.ledger,stream=stream)
            while 'issued' not in result:
                result=r.read_page(cursor=result['cursor'],page_bytes=300,root=self.root,ledger=self.ledger,stream=stream)
        self.assertNotIn(self.guide['sections'][2]['rules'][0],stream.getvalue())
        self.assertEqual({x['dialect'] for x in result['issued']['row']['resources'].values()},{'family-a'})
    def test_read_command_takes_the_family_from_the_model_record(self):
        import argparse,contextlib,prepare_generation_references
        catalog,self.guide=self.family_catalog()
        parser=argparse.ArgumentParser();r.add_read_arguments(parser)
        state=self.root/'runtime'
        args=parser.parse_args(['generation','--root',str(self.root),'--model','synthetic-model',
                                '--state-file',str(state/'state.json'),'--cache-dir',str(state/'cache'),
                                '--managed-root',str(state/'managed')])
        out=io.StringIO()
        record=('synthetic-model',{'prompt_dialect':'family-b'})
        with (catalog,patch.object(prepare_generation_references,'resolve_model_record',return_value=record),
              patch.dict(os.environ),contextlib.redirect_stdout(out)):
            os.environ.pop('CPB_READS_LEDGER',None)
            r.read_command(args,parser)
        self.assertNotIn(self.guide['sections'][1]['rules'][0],out.getvalue())
        draft=c.load(self.root/out.getvalue().rstrip().splitlines()[-1].split(': ',1)[1])
        self.assertEqual({x['dialect'] for x in draft['resources'].values()},{'family-b'})
    def read_args(self,*words):
        import argparse
        parser=argparse.ArgumentParser();r.add_read_arguments(parser)
        state=self.root/'runtime'
        return parser.parse_args([*words,'--root',str(self.root),'--state-file',str(state/'state.json'),
                                  '--cache-dir',str(state/'cache'),'--managed-root',str(state/'managed')]),parser
    def test_read_command_takes_a_prompt_family_without_a_model_record(self):
        import contextlib
        catalog,self.guide=self.family_catalog()
        out=io.StringIO()
        with catalog,patch.dict(os.environ),contextlib.redirect_stdout(out):
            os.environ.pop('CPB_READS_LEDGER',None)
            r.read_command(*self.read_args('generation','--dialect','family-a'))
            with self.assertRaisesRegex(ValueError,"unknown dialect 'family-c'; the prompt-dialects resource carries: family-a, family-b"):
                r.read_command(*self.read_args('generation','--dialect','family-c'))
        self.assertIn(self.guide['sections'][1]['rules'][0],out.getvalue())
        self.assertNotIn(self.guide['sections'][2]['rules'][0],out.getvalue())
        draft=c.load(self.root/out.getvalue().rstrip().splitlines()[-1].split(': ',1)[1])
        self.assertEqual({x['dialect'] for x in draft['resources'].values()},{'family-a'})
        row=next(x for x in r.ledger_rows(self.root/'work/reads.jsonl') if x['key_sha256']==c.digest(draft['reading_key'].encode()))
        self.assertEqual(row['resources'],draft['resources'])
    def test_an_unknown_model_names_the_models_and_the_prompt_families(self):
        import prepare_generation_references
        catalog,self.guide=self.family_catalog()
        models=[SimpleNamespace(kind='model',record={'id':name},source_pack='synthetic-pack',source_root=self.root/'pack')
                for name in ('synthetic-model-b','synthetic-model-a')]
        refused=ValueError("unknown model 'family-a'; use a model record from an enabled pack")
        with catalog as loader,patch.object(prepare_generation_references,'resolve_model_record',side_effect=refused):
            loader.return_value.entries=tuple(models)
            with self.assertRaises(ValueError) as caught:
                r.read_command(*self.read_args('generation','--model','family-a'))
        self.assertEqual(str(caught.exception),"unknown model 'family-a'; use a model record from an enabled pack; "
                         'model ids: synthetic-model-a, synthetic-model-b; a prompt-only read can name the prompt family '
                         'instead with --dialect ID: family-a, family-b')
    def test_a_model_needs_the_prompt_dialect_feature(self):
        with self.assertRaisesRegex(ValueError,'add --feature prompt-dialect'):
            r.capture('generation',root=self.root,dialect='family-a')
    def test_ledger_has_only_key_hash(self):
        issued=self.issued()
        self.assertNotIn(issued['reading_key'],self.ledger.read_text(encoding='utf-8'))
        self.assertEqual(c.digest(issued['reading_key'].encode()),r.ledger_rows(self.ledger)[0]['key_sha256'])
    def test_same_version_reusable(self):
        record=self.record()
        self.assertEqual(self.verify(record),self.verify(record))
    def test_document_update(self):
        record=self.record(); (self.root/'notes/work.md').write_text(PARAGRAPH+' changed', encoding='utf-8')
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
    def test_a_reading_that_applies_nothing_verifies(self):
        record=self.record();record['applied']=[]
        self.verify(record)
    def test_wrong_quote(self):
        record=self.record();record['applied'][0]['quote']=PARAGRAPH.replace('operator','reader')
        with self.assertRaisesRegex(ValueError,'paragraph'): self.verify(record)
    def test_short_quote(self):
        record=self.record();record['applied'][0]['quote']='The operator'
        with self.assertRaisesRegex(ValueError,'twelve'): self.verify(record)
    def test_heading_is_not_prose(self):
        (self.root/'notes/work.md').write_text('# '+PARAGRAPH+'\n', encoding='utf-8')
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
        (self.root/'notes/work.md').write_text(PARAGRAPH+' New source.', encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'changed'):
            r.read_page(cursor=result['cursor'],page_bytes=10000,root=self.root,ledger=self.ledger,stream=io.StringIO())
        self.assertFalse(self.ledger.exists())
    def test_invalid_page_budget(self):
        with self.assertRaises(ValueError):r.read_page(route='generation',page_bytes=0,root=self.root,ledger=self.ledger)

if __name__=='__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main(verbosity=2)
