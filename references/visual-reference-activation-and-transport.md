# Visual reference activation and transport

Load this document only after a canonical record with linked visual evidence has been adopted, when the user supplies a reference, or when a reusable or generation-ready reference package is requested.

Choose the preparation owner from the source and execution path. Pack-backed evidence uses the Reference Use Plan below.
Supplied-image external edits use [Semantic instruction editing](runtime/semantic-instruction-edit.md) and its original-file bindings.
The authority and review principles apply to both; external editing does not require converting a raster into vector evidence.

## Activation gate

1. Inspect every adopted record.
2. Run asset lookup for that record.
3. Select only evidence whose authority matches the intended influence.
4. Assign each selected source an explicit role, scope and precedence under its preparation owner's contract.
5. Reject unnamed averaging between identity, pose, camera, color, material, lighting, and environment sources.

A prompt-only request does not call an image-generation API. It may still include selected SVGs when they materially support reuse. No-reference prompt-only output does not create empty reference manifests.

## Semantic reading

Use [Production direction](runtime/production-direction.md#form-a-prompt-from-an-image)
to determine the source contribution from the whole image and actual request
before dividing it into reference uses. Supplied raster images use that same
interpretation through their existing image-input owner. A selected complete
construction can span several roles. Those roles locate authority for its
parts; the prompt must still express the relationships that make them one
picture. A technical role boundary does not decide that an unmentioned source
relationship is incidental.

Treat an SVG as bounded visual evidence, not as the complete target image and not as a replacement for prompt authoring. Read three authorities together:

1. The user brief and resolved image intent define the target.
2. The complete linked canonical record explains what the selected evidence means through its title, description, prompt fragments, `image_promise`, `staging`, `defaults`, `performance_language`, `style_reference_guidance`, and failure modes when those fields exist.
3. The SVG supplies visible construction, appearance, layout, and technique only within the selected role.

User anchors and the resolved target override source presentation. Record knowledge names the reusable meaning; visible evidence shows how that meaning is depicted. Do not infer a semantic claim from a filename, gallery title, color patch, mask, or unexplained shape alone. When the record and image appear inconsistent, stop and review the evidence relation instead of choosing whichever is convenient.

Assess each source through these questions before composition. Record task-bearing decisions at the existing reference owner:

- `role`: exactly one intended influence for this use;
- `preserve`: visible properties that the source is authorized to carry;
- `replace`: source properties that the target deliberately changes;
- `add`: requested target properties absent from the source;
- `omit`: incidental, conflicting, masked, low-quality, or out-of-scope source properties;
- `prompt_clause`: positive final-state wording that binds the accepted evidence to the target;
- `precedence`: the source's order among other uses.

One SVG may serve several intended influences through separate declared uses.
Keep their scopes distinct even when the same pixels carry multiple properties.
The assessment is not a prose inventory for the final prompt. In particular,
an omitted incidental detail needs no model-facing permission or denial.

Connect the assessment to the task's existing applied sources, direction and
criteria. For each relevant attribute, identify the subject, the readable source
region, the target value or intended change, and how the output can demonstrate
it. Record the selected interpretation in `direction.decisions` when it needs
an authored decision. Preserve the distinction between an observed source
feature, a chosen depiction and an unresolved detail. A reference's useful
coverage and authority determine its role, including a complete character sheet
as primary evidence where it supplies the required design.

Resolve scope overlaps at the attribute level using
[Exact reference delivery](runtime/reference-delivery.md#resolve-the-attributes-needed-by-this-image).
Carry every required feature through the resulting source assignments or target
description. Complementary views and an explicitly scoped exception can coexist;
the final instruction states which source controls the attribute that matters.

## Role map

Use the following semantic boundaries for canonical reference uses. External semantic plans may name other explicit roles, such as `scene` or `geometry`.
Technical artifacts narrow authority; they never widen it.

| Intended influence | May carry | Must exclude unless separately declared |
| --- | --- | --- |
| `identity` | species, anatomy, proportions, permanent markings, stable palette regions, mane, ruff, hair, grooming topology, identity equipment | pose, camera, expression, temporary state, clothing, room, source lighting |
| `pose-camera` | body arrangement, support, weight, contact, overlap, depth, viewpoint, perspective, crop, focal order | source identity, clothing, palette, environment identity, finish |
| `outfit` | garment silhouette, layers, closures, seams, fit, material construction | body identity, source pose, source wearer, room |
| `environment` | room or landscape layout, support surfaces, depth cues, spatial relationships, background objects | source subject identity, subject pose, clothing, source performance |
| `prop-accessory` | object construction, placement, grip, attachment, scale, contact path | source owner, unrelated pose, unrelated scene, incidental objects |
| `local-color` | named local color regions and their relationships | lighting direction, gloss, shadow topology, identity not defined by those colors |
| `lighting` | source direction, apparent size, contrast, softness, color, shadow placement when preservation is authorized | object identity, base material, pose, local color not caused by light |
| `surface-finish` | line economy, value grouping, edge handling, texture abstraction, highlight budget, rendering finish | subject identity, scene content, pose, wardrobe, source-specific text |

Apply retained design and local-color facts through the selected
[representation](runtime/render-contract.md#represent-the-selected-design).
The table separates source authority; it does not require unchanged rendered
pixels when the commission selects another treatment of those facts.

For a request such as "use this character with that pose and this background," create three uses even if two uses originate from one SVG. Identity authority decides the target character. Pose-camera authority decides body geometry. Environment authority decides the setting. If the pose source depicts a different identity, body plan, outfit, expression, or room, those properties are contamination, not inspiration.

### Registered Character Sheet identity with other evidence

A registered Character Sheet does not create a second reference system. Once its accepted identity artifacts are linked to the character's canonical record, they enter the same Reference Use Plan as every other active pack artifact. Use the character record with `intended_influence=identity`; add separate record uses for `pose-camera`, `outfit`, `environment`, `prop-accessory`, `local-color`, `lighting`, or `surface-finish` only when those influences are explicitly selected for the current image. The resulting Prepared Reference Set is the single model-facing package.

The identity role is not a blanket veto on every visible difference, and non-identity roles are not permission to borrow the source individual. Scope decides the conflict. Stable anatomy, proportions, permanent markings, and other identity-fixed facts stay under identity authority. Body arrangement and viewpoint may come from `pose-camera`; garment construction may come from `outfit`; light behavior may come from `lighting`. Do not classify anatomical construction as a generic non-identity attribute merely because it is visible in another source. If anatomy itself is intentionally changed, that is an identity/form decision and must be represented by the owning identity or form contract.

Generation Package preparation has two provenance paths: pack-backed Reference Use Plans and supplied-file-only preparation. Do not claim a fully audited mixed package when a Character Sheet board is only a local file and other sources are pack artifacts. Register the sheet identity into the pack/catalog path first, or keep all references in supplied-file preparation. External edits retain selected local originals and their acquisition evidence in the semantic binding. Never splice prepared outputs by hand.

## Reference-to-prompt synthesis

Develop the target depiction from the commission and selected sources under
[Prompt Composition](runtime/prompt-composition.md#select-the-depiction).
Use the resolved contribution and source-based comparison from Production
direction while carrying that depiction into the actual input.

1. State the intended event or visual purpose, its present situation and
   organizing relationships at the chosen degree. Establish any premise needed
   to understand the action, performance or visual construction through the
   actual prompt and supplied media.
2. Assign the delivered references to their subjects and permitted uses in
   the authored prompt, guided by the canonical bindings. Express required
   precedence, including the distinction between the source of a subject's
   design and the treatment applied to it here.
3. Describe target changes as the chosen result. Keep a required exclusion when
   it has independent meaning; do not manufacture an opposite for every deletion.
4. Specify geometry where ownership, contact, depth, framing or the arrangement
   of large forms and intervals carries the selected construction. Keep the
   strength and scope of its contrast, movement and treatment relationships.
5. Apply record knowledge according to its role in the selected depiction.
   Keep fuller histories, source decisions and conclusions outside that
   depiction at their owners. A record's defaults, possible failures and
   example objects are not automatic additions.
6. Add required target properties absent from the references. Let a sheet's
   relevant views supply its declared identity or wardrobe information.
7. Reconstruct the picture from the final prompt, supported controls and actual
   ordered media, using only source assignments conveyed in that input. A role
   recorded in a working plan but absent from the request is not an instruction
   the model has received. Compare that picture with the original commission
   and the retained source-based reading, not only with the subset already
   described in the prompt.

Use the committed delivery mapping for that final comparison, including shared
attachments and board regions. Inspect the actual carriers for legible evidence
of the attributes being assigned. Compare the requested appearance with the
adopted source regions before using words such as `exact` or `preserve`; express
the specific shape, placement or relationship when it is needed to convey the
target. Keep source decisions and unresolved coverage with the existing task
records so that image review can assess the same requirements.

Trace a consequential mismatch to its owner. A missing contribution calls for
source interpretation or input repair. A softened relation calls for the
intended degree. Competing source appearances call for scoped precedence and
representation. An actual limitation of attachment handling or control calls
for a supported transport or production method. A clear input followed by a
different returned image is a realization issue to assess from that output.
Attaching a rich reference does not guarantee that it restores a relation the
prose weakens or excludes. Conversely, a visible match cannot be attributed to
text alone when the model received the matching image.

For a consequential unresolved reading of the combined input, use the existing
[competing-realization test](runtime/prompt-composition.md#competing-realization-test).
It can examine whether a materially different whole still satisfies the actual
request sent to the model. Its later comparison with the commission and sources
does not replace them with the author's interpretation. Use its declared
independence limits; no additional form or general second review is required.

Synthetic example with a character sheet and an environment source:

```text
Illustrate a potter shaping the rim of a clay bowl at a wheel. The character sheet defines the potter's appearance and work clothes; Image 2 defines the studio interior. The potter looks at the rim while guiding it with both hands. Make the shaping action readable. Use the sheet's illustrated finish throughout the scene.
```

The scene specifies what happens; the references supply their assigned
construction and appearance. A sheet's alternative views remain evidence for
one character rather than additional people or a requested output layout.

## Layer roles

- Layer A may control stable identity, shape, markings, local color, clothing construction, and accessory construction when authorized.
- Layer B controls only the named evidence channel, such as structure, value, color, saturation, highlight candidates, or subject mask.
- Layer C is a transport recipe. It does not create new visual authority.

Choose the artifact that matches the declared job:

- use `faithful-archival.svg` when authorized identity, outfit, prop-accessory, local-color, lighting, or surface-finish evidence must remain visible;
- use `structural-line-tone.svg` for pose-camera, support, contact, perspective, crop, or environment layout without importing source color as authority;
- use color, saturation, specular, and subject-mask audit artifacts only for their named measurement channels;
- never treat a mask, placeholder color, audit overlay, or simplified structural projection as faithful subject appearance.

If one faithful SVG contains useful identity but harmful scene state, keep the identity scope explicit in both the plan and prompt. A technical carrier cannot remove semantic contamination by itself.

## Conditional artifacts

These artifacts belong to canonical reference preparation. External instruction edits retain their semantic plan and exact original files instead.

- Deliver `reference-use-plan.json` only when one or more references are selected or a reusable reference package is requested.
- Deliver `surface-lighting-plan.json` only when source lighting or material response must be explicitly preserved, rescoped, or replaced.
- Deliver `prepared-reference-set.json` only for a target-specific or generation-ready transport.
- Deliver the selected SVG files themselves. A path or hash alone is not delivery.

## Target transport

For a target that accepts several images, keep identity, structure, color, and lighting evidence as separate ordered inputs. For a target that accepts one image, build one labeled disposable board and retain the panel manifest. Rasterized carriers are build artifacts and do not replace the source SVG.

Match transport claims to the exact interface:

- When the interface supports several ordered images but no per-image role controls, preserve separate carriers and bind each order position to its prompt clause.
- When it supports role-specific adapters, weights, or controls, map each setting to the same semantic reading; a high weight never grants broader authority.
- When it accepts only one seed image for image-to-image, treat that input as holistic coupling. Do not claim independent character, pose, and environment control. Use a reviewed single board or one coherent carrier only when the adapter supports it, disclose the reduced control, or stop and revise the plan.
- When it accepts raster only, rasterize the selected SVG deterministically. Do not send raw SVG, replace it with a nearby artifact, or redraw it from memory.

If the selected model cannot express the required role separation, change the technical path without changing the image intent. A different intermediate model may prepare a role-integrated carrier only when the user permits that model path and the final generation still preserves the declared authority and provenance.

**Reference hygiene.** Prepare reusable character evidence with a sharp face,
even light and a readable outline. A plain ground, one clearly assigned subject
and a front or three-quarter view provide a useful starting arrangement; front,
profile and three-quarter views can supply complementary coverage. Around a
thousand pixels or more on the short side is a preparation guideline. Judge the
actual face and required detail regions at the delivered size, including their
size within a sheet or board. Select additional views or details when angle,
occlusion, several subjects, filtering or exposure obscures a needed attribute.
Choose their number from the task's coverage and the interface limits. A clear
full sheet can remain the principal reference. The prompt supplies the target
place, action, light and camera, together with the assigned uses of the readable
reference evidence.

**Service records.** How a service is called is recorded once, in the `service-profiles` resource of the active pack: endpoint, authentication shape, request envelope, operations, asynchronous delivery and polling, error shape, and limits, with one observation date and one source for the whole record, because a record is refreshed as a whole from the service's documentation. A model's behaviour is not in that record; a model record carries it, and an offering inside the model record says how the model is exposed on one service (its identifier there, the request keys per input mode, and the limits that service enforces, such as a duration band). The same model on a second service is a second offering, not a second record. Scripts read the record rather than carrying endpoints of their own, and print its observation date beside what they send, so an ageing record is seen before it fails.

**Composition and rendering across interfaces.** Choose this path when the
selected rendering interface cannot directly carry the required reference
roles, but supports image-to-image input and the user permits an intermediate
composition. Prepare one coherent picture from the assigned character panels
and scene sources, expressing each figure's appearance and state with that
figure. The rendering step receives that picture and the requested treatment.
Preserve the composition and change the intended finish through the controls
the exact interface actually provides. Choose strength from that control's
documented meaning and inspected results: the amount that retains a required
pose, face or garment while changing its treatment depends on the model,
input and operation.

A sampling seed supplies no character-sheet content. Carry a recurring design
through the supported image, reference or trained-identity inputs and the
description needed by the target. Record those inputs and evaluate identity
across the resulting images; reusing a seed alone establishes no continuity.
An interface that accepts only a holistic image-to-image input cannot thereby
claim independently controlled character, pose and environment roles.

In the rendering prompt, describe the selected finish and the visible content
needed to preserve the intended picture. Bind attributes to their subjects
using the target's supported syntax and controls. Attribute transfer between
figures is a possible failure to inspect, not an inevitable effect of every
tag. If it occurs, repair the affected relation through supported wording,
regional controls, masks or another authorized operation. A proposed content
change still needs the source authority and direction that justify it; an
extra rendering step creates no new authority. Register the composition and
rendering as separate assets, retaining their exact inputs and relationship.
The composition can be accepted as a source even when the rendered image is
the selected final frame.

## Surface and lighting

Color evidence does not determine gloss or shadow. Resolve source-lighting authority as `preserve`, `rescope`, or `replace`. Separate form, cast, contact, and ambient-occlusion shadows from broad sheen, hard specular, rim light, reflection tint, roughness, wetness, and material response. A specular audit marks highlight candidates only.

## Review

Use the preserved attributes and requested changes from production direction
and the reference assessment as the existing review criteria. Compare the
actual candidate with its assigned source regions, taking the target view and
accepted variation into account. Record the visible result, its interpretation
against the criterion and the limits of the observation. Use `indeterminate`
when inspected evidence cannot resolve a criterion, and `not-assessed` for a
criterion that has yet to be inspected. Input integrity and visual realization
remain separate findings.

First compare the combined construction at its requested scope. Correct
identity, readable words and plausible contact can coexist with a different
balance, viewer relationship or visual force. Then inspect each declared role
after generation:

- identity drift: the target character changed or inherited the pose source's subject;
- geometry drift: pose, support, contact, crop, or depth no longer matches the pose-camera authority;
- environment drift: the setting lost its layout or imported a subject from the environment source;
- source-state leakage: source expression, clothing, wetness, injury, props, text, or lighting appeared without authority;
- technical leakage: masks, placeholder colors, audit shapes, board labels, or rasterization artifacts entered the image;
- prompt omission: requested additions or replacements never became visible.

Repair the failed role first. Change its prompt clause, carrier, weight, or precedence without globally strengthening every reference. If the interface cannot isolate the repair, treat that as a capability limit rather than repeatedly rewriting unrelated prompt content.

Link the repair to the existing review observation and affected direction
decision. State the desired resulting attribute and retain the working features
of the candidate. Choose the prompt, reference, transport or supported editing
operation that addresses the observed cause, then evaluate the next actual
image against the same retained and changed requirements.
