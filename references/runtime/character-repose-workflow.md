# Character Assets and Multi-Character Scenes

Use the `repose` route to place one or more adopted characters in a new pose
or scene. Separate asset production from scene production when they need
different capabilities. Each actual generation uses the ordinary Production
workflow and Studio adoption. The author chooses which output becomes canon.

## Contents

- [Choose stages from missing information](#choose-stages-from-missing-information)
- [Bind each reference to its subject and use](#bind-each-reference-to-its-subject-and-use)
- [Direct the new scene](#direct-the-new-scene)
- [Choose an interface for each stage](#choose-an-interface-for-each-stage)
- [Prepare and execute the exact input](#prepare-and-execute-the-exact-input)
- [Review identity, performance and finish](#review-identity-performance-and-finish)
- [Repair a specific observed failure](#repair-a-specific-observed-failure)
- [Retain evidence at its owner](#retain-evidence-at-its-owner)

## Choose stages from missing information

Read the brief, adopted identity and appearance sources, and the next scene's
view. Decide which required features those materials actually show. A clear
portrait may establish a face while leaving a garment's back unobserved.

Record the coverage decision in `task.direction.decisions`: applied sources,
missing information, selected method, limitations and relevant criteria.
Use a fixed or routine decision when the available sources settle the choice.
Use a material decision for a real comparison of methods and tradeoffs.

1. Produce only missing character material when the next scene requires it.
   Select a model suited to that asset's identity, physique and finish.
   Inspect the actual output and apply the existing selection and adoption
   rules before granting it reference authority.
2. Produce the scene from the selected independent references. Select its
   model for the required reference inputs, instruction following, performance
   and finish. Existing adequate assets allow this stage to begin immediately.

A skipped asset stage creates no placeholder run. A generated intermediate
has only its selected use: composition, wardrobe, identity, or another explicit
scope. Keep its original provenance and adoption status when reusing it.

## Bind each reference to its subject and use

Use the existing [Studio canon references](studio-canon-references.md) and
[reference delivery](reference-delivery.md) owners. Resolve who each source
concerns before preparing its transport. Synthetic assignment:

| Subject | Source | Controls | Chosen in the new scene |
|---|---|---|---|
| A | Adopted character A | Stable face, body proportions and markings | Expression, gaze and pose |
| A | Adopted wardrobe A | Garment shape, color and closures | Face, acting and camera |
| B | Adopted character B | B's stable face, proportions and markings | Expression, gaze and pose |
| B | Adopted wardrobe B | B's garment shape, color and closures | Face, acting and camera |

Carry these assignments through each reference's `subject_uses`. A row names
`subject_id`, `use` and `priority`. Lower priority numbers take precedence
within the same subject and use. Priority leaves source authority unchanged
and has no meaning between different subjects or uses.

Keep logical assignments separate from physical attachments. One source may
serve identity and wardrobe for the same person. Several views of a person
still describe one subject. Equal image bytes with different source or
adoption evidence retain their distinct provenance.

Keep `controls`, `must_not_control` and the original source authority. A
wardrobe reference cannot silently acquire identity or pose authority. A
layout intermediate cannot redefine an adopted face or permanent physique.
Generate image numbers from the finalized delivery; every number must refer
to the actual attachment or board panel that will be sent.

When continuity needs state graphs, resolve each subject's identity, era,
appearance, state and selected references independently. Aggregate them into
the scene's canonical reference selection. Stateless scenes use the ordinary
reference path without inventing event history.

## Direct the new scene

Apply the [Character Identity Contract](../character-identity-contract.md).
Preserve adopted stable traits and release source-only expression, gaze,
body orientation, pose, wardrobe and relationships unless explicitly retained.
Write the target state affirmatively.

Use Production Specification `subjects[]` for identity, performance, wardrobe,
body geometry and contacts. Use its scene and camera fields for placement.
The production task's `direction.action_slice` owns a selected action phase
when the image needs one. Read the performance and geometry features when
those decisions are load-bearing.

For a conversation across a desk, establish each subject's side of the desk,
the speaker and listener, gaze targets, body orientation and readable moment.
Similar expressions can suit a scene; the intended interaction decides their
relationship. A forced expression difference is not a quality criterion.

Resolve `render_intent` for the final image, including medium, dimensionality,
linework, shading, surface and detail. Preserve required physique and finish
across model changes. Framing follows the scene's information needs, including
natural crop when appropriate.

## Choose an interface for each stage

Read the selected model's full guidance card and acquired interface evidence.
Distinguish input acceptance, meaningful reference influence and observed
image quality. Record exact model, service, operation, evidence date and the
conditions a prior observation actually covered.

Check independent image fields, maximum count, supported dimensions, available
controls, use-case guidance and the author's model restrictions. Four source
images require four accepted slots unless an explicitly selected source
already covers multiple needs. A board reduces physical input count; its
subject correspondence still needs inspection in the generated image.

For a catalog target, assess the relevant declared use and input requirements:

```sh
python scripts/render_contract.py assess --model MODEL --service SERVICE \
  --use-case USE_CASE --mode reference-guided --reference-count 4 \
  --alternative-model OTHER_MODEL
```

Read [Model request evidence](model-evidence.md) for external targets,
persistent selection preferences and the assessment's limits. Interpret a
model instruction at its author-declared scope: one stage or the whole work.
Select alternatives within that scope and existing submission authority.

Use only controls exposed by the exact interface. A checkpoint's sampler,
CFG, negative field, denoise strength or seed does not transfer automatically
to an instruction model. Choose a method from supported capabilities; a text
description alone does not establish exact identity control.

## Prepare and execute the exact input

Use ordinary `generation` for asset creation and `repose` for reuse in a
scene. Read the applicable route and interface feature, retrieve the required
visual concepts, and author the complete target prompt and criteria.

For shared image inputs, `task.image_input` binds the selected model,
reference uses and any exact external request. Its prepared references retain
the canonical set's source and delivery commitments. Existing-image changes
also use `task.semantic_edit` for the source and requested changes and
preservation, following [Semantic instruction editing](semantic-instruction-edit.md).
New scenes use their individual character references directly.

Run `production_workflow.py check` and `prepare` with the current task. Inspect
the complete request and reference correspondence. Execute through the
existing dispatcher or external handoff, claim, host call, capture and
settlement path in [Production Execution](production-execution.md). A saved
request binding establishes the intended bytes; the actual invocation and
returned response establish what was sent and received.

Each additional external attempt has its own task and exact request. An
interruption uses `status` or `resume` to recover the same attempt. Preserve
every actual result and its observed disposition.

## Review identity, performance and finish

Inspect each actual candidate beside its assigned sources. Review the whole
scene and the relevant face, garment, hand, foot and contact regions.

| Dimension | Observe |
|---|---|
| Identity | Each subject's adopted face, stable proportions and markings |
| Wardrobe | Correct owner, garment structure and absence of unwanted old clothing |
| Performance | Target expression, gaze, action and partner response |
| Scene | Count, placement, support, overlap, contact and camera |
| Finish | Required medium, proportions, linework and rendering quality |
| Integrity | Unwanted transparency, missing or extra structures and broken edges |

Apply the author's scoped `accepted_variations` from
[Production direction](production-direction.md#preserve-accepted-variation-at-its-declared-scope).
Evaluate natural acting changes separately from identity drift. Record the
observation, criterion, reason and unresolved issue in the existing review.

Before treating a method as reusable, exercise the actual requirements that
matter: distinct face angles, changed wardrobe, multiple subjects, reference
role separation and another scene. A successful image establishes its tested
conditions. The author decides how much evidence the intended reuse needs.

## Repair a specific observed failure

Start from the adopted original or a candidate explicitly selected for the
repair. Preserve its working features and identify the observed defect.
Read [Repair analysis](repair-analysis.md) when comparing recorded failures.

Provider refusal, invalid input, missing credentials, transport failure and a
visually incorrect output require different responses. Use the evidence-based
diagnosis in [Model request evidence](model-evidence.md) before deciding that
use-case restrictions contributed. For a permitted request, compare suitable
alternatives with the required inputs and current provider conditions. The
normal authorization and exact-request preparation apply to the selected one.

Additional restyling, local editing, compositing or a character model may help
a specific defect. Assess each method's capability evidence and expected
effect on identity, acting, finish and other subjects. Keep model-specific
settings with their exact offering and observed conditions. A face composite
must preserve the target view and performance if those are requirements.

Finish when the scene meets its criteria. Further full-frame passes require
a concrete improvement to pursue and an assessment of existing strengths.

## Retain evidence at its owner

Studio owns requests, outputs, reviews, candidate selection and adoption.
Model and offering evidence owns interface limits and bounded observations.
The runtime method owns reusable preparation and review rules. Retain both
successes and failures at their actual scope.

Follow Production Execution through review, selection and completion.
`status`, `impact` and `resume` recheck dependencies and artifact bytes.
Structural validation establishes input integrity; image inspection establishes
the observed result, and the author decides acceptance.
