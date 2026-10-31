# Character Identity Contract

A Character Identity Contract contains only the features that make a subject the same character across scenes and time. A scene-specific Production Specification is not an identity authority.

## Owns

- species or base form and body plan
- stable proportions and silhouette
- head and face construction
- stable surface regions and markings
- appendages and stable asymmetry
- identity-level accessory relationships
- distinctive details
- stable performance vocabulary
- stable growth identity as author-declared structures, with independent locations, boundaries, geometry and applicable continuity; no particular head, facial, regional or terminal structure is a required slot
- conditional text-anchor fragments
- reference-coverage obligations

## Does not own

- current emotion or pose
- current wardrobe or carried props
- temporary hair or fur wetness, disorder, raised or compressed covering, removable polish, chipped nails, dirt, or scene-specific grooming
- temporary injuries, wetness, dirt, or fatigue
- relationship state
- scene, camera, lighting, or target model

The growth contract carries that split in its own fields. `identity_lock_fields` names the exact stable paths that must transfer across scenes, `variant_fields` names the exact paths an approved Appearance Variant may change without redefining identity, `grooming_state` holds the current scene-resolved condition, and `source_confidence` declares the authority behind the record. Naming a path in either array does not make a current value into identity; the paths must agree with the owning Identity or Appearance Contract and with the resolved scene state.

## Rendered reference transfer boundary

A rendered reference image is evidence for the contract, not the contract itself. It shows permanent identity, scene-specific character state, and source-render context together, so no visible property becomes an identity invariant merely because it appears in the reference.

**Scene-specific character state** is every visible or performance-relevant property resolved for a scene rather than owned by permanent identity. If a property can change while the subject remains the same character, it belongs to this state by default unless an approved Identity, Era, Form, or Appearance Contract explicitly owns it. The definition is open-class and must not be reduced to the examples in `Does not own`.

For every cross-scene reuse, derive an explicit transfer map:

- permanent identity traits that the new image must retain;
- approved scene-specific character state that must continue;
- source-only scene-specific character state that must be discarded;
- target scene-specific character state that replaces it;
- source-render context or contamination that must be discarded or rescoped;
- scene-only geometry or finish supplied by other references.

Unless the user or approved state artifacts require continuity, unlock the complete source scene-specific character state across performance and attention, articulation and action, physical and physiological condition, appearance and presentation, possession and equipment, relationship and viewer awareness, environmental response, and resolved current state. Treat camera, crop, lighting, environment, finish, and source-specific text or insignia as source-render context rather than character identity. Keep this classification in the transfer map. Author the target scene from it, adding only the necessary directions for the images actually supplied. A request for the `same character` does not communicate this distinction reliably by itself.

Apply the transfer map to the attributes that matter in the current image.
Inspect their actual construction and location in the adopted references,
including the visible facial proportions, marking boundaries and body silhouette.
Pair each retained attribute with its source and each requested change with its
current scene or contract owner. Choose the reference view that reveals the
attribute; a full sheet, portrait and detail image can each carry primary
evidence within their coverage. Preserve unknown regions as unresolved coverage.

Use the same retained attributes and requested changes in the task's existing
criteria. Evaluate the result with the selected view, expression and approved
variation in mind: a head turn changes the projected outline while the face
construction remains the identity requirement. State the region that can
establish each relevant property and any required visibility. A newly chosen
gesture or expression realizes the present scene; its selection alone leaves
permanent identity and future behavior with their existing owners.

Keep these application decisions in Production direction, the reference scopes
and the existing review, at the depth needed for the task. The contract remains
the owner of stable facts. Use a criterion's observed outcome to decide whether
the current image carries those facts successfully; a valid contract or matching
source hash establishes the input authority, while the rendered candidate
supplies the evidence of its realization.

For an anthropomorphic subject, human-like head hair is not implied by base fur and is not interchangeable with a mane, ruff, cheek tuft, crest, or other regional covering. Record every coexisting system independently with explicit presence, stable boundaries, landmark-based length, density, direction, texture, color relationship, silhouette role, and continuity rules. Cross-scene transfer preserves those permanent definitions while leaving wetness, temporary styling, wind response, flattening, raised fur, and other current presentation to the target scene state.

## Anchor fragments

Each anchor fragment has exact wording, priority, visibility conditions, carriers, and omission conditions. Preserve the full specificity needed to reconstruct the character; concision does not permit generic replacement of identity anchors. A signature ear stud may be carried by approved reference media, text when the ear is visible, and review criteria. It is not pasted into every prompt when the ear is fully occluded.

## Coverage requirements

Reference bundles are planned from visible identity obligations, not a fixed image count. A left-ear accessory requires left-profile or left-three-quarter coverage; a rear marking requires a rear view; paw-pad identity requires a paw detail. The planner may add views until every declared obligation is covered.

## Identity versus era, form, and appearance

- **Era Contract**: approved long-term changes such as aging or long-term training.
- **Form Contract**: topology or silhouette changes such as transformation or mechanization.
- **Appearance Variant Contract**: approved wardrobe, grooming, paint, disguise, or ceremonial presentation.

Each contract is independently hashed. Reference assets can therefore state exactly which identity, era, form, and appearance they support.

The identity contract's morphology references are cryptographic, so changing the species profile or individual realization requires rebuilding the identity contract and every dependent artifact. A permanent change is routed to the correct owning contract and every downstream hash is rebuilt.


## Morphology references

A recurring identity contract references exactly one approved `species-morphology-profile` and one approved `individual-morphology-contract`. The identity contract summarizes stable recognition anchors, but it does not duplicate the complete anatomical inventory.

The species profile owns valid feature kinds, counts, attachment topology, body regions, surfaces, expression channels, capabilities, meaningful absences, developmental variation, and near-species differentials. The individual contract owns exact feature realizations, measurements, instance IDs, asymmetries, markings, damage, modifications, grooming, nails or claws, personal expression habits, expression tools, and state boundaries.

Use [Morphology and species contracts](morphology-and-species-contracts.md) for the full authoring and review procedure. Unknown or occluded details remain unresolved rather than becoming generic defaults.
