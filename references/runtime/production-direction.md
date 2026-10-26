# Production direction

Establish what the requested artifact must communicate, what the viewer should
notice, what must remain fixed, and what the author has left to the agent.
Read the applicable design, persona and authorial intent together. A trait,
emotion or format label alone does not determine its expression. Characters,
a story clock and a physical camera are optional.

This direction process applies before prompt wording, including a prompt
delivered in conversation. Saved production records the consequential choices
in the existing task `direction`; a conversation-only draft needs no task file.

## Contents

- [Choose the expression](#choose-the-expression)
- [Record the production direction](#record-the-production-direction)
- [Preserve accepted variation at its declared scope](#preserve-accepted-variation-at-its-declared-scope)
- [An image of an action is not the action](#an-image-of-an-action-is-not-the-action)
- [Observe and repair](#observe-and-repair)

## Choose the expression

Establish the intended use and viewing conditions alongside the content. A
page, card, screen image, display or another form changes what can be read,
handled or encountered together. Distinguish the artifact itself from an image
of that artifact in a setting. A screenshot appearance supplies visible screen
content; working interaction requires a separately supported implementation.

Choose how the information is organized and how its marks or surfaces look.
A rendering medium or profile supplies the latter. Layout, attention, sequence,
typography and relationships still need direction. One image can contain
several views, and one continuous scene can combine different rendering
treatments. An unspecified choice is open within the current request's authority.

Before resolving an open expressive choice, consult applicable production
knowledge through [Discovery](sparse-discovery.md). Use the communication
problem as the query: establishing a relationship, revealing a detail, comparing
states, directing attention, or organizing an image with type, for example.
These examples are not a closed list of purposes or a format classifier. Read
the returned functions and scoped inventory, then inspect records that could
change the decision. Use vocabulary category browsing for additional forms and
wording. Inspect component roles and their relationship when combining forms:
an image can carry an event while lettering carries speech, a diagram explains
structure, or an interface makes a selected state visible. Detailed subject
requirements can still leave presentation open.

Consider materially different constructions when there is a real tradeoff.
Choose the one that serves the purpose and fixed requirements with the least
unnecessary complexity. A single continuous view may establish space; ordered
views may distinguish an observation from a reaction; a whole with a detail
view may explain a mechanism; image and type may share a hierarchy. Compare
their actual effects and limitations, rather than merely changing style labels.
A fixed layout or a narrowly scoped edit needs no manufactured alternatives.
Catalog ranking provides evidence to consider, never the choice itself. A
missing record leaves room for an authored construction. Familiar form labels
and their usual conventions supply possibilities, not compulsory furniture.

Choose within delegated scope and proceed. Briefly state a consequential
presentation choice when it helps the user assess the result, outside the
artifact. Offer a concrete alternative when its tradeoff is useful; do not
make the user choose from a menu for every task. Ask only when unresolved
meaning or authority would materially change a fixed requirement, or when the
user requested selection. The importance of a choice alone is not an approval
requirement. A choice for this artifact does not become a permanent preference.

Resolve the selected construction before adding local detail. Decide what is
seen first, what supports it, and how the parts relate. For multiple regions,
assign each a depicted purpose and local view; establish reading order where
order carries meaning. Panel dimensions, spacing and exact geometry need
specification only when they affect that reading or are fixed by the brief.
An open layout still needs coherent hierarchy and relationships.

For a mixed construction, give each image, material, mark system or information
layer a purpose and scope. Decide how the components meet: integration in one
depicted space, overlap on a page, an inset, a transition, or another authored
relationship. A drawn figure in a photographic setting needs the selected
scale, contact and depth relationships. Pasted photographs and drawn notes may
instead share the surface of a collage. Neither construction requires panel
borders. Apply rendering choices through the existing
[render intent](render-contract.md#choose-the-finish), preserving the intended
differences as well as the relationships that unify the result.

Shared identity can recur across views while pose, crop and visible detail
change. Check each view on its own and the artifact as a whole. A face turned
away need not display its markings; a selected detail view can carry information
that the spatial view cannot show. A sequence of attention need not advance
time or change story state. Preserve the actual temporal and source authority.
Flat graphic, diagram and type regions need their own visual organization,
without invented anatomy, depth or camera fields.

Use the selected knowledge by meaning and scope. A record's incidental subjects,
palette, default camera or example format do not become requirements. Preserve
its useful relationship or construction and adapt the realization deliberately.
The existing Production Specification owns any needed whole-artifact and local
region detail. Final prompt text describes those visible choices and necessary
reference use; selection reasons, source IDs and review criteria stay outside it.

When the request spans related images, use the existing
[Project Design](../../templates/narrative/design/design-template.md) to establish
shared recognition anchors, each output's purpose and the relationships between
outputs. Its medium, expression, continuity and dependency sections hold those
decisions at the needed depth. Adapt hierarchy, detail, text and treatment to
each use while preserving the declared anchors. Prepare each image through its
own Production Specification and request. Independent deliverables retain their
separate boundaries; a composed page is a selected output in its own right.
The batch route executes prepared image requests after their design is resolved.

## Record the production direction

The task's `direction` holds `purpose`, `intended_effect`, applied source IDs
in `basis`, optional `decisions`, optional `action_slice`, and `limitations`.
Keep the distinction between an intended effect and an audience response
actually observed; a manifest or passing test proves neither.

Record a consequential branch as `material`, with the considered options,
tradeoffs, selection and reason; the reader requires at least two options with
tradeoffs. A fixed instruction or routine choice may have one option (`fixed`
or `routine`). Leave `decisions` empty when no choice needs a record. The agent
chooses the expression; the script checks references, scope and complete
relationships. These records do not introduce an approval step.

Each decision names its question, source basis, options, selected option,
reason, criterion IDs, predecessor decisions in `depends_on`, and any
intentional deviations. A deviation records its source ID, source locator,
scope and reason, and leaves canonical identity unchanged. Detailed
personality, experience, physique, relationships and context may matter
together; read them together rather than looking up a stock gesture from an
emotion. Restraint, an unchanged stance, expressive exaggeration and a
deliberate contrast with ordinary behavior can all be valid choices.

An option's `realization` describes the actual `method`, executable
`instructions`, an optional applied `capability_source` and known
`limitations`. Check the selected tool's real accepted controls; precise
language about a pose or motion leaves open whether a model can realize it.
Use generation, existing artwork, reference preparation, composition, local
edits or another supported operation according to the purpose; a longer prompt
is one repair among several.

The bounded consumer and Generation Package receive **only selected expression
and method instructions**. Private source prose, rejected options, selection
rationale and deviation records stay in the author's run. Author the
model-facing instructions deliberately: whatever you copy into the selected
instructions reaches the consumer, sensitive content included.

## Preserve accepted variation at its declared scope

An author's allowance belongs in an optional decision `accepted_variations`
list. Each entry names its `id`, applied approval `source`, source `locator`,
`author`, `scope`, `allowance`, `limits`, and affected `criteria`. Include the
approval source in the decision's `basis`. Criteria must belong to that
decision; their existing hard/advisory status remains in force.

Use task scope for an allowance limited to this work task. Synthetic entry:

```json
{
  "id": "natural-fabric-folds",
  "source": "author-direction",
  "locator": "wardrobe allowances",
  "author": "request owner",
  "scope": {"kind": "task", "task_id": "outfit-study"},
  "allowance": "Fabric folds may change with the declared arm pose.",
  "limits": ["Keep the adopted garment color and closure structure."],
  "criteria": ["wardrobe-fidelity"]
}
```

For reuse across tasks, use `scope` with `kind: source`, an applied `source`
ID, and that source file's exact `sha256`. Include that source in the decision
basis. Task checking and preparation both verify the captured bytes. A changed source requires
reassessment before the allowance applies again. The source owner may be an
appearance contract, an adopted image, or another explicit production source.
The agent interprets the author's stated range; a hash establishes which
source the decision concerns.

Carry applicable entries into the next task and its review criteria. Task
scope cannot cross into another work task. Source scope can cross tasks only
with the same declared source bytes and an applied approval source. The review
uses the original allowance and limits, while consumer output retains only
the selected expressive instructions. A matching hash does not grade an image
or promote a candidate to canon.

Keep changed expression, pose, natural crop and approved wardrobe variation
separate from identity drift. Assess unwanted old clothing, source-state
leakage, broken contacts and anatomy against their own declared criteria.

## An image of an action is not the action

When a still needs a particular phase, `action_slice` describes `phase`,
`before`, `after`, free-form relations (`subject`, `relation`, `object`,
`note`) and a nonempty `not_verified` list. Use only relations needed to read
the image: support, contact, overlap, ownership, or other relevant constraints.
No mandatory anatomy, cast size or universal phase sequence is imposed.
Leave `action_slice` null when unnecessary; a still request stands apart from
any video pipeline. Two coherent poses leave the feasibility and timing of the
motion between them unestablished.

## Observe and repair

Prepare observable criteria before execution. Each has hard/advisory strength
and an evidence kind: `artifact`, `text`, `image`, `motion`, or `audio`. Review
the actual captured artifact with specific observations rather than an overall
score. Separate observation, interpretation against the purpose, and
limitations. An unexamined quality stays unexamined, not implicitly passed.

A repair identifies the relevant observation, decision IDs, operation, changed
targets and reason in the same review. Reconsider expression, framing, action
phase, source selection, local composition or a limited remaking operation when
appropriate. The `revision-intent` command compares the complete revised
preparation with its parent and refuses changes beyond the reviewed targets. It
binds the exact new input to an `edit` authorization and creates a linked run
through `revise`; old successful checks and candidate selection do not transfer.

See [Production execution](production-execution.md) for commands and evidence
locators, and [Production permissions](production-permissions.md) for the
independent authority boundaries.

## A failure must leave an actionable record

When any review check fails, record at least one repair with its observation
and target links, or state an explicit unresolved issue. A repair is a proposed
next action; its success is a separate observation. Use the actual image-edit
executor for scoped pixel operations, or a reviewed child run when the
production inputs must change. Either route starts from a fresh review and
selection.
