# Preset Authoring Standard

This standard governs canonical curated records. It defines what each record family stores, how much detail it retains, and how new reference material is converted into reusable production knowledge.

## General principles

### Production knowledge, not captions

A curated record must let an agent reconstruct or adapt the visual decision without seeing the source image.

A label such as `relaxed couch pose` is discovery text. A curated record also preserves support, contact, body geometry, depth order, crop, focal hierarchy, and adaptation invariants.

### Atomic does not mean vague

Atomic means one reusable visual decision. It does not mean a few keywords.

### Positive fields are affirmative

Prompt-facing fields describe what the image contains and how it is constructed. Nearby mistakes belong in diagnostic fields. Negative output follows `cpb-resource:negative-policy` resolved from the explicitly selected provider.

### Negative-source roles

The `cpb-resource:negative-policy` resource resolved from the explicitly selected provider defines the runtime sources:

- centralized generation hygiene
- feature-scoped limb, hand or paw, tail, clothing, and held-prop integrity
- the single selected rendering profile
- an activated correction for a concrete risk
- explicit user exclusions

Scene failure modes, atomic misreadings, and archetype presentation-freedom metadata remain diagnostic and are not automatically emitted.

### Audit boundary

The audit verifies the authoring contract. It does not prove artistic quality or guarantee model compliance. Actual prompt and image quality still require creative review and comparison against a no-skill baseline.

### Scope determines content

Every record contains only knowledge belonging to its family.

- cross-domain appeal → universal aesthetic core
- one domain's anatomy, behavior, and surfaces → domain realization
- medium mechanics → rendering profile
- one craft decision → atomic module
- staging → base scene
- stable identity → archetype
- repair → correction

### Preserve relationships

Do not summarize away:

- gaze target
- head-versus-eye direction
- body support and weight
- hand, paw, manipulator, mouth, or prop contact
- depth order
- crop and frame
- lighting geometry
- material construction
- silhouette requirements
- adaptation boundaries

### Preserve content-bearing evidence

Prompt knowledge is not an execution request. Preserve any visually or narratively load-bearing element supported by the source or brief, whatever its genre: everyday, dramatic, violent, medical, grotesque, disturbing, body-altering, intimate, adult, or otherwise sensitive content. When the source is user-supplied and the user requests preset extraction, author the supported content at full construction detail, recording whichever facts the genre makes load-bearing: limb and hand ownership, contact location and pressure direction, action phase, physiological response, garment or wound state, viewer or partner relationship, camera, crop, and content intensity whenever the evidence supports them. Sensitivity never licenses summary language such as vague intimacy, generic battle wear, or generic adult content when the production distinction is more specific. Editorial overlays contribute zero canonical knowledge; unseen fine measurements remain open rather than fabricated. Do not silently sanitize, euphemize, or delete that evidence because of its sensitivity. Do not invent detail that the source and brief do not support, applying the same general authoring rule regardless of content type. Keep local scene scope local, and keep downstream execution decisions separate from canonical authoring. Read `references/prompt-knowledge-boundary.md`.

## Shared metadata

Curated records include:

```text
id
label
curation_status: "curated"
record_role
```

They also include exact domains and family-specific tags. Record IDs are current canonical identifiers.

## Discovery projection

Every curated record must be discoverable without its exact label or ID. Discovery metadata may be authored on the canonical record or generated into its search profile. The derived cache projection must contain:

```text
aliases
outcome_summary
discovery_group
facets
anchor_signature
variant_of, when applicable
```

- `aliases` contains at least three natural canonical-English descriptions of the visible result or construction problem. They must not be copies of the ID or exact label with punctuation changed. They are catalog vocabulary, not translations of user-language briefs.
- `outcome_summary` says what visible image, construction, or treatment the record can help produce. It is not a category definition.
- `discovery_group` gathers records that represent one discoverable family.
- `variant_of` links a specialized member to its representative family when appropriate.
- `facets` scope evidence by meaning, such as species, body build, coat palette, head hair, mane, ruff, regional covering, camera, lighting, wardrobe, environment, style, expression, emotion, pose, activity, situation, relationship, theme, or content intensity.
- `anchor_signature` records stable identity constraints that recommendation must preserve.

