"""Lexical scoring: indexed entry views, facet maps, and the corpus scorer."""
from __future__ import annotations

import json
import math
from array import array
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from search_discovery import (
    FACET_BY_CATEGORY,
    KIND_PRIMARY_FACET,
    PERMANENT_IDENTITY_FACETS,
    QueryAnalysis,
    SearchIndex,
    color_families_in_text,
    extract_record_facets,
    profile_aliases,
)

import catalog_retrieval.runtime as runtime
from catalog_retrieval.core import (
    STOPWORDS,
    _domain_compatible,
    _field_text,
    _normalized_domains,
    _species_anchor_scope,
    _species_family_value,
    _species_taxon_value,
    canonical_domain,
    contrastive_modifier_conflicts,
    normalize,
    tokens_of,
)
# Runtime-owned objects are looked up when called, not while the modules are
# initializing. This keeps both import orders valid and annotations concrete.

# ---------------------------------------------------------------------------
# Scoring
#
# The previous scorer counted raw token overlap, which made one shared common
# word ("close", "light") rank an unrelated record next to a genuinely
# relevant one and produced flat alphabetical ties. This scorer:
#   * weights query tokens by inverse document frequency, so rare, informative
#     words dominate and ubiquitous ones barely count
#   * weights WHERE a token matches (label/tags count double prose)
#   * rewards consecutive query bigrams and full-phrase hits
#   * reports a coarse relevance band plus the matched terms instead of a
#     pseudo-precise number, and refuses to return weak matches at all
# ---------------------------------------------------------------------------

_STRONG_FIELDS = ("label", "tags", "category")
_PROSE_FIELDS = (
    "applies_to", "visual_function", "image_promise",
    "description", "prompt", "rendering", "positive_correction",
    "diagnosis", "best_for", "defaults", "staging", "must_preserve",
    "invariants", "misreadings_to_avoid", "identity_invariants",
    "identity_construction", "trigger", "inspection_points",
    "medium_family", "visual_intent", "linework", "shape_language",
    "value_structure", "color_logic", "surface_policy",
    "lighting_response", "background_policy", "detail_hierarchy",
    "aesthetic_promise", "appeal_center",
    "silhouette_and_proportion_strategy",
    "performance_and_expression_strategy", "viewer_relationship_strategy",
    "composition_and_focal_strategy", "shape_and_rhythm_strategy",
    "surface_and_tactility_strategy", "color_and_light_strategy",
    "finish_and_detail_hierarchy", "integration_prompt",
    "compatible_medium_families", "variation_axes", "domain_neutrality",
    "realization_promise", "identity_and_silhouette", "performance_channels",
    "anatomy_and_weight", "surface_and_materials", "viewer_relationship",
    "motion_and_environment", "translation_rules", "extension_points",
    "style_promise", "visual_signature", "line_system", "form_system",
    "value_and_shadow_system", "highlight_system", "color_system",
    "surface_system", "background_system", "touch_policy",
    "style_reference_guidance", "domain_overlays", "base_render_profile_id",
    "compatible_render_profile_ids", "subject_domain", "realization_level",
    "performance_language",
    "character_lock", "identity", "head_hair", "hair_style",
    "hair_texture", "hair_color", "facial_hair", "mane", "ruff",
    "head_fur_placement", "head_feature", "grooming",
    "feature_type", "target_region", "laterality", "landmark_relation",
    "count_or_distribution", "relative_size", "shape_and_path", "orientation",
    "color_and_value", "depth_and_relief", "edge_and_texture",
    "surface_interaction", "age_or_condition", "visibility_and_occlusion",
    "identity_priority", "adaptation_limits",
)


