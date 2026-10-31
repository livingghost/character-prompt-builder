# Production Specification

A Production Specification describes the selected depiction for one image
artifact. It joins art direction, resolved character state and an exact
image-generation request. Stable identity and approved history retain their
own contracts.

## Ownership boundary

The related artifacts have different jobs:

- **Character Identity Contract**: stable identity across scenes and time.
- **Era, Form, and Appearance contracts**: approved long-term, topology, and presentation variants.
- **State Event Ledger**: the append-only record of approved changes over story time, resolved here and never authored here.
- **State Snapshot**: the resolved truth for one character at one story time.
- **Scene Context Snapshot**: relationships, environment, wardrobe, inventory, props, disclosure, and planned transitions for one scene.
- **Visual State Projection**: which identity, state and performance facts the artifact should express, with relevant occlusion and reference authority.
- **Asset Render Specification**: the exact purpose, view, crop, coverage obligations, and target assumptions for one generated image.
- **Production Specification**: shared depiction requirements and any local views arranged within one image artifact.

A Production Specification may be regenerated whenever scene-visible semantic inputs change. Stable identity and approved history remain in their owning artifacts rather than being overwritten inside the scene specification.

## State modes

### Stateless

Use `state_context.mode: "stateless"` for a one-off image and for the first images of a character, when no approved temporal canon exists. A stateless `state_context` holds only the mode and optional notes, and the builder seals the stateless lineage.

For a detailed composition or dispatcher request, draft the specification for
its subject. Replace each `"unspecified"` the author decides and add the camera
and performance records once decided. Validate before delivery or packaging:

```bash
python scripts/production_spec.py draft production-spec.json --root STUDIO --model grok-imagine-image-2.0 \
  --render-intent render-intent.json --brief "An old lighthouse keeper watches the sea from a window at dawn." \
  --kind human --continuity undecided
python scripts/production_spec.py validate STUDIO/production-spec.json --require-content
```

`draft` resolves the output and `--render-intent` below `--root`; an absolute path needs no root.
It refuses a relative path without `--root`, and it refuses an existing output, which it keeps.
Supply `--layout LAYOUT.json` when a region arrangement has been selected.
The draft preserves that authored layout and checks its subject references.
The draft prints the builder arguments that name its subject (synthetic brief):

```json
{"created": "production-spec.json", "sha256": "8f24ca9f06b2a96c63d35fa29f136f748b38e23af229bc37331b0d9386de4894",
 "build_with": ["--production-spec-file", "production-spec.json", "--continuity", "C01=undecided"]}
```

Name the file in the task's `generation.production_spec`. `build_with` applies only to a builder run whose task declares no specification.

Running the same `draft` again exits 1:

```json
{"ok": false, "errors": ["OUTPUT_ALREADY_EXISTS: output path names an existing file, which is kept: production-spec.json Choose a new output path."]}
```

