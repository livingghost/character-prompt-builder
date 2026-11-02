# Performance Language Specification

Performance language connects a character's act or reaction with the emotion,
intent, attention, relationship and bodily state it communicates. It applies
to humans, anthropomorphic animals, ordinary animals, creatures, hybrids,
robots and androids. [Production direction](runtime/production-direction.md)
owns the selected depiction and any reconsideration of it. This specification
supplies knowledge about expressive channels, source observation and the
evidence needed to resolve a performance question.

A structured performance record connects relevant observations or selected
cues, their combined read, the interpretations still supported and the meaning
chosen for this image. It can preserve detailed evidence without turning every
observed channel into an instruction for the new depiction.

For person-specific authoring, first use [Character Performance](runtime/character-performance.md)
and [Authorial Intent](runtime/authorial-intent.md), then the applicable persona section 2 and its
response/contextual voice rules. Select cues under the creator's adopted portrayal aim, not merely
because an emotional reaction would be plausible. This document owns the visual
record, not a dialogue-mode schema. Speech/register changes and their triggers stay in persona and
scene realization; a visual record projects the chosen moment, not the full emotional trajectory.
Source-image analysis still records observations before interpreting them.

## 1. Why coordinated channels matter

A single cue rarely fixes one meaning.

- A tongue display may indicate play, exertion, heat relief, appetite, teasing, arousal, or a species-specific behavior.
- Red cheeks may indicate embarrassment, attraction, heat, exertion, illness, anger, alcohol, or reflected light.
- Half-lidded eyes may indicate relaxation, fatigue, confidence, contempt, intoxication, sensual interest, or emotional overwhelm.
- Crossed arms may indicate vigilance, authority, displeasure, comfort, cold, or simple resting posture.
- A tail flick may indicate irritation, concentration, play, excitement, balance, or species-specific motion.
- A blinking indicator may indicate attention, warning, uncertainty, overload, or ordinary machine status.

The selected meaning comes from the pattern: gaze target, eyelids, brows, mouth, head angle, posture, hands, feet, distance, contact, physiology, appendages, environment, relationship, and timing. Keep alternate readings when the visible evidence supports more than one.

For example, the festival shaved-ice scene combines a visible tongue, bilateral cheek blush, softened half-lidded eyes, a small forward head lean, relaxed ears and shoulders, sweat, direct viewer engagement, and cold dessert contact. Together they support playful flustered teasing. In an adult sensual brief, the same coordinated pattern can carry flirtatious or sensual subtext. The tongue or blush alone does not decide the interpretation.

## 2. Ownership and stability

Performance information can belong to different artifacts.

| Information | Owner |
|---|---|
| Creator portrayal aim, permitted contrast and deliberate departure | Scoped authorial intent entry in the design register, not a new performance JSON field |
| Character profile and signature dynamics | Applicable persona section 2, binding the creator aim to internal traits and expression |
| Individual behavioral baseline, conditional response and voice modes | Applicable persona PHYSICAL/THOUGHT/SPEECH/RELATIONSHIPS, bound to section 2 with world and phase scope |
| Adopted visual-production summary of mannerisms and declared available channels | Character Identity Contract `stable_identity.performance_vocabulary`; a bounded summary, not a competing persona |
| Current felt emotion, masked emotion, fatigue, arousal, pain, intoxication, or alert state | State Snapshot or Scene Context |
| The cues that must be visible from the current camera | Visual State Projection `performance_cues`, optional structured `performance_language`, and prompt fragments |
| The exact coordinated performance for one image | Production Specification `subjects[].performance` |
| Reusable multi-channel performance grammar | Enabled `module` records in category `body-language-cue` |
| One scene-specific performance with pose, props, support, and camera | Base scene `performance_language` plus staging |

A cue also records its stability:

- `identity-vocabulary`: a stable mannerism or channel preference
- `current-state`: a state that persists across part of the story
- `transient-action`: a momentary pose, glance, reaction, or gesture
- `environment-response`: heat, cold, wind, water, pain, exertion, or another environmental response

Repeated evidence and explicit user approval may establish a conditional mannerism or channel preference in stable performance vocabulary. That does not make the cue's current value permanent: blush, sweat, ear angle, tail motion, optic pulse, hand tension, and other transient cues still resolve from current state and scene conditions.

## 3. Structured record

