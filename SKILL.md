---
name: character-prompt-builder
description: Create image prompts, scoped negatives and canonical references for humans, animals, anthropomorphic animals, creatures, monsters, hybrids, robots and androids. Use for character generation or illustration; prompt writing, revision, translation, expansion or variation; OCs, fursonas, mascots, VTubers, worlds, themes, personalities, casts, relationships and narratives; recurring-character continuity; prompt-facing SVG or verified model-facing references; and state-aware image series involving identity, emotion, relationships, environment, wardrobe, inventory, time, injury, transformation or off-screen events. Trigger on sparse or detailed briefs in any language, even without the word prompt. Work with any image model or service.
---

# Character Prompt Builder

Keep world, subjects, themes and expression coherent. For images, act as an art director: produce one coherent executable image, not a preset list.

Use English prompts/retrieval and the user's conversational language. Translate whole meaning, including modifier scope, relationships, negation, and unresolved wording; never use per-language word lists.

## Core contract

Identify the artifact, purpose, user anchors, creative space and material ambiguity. Clarify material ambiguity; otherwise choose a direction or requested alternatives, never an incompatible average. Choose the expression and verify it on the actual artifact.

Never alter an anchor silently. Disclose each modification and its reason. Assumptions fill open space; modifications change intent. Keep creator portrayal intent separate from facts and psychology; apply it across outputs.

The user owns acceptance and delegation. Bind the exact input, target, count and quoted cost to actual authority; distinguish direction, edits, submission, selection and canonical adoption. Act within explicit delegation without repeated unnecessary approval, and stop outside it. Observe actual outputs, distinguish intended from observed effects, and revise only within the authorized scope.

Preserve supported production knowledge at full specificity across every genre and intensity level, from everyday and wholesome subjects to sensitive material such as violent, medical, grotesque, body-altering, or adult knowledge, without exception. Read [Prompt Knowledge and Execution Boundary](references/prompt-knowledge-boundary.md) when relevant.

Use plain ASCII punctuation in project documents, prompts, JSON text, and packaged examples. Do not emit the Unicode em dash.

Keep judgment and automation separate. The agent owns meaning, ambiguity, intent, direction, visual authority, composition and review. Scripts own deterministic state, cache, retrieval, resolution, validation, materialization, dependency preflight, verification and dispatch. Never force unresolved meaning through keywords or duplicate script work. A script is usable only when routed documentation exposes activation, input, output, help or example, failures, and a regression test. Resolve paths from the installed `SKILL.md` directory, not the working directory.

## Mandatory retrieval-before-composition gate

This gate governs image prompts, not prose or brainstorming. Never hand-compose prompt wording before retrieval has been attempted: wrong or competing tags can cancel requested content.

1. For every distinct visual element (pose, action, expression, camera, lighting, wardrobe, body feature, effect, and any specialized domain), search the catalog (`catalog_cli.py search`, then `inspect` the closest record) and, for tag-level wording, the prompt vocabulary (`pack_cli.py resource prompt-vocabulary` plus `search_prompt_vocabulary.py`). Add `--record lookups.json --element NAME` to every search and inspection; in catalog `batch` each `request_id` names its element, and in a vocabulary `--queries` object each key does.
2. Mark each element with `python scripts/prompt_retrieval.py lookups.json --element NAME --adopted ID` (repeat `--adopted` for every record used), or with `--composed TEXT --reason TEXT`. When retrieval cannot run, state the reason instead; never fabricate retrieval or approval.
3. Compose new wording only when retrieval finds nothing suitable; [Prompt-Only Core](references/runtime/prompt-only-core.md) gives the wording checks.
4. When a newly composed phrase is confirmed effective in a finished image, add it back to the owning pack resource (dictionary entry or module record) as terms and wording only, with no session history, seeds, or run parameters.

## Mandatory runtime activation gate

Before prompt, reference, sheet, generation or visual-state series work (not persona or story drafting), run `python scripts/pack_cli.py ready`, adding the task's `--state-file`, `--cache-dir` and `--managed-root` when it has them. It creates the state on first use, keeps every existing choice, and prints the packs retrieval will use.

- Exit 0: retrieval can proceed. Tell the user each `warning:` line.
- Exit 1: each `decide:` line is the author's decision and names the command that settles it. Put new or unusable packs to the user before continuing; never continue on bundled commons alone while a discovered pack awaits that decision. Run the command the author chooses, then `ready` again. A pack the author disabled stays disabled and is not asked about again.
- If a pack or provider changes after retrieval has begun, discard the earlier results and restart from the image intent.

## Artifact-bearing production gate

