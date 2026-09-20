---
name: character-prompt-builder
description: Create image prompts, scoped negatives and canonical references for humans, animals, anthropomorphic animals, creatures, monsters, hybrids, robots and androids. Use for character generation or illustration; prompt writing, revision, translation, expansion or variation; OCs, fursonas, mascots, VTubers, worlds, themes, personalities, casts, relationships and narratives; recurring-character continuity; prompt-facing SVG or verified model-facing references; and state-aware image series involving identity, emotion, relationships, environment, wardrobe, inventory, time, injury, transformation or off-screen events. Trigger on sparse or detailed briefs in any language, even without the word prompt. Work with any image model or service.
---

# Character Prompt Builder

Keep world, subjects, themes and expression coherent. For images, act as an art director: produce one coherent executable image, not a preset list.

Use English prompts/retrieval and the user's conversational language. Translate whole meaning, including modifier scope, relationships, negation, and unresolved wording; never use per-language word lists.

## Exact reference transport

When preparing model-facing references, read [Exact Reference Delivery](references/runtime/reference-delivery.md). Select explicit authority scopes, then derive the prompt mapping from the actual attachment order or single-board pixel regions. Do not equate reference count with attachment count or freeze transient state as identity.

## Inspectable outcomes

For a production review or an evidence study, read [Evidence Review](references/runtime/evidence-review.md). Export the existing run's pinned inputs, exact consumer, all candidates and judgments; do not create a parallel production ledger. Evaluate technical, behavioral and expressive outcomes separately, keep unobserved evidence missing, and distinguish actual use from constructed tests. A report grants no execution or adoption authority.

## Preserved authoring and observed evaluation

Use [Source Material](references/runtime/source-material.md) to preserve existing
originals and create citation-bound extraction proposals, never automatic canon.
Use [Agent Evaluation](references/runtime/agent-evaluation.md) for explicitly
confirmed host trials and [Repair Analysis](references/runtime/repair-analysis.md)
for evidence-backed revision hypotheses over existing reviews. Runtime evidence,
creative assessment and authorization are distinct. Each works with local resources
or explicitly supplied public artifacts; no other application is assumed.

## Core contract

Identify the artifact, purpose, user anchors, creative space and material ambiguity. For scene preparation, read applicable persona and design in full; preserve the relevant definition text and scoped application in [Scene Persona Material](references/runtime/scene-persona.md). For execution or local repair within that reviewed scope, verify and reuse the prepared material instead of repeating preparation. Reopen when originals or applicable conditions change. Choose the expression and verify it on the actual artifact.

Clarify material ambiguity; otherwise choose a direction or requested alternatives, never an incompatible average.

Never alter an anchor silently. Disclose each modification and its reason. Assumptions fill open space; modifications change intent. Keep creator portrayal intent separate from facts and psychology; apply it across outputs.

The user owns acceptance and delegation. Bind the exact input, target, count and quoted cost to actual authority; distinguish direction, edits, submission, selection and canonical adoption. Act within explicit delegation without repeated unnecessary approval, and stop outside it. Observe actual outputs, distinguish intended from observed effects, and revise only within the authorized scope.

Preserve supported production knowledge at full specificity across every genre and intensity level, from everyday and wholesome subjects to sensitive material such as violent, medical, grotesque, body-altering, or adult knowledge, without exception. Read [Prompt Knowledge and Execution Boundary](references/prompt-knowledge-boundary.md) when relevant.

Use plain ASCII punctuation in project documents, prompts, JSON text, and packaged examples. Do not emit the Unicode em dash.

Keep judgment and automation separate. The agent owns meaning, ambiguity, intent, direction, visual authority, composition and review. Scripts own deterministic state, cache, retrieval, resolution, validation, materialization, dependency preflight, verification and dispatch. Never force unresolved meaning through keywords or duplicate script work. A script is usable only when routed documentation exposes activation, input, output, help or example, failures, and a regression test. Resolve paths from the installed `SKILL.md` directory, not the working directory.

## Mandatory retrieval-before-composition gate

This gate governs image prompts, not prose or brainstorming. Never hand-compose prompt wording before retrieval has been attempted. Wrong or competing tags can cancel requested content. Prefer suitable proven phrasing across every domain.

