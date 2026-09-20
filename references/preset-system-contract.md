# Preset System Contract

This contract defines the authority, purpose, and runtime use of Character Prompt Builder's production-knowledge library.

## Core principle

A preset is reusable visual production knowledge. It is not a replacement for language understanding, image intent, or art direction.

The authority order is:

```text
1. explicit user intent
2. meaning of the user's whole brief
3. chosen image intent and art direction
4. series identity locks, when any
5. selected preset records
6. project defaults
```

A lower layer cannot silently override a higher one.

## Art direction and sparse exploration

A well-specified brief establishes these decisions before focused preset retrieval:

- center of appeal
- subject relationship
- composition and focal hierarchy
- medium family
- shape rhythm and proportion emphasis
- surface and tactile character
- color and lighting logic
- detail hierarchy

Focused retrieval then sharpens, implements, or repairs the chosen direction. It does not decide what the image should be.

A sparse identity brief is a controlled exception. After the image intent and explicit anchors are understood, `recommend` may retrieve several materially different outcome directions for still-open axes. Recommendation adopts no preset, does not override anchors, and does not replace art-directorial judgment. One direction must still be selected before canonical records are adopted and assembled.

## Record roles

### Curated

A `curated` record satisfies the Preset Authoring Standard. It carries complete production knowledge for its defined scope. Its structured relationships, invariants, translation rules, and diagnostics must be inspected before use.

### Vocabulary

A `vocabulary` record supplies a current name, option, or model-legible phrase. Its brevity is intentional. It does not imply hidden staging or rendering knowledge.

The roles are not a quality ladder. Curated knowledge is useful for implementation; vocabulary is useful for recall and communication.

## Knowledge families

### Atomic module

One reusable visual decision or construction solution. Examples include a camera treatment, pose geometry, lighting condition, prop, material, expression, surface strategy, or aesthetic touch.

Atomic means one decision, not a short or vague record.

### Universal aesthetic core

One cross-domain appeal and visual-taste system. It may define:

- appeal center
- silhouette and proportion strategy
- performance strategy
- viewer relationship
- composition and focal hierarchy
- shape rhythm
- tactile taste
- color-light taste
- finish and detail hierarchy

A universal core uses `domains: ["shared"]`. It contains no domain anatomy, locomotion, facial organ, or material assumptions. Use zero or one core when it contributes useful production knowledge to the already chosen art direction.

### Concrete style family

One concrete finish language binding line hierarchy, form abstraction, value and shadow design, highlight placement, color behavior, surface grouping, background treatment, detail hierarchy, and subject-domain overlays. Use zero or one family after the art direction is chosen.

The selected family is the primary positive grammar. Its linked rendering profile supplies the medium envelope and scoped negative boundary. The two full grammars are not concatenated. Aesthetic touches remain subordinate to the family's compatibility policy.

### Domain realization

A translation system for one exact subject domain:

```text
human
anthropomorphic-animal
animal
creature
hybrid
robot
```

It defines how the chosen art direction and any selected universal core become valid identity, anatomy or body plan, expression or behavior, surface, locomotion, manipulation, contact, and environmental interaction.

Use the baseline domain realization matching the subject unless a more specific curated realization is clearly relevant. A scene with materially different subject domains may use one realization for each represented domain. Baseline versus specialized is a record-level realization tier, never a content-pack boundary.

### Rendering profile

One coherent medium grammar: line, shape language, value structure, color behavior, surface rendering, light response, background policy, detail hierarchy, and medium-drift terms.

Use at most one profile. A hybrid medium is a separate art direction.

### Base scene

A reusable staging blueprint. It stores body or structural geometry, action, gaze, support, contact, depth, crop, focal hierarchy, environment, and adaptable fields.

### Finished recipe

A repeatable production template combining one complete scene and one complete rendering profile. It is not the default source of a new concept.

### Distinctive-detail module

A curated localized identity feature. It records feature type, subject-relative region, laterality, landmark relation, count, relative size, shape, orientation, color and value relationship, physical depth, edge character, surface interaction, age, visibility, and identity priority. It supports scars, tattoos, notches, claws, wrinkles, calluses, damage, wear, asymmetry, and comparable details. It does not replace the broader surface or marking system.

### Character archetype

Identity construction for series consistency. It stores stable morphology, palette, markings, proportions, surface system, and identity-defining equipment. It excludes one-off camera, environment, pose, lighting, occupation, and ordinary wardrobe decisions. A species label, body build, color, accessory, or scene is not an archetype by itself; creation and merge rules are defined in `archetype-governance.md`.

### Correction

A positive repair for one concrete failure risk. It defines trigger, diagnosis, correction, inspection points, and scoped avoidance terms.

## Retrieval and inspection

Catalog retrieval is deterministic textual evidence, not artistic judgment. Preset names and IDs are not required for discovery.

Record retrieval has three modes:

- `recommend`: explore coherent finished-image directions from a sparse brief. It returns anchor evidence, open axes, identity candidates, and direction cards.
- `search` or `inspire`: retrieve known staging, identity, style, or atomic craft knowledge for a chosen direction. Normal search groups near-duplicate variants.
- `inspect`: read the complete canonical record selected by an internal ID.

Search and recommendation output are discovery excerpts. `strong` and `moderate` describe textual evidence only. Empty results are valid. Every selected ID must be inspected in full before adoption. Expression, emotion, pose, activity, situation, relationship, theme, and content-intensity terms are valid retrieval evidence when the canonical records support them. Read `references/maintenance/search-discovery.md` when authoring this evidence.

```bash
python scripts/catalog_cli.py recommend "elderly human botanist" --domain human --directions 4
python scripts/catalog_cli.py inspect <record-id>
```

