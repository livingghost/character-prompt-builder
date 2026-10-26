"""Discover catalog knowledge and vocabulary categories for an authored purpose."""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Sequence

from search_discovery import QueryAnalysis, SearchIndex, analyze_query

from catalog_retrieval.core import (
    STOPWORDS,
    _domain_compatible,
    _normalized_domains,
    canonical_domain,
    load_json,
    record_tier,
    tokens_of,
)
from catalog_retrieval.queries import ensure_supported_query
from catalog_retrieval.retrieval import search_entries
from catalog_retrieval.runtime import Entry, load_pack_catalog, load_search_index


KNOWLEDGE_KINDS = frozenset({
    "module", "profile", "aesthetic-core", "style-family", "domain-realization",
    "scene", "archetype", "correction",
})


def _catalog_inventory(
    entries: Sequence[Entry], query: str, expanded_facets: Sequence[str],
) -> dict[str, Any]:
    """Expose every available knowledge group without selecting a treatment."""
    families = Counter(entry.kind for entry in entries)
    categories = Counter(entry.category for entry in entries if entry.category)
    tiers = Counter(record_tier(entry.record) for entry in entries)
    facets: dict[str, set[str]] = defaultdict(set)
    for entry in entries:
        for name, values in (entry.record.get("search_profile") or {}).get("facets", {}).items():
            rows = [values] if isinstance(values, str) else values if isinstance(values, list) else []
            facets[str(name)].update(str(value) for value in rows if isinstance(value, str))
    expanded = set(expanded_facets)
    unknown = sorted(expanded - set(facets))
    if unknown:
        raise ValueError("Unknown authored inventory facets in the current catalog scope: " + ", ".join(unknown))
    query_tokens = set(tokens_of(query)) - STOPWORDS
    facet_inventory = {}
    for name, values in sorted(facets.items()):
        ranked = sorted(values, key=lambda value: (-len(query_tokens & set(tokens_of(value))), value))
        examples = ranked if name in expanded else ranked[:3]
        facet_inventory[name] = {
            "value_count": len(values),
            "examples": examples,
            "truncated": len(examples) < len(values),
        }
    return {
        "record_count": len(entries),
        "record_families": dict(sorted(families.items())),
        "categories": dict(sorted(categories.items())),
        "tiers": dict(sorted(tiers.items())),
        "facets": facet_inventory,
    }


def _vocabulary_categories(query: str, limit: int) -> dict[str, Any]:
    """Expose the resolved dictionary's category inventory and lexical matches."""
    resource = load_pack_catalog().resources.get("prompt-vocabulary")
    if resource is None:
        return {"available": False, "category_counts": {}, "matches": []}
    value = load_json(resource.path)
    query_tokens = set(tokens_of(query)) - STOPWORDS
    ranked: list[tuple[int, str, dict[str, Any]]] = []
    counts: dict[str, int] = {}
    for category in value.get("categories") or []:
        category_id = str(category["id"])
        counts[category_id] = len(category.get("entries") or [])
        fields = {
            "id": category_id,
            "name": str(category.get("name") or ""),
            "description": str(category.get("description") or ""),
        }
        evidence = {
            field: sorted(query_tokens & set(tokens_of(text)))
            for field, text in fields.items()
        }
        evidence = {field: words for field, words in evidence.items() if words}
        if not evidence:
            continue
        matched = sorted({word for words in evidence.values() for word in words})
        ranked.append((len(matched), category_id, {
            **fields,
            "entry_count": counts[category_id],
            "matched": matched,
            "match_evidence": evidence,
        }))
    ranked.sort(key=lambda row: (-row[0], row[1]))
    return {
        "available": True,
        "source_pack": resource.source_pack,
        "source_file": resource.relative_path,
        "category_counts": dict(sorted(counts.items())),
        "matches": [row[2] for row in ranked[:limit]],
        "note": "Categories supply vocabulary to explore; their entries are not curated catalog records.",
    }


def recommend(
    entries: Sequence[Entry],
    query: str,
    domain: str | None = None,
    limit: int = 8,
    *,
    inventory_facets: Sequence[str] = (),
    analysis: QueryAnalysis | None = None,
    search_index: SearchIndex | None = None,
) -> dict[str, Any]:
    """Retrieve candidate knowledge while leaving expression choices to the agent."""
    ensure_supported_query(query)
    if limit < 1:
        raise ValueError("limit must be 1 or greater")
    index = search_index or load_search_index()
    analysis = analysis or analyze_query(query, index, domain)
    resolved_domain = canonical_domain(domain or analysis.domain) if domain or analysis.domain else None
    scoped = [
        entry for entry in entries
        if entry.kind in KNOWLEDGE_KINDS
        and (not resolved_domain or _domain_compatible(resolved_domain, _normalized_domains(entry.record)))
    ]
    inventory = _catalog_inventory(scoped, query, inventory_facets)
    matches = search_entries(
        scoped, query, kinds=set(KNOWLEDGE_KINDS), categories=set(),
        domain=resolved_domain, limit=limit, diverse=True, tier="any",
        group_variants=True, search_index=index, analysis=analysis,
    )
    candidate_fields = {
        "id", "label", "kind", "category", "tier", "source_pack", "source_file",
        "domain", "domains", "applies_to", "applicability", "outcome_summary", "visual_function",
        "invariants", "compatible_with", "avoid_with", "variation_examples",
        "discovery_group", "variant_of", "related_variants", "relevance", "matched",
        "match_evidence", "linked_asset_activation",
    }
    candidates = [
        {key: value for key, value in row.items() if key in candidate_fields}
        for row in matches
    ]
    return {
        "mode": "knowledge-discovery",
        "query_analysis": analysis.to_dict(),
        "scope": {
            "domain": resolved_domain,
            "source_packs": sorted({entry.source_pack for entry in scoped}),
        },
        "candidates": candidates,
        "catalog_inventory": inventory,
        "vocabulary": _vocabulary_categories(query, limit),
        "inspection_queue": [str(row["id"]) for row in candidates],
        "terms_without_alias": list(analysis.terms_without_alias),
        "note": (
            "Candidates are ordered by textual evidence and grouped for variety. "
            "Inventory counts describe available knowledge, not suitability. "
            "Inspect complete records before adapting them; the agent chooses the expression."
            if candidates else
            "No sufficiently relevant catalog record. The inventory shows available knowledge, "
            "not a recommended fallback. Explore another purpose or author the expression directly."
        ),
    }