1. For every distinct visual element (pose, action, expression, camera, lighting, wardrobe, body feature, effect, and any specialized domain), first search the catalog (`catalog_cli.py search`, then `inspect` on the closest record) and, for tag-level wording, the prompt vocabulary (`pack_cli.py resource prompt-vocabulary` plus `search_prompt_vocabulary.py`).
2. Record the lookups as they are made: one entry per element with its search strings, the records or vocabulary terms inspected, and whether the wording was adopted or composed. Every generation builder and verifier requires the settled record, bound to the authored prompt and approved plot. Draft artifacts retain the actual lookup record, or an explicit unavailable reason; never fabricate retrieval or approval.
3. Compose new wording only when retrieval finds nothing suitable. Prefer concise proven phrasing, check competing terms over the same region, and disambiguate words that could instead name gear or camera direction. [Prompt-Only Core](references/runtime/prompt-only-core.md) gives the wording checks.
4. When a newly composed phrase is confirmed effective in a finished image, add the proven phrase back to the owning pack resource (dictionary entry or module record), as terms and wording only, with no session history, seeds, or run parameters. Keep the pack as the single source of proven wording.

## Mandatory runtime activation gate

Resolve the pack runtime before prompt, reference, sheet, generation or visual-state series work, not persona or story drafting. This is a precondition, not maintenance.

1. Determine whether the invocation supplies an explicit pack state. If it does, use that state as the complete activation authority.
2. If no explicit state is supplied, check for the persistent user state at `~/.character-prompt-builder/pack-state.json`.
3. Without either state, read [Pack State Runtime Quickstart](references/runtime/pack-state-quickstart.md), then run `python scripts/pack_cli.py state-init` once before retrieval to persist all discovered valid packs and report their status. Preserve existing explicit or persistent states, including deliberate disabling; the core-only release seed is not first-use activation policy.
4. Surface `disabled_discovered_packs` before continuing; file presence does not enable a pack. Do not silently default to bundled commons when other discovered packs are disabled.
5. Enable the packs required for the intended capabilities and select any required logical-resource providers. Finish activation before `recommend`, `search`, `inspire`, `inspect`, `asset-lookup`, reference planning, or generation.
6. If pack or provider activation changes after retrieval has begun, discard the earlier retrieval and restart from the image intent under the new resolved state. Use that one resolved state through catalog, planning, materialization, packaging, generation, and verification.

Archive presence does not activate packs.

## Artifact-bearing production gate

For saved deliverables and multistep production, read [Production Execution](references/runtime/production-execution.md). Resolve the selected route with `scripts/execution_routes.py inspect ROUTE` and explicit `--feature` flags. Its manifest owns mandatory and conditional reads; read the actual selected material, not just the manifest.

Open a work task. Use `scripts/production_workflow.py` to prepare the exact sources and delivery, hand off bounded inputs, capture the actual artifact, record observations against it, select a reviewed candidate, and complete. Run `status` or `resume` before continuing after an interruption. Changed inputs require new preparation; never rewrite evidence hashes to preserve an earlier pass. An uncertain submission result requires checking the run record before any retry.

A completion receipt binds actual files and decisions, not model comprehension or user consent. Finish the work ledger only with that receipt. Expose actual output status, remaining uncertainties and the files themselves. Delivery selection does not adopt canon. For manual or conversation generation, record the handoff without claiming control of the external model call.

## Choose a runtime path

Activate selectively:

