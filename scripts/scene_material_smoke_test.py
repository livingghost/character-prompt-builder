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
    (root / 'persona.md').write_text(original, encoding='utf-8', newline='\n')
    (root / 'scene.md').write_text('A bounded authored activity. No turn or conflict is required.\n', encoding='utf-8', newline='\n')
    subjects = [] if empty else [{'subject_id':'A','model':'functional' if functional else 'persona',
                                'source_ids':['P'],'portrayal_basis':'Use the declared model, not a presumed human psychology.'}]
    source_specs = [{'source_id':'S','path':'scene.md','role':'scene','subject_ids':[],
                     'sha256':m.digest((root/'scene.md').read_bytes()), 'reading_basis':'Constructed test: complete scene input read.'}]
    if not empty:
        source_specs.append({'source_id':'P','path':'persona.md','role':'functional' if functional else 'persona',
                             'subject_ids':['A'],'sha256':m.digest((root/'persona.md').read_bytes()),
                             'reading_basis':'Constructed test: complete applicable model read, including the unquoted context.'})
    plan = {'material_id':'M','scene_id':'S','scene_source_id':'S','medium':'text','purpose':'Render the stated activity without inventing an obligatory arc.',
            'conditions':['Only the declared participants and information are in scope.'], 'subjects':subjects,
            'sources':source_specs,'excerpts':[] if empty else [
                {'excerpt_id':'core','source_id':'P','anchor':'Portrayal','subject_ids':['A'],'depends_on':[],
                 'reason':'Preserve the controlling portrayal pattern.'},
                {'excerpt_id':'expression','source_id':'P','anchor':'Expression','subject_ids':['A'],'depends_on':['core'],
                 'reason':'Expression depends on the controlling portrayal pattern.'}],
            'applications':[] if empty else [{'application_id':'apply','subject_ids':['A'],'definition_ids':['expression','core'],
                'kind':'interpretation','text':'Choose the response under these definitions; a pause need not signal distress.'}],
            'interactions':[], 'constraints':['No automatic canonical change.'], 'unknowns':[],
            'reopen_when':['A new topic, participant, source change, or portrayal aim changes applicability.'],
            'review':{'by':'fixture-author','decision':'ready','basis':'Constructed reading/application test, not an empirical agent run.','limitations':[],'revisions':[]},
            'supersedes':None}
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


ROOT = Path(__file__).resolve().parents[1]


def form_persona(title: str, *, speech: str = 'plain first person, short sentences', core: bool = True,
                 appearance: str = 'tall, ink on both cuffs') -> str:
    """A persona in the installed form's shape, cut to the headings a scene reads."""
    answer = (lambda text: ' ' + text) if core else (lambda text: '')
    return (f'---\nkind: persona\nid: x\n---\n# {title}\n\n'
            '## 1. TIMELINE\n\n### Epistemic Position in This Phase\n\n'
            f'- **available_evidence**:{answer("what the subject saw at the bench")}\n'
            '  <!-- Evidence legitimately available in this phase. -->\n\n'
            '## 2. PORTRAYAL IDENTITY\n\n### Established Identity Facts\n\n'
            f'- **identity_core**:{answer("keeps a promise to the letter")}\n\n'
            '## 4. PHYSICAL\n\n### Appearance & Body\n\n'
            f'- **appearance**:{" " + appearance if appearance else ""}\n\n'
            '## 7. SPEECH\n\n### Speech Patterns\n\n'
            f'- **first_person**:{answer(speech)}\n\n'
            '## 9. KNOWLEDGE\n\n### Expertise\n\n- **field**: bench repair\n- **hobby**:\n\n'
            '## 13. RELATIONSHIPS\n\n### Important People\n\n| Person | Relationship |\n|---|---|\n| C02 | bench partner |\n\n'
            '### Relationship-Specific Realizations\n\n#### C02\n\n- **speech_realization**: drops the formal register\n\n'
            f'## 17. PROHIBITIONS\n\n- **never**:{answer("does not lie to C02")}\n')


def write_series(series: Path) -> None:
    """A narrative whose C01 changes phase at ch2, its personas and an approved scene plot in ch1."""
    from narrative_contract_smoke_test import base
    (series / 'narrative' / 'personas').mkdir(parents=True)
    (series / 'narrative' / 'scenes').mkdir()
    narrative = base()
    c01, c02 = narrative['characters']
    c01['persona'] = 'narrative/personas/c01-later.md'
    c01['phases'] = [{'id': 'early', 'persona': 'narrative/personas/c01.md', 'from_chapter': 'ch1'},
                     {'id': 'later', 'persona': 'narrative/personas/c01-later.md', 'from_chapter': 'ch2',
                      'changed': 'speaks more openly', 'held': 'keeps promises'}]
    c02['persona'] = 'narrative/personas/c02.md'
    (series / 'narrative/narrative.json').write_bytes(m.encoded(narrative))
    (series / 'narrative/personas/c01.md').write_bytes(form_persona('C01 early').encode('utf-8'))
    (series / 'narrative/personas/c01-later.md').write_bytes(
        form_persona('C01 later', speech='open, longer sentences').encode('utf-8'))
    (series / 'narrative/personas/c02.md').write_bytes(form_persona('C02').encode('utf-8'))
    write_plot(series, 'ch1')


