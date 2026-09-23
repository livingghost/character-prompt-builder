# Pack State Runtime Quickstart

Run `python scripts/pack_cli.py ready` before any catalog retrieval or generation, with the task's runtime selectors when it has them. It creates the state on first use, keeps every existing choice, and prints the packs retrieval will use. Exit 1 means a `decide:` line needs the author. For pack authoring, installation, locking, update, removal, or quarantine, read [Pack Maintenance](../maintenance/packs.md).

A synthetic fixture after the author left out two packs, trimmed, with runtime paths shortened to `S`, `C` and `M`:

```text
ready: retrieval can use 1 pack(s)
warning: pack broken-shelf is invalid (lock-extra-files: files not in pack.lock.json); remove the extra files or disable it: python scripts/pack_cli.py --state-file S --cache-dir C --managed-root M disable 01a0cb9d-1add-7b73-b012-1bc279dab959
left out: spare-shelf 01a0cb9d-1ac3-7f2a-beac-af4b6d1362e2 (disabled)
```

## Choose one pack runtime

`pack-state.json` is the complete activation authority. It governs discovery roots, enabled UUIDs, the packs the author disabled, and logical-resource providers. Providers are never implicit, and enabling a pack does not change existing selections.

State resolution is deterministic:

1. An explicit `--state-file` path is the complete authority for that invocation.
2. Without `--state-file`, commands use the persistent user state at `~/.character-prompt-builder/pack-state.json` on every platform, with the cache in `cache/` and personal or installed packs in `packs/` beside it; an explicit state file has the same neighbors. Runtime state never lives inside the Skill directory, so those packs and activation survive Skill updates.
3. While the selected state file does not exist, `config/pack-initialization.json` enables every discovered pack on top of the minimal `config/default-pack-state.json` seed; `ready --only PACK_ID`, repeated for each pack, enables exactly the named packs instead and reads nothing of the others but `pack.json`. A logical resource with exactly one provider gets that provider; competing providers stay unselected.

Once a state file exists it is complete: nothing re-enables a pack the author disabled or overwrites a provider choice. `disable`, `ready --without` and `ready --only` record that decision in `disabled_packs`, and `enable` clears it; `ready` asks only about a discovered pack in neither list.

A pack the catalog cannot use is left out: an invalid pack, a missing one, one whose required pack is not in use, an unreadable `pack.json`, or one pack ID in two roots. Every command that reads the catalog names it once, in the `warning:` line shown above.

Choose capabilities before retrieval. A core-only installation supplies generic direction; a full source installation initially enables all discovered packs, but capabilities still come from validated active manifests rather than promises based on filenames. Existing evidence-artifact prompt packages require enabled `searchable-assets` and `evidence-artifact-reference`; derived evidence also requires `visual-evidence`, and reusable authored identity requires `character-archetypes`. If none is discovered, stop on that prerequisite rather than fabricate references.

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

Enable dependencies first. `provider-clear` leaves a resource unresolved. Disabling or removing a pack clears the provider choices it owned, lists them in `cleared_providers`, and never selects a replacement. Unselected resources remain excluded with a warning. Requesting one without a selected available provider still fails.

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
