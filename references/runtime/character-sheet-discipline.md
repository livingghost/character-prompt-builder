# Character Sheet Discipline

Producing a canonical identity reference before production, so a recurring character stays the same character across poses, scenes, and sessions. The discipline is domain-neutral: it applies to humans, anthropomorphic characters, creatures, and machines alike, with anatomy-specific items treated as conditional branches.

## Why a sheet phase exists

Words fix rules; only a picture fixes a map. A prompt can hold the rules of a dense pattern field (a striped coat, a freckle field, a fabric print, armor panel seams). The placement of its thirty elements, the exact fork of one marking, and the precise reach of a scar are pixel-level facts that re-roll on every generation, beyond listing in words. The same applies to every character-specific fact: tattoo and marking layouts, per-part colors and sizes (skin, hair or fur, eyes, nails or claws), damage positions, height and build. Human production pipelines solved this long ago with a model-sheet phase: a canonical reference drawing that every later image is checked against. This discipline adapts that phase.

Insert the phase whenever a character is intended to recur. A one-off image can skip it; a second image already needs it.

**A sheet is built for the character, not for the shots on the current list.** It holds identity constant across every future image, including scenes nobody has written yet. Deriving the panel set from a scene list is the characteristic failure of this phase: the sheet then certifies exactly the poses and states already planned, and certifies nothing once the story moves. Build the sheet from what the character IS, and let scene work draw from that stock:

- the views its body plan requires;
- the parts and marks its identity ledger declares;
- the range of states its inner canon says it can occupy.

A panel unused by every current shot is normal. A state the character can plainly feel and the sheet leaves unproven is a gap, whatever the shot list says.

## The character layer: the inner canon that drives the form

For individualized behavior development, use [World-Coherent Creative Development](narrative-development.md) and the complete persona form with relevant world records. The sheet's inner canon is a scoped visual-production summary; those documents remain the authorities. An isolated visual brief can skip the life story; a recurring individualized portrayal should preserve its active rules.

Appearance may express, conceal or contrast with personality according to the adopted direction. Role, practical use, culture, chance and deliberate ambiguity are all valid reasons for a visual element; a readable temperament, counter-trait, weakness or symbolic explanation is optional for each one. Proposals remain provisional. Anatomy exists only where it is declared; personality and species license none on their own.

- **Behavioral identity.** Summarize applicable patterns, conditions and boundaries from persona, rather than a fixed number of personality axes. Use their actual expression or concealment in the chosen scene.
- **Design concerns and motifs.** Record the adopted motifs and their scope where useful. The theme count is open, and an element may symbolize none of them. Review unexplained drift against the intended world and design rather than a universal symbolism test.
- **Role, world, and standing.** Occupation, era, and social position drive the costume, the items, and the registers the character may appear in.
- **Signature poses and mannerisms.** Summarize the persona's adopted, scoped baseline and range, with relevant rule/phase references. A typical stance is an option in each scene rather than a mandate; body shape and temperament are independent.
- **Conditional performance changes.** Use [Character Performance](character-performance.md) and [Authorial Intent](authorial-intent.md) to connect the scoped identity center to appraisal, context, voice and body. Select stable presence, designed contrast or an authorized departure under that aim; physical plausibility alone leaves the choice open. The sheet keeps a bounded visual-production view of the owning persona rules rather than another editable emotion-to-pose table. Name changed and held channels, targets, activation, overlap with audience/task/relationship, timing and release where relevant. Resolve the actual scene against current state; the state label alone leaves the row open, and a feeling may stay hidden. Form-specific remapping requires declared structures and adopted rules.
- **Relationships and stance.** How the character faces rivals, partners and strangers, which constrains expressions and poses in any multi-character scene.
- **Unseen settings.** Facts absent from every image that still shape it: an alternate form, a past, a habit. Recorded so revisions stay consistent with them.

In production, this layer informs the performance contract. Review expressions, poses and register against the applicable persona range, current conditions and declared expressive channels rather than a single frozen expression. Cross-channel lag, masking or minimal response may be intentional. Review the intended constancy/contrast over the actual requested span as well as this panel. This is a semantic review rather than a pixel or string equality proof of personality.

## The kind layer, and binding levels

Characters descend from many silhouettes, and a sheet format that assumes a human one breaks on the first slime, hydra, swarm, or ship. Separate formats per domain would fracture the audit and the machine lane, so the answer is a second layer above the individual:

- **The kind sheet** is the baseline contract of a species, type, or model line. It declares:
  - which identity axes exist at all;
  - which view set is canonical for this body plan (a humanoid's front, back, and profile; a serpent's coil and extension; a swarm's unit design and formation rules; a multi-headed kind's head count);
  - which parts exist;
  - which values the kind fixes for every member;
  - which axes are left to individuals, with their permitted ranges.

  One kind sheet serves every individual of the kind, and it maps directly onto the species and archetype records the pack already keeps.
- **The individual sheet** references its kind (or stands as its own kind when the character is one of a kind). It inherits the view set, the part list, and the kind-fixed values, then declares everything the kind left open.

Every attribute on either sheet carries a **binding level** (a transforming character adds character-fixed between these; see Forms and transformations):

- **kind-fixed** - shared by every member; the individual sheet references it and leaves it as the kind states it.
- **individual-fixed** - this character's own canon; the audit holds it in every image.
- **variable** - permitted to change, with the rules of its variation declared: a mood-shifted skin tone, a seasonal coat, a power-state glow, the bulk of a pattern field. The declared rule keeps the variation auditable rather than accidental.

**Overrides are first-class.** A deliberate violation of the kind baseline (the wingless dragon, the albino of a colored kind, the machine with a heartbeat) is registered explicitly: the attribute, what the kind says, what this individual is instead, and why it matters. An override is automatically signature-grade, because breaking its kind distinguishes an individual more than anything else. It is also the hardest-audited entry on the sheet: generation engines pull constantly toward the kind's prior and quietly revert the override whenever the anchor weakens. Expect to fight for it in every image.

