# Production permissions

A task points to an `authority` JSON file that follows `schemas/authoring/production-authority.schema.json`.
Its `issuer` and `evidence.path`/`locator` refer to the instruction or approval whose bytes are pinned during preparation.
The host must check that this is the user's real authority.
The schema authenticates no issuer, proves no natural-language condition, and turns no agent-filled form into consent.

Each grant names:

- `id` and `actor`;
- `mode`, `direct` or `delegated`, which records the source of the instruction; both modes are bounded and bind the actual operation;
- the allowed `operations` and the exact `targets`;
- `limits` and `protected_criteria`;
- `request_scope`, the delegated cases a model request may fall in, or null;
- `submission_validation_modes`, the request validation modes a submission may use;
- `expires_at`, a UTC time or null, and optional UTC `effective_at` and `revoked_at`.

Use an explicit stop decision for ambiguity, contradictory constraints, unavailable controls or exhausted authority.

Operations are independent: `direction`, `edit`, `submit`, `select`, `adopt`.
A budget leaves personality change and canonical adoption unauthorized.
Permission to select a delivery leaves a new submission unauthorized.
Delegated creative decisions can proceed on their own, within their scope, protected conditions and stop conditions.

Targets are exact strings rather than wildcards:

- Direction uses `purpose` and `decision:<id>`.
- Submission and delivery selection use `delivery`.
- Canonical owner operations use `canon:sheet` or `canon:catalog`.
- A repair can affect `purpose`, `decision:<id>`, `source:<id>`, `criterion:<id>`, `delivery`, `execution` or `authority`, as the preparation comparison detects.

Grant only the necessary targets.
A changed source or criterion is detected whatever the repair is labeled, "local edit" included.
Protected criteria are checked on revision and on the next direction handoff.

`limits.uses` counts distinct external generation requests, and `limits.outputs` counts requested or captured outputs.
`limits.cost` is null for no paid work, or `{currency, amount}`.
Money is a nonnegative decimal **string**, never a floating-point estimate.
Budget arithmetic is exact Decimal arithmetic and never rounds.
A submit request carries a quoted `basis`, or an explicit zero-cost basis, and binds its exact output count.
Reserve a conservative permitted upper bound rather than a promise of final billing.
Independent grants share a budget only when the author deliberately uses the same grant identity and limit.

## Reservation and consumption

```text
python scripts/production_workflow.py draft-authorization --root STUDIO --run RUN --grant GRANT --intent intent.json --out authorization.json
python scripts/production_workflow.py authorize --root STUDIO --run RUN --file authorization.json
```

An intent command such as `handoff-intent` or `selection-intent` prints the exact operation to save as `intent.json`.
`draft-authorization` writes an **unapproved** draft with a blank reason, an empty cost and stop assessments set to false.
Creating it grants nothing.
Fill its reason, its quote when submitting, and every stop assessment from actual evidence.
`authorize` checks the declared grant and records an authorization receipt in the run.
The receipt records the IDs and digest of the criteria its grant protects, and it reserves no budget.
The consuming operation takes the receipt digest and rechecks the exact payload, actor, target set, authority, expiry and cumulative limits.
Execution reserves one use at the execution boundary, in one transaction with the current grant check and the dispatch claim.

An exact comparison covers scalar types and ordered array elements as well as object fields.
A boolean is not an authorized number.
A mismatch names the nested field or array element and the expected and actual value types.
The JSON Schema checker also treats booleans and numbers as different types, while 1 and 1.0 are equal schema values.
The prepared operation keeps its selected representation for request hashing and authorization.

A model dispatcher submission also carries `request_decision`, with four fields:

- `case`: the ID of the grant's `request_scope` case that the request falls in, or null when the grant has no request scope.
- `assessments`: one `{criterion, request_sha256, conclusion, reason}` for each review criterion of that case; each must conclude `satisfied`.
- `principal_approval`: `{request_sha256, principal, evidence{path, sha256, locator}}` naming the authority issuer, or null. A grant without a request scope needs it.
- `rendition_review`: `{request_sha256, reviewer, conclusion, reason, binding_ids}`, the actor's review of the exact final request. Its conclusion is `satisfied`, and `binding_ids` lists every transported reference binding.

`draft-execution` derives the identifiers and leaves every judgment empty.
The actual principal fills `principal_approval`; a delegated case with satisfied assessments stands in for it.
A synthetic draft without reference bindings (trimmed):

```json
{"case": null, "assessments": [], "principal_approval": null,
 "rendition_review": {"request_sha256": "71bece6826a2...", "reviewer": "SYNTHETIC FIXTURE OPERATOR - NOT USER CONSENT",
  "conclusion": null, "reason": "", "binding_ids": []}}
```

A missing target stops authorization as `GRANT_SCOPE_EXCEEDED`.
The diagnostic names the operation, the grant, its `granted` targets and the `missing` ones.
A synthetic `execute` under a grant that lacks `decision:expression` exits 3 with (trimmed):

```json
{"code": "GRANT_SCOPE_EXCEEDED", "phase": "authorization", "pointer": "$.targets",
 "required_action": "Obtain a current grant covering the missing targets; do not remove decisions or narrow targets.",
 "operation": "direction", "grant": "fixture-grant",
 "granted": ["canon:sheet", "delivery", "purpose"], "missing": ["decision:expression"]}
```