Searchable image resources have a discovery interface, followed by an explicit Reference Use Plan and runtime:

```bash
python scripts/catalog_cli.py asset-lookup <asset-id-or-canonical-record-id>
python scripts/reference_runtime.py plan \
  --record-use <identity-record-id>=identity \
  --record-use <environment-record-id>=environment \
  --record-use <lighting-record-id>=lighting \
  --transport-mode prompt-artifacts \
  --source-lighting-mode preserve \
  --out reference-use-plan.json
python scripts/reference_runtime.py execute \
  --plan reference-use-plan.json \
  --output-dir reference-package
```

`inspect` and `asset-lookup` are discovery-only operations. They expose complete canonical records, linked asset records, technical roles, owning-pack coordinates, resource paths, media types, and hashes, but they do not activate or prepare a generation reference. After adopting records, each repeated `--record-use RECORD_ID=INTENDED_INFLUENCE` declares why a canonical record contributes visual authority. The planner rejects an influence that the complete canonical record does not affirmatively support. Record-use order establishes precedence. The planner resolves suitable active linked assets and records each source, semantic role, authority boundary, prohibited influence, and Surface and Lighting Plan.

`reference_runtime.py execute` validates the sealed plan against the same active pack runtime and materializes the sole canonical `prepared-reference-set`. `preserve` is resolved only by an item with `intended_influence=lighting` and `technical_role=faithful-archival-vector`; `specular-audit` alone remains candidate highlight evidence and cannot own full shadow or material behavior. Surface-plan `source_evidence_roles` records the qualifying items' unique semantic roles and must exactly match the plan validator's recomputation. `rescope` and `replace` require explicit target light sources and material responses before model-facing execution. Prompt delivery includes the actual selected SVG files; model-facing modes keep the authoritative source and exact transport separate and commit both hashes. A finalized state Reference Selection, when present, enters that same execution through `--reference-selection` to constrain eligibility and preserve state scope. Generation Package construction copies the committed carriers into its self-contained `<out-stem>.references/` companion, rebases the canonical set to those paths, and embeds that set and its hash. Any selected source or transport failure blocks packaging rather than silently removing a reference. For visual inspection without ranking, rewriting, or merging records, export an explicit pack set or enabled state with `scripts/catalog_html.py`.

Request-supplied images are not catalog records. `prepare_generation_references.py --supplied-selection-file` accepts only explicit `supplied-file` sources and produces the same canonical prepared reference set. Pack-owned sources always derive from the Reference Use Plan and runtime.

Normal `inspire` output separates:

```text
aesthetic_cores
style_families
domain_realizations
render_profiles
subject_archetypes
atomic categories
```

Base scenes and finished recipes are reachable through `search --kind scene` and `search --include-recipes`. An empty requested category is a valid result. Reformulate and retry only when the semantic craft question itself should be expressed differently, and do not infer absent catalog coverage from a single query.

Do not concatenate these records blindly. Adapt each according to its function.

## Composition rules

- The art direction remains authoritative.
- Use zero or one universal core.
- Use one matching realization per represented subject domain.
- Use zero or one compatible rendering profile.
- Use atomic records only for relevant construction questions.
- Keep finished recipes optional.
- Do not average several complete cores, profiles, or scenes.
- Do not let a vocabulary record invent missing staging.
- Do not let a domain realization become an aesthetic style or a scene.
- Do not let a universal core introduce anatomy.
- Judge integrity-bundle applicability against pose, anatomy, and framing; a structure the drafted prompt forgot still activates its bundle.

## Prompt knowledge and execution boundary

Character Prompt Builder stores and composes prompt knowledge; it does not execute image generation. Canonical records preserve relevant supported content even when it is grotesque, disturbing, violent, medical, adult erotic, sexual, sensual, intimate, nude, body-altering, or otherwise sensitive. Sensitivity alone is not a reason to remove, soften, or hide production knowledge. All content types, including graphic, erotic, sexual, nude, violent, medical, and other intense content, are authored, preserved, retrieved, and composed under the same authority order and evidence standard, without exception. Do not invent detail that the source and brief do not support, applying the same general authoring rule regardless of content type. Unrelated records must not be auto-injected into a prompt. Downstream execution policy belongs to the separate target system. Read `references/prompt-knowledge-boundary.md`.

## Positive and negative information

Prompt-facing positive fields describe the desired image affirmatively.

The following remain diagnostic unless activated through policy:

- scene failure modes
- atomic misreadings
- domain-realization boundaries
- archetype diagnostics
- correction avoidance terms

Negative output is assembled according to `cpb-resource:negative-policy` resolved from the explicitly selected provider, using applicable technical hygiene, selected medium boundaries, activated corrections, and explicit user exclusions.

## Canonical interface

Current identifiers are exact. Tiers, domains, categories, and preset IDs must match the current catalog. Duplicate consolidation updates internal references and leaves one canonical record.

The automatically invalidated pack cache is a derived many-to-many English discovery index. It maps ordinary canonical phrases to one or more records with facet, source, and weight evidence, and stores search profiles for curated records. Every record reference uses a current canonical ID directly. The calling agent translates arbitrary user-language briefs into canonical English or supplies `schemas/catalog-query.schema.json`; the package maintains no per-language alias dictionaries.

## New-session reconstruction

Before using the library in a new session, read:

1. this contract
2. `references/preset-workflow.md`
3. `references/aesthetic-language.md`

When the brief contains only a few identity anchors or asks what the catalog can produce, also read `references/runtime/sparse-discovery.md`.

Before editing records, also read:

4. `references/preset-authoring-standard.md`

This reading order establishes the purpose of the library before any record is selected.
