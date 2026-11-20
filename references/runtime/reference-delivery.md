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

A canonical influence names its available capabilities. Select the contribution
this request actually uses with `selected_controls` on the record-use decision.
New JSON declarations require that choice; an omitted list remains unresolved.
Each value must be one of the supported capability strings returned by
`reference_runtime.py capabilities --influence INFLUENCE`; the preparer intersects
that choice with the actual artifact's technical capabilities. For example,
`pose-camera` can contribute pose, camera framing or silhouette relationships
independently. Choosing pose alone leaves camera and crop with the depiction's
owner. The short `RECORD_ID=INFLUENCE` form selects the whole influence.

`control_expressions` optionally maps a selected capability to the target's
actual wording. The selected capability remains the authority boundary; its
expression supplies the description, tags or mixed syntax to deliver. An
authored image-input plan instead owns these words directly at `use_for`.
Choose the supported source and contribution for this task before choosing
their expression. The validator checks the declared subset and exact delivery;
source inspection and the complete-input review assess meaning and suitability.

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
  --record-use '{"record_id":"wardrobe-record","intended_influence":"outfit","selected_controls":["garment and wearable construction"],"subject_uses":[{"subject_id":"A","use":"outfit","priority":1}]}' \
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

## Reference identities and coverage

A reference use has one stable ID, separate from its position among delivered
images. In editable dispatcher choices, select it at
`authoring.references.additional_references[].id`; an explicit image-input plan
uses `references[].id`. Give each use a distinct ID such as `keeper-face`.
When a selection first needs an ID, the authoring builder preserves a unique
`source.reference_id` when available, or assigns `reference-` followed by a
UUID. Read the assigned value in the saved choices. Reordering attachments
keeps the use ID and derives the new attachment positions.

The compiled prepared reference row records that use as `reference_id`, and
the image-input row records the same value as `id`. A supplied file's
`source.reference_id` identifies its original source; several uses of one
source can have different use IDs. Standalone canonical preparation derives a
stable use ID from the canonical record, source artifact, influence and subject
assignment. Other native prepared rows retain their declared source reference
or state binding ID. Inspect the selected rows or the input guide when
continuing such work; file names and attachment numbers do not assign those
identities.

Identity coverage adds the prefix `reference:` to the use ID when it exposes
the source inventory. That prefix belongs to the coverage source, and is not
added to the reference use or the `carriers[].reference` field.

| Location | Synthetic value | Meaning |
| --- | --- | --- |
| `additional_references[].id` | `keeper-face` | Stable selected reference use |
| Prepared row `reference_id` / image-input row `id` | `keeper-face` | The same use through preparation |
| Identity inventory source `id` | `reference:keeper-face` | Original image and scope that identity coverage must account for |
| Identity binding `carriers[].reference` | `keeper-face` | The selected reference carrying that identity |
| Delivered image | `Image 1` | Current model-facing attachment position, derived from transport |

