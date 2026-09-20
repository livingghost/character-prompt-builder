# Troubleshooting

## Conditional catalog routes

Every correction route in this document is semantic rather than a promise that one particular record ID exists. Search the currently active catalog by the diagnosed symptom, inspect the exact returned record before use, and proceed without preset support when no matching record resolves. Never substitute an unrelated record or copy an optional-pack ID into core logic.

Find the symptom, jump to the destination. Consult this file during the step-8 art-direction review and again after any failed generation.

## Growth policy

This file stays small. It holds a routing index and **process-level** failures: ways of misusing the Skill that no drawable repair can encode. **Image-construction** failures belong in enabled `correction` records, where they are searchable (`search --kind correction`), carry scoped avoidance terms, and can grow without bound. When a new failure is observed, author a correction; add a prose section here only when the failure concerns the workflow rather than the picture. Construction sections provide explanatory context, while the matching correction record is the canonical searchable form.

## Symptom index

| Symptom | Destination |
|---|---|
| Output is polished but conceptually unrelated | section: The result is polished but feels unrelated |
| Output looks like a template | section: The result looks like a generic preset |
| Anime turned painterly, photo turned 3D, etc. | section: The medium drifts |
| Wrong gaze, gesture, or interaction | section: Gaze, gesture, or interaction is wrong |
| Fur is long, plush, or drawn hair-by-hair | search active corrections for close-lying fur and hair-by-hair drift |
| Polished target came out dry, sketchy, or paper-textured | search active corrections for process-word or medium drift; section: Representation grammar in `references/runtime/prompt-composition.md` |
| Every revision looks the same: wardrobe, palette, staging repeat | section: Revisions converge on the agent's first inventions |
| A supplied reference was matched on one axis while others still diverge | section: A reference is mined for one axis only |
| A surface the style omits keeps getting described and rendered | section: A surface the style omits keeps getting described |
| Body reads soft; muscles vanished | section: Muscles disappear under fur |
| Dark fur and dark clothing merge | section: Black fur and black clothing merge |
| Hand and held object fuse | section: A hand and prop merge |
| Technically fine, emotionally empty | section: The image is technically correct but emotionally flat |
| Meant looming close; got a distant giant | search active corrections for looming-proximity drift |
| Camera backed off; unwanted full body | search active corrections for camera pullback or coverage drift |
| A failure a record predicted still happened | section: A predicted misreading appears in the output |
| A long-patched prompt underperforms its shorter draft | section: Prompt economy preserves canonical records in `references/prompt-composition-geometry.md` |
| Output overshoots to the opposite pole after a scaffold swap | section: Prompt economy preserves canonical records in `references/prompt-composition-geometry.md` |
| Crossed limbs swap which one lies in front between generations | section: Spatial relations use three independent codes in `references/prompt-composition-geometry.md` |
| Repeated elements render uniform, or their positions break when the pose changes | section: Organic variation is a distribution in `references/prompt-composition-geometry.md` |
| A stated mood flattens into an average face | sections: Universal observation pass in `references/performance-language-specification.md` and Reference attribute audit in `references/preset-authoring-standard.md`; records: the geometry-annotated expression records |
| A stated camera move leaves the frame unchanged | section: Camera terms become visible consequences in `references/prompt-composition-geometry.md` |
| Feline reference is described as canine, or canine reference as feline | search active corrections for feline/canine face-scaffold drift; section: Reference-based feline and canine disambiguation in `references/species-architecture.md` |

## The result is polished but feels unrelated

Re-read the brief as a whole and restate the image intent. The prompt probably translated fragments instead of the pictured relationship.

## The result looks like a generic preset

The concept was replaced by the nearest record. Return to the chosen art direction and keep only preset knowledge that serves it.

## The medium drifts

Name one medium family explicitly, select one compatible rendering profile or style family, and activate its medium-drift terms through the negative policy.

## Gaze, gesture, or interaction is wrong

State explicitly:

- who acts
- what they act on or attend to
- where the viewer is
- how the head, eyes, hands, or body carry the action

Avoid relying on a short directional tag when the relationship is central to the image.

## Fur becomes too fluffy

```text
short close-lying matte fur grouped into broad color planes;
sparse tufts only at the cheeks, neck ruff, joints, and silhouette
```

