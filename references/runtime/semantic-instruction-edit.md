# Instruction editing of an existing image

Use this feature when a user asks to change a depicted property while retaining
an existing image's subjects or composition. It applies to a supplied image and
to an accepted Studio image. The agent chooses the edit's meaning and evaluates
the result. Production pins the selected source, reference scopes, model, exact
request and output evidence through its ordinary execution path.

A new scene assembled from character or design references uses the common
`image_input` contract in [Production Execution](production-execution.md#image-input-and-exact-external-requests).
It has no edit source unless an existing scene is actually being edited.

## Contents

- [Resolve the intended change](#resolve-the-intended-change)
- [Author and bind the task](#author-and-bind-the-task)
- [Retain rendering and retrieval evidence](#retain-rendering-and-retrieval-evidence)
- [Select the model and transport](#select-the-model-and-transport)
- [Prepare supplied references for dispatch](#prepare-supplied-references-for-dispatch)
- [Execute through an external host](#execute-through-an-external-host)
- [Review and transferable findings](#review-and-transferable-findings)

## Resolve the intended change

Read the selected source at its original resolution. For an accepted Studio
image, retain its adoption evidence through the canonical prepared reference
set. Inspect accepted design references when identity, anatomy or scale matters.
Select references that answer the current edit. A source pose, outfit or
background remains scene state unless its declared scope gives it authority.

Declare the changed target and the properties that must remain fixed. Give them
separate review criteria. A background change does not implicitly authorize
changes to anatomy, clothing or rendering. When a garment exposes previously
covered anatomy, use the relevant design view and review that region explicitly.

Identify the visible region that could prove each requested change. A detail
outside the frame or behind an obstruction remains unverifiable. A wider view
is a separate composition choice and must fit the authorized edit scope.

Assign a role and precise scope to each reference in the shared image input.
The selected source has the `scene` role. `use_for` names positive influence;
`do_not_transfer` names properties it must not control. `subject_uses` limits
an influence to named Production Specification subjects and records priority
within each subject and use. It does not expand the source's authority.

Choose the source for every trial explicitly. Return to the accepted original
when a rejected output contains defects outside the next edit's scope. A user
may instead authorize an edit of an existing candidate.

## Author and bind the task

Start with `templates/semantic-edit-plan.template.json` and
`templates/image-input-plan.template.json`. Their authoring schemas are
`schemas/authoring/semantic-edit-plan.schema.json` and
`schemas/authoring/image-input-plan.schema.json`. Paths are relative to Studio.

The edit plan owns only `source`, `edit` and `review_criteria`. `source` names
an existing reference ID with role `scene`. `edit` contains the target, change,
preserved properties and required reference roles. `review_criteria` names
existing task criteria. The runtime checks these authored requirements without
guessing body plans, clothing or artistic intent.

The image input owns `model`, ordered `references` and `external_request`.
The optional `prepared_references` points to an existing canonical set whose
source, state eligibility, adoption and authority remain intact. The edit
binding pins the common input binding's hash; it does not copy the reference
registry or invent another authority owner.

For external execution, generate the common reference preamble through
[exact request authoring](production-execution.md#exact-target-and-provider-schema)
and include it in the final instruction. The saved request binds that text to
the actual media fields before the edit plan is validated.

A trimmed synthetic task fragment:

```json
{"route": "generation", "features": ["semantic-instruction-edit", "instruction-edit"],
 "artifact": "image", "execution": "external",
 "semantic_edit": "inputs/edit-plan.json", "image_input": "inputs/image-input.json",
 "sources": [{"id": "edit-source", "path": "inputs/scene.png", "role": "accepted-source",
   "disposition": "applied", "locator": "whole", "reason": "The selected product scene."}]}
```

Fill the ordinary direction, criteria, route reading, authority and delivery
fields through Production Execution. Use separate criteria for requested
changes, identity, structure, pose, other subjects, environment and rendering
where those properties matter. `accepted-source` names the scene selected for
this task; the role does not itself adopt the image as canon. Its path must
match the common input's selected `scene` file. Additional task sources may use
`reference-images`. A one-source edit requires no auxiliary image. Remove unused
template references and required roles together.

For an optional standalone inspection:

```sh
python scripts/semantic_edit_plan.py inputs/edit-plan.json \
  --image-input inputs/image-input.json --root STUDIO --out checks/edit-binding.json
python scripts/production_workflow.py check --root STUDIO --task task.json
python scripts/production_workflow.py prepare --root STUDIO --task task.json
```

The first command reports `prepared-not-generated`. It checks the common input,
decodes images, pins evidence and binds edit meaning. It makes no remote call.
`check` and `prepare` use the same validators; the inspection file is not another
runtime input. Missing roles, changed hashes, undeclared criteria, conflicting
scope and an edit without its shared image input fail before submission.

## Retain rendering and retrieval evidence

Resolve the finish through [Rendering choices](render-contract.md). Save its
complete intent as an applied task source with role `render-intent`, or in an
applied `production-spec` source. External preparation runs the common render
intent validator and checks its exact prompt expression against delivery.
When the finish is fixed, include its preservation in the edit and instruction.
A declared Production Specification is validated through the same owner used
by dispatch. Subject assignments must resolve against that specification.

Run catalog and vocabulary retrieval before composing the edit. Record each
selected outcome under the ordinary retrieval gate, then validate:

```sh
python scripts/prompt_retrieval.py STUDIO/inputs/lookups.json
python scripts/render_contract.py validate-intent STUDIO/inputs/render-intent.json
```

Keep lookup evidence as an applied source with role `retrieval-evidence`. Assess
wording against those outcomes in task direction. When an approved plot is
required, use normal retrieval settlement with that plot and final prompt.
External preparation pins this evidence; it does not invent a specification,
provider capability or visual success from its presence.

## Select the model and transport

Resolve the requested model and current interface from evidence. The common
input records the exact target, catalog presence and lookup evidence. Missing
catalog models remain possible as recorded external trials. A similarly named
model is a new target requiring an explicit choice. Model identity may be a
request parameter or a pinned endpoint/tool identity, as described in Production
Execution. Do not fabricate an unsupported `model` request field.

`model.target.operation` is the service's wire operation. Rendering execution
modes and model operation kinds do not supply that wire value. A service may
name its operation `generate` while the rendering intent is `instruction-edit`.
Read the service operation contract and acquired schema.

Choose a transport carrying every required source and scope. Multiple-image
support establishes input compatibility; reference-role effectiveness requires
visual evidence. Separate images and verified boards retain panel lineage in
dispatch. External exact bindings map logical images to explicit request fields;
identical original bytes may share one field while retaining each logical role.
Untracked boards cannot replace several selected original images.

The optional `scene-mask-planning` feature remains a dispatcher workflow. Its
technical guidance is separate from the canonical selected references. A mask
identifies an intended region; a hard pixel boundary requires an evidenced mask
contract. Record transport limits separately from visual quality.

## Prepare supplied references for dispatch

Leave the common input's `external_request` null. Name a defined canonical model
and its exact active service offering. Prepare through the existing command:

```sh
python scripts/prepare_generation_references.py --studio STUDIO \
  --image-input-plan-file inputs/image-input.json \
  --output-dir STUDIO/inputs/reference-carriers \
  --out STUDIO/inputs/prepared-reference-set.json
```

The plan and image paths resolve below `--studio`; output paths use the calling
directory. An optional `--model` must resolve to the same record. Use
`--transport-mode single-board` when the interface needs one attachment with
several declared panels. The set embeds `image_input_binding`, retaining original
hashes, scopes and subject uses. It does not embed edit meaning as source authority.

A trimmed dispatcher fragment:

```json
{"execution": "dispatcher", "semantic_edit": "inputs/edit-plan.json",
 "image_input": "inputs/image-input.json",
 "generation": {"production_spec": "inputs/production-spec.json",
                "references": "inputs/prepared-reference-set.json"}}
```

The current common input must match the prepared model, bytes, order, scope and
subject mapping. Its request seal carries both shared input and edit meaning.
Changes require preparation again. A frozen Generation Package verifies its
recorded evidence from its companion directory after original files move.

The ordinary supplied-selection path retains its conservative authority. Use
the common image input for explicitly authored supplied-file scopes. Existing
state selections and pack Reference Use Plans remain the upper authority; an
image input consumes their prepared result and cannot broaden their scopes.
For images without subjects, use [object-only Production Specifications](../production-specification.md#object-only-scenes).

## Execute through an external host

Follow [image input and exact external requests](production-execution.md#image-input-and-exact-external-requests)
for request schemas, endpoint/tool identity, media field bindings and saved-call
evidence. Complete the ordinary handoff, exact authorization and external claim
before one host call. Save the actual response, capture original returned bytes
and settle the result with reported cost. Preparation and a claim do not prove
execution. A saved request JSON is not an actual host-call record.

After interruption, use `status` or `resume` to recover the existing result.
Capture uses prepared evidence even if live inputs later change. An image ID is
uncaptured until its bytes have been saved and verified. A new trial has its own
task, image input and request; include an edit plan when that trial edits a scene.
The dispatcher's `variant`, `repeat` and `retarget` commands do not act on an
external run.

## Review and transferable findings

Assess every relevant criterion on the actual image. API acceptance does not
establish identity or edit quality. Record incomplete changes, anatomy drift,
pose drift and changes outside the requested scope separately. Assess every
protected subject or region: one correct subject does not establish preservation
of its neighbor. Record transferred clothing, shape, color or lighting as scope
leakage where those properties were fixed.

If a detail is hidden or outside the frame, mark its criterion `indeterminate`
with the visibility limit. Do not infer a pass from the prompt or another view.
Keep trials, images and measurements in Studio. Model findings belong to model
and offering records with measured conditions; reusable wording belongs to its
owning pack. General corrections belong to the existing production contract.

`python scripts/semantic_edit_plan_smoke_test.py` checks common and edit bindings,
source changes, external recovery and dispatcher delivery with synthetic local
images. It invokes no paid provider and establishes no image-quality success.
