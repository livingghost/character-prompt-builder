# Pack Maintenance

Use this document for pack creation, registration, activation changes, installation, update, removal, locking, conflict diagnosis, or catalog export. For ordinary runtime activation only, use [Pack State Runtime Quickstart](../runtime/pack-state-quickstart.md).

## Contents

- [Identity and contents](#identity-and-contents)
- [Core-interpreted resource contracts](#core-interpreted-resource-contracts)
- [Development and locking](#development-and-locking)
- [Discovery roots and state changes](#discovery-roots-and-state-changes)
- [Install, update, remove, and quarantine](#install-update-remove-and-quarantine)
- [Cache and catalog operations](#cache-and-catalog-operations)
- [Conflict rules](#conflict-rules)
- [Ownership and distribution](#ownership-and-distribution)
- [Command index](#command-index)
- [First-use activation and bundled integrity](#first-use-activation-and-bundled-integrity)

## Identity and contents

A content pack distributes searchable production knowledge and its supporting resources. Core code, shared schemas, and generic runtime templates are not optional pack content.

Before changing manifest, record/resource boundaries, locks, active-set resolution, installation, or update semantics, read the complete [Pack Format Specification](../pack-format-specification.md).

Every pack has:

- `pack_id`: generated UUIDv7, stable across rename, move, and update;
- `release`: independent UTC CalVer in `YYYY.MM.DD.N`.

The current schema is the complete contract, and dependencies name one pack by UUID rather than one of its releases. Author only fields defined by that schema.

```text
<pack>/
  pack.json
  pack.lock.json
  README.md
  LICENSE
  records/*.json
  resources/**
```

`pack.lock.json` is required for installed or released external packs. The actual bundled `packs/commons` is core-managed and lockless; copying its UUID elsewhere does not grant this exemption. `README.md` and license text are optional; `pack.json` remains authoritative for license identity. Manifest `record_globs` and `resource_globs` must not overlap, and resources may not capture `records/`, `pack.json`, or `pack.lock.json`.

An `asset` is a searchable record, not a loose file. Its `primary_resource` identifies the main source; its nonempty `resource_refs` contains that path and may add views, semantic maps, audits, or evidence JSON. The catalog derives the reverse link from canonical records to complete assets while preserving pack UUID, release, root, and source record path.

`content.resource_bindings` assigns stable logical resource names such as `negative-policy`, `pack-defaults`, or `reference-corpus-manifest`. Each name resolves to the file of the highest-ranked enabled pack that binds it, as [Pack Format Specification](../pack-format-specification.md) states.

## Core-interpreted resource contracts

Most named resources are opaque to core pack validation. Three logical names are interpreted directly by core workflows and therefore have semantic contracts that hold in every pack that binds them:

- `pack-defaults` enables one medium family by default and permits a hybrid only after an explicit request: `medium_policy.single_medium_family_by_default` and `medium_policy.hybrid_requires_explicit_request` are both `true`.
- `negative-policy` makes semantic exclusions user-request-only. Its `scene_failure_modes` and `atomic_misreadings` sources remain diagnostic-only with `automatic_emission: false`.
- `discovery-lanes` keeps every `preferred_scene_ids` target resolvable in the active canonical record set. Missing targets exclude the resource and produce a diagnostic instead of being silently skipped.

These contracts apply to the bundled commons pack and to any other pack that binds one of the logical names. `pack_cli.py validate` and lock construction reject a bound known resource that violates its contract. `audit_preset_quality.py` also validates the resources of the enabled packs.

## Development and locking

Create a personal pack in the packs folder beside the state:

```bash
python scripts/pack_cli.py init ~/.character-prompt-builder/packs/my-pack --name "My Pack"
```

`init` generates the UUIDv7, registers the location when no pack root holds it, and enables the pack. Add normalized records and resources, then declare capabilities, globs, and logical bindings; the next catalog command uses them. A pack without `pack.lock.json` is a development pack that may be empty. The runtime validates it at every catalog build, and `ready` and every catalog command name a problem in one line.

Production preparation uses a development pack like a locked one. The prepared run keeps the bytes it read. An edit to a record or resource the run uses stops that run's execution. An edit elsewhere in the pack leaves the run usable. A synthetic run after its model record was edited, trimmed:

```json
{
  "code": "PACK_CONTENT_MISMATCH",
  "severity": "error",
  "phase": "runtime-freshness",
  "message": "Current source bytes differ from the fixed execution resource.",
  "required_action": "Restore the pinned content, or retarget from this run to adopt the edited pack content.",
  "pack": "019a0290-1234-789a-8123-0123456789ab",
  "resource": "records/models.json",
  "expected": "68090f5383af9a6b...",
  "actual": "12225c76355c5f36...",
  "affected_runs": ["01a10263-2df5-748c-bc85-242e97cdd707"],
  "actions": [{"operation": "restore", "command": null}, {"operation": "retarget", "command": "python scripts/production_workflow.py retarget --root STUDIO --from RUN ..."}]
}
```

Build a lock only to publish a release or to install the pack elsewhere; `install` requires one:

```bash
python scripts/pack_cli.py build-lock --directory ~/.character-prompt-builder/packs/my-pack
python scripts/pack_cli.py validate --directory ~/.character-prompt-builder/packs/my-pack --released
```

The lock records every pack file except itself with relative path, size, media type, role, and SHA-256. Any change to a locked file invalidates the pack, so a pack still being edited stays unlocked. Advance the pack's own CalVer, rebuild the lock, and publish the complete new release. Never publish different bytes under the same pack UUID and release.

Run exact one-pack publication checks through [Release Validation](../release/validation.md).

## Discovery roots and state changes

The Skill's `packs/` directory and the packs folder beside the state are always discovered; registering either as well changes nothing. `packs/commons/` is the single Git-tracked shipped pack. Other immediate children are personal packs and are ignored by the core repository by default.

A registered path can be an exact directory containing `pack.json` or a container whose immediate children are pack roots. Use an exact root for isolation and a container for siblings.

```bash
python scripts/pack_cli.py ready
python scripts/pack_cli.py root-add PACK_OR_CONTAINER
python scripts/pack_cli.py list
python scripts/pack_cli.py root-remove PACK_OR_CONTAINER
python scripts/pack_cli.py enable <pack-uuid>
python scripts/pack_cli.py disable <pack-uuid>
```

Without `--state-file`, these commands read and persist the state in the configuration directory described in [Pack State Runtime Quickstart](../runtime/pack-state-quickstart.md). `ready` persists that resolved state file when absent, never rewrites an existing one, and prints the packs in use and each decision the author owes.

Required dependencies must be enabled before activation. Disable dependents first or use the explicit cascade behavior. `root-remove` refuses to orphan an enabled pack. Deleting an enabled directory makes it unavailable immediately and produces a state diagnostic until corrected.

## Install, update, remove, and quarantine

```bash
python scripts/pack_cli.py install my-pack.zip
python scripts/pack_cli.py update my-pack-new-release.zip
python scripts/pack_cli.py disable <pack-uuid>
python scripts/pack_cli.py remove <pack-uuid>
```

Install and update validate manifest, lock, paths, dependency declarations, record IDs, media, and hashes before changing the managed root. A fresh install may remain disabled while dependencies are unavailable; activation still enforces the complete dependency graph.

ZIP handling rejects malformed or unreadable archives, absolute and traversing paths, symbolic links, duplicate member paths, and file-directory collisions. These are structured operation failures. The pack layer does not impose a project-specific archive-size or member-count ceiling; general archive and filesystem behavior remains outside this content-management contract.

The default managed root is the `packs` folder beside the state, which is `packs/` in the configuration directory for the persistent state; `--managed-root` selects an explicit alternative. Managed directories are `<managed-root>/<pack-uuid>/`. Update requires the same UUID and a strictly newer CalVer, then replaces the directory atomically. Retain the prior release in recoverable quarantine at `<managed-root>/.quarantine/` on the same filesystem.

Remove accepts only lowercase UUIDv7, applies only to a disabled managed pack, and moves the exact UUID directory into quarantine. It remains recoverable even when the installed manifest is missing or corrupt.

## Cache and catalog operations

The catalog cache is derived. State and file inventories determine freshness, direct edits are detected at the next boundary, and managed mutations refresh immediately.

```bash
python scripts/pack_cli.py cache-status
python scripts/pack_cli.py cache-refresh
```

Do not distribute the cache as authored content. See [Catalog Cache Lifecycle](../catalog-cache-lifecycle.md) for locking, invalidation, failure isolation, and deletion behavior.

Use `inspect` for the complete canonical record plus compact asset activation summary. Use `asset-lookup --summary` for asset IDs and technical roles. Use full `asset-lookup` only when reference planning requires complete artifact paths, roles, media, hashes, and ownership. Reference activation and transport belong to [Prompt Artifact Reference Runtime](../runtime/reference-prompt-artifacts.md) and [Image Generation Runtime](../runtime/image-generation.md), not pack lifecycle.

Export a visual catalog from an explicit pack tree:

```bash
python scripts/catalog_html.py \
  --pack-tree packs \
  --released \
  --output catalog
```

`--pack-tree` recursively discovers every `pack.json` below the named tree, validates each pack, and orders them deterministically. A later third-party or owner-authored pack placed beneath `packs/` is therefore included without editing the command or exporter. Use repeated `--pack` only for a deliberately fixed subset, or use `--state` / `--settings` when activation state rather than the filesystem tree should define scope.

Open `catalog/index.html`. The direct-open page is script-free and links to a static visual-evidence gallery, a linked-record gallery, record-kind browsing, pack summaries, and the separate interactive `search.html`. Complete records live on individual pages. `data/record-asset-map.json` contains both canonical-record-to-asset and asset-to-canonical-record mappings. Linked Visual Evidence is shown as a preview thumbnail on the relevant gallery, search result, record page, and evidence page. The output stays outside every inspected pack and does not rank, rewrite, merge, or summarize source records. Use `--copy-assets` only when the catalog must move independently of its packs. See [Catalog Export](catalog-export.md).

## Conflict rules

Canonical record IDs must be unique across the enabled set. Resolution compares the complete candidate set without state or discovery order. One candidate wins only when it explicitly replaces that ID from every other declaring pack and none of those replaces the prospective winner. Otherwise exclude the ID and report a conflict. There is no implicit last-writer-wins rule.

Admit an asset with `canonical_record_ids` only when every referenced record exists after dependencies and replacements resolve. Missing references produce diagnostics and exclude the asset.

Pack UUIDs are unique across all roots. Multiple enabled packs may bind one logical resource; the highest-ranked of them supplies it, as [Pack Format Specification](../pack-format-specification.md) states.

## Ownership and distribution

A storage location is not a pack taxonomy. Moving a pack between roots does not make it default, user-owned, third-party, local, or cloud. Identity, release, authorship, policy, and explicit distribution choice define its role.

The bundled commons pack is separately authored and minimal. It is not a rename, summary, automatic subset, or replacement of another pack. Expanding it is an explicit content-authoring decision and does not move or delete the source record from its owner pack.

Every other pack is a personal pack. Its author creates it and manages its lifecycle independently. A personal pack is a normal pack: full-package construction and catalog export preserve and validate it, and first use enables it without making its records core-release catalog dependencies.

Core documentation, runtime defaults and regression expectations never depend on what a personal pack holds:

- its record IDs and aliases;
- its model inventory and counts;
- its search results and evaluation history.

The product's tests and release checks create commons-only states with `ready --only`. A test that needs other content creates a synthetic pack in a temporary directory. This boundary protects ownership without deleting, moving, renaming, or excluding a personal pack.

Keep each non-bundled pack's atomic modules, policies, records, assets, and evidence in the release unit declared by that pack. Do not split pack-owned scene knowledge or visual evidence into undeclared subpacks.

Third parties may add packs with independent UUIDv7, CalVer, lock, license, provenance, records, and resources. They are not defaults or core distribution unless an explicit policy says so. Activation is an explicit user choice.

Cache generation, inspection, export, copying, and distribution preserve records and resources one-to-one. They never summarize, compress, deduplicate, split, or merge pack content. Semantic consolidation is a separate reviewed authoring operation with lossless field union and explicit reference remapping.

## Command index

```text
pack_cli.py init, validate, build-lock
pack_cli.py ready
pack_cli.py root-add, root-remove, list
pack_cli.py enable, disable
pack_cli.py install, update, remove
pack_cli.py cache-status, cache-refresh
pack_cli.py resources, resource
```

`validate` and `build-lock` act on one pack:

- `--pack PACK_ID_OR_UNIQUE_NAME` selects a discovered pack by UUID or by its unique `name`.
- `--directory PACK_DIRECTORY` selects the absolute directory holding `pack.json`. A leading `~` names the home directory, and a relative path is refused.

`validate` returns the manifest, the validation report and, for `--pack`, the discovery issues. A name is matched only against discovered manifests, never against a directory in the current folder. A name that several packs share stops the command and lists them. A synthetic case, trimmed:

```json
{
  "ok": false,
  "diagnostics": [{
    "code": "PACK_NAME_AMBIGUOUS",
    "phase": "pack-selection",
    "message": "Pack name 'Minimal Example Pack' is not unique.",
    "required_action": "Select one of the candidates with --pack PACK_ID.",
    "candidates": [
      {"pack_id": "0198b4e8-7c00-7a31-8c5a-2a6d9f18e4b7", "name": "Minimal Example Pack", "root": "...\\managed\\alpha"},
      {"pack_id": "01a10263-479b-7a1b-9bfe-412dc0308741", "name": "Minimal Example Pack", "root": "...\\managed\\beta"}
    ]
  }]
}
```

`ready` prints plain lines and exits 1 while the author owes a decision. The other commands report JSON and exit 2 on failure, with every failure in the `diagnostics` form shown above. Runtime options such as `--state-file` and repeated `--pack-root` go before the subcommand. An extra root applies to that invocation only. `scripts/pack_selector_smoke_test.py` exercises pack selection.

## First-use activation and bundled integrity

`config/pack-initialization.json` enables all discovered packs only while the selected state file is absent. `ready` persists that result. Existing explicit state is never overwritten: deliberately disabled packs remain disabled. `config/default-pack-state.json` remains the minimal core-release catalog seed, not a restriction on first-use activation of additional supplied packs.

The actual bundled `packs/commons` directory with the commons UUID is core-managed. It has no `pack.lock.json`; core source inventory and `MANIFEST.json` commit it together with the project, and pack validation still checks its schema and files. `build-lock` and pack release-lock creation refuse that directory rather than recreating an unnecessary lock. The exemption is path-bound, not a manifest flag: a copy of commons and every other pack still need a lock to be released or installed. The release gate reports a live core inventory for commons, not a nonexistent lock. Do not remove or weaken any external pack's lock.

For the actual commons directory, `pack_release_gate.py` reports `scope: core-managed-pack-structure` and `release_authorized: false` after live-inventory and cache checks. This is not a standalone core release pass: `scripts/run_checks.py` runs the regression suites, and `scripts/validate.py` and the project packager check the tree and the release. The separate pack evaluation contract remains mandatory for external packs that declare evaluation resources.