## Forms and transformations

Some characters change shape, and sometimes name, on a trigger: a moon, an item, a wound, a will. Fully independent sheets per form lose the fact that it is one character, and one flat sheet explodes when every form needs its own views, marks, and colors. The structure is a spine and its forms:

- **The spine** is the character's identity across forms. It holds three things:
  - the inner canon, with any per-form deltas declared (a form may shift the personality itself, and that shift is canon rather than drift);
  - the **form registry**, one row per form: form id, display name (name changes are managed here), the kind that form references (a human form and a beast form may reference different kinds), the trigger and transition rule, and what persists through the change (clothing may shred while a scar earned in one form appears in all);
  - the **cross-form invariants**: the recognition thread that makes every form readably the same character, bound at a new level, **character-fixed**, above form-fixed and below kind-fixed.

  A character with one form is the degenerate case: spine and form sheet are the same page.
- **Each form is a full sheet** of the ordinary format, in its own subfolder with its own images and packages, referencing the spine and its own kind. Stable form ids and the spine roster identify the forms; committed sidecar, image, and package hashes identify the exact evidence used by a render.

The linkage is executable rather than documentary. A substantive `formreg` row must be complete and point to a safe in-tree `sheet-data.json` (or its directory). That linked sheet must:

- repeat the row's semantic id in `field.form_id`;
- point back to the exact spine sidecar through `field.form_spine_path`;
- resolve and validate its own layout profile;
- pass current coverage rules.

The spine must declare at least one complete `character-fixed` cross-form invariant. `render-package.json.form_lineage` records the spine hash, canonical invariant hash, and every linked form's sidecar hash, profile hash, profile selection, view count, state panels, and coverage result. A registry never means "fit every form into this one board."

Audit follows the scopes: character-fixed invariants are counted in every image of every form, and form-fixed values are counted within their form. The characteristic failure needs its own check: **engines leak features across forms**, letting one form's coat, markings, or silhouette bleed into another. Anchor each form independently, audit for cross-contamination explicitly, and treat a transition scene as its own declared state with the transition rule as its contract. In a series, a form is a heavyweight state: the state continuity machinery carries which form is on screen, and the spine carries what stays fixed regardless.

## The identity ledger: fixed versus rule-governed

Before drawing anything, split the character's visual facts into two declared classes.

**Signature-fixed facts** are individually described and always audited:

- Signature marks, when the design declares them, are each anchored to a landmark: a tattoo, scar or damage site, birthmark or mole pattern, heterochromia, named pattern event, ear notch, or chipped plate. Inventing a mark merely to satisfy the sheet is a mistake. Declared marks record landmark relation, shape and path, laterality, counterpart, continuity, and visibility or occlusion rules.
- Per-part attributes: eye color, nail or claw state, skin, pad, or plating colors, regional hair or fur length and color, component state, repeated unit geometry, and any other domain-appropriate part fact.
- Fixed colors, coverings, outfits, equipment, carried or docked items, repairs, and modules. These rank with marks. Every fixed visual row states where it applies, what stays identical, and the only view, state, or physical occlusion conditions that may hide it. It recurs in every applicable panel where its subject is exposed.
- Proportions: height register, build register, and the part ratios that keep them, carried as load-bearing measurements.

**Rule-governed texture** is everything else in the pattern field: the bulk of the stripes, spots, freckles, prints, or panel seams. It is fixed only by rules (zones, counts, flow, symmetry), and the ledger explicitly declares that its concrete layout may vary between images. Declaring the permitted variance is part of the ledger rather than a concession; it is what makes the audit decidable.

**The part inventory.** Whatever the kind of body, its identity is carried by parts, and each part can go wrong on its own in five ways:

- how many there are;
- what colour they are;
- how large they are against their neighbours;
- where they sit (which side, and against which landmark);
- what about them is allowed to change.

An eyebrow marking, a horn, a wing membrane, a sensor housing, a digit, a scar, a stripe that crosses the eye: each gets a row with those five columns. The row says which of them are fixed and which are state (an ear that may turn but keeps its colour; a claw that may extend but keeps its count). Hair-like fur is a part in its own right. A crest, mane, ruff, tuft, or forelock has a length, a volume, and a direction; it is the anthropomorphic character's hairstyle, and it drifts from shot to shot exactly as hair does unless its row is named in the composition text of every close-up. The rows live in the sheet's parts and colours tables. The inventory is a checklist rather than a description: every returned image is walked against it for the parts in frame, beside the accepted views. A miss on one column is a defect even when the picture is otherwise good, because it reads as another character. Close-ups are where misses are found and most often made, since a close-up isolates the part from the body that would anchor it. A row that says "left" is read against the pose (which ear is uppermost when the figure lies on its right side), and a marking the composition source lacks stays missing after the rendering step.

## Building the sheet

The sheet's inventory follows a domain-neutral reference-sheet standard. A "complete view" means the whole declared individual or collective configuration, which may be something other than a body:

