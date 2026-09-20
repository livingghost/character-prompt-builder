# Morphology and species contracts

## 1. Purpose

This reference defines how Character Prompt Builder records species anatomy, individual anatomy, fictional body plans, expression channels, and shot-visible morphology without reducing a subject to a species name or a loose list of tags.

The system has three canonical layers:

1. `species-morphology-profile`: the valid anatomical and expressive possibility space for a species, lineage, chassis family, or original creature class.
2. `individual-morphology-contract`: the exact realization for one recurring character or one identifiable animal, creature, hybrid, robot, or android.
3. `resolved-morphology`: the shot-specific visible result after current form, state, crop, pose, clothing, occlusion, damage, and expression are applied.

A species noun is not a complete morphology contract. A familiar noun may help retrieval, but every production-critical count, attachment, shape, dimension, surface, motion range, and expression carrier must be declared or explicitly left unresolved.

## 2. Ownership and precedence

Use the following precedence order:

1. Explicit user statement.
2. Approved species or lineage profile.
3. Approved individual morphology contract.
4. Approved current state and form events.
5. Shot-specific resolved morphology.
6. Retrieval heuristics and model priors.

A lower source never silently changes a higher source. A model prior cannot add undeclared wings, tails, eyes, digits, tentacles, horns, sensors, masks, or internal organs. A reference image cannot override an explicit user species label without a disclosed correction request.

## 3. Species profile scope

A species profile may describe:

- a real biological species;
- an ordinary animal body plan;
- an anthropomorphic realization of a real animal family;
- a fictional species;
- a custom hybrid lineage;
- a creature class with no natural taxonomy;
- a robot chassis family;
- an android platform;
- an energy, fluid, modular, colonial, or distributed organism;
- a transformation form whose topology differs from the baseline form.

`reality_status` records whether the profile is real, fictional, custom, hybrid, mechanical, or otherwise authored. `taxonomy_or_origin` may use biological taxonomy, design ancestry, engineering lineage, mythic influence, or a direct original-construction statement. A fictional species does not need a real-world taxonomic substitute.

## 4. Complete feature inventory

The species profile inventories every production-relevant feature. For each feature, record at least:

- feature ID and feature kind;
- feature group or organ system;
- presence or explicit absence;
- typical, minimum, and maximum count;
- laterality or radial distribution;
- attachment site and parent features;
- attachment landmarks and branching sequence;
- length, width, thickness, spacing, and body ratio;
- measurement basis and permitted tolerance;
- shape, taper, curvature, orientation, and resting configuration;
- color, pattern, texture, material, and surface response;
- articulation and range of motion;
- functional role;
- expression or communication role;
- life-stage, dimorphic, seasonal, metamorphic, and shedding behavior;
- individual variation axes;
- cross-feature dependencies;
- continuity rules;
- views required to prove the feature;
- source confidence and unresolved questions.

Review absences only when they are meaningful user anchors or resolve an actual ambiguity. `inventory_completeness.explicitly_absent_or_inapplicable` records those explicit negative declarations; an unlisted organ is not automatically absent. The specialized inventories below are non-exhaustive prompts for applicable structures, not a universal checklist.

## 5. Body regions and topology

The body plan defines the region graph before detail is added. Each region has:

- a stable region ID;
- a parent region or root status;
- named landmarks;
- bilateral, radial, distributed, or centerline behavior;
- continuity rules.

Examples include head, sensory crown, neck, thorax, abdomen, pelvis, limb girdle, wing root, tail base, tentacle ring, chassis core, faceplate, and detachable tool mount.

Topology follows the authored attachment graph. A correct color cannot compensate for attaching a declared structure to a different carrier. Familiar anatomical examples are errors only when they contradict the approved profile, not because they depart from typical anatomy.

## 6. Counts and instance identity

Counts must be explicit.

Examples:

- two arms and two legs;
- four eyes in two vertical pairs;
- one primary tail and two shorter balance tails;
- six radial tentacles around a central mouth;
- no external ears;
- variable horn count from two to four under a declared polymorphism;
- one detachable sensor mast that may be temporarily absent from a scene but remains part of the individual contract.

For recurring subjects, each repeated or asymmetric feature receives stable instance IDs when necessary, such as `eye-left-upper`, `tail-secondary-right`, or `wing-dorsal-02`. Damage, markings, accessories, and state changes attach to the instance rather than to a vague feature class.

## 7. Limbs, hands, feet, digits, claws, and terminal structures

