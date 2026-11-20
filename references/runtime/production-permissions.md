# Production permissions

A task points to an `authority` JSON file following
`schemas/authoring/production-authority.schema.json`. Its issuer and evidence
path/locator identify the instruction whose bytes are pinned during preparation.
The host checks real user authority: a schema authenticates no issuer and an
agent-filled form is not consent.

Each grant names an id, actor, direct/delegated mode, allowed operations, exact
targets, protected criteria, optional request scope, submission validation modes,
and expiry/effective/revocation timestamps. Direction, edit, submit, select and
adopt are independent operations. Permission to submit is not canonical adoption
or permission to change personality. Permission to select is not permission for
another submission. Stop outside the stated scope or on ambiguous conditions.

Targets are exact strings: `purpose`, `decision:<id>`, `delivery`, `canon:sheet`,
`canon:catalog`, and changed `source:<id>`, `criterion:<id>`, `execution` or
`authority` scopes. Grant only necessary targets. Calling a repair a local edit
does not exempt its changed sources or protected criteria.

## Protected criteria across runs

A grant's `protected_criteria` names criterion ids whose complete definitions
must stay identical to the comparison run. Direction compares the new run with
the previous registered run in the same work task and `production_id`; an edit
compares its revised task with the parent run. Added and removed protected ids
also differ. The first run of a production series has no earlier comparison.

Choose these invariants from the actual instruction. `task.criteria` continues
to hold the intended hard and advisory review requirements. A hard criterion can
change under explicit authority and remain a hard review requirement of the new
run. Its changed definition cannot at the same time satisfy a grant requiring
that id to stay identical. Scripts compare the declared values; they do not
interpret an instruction or choose the protection scope.

`workspace --phase decision`, `draft-execution`, `draft-authority-update` and
unsent-run status expose the same comparison in
`authorization_requirements.protected_criteria`. The report names the comparison
run, production series, changed ids and their exact before/after values. Grant
eligibility includes this constraint. A conflicting selected grant reports its
actual declaration field and the public authority update action.

When an existing actual instruction authorizes a change, use that evidence to
author the corresponding grant terms. The run-bound additional-grant draft
preserves every existing grant and records a separate selection; choose its
`protected_criteria` from the invariants the instruction still requires, import
it with the observed predecessor, and select that grant for the affected
operation. A complete current-authority declaration can also record a supported
change to existing grant terms. Follow the report's update action for that
owner. Keep the new task's hard review requirements and every saved run intact.
An already imported compact addition is retained evidence: draft a new update
against current authority for another change.

## Authorization and execution records

```text
python scripts/production_workflow.py draft-authorization --root STUDIO --run RUN --grant GRANT --intent intent.json --out authorization.json
python scripts/production_workflow.py authorize --root STUDIO --run RUN --file authorization.json
```

`handoff-intent` or `selection-intent` prints the exact intent to save.
`draft-authorization` leaves reasons and stop assessments unapproved. Fill them
from actual evidence. `authorize` validates current authority and records a
receipt, including the protected criteria and their digest. It performs no send.
The consuming operation checks the exact payload, actor, targets, scope, expiry,
revocation and current authority again. Scalar types and ordered array elements
are compared as well as object fields; a boolean is not an authorized number.

A dispatcher submission carries `request_decision`:

- `case`: a declared request-scope case, or null.
- `assessments`: each case criterion, exact request hash, satisfied conclusion
  and actual reason.
- `principal_approval`: the exact request hash, principal and
  `evidence{path,sha256,locator}`, or null when a delegated case applies.
- `rendition_review`: exact input hash, reviewer, transported reference binding
  IDs and the author's three meaning assessments below.

Dispatcher and external image submissions use this same `rendition_review`.
Its `input_sha256` is the dispatcher request hash or the external image-input
binding hash. `reviewer` equals the authorized actor, and `binding_ids` names
every transported logical reference, including uses sharing one attachment.
Its `assessments` contains one conclusion and reason for each criterion:

