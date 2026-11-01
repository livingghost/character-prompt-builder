#!/usr/bin/env python3
"""Exercise private Studio JSON, explicit sources and credential recovery locally."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import operation_context as operations
from production_diagnostics import ProductionError
import service_auth as auth
import private_state
import studio
import validate_studio


class StudioAuthenticationTests(unittest.TestCase):

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="cpb-auth-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.user = self.base / "working-directory"
        self.user.mkdir()
        self.enterContext(mock.patch.dict(os.environ, {}, clear=True))
        self.home = self.base / "user-home"
        self.home.mkdir()
        self.enterContext(mock.patch.object(Path, "home", return_value=self.home))
        self.root = studio.init(self.base / "studio", "auth-studio", "Synthetic authentication study")
        self.variable = "CPB_SYNTHETIC_API_KEY"
        self.service = "synthetic-service"
        self.value = "synthetic-private-value-for-studio-one"

    def other_studio(self, name="other-studio"):
        return studio.init(self.base / name, name, "Synthetic authentication owner")

    def config(self, root=None):
        return (root or self.root) / auth.CONFIG_FILE

    def document(self, root=None):
        return json.loads(self.config(root).read_text(encoding="utf-8-sig"))

    def write_document(self, document, root=None):
        path = self.config(root)
        path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        if os.name != "nt":
            path.chmod(0o600)
        return path.read_bytes()

    def invoke(self, *args, stdin="", terminal=False):
        output, errors = io.StringIO(), io.StringIO()
        input_stream = io.StringIO(stdin)
        input_stream.isatty = lambda: terminal
        with mock.patch.object(sys, "argv", [str(ROOT / "scripts" / "studio.py"), *args]), \
                mock.patch.object(sys, "stdin", input_stream), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            code = operations.run_cli(lambda: studio.main(list(args)))
        return code, output.getvalue(), errors.getvalue()

    def run_action(self, action):
        code, output, errors = self.invoke(*action["argv"][2:])
        self.assertEqual(code, 0, errors)
        return json.loads(output)

    def run_concurrently(self, *actions):
        start = threading.Barrier(len(actions) + 1)
        failures, results = [], []
        def perform(action):
            try:
                start.wait(timeout=10)
                results.append(action())
            except BaseException as exc:
                failures.append(type(exc).__name__)
        threads = [threading.Thread(target=perform, args=(action,), daemon=True) for action in actions]
        for thread in threads:
            thread.start()
        start.wait(timeout=10)
        for thread in threads:
            thread.join(timeout=20)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertFalse(failures)
        self.assertEqual(len(results), len(actions))
        return results

    def test_ignore_rules_exist_before_private_temporary_file_creation(self):
        original = auth.tempfile.mkstemp
        calls = []
        def checked_temporary(*args, **kwargs):
            self.assertEqual((self.root / '.gitignore').read_bytes(), private_state.PRIVATE_IGNORE_BLOCK)
            calls.append(True)
            return original(*args, **kwargs)
        with mock.patch.object(auth.tempfile, 'mkstemp', side_effect=checked_temporary):
            self.set_value()
        self.assertEqual(calls, [True])
        self.assertEqual(auth.resolve(self.root, self.service).value, self.value)

    def test_prepare_preserves_ignore_bytes_and_repeated_preparation_is_idempotent(self):
        path = self.root / '.gitignore'
        authored = b'# Existing owner rules\r\ngenerated/\r\n!credentials.json'
        path.write_bytes(authored)
        if os.name != 'nt':
            path.chmod(0o640)
        prepared = auth.prepare(self.root, self.service)
        expected = authored + b'\n' + private_state.PRIVATE_IGNORE_BLOCK
        self.assertEqual(path.read_bytes(), expected)
        credentials = self.config().read_bytes()
        repeated = auth.prepare(self.root, self.service)
        self.assertEqual(path.read_bytes(), expected)
        self.assertEqual(self.config().read_bytes(), credentials)
        self.assertEqual(prepared['selection'], repeated['selection'])
        self.set_value()
        self.assertEqual(path.read_bytes(), expected)
        if os.name != 'nt':
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o640)

    def test_prepare_restores_final_rule_priority_without_rewriting_existing_credentials(self):
        self.set_value()
        path = self.root / '.gitignore'
        credentials = self.config().read_bytes()
        original = path.read_bytes() + b'!credentials.json\n!.pending-auth-*\n'
        path.write_bytes(original)
        auth.prepare(self.root, self.service)
        self.assertEqual(path.read_bytes(), original + private_state.PRIVATE_IGNORE_BLOCK)
        self.assertEqual(self.config().read_bytes(), credentials)
        once = path.read_bytes()
        auth.prepare(self.root, self.service)
        self.assertEqual(path.read_bytes(), once)

    def test_ignore_append_failure_keeps_user_bytes_and_publishes_no_private_file(self):
        path = self.root / '.gitignore'
        before = b'# Retain these owner rules\noutput/\n'
        path.write_bytes(before)
        with mock.patch.object(private_state.os, 'write', side_effect=PermissionError('synthetic append refusal')):
            with self.assertRaises(ProductionError) as caught:
                self.set_value()
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse(self.config().exists())
        self.assertFalse(list(self.root.glob('.pending-auth-*')))
        self.assertNotIn(self.value, str(caught.exception))

    def test_redirected_ignore_is_rejected_before_private_publication(self):
        path, target = self.root / '.gitignore', self.base / 'owner-ignore'
        before = b'# Existing ignore target\noutput/\n'
        target.write_bytes(before)
        def assert_refused():
            with self.assertRaises(ProductionError):
                self.set_value()
            self.assertFalse(self.config().exists())
            self.assertFalse(list(self.root.glob('.pending-auth-*')))
            self.assertEqual(target.read_bytes(), before)
        try:
            path.symlink_to(target)
        except OSError:
            path.write_bytes(before)
        else:
            try:
                with self.subTest(filesystem='native symlink'):
                    assert_refused()
            finally:
                path.unlink()
                path.write_bytes(before)
        for method in ('is_symlink', 'is_junction'):
            original = getattr(Path, method)
            def redirected(candidate):
                return True if candidate == path else original(candidate)
            with self.subTest(filesystem='synthetic ' + method), \
                    mock.patch.object(Path, method, autospec=True, side_effect=redirected):
                assert_refused()
                self.assertEqual(path.read_bytes(), before)

    def test_hardlinked_ignore_is_rejected_before_private_publication(self):
        path, linked = self.root / '.gitignore', self.base / 'linked-ignore'
        before = b'# Existing ignore data\noutput/\n'
        path.write_bytes(before)
        def assert_refused():
            with self.assertRaises(ProductionError):
                self.set_value()
            self.assertFalse(self.config().exists())
            self.assertFalse(list(self.root.glob('.pending-auth-*')))
            self.assertEqual(path.read_bytes(), before)
        try:
            os.link(path, linked)
        except OSError:
            pass
        else:
            try:
                with self.subTest(filesystem='native hardlink'):
                    assert_refused()
                    self.assertEqual(linked.read_bytes(), before)
            finally:
                linked.unlink()
        original_lstat = Path.lstat
        def linked_info(candidate):
            info = original_lstat(candidate)
            if candidate == path:
                fields = list(info)
                fields[3] = 2
                return os.stat_result(fields)
            return info
        with self.subTest(filesystem='synthetic hardlink metadata'), \
                mock.patch.object(Path, 'lstat', autospec=True, side_effect=linked_info):
            assert_refused()

    def test_cli_prepare_user_save_and_status_resolve_without_environment_setup(self):
        code, output, errors = self.invoke("credentials", "prepare", self.service, "--studio", str(self.root))
        self.assertEqual(code, 0, errors)
        prepared = json.loads(output)
        self.assertTrue(prepared["ok"])
        self.assertFalse(prepared["available"])
        self.assertEqual(prepared["operation"], "created")
        entry = prepared["input"]
        self.assertEqual(entry["path"], str(self.config()))
        self.assertEqual(entry["json_pointer"], "/" + self.service + "/api_key")
        self.assertTrue(entry["instructions"])
        self.assertEqual(self.document(), {self.service: {"api_key": ""}})
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(self.config().stat().st_mode), 0o600)
        action = prepared["next_action"]
        self.assertEqual(action["command"], "credentials-status")
        self.assertTrue(action["requires_author_input"])
        self.assertEqual(action["input"], entry)
        code, pending, errors = self.invoke(*action["argv"][2:])
        self.assertEqual(code, 3, errors)
        self.assertFalse(json.loads(pending)["services"][0]["available"])
        raw = self.enter_key(entry, self.value)
        code, ready, errors = self.invoke(*action["argv"][2:])
        self.assertEqual(code, 0, errors)
        self.assertTrue(json.loads(ready)["services"][0]["available"])
        self.assertEqual(auth.resolve(self.root, self.service).value, self.value)
        logs = "\n".join(p.read_text(encoding="utf-8") for p in (self.root / "logs").rglob("*") if p.is_file())
        self.assertNotIn(self.value, output + pending + ready + errors + logs)
        self.assertNotIn(hashlib.sha256(raw).hexdigest(), logs)
        self.assertNotIn(hashlib.sha256(self.value.encode()).hexdigest(), logs)

    def test_repeated_prepare_preserves_pending_and_entered_document_bytes(self):
        first = auth.prepare(self.root, self.service)
        pending_bytes = self.config().read_bytes()
        repeated = auth.prepare(self.root, self.service)
        self.assertEqual(repeated["selection"], first["selection"])
        self.assertEqual(repeated["operation"], "retained")
        self.assertFalse(repeated["available"])
        self.assertEqual(self.config().read_bytes(), pending_bytes)
        document = self.document()
        document[self.service]["api_key"] = self.value
        raw = b"\xef\xbb\xbf" + json.dumps(document, indent=4).replace("\n", "\r\n").encode() + b"\r\n"
        self.config().write_bytes(raw)
        ready = auth.prepare(self.root, self.service)
        self.assertEqual(ready["selection"], first["selection"])
        self.assertEqual(ready["operation"], "retained")
        self.assertTrue(ready["available"])
        self.assertIsNone(ready["next_action"])
        self.assertEqual(self.config().read_bytes(), raw)
        self.assertNotIn(self.value, json.dumps(ready))

    def test_prepare_preserves_an_explicit_environment_source_and_creates_no_value(self):
        selected = auth.prepare(self.root, self.service, environment=self.variable)["selection"]
        before = self.config().read_bytes()
        for value in (None, "synthetic-environment-account"):
            if value is not None:
                os.environ[self.variable] = value
            report = auth.prepare(self.root, self.service)
            self.assertTrue(report["ok"])
            self.assertEqual(report["selection"], selected)
            self.assertEqual(report["operation"], "retained")
            self.assertEqual(report["available"], value is not None)
            self.assertEqual(self.config().read_bytes(), before)
            self.assertEqual(self.document(), {self.service: {"api_key_env": self.variable}})
            self.assertIsNone(report["input"])
            if value is not None:
                self.assertNotIn(value, json.dumps(report) + self.config().read_text(encoding="utf-8"))

    def test_json_bom_crlf_and_value_whitespace_resolve_without_rewriting(self):
        auth.prepare(self.root, self.service)
        for value in (self.value, "  " + self.value + "  ", self.value + "\r\n"):
            with self.subTest(padding=len(value) - len(self.value)):
                document = self.document()
                document[self.service]["api_key"] = value
                raw = b"\xef\xbb\xbf" + json.dumps(document, indent=2).replace("\n", "\r\n").encode() + b"\r\n"
                self.config().write_bytes(raw)
                self.assertTrue(auth.status(self.root, self.service)["ok"])
                self.assertEqual(auth.resolve(self.root, self.service).value, value)
                self.assertEqual(self.config().read_bytes(), raw)

    def test_empty_key_waits_at_its_json_pointer(self):
        first = auth.prepare(self.root, self.service)
        raw = self.enter_key(first["input"], "")
        pending = auth.prepare(self.root, self.service)
        self.assertTrue(pending["ok"])
        self.assertFalse(pending["available"])
        self.assertEqual(pending["operation"], "retained")
        self.assertEqual(self.config().read_bytes(), raw)
        action = auth.inspect(self.root, self.service)["diagnostics"][0]["next_action"]
        self.assertEqual(action["command"], "credentials-status")
        self.assertTrue(action["requires_author_input"])
        self.assertEqual(action["input"], pending["input"])
        self.assertEqual(action["input"]["json_pointer"], "/" + self.service + "/api_key")

    def test_invalid_selected_values_preserve_data_and_report_the_exact_input_entry(self):
        first = self.set_value()
        values = (None, 17, {"unexpected": "synthetic-invalid-value"})
        for value in values:
            with self.subTest(kind=type(value).__name__):
                raw = self.edit_key(self.service, value)
                report = auth.inspect(self.root, self.service)
                self.assertFalse(report["available"])
                self.assertEqual(report["selection"], first["selection"])
                action = report["diagnostics"][0]["next_action"]
                self.assertEqual(action["command"], "credentials-status")
                self.assertEqual(action["input"]["json_pointer"], "/" + self.service + "/api_key")
                prepared = auth.prepare(self.root, self.service)
                self.assertTrue(prepared["ok"])
                self.assertFalse(prepared["available"])
                self.assertEqual(prepared["selection"], first["selection"])
                self.assertEqual(self.config().read_bytes(), raw)
                self.assertNotIn("synthetic-invalid-value", json.dumps(report) + json.dumps(prepared))
                if isinstance(value, str):
                    self.assertNotIn(value, json.dumps(report) + json.dumps(prepared))

    def test_unrelated_invalid_entry_does_not_block_valid_selection_or_management(self):
        selected = self.set_value()["selection"]
        self.edit_key("other-service", {"unexpected": "synthetic-malformed-unrelated-value"})
        self.assertEqual(auth.resolve(self.root, self.service).selection, selected)
        self.assertTrue(auth.prepare(self.root, self.service)["available"])
        self.set_value("synthetic-third-key", service="third-service")
        self.assertEqual(self.document()["other-service"]["api_key"],
                         {"unexpected": "synthetic-malformed-unrelated-value"})
        self.assertEqual(auth.resolve(self.root, "third-service").value, "synthetic-third-key")

    def test_value_is_absent_from_credential_repr(self):
        self.set_value()
        credential = auth.resolve(self.root, self.service)
        self.assertNotIn(self.value, repr(credential))
        self.assertIn(self.service, repr(credential))

    def test_two_studios_resolve_the_same_service_independently_after_cwd_changes(self):
        other = self.other_studio()
        first = self.set_value()["selection"]
        second = self.set_value("synthetic-other-studio-value", root=other)["selection"]
        self.assertEqual(first, second)
        with contextlib.chdir(self.user):
            self.assertEqual(auth.resolve(self.root, self.service).value, self.value)
            self.assertEqual(auth.resolve(other, self.service).value, "synthetic-other-studio-value")

    def test_rotation_preserves_source_selection_and_studio_manifest(self):
        first = self.set_value()
        before = auth.selections(self.root)
        manifest = (self.root / studio.MANIFEST).read_bytes()
        changed = self.set_value("synthetic-rotated-value")
        self.assertEqual(changed["selection"], first["selection"])
        self.assertEqual(auth.resolve(self.root, self.service, expected=first["selection"]).value,
                         "synthetic-rotated-value")
        self.assertEqual(auth.selections(self.root), before)
        self.assertEqual((self.root / studio.MANIFEST).read_bytes(), manifest)

    def test_environment_rotation_preserves_the_claimed_source(self):
        os.environ[self.variable] = "synthetic-first-environment-key"
        selected = auth.prepare(self.root, self.service, environment=self.variable)["selection"]
        os.environ[self.variable] = "synthetic-second-environment-key"
        credential = auth.resolve(self.root, self.service, expected=selected)
        self.assertEqual(credential.selection, selected)
        self.assertEqual(credential.value, "synthetic-second-environment-key")
        self.assertNotIn(credential.value, json.dumps(auth.inspect(self.root, self.service, expected=selected)))

    def test_environment_claim_is_pinned_against_a_new_stored_source(self):
        os.environ[self.variable] = "synthetic-environment-key"
        selected = auth.prepare(self.root, self.service, environment=self.variable)["selection"]
        self.set_value()
        report = auth.inspect(self.root, self.service, expected=selected)
        self.assertFalse(report["available"])
        self.assertEqual(report["diagnostics"][0]["expected_selection"], selected)
        self.run_action(report["diagnostics"][0]["next_action"])
        self.assertEqual(auth.resolve(self.root, self.service, expected=selected).value, "synthetic-environment-key")

    def test_environment_resolution_uses_process_state_independently_of_user_home(self):
        selected = auth.prepare(self.root, self.service, environment=self.variable)["selection"]
        with mock.patch.object(Path, "home", side_effect=AssertionError("Environment source reads process state")):
            report = auth.inspect(self.root, self.service)
            self.assertFalse(report["available"])
            self.assertEqual(report["selection"], selected)
            self.assertIn(self.variable, report["diagnostics"][0]["message"])
            os.environ[self.variable] = "synthetic-independent-environment-key"
            self.assertEqual(auth.resolve(self.root, self.service).selection, selected)

    def test_readable_editor_file_retains_its_permissions_and_value(self):
        self.set_value()
        path = self.config()
        path.chmod(0o644)
        before = path.read_bytes()
        mode = stat.S_IMODE(path.stat().st_mode)
        self.assertTrue(auth.status(self.root, self.service)["ok"])
        self.assertEqual(auth.resolve(self.root, self.service).value, self.value)
        self.assertTrue(auth.prepare(self.root, self.service)["available"])
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), mode)
        self.set_value("synthetic-editor-file-rotation")
        self.assertEqual(auth.resolve(self.root, self.service).value, "synthetic-editor-file-rotation")


    def test_hardlinked_document_is_read_and_rotation_publishes_the_studio_copy(self):
        self.set_value()
        path, linked = self.config(), self.base / "hardlinked-document"
        before = path.read_bytes()
        try:
            os.link(path, linked)
        except OSError as exc:
            self.skipTest("Filesystem cannot create this hardlink: " + type(exc).__name__)
        self.assertEqual(auth.resolve(self.root, self.service).value, self.value)
        self.assertTrue(auth.prepare(self.root, self.service)["available"])
        self.assertEqual(linked.read_bytes(), before)
        self.set_value("synthetic-independent-rotation")
        self.assertEqual(auth.resolve(self.root, self.service).value, "synthetic-independent-rotation")
        self.assertEqual(linked.read_bytes(), before)

    def test_linked_document_is_read_and_rotation_publishes_the_studio_copy(self):
        self.set_value()
        path, target = self.config(), self.base / "credentials-target.json"
        before = path.read_bytes()
        path.rename(target)
        try:
            path.symlink_to(target)
        except OSError as exc:
            target.rename(path)
            self.skipTest("Filesystem cannot create this symlink: " + type(exc).__name__)
        self.assertEqual(auth.resolve(self.root, self.service).value, self.value)
        self.assertTrue(auth.prepare(self.root, self.service)["available"])
        self.assertEqual(target.read_bytes(), before)
        self.set_value("synthetic-linked-file-rotation")
        self.assertEqual(auth.resolve(self.root, self.service).value, "synthetic-linked-file-rotation")
        self.assertEqual(target.read_bytes(), before)
        self.assertFalse(path.is_symlink())

    def test_atomic_publication_uses_a_temporary_file_with_platform_access_policy(self):
        self.set_value()
        replace = auth.os.replace
        observed = []
        def publish(source, destination, *args, **kwargs):
            if Path(destination) == self.config():
                temporary = Path(source)
                self.assertEqual(temporary.parent, self.config().parent)
                self.assertTrue(temporary.is_file())
                self.assertEqual(json.loads(temporary.read_text(encoding="utf-8"))[self.service]["api_key"],
                                 "synthetic-private-temp-rotation")
                self.assertEqual(self.document()[self.service]["api_key"], self.value)
                observed.append((temporary, stat.S_IMODE(temporary.stat().st_mode)))
            return replace(source, destination, *args, **kwargs)
        with contextlib.ExitStack() as contexts:
            contexts.enter_context(mock.patch.object(auth.os, "replace", side_effect=publish))
            if os.name == "nt":
                for name in ("geteuid", "fchmod"):
                    contexts.enter_context(mock.patch.object(auth.os, name, create=True,
                        side_effect=AssertionError("Windows uses inherited ACL policy")))
            self.set_value("synthetic-private-temp-rotation")
        self.assertEqual(len(observed), 1)
        temporary, mode = observed[0]
        self.assertFalse(temporary.exists())
        self.assertEqual(auth.resolve(self.root, self.service).value, "synthetic-private-temp-rotation")
        if os.name != "nt":
            self.assertEqual(mode, 0o600)
            self.assertEqual(stat.S_IMODE(self.config().stat().st_mode), 0o600)

    def test_failed_atomic_replace_preserves_existing_sources_and_values(self):
        self.set_value()
        self.set_value("synthetic-unrelated-key", service="other-service")
        before = self.config().read_bytes()
        files_before = set(self.root.iterdir())
        with mock.patch.object(auth.os, "replace", side_effect=PermissionError("Synthetic publish failure")):
            with self.assertRaises(ProductionError):
                self.set_value("synthetic-unpublished-value")
        self.assertEqual(self.config().read_bytes(), before)
        self.assertEqual(set(self.root.iterdir()), files_before)
        self.assertEqual(auth.resolve(self.root, self.service).value, self.value)

    def test_external_editor_change_is_retained_when_optimistic_publication_detects_conflict(self):
        self.set_value()
        write = auth._write
        edited = []
        def editor_then_publish(path, document, **options):
            if Path(path) == self.config() and not edited:
                edited.append(self.edit_key("external-service", "synthetic-editor-added-value"))
            return write(path, document, **options)
        with mock.patch.object(auth, "_write", side_effect=editor_then_publish), self.assertRaises(ProductionError):
            self.set_value("synthetic-concurrent-agent-rotation")
        self.assertEqual(self.config().read_bytes(), edited[0])
        self.assertEqual(self.document()[self.service]["api_key"], self.value)
        self.assertEqual(self.document()["external-service"]["api_key"], "synthetic-editor-added-value")

    def test_environment_strings_are_passed_through_without_changing_the_source(self):
        selected = auth.prepare(self.root, self.service, environment=self.variable)["selection"]
        before = self.config().read_bytes()
        for value in ("  synthetic-padded-value  ", "synthetic-first\nsynthetic-second", " \t\n ", "x" * 20000):
            os.environ[self.variable] = value
            for expected in (None, selected):
                with self.subTest(length=len(value), claimed=expected is not None):
                    report = auth.inspect(self.root, self.service, expected=expected)
                    self.assertTrue(report["available"])
                    self.assertEqual(report["selection"], selected)
                    self.assertEqual(auth.resolve(self.root, self.service, expected=expected).value, value)
                    self.assertNotIn(value, json.dumps(report))
        self.assertEqual(self.config().read_bytes(), before)

    def test_cli_environment_import_accepts_short_numeric_values_without_echoing(self):
        for value in ("short", "12345678901234567890"):
            with self.subTest(kind="short" if value == "short" else "numeric"):
                os.environ["SYNTHETIC_INPUT"] = value
                code, output, errors = self.invoke("credentials", "set", self.service, "--studio", str(self.root),
                                                   "--from-env", "SYNTHETIC_INPUT")
                self.assertEqual(code, 0, errors)
                self.assertNotIn(value, output + errors)
                os.environ.pop("SYNTHETIC_INPUT")
                self.assertEqual(auth.resolve(self.root, self.service).value, value)

    def test_services_import_one_environment_name_into_independent_owned_entries(self):
        selections = []
        for service, value in ((self.service, self.value), ("other-service", "synthetic-other-account")):
            os.environ[self.variable] = value
            code, output, errors = self.invoke("credentials", "set", service, "--studio", str(self.root),
                                               "--from-env", self.variable)
            self.assertEqual(code, 0, errors)
            selections.append(json.loads(output)["selection"])
        os.environ.pop(self.variable)
        self.assertNotEqual(selections[0]["service"], selections[1]["service"])
        self.assertEqual(auth.resolve(self.root, self.service).value, self.value)
        self.assertEqual(auth.resolve(self.root, "other-service").value, "synthetic-other-account")

    def test_hidden_terminal_input_saves_without_environment_setup(self):
        with mock.patch.object(auth.getpass, "getpass", return_value=self.value) as getpass:
            code, output, errors = self.invoke("credentials", "set", self.service, "--studio", str(self.root), terminal=True)
        self.assertEqual(code, 0, errors)
        getpass.assert_called_once()
        self.assertNotIn(self.value, output + errors)
        self.assertEqual(auth.resolve(self.root, self.service).value, self.value)

    def test_hidden_input_refuses_nonterminal_without_echo_or_configuration_change(self):
        code, output, errors = self.invoke("credentials", "set", self.service, "--studio", str(self.root), stdin=self.value)
        self.assertEqual(code, 3)
        self.assertNotIn(self.value, output + errors)
        self.assertFalse(self.config().exists())

    def test_hidden_input_warning_fails_before_value_read(self):
        input_stream = io.StringIO()
        input_stream.isatty = lambda: True
        with mock.patch.object(sys, "stdin", input_stream), \
                mock.patch.object(auth.getpass, "getpass", side_effect=auth.getpass.GetPassWarning):
            with self.assertRaises(ProductionError):
                auth.read_input(self.root, self.service)

    def test_stdin_saves_the_complete_value_with_whitespace_and_long_content(self):
        value = "  synthetic-prefix\t" + "x" * 20000 + "\nsynthetic-suffix  \n"
        code, output, errors = self.invoke("credentials", "set", self.service, "--studio", str(self.root),
                                          "--stdin", stdin=value)
        self.assertEqual(code, 0, errors)
        self.assertEqual(self.document()[self.service]["api_key"], value)
        self.assertEqual(auth.resolve(self.root, self.service).value, value)
        self.assertNotIn("synthetic-prefix", output + errors)

    def test_set_requires_a_present_string_without_coercing_other_json_types(self):
        for value in ("", None, 17, False, [], {"private": "synthetic-not-a-string"}):
            with self.subTest(kind=type(value).__name__), self.assertRaises(ProductionError) as caught:
                auth.set_value(self.root, self.service, value)
            self.assertFalse(self.config().exists())
            self.assertNotIn("synthetic-not-a-string", str(caught.exception))

    def test_saved_strings_preserve_every_character(self):
        values = ("  synthetic-padded-key  ", " \t\r\n ", "synthetic\x00value",
                  "synthetic\tvalue\x7f", "synthetic-first\nsynthetic-second", "clef-\u00e9", "x" * 20000)
        for value in values:
            with self.subTest(length=len(value)):
                selected = auth.set_value(self.root, self.service, value)["selection"]
                self.assertEqual(self.document()[self.service]["api_key"], value)
                self.assertEqual(auth.resolve(self.root, self.service, expected=selected).value, value)
                self.assertTrue(auth.status(self.root, self.service)["ok"])

    def test_large_json_document_preserves_selected_and_unrelated_values(self):
        large = "synthetic-long-key-" + "x" * (8 * 1024 * 1024)
        self.write_document({self.service: {"api_key": self.value}, "other-service": {"api_key": large}})
        self.assertEqual(auth.resolve(self.root, self.service).value, self.value)
        self.assertEqual(auth.resolve(self.root, "other-service").value, large)
        self.set_value("synthetic-selected-rotation")
        self.assertEqual(auth.resolve(self.root, self.service).value, "synthetic-selected-rotation")
        self.assertEqual(auth.resolve(self.root, "other-service").value, large)

    def test_real_cli_handles_spaces_and_unicode_in_the_studio_path(self):
        root = studio.init(self.base / "studio 認証 work", "unicode-auth-studio", "Synthetic path test")
        command = [sys.executable, "-B", str(ROOT / "scripts" / "studio.py"), "credentials", "set", self.service,
                   "--studio", str(root), "--stdin"]
        value = "  " + self.value + "\r\n"
        result = subprocess.run(command, input=value.encode("utf-8"), capture_output=True,
                                cwd=self.user, env={"PYTHONDONTWRITEBYTECODE": "1",
                                                    "CPB_HOME": str(self.base / "cli-configuration")}, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(self.value.encode("utf-8"), result.stdout + result.stderr)
        self.assertEqual(auth.resolve(root, self.service).value, value)
        self.assertEqual(json.loads(result.stdout)["selection"]["service"], self.service)

    def edit_key(self, service, value, root=None):
        document = self.document(root)
        document[service] = {"api_key": value}
        return self.write_document(document, root)

    def enter_key(self, entry, value):
        self.assertEqual(entry["format"], "json")
        self.assertEqual(entry["encoding"], "utf-8")
        pointer = entry["json_pointer"].split("/")
        self.assertEqual(len(pointer), 3)
        self.assertEqual(pointer[0], "")
        self.assertEqual(pointer[2], "api_key")
        path = Path(entry["path"])
        self.assertTrue(path.is_absolute())
        self.assertEqual(path.name, auth.CONFIG_FILE)
        return self.edit_key(pointer[1], value, path.parent)

    def set_value(self, value=None, *, root=None, service=None):
        return auth.set_value(root or self.root, service or self.service,
                              self.value if value is None else value)


    def test_repeated_lookup_resave_and_rotation_use_the_current_value(self):
        first = self.set_value()
        for _ in range(2):
            self.assertEqual(auth.resolve(self.root, self.service).value, self.value)
        self.assertEqual(self.set_value()["operation"], "retained")
        changed = self.set_value("synthetic-current-rotation")
        self.assertEqual(changed["operation"], "rotated")
        self.assertEqual(changed["selection"], first["selection"])
        for _ in range(2):
            self.assertEqual(auth.resolve(self.root, self.service, expected=first["selection"]).value,
                             "synthetic-current-rotation")


    def test_lookup_reads_the_current_key_after_an_editor_replaces_the_file_before_open(self):
        selected = self.set_value()["selection"]
        path = self.config()
        replacement = self.root / "owner-editor-pending.json"
        value = "synthetic-editor-replacement-value"
        raw = json.dumps({self.service: {"api_key": value}}).encode("utf-8")
        replacement.write_bytes(raw)
        if os.name != "nt":
            replacement.chmod(0o600)
        original_open, replacements = Path.open, []
        def open_current(candidate, *args, **kwargs):
            if Path(candidate) == path and not replacements:
                os.replace(replacement, path)
                replacements.append(True)
            return original_open(candidate, *args, **kwargs)
        with mock.patch.object(Path, "open", open_current):
            credential = auth.resolve(self.root, self.service, expected=selected)
        self.assertEqual(replacements, [True])
        self.assertEqual(credential.value, value)
        self.assertEqual(credential.selection, selected)
        self.assertEqual(path.read_bytes(), raw)
        self.assertEqual(auth.resolve(self.root, self.service, expected=selected).value, value)


    def test_operating_system_read_failures_report_unavailable_without_disclosing_input(self):
        self.set_value()
        original = Path.read_bytes
        for error in (PermissionError, IsADirectoryError):
            def unavailable(path):
                if path == self.config():
                    raise error("synthetic-private-os-error")
                return original(path)
            with self.subTest(error=error.__name__), mock.patch.object(Path, "read_bytes", unavailable):
                report = auth.inspect(self.root, self.service)
                self.assertFalse(report["available"])
                self.assertNotIn("synthetic-private-os-error", json.dumps(report))
                self.assertNotIn(self.value, json.dumps(report))
        self.assertEqual(auth.resolve(self.root, self.service).value, self.value)

    def test_private_document_contains_one_direct_source_for_each_service(self):
        report = self.set_value()
        expected = {"service": self.service, "source": "api_key"}
        self.assertEqual(self.document(), {self.service: {"api_key": self.value}})
        self.assertEqual(auth.selections(self.root), {self.service: expected})
        self.assertEqual(report["selection"], expected)
        self.assertEqual(auth.resolve(self.root, self.service).value, self.value)
        self.assertNotIn(self.value, json.dumps(report) + json.dumps(auth.selections(self.root)))
        self.assertNotIn(self.variable, os.environ)

    def test_service_preparation_preserves_other_services_and_value_choices(self):
        first = self.set_value()["selection"]
        second = auth.prepare(self.root, "other-service")
        self.assertEqual(second["input"]["json_pointer"], "/other-service/api_key")
        self.assertEqual(self.document(), {self.service: {"api_key": self.value},
                                          "other-service": {"api_key": ""}})
        self.enter_key(second["input"], "synthetic-second-service-value")
        self.assertEqual(auth.resolve(self.root, self.service, expected=first).value, self.value)
        self.assertEqual(auth.resolve(self.root, "other-service").value, "synthetic-second-service-value")

    def test_missing_configuration_prepares_input_before_requesting_owner_value(self):
        observed = auth.inspect(self.root, self.service)
        self.assertFalse(observed["available"])
        self.assertFalse(self.config().exists())
        action = observed["diagnostics"][0]["next_action"]
        self.assertEqual(action["command"], "credentials-prepare")
        self.assertFalse(action["requires_author_input"])
        self.assertEqual(action["argv"][2:5], ["credentials", "prepare", self.service])
        prepared = self.run_action(action)
        self.assertEqual(self.document(), {self.service: {"api_key": ""}})
        self.assertEqual(prepared["input"]["json_pointer"], "/" + self.service + "/api_key")
        self.enter_key(prepared["input"], self.value)
        self.assertEqual(auth.resolve(self.root, self.service).value, self.value)

    def test_removed_claimed_service_has_executable_preparation_for_its_source(self):
        selected = self.set_value()["selection"]
        auth.remove(self.root, self.service)
        diagnostic = auth.inspect(self.root, self.service, expected=selected)["diagnostics"][0]
        self.assertEqual(diagnostic["expected_selection"], selected)
        action = diagnostic["next_action"]
        self.assertEqual(action["command"], "credentials-prepare")
        self.assertIn("--stored", action["argv"])
        restored = self.run_action(action)
        self.assertEqual(restored["selection"], selected)
        self.assertFalse(restored["available"])
        self.enter_key(restored["input"], "synthetic-restored-service-key")
        self.assertEqual(auth.resolve(self.root, self.service, expected=selected).value,
                         "synthetic-restored-service-key")

    def test_explicit_source_changes_replace_only_the_named_service_configuration(self):
        self.set_value()
        self.set_value("synthetic-unrelated-key", service="other-service")
        os.environ[self.variable] = "synthetic-live-environment-value"
        environment = auth.prepare(self.root, self.service, environment=self.variable)
        self.assertTrue(environment["available"])
        self.assertEqual(self.document(), {self.service: {"api_key_env": self.variable},
                                          "other-service": {"api_key": "synthetic-unrelated-key"}})
        self.assertIsNone(environment["input"])
        stored = auth.prepare(self.root, self.service, stored=True)
        self.assertFalse(stored["available"])
        self.assertEqual(self.document(), {self.service: {"api_key": ""},
                                          "other-service": {"api_key": "synthetic-unrelated-key"}})
        self.enter_key(stored["input"], self.value)
        before = self.config().read_bytes()
        self.assertTrue(auth.prepare(self.root, self.service, stored=True)["available"])
        self.assertEqual(self.config().read_bytes(), before)

    def test_explicit_set_and_remove_repair_only_the_named_invalid_entry(self):
        selected = self.set_value()["selection"]
        invalid = {"unexpected": "synthetic-invalid-unrelated-value"}
        self.edit_key(self.service, {"unexpected": "synthetic-invalid-selected-value"})
        self.edit_key("other-service", invalid)
        restored = self.set_value("synthetic-repaired-value")
        self.assertEqual(restored["selection"], selected)
        self.assertEqual(auth.resolve(self.root, self.service).value, "synthetic-repaired-value")
        self.assertEqual(self.document()["other-service"], {"api_key": invalid})
        auth.remove(self.root, "other-service")
        self.assertEqual(self.document(), {self.service: {"api_key": "synthetic-repaired-value"}})

    def test_malformed_document_reports_root_pointer_without_disclosing_contents(self):
        self.set_value()
        private = "synthetic-private-invalid-document"
        documents = (b'{"synthetic-service":{"api_key":"' + private.encode() + b'"}',
                     b'{"synthetic-service":{"api_key":"' + private.encode() + b'\xff"}}')
        for raw in documents:
            with self.subTest(size=len(raw)):
                self.config().write_bytes(raw)
                observed = auth.inspect(self.root, self.service)
                self.assertFalse(observed["available"])
                action = observed["diagnostics"][0]["next_action"]
                self.assertEqual(action["input"]["path"], str(self.config()))
                self.assertEqual(action["input"]["json_pointer"], "")
                self.assertTrue(action["requires_author_input"])
                self.assertNotIn(private, json.dumps(observed))
                with self.assertRaises(ProductionError) as caught:
                    auth.prepare(self.root, self.service)
                self.assertNotIn(private, str(caught.exception))
                self.assertEqual(self.config().read_bytes(), raw)

    def test_new_service_preparation_retains_another_services_invalid_value(self):
        invalid = {"unexpected": "synthetic-invalid-entry"}
        self.set_value()
        self.edit_key(self.service, invalid)
        prepared = auth.prepare(self.root, "other-service")
        self.assertTrue(prepared["ok"])
        self.assertFalse(prepared["available"])
        self.assertEqual(prepared["input"]["json_pointer"], "/other-service/api_key")
        self.assertEqual(self.document()[self.service], {"api_key": invalid})
        self.enter_key(prepared["input"], "synthetic-valid-other-key")
        self.assertEqual(auth.resolve(self.root, "other-service").value, "synthetic-valid-other-key")
        self.assertFalse(auth.inspect(self.root, self.service)["available"])

    def test_remove_deletes_one_complete_service_entry_and_is_idempotent(self):
        self.set_value()
        self.set_value("synthetic-other-service-value", service="other-service")
        os.environ[self.variable] = "synthetic-ambient-value"
        self.assertTrue(auth.remove(self.root, self.service)["removed"])
        self.assertEqual(self.document(), {"other-service": {"api_key": "synthetic-other-service-value"}})
        self.assertFalse(auth.inspect(self.root, self.service)["available"])
        self.assertFalse(auth.remove(self.root, self.service)["removed"])
        self.assertEqual(auth.resolve(self.root, "other-service").value, "synthetic-other-service-value")
        self.edit_key("other-service", {"unexpected": "synthetic-invalid-entry"})
        self.assertTrue(auth.remove(self.root, "other-service")["removed"])
        self.assertEqual(self.document(), {})

    def test_removing_environment_configuration_preserves_the_process_variable(self):
        os.environ[self.variable] = self.value
        auth.prepare(self.root, self.service, environment=self.variable)
        auth.remove(self.root, self.service)
        self.assertEqual(os.environ[self.variable], self.value)
        self.assertEqual(self.document(), {})
        self.assertFalse(auth.inspect(self.root, self.service)["available"])

    def test_copy_retains_an_independent_value_and_removal_affects_only_the_copy(self):
        first = self.set_value()["selection"]
        copied = self.base / "copied"
        shutil.copytree(self.root, copied)
        self.assertEqual(auth.resolve(copied, self.service, expected=first).value, self.value)
        self.set_value("synthetic-copied-rotation", root=copied)
        self.assertEqual(auth.resolve(self.root, self.service).value, self.value)
        self.assertEqual(auth.resolve(copied, self.service).value, "synthetic-copied-rotation")
        auth.remove(copied, self.service)
        self.assertEqual(self.document(copied), {})
        self.assertFalse(auth.inspect(copied, self.service)["available"])
        self.assertEqual(auth.resolve(self.root, self.service).value, self.value)

    def test_services_can_explicitly_read_the_same_environment_variable(self):
        os.environ[self.variable] = "synthetic-common-environment-value"
        auth.prepare(self.root, self.service, environment=self.variable)
        auth.prepare(self.root, "other-service", environment=self.variable)
        before = self.config().read_bytes()
        self.assertEqual(self.document(), {name: {"api_key_env": self.variable}
                                          for name in (self.service, "other-service")})
        os.environ[self.variable] = "synthetic-rotated-common-value"
        for name in (self.service, "other-service"):
            self.assertEqual(auth.resolve(self.root, name).value, "synthetic-rotated-common-value")
        auth.remove(self.root, self.service)
        self.assertEqual(auth.resolve(self.root, "other-service").value, "synthetic-rotated-common-value")
        self.assertNotIn(b"synthetic-common-environment-value", before)
        self.assertNotIn(b"synthetic-rotated-common-value", self.config().read_bytes())

    def test_environment_value_requires_explicit_service_configuration(self):
        os.environ[self.variable] = "synthetic-environment-key"
        self.assertFalse(auth.inspect(self.root, self.service)["available"])
        auth.prepare(self.root, self.service, environment=self.variable)
        credential = auth.resolve(self.root, self.service)
        self.assertEqual(credential.selection, {"service": self.service, "source": "api_key_env",
                                               "variable": self.variable})
        self.assertEqual(credential.value, "synthetic-environment-key")
        self.assertEqual(self.document(), {self.service: {"api_key_env": self.variable}})

    def test_pending_stored_key_waits_at_its_field_when_an_environment_value_exists(self):
        selected = auth.prepare(self.root, self.service)["selection"]
        os.environ[self.variable] = "synthetic-unselected-environment-value"
        report = auth.inspect(self.root, self.service, expected=selected)
        self.assertFalse(report["available"])
        self.assertEqual(report["selection"], selected)
        self.assertEqual(report["diagnostics"][0]["next_action"]["input"]["json_pointer"],
                         "/" + self.service + "/api_key")
        self.assertEqual(self.document(), {self.service: {"api_key": ""}})

    def test_stored_claim_requires_explicit_restoration_after_source_change(self):
        selected = self.set_value()["selection"]
        os.environ[self.variable] = "synthetic-other-environment-account"
        auth.prepare(self.root, self.service, environment=self.variable)
        report = auth.inspect(self.root, self.service, expected=selected)
        self.assertFalse(report["available"])
        self.assertEqual(report["diagnostics"][0]["expected_selection"], selected)
        action = report["diagnostics"][0]["next_action"]
        self.assertEqual(action["command"], "credentials-prepare")
        self.assertTrue(action["requires_author_input"])
        self.assertIn("--stored", action["argv"])
        prepared = self.run_action(action)
        self.assertEqual(prepared["selection"], selected)
        self.assertFalse(prepared["available"])
        self.enter_key(prepared["input"], self.value)
        self.assertEqual(auth.resolve(self.root, self.service, expected=selected).value, self.value)

    def test_environment_claim_detects_a_changed_variable_even_when_values_match(self):
        alternate = "CPB_SYNTHETIC_ALTERNATE_KEY"
        os.environ[self.variable] = os.environ[alternate] = self.value
        selected = auth.prepare(self.root, self.service, environment=self.variable)["selection"]
        auth.prepare(self.root, self.service, environment=alternate)
        report = auth.inspect(self.root, self.service, expected=selected)
        self.assertFalse(report["available"])
        action = report["diagnostics"][0]["next_action"]
        self.assertEqual(action["command"], "credentials-prepare")
        self.assertTrue(action["requires_author_input"])
        self.assertEqual(action["argv"][action["argv"].index("--environment") + 1], self.variable)
        self.run_action(action)
        self.assertEqual(auth.resolve(self.root, self.service, expected=selected).value, self.value)

    def test_removed_environment_claim_restores_only_its_variable_name(self):
        os.environ[self.variable] = self.value
        selected = auth.prepare(self.root, self.service, environment=self.variable)["selection"]
        auth.remove(self.root, self.service)
        action = auth.inspect(self.root, self.service, expected=selected)["diagnostics"][0]["next_action"]
        restored = self.run_action(action)
        self.assertEqual(restored["selection"], selected)
        self.assertTrue(restored["available"])
        self.assertIsNone(restored["input"])
        self.assertEqual(self.document(), {self.service: {"api_key_env": self.variable}})

    def test_status_reports_each_service_and_can_focus_on_one_available_source(self):
        selected = self.set_value()["selection"]
        auth.prepare(self.root, "pending-service")
        all_services = auth.status(self.root)
        self.assertFalse(all_services["ok"])
        rows = {row["service"]: row for row in all_services["services"]}
        self.assertEqual(set(rows), {self.service, "pending-service"})
        self.assertTrue(rows[self.service]["available"])
        self.assertEqual(rows[self.service]["selection"], selected)
        self.assertFalse(rows["pending-service"]["available"])
        named = auth.status(self.root, self.service)
        self.assertTrue(named["ok"])
        self.assertEqual(len(named["services"]), 1)
        self.assertFalse(auth.status(self.root, "absent-service")["ok"])
        self.assertNotIn(self.value, json.dumps(all_services) + json.dumps(named))

    def test_malformed_source_data_is_private_and_studio_validation_reports_the_file(self):
        secret = "synthetic-secret-in-invalid-configuration"
        self.write_document({self.service: {"api_key": secret, "api_key_env": self.variable}})
        report = auth.inspect(self.root, self.service)
        self.assertFalse(report["available"])
        self.assertNotIn(secret, json.dumps(report))
        errors = validate_studio.validate(self.root)
        self.assertTrue(any(auth.CONFIG_FILE in error for error in errors))
        self.assertNotIn(secret, json.dumps(errors))

    def test_selections_reports_missing_or_ambiguous_sources_and_nonobject_documents(self):
        documents = ('{"synthetic-service":[]}', '{"synthetic-service":{}}', '[]',
                     '{"synthetic-service":{"api_key":"","api_key_env":"NAME"}}',
                     '{"synthetic-service":{"api_key_env":"INVALID-NAME"}}')
        for raw in documents:
            with self.subTest(size=len(raw)):
                self.config().write_text(raw, encoding="utf-8")
                with self.assertRaises(ValueError):
                    auth.selections(self.root)

    def test_named_lookup_and_edits_preserve_other_service_configuration(self):
        self.write_document({self.service: {"api_key": self.value, "owner_note": "keep"},
                             "other-service": {"api_key_env": []}, "unfinished-service": None})
        self.assertEqual(auth.resolve(self.root, self.service).value, self.value)
        self.assertTrue(auth.status(self.root, self.service)["ok"])
        report = auth.status(self.root)
        rows = {row["service"]: row for row in report["services"]}
        self.assertTrue(rows[self.service]["available"])
        self.assertFalse(rows["other-service"]["available"])
        self.assertFalse(rows["unfinished-service"]["available"])
        self.assertTrue(auth.prepare(self.root, self.service)["available"])
        self.set_value("synthetic-new-service-key", service="new-service")
        self.assertEqual(self.document()[self.service]["owner_note"], "keep")
        self.assertEqual(self.document()["other-service"], {"api_key_env": []})
        self.assertIsNone(self.document()["unfinished-service"])
        removed = auth.remove(self.root, "unfinished-service")
        self.assertTrue(removed["removed"])
        self.assertNotIn("unfinished-service", self.document())
        auth.set_value(self.root, "other-service", "synthetic-repaired-service")
        self.assertEqual(auth.resolve(self.root, "other-service").value, "synthetic-repaired-service")

    def test_studio_validation_checks_sources_without_requiring_available_values(self):
        auth.prepare(self.root, self.service)
        auth.prepare(self.root, "environment-service", environment=self.variable)
        self.assertEqual(validate_studio.validate(self.root), [])
        self.assertFalse(auth.status(self.root)["ok"])

    def test_redirected_studio_directory_is_rejected_without_modifying_its_value(self):
        self.set_value()
        root = self.root
        before = self.config().read_bytes()
        moved = self.base / "moved-studio"
        def assert_refused():
            self.assertFalse(auth.inspect(root, self.service)["available"])
            for action in (lambda: auth.prepare(root, self.service),
                           lambda: auth.set_value(root, self.service, "synthetic-redirected-rotation")):
                with self.assertRaises(ProductionError):
                    action()
        root.rename(moved)
        try:
            root.symlink_to(moved, target_is_directory=True)
        except OSError:
            moved.rename(root)
        else:
            try:
                with self.subTest(filesystem="native directory symlink"):
                    assert_refused()
                    self.assertEqual(self.config(moved).read_bytes(), before)
            finally:
                root.unlink()
                moved.rename(root)

    def test_failed_prepare_keeps_existing_services_and_publishes_no_new_entry(self):
        self.set_value(service="other-service")
        before = self.config().read_bytes()
        with mock.patch.object(auth, "_write", side_effect=PermissionError("Synthetic publication failure")), \
                self.assertRaises(ProductionError):
            auth.prepare(self.root, self.service)
        self.assertEqual(self.config().read_bytes(), before)
        self.assertEqual(self.document(), {"other-service": {"api_key": self.value}})

    def test_failed_remove_preserves_the_complete_private_document(self):
        self.set_value()
        before = self.config().read_bytes()
        with mock.patch.object(auth, "_write", side_effect=PermissionError("Synthetic publication failure")), \
                self.assertRaises(ProductionError):
            auth.remove(self.root, self.service)
        self.assertEqual(self.config().read_bytes(), before)
        self.assertEqual(auth.resolve(self.root, self.service).value, self.value)

    def test_failed_source_change_preserves_the_current_method_and_value(self):
        selected = self.set_value()["selection"]
        before = self.config().read_bytes()
        with mock.patch.object(auth, "_write", side_effect=PermissionError("Synthetic publication failure")), \
                self.assertRaises(ProductionError):
            auth.prepare(self.root, self.service, environment=self.variable)
        self.assertEqual(self.config().read_bytes(), before)
        self.assertEqual(auth.resolve(self.root, self.service, expected=selected).value, self.value)

    def test_concurrent_services_preserve_each_complete_entry(self):
        names = ("first-service", "second-service")
        self.run_concurrently(*(lambda name=name: self.set_value("synthetic-key-for-" + name, service=name)
                                for name in names))
        self.assertEqual(set(auth.selections(self.root)), set(names))
        self.assertEqual(self.document(), {name: {"api_key": "synthetic-key-for-" + name} for name in names})

    def test_concurrent_prepare_creates_one_service_entry(self):
        results = self.run_concurrently(*(lambda: auth.prepare(self.root, self.service) for _ in range(2)))
        self.assertEqual(results[0]["selection"], results[1]["selection"])
        self.assertEqual(self.document(), {self.service: {"api_key": ""}})
        self.assertEqual(sorted(report["operation"] for report in results), ["created", "retained"])

    def test_concurrent_prepare_and_set_preserve_other_services(self):
        self.set_value(service="existing-service")
        self.run_concurrently(lambda: auth.prepare(self.root, self.service),
                              lambda: self.set_value("synthetic-second-key", service="other-service"))
        self.assertEqual(self.document(), {"existing-service": {"api_key": self.value},
                                          self.service: {"api_key": ""},
                                          "other-service": {"api_key": "synthetic-second-key"}})

    def test_input_wait_preserves_an_unrelated_service_added_by_the_owner(self):
        selected = self.set_value()["selection"]
        def supply(prompt):
            self.assertIn(self.service, prompt)
            self.edit_key("other-service", "synthetic-owner-other-key")
            return "synthetic-requested-key-rotation"
        with mock.patch.object(auth.getpass, "getpass", side_effect=supply):
            code, output, errors = self.invoke("credentials", "set", self.service,
                                               "--studio", str(self.root), terminal=True)
        self.assertEqual(code, 0, errors)
        self.assertEqual(json.loads(output)["selection"], selected)
        self.assertEqual(self.document(), {self.service: {"api_key": "synthetic-requested-key-rotation"},
                                          "other-service": {"api_key": "synthetic-owner-other-key"}})

    def test_input_wait_refuses_overwriting_the_owners_rotation_at_the_same_source(self):
        selected = self.set_value()["selection"]
        saved = []
        def supply(prompt):
            saved.append(self.edit_key(self.service, "synthetic-owner-rotation"))
            return "synthetic-pending-input-value"
        with mock.patch.object(auth.getpass, "getpass", side_effect=supply):
            code, output, errors = self.invoke("credentials", "set", self.service,
                                               "--studio", str(self.root), terminal=True)
        self.assertEqual(code, 3, errors)
        self.assertEqual(json.loads(output)["diagnostics"][0]["code"], "CREDENTIAL_UNAVAILABLE")
        self.assertEqual(self.config().read_bytes(), saved[0])
        self.assertEqual(auth.resolve(self.root, self.service, expected=selected).value,
                         "synthetic-owner-rotation")
        self.assertNotIn("synthetic-pending-input-value", output + errors)
        self.assertNotIn("synthetic-owner-rotation", output + errors)

    def test_input_wait_refuses_a_changed_source_and_keeps_the_new_configuration(self):
        self.set_value()
        os.environ[self.variable] = "synthetic-owner-environment-value"
        saved = []
        def supply(prompt):
            auth.prepare(self.root, self.service, environment=self.variable)
            saved.append(self.config().read_bytes())
            return "synthetic-pending-input-value"
        with mock.patch.object(auth.getpass, "getpass", side_effect=supply):
            code, output, errors = self.invoke("credentials", "set", self.service,
                                               "--studio", str(self.root), terminal=True)
        self.assertEqual(code, 3, errors)
        self.assertEqual(self.config().read_bytes(), saved[0])
        self.assertEqual(auth.resolve(self.root, self.service).value, "synthetic-owner-environment-value")
        self.assertNotIn("synthetic-pending-input-value", output + errors)

    def test_input_wait_refuses_recreating_a_service_removed_by_the_owner(self):
        self.set_value()
        def supply(prompt):
            auth.remove(self.root, self.service)
            return "synthetic-pending-input-value"
        with mock.patch.object(auth.getpass, "getpass", side_effect=supply):
            code, output, errors = self.invoke("credentials", "set", self.service,
                                               "--studio", str(self.root), terminal=True)
        self.assertEqual(code, 3, errors)
        self.assertEqual(self.document(), {})
        self.assertNotIn("synthetic-pending-input-value", output + errors)

    def test_cli_set_status_remove_keep_values_and_digests_out_of_artifacts(self):
        code, output, errors = self.invoke("credentials", "set", self.service, "--studio", str(self.root),
                                           "--stdin", stdin=self.value + "\n")
        self.assertEqual(code, 0, errors)
        raw = self.config().read_bytes()
        self.assertEqual(auth.resolve(self.root, self.service).value, self.value + "\n")
        code, status, errors = self.invoke("credentials", "status", self.service, "--studio", str(self.root))
        self.assertEqual(code, 0, errors)
        self.assertTrue(json.loads(status)["services"][0]["available"])
        code, removed, errors = self.invoke("credentials", "remove", self.service, "--studio", str(self.root))
        self.assertEqual(code, 0, errors)
        self.assertTrue(json.loads(removed)["removed"])
        self.assertEqual(self.document(), {})
        logs = "\n".join(p.read_text(encoding="utf-8") for p in (self.root / "logs").rglob("*") if p.is_file())
        self.assertNotIn(self.value, output + status + removed + errors + logs)
        self.assertNotIn(hashlib.sha256(raw).hexdigest(), logs)
        self.assertNotIn(hashlib.sha256(self.value.encode()).hexdigest(), logs)
        for file in (self.root / "logs").rglob("artifacts.json"):
            entries = json.loads(file.read_text(encoding="utf-8"))
            self.assertFalse(any(auth.CONFIG_FILE in str(entry.get("path", "")) for entry in entries))

    def test_cli_source_switches_use_one_configuration_and_environment_is_live(self):
        self.set_value()
        os.environ[self.variable] = "synthetic-runtime-environment-account"
        code, output, errors = self.invoke("credentials", "prepare", self.service, "--studio", str(self.root),
                                           "--environment", self.variable)
        self.assertEqual(code, 0, errors)
        self.assertEqual(self.document(), {self.service: {"api_key_env": self.variable}})
        self.assertIsNone(json.loads(output)["input"])
        os.environ[self.variable] = "synthetic-rotated-environment-account"
        self.assertEqual(auth.resolve(self.root, self.service).value, "synthetic-rotated-environment-account")
        code, output, errors = self.invoke("credentials", "prepare", self.service, "--studio", str(self.root),
                                           "--stored")
        self.assertEqual(code, 0, errors)
        self.assertFalse(json.loads(output)["available"])
        self.assertEqual(self.document(), {self.service: {"api_key": ""}})
        self.enter_key(json.loads(output)["input"], self.value)
        self.assertEqual(auth.resolve(self.root, self.service).value, self.value)

    def test_service_identifiers_and_environment_names_are_validated_before_mutation(self):
        self.set_value()
        before = self.config().read_bytes()
        for service in ("../outside", "Uppercase", "/absolute", "a/b", "a.b", "a b", "a~b", ""):
            with self.subTest(service=service), self.assertRaises(ProductionError):
                auth.prepare(self.root, service)
            self.assertEqual(self.config().read_bytes(), before)
        for variable in ("", "INVALID-NAME", "NAME WITH SPACE", "7NAME"):
            with self.subTest(variable=variable), self.assertRaises(ProductionError):
                auth.prepare(self.root, self.service, environment=variable)
            self.assertEqual(self.config().read_bytes(), before)
        for choices in ({"environment": self.variable, "stored": True},):
            with self.subTest(choices=tuple(choices)), self.assertRaises(ProductionError):
                auth.prepare(self.root, self.service, **choices)
            self.assertEqual(self.config().read_bytes(), before)

    def test_claim_selection_validates_its_service_and_complete_nonsecret_source(self):
        selected = {"service": self.service, "source": "api_key"}
        self.assertEqual(auth.validate_selection(selected, service=self.service), selected)
        malformed = ({"service": self.service}, {"service": self.service, "source": []},
                     {"service": self.service, "source": "api_key_env"},
                     {"service": self.service, "source": "api_key", "value": "synthetic-private"},
                     {"service": self.service, "source": "api_key_env", "variable": "INVALID-NAME"})
        for value in malformed:
            with self.subTest(fields=tuple(value)), self.assertRaises(ValueError):
                auth.validate_selection(value)
        with self.assertRaises(ValueError):
            auth.validate_selection(selected, service="other-service")


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
