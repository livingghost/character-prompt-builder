# Catalog Cache Lifecycle

## Authority

Pack source files and `pack-state.json` are authoritative. The SQLite catalog cache is derived and disposable. It must never be edited as source data or distributed as the authored contents of a pack.

`pack-state.json` is the sole user-controlled activation state. It contains:

```json
{
  "pack_roots": [],
  "enabled_packs": ["01a0043b-2250-720d-87b7-f1e6fd7ed230"],
  "resource_providers": {
    "archetype-policy": "01a0043b-2250-720d-87b7-f1e6fd7ed230",
    "discovery-lanes": "01a0043b-2250-720d-87b7-f1e6fd7ed230",
    "negative-policy": "01a0043b-2250-720d-87b7-f1e6fd7ed230",
    "project-defaults": "01a0043b-2250-720d-87b7-f1e6fd7ed230"
  }
}
```

This is the complete shipped default state. The state file is the sole authority for pack activation and resource-provider selection. Tools that need isolation, including package validation, receive explicit state and cache locations. When only one of those locations is supplied programmatically, the other is derived beside it.

## Why the cache exists

Pack content may be large and may change independently of core. Parsing every record, rebuilding every lexical association, and rechecking every relationship at the start of every prompt request would make normal skill use unpredictable.

The cache stores normalized enabled-pack records, lexical phrases, curated search profiles, pack ownership and source locations, dependencies, canonical-record-to-asset relationships, explicitly selected named resource bindings, resource paths, and diagnostics. SQLite provides transactional updates and indexed lookup. Search uses the deterministic phrase and profile indexes that runtime queries actually consume; the cache does not build an unused FTS table.

Every authored `search_terms` row retains its phrase, facet, weight, and source as an independent cache row. Label, tag, and profile-alias associations are generated only when the same normalized `(record_id, phrase, facet)` association is not already authored. Generated rows are deduplicated by that association key; authored rows are never collapsed by source.

## Freshness snapshot

Every catalog entry point performs a lightweight comparison before using the cache. The source fingerprint covers:

- core release
- enabled pack UUIDs from state
- logical-resource provider selections from state
- resolved root of each available enabled pack
- available enabled packs and releases
- SHA-256 of each `pack.json`
- SHA-256 of each available `pack.lock.json`
- relative path, byte size, and nanosecond modification time for every pack file
- discovery diagnostics, including missing enabled packs
- hashes of the cache builder, `pack_manager.py`, `search_discovery.py`, `state_protocol.py`, and current pack schemas

The tree inventory detects additions and deletions. Size and modification time identify files that require full validation during a rebuild. Manifest and lock hashes are always included. A released pack's lock supplies the authoritative content hashes.

## Rebuild triggers

Managed operations rebuild immediately after success:

- root registration changes that affect enabled packs
- enable or disable
- resource-provider select or clear
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

Named resources are admitted only from the UUID selected in `resource_providers`. Multiple candidate packs may expose the same name, but no candidate is chosen implicitly. A missing selection or unavailable selected provider leaves the resource unresolved and produces a diagnostic. Runtime policy and evidence resolution never use pack-root order as precedence.

## Atomic construction

One process obtains a cache lock. Other processes wait briefly for the same result instead of starting duplicate rebuilds. A well-formed lock is recovered only when its recorded owner process no longer exists; elapsed time alone never steals a legitimate long rebuild. A malformed lock is allowed one lock-timeout interval to finish being written, then is treated as ownerless and recovered. A live, well-formed owner always wins over elapsed time.

The writer creates a separate SQLite file, commits all records and indexes, runs an integrity check, closes every database handle, and then atomically replaces the current cache. A failed temporary build never replaces the current file.

Windows requires every reader connection to close before replacement. Runtime loaders therefore close SQLite handles explicitly rather than relying on garbage collection.

## Status and repair

```bash
python scripts/pack_cli.py cache-status
python scripts/pack_cli.py cache-refresh
python scripts/pack_cli.py cache-refresh --force
```

`cache-status` compares source and cached fingerprints without rebuilding. `cache-refresh` rebuilds only when stale. `--force` performs a complete cache reconstruction from the enabled state.

Deleting the cache is safe, but normal users should prefer `cache-refresh --force` so locking and validation remain active.
