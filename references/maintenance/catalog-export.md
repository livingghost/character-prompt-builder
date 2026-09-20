# Catalog export

The exporter writes a directory rather than one document containing every record. Open `catalog/index.html` directly. That file is a small, script-free landing page; it does not load the compact search index or create thousands of DOM nodes. Search, visual browsing, complete records, and Visual Evidence are split into separate pages.

## Catalog terminology

The catalog uses **Visual Evidence** as the product-facing name for the feature and its authored record relationship. An individual original file is an **evidence artifact**. A display-only WebP sidecar is a **preview thumbnail**. `SVG` appears only where the file format itself is relevant, such as a filename, MIME type, download target, safety validator, or rasterization operation.

## Generate every pack below an explicit tree

```bash
python scripts/catalog_html.py \
  --pack-tree packs \
  --released \
  --output catalog
```

`--pack-tree` recursively discovers every `pack.json` below the explicit directory. Each discovered pack is validated and sorted deterministically. Adding another pack later beneath `packs/` therefore requires no change to the command, exporter, home page, filters, or full-release builder. The exporter never scans ambient user directories unless they are explicitly supplied.

Use repeated `--pack` for a deliberately fixed subset. Use `--state` or `--settings` when enabled-pack state, rather than every pack in a tree, should define the catalog.

## Direct-open structure

```text
catalog/
  index.html                         script-free landing page
  search.html                        interactive filtering and paging
  catalog-manifest.json

  assets/
    catalog.css
    catalog.js

  data/
    catalog-index.js                 compact filtering data
    record-asset-map.json            forward and reverse evidence links

  visual-evidence/
    index.html                        Visual Evidence gallery page 1
    page-002.html                    additional static gallery pages

  linked-presets/
    index.html                        presets with evidence, page 1
    page-002.html                    additional static gallery pages

  browse/
    kinds.html                        discoverable record-kind entry points

  packs/
    <pack-id>.html                    pack summary and kind links

  records/
    <pack-id>/
      <record-id>.html                one complete authored record
```

`index.html` offers Visual Evidence, linked presets, record kinds, packs, and search as separate entry points. A user does not need to know an archetype ID or internal label before browsing. The Visual Evidence gallery starts from lightweight preview thumbnails; each evidence card links to the Visual Evidence record, every authored evidence artifact, and every linked canonical preset. The linked-preset gallery starts from preset thumbnails and opens the full preset page.

The interactive search page renders at most 60 cards at once. Its asset-presence filter has distinct meanings:

- presets with linked visual evidence;
- presets without linked visual evidence;
- visual-evidence asset records;
- presets linked to multiple evidence assets.

The option labels contain the actual generated counts. Asset records are not counted as presets with linked evidence.

## Record and Visual Evidence linkage

Visual-evidence records own the authoritative relationship through `canonical_record_ids`. The optional `canonical_record_refs` array accepts three forms:

- a bare record ID, such as `"forest-portrait"`, which means exactly what the same ID means as an element of `canonical_record_ids`;
- a pack-qualified string, `"<pack_id>:<record_id>"`, when an asset intentionally names a record in another pack;
- an object, `{"pack_id": "<pack_id>", "record_id": "<record_id>"}`, which says the same as the pack-qualified string.

A record ID never contains a colon, so the bare and pack-qualified string forms cannot be confused. Resolution occurs only after pack replacement and dependency rules have been applied.

The exporter creates both directions:

```text
canonical preset -> linked Visual Evidence record -> evidence artifacts
Visual Evidence record -> linked canonical presets
```

For each relationship it records:

- pack and record IDs for both sides;
- links to both detail pages;
- artifact ID, technical role, media type, relative resource path, and SHA-256;
- a lightweight catalog-thumbnail path when the pack provides one;
- the primary evidence artifact and every additional evidence artifact as direct download or inspection links.

Catalog thumbnails are display-only sidecars and never become prompt authority. A pack without sidecars falls back to its declared primary previewable resource.

The same data is available to tools in `data/record-asset-map.json`. Generation fails when an enabled asset names a canonical record that cannot be resolved. The exporter does not infer relationships from labels, filenames, tags, species, or visual similarity.

## Resource location

By default, record and gallery pages use relative links to validated pack resources. In a full release, `catalog/` and `packs/` share one product tree, so the original evidence corpus is not duplicated. No emitted link or `src` is a `/mnt/data` path or a `file://` URI. Record content is published verbatim and is not subject to this rule.

For a standalone catalog that can be moved without its packs, add:

```bash
--copy-assets
```

This copies referenced resources beneath `catalog/media/`. It can be large because the evidence corpus is included once inside the portable catalog.

## Full release

```bash
python scripts/package_full.py
```

The full builder stages every validated pack from the explicit `packs/` tree, regenerates the catalog from that staged tree, runs the complete production gate set against the staged and extracted release trees, validates all local HTML and evidence-resource links, verifies `FULL-MANIFEST.json`, and builds a deterministic archive. Reports, checksum, and archive are published only after every gate succeeds. The ordinary `scripts/package.py` remains the minimal default-pack release.

Validate an already generated catalog independently with:

```bash
python scripts/validate_catalog_site.py catalog
```

The validator walks every generated HTML page, preview thumbnail, stylesheet, script, preset-to-Visual-Evidence mapping, reverse mapping, and relative evidence-artifact target. It also rejects workspace path leaks and a direct-open landing page that loads the search index.

## Inspection scope

The exporter is an inspection tool. It does not rank, normalize, merge, summarize, or rewrite records, and it never modifies source packs. Lock verification is controlled by `--released`.
