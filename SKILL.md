---
name: character-prompt-builder
description: Create image prompts, scoped negatives and canonical references for humans, animals, anthropomorphic animals, creatures, monsters, hybrids, robots and androids. Use for character generation or illustration; editing an existing image to replace clothing, objects, backgrounds or lighting; prompt writing, revision, translation, expansion or variation; OCs, fursonas, mascots, VTubers, worlds, themes, personalities, casts, relationships and narratives; recurring-character continuity; prompt-facing SVG or verified model-facing references; and state-aware image series involving identity, emotion, relationships, environment, wardrobe, inventory, time, injury, transformation or off-screen events. Trigger on sparse or detailed briefs in any language, even without the word prompt. Work with any image model or service.
---

# Character Prompt Builder

Keep subjects, world and expression coherent. Art-direct each image as one depiction, not a record list.

Use English prompts/retrieval and the user's language. Preserve meaning, modifier scope, relationships, negation and ambiguity without language word lists.

## Core contract

Identify the artifact, purpose, anchors and creative space. Clarify consequential ambiguity; otherwise choose a coherent direction. Select explicit requirements, necessary meaning and purposeful art direction. An imagined detail is not a requirement: leave it open when another depiction meets the same intent. Do not convert omissions into permissions or exclusions. Verify the chosen instructions and resulting image against the intended event.

Never alter an anchor silently. Disclose each modification and its reason. Assumptions fill open space; modifications change intent. Keep creator portrayal intent separate from facts and psychology; apply it across outputs.

The user controls acceptance and delegation. Bind inputs, target and count to authorization; distinguish direction, editing, submission, selection and canonical adoption. Act within that scope without repeated approval, and stop outside it. Compare actual output with intent; revise only within authority.

Preserve supported production knowledge at full specificity across every genre and intensity level, from everyday and wholesome subjects to sensitive material such as violent, medical, grotesque, body-altering, or adult knowledge, without exception. Read [Prompt Knowledge and Execution Boundary](references/prompt-knowledge-boundary.md) when relevant.

Use plain ASCII punctuation in studio documents, prompts, JSON text, and packaged examples. Do not emit the Unicode em dash.

Keep judgment and automation separate. The agent owns meaning, ambiguity, direction, visual authority, composition and review. Scripts own state, retrieval, validation, materialization, dependency checks, verification and dispatch. Do not force unresolved meaning into keywords. Use scripts with documented activation, inputs, outputs, failures and tests. Resolve paths from installed `SKILL.md`.

## Rendering and model controls

For image work, resolve [Rendering choices and execution controls](references/runtime/render-contract.md), feature `render-contract`.
Choose medium, dimensionality, linework, shading, surface, and detail explicitly, with the user's selection or the agent's reason.
Keep presentation and subject identity separate. Use scoped overrides for mixed media; never invent body or age changes from a finish.
After `pack_cli.py ready`, read the selected model card and use-case guidance and author preferences before model-specific wording. Unlisted targets use acquired provider contracts.
Retrieve the wording, then bind its rendering span in `render_intent`: inside the Production Specification for dispatch, or as an applied task source for external work.
A Generation Package requires the exact interface's profile and mode-valid controls. For an unlisted target, record the absence and follow [Image Generation](references/runtime/image-generation.md#choose-execution). Shared `image_input` binds references and exact external requests; actual edits add [Semantic instruction editing](references/runtime/semantic-instruction-edit.md). [Model request evidence](references/runtime/model-evidence.md) owns schemas, trials, profiles, suitability and failure diagnosis.
Required scalar recommendations resolve with provenance; ranges require a choice. Unavailable controls are displayed, not sent.
Use the verified request and its named provider. Display the rendering choice and complete final request before submission; never substitute a different engine.

## Mandatory retrieval-before-composition gate

This gate governs image prompts, not prose or brainstorming. Never hand-compose prompt wording before retrieval has been attempted: wrong or competing tags can cancel requested content.

1. For every distinct visual element (pose, action, expression, camera, lighting, wardrobe, body feature, effect, and any specialized domain), search the catalog (`catalog_cli.py search`, then `inspect` the closest record) and, for tag-level wording, the prompt vocabulary (`pack_cli.py resource prompt-vocabulary` plus `search_prompt_vocabulary.py`). Add `--record lookups.json --element NAME` to every search and inspection; in catalog `batch` each `request_id` names its element, and in a vocabulary `--queries` object each key does.
2. Mark each element with `python scripts/prompt_retrieval.py lookups.json --element NAME --adopted ID` (repeat `--adopted` for every record used), or with `--composed TEXT --reason TEXT`. When retrieval cannot run, state the reason instead; never fabricate retrieval or approval.
3. Compose new wording only when retrieval finds nothing suitable; [Prompt-Only Core](references/runtime/prompt-only-core.md) gives the wording checks.
4. When a newly composed phrase is confirmed effective in a finished image, add it back to the owning pack resource (dictionary entry or module record) as terms and wording only, with no session history, seeds, or run parameters.

