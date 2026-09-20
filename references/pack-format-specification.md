# Pack Format Specification

## Purpose

A content pack is an independently released, UUID-identified collection of searchable records and supporting resources. It is the only extensibility and distribution unit for catalog content.

A pack is valid only when it satisfies the current schemas and semantic checks in this specification.

## Directory boundary

The directory containing `pack.json` is the pack root. Every declared or locked path must remain below that root. Absolute paths, parent traversal, backslash archive paths, and symbolic links are forbidden.

```text
<pack-root>/
  pack.json
  pack.lock.json              # required for external released or installed packs; omitted for core commons
  README.md                   # optional
  LICENSE                     # optional; license identity is declared in pack.json
  records/
  resources/
```

The directory name is not identity and may change. `pack_id` is identity.

## Manifest

`pack.json` is authored and validated with [pack.schema.json](../schemas/pack.schema.json).

```json
{
  "pack_id": "0198b4e8-7c00-7a31-8c5a-2a6d9f18e4b7",
  "name": "Example Pack",
  "description": "Optional human-facing description.",
  "release": "2026.08.15.1",
  "content": {
    "record_globs": ["records/**/*.json"],
    "resource_globs": ["resources/**/*"],
    "resource_bindings": {
      "reference-corpus-manifest": "resources/reference-corpus/manifest.json"
    }
  },
  "capabilities": ["cranial-hair", "visual-evidence"],
  "dependencies": [],
  "optional_dependencies": [],
  "replaces": [],
  "license": "GPL-3.0-only"
}
```

### `pack_id`

`pack_id` is a lowercase RFC 9562 UUIDv7 generated once by `pack_cli.py init`. It remains stable across renames, release updates, content additions, and directory moves. It is never derived from a name, path, author, or content hash.

### `release`

`release` is the pack's independent UTC CalVer in `YYYY.MM.DD.N` form. `N` starts at `1` for the first release on one UTC date and increments for another release on that date.

A released UUID and CalVer pair is immutable. Any content change requires a new release. Direct validation against the current manifest and record schemas is authoritative; a schema or semantic validation failure is an error.

### `content`

`record_globs` select JSON files below `records/`. `resource_globs` select non-record content such as SVGs, evidence bundles, thumbnails, lookup data, and pack-specific supporting documents. A resource glob may not select any file below `records/`, `pack.json`, or `pack.lock.json`. `resource_bindings` maps stable lowercase logical names to exact files selected by `resource_globs`.

Globs and binding targets use forward-slash relative paths. They may not escape the pack root. At least one record or resource glob must be declared. Every binding target must exist and be covered by a resource glob. A mutable unlocked development pack may have no matched record or resource content and receives a warning. A released or locked pack with neither a matched record nor a matched resource is invalid.

### Dependencies

Required and optional dependencies contain a source `pack_id` and nothing else. A dependency names a pack, not a version: a required dependency must be installed and enabled before the dependent pack can enter the active catalog, and the dependency's release is not an input to that resolution.

Dependency pack IDs are unique within one manifest. Self-dependency is forbidden. Required dependency cycles are invalid.

### Replacements

`replaces` contains exact pairs of `record_id` and source pack UUID. It is the only supported way to resolve the same canonical record ID across packs. Resolution evaluates the complete enabled candidate set for an ID without using state or discovery order. One candidate wins only when it explicitly replaces that ID from every other declaring pack and none of those candidates replaces the prospective winner. Otherwise the ID is excluded and reported as a conflict.

Every pack uses its manifest UUIDv7 identity, and root discovery order does not define precedence.

### License and provenance

Every pack manifest declares `license`, a license identifier or rights statement. The manifest has no provenance field: the account of where content came from lives in pack-owned notices such as `README.md`, in pack-owned resources, or in the provenance fields of individual records. Resource-level provenance may be more detailed, but it cannot contradict the pack's license declaration.

## Record files

Record containers are validated with [pack-record-file.schema.json](../schemas/pack-record-file.schema.json).

```json
{
  "kind": "module",
  "category": "lighting",
  "records": [
    {
      "id": "soft-window-rim",
      "label": "soft window rim",
      "curation_status": "vocabulary",
      "category": "lighting",
      "prompt": "a soft window rim separating the subject from the background",
      "domains": ["shared"],
      "tags": ["window light", "soft rim"],
      "search_terms": [
        {
          "phrase": "soft window rim",
          "facet": "lighting",
          "weight": 1.0,
          "source": "author"
        }
      ]
    }
  ]
}
```

`kind` identifies the catalog role. Module files require `category`. Every record requires a canonical ID, and IDs must be unique within the pack and across the resolved enabled set.

Canonical retrieval fields are English. Source-language text may be retained only in explicit provenance or opaque source metadata fields.

### Asset records

`kind: "asset"` makes a resource set searchable. An asset uses the common record fields, including `id`, `label`, `curation_status`, `domains`, `search_terms`, and optional `search_profile`. Aliases and facets, when used, are nested inside `search_profile`. The complete asset-specific required field set is `category`, `asset_type`, `description`, `source_ref_id`, `source_sha256`, `source_media_type`, `source_dimensions`, `disposition`, `evidence_relation`, `canonical_record_ids`, `primary_resource`, `resource_refs`, `artifacts`, and `tags`.

