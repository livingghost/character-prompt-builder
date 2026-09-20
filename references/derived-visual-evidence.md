# Derived Visual Evidence

## Purpose

Derived Visual Evidence gives CPB a source-derived perceptual vector layer that is materially smaller than pixel-faithful path expansion while preserving native canvas dimensions, coherent shapes, local color organization, and fine detail to a measured perceptual threshold.

## Three-layer contract

### Layer A: source-derived perceptual vector projection

`faithful-archival.svg` is a self-contained full-color path projection. The extractor:

- keeps the source width and height as the SVG canvas;
- performs no preliminary resize or resampling for Layer A;
- never embeds a raster payload or creates an external raster reference;
- applies one profile uniformly to the complete frame;
- starts with a compact palette and edge-preserving filter, then increases palette density for the whole image until every gate passes;
- polygonizes connected accepted-color areas without semantic importance maps;
- does not delete small connected regions or simplify contours after polygonization;
- selects the first passing profile instead of reproducing JPEG/WebP noise pixel by pixel.

This is a source-derived perceptual vector projection, not an exact source-raster archive or a pixel-identical replacement.

### Layer B: audit extraction set

Layer B contains a subject mask, structural line-and-tone guide, color audit, saturation rescue, specular audit, and palette probes. These are intentionally simplified measurement artifacts. Automated masks do not claim human review, owner approval, or canonical segmentation.

### Layer C: runtime attachment build

Layer C stores the executable reference-use plan and recipes for disposable model-facing guides. After selecting a canonical record, declare its use as `RECORD_ID=INTENDED_INFLUENCE` and build the plan through `scripts/build_reference_use_plan.py` or `scripts/reference_runtime.py plan`. The intended influence is one of `identity`, `pose-camera`, `outfit`, `surface-finish`, `lighting`, `environment`, `prop-accessory`, or `local-color`. The planner selects active linked evidence, assigns explicit precedence, and computes each artifact's authority as the intersection of its technical role and that record-scoped influence.

For identity reuse, stable authority includes species, anatomy, permanent markings, and stable anthropomorphic head hair, mane, ruff, facial hair, tuft and body-fur distribution, regional covering boundaries, silhouette construction, and grooming topology. The umbrella exclusion covers the complete class of scene-conditioned presentation outside the declared identity influence, including properties not named in examples. Gaze, expression, mouth state, perspiration, outfit, pose, wind, wetness, motion response, temporary styling, and displaced, compressed, or raised fur are examples of excluded state.

`scripts/reference_runtime.py execute` materializes one complete `prepared-reference-set`. For model-facing modes, each prepared-reference row retains the selected artifact as authoritative `source` and records the disposable file as `transport`, with separate paths, media types, hashes, bounded authority, and a committed derivation. For prompt delivery, each prompt-artifact row commits an exact copy of the selected source with equal source and delivered hashes.

For `gpt-image-2.5-flare`, the declared reference inputs are PNG, JPEG, and WebP. A selected managed SVG is therefore rendered safely and deterministically from that same SVG to a PNG transport. The `svg-rasterization` derivation commits renderer identity and release, source SHA-256, output dimensions, and `max_side`. Preparation never replaces the selected artifact with another structural, palette, saturation, highlight, or mask artifact. Failure blocks packaging; it does not remove the reference or switch transport modes.

## Perceptual gates

The current whole-frame gates are:

```text
PSNR:                  28 dB or higher
SSIM:                  0.90 or higher
Minimum tile SSIM:     0.75 or higher
Mean CIEDE2000:        3.5 or lower
P95 CIEDE2000:         12 or lower
Edge F1:               0.88 or higher
Mean absolute error:   6 or lower
```

SSIM, tile SSIM, CIEDE2000, and edge measurements are evaluated at a bounded measurement resolution; PSNR and mean absolute error use the native-size candidate. These gates measure the accepted raster candidate from which connected-contour paths are emitted. They establish a bounded perceptual projection, not an exact source-raster archive. Managed SVGs are also hash-checked and fully scanned for prohibited active or external content.

## Uniform quality

