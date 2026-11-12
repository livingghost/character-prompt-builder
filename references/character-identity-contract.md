# Character Identity Contract

A Character Identity Contract defines the stable properties that make a subject the same character across scenes and time. The adopted contract supplies those properties; a scene-specific Production Specification realizes them in the chosen scene.

## Identity at the authored level of detail

Identity is the complete set of applicable authored distinctions, together with
their relationships, conditions and permitted variation. Use that definition to
construct the character in each scene. The ownership categories below organize
the sources; applicable definitions can extend beyond those categories. A
character can depend on a subtle transition between regions, the placement of a
small detail relative to another structure, a deliberately absent feature, a
characteristic way of initiating movement, or a relationship between two
characters. Carry these distinctions at their authored level of detail alongside
the broad silhouette and other recognition anchors.

Preserve the meaning and granularity of the source. A broad silhouette and a
small directional asymmetry can both be essential. Keep qualifiers, degree,
attachment, orientation, comparison, negation and conditions with the property
they define. Describe coexisting systems independently where their distinction
matters, retain an unspecified value's open scope, and apply examples to the
particular construction they explain. Free text remains complete source evidence
even when it contains more distinctions than its current structured
interpretation records.

Select the applicable owners while composing the image: the adopted identity,
its species and individual morphology, any active Era, Form or Appearance
Contract, and independently authorized sheet or other source material. A sheet
can collect these definitions without becoming the sole authority for them.
Carry their applicable definitions into each new scene at the adopted scope,
including when the latest request relies on the character without repeating
its design. Apply authorized changes through their owning sources.
Keep source authority, current scene state and rendering choices distinct. A
proposal, an unaccepted candidate or a detail merely visible in a reference does
not acquire canonical status through this selection.

For each meaningful group of source definitions, decide what the current scene
requires. Group definitions that share the same treatment and split exceptions
where their conditions differ. Visibility is a projection question: an occluded
part still exists, and it may affect silhouette, draping, contact, shadow or
motion. An approved transformation changes only its stated scope. A relative
size definition compares the characters under its authored conditions; image
height alone cannot establish it across different depth, pose or perspective.
Do not manufacture a comparison for every pair of subjects.

## Construct the character in the scene

Start with the adopted definition and the scene being made. Treat settled
properties as the character's established construction. Describe the forms,
surfaces, details, relationships and performance that realize that definition
under the chosen action, view and rendering. Resolve open scene choices within
the commission's creative scope and carry them into the depiction.

Develop each meaningful group as wanted content. For a surface feature, state
its shape, location and relationship to adjoining structures at the specificity
the source supplies. For a characteristic action, describe what the character
does and how the defined tendency appears in this situation. For a relative
property, describe the relationship under its applicable conditions. Related
properties can share one intelligible description or a suitable reference view.

Choose the text and media that communicate that construction most effectively.
A source image can supply several adopted details together; a focused view or
sentence can carry a distinction that another image leaves unclear. Select the
suitable combination and write the actual depiction through the ordinary
direction, delivery and reference choices. Use the model's supported primary
description and image inputs for the wanted content. An explicit absence or
other required exclusion keeps its exact meaning in the appropriate supported
channel alongside that description.

For example, an adopted design may define a left seam that forks into two
shallow branches, two pale marks just inside that fork, and a right seam that
stays unbranched. A frontal greeting rendition can say:

> The character faces forward with its left hand raised in an open greeting.
> Its left head seam forks into two shallow branches, with two pale marks just
> inside the fork. The right head seam follows its single unbranched course.
> The raised hand sits clear of the head,
> leaving both seams and the marks visible together.

The action, view and hand placement in this synthetic example are selected
means for that scene; the seam and mark definitions come from its adopted
source. The wording describes the image to make. Use the same approach for
other kinds and scales of identity detail, preserving their own source meaning.

