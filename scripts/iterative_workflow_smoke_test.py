#!/usr/bin/env python3
"""Synthetic author/editor, history, gallery, scoped reads and conversation regressions.

No network, credentials, private pack or historical file layout is required.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import tempfile
import time
import unittest
from unittest.mock import patch

import execution_contract as c
import sheet_artifacts as fills
import sheet_edits
import sheet_inventory
import sheet_review
import studio
import studio_activity as activity
import work_ledger as work
from sheet_artifacts_smoke_test import make_sheet, make_artifact, accepted, decision


class EditingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sheet = make_sheet(self.root / 'sheet')

    def test_stale_author_edit_preserves_new_selection_and_history(self):
        first = accepted(self.sheet)
        old = c.load(self.sheet)
        second = accepted(self.sheet, marker='second', color=(170, 70, 90))
        wanted = copy.deepcopy(old); wanted['fields']['identity.name'] = 'Revised name'
        result = sheet_edits.apply(self.sheet, sheet_edits.draft(old, wanted))
        actual = c.load(self.sheet)
        self.assertTrue(result['changed'])
        self.assertEqual(actual['fields']['identity.name'], 'Revised name')
        self.assertEqual(actual['slots']['canon.primary']['current']['artifact'], second)
        self.assertEqual(actual['slots']['canon.primary']['history'][0]['artifact'], first)
        again = sheet_edits.apply(self.sheet, sheet_edits.draft(old, wanted))
        self.assertFalse(again['changed'])
        self.assertEqual(c.load(self.sheet), actual)

    def test_concurrent_author_keys_merge_but_same_key_conflict_is_atomic(self):
        base = c.load(self.sheet)
        left = copy.deepcopy(base); left['fields']['identity.name'] = 'New name'
        right = copy.deepcopy(base); right['fields']['identity.species_domain'] = 'Declared machine'
        sheet_edits.apply(self.sheet, sheet_edits.draft(base, left))
        sheet_edits.apply(self.sheet, sheet_edits.draft(base, right))
        before = self.sheet.read_bytes()
        conflict = copy.deepcopy(base)
        conflict['fields']['identity.name'] = 'Conflicting name'
        conflict['fields']['identity.species_domain'] = 'Conflicting structure'
        with self.assertRaisesRegex(ValueError, 'SHEET_EDIT_CONFLICT'):
            sheet_edits.apply(self.sheet, sheet_edits.draft(base, conflict))
        self.assertEqual(self.sheet.read_bytes(), before)
        self.assertEqual(c.load(self.sheet)['fields'], {**base['fields'], **left['fields'], **right['fields'], 'identity.name':'New name'})

    def test_history_can_be_reoffered_without_new_artifact_or_auto_accept(self):
        first = accepted(self.sheet)
        second = accepted(self.sheet, marker='second')
        fills.reoffer(self.sheet, 'canon.primary', first['artifact_id'])
        state = c.load(self.sheet)['slots']['canon.primary']
        self.assertEqual(state['current']['artifact'], second)
        self.assertEqual(state['candidates'], [first])
        fills.adopt(self.sheet, decision(self.sheet, 'canon.primary', first), evidence_root=self.sheet.parent)
        state = c.load(self.sheet)['slots']['canon.primary']
        self.assertEqual(state['current']['artifact'], first)
        self.assertEqual([s['artifact'] for s in state['history']], [first, second])
        self.assertEqual(len(list((self.sheet.parent / '.fills/artifacts').glob('*/provenance.json'))), 2)

    def test_unrelated_missing_candidate_and_history_do_not_block_healthy_current(self):
        previous = accepted(self.sheet)
        current = accepted(self.sheet, marker='current')
        broken = make_artifact(self.sheet, marker='broken')
        fills.register_candidates(self.sheet, [('canon.side', broken)])
        for art in (previous, broken):
            (self.sheet.parent / art['image']['path']).unlink()
        status = sheet_inventory.status(self.sheet, slot='canon.primary', state_filter='current')
        self.assertEqual(status['total'], 1)
        self.assertEqual(status['unavailable_on_page'], 0)
        self.assertEqual(status['entries'][0]['availability'], 'verified')
        self.assertEqual(sheet_inventory.status(self.sheet, slot='canon.side')['unavailable_on_page'], 1)
        result = fills.crop(self.sheet, 'canon.primary', 'detail.hand', [0, 0, 20, 20])
        self.assertIn('artifact_id', result)
        (self.sheet.parent / current['image']['path']).unlink()
        with self.assertRaises((ValueError, OSError)):
            fills.crop(self.sheet, 'canon.primary', 'detail.other', [0, 0, 20, 20])

    def test_two_hundred_candidates_are_paged_and_reviewed_with_linear_validation(self):
        anchor = accepted(self.sheet, size=(64,64))
        candidates = [make_artifact(self.sheet, size=(64,64), marker=f'candidate-{i}',
                      color=(i % 256, (i*3) % 256, 80)) for i in range(205)]
        fills.register_candidates(self.sheet, [('canon.primary', art) for art in candidates])
        original = fills._image_metadata
        with patch.object(fills, '_image_metadata', wraps=original) as metadata:
            first_page = sheet_inventory.status(self.sheet, state_filter='candidate', limit=20)
            self.assertEqual(first_page['total'], 205)
            self.assertEqual(first_page['next_offset'], 20)
            self.assertEqual(metadata.call_count, 20)
        select = lambda art, label: {'sheet':str(self.sheet), 'slot':'canon.primary',
                                    'artifact_id':art['artifact_id'], 'label':label, 'head':None}
        with patch.object(fills, '_image_metadata', wraps=original) as metadata, \
             patch.object(sheet_review, '_montage', wraps=sheet_review._montage) as montage:
            started = time.monotonic()
            result = sheet_review.build_review(select(anchor,'anchor'),
                [select(art,f'candidate-{i}') for i,art in enumerate(candidates)], [],
                out_dir=self.root/'comparison', cell_size=100, pairs_per_page=6)
            elapsed = time.monotonic()-started
            self.assertEqual(metadata.call_count, 206)
            self.assertLessEqual(max(len(call.args[1]) for call in montage.call_args_list), 6)
        self.assertEqual(len(result['montages']['full']), 35)
        self.assertEqual(len(result['candidates']), 205)
        print(json.dumps({'probe':'205-candidate-comparison', 'image_verifications':206,
                          'seconds':round(elapsed,4), 'pages':35, 'maximum_pairs_per_page':6}))


class StudioIterationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = studio.init(Path(self.temp.name)/'studio', 'synthetic-work', 'Synthetic iterative workflow')
        studio.add_character(self.root, 'robot', '')
        self.sheet = make_sheet(self.root/'characters/robot/sheet')

    def test_continuous_author_history_pause_resume_stale_edit_and_local_gallery(self):
        task = work.begin(self.root, 'Develop a synthetic character', ['Establish design','Compare trials','Deliver'])
        first = accepted(self.sheet, marker='first')
        old_editor = c.load(self.sheet)
        work.step_done(self.root, 1)
        question = work.block(self.root, 'Keep A or try B?')['questions'][-1]
        second = make_artifact(self.sheet, marker='second', color=(180,120,20))
        fills.register_candidates(self.sheet, [('canon.primary', second)])
        work.respond(self.root, question['question_id'], 'Try B, then revisit the design.', actor='Synthetic author',
                     candidates=[first['artifact_id'], second['artifact_id']])
        revised = work.reopen(self.root, 1, reason='Explicit synthetic answer revisits the design.', actor='Synthetic author')
        self.assertIsNone(revised['blocked_on']); self.assertEqual(revised['next'], 'Establish design')
        self.assertEqual(revised['revision'], 2)
        self.assertTrue(c.load(self.root/revised['revisions'][0]['snapshot'])['steps'][0]['done_at'])
        # Answering and reopening have not implicitly accepted the proposed image.
        self.assertEqual(fills.current_artifact(c.load(self.sheet)['slots']['canon.primary']), first)
        fills.adopt(self.sheet, decision(self.sheet, 'canon.primary', second), evidence_root=self.sheet.parent)
        work.suspend(self.root, reason='Await another author choice')
        other = work.begin(self.root, 'An independent synthetic task', ['Plan'])
        work.suspend(self.root, reason='Return to character work')
        resumed = work.resume_task(self.root, task['task_id'])
        self.assertEqual(resumed['questions'][-1]['state'], 'answered')
        self.assertEqual(resumed['next'], 'Establish design')
        self.assertEqual(work.suspended_tasks(self.root)[0]['task_id'], other['task_id'])
        fills.reoffer(self.sheet, 'canon.primary', first['artifact_id'])
        fills.adopt(self.sheet, decision(self.sheet, 'canon.primary', first), evidence_root=self.sheet.parent)
        edited = copy.deepcopy(old_editor); edited['fields']['identity.name'] = 'Final synthetic name'
        sheet_edits.apply(self.sheet, sheet_edits.draft(old_editor, edited))
        self.assertEqual(len(c.load(self.sheet)['slots']['canon.primary']['history']), 2)
        many = [make_artifact(self.sheet, marker=f'long-session-{i}', color=(i % 256, 70, 40)) for i in range(205)]
        fills.register_candidates(self.sheet, [('detail.hand', art) for art in many])
        (self.sheet.parent/many[0]['image']['path']).unlink()
        cropped = fills.crop(self.sheet, 'canon.primary', 'detail.hand', [0,0,20,20])
        self.assertEqual(sheet_inventory.status(self.sheet, slot='detail.hand', limit=1)['total'], 206)
        self.assertGreater(sum(p.is_file() for p in self.root.rglob('*')), 1000)
        # Local publications appear without an explicit gallery command.
        index = c.load(self.root/'gallery.json')
        self.assertEqual(index['entries'][0]['kind'], 'crop')
        self.assertEqual(index['entries'][0]['status'], 'candidate')
        self.assertEqual(index['entries'][0]['slot'], 'detail.hand')
        self.assertEqual(studio.gallery_stale(self.root), None)
        events, errors = activity.read_events(self.root)
        self.assertFalse(errors)
        types = {row['event'] for row in events}
        self.assertTrue({'work-answered','work-reopened','work-suspended','work-resumed','sheet-history-reoffered','sheet-edited'} <= types)
        timeline = (self.root/'work/activity/timeline.jsonl').read_text(encoding='utf-8').splitlines()
        self.assertEqual(len(timeline), len(events))
        self.assertEqual(work.check(self.root), [])

    def test_bad_old_activity_and_retry_receipt_do_not_hide_current_gallery(self):
        accepted(self.sheet, marker='first')
        malformed = self.root/'work/activity/events/ff/ff-malformed.json'
        c.atomic(malformed, c.encoded({'event_id':malformed.stem}))
        retry = self.root/'work/activity/pending-events/unreadable.json'
        c.atomic(retry, b'{synthetic broken receipt')
        newest = accepted(self.sheet, marker='newest')
        report = activity.refresh(self.root)
        self.assertFalse(report['ok'])
        self.assertTrue(report['views_refreshed'])
        self.assertTrue(report['timeline']['diagnostics'])
        self.assertTrue(retry.exists())
        self.assertEqual(c.load(self.root/'gallery.json')['entries'][0]['artifact_id'], newest['artifact_id'])
        self.assertIsNone(studio.gallery_stale(self.root))

    def test_partial_gallery_publish_is_detected_and_sync_repairs_both_views(self):
        accepted(self.sheet, marker='first')
        stale = (self.root/'gallery.html').read_bytes()
        accepted(self.sheet, marker='second')
        (self.root/'gallery.html').write_bytes(stale)
        self.assertIn('revision', studio.gallery_stale(self.root))
        self.assertTrue(activity.refresh(self.root)['ok'])
        self.assertIsNone(studio.gallery_stale(self.root))

    def test_cli_crop_automatically_logs_operation_and_correlates_activity(self):
        import subprocess
        import sys
        accepted(self.sheet)
        command = Path(__file__).with_name('sheet_workflow.py')
        result = subprocess.run([sys.executable, str(command), 'crop', '--sheet', str(self.sheet),
            '--source-slot', 'canon.primary', '--target-slot', 'detail.hand', '--rectangle', '0','0','20','20'],
            capture_output=True, text=True, encoding='utf-8', check=False)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        artifact = json.loads(result.stdout)
        operations = list((self.root/'logs/operations').glob('*/*/operation.json'))
        self.assertEqual(len(operations), 1)
        operation = c.load(operations[0])
        self.assertEqual(operation['context']['studio'], str(self.root))
        self.assertEqual(operation['arguments']['command'], 'crop')
        for name in ('stdout.log','stderr.log','events.jsonl','artifacts.json'):
            self.assertTrue((operations[0].parent/name).is_file())
        events, diagnostics = activity.read_events(self.root)
        self.assertFalse(diagnostics)
        self.assertTrue(any(event['operation_id']==operation['operation_id'] for event in events))
        self.assertEqual(c.load(self.root/'gallery.json')['entries'][0]['artifact_id'], artifact['artifact_id'])

    def test_gallery_is_newest_first_uses_recorded_time_not_mtime_or_acceptance(self):
        first = accepted(self.sheet, marker='first')
        second = accepted(self.sheet, marker='second')
        # Explicit recorded offsets demonstrate absolute-time ordering.
        for art, at in ((first,'2026-10-08T10:00:00+09:00'), (second,'2026-10-08T00:30:00Z')):
            pub = self.sheet.parent/Path(art['provenance']['path']).parent/'publication.json'
            value=c.load(pub); value['recorded_at']=at; c.atomic_write_json(pub,value)
        activity.refresh(self.root)
        rows = c.load(self.root/'gallery.json')['entries']
        self.assertEqual(rows[0]['artifact_id'], first['artifact_id'])
        self.assertEqual(rows[0]['status'], 'superseded')
        self.assertEqual(rows[1]['artifact_id'], second['artifact_id'])
        (self.root/'gallery.html').unlink()
        studio.status(self.root)
        self.assertTrue((self.root/'gallery.html').is_file())
        self.assertIsNone(studio.gallery_stale(self.root))

    def test_missing_old_artwork_is_visible_unavailable_and_does_not_hide_new_work(self):
        first = accepted(self.sheet, marker='first')
        second = accepted(self.sheet, marker='second')
        (self.sheet.parent/first['image']['path']).unlink()
        self.assertTrue(activity.refresh(self.root)['ok'])
        rows = c.load(self.root/'gallery.json')['entries']
        self.assertEqual(len(rows), 2)
        by_id = {row['artifact_id']:row for row in rows}
        self.assertEqual(by_id[first['artifact_id']]['availability'], 'unavailable')
        self.assertEqual(by_id[second['artifact_id']]['availability'], 'present')

    def test_projection_failure_preserves_committed_artwork_and_is_repairable(self):
        image = make_artifact(self.sheet)
        with patch.object(studio,'write_gallery',side_effect=OSError('synthetic display failure')):
            result = fills.register_candidates(self.sheet,[('canon.primary',image)])
        self.assertEqual(result['candidates'][0]['artifact_id'], image['artifact_id'])
        self.assertFalse(result['projection']['ok'])
        self.assertTrue(result['projection']['committed_state_retained'])
        self.assertTrue((self.root/'work/activity/projections-pending.json').exists())
        self.assertEqual(c.load(self.sheet)['slots']['canon.primary']['candidates'], [image])
        self.assertTrue(activity.refresh(self.root)['ok'])
        self.assertFalse((self.root/'work/activity/projections-pending.json').exists())
        self.assertEqual(len(c.load(self.root/'gallery.json')['entries']), 1)

    def test_failed_activity_append_is_queued_then_idempotently_repaired(self):
        with patch.object(activity, 'event', side_effect=OSError('synthetic log failure')):
            result = activity.changed(self.sheet, 'synthetic-change', revision='one', details={'state':'committed'})
        self.assertFalse(result['ok']); self.assertTrue(result['retry_receipt_saved'])
        self.assertTrue(activity.refresh(self.root)['ok'])
        activity.changed(self.sheet, 'synthetic-change', revision='one', details={'state':'committed'})
        rows, _ = activity.read_events(self.root)
        self.assertEqual(sum(row['event']=='synthetic-change' for row in rows), 1)

    def test_managed_gallery_elsewhere_has_a_working_studio_base(self):
        accepted(self.sheet)
        path, _ = studio.write_gallery(self.root, self.root/'views/browser/gallery.html')
        page = path.read_text(encoding='utf-8')
        self.assertIn('<base href="../../">', page)
        self.assertIn('loading="lazy"',page)
        self.assertIn('work/activity/timeline.md',page)
