#!/usr/bin/env python3
"""Exercise complete reading evidence with synthetic local documents."""
from __future__ import annotations
import copy
import io
import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
import execution_contract as c
import route_reading as r
from pack_cache import RuntimePackCatalog, RuntimePackEntry, RuntimePackResource


PARAGRAPH = 'The operator preserves the selected source and records the explicit decision before performing the requested operation.'

class ReadingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root/'config').mkdir()
        (self.root/'notes').mkdir()
        self.manifest = {'operation_contexts': {name: {'reads': ['notes/always.md'],
            'executions': {mode: [] for mode in r.execution_routes.EXECUTIONS}}
            for name in r.execution_routes.OPERATIONS}, 'routes': {
            'development': {'default_operation':'author', 'features': [], 'reads': ['notes/work.md'], 'stages': []},
            'generation': {'default_operation':'prepare', 'features': [], 'reads': ['notes/work.md'], 'stages': []}},
            'features': {'extra': {'reads': ['notes/extra.md'], 'source_roles': []}},
            'reading_scopes': {operation: {'documents': {}} for operation in ('adopt', 'withdraw')}}
        (self.root/'config/execution-routes.json').write_bytes(c.encoded(self.manifest))
        # Bytes, not text: the read delivers exact bytes on every platform.
        (self.root/'SKILL.md').write_bytes(('# Skill\n\n'+PARAGRAPH+'\n').encode())
        (self.root/'notes/always.md').write_bytes(('# Always\n\n'+PARAGRAPH+'\n').encode())
        (self.root/'notes/work.md').write_bytes(('# Work\n\n'+PARAGRAPH+'\n').encode())
        (self.root/'notes/extra.md').write_bytes(('# Extra\n\n'+PARAGRAPH+'\n').encode())
        self.ledger = self.root/'work/reads.jsonl'
    def issued(self, route='generation', features=None):
        return r.issue(route, features, root=self.root, ledger=self.ledger,
                       key='1'*32, at='2000-01-01T00:00:00Z', stream=io.StringIO(), execution='dispatcher')
    def record(self, route='generation', features=None):
        return r.build_record(self.issued(route, features), root=self.root, ledgers=[self.ledger])
    def verify(self, record):
        return r.require_route_reading(record,root=self.root,ledgers=[self.ledger],routes={'generation'})
    def expanded_index(self, indexed):
        rows = []
        for source in indexed['index']:
            detail = r.read_page(snapshot_id=indexed['snapshot'], index_source=source['selector'],
                navigation=True, root=self.root, ledger=self.ledger, stream=io.StringIO())
            self.assertEqual((detail['body'], detail['reading']), ([], None))
            rows.extend(detail['index'])
        return {**indexed, 'index': rows}
    def test_full_text_and_key(self):
        stream=io.StringIO()
        issued=r.issue('generation',root=self.root,ledger=self.ledger,stream=stream, execution='dispatcher')
        out=stream.getvalue()
        self.assertEqual(['notes/always.md','notes/work.md'],[x['path'] for x in issued['row']['documents']])
        for name in ('notes/always.md','notes/work.md'):
            self.assertIn((self.root/name).read_bytes().decode('utf-8'), [item['text'] for item in json.loads(out)['body']])
        self.assertEqual(json.loads(out)['reading']['key'], issued['reading_key'])
    def test_route_and_feature_errors_explain_selection_before_delivery(self):
        cases = [
            (r.ROOT, 'generation', ['batch'],
             ["'batch' is a route", "select route 'batch'", 'remove --feature batch']),
            (self.root, 'generation', ['development'],
             ["'development' is a route", "select route 'development'", 'remove --feature development']),
            (self.root, 'extra', [],
             ["'extra' is a feature", 'choose a route from: development, generation', 'include --feature extra']),
            (self.root, 'unlisted-scope', [],
             ['unknown route: unlisted-scope', 'choose a route from: development, generation']),
            (self.root, 'generation', ['unlisted-scope'],
             ['unknown feature: unlisted-scope', 'choose a feature from: extra']),
        ]
        for root, route, features, expected in cases:
            with self.subTest(route=route, features=features):
                acquired = []
                def source(path):
                    acquired.append(path)
                    return (root / path).read_bytes()
                with self.assertRaises(ValueError) as resolved:
                    r.execution_routes.resolve(route, features, execution='dispatcher',
                                               root=root, read_source=source)
                message = str(resolved.exception)
                for fragment in [*expected, r.execution_routes.MANIFEST, 'SKILL.md']:
                    self.assertIn(fragment, message)
                self.assertEqual(acquired, [r.execution_routes.MANIFEST])
                for reader in (r.issue, r.read_page):
                    stream = io.StringIO()
                    with self.assertRaises(ValueError) as rejected:
                        reader(route=route, features=features, execution='dispatcher',
                               root=root, ledger=self.ledger, stream=stream)
                    self.assertEqual(str(rejected.exception), message)
                    self.assertEqual(stream.getvalue(), '')
                    self.assertFalse(self.ledger.exists())
                    self.assertFalse((self.ledger.parent / 'reading-snapshots').exists())
                    self.assertFalse((self.ledger.parent / 'readings').exists())
        corrected = r.read_page(route='development', features=['extra'], execution='dispatcher',
                                root=self.root, ledger=self.ledger, stream=io.StringIO())
        self.assertEqual(corrected['issued']['row']['route'], 'development')
        self.assertEqual(corrected['issued']['row']['features'], ['extra'])
        self.assertEqual([item['metadata']['path'] for item in corrected['body']],
                         ['notes/always.md', 'notes/work.md', 'notes/extra.md'])
    def test_only_a_failed_resource_blocks_a_reading(self):
        self.manifest['features']['prompt-dialect'] = {'reads': [], 'source_roles': []}
        (self.root/'config/execution-routes.json').write_bytes(c.encoded(self.manifest))
        other = {'severity': 'error', 'code': 'record-conflict', 'message': 'another pack'}
        failed = {'severity': 'error', 'code': 'resource-conflict', 'resource': 'prompt-dialects',
                  'pack_ids': ['pack-b'], 'message': 'packs disagree'}
        line = 'warning: pack pack-b is invalid (lock-extra-files: files not in pack.lock.json)'
        def catalog(*diagnostics):
            return RuntimePackCatalog(fingerprint='synthetic-empty', active_pack_count=0,
                                      entries=(), phrases={}, profiles={}, resources={},
                                      assets_by_canonical_record={}, diagnostics=diagnostics,
                                      warnings=(line,))
        with patch('catalog_retrieval.runtime.load_pack_catalog', return_value=catalog(other)):
            manifest, _ = r.capture('generation', ['prompt-dialect'], root=self.root, execution='dispatcher')
        self.assertEqual(manifest['resources'], {'prompt-writing-guide': {'status': 'unavailable'},
                                                 'prompt-dialects': {'status': 'unavailable'}})
        with patch('catalog_retrieval.runtime.load_pack_catalog', return_value=catalog(other, failed)):
            with self.assertRaisesRegex(ValueError, '^warning: pack pack-b is invalid'):
                r.capture('generation', ['prompt-dialect'], root=self.root, execution='dispatcher')
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
        self.assertEqual(manifest['features']['recurring-identity']['reads'],[
            'references/character-identity-contract.md',
            'references/runtime/prompt-vocabulary.md',
        ])
    def test_a_route_reads_its_complete_operation_and_specialists(self):
        manifest = c.load(r.ROOT/r.execution_routes.MANIFEST)
        authored = r.execution_routes.resolve('prompt-only', execution='authored')
        expected = manifest['operation_contexts']['author']['reads'] + manifest['routes']['prompt-only']['reads']
        expected += manifest['operation_contexts']['author']['executions']['authored']
        expected += manifest['features']['render-contract']['reads']
        self.assertEqual({row['path'] for row in authored['reads']}, set(expected))
        self.assertEqual(authored['operation'], 'author')
        prepared = r.execution_routes.resolve('repose', execution='dispatcher')
        self.assertEqual(prepared['operation'], 'prepare')
        self.assertEqual(prepared['features'], ['generation-package','prompt-dialect','reference-delivery','render-contract','studio'])
        package = 'references/runtime/generation-package.md'
        self.assertIn(package, {row['path'] for row in prepared['reads']})
        external = r.execution_routes.resolve('generation', execution='external', operation='execute')
        paths = {row['path'] for row in external['reads']}
        self.assertIn('references/runtime/production-external-execution.md', paths)
        self.assertNotIn('references/runtime/production-dispatch.md', paths)
        self.assertNotIn(package, paths)
        packaged = r.execution_routes.resolve('generation', ['generation-package'], execution='external')
        self.assertIn(package, {row['path'] for row in packaged['reads']})
        self.assertNotIn('references/runtime/production-dispatch.md', {row['path'] for row in packaged['reads']})
        ordinary = r.execution_routes.resolve('generation', execution='external', operation='prepare')
        paths = {row['path'] for row in ordinary['reads']}
        self.assertIn('references/runtime/production-diagnostic-navigation.md', paths)
        self.assertNotIn('references/runtime/production-diagnostics.md', paths)
        self.assertNotIn('references/runtime/studio-placement.md', paths)
        placement = r.execution_routes.resolve('generation', ['studio-placement'], execution='external', operation='adopt',
                                              scope='studio-slot', source_kind='production-candidate')
        self.assertIn('references/runtime/studio-placement.md', {row['path'] for row in placement['reads']})
        self.assertEqual(placement['read_owners']['references/runtime/studio-placement.md'], ['feature:studio-placement'])
    def test_package_reading_requires_its_complete_artifact_contract(self):
        plain = r.issue('generation', execution='external', ledger=self.ledger, stream=io.StringIO())
        record = r.build_record(plain, ledgers=[self.ledger])
        with self.assertRaisesRegex(ValueError, 'features do not cover'):
            r.require_route_reading(record, execution='external', operation='prepare',
                features=['generation-package'], ledgers=[self.ledger])
        selected = r.issue('generation', ['generation-package'], execution='external',
                           ledger=self.ledger, stream=io.StringIO())
        record = r.build_record(selected, ledgers=[self.ledger])
        r.require_route_reading(record, execution='external', operation='prepare',
            features=['generation-package'], ledgers=[self.ledger])
        with self.assertRaisesRegex(ValueError, 'documents do not cover'):
            r.require_route_reading(record, execution='dispatcher', operation='execute',
                features=['generation-package'], ledgers=[self.ledger])
    def test_delivery_record_is_complete_at_issuance(self):
        issued = self.issued()
        record = r.draft_record(issued)
        self.assertEqual(set(record), r.MANIFEST_FIELDS | {'reading_key'})
        self.assertEqual(record['documents'], issued['row']['documents'])
        self.assertEqual(record['operation'], 'prepare')
        self.verify(record)
    def test_delivered_feature_superset_covers_current_selected_features(self):
        record = self.record(features=['extra'])
        r.require_route_reading(record, root=self.root, ledgers=[self.ledger], features=[])
        narrow = r.issue('generation', root=self.root, ledger=self.ledger, stream=io.StringIO(), execution='dispatcher')
        with self.assertRaisesRegex(ValueError, 'features do not cover'):
            r.require_route_reading(r.draft_record(narrow), root=self.root, ledgers=[self.ledger], features=['extra'])
    def test_delivery_record_is_published_from_its_issuance(self):
        issued = self.issued()
        path = r.write_draft(issued, self.ledger)
        original = path.read_bytes()
        self.assertEqual(r.write_draft(issued, self.ledger), path)
        self.assertEqual(path.read_bytes(), original)
        changed = c.load(path); changed['documents'][0]['sha256'] = '0' * 64
        path.write_bytes(c.encoded(changed))
        with self.assertRaisesRegex(ValueError, 'differs from its issuance'):
            r.write_draft(issued, self.ledger)
    def test_cli_default_index_and_selected_pages_cover_complete_bodies_before_issuance(self):
        env={k:v for k,v in os.environ.items() if k!='CPB_READS_LEDGER'}
        state=self.root/'runtime'
        argv=[sys.executable,str(r.ROOT/'scripts/execution_routes.py'),'read','development',
              '--execution','authored',
              '--root',str(self.root),'--state-file',str(state/'state.json'),
              '--cache-dir',str(state/'cache'),'--managed-root',str(state/'managed')]
        ledger=self.root/'work/reads.jsonl'
        indexed=json.loads(self.cli_read(argv,cwd=self.root,environment=env))
        self.assertEqual(indexed['mode'],'index')
        self.assertEqual(indexed['body'],[])
        self.assertIsNone(indexed['reading'])
        self.assertIsNone(indexed['context_reuse'])
        self.assertEqual(indexed['progress']['delivered_bytes'],0)
        self.assertFalse(indexed['same_context_required'])
        self.assertFalse(ledger.exists())
        argv=indexed['actions']['next']['argv']
        delivered={}
        for page_number in range(64):
            output=self.cli_read(argv,cwd=self.root,environment=env)
            result=json.loads(output)
            page_bytes=0
            for segment in result['body']:
                header=segment['metadata']
                body=segment['text'].encode('utf-8')
                key=(header['kind'],header['path'])
                self.assertEqual(len(body),header['end']-header['start'])
                self.assertEqual(len(delivered.get(key,b'')),header['start'])
                delivered[key]=delivered.get(key,b'')+body
                page_bytes+=len(body)
            self.assertLessEqual(page_bytes,r.DEFAULT_PAGE_BYTES)
            self.assertGreater(page_bytes,0)
            actions=result['actions']
            if result['reading'] is not None:
                break
            self.assertIsNone(result['reading'])
            self.assertIsNone(result['context_reuse'])
            self.assertFalse(ledger.exists())
            self.assertFalse((self.root/'work/readings').exists())
            argv=(actions['continue'] or actions['all'])['argv']
            self.assertEqual(argv[argv.index('--page-bytes')+1],str(r.DEFAULT_PAGE_BYTES))
        else:
            self.fail('Default continuation did not finish the route reading')
        self.assertGreater(page_number,0)
        self.assertTrue(result['reading']['record'].startswith('work/readings/development-'))
        draft=c.load(self.root/result['reading']['record'])
        self.assertEqual((draft['route'],draft['operation']),('development','author'))
        for document in draft['documents']:
            body=(r.ROOT/document['path']).read_bytes()
            self.assertEqual(delivered[('document',document['path'])],body)
            self.assertEqual(document['sha256'],c.digest(body))
        r.require_route_reading(draft,root=r.ROOT,ledgers=[ledger])

    def test_each_operation_delivers_its_complete_contract(self):
        required = {
            ('author', 'authored'): {'references/runtime/authoring-work.md', 'references/runtime/production-authoring.md', 'references/runtime/production-authored-storage.md',
                       'references/runtime/production-direction.md'},
            ('save', 'authored'): {'references/runtime/authoring-work.md', 'references/runtime/production-authored-storage.md'},
            ('prepare', 'dispatcher'): {'references/runtime/authoring-work.md', 'references/runtime/production-preparation.md', 'references/runtime/production-diagnostic-navigation.md'},
            ('prepare', 'external'): {'references/runtime/authoring-work.md', 'references/runtime/production-image-inputs.md', 'references/runtime/production-external-inputs.md'},
            ('execute', 'dispatcher'): {'references/runtime/production-dispatch.md', 'references/runtime/production-permissions.md',
                                       'references/runtime/production-request-execution.md', 'references/runtime/production-recovery.md'},
            ('execute', 'external'): {'references/runtime/production-external-execution.md', 'references/runtime/production-permissions.md',
                                     'references/runtime/production-request-execution.md', 'references/runtime/production-recovery.md'},
            ('review', 'external'): {'references/runtime/authoring-work.md', 'references/runtime/production-review.md'},
            ('review', 'authored'): {'references/runtime/authoring-work.md', 'references/runtime/production-authored-storage.md'},
        }
        for (operation, execution), names in required.items():
            with self.subTest(operation=operation, execution=execution):
                manifest, bodies = r.capture('development', operation=operation, execution=execution)
                received = {}
                for meta, body in bodies:
                    if meta['kind'] == 'document':
                        received.setdefault(meta['path'], []).append((meta, body))
                self.assertEqual(manifest['execution'], execution)
                for name in names:
                    self.assertEqual(b''.join(body for _, body in received[name]), (r.ROOT/name).read_bytes())
                for document in manifest['documents']:
                    source = (r.ROOT/document['path']).read_bytes()
                    expected = b''.join(source[part['start']:part['end']] for part in document['ranges'])
                    self.assertEqual(b''.join(body for _, body in received[document['path']]), expected)
                    for meta, body in received[document['path']]:
                        self.assertEqual(body, source[meta['source_start']:meta['source_end']])
                        self.assertEqual(meta['source_sha256'], c.digest(source))
                if execution != 'dispatcher':
                    self.assertNotIn('references/runtime/production-dispatch.md', received)
        _, bodies = r.capture('prompt-only', operation='author', execution='authored')
        received = {meta['path'] for meta, _ in bodies}
        self.assertNotIn('references/runtime/production-dispatch.md', received)
        self.assertNotIn('references/runtime/production-adoption.md', received)
        self.assertNotIn('references/runtime/production-external-inputs.md', received)

    def cli_read(self, argv, *, cwd, environment):
        run = subprocess.run(argv, cwd=cwd, env=environment, capture_output=True,
                             text=True, encoding='utf-8', check=False)
        self.assertEqual(run.returncode, 0, run.stdout[-2000:] + run.stderr)
        return run.stdout

    def cli_reading_actions(self, output, *, studio, ledger, runtime, roots, page_bytes):
        actions = json.loads(output)['actions']
        self.assertIn('replay', actions)
        self.assertEqual(set(actions), {'continue', 'next', 'replay', 'restart', 'index', 'all'})
        self.assertIn('restart', actions)
        for name, action in actions.items():
            if action is None:
                self.assertIn(name, {'continue', 'next', 'replay'})
                continue
            self.assertEqual(set(action), {'argv', 'command', 'reason'})
            argv = action['argv']
            self.assertEqual(argv[:3], [os.path.abspath(sys.executable),
                                       str(r.ROOT / 'scripts/execution_routes.py'), 'read'])
            self.assertTrue(action['reason'].strip())
            self.assertTrue(action['command'].strip())
            if os.name != 'nt':
                self.assertEqual(shlex.split(action['command']), argv)
            expected = {'--root': str(studio), '--reading-ledger': str(ledger),
                        '--page-bytes': str(page_bytes), **runtime}
            for option, value in expected.items():
                self.assertEqual(argv.count(option), 1, argv)
                self.assertEqual(argv[argv.index(option) + 1], value, argv)
            self.assertEqual([argv[i + 1] for i, word in enumerate(argv) if word == '--pack-root'],
                             [str(path) for path in roots])
            option = '--snapshot' if name in {'next', 'index', 'all'} else '--' + name
            self.assertEqual(argv.count(option), 1, argv)
            if name == 'next':
                self.assertIn('--section', argv)
            elif name == 'all':
                self.assertIn('--all', argv)
            for fixed in ('development', '--feature', '--model', '--dialect'):
                self.assertNotIn(fixed, argv[3:])
        return actions

    def cli_reading_record(self, output, *, studio, ledger):
        result = json.loads(output)
        self.assertIsNone(result['actions']['continue'])
        path = Path(result['reading']['record'])
        if not path.is_absolute():
            path = studio / path
        record = c.load(path)
        r.require_route_reading(record, root=r.ROOT, ledgers=[ledger], routes={'development'})
        self.assertEqual(record['operation'], 'author')
        return path, record

    def exercise_cli_paged_actions(self, *, explicit):
        import studio_workspace as studio_runtime

        studio = self.root / "Studio with spaces and an apostrophe's"
        studio_runtime.init(studio, 'paged-reading', 'Paged reading fixture')
        first_cwd = studio / 'work/first caller' if not explicit else self.root / 'first caller'
        second_cwd = self.root / 'different caller'
        first_cwd.mkdir(parents=True)
        second_cwd.mkdir()
        home = self.root / 'initial default home'
        environment = {k: v for k, v in os.environ.items() if k != 'CPB_READS_LEDGER'}
        environment.update(CPB_HOME=str(home), PATH='', PYTHONDONTWRITEBYTECODE='1')
        page_bytes = 8192
        base = [sys.executable, str(r.ROOT / 'scripts/execution_routes.py'), 'read']
        start = [*base, 'development', '--execution', 'authored', '--all', '--page-bytes', str(page_bytes)]
        roots = []
        if explicit:
            selected = self.root / 'selected runtime with spaces'
            runtime = {'--state-file': str(selected / 'state.json'),
                       '--cache-dir': str(selected / 'cache'),
                       '--managed-root': str(selected / 'managed')}
            roots = [self.root / "first root's $literal", self.root / 'second root & extra']
            for path in roots:
                path.mkdir()
            start.extend(['--root', str(studio), '--feature', 'studio'])
            start.extend(word for option, value in runtime.items() for word in (option, value))
            start.extend(word for path in roots for word in ('--pack-root', str(path)))
            relative_ledger = Path('relative ledger') / 'reading evidence.jsonl'
            environment['CPB_READS_LEDGER'] = str(relative_ledger)
            ledger = first_cwd / relative_ledger
        else:
            runtime = {'--state-file': str(home / 'pack-state.json'),
                       '--cache-dir': str(home / 'cache'),
                       '--managed-root': str(home / 'packs')}
            ledger = studio / 'work/reads.jsonl'
        runtime = {option: str(Path(value).resolve()) for option, value in runtime.items()}
        roots = [path.resolve() for path in roots]
        expected = dict(studio=studio, ledger=ledger, runtime=runtime,
                        roots=roots, page_bytes=page_bytes)
        output = self.cli_read(start, cwd=first_cwd, environment=environment)
        actions = self.cli_reading_actions(output, **expected)
        self.assertIn('continue', actions)
        self.assertFalse(ledger.exists())
        cursor = json.loads(output)['cursor']
        snapshot_path = ledger.parent / 'reading-snapshots' / cursor.split(':')[0] / 'snapshot.json'
        snapshot_bytes = snapshot_path.read_bytes()
        snapshot = json.loads(snapshot_bytes)
        self.assertEqual(set(snapshot), {'manifest', 'root', 'runtime', 'task_id', 'model_file', 'nonce', 'bodies',
                                         'required_bodies', 'reused_bodies', 'known_readings', 'context_keys', 'read_owners', 'section_owners'})
        self.assertIsNone(snapshot['task_id'])
        self.assertEqual(snapshot['runtime'], {
            'state_file': runtime['--state-file'], 'cache_dir': runtime['--cache-dir'],
            'managed_root': runtime['--managed-root'], 'extra_roots': [str(path) for path in roots]})

        # Each offered argv runs unchanged in another cwd with different ambient
        # settings and no Python alias on PATH. The saved context owns this read.
        other_home = self.root / 'different ambient home'
        other_ledger = second_cwd / 'unrelated reads.jsonl'
        continued_environment = {**environment, 'CPB_HOME': str(other_home),
                                 'CPB_READS_LEDGER': str(other_ledger)}
        replay = self.cli_read(actions['replay']['argv'], cwd=second_cwd,
                               environment=continued_environment)
        headers = lambda text: [segment['metadata'] for segment in json.loads(text)['body']]
        self.assertEqual(headers(replay), headers(output))
        self.cli_reading_actions(replay, **expected)
        output = self.cli_read(actions['continue']['argv'], cwd=second_cwd,
                               environment=continued_environment)
        actions = self.cli_reading_actions(output, **expected)
        if explicit:
            # A manually supplied cursor may omit runtime selectors. The next
            # offered commands must still name the runtime stored in the snapshot.
            self.assertIn('continue', actions)
            cursor = json.loads(output)['cursor']
            output = self.cli_read([*base, '--continue', cursor, '--root', str(studio),
                                    '--reading-ledger', str(ledger), '--page-bytes', str(page_bytes)],
                                   cwd=second_cwd, environment=continued_environment)
            actions = self.cli_reading_actions(output, **expected)
        for _ in range(64):
            if actions['continue'] is None:
                break
            output = self.cli_read(actions['continue']['argv'], cwd=second_cwd,
                                   environment=continued_environment)
            actions = self.cli_reading_actions(output, **expected)
        else:
            self.fail('Returned continuation commands did not finish the route reading')
        self.assertEqual(set(actions), {'continue', 'next', 'replay', 'restart', 'index', 'all'})
        self.assertIsNone(actions['continue'])
        path, record = self.cli_reading_record(output, studio=studio, ledger=ledger)
        self.assertEqual(record['features'], ['studio'] if explicit else [])
        first_record_bytes = path.read_bytes()
        replay = self.cli_read(actions['replay']['argv'], cwd=second_cwd,
                               environment=continued_environment)
        self.assertIsNone(self.cli_reading_actions(replay, **expected)['continue'])
        _, replay_record = self.cli_reading_record(replay, studio=studio, ledger=ledger)
        self.assertNotEqual(record['reading_key'], replay_record['reading_key'])
        self.assertEqual(path.read_bytes(), first_record_bytes)
        r.require_route_reading(record, root=r.ROOT, ledgers=[ledger])
        self.assertEqual(len(r.ledger_rows(ledger)), 2)
        reuse = json.loads(output)['context_reuse']
        reused = self.cli_read(reuse['operations']['author']['argv'], cwd=second_cwd,
                               environment=continued_environment)
        self.assertIsNone(json.loads(reused)['reading'])
        self.assertEqual(json.loads(reused)['mode'], 'index')
        reused = self.cli_read(json.loads(reused)['actions']['all']['argv'], cwd=second_cwd,
                               environment=continued_environment)
        reused_path, reused_record = self.cli_reading_record(reused, studio=studio, ledger=ledger)
        self.assertEqual(reused_record['documents'], record['documents'])
        self.assertNotEqual(reused_record['reading_key'], record['reading_key'])
        self.assertNotEqual(reused_path, path)
        self.assertEqual(json.loads(reused)['body'], [])
        self.assertEqual(json.loads(reused)['progress']['total_bytes'], 0)
        before = ledger.read_bytes()
        restart_action = json.loads(reused)['actions']['restart']
        self.assertNotIn('--known-reading', restart_action['argv'])
        restart = self.cli_read(restart_action['argv'], cwd=second_cwd,
                                environment=continued_environment)
        self.assertEqual(json.loads(restart)['mode'], 'index')
        self.assertEqual(json.loads(restart)['body'], [])
        self.assertIsNone(json.loads(restart)['reading'])
        self.cli_reading_actions(restart, **expected)
        restart = self.cli_read(json.loads(restart)['actions']['all']['argv'], cwd=second_cwd,
                                environment=continued_environment)
        restarted_headers = headers(restart)
        self.assertEqual(restarted_headers[0]['start'], 0)
        self.assertEqual(json.loads(restart)['progress']['reused_bytes'], 0)
        self.assertNotEqual(restarted_headers[0]['snapshot'], cursor.split(':')[0])
        self.cli_reading_actions(restart, **expected)
        self.assertEqual(ledger.read_bytes(), before)
        self.assertEqual(snapshot_path.read_bytes(), snapshot_bytes)
        self.assertFalse(other_ledger.exists())
        self.assertFalse((other_home / 'pack-state.json').exists())

    def test_cli_paged_actions_keep_explicit_runtime_roots_and_custom_ledger(self):
        self.exercise_cli_paged_actions(explicit=True)

    def test_cli_paged_actions_keep_default_runtime_and_discovered_studio(self):
        self.exercise_cli_paged_actions(explicit=False)

    def test_cursor_cli_rejects_start_selectors_before_model_lookup(self):
        import contextlib
        cases = [('development', '--continue', 'synthetic-cursor'),
                 ('--continue', 'synthetic-cursor', '--feature', 'extra'),
                 ('--continue', 'synthetic-cursor', '--model', 'synthetic-missing-model'),
                 ('--replay', 'synthetic-cursor', '--dialect', 'synthetic-family')]
        for words in cases:
            with self.subTest(words=words):
                args, parser = self.read_args(*words)
                with patch.object(r, '_selected_model') as lookup, contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises((ValueError, SystemExit)):
                        r.read_command(args, parser)
                lookup.assert_not_called()
        self.assertFalse((self.root / 'work/reading-snapshots').exists())

    def test_explicit_ledger_is_a_current_reading_location(self):
        import contextlib
        ledger = self.root / 'selected ledger/reads.jsonl'
        args, parser = self.read_args('development', '--all', '--reading-ledger', str(ledger), '--page-bytes', '1000000')
        with contextlib.redirect_stdout(io.StringIO()):
            result = r.read_command(args, parser)
        self.assertTrue(ledger.is_file())
        self.assertEqual(result['issued']['row']['route'], 'development')
        self.assertIn(str(ledger), result['context_reuse']['operations']['save']['argv'])

    def family_catalog(self):
        pack=self.root/'pack';(pack/'resources').mkdir(parents=True)
        rule='Synthetic rule for {} gives the rendition one clear priority and records it in the delivered prompt.'
        guide={'format':'synthetic','name':'Synthetic guide','description':'Synthetic fixture.','sections':[
            {'id':'every','title':'Every family','rules':[rule.format('every family')]},
            {'id':'first','title':'First family','dialects':['family-a'],'rules':[rule.format('the first family')]},
            {'id':'second','title':'Second family','dialects':['family-b'],'rules':[rule.format('the second family')]}]}
        family=lambda name:{'id':name,'name':name,'description':'Synthetic family.','tag_separator':', ',
                            'vocabularies':['synthetic'],
                            'block_order':['subject','scene']}
        dialects={'format':'character-prompt-builder-prompt-dialects','name':'Synthetic dialects',
                  'description':'Synthetic fixture.','dialects':[family('family-a'),family('family-b')]}
        (pack/'resources/guide.json').write_text(json.dumps(guide), encoding='utf-8')
        (pack/'resources/dialects.json').write_text(json.dumps(dialects), encoding='utf-8')
        self.manifest['features']['prompt-dialect']={'reads':[],'source_roles':[]}
        (self.root/'config/execution-routes.json').write_bytes(c.encoded(self.manifest))
        named=lambda name,relative:RuntimePackResource(name=name,path=pack/relative,media_type='application/json',
                                                       source_pack='synthetic-pack',relative_path=relative)
        catalog=RuntimePackCatalog(fingerprint='synthetic-family',active_pack_count=1,
                                   entries=(),phrases={},profiles={},assets_by_canonical_record={},diagnostics=(),
                                   resources={'prompt-writing-guide':named('prompt-writing-guide','resources/guide.json'),
                                              'prompt-dialects':named('prompt-dialects','resources/dialects.json')},
                                   pack_roots={'synthetic-pack':pack})
        return patch('catalog_retrieval.runtime.load_pack_catalog',return_value=catalog),guide
    def family_record(self, dialect, section):
        stream = io.StringIO()
        issued = r.issue('generation', ['prompt-dialect'], root=self.root, ledger=self.ledger,
                         stream=stream, dialect=dialect, execution='dispatcher')
        return r.draft_record(issued), stream.getvalue()
    def test_model_family_reading_preserves_the_complete_selected_scope(self):
        catalog, self.guide = self.family_catalog()
        with catalog:
            record, out = self.family_record('family-a', 1)
            self.assertIn(self.guide['sections'][0]['rules'][0], out)
            self.assertIn(self.guide['sections'][1]['rules'][0], out)
            self.assertNotIn(self.guide['sections'][2]['rules'][0], out)
            self.assertEqual({row['dialect'] for row in record['resources'].values()}, {'family-a'})
            r.require_route_reading(record, root=self.root, ledgers=[self.ledger], dialect='family-a')
            with self.assertRaisesRegex(ValueError, 'read the current model'):
                r.require_route_reading(record, root=self.root, ledgers=[self.ledger], dialect='family-b')
            universal, out = self.family_record(None, 0)
            self.assertNotIn(self.guide['sections'][1]['rules'][0], out)
            r.require_route_reading(universal, root=self.root, ledgers=[self.ledger], dialect=None)
            with self.assertRaisesRegex(ValueError, 'read the current model'):
                r.require_route_reading(universal, root=self.root, ledgers=[self.ledger], dialect='family-a')
    def read_command_to_completion(self,args,parser,*,bodies=None):
        result=r.read_command(args,parser)
        if bodies is not None:bodies.extend(result['body'])
        while result['reading'] is None:
            args=parser.parse_args((result['actions']['continue'] or result['actions']['all'])['argv'][3:])
            result=r.read_command(args,parser)
            if bodies is not None:bodies.extend(result['body'])
        return result
    def test_read_command_without_a_target_selects_neutral_guidance(self):
        import contextlib
        catalog,self.guide=self.family_catalog()
        out=io.StringIO();bodies=[]
        with catalog,patch.dict(os.environ),contextlib.redirect_stdout(out):
            os.environ.pop('CPB_READS_LEDGER',None)
            result=self.read_command_to_completion(*self.read_args('generation'),bodies=bodies)
        draft=c.load(self.root/result['reading']['record'])
        self.assertEqual({x['dialect'] for x in draft['resources'].values()},{None})
        delivered=''.join(segment['text'] for segment in bodies)
        self.assertIn(self.guide['sections'][0]['rules'][0],delivered)
        for section in self.guide['sections'][1:]:
            self.assertNotIn(section['rules'][0],delivered)
    def test_paged_family_reading_issues_its_family(self):
        catalog,self.guide=self.family_catalog()
        with catalog:
            stream=io.StringIO()
            result=r.read_page(route='generation',features=['prompt-dialect'],page_bytes=300,dialect='family-a',
                               root=self.root,ledger=self.ledger,stream=stream, execution='dispatcher')
            while 'issued' not in result:
                result=r.read_page(cursor=result['cursor'],page_bytes=300,root=self.root,ledger=self.ledger,stream=stream)
        self.assertNotIn(self.guide['sections'][2]['rules'][0],stream.getvalue())
        self.assertEqual({x['dialect'] for x in result['issued']['row']['resources'].values()},{'family-a'})
    def test_read_command_takes_the_family_from_the_model_record(self):
        import argparse
        import contextlib
        import generation_references as prepare_generation_references
        catalog,self.guide=self.family_catalog()
        parser=argparse.ArgumentParser();r.add_read_arguments(parser)
        state=self.root/'runtime'
        args=parser.parse_args(['generation','--execution','dispatcher','--root',str(self.root),'--model','synthetic-model',
                                '--state-file',str(state/'state.json'),'--cache-dir',str(state/'cache'),
                                '--managed-root',str(state/'managed')])
        out=io.StringIO()
        from model_prompt_input_fixtures import prompt_input
        record=('synthetic-model',{'id':'synthetic-model','prompt_dialect':'family-b',
                'prompt_input':prompt_input('tag-based',vocabularies=('synthetic',))})
        with (catalog,patch.object(prepare_generation_references,'resolve_model_record',return_value=record),
              patch.dict(os.environ),contextlib.redirect_stdout(out)):
            os.environ.pop('CPB_READS_LEDGER',None)
            result=self.read_command_to_completion(args,parser)
        self.assertNotIn(self.guide['sections'][1]['rules'][0],out.getvalue())
        draft=c.load(self.root/result['reading']['record'])
        self.assertEqual({x['dialect'] for x in draft['resources'].values()},{'family-b'})
        self.assertEqual(draft['model']['id'], 'synthetic-model')
        self.assertEqual(draft['model']['record_sha256'], c.content_id(record[1]))

    def test_selected_model_and_service_guidance_cannot_change_under_a_receipt(self):
        from model_prompt_input_fixtures import prompt_input
        model = {'id': 'synthetic-renderer',
                 'prompt_input': prompt_input('descriptive'),
                 'offerings': [{'service': 'interface-a', 'model_identifier': 'render-a'},
                               {'service': 'interface-b', 'model_identifier': 'render-b'}]}
        with patch.object(r, '_selected_model', return_value=(model['id'], model)):
            output = io.StringIO()
            issued = r.issue('generation', root=self.root, ledger=self.ledger,
                             model=model['id'], service='interface-a', stream=output, execution='dispatcher')
        record = r.draft_record(issued)
        self.assertIn('render-a', output.getvalue())
        self.assertNotIn('render-b', output.getvalue())
        r.require_model_reading(record, model_record=model, service='interface-a', resource_reader=lambda name: None)
        with self.assertRaisesRegex(ValueError, 'different service'):
            r.require_model_reading(record, model_record=model, service='interface-b', resource_reader=lambda name: None)
        changed = copy.deepcopy(model); changed['recommended_positive_prompt'] = 'A changed recommendation.'
        with self.assertRaisesRegex(ValueError, 'model edition'):
            r.require_model_reading(record, model_record=changed, service='interface-a', resource_reader=lambda name: None)

    def test_complete_model_guidance_covers_a_selected_offering(self):
        from model_prompt_input_fixtures import prompt_input
        model = {'id': 'synthetic-options',
                 'prompt_input': prompt_input('descriptive'),
                 'offerings': [{'service': 'interface-a', 'model_identifier': 'render-a'},
                               {'service': 'interface-b', 'model_identifier': 'render-b'}]}
        with patch.object(r, '_selected_model', return_value=(model['id'], model)):
            issued = r.issue('generation', root=self.root, ledger=self.ledger,
                             model=model['id'], stream=io.StringIO(), execution='dispatcher')
        record = r.draft_record(issued)
        r.require_model_reading(record, model_record=model, service='interface-b', resource_reader=lambda name: None)
        self.assertIsNone(record['model']['service'])

    def test_acquired_model_file_retains_its_complete_scope_across_pages(self):
        from model_prompt_input_fixtures import prompt_input
        model = {'id': 'synthetic-acquired', 'prompt_input': prompt_input('descriptive'),
                 'recommended_positive_prompt': 'A complete acquired instruction.'}
        source = self.root / 'acquired-model.json'
        source.write_bytes(c.encoded(model))
        stream = io.StringIO()
        result = r.read_page(route='generation', root=self.root, ledger=self.ledger,
                             model_file=source, page_bytes=200, stream=stream, execution='dispatcher')
        while 'issued' not in result:
            result = r.read_page(cursor=result['cursor'], root=self.root, ledger=self.ledger,
                                 page_bytes=200, stream=stream)
        record = r.draft_record(result['issued'])
        r.require_model_reading(record, model_record=model, resource_reader=lambda name: None)
        pages = [json.loads(line) for line in stream.getvalue().splitlines()]
        segments = [item for page in pages for item in page['body']
                    if item['metadata']['kind'] == 'model']
        delivered = b''
        for item in segments:
            metadata = item['metadata']
            self.assertEqual(metadata['start'], len(delivered))
            delivered += item['text'].encode('utf-8')
            self.assertEqual(metadata['end'], len(delivered))
        _, bodies = r.capture('generation', execution='dispatcher', model_file=source, root=self.root)
        expected = next(raw for metadata, raw in bodies if metadata['kind'] == 'model')
        self.assertEqual(delivered, expected)
        self.assertIn(model['recommended_positive_prompt'], delivered.decode('utf-8'))
        self.assertEqual(record['model']['record_sha256'], c.content_id(model))

    def test_direct_issue_retains_acquired_model_file_and_record(self):
        from model_prompt_input_fixtures import prompt_input
        model = {'id': 'synthetic-direct-model', 'prompt_input': prompt_input('descriptive'),
                 'recommended_positive_prompt': 'Retain this complete acquired model recommendation.',
                 'offerings': [{'service': 'selected-host', 'model_identifier': 'selected-renderer'},
                               {'service': 'other-host', 'model_identifier': 'other-renderer'}]}
        source = self.root / 'direct-model.json'
        source.write_bytes(c.encoded(model))
        for selected in ({'model_file': source}, {'model_record': model}):
            with self.subTest(source=next(iter(selected))):
                output = io.StringIO()
                issued = r.issue('generation', root=self.root, ledger=self.ledger,
                                 execution='external', service='selected-host', stream=output, **selected)
                record = r.draft_record(issued)
                self.assertEqual(record['execution'], 'external')
                self.assertEqual(record['model']['record_sha256'], c.content_id(model))
                self.assertEqual(record['model']['service'], 'selected-host')
                self.assertIn(model['recommended_positive_prompt'], output.getvalue())
                self.assertIn('selected-renderer', output.getvalue())
                self.assertNotIn('other-renderer', output.getvalue())
                r.require_model_reading(record, model_record=model, service='selected-host',
                                        resource_reader=lambda name: None)

    def test_direct_issue_rechecks_the_actual_acquired_model_source(self):
        from model_prompt_input_fixtures import prompt_input
        model = {'id': 'synthetic-changing-model', 'prompt_input': prompt_input('descriptive')}
        source = self.root / 'changing-model.json'
        source.write_bytes(c.encoded(model))
        class SourceChange(io.StringIO):
            def flush(sink):
                changed = {**model, 'recommended_positive_prompt': 'A different source edition.'}
                source.write_bytes(c.encoded(changed))
                super().flush()
        with self.assertRaisesRegex(ValueError, 'reading sources changed'):
            r.issue('generation', execution='external', root=self.root, ledger=self.ledger,
                    model_file=source, stream=SourceChange())
        self.assertFalse(self.ledger.exists())

    def test_studio_status_shares_partial_reading_and_fresh_context_actions(self):
        import studio_workspace as studio
        import work_ledger
        import production_authoring_state
        studio_root = self.root / 'studio'
        studio.init(studio_root, 'reading-continuation', 'Reading continuation')
        work_ledger.begin(studio_root, 'Save an authored description.', ['Compose'])
        result = r.read_page(route='development', studio=studio_root, root=self.root, ledger=self.ledger,
                             page_bytes=100, stream=io.StringIO(), execution='authored')
        rendered = studio.status(studio_root)
        self.assertIn('Resume route reading in the same context:', rendered)
        self.assertIn('--continue', rendered)
        while 'issued' not in result:
            result = r.read_page(cursor=result['cursor'], studio=studio_root, root=self.root, ledger=self.ledger,
                                 page_bytes=1000000, stream=io.StringIO())
        r.write_draft(result['issued'], self.ledger, studio=studio_root, snapshot=result['snapshot'])
        report = production_authoring_state.inspect(studio_root)
        selected = next(row for row in report['readings'] if row['current'])
        self.assertEqual(selected['state'], 'recorded')
        self.assertEqual(selected['next_actions'], [])
        self.assertIn('--operation', selected['fresh_context_action']['argv'])
        self.assertIn('Read the complete contract for a new context:', studio.status(studio_root))
    def read_args(self,*words):
        import argparse
        parser=argparse.ArgumentParser();r.add_read_arguments(parser)
        state=self.root/'runtime'
        scope = [] if any(option in words for option in ('--continue', '--replay', '--restart', '--snapshot')) else ['--execution', 'authored' if 'development' in words else 'dispatcher']
        return parser.parse_args([*words,*scope,'--root',str(self.root),'--state-file',str(state/'state.json'),
                                  '--cache-dir',str(state/'cache'),'--managed-root',str(state/'managed')]),parser
    def test_read_command_takes_a_prompt_family_without_a_model_record(self):
        import contextlib
        catalog,self.guide=self.family_catalog()
        out=io.StringIO()
        with catalog,patch.dict(os.environ),contextlib.redirect_stdout(out):
            os.environ.pop('CPB_READS_LEDGER',None)
            result=self.read_command_to_completion(*self.read_args('generation','--dialect','family-a'))
            with self.assertRaisesRegex(ValueError,"unknown dialect 'family-c'; the prompt-dialects resource carries: family-a, family-b"):
                self.read_command_to_completion(*self.read_args('generation','--dialect','family-c'))
        self.assertIn(self.guide['sections'][1]['rules'][0],out.getvalue())
        self.assertNotIn(self.guide['sections'][2]['rules'][0],out.getvalue())
        draft=c.load(self.root/result['reading']['record'])
        self.assertEqual({x['dialect'] for x in draft['resources'].values()},{'family-a'})
        row=next(x for x in r.ledger_rows(self.root/'work/reads.jsonl') if x['key_sha256']==c.digest(draft['reading_key'].encode()))
        self.assertEqual(row['resources'],draft['resources'])
    def test_an_unknown_model_names_the_models_and_the_prompt_families(self):
        import generation_references as prepare_generation_references
        catalog,self.guide=self.family_catalog()
        models=[RuntimePackEntry(kind='model',category=None,record={'id':name},source_pack='synthetic-pack',
                                 source_root=self.root/'pack',source_file='models/synthetic.json')
                for name in ('synthetic-model-b','synthetic-model-a')]
        refused=ValueError("unknown model 'family-a'; use a model record from an enabled pack")
        with catalog as loader,patch.object(prepare_generation_references,'resolve_model_record',side_effect=refused):
            loader.return_value=replace(loader.return_value,entries=tuple(models))
            with self.assertRaises(ValueError) as caught:
                r.read_command(*self.read_args('generation','--model','family-a'))
        self.assertEqual(str(caught.exception),"unknown model 'family-a'; use a model record from an enabled pack; "
                         'model ids: synthetic-model-a, synthetic-model-b; a prompt-only read can name the prompt family '
                         'instead with --dialect ID: family-a, family-b')
    def test_a_model_needs_the_prompt_dialect_feature(self):
        with self.assertRaisesRegex(ValueError,'add --feature prompt-dialect'):
            r.capture('generation',root=self.root,dialect='family-a', execution='dispatcher')
    def test_ledger_has_only_key_hash(self):
        issued=self.issued()
        self.assertNotIn(issued['reading_key'],self.ledger.read_text(encoding='utf-8'))
        self.assertEqual(c.digest(issued['reading_key'].encode()),r.ledger_rows(self.ledger)[0]['key_sha256'])
    def test_same_version_reusable(self):
        record=self.record()
        self.assertEqual(self.verify(record),self.verify(record))

    def test_current_scope_preserves_an_unneeded_changed_specialist(self):
        record = self.record(features=['extra'])
        (self.root / 'notes/extra.md').write_bytes(b'# Changed specialist\nA different specialist source.\n')
        r.require_route_reading(record, root=self.root, ledgers=[self.ledger], features=[])
        issued = r.resolve_issuance(record['reading_key'], ledgers=[self.ledger])
        self.assertEqual(r.build_record(issued, root=self.root, ledgers=[self.ledger], features=[]), record)
        copied = self.root / 'copied/reads.jsonl'
        r.copy_issuance(record, copied, root=self.root, ledgers=[self.ledger])
        self.assertEqual(r.ledger_rows(copied), r.ledger_rows(self.ledger))
        with self.assertRaises(r.ReadingSourcesChanged) as failure:
            r.require_route_reading(record, root=self.root, ledgers=[self.ledger], features=['extra'])
        self.assertEqual([row['path'] for row in failure.exception.changes], ['notes/extra.md'])
        self.assertEqual(failure.exception.as_dict()['code'], 'READING_SOURCES_CHANGED')
        from production_diagnostics import from_exception
        diagnostic = from_exception(failure.exception, phase='authoring', file='choices.json')
        self.assertEqual(diagnostic['changes'], failure.exception.changes)
        self.assertEqual(diagnostic['code'], 'READING_SOURCES_CHANGED')
        self.assertEqual(diagnostic['file'], 'choices.json')
        self.assertEqual(diagnostic['required_action'], failure.exception.required_action)

    def test_same_context_read_issues_current_scope_without_repeated_bodies(self):
        issued = self.issued()
        before = self.ledger.read_bytes()
        reused = r.read_page(route='generation', root=self.root, ledger=self.ledger, stream=io.StringIO(),
                             operation='save', execution='dispatcher', known_reading_keys=[issued['reading_key']])
        self.assertTrue(reused['same_context_required'])
        self.assertEqual(reused['body'], [])
        self.assertEqual(reused['issued']['row']['operation'], 'save')
        self.assertNotEqual(reused['issued']['reading_key'], issued['reading_key'])
        self.assertTrue(self.ledger.read_bytes().startswith(before))
        self.assertEqual(reused['progress']['reused_bytes'], reused['progress']['required_bytes'])
        changed = b'# Changed work\nA current source.\n'
        (self.root / 'notes/work.md').write_bytes(changed)
        current = r.read_page(route='generation', root=self.root, ledger=self.ledger, stream=io.StringIO(),
                              operation='save', execution='dispatcher', known_reading_keys=[issued['reading_key']])
        self.assertEqual([item['metadata']['path'] for item in current['body']], ['notes/work.md'])
        self.assertEqual(current['body'][0]['text'].encode(), changed)
        self.assertEqual(current['progress']['reused_bodies'], 1)
        r.require_route_reading(r.draft_record(current['issued']), root=self.root, ledgers=[self.ledger])

    def test_phase_continuation_combines_multiple_complete_readings_and_keeps_origins(self):
        for name in ('prepare', 'execute', 'review', 'adopt'):
            path = 'notes/' + name + '.md'
            (self.root / path).write_bytes(('# ' + name + '\nComplete ' + name + ' contract.\n').encode())
            self.manifest['operation_contexts'][name]['reads'].append(path)
        self.manifest['operation_contexts']['review']['reads'] += ['notes/prepare.md', 'notes/execute.md']
        self.manifest['operation_contexts']['adopt']['reads'] += ['notes/prepare.md', 'notes/review.md']
        (self.root / 'config/execution-routes.json').write_bytes(c.encoded(self.manifest))
        prepared = self.root / 'prepared-request.json'
        original = b'{"prompt":"The retained character choice.","seed":31}\n'
        prepared.write_bytes(original)
        keys, seen = [], set()
        delivered = 0
        for operation in ('prepare', 'execute', 'review', 'adopt'):
            output = io.StringIO()
            result = r.read_page(route='generation', operation=operation, execution='dispatcher',
                                 root=self.root, ledger=self.ledger, stream=output, known_reading_keys=keys,
                                 **({'scope': 'studio-slot', 'source_kind': 'production-candidate'} if operation == 'adopt' else {}))
            response = json.loads(output.getvalue())
            paths = [item['metadata']['path'] for item in response['body']]
            self.assertTrue(paths)
            self.assertFalse(set(paths) & seen)
            self.assertEqual(response['reading']['key'], result['issued']['reading_key'])
            self.assertIsNone(response['actions']['continue'])
            seen.update(paths)
            delivered += result['progress']['total_bytes']
            keys = result['context_reuse']['known_reading_keys']
            record = r.draft_record(result['issued'])
            r.require_route_reading(record, root=self.root, ledgers=[self.ledger], operation=operation)
            self.assertEqual(prepared.read_bytes(), original)
        self.assertEqual(delivered, sum((self.root / path).stat().st_size for path in seen))
        adopted = result['issued']['row']
        first = r.resolve_issuance(keys[0], ledgers=[self.ledger])['row']
        work = next(item for item in adopted['delivery']['bodies'] if item['body']['path'] == 'notes/work.md')
        self.assertEqual(work['origin']['key_sha256'], first['key_sha256'])
        self.assertNotEqual(work['reused_from'], first['key_sha256'])
        copied = self.root / 'isolated-copy/reads.jsonl'
        r.copy_issuance(r.draft_record(result['issued']), copied, root=self.root, ledgers=[self.ledger])
        r.require_route_reading(r.draft_record(result['issued']), root=self.root, ledgers=[copied])
        self.assertEqual(r.ledger_rows(copied)[0]['delivery'], adopted['delivery'])

    def test_partial_delivery_never_supplies_known_bodies_and_fresh_read_ignores_ledger(self):
        partial = r.read_page(route='generation', execution='dispatcher', root=self.root,
                              ledger=self.ledger, stream=io.StringIO(), page_bytes=17)
        self.assertIsNone(partial['reading'])
        self.assertIsNone(partial['context_reuse'])
        self.assertFalse(partial['same_context_required'])
        with self.assertRaisesRegex(ValueError, 'no issuance row'):
            r.read_page(route='generation', execution='dispatcher', root=self.root, ledger=self.ledger,
                        stream=io.StringIO(), known_reading_keys=['a' * 32])
        complete = r.read_page(cursor=partial['cursor'], root=self.root, ledger=self.ledger,
                               stream=io.StringIO(), page_bytes=10000)
        self.assertTrue(complete['same_context_required'])
        fresh = r.read_page(route='generation', execution='dispatcher', root=self.root,
                            ledger=self.ledger, stream=io.StringIO())
        self.assertEqual(fresh['progress']['reused_bytes'], 0)
        self.assertFalse(fresh['same_context_required'])
        self.assertEqual(fresh['progress']['total_bytes'], complete['progress']['total_bytes'])
        self.assertEqual(fresh['progress']['total_bytes'], fresh['progress']['required_bytes'])
        self.assertEqual(len(fresh['body']), len(fresh['issued']['row']['documents']))

    def test_context_delta_replay_and_interruption_preserve_complete_union(self):
        issued = self.issued()
        self.manifest['operation_contexts']['execute']['reads'].append('notes/extra.md')
        (self.root / 'config/execution-routes.json').write_bytes(c.encoded(self.manifest))
        first = r.read_page(route='generation', operation='execute', execution='dispatcher',
                            root=self.root, ledger=self.ledger, stream=io.StringIO(),
                            known_reading_keys=[issued['reading_key']], page_bytes=31)
        replay = r.read_page(cursor=first['cursor'], replay=True, root=self.root, ledger=self.ledger,
                             stream=io.StringIO(), page_bytes=11)
        self.assertEqual(replay['body'][0]['metadata']['start'], 0)
        self.assertEqual(replay['body'][0]['metadata']['path'], 'notes/extra.md')
        self.assertEqual(len(r.ledger_rows(self.ledger)), 1)
        complete = r.read_page(cursor=replay['cursor'], root=self.root, ledger=self.ledger,
                               stream=io.StringIO(), page_bytes=10000)
        self.assertEqual(complete['progress']['page_end'], first['progress']['page_end'])
        self.assertIsNone(complete['reading'])
        while complete['reading'] is None:
            complete = r.read_page(cursor=complete['cursor'], root=self.root, ledger=self.ledger,
                                   stream=io.StringIO(), page_bytes=10000)
        self.assertEqual(complete['progress']['reused_bodies'], 2)
        self.assertEqual(complete['progress']['delivered_bytes'], (self.root / 'notes/extra.md').stat().st_size)
        r.require_route_reading(r.draft_record(complete['issued']), root=self.root,
                                ledgers=[self.ledger], operation='execute')
        again = r.read_page(cursor=complete['cursor'], replay=True, root=self.root,
                            ledger=self.ledger, stream=io.StringIO(), page_bytes=10000)
        self.assertNotEqual(again['issued']['reading_key'], complete['issued']['reading_key'])
        self.assertEqual(again['issued']['row']['documents'], complete['issued']['row']['documents'])

    def test_changed_reused_source_during_new_body_delivery_never_issues_current_receipt(self):
        issued = self.issued()
        self.manifest['operation_contexts']['execute']['reads'].append('notes/extra.md')
        (self.root / 'config/execution-routes.json').write_bytes(c.encoded(self.manifest))
        first = r.read_page(route='generation', operation='execute', execution='dispatcher',
                            root=self.root, ledger=self.ledger, stream=io.StringIO(),
                            known_reading_keys=[issued['reading_key']], page_bytes=11)
        (self.root / 'notes/work.md').write_bytes(b'# Changed during delivery\nCurrent source.\n')
        output = io.StringIO()
        with self.assertRaises(r.ReadingSourcesChanged) as failed:
            r.read_page(cursor=first['cursor'], root=self.root, ledger=self.ledger,
                        stream=output, page_bytes=10000)
        self.assertEqual(len(r.ledger_rows(self.ledger)), 1)
        response = json.loads(output.getvalue())
        self.assertFalse(response['ok'])
        self.assertIsNone(response['reading'])
        self.assertEqual(response['changes'][0]['path'], 'notes/work.md')
        self.assertNotIn('--known-reading', failed.exception.actions['restart']['argv'])

    def test_model_family_service_and_resource_changes_deliver_their_current_bodies(self):
        from model_prompt_input_fixtures import prompt_input
        catalog, _ = self.family_catalog()
        models = {name: {'id': name, 'prompt_dialect': family,
                         'prompt_input': prompt_input('tag-based', vocabularies=('synthetic',)),
                         'offerings': [{'service': 'host-a', 'model_identifier': name + '-a'},
                                       {'service': 'host-b', 'model_identifier': name + '-b'}]}
                  for name, family in (('model-a', 'family-a'), ('model-b', 'family-b'))}
        def read(name, keys, service='host-a'):
            return r.read_page(route='generation', features=['prompt-dialect'], execution='dispatcher',
                               root=self.root, ledger=self.ledger, stream=io.StringIO(), model=name,
                               service=service, known_reading_keys=keys, page_bytes=100000)
        with catalog, patch.object(r, '_selected_model', side_effect=lambda name: (name, models[name])):
            first = read('model-a', [])
            switched = read('model-b', [first['issued']['reading_key']])
            self.assertEqual([item['metadata']['kind'] for item in switched['body']], ['resource', 'resource', 'model'])
            self.assertEqual(switched['progress']['reused_bodies'], 2)
            service = read('model-b', switched['context_reuse']['known_reading_keys'], service='host-b')
            self.assertEqual([item['metadata']['kind'] for item in service['body']], ['model'])
            self.assertEqual(service['issued']['row']['model']['service'], 'host-b')
            returned = read('model-a', service['context_reuse']['known_reading_keys'])
            self.assertEqual(returned['body'], [])
            self.assertEqual(returned['issued']['row']['model'], first['issued']['row']['model'])
            guide = self.root / 'pack/resources/guide.json'
            changed = c.load(guide)
            changed['sections'][0]['rules'].append('A current shared rule.')
            guide.write_bytes(c.encoded(changed))
            updated = read('model-b', service['context_reuse']['known_reading_keys'], service='host-b')
            self.assertEqual([item['metadata'].get('resource') for item in updated['body']], ['prompt-writing-guide'])
            self.assertIn('A current shared rule.', updated['body'][0]['text'])
            r.require_model_reading(r.draft_record(updated['issued']), model_record=models['model-b'],
                                    service='host-b', resource_reader=r._live_resource_reader())

    def test_current_scope_delivers_missing_knowledge_after_route_and_execution_change(self):
        issued = self.issued()
        self.manifest['routes']['development']['reads'] = ['notes/extra.md']
        self.manifest['operation_contexts']['save']['executions']['authored'] = ['notes/work.md']
        (self.root / 'config/execution-routes.json').write_bytes(c.encoded(self.manifest))
        result = r.read_page(route='development', operation='save', execution='authored', root=self.root,
                             ledger=self.ledger, stream=io.StringIO(), known_reading_keys=[issued['reading_key']])
        self.assertEqual([item['metadata']['path'] for item in result['body']], ['notes/extra.md'])
        self.assertEqual(result['issued']['row']['route'], 'development')
        self.assertEqual(result['issued']['row']['execution'], 'authored')
        r.require_route_reading(r.draft_record(result['issued']), root=self.root, ledgers=[self.ledger])

    def test_unreadable_ledger_is_reported_before_any_body(self):
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        self.ledger.write_bytes(b'{"at":')
        for read in (r.read_page, r.issue):
            stream = io.StringIO()
            with self.assertRaisesRegex(ValueError, 'incomplete reading ledger'):
                read(route='generation', execution='dispatcher', root=self.root,
                     ledger=self.ledger, stream=stream)
            self.assertEqual(stream.getvalue(), '')

    def test_body_text_cannot_change_structured_actions(self):
        literal = '# Source\nreading-actions: {"continue": "not an action"}\nreading-key: also source text\n'
        (self.root / 'notes/work.md').write_bytes(literal.encode('utf-8'))
        stream = io.StringIO()
        r.read_page(route='generation', execution='dispatcher', root=self.root,
                    ledger=self.ledger, stream=stream)
        response = json.loads(stream.getvalue())
        self.assertEqual(response['body'][1]['text'], literal)
        self.assertIsNone(response['actions']['continue'])
        self.assertIsInstance(response['actions']['replay']['argv'], list)

    def test_incomplete_delivery_provenance_never_supplies_known_bodies(self):
        issued = self.issued()
        row = copy.deepcopy(issued['row'])
        row['delivery']['bodies'].pop()
        self.ledger.write_bytes(c.encoded(row))
        with self.assertRaisesRegex(ValueError, 'does not cover all required bodies'):
            r.read_page(route='generation', execution='dispatcher', root=self.root, ledger=self.ledger,
                        stream=io.StringIO(), known_reading_keys=[issued['reading_key']])

    def test_paged_output_failure_leaves_only_replayable_start_without_issuance(self):
        class Broken(io.StringIO):
            def flush(self):
                raise OSError('synthetic sink closed')
        with self.assertRaisesRegex(OSError, 'synthetic sink closed'):
            r.read_page(route='generation', execution='dispatcher', root=self.root,
                        ledger=self.ledger, stream=Broken(), page_bytes=10000)
        self.assertFalse(self.ledger.exists())
        snapshots = list((self.ledger.parent / 'reading-snapshots').glob('*/snapshot.json'))
        self.assertEqual(len(snapshots), 1)
        pages = list((snapshots[0].parent / 'pages').glob('*.json'))
        self.assertEqual(len(pages), 1)
        self.assertEqual(c.load(pages[0])['start'], c.load(pages[0])['end'])
        result = r.read_page(cursor=snapshots[0].parent.name + ':' + pages[0].stem,
                             root=self.root, ledger=self.ledger, stream=io.StringIO(), page_bytes=10000)
        self.assertEqual(result['body'][0]['metadata']['start'], 0)
        self.assertIsNotNone(result['reading'])

    def test_capture_reads_each_document_once_per_acquisition(self):
        from collections import Counter
        reads = Counter()
        def acquire(path):
            reads[path] += 1
            return (self.root / path).read_bytes()
        manifest, bodies = r.capture('generation', execution='dispatcher', root=self.root, read_source=acquire)
        self.assertEqual(set(reads), {r.execution_routes.MANIFEST, *(row['path'] for row in manifest['documents'])})
        self.assertTrue(all(count == 1 for count in reads.values()), reads)
        self.assertEqual(len(bodies), len(manifest['documents']))

    def test_model_guidance_serialization_ignores_dictionary_insertion_order(self):
        from model_prompt_input_fixtures import prompt_input
        model = {'id': 'synthetic-ordering-model', 'prompt_input': prompt_input('descriptive'),
                 'recommended_positive_prompt': 'A selected subject.'}
        first, body = r._model_material(model, None)
        reordered = json.loads(json.dumps(model, sort_keys=True))
        second, reordered_body = r._model_material(reordered, None)
        self.assertEqual((first, body), (second, reordered_body))

    def test_document_update(self):
        record=self.record(); (self.root/'notes/work.md').write_text(PARAGRAPH+' changed', encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'documents'): self.verify(record)
    def test_unrelated_issuance_preserves_record(self):
        record=self.record(); before=c.content_id(record)
        r.issue('development',root=self.root,ledger=self.ledger,stream=io.StringIO(), execution='authored')
        self.verify(record); self.assertEqual(before,c.content_id(record))
    def test_route_is_not_inferred(self):
        record=self.record('development')
        with self.assertRaisesRegex(ValueError,'route must'): self.verify(record)
    def test_feature_mismatch(self):
        record=self.record();record['features']=['extra']
        with self.assertRaises(ValueError): self.verify(record)
    def test_equivalent_operation_coverage_reuses_actual_delivery(self):
        issued = r.issue('development', operation='author', root=self.root, ledger=self.ledger, stream=io.StringIO(), execution='authored')
        record = r.draft_record(issued)
        row = r.require_route_reading(record, root=self.root, ledgers=[self.ledger], operation='save')
        self.assertEqual(row['operation'], 'author')
    def test_current_operation_requires_its_complete_contract(self):
        self.manifest['operation_contexts']['execute']['reads'].append('notes/execute.md')
        (self.root/'notes/execute.md').write_bytes(b'# Execute\n\nThe send and recovery contract.\n')
        (self.root/'config/execution-routes.json').write_bytes(c.encoded(self.manifest))
        record = self.record()
        with self.assertRaisesRegex(ValueError, 'current operation'):
            r.require_route_reading(record, root=self.root, ledgers=[self.ledger], operation='execute')
        issued = r.issue('generation', operation='execute', root=self.root, ledger=self.ledger, stream=io.StringIO(), execution='dispatcher')
        r.require_route_reading(r.draft_record(issued), root=self.root, ledgers=[self.ledger], operation='execute')
    def test_operation_metadata_cannot_be_reassigned_to_another_delivery(self):
        record = self.record(); record['operation'] = 'author'
        with self.assertRaisesRegex(ValueError, 'issuance'):
            self.verify(record)
    def test_execution_coverage_uses_required_sources_and_preserves_issuance(self):
        for name in r.execution_routes.OPERATIONS:
            self.manifest['operation_contexts'][name]['executions']['dispatcher'] = ['notes/dispatcher.md']
        (self.root/'notes/dispatcher.md').write_bytes(b'# Dispatcher\n\nRetain exact transport and authentication recovery.\n')
        (self.root/'config/execution-routes.json').write_bytes(c.encoded(self.manifest))
        issued = r.issue('generation', execution='external', root=self.root, ledger=self.ledger, stream=io.StringIO())
        record = r.draft_record(issued)
        with self.assertRaisesRegex(ValueError, 'current operation and execution'):
            r.require_route_reading(record, root=self.root, ledgers=[self.ledger], execution='dispatcher')
        complete = self.record()
        row = r.require_route_reading(complete, root=self.root, ledgers=[self.ledger], execution='external')
        self.assertEqual(row['execution'], 'dispatcher')
        changed = copy.deepcopy(complete); changed['execution'] = 'external'
        with self.assertRaisesRegex(ValueError, 'documents|issuance'):
            self.verify(changed)
    def test_markdown_and_nonprose_are_delivered_as_complete_source_bytes(self):
        raw = b'# Heading\n\n| field | value |\n| --- | --- |\n| A | **B** |\n\n```text\nliteral [link](source.md)\n```\n'
        (self.root/'notes/work.md').write_bytes(raw)
        stream = io.StringIO()
        issued = r.issue('generation', root=self.root, ledger=self.ledger, stream=stream, execution='dispatcher')
        self.assertIn(raw.decode('utf-8'), [item['text'] for item in json.loads(stream.getvalue())['body']])
        self.verify(r.draft_record(issued))
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
        with self.assertRaises(OSError):r.issue('generation',root=self.root,ledger=self.ledger,stream=Broken(), execution='dispatcher')
        self.assertFalse(self.ledger.exists())
    def test_index_partitions_exact_sources_without_delivering_or_issuing(self):
        raw = b'Opening.\r\n\r\n# Work\r\n\r\n```markdown\r\n## Example only\r\n```\r\n\r\n## Required detail\r\nText.\r\n\r\nFinal condition\r\n---------------\r\nLast bytes.\r\n'
        (self.root/'notes/work.md').write_bytes(raw)
        output=io.StringIO()
        indexed=r.read_page(route='generation',execution='dispatcher',navigation=True,
                            root=self.root,ledger=self.ledger,stream=output)
        self.assertEqual((indexed['mode'], indexed['body'], indexed['reading'], indexed['context_reuse']),
                         ('index', [], None, None))
        self.assertNotIn('Text.',output.getvalue())
        self.assertEqual(indexed['progress']['delivered_bytes'],0)
        self.assertFalse(self.ledger.exists())
        work=next(row for row in indexed['index'] if row['path']=='notes/work.md')
        self.assertEqual(work['sha256'],c.digest(raw))
        self.assertEqual(work['selected_by'],['route:generation'])
        self.assertEqual(work['sections'], [])
        self.assertEqual(work['section_count'], 4)
        self.assertFalse(work['sections_expanded'])
        self.assertTrue(all(key in indexed['selection_reasons'] for key in work['selection_reason_ids']))
        expanded = self.expanded_index(indexed)
        work=next(row for row in expanded['index'] if row['path']=='notes/work.md')
        self.assertEqual([row['heading'] for row in work['sections']],
                         ['Source opening','Work','Required detail','Final condition'])
        self.assertEqual(sum(row['bytes'] for row in work['sections']),len(raw))
        self.assertEqual(work['remaining_bytes'],len(raw))
        self.assertIsNone(indexed['actions']['continue'])
        self.assertIsNone(indexed['actions']['replay'])
        self.assertIn('--section',indexed['actions']['next']['argv'])

    def test_out_of_order_section_delivery_and_all_preserve_complete_exact_coverage(self):
        raw=b'# Work\nOpening.\n\n## First\nFirst condition.\n\n## Last\nLast condition.\n'
        (self.root/'notes/work.md').write_bytes(raw)
        indexed=r.read_page(route='generation',execution='dispatcher',navigation=True,
                            root=self.root,ledger=self.ledger,stream=io.StringIO())
        indexed=self.expanded_index(indexed)
        selector=indexed['index'][-1]['sections'][-1]['selector']
        result=r.read_page(snapshot_id=indexed['snapshot'],section=selector,root=self.root,
                           ledger=self.ledger,stream=io.StringIO())
        self.assertIsNone(result['reading'])
        self.assertFalse(result['same_context_required'])
        self.assertIsNone(result['actions']['continue'])
        self.assertIsNotNone(result['actions']['next'])
        self.assertFalse(self.ledger.exists())
        segments=list(result['body'])
        result=r.read_page(snapshot_id=indexed['snapshot'],root=self.root,ledger=self.ledger,
                           stream=io.StringIO(),page_bytes=10000)
        self.assertTrue(result['same_context_required'])
        segments.extend(result['body'])
        while result['reading'] is None:
            result=r.read_page(cursor=result['cursor'],root=self.root,ledger=self.ledger,
                               stream=io.StringIO(),page_bytes=10000)
            segments.extend(result['body'])
        for path in ('notes/always.md','notes/work.md'):
            chunks=sorted((item['metadata']['start'],item['text'].encode('utf-8'))
                          for item in segments if item['metadata']['path']==path)
            self.assertEqual(b''.join(body for _,body in chunks),(self.root/path).read_bytes())
            self.assertEqual(sum(len(body) for _,body in chunks),(self.root/path).stat().st_size)
        self.assertEqual(result['remaining_bytes'],0)
        self.assertIsNone(result['actions']['next'])
        self.verify(r.draft_record(result['issued']))

    def test_known_reading_index_and_fresh_context_preserve_distinct_knowledge(self):
        issued=self.issued()
        indexed=r.read_page(route='generation',execution='dispatcher',navigation=True,
                            root=self.root,ledger=self.ledger,stream=io.StringIO(),
                            known_reading_keys=[issued['reading_key']])
        self.assertEqual(indexed['progress']['remaining_bytes'],0)
        self.assertEqual(indexed['progress']['reused_bodies'],2)
        self.assertTrue(all(source['selector'] is None and source['sections']==[]
                            for source in indexed['index']))
        self.assertIsNone(indexed['reading'])
        self.assertEqual(len(r.ledger_rows(self.ledger)),1)
        complete=r.read_page(snapshot_id=indexed['snapshot'],root=self.root,ledger=self.ledger,
                             stream=io.StringIO())
        self.assertEqual(complete['body'],[])
        self.assertEqual(len(r.ledger_rows(self.ledger)),2)
        for item in complete['issued']['row']['delivery']['bodies']:
            self.assertEqual(item['origin']['key_sha256'],issued['row']['key_sha256'])
        fresh=r.read_page(route='generation',execution='dispatcher',navigation=True,
                          root=self.root,ledger=self.ledger,stream=io.StringIO())
        self.assertIsNone(fresh['reading'])
        self.assertEqual(fresh['progress']['reused_bytes'],0)
        self.assertEqual(fresh['progress']['remaining_bytes'],fresh['progress']['required_bytes'])
        self.assertEqual(len(r.ledger_rows(self.ledger)),2)

    def test_sections_retain_the_selected_family_and_complete_model_bytes(self):
        from model_prompt_input_fixtures import prompt_input
        catalog,_=self.family_catalog()
        model_file=self.root/'selected-model.json'
        model_file.write_bytes(c.encoded({'id':'synthetic-model','prompt_dialect':'family-b',
            'prompt_input':prompt_input('tag-based',vocabularies=('synthetic',))}))
        with catalog:
            indexed=r.read_page(route='generation',features=['prompt-dialect'],execution='dispatcher',
                navigation=True,model_file=model_file,root=self.root,ledger=self.ledger,stream=io.StringIO())
            indexed=self.expanded_index(indexed)
            manifest,bodies=r.capture('generation',['prompt-dialect'],execution='dispatcher',
                                      model_file=model_file,root=self.root)
            expected={meta['sha256']:raw for meta,raw in bodies}
            actual={}
            selectors=[section['selector'] for source in indexed['index'] for section in source['sections']]
            for number,selector in enumerate(reversed(selectors)):
                result=r.read_page(snapshot_id=indexed['snapshot'],section=selector,root=self.root,
                                   ledger=self.ledger,stream=io.StringIO(),page_bytes=1000000)
                for item in result['body']:
                    meta=item['metadata']
                    actual.setdefault(meta['sha256'],[]).append((meta['start'],item['text'].encode('utf-8')))
                if number<len(selectors)-1:
                    self.assertIsNone(result['reading'])
            self.assertIsNotNone(result['reading'])
            for digest,chunks in actual.items():
                self.assertEqual(b''.join(raw for _,raw in sorted(chunks)),expected[digest])
            self.assertEqual(result['issued']['row']['resources'],manifest['resources'])
            self.assertEqual(result['issued']['row']['model'],manifest['model'])
            r.require_route_reading(r.draft_record(result['issued']),root=self.root,
                                     ledgers=[self.ledger],dialect='family-b')

    def test_out_of_order_section_recovery_preserves_selected_continuation_and_work(self):
        import production_authoring_state
        import studio_workspace as studio
        import work_ledger
        studio_root=self.root.resolve()/'studio'
        studio.init(studio_root,'section-continuation','Section continuation')
        work_ledger.begin(studio_root,'Keep the authored choices and continue the source reading.',['Compose'])
        work_before=(studio_root/'work/current.json').read_bytes()
        (self.root/'notes/work.md').write_bytes(('# Work\n\n## Detail\n'+PARAGRAPH*3+'\n').encode())
        indexed=r.read_page(route='generation',execution='dispatcher',navigation=True,
                            studio=studio_root,root=self.root,ledger=self.ledger,stream=io.StringIO())
        indexed=self.expanded_index(indexed)
        r.read_page(snapshot_id=indexed['snapshot'],section=indexed['index'][-1]['sections'][-1]['selector'],
                    page_bytes=8192,studio=studio_root,root=self.root,ledger=self.ledger,stream=io.StringIO())
        result=r.read_page(snapshot_id=indexed['snapshot'],section=indexed['index'][0]['sections'][0]['selector'],
                           page_bytes=17,studio=studio_root,root=self.root,ledger=self.ledger,stream=io.StringIO())
        report=production_authoring_state.inspect(studio_root)
        selected=next(row for row in report['readings'] if row['current'])
        self.assertEqual(selected['state'],'partial')
        self.assertEqual(selected['mode'],'section')
        self.assertEqual(selected['delivered_bytes'],result['progress']['delivered_bytes'])
        self.assertGreater(selected['delivered_bytes'],17)
        self.assertEqual(selected['remaining_bytes'],result['remaining_bytes'])
        self.assertTrue(selected['same_context_required'])
        self.assertTrue(result['same_context_required'])
        self.assertEqual(selected['next_actions'][0]['argv'],result['actions']['continue']['argv'])
        self.assertNotIn('--known-reading',selected['fresh_context_action']['argv'])
        self.assertEqual((studio_root/'work/current.json').read_bytes(),work_before)
        # Losing only the navigation pointer retains all source delivery and
        # opens the index without guessing which source offset was selected.
        (self.ledger.parent/'reading-snapshots'/indexed['snapshot']/'continuation.json').unlink()
        recovered=production_authoring_state.inspect(studio_root)
        selected=next(row for row in recovered['readings'] if row['current'])
        self.assertEqual(selected['mode'],'index')
        self.assertEqual(selected['delivered_bytes'],result['progress']['delivered_bytes'])
        self.assertIn('--snapshot',selected['next_actions'][0]['argv'])
        self.assertNotIn('--section',selected['next_actions'][0]['argv'])

    def test_sections_recheck_current_sources_before_complete_issuance(self):
        indexed=r.read_page(route='generation',execution='dispatcher',navigation=True,
                            root=self.root,ledger=self.ledger,stream=io.StringIO())
        r.read_page(snapshot_id=indexed['snapshot'],section=indexed['index'][-1]['selector'],
                    root=self.root,ledger=self.ledger,stream=io.StringIO())
        (self.root/'notes/always.md').write_bytes(b'# Changed current condition\n')
        with self.assertRaises(r.ReadingSourcesChanged) as failure:
            r.read_page(snapshot_id=indexed['snapshot'],root=self.root,ledger=self.ledger,
                        stream=io.StringIO(),page_bytes=10000)
        self.assertEqual(failure.exception.changes[0]['path'],'notes/always.md')
        self.assertIn('--restart',failure.exception.actions['restart']['argv'])
        self.assertFalse(self.ledger.exists())

    def test_small_replay_of_complete_reading_finishes_that_page_before_issuance(self):
        first=r.read_page(route='generation',execution='dispatcher',root=self.root,
                          ledger=self.ledger,stream=io.StringIO())
        replay=r.read_page(cursor=first['cursor'],replay=True,page_bytes=8,
                           root=self.root,ledger=self.ledger,stream=io.StringIO())
        self.assertEqual(replay['remaining_bytes'],0)
        self.assertIsNone(replay['reading'])
        self.assertIsNotNone(replay['actions']['continue'])
        self.assertEqual(len(r.ledger_rows(self.ledger)),1)
        complete=r.read_page(cursor=replay['cursor'],page_bytes=10000,
                             root=self.root,ledger=self.ledger,stream=io.StringIO())
        self.assertEqual(complete['progress']['page_start'],8)
        self.assertEqual(complete['progress']['page_end'],first['progress']['page_end'])
        self.assertNotEqual(complete['reading']['key'],first['reading']['key'])

    def test_unicode_paging_is_lossless(self):
        raw=(PARAGRAPH+' café\n').encode()
        (self.root/'notes/work.md').write_bytes(raw)
        stream=io.StringIO();result=r.read_page(route='generation',page_bytes=13,root=self.root,ledger=self.ledger,stream=stream, execution='dispatcher')
        ranges=list(result['delivered'])
        while result['remaining_bytes']:
            self.assertNotIn('issued',result)
            self.assertFalse(self.ledger.exists())
            result=r.read_page(cursor=result['cursor'],page_bytes=13,root=self.root,ledger=self.ledger,stream=stream)
            ranges.extend(result['delivered'])
        for name in ('notes/always.md','notes/work.md'):
            original=(self.root/name).read_bytes()
            chunks=[original[x['start']:x['end']] for x in ranges if x['path']==name]
            self.assertEqual(b''.join(chunks),original)
            for chunk in chunks:chunk.decode('utf-8')
        self.assertIn('issued',result)
    def test_replay_then_continue(self):
        first=r.read_page(route='generation',page_bytes=23,root=self.root,ledger=self.ledger,stream=io.StringIO(), execution='dispatcher')
        replay=r.read_page(cursor=first['cursor'],replay=True,page_bytes=8,root=self.root,ledger=self.ledger,stream=io.StringIO())
        self.assertEqual(replay['delivered'][0]['start'],0)
        self.assertEqual(replay['remaining_bytes'],first['remaining_bytes'])
        self.assertEqual(replay['progress']['replay_remaining_bytes'],15)
        resumed=r.read_page(cursor=replay['cursor'],page_bytes=10000,root=self.root,ledger=self.ledger,stream=io.StringIO())
        self.assertEqual((resumed['progress']['page_start'],resumed['progress']['page_end']),(8,23))
        self.assertIsNone(resumed['reading'])
    def test_cursor_cannot_skip(self):
        result=r.read_page(route='generation',page_bytes=23,root=self.root,ledger=self.ledger,stream=io.StringIO(), execution='dispatcher')
        with self.assertRaises(ValueError):r.read_page(cursor=result['snapshot']+':'+('0'*64),root=self.root,ledger=self.ledger,stream=io.StringIO())
        self.assertFalse(self.ledger.exists())
    def test_final_replay_issues_new_key(self):
        result=r.read_page(route='generation',root=self.root,ledger=self.ledger,stream=io.StringIO(), execution='dispatcher')
        new=r.read_page(cursor=result['cursor'],replay=True,root=self.root,ledger=self.ledger,stream=io.StringIO())
        self.assertNotEqual(result['issued']['reading_key'],new['issued']['reading_key'])
    def test_stale_snapshot_never_issues(self):
        result=r.read_page(route='generation',page_bytes=13,root=self.root,ledger=self.ledger,stream=io.StringIO(), execution='dispatcher')
        (self.root/'notes/work.md').write_text(PARAGRAPH+' New source.', encoding='utf-8')
        with self.assertRaises(r.ReadingSourcesChanged) as failure:
            r.read_page(cursor=result['cursor'],page_bytes=10000,root=self.root,ledger=self.ledger,stream=io.StringIO())
        self.assertEqual(failure.exception.changes[0]['path'], 'notes/work.md')
        restart = failure.exception.as_dict()['actions']['restart']['argv']
        self.assertIn('--restart', restart)
        self.assertEqual(restart[restart.index('--reading-ledger') + 1], str(self.ledger))
        self.assertFalse(self.ledger.exists())
    def test_invalid_page_budget(self):
        with self.assertRaises(ValueError):r.read_page(route='generation',page_bytes=0,root=self.root,ledger=self.ledger, execution='dispatcher')

    def test_manifest_digest_binds_manifest_bytes_not_the_last_source(self):
        manifest_path = self.root / r.execution_routes.MANIFEST
        first = r.execution_routes.resolve('generation', execution='dispatcher', root=self.root)
        expected = c.digest(manifest_path.read_bytes())
        self.assertEqual(first['manifest_sha256'], expected)
        (self.root / 'notes/work.md').write_bytes(b'# Changed document\nIts independent source edition.\n')
        changed_document = r.execution_routes.resolve('generation', execution='dispatcher', root=self.root)
        self.assertEqual(changed_document['manifest_sha256'], expected)
        self.assertNotEqual(first['reads'][-1]['sha256'], changed_document['reads'][-1]['sha256'])
        self.manifest['features']['extra']['source_roles'] = ['declared-role']
        manifest_path.write_bytes(c.encoded(self.manifest))
        changed_manifest = r.execution_routes.resolve('generation', execution='dispatcher', root=self.root)
        self.assertNotEqual(changed_manifest['manifest_sha256'], expected)
        self.assertEqual(changed_manifest['manifest_sha256'], c.digest(manifest_path.read_bytes()))

    def test_operation_profiles_refine_selected_features_and_execution_without_new_scope(self):
        raw = b'# Work\nSource opening.\n\n## Common\nCommon authority.\n\n## Prepare\nExact input and recovery.\n\n## Execute\nPerform the actual send.\n'
        (self.root / 'notes/work.md').write_bytes(raw)
        self.manifest['features']['complete'] = {'reads': ['notes/work.md'], 'source_roles': []}
        self.manifest['reading_scopes']['prepare'] = {'documents': {
            'notes/work.md': [
                {'sections': ['common'], 'reason': 'Preserve the common authority.'},
                {'sections': ['prepare'], 'reason': 'Prepare the exact input.', 'executions': ['dispatcher']},
                {'whole_source': True, 'reason': 'The complete specialist was explicitly selected.',
                 'features_any': ['complete']}],
            'notes/extra.md': [{'whole_source': True, 'reason': 'Only when extra is actually selected.'}]}}
        (self.root / r.execution_routes.MANIFEST).write_bytes(c.encoded(self.manifest))
        record, bodies = r.capture('generation', execution='dispatcher', root=self.root)
        self.assertIsNone(record['scope']); self.assertIsNone(record['source_kind'])
        self.assertNotIn('notes/extra.md', [item['path'] for item in record['documents']])
        selected = [(meta, body) for meta, body in bodies if meta.get('path') == 'notes/work.md']
        self.assertEqual(len(selected), 1)  # Adjacent complete sections form one exact interval.
        self.assertEqual(selected[0][1], raw[raw.index(b'## Common'):raw.index(b'## Execute')])
        external, external_bodies = r.capture('generation', execution='external', root=self.root)
        self.assertNotIn(b'## Prepare', b''.join(body for _, body in external_bodies))
        complete, complete_bodies = r.capture('generation', ['complete'], execution='dispatcher', root=self.root)
        self.assertEqual(next(body for meta, body in complete_bodies if meta.get('path') == 'notes/work.md'), raw)
        self.assertEqual(complete['documents'][-1]['ranges'], [{'start': 0, 'end': len(raw), 'sha256': c.digest(raw)}])
        ordinary, ordinary_bodies = r.capture('generation', operation='execute', execution='dispatcher', root=self.root)
        self.assertIn(raw, [body for _, body in ordinary_bodies])

    def test_actual_prepare_profile_retains_complete_boundaries_and_excludes_later_procedures(self):
        resolved = r.execution_routes.resolve('generation',
            ['vocabulary', 'sparse-retrieval', 'performance-language', 'unlisted-interface'],
            operation='prepare', execution='dispatcher')
        by_path = {path: {row['anchor'] for row in sections}
                   for path, sections in resolved['section_owners'].items()}
        self.assertTrue({'form-a-prompt-from-an-image', 'form-a-prompt-from-an-idea',
                         'preserve-accepted-variation-at-its-declared-scope', 'worked-depictions',
                         'an-image-of-an-action-is-not-the-action'} <= by_path['references/runtime/production-direction.md'])
        self.assertFalse({'observe-and-repair', 'a-failure-must-leave-an-actionable-record'}
                         & by_path['references/runtime/production-direction.md'])
        self.assertTrue({'verification-and-host-forwarding', 'preview-a-prepared-request', 'failure-policy'}
                        <= by_path['references/runtime/generation-package.md'])
        self.assertNotIn('capture-and-recover-the-provider-result', by_path['references/runtime/generation-package.md'])
        self.assertFalse({'authorization-and-execution-records', 'add-authority-for-selected-canonical-use',
                          'reuse-stop-judgments-for-the-same-selected-image'}
                         & by_path['references/runtime/production-permissions.md'])
        self.assertNotIn('display-publication-ownership', by_path['references/runtime/studio.md'])
        self.assertNotIn('upload-the-selected-media-for-one-generation', by_path['references/runtime/reference-delivery.md'])
        self.assertNotIn('external-image-work', by_path['references/runtime/render-contract.md'])
        self.assertNotIn('design-a-trial', by_path['references/runtime/model-evidence.md'])
        for path in ('references/prompt-knowledge-boundary.md',
                     'references/performance-language-specification.md', 'references/runtime/prompt-vocabulary.md'):
            source = (r.ROOT / path).read_bytes()
            selected = next(item for item in resolved['reads'] if item['path'] == path)
            self.assertEqual(selected['ranges'], [{'start': 0, 'end': len(source), 'sha256': c.digest(source)}])
        external = r.execution_routes.resolve('generation', operation='prepare', execution='external')
        self.assertIn('external-image-work',
                      {row['anchor'] for row in external['section_owners']['references/runtime/render-contract.md']})

    def test_sparse_foundation_expands_to_complete_finishing_with_only_missing_bytes(self):
        path = 'references/finishing-layers-specification.md'
        raw = (r.ROOT / path).read_bytes()
        with patch.object(r, '_live_resource_reader', return_value=lambda name: None):
            first = r.read_page(route='generation', features=['sparse-retrieval'], execution='dispatcher',
                root=r.ROOT, ledger=self.ledger, stream=io.StringIO(), page_bytes=1000000)
            chosen = next(item for item in first['issued']['row']['documents'] if item['path'] == path)
            foundation = sum(row['end'] - row['start'] for row in chosen['ranges'])
            sections = r.execution_routes.document_sections(raw)
            selected_ranges = {(row['start'], row['end']) for row in chosen['ranges']}
            self.assertEqual({row['anchor'] for row in sections if (row['start'], row['end']) in selected_ranges}, {
                'visual-construction-and-finishing', '1-purpose', '2-the-five-finishing-layers',
                '3-composition-order', 'visibility-and-surface-order', 'large-form-interval-and-degree',
                'color-and-value-as-a-shared-construction', 'shape-and-mark-as-one-drawing-grammar',
                '8-resolve-competition-and-choose-a-realizable-method', '9-observation-contract',
                '10-layer-specific-cautions'})
            self.assertGreater(foundation, 0)
            self.assertLess(foundation, len(raw))
            self.assertEqual(chosen['sha256'], c.digest(raw))
            indexed = r.read_page(route='generation', features=['sparse-retrieval', 'finishing'],
                execution='dispatcher', root=r.ROOT, ledger=self.ledger, stream=io.StringIO(), navigation=True,
                known_reading_keys=[first['reading']['key']])
            self.assertIsNone(indexed['reading'])
            self.assertEqual(indexed['remaining_bytes'], len(raw) - foundation)
            current = r.read_page(snapshot_id=indexed['snapshot'], root=r.ROOT, ledger=self.ledger,
                stream=io.StringIO(), page_bytes=1000000)
            self.assertEqual({item['metadata']['path'] for item in current['body']}, {path})
            self.assertEqual(sum(len(item['text'].encode()) for item in current['body']), len(raw) - foundation)
            r.require_route_reading(r.draft_record(current['issued']), root=r.ROOT, ledgers=[self.ledger],
                                   features=['sparse-retrieval', 'finishing'], execution='dispatcher', operation='prepare')
            fresh = r.read_page(route='generation', features=['sparse-retrieval', 'finishing'],
                execution='dispatcher', root=r.ROOT, ledger=self.ledger, stream=io.StringIO(), navigation=True)
            self.assertEqual(fresh['progress']['reused_bytes'], 0)
            self.assertEqual(fresh['remaining_bytes'], fresh['progress']['required_bytes'])

    def test_public_source_index_expands_navigation_without_issuing_or_counting_delivery(self):
        import argparse
        import contextlib
        with patch.object(r, '_live_resource_reader', return_value=lambda name: None):
            indexed = r.read_page(route='generation', execution='dispatcher', root=r.ROOT,
                ledger=self.ledger, stream=io.StringIO(), navigation=True)
            source = next(row for row in indexed['index'] if row['path'] == 'references/runtime/authoring-work.md')
            self.assertFalse(source['sections_expanded'])
            self.assertEqual(source['sections'], [])
            arguments = [*indexed['actions']['index']['argv'][3:], '--index-source', source['selector']]
            parser = argparse.ArgumentParser(); r.add_read_arguments(parser)
            with contextlib.redirect_stdout(io.StringIO()), patch.object(r, '_configure_runtime', return_value=None):
                detailed = r.read_command(parser.parse_args(arguments), parser)
            self.assertEqual(detailed['index_source'], source['selector'])
            self.assertEqual((detailed['body'], detailed['reading']), ([], None))
            self.assertEqual(detailed['progress']['delivered_bytes'], 0)
            self.assertEqual(detailed['progress']['required_bytes'], indexed['progress']['required_bytes'])
            self.assertTrue(detailed['index'][0]['sections_expanded'])
            self.assertEqual(len(detailed['index'][0]['sections']), source['section_count'])
            self.assertEqual(len(detailed['selection_reasons']), 1)
            for section in detailed['index'][0]['sections']:
                self.assertEqual(section['selection_reason_ids'], ['1'])
            self.assertFalse(self.ledger.exists())
            with self.assertRaisesRegex(ValueError, 'unknown source index selector'):
                r.read_page(snapshot_id=indexed['snapshot'], index_source='not-a-source', navigation=True,
                    root=r.ROOT, ledger=self.ledger, stream=io.StringIO())