Search associations are many-to-many. A general phrase may point to several records with facet, source, and weight evidence. Do not make one common word a hard redirect to one preset. Author `search_terms` and `search_profile` in the owning pack record; the disposable catalog cache derives its associations automatically and must not be edited as source.

Useful aliases describe the visible result, viewer relationship, camera treatment, intended use, or construction problem. For example, `shiny muscular animal close portrait` is more useful than repeating `Hard Specular Gloss Cel`.

### Search intent facets

Curated records should expose the meanings a user is likely to search for when those meanings are actually supported by the record. Use explicit `search_profile.facets` for cross-cutting intent such as:

```text
emotion
expression
pose
activity
situation
theme
relationship
viewer_relationship
role
environment
head_hair
hair_style
hair_texture
hair_color
facial_hair
mane
ruff
head_fur_placement
head_feature
content_intensity
```

A facet is discovery evidence, not a substitute for production detail. Do not infer jealousy from any side-eye, affection from any touch, or danger from any weapon. When one broad word can mean several things, preserve the broad alias but add the specific construction or situation that disambiguates it. Search coverage and maintenance examples are documented in `references/maintenance/search-discovery.md`.

## Atomic module

Required production fields:

```text
category
label
visual_function
prompt
invariants
misreadings_to_avoid
tags
domains
applies_to
```

The prompt is a complete visual instruction for one decision. Invariants define what survives adaptation. Misreadings are diagnostic-only.

Examples:

- human hand gesture clarity
- natural-animal weight transfer
- robot optic expression
- controlled soft-cel transition
- halberd forward foreshortening

## Universal aesthetic core

Canonical file:

```text
enabled aesthetic-core records
```

A core stores cross-domain visual judgment. Required fields:

```text
label
domains: ["shared"]
compatible_medium_families
aesthetic_promise
appeal_center
silhouette_and_proportion_strategy
performance_and_expression_strategy
viewer_relationship_strategy
composition_and_focal_strategy
shape_and_rhythm_strategy
surface_and_tactility_strategy
color_and_light_strategy
finish_and_detail_hierarchy
integration_prompt
domain_neutrality
variation_axes
best_for
avoid_for
tags
```

### Domain-neutrality requirement

A universal core must be expressible without assuming:

- human hair, skin, facial anatomy, or hands
- animal fur, feathers, scales, muzzle, beak, paws, hooves, ears, wings, or tail
- robot panels, chassis, optics, sensors, actuators, or manipulators
- creature-specific appendages or body plans

Use abstract but visual concepts such as identity zone, primary mass, active structures, material systems, surface grouping, focal relationship, viewer distance, and shape rhythm.

A core may mention materials in general, but implementation belongs to domain realization and rendering profile.

### When to author a core

Create or revise a core only when the same appeal system recurs across materially different scenes and remains useful across domains. A source collection dominated by one subject domain is evidence for a core only after domain-specific features are removed from the formulation.

## Concrete style family

Canonical file:

```text
enabled style-family records
```

A style family stores one indivisible concrete drawing grammar. It is more specific than a rendering profile and more integrated than a set of atomic touches. Required fields include:

```text
label
domains
medium_family
base_render_profile_id
compatible_render_profile_ids
style_promise
visual_signature
line_system
form_system
value_and_shadow_system
highlight_system
color_system
surface_system
background_system
detail_hierarchy
touch_policy
style_reference_guidance
domain_overlays
integration_prompt
negative_terms
variation_axes
best_for
avoid_for
tags
```

A curated family uses `domains: ["shared"]` and provides overlays for exactly these domains:

```text
human
anthropomorphic-animal
animal
creature
hybrid
robot
```

Every overlay defines identity and form, surface translation, performance translation, detail priority, and integration. The family remains the primary positive grammar. Its base rendering profile supplies the medium envelope and scoped negative boundary.

