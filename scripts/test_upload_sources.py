#!/usr/bin/env python3
"""Bind current upload inputs to prepared carriers before any external effect."""
from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

import execution_contract as c
import production_inputs
from production_diagnostics import ProductionError
import request_contract as rc
from state_protocol import validate_against_schema


class UploadSourceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.media = []
        for name, role, bindings in [('board', 'reference', ['reference:1', 'reference:2']),
                                     ('mask', 'mask', [])]:
            path = self.root / (name + '.png')
            Image.new('RGB', (4, 3), 'white').save(path)
            self.media.append(rc.media_metadata(path, role=role, binding_ids=bindings))

    def sources(self):
        return [{'index': 1, 'url': 'https://files.example/mask.png?version=2'},
                {'index': 0, 'url': 'https://files.example/board.png?version=4'}]

    def seal(self, media):
        request = {'model': 'synthetic-model', 'operation': 'generate', 'prompt': 'Clear arrangement.',
                   'count': 1, 'images': [rc.MANAGEMENT_VALUE] * len(media)}
        layout = {
            'model': ['model'], 'operation': ['operation'], 'primary_text': ['prompt'],
            'negative_text': None, 'output_count': ['count'], 'fixed_output_count': None,
            'seed': None, 'media': [{'index': i, 'field': ['images', i]} for i in range(len(media))],
            'management': [], 'content': [{'id': 'prompt', 'field': ['prompt']}],
            'fields': [{'id': 'prompt', 'field': ['prompt'], 'kind': 'content'}],
        }
        target = {'service': 'synthetic-service', 'model_identifier': 'synthetic-model',
                  'operation': 'generate'}
        return rc.seal(request, layout, media, target, {}, [], context={'output_kind': 'image'})

    def test_urls_bind_actual_board_and_mask_without_network(self):
        before = copy.deepcopy(self.media)
        with patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('unexpected network')):
            bound = rc.bind_upload_sources(self.media, self.sources(), 'url')
            sealed = self.seal(bound)
        self.assertEqual(bound[0]['upload_source']['url'], self.sources()[1]['url'])
        self.assertEqual(bound[1]['upload_source']['url'], self.sources()[0]['url'])
        self.assertEqual(bound[0]['binding_ids'], ['reference:1', 'reference:2'])
        self.assertEqual(self.media, before)
        self.assertEqual(sealed['sealed']['media'][0]['sha256'], c.sha256_file(self.root / 'board.png'))
        self.assertNotIn('path', sealed['sealed']['media'][0])

    def test_each_missing_carrier_is_actionable_in_one_diagnostic(self):
        with self.assertRaises(ProductionError) as caught:
            rc.bind_upload_sources(self.media, [], 'url')
        diagnostic = caught.exception.diagnostic.as_dict()
        self.assertEqual(diagnostic['code'], 'UPLOAD_SOURCE_REQUIRED')
        self.assertEqual(diagnostic['pointer'], '$.upload_sources')
        self.assertEqual(diagnostic['carriers'], [
            {'index': 0, 'path': str(self.root / 'board.png'), 'role': 'reference'},
            {'index': 1, 'path': str(self.root / 'mask.png'), 'role': 'mask'},
        ])

    def test_duplicate_and_absent_carriers_are_rejected_before_sealing(self):
        cases = [self.sources() + [self.sources()[0]],
                 [{'index': 2, 'url': 'https://files.example/unused.png'}],
                 [{'index': True, 'url': 'https://files.example/unused.png'}]]
        for selected in cases:
            with self.subTest(selected=selected), self.assertRaises(ProductionError):
                rc.bind_upload_sources(self.media, selected, 'url')

    def test_local_byte_transport_has_no_remote_input(self):
        bound = rc.bind_upload_sources(self.media, [], 'bytes')
        self.assertEqual([row['upload_source'] for row in bound], [{'kind': 'bytes'}, {'kind': 'bytes'}])
        with self.assertRaises(ProductionError):
            rc.bind_upload_sources(self.media, self.sources(), 'bytes')
        self.assertEqual(rc.bind_upload_sources([], [], 'url'), [])

    def test_source_url_change_changes_the_authorized_request(self):
        first = self.seal(rc.bind_upload_sources(self.media, self.sources(), 'url'))
        selections = self.sources()
        selections[0]['url'] = 'https://files.example/mask.png?version=3'
        second = self.seal(rc.bind_upload_sources(self.media, selections, 'url'))
        self.assertNotEqual(first['request_sha256'], second['request_sha256'])
        self.assertEqual(first['media'][1]['sha256'], second['media'][1]['sha256'])
        self.assertEqual(first['profile'], second['profile'])
        self.assertEqual(first['profile']['media'][1]['upload_source'], {'kind': 'url'})
        first['media'][1]['upload_source']['url'] = selections[0]['url']
        with self.assertRaises(ValueError):
            rc.validate_seal(first)

    def test_only_actual_upload_results_enter_the_generation_fields(self):
        sealed = self.seal(rc.bind_upload_sources(self.media, self.sources(), 'url'))
        ids = {0: 'provider-board-uuid', 1: 'provider-mask-uuid'}
        wire = rc.materialize(sealed, ids)
        self.assertEqual(wire['images'], list(ids.values()))
        self.assertEqual(wire['prompt'], sealed['request']['prompt'])
        rc.validate_wire(sealed, wire, ids)

    def test_source_urls_cannot_embed_credentials_or_fragments(self):
        invalid = ['file:///tmp/image.png', 'http://files.example/image.png',
                   'https://name:secret@files.example/image.png', 'https://@files.example/image.png',
                   'https://files.example/image.png#panel', 'https://files.example/image.png#',
                   'https://files.example/image name.png', 'https://files.example:invalid/image.png']
        for url in invalid:
            with self.subTest(url=url), self.assertRaises(ValueError):
                rc.validate_upload_source({'kind': 'url', 'url': url})
        rc.validate_upload_source({'kind': 'url', 'url': 'http://127.0.0.1:8080/image.png'})

    def test_input_choices_keep_authority_and_derive_hashes_from_files(self):
        task = {'task_id': 'synthetic-task', 'authority': 'authority.json', 'execution': 'dispatcher'}
        choices = {'reading': None, 'visual': None, 'validation': None,
                   'task_changes': {'upload_sources': self.sources()}, 'external': None}
        production_inputs.read_choices(choices)
        changed = production_inputs._chosen_task(task, choices)
        self.assertEqual(changed['upload_sources'], self.sources())
        self.assertEqual(changed['task_id'], task['task_id'])
        self.assertEqual(changed['authority'], task['authority'])
        self.assertNotIn('upload_sources', task)
        schema = c.load(production_inputs.ROOT / 'schemas/authoring/production-task.schema.json')
        self.assertEqual(validate_against_schema(changed['upload_sources'], schema['properties']['upload_sources']), [])
        malformed = copy.deepcopy(choices)
        malformed['task_changes']['upload_sources'][0]['index'] = -1
        with self.assertRaises(ValueError):
            production_inputs.read_choices(malformed)


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
