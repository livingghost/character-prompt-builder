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

`draft-execution` produces one compact editing document for dispatcher and external image execution. Its `decisions` keep direction and submission separate. Select grants and write each operation's reason, stop assessments and request judgments; exact payloads, actors, counts and review hashes are derived from the prepared input when execution records the separate authorizations. For a dispatcher principal approval, select only its actual evidence `path` and `locator`; the runtime measures the bytes and binds the current issuer and exact request. Scope assessment entries contain criterion, conclusion and reason. The editing `rendition_review` contains its assessments; the runtime supplies the exact input and reference identities in the formal record.

Use the input workspace before the decision workspace to reconstruct the actual request, then compare it with the source commission and authority. Inspect the complete references, controls and `execution_plan.prompt_check` before approving. Draft assessments have null conclusions and empty reasons. Structural
checks and dictionary evidence cannot fill them. An unscoped dispatcher request
needs principal approval; a scoped delegation needs satisfied assessments.
`GRANT_SCOPE_EXCEEDED` names
missing targets and the current granted set without narrowing the requested work.

An execution claim records the unique owner of an authorized submission. The
owner, request hash and requested output count are durable before external I/O.
Each upload and send has a unique step, committed immediately before I/O after
current source, authority and implementation checks. One execution can start its
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
capture; it does not reopen submission or require a new generation approval.
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

A review repair binds its changed creative scopes and revised input hash. An
authority-only update is separate from a creative variant, and a revoked grant
stops consumption of an edit receipt as `GRANT_REVOKED`.

A new selection of a captured candidate uses its retained preparation, review
and artifact evidence together with current authority. Completion and recovery
verify that saved selection, its authorization and required destination evidence.
They do not renew an already recorded decision or require live creative sources
to remain at their original paths. Missing or corrupt retained evidence still
blocks them. New preparation and execution retain their live-source checks.

The selection's nullable `owner_acceptance` records an explicit decision by the
current authority issuer to use the candidate despite identified assessed
departures or unresolved matters. Its evidence path, hash and locator identify
the actual instruction. The host checks that instruction and its scope; an
agent-filled acceptance form establishes no consent. Every nonpass hard
criterion and unresolved entry must be covered, and an unassessed hard criterion
cannot be accepted in place of review. The authorization pins the evidence bytes
and the complete selection payload, including its candidate, exact review,
acceptance and destination. Later changes to the live evidence file cannot
rewrite that saved decision.

A `studio-slot` selection uses the `select` operation and `delivery` target to
authorize acceptance of the exact recorded iteration for its slot. Its compact
`draft-acceptance` and `accept` operations derive the formal identifiers and
record the selection, Studio acceptance and completion separately. The criterion
definitions remain unchanged, so accepting an assessed departure needs no
criterion-target amendment. The authority to change criteria or submit another
request remains separate.

Canonical adoption requires the owner's explicit approval plus its own `adopt`
authorization. The operation can use the existing selected candidate of a
completed or abandoned run with current authority. The source task stays closed;
its selection and review remain the evidence for that candidate. New production
decisions and submissions keep their own lifecycle and permissions. Follow
selection, adoption and completion in
[Production execution](production-adoption.md#select-optionally-adopt-and-finish).
The sheet stores the selected immutable image and provenance together; candidates
and historical selections cannot silently replace the current image.

Protocol tests use independent synthetic packs and authored fixture approvals:
`scripts/execution_lifecycle_smoke_test.py`, `scripts/test_production_execution.py`
and `scripts/test_production_adoption.py`. Synthetic usage proves accounting
mechanics, not provider prices or real user approval.
