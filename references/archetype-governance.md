# Archetype Governance

A character archetype is a reusable identity contract for a recurring subject. It is not a synonym for species, body build, color, occupation, outfit, scene, or style.

The machine-readable policy is `cpb-resource:archetype-policy` resolved from the explicitly selected provider. The prose and machine-readable policy are one governance contract and must be revised together.

## 1. What an archetype owns

An archetype may own only stable identity decisions that should survive materially different scenes:

- subject domain and body-plan class
- species or structural family
- stable morphology, including face, muzzle or beak, ears, appendages, hands or paws, feet, and tail
- stable proportions and silhouette
- stable surface system, palette, markings, stripe or patch topology, and eye design
- localized identity details such as scars, notches, tattoos, piercings, or prosthetics when they are part of the recurring identity
- identity-defining equipment only when the item is persistent enough that removing it would change recognition

The archetype does not own one-off pose, camera, crop, environment, lighting, weather, temporary wetness, transient emotion, scene-specific role, or ordinary clothing. Those belong to scenes, modules, current state, or art direction.

## 2. What does not justify a new archetype

None of the following is sufficient by itself:

- species alone
- body build alone
- coat or skin color alone
- one accessory, garment, or occupation alone
- one pose, expression, camera angle, or environment
- one source image whose stable identity cannot yet be separated from its scene

Route those cases to the appropriate species, body-build, proportion, palette, marking, accessory, outfit, occupation, expression, scene, or style record.

## 3. Creation gate

Create a new archetype only when all of the following are true:

1. The intended subject is recurring, or the user explicitly requests a reusable character identity.
2. The identity can be described independently of one scene.
3. At least three stable identity axes are known beyond a bare species name. The axes normally include morphology or body plan, surface or markings, proportions, palette, eye design, or distinctive details.
4. The record reduces repeated identity decisions across several images or scenes.
5. A complete existing archetype cannot represent the identity without changing its stable face, marking topology, proportions, or body plan.
6. Ordinary short English wording can distinguish it from nearby archetypes in retrieval.

Evidence from two or more materially different scenes is preferred because it reveals what remains stable. A single image can still support an archetype when the user explicitly intends a recurring character and the stable identity is sufficiently specified, but the author must mark uncertain details as variable rather than inventing permanent locks.

## 4. Add, reuse, merge, or variant

Use this decision order:

- Same recurring identity, different pose, clothing, occupation, setting, or time: reuse one archetype and add scenes or modules.
- Same species and build, but different face, marking map, proportions, or persistent details: separate archetypes may be justified.
- Same identity with named forms or transformations: keep one identity contract with named variants when the forms share a canonical identity; split only when each form needs a separately reusable body plan and appearance lock.
- Differences limited to wording or retrieval aliases: merge into the richer canonical record.
- A formerly scene-owned detail that recurs across scenes: promote it to a module or archetype field and update the affected scenes.

A useful cluster often becomes one archetype plus several scene variants, not one archetype per image.

## 5. Growth control

There is no useful global numeric cap. Growth is safe only while semantic ownership and retrieval remain clear.

Every archetype addition must therefore include:

- comparison against complete existing archetypes
- a distinct discovery group or a deliberate variant relationship
- at least three natural aliases
- a retrieval regression that omits the ID and exact label
- scene and module reuse where appropriate
- merge or retirement of any newly exposed duplicate
- direct updates to every affected reference when a canonical archetype ID changes

If an archetype is reachable only by its exact name, differs from another only by outfit or scene, or does not reduce repeated identity work, it should be merged, downgraded to modules, or removed.

## 6. Species, domain, and reality status

Species and domain answer different questions.

- The species module names the biological or fictional species vocabulary.
- The domain states the body-plan and behavior contract used in the image.

The same species word may therefore exist in different domains without conflict:

- `domain: animal` means an ordinary or natural animal body plan and species-appropriate behavior.
- `domain: anthropomorphic-animal` means a humanoid or person-like body plan with species head, surface, appendages, clothing adaptation, and coordinated animal-human performance.
- `domain: creature` or `domain: hybrid` covers fictional body plans that are not ordinary animals or standard anthropomorphic forms.

A natural tiger and an anthropomorphic tiger must not share one archetype. They may share species vocabulary, but they require different domain realizations, morphology, locomotion, contact logic, and identity locks.

For a generic real tiger or wolf request, use the ordinary-animal domain realization plus the species record, surface, behavior, environment, camera, and scene modules. Create an ordinary-animal archetype only for a recurring individual whose stable stripe map, scars, ear damage, proportions, coloration, or other identity details must persist across images.

Fictional and real subjects may coexist in the same catalog and in the same image. Apply one domain realization to each materially different subject and preserve explicit subject ownership. Domain filtering and identity contracts prevent an ordinary animal from inheriting humanoid limbs or clothing and prevent an anthropomorphic subject from collapsing into a quadruped.

## 7. Examples

| Brief | Correct layer |
|---|---|
| `tiger` | species vocabulary plus chosen domain |
| `muscular tiger` | species plus body-build or proportion modules |
| `orange tiger wearing a visor` | species, palette, accessory, and scene modules |
| the same orange tiger with the same face, stripes, eyes, and proportions across pool, beach, and onsen scenes | one archetype plus several scenes |
| a natural Bengal tiger photographed in a forest | ordinary-animal domain plus species, environment, camera, and behavior |
| the same natural tiger with a chipped right ear and a stable stripe map across a documentary series | ordinary-animal archetype |
| an upright tiger athlete with humanoid hands and clothing | anthropomorphic-animal domain; archetype only when the identity recurs |