Use [the schema](../protocols/shared-state/schemas/performance-language.schema.json) and [the template](../templates/performance-language-template.json) for structured records.

The record stores:

```text
felt_emotion
displayed_emotion
masked_or_conflicted_emotion
intent
viewer_or_partner_relationship
intensity
temporal_phase
channel_cues
interpretation_candidates
selected_interpretation
ambiguity_notes
prompt_projection
```

An ordinary depiction can express its performance in the prompt without a
separate structured record. Use this object when the construction question
needs the relationships among several cues, source observations, alternative
interpretations or continuity across a series. Its fields preserve that
reasoning and evidence; prompt projection carries the selected act or reaction
and the distinctions it needs.

### Channel cue fields

Each cue states:

```text
cue_id
channel
observation
visual_instruction
laterality
intensity
direction_or_target
visibility
evidence_status
confidence
stability
notes
```

`observation` records what the source or approved state shows.
`visual_instruction` records the selected visible behavior for this cue, using
geometry or material behavior where that distinction matters. They remain
separate because observed evidence can support several interpretations, while
the new depiction has its own selected performance and source authority.

## 4. Source observation questions

Use this repertoire when interpreting a source image, diagnosing a returned
performance or harvesting reference evidence. The question and the source's
assigned scope determine which observations matter. Read their relationships
before attributing emotion or intent. These observations describe evidence;
they are not a sequence of cues to add while authoring a prompt.

### 4.1 Target and relationship

Target and relationship evidence includes:

- who or what the subject watches
- whether the target is the viewer, another character, a prop, a threat, a task, or the environment
- social distance and body orientation toward or away from the target
- contact, interruption, pursuit, retreat, invitation, monitoring, or concealment

A side-eye has little meaning until its target and relationship are known.

### 4.2 Eyes, lids, brows, and optics

Eye, brow and optic evidence includes:

- visible pupil or optic direction
- upper and lower lid height
- inner and outer corner tilt
- brow angle, height, gap, and asymmetry
- aperture size, shutter position, or sensor focus for mechanical subjects
- tears, glaze, glow, flicker, focus change, or occlusion

Separate visible eye direction from inferred attention. A visor, brim, hair mass, shadow, or crop may conceal the eyes while head axis and posture still carry viewer relationship.

### 4.3 Mouth, jaw, tongue, beak, muzzle, and faceplate

Mouth and faceplate evidence includes:

- open or closed mouth band
- corner height and asymmetry
- lip, muzzle, beak, or faceplate tension
- jaw loading
- teeth or fang visibility
- tongue visibility, direction, and amount
- breath, drool, condensation, or vocal preparation

Describe a tongue display as geometry first. Select playfulness, exertion, appetite, teasing, arousal, or another meaning only after checking the other channels and context.

### 4.4 Cheeks, skin, fur, feathers, surface color, and physiology

Surface and physiological evidence includes:

- blush location, laterality, hue, edge, area, and intensity
- heat, cold, exertion, illness, anger, fear, arousal, or environmental color response
- sweat, tears, saliva, piloerection, hackles, feather lift, tremor, vibration, condensation, panel heat, or glow
- breathing depth and cadence

Distinguish localized physiological color from global lighting. Blush normally follows the face surface and remains local; reflected red light follows the light geometry and may affect nearby materials.

### 4.5 Head, neck, shoulders, spine, torso, and center of gravity

Posture and support evidence includes:

- head pitch, yaw, roll, and distance toward the target
- neck extension or withdrawal
- shoulder height and asymmetry
- chest opening or closure
- spine curve
- pelvis and center-of-gravity shift
- balance, support, readiness, collapse, or expansion

A forward head and shoulder lean can turn a smile into invitation, challenge, concern, or threat. A withdrawn torso can turn the same face into hesitation or restraint.

### 4.6 Arms, hands, paws, claws, manipulators, legs, and feet

Limb and manipulator evidence includes:

- open, closed, curled, clenched, gripping, braced, pointing, hiding, or self-touching hand shape
- finger or claw tension
- hand target and contact surface
- arm crossing and overlap order
- foot direction, stance width, knee bend, toe or paw pressure
- approach, retreat, freeze, bounce, crouch, step preparation, or weight transfer
- manipulator and actuator load for robots