Search the active correction catalog for records that explicitly constrain close-lying fur and hair-by-hair drift, then inspect the resolved record before use.

## Muscles disappear under fur

Describe anatomy as clean overlapping shape and value planes beneath the fur rather than skin-like contour lines drawn on top.

## Black fur and black clothing merge

Separate near-black materials by undertone and highlight behavior:

- fur: cool charcoal matte
- leather: narrow directional highlights
- woven cloth: soft fold contrast
- metal: crisp small highlights

## A hand and prop merge

Describe the contact path, grip point, visible fingers, and where the prop continues after the hand. Keep the interaction simple enough for the chosen crop.

## The image is technically correct but emotionally flat

The prompt likely contains attributes without performance. Add a visible decision: posture under tension, a withheld reaction, an environmental interaction, or a viewer relationship that expresses the image intent.

## A predicted misreading appears in the output

This is a process failure: the record that predicted it was retrieved and its diagnostics were read past. Re-run Prompt assembly and review in `references/runtime/prompt-composition.md`: for every selected record, ask whether the prompt actively prevents each entry in `misreadings_to_avoid` and each matching scene `failure_mode`. For prose-only models, convert each unresolved item into affirmative construction language from that same authority; for models with a negative channel, activate the matching correction.

## Revisions converge on the agent's first inventions

This is a process failure. Symptom: across several revisions for the same brief, wardrobe category, palette, staging, props, and camera repeat, even though the user never specified them. Mechanism: the first retrieval seeds the choices (a query word such as muscular surfaces athletic records, and the agent adopts their wardrobe and staging), and the agent then freezes its own inventions across revisions, often under the reasonable-sounding rule of changing one variable at a time. The freeze itself was never requested.

Repair: an agent invention is creative space, not an anchor, and every revision re-opens it by default. Only two things persist across revisions: user-specified anchors, and freezes the agent has explicitly disclosed as deliberate isolation choices the user can veto. When the user signals sameness, or simply on the second and later generations for one brief, vary the unlocked axes deliberately across the catalog's breadth: wardrobe family, palette, staging, camera distance, lighting, expression register, gaze target, and body build each have dozens to hundreds of records, and repetition wastes them. Retrieval seeding is diagnosable: if the current wardrobe or staging traces to the first query's incidental matches rather than to the brief, it is a seed, not a decision.

## A surface the style omits keeps getting described

This is a process failure. Symptom: a surface the target style deliberately leaves undrawn (fur, pores, fabric weave, panel seams) keeps reappearing in the output, and every attempted fix adds more language about that surface: shorter fur, sparser texture, an in-world reason the surface looks smooth. Mechanism: a completeness reflex treats an unmentioned surface as unspecified, so the agent describes a minimal version of it; under the emphasis budget every mention is a vote to render it, and diegetic justifications (fur so short it looks like skin) reintroduce the omitted concept as a property of the subject. The reference model is stylistic omission: the subject still has the surface; the artist declines to draw it, exactly as anime skin omits pores.

Repair, three rules. Describe the drawing's content, not the subject's covering: an omitted surface needs silence plus affirmative plain-field language for those regions, never an in-world explanation. Match the inventory: mention only the surface elements the reference or chosen direction actually contains, once each, with their silhouette character and nothing about their internal structure. Repair over-description by deletion: when the surface reappears, remove sentences about it rather than adding compensating ones, and compare the prompt's word count on that surface against the reference's actual visual inventory.

## A reference is mined for one axis only

This is a process failure. Symptom: the user supplies a reference image with a one-word scope (finish, style, vibe), the agent repairs that axis, and the user returns saying the build, face, camera, palette, or wardrobe are still wrong. Mechanism: the user's naming of one axis was treated as excluding the others, when it was only the axis they had words for.

Repair: when a reference arrives mid-iteration, inventory its differences from the last output across all eight art-direction axes plus identity construction before writing anything: build proportions in landmark ratios (shoulder span in head-widths, limb girth against the head), head and muzzle or face construction (length, width, cheek mass), camera distance and crop (which body landmarks touch the frame edges), palette and value range, wardrobe, staging, finish. Report the divergent axes, but apply only the user's requested scope during a local edit. Do not infer permission to replace other baseline choices from visual differences alone. Request broader scope only when necessary; alternative exploration requires an explicit explore operation. Reference authority and identity ownership still apply. See [Revision Contract](runtime/revision-contract.md).