- **Views.** At least two complete canonical views that expose the declared topology, and as many more as the kind requires. A humanoid starter may use front, both lateral surfaces, and back; a serpent may need coiled, extended, dorsal, and ventral configurations; a swarm uses unit and formation views; a ship can require port, starboard, dorsal, ventral, internal, or deployed views. The profile owns the names and count. Four horizontal directions cover some kinds only, and a kind may need more. One exception: when the sheet's `views` table declares rows, those rows become the base view grid and replace the profile's authored canonical view set one-for-one, so a declared views table needs at least two rows of its own.
- **Close-ups.** One recognition-focal detail (face, sensor, emblem, core, pattern junction, or another declared landmark), one detail per signature mark, and one panel per declared identity-bearing part or component. A face, head, eye, hand, foot, or biological structure appears only when declared.
- **Part and component details.** Specialized profiles may offer anatomy-specific frames, but a frame is generated only when a matching `parts` row exists. The domain-neutral profile creates one detail frame per substantive `parts` row. Undeclared optional frames are omitted from the model-facing board rather than shown as invitations to invent anatomy.
- **Visual identity axes.** Axes are author-declared rows rather than a fixed list of humanoid concerns. A character may need silhouette or topology, surface or material language, habitual configuration, locomotion or formation language, signaling, worn assemblies, or entirely different axes. The blank editor starts with an empty axis list, and every substantive row is carried into the complete fill prompt with its binding scope.
- **Color key.** When exact color continuity matters, provide one flat solid swatch row for every declared identity-bearing region, component, material, signal, or other color target, with color codes. Skin, fur, a nose, a beak, claws, scales, paint, plating, cables, and lights are examples only; the inventory comes from the declared rows. When the production style uses stepped shading, base, shadow, and highlight values can be recorded separately. Leaving a row blank or marking it with a dash deliberately leaves that decision to the generation model; inventing a fixed palette merely to complete the sheet is forbidden.
- **Proportions.** A height indication against a stated measure, the build register, and the key ratios already carried as load-bearing measurements.
- **Text block.** Minimal identity facts only. Non-visual trivia stays off the sheet; it dilutes the reference and proves nothing.
- **Icon.** A crop of the primary recognition feature: head, emblem, sensor cluster, core, prow, pattern junction, or another declared focal landmark.
- **Base body and outfits.** The uncovered body, underlying chassis, unladen formation, or other base configuration is the identity reference. Every declared outfit, shell, covering, carried assembly, or equipment state repeats the profile's complete outfit view set; each additional row keeps its own set rather than collapsing into one generic variant image.
- **Items.** Each carried item drawn separately. Items reveal role, purpose, and taste, and the signature items also appear in the icon.
- **Communicated states and body language.** Declare however many visually distinct `expressions` and `bodylang` rows the character's emotional range requires, whatever the current scene list uses. A communicated state may use a face, gaze, ears, tail, light pattern, topology, formation, component spacing, or any other channel the kind declares. A body-language state may be a posture, gesture, orientation, deployment, or collective formation. The bundled profiles seed six expression rows and four body-language rows as authoring starters only; any count is valid, and every additional substantive row receives another panel.

  Derive the state set from the character layer, then check it against a broad emotion catalog rather than from memory. The pack's prompt vocabulary carries an `emotional-states` category spanning:

  - security and anxiety;
  - gratitude;
  - excitement and arousal;
  - curiosity;
  - composure and impatience;
  - confusion;
  - happiness;
  - relaxation and tension;
  - dignity and duty;
  - respect;
  - affection;
  - admiration;
  - yearning;
  - drive;
  - fear and courage;
  - regret;
  - satisfaction and its absence;
  - disgust;
  - shame;
  - contempt;
  - envy and jealousy;
  - guilt;
  - lethal intent;
  - gloating;
  - wistfulness;
  - expectation;
  - superiority and inferiority;
  - resentment;
  - suffering;
  - sorrow;
  - anger;
  - anguish;
  - resignation;
  - despair and hope;
  - hatred;
  - tenderness;
  - emptiness;
  - astonishment.

  Read that catalog, then declare the subset this individual can plausibly occupy across the whole story, including states unused by any planned shot. A useful working floor for a recurring dramatic character is roughly eight to twelve expression rows and four to six body-language rows, weighted toward the registers the inner canon says this character lives in; a background or single-register character needs fewer. Prefer states that read differently on this kind's channels: two rows that resolve to the same ears, brow, and mouth configuration are one row.

  Weight the set by intensity as well as by emotion. Most shots sit near the resting face, so a set made only of peak states leaves the faces scenes use unproven, and a returned shot is judged against the nearest declared row. Three bands cover the range:

  - the resting face and its plain variants along the channels a shot changes with emotion held neutral (gaze at the viewer, aside, down, up; eyes open, half-closed, closed; mouth closed, parted, open mid-speech; ears or the kind's other channels forward, aside, back);
  - the low-intensity departures this individual habitually makes; for example a closed-mouth smile, a flat displeasure with the brow down, one raised brow, narrowed eyes in thought, mild surprise with the brows up and the mouth closed, or a faint embarrassment;
  - the peak states from the catalog.

  Where one register recurs in the story, declare it as a ladder of two or three rungs (annoyed, angry, furious; amused, grinning, laughing) rather than one peak. The bands scale with the character. A deadpan or masked character is declared mostly in the first band, with small departures and rare or absent peaks; that restraint is the identity rather than a gap. Write every row as channel states, because an emotion word alone is drawn at its peak; a subtle row names the channels (light smile, half-closed eyes, closed mouth) and leaves the emotion word out.

  A starter catalogue for the first two bands follows, written as channel states so each row can be pasted into a tag prompt or rewritten as prose. The kind channel column is for ears, a tail, plating, an emissive state, or whatever the kind declares; a kind that declares none drops the column. Peak states come from the emotion catalog above.

  | Band | Row | Brow and eyes | Gaze | Mouth | Kind channel |
  |---|---|---|---|---|---|
  | plain | resting face | level | at viewer | closed | forward |
  | plain | resting, gaze aside | level | to the side | closed | forward |
  | plain | resting, gaze down | level | down | closed | forward |
  | plain | resting, gaze up | level | up | closed | forward |
  | plain | resting, eyes closed | closed | - | closed | forward |
  | plain | resting, half-lidded | half-closed | at viewer | closed | forward |
  | plain | speaking | level | at viewer | open, mid-word | forward |
  | plain | listening, lips parted | level | at viewer | parted | forward |
  | plain | attention caught | level | ahead | closed | one channel turned aside |
  | plain | resting, channel back | level | at viewer | closed | back |
  | low | faint smile | level | at viewer | light smile, closed | forward |
  | low | wry smile | level | aside | nervous smile, closed | back |
  | low | relieved | closed | - | light smile, closed | forward |
  | low | displeasure | furrowed, unamused | at viewer | closed, flat | forward |
  | low | exasperated | half-closed, unamused | at viewer | closed | down |
  | low | raised brow | one brow raised | at viewer | closed | forward |
  | low | confused | one brow raised, head tilt | at viewer | parted | forward |
  | low | pensive | narrowed | to the side | closed | forward |
  | low | suspicious glance | narrowed | sideways glance | closed | forward |
  | low | determined | furrowed, narrowed | ahead | closed | forward |
  | low | mild surprise | brows raised, wide | at viewer | closed | forward |
  | low | mild embarrassment | light blush | away | closed | forward |
  | low | agitation, low | furrowed, nervous | at viewer | parted | back |
  | low | agitation, high | furrowed, impatient | to the side | clenched teeth | back |
  | ladder | annoyed | narrowed | at viewer | closed | back |
  | ladder | glare | glare | at viewer | closed | forward |
  | low | sleepy | half-closed | down | closed | down |
  | low | yawn | closed | - | open wide | back |

  Cut the catalogue to the individual: a character whose inner canon excludes smiling keeps the smile rows out, and a character whose story lacks a morning keeps the sleep rows out.
- **Performance series.** Declare how the character moves in four tables, each row one panel:
  - `partstates` for one part in one configuration (the tail carried high, low, curled, or bristled);
  - `motion` for a body region at both ends of its reach with the limit it stays within;
  - `actions` for the complete figure mid-action in a named phase;
  - `gestures` for everyday habits with their props.

  A video model that receives only standing views guesses the motion; these panels are what it is given instead.
- **Top and underside.** The bundled profiles carry a top view and an underside view beside the turnaround; a sheet that declares its own `views` rows declares those two orientations there.
- **Where each part sits between animal and human.** An anthropomorphic character is a set of points on that line rather than one. The hands may be human with claws while the feet are animal paws, the legs digitigrade while the torso is human, the muzzle full while the eyes face forward. Declare the construction of every part where the choice exists (hands, feet, legs, muzzle, ears, tail, eyes) in words that name the construction itself. Examples: five fingers and an opposable thumb, a plantigrade foot with a heel, a digitigrade leg with a hock, a full muzzle, a flat face. The species word leaves it open. A part named with the animal's word is drawn as the animal's part; a hand tagged as a paw comes back as a paw, most surely in a close-up where nothing else says the character is upright. The slip is common and reads as a different character, so each part panel is compared with the declared construction and the accepted full-body views before it is accepted.
- **Laterality, counterparts, continuity, and visibility.** Every substantive `marks` row declares laterality, and every substantive `parts` row declares laterality or topology. An asymmetric or unilateral row also declares `counterpart_rule`: positive evidence on the feature side and explicit absence, intactness, or different evidence on the paired side. A deliberately unpaired topology (a value such as `single`, `unpaired`, `radial`, or `distributed`) names no opposite side and therefore demands no counterpart rule. Every fixed `marks`, `parts`, `items`, and `outfits` row declares both `continuity_rule` and `visibility_rule`; every fixed `colors` row declares `visibility_rule`. These rules carry the fixed-visual statement from The identity ledger: what remains identical, where the declaration applies, where its subject is exposed, and the only conditions that may hide it. They apply to biological, mechanical, collective, material, worn, carried, docked, and otherwise configured features alike. Comparison panels prove paired differences, while every fixed declaration remains global across all applicable views, expressions, and poses.

## Layout profiles: the agent designs the frames

The scaffold is drawn from a **layout profile**: a JSON file declaring the canvas, the header fields, and every panel with its slot id, panel code, reference role, output name, and, decisively, its `hint`. The hint is the complete drawing instruction printed into the panel footer and the model-fill prompt. Profiles are validated by `schemas/character-sheet-render-profile.schema.json`, which fixes the panel grammar (row heights, unique slot ids and panel codes, output names, fill policies) and leaves **the panel count and the panel set** open: rows and boxes are arbitrary.

**Deciding what frames a character needs is design work the agent performs from the character definition, not a menu choice.** The kind layer names the canonical view set; the identity ledger names the marks, parts, components, and ratios that need close-ups; the character layer names the poses, items, and communicated states worth panels. The agent may use the bundled domain-neutral `character-sheet-layout.general.json`, opt into the `humanoid` or `anthro` specializations, or author a character-specific profile JSON in the sheet folder. Bundled profiles are starting points rather than a closed menu.

**The profile this sheet uses is declared where the character is defined, not improvised at render time.** The editor exposes a `Layout profile` field (`field.sheet_layout_profile` in `sheet-data.json`); the agent writes the bundled id or the authored profile's path there. The renderer:

- resolves that field (paths relative to the sheet folder, the working directory, or the skill root; `--profile` overrides; blank falls back to the bundled domain-neutral `general` profile);
- records the resolved profile, its source, and the selection reason in `render-package.json`;
- fails with the list of bundled profile ids when the declaration fails to resolve.

`humanoid` and `anthro` are opt-in specializations that a species name alone leaves unselected.

**A still carries a state, not a motion.** A row that names a movement (a tail's slow sway, an ear rotating toward a sound, a body rising onto one elbow) asks a still for the one instant that reads as the whole. The instant that comes back reads as some other state instead: a raised tail, a symmetric head, a body already up or still down. Declare movements in the shot's motion text, and declare on the sheet only the states a still can prove. A range-of-motion row earns its panel only while both ends lack proof in another accepted panel. A state row earns its panel only when a planned shot or a recurring register uses it; a row whose state every story moment leaves unused is removed before anything is drawn. Two rows that would resolve to the same picture collapse into one, as under Building the sheet.

**Declared state rows complete the panel set at render time.** Each substantive `parts`, `marks`, `expressions`, `bodylang`, `partstates`, `motion`, `actions`, and `gestures` row receives a same-kind frame, and resolved panels of one kind form one labeled section of the board. Every substantive `outfits` row receives a complete clone of the selected profile's authored `outfit_turnaround` view group; a profile that lacks such a group applies its declared fallback outfit panel grammar. Table-bound panels bind through persistent `source_row_id`; `source_index` is only a positional profile-authoring convenience. Deleting or reordering one row therefore leaves every other row's accepted image labeled as before. Resolved panels take dedicated rows and preserve kind-appropriate shapes. The canvas grows to contain the complete declared inventory; the coordinate manifest is the harvester contract, rather than a fixed aspect or fixed panel total.

**Every fill-state panel must carry a complete instruction.** Image models are given the whole frame's contents rather than trusted to improvise them. A profile hint is therefore a full drawable sentence (view, scale, subject, the anatomy facts to show, and the presentation), and sheet context merges the declared data on top. Each panel `kind` is a generic grammar the profile author composes, with a fixed data source in `sheet-data.json`:

| Panel kind | Fills from | Use for |
| --- | --- | --- |
| `canonical_view` | the profile hint | any declared view: full body, upper body from any side, per-form views |
| `part_detail` | the `parts` table row named by `source_part` | claws or nails, wings, ears, joints - one panel per identity-bearing part |
| `mark_detail` | the `marks` row at persistent `source_row_id` | tattoos, scars, named pattern events - one panel per landmarked mark |
| `items` | the `items` table | carried items, each drawn separately |
| `expressions` | the character-specific expression field | an optional general communicated-state note |
| `expression_variant` | one `expressions` row at persistent `source_row_id` | declared expression or communicated-state variants, one panel per row |
| `pose_state` | one `bodylang` row at persistent `source_row_id` | declared poses and body-language states, one panel per row |
| `part_state` | one `partstates` row | one part in one declared configuration (a tail carried high, ears pinned), drawn from its identity panel |
| `range_of_motion` | one `motion` row | one body region at both extremes of its declared range, side by side, with its limit |
| `action_pose` | one `actions` row | the complete figure mid-action in the declared phase |
| `idle_gesture` | one `gestures` row | the complete figure in a declared everyday habit, with its prop when declared |
| `outfit` | the dressed/equipped description and declared `outfits` rows | the canonical covering, shell, carried assembly, or equipment state over the readable base configuration |
| `outfit_turnaround` | one `outfits` row at persistent `source_row_id` | the profile-declared complete view group, repeated for every outfit/equipment state |
| `outfit_variant` | one `outfits` row at persistent `source_row_id` | fallback for a profile that intentionally declares a single-view outfit grammar |
| `signature_pose` | the signature-poses field | the habitual stance or gesture |
| `head_study` / `icon` | the profile hint | the face study and the recognition crop |
| `palette` | the `colors` table | the renderer-owned color key |

Before the fill prompt is written, the renderer checks the plan and refuses to render when any fill-state panel would end up with an empty effective hint. An undeclared source is left alone: an automatic optional panel is omitted, and an explicit `skip` stays visible as protected `LEAVE BLANK`. An authored panel may be bound to a row the sheet lacks: a nonexistent row id, another table's row, or a `source_part` matching none of the parts rows. It then falls back to an unbound default rather than borrowing another row's data; the substitution is reported in `coverage_warnings` of `render-package.json`.

A row has two kinds of column:

- The drawing columns (`attribute`, `description`, `specification`, `shape_path`, `configuration`, `range`) say what the picture shows; they reach the model-facing hint and the character anchors.
- The rule columns (`continuity_rule`, `visibility_rule`, `counterpart_rule`, `role_rule`, `must_prove`, `limit`) say how a returned panel is judged; they reach each request's `review` field and the coverage audit. They stay out of every prompt, because a model draws every word it is given, and a rule about what must stay fixed is unpaintable.

A candidate is judged against the accepted panels as well as the declaration. A declaration names a feature in words (digitigrade legs, five digits, a sleeveless top, a white side stripe); the first accepted panel that shows it fixes its construction in pixels, and every later panel showing it is compared with that one, because two constructions of one feature are two characters. Drift enters one panel at a time. Each candidate looks right beside its own prompt; only the row of accepted panels shows the foot flattened, the digit count changed, a mark gained on the garment, or the ear's rim lost. Before accepting, put the candidate beside the accepted panels that show the same features and check each fixed construction. When it differs, redraw it, or, if the new construction serves the sheet better, revise the declaration and redraw the earlier panels; keeping both is the one forbidden outcome. Keep a short list of the constructions acceptance has settled (which panel fixed the foot, the hand, each garment, the tail's colour split) and read it before every review. Acceptance may revise a declaration: when the accepted panels agree on a feature the sheet declares differently, and the drawn form still serves the sheet, change the declaration before the next panels are written. A detail the panels disagree on is settled by the outfit or part detail panel and carried as a reference from then on.

A garment or carried item shown by itself is drawn from the dressed panel rather than from words alone. Declare one `evidence` row per garment against its `outfits` row, stating how the garment is presented (alone on one hanger, laid flat, one pair standing on the ground) and the direction it is seen from; the combined outfit detail panel may then be skipped. A text-only request to a tag checkpoint returns the garment worn, a wearer the text never named, or a neighbouring garment, because its prior for a garment is a figure wearing it. Produce the panel instead on a surface that accepts a reference image. Give it the accepted dressed view of this individual as the only reference, plus prose that puts one garment alone in the frame; the prose presents it as the row states, seen from one named direction, filling the frame. The reference supplies cut, colour, and drawing style; the text supplies the composition and every surface that must read a particular way. A surface the text leaves undescribed is filled by the model, usually with a patch, a second stripe, or lettering. So either name the plain surface (a plain chest, one stripe per side, an unlettered band) or accept the drawn detail and revise the outfit declaration to it. One request draws one garment; a request for a set returns the set drawn as one garment.

Raster text and model instructions are separate contracts. The PNG receives a short, complete `caption`; the selected panel prompt or confirmed masked-sheet prompt and `sheet-layout.json` retain the complete `hint`. Headers, titles, profile facts, palette entries, and captions are printed in full rather than shortened with an ellipsis: the renderer reduces type within the declared minimum, then fails if the complete text still overflows. Text outside the Latin script is printed with platform fonts, and each run of text uses the first installed font that has every glyph it needs. A character that no installed font can print stops the render and is named in the error, so the sheet never shows a replacement box.

**The design is audited against the character definition before anything renders.** The audit requires:

- at least two canonical views: the profile's authored set, or the sheet's declared view rows when a declared views table replaces them;
- a recognition-focal detail;
- a palette whenever colors are declared;
- an expression/state panel only when expression behavior is declared;
- coverage for declared items and parts.

Every ordinary gap is named. A deliberate omission requires exactly one substantive line in `field.sheet_coverage_exceptions` per reported gap; `render-package.json` records explicit gap-to-justification pairs, so one generic sentence covers exactly one gap. Structural errors, which coverage prose leaves in place:

- missing laterality or topology;
- a missing asymmetric counterpart rule;
- a fixed visual lacking its required continuity or visibility rule;
- an inadequate canonical topology floor.

The audit also asks the scope question beyond the automated checks: does this state set cover the character's range, or only the scenes already planned? Name the registers the inner canon claims and confirm each has a panel that proves it; "the current episode does not need it" fails as a justification.

**Process.** Treat these as different artifacts with different authority:

- the editable page;
- the model-fill scaffold;
- the model output;
- the accepted slot images;
- the downstream reference board.

The panel is the unit. Each accepted slot image is a full-size model result whose long side is the profile's `panel_long_side` (2048 by default, or the box's own `long_side`). The board shows a reduced copy and is a viewing artifact; later generation consumes the full-size images.

