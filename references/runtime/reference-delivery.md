# Exact reference delivery

Read this when preparing or inspecting model-facing reference attachments. Package dispatch uses one committed prepared reference set.
Image inputs use the common original-file mapping described in [Semantic instruction editing](semantic-instruction-edit.md).
Dispatcher and external requests retain the same source bytes, subject assignments, order and authority.

## Selection and authority

Retrieve applicable production knowledge and inspect each selected source before preparing it. Decide what the source may control, what it must leave alone, and why this request needs it. Choose only task-relevant sources rather than filling an arbitrary count. A model's observed attachment limit is an execution constraint, unlike a fixed aesthetic reference quota.

A character sheet is a document containing views of its assigned subject.
Use relevant views within the source's declared scope; panel selection need not
be prescribed when several views carry complementary information. State the
target outfit, action and expression separately. Add individual detail images
when needed for legibility rather than enforcing a fixed reference count.

Identity, current expression, wardrobe, lighting, pose and camera are different scopes; a transient state propagates only when requested, whatever identity the source shows. Express each source's `controls` and `must_not_control` authority scopes explicitly. Identical positive and excluded scopes are contradictory and rejected. The script leaves synonyms and semantic conflicts to the agent, who resolves them against the actual source and current intent.

### Resolve the attributes needed by this image

Inspect the source regions that carry the requested features. Establish the
actual face construction, marking placement, proportions, garment structure
or other relevant attributes before writing their preservation instructions.
Use descriptions supported by those regions and the adopted design. Species
and garment categories help retrieve knowledge; the individual source resolves
the particular design. Record an unreadable or unseen detail as a coverage
limit in the current production direction.

For each consequential attribute, determine its subject, adopted source,
preservation or requested change, and the reference use that carries it.
Keep those choices in the existing `task.direction.decisions`, applied sources
and task criteria. The image input's `use_for` and `do_not_transfer` carry the
source scopes; prepared references express them as `controls` and
`must_not_control`. A change to the current scene belongs to its Production
Specification or semantic edit. A change to permanent identity follows the
owning Identity, Era, Form or Appearance Contract.

Choose the source with the needed authority and readable coverage for each
attribute. A complete character sheet can be the primary identity evidence;
a portrait or detail view can supply the particular face or surface information
the task needs. Several views may complement one another. Resolve their
precedence within the same subject and use, and describe the finer attribute
boundary in their scopes and the selected instructions.

Read positive scopes and their exceptions together. A broad scope with an
explicit exception can express a coherent use when the remaining attributes
and their target owners are clear. When replacing a broad term with specific
parts, account for every still-required attribute through a source or the
target depiction. Preserve complementary evidence and meaningful exceptions.
Resolve incompatible values for the same subject and attribute against the
current request and adopted authority, then describe the chosen result.

Synthetic example: an adopted portrait shows a short, rounded muzzle and three
cheek marks; an adopted sheet provides the tail bands and back markings; the
new scene changes the expression and arm pose. With those files delivered as
Images 1 and 2, the reference-use portion of the prompt can read:

```text
Use Image 1 for the character's short, rounded muzzle and three cheek marks. Use Image 2 for the tail bands and back markings. Depict the expression and arm pose specified for the new scene.
```

The scene description supplies that expression and pose. The source scopes and
criteria retain the corresponding preservation and change decisions for review.

Use `prepare_generation_references.py --image-input-plan-file PLAN --studio STUDIO`
for authored `use_for` and `do_not_transfer` scopes. The plan can pin an existing
prepared set through `prepared_references`. Its source, state, adoption and pack
scope must match exactly. Existing candidates remain candidates until their
actual owner adopts them.

The supplied-selection input is an ordered array with `role`, `source` and
optional `subject_uses`. A synthetic two-character example:

```json
[
  {"role": "identity-a", "source": {"kind": "supplied-file", "reference_id": "a-original",
   "resolved_path": "/absolute/studio/inputs/a.png"},
   "subject_uses": [{"subject_id": "A", "use": "identity", "priority": 0}]},
  {"role": "identity-b", "source": {"kind": "supplied-file", "reference_id": "b-original",
   "resolved_path": "/absolute/studio/inputs/b.png"},
   "subject_uses": [{"subject_id": "B", "use": "identity", "priority": 0}]}
]
```

The preparer measures media type and hashes. Each `subject_id` must resolve to
an actual Production Specification subject. `use` names a canonical intended
influence. Lower `priority` numbers win within the same subject and use;
equal priorities supply complementary evidence. Priority grants no additional
influence and never settles a conflict between different people or purposes.
Leave the array absent or empty for references without a character assignment,
such as a room plan. Multiple characters without story state require no state graph.