def write_plot(series: Path, chapter: str) -> None:
    from scene_plot_contract_smoke_test import approve, plot
    value = plot()
    value.update(chapter=chapter)
    (series / 'narrative/scenes/sc01-plot.json').write_bytes(m.encoded(approve(value)))


def finish_draft(root: Path, name: str) -> dict:
    """Write the values a drafted plan leaves to the author, as a constructed test author."""
    plan = m.load(root, name)
    for row in plan['sources']:
        row['reading_basis'] = 'Constructed test: the complete file was read.'
    for subject in plan['subjects']:
        subject['portrayal_basis'] = 'Constructed test portrayal.'
    plan.update(purpose='Constructed test scene.', conditions=['At the bench.'], reopen_when=['A source changes.'])
    plan['review'].update(by='fixture author', basis='Constructed test review.', decision='ready')
    (root / name).write_bytes(m.encoded(plan))
    return plan


class FormPersonaTests(unittest.TestCase):
    """A persona in the form: its core, its phase, a drafted plan and the reach of a later change."""

    PLOT = 'narrative/scenes/sc01-plot.json'

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        write_series(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, relative: str, raw: bytes) -> None:
        (self.root / relative).write_bytes(raw)

    def drafted(self, name: str = 'plan.json', medium: str = 'text') -> dict:
        self.assertTrue(scene.draft(self.root, self.PLOT, name, medium)['ok'])
        return finish_draft(self.root, name)

    def edit(self, relative: str, old: str, new: str) -> None:
        path = self.root / relative
        path.write_bytes(path.read_bytes().replace(old.encode('utf-8'), new.encode('utf-8')))

    def test_comments_are_not_content(self):
        import persona_units
        first = persona_units.index(form_persona('C01'))
        second = persona_units.index(form_persona('C01').replace('<!-- Evidence legitimately available in this phase. -->',
                                                                  '<!-- Different instructions. -->'))
        self.assertEqual(first, second)

    def test_draft_names_the_core_and_the_other_person(self):
        plan = self.drafted()
        anchors = {row['excerpt_id']: row['anchor'] for row in plan['excerpts']}
        self.assertEqual(anchors['C01-core-2'], '1. TIMELINE > Epistemic Position in This Phase')
        self.assertEqual(anchors['C01-with-C02'], '13. RELATIONSHIPS > Relationship-Specific Realizations > C02')
        self.assertNotIn('4. PHYSICAL > Appearance & Body', anchors.values())
        self.assertEqual(plan['sources'][1]['path'], 'narrative/personas/c01.md')
        self.assertTrue(scene.build(self.root, 'plan.json', 'material')['ok'])

    def test_an_unfilled_draft_is_refused(self):
        scene.draft(self.root, self.PLOT, 'raw.json', 'text')
        with self.assertRaisesRegex(ValueError, 'placeholder not filled: .*purpose'):
            scene.build(self.root, 'raw.json', 'material')

    def test_the_core_is_carried_and_answered(self):
        plan = self.drafted()
        plan['excerpts'] = [row for row in plan['excerpts'] if row['anchor'] != '7. SPEECH > Speech Patterns']
        (self.root / 'plan.json').write_bytes(m.encoded(plan))
        with self.assertRaisesRegex(ValueError, "leaves out '7. SPEECH > Speech Patterns' of the persona core"):
            scene.build(self.root, 'plan.json', 'material')
        self.write('narrative/personas/c02.md', form_persona('C02', core=False).encode('utf-8'))
        self.drafted('blank.json')
        with self.assertRaisesRegex(ValueError, 'C02: the persona core .* is blank'):
            scene.build(self.root, 'blank.json', 'material')

    def test_an_image_carries_the_appearance(self):
        plan = self.drafted('image.json', medium='image')
        anchors = {row['excerpt_id']: row['anchor'] for row in plan['excerpts']}
        self.assertEqual(anchors['C01-appearance-1'], '4. PHYSICAL > Appearance & Body')
        built = scene.build(self.root, 'image.json', 'image')
        self.assertEqual((built['medium'], built['identities']), ('image', []))
        plan['excerpts'] = [row for row in plan['excerpts'] if row['excerpt_id'] != 'C02-appearance-1']
        (self.root / 'image.json').write_bytes(m.encoded(plan))
        with self.assertRaisesRegex(ValueError, 'C02: the material leaves out .* of the appearance an image depicts'):
            scene.build(self.root, 'image.json', 'missing')
        self.write('narrative/personas/c02.md', form_persona('C02', appearance='').encode('utf-8'))
        self.drafted('blank.json', medium='image')
        with self.assertRaisesRegex(ValueError, "C02: the appearance an image depicts '4. PHYSICAL > Appearance & Body' .* is blank"):
            scene.build(self.root, 'blank.json', 'blank')

    def test_the_chapter_decides_the_phase(self):
        self.drafted()
        write_plot(self.root, 'ch2')
        plan = m.load(self.root, 'plan.json')
        plan['sources'][0]['sha256'] = m.digest((self.root / self.PLOT).read_bytes())
        (self.root / 'plan.json').write_bytes(m.encoded(plan))
        with self.assertRaisesRegex(ValueError, 'C01 is in the phase whose persona is narrative/personas/c01-later.md'):
            scene.build(self.root, 'plan.json', 'material')

    def test_impact_separates_quoted_from_unquoted_changes(self):
        self.drafted()
        scene.build(self.root, 'plan.json', 'material')
        self.assertEqual(scene.impact(self.root)['scenes'][0]['status'], 'current')
        self.edit('narrative/personas/c01.md', '- **hobby**:', '- **hobby**: kite flying')
        report = scene.impact(self.root, 'narrative/personas/c01.md')
        row = report['scenes'][0]
        self.assertEqual((row['status'], report['ok']), ('review', True))
        self.assertEqual(row['sources'][0]['changes'],
                         [{'anchor': '9. KNOWLEDGE > Expertise > hobby', 'change': 'filled', 'quoted': False}])
        self.edit('narrative/personas/c01.md', 'short sentences', 'clipped sentences')
        report = scene.impact(self.root, 'narrative/personas/c01.md')
        self.assertEqual((report['scenes'][0]['status'], report['ok']), ('stale', False))
        self.assertIn({'anchor': '7. SPEECH > Speech Patterns > first_person', 'change': 'changed', 'quoted': True},
                      report['scenes'][0]['sources'][0]['changes'])
        self.assertEqual(report['unrecorded'], [])

    def test_the_blank_form_carries_no_answer(self):
        import persona_units
        template = ROOT / 'templates/narrative/personas/persona-template.md'
        found, repeated = persona_units.units(template.read_text(encoding='utf-8'))
        self.assertEqual(repeated, [])
        # Table headers, rules and the defaults a form ships in a row are not answers.
        self.assertEqual([unit['anchor'] for unit in found if not unit['blank']],
                         ['front matter', 'Persona Template (Single Phase)'])

    def test_a_renamed_heading_or_field_is_reported_as_renamed(self):
        self.drafted()
        scene.build(self.root, 'plan.json', 'material')
        self.edit('narrative/personas/c01.md', '#### C02', '#### Tamsin')
        self.edit('narrative/personas/c01.md', '- **field**:', '- **trade**:')
        changes = scene.impact(self.root, 'narrative/personas/c01.md')['scenes'][0]['sources'][0]['changes']
        relations = '13. RELATIONSHIPS > Relationship-Specific Realizations > '
        self.assertIn({'anchor': relations + 'Tamsin > speech_realization', 'change': 'renamed',
                       'from': relations + 'C02 > speech_realization', 'quoted': True}, changes)
        self.assertIn({'anchor': '9. KNOWLEDGE > Expertise > trade', 'change': 'renamed',
                       'from': '9. KNOWLEDGE > Expertise > field', 'quoted': False}, changes)
        self.assertEqual({c['change'] for c in changes}, {'renamed'})

    def test_a_scene_without_material_is_listed_for_its_persona(self):
        report = scene.impact(self.root, 'narrative/personas/c02.md')
        self.assertEqual([(row['scene_id'], row['character']) for row in report['unrecorded']], [('sc01', 'C02')])

    def test_a_replaced_material_is_superseded(self):
        plan = self.drafted()
        first = scene.build(self.root, 'plan.json', 'material')['content_sha256']
        plan['supersedes'] = first
        plan['review']['revisions'] = [{'source_id': 'persona-C01', 'from_sha256': '1' * 64, 'kind': 'correction',
                                        'anchors': ['7. SPEECH > Speech Patterns > first_person'],
                                        'decision': 'Constructed test: the scene keeps the corrected register.'}]
        (self.root / 'plan2.json').write_bytes(m.encoded(plan))
        scene.build(self.root, 'plan2.json', 'material2')
        statuses = {row['material']: row['status'] for row in scene.impact(self.root)['scenes']}
        self.assertEqual(statuses, {'material/material.json': 'superseded', 'material2/material.json': 'current'})


