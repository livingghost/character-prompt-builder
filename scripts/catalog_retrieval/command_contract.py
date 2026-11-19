"""Catalog query defaults and the complete batch example shared by CLI and execution."""
from __future__ import annotations
import json

DEFAULT_SEARCH_KINDS = (
    "module,profile,aesthetic-core,style-family,domain-realization,scene,"
    "archetype,correction"
)

DEFAULT_INSPIRE_CATEGORIES = (
    "composition,camera,lighting,mood-palette,rendering,environment,"
    "pose-action,expression"
)

def batch_help_example() -> str:
    """Return the smallest complete ordered-query example for CLI discovery."""

    return json.dumps(
        [
            {
                "request_id": "identity",
                "command": "search",
                "canonical_query": "muscular black panther",
            },
        ],
        ensure_ascii=True,
        separators=(",", ":"),
    )
