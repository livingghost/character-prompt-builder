# Visual reference activation and transport

Load this document only after a canonical record with linked visual evidence has been adopted, when the user supplies a reference, or when a reusable or generation-ready reference package is requested.

## Activation gate

1. Inspect every adopted record.
2. Run asset lookup for that record.
3. Select only evidence whose authority matches the intended influence.
4. Assign each selected source one unique semantic role and precedence.
5. Reject unnamed averaging between identity, pose, camera, color, material, lighting, and environment sources.

A prompt-only request does not call an image-generation API. It may still include selected SVGs when they materially support reuse. No-reference prompt-only output does not create empty reference manifests.

## Semantic reading

Treat an SVG as bounded visual evidence, not as the complete target image and not as a replacement for prompt authoring. Read three authorities together:

1. The user brief and resolved image intent define the target.
2. The complete linked canonical record explains what the selected evidence means through its title, description, prompt fragments, `image_promise`, `staging`, `defaults`, `performance_language`, `style_reference_guidance`, and failure modes when those fields exist.
3. The SVG supplies visible construction, appearance, layout, and technique only within the selected role.

User anchors and the resolved target override source presentation. Record knowledge names the reusable meaning; visible evidence shows how that meaning is depicted. Do not infer a semantic claim from a filename, gallery title, color patch, mask, or unexplained shape alone. When the record and image appear inconsistent, stop and review the evidence relation instead of choosing whichever is convenient.

For every source, write a compact semantic reading before prompt composition:

- `role`: exactly one intended influence for this use;
- `preserve`: visible properties that the source is authorized to carry;
- `replace`: source properties that the target deliberately changes;
- `add`: requested target properties absent from the source;
- `omit`: incidental, conflicting, masked, low-quality, or out-of-scope source properties;
- `prompt_clause`: positive final-state wording that binds the accepted evidence to the target;
- `precedence`: the source's order among other uses.

One SVG may serve several intended influences only through separate declared uses with separate preserve, replace, add, and omit scopes. Never widen one use merely because the same pixels contain other useful properties.

## Role map

Use the following semantic boundaries. Technical artifacts narrow these roles further; they never widen them.

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

The canonical runtime currently has two provenance preparation paths: pack-backed Reference Use Plans and supplied-file-only preparation. Do not claim a fully audited mixed package when the Character Sheet board is still only a local supplied file and the other sources are pack artifacts. Register the sheet identity into the pack/catalog path first, or keep all references in the supported supplied-file path. Never splice the two prepared outputs by hand.

## Reference-to-prompt synthesis

Compose the prompt from the final target outward, not by narrating the source images.

1. State the complete target subject and scene first. Make the final species, age presentation, body plan, activity, setting, and medium unambiguous.
2. Add one role-scoped clause per selected source in precedence order. Name both the accepted properties and the scope boundary.
3. Express changes as final positive construction. State the target identity's required anatomy, proportions, and markings rather than merely saying to remove the source identity.
4. Bind exact geometry in text whenever it is load-bearing: subject ownership, hand path, support, contact point, overlap, camera side, crop, prop attachment, and depth order.
5. Translate record knowledge into visible language. Use scene `staging` for geometry, `performance_language` for expression and physiological cues, `defaults` only for open choices, `image_promise` for the whole-image thesis, and `style_reference_guidance` only for the named finish channels.
6. Add requested properties absent from the references. A reference never cancels prompt requirements such as a darker room, stronger blush, more sweat, a different species, removed clothing, or an added prop.
7. Omit incidental source presentation affirmatively where possible and place residual contamination risks in the target adapter's supported negative channel.
8. Read the assembled prompt once without seeing the sources. It must still describe one coherent image. Then read it with the sources and confirm that every reference has one understandable job.

Do not use vague clauses such as `same as the reference`, `copy the SVG`, or `use reference 2 for the vibe`. Use clauses such as:

```text
Render [target subject] performing [target action] in [target environment]. Preserve reference A only for [authorized identity features]. Adopt reference B only for [pose, support, contact, camera, and crop]; replace B's source subject with the target identity and ignore B's identity, clothing, lighting, and environment. Use reference C only for [authorized environment layout, support surfaces, depth, and background objects]. Add [requested target properties absent from the references]. Omit [incidental source state, masks, placeholder colors, text, and unrelated objects].
```

This wording performs four distinct operations: preserve authorized evidence, replace conflicting source content, add target content, and omit contamination. The final prompt remains authoritative even when the endpoint also receives the SVG-derived carriers.

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

- Deliver `reference-use-plan.json` only when one or more references are selected or a reusable reference package is requested.
- Deliver `surface-lighting-plan.json` only when source lighting or material response must be explicitly preserved, rescoped, or replaced.
- Deliver `prepared-reference-set.json` and `reference-preamble.txt` only for a target-specific or generation-ready transport.
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

**Service records.** How a service is called is recorded once, in the `service-profiles` resource of the active pack: endpoint, authentication shape, request envelope, operations, asynchronous delivery and polling, error shape, and limits, with one observation date and one source for the whole record, because a record is refreshed as a whole from the service's documentation. A model's behaviour is not in that record; a model profile carries it, and an offering inside the model profile says how the model is exposed on one service (its identifier there, the request keys per input mode, and the limits that service enforces, such as a duration band). The same model on a second service is a second offering, not a second profile. Scripts read the record rather than carrying endpoints of their own, and print its observation date beside what they send, so an ageing record is seen before it fails.

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