1. **Author.** For a new folder, run `python scripts/character_sheet.py init SHEET_DIR` to create the current [blank sidecar contract](../../templates/character-sheet-data.blank.json). Its one empty row per table exposes the current column names while leaving row count, anatomy, and category inventory undeclared. Use `--profile general`, `--profile humanoid`, `--profile anthro`, or an authored profile path only when the choice is already justified. Form stable identity from the user's brief and write or revise `sheet-data.json` directly; [the sidecar schema](../../schemas/character-sheet-data.schema.json) defines its safe JSON envelope. Describe stable identity rather than a production scene. The two Model-fill brief fields are printed into the scaffold, so the raster carries the visible design brief and sheet finish. Set each image panel to `Auto`, `Generate / replace`, `Keep accepted image`, or `Skip / leave blank`. Decide the panel set here too, and declare it in `field.sheet_layout_profile` (see the start of this section). `templates/character-sheet.template.html` is optional, for human review or manual correction of the imported sidecar only; it stays the same for every character, and its page layout is separate from the PNG.
2. **Render the handoff.** Run `scripts/render_character_sheet.py SHEET_DIR --mode scaffold --out SHEET_DIR/model-fill`. The safe default `panel-images` transport creates:
   - the renderer-owned `sheet-render.png`;
   - white-editable/black-protected `sheet-edit-mask.png`;
   - coordinate-bearing `sheet-layout.json`;
   - hash-bearing `render-package.json`;
   - `panel-fill-requests.json`;
   - one exact artwork-only prompt per editable panel under `panel-fill-prompts/`.

   Those files are the handoff; the HTML is kept away from the image model and from rasterization.
