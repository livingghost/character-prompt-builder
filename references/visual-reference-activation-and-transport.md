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

For a request such as "use this character with that pose and this background," create three uses even if two uses originate from one SVG. Identity authority decides the target character. Pose-camera authority decides body geometry. Environment authority decides the setting. If the pose source depicts a different identity, body plan, outfit, expression, or room, those properties are contamination, not inspiration.

### Registered Character Sheet identity with other evidence

A registered Character Sheet does not create a second reference system. Once its accepted identity artifacts are linked to the character's canonical record, they enter the same Reference Use Plan as every other active pack artifact. Use the character record with `intended_influence=identity`; add separate record uses for `pose-camera`, `outfit`, `environment`, `prop-accessory`, `local-color`, `lighting`, or `surface-finish` only when those influences are explicitly selected for the current image. The resulting Prepared Reference Set is the single model-facing package.

The identity role is not a blanket veto on every visible difference, and non-identity roles are not permission to borrow the source individual. Scope decides the conflict. Stable anatomy, proportions, permanent markings, and other identity-fixed facts stay under identity authority. Body arrangement and viewpoint may come from `pose-camera`; garment construction may come from `outfit`; light behavior may come from `lighting`. Do not classify anatomical construction as a generic non-identity attribute merely because it is visible in another source. If anatomy itself is intentionally changed, that is an identity/form decision and must be represented by the owning identity or form contract.

Generation Package preparation has two provenance paths: pack-backed Reference Use Plans and supplied-file-only preparation. Do not claim a fully audited mixed package when a Character Sheet board is only a local file and other sources are pack artifacts. Register the sheet identity into the pack/catalog path first, or keep all references in supplied-file preparation. External edits retain selected local originals and their acquisition evidence in the semantic binding. Never splice prepared outputs by hand.

## Reference-to-prompt synthesis

Select the target depiction under
[Prompt Composition](runtime/prompt-composition.md#select-the-depiction), then
bind the relevant source evidence to it.

1. State the intended event or visual purpose and its necessary relationships.
2. Assign the delivered references to their subjects and permitted uses in
   the authored prompt, guided by the canonical bindings. Express required precedence.
3. Describe target changes as the chosen result. Keep a required exclusion when
   it has independent meaning; do not manufacture an opposite for every deletion.
4. Specify geometry where ownership, contact, depth or framing carries the
   intended action or a reconstruction-critical detail.
5. Use record knowledge only for the selected depiction. A record's defaults,
   possible failures and example objects are not automatic additions.
6. Add required target properties absent from the references. Let a sheet's
   relevant views supply its declared identity or wardrobe information.
7. Check the prompt against the actual ordered inputs. Together they must
   communicate the intent, without narrating irrelevant source contents.

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

**Reference hygiene.** Whatever the surface, a character reference works best at about a thousand pixels or more on the short side, with a sharp face, even light, one character, a plain ground, and a front or three-quarter view; two or three views of the same individual (front, profile, three-quarter) anchor identity across angles better than any one of them. An extreme angle, an occluded face, a second person, a heavy filter, or a dark exposure weakens the anchor. The prompt then carries place, action, light, and camera, and does not restate or contradict what the reference shows.

**Service records.** How a service is called is recorded once, in the `service-profiles` resource of the active pack: endpoint, authentication shape, request envelope, operations, asynchronous delivery and polling, error shape, and limits, with one observation date and one source for the whole record, because a record is refreshed as a whole from the service's documentation. A model's behaviour is not in that record; a model record carries it, and an offering inside the model record says how the model is exposed on one service (its identifier there, the request keys per input mode, and the limits that service enforces, such as a duration band). The same model on a second service is a second offering, not a second record. Scripts read the record rather than carrying endpoints of their own, and print its observation date beside what they send, so an ageing record is seen before it fails.

**Two surfaces, one carrier.** Surfaces divide by what reaches them. A composition surface takes reference images and follows a prose description of the picture; a rendering surface holds a design's line, colour, and finish but takes no reference, or takes one only as a seed image for image-to-image. A registered sheet reaches a rendering surface in exactly one way: as an image. A tag prompt with the character's seed carries none of it. The seed reproduces one prompt's picture and, once the prompt changes, reproduces nothing; two stills of the same character made from tags and a seed are two designs, whatever the sheet says. So the standard path for a still of a recurring character on such a surface has two steps: the composition surface draws the picture from the sheet's panels and the scene references, with each figure's garments and state written in prose beside that figure; the rendering surface then redraws that picture as a seed image at a strength that keeps the composition and replaces the finish (about half). The rendering step's text names the style and what is already in the picture, and nothing else: a tag reaches every figure in the frame, so a garment or an expression tagged for one of two figures is drawn on both. What the composition decided is not restated at the rendering step, and what the picture does not show is not named at either. Register the composition and the rendering as two assets: the first can be accepted as the source even when the second is the frame that goes on.

## Surface and lighting

Color evidence does not determine gloss or shadow. Resolve source-lighting authority as `preserve`, `rescope`, or `replace`. Separate form, cast, contact, and ambient-occlusion shadows from broad sheen, hard specular, rim light, reflection tint, roughness, wetness, and material response. A specular audit marks highlight candidates only.

## Review

Review each declared role independently after generation:

- identity drift: the target character changed or inherited the pose source's subject;
- geometry drift: pose, support, contact, crop, or depth no longer matches the pose-camera authority;
- environment drift: the setting lost its layout or imported a subject from the environment source;
- source-state leakage: source expression, clothing, wetness, injury, props, text, or lighting appeared without authority;
- technical leakage: masks, placeholder colors, audit shapes, board labels, or rasterization artifacts entered the image;
- prompt omission: requested additions or replacements never became visible.

Repair the failed role first. Change its prompt clause, carrier, weight, or precedence without globally strengthening every reference. If the interface cannot isolate the repair, treat that as a capability limit rather than repeatedly rewriting unrelated prompt content.