Do not split one family's line, value, highlight, and surface systems into freely recombinable tags. Atomic touches may modify a local decision only when the family touch policy remains satisfied.

### Style-family taxonomy gate

A concrete style family is accepted only when the same production grammar recurs across at least three materially different reference situations. Compare line, form, shadow and value, highlight, color, surface, background, and detail hierarchy. Six matching axes are the minimum structural threshold; strong evidence normally spans all eight. The situations should differ in scene, pose, wardrobe, environment, or relationship so repeated finish can be separated from repeated content.

Run four tests before adding or revising a family:

1. **Scene-leakage test**: remove species, body build, role, pose, camera, season, environment, temporary wetness, and source text. The remaining grammar must still describe a recognizable finish.
2. **Cross-scene transfer test**: apply the grammar to a materially different scene. Line, value, highlight, color, surface, and background behavior must remain coherent.
4. **Nearest-family boundary test**: name the closest existing family and state at least two visible rules that separate them.
5. **Decomposition test**: move relationship, support, clothing, camera, lighting geometry, and effects into scenes or modules whenever they remain independently reusable.

When new reference evidence reveals that an existing family is scene-bound, generalize it only through the lossless reviewed-merge gate instead of adding an unjustified near-duplicate. Update every internal reference and search profile in the same change. When the selected pack state provides `cpb-resource:style-family-taxonomy`, record the evidence and boundaries in the resource resolved from its explicitly selected provider; otherwise do not claim that resource-specific gate is complete. Validate a released pack through its exact one-pack `scripts/pack_release_gate.py` invocation. Use `scripts/style_family_audit.py` only as a focused development diagnostic with the same explicit pack runtime.

When the evidence is suggestive but does not meet the threshold, record the proposal in `deferred_candidates` with the available evidence, the exact evidence gap, and a reconsideration condition. Curate any independently reusable layout, effect, lighting, clothing, contact, or staging knowledge in its correct layer instead of promoting an under-evidenced family.

## Domain realization

Canonical file:

```text
enabled domain-realization records
```

Required fields:

```text
label
domains
subject_domain
realization_level
base_realization
realization_promise
identity_and_silhouette
performance_channels
anatomy_and_weight
surface_and_materials
viewer_relationship
motion_and_environment
translation_rules
integration_prompt
extension_points
best_for
avoid_for
tags
```

`domains` contains exactly one non-shared canonical domain and matches `subject_domain`.

Baseline domain-realization records use the schema's record-level tier:

```text
realization_level: "foundation"
base_realization: true
```

Required translation-rule keys:

```text
appeal_center
shape_and_rhythm
performance
surface
color_and_light
detail_hierarchy
```

### Purpose

A realization explains how a universal direction becomes valid for one subject domain. It must cover identity, anatomy or body plan, expressive channels, weight, locomotion, surface systems, manipulation, contact, and environmental interaction.

### Specialized realizations

Future material may justify specialized realizations, for example:

- human fashion portrait
- human action anatomy
- canine anthropomorphic short-fur physique
- avian ordinary-animal behavior
- quadrupedal creature locomotion
- hard-surface robot key art
- soft robot or mascot performance

A specialized realization extends the baseline domain record and keeps the same exact domain. This tier is never a content-pack boundary.

## Rendering profile

Required fields:

```text
label
medium_family
visual_intent
linework
shape_language
value_structure
color_logic
surface_policy
lighting_response
background_policy
detail_hierarchy
prompt
rendering
negative_terms
best_for
avoid_for
```

The rendering grammar is complete and independent of a particular identity or scene. Scene-specific failures, prop contact, furniture, or costume details do not belong in profile negatives.

## Base scene

A curated scene stores a reusable staging blueprint. Required content includes:

```text
image_promise
staging
must_preserve
adaptable_fields
specific_failure_modes
```

The staging should preserve, as applicable:

- subject count and roles
- body or structural geometry
- pose and action
- gaze and relationship
- support and weight
- contact geometry
- foreground, midground, and background order
- crop and frame
- focal hierarchy
- lighting geometry
- environment