3. **Fill through the declared transport.** Under `panel-images`, keep the full sheet away from the image model. Each request's `target.generation_w` by `target.generation_h` is the image size to ask for; the prompt states it, and the box on the board only shows a reduced copy. A target that returns only fixed sizes is given them at render time with `--panel-geometries WxH,WxH,...`; each request then asks for the geometry nearest its panel's aspect, and the set is recorded in `panel-fill-requests.json` and `render-package.json`. Generate the declared identity anchor first, review and accept it as the temporary identity reference for this fill run, then generate later requests with every `required_accepted_reference_results` image attached. Save one artwork-only PNG at the requested size under each request's `result_file`, and run `scripts/compose_sheet_panel_fills.py` to place reduced copies of only those pixels into the pristine scaffold for viewing. The exact request prompts carry the complete form registry, cross-form invariants, overrides, fixed or variable binding semantics, topology rules, and every fixed visual declaration. Every fixed feature remains global, as The identity ledger states; a dedicated detail panel is evidence, and the feature exists in every applicable panel besides.
4. **Use masked full-sheet editing only with evidence of capability.** `--fill-transport masked-sheet --confirm-pixel-edit-mask` is valid only when the exact active interface applies `sheet-edit-mask.png` as a pixel edit mask. A model that merely accepts the scaffold and mask as reference images is maskless for this purpose. Lacking that capability, stop or use `panel-images`; the whole sheet is never handed to a model for redrawing.
5. **Harvest candidates from a masked-sheet edit only.** The harvester serves the `masked-sheet` transport, where the model returns the whole board and the panel pixels are cut out of it. Run `scripts/harvest_sheet_render.py` with `--update-sidecar` left off. It verifies scaffold aspect ratio and compares every renderer-owned protected region against `sheet-render.png` and `sheet-edit-mask.png` before writing any crop; an output that moved panels, repainted labels or borders, or changed profile facts or the color key is rejected even with a matching aspect ratio. Only panels whose effective state was `fill` are cropped; footer, labels, profile facts, color key, kept panels, and skipped panels stay on the board. The crops are candidates only. Under `panel-images` the candidates are the result files themselves; harvesting the composed board would replace a full-size result with a crop of its reduced copy.
6. **Review and accept.** Inspect every candidate crop against every fixed visual row's continuity and visibility rules (Laterality, counterparts, continuity, and visibility under Building the sheet). After explicit owner acceptance, bind the accepted slots: under `panel-images`, rerun `scripts/compose_sheet_panel_fills.py` with `--update-sidecar` and `--only` for the accepted slots, which points each slot at its full-size result file; under `masked-sheet`, rerun the harvester with `--only` and `--update-sidecar`. Either can record a Generation Package with `--generation-package`. Acceptance is the owner's explicit decision; output quality, file presence, and a previous render imply nothing.
7. **Render the reusable board.** Run the renderer with `--mode reference`. It composes reduced copies of the accepted images and fixed color rows under pristine renderer-owned labels, for people; the accepted slot images keep their full size beside it. It also writes `reference-bundle.json`, listing every accepted slot image with its kind, role, binding, section, size, and hash, whatever the board scope shows. The default `--reference-scope all` shows every accepted panel; `identity` narrows the board to `reference_role=identity` panels other than those with `binding=variable`.
8. **Consume downstream.** Attach the accepted slot images themselves as evidence for the exact individual, choosing from `reference-bundle.json` the panels the shot needs within the target's reference-image limit: identity panels for who it is, performance panels for how it moves. The board is attached only where a target reads a contact sheet better than separate images. The scene prompt remains authoritative for pose, expression, action, camera, crop, environment, lighting, wardrobe state, injury, dirt, wetness, and every other transient condition. A new scene reuses the sheet rather than regenerating or refilling it.

