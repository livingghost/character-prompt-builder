"""Retrieval orchestration: stats, inspection, search, and inspire."""
from __future__ import annotations

import hashlib
from typing import Any, Mapping, Sequence

from search_discovery import QueryAnalysis, SearchIndex, analyze_query

import catalog_retrieval.runtime as runtime
from catalog_retrieval.assets import linked_asset_activation
from catalog_retrieval.core import (
    STOPWORDS,
    _domain_compatible,
    _normalized_domains,
    canonical_category,
    canonical_domain,
    normalize,
    normalize_tier,
    record_tier,
    relevance_band,
    tokens_of,
)
from catalog_retrieval.queries import ensure_supported_query
from catalog_retrieval.runtime import (
    Entry,
    _lru_get,
    _lru_put,
    load_search_index,
    runtime_profile,
)
from catalog_retrieval.scoring import (
    Corpus,
    EXACT_SELECTION_FACETS,
    primary_facet_query_phrases,
    semantic_primary_facet,
)

def catalog_stats(entries: Sequence[Entry]) -> dict[str, Any]:
    kind_counts: dict[str, int] = {}
    module_counts: dict[str, int] = {}
    for entry in entries:
        kind_counts[entry.kind] = kind_counts.get(entry.kind, 0) + 1
        if entry.kind == "module":
            category = entry.category or "uncategorized"
            module_counts[category] = module_counts.get(category, 0) + 1
    return {
        "total_records": len(entries),
        "record_families": dict(sorted(kind_counts.items())),
        "module_categories": dict(sorted(module_counts.items())),
    }




def inspect_record(entries: Sequence[Entry], record_id: str) -> dict[str, Any]:
    requested_id = str(record_id)
    for entry in entries:
        if str(entry.record.get("id")) == requested_id:
            if entry.kind == "asset":
                raise SystemExit(
                    f"{requested_id!r} is an asset ID. Use asset-lookup for asset records "
                    "and artifact resources."
                )
            result = {
                "record_id": requested_id,
                "kind": entry.kind,
                "category": entry.category,
                "source_pack": entry.source_pack,
                "source_file": entry.source_file,
                "tier": record_tier(entry.record),
                "record": entry.record,
                "linked_asset_activation": linked_asset_activation(requested_id),
                "note": (
                    "This is the complete curated canonical record. Use its structured "
                    "relationships, not only its label, tags, or compact search excerpt."
                    if record_tier(entry.record) == "curated" else
                    "This is a VOCABULARY record. Its job is supplying a name and "
                    "model-legible phrasing, and this is the whole record, not a summary "
                    "of something richer. Protocol: borrow the wording, then supply the "
                    "craft decisions (staging, light, rendering, relationships) from your "
                    "own art direction; do not preserve this record as if it were one."
                ),
            }
            return result
    raise SystemExit(f"Unknown preset id: {record_id}")