## Calibration feedback gets minimal deltas

When the user adjusts a single axis, too long, too short, too bright, move that one axis by one step and change nothing else. Adding compensating clauses, restructured sentences, or rebalanced exclusions alongside the requested step reintroduces rejected constructions from the other direction and reads as regression. The paired-bound principle governs the record's specification; the turn-by-turn adjustment moves one bound at a time.


## A stack of diminishing words deletes the feature

Diminishing terms accumulate: a feature called flat, then short, then small, then explicitly shorter than its own width, carries four votes for absence against whatever single phrase asserts it, and renders as gone. Watch especially for structural words borrowed to describe an armature, such as a flat vertical face plane meant to convey human proportion, which read as direct commands about the feature's own geometry. Repair by removing the suppressors rather than by adding a compensating clause on the other side, since paired pushes at full strength oscillate.


## Unbounded features drift further every revision

A feature described without a bound, long back tufts sweeping past the skull, grows with each regeneration until the character no longer matches its own reference. State the limit in the same breath as the shape, such as short spikes that do not reach the shoulders. The same applies to an accent color given a location list: naming a place near a different feature, behind the ears, invites the color to colonize that feature, so scope the accent to its own system explicitly.


## Shorten the animal skull, do not swap in a human one

A face that reads close to human is usually an animal skull compressed along one axis, not a human skull wearing animal parts. Compression preserves width: the cheeks stay broad, the muzzle keeps its width forward to a blunt front, and no human chin taper appears. Specifying human facial proportions to get that read produces a narrow pointed face instead, and the error hides because the muzzle length looks arguably right while the width is wrong. When a reference reads as an animal despite a short face, describe what stayed animal before describing what shortened.


## Measure the bone, not the fur

Cheek tufts, ruffs, and mane spikes widen a silhouette without widening the skull beneath. Copying that silhouette width into the head's own geometry yields a round, short-faced animal that reads as a different species, and the error survives revisions because the reference genuinely does look wide. When calibrating a face from reference art, state which dimension belongs to the fur and which to the bone, and give the muzzle its own length and taper independently of the fur that flanks it.

## A feature stays large despite a shrinking ratio

A proportion expressed against the feature's own dimensions is self-referential: half of its own width still grows when the width grows, so successive reductions change little. Anchor the number to a landmark the feature does not control, an eye, the head's height, the gap between the ears, and the size becomes checkable and stable. Give adjoining structures their own measurements too, since a muzzle and the jaw beneath it read as one wedge when only one length is stated, and shortening the stated one drags the other with it.

## A species noun re-summons its default proportions

Every mention of a species part carries that species' default geometry with it, so a prompt that states a measurement once and then names the part four more times has cast one vote for the measurement and four for the default. State the geometry once, then refer to the region by neutral names, the mouth, the lip line, the front of the face, and keep the part out of any list of what carries the species read, since naming it there argues for its prominence. The species survives on the other carriers, the ears, the nose, the fur, the fangs, and the tail.

## Silhouette tufts vanish on a heavily muscled figure

The exemption that keeps gentle arcs clean covers more of a muscular body than of a lean one, since thick deltoids, lats, and thighs round their joints into wide curves, so the landmarks that should carry tufts fall inside the exemption and the contour comes back smooth. Scope the exemption to the long straight runs between landmarks and state that each named joint or volume handoff keeps its tuft even when a heavy muscle rounds it. Back and three-quarter-rear views need this most, since the shoulder and flank read there as their broadest arcs.

## Fluffiness was corrected by shrinking, and the coat disappeared

When a coat reads as too fluffy, the fault is usually the softness of the clump edges, and shrinking the clumps treats the wrong axis: the fur stops reading at all while the softness survives. Correct the edge first, keeping each clump a solid straight-sided point, and give the depth its own number anchored to the part it sits on, such as a fifth of that limb's width. Reference art that reads as clean and graphic often carries very deep tufts, and what keeps it from looking fluffy is the sharpness.


## Calibrate the species scaffold while preserving the identity anchor

A face calibration that keeps oscillating against a stubborn pull may be fighting the model prior summoned by the current species wording. Audit the reference directly: ear shape, ear set, ear orientation, muzzle reach, muzzle depth, nose proportions, jaw mass, cheek volume, and eye placement.

