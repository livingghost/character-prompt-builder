# Prompt Composition Runtime

Use the `composition` route when interacting requirements need detailed art
direction and a scene specification. Load construction specialists for the
subjects and relationships the image depends on.

## Contents

- [Image intent and anchor integrity](#image-intent-and-anchor-integrity)
- [Whole-image art direction](#whole-image-art-direction)
- [Select the depiction](#select-the-depiction)
- [Carry scene intent into depiction](#carry-scene-intent-into-depiction)
- [Construction order](#construction-order)
- [Representation grammar](#representation-grammar)
- [Catalog retrieval and inspection](#catalog-retrieval-and-inspection)
- [Scene specification](#scene-specification)
- [Prompt assembly and review](#prompt-assembly-and-review)
- [Competing-realization test](#competing-realization-test)
- [Model-specific construction evidence](#model-specific-construction-evidence)
- [Creative latitude and interaction](#creative-latitude-and-interaction)
- [Revision contract](#revision-contract)
- [Negative output](#negative-output)
- [Conditional specialists](#conditional-specialists)

## Image intent and anchor integrity

[Production direction](production-direction.md) owns the construction and
judgment of the commissioned depiction. Use this document as construction
knowledge for the question that work raises. A route or specialist does not
start a separate composition algorithm. Keep its knowledge connected to the
situation, design and selected effect.

Establish source roles and authority under that owner. Preserve explicit
requirements, including precise design, count, action, relationship, crop,
lighting, medium and exclusions. Disclose an authorized anchor change and its
actual reason separately from creative rationale. Source material and a draft
proposal have different authority; detailed wording alone does not establish
adoption. Use ordinary language understanding before asking about meaning.
Ask only when unresolved meaning or authority would change a fixed requirement.
Missing catalog vocabulary does not erase a requirement.

When the user specifies anime, produce anime. When the user specifies photorealism, produce photorealism.

Forbid silent constraint injection (an unrequested restriction) and motive
substitution (an agent change presented as craft). An omitted property is not
a permission or an exclusion. Open choices can have several successful answers.

## Whole-image art direction

Use rendering and design knowledge for the selected depiction. Direction,
relationship, hierarchy, shape rhythm, negative space, color-light organization,
material response and finish can matter together; select them through their
role in the image rather than completing an axis inventory. Open expressive
questions use [Discovery](sparse-discovery.md). The resulting choice remains
with Production direction.

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

Apply the authority order to sources in their assigned roles. For assessment,
establish those roles and the comparison basis through
[Observe and repair](production-direction.md#observe-and-repair). The force or
detail of wording in a submitted draft does not establish its approval status;
the draft remains the complete candidate being evaluated. The authority order is:

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

Follow [Choose the expression](production-direction.md#choose-the-expression)
for the authored picture and the specificity it needs. Write the selected
activity, state or design as connected meaning. An exclusion defines its
actual boundary; it does not automatically select the opposite or diminish
the remaining requested quality. Preserve modifier scope and intended degree.
A direct exclusion is sufficient when that boundary fully defines the change.

Use the same production knowledge from either starting point. For
[an image source](production-direction.md#form-a-prompt-from-an-image), identify
the appearance and relationships to carry, including distinctive details at
the requested fidelity. For
[an idea](production-direction.md#form-a-prompt-from-an-idea), choose concepts
and a visual realization that make the intended experience concrete. The
former interprets supplied choices; the latter authors open choices. Neither
requires converting every visible or imagined consequence into an instruction.

The current Production Specification records the chosen depiction:
`constraints.user_anchors` holds explicit requirements, `purposeful_additions`
holds selected art direction, and `construction_invariants` holds relationships
needed for that construction. Scene, subject, camera and optional layout
fields record its realization. `consequential_assumptions` holds assumptions
that matter. A recorded choice is not thereby a user requirement, and a filled
field need not have its own prompt sentence. The form records the result of
authoring; it does not prescribe how to author it.

## Carry scene intent into depiction

Carry the situation selected through Production direction into the actual
input. For scene work, an action or reaction means something in its
circumstances. Retain the participants' activity, relevant relationships and
necessary premise rather than replacing the performance with isolated body
cues. A prior event or off-frame circumstance can explain the present action;
a generally intelligible act may need no such explanation. Narrative ambiguity,
symbolism or an outcome belongs when the commissioned image is to express it.
An unresolved authoring decision alone does not commission that portrayal.

The renderer receives the actual prompt, supported controls and delivered
media. The agent's conversation, story records and unselected images are
separate knowledge. Establish necessary context within that input before
relying on it. Reference an image only when it is actually supplied and assign
its contribution. Translate the relevant contribution of authoring-only
material into the requested depiction. Preserve the source's scope instead of
forwarding its contents indiscriminately.

A scene rendition preserves its current facts and intended meaning without
becoming a production memo. Selection reasons, approval history, private IDs,
paths and future project decisions stay with their owners when outside the
image's purpose. Time alone is not a relevance filter: past or future content
can be the subject of an artifact, while a fact about the current project can
be unnecessary to its image. A visible action, a contextual sentence and
supplied media can jointly carry the intended portrayal.

Use [Performance Language](../performance-language-specification.md#8-prompt-projection)
when a performance question needs it. It supports contextual actions, felt and
displayed state, intensity, masking, stillness and distinct expressive channels.
It does not require translating every ordinary act into a set of cues. A chosen
physical realization remains a choice for this depiction; it is not a new
permanent mannerism or an automatically true story inference. Update enduring
identity or narrative facts only through their owning adoption procedure.

## Construction order

Resolve a consequential construction in the same situation and presentation
chosen through Production direction. The useful unit can be a whole activity,
a mechanism, a visual comparison or a precise local feature. Keep its parts
related while following ownership, orientation, support, contact, scale,
overlap and visibility where those relations matter. They explain a
construction; they are not separate questions to answer for every image.

Follow changes through their actual consequences. The body's engagement in an
action and the objects it uses constrain each other. A view changes what is
available to the viewer; it does not change what a participant can perceive or
do merely to preserve an attractive presentation. Familiar actions can carry
ordinary support and movement without separately specifying every joint.
Use [spatial construction](../prompt-composition-geometry.md#3-spatial-relations-carry-the-event)
when those relationships need resolution. A sketch or position model can help
answer a difficult question without becoming a mandatory artifact or numeric
prompt specification.

Interpret each source image in its assigned role and scope. Establish whether
it contributes to authoring, is delivered to the model, or serves both uses.
Read an assigned design as a coherent whole, including its visible form,
proportions, construction, depicted state and treatment. Distinguish what the
image establishes from what the current brief supplies and what still needs
an authored choice. A cropped view leaves some construction unobserved; develop
what the depiction needs consistently with the established design.

For an interaction, inspect the participants and objects together. Identify who
acts on what and how ownership, support, contact and orientation establish the
action. Use these connections to construct the pose and positions. Separate
visible evidence from inferred intention, mechanism and hidden structure. An
unobserved connection can need a coherent solution in the new depiction without
the source establishing one exact solution. Follow an orientation, connection
or state choice through its other consequences before settling the view. A
layout that establishes a required action may expose less of an object than a
reference view; preserving its design does not mean reproducing that coverage.

Realize the required design and relationships in the selected moment and view.
The source camera and temporary pose can determine apparent extent, overlap,
orientation and exposed surfaces. Preserve properties required by the assigned
design or current brief; construct their appearance from the new view. Name a
crop or occlusion when it is requested, meaning-bearing or needed for an
observed construction repair. Construct implied connections coherently through
occlusion and expose the information the depiction requires. Other geometry
follows from the selected scene.

Express the necessary contribution of an authoring-only image in the prompt.
For a delivered image, assign the properties that it carries and use text for
the current depiction that its assigned evidence does not establish. The
combined text and actual media must make the chosen construction intelligible.

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

Develop image-level grammar for the selected construction, independently of
its medium label. Work on the unresolved choices that affect its intended
effect or a required property. An adopted treatment or sufficient existing
depiction can already settle them. The available construction knowledge covers:

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

Select retrieval questions from the current purpose, construction and intended
wording. A retrieval element is one coherent production or wording question;
it can concern related subjects, objects and details together. Name it for the
decision it serves, and record its actual queries and use of inspected results
through the [retrieval record](prompt-only-core.md#saved-prompt-artifacts).
The question determines what knowledge is needed and when it is sufficient.

Use [Discovery](sparse-discovery.md) for an open expressive choice and focused
catalog or vocabulary lookup for a known need. Search supplies evidence and
possibilities; the agent chooses the depiction. During review, inspect the
existing input and its applicable evidence. Retrieve when an unresolved
production or wording question affects the assessment or an authorized
revision.

Use canonical English describing the chosen direction and one coherent unresolved craft question. Preserve every anchor and modifier relationship. Prefer three to six distinctive content words for a focused query when they express the complete craft question; retain longer wording whenever it is needed to preserve a load-bearing relationship, negation, or modifier scope. Never truncate anchors merely to satisfy a word count. Use one `batch` process so the catalog loads once.

Choose the search that serves the selected question:

- For a question about character design, use `search --kind archetype` with the
  declared species, build, proportions and presentation. Use
  `search --categories occupation` when representing the occupation is the
  production question.
- For a question about space or action, use `search --kind scene` with
  the required relationships. Objects and environments need no invented
  character query.
- For an anatomy question about an anthropomorphic animal, creature or hybrid,
  use `search --categories creature-anatomy` with its lineage. For appendage
  performance, use `search --categories body-language-cue` with the emotion and
  part.

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

Inspect linked visual evidence when it can resolve the selected question or
supply a contribution being considered. The compact activation summary can
locate relevant assets; it cannot establish their content or authority. Run
full `asset-lookup` for each record whose visual evidence is under consideration
before adopting that evidence. Read the returned ownership, resource details,
source bytes, paths, hashes, linked records and technical roles. Full inspection
is required for adoption even when an earlier summary looked sufficient.
A purely textual knowledge use needs no unrelated asset investigation. Continue
with [Prompt Artifact Reference Runtime](reference-prompt-artifacts.md) for
selected visual contributions.

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

Author one coherent rendition of the selected depiction. The Production
Specification supplies meaning and provenance; field order is not sentence
order. Keep ordinary activities, reactions, relationships and design concepts
intact in prose. Add local description where it makes a needed distinction,
realizes chosen expression, preserves a fine requirement or addresses an
evidenced interface weakness. Source fields and derived coordinates do not
automatically become clauses. Preserve useful detail and applicable exclusions
at their actual scope without a quota of words, cues or negative terms.

Bind delivered references to their actual order and assigned contribution.
A delivered design can carry its correlated form without a prose inventory
of every visible feature. Specify critical information when the combined
input needs it. A source location identifies evidence, not the new scene's
layout. A temporary source pose or expression transfers only when assigned.
Authoring-only media supply their necessary contribution through text.

Use [Prompt Writing Guide](prompt-writing-guide.md) for the final interface
rendition. It owns syntax and target evidence; it does not select the event,
replace source authority or start another construction process. Adopted
knowledge can be combined and rephrased while preserving scope. Character
and work names borrow a design only through an intentional choice.

Apply [Observe and repair](production-direction.md#observe-and-repair) to the
complete delivered input. That is the common judgment for a first draft,
assessment and revision. Read what the input depicts, then judge how it serves
the commission. A renderer obeying every authored clause could still produce
a picture that misses the request if those clauses are poor choices. Keep
rendition adherence and service to the commission distinguishable. Do not
promote agent-authored detail into hard criteria merely to make it checkable.

A real conflict concerns the same subject, region, state and condition. An
opaque vase beside a transparent vase is coherent; requiring the same intact
wall both to hide contents and show them clearly in the same natural view
needs a different construction or an author decision. A cutaway can serve an
explanatory commission when presentation is open, but cannot silently replace
a fixed natural view. Difficult or unresolved construction is not proof of
impossibility. Compatible clauses are not by themselves proof of effective
expression.

Use the optional [competing-realization test](#competing-realization-test) for
an unresolved, consequential input reading. Preserve permitted variation and
judge at the precision the commission needs. Structured validation checks
declared assignments and bounds; the author evaluates their relevance and
agreement with the rendition. When a generated image is available, observe it
under [Production execution](production-review.md#observe-before-interpreting)
and compare it with the same commission and applicable sources. Neither a
valid request nor a criterion supplies evidence of rendered success.

## Competing-realization test

Test a consequential uncertainty about what the delivered input communicates.
Reconstruct a coherent reading of that complete input and a materially different
plausible reading relevant to the uncertainty. Interpret wording in context;
do not create a failure by dropping an instruction or choosing an implausible
isolated sense. The purpose is to distinguish an intended result from a credible
miss, not to eliminate all visual variation.

Use a separate input-reader context when available. Supply the final positive
and applicable negative text, supported controls, and the media actually delivered,
including only reference assignments carried in that input. Ask what complete
depiction it establishes, how its parts direct attention or communicate an
effect, and which instructions or media constrain the uncertain relationship.
When the question concerns interacting conditions, have the reader trace them
through the same construction. Distinguish a workable realization, a supported
conflict and an unresolved construction, and identify consequential choices
the reader supplied. A fluent account of the intended result alone does not
settle feasibility; a possible arrangement alone does not settle its effect.
Withhold the conversation, production history, preferred frame,
planning criteria, earlier failures and the author's expected interpretation.
The reader can conclude that a proposed alternative does not satisfy the input,
or that the apparent uncertainty is already resolved.

Compare the reading with the authoritative request and applicable sources,
including explicit details and permitted variation. Revisit the author's own
derived criteria in that comparison; they are interpretations to justify, not
additional authority. If the same separate reviewer performs this comparison,
provide the request and sources after its input-only reading and distinguish
that assessment from the renderer's available information. Do not substitute
an extracted list of hard conditions for the request it was meant to express.

A reading that changes the requested meaning or violates a fixed property can
identify a missing premise, relationship or conflicting instruction. Repair
that construction. A different reading that fulfills the same request stays
available. Record unavailable source evidence as a limit on the comparison.
Rejected alternatives and the comparison reasoning stay out of model-facing
text; they do not become a list of negative terms.

Record the reviewer's actual input boundary and the limitation of the method
in the existing review notes. A separate input-limited review reduces exposure
to the author's framing; it does not establish objectivity or a blind study.
When only the production context is available, perform an author self-review
and state that it is not independent. Asking that context to forget the intent
does not change its available information. A conversation-only task needs no
new record or approval step. See the
[synthetic review cases](../../examples/production-execution/evidence-review-cases.md)
for differing realizations and inconclusive evidence.

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

Establish the requested achieved state and the baseline properties and premises
that continue to carry the image. Use
[Observe and repair](production-direction.md#observe-and-repair) to diagnose
what needs changing, and rebuild the responsible depiction, context, reference
role or wording. Apply the complete-input review above to the resulting
rendition. A revision request framed as "less" or "not" still needs the intended
remaining quality and degree, unless the requested boundary alone completely
defines the change.

Use [Revision Contract](revision-contract.md). `edit` is the default: preserve the current baseline except the requested paths and necessary, explained consistency changes. `explore` varies non-frozen axes only when a new alternative is requested. `retarget` preserves structured meaning while changing interface-specific rendition. Keeping a draft choice during a local edit does not promote it into permanent identity.

Interpret a newly supplied reference against the current request to establish
its role, assigned properties and effect on the revision's scope. Inspect the
source and the corresponding construction in the current depiction to resolve
that request. A complete-design assignment needs the full design considered
together; a reference's other differences do not expand a local change. Apply
the source interpretation and delivery distinctions in
[Construction order](#construction-order).
Ask only when an unresolved role would materially change what is being revised.

When a pack changes, refresh retrieval under the current snapshot and validate
the affected choices. Disclose necessary consistency changes and keep the
revision within its authorized scope. When editing a canonical record, reread
the whole record for coherence and update the affected relationships together.

## Negative output

Read `cpb-resource:negative-policy` and record the exclusions selected for this
composition. First establish whether a source constraint governs this depiction,
its reference use or a separate authoring decision. Select image exclusions for
the first two purposes; keep the author's other obligations with their owners.
Resolve a missing present-scene premise through the scene description. Consider:

1. central hygiene and integrity bundles for structures actually implied by the subject, pose, and framing;
2. drift terms from the selected render profile;
3. terms from corrections activated by a concrete risk;
4. explicit user exclusions.

Do not sweep record diagnostics, scene failure modes, domain boundaries, or semantic alternatives into the negative automatically. Romance, hostility, dominance, age, gender, genre, and similar alternatives enter only when the user explicitly excludes them. Apply structure-specific terms to the intended depiction and relevant construction risks. Known anatomy alone does not require describing every part's visibility. For an interface without an independent negative field, integrate necessary exclusions through affirmative construction or explicit negation according to their meaning. Keep the selected source evidence with the composition; a source does not require its own clause when another instruction already carries the constraint.

## Conditional specialists

Read only when needed: [Creative Core](../creative-core.md) for direction examples; [Character Domains](../domain-model.md) for domain choice; [Anthro Prompt Anatomy](../anthro-prompt-anatomy.md) for anthropomorphic construction questions; [Preset Authoring Standard](../preset-authoring-standard.md) for positive/diagnostic separation; [Troubleshooting](../troubleshooting.md) for workflow symptoms and failed outputs.