def compact_record(
    entry: Entry,
    band: str,
    matched: Sequence[str],
    evidence: Sequence[Mapping[str, Any]] | None = None,
    profile: Mapping[str, Any] | None = None,
    related_variants: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    record = entry.record
    profile = dict(profile or runtime_profile(entry, load_search_index()))
    record_id = str(record.get("id") or "")
    output: dict[str, Any] = {
        "kind": entry.kind,
        "category": entry.category,
        "source_pack": entry.source_pack,
        "id": record.get("id"),
        "label": record.get("label"),
        "domain": record.get("domain"),
        "domains": record.get("domains"),
        "applies_to": record.get("applies_to"),
        "tags": record.get("tags"),
        "prompt": record.get("prompt") or record.get("rendering") or record.get("positive_correction"),
        "curation_status": record.get("curation_status"),
        "visual_function": record.get("visual_function"),
        "invariants": record.get("invariants"),
        "misreadings_to_avoid": record.get("misreadings_to_avoid"),
        "image_promise": record.get("image_promise"),
        "must_preserve": record.get("must_preserve"),
        "medium_family": record.get("medium_family"),
        "aesthetic_promise": record.get("aesthetic_promise"),
        "appeal_center": record.get("appeal_center"),
        "style_promise": record.get("style_promise"),
        "visual_signature": record.get("visual_signature"),
        "base_render_profile_id": record.get("base_render_profile_id"),
        "compatible_render_profile_ids": record.get("compatible_render_profile_ids"),
        "realization_promise": record.get("realization_promise"),
        "subject_domain": record.get("subject_domain"),
        "realization_level": record.get("realization_level"),
        "base_realization": record.get("base_realization"),
        "compatible_medium_families": record.get("compatible_medium_families"),
        "integration_prompt": record.get("integration_prompt"),
        "best_for": record.get("best_for"),
        "avoid_for": record.get("avoid_for"),
        "outcome_summary": profile.get("outcome_summary"),
        "discovery_group": profile.get("discovery_group"),
        "variant_of": profile.get("variant_of"),
        "variation_examples": profile.get("variation_examples"),
        "tier": record_tier(record),
        "relevance": band,
        "matched": list(matched),
        "match_evidence": list(evidence or []),
        "related_variants": list(related_variants or []),
        "linked_asset_activation": linked_asset_activation(record_id),
    }
    filtered = {
        key: value for key, value in output.items()
        if value not in (None, [], "")
    }
    # Zero linked assets is meaningful and must remain visible so callers know
    # that the separate visual-activation lookup has nothing to retrieve.
    filtered["linked_asset_activation"] = output["linked_asset_activation"]
    return filtered


def search_entries(
    entries: Sequence[Entry],
    query: str,
    *,
    kinds: set[str],
    categories: set[str],
    domain: str | None,
    limit: int,
    diverse: bool,
    tier: str | None = "any",
    group_variants: bool = False,
    search_index: SearchIndex | None = None,
    analysis: QueryAnalysis | None = None,
) -> list[dict[str, Any]]:
    ensure_supported_query(query)
    # Asking for nothing is answered with nothing. The selection loops below
    # append a candidate before they test the running count, so a limit of zero
    # or less has to be settled at the door.
    if limit <= 0:
        return []
    search_index = search_index or load_search_index()
    analysis = analysis or analyze_query(query, search_index, domain)
    query_norm = normalize(analysis.normalized_query)
    query_tokens = tokens_of(analysis.normalized_query)
    wanted_categories = {canonical_category(category) for category in categories}
    wanted_tier = normalize_tier(tier)
    wanted_domain = canonical_domain(domain) if domain else (canonical_domain(analysis.domain) if analysis.domain else None)

    eligible: list[Entry] = []
    for entry in entries:
        if kinds and entry.kind not in kinds:
            continue
        if wanted_categories and canonical_category(entry.category or "") not in wanted_categories:
            continue
        if wanted_tier != "any" and record_tier(entry.record) != wanted_tier:
            continue
        if wanted_domain and not _domain_compatible(wanted_domain, _normalized_domains(entry.record)):
            continue
        eligible.append(entry)
    if not eligible:
        return []

    eligible_signature = hashlib.sha256(
        "\n".join(entry.fingerprint for entry in eligible).encode("utf-8")
    ).hexdigest()
    cache_key = (
        eligible_signature,
        tuple(sorted(kinds)),
        tuple(sorted(wanted_categories)),
        wanted_tier,
        wanted_domain or "",
        search_index.fingerprint,
    )
    corpus = _lru_get(runtime._CORPUS_CACHE, cache_key)
    if corpus is None:
        corpus = Corpus(eligible, search_index)
        _lru_put(runtime._CORPUS_CACHE, cache_key, corpus, runtime._MAX_CORPUS_CACHE)
    eligible_primary_facets = {
        semantic_primary_facet(entry.kind, entry.category)
        for entry in eligible
    }
    singular_semantic_scope = bool(wanted_categories) or len(eligible_primary_facets) == 1
    required_phrases_by_facet = {
        facet: primary_facet_query_phrases(analysis, search_index, facet)
        for facet in eligible_primary_facets
        if facet in EXACT_SELECTION_FACETS
    } if singular_semantic_scope else {}
    candidates: list[tuple[float, str, list[str], list[dict[str, Any]], int]] = []
    for candidate_index in corpus.candidate_indices(query_tokens, analysis):
        indexed = corpus.indexed_at(candidate_index)
        primary_facet = semantic_primary_facet(
            indexed.entry.kind,
            indexed.entry.category,
        )
        value, matched, strong_eligible, evidence = corpus.score(
            indexed,
            query_tokens,
            query_norm,
            wanted_domain,
            analysis,
            required_primary_phrases=required_phrases_by_facet.get(
                primary_facet,
                (),
            ),
        )
        band = relevance_band(value, strong_eligible)
        if band:
            candidates.append((value, band, matched, evidence, candidate_index))
    candidates.sort(
        key=lambda item: (
            -item[0],
            0 if record_tier(corpus.entries[item[4]].record) == "curated" else 1,
            str(corpus.entries[item[4]].record.get("id") or ""),
        )
    )

    selected: list[tuple[str, list[str], list[dict[str, Any]], int]] = []
    seen_buckets: set[tuple[str, str]] = set()
    seen_groups: set[str] = set()
    grouped_siblings: dict[str, list[dict[str, Any]]] = {}

    if group_variants:
        for _value, _band, _matched, _evidence, candidate_index in candidates:
            entry = corpus.entries[candidate_index]
            profile = runtime_profile(entry, search_index)
            group = str(profile.get("discovery_group") or entry.record.get("id") or "")
            grouped_siblings.setdefault(group, []).append({
                "id": entry.record.get("id"),
                "label": entry.record.get("label"),
                "tier": record_tier(entry.record),
            })

    for value, band, matched, evidence, candidate_index in candidates:
        entry = corpus.entries[candidate_index]
        profile = runtime_profile(entry, search_index)
        bucket = (entry.kind, entry.category or "")
        group = str(profile.get("discovery_group") or entry.record.get("id") or "")
        if group_variants and group in seen_groups:
            continue
        if diverse and bucket in seen_buckets and len(selected) < max(3, limit // 2):
            continue
        selected.append((band, matched, evidence, candidate_index))
        seen_buckets.add(bucket)
        seen_groups.add(group)
        if len(selected) >= limit:
            break

    if len(selected) < limit and not group_variants:
        selected_ids = {
            str(corpus.entries[candidate_index].record.get("id"))
            for _, _, _, candidate_index in selected
        }
        for value, band, matched, evidence, candidate_index in candidates:
            record_id = str(corpus.entries[candidate_index].record.get("id"))
            if record_id in selected_ids:
                continue
            selected.append((band, matched, evidence, candidate_index))
            selected_ids.add(record_id)
            if len(selected) >= limit:
                break

    output: list[dict[str, Any]] = []
    for band, matched, evidence, candidate_index in selected:
        entry = corpus.entries[candidate_index]
        profile = runtime_profile(entry, search_index)
        group = str(profile.get("discovery_group") or entry.record.get("id") or "")
        siblings = [
            row for row in grouped_siblings.get(group, [])
            if str(row.get("id")) != str(entry.record.get("id"))
        ][:8]
        output.append(compact_record(
            entry, band, matched, evidence, profile, siblings
        ))
    return output


def _domain_realization_candidates(
    entries: Sequence[Entry],
    query: str,
    domain: str | None,
    limit: int,
    *,
    analysis: QueryAnalysis | None = None,
    search_index: SearchIndex | None = None,
) -> list[dict[str, Any]]:
    if not domain or limit <= 0:
        return []
    wanted = canonical_domain(domain)
    compatible = [
        entry for entry in entries
        if entry.kind == "domain-realization"
        and record_tier(entry.record) == "curated"
        and _domain_compatible(wanted, _normalized_domains(entry.record))
    ]
    if not compatible:
        return []

    # Query relevance may identify a specialized realization. The foundational
    # realization remains available because it translates the entire art
    # direction into the selected subject domain rather than acting as a style
    # suggestion. Future specialized realizations can rank beside it.
    retrieved = search_entries(
        entries, query, kinds={"domain-realization"}, categories=set(),
        domain=wanted, limit=max(limit, 1), diverse=False, tier="curated",
        search_index=search_index, analysis=analysis,
    )
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    foundations = sorted(
        (entry for entry in compatible if entry.record.get("base_realization") is True),
        key=lambda entry: str(entry.record.get("id") or ""),
    )
    for entry in foundations:
        rid = str(entry.record.get("id") or "")
        selected.append(compact_record(entry, "domain-foundation", [wanted]))
        seen.add(rid)
        if len(selected) >= limit:
            return selected
    for item in retrieved:
        rid = str(item.get("id") or "")
        if rid in seen:
            continue
        selected.append(item)
        seen.add(rid)
        if len(selected) >= limit:
            break
    return selected


# Requested atomic categories are mapped onto the eight art-direction axes so
# a retrieval pass can report which axes it never asked about. The mapping is
# advisory coverage information, never a requirement to query every axis.
AXIS_CATEGORIES: dict[str, tuple[str, ...]] = {
    "center_of_appeal": ("emotion-nuance", "expression"),
    "viewer_or_environment_relationship": ("head-gaze", "gesture", "pose-action"),
    "composition_and_visual_hierarchy": ("composition", "camera", "shot-type"),
    "medium_family": ("rendering", "illustration-medium"),
    "shape_and_rhythm": ("body-build", "proportion", "movement"),
    "surface_and_tactility": ("animal-surface", "material", "skin-detail", "effect"),
    "color_and_light": ("lighting", "mood-palette", "color-role", "time-of-day"),
    "detail_hierarchy": ("rendering", "aesthetic-touch"),
}


def inspire(
    entries: Sequence[Entry],
    query: str,
    categories: Sequence[str],
    domain: str | None,
    per_category: int,
    tier: str | None = "any",
    profile_limit: int = 3,
    core_limit: int = 3,
    style_family_limit: int = 3,
    realization_limit: int = 2,
    archetype_limit: int = 2,
    *,
    analysis: QueryAnalysis | None = None,
    search_index: SearchIndex | None = None,
) -> dict[str, Any]:
    ensure_supported_query(query)
    search_index = search_index or load_search_index()
    analysis = analysis or analyze_query(query, search_index, domain)
    resolved_domain = canonical_domain(domain) if domain else (
        canonical_domain(analysis.domain) if analysis.domain else None
    )
    wanted_tier = normalize_tier(tier)
    output: dict[str, Any] = {}
    category_queries: dict[str, str | None] = {}
    for category in categories:
        canonical = canonical_category(category)
        if canonical in output:
            continue
        category_queries[canonical] = query
        output[canonical] = search_entries(
            entries,
            query,
            kinds={"module"},
            categories={canonical},
            domain=resolved_domain,
            limit=per_category,
            diverse=False,
            tier=wanted_tier,
            search_index=search_index,
            analysis=analysis,
        )

    # Aesthetic cores are domain-neutral taste references. They may clarify an
    # already chosen art direction, but the art direction remains authoritative.
    aesthetic_cores = search_entries(
        entries,
        query,
        kinds={"aesthetic-core"},
        categories=set(),
        domain=resolved_domain,
        limit=max(0, core_limit),
        diverse=False,
        tier="curated",
        search_index=search_index,
        analysis=analysis,
    ) if core_limit > 0 else []

    # Concrete style families bind line, form, value, highlight, color,
    # surface, background, and detail behavior into one indivisible drawing
    # grammar. Select zero or one after the art direction is chosen.
    style_families = search_entries(
        entries,
        query,
        kinds={"style-family"},
        categories=set(),
        domain=resolved_domain,
        limit=max(0, style_family_limit),
        diverse=False,
        tier="curated",
        search_index=search_index,
        analysis=analysis,
    ) if style_family_limit > 0 else []

    # Domain realizations translate the selected art direction and any chosen
    # core into valid anatomy, behavior, surfaces, and expression channels for
    # the actual subject domain. One foundational realization is returned when
    # a canonical domain is supplied.
    domain_realizations = _domain_realization_candidates(
        entries, query, resolved_domain, max(0, realization_limit),
        analysis=analysis, search_index=search_index,
    )

    # Rendering profiles remain complete medium grammars and are retrieved
    # separately from taste and subject-domain realization.
    render_profiles = search_entries(
        entries,
        query,
        kinds={"profile"},
        categories=set(),
        domain=resolved_domain,
        limit=max(0, profile_limit),
        diverse=False,
        tier="curated",
        search_index=search_index,
        analysis=analysis,
    ) if profile_limit > 0 else []

    # Character archetypes are identity contracts (stable morphology, palette,
    # marking logic, proportions). Surfacing them here lets the agent adopt an
    # existing subject identity, or diverge from it deliberately, before
    # designing colors and markings from a blank page.
    subject_archetypes = search_entries(
        entries,
        query,
        kinds={"archetype"},
        categories=set(),
        domain=resolved_domain,
        limit=max(0, archetype_limit),
        diverse=False,
        tier="any",
        search_index=search_index,
        analysis=analysis,
    ) if archetype_limit > 0 else []

    informative_tokens = [t for t in tokens_of(analysis.normalized_query) if t not in STOPWORDS]
    query_token_count = len(dict.fromkeys(informative_tokens))
    requested = {canonical_category(c) for c in categories}
    covered_axes = sorted(
        axis for axis, cats in AXIS_CATEGORIES.items() if requested & set(cats)
    )
    unqueried_axes = {
        axis: list(cats)
        for axis, cats in sorted(AXIS_CATEGORIES.items())
        if not requested & set(cats)
    }

    result: dict[str, Any] = {
        "query": query,
        "query_analysis": analysis.to_dict(),
        "query_token_count": query_token_count,
        "domain": canonical_domain(resolved_domain) if resolved_domain else None,
        "tier": wanted_tier,
        "profile_tier": "curated",
        "aesthetic_core_tier": "curated",
        "style_family_tier": "curated",
        "domain_realization_tier": "curated",
        "note": (
            "These are optional discovery candidates ordered by textual relevance, "
            "not creative quality. Empty atomic categories, aesthetic_cores, style_families, "
            "or render_profiles are valid. The art direction already contains the aesthetic "
            "decision. Choose at most one aesthetic core and at most one concrete style family. "
            "A selected style family is the primary drawing grammar; its linked rendering profile "
            "supplies the medium envelope and scoped negative boundary rather than a second full "
            "grammar. Use one domain realization matching each actual subject domain. "
            "subject_archetypes are identity contracts: adopt a matching one or diverge from it "
            "deliberately, and honor constraints marked automatic_prompt_injection when adopted. "
            "Base scenes and finished recipes are reachable through `search --kind scene` and "
            "`search --include-recipes`, and are intentionally absent from this layered response. "
            "Run `catalog_cli.py inspect <id>` for every selected record before prompt construction."
        ),
        "aesthetic_cores": aesthetic_cores,
        "style_families": style_families,
        "domain_realizations": domain_realizations,
        "render_profiles": render_profiles,
        "subject_archetypes": subject_archetypes,
        "category_queries": category_queries,
        "categories": output,
        "axis_coverage": {
            "covered": covered_axes,
            "unqueried": unqueried_axes,
        },
    }
    if requested and output and all(not hits for hits in output.values()):
        result["retrieval_note"] = (
            f"Every requested atomic category returned zero results for a query of "
            f"{query_token_count} informative words. With more than about eight informative "
            f"words this usually indicates query dilution rather than absent coverage: retry "
            f"each craft question as its own query of three to six distinctive words before "
            f"concluding that the catalog lacks support. Scenes, archetypes, and recipes are "
            f"reachable through `search --kind`."
        )
    return result
