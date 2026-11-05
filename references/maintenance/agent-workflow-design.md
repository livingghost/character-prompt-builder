# Agent workflow design

Use this document when designing, changing or reviewing the Skill's authoring,
execution and recovery interfaces. It defines maintenance criteria for the
whole production workflow. It adds no production approval, reading receipt or
checklist to an agent's ordinary task.

## Contents

- [Responsibilities](#responsibilities)
- [One editable source across a task](#one-editable-source-across-a-task)
- [Changes and dependencies](#changes-and-dependencies)
- [Context for judgment](#context-for-judgment)
- [Interruption and external effects](#interruption-and-external-effects)
- [Instructions and knowledge](#instructions-and-knowledge)
- [Evaluation](#evaluation)

## Responsibilities

The agent interprets the commission and sources, chooses the depiction, writes
the rendition, assesses evidence and applies actual authority. The runtime
turns those choices into consistent input files, declared references, exact
requests and recoverable records. A normal task must not require the agent to
read implementation code, reconstruct an internal dependency graph, or repair
generated files to make those responsibilities meet.

| Information | Owner |
| --- | --- |
| Requirements, selected depiction, source authority, intended influence and exclusions | The author, with source evidence and scope |
| Prompt wording, supported controls, independent criteria and result assessment | The author, in their respective roles |
| File placement, attachment positions, content hashes, repeated identifiers and request bindings | The owning builder, derived from selected inputs |
| Submission, capture, cleanup and recovery state | The execution runtime, from actual effects and saved observations |
| Permission and canonical adoption | The relevant authority; no builder or saved file invents a decision |

Independent responsibilities do not require independently retyping the same
fact. Keep each meaningful choice at one editable location and derive or
reference its other representations. Preserve a commission-based review basis
independently of the prompt it judges. Do not generate that basis by treating
the prompt as a successful answer to the commission.

## One editable source across a task

Initial creation, revision and resumption use the same authored contract.
An agent can inspect the current content, change selected choices, and ask the
runtime to build the corresponding task. Drafting from a saved task or run
restores editable content and provenance rather than requiring a new set of
handwritten intermediary documents.

Keep the authored surface appropriate to the task. Show the fields and
selected content that apply, with explicit unresolved choices where necessary.
Do not replace a collection of internal documents with an equally demanding
form containing every possible route's fields. Preserve arbitrary detailed
meaning, literal prompt bytes and model-native values where the contract
supports them; compact authoring does not mean a restricted creative language.

Generated artifacts are inspectable products of the authored input. Give them
stable roles and clear provenance, and keep edits at their owning authored
location. A failure must identify that location and a concrete recovery action.
Adding another report that describes manual coordination does not transfer
responsibility for that coordination to the implementation.

## Changes and dependencies

Recompute deterministic consequences of a changed selection in the owning
builder. Preserve unchanged choices and source evidence. Return unresolved
meaning or authority to the agent without manufacturing a conclusion.
The same rule applies to references, prompt text, direction, criteria,
parameters, rendering, target changes and external requests.

A reference's use, subject scope, source authority and prohibited influence
remain authored decisions. Attachment order, board placement, relative paths
and hashes follow the selected source content. A setting change must not
require a second editable copy of that setting solely to satisfy a downstream
builder. Independently meaningful evidence retains its own purpose and source.

Do not infer semantic consistency with keyword lists, regular expressions or
feature-specific interpretation tables. Mechanical checks can establish
identities, explicit coverage, constraints and content equality. The agent
judges the relationship between changed meaning and the commission.

Keep service-specific requirements within their adapters. A new supported
service must not silently become a requirement for unrelated production work.
Transport choices follow their declared API contract and existing product
dependencies. A local implementation shortcut does not justify expanding the
Skill's scope or installation requirements.

## Context for judgment

At each phase, expose the commission, applicable source material, current
choices, actual model input, unresolved questions and relevant execution state.
Link to complete original documents and actual images from that view. Separate
the model-facing input from its assessment basis when an independent reading
is needed, then make their relationship available for the decision.

Context is a view of existing evidence. It does not certify comprehension,
perform a review, grant permission or require the agent to re-enter established
facts. Do not make the agent reconstruct these relationships by inspecting a
set of internal JSON files. Do not omit necessary knowledge solely to produce
a smaller response.

## Interruption and external effects

Save the current authoring location and its connection to published inputs.
Detect later edits by content, including edits to a draft that has already
been built. A newer draft remains discoverable when an older run exists.
Identify each continuation's purpose so that editing, preparing and recovering
an external operation cannot be confused.

Preserve the operation's durable start, response and capture boundaries.
Resuming an uncertain operation recovers that operation's evidence; it does
not authorize another submission. New authored work can reuse creative input
without inheriting a claim, a result review or exact-request authorization.
An existing grant remains subject to its actual scope rather than being
discarded or broadened merely because the agent changed an input file.

## Instructions and knowledge

Ordinary instructions teach what to understand and decide, which operation
receives the decision, and how to act on its result. Keep ordinary operation specifications and their applicable prerequisites,
authority, constraints, exceptions and recovery instructions together in the
complete documents delivered by the existing route read. Owning references
retain their full bodies in that read. A link, search hit or available source
file alone does not deliver its context, and the agent must not have to search
backward for a caller's restrictions. Page large reads without omitting sources,
return an executable continuation and issue a reading record only after all
pages have been delivered. Implementation-only maintenance details can remain
in their owning maintenance references.

Retain specialized production knowledge at the specificity its uses require.
Before moving or consolidating instructions, examine their dependent uses,
examples, failure cases and explanatory roles. Document length or a passing
test alone is no justification for removal. A recorded read establishes
delivery of source content under its contract, not understanding or correct
application to the current task.

## Evaluation

Assess complete agent tasks from realistic briefs and raw source artifacts.
Cover more than the example that first exposed a problem: new authoring,
changed meaning, reference changes, settings, alternate execution branches,
and recovery at distinct phases. Check that the agent can finish without
editing generated files, inspecting implementation code for normal usage, or
manually propagating one choice into unrelated records.

Use independent agents without implementation history where possible. Retain
their actual commands, edits, diagnostics and results. Repair a demonstrated
interface defect in its owning contract, then exercise the affected task.
Report automated contract checks, observed agent behavior, reading volume and
unverified artistic or live-service behavior separately. Evaluate the actual
reading, search, editing and context-reconstruction work needed to finish the
task; a shorter first read alone establishes no workflow improvement. Measured
time and context consumption describe only the task and environment actually
observed.