- `finished-image`: read back the complete input and compare its qualities,
  degree, relationships and finish with the author's anchors. Identify how text
  and supplied media establish that target beyond satisfying exclusions. Explain
  how actions, visibility and exclusions coexist within their actual scopes.
  Resolve missing anchors, weakened intent and conflicts under the composition's
  source authority before marking it satisfied.
- `supplied-inputs`: subjects and reference uses resolve from the delivered text
  and actual images; a reference-free request invents no supplied source.
- `ownership`: prompt text carries depiction and necessary image-use directions;
  production IDs, provenance, decisions, grading and native settings keep their
  existing record or request-field owners.

Record `not-satisfied` for a missing anchor, weakened intent or contradiction,
and `unmeasured` when evidence or interpretation remains insufficient.
Both prevent submission. Repair the input
within authority, prepare it again and assess the resulting exact input.
A request can proceed only when every conclusion is `satisfied` with an explicit
reason grounded in that input. Repeating a criterion or citing a passing checker
does not perform the judgment. The validator checks attribution, coverage and
input integrity; it cannot establish whether the author's reasoning is true.

Binding IDs retain their exact delivery order. An external image submission's
`request_decision` contains only this `rendition_review`; its ordinary outer
authorization grants the exact operation.

`draft-execution` produces one compact editing document for dispatcher and
external image execution. Its `decisions` keep direction and submission separate.
Select grants and write each operation's reason and request judgments. Author a
common stop judgment once in `shared_stop_assessments`. Each decision's
`additional_stop_assessments` adds judgments or replaces the complete shared
judgment with the same id for that operation. Duplicate ids within either list
are refused. An operation-specific `clear: false` therefore blocks that
operation even when the shared judgment is clear; it does not inherit the
shared evidence or approval. Every formal authorization retains its own complete
`stop_assessments` and passes the ordinary current-condition check.

For example, a synthetic shared assessment for `single-trial` can say
`{"id":"single-trial","clear":true,"evidence":"Synthetic instruction permits this trial."}`.
If submission needs separate evidence, put its complete replacement in the
submission decision's `additional_stop_assessments`; direction keeps the shared
assessment. Drafts leave `clear` false and evidence empty. Their derived
`stop_conditions_sha256` identifies the actual condition definitions. A changed
definition, including changed text under the same id, requires reassessment.
Do not update only that digest to reuse an earlier judgment.
Consuming a recorded authorization also compares the stop definitions of its
recorded authority event with current authority before an external step. A
later authority event with unchanged definitions remains usable; changed text
under the same id requires a new assessment. The old receipt stays unchanged.
An existing claim retains its original authorizations and cannot be repurposed
to send again after the condition changes.

Exact payloads, actors, counts and review hashes are derived from the prepared
input when execution records the separate authorizations. For a dispatcher
principal approval, select only its actual evidence `path` and `locator`; the
runtime measures the bytes and binds the current issuer and exact request.
Scope assessment entries contain criterion, conclusion and reason. The editing
`rendition_review` contains its assessments; the runtime supplies the exact
input and reference identities in the formal record.

Before execution, `workspace --phase decision`, `status` and `draft-execution`
expose `authorization_requirements`: each operation and all required targets,
candidate grants, missing targets and current eligibility. These use the same
grant check as execution. Resolve all named gaps from the actual issuer's
authority while preserving the requested work and already applicable choices.
A unique eligible grant can fill an unanswered selector; that mechanical choice
does not approve the request, choose a delegation case or assess any condition.

For a dispatcher request, `request_scope_template` supplies the complete current
scope shape from the exact prepared target, execution hashes and fixed fields.
Its state is `unapproved`; source path and locator remain unanswered. Use it
only where the actual instruction delegates that scope. Its linked
`schemas/authoring/request-scope.schema.json` describes fixed fields, finite or
numeric variations, authored-content sources and review criteria. The author
selects the actual source and authorized variations. Acquisition derives omitted
source hashes from those bytes, checks any supplied hash and stores complete
canonical references. Editing a source does not silently repin an existing
registered authority. The template is separate from both the current authority
and the execution choices and is never imported automatically.