class AuthoringScopeTests(unittest.TestCase):
    """Keep current staged work separate from historical delivery evidence."""

    def setUp(self):
        ReadingTests.setUp(self)
        self.raw = (b'# Work\n\nShared authoring contract.\n\n'
            b'## Definition\n\nEstablish the requested subject.\n\n'
            b'## Depiction\n\nDevelop the intended depiction.\n\n'
            b'## Image source\n\nPreserve selected source authority and exclusions.\n\n'
            b'## Wording\n\nWrite the actual selected prompt.\n\n'
            b'## Native request\n\nBind carriers without rewriting the chosen content.\n')
        (self.root / 'notes/work.md').write_bytes(self.raw)
        self.manifest['reading_scopes']['authoring'] = {'documents': {
            'notes/work.md': [
                {'sections': ['work'], 'reason': 'The common contract applies at every stage.'},
                {'stages': ['definition'], 'sections': ['definition'], 'reason': 'Define the subject now.'},
                {'stages': ['depiction'], 'sections': ['depiction'], 'reason': 'Develop the picture now.'},
                {'stages': ['depiction'], 'conditions_any': ['image-source'], 'sections': ['image-source'],
                 'reason': 'A selected image retains its scoped source authority.'},
                {'stages': ['rendition'], 'sections': ['wording'], 'reason': 'Write the selected depiction now.'},
                {'stages': ['prepare'], 'sections': ['native-request'], 'reason': 'Bind the prepared request now.'}],
            'notes/always.md': [{'stages': ['definition', 'depiction'], 'whole_source': True,
                                 'reason': 'Resolve source meanings while defining and depicting.'}],
            'notes/unselected.md': [{'whole_source': True, 'reason': 'Only the selected specialist owns this source.'}]}}
        (self.root / 'config/execution-routes.json').write_bytes(c.encoded(self.manifest))

    def scope(self, stage='definition', conditions=None):
        return {'stage': stage, 'composition': 'compose', 'source_formats': ['text'],
                'documents': [], 'render_operation': 'generation', 'conditions': sorted(conditions or [])}

    def start(self, stage='definition', **kwargs):
        return r.read_page(route='generation', execution='external', root=self.root, ledger=self.ledger,
            stream=io.StringIO(), page_bytes=1000000, authoring_scope=self.scope(stage), **kwargs)

    def test_selected_stage_preserves_exact_text_and_unmanaged_specialist(self):
        result = self.start(features=['extra'])
        bodies = {item['metadata']['path']: item['text'] for item in result['body']}
        text = ''.join(bodies.values())
        self.assertIn('Establish the requested subject.', text)
        self.assertNotIn('Develop the intended depiction.', text)
        self.assertNotIn('Bind carriers without rewriting', text)
        self.assertEqual(bodies['notes/extra.md'], (self.root / 'notes/extra.md').read_text(encoding='utf-8'))
        self.assertNotIn('notes/unselected.md', bodies)
        record = r.draft_record(result['issued'])
        self.assertEqual(record['authoring_scope'], self.scope())
        for document in record['documents']:
            source = (self.root / document['path']).read_bytes()
            self.assertEqual(document['sha256'], c.digest(source))
            for part in document['ranges']:
                self.assertEqual(part['sha256'], c.digest(source[part['start']:part['end']]))
        r.require_route_reading(record, root=self.root, ledgers=[self.ledger])

    def test_source_conditions_add_selected_image_contract_only_when_applicable(self):
        for conditions, expected in (([], False), (['image-source'], True), (['unknown-sources'], True)):
            with self.subTest(conditions=conditions):
                scope = self.scope('depiction', conditions)
                manifest, bodies = r.capture('generation', execution='external', root=self.root, authoring_scope=scope)
                self.assertEqual(b'Preserve selected source authority' in b''.join(raw for _, raw in bodies), expected)
                self.assertEqual(manifest['authoring_scope'], scope)
        prepared = self.start('prepare')
        self.assertEqual(prepared['metadata']['operation'], 'prepare')
        self.assertNotIn('notes/always.md', {item['metadata']['path'] for item in prepared['body']})

    def test_current_stage_requires_its_ranges_and_whole_source_read_can_cover_them(self):
        definition = r.draft_record(self.start()['issued'])
        with self.assertRaises(r.ReadingSourcesChanged):
            r.require_route_reading(definition, root=self.root, ledgers=[self.ledger],
                authoring_scope=self.scope('prepare'), operation='prepare')
        whole = r.issue('generation', execution='external', root=self.root, ledger=self.ledger, stream=io.StringIO())
        r.require_route_reading(r.draft_record(whole), root=self.root, ledgers=[self.ledger],
            authoring_scope=self.scope('prepare'), operation='prepare')
        changed = copy.deepcopy(definition)
        changed['authoring_scope']['stage'] = 'depiction'
        with self.assertRaisesRegex(ValueError, 'issuance differs'):
            r.require_route_reading(changed, root=self.root, ledgers=[self.ledger])
        for operation in ('execute', 'review'):
            with self.assertRaisesRegex(ValueError, 'own reading action'):
                r.capture('generation', execution='external', operation=operation, root=self.root,
                    authoring_scope=self.scope())

    def test_stage_change_reuses_only_explicit_current_context_ranges(self):
        first = self.start()
        second = self.start('depiction', known_reading_keys=[first['reading']['key']])
        self.assertGreater(second['progress']['reused_bytes'], 0)
        self.assertGreater(second['progress']['delivered_bytes'], 0)
        text = ''.join(item['text'] for item in second['body'])
        self.assertIn('Develop the intended depiction.', text)
        self.assertNotIn('Establish the requested subject.', text)
        self.assertNotIn('Shared authoring contract.', text)
        fresh = self.start('depiction', navigation=True)
        self.assertEqual(fresh['progress']['reused_bytes'], 0)
        self.assertEqual(fresh['remaining_bytes'], second['progress']['required_bytes'])
        self.assertFalse(fresh['same_context_required'])

    def test_public_choices_and_restart_keep_current_stage_without_inheriting_knowledge(self):
        import argparse
        import contextlib
        import production_reading_scope
        import studio_workspace
        studio = self.root / 'studio'
        studio_workspace.init(studio, 'stage-reading', 'Synthetic authoring stages')
        task = {'route': 'generation', 'execution': 'external', 'features': []}
        choices = {'target': None}
        def command(words):
            parser = argparse.ArgumentParser(); r.add_read_arguments(parser)
            args = parser.parse_args(words)
            with contextlib.redirect_stdout(io.StringIO()), patch.object(r, 'ROOT', self.root), \
                 patch.object(r, '_configure_runtime', return_value=None):
                return r.read_command(args, parser)
        with patch.object(production_reading_scope, 'from_choices', return_value=(self.scope(), task, choices)) as acquire:
            indexed = command(['--root', str(studio), '--choices', 'work/input/choices.json',
                               '--reading-ledger', str(self.ledger)])
        acquire.assert_called_once_with(studio, 'work/input/choices.json', include_choices=True)
        self.assertEqual(indexed['metadata']['authoring_scope'], self.scope())
        first = command(indexed['actions']['all']['argv'][3:])
        self.assertIn('--choices', first['context_reuse']['operations']['author']['argv'])
        record = c.load(Path(first['reading']['record_absolute']))
        self.assertEqual(record['authoring_scope'], self.scope())
        fresh = command(first['actions']['restart']['argv'][3:])
        self.assertEqual(fresh['metadata']['authoring_scope'], self.scope())
        self.assertEqual(fresh['progress']['reused_bytes'], 0)
        self.assertEqual(fresh['remaining_bytes'], first['progress']['required_bytes'])
        self.assertFalse(fresh['same_context_required'])
        self.assertIsNone(fresh['reading'])
        snapshot = c.load(self.ledger.parent / 'reading-snapshots' / fresh['snapshot'] / 'snapshot.json')
        self.assertEqual(snapshot['choices'], 'work/input/choices.json')