For a design that declares these structures, record each system independently and select only applicable details:

- count and bilateral or radial arrangement;
- upper and lower segment proportions;
- joint order and range;
- muscle, fur, scale, plate, or material distribution;
- hand, paw, hoof, fin, manipulator, or tool-interface class;
- digit count per limb;
- digit ordering, opposability, webbing, pads, claws, nails, talons, suction cups, or terminal plates;
- whether terminal structures retract, fold, detach, glow, or change under state;
- contact and load-bearing behavior.

Human nails, canine claws, feline retractable claws, avian talons, hoof walls, robotic fingertip plates, and tentacle suction cups are distinct terminal systems. Do not average them into a generic hand.

## 8. Head and sensory cluster

Only when the design declares such a cluster, record the applicable structures. The following examples are neither mandatory organs nor mandatory absence declarations:

- eyes or optical sensors;
- eyelids, shutters, nictitating membranes, pupils, apertures, or lenses;
- nose, nostrils, olfactory pits, antennae, whiskers, or chemical sensors;
- mouth, muzzle, beak, mandibles, proboscis, feeding aperture, or speaker grille;
- teeth, fangs, tusks, plates, tongue, inner mouth, or feeding tools;
- ears, auditory membranes, antennae, sonar structures, or integrated microphones;
- horns, antlers, crests, mane, cheek ruff, facial plates, and face masks.

Near-species diagnosis must prioritize structural evidence. For example, large feline and canine faces should be compared by muzzle reach and depth, muzzle shadow, ear-tip geometry, nose thickness and projection, cheek volume, and jaw shape. Coat color or generic triangular ears are insufficient.

## 9. Tails, wings, fins, tentacles, and special appendages

For every appendage, declare:

- presence and exact count;
- attachment region and base spacing;
- segment count or branching pattern;
- length, width, thickness, taper, and tip shape;
- surface and underside differences;
- resting pose and full motion range;
- load-bearing, balance, flight, swimming, grasping, display, defense, sensory, or reproductive function;
- expression role;
- clothing, harness, armor, chair, and crop clearance;
- required views that prove attachment and count.

A tail is not fully defined by color and length. The contract must state where it grows, how thick the base is, how it tapers, whether it is prehensile, how it bends, and which emotional motions are normal for the species and individual.

## 10. Skin, fur, scales, feathers, shells, and materials

Surface systems are region maps, not color names. Record:

- regions covered;
- material or integument class;
- base color logic;
- marking topology and boundary shape;
- directional growth or plate order;
- length, density, thickness, relief, and edge behavior;
- wetness, sweat, oil, reflection, subsurface, and rim-light response;
- damage, shedding, molting, rust, cracking, repair, and regeneration behavior;
- seams between surface systems.

An individual surface map resolves exact markings, scars, tattoos, notches, discoloration, worn paint, repaired panels, and asymmetries. Scene lighting may change perceived value but does not move a marking to another body region.

## 11. Special organs and capabilities

Fictional and mechanical subjects may have organs or systems not covered by ordinary anatomy. Use feature kinds such as:

- gill or respiratory organ;
- luminous organ;
- energy structure;
- fluid organ;
- shell or carapace;
- pouch;
- sensor array;
- tool interface;
- mask or faceplate;
- integrated display;
- detachable module;
- regenerative or metamorphic organ.

Each capability points to the feature carriers that physically enable it. Flight requires declared wings, control surfaces, body mass logic, and an attachment system. Bioluminescent communication requires declared luminous regions, controllable color or pulse dimensions, and readable states. A capability is invalid if its carrier features are absent.

## 12. Expression and communication grammar

Species expression is a coordinated system, not a universal human-face overlay. Record every channel the species can use:

- gaze, lids, pupils, shutters, or optic brightness;
- brows, supraorbital plates, crest angle, or faceplate movement;
- mouth, jaw, tongue, beak, mandibles, or speaker output;
- cheek color, skin flush, chromatophores, fur lift, feather spread, scale sheen, or panel light;
- ears, antennae, whiskers, horns, mane, ruff, hackles, fins, wings, tails, tentacles, or posture;
- breath, heat, scent, fluid, vibration, sound, servo cadence, fan speed, or electrical pulse;
- hands, paws, feet, manipulators, tools, signs, badges, screens, or cultural props.

For each channel, record neutral state, active configurations, controllable dimensions, timing, meanings, ambiguity, and cross-channel coordination. A single cue does not prove one emotion. Red cheeks may indicate embarrassment, attraction, exertion, heat, illness, anger, alcohol, or reflected light. Meaning is selected from the coordinated cue bundle and scene context.