A contrast between a composed face and tensed available channels can support an authored reading
of tension. It does not reliably reveal a hidden feeling or require every concealed state to leak.
Check the actual task, bodily constraints, individual rule and viewpoint before interpreting it.

### 4.7 Distance and contact

Distance and contact evidence includes:

- interpersonal distance
- contact point, pressure, support, and ownership
- whether touch is reciprocal, protective, restraining, clinical, playful, aggressive, affectionate, erotic, or task-driven
- approach or withdrawal direction

Do not infer relationship from touch alone. Contact geometry, gaze, body tension, and context select the meaning.

### 4.8 Rhythm and phase

A performance's timing can be described through:

- anticipation
- onset
- held state
- peak
- release
- aftermath

These phases are descriptive choices, not a mandatory progression. Channels can start and release
at different times, remain unchanged, stay concealed or retain residue. The end of a trigger does
not require instant recovery. Relate the current instant to adjacent scene beats where continuity
matters; one structured visual record does not serialize every transition or every spoken mode.

Motion rhythm, where supported, can be still, hesitant, pulsing, repeated,
sudden, heavy, buoyant, trembling, delayed or mechanically stepped. A still
presents one selected moment. Declared channels, displaced materials or staging
can imply duration without making the entire temporal sequence simultaneously
visible.

## 5. Declared channels and subject-specific interpretation

The following are discovery examples, not inherited anatomy, expressive meaning or required
coverage. Only declared structures and capabilities activate a channel. Preserve natural behavior
where the author asserts a natural organism; fictional or engineered departures need their own
scope. Missing, absent, unknown and occluded channels are different.

### Biological and anthropomorphic portrayals

Where present, usable channels may include eyes, lids, brows, mouth, muzzle or beak, jaw, breath,
head orientation, posture, appendage movement, contact and surface changes. Ears, tails, whiskers,
ruff, fins or wings are independent possibilities, not consequences of a species label. A channel
may be performing a task or environmental function rather than communicating an emotion.

Different channels need not agree or move simultaneously. One sensory structure can track a sound
while the person keeps another oriented toward a task. Determine the actual declared mechanics,
individual habits and relevant world/cultural conventions before assigning significance. Do not
force human speech or face grammar onto an ordinary animal or unfamiliar body plan.

### Mechanical, distributed and other portrayals

Where declared, signals can include focus, aperture, sensor orientation, manipulators, actuator
load, panel position, indicators, ventilation, vibration, sound, motion timing or distribution.
Retain functional constraints and clearance. A functional pause, status pulse or heat response is
not by itself evidence of curiosity, distress or any felt emotion. An authored personification can
supply a meaning with its scope; otherwise record the observable operation and its uncertainty.
Non-facial and non-vocal subjects do not need substitute human features to complete the record.

## 6. Interpretation discipline

When the question is how to interpret source evidence, connect each plausible
reading to its support:

1. name the meaning;
2. list the cue IDs that support it;
3. state the scene, relationship, domain, and intensity context required;
4. assign high, medium, or low confidence;
5. state content intensity, including adult sensual or erotic context when supported;
6. retain alternative readings that remain visually plausible.

The selected interpretation belongs to the current image intent. It does not erase the alternative readings from the canonical observation. A Visual State Projection may carry the complete structured record in its optional `performance_language` field and concise visible instructions in `performance_cues`; each field retains its declared meaning.

Sensitive content remains production knowledge when supported. Adult erotic or sensual interpretation may be recorded alongside non-erotic readings. The presence of blush, tongue, nudity, muscle emphasis, or close distance alone does not force an erotic interpretation, and sensitivity alone does not justify deleting one that the combined evidence supports. Read `prompt-knowledge-boundary.md`.

## 7. Search projection

Search facets are a discovery projection of the complete record. Useful keys include:

```text
emotion
expression
body_language
gaze
mouth_action
hand_action
leg_action
appendage_action
physiology
mechanical_signal
activity
situation
theme
relationship
viewer_relationship
performance_intent
content_intensity
interpretation
```

Use ordinary canonical-English aliases that describe the coordinated read. Keep cue-specific terms too, such as `flushed cheeks`, `half-lidded eyes`, `ears angled back`, `tail tip flick`, `hands gripping the hem`, `optic aperture narrowed`, or `ventilation pulse`.

## 8. Prompt projection

