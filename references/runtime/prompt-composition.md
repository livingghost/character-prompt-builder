# Prompt Composition Runtime

Use the `composition` route when interacting requirements need detailed art
direction and a scene specification. Load construction specialists for the
subjects and relationships the image depends on.

## Contents

- [Image intent and anchor integrity](#image-intent-and-anchor-integrity)
- [Whole-image art direction](#whole-image-art-direction)
- [Select the depiction](#select-the-depiction)
- [Construction order](#construction-order)
- [Representation grammar](#representation-grammar)
- [Catalog retrieval and inspection](#catalog-retrieval-and-inspection)
- [Scene specification](#scene-specification)
- [Prompt assembly and review](#prompt-assembly-and-review)
- [Model-specific construction evidence](#model-specific-construction-evidence)
- [Creative latitude and interaction](#creative-latitude-and-interaction)
- [Revision contract](#revision-contract)
- [Negative output](#negative-output)
- [Conditional specialists](#conditional-specialists)

## Image intent and anchor integrity

Establish what the artifact must communicate and which relationships or visible
information carry that purpose. Keep unresolved presentation and finish choices
open while consulting knowledge. Follow
[Production direction](production-direction.md#choose-the-expression) to select
the construction within the brief's authority. The resulting image intent
describes the artifact's visual focus; an attribute list is insufficient. State
a consequential choice to the user when useful, outside the artifact.

Separate anchors from creative space. Never silently alter species, age, build, color, clothing, exposure, role, action, relationship, camera, lighting, or medium. Ask one compact question only when ordinary language understanding still leaves two or more similarly natural readings that would produce materially different images. Do not treat every omission as ambiguity, and do not call a familiar expression ambiguous merely because its individual words admit several translations.

When the user specifies anime, produce anime. When the user specifies photorealism, produce photorealism.

Forbid silent constraint injection (an unrequested restriction) and motive substitution (an agent change presented as craft).

Disclose every anchor change and its actual reason separately from creative rationale. Preserve unresolved wording until interpreted; missing catalog vocabulary does not erase it.

## Whole-image art direction

Use [Discovery](sparse-discovery.md) for unresolved expressive questions in both
sparse and detailed briefs. Compare treatments when they offer a real tradeoff,
then select one coherent construction. Fully fixed treatment needs no invented
contest. Discovery exposes knowledge; the agent owns the decision.

Consider the relevant axes together when choosing a direction. This is a planning aid, not a list of clauses to emit:

- center of appeal;
- subject-viewer, subject-subject, or subject-environment relationship;
- whole-artifact hierarchy, reading order when meaningful, and the relationships
  between any scenes, details, diagrams, image and type;
- local viewpoint, framing, depth, silhouette and visual weight where applicable;
- rendering treatments and their applicable subjects, parts, layers or areas;
- major masses, directional rhythms, repeated curves or angles, and useful negative space;
- anatomy, hair, fur, skin, feathers, scales, fabric, casing, metal, water, props, and effects as applicable;
- color hierarchy, with lighting relationships for each depicted space;
- edge, texture, finish, and complexity concentration.

When finish is open, consider the studio's `default_render_profile` in the
selected construction. A new studio takes `profile-clear-2d-illustration`, a
polished 2D character-illustration finish; inspect that complete record before
using it. A default cannot settle the artifact's presentation or override its
purpose. Treat rendering knowledge as four distinct layers:

1. A universal aesthetic core is optional, zero or one. It provides domain-neutral appeal, hierarchy, viewer relationship, shape rhythm, tactility, color-light taste, and finish. It may sharpen an already chosen direction, but never supplies anatomy or chooses the concept.
2. A concrete style family is optional, zero or one. It is an indivisible drawing grammar binding line hierarchy, form abstraction, value and shadow design, highlight placement, color behavior, surface grouping, background treatment, detail hierarchy, and domain-specific realization. Select one only when it closely fits the direction. Use its linked render profile as the medium envelope and scoped negative boundary, not as a second positive grammar. If no family fits, proceed with a render profile directly.
3. A domain realization is normally required for each represented subject domain. It translates the direction into valid identity cues, anatomy or body plan, expression channels, locomotion, surfaces, materials, contact, and environmental interaction. When a family is selected, use that family's matching domain overlay together with the selected domain realization.
4. A [render profile](../preset-system-contract.md#render-profile) is optional, zero or one. It owns the medium envelope. Without a family it supplies the primary grammar. With a family it supplies compatibility and negative scope while the family remains the primary positive grammar.

Apply each selected grammar within its declared scope. The shared grammar can
have zero or one family and profile; a different local treatment uses the
existing render intent's regional overrides. Interpret knowledge from another
profile into that scope's selected axes and wording. A family governs the
areas assigned to it, including its line, value, highlight and surface systems.
Use compatible atomic modules and activated corrections for the actual
construction questions. An empty candidate group is valid.

The authority order is:

```text
explicit user intent and approved canon
-> meaning of the whole brief
-> approved identity and state artifacts, when present
-> image intent and selected art direction
-> scene projection and Production Specification
-> inspected production-knowledge records
-> the studio defaults
```

## Select the depiction

The agent separates requirements from an imagined way to satisfy them:

- Explicit author requirements and adopted design remain anchors, including a
  requested crop or exclusion.
- Necessary relationships make the intended event and each participant's role
  readable.
- Purposeful art direction chooses an effect, such as quieter light for a
  reflective mood, within the delegated creative space.
- Incidental deductions belong to a possible realization, not automatically
  to the request.

For each inferred detail, ask what would be lost if a successful image rendered
it differently. Keep it when it preserves an anchor, communicates necessary
meaning, or serves the chosen direction. Plausibility alone is insufficient.
Leave other details unspecified. Removing a restriction means deleting it,
not replacing it with permission to ignore it or a denial of its alternative.

Establish the wanted appearance, action, relationships and finish from the
brief, applicable references and chosen direction. An exclusion sets a boundary;
it does not supply a desired alternative or degree. Preserve modifier scope:
rejecting an excessive form of a quality does not reject the quality itself.
Describe its intended form and strength when the brief makes those an anchor.

Synthetic example: a richly decorated hall with an orderly composition can use
carved bands around broad arches and quiet wall areas between them. Excluding
excessive ornament alone carries neither the requested richness nor its hierarchy.

Resolve missing choices from the author's intent and delegated art direction.
Do not infer the opposite of a prohibition, dilute a wanted quality, or fill
intentionally open alternatives. A direct exclusion is sufficient when only
that boundary matters. Text or an applicable supplied image can establish the
wanted state; neither requires a redundant inventory of the other.

Check the selected instructions together. Could an image satisfy them all while
losing the intended quality, degree, event, relationship or finish? Repair that
missing meaning in the specification. An object inventory cannot distinguish
cooperative work from people posing with the same tools. Necessary detail and
prompt length are separate decisions.

Synthetic example:

> Two technicians assemble a component across a workshop bench. One secures
> the component to the bench while the other applies a tool to the joint.
> Both look at the joint. Frame the component and their hands so each role is
> readable. Follow the references for their appearance and work clothes.

This brief requires a readable action. A wardrobe reference instead may require
a complete outfit view. Let the artifact's purpose determine visible coverage.
Do not turn readability into a close-up, central placement or another fixed
composition unless that choice serves the brief.

Use the existing Production Specification fields: `constraints.user_anchors`
for explicit requirements, `purposeful_additions` for selected art direction,
`construction_invariants` for essential relationships, and scene, subject and
camera fields for their realization. Store only consequential assumptions in
`consequential_assumptions`. Imagined alternatives need no additional record.

## Construction order

Resolve the relationships that carry the intent before local detail. Use these
questions where relevant; neither the plan nor the prompt needs every field:

1. What event or visual purpose should the image communicate?
2. Which subjects, objects, identities and states participate?
3. Who acts on what, addresses whom, or supports and contacts which object?
4. Which spatial relations distinguish that event, including meaningful depth,
   orientation, scale, overlap or separation?
5. Which information must be readable, and what whole-artifact and local-view
   composition serves it? Can the chosen view actually show that information?
6. Which performance cues, clothing details and physical constructions carry
   identity, state or the selected effect?
7. Which rendering grammar, lighting and material response serve the direction?

A visible action must have coherent ownership and physical connections. Assess
that consistency without prescribing visibility for every implied body region.
Name a crop or occlusion when it is requested, meaning-bearing, or necessary
for a specific observed construction repair. Keep other geometry as a result
of the chosen scene rather than a separate instruction.

The user's species and declared topology govern anatomy. Identity may depend on correlated evidence such as muzzle projection, nose thickness and placement, ear construction, cheek and jaw mass, eye placement, appendage connections, limb topology and surface behavior. Choose the relevant features rather than pasting the list into every prompt. Build, muscularity, frame mass and surface character are separate axes. Perspective enlargement belongs to the camera, not stable identity.

Ordinary animals use their natural anatomy, locomotion, support and sensory
behavior. Mechanical subjects use declared chassis, articulation, clearance,
sensors, manipulators and materials. For unfamiliar bodies, transformations,
unusual feature counts and recurring identity, load both [Morphology and Species Contracts](../morphology-and-species-contracts.md)
and [Species Architecture](../species-architecture.md). Apply their details only
to structures the intended depiction depends on.

Direct performance through the action, relationship and intended emotional
read. Resolve felt and displayed emotion, masking, intensity and timing when
that distinction matters. Specify local channels only where they carry the
requested performance; a channel inventory is not an acting requirement.

Garment, accessory and growth geometry needs landmark-relative construction
when identity or reproduction depends on it. Preserve stable grooming topology
separately from temporary wind, wetness, compression or movement. Apply
[Declared Structures](declared-structures.md) and [Growth Geometry](../growth-geometry-specification.md)
to the declared systems. Their examples supply construction knowledge, not a
checklist of features to insert.

## Representation grammar

Resolve the image-level grammar independently from the selected medium:

- large, medium, and fine-form hierarchy;
- boundary types and lost-edge behavior;
- the primary volume cue;
- information density and quiet regions;
- value and color organization;
- mark and surface treatment;
- material differentiation;
- background integration.

Realize the selected grammar within each treatment's scope. Resolve overlapping
family and rendering knowledge into the actual marks, surfaces and transitions
instead of appending complete source descriptions. Preserve intentionally
different treatments within the whole-artifact hierarchy.

Give each instruction the visual priority its meaning requires. Inspect whether local surface, pose or lighting detail overwhelms the whole-image direction. Combine overlapping finish instructions at their controlling scope and preserve distinct identity or construction detail. Repetition and word count alone establish neither useful emphasis nor fidelity; assess the complete rendition and the returned image.

On a prose-only interface, process words describe a finish whether or not the author intended them that way. Words such as `hand-drawn`, `hand-painted`, `sketch`, `ink`, `matte`, `flat`, and `paper` can pull the result toward pencil hatching, dry strokes, paper grain, muted chroma, or strand-by-strand treatment of coat and hair even when the selected family forbids microtexture. For a smooth polished field, describe the result instead: noise-free color fields, one unbroken gradient per large volume, placed soft-edged speculars, and designed clump shapes with gradient fills. Species-surface nouns can create the same drift; use `coat` plus an explicit strand-free surface description when `fur` would invite strands. For a hard-specular target specifically, `soft-edged`, `airbrushed`, and `painted` can pull the finish toward diffuse gradients. State hard-edged tone boundaries and bright, deliberately shaped speculars instead. This is target-dependent: soft edges remain valid when the selected material and finish actually require them.

On an `integrated-critical` interface, place necessary construction and exclusions
beside the surface or subject they govern. Existing wording can carry several
sources' requirements. Select the target adapter after the target is known.

## Catalog retrieval and inspection

Search is discovery, not authority. Interpret the complete brief and choose the direction before normal lookup. The sparse `recommend` branch is the sole exception.

Use canonical English describing the chosen direction and one coherent unresolved craft question. Preserve every anchor and modifier relationship. Prefer three to six distinctive content words for a focused query when they express the complete craft question; retain longer wording whenever it is needed to preserve a load-bearing relationship, negation, or modifier scope. Never truncate anchors merely to satisfy a word count. Use one `batch` process so the catalog loads once.

Retrieve the production questions the composition actually raises:

- For a character design, use `search --kind archetype` with the declared species,
  build, proportions and presentation. An explicit occupation also uses
  `search --categories occupation`.
- For staging, use `search --kind scene` with the required spatial and action
  relationships. Objects and environments need no invented character query.
- For an anthropomorphic animal, creature or hybrid, use
  `search --categories creature-anatomy` with its lineage. When appendage acting
  matters, use `search --categories body-language-cue` with the emotion and part.

When an enabled pack binds `cpb-resource:reference-cluster-mapping`, consult it
for relevant record groups. It supports search and full-record inspection.
An adopted archetype supplies identity invariants and marking logic; a base scene
supplies staging geometry. Their constraints support composition, while
`misreadings_to_avoid` and `failure_modes` support review. `inspire` may return
archetypes; search reaches base scenes and finished recipes.

Adopt at most one useful core, style family, and render profile, plus the domain realization for each represented subject domain and only compatible atomic modules. A finished recipe is optional. An archetype is an identity contract, not a scene: adopt its identity invariants and automatic identity constraints, or diverge deliberately. A scene supplies staging; keep its failure modes as review knowledge.

Use `--tier curated` only when the unresolved question requires a complete blueprint. Use `--tier vocabulary` only for a naming or option question. Leave the tier unrestricted when either complete production knowledge or model-legible vocabulary may answer the question; these are different functions, not quality ranks.

Treat an empty candidate group as valid. Read `query_token_count`, `axis_coverage`, and any `retrieval_note` in the complete response. `axis_coverage.unqueried` identifies art-direction axes that the requested categories never asked about and names categories that can query them; it does not prove missing catalog coverage. When every requested group and category is empty, or when `retrieval_note` reports that every requested atomic category is empty, separate materially different craft questions and retry each as a focused three-to-six-word query before concluding that coverage is absent. Preserve all anchors and modifier relationships during that retry; the range is a query-dilution diagnostic, not permission to discard meaning. Otherwise reformulate only when the semantic craft question itself should change, then art-direct genuinely unsupported axes.

Inspect the complete record after selection. The canonical record is not a summary. Read relationships, invariants, adaptation rules, `misreadings_to_avoid`, and scene `failure_modes`. `curated` records provide complete production knowledge; `vocabulary` records provide names and model-legible phrasing that the art direction must complete. These are functions, not quality ranks.

After inspection, run the Visual Reference Activation Gate for every selected record. Run full `asset-lookup` for each record before final prompt delivery or image-generation packaging, even when no linkage is already known and even when the requested deliverable is prompt-only. The operation returns complete active-pack ownership, resource details and source bytes, artifact paths and hashes, linked canonical records, and technical artifact roles. Review that complete result before deciding whether any visual contribution is adopted. Continue with [Prompt Artifact Reference Runtime](reference-prompt-artifacts.md) when evidence is adopted.

`asset-lookup --summary` remains available as an optional compact preview of linked asset IDs and declared technical roles, but it is not the activation gate and never replaces the mandatory full lookup. Do not use the summary to make the adoption decision, infer complete ownership or authority, or exempt a selected record from inspection.

## Scene specification

Record this composition in a current [Production Specification](../production-specification.md).
Draft it with `python scripts/production_spec.py draft` as the
[stateless workflow](../production-specification.md#stateless) shows; its relative
paths are below `--root`. Resolve the current scene before writing the prompt.
Validate the completed specification before delivery:

```bash
python scripts/production_spec.py validate production-specification.json --require-content
```

Use its optional `layout` when distinct regions need their own depiction or
views. Whole-artifact arrangement and reading relationships govern those
regions; each subject occurrence refers to shared identity and describes only
its local pose, state and visibility. A simple scene needs no region wrapper.
Text and diagram regions need no fictitious physical camera. Specify exact
geometry only when the purpose or requirement needs it.

For state-aware work, follow the State-Aware Series Runtime and reference the
sealed lineage, scene context, identity, snapshot and projection artifacts.
Local views retain that authority; a region does not authorize an unrecorded
state transition. For stateless work, do not invent series references. The same
Production Specification owns the requested artifact and its construction.

## Prompt assembly and review

Compose the selected specification as one art brief. Its `image_promise` and
`art_direction` establish the focus; subject, layout, scene and local view fields
resolve how that focus is realized. Open a prose rendition with the artifact or edit and
its visual focus, then arrange detail around those relationships. A tag interface
uses its evidenced order while preserving the same depiction. Field order does
not determine sentence order. Populated fields need no individual sentence when
their meaning is already carried by the depiction.

An adopted record contributes its selected construction knowledge. Combine or
rephrase that knowledge while preserving scope. Character and work names borrow
their design only through an intentional choice. An example's incidental pose,
objects or lighting do not become requirements of the current scene.

Bind references through their actual delivered order and assigned properties.
A source can carry appearance without a prose inventory of everything visible
in it. Specify critical identity details when reference evidence alone is
insufficient. Distinguish source-image locations from positions in the new
scene, and source expression or pose from the requested performance.

Use [Prompt Writing Guide](prompt-writing-guide.md) for the final interface
rendition. Read it back as a picture, using the actual positive and negative
channels, controls and supplied images. Compare that picture with the brief
and this specification:

- Check that text and supplied images establish the wanted qualities and their
  degree. Satisfying exclusions alone must not leave an anchor unspecified or
  weaken the intended effect.
- Check that action ownership, contact, support, gaze and depth communicate the
  selected relationships together.
- Check the whole-artifact hierarchy, reading relationships and each local view.
  Required visibility must be possible in the assigned view. Shared identity
  does not require every view to expose every identity detail.
- Check that identity, current state and reference scope agree, including
  properties carried by images rather than repeated in text.
- Check that local surface, lighting and detail instructions support the chosen
  whole-image grammar and emphasis.

Resolve apparent conflicts by identifying their subject, region, moment,
condition and source authority. Opposing words can describe different scopes;
different words can impose incompatible demands on the same scope. A distant
object can be physically larger while appearing smaller. Source-image pose and
target pose can differ when the source carries identity only. Distinguish an
unusual or difficult depiction from an impossible conjunction of requirements.

Synthetic example: one vase is opaque and another is transparent. Both fit one
still life. Requiring the same intact wall of one vase to hide its contents and
show them clearly in the same view needs a decision. A cutaway or separate view
can serve an explanatory artifact when presentation is open. It cannot silently
replace a fixed request for one natural continuous view.

Apply the authority order above. Repair missing meaning or a conflicting draft
choice in its owning scene or subject description, then rewrite the rendition. If fixed
requirements remain incompatible, ask for the smallest necessary decision and
leave the prompt unfinished. Do not silently discard an anchor or use stronger
weights and additional negatives to mask the conflict. A scoped exclusion must
also be representable by the selected interface; an unscoped negative token
cannot be treated as a local instruction merely because planning assigned it one.

Read the complete revised input again. Preserve required identity and exclusions
and check that the intended image still follows. Consolidate repeated requirements
within their actual scopes. Keep judgments and success criteria in review records,
instead of appending them to image text. Structural checks verify declared
assignments; the author judges their meaning and agreement with the rendition.
Compare returned images with the same requirements. A different valid realization
is not a defect merely because it was unimagined.

## Model-specific construction evidence

Choose a repair from the observed mismatch and the selected interface's
capabilities. The active catalog and recorded trials supply model-specific
wording and settings. Generic techniques below are hypotheses to evaluate,
not instructions to append to every prompt.

**Overlapping actions.** A turned torso with a manual task can create ambiguous
limb paths. Check which hand acts on which object and whether the pose supports
that action. Clarify a necessary contact or test another permitted camera view.
Changing a grip or action requires authority when it is part of the brief.

**Visibility pressure.** Terms for a covered marking or cropped accessory can
compete with framing or clothing instructions on some interfaces. Reassess why
the term is present. Keep a detail required by the depiction; leave incidental
source knowledge in its owning record. Do not replace the omitted detail with
an instruction that it may be hidden.

**Performance.** Use an emotion or performance phrase when it conveys the
intended moment. Local cues can clarify masking, subtlety or a tested model
response. Judge their combined read rather than enforcing a default intensity.
Graphic marks require assessment against the requested finish; an emotion word
alone does not prove that such marks will appear.

**Vocabulary.** Select spelling and weighting from the active interface's
evidenced vocabulary. Different training vocabularies can name the same pose
or channel differently. Resolve those names through retrieval before using
weights or adding contradictory synonyms.

**Local changes.** An accepted image can support a targeted edit when text alone
does not achieve the requested state. Bind the edit source, changed region and
preserved properties through the semantic-edit workflow. Choose strength or
other controls only from the exact interface's evidence. Inspect both the edit
and the supposedly preserved areas afterward.

**Body construction.** A close view can weaken the contextual cues for a
nonhuman or designed body. Describe the declared construction where the image
needs it. A species prior never authorizes replacement of the subject's actual
parts, topology or proportions.

**Detail scale.** Compare a feature's pixel coverage with the required
readability. More resolution or a separate detail image may help where wording
does not. Preserve requested framing; a closer camera is a choice, not an
automatic repair for every small feature.

**Prompt conflicts.** Inspect positive terms, source scopes and framing before
adding an exclusion. Delete an inviting term only when it is not an intended
requirement. An explicit author exclusion or a supported technical negative
can still be necessary. Neither longer nor shorter text proves better intent
fidelity.

**Controls and comparisons.** Use supported prompt, reference, weighting and
inference controls for a particular diagnosis. Record changed conditions and
evaluate the complete output. A trial that changes several inputs can assess
the setup but cannot isolate one cause. A provider refusal remains distinct
from an unwanted visual result under [Model request evidence](model-evidence.md).

**Strong perspective.** An intentionally extreme viewpoint can need a near-form
anchor, relevant background scale or converging environmental lines. Select
those cues for the requested camera effect, rather than prescribing a fixed
angle, body crop or foreground limb. Matching active records may supply an
evidenced treatment; their applicability depends on the actual shot and model.

## Creative latitude and interaction

Use `directed` and `balanced` unless the user requests another mode.

- `minimal`: add only what makes the image legible and polished;
- `directed`: make purposeful clothing, setting, lighting, and presentation choices that strengthen the intent;
- `expansive`: make bolder narrative, fashion, environmental, or graphic choices while preserving the core concept.

Keep additions coherent within the requested artifact. Interaction modes are:

- `balanced`: ask only about consequential unresolved meaning;
- `interactive`: present two or three complete art directions for selection;
- `autonomous`: choose the strongest direction and disclose consequential assumptions and every modification.

## Revision contract

Return the complete current prompt, negative, reference mode, ordered reference deliverables, and scope review after a revision. Return a diff only when requested.

Use [Revision Contract](revision-contract.md). `edit` is the default: preserve the current baseline except the requested paths and necessary, explained consistency changes. `explore` varies non-frozen axes only when a new alternative is requested. `retarget` preserves structured meaning while changing interface-specific rendition. Keeping a draft choice during a local edit does not promote it into permanent identity.

When a new reference arrives during revision, inventory its differences from the last output across identity construction and all art-direction axes before deciding which axis the user wants changed. When a pack changed, refresh retrieval under the current snapshot and validate affected choices without reopening unrelated baseline decisions. Disclose any necessary consistency change; do not silently turn a local edit into a new concept. When editing a canonical record, reread the whole record for coherence rather than patching one prompt-facing field in isolation.

## Negative output

Read `cpb-resource:negative-policy` and record the exclusions selected for this composition. Consider:

1. central hygiene and integrity bundles for structures actually implied by the subject, pose, and framing;
2. drift terms from the selected render profile;
3. terms from corrections activated by a concrete risk;
4. explicit user exclusions.

Do not sweep record diagnostics, scene failure modes, domain boundaries, or semantic alternatives into the negative automatically. Romance, hostility, dominance, age, gender, genre, and similar alternatives enter only when the user explicitly excludes them. Apply structure-specific terms to the intended depiction and relevant construction risks. Known anatomy alone does not require describing every part's visibility. For an interface without an independent negative field, integrate necessary exclusions through affirmative construction or explicit negation according to their meaning. Keep the selected source evidence with the composition; a source does not require its own clause when another instruction already carries the constraint.

## Conditional specialists

Read only when needed: [Creative Core](../creative-core.md) for direction examples; [Character Domains](../domain-model.md) for domain choice; [Anthro Prompt Anatomy](../anthro-prompt-anatomy.md) for anthropomorphic prompt blocks; [Preset Authoring Standard](../preset-authoring-standard.md) for positive/diagnostic separation; [Troubleshooting](../troubleshooting.md) for workflow symptoms and failed outputs.
