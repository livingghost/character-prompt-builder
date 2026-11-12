---
name: character-prompt-builder
description: Create image prompts, scoped negatives and canonical references for humans, animals, anthropomorphic animals, creatures, monsters, hybrids, robots and androids. Use for character generation or illustration; editing an existing image to replace clothing, objects, backgrounds or lighting; prompt writing, assessment, revision, translation, expansion or variation; OCs, fursonas, mascots, VTubers, worlds, themes, personalities, casts, relationships and narratives; recurring-character continuity; prompt-facing SVG or verified model-facing references; and state-aware image series involving identity, emotion, relationships, environment, wardrobe, inventory, time, injury, transformation or off-screen events. Trigger on sparse or detailed briefs in any language, even without the word prompt. Work with any image model or service.
---

# Character Prompt Builder

Art-direct the commissioned depiction.

Use English prompts/retrieval and the user's language. Preserve meaning, modifier scope, relationships, negation and ambiguity without language word lists.

## Mandatory execution environment

`<skill-root>` is this installed `SKILL.md`'s absolute directory. Run scripts in its complete locked environment:

```bash
uv run --project <skill-root> --locked python <skill-root>/scripts/check_dependencies.py
```

The first invocation synchronizes packages. Add `--capability sheet` for fonts or `--capability temporal-media` for FFprobe. Resolve requirements under [Dependencies](DEPENDENCIES.md).

Run documented `python scripts/<name>.py ...` commands as `uv run --project <skill-root> --locked python <skill-root>/scripts/<name>.py ...`. Keep the Studio working directory: `--project` selects the skill environment without changing argument paths. Execute returned `argv` as given; it retains the interpreter and absolute script path. Use this environment for every route.

## Core contract

