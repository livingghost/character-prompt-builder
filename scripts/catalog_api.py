#!/usr/bin/env python3
"""Search and inspect the Character Prompt Builder pack records.

Retrieve knowledge for unresolved expression choices and inspect chosen records.
The calling agent chooses how the image communicates and authors its depiction.

Catalog retrieval accepts canonical English craft wording or a structured query
prepared by the calling agent. Source briefs may remain in any language, but
translation and semantic normalization are deliberately outside this lexical
search tool so the package does not maintain per-language word lists.
"""
from __future__ import annotations
import operation_context as _operation_context

import argparse
import json
import time
from pathlib import Path
from typing import Sequence

import prompt_retrieval
from pack_runtime_cli import add_pack_runtime_arguments, resolve_pack_runtime
from search_discovery import CatalogQueryInput, catalog_query_from_mapping

from catalog_retrieval.assets import (
    active_pack_artifact_sources,
    asset_lookup,
    linked_asset_activation,
    resolve_asset_resources,
)
from catalog_retrieval.batch import execute_batch, execute_query_command, load_batch_requests
from catalog_retrieval.command_contract import DEFAULT_INSPIRE_CATEGORIES, DEFAULT_SEARCH_KINDS, batch_help_example
from catalog_retrieval.core import (
    CONTRASTIVE_MODIFIER_GROUPS,
    MODERATE_FLOOR,
    STOPWORDS,
    STRONG_FLOOR,
    VALID_DOMAINS,
    VALID_TIERS,
    ascii_fold,
    canonical_category,
    canonical_domain,
    contrastive_modifier_conflicts,
    load_json,
    normalize,
    normalize_tier,
    parse_csv,
    record_tier,
    relevance_band,
    token_set,
    tokens_of,
)
from catalog_retrieval.discovery import recommend
from catalog_retrieval.queries import (
    analyze_catalog_query,
    ensure_supported_query,
    load_catalog_query,
    resolve_query_input,
    validate_query_request,
)
from catalog_retrieval.retrieval import (
    AXIS_CATEGORIES,
    catalog_stats,
    compact_record,
    inspect_record,
    inspire,
    search_entries,
)
from catalog_retrieval.runtime import (
    ROOT,
    Entry,
    begin_catalog_request,
    clear_corpus_cache,
    clear_runtime_caches,
    configure_pack_runtime,
    load_entries,
    load_pack_catalog,
    load_search_index,
    named_resource_path,
    require_active_catalog,
    reset_catalog_request,
    runtime_profile,
)
from catalog_retrieval.scoring import (
    Corpus,
    EXACT_SELECTION_FACETS,
    FACET_COMPATIBILITY,
    IndexedEntry,
    LEXICAL_FACET_COMPATIBILITY,
    lexical_facet_candidates,
    primary_facet_query_phrases,
    semantic_primary_facet,
)






def _recorded_lookups(args: argparse.Namespace, result: dict, *, query: str | None = None,
                      requests: Sequence[dict] | None = None) -> list[tuple[str, list[str], list[str]]]:
    """Return (element, queries, inspected records) for each lookup this command ran."""
    if args.command == "batch":
        by_id = {item["request_id"]: item for item in requests or ()}
        return [(item["request_id"], [by_id[item["request_id"]]["canonical_query"]], [])
                for item in result["results"] if item["ok"]]
    if args.command == "inspect-many":
        identifiers = [row["record_id"] for row in result["records"]]
        elements = args.element if len(args.element) != 1 else args.element * len(identifiers)
        return [(element, [], [identifier]) for element, identifier in zip(elements, identifiers)]
    if args.command == "inspect":
        return [(args.element, [], [args.record_id])]
    return [(args.element, [query] if query else [], [])]


def _check_record_arguments(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if getattr(args, "record", None) is None:
        if getattr(args, "element", None):
            parser.error("--element requires --record")
        return
    if args.command == "inspect-many":
        if len(args.element) not in {1, len(dict.fromkeys(args.record_ids))}:
            parser.error("--record needs one --element, or one --element per record ID")
    elif args.command != "batch" and not args.element:
        parser.error("--record requires --element")