- worlds, themes, agents or narratives: [Creative Development](references/runtime/narrative-development.md) and [Project Design](templates/narrative/design/design-template.md); for individualized behavior, read the complete [Persona Template](templates/narrative/personas/persona-template.md);
- any chosen story moment, concurrent states or a depiction between recorded events: [Story Context](references/runtime/story-context.md);
- grounded continuity, state provenance or bounded consumer views: [World Realization](references/runtime/world-realization.md); reusable identity patterns: [Portrayal Principles](references/portrayal-principles.md);
- creator portrayal aims and identity: [Authorial Intent](references/runtime/authorial-intent.md); individualized voice/body: [Character Performance](references/runtime/character-performance.md);
- ordinary prompt-only with no selected reference and no complex construction risk: [Prompt-Only Core](references/runtime/prompt-only-core.md); use [Subject Domain Quick Reference](references/runtime/subject-domain-quick-reference.md) only when the subject domain is unresolved;
- deterministic editing of pinned stills: [Image Editing](references/runtime/image-editing.md); preserve the current contract or use the reviewed child-run path when authoring inputs change;
- complex multi-axis prompt composition: [Prompt Composition Runtime](references/runtime/prompt-composition.md);
- sparse brief or difficult emotion, activity, situation, relationship, or theme retrieval: [Sparse-Brief Discovery Runtime](references/runtime/sparse-discovery.md);
- terminology lookup, alternate wording, or category browsing after the image direction is understood: [Prompt Vocabulary Runtime](references/runtime/prompt-vocabulary.md);
- final prompt ordering, tag separation, attention weighting, LoRA notation, negative syntax, or controlled term comparison for a selected interface: [Prompt Writing Guide Runtime](references/runtime/prompt-writing-guide.md); resolve the model's family first with `scripts/prompt_dialect.py`;
- linked evidence or prompt plus references: [Prompt Artifact Reference Runtime](references/runtime/reference-prompt-artifacts.md), without generation or series state;
- generation or model transport: [Image Generation Runtime](references/runtime/image-generation.md) plus exactly one of [GPT Image](references/adapters/gpt-image.md), [Midjourney and Niji](references/adapters/midjourney-niji.md), [FLUX](references/adapters/flux.md), [SDXL and ComfyUI](references/adapters/sdxl-comfyui.md), [NovelAI](references/adapters/novelai.md), [Grok Imagine](references/adapters/grok-imagine.md), [Instruction-Edit](references/adapters/instruction-edit.md), or the [Unlisted Image Interface](references/adapters/unlisted-interface.md);
- continuity, temporal state, off-screen events, cross-scene identity, or an arriving shot-request: [State-Aware Series Runtime](references/runtime/state-aware-series.md);
- persistent world/narrative files or scene-derived plots: [Narrative Protocol](references/narrative-protocol.md) and [Narrative Authoring](references/narrative-authoring.md);
- several images at once, across models or as concurrent variants of one model: [Batch Generation Runtime](references/runtime/batch-generation.md);
- reposing an existing character render, or same-character-new-pose and new-scene requests (select the method by the actual model interface, not a universal tag-model recipe): [Character Repose Workflow](references/runtime/character-repose-workflow.md);
- enlarging a finished image: [Upscale Adapter](references/adapters/upscale.md) with an active upscaler model record;
- creating or revising a recurring character's canonical identity, building a character sheet, filling its visual panels, accepting model-filled candidates, or preparing its reusable reference board: [Character Sheet Discipline](references/runtime/character-sheet-discipline.md), with the optional JSON review editor at [templates/character-sheet.template.html](templates/character-sheet.template.html), the raster handoff renderer at [scripts/render_character_sheet.py](scripts/render_character_sheet.py), and the candidate harvester at [scripts/harvest_sheet_render.py](scripts/harvest_sheet_render.py);
- sheet, candidate, or accepted-image work, which lives in a studio: [Studio Runtime](references/runtime/studio.md) first;
- absent pack state, custom packs, or provider selection: [Pack State Runtime Quickstart](references/runtime/pack-state-quickstart.md).

Load specialists only for a load-bearing subject:

- exact multi-subject geometry, crop, perspective, overlap, or contact: [Prompt Composition Geometry](references/prompt-composition-geometry.md) and [Camera Framing Contract](references/camera-framing-contract.md);
- recurring identity, unfamiliar body plan, ordinary animal, hybrid, creature, robot, transformation, or unusual feature counts: [Morphology and Species Contracts](references/morphology-and-species-contracts.md) and [Species Architecture](references/species-architecture.md); recurring identity also requires [Character Identity Contract](references/character-identity-contract.md);
- subtle emotion, body language, appendage acting, physiological response, or mechanical performance: [Performance Language Specification](references/performance-language-specification.md);
- garment, growth, grooming, hair, fur, feathers, quills, bristles, spun fiber, molded strands, nails, claws, talons, hooves, digit plates, or local identity: [Garment Geometry](references/garment-geometry-specification.md), [Growth Geometry](references/growth-geometry-specification.md), and [Distinctive Detail](references/distinctive-detail-specification.md);
- scene artifacts: [Production Specification](references/production-specification.md);
- a named or implied rendering medium, photographic look, 3D or toy presentation, in-image type or logo, environment-forward composition, or repeated wrong-finish results: [Finishing Layers Specification](references/finishing-layers-specification.md);
- supplied raster, linked SVG, reference collection, or corpus ingestion: [Derived Visual Evidence](references/derived-visual-evidence.md), [Visual Reference Activation and Transport](references/visual-reference-activation-and-transport.md), [Reference Corpus Ingestion](references/reference-corpus-ingestion.md), and [Visual Technique Observation](references/reference-corpus-visual-technique-observation.md).