Reservations accumulate across all preparations with the same work task and grant ID.
Repeating preparation or revising the task leaves usage where it is.
A reservation stays outstanding until a settlement records the actual outputs and cost, or `release-reservation` returns it.
Abandoning the work task releases nothing, as [Production execution](production-execution.md#status-and-resume) describes.

A reservation can be released while no started step can have had an external effect.
A started upload or send blocks release until its saved result shows that it made nothing.
That result is `rejected` by the provider, or `not_executed` on the actor's evidence.
An error, a timeout or a lost connection alone is not that evidence.

Input changes require a current preparation.
An edit may intentionally change the parent's source files, while changed authority evidence and changed implementation are excluded from reuse.
A changed quote, service, package, seed, count, selection reason or recipient requires a new matching authorization.
Receipts are integrity records rather than cryptographic user signatures.
Leave run files unedited and undeleted, whatever budget they hold.
The host reports its own tool calls; the script cannot observe an unreported call outside this process.

Canonical adoption needs the owner's approval plus its own `adopt` authorization.
[Production execution](production-execution.md#select-optionally-adopt-and-finish) gives the order of selection, adoption and completion.
Low-level packaging and owner utilities show nothing about whether a production task has passed these gates.

## Current grant and execution budget

A prepared input does not pin the changing grant declaration or the work ledger's tail.
Each cited evidence reading is stored by path and SHA-256, with its locator, capture time and purpose.
A later append to a ledger therefore leaves an earlier approval of it valid.

Import a real authority update with `authority-import --root STUDIO --file FILE --expected-event EVENT`.
Its evidence and predecessor are retained.
Used quantities and outstanding reservations stay in the same formal event store.
Increasing a limit does not authorize different request bytes.
A decrease below recorded obligations shows as negative remaining budget, not rewritten history.
Where consumption alone exceeds a limit, `overrun` is true for that unit or currency.
The current limit is checked again immediately before every external-effect boundary.

The direction, handoff and submission receipts of one request share its single use.
A local adoption needs no generation reservation.
Unknown actual cost stays unknown, even after the images are acquired.
A transport wait holds no studio transaction.

`status --budget` reports used, outstanding and remaining quantities from the same events at Studio, grant and run scope.
Remaining is always grant-wide.
With `--run`, the view keeps that run's task and adds `run_share`, the run's own consumed and outstanding amounts.
Each reservation lists `release_eligible` and `release_reason`.
A synthetic grant with one unsent reservation (trimmed):

```json
{"grant": "fixture-grant", "limits": {"uses": 100, "outputs": 20, "cost": {"currency": "USD", "amount": "100"}},
 "consumed": {"uses": 0, "outputs": 0, "cost": {}},
 "outstanding_reserved": {"uses": 1, "outputs": 1, "cost": {"USD": "0"}},
 "remaining": {"uses": 99, "outputs": 19, "cost": {"USD": "100"}},
 "overrun": {"uses": false, "outputs": false, "cost": {"USD": false}},
 "run_share": {"run": "01a1032a-d1c8-...", "consumed": {"uses": 0, "outputs": 0, "cost": {}},
  "outstanding_reserved": {"uses": 1, "outputs": 1, "cost": {"USD": "0"}}}}
```

```text
python scripts/production_workflow.py draft-release --root STUDIO --run RUN --reservation RESERVATION --out release.json
python scripts/production_workflow.py release-reservation --root STUDIO --run RUN --request release.json
```

`draft-release` writes the release request with the actor's fields empty.
Fill in the actual actor, evidence and reason, then pass that file to `release-reservation`.
The actor is the reserving actor or the authority issuer.
Both commands check the request against `schemas/authoring/production-release.schema.json`.
A filled synthetic request:

```json
{"reservation_id": "01a1032b-09d5-78fa-86fe-e10849b84acd", "actor": "SYNTHETIC FIXTURE OPERATOR - NOT USER CONSENT",
 "evidence": {"path": "release/evidence.txt", "sha256": "4a43229abb8e0977a306a8b61ff4cc1ace0a5ea4b5171b332b74f3c09ca5e34e", "locator": "whole"},
 "reason": "Synthetic no-effect reservation release."}
```

Repeating the release reports `already_released` and releases nothing twice.

## Charges for separate external effects

The execution plan lists a send ceiling and, when media is uploaded, a separate aggregate upload ceiling.
Each uploaded input has one durable `external-step` and one `external-effect-result` receipt with the actual provider response.
The transport returns `provider_id`, `response` and `usage`.
`usage` is null, or a currency, a decimal-string amount and a `final` boolean.
No receipt is inferred from a quoted ceiling, and send usage covers the send alone.

Budget views show known effect charges as consumed, even when a later effect times out.
The unconfirmed remainder of the ceiling stays reserved.
Missing upload usage is never replaced by zero or by a known send charge.
Complete final receipts are summed once per currency.
A reported overrun is kept, and an overrun of an effect ceiling stops every later unsent effect.

Protocol tests with explicitly synthetic fees are in `scripts/test_production_execution.py` (`ExternalEffectAccountingTests`).
They do not establish a real provider's fee schedule.

## Authority updates during reviewed repairs

A review repair binds its changed creative scopes and `revised_input_sha256`.
Changing a grant limit or its evidence does not change that repair input.
The exact edit receipt still needs a current, valid grant when it is consumed.
A revoked grant stops the edit as `GRANT_REVOKED`, rather than inventing a creative scope change.
Import the actual authority update separately; an authority-only update is not a creative variant.