FACET_COMPATIBILITY: Mapping[str, frozenset[str]] = {
    "coat_palette": frozenset({"coat_palette", "primary_coat_color"}),
    "body_build": frozenset({"body_build", "proportion"}),
    "proportion": frozenset({"proportion", "body_build"}),
    "hair_style": frozenset({"hair_style", "head_hair"}),
    "hair_texture": frozenset({"hair_texture", "head_hair"}),
    "head_hair": frozenset({"head_hair", "hair_style", "hair_texture"}),
    "facial_hair": frozenset({"facial_hair"}),
    "mane": frozenset({"mane"}),
    "ruff": frozenset({"ruff"}),
    "head_fur_placement": frozenset({"head_fur_placement"}),
    "head_feature": frozenset({"head_feature"}),
    # Framing language commonly describes both lens/camera distance and the
    # resulting arrangement in frame.  Query analysis must choose one scope
    # for an ambiguous phrase such as ``close portrait``, but retrieval should
    # still admit authored evidence on the other, directly coupled craft axis.
    "camera": frozenset({"camera", "composition"}),
    "composition": frozenset({"composition", "camera"}),
}

# Lexical retrieval may connect one exact word to a contextual state or surface
# facet without weakening permanent-identity matching. In particular, a ruff
# can be authored as stable neck surface or as transient hackle performance;
# those meanings stay distinct in records even though both are relevant to an
# explicit ``ruff`` search. ``_anchor_value_matches`` deliberately does not use
# this broader map when deciding whether an archetype satisfies an identity lock.
LEXICAL_FACET_COMPATIBILITY: Mapping[str, frozenset[str]] = {
    "ruff": frozenset({"subject_surface", "performance", "appendage_action"}),
}

# A named prop is a discrete object selection: once the query explicitly names
# one, another prop is not a complementary interpretation of that same facet.
# Broader craft facets such as style, composition, environment, and pose are
# deliberately absent because several candidates may contribute distinct,
# compatible parts of one art direction.
EXACT_SELECTION_FACETS = frozenset({"prop"})


def lexical_facet_candidates(facet: str) -> set[str]:
    """Return record facets eligible for one scoped lexical query facet."""
    candidates = set(FACET_COMPATIBILITY.get(facet, frozenset({facet})))
    candidates.update(LEXICAL_FACET_COMPATIBILITY.get(facet, frozenset()))
    return candidates


# The facet a record falls back to when neither its category nor its kind is
# mapped to a semantic field. It is a sentinel rather than a comparable facet:
# such a record has no semantic field to test a scoped query token against.
UNMAPPED_PRIMARY_FACET = "subject"


def semantic_primary_facet(kind: str, category: str | None) -> str:
    """Return the contextual facet represented by one concrete record."""
    return (
        FACET_BY_CATEGORY.get(str(category or ""))
        or KIND_PRIMARY_FACET.get(kind)
        or UNMAPPED_PRIMARY_FACET
    )


def primary_facet_query_phrases(
    analysis: QueryAnalysis,
    search_index: SearchIndex,
    facet: str,
) -> tuple[str, ...]:
    """Return exact query phrases that explicitly address ``facet``.

    The full brief remains the scoring query.  These phrases are only an
    eligibility constraint inside a semantically singular retrieval scope.
    For example, an exact ``wrench`` association establishes a prop request;
    another prop must not qualify merely because its prose happens to contain
    the subject-height word ``tall`` from the same full brief.
    """
    accepted = lexical_facet_candidates(facet)
    phrases: list[str] = []
    for match in analysis.phrase_matches:
        associated_facets = {
            search_index.association_facet(row)
            for row in match.associations
            if search_index.association_facet(row)
        }
        # A phrase is a category anchor only when every indexed meaning stays
        # inside this facet's compatibility group.  ``wrench`` is an explicit
        # prop anchor; broad words such as ``poster`` or ``graphic`` remain
        # shared context because the catalog intentionally associates them
        # with composition, camera, pose, style, and other craft axes.
        if associated_facets and associated_facets <= accepted:
            phrase = normalize(match.phrase)
            if phrase and phrase not in phrases:
                phrases.append(phrase)
    return tuple(phrases)


@dataclass(frozen=True)
class IndexedEntry:
    entry: runtime.Entry
    strong_text: str
    prose_text: str
    alias_text: str
    strong_tokens: frozenset[str]
    prose_tokens: frozenset[str]
    alias_tokens: frozenset[str]
    facet_tokens: Mapping[str, frozenset[str]]
    facet_values: Mapping[str, tuple[str, ...]]
    domains: tuple[str, ...]
    profile: Mapping[str, Any]


_IDF_KINDS = {"module", "profile", "aesthetic-core", "style-family", "domain-realization", "correction"}


