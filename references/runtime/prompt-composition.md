# Prompt Composition Runtime

Use for every prompt. Load specialists only when activated.

## Contents

- [Image intent and anchor integrity](#image-intent-and-anchor-integrity)
- [Whole-image art direction](#whole-image-art-direction)
- [Construction order](#construction-order)
- [Representation grammar](#representation-grammar)
- [Catalog retrieval and inspection](#catalog-retrieval-and-inspection)
- [Prompt assembly and review](#prompt-assembly-and-review)
- [Creative latitude and interaction](#creative-latitude-and-interaction)
- [Revision contract](#revision-contract)
- [Negative output](#negative-output)
- [Conditional specialists](#conditional-specialists)

## Image intent and anchor integrity

Before lookup, privately state in one or two sentences what must be visually true, what holds the image together emotionally and visually, how the subject relates to the viewer, another subject, an object, or the environment, and which medium and finish hold the image together. This image intent describes the finished picture rather than listing attributes. Do not show the private statement unless it helps the user understand a choice or the user asks for it. Presets support the direction; they never choose it.

Separate anchors from creative space. Never silently alter species, age, build, color, clothing, exposure, role, action, relationship, camera, lighting, or medium. Ask one compact question only when ordinary language understanding still leaves two or more similarly natural readings that would produce materially different images. Do not treat every omission as ambiguity, and do not call a familiar expression ambiguous merely because its individual words admit several translations.

When the user specifies anime, produce anime. When the user specifies photorealism, produce photorealism.

Forbid silent constraint injection (an unrequested restriction) and motive substitution (an agent change presented as craft).

Disclose every anchor change and its actual reason separately from creative rationale. Preserve unresolved wording until interpreted; missing catalog vocabulary does not erase it.

## Whole-image art direction

For a well-specified brief, privately compare two to four coherent treatments of the same intent and choose one. For a sparse brief, use the direction-card procedure in [Sparse-Brief Discovery Runtime](sparse-discovery.md). Never average candidates.

Resolve these as one system:

- center of appeal;
- subject-viewer, subject-subject, or subject-environment relationship;
- viewpoint, framing, depth, silhouette, focal sequence, and visual weight;
- one medium family, unless a deliberate hybrid is requested;
- major masses, directional rhythms, repeated curves or angles, and useful negative space;
- anatomy, hair, fur, skin, feathers, scales, fabric, casing, metal, water, props, and effects as applicable;
- local-color hierarchy and one lighting thesis;
- edge, texture, finish, and complexity concentration.

When medium is open, resolve `cpb-resource:project-defaults` from its explicitly selected provider. The bundled commons pack selects `profile-clear-2d-illustration`, a polished 2D character-illustration direction; inspect that complete profile before using it. A non-bundled provider may deliberately select another project default. Treat production knowledge as four distinct layers:

1. A universal aesthetic core is optional, zero or one. It provides domain-neutral appeal, hierarchy, viewer relationship, shape rhythm, tactility, color-light taste, and finish. It may sharpen an already chosen direction, but never supplies anatomy or chooses the concept.
2. A concrete style family is optional, zero or one. It is an indivisible drawing grammar binding line hierarchy, form abstraction, value and shadow design, highlight placement, color behavior, surface grouping, background treatment, detail hierarchy, and domain-specific realization. Select one only when it closely fits the direction. Use its linked rendering profile as the medium envelope and scoped negative boundary, not as a second positive grammar. If no family fits, proceed with a rendering profile directly.
3. A domain realization is normally required for each represented subject domain. It translates the direction into valid identity cues, anatomy or body plan, expression channels, locomotion, surfaces, materials, contact, and environmental interaction. When a family is selected, use that family's matching domain overlay together with the selected domain realization.
4. A rendering profile is optional, zero or one. It owns the medium envelope and general mechanics: line, value structure, color behavior, surface rendering, light response, background policy, detail hierarchy, and medium-drift boundaries. Without a family it supplies the primary grammar. With a family it supplies compatibility and negative scope while the family remains the primary positive grammar.

Then use only compatible atomic modules and activated corrections for specific construction questions. Aesthetic touches may refine the family only when they preserve its line, value, highlight, and surface systems. An empty candidate group is valid.

The authority order is:

```text
explicit user intent and approved canon
-> meaning of the whole brief
-> approved identity and state artifacts, when present
-> image intent and selected art direction
-> scene projection and Production Specification
-> inspected production-knowledge records
-> explicitly selected project defaults
```

## Construction order

Resolve large relationships before local detail:

1. subject count, domain, and identity;
2. support, contact, overlap, and prop ownership;
3. camera position, distance, lens behavior, pitch, yaw, roll, and crop landmarks;
4. major silhouette, depth order, and frame occupancy;
5. action chains from declared roots or carriers through their actual connections and contact points;
6. coordinated expression, gaze, posture, gesture, appendage, physiology, or mechanical signals;
7. clothing construction, grooming systems, markings, accessories, and distinctive details;
8. representation grammar, lighting, material response, and finish.

Every visible hand, paw, foot, tail, wing, manipulator, tool, garment panel, or accessory needs an owner and a traceable attachment path. A required feature outside the crop remains known off-screen structure. State whether each implied body region is visible, exits a named frame edge, or is occluded or supported by a named surface.

The user's species or declared topology is authoritative. Do not average neighboring species. Coordinate muzzle projection, nose thickness and placement, ear construction, cheek and jaw mass, eye placement, limb topology, digit system, tail or wing attachment, and surface behavior as correlated evidence. Body build, muscularity, frame mass, and surface character are separate axes. A powerful body does not imply a chiseled face. Keep face and body on the same declared frame-character projection. Camera roll may tilt the frame and environmental lines, but it must not deform the subject's local anatomy. Perspective enlargement belongs to camera distance, not identity.

For an ordinary animal, preserve natural anatomy, locomotion, support, behavior, and environmental contact. Carry performance through gaze and head direction, ears or feathers, body tension, breath, timing, distance, and species-appropriate movement; do not impose a human pose, hands, upright stance, facial grammar, or clothing unless the brief explicitly designs them. For a robot or android, resolve chassis or body architecture, load-bearing articulation, joint range and mechanical clearance, sensors or optics, manipulators, materials, emissive systems, wear, tools, and locomotion as one functional structure. Do not translate those systems into human anatomy by default. In addition to these inline baselines, load both [Morphology and Species Contracts](../morphology-and-species-contracts.md) and [Species Architecture](../species-architecture.md) for every unfamiliar creature, hybrid, ordinary animal, robot or mechanical body plan, transformation, unusual feature count, and recurring identity. The inline summary is not a substitute for either authority.

Treat performance as coordinated evidence, not a face label. Resolve felt emotion, displayed emotion, masking or conflict, intent, intensity, temporal phase, and relationship. Use the channels the subject possesses: eyes, lids, pupils, brows, mouth, tongue, teeth, cheeks, flush and breath; head, shoulders, torso, hands, feet, distance, support and contact; ears, whiskers, ruff, mane, hackles, tail, wings, fins, antennae and tentacles; or optics, shutters, indicators, displays, manipulators, ventilation and servo cadence.

Names such as `tank top`, `shorts`, `long hair`, `black nails`, or `black claws` are insufficient when construction is identity-bearing. Use openings, panel paths, strap widths, coverage, rise, inseam, pose response, nail or claw length and tip geometry, landmark-relative placement, physical depth, color relation, count, distribution, asymmetry, and visibility rules as applicable. Distinguish stable grooming topology from temporary wind, wetness, disorder, compression, raised fur, or styling.

Declare only the structures the request or adopted design actually establishes. Keep independent systems separate; a name never adds anatomy. Apply [Declared Structures Runtime](declared-structures.md) to growth, frame, terminal, garment and topology contracts. Specialist examples are optional detail, not mandatory presence/absence checks. Load [Growth Geometry Specification](../growth-geometry-specification.md) when growth construction is load-bearing. Preserve local scope when rendering its wording; a change to one region does not describe the whole subject.

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

Before atomic retrieval, always run one `search --kind archetype` query with the subject's species, build, proportion, and age or presentation, one `search --categories occupation` query for an explicit role, and one semantically focused `search --kind scene` query with the required staging relationships. Express each in three to six distinctive words when that preserves the full requirement; otherwise retain the additional words needed for exact scope. Do not silently downgrade either required query to generic inspiration. When the subject is an anthropomorphic animal, creature, or hybrid, add one `search --categories creature-anatomy` query naming the subject's lineage (for example canine, feline, dragon, avian, marine) so the lineage anatomy grammar and its invariants enter inspection, and when the direction asks the subject to express emotion through an appendage such as a tail, ears, feathers, or flukes, add one `search --categories body-language-cue` query naming the emotion and the appendage so the matching cue record, its invariants, and its misreading list reach the review. When the selected pack provides `cpb-resource:reference-cluster-mapping`, resolve it from that explicit provider to relate recurring brief patterns to records in the same pack; otherwise rely on catalog search and record inspection. The mapping is an index aid, not an authority or a substitute for search and full-record inspection. An archetype is an identity contract, not a scene choice: adopt its `identity_invariants` and `marking_logic`, including its `automatic_prompt_injection` identity constraints, or diverge deliberately. A matching base scene supplies staging geometry and its `failure_modes` become review knowledge. `inspire` may return a `subject_archetypes` candidate group, but base scenes and finished recipes remain reachable only through `search`.

Adopt at most one useful core, style family, and rendering profile, plus the domain realization for each represented subject domain and only compatible atomic modules. A finished recipe is optional. An archetype is an identity contract, not a scene: adopt its identity invariants and automatic identity constraints, or diverge deliberately. A scene supplies staging; keep its failure modes as review knowledge.

Use `--tier curated` only when the unresolved question requires a complete blueprint. Use `--tier vocabulary` only for a naming or option question. Leave the tier unrestricted when either complete production knowledge or model-legible vocabulary may answer the question; these are different functions, not quality ranks.

Treat an empty candidate group as valid. Read `query_token_count`, `axis_coverage`, and any `retrieval_note` in the complete response. `axis_coverage.unqueried` identifies art-direction axes that the requested categories never asked about and names categories that can query them; it does not prove missing catalog coverage. When every requested group and category is empty, or when `retrieval_note` reports that every requested atomic category is empty, separate materially different craft questions and retry each as a focused three-to-six-word query before concluding that coverage is absent. Preserve all anchors and modifier relationships during that retry; the range is a query-dilution diagnostic, not permission to discard meaning. Otherwise reformulate only when the semantic craft question itself should change, then art-direct genuinely unsupported axes.

Inspect the complete record after selection. The canonical record is not a summary. Read relationships, invariants, adaptation rules, `misreadings_to_avoid`, and scene `failure_modes`. `curated` records provide complete production knowledge; `vocabulary` records provide names and model-legible phrasing that the art direction must complete. These are functions, not quality ranks.

After inspection, run the Visual Reference Activation Gate for every selected record. Run full `asset-lookup` for each record before final prompt delivery or image-generation packaging, even when no linkage is already known and even when the requested deliverable is prompt-only. The operation returns complete active-pack ownership, resource details and source bytes, artifact paths and hashes, linked canonical records, and technical artifact roles. Review that complete result before deciding whether any visual contribution is adopted. Continue with [Prompt Artifact Reference Runtime](reference-prompt-artifacts.md) when evidence is adopted.

`asset-lookup --summary` remains available as an optional compact preview of linked asset IDs and declared technical roles, but it is not the activation gate and never replaces the mandatory full lookup. Do not use the summary to make the adoption decision, infer complete ownership or authority, or exempt a selected record from inspection.

## Scene specification

Every final image uses a current [Production Specification](../production-specification.md), including an ordinary one-off prompt-only image. Start from `templates/production-spec-template.json`, set `state_context.mode` to `stateless` when there is no managed temporal canon, author the current scene structure directly rather than patching an older prompt, and validate it before final prompt delivery:

```bash
python scripts/production_spec.py validate production-specification.json --require-content
```

For state-aware work, follow the State-Aware Series Runtime and reference the sealed lineage, scene context, identity, snapshot, and projection artifacts. For stateless work, do not invent those series references; the same current Production Specification structure still owns the exact one-image scene, camera, relationships, materials, and construction obligations.

## Prompt assembly and review

Write natural-language art direction in this order when useful:

1. subject and permanent identity;
2. action, expression, interaction, or performance;
3. composition, spatial relationships, camera, and crop;
4. aesthetic taste, center of appeal, and the strategy that makes the image desirable rather than generic;
5. environment and physical lighting;
6. medium, shape, line, value, color, surface, and finish;
7. critical construction constraints.

Explain visual relationships rather than replacing them with vague tags. The prompt should tell an illustrator what happens in the image and why the visual choices belong together. Keep enough detail to guide construction without flattening hierarchy, and repeat only a truly critical invariant. State affirmative evidence that only the correct geometry can show. A property can also be carried by an action that is only possible when the property holds, so the model draws the property to draw the action: a figure on the toes to reach a shelf carries the height difference, a jar lifted with both arms carries its weight, a sleeve pushed back carries a coat too big for the wearer. Prefer this carried form when the direct word is vague or has already failed to hold, and write the action alone rather than the action beside the statement, so the surface has one carrier. On a prose-only interface, convert a predicted failure into the opposite visible construction; never mention the failure concept in the positive prompt.

The vocabulary also carries phrase sets for prose surfaces (one-sentence camera, action, scene, audio, style, and character phrases, and expression and hair phrases): on a surface that reads prose, take the shape of a phrase and replace its subject rather than pasting it, and on a tag surface break a phrase into the component tags. A separate artist index lists artist tags one anime-line checkpoint knows with their frequency; an artist tag pulls the rendering toward that artist, so treat it as a way to find a rendering family and then describe the look in the prompt's own words, and leave the decision to lean on a named artist's style to the user, stated in the open. A dictionary that covers a tag set covers all of it, including the names of other people's characters and the words for what a project would rather not draw; a term being present is a statement of what it draws, never a recommendation to use it. Two kinds deserve care. A character or work name carries that character's whole trained design, so it overrides a character sheet and quietly replaces the figure you described: name a source only when you mean to borrow the design, and never beside your own character's parts. And a word for an injury, an explicit act, or a state you do not want is drawn when it is written, in the primary field or a negative field alike, so read the description before placing one. A character record states what is true of the character; a prompt states what one picture shows. Copying from the first into the second without filtering is the most common way a prompt goes wrong, because a property that is true is not always visible: an eye colour is not visible when the eyes are closed, a tail marking is not visible when the tail is behind the body, a shirt is not visible under a blanket. Written anyway, the invisible property does not join the picture; it becomes a second statement the surface reconciles with the first, and it reconciles by making the property visible, which changes the shot. So an identity block is a source to draw from, never a block to paste, and each image's text is filtered against the frame it describes. Run the vocabulary pass per visual element before the wording is final. Read the finished text back before it is final: term by term, with what each term draws, which is where a term that contradicts the frame is seen. A text is not finished until it has been read back, and it is read per image rather than per identity block, since the block is shared and the frames are not. For each distinct element (pose, action, expression, camera, lighting, wardrobe, body feature, effect, and any specialized domain), resolve the active `prompt-vocabulary` resource and search it for the element's tag-level wording; when a dictionary term fits, prefer it as the compact model-legible tag and record the category it came from; when no term fits, or the prose relationship carries the meaning, keep the hand-composed wording and do not force a tag. Sibling-tag competition still applies: adopt one term per competing system (one build tag, one expression system) even when the dictionary offers several. When a session proves a new effective phrase that the dictionary lacks, fold it back into the owning dictionary as a term with a description.

This reviewed wording is the master prompt. When a target model or interface is named, use [Prompt Writing Guide Runtime](prompt-writing-guide.md) and the selected adapter only after semantic review. The guide controls target rendition, not image meaning; vocabulary, weights, LoRA notation, embeddings, negative channels, and platform parameters must remain subordinate to the approved image intent.

Make those repairs local and observable. A low-angle misreading becomes `the camera sits below the subject, vertical structures converge upward, and the underside of the jaw is visible`; a cropped-torso risk becomes `the torso continues through the waist and hips and exits the lower frame edge`. Do not name a duplicate limb even in a denial. State countable structure beside the governed region, such as `two elbows, one on each side, the right elbow bent`, rather than as a distant tally that loses the emphasis budget.

Review only the finished prompt:

- Does the likely image fulfill the intent and every anchor?
- Are gaze, lids, brows, mouth, tongue, blush or physiology, head, shoulders, hands, feet, appendages or mechanical signals, gesture, posture, support, contact, depth, and viewer relationship coordinated?
- Does the performance distinguish felt, displayed, and masked emotion, preserve plausible alternate readings, and choose the reading that fits the current brief, relationship, state, and intensity?
- Did shorthand turn into a different action, attitude, medium, or subject type?
- Does every invented detail reinforce the center of appeal?
- Did an optional universal core remain domain-neutral while each domain realization supplied the subject's valid anatomy, behavior, expression channels, surfaces, materials, and contact?
- Is there one coherent medium and production grammar? If a style family is selected, do line, form, shadow, highlight, color, surface, and background still act as one family rather than a mixture of touches?
- Does the prompt preserve every material relationship recorded in the current Production Specification?
- Does each subject match its current snapshot rather than a previous or future state? Are expressed emotion, public mask, relationship distance, wardrobe layers, inventory ownership, and environmental response consistent with the current context and projection?
- Are occluded or undisclosed facts absent from the visible description while approved performance consequences remain?
- For every selected record, were its `misreadings_to_avoid` and any matching scene's `failure_modes` reread against the finished prompt? If the wording still permits a predicted misreading, prevent it with affirmative visible construction or an activated correction.
- Are all implied body regions visible, named-edge continuations, or named occlusions?
- Are adopted archetype identity constraints and connected marking logic present?
- Does every task-bearing limb form one visible root-to-contact path?
- Are scars, markings, notches, claws, tattoos, wear, wrinkles, and asymmetries fixed to the correct subject-relative side, landmark, scale, depth, color relation, and visibility condition?
- Did the result collapse into generic preset output or retain a distinctive center of appeal?
- Did any unrequested constraint enter the prompt? Remove it unless the chosen art direction requires it; if it changes a user anchor, disclose it separately as a modification with the actual reason.

If any applicable answer is weak, revise the prompt and repeat the review. Do not advance to reference materialization, packaging, delivery, or generation while a known weakness remains.

A three-quarter rear or strongly turned torso combined with a manual task at chest or collar height, often with an over-shoulder glance, is a composition conflict rather than a wording defect. The framing supplies a visible back-side arm while the task supplies a front-side hand, and the model may complete both as separate limbs on one side. Symmetric limb grammar, full shoulder-to-hand path wording, a named far-arm occluder, and adjacent visible-elbow counts did not reliably fix this observed failure on a prose-only interface. Either recompose so both arms are fully visible from shoulder to hand, or keep the turned view and move the task off the torso midline so each arm remains on its own side, with props resting rather than gripped. When this conflict is diagnosed, search the active catalog for a matching turned-torso duplicate-limb correction and inspect the exact resolved record before use. Do not assume an optional-pack correction ID in core logic; diagnostic vocabulary belongs only in a real negative channel.

**Naming a thing asks the model to show it.** Every term is a visibility request as much as a description, so a tag whose subject the composition should hide fights the composition. Region-specific colors and anatomy tags for covered areas (chest fur color, abs, pecs, belly markings) pull clothing open or off; a garment named for a crop that excludes it pulls the crop wider; an accessory named while the character faces away rotates the character. In a clothed prompt, describe only exposed regions plus the garments, and let the garment wording carry everything beneath it. In a cropped prompt, name only what the crop contains. When a stubborn conflict appears between what is named and what is worn, framed, or occluded, audit the prompt for terms whose subject cannot be visible in the requested image before reaching for weights.

**What the situation already supplies is not written.** These models carry a world. A figure described as asleep on a bed comes back with its head on the pillow, its legs present, its weight on the mattress and a pose that holds together, none of it asked for. Writing those consequences is not free: each one adds weight to its subject, and each one is another statement that can argue with the rest. A sleeping figure given a framing word came back with no legs; the same figure given the legs a placement came back sprawled; with both removed and nothing put in their place, the pose was correct. Write the situation, and the facts the situation cannot imply, and let the consequences follow. When a returned pose is wrong, look first for another sentence arguing with the situation, not for a missing instruction.

**What an input carries is not written either.** A scene plate carries the room, the camera position and the light. A reference image carries the face, the build and the clothing at the scale its framing shows. Restating any of that in the text is worse than silence, because a wrong restatement overrides the input: a plate holding the bed at the right of the frame, described in the text as standing at the left, returns the bed at the left, and every later shot that shares the plate is mirrored against it. Take an inventory of what each input holds before writing, and write only what none of them holds.

**Diagnose a wrong result before editing it.** Work down this order and stop at the first that applies:

1. The defect is already in an input. Repair the input. Text written to fight an input is the most expensive repair there is.
2. Two statements cannot both be true of one picture. Remove one of them; the model has already dropped the other.
3. One subject is named more times than the picture needs. Naming is weight, and the subject grows to match: bedding named three times returns a figure buried in it.
4. The text states something the situation or an input already supplies. Remove it, then check whether it also contradicted what it was restating.
5. A framing word excludes something the text names. One of the two goes.
6. Only when none of the above applies is a fact the shot needs genuinely absent. State it once.

An addition that argues with a sentence already in the text, or with an input, is not a repair. It is evidence that something else should have been removed.

**Vocabulary carries cluster baggage beyond its literal sense.** A term's training neighbourhood travels with it: a garment word can be dominated by one gender's imagery, a pose word by one genre's staging, a medium word by one era's palette. When a prompt flips to an unrequested gender, species, genre, or setting despite correct explicit tags, suspect a cluster pull from an incidental word rather than a failure of the explicit ones, and probe the alternatives before escalating weights. Corpus frequency checks over the model's training vocabulary answer this quickly.

**Structure beats quality words for any feature that must stay stable.** Asking for a good, detailed, or beautiful feature leaves its actual form to the sampler, so it re-rolls every generation. Name the form instead: the eye's shape family, the brow's set, the mouth's configuration, the ear's angle. A recurring character's face is stabilized by naming its structure once and reusing that wording, not by raising a detail weight.

**A tag checkpoint reads its first window hardest.** On SDXL-family checkpoints the first block of about seventy-five tokens carries the picture; what falls past it is read faintly or not at all, and two prompts that differ only past that point return the same image. Put the view, the garments, and the state the panel exists to show in the first block, right after the subject, and let a seed or reference carry the identity the model already knows rather than restating it ahead of the garments.

**The first window is a budget, and every phrase added spends it.** When a pose phrase, a weight, or a view is added at the head of a tag prompt, whatever stood at the end of the first block falls out of it, and the garment or feature it named reverts to the model's default: sleeves grow back, a colour changes, shoes vanish. Reread the whole first block after any addition, keep the pose phrase short, and name each garment as one bound phrase (`grey sleeveless hoodie`) rather than as separate adjectives that a later word can detach.

**A seed reproduces a prompt, not a character.** With the prompt held, a seed returns the same picture; with the prompt changed, it returns a new one, and nothing of the earlier design survives in it. Identity on a surface that takes no reference arrives only as an image (a seed image drawn from the sheet), never through the seed number. **A tag reaches every figure in the frame.** On a tag surface a garment, a colour, or an expression is not addressed to one of two figures; it is drawn on whichever figure the model finds room for, usually both. Give a two-figure picture its per-figure facts in prose on a surface that reads prose, and keep the tag step to style and to what the picture already contains.

**A place named beside a full figure is fitted into the margin.** A tag checkpoint composes the figure first and puts the named doorway, counter, or window into whatever space is left, so architecture beside a full-body tag comes back at the width of the gap: a door a hand's breadth wide, a counter that ends at the elbow. When the structure must read at true scale, give it the frame: a medium shot with the figure smaller, the structure named first, or a scene panel drawn without the figure and the figure composed against it by a reference-capable surface.

**Identity holds at the scale the training saw.** A tag checkpoint trained on figure-centred images keeps a face and a body correct at close and medium scale and loses them as the figure shrinks toward the width of a hand: the muzzle flattens, the markings drift, the hands and feet go generic. Do not ask such a surface for a recognisable character far from the camera. Frame closer, keep the far figure faceless or turned away, or compose the wide frame on a reference-following surface and use the checkpoint for the close rendering. The band is read from returned results, not assumed; a surface that holds identity at a distance has shown it.

**A prompt describes the picture the camera takes, not the scene a narrator knows.** Blocking, a script, and a novel say where a character stands and faces in the world: his back to the door, facing the window, turned away from the other. A prompt says what the lens sees from where it stands: in profile at a table on the right of the frame, the back of a head in the left foreground, a face turned three-quarters toward the camera. The same world fact becomes different words for every camera position, and a blocking phrase carried into a prompt unchanged is drawn as a picture relation, with the back toward the viewer whatever the room says, because the model has no room, only the frame. Translate every orientation before it enters model-facing text: take the character's facing in the world and the camera's position, work out what the lens sees, and write that. Where the geometry already settles it, write the action and the fixture and nothing about facing at all.

**Only words for what should be visible belong in a prompt.** An image model reads every word as something to put in the picture, camera idioms and framing directions included: a view named after an animal draws the animal, and an instruction about where the head sits in the frame moves the head. Name a view with plain words for what the camera sees (from above, overhead view; from below, seen from underneath) and describe the subject, never the page. When a result shows something the prompt did not ask for, read the prompt before blaming the model: the word that names the stray thing is usually there, so remove it or say it plainly, and carry the stray thing in a negative field only as insurance against a prior the text no longer feeds.

**An emotion word is drawn at its peak.** A tag such as `happy`, `angry`, or `sad` returns the strongest face the model associates with it. A subtle state is written as the states of its channels (light smile, closed mouth, half-closed eyes, ears aside) with the emotion word left out, and a neutral face is asked for as `expressionless` with the mouth and gaze named, because an unnamed channel is filled by the nearest emotion the rest of the prompt suggests.

**An emotion tag brings its drawn marks.** Surprise, confusion, exhaustion, and embarrassment are tagged in the training data together with the sweat drops, question marks, bubbles, and shock lines drawn beside the head, so the tag returns the marks. A panel that must be clean names the channel states instead of the emotion, and lists the marks themselves (`sweatdrop`, `question mark`, `motion lines`) in the negative field, because a negative that names only the emotion leaves the marks in place.

**A tag is spelled the way its training source spells it.** The booru side writes `closed eyes`, `animal ears`, and `looking at viewer`; the furry side writes `eyes closed`, `ears back`, `ears up`, `ears down`, and `airplane ears` for ears flattened out to the sides. A checkpoint fused from both reads the form its subject matter was tagged with, so an anthro or animal subject takes the furry-side form and a human subject the booru form; when a channel does not respond, try the other source's spelling before adding weight.

**Change one channel by drawing over the accepted panel.** When a seed's rendering holds a channel against every wording (the eyes stay open, the mouth stays shut), send the accepted panel as the image input at a low strength (about half) with the one changed state at the head of the prompt, and drop every word for what the change hides (an eye colour on closed eyes). The composition, fur, and light survive and only the named channel moves. What a single asymmetric channel (one ear turned) needs is a model that has seen it tagged; when three wordings return symmetry, the state is not reachable by text on that checkpoint and the row is dropped or drawn by hand rather than pushed. The same pass cannot hold a state that the composition's own prior contradicts: an egg held over a hot pan is drawn cracking at every strength that changes the rendering, whatever the words say about the shell, because the arrangement itself is the model's cue for the crack. When a state must survive a restyle, compose the source so the prior agrees with it (the egg held away from the pan), or keep the source frame and let the video carry the state.

**The animal's word draws the animal's part.** For an anthropomorphic subject, name each part by its construction rather than by the species: `humanoid hands, five fingers, thumb` where the hands are human, `paws, pawpads` only where they are animal, and the same for feet, legs, and face. A close-up isolates the part from the upright body that would otherwise anchor it, so a species word there returns the feral part; put the construction words first and the animal's part words in the negative field.

**Small features fail for resolution reasons that no wording fixes.** When a feature renders muddy at full-body distance but cleanly in a portrait, the cause is the pixel budget that feature receives, not the tags describing it. Raise the canvas, reframe closer, or move that feature's proof to a dedicated close-up rather than escalating its weight; weight escalation on a starved feature buys artifacts, not fidelity.

**Delete the cause before negating it.** When an unwanted quality appears, the first question is which positive term invited it, not which negative term could suppress it. A negative aimed at a quality that a positive term is actively requesting fights inside the same representation, and the collision usually damages the wanted content alongside the unwanted: suppressing cartoon proportions can flatten the large gesture that pulled them in, suppressing a garment style can strip the garment. Removing the inviting term costs nothing and often fixes the image in one pass. Reserve the negative channel for qualities that arrive on their own, with nothing in the prompt asking for them.

**Shorter is a repair, not a concession.** A prompt that failed does not become correct by growing: added qualifiers and stacked negatives dilute the emphasis budget and multiply the chances of a cluster pull. When a revision is needed, first look for terms to cut - redundant restatements, decorative adjectives, negatives that duplicate what the positives already exclude - and only then consider what to add. Two successive revisions that both lengthen the prompt are a signal that the diagnosis is wrong.

**Resistance thresholds are crossed by simultaneous levers, not by one lever pushed harder.** When a model persistently refuses a requested combination, the available levers are prompt position, term weight, guidance scale, an image-to-image seed that already contains the wanted structure, and the negative channel. Pushing one of them to an extreme distorts the image before it changes the refusal, while a moderate move on several at once often crosses it in one attempt. Expect a moderate cost at the crossing - drifted secondary colors, stray logos, mass thinned by denoise - and correct those in the following pass rather than accepting a failed combination.

Extreme worm's-eye views with a subject leaning within arm's reach of the lens often drift into a distant upward portrait. Stabilize them with, in order: a proximity-anchor foreground limb; the subject occluding the background so only edge slivers of sky or ceiling remain; gravity cues hanging toward the lens; a 10-15 degree lateral camera offset and slight cant rather than a mathematically vertical axis; and named-edge continuation for every cropped region. When the active catalog provides matching records, inspect the resolved proximity-anchor, loom-close, and frame-edge-continuation treatments before use. Their IDs and availability come from the selected pack state; core guidance must not assume that an optional pack supplies them. When image input or image-to-image is available, let structural evidence carry the framing while text carries identity and surface.

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

When a new reference arrives mid-iteration, inventory its differences from the last output across identity construction and all art-direction axes before deciding which axis the user wants changed. When the production library changed, refresh retrieval under the current snapshot and validate affected choices without reopening unrelated baseline decisions. Disclose any necessary consistency change; do not silently turn a local edit into a new concept. When editing a canonical record, reread the whole record for coherence rather than patching one prompt-facing field in isolation.

## Negative output

Resolve and read `cpb-resource:negative-policy` from the selected provider. Always retain a portable negative or equivalent diagnostic block. Activate only:

1. central hygiene and integrity bundles for structures actually implied by the subject, pose, and framing;
2. drift terms from the selected rendering profile;
3. terms from corrections activated by a concrete risk;
4. explicit user exclusions.

Do not sweep record diagnostics, scene failure modes, domain boundaries, or semantic alternatives into the negative automatically. Romance, hostility, dominance, age, gender, genre, and similar alternatives enter only when the user explicitly excludes them. A structure's omission from a flawed draft does not deactivate its integrity bundle; deactivate it only when the structure is affirmatively absent, off-frame, or occluded. For an interface without an independent negative field, translate only the activated technical requirements into affirmative construction language and keep the portable negative for traceability.

## Conditional specialists

Read only when needed: [Creative Core](../creative-core.md) for direction examples; [Character Domains](../domain-model.md) for domain choice; [Anthro Prompt Anatomy](../anthro-prompt-anatomy.md) for anthropomorphic prompt blocks; [Preset Authoring Standard](../preset-authoring-standard.md) for positive/diagnostic separation; [Troubleshooting](../troubleshooting.md) for workflow symptoms and failed outputs.