Failure modes are diagnostic-only.

## Finished recipe

A recipe combines one full scene and one full rendering profile. It stores:

```text
base_scene_id
render_profile_id
complete scene blueprint snapshot
complete rendering grammar snapshot
adaptation rules
must_preserve
prompt_template
negative_terms
diagnostic_failure_modes
```

The prompt template uses affirmative scene and medium construction. Negative terms come from the rendering profile's medium boundary; scene failures remain diagnostic.

## Character archetype

An archetype stores identity across a series:

```text
identity_construction
identity_invariants
variable_fields
character_lock
do_not_lock
```

Stable morphology, palette, markings, proportions, surface system, and identity-defining equipment may be locked. One-off pose, camera, background, lighting, weather, and narrative events remain variable. Species, body build, color, occupation, clothing, or one scene alone do not establish an archetype. Apply the creation, merge, domain-separation, and growth rules in `archetype-governance.md`.

## Correction

A correction stores one repair:

```text
trigger
diagnosis
positive_correction
inspection_points
avoidance_terms
tags
```

The positive correction describes the repaired construction. Avoidance terms activate only when the correction is selected for a concrete risk.

## Vocabulary record

Vocabulary records are compact by design. They provide names and model-legible phrasing. They do not claim authoring-standard completeness and do not receive invented fields merely to resemble curated records.

## Converting new material into the catalog

When reference material is supplied, `reference-corpus-visual-technique-observation.md` is a required companion to this standard. Complete its whole-image inventory before naming a style, scene, or module. When visible emotion, social intent, viewer relationship, physiology, appendage behavior, or mechanical acting contributes to the image, also complete `performance-language-specification.md` before selecting the performance meaning.

### Required visual-technique observation pass

Record enough visible relationships that another agent can reconstruct the decision without the source image:

- image intent, center of appeal, focal order, overlap, depth, and crop
- line-weight hierarchy, contour rhythm, interior-line density, and material-specific marks
- stable head, torso, limb, hand, foot, and appendage proportions
- camera distance, height, pitch, yaw, roll, lens behavior, nearest form, and near-to-far scale change
- head direction, visible pupil direction, gaze target, and inferred viewer relationship under occlusion
- coordinated performance channels: lids, brows, mouth, tongue, blush, tears, breath, posture, hands, feet, distance, contact, ears, tail, whiskers, wings, sensors, optics, manipulators, indicators, actuators, and timing
- felt, displayed, and masked emotion; plausible interpretation candidates; and the context that selects the current reading
- key, fill, rim, bounce, and cast-shadow geometry
- value-group count, shadow-edge class, highlight size, highlight edge, gradient scope, and reserved glints
- material response, temporary wetness or damage, support points, prop contact, and complete action chains

Do not collapse base anatomy into foreshortening, lighting arrangement into rendering treatment, visible eye direction into inferred gaze, or temporary state into stable identity.

### Conversion sequence

1. Observe the complete image and identify its center of appeal.
2. Complete the required visual-technique inventory and state which evidence is visible versus inferred.
3. Complete the multi-channel performance observation when emotion, intent, relationship, physiology, appendage behavior, or mechanical acting contributes to the image. Record visible cues before interpretation, retain plausible alternate readings, and select the current reading from scene and relationship context.
4. Separate recurring knowledge from one-off identity, temporary state, source text, logos, signatures, exact insignia, decoration, and obvious editorial censorship devices. Treat mosaics, blur patches, opaque paint, stickers, bars, warning labels, and replacement shapes as source contamination. Preserve the underlying semantic content at the supported level and leave covered fine structure open.
5. Classify each reusable decision by function and preserve the required layer separations.
6. Compare complete existing records before adding a new ID. Prefer promoting a matching vocabulary record when the evidence completes its construction.
7. Author positive production knowledge manually, including geometry, hierarchy, and adaptation boundaries rather than a source caption.
8. Store nearby mistakes in diagnostic fields with non-automatic activation policies.
9. Add an outcome summary, at least three natural canonical-English search aliases, scoped facets, a discovery group, and a variant relationship when applicable. The aliases must distinguish the record rather than merely copy its label, and they must not form a per-language translation table. Include supported expression, emotion, body language, gaze, physiology, appendage or mechanical signals, pose, activity, situation, relationship, theme, and content-intensity facets so ordinary intent language can reach the record.
10. Confirm that ordinary short canonical-English descriptions can reach the record without an exact label, ID, category hint, or internal vocabulary. Preserve source-language briefs only at the agent or structured-query boundary.
11. For a style-family addition, merge, split, generalization, or rename, update the taxonomy evidence and every affected record reference in the same change.
12. Update reference-cluster mapping and provenance notes without distributing source imagery or source identity.
13. Add focused retrieval regression cases and sparse-discovery cases for modifier scope, anchor preservation, variant grouping, and materially different direction cards when artistic behavior changes.
14. Rebuild the generated many-to-many search index and all metadata, then run every required audit.

