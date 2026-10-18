#!/usr/bin/env python3
"""Commons offering integration, using shared cases and local synthetic media."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

import model_contract as mc
import prepare_generation_references as refs
import render_contract_lib as rendering
import transport_contract
from catalog_retrieval.runtime import using_pack_runtime
from pack_manager import PackSettings
from reference_delivery import bindings


ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "packs" / "commons"
CASES = Path(__file__).resolve().parent / "fixtures" / "model_capability_cases.json"
PROMPT = "A flat graphic of two distinct geometric figures beside one table. No text."


def put(value, path, item):
    parts = path.split(".")
    for key in parts[:-1]:
        value = value.setdefault(key, {})
    value[parts[-1]] = copy.deepcopy(item)


class ModelCapabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temporary = tempfile.TemporaryDirectory(prefix="cpb-model-capabilities-")
        cls.addClassCleanup(temporary.cleanup)
        cls.root = Path(temporary.name)
        cls.cases = json.loads(CASES.read_text(encoding="utf-8"))
        cls.fixtures = cls.cases["offerings"]
        cls.models = {}
        for path in sorted((PACK / "records").rglob("*.json")):
            document = json.loads(path.read_text(encoding="utf-8"))
            if document.get("kind") == "model":
                cls.models.update((row["id"], row) for row in document["records"])
        cls.offerings = {(model_id, offering["service"]): offering
                         for model_id, record in cls.models.items() for offering in record["offerings"]}
        cls.services = json.loads((PACK / "resources/service-profiles/services.json").read_text(encoding="utf-8"))["services"]
        cls.transports = {name: transport_contract.load(service["transport"])
                          for name, service in cls.services.items() if name in cls.cases["services"]}
        pack_id = json.loads((PACK / "pack.json").read_text(encoding="utf-8"))["pack_id"]
        state_file = cls.root / "pack-state.json"
        state_file.write_text(json.dumps({"pack_roots": [str(PACK)], "enabled_packs": [pack_id]}), encoding="utf-8")
        cls.enterClassContext(using_pack_runtime(PackSettings(
            roots=(PACK,), state_file=state_file, cache_dir=cls.root / "cache",
            managed_root=cls.root / "managed", quarantine_root=cls.root / "quarantine",
            default_enabled_packs=(pack_id,))))
        cls.sources, cls.source_hashes, cls.provider_ids = [], [], []
        total = max(row["reference_limit"] for row in cls.fixtures) + 1
        for index in range(total):
            path = cls.root / f"input-{total - index:02d}.png"
            Image.new("RGB", (128, 128), ((index >> 16) & 255, (index >> 8) & 255, index & 255)).save(path)
            cls.sources.append({"role": f"shape-{index}", "source": {"kind": "supplied-file",
                "reference_id": f"input-{index}", "resolved_path": str(path)}})
            cls.source_hashes.append(hashlib.sha256(path.read_bytes()).hexdigest())
            cls.provider_ids.append(f"00000000-0000-4000-8000-{index:012d}")

    def setUp(self):
        self.blocked = []
        for target in ("urllib.request.urlopen", "socket.create_connection"):
            self.blocked.append(self.enterContext(patch(target, side_effect=AssertionError("unexpected network call"))))
        for transport in self.transports.values():
            for name in ("send", "upload_bytes"):
                self.blocked.append(self.enterContext(patch.object(
                    transport, name, side_effect=AssertionError("unexpected provider operation"))))

    def tearDown(self):
        for blocked in self.blocked:
            blocked.assert_not_called()

    def offering(self, fixture):
        return self.offerings[fixture["model"], fixture["service"]]

    def compile(self, fixture, parameters=None, *, mode="text-to-image", references=0):
        intent = rendering.make_intent("flat-graphic", mode=mode, chosen_by="agent",
            reason="Synthetic contract validation.", presentation="single illustration", prompt_expression="flat graphic")
        return rendering.compile_contract(self.models[fixture["model"]], self.offering(fixture), intent,
            copy.deepcopy(self.cases["parameters"] if parameters is None else parameters),
            prompt=PROMPT, reference_count=references)

    def request(self, fixture, parameters=None, *, references=0, prompt=PROMPT):
        return mc.request_instance(self.offering(fixture),
            self.cases["parameters"] if parameters is None else parameters,
            prompt=prompt, media_counts={"reference images": references})

    def validate(self, fixture, request):
        mc.validate_request_instance(self.offering(fixture), request, PACK, fixture["model"])

    def assert_outcome(self, operation, accepted, error="."):
        if accepted:
            return operation()
        else:
            with self.assertRaisesRegex(ValueError, error):
                operation()

    def scenarios(self, fixture):
        yield from self.cases["common_cases"]
        for name in fixture["case_sets"]:
            yield from self.cases["case_sets"][name]

    def test_case_matrix_covers_every_commons_offering(self):
        keys = [(row["model"], row["service"]) for row in self.fixtures]
        self.assertTrue(keys)
        self.assertEqual(len(keys), len(set(keys)), "duplicate offering cases")
        self.assertEqual(set(keys), set(self.offerings), "commons offerings and validation cases must match")
        self.assertEqual({name for row in self.fixtures for name in row["case_sets"]}, set(self.cases["case_sets"]))
        for fixture in self.fixtures:
            cases = list(self.scenarios(fixture))
            self.assertTrue(cases)
            for case in cases:
                with self.subTest(model=fixture["model"], case=case["name"]):
                    self.assertIs(type(case["schema"]), bool)
                    if "profile" in case:
                        self.assertIs(type(case["profile"]), bool)

    def test_definition_identity_and_aliases(self):
        for fixture in self.fixtures:
            with self.subTest(model=fixture["model"]):
                record, offering = self.models[fixture["model"]], self.offering(fixture)
                self.assertEqual(offering["model_identifier"], fixture["model_identifier"])
                self.assertEqual(set(offering["execution_profile"]["modes"]), set(fixture["modes"]))
                self.assertEqual(record["supports_negative_prompt"], fixture["supports_negative_prompt"])
                self.assertEqual(record["negative_transport_mode"], fixture["negative_transport_mode"])
                for name in [fixture["model"], *fixture["aliases"], *record.get("aliases", [])]:
                    self.assertEqual(refs.resolve_model_record(name)[0], fixture["model"])
                self.assertEqual(refs.model_pack_root(fixture["model"]), PACK)

    def test_declared_modes_preserve_explicit_parameters(self):
        for fixture in self.fixtures:
            for mode, count in fixture["modes"].items():
                with self.subTest(model=fixture["model"], mode=mode):
                    contract = self.compile(fixture, mode=mode, references=count)
                    self.assertEqual(contract["parameters"], self.cases["parameters"], "an optional control was injected")
                    self.validate(fixture, self.request(fixture, contract["parameters"], references=count))

    def test_schema_target_and_negative_channel(self):
        for fixture in self.fixtures:
            fields = self.cases["services"][fixture["service"]]
            with self.subTest(model=fixture["model"], case="exact target"):
                request = self.request(fixture)
                put(request, fields["model"], "synthetic:incorrect-target")
                self.assert_outcome(lambda: self.validate(fixture, request), False)
            with self.subTest(model=fixture["model"], case="negative channel"):
                request = self.request(fixture)
                put(request, fields["negative"], "illegible text")
                self.assert_outcome(lambda: self.validate(fixture, request), fixture["supports_negative_prompt"])

    def test_request_text_and_reference_limits(self):
        for fixture in self.fixtures:
            low, high = fixture["prompt_length"]
            for length, accepted in ((low, True), (high, True), (low - 1, False), (high + 1, False)):
                with self.subTest(model=fixture["model"], prompt_length=length):
                    request = self.request(fixture, references=2, prompt="x" * length)
                    self.assert_outcome(lambda: self.validate(fixture, request), accepted)
            for count, accepted in ((fixture["reference_limit"], True), (fixture["reference_limit"] + 1, False)):
                with self.subTest(model=fixture["model"], references=count):
                    request = self.request(fixture, references=count)
                    self.assert_outcome(lambda: self.validate(fixture, request), accepted)

    def test_dispatch_count_and_seed_limits(self):
        for fixture in self.fixtures:
            contract = self.compile(fixture)
            low, high = fixture["output_count"]
            fields = self.cases["services"][fixture["service"]]
            for count, accepted in ((low, True), (high, True), (low - 1, False), (high + 1, False)):
                with self.subTest(model=fixture["model"], count=count):
                    actual = self.assert_outcome(lambda: rendering.dispatch_values(
                        contract, seed=fixture["dispatch_seed"], count=count), accepted)
                    if accepted:
                        self.assertEqual(actual, (fixture["dispatch_seed"], count))
                    request = self.request(fixture)
                    put(request, fields["count"], count)
                    self.assert_outcome(lambda: self.validate(fixture, request), accepted)
            for outcome, values in fixture["seed_values"].items():
                for seed in values:
                    with self.subTest(model=fixture["model"], seed=seed):
                        accepted = outcome == "accept"
                        actual = self.assert_outcome(lambda: rendering.dispatch_values(contract, seed=seed, count=low), accepted)
                        if accepted:
                            self.assertEqual(actual, (seed, low))
                        if seed is not None:
                            request = self.request(fixture)
                            put(request, fields["seed"], seed)
                            self.assert_outcome(lambda: self.validate(fixture, request), accepted)

    def test_capability_cases_against_schema_and_profile(self):
        for fixture in self.fixtures:
            for case in self.scenarios(fixture):
                parameters = copy.deepcopy(case.get("parameters", self.cases["parameters"]))
                for path, value in case.get("set", {}).items():
                    put(parameters, path, value)
                references = case.get("references", 0)
                request = self.request(fixture, parameters, references=references, prompt=case.get("prompt", PROMPT))
                with self.subTest(model=fixture["model"], case=case["name"], surface="schema"):
                    self.assert_outcome(lambda: self.validate(fixture, request), case["schema"])
                if "profile" in case:
                    with self.subTest(model=fixture["model"], case=case["name"], surface="profile"):
                        self.assert_outcome(lambda: self.compile(fixture, parameters,
                            mode=case.get("mode", "text-to-image"), references=references),
                            case["profile"], case.get("profile_error", "."))

    def test_prepared_media_and_wire_preserve_authored_order(self):
        original_ids = dict(zip(self.source_hashes, self.provider_ids, strict=True))
        for index, fixture in enumerate(self.fixtures):
            with self.subTest(model=fixture["model"]):
                count = fixture["reference_limit"]
                prepared = refs.prepare_references(copy.deepcopy(self.sources[:count]), model=fixture["model"],
                    output_dir=self.root / f"prepared-{index}")
                self.assertEqual(prepared["transport_mode"], "multi-image")
                self.assertIsNone(prepared["single_board"])
                rows = prepared["selected_references"]
                self.assertEqual([row["role"] for row in rows], [row["role"] for row in self.sources[:count]])
                self.assertEqual([row["source"]["sha256"] for row in rows], self.source_hashes[:count])
                self.assertEqual([row["transport"]["sha256"] for row in rows], self.source_hashes[:count])
                refs.validate_prepared_reference_set(prepared, model=fixture["model"])
                media_ids = {row["transport"]["resolved_path"]: original_ids[hashlib.sha256(
                    Path(row["transport"]["resolved_path"]).read_bytes()).hexdigest()] for row in rows}
                for overrides in ({}, fixture["wire_parameters"]):
                    with self.subTest(parameters=overrides):
                        parameters = copy.deepcopy(self.cases["parameters"])
                        for path, value in overrides.items():
                            put(parameters, path, value)
                        self.assert_wire(fixture, prepared, media_ids, parameters)

    def assert_wire(self, fixture, prepared, media_ids, parameters):
        count = fixture["reference_limit"]
        contract = self.compile(fixture, parameters, mode="reference-guided", references=count)
        verified = {"host_forwarding": {
            "effective_prompt": PROMPT, "parameters": contract["parameters"],
            "selected_transport": {"mode": fixture["negative_transport_mode"], "rendition": {"text": PROMPT}},
            "selected_references": refs.host_reference_transports(prepared),
            "reference_media_role": "references", "native_reference_controls": []},
            "bindings": bindings(prepared["transport_mode"], prepared["selected_references"], prepared["single_board"])}
        compiled = self.transports[fixture["service"]].compile_request(
            verified, self.offering(fixture), self.services[fixture["service"]], media_ids,
            seed=fixture["dispatch_seed"], count=2)
        wire = copy.deepcopy(compiled["request"])
        fields = self.cases["services"][fixture["service"]]
        for name in fields["management_fields"]:
            self.assertTrue(wire.pop(name))
        expected = copy.deepcopy(parameters)
        for role, value in (("model", fixture["model_identifier"]), ("prompt", PROMPT),
                            ("references", self.provider_ids[:count]), ("count", 2)):
            put(expected, fields[role], value)
        if fixture["dispatch_seed"] is not None:
            put(expected, fields["seed"], fixture["dispatch_seed"])
        for path, value in fields["fixed_fields"].items():
            put(expected, path, value)
        self.assertEqual(wire, expected)
        rendering.check_wire(contract, compiled["request"], compiled["layout"], seed=fixture["dispatch_seed"], count=2)
        for name in fields["fixed_fields"]:
            wire.pop(name)
        self.validate(fixture, wire)

    def test_preparation_and_request_limit_boundaries(self):
        for index, fixture in enumerate(self.fixtures):
            with self.subTest(model=fixture["model"]):
                limit = fixture["preparation_limit"]
                count = (fixture["reference_limit"] if limit is None else limit) + 1
                prepared = self.assert_outcome(lambda: refs.prepare_references(copy.deepcopy(self.sources[:count]),
                    model=fixture["model"], output_dir=self.root / f"over-limit-{index}"), limit is None)
                if prepared is not None:
                    self.assertEqual(len(prepared["selected_references"]), count)
                    self.assert_outcome(lambda: self.validate(fixture, self.request(fixture, references=count)), False)


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main(verbosity=2)
