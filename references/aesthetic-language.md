# Aesthetic Language Architecture

This document defines how Character Prompt Builder stores and applies visual taste across humans, anthropomorphic animals, ordinary animals, creatures, hybrids, and robots.

The first aesthetic dataset was extracted from the reference images supplied during development. Those references were rich in anthropomorphic character art, so they contributed valuable knowledge about silhouette, performance, body mass, graphic surface grouping, clothing tension, viewer relationship, and illustrated lighting. The architecture does not treat those references as the boundary of the skill. It separates cross-domain visual judgment from domain-specific realization so future human, animal, creature, hybrid, and robot material can extend the system cleanly.

Source characters, signatures, logos, text, franchise identifiers, and one-off decoration are not preserved. The library stores reusable visual production knowledge for original work.

## Art direction already contains aesthetic judgment

Aesthetic judgment is not an optional stage added after an otherwise complete direction. An art direction is incomplete until it establishes:

- the image's center of appeal
- the subject's relationship to the viewer, another subject, or the environment
- composition, depth, silhouette, and focal hierarchy
- one medium family
- shape rhythm and proportion emphasis
- surface and tactile character
- color and lighting logic
- detail and finish hierarchy

The preset library supports those decisions after the direction exists. It does not create an aesthetic direction by itself.

## Four-layer production-knowledge architecture

### 1. Universal aesthetic core

Catalog source:

```text
enabled aesthetic-core records
```

A universal aesthetic core stores recurring cross-domain visual judgment. It can describe such appeal structures as:

- heroic physical presence
- gentle giant warmth
- tailored commanding presence
- summer athletic radiance
- neon-night tension
- graphic poster impact
- viewer-close confidence
- dynamic magic spectacle

A core may guide:

- center of appeal
- silhouette and proportion strategy
- performance strategy
- viewer relationship
- composition and focal hierarchy
- shape rhythm
- surface and tactile taste at a domain-neutral level
- color and light taste
- finish and detail hierarchy

A core does **not** define fur, skin, hair, feathers, scales, paws, muzzles, human facial anatomy, robot panels, optics, locomotion, or any other domain implementation. Canonical cores use `domains: ["shared"]` and remain valid across materially different subject types.

The selected art direction remains authoritative. Use zero or one core only when its full production knowledge strengthens the chosen direction. A core is never a mandatory style label and several cores are not averaged together.

### 2. Concrete style family

Catalog source:

```text
enabled style-family records
```

A concrete style family is the bridge between a broad rendering medium and subject realization. It stores one indivisible finish language: outer-to-inner line hierarchy, form abstraction, hard and soft value behavior, highlight placement, color logic, surface grouping, background treatment, detail hierarchy, and a realization overlay for every supported subject domain.

Select zero or one family after the art direction is chosen. The family is the primary positive drawing grammar. Its `base_render_profile_id` identifies the compatible medium envelope and scoped negative boundary. Do not concatenate the complete family grammar with the complete rendering-profile grammar.

The current curated families are:

- bold flat expressive cartoon
- fantasy line-and-wash character sheet
- graphic cinematic cel illustration
- matte character-design illustration
- neon screenprint character poster
- distressed editorial campaign cel
- polished soft-cel character portrait
- sculpted rounded luminous soft cel
- clean rounded flat cel
- ornate arcane splash illustration
- clean expressive casual webcomic
- regal blue nocturne character key visual
- luminous festival waterscape soft cel
- commercial athletic action cel
- smoldering nocturne painterly portrait
- electric workstation cutout soft cel
- graphic accent cutout action cel
- quiet seasonal veranda soft cel
- gilded cyan-sigil gothic cel
- hard-specular gloss cel

Aesthetic-touch modules may refine one local decision only when the selected family's `touch_policy` remains satisfied. The evidence method is defined in the [Reference-Derived Style-Family Evidence Contract](maintenance/presets.md#reference-derived-style-family-evidence-contract); concrete family notes belong to `cpb-resource:reference-derived-style-families` resolved from the explicitly selected provider. When image references are supported, `style_reference_guidance` assigns the reference to line, form, shadow, color, surface, and finish language while the brief retains authority over identity and scene.

### 3. Domain realization

Catalog source:

```text
enabled domain-realization records
```

A domain realization translates the art direction and any selected core into valid construction for the actual subject type.

The canonical subject domains are:

```text
human
anthropomorphic-animal
animal
creature
hybrid
robot
```

A realization may define:

- identity and silhouette channels
- anatomy, body plan, weight, and locomotion
- facial, postural, optical, or behavioral performance channels
- surface and material systems
- gesture, manipulation, and environmental contact
- domain-appropriate viewer relationship
- translation rules for appeal, shape, performance, color, surface, and detail

Examples:

- A human realization translates viewer-close confidence through eye contact, head angle, brows, eyelids, jaw, hair silhouette, shoulders, hands, clothing, and skin rendering.
- An anthropomorphic realization translates it through eyes, brows or equivalents, ears, muzzle or beak corners, head pitch, paws or hands, torso orientation, tail, markings, fur or species surface, and clothing.
- An ordinary-animal realization preserves species anatomy and natural behavior, using head direction, ears, body tension, locomotion, distance, timing, and environment instead of imposing human gesture.
- A robot realization uses head or sensor orientation, optic behavior, faceplate angle, articulation, panel hierarchy, manipulators, stance, emissive accents, casing materials, and mechanical contact.

Use the baseline domain realization matching the subject unless a more specific curated realization offers relevant production knowledge. A scene with materially different subject domains may use one realization for each represented domain. Baseline versus specialized is a record-level realization tier, never a content-pack boundary.

### 4. Rendering profile

Catalog source:

```text
enabled profile records
```

A rendering profile defines the mechanics of one medium:

- linework
- shape language
- value structure
- color behavior
- surface rendering
- light response
- background policy
- detail hierarchy
- medium-drift boundaries

Examples include clean anime cel illustration, flat cartoon, cinematic soft-cel art, concept-sheet rendering, painterly illustration, photography, and 3D character rendering.

A rendering profile does not determine the subject's appeal or anatomy. Select at most one compatible profile. A mixed medium is a separate art direction rather than the average of several profiles.

## Atomic aesthetic touches

Catalog source:

```text
enabled module records in category aesthetic-touch
```

Aesthetic-touch modules store one reusable craft decision. Some are shared, such as controlled soft-cel transitions or identity-first detail hierarchy. Others are domain-specific, such as:

- human face, hair, skin, and hand hierarchy
- natural-animal behavior and locomotion
- creature body-plan and appendage-junction clarity
- hybrid transition maps
- robot panel hierarchy, articulation, optics, and emissive separation
- anthropomorphic fur grouping and species-performance channels

An atomic touch is not a miniature aesthetic core. It solves one construction or finish question inside the chosen direction.

## Runtime combination

The intended order is:

```text
user brief
→ image intent
→ complete art direction
→ optional universal aesthetic core
→ optional concrete style family
→ matching domain realization and family overlay
→ linked or directly selected rendering profile
→ relevant atomic modules and corrections
→ final prompt
```

The art direction is complete before retrieval. Retrieval contributes production knowledge; it does not choose the image's purpose.

The `inspire` command returns these families separately:

```json
{
  "aesthetic_cores": [],
  "style_families": [],
  "domain_realizations": [],
  "render_profiles": [],
  "categories": {}
}
```

Inspect every selected record in full:

```bash
python scripts/catalog_cli.py inspect <record-id>
```

## How future reference material extends the system

When new images or other visual material are supplied, first complete `reference-corpus-visual-technique-observation.md`. Inventory the whole image before deciding what recurs: line behavior, stable proportions, camera geometry, head and eye direction, light-source arrangement, rendered shadow and highlight grammar, material response, temporary state, support, contact, depth, crop, and focal order.

Keep four boundaries explicit. Stable anatomy is not camera foreshortening. Physical light geometry is not the same thing as a style's shadow and highlight treatment. A hidden eye does not establish visible pupil direction, even when muzzle, head, ears, or posture imply a viewer relationship. Sweat, blush, wetness, damage, and colored light remain scene-visible state unless repeated evidence or the user promotes them into stable identity.

Only after that observation pass should the material be classified by the smallest reusable production function.

### Add or revise a universal core when

- the same appeal logic recurs across materially different subject domains or can be stated without domain anatomy
- the recurring knowledge concerns viewer relationship, hierarchy, proportion emphasis, color-light taste, shape rhythm, tactility, or finish
- the idea remains useful across multiple scenes and media

A core must be rewritten into domain-neutral visual language. It must not carry anatomy or materials merely because the source examples shared them.

### Add or revise a concrete style family when

- line, form, shadow, highlight, color, surface, background, and detail repeatedly operate as one recognizable finish language
- splitting those decisions into independent touches would permit incoherent combinations
- the same family can be translated through explicit overlays for every supported subject domain
- the family has a compatible medium envelope and clear boundaries

### Add or revise a domain realization when

- the material reveals how one subject domain expresses appeal, emotion, action, weight, or contact
- the knowledge concerns anatomy, body plan, locomotion, expressive channels, surface systems, manipulation, or environmental interaction
- the same translation applies across several art directions

Specialized realizations may extend the baseline domain record, for example human fashion portrait realization, avian ordinary-animal realization, hard-surface robot realization, quadrupedal creature realization, or soft mascot realization.

### Add an aesthetic-touch module when

- one isolated craft decision is independently reusable
- the decision has a clear visual function, adaptation invariants, and nearby misreadings
- the complete system does not require a new core or realization

### Add a rendering profile when

- the recurring knowledge is medium mechanics
- line, value, surface, light, background, and detail operate as one coherent grammar
- the profile remains independent of a particular identity or scene

### Add a scene when

- the reusable knowledge is staging: body geometry, support, contact, gaze, depth, crop, and focal order

## Coverage and honesty

The architecture is broad; the depth of knowledge varies by domain. The original reference set gives anthropomorphic character art unusually strong coverage. Human, ordinary-animal, creature, hybrid, and robot domains have explicit baseline realizations and domain-specific atomic touches, but future curated material should continue to deepen them.

Do not claim equal artistic coverage merely because every domain has a record. Coverage should be evaluated by whether the library provides concrete, reusable production knowledge for diverse briefs and whether generated prompts and images improve in comparison with unaided art direction.

## Style grammar and material identity

A style family or rendering profile defines **how** a surface is drawn: line economy, value grouping, highlight budget, clump abstraction. It does not decide **what** each surface is. Fur length and dampness, guard hairs, pad construction, fabric weave, skin condition, and moisture come from the brief plus the `animal-surface`, `material`, `skin-detail`, and `effect` atomic categories. Reading a family's `surface_system` as a material specification leaves the prompt without material identity; querying only staging categories leaves the same gap. Keep the two layers separate, and keep the total wording spent on material behavior proportional to the family's own guidance so a single family term such as smooth torso planes is reinforced by the material text around it (see Representation grammar in `references/runtime/prompt-composition.md`).

## Distinctive detail boundary

Distinctive details are documented separately in `references/distinctive-detail-specification.md`. They are identity-scale localized features, not a rendering style and not a complete surface system. The chosen style family determines how a scar, tattoo, notch, claw, wrinkle, or wear mark is drawn; the distinctive-detail record determines where it is, how large it is, what physical depth it has, and how it remains consistent.