One image may carry several subject/use entries. A pack record declares them in
its selected-record decision, for example:

```sh
python scripts/reference_runtime.py plan \
  --record-use '{"record_id":"wardrobe-record","intended_influence":"outfit","subject_uses":[{"subject_id":"A","use":"outfit","priority":1}]}' \
  --transport-mode prompt-artifacts --source-lighting-mode replace --out reference-use-plan.json
```

A state binding limits assignments to its character and declared influences.
A plan narrows them to its selected influence. Studio identity use requires the
matching identity adoption. The Reference Use Plan retains canonical pack
technical authority. Identity use leaves current expression, action and camera
to their target-scene owners.

One prepared set may contain state-aware A's pack references and stateless B's
accepted Studio face and outfit. Execute the pack plan with `--reference-selection`
and append B's `--studio-selection-file` choices, using `--studio` for their owner.
Use `--supplied-selection-file` for direct source choices instead.
Without pack sources, combine `--state-selection-file` with either direct input.
State eligibility covers the managed rows; other subjects require no invented history.
The state row retains its subject assignment in the binding. The authored prompt identifies that subject through the delivered inputs.

## Bind the actual transport

The following prepared-set commands apply to reference-runtime and Generation Package delivery.
An external request binds the same logical rows to its declared field paths and upload evidence.

After rendering or copying the actual transports, the reference preparation runtime derives their actual attachment mapping. For multi-image input, identical committed transport hashes and media types share one attachment. Logical reference rows retain their distinct sources, adoption, roles and subject uses. For a single-board input, every logical reference points to attachment 1 and its exact panel rectangle in pixels from the top-left, and a board with several source panels consumes one model image slot in total. Source hashes, transport hashes, roles and panel rectangles must agree with the prepared set.

The map is authoring input for the agent. Interpret its subject assignments, scopes and precedence into the selected depiction using [Prompt Composition](prompt-composition.md#prompt-assembly-and-review). Internal keys, numeric priorities and request field paths stay in the binding record. Identify delivered images by their actual order and use a panel location when necessary. A source panel identifies evidence; it does not prescribe the output layout.

```sh
python scripts/reference_delivery.py --prepared-set prepared.json --package-root WORK
```

This inspection validates the complete prepared set and returns `bindings` with attachment positions, scopes and subject assignments. It submits and mutates nothing. Normal preparation uses the same functions through `prepare_generation_references.py` and `reference_runtime.py`. Review the authored prompt against those bindings and the actual attachments before packaging.

Inspect the committed carrier at its delivered size as well as the original
source. Confirm that the needed face, marking, seam or other evidence remains
readable after panel selection, rasterization, board assembly or resizing.
Compare each reference-use instruction with the actual attachment position,
subject and visible region. Check that the intended output attributes agree
with both the source scopes and the current target. A hash and panel rectangle
establish which bytes and region are bound; the agent establishes their visual
suitability. Read the complete prompt and delivered carriers as one request:
identify the present situation, relevant source attributes and their intended
uses from what the model receives. Supply a necessary scene premise in text
when those carriers do not establish it. Source records, earlier conversations
and authoring decisions retain their own information; their existence alone
does not deliver that information with the images. Compare the receiving-input
reading with the intended depiction before accepting the assignment. Carry a
material coverage limit into the existing direction and review criteria, and
choose a clearer authorized source or transport when the requested result
requires that evidence.

For an external request, inspect the same mapping from its declared image field paths:

```sh
python scripts/reference_delivery.py --image-input-plan image-input.json --studio STUDIO
```

This reads an existing prepared origin when the plan names one. Each binding records its exact request field, such as `["images",0,"uri"]`, for transport verification. A prepared origin also supplies the actual attachment number and board region for each logical reference. Different sources may share one external field when they use the same verified carrier and uploaded value; their individual roles and scopes remain recorded. Author the reference instructions using the image positions and controls the target actually receives. Preparation verifies the exact request, image mapping and source bytes; the agent reviews whether the received prompt and media convey the assigned uses.

Production preparation preserves the original source images and the actual
prepared carriers in the run. The review draft exposes both, with their
source assignments and transformations, so later review can inspect the same
pixels after live files move. Saved bytes remain subject to integrity checks.
A new send validates the live prepared inputs again. Use the recorded
submission evidence to establish which prepared media reached the target.

For prompt-artifacts, SVG-bundle, or no-reference delivery, never claim that model-visible attachments were sent. An unsupported target or missing selected transport is an explicit failure rather than silent reference omission. Targets and their observed limits are resolved from actual model records rather than fixed service names in this procedure.

Run `python scripts/reference_delivery_smoke_test.py` and the existing reference runtime tests. They test mappings and transport contracts, not whether a generator actually follows them.