Expression tools may be biological, mechanical, worn, held, cultural, assistive, or profession-specific. Examples include a robot visor, color-changing collar, sign board, handheld fan, scent dispenser, ritual mask, or communication tablet. The species profile declares the possible tool relationship. The individual contract declares the exact tool realization.

When the active packs provide curated cue records in category `body-language-cue`, retrieve the cues that match the channels and the requested emotion instead of re-deriving the appendage grammar, and adopt their invariants and `misreadings_to_avoid` as review knowledge. Lineage-level anatomy knowledge may likewise exist as curated `creature-anatomy` module records; retrieve them by lineage name and treat their prompts and invariants as generic species-neutral anatomy grammar, always subordinate to the Character Identity Contract and the species profile.

## 13. Individual morphology contract

The individual contract resolves one subject from the species possibility space. It records:

- life stage, sex or role morph, and active baseline form;
- overall scale and proportions;
- exact feature count and stable instance IDs;
- exact measurements and tolerances;
- exact attachment offsets and angles;
- individual colors, markings, scars, tattoos, notches, missing segments, repairs, prosthetics, and modifications;
- exact hair, grooming, nail, claw, horn, feather, panel, and surface treatment;
- individual expression habits and timing;
- individual communication tools;
- stable asymmetries;
- identity-priority features;
- approved variation fields;
- mutable state paths;
- unresolved features and their permitted treatment;
- differences from similar individuals.

Do not copy every species feature into prose. Store one feature realization per production-relevant species feature and preserve the reference to the species definition. The individual record states what is different, exact, damaged, selected, or personally characteristic.

## 14. Identity versus state

Use this boundary:

- species invariant: valid for the species or lineage;
- individual identity: stable for this subject across ordinary scenes;
- form identity: stable while one approved form is active;
- state: changes with events, time, environment, injury, emotion, grooming, clothing, or equipment;
- shot projection: visible in this shot after crop and occlusion.

Examples:

- one tail at the posterior pelvis: species and individual morphology;
- dark tail tip pattern: individual morphology;
- tail temporarily bandaged: state;
- tail outside a waist-up crop: shot projection;
- tail cut off by an approved event: state change that may later require a revised individual or form contract after canon review.

Unknown information remains unknown. Do not convert an occluded feature into an absence or invent an exact shape that the source does not support.

## 15. Near-species and near-individual differentials

Each species profile may contain structured comparisons with commonly confused species. Each individual contract may contain comparisons with similar individuals.

A useful differential names:

- shared traits;
- diagnostic differences;
- reliable views;
- misleading views or lighting;
- common model errors;
- constructive correction guidance.

Examples include feline versus canine face scaffolds, wolf versus fox ear and muzzle proportions, leopard versus jaguar rosette topology, bird wing versus draconic membrane attachment, tentacle versus tail articulation, organic eye versus display lens, and two characters with similar coat color but different markings and asymmetry.

## 16. Fictional species workflow

When the user introduces a species that has no established taxonomy:

1. Preserve the supplied name as the canonical species or lineage name.
2. Mark the reality status and origin as original, fictional, hybrid, mechanical, or other declared class.
3. Build the region map and body topology before styling.
4. Inventory all visible and production-relevant features.
5. Record important absences.
6. Declare feature counts and attachments.
7. Declare materials and surfaces.
8. Declare locomotion, manipulation, feeding, sensing, communication, and expression systems.
9. Declare developmental, polymorphic, and form-change rules.
10. Declare near-species or near-design differentials when confusion is plausible.
11. Resolve one individual contract without silently turning optional species variation into this character's identity.
12. Generate coverage requirements that prove count, attachment, front, profile, rear, underside, and special-organ behavior.

The system does not require a real animal label. Direct geometry and topology are authoritative.

## 17. Resolved morphology for a shot

`resolved-morphology` combines the approved species profile, individual contract, current state, and shot request. It contains:

- active form;
- body plan;
- visible feature instances;
- hidden or out-of-frame feature references;
- resolved feature relationships;
- surface and marking map;
- active expression channels and tool states;
- identity invariants;
- current state deltas;
- inventory proof for count and attachment;
- visible obligations;
- crop and occlusion requirements;
- unresolved uncertainties.

Every visible feature must exist in the individual contract. Hidden features remain declared rather than disappearing from the body plan. A crop may omit a leg, tail, wing, or antenna from the image, but the prompt and review contract must prevent the generator from interpreting the crop as anatomical absence or truncation.

