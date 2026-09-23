# Production Specification

A Production Specification is the editable, scene-specific bridge between an approved art direction, resolved character state, and one exact image-generation request. It is not the canonical identity contract and it is not the State Event Ledger.

## Ownership boundary

The related artifacts have different jobs:

- **Character Identity Contract**: stable identity across scenes and time.
- **Era, Form, and Appearance contracts**: approved long-term, topology, and presentation variants.
- **State Event Ledger**: the append-only record of approved changes over story time, resolved here and never authored here.
- **State Snapshot**: the resolved truth for one character at one story time.
- **Scene Context Snapshot**: relationships, environment, wardrobe, inventory, props, disclosure, and planned transitions for one scene.
- **Visual State Projection**: what the current camera should visibly express, what is occluded, which performance cues are required, and which references or text anchors should carry those facts.
- **Asset Render Specification**: the exact purpose, view, crop, coverage obligations, and target assumptions for one generated image.
- **Production Specification**: the coherent render specification compiled from those inputs for one image.

A Production Specification may be regenerated whenever scene-visible semantic inputs change. Stable identity and approved history remain in their owning artifacts rather than being overwritten inside the scene specification.

## State modes

### Stateless

Use `state_context.mode: "stateless"` for a one-off image and for the first images of a character, when no approved temporal canon exists. A stateless `state_context` holds only the mode and optional notes, and the builder seals the stateless lineage.

For every such image, including prompt-only delivery, draft the smallest valid specification for its subject, replace each `"unspecified"` the author decides, and validate it before final prompt delivery or packaging:

```bash
python scripts/production_spec.py draft production-spec.json --model grok-imagine-image-2.0 \
  --brief "An old lighthouse keeper watches the sea from a window at dawn." \
  --kind human --framing upper-thigh --continuity undecided
python scripts/production_spec.py validate production-spec.json --require-content
```

The draft prints the builder arguments that name its subject (synthetic brief):

```json
{"created": "production-spec.json", "sha256": "a28ec0d3f9a951ae75b7d10294aeaab54867d6b0f7424408d00bb8d5c7326eae",
 "build_with": ["--production-spec-file", "production-spec.json", "--continuity", "C01=undecided"]}
```

Author the current scene directly rather than patching an older prompt into apparent compliance.

### State-aware

Use `state_context.mode: "state-aware"` when the image belongs to a managed series. The specification must carry:

- the sealed State Lineage hash;
- a Scene Context reference;
- for every subject, Identity Contract, State Snapshot, and Visual State Projection references;
- the resolved current state that is materially visible or performance-relevant in this image.

The specification never reconstructs state from chat memory. It consumes reviewed and hash-sealed protocol artifacts.

## Subject record

Each materially distinct subject defines:

- `id` and canonical `domain`;
- `identity`: the stable features relevant to this image, projected from the Identity Contract when one exists;
- `current_state`: visible and performance-relevant deltas resolved for this story time;
- `proportions_and_form`;
- `surfaces_and_markings`;
- `distinctive_details` using `references/distinctive-detail-specification.md`;
- `performance` derived from felt, displayed, masked, physiological, relationship, and scene context, using `performance-language.schema.json`;
- `wardrobe_and_accessories`, including layer and condition state;
- `pose_and_body_geometry`;
- `props_and_contacts`, including current possession, attachment, support, and depth order.

A subject adds only the structures this image depends on:

- `frame_character`: an authored overall form and declared structure map, with specialist detail only where applicable;
- `load_bearing_part_measurements`: landmark-anchored dimensions for anatomy, garments, accessories, props, or mechanical parts that must reconstruct consistently;
- `accessory_geometry`: count, site, attachment, dimensions, repeated elements, material, color, layer order, clearance, pose response, articulation, visibility, and continuity for every reconstruction-critical accessory;
- `growth_geometry`, declaring only relevant carried or projecting structures without a mandatory anatomy inventory;
- `garment_geometry`, containing one geometry contract per materially visible garment;
- `head_and_face`, `hands`, `legs_and_feet` and `gaze_and_head` convenience summaries, or `structure_notes` for authored parts.

