# Instruction editing of an existing image

Use this feature when a user asks to replace clothing, an object, a background,
lighting or another depicted property while retaining a source image's subjects
or composition. It applies to a supplied image and to an accepted Studio image.
The agent chooses the edit's meaning and evaluates the result. Production pins
its selected source, reference roles, model, exact request and output evidence.

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
image, retain its adoption evidence. Inspect the current character sheet or
other accepted design references when identity, anatomy or scale matters.
Select only references that answer the current edit; a source pose, outfit or
background remains scene state unless its declared role gives it authority.

Declare the changed target and the properties that must remain fixed. Treat
these as separate review criteria. A request to change a background gives the
new background authority over that region. It does not implicitly change a
subject's anatomy, clothing or rendering. When a garment exposes previously
covered anatomy, use the relevant design view and review that region explicitly.

Identify the visible region that could prove each requested change. Preserve
fixed framing; an off-frame or occluded detail remains unverifiable. A wider
view is a separate composition choice and must fit the authorized edit scope.

Assign one role and a precise scope to each reference. Role names are open:
`scene`, `identity`, `anatomy`, `geometry`, `wardrobe`, `environment` and `style`
are useful choices. The selected source has the `scene` role. `use_for` names
its positive influence; `do_not_transfer` names properties it must not control.
An anatomy reference can supply physique and markings while the source image
continues to supply pose, framing and the relationship between subjects.

Choose the source for every trial explicitly. Return to the accepted original
when a rejected output contains defects outside the next edit's scope. A user
may instead authorize an edit of an existing candidate.

## Author and bind the task

Start with `templates/semantic-edit-plan.template.json` and validate against
`schemas/authoring/semantic-edit-plan.schema.json`. All file paths are relative
to the Studio root. The plan declares:

- `source`: the selected scene reference ID.
- `edit`: target, requested change, preserved properties and required roles.
- `model`: exact requested name, catalog status, selected service identifier and
  the saved evidence used to resolve it.
- `references`: ordered files, optional input hashes, roles and influence scopes.
- `review_criteria`: existing task criterion IDs that evaluate this edit.
- `external_request`: an exact host request binding, or `null` for dispatch.

The plan's `required_reference_roles` are authored requirements. The runtime
checks them without guessing a body plan or detecting clothing words.
`model.target.operation` names the selected service transport's wire operation.
Read that service's operation contract and acquired schema. A model's
`operation_kind` and rendering modes classify CPB behavior; neither supplies
this wire value. For example, a service can name its wire operation `generate`
while the rendering intent is `instruction-edit`. The service profile resource
is discoverable with `python scripts/pack_cli.py resource service-profiles`.

The ordinary production task names the plan at its top level. A synthetic fragment:

```json
{"route": "generation", "features": ["semantic-instruction-edit", "instruction-edit"],
 "artifact": "image", "execution": "external", "semantic_edit": "inputs/edit-plan.json",
 "sources": [{"id": "edit-source", "path": "inputs/scene.png", "role": "accepted-source",
   "disposition": "applied", "locator": "whole", "reason": "The selected product scene."}]}
```

This is a trimmed task fragment. Fill the ordinary sources, direction, criteria,
route reading, authority and delivery fields through Production Execution.
Use separate task criteria for change completeness, identity, structure, pose,
other subjects, environment and rendering where those properties matter.
`accepted-source` names the scene selected for this task; it does not adopt that image as canon.
Its path must match the plan's selected `scene` file. Additional task sources may use `reference-images`.
Their semantic roles and influence scopes remain in the plan. A one-source edit requires no auxiliary image.
Remove unused template references and their required roles together; never remove a reference the edit requires.

For an optional standalone inspection:

```sh
python scripts/semantic_edit_plan.py inputs/edit-plan.json --root STUDIO --out checks/edit-binding.json
python scripts/production_workflow.py check --root STUDIO --task task.json
python scripts/production_workflow.py prepare --root STUDIO --task task.json
```

The first command reports `status: prepared-not-generated`. It decodes every
selected image and pins the plan, source bytes, model evidence and request
bindings. It creates no remote request. `check` and `prepare` run the same
validator directly; the optional inspection file is not another runtime input.
An existing output path, invalid image, missing role, changed hash, undeclared
review criterion or conflicting reference scope fails with a diagnostic.

## Retain rendering and retrieval evidence