class StudioSceneTests(unittest.TestCase):
    """A series in a studio's story/: paths from the studio, and the status line a persona change adds."""

    PLOT = 'story/narrative/scenes/sc01-plot.json'
    PLAN = 'story/narrative/scenes/sc01.plan.json'
    BUNDLE = 'story/narrative/scenes/sc01-persona'
    PERSONA = 'story/narrative/personas/c01.md'

    def setUp(self):
        import studio
        self.tmp = tempfile.TemporaryDirectory()
        self.root = studio.init(Path(self.tmp.name) / 'studio', 'scene-studio', 'Constructed scene studio')
        write_series(self.root / 'story')

    def tearDown(self):
        self.tmp.cleanup()

    def built(self, medium: str = 'text') -> dict:
        self.assertTrue(scene.draft(self.root, self.PLOT, self.PLAN, medium)['ok'])
        finish_draft(self.root, self.PLAN)
        return scene.build(self.root, self.PLAN, self.BUNDLE)

    def test_paths_are_read_from_the_studio(self):
        self.built()
        plan = m.load(self.root, self.PLAN)
        self.assertEqual([row['path'] for row in plan['sources']],
                         [self.PLOT, self.PERSONA, 'story/narrative/personas/c02.md'])
        self.assertTrue(scene.verify(self.root, self.PLAN, self.BUNDLE, require_ready=True)['ok'])

    def test_two_narratives_under_one_root_are_refused(self):
        write_series(self.root)
        with self.assertRaisesRegex(ValueError, 'narrative/narrative.json and story/narrative/narrative.json'):
            scene.draft(self.root, self.PLOT, 'plan.json', 'text')

    def test_status_names_the_materials_a_persona_change_reaches(self):
        import shlex
        import studio
        self.built()
        self.assertNotIn('persona changes', studio.status(self.root))
        path = self.root / self.PERSONA
        path.write_bytes(path.read_bytes().replace(b'short sentences', b'clipped sentences'))
        line = studio.status(self.root).splitlines()[-1]
        self.assertTrue(line.startswith('persona changes reach 1 scene material (1 stale): python '), line)
        self.assertTrue(line.endswith(' impact --root ' + shlex.quote(str(self.root.resolve()))), line)
        self.assertEqual(scene.impact(self.root, self.PERSONA)['scenes'][0]['material'], self.BUNDLE + '/material.json')

    def test_impact_names_the_studio_images_made_from_a_material(self):
        import execution_contract as c
        import production_binding
        import production_fixtures as fixture
        import production_workflow as workflow
        import studio
        import work_ledger
        self.built('image')
        task = work_ledger.begin(self.root, 'Constructed image from a scene material', ['prepare'])
        (self.root / 'delivery.txt').write_text('One figure at the bench.\n', encoding='utf-8', newline='\n')
        spec = {'task_id': task['task_id'], 'route': 'performance', 'features': ['scene-persona'], 'sources': [],
                'delivery': {'path': 'delivery.txt', 'transport': 'authored-rendition', 'translation_notes': 'None.'},
                'criteria': [{'id': 'scope', 'strength': 'hard', 'text': 'Use only the prepared scope.'}],
                'world_views': [], 'scene_materials': [{'plan': self.PLAN, 'bundle': self.BUNDLE}]}
        fixture.task(self.root, spec, artifact='image')
        (self.root / 'task.json').write_bytes(c.encoded(spec))
        run = workflow.prepare(self.root, 'task.json')['run']
        package = Path(self.tmp.name) / 'package.json'
        package.write_bytes(c.encoded({'production_binding': production_binding.create(
            self.root, run, 'One figure at the bench.')}))
        result = Path(self.tmp.name) / 'result.png'
        result.write_bytes(b'constructed image bytes')
        studio.add_character(self.root, 'C01', '')
        studio.iterate(self.root, 'C01', 'base.front', result, package=package, request=None, response=None,
                       note='Constructed iteration.')
        studio.accept(self.root, 'C01', 'it-0001')
        with (self.root / 'characters/C01/iterations.jsonl').open('a', encoding='utf-8', newline='\n') as log:
            log.write('{"damaged": \n')
        row = scene.impact(self.root)['scenes'][0]
        self.assertEqual(row['runs'], [{'run': run, 'selection_recorded': False}])
        self.assertEqual(row['iterations'], [{'character': 'C01', 'slot': 'base.front', 'iteration_id': 'it-0001',
                                              'status': 'accepted', 'accepted': True}])


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