### Classification guide

```text
recurs across domains as appeal or visual taste
→ universal aesthetic core

implements appeal through one domain's anatomy, behavior, or materials
→ domain realization or domain-specific aesthetic-touch module

binds line, form, shadow, highlight, color, surface, background, detail hierarchy, and domain overlays as one specific finish
→ concrete style family

defines broader medium mechanics and drift boundaries without one specific finish identity
→ rendering profile

stages subjects and environment in reusable spatial relationships
→ base scene

solves one isolated craft question
→ atomic module

coordinates reusable meaning across several visible performance channels
→ body-language-cue module

holds identity stable across scenes
→ archetype

repairs one observed or strongly predicted failure
→ correction
```

## Review questions

Before accepting a curated record, ask:

- Can another agent use it without the source image?
- Does it contain only knowledge belonging to this family?
- Does it preserve relationships and adaptation invariants?
- Was stable body-part scale separated from perspective enlargement by camera proximity?
- Were camera distance, height, pitch, lens behavior, crop, nearest form, and depth order recorded where relevant?
- Were head direction, visible eye direction, gaze target, and inferred viewer relationship kept distinct?
- Was physical light geometry separated from the style's value, shadow-edge, highlight, and gradient grammar?
- Were material identity and stable surface construction separated from wetness, sweat, blush, dirt, injury, and other temporary state?
- Are support, contact, and root-to-endpoint action chains reconstructible?
- Are positive fields affirmative?
- Was any relevant sensitive knowledge of any genre silently removed, euphemized, or hidden from retrieval before the execution boundary?
- Are diagnostics scoped and non-automatic?
- Does it duplicate an existing record that should instead be promoted or enriched?
- Does its domain metadata match its actual language?
- For a universal core, is every positive field free of domain anatomy?
- For a style family, do all finish axes operate as one repeated system rather than a collection of subject, camera, or lighting similarities?
- For a realization, does it translate the art direction rather than create a style or scene?
- Have signatures, logos, copied text, exact insignia, and source-character identity been removed?
- Can an ordinary short description find the record without its exact label, ID, or category name?
- Does the outcome summary describe a visible result rather than restate the category?
- Do canonical-English aliases cover plausible descriptions of the result, and are color, material, camera, lighting, wardrobe, and environment terms assigned to the correct facets without duplicating translation logic?
- Are near-duplicate variants grouped rather than allowed to occupy the full result set?

## Required maintenance commands

After authoring is complete, rebuild the owning pack lock and run the complete
pack-owned release contract through an exact one-pack runtime:

```bash
python -B scripts/pack_cli.py build-lock <pack-dir>
python -B scripts/pack_release_gate.py <pack-dir> \
  --state-file <absolute-exact-pack-state.json> \
  --cache-dir <absolute-dedicated-cache-dir> \
  --managed-root <absolute-existing-managed-dir> \
  --report-out <absolute-report-path-outside-pack>
```