def _build_indexed_entry(entry: runtime.Entry, search_index: SearchIndex) -> IndexedEntry:
    """Build or reuse one immutable scoring view for a catalog record.

    The same record participates in corpus construction, candidate scoring,
    category-restricted retrieval, and regression suites. Recomputing its
    flattened prose, facets, aliases, and token sets for every route dominates
    runtime and makes release validation unnecessarily slow. Cache the view by
    the search-index fingerprint and the record fingerprint. Both inputs are
    content-derived, so reuse is deterministic and invalidates automatically
    when either source changes.
    """
    cache_key = (search_index.fingerprint, entry.fingerprint)
    cached = runtime._lru_get(runtime._INDEXED_ENTRY_CACHE, cache_key)
    if cached is not None:
        return cached

    rid = str(entry.record.get("id") or "")
    profile = runtime.runtime_profile(entry, search_index)
    aliases = profile_aliases(search_index, rid)
    alias_text = normalize(" ".join(aliases))
    strong = _field_text(entry.record, _STRONG_FIELDS)
    prose_parts = [_field_text(entry.record, _PROSE_FIELDS)]
    if profile.get("outcome_summary"):
        prose_parts.append(normalize(profile["outcome_summary"]))
    prose = normalize(" ".join(prose_parts))
    strong_tokens = frozenset(tokens_of(strong))
    prose_tokens = frozenset(tokens_of(prose))
    alias_tokens = frozenset(tokens_of(alias_text))

    facets = extract_record_facets(entry.kind, entry.category, entry.record)
    profile_facets = profile.get("facets")
    if isinstance(profile_facets, Mapping):
        for facet, values in profile_facets.items():
            existing = list(facets.get(str(facet), []))
            if isinstance(values, str):
                values = [values]
            if isinstance(values, (list, tuple, set)):
                for value in values:
                    normalized = normalize(value)
                    if normalized and normalized not in existing:
                        existing.append(normalized)
            if existing:
                facets[str(facet)] = existing
    facet_values = {
        facet: tuple(
            normalized
            for value in values
            if (normalized := normalize(value))
        )
        for facet, values in facets.items()
    }
    facet_tokens = {
        facet: frozenset(tokens_of(" ".join(values)))
        for facet, values in facet_values.items()
    }
    indexed = IndexedEntry(
        entry=entry,
        strong_text=strong,
        prose_text=prose,
        alias_text=alias_text,
        strong_tokens=strong_tokens,
        prose_tokens=prose_tokens,
        alias_tokens=alias_tokens,
        facet_tokens=facet_tokens,
        facet_values=facet_values,
        domains=_normalized_domains(entry.record),
        profile=profile,
    )
    runtime._lru_put(runtime._INDEXED_ENTRY_CACHE, cache_key, indexed, runtime._MAX_INDEXED_ENTRY_CACHE)
    return indexed


