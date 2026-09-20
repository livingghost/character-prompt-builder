# Visual Evidence in External Packs

A visual corpus belongs to its owning content pack. Its searchable asset records, SVG and JSON resources, canonical records, atomic modules, policies, UUIDv7 identity, CalVer release, lock inventory, and rights statements form one release unit.

Each admitted user-provided source hash has one portable three-layer bundle:

```text
visual-authority.json
visual-evidence-bundle.json
derived-visual/
  faithful-archival.svg
  vectorization-result.json
  semantic-regions.json
  subject-mask.svg
  structural-line-tone.svg
  color-audit.svg
  saturation-rescue.svg
  specular-audit.svg
  palette-probes.json
  audit-extraction-set.json
  runtime-attachment-build.json
```

`faithful-archival.svg` is a stable artifact filename for a source-derived perceptual vector projection, not an exact raster archive.

Layer A is a native-dimension source-derived perceptual vector projection with one uniformly selected profile for the complete frame. It intentionally discards compression noise and sub-visible pixel variation rather than expanding them into millions of paths. It is not an exact source-raster archive. Layers B and C provide audit artifacts and disposable runtime recipes.

The corpus contains no standalone source raster, Base64 image payload, SVG `image` element, external raster link, assistant-generated image, contact sheet, montage, or conversational work product. A pack may declare display-only WebP catalog thumbnails through its `catalog-thumbnails` resource; those previews carry no prompt authority and never replace the linked SVG evidence. Content hashes and portable canonical-record references are retained; source locators and workflow approval fields are not.

Place or install a complete pack directory under `packs/` or a registered pack root, enable its UUID, and inspect its searchable assets with the normal pack and catalog commands. Select that pack explicitly in `resource_providers` for logical resources such as `reference-corpus-manifest` and `reference-corpus-notice`; runtime resolution uses only that selected provider.

Validate a released pack directory with:

```bash
python scripts/pack_cli.py validate <pack-dir> --released
python scripts/validate_reference_corpus.py <pack-dir> --require-bundles --workers 1
```

These two commands validate the released pack inventory and the integrity of
the stored corpus. The corpus validator checks manifest and record closure,
asset-to-bundle relationships, file hashes, SVG safety, declared artifact
structure, and consistency between stored accepted metrics and stored
thresholds. It uses the standard-library Core profile. It does not possess the
source rasters, render the stored SVGs, or recompute PSNR, SSIM, CIEDE2000,
edge, or absolute-error measurements; therefore its success is not a new
fidelity result.

Creating a bundle or recomputing perceptual measurements from an admitted
source raster requires the Visual profile. Full core validation and packaging
require the exact Tested profile and independently exercise a real CairoSVG
render plus the production visual-evidence workflow.

When a pack declares its pack-owned release evaluation contract, run that
complete contract with an exact one-pack state and dedicated cache:

```bash
python -B scripts/pack_release_gate.py <pack-dir> \
  --state-file <absolute-exact-pack-state.json> \
  --cache-dir <absolute-dedicated-cache-dir> \
  --managed-root <absolute-existing-managed-dir> \
  --report-out <absolute-report-path-outside-pack>
```

The state must contain exactly this pack directory, enable only this pack UUID,
and select it for every and only its named resource bindings. The gate never
uses ambient or bundled default state.

Disabling or removing a pack removes all of its records and evidence resources from the derived catalog cache on the next refresh. The core runtime remains usable for installing, validating, and enabling other packs.