For saved deliverables and multistep production, read the route with `python scripts/execution_routes.py read ROUTE --root PROJECT`, adding `--feature NAME` for each applicable feature named below and, once the target is chosen, `--model MODEL`, or `--dialect ID` for a prompt family without a model record, to read only that family's guide sections. It prints [Production Execution](references/runtime/production-execution.md) and every document the route needs, then the path of the reading record to complete; `--page-bytes N` pages a long read and `--continue CURSOR` resumes it. Follow Production Execution through completion, and run `production_workflow.py status` or `resume` before continuing after an interruption.

## Choose a runtime path

Each item names a route or `--feature` whose read prints its documents. A prompt answered in conversation, with nothing saved, reads no route: it reads [Prompt-Only Core](references/runtime/prompt-only-core.md) and the linked documents that apply. Activate selectively:

- worlds, themes, agents or narratives: route `development`, [Creative Development](references/runtime/narrative-development.md) and [Project Design](templates/narrative/design/design-template.md); for individualized behavior, feature `persona` and the complete [Persona Template](templates/narrative/personas/persona-template.md);
- cast admission, a recurring unnamed participant, or how much of a person a scene needs: route `development`;
- reusing reviewed scene persona material: feature `scene-persona`;
- any chosen story moment, concurrent states or a depiction between recorded events: route or feature `story-context`;
- grounded continuity, state provenance or bounded consumer views: route `world-realization` or feature `world-view`; reusable identity patterns: feature `portrayal-principles`;
- creator portrayal aims and identity: feature `authorial-intent`, [Authorial Intent](references/runtime/authorial-intent.md); individualized voice or body: route or feature `performance`, [Character Performance](references/runtime/character-performance.md);
- persistent world or narrative files, or scene-derived plots: feature `narrative-files`;
- ordinary prompt-only work with no selected reference and no complex construction risk: route `prompt-only`; feature `subject-domain`, [Subject Domain](references/runtime/subject-domain-quick-reference.md), only when the subject domain is unresolved;
- complex multi-axis prompt composition: route `composition`, [Composition](references/runtime/prompt-composition.md);
- sparse brief or difficult emotion, activity, situation, relationship, or theme retrieval: feature `sparse-retrieval`, [Sparse Discovery](references/runtime/sparse-discovery.md);
- craft knowledge for open axes or an observed failure: feature `craft-consultation`, [Craft consultation](references/runtime/craft-consultation.md);
- terminology lookup, alternate wording or category browsing: feature `vocabulary`, [Vocabulary](references/runtime/prompt-vocabulary.md);
- final prompt ordering, weighting, LoRA notation, negative syntax or term comparison: feature `prompt-dialect`, [Writing Guide](references/runtime/prompt-writing-guide.md);
- linked evidence, or a prompt plus references without generation: route `reference-artifacts` or feature `references`;
- model-facing reference transports: feature `reference-delivery`;
- generation or model transport: route `generation` plus the feature for exactly one of `gpt-image`, `midjourney` (and Niji), `flux`, `sdxl` (and ComfyUI), `novelai`, `grok`, `instruction-edit`, or `unlisted-interface` for any other image interface;
- continuity, temporal state, off-screen events, cross-scene identity, or an arriving shot-request: route or feature `state-series`;
- several images at once, across models or as concurrent variants of one model: route `batch`;
- the same character in a new pose or scene: route `repose`;
- deterministic editing of pinned stills: feature `image-edit`;
- enlarging a finished image: route `upscale` with an active upscaler model record;
- canonical identity, a character sheet, its panels, candidates or reference board: route `character-sheet`; a new pose or scene for an accepted character uses `repose` or `generation` instead;
- sheet, candidate, or accepted-image work, which lives in a studio: feature `studio` first;
- explicit selection for a canonical owner: route or feature `adoption`;
- scoped changes or review of existing artifacts: route `revise` or feature `revision-guidance`;
- a production report or evidence study: feature `evidence-review`; preserved originals, host trials or repair hypotheses: feature `source-material`, `agent-evaluation` or `repair-analysis`;
- public state or shot interchange: feature `protocol-exchange`;
- absent pack state, custom packs, or provider selection: feature `pack-runtime`.

Add a specialist feature only for a load-bearing subject: `geometry` for exact multi-subject geometry, crop, perspective, overlap, or contact; `body-plan` for any non-human or unfamiliar body (animal, anthropomorphic animal, hybrid, creature, robot, android), a transformation, or unusual feature counts; `recurring-identity` for a recurring character's identity contract; `performance-language` for subtle emotion, body language, appendage acting, physiological response, or mechanical performance; `garment-growth` for garment, growth, grooming, hair, fur, feathers, quills, bristles, spun fiber, molded strands, nails, claws, talons, hooves, digit plates, or local identity; `production-spec` for scene artifacts; `finishing` for a named or implied rendering medium, photographic look, 3D or toy presentation, in-image type or logo, environment-forward composition, or repeated wrong-finish results; `visual-evidence` for a supplied raster, linked SVG, reference collection, or corpus ingestion.

