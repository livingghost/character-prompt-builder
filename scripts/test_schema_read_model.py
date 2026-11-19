"""Owned schema inputs and shared evaluation using synthetic JSON documents."""
from __future__ import annotations
import read_context

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


class SchemaReadModelTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="schema-read-model-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
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

    def test_character_sheet_uses_the_acquired_schema_and_exports_independent_values(self):
        import character_sheet
        relative = 'schemas/character-sheet-data.schema.json'
        schema = {'type': 'object', 'properties': {'marker': {'const': 'first'}}, 'required': ['marker']}
        source = builder_inputs.BuilderInputs(self.root, (
            builder_inputs.FileInput(relative, json.dumps(schema).encode('utf-8')),))
        value = {'marker': 'first', 'sheet_status': 'draft', 'slots': {}, 'fields': {}, 'tables': {}}
        with mock.patch.object(character_sheet, 'SCHEMA_PATH', self.root / relative), \
                mock.patch.object(Path, 'read_bytes', side_effect=AssertionError('Use acquired schema bytes')), \
                state.schema_read_scope(source=source):
            one = character_sheet.validate_sidecar(value)
            two = character_sheet.validate_sidecar(value)
        one['fields']['identity.name'] = 'Private edit'
        self.assertEqual(two, value)
        self.assertNotEqual(one, value)

    def test_character_sheet_acquires_once_per_phase_and_observes_a_later_schema(self):
        import character_sheet
        schema = self.write('sheet.json', {'type': 'object', 'properties': {'marker': {'const': 'first'}}})
        value = {'marker': 'first', 'sheet_status': 'draft', 'slots': {}, 'fields': {}, 'tables': {}}
        original = Path.read_bytes
        reads = []
        def read(path):
            if path == schema:
                reads.append(path)
            return original(path)
        with mock.patch.object(character_sheet, 'SCHEMA_PATH', schema), mock.patch.object(Path, 'read_bytes', read):
            with state.schema_read_scope():
                for _ in range(5):
                    self.assertEqual(character_sheet.validate_sidecar(value), value)
            self.write('sheet.json', {'type': 'object', 'properties': {'marker': {'const': 'later'}}})
            with state.schema_read_scope(), self.assertRaisesRegex(ValueError, 'expected constant'):
                character_sheet.validate_sidecar(value)
        self.assertEqual(reads, [schema, schema])

    def test_definition_consumers_share_acquired_schemas_without_live_fallback(self):
        from contextlib import ExitStack
        import authoring_work
        import model_prompt_input
        import prompt_dialect
        import prompt_plot
        import prompt_retrieval
        import prompt_vocabulary_selection
        import story_context
        import world_realization
        from pack_manager import PackError
        root = Path(state.__file__).resolve().parents[1]
        paths = {authoring_work.SCHEMA, model_prompt_input.SCHEMA_PATH, prompt_dialect.SCHEMA_PATH,
                 prompt_plot.SCHEMA_PATH, root / 'schemas/prompt-vocabulary-selection.schema.json',
                 story_context.SCHEMA, world_realization.SCHEMA}
        source = builder_inputs.BuilderInputs(root, tuple(builder_inputs.FileInput(
            path.relative_to(root).as_posix(), b'{"const":"synthetic accepted value"}') for path in paths))
        self.write('input.json', {})
        source_reads = []
        original = builder_inputs.BuilderInputs.read_bytes
        def acquired(owner, path):
            source_reads.append(Path(path))
            return original(owner, path)
        read_bytes, read_text = Path.read_bytes, Path.read_text
        def bytes_from_disk(path):
            if path in paths:
                raise AssertionError('A definition consumer reopened its acquired schema')
            return read_bytes(path)
        def text_from_disk(path, *args, **kwargs):
            if path in paths:
                raise AssertionError('A definition consumer reopened its acquired schema')
            return read_text(path, *args, **kwargs)
        with ExitStack() as contexts:
            contexts.enter_context(mock.patch.object(builder_inputs.BuilderInputs,'read_bytes',acquired))
            contexts.enter_context(mock.patch.object(Path,'read_bytes',bytes_from_disk))
            contexts.enter_context(mock.patch.object(Path,'read_text',text_from_disk))
            contexts.enter_context(state.schema_read_scope(source=source))
            self.assertIn('expected constant', str(authoring_work.validate_work({})))
            for validate in (model_prompt_input.validate_prompt_input,prompt_dialect.validate_dialects):
                with self.assertRaisesRegex((ValueError,PackError),'expected constant'):
                    validate({})
            self.assertIn('expected constant', str(prompt_plot.schema_errors({})))
            self.assertIn('expected constant', str(prompt_retrieval.validate_prompt_retrieval_record(
                {'artifact_type':'prompt-retrieval-record','elements':[],'vocabulary':{}})))
            # Isolate dictionary discovery; the previous selection's real schema check remains active.
            with mock.patch.object(prompt_vocabulary_selection,'resolve_prompt_input',return_value={'mode':'tag-based'}), \
                    mock.patch.object(prompt_vocabulary_selection,'_resources',return_value=([],{},{})), \
                    self.assertRaisesRegex(ValueError,'expected constant'):
                prompt_vocabulary_selection.search_selection(prompt='',negative='',syntax='literal',
                    model_record={'id':'synthetic','prompt_dialect':'synthetic'},previous={})
            for load in (story_context.load_query,world_realization.load_plan):
                with self.assertRaisesRegex(ValueError,'expected constant'):
                    load(self.root,'input.json')
        self.assertEqual(Counter(source_reads),Counter({path:1 for path in paths}))
        with state.schema_read_scope(source=builder_inputs.BuilderInputs(root, ())):
            self.assertIn('not in the acquired implementation',str(prompt_plot.schema_errors({})))

    def test_production_specification_schema_follows_the_current_read_phase(self):
        import production_spec
        path = self.write('specification.json',{'type':'object','properties':{'marker':{'const':'first'}}})
        value = {'marker':'first'}
        with mock.patch.object(production_spec,'SCHEMA_PATH',path):
            with state.schema_read_scope():
                self.assertTrue(production_spec.validate(value)['ok'])
                self.write('specification.json',{'type':'object','properties':{'marker':{'const':'later'}}})
                self.assertTrue(production_spec.validate(value)['ok'])
            with state.schema_read_scope():
                report = production_spec.validate(value)
                self.assertFalse(report['ok'])
                self.assertIn('expected constant',str(report['errors']))

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

    def test_any_of_reads_alternatives_until_one_matches_and_keeps_failure_details(self):
        source = self.write("alternatives.json", {
            "anyOf": [{"const": "selected"}, {"$ref": "./unavailable.json"}],
            "maxLength": 4})
        with state.schema_read_scope() as owner:
            document = owner.read(source)
            self.assertEqual(owner.validate("selected", document), ["$: string is longer than maxLength"])
            with self.assertRaises(FileNotFoundError):
                owner.validate("other", document)
        self.write("alternatives.json", {
            "anyOf": [{"const": "selected"}, {"unknown-constraint": True}]})
        with state.schema_read_scope() as owner, self.assertRaisesRegex(ValueError, r"\$\.anyOf\[1\]\.unknown-constraint"):
            owner.read(source)
        schema = {"anyOf": [{"const": 1}, {"const": 2}]}
        for validate in (public.validate_against_schema, state.validate_against_schema):
            self.assertEqual(validate(3, schema), [
                "$: value matches none of the 2 alternatives: expected constant 1; or expected constant 2"])
            self.assertEqual(validate(1, {"anyOf": []}),
                             ["$: value matches none of the 0 alternatives"])
            self.assertEqual(validate(1, {"oneOf": [{"type": "number"}, {"type": "integer"}]}),
                             ["$: value matches 2 of the 2 alternatives; exactly one must match"])

    def test_empty_constraints_and_scalar_types_keep_their_validation_meaning(self):
        cases = [
            (1, {"not": {}}, ["$: value satisfies a forbidden schema"]),
            (2, {"if": {}, "then": {"const": 1}}, ["$: expected constant 1"]),
            ([], {"contains": {}}, ["$: no item satisfies contains"]),
            ([float('nan')], {"items": {}}, ["$[0]: number must be finite"]),
            ({"extra": float('nan')}, {"additionalProperties": {}}, ["$.extra: number must be finite"]),
            (True, {"type": "integer"}, ["$: expected type ['integer'], got bool"]),
            (True, {"type": ["integer", "null"]}, ["$: expected type ['integer', 'null'], got bool"]),
            ({"z": "bad", "a": "bad", "declared": "bad"},
             {"properties": {"declared": {"type": "integer"}}, "additionalProperties": {"type": "integer"}},
             ["$.declared: expected type ['integer'], got str", "$.a: expected type ['integer'], got str",
              "$.z: expected type ['integer'], got str"]),
            ({"z": 1, "a": 2}, {"additionalProperties": False},
             ["$: unexpected properties ['a', 'z']; permitted properties []"]),
        ]
        for value, schema, expected in cases:
            for validate in (public.validate_against_schema, state.validate_against_schema):
                with self.subTest(value=value, schema=schema, evaluator=validate.__module__):
                    self.assertEqual(validate(value, schema), expected)

    def test_alternatives_stop_rejected_kinds_before_walking_their_records(self):
        branches = [{'properties': {'kind': {'const': kind}, 'records': {
            'type': 'array', 'items': {'type': 'integer', 'minimum': 1}}}}
            for kind in ('one', 'two', 'three', 'selected')]
        document = public.SchemaDocument({'oneOf': branches})
        value = {'kind': 'selected', 'records': [1] * 80}
        visit = public._validate_schema
        paths = []

        def observe(instance, schema, path, root, **options):
            paths.append(path)
            return visit(instance, schema, path, root, **options)

        with mock.patch.object(public, '_validate_schema', observe):
            self.assertEqual(public.validate_against_schema(value, document), [])
        # A selected record is inspected once, independent of how many other
        # record kinds the container permits.
        self.assertEqual(sum(path.startswith('$.records[') for path in paths), 80)
        value['records'][-1] = 0
        self.assertEqual(public.validate_against_schema(value, document), [
            '$: value matches none of the 4 alternatives: '
            "$.kind: expected constant 'one'; or $.kind: expected constant 'two'; or "
            "$.kind: expected constant 'three'; or $.records[79]: value is below minimum 1"])
        value['kind'] = 'one'
        value['records'][-1] = 2
        self.assertEqual(public.validate_against_schema(value, document), [])

    def test_predicates_keep_first_diagnostics_and_full_validation_keeps_all(self):
        definitions = {'record': {'type': 'object', 'required': ['first', 'second'],
            'properties': {'count': {'type': 'integer', 'minimum': 1},
                           'title': {'minLength': 3, 'pattern': '^valid$'}}}}
        branch = {'$ref': '#/$defs/record', 'maxProperties': 0}
        value = {'count': 0, 'title': 'x'}
        self.assertEqual(public.validate_against_schema(value, {'$defs': definitions, **branch}), [
            "$: missing required property 'first'", "$: missing required property 'second'",
            '$.count: value is below minimum 1', '$.title: string is shorter than minLength',
            "$.title: string does not match pattern '^valid$'",
            '$: object has more properties than maxProperties'])
        for keyword in ('anyOf', 'oneOf'):
            with self.subTest(keyword=keyword):
                self.assertEqual(public.validate_against_schema(value,
                    {'$defs': definitions, keyword: [branch, {'allOf': [branch]}]}), [
                    '$: value matches none of the 2 alternatives: '
                    "missing required property 'first'; or missing required property 'first'"])

    def test_conditions_skip_reference_work_after_a_decisive_mismatch(self):
        condition = {'properties': {'kind': {'const': 'other'},
                                    'payload': {'$ref': './unvisited.json'}}}
        source = self.write('conditional.json', {'if': condition,
            'then': {'const': 'unreachable'}, 'else': {'properties': {'payload': {'type': 'integer'}}}})
        with state.schema_read_scope() as owner:
            document = owner.read(source)
            self.assertEqual(owner.validate({'kind': 'selected', 'payload': 1}, document), [])
            self.assertEqual(owner.validate({'kind': 'selected', 'payload': 'bad'}, document),
                             ["$.payload: expected type ['integer'], got str"])
            with self.assertRaises(FileNotFoundError):
                owner.validate({'kind': 'other', 'payload': 1}, document)

    def test_one_of_still_counts_every_matching_branch_and_semantic_failures(self):
        schema = {'oneOf': [{'type': 'number'}, {'type': 'integer'}, {'minimum': 0},
                            {'$id': 'synthetic-semantic-check'}]}
        check = mock.Mock(return_value=['$: first semantic error', '$: second semantic error'])
        self.assertEqual(public.validate_against_schema(1, schema,
            semantic_checks={'synthetic-semantic-check': check}), [
                '$: value matches 3 of the 4 alternatives; exactly one must match'])
        check.assert_called_once_with(1, '$')
        self.assertEqual(public.validate_against_schema(1, {'$id': 'synthetic-semantic-check'},
            semantic_checks={'synthetic-semantic-check': check}),
            ['$: first semantic error', '$: second semantic error'])

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

    def test_dispatch_plans_belong_to_owned_schema_nodes_and_preserve_changed_input_checks(self):
        schema = {'type': 'array', 'items': {'type': 'object', 'required': ['mode', 'count'],
            'properties': {'mode': {'enum': ['draft', 'ready']}, 'count': {'type': 'integer', 'minimum': 1}},
            'additionalProperties': False}}
        document = public.SchemaDocument(schema)
        rows = [{'mode': 'ready', 'count': 3} for _ in range(100)]
        with mock.patch.object(public, '_SchemaPlan', wraps=public._SchemaPlan) as planned:
            self.assertEqual(public.validate_against_schema(rows, document), [])
            acquired = planned.call_count
            self.assertEqual(acquired, 4)
            rows[45]['count'] = 0
            self.assertEqual(public.validate_against_schema(rows, document),
                             ['$[45].count: value is below minimum 1'])
            self.assertEqual(planned.call_count, acquired)
        schema['items']['properties']['count']['minimum'] = 5
        self.assertEqual(public.validate_against_schema([{'mode': 'ready', 'count': 3}], document), [])
        self.assertEqual(public.validate_against_schema([{'mode': 'ready', 'count': 3}], schema),
                         ['$[0].count: value is below minimum 5'])

    def test_plans_keep_known_keyword_errors_lazy_and_check_unconstrained_nonfinite_numbers(self):
        schema = public.SchemaDocument({'anyOf': [{}, {'minLength': 'invalid limit'}],
            'if': {'type': 'number'}, 'then': {'multipleOf': 2}, 'else': {'type': 'string'}})
        self.assertEqual(public.validate_against_schema('selected', schema), [])
        self.assertEqual(public.validate_against_schema(3, schema), ['$: value is not a multiple of 2'])
        with self.assertRaises(ValueError):
            public.validate_against_schema('selected', {'minLength': 'invalid limit'})
        self.assertEqual(public.validate_against_schema(float('inf'), {}), ['$: number must be finite'])
        self.assertEqual(public.validate_against_schema(float('nan'), {'type': 'string'}),
                         ["$: expected type ['string'], got float"])

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
        with mock.patch.object(public, "ROOT", installed), read_context.public_call():
            outer = read_context.call_scope()
            outer["synthetic-scope-marker"] = True
            with mock.patch.object(Path, "read_bytes", side_effect=AssertionError("owned schema evaluation reopened a file")), \
                    state.schema_read_scope(source=source) as owner:
                self.assertIs(read_context.call_scope(), outer)
                self.assertEqual(owner.validate(1, owner.read(private)), [])
                self.assertTrue(owner.validate(2, owner.read(private)))
                contracts = public.contract_set()
                self.assertIs(contracts, owner.contracts())
                self.assertTrue(public.validate_artifact(fixture, contracts=contracts)["ok"])
            self.assertIs(read_context.call_scope(), outer)
            self.assertTrue(outer["synthetic-scope-marker"])
            with state.schema_read_scope(fresh=True) as current:
                self.assertEqual(current.validate(2, current.read(private)), [])
                with self.assertRaisesRegex(ValueError, "public schema byte hash mismatch"):
                    public.contract_set().schema_named("state-event.schema.json")


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
