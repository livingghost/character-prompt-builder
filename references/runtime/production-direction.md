# Production direction

Read the whole applicable persona, design and authorial intent, not just a
trait or emotion label. First establish what this deliverable must do, for whom
or in what use, what must remain fixed, and what expressive freedom was actually
granted. A scene, identity reference, diagram, costume study, still landscape
and abstract asset each need their own information and viewing hierarchy; these
are examples, not a closed purpose list. Characters and a story clock are
optional.

## Choose an expression, not a label

The task's `direction` holds `purpose`, `intended_effect`, applied source IDs
in `basis`, optional `decisions`, optional `action_slice`, and `limitations`.
Keep the distinction between an intended effect and an audience response
actually observed; a manifest or passing test proves neither.

For a consequential branch, compare materially different options with their
tradeoffs, select one, and explain why it suits this purpose and these sources.
Mark that decision `material`; the reader requires at least two options with
tradeoffs. A fixed instruction or routine choice may have one option (`fixed`
or `routine`), so reserve the contest for consequential branches. The actor
chooses the expression; the script checks references, scope and complete
relationships.

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
