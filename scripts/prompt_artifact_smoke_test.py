#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from prompt_plot import content_sha256
from prompt_retrieval import settle_retrieval_record
from model_prompt_input_fixtures import prompt_input

NL = chr(10)

INVALID_SEMANTIC_PLAN = {
    "structure_plan": {
        "expected_counts": {"arm": 2},
        "assigned_structures": [
            {"structure_id": "left-arm", "kind": "arm", "side": "left", "owner_id": "C01"},
            {"structure_id": "left-arm-copy", "kind": "arm", "side": "left", "owner_id": "C01"},
            {"structure_id": "right-arm", "kind": "arm", "side": "right", "owner_id": "C01"},
        ],
        "primary_actions": [],
    },
    "camera": {
        "angle": "worms-eye", "shot_scale": "wide", "distance": "distant",
        "camera_height": "eye", "pitch": "level", "subject_frame_occupancy": 0.2,
    },
}

BOUNDED_CAMERA_PLAN = {
    "structure_plan": {"expected_counts": {}, "assigned_structures": [], "primary_actions": []},
    "camera": {
        "angle": "worms-eye", "shot_scale": "wide", "distance": "distant",
        "camera_height": "ground", "pitch": "upward", "subject_frame_occupancy": 0.25,
        "subject_frame_occupancy_bounds": {"minimum": 0.2, "maximum": 0.3},
        "establishing_context": True,
    },
}

RETRIEVAL_RECORD = {
    "artifact_type": "prompt-retrieval-record",
    "elements": [
        {
            "element": "pose",
            "queries": ["standing arms at sides"],
            "inspected_records": ["MOD-POSE-EXAMPLE"],
            "outcome": "adopted",
            "adopted_records": ["MOD-POSE-EXAMPLE"],
        },
        {
            "element": "camera",
            "queries": ["knee up front view"],
            "inspected_records": [],
            "outcome": "composed",
            "composed_wording": "a knee-up view from the front",
            "reason": "no retrieved record covers this framing",
        },
    ],
}

PLOT = {
    "artifact_type": "prompt-plot",
    "story": [
        {"id": "s1", "beat": "The subject stands still for a reference photograph.", "visibility": "visible"},
        {"id": "s2", "beat": "The room beyond the backdrop is a working studio.", "visibility": "context"},
    ],
    "derived": [
        {"kind": "shows", "statement": "the subject and a plain backdrop", "from": ["s1"]},
        {"kind": "placement", "statement": "the subject stands centred, facing the camera", "from": ["s1"]},
        {"kind": "composition", "statement": "a knee-up view at eye height", "from": ["s1"]},
        {"kind": "must_preserve", "statement": "the subject own proportions", "from": ["s1"]},
        {"kind": "free", "statement": "the backdrop exact tone"},
    ],
}

APPROVED_PLOT = {**PLOT, "approved": {
    "by": "the person who owns the brief",
    "at": "2026-09-11T00:00:00Z",
    "content_sha256": content_sha256(PLOT),
}}


import execution_contract as c
from authoring_work_fixtures import prompt_work
from build_prompt_artifacts import publish


class PromptArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='cpb-prompt-work-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.model = {'id': 'synthetic-prompt-editor', 'prompt_input': prompt_input('descriptive')}
        self.prompt = 'An articulated robot steadies a bowl while another repairs its rim.\n'
        self.content = {'prompt': self.prompt}
        self.serial = 0

    def work_file(self, content=None, *, work=None):
        self.serial += 1
        path = self.root / ('work-' + str(self.serial) + '.json')
        path.write_bytes(c.encoded(work if work is not None else prompt_work(content or self.content)))
        return path

    def export(self, content=None, *, work=None, name=None, **options):
        path = self.work_file(content, work=work)
        out = self.root / (name or ('output-' + str(self.serial)))
        return out, publish(path, out, **options)

    def test_exact_candidate_text_and_acquired_work_are_published(self):
        work_path = self.work_file({'prompt': self.prompt, 'negative': ''})
        out = self.root / 'exact'
        manifest = publish(work_path, out)
        self.assertEqual((out / 'final-prompt.txt').read_bytes(), self.prompt.encode())
        self.assertEqual((out / 'final-negative.txt').read_bytes(), b'')
        self.assertEqual((out / 'authoring-work.json').read_bytes(), work_path.read_bytes())
        for row in manifest['included']:
            self.assertEqual(c.digest((out / row['path']).read_bytes()), row['sha256'])
        self.assertFalse(manifest['execution_authorized'])
        self.assertFalse(manifest['canonical_update_authorized'])
        self.assertIsNone(manifest['target'])
        self.assertEqual(manifest['input_validation'], {'state': 'unverified-draft', 'vocabulary_searched': False})

    def test_completed_character_prompt_uses_an_applied_definition(self):
        work = prompt_work(self.content)
        work['basis']['subjects'] = {}
        with self.assertRaises(ValueError):
            self.export(work=work)

    def test_explicit_supporting_setting_can_finish_without_subject_definition(self):
        from authoring_work import begin_work
        work = begin_work(operation='compose', request='Prepare only the empty repair workshop for this character project.',
                          focus='supporting-setting', content={'prompt': 'An empty repair workshop with a lit bench.'})
        out, _ = self.export(work=work)
        self.assertEqual((out / 'final-prompt.txt').read_text(encoding='utf-8'), work['content']['prompt'])

    def test_delivery_uses_the_actual_amended_candidate(self):
        from authoring_work import begin_work
        original = prompt_work({'prompt': self.prompt, 'negative': 'lettering'})
        basis = original['basis']
        work = begin_work(operation='amend', request='Have the second robot steady the bowl while the first repairs the rim.',
            sources=basis['sources'], applications=basis['applications'], subjects=basis['subjects'],
            requirements=basis['requirements'], baseline=original['content'])
        work['content']['prompt'] = 'The second robot steadies the bowl while the first repairs its rim.\n'
        out, manifest = self.export(work=work)
        self.assertEqual((out / 'final-prompt.txt').read_text(encoding='utf-8'), work['content']['prompt'])
        self.assertEqual((out / 'final-negative.txt').read_text(encoding='utf-8'), original['content']['negative'])
        self.assertEqual(manifest['authoring']['content_sha256'], c.content_id(work['content']))
        self.assertEqual(c.load(out / 'authoring-work.json')['basis']['baseline'], work['basis']['baseline'])

    def test_target_is_selected_in_the_work(self):
        out, manifest = self.export({'prompt': self.prompt, 'model_record': self.model}, generation=True)
        self.assertEqual(manifest['target']['id'], self.model['id'])
        self.assertEqual(c.load(out / 'model-input.json'), self.model)
        self.assertEqual(manifest['input_validation'], {'state': 'model-input-checked', 'vocabulary_searched': False})
        with self.assertRaisesRegex(ValueError, 'content.model'):
            self.export(generation=True)

    def test_unselected_retrieval_records_no_invented_search(self):
        for target in (None, self.model):
            content = dict(self.content)
            if target is not None:
                content['model_record'] = target
            out, manifest = self.export(content)
            self.assertEqual(manifest['retrieval'], {'settled': True, 'elements': 0, 'adopted': 0, 'composed': 0, 'unused': 0})
            self.assertFalse((out / 'prompt-retrieval-record.json').exists())

    def test_selected_retrieval_has_the_actual_prompt_and_plot_binding(self):
        record = settle_retrieval_record(RETRIEVAL_RECORD, prompt=self.prompt, plot=APPROVED_PLOT)
        content = {'prompt': self.prompt, 'model_record': self.model,
                   'documents': {'plot': APPROVED_PLOT, 'retrieval_record': record}}
        out, manifest = self.export(content, generation=True)
        self.assertEqual(c.load(out / 'prompt-retrieval-record.json'), record)
        self.assertEqual(c.load(out / 'prompt-plot.json'), APPROVED_PLOT)
        self.assertEqual(manifest['retrieval'], {'settled': True, 'elements': 2, 'adopted': 1, 'composed': 1, 'unused': 0})
        content['prompt'] += 'The repaired bowl sits on the table.'
        with self.assertRaisesRegex(ValueError, 'different prompt or plot'):
            self.export(content, generation=True)

    def test_empty_retrieval_remains_exactly_bound(self):
        record = settle_retrieval_record({'artifact_type': 'prompt-retrieval-record', 'elements': []},
                                        prompt=self.prompt, plot=APPROVED_PLOT)
        content = {'prompt': self.prompt, 'model_record': self.model,
                   'documents': {'plot': APPROVED_PLOT, 'retrieval_record': record}}
        self.export(content, generation=True)
        content['prompt'] += 'A distinct scene.'
        with self.assertRaisesRegex(ValueError, 'different prompt or plot'):
            self.export(content, generation=True)

    def test_pending_lookup_does_not_become_settled_through_publication(self):
        content = {'prompt': self.prompt, 'documents': {'retrieval_record': {
            'artifact_type': 'prompt-retrieval-record', 'elements': [{'element': 'support', 'queries': ['shared support']}]
        }}}
        with self.assertRaisesRegex(ValueError, 'retrieval record is invalid'):
            self.export(content)

    def test_unavailable_lookup_is_explicit_and_limits_preparation(self):
        content = {'prompt': self.prompt, 'model_record': self.model, 'retrieval_unavailable': 'Synthetic inaccessible dictionary.'}
        _, manifest = self.export(content)
        self.assertEqual(manifest['retrieval'], {'settled': False, 'reason': content['retrieval_unavailable']})
        with self.assertRaisesRegex(ValueError, 'retrieval was unavailable'):
            self.export(content, generation=True)
        content['documents'] = {'retrieval_record': {'artifact_type': 'prompt-retrieval-record', 'elements': []}}
        with self.assertRaisesRegex(ValueError, 'select a retrieval_record'):
            self.export(content)

    def test_plot_approval_and_story_links_reach_the_publication_gate(self):
        content = {'prompt': self.prompt, 'model_record': self.model, 'documents': {'plot': PLOT}}
        self.export(content)
        with self.assertRaisesRegex(ValueError, 'approved selected plot'):
            self.export(content, generation=True)
        content['documents']['plot'] = APPROVED_PLOT
        _, manifest = self.export(content, generation=True)
        self.assertTrue(manifest['plot']['approved'])
        for changed in (
            {**APPROVED_PLOT, 'target': 'another-interface'},
            {**PLOT, 'approved': {'by': 'fixture author', 'at': 'yesterday'}},
            {**PLOT, 'derived': [{'kind': 'shows', 'statement': 'an unrelated item', 'from': ['missing']}]},
        ):
            with self.subTest(changed=changed):
                content['documents']['plot'] = changed
                with self.assertRaises(ValueError):
                    self.export(content)

    def test_numeric_camera_and_structure_requirements_are_checked(self):
        content = {'prompt': self.prompt, 'documents': {'semantic_plan': BOUNDED_CAMERA_PLAN}}
        out, _ = self.export(content, require_semantics=True)
        self.assertTrue(c.load(out / 'semantic-preflight.json')['ok'])
        plan = copy.deepcopy(BOUNDED_CAMERA_PLAN)
        plan['camera']['subject_frame_occupancy'] = 0.4
        content['documents']['semantic_plan'] = plan
        with self.assertRaisesRegex(ValueError, 'outside declared bounds'):
            self.export(content)
        content['documents']['semantic_plan'] = INVALID_SEMANTIC_PLAN
        with self.assertRaisesRegex(ValueError, 'semantic preflight'):
            self.export(content)
        with self.assertRaisesRegex(ValueError, 'content.documents.semantic_plan'):
            self.export(require_semantics=True)

    def test_reference_count_and_transport_are_owned_by_selected_documents(self):
        plan = {'artifact_type': 'reference-use-plan', 'reference_items': [{'record_id': 'R1'}, {'record_id': 'R2'}]}
        content = {'prompt': self.prompt, 'documents': {'reference_use_plan': plan}}
        out, manifest = self.export(content)
        self.assertEqual(manifest['selected_reference_count'], 2)
        self.assertEqual(c.load(out / 'reference-use-plan.json'), plan)
        content['model_record'] = self.model
        with self.assertRaisesRegex(ValueError, 'prepared_reference_set'):
            self.export(content, generation=True)
        content['documents']['reference_use_plan'] = {'selected_references': []}
        with self.assertRaisesRegex(ValueError, 'reference use plan'):
            self.export(content)

    def test_failed_publication_keeps_existing_package_and_work(self):
        out, _ = self.export(name='existing')
        original = {path.name: path.read_bytes() for path in out.iterdir()}
        bad = self.work_file({'prompt': self.prompt, 'documents': {'semantic_plan': INVALID_SEMANTIC_PLAN}})
        with self.assertRaises(ValueError):
            publish(bad, out, overwrite=True)
        self.assertEqual({path.name: path.read_bytes() for path in out.iterdir()}, original)
        nested = out / 'my-work.json'
        nested.write_bytes(self.work_file().read_bytes())
        with self.assertRaisesRegex(ValueError, 'inside the output directory'):
            publish(nested, out, overwrite=True)
        self.assertTrue(nested.is_file())
        good = self.work_file({'prompt': self.prompt + 'A different actual candidate.'})
        with self.assertRaisesRegex(ValueError, 'not empty'):
            publish(good, out)
        publish(good, out, overwrite=True)
        self.assertEqual((out / 'final-prompt.txt').read_text(encoding='utf-8'), c.load(good)['content']['prompt'])

    def test_cli_publishes_the_chosen_work_without_separate_text_input(self):
        path = self.work_file()
        result = subprocess.run([sys.executable, str(Path(__file__).with_name('build_prompt_artifacts.py')),
            '--work', str(path), '--out-dir', str(self.root / 'cli')], text=True, encoding='utf-8', capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.root / 'cli/final-prompt.txt').read_text(encoding='utf-8'), self.prompt)

    def test_dictionary_selection_is_acquired_and_bound_to_actual_text(self):
        import production_case_fixtures as fixture
        import pack_manager as packs
        folder = self.root / 'tags'
        pack = fixture.create_pack(folder / 'pack')
        manifest = c.load(pack / 'pack.json')
        manifest['content']['resource_bindings'].update({
            'prompt-vocabulary': 'resources/dictionary.json', 'prompt-dialects': 'resources/dialects.json'})
        fixture.write(pack / 'pack.json', manifest)
        fixture.write(pack / 'resources/dictionary.json', {
            'format': 'character-prompt-builder-prompt-vocabulary', 'name': 'Synthetic artifact wording',
            'description': 'Fictional lookup terms for artifact input tests.',
            'categories': [{'id': 'synthetic', 'name': 'Synthetic terms', 'description': 'Authored fixture terms.',
                'entries': [{'term': term} for term in ('blue triangle', 'plain backdrop', 'lettering')]}]})
        fixture.write(pack / 'resources/dialects.json', {
            'format': 'character-prompt-builder-prompt-dialects', 'name': 'Synthetic artifact dialect',
            'description': 'Fictional tag input contract, not a model claim.',
            'dialects': [{'id': 'synthetic-tags', 'name': 'Synthetic tags', 'description': 'Test-only family.',
                'vocabularies': ['synthetic'], 'tag_separator': ', ', 'block_order': ['subject', 'environment']}]})
        models = c.load(pack / 'records/models.json')
        model = models['records'][0]
        model.update(prompt_input=prompt_input('tag-based', vocabularies=('synthetic',)), prompt_dialect='synthetic-tags')
        fixture.write(pack / 'records/models.json', models)
        packs.write_lock(pack)
        packs.save_state(folder / 'state.json', {'pack_roots': [], 'enabled_packs': [fixture.PACK_ID]})
        runtime_args = ['--state-file', str(folder / 'state.json'), '--cache-dir', str(folder / 'cache'),
                        '--managed-root', str(folder / 'managed'), '--pack-root', str(pack)]
        model_record = {key: model[key] for key in ('id', 'prompt_input', 'prompt_dialect')}
        files = {name: folder / (name + '.json') for name in ('model', 'retrieval', 'plot')}
        files.update(prompt=folder / 'prompt.txt', negative=folder / 'negative.txt')
        fixture.write(files['model'], model_record)
        fixture.write(files['prompt'], 'blue triangle, (plain backdrop:1.2)')
        fixture.write(files['negative'], '(lettering:1.1)')
        fixture.write(files['retrieval'], {'artifact_type': 'prompt-retrieval-record', 'elements': []})
        fixture.write(files['plot'], APPROVED_PLOT)
        script = Path(__file__).with_name('build_prompt_artifacts.py')
        content = {'prompt': files['prompt'].read_text(encoding='utf-8'), 'negative': files['negative'].read_text(encoding='utf-8'),
                   'weighting': 'sdEmbeds', 'model_record': model_record,
                   'documents': {'plot': APPROVED_PLOT}}
        def export_cli(name, *, generation=False):
            path = self.work_file(content)
            return subprocess.run([sys.executable, str(script), '--work', str(path),
                '--out-dir', str(folder / name), *(['--prepare-for-generation'] if generation else []), *runtime_args],
                capture_output=True, text=True, encoding='utf-8')
        blocked = export_cli('unsearched')
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn('searched vocabulary selection', blocked.stdout + blocked.stderr)
        for command in ('--search-vocabulary', '--settle'):
            result = subprocess.run([sys.executable, str(script.with_name('prompt_retrieval.py')),
                str(files['retrieval']), command, '--model-file', str(files['model']),
                '--prompt-file', str(files['prompt']), '--negative-file', str(files['negative']),
                '--weighting', 'sdEmbeds',
                *(['--plot-file', str(files['plot']), '--out', str(files['retrieval'])] if command == '--settle' else []),
                *runtime_args],
                capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        content['documents']['retrieval_record'] = c.load(files['retrieval'])
        result = export_cli('searched')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(json.loads(result.stdout)['manifest']['input_validation']['vocabulary_searched'])
        content.pop('model_record')
        content['model'] = fixture.MODEL_ID
        result = export_cli('catalog', generation=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        content['negative'] = '(lettering:1.3)'
        changed = export_cli('changed-negative')
        self.assertNotEqual(changed.returncode, 0)
        self.assertIn('different text', changed.stdout + changed.stderr)


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main(verbosity=2)
