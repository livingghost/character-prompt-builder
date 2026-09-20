# Reference Corpus Ingestion

## Goal

Give every admitted user-provided image in its owning content pack an explicit, portable disposition without creating one canonical preset per file and without leaking conversation or sandbox state into the pack.

## Workflow

1. Admit only user-provided source images.
2. Exclude assistant-generated images, contact sheets, montages, previews, comparison renders, diagnostic composites, and other conversational work products.
3. Identify each admitted source by SHA-256 and native media dimensions.
4. Group exact duplicates under one source hash.
5. Compare the source with existing scenes, cues, outfits, morphology, accessories, frame-character records, and style families.
6. Reuse or enrich a canonical family only through deliberate reviewed authoring when semantic authority matches and every detail, provenance fact, search association, and reference remains lossless. Visual or naming similarity alone never authorizes a merge.
7. Create a new record only when the source contributes a distinct reusable production contract.
8. Generate the native-dimension source-derived perceptual Layer A vector projection, Layer B audit set, Layer C runtime recipes, and portable metadata.
9. Validate hashes, schemas, uniform full-frame profile selection, perceptual gates, SVG safety, and corpus coverage.

## Portable manifest

The packaged manifest stores source SHA-256, media type, native dimensions, disposition, evidence relation, canonical record IDs, visual-authority reference, and visual-evidence-bundle reference. It does not store local filenames, absolute paths, sandbox IDs, conversation IDs, upload timestamps, approval status, review status, story ranges, or runtime defaults.

## Duplicate handling

Exact duplicates share one bundle. The manifest records aggregate source occurrence count rather than preserving local locator strings. Near duplicates remain separate sources when crop, compression, color, or content differs, but may share the same canonical record family.

Before corpus mutation, `scripts/preset_maintenance.py duplicates` can compare an
optional source directory with the owning pack's declared catalog thumbnails and
canonical metadata. It reports exact bytes, identical decoded pixels,
perceptual-hash candidates, aspect and color evidence, semantic overlap, and
existing family membership. The report is advisory and never deletes a source
or record automatically.

When removing a canonical record, use `scripts/preset_maintenance.py remove` so
record references and content-addressed evidence metadata remain coherent. Its
default evidence mode preserves the bundle as noncanonical when the removed
record was its final canonical link. The explicit purge mode removes the
manifest entry, thumbnail declaration, searchable asset, and bundle from the
pack while placing recoverable material outside the pack root.

## Corpus completeness

An owning pack's corpus release is complete only when every admitted user source resolves to one three-layer bundle, every expected artifact is present and hash-bound, every referenced canonical record exists, and every Layer A candidate meets the published perceptual gates. The core/default archive carries no completeness claim for an independently distributed corpus pack.

## Distribution

The user-owned pack keeps each admitted source's SVG and JSON evidence together with its records and policies. It contains no standalone source raster, embedded raster payload, external raster link, assistant-generated image, or conversational work image.