## 18. Coverage planning

A reference bundle proves the actual identity-bearing topology, connections, local geometry, surface continuity, and any state-dependent structure needed by later images. Choose enough authored views to establish those properties. A head, left/right pair, front/rear axis, underside, or expressive organ is not presumed.

Identities provide explicit `reference_views`, coverage tokens and camera contracts. Conventional front, rear, profile or detail views remain useful options when the design calls for them, not universal baselines. One view may suffice for a simple declaration; complex or occluded structure can require several. See [Declared Structures Runtime](runtime/declared-structures.md).

## 19. Which authority settles what

Species profiles describe shared morphology; individual contracts declare one
subject's structures; identity contracts bind persistent appearance; events and
snapshots describe approved changes at a time and place; scene and camera records
specify what is shown. These are scopes of data authority, not application roles.
Record each decision with its evidence and approval.

Resolve morphology against the chosen local identity, form, state and scene.
Record species, individual, identity and snapshot hashes by character together
with visible morphology feature references. Scene context, camera and projection
commitments identify this particular view. Cropping never edits the underlying
body. A state event changes anatomy only through an approved mutable path or
explicit form or identity revision.

A supplied public record is optional evidence. Validate its artifact type, content,
lineage and relevant declared features before choosing it, regardless of who wrote
it. A file hash settles which record was used; it does not confer approval or
fetch the media that the record mentions.

## 20. Review checklist

Before approving a species or individual contract, confirm:

- every reconstruction-critical declared region has been considered;
- meaningful absences are explicit without inventing an organ checklist;
- feature counts are explicit;
- repeated features have stable instance IDs when needed;
- attachments are named by landmark;
- measurements use declared references;
- surfaces and markings have stable region paths;
- expression channels fit the body plan;
- external expression tools are declared;
- life stage and polymorphism do not silently change identity;
- state boundaries are clear;
- near-species differences are diagnostic rather than color-based;
- fictional capabilities have physical carriers;
- coverage views can prove the anatomy;
- unresolved information remains unresolved;
- the shot projection carries only approved visible changes.

## 21. Public exchange and local ownership

The [public contract](../protocols/contract-manifest.json) fixes artifact meaning
and transitive schema dependencies. Private presets, retrieval state, art direction,
production runs and adoption records remain local. The public boundary accepts
explicit artifacts and declarations, never software installation paths.

Use [Protocol Exchange](protocol-exchange.md) for a schema-bound artifact bundle,
or a declared interchange profile when feature negotiation is needed. Both sending
and receiving are explicit operations. A capability hash identifies a declaration;
it does not identify an application, locate a producer, or grant file access.

```bash
python scripts/protocol_exchange.py check-installed
python scripts/validate_integration.py
python scripts/public_boundary_smoke_test.py
```

The asset and canon owners make their own explicit adoption decisions after local
review. Receiving and validating a bundle cannot modify those records.

## 22. Frame character, per-part measurement, and accessory geometry

Body build, muscularity, body weight, frame mass, surface character, and soft-tissue padding are separate axes. Terms such as powerful, heavyweight, broad, or masculine must not fill an undeclared facial skeleton with a generic chiseled prior.

A `frame-character` contract declares `overall_form` and an ID-keyed `structures` map, plus coherence, diagnostic notes and provenance. A face, bone, soft tissue or muscle is never required. Detailed shape and material construction belongs in the relevant structure's geometry properties. See [Declared Structures Runtime](runtime/declared-structures.md).

Species profiles own a default and any allowed individual variants. Individual morphology contracts own the character realization. Resolved morphology copies the active frame character into every shot. A temporary state event does not rewrite frame mass or surface character unless an approved form or morphology contract permits it.

Recurring identities also store `load_bearing_part_measurements`. A one-off brief performs the same lightweight measurement pass in the Production Specification. Record count, length, width, thickness, spacing, diameter, angle, offset, coverage, color, or surface only when the dimension is identity-bearing, pose-bearing, or required for reliable reconstruction. Prefer landmark-relative relations such as muzzle length against head depth, tag width against nose width, hoop diameter against ear height, or buckle span against palm width.

Accessory names are not sufficient. `accessory-geometry` records count, site, support, fastening, orientation, relative dimensions, repeated-element scale, construction, material, color, layer order, body and garment clearance, contact response, mobility, visibility, continuity, and diagnostic misreadings.
