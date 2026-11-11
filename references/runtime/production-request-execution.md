# Prepared request execution

Execute one exact prepared input under its actual authority. The operation reader also delivers [Permissions](production-permissions.md), [Recovery](production-recovery.md), and the full contract for the selected [dispatcher](production-dispatch.md) or [external host](production-external-execution.md).

## Execute the prepared request

```text
python scripts/production_workflow.py draft-execution --root STUDIO --run RUN --out decisions.json
python scripts/production_workflow.py execute --root STUDIO --run RUN --decisions-file decisions.json
```

The saved draft follows `schemas/authoring/production-execution-decisions.schema.json`.
The command response keeps that editing document under `choices`, alongside
`authorization_requirements`, current `authority` and an unapproved
`request_scope_template` when the prepared dispatcher request supports one.
Only `choices` is written to `--out`. The returned execute action names that
exact file.

The requirements list every operation, its complete target set, current grant
candidates and their missing scope. An unanswered grant selector uses its sole
eligible candidate; several eligible candidates remain an explicit choice.
`--grant` selects one grant for all unanswered entries when that is the actual
authority. An explicit selection stays selected even when it is ineligible,
with its diagnostic shown. Coverage does not approve the exact request or fill
judgments. Direction and submission can use one grant when it actually covers
both operations and all their targets.
It contains the generated run and input identities, with one compact entry in `decisions` for each required operation. Each entry selects its grant and contains only its reason, stop-condition assessments and applicable request judgments. Direction and submission remain separate entries and formal events. The full request, exact targets, payloads, actor identities and output counts are derived from the prepared run when execution records those decisions.

Use the `workspace --phase input` view to read the complete model-facing input without the assessment basis, then `workspace --phase decision` to compare that reading with the commission, source roles, current authority and request-review requirements. These views gather material already needed for the decision; they add no approval or read-completion event. Read only context that is missing from the active session. Complete the reasons, stop-condition assessments and final-request assessment from actual evidence.
[Production permissions](production-permissions.md#authorization-and-execution-records) describes each authorization and its `request_decision`.
For the `rendition_review`, first reconstruct the artifact and depicted
situation from the sealed prompt fields, supported controls and actual supplied
images. State which premises and relationships the delivered input establishes.
Then compare that reading with the brief and selected production scope, using
[Prompt assembly and review](prompt-composition.md#prompt-assembly-and-review).
Resolve missing premises and instructions outside the requested depiction in
their owning authored inputs. Record the correspondence and remaining limits
in the existing assessment reasons. The request validator checks the identity,
coverage and author of those assessments; the agent judges their meaning.
A draft has unanswered judgments and grants no permission.
A supplied decision file must cover the complete operation set; altering targets does not narrow the prepared requirement.
With valid exact receipts already recorded, `execute --root STUDIO --run RUN` needs no decision file.

The run owns one complete model input and execution plan, including its handoff recipient and method. Dispatcher work also owns its sealed Generation Package.
Preparation verified that package and rendered its request. `execute` sends them as prepared: reading the run checks every published file against its content hash, and the claim names the package and request by those hashes.
A different parameter, count, model, service, media binding or recipient requires a newly prepared input.
A receipt for another request cannot replace that contract, and a mismatch names the field before an execution claim is committed.

Low-level `authorize` and both execution branches share the same permission and execution-claim implementation.
A request has one claim even when it returns several images.
Use `resume` for recovery, `variant` for changed input, and `repeat` for an intentional additional request.

## Capture the actual result

```text
python scripts/production_workflow.py capture --root STUDIO --run RUN --artifact result.png --note "Origin and limits"
```

Capture preserves exact bytes and inspects the declared medium.
Images must decode, JSON and text must parse, and video or audio needs measured streams from ffprobe.
SVG image evidence uses the same self-contained, inactive content checks and
renderer as reference preparation. Its original bytes remain available as an
image for region observations and the review export.
A dispatcher capture must match its already recorded downloaded results.
An external capture cannot exceed the claimed count, and an identical capture creates no second result.
A media header or probe is a processing check, not evidence of an observed expression or a heard sound.
## Managed next-action drafts during repeated work

`status` names a draft under `production/decisions/RUN/KIND/BASIS_DIGEST.json`, scoped to the exact run, candidate and decision basis. When that draft exists, the next action points to inspection/completion and the appropriate apply command instead of repeating a failing `--out` write. A completed draft is not evidence of approval until the usual validator accepts its actual author evidence. A new review basis gets a different draft; no existing decision file is overwritten.

Every `draft-execution --out` location is registered to its task and run before
publication, including paths outside that folder. Reopening the task, changing
its authority or removing diagnostic logs retains the same editable file.
An interrupted publication returns the registered unused location. When several
files exist, the next action exposes their execute commands for an explicit
selection; it does not silently pick or replace one.

When a decision needs context, `next_action.read_context` names complete
`workspace` commands in reading order. `input` precedes `decision`; candidate-only
`observe` precedes `review`. Acceptance uses the existing review's context and
findings. These are read views, not additional gates or evidence of understanding.
The views retain full actual inputs and relevant source material while keeping
generated facts out of editing fields. They show applicable Skill paths for a
reader whose active context lacks those instructions. A prior reading record
does not establish that a new reader knows them. Execute returned `argv` as given,
and reuse an existing draft instead of creating parallel copies.

The Production run registry resolves the prior run in the **same task and production series at the saved registration boundary**. It does not open every unrelated historical run merely to find that owner. The selected required predecessor is fully verified; a damaged required series run stops protected-criteria use with `PREDECESSOR_UNAVAILABLE`, rather than silently skipping the comparison.

Sheet batching uses the same commands and statuses. [Sheet fills](sheet-fill-workflow.md) adds dated result ownership, frozen batch inputs and discovery. [Studio Runtime](studio.md) documents gallery and timeline recovery; [Operation diagnostics](operation-logs.md) distinguishes auxiliary views from the formal records required before a send.
