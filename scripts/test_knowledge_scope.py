"""Scoped Commons wording remains separately retrievable from its source records.

This verifies record validity and retrieval surfaces, not whether an author
chooses or adapts the knowledge appropriately for a particular picture.
"""
from __future__ import annotations

import json
from pathlib import Path
import unittest
from unittest import mock

from audit_preset_quality import Record, check_atomic
from catalog_retrieval.retrieval import search_entries
from catalog_retrieval.runtime import Entry
from search_discovery import SearchIndex, build_search_profile
from state_protocol import validate_against_schema


ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILES = (
    "modules/aesthetic-touch.json", "modules/rendering-molded-vinyl.json",
    "modules/creature-anatomy-lineages.json", "modules/body-language-cue-tail-grammar.json",
    "presentation-scenes.json",
)


class KnowledgeScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.documents, cls.entries = [], []
        phrases, profiles = {}, {}
        for relative in SOURCE_FILES:
            path = ROOT / "packs/commons/records" / relative
            document = json.loads(path.read_text(encoding="utf-8"))
            cls.documents.append((relative, document))
            for record in document["records"]:
                entry = Entry(document["kind"], document.get("category"), record,
                              "scope-fixture", path.parent, path.name)
                cls.entries.append(entry)
                aliases = []
                for term in record.get("search_terms", []):
                    aliases.append(term["phrase"])
                    phrases.setdefault(term["phrase"], []).append({"id": record["id"], **term})
                profiles[record["id"]] = build_search_profile(entry.kind, entry.category, record, aliases)
        cls.index = SearchIndex({"records": profiles, "phrases": phrases})

    def lookup(self, query, kind, category=None):
        # The source-only fixture has no linked image assets. That display
        # lookup is independent of the production lexical ranking under test.
        with mock.patch("catalog_retrieval.retrieval.linked_asset_activation",
                        return_value={"asset_count": 0, "asset_ids": []}):
            hits = search_entries(self.entries, query, kinds={kind},
                                  categories={category} if category else set(),
                                  domain=None, limit=3, diverse=False, search_index=self.index)
        self.assertTrue(hits, query)
        return hits[0]

    def test_records_validate_and_keep_unique_identifiers(self):
        schema = json.loads((ROOT / "schemas/pack-record-file.schema.json").read_text(encoding="utf-8"))
        errors, warnings = [], []
        for relative, document in self.documents:
            self.assertEqual(validate_against_schema(document, schema), [], relative)
            for record in document["records"]:
                if document["kind"] == "module" and record.get("curation_status") == "curated":
                    check_atomic(Record(document["kind"], document["category"], record, relative), errors, warnings)
        self.assertEqual(errors, [])
        self.assertEqual(len({entry.record["id"] for entry in self.entries}), len(self.entries))

    def test_material_and_complete_display_have_separate_retrieval_surfaces(self):
        finish = self.lookup("designer toy finish", "module", "rendering")
        display = self.lookup("collectible toy display", "scene")
        self.assertEqual(finish["id"], "rendering-molded-vinyl-surface")
        self.assertEqual(display["id"], "aesthetic-touch-blind-box-presentation")
        self.assertEqual(finish["applies_to"], "material rendering on the selected subjects or regions")
        self.assertIn("the whole figure stays inside the frame for this complete display", display["must_preserve"])

    def test_kawaii_finish_and_character_presentation_are_distinct_choices(self):
        finish = self.lookup("kawaii style finish", "module", "aesthetic-touch")
        presentation = self.lookup("rounded character with large friendly eyes", "scene")
        self.assertEqual(finish["id"], "aesthetic-touch-kawaii-finish")
        self.assertEqual(presentation["id"], "scene-cheerful-kawaii-character-presentation")
        self.assertIn("selected expression", finish["prompt"])
        self.assertIn("large friendly eyes", presentation["image_promise"])

    def test_canid_construction_and_authored_tail_display_remain_separate(self):
        anatomy = self.lookup("canine muzzle ruff and paw pads", "module", "creature-anatomy")
        display = self.lookup("big fast tail wag for happiness", "module", "body-language-cue")
        self.assertEqual(anatomy["id"], "creature-anatomy-anthro-canine-lineage")
        self.assertEqual(display["id"], "body-language-cue-tail-wag-joy")
        self.assertEqual(anatomy["applies_to"], "the selected ruffed upright canid construction")
        self.assertIn("explicitly selected coordinated display", display["applies_to"])
        self.assertIn("root joins the surrounding coat", anatomy["prompt"])
        self.assertNotIn("wide, fast sweeping tail movement", anatomy["prompt"])


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