Use the input workspace before the decision workspace to reconstruct the actual request, then compare it with the source commission and authority. Inspect the complete references, controls and `execution_plan.prompt_check` before approving. Draft assessments have null conclusions and empty reasons. Structural
checks and dictionary evidence cannot fill them. An unscoped dispatcher request
needs principal approval; a scoped delegation needs satisfied assessments.
`GRANT_SCOPE_EXCEEDED` names
missing targets and the current granted set without narrowing the requested work.

An execution claim records the unique owner of an authorized submission. The
owner, request hash and requested output count are durable before external I/O.
Each upload and send has a unique step, committed immediately before I/O after
saved request, media, runtime, current authority and transport implementation checks. One execution can start its
send only once. A transport wait holds no Studio transaction.

The exact per-request count remains part of the sealed request and is checked
against model capabilities. Execution authorization does not contain cumulative
monetary, send-count or image-count limits. Tasks contain no predicted-cost
conditions. Provider pricing does not decide whether approved work can proceed.

## Result capture and recovery

Every external step retains its provider identifier, response and optional
usage. Each acquired image and its native dimensions/hash are recorded even if
another output has not arrived. Execution results record actual submission and
captured-image counts. Missing usage remains unknown; it is never replaced with
zero and never prevents image recovery or execution completion.

`status` includes `execution_records`, whose `submissions`, `captured_outputs`,
`reported_cost` and `usage_complete` are projections of formal events. Known final
provider charges are added exactly once per currency using decimal strings.
These are retrospective records, not quotas or permission. The same records can
be filtered to a run without rewriting Studio history.

`resume` reuses the same claim. It recovers saved answers and missing outputs,
reuses completed uploads within that execution, checks the provider's recorded
outcome, or completes deletion of that execution's uploaded inputs. The exact
submission scope includes those deletions when the selected transport supports
them. Cleanup uses the owned upload receipts after a terminal result and output
capture, or after an upload that stopped the execution before its send; it does
not reopen submission or require a new generation approval.
Every new generation uploads its inputs anew. Recovery never
resends a started request. A timeout, disconnect or missing image is not evidence
that the provider did nothing. `draft-outcome` leaves an evidenced `not_executed`
statement for an authorized actor when the provider's own records establish that
outcome. A new request requires a distinct preparation and authorization.
Abandoning a task neither deletes the execution nor resolves an unknown outcome.

Input changes require a current preparation. A changed service, package, seed,
count, selected reference, selection reason or recipient needs a matching
approval. Receipts are integrity records, not cryptographic user signatures.
Leave run evidence unedited. Calls outside the recorded execution cannot be
inferred by the runtime and must be explicitly recorded by the host.

## Current authority and adoption

A prepared input does not pin the mutable grant declaration or a whole work
ledger tail. Evidence is captured with its path, hash, locator, time and purpose;
a later ledger append does not invalidate an earlier reading.
`authority-import --root STUDIO --file FILE --expected-event EVENT` records a real
authority update and its predecessor. Revocation is checked again at every new
external boundary. Updating authority does not authorize different request bytes.

The decision and status views expose `authority.document`, its `source_path`,
the current `event_sha256` and an `update_action` containing the exact predecessor
argument. Edit that declaration from the actual instruction and use the returned
action. A concurrent authority change requires another inspection and
reconciliation; no `current` shortcut replaces the observed predecessor.

### Retain a direct instruction for one request

Use the actual instruction file when a dispatcher request needs exact principal
approval. The actor is the instruction's actual speaker and must equal this work
task's current issuer. Existing explicit instruction can supply the decision;
the command introduces no additional user confirmation.

```text
python scripts/production_workflow.py draft-principal-approval --root STUDIO --run RUN --instruction-file instruction.txt --actor "ACTUAL_ISSUER" --out approval.json
```

