# Preset Workflow

Use this workflow to retrieve, inspect and apply knowledge for the depiction
being developed under
[Production direction](runtime/production-direction.md#choose-the-expression).
That owner governs creative choices, interaction and
[whole-depiction judgment](runtime/production-direction.md#observe-and-repair).
[Craft consultation](runtime/craft-consultation.md) connects selected knowledge
to a saved specification and its review.

## Contents

- [Choose the retrieval path](#choose-the-retrieval-path)
- [Express the craft question](#express-the-craft-question)
- [Read layered inspiration results](#read-layered-inspiration-results)
- [Apply record roles correctly](#apply-record-roles-correctly)
- [Inspect every selected ID](#inspect-every-selected-id)
- [Adapt by function](#adapt-by-function)
- [Record and use the contribution](#record-and-use-the-contribution)
- [Assemble scoped negatives](#assemble-scoped-negatives)
- [Multiple subject domains](#multiple-subject-domains)
- [Empty results](#empty-results)
- [Localized identity details](#localized-identity-details)

## Choose the retrieval path

Discover knowledge before choosing an unresolved presentation or expressive
relationship. Detailed subject requirements can leave those choices open.
Use focused lookup for a known craft need. Neither path requires known record
names or IDs.

Let the current depiction and its unresolved question determine what knowledge
to seek. Search a relationship or technique where that is the need; separate
features only when their distinction matters. An intelligible activity, state
or relationship can remain expressed at that level. Retrieved knowledge can
develop an open choice or reveal a reason to reconsider it within the same
production direction.

```bash
python scripts/catalog_cli.py recommend \
  "whole object detail relationship" \
  --limit 8
```

Recommendation returns query evidence, candidate knowledge, a scoped catalog
inventory and optional dictionary categories. Inspect applicable candidates,
then choose or author a construction that serves the purpose. A search result
does not supply an adopted direction.

Read `references/runtime/sparse-discovery.md` for discovery and modifier scope.
Read `references/maintenance/search-discovery.md` for index authoring, grouping
and retrieval evaluation.

## Express the craft question

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

## Read layered inspiration results

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

Curated concrete drawing grammars. Select zero or one when the art direction needs a specific line, form, shadow, highlight, color, surface, background, and detail system. Inspect the complete family and apply the overlay matching the subject domain. The linked render profile supplies the medium envelope and scoped negative boundary.

### `domain_realizations`

Curated translation knowledge for the exact subject domain. Use the selected matching realization to convert the direction into valid identity, anatomy or body plan, expression or behavior, surfaces, locomotion, contact, and environmental interaction.

### `render_profiles`

Curated medium grammars. Select at most one that fits.

### `subject_archetypes`

Identity contracts: stable morphology, palette, connected marking logic, proportions, and identity equipment for a recurring subject. Adopt a matching archetype, or diverge from it deliberately; when adopted, its identity constraints carry `automatic_prompt_injection: true` and belong in the prompt. Consult these before designing colors and markings from a blank page. Follow the [Reference Cluster Mapping Contract](maintenance/presets.md#reference-cluster-mapping-contract) and, when provided, read `cpb-resource:reference-cluster-mapping` for mappings to that pack's records.

### `categories`

Atomic candidates from the requested categories. The default `any` retrieval includes both curated and vocabulary roles.

Use `search --kind scene` for base scenes and `search --include-recipes` for
finished recipes. Retrieve scenes when spatial staging matters; a flat graphic
needs no invented scene requirement. Normal `search` output groups related
variants under one representative. Use `--ungrouped` for exact inventory or
deliberate variant comparison.

## Apply record roles correctly

### Curated

Use as complete production knowledge for its defined scope. Preserve its relationships and adapt them to the current direction.

### Vocabulary

Use for names and model-legible phrasing. Supply staging, light, interaction, and medium from the art direction and curated records.

Use `--tier curated` only when the unresolved question requires a complete blueprint. Use `--tier vocabulary` only for a naming or option question.

## Inspect every selected ID

Recommendation and search output are discovery excerpts. User-facing discovery does not require IDs, but every internally selected record must be inspected before adoption.

```bash
python scripts/catalog_cli.py inspect <record-id-from-current-results>
```

The bundled commons pack is sufficient for copy-paste inspection examples across a render profile, domain realization, and concrete style family:

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

## Adapt by function

### Universal aesthetic core

Extract the relevant appeal, hierarchy, viewer relationship, shape rhythm, tactile taste, color-light strategy, and finish hierarchy. Keep the art direction authoritative.

### Domain realization

Translate the core and art direction into the subject's real expressive and structural channels. Do not carry channels from another domain.

### Concrete style family

Apply its line, form, shadow, highlight, color, surface, background, and detail systems together. Use the overlay for the active subject domain.

### Render profile

Without a concrete family, apply its line, value, surface, light, background, and detail grammar. With one, use it as the medium envelope and scoped negative boundary.

### Atomic module

Use only the visual decision it solves. Do not import unrelated scene or identity details.

### Base scene or recipe

Consult scene and recipe candidates while developing the staging or a repeatable production method. Choose a fitting record within the user's anchors, then inspect and adapt its complete relationships.

## Record and use the contribution

Preserve the relationships borrowed from inspected knowledge and their useful
application in the existing
[Production Specification](production-specification.md). Its shared subjects,
whole-artifact arrangement and local depictions hold the required construction;
the optional `layout` owns distinct regions and their reading relationships.
Geometry, camera and lighting belong where the depiction needs them. Modules
are optional and chainable in function; use the precision needed by the
selected relationship and explicit requirements.

Integrate the contribution into the authored depiction. An inspected record
can supply a complete technique, one relevant relationship or fitting wording;
its fields and examples do not each require an emitted clause. Use the
[Prompt Writing Guide](runtime/prompt-writing-guide.md) to carry that meaning
into the actual interface. Retain the user's fixed anchors and the complete
identity and construction detail needed by the image.

Apply [Production direction's judgment](runtime/production-direction.md#observe-and-repair)
to the contribution in the whole depiction. Its intended use and actual effect
can differ. Keep the record's adaptation rules and diagnostics available for
the question being assessed, including any unrelated identity, setting or
narrative imported with its useful technique. A successful lookup alone
establishes neither a successful application nor an observed image result.

## Assemble scoped negatives

Follow `cpb-resource:negative-policy`.

Judge bundle applicability against the pose, subject anatomy, and framing, never against the drafted prompt text. A structure the pose implies activates its bundle even when the prompt forgot to write it; drop a bundle only when the structure is affirmatively out of frame, occluded, or absent.

Activate only:

- general hygiene
- relevant visible-structure bundles
- the render profile's medium boundaries
- concrete corrections
- explicit user exclusions

Keep scene failures, atomic misreadings, realization boundaries, and archetype diagnostics as review data.

## Multiple subject domains

A scene may contain more than one domain, for example a human with an ordinary animal, or a robot holding a plant-like creature. In that case:

- maintain one shared image intent and art direction
- apply one domain realization to each materially different subject domain
- coordinate scale, support, contact, and focal hierarchy across them
- apply rendering knowledge at the scopes selected in the [render intent](runtime/render-contract.md)

## Empty results

An empty category or core list is valid. The catalog is a support system, not a quota. Use the agent's own art direction rather than lowering standards until an unrelated record appears.

## Localized identity details

When a brief or reference includes scars, tattoos, notches, claw damage, wrinkles, calluses, wear, or comparable identity features, read `references/distinctive-detail-specification.md`. Search the `distinctive-detail` module category, inspect selected records in full, and copy the measurable placement and construction into `subjects[].distinctive_details` in the production specification.