Do not read maintenance, pack-release, release-validation, state-aware, or unselected-model documents during an ordinary reference-free prompt-only task.

## Mandatory studio gate

Persistent character production, sheets, and recorded generation live in a studio. When `python scripts/session_entry_points.py` reports none, create one (`studio.py init`) before any sheet or generation work, generate through `dispatch.py`, and follow [Studio Runtime](references/runtime/studio.md).

## Character Sheet runtime contract

Activate this branch only for canonical identity authoring, sheet filling, candidate acceptance, sheet revision, or reference-board preparation. A new pose or scene for an accepted character does not reopen it; route that through the Character Repose Workflow or Image Generation Runtime with the accepted reference board.

Follow the complete operational sequence in [Character Sheet Discipline](references/runtime/character-sheet-discipline.md): validate declarations, scaffold, fill artwork-only panels, inspect actual outputs, accept in the declared scope, and render references. Preserve renderer-owned regions; an attached reference is not a pixel edit mask. Temporary fill acceptance is not canonical adoption. Later scenes use identity evidence without importing its transient performance or wardrobe state.

## Revision and adoption scope

Use [Revision Contract](references/runtime/revision-contract.md): default to local edits, preserve unrelated baseline decisions, and separate exploration from target conversion. Scene clothing preserves identity slots; fixed wardrobe requires canonical approval. Retained draft choices are not canon. Saving a text draft does not require Studio.

## Common runtime sequence

For image work; narrative development follows its own routed sequence.

1. Form one image intent and separate anchors from creative space.
2. Choose one coherent direction; for a sparse brief, use `recommend` first.
3. Search packs only after choosing the direction. When exact English wording is missing, resolve and query the optional `prompt-vocabulary` resource; treat its results as candidates selected by the agent, never as automatic prompt expansion.
4. Inspect every selected canonical record in full.
5. Inspect complete records and asset details together with `inspect-many` (or `inspect` plus `asset-lookup`). Adopt evidence only when it has a relevant authority role.
6. Draft the plot and wording without inventing approval. A prompt-only draft may omit a plot artifact. Before preparation, present the plot for actual approval and settle retrieval against it and the authored prompt. Preparation is not permission to execute or change canon.
7. Choose a target for the draft or approved intent. Report unsupported plot requirements to the approving person; never absorb them silently.
8. Build or infer a compact semantic plan and run `scripts/validate_prompt_semantics.py` before delivery.
9. For the chosen target, select its adapter, resolve the optional `prompt-writing-guide`, and read the complete selected guide before final rendition. Apply only rules supported by the active interface; the agent chooses what is useful and never injects examples automatically.
10. Compose and review under the activated runtime document.

## Expression and actual evidence

Use [Production direction](references/runtime/production-direction.md) and
[Production permissions](references/runtime/production-permissions.md) with the production lifecycle.
Record meaningful choices, selected instructions, source scope and intentional deviations, without
requiring a genre, cast, anatomy, dramatic change or stock gesture. A static phase is not proof
of intervening motion. Review actual located evidence, then select, repair locally or remake the
necessary part under the proper authorization. Never carry a prior passing review across changed
inputs or promote delivery selection into canon.

## Identity and scene-state authority

A category name proposes; only the author's declaration decides. Species, domain, and material supply no default. Examples are not anatomy, symmetry, clothing, or reference-view checklists. Permanent identity owns only the adopted design.

Use [Declared Structures Runtime](references/runtime/declared-structures.md) for structural contracts. Declare relevant parts, preserving independent systems. Missing, absent, unknown, and occluded differ. Describe details within the relevant structure's geometry. Validate declared topology, not typical anatomy. Creative proposals neither become canon nor broaden local edits.

Scene-specific character state is an open class: any visible or performance-relevant property that can change without changing identity, unless an approved Identity, Era, Form, or Appearance Contract owns it.

A rendered reference does not promote state into identity. Review identity drift separately from source-state leakage.

