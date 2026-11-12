# Instruction editing of an existing image

Use this feature when a user asks to change a depicted property while retaining
an existing image's subjects or composition. It applies to a supplied image and
to an accepted Studio image. The agent chooses the edit's meaning and evaluates
the result. Production pins the selected source, reference scopes, model, exact
request and output evidence through its ordinary execution path.

A new scene assembled from character or design references uses the common
`image_input` contract in [Production Execution](production-image-inputs.md#image-input).
It has no edit source unless an existing scene is actually being edited.

## Contents

- [Start from the accepted image](#start-from-the-accepted-image)
- [Resolve the intended change](#resolve-the-intended-change)
- [Answer the draft and prepare](#answer-the-draft-and-prepare)
- [Author and bind the task](#author-and-bind-the-task)
- [Retain rendering and retrieval evidence](#retain-rendering-and-retrieval-evidence)
- [Select the model and transport](#select-the-model-and-transport)
- [Prepare supplied references for dispatch](#prepare-supplied-references-for-dispatch)
- [Execute through an external host](#execute-through-an-external-host)
- [Review and transferable findings](#review-and-transferable-findings)

## Start from the accepted image

An accepted Studio image is edited through the ordinary editable workflow:
`draft-inputs` creates the choices, the author answers them, and
`prepare --choices` compiles the request. Select the image by its Studio
character and slot. A Studio slot acceptance is sufficient for a scene edit;
the image does not need to be adopted into the character sheet. The draft pins
its iteration, image bytes and exact acceptance receipt. An applicable canonical
identity remains an independently verified adopted reference.

```sh
python scripts/production_workflow.py draft-inputs --root STUDIO --route generation --execution dispatcher \
  --edit-character CHARACTER --edit-slot SLOT --new-task "GOAL" --out-dir work/edit
```

Use `--execution external` instead for a host call that the agent performs and
records. `--new-task GOAL` opens the work task when no task is open; with an
open task, omit it and the draft uses that task. `--model MODEL_ID` and
`--service SERVICE_ID` select another target than the run that produced the
image. `--feature` adds specialist features. `scripts/studio.py status --studio
STUDIO` lists each character's slots and their accepted images. A slot without
a current accepted image is refused, and a refused command opens no work.
The draft's `edit_source.source.kind` states the evidence it selected:
`studio-accepted-image` for the Studio slot's current accepted iteration, or
`studio-artifact` for current sheet artwork without a Studio iteration. Damaged
canonical evidence is reported at its owner; it is not converted to a plain file.
`--source-image`, `--source-run`, `--source-candidate`, `--scale` and
`--purpose` belong to the upscale draft and are refused here.

The draft selects what follows from the accepted image and its owners:

- features `semantic-instruction-edit` and `instruction-edit`, artifact `image`,
  and the applied task source `edit-source` with role `accepted-source` at the
  accepted image's retained Studio path;
- the image as the scene reference `edit-source`. A `studio-accepted-image`
  source names the Studio, character, current slot, immutable iteration, image,
  acceptance and proof hashes. Its proof retains the original recording slot
  and producing run and selection when present. The command
  `scripts/studio_reference.py accepted-source` writes this source explicitly,
  as [Studio reference sources](studio-canon-references.md#choose-the-current-source-and-its-influence)
  describes. It grants no canonical identity authority;
- when that exact iteration also has a current verified identity adoption, the
  separate `edit-identity` reference with its `studio-artifact` proof and subject
  use `{"subject_id": SUBJECT, "use": "identity", "priority": 0}`. The source
  run's independently selected stateless Studio identity references retain their
  exact source and subject assignments. State-scoped references retain their own
  graph and eligibility requirements;
- for `dispatcher`, those references in `authoring.references.additional_references`
  with the mirrored `authoring.references.image_input: {}`. Preparation writes
  the image input from the prepared Studio source. For `external`, the same
  references in `external.reference_delivery.choices` and their IDs in
  `external.image_input.references`;
- the editable plan `edit-plan.json` in the draft directory, selected by
  `task_changes.semantic_edit`, with `source: "edit-source"` and
  `required_reference_roles: ["scene"]`;
- from the Production run that produced the image: its Production
  Specification with `render_intent.execution_mode: "instruction-edit"`, and
  its model and service as `choices.target`. A dispatcher draft also takes its
  `parameters` and its `validation` selection. A rendering declaration of that
  specification stays selected; its `prompt_expression` spans named the earlier
  prompt, so they are null until the edit instruction states the finish;
- for `dispatcher`, the original run's explicit continuity decisions and
  subject mappings, including every participant of a multi-subject scene.
  An applicable identity adoption supplies that subject's actual continuity
  decision. Missing decisions stay unanswered at
  `authoring.generation.continuity.SUBJECT`; accepting a scene does not decide
  that its participants are canonical recurring characters.

An adoption with identity influence makes the image the identity of a recurring
Studio character. The draft selects `recurring-identity` for that separate
adoption or for an original canonical identity reference that it carries, which
delivers the [character identity contract](../character-identity-contract.md#source-to-input-and-review-coverage).
An identity adoption of the edited image becomes `reference:edit-identity`, and the
draft reports its uncovered identity and the missing whole-subject review.
Select `--feature recurring-identity` yourself when the edit also applies the
character's adopted identity definition, such as its design or identity
contract, declared in `authoring.task.sources` with `identity.subject_ids` and
`identity.selectors`, or when the image has no identity adoption but its
identity still has to be preserved through such a definition.

Everything the author decides stays unanswered: the purpose and intended
effect, the instruction text, the criteria, what changes and what stays in the
edit plan, the recording slot, whether it is a sheet panel and the recording's
role, the passage of the prompt that states the finish, and each identity
binding's reason. The draft reports each as an `unresolved` entry with its
repair. In a synthetic Studio whose fixture author adopted a robot image as the
identity of slot `base.front`, with no work task open, this command printed the
output below. It is trimmed to `state`, selected `edit_source` fields,
and the field and reason of each entry (the code and gaps of the
identity entries); every entry also carries its message, repair and guidance:

```sh
python scripts/production_workflow.py draft-inputs --root STUDIO --route generation --execution dispatcher \
  --edit-character robot --edit-slot base.front \
  --new-task "Replace the plain background of the adopted robot image with a pale green wall." --out-dir work/edit
```

```json
{"state": "draft",
 "edit_source": {"character": "robot", "slot": "base.front",
   "path": "characters/robot/iterations/it-0001/result.png",
   "origin": {"run": "01a1c9be-bd50-71c9-aa7b-59beb427419b",
              "candidate": "622fb0ce160306df39e214eab667f9f524fa857d2e0a8c3312a056d6ffcc0f2c"},
   "identity": {"character_id": "robot", "continuity": "recurring"}},
 "unresolved": [
  {"field": "reading.reading_key", "reason": "reading-required"},
  {"field": "authoring.task.direction.purpose", "reason": "authored-choice-required"},
  {"field": "authoring.task.direction.intended_effect", "reason": "authored-choice-required"},
  {"field": "authoring.task.criteria", "reason": "authored-choice-required"},
  {"field": "authoring.documents.production_spec.render_intent.prompt_expression", "reason": "authored-choice-required"},
  {"field": "authoring.task.recording.slot", "reason": "authored-choice-required"},
  {"field": "authoring.task.recording.sheet_panel", "reason": "authored-choice-required"},
  {"field": "authoring.task.recording.role", "reason": "authored-choice-required"},
  {"field": "task_changes.semantic_edit.edit.target", "reason": "authored-choice-required"},
  {"field": "task_changes.semantic_edit.edit.change", "reason": "authored-choice-required"},
  {"field": "task_changes.semantic_edit.edit.preserve", "reason": "authored-choice-required"},
  {"field": "task_changes.semantic_edit.review_criteria", "reason": "authored-choice-required"},
  {"field": "authoring.delivery.content", "reason": "authored-choice-required"},
  {"field": "authoring.task.criteria", "code": "IDENTITY_COVERAGE_INCOMPLETE",
   "gaps": {"uncovered": [{"source": "reference:edit-identity", "pointer": "", "subject_ids": ["robot"]}]}},
  {"field": "authoring.task.criteria", "code": "IDENTITY_COVERAGE_INCOMPLETE",
   "gaps": {"missing_whole_reviews": ["robot"]}}]}
```

One complete entry from the same output names the plan file and its repair:

```json
{"field": "task_changes.semantic_edit.edit.target", "code": "AUTHORED_CHOICE_REQUIRED",
 "reason": "authored-choice-required",
 "message": "edit.target in work/edit/edit-plan.json, the edit plan that task_changes.semantic_edit selects, is null, so the edit names no part of the source image to change.",
 "required_action": "Write at edit.target in work/edit/edit-plan.json the depicted part of the source image that the commission changes, such as the region, object or property it names.",
 "guidance": {"document_path": "references/runtime/semantic-instruction-edit.md#resolve-the-intended-change"},
 "file": "work/edit/edit-plan.json"}
```

The external draft of the same image reports `target.operation`,
`external.request` and `external.image_input.external_request` in place of the
recording entries. `inspect-inputs` and `status` report the same choices for
the saved draft, apart from the identity coverage, which the draft and
preparation derive.

## Resolve the intended change

Read the selected source at its original resolution. For an accepted Studio
image, retain its acceptance and any selected adoption evidence through the prepared reference
set; the draft above selects it that way. Inspect accepted design references
when identity, anatomy or scale matters. Select references that answer the
current edit. A source pose, outfit or background remains scene state unless
its declared scope gives it authority. The scene reference's `subject_uses`
are that scope: add the uses that the edit keeps from the source image, such as
`pose-camera`, and assign each to its Production
Specification subject.

Declare the changed target and the properties that must remain fixed. Write
them in the edit plan: `edit.target` is the depicted part that changes,
`edit.change` the change it receives, and `edit.preserve` the properties that
must stay as the source shows them (an empty array states that none is fixed).
Give them separate review criteria and list their IDs in `review_criteria`. A
background change does not implicitly authorize changes to anatomy, clothing or
rendering. When a garment exposes previously covered anatomy, use the relevant
design view and review that region explicitly.

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

## Answer the draft and prepare

Work through every reported entry in the draft directory:

1. Inspect the route index from the draft's read action. Choose `actions.all`
   for complete paged delivery, or read required sections with `actions.next`
   and their `actions.continue`. Completion is a non-null `reading`; set
   `reading.reading_key` to its issued `reading.key`.
2. Write the edit instruction in the draft's `prompt.txt`. Express each
   source's assigned use against the images the target receives.
3. Fill `edit.target`, `edit.change`, `edit.preserve` and `review_criteria`
   in `edit-plan.json`.
4. Set `authoring.task.direction.purpose` and `intended_effect`, and add the
   independent criteria to `authoring.task.criteria`: one for the requested
   change and one for each preserved property whose result matters. For a
   recurring character, add the `identity_bindings` that cover
   `reference:edit-identity` (its source, `subject_ids`, selector `""`, treatment,
   reason and the reference carrier `{"kind": "reference", "reference":
   "edit-identity", "use": "identity"}`) and a hard whole-subject criterion whose
   `identity_review` names the subject, as the identity contract describes.
5. Set `authoring.documents.production_spec.render_intent.prompt_expression` to
   the passage of `prompt.txt` that states the retained finish, or remove the
   rendering fields so that only `artifact_type` and `execution_mode` remain.
   The copied specification describes the source image; revise its depiction
   fields, such as `image_promise`, `source_brief` and `scene`, to the edited
   result.
6. For `dispatcher`, set `authoring.task.recording.slot`, `sheet_panel` and
   `role`. Choose the destination independently of the source: use the source
   slot for a replacement candidate, or another slot for a deliberate new result.
   Generation creates a candidate; acceptance applies to its recorded destination.
   A panel declared by the resolved character-sheet layout, including its explicit
   aliases and state panels, uses `sheet_panel: true` and exactly one production
   subject mapped to the owning character. An ordinary scene slot uses
   `sheet_panel: false`, even when its artwork has been adopted or retained in
   `sheet-data.json`. Preserve all production subjects and every recurring
   subject's mapping and identity references. Criteria do not replace subject
   declarations. Later placement changes use the recorded
   [Studio placement operation](studio-placement.md), preserving the original run.
7. For `external`, set `target.operation`, the native `external.request`, its
   `external.media_slots` and the field paths of
   `external.image_input.external_request`, as
   [External request inputs](production-external-inputs.md#edit-the-request-and-media-choices)
   describes.

Then prepare the same choices:

```sh
python scripts/production_workflow.py prepare --root STUDIO --choices work/edit/choices.json
```

A dispatcher draft whose entries are answered prepares in one step. Its
prepared reference set holds the Studio source, so the request seal carries the
image's exact acceptance evidence and any separately selected canonical proofs;
the package's visual continuity names each adopted identity image. An external
draft first needs the actual upload of
the prepared scene carrier: `build-inputs --choices work/edit/choices.json
--out-dir NEW_DIRECTORY` publishes the carrier and reports it as
`provider-upload-required`. Upload that file through the service's actual
operation, set the reference's `transport` to the returned value, the saved
response and `uploaded_file`, then prepare the same choices.

The prepared scene reference delivers the image from a carrier under the run's
inputs, not from its Studio path. The edit binding therefore matches the
task's applied `accepted-source` by the SHA-256 of its file against the scene
reference's bytes. Preparation and every later upload or send check that the
source's current acceptance is still the selected one. A changed Studio slot
acceptance stops new work, and a replaced or withdrawn canonical adoption stops
work that uses its independent identity reference, with `STUDIO_REFERENCE_CHANGED`, as
[Studio canon references](studio-canon-references.md#preserve-current-acceptance-and-recorded-recovery)
describes, and a new draft selects the current image.

## Author and bind the task

A supplied image outside the Studio, or a complete task written by hand, uses
the same two plans. Start with `templates/semantic-edit-plan.template.json` and
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
source, state eligibility, adoption and authority remain intact. Each of its
rows takes the image input's own reference ID. The edit binding pins the common
input binding's hash; it does not copy the reference registry or invent another
authority owner. In editable choices, `authoring.references.image_input` holds
this explicit plan; [Production authoring](production-authoring.md#assemble-authored-choices)
describes it beside the mirrored form.

For external execution, inspect the reference mapping through
[exact request authoring](production-external-inputs.md#exact-target-and-provider-schema).
Express each source's assigned use in the final instruction against the actual
delivered images. The saved request binds that text and those media fields
before the edit plan is validated.

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
this task; the role does not itself adopt the image as canon. The file of an
applied `accepted-source` must hold the same bytes (SHA-256) as the common
input's selected `scene` reference; a prepared carrier at another path matches
by those bytes. Additional task sources may use `reference-images`. A
one-source edit requires no auxiliary image. Remove unused template references
and required roles together.

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
scope and an edit without its shared image input fail before submission. A
scene whose bytes no applied `accepted-source` holds, and a review criterion
the task does not declare, are refused in phase `semantic-edit` with the repair
in `required_action`.

## Retain rendering and retrieval evidence

Resolve the finish through [Rendering choices](render-contract.md). Save its
complete intent as an applied task source with role `render-intent`, or in an
applied `production-spec` source. External preparation runs the common render
intent validator and checks its exact prompt expression against delivery.
When the finish is fixed, include its preservation in the edit and instruction.
A declared Production Specification is validated through the same owner used
by dispatch. Subject assignments must resolve against that specification.

Use the selected model's input contract. Tag-based input requires the actual
dictionary search and wording selection. Descriptive input needs retrieval for
unresolved construction or wording questions. Record the investigations actually
performed and their selected outcomes; their owning validators are available
when an independent diagnostic is useful:

```sh
python scripts/prompt_retrieval.py STUDIO/inputs/lookups.json
python scripts/render_contract.py validate-intent STUDIO/inputs/render-intent.json
```

When lookup work was performed, keep its evidence as an applied source with role `retrieval-evidence`. Assess
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

Follow [image input and exact external requests](production-image-inputs.md#image-input)
for request schemas, endpoint/tool identity, media field bindings and saved-call
evidence. Complete the ordinary handoff, exact authorization and external claim
before one host call. Save the actual response, capture original returned bytes
and settle the result with reported cost. Preparation and a claim do not prove
execution. A saved request JSON is not an actual host-call record.

After interruption, use `status` or `resume` to recover the existing result.
Capture uses prepared evidence even if live inputs later change. An image ID is
uncaptured until its bytes have been saved and verified. A new trial has its own
task, image input and request; include an edit plan when that trial edits a scene.
The dispatcher's `variant` and `repeat` commands retain their declared input
contracts. A changed external target uses `retarget` with reassessed editable
choices or a complete task; it preserves the source run as lineage and checks
the current semantic plan, source scope and exact target input together.

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
images. `scripts/test_production_edit_inputs.py` drafts, answers and prepares a
dispatcher and an external edit of an adopted synthetic Studio image. Neither
invokes a paid provider or establishes image-quality success.
