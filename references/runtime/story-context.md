# Story Context

Apply [Production direction](production-direction.md) within the existing [production run](production-execution.md): full applicable design and persona → purpose-specific choices → selected realization → actual evidence → scoped repair. [Permissions](production-permissions.md) distinguish delegated judgment from submission, selection and canonical adoption. This adds no second evaluation ledger and no obligatory cast, emotion curve or stock gesture.

Use a moment query when the task begins with a chosen story point rather than a
finished scene: a quiet interval, parallel actions, an earlier memory or a state
needed for a new depiction. No chapter, event, shot or protagonist count is
required at that point.

## Author and resolve

Read the relevant [narrative and persona](narrative-development.md) and identify
which recorded facts and [portrayal decisions](authorial-intent.md) matter. Keep
stable identity in its contracts. Use the state ledger for changes, including
learning, mistaken belief, emotion and obligations. A world fact does not teach
every character. Finishing an activity does not erase its unresolved consequences.

Create `story-context-query` using
[the query schema](../../schemas/authoring/story-context-query.schema.json) and
[the drafting template](../../templates/story-context-query.json). It
selects the exact sources, one timeline, an integer `story_order`, a descriptive
`story_time`, and an authored coverage record. The source bytes are pinned by
SHA-256. The timeline points to the existing base, event and process records and
records evidence for base fields; it is not another editable state history.
Coverage has `timeline_id`, `start_order`, `through_order` and `basis`. It bounds
the query inclusively but does not prove that every relevant event was authored.

The result contains the complete registered state in the five Shared State
buckets. Empty character sets are valid. Additional concepts live in the fields
chosen for the work, not in prescribed activity or emotion vocabularies.
`scene_context_ids` selects only the named scoped projections. An omitted list
selects none; old contexts are not automatically expanded. The timeline-wide
snapshot has a null context and excludes scene-local changes. A context's presence
in a query is not a claim that its activity is still underway.

Optional indexes group ID-keyed records using an authored collection pointer and
field pointer. They refer to state, not a second store of facts. Missing collections
remain missing. Preserve null, false, missing and explicitly unknown values as
different declarations. Do not infer psychology or interpolate between milestones.

`requirements` name a context (or null), JSON Pointer, test (`present`, `non_null`,
`equals`), purpose and requirement ID. Only `equals` takes a value. A view lists the
requirement IDs that apply to its use. Diagnostics include the failed pointer,
expected test, presence and actual value. A predicate is not artistic judgment.

## Portray the same identity at the chosen point

Use `author_bindings` to reference the applicable persona epoch, identity decisions
or authorial intent. Each binding has a role, source, exact selector and a half-open
story interval `[start_order, end_order)`. Null end means unbounded; an empty
context list applies to any selected context. Select a full document, an exact
Markdown section, a JSON Pointer or a declared intent ID. These are authored
applicability decisions; the resolver does not invent the relationship between a
chapter and a story coordinate.

Read the complete persona when developing characterization. A selected passage
supports the present choice; it does not replace the dossier or explain away
inconsistency. Choose voice, bodily expression and emphasis from the persona and
creator intent in this situation and with these counterparts. Document a deliberate
departure and its reason rather than treating the current emotional label as a
universal performance instruction. Consult [Character Performance](character-performance.md).

A view's `guidance` pairs the chosen instruction with the binding IDs supporting
it. The binding must apply to the selected context and time. An intent binding
requires declared adopted or user-anchor status before it supports a consumer
instruction. The author context contains selected source passages for review;
consumer files contain only chosen scalar state leaves, explicit instructions,
requirement results and compact binding references, not full dossiers or ledgers.
Review that selection for knowledge limits, secrets and the requested audience.

Do not duplicate promises, relationships or knowledge already owned by a narrative
record. Refer to the existing owner when recording a mutable status. A reader-facing
mystery and a character's unanswered question may be distinct; link their meaning
without silently treating either as the other.