The [principal approval schema](../../schemas/authoring/production-principal-approval.schema.json)
keeps the literal UTF-8 text in `instruction.text`, with its source path and byte
digest. Leading spaces, Unicode and line endings are preserved. Empty or invalid
UTF-8 input is refused. The `binding` derives task, run, exact input and request
hashes, target model/service and transported reference/media bindings from the
saved run. It remains separate from `approval`, whose `approved` is initially
null and whose `scope` is empty. The retained text is not replaced by a summary.

After interpreting the real instruction, fill those approval fields only within
its actual scope. The retained instruction is available even when the original
file moves. Select the completed file as
`{"path":"approval.json","locator":"whole"}` in the dispatcher submission's
`principal_approval`. Import and execution refuse an unanswered, declined,
different-run or mismatched structured approval. The same checks use captured
evidence at later execution boundaries. A hash authenticates neither the speaker
nor the words' meaning. Ordinary evidence files remain supported for instructions
already recorded in another format.

### Add authority for a prepared run

```text
python scripts/production_workflow.py draft-authority-update --root STUDIO --run RUN --approval-evidence approval.json --out authority-update.json
python scripts/production_workflow.py authority-import --root STUDIO --file authority-update.json --expected-event EVENT
```

The first command writes a draft and prints the exact observed `expected_event`
for the second command. The [authority update schema](../../schemas/authoring/production-authority-update.schema.json)
contains only new grants and optional `additional_stop_conditions`. The current
issuer, work task, run, prepared input/request, operation order and required
targets are derived. Direction and submission receive separate grant entries.
The actual actor, direct/delegated mode, permission reason and permitted
submission validation modes remain unanswered. The report shows the mode this
request needs and the current stop definitions; select that mode only where the
instruction allows it. An optional request scope retains its ordinary delegated
scope contract. The drafting operation never imports or activates these grants.

### Add authority for a reviewed selection

For authority to select an already reviewed candidate, name that operation and
candidate explicitly:

```text
python scripts/production_workflow.py draft-authority-update --root STUDIO --run RUN --phase selection --candidate CANDIDATE --approval-evidence actual-choice.txt --out selection-authority-update.json
```

The default `--phase execution` still derives direction and submission. The
selection phase uses the existing selection owner to derive only `select` with
the `delivery` target. It requires a recorded review with the hard criteria
assessed, and pins the candidate, latest review and selection it would replace.
Import refuses a changed basis; inspect the changed review or selection and
draft again if the actual instruction still supports it. A nonpassing assessed
criterion remains nonpassing: its explicit owner allowance belongs to the later
selection decision. Neither a grant draft nor its import supplies that allowance,
selects an image, approves an actor or completes the work.

When no current grant covers selection, status and the `draft-acceptance`
diagnostic provide this candidate-specific drafting action. Complete its actual
instruction evidence, actor, direct/delegated mode and reason, follow its
`authority-import` action, then inspect status for the acceptance decision. This
grant covers the selection operation and `delivery` target within its work task;
the actual selection authorization still binds the exact reviewed candidate and
decision. The draft's candidate binding does not create a new candidate-limited
grant format. Authority to adopt the selected image has its own draft below.

### Add authority for selected canonical use

When the actual instruction approves canonical reuse but no current grant covers
it, draft that operation from the run's current selection:

```text
python scripts/production_workflow.py draft-authority-update --root STUDIO --run RUN --phase adoption --scope sheet --influence identity --out adoption-authority-update.json
```

The adoption owner derives the candidate, latest selected review, selection,
character, iteration, image, effective slot and destination state. Scope and
influence state the intended reuse. Sheet scope derives `adopt` and
`canon:sheet`; catalog scope derives `adopt` and `canon:catalog` and also takes
`--registration-record RECORD --pack-dir DESTINATION`. The existing catalog
owner checks the record and binds its exact content and destination. An optional
`--candidate` verifies the explicitly selected image; it never selects another
candidate. The current issuer, run, input/request and authority predecessor are
derived in the same way as other authority updates.

