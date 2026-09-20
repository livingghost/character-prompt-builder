#!/usr/bin/env python3
"""Exercise dispatch preflight and post-send recovery without credentials or a service."""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import dispatch
import studio


class DispatchRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="cpb-dispatch-recovery-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = studio.init(self.base / "studio", "recovery-test", "Offline recovery tests")
        self.home = studio.add_character(self.root, "C01", "")
        self.package = self.base / "generation-package.json"
        self.package.write_text('{"generation_payload": {}, "production_binding": null}', encoding="utf-8")
        self.source = self.root / "source.png"
        self.source.write_bytes(b"offline-source")
        self.options = argparse.Namespace(package=self.package, service=None, profiles=None, seed=None, count=2,
                                          send=True, character="C01", slot="base.front", note=None,
                                          source=self.source, model="fixture", scale=2, settings="{}", guidance=None,
                                          production_root=self.root, production_run='synthetic-boundary-stub',
                                          production_authorization='synthetic-receipt-stub')
        self.request = {"taskUUID": "fixed-fixture-task-uuid", "model": "fixture-model", "seed": 7}
        self.answer = {"data": [{"imageURL": "https://example.invalid/one.png"}]}
        self.entries = [{"url": "https://example.invalid/one.png", "id": "one", "seed": 11},
                        {"url": "https://example.invalid/two.png", "id": "two", "seed": 12}]
        self.transport = SimpleNamespace(
            build=Mock(side_effect=lambda *a, **k: dict(self.request)),
            build_upscale=Mock(side_effect=lambda *a, **k: dict(self.request)),
            media_paths=Mock(return_value=[str(self.source)]), upload=Mock(return_value="uploaded-fixture"),
            send=Mock(return_value=self.answer), rejections=Mock(return_value=[]),
            results=Mock(side_effect=lambda answer: list(self.entries)),
        )
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
        # This suite isolates storage/network-failure behavior behind explicit stubs.
        # Real scoped grants, snapshots and claim-before-upload are tested separately.
        for target in ('production_binding.validate_live', 'production_binding.validate_upscale_live',
                       'production_workflow.claim_dispatch', 'production_workflow.record_dispatch_results'):
            self.stack.enter_context(patch(target))
        self.patches = {}
        offering = {"service": "fixture", "model_identifier": "fixture-model", "observed_at": "2026-09-15"}
        record = {"operation_kind": "upscale", "supported_scale_factors": [2], "upscale_settings": {}, "upscaler_class": "deterministic"}
        for name, kwargs in {
            "verify": {"return_value": {"model": "fixture"}},
            "validate_generation_package_carrier_paths": {"return_value": None},
            "resolve_model_record": {"return_value": ("fixture", record)},
            "select_offering": {"return_value": offering},
            "service_for": {"return_value": ("fixture", {}, self.transport)},
            "check_request": {}, "validate_generation_parameters": {},
            "model_pack_root": {"return_value": self.base},
            "api_key": {"return_value": "OFFLINE-CREDENTIAL-MUST-NEVER-BE-SAVED"},
            "save": {"side_effect": self.save},
        }.items():
            self.patches[name] = self.stack.enter_context(patch.object(dispatch, name, **kwargs))

    @staticmethod
    def save(url, destination):
        destination.write_bytes(b"offline-image-result")
        return "fixture-hash"

    def call(self, mode="generation"):
        if mode == "upscale":
            self.entries = self.entries[:1]
        return getattr(dispatch, "dispatch_" + mode)(self.options, self.root)

    def journal(self):
        paths = list((self.root / "runs").glob("*/run.json"))
        self.assertEqual(len(paths), 1)
        return paths[0].parent, json.loads(paths[0].read_text(encoding="utf-8"))

    def assert_no_network(self):
        self.transport.upload.assert_not_called()
        self.transport.send.assert_not_called()
        self.patches["api_key"].assert_not_called()

    def fake_upscale_builder(self, **kwargs):
        # The package builder has its own image/model contract suite. Here the
        # storage contract is the relative source and output it was handed.
        return {"artifact_type": "upscale-package", "source": kwargs["source_stored_path"],
                "output": kwargs["output_stored_path"]}

    def test_unknown_character_is_rejected_before_upload_in_both_modes(self):
        for mode in ("generation", "upscale"):
            with self.subTest(mode=mode):
                self.options.character = "MISSING"
                with self.assertRaisesRegex(ValueError, "not in this studio"):
                    self.call(mode)
                self.assert_no_network()

    def test_invalid_slots_and_trailing_newlines_are_rejected_before_upload(self):
        for mode in ("generation", "upscale"):
            for slot in ("../escape", "Base Front", "base.front\n", ""):
                with self.subTest(mode=mode, slot=slot):
                    self.options.slot = slot
                    with self.assertRaisesRegex(ValueError, "slot must be"):
                        self.call(mode)
                    self.assert_no_network()
        self.options.character = "C01\n"
        with self.assertRaisesRegex(ValueError, "character id"):
            self.call()

    def test_missing_run_directory_is_refused_before_upload(self):
        runs = self.root / "runs"
        (runs / "README.md").unlink()
        runs.rmdir()
        runs.write_text("not a directory", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "recording destination"):
            self.call()
        self.assert_no_network()

    def test_unwritable_destination_is_refused_before_upload(self):
        with patch.object(studio.tempfile, "mkstemp", side_effect=PermissionError("write denied")):
            with self.assertRaises(PermissionError):
                self.call()
        self.assert_no_network()

    def test_corrupt_iteration_log_is_refused_before_upload(self):
        (self.home / "iterations.jsonl").write_text("broken json", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.call()
        self.assert_no_network()

    def test_dry_run_writes_nothing_and_sends_nothing_in_both_modes(self):
        self.options.send = False
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        for mode in ("generation", "upscale"):
            with self.subTest(mode=mode):
                self.assertEqual(self.call(mode), 0)
                self.assert_no_network()
        after = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_success_records_every_image_seed_and_exact_request(self):
        self.assertEqual(self.call(), 0)
        path, journal = self.journal()
        self.assertEqual(journal["status"], "complete")
        self.assertEqual(journal["iterations"], ["it-0001", "it-0002"])
        self.assertEqual(json.loads((path / "request.json").read_text()), self.request)
        self.assertEqual(json.loads((path / "answer.json").read_text()), self.answer)
        self.assertEqual([row["seed"] for row in studio.read_iterations(self.home)], [11, 12])
        for file in self.root.rglob("*.json"):
            self.assertNotIn("OFFLINE-CREDENTIAL-MUST-NEVER-BE-SAVED", file.read_text(encoding="utf-8"))

    def test_generation_uploads_reverified_saved_carriers_not_live_author_files(self):
        companion = self.base / "fixture.references"
        companion.mkdir()
        (companion / "input.png").write_bytes(b"approved-carrier")
        self.patches["validate_generation_package_carrier_paths"].return_value = companion.name
        self.patches["verify"].side_effect = lambda package, *, package_root: {
            "model": "fixture", "root": package_root,
        }
        self.transport.media_paths.side_effect = lambda verified: [
            str(verified["root"] / companion.name / "input.png")
        ]
        self.assertEqual(self.call(), 0)
        run, _ = self.journal()
        self.assertEqual(self.patches["verify"].call_count, 2)
        self.transport.upload.assert_called_once_with(str(run / companion.name / "input.png"), {},
                                                     "OFFLINE-CREDENTIAL-MUST-NEVER-BE-SAVED")
        self.assertEqual((run / companion.name / "input.png").read_bytes(), b"approved-carrier")

    def test_package_changed_during_snapshot_is_rejected_before_upload(self):
        keep = dispatch.RunJournal.keep
        def changed(journal, source, name):
            if name == "package.json":
                source.write_text('{"generation_payload": {}, "changed": true}', encoding="utf-8")
            return keep(journal, source, name)
        with patch.object(dispatch.RunJournal, "keep", changed), self.assertRaisesRegex(ValueError, "changed"):
            self.call()
        self.transport.upload.assert_not_called()
        self.transport.send.assert_not_called()
        run, document = self.journal()
        self.assertEqual(document["status"], "failed")
        self.assertTrue((run / "package.json").is_file())

    def test_upload_failure_preserves_package_and_does_not_send(self):
        self.transport.upload.side_effect = OSError("offline upload failure")
        with self.assertRaises(OSError):
            self.call()
        path, journal = self.journal()
        self.assertEqual(journal["failed_at"], "uploading")
        self.assertEqual((path / "package.json").read_bytes(), self.package.read_bytes())
        self.transport.send.assert_not_called()

    def test_send_failure_preserves_request_without_automatic_retry(self):
        self.transport.send.side_effect = OSError("offline network failure")
        with self.assertRaises(OSError):
            self.call()
        path, journal = self.journal()
        self.assertEqual(journal["failed_at"], "sending")
        self.assertEqual(json.loads((path / "request.json").read_text()), self.request)
        self.assertEqual(self.transport.send.call_count, 1)
        self.assertFalse((path / "answer.json").exists())

    def test_service_refusal_preserves_exact_answer(self):
        self.transport.rejections.return_value = [{"reason": "offline refusal"}]
        self.assertEqual(self.call(), 1)
        path, journal = self.journal()
        self.assertEqual(journal["status"], "refused")
        self.assertEqual(json.loads((path / "answer.json").read_text()), self.answer)
        self.assertEqual(studio.read_iterations(self.home), [])

    def test_empty_result_preserves_answer_in_both_modes(self):
        self.entries = []
        with self.assertRaisesRegex(ValueError, 'count'):
            self.call()
        path, journal = self.journal()
        self.assertEqual(journal["failed_at"], "response-count-mismatch")
        self.assertTrue((path / "answer.json").is_file())
        with self.assertRaisesRegex(ValueError, 'count'):
            self.call("upscale")
        for file in (self.root / "runs").glob("*/run.json"):
            self.assertEqual(json.loads(file.read_text())["failed_at"], "response-count-mismatch")

    def test_download_failure_preserves_answer_and_result_metadata(self):
        self.patches["save"].side_effect = OSError("offline download failure")
        with self.assertRaises(OSError):
            self.call()
        path, journal = self.journal()
        self.assertEqual(journal["failed_at"], "downloading")
        self.assertTrue((path / "answer.json").is_file())
        self.assertEqual(json.loads((path / "response-1.json").read_text())["url"], self.entries[0]["url"])

    def test_recording_failure_preserves_result_and_reference_companion_for_recovery(self):
        companion = self.base / "generation-package.references"
        companion.mkdir()
        (companion / "reference.svg").write_text("offline reference", encoding="utf-8")
        self.patches["validate_generation_package_carrier_paths"].return_value = companion.name
        with patch.object(studio, "iterate", side_effect=OSError("offline disk failure")):
            with self.assertRaises(OSError):
                self.call()
        path, journal = self.journal()
        self.assertEqual(journal["failed_at"], "recording")
        self.assertEqual((path / "result-1.png").read_bytes(), b"offline-image-result")
        self.assertTrue((path / companion.name / "reference.svg").is_file())
        # Re-record the saved files locally, with no second service request.
        row = studio.iterate(self.root, "C01", "base.front", path / "result-1.png", package=path / "package.json",
                             request=path / "request.json", response=path / "response-1.json", note="recovered",
                             package_companion=path / companion.name)
        self.assertEqual(row["seed"], 11)
        self.assertEqual(self.transport.send.call_count, 1)

    def test_recovery_cli_keeps_saved_companion_without_resending(self):
        self.call()
        path, _ = self.journal()
        companion = path / "saved.references"
        companion.mkdir()
        (companion / "ref.svg").write_text("offline reference", encoding="utf-8")
        result = studio.main([
            "--studio", str(self.root), "iterate", "--character", "C01", "--slot", "recovered.front",
            "--result", str(path / "result-1.png"), "--package", str(path / "package.json"),
            "--request", str(path / "request.json"), "--response", str(path / "response-1.json"),
            "--package-companion", str(companion),
        ])
        self.assertEqual(result, 0)
        row = studio.read_iterations(self.home)[-1]
        self.assertTrue((self.root / row["package"]["path"]).parent.joinpath("saved.references/ref.svg").is_file())
        self.assertEqual(self.transport.send.call_count, 1)

    def test_partial_recording_keeps_prior_iteration_and_remaining_download(self):
        actual = studio.iterate
        count = 0
        def fail_second(*args, **kwargs):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError("offline second record failure")
            return actual(*args, **kwargs)
        with patch.object(studio, "iterate", side_effect=fail_second):
            with self.assertRaises(OSError):
                self.call()
        path, journal = self.journal()
        self.assertEqual(journal["iterations"], ["it-0001"])
        self.assertTrue((path / "result-2.png").is_file())
        self.assertEqual(len(studio.read_iterations(self.home)), 1)

    def test_upscale_package_failure_preserves_source_output_and_answer(self):
        with patch.object(dispatch, "build_upscale_package", side_effect=ValueError("offline invalid dimensions")):
            with self.assertRaises(ValueError):
                self.call("upscale")
        path, journal = self.journal()
        self.assertEqual(journal["failed_at"], "building-package")
        self.assertEqual((path / "upscale.references/source.png").read_bytes(), self.source.read_bytes())
        self.assertTrue((path / "upscale.references/output-1.png").is_file())
        self.assertTrue((path / "answer.json").is_file())

    def test_upscale_records_all_results_with_portable_source_and_output(self):
        with patch.object(dispatch, "build_upscale_package", side_effect=self.fake_upscale_builder):
            self.assertEqual(self.call("upscale"), 0)
        path, journal = self.journal()
        self.assertEqual(journal["status"], "complete")
        self.assertEqual(len(journal["iterations"]), 1)
        for row in studio.read_iterations(self.home):
            package_path = self.root / row["package"]["path"]
            package = json.loads(package_path.read_text())
            self.assertTrue((package_path.parent / package["source"]).is_file())
            self.assertTrue((package_path.parent / package["output"]).is_file())

    def test_repeated_task_uuid_never_overwrites_previous_run(self):
        self.assertEqual(self.call(), 0)
        self.assertEqual(self.call(), 0)
        self.assertEqual(len(list((self.root / "runs").glob("*/request.json"))), 2)
        self.assertEqual(len(studio.read_iterations(self.home)), 4)


def main():
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream).run(unittest.defaultTestLoader.loadTestsFromTestCase(DispatchRecoveryTests))
    print(json.dumps({"ok": result.wasSuccessful(), "checks": result.testsRun,
                      "failures": len(result.failures), "error_count": len(result.errors),
                      "errors": [f"{case.id()}: {detail}" for case, detail in result.failures + result.errors],
                      "detail": stream.getvalue()}, indent=2))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
