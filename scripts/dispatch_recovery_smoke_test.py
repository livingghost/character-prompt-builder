#!/usr/bin/env python3
"""Exercise dispatch preflight and post-send recovery without credentials or a service."""
from __future__ import annotations

import argparse
import copy
import hashlib
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from smoke_fixtures import isolate_home

isolate_home()
import dispatch
import studio


class DispatchRecoveryTests(unittest.TestCase):
    def setUp(self):
        from PIL import Image
        import execution_contract as c
        import input_contracts
        import transport_runware
        from request_validation_fixtures import interface_validation
        from visual_continuity import file_ref

        self.temporary = tempfile.TemporaryDirectory(prefix="cpb-dispatch-recovery-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = studio.init(self.base / "studio", "recovery-test", "Synthetic offline recovery tests")
        self.home = studio.add_character(self.root, "C01", "")
        self.source = self.root / "source.png"
        Image.new("RGB", (8, 8)).save(self.source)
        output = io.BytesIO()
        Image.new("RGB", (16, 16)).save(output, format="PNG")
        self.result_bytes = output.getvalue()
        self.prompt = "A synthetic single-subject study."
        self.request_id = "fixed-fixture-task-uuid"
        self.offering = {
            "service": "fixture", "model_identifier": "fixture-model", "observed_at": "2000-01-01",
            "request_keys": {"prompt": ["positivePrompt"], "negative prompt": ["negativePrompt"],
                             "reference images": ["inputs.referenceImages"], "input image": ["inputImage"]},
        }
        self.record = {"operation_kind": "upscale", "supported_scale_factors": [2],
                       "upscale_settings": {}, "upscaler_class": "deterministic"}
        self.service = {"id": "fixture", "transport": "fixture", "endpoint": {"base_url": "https://example.invalid"},
                        "operations": {"imageInference": {}, "imageUpscale": {}}}
        self.answer = {"data": [{"imageURL": "https://example.invalid/one.png"}]}
        self.entries = [{"url": "https://example.invalid/one.png", "id": "one", "seed": 11},
                        {"url": "https://example.invalid/two.png", "id": "two", "seed": 12}]

        def compile_generation(*args, **kwargs):
            result = transport_runware.compile_request(*args, **kwargs)
            result["request"]["taskUUID"] = self.request_id
            return result

        def compile_upscale(*args, **kwargs):
            result = transport_runware.compile_upscale(*args, **kwargs)
            result["request"]["taskUUID"] = self.request_id
            return result

        self.transport = SimpleNamespace(
            __file__=transport_runware.__file__, RESULT_HOSTS=frozenset({"example.invalid"}),
            compile_request=compile_generation, compile_upscale=compile_upscale,
            upload_bytes=Mock(return_value="uploaded-fixture"),
            send=Mock(return_value=self.answer), rejections=Mock(return_value=[]),
            results=Mock(side_effect=lambda answer: list(self.entries)),
            observation_outcome=Mock(return_value="accepted"),
        )
        validation = interface_validation(
            self.root, target={"service": "fixture", "model_identifier": "fixture-model",
                               "operation": "imageInference"},
            record=self.record, offering=self.offering, service_record=self.service,
            transport=self.transport, reference_mode="authored-rendition",
        )
        reader, _ = input_contracts.capture_validation(validation, root=self.root)
        self.execution_policy = reader.json(validation["execution_policy"])
        basis = self.root / "visual-basis.txt"
        basis.write_text("Synthetic single-subject exploration; no author acceptance is asserted.\n", encoding="utf-8")
        visual = {
            "purpose": "sheet-panel", "basis": file_ref(self.root, basis.name, locator="whole"),
            "subjects": {"subject": {"continuity": "undecided", "character_id": None,
                        "studio_character": "C01", "identity_refs": []}},
        }
        self.reference_rows = [{
            "role": "scene", "source": {"sha256": c.digest(self.source.read_bytes())},
            "authority": {"controls": ["lighting"], "must_not_control": ["identity"]},
        }]
        package = {
            "generation_payload": {}, "production_binding": {"run": "synthetic-boundary-stub"},
            "composition_prompt": self.prompt,
            "visual_continuity": visual, "production_spec": {"subjects": [{"id": "subject"}]},
            "prepared_reference_set": {"transport_mode": "multi-image",
                                      "selected_references": self.reference_rows, "single_board": None},
        }
        input_contracts.attach(package, validation, reader)
        self.package = self.base / "generation-package.json"
        self.package.write_bytes(c.encoded(package))
        upscale_validation = interface_validation(
            self.root, target={"service": "fixture", "model_identifier": "fixture-model",
                               "operation": "imageUpscale"},
            record=self.record, offering=self.offering, service_record=self.service,
            transport=self.transport, reference_mode="authored-rendition",
        )
        self.validation_file = self.root / "upscale-validation.json"
        self.validation_file.write_bytes(c.encoded(upscale_validation))
        self.options = argparse.Namespace(
            package=self.package, service=None, profiles=None, seed=7, count=2, send=True,
            character="C01", slot="base.front", note=None, source=self.source, model="fixture",
            scale=2, settings="{}", guidance=None, production_authorization="synthetic-receipt-stub",
            request_validation_file=self.validation_file,
        )
        self.request = {
            "taskType": "imageInference", "taskUUID": self.request_id, "model": "fixture-model",
            "positivePrompt": self.prompt, "inputs": {"referenceImages": ["uploaded-fixture"]},
            "numberResults": 2, "seed": 7,
        }
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
        # This suite isolates filesystem and transport failures. Request rendering,
        # sealing, validation and visual correspondence use their real contracts.
        # The integrated workflow suites exercise the live authority and claim.
        for target in ("production_binding.validate_live", "production_binding.validate_upscale_live"):
            self.stack.enter_context(patch(target))
        self.results_recorded = self.stack.enter_context(patch("production_workflow.record_dispatch_results"))
        self.stack.enter_context(patch("production_workflow.claim_dispatch",
                                       return_value={"sha256": "c" * 64}))
        self.started = self.stack.enter_context(patch("reservation_lifecycle.begin_step"))
        self.loaded = self.stack.enter_context(patch("transport_contract.load", return_value=self.transport))
        self.patches = {}
        for name, kwargs in {
            "verify": {"side_effect": self.verified},
            "validate_generation_package_carrier_paths": {"return_value": None},
            "resolve_model_record": {"return_value": ("fixture", self.record)},
            "select_offering": {"return_value": self.offering},
            "service_for": {"return_value": ("fixture", self.service, self.transport)},
            "check_request": {}, "validate_generation_parameters": {},
            "model_pack_root": {"return_value": self.base},
            "api_key": {"return_value": "OFFLINE-CREDENTIAL-MUST-NEVER-BE-SAVED"},
            "save": {"side_effect": self.save},
            "open_run": {"return_value": "synthetic-boundary-stub"},
        }.items():
            self.patches[name] = self.stack.enter_context(patch.object(dispatch, name, **kwargs))

    def verified(self, package, *, package_root, project=None, source=None):
        from reference_delivery import bindings
        source = source or self.source
        return {
            "model": "fixture", "bindings": bindings("multi-image", self.reference_rows),
            "execution_policy": self.execution_policy, "review_requirements": [],
            "host_forwarding": {
                "effective_prompt": self.prompt, "parameters": {},
                "selected_transport": {"mode": "separate-field", "rendition": {"negative": ""}},
                "selected_references": [{"role": "scene", "resolved_path": str(source),
                    "media_type": "image/png", "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}],
            },
        }

    def save(self, url, destination, hosts):
        self.assertEqual(hosts, self.transport.RESULT_HOSTS)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self.result_bytes)
        return hashlib.sha256(self.result_bytes).hexdigest()

    def call(self, mode="generation"):
        if mode == "upscale":
            self.entries = self.entries[:1]
        return getattr(dispatch, "dispatch_" + mode)(self.options, self.root)

    def journal(self):
        paths = list((self.root / "runs").glob("*/run.json"))
        self.assertEqual(len(paths), 1)
        return paths[0].parent, json.loads(paths[0].read_text(encoding="utf-8"))

    def assert_no_network(self):
        self.transport.upload_bytes.assert_not_called()
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
        self.assertEqual(json.loads((path / "request.json").read_text(encoding="utf-8")), self.request)
        self.assertEqual(json.loads((path / "answer.json").read_text(encoding="utf-8")), self.answer)
        self.assertEqual([row["seed"] for row in studio.read_iterations(self.home)], [11, 12])
        for file in self.root.rglob("*.json"):
            self.assertNotIn("OFFLINE-CREDENTIAL-MUST-NEVER-BE-SAVED", file.read_text(encoding="utf-8"))

    def test_generation_uploads_reverified_saved_carriers_not_live_author_files(self):
        companion = self.base / "fixture.references"
        companion.mkdir()
        carrier = self.source.read_bytes()
        (companion / "input.png").write_bytes(carrier)
        self.patches["validate_generation_package_carrier_paths"].return_value = companion.name
        self.patches["verify"].side_effect = lambda package, *, package_root, project=None: self.verified(
            package, package_root=package_root, project=project,
            source=package_root / companion.name / "input.png")
        self.assertEqual(self.call(), 0)
        run, _ = self.journal()
        self.assertEqual(self.patches["verify"].call_count, 2)
        self.transport.upload_bytes.assert_called_once_with(carrier, "image/png", self.service,
                                                     "OFFLINE-CREDENTIAL-MUST-NEVER-BE-SAVED")
        self.assertEqual((run / companion.name / "input.png").read_bytes(), carrier)
        sealed = json.loads((run / "request-contract.json").read_text(encoding="utf-8"))
        self.assertEqual(sealed["media"][0]["path"], str(run / companion.name / "input.png"))


    def test_package_changed_during_snapshot_is_rejected_before_upload(self):
        keep = dispatch.RunJournal.keep
        def changed(journal, source, name):
            if name == "package.json":
                source.write_text('{"generation_payload": {}, "changed": true}', encoding="utf-8")
            return keep(journal, source, name)
        with patch.object(dispatch.RunJournal, "keep", changed), self.assertRaisesRegex(ValueError, "changed"):
            self.call()
        self.transport.upload_bytes.assert_not_called()
        self.transport.send.assert_not_called()
        run, document = self.journal()
        self.assertEqual(document["status"], "failed")
        self.assertTrue((run / "package.json").is_file())

    def test_upload_failure_preserves_package_and_does_not_send(self):
        self.transport.upload_bytes.side_effect = OSError("offline upload failure")
        with self.assertRaises(OSError):
            self.call()
        path, journal = self.journal()
        self.assertEqual(journal["failed_at"], "uploading")
        self.assertEqual((path / "package.json").read_bytes(), self.package.read_bytes())
        self.transport.send.assert_not_called()

    def test_a_send_without_an_answer_is_indeterminate_kept_and_never_resent_in_both_modes(self):
        import transport_contract
        failures = {"generation": OSError("offline network failure at 203.0.113.9"),
                    "upscale": transport_contract.Indeterminate("the service answered 502", status=502, body=b"bad gateway")}
        kept = {"generation": {"outcome": "indeterminate", "http_status": None, "body": None,
                               "reason": "the connection ended before a complete answer (OSError)"},
                "upscale": {"outcome": "indeterminate", "http_status": 502, "body": "bad gateway",
                            "reason": "the service answered 502"}}
        for mode, failure in failures.items():
            with self.subTest(mode=mode):
                self.transport.send.reset_mock()
                self.transport.send.side_effect = failure
                said = io.StringIO()
                with contextlib.redirect_stderr(said), patch.object(dispatch, "build_upscale_package",
                                                                    side_effect=self.fake_upscale_builder):
                    self.assertEqual(self.call(mode), 1)
                path = next(folder for folder in (self.root / "runs").iterdir()
                            if (folder / "run.json").is_file()
                            and json.loads((folder / "run.json").read_text(encoding="utf-8"))["operation"] == mode)
                journal = json.loads((path / "run.json").read_text(encoding="utf-8"))
                self.assertEqual(journal["status"], "indeterminate")
                self.assertEqual(json.loads((path / "indeterminate.json").read_text(encoding="utf-8")), kept[mode])
                self.assertTrue((path / "request.json").is_file())
                self.assertFalse((path / "answer.json").exists() or (path / "transport-outcome.json").exists())
                self.assertEqual(self.transport.send.call_count, 1)
                self.assertIn("Nothing is sent again", said.getvalue())
                self.assertNotIn("203.0.113.9", said.getvalue() + (path / "indeterminate.json").read_text(encoding="utf-8"))
        path, journal = next((folder, json.loads((folder / "run.json").read_text(encoding="utf-8")))
                             for folder in (self.root / "runs").iterdir() if (folder / "run.json").is_file()
                             and json.loads((folder / "run.json").read_text(encoding="utf-8"))["operation"] == "generation")
        self.assertEqual(json.loads((path / "request.json").read_text(encoding="utf-8")), self.request)
        self.assertEqual(journal["transport"], "fixture")

    def test_service_refusal_preserves_exact_answer(self):
        self.entries = []
        self.transport.rejections.return_value = [{"reason": "offline refusal"}]
        self.assertEqual(self.call(), 1)
        path, journal = self.journal()
        self.assertEqual(journal["status"], "refused")
        self.assertEqual(journal["refused"], [{"reason": "offline refusal"}])
        self.assertEqual(json.loads((path / "answer.json").read_text(encoding="utf-8")), self.answer)
        self.assertEqual(studio.read_iterations(self.home), [])

    def test_images_beside_a_refusal_are_downloaded_and_recorded(self):
        self.transport.rejections.return_value = [{"reason": "offline partial refusal"}]
        self.assertEqual(self.call(), 1)
        path, journal = self.journal()
        self.assertEqual(journal["refused"], [{"reason": "offline partial refusal"}])
        self.assertEqual((journal["expected"], journal["received"]), (2, 2))
        self.assertEqual(journal["iterations"], ["it-0001", "it-0002"])
        self.assertTrue((path / "result-2.png").is_file())

    def test_empty_result_preserves_answer_in_both_modes(self):
        self.entries = []
        self.assertEqual(self.call(), 1)
        path, journal = self.journal()
        self.assertEqual((journal["status"], journal["expected"], journal["received"]), ("no-results", 2, 0))
        self.assertTrue((path / "answer.json").is_file())
        self.assertEqual(self.call("upscale"), 1)
        for file in (self.root / "runs").glob("*/run.json"):
            self.assertEqual(json.loads(file.read_text(encoding="utf-8"))["status"], "no-results")
        self.results_recorded.assert_not_called()

    def test_count_mismatch_records_every_image_and_no_production_result(self):
        for count in (3, 1):
            with self.subTest(count=count):
                self.options.count = count
                before = len(studio.read_iterations(self.home))
                self.assertEqual(self.call(), 1)
                journals = [json.loads(path.read_text(encoding="utf-8")) for path in (self.root / "runs").glob("*/run.json")]
                journal = next(row for row in journals if row["expected"] == count)
                self.assertEqual((journal["status"], journal["received"]), ("count-mismatch", 2))
                self.assertEqual(len(studio.read_iterations(self.home)), before + 2)
        self.results_recorded.assert_not_called()
        self.assertEqual(self.transport.send.call_count, 2)

    def test_download_failure_preserves_answer_and_result_metadata(self):
        self.patches["save"].side_effect = OSError("offline download failure")
        self.assertEqual(self.call(), 1)
        path, journal = self.journal()
        self.assertEqual(journal["status"], "download-incomplete")
        self.assertEqual([row["index"] for row in journal["failed_downloads"]], [1, 2])
        self.assertTrue((path / "answer.json").is_file())
        self.assertEqual(json.loads((path / "response-1.json").read_text(encoding="utf-8"))["url"], self.entries[0]["url"])
        self.results_recorded.assert_not_called()

    def test_one_failed_download_keeps_the_rest_and_recovery_fetches_it_without_sending(self):
        def second_fails(url, destination, hosts):
            if url.endswith("two.png"):
                raise OSError("offline download failure")
            return self.save(url, destination, hosts)
        self.patches["save"].side_effect = second_fails
        self.assertEqual(self.call(), 1)
        path, journal = self.journal()
        self.assertEqual(journal["status"], "download-incomplete")
        self.assertEqual(journal["iterations"], ["it-0001"])
        self.assertTrue((path / "result-1.png").is_file() and not (path / "result-2.png").exists())
        self.results_recorded.assert_not_called()
        self.patches["save"].side_effect = self.save
        self.assertEqual(dispatch.recover(self.root, "synthetic-boundary-stub", path), 1)
        self.assertEqual(dispatch.recover(self.root, "synthetic-boundary-stub", path), 0)
        self.loaded.assert_called_with("fixture")
        _, journal = self.journal()
        self.assertEqual((journal["status"], journal["iterations"]), ("complete", ["it-0001", "it-0002"]))
        self.assertEqual(len(studio.read_iterations(self.home)), 2)
        self.assertEqual(self.results_recorded.call_count, 2)
        self.assertEqual([p.name for p in self.results_recorded.call_args.args[4]], ["result-1.png", "result-2.png"])
        self.assertEqual((self.transport.send.call_count, self.transport.upload_bytes.call_count), (1, 1))
        with self.assertRaisesRegex(ValueError, "another production run"):
            dispatch.recover(self.root, "01900000-0000-7000-8000-00000000000f", path)

    def test_upscale_download_failure_is_recovered_from_the_saved_answer(self):
        self.patches["save"].side_effect = OSError("offline download failure")
        with patch.object(dispatch, "build_upscale_package", side_effect=self.fake_upscale_builder):
            self.assertEqual(self.call("upscale"), 1)
            path, journal = self.journal()
            self.assertEqual((journal["status"], journal["iterations"]), ("download-incomplete", []))
            self.assertTrue((path / "upscale.references/source.png").is_file())
            self.patches["save"].side_effect = self.save
            self.assertEqual(dispatch.recover(self.root, "synthetic-boundary-stub", path), 1)
        _, journal = self.journal()
        self.assertEqual((journal["status"], len(journal["iterations"])), ("complete", 1))
        self.assertTrue((path / "upscale-package-1.json").is_file())
        self.results_recorded.assert_called_once()
        self.assertEqual((self.transport.send.call_count, self.transport.upload_bytes.call_count), (1, 1))

    def test_recovery_needs_a_dispatch_journal(self):
        empty = self.root / "runs" / "empty"
        empty.mkdir()
        with self.assertRaisesRegex(ValueError, "holds no dispatch journal"):
            dispatch.recover(self.root, "synthetic-boundary-stub", empty)

    def test_recovery_never_sends_when_the_answer_was_not_saved(self):
        self.transport.send.side_effect = TimeoutError("offline network failure")
        self.assertEqual(self.call(), 1)
        path, _ = self.journal()
        with self.assertRaisesRegex(ValueError, "outcome is unknown"):
            dispatch.recover(self.root, "synthetic-boundary-stub", path)
        self.assertEqual(self.transport.send.call_count, 1)
        self.patches["save"].assert_not_called()

    def test_run_journal_names_the_run_and_the_authorized_count(self):
        self.assertEqual(self.call(), 0)
        _, journal = self.journal()
        self.assertEqual((journal["production_run"], journal["expected"], journal["received"], journal["refused"],
                          journal["failed_downloads"]), ("synthetic-boundary-stub", 2, 2, [], []))
        self.results_recorded.assert_called_once()

    def test_preview_prints_plain_lines_before_the_request(self):
        self.options.send = False
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(self.call(), 0)
        text = output.getvalue()
        head, _, body = text.partition("request (sha256 ")
        for line in ("model: fixture as fixture-model", "service: fixture at https://example.invalid", "outputs: 2",
                     "negative prompt: none authored", "cost: unknown", "production run: synthetic-boundary-stub",
                     "shown, not sent"):
            self.assertIn(line, head)
        request = json.loads(body.partition("\n")[2])
        self.assertEqual(request["positivePrompt"], self.prompt)
        self.assertNotIn("request_trace", text)
        self.assertNotIn("base64", text)
        self.assertLess(len(head.splitlines()), 12)

    def test_preview_says_plainly_when_the_authored_negative_is_not_sent(self):
        verified = {"negative_prompt": "blurry",
                    "host_forwarding": {"selected_transport": {"mode": "integrated-critical"}}}
        unnegated = {**self.offering, "request_keys": {"prompt": ["positivePrompt"]}}
        self.assertEqual(dispatch.negative_line(verified, {"layout": {"negative_text": None}}, unnegated),
                         "not sent; this target has no negative field, so the authored negative stays in the package")
        self.assertEqual(dispatch.negative_line(verified, {"layout": {"negative_text": None}}, self.offering),
                         "not sent under the record's integrated-critical negative transport; "
                         "the authored negative stays in the package")
        self.assertEqual(dispatch.negative_line(verified, {"layout": {"negative_text": ["negativePrompt"]}}, self.offering),
                         "sent on negativePrompt")
        self.assertEqual(dispatch.negative_line({}, {"layout": {"negative_text": None}}, self.offering), "none authored")

    def test_inline_results_are_decoded_without_a_download_and_recovered_the_same_way(self):
        import base64
        encoded = base64.b64encode(self.result_bytes).decode("ascii")
        self.entries = [{"data": encoded, "id": "one", "seed": 11}, {"data": encoded, "id": "two", "seed": 12}]
        real = dispatch.inline_image
        calls = []

        def second_fails(data):
            calls.append(data)
            if len(calls) == 2:
                raise OSError("offline disk failure")
            return real(data)

        with patch.object(dispatch, "inline_image", side_effect=second_fails):
            self.assertEqual(self.call(), 1)
        path, journal = self.journal()
        self.assertEqual((journal["status"], journal["iterations"]), ("download-incomplete", ["it-0001"]))
        self.assertEqual((path / "result-1.png").read_bytes(), self.result_bytes)
        self.assertEqual(dispatch.recover(self.root, "synthetic-boundary-stub", path), 0)
        _, journal = self.journal()
        self.assertEqual((journal["status"], journal["iterations"]), ("complete", ["it-0001", "it-0002"]))
        self.assertEqual((path / "result-2.png").read_bytes(), self.result_bytes)
        self.assertIsNone(json.loads((path / "response-2.json").read_text(encoding="utf-8"))["url"])
        self.patches["save"].assert_not_called()
        self.assertEqual([row["seed"] for row in studio.read_iterations(self.home)], [11, 12])
        self.assertEqual((self.transport.send.call_count, self.transport.upload_bytes.call_count), (1, 1))

    def test_an_inline_answer_is_kept_once_and_each_response_names_its_place_in_it(self):
        import base64
        import validate_studio
        encoded = base64.b64encode(self.result_bytes).decode("ascii")
        self.answer["data"] = [{"imageBase64Data": encoded, "seed": 11}, {"imageBase64Data": encoded, "seed": 12}]
        self.entries = [{"data": encoded, "id": "one", "seed": 11}, {"data": encoded, "id": "two", "seed": 12}]
        self.assertEqual(self.call(), 0)
        path, _ = self.journal()
        answer_sha256 = hashlib.sha256((path / "answer.json").read_bytes()).hexdigest()
        for index, name in ((1, "one"), (2, "two")):
            named = json.loads((path / f"response-{index}.json").read_text(encoding="utf-8"))
            self.assertEqual({key: value for key, value in named.items() if key != "at"},
                             {"answer_sha256": answer_sha256, "index": index, "seed": 10 + index, "id": name, "url": None})
        holding = lambda folder: sorted(p.name for p in folder.rglob("*.json") if encoded in p.read_text(encoding="utf-8"))
        self.assertEqual(holding(path), ["answer.json"])
        rows = studio.read_iterations(self.home)
        self.assertEqual(rows[0]["answer"], rows[1]["answer"])
        self.assertEqual(rows[0]["answer"]["sha256"], answer_sha256)
        self.assertEqual(holding(self.home), ["answer.json"])
        self.assertEqual(studio.recipe(self.root, "C01", "base.front", iteration="it-0002")["evidence"]["answer"]["sha256"],
                         answer_sha256)
        self.assertEqual([error for error in validate_studio.validate(self.root) if "answer" in error or "response" in error], [])

    def test_recovery_refuses_a_response_that_names_another_answer(self):
        import base64
        encoded = base64.b64encode(self.result_bytes).decode("ascii")
        self.entries = [{"data": encoded, "id": "one", "seed": 11}, {"data": encoded, "id": "two", "seed": 12}]
        real = dispatch.inline_image
        with patch.object(dispatch, "inline_image", side_effect=[real(encoded), OSError("offline disk failure")]):
            self.assertEqual(self.call(), 1)
        path, _ = self.journal()
        response = path / "response-2.json"
        response.write_text(json.dumps({**json.loads(response.read_text(encoding="utf-8")), "answer_sha256": "0" * 64}), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "names another answer"):
            dispatch.recover(self.root, "synthetic-boundary-stub", path)
        self.assertFalse((path / "result-2.png").exists())
        self.assertEqual(len(studio.read_iterations(self.home)), 1)

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
        self.assertEqual((path / "result-1.png").read_bytes(), self.result_bytes)
        self.assertTrue((path / companion.name / "reference.svg").is_file())
        # Re-record the saved files locally, with no second service request.
        row = studio.iterate(self.root, "C01", "base.front", path / "result-1.png", package=path / "package.json",
                             request=path / "request.json", response=path / "response-1.json", note="recovered",
                             package_companion=path / companion.name, answer=path / "answer.json")
        self.assertEqual(row["seed"], 11)
        self.assertEqual(row["answer"]["sha256"], hashlib.sha256((path / "answer.json").read_bytes()).hexdigest())
        other = self.base / "other-answer.json"
        other.write_text('{"data": []}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "does not name the answer"):
            studio.iterate(self.root, "C01", "base.front", path / "result-1.png", package=path / "package.json",
                           request=path / "request.json", response=path / "response-1.json", note="recovered",
                           answer=other)
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
            package = json.loads(package_path.read_text(encoding="utf-8"))
            self.assertTrue((package_path.parent / package["source"]).is_file())
            self.assertTrue((package_path.parent / package["output"]).is_file())

    def test_repeated_task_uuid_never_overwrites_previous_run(self):
        self.assertEqual(self.call(), 0)
        self.assertEqual(self.call(), 0)
        self.assertEqual(len(list((self.root / "runs").glob("*/request.json"))), 2)
        self.assertEqual(len(studio.read_iterations(self.home)), 4)


class ResumeOffersDownload(unittest.TestCase):
    """A claimed run whose answer was saved offers recover-recording, which sends nothing again."""

    def test_saved_answer_offers_recover_recording(self):
        import production_workflow as w
        from production_resume_smoke_test import ResumeFixture, RUN

        class Fixture(ResumeFixture, unittest.TestCase):
            def runTest(self):
                pass

        fixture = Fixture()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.start()
        offered = lambda: [a["operation"] for a in w.status(fixture.root, RUN)["next_actions"]]
        self.assertNotIn("recover-recording", offered())
        journal = fixture.root / "runs" / "synthetic-journal"
        journal.mkdir(parents=True)
        (journal / "answer.json").write_text('{"data": []}', encoding="utf-8")
        self.assertIn("recover-recording", offered())


# A second service, as its author would add it: a transport module written
# against scripts/transport_contract.py, named by the service record rather than
# by the service's key. The model and the operation travel in the address, the
# text on the offering's keys, and images come back inline as base64. It sends
# through the contract's post() to a loopback service the test starts.
SECOND_TRANSPORT = '''"""A synthetic second service for the dispatch tests; it reaches only the test's loopback service."""
import json

from model_contract import NEGATIVE_ROLE, PROMPT_ROLE, required_request_key
from request_contract import RequestWriter, path_parts
from transport_contract import address, post

OPERATIONS = {"generation": "text-to-image"}
RESULT_HOSTS = frozenset()


def endpoint(service):
    return address(service["endpoint"]["base_url"])


def compile_request(verified, offering, service, media_ids=None, seed=None, count=1):
    forwarding = verified["host_forwarding"]
    writer = RequestWriter()
    source = [{"kind": "offering", "service": offering["service"], "model_identifier": offering["model_identifier"]}]

    def write(path, value, kind, transform):
        writer.write(path, value, source_kind=kind, source_refs=source, transform_id=transform)

    prompt = path_parts(required_request_key(offering, PROMPT_ROLE))
    write(prompt, forwarding["effective_prompt"], "authored", "selected-rendition")
    layout = {"model": None, "operation": None, "primary_text": prompt, "negative_text": None,
              "output_count": ["num_images"], "fixed_output_count": None, "seed": None, "media": [],
              "management": [], "content": [{"id": "prompt", "field": prompt}],
              "fields": [{"id": "prompt", "field": prompt, "kind": "content"},
                         {"id": "count", "field": ["num_images"], "kind": "parameter"}]}
    selected = forwarding["selected_transport"]
    negative = selected["rendition"].get("negative") or ""
    if selected["mode"] in {"separate-field", "native-subset"} and negative:
        field = path_parts(required_request_key(offering, NEGATIVE_ROLE))
        write(field, negative, "authored", "selected-negative-channel")
        layout["negative_text"] = field
        layout["content"].append({"id": "negative", "field": field})
        layout["fields"].append({"id": "negative", "field": field, "kind": "content"})
    for name, value in sorted((forwarding.get("parameters") or {}).items()):
        write(path_parts(name), value, "model-setting", "selected-parameter")
        layout["fields"].append({"id": "parameter:" + name, "field": path_parts(name), "kind": "parameter"})
    write(["num_images"], count, "model-setting", "explicit-output-count")
    if seed is not None:
        write(["seed"], seed, "model-setting", "explicit-seed")
        layout["seed"] = ["seed"]
        layout["fields"].append({"id": "seed", "field": ["seed"], "kind": "parameter"})
    return {"request": writer.request, "layout": layout, "request_trace": writer.trace}


def added_parameters(offering, seed=None, count=1):
    return {"num_images": count, **({"seed": seed} if seed is not None else {})}


def upload_bytes(data, media_type, service, key):
    raise ValueError("the fixture service takes no media")


def send(request, service, key):
    status, body = post(endpoint(service), json.dumps(request).encode("utf-8"),
                        {"Content-Type": "application/json", "Authorization": "Key " + key})
    answer = json.loads(body.decode("utf-8"))
    return answer if status == 200 else {"errors": [{"status": status, **answer}]}


def rejections(answer):
    return list(answer.get("errors") or [])


def results(answer):
    return [{"data": item["b64"], "seed": item.get("seed"), "id": item.get("id")} for item in answer.get("images") or []]


def observation_outcome(answer):
    return "rejected" if rejections(answer) else "accepted" if results(answer) else "indeterminate"
'''


class SecondServiceTests(unittest.TestCase):
    """A service that is not Runware is data plus the transport module its record names, with no Runware code on the path."""

    @classmethod
    def setUpClass(cls):
        import feature_workflow_smoke_test as generation_fixture
        cls.fixture = generation_fixture
        generation_fixture.FeatureWorkflowTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        cls.fixture.FeatureWorkflowTests.tearDownClass.__func__(cls)
        cls.fixture.catalog_cli.configure_pack_runtime(None)

    def setUp(self):
        from dispatch_smoke_test import LoopbackService
        self.fixture.FeatureWorkflowTests.setUp(self)
        self.loopback = LoopbackService()
        self.addCleanup(self.loopback.__exit__)

    def prepare(self):
        """The records, the bound package and its authorization for one send of two images through the second service."""
        import importlib
        import input_contracts
        import production_fixtures
        import production_workflow as workflow
        import request_renderer
        import execution_contract as c
        from build_generation_payload import generation_input_sha256
        from model_contract import validate_model_record
        from prepare_generation_references import resolve_model_record
        from request_validation_fixtures import interface_validation
        from verify_generation_payload import verify

        folder = self.work / "second-service"
        folder.mkdir()
        (folder / "transport_loopback_fixture.py").write_text(SECOND_TRANSPORT, encoding="utf-8")
        sys.path.insert(0, str(folder))
        self.addCleanup(sys.path.remove, str(folder))
        self.addCleanup(sys.modules.pop, "transport_loopback_fixture", None)
        transport = importlib.import_module("transport_loopback_fixture")

        # The service record, the offering with its keys, and the service's observed schema: data only.
        service = {"label": "Second fixture service", "observed_at": "2026-09-23", "source": "synthetic fixture",
                   "transport": "loopback_fixture",
                   "endpoint": {"base_url": self.loopback.url + "/v1/second-model/text-to-image", "method": "POST"},
                   "auth": {"env_var": "SECOND_FIXTURE_KEY"}, "operations": {"text-to-image": {}}}
        profiles = self.work / "services.json"
        profiles.write_text(json.dumps({"services": {"second-fixture": service}}), encoding="utf-8")
        snapshot = "resources/observed-schemas/second-model.second-fixture.json"
        self.schema_pack = self.work / "second-pack"
        (self.schema_pack / snapshot).parent.mkdir(parents=True)
        (self.schema_pack / snapshot).write_text(json.dumps({"observed_at": "2026-09-23", "schema": {
            "type": "object", "required": ["prompt"], "additionalProperties": False,
            "properties": {"prompt": {"type": "string", "minLength": 1}, "negative_prompt": {"type": "string"},
                           "num_images": {"type": "integer", "minimum": 1, "maximum": 4}, "seed": {"type": "integer"},
                           "size": {"enum": ["1024x1024"]}, "quality": {"enum": ["high"]}}}}), encoding="utf-8")
        offering = {"service": "second-fixture", "model_identifier": "vendor/second-model", "observed_at": "2026-09-23",
                    "request_keys": {"prompt": ["prompt"], "negative prompt": ["negative_prompt"]},
                    "constraints": {}, "schema_snapshot": snapshot}
        self.production_run = production_fixtures.prepare_dispatch(self.root, self.fixture.PROMPT)
        package = production_fixtures.bind_package(self.root, self.production_run, self.package)
        _, record = resolve_model_record(package["model"])
        self.record = copy.deepcopy(record)
        self.record["offerings"] = [offering]
        self.assertEqual(validate_model_record(self.record), [])
        validation = interface_validation(self.root, target={"service": "second-fixture", "model_identifier": "vendor/second-model",
            "operation": "text-to-image"}, record=self.record, offering=offering, service_record=service,
            transport=transport, reference_mode="prompt-prefix")
        reader, _ = input_contracts.capture_validation(validation, root=self.root)
        reader.basis(package["visual_continuity"]["basis"])
        input_contracts.attach(package, validation, reader)
        for key in ("request_validation_sha256", "input_snapshots_sha256"):
            package["generation_contract"][key] = package[key]
        package["generation_input_sha256"] = generation_input_sha256(package)
        package["generation_contract"]["generation_input_sha256"] = package["generation_input_sha256"]
        path = self.root / "bound.json"
        path.write_bytes(c.encoded(package))
        self.model = package["model"]
        rendered = request_renderer.generation(package, verify(package, package_root=self.root, project=self.root),
                                               self.record, offering, service, transport, seed=7, count=2)
        authorization = production_fixtures.grant(self.root, self.production_run, workflow.submission_intent(
            package, rendered=rendered, seed=7, count=2, offering=offering, service=service))
        return argparse.Namespace(package=path, service=None, profiles=str(profiles), seed=7, count=2, send=False,
                                  character="C01", slot="base.front", note="Synthetic second service.",
                                  production_authorization=authorization), rendered

    @contextlib.contextmanager
    def only_the_loopback_service(self):
        """No Runware code, no connection but to the loopback service, and no download of an inline image."""
        import socket
        connect = socket.create_connection
        port = self.loopback.server.server_address[1]

        def loopback_only(address, *args, **kwargs):
            if tuple(address[:2]) != ("127.0.0.1", port):
                raise AssertionError(f"the second-service dispatch connected to {address}")
            return connect(address, *args, **kwargs)

        with patch.dict(sys.modules, {"transport_runware": None}), \
                patch.dict(os.environ, {"SECOND_FIXTURE_KEY": "SYNTHETIC-SECOND-KEY"}), \
                patch.object(socket, "create_connection", loopback_only), \
                patch.object(dispatch, "resolve_model_record", return_value=(self.model, self.record)), \
                patch.object(dispatch, "model_pack_root", return_value=self.schema_pack), \
                patch.object(dispatch, "save", side_effect=AssertionError("an inline image was downloaded")):
            yield

    def test_preview_send_and_inline_recovery_through_a_second_service(self):
        import base64
        import production_workflow as workflow
        from PIL import Image
        from generation_payload_smoke_test import NEGATIVE

        options, rendered = self.prepare()
        output = io.BytesIO()
        Image.new("RGB", (24, 24), "white").save(output, format="PNG")
        image = output.getvalue()
        self.loopback.reply = (200, {"Content-Type": "application/json"}, json.dumps({"images": [
            {"b64": base64.b64encode(image).decode("ascii"), "seed": 101, "id": "a"},
            {"b64": base64.b64encode(image).decode("ascii"), "seed": 102, "id": "b"}]}).encode("utf-8"))
        real = dispatch.inline_image
        calls = []

        def second_fails(data):
            calls.append(data)
            if len(calls) == 2:
                raise OSError("offline disk failure")
            return real(data)

        shown = io.StringIO()
        with self.only_the_loopback_service():
            with contextlib.redirect_stdout(shown):
                self.assertEqual(dispatch.dispatch_generation(options, self.root), 0)
            head, _, body = shown.getvalue().partition("request (sha256 ")
            previewed = json.loads(body.partition("\n")[2])
            self.assertIn(f"service: second-fixture at {self.loopback.url}/v1/second-model/text-to-image", head)
            self.assertIn("negative prompt: sent on negative_prompt", head)
            self.assertEqual(previewed, {"prompt": rendered["request"]["prompt"], "negative_prompt": NEGATIVE,
                                         "num_images": 2, "seed": 7, "size": "1024x1024", "quality": "high"})
            self.assertEqual(self.loopback.received, [])
            options.send = True
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()), \
                    patch.object(dispatch, "inline_image", side_effect=second_fails):
                self.assertEqual(dispatch.dispatch_generation(options, self.root), 1)
            with contextlib.redirect_stdout(io.StringIO()):
                recovered = workflow.recover_recording(self.root, self.production_run)
        self.assertEqual([(row["path"], json.loads(row["body"])) for row in self.loopback.received],
                         [("/v1/second-model/text-to-image", previewed)])
        self.assertEqual((len(recovered["iterations"]), recovered["network_calls"]), (2, 0))
        journal = next((self.root / "runs").glob("*/run.json")).parent
        self.assertEqual({key: json.loads((journal / "run.json").read_text(encoding="utf-8"))[key]
                          for key in ("status", "service", "transport")},
                         {"status": "complete", "service": "second-fixture", "transport": "loopback_fixture"})
        self.assertEqual([(journal / f"result-{index}.png").read_bytes() for index in (1, 2)], [image, image])
        rows = studio.read_iterations(self.home)
        self.assertEqual([row["seed"] for row in rows], [101, 102])
        self.assertEqual(rows[0]["request_layout"]["negative_text"], ["negative_prompt"])
        recipe = studio.recipe(self.root, "C01", "base.front", iteration=rows[0]["iteration_id"])
        self.assertNotIn("seed", recipe["settings"])
        self.assertEqual(recipe["settings"]["prompt"], previewed["prompt"])
        for file in self.root.rglob("*.json"):
            self.assertNotIn("SYNTHETIC-SECOND-KEY", file.read_text(encoding="utf-8"))

    def unanswered(self, reply):
        """Send once to a loopback service that gives `reply`; the run's saved evidence and what was said."""
        import production_workflow as workflow
        options, _ = self.prepare()
        options.send = True
        self.loopback.reply = reply
        said = io.StringIO()
        with self.only_the_loopback_service():
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(said):
                self.assertEqual(dispatch.dispatch_generation(options, self.root), 1)
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(ValueError, "outcome is unknown"):
                workflow.recover_recording(self.root, self.production_run)
        self.assertEqual(len(self.loopback.received), 1)
        journal = next((self.root / "runs").glob("*/run.json")).parent
        self.assertEqual(json.loads((journal / "run.json").read_text(encoding="utf-8"))["status"], "indeterminate")
        self.assertFalse((journal / "answer.json").exists())
        resume = workflow.status(self.root, self.production_run)
        self.assertEqual(resume["next"], "recover-recording-or-resolve-remote-status")
        self.assertNotIn("recover-recording", [action["operation"] for action in resume["next_actions"]])
        self.assertEqual(studio.read_iterations(self.home), [])
        self.assertIn("Nothing is sent again", said.getvalue())
        return json.loads((journal / "indeterminate.json").read_text(encoding="utf-8"))

    def test_a_5xx_answer_is_indeterminate_and_sent_once(self):
        self.assertEqual(self.unanswered((503, {}, b"upstream busy")),
                         {"outcome": "indeterminate", "reason": "the service answered 503", "http_status": 503,
                          "body": "upstream busy"})

    def test_a_dropped_connection_is_indeterminate_and_sent_once(self):
        kept = self.unanswered("drop")
        self.assertEqual((kept["http_status"], kept["body"]), (None, None))
        self.assertTrue(kept["reason"].startswith("the connection ended before a complete answer"), kept)


def main():
    stream = io.StringIO()
    suite = unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(case)
                                for case in (DispatchRecoveryTests, ResumeOffersDownload, SecondServiceTests)])
    result = unittest.TextTestRunner(stream=stream).run(suite)
    print(json.dumps({"ok": result.wasSuccessful(), "checks": result.testsRun,
                      "failures": len(result.failures), "error_count": len(result.errors),
                      "errors": [f"{case.id()}: {detail}" for case, detail in result.failures + result.errors],
                      "detail": stream.getvalue()}, indent=2))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
