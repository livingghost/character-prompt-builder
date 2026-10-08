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
- `rendition_review`: request hash, reviewer, satisfied conclusion, reason and
  every transported reference binding id.

`draft-execution` derives identifiers but never fills judgments. Inspect its
complete request, references, controls and `execution_plan.prompt_check` before
approving. Tag-check notes and dictionary meanings are evidence to examine, not
an automatic acceptance verdict. An unscoped request needs principal approval;
a scoped delegation needs satisfied assessments. `GRANT_SCOPE_EXCEEDED` names
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
reuses completed uploads, or checks the provider's recorded outcome. It never
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

Canonical adoption requires the owner's explicit approval plus its own `adopt`
authorization. It does not submit an image request. Follow selection, adoption and
completion in [Production execution](production-execution.md#select-optionally-adopt-and-finish).
The sheet stores the selected immutable image and provenance together; candidates
and historical selections cannot silently replace the current image.

Protocol tests use independent synthetic packs and authored fixture approvals:
`scripts/execution_lifecycle_smoke_test.py`, `scripts/test_production_execution.py`
and `scripts/test_production_adoption.py`. Synthetic usage proves accounting
mechanics, not provider prices or real user approval.