## Commands and results

Run from the directory containing `SKILL.md`. Choose a new directory for output.

```text
python scripts/story_context.py inspect --root PROJECT --query query.json
python scripts/story_context.py build --root PROJECT --query query.json --out OUTPUT --require-fields
python scripts/story_context.py verify --root PROJECT --query query.json --bundle OUTPUT --require-fields
python scripts/story_context_smoke_test.py
python examples/story-context/run_example.py --out EXAMPLE_DIRECTORY
```

`inspect` reports the diagnostics, indexes, applicable bindings and per-view
requirements. `build` creates `story-context.json`, public world snapshots, requested
consumer views and `report.json`. Context and view IDs address records; full SHA-256
filenames keep their punctuation separate from file naming. Existing output is not
replaced. On interruption, inspect the retained reservation before removing it;
only a completed, verified directory is usable.

`verify` rebuilds from the selected query and current source bytes, checks every
expected file and rejects extras. `--require-fields` applies to all three commands:
failed predicates produce a failing exit, and prevent build publication. Without
it, diagnostic output may be retained, with `requirements_ok: false`. Content
agreement and predicate results are reported separately.

Input changes, malformed records, missing source pins, impossible applicability,
unselected contexts, unsupported array/object selections, conflicting temporal
operations and output-size limits fail with a diagnostic. Nothing is silently
truncated. Narrow the selected contexts or references when the output is too large.

## Use the moment in production

Read [Production Execution](production-execution.md). Select the `story-context`
route or add `--feature story-context` to the relevant route. A task's optional
`moment_views` selects `{query, bundle, view_id}`; the feature requires at least
one verified view. No realization unit has to be invented to fill this selector.

Preparation rebuilds the query, verifies the bundle and checks the selected view's
requirements. It pins the query, source documents and exact output files. Handoff
includes only the selected views. Changed source state, persona, query, instructions
or outputs make the run stale and require preparation again. Review, candidate
selection and completion remain bound to the actual result. Delivery does not
adopt new canon.

For image work, use the selected state as the basis for applicable identity,
scene-context and visual-projection records, then follow reference selection,
retrieval-before-composition and exact-submission approval. The moment is not itself
a complete render specification. Do not bypass those gates by pasting the author
context into a prompt.

## Time and simultaneous operations

The temporal resolver serves both moment queries and planned realizations. At a
coordinate, process milestones advance first, then discrete events apply. Within
each phase, independent operations may coexist. Overlapping writes, array index
shifts, and writes to another event's preconditions require a distinct coordinate
or one ordered atomic event. An initiating event and its matching offset-zero
milestone are one logical start with both evidence IDs retained. Use explicit
coordinates for intentional causal ordering; identifiers are not priority rules.

The tests cover arbitrary coordinates, rewinds, character-free worlds, scoped
contexts, concurrent and interfering actions, linked processes, selective guidance,
missing facts, output verification and production invalidation. Fixtures and
predicate success do not establish user consent or the quality of a depiction.

## Prepared scene Persona material

During scene preparation, read the complete applicable Persona definitions, their
portrayal model, authorial intent and current conditions. Save the actual relevant
definition text, cross-definition dependencies, partner-specific exceptions and
scoped applications with [Scene Persona Material](scene-persona.md). This is a
record of understanding after reading, not a router guessing which sections matter.

When a reviewed material bundle is explicitly selected for this task, verify it and
use its `persona.md` for execution, local repair and resumption. Do not repeat the
full preparation read merely because the same scene is rendered again. Reopen the
preparation when sources change, material is unready, or the work introduces a new
participant, topic, knowledge, relationship condition, aim or other condition not
covered by the prepared application. No genre, cast count, speech or human model is
required. Missing material is not evidence that the original had no definition.

The material is authoring input, not canon or a performer's knowledge. Required
text is never silently truncated, and a size measure cannot establish semantic
completeness. Full reading and its scope review remain attributed judgments.