For example, a binding can cite `"source": "reference:keeper-face"` and carry
that source with `{"kind": "reference", "reference": "keeper-face", "use": "identity"}` in
`carriers`. Use the inventory's exact source ID when selecting coverage;
the [identity coverage contract](../character-identity-contract.md#source-to-input-and-review-coverage)
defines the rest of that binding. Prompt wording identifies delivered images
by their actual positions and relevant visual content.

## Author the consumed reference direction

Write the reference direction in the editable delivery prompt, where its
meaning belongs in the whole depiction. Use the stable reference use ID to
bind actual locations and contributions. The inspector below returns
`reference_text_slots`, including each usable marker and its current value.
For a descriptive target, a source fragment can read:

```text
Use Image {{reference:keeper-face:attachment_number}} for {{reference:keeper-face:controls}}. Place this character beside the doorway, watching the other subject.
```

The compiler substitutes the current image number and the selected `controls`
words. Surrounding text is preserved exactly. A sentence can relate several
references, describe a whole sheet, or use the target's tag grammar. For
example, an authored `control_expressions` value can be a tag phrase inside an
existing weighted expression. Write the grammar that the selected target
supports; the substitution adds no sentence, weighting or exclusion of its own.

| Marker field | Delivered value |
| --- | --- |
| `attachment_number` | Actual image position after ordering and deduplication |
| `controls` | The selected contribution expressions, joined by comma and space |
| `region` | Board panel `x, y, width, height` in pixels |
| `x`, `y`, `width`, `height` | Individual board coordinates for authored location wording |
| `must_not_control` | Declared exceptions, only where the author places this optional marker |

A shared board needs its panel location: place `region`, or all four coordinate
fields, in the reference instruction with wording that identifies their meaning.
Every authored reference direction consumes its `attachment_number` and
`controls`; a number by itself does not deliver the selected contribution.
The requirement applies to the actual primary text selected for transport.
An unused working text need not repeat that direction. A target with verified
`native-fields` reference transport receives the selected scope through its
declared native mappings and needs no textual reference direction.

Preview the resolved text before dictionary or model grammar work:

```sh
python scripts/reference_delivery.py --prepared-set WORK/prepared.json \
  --prompt-file WORK/prompt.txt --out WORK/resolved-prompt.txt
```

Use `--image-input-plan PLAN --studio STUDIO` in place of `--prepared-set` for
an external input. The command returns the complete resolved text and its
source-to-final ranges. `--out` writes the same final UTF-8 bytes for vocabulary
search. Edit the original prompt and contribution owners; the resolved file is
an inspection surface. Normal preparation performs the same expansion before
checking grammar, vocabulary, limits and final input hashes.

The package retains authored literals and a derived `reference_text` record.
Its verifier recomputes the substitution from the bound references and compares
the actual transported text. For an external source request, markers belong in
the request's ordinary prompt field. The image-input builder expands that source
before schema and prompt checks; a materialized external plan retains the
derived record beside its final request. This record is produced by the compiler
from the work and carries no assessment or approval. The agent still reviews
the complete final text and actual media for meaning, source fit and intended
effect; successful substitution establishes delivery alone.

## Bind the actual transport

The following prepared-set commands apply to reference-runtime and Generation Package delivery.
An external request binds the same logical rows to its declared field paths and upload evidence.

After rendering or copying the actual transports, the reference preparation runtime derives their actual attachment mapping. For multi-image input, identical committed transport hashes and media types share one attachment. Logical reference rows retain their distinct sources, adoption, roles and subject uses. For a single-board input, every logical reference points to attachment 1 and its exact panel rectangle in pixels from the top-left, and a board with several source panels consumes one model image slot in total. Source hashes, transport hashes, roles and panel rectangles must agree with the prepared set.

The map is authoring input for the agent. Interpret its subject assignments, scopes and precedence into the selected depiction using [Prompt Composition](prompt-composition.md#prompt-assembly-and-review). Internal keys, numeric priorities and request field paths stay in the binding record. Identify delivered images by their actual order and use a panel location when necessary. A source panel identifies evidence; it does not prescribe the output layout.

```sh
python scripts/reference_delivery.py --prepared-set WORK/prepared.json
```

Pass the complete prepared-set document, not the raw array of selected source rows. Relative carrier paths resolve from the prepared-set file's parent by default. Use `--package-root WORK` only when those paths intentionally use another base. The inspector accepts the same selected pack runtime as preparation: supply `--state-file STATE --cache-dir CACHE --managed-root MANAGED` together, with any applicable `--pack-root ROOT` values.

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

This reads an existing prepared origin when the plan names one. Each binding records its exact request field, such as `["images",0,"uri"]`, for transport verification. External image numbers follow the actual array positions within each native media field shape; independent named media slots retain their declared field order. A prepared origin supplies the board region for each logical reference. Different sources may share one external field when they use the same verified carrier and uploaded value; their individual roles and scopes remain recorded. Author the reference instructions using the image positions and controls the target actually receives. Preparation verifies the exact request, image mapping and source bytes; the agent reviews whether the received prompt and media convey the assigned uses.

### Upload the selected media for one generation

For dispatcher work, `production_workflow.py execute` owns the upload. It reads
and verifies the sealed carrier bytes, invokes the selected service's declared
HTTP upload interface, and records the actual provider response and returned
media identifier before sending the generation request. The service definition
and transport own the upload fields and response shape.

#### Bind a hosted carrier URL

A transport declares whether its HTTP interface receives file bytes or imports
an existing media URL. For a URL-import interface, `task.upload_sources` binds
the actual prepared carrier file to its remotely readable URL. This synthetic
excerpt selects the hosted bytes of one Studio-relative carrier:

```json
{
  "upload_sources": [
    {
      "file": "work/reference-inputs/attachments/reference.png",
      "url": "https://assets.example.org/reference.png"
    }
  ]
}
```

Select this file and URL in `authoring.task.upload_sources` in the common
draft. The file is Studio-relative and must contain the exact carrier bytes
hosted at the URL. The builder measures its content and binds the URL to the
current prepared carrier by digest, so reordering references does not require
editing media indices or hashes. A shared board is one carrier even when it
supplies several logical references. Identical carrier bytes can share one URL;
conflicting URLs for the same bytes are refused.

Select the exact prepared image's URL from the owner's existing storage or an
available host interface. A local path is not a remotely readable URL, and the
adapter does not publish local files to create one. The generated authoring
source-file record preserves the selected bytes as evidence. A later change to
those saved file bytes is refused. When an edit removes or changes a carrier,
`build-inputs` drops its inherited URL selection; select the newly hosted carrier
file and actual URL when the changed input needs one. Preparation records the
source dependency and seals the URL with the carrier's hash, size and media
type. The URL-import transport verifies the provider's stored bytes against
that carrier before accepting its issued identifier. Byte-upload interfaces
receive the sealed content directly.

#### Recover uploads and cleanup

Each generation owns fresh uploads. Recovery of the same unfinished execution
can continue from its completed uploads; a new generation uploads again.
After the generation reaches a known terminal result and its returned images
are captured, execution deletes its uploaded input media through the selected
transport's declared deletion operation. A pending or failed cleanup remains
explicit and cannot cause another generation request. Each uploaded input gets
one deletion request. A deletion error, including a missing target, is recorded
without retrying that deletion; the saved images remain available for review.
An uncertain outcome can be queried by the original deletion request's
identifier without resending it. Saved source bytes,
upload responses and deletion records remain available for review after the
provider's temporary input is removed. An upload without its saved response
stays unknown.

#### Bind external media

External host interfaces follow their actual upload and deletion contracts.
Pass a local file only when the available host interface explicitly accepts
one, selecting `transport: {"local_file": true}` in the external input choices;
the builder derives its carrier path and execution uses its saved bytes.
Otherwise use a documented input it supports. Bind the identifier returned
for this generation and its upload evidence in the image-input plan's
`external_request.reference_fields`, then record the actual deletion result
after capturing the output. A provider response and an arbitrary local image
do not establish which bytes were uploaded. A host that lacks a required
operation needs an explicitly available interface; do not assume one exists.

#### Retain source and carrier evidence

Production preparation preserves the original source images and the actual
prepared carriers in the run. The review draft exposes both, with their
source assignments and transformations, so later review can inspect the same
pixels after live files move. A prepared run checks its saved bytes and current
execution authority when it sends; a new preparation resolves its selected
source eligibility. Use the recorded
submission evidence to establish which prepared media reached the target.

For prompt-artifacts, SVG-bundle, or no-reference delivery, never claim that model-visible attachments were sent. An unsupported target or missing selected transport is an explicit failure rather than silent reference omission. Targets and their observed limits are resolved from actual model records rather than fixed service names in this procedure.

Run `python scripts/reference_delivery_smoke_test.py` and the existing reference runtime tests. They test mappings and transport contracts, not whether a generator actually follows them.
