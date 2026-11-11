"""A dispatcher run that uses a pack-owned reference asset binds it, previews and executes."""
from __future__ import annotations

import argparse
import contextlib
import io
from pathlib import Path
import tempfile
import unittest

import dispatch
import execution_contract as c
import pack_manager as packs
import production_case_fixtures as fixtures
import production_execution as execution
import production_fixtures
import production_inputs
import production_reference_inputs as reference_inputs
import production_store as store
import production_workflow as workflow
import runtime_snapshot
from catalog_retrieval import runtime
from reference_runtime import build_reference_use_plan, execute_reference_use_plan
from reference_runtime_smoke_test import DIRECT_RASTER_RECORD_ID, FIXTURE_PACK_ID, _write_fixture_pack
from test_production_execution import decisions


class PackReferenceRunTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='cpb-pack-reference-')
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name)
        self.enterContext(production_fixtures.scratch_home(base / 'home'))
        self.addCleanup(runtime.configure_pack_runtime, None)
        self.case = fixtures.create(base / 'studio', base / 'runtime', with_alternate=True)
        self.root = self.case['root']
        settings = self.case['settings']
        asset_pack = _write_fixture_pack(base / 'runtime')
        state = packs.load_state(settings.state_file)
        state.update(pack_roots=[*state.get('pack_roots', []), str(asset_pack)],
                     enabled_packs=[*state['enabled_packs'], FIXTURE_PACK_ID],
                     pack_order=[*state['pack_order'], FIXTURE_PACK_ID])
        packs.save_state(settings.state_file, state)
        runtime.configure_pack_runtime(settings)
        parent = fixtures.reference_retarget_case(self.case)['parent']['run']
        plan = build_reference_use_plan(
            [{'record_id': DIRECT_RASTER_RECORD_ID, 'intended_influence': 'pose-camera',
              'subject_uses': [{'subject_id': 'robot', 'use': 'pose-camera', 'priority': 0}]}],
            transport_mode='multi-image', source_lighting_mode='replace', target_model=fixtures.MODEL_ID,
            include_technical_roles=['subject-mask'],
            light_sources=[{'light_id': 'key', 'direction': 'upper left', 'apparent_size': 'large',
                            'color': 'neutral', 'relative_intensity': 'primary', 'softness': 'soft'}],
            material_responses=[{'material': 'matte sample', 'roughness': 'matte', 'specular_strength': 'low',
                                 'highlight_shape': 'broad', 'wetness': 'dry', 'anisotropy': 'none'}])
        delivered = execute_reference_use_plan(plan, output_dir=self.root / 'pack-source')
        draft = production_inputs.draft_inputs(self.root, None, 'pack-reference', from_run=parent)
        choices = draft['choices']
        choices['authoring']['references']['reference_use_plan'] = reference_inputs.draft(
            delivered, package_root=self.root / 'pack-source')['reference_use_plan']
        fixtures.write(self.root / draft['choices_file'], choices)
        self.prepared_run = workflow.prepare(self.root, choices=draft['choices_file'])['run']

    def test_run_binds_the_reference_records_and_artifact_it_used(self):
        loaded = workflow.read_run(self.root, self.prepared_run)
        plan = loaded.artifacts['package.json']['prepared_reference_set']['reference_use_plan']
        item = plan['reference_items'][0]
        self.assertEqual(item['source']['kind'], 'pack-artifact')
        used = {item['canonical_record_id'], item['asset_id']}
        descriptor = loaded.prepared['runtime_snapshot']
        binding = descriptor['binding']
        self.assertEqual({row['id'] for row in binding['records'] if row['role'] == 'reference'}, used)
        artifact = [row for row in binding['evidence'] if row['sha256'] == item['source']['sha256']]
        self.assertEqual([row['pack'] for row in artifact], [FIXTURE_PACK_ID])
        fixed = runtime_snapshot.acquire_runtime(runtime_snapshot.path(self.root, descriptor), descriptor)
        self.assertEqual(c.digest(fixed.read_pack(FIXTURE_PACK_ID, artifact[0]['path'])), item['source']['sha256'])
        self.assertLessEqual(used, {entry['record']['id'] for entry in fixed.payload['entries']})

    def test_prepared_run_previews_without_effect_and_executes(self):
        saved = execution.compiled(self.root, self.prepared_run)
        options = argparse.Namespace(package=saved[0] / 'package.json', character='robot', slot='candidate',
                                     pack_settings=self.case['settings'], preview_out=None)
        before = store.event_rows(self.root, self.prepared_run)
        shown = io.StringIO()
        with contextlib.redirect_stdout(shown):
            self.assertEqual(dispatch.dispatch_generation(options, self.root), 0)
        self.assertIn('shown, not sent', shown.getvalue())
        self.assertEqual(store.event_rows(self.root, self.prepared_run), before)
        result = execution.execute(self.root, self.prepared_run,
                                   decisions_file=decisions(self.root, self.prepared_run))
        self.assertTrue(result['execution_completed'])
        self.assertEqual(len(result['runs'][0]['candidates']), 1)


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
