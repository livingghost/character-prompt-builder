# Production selection and adoption

Select and adopt actual reviewed artifacts under the requested scope and current authority. Selection, Studio acceptance and canonical reuse remain distinct acts owned by their existing records.

## Select a reviewed result and finish

Use one decision document to select an existing reviewed candidate for delivery:

```sh
python scripts/production_workflow.py draft-acceptance --root STUDIO --run RUN --candidate CANDIDATE --out acceptance.json
python scripts/production_workflow.py accept --root STUDIO --run RUN --file acceptance.json
python scripts/work_ledger.py finish --studio STUDIO --run RUN
```

The draft's default scope is `delivery-only`, for an image, text or other
captured artifact. Use `--scope studio-slot` when the requested result also
accepts the image in its existing Studio slot. Canonical sheet or catalog reuse
has its own [adoption procedure](#adopt-the-selected-image-as-a-reusable-reference).
For directly authored text or JSON, use its saved authored revision and actual
delivery/review requirements; that workflow needs no generated candidate or
selection. [Production workflow](production-workflow.md) describes the authored
completion path.

The [acceptance decision schema](../../schemas/authoring/production-acceptance.schema.json)
holds the choice once. Fill its reason, stop-condition assessments and any
`owner_acceptance` from actual instructions. The run, input and latest review
are pinned by the draft. It selects the sole current grant covering `select`
and `delivery` when there is exactly one; use `--grant GRANT` to choose among
eligible grants. Grant coverage does not assess a stop condition or supply
owner approval.

The runtime derives the actor, evidence hashes, exact authorization payload,
selection and completion records. The authority binding includes the chosen
grant's selection terms, the issuer and source declaration, and current stop
definitions. Unrelated grant edits or changed permissions for another operation
do not reset this decision. Changed selection authority, a source instruction,
stop definition or review needs a current decision; retain
judgments only where their basis still applies. The actual authorization records
the current authority event when the decision is applied.

Every selection binds the candidate, its latest review, every selection field
and the selection it replaces. Its `replaces` field names the run's latest
selection when it is recorded, or is null for the run's first selection; the
runtime derives it, and the exact `select` authorization covers it.
Every hard criterion needs an assessed verdict. A supported `pass` satisfies it;
`fail`, `indeterminate` or `not-applicable` requires the owner's explicit
acceptance of that criterion. A missing or `not-assessed` hard criterion still
needs review and cannot be accepted in place of inspection. Advisory criteria
may remain unassessed, indeterminate or failed with their actual reasons.
Every entry in the selected review's `unresolved` list needs resolution through
a new review or explicit owner acceptance. Retain a nonblocking improvement as
a proposed repair without making its execution a condition of selection.

The required `owner_acceptance` field is null when there are no explicitly
accepted review findings. In the editable decision, a nonnull value contains:

| Field | Decision it records |
|---|---|
| `evidence` | The actual instruction's `path` and `locator`. |
| `criteria` | Unique IDs of assessed nonpass criteria the owner accepts. |
| `unresolved_indices` | Unique zero-based indices into this exact review's `unresolved` list. |
| `reason` | Why the instruction covers those findings for this candidate. |

The acceptance names at least one criterion or unresolved entry. Its coverage
must include every nonpass hard criterion and every unresolved entry; it may
also identify assessed nonpass advisory criteria. Read the actual instruction
and preserve its scope. Recording acceptance leaves the criteria, observations,
verdicts and evaluation unchanged. It authorizes use of this candidate under
this review, without changing a requirement for future work or claiming a
successful repair. The exact `select` authorization binds this decision and its
evidence. The runtime derives `principal` from the current authority issuer and
`evidence.sha256` from the selected instruction's bytes. Those derived fields
belong to the formal selection and exact authorization; the author does not
transcribe them into the compact decision.
[Production permissions](production-permissions.md#current-authority-and-adoption)
owns its current-authority checks. The
[synthetic review cases](../../examples/production-execution/evidence-review-cases.md)
show acceptance beside an unchanged failed review.

The formal selection records the scope and its destination evidence:

| `scope` | Required destination evidence |
|---|---|
| `delivery-only` | `slot` and `adoption` are null; the artifact is selected for delivery. |
| `studio-slot` | `slot` names the exact `character`, `iteration_id` and `slot`; `adoption` is null. Completion also requires the matching Studio acceptance receipt. |
| `studio-adoption` | `adoption` names the completed sheet or catalog adoption; `slot` is null. |

A new selection of a captured candidate checks current authority against the
retained preparation, review and artifact evidence. Completion verifies that
saved selection, its authorization and required destination evidence. Live
creative sources can move or change without making the retained result
unavailable for this decision. Corrupt or missing retained bytes still block it.
A new preparation or execution keeps its live-source requirements. A finished
run keeps the selection and scope recorded in its completion. A later prompt
revision, source edit, disposition or separately authorized use preserves that
earlier completion. New creative work uses a new run; recovery of the completed
result does not reopen the earlier task or regenerate its artifact.

`accept` returns the exact selection and completion, scope and owning task. Its
`work` view lists unfinished steps, open questions and any block, and reports
whether that task is ready to finish. `finish_command` names the owning run.
The result reports a completed production decision separately from a finished
work task. It records no step or answer on the author's behalf.

After selection commits, recover an interrupted decision with:

```sh
python scripts/production_workflow.py accept --root STUDIO --run RUN
```

Recovery uses the saved selection and retained evidence. Before selection is
recorded, supply the completed decision file. Repetition verifies the existing
completion or completes the same pending selection; it creates no new run,
candidate, review or iteration and records no replacement decision. Supplying
the decision file of that selection again does the same.

A decision whose selection is no longer in force is a new decision. When a
later selection replaced the one a decision file recorded, or a later
disposition of its candidate withdrew it, `accept --file` with the same file
records a new selection that replaces the run's latest one, under its own
authorization, and completes it; nothing new is authored. Its review must still
be the candidate's latest. A newer review, which also ends the selection the
file recorded, makes `accept --file` refuse the file with
`SELECTION_REVIEW_CHANGED`; its `required_action` gives the `draft-acceptance`
command that drafts a decision against the latest review. A `studio-slot`
decision still needs its drafted slot state. A completed run accepts no new
selection.

`finish --run RUN` closes the exact owning task after the ordinary checks on
actual steps, answered questions and completion evidence. It can finish a
suspended owning task while leaving another active task unchanged. Use the
owning task's normal workflow when work remains. A closed owning task and its
result remain available when a later request begins another work task.

### Accept an existing candidate for its Studio slot

Use the original Production run and candidate when the owner chooses an existing
reviewed image for its slot:

```sh
python scripts/production_workflow.py draft-acceptance --root STUDIO --run RUN --candidate CANDIDATE --scope studio-slot --grant GRANT --out acceptance.json
python scripts/production_workflow.py accept --root STUDIO --run RUN --file acceptance.json
python scripts/work_ledger.py finish --studio STUDIO --run RUN
```

The same compact decision additionally pins the current slot state. The runtime
derives the exact Studio destination from the candidate's existing recording
and verifies its actual bytes. It checks the decision before
recording an exact select authorization, selection, Studio acceptance receipt
and run completion. The original candidate bytes, iteration, review and work
task remain the owners; acceptance needs no new generation, import, capture or
criteria definition.

The result additionally identifies the slot-acceptance receipt and exact slot.
A separate `studio-slot` selection made through the granular selection commands
uses the same acceptance and completion path.

Repeating `accept --run RUN` does not create another iteration or supersede a
different slot decision made since it was authorized. Inspect a reported
conflict before continuing. When another selection of the candidate is
recorded while `accept` applies a decision, the Studio refuses the slot
acceptance with `SLOT_ACCEPTANCE_MISMATCH`: `accept --run RUN` resumes that
selection in its own scope, and `accept --run RUN --file FILE` with the same
decision file records it again as a new selection that replaces it.

The Studio owns the durable slot receipt. Recovery checks that receipt before
completing the run. An ordinary later replacement of the slot preserves the
earlier completion and its recorded acceptance history.

### Explicit selection and canonical scope

The lower-level selection operations remain available for exact separately
authored intents, including a selection that cites an already completed
canonical adoption:

```text
python scripts/production_workflow.py draft-selection --root STUDIO --run RUN --candidate CANDIDATE --out selection.json
python scripts/production_workflow.py selection-intent --root STUDIO --run RUN --file selection.json
python scripts/production_workflow.py select --root STUDIO --run RUN --file selection.json
python scripts/production_workflow.py complete --root STUDIO --run RUN
```

Fill the formal selector, reason and selected scope, then authorize the printed
`select` intent as [Production permissions](production-permissions.md) describes.
Put the authorization event digest in `selection.authorization` before `select`.
`draft-selection` fills `replaces` with the run's latest selection. When another
selection is recorded before this file is applied, `select` refuses it with
`SELECTION_REPLACED`; draft, authorize and select again. Applying the file of
the run's latest selection again returns that selection.
The formal `owner_acceptance`, when present, includes the current authority
issuer in `principal` and the instruction's exact `path`, `sha256` and `locator`
in `evidence`. The compact decision path derives these same formal fields.
Both paths use the same selection, permission and completion owners.

### Adopt the selected image as a reusable reference

Use this procedure when the requested result includes sheet or catalog reuse.
It has its own approval and authorization, and applies to the existing selected
candidate of an open, completed or abandoned run. Completion fixes the result
and scope of the production decision. Later adoption records another use of
those retained bytes, with its own exact current authority.

1. Use the run's existing current selection. For an open run without one,
   select the candidate with `scope: delivery-only`.
2. Run `adoption-intent`, then `adopt` under its own `adopt` authorization; the Studio accepts the iteration in this step. `adopt` refuses a candidate that is not the run's current selection (`SELECTION_REQUIRED`).
3. For an open run, optionally select the same candidate with
   `scope: studio-adoption`, citing the adoption record and retaining any
   applicable owner acceptance. It needs the run's own adoption result. When
   the adoption stopped before the run recorded its result,
   `ADOPTION_RESULT_MISSING` gives the `adopt` command of that adoption;
   repeating it finishes the adoption and records the result.
4. Complete an open run's selected scope. A completed or abandoned run keeps
   its original selection, completion or abandonment and owning task state.

The adoption authorization, claim, local operation boundary and result append
to the existing event chain. They identify the same candidate and review and
do not create another execution or iteration. Current grant scope, actor,
expiry, revocation and stop assessments apply at authorization and adoption.
Use `authority-import` for an actual change in the authority declaration.
A candidate without a valid current selection needs that decision before the
production task closes; closing a task supplies no missing review or selection.

Retry an interrupted adoption with the same exact approval, authorization and
destination. A subsequent catalog registration uses a new catalog approval and
authorization while retaining the initial sheet decision. A registration that
stopped after writing its pack keeps that pack when it resumes, because the
pack's adoption receipt names the same approval and Studio. Completion verification
uses the adoption evidence captured for its selected scope; a later registration
or ordinary replacement does not rewrite what the earlier run completed.

The Studio keeps each adoption's record in
`characters/CHARACTER/adoptions/ITERATION.json`, and the run keeps the same
content as the result of that adoption. The record agrees with the run when it
is the latest adoption result the run records for the iteration, or when a
later adoption claim of the iteration wrote it and that claim has no result yet.
Repeating a completed `adopt` with the same approval and authorization adopts
nothing again: it returns the recorded result, and when the record is missing,
unreadable, malformed or disagrees with the run, it writes the record again
from the latest result. A record that agrees is left as it is; a later adoption
of another candidate writes its own record. The repetition needs the run's
current selection of the candidate and a current grant, as the adoption did;
the Studio eligibility checks that come before an adoption do not apply to it.

A reader of a current or pending adoption that finds the record missing,
malformed or in disagreement with the run reports `ADOPTION_RECORD_CORRUPT`
with the `adopt` command of the latest completed adoption in `required_action`:
`studio_reference.py`, status, `adoption-intent`, a new or resumed `adopt` and a
`studio-adoption` selection. A later adoption continues from the record, so
once the run records an adoption result, `adoption-intent` and `adopt` refuse a
missing record in the same way and change nothing until it is written again.
Once it is, a catalog registration that stopped before the record was lost
resumes with its own `adopt` command.

`adoption-intent` and `adopt` take `--candidate`, `--character`, `--iteration` and `--approval`.
`adopt` also takes `--authorization`, the event digest of its adopt authorization.
A catalog adoption adds `--registration-record`, `--pack-dir` and the same explicit pack runtime arguments as the owner.
An imported iteration belongs to `studio.py accept` for slot acceptance and
`adoption_workflow.py adopt` for sheet or catalog adoption. Production
`adoption-intent` identifies that ownership before creating an adoption claim.

A run has at most one current selection:

- `select` refuses another candidate while one holds it (`SELECTION_CONFLICT`).
- A later selection of the same candidate replaces the current one and names it in `replaces`.
- A disposition (`not_selected` or `pending`) of the selected candidate withdraws its selection explicitly; `studio.py reject` records the same disposition.
- Both refuse the withdrawal while the Studio holds that candidate as the slot's accepted image (`SELECTED_CANDIDATE`). Accepting another image for the slot first lifts the refusal.
- A newer review of the selected candidate also ends its selection, without a disposition.

`complete` verifies the current selection and its required destination evidence.
`work_ledger.py finish --studio STUDIO --run RUN` checks the named run's
completion and its owning task's actual steps and questions.
Preparations, generated images, draft reviews or a task with no selected artifact are not finished production.

`review`, `disposition`, `select`, `accept`, `complete` and `adopt` update the Studio gallery; [Studio Runtime](studio.md#every-image-with-what-produced-it) covers a failed rewrite.
