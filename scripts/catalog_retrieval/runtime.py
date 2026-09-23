"""Single owner of all mutable catalog-runtime state and its lifecycle."""
from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pack_cache import RuntimePackCatalog, RuntimePackEntry, load_runtime_catalog
from pack_manager import PackSettings
from search_discovery import (
    SearchIndex,
    infer_discovery_group,
    infer_outcome_summary,
    infer_variant_of,
    profile_aliases,
    profile_for,
)

# Import the module, not its classes: scoring also uses this runtime. Concrete
# type names are resolved after initialization, without a TYPE_CHECKING-only
# binding or a custom namespace for typing.get_type_hints().
from catalog_retrieval import scoring
from catalog_retrieval.core import record_tier

ROOT = Path(__file__).resolve().parents[2]
_SEARCH_INDEX_CACHE: SearchIndex | None = None
_CORPUS_CACHE: OrderedDict[tuple[Any, ...], scoring.Corpus] = OrderedDict()
_MAX_CORPUS_CACHE = 12
_MAX_RUNTIME_PROFILE_CACHE = 16_384
_MAX_INDEXED_ENTRY_CACHE = 32_768
_RUNTIME_PROFILE_CACHE: OrderedDict[tuple[str, str], dict[str, Any]] = OrderedDict()
_INDEXED_ENTRY_CACHE: OrderedDict[tuple[str, str], scoring.IndexedEntry] = OrderedDict()
_ASSET_DETAIL_CACHE: OrderedDict[tuple[str, str], dict[str, Any]] = OrderedDict()
_PACK_CATALOG_CACHE: RuntimePackCatalog | None = None
_PACK_SETTINGS: PackSettings | None = None


def clear_corpus_cache() -> None:
    """Release query-subset corpus objects while retaining per-record indexing.

    Long regression suites call many different category/domain combinations.
    Keeping every subset corpus is unnecessary once one case is complete and
    can retain large document-frequency and token-routing dictionaries.
    """
    _CORPUS_CACHE.clear()


def _clear_derived_runtime_caches() -> None:
    """Drop views derived from the current in-memory pack catalog."""
    global _SEARCH_INDEX_CACHE
    _CORPUS_CACHE.clear()
    _RUNTIME_PROFILE_CACHE.clear()
    _INDEXED_ENTRY_CACHE.clear()
    _ASSET_DETAIL_CACHE.clear()
    _SEARCH_INDEX_CACHE = None


def clear_runtime_caches() -> None:
    """Release every retrieval cache between independent suites."""
    global _PACK_CATALOG_CACHE
    _clear_derived_runtime_caches()
    _PACK_CATALOG_CACHE = None


def configure_pack_runtime(settings: PackSettings | None) -> None:
    """Select the explicit pack state used by this process and clear old views."""
    global _PACK_SETTINGS
    _PACK_SETTINGS = settings
    clear_runtime_caches()


@contextmanager
def using_pack_runtime(settings: PackSettings | None):
    """Use one explicit runtime for a bounded operation, then restore its caller."""
    previous = _PACK_SETTINGS
    configure_pack_runtime(settings)
    try:
        yield
    finally:
        configure_pack_runtime(previous)


def selected_pack_settings() -> PackSettings:
    """Expose the selected runtime paths without creating or changing activation."""
    from pack_manager import default_settings
    return _PACK_SETTINGS or default_settings()


def begin_catalog_request() -> RuntimePackCatalog:
    """Start one explicit freshness boundary for a command or service request.

    Pack discovery and cache freshness are evaluated once here. Every catalog,
    search-index, named-resource, and asset lookup performed during the request
    reuses that immutable runtime catalog. Long-lived callers must start a new
    boundary after pack state or pack contents may have changed.
    """
    clear_runtime_caches()
    return load_pack_catalog()


def reset_catalog_request() -> None:
    """Discard the current request snapshot without changing pack settings."""
    clear_runtime_caches()


