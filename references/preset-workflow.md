# Preset Workflow

This workflow combines discovery and focused lookup. Preserve the user's fixed anchors while consulting successful craft patterns to develop open choices. A sparse brief can compare coherent directions before selection. During composition and repair, return to the library for each unresolved craft question. Follow [Craft consultation](runtime/craft-consultation.md) to connect selected knowledge to the production specification and its review.

## 1. Choose the retrieval path

Use focused lookup when the brief already establishes most outcome-defining axes: scene, relationship, composition, medium, camera, light, and mood.

Use sparse-brief discovery when the user supplies only a few stable facts, such as species, build, coat color, age, occupation, or one accessory, while scene, wardrobe, camera, light, mood, and style remain open. Preset names and IDs are not required.

```bash
python scripts/catalog_cli.py recommend \
  "elderly human botanist" \
  --domain human \
  --directions 4
```

Recommendation returns normalized anchors, open axes, identity candidates, and several direction cards. Each card explains what the finished image could become, which anchors it preserves, which choices it adds, what remains adjustable, and which internal records can implement it. Choose one card or present materially distinct cards when the user asks for possibilities. Do not average them.

Read `references/runtime/sparse-discovery.md` for runtime modifier scope and direction cards. Read `references/maintenance/search-discovery.md` for many-to-many index authoring, variant grouping, and sparse-query evaluation.

## 2. Develop the direction with focused retrieval

Use the brief and complete inspected records to establish:

- image intent
- center of appeal
- subject relationship
- composition and focal hierarchy
- medium family
- shape and rhythm
- surface and tactile character
- color and light
- detail hierarchy

The agent selects a coherent treatment, preserves the fixed anchors, and records the relationships borrowed from inspected knowledge.

## 3. Describe the chosen direction for focused lookup

Use concise canonical English for deterministic retrieval. The calling agent translates the complete user brief semantically, preserving relationships and modifier scope, then searches with the unresolved craft question it wants the catalog to solve. The catalog maintains no per-language word lists. Use `--query-json` when the original brief and language need to remain attached as opaque audit metadata.

Make each focused query one coherent craft question and preserve its load-bearing anchors and modifier relationships. Prefer three to six distinctive content words when they express the complete question, and run separate queries for materially different questions. Retrieval is field-aware and uses natural aliases, but it remains deterministic lexical retrieval: unmatched words can dilute matched words, and synonyms still matter. Retain additional wording when it is required for an anchor, negation, relationship, or modifier scope. Scoped modifiers matter: for example, `blue fur`, `blue eyes`, `blue lighting`, and `blue room` describe different targets.

Too vague:

```text
bedside scene
```

Too long because it combines several craft questions and dilutes its own matches:

```text
protective bedside size contrast open sheltering arm warm window light intimate 2D character illustration
```

Separated by craft question:

```text
protective bedside size contrast
warm window light interior
open sheltering arm
```

## 4. Run layered inspiration retrieval

```bash
python scripts/catalog_cli.py inspire \
  "protective bedside size contrast warm window light" \
  --categories composition,camera,lighting,hand-placement,pose-action,emotion-nuance \
  --domain anthropomorphic-animal \
  --core-limit 3 \
  --style-family-limit 3 \
  --realization-limit 2 \
  --profile-limit 3 \
  --archetype-limit 2
```

The response separates six groups, plus `axis_coverage` reporting which of the eight art-direction axes the requested categories cover, `query_token_count`, and a conditional `retrieval_note`. Empty groups are valid. If every requested group and category is empty, or `retrieval_note` reports that every requested atomic category is empty, separate the craft questions and retry each with three to six distinctive words before treating the result as absent coverage. Preserve every anchor and modifier relationship during recovery; one empty query is not proof that the enabled catalog lacks the concept.

### `aesthetic_cores`

Curated, domain-neutral appeal and taste knowledge. Select zero or one when it strengthens the existing art direction. A core does not supply anatomy or choose the concept.

### `style_families`

Curated concrete drawing grammars. Select zero or one when the art direction needs a specific line, form, shadow, highlight, color, surface, background, and detail system. Inspect the complete family and apply the overlay matching the subject domain. The linked rendering profile supplies the medium envelope and scoped negative boundary.

### `domain_realizations`

Curated translation knowledge for the exact subject domain. Use the selected matching realization to convert the direction into valid identity, anatomy or body plan, expression or behavior, surfaces, locomotion, contact, and environmental interaction.

### `render_profiles`

Curated medium grammars. Select at most one compatible profile.

### `subject_archetypes`

