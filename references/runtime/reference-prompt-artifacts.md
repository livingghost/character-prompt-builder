# Prompt Artifact Reference Runtime

Use this document after selecting canonical records whenever linked visual evidence exists or the requested deliverable includes prompt plus reference files. This path materializes source SVG or raster artifacts without calling an image-generation service.

## Contents

- [Activation gate](#activation-gate)
- [Record-scoped authority](#record-scoped-authority)
- [Technical artifact roles](#technical-artifact-roles)
- [Prompt-facing transports](#prompt-facing-transports)
- [Surface and Lighting Plan](#surface-and-lighting-plan)
- [Dependency activation matrix](#dependency-activation-matrix)
- [Commands](#commands)
- [Validation and failure policy](#validation-and-failure-policy)

The canonical chain is:

```text
selected canonical record use
-> reference-use plan
-> optional state eligibility
-> prepared-reference-set
```

Do not create an independent reference list beside this chain. The prepared-reference-set is the sole prepared-reference truth.

## Activation gate

Before final prompt delivery:

1. Inspect every selected canonical record in full.
2. Run full `asset-lookup` for every selected record. Review complete active-pack ownership, resource metadata and source bytes, artifact paths and hashes, linked-record context, and technical roles before deciding whether evidence is adopted.
3. For an adopted visual contribution, declare `RECORD_ID=INTENDED_INFLUENCE`. The influence is exactly one of `identity`, `pose-camera`, `outfit`, `surface-finish`, `lighting`, `environment`, `prop-accessory`, or `local-color`.
4. Build one Reference Use Plan from the declarations.
5. Review every selected item's semantic role, technical role, authority, exclusions, and precedence.
6. Resolve or explicitly retain prompt-facing Surface and Lighting decisions.
7. Execute the plan transactionally as `prompt-artifacts` or, for an explicitly SVG-consuming downstream tool, `svg-bundle`.
8. Validate the prepared-reference-set against its package root, the current active pack declarations, and current source bytes.

`asset-lookup --summary` is an optional preview only. It omits complete active-pack ownership, resource metadata, paths, hashes, linked-record context, and source bytes, so it cannot satisfy the gate or support an adoption decision. Full `asset-lookup` and review are mandatory for every selected record whether or not its evidence is ultimately used.

When an adopted target-finish canonical record has linked visual evidence and the downstream interface accepts image input, declare that record as `surface-finish` and transport the resulting plan-scoped artifact instead of relying on prose to carry the finish. The selected record's `style_reference_guidance` defines exactly which qualities the reference governs. Prose translation of a finish is lossy in both directions. The selected source remains part of the canonical plan; failed preparation blocks execution rather than reopening an undeclared text-only path.

Use the same complete `--state-file`, `--cache-dir`, `--managed-root`, and repeated `--pack-root` context at every boundary. A previously valid plan cannot reactivate a disabled, deleted, replaced, or changed pack source.

The gate may produce zero references only with a structured `zero_reference_reason`, such as no suitable active asset, user-declined visual evidence, or state ineligibility. A reference-free prepared set uses transport mode `none`. Every prepared set with pack-backed references embeds a non-null plan and its hashes.

## Record-scoped authority

The intended influence states why the canonical record is used. The artifact's technical role states what its pixels or vectors can prove. An item receives only the intersection of those authorities. The whole record and every visible source property do not become authoritative.

| Technical role | Eligible intended influences | Bounded evidence | Must not control by itself |
| --- | --- | --- | --- |
| `faithful-archival-vector` | `identity`, `outfit`, `lighting`, `surface-finish`, `prop-accessory`, `local-color` | source-supported appearance within the declared influence | target pose, crop, environment, temporary state, outfit, or any visible property outside the declared influence |
| `structural-line-tone` | `pose-camera`, `outfit`, `environment`, `prop-accessory` | structure, silhouette, overlap, broad value, or construction within the influence | final local color, material finish, lighting color, or rendering medium |
| `color-audit` | `identity`, `outfit`, `surface-finish`, `prop-accessory`, `local-color` | permanent marking or declared local-color relationships, never geometry | shape, pose, camera, identity topology, material class, or lighting direction |
| `saturation-rescue` | `local-color` | small declared high-saturation accents only | base color, geometry, identity, pose, material, or lighting |
| `specular-audit` | `surface-finish`, `lighting`, `prop-accessory` | candidate highlight placement and density only | local color, identity topology, pose, shadow topology, or material class by itself |
| `subject-mask` | `pose-camera`, `environment` | silhouette or subject-background separation only | identity detail, local color, material, lighting, or internal anatomy |

Every authority block includes affirmative controls and nonempty `must_not_control` exclusions. Scene-conditioned presentation outside the intended influence must not transfer, including properties not named in examples.

Identity authority includes stable species, anatomy, permanent marking layout, human-like head hair, mane, ruff, facial hair, fur-tuft and body-fur distribution, regional boundaries, silhouette construction, and stable grooming topology. It excludes the open class of scene-conditioned presentation: attention, expression, mouth state, physiology, outfit, props, pose, camera, environment, lighting, current wetness or wind response, fur compression or raising, temporary styling, dirt, injury state, relationships, viewer awareness, and other changeable presentation. Transfer excluded properties only through another declared influence or approved state artifact.

The same boundary applies to every influence. An outfit item acquires no identity or expression authority; a pose-camera item acquires no species, markings, local color, material, outfit, or lighting authority; finish and lighting items acquire no geometry or identity authority.

Logos, watermarks, signatures, UI residue, copied meaningless text, contact-sheet borders, and obvious post-added concealment are source contamination. They contribute no scene, prop, body, occlusion, negative-term, or failure knowledge. Exclude them before assigning visual authority; do not reinterpret them as deliberate image content.

## Technical artifact roles

Layer A is a `faithful-archival-vector`: source appearance bounded by its declared influence and the preceding exclusions.

Layer B keeps five audit projections separate: `structural-line-tone.svg`, `color-audit.svg`, `saturation-rescue.svg`, `specular-audit.svg`, and `subject-mask.svg`. Each obeys the preceding table's bounded evidence and exclusions; none supplies another role's authority.

Do not present an audit projection as the final image. Its grayscale, white mask, flattened palette, or isolated highlights must not leak into the target medium unless independently requested.

Layer C is the Reference Use Plan and prepared transport. It records ordered uses, semantic and technical roles, bounded authority and exclusions, precedence, pack and source provenance, source hashes, exact package paths and delivered hashes, the Surface and Lighting Plan and hash, the canonical preamble, optional state-selection origin, and optional board or transport data for a later generation branch.

Use one reference when one record/artifact pair has clear bounded authority, or several when separate record uses carry identity, pose-camera, outfit, surface-finish, lighting, environment, prop-accessory, or local-color evidence. Preserve plan order as explicit precedence. Never assume one SVG is the only available reference or merge several source roles into an unnamed average. The same canonical record may be declared repeatedly for distinct intended influences. Duplicate technical roles remain separate because `record_id` plus `intended_influence` defines their authority; multi-reference use does not require different canonical records.

When an already validated Visual Evidence Bundle is active, verify its native-dimension source-derived perceptual Layer A vector projection, whole-frame profile and fidelity metrics, hashes, SVG safety, Layer B audit set, Layer C runtime recipes, and portable source identity before using it as visual authority. An automated audit mask is not human review. Never feed the entire corpus to a model; select the small number of relevant bundle items and compile only disposable, role-scoped attachments through the canonical Reference Use Plan.

## Prompt-facing transports

Use `prompt-artifacts` for prompt delivery. The package contains:

```text
final-prompt.txt
final-negative.txt
reference-use-plan.json
surface-lighting-plan.json
prepared-reference-set.json
reference-preamble.txt
reference-artifacts/*
```

`prompt-only` is an interaction and user-facing reference result: no image-generation API is called and zero references are selected. It does not mean that visual-reference discovery was skipped. The canonical reference-free prepared set has `transport_mode: none` and a structured `zero_reference_reason`; `none` is prepared transport terminology, not a user-facing reference mode. When prompt delivery includes selected artifacts, materialize `prompt-artifacts` and report `prompt+1` for one or `prompt+N` for two or more, even though no generator is called. Deliver the exact source files with the prompt, negative prompt, Reference Use Plan, Surface and Lighting Plan, preamble, and prepared-reference-set. Never report a prompt package with selected references as `prompt-only` or `none`.

The executor copies every selected source artifact byte-for-byte. Each prepared row records source identity and SHA-256, package-relative delivered path, media type, and delivered SHA-256. Source and delivered hashes must match. A path or hash in prose is not file delivery. Do not substitute one faithful, structural, palette, saturation, specular, or mask artifact for another.

Use `svg-bundle` only when every selected artifact is SVG and the downstream non-generation workflow explicitly consumes SVG. It retains the same role-scoped plan, separate files, hashes, and Surface and Lighting Plan. Never flatten several artifacts into one unnamed SVG.

Prompt-facing packages may retain named unresolved Surface and Lighting decisions for human review. They remain visible in the plan and must not be described as resolved.

Report the prepared set's transport mode and hash, embedded plan and plan hash, nested Surface and Lighting hash, optional finalized state-selection origin, structured zero-reference reason when applicable, exact source and delivered artifacts, and precedence. For a state-aware row, also report its binding ID, covered state, intended influence, review dimensions, unsupported or occluded state, and unsupported assumptions. Review permanent identity separately from every scene-conditioned influence and confirm that no excluded source presentation leaked into the package. Hide large parser audits by default.

For `multi-image`, `single-board`, target-model rasterization, Generation Package construction, or a model call, continue with [Image Generation Runtime](image-generation.md). For state eligibility, read [State-Aware Series Runtime](state-aware-series.md).

## Surface and Lighting Plan

Every plan declares one source-lighting mode:

- `preserve`: retain source-supported light, shadows, sheen, and highlights only when a selected item has both `intended_influence=lighting` and `technical_role=faithful-archival-vector`;
- `rescope`: retain declared material response while translating physical lighting to explicit target-scene sources;
- `replace`: make source lighting non-authoritative and use explicit target light and material contracts.

Visible light is not sufficient for `preserve`. A specular audit remains candidate-placement evidence and cannot preserve the full light, shadow, or material system. Without the exact eligible faithful item, preservation remains unresolved.

`source_evidence_roles` contains the unique semantic roles of every and only eligible preservation item, never technical-role names. Validation recomputes the exact list.

The plan separately records physical light sources and their apparent size, direction, color, relative intensity, and softness; form, cast, contact, and ambient-occlusion shadows; edge hardness, hue shift, occluders, and receivers; broad sheen, hard speculars, rim light, lobe width, edge character, reflection tint, and protected highlight islands; and per-material roughness, specular strength, highlight shape, wetness, and anisotropy.

## Dependency activation matrix

Determine dependency need immediately after selecting the transport:

| Operation | Required profile | Preflight |
| --- | --- | --- |
| prompt only with no references | Core | `python scripts/check_dependencies.py --profile core` |
| `prompt-artifacts` with existing SVG or raster files | Core | same Core check |
| `svg-bundle` | Core | same Core check |
| SVG-to-PNG model transport | Visual | `python scripts/check_dependencies.py --profile visual` |
| raster extraction or fidelity recomputation | Visual | same Visual check |
| full release validation | Tested | follow [Release Validation](../release/validation.md) |

Do not install Visual dependencies for prompt-artifacts or svg-bundle. If a later operation needs Visual, follow the conditional permission and stop rules in [Image Generation Runtime](image-generation.md).

## Commands

On first use, read the schema-derived plan example and replace its placeholders with the selected record and explicit pack runtime values. Read the complete schema only when manually authoring or repairing the JSON contract:

```bash
python scripts/reference_runtime.py example plan
python scripts/reference_runtime.py schema surface-lighting-plan
```

Build a prompt-artifact plan:

`scripts/build_reference_use_plan.py` and `scripts/reference_runtime.py plan` use the same canonical planning argument contract: identical record-use parsing, transport and lighting choices, repeatable light, material, unresolved-decision, and technical-role options, reference limits, target-model option, pack-runtime arguments, defaults, and requiredness. The standalone builder differs only by omitting the `plan` subcommand token.

```bash
python scripts/reference_runtime.py plan \
  --record-use <identity-record-id>=identity \
  --record-use <scene-record-id>=pose-camera \
  --transport-mode prompt-artifacts \
  --source-lighting-mode replace \
  --light-source-json '{"light_id":"target-key","direction":"front-left and above","apparent_size":"large","color":"neutral daylight","relative_intensity":"primary","softness":"soft"}' \
  --material-response-json '{"material":"character surfaces","roughness":"target-defined by material","specular_strength":"moderate by material","highlight_shape":"broad on soft surfaces and tight on hard surfaces","wetness":"dry","anisotropy":"none"}' \
  --out reference-use-plan.json \
  --state-file PACK_STATE_JSON \
  --cache-dir CATALOG_CACHE \
  --managed-root MANAGED_PACKS \
  --pack-root ADDITIONAL_PACK_ROOT
```

Validate and execute:

```bash
python scripts/validate_reference_use_plan.py reference-use-plan.json \
  --state-file PACK_STATE_JSON \
  --cache-dir CATALOG_CACHE \
  --managed-root MANAGED_PACKS \
  --pack-root ADDITIONAL_PACK_ROOT

python scripts/reference_runtime.py execute \
  --plan reference-use-plan.json \
  --output-dir prompt-package \
  --prompt-file final-prompt.txt \
  --negative-file final-negative.txt \
  --state-file PACK_STATE_JSON \
  --cache-dir CATALOG_CACHE \
  --managed-root MANAGED_PACKS \
  --pack-root ADDITIONAL_PACK_ROOT
```

`--record-use` and `--pack-root` are repeatable. The executor requires an absent or empty output directory. It builds and validates a sibling staging directory, promotes it only after every check passes, and restores a pre-existing empty directory if publication fails. A partial directory is never a valid package.

## Validation and failure policy

Stop when a record use is malformed; an influence is unsupported; a source is inactive, missing, changed, unsafe, or hash-mismatched; a technical role cannot serve the influence; semantic roles or precedence are invalid; the reference limit is exceeded; state eligibility disagrees; or transactional publication cannot complete.

Do not substitute an adjacent artifact, widen authority, drop a selected source, average properties, downgrade transport, or continue as text-only after a committed visual-reference step fails. Revise and review the plan, then materialize a new package.


## Artifact evidence and completion

For a saved deliverable, continue through [Production Execution](production-execution.md). Preserve this document's own interpretation, retrieval, approval and adoption boundaries. Prepare the exact inputs, capture the real output, bind review and selection to it, then complete and close the work task. `scripts/production_workflow.py status`, `impact` and `resume` recheck dependencies and artifact bytes. A progress checkbox, a search hit or a newly created image is not production completion or canonical adoption.
