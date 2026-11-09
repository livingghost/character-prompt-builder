# Production selection and adoption

Select and adopt actual reviewed artifacts under the requested scope and current authority. Selection, Studio acceptance and canonical reuse remain distinct acts owned by their existing records.

## Select, optionally adopt, and finish

```text
python scripts/production_workflow.py draft-selection --root STUDIO --run RUN --candidate CANDIDATE --out selection.json
python scripts/production_workflow.py selection-intent --root STUDIO --run RUN --file selection.json
python scripts/production_workflow.py select --root STUDIO --run RUN --file selection.json
python scripts/production_workflow.py complete --root STUDIO --run RUN
```

Fill the selector and reason, then authorize the printed `select` intent as [Production permissions](production-permissions.md) describes.
Put the authorization event digest in `selection.authorization` before `select`.
A selection binds the candidate, its latest review and every selection field.
Every hard criterion needs an assessed verdict. A supported `pass` satisfies it;
`fail`, `indeterminate` or `not-applicable` requires the owner's explicit
acceptance of that criterion. A missing or `not-assessed` hard criterion still
needs review and cannot be accepted in place of inspection. Advisory criteria
may remain unassessed, indeterminate or failed with their actual reasons.
Every entry in the selected review's `unresolved` list needs resolution through
a new review or explicit owner acceptance. Retain a nonblocking improvement as
a proposed repair without making its execution a condition of selection.

The required `owner_acceptance` field is null when there are no explicitly
accepted review findings. A nonnull value contains:

| Field | Decision it records |
|---|---|
| `principal` | The current authority issuer whose instruction accepts the candidate. |
| `evidence` | The instruction's exact `path`, `sha256` and `locator`. |
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
evidence. [Production permissions](production-permissions.md#current-authority-and-adoption)
owns its current-authority checks. The
[synthetic review cases](../../examples/production-execution/evidence-review-cases.md)
show acceptance beside an unchanged failed review.

Choose the selection scope for the result being recorded:

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
A new preparation or execution keeps its live-source requirements.

### Accept an existing candidate for its Studio slot

Use the original Production run and candidate when the owner chooses an existing
reviewed image for its slot:

```sh
python scripts/production_workflow.py draft-acceptance --root STUDIO --run RUN --candidate CANDIDATE --grant GRANT --out acceptance.json
python scripts/production_workflow.py accept --root STUDIO --run RUN --file acceptance.json
python scripts/work_ledger.py finish --studio STUDIO --run RUN
```

The compact draft follows the
[acceptance decision schema](../../schemas/authoring/production-acceptance.schema.json)
and pins the run, input, candidate, review and current slot state.
Fill its reason, stop-condition assessments and any `owner_acceptance` from the
actual instruction. In this editing document, the acceptance selects its evidence
path and locator, criterion IDs, unresolved indices and reason. The runtime
derives the principal, evidence hash, selector and exact Studio destination from
the current authority and existing records. It checks the decision before
recording an exact select authorization, selection, Studio acceptance receipt
and run completion. The original candidate bytes, iteration, review and work
task remain the owners; acceptance needs no new generation, import, capture or
criteria definition.

The result identifies the selection, slot-acceptance and completion receipts,
the exact slot and owning task, and a `finish_command` for that run. A separate
`studio-slot` selection made through the granular selection commands uses the
same acceptance and completion path.

After selection commits, resume an interrupted acceptance with:

```sh
python scripts/production_workflow.py accept --root STUDIO --run RUN
```

Recovery uses that saved decision and its evidence. Before a selection has been
recorded, supply the completed decision file. Repeating `accept --run RUN` does
not create another iteration or supersede a different slot decision made since
it was authorized. Inspect a reported conflict before continuing.

Acceptance completes the run, then `finish --run RUN` closes its exact owning
work task after the ordinary checks on actual steps, answered questions and
completion evidence. It can close a suspended owning task while leaving another
active task unchanged. It does not mark steps done or answer questions. Use the
owning task's normal workflow when such work remains.

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
   applicable owner acceptance. It needs the run's own adoption result
   (`ADOPTION_RESULT_MISSING` otherwise).
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
authorization while retaining the initial sheet decision. Completion verification
uses the adoption evidence captured for its selected scope; a later registration
or ordinary replacement does not rewrite what the earlier run completed.

`adoption-intent` and `adopt` take `--candidate`, `--character`, `--iteration` and `--approval`.
`adopt` also takes `--authorization`, the event digest of its adopt authorization.
A catalog adoption adds `--registration-record`, `--pack-dir` and the same explicit pack runtime arguments as the owner.
An imported iteration belongs to `studio.py accept` for slot acceptance and
`adoption_workflow.py adopt` for sheet or catalog adoption. Production
`adoption-intent` identifies that ownership before creating an adoption claim.

A run has at most one current selection:

- `select` refuses another candidate while one holds it (`SELECTION_CONFLICT`).
- A disposition (`not_selected` or `pending`) of the selected candidate withdraws its selection explicitly; `studio.py reject` records the same disposition.
- Both refuse the withdrawal while the Studio holds that candidate as the slot's accepted image (`SELECTED_CANDIDATE`). Accepting another image for the slot first lifts the refusal.
- A newer review of the selected candidate also ends its selection, without a disposition.

`complete` verifies the current selection and its required destination evidence.
`work_ledger.py finish --studio STUDIO --run RUN` checks the named run's
completion and its owning task's actual steps and questions.
Preparations, generated images, draft reviews or a task with no selected artifact are not finished production.

`review`, `disposition`, `select`, `accept`, `complete` and `adopt` update the Studio gallery; [Studio Runtime](studio.md#every-image-with-what-produced-it) covers a failed rewrite.