## Mandatory runtime activation gate

Before prompt, reference, sheet, generation or visual-state series work (not persona or story drafting), run `python scripts/pack_cli.py ready`. Put the task's `--state-file`, `--cache-dir`, `--managed-root` and repeated `--pack-root` options before `ready` when supplied. It creates the state on first use, keeps every existing choice, and prints the packs retrieval will use.

- Exit 0: retrieval can proceed. Tell the user each `warning:` line.
- Exit 1: each `decide:` line is the author's decision and names the command that settles it. Put new or unusable packs to the user before continuing; never continue on bundled commons alone while a discovered pack awaits that decision. Run the command the author chooses, then `ready` again. A pack the author disabled stays disabled and is not asked about again.
- If the enabled packs change after retrieval has begun, discard the earlier results and restart from the image intent.

## Artifact-bearing production gate

For saved deliverables, run `python scripts/execution_routes.py read ROUTE --root STUDIO` with each applicable `--feature NAME`. Add `--model MODEL` for a catalog target or `--dialect ID` for an evidenced prompt family; omit both for an unknown external target. It prints [Production Execution](references/runtime/production-execution.md), the required documents and a reading record to complete. Use `--page-bytes N` and `--continue CURSOR` for long reads. Follow the route through completion; use `status` or `resume` after interruption.

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
- accepted characters in a new pose or shared scene, including staged asset creation: route `repose`;
- deterministic editing of pinned stills: feature `image-edit`; user-requested semantic replacement of clothing, objects, environment or other depicted content: feature `semantic-instruction-edit`, [Semantic instruction editing](references/runtime/semantic-instruction-edit.md); masks when needed: feature `scene-mask-planning`;
- enlarging a finished image: route `upscale` with an active upscaler model record;
- canonical identity, a character sheet, its panels, candidates or reference board: route `character-sheet`, [Sheet fills](references/runtime/sheet-fill-workflow.md); a new pose or scene for an accepted character uses `repose` or `generation` instead;
- sheet, iteration, or accepted-image work, which lives in a studio: feature `studio` first;
- explicit selection for a canonical owner: route or feature `adoption`;
- scoped changes or review of existing artifacts: route `revise` or feature `revision-guidance`;
- a production report or evidence study: feature `evidence-review`; preserved originals, host trials or repair hypotheses: feature `source-material`, `agent-evaluation` or `repair-analysis`;
- public state or shot interchange: feature `protocol-exchange`;
- absent pack state, custom packs, or a resource conflict between packs: feature `pack-runtime`.

Add a specialist feature only for a load-bearing subject: `geometry` for exact multi-subject geometry, crop, perspective, overlap, or contact; `body-plan` for any non-human or unfamiliar body (animal, anthropomorphic animal, hybrid, creature, robot, android), a transformation, or unusual feature counts; `recurring-identity` for a recurring character's identity contract; `performance-language` for subtle emotion, body language, appendage acting, physiological response, or mechanical performance; `garment-growth` for garment, growth, grooming, hair, fur, feathers, quills, bristles, spun fiber, molded strands, nails, claws, talons, hooves, digit plates, or local identity; `production-spec` for scene artifacts; `finishing` for a named or implied rendering medium, photographic look, 3D or toy presentation, in-image type or logo, environment-forward composition, or repeated wrong-finish results; `visual-evidence` for derived visual evidence, linked SVGs, or corpus ingestion.

[Weighting grammar](references/runtime/prompt-weighting.md).

## Mandatory studio gate

Persistent character production, sheets, recorded generation and reusable drafts live in a studio. When `python scripts/session_entry_points.py` reports none, use `studio.py init` before authoring. Use `production_workflow.py execute` for dispatcher tasks, or its documented external claim, capture and settlement branch for host tools; follow [Studio Runtime](references/runtime/studio.md). One-off answers need no studio.

Use managed attempts in [Sheet fills](references/runtime/sheet-fill-workflow.md). Apply HTML edits with `sheet_workflow.py apply-edit`. Record answers with `work_ledger.py respond`, reopen the indicated step, and suspend/resume when switching tasks. `studio.py status` or `sync` reconstructs views without repeating generation.

After story revisions, update Studio sources and run `studio.py sync` for the automatic Flow and Graph (`narrative-files`). Compare passages for meaning; structural checks do not judge story quality.

## Common runtime sequence

