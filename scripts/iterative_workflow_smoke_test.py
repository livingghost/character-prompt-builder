#!/usr/bin/env python3
"""Synthetic author/editor, history, gallery, scoped reads and conversation regressions.

No network, credentials, private pack or historical file layout is required.
"""
from __future__ import annotations

import copy
import contextvars
from concurrent.futures import ThreadPoolExecutor
import json
import multiprocessing
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
import studio_gallery
import studio_activity as activity
import work_ledger as work
from sheet_artifacts_smoke_test import make_sheet, make_artifact, accepted, decision


def _concurrent_gallery(root: str, source: str, role: str, notices, release) -> None:
    """Two spawned processes overlap a view build and a canonical import."""
    root = Path(root)
    try:
        if role == 'older':
            original = studio_gallery.publish

            def paused(root, index, out=None):
                notices.send(('snapshot', len(index['entries'])))
                if not release.wait(20):
                    raise TimeoutError('Synthetic publication barrier timed out')
                return original(root, index, out)

            with patch.object(studio_gallery, 'publish', side_effect=paused):
                studio.write_gallery(root)
        else:
            original = activity.event

            def committed(root, kind, *args, **kwargs):
                result = original(root, kind, *args, **kwargs)
                if kind == 'iteration-recorded':
                    notices.send(('source-committed', result['event_id']))
                return result

            with patch.object(activity, 'event', side_effect=committed):
                studio.iterate(root, 'robot', 'base.front', Path(source), package=None,
                    request=None, response=None, note='Synthetic concurrent import')
        notices.send(('finished', True))
    except BaseException:
        import traceback
        notices.send(('failure', traceback.format_exc()))
        raise
    finally:
        notices.close()


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

    def import_image(self, name: str) -> dict:
        from PIL import Image
        path = self.root.parent / (name + '.png')
        Image.new('RGB', (8, 8), 'red').save(path)
        return studio.iterate(self.root, 'robot', 'base.front', path, package=None,
                              request=None, response=None, note='Synthetic ' + name)

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

    def test_work_note_updates_only_activity(self):
        work.begin(self.root, 'Synthetic isolated note', ['Document the decision'])
        with (patch.object(studio, 'write_gallery') as gallery,
              patch('adoption_workflow._reference_index') as references):
            result = work.note(self.root, 'No artwork or adoption changed.')
        gallery.assert_not_called()
        references.assert_not_called()
        self.assertNotIn('projection_warning', result)
        self.assertIn('No artwork or adoption changed.', work.read_current(self.root)['notes'])
        self.assertIn('work-note', (self.root/'work/activity/timeline.md').read_text(encoding='utf-8'))
        self.assertFalse((self.root/'work/activity/projections-pending.json').exists())

    def test_outer_operation_reports_deferred_display_failure(self):
        image = make_artifact(self.sheet)
        with patch.object(studio, 'write_gallery', side_effect=OSError('synthetic deferred failure')) as gallery:
            with activity.operation(self.root) as projection:
                result = fills.register_candidates(self.sheet, [('canon.primary', image)])
                activity.changed(self.sheet, 'synthetic-owner-finished', revision='complete')
                gallery.assert_not_called()
        self.assertEqual(gallery.call_count, 1)
        self.assertFalse(projection['ok'])
        self.assertFalse(result['projection']['ok'])
        receipt = activity.project_result({'committed': True}, projection)
        self.assertTrue(receipt['committed'])
        self.assertTrue(receipt['projection_warning']['committed_state_retained'])
        self.assertEqual(c.load(self.sheet)['slots']['canon.primary']['candidates'], [image])

    def test_refresh_keeps_a_concurrent_writers_dirty_receipt(self):
        original = studio.write_gallery

        def concurrent_event(root, *args, **kwargs):
            activity.event(root, 'synthetic-concurrent-change', 'gallery', revision='later', views={'gallery'})
            return original(root, *args, **kwargs)

        with patch.object(studio, 'write_gallery', side_effect=concurrent_event):
            self.assertTrue(activity.refresh(self.root)['ok'])
        self.assertTrue((self.root/'work/activity/projections-pending.json').exists())
        self.assertTrue(activity.refresh(self.root)['ok'])
        self.assertFalse((self.root/'work/activity/projections-pending.json').exists())

    def test_supplied_read_cannot_overwrite_new_gallery_or_reference_state(self):
        first = self.import_image('first')
        studio.accept(self.root, 'robot', first['iteration_id'])
        old = studio.StudioRead(self.root)
        old.iterations('robot'); old.sheet('robot'); old.reference_index('robot')
        second = self.import_image('second')
        studio.accept(self.root, 'robot', second['iteration_id'])
        self.assertEqual(len(c.load(self.root/'gallery.json')['entries']), 2)
        self.assertTrue(activity.refresh(self.root, read=old)['ok'])
        self.assertEqual(len(c.load(self.root/'gallery.json')['entries']), 2)
        self.assertEqual(len(old.iterations('robot')), 2)
        bindings = c.load(self.sheet.parent/'active-references.json')['bindings']
        self.assertEqual([row['iteration_id'] for row in bindings], [second['iteration_id']])
        self.assertFalse((self.root/'work/activity/projections-pending.json').exists())
        self.assertIsNone(studio.gallery_stale(self.root))

    def test_same_event_retry_during_build_keeps_its_own_repair_receipt(self):
        kwargs = dict(revision='same-revision', views={'gallery'})
        activity.event(self.root, 'synthetic-retry', 'gallery', **kwargs)
        original = studio.write_gallery

        def concurrent_retry(root, *args, **options):
            result = original(root, *args, **options)
            activity.event(root, 'synthetic-retry', 'gallery', **kwargs)
            return result

        with patch.object(studio, 'write_gallery', side_effect=concurrent_retry):
            report = activity.refresh(self.root, views={'gallery'})
        self.assertTrue(report['ok'])
        self.assertTrue((self.root/'work/activity/projections-pending.json').exists())
        self.assertEqual(len(list((self.root/'work/activity/dirty/gallery').glob('*'))), 1)
        self.assertEqual(sum(row['event'] == 'synthetic-retry' for row in activity.read_events(self.root)[0]), 1)
        self.assertTrue(activity.refresh(self.root, views={'gallery'})['ok'])
        self.assertFalse((self.root/'work/activity/projections-pending.json').exists())

    def test_pending_marker_cleanup_cannot_erase_a_new_writer_notice(self):
        pending = self.root/'work/activity/projections-pending.json'
        original = Path.unlink
        raced = False

        def write_before_delete(path, *args, **kwargs):
            nonlocal raced
            if path == pending and not raced:
                raced = True
                activity.event(self.root, 'synthetic-late-write', 'gallery', revision='late', views={'gallery'})
            return original(path, *args, **kwargs)

        with patch.object(Path, 'unlink', new=write_before_delete):
            self.assertTrue(activity.refresh(self.root, views={'activity-timeline'})['ok'])
        self.assertTrue(raced)
        self.assertTrue(pending.exists())
        self.assertTrue(list((self.root/'work/activity/dirty/gallery').glob('*')))
        self.assertTrue(activity.refresh(self.root)['ok'])
        self.assertFalse(pending.exists())

    def test_failed_explicit_view_stays_pending_when_another_view_succeeds(self):
        self.assertFalse((self.root/'work/activity/projections-pending.json').exists())
        with patch.object(studio, 'write_gallery', side_effect=OSError('Synthetic explicit view failure')):
            self.assertFalse(activity.refresh(self.root, views={'gallery'})['ok'])
        self.assertTrue(activity.refresh(self.root, views={'activity-timeline'})['ok'])
        self.assertTrue((self.root/'work/activity/projections-pending.json').exists())
        self.assertTrue(list((self.root/'work/activity/dirty/gallery').glob('*')))
        self.assertTrue(activity.refresh(self.root, views={'gallery'})['ok'])
        self.assertFalse((self.root/'work/activity/projections-pending.json').exists())

    def test_refresh_does_not_acknowledge_an_unpublished_receipt_temporary(self):
        temporary = self.root/'work/activity/dirty/gallery'/ (c.TEMPORARY_PREFIX + 'synthetic-writer')
        temporary.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_bytes(b'Synthetic writer has not published this receipt yet')
        self.assertTrue(activity.refresh(self.root, views={'gallery'})['ok'])
        self.assertTrue(temporary.exists())

    def test_copied_context_cannot_reuse_a_completed_publication_admission(self):
        self.import_image('first')
        old = studio.StudioRead(self.root)
        old.iterations('robot')
        with activity.publication(activity.artwork_owner(self.root)):
            copied = contextvars.copy_context()
        self.import_image('second')
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(copied.run, studio.write_gallery, self.root, read=old).result(timeout=20)
        self.assertEqual(len(c.load(self.root/'gallery.json')['entries']), 2)
        self.import_image('third')
        copied.run(studio.write_gallery, self.root, read=old)
        self.assertEqual(len(c.load(self.root/'gallery.json')['entries']), 3)

    def test_unconfigured_story_needs_no_publisher_and_keeps_a_new_source_notice(self):
        import story_timeline
        with patch.object(c, 'lock', wraps=c.lock) as locks:
            self.assertTrue(activity.refresh(self.root, views={'story-timeline'})['ok'])
        locks.assert_not_called()
        activity.event(self.root, 'synthetic-old-story', 'timeline', revision='old', views={'story-timeline'})
        original = story_timeline.configured

        def source_arrives(root):
            configured = original(root)
            self.assertFalse(configured)
            c.atomic_write_json(root/story_timeline.CONFIG, story_timeline.DEFAULT)
            activity.event(root, 'synthetic-new-story', 'timeline', revision='new', views={'story-timeline'})
            return configured

        with (patch.object(story_timeline, 'configured', side_effect=source_arrives),
              patch.object(c, 'lock', wraps=c.lock) as locks):
            report = activity.refresh(self.root, views={'story-timeline'})
        locks.assert_not_called()
        self.assertTrue(report['ok'])
        self.assertTrue((self.root/'work/activity/projections-pending.json').exists())
        self.assertEqual(len(list((self.root/'work/activity/dirty/story-timeline').glob('*'))), 1)
        self.assertTrue(original(self.root))
        self.assertFalse((self.root/story_timeline.OUTPUT).exists())

    def test_absent_studio_needs_no_publisher_and_keeps_a_new_manifest_notice(self):
        root = self.root.parent/'activity-only'
        root.mkdir()
        views = {'gallery', 'active-references'}
        activity.event(root, 'synthetic-old-studio', 'studio', revision='old', views=views)
        original = Path.is_file
        appeared = False

        def manifest_arrives(path):
            nonlocal appeared
            present = original(path)
            if path == root/studio.MANIFEST and not appeared:
                appeared = True
                self.assertFalse(present)
                document = {**studio.manifest(self.root), 'studio_id': 'synthetic-new-studio', 'characters': []}
                c.atomic_write_json(path, document)
                activity.event(root, 'synthetic-new-studio', 'studio', revision='new', views=views)
            return present

        with (patch.object(Path, 'is_file', new=manifest_arrives),
              patch.object(c, 'lock', wraps=c.lock) as locks):
            report = activity.refresh(root, views=views)
        locks.assert_not_called()
        self.assertTrue(appeared)
        self.assertTrue(report['ok'])
        self.assertTrue((root/'work/activity/projections-pending.json').exists())
        self.assertFalse((root/'gallery.json').exists())
        for view in views:
            self.assertEqual(len(list((root/'work/activity/dirty'/view).glob('*'))), 1)
        self.assertTrue(activity.refresh(root, views=views)['ok'])
        self.assertTrue((root/'gallery.json').exists())
        self.assertFalse((root/'work/activity/projections-pending.json').exists())

    def test_separate_process_refreshes_publish_latest_committed_artwork(self):
        self.import_image('first')
        context = multiprocessing.get_context('spawn')
        release = context.Event()
        old_read, old_write = context.Pipe(duplex=False)
        new_read, new_write = context.Pipe(duplex=False)
        old = context.Process(target=_concurrent_gallery,
            args=(str(self.root), '', 'older', old_write, release))
        new = context.Process(target=_concurrent_gallery,
            args=(str(self.root), str(self.root.parent/'first.png'), 'newer', new_write, release))
        started = []
        try:
            old.start(); started.append(old); old_write.close()
            self.assertTrue(old_read.poll(20), 'Older publisher did not read its source')
            self.assertEqual(old_read.recv(), ('snapshot', 1))
            new.start(); started.append(new); new_write.close()
            self.assertTrue(new_read.poll(20), 'Canonical writer did not commit during publication')
            self.assertEqual(new_read.recv()[0], 'source-committed')
            self.assertEqual(len(studio.read_iteration_records(self.sheet.parent.parent)), 2)
            # The canonical update is allowed through; its newer display waits
            # for the older publisher and then reads the committed source.
            self.assertFalse(new_read.poll(0.1), 'A newer publisher bypassed the active display owner')
            release.set()
            for process, channel in ((old, old_read), (new, new_read)):
                process.join(20)
                self.assertFalse(process.is_alive(), 'Projection process did not finish')
                self.assertTrue(channel.poll(1), 'Projection process returned no result')
                self.assertEqual(channel.recv(), ('finished', True))
                self.assertEqual(process.exitcode, 0)
            self.assertEqual(len(c.load(self.root/'gallery.json')['entries']), 2)
            self.assertIsNone(studio.gallery_stale(self.root))
            self.assertFalse((self.root/'work/activity/projections-pending.json').exists())
        finally:
            release.set()
            for process in started:
                if process.is_alive():
                    process.terminate()
                process.join(5)
                process.close()
            for channel in (old_read, old_write, new_read, new_write):
                channel.close()

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
        entry = c.load(path.with_suffix('.json'))['entries'][0]
        detail = studio_gallery.detail_file(path, entry['entry_id']).read_text(encoding='utf-8')
        self.assertIn('loading="lazy"', detail)
        self.assertIn('views/browser/gallery.assets/index.js', page)
        self.assertIn('work/activity/timeline.md',page)


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
