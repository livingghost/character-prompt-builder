#!/usr/bin/env python3
"""Search and inspect the Character Prompt Builder preset library.

This script is deliberately not a prompt generator. It supports two retrieval
paths: focused lookup after an art direction exists, and sparse-brief discovery
that preserves explicit identity anchors while proposing several coherent
visual directions for unspecified axes.

Catalog retrieval accepts canonical English craft wording or a structured query
prepared by the calling agent. Source briefs may remain in any language, but
translation and semantic normalization are deliberately outside this lexical
search tool so the package does not maintain per-language word lists.
"""
from __future__ import annotations

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
from catalog_retrieval.batch import (
    DEFAULT_INSPIRE_CATEGORIES,
    DEFAULT_SEARCH_KINDS,
    batch_help_example,
    execute_batch,
    execute_query_command,
    load_batch_requests,
)
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
from catalog_retrieval.discovery import load_discovery_lanes, recommend
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


def _add_query_source_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "query",
        nargs="?",
        help=(
            "Canonical English retrieval wording prepared by the calling agent. "
            "Do not pass untranslated user-language prose."
        ),
    )
    parser.add_argument(
        "--query-json",
        metavar="PATH",
        help=(
            "Structured catalog-query JSON. Use '-' for stdin. The JSON may "
            "retain an arbitrary-language source_brief, but canonical_query and anchors "
            "must use canonical English catalog wording."
        ),
    )


