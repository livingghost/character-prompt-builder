#!/usr/bin/env python3
"""Focused regression tests for facet-aware search discovery."""
from __future__ import annotations

import re
import unittest

from search_discovery import (
    COLOR_TERMS,
    FACET_BY_CATEGORY,
    SearchIndex,
    _COLOR_CONTEXT_TARGETS,
    _color_context_patterns,
    _color_word_pattern,
    _find_color_contexts,
    _normalized_sentence_boundaries,
    analyze_query,
    extract_record_facets,
    normalize_query,
)


def _row(
    record_id: str,
    facet: str,
    *,
    source: str = "label",
    weight: float = 1.0,
) -> dict[str, object]:
    return {
        "id": record_id,
        "facet": facet,
        "source": source,
        "weight": weight,
    }


class SearchDiscoveryTest(unittest.TestCase):
    @staticmethod
    def _modifier_scope_index() -> SearchIndex:
        return SearchIndex({
            "records": {},
            "phrases": {
                "black panther": [
                    _row("fixture-species-shadow-cat", "species", source="label")
                ],
                "anthropomorphic": [
                    _row("body-build-anthropomorphic", "body_build", source="label")
                ],
                "broad": [
                    _row("body-build-broad", "body_build", source="label")
                ],
                "crown clumps": [
                    _row("hair-style-crown-clumps", "hair_style", source="label")
                ],
                "athletic": [
                    _row("body-build-athletic", "body_build", source="label")
                ],
                "shorts": [
                    _row("outfit-athletic-shorts", "wardrobe", source="label")
                ],
                "muscular": [
                    _row("body-build-muscular", "body_build", source="label")
                ],
                "maintenance robot": [
                    _row("fixture-subject-service-automaton", "species", source="label")
                ],
                "tall": [
                    _row("proportion-tall", "proportion", source="label")
                ],
                # Deliberately associate the same color with every relevant
                # facet. The explicit governed noun must resolve the scope.
                "blue": [
                    _row("coat-palette-blue", "coat_palette", source="label"),
                    _row("eye-feature-blue", "eye_feature", source="label"),
                    _row("lighting-blue", "lighting", source="label"),
                    _row("outfit-blue", "wardrobe", source="label"),
                    _row("environment-blue", "environment", source="label"),
                ],
            },
        })

    def test_domain_word_cannot_become_a_species_build_modifier(self) -> None:
        analysis = analyze_query(
            "anthropomorphic black panther",
            self._modifier_scope_index(),
        )

        self.assertEqual("anthropomorphic-animal", analysis.domain)
        self.assertEqual(
            ["anthropomorphic-animal"], analysis.anchors.get("domain")
        )
        self.assertEqual(["black panther"], analysis.anchors.get("species"))
        self.assertNotIn("body_build", analysis.anchors)
        self.assertEqual(
            {"domain"}, analysis.scoped_terms.get("anthropomorphic", set())
        )

    def test_explicit_hair_and_wardrobe_heads_own_ambiguous_build_words(self) -> None:
        index = self._modifier_scope_index()

        hair = analyze_query("broad crown clumps", index)
        wardrobe = analyze_query("athletic shorts", index)

        self.assertNotIn("body_build", hair.anchors)
        self.assertIn("head_hair", hair.scoped_terms.get("broad", set()))
        self.assertEqual(["broad crown clumps"], hair.anchors.get("head_hair"))
        self.assertEqual(["crown clumps"], hair.anchors.get("hair_style"))
        self.assertNotIn("body_build", wardrobe.anchors)
        self.assertIn("wardrobe", wardrobe.scoped_terms.get("athletic", set()))
        self.assertEqual(
            ["athletic shorts", "shorts"], wardrobe.anchors.get("wardrobe")
        )

        hair_evidence = next(
            row for row in hair.anchor_evidence
            if row["facet"] == "head_hair" and row["value"] == "broad crown clumps"
        )
        self.assertEqual("clumps", hair_evidence["governed_noun"])
        self.assertEqual(
            {"start": 0, "end": 18, "text": "broad crown clumps"},
            hair_evidence["source_span"],
        )
        wardrobe_evidence = next(
            row for row in wardrobe.anchor_evidence
            if row["facet"] == "wardrobe" and row["value"] == "athletic shorts"
        )
        self.assertEqual("shorts", wardrobe_evidence["governed_noun"])
        self.assertEqual(
            {"start": 0, "end": 15, "text": "athletic shorts"},
            wardrobe_evidence["source_span"],
        )

    def test_explicit_species_build_and_proportion_modifiers_are_preserved(self) -> None:
        index = self._modifier_scope_index()

        muscular = analyze_query("muscular black panther", index)
        tall = analyze_query("tall maintenance robot", index)

        self.assertEqual(["muscular"], muscular.anchors.get("body_build"))
        self.assertEqual(["black panther"], muscular.anchors.get("species"))
        muscular_evidence = next(
            row for row in muscular.anchor_evidence
            if row["facet"] == "body_build" and row["value"] == "muscular"
        )
        self.assertEqual("black panther", muscular_evidence["governed_noun"])
        self.assertEqual(
            {"start": 0, "end": 8, "text": "muscular"},
            muscular_evidence["source_span"],
        )

        self.assertEqual(["tall"], tall.anchors.get("proportion"))
        self.assertEqual(["maintenance robot"], tall.anchors.get("species"))
        tall_evidence = next(
            row for row in tall.anchor_evidence
            if row["facet"] == "proportion" and row["value"] == "tall"
        )
        self.assertEqual("maintenance robot", tall_evidence["governed_noun"])
        self.assertEqual(
            {"start": 0, "end": 4, "text": "tall"},
            tall_evidence["source_span"],
        )

    def test_build_modifiers_govern_a_species_behind_unknown_words(self) -> None:
        index = self._modifier_scope_index()

        for query in ("muscular young black panther", "muscular armored black panther"):
            with self.subTest(query=query):
                analysis = analyze_query(query, index)
                self.assertEqual(["black panther"], analysis.anchors.get("species"))
                self.assertEqual(["muscular"], analysis.anchors.get("body_build"))
                self.assertNotIn("muscular", analysis.terms_without_alias)
                self.assertEqual([], analysis.modifier_scope_evidence)

        for query in ("broad built black panther", "broad-built black panther"):
            with self.subTest(query=query):
                analysis = analyze_query(query, index)
                self.assertEqual(["broad built"], analysis.anchors.get("body_build"))
                self.assertEqual([], analysis.terms_without_alias)
                self.assertEqual([], analysis.modifier_scope_evidence)

        wardrobe = analyze_query("athletic shorts black panther", index)
        self.assertEqual({"wardrobe"}, wardrobe.scoped_terms.get("athletic"))
        self.assertIsNone(wardrobe.anchors.get("body_build"))

        hair = analyze_query("broad crown clumps", index)
        self.assertEqual(["crown clumps"], hair.anchors.get("hair_style"))

        robot = analyze_query("tall maintenance robot", index, "robot")
        self.assertEqual(["tall"], robot.anchors.get("proportion"))

    def test_color_modifiers_bind_to_the_head_of_the_noun_phrase(self) -> None:
        index = self._modifier_scope_index()

        for query, color in (("blue head hair", "blue"), ("black head hair", "black")):
            with self.subTest(query=query):
                analysis = analyze_query(query, index)
                self.assertEqual([color], analysis.anchors.get("hair_color"))
                self.assertEqual(["head hair"], analysis.anchors.get("head_hair"))
                self.assertNotIn(color, analysis.terms_without_alias)

        jacket = analyze_query("blue field jacket", index)
        jacket_rows = [
            row for row in jacket.anchor_evidence if row["value"] == "blue"
        ]
        self.assertTrue(jacket_rows)
        self.assertEqual({"wardrobe"}, {row["facet"] for row in jacket_rows})
        self.assertIn(
            "field jacket", {row.get("governed_noun") for row in jacket_rows}
        )
        self.assertIsNone(jacket.anchors.get("environment"))

        expected = {
            "blue fur": ("coat_palette", "fur"),
            "blue eyes": ("eye_feature", "eyes"),
            "blue background": ("environment", "background"),
            "blue jacket": ("wardrobe", "jacket"),
            "fur is blue": ("coat_palette", "fur"),
        }
        for query, (facet, governed_noun) in expected.items():
            with self.subTest(query=query):
                analysis = analyze_query(query, index)
                row = next(
                    row
                    for row in analysis.anchor_evidence
                    if row["value"] == "blue" and row.get("governed_noun")
                )
                self.assertEqual(facet, row["facet"])
                self.assertEqual(governed_noun, row["governed_noun"])

    def test_color_scope_is_owned_by_the_explicit_governed_noun(self) -> None:
        index = self._modifier_scope_index()
        expected = {
            "blue fur": ("coat_palette", "fur"),
            "blue eyes": ("eye_feature", "eyes"),
            "blue lighting": ("lighting", "lighting"),
            "blue clothing": ("wardrobe", "clothing"),
            "blue room": ("environment", "room"),
        }

        for query, (facet, governed_noun) in expected.items():
            with self.subTest(query=query):
                analysis = analyze_query(query, index)
                self.assertEqual(["blue"], analysis.anchors.get(facet))
                self.assertEqual({facet}, analysis.scoped_terms.get("blue"))
                for other_facet, _noun in expected.values():
                    if other_facet != facet:
                        self.assertNotIn(other_facet, analysis.anchors)
                evidence = next(
                    row for row in analysis.anchor_evidence
                    if row["facet"] == facet and row["value"] == "blue"
                )
                self.assertEqual(governed_noun, evidence["governed_noun"])
                self.assertEqual(
                    {"start": 0, "end": len(query), "text": query},
                    evidence["source_span"],
                )

    def test_modifier_scope_stops_at_prepositions_and_sentence_boundaries(self) -> None:
        index = self._modifier_scope_index()

        for query in ("athletic near blue shorts", "athletic. blue shorts"):
            with self.subTest(query=query):
                analysis = analyze_query(query, index)
                self.assertEqual(["athletic"], analysis.anchors.get("body_build"))
                self.assertIn("blue", analysis.anchors.get("wardrobe", []))
                self.assertNotIn("athletic blue shorts", analysis.anchors.get("wardrobe", []))

        separated_color = analyze_query("blue. shorts", index)
        self.assertNotIn("blue", separated_color.anchors.get("wardrobe", []))
        self.assertNotIn("body_build", separated_color.anchors)

        governed_figure = analyze_query("athletic figure in shorts", index)
        self.assertEqual(["athletic"], governed_figure.anchors.get("body_build"))
        self.assertNotIn(
            "athletic figure in shorts",
            governed_figure.anchors.get("wardrobe", []),
        )
        figure_evidence = next(
            row
            for row in governed_figure.anchor_evidence
            if row["facet"] == "body_build" and row["value"] == "athletic"
        )
        self.assertEqual("figure", figure_evidence["governed_noun"])

        separate_sentences = analyze_query("athletic. Shorts are blue.", index)
        self.assertEqual(["athletic"], separate_sentences.anchors.get("body_build"))
        self.assertIn("blue", separate_sentences.anchors.get("wardrobe", []))
        blue_evidence = next(
            row
            for row in separate_sentences.anchor_evidence
            if row["facet"] == "wardrobe" and row["value"] == "blue"
        )
        self.assertEqual("shorts", blue_evidence["governed_noun"])
        self.assertEqual("shorts are blue", blue_evidence["source_span"]["text"])

    def test_color_scope_covers_common_garment_head_nouns(self) -> None:
        index = self._modifier_scope_index()
        for noun in ("shorts", "pants", "trousers", "jersey", "socks"):
            query = f"blue {noun}"
            with self.subTest(query=query):
                analysis = analyze_query(query, index)
                self.assertIn("blue", analysis.anchors.get("wardrobe", []))
                evidence = next(
                    row for row in analysis.anchor_evidence
                    if row["facet"] == "wardrobe" and row["value"] == "blue"
                )
                self.assertEqual(noun, evidence["governed_noun"])
                self.assertEqual(query, evidence["source_span"]["text"])

    def test_known_and_unknown_non_physique_governors_never_default_to_body(self) -> None:
        index = self._modifier_scope_index()

        socks = analyze_query("athletic socks", index)
        beard = analyze_query("broad beard", index)
        self.assertNotIn("body_build", socks.anchors)
        self.assertEqual(["athletic socks"], socks.anchors.get("wardrobe"))
        self.assertNotIn("body_build", beard.anchors)
        self.assertIn("broad beard", beard.anchors.get("facial_hair", []))

        for query, modifier, noun in (
            ("athletic gaiters", "athletic", "gaiters"),
            ("broad whiskercoat", "broad", "whiskercoat"),
        ):
            with self.subTest(query=query):
                analysis = analyze_query(query, index)
                self.assertNotIn("body_build", analysis.anchors)
                self.assertIn(modifier, analysis.terms_without_alias)
                diagnostic = next(
                    row for row in analysis.modifier_scope_evidence
                    if row["value"] == modifier
                )
                self.assertIsNone(diagnostic["facet"])
                self.assertEqual(noun, diagnostic["governed_noun"])
                self.assertIn("not promoted to physique", diagnostic["reason"])

    def test_stacked_species_modifiers_are_order_independent(self) -> None:
        index = self._modifier_scope_index()
        for query in (
            "tall muscular maintenance robot",
            "muscular tall maintenance robot",
        ):
            with self.subTest(query=query):
                analysis = analyze_query(query, index)
                self.assertEqual(["maintenance robot"], analysis.anchors.get("species"))
                self.assertEqual(["muscular"], analysis.anchors.get("body_build"))
                self.assertEqual(["tall"], analysis.anchors.get("proportion"))
                for facet, value in (
                    ("body_build", "muscular"),
                    ("proportion", "tall"),
                ):
                    evidence = next(
                        row for row in analysis.anchor_evidence
                        if row["facet"] == facet
                        and row["value"] == value
                        and "modifier stack" in row["reason"]
                    )
                    self.assertEqual("maintenance robot", evidence["governed_noun"])
                    self.assertEqual(value, evidence["source_span"]["text"])

    def test_query_evidence_augments_existing_structured_anchors(self) -> None:
        analysis = analyze_query(
            "anthropomorphic muscular black panther",
            self._modifier_scope_index(),
            explicit_anchors={
                "domain": ["anthropomorphic-animal"],
                "species": ["black panther"],
                "body_build": ["muscular"],
            },
        )

        expected = {
            "domain": ("anthropomorphic-animal", "anthropomorphic", "black panther"),
            "species": ("black panther", "black panther", "black panther"),
            "body_build": ("muscular", "muscular", "black panther"),
        }
        for facet, (value, span_text, governed_noun) in expected.items():
            with self.subTest(facet=facet):
                self.assertTrue(any(
                    row["facet"] == facet
                    and row["value"] == value
                    and row["source"] == "structured query facet"
                    for row in analysis.anchor_evidence
                ))
                query_evidence = next(
                    row for row in analysis.anchor_evidence
                    if row["facet"] == facet
                    and row["value"] == value
                    and row.get("source_span", {}).get("text") == span_text
                )
                self.assertEqual(governed_noun, query_evidence["governed_noun"])
                self.assertEqual(query_evidence["source"], query_evidence["reason"])

    def test_matches_every_actual_indexed_phrase_width(self) -> None:
        phrase = "one two three four five six seven eight"
        index = SearchIndex({
            "records": {},
            "phrases": {phrase: [_row("long-phrase", "wardrobe")]},
        })

        self.assertIn(8, index.phrase_widths)
        self.assertEqual(
            [phrase],
            [match.phrase for match in index.match_phrases(f"please use {phrase} now")],
        )

    def test_hair_texture_category_uses_canonical_facet(self) -> None:
        authored = _row("fixture-covering-texture-rugged", "hair_texture")
        index = SearchIndex({
            "records": {},
            "phrases": {"coarse": [authored]},
        })

        analysis = analyze_query("coarse hair texture", index)

        self.assertEqual(["coarse"], analysis.anchors.get("hair_texture"))
        self.assertNotIn("hair_style", analysis.anchors)
        projected = analysis.associations_by_id["fixture-covering-texture-rugged"][0]
        self.assertEqual("hair_texture", projected["facet"])
        self.assertNotIn("authored_facet", projected)
        self.assertEqual(
            "hair_texture",
            index.phrases["coarse"][0]["facet"],
            "the canonical lexical tuple must remain untouched",
        )
        self.assertNotIn("coarse", analysis.terms_without_alias)

        self.assertEqual(
            "hair_texture",
            FACET_BY_CATEGORY["hair-texture"],
            "cache generation must emit the canonical texture facet",
        )
        record_facets = extract_record_facets(
            "module",
            "hair-texture",
            {"id": "fixture-covering-texture-rugged", "label": "coarse", "prompt": "coarse hair texture"},
        )
        self.assertIn("hair_texture", record_facets)

    def test_generic_match_does_not_cover_unresolved_head_hair_trait(self) -> None:
        index = SearchIndex({
            "records": {},
            "phrases": {"shaggy": [_row("style-shaggy", "style")]},
        })

        analysis = analyze_query("shaggy head hair", index)

        self.assertEqual(["head hair"], analysis.anchors.get("head_hair"))
        self.assertNotIn("style", analysis.anchors)
        self.assertIn("shaggy", analysis.terms_without_alias)

    def test_hair_color_requires_local_hair_scope(self) -> None:
        index = SearchIndex({
            "records": {},
            "phrases": {
                "black": [_row("fixture-covering-color-ebony", "hair_color")],
                "blue": [_row("fixture-covering-color-cobalt", "hair_color")],
                "panther": [_row("fixture-species-generic-cat", "species")],
            },
        })

        coat_analysis = analyze_query("black panther with head hair", index)
        hair_analysis = analyze_query("blue hair", index)

        self.assertEqual(["black"], coat_analysis.anchors.get("coat_palette"))
        self.assertNotIn("hair_color", coat_analysis.anchors)
        self.assertEqual(["blue"], hair_analysis.anchors.get("subject_surface"))
        self.assertNotIn("head_hair", hair_analysis.anchors)

    def test_archetype_identity_projects_hair_and_head_invariants(self) -> None:
        record = {
            "id": "archetype-hair-test",
            "label": "Hair topology test",
            "character_lock": (
                "Adult anthropomorphic tiger with brown head hair, a forward "
                "forelock, short chin beard, full mane, layered neck ruff, "
                "cranial horns, pointed ears, and cheek fur tufts."
            ),
        }

        facets = extract_record_facets("archetype", None, record)

        for facet in (
            "head_hair", "hair_style", "hair_color", "facial_hair", "mane",
            "ruff", "head_fur_placement", "head_feature",
        ):
            self.assertIn(facet, facets)

    def test_scene_performance_remains_an_open_lexical_facet(self) -> None:
        index = SearchIndex({
            "records": {},
            "phrases": {"stern gaze": [_row("performance-stern-gaze", "performance")]},
        })

        analysis = analyze_query("stern gaze", index)

        self.assertEqual(["stern gaze"], analysis.anchors.get("performance"))
        self.assertEqual([], analysis.terms_without_alias)

    def test_species_tags_do_not_become_species_names_and_local_stature_is_scoped(self) -> None:
        index = SearchIndex({
            "records": {},
            "phrases": {
                "maintenance robot": [
                    _row("fixture-subject-service-automaton", "species", source="label")
                ],
                "tall": [
                    _row("fixture-species-alpha-canid", "species", source="tag", weight=0.9),
                    _row("proportion-tall", "proportion", source="tag", weight=0.9),
                ],
                "bold": [
                    _row("fixture-species-beta-mustelid", "species", source="tag", weight=0.9),
                    _row("rendering-bold", "style", source="tag", weight=0.9),
                ],
                "wolf": [
                    _row("fixture-species-silver-canid", "species", source="tag", weight=0.9),
                    _row("species-wolf", "species", source="author"),
                ],
            },
        })

        analysis = analyze_query(
            "tall maintenance robot with a bold graphic treatment",
            index,
            "robot",
        )

        self.assertEqual(["maintenance robot"], analysis.anchors.get("species"))
        self.assertEqual(["tall"], analysis.anchors.get("proportion"))
        self.assertNotIn("species", analysis.scoped_terms.get("bold", set()))
        self.assertEqual({"proportion"}, analysis.scoped_terms.get("tall"))

        wolf_analysis = analyze_query("wolf baseball cap", index)
        self.assertEqual(["wolf"], wolf_analysis.anchors.get("species"))

    # Each query's color rows, as the color scan records them. The queries cover:
    #   - several colors
    #   - a two-word color
    #   - a clause boundary
    #   - garment and body readings of coat
    #   - located and unlocated hair
    #   - no color
    COLOR_CONTEXT_ROWS = {
        "anthropomorphic wolf with blue eyes and silver fur": [
            ("silver", "coat_palette", "silver fur", (40, 50), "fur"),
            ("blue", "eye_feature", "blue eyes", (26, 35), "eyes"),
        ],
        "navy blue field jacket, red shorts. Warm gray background": [
            ("navy blue", "wardrobe", "navy blue field jacket", (0, 22), "field jacket"),
            ("warm gray", "environment", "warm gray background", (34, 54), "background"),
            ("blue", "wardrobe", "blue field jacket", (5, 22), "field jacket"),
            ("gray", "environment", "gray background", (39, 54), "background"),
            ("red", "wardrobe", "red shorts", (23, 33), "shorts"),
        ],
        "pale blue skin; white hair; crimson armor": [
            ("pale blue", "skin_tone", "pale blue skin", (0, 14), "skin"),
            ("crimson", "wardrobe", "crimson armor", (26, 39), "armor"),
            ("white", "subject_surface", "white hair", (15, 25), "hair"),
            ("blue", "skin_tone", "blue skin", (5, 14), "skin"),
        ],
        "fox wearing a black coat; dragon whose scales are bronze": [
            ("bronze", "subject_surface", "scales are bronze", (38, 55), "scales"),
            ("black", "wardrobe", "black coat", (14, 24), "coat"),
        ],
        "golden coat of fur, amber rim light in a teal room": [
            ("golden", "coat_palette", "golden coat of fur", (0, 18), "coat of fur"),
            ("golden", "coat_palette", "golden coat", (0, 11), "coat"),
            ("amber", "coat_palette", "fur amber", (15, 24), "fur"),
            ("amber", "lighting", "amber rim light", (19, 34), "rim light"),
            ("teal", "environment", "teal room", (40, 49), "room"),
        ],
        "black-white striped socks and brown head hair": [
            ("brown", "hair_color", "brown head hair", (30, 45), "head hair"),
            ("white", "wardrobe", "white striped socks", (6, 25), "striped socks"),
        ],
        "synthetic robot fixture": [],
        "standing figure in a fantasy setting": [],
    }

    def test_color_contexts_record_each_governed_color(self) -> None:
        for raw, expected in self.COLOR_CONTEXT_ROWS.items():
            with self.subTest(query=raw):
                rows = _find_color_contexts(
                    normalize_query(raw),
                    _normalized_sentence_boundaries(raw),
                )
                self.assertEqual(expected, rows)

    def test_color_contexts_compile_patterns_only_for_colors_in_the_query(self) -> None:
        _color_word_pattern.cache_clear()
        _color_context_patterns.cache_clear()
        _find_color_contexts(normalize_query("standing figure in a fantasy setting"))
        self.assertEqual(0, _color_context_patterns.cache_info().currsize)

        query = normalize_query("navy blue field jacket and red boots")
        present = [
            color for color in COLOR_TERMS
            if re.search(rf"\b{re.escape(color)}\b", query)
        ]
        self.assertEqual(["navy blue", "blue", "navy", "red"], present)
        _find_color_contexts(query)
        compiled = _color_context_patterns.cache_info()
        self.assertEqual(len(present) * len(_COLOR_CONTEXT_TARGETS), compiled.currsize)
        # "tan" is a substring of "standing" in the first query; the other
        # four are the colors present in the second.
        self.assertEqual(5, _color_word_pattern.cache_info().currsize)

        _find_color_contexts(query)
        self.assertEqual(compiled.misses, _color_context_patterns.cache_info().misses)


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