## Catalog and pack runtime

Use one resolved runtime across retrieval, planning, preparation and verification; see [Pack State Runtime Quickstart](references/runtime/pack-state-quickstart.md).

`recommend` explores sparse outcomes; `search` and `inspire` retrieve known needs; `inspect` returns a complete record plus compact activation; `asset-lookup` owns asset details; `batch` loads once for several queries; `inspect-many` returns complete records and assets under one fingerprint with timing diagnostics.

Prefer one `batch` for several independent queries and one `inspect-many` for the selected records. Do not start several catalog CLI processes in parallel.

## Visual Reference Activation Gate

After any record selection, including prompt-only work, obtain asset details with `inspect-many` or `asset-lookup`. If no reference is selected, stop the reference branch without creating empty reference artifacts. If evidence is selected, declare one intended influence and one technical role per item.

Treat every selected SVG as bounded evidence, not as the whole requested image. Before prompt composition or model transport, use the linked record's meaning and the visible SVG evidence to state what to preserve, replace, add, and omit for each source. Compose identity, pose-camera, environment, outfit, prop-accessory, local-color, lighting, and surface-finish roles explicitly under [Visual Reference Activation and Transport](references/visual-reference-activation-and-transport.md); never rely on a title, filename, or vague instruction such as `use this reference`.

When a registered Character Sheet supplies identity and other registered evidence supplies pose, outfit, camera, lighting, environment, props, color, or finish, do not create a second transport package or a special Character Sheet adapter. Build one ordinary Reference Use Plan with one bounded intended influence per use. The character-sheet source owns only the declared identity role; every non-identity source remains limited by its own `controls` and `must_not_control`. If the reference board is still an unregistered supplied file, current canonical packaging cannot mix it with pack-artifact references; use the explicit catalog scope of [Adoption Workflow](references/runtime/adoption-workflow.md) to register the sheet identity first instead of pretending the two provenance paths are interchangeable.

Before rasterization or model-facing SVG preparation, run the Visual dependency preflight documented by [Image Generation Runtime](references/runtime/image-generation.md).

Authority is the intended-influence and technical-role intersection. Give each item a role, exclusions, and precedence; never create a parallel list or unnamed average. A failed check blocks execution.

## Output contract

For world, persona or narrative work, return requested artifacts with actual design status, not unsolicited prompts. For prompt work, always return the requested prompt. Return a negative prompt only when requested or supported by the target. When no target parser is named, keep the prompt portable and do not add interface-specific weighting syntax unless the user asks for that syntax.

Reference-free prompt drafts include concise provenance and no empty placeholders.

Add `reference-use-plan.json` only when references are selected or a reusable reference package is requested. Add `surface-lighting-plan.json` only when source lighting or material response needs explicit preserve, rescope, or replace authority. Add `prepared-reference-set.json` and `reference-preamble.txt` only for model-facing preparation or a transport-ready package.

When a reference is selected, return the actual file. A file path or hash is not delivery.

## Maintenance and release

Activate these documents only when changing the library or distributing the project:

- record, taxonomy, evidence, or preset work: [Preset Maintenance](references/maintenance/presets.md);
- search-profile authoring and retrieval evaluation: [Search Discovery Maintenance](references/maintenance/search-discovery.md);
- pack creation, installation, update, removal, lock, or lifecycle: [Pack Maintenance](references/maintenance/packs.md);
- core or pack publication and complete gates: [Release Validation](references/release/validation.md).

Keep maintenance outside ordinary prompt context. Rebuild metadata and run release gates. Release archives exclude caches. Development handoffs preserve Git history, settings, packs and the working index; release exclusions require approval. Never report Library storage until the completed body ZIP is uploaded and a Library listing confirms it.

For public state or shot interchange, use [Protocol Exchange](references/protocol-exchange.md). Check the installed contract, export only selected public artifacts, and verify received bundles before adoption. Complete shot lineage uses `scripts/shot_request.py --require-complete`; private narrative and production records remain in the project and are not included in the exchange.

## Resource handling

When configuring reads, imports, evaluation, review exports or execution budgets,
use [Resource handling](references/resource-handling.md). Read complete material
by default; an explicit operating budget must not silently shorten a definition
or turn incomplete evidence into success. This does not replace full Persona
preparation or the scene material's source/meaning checks.