Identity contracts: stable morphology, palette, connected marking logic, proportions, and identity equipment for a recurring subject. Adopt a matching archetype, or diverge from it deliberately; when adopted, its identity constraints carry `automatic_prompt_injection: true` and belong in the prompt. Consult these before designing colors and markings from a blank page. Follow the [Reference Cluster Mapping Contract](maintenance/presets.md#reference-cluster-mapping-contract) and, when provided, resolve `cpb-resource:reference-cluster-mapping` from the explicitly selected provider for mappings to that pack's records.

### `categories`

Atomic candidates from the requested categories. The default `any` retrieval includes both curated and vocabulary roles.

Base scenes and finished recipes are reachable only through `search --kind scene` and `search --include-recipes`. Before atomic retrieval, always run one semantically focused `search --kind scene` query with the required staging relationships; do not restrict this query to staging already known to be common. Normal `search` output groups near-duplicate variants under one representative result. Use `--ungrouped` only when auditing exact inventory or comparing every variant.

## 5. Apply record roles correctly

### Curated

Use as complete production knowledge for its defined scope. Preserve its relationships and adapt them to the current direction.

### Vocabulary

Use for names and model-legible phrasing. Supply staging, light, interaction, and medium from the art direction and curated records.

Use `--tier curated` only when the unresolved question requires a complete blueprint. Use `--tier vocabulary` only for a naming or option question.

## 6. Inspect every selected ID

Recommendation and search output are discovery excerpts. User-facing discovery does not require IDs, but every internally selected record must be inspected before adoption.

```bash
python scripts/catalog_cli.py inspect <record-id-from-current-results>
```

The bundled commons pack is sufficient for copy-paste inspection examples across a rendering profile, domain realization, and concrete style family:

```bash
python scripts/catalog_cli.py inspect profile-clear-2d-illustration
python scripts/catalog_cli.py inspect domain-realization-anthropomorphic-animal-baseline
python scripts/catalog_cli.py inspect style-family-clear-portrait
```

When a non-bundled pack is explicitly selected, inspect only IDs returned by the current catalog query or recommendation response:

```bash
python scripts/catalog_cli.py inspect <record-id-from-current-results>
```

Do not copy optional-pack IDs into core documentation or tests as permanent examples. Read the complete canonical record before prompt assembly.

## 7. Adapt by function

### Universal aesthetic core

Extract the relevant appeal, hierarchy, viewer relationship, shape rhythm, tactile taste, color-light strategy, and finish hierarchy. Keep the art direction authoritative.

### Domain realization

Translate the core and art direction into the subject's real expressive and structural channels. Do not carry channels from another domain.

### Concrete style family

Apply its line, form, shadow, highlight, color, surface, background, and detail systems together. Use the overlay for the active subject domain.

### Rendering profile

When no concrete family is selected, apply the profile's line, value, surface, light, background, and detail grammar. With a selected family, use the linked profile as the medium envelope and scoped negative boundary.

### Atomic module

Use only the visual decision it solves. Do not import unrelated scene or identity details.

### Base scene or recipe

Consult scene and recipe candidates while developing the staging or a repeatable production method. Choose a fitting record within the user's anchors, then inspect and adapt its complete relationships.

## 8. Build the modular production specification

For a simple brief, keep the specification compact. For exact poses, interactions, character sheets, or series consistency, record the relevant identity, fashion, body geometry, left and right hand placement, leg placement, head and gaze, prop contact, scene, camera, lighting, and visual-language modules. Read `references/production-specification.md`.

The modules are optional and chainable in function. Include only the controls required by the image, then translate the reviewed specification into one coherent natural-language prompt.

## 9. Assemble one prompt

A useful order is:

```text
subject and identity
→ performance and relationship
→ pose, support, and contact
→ composition and camera
→ environment and light
→ medium, shape, surface, color, and finish
→ critical construction constraints
```

Do not paste every retrieved record. Integrate selected knowledge into one coherent art brief.

## 10. Review the likely picture

Check:

- user anchors
- image intent
- center of appeal
- subject-domain validity
- gaze and relationship
- anatomy or body-plan coherence
- support and contact
- composition and crop
- medium integrity
- surface and material logic
- color and light
- detail hierarchy
- accidental preset narrative

## 11. Assemble scoped negatives

Follow `cpb-resource:negative-policy` resolved from the explicitly selected provider.

Judge bundle applicability against the pose, subject anatomy, and framing, never against the drafted prompt text. A structure the pose implies activates its bundle even when the prompt forgot to write it; drop a bundle only when the structure is affirmatively out of frame, occluded, or absent.

Activate only:

- general hygiene
- relevant visible-structure bundles
- selected profile medium boundaries
- concrete corrections
- explicit user exclusions

Keep scene failures, atomic misreadings, realization boundaries, and archetype diagnostics as review data.

## Multiple subject domains

A scene may contain more than one domain, for example a human with an ordinary animal, or a robot holding a plant-like creature. In that case:

- maintain one shared image intent and art direction
- apply one domain realization to each materially different subject domain
- coordinate scale, support, contact, and focal hierarchy across them
- select one rendering profile for the whole image unless the user requests a deliberate mixed-medium construction

## Empty results

An empty category or core list is valid. The catalog is a support system, not a quota. Use the agent's own art direction rather than lowering standards until an unrelated record appears.

## Localized identity details

When a brief or reference includes scars, tattoos, notches, claw damage, wrinkles, calluses, wear, or comparable identity features, read `references/distinctive-detail-specification.md`. Search the `distinctive-detail` module category, inspect selected records in full, and copy the measurable placement and construction into `subjects[].distinctive_details` in the production specification.