The state must contain exactly the positional pack directory, enable only that
pack UUID, and select it for every and only its named resource bindings. The
gate validates the released lock, exact derived cache, and every suite declared
by the owning pack; it does not borrow cases or expected IDs from core or
another pack. Run `python scripts/validate.py .` separately when core code or
the bundled default release also changes. Automated checks verify structural
conformance and known retrieval behavior. They do not replace human review of
artistic usefulness.


## Source-artifact exclusion

Reference cleanup precedes preset authoring. Discard clearly non-diegetic censor masks, opaque pasted shapes, mosaics, blur patches, bars, stickers, UI remnants, watermarks, logos, signatures, and meaningless source text. A canonical preset records the intended depicted image and never records that an editorial concealment occurred. The artifact does not become a prop, body feature, clothing layer, composition device, search facet, negative term, constraint, or diagnostic failure.

Preserve supported adult content and other sensitive content at its actual intensity. Use the selected subject contract or another supporting source for exact anatomy. Source cleanup removes the editing layer; it does not turn an explicit scene into a generic or sanitized one.

## Canonical medium-family vocabulary

`medium_family` (on every rendering profile, any tier) and `compatible_medium_families` (on aesthetic cores) share one closed vocabulary: 2D anime character illustration; cinematic 2D soft-cel anime illustration; flat 2D cartoon illustration; bold 2D comic and anime poster; 2D game character splash illustration; clean fantasy concept-sheet illustration; painterly illustration; photography / photorealism; 3D character rendering; monochrome ink and manga illustration; pixel art; scientific and technical illustration. The audit rejects values outside this set. Core-to-profile compatibility resolves through this vocabulary; never through free-text similarity.

## Subject scope on rendering profiles

A rendering profile is a shared medium grammar by default (`domains: ["shared"]`) and must then describe subject matter conditionally: fur, hair, scales, or plating are treated as materials when present, never assumed. A grammar that genuinely depends on one subject family declares it (for example `domains: ["anthropomorphic-animal"]`); the audit rejects subject-assumption words (anthro, kemono, furry) inside shared-scope profiles.

## Distinctive-detail module

A curated `distinctive-detail` module must preserve enough information to place and reconstruct one localized identity feature. Required structured fields are:

```text
feature_type
target_region
laterality
landmark_relation
count_or_distribution
relative_size
shape_and_path
orientation
color_and_value
depth_and_relief
edge_and_texture
surface_interaction
age_or_condition
visibility_and_occlusion
identity_priority
invariants
adaptation_limits
misreadings_to_avoid
```

Before authoring from images, use `references/reference-corpus-detail-observation.md` to separate stable identity evidence from expression, moisture, light, perspective, and style artifacts. Use subject-relative left and right. Express size against a local landmark rather than pixels. Separate physical depth from color, and separate broad surface or coat patterns from localized distinctive features. Positive prompt fields describe the visible target affirmatively; adaptation limits and misreadings remain diagnostic metadata.
## Reference attribute audit

Before authoring or calibrating any record against a reference image, build
an attribute ledger and keep it beside the work: the count of every discrete
element (earrings, chains, tags, straps), the anatomical left or right each
one belongs to, the stacking order of every overlap (which limb or layer
lies in front and which behind, stated from both sides), each element's size
anchored to a nearby landmark, and its color. Every spatial relation is
written from both sides: when the left forearm crosses in front, the record
also states that the right forearm passes behind. Expressions are audited as geometry too: the lid line and its corner tilt, the brow angle, height, and gap, the openness band, gaze target, mouth and tongue shape, jaw tension, cheek color, breath, head angle, shoulders, hands, feet, distance, contact, species appendages, and mechanical signals. A mood label alone flattens into an average face. Use `performance-language-specification.md` to separate observation, interpretation candidates, selected meaning, and prompt projection. Inherited draft values count for nothing
until the attribute ledger confirms them. The six geometry-annotated
expression records, challenging-smirk, calm-serious, warm-open-smile,
cold-detached, angry-snarl, and quiet-melancholy, are the authoring
models for writing any further mood.

## Prompt economy

