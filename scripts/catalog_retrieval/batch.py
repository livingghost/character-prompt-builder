"""Batch request loading and shared query-command execution."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from search_discovery import CatalogQueryInput, SearchIndex, catalog_query_from_mapping

from catalog_retrieval.core import load_json, normalize_tier, parse_csv
from catalog_retrieval.discovery import recommend
from catalog_retrieval.queries import analyze_catalog_query, validate_query_request
from catalog_retrieval.retrieval import inspire, search_entries
from catalog_retrieval.runtime import Entry, load_search_index

DEFAULT_SEARCH_KINDS = (
    "module,profile,aesthetic-core,style-family,domain-realization,scene,"
    "archetype,correction"
)
DEFAULT_INSPIRE_CATEGORIES = (
    "composition,camera,lighting,mood-palette,rendering,environment,"
    "pose-action,expression"
)
_BATCH_QUERY_FIELDS = {
    "canonical_query",
    "domain",
    "anchors",
    "source_brief",
    "source_language",
    "unresolved_terms",
}
_BATCH_OPTION_FIELDS = {
    "search": {
        "kind",
        "categories",
        "limit",
        "include_recipes",
        "diverse",
        "group_variants",
        "tier",
    },
    "recommend": {"directions"},
    "inspire": {
        "categories",
        "per_category",
        "tier",
        "profile_limit",
        "core_limit",
        "style_family_limit",
        "realization_limit",
        "archetype_limit",
    },
}


def batch_help_example() -> str:
    """Return one copyable ordered-query example for CLI discovery."""

    return json.dumps(
        [
            {
                "request_id": "identity",
                "command": "search",
                "canonical_query": "muscular black panther",
                "kind": ["archetype"],
                "domain": "anthropomorphic-animal",
                "limit": 6,
            },
            {
                "request_id": "scene",
                "command": "search",
                "canonical_query": "low-angle athletic action",
                "kind": ["scene"],
                "domain": "anthropomorphic-animal",
                "limit": 6,
            },
        ],
        ensure_ascii=True,
        separators=(",", ":"),
    )


def load_batch_requests(source: str) -> list[dict[str, Any]]:
    """Load one ordered batch from a file, stdin, or literal JSON array."""
    candidate = str(source or "").strip()
    if not candidate:
        raise ValueError("batch input must be a JSON array, a JSON file path, or '-'")
    try:
        if candidate == "-":
            payload = json.load(sys.stdin)
        elif candidate.startswith(("[", "{")):
            payload = json.loads(candidate)
        else:
            path = Path(candidate)
            if not path.is_file():
                raise ValueError(f"batch input file does not exist: {candidate}")
            payload = load_json(path)
    except json.JSONDecodeError as exc:
        raise ValueError(f"batch input is not valid JSON: {exc}") from exc
    if not isinstance(payload, list):
        raise ValueError("batch input must be a top-level JSON array")

    requests: list[dict[str, Any]] = []
    seen_request_ids: set[str] = set()
    for position, raw in enumerate(payload):
        if not isinstance(raw, Mapping):
            raise ValueError(f"batch item {position} must be an object")
        request_id = raw.get("request_id")
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError(
                f"batch item {position} must declare a non-empty string request_id"
            )
        request_id = request_id.strip()
        if request_id in seen_request_ids:
            raise ValueError(f"duplicate batch request_id: {request_id}")
        seen_request_ids.add(request_id)
        item = dict(raw)
        item["request_id"] = request_id
        requests.append(item)
    return requests


def _batch_string_set(value: Any, field_name: str, default: str) -> set[str]:
    selected = default if value is None else value
    if isinstance(selected, str):
        return parse_csv(selected)
    if isinstance(selected, list) and all(isinstance(item, str) for item in selected):
        return {item.strip() for item in selected if item.strip()}
    raise ValueError(f"{field_name} must be a comma-separated string or string array")


def _batch_integer(value: Any, field_name: str, default: int) -> int:
    selected = default if value is None else value
    if isinstance(selected, bool) or not isinstance(selected, int):
        raise ValueError(f"{field_name} must be an integer")
    return selected


def _batch_positive_integer(value: Any, field_name: str, default: int) -> int:
    """Return a narrowing count. Zero is a request for nothing, not for one."""
    selected = _batch_integer(value, field_name, default)
    if selected < 1:
        raise ValueError(f"{field_name} must be 1 or greater")
    return selected


def _batch_boolean(value: Any, field_name: str, default: bool) -> bool:
    selected = default if value is None else value
    if not isinstance(selected, bool):
        raise ValueError(f"{field_name} must be a boolean")
    return selected


def _batch_query_request(item: Mapping[str, Any]) -> CatalogQueryInput:
    query_data = {
        field_name: item[field_name]
        for field_name in _BATCH_QUERY_FIELDS
        if field_name in item
    }
    try:
        return validate_query_request(catalog_query_from_mapping(query_data))
    except SystemExit as exc:
        # Invalid query wording is local to this request. Runtime/catalog
        # SystemExit failures raised later must still abort the entire batch.
        raise ValueError(str(exc)) from exc


def execute_query_command(
    entries: Sequence[Entry],
    command: str,
    request: CatalogQueryInput,
    options: Mapping[str, Any],
    *,
    search_index: SearchIndex | None = None,
) -> dict[str, Any]:
    """Execute one query command against an already loaded catalog snapshot."""
    index = search_index or load_search_index()
    analysis = analyze_catalog_query(request, index)
    resolved_domain = request.domain or analysis.domain

    if command == "search":
        kinds = _batch_string_set(options.get("kind"), "kind", DEFAULT_SEARCH_KINDS)
        # ``recipe`` is absent from the default kind set, so it only ever
        # arrives here because the caller asked for it. ``--include-recipes``
        # adds it; nothing silently takes an explicit request away.
        if _batch_boolean(options.get("include_recipes"), "include_recipes", False):
            kinds.add("recipe")
        if not kinds:
            raise ValueError("kind must name at least one record kind")
        tier = str(options.get("tier", "any"))
        results = search_entries(
            entries,
            request.canonical_query,
            kinds=kinds,
            categories=_batch_string_set(options.get("categories"), "categories", ""),
            domain=resolved_domain,
            limit=_batch_positive_integer(options.get("limit"), "limit", 12),
            diverse=_batch_boolean(options.get("diverse"), "diverse", False),
            tier=tier,
            group_variants=_batch_boolean(
                options.get("group_variants"), "group_variants", True
            ),
            search_index=index,
            analysis=analysis,
        )
        result: dict[str, Any] = {
            "query_request": request.to_dict(),
            "tier": normalize_tier(tier),
            "query_analysis": analysis.to_dict(),
            "results": results,
        }
        if not results:
            result["note"] = (
                "No sufficiently relevant preset. This is a valid outcome: "
                "art-direct this aspect without preset support, or retry with "
                "different canonical wording. Short queries of three to six "
                "distinctive words usually retrieve more than one long sentence."
            )
        return result

    if command == "recommend":
        result = recommend(
            entries,
            request.canonical_query,
            resolved_domain,
            max(
                1,
                min(
                    8,
                    _batch_integer(options.get("directions"), "directions", 4),
                ),
            ),
            analysis=analysis,
            search_index=index,
        )
        result["query_request"] = request.to_dict()
        return result

    if command == "inspire":
        result = inspire(
            entries,
            request.canonical_query,
            sorted(
                _batch_string_set(
                    options.get("categories"),
                    "categories",
                    DEFAULT_INSPIRE_CATEGORIES,
                )
            ),
            resolved_domain,
            _batch_positive_integer(
                options.get("per_category"), "per_category", 4
            ),
            str(options.get("tier", "any")),
            max(
                0,
                _batch_integer(options.get("profile_limit"), "profile_limit", 3),
            ),
            max(0, _batch_integer(options.get("core_limit"), "core_limit", 3)),
            max(
                0,
                _batch_integer(
                    options.get("style_family_limit"), "style_family_limit", 3
                ),
            ),
            max(
                0,
                _batch_integer(
                    options.get("realization_limit"), "realization_limit", 2
                ),
            ),
            max(
                0,
                _batch_integer(
                    options.get("archetype_limit"), "archetype_limit", 2
                ),
            ),
            analysis=analysis,
            search_index=index,
        )
        result["query_request"] = request.to_dict()
        return result

    raise ValueError("command must be one of: search, recommend, inspire")


def execute_batch(
    entries: Sequence[Entry],
    requests: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Execute ordered requests while retaining one catalog and search index."""
    search_index = load_search_index()
    results: list[dict[str, Any]] = []
    for item in requests:
        request_id = str(item["request_id"])
        command = str(item.get("command") or "")
        try:
            if command not in _BATCH_OPTION_FIELDS:
                raise ValueError("command must be one of: search, recommend, inspire")
            allowed = {
                "request_id",
                "command",
                *_BATCH_QUERY_FIELDS,
                *_BATCH_OPTION_FIELDS[command],
            }
            unknown = sorted(set(item) - allowed)
            if unknown:
                raise ValueError("unknown request fields: " + ", ".join(unknown))
            request = _batch_query_request(item)
            result = execute_query_command(
                entries,
                command,
                request,
                item,
                search_index=search_index,
            )
            results.append({
                "request_id": request_id,
                "command": command,
                "ok": True,
                "result": result,
            })
        except ValueError as exc:
            results.append({
                "request_id": request_id,
                "command": command or None,
                "ok": False,
                "error": {
                    "type": "query-error",
                    "message": str(exc),
                },
            })
    success_count = sum(1 for item in results if item["ok"])
    return {
        "request_count": len(results),
        "success_count": success_count,
        "error_count": len(results) - success_count,
        "results": results,
    }