## Mandatory studio gate

Persistent character production, sheets, and recorded generation live in a studio. When `python scripts/session_entry_points.py` reports none, create one (`studio.py init`) before any sheet or generation work, generate through `dispatch.py`, and follow [Studio Runtime](references/runtime/studio.md). Authoring whose decisions a later draft reuses lives there too, with or without images: resolve or create the studio before the first draft that will be revised or reused. A one-off answer needs none.

## Common runtime sequence

For image work:

1. For saved work, read the route (see the production gate). Form one image intent, and separate anchors from creative space.
2. Develop one coherent direction; for a sparse brief, run `recommend` first.
3. Retrieve under the gate above; consult craft (feature `craft-consultation`) before settling open axes or after an observed failure. Inspect every selected canonical record in full. Inspect complete records and asset details together with `inspect-many` (or `inspect` plus `asset-lookup`). Adopt evidence only when it has a relevant authority role.
4. Draft the plot and wording without inventing approval; a prompt-only draft may omit the plot. Present the plot for actual approval, then settle retrieval against it and the prompt. Preparation grants no permission to execute or change canon.
5. Choose a target; report plot requirements it cannot meet to the approving person. Run `python scripts/validate_prompt_semantics.py plan.json` before delivery; `--template` prints a plan to start from.
6. Select the target's adapter, resolve the optional `prompt-writing-guide`, and read the complete selected guide before final rendition.
7. Compose and review under the route's documents.

## Identity and scene-state authority

A category name proposes; only the author's declaration decides. Species, domain, and material supply no default. Examples are not anatomy, symmetry, clothing, or reference-view checklists. Permanent identity owns only the adopted design.

Use [Declared Structures Runtime](references/runtime/declared-structures.md) for structural contracts. Missing, absent, unknown, and occluded differ; validation checks declared topology, not typical anatomy.

Scene-specific character state is an open class: any visible or performance-relevant property that can change without changing identity, unless an approved Identity, Era, Form, or Appearance Contract owns it. A rendered reference does not promote state into identity. Review identity drift separately from source-state leakage.

## Catalog and pack runtime

Use one resolved runtime across retrieval, planning, preparation and verification. `recommend` explores sparse outcomes; `search` and `inspire` retrieve known needs; `batch` runs several queries in one process; `inspect-many` returns complete records and assets under one runtime fingerprint. Do not start several catalog CLI processes in parallel.

## Visual Reference Activation Gate

With no reference selected, stop the reference branch without creating empty reference artifacts. Otherwise declare one intended influence and one technical role per selected item under [Visual Reference Activation and Transport](references/visual-reference-activation-and-transport.md). Treat every selected SVG as bounded evidence, not as the whole requested image. A registered Character Sheet joins other evidence in one ordinary Reference Use Plan and owns only its identity role. Before rasterization or model-facing SVG preparation, run the visual dependency preflight, `python scripts/check_dependencies.py --profile visual`. A failed check blocks execution.

## Output contract

For world, persona or narrative work, return requested artifacts with actual design status, not unsolicited prompts. For prompt work, always return the requested prompt. Return a negative prompt only when requested or supported by the target. When no target parser is named, keep the prompt portable, without interface-specific weighting syntax unless the user asks for it. Reference-free prompt drafts include concise provenance and no empty placeholders.

Add reference artifacts only when references are selected or a reusable reference package is requested; [Prompt-Only Core](references/runtime/prompt-only-core.md) gives each file's condition. When a reference is selected, return the actual file. A file path or hash is not delivery.

## Maintenance and release

Activate these documents only when changing the library or distributing the project:

- record, taxonomy, evidence, or preset work: [Preset Maintenance](references/maintenance/presets.md);
- search-profile authoring and retrieval evaluation: [Search Discovery Maintenance](references/maintenance/search-discovery.md);
- pack creation, installation, update, removal, lock, or lifecycle: [Pack Maintenance](references/maintenance/packs.md);
- core or pack publication and complete gates: [Release Validation](references/release/validation.md).

Do not read maintenance, pack-release, release-validation, state-aware, or unselected-model documents during an ordinary reference-free prompt-only task.

## Resource handling

Read complete material by default. For reads, imports, evaluation, review exports or execution budgets, use [Resource handling](references/resource-handling.md).