Author the current depiction using [instruction selection](runtime/prompt-composition.md#select-the-depiction). The specification stores selected requirements and art direction, not every detail imagined while reading the brief.

### Object-only scenes

For a still life, product image or environment without character subjects, copy
`templates/production-spec-template.json` to a new Studio input file. Keep
`subjects: []`, `state_context.mode: "stateless"` and
`visual_language.domain_realizations: {}`. Fill the source brief, target model,
image promise and resolved rendering intent. Describe objects and their
relationships in `scene`, camera, art direction and construction invariants.
The `draft` command creates one character subject; an object-only specification
uses the existing empty-subject template directly.

A dispatcher task uses `generation.continuity: {}` for this specification.
Register an ordinary Studio storage destination, for example:

```sh
python scripts/studio.py character add product-scene --studio STUDIO --profile general
```

Then use a non-sheet slot with `recording.character: "product-scene"`,
`recording.slot: "candidate"`, `recording.subject_map: {}` and
`recording.sheet_panel: false`. The storage key organizes candidate files; it
does not add a depicted character, visual identity or subject domain.
Validate the complete specification with `production_spec.py validate
STUDIO/inputs/production-spec.json --require-content` before packaging.

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

## Layout and local views

Use `layout` when the artifact needs distinct content regions or views.
A region can hold a scene, detail, diagram, title, texture or another authored
element. Regions may overlap as layers or share a continuous surface. Their
relationships describe the intended integration or separation. Rendering
differences use `render_intent.regional_overrides`; they do not require
visible panel boundaries or a region for every brush or material.
A continuous scene can use the ordinary specification directly.
Selecting one output image does not select its internal arrangement.

The layout records:

- `arrangement`: the whole artifact's hierarchy, relative sizes, spacing and overlap;
- `regions`: each region's `id`, `placement` and positive `depiction`;
- `reading_order`, when selected: region IDs in the intended attention sequence;
- `relationships`, when needed: `from`, `to` and an authored `relation` between regions.

Reading order and depicted time are separate. State whether related views show
the same instant, successive moments, an enlargement or another relationship.
The order of the `regions` array alone grants no chronology.
Leave decorative regions outside `reading_order` when they have no selected
position in the attention sequence.

Each region may name `subjects` through `subject_id`. The root subject owns
shared identity and state authority. An occurrence owns its local `depiction`
and any selected pose, gaze, performance, clothing, contact or visible state.
Use `visible_elements` and `occluded_elements` only for distinctions the view
depends on. Repeated appearances refer to the same subject record.

Top-level scene, camera and lighting describe shared spatial requirements.
Local `scene`, `camera` and `lighting` record a region's differences. A local
camera is a complete contract. Flat lettering and graphic marks need only
their depiction; spatial contracts apply to depicted space.
When poses or visibility vary, author them locally and leave shared summaries
undecided unless a common requirement applies.

This synthetic excerpt shows different visibility for one subject:

```json
{
  "arrangement": "A large rear view beside a smaller front detail.",
  "regions": [
    {
      "id": "wide",
      "placement": "Large left region",
      "depiction": "A blue robot leans over a workbench, seen from behind.",
      "subjects": [{
        "subject_id": "mechanic",
        "depiction": "Its rounded blue back and planted feet establish the stance.",
        "occluded_elements": ["front display"]
      }]
    },
    {
      "id": "detail",
      "placement": "Small right region",
      "depiction": "A front close view shows the same robot's amber display.",
      "subjects": [{
        "subject_id": "mechanic",
        "depiction": "One raised white indicator line appears on the amber display.",
        "visible_elements": ["front display"]
      }]
    }
  ],
  "reading_order": ["wide", "detail"],
  "relationships": [{
    "from": "wide",
    "to": "detail",
    "relation": "The same instant, viewed from opposite sides."
  }]
}
```

Complete synthetic layouts are in `examples/composed-artifact/inspection-layout.json`,
`sequence-layout.json` and `poster-layout.json`. The poster uses no character
subjects or cameras. `inspection-prompt.txt` shows an authored depiction using
spatial descriptions rather than internal region or subject IDs.
The `study-page` layout, render intent and prompt combine a photographic
specimen, a corresponding line drawing and typography in one informational page.

The Asset Render Specification carries the same layout when state-aware
production uses it. Both artifacts seal its content, and graph validation
checks their agreement. Each managed subject still resolves one sealed
snapshot. Occurrence state stays within that authority. If a composition needs
distinct historical snapshots for one subject, resolve separate productions
before composing their approved outputs.

Validation checks unique region IDs, declared references and reading-order
structure. The author reviews spatial coherence, temporal meaning and local
visibility. Planned relationships become observed results only after reviewing
the generated artifact.


## Performance language

Use `references/performance-language-specification.md` for coordinated character acting. `subjects[].performance` is a structured performance-language record separating felt emotion, displayed emotion, masked or conflicted emotion, intent, viewer or partner relationship, intensity, temporal phase, visible channel cues, interpretation candidates, the selected interpretation, ambiguity notes, and the final prompt projection. A region's subject occurrence may carry its own performance for that view.

Channel cues record observation and affirmative visual instruction separately. This lets a source image retain several plausible readings while the current image intent selects one. Visible cues may include eyes, lids, brows, mouth, tongue, jaw, blush, tears, sweat, breath, head, shoulders, spine, hands, feet, distance, contact, ears, tail, whiskers, ruff, wings, crests, sensors, optics, manipulators, panels, indicators, actuators, and ventilation.

The Visual State Projection owns which current cues must be visible. The Production Specification assigns those cues to the selected views and their pose, camera, support, contact, environment, and art direction. A cue hidden in one view remains state knowledge for that view. Another selected region can carry it visibly.


## Camera framing contract

`camera` uses `camera-framing-contract.schema.json`, and the specification carries it once the shot is decided. A repeatable shot records shot scale, distance class, subject-relative distance, optional human-scale metre guidance, camera height against a body or environmental landmark, pitch, yaw, roll, lens behavior, frame occupancy, exact crop landmarks, eye-line position, nearest form, perspective scale change, required visible elements, allowed off-screen elements, focal sequence, and stability invariants.

The subject-relative measurement is authoritative across humans, animals, creatures, and robots. A metre range is a translation aid rather than a replacement for the subject-relative distance.

## Garment and growth contracts

`subjects[].garment_geometry` and `subjects[].growth_geometry` store only declared constructions. Contracts use stable-ID structure maps; detailed construction is recorded in each structure's geometry. `head_and_face`, `hands`, `legs_and_feet` and `gaze_and_head` remain optional convenience summaries, with `structure_notes` available for author-owned IDs. Frame geometry need not invent a face or muscle. Permanent geometry, approved variations and temporary state retain separate authority. See [Declared Structures Runtime](runtime/declared-structures.md).

## Visible coverage and structural coherence

Required visibility follows the artifact's purpose and the author's choices.
A figure study may require the full silhouette; a tool-use image may depend on
the contact between a hand, tool and workpiece. Keep those requirements distinct
from how an imagined composition happens to crop a subject.
For a composed artifact, assign each coverage requirement to the view that
expresses it. Whole-artifact coverage does not require repetition in every region.

Check ownership, attachment and support where the depicted action depends on
them. Record a particular crop or occlusion when it is meaningful, explicitly
selected, or necessary for an observed construction repair. Other unseen
structure remains identity or state knowledge. Its existence does not require
an instruction about where it leaves the frame.

## State-aware compilation

Compile the selected current depiction from the resolved state and the
contextual premises needed to interpret it. The complete history remains in
its owning state and story records.

```text
Identity Contract
+ optional Era / Form / Appearance Contract
+ resolved State Snapshot
+ Scene Context Snapshot
+ Visual State Projection
+ Asset Render Specification
+ chosen art direction and production knowledge
= Production Specification
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
- zero or one render profile;
- compatible atomic aesthetic touches.

A style family is an indivisible concrete drawing grammar. When selected, use its line, form, value, highlight, color, surface, background, and detail systems together. The linked render profile supplies the medium envelope and scoped negative boundary. Do not append two full grammars as independent tags.

## Modular control

A free text field the author does not decide holds the string `"unspecified"`.
Camera, performance and layout are whole optional structures, added when selected.
The base template and ordinary draft keep them absent. A supplied `--layout`
is retained as authored. A sparse portrait can remain small; a contact scene,
reference sheet, state transition or composed page may need more detail.

## Prompt assembly

Select the specification's task-bearing content using
[Prompt Composition](runtime/prompt-composition.md#select-the-depiction), then
compose the whole image before refining subject detail and necessary exclusions.
For a layout, establish its hierarchy and selected reading relationships, then
describe each region at its needed level of detail. Resolve internal references
into visible subject descriptions and positions. Select identity cues within
the local view; preserving identity does not make every feature visible.
Resolve subjects and reference uses within the delivered text and images.
`user_anchors` preserves requirements;
`purposeful_additions` records chosen effects; `construction_invariants` records
relationships essential to the result. Scene, subject and camera fields hold
their realization. Keep consequential assumptions at their existing owner.

A complete state record holds more than the selected image depicts. Carry
necessary identity, present circumstances, visible state, action, relationship,
camera and finish at the specificity this artifact needs. Establish the
contextual premises that make its selected performance or construction
intelligible in the delivered text and media. Apply
[depiction scope](runtime/prompt-composition.md#carry-scene-intent-into-depiction)
when selecting that context: source knowledge about other events, authorial
decisions and future outcomes retains its own record. A requested narrative
outcome or ambiguous portrayal is part of the image when the selected artifact
calls for it. Leave incidental deductions and unselected alternatives at their
source. A desired effect such as a readable interaction does not by itself
prescribe one camera position.

Subject IDs, source paths, lineage, decisions and review criteria stay in the
specification and related production records. Render settings use the exact
interface's native controls. The prompt carries the depiction and any necessary
directions for its supplied images, including scoped preservation or exclusions.

After assembly, reconstruct the artifact from the complete prompt, actual
ordered attachments and supported controls. Identify the premises and
relationships this delivered input establishes, including anything the
instructions rely on but leave unstated. Then compare that reading with the
image intent, Visual State Projection, Asset Render Specification and current
State Snapshot for the selected depiction. Resolve missing premises and
instructions that exceed its scope under
[Prompt assembly and review](runtime/prompt-composition.md#prompt-assembly-and-review).

Declare the reference mode as `prompt-only`, `prompt+1`, or `prompt+N`. For every image source, record its semantic role and decide whether it may govern permanent identity, target scene-conditioned construction, or another narrow visual property. Audit source scene-specific character state and source-render context separately. An identity-only source may not transfer gaze, expression, mouth state, pose, action, contact, support, physiology, surface condition, grooming condition, wardrobe, inventory, relationships, viewer awareness, environment response, current form, camera, crop, light, or finish unless an owning target-state or scene authority explicitly requires that property.

Activate every pack-backed reference through one explicit Reference Use Plan. Each plan decision binds an active canonical record to one intended influence, resolves only artifacts linked to that record, assigns narrow authority and exclusions, and commits the resulting order. If a State Protocol Reference Selection is present, reconcile every activated source and intended influence against that state authority. A prepared set without a Reference Use Plan cannot introduce a pack artifact or fabricated pack identity.

Task-specific scopes for supplied images come from the embedded `image_input_binding`, as [Semantic instruction editing](runtime/semantic-instruction-edit.md#prepare-supplied-references-for-dispatch) describes. The edit plan consumes those references and owns the edit source, requested change, preserved properties and review criteria.

Prepare one canonical Prepared Reference Set for the target model. Each prepared item preserves its authoritative `source` and adds the exact model-facing `transport`, with independent media types, hashes, and derivation. Prompt-artifact transport copies the exact selected source bytes. A direct model transport retains source bytes when supported. A selected safe SVG becomes a deterministic PNG transport only when the selected model accepts PNG. Commit the rasterization derivation under [Derived Visual Evidence](derived-visual-evidence.md#layer-c-runtime-attachment-build). Source-lighting `preserve` is authorized only by an item whose intended influence is `lighting` and whose technical role is `faithful-archival-vector`; a `specular-audit` item alone supplies candidate highlight evidence, not complete shadow and material-response authority. `source_evidence_roles` stores the unique semantic roles of exactly those complete lighting-evidence items and is recomputed by validation. Without that evidence, leave preservation explicitly unresolved or declare target lights and material responses with `rescope` or `replace`. Unresolved surface-lighting decisions block model-facing execution.

The reviewed effective prompt, Prepared Reference Set, exact carrier bytes, derivations, and order form one committed generation input. `prompt-only` commits an explicit empty Prepared Reference Set with a structured zero-reference reason. A Generation Package copies every carrier into its package-relative companion, publishes the JSON and companion transactionally, and remains verifiable after both are moved together. The verifier rechecks the complete contract and forwards only the verified prompt and carrier paths. If any selected source cannot be prepared or accepted by the target, stop before packaging; do not omit it or silently continue with text alone.

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

`resolved_morphology` is the resolved anatomy contract, and the subject's `frame_character` and `load_bearing_part_measurements` equal its own. It lists relevant feature instances, active form, surface map, feature relationships, expression channels, communication tools, current state deltas, count and attachment checks, coverage requirements, and uncertainties. It retains declared anatomy independently of crop. Local views own their visibility and pose. Prompt wording selects the details needed for each depiction; the resolved record is not emitted as a visibility inventory.

Use [Morphology and species contracts](morphology-and-species-contracts.md) before authoring an unfamiliar, fictional, hybrid, ordinary-animal, or mechanical body plan.

## Frame character and reconstruction-critical dimensions

Do not allow body-build terms to decide the bone and surface character implicitly. Resolve frame mass, surface character, soft-tissue padding, facial projection, body projection, and face-body coherence before prompt assembly. A thick-boned smooth-padded subject retains one rounded cheek mass, a submerged cheekbone landmark, a soft jaw corner, rounded joints, and broad mass handoffs even when the subject is extremely muscular. An angular subject uses a separately declared chiseled-angular frame.

Run the part-measurement pass for every one-off or recurring subject when size, count, spacing, angle, coverage, color, or surface is load-bearing. Prefer a local relationship and tolerance over an unsupported absolute unit. Examples include tag width against nose width, hoop diameter against ear height, tail thickness against pelvis width, wing span against torso width, or a mechanical panel gap against local plate thickness.

Accessory geometry is a first-class subject contract. A label such as `chain`, `dog tag`, `earring`, or `buckle` is not sufficient when reconstruction matters. Preserve the complete geometry, support path, attachment, repeated-element scale, material, color, layer order, pose response, and occlusion behavior.

## Rendering intent

Every current specification includes a resolved `render_intent`.
Create it with `scripts/render_contract.py intent` under [Rendering choices and execution controls](runtime/render-contract.md).
Draft prompt wording after retrieval, then validate with `--require-content` before building a Generation Package.
The rendering choice owns finish; visual-language catalog references and art direction supply additional scoped evidence.
Review them for agreement rather than silently rewriting either source.