**Fill-policy semantics.**

- `auto` preserves an accepted slot image and fills required panels and any source-declared identity, support, pose, or expression panel; undeclared optional panels are omitted.
- `fill` forces a new candidate only for a panel whose persistent source still exists.
- `keep` requires and protects an accepted `image_path`; a deleted source row leaves its obsolete panel beyond keeping or regeneration.
- `skip` explicitly excludes a declared panel: a gray `LEAVE BLANK` panel, a black mask region, and zero harvest crops.

The reference board includes only fixed identity-role evidence; performance panels may be filled as acting evidence, and the default board excludes them.

**Multiple views.** Use one masked full-sheet edit only when the engine applies the pixel edit mask and preserves the exact canvas; otherwise follow step 3 (identity anchor first, then the staged `panel-images` requests, each at its requested generation size). Repair identity-bearing details with grafting or low-strength fusion rather than repeatedly rerolling accepted panels.

**Editor readiness.** The optional editor has three identity/provenance readiness states:

- `DRAFT` lacks a meaningful Name or Species / Domain.
- `IDENTITY READY` has those identity selectors and can be rendered as a scaffold.
- `REFERENCE READY` additionally has the canonical image and its Generation Package path.

Per-slot `fill_policy` decides which image panels the model fills; readiness leaves that untouched. Editable fields round-trip through non-executable `sheet-data.json`, whose canonical table rows use `values`. The layout profile is declared and resolved as described at the start of this section.