class Corpus:
    def __init__(self, entries: Sequence[runtime.Entry], search_index: SearchIndex | None = None):
        self.search_index = search_index or runtime.load_search_index()
        self.entries = list(entries)

        use_atomic_idf = any(entry.kind in _IDF_KINDS for entry in self.entries)
        document_frequency: dict[str, int] = {}
        token_to_indices: dict[str, array] = {}
        record_id_to_index: dict[str, int] = {}
        idf_population = 0

        for index, entry in enumerate(self.entries):
            indexed = _build_indexed_entry(entry, self.search_index)
            record_id = str(entry.record.get("id") or "")
            if record_id:
                record_id_to_index[record_id] = index

            if not use_atomic_idf or entry.kind in _IDF_KINDS:
                idf_population += 1
                for token in indexed.strong_tokens | indexed.prose_tokens | indexed.alias_tokens:
                    document_frequency[token] = document_frequency.get(token, 0) + 1

            searchable_tokens = set(indexed.strong_tokens)
            searchable_tokens.update(indexed.prose_tokens)
            searchable_tokens.update(indexed.alias_tokens)
            for values in indexed.facet_tokens.values():
                searchable_tokens.update(values)
            for token in searchable_tokens:
                token_to_indices.setdefault(token, array("I")).append(index)

        self._df = document_frequency
        self._n = max(1, idf_population)
        self._token_to_indices = token_to_indices
        self._record_id_to_index = record_id_to_index

    def indexed_at(self, index: int) -> IndexedEntry:
        return _build_indexed_entry(self.entries[index], self.search_index)

    def candidate_indices(
        self,
        query_tokens: Sequence[str],
        analysis: QueryAnalysis | None = None,
    ) -> tuple[int, ...]:
        """Return the exact superset of records capable of positive scoring.

        Direct text and facet evidence are reached through the inverted token
        index. Query analysis can also award lexical-association bonuses to a
        record whose canonical text does not repeat the alias phrase, so those
        record IDs are included explicitly. If a future query-analysis route
        supplies no candidates, fall back to the full corpus rather than risk
        hiding a newly introduced evidence source.
        """
        candidates: set[int] = set()
        for token in dict.fromkeys(query_tokens):
            candidates.update(self._token_to_indices.get(token, ()))
        if analysis:
            for record_id in analysis.associations_by_id:
                index = self._record_id_to_index.get(str(record_id))
                if index is not None:
                    candidates.add(index)
            for values in analysis.anchors.values():
                for value in values:
                    for token in tokens_of(value):
                        candidates.update(self._token_to_indices.get(token, ()))
        if not candidates:
            return tuple(range(len(self.entries)))
        return tuple(sorted(candidates))

    def idf(self, token: str) -> float:
        return math.log(1.0 + self._n / (1.0 + self._df.get(token, 0)))

    @staticmethod
    def _facet_match(indexed: IndexedEntry, token: str, wanted: set[str]) -> bool:
        for facet in wanted:
            for candidate in lexical_facet_candidates(facet):
                if token in indexed.facet_tokens.get(candidate, frozenset()):
                    return True
        return False

    @staticmethod
    def _anchor_value_matches(indexed: IndexedEntry, facet: str, value: str) -> bool:
        wanted_tokens = set(tokens_of(value))
        if not wanted_tokens:
            return False
        if facet == "coat_palette":
            wanted_colors = color_families_in_text(value)
            primary_values = indexed.facet_values.get("primary_coat_color", ())
            primary_colors: set[str] = set()
            for candidate in primary_values:
                primary_colors.update(color_families_in_text(candidate))
            if wanted_colors and primary_colors:
                return bool(wanted_colors & primary_colors)
            primary = set(indexed.facet_tokens.get("primary_coat_color", frozenset()))
            if primary:
                return wanted_tokens <= primary
        if facet == "species":
            wanted_family = _species_family_value(value)
            candidate_values = indexed.facet_values.get("species", ())
            candidate_families = {_species_family_value(candidate) for candidate in candidate_values} - {None}
            if wanted_family and candidate_families:
                return wanted_family in candidate_families and any(
                    wanted_tokens & set(tokens_of(candidate)) for candidate in candidate_values
                )
        compatible = FACET_COMPATIBILITY.get(facet, frozenset({facet}))
        combined: set[str] = set()
        for candidate in compatible:
            combined.update(indexed.facet_tokens.get(candidate, frozenset()))
        return wanted_tokens <= combined

    def _matches_primary_query_phrase(
        self,
        indexed: IndexedEntry,
        facet: str,
        phrases: Sequence[str],
        analysis: QueryAnalysis,
    ) -> bool:
        """Return whether a candidate satisfies one explicit facet phrase."""
        accepted = lexical_facet_candidates(facet)
        wanted = set(phrases)
        record_id = str(indexed.entry.record.get("id") or "")
        for association in analysis.associations_by_id.get(record_id, []):
            if (
                normalize(association.get("phrase")) in wanted
                and str(association.get("facet") or "") in accepted
            ):
                return True

        facet_tokens: set[str] = set()
        for candidate in accepted:
            facet_tokens.update(indexed.facet_tokens.get(candidate, frozenset()))
        return any(
            phrase_tokens <= facet_tokens
            for phrase in phrases
            if (phrase_tokens := set(tokens_of(phrase)))
        )

    def score(
        self,
        indexed: IndexedEntry,
        query_tokens: Sequence[str],
        query_norm: str,
        domain: str | None,
        analysis: QueryAnalysis | None = None,
        required_primary_phrases: Sequence[str] = (),
    ) -> tuple[float, list[str], bool, list[dict[str, Any]]]:
        informative = [token for token in query_tokens if token not in STOPWORDS]
        if not informative:
            informative = list(query_tokens)
        unique_informative = list(dict.fromkeys(informative))

        if analysis and required_primary_phrases:
            primary_facet = semantic_primary_facet(
                indexed.entry.kind,
                indexed.entry.category,
            )
            if not self._matches_primary_query_phrase(
                indexed,
                primary_facet,
                required_primary_phrases,
                analysis,
            ):
                return 0.0, [], False, []

        # Identity retrieval treats an explicitly scoped primary coat color as
        # a hard anchor. A red or black wolf should not rank as a useful answer
        # to "blue fur" merely because it also mentions blue eyes, shadows, or
        # clothing. Related color names such as navy and teal share a family.
        if analysis and indexed.entry.kind == "archetype" and analysis.anchors.get("coat_palette"):
            primary_values = indexed.facet_values.get("primary_coat_color", ())
            candidate_colors: set[str] = set()
            for candidate in primary_values:
                candidate_colors.update(color_families_in_text(candidate))
            wanted_colors: set[str] = set()
            for wanted in analysis.anchors.get("coat_palette", []):
                wanted_colors.update(color_families_in_text(wanted))
            if wanted_colors and candidate_colors and not (wanted_colors & candidate_colors):
                return 0.0, [], False, []

        if analysis and indexed.entry.kind == "archetype" and analysis.anchors.get("species"):
            wanted_taxa: set[str] = set()
            wanted_families: set[str] = set()
            for wanted in analysis.anchors.get("species", []):
                scope = _species_anchor_scope(wanted)
                if scope is None:
                    continue
                (wanted_taxa if scope[0] == "taxon" else wanted_families).add(scope[1])
            candidate_values = indexed.facet_values.get("species", ())
            candidate_taxa = {value for value in (_species_taxon_value(candidate) for candidate in candidate_values) if value}
            candidate_families = {value for value in (_species_family_value(candidate) for candidate in candidate_values) if value}
            if wanted_taxa and candidate_taxa and not (wanted_taxa & candidate_taxa):
                return 0.0, [], False, []
            if wanted_families and candidate_families and not (wanted_families & candidate_families):
                return 0.0, [], False, []

        denom_idfs = sorted((self.idf(token) for token in unique_informative), reverse=True)[:8]
        total_mass = sum(denom_idfs)
        if total_mass <= 0:
            return 0.0, [], False, []

        matched_mass = 0.0
        matched: list[tuple[float, str]] = []
        evidence: list[dict[str, Any]] = []
        strong_field_matches = 0
        strong_field_token_count = 0
        max_strong_idf = 0.0
        rare_strong_field_match = False
        # A record whose category and kind are both unmapped has no semantic
        # field to compare a scoped query token against. Silencing it entirely
        # would remove it from every scoped query, so it keeps the unscoped
        # weight instead, without the matched-facet bonus, so it never
        # outranks a record that does declare the facet.
        unmapped_primary = (
            semantic_primary_facet(indexed.entry.kind, indexed.entry.category)
            == UNMAPPED_PRIMARY_FACET
        )
        for token in unique_informative:
            weight = 0.0
            source = ""
            if token in indexed.strong_tokens:
                weight = 2.0
                source = "label-tags-category"
                strong_field_token_count += 1
                max_strong_idf = max(max_strong_idf, self.idf(token))
                if self.idf(token) >= 4.0:
                    strong_field_matches += 1
                if self.idf(token) >= 3.5:
                    rare_strong_field_match = True
            elif token in indexed.alias_tokens:
                weight = 1.55
                source = "search-alias"
            elif token in indexed.prose_tokens:
                weight = 1.0
                source = "canonical-prose"

            wanted_facets = set(analysis.scoped_terms.get(token, set())) if analysis else set()
            if weight and wanted_facets:
                match_facets = set(wanted_facets)
                # A strongly authored tag can describe the craft treatment of
                # another explicit query facet. For example, "cinematic" is a
                # style anchor in isolation, but on a lighting record selected
                # by the same query's exact rim-light anchor it remains useful
                # lighting evidence. Requiring an independently matched primary
                # facet prevents a scoped identity color from leaking into an
                # unrelated blue-lit record.
                if analysis and "style" in wanted_facets and token in indexed.strong_tokens:
                    primary_facet = semantic_primary_facet(
                        indexed.entry.kind,
                        indexed.entry.category,
                    )
                    primary_values = (
                        analysis.anchors.get(primary_facet) or []
                        if primary_facet != "style"
                        else []
                    )
                    if primary_values and any(
                        self._anchor_value_matches(indexed, primary_facet, value)
                        for value in primary_values
                    ):
                        match_facets.add(primary_facet)
                if self._facet_match(indexed, token, match_facets):
                    weight *= 1.2
                    source = "facet:" + ",".join(sorted(match_facets))
                    if "coat_palette" in wanted_facets:
                        primary = indexed.facet_tokens.get("primary_coat_color", frozenset())
                        if token in primary:
                            weight *= 1.45
                            source = "facet:primary_coat_color"
                        elif primary:
                            # A scoped coat-color request is identity-bearing.
                            # Once a record declares a different primary coat, a
                            # mention of the requested color only in shadow, eyes,
                            # trim, or accents is not positive retrieval evidence.
                            weight = 0.0
                            source = ""
                elif not unmapped_primary:
                    # A scoped token that appears only in another semantic
                    # field is not relevant evidence. Example: "blue fur" must
                    # not rank a blue-lit room or blue eyes.
                    weight = 0.0
                    source = ""
            if weight:
                idf = self.idf(token)
                matched_mass += weight * idf
                matched.append((idf, token))
                evidence.append({
                    "query_term": token,
                    "facet": sorted(wanted_facets) if wanted_facets else [],
                    "source": source,
                })
        coverage = matched_mass / (2.0 * total_mass)

        haystack = f"{indexed.strong_text} {indexed.alias_text} {indexed.prose_text}"
        bigram_bonus = 0.0
        for first, second in zip(informative, informative[1:]):
            phrase = f"{first} {second}"
            if phrase in indexed.strong_text or phrase in indexed.alias_text:
                bigram_bonus += 0.08
        bigram_bonus = min(bigram_bonus, 0.40)

        phrase_bonus = 0.25 if query_norm and query_norm in haystack else 0.0
        label = normalize(indexed.entry.record.get("label"))
        label_bonus = 0.20 if label and " " in label and label in query_norm else 0.0

        alias_bonus = 0.0
        if analysis:
            rid = str(indexed.entry.record.get("id") or "")
            semantic_contributions: dict[tuple[str, str, str], float] = {}
            for association in analysis.associations_by_id.get(rid, []):
                phrase = normalize(association.get("phrase"))
                facet = str(association.get("facet") or "")
                phrase_tokens = tokens_of(phrase)
                scoped = set().union(*(analysis.scoped_terms.get(token, set()) for token in phrase_tokens)) if phrase_tokens else set()
                if scoped and not any(
                    facet in lexical_facet_candidates(wanted_facet)
                    for wanted_facet in scoped
                ):
                    continue
                contribution = (0.035 + 0.018 * min(4, len(phrase_tokens))) * float(association.get("weight", 0.7))
                semantic_key = (rid, phrase, facet)
                semantic_contributions[semantic_key] = max(
                    semantic_contributions.get(semantic_key, 0.0),
                    contribution,
                )
                evidence.append({
                    "query_term": phrase,
                    "facet": facet,
                        "source": "search-association:" + str(association.get("source") or "unknown"),
                    "weight": float(association.get("weight", 0.7)),
                })
            alias_bonus = sum(semantic_contributions.values())
            alias_bonus = min(alias_bonus, 0.28)

        anchor_adjust = 0.0
        anchor_matches = 0
        anchor_total = 0
        if analysis and indexed.entry.kind == "archetype":
            for facet, values in analysis.anchors.items():
                if facet == "domain" or facet not in PERMANENT_IDENTITY_FACETS:
                    continue
                for value in values:
                    anchor_total += 1
                    if self._anchor_value_matches(indexed, facet, value):
                        anchor_matches += 1
                        anchor_adjust += 0.035
                        if facet == "coat_palette":
                            value_tokens = set(tokens_of(value))
                            if value_tokens <= set(indexed.facet_tokens.get("primary_coat_color", frozenset())):
                                anchor_adjust += 0.055
                    else:
                        anchor_adjust -= 0.035
            if anchor_total and anchor_matches == anchor_total:
                anchor_adjust += 0.05

        # Ordinary cross-category searches should prefer a record whose
        # canonical category owns the requested facet. A blue cheek marking may
        # mention both "blue" and "fur", but a coat-palette record is the more
        # useful first answer to the scoped query "blue fur". This is a modest
        # routing bonus, not a hard filter; related records remain discoverable.
        primary_facet_adjust = 0.0
        if analysis:
            primary_facet = (
                semantic_primary_facet(indexed.entry.kind, indexed.entry.category)
            )
            compatible_primary = {
                "coat_palette": {"coat_palette", "subject_surface"},
                "body_build": {"body_build", "proportion"},
                "proportion": {"proportion", "body_build"},
                "camera": {"camera", "composition"},
                "composition": {"composition", "camera"},
            }
            for facet, values in analysis.anchors.items():
                if facet == "domain" or not values:
                    continue
                accepted = compatible_primary.get(
                    facet,
                    set(FACET_COMPATIBILITY.get(facet, frozenset({facet}))),
                )
                if primary_facet not in accepted:
                    continue
                if any(self._anchor_value_matches(indexed, facet, value) for value in values):
                    primary_facet_adjust += 0.12
            primary_facet_adjust = min(primary_facet_adjust, 0.24)

        domain_adjust = 0.0
        if domain:
            wanted = canonical_domain(domain)
            if not _domain_compatible(wanted, indexed.domains):
                return 0.0, [], False, []
            if wanted in {canonical_domain(item) for item in indexed.domains}:
                domain_adjust = 0.05

        conflicts = contrastive_modifier_conflicts(unique_informative, indexed.strong_tokens)
        contrastive_penalty = min(0.30, 0.18 * len(conflicts))
        for requested, candidate in conflicts:
            evidence.append({
                "query_term": requested,
                "facet": [],
                "source": f"contrastive-conflict:{candidate}",
            })

        rare_recall_bonus = 0.06 if rare_strong_field_match else 0.0
        value = (
            coverage + bigram_bonus + phrase_bonus + label_bonus + alias_bonus
            + anchor_adjust + primary_facet_adjust + domain_adjust
            + rare_recall_bonus - contrastive_penalty
        )
        matched.sort(reverse=True)
        atomic = indexed.entry.kind in _IDF_KINDS
        exact_alias_phrase = False
        if analysis:
            for row in analysis.associations_by_id.get(str(indexed.entry.record.get("id") or ""), []):
                phrase_tokens = tokens_of(str(row.get("phrase") or ""))
                if len(phrase_tokens) < 2:
                    continue
                facet = str(row.get("facet") or "")
                scoped = set().union(*(
                    analysis.scoped_terms.get(token, set()) for token in phrase_tokens
                )) if phrase_tokens else set()
                if scoped and facet not in scoped:
                    continue
                exact_alias_phrase = True
                break
        strong_eligible = not conflicts and (
            phrase_bonus > 0
            or label_bonus > 0
            or exact_alias_phrase
            or (indexed.entry.kind == "archetype" and anchor_total >= 2 and anchor_matches == anchor_total)
            or (atomic and strong_field_matches >= 2)
            or (
                atomic
                and strong_field_token_count >= 3
                and max_strong_idf >= 3.0
                and bigram_bonus > 0
            )
        )
        unique_evidence: list[dict[str, Any]] = []
        seen_evidence: set[tuple[str, str, str, str]] = set()
        for row in evidence:
            key = (
                str(row.get("query_term")),
                json.dumps(row.get("facet"), sort_keys=True),
                str(row.get("source")),
                str(row.get("weight", "")),
            )
            if key not in seen_evidence:
                seen_evidence.add(key)
                unique_evidence.append(row)
        return (
            max(0.0, min(3.0, value)),
            [token for _, token in matched[:4]],
            strong_eligible,
            unique_evidence,
        )