Build criteria from the applicable source and commissioned result: state the
properties and relationships that make this the same character, with their
conditions and permitted variation. Bind that expectation to the authored
rendition through the coverage procedure below. Chosen views and actions realize
that definition within the commission's scope. During review, compare the
depicted character with the full applicable source. A supported realization of
those requirements receives a pass, including through another suitable view or
action. A source discrepancy receives a repair scoped to its effect on identity
or the requested scene. Keep uncertainty with the property and decision it
affects, using the existing [review and repair guidance](runtime/production-direction.md#observe-and-repair)
to distinguish a selection issue from a nonblocking limitation or improvement.

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

## Source to input and review coverage

Use the ordinary `draft-inputs`, `build-inputs`, `check` and `prepare` workflow
for saved production. Construct the wanted depiction as described above, then
use coverage to carry its source relationships through preparation and review.
The editable owners are `authoring.task.sources` and
`authoring.task.criteria` in the existing choices. The builder derives the
coverage view; do not maintain another digest or manually copy hashes between
records. A source row can declare `identity.subject_ids` and
`identity.selectors`. Each selector is a JSON Pointer into the original source;
`""` selects the complete document. Text and media use the whole-source
selector. Choose the actual source authority and its applicable scope, keeping
the row's original path, locator and reason. Source selection does not adopt a
proposal or authorize changing canon.

The inventory preserves the original bytes by hash, selected values and every
terminal below each selected subtree, including empty collections and null.
It does not filter by familiar feature names. A selected free-text value stays
complete; its internal clauses are not claimed to have been semantically
decomposed. Review such values at the detail their meaning requires. Selecting
the entire document or a large group is a commitment to examine that scope,
not evidence that the examination happened.

Existing state graphs contribute their independently owned Identity, species,
individual morphology, Era, Form and Appearance nodes. References assigned
identity influence contribute their original image and exact influence scope.
These sources are discovered from the selected graph and reference owners even
when the `recurring-identity` reading feature was omitted. Their displayed IDs
are `state:SUBJECT:NODE` and `reference:REFERENCE_ID`. Use the IDs in the
inventory; do not redeclare those images or graph nodes merely to copy their
hashes. An explicitly selected source covering the same original owner is
reused. Recurring subjects require source coverage and independent review.
Identity mentioned only in unrestricted prose still requires the author's
explicit subject and source selection; the runtime does not infer it by words.

`REFERENCE_ID` is the stable reference use, not an attachment number. For use
`keeper-face`, the inventory source is `reference:keeper-face`, while
`carriers[].reference` remains `keeper-face`. The
[reference identity procedure](runtime/reference-delivery.md#reference-identities-and-coverage)
shows where to select or discover each ID and how the builder preserves it.

When a state graph supplies a Visual Authority or Visual Evidence Bundle,
include its complete scope, priority notes, evidence relation and disposition
in the same inventory. These documents remain authority or evidence context
according to their original status. Their presence does not adopt an observed
feature as canon. Classify their application through the same grouped criterion
bindings used for the other sources.

For each applicable group, add `identity_bindings` to its existing independent
criterion. A binding names the source ID, subject IDs, selectors, scene
treatment, reason, actual-input carriers and any accepted variation ID. Its
criterion's `text` owns the question the result must answer. Write that
expectation from the commission and source, independently of the prompt.
Several selectors may share a criterion. A more specific selector can define
an exception to a broader group; equally specific conflicting treatments are
rejected. Cross-subject definitions name every affected subject in the same
binding and retain the source's comparison conditions.

| Treatment | Meaning in this image |
| --- | --- |
| `preserve` | Keep the applicable source definition, including its conditions and meaningful absences. |
| `indirect` | Keep its effect on another visible property, such as contact, silhouette, draping or movement. |
| `not-exposed` | The chosen view cannot establish the property itself. Keep it binding and record the observation limit. Occlusion does not establish absence. |
| `not-applicable` | A stated source condition does not apply to this scene. Give the actual reason; omission alone is insufficient. |
| `authorized-variation` | Apply one existing accepted variation, within its task or exact source scope and limits. Name its existing ID in `variation`. |
| `unresolved` | A necessary definition or its application remains unsettled. Preserve the question; a candidate review cannot turn it into a pass. |

Active obligations require hard criteria, with image evidence for an image
task. `not-exposed` and `not-applicable` groups can use advisory criteria for
their limits; they do not become demonstrations of invisible identity. Every
identity subject also needs a hard criterion with `identity_review` naming its
subject ID. That criterion compares the character against the complete
applicable source scope, beyond the traits initially extracted into individual
bindings. Several subjects may share this comparison when its question covers
them together. Report additional mismatches or uncertainty through the existing
review's repairs and unresolved issues.

The following is a synthetic excerpt, not a complete production task. Assume
the adopted source `design.json` contains a `seam` object and the actual primary
request includes the quoted sentence. The source selection and criterion stay
in the ordinary task; its independent whole-subject criterion is also required.

```json
{
  "source": {
    "id": "adopted-design",
    "path": "design.json",
    "role": "design",
    "disposition": "applied",
    "locator": "The adopted seam definition",
    "reason": "Preserve the authored asymmetric termination and surface transition.",
    "identity": {"subject_ids": ["A"], "selectors": ["/seam"]}
  },
  "criterion": {
    "id": "seam-construction",
    "strength": "hard",
    "evidence": "image",
    "text": "The seam retains its source termination, direction and transition into the adjacent surface.",
    "identity_bindings": [{
      "source": "adopted-design",
      "subject_ids": ["A"],
      "selectors": ["/seam"],
      "treatment": "preserve",
      "reason": "This view exposes the complete seam and its adjoining surface.",
      "carriers": [{
        "kind": "text",
        "surface": "primary",
        "quote": "The single seam curls inward and ends before the blue rim."
      }],
      "variation": null
    }]
  },
  "whole_subject_criterion": {
    "id": "character-A",
    "strength": "hard",
    "evidence": "image",
    "text": "Compare A with the complete applicable source, including distinctions omitted from the individual checks; record any mismatch and any limit of this view.",
    "identity_review": ["A"]
  }
}
```

A text carrier selects the actual `primary` or `negative` request surface.
Use `"selection": {"whole": true}` when the whole selected surface carries the
obligation. The compiler takes its current text directly; no separate quotation
or numeric offset needs editing. For a narrower selection, use
`"selection": {"text": "the exact selected passage"}`. If that passage occurs
more than once, add a one-based `occurrence` to select one occurrence. An
ambiguous or missing selection identifies the unresolved carrier. An explicitly
authored `quote` is also an exact wording choice, as in the example above.

The compiler derives the quotation, current field hash and UTF-8 byte ranges
from the actual rendered request. A changed surface becomes new input; an
updated position does not certify that the source's meaning remains preserved.
Text in a Production Specification, criterion or unused prompt file does not
establish delivery to the model. A reference
carrier selects `{"kind":"reference","reference":"REFERENCE_ID","use":"identity"}`
or another explicitly permitted influence appropriate to the obligation. The
compiler resolves its subject assignment, original source, delivered bytes,
request field and any board region or transform. Reordering attachments keeps
their logical identity. The reference input owner assigns the editable use ID
when the selection is first saved and retains it through reordering or an
explicit same-use replacement. The actual source, crop and delivered content
remain separately bound by their current hashes. A different approved view may carry a definition; the
source image need not be pasted into every request. The reference's allowed
influence and exclusions still apply.

Inspect the actual prepared carrier and the complete combined model input.
An original image's existence does not show that its relevant region survives
a crop, resize or board assembly. A valid text occurrence establishes delivery
of that wording, not that it conveys every source condition. The independent
rendition assessment judges sufficiency and leakage from incidental source
state. Widen a reference's scope only when its actual authority supports it;
do not universally narrow references and then attempt to repair every missing
property with text.

The input builder returns uncovered source values, missing subject sources,
unbound active groups and missing whole-subject reviews at their editable
locations. It can publish useful prepared files with those choices unresolved,
but it does not publish an executable production task. `check` and `prepare`
also enforce the contract, including exact request carriers, so bypassing the
input builder does not bypass coverage. The sealed run retains the coverage
view for decision and review, separately from model-facing instructions. A
prompt-only authored artifact binds its delivery text and explicitly lacks
verification of a model request.

Retained identity sources remain at their original owning paths. Drafting
records their bytes; a changed source invalidates that draft's retained witness.
Edit or adopt a new definition in its owning workflow, read it, then draft the
current application and criteria. Editing a generated source copy cannot
redefine its identity authority. Existing runs retain their historical source
bytes and review basis; freshness checks prevent using stale live inputs for a
new operation. A later source edit never rewrites an earlier review as if it
had assessed the new definition.

Coverage establishes explicit source selection, structural correspondence and
delivery bindings. It does not prove complete semantic interpretation or
successful depiction. Observe the candidate first without expected criteria,
then compare it with the preserved source and actual input. Keep unsupported,
unseen and indeterminate findings explicit. An owner's allowance for a
particular nonpassing result preserves that finding and does not alter canon.

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
