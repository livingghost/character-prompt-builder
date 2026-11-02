#!/usr/bin/env python3
"""Exercise explicit model input modes, evidence, and model-facing reports."""
from __future__ import annotations

import argparse
import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import model_prompt_input as inputs
import prompt_dialect
from render_contract_lib import model_card
from state_protocol import validate_against_schema


def record(mode: str = "descriptive") -> dict:
    """A synthetic declaration; it is not evidence about a provider model."""
    value = {
        "id": "synthetic-input-model",
        "label": "Synthetic input model",
        "aliases": [],
        "operation_kind": "generation",
        "prompt_style": "Synthetic input choices for contract tests.",
        "ordering": ["subject", "action"],
        "search_terms": [],
        "offerings": [],
        "supports_negative_prompt": False,
        "negative_transport_mode": "integrated-critical",
        "negative_transport_notes": "Synthetic single text input.",
        "prompt_input": {
            "mode": mode,
            "forms": ["tags"] if mode == "tag-based" else ["natural-language"] if mode == "descriptive" else [],
            "vocabularies": ["fixture-vocabulary"] if mode == "tag-based" else [],
            "basis": [{
                "kind": "synthetic-fixture",
                "source": "Synthetic model-input contract fixture.",
                "scope": "model",
                "observed_at": "2026-01-01",
                "statement": "This fixture explicitly selects its input workflow.",
            }],
        },
    }
    if mode == "tag-based":
        value["prompt_dialect"] = "fixture-family"
    return value


class PromptInputTests(unittest.TestCase):
    def test_each_declared_mode_is_preserved(self):
        for mode in ("tag-based", "descriptive", "unresolved", "none"):
            with self.subTest(mode=mode):
                target = record(mode)
                self.assertEqual(inputs.resolve_prompt_input(target), target["prompt_input"])
                card = inputs.prompt_input_card(target)
                self.assertEqual(card["prompt_input"]["mode"], mode)
                self.assertEqual(card["requires_vocabulary_search"], mode == "tag-based")

    def test_tag_workflow_retains_supported_prose_and_every_vocabulary(self):
        target = record("tag-based")
        target["prompt_input"]["forms"].append("natural-language")
        target["prompt_input"]["vocabularies"].append("another-vocabulary")
        card = inputs.prompt_input_card(target)
        self.assertTrue(card["requires_vocabulary_search"])
        self.assertEqual(card["prompt_input"], target["prompt_input"])

    def test_structured_caption_remains_an_explicit_input_form(self):
        target = record()
        target["prompt_input"]["forms"].append("structured-caption")
        card = inputs.prompt_input_card(target)
        self.assertEqual(card["prompt_input"]["forms"], ["natural-language", "structured-caption"])

    def test_resolution_does_not_share_mutable_evidence(self):
        target = record()
        resolved = inputs.resolve_prompt_input(target)
        resolved["basis"][0]["statement"] = "A changed result does not change the record."
        self.assertNotEqual(target["prompt_input"]["basis"], resolved["basis"])

    def test_input_mode_and_owned_family_are_consistent(self):
        target = record("tag-based")
        target["prompt_dialect"] = ""
        with self.assertRaises(ValueError):
            inputs.resolve_prompt_input(target)
        target = record("descriptive")
        target["prompt_dialect"] = "fixture-family"
        with self.assertRaises(ValueError):
            inputs.resolve_prompt_input(target)

    def test_declared_input_forms_and_vocabulary_scope_are_consistent(self):
        changes = [
            ("tag-based", "forms", ["natural-language"]),
            ("tag-based", "vocabularies", []),
            ("descriptive", "forms", []),
            ("descriptive", "forms", ["tags"]),
            ("descriptive", "forms", ["natural-language", "tags"]),
            ("descriptive", "vocabularies", ["fixture-vocabulary"]),
            ("unresolved", "forms", ["natural-language"]),
            ("none", "vocabularies", ["fixture-vocabulary"]),
        ]
        for mode, field, value in changes:
            with self.subTest(mode=mode, field=field):
                target = record(mode)["prompt_input"]
                target[field] = value
                with self.assertRaises(ValueError):
                    inputs.validate_prompt_input(target)

    def test_evidence_identifies_its_source_scope_and_calendar_date(self):
        for field, value in (("source", " "), ("statement", ""),
                             ("scope", "unspecified"), ("observed_at", "2026-02-30")):
            with self.subTest(field=field):
                target = record()["prompt_input"]
                target["basis"][0][field] = value
                with self.assertRaises(ValueError):
                    inputs.validate_prompt_input(target)

    def test_pack_schema_enforces_the_same_declared_workflow(self):
        schema = json.loads((inputs.SCHEMA_PATH.parent / "pack-record-file.schema.json").read_text(encoding="utf-8"))
        for mode in ("tag-based", "descriptive", "unresolved", "none"):
            target = record(mode)
            with self.subTest(mode=mode):
                self.assertEqual(validate_against_schema({"kind": "model", "records": [target]}, schema), [])
        invalid = record("tag-based")
        invalid["prompt_input"]["vocabularies"] = []
        self.assertTrue(validate_against_schema({"kind": "model", "records": [invalid]}, schema))

    def test_public_model_card_exposes_input_and_basis(self):
        target = record("unresolved")
        with patch("model_suitability.guidance_card", return_value={}):
            card = model_card(target)
        self.assertEqual(card["prompt_input"], target["prompt_input"])
        self.assertEqual(card["prompt_input"]["mode"], "unresolved")
        self.assertFalse(card["requires_vocabulary_search"])

    def report(self, target: dict | None) -> dict:
        args = argparse.Namespace(model=target["id"] if target else None,
                                  dialect=None if target else "fixture-family", list=False,
                                  dialects=None, guide=None, weighting=None, service=None, mode=None)
        output = io.StringIO()
        with patch("prepare_generation_references.resolve_model_record", return_value=(args.model, target)), \
             patch.object(prompt_dialect, "resolve_resource", return_value=None), \
             patch.object(prompt_dialect, "find_dialect", return_value={"id": "fixture-family"}), \
             patch("model_suitability.guidance_card", return_value={}), redirect_stdout(output):
            self.assertEqual(prompt_dialect.render_report(args, None), 0)
        return json.loads(output.getvalue())

    def test_dialect_report_preserves_all_input_modes_and_evidence(self):
        for mode in ("tag-based", "descriptive", "unresolved", "none"):
            with self.subTest(mode=mode):
                target = record(mode)
                report = self.report(target)
                self.assertEqual(report["prompt_input"], target["prompt_input"])
                self.assertEqual(report["requires_vocabulary_search"], mode == "tag-based")
                self.assertEqual(report["execution_guidance"][0]["prompt_input"], target["prompt_input"])

    def test_family_inspection_does_not_claim_a_selected_model(self):
        report = self.report(None)
        self.assertIsNone(report["model"])
        self.assertIsNone(report["prompt_input"])
        self.assertIsNone(report["requires_vocabulary_search"])
        self.assertEqual(report["dialect"]["id"], "fixture-family")


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
