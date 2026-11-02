# Catalog Cache Lifecycle

## Authority

Pack source files and `pack-state.json` are authoritative. The SQLite search cache and the enabled-runtime browser catalog are derived and disposable. It must never be edited as source data or distributed as the authored contents of a pack.

`pack-state.json` is the sole user-controlled activation state. It contains:

```json
{
  "pack_roots": [],
  "enabled_packs": ["01a0043b-2250-720d-87b7-f1e6fd7ed230"]
}
```

This is the complete shipped default state. The state file is the sole authority for pack activation. Tools that need isolation, including package validation, receive explicit state and cache locations. When only one of those locations is supplied programmatically, the other is derived beside it.

## Why the cache exists

Pack content may be large and may change independently of core. Parsing every record, rebuilding every lexical association, and rechecking every relationship at the start of every prompt request would make normal skill use unpredictable.

The cache stores normalized enabled-pack records, lexical phrases, curated search profiles, pack ownership and source locations, dependencies, canonical-record-to-asset relationships, the named resources of every active pack, resource paths, and diagnostics. SQLite provides transactional updates and indexed lookup. Search uses the deterministic phrase and profile indexes that runtime queries actually consume; the cache does not build an unused FTS table.

Every authored `search_terms` row retains its phrase, facet, weight, and source as an independent cache row. Label, tag, and profile-alias associations are generated only when the same normalized `(record_id, phrase, facet)` association is not already authored. Generated rows are deduplicated by that association key; authored rows are never collapsed by source.

## Freshness snapshot

Every catalog request boundary selects one content fingerprint before using the search cache. It covers:

- enabled pack UUIDs and explicit `pack_order`;
- resolved roots of available enabled packs;
- SHA-256 of every pack file, including its manifest and lock when present;
- discovery diagnostics, including missing enabled packs;
- the cache builder and the modules and schemas that determine its contents.

Additions, changes and deletions therefore affect freshness through actual bytes. File timestamps and sizes do not substitute for content. A release label is already covered by its manifest bytes; a product version alone does not invalidate the cache.

`refresh_runtime_catalog` selects and hydrates the same immutable cache once. A caller publishing a derived view receives that exact resolved catalog instead of rediscovering packs or constructing an inspection cache.

## Rebuild triggers

Managed operations rebuild immediately after success:

- root registration changes that affect enabled packs
- enable or disable
- install or enabled-pack update
- remove after state no longer enables the pack

Pack source files are edited with ordinary authoring tools, outside `pack_cli.py`. Those out-of-band edits rebuild lazily on the next catalog use:

- a record or resource is added
- a record or resource changes
- a record or resource is deleted
- an enabled pack directory disappears or returns
- a manifest or lock changes

If the fingerprint is unchanged, the existing cache is used immediately. The agent does not regenerate the full cache on every skill invocation.

## Deletion behavior

Deletion must never leave searchable ghost content.

- Deleting one development-pack record removes that record on the next rebuild.
- Deleting an asset removes both its record row and every reverse-index link to it on the next rebuild.
- Deleting a locked file invalidates the pack, so all records from that pack are excluded until the lock and content agree again.
- Deleting an enabled pack directory marks the UUID unavailable, rebuilds without its records, and retains a diagnostic in state-derived status.
- Removing a managed pack requires it to be disabled and moves it to quarantine.

Detected source deletion immediately invalidates the last successful cache and requires rebuilding against the current enabled packs.

## Failure isolation

One invalid pack does not make every valid pack unusable. Rebuild performs full validation, excludes the invalid pack, removes dependents whose required dependency is unavailable, and builds the cache from the remaining valid set.

Canonical record-ID conflicts are not resolved by root order. Conflicted records are excluded unless one exact pack-to-pack replacement direction is declared.

Each named resource resolves to the file of the highest-ranked active pack that binds it, as [Pack Format Specification](pack-format-specification.md) states. Two packs that no rank orders and that bind one name with different files exclude that resource and produce one diagnostic naming both packs. Runtime policy and evidence resolution never use pack-root order as precedence.

## Atomic construction

A writer holds the cache's operating-system lock while constructing one new fingerprint-named SQLite file. It commits the data, checks database integrity, closes the file and publishes it whole. Published caches are immutable, so an open reader does not block a subsequent generation. A cache removed between selection and opening is selected again from current inputs; readers close their handles explicitly.

## Browser projection

`ready` and successful public pack-changing operations maintain the browser projection using their already loaded runtime. Lock publication, installation, update and removal update the display only when state has already been selected; an absent state remains absent, and the operation reports an unselected browser view. Its output is `CACHE/browser-catalog/CONTEXT/`, where the context hashes the selected state-file path, explicit discovery-root selection and managed root. Independent runtimes sharing a search-cache directory cannot overwrite each other's browser view.

The browser manifest records the resolved source fingerprint, renderer fingerprint, display settings and generated-file inventory. Matching inputs and complete files reuse the site without writes; changed inputs or missing pages trigger one transactional directory replacement. The site shows resolved active records, retains declared evidence links and uses pack-owned thumbnails. It does not copy the source corpus or write into a pack.

An empty active set publishes an empty current site. Invalid packs are omitted with their runtime diagnostics. A rendering or output failure marks the managed landing page unavailable and reports a display warning; it does not undo activation, alter authored data or become an additional readiness gate. A later readiness or maintenance boundary retries the view. Ordinary search requests, image operations and SessionStart do not rebuild the HTML site.

Explicit `catalog_html.py --pack-tree` exports and full-release catalogs retain their separately selected inspection or distribution scope. See [Catalog export](maintenance/catalog-export.md).

## Status and repair

```bash
python scripts/pack_cli.py cache-status
python scripts/pack_cli.py cache-refresh
python scripts/pack_cli.py cache-refresh --force
```

`cache-status` compares source and cached fingerprints without rebuilding and reports the managed browser view's freshness and entry point. `cache-refresh` rebuilds only when stale and maintains the browser view from the resulting catalog. `--force` performs a complete cache reconstruction from the enabled state.

Deleting the cache is safe, but normal users should prefer `cache-refresh --force` so locking and validation remain active.