class ScopedReadingTests(unittest.TestCase):
    """Prove destination/source contracts and exact same-context range reuse."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / 'config').mkdir()
        (self.root / 'notes').mkdir()
        self.ledger = self.root / 'work/reads.jsonl'
        self.document = 'notes/contract.md'
        self.raw = b'# Contract\nOriginal source opening.\n\n## Common\nThe common condition.\n\n## Slot\nThe complete slot decision and recovery.\n\n## Sheet\nThe complete canonical approval and recovery.\n\n## Catalog\nThe exact new catalog destination and retry.\n\n## Imported\nThe imported source approval and recovery.\n\n## Withdrawal\nThe actual ending decision and historical proof.\n'
        (self.root / self.document).write_bytes(self.raw)
        base = {'reads': [self.document], 'executions': {mode: [] for mode in r.execution_routes.EXECUTIONS}}
        def selection(heading, *, scopes=None, sources=None):
            value = {'sections': [heading], 'reason': 'Complete ' + heading + ' contract, including its authority and recovery.'}
            if scopes is not None:
                value['scopes'] = scopes
            if sources is not None:
                value['source_kinds'] = sources
            return value
        self.manifest = {
            'operation_contexts': {name: copy.deepcopy(base) for name in r.execution_routes.OPERATIONS},
            'routes': {'development': {'default_operation': 'author', 'reads': [], 'features': [], 'stages': []},
                       'adoption': {'default_operation': 'adopt', 'reads': [], 'features': [], 'stages': []}},
            'features': {},
            'reading_scopes': {
                'adopt': {'documents': {self.document: [selection('common'),
                    selection('slot', scopes=['delivery-only', 'studio-slot']),
                    selection('sheet', scopes=['sheet', 'catalog'], sources=['production-candidate']),
                    selection('imported', scopes=['sheet', 'catalog'], sources=['imported-iteration']),
                    selection('catalog', scopes=['catalog'])]}},
                'withdraw': {'documents': {self.document: [selection('common'), selection('withdrawal')]}}}}
        (self.root / 'config/execution-routes.json').write_bytes(c.encoded(self.manifest))

    def start(self, scope='studio-slot', source_kind='production-candidate', **kwargs):
        return r.read_page(route='adoption', operation='adopt', execution='dispatcher',
                          scope=scope, source_kind=source_kind, root=self.root, ledger=self.ledger,
                          stream=io.StringIO(), **kwargs)

    def finish(self, indexed, *, root=None, ledger=None, page_bytes=16384, publish_record=False):
        pages, total, response = [], 0, indexed
        while True:
            response = r.read_page(snapshot_id=indexed['snapshot'] if not pages else None,
                cursor=response['cursor'] if pages else None, root=root or self.root,
                ledger=ledger or self.ledger, stream=io.StringIO(), page_bytes=page_bytes,
                publish_record=publish_record)
            pages.append(response)
            for item in response['body']:
                meta = item['metadata']; raw = item['text'].encode('utf-8')
                source = ((root or self.root) / meta['path']).read_bytes()
                self.assertEqual(source[meta['source_start'] + meta['start']:meta['source_start'] + meta['end']], raw)
                self.assertEqual(c.digest(source), meta['source_sha256'])
                total += len(raw)
            if response['reading'] is not None:
                break
            self.assertNotIn('issued', response)
            self.assertIsNotNone(response['actions']['continue'])
            self.assertLess(len(pages), 100)
        return response, pages, total

    def test_operation_destinations_and_source_owners_are_independent(self):
        for source_kind in r.execution_routes.SOURCE_KINDS:
            for scope in ('studio-slot', 'sheet', 'catalog'):
                with self.subTest(scope=scope, source_kind=source_kind):
                    record, bodies = r.capture('adoption', operation='adopt', execution='dispatcher',
                        scope=scope, source_kind=source_kind, root=self.root)
                    self.assertEqual((record['scope'], record['source_kind']), (scope, source_kind))
                    text = b''.join(raw for _, raw in bodies)
                    self.assertNotIn(b'## Withdrawal', text)
                    self.assertEqual(b'## Catalog' in text, scope == 'catalog')
                    self.assertEqual(b'## Imported' in text, scope != 'studio-slot' and source_kind == 'imported-iteration')
        with self.assertRaisesRegex(ValueError, '--scope.*--source-kind'):
            r.capture('adoption', execution='dispatcher', root=self.root)
        with self.assertRaisesRegex(ValueError, 'withdraw reading uses --scope sheet'):
            r.capture('adoption', operation='withdraw', execution='dispatcher', scope='catalog',
                      source_kind='production-candidate', root=self.root)
        record, bodies = r.capture('adoption', operation='withdraw', execution='dispatcher', scope='sheet',
                                  source_kind='production-candidate', root=self.root)
        self.assertIn(b'## Withdrawal', b''.join(raw for _, raw in bodies))
        self.assertEqual(record['operation'], 'withdraw')

    def test_complete_selected_ranges_issue_only_after_every_required_byte(self):
        indexed = self.start(navigation=True)
        self.assertIsNone(indexed['reading'])
        self.assertFalse(self.ledger.exists())
        for source in indexed['index']:
            self.assertTrue(source['sections'])
            for section in source['sections']:
                self.assertTrue(section['selection_reason_ids'])
                self.assertTrue(all(key in indexed['selection_reasons'] for key in section['selection_reason_ids']))
                self.assertGreater(section['source_end'], section['source_start'])
        result, pages, total = self.finish(indexed, page_bytes=13, publish_record=True)
        self.assertGreater(len(pages), 1)
        record = c.load(Path(result['reading']['record_absolute']))
        self.assertEqual((record['scope'], record['source_kind']), ('studio-slot', 'production-candidate'))
        document = record['documents'][0]
        self.assertEqual(document['sha256'], c.digest(self.raw))
        self.assertEqual(document['size'], len(self.raw))
        self.assertEqual(total, sum(item['end'] - item['start'] for item in document['ranges']))
        for selected in document['ranges']:
            self.assertEqual(selected['sha256'], c.digest(self.raw[selected['start']:selected['end']]))
        r.require_route_reading(record, root=self.root, ledgers=[self.ledger], scope='studio-slot',
                              source_kind='production-candidate')
        changed = copy.deepcopy(record)
        changed['documents'][0]['ranges'] = changed['documents'][0]['ranges'][:1]
        with self.assertRaisesRegex(ValueError, 'issuance differs'):
            r.require_route_reading(changed, root=self.root, ledgers=[self.ledger])
        row = copy.deepcopy(result['issued']['row'])
        row['delivery']['bodies'].pop()
        with self.assertRaisesRegex(ValueError, 'does not cover'):
            r._validate_delivery(row)

    def test_known_whole_source_covers_selected_sections_with_original_witness(self):
        whole = r.issue('development', execution='dispatcher', root=self.root, ledger=self.ledger, stream=io.StringIO())
        indexed = self.start(scope='sheet', navigation=True, known_reading_keys=[whole['reading_key']])
        self.assertIsNone(indexed['reading'])
        self.assertEqual(indexed['progress']['remaining_bytes'], 0)
        result, pages, delivered = self.finish(indexed)
        self.assertEqual(delivered, 0)
        for part in result['issued']['row']['delivery']['bodies']:
            self.assertEqual(part['origin']['key_sha256'], whole['row']['key_sha256'])
            self.assertEqual(part['source_body']['source_start'], 0)
            self.assertEqual(part['source_body']['source_end'], len(self.raw))
            self.assertGreater(part['body']['source_start'], 0)
        r.require_route_reading(r.draft_record(whole), root=self.root, ledgers=[self.ledger],
                              operation='adopt', scope='sheet', source_kind='production-candidate')

    def test_scope_expansion_delivers_only_missing_ranges_and_never_a_gap(self):
        slot = self.start()
        slot_record = r.draft_record(slot['issued'])
        with self.assertRaises(r.ReadingSourcesChanged) as missing:
            r.require_route_reading(slot_record, root=self.root, ledgers=[self.ledger],
                                  scope='sheet', source_kind='production-candidate')
        self.assertEqual(missing.exception.changes[0]['change'], 'scope-expanded')
        self.assertTrue(missing.exception.changes[0]['missing_ranges'])
        sheet = self.start(scope='sheet', known_reading_keys=[slot['reading']['key']])
        self.assertEqual(len(sheet['body']), 1)
        self.assertTrue(sheet['body'][0]['text'].startswith('## Sheet'))
        catalog = self.start(scope='catalog', known_reading_keys=[slot['reading']['key'], sheet['reading']['key']])
        self.assertEqual(len(catalog['body']), 1)
        self.assertTrue(catalog['body'][0]['text'].startswith('## Catalog'))
        # A broader whole-source requirement reuses all complete known intervals,
        # while the opening, imported contract and withdrawal remain unread gaps.
        indexed = r.read_page(route='development', execution='dispatcher', navigation=True,
            root=self.root, ledger=self.ledger, stream=io.StringIO(),
            known_reading_keys=[slot['reading']['key'], sheet['reading']['key'], catalog['reading']['key']])
        self.assertGreater(indexed['progress']['reused_bytes'], 0)
        self.assertGreater(indexed['progress']['remaining_bytes'], 0)
        result, pages, total = self.finish(indexed, page_bytes=17)
        text = ''.join(item['text'] for page in pages for item in page['body'])
        self.assertIn('# Contract', text)
        self.assertIn('## Imported', text)
        self.assertIn('## Withdrawal', text)
        self.assertNotIn('## Common', text)
        self.assertNotIn('## Slot', text)
        self.assertEqual(total + result['progress']['reused_bytes'], len(self.raw))
        self.assertEqual(result['context_reuse']['curation_scopes'], [])
        self.assertIn('reading_action', result['context_reuse']['curation_guidance'])
        r.require_route_reading(r.draft_record(result['issued']), root=self.root, ledgers=[self.ledger])

    def test_fresh_context_rereads_selected_ranges_and_changed_source_is_not_known(self):
        first = self.start(scope='sheet')
        indexed = self.start(scope='sheet', navigation=True)
        self.assertEqual(indexed['progress']['reused_bytes'], 0)
        self.assertEqual(indexed['remaining_bytes'], first['progress']['required_bytes'])
        fresh, pages, total = self.finish(indexed)
        self.assertEqual(total, first['progress']['required_bytes'])
        # Even an edit outside the selected ranges changes the complete source edition.
        (self.root / self.document).write_bytes(self.raw + b'Changed retained source edition.\n')
        changed = self.start(scope='sheet', known_reading_keys=[fresh['reading']['key']])
        self.assertEqual(changed['progress']['reused_bytes'], 0)
        self.assertEqual(changed['progress']['delivered_bytes'], changed['progress']['required_bytes'])
        partial = self.start(scope='sheet', page_bytes=11)
        (self.root / self.document).write_bytes(self.raw)
        before = self.ledger.read_bytes()
        with self.assertRaises(r.ReadingSourcesChanged):
            r.read_page(cursor=partial['cursor'], root=self.root, ledger=self.ledger,
                        stream=io.StringIO(), page_bytes=10000)
        self.assertEqual(self.ledger.read_bytes(), before)

    def test_actual_curation_contracts_exclude_other_procedures_and_keep_recovery(self):
        expected = {
            'studio-slot': {'select-a-reviewed-result-and-finish', 'acceptance-completion-and-recovery',
                           'accept-an-existing-candidate-for-its-studio-slot', 'studio-slot-selection-authority'},
            'sheet': {'adopt-the-selected-image-as-a-reusable-reference', 'canonical-adoption-authority',
                      'reuse-stop-judgments-for-the-same-selected-image', 'resume-a-retained-canonical-adoption',
                      'recover-the-recorded-adoption-evidence', 'canonical-image-scope'},
            'catalog': {'register-the-selected-candidate-in-the-catalog', 'catalog-publication-and-reuse',
                        'catalog-registration-recovery'},
        }
        for scope, needed in expected.items():
            resolved = r.execution_routes.resolve('adoption', execution='dispatcher', scope=scope,
                                                 source_kind='production-candidate')
            anchors = {part['anchor'] for values in resolved['section_owners'].values() for part in values}
            self.assertTrue(needed <= anchors, (scope, needed - anchors))
            self.assertFalse({'service-authentication', 'display-publication-ownership',
                'story-timeline-projection', 'input-and-scope', 'register-an-imported-catalog-reference',
                'withdraw-current-canonical-reuse'} & anchors)
            if scope == 'studio-slot':
                self.assertNotIn('author-one-canonical-adoption-decision', anchors)
                self.assertNotIn('canonical-image-scope', anchors)
            if scope == 'sheet':
                self.assertNotIn('register-the-selected-candidate-in-the-catalog', anchors)
                self.assertNotIn('catalog-publication-and-reuse', anchors)
        imported = r.execution_routes.resolve('adoption', execution='external', scope='sheet', source_kind='imported-iteration')
        anchors = {part['anchor'] for values in imported['section_owners'].values() for part in values}
        self.assertIn('input-and-scope', anchors)
        self.assertIn('record-a-missing-generation-package', anchors)
        self.assertNotIn('author-one-canonical-adoption-decision', anchors)

    def test_actual_fresh_contract_pages_and_explicit_scope_transition(self):
        ledgers = {}
        readings = {}
        measured = {}
        for scope in ('studio-slot', 'sheet', 'catalog'):
            ledger = self.root / scope / 'reads.jsonl'; ledgers[scope] = ledger
            indexed = r.read_page(route='adoption', operation='adopt', execution='dispatcher', scope=scope,
                source_kind='production-candidate', root=r.ROOT, ledger=ledger, stream=io.StringIO(), navigation=True)
            result, pages, delivered = self.finish(indexed, root=r.ROOT, ledger=ledger, publish_record=True)
            measured[scope] = {'bytes': delivered, 'pages': len(pages)}
            self.assertLess(delivered, 112905 // 2)
            self.assertLessEqual(len(pages), 3)
            readings[scope] = result
            r.require_route_reading(c.load(Path(result['reading']['record_absolute'])), ledgers=[ledger],
                                  scope=scope, source_kind='production-candidate')
        slot = readings['studio-slot']
        self.assertEqual(set(slot['context_reuse']['operations']), {'adopt'})
        self.assertTrue(all(item['source_kind'] == 'production-candidate'
                            for item in slot['context_reuse']['curation_scopes']))
        self.assertFalse(any(item['operation'] == 'adopt' and item['scope'] == 'studio-slot'
                             for item in slot['context_reuse']['curation_scopes']))
        action = next(item['action'] for item in slot['context_reuse']['curation_scopes']
                      if item['operation'] == 'adopt' and item['scope'] == 'sheet'
                      and item['source_kind'] == 'production-candidate')
        self.assertIn('--known-reading', action['argv'])
        self.assertEqual(action['argv'][action['argv'].index('--scope') + 1], 'sheet')
        indexed = r.read_page(route='adoption', operation='adopt', execution='dispatcher', scope='sheet',
            source_kind='production-candidate', root=r.ROOT, ledger=ledgers['studio-slot'], stream=io.StringIO(),
            known_reading_keys=[slot['reading']['key']], navigation=True)
        self.assertGreater(indexed['progress']['reused_bytes'], 0)
        self.assertGreater(indexed['remaining_bytes'], 0)
        result, pages, delivered = self.finish(indexed, root=r.ROOT, ledger=ledgers['studio-slot'])
        self.assertLess(delivered, measured['sheet']['bytes'])
        self.assertEqual(delivered + result['progress']['reused_bytes'], measured['sheet']['bytes'])

    def test_public_draft_read_action_and_fresh_restart_preserve_both_axes(self):
        import argparse
        import contextlib
        import studio_workspace
        studio_root = self.root / 'studio'
        studio_workspace.init(studio_root, 'scoped-reading', 'Synthetic scoped reading')
        action = r.curation_action(studio_root, execution='dispatcher', scope='sheet')
        self.assertNotIn('--known-reading', action['argv'])
        self.assertEqual(action['argv'][action['argv'].index('--source-kind') + 1], 'production-candidate')
        def command(words):
            parser = argparse.ArgumentParser(); r.add_read_arguments(parser)
            args = parser.parse_args(words)
            with contextlib.redirect_stdout(io.StringIO()), patch.object(r, '_configure_runtime', return_value=None):
                return r.read_command(args, parser)
        indexed = command(action['argv'][3:])
        self.assertEqual((indexed['metadata']['scope'], indexed['metadata']['source_kind']), ('sheet', 'production-candidate'))
        first = command(indexed['actions']['all']['argv'][3:])
        fresh = command(first['actions']['restart']['argv'][3:])
        self.assertEqual((fresh['metadata']['scope'], fresh['metadata']['source_kind']), ('sheet', 'production-candidate'))
        self.assertEqual(fresh['progress']['reused_bytes'], 0)
        self.assertEqual(fresh['progress']['remaining_bytes'], fresh['progress']['required_bytes'])
        self.assertIsNone(fresh['reading'])

    def test_interrupted_snapshot_reconstruction_keeps_scope_and_source_kind(self):
        import production_authoring_state
        import studio_workspace
        import work_ledger
        studio_root = self.root / 'studio'
        studio_workspace.init(studio_root, 'scoped-recovery', 'Synthetic scoped recovery')
        work_ledger.begin(studio_root, 'Choose the retained image.', ['Read and decide'])
        before = (studio_root / 'work/current.json').read_bytes()
        indexed = r.read_page(route='adoption', operation='adopt', execution='dispatcher', scope='sheet',
            source_kind='production-candidate', root=self.root, studio=studio_root, ledger=self.ledger,
            stream=io.StringIO(), navigation=True)
        snapshot = self.ledger.parent / 'reading-snapshots' / indexed['snapshot'] / 'snapshot.json'
        snapshot.unlink()
        state = production_authoring_state.inspect(studio_root)
        row = next(item for item in state['readings'] if item['current'])
        action = row['next_actions'][0]['argv']
        self.assertEqual(action[action.index('--scope') + 1], 'sheet')
        self.assertEqual(action[action.index('--source-kind') + 1], 'production-candidate')
        self.assertNotIn('--known-reading', action)
        self.assertEqual((studio_root / 'work/current.json').read_bytes(), before)


if __name__=='__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main(verbosity=2)