Every sentence in a model-facing prompt is a vote, and patch accretion
weakens each one. The full grammar, the canonical-record preservation
boundary, the counter-text cut after a scaffold change, and the scoped
consolidation evidence live in `references/prompt-composition-geometry.md`
(sections 1 and 2); they apply verbatim when authoring the model-facing
prompt text inside records.

## Spatial relations take three codes

State every critical overlap in three codes at once: the side from both
directions, a unique visible marker on the front element, and occlusion
verbs. The full grammar and examples live in
`references/prompt-composition-geometry.md` (section 3); the reference
attribute audit above supplies the sides and markers.

## Distributions over instances

Write organic variety as a distribution: count, landmark-anchored size,
a local direction rule, irregularity, and spacing. The full grammar and
the mane-lobe example live in `references/prompt-composition-geometry.md`
(section 4).

## Camera moves as visible consequences

State a camera move as what the picture shows: magnitude, the lines that
change, and the subject geometry that stays put. The full grammar and
evidence live in `references/prompt-composition-geometry.md` (section 5).

## Species geometry duty

A species noun is a geometry vote: every mention re-summons that species'
default proportions from the generator's prior. Before writing a species
word into any face-bearing record (a species entry, a character archetype,
a style family overlay, a correction, or a scene's cast), verify the
reference's facial architecture against `references/species-architecture.md`:
the ear shape and set, the muzzle's reach against its depth, the nose's
proportions and position, and the jaw's mass. When a design's architecture and its nominal species disagree, preserve the user or Character Identity Contract species as the primary anchor. Use species-neutral geometry wording first. A different species noun enters only as an explicit disclosed modification approved for the task. Species records themselves stay minimal name tokens. When the selected pack state explicitly provides `cpb-resource:species-scaffold-map`, file a new species entry under its prompt scaffold family in both the architecture reference and that resolved resource. Without a selected provider, do not claim that the resource-specific authoring gate has been completed.

## Punctuation integrity

Canonical preset data and supporting prose use plain ASCII punctuation. The Unicode em dash is forbidden in packaged Skill content. Rewrite the sentence with a colon, semicolon, comma, parentheses, or a plain hyphen. The package validator scans every UTF-8 file and rejects the release when the character is present.
## Reference-derived structural contracts

A reference-derived scene records a camera-framing contract whenever shot scale, distance, crop, lens behavior, or body coverage is load-bearing. A reference-derived outfit records garment geometry whenever a generic garment name cannot reproduce openings, straps, panels, rise, inseam, leg openings, coverage, or pose response. Record identity-relevant growth through declared structures, locations and authored geometry. Independent coverings and projections remain separate. Detail examples never impose a part inventory on other subjects.

These records remain complete production knowledge. Do not summarize a deep armhole as `tank top`, a micro low-rise short as `shorts`, a measured crop as `close-up`, or a structured hairstyle as `short hair`.

## Frame character and measured accessory duty

When a source or brief distinguishes smooth padded structure from chiseled, ridged, gaunt, fine-boned, massive, or mechanical structure, author or select a frame-character record. Do not let body-build adjectives silently rewrite the face. Review cheeks, cheekbone visibility, jaw corner, facial plane transitions, joints, and body mass handoffs as one coherent structural system.

When a body part or accessory is load-bearing for identity or reconstruction, record a landmark-relative measurement. Accessory records must define geometry rather than naming the item only. Representative curated accessory records may coexist with compact vocabulary records, but a scene that depends on exact count, side, size, attachment, color, or layer order must use the curated geometry tier.

When source images are represented through SVG, follow `references/derived-visual-evidence.md`. The bundle contains a native-dimension source-derived perceptual full-color path projection that uses one uniform precision over the complete frame; it is not an exact source-raster archive. Do not embed or externally reference raster data, resize before conversion, simplify contours, delete small connected regions, or allocate vector precision by semantic importance. When a collection is ingested, follow `references/reference-corpus-ingestion.md`: exact duplicate inputs share one content-addressed evidence bundle, existing families are preferred over one-image preset growth, and excluded artifacts remain auditable without entering canonical character knowledge.