Resolve the visible finish through [Rendering choices](render-contract.md).
Save its complete intent as an applied task source with role `render-intent`.
When the finish is fixed, include its preservation in the edit and final instruction.
The author checks the intent's exact `prompt_expression` against that instruction.

Run catalog and vocabulary retrieval before composing the edit. Mark the selected
outcome for every visual element under the ordinary retrieval gate, then validate:

```sh
python scripts/prompt_retrieval.py STUDIO/inputs/lookups.json
python scripts/render_contract.py validate-intent STUDIO/inputs/render-intent.json
```

Keep the lookup record as an applied task source with role `retrieval-evidence`.
Assess the final wording against its selected outcomes in the task's direction.
When an approved plot is required, use the normal retrieval settlement command
with that plot and final prompt. External preparation pins these sources; the
agent evaluates their meaning. It does not synthesize a Production Specification
or claim the dispatcher's compiled rendering and retrieval checks.

## Select the model and transport

Look up the requested model before final composition. Record its exact requested
name in `model.requested`. When its catalog record is absent, use
`catalog_status: missing` and `catalog_model: null`; retain the lookup and the
provider's exact identifier in the evidence. Resolve aliases from evidence.
A similarly named model is a new target, requiring an explicit choice.

Read the selected interface's current parameter schema and prompt guidance.
Choose natural language or tag syntax from that model's actual contract.
Retrieve relevant visual vocabulary before writing the target rendition.
Each extra image's role must reach the request through supported fields or
clear instructions. Multiple-image support alone does not establish which
reference controls each property.

Choose a transport that carries every required source and scope. One source is
enough when it supplies all fixed visible properties. Add identity, construction,
or other references only when the edit needs their information.

Dispatcher preparation supports separate images and verified boards with panel
lineage. External binding maps each original image to its own exact request field;
it does not merge several logical originals into an untracked board. A supported
source/mask/guidance interface may bind those distinct fields explicitly.
A guidance mask identifies an intended region; only an evidenced hard-mask
contract can promise a pixel boundary. Record transport limits separately from quality.

For `execution: dispatcher`, leave `external_request: null` and use the ordinary
Generation Package. The ordered prepared reference set must match every plan
source hash, role and influence scope. Its canonical model record and exact
offering must match the declared target. The existing reference delivery flow
binds the actual transported image bytes or board regions. The final request
seal also retains the edit contract, so changing a target or scope requires a
new preparation. Run the usual request review, `execute` and `resume` commands.
The optional `scene-mask-planning` feature remains a dispatcher workflow.
Its auxiliary guidance is outside `prepared_reference_set`; it cannot satisfy a
required semantic reference through that matcher. Use an external binding that
carries every required input when the interface exposes separate guidance fields.

## Prepare supplied references for dispatch

For request-supplied scene and design files, prepare directly from the authored
semantic edit plan. Leave its `external_request` null and name a defined,
canonical `catalog_model` with its exact active service offering.

```sh
python scripts/prepare_generation_references.py --studio STUDIO \
  --semantic-edit-plan-file inputs/edit-plan.json \
  --output-dir STUDIO/inputs/reference-carriers \
  --out STUDIO/inputs/prepared-reference-set.json
```

The plan path and its image paths resolve below `--studio`. Output paths use the
calling directory. The model comes from the plan; an optional `--model` must
resolve to that same record. Use `--transport-mode single-board` when the
selected interface needs one attachment carrying several declared panels.

The command derives every supplied-file source, role, ordered position and
authority scope from `references`. Its prepared rows retain `use_for` as
`authority.controls` and `do_not_transfer` as `authority.must_not_control`.
The set embeds a validated `semantic_edit_binding` that pins the complete edit,
model evidence and original image hashes. It preserves those scopes through
ordinary package construction and reference delivery.

Name the same plan and the prepared set in the production task. A trimmed
synthetic task fragment:

```json
{"execution": "dispatcher", "semantic_edit": "inputs/edit-plan.json",
 "generation": {"production_spec": "inputs/production-spec.json",
                "references": "inputs/prepared-reference-set.json"}}
```

Production checks the prepared binding against the task's current plan.
Changed source bytes, scope, reference order, model or plan require preparation
again. A frozen Generation Package verifies its recorded sources and binding
from its companion directory after the original Studio files have moved.