Author the act or reaction selected through
[Production direction](runtime/production-direction.md): what the participant
is doing or responding to, in which circumstances, and how that response
contributes to this depiction. Preserve the relationship between that act,
its intended emotional read and its degree. An ordinary complete action or
performance phrase can carry natural gaze, posture and expression without a
separate instruction for each channel.

Use channel knowledge when a fixed design, a consequential ambiguity or an
observed mismatch needs a more specific distinction. A gaze target can clarify
whom a response addresses; a held posture can distinguish restraint from an
interruption; local facial or material behavior can establish an expressly
requested cue. Choose the detail for that work. A position or measurement that
merely describes one imagined realization need not narrow the authored act.

Felt state, intended display, masking and timing remain separate decisions.
The selected channels can reinforce, contradict or lag each other, stay quiet,
or withhold a response. Coordinated performance means that their relationship
serves the chosen portrayal, including a requested ambiguity or contrast.
It does not require agreement among every signal. Use the individual's
declared channels, actual bodily or mechanical constraints and selected view.

The actual prompt and supplied media must establish the present circumstances
needed to understand the performance. A prior event can supply a necessary
premise for a reaction; retain that premise before a dependent cue. A source
record can hold fuller history and unselected interpretations. The model does
not share the authoring conversation. Readable supplied evidence carries its
assigned contribution, while text establishes the current act and any missing
context. Different participants or local views retain their own performance
scope.

For a portrayal whose selected construction depends on these cues, a detailed
realization could read:

```text
playful flustered teasing carried by a small tongue display, bilateral cheek blush,
softened half-lidded viewer-directed eyes, a slight forward head lean, relaxed ears,
and one stable cup-holding hand
```

A compact direction could instead read:

```text
playful and flirty
```

Neither form establishes its own suitability. The current act, context,
character and available source evidence determine whether the compact direction
already carries the result or a particular cue must be resolved. A small
multi-channel set, one channel, subtle stillness, intentional ambiguity or no
expressive display can each be appropriate. If the actual construction remains
underdetermined in a consequential way, return that question to Production
direction rather than expanding all channels or inventing anatomy.

Record a newly selected gesture, distance or expression in the current Visual
State Projection or Production Specification. Structured cues use the existing
stability values in section 2. Such a staging choice can be made within the
task's delegated scope and used in the current depiction; stable performance
vocabulary retains its evidence and adoption requirements. Lasting traits,
relationship changes and future outcomes continue to be authored at their
state owners. Keep that authoring decision separate from the performance
requested of the image. When uncertainty, concealment or multiple readings
are part of the selected portrayal, define the current cues and contextual
conditions that support them. An unresolved story decision can remain in the
story record while the present performance is clear.

When a returned image misses the requested read, compare the actual act or
reaction with the requested result under Production direction's repair process.
The cause can lie in the situation, relationship, chosen instant, source use or
a local cue. A local defect can be repaired by specifying its wanted state and
degree; a mistaken act or reaction requires rebuilding that construction.
Keep applicable exclusions as boundaries and assess the resulting performance
together, including its quiet, masked or ambiguous components.

## 9. Evidence for a performance judgment