Saved work reads [Production direction](references/runtime/production-direction.md) and applicable runtime guidance through the [route reader](#artifact-bearing-production-gate). Convey actions, states, relationships and designs as meaningful wholes with their relevant detail. Specialist knowledge answers the construction question. Preserve exact requirements and purposeful detail. Judge chosen means against the commission, including when a renderer obeys them. A draft commands its renderer, not its reviewer; plans and criteria grant no authority. Construct the intended depiction, choose suitable means and complete the work. Omissions grant no permission or exclusion.

Resolve open choices within the requested work through the [conception study](references/runtime/production-direction.md#form-a-prompt-from-an-idea). Character design can be the work itself. Assess actual alternatives; use selected-target evidence for model-dependent means. A portable proposal proves no model effect.

Preserve anchors and applicable adopted definitions. Record changes and reasons at their owners; resolve open choices within delegated scope. Keep creator portrayal intent distinct from facts and psychology across outputs.

Bind inputs, target and count to actual authorization. Distinguish direction, editing, submission, selection and canonical adoption. Continue within delegated scope without repeated approval.

Preserve supported production knowledge at full specificity across every genre and intensity level, from everyday and wholesome subjects to sensitive material such as violent, medical, grotesque, body-altering, or adult knowledge, without exception. Read [Prompt Knowledge and Execution Boundary](references/prompt-knowledge-boundary.md) when relevant.

Use ASCII punctuation in Studio text, prompts, JSON and examples.

Keep judgment and automation separate. The agent owns meaning, ambiguity, direction, visual authority, composition and review. Scripts own state, retrieval, validation, materialization, dependency checks, verification and dispatch. Do not force unresolved meaning into keywords. Use scripts with documented activation, inputs, outputs, failures and tests. Resolve paths from installed `SKILL.md`.

Prompts establish the depiction, necessary premises and reference use. The model receives actual input; carry necessary meaning from authoring-only sources in text. Keep out-of-scope authoring decisions, internal keys, paths, provenance and assessment in their records; depicted names and codes remain content.

Use the optional [competing-realization test](references/runtime/prompt-composition.md#competing-realization-test) when it can resolve a consequential uncertainty. [Observe the artifact first](references/runtime/production-review.md#observe-before-interpreting), then assess its criteria; disclose review limits and keep inconclusive evidence indeterminate.

## Rendering and model controls

Image work selects feature `render-contract`: [Rendering and controls](references/runtime/render-contract.md).
Select the operation. Add a rendering declaration for authored rendering choices; other choices may remain with the model. Preserve actual selected constraints at their scopes.
Keep presentation and subject identity separate. Use scoped overrides for mixed media; never invent body or age changes from a finish.
Use complete selected-model `prompt_input`, use-case guidance and author preferences. Saved work receives these through its route; unlisted targets use acquired provider evidence.
An authored rendering declaration binds its prompt span in `render_intent`. Use the selected Production Specification when it owns that intent; an ordinary editable delivery can own the span directly.
A Generation Package uses `generation-package` (automatic for dispatcher), with its exact interface profile and mode-valid controls. Record unlisted targets under [Image Generation](references/runtime/image-generation.md#choose-execution). `image_input` binds references and exact external requests; edits add [Semantic instruction editing](references/runtime/semantic-instruction-edit.md). [Model evidence](references/runtime/model-evidence.md) owns schemas, trials, profiles, suitability and failure diagnosis.
Put execution values in declared controls, not prompt prose. Image shape and framing remain depiction choices. Resolve required scalar recommendations with provenance; choose within ranges. Display unavailable controls without sending them.
Display the rendering choice and complete verified request before submission. Use its named provider; never substitute engines.
For model, prompt, reference or post-completion changes, follow [Variation](references/runtime/production-variation.md) from the source run. Preserve independent branches and earlier results.

## Knowledge use and retrieval records

Investigate unresolved construction or wording with relevant sources. Use knowledge by meaning and scope; neither both lookup systems nor a query per visual attribute is required.

`prompt_input` selects the mode. `tag-based` requires real [dictionary search](references/runtime/prompt-vocabulary.md#select-wording-for-a-tag-based-model), even for familiar terms or prose-capable models. Prefer existing terms or close synonyms that preserve meaning, scope and degree; after comparing candidates, retain authored wording when needed. `descriptive` needs lookup only for unresolved questions; `unresolved` stays portable pending evidence; `none` has no text surface. Missing dialect metadata never implies descriptive input.

Record actual investigations, inspect complete selected records, and settle each as adopted, composed or unused under [Prompt-only Core](references/runtime/prompt-only-core.md#saved-prompt-artifacts). Composed wording may use inspected knowledge. Failed necessary retrieval stays unresolved; never fabricate evidence.

Construction questions may be empty; tag renditions need a searched vocabulary selection. Add image-supported wording to its owning resource without session history or run parameters.

## Mandatory runtime activation gate

Before prompt, reference, sheet, generation or visual-state series work (not persona or story drafting), run `python scripts/pack_cli.py ready`. For an explicit runtime, supply `--state-file`, `--cache-dir` and `--managed-root` together before `ready`; repeated `--pack-root` options add discovery roots for that invocation. It initializes state once, preserves existing choices, lists active packs and maintains their browser catalog.

- Exit 0: retrieval can proceed. Tell the user each `warning:` line.
- Exit 1: each `decide:` line is the author's decision and names the command that settles it. Put new or unusable packs to the user before continuing; never continue on bundled commons alone while a discovered pack awaits that decision. Run the command the author chooses, then `ready` again. A pack the author disabled stays disabled and is not asked about again.
- If the enabled packs change after retrieval has begun, discard the earlier results and restart from the image intent.

## Artifact-bearing production gate

Saved work reads through its draft action or `python scripts/execution_routes.py read ROUTE --operation OPERATION --execution EXECUTION --root STUDIO` with applicable features and `--model MODEL [--service SERVICE]`, `--model-file FILE` or `--dialect ID`. Read [operation contracts](references/runtime/production-execution.md) and specialists. Inspect the index; read `body` through `actions.all` or sections, following `actions.continue` and `actions.next` until `reading.record` exists. Null continuation is not completion. `--known-reading` reuses complete current context; fresh contexts reread. Delivery is not comprehension.

`draft-inputs` supplies editable files and `authoring_guide`; `explain-inputs --root STUDIO --choices FILE` locates contracts and filled examples. Edit the owning files. Use `save --choices FILE` for text (`--draft` if unfinished), or `prepare --choices FILE` for images. `status` locates sources and actions; `build-inputs` exports when needed.

## Choose a runtime path

Conversation-only prompts read no route: read [Prompt-Only Core](references/runtime/prompt-only-core.md) and applicable links directly. Select routes and features as needed:

- worlds, themes, agents or narratives: route `development`, [Creative Development](references/runtime/narrative-development.md) and [Project Design](templates/narrative/design/design-template.md); for individualized behavior, feature `persona` and the complete [Persona Template](templates/narrative/personas/persona-template.md);
- cast admission, a recurring unnamed participant, or how much of a person a scene needs: route `development`;
- reusing reviewed scene persona material: feature `scene-persona`;
- any chosen story moment, concurrent states or a depiction between recorded events: route or feature `story-context`;
- grounded continuity, state provenance or bounded consumer views: route `world-realization` or feature `world-view`; reusable identity patterns: feature `portrayal-principles`;
- creator portrayal aims and identity: feature `authorial-intent`, [Authorial Intent](references/runtime/authorial-intent.md); individualized voice or body: route or feature `performance`, [Character Performance](references/runtime/character-performance.md);
- persistent world or narrative files, or scene-derived plots: feature `narrative-files`;
- ordinary prompt-only work with no selected reference and no complex construction risk: route `prompt-only`; feature `subject-domain`, [Subject Domain](references/runtime/subject-domain-quick-reference.md), only when the subject domain is unresolved;
- complex multi-axis prompt composition: route `composition`, [Composition](references/runtime/prompt-composition.md);
- open expressive choices, a sparse brief, or difficult purpose, activity, relationship, or theme retrieval: feature `sparse-retrieval`, [Discovery](references/runtime/sparse-discovery.md);
- craft knowledge for open axes or an observed failure: feature `craft-consultation`, [Craft consultation](references/runtime/craft-consultation.md);
- terminology lookup, alternate wording or category browsing: feature `vocabulary`, [Vocabulary](references/runtime/prompt-vocabulary.md);
- final prompt rendition, ordering, weighting, LoRA notation, negative syntax or term comparison: feature `prompt-dialect`, [Writing Guide](references/runtime/prompt-writing-guide.md);
- linked evidence, or a prompt plus references without generation: route `reference-artifacts` or feature `references`;
- model-facing reference transports: feature `reference-delivery`;
- generation or model transport: route `generation` plus the feature for exactly one of `gpt-image`, `midjourney` (and Niji), `sdxl` (and ComfyUI), `novelai`, `grok`, `instruction-edit`, or `unlisted-interface` for any other image interface;
- continuity, temporal state, off-screen events, cross-scene identity, or an arriving shot-request: route or feature `state-series`;
- several images at once, across models or as concurrent variants of one model: route `batch`;
- accepted characters in a new pose or shared scene, including staged asset creation: route `repose`;
- deterministic editing of pinned stills: feature `image-edit`; user-requested semantic replacement of clothing, objects, environment or other depicted content: feature `semantic-instruction-edit`, [Semantic instruction editing](references/runtime/semantic-instruction-edit.md); masks when needed: feature `scene-mask-planning`;
- enlarging a finished image: route `upscale`; offer enlargement when its intended use needs more resolution;
- canonical identity, a character sheet, its panels, candidates or reference board: route `character-sheet`, [Sheet fills](references/runtime/sheet-fill-workflow.md); a new pose or scene for an accepted character uses `repose` or `generation` instead;
- sheet, iteration, or accepted-image work, which lives in a studio: feature `studio` first;
- an iteration's scene or slot correction: feature `studio-placement`;
- explicit selection for a canonical owner: route or feature `adoption`;
- artifact review: feature `evidence-review` and Production direction; changes: route `revise` or feature `revision-guidance`;
- reports or evidence studies: feature `evidence-review`; originals, host trials or repair hypotheses: feature `source-material`, `agent-evaluation` or `repair-analysis`;
- public state or shot interchange: feature `protocol-exchange`;
- absent pack state, custom packs, or a resource conflict between packs: feature `pack-runtime`.

Select specialist knowledge for a consequential construction question: `geometry` for exact multi-subject geometry, crop, perspective, overlap, or contact; `body-plan` for the declared construction of non-human or unfamiliar bodies, transformations, or feature counts; `recurring-identity` for a recurring character's identity contract; `performance-language` for subtle emotion, body language, appendage acting, physiological response, or mechanical performance; `garment-growth` for garment construction, growth, grooming and localized identity, including hair, fur, feathers, quills, fibers, nails, claws, hooves and digit plates; `production-spec` for scene artifacts; `finishing` for a named or implied rendering medium, photographic look, 3D or toy presentation, in-image type or logo, environment-forward composition, or repeated wrong-finish results; `visual-evidence` for derived visual evidence, linked SVGs, or corpus ingestion.

[Weighting grammar](references/runtime/prompt-weighting.md).

## Mandatory studio gate

Saved deliverables, sheets and recorded generation use [Studio Runtime](references/runtime/studio.md). Conversation-only answers need no Studio. If `python scripts/session_entry_points.py` reports none, run `studio.py init` before authoring.

For dispatcher API keys, read and follow [Studio authentication](references/runtime/studio-authentication.md) for source choice, preparation, owner input, readiness and recovery. Key availability and submission authority are separate.

Use managed attempts in [Sheet fills](references/runtime/sheet-fill-workflow.md). Apply HTML edits with `sheet_workflow.py apply-edit`. Record answers with `work_ledger.py respond`, reopen the indicated step, and suspend/resume when switching tasks. `studio.py status` or `sync` reconstructs views without repeating generation.

After story revisions, update Studio sources and run `studio.py sync` for the automatic Flow and Graph (`narrative-files`). Compare passages for meaning; structural checks do not judge story quality.

## Common runtime sequence

Follow [Common runtime sequence](references/runtime/production-workflow.md) for images. Start with `draft-inputs` and its read action, then `next_action` and phase context. Edit choices; scripts derive paths, repeated values and receipts. Views supply no judgment.

## Identity and scene-state authority

A category name proposes; only the author's declaration decides. Species, domain, and material supply no default. Examples are not anatomy, symmetry, clothing, or reference-view checklists. Permanent identity owns only the adopted design.

Use [Declared Structures Runtime](references/runtime/declared-structures.md) for structural contracts. Missing, absent, unknown, and occluded differ; validation checks declared topology, not typical anatomy.

Scene-specific character state is an open class: any visible or performance-relevant property that can change without changing identity, unless an approved Identity, Era, Form, or Appearance Contract owns it. A rendered reference does not promote state into identity. Review identity drift separately from source-state leakage.

## Catalog and pack runtime

Use one runtime for retrieval, planning, preparation and verification. Use `recommend` for expressive scope, `search`/`inspire` for known needs, and `batch` for queries. Read records/assets with `inspect-many` or `inspect` plus `asset-lookup`. Run catalog CLI calls sequentially.

## Visual Reference Activation Gate

Create reference artifacts only for selected sources. Declare authority, subject uses and exclusions under [Visual Reference Activation and Transport](references/visual-reference-activation-and-transport.md). Use one ordinary Reference Use Plan for packs and one canonical prepared set for shared image inputs. Sheets supply selected identity scope. Treat every selected SVG as bounded evidence, not as the whole requested image. Preparation rechecks the same skill environment before rasterization or board composition; failure blocks preparation.

## Output contract

Return the requested assessment or artifact in its requested form. World, persona and narrative artifacts retain their actual design status. Prompt delivery contains the prompt and any requested or supported negative channel. Add settings or reference artifacts when the handoff needs them. Without a named parser, use portable wording and no interface-specific weights unless requested. Omit empty placeholders.

Deliver actual selected reference files under [Prompt Artifact References](references/runtime/reference-prompt-artifacts.md). A file path or hash is not delivery.

## Maintenance and release

- core checks: [Testing](references/maintenance/testing.md);
- records, taxonomy or evidence: [Preset Maintenance](references/maintenance/presets.md);
- search profiles and retrieval evaluation: [Search Discovery](references/maintenance/search-discovery.md);
- pack creation, installation, updates, removal, locks or lifecycle: [Pack Maintenance](references/maintenance/packs.md);
- publication gates: [Release Validation](references/release/validation.md).

Reference-free prompt-only work reads no maintenance, pack-release, release-validation, state-aware or unselected-model material.

## Resource handling

Read complete material by default. Follow [Resource handling](references/resource-handling.md).