The ordinary `--supplied-selection-file` path retains role-derived conservative
authority. Use the semantic plan path for task-specific scopes. A semantic edit
binding cannot replace state eligibility or a pack Reference Use Plan. Keep
those sources in their existing provenance workflow. For object-only images,
use the [Production Specification object-only guidance](../production-specification.md#object-only-scenes).

## Execute through an external host

Use `execution: external` when a supported host tool performs the call,
including a schema-backed trial of a model missing from the catalog. Keep its
lookup and schema evidence without claiming a completed catalog profile.

Upload the selected original bytes through the host's supported media API and
retain its response. Save one exact model request as Studio JSON. The plan's
`external_request` names that file and its field paths as arrays of object keys
and array indices. Declare model, prompt, optional operation and output count
fields. `reference_fields` lists every reference in the selected order, with
its request path, uploaded value and acquisition evidence. A model without a
count or operation field uses `null` for that field; record the expected count.

Add `schema: {"path": "inputs/schema.json", "sha256": "...", "pointer": []}`
to select the acquired request schema. An empty pointer selects the whole JSON
document; a nested pointer may select an encoded schema string in a tool
response. Validation checks fields, numeric constraints and declared per-image
file size or dimension limits using the pinned original bytes. Unsupported
schema rules remain explicit in `schema_validation.unmeasured`. Without a
schema, the binding records `bounded-probe` with `schema-unavailable`; scope
the trial's question and quantity through the existing task and authority.
Authorization checks that mode against the grant's `submission_validation_modes`.
External semantic submission uses exact-operation authority with `request_scope: null`;
dispatcher request-scope cases cannot authorize a request they do not assess.
Use the principal's existing explicit authorization where it covers this trial.

For example, a synthetic transport may bind `model_field: ["model"]`,
`prompt_field: ["prompt"]` and two media fields at `["images", 0]` and
`["images", 1]`. These are declared paths, not provider defaults. The request's
prompt must exactly equal the task's delivery text, including whitespace.

Preparation stores the complete request preview and the binding in the
consumer. Model substitution, changed media IDs, omitted reference fields,
reordered roles or an inconsistent output count fail before a claim. The
compiler pins all referenced files. `external-intent` checks those live pins
again and binds the exact model, input count and request digest to the existing
submission authority.

Follow the external branch in Production Execution:

1. Complete `handoff-intent`, its authorization and `handoff` for the selected host.
2. Complete `external-intent`, its authorization and `claim-external` before the call.
3. Invoke the host with the saved request once and keep its actual response.
4. Save original returned bytes, `capture` each image and `settle-external` with
   the response, captured count and actual cost when reported.
5. Inspect and review each captured candidate before selecting a result.

A repeated claim lookup grants no second call. After interruption, use `status`
or `resume` and recover the existing host result. Capturing a returned result
uses the prepared evidence even if a live source later changes. A returned
image ID remains an uncaptured result until its bytes have been saved and
verified. A provider refusal, transport error and captured quality failure are
separate observed outcomes.

Each additional external trial uses its own task, request file and semantic plan.
Keep the earlier run or candidate as a comparison source when relevant, and run
`check` and `prepare` again. The dispatcher's `variant`, `repeat` and `retarget`
commands do not operate on an external run.

## Review and transferable findings

Assess every relevant criterion on the actual image. Preserve uncertainty when
an output cannot be viewed or a reference was not delivered. API acceptance
establishes request acceptance; it does not establish identity or edit quality.
Record incomplete edits, anatomy drift, pose drift and changes outside the
requested scope independently. Keep trials and measurements in their Studio.

Assess the edited target and every protected subject or region separately.
A correct change on one subject does not establish preservation of its neighbor.
Record transferred clothing, color, shape or lighting as scope leakage where
those properties were fixed. If a required detail is outside the frame or hidden,
mark that criterion `indeterminate` with the visibility limit; never infer a pass
from the prompt or from a different reference view.

Model capabilities belong in the model and offering records, with measured
conditions and limits. Effective reusable wording belongs in its owning pack.
General corrections belong in the owning production contract. Keep private
images, task histories and experiment narratives outside the reusable skill.

`python scripts/semantic_edit_plan_smoke_test.py` uses neutral synthetic images
and the ordinary external lifecycle. It checks request pins, role delivery,
source changes, capture and recovery without invoking a provider.