## Registering the sheet

Commit the character as a canonical record with the selected sheet linked as its visual evidence, through the pack's record and asset machinery. The record carries the identity ledger; the sheet carries the map. Canonical status lives outside the document: registration confers it, and the registered content hashes carry it. A copy of the sheet is harmless, because identical bytes are the same canon; an edited copy identifies itself, because its bytes have stopped matching the registered hash. A signature or approval field on the sheet would add nothing, so it carries none. From registration onward the character is catalog-discoverable, and the visual-reference activation path arms for it exactly as for collected reference works.

## Provenance and consumption

Every image on the sheet is a generated artifact, and only an image whose generation can be reproduced qualifies as canon material. The sheet is therefore a folder rather than a file:

- One folder per character: `sheet-data.json`, accepted slot images under stable names, their matching Generation Packages, model-fill runs, candidate crops, and the rendered reference board. Every populated image slot identifies its matching Generation Package (for example, front.png with front.package.json). The package commits the request, negative transport, model, parameters, seed when available, and references; it enables request replay and audit, though probabilistic providers may return different bytes on regeneration. Empty optional image slots leave identity readiness intact.
- Editable fields round-trip through the non-executable `sheet-data.json` sidecar. Stable semantic field, row, and slot IDs make the sidecar independent of DOM position. `scripts/character_sheet.py` validates the sidecar and can bind image and package hashes before registration. The optional HTML is a manual data view; the rendered reference board is the visual human view; the JSON sidecar and packages are the machine interface.

Consumption runs in two lanes:

- **The human lane.** Open the rendered reference board for visual identity, and the optional editor only when the structured identity ledger needs inspection or correction. Together they brief a collaborator or commissioned artist.
- **The machine lane.** Validate and hash-bind `sheet-data.json`, then register the character as described under Registering the sheet. Catalog search can then find the character, and reference activation can use the registered images as role-scoped identity sources. A matching Generation Package permits replay of the committed request for repair or new-view derivation, under the same provider caveat.

## Character reference sheet

The reference sheet is the small set of images every later shot draws from. Build it before the shots rather than alongside them.

Procedure:

1. Settle the canonical appearance first: face markings, build, and the outfit this run uses.
2. Generate one image per framing in the table below, one character per image.
3. Hold the same conditions across the whole set: plain background, even frontal light, arms at the sides, with props, a second character, and action all left out. The model returns its best work under these conditions, and every shot that uses a reference inherits the quality of that reference.
4. Write each reference prompt to state what its own image will show: the markings, the build, and the clothing, each in words.
5. Register the finished set as the character's reference sheet before any shot prompt is written.
6. For each shot, choose its reference images from the sheet first, then write the prompt for the images that shot has.

A reference image records only what its framing shows, so the set covers the distances the shots need:

| Framing | What it records |
|---|---|
| close-up of the head | face markings, brow marks, eye color, ear interiors |
| knee-up (cowboy shot) | build and clothing at the distance most shots use |
| full body | proportions, stance, leg and foot construction, tail length and set |
| back view | what no front view records; needed as soon as the character turns |

Rules:

