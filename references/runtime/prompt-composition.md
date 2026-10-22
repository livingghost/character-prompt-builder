# Prompt Composition Runtime

Use for every prompt. Load specialists only when activated.

## Contents

- [Image intent and anchor integrity](#image-intent-and-anchor-integrity)
- [Whole-image art direction](#whole-image-art-direction)
- [Select the depiction](#select-the-depiction)
- [Construction order](#construction-order)
- [Representation grammar](#representation-grammar)
- [Catalog retrieval and inspection](#catalog-retrieval-and-inspection)
- [Prompt assembly and review](#prompt-assembly-and-review)
- [Creative latitude and interaction](#creative-latitude-and-interaction)
- [Revision contract](#revision-contract)
- [Negative output](#negative-output)
- [Conditional specialists](#conditional-specialists)

## Image intent and anchor integrity

Before lookup, privately state in one or two sentences what must be visually true, what holds the image together emotionally and visually, how the subject relates to the viewer, another subject, an object, or the environment, and which medium and finish hold the image together. This image intent describes the finished picture rather than listing attributes. Do not show the private statement unless it helps the user understand a choice or the user asks for it. Records support the direction; they never choose it.

Separate anchors from creative space. Never silently alter species, age, build, color, clothing, exposure, role, action, relationship, camera, lighting, or medium. Ask one compact question only when ordinary language understanding still leaves two or more similarly natural readings that would produce materially different images. Do not treat every omission as ambiguity, and do not call a familiar expression ambiguous merely because its individual words admit several translations.

When the user specifies anime, produce anime. When the user specifies photorealism, produce photorealism.

Forbid silent constraint injection (an unrequested restriction) and motive substitution (an agent change presented as craft).

Disclose every anchor change and its actual reason separately from creative rationale. Preserve unresolved wording until interpreted; missing catalog vocabulary does not erase it.

## Whole-image art direction

For a well-specified brief, privately compare two to four coherent treatments of the same intent and choose one. For a sparse brief, use the direction-card procedure in [Sparse-Brief Discovery Runtime](sparse-discovery.md). Never average candidates.

Consider the relevant axes together when choosing a direction. This is a planning aid, not a list of clauses to emit:

- center of appeal;
- subject-viewer, subject-subject, or subject-environment relationship;
- viewpoint, framing, depth, silhouette, focal sequence, and visual weight;
- one medium family, unless a deliberate hybrid is requested;
- major masses, directional rhythms, repeated curves or angles, and useful negative space;
- anatomy, hair, fur, skin, feathers, scales, fabric, casing, metal, water, props, and effects as applicable;
- local-color hierarchy and one lighting thesis;
- edge, texture, finish, and complexity concentration.

When medium is open, read the studio's `default_render_profile`. A new studio takes `profile-clear-2d-illustration`, a polished 2D character-illustration direction; inspect that complete render profile before using it. Treat production knowledge as four distinct layers:

1. A universal aesthetic core is optional, zero or one. It provides domain-neutral appeal, hierarchy, viewer relationship, shape rhythm, tactility, color-light taste, and finish. It may sharpen an already chosen direction, but never supplies anatomy or chooses the concept.
2. A concrete style family is optional, zero or one. It is an indivisible drawing grammar binding line hierarchy, form abstraction, value and shadow design, highlight placement, color behavior, surface grouping, background treatment, detail hierarchy, and domain-specific realization. Select one only when it closely fits the direction. Use its linked render profile as the medium envelope and scoped negative boundary, not as a second positive grammar. If no family fits, proceed with a render profile directly.
3. A domain realization is normally required for each represented subject domain. It translates the direction into valid identity cues, anatomy or body plan, expression channels, locomotion, surfaces, materials, contact, and environmental interaction. When a family is selected, use that family's matching domain overlay together with the selected domain realization.
4. A [render profile](../preset-system-contract.md#render-profile) is optional, zero or one. It owns the medium envelope. Without a family it supplies the primary grammar. With a family it supplies compatibility and negative scope while the family remains the primary positive grammar.

Then use only compatible atomic modules and activated corrections for specific construction questions. Aesthetic touches may refine the family only when they preserve its line, value, highlight, and surface systems. An empty candidate group is valid.

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

Check the selected instructions together. Could an image satisfy them all while
communicating a different event? State the missing relationship or action.
An object inventory cannot distinguish cooperative work from people posing
with the same tools. Necessary detail and prompt length are separate decisions.

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
5. Which information must be readable, and what camera or composition serves it?
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

Project that grammar into one medium; do not concatenate overlapping family and rendering prose after a resolved contract exists.

Treat prompt wording as an emphasis budget. A selected family's single instruction, such as smooth grouped torso planes, loses to five surrounding sentences of fine texture description because the model renders the greater verbal weight. When the prompt elaborates a surface, pose, or light beyond the family's guidance, keep that elaboration proportional to the visual priority it deserves and restate the family's controlling term once beside the governed region.

On a prose-only interface, process words describe a finish whether or not the author intended them that way. Words such as `hand-drawn`, `hand-painted`, `sketch`, `ink`, `matte`, `flat`, and `paper` can pull the result toward pencil hatching, dry strokes, paper grain, muted chroma, or strand-by-strand treatment of coat and hair even when the selected family forbids microtexture. For a smooth polished field, describe the result instead: noise-free color fields, one unbroken gradient per large volume, placed soft-edged speculars, and designed clump shapes with gradient fills. Species-surface nouns can create the same drift; use `coat` plus an explicit strand-free surface description when `fur` would invite strands. For a hard-specular target specifically, `soft-edged`, `airbrushed`, and `painted` can pull the finish toward diffuse gradients. State hard-edged tone boundaries and bright, deliberately shaped speculars instead. This is target-dependent: soft edges remain valid when the selected material and finish actually require them.

On an `integrated-critical` interface, restate every activated anti-drift construction affirmatively beside the surface it governs. Select the target adapter only after the target is known.

## Catalog retrieval and inspection

Search is discovery, not authority. Interpret the complete brief and choose the direction before normal lookup. The sparse `recommend` branch is the sole exception.

Use canonical English describing the chosen direction and one coherent unresolved craft question. Preserve every anchor and modifier relationship. Prefer three to six distinctive content words for a focused query when they express the complete craft question; retain longer wording whenever it is needed to preserve a load-bearing relationship, negation, or modifier scope. Never truncate anchors merely to satisfy a word count. Use one `batch` process so the catalog loads once.

Before atomic retrieval, always run one `search --kind archetype` query with the subject's species, build, proportion, and age or presentation, one `search --categories occupation` query for an explicit role, and one semantically focused `search --kind scene` query with the required staging relationships. Express each in three to six distinctive words when that preserves the full requirement; otherwise retain the additional words needed for exact scope. Do not silently downgrade either required query to generic inspiration. When the subject is an anthropomorphic animal, creature, or hybrid, add one `search --categories creature-anatomy` query naming the subject's lineage (for example canine, feline, dragon, avian, marine) so the lineage anatomy grammar and its invariants enter inspection, and when the direction asks the subject to express emotion through an appendage such as a tail, ears, feathers, or flukes, add one `search --categories body-language-cue` query naming the emotion and the appendage so the matching cue record, its invariants, and its misreading list reach the review. When an enabled pack binds `cpb-resource:reference-cluster-mapping`, read it to relate recurring brief patterns to records in the pack that binds it; otherwise rely on catalog search and record inspection. The mapping is an index aid, not an authority or a substitute for search and full-record inspection. An archetype is an identity contract, not a scene choice: adopt its `identity_invariants` and `marking_logic`, including its `automatic_prompt_injection` identity constraints, or diverge deliberately. A matching base scene supplies staging geometry and its `failure_modes` become review knowledge. `inspire` may return a `subject_archetypes` candidate group, but base scenes and finished recipes remain reachable only through `search`.

Adopt at most one useful core, style family, and render profile, plus the domain realization for each represented subject domain and only compatible atomic modules. A finished recipe is optional. An archetype is an identity contract, not a scene: adopt its identity invariants and automatic identity constraints, or diverge deliberately. A scene supplies staging; keep its failure modes as review knowledge.

Use `--tier curated` only when the unresolved question requires a complete blueprint. Use `--tier vocabulary` only for a naming or option question. Leave the tier unrestricted when either complete production knowledge or model-legible vocabulary may answer the question; these are different functions, not quality ranks.

Treat an empty candidate group as valid. Read `query_token_count`, `axis_coverage`, and any `retrieval_note` in the complete response. `axis_coverage.unqueried` identifies art-direction axes that the requested categories never asked about and names categories that can query them; it does not prove missing catalog coverage. When every requested group and category is empty, or when `retrieval_note` reports that every requested atomic category is empty, separate materially different craft questions and retry each as a focused three-to-six-word query before concluding that coverage is absent. Preserve all anchors and modifier relationships during that retry; the range is a query-dilution diagnostic, not permission to discard meaning. Otherwise reformulate only when the semantic craft question itself should change, then art-direct genuinely unsupported axes.

Inspect the complete record after selection. The canonical record is not a summary. Read relationships, invariants, adaptation rules, `misreadings_to_avoid`, and scene `failure_modes`. `curated` records provide complete production knowledge; `vocabulary` records provide names and model-legible phrasing that the art direction must complete. These are functions, not quality ranks.

After inspection, run the Visual Reference Activation Gate for every selected record. Run full `asset-lookup` for each record before final prompt delivery or image-generation packaging, even when no linkage is already known and even when the requested deliverable is prompt-only. The operation returns complete active-pack ownership, resource details and source bytes, artifact paths and hashes, linked canonical records, and technical artifact roles. Review that complete result before deciding whether any visual contribution is adopted. Continue with [Prompt Artifact Reference Runtime](reference-prompt-artifacts.md) when evidence is adopted.

`asset-lookup --summary` remains available as an optional compact preview of linked asset IDs and declared technical roles, but it is not the activation gate and never replaces the mandatory full lookup. Do not use the summary to make the adoption decision, infer complete ownership or authority, or exempt a selected record from inspection.

## Scene specification

Every final image uses a current [Production Specification](../production-specification.md), including an ordinary one-off prompt-only image. Draft it with `python scripts/production_spec.py draft` as [Production Specification](../production-specification.md#stateless) shows; its relative paths are below `--root`. Author the current scene structure directly rather than patching an older prompt. Validate it before final prompt delivery:

```bash
python scripts/production_spec.py validate production-specification.json --require-content
```

For state-aware work, follow the State-Aware Series Runtime and reference the sealed lineage, scene context, identity, snapshot, and projection artifacts. For stateless work, do not invent those series references; the same current Production Specification structure still owns the exact one-image scene, camera, relationships, materials, and construction obligations.

## Prompt assembly and review

Write the selected depiction as instructions to an illustrator. Lead with the
event or visual purpose, then give the identity, relationships, presentation
and rendering details needed to realize it. Adjust the order for the selected
interface after the meaning is settled. Field order is not a prompt template.

Keep private deliberation separate from the authored text. Do not narrate
rejected possibilities, internal checks or why an unspecified detail is free.
A negative or permission sentence is useful only when its content is itself a
requirement. The grammatical form alone does not decide whether it belongs.

Use the active vocabulary for the selected visual concepts. Records provide
candidate terms and construction knowledge; use only relevant wording.
Character and work names carry their own design and require an intentional
choice to borrow it. A retrieved phrase does not authorize the objects,
actions, camera or state that happen to appear in its example.

References can supply identity, attire or visual construction without a prose
inventory of their contents. Describe the new event and meaningful changes,
plus any critical detail the reference alone does not communicate. Keep source
expression and pose distinct from the current performance. Known facts outside
the depicted action remain with their source authority rather than becoming
instructions to expose them.

Concrete action can clarify a property when the action is part of the intended
scene. Do not introduce a new action merely to force an incidental property.
Likewise, deleting an unwanted clause does not require adding its opposite.
Diagnose the cause of a mismatch and state only the construction the image needs.

Read the complete prompt against its brief and selected direction:

- Does it retain every explicit anchor and purposeful choice?
- Can each inferred instruction justify its contribution to the intended image?
- Do the remaining instructions convey the intended event and participant roles?
- Do camera, placement, actions and required visible information fit one picture?
- Are references assigned to the right subjects and uses, without importing a
  source-only performance or layout?
- Does target-specific wording preserve meaning, identity, state and finish?

Use relevant specialist checks for anatomy, contact, clothing or rendering.
A possible misreading is a reason to assess the text, not automatically to add
a guard. Remove conflicting or redundant requirements before adding a repair.

The agent evaluates meaning. Scripts validate declared counts, references,
field relationships and transport. Neither a keyword checklist nor successful
packaging proves that the scene communicates its intended meaning.

Use [Prompt Writing Guide](prompt-writing-guide.md) for the final interface
rendition. Match output review to these same requirements. A different valid
composition or expression is not a defect merely because it differs from the
agent's imagined picture.

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

Even expansive additions form one image. Interaction modes are:

- `balanced`: ask only about consequential unresolved meaning;
- `interactive`: present two or three complete art directions for selection;
- `autonomous`: choose the strongest direction and disclose consequential assumptions and every modification.

## Revision contract

Return the complete current prompt, negative, reference mode, ordered reference deliverables, and scope review after a revision. Return a diff only when requested.

Use [Revision Contract](revision-contract.md). `edit` is the default: preserve the current baseline except the requested paths and necessary, explained consistency changes. `explore` varies non-frozen axes only when a new alternative is requested. `retarget` preserves structured meaning while changing interface-specific rendition. Keeping a draft choice during a local edit does not promote it into permanent identity.

When a new reference arrives during revision, inventory its differences from the last output across identity construction and all art-direction axes before deciding which axis the user wants changed. When a pack changed, refresh retrieval under the current snapshot and validate affected choices without reopening unrelated baseline decisions. Disclose any necessary consistency change; do not silently turn a local edit into a new concept. When editing a canonical record, reread the whole record for coherence rather than patching one prompt-facing field in isolation.

## Negative output

Read `cpb-resource:negative-policy`. Always retain a portable negative or equivalent diagnostic block. Activate only:

1. central hygiene and integrity bundles for structures actually implied by the subject, pose, and framing;
2. drift terms from the selected render profile;
3. terms from corrections activated by a concrete risk;
4. explicit user exclusions.

Do not sweep record diagnostics, scene failure modes, domain boundaries, or semantic alternatives into the negative automatically. Romance, hostility, dominance, age, gender, genre, and similar alternatives enter only when the user explicitly excludes them. Apply structure-specific terms to the intended depiction and relevant construction risks. Known anatomy alone does not require describing every part's visibility. For an interface without an independent negative field, translate only the activated technical requirements into affirmative construction language and keep the portable negative for traceability.

## Conditional specialists

Read only when needed: [Creative Core](../creative-core.md) for direction examples; [Character Domains](../domain-model.md) for domain choice; [Anthro Prompt Anatomy](../anthro-prompt-anatomy.md) for anthropomorphic prompt blocks; [Preset Authoring Standard](../preset-authoring-standard.md) for positive/diagnostic separation; [Troubleshooting](../troubleshooting.md) for workflow symptoms and failed outputs.