All regions in one image use the same selected profile. Faces, backgrounds, accessories, textural surfaces, and empty regions do not receive different semantic quality budgets. The profile may differ between source images only because each complete image must clear the same gates.

## Semantic regions

Semantic region maps use native coordinates. A region is added only when its meaning and SVG element references are actually authored. Automated conversion alone does not make a region reviewed, approved, or owner-declared. An empty region list is valid.

## Source admission

Only user-provided source images are admitted. Assistant-generated images, contact sheets, montages, previews, comparison renders, diagnostic composites, and other conversational work products are excluded.

## Safety and portability

Managed SVGs reject scripts, `foreignObject`, event handlers, animation, embedded raster images, data URLs, remote references, local file references, and symbolic links. Content-derived identifiers replace local filenames, sandbox paths, conversation identifiers, upload timestamps, approval state, review state, story ranges, and runtime selection fields.

## Product boundary

Every evidence bundle remains in the same owning content pack as its searchable asset record, canonical-record relationships, policies, lock inventory, and rights declaration. The core release ships the extraction, validation, and prompt-authoring machinery plus the minimal commons pack; independently authored packs are distributed separately. This distribution boundary does not change the loose capability boundary the interchange envelope defines.

## Runtime activation and delivery

Derived Visual Evidence is activated after canonical record selection, not only when a new raster is supplied. If an active pack links a selected record to a visual-evidence asset, the agent builds a role-scoped `reference-use-plan` and considers the linked SVGs for the final package without waiting for a separate user reminder.

A prompt requested as the final product still receives selected source artifacts. Use `prompt-artifacts` to deliver the prompt, negative prompt, plan, Surface and Lighting Plan, preamble, prepared-reference-set, and exact selected files. Use `svg-bundle` only when the downstream workflow consumes SVG and every selected artifact is SVG. No image-generation call does not mean no visual-reference activation.

Layer A, Layer B, and Layer C have separate responsibilities:

- Layer A carries source-derived identity and appearance evidence.
- Layer B separates structural, color, saturation, highlight, and mask evidence.
- Layer C commits selected record uses, intended-influence/technical-role authority intersections, exclusions, precedence, target transport, state eligibility when applicable, and Surface and Lighting authority.

For multi-image endpoints, keep selected layers as separate ordered inputs. For a one-image endpoint, construct a disposable board and preserve each panel's role, source hash, transport hash, and coordinates separately from the final board hash. Do not flatten several references into an unnamed average or allow one panel's visible properties to widen another panel's authority.

`specular-audit.svg` remains a candidate-highlight map. It does not prove material class, roughness, lobe width, reflection tint, or shadow topology. Those decisions belong to `surface-lighting-plan.json`.

Full source-lighting preservation requires a selected plan item at the exact `intended_influence=lighting` and `technical_role=faithful-archival-vector` intersection. `specular-audit.svg` alone cannot resolve it. The Surface and Lighting Plan's `source_evidence_roles` records the unique semantic roles of every and only eligible item, never technical-role names, and validation derives that list exactly from the plan.

Prompt-facing packages may retain explicit unresolved Surface and Lighting decisions for review. Model-facing `multi-image` and `single-board` execution is blocked until every decision is resolved. For state-aware work, pass the finalized Reference Selection to `reference_runtime.py execute`; every plan item must match the same committed source and an eligible intended influence.

Give planning, state selection, execution, Generation Package construction, and verification the same complete pack runtime. Each boundary revalidates current active-pack ownership, media declaration, source identity, and source bytes. The executor creates the complete reference package in a sibling staging directory and promotes it only after validation, so a failed build does not leave a partial package.

For direct generation, pass the canonical `prepared-reference-set.json` to the stateless or state-aware Generation Package builder. The builder copies the model carriers into the package's named `.references` companion, commits relative transport paths strictly inside that exact companion, and publishes the JSON plus companion transactionally. Composite-board carriers follow the same boundary; absolute and outside-companion paths are invalid. Move JSON and companion together. Only `verify_generation_payload.py` resolves those paths and emits `host_forwarding.selected_references`; never scan a directory, infer a neighboring file, reconstruct the preamble, or forward source paths directly.