- Reference prompt and reference image state the same things. Where they agree, a later shot can rely on either; where they disagree, the model resolves the conflict differently in every generation.
- Permanent identity and explicitly fixed wardrobe are different from scene clothing, which belongs to the shot rather than to a replacement identity sheet. On interfaces that need outfit evidence, add a bounded outfit-only reference while the identity slots stay as they are. Inspect for source-clothing leakage rather than assuming a reference is perfectly separable.
- An explicitly approved canonical change invalidates the affected identity bindings. Regenerate only affected slots and their dependents, retain unaffected evidence, and block generation that uses stale bindings. Ordinary scene outfit changes leave identity slots valid.
- Repair a canonical change across the whole set at once rather than one shot at a time: each edit to a shot's reference selection removes an input some other shot depended on. The symptom is a set of shots degrading with the cause spread across several edits, which reads as bad luck rather than as the rule being broken.
- Decide a shot's reference images before writing its text. An interface that accepts three reference images supports one character well; two characters in frame divide the same limit, which is why two-character shots drift more than solo shots.

## Using the sheet downstream

- **Reference-capable engines:** use the sheet only for the identity authority registered on the character record: this individual, these stable proportions, marks, colors, and other declared identity-fixed facts. A composed sheet render can carry that identity in one reference slot when it is a registered artifact. Pose, camera, outfit, environment, lighting, props, local color, or finish may come from separately selected evidence only through the existing [Visual Reference Activation and Transport](../visual-reference-activation-and-transport.md) role map. Build one Reference Use Plan and one Prepared Reference Set; do not invent a second "sheet plus evidence" transport format. Input order and visual similarity leave a source's authority unchanged. Until a local reference board is registered, the supplied-file-only preparation path stays separate from pack-artifact references in the canonical package: register the identity first, or keep the request in one provenance path.
- **Checkpoint workflows:** the sheet is the seed and graft source. Identity locking, head and part grafts, and the repose workflow's face stage all pull from the sheet rather than from an arbitrary earlier output, which keeps drift from compounding across a chain of images.
- **Instruction-edit engines:** the preserve clauses enumerate the sheet's signature marks by their landmark descriptions.
- **Audit:** every production image is compared against the sheet. A signature-fixed deviation fails; rule-governed variation passes; the identity ledger makes the verdict mechanical. Review the character layer separately against its conditional rules, current context and permitted range; that semantic review is beyond what identity hashes or a fixed pose lookup can settle. A deliberate exception needs its own scope and basis.
- **Training:** when the character graduates to a trained adapter, the sheet and its approved derivatives seed the dataset.

## Maintaining the canon

Design changes are deliberate replacements:

- revise the identity ledger and the sheet together;
- commit the new content and artifact hashes;
- record its lineage or supersession at the registry boundary that owns that history;
- re-link the record.

Revision history lives at that registry boundary rather than in a counter on the mutable sheet. Production images redefine the character only through the sheet: a deviation worth keeping is promoted into the sheet first.

## Editor interaction contract

Use the HTML only when a person needs to inspect or correct the JSON. The editor must retain native form controls in every visible data cell, add exactly one row per Add activation, and remove only the selected row. Run [`scripts/character_sheet_editor_dom_smoke_test.py`](../../scripts/character_sheet_editor_dom_smoke_test.py) after changing its structure, then perform browser interaction checks before release.

## Non-anatomical reference coverage

A declared-structures identity authors its own `reference_views`, including complete cameras and coverage tokens. The planner leaves head, bust, expression and hand views out of this route. Choose views against actual identity landmarks rather than the historical character-shaped baseline. See [Declared Structures Runtime](declared-structures.md).

## Operational sequence from the skill entrypoint

Run the sheet workflow in this order; the numbered Process steps under Layout profiles carry the detail.

1. Add the character with `python scripts/studio.py character add <id>`; its sheet folder is `characters/<id>/sheet`. Form stable identity from the user's brief and write or revise `sheet-data.json` there; add `--profile` only when that choice is already justified. The command creates the current [blank sidecar contract](../../templates/character-sheet-data.blank.json); validate it against [the sidecar schema](../../schemas/character-sheet-data.schema.json).
2. Validate `sheet-data.json`. Each image slot carries a `fill_policy`: `auto`, `fill`, `keep`, or `skip`. Every fixed visual row (`marks`, `parts`, `items`, `outfits`, and fixed `colors`) declares enough continuity and applicability or visibility rules to make its recurrence decidable, with biological anatomy assumed for none of them; marks and parts add their spatial anchor or part, laterality or topology, and counterpart rule where applicable. The rules are stated under Laterality, counterparts, continuity, and visibility in Building the sheet. Use the optional HTML editor only for human review; its interaction checks are the Editor interaction contract in [Character Sheet Discipline](character-sheet-discipline.md).
3. Render `--mode scaffold` from the sidecar and selected layout profile (Process step 2). Under `panel-images`, each request in `panel-fill-requests.json` and `panel-fill-prompts/` names its image size in `target.generation_w` and `target.generation_h`; `sheet-render.png` is a renderer-owned composition base, and a maskless image model must never receive it.
4. Under `panel-images`, follow Process step 3: identity anchor first, then each request's `required_accepted_reference_results`, one artwork-only PNG at the requested size per declared `result_file`, and `scripts/compose_sheet_panel_fills.py` for viewing; the result files are the candidates. Garment-only evidence panels follow [Character Sheet Discipline](character-sheet-discipline.md) (the garment paragraph under Layout profiles). `--fill-transport masked-sheet --confirm-pixel-edit-mask` requires a real pixel edit mask on the exact active interface; a reference-image input falls short of that.
5. Under `masked-sheet` only, harvest the genuinely mask-edited image into a candidate directory with `--update-sidecar` left off (Process step 5). Candidate crops are review material rather than identity authority.
6. After explicit owner acceptance, use [Adoption Workflow](adoption-workflow.md) for Studio candidates: bind the full-size image and package, refresh selection, and record completion or resumption. Candidate-only acceptance leaves sheet and catalog unchanged. Non-Studio panel acceptance remains scoped through the composer or harvester; record provenance before promotion.
7. Render `--mode reference` after accepted slot images exist (Process step 7); `--reference-scope identity` narrows the board.
8. In later images, attach the accepted slot images the shot needs, in the identity role only; the scene prompt owns every transient condition (Process step 8).

Fill-policy semantics and the acceptance rule are stated under Layout profiles.
