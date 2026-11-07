"""Owned schema inputs and shared evaluation using synthetic JSON documents."""
from __future__ import annotations

from collections import Counter
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import protocol_contract as public
import state_protocol as state
import builder_inputs
import runtime_snapshot


class SchemaReadModelTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="schema-read-model-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        patch = mock.patch.object(state, "SCHEMA_DIR", self.root)
        patch.start()
        self.addCleanup(patch.stop)

    def write(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
        return path

    def test_documents_and_reference_fragments_are_owned_across_validations(self):
        source = self.write("source.json", {"type": "array", "items": {"$ref": "./definitions.json#/$defs/alias"}})
        definitions = self.write("definitions.json", {"$defs": {
            "alias": {"$ref": "#/$defs/value"}, "value": {"type": "integer", "minimum": 1}}})
        read = Path.read_bytes
        pointer = public._json_pointer
        reads, fragments = [], []

        def observe_read(path):
            reads.append(path)
            return read(path)

        def observe_pointer(document, fragment):
            fragments.append((id(document), fragment))
            return pointer(document, fragment)

        with mock.patch.object(Path, "read_bytes", observe_read), \
                mock.patch.object(public, "_json_pointer", observe_pointer), \
                state.schema_read_scope() as owner:
            document = owner.read(source)
            self.assertIs(document, state.read_schema(source))
            with state.schema_read_scope() as nested:
                self.assertIs(owner, nested)
                for _ in range(6):
                    self.assertEqual(state.validate_against_schema([1, 2, 3], document), [])
        self.assertEqual(Counter(reads), Counter({source: 1, definitions: 1}))
        self.assertEqual(len(fragments), 2)
        self.assertTrue(all(count == 1 for count in Counter(fragments).values()))

    def test_local_reference_identity_belongs_to_its_document(self):
        first = self.write("first.json", {"$defs": {"value": {"const": 1}}, "$ref": "#/$defs/value"})
        second = self.write("second.json", {"$defs": {"value": {"const": 2}}, "$ref": "#/$defs/value"})
        with state.schema_read_scope() as owner:
            one, two = owner.read(first), owner.read(second)
            for _ in range(2):
                self.assertEqual(owner.validate(1, one), [])
                self.assertEqual(owner.validate(2, two), [])
                self.assertEqual(owner.validate(2, one), ["$: expected constant 1"])
                self.assertEqual(owner.validate(1, two), ["$: expected constant 2"])

    def test_later_phase_reacquires_same_metadata_reference_changes_and_deletions(self):
        source = self.write("source.json", {"$ref": "./child.json"})
        child = self.write("child.json", {"const": 1})
        original = child.stat()
        with state.schema_read_scope() as before:
            document = before.read(source)
            self.assertEqual(before.validate(1, document), [])
            self.write("child.json", {"const": 2})
            os.utime(child, ns=(original.st_atime_ns, original.st_mtime_ns))
            self.assertEqual(child.stat().st_size, original.st_size)
            self.assertEqual(before.validate(1, document), [])
            with state.schema_read_scope(fresh=True) as current:
                self.assertIsNot(before, current)
                self.assertEqual(current.validate(2, current.read(source)), [])
                self.assertEqual(current.validate(1, current.read(source)), ["$: expected constant 2"])
            self.assertEqual(before.validate(1, document), [])
        child.unlink()
        with state.schema_read_scope() as after, self.assertRaises(FileNotFoundError):
            after.validate(2, after.read(source))

    def test_nested_schema_values_are_immutable_and_exports_are_independent(self):
        source = self.write("source.json", {"const": {"parts": [1, {"enabled": True}]}})
        with state.schema_read_scope() as owner:
            document = owner.read(source)
            with self.assertRaises(TypeError):
                document["const"]["parts"][1]["enabled"] = False
            with self.assertRaises(TypeError):
                document["const"]["parts"][0] = 2
            exported = public._mutable(document)
            exported["const"]["parts"][1]["enabled"] = False
            self.assertEqual(owner.validate({"parts": [1, {"enabled": True}]}, document), [])
            self.assertTrue(owner.validate({"parts": [1, {"enabled": False}]}, document))

    def test_mutable_inline_schema_is_recaptured_at_each_validation(self):
        schema = {"$defs": {"value": {"const": 1}}, "$ref": "#/$defs/value"}
        with state.schema_read_scope() as owner:
            self.assertEqual(owner.validate(1, schema), [])
            schema["$defs"]["value"]["const"] = 2
            self.assertEqual(owner.validate(2, schema), [])
            self.assertEqual(owner.validate(1, schema), ["$: expected constant 2"])

    def test_reference_resolution_is_lazy_but_keyword_check_walks_unvisited_branches(self):
        source = self.write("source.json", {
            "if": {"const": "selected"}, "then": {"type": "string"},
            "else": {"$ref": "./unavailable.json"}})
        with state.schema_read_scope() as owner:
            document = owner.read(source)
            self.assertEqual(owner.validate("selected", document), [])
            with self.assertRaises(FileNotFoundError):
                owner.validate("other", document)
        self.write("source.json", {
            "if": {"const": "selected"}, "then": {"type": "string"},
            "else": {"unknown-constraint": True}})
        with state.schema_read_scope() as owner, self.assertRaisesRegex(ValueError, r"\$\.else\.unknown-constraint"):
            owner.read(source)

    def test_reference_siblings_and_alternatives_keep_diagnostic_order(self):
        schema = {"$defs": {"value": {"type": "integer", "minimum": 10}},
                  "$ref": "#/$defs/value", "allOf": [{"const": 0}],
                  "anyOf": [{"const": 3}, {"const": 4}],
                  "oneOf": [{"type": "number"}, {"type": "integer"}],
                  "not": {"const": 5}, "if": {"type": "integer"},
                  "then": {"maximum": 2}, "else": {"$ref": "./unvisited.json"},
                  "enum": [6, 7]}
        expected = [
            "$: value is below minimum 10", "$: expected constant 0",
            "$: value matches none of the 2 alternatives: expected constant 3; or expected constant 4",
            "$: value matches 2 of the 2 alternatives; exactly one must match",
            "$: value satisfies a forbidden schema", "$: value is above maximum 2",
            "$: value 5 is not in [6, 7]",
        ]
        self.assertEqual(public.validate_against_schema(5, schema), expected)
        self.assertEqual(state.validate_against_schema(5, schema), expected)
        names = {"$defs": {"name": {"pattern": "^[a-z]+$"}},
                 "type": "object", "propertyNames": {"$ref": "#/$defs/name"},
                 "additionalProperties": {"type": "integer"}}
        for validate in (public.validate_against_schema, state.validate_against_schema):
            self.assertEqual(validate({"A": "bad"}, names), [
                "$.<property-name:A>: string does not match pattern '^[a-z]+$'",
                "$.A: expected type ['integer'], got str"])

    def test_product_semantic_check_retains_its_owned_diagnostic(self):
        value = {"a": {"overrides": [{"structure_id": "b", "properties": ["shape"]}]},
                 "b": {"geometry": {"shape": "declared synthetic shape"}}}
        schema = {"$id": "declared-structures.schema.json", "type": "object"}
        self.assertEqual(state.validate_against_schema(value, schema),
                         ["$.a: override property 'shape' has no local value"])
        self.assertEqual(public.validate_against_schema(value, schema),
                         ["$.a: override property 'shape' has no value on this structure"])

    def test_product_reference_paths_remain_contained_and_local(self):
        with state.schema_read_scope() as owner:
            for reference, message in (("../outside.json", "escapes schema directory"),
                                       ("https://example.invalid/schema.json", "remote schema references")):
                with self.subTest(reference=reference), self.assertRaisesRegex(ValueError, message):
                    owner.validate(None, {"$ref": reference})

    def test_public_evaluator_runs_without_product_modules_or_installation(self):
        isolated = self.root / "standalone"
        isolated.mkdir()
        shutil.copyfile(Path(public.__file__), isolated / "protocol_contract.py")
        code = """import sys
sys.path.insert(0, sys.argv[1])
import protocol_contract as p
s = {'$defs': {'number': {'type': 'integer'}}, '$ref': '#/$defs/number'}
assert p.validate_against_schema(3, s) == []
assert p.validate_against_schema('x', s) == [\"$: expected type ['integer'], got str\"]
assert not {'state_protocol', 'runtime_snapshot', 'pack_manager', 'owned_json'} & set(sys.modules)
"""
        result = subprocess.run([sys.executable, "-I", "-B", "-c", code, str(isolated)],
                                capture_output=True, text=True, encoding="utf-8", timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_failed_nested_fresh_contract_read_cannot_restore_the_parent_success(self):
        installed = self.root / "fresh-contract-installation"
        original = Path(public.__file__).resolve().parents[1]
        shutil.copytree(original / "protocols", installed / "protocols")
        (installed / "scripts").mkdir()
        shutil.copyfile(Path(public.__file__), installed / public.VALIDATOR_PATH)
        manifest = installed / public.MANIFEST_PATH
        manifest.write_text(public.seal_registry(manifest.read_text(encoding="utf-8"), installed), encoding="utf-8")
        schema = installed / "protocols/shared-state/schemas/state-event.schema.json"
        with public.read_scope():
            before = public.contract_set(root=installed)
            observed = before.schema_named("state-event.schema.json")
            schema.write_bytes(schema.read_bytes() + b" ")
            with public.read_scope(fresh=True):
                with self.assertRaisesRegex(ValueError, "public schema byte hash mismatch"):
                    public.contract_set(root=installed).schema_named("state-event.schema.json")
            self.assertIs(before.schema_named("state-event.schema.json"), observed)
            with self.assertRaisesRegex(ValueError, "public schema byte hash mismatch"):
                public.contract_set(root=installed).schema_named("state-event.schema.json")

    def test_captured_implementation_supplies_private_and_sealed_public_schemas(self):
        installed = self.root / "installed"
        original = Path(public.__file__).resolve().parents[1]
        shutil.copytree(original / "protocols", installed / "protocols")
        (installed / "scripts").mkdir()
        shutil.copyfile(Path(public.__file__), installed / public.VALIDATOR_PATH)
        manifest = installed / public.MANIFEST_PATH
        manifest.write_text(public.seal_registry(manifest.read_text(encoding="utf-8"), installed), encoding="utf-8")
        private = self.write("installed/schemas/local.json", {"const": 1})
        fixture = public.load_json(original / "examples/protocol-exchange/fixtures/state-event.json")
        source = builder_inputs.capture(installed)
        self.write("installed/schemas/local.json", {"const": 2})
        public_path = installed / "protocols/shared-state/schemas/state-event.schema.json"
        public_path.write_bytes(public_path.read_bytes() + b" ")
        with mock.patch.object(public, "ROOT", installed), runtime_snapshot.public_call():
            outer = runtime_snapshot.call_scope()
            outer["synthetic-scope-marker"] = True
            with mock.patch.object(Path, "read_bytes", side_effect=AssertionError("owned schema evaluation reopened a file")), \
                    state.schema_read_scope(source=source) as owner:
                self.assertIs(runtime_snapshot.call_scope(), outer)
                self.assertEqual(owner.validate(1, owner.read(private)), [])
                self.assertTrue(owner.validate(2, owner.read(private)))
                contracts = public.contract_set()
                self.assertIs(contracts, owner.contracts())
                self.assertTrue(public.validate_artifact(fixture, contracts=contracts)["ok"])
            self.assertIs(runtime_snapshot.call_scope(), outer)
            self.assertTrue(outer["synthetic-scope-marker"])
            with state.schema_read_scope(fresh=True) as current:
                self.assertEqual(current.validate(2, current.read(private)), [])
                with self.assertRaisesRegex(ValueError, "public schema byte hash mismatch"):
                    public.contract_set().schema_named("state-event.schema.json")


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