Keep the user species and the Character Identity Contract unchanged. Describe the required geometry in species-neutral language first. Consult `references/species-architecture.md`; when the selected pack state explicitly provides `cpb-resource:species-scaffold-map`, resolve and consult that provider as well. Do not fabricate a missing resource. A different species noun enters only after the modification is disclosed and approved; it never appears as a silent internal fix.

After changing any scaffold wording, remove counter-text that existed only to fight the previous prior and regenerate from the complete current records.

## A large feline keeps turning into a canine, or a canine into a large feline

This is a species-scaffold diagnosis failure. The visible outline can be misleading in
low-angle, three-quarter, or simplified 2D art. A pointed stylized ear can make a feline
look canine, and broad cheek fur can make a canine face look compact. Preserve the user
or Character Identity Contract classification, then inspect the complete scaffold.

Read muzzle reach and muzzle depth separately. A large feline uses a short deep broad
front with near-parallel side planes; a canine projects farther and usually tapers toward
the nose. When the silhouette is ambiguous, inspect the shadow beneath the nose, lip line,
and lower muzzle. A compact feline muzzle produces a short block-like shadow footprint,
while a projecting canine muzzle produces a longer wedge-shaped shadow. Then compare the
nose profile: stylized large felines often use a flatter thin dark nose plate set high on
the compact front, while canines often use a thicker rounded nose pad at the forward tip.
Ear tips and cheek mass confirm the reading: rounded large-feline tips and heavy cheek pads
support feline construction; pointed canine tips and forward-flowing bridge-to-muzzle
geometry support canine construction.

Do not silently replace the species noun. State the approved scaffold once, describe the
geometry directly, and search the active correction catalog for a matching face-scaffold repair when the
rendered face crosses the family boundary. Inspect the resolved record before use. Treat one conflicting cue as a stylization or
camera issue until the muzzle, shadow, nose, ear, cheek, and jaw evidence are considered
together.
## Camera distance or coverage drifts

Search the active correction catalog for a camera-distance and coverage-drift repair, then inspect the resolved record. Reassert subject-relative distance, shot scale, camera height, pitch, lens range, frame occupancy, crop landmarks, nearest form, and required visible elements. Diagnose whether the model changed the camera or changed the subject proportions.

## Deep armholes close into a standard tank

Search the active correction catalog for a deep-armhole-to-standard-tank drift repair, then inspect the resolved record. Anchor the armhole lower edge to the waist or upper hip, preserve narrow shoulder bridges and minimal side panels, and name the exposed lateral chest, lat, ribs, and obliques.

## Low-rise micro shorts become ordinary shorts

Search the active correction catalog for a low-rise-to-natural-waist drift repair, then inspect the resolved record. Reassert waistband height below the iliac crest, shallow rise, nearly zero inseam, high leg openings, minimal continuous seat coverage, and the exact crouch-conditioned waistband tilt and ride-up.

## Hair or nail identity drifts

Search the active correction catalog for the matching hairstyle-section-map or nail-shape-and-length repair, then inspect the resolved record. Reassert the hairline, parting, section map, landmark-based lengths, principal clumps, and color zones, or the nail and claw digit ownership, base, length, tip shape, curvature, material, and damage state.

## A smooth padded subject develops a chiseled or hollow face

The frame-character axis is missing, weak, or contradicted. Select or author one frame-character contract for both face and body. Restate cheek convexity, submerged cheekbone landmarks, jaw-corner rounding, joint surface, and body mass handoffs. Activate only a resolved correction whose scope explicitly matches smooth-frame to chiseled-face drift. Do not add its negative poles to unrelated prompts.

## An accessory changes size, side, count, or attachment

A label-only accessory was used where geometry was load-bearing. Add an `accessory-geometry` contract with landmark-relative dimensions, exact count, laterality or site, support and fastening, construction, color, material, layer order, body clearance, and pose response. Inspect the full support chain rather than the item in isolation.

## A visual guide averages identity or leaks its finish

Check `guide_scope`, `locked_dimensions`, `free_dimensions`, and visual authority. Use the selected visual authority and routing contract. The native-dimension source-derived perceptual vector projection is reference evidence, not an automatically selected runtime attachment. A guide from another identity must not be combined with the current character text.