Rights are declared by the pack manifest's `license`, and provenance is carried by pack-owned notices or supporting resources rather than by the manifest. They are not asset-record fields in the current schema. Artifact derivation, when applicable, is recorded by the referenced bundle or runtime-attachment artifact rather than by an undeclared top-level asset field.

- `primary_resource`: the main pack-relative SVG or other resource;
- `resource_refs`: one or more pack-relative resources, including `primary_resource`.

Every referenced path must be selected by `resource_globs`. Multiple asset records may be selected together, so one record can provide identity geometry while others provide pose, clothing, finish, or evidence views. Resource relationships are explicit; the runtime does not silently choose one global SVG.

Every `artifacts` row must name a declared `resource_refs` path. Its media type and SHA-256 must match the corresponding lock row in a released pack, or the actual resource in an unlocked development pack. Artifact IDs and paths are unique within the asset.

An asset with `asset_type: "visual-evidence-bundle"` names exactly one `visual-evidence-bundle.json` in `resource_refs`. The asset and bundle artifact sets must match exactly by `artifact_id`; role, bundle-relative path expanded to pack-relative form, media type, and SHA-256 must agree. Duplicated source identity, source hash and dimensions, canonical record IDs, disposition, and evidence relation must also agree. A lock inventory, bundle manifest, and asset record are not independent authorities that may drift.

## Resources

Resources are pack-owned files that are not direct catalog records. Examples include:

- SVG visual evidence
- evidence indexes and semantic-region maps
- reference-board source material
- thumbnails and previews
- pack-specific model or composition lookup data
- documentation required to interpret the pack

The lock inventories resources. Asset records describe searchable semantic roles, supported scopes, provenance, and relationships to canonical records. `resource_bindings` expose pack-owned policy or index files under stable logical names. Large resource contents are not copied into the lexical search database; searchable metadata, resource paths, and relationships are indexed instead.

Several enabled packs may expose the same logical resource name. The required `resource_providers` state object selects the provider pack UUID for each resource the runtime should resolve. Only that selected provider is eligible. Missing selections and unavailable, invalid, disabled, dependency-excluded, or UUID-conflicted providers leave the resource unresolved and produce diagnostics. Root order and last-writer-wins precedence are never used.

## Lock inventory

`pack.lock.json` is generated and validated with [pack-lock.schema.json](../schemas/pack-lock.schema.json). It contains:

- pack UUID and release
- every file except the lock itself
- relative path
- byte size
- SHA-256
- media type
- file role
- one hash of the canonical inventory

Installed and distributed external packs require a valid lock. An unlocked external directory is a development pack. The actual bundled commons directory is instead core-managed: omit its lock, validate its live files, and commit changes through the project inventory and MANIFEST.json. The path-bound exception never applies to external copies.
Each relative path occurs exactly once in `files`; two rows with the same path are invalid even when another field differs.

## Active-set resolution

Pack discovery reads the project `packs/` directory, the managed installation root, and every discovery path registered in explicit pack state. A registered discovery path may be one exact pack root containing `pack.json` or a container whose immediate child directories are pack roots. After initialization, discovery alone does not enable a directory. While the selected state is absent, the explicit all-discovered initialization policy enables the discovered UUIDs and normal validation still determines whether they can become active.

Resolution performs these checks in order:

1. unique UUID across roots
2. current manifest validation
3. lock validation when present or required
4. required dependency availability
5. record-file validation
6. canonical record-ID conflicts and explicit replacements
7. resource inventory and asset references
8. explicit named-resource provider resolution from state

Invalid packs and packs whose required dependencies are invalid are excluded from the generated cache. Other valid packs remain usable. Diagnostics retain exact UUIDs and paths.

## Installation and update

Install accepts a directory or ZIP, rejects unreadable or malformed archives, absolute or traversing member paths, symbolic links, duplicate member paths, and file/directory path collisions, validates the released pack in staging, and then moves it into the managed root. Archive-open and extraction failures are normalized as handled pack-operation errors. The pack layer defines no archive byte or member-count ceiling. A fresh install does not activate the pack and therefore does not require its declared dependency packs to be installed already; dependency availability is enforced before activation. Update requires an existing managed pack with the same UUID and a strictly newer CalVer. An enabled update succeeds only when the resulting dependency graph is valid; on a rejected update the prior release is restored. The prior release otherwise moves to quarantine below the managed root on the same filesystem.

Remove accepts only a lowercase UUIDv7, requires a disabled managed pack, and moves its exact managed UUID directory to recoverable quarantine. Manifest validation is not a prerequisite, so a missing or corrupt manifest does not block recovery. Permanent deletion is outside the default management operation.

## User state and shipped initial state

`pack-state.json` contains exactly `pack_roots`, `enabled_packs`, and `resource_providers`. The last field maps lowercase logical resource names to provider pack UUIDv7 identities. The core ships [default-pack-state.json](../config/default-pack-state.json) as its minimal release seed, with commons and its required providers. When the selected state does not yet exist, [pack-initialization.json](../config/pack-initialization.json) adds every discovered pack and unambiguous additional provider. Explicit user state then becomes the sole activation and provider authority. It is not merged with the shipped file.