For image work:

1. Resolve the artifact and whether it needs saving. For saved work, establish the Studio and read the selected route.
2. Separate requirements, purposeful choices and incidental deductions. Select the relationships and visible information the purpose needs. For character reuse, resolve reference coverage and stage-specific targets.
3. Read interface guidance; resolve the optional `prompt-writing-guide` and read the complete selected guide before final rendition. Retrieve every visual element. Inspect every selected canonical record in full. Dispatcher work resolves the execution profile.
4. Write the selected depiction, render intent, reference scopes and matching criteria. Keep planning alternatives and unneeded details out of the prompt. Retain required plot approval and settle retrieval against the final wording.
5. Save the final prompt, settings, evidence and any Studio recording destination in the task's declared inputs.
6. `production_workflow.py check --task task.json` reports diagnostics without creating a run. `prepare` publishes the request preview and execution plan; dispatcher runs also contain a Generation Package.
7. Review the complete request and operation targets. Dispatcher work uses `draft-execution --run RUN --grant GRANT --out decisions.json`, actual decisions, then `execute --run RUN --decisions-file decisions.json`.
8. External work follows Production Execution's handoff, exact authorization, `claim-external`, host call, `capture` and `settle-external` branch. After interruption, `resume --run RUN` recovers the existing execution.
9. Inspect candidates against the same requirements, not an imagined exact picture. Diagnose failures from saved evidence. Dispatcher trials use `variant`, `repeat` or `retarget`; external trials use new tasks and exact input binding. Actual edits also need semantic plans.
10. `status` reports runs, next commands and execution records. [Operation logs](references/runtime/operation-logs.md) defines inspection, export and cleanup; inspect reported staging before applying cleanup to its exact owner operation.

Each of these commands takes `--root STUDIO`; Production Execution defines them. Authored prose and conversation-only prompts do not acquire image-generation requirements.

## Identity and scene-state authority

A category name proposes; only the author's declaration decides. Species, domain, and material supply no default. Examples are not anatomy, symmetry, clothing, or reference-view checklists. Permanent identity owns only the adopted design.

Use [Declared Structures Runtime](references/runtime/declared-structures.md) for structural contracts. Missing, absent, unknown, and occluded differ; validation checks declared topology, not typical anatomy.

Scene-specific character state is an open class: any visible or performance-relevant property that can change without changing identity, unless an approved Identity, Era, Form, or Appearance Contract owns it. A rendered reference does not promote state into identity. Review identity drift separately from source-state leakage.

## Catalog and pack runtime

Use one resolved runtime across retrieval, planning, preparation and verification. `recommend` explores sparse outcomes; `search` and `inspire` retrieve known needs; `batch` runs several queries in one process. Inspect complete records and asset details together with `inspect-many` (or `inspect` plus `asset-lookup`). Do not start several catalog CLI processes in parallel.

## Visual Reference Activation Gate

With no reference selected, create no empty reference artifacts. Declare selected sources' authority, subject uses and exclusions under [Visual Reference Activation and Transport](references/visual-reference-activation-and-transport.md). Pack preparation uses one ordinary Reference Use Plan; shared image inputs retain the canonical prepared set. A character sheet supplies its selected identity scope. Treat every selected SVG as bounded evidence, not as the whole requested image. Before rasterization, run `python scripts/check_dependencies.py --profile visual`; a failed check blocks that preparation.

## Output contract

For world, persona or narrative work, return requested artifacts with actual design status, not unsolicited prompts. For prompt work, always return the requested prompt. Return a negative prompt only when requested or supported by the target. When no target parser is named, keep the prompt portable, without interface-specific weighting syntax unless the user asks for it. Reference-free prompt drafts include concise provenance and no empty placeholders.

Add reference artifacts only when references are selected or a reusable reference package is requested; [Prompt-Only Core](references/runtime/prompt-only-core.md) gives each file's condition. When a reference is selected, return the actual file. A file path or hash is not delivery.

## Maintenance and release

Activate these documents only when changing a pack or distributing the skill:

- record, taxonomy or evidence work: [Preset Maintenance](references/maintenance/presets.md);
- search-profile authoring and retrieval evaluation: [Search Discovery Maintenance](references/maintenance/search-discovery.md);
- pack creation, installation, update, removal, lock, or lifecycle: [Pack Maintenance](references/maintenance/packs.md);
- core or pack publication and complete gates: [Release Validation](references/release/validation.md).

Do not read maintenance, pack-release, release-validation, state-aware, or unselected-model documents during an ordinary reference-free prompt-only task.

## Resource handling

Read complete material by default. For reads, imports, evaluation, review exports or resource limits, use [Resource handling](references/resource-handling.md).
