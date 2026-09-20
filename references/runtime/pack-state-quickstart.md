# Pack State Runtime Quickstart

When routed here because no explicit or persistent state exists, this document is the mandatory initialization path before any catalog retrieval or generation. An extracted Skill directory is not an initialized runtime; discovered pack files remain inactive until the resolved state enables them.

Use this document only when a runtime state must be selected, a non-bundled pack must be activated, or a logical-resource provider must be chosen. For pack authoring, installation, locking, update, removal, or quarantine, read [Pack Maintenance](../maintenance/packs.md).

## Choose one pack runtime

`pack-state.json` is the complete activation authority. It governs discovery roots, enabled UUIDs, and logical-resource providers. Providers are never implicit, and enabling a pack does not change existing selections.

State resolution is deterministic:

1. An explicit `--state-file` path is the complete authority for that invocation.
2. Without `--state-file`, commands use the persistent user state at `~/.character-prompt-builder/pack-state.json` under the user home directory on every platform. The flag-free cache defaults to `cache/` beside it, and a mutating command persists its result there. Runtime state never lives inside the Skill directory, so packs and activation survive Skill updates.
3. While the selected state file does not exist, `config/pack-initialization.json` enables all valid discovered packs, including additional shipped packs, on top of the minimal `config/default-pack-state.json` core-release seed. Existing selected providers are preserved; an additional logical resource is selected only when exactly one provider exists. Conflicting providers remain unresolved and visible. Discovery errors stop initialization rather than hiding a broken pack.

Once a state file exists it is complete: initialization never re-enables a deliberately disabled pack or overwrites explicit provider choices. An explicit empty state stays empty subject to the existing protected-core policy.

Run `python scripts/pack_cli.py state-init` once to persist the resolved state file and report every discovered pack with its enabled status. At the first pack-facing step of a session without an explicit state, surface `disabled_discovered_packs` to the user instead of silently continuing with a smaller enabled set.

`python scripts/session_entry_points.py` answers the cheap half of that at session start, from the state file alone: whether the persistent runtime exists, how many packs it enables, and how many roots and providers it carries. It is what a plugin host runs on `SessionStart`. It does not answer `disabled_discovered_packs`, because that needs discovery, and discovery reads every record in every root: on the bundled commons pack that is about twenty seconds, with or without lock verification. The hook reports the question as unsettled rather than spending it in every session that never touches a pack.

Choose capabilities before retrieval. A core-only installation supplies generic direction; a full source installation initially enables all discovered packs, but capabilities still come from validated active manifests rather than promises based on filenames. Existing evidence-artifact prompt packages require enabled `searchable-assets` and `evidence-artifact-reference`; derived evidence also requires `visual-evidence`, and reusable authored identity requires `character-archetypes`. If none is discovered, stop on that prerequisite rather than fabricate references.

For isolation, use task-local state, cache, managed root, and unchanged additional roots throughout.

## Enable packs and select providers

Use one explicit prefix for every command; global options precede the subcommand:

```bash
python scripts/pack_cli.py \
  --state-file TASK_PACK_STATE_JSON \
  --cache-dir TASK_CATALOG_CACHE \
  --managed-root TASK_MANAGED_PACKS \
  root-add PACK_OR_CONTAINER
```

Replace the final `root-add` line with one needed subcommand. `list` exposes UUIDs and capabilities; `inspect` exposes a manifest and validation. Select by capability, not name.

```bash
list
inspect <pack-uuid>
enable <pack-uuid>
provider-list
provider-select <logical-name> <pack-uuid>
resources
resource <logical-name>
```

For the bundled commons pack context, retrieve the selected negative-policy resource directly with:

```bash
python scripts/pack_cli.py resource negative-policy
```

Enable dependencies first. `provider-clear` leaves a resource unresolved; disabling its pack or removing its root never selects a replacement. Unselected resources remain excluded with a warning. Requesting one without a selected available provider still fails.

Finish activation before retrieval. After any pack or provider change, discard earlier results and restart; never mix authority snapshots.

## Cache freshness

Catalog commands reuse a derived SQLite cache until state or enabled-pack inventory changes; edits, additions, deletions, disabled packs, and missing packs invalidate it at the next boundary. Do not refresh per invocation. Use `cache-status` for diagnosis and `cache-refresh` only for maintenance or recovery. Cache data is never canonical or distributable.

## Use one context everywhere

Place invocation context before the catalog subcommand:

```bash
python scripts/catalog_cli.py \
  --state-file PACK_STATE_JSON \
  --cache-dir CATALOG_CACHE \
  --managed-root MANAGED_PACKS \
  --pack-root ADDITIONAL_PACK_ROOT \
  search "coherent craft question"
```

Repeat `--pack-root` for each additional root and pass identical context through retrieval, inspection, asset lookup, planning, state, materialization, Generation Package, and verification. Invocation options isolate a run. On first initialization, all valid packs found through those roots are enabled. Once the selected state exists, adding a root only discovers a pack; enable its UUID explicitly and choose required providers.

## Batched complete inspection

After one search `batch`, read the selected canonical records and their linked asset details in one request:

```bash
python scripts/catalog_cli.py inspect-many <record-id-1> <record-id-2> --out inspected.json
```

The same runtime selectors precede the subcommand. This returns complete records (not summaries), complete assets, source provenance, one runtime fingerprint, diagnostics and elapsed timings. The maximum is 256 distinct IDs; an unknown ID fails the entire request rather than publishing partial success. Inspect the returned contents and record adoption/rejection as usual. Reuse that snapshot only within its request; state or content changes invalidate derived caches at the next boundary. Run `python scripts/feature_workflow_smoke_test.py` for the bulk contract and `catalog_cli_runtime_smoke_test.py` for cache freshness.