[Production direction](runtime/production-direction.md#observe-and-repair)
owns the judgment against the requested result. Performance evidence helps
answer the particular question it identifies. A gaze target, body orientation,
distance or contact can distinguish an addressed response from another
activity. Their meaning depends on the task, context and individual; hidden
states need not leak visibly.

Where physiological or mechanical signals affect the interpretation, distinguish
local blush, sweat, tears, heat or glow from lighting and other environmental
causes. Declared channels retain their mechanics and relevant world conventions.
For a robot, expressive optics, sensors, manipulators, actuators, indicators,
panels or ventilation still need their functional clearance and operation.

Keep felt, intended, displayed and observer-inferred states distinct, with
uncertainty attached to the evidence that creates it. Continuity can depend on
an active voice or response mode and neighboring beats without requiring every
channel to reset together. Plausible source interpretations remain with their
observations; ambiguity requested of the output belongs to the selected
portrayal and its relationship, scene, state and content intensity.

Assess what the delivered prompt and media establish about the present act,
its circumstances, its degree and any consequential local cue. Compare that
performance with the richer authoring sources under their assigned authority.
Contextual and interpretive instructions must contribute to the selected
depiction; story-state decisions and observation limits retain their own owners.


## 10. Reference-corpus cue harvesting

For an authorized reference-corpus analysis or cue-harvesting task, treat the
selected images as evidence for coordinated performance grammar rather than as
a queue of one-image labels. The observation scope can require complete channel
coverage; it does not prescribe the detail of a later prompt projection.

1. Inventory the visible observation channels before naming emotion: eyes, lids, brows, mouth, tongue, jaw, cheek color, breath, sweat, tears, head, shoulders, spine, hands, feet, distance, contact, species appendages, and mechanical signals.
2. Preserve cue ownership and geometry. Record which subject owns each hand, paw, tail, wing, manipulator, tool, contact, support surface, and gaze target.
3. Separate observation from interpretation. Keep plausible alternative readings with confidence and context requirements, including adult sensual or erotic readings when the combined evidence supports them.
4. Cluster repeated coordinated patterns across images. Promote a `body-language-cue` record only when the pattern is reusable beyond one subject, outfit, pose, environment, or camera.
5. Reuse or strengthen an existing cue only when it already owns the pattern. Visual or naming similarity is not enough to merge records. A deliberate consolidation requires common semantic authority, a field-by-field lossless union of every detail, provenance fact, and search association, explicit remapping of every reference, and review. Otherwise retain both cues and relate them as variants.
6. Keep scene-owned geometry in the base scene and link reusable grammar through `search_profile.compatible_with`. A cue does not replace exact scene staging, contact, depth, or prop construction.
7. Keep transient cues out of identity locks. Blush, sweat, saliva, tears, ear rotation, tail motion, raised hackles, optic pulse, vent cadence, and gesture state remain current-state or transient-action evidence unless the source explicitly defines a stable identity feature.
8. Ordinary animals, anthropomorphic subjects, creatures, hybrids, robots, and androids use domain-valid channels. Never force a human face grammar onto a subject whose performance is carried by natural body plan or mechanical function.
9. Source images remain evidence and are not distributed with the skill. Preserve reusable production knowledge, not source signatures, exact logos, watermarks, copied character identity, or editorial censorship devices. Remove obvious mosaics, blur patches, paint shapes, stickers, bars, and replacement marks, preserve the underlying supported semantic content, and keep covered fine structure open.

The maintainer may sample a very large residual corpus through contact sheets, but promotion decisions must still be traceable to representative source filenames or reference IDs. Follow the [Cue Extraction Log Contract](maintenance/presets.md#cue-extraction-log-contract); record the pack-specific trace in `cpb-resource:sandbox-cue-extraction-log` or `cpb-resource:source-notes`.


## Human garment, recovery, and adult-social cue collection

For recurring human reference clusters, collect performance evidence through natural human anatomy and explicit scene ownership. Track shoulder-to-hand chains during camera reach, towel use, self-touch, and garment removal; pelvis, bench, bed, table, floor, and water support during seated, reclining, stretching, and bathing poses; eyelid tension, returning gaze, mouth shape, tongue, localized color, breath, sweat, and muscle tension; garment phase, cloth continuity, waistband construction, and hand-to-fabric contact; and the declared viewer or partner relationship that distinguishes casual confidence, fatigue, sensuality, erotic invitation, reflection, and private recovery.

A repeated adult human identity may support general, romantic, adult-sensual, and adult-erotic performance candidates across different scenes. Preserve the visible cue bundle and record candidate interpretations separately. Select intensity from the brief and relationship context. Keep temporary sweat, water, flush, fatigue, arousal, garment state, and pose outside the identity lock. When two images document adjacent phases of one action, such as a shirt crossing the crown and gathering above the head, strengthen one canonical action scene and retain both phases as variation evidence.

## State-grounded application and observed review

Apply this expressive specification to the actual target state and scoped portrayal intention,
not a generic emotion-to-gesture label. [World Realization](runtime/world-realization.md) coordinates
independent temporal targets, relevant source versions and explicit consumer views. Felt state,
visible display, current voice mode and reference-image identity retain different roles.

For continuous output, compare the adopted outgoing/incoming conditions actually needed for the
connection. For a still image choose the depicted phase rather than contradictory endpoints.
Review actual observed voice/body cues and timings separately from the correctness of a planned
state. A deliberate contrast, omission or disruption can be valid when scoped in authorial intent;
a render discrepancy does not establish that intention retroactively.