A subject that names an `identity_contract_ref` also carries its morphology references and `resolved_morphology`, as [Subject morphology resolution](#subject-morphology-resolution) describes. A state-aware subject also names `state_snapshot_ref` and `visual_projection_ref`, and carries `growth_geometry`.

Do not force an unrelated structure into a human-named summary. Omit inapplicable optional summaries and use the declared structure IDs.


## Performance language

Use `references/performance-language-specification.md` for coordinated character acting. `subjects[].performance` is a structured performance-language record separating felt emotion, displayed emotion, masked or conflicted emotion, intent, viewer or partner relationship, intensity, temporal phase, visible channel cues, interpretation candidates, the selected interpretation, ambiguity notes, and the final prompt projection.

Channel cues record observation and affirmative visual instruction separately. This lets a source image retain several plausible readings while the current image intent selects one. Visible cues may include eyes, lids, brows, mouth, tongue, jaw, blush, tears, sweat, breath, head, shoulders, spine, hands, feet, distance, contact, ears, tail, whiskers, ruff, wings, crests, sensors, optics, manipulators, panels, indicators, actuators, and ventilation.

The Visual State Projection owns which current cues must be visible. The Production Specification composes those cues with the current pose, camera, support, contact, environment, and art direction. A cue that is hidden by crop or occlusion remains state knowledge but does not appear as a visible claim in the prompt.


## Camera framing contract

`camera` uses `camera-framing-contract.schema.json`. A repeatable shot records shot scale, distance class, subject-relative distance, optional human-scale metre guidance, camera height against a body or environmental landmark, pitch, yaw, roll, lens behavior, frame occupancy, exact crop landmarks, eye-line position, nearest form, perspective scale change, required visible elements, allowed off-screen elements, focal sequence, and stability invariants.

The subject-relative measurement is authoritative across humans, animals, creatures, and robots. A metre range is a translation aid rather than a replacement for the subject-relative distance.

## Garment and growth contracts

`subjects[].garment_geometry` and `subjects[].growth_geometry` store only declared constructions. Contracts use stable-ID structure maps; detailed construction is recorded in each structure's geometry. `head_and_face`, `hands`, `legs_and_feet` and `gaze_and_head` remain optional convenience summaries, with `structure_notes` available for author-owned IDs. Frame geometry need not invent a face or muscle. Permanent geometry, approved variations and temporary state retain separate authority. See [Declared Structures Runtime](runtime/declared-structures.md).

## Crop completeness

Every body region the pose implies is either visible, stated to continue out of frame at a named edge, or resting on or occluded by a named surface. A region that is none of these tends to render as a termination: an unwritten lower body becomes a torso ending at the ribs. Record the exit edge against the actual structure ID; a specialized summary such as `legs_and_feet.crop` is appropriate only when that structure exists. In a close crop, continuation outranks visibility: demanding that the figure be fully visible makes the camera pull back and changes the composition. For a robot, hands may be manipulators and gaze may be optic direction. For an ordinary animal, performance is expressed through natural posture and sensory orientation.

## State-aware compilation

Compile only the current visual result, not the full history.

```text
Identity Contract
+ optional Era / Form / Appearance Contract
+ resolved State Snapshot
+ Scene Context Snapshot
+ Visual State Projection
+ Asset Render Specification
+ chosen art direction and production knowledge
→ Production Specification
```

Examples:

- A transferred pendant is omitted when the Inventory State says another character now carries it.
- A persistent ear notch is preserved when the ear is visible, but remains in occluded-state metadata when a helmet hides it.
- Felt fear with a professional public mask becomes controlled facial acting, shallow breath, and one tension cue rather than an abstract emotion label.
- Heat and humidity may produce an Appearance Adaptation Proposal such as rolled sleeves or damp fur; the proposal affects canon only after approval.
- A flashback resolves the snapshot at the earlier story time and selects references valid for that time range.

## Visual language

The specification records separate roles:

- optional universal aesthetic core;
- zero or one concrete style family;
- one domain realization for every materially different subject domain;
- zero or one rendering profile;
- compatible atomic aesthetic touches.

A style family is an indivisible concrete drawing grammar. When selected, use its line, form, value, highlight, color, surface, background, and detail systems together. The linked rendering profile supplies the medium envelope and scoped negative boundary. Do not append two full grammars as independent tags.

## Modular control

A field the author does not decide holds the string `"unspecified"`: free text, each `camera` field and each `performance` field alike. An optional structure the image does not depend on is left out. Either is preferable to invented filler. A sparse portrait may need little more than the draft; a multi-character contact scene, reference sheet, state transition, or recurring series image may need a complete one.

## Prompt assembly

Translate the reviewed specification into fluent English. Preserve hierarchy and relationships rather than dumping field names. The final prompt should express:

1. subject identity and current visible state;
2. action, expression, relationship, and performance;
3. composition and camera;
4. aesthetic taste, center of appeal, and appeal strategy;
5. environment and lighting;
6. medium, line, shape, color, surface, and finish;
7. critical construction invariants.

After assembly, read the prompt alone and compare the likely picture with the image intent, Visual State Projection, Asset Render Specification, and current State Snapshot. Declare the reference mode as `prompt-only`, `prompt+1`, or `prompt+N`. For every image source, record its semantic role and decide whether it may govern permanent identity, target scene-conditioned construction, or another narrow visual property. Audit source scene-specific character state and source-render context separately. An identity-only source may not transfer gaze, expression, mouth state, pose, action, contact, support, physiology, surface condition, grooming condition, wardrobe, inventory, relationships, viewer awareness, environment response, current form, camera, crop, light, or finish unless an owning target-state or scene authority explicitly requires that property.

Activate every pack-backed reference through one explicit Reference Use Plan. Each plan decision binds an active canonical record to one intended influence, resolves only artifacts linked to that record, assigns narrow authority and exclusions, and commits the resulting order. If a State Protocol Reference Selection is present, reconcile every activated source and intended influence against that state authority. A plan-null prepared set may contain only explicit `supplied-file` sources; it cannot introduce a pack artifact or fabricated pack identity.

Prepare one canonical Prepared Reference Set for the target model. Each prepared item preserves its authoritative `source` and adds the exact model-facing `transport`, with independent media types, hashes, and derivation. Prompt-artifact transport copies the exact selected source bytes. A direct model transport retains source bytes when supported. When `gpt-image-2.5-flare` receives a selected safe SVG source, prepare a deterministic PNG from that same artifact because its declared input media types are PNG, JPEG, and WebP; commit the rasterization derivation instead of substituting different evidence. Source-lighting `preserve` is authorized only by an item whose intended influence is `lighting` and whose technical role is `faithful-archival-vector`; a `specular-audit` item alone supplies candidate highlight evidence, not complete shadow and material-response authority. `source_evidence_roles` stores the unique semantic roles of exactly those complete lighting-evidence items and is recomputed by validation. Without that evidence, leave preservation explicitly unresolved or declare target lights and material responses with `rescope` or `replace`. Unresolved surface-lighting decisions block model-facing execution.

The reviewed effective prompt, canonical authority preamble, Prepared Reference Set, exact carrier bytes, derivations, and order form one committed generation input. `prompt-only` commits an explicit empty Prepared Reference Set with a structured zero-reference reason. A Generation Package copies every carrier into its package-relative companion, publishes the JSON and companion transactionally, and remains verifiable after both are moved together. The verifier rechecks the complete contract and forwards only the verified prompt and carrier paths. If any selected source cannot be prepared or accepted by the target, stop before packaging; do not omit it or silently continue with text alone.

## Distinctive details

Use `subjects[].distinctive_details` for any localized feature whose location, laterality, scale, shape, color, depth, edge, or visibility matters. Preserve subject-relative left and right, anchor measurements to stable anatomical or mechanical landmarks, and leave hidden continuation unspecified. The Identity Contract owns stable details; the State Snapshot owns temporary or event-derived changes; the Visual State Projection decides whether they must be visible in the current image.

## Relationship to series locks

A series lock is a lightweight operational view. It points to an approved Identity Contract, current Era/Form/Appearance contracts, and the current State Snapshot or Visual State Projection. It may summarize those sources for quick use, but it does not redefine them.

When a conflict appears:

1. determine which owning artifact is wrong;
2. revise the owning artifact through its canonical workflow;
3. rebuild the snapshot, projection, specification, and series lock;
4. rebuild the Generation Package because every downstream hash changes.

Do not treat a scene-specific Production Specification as the source of stable identity or approved history.


## Subject morphology resolution

A subject that names an identity contract carries:

- `species_morphology_profile_ref`;
- `individual_morphology_contract_ref`;
- `resolved_morphology`.

`resolved_morphology` is the shot-specific anatomy contract, and the subject's `frame_character` and `load_bearing_part_measurements` equal its own. It lists visible feature instances, hidden or out-of-frame features, active form, surface map, feature relationships, expression channels, communication tools, current state deltas, count and attachment checks, crop requirements, and uncertainties. It prevents the prompt from silently dropping a tail, wing, limb, organ, digit, marking, or tool merely because it is outside the crop.

Use [Morphology and species contracts](morphology-and-species-contracts.md) before authoring an unfamiliar, fictional, hybrid, ordinary-animal, or mechanical body plan.

## Frame character and reconstruction-critical dimensions

Do not allow body-build terms to decide the bone and surface character implicitly. Resolve frame mass, surface character, soft-tissue padding, facial projection, body projection, and face-body coherence before prompt assembly. A thick-boned smooth-padded subject retains one rounded cheek mass, a submerged cheekbone landmark, a soft jaw corner, rounded joints, and broad mass handoffs even when the subject is extremely muscular. An angular subject uses a separately declared chiseled-angular frame.

Run the part-measurement pass for every one-off or recurring subject when size, count, spacing, angle, coverage, color, or surface is load-bearing. Prefer a local relationship and tolerance over an unsupported absolute unit. Examples include tag width against nose width, hoop diameter against ear height, tail thickness against pelvis width, wing span against torso width, or a mechanical panel gap against local plate thickness.

Accessory geometry is a first-class subject contract. A label such as `chain`, `dog tag`, `earring`, or `buckle` is not sufficient when reconstruction matters. Preserve the complete geometry, support path, attachment, repeated-element scale, material, color, layer order, pose response, and occlusion behavior.