def _add_record_arguments(parser: argparse.ArgumentParser, *, element: str | None = "one") -> None:
    parser.add_argument(
        "--record",
        type=Path,
        metavar="PATH",
        help=(
            "Append this lookup to a prompt retrieval record, created when absent. "
            "Mark each element's outcome afterward with prompt_retrieval.py."
        ),
    )
    if element == "one":
        parser.add_argument("--element", help="Visual element this lookup serves, such as pose or lighting")
    elif element == "each":
        parser.add_argument(
            "--element",
            action="append",
            default=[],
            help="Visual element: give one for every ID, or one per ID in order",
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


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Search Character Prompt Builder presets without generating a prompt. "
            "The calling agent translates and normalizes the user brief; this tool "
            "accepts canonical English retrieval wording or structured canonical facets."
        )
    )
    add_pack_runtime_arguments(parser)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("stats", help="Show catalog counts")
    consultation = sub.add_parser("consult", help="Search explicit craft layers and open complete chosen records in one runtime.")
    consultation.add_argument("query", nargs="?")
    import craft_consultation
    consultation.add_argument("--focus", choices=["all", *craft_consultation.LAYERS], default="all")
    consultation.add_argument("--inspect", nargs="*", default=[], metavar="ID")
    consultation.add_argument("--previous", type=Path)


    inspect_parser = sub.add_parser(
        "inspect",
        help=(
            "Return one complete canonical preset record plus a compact linked-asset "
            "activation summary. Use asset-lookup for asset records and resources."
        ),
    )
    inspect_parser.add_argument("record_id")
    inspect_parser.add_argument(
        "--out",
        metavar="PATH",
        help="Write UTF-8 JSON to PATH instead of standard output.",
    )
    _add_record_arguments(inspect_parser)

    inspect_many = sub.add_parser(
        "inspect-many", help="Read complete records plus all linked asset details under one fresh runtime snapshot")
    inspect_many.add_argument("record_ids", nargs="+")
    inspect_many.add_argument("--out", metavar="PATH")
    _add_record_arguments(inspect_many, element="each")

    asset_lookup_parser = sub.add_parser(
        "asset-lookup",
        help=(
            "Discover one asset ID or every asset linked to one canonical record, "
            "including owning-pack resource paths; this does not build a reference plan."
        ),
    )
    asset_lookup_parser.add_argument("lookup_id")
    asset_lookup_parser.add_argument(
        "--summary",
        action="store_true",
        help=(
            "Return only asset IDs and artifact role/media-type metadata. "
            "Omit complete records, resources, hashes, and resolved paths."
        ),
    )

    batch_parser = sub.add_parser(
        "batch",
        help=(
            "Run ordered search, recommend, and inspire requests in one catalog "
            "process. Input is a JSON array file, '-' for stdin, or a literal array."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Supported commands: search, recommend, and inspire. "
            "Each request requires request_id, command, and canonical_query. "
            "Command-specific options use the same names as the individual CLI.\n"
            "Example JSON:\n" + batch_help_example()
        ),
    )
    batch_parser.add_argument(
        "--input",
        dest="requests",
        required=True,
        metavar="JSON_OR_PATH",
        help=(
            "Ordered JSON request array, path to a UTF-8 JSON file, or '-' for stdin. "
            "Every object requires a unique request_id and a command."
        ),
    )
    _add_record_arguments(batch_parser, element=None)

    search = sub.add_parser("search", help="Look up preset records from canonical descriptive wording")
    _add_query_source_arguments(search)
    _add_record_arguments(search)
    search.add_argument("--kind", default=DEFAULT_SEARCH_KINDS)
    search.add_argument("--categories", default="")
    search.add_argument("--domain", choices=sorted(VALID_DOMAINS))
    search.add_argument("--limit", type=int, default=12)
    search.add_argument("--include-recipes", action="store_true")
    search.add_argument("--diverse", action="store_true")
    search.add_argument(
        "--group-variants",
        dest="group_variants",
        action="store_true",
        default=True,
        help="Collapse one discovery family into a representative result (default).",
    )
    search.add_argument(
        "--ungrouped",
        dest="group_variants",
        action="store_false",
        help="Return every matching variant separately for debugging or exhaustive inspection.",
    )
    search.add_argument(
        "--tier",
        choices=sorted(VALID_TIERS),
        default="any",
        help="Record role for this retrieval question. Default: any.",
    )

    recommendation = sub.add_parser(
        "recommend",
        help="Explore coherent visual directions from a sparse canonical brief without requiring preset names or IDs.",
    )
    _add_query_source_arguments(recommendation)
    _add_record_arguments(recommendation)
    recommendation.add_argument("--domain", choices=sorted(VALID_DOMAINS))
    recommendation.add_argument("--directions", type=int, default=4)

    inspiration = sub.add_parser("inspire", help="Retrieve diverse atomic ingredients for a chosen direction")
    _add_query_source_arguments(inspiration)
    _add_record_arguments(inspiration)
    inspiration.add_argument(
        "--categories",
        default=DEFAULT_INSPIRE_CATEGORIES,
    )
    inspiration.add_argument("--domain", choices=sorted(VALID_DOMAINS))
    inspiration.add_argument("--per-category", type=int, default=4)
    inspiration.add_argument(
        "--tier",
        choices=sorted(VALID_TIERS),
        default="any",
        help=(
            "Atomic-record role for this retrieval question. Default: any. "
            "Rendering-profile candidates remain curated."
        ),
    )
    inspiration.add_argument("--profile-limit", type=int, default=3, help="Number of curated rendering-profile candidates")
    inspiration.add_argument("--core-limit", type=int, default=3, help="Number of curated universal aesthetic-core candidates")
    inspiration.add_argument("--style-family-limit", type=int, default=3, help="Number of curated concrete style-family candidates")
    inspiration.add_argument("--realization-limit", type=int, default=2, help="Number of curated domain-realization candidates")
    inspiration.add_argument("--archetype-limit", type=int, default=2, help="Number of subject-archetype identity candidates")

    args = parser.parse_args(argv)
    _check_record_arguments(parser, args)
    runtime = resolve_pack_runtime(parser, args)
    configure_pack_runtime(runtime.settings)
    if args.command == "consult":
        try:
            questions = ([{"request_id": "craft", "canonical_query": args.query, "focus": args.focus}]
                         if args.query else [])
            previous = load_json(args.previous) if args.previous else None
            result = craft_consultation.consult(questions, args.inspect, settings=runtime.settings, previous=previous)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["ok"] else 1
        except (ValueError, OSError, KeyError, TypeError) as exc:
            parser.error(str(exc))
        finally:
            configure_pack_runtime(None)
    try:
        batch_requests = (
            load_batch_requests(args.requests)
            if args.command == "batch"
            else None
        )
        started = time.perf_counter()
        catalog = begin_catalog_request()
        runtime_seconds = time.perf_counter() - started
        record = getattr(args, "record", None)
        if record is not None:
            prompt_retrieval.check_recordable(record, catalog.fingerprint)
        entries = load_entries()
        request = None
        if args.command == "stats":
            result = catalog_stats(entries)
            result["active_pack_count"] = catalog.active_pack_count
            result["diagnostics"] = list(catalog.diagnostics)
        elif args.command == "inspect":
            require_active_catalog(catalog)
            result = inspect_record(entries, args.record_id)
        elif args.command == "inspect-many":
            require_active_catalog(catalog)
            identifiers = list(dict.fromkeys(args.record_ids))
            if not identifiers:
                raise ValueError("inspect-many requires at least one distinct record ID")
            rows = []
            for identifier in identifiers:
                item_start = time.perf_counter()
                rows.append({"record_id": identifier,
                             "record": inspect_record(entries, identifier),
                             "assets": asset_lookup(identifier, summary=False),
                             "elapsed_seconds": round(time.perf_counter() - item_start, 6)})
            result = {"ok": True, "runtime_fingerprint": catalog.fingerprint,
                      "active_pack_count": catalog.active_pack_count,
                      "record_source_pack_ids": sorted({entry.source_pack for entry in catalog.entries}),
                      "records": rows, "diagnostics": list(catalog.diagnostics),
                      "timing": {"runtime_seconds": round(runtime_seconds, 6),
                                 "total_seconds": round(time.perf_counter() - started, 6)}}
        elif args.command == "asset-lookup":
            require_active_catalog(catalog)
            result = asset_lookup(args.lookup_id, summary=args.summary)
        elif args.command == "batch":
            require_active_catalog(catalog)
            assert batch_requests is not None
            result = execute_batch(entries, batch_requests)
        else:
            require_active_catalog(catalog)
            request = resolve_query_input(args.query, args.query_json, args.domain)
            result = execute_query_command(
                entries,
                args.command,
                request,
                vars(args),
            )
        if record is not None:
            for element, queries, inspected in _recorded_lookups(
                    args, result, query=request.canonical_query if request else None, requests=batch_requests):
                prompt_retrieval.record_lookup(record, element, queries=queries, inspected=inspected,
                                               pack_state=catalog.fingerprint)
    except ValueError as exc:
        parser.error(str(exc))
    finally:
        configure_pack_runtime(None)
    serialized = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.command in {"inspect", "inspect-many"} and args.out:
        output_path = Path(args.out)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(serialized, encoding="utf-8")
    else:
        print(serialized, end="")
    return 0


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