Actor, direct/delegated mode, actual instruction evidence and the new grant's
reason remain unanswered. Complete those choices from the actual instruction.
The resulting grant does not supply canonical approval, selection, an owner
allowance or a stop assessment. Import rechecks the retained candidate, review,
current selection and complete destination state through the adoption owner and
compares both authority predecessors. A changed basis needs a fresh draft.

`draft-adoption` reports this exact drafting action when the required grant is
missing. Follow its `authority-import` action after authoring the actual
permission; the import returns the matching `draft-adoption` action with the new
grant and destination already selected. These operations create no generation,
upload, send, candidate or iteration. An instruction covering both slot selection
and sheet reuse can be cited for both grants, while each operation retains its
own grant, reason, authorization and decision evidence.

After interruption, `status --run RUN` recovers the matching `draft-adoption`
action from this run's current imported authority source when no matching draft
or retained claim owns that use yet. Existing drafts and claims keep their own
recovery actions. The authority's update action also retains the imported phase,
candidate, scope, influence and catalog destination for this run; it does not
silently return a canonical-use update to execution authority.

### Import a run-bound authority update

`--approval-evidence` may select the completed structured approval above or an
existing actual instruction file. Omitting it leaves evidence unanswered and
prevents import. A selected file's digest pins the acquired revision; changing
that evidence requires a new draft from the revised instruction. The host judges
the evidence and fills each grant's reason from the actual instruction. A
nonempty file, completed form or derived target alone establishes no consent.

Import checks the command's `--expected-event` and the draft's `expected_event`
against the same current event within its transaction. It preserves every
existing grant and stop definition, including revocations and captured scope
evidence, and refuses a new grant that reuses an existing id. It derives the
complete declaration and stores the compact source with its authored reasons as
evidence. Editing the issuer or required targets cannot change their derived
meaning. Another authority update requires inspection and a new draft; changing
the command's predecessor alone cannot rebase an old decision. Status supplies
that new drafting action after a compact update has been imported.

The complete `production-authority.schema.json` declaration and its ordinary
`authority-import` remain available for an actual change to existing grants or
stop definitions. Its issuer and predecessor checks still apply. The import
result can report added, updated, revoked and removed grant ids; that display
does not modify the formal event. Use
`production_document_contracts.py explain authority_update` or
`production_document_contracts.py explain principal_approval` for the fields,
and its `validate` command for a shape check. Actual evidence and current
authority are checked only by their owning import or execution operation.

An edit of the authority file takes effect only through `authority-import`:
`draft-execution`, `execute` and `status` read the imported authority. When the
file of the latest import now differs from the bytes that import recorded,
`authority.source_edited` gives its path and both digests and the update action
says so. An unsent run then also reports the warning
`AUTHORITY_SOURCE_NOT_IMPORTED`, and an authorization that `execute` refuses
names the unimported edit ahead of its own repair. Import the edit when it
records an actual authority change, then draft the execution decisions again;
the stop assessments of a draft follow the imported stop conditions.

A review repair binds its changed creative scopes and revised input hash. An
authority-only update is separate from a creative variant, and a revoked grant
stops consumption of an edit receipt as `GRANT_REVOKED`.

### Stored decisions and current authority

A new selection of a captured candidate uses its retained preparation, review
and artifact evidence together with current authority. Completion and recovery
verify that saved selection, its authorization and required destination evidence.
They do not renew an already recorded decision or require live creative sources
to remain at their original paths. Missing or corrupt retained evidence still
blocks them. New preparation acquires its selected sources. Execution of an
already prepared run consumes that saved revision and current imported
authority; edits or removal of its original authoring files are not a new
authorization decision and do not block it.

The selection's nullable `owner_acceptance` records an explicit decision by the
current authority issuer to use the candidate despite identified assessed
departures or unresolved matters. Its evidence path, hash and locator identify
the actual instruction. The host checks that instruction and its scope; an
agent-filled acceptance form establishes no consent. Every nonpass hard
criterion and unresolved entry must be covered, and an unassessed hard criterion
cannot be accepted in place of review. The authorization pins the evidence bytes
and the complete selection payload, including its candidate, exact review,
acceptance, destination and the selection it replaces. Later changes to the live
evidence file cannot rewrite that saved decision.