def load_pack_catalog() -> RuntimePackCatalog:
    """Return the catalog snapshot for the current request boundary."""
    global _PACK_CATALOG_CACHE
    if _PACK_CATALOG_CACHE is None:
        _PACK_CATALOG_CACHE = load_runtime_catalog(_PACK_SETTINGS)
    return _PACK_CATALOG_CACHE


def require_active_catalog(catalog: RuntimePackCatalog | None = None) -> RuntimePackCatalog:
    """Fail with a pack-state diagnosis before attempting retrieval."""
    resolved = catalog or load_pack_catalog()
    if resolved.active_pack_count == 0:
        raise SystemExit(
            "No active content pack is available. Enable at least one discovered "
            "pack in explicit pack state, then start a new catalog request."
        )
    return resolved


def _lru_get(cache: OrderedDict[Any, Any], key: Any) -> Any | None:
    value = cache.pop(key, None)
    if value is not None:
        cache[key] = value
    return value


def _lru_put(cache: OrderedDict[Any, Any], key: Any, value: Any, limit: int) -> None:
    cache.pop(key, None)
    cache[key] = value
    while len(cache) > limit:
        cache.popitem(last=False)


def load_search_index() -> SearchIndex:
    global _SEARCH_INDEX_CACHE
    pack_catalog = load_pack_catalog()
    if _SEARCH_INDEX_CACHE is None:
        _SEARCH_INDEX_CACHE = SearchIndex(
            {
                "records": {
                    record_id: dict(profile)
                    for record_id, profile in pack_catalog.profiles.items()
                },
                "phrases": {
                    phrase: [dict(row) for row in rows]
                    for phrase, rows in pack_catalog.phrases.items()
                },
            }
        )
    return _SEARCH_INDEX_CACHE


def named_resource_path(name: str, *, required: bool = True) -> Path | None:
    resource = load_pack_catalog().resources.get(name)
    if resource is None:
        if required:
            raise SystemExit(f"Required named pack resource is unavailable: {name}")
        return None
    return resource.path


@dataclass(frozen=True)
class Entry:
    kind: str
    category: str | None
    record: dict[str, Any]
    source_pack: str
    source_root: Path
    source_file: str
    fingerprint: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        payload = json.dumps(
            {
                "kind": self.kind,
                "category": self.category,
                "record": self.record,
                "source_pack": self.source_pack,
                "source_root": str(self.source_root),
                "source_file": self.source_file,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        object.__setattr__(
            self, "fingerprint", hashlib.sha256(payload.encode("utf-8")).hexdigest()
        )


def runtime_profile(entry: Entry, search_index: SearchIndex | None = None) -> dict[str, Any]:
    """Return stored curated discovery metadata or a lightweight runtime view.

    Vocabulary records are intentionally not duplicated into the large stored
    profile table. Their label, aliases, outcome, and variant family are cheap
    to derive and cached for repeated regression and exploration calls.
    """
    index = search_index or load_search_index()
    rid = str(entry.record.get("id") or "")
    stored = profile_for(index, rid)
    if stored:
        return stored
    cache_key = (index.fingerprint, entry.fingerprint)
    cached = _lru_get(_RUNTIME_PROFILE_CACHE, cache_key)
    if cached is not None:
        return cached
    aliases = profile_aliases(index, rid)
    profile = {
        "kind": entry.kind,
        "category": entry.category,
        "tier": record_tier(entry.record),
        "discovery_group": infer_discovery_group(entry.kind, entry.record),
        "variant_of": infer_variant_of(entry.kind, entry.record),
        "outcome_summary": infer_outcome_summary(entry.kind, entry.record),
        "aliases": aliases,
        "variation_examples": [],
    }
    _lru_put(
        _RUNTIME_PROFILE_CACHE,
        cache_key,
        profile,
        _MAX_RUNTIME_PROFILE_CACHE,
    )
    return profile


def _entry_from_runtime(packed: RuntimePackEntry) -> Entry:
    return Entry(
        packed.kind,
        packed.category,
        dict(packed.record),
        packed.source_pack,
        packed.source_root,
        packed.source_file,
    )


def load_entries() -> list[Entry]:
    return [_entry_from_runtime(packed) for packed in load_pack_catalog().entries]
