"""Canonical query-input parsing, validation, and analysis bridging."""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Mapping

from search_discovery import (
    ANCHOR_FACETS,
    CatalogQueryInput,
    QueryAnalysis,
    SearchIndex,
    analyze_query,
    catalog_query_from_mapping,
)

from catalog_retrieval.core import ascii_fold, canonical_domain, load_json, normalize
from catalog_retrieval.runtime import load_search_index

def ensure_supported_query(query: str) -> None:
    """Require canonical English retrieval text without language-specific branches."""
    raw = str(query or "")
    if not re.sub(r"\s+", "", raw):
        raise SystemExit(
            "Empty canonical query. Supply concise English retrieval wording or "
            "use --query-json with canonical_query and structured anchors."
        )
    folded = ascii_fold(raw)
    foreign_letters = [
        ch for ch in folded
        if ord(ch) > 127 and unicodedata.category(ch).startswith("L")
    ]
    if foreign_letters:
        raise SystemExit(
            "The deterministic catalog accepts canonical English retrieval text, "
            "not raw user-language prose. Translate the complete brief semantically "
            "in the calling agent or use --query-json. source_brief may preserve the "
            "original wording for audit. The package maintains no per-language alias table."
        )
    if not normalize(raw):
        raise SystemExit(
            "The canonical query contains no searchable English terms. Translate "
            "the brief before retrieval or supply structured English anchors."
        )


def load_catalog_query(path_value: str) -> CatalogQueryInput:
    """Load a structured query from a JSON file or standard input (`-`)."""
    if path_value == "-":
        data = json.load(sys.stdin)
    else:
        data = load_json(Path(path_value))
    if not isinstance(data, Mapping):
        raise ValueError("catalog query JSON must be an object")
    return catalog_query_from_mapping(data)


def resolve_query_input(
    query: str | None,
    query_json: str | None,
    cli_domain: str | None = None,
) -> CatalogQueryInput:
    """Resolve one canonical query source and preserve opaque source metadata."""
    if bool(query) == bool(query_json):
        raise ValueError("provide exactly one of the query argument or --query-json")
    if query_json:
        request = load_catalog_query(query_json)
    else:
        request = CatalogQueryInput(canonical_query=str(query), domain=cli_domain)
    return validate_query_request(request, cli_domain)


def validate_query_request(
    request: CatalogQueryInput,
    cli_domain: str | None = None,
) -> CatalogQueryInput:
    """Validate one structured request regardless of its transport."""
    if cli_domain and request.domain and cli_domain != request.domain:
        raise ValueError(
            f"domain conflict: request specified {request.domain}, command specified "
            f"{cli_domain}"
        )
    if cli_domain:
        request.domain = cli_domain
    ensure_supported_query(request.canonical_query)
    for facet, values in request.anchors.items():
        if facet not in ANCHOR_FACETS:
            raise ValueError(
                f"unknown structured anchor facet `{facet}`; use one of: "
                + ", ".join(sorted(ANCHOR_FACETS))
            )
        for value in values:
            try:
                ensure_supported_query(value)
            except SystemExit as exc:
                raise ValueError(
                    f"structured anchor `{facet}` must use canonical English craft wording: {value!r}"
                ) from exc
    if request.domain:
        request.domain = canonical_domain(request.domain)
    return request


def analyze_catalog_query(
    request: CatalogQueryInput,
    search_index: SearchIndex | None = None,
) -> QueryAnalysis:
    index = search_index or load_search_index()
    return analyze_query(
        request.canonical_query,
        index,
        request.domain,
        explicit_anchors=request.anchors,
        source_brief=request.source_brief,
        source_language=request.source_language,
        unresolved_terms=request.unresolved_terms,
    )