### Studio slot selection authority

A `studio-slot` selection uses the `select` operation and `delivery` target to
authorize acceptance of the exact recorded iteration for its slot. Its compact
`draft-acceptance` and `accept` operations derive the formal identifiers and
record the selection, Studio acceptance and completion separately. The criterion
definitions remain unchanged, so accepting an assessed departure needs no
criterion-target amendment. The authority to change criteria or submit another
request remains separate.

### Canonical adoption authority

Canonical adoption requires the owner's explicit approval plus its own `adopt`
authorization. The operation can use the existing selected candidate of a
completed or abandoned run with current authority. The source task stays closed;
its selection and review remain the evidence for that candidate. New production
decisions and submissions keep their own lifecycle and permissions. Follow
selection, adoption and completion in
[Production execution](production-adoption.md#select-a-reviewed-result-and-finish).
The sheet stores the selected immutable image and provenance together; candidates
and historical selections cannot silently replace the current image.

### Reuse stop judgments for the same selected image

The compact acceptance decision authors each stop judgment once. Its exact
selection authorization retains the complete `stop_assessments` under its own
grant and actual instruction. A later adoption draft can propose those judgments
in `shared_stop_assessments` when the current selection has the same reviewed
candidate and exact Studio slot, the select terms and stop definitions are
unchanged, and the retained instruction evidence is identical. A delivery-only
selection has no prior slot judgment to reuse. When these conditions do not
match, the draft leaves `shared_stop_assessments` null and gives every current
condition as an unanswered `additional_stop_assessments` entry.

A shared proposal shows its source `authorization`, `authority_event`, full
`basis` and original `assessments`. Its `confirmed` value starts at null. The
acting author reads that evidence and the intended canonical use and sets
`confirmed` to true only when the judgments apply. This is the author's existing
evidence assessment; the command requires no additional conversation with the
owner when the actual instruction already settles it. The proposal supplies no
adopt permission or canonical approval. Fill the adoption's own `reason`, `at`
and any required continuity decision separately.

Use `additional_stop_assessments` for an adoption-specific judgment. Each entry
contains the actual `id`, `condition`, `clear` and `evidence`, and replaces the
complete shared judgment with the same id. For example, the following synthetic
entry keeps an adoption blocked even when the selection's judgment was clear:

```json
{"id":"actual-scope","condition":"Stop if the instruction does not cover this use.","clear":false,"evidence":"The synthetic operator has not settled canonical reuse."}
```

Keep the condition text supplied by the actual draft. Duplicate ids in either
list are refused. Missing, false or unanswered judgments remain unresolved. The
shared proposal's source judgments are derived values; author a complete
operation-specific replacement in the additional list instead of editing the
retained source evidence. Setting `shared_stop_assessments` to null removes those
judgments and requires complete current assessments in the additional list.

The single owner, `scripts/production_curation_assessments.py`, checks the saved
selection authorization, its captured instruction bytes, current stop text,
selection terms, adoption terms, candidate, review, selection, destination,
scope, influence and catalog registration before expanding the proposal. Its
full basis remains bound to those observations. Updating only a digest cannot
rebase old judgments. The formal adoption authorization stores the resulting
complete stop assessments and passes the ordinary permission checks; the earlier
selection authorization and its evidence stay unchanged. A later authority
reassessment of an existing adoption claim asks for current judgments of that
claim and preserves its original canonical approval.

Protocol tests use independent synthetic packs and authored fixture approvals:
`scripts/execution_lifecycle_smoke_test.py`, `scripts/test_production_execution.py`
and `scripts/test_production_adoption.py`, with authored reuse and refusal cases in
`scripts/test_production_adoption_decisions.py`. Synthetic usage proves accounting
mechanics, not provider prices or real user approval.
